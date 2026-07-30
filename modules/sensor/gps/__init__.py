from modules.app_logger import app_logger


def get_sensor_gps_class():
    from .i2c_cxd5610 import _SENSOR_GPS_CXD5610, CXD5610_GPS

    if _SENSOR_GPS_CXD5610:
        sensor_gps = CXD5610_GPS
        sensor_detail = ""
    else:
        sensor_gps, sensor_detail = _detect_ublox()
        if sensor_gps is None:
            sensor_gps, sensor_detail = _detect_gpsd()

    if sensor_gps is None:
        from .dummy import Dummy_GPS

        sensor_gps = Dummy_GPS
        sensor_detail = ""

    app_logger.info(f"  GPS ({sensor_gps.__name__}{sensor_detail})")
    return sensor_gps


def _detect_ublox():
    try:
        from .ublox_support.transport import detect_sensor_ublox
    except ModuleNotFoundError:
        return None, ""

    detected, uart_device = detect_sensor_ublox()
    if not detected:
        return None, ""

    from .ublox import UBlox, _UBLOX_IMPORT_ERROR

    if _UBLOX_IMPORT_ERROR is not None:
        return None, ""
    UBlox.detected_uart_device = uart_device
    return UBlox, ""


def _detect_gpsd():
    from .gpsd import _SENSOR_GPS_GPSD, _SENSER_GPS_STR, GPSD

    if not _SENSOR_GPS_GPSD:
        return None, ""
    return GPSD, f"/{_SENSER_GPS_STR}"
