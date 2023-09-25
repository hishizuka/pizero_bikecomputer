from PIL import Image

from logger import app_logger

_SENSOR_DISPLAY = False
try:
    import RPi.GPIO as GPIO
    from papirus import Papirus

    _SENSOR_DISPLAY = True
except ImportError:
    pass

app_logger.info(f"PAPIRUS E-INK DISPLAY: {_SENSOR_DISPLAY}")


class PapirusDisplay:
    config = None
    papirus = None

    def __init__(self, config):
        self.config = config

        if _SENSOR_DISPLAY:
            self.papirus = Papirus(rotation=180)
            self.clear()

    def clear(self):
        self.papirus.clear()

    def update(self, im_array):
        self.papirus.display(
            Image.frombytes(
                "1", (im_array.shape[1] * 8, im_array.shape[0]), (~im_array).tobytes()
            )
        )
        self.papirus.fast_update()

    def quit(self):
        if _SENSOR_DISPLAY:
            self.clear()
