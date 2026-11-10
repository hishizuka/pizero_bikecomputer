from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Callable

from .cps import CPS_SERVICE_UUID, CpsPowerProcessor
from .csc import CSC_SERVICE_UUID, CscCadenceProcessor, CscSpeedProcessor
from .discovery import discover_ble_devices
from .health import BleSessionHealth
from .hrs import HRS_SERVICE_UUID, HrsHeartRateProcessor
from .identity import format_ble_identity
from .pycycling_adapter import PycyclingValidationClient
from .session import (
    GATT_SETUP_TIMEOUT,
    BleGattLink,
    BleSetupDeadline,
    wait_for_any_event,
    wait_for_stop,
)
from .transport import (
    BleSensorCandidate,
    BleTransportProtocol,
    format_ble_error,
)

PROFILE_CSCS = "CSCS"
PROFILE_CPS = "CPS"
PROFILE_HRS = "HRS"
MAX_RECONNECT_DELAY = 30.0
PROFILE_SERVICE_UUIDS = {
    PROFILE_HRS: HRS_SERVICE_UUID,
    PROFILE_CSCS: CSC_SERVICE_UUID,
    PROFILE_CPS: CPS_SERVICE_UUID,
}
CyclingProcessor = (
    HrsHeartRateProcessor | CscSpeedProcessor | CscCadenceProcessor | CpsPowerProcessor
)


def _advertised_profiles(advertisement) -> tuple[str, ...]:
    advertised_uuids = {str(uuid).lower() for uuid in advertisement.service_uuids}
    return tuple(
        profile
        for profile, uuid in PROFILE_SERVICE_UUIDS.items()
        if uuid.lower() in advertised_uuids
    )


async def discover_cycling_devices(
    timeout: float = 10.0,
    *,
    adapter: str | None = None,
    profiles: tuple[str, ...] = (PROFILE_CSCS, PROFILE_CPS),
    discoverer=None,
) -> list[tuple[object, BleSensorCandidate]]:
    """Discover standard cycling sensors across the requested GATT profiles."""
    unknown_profiles = set(profiles) - set(PROFILE_SERVICE_UUIDS)
    if unknown_profiles:
        raise ValueError(f"Unknown BLE cycling profiles: {sorted(unknown_profiles)}")
    requested_profiles = set(profiles)

    def matches_profile(_device, advertisement) -> bool:
        return bool(
            requested_profiles.intersection(_advertised_profiles(advertisement))
        )

    discovered = await (discoverer or discover_ble_devices)(
        adapter=adapter,
        timeout=timeout,
        predicate=matches_profile,
    )

    candidates = []
    for device, advertisement in discovered:
        candidate_profiles = _advertised_profiles(advertisement)
        candidates.append(
            (
                device,
                BleSensorCandidate(
                    identifier=str(device.address),
                    name=device.name or advertisement.local_name,
                    rssi=advertisement.rssi,
                    profiles=candidate_profiles,
                ),
            )
        )
    candidates.sort(key=lambda item: item[1].identifier)
    return candidates


