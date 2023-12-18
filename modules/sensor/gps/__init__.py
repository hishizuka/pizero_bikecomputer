from logger import app_logger


from .adafruit_uart import _SENSOR_GPS_ADAFRUIT_UART, Adafruit_GPS
from .gpsd import _SENSOR_GPS_GPSD, GPSD
from .i2c import _SENSOR_GPS_I2C, GPS_I2C

# we always have a non-null GPS sensor, but it won't generate data unless told to do so with G_DUMMY_OUTPUT
from .dummy import Dummy_GPS

if _SENSOR_GPS_GPSD:
    SensorGPS = GPSD
elif _SENSOR_GPS_I2C:
    SensorGPS = GPS_I2C
elif _SENSOR_GPS_ADAFRUIT_UART:
    SensorGPS = Adafruit_GPS
else:
    SensorGPS = Dummy_GPS

app_logger.info(f"GPS ({SensorGPS.__name__})")
