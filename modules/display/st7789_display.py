from PIL import Image, ImageDraw

from logger import app_logger
from .display_core import Display

_SENSOR_DISPLAY = False
try:
    from ST7789 import ST7789
    #import pigpio

    _SENSOR_DISPLAY = True
except ImportError:
    pass

app_logger.info(f"ST7789 DISPLAY: {_SENSOR_DISPLAY}")

GPIO_BACKLIGHT = 13
GPIO_BACKLIGHT_FREQ = 64

class ST7789Display(Display):
    st7789 = None
    rotation = 90
    blank_buffer = None
    blank_draw = None
    # backlight = None
    pi = None

    has_touch = False
    send = True

    brightness = 100
    #brightness_table = [0, 1, 2, 3, 4, 5, 10, 50, 100]
    brightness_table = [0, 100]
    brightness_index = len(brightness_table)-1

    size = (240, 240)

    def __init__(self, config, size=None):
        super().__init__(config)

        if size:
            self.size = size
        if config.G_DISPLAY == "Display_HAT_Mini":
            self.rotation = 180

        self.st7789 = ST7789(
            height=self.size[1],
            width=self.size[0],
            rotation=self.rotation,
            port=0,
            cs=1,
            dc=9,
            #backlight=None,
            backlight=13,
            spi_speed_hz=120 * 1000 * 1000,
            offset_left=0,
            offset_top=0,
        )
        self.st7789.begin()

        # backlight
        #self.pi = pigpio.pi()
        #self.pi.set_mode(GPIO_BACKLIGHT, pigpio.OUTPUT)
        #self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, 100 * 10000)

        self.blank_buffer = Image.new("RGB", self.size)
        self.blank_draw = ImageDraw.Draw(self.blank_buffer)
        self.blank_draw.rectangle((0, 0, *self.size), (0, 0, 0))
        self.clear()

    def quit(self):
        self.clear()
        self.set_brightness(0)

    def clear(self):
        # self.st7789.reset()
        self.st7789.display(self.blank_buffer)

    def update(self, im_array, direct_update=False):
        self.st7789.display(im_array)

    def set_brightness(self, b):
        if b == self.brightness:
            return
        #self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, b * 10000)
        if b == 0:
            self.st7789.set_backlight(False)
        else:
            self.st7789.set_backlight(True)
        self.brightness = b