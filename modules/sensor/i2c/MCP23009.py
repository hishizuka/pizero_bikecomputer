import time
from threading import Thread
from logger import app_logger


try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
except:
    # directly run this program
    import i2c

# https://www.microchip.com/en-us/product/mcp23009
# https://ww1.microchip.com/downloads/en/DeviceDoc/20002121C.pdf

### MCP23009 Register definitions ###
IODIR = 0x00
GPIO = 0x09
GPPU = 0x06


class MCP23009(i2c.i2c):
    # address
    SENSOR_ADDRESS = 0x27

    RESET_ADDRESS = IODIR
    RESET_VALUE = 0xFF

    TEST_ADDRESS = IODIR
    TEST_VALUE = (0xFF,)

    # The amount of available channels (8 for MCP23009)
    CHANNELS = 8

    # A button press counts as long press after this amount of milliseconds
    LONG_PRESS_DURATION_MS = 1000

    # After the button is pressed, it is disabled for this amount of milliseconds to prevent bouncing
    DEBOUNCE_DURATION_MS = 80

    # Button reads per second. Should be at least 20 for precise results
    FPS = 30

    _ms_per_frame = 1000 / FPS

    # How many frames it takes to reach the LONG_PRESS_DURATION_MS
    _long_press_frames = int(LONG_PRESS_DURATION_MS // _ms_per_frame)

    # How many frames a button is disabled after release
    _debounce_frames = int(DEBOUNCE_DURATION_MS // _ms_per_frame)

    _thread = None

    # The amount of frames a button is held
    _counter = [0] * CHANNELS
    # Previous button state
    _previous = [0] * CHANNELS
    # Saves the lock state of a Button
    # NOTE: A button is getting locked to debounce or after long press to prevent that the short and long press event gets triggered simultaneously.
    _locked = [False] * CHANNELS

    def __init__(self, config):
        self.config = config
        super().__init__()

    def _run(self):
        sleep_time = 1.0 / self.FPS

        while True:
            try:
                self.read()
            except:
                app_logger.error(f"MCP23009 connection issue! Resetting all buttons...")
                # if an I2C error occurs due to e.g. connection issues, reset all buttons
                for index in range(self.CHANNELS):
                    self._reset_button(index)
            time.sleep(sleep_time)

    def press_button(self, button, index):
        try:
            self.config.button_config.press_button("MCP23009", button, index)
        except:
            app_logger.warning(f"No button_config for button '{button}'")

    def init_sensor(self):
        # Set GP0 to GP7 as inputs (1)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, IODIR, 0xFF)
        # Enable pull-up resistors for GP0 to GP7
        self.bus.write_byte_data(self.SENSOR_ADDRESS, GPPU, 0xFF)

        self._thread = Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()

    def read(self):
        gpio_state = self.bus.read_byte_data(self.SENSOR_ADDRESS, GPIO)
        buttons_pressed = [
            not bool(gpio_state & (1 << i)) for i in range(self.CHANNELS)
        ]

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
