import asyncio
import os
import struct
import sys
from pathlib import Path

from modules.app_logger import app_logger
from modules.button_config import ButtonPress

from .bridge_core import Bridge

G_BUTTON_PROFILE = "CardputerZero_Keyboard"

# struct input_event on 64-bit Linux: timeval, type, code, value.
_INPUT_EVENT = struct.Struct("llHHi")
_EV_SYN = 0x00
_EV_KEY = 0x01
_EV_MSC = 0x04
_SYN_REPORT = 0
_SYN_DROPPED = 3
_MSC_SCAN = 0x04
_KEY_UP = 0
_KEY_DOWN = 1
_EVIOCGRAB = 0x40044590

# tca8418c reports each key's matrix position (row << 4 | col) as MSC_SCAN
# before EV_KEY. The position does not change with the Fn layer. The Sym layer
# maps F/Z/X/C to KEY_RESERVED, so the kernel sends no EV_KEY for them there.
G_SCAN_CODE_KEYS = {
    0x40: "ESC",
    0x44: "1",
    0x00: "2",
    0x01: "3",
    0x02: "4",
    0x03: "5",
    0x04: "6",
    0x05: "7",
    0x06: "8",
    0x07: "9",
    0x08: "0",
    0x09: "BACKSPACE",
    0x23: "F",
    0x29: "ENTER",
    0x32: "Z",
    0x33: "X",
    0x34: "C",
    0x39: "SPACE",
}


def _set_grab(fd, grab):
    # fcntl is Linux only; the keyboard is never opened elsewhere.
    import fcntl

    fcntl.ioctl(fd, _EVIOCGRAB, int(grab))


class CardputerZeroBridge(Bridge):
    """Handle CardputerZero-specific hardware and input."""

    backlight_path = Path("/sys/class/backlight/backlight")

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.device_path = config.board_preset.keyboard_device
        self.has_backlight = False
        self.backlight_max_brightness = 0
        self._backlight_task = None
        self._backlight_value = None
        if config.G_DISPLAY_PARAM["USE_BACKLIGHT"]:
            try:
                self.backlight_max_brightness = int(
                    (self.backlight_path / "max_brightness").read_text().strip()
                )
            except (OSError, ValueError):
                pass
            self.has_backlight = self.backlight_max_brightness > 0 and os.access(
                self.backlight_path / "brightness", os.W_OK
            )
            if not self.has_backlight:
                app_logger.warning("CardputerZero backlight is unavailable")
        self._fd = None
        self._reader_added = False
        self._scan_code = None
        self._dropped = False
        self._long_press_timers = {}
        if self.device_path is None or sys.platform != "linux":
            return

        try:
            self._fd = os.open(self.device_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as error:
            app_logger.warning("CardputerZero keyboard is unavailable: %s", error)
            return
        try:
            # Keep the launcher, the console and SysRq from seeing key presses.
            _set_grab(self._fd, True)
        except OSError as error:
            # Another reader holding the grab would receive every key instead.
            app_logger.warning("CardputerZero keyboard grab failed: %s", error)
            os.close(self._fd)
            self._fd = None

    @property
    def has_buttons(self) -> bool:
        return self._fd is not None

    def _start(self) -> None:
        if self._fd is None:
            return
        asyncio.get_running_loop().add_reader(self._fd, self._read_events)
        self._reader_added = True

    def set_backlight(self, brightness):
        if self._quit_task is not None or not self.has_backlight:
            return False
        value = round(
            max(0, min(100, brightness)) * self.backlight_max_brightness / 100
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Display initialization runs before the application event loop.
            return self._write_backlight(value)
        self._backlight_value = value
        if self._backlight_task is None or self._backlight_task.done():
            self._backlight_task = loop.create_task(self._update_backlight())
        return True

    def _write_backlight(self, value):
        try:
            (self.backlight_path / "brightness").write_text(f"{value}\n")
        except OSError as error:
            app_logger.warning("Failed to set CardputerZero backlight: %s", error)
            return False
        return True

    async def _update_backlight(self):
        # Serialize writes and retain only the latest requested brightness.
        while self._backlight_value is not None:
            value, self._backlight_value = self._backlight_value, None
            await asyncio.to_thread(self._write_backlight, value)

    def _read_events(self):
        try:
            data = os.read(self._fd, _INPUT_EVENT.size * 64)
        except BlockingIOError:
            return
        except OSError as error:
            app_logger.warning("CardputerZero keyboard read failed: %s", error)
            self._close()
            return
        if not data:
            app_logger.warning("CardputerZero keyboard reached EOF")
            self._close()
            return
        for _, _, event_type, code, value in _INPUT_EVENT.iter_unpack(data):
            if event_type == _EV_SYN:
                if code == _SYN_DROPPED:
                    # Lost events may include releases; drop presses in progress
                    # and skip the partial report.
                    self._cancel_presses()
                    self._dropped = True
                elif code == _SYN_REPORT:
                    self._dropped = False
            elif self._dropped:
                continue
            elif event_type == _EV_MSC and code == _MSC_SCAN:
                self._scan_code = value
            elif event_type == _EV_KEY:
                self._handle_key(self._scan_code, value)
                self._scan_code = None

    def _handle_key(self, scan_code, value):
        button = G_SCAN_CODE_KEYS.get(scan_code)
        if button is None:
            return
        if value == _KEY_DOWN:
            if button in self._long_press_timers:
                return
            self._long_press_timers[button] = asyncio.get_running_loop().call_later(
                self.config.button_config.button_long_press,
                self._press_long,
                button,
            )
        elif value == _KEY_UP:
            timer = self._long_press_timers.pop(button, None)
            if timer is None:
                return
            # A pending timer means the long press has not fired yet.
            if not timer.cancelled():
                timer.cancel()
                self._press_button(button, ButtonPress.SHORT)

    def _press_long(self, button):
        # Keep the cancelled handle until key up so the release is ignored.
        self._long_press_timers[button].cancel()
        self._press_button(button, ButtonPress.LONG)

    def _press_button(self, button, index):
        self.config.button_config.press_button(G_BUTTON_PROFILE, button, index)

    def _cancel_presses(self):
        for timer in self._long_press_timers.values():
            timer.cancel()
        self._long_press_timers.clear()
        self._scan_code = None

    def _close(self):
        self._cancel_presses()
        if self._fd is None:
            return
        if self._reader_added:
            asyncio.get_running_loop().remove_reader(self._fd)
            self._reader_added = False
        try:
            _set_grab(self._fd, False)
        except OSError:
            pass
        os.close(self._fd)
        self._fd = None

    async def _quit(self) -> None:
        self._close()
        if self._backlight_task is not None:
            await self._backlight_task
