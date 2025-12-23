"""
Zwift Click V2 listener that mirrors the Flutter (Dart) implementation using `bleak`.

- Discovers Zwift Click V2 units via manufacturer data (0x094A, device types 0x0A/0x0B).
- Performs the same handshake as the app: write RIDE_ON, then write FF 04 00.
- Subscribes to async (notify) and sync TX (indicate) characteristics and decodes button events.
- Prints which side triggered which buttons, one line per classified press (short/long).

This implementation is informed by and includes portions adapted from the
swiftcontrol project (GPL-3.0): https://github.com/jonasbark/swiftcontrol

Comments are in English as requested by the repository instructions.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# UUIDs and constants sourced from lib/bluetooth/devices/zwift/constants.dart
ZWIFT_MANUFACTURER_ID = 0x094A  # 2378
ZWIFT_CLICK_V2_RIGHT = 0x0A
ZWIFT_CLICK_V2_LEFT = 0x0B

CUSTOM_SERVICE = "0000fc82-0000-1000-8000-00805f9b34fb"
ASYNC_CHAR = "00000002-19ca-4651-86e5-fa29dcdd09d1"
SYNC_RX_CHAR = "00000003-19ca-4651-86e5-fa29dcdd09d1"  # writes
SYNC_TX_CHAR = "00000004-19ca-4651-86e5-fa29dcdd09d1"  # indications

RIDE_ON = bytes([0x52, 0x69, 0x64, 0x65, 0x4F, 0x6E])
HANDSHAKE_EXTRA = bytes([0xFF, 0x04, 0x00])
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

    def observe_pressed(self, side: str, source: str, buttons: Iterable[str], now: Optional[float] = None) -> None:
        now_mono = time.monotonic() if now is None else now
        for button in _dedupe(buttons):
            key = (side, source, button)
            state = self._active.get(key)
            if state is None:
                self._active[key] = _PressState(started_at=now_mono, last_seen_at=now_mono)
                continue
            interval = now_mono - state.last_seen_at
            if interval > 0:
                if state.repeat_interval_est is None:
                    state.repeat_interval_est = interval
                else:
                    # EWMA to smooth jitter.
                    state.repeat_interval_est = (state.repeat_interval_est * 0.7) + (interval * 0.3)
            state.last_seen_at = now_mono

    def observe_released(self, side: str, source: str, buttons: Iterable[str], now: Optional[float] = None) -> None:
        now_mono = time.monotonic() if now is None else now
        for button in _dedupe(buttons):
            key = (side, source, button)
            state = self._active.pop(key, None)
            if state is None:
                continue
            self._emit_on_release(side, source, button, release_time=now_mono, state=state)

    def observe_snapshot(self, side: str, source: str, pressed_buttons: Iterable[str], now: Optional[float] = None) -> None:
        now_mono = time.monotonic() if now is None else now
        pressed = set(_dedupe(pressed_buttons))

        # Release buttons from the same (side, source) that are no longer pressed.
        for (s, src, button), state in list(self._active.items()):
            if s == side and src == source and button not in pressed:
                self._active.pop((s, src, button), None)
                self._emit_on_release(s, src, button, release_time=now_mono, state=state)

        # Update currently pressed buttons.
        self.observe_pressed(side, source, pressed, now=now_mono)

    def suppress_buttons(self, side: str, source: str, buttons: Iterable[str]) -> None:
        """Remove active buttons without emitting a release classification."""
        for button in _dedupe(buttons):
            self._active.pop((side, source, button), None)

    def flush_long_presses(self, now: Optional[float] = None) -> None:
        now_mono = time.monotonic() if now is None else now
        for (side, source, button), state in self._active.items():
            if state.long_fired:
                continue
            duration = now_mono - state.started_at
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
            if state.long_fired:
                continue
            side, source, button = key
            repeat = state.repeat_interval_est or self._default_repeat_interval_seconds
            # Approximate "release" near the next expected report to reduce under-estimation.
            release_time = min(now_mono, state.last_seen_at + repeat)
            self._emit_on_release(side, source, button, release_time=release_time, state=state)

    def _emit_on_release(self, side: str, source: str, button: str, release_time: float, state: _PressState) -> None:
        if state.long_fired:
            return
        duration = max(0.0, release_time - state.started_at)
        kind = "long" if duration >= self._long_press_seconds else "short"
        self._on_classified(side, button, kind, duration)


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


def _apply_shift_up_combo(buttons: Iterable[str]) -> List[str]:
    """Add a synthetic combo button when both shift-up buttons are pressed."""
    pressed = _dedupe(buttons)
    if SHIFT_UP_LEFT in pressed and SHIFT_UP_RIGHT in pressed:
        pressed = [b for b in pressed if b not in (SHIFT_UP_LEFT, SHIFT_UP_RIGHT)]
        pressed.append(SHIFT_UP_BOTH)
    return pressed


async def connect_and_listen(
    address: str,
    side: str,
    classifier: PressDurationClassifier,
    stop_event: asyncio.Event,
    *,
    name: Optional[str] = None,
    log: Callable[[str], None] = print,
    on_connected: Optional[Callable[[str, str, Optional[str]], None]] = None,
) -> bool:
    """Connect to a single Click V2 and feed button events to callback."""
    connected = False
    try:
        async with BleakClient(address) as client:
            connected = True
            if on_connected is not None:
                on_connected(side, address, name)
            await client.start_notify(
                ASYNC_CHAR,
                lambda _, data: handle_notification(side, data, classifier, log=log),
            )
            await client.start_notify(
                SYNC_TX_CHAR,
                lambda _, data: handle_notification(side, data, classifier, log=log),
            )

            # Handshake sequence mirrors Dart: RIDE_ON then FF 04 00.
            await client.write_gatt_char(SYNC_RX_CHAR, RIDE_ON, response=False)
            await asyncio.sleep(0.1)
            await client.write_gatt_char(SYNC_RX_CHAR, HANDSHAKE_EXTRA, response=False)

            # Keep alive until disconnected or requested to stop.
            while client.is_connected and not stop_event.is_set():
                await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        if connected:
            stop_event.set()
        return connected
    except Exception as exc:  # noqa: BLE errors are runtime
        log(f"[{side}] error: {exc}")
    return connected


def handle_notification(
    side: str,
    data: bytes,
    classifier: PressDurationClassifier,
    *,
    log: Callable[[str], None] = print,
) -> None:
    """Process incoming data from SYNC_TX/ASYNC characteristics."""
    if not data:
        return

    # Ignore pure RIDE_ON packets that can appear during some stacks' handshake sequences.
    if data == RIDE_ON:
        return

    if data.startswith(RESPONSE_STOPPED_CLICK_V2_VARIANT_1) or data.startswith(RESPONSE_STOPPED_CLICK_V2_VARIANT_2):
        #log(f"[{side}] Device stopped sending events; open Zwift app once this session to re-enable.")
        return

    # Ignore the startup public-key packet (RideOn + response header).
    if data.startswith(START_COMMAND):
        return

    opcode = data[0]
    payload = data[1:]

    if opcode == MESSAGE_TYPE_RIDE_NOTIFICATION:
        buttons = parse_ride_keypad_status(payload)
        if SHIFT_UP_LEFT in buttons and SHIFT_UP_RIGHT in buttons:
            # Suppress single-button releases when the combo is active.
            classifier.suppress_buttons(side, "ride", [SHIFT_UP_LEFT, SHIFT_UP_RIGHT])
        buttons = _apply_shift_up_combo(buttons)
        classifier.observe_snapshot(side, "ride", buttons)
    elif opcode == MESSAGE_TYPE_CLICK_NOTIFICATION:
        pressed, released = parse_click_keypad_status(payload)
        if pressed:
            classifier.observe_pressed(side, "click", pressed)
        if released:
            classifier.observe_released(side, "click", released)
    elif opcode in (0x19, 0x42, 0x2A, 0xFF, 0x15, 0x3C):
        # Battery/log/empty/vendor noise; ignore for CLI output.
        return
    else:
        # Unknown/unhandled packet; ignore to avoid noisy logs in app mode.
        return


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
    on_connected: Optional[Callable[[str, str, Optional[str]], None]] = None,
    log: Callable[[str], None] = print,
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
            if preferred_address:
                connected = await connect_and_listen(
                    preferred_address,
                    "left",
                    classifier,
                    stop_event,
                    name=None,
                    log=log,
                    on_connected=on_connected,
                )
                if stop_event.is_set():
                    return
                if connected:
                    if not scan_forever:
                        return
                    await asyncio.sleep(reconnect_delay_seconds)
                    continue
                preferred_address = None
            devices = await scan_for_click_v2(
                timeout=scan_timeout_seconds,
                prefer_left=prefer_left,
            )
            selected = [d for d in devices if d.side == "left"]
            if not selected:
                if not scan_forever:
                    log("Zwift Click V2 not found. Ensure the device is awake and advertising.")
                    return
                await asyncio.sleep(scan_interval_seconds)
                continue

            log("Connecting to:")
            for d in selected:
                label = d.device.name or d.device.address
                log(f"  - {label} ({d.device.address})")

            tasks = [
                asyncio.create_task(
                    connect_and_listen(
                        d.device.address,
                        d.side,
                        classifier,
                        stop_event,
                        name=d.device.name,
                        log=log,
                        on_connected=on_connected,
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
) -> List[ZwiftClickSide]:
    """Scan for Click V2 left/right units using manufacturer data."""
    found: dict[str, ZwiftClickSide] = {}
    found_preferred = asyncio.Event()

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

    def detection_callback(device: BLEDevice, adv: AdvertisementData) -> None:
        side = classify(adv)
        if side:
            found[device.address] = ZwiftClickSide(device=device, side=side)
            if prefer_left and side == "left":
                # Stop scanning early when the preferred side is found.
                found_preferred.set()

    async with BleakScanner(detection_callback=detection_callback) as _:
        if prefer_left:
            try:
                await asyncio.wait_for(found_preferred.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(timeout)

    return list(found.values())


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


async def main() -> None:
    parser = argparse.ArgumentParser(description="Listen to Zwift Click V2 and classify short/long presses.")
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
    args = parser.parse_args()

    stop_event = asyncio.Event()

    def on_classified(side: str, button: str, kind: str, duration: float) -> None:
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
        log=print,
    )


if __name__ == "__main__":
    asyncio.run(main())
