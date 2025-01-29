from .mip_display_base import MipDisplayBase

from modules.app_logger import app_logger

_SENSOR_DISPLAY = False
try:
    import mraa
    _SENSOR_DISPLAY = True
except ImportError:
    pass

if _SENSOR_DISPLAY:
    app_logger.info(f"MIP DISPLAY(mraa): {_SENSOR_DISPLAY}")


class MipDisplayMraa(MipDisplayBase):

    # GPIO.BCM
    DISP = 13
    SCS = 16
    VCOMSEL = 11
    BACKLIGHT = 12 # 18?
    gpio = {}

    def __init__(self, config, size=None, color=None):
        super().__init__(config, size, color)

        if self.color == 2:
            self.conv_color = self.conv_1bit_color_py
        elif self.color == 8:
            self.conv_color = self.conv_3bit_color_py
        if self.color == 64:
            self.conv_color = self.conv_4bit_color_py

    def init_spi(self):
        self.spi = mraa.Spi(1)
        self.spi.mode(0)
        self.spi.frequency(self.config.G_DISPLAY_PARAM["SPI_CLOCK"])

    def init_gpio(self):
        for key in [self.DISP, self.SCS, self.VCOMSEL]:
            self.gpio[key] = mraa.Gpio(key)
            self.gpio[key].dir(mraa.DIR_OUT)
        self.gpio[self.SCS].write(0)
        self.gpio[self.DISP].write(1)
        self.gpio[self.VCOMSEL].write(1)
    
    def init_backlight(self): 
        self.gpio[self.BACKLIGHT] = mraa.Pwm(0, chipid=4)
        self.gpio[self.BACKLIGHT].period_ms(15)
        self.gpio[self.BACKLIGHT].enable(True)

    def spi_write(self, data):
        self.spi.write(bytearray(data))

    def gpio_write(self, pin, value):
        self.gpio[pin].write(value)

    def set_PWM(self, value):
        self.gpio[self.BACKLIGHT].write(value/100)

    def spi_close(self):
        self.GPIO[self.BACKLIGHT].enable(False)
