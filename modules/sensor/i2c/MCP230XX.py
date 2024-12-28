import time
from threading import Thread

import board
import busio
from digitalio import Direction, Pull
from adafruit_mcp230xx.mcp23008 import MCP23008 as Adafruit_MCP23008
from adafruit_mcp230xx.mcp23017 import MCP23017 as Adafruit_MCP23017

from logger import app_logger

try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
except:
    # directly run this program
    import i2c


class ButtonIOExpander(i2c.i2c):

    # The amount of available channels (8 for MCP23009)
    CHANNELS = 8

    # After the button is pressed, it is disabled for this amount of milliseconds to prevent bouncing
    DEBOUNCE_DURATION_MS = 90

    # Button reads per second. Should be at least 20 for precise results
    FPS = 20

    _thread = None

    def __init__(self, config, mcp):
        # reset=False because the adafruit_mcp230xx library is resetting.
        super().__init__(reset=False)

        self.config = config
        self.mcp = mcp

        self._ms_per_frame = 1000 / self.FPS

        # How many frames it takes to reach the G_BUTTON_LONG_PRESS
        self._long_press_frames = int(
            (self.config.button_config.G_BUTTON_LONG_PRESS*1000)
            // self._ms_per_frame
        )

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
            #pass

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


# https://www.microchip.com/en-us/product/mcp23009
# https://ww1.microchip.com/downloads/en/DeviceDoc/20002121C.pdf

# NOTE: no need to set TEST and RESET address and value, due to adafruit_mcp230xx library handling it.
class MCP23008(ButtonIOExpander):
    # address
    SENSOR_ADDRESS = 0x20
    # The amount of available channels (8 for MCP23008)
    CHANNELS = 8

    def __init__(self, config):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.mcp = Adafruit_MCP23008(i2c, address=self.SENSOR_ADDRESS)
        super().__init__(config, self.mcp)


class MCP23009(MCP23008):
    # address
    SENSOR_ADDRESS = 0x27


class MCP23017(ButtonIOExpander):
    # address
    SENSOR_ADDRESS = 0x20

    def __init__(self, config):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.mcp = Adafruit_MCP23017(i2c, address=self.SENSOR_ADDRESS)
        super().__init__(config, self.mcp)


if __name__ == "__main__":
    
    class button_config:
        G_BUTTON_LONG_PRESS = 1
        def press_button(self, key, button, index):
            print(f"{key}, {button}, {index}")

    class config_local:
        button_config = None

    c = config_local()
    b = button_config()
    c.button_config = b

    #mcp = MCP23017(c)
    mcp = MCP23008(c)

    while True:
        time.sleep(1)
