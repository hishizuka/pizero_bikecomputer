import asyncio
import math
import sys
from dataclasses import dataclass

from modules.app_logger import app_logger
from modules.sensor.light_control import LightControlState

from .ble.adapter import (
    BleAdapterPolicy,
    BleAdapterResolutionError,
    BleAdapterResolver,
)
from .ble.health import BleSessionHealth
from .ble.bontrager_light import (
    BONTRAGER_LIGHT_TYPE,
    MODE_VALUES as LIGHT_MODE_VALUES,
    BontragerLightSession,
    discover_bontrager_lights,
)
from .ble import zwift_click_v2
from .ble.zwift_click_v2 import (
    ZWIFT_CLICK_AVAILABLE as _HAS_ZWIFT_CLICK_V2,
    ZwiftClickV2Session,
)
from .ble.transport import BleakTransport, BleSensorCandidate, BleTransportProtocol
from .sensor import Sensor

_HAS_BLE = False
try:
    import bleak  # noqa: F401

    _HAS_BLE = True
except ImportError:
    pass

_HAS_BLE_CYCLING = False
try:
    import pycycling  # noqa: F401

    from .ble.cps import CpsPowerProcessor
    from .ble.csc import CscCadenceProcessor, CscSpeedProcessor
    from .ble.cycling import (
        BleCyclingSession,
        PROFILE_CPS,
        PROFILE_CSCS,
        PROFILE_HRS,
        discover_cycling_devices,
    )
    from .ble.hrs import HrsHeartRateProcessor

    _HAS_BLE_CYCLING = _HAS_BLE
except ImportError:
    pass

if _HAS_BLE or _HAS_ZWIFT_CLICK_V2 or _HAS_BLE_CYCLING:
    app_logger.info("  BLE")


@dataclass(frozen=True, slots=True)
class _CyclingSessionSpec:
    roles: tuple[str, ...]
    cadence_profile: str | None
    adapter: str | None


