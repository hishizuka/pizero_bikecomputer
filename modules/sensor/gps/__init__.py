from modules.app_logger import app_logger

from .gpsd import _SENSOR_GPS_GPSD, _SENSER_GPS_STR, GPSD
from .i2c_cxd5610 import _SENSOR_GPS_CXD5610, CXD5610_GPS

if _SENSOR_GPS_CXD5610:
    SensorGPS = CXD5610_GPS
elif _SENSOR_GPS_GPSD:
    SensorGPS = GPSD
else:
    # we always have a non-null GPS sensor, but it won't generate data unless told to do so with G_DUMMY_OUTPUT
    from .dummy import Dummy_GPS
    SensorGPS = Dummy_GPS

sensor_detail = ""
if SensorGPS is GPSD and _SENSOR_GPS_GPSD:
    sensor_detail = f"/{_SENSER_GPS_STR}"

app_logger.info(f"  GPS ({SensorGPS.__name__}{sensor_detail})")
