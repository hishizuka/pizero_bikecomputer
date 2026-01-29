from datetime import datetime, timezone
import asyncio
import threading

from modules.utils.cmd import exec_cmd, exec_cmd_return_value
from modules.app_logger import app_logger


_LAST_KNOWN_DATE_CACHE = None
_LAST_KNOWN_DATE_INITIALIZED = False
_LAST_KNOWN_DATE_LOCK = threading.Lock()
_UTC_OFFSET_MINUTES = None


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


def init_utc_offset():
    """Initialize UTC offset from system timezone (call at startup)."""
    global _UTC_OFFSET_MINUTES
    offset = datetime.now().astimezone().utcoffset()
    _UTC_OFFSET_MINUTES = int(offset.total_seconds() // 60) if offset else 0


def update_utc_offset():
    """Update UTC offset (call after GPS timezone update)."""
    init_utc_offset()


def _get_utc_offset_minutes():
    if _UTC_OFFSET_MINUTES is None:
        init_utc_offset()
    return _UTC_OFFSET_MINUTES


def _shift_hhmm_to_local(utc_hhmm):
    """Convert HHMM format UTC time to local time by adding offset."""
    if not utc_hhmm or len(utc_hhmm) < 4:
        return ""
    try:
        total = (int(utc_hhmm[0:2]) * 60 + int(utc_hhmm[2:4]) + _get_utc_offset_minutes()) % 1440  # minutes per day
        return f"{total // 60:02d}{total % 60:02d}"
    except ValueError:
        return ""


def format_jma_validtime_local(validtime, time_format):
    """Convert JMA validtime (extract HHMM from last 6 chars) to local HHMM."""
    if not validtime or len(validtime) < 4:
        return ""
    hhmm = validtime[-6:-2] if len(validtime) >= 6 else validtime[:4]
    return _shift_hhmm_to_local(hhmm)


def format_scw_validtime_local(validtime):
    """Convert SCW validtime (first HHMMSS) to local HHMM."""
    if not validtime or len(validtime) < 4:
        return ""
    return _shift_hhmm_to_local(validtime[:4])


def format_unix_validtime_local(validtime):
    """Convert Unix timestamp to local HHMM."""
    if validtime is None:
        return ""
    try:
        utc_dt = datetime.fromtimestamp(int(validtime), tz=timezone.utc)
        return _shift_hhmm_to_local(f"{utc_dt.hour:02d}{utc_dt.minute:02d}")
    except (TypeError, ValueError):
        return ""


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
        update_utc_offset()
        app_logger.info(f"success: {tz_str}")


def _resolve_timezone(lat, lon):
    from timezonefinder import TimezoneFinder  # heavy import off the UI thread
    app_logger.info("try to modify timezone by gps...")
    finder = TimezoneFinder()
    tz = finder.timezone_at(lng=lon, lat=lat)
    if tz is None:
        tz = finder.certain_timezone_at(lng=lon, lat=lat)
    return tz
