from .mip_display_base import MipDisplayBase

from modules.app_logger import app_logger

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
    _GPIOCHIP_PATH = "/dev/gpiochip4"
    _SPI_BUS = 0
    _SPI_DEVICE = 0
    _SPI_MODE = 0b00
    _GPIO_CONSUMER = "pizero_bikecomputer"

    def __init__(self, config, size=None, color=None):
        self._line_request = None
        self._value_active = None
        self._value_inactive = None
        super().__init__(config, size, color)

    def init_cython(self):
        if self.color == 2:
            self.conv_color = self.conv_1bit_2colors_py
        elif self.color == 8:
            self.conv_color = self.conv_3bit_27colors_py
        if self.color == 64:
            self.conv_color = self.conv_4bit_64colors_py
        return False

    def init_spi(self):
        self.spi = spidev.SpiDev()
        self.spi.open(self._SPI_BUS, self._SPI_DEVICE)
        self.spi.mode = self._SPI_MODE
        self.spi.max_speed_hz = self.config.G_DISPLAY_PARAM["SPI_CLOCK"]

    def _gpio_pins(self):
        return [self.DISP, self.VCOMSEL]

    def init_gpio(self):
        pins = self._gpio_pins()

        # libgpiod v2 Python API only.
        try:
            from gpiod.line import Direction, Value

            settings_default = gpiod.LineSettings(
                direction=Direction.OUTPUT,
                output_value=Value.INACTIVE,
            )
            config = {pin: settings_default for pin in pins}

            self._line_request = gpiod.request_lines(
                self._GPIOCHIP_PATH,
                consumer=self._GPIO_CONSUMER,
                config=config,
            )
            self._value_active = Value.ACTIVE
            self._value_inactive = Value.INACTIVE
        except OSError as e:
            raise RuntimeError(
                f"Failed to request display GPIO lines via gpiod. chip={self._GPIOCHIP_PATH}, pins={pins}. "
                "If GPIO8 is busy (claimed by SPI0 CS0), move SPI0 CS0 to another pin in "
                "device-tree overlay and reboot."
            ) from e
    
    def init_backlight(self):
        pass

    def spi_write(self, data):
        # writebytes2 avoids the readback buffer and is usually faster.
        self.spi.writebytes2(data)

    def gpio_write(self, pin, value):
        v = self._value_active if value else self._value_inactive
        self._line_request.set_value(pin, v)

    def set_PWM(self, value):
        pass

    def spi_close(self):
        self.spi.close()
        self._line_request.release()
        