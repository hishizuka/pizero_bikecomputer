import digitalio
import board
from PIL import Image, ImageDraw
from logger import app_logger
import numpy as np


from modules.display.display_core import Display

_SENSOR_DISPLAY = False
try:
    from adafruit_rgb_display import st7789

    _SENSOR_DISPLAY = True
except ImportError:
    pass

app_logger.info(f"ST7789 Breakout DISPLAY: {_SENSOR_DISPLAY}")


# Configuration for CS and DC pins
cs_pin = digitalio.DigitalInOut(board.CE0)
dc_pin = digitalio.DigitalInOut(board.D9)
reset_pin = digitalio.DigitalInOut(board.D24)

# Config for display baudrate
BAUDRATE = 120 * 1000 * 1000


class ST7789BreakoutDisplay(Display):
    st7789 = None
    rotation = 0
    blank_buffer = None
    blank_draw = None
    # backlight = None
    pi = None

    has_auto_brightness = False
    has_color = True
    # Actually has touch, but has to be implemented
    has_touch = False
    send = True

    backlight_pin = digitalio.DigitalInOut(board.D13)
    backlight_pin.direction = digitalio.Direction.OUTPUT

    size = (320, 240)

    def __init__(self, config, size=None):
        super().__init__(config)

        is_horizontal = config.G_DISPLAY_ORIENTATION == "horizontal"

        if size is not None:
            self.size = size if is_horizontal else size[::-1]
            pass

        spi = board.SPI()

        res = self.resolution

        if is_horizontal:
            res = res[::-1]
            self.rotation = 90

        self.st7789 = st7789.ST7789(
            spi,
            rotation=self.rotation,
            width=res[0],
            height=res[1],
            x_offset=0,
            y_offset=0,
            cs=cs_pin,
            dc=dc_pin,
            rst=reset_pin,
            baudrate=BAUDRATE,
        )

        self.set_brightness(1)

        self.blank_buffer = Image.new("RGB", self.resolution)
        self.blank_draw = ImageDraw.Draw(self.blank_buffer)
        self.blank_draw.rectangle((0, 0, *self.resolution), (0, 0, 0))
        self.clear()

    def quit(self):
        self.clear()
        self.set_brightness(0)

    def clear(self):
        self.st7789.image(self.blank_buffer)

    def update(self, im_array, direct_update=False):
        im_array = 255 - im_array
        img = Image.fromarray(im_array, "RGB")
        self.st7789.image(img)

    def set_brightness(self, b):
        # 0 will be False, everything greater than 0 will be True
        b = bool(b)
        if b == self.backlight_pin.value:
            return

        self.backlight_pin.value = b
