from datetime import datetime
import asyncio
import threading

from modules.utils.cmd import exec_cmd, exec_cmd_return_value
from modules.app_logger import app_logger


_LAST_KNOWN_DATE_CACHE = None
_LAST_KNOWN_DATE_INITIALIZED = False
_LAST_KNOWN_DATE_LOCK = threading.Lock()


def _get_last_known_date():
    global _LAST_KNOWN_DATE_CACHE, _LAST_KNOWN_DATE_INITIALIZED
    if _LAST_KNOWN_DATE_INITIALIZED:
        return _LAST_KNOWN_DATE_CACHE
    with _LAST_KNOWN_DATE_LOCK:
        if _LAST_KNOWN_DATE_INITIALIZED:
            return _LAST_KNOWN_DATE_CACHE
        last_known_date, _ = exec_cmd_return_value(
            [
                "git",
                "log",
                "-1",
                "--format=%cI",
                "--date=iso-strict",
            ],
            cmd_print=False,
        )
        try:
            _LAST_KNOWN_DATE_CACHE = datetime.fromisoformat(last_known_date)
        except Exception:
            _LAST_KNOWN_DATE_CACHE = None
        _LAST_KNOWN_DATE_INITIALIZED = True
        return _LAST_KNOWN_DATE_CACHE


def set_time(time_info):
    app_logger.info(f"modify time to {time_info}")

    dt = datetime.fromisoformat(time_info)
    last_known_date = _get_last_known_date()
    if last_known_date is not None and dt < last_known_date:
        return False

    exec_cmd(
        ["sudo", "date", "-u", "--set", time_info],
        cmd_print=False,
    )
    return True


async def set_timezone(lat, lon):
    try:
        tz_str = await asyncio.to_thread(_resolve_timezone, lat, lon)
    except ImportError:
        return
    if tz_str is None:
        return
    ret_code = await asyncio.to_thread(
        exec_cmd,
        ["sudo", "timedatectl", "set-timezone", tz_str],
        False
    )
    if ret_code:  # 0 = success
        app_logger.warning(f"Timezone {tz_str} be could not set: {ret_code}")
    else:
        app_logger.info(f"success: {tz_str}")


def _resolve_timezone(lat, lon):
    from timezonefinder import TimezoneFinder  # heavy import off the UI thread
    app_logger.info("try to modify timezone by gps...")
    finder = TimezoneFinder()
    tz = finder.timezone_at(lng=lon, lat=lat)
    if tz is None:
        tz = finder.certain_timezone_at(lng=lon, lat=lat)
    return tz
