from datetime import datetime

_TIMEZONE_FINDER = False
try:
    from timezonefinder import TimezoneFinder
    _TIMEZONE_FINDER =True
except:
    pass

from modules.utils.cmd import exec_cmd, exec_cmd_return_value
from logger import app_logger


def set_time(time_info):
    app_logger.info(f"modify time to {time_info}")

    last_known_date = exec_cmd_return_value(
        [
            "git",
            "log",
            "-1",
            "--format=%cI",
            "--date=iso-strict",
        ],
        cmd_print=False,
    )

    if datetime.fromisoformat(time_info) < datetime.fromisoformat(last_known_date):
        return False

    exec_cmd(
        ["sudo", "date", "-u", "--set", time_info],
        cmd_print=False,
    )
    return True


async def set_timezone(lat, lon):
    if not _TIMEZONE_FINDER:
        return

    app_logger.info("try to modify timezone by gps...")

    tz_finder = TimezoneFinder()
    try:
        tz_str = tz_finder.timezone_at(lng=lon, lat=lat)

        if tz_str is None:
            # certain_timezone_at is deprecated since timezonefinder 6.2.0
            tz_str = tz_finder.certain_timezone_at(lng=lon, lat=lat)

        if tz_str is not None:
            ret_code = exec_cmd(
                ["sudo", "timedatectl", "set-timezone", tz_str], cmd_print=False
            )
            if ret_code:  # 0 = success
                app_logger.warning(f"Timezone {tz_str} be could not set: {ret_code}")
            else:
                app_logger.info(f"success: {tz_str}")
    except TypeError as e:
        app_logger.exception(f"Incorrect lat, lon passed: {e}")
    except Exception as e:
        app_logger.warning(f"Could not set timezone: {e}")