class SensorBLE(Sensor):
    CYCLING_ROLES = ("HR", "SPD", "CDC", "PWR")
    LIGHT_ROLE = "LGT"
    LIGHT_TYPE = BONTRAGER_LIGHT_TYPE
    CONTROL_ROLE = "CTRL"
    CONTROL_TYPE = "ZWIFT_CLICK_V2"
    LIGHT_DEFAULT_ON_MODE = "FLASH_LOW"
    LIGHT_AUTO_MIN_DURATION = 5.0

    def __init__(
        self,
        config,
        values,
        *,
        transport: BleTransportProtocol | None = None,
    ):
        self.transport = transport or BleakTransport()
        self._closed = False
        self._light_health = BleSessionHealth()
        super().__init__(config, values)
        self._cycling_health = {role: BleSessionHealth() for role in self.CYCLING_ROLES}
        self._cycling_discovered_devices = {}
        self._cycling_discovered_profiles = {}
        self._cycling_cadence_profiles = {}
        self._hrs_heart_rate_processor = None
        self._csc_speed_processor = None
        self._csc_cadence_processor = None
        self._cps_power_processor = None
        if _HAS_BLE_CYCLING:
            self._hrs_heart_rate_processor = HrsHeartRateProcessor(
                health=self._cycling_health["HR"],
            )
            self._csc_speed_processor = CscSpeedProcessor(
                self.config.G_WHEEL_CIRCUMFERENCE,
                health=self._cycling_health["SPD"],
            )
            self._csc_cadence_processor = CscCadenceProcessor(
                health=self._cycling_health["CDC"],
            )
            self._cps_power_processor = CpsPowerProcessor(
                health=self._cycling_health["PWR"],
            )
        self._cycling_processors = {
            "HR": self._hrs_heart_rate_processor,
            "SPD": self._csc_speed_processor,
            "CDC": self._csc_cadence_processor,
            "PWR": self._cps_power_processor,
        }
        self._publish_cycling_values()

    def sensor_init(self):
        self._cycling_stop_events = {}
        self._cycling_tasks = {}
        self._cycling_session_roles = {}
        self._cycling_session_specs = {}
        self._cycling_desired_specs = {}
        self._cycling_reconcile_revision = 0
        self._cycling_reconcile_task = None
        self._light_discovered_devices = {}
        self._light_session = None
        self._light_stop_event = None
        self._light_task = None
        self._light_control = LightControlState(
            LIGHT_MODE_VALUES,
            self.LIGHT_DEFAULT_ON_MODE,
            auto_min_duration=self.LIGHT_AUTO_MIN_DURATION,
        )
        self._light_control.reset(self.config.G_AUTO_LIGHT)
        self.values[self.LIGHT_ROLE] = {
            "status": "inactive",
            "light_state": self._light_control.state,
            "light_mode": self._light_control.desired_mode,
            "actual_light_mode": None,
            "battery_percentage": None,
            "command_status": "idle",
        }
        self.click = ZwiftClickV2Session(
            self.config, self._resolve_sensor_adapter, transport=self.transport
        )

    def reset(self):
        if self._csc_speed_processor is not None:
            self._csc_speed_processor.reset_distance()
        if self._cps_power_processor is not None:
            self._cps_power_processor.reset_accumulated_power()
        self._publish_cycling_values()

    def start_coroutine(self):
        if self._closed:
            raise RuntimeError("The Bluetooth sensor has been closed")
        self.connect_cycling_sensors()
        self.connect_light()
        self.connect_zwift_click_v2()

    def pause_recording(self):
        for processor in (self._csc_speed_processor, self._cps_power_processor):
            if processor is not None:
                processor.pause_recording()

    def quit(self):
        self.disconnect_cycling_sensors()
        self.disconnect_light()
        self.disconnect_zwift_click_v2()
        for role, health_record in self._cycling_health.items():
            snapshot = health_record.snapshot()
            if snapshot.connect_attempt_count == 0:
                continue
            app_logger.debug(
                f"[BLE_HEALTH] cycling_{role.lower()}={snapshot.as_dict()}"
            )
        snapshot = self.click.health.snapshot()
        if snapshot.connect_attempt_count > 0:
            app_logger.debug(f"[BLE_HEALTH] zwift_click_v2={snapshot.as_dict()}")
        snapshot = self._light_health.snapshot()
        if snapshot.connect_attempt_count > 0:
            app_logger.debug(f"[BLE_HEALTH] light={snapshot.as_dict()}")

    async def close(self):
        self._closed = True
        self.quit()
        await self.click.close()
        if self._cycling_reconcile_task is not None:
            await self._cycling_reconcile_task
        if self._light_task is not None:
            await asyncio.gather(self._light_task, return_exceptions=True)

    def update(self) -> None:
        for processor in self._cycling_processors.values():
            if processor is None:
                continue
            processor.tick()
            processor.report_notification_silence()
        self._publish_cycling_values()

    def _publish_cycling_values(self) -> None:
        self._publish_hrs_heart_rate_values()
        self._publish_csc_speed_values()
        self._publish_csc_cadence_values()
        self._publish_cps_power_values()

    def _publish_hrs_heart_rate_values(self) -> None:
        processor = self._hrs_heart_rate_processor
        if processor is None:
            self.values["HR"] = {
                "heart_rate": math.nan,
                "sensor_contact": None,
                "energy_expended": None,
                "rr_intervals": (),
                "status": "inactive",
                "measured_at": None,
                "received_at": None,
            }
            return
        reading = processor.heart_rate
        self.values["HR"] = {
            "heart_rate": reading.value,
            "sensor_contact": processor.sensor_contact,
            "energy_expended": processor.energy_expended,
            "rr_intervals": processor.rr_intervals,
            "status": processor.status.value,
            "measured_at": reading.measured_at,
            "received_at": reading.received_at,
        }

    def _publish_csc_speed_values(self) -> None:
        processor = self._csc_speed_processor
        if processor is None:
            self.values["SPD"] = {
                "speed": math.nan,
                "distance": 0.0,
                "status": "inactive",
                "measured_at": None,
                "received_at": None,
            }
            return
        reading = processor.speed
        self.values["SPD"] = {
            "speed": reading.value,
            "distance": processor.distance,
            "status": processor.status.value,
            "measured_at": reading.measured_at,
            "received_at": reading.received_at,
        }

    def _publish_csc_cadence_values(self) -> None:
        processor = self._csc_cadence_processor
        if processor is None:
            self.values["CDC"] = {
                "cadence": math.nan,
                "status": "inactive",
                "measured_at": None,
                "received_at": None,
            }
            return
        reading = processor.cadence
        self.values["CDC"] = {
            "cadence": reading.value,
            "status": processor.status.value,
            "measured_at": reading.measured_at,
            "received_at": reading.received_at,
        }

    def _publish_cps_power_values(self) -> None:
        processor = self._cps_power_processor
        if processor is None:
            self.values["PWR"] = {
                "power": math.nan,
                "accumulated_power": 0.0,
                "status": "inactive",
                "measured_at": None,
                "received_at": None,
            }
            return
        reading = processor.power
        self.values["PWR"] = {
            "power": reading.value,
            "accumulated_power": processor.accumulated_power,
            "status": processor.status.value,
            "measured_at": reading.measured_at,
            "received_at": reading.received_at,
        }

    def is_sensor_available(self, role: str) -> bool:
        if role == self.CONTROL_ROLE:
            return self.click.is_enabled()
        if role == self.LIGHT_ROLE:
            return bool(
                (_HAS_BLE or self.transport.remote)
                and self.config.ble_sensor_enabled()
                and self.config.is_sensor_configured(
                    role, self.config.SENSOR_PROTOCOL_BLE
                )
            )
        if role not in self.CYCLING_ROLES or not _HAS_BLE_CYCLING:
            return False
        return bool(
            self.config.ble_sensor_enabled()
            and self.config.is_sensor_configured(role, self.config.SENSOR_PROTOCOL_BLE)
        )

    def is_sensor_connected(self, role: str) -> bool:
        if role == self.CONTROL_ROLE:
            return self.get_sensor_connection_status(role) == "connected"
        if role == self.LIGHT_ROLE:
            return self.values[self.LIGHT_ROLE]["status"] == "connected"
        if role not in self.CYCLING_ROLES:
            return False
        processor = self._cycling_processors[role]
        if processor is None:
            return False
        return processor.status.value == "connected"

    def get_sensor_connection_status(self, role: str) -> str:
        if not self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE):
            return "inactive"
        if not self.is_sensor_available(role):
            return "disconnected"
        if role == self.CONTROL_ROLE:
            return self.click.connection_status
        if role == self.LIGHT_ROLE:
            return self.values[self.LIGHT_ROLE]["status"]
        status = self._cycling_processors[role].status.value
        if status in ("connected", "disconnected"):
            return status
        return "connecting"

    def can_scan_cycling_sensors(self, role: str | None = None) -> bool:
        return bool(
            (role is None or role in self.CYCLING_ROLES)
            and _HAS_BLE_CYCLING
            and self.config.ble_sensor_enabled()
        )

    def can_scan_sensor(self, role: str) -> bool:
        if role in self.CYCLING_ROLES:
            return self.can_scan_cycling_sensors(role)
        if role == self.LIGHT_ROLE:
            return bool(
                (_HAS_BLE or self.transport.remote) and self.config.ble_sensor_enabled()
            )
        return bool(
            role == self.CONTROL_ROLE
            and _HAS_ZWIFT_CLICK_V2
            and self.transport.supports_control
            and self.config.ble_sensor_enabled()
        )

    async def discover_sensors(
        self,
        role: str,
        timeout: float = 10.0,
    ) -> list[BleSensorCandidate]:
        if role in self.CYCLING_ROLES:
            return await self.discover_cycling_sensors(role, timeout)
        if role == self.LIGHT_ROLE:
            if not self.can_scan_sensor(role):
                return []
            adapter = self._resolve_sensor_adapter()
            if not self._cycling_adapter_available(adapter):
                return []
            devices = await discover_bontrager_lights(
                timeout=timeout,
                adapter=adapter,
                discoverer=self.transport.discover,
            )
            self._light_discovered_devices = {
                candidate.identifier: device for device, candidate in devices
            }
            return [candidate for _device, candidate in devices]
        if role != self.CONTROL_ROLE or not self.can_scan_sensor(role):
            return []
        adapter = self._resolve_sensor_adapter()
        if not self._cycling_adapter_available(adapter):
            return []
        devices = await zwift_click_v2.scan_for_click_v2(
            timeout=timeout,
            prefer_left=True,
            adapter=adapter,
            discoverer=self.transport.discover,
        )
        return [
            BleSensorCandidate(
                identifier=str(click.device.address),
                name=click.device.name,
                rssi=None,
            )
            for click in devices
            if click.side == "left"
        ]

    def known_sensor_candidates(self, role: str) -> list[BleSensorCandidate]:
        if role == self.LIGHT_ROLE:
            if not self.config.is_sensor_configured(
                role, self.config.SENSOR_PROTOCOL_BLE
            ):
                return []
            sensor = self.config.G_SENSORS[role]
            return [
                BleSensorCandidate(
                    identifier=sensor["ID"],
                    name=sensor["NAME"] or None,
                    rssi=None,
                    profiles=(self.LIGHT_TYPE,),
                )
            ]
        if role not in self.CYCLING_ROLES:
            return []

        candidates = {}

        def add_candidate(source_role: str, profiles: tuple[str, ...]) -> None:
            if not self.config.is_sensor_configured(
                source_role, self.config.SENSOR_PROTOCOL_BLE
            ):
                return
            sensor = self.config.G_SENSORS[source_role]
            identifier = sensor["ID"]
            candidates[identifier] = BleSensorCandidate(
                identifier=identifier,
                name=sensor["NAME"] or None,
                rssi=None,
                profiles=profiles,
            )

        sensor = self.config.G_SENSORS[role]
        profile = sensor["TYPE"]
        if profile is None and len(self.config.G_BLE_SENSOR_TYPES[role]) == 1:
            profile = self.config.G_BLE_SENSOR_TYPES[role][0]
        add_candidate(role, () if profile is None else (profile,))

        if role == "CDC":
            power = self.config.G_SENSORS["PWR"]
            power_profiles = self._cycling_cadence_profiles.get(power["ID"], ())
            if power["TYPE"] == PROFILE_CPS or PROFILE_CPS in power_profiles:
                add_candidate("PWR", (PROFILE_CPS,))
        elif role == "PWR":
            cadence = self.config.G_SENSORS["CDC"]
            cadence_profiles = self._cycling_cadence_profiles.get(cadence["ID"], ())
            if cadence["TYPE"] == PROFILE_CPS or PROFILE_CPS in cadence_profiles:
                add_candidate("CDC", (PROFILE_CPS,))

        return list(candidates.values())

    def _scan_profiles_for_role(self, role: str) -> tuple[str, ...]:
        if role == "HR":
            return (PROFILE_HRS,)
        if role == "SPD":
            return (PROFILE_CSCS,)
        if role == "PWR":
            return (PROFILE_CPS,)
        if role == "CDC":
            return (PROFILE_CSCS, PROFILE_CPS)
        return ()

    async def discover_cycling_sensors(
        self,
        role: str,
        timeout: float = 10.0,
    ) -> list[BleSensorCandidate]:
        self._cycling_discovered_devices.clear()
        self._cycling_discovered_profiles.clear()
        if not self.can_scan_cycling_sensors(role):
            return []
        adapter = self._resolve_sensor_adapter()
        if not self._cycling_adapter_available(adapter):
            return []
        devices = await discover_cycling_devices(
            timeout=timeout,
            adapter=adapter,
            profiles=self._scan_profiles_for_role(role),
            discoverer=self.transport.discover,
        )
        self._cycling_discovered_devices = {
            candidate.identifier: device for device, candidate in devices
        }
        self._cycling_discovered_profiles = {
            candidate.identifier: candidate.profiles for _device, candidate in devices
        }
        return [candidate for _device, candidate in devices]

    def set_cycling_sensor(
        self,
        role: str,
        identifier: str,
        name: str = "",
        profile: str | None = None,
    ) -> None:
        if role not in self.CYCLING_ROLES:
            raise ValueError(f"Unsupported BLE cycling role: {role}")
        identifier = identifier.strip()
        if not identifier:
            raise ValueError("identifier must not be empty")
        profile = self._select_pairing_profile(role, identifier, profile)
        self.config.set_sensor(
            role,
            self.config.SENSOR_PROTOCOL_BLE,
            identifier,
            profile,
            name,
        )
        self.config.setting.write_config()
        self.connect_cycling_sensors()

    def set_ble_sensor(
        self,
        role: str,
        identifier: str,
        name: str = "",
        profile: str | None = None,
    ) -> None:
        if role in self.CYCLING_ROLES:
            self.set_cycling_sensor(role, identifier, name, profile)
            return
        if role == self.LIGHT_ROLE:
            self.disconnect_light()
            self.config.set_sensor(
                role,
                self.config.SENSOR_PROTOCOL_BLE,
                identifier,
                self.LIGHT_TYPE,
                name,
            )
            self.config.setting.write_config()
            self.connect_light()
            return
        if role != self.CONTROL_ROLE:
            raise ValueError(f"Unsupported BLE sensor role: {role}")
        self.disconnect_zwift_click_v2()
        self.config.set_sensor(
            role,
            self.config.SENSOR_PROTOCOL_BLE,
            identifier,
            self.CONTROL_TYPE,
            name,
        )
        self.config.setting.write_config()
        self.connect_zwift_click_v2()

    def _select_pairing_profile(
        self,
        role: str,
        identifier: str,
        profile: str | None,
    ) -> str | None:
        if role == "HR":
            return PROFILE_HRS
        if role == "SPD":
            return PROFILE_CSCS
        if role == "PWR":
            return PROFILE_CPS
        if profile in (PROFILE_CSCS, PROFILE_CPS):
            return profile
        profiles = self._cycling_discovered_profiles.get(identifier, ())
        if len(profiles) == 1:
            return profiles[0]
        if (
            PROFILE_CPS in profiles
            and self.config.sensor_uses("PWR", self.config.SENSOR_PROTOCOL_BLE)
            and self.config.G_SENSORS["PWR"]["ID"] == identifier
        ):
            return PROFILE_CPS
        if PROFILE_CSCS in profiles:
            return PROFILE_CSCS
        if PROFILE_CPS in profiles:
            return PROFILE_CPS
        return None

    def remove_cycling_sensor(self, role: str) -> None:
        if role not in self.CYCLING_ROLES:
            return
        if self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE):
            self.config.clear_sensor(role)
        self.config.setting.write_config()
        self.connect_cycling_sensors()

    def remove_ble_sensor(self, role: str) -> None:
        if role in self.CYCLING_ROLES:
            self.remove_cycling_sensor(role)
            return
        if role == self.LIGHT_ROLE:
            self.disconnect_light()
            if self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE):
                self.config.clear_sensor(role)
            self.config.setting.write_config()
            return
        if role != self.CONTROL_ROLE:
            raise ValueError(f"Unsupported BLE sensor role: {role}")
        self.disconnect_zwift_click_v2()
        if self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE):
            self.config.clear_sensor(role)
        self.config.setting.write_config()

    def _configured_cycling_roles(self) -> dict[str, list[str]]:
        roles_by_identifier = {}
        for role in self.CYCLING_ROLES:
            if not self.is_sensor_available(role):
                continue
            identifier = self.config.G_SENSORS[role]["ID"]
            roles_by_identifier.setdefault(identifier, []).append(role)
        return roles_by_identifier

    def connect_cycling_sensors(self) -> bool:
        roles_by_identifier = self._configured_cycling_roles()
        if not roles_by_identifier:
            self._schedule_cycling_reconcile({})
            return False
        adapter = self._resolve_sensor_adapter()
        if not self._cycling_adapter_available(adapter):
            self._schedule_cycling_reconcile({})
            return False
        desired_specs = {}
        for identifier, roles in roles_by_identifier.items():
            desired_specs[identifier] = _CyclingSessionSpec(
                roles=tuple(roles),
                cadence_profile=self._configured_cadence_profile(identifier, roles),
                adapter=adapter,
            )
        self._schedule_cycling_reconcile(desired_specs)
        return True

    def _schedule_cycling_reconcile(
        self,
        desired_specs: dict[str, _CyclingSessionSpec],
    ) -> None:
        self._cycling_desired_specs = desired_specs
        self._cycling_reconcile_revision += 1
        task = self._cycling_reconcile_task
        if task is not None and not task.done():
            return
        self._cycling_reconcile_task = None

        requires_cleanup = any(
            task.done()
            or desired_specs.get(identifier) != self._cycling_session_specs[identifier]
            for identifier, task in self._cycling_tasks.items()
        )
        if requires_cleanup:
            self._cycling_reconcile_task = asyncio.create_task(
                self._reconcile_cycling_sessions()
            )
            return

        for identifier, spec in desired_specs.items():
            if not self._is_cycling_session_running(identifier):
                self._start_cycling_session(identifier, spec)

    async def _reconcile_cycling_sessions(self) -> None:
        current_task = asyncio.current_task()
        try:
            while True:
                revision = self._cycling_reconcile_revision
                desired_specs = self._cycling_desired_specs.copy()
                await self._reconcile_cycling_sessions_once(
                    desired_specs,
                    revision,
                )
                if revision == self._cycling_reconcile_revision:
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app_logger.error(f"BLE cycling session reconciliation failed: {exc}")
        finally:
            if self._cycling_reconcile_task is current_task:
                self._cycling_reconcile_task = None

    async def _reconcile_cycling_sessions_once(
        self,
        desired_specs: dict[str, _CyclingSessionSpec],
        revision: int,
    ) -> None:
        stopping = []
        stopped_roles = set()
        for identifier, task in tuple(self._cycling_tasks.items()):
            current_spec = self._cycling_session_specs[identifier]
            if not task.done() and desired_specs.get(identifier) == current_spec:
                continue
            self._cycling_stop_events[identifier].set()
            task.cancel()
            stopping.append((identifier, task))
            stopped_roles.update(self._cycling_session_roles[identifier])

        if stopping:
            await asyncio.gather(
                *(task for _identifier, task in stopping),
                return_exceptions=True,
            )
            for identifier, task in stopping:
                if self._cycling_tasks.get(identifier) is not task:
                    continue
                self._cycling_tasks.pop(identifier)
                self._cycling_stop_events.pop(identifier)
                self._cycling_session_roles.pop(identifier)
                self._cycling_session_specs.pop(identifier)
            for role in stopped_roles:
                self._cycling_processors[role].set_suspended()
            self._publish_cycling_values()

        if revision != self._cycling_reconcile_revision:
            return

        for identifier, spec in desired_specs.items():
            if self._is_cycling_session_running(identifier):
                continue
            self._start_cycling_session(identifier, spec)

    def _start_cycling_session(
        self,
        identifier: str,
        spec: _CyclingSessionSpec,
    ) -> None:
        roles = spec.roles
        stop_event = asyncio.Event()
        session = BleCyclingSession(
            identifier,
            transport=self.transport,
            heart_rate_processor=(
                self._hrs_heart_rate_processor if "HR" in roles else None
            ),
            speed_processor=(self._csc_speed_processor if "SPD" in roles else None),
            cadence_processor=(self._csc_cadence_processor if "CDC" in roles else None),
            power_processor=(self._cps_power_processor if "PWR" in roles else None),
            cadence_profile=spec.cadence_profile,
            adapter=spec.adapter,
            initial_device=self._cycling_discovered_devices.pop(identifier, None),
            name=self._configured_cycling_name(roles),
            on_name=lambda name, sensor_id=identifier: self._set_cycling_sensor_name(
                sensor_id, name
            ),
            on_cadence_profile=lambda profile, sensor_id=identifier: (
                self._record_cadence_profile(sensor_id, profile)
            ),
            should_accumulate=lambda: self.config.G_STOPWATCH_STATUS == "START",
            log=lambda message: app_logger.info(f"[BLE-CYCLING] {message}"),
            debug_log=lambda message: app_logger.debug(f"[BLE-CYCLING] {message}"),
        )
        self._cycling_stop_events[identifier] = stop_event
        self._cycling_session_roles[identifier] = roles
        self._cycling_session_specs[identifier] = spec
        self._cycling_tasks[identifier] = asyncio.create_task(session.run(stop_event))

    def _cycling_adapter_available(self, adapter):
        return (
            self.transport.remote
            or not sys.platform.startswith("linux")
            or adapter is not None
        )

    def _configured_cadence_profile(
        self,
        identifier: str,
        roles: list[str],
    ) -> str | None:
        if "CDC" not in roles:
            return None
        profile = self.config.G_SENSORS["CDC"]["TYPE"]
        if profile in (PROFILE_CSCS, PROFILE_CPS):
            return profile
        if "PWR" in roles and "SPD" not in roles:
            return PROFILE_CPS
        if "SPD" in roles and "PWR" not in roles:
            return PROFILE_CSCS
        return None

    def disconnect_cycling_sensors(self) -> None:
        self._schedule_cycling_reconcile({})
        for processor in self._cycling_processors.values():
            if processor is not None:
                processor.set_suspended()
        self._publish_cycling_values()

    def _is_cycling_session_running(self, identifier: str) -> bool:
        if identifier not in self._cycling_tasks:
            return False
        stop_event = self._cycling_stop_events[identifier]
        task = self._cycling_tasks[identifier]
        return not stop_event.is_set() and not task.done()

    def is_cycling_sensor_running(self, role: str | None = None) -> bool:
        for identifier, roles in self._cycling_session_roles.items():
            if role is not None and role not in roles:
                continue
            if self._is_cycling_session_running(identifier):
                return True
        return False

    def _configured_cycling_name(self, roles: list[str]) -> str:
        for role in roles:
            name = self.config.G_SENSORS[role]["NAME"]
            if name:
                return name
        return ""

    def _resolve_sensor_adapter(self) -> str | None:
        if self.transport.remote or not sys.platform.startswith("linux"):
            return None
        errors = []
        resolver = BleAdapterResolver()
        for configured_policy in self.config.get_ble_sensor_adapter_policies():
            try:
                policy = BleAdapterPolicy(configured_policy)
                adapter = resolver.resolve(policy)
                app_logger.debug(f"[BLE-SENSOR] using BlueZ adapter {adapter}")
                return adapter
            except (ValueError, BleAdapterResolutionError) as exc:
                errors.append(str(exc))
        if errors:
            app_logger.warning(
                f"[BLE-SENSOR] adapter resolution failed: {'; '.join(errors)}"
            )
        return None

    def _set_cycling_sensor_name(self, identifier: str, name: str | None) -> None:
        name = str(name or "").strip()
        if not name:
            return
        for role in self.CYCLING_ROLES:
            sensor = self.config.G_SENSORS[role]
            if (
                self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE)
                and sensor["ID"] == identifier
            ):
                sensor["NAME"] = name

    def _record_cadence_profile(self, identifier: str, profile: str) -> None:
        profiles = self._cycling_cadence_profiles.setdefault(identifier, set())
        profiles.add(profile)

    def connect_light(self) -> bool:
        if not self.is_sensor_available(self.LIGHT_ROLE):
            self.disconnect_light()
            return False
        adapter = self._resolve_sensor_adapter()
        if not self._cycling_adapter_available(adapter):
            self.disconnect_light()
            return False

        previous_task = self._light_task
        if previous_task is not None and not previous_task.done():
            self._light_stop_event.set()
            previous_task.cancel()

        sensor = self.config.G_SENSORS[self.LIGHT_ROLE]
        identifier = sensor["ID"]
        stop_event = asyncio.Event()
        session = BontragerLightSession(
            identifier,
            adapter=adapter,
            initial_device=self._light_discovered_devices.pop(identifier, None),
            name=sensor["NAME"],
            on_name=self._set_light_name,
            on_status=self._set_light_connection_status,
            on_mode=self._set_light_actual_mode,
            on_battery=self._set_light_battery,
            on_command_status=self._set_light_command_status,
            health=self._light_health,
            log=lambda message: app_logger.info(f"[BLE-LIGHT] {message}"),
            debug_log=lambda message: app_logger.debug(f"[BLE-LIGHT] {message}"),
            transport=self.transport,
        )
        if self._light_control.desired_mode is not None:
            session.request_mode(self._light_control.desired_mode)
        self._light_stop_event = stop_event
        self._light_session = session

        async def run_after_previous() -> None:
            if previous_task is not None:
                await asyncio.gather(previous_task, return_exceptions=True)
            await session.run(stop_event)

        self._light_task = asyncio.create_task(run_after_previous())
        return True

    def disconnect_light(self) -> None:
        if self._light_stop_event is not None:
            self._light_stop_event.set()
        if self._light_task is not None and not self._light_task.done():
            self._light_task.cancel()
        self._light_session = None
        self._set_light_connection_status("inactive")

    def set_light_mode(self, mode: str, auto: bool = False) -> None:
        if not self.is_sensor_available(self.LIGHT_ROLE):
            return
        changed = self._light_control.request_mode(
            mode,
            auto=auto,
            auto_enabled=self.config.G_AUTO_LIGHT,
        )
        self._apply_light_control(changed)

    def set_auto_light_enabled(self, enabled: bool) -> None:
        if not self.is_sensor_available(self.LIGHT_ROLE):
            return
        changed = self._light_control.set_state(
            "AUTO" if enabled else "OFF",
            auto_enabled=enabled,
        )
        self._apply_light_control(changed)

    def _apply_light_control(self, changed: bool) -> None:
        self.values[self.LIGHT_ROLE]["light_state"] = self._light_control.state
        self.values[self.LIGHT_ROLE]["light_mode"] = self._light_control.desired_mode
        if changed and self._light_session is not None:
            self._light_session.request_mode(self._light_control.desired_mode)

    def _set_light_name(self, name: str | None) -> None:
        name = str(name or "").strip()
        if name:
            self.config.G_SENSORS[self.LIGHT_ROLE]["NAME"] = name

    def _set_light_connection_status(self, status: str) -> None:
        self.values[self.LIGHT_ROLE]["status"] = status

    def _set_light_actual_mode(self, mode: str | None) -> None:
        self.values[self.LIGHT_ROLE]["actual_light_mode"] = mode

    def _set_light_battery(self, battery: int | None) -> None:
        self.values[self.LIGHT_ROLE]["battery_percentage"] = battery

    def _set_light_command_status(self, status: str) -> None:
        self.values[self.LIGHT_ROLE]["command_status"] = status

    def connect_zwift_click_v2(self) -> bool:
        return self.click.connect()

    def disconnect_zwift_click_v2(self) -> None:
        self.click.disconnect()

    def paused_zwift_click_v2(self):
        return self.click.paused()

    def is_zwift_click_v2_running(self) -> bool:
        return self.click.is_running()
