from .mip_display_base import MipDisplayBase

from logger import app_logger

_SENSOR_DISPLAY = False
try:
    import spidev
    import gpiod

    _SENSOR_DISPLAY = True
except ImportError:
    pass

if _SENSOR_DISPLAY:
    app_logger.info(f"MIP DISPLAY(spidev): {_SENSOR_DISPLAY}")


class MipDisplaySpidev(MipDisplayBase):
    chip = None
    GPIO = {}

    def __init__(self, config, size=None, color=None):
        super().__init__(config, size, color)

    def init_cython(self):
        if self.color == 2:
            self.conv_color = self.conv_1bit_color_py
        elif self.color == 8:
            self.conv_color = self.conv_3bit_color_py
        if self.color == 64:
            self.conv_color = self.conv_4bit_color_py

    def init_spi(self):
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.mode = 0b00 #SPI MODE0
        self.spi.max_speed_hz = self.config.G_DISPLAY_PARAM["SPI_CLOCK"]
        self.spi.no_cs

    def init_gpio(self):
        self.chip = gpiod.Chip('gpiochip4', gpiod.Chip.OPEN_BY_NAME)
        for key in [self.DISP, self.SCS, self.VCOMSEL]:
            self.GPIO[key] = self.chip.get_line(key)
            self.GPIO[key].request(consumer="LED", type=gpiod.LINE_REQ_DIR_OUT)
    
    def init_backlight(self):
        pass

    def spi_write(self, data):
        self.spi.xfer3(data)
    
    def gpio_write(self, pin, value):
        self.GPIO[pin].set_value(value)

    def set_PWM(self, value):
        pass

    def spi_close(self):
        self.spi.close()
