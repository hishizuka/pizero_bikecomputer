from .mip_display_base import MipDisplayBase

from logger import app_logger

_SENSOR_DISPLAY = False
MODE = "Python"
try:
    import pigpio

    _SENSOR_DISPLAY = True

    import pyximport
    pyximport.install()
    from .cython.mip_helper import conv_3bit_color, MipDisplay_CPP
    MODE = "Cython_full"
except ImportError:
    pass

if _SENSOR_DISPLAY:
    app_logger.info(f"MIP DISPLAY(pigpio): {_SENSOR_DISPLAY}")


class MipDisplayPigpio(MipDisplayBase):

    def __init__(self, config, size=None, color=None):
        super().__init__(config, size, color)

    def init_cython(self):
        if MODE == "Cython_full" and not self.config.G_DISPLAY.startswith("MIP_Sharp_mono"):
            self.mip_display_cpp = MipDisplay_CPP(self.config.G_DISPLAY_PARAM["SPI_CLOCK"])
            self.mip_display_cpp.set_screen_size(self.size[0], self.size[1], self.color)
            self.update = self.mip_display_cpp.update
            self.set_brightness = self.mip_display_cpp.set_brightness
            self.inversion = self.mip_display_cpp.inversion
            self.quit = self.mip_display_cpp.quit
            return True
        elif MODE == "Cython":
            if self.color == 2:
                self.conv_color = self.conv_1bit_color_py
            elif self.color == 8:
                self.conv_color = conv_3bit_color
            elif self.color == 64:
                self.conv_color = self.conv_4bit_color_py
            return False
        else:
            if self.color == 2:
                self.conv_color = self.conv_1bit_color_py
            elif self.color == 8:
                self.conv_color = self.conv_3bit_color_py
            if self.color == 64:
                self.conv_color = self.conv_4bit_color_py
            return False
        
    def init_spi(self):
        self.pi = pigpio.pi()
        self.spi = self.pi.spi_open(0, self.config.G_DISPLAY_PARAM["SPI_CLOCK"], 0)

    def init_gpio(self):
        self.pi.set_mode(self.DISP, pigpio.OUTPUT)
        self.pi.set_mode(self.SCS, pigpio.OUTPUT)
        self.pi.set_mode(self.VCOMSEL, pigpio.OUTPUT)
    
    def init_backlight(self):
        self.pi.set_mode(self.BACKLIGHT, pigpio.OUTPUT)
        self.pi.hardware_PWM(self.BACKLIGHT, self.BACKLIGHT_FREQ, 0)

    def spi_write(self, data):
        self.pi.spi_write(self.spi, data)
    
    def gpio_write(self, pin, value):
        self.pi.write(pin, value)

    def set_PWM(self, value):
        self.pi.hardware_PWM(self.BACKLIGHT, self.BACKLIGHT_FREQ, value*10000)

    def spi_close(self):
        self.pi.spi_close(self.spi)
        self.pi.stop()
