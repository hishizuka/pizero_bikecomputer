from datetime import datetime
import sys
import asyncio

from modules.utils.cmd import exec_cmd, exec_cmd_return_value
from modules.app_logger import app_logger


def set_time(time_info):
    app_logger.info(f"modify time to {time_info}")

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
    
    dt = datetime.fromisoformat(time_info)
    if dt < datetime.fromisoformat(last_known_date):
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
