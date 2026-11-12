from pathlib import Path

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
        source = Path(__file__).with_name("cython") / "mip_helper_spidev.pyx"
        source_mtime = source.stat().st_mtime_ns
        for extension in source.parent.glob(f"{source.stem}*.so"):
            if extension.stat().st_mtime_ns < source_mtime:
                extension.unlink()

        try:
            from .cython.mip_helper_spidev import MipDisplay_CPP
        except ImportError:
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
    _GPIOCHIP_LABELS = {"pinctrl-bcm2835", "pinctrl-bcm2711", "pinctrl-rp1"}
    _SPI_BUS = 0
    _SPI_DEVICE = 0
    _SPI_MODE = 0b00
    _GPIO_CONSUMER = "pizero_bikecomputer"

    def __init__(self, config, size=None, color=None):
        self._gpiochip_path = self._find_gpiochip()
        super().__init__(config, size, color)

    def _find_gpiochip(self):
        for path in sorted(Path("/dev").glob("gpiochip*")):
            try:
                with gpiod.Chip(str(path)) as chip:
                    if chip.get_info().label in self._GPIOCHIP_LABELS:
                        return str(path)
            except OSError:
                continue
        raise RuntimeError("Raspberry Pi header GPIO chip not found")

    def init_cython(self):
        if MODE == "Cython_full" and not self.config.G_DISPLAY.startswith("MIP_Sharp_mono"):
            self.mip_display_cpp = MipDisplay_CPP(
                self.config.G_DISPLAY_PARAM["SPI_CLOCK"], self._gpiochip_path.encode()
            )
            self.mip_display_cpp.set_screen_size(self.size[0], self.size[1], self.color)
            self.update = self.mip_display_cpp.update
            self.inversion = self.mip_display_cpp.inversion
        elif self.color == 2:
            self.conv_color = self.conv_1bit_2colors_py
        elif self.color == 8:
            self.conv_color = (
                conv_3bit_8colors_cy if MODE == "Cython" else self.conv_3bit_27colors_py
            )
        elif self.color == 64:
            self.conv_color = self.conv_4bit_64colors_py

    def init_spi(self):
        self.spi = spidev.SpiDev()
        self.spi.open(self._SPI_BUS, self._SPI_DEVICE)
        self.spi.mode = self._SPI_MODE
        self.spi.max_speed_hz = self.config.G_DISPLAY_PARAM["SPI_CLOCK"]

    def init_gpio(self):
        pins = (self.DISP, self.VCOMSEL)

        # libgpiod v2 Python API only.
        try:
            settings_default = gpiod.LineSettings(
                direction=Direction.OUTPUT,
                output_value=Value.INACTIVE,
            )
            self._line_request = gpiod.request_lines(
                self._gpiochip_path,
                consumer=self._GPIO_CONSUMER,
                config=dict.fromkeys(pins, settings_default),
            )
        except OSError as e:
            raise RuntimeError(
                f"Failed to request display GPIO lines via gpiod. chip={self._gpiochip_path}, pins={pins}."
            ) from e

    def spi_write(self, data):
        # writebytes2 avoids the readback buffer and is usually faster.
        self.spi.writebytes2(data)

    def gpio_write(self, pin, value):
        self._line_request.set_value(pin, Value.ACTIVE if value else Value.INACTIVE)

    def spi_close(self):
        self.spi.close()
        self._line_request.release()
        
