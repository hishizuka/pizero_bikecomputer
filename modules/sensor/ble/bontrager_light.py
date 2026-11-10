from __future__ import annotations

import asyncio
import time
from typing import Callable

from .discovery import discover_ble_devices
from .health import BleSessionHealth
from .identity import format_ble_identity
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

BONTRAGER_LIGHT_TYPE = "BONTRAGER_FLARE_RT"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
MODE_SERVICE_UUID = "71261000-3692-ae93-e711-472ba41689c9"
MODE_CHAR_UUID = "71261001-3692-ae93-e711-472ba41689c9"
MODE_VALUES = {
    "OFF": 0x00,
    "STEADY_HIGH": 0x01,
    "STEADY_MID": 0x05,
    "FLASH_HIGH": 0x07,
    "FLASH_MID": 0x08,
    "FLASH_LOW": 0x3F,
}
MODE_NAMES = {value: name for name, value in MODE_VALUES.items()}
SUPPORTED_NAMES = ("flare rt", "ion 200 rt")
MAX_RECONNECT_DELAY = 30.0


def _matches_bontrager_light(device, advertisement) -> bool:
    names = (device.name, advertisement.local_name)
    if any(
        supported in str(name or "").casefold()
        for name in names
        for supported in SUPPORTED_NAMES
    ):
        return True
    return MODE_SERVICE_UUID in {
        str(uuid).lower() for uuid in advertisement.service_uuids
    }


async def discover_bontrager_lights(
    timeout: float = 10.0,
    *,
    adapter: str | None = None,
    discoverer=None,
) -> list[tuple[object, BleSensorCandidate]]:
    discovered = await (discoverer or discover_ble_devices)(
        adapter=adapter,
        timeout=timeout,
        predicate=_matches_bontrager_light,
    )
    candidates = []
    for device, advertisement in discovered:
        candidates.append(
            (
                device,
                BleSensorCandidate(
                    identifier=str(device.address),
                    name=device.name or advertisement.local_name,
                    rssi=advertisement.rssi,
                    profiles=(BONTRAGER_LIGHT_TYPE,),
                ),
            )
        )
    candidates.sort(key=lambda item: item[1].identifier)
    return candidates


class BontragerLightSession:
    """Keep a Bontrager light connected and serialize GATT mode writes."""

    def __init__(
        self,
        identifier: str,
        *,
        adapter: str | None = None,
        initial_device: object | None = None,
        name: str | None = None,
        on_name: Callable[[str | None], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_mode: Callable[[str | None], None] | None = None,
        on_battery: Callable[[int | None], None] | None = None,
        on_command_status: Callable[[str], None] | None = None,
        scan_timeout: float = 10.0,
        reconnect_delay: float = 2.0,
        max_reconnect_delay: float = MAX_RECONNECT_DELAY,
        health: BleSessionHealth | None = None,
        log: Callable[[str], None] | None = None,
        debug_log: Callable[[str], None] | None = None,
        transport: BleTransportProtocol,
    ):
        if not identifier.strip():
            raise ValueError("identifier must not be empty")
        self.identifier = identifier.strip()
        self.adapter = adapter
        self._initial_device = initial_device
        self.name = str(name or "").strip() or None
        self.on_name = on_name or (lambda _name: None)
        self.on_status = on_status or (lambda _status: None)
        self.on_mode = on_mode or (lambda _mode: None)
        self.on_battery = on_battery or (lambda _battery: None)
        self.on_command_status = on_command_status or (lambda _status: None)
        self.scan_timeout = scan_timeout
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.health = health or BleSessionHealth()
        self.log = log or (lambda _message: None)
        self.debug_log = debug_log or (lambda _message: None)
        self.transport = transport
        self._command_event = asyncio.Event()
        self._requested_mode: str | None = None

    def request_mode(self, mode: str) -> None:
        if mode not in MODE_VALUES:
            raise ValueError(f"Unsupported Bontrager light mode: {mode}")
        self._requested_mode = mode
        self.on_command_status("pending")
        self._command_event.set()

    async def run(self, stop_event: asyncio.Event) -> None:
        retry_delay = self.reconnect_delay
        try:
            while not stop_event.is_set():
                self.on_status("connecting")
                self.health.record_connect_attempt()
                stage = "scan"
                try:
                    device = await self._next_device()
                    if device is None:
                        self.log("configured light was not found")
                    else:
                        stage = "connection"
                        await self._connect_once(device, stop_event)
                        retry_delay = self.reconnect_delay
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.health.record_connect_failure()
                    self.on_status("disconnected")
                    self.on_command_status("failed")
                    self.log(f"{stage} failed: {format_ble_error(exc)}")
                if not stop_event.is_set():
                    await self._wait_retry(stop_event, retry_delay)
                    retry_delay = min(retry_delay * 2, self.max_reconnect_delay)
        finally:
            self.on_status("inactive")

    async def _next_device(self):
        if self._initial_device is not None:
            device = self._initial_device
            self._initial_device = None
            return device
        return await self.transport.find_device(
            self.identifier,
            timeout=self.scan_timeout,
            adapter=self.adapter,
        )

    async def _connect_once(self, device, stop_event: asyncio.Event) -> None:
        link = BleGattLink(
            self.transport,
            device,
            adapter=self.adapter,
            on_unexpected_disconnect=self.health.record_unexpected_disconnect,
        )
        client = link.client
        try:
            connected_started_at = time.monotonic()
            await link.connect()
            self.debug_log(
                f"GATT connected after {time.monotonic() - connected_started_at:.3f}s"
            )
            device_name = str(device.name or "").strip()
            if device_name:
                self.name = device_name
                self.on_name(device_name)

            setup_deadline = BleSetupDeadline(GATT_SETUP_TIMEOUT)
            mode_value = await setup_deadline.wait(
                client.read_gatt_char(MODE_CHAR_UUID)
            )
            self.on_mode(self._decode_mode(mode_value))
            try:
                async with asyncio.timeout(3.0):
                    battery_value = await client.read_gatt_char(BATTERY_LEVEL_UUID)
                self.on_battery(self._decode_battery(battery_value))
            except Exception as exc:
                self.debug_log(f"battery read failed: {format_ble_error(exc)}")

            self.health.record_connected()
            self.on_status("connected")
            self.log(f"connected to {format_ble_identity(self.name, self.identifier)}")
            await link.mark_ready()

            while not stop_event.is_set() and not link.disconnected.is_set():
                if self._command_event.is_set():
                    await self._write_requested_mode(client)
                    continue
                await wait_for_any_event(
                    stop_event,
                    link.disconnected,
                    self._command_event,
                )
            if link.disconnected.is_set() and not stop_event.is_set():
                self.on_status("disconnected")
        finally:
            await link.close()

    async def _write_requested_mode(self, client) -> None:
        self._command_event.clear()
        mode = self._requested_mode
        if mode is None:
            return
        await client.write_gatt_char(
            MODE_CHAR_UUID,
            bytes((MODE_VALUES[mode],)),
            response=True,
        )
        self.on_mode(mode)
        self.on_command_status("success")

    @staticmethod
    def _decode_mode(payload) -> str | None:
        if len(payload) != 1:
            raise ValueError(f"Unexpected light mode length: {len(payload)}")
        return MODE_NAMES.get(payload[0])

    @staticmethod
    def _decode_battery(payload) -> int | None:
        if len(payload) != 1:
            raise ValueError(f"Unexpected battery level length: {len(payload)}")
        return payload[0] if payload[0] <= 100 else None

    @staticmethod
    async def _wait_retry(stop_event: asyncio.Event, delay: float) -> None:
        await wait_for_stop(stop_event, delay)
