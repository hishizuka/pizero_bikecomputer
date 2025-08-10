from .mip_display_base import MipDisplayBase

from modules.app_logger import app_logger

_SENSOR_DISPLAY = False
MODE = "Python"
try:
    import pigpio
    _SENSOR_DISPLAY = True

    import pyximport
    pyximport.install()
    from .cython.mip_helper import conv_3bit_8colors_cy, MipDisplay_CPP
    MODE = "Cython_full"
except ImportError:
    pass

if _SENSOR_DISPLAY:
    app_logger.info(f"MIP DISPLAY(pigpio): {_SENSOR_DISPLAY} ({MODE})")


class MipDisplayPigpio(MipDisplayBase):

    def __init__(self, config, size=None, color=None):
        super().__init__(config, size, color)

    def init_cython(self):
        if MODE == "Cython_full" and not self.config.G_DISPLAY.startswith("MIP_Sharp_mono"):
            self.mip_display_cpp = MipDisplay_CPP(
                self.config.G_DISPLAY_PARAM["SPI_CLOCK"],
                self.get_pcb_backlight()
            )
            self.mip_display_cpp.set_screen_size(self.size[0], self.size[1], self.color)
            self.update = self.mip_display_cpp.update
            self.set_brightness = self.mip_display_cpp.set_brightness
            self.inversion = self.mip_display_cpp.inversion
            self.quit = self.mip_display_cpp.quit
            self.use_cpp = True
            return True
        elif MODE == "Cython":
            if self.color == 2:
                self.conv_color = self.conv_1bit_2colors_py
            elif self.color == 8:
                self.conv_color = conv_3bit_8colors_cy
            elif self.color == 64:
                self.conv_color = self.conv_4bit_64colors_py
            return False
        else:
            if self.color == 2:
                self.conv_color = self.conv_1bit_2colors_py
            elif self.color == 8:
                self.conv_color = self.conv_3bit_27colors_py
            if self.color == 64:
                self.conv_color = self.conv_4bit_64colors_py
            return False

    def get_pcb_backlight(self):
        p = 0
        if self.config.G_PCB_BACKLIGHT == "SWITCH_SCIENCE_MIP_BOARD":
            p = 1
        elif self.config.G_PCB_BACKLIGHT == "PIZERO_BIKECOMPUTER":
            p = 2
        return p

    def init_backlight_func(self):
        if self.config.G_PCB_BACKLIGHT == "SWITCH_SCIENCE_MIP_BOARD":
            self.set_PWM = self.set_PWM_switch_science_mip_board
        elif self.config.G_PCB_BACKLIGHT == "PIZERO_BIKECOMPUTER":
            self.set_PWM = self.set_PWM_pizero_bikecomputer_pcb

    def init_spi(self):
        self.pi = pigpio.pi()
        ce_setting = 0b00100000  # no use ce0
        #ce_setting = 0b00000100  # use ce0
        self.spi = self.pi.spi_open(0, self.config.G_DISPLAY_PARAM["SPI_CLOCK"], ce_setting)

    def init_gpio(self):
        self.pi.set_mode(self.DISP, pigpio.OUTPUT)
        self.pi.set_mode(self.SCS, pigpio.OUTPUT)
        self.pi.set_mode(self.VCOMSEL, pigpio.OUTPUT)

    def init_backlight(self):
        if self.config.G_PCB_BACKLIGHT == "PIZERO_BIKECOMPUTER":
            self.pi.set_mode(self.BACKLIGHT_SWITCH, pigpio.OUTPUT)
        self.pi.set_mode(self.BACKLIGHT, pigpio.OUTPUT)
        self.set_PWM(0)

    def spi_write(self, data):
        self.pi.spi_write(self.spi, data)
    
    def gpio_write(self, pin, value):
        self.pi.write(pin, value)

    def set_PWM(self, value):
        pass
    
    def set_PWM_switch_science_mip_board(self, value):
        self.pi.hardware_PWM(self.BACKLIGHT, self.BACKLIGHT_FREQ, value*10000)

    def set_PWM_pizero_bikecomputer_pcb(self, value):
        self.pi.write(self.BACKLIGHT_SWITCH, bool(value))
        self.pi.hardware_PWM(self.BACKLIGHT, self.BACKLIGHT_FREQ, (100-value)*10000)

    def spi_close(self):
        self.set_PWM(0)
        self.pi.spi_close(self.spi)
        self.pi.stop()
