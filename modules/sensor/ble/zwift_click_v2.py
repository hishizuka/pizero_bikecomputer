"""
Zwift Click V2 listener that mirrors the Flutter (Dart) implementation using `bleak`.

- Discovers Zwift Click V2 units via manufacturer data (0x094A, device types 0x0A/0x0B).
- Starts the controller session with the Click V2 RIDE_ON command.
- Subscribes to async (notify) and sync TX (indicate) characteristics and decodes button events.
- Prints which side triggered which buttons, one line per classified press (short/long).

This implementation is informed by and includes portions adapted from the
swiftcontrol project (GPL-3.0): https://github.com/jonasbark/swiftcontrol

Comments are in English as requested by the repository instructions.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import signal
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Protocol

if __package__:
    from modules.app_logger import app_logger

    from .health import BleSessionHealth
    from .identity import format_ble_identity
else:
    # Allow running this file directly for hardware diagnostics.
    from identity import format_ble_identity

try:
    from bleak import BleakClient
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData

    if __package__:
        from .discovery import discover_ble_devices, shutdown_ble_discovery
    else:
        from discovery import discover_ble_devices, shutdown_ble_discovery
except ImportError:
    BleakClient = None
    discover_ble_devices = None

ZWIFT_CLICK_AVAILABLE = BleakClient is not None and discover_ble_devices is not None

# UUIDs and constants sourced from lib/bluetooth/devices/zwift/constants.dart
ZWIFT_MANUFACTURER_ID = 0x094A  # 2378
ZWIFT_CLICK_V2_RIGHT = 0x0A
ZWIFT_CLICK_V2_LEFT = 0x0B

CUSTOM_SERVICE = "0000fc82-0000-1000-8000-00805f9b34fb"
ASYNC_CHAR = "00000002-19ca-4651-86e5-fa29dcdd09d1"
SYNC_RX_CHAR = "00000003-19ca-4651-86e5-fa29dcdd09d1"  # writes
SYNC_TX_CHAR = "00000004-19ca-4651-86e5-fa29dcdd09d1"  # indications

RIDE_ON = bytes([0x52, 0x69, 0x64, 0x65, 0x4F, 0x6E])
RESPONSE_START_CLICK_V2 = bytes([0x02, 0x03])
RESPONSE_STOPPED_CLICK_V2_VARIANT_1 = bytes([0xFF, 0x05, 0x00, 0xEA, 0x05])
RESPONSE_STOPPED_CLICK_V2_VARIANT_2 = bytes([0xFF, 0x05, 0x00, 0xFA, 0x05])
START_COMMAND = RIDE_ON + RESPONSE_START_CLICK_V2

MESSAGE_TYPE_RIDE_NOTIFICATION = 0x23  # RideKeyPadStatus
MESSAGE_TYPE_CLICK_NOTIFICATION = 0x37  # ClickKeyPadStatus
ANALOG_PADDLE_THRESHOLD = 25

# Button map uses active-low bits (0 == pressed), mirroring RideButtonMask in Dart.
BUTTON_MASKS: Dict[int, str] = {
    0x00001: "navigationLeft",
    0x00002: "navigationUp",
    0x00004: "navigationRight",
    0x00008: "navigationDown",
    0x00010: "a",
    0x00020: "b",
    0x00040: "y",
    0x00080: "z",
    0x00100: "shiftUpLeft",
    0x00200: "shiftDownLeft",
    0x00400: "powerUpLeft",
    0x00800: "onOffLeft",
    0x01000: "shiftUpRight",
    0x02000: "shiftDownRight",
    0x04000: "powerUpRight",
    0x08000: "onOffRight",
}

SHIFT_UP_LEFT = "shiftUpLeft"
SHIFT_UP_RIGHT = "shiftUpRight"
SHIFT_UP_BOTH = "shiftUpBoth"

DEFAULT_LONG_PRESS_SECONDS = 1.0
DEFAULT_RELEASE_TIMEOUT_SECONDS = 1.2
DEFAULT_REPEAT_INTERVAL_SECONDS = 0.5
DEFAULT_SCAN_TIMEOUT_SECONDS = 10.0
DEFAULT_SCAN_INTERVAL_SECONDS = 30.0
DEFAULT_RECONNECT_DELAY_SECONDS = 3.0
STOPPED_PACKET_WARNING = (
    "Zwift Click V2 may be locked. Connect it once in the Zwift app, " "then reconnect."
)


def _bluez_args(adapter: Optional[str]) -> dict:
    if not adapter:
        return {}
    return {"bluez": {"adapter": adapter}}


class BleHealthRecorder(Protocol):
    def record_connect_attempt(self) -> None: ...

    def record_connected(self, connected_at: float | None = None) -> None: ...

    def record_connect_failure(self) -> None: ...

    def record_notification(self, received_at: float | None = None) -> None: ...

    def record_unexpected_disconnect(
        self, disconnected_at: float | None = None
    ) -> None: ...


@dataclass
class ZwiftClickSide:
    device: BLEDevice
    side: str  # "left" or "right"


@dataclass
class _PressState:
    started_at: float
    last_seen_at: float
    repeat_interval_est: Optional[float] = None
    long_fired: bool = False
    long_eligible: bool = True


class PressDurationClassifier:
    """Coalesce repeated notifications and classify presses as short/long.

    - Short press: emitted on release.
    - Long press: emitted as soon as the duration reaches the threshold, then suppressed until release.
    """

    def __init__(
        self,
        long_press_seconds: float,
        release_timeout_seconds: float,
        default_repeat_interval_seconds: float,
        on_classified: Callable[[str, str, str, float], None],
    ) -> None:
        self._long_press_seconds = long_press_seconds
        self._release_timeout_seconds = release_timeout_seconds
        self._default_repeat_interval_seconds = default_repeat_interval_seconds
        self._on_classified = on_classified
        self._active: dict[tuple[str, str, str], _PressState] = {}
        self._latched_combos: dict[tuple[str, str], tuple[frozenset[str], str]] = {}

    def observe_pressed(
        self,
        side: str,
        source: str,
        buttons: Iterable[str],
        now: Optional[float] = None,
    ) -> None:
        now_mono = time.monotonic() if now is None else now
        for button in _dedupe(buttons):
            key = (side, source, button)
            state = self._active.get(key)
            if state is None:
                state = _PressState(started_at=now_mono, last_seen_at=now_mono)
                self._active[key] = state
                continue
            interval = now_mono - state.last_seen_at
            if interval > 0:
                if state.repeat_interval_est is None:
                    state.repeat_interval_est = interval
                else:
                    # EWMA to smooth jitter.
                    state.repeat_interval_est = (state.repeat_interval_est * 0.7) + (
                        interval * 0.3
                    )
            state.last_seen_at = now_mono

    def observe_released(
        self,
        side: str,
        source: str,
        buttons: Iterable[str],
        now: Optional[float] = None,
    ) -> None:
        now_mono = time.monotonic() if now is None else now
        for button in _dedupe(buttons):
            key = (side, source, button)
            state = self._active.pop(key, None)
            if state is None:
                continue
            self._emit_on_release(
                side, source, button, release_time=now_mono, state=state
            )

    def observe_snapshot(
        self,
        side: str,
        source: str,
        pressed_buttons: Iterable[str],
        now: Optional[float] = None,
    ) -> None:
        now_mono = time.monotonic() if now is None else now
        pressed = set(_dedupe(pressed_buttons))

        # Release buttons from the same (side, source) that are no longer pressed.
        for (s, src, button), state in list(self._active.items()):
            if s == side and src == source and button not in pressed:
                self._active.pop((s, src, button), None)
                self._emit_on_release(
                    s, src, button, release_time=now_mono, state=state
                )

        # Update currently pressed buttons.
        self.observe_pressed(side, source, pressed, now=now_mono)

    def observe_combo_snapshot(
        self,
        side: str,
        source: str,
        pressed_buttons: Iterable[str],
        member_buttons: Iterable[str],
        combo_button: str,
        now: Optional[float] = None,
    ) -> None:
        """Latch a combo until all member buttons have been released."""
        now_mono = time.monotonic() if now is None else now
        pressed = set(_dedupe(pressed_buttons))
        members = frozenset(_dedupe(member_buttons))
        latch_key = (side, source)
        latched = self._latched_combos.get(latch_key)

        if latched is None and members.issubset(pressed):
            self.suppress_buttons(side, source, members)
            latched = (members, combo_button)
            self._latched_combos[latch_key] = latched

        if latched is not None:
            latched_members, latched_button = latched
            pressed_members = pressed & latched_members
            self.suppress_buttons(side, source, latched_members)
            state = self._active.get((side, source, latched_button))
            if state is not None and pressed_members != latched_members:
                self._fire_long_press_if_due(
                    side,
                    latched_button,
                    state,
                    now_mono,
                )
                state.long_eligible = False
            pressed.difference_update(latched_members)
            if pressed_members:
                pressed.add(latched_button)
            else:
                self._latched_combos.pop(latch_key, None)

        self.observe_snapshot(side, source, pressed, now=now_mono)

    def suppress_buttons(self, side: str, source: str, buttons: Iterable[str]) -> None:
        """Remove active buttons without emitting a release classification."""
        for button in _dedupe(buttons):
            self._active.pop((side, source, button), None)

    def flush_long_presses(self, now: Optional[float] = None) -> None:
        now_mono = time.monotonic() if now is None else now
        for (side, _source, button), state in self._active.items():
            self._fire_long_press_if_due(side, button, state, now_mono)

    def _fire_long_press_if_due(
        self,
        side: str,
        button: str,
        state: _PressState,
        now: float,
    ) -> None:
        if state.long_fired or not state.long_eligible:
            return
        duration = now - state.started_at
        if duration >= self._long_press_seconds:
            state.long_fired = True
            self._on_classified(side, button, "long", duration)

    def flush_timeouts(self, now: Optional[float] = None) -> None:
        now_mono = time.monotonic() if now is None else now
        expired_keys: List[tuple[str, str, str]] = []
        for key, state in self._active.items():
            if (now_mono - state.last_seen_at) >= self._release_timeout_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            state = self._active.pop(key, None)
            if state is None:
                continue
            side, source, button = key
            latched = self._latched_combos.get((side, source))
            if latched is not None and button == latched[1]:
                self._latched_combos.pop((side, source), None)
            if state.long_fired:
                continue
            repeat = state.repeat_interval_est or self._default_repeat_interval_seconds
            # Approximate "release" near the next expected report to reduce under-estimation.
            release_time = min(now_mono, state.last_seen_at + repeat)
            self._emit_on_release(
                side, source, button, release_time=release_time, state=state
            )

    def _emit_on_release(
        self,
        side: str,
        source: str,
        button: str,
        release_time: float,
        state: _PressState,
    ) -> None:
        if state.long_fired:
            return
        duration = max(0.0, release_time - state.started_at)
        self._on_classified(side, button, "short", duration)


def _read_varint(buf: bytes, idx: int) -> tuple[int, int]:
    """Decode protobuf varint and return (value, next_index)."""
    shift = 0
    val = 0
    while True:
        if idx >= len(buf):
            raise ValueError("Unexpected end of buffer while reading varint")
        b = buf[idx]
        val |= (b & 0x7F) << shift
        idx += 1
        if not (b & 0x80):
            break
        shift += 7
    return val, idx


def _zigzag_decode(n: int) -> int:
    """Decode protobuf sint32 zigzag."""
    return (n >> 1) ^ -(n & 1)


def parse_ride_keypad_status(payload: bytes) -> List[str]:
    """
    Parse RideKeyPadStatus (field 1: buttonMap varint, field 3: repeated RideAnalogKeyPress).
    Returns list of pressed button names.
    """
    idx = 0
    button_map: Optional[int] = None
    analog_paddles: List[tuple[int, int]] = []

    while idx < len(payload):
        key, idx = _read_varint(payload, idx)
        field = key >> 3
        wire = key & 0x07

        if field == 1 and wire == 0:
            button_map, idx = _read_varint(payload, idx)
        elif field == 3 and wire == 2:
            length, idx = _read_varint(payload, idx)
            end = idx + length
            loc = None
            val = None
            sub_idx = idx
            # Parse RideAnalogKeyPress: field1 location (varint), field2 analogValue (sint32)
            while sub_idx < end:
                sub_key, sub_idx = _read_varint(payload, sub_idx)
                sub_field = sub_key >> 3
                sub_wire = sub_key & 0x07
                if sub_field == 1 and sub_wire == 0:
                    loc, sub_idx = _read_varint(payload, sub_idx)
                elif sub_field == 2 and sub_wire == 0:
                    raw, sub_idx = _read_varint(payload, sub_idx)
                    val = _zigzag_decode(raw)
                else:
                    # Skip unknown fields
                    if sub_wire == 0:
                        _, sub_idx = _read_varint(payload, sub_idx)
                    elif sub_wire == 2:
                        l, sub_idx = _read_varint(payload, sub_idx)
                        sub_idx += l
                    else:
                        raise ValueError(f"Unhandled wire type {sub_wire}")
            idx = end
            if loc is not None and val is not None:
                analog_paddles.append((loc, val))
        else:
            # Skip unknown fields
            if wire == 0:
                _, idx = _read_varint(payload, idx)
            elif wire == 2:
                l, idx = _read_varint(payload, idx)
                idx += l
            else:
                raise ValueError(f"Unhandled wire type {wire}")

    pressed: List[str] = []
    if button_map is not None:
        for mask, name in BUTTON_MASKS.items():
            # Active-low: bit cleared (==0) means pressed.
            if (button_map & mask) == 0:
                pressed.append(name)

    for loc, value in analog_paddles:
        if abs(value) >= ANALOG_PADDLE_THRESHOLD:
            if loc == 0:
                pressed.append("paddleLeft")
            elif loc == 1:
                pressed.append("paddleRight")
    return pressed


def parse_click_keypad_status(payload: bytes) -> tuple[List[str], List[str]]:
    """
    Parse ClickKeyPadStatus (fields 1/2 are enums: ON == 0, OFF == 1).
    Returns (pressed, released) lists.
    """
    idx = 0
    pressed: List[str] = []
    released: List[str] = []
    while idx < len(payload):
        key, idx = _read_varint(payload, idx)
        field = key >> 3
        wire = key & 0x07
        if wire != 0:
            # Skip non-varint fields
            if wire == 2:
                length, idx = _read_varint(payload, idx)
                idx += length
            elif wire == 1:
                idx += 8
            elif wire == 5:
                idx += 4
            else:
                break
            continue
        val, idx = _read_varint(payload, idx)
        target: Optional[List[str]] = None
        if val == 0:
            target = pressed
        elif val == 1:
            target = released
        else:
            continue
        if field == 1:
            target.append("plus")
        elif field == 2:
            target.append("minus")
    return pressed, released


def _format_packet_hex(packet: bytes) -> str:
    return " ".join(f"{b:02X}" for b in packet)


def _is_duplicate_debug_packet(packet: bytes, previous: Dict[int, bytes]) -> bool:
    if not packet or packet[0] not in (0x19, 0x23, 0x37):
        return False
    old_packet = previous.get(packet[0])
    previous[packet[0]] = packet
    return old_packet == packet


def _read_varint(data: bytes, index: int) -> tuple[Optional[int], int]:
    value = 0
    shift = 0
    while index < len(data):
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, index
        shift += 7
        if shift >= 64:
            break
    return None, index


def _extract_click_v2_vendor_status(data: bytes) -> Optional[int]:
    if not data.startswith(RESPONSE_STOPPED_CLICK_V2_VARIANT_1):
        return None

    payload = data[len(RESPONSE_STOPPED_CLICK_V2_VARIANT_1) :]
    if not payload:
        return None

    # The first byte is a protobuf payload length in observed packets.
    if payload[0] == len(payload) - 1:
        payload = payload[1:]

    index = 0
    while index < len(payload):
        tag, index = _read_varint(payload, index)
        if tag is None:
            return None
        field_number = tag >> 3
        wire_type = tag & 0x07

        if wire_type == 0:
            value, index = _read_varint(payload, index)
            if value is None:
                return None
            if field_number == 2:
                return value
        elif wire_type == 2:
            length, index = _read_varint(payload, index)
            if length is None:
                return None
            index += length
            if index > len(payload):
                return None
        else:
            return None

    return None


def _is_stopped_event_packet(data: bytes) -> bool:
    if data in (
        RESPONSE_STOPPED_CLICK_V2_VARIANT_1,
        RESPONSE_STOPPED_CLICK_V2_VARIANT_2,
    ):
        return True
    return _extract_click_v2_vendor_status(data) == 1


def _is_button_notification_packet(data: bytes) -> bool:
    return bool(data) and data[0] in (
        MESSAGE_TYPE_RIDE_NOTIFICATION,
        MESSAGE_TYPE_CLICK_NOTIFICATION,
    )


async def connect_and_listen(
    device: str | BLEDevice,
    side: str,
    classifier: PressDurationClassifier,
    stop_event: asyncio.Event,
    *,
    name: Optional[str] = None,
    log: Callable[[str], None] = print,
    debug_log: Optional[Callable[[str], None]] = None,
    on_connected: Optional[Callable[[str, str, Optional[str]], None]] = None,
    on_disconnected: Optional[Callable[[str, str], None]] = None,
    on_stopped: Optional[Callable[[str, bytes], None]] = None,
    on_vendor_status: Optional[Callable[[str, int, bytes], None]] = None,
    on_button_notification: Optional[Callable[[str, bytes], None]] = None,
    adapter: Optional[str] = None,
    health: Optional[BleHealthRecorder] = None,
) -> bool:
    """Connect to a single Click V2 and feed button events to callback."""
    connected = False
    address = device if isinstance(device, str) else device.address
    if health is not None:
        health.record_connect_attempt()
    try:
        async with BleakClient(device, **_bluez_args(adapter)) as client:
            connected = True
            if health is not None:
                health.record_connected()
            log(f"[{side}] connected to {format_ble_identity(name, address)}")
            last_rx_mono: Optional[float] = None
            stopped_notice_sent = False
            previous_debug_packets: Dict[int, bytes] = {}

            def mark_rx() -> None:
                nonlocal last_rx_mono
                last_rx_mono = time.monotonic()
                if health is not None:
                    health.record_notification(last_rx_mono)

            def handle_data(_sender, data: bytes) -> None:
                nonlocal stopped_notice_sent
                packet = bytes(data)
                if debug_log is not None and not _is_duplicate_debug_packet(
                    packet,
                    previous_debug_packets,
                ):
                    sender_uuid = getattr(_sender, "uuid", _sender)
                    debug_log(
                        f"[{side}] rx char={sender_uuid} len={len(packet)} "
                        f"packet={_format_packet_hex(packet)}"
                    )
                vendor_status = _extract_click_v2_vendor_status(packet)
                if vendor_status is not None and on_vendor_status is not None:
                    on_vendor_status(side, vendor_status, packet)
                stopped = handle_notification(
                    side,
                    packet,
                    classifier,
                    log=log,
                    on_rx=mark_rx,
                )
                if _is_button_notification_packet(packet):
                    if on_button_notification is not None:
                        on_button_notification(side, packet)
                if not stopped or stopped_notice_sent:
                    return
                stopped_notice_sent = True
                log(
                    f"[{side}] {STOPPED_PACKET_WARNING} "
                    f"packet={_format_packet_hex(packet)}"
                )
                if on_stopped is not None:
                    on_stopped(side, packet)

            if on_connected is not None:
                on_connected(side, address, name)
            await client.start_notify(ASYNC_CHAR, handle_data)
            await client.start_notify(SYNC_TX_CHAR, handle_data)

            # Send the Click V2 session-start command as one BLE write.
            await client.write_gatt_char(
                SYNC_RX_CHAR,
                START_COMMAND,
                response=False,
            )

            # Wait until disconnected or requested to stop.
            while client.is_connected and not stop_event.is_set():
                await asyncio.sleep(0.2)
            if not stop_event.is_set() and not client.is_connected:
                if health is not None:
                    health.record_unexpected_disconnect()
                if last_rx_mono is None:
                    log(f"[{side}] disconnected (no notifications received)")
                else:
                    since_last = time.monotonic() - last_rx_mono
                    log(
                        f"[{side}] disconnected (last notification {since_last:.1f}s ago)"
                    )
    except asyncio.CancelledError:
        if connected:
            stop_event.set()
        return connected
    except Exception as exc:  # noqa: BLE errors are runtime
        if health is not None:
            if connected:
                health.record_unexpected_disconnect()
            else:
                health.record_connect_failure()
        log(f"[{side}] error: {exc}")
    finally:
        if connected and on_disconnected is not None:
            on_disconnected(side, address)
    return connected


def handle_notification(
    side: str,
    data: bytes,
    classifier: PressDurationClassifier,
    *,
    log: Callable[[str], None] = print,
    on_rx: Optional[Callable[[], None]] = None,
) -> bool:
    """Process incoming data from SYNC_TX/ASYNC characteristics.

    Returns True when the packet indicates a Click V2 stopped/locked state.
    """
    if not data:
        return False
    if on_rx is not None:
        on_rx()

    # Ignore pure RIDE_ON packets that can appear during some stacks' handshake sequences.
    if data == RIDE_ON:
        return False

    if _is_stopped_event_packet(data):
        return True

    # Ignore the startup public-key packet (RideOn + response header).
    if data.startswith(START_COMMAND):
        return False

    opcode = data[0]
    payload = data[1:]

    if opcode == MESSAGE_TYPE_RIDE_NOTIFICATION:
        buttons = parse_ride_keypad_status(payload)
        classifier.observe_combo_snapshot(
            side,
            "ride",
            buttons,
            [SHIFT_UP_LEFT, SHIFT_UP_RIGHT],
            SHIFT_UP_BOTH,
        )
    elif opcode == MESSAGE_TYPE_CLICK_NOTIFICATION:
        pressed, released = parse_click_keypad_status(payload)
        if pressed:
            classifier.observe_pressed(side, "click", pressed)
        if released:
            classifier.observe_released(side, "click", released)
    elif opcode in (0x19, 0x42, 0x2A, 0xFF, 0x15, 0x3C):
        # Battery/log/empty/vendor noise; ignore for CLI output.
        return False
    else:
        # Unknown/unhandled packet; ignore to avoid noisy logs in app mode.
        return False
    return False


async def listen(
    *,
    on_classified: Callable[[str, str, str, float], None],
    stop_event: asyncio.Event,
    long_press_seconds: float = DEFAULT_LONG_PRESS_SECONDS,
    release_timeout_seconds: float = DEFAULT_RELEASE_TIMEOUT_SECONDS,
    repeat_interval_seconds: float = DEFAULT_REPEAT_INTERVAL_SECONDS,
    scan_timeout_seconds: float = DEFAULT_SCAN_TIMEOUT_SECONDS,
    scan_forever: bool = False,
    scan_interval_seconds: float = DEFAULT_SCAN_INTERVAL_SECONDS,
    reconnect_delay_seconds: float = DEFAULT_RECONNECT_DELAY_SECONDS,
    prefer_left: bool = True,
    preferred_address: Optional[str] = None,
    adapter: Optional[str] = None,
    health: Optional[BleHealthRecorder] = None,
    on_connected: Optional[Callable[[str, str, Optional[str]], None]] = None,
    on_disconnected: Optional[Callable[[str, str], None]] = None,
    on_stopped: Optional[Callable[[str, bytes], None]] = None,
    on_vendor_status: Optional[Callable[[str, int, bytes], None]] = None,
    on_button_notification: Optional[Callable[[str, bytes], None]] = None,
    log: Callable[[str], None] = print,
    debug_log: Optional[Callable[[str], None]] = None,
) -> None:
    """Scan, connect, and dispatch button presses (short/long) via callback.

    `scan_forever=False` matches the previous CLI behavior: scan once and exit if not found.
    `scan_forever=True` keeps scanning and reconnecting until `stop_event` is set.
    """
    classifier = PressDurationClassifier(
        long_press_seconds=long_press_seconds,
        release_timeout_seconds=release_timeout_seconds,
        default_repeat_interval_seconds=repeat_interval_seconds,
        on_classified=on_classified,
    )

    timeout_task = asyncio.create_task(_press_timeout_poller(classifier, stop_event))
    try:
        while not stop_event.is_set():
            try:
                devices = await scan_for_click_v2(
                    timeout=scan_timeout_seconds,
                    prefer_left=prefer_left,
                    preferred_address=preferred_address,
                    adapter=adapter,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BlueZ discovery errors are runtime
                log(f"scan failed: {exc}")
                if not scan_forever:
                    return
                await asyncio.sleep(reconnect_delay_seconds)
                continue

            preferred = [
                device
                for device in devices
                if preferred_address
                and device.device.address.casefold() == preferred_address.casefold()
            ]
            selected = (
                preferred
                if preferred_address
                else [d for d in devices if d.side == "left"]
            )
            if not selected:
                if not scan_forever:
                    log(
                        "Zwift Click V2 not found. Ensure the device is awake and advertising."
                    )
                    return
                await asyncio.sleep(scan_interval_seconds)
                continue

            tasks = [
                asyncio.create_task(
                    connect_and_listen(
                        d.device,
                        d.side,
                        classifier,
                        stop_event,
                        name=d.device.name,
                        log=log,
                        debug_log=debug_log,
                        on_connected=on_connected,
                        on_disconnected=on_disconnected,
                        on_stopped=on_stopped,
                        on_vendor_status=on_vendor_status,
                        on_button_notification=on_button_notification,
                        adapter=adapter,
                        health=health,
                    )
                )
                for d in selected
            ]
            stop_task = asyncio.create_task(stop_event.wait())

            try:
                done, _pending = await asyncio.wait(
                    tasks + [stop_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if stop_task in done:
                    return
            finally:
                for t in tasks:
                    t.cancel()
                stop_task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.gather(stop_task, return_exceptions=True)

            if not scan_forever:
                return

            await asyncio.sleep(reconnect_delay_seconds)
    finally:
        timeout_task.cancel()
        await asyncio.gather(timeout_task, return_exceptions=True)


async def scan_for_click_v2(
    timeout: float = 10.0,
    prefer_left: bool = True,
    preferred_address: Optional[str] = None,
    adapter: Optional[str] = None,
) -> List[ZwiftClickSide]:
    """Scan for Click V2 left/right units using manufacturer data."""

    def classify(ad: AdvertisementData) -> Optional[str]:
        md = ad.manufacturer_data.get(ZWIFT_MANUFACTURER_ID)
        if not md:
            return None
        dev_type = md[0]
        if dev_type == ZWIFT_CLICK_V2_LEFT:
            return "left"
        if dev_type == ZWIFT_CLICK_V2_RIGHT:
            return "right"
        return None

    def matches_click(_device: BLEDevice, adv: AdvertisementData) -> bool:
        return classify(adv) is not None

    def matches_preferred(device: BLEDevice, adv: AdvertisementData) -> bool:
        side = classify(adv)
        if preferred_address is not None:
            return device.address.casefold() == preferred_address.casefold()
        return prefer_left and side == "left"

    devices = await discover_ble_devices(
        adapter=adapter,
        timeout=timeout,
        predicate=matches_click,
        stop_when=matches_preferred if prefer_left or preferred_address else None,
    )
    found = []
    for device, advertisement in devices:
        side = classify(advertisement)
        if side is not None:
            found.append(ZwiftClickSide(device=device, side=side))
    return found


def _dedupe(seq: Iterable[str]) -> List[str]:
    """Preserve order while removing duplicates."""
    seen = set()
    out: List[str] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


async def _press_timeout_poller(
    classifier: PressDurationClassifier,
    stop_event: asyncio.Event,
    interval_seconds: float = 0.05,
) -> None:
    """Periodically flush timeouts so release can be detected even without an explicit packet."""
    try:
        while not stop_event.is_set():
            classifier.flush_long_presses()
            classifier.flush_timeouts()
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        return


class ZwiftClickV2Session:
    CONTROL_ROLE = "CTRL"
    CONTROL_BUTTON_PROFILE = "Zwift_Click_V2"
    CLICK_AUTH_UNKNOWN = "unknown"
    CLICK_AUTHENTICATED = "authenticated"
    CLICK_LOCKED = "locked"
    CLICK_INPUT_UNKNOWN = "unknown"
    CLICK_INPUT_WAITING = "waiting"
    CLICK_INPUT_OPERATIONAL = "operational"
    CLICK_INPUT_INACTIVE = "inactive"
    CLICK_RECOVERY_INPUT_TIMEOUT_SECONDS = 30.0

    def __init__(self, config, resolve_adapter):
        self.config = config
        self.resolve_adapter = resolve_adapter
        self.health = BleSessionHealth()
        self._reset_runtime()
        self.thread: Optional[threading.Thread] = None
        self.connection_status = "inactive"
        self.auth_status = self.CLICK_AUTH_UNKNOWN
        self.input_status = self.CLICK_INPUT_UNKNOWN
        self.recovery_pending = False
        self._recovery_timer: Optional[threading.Timer] = None

    def _reset_runtime(self) -> None:
        self._loop = None
        self._stop_event = None
        self._task = None
        self._stop_requested = threading.Event()

    def connect(self) -> bool:
        """Start Zwift Click V2 listener if it is enabled and available."""
        if not self.is_enabled():
            self.connection_status = self._control_idle_status()
            return False
        if self.is_running():
            return True
        thread = self.thread
        if thread is not None and thread.is_alive():
            return False

        self._reset_runtime()
        self.connection_status = "connecting"
        self.thread = threading.Thread(
            target=self._run_thread,
            name="zwift-click-v2",
            daemon=True,
        )
        self.thread.start()
        return True

    def disconnect(self) -> None:
        """Stop Zwift Click V2 listener if running."""
        self.connection_status = self._control_idle_status()
        self._stop_requested.set()
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def stop_listener() -> None:
            if self._stop_event is not None:
                self._stop_event.set()
            if self._task is not None:
                self._task.cancel()

        try:
            loop.call_soon_threadsafe(stop_listener)
        except RuntimeError:
            pass

    @asynccontextmanager
    async def paused(self):
        thread = self.thread
        running = thread is not None and thread.is_alive()
        restart = running and not self._stop_requested.is_set()
        if running:
            self.disconnect()
            await asyncio.to_thread(thread.join, 5)
            if thread.is_alive():
                raise TimeoutError("Zwift Click V2 listener did not stop")
        try:
            yield
        finally:
            if restart:
                self.connect()

    def is_enabled(self) -> bool:
        return bool(
            ZWIFT_CLICK_AVAILABLE
            and self.config.ble_sensor_enabled()
            and self.is_configured()
        )

    def is_configured(self) -> bool:
        return self.config.is_sensor_configured(
            self.CONTROL_ROLE,
            self.config.SENSOR_PROTOCOL_BLE,
        )

    def _control_idle_status(self) -> str:
        if self.config.sensor_uses(
            self.CONTROL_ROLE,
            self.config.SENSOR_PROTOCOL_BLE,
        ):
            return "disconnected"
        return "inactive"

    def join(self) -> None:
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run_listener())
        except Exception as exc:  # noqa: BLE errors are runtime
            app_logger.info(f"[ZwiftClickV2] listener crashed: {exc}")

    async def _run_listener(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._task = asyncio.current_task()
        if self._stop_requested.is_set():
            self._stop_event.set()
        preferred_address = str(self.config.G_SENSORS[self.CONTROL_ROLE]["ID"]).strip()

        def log(msg: str) -> None:
            app_logger.info(f"[ZwiftClickV2] {msg}")

        def debug_log(msg: str) -> None:
            app_logger.debug(f"[ZwiftClickV2] {msg}")

        adapter = None
        try:
            if sys.platform.startswith("linux"):
                adapter = self.resolve_adapter()
                if adapter is None:
                    return
                debug_log(f"using BlueZ adapter {adapter}")
            await listen(
                on_classified=self._on_classified,
                stop_event=self._stop_event,
                scan_forever=True,
                preferred_address=preferred_address,
                on_connected=self._on_connected,
                on_disconnected=self._on_disconnected,
                on_stopped=self._handle_stopped,
                on_vendor_status=self._handle_vendor_status,
                on_button_notification=self._handle_button_notification,
                log=log,
                debug_log=debug_log,
                adapter=adapter,
                health=self.health,
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE errors are runtime
            log(f"listener crashed: {exc}")
        finally:
            await shutdown_ble_discovery(adapter)
            self._task = None
            self._stop_event = None
            self._loop = None
            self.connection_status = self._control_idle_status()

    def _on_classified(
        self, _side: str, button: str, kind: str, _duration: float
    ) -> None:
        snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", button)
        button_key = re.sub(r"[^A-Za-z0-9]+", "_", snake).upper().strip("_")
        if button_key:
            self.config.loop.call_soon_threadsafe(
                self.config.button_config.press_button,
                self.CONTROL_BUTTON_PROFILE,
                button_key,
                1 if kind == "long" else 0,
            )

    def _on_connected(self, _side: str, address: str, name: Optional[str]) -> None:
        sensor = self.config.G_SENSORS[self.CONTROL_ROLE]
        if str(sensor["ID"]).casefold() != address.casefold():
            return
        sensor["NAME"] = str(name or "").strip()
        self.connection_status = "connected"
        self.auth_status = self.CLICK_AUTH_UNKNOWN
        self.input_status = self.CLICK_INPUT_WAITING
        self.start_recovery_timeout()

    def _on_disconnected(self, _side: str, _address: str) -> None:
        self.cancel_recovery_timeout()
        if self._stop_requested.is_set():
            return
        self.connection_status = "connecting"
        self.input_status = self.CLICK_INPUT_UNKNOWN

    def _handle_vendor_status(
        self,
        side: str,
        status: int,
        _packet: bytes,
    ) -> None:
        if status == 0:
            auth_status = self.CLICK_AUTHENTICATED
        elif status == 1:
            auth_status = self.CLICK_LOCKED
        else:
            return
        if auth_status == self.auth_status:
            return
        self.auth_status = auth_status
        app_logger.info(f"[ZwiftClickV2] [{side}] authentication status={auth_status}")

    def _handle_button_notification(
        self,
        side: str,
        _packet: bytes,
    ) -> None:
        first_notification = self.input_status != self.CLICK_INPUT_OPERATIONAL
        self.input_status = self.CLICK_INPUT_OPERATIONAL
        if first_notification:
            app_logger.info(f"[ZwiftClickV2] [{side}] input status=operational")
        if not self.recovery_pending:
            return
        self.cancel_recovery_timeout()
        self.recovery_pending = False
        self._notify_recovered()

    def _handle_stopped(
        self,
        _side: str,
        _packet: bytes,
    ) -> None:
        self.auth_status = self.CLICK_LOCKED
        self.input_status = self.CLICK_INPUT_INACTIVE
        recovery_failed = self.recovery_pending
        self.cancel_recovery_timeout()
        self.recovery_pending = False
        self._notify_stopped(recovery_failed=recovery_failed)

    def start_recovery_timeout(self) -> None:
        self.cancel_recovery_timeout()
        if not self.recovery_pending:
            return
        timer = threading.Timer(
            self.CLICK_RECOVERY_INPUT_TIMEOUT_SECONDS,
            self._handle_recovery_timeout,
        )
        timer.daemon = True
        self._recovery_timer = timer
        timer.start()

    def cancel_recovery_timeout(self) -> None:
        timer = self._recovery_timer
        self._recovery_timer = None
        if timer is not None:
            timer.cancel()

    def _handle_recovery_timeout(self) -> None:
        self._recovery_timer = None
        if not self.recovery_pending:
            return
        if self.input_status == self.CLICK_INPUT_OPERATIONAL:
            return
        self.recovery_pending = False
        self.input_status = self.CLICK_INPUT_INACTIVE
        app_logger.info("[ZwiftClickV2] recovery timed out waiting for button input")
        self._notify_no_input()

    def _notify_stopped(self, *, recovery_failed=False) -> None:
        self._show_dialog(
            (
                "Click V2 unlock failed. Retry with Fake Trainer?"
                if recovery_failed
                else "Click V2 is locked. Start Fake Trainer to unlock?"
            ),
            retry=True,
        )

    def _notify_recovered(self) -> None:
        self._show_dialog("Click V2 recovered. Button input is active.")

    def _notify_no_input(self) -> None:
        self._show_dialog(
            "No button input. Disconnect Click for 60 seconds, then retry?",
            retry=True,
        )

    def _show_dialog(self, title, retry=False) -> None:
        gui = self.config.gui
        if gui is None:
            return

        def show() -> None:
            if retry:
                gui.show_dialog(gui.toggle_fake_trainer, title)
            else:
                gui.show_dialog_ok_only(None, title)

        self.config.loop.call_soon_threadsafe(show)

    def is_running(self) -> bool:
        thread = self.thread
        return bool(
            thread is not None
            and thread.is_alive()
            and not self._stop_requested.is_set()
        )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Listen to Zwift Click V2 and classify short/long presses."
    )
    parser.add_argument(
        "--long-press-seconds",
        type=float,
        default=DEFAULT_LONG_PRESS_SECONDS,
        help="Seconds required to classify as a long press.",
    )
    parser.add_argument(
        "--release-timeout-seconds",
        type=float,
        default=DEFAULT_RELEASE_TIMEOUT_SECONDS,
        help="Seconds without pressed reports to treat the button as released.",
    )
    parser.add_argument(
        "--repeat-interval-seconds",
        type=float,
        default=DEFAULT_REPEAT_INTERVAL_SECONDS,
        help="Fallback repeat interval for duration estimation when release packet is missing.",
    )
    parser.add_argument(
        "--address",
        default="",
        help="BLE address to connect directly (skip scan).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress runtime output and print only a summary after stopping.",
    )
    args = parser.parse_args()

    stop_event = asyncio.Event()
    connection_count = 0
    button_event_count = 0

    def log(message: str) -> None:
        if not args.quiet:
            print(message)

    def on_connected(_side: str, _address: str, _name: Optional[str]) -> None:
        nonlocal connection_count
        connection_count += 1

    def on_classified(side: str, button: str, kind: str, duration: float) -> None:
        nonlocal button_event_count
        button_event_count += 1
        if not args.quiet:
            print(f"[{side}] {button} {kind} ({duration:.2f}s)")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # add_signal_handler may be unavailable on Windows
            pass
    await listen(
        on_classified=on_classified,
        stop_event=stop_event,
        long_press_seconds=args.long_press_seconds,
        release_timeout_seconds=args.release_timeout_seconds,
        repeat_interval_seconds=args.repeat_interval_seconds,
        scan_timeout_seconds=DEFAULT_SCAN_TIMEOUT_SECONDS,
        scan_forever=False,
        preferred_address=args.address or None,
        on_connected=on_connected,
        log=log,
    )
    if args.quiet:
        print(
            f"summary: connections={connection_count} "
            f"button_events={button_event_count}"
        )


if __name__ == "__main__":
    asyncio.run(main())
