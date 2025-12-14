from .mip_display_base import MipDisplayBase

from modules.app_logger import app_logger

_SENSOR_DISPLAY = False
MODE = "Python"
MipDisplay_CPP = None
try:
    import spidev
    import gpiod
    from gpiod.line import Direction, Value
    _SENSOR_DISPLAY = True

    # Prefer a prebuilt Cython extension if available.
    # Falling back to pyximport keeps source builds working, while
    # avoiding runtime recompilation on every boot.
    try:
        from .cython.mip_helper_spidev import MipDisplay_CPP
        MODE = "Cython_full"
    except Exception:
        try:
            import pyximport

            # Build in-place so the compiled .so can be imported directly next time.
            pyximport.install(inplace=True, language_level=3)
            from .cython.mip_helper_spidev import MipDisplay_CPP
            MODE = "Cython_full"
        except Exception:
            pass

    if MODE != "Cython_full":
        # Optional: conversion-only helper (no hardware deps).
        try:
            from .cython.mip_helper import conv_3bit_8colors_cy
            MODE = "Cython"
        except Exception:
            try:
                import pyximport

                # Build in-place so the compiled .so can be imported directly next time.
                pyximport.install(inplace=True, language_level=3)
                from .cython.mip_helper import conv_3bit_8colors_cy
                MODE = "Cython"
            except Exception:
                pass
except ImportError:
    pass

if _SENSOR_DISPLAY:
    app_logger.info(f"MIP DISPLAY(spidev): {_SENSOR_DISPLAY} ({MODE})")


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
        if MODE == "Cython_full" and not self.config.G_DISPLAY.startswith("MIP_Sharp_mono"):
            self.mip_display_cpp = MipDisplay_CPP(
                self.config.G_DISPLAY_PARAM["SPI_CLOCK"]
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
        