class BleCyclingSession:
    """Own one BleakClient and distribute HRS/CSCS/CPS data to bound roles."""

    def __init__(
        self,
        identifier: str,
        *,
        heart_rate_processor: HrsHeartRateProcessor | None = None,
        speed_processor: CscSpeedProcessor | None = None,
        cadence_processor: CscCadenceProcessor | None = None,
        power_processor: CpsPowerProcessor | None = None,
        cadence_profile: str | None = None,
        adapter: str | None = None,
        initial_device: object | None = None,
        name: str | None = None,
        on_name: Callable[[str | None], None] | None = None,
        on_cadence_profile: Callable[[str], None] | None = None,
        scan_timeout: float = 10.0,
        reconnect_delay: float = 2.0,
        max_reconnect_delay: float = MAX_RECONNECT_DELAY,
        should_accumulate: Callable[[], bool] | None = None,
        log: Callable[[str], None] | None = None,
        debug_log: Callable[[str], None] | None = None,
        transport: BleTransportProtocol,
    ):
        if not identifier.strip():
            raise ValueError("identifier must not be empty")
        if all(
            processor is None
            for processor in (
                heart_rate_processor,
                speed_processor,
                cadence_processor,
                power_processor,
            )
        ):
            raise ValueError("at least one cycling processor is required")
        if cadence_profile not in (None, PROFILE_CSCS, PROFILE_CPS):
            raise ValueError(f"Unknown cadence profile: {cadence_profile}")
        if reconnect_delay <= 0:
            raise ValueError("reconnect_delay must be positive")
        if max_reconnect_delay < reconnect_delay:
            raise ValueError(
                "max_reconnect_delay must not be less than reconnect_delay"
            )
        self.identifier = identifier.strip()
        self.heart_rate_processor = heart_rate_processor
        self.speed_processor = speed_processor
        self.cadence_processor = cadence_processor
        self.power_processor = power_processor
        self.cadence_profile = cadence_profile
        self.adapter = adapter
        self._initial_device = initial_device
        self.name = str(name or "").strip() or None
        self.on_name = on_name or (lambda _name: None)
        self.on_cadence_profile = on_cadence_profile or (lambda _profile: None)
        self.scan_timeout = scan_timeout
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self._next_retry_delay = reconnect_delay
        self.should_accumulate = should_accumulate or (lambda: True)
        self.log = log or (lambda _message: None)
        self.debug_log = debug_log or (lambda _message: None)
        self._attempt_started_at = 0.0
        self.transport = transport

    @property
    def processors(self) -> tuple[CyclingProcessor, ...]:
        return tuple(
            processor
            for processor in (
                self.heart_rate_processor,
                self.speed_processor,
                self.cadence_processor,
                self.power_processor,
            )
            if processor is not None
        )

    @property
    def health_records(self) -> tuple[BleSessionHealth, ...]:
        records = []
        for processor in self.processors:
            if processor.health is not None and processor.health not in records:
                records.append(processor.health)
        return tuple(records)

    @property
    def requested_profiles(self) -> tuple[str, ...]:
        profiles = []
        if self.heart_rate_processor is not None:
            profiles.append(PROFILE_HRS)
        if self.speed_processor is not None:
            profiles.append(PROFILE_CSCS)
        if self.power_processor is not None:
            profiles.append(PROFILE_CPS)
        if self.cadence_processor is not None:
            if self.cadence_profile is None:
                profiles.extend((PROFILE_CSCS, PROFILE_CPS))
            else:
                profiles.append(self.cadence_profile)
        return tuple(dict.fromkeys(profiles))

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            for processor in self.processors:
                processor.set_connecting()
            stage = "scan"
            try:
                device = await self._next_device()
                if device is None:
                    await self._wait_retry(stop_event)
                    continue
                stage = "connection"
                await self._connect_once(device, stop_event)
            except Exception as exc:
                for health in self.health_records:
                    health.record_connect_failure()
                for processor in self.processors:
                    processor.on_disconnected()
                self.log(f"{stage} failed: {format_ble_error(exc)}")
            if not stop_event.is_set():
                await self._wait_retry(stop_event)

    async def _next_device(self):
        self._attempt_started_at = time.monotonic()
        for health in self.health_records:
            health.record_connect_attempt()
        if self._initial_device is not None:
            device = self._initial_device
            self._initial_device = None
            return device
        return await self._find_device()

    async def _find_device(self):
        scan_started_at = time.monotonic()
        self.debug_log(f"scan waiting on {self.adapter or 'platform default'}")
        device = await self.transport.find_device(
            self.identifier,
            timeout=self.scan_timeout,
            adapter=self.adapter,
        )
        scan_elapsed = time.monotonic() - scan_started_at
        if device is not None:
            self.debug_log(f"sensor found after {scan_elapsed:.3f}s")
            self.name = device.name
            self.on_name(self.name)
            return device
        self.debug_log(f"scan timed out after {scan_elapsed:.3f}s")
        self.log("configured sensor was not found; wake the sensor and try again")
        return None

    async def _connect_once(self, device, stop_event: asyncio.Event) -> None:
        from pycycling.cycling_power_service import CyclingPowerService
        from pycycling.cycling_speed_cadence_service import (
            CyclingSpeedCadenceService,
        )
        from pycycling.heart_rate_service import HeartRateService

        def on_unexpected_disconnect() -> None:
            for processor in self.processors:
                processor.on_disconnected()
            for health in self.health_records:
                health.record_unexpected_disconnect()

        link = BleGattLink(
            self.transport,
            device,
            adapter=self.adapter,
            on_unexpected_disconnect=on_unexpected_disconnect,
        )
        client = link.client
        pycycling_client = PycyclingValidationClient(
            client,
            on_invalid_payload=lambda uuid, actual, expected: self.log(
                f"ignored malformed notification: {uuid}, "
                f"length={actual}, expected={expected}"
            ),
        )
        hrs_service = HeartRateService(pycycling_client)
        csc_service = CyclingSpeedCadenceService(pycycling_client)
        cps_service = CyclingPowerService(pycycling_client)
        hrs_notifications_enabled = False
        csc_notifications_enabled = False
        cps_notifications_enabled = False
        feature_task = None
        first_notification_profiles = set()
        confirmed_cadence_profiles = set()
        stage = "gatt_connect"

        def confirm_cadence_profile(profile: str) -> None:
            if profile in confirmed_cadence_profiles:
                return
            confirmed_cadence_profiles.add(profile)
            self.on_cadence_profile(profile)

        def log_first_notification(profile: str, received_at: float) -> None:
            if profile in first_notification_profiles:
                return
            first_notification_profiles.add(profile)
            self.debug_log(
                f"first {profile} notification after "
                f"{received_at - self._attempt_started_at:.3f}s"
            )

        try:
            connect_started_at = time.monotonic()
            await link.connect()
            setup_deadline = BleSetupDeadline(GATT_SETUP_TIMEOUT)

            self.debug_log(
                f"GATT connected after {time.monotonic() - connect_started_at:.3f}s"
            )
            device_name = str(device.name or "").strip()
            if device_name and not self.name:
                self.name = device_name
                self.on_name(self.name)

            stage = "profile_discovery"
            hrs_available = self._profile_available(client, PROFILE_HRS)
            csc_available = self._profile_available(client, PROFILE_CSCS)
            cps_available = self._profile_available(client, PROFILE_CPS)
            csc_wheel_supported = csc_available
            csc_crank_supported = csc_available
            cps_crank_supported = cps_available
            cadence_source = self._select_cadence_source(
                csc_crank_supported,
                cps_crank_supported,
            )

            def on_hrs_measurement(measurement) -> None:
                if hrs_available and self.heart_rate_processor is not None:
                    received_at = time.monotonic()
                    log_first_notification(PROFILE_HRS, received_at)
                    if pycycling_client.hrs_sensor_contact_observed:
                        measurement = measurement._replace(
                            sensor_contact=pycycling_client.hrs_sensor_contact
                        )
                    self.heart_rate_processor.handle_measurement(
                        measurement,
                        received_at=received_at,
                    )

            def on_csc_measurement(measurement) -> None:
                received_at = time.monotonic()
                log_first_notification(PROFILE_CSCS, received_at)
                if csc_wheel_supported and self.speed_processor is not None:
                    self.speed_processor.handle_measurement(
                        measurement,
                        received_at=received_at,
                        accumulate_distance=self.should_accumulate(),
                    )
                if (
                    cadence_source == PROFILE_CSCS
                    and self.cadence_processor is not None
                ):
                    self.cadence_processor.handle_measurement(
                        measurement,
                        received_at=received_at,
                    )

            def on_cps_measurement(measurement) -> None:
                received_at = time.monotonic()
                log_first_notification(PROFILE_CPS, received_at)
                if (
                    measurement.cumulative_crank_revs is not None
                    and measurement.last_crank_event_time is not None
                ):
                    confirm_cadence_profile(PROFILE_CPS)
                if cps_available and self.power_processor is not None:
                    self.power_processor.handle_measurement(
                        measurement,
                        received_at=received_at,
                        accumulate_work=self.should_accumulate(),
                    )
                if cadence_source == PROFILE_CPS and self.cadence_processor is not None:
                    self.cadence_processor.handle_measurement(
                        measurement,
                        received_at=received_at,
                    )

            stage = "start_notify:HRS"
            if hrs_available and self.heart_rate_processor is not None:
                hrs_service.set_hr_measurement_handler(on_hrs_measurement)
                await setup_deadline.wait(
                    hrs_service.enable_hr_measurement_notifications()
                )
                hrs_notifications_enabled = True
            stage = "start_notify:CSCS"
            if csc_available and (
                self.speed_processor is not None
                or (
                    PROFILE_CSCS in self.requested_profiles
                    and self.cadence_processor is not None
                )
            ):
                csc_service.set_csc_measurement_handler(on_csc_measurement)
                await setup_deadline.wait(
                    csc_service.enable_csc_measurement_notifications()
                )
                csc_notifications_enabled = True
            stage = "start_notify:CPS"
            if cps_available and (
                self.power_processor is not None
                or (
                    PROFILE_CPS in self.requested_profiles
                    and self.cadence_processor is not None
                )
            ):
                cps_service.set_cycling_power_measurement_handler(on_cps_measurement)
                await setup_deadline.wait(
                    cps_service.enable_cycling_power_measurement_notifications()
                )
                cps_notifications_enabled = True

            cadence_notifications_enabled = self._cadence_notifications_enabled(
                cadence_source, csc_notifications_enabled, cps_notifications_enabled
            )
            processor_states = (
                (
                    self.heart_rate_processor,
                    hrs_notifications_enabled,
                    "Heart Rate Service is not supported",
                ),
                (
                    self.speed_processor,
                    csc_notifications_enabled,
                    "CSCS wheel revolution data is not supported",
                ),
                (
                    self.power_processor,
                    cps_notifications_enabled,
                    "Cycling Power Service is not supported",
                ),
                (
                    self.cadence_processor,
                    cadence_notifications_enabled,
                    "crank revolution data is not supported",
                ),
            )
            for processor, enabled, unavailable_message in processor_states:
                self._set_processor_availability(
                    processor, enabled, unavailable_message
                )
            if not (
                hrs_notifications_enabled
                or csc_notifications_enabled
                or cps_notifications_enabled
            ):
                raise RuntimeError(
                    "no requested measurement notifications are available"
                )
            for health in self.health_records:
                if any(
                    enabled and processor is not None and processor.health is health
                    for processor, enabled, _ in processor_states
                ):
                    health.record_connected()
            self._next_retry_delay = self.reconnect_delay
            self.debug_log(
                f"notifications enabled after "
                f"{time.monotonic() - self._attempt_started_at:.3f}s"
            )
            self.log(f"connected to {format_ble_identity(self.name, self.identifier)}")
            await link.mark_ready()

            async def refine_profile_features() -> None:
                nonlocal csc_wheel_supported
                nonlocal csc_crank_supported
                nonlocal cps_crank_supported
                nonlocal cadence_source
                try:
                    csc_feature, cps_feature = await asyncio.gather(
                        self._read_profile_feature(
                            PROFILE_CSCS, csc_available, csc_service.get_csc_feature
                        ),
                        self._read_profile_feature(
                            PROFILE_CPS,
                            cps_available,
                            cps_service.get_cycling_power_feature,
                        ),
                    )
                    if csc_feature is not None:
                        csc_wheel_supported = bool(csc_feature.wheel_rev_supported)
                        csc_crank_supported = bool(csc_feature.crank_rev_supported)
                    if cps_feature is not None:
                        cps_crank_supported = bool(cps_feature.crank_rev_supported)
                        if cps_crank_supported:
                            confirm_cadence_profile(PROFILE_CPS)
                    selected_cadence_source = self._select_cadence_source(
                        csc_crank_supported,
                        cps_crank_supported,
                    )
                    if self.speed_processor is not None and not csc_wheel_supported:
                        self._set_processor_availability(
                            self.speed_processor,
                            False,
                            "CSCS wheel revolution data is not supported",
                        )
                    if selected_cadence_source != cadence_source:
                        cadence_source = selected_cadence_source
                        self._set_processor_availability(
                            self.cadence_processor,
                            self._cadence_notifications_enabled(
                                cadence_source,
                                csc_notifications_enabled,
                                cps_notifications_enabled,
                            ),
                            "crank revolution data is not supported",
                        )
                except Exception as exc:
                    self.log(f"Feature processing failed: {format_ble_error(exc)}")

            stage = "feature_read"
            feature_task = asyncio.create_task(refine_profile_features())
            stage = "connected_wait"
            await wait_for_any_event(stop_event, link.disconnected)
        except Exception as exc:
            raise RuntimeError(f"{stage}: {format_ble_error(exc)}") from exc
        finally:
            if feature_task is not None:
                feature_task.cancel()
                await asyncio.gather(feature_task, return_exceptions=True)
            link.expect_disconnect()
            if client.is_connected:
                if hrs_notifications_enabled:
                    with contextlib.suppress(Exception):
                        await hrs_service.disable_hr_measurement_notifications()
                if csc_notifications_enabled:
                    with contextlib.suppress(Exception):
                        await csc_service.disable_csc_measurement_notifications()
                if cps_notifications_enabled:
                    with contextlib.suppress(Exception):
                        await cps_service.disable_cycling_power_measurement_notifications()
            await link.close()

    def _profile_available(self, client, profile: str) -> bool:
        if profile not in self.requested_profiles:
            return False
        return client.services.get_service(PROFILE_SERVICE_UUIDS[profile]) is not None

    def _set_processor_availability(
        self,
        processor: CyclingProcessor | None,
        available: bool,
        unavailable_message: str,
    ) -> None:
        if processor is None:
            return
        if available:
            processor.set_connected()
            return
        processor.on_disconnected()
        self.log(unavailable_message)

    async def _read_profile_feature(self, profile: str, available: bool, read_feature):
        if not available:
            return None
        try:
            return await read_feature()
        except Exception as exc:
            self.log(f"{profile} Feature read failed: {format_ble_error(exc)}")
            return None

    @staticmethod
    def _cadence_notifications_enabled(
        cadence_source: str | None,
        csc_notifications_enabled: bool,
        cps_notifications_enabled: bool,
    ) -> bool:
        if cadence_source == PROFILE_CSCS:
            return csc_notifications_enabled
        if cadence_source == PROFILE_CPS:
            return cps_notifications_enabled
        return False

    def _select_cadence_source(
        self,
        csc_crank_supported: bool,
        cps_crank_supported: bool,
    ) -> str | None:
        if self.cadence_processor is None:
            return None
        if self.cadence_profile == PROFILE_CSCS:
            return PROFILE_CSCS if csc_crank_supported else None
        if self.cadence_profile == PROFILE_CPS:
            return PROFILE_CPS if cps_crank_supported else None
        if self.power_processor is not None and cps_crank_supported:
            return PROFILE_CPS
        if self.speed_processor is not None and csc_crank_supported:
            return PROFILE_CSCS
        if csc_crank_supported:
            return PROFILE_CSCS
        if cps_crank_supported:
            return PROFILE_CPS
        return None

    async def _wait_retry(self, stop_event: asyncio.Event) -> None:
        delay = self._next_retry_delay
        self.debug_log(f"retrying after {delay:.1f}s")
        await wait_for_stop(stop_event, delay)
        self._next_retry_delay = min(self.max_reconnect_delay, delay * 2.0)
