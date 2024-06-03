from digitalio import Direction, Pull
import time
from threading import Thread
from logger import app_logger


try:
    # run from top directory (pizero_bikecomputer)
    from .. import i2c
except:
    # directly run this program
    import modules.sensor.i2c.i2c


class ButtonIOExpander(i2c.i2c):

    # The amount of available channels (8 for MCP23009)
    CHANNELS = 8

    # A button press counts as long press after this amount of milliseconds
    LONG_PRESS_DURATION_MS = 1000

    # After the button is pressed, it is disabled for this amount of milliseconds to prevent bouncing
    DEBOUNCE_DURATION_MS = 80

    # Button reads per second. Should be at least 20 for precise results
    FPS = 30

    _thread = None

    def __init__(self, config, mcp):
        # reset=False because the adafruit_mcp230xx library is resetting.
        super().__init__(reset=False)

        self.config = config
        self.mcp = mcp

        self._ms_per_frame = 1000 / self.FPS

        # How many frames it takes to reach the LONG_PRESS_DURATION_MS
        self._long_press_frames = int(self.LONG_PRESS_DURATION_MS // self._ms_per_frame)

        # How many frames a button is disabled after release
        self._debounce_frames = int(self.DEBOUNCE_DURATION_MS // self._ms_per_frame)

        # The amount of frames a button is held
        self._counter = [0] * self.CHANNELS
        # Previous button state
        self._previous = [0] * self.CHANNELS
        # Saves the lock state of a Button
        # NOTE: A button is getting locked to debounce or after long press to prevent that the short and long press event gets triggered simultaneously.
        self._locked = [False] * self.CHANNELS

        self.pins = []
        for i in range(self.CHANNELS):
            pin = self.mcp.get_pin(i)
            pin.direction = Direction.INPUT
            pin.pull = Pull.UP
            self.pins.append(pin)

        self._start_thread()

    def _start_thread(self):
        self._thread = Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()

    def _run(self):
        sleep_time = 1.0 / self.FPS

        while True:
            try:
                self.read()
            except:
                app_logger.error(
                    f"I/O Expander connection issue! Resetting all buttons..."
                )
                # if an I2C error occurs due to e.g. connection issues, reset all buttons
                for index in range(self.CHANNELS):
                    self._reset_button(index)
            time.sleep(sleep_time)

    def press_button(self, button, index):
        try:
            self.config.button_config.press_button("IOExpander", button, index)
        except:
            app_logger.warning(f"No button_config for button '{button}'")

    def get_pressed_buttons(self):
        return [not button.value for button in self.pins]

    def read(self):
        buttons_pressed = self.get_pressed_buttons()

        for i, pressed in enumerate(buttons_pressed):
            if pressed:
                if not self._locked[i]:
                    self._counter[i] += 1

                if self._counter[i] >= self._long_press_frames and not self._locked[i]:
                    self._on_button_pressed(i, True)
            else:
                if self._locked[i]:
                    if self._counter[i] <= self._debounce_frames:
                        self._counter[i] += 1
                        continue
                    else:
                        self._reset_button(i)
                elif not self._locked[i] and self._previous[i] != 0:
                    self._on_button_pressed(i, False)
        self._previous = buttons_pressed

    def _on_button_pressed(self, button_index, long_press):
        self._locked[button_index] = True
        self._counter[button_index] = 0
        self.press_button(f"GP{button_index}", int(long_press))

    def _reset_button(self, button_index):
        self._locked[button_index] = False
        self._counter[button_index] = 0
