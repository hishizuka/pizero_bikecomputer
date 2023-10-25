from PIL import Image

from logger import app_logger
from .display_core import Display

_SENSOR_DISPLAY = False
try:
    import RPi.GPIO as GPIO
    from papirus import Papirus

    _SENSOR_DISPLAY = True
except ImportError:
    pass

app_logger.info(f"PAPIRUS E-INK DISPLAY: {_SENSOR_DISPLAY}")


class PapirusDisplay(Display):
    papirus = None

    has_color = False
    has_touch = False

    size = (264, 176)

    def __init__(self, config):
        super().__init__(config)
        self.papirus = Papirus(rotation=180)
        self.clear()

    def clear(self):
        self.papirus.clear()

    def update(self, im_array, direct_update=False):
        self.papirus.display(
            Image.frombytes(
                "1", (im_array.shape[1] * 8, im_array.shape[0]), (~im_array).tobytes()
            )
        )
        self.papirus.fast_update()

    def quit(self):
        self.clear()
