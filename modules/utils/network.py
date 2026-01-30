import socket
import time
import asyncio
import threading

_DEFAULT_HOST = "8.8.8.8"
_DEFAULT_PORT = 53
_DEFAULT_TIMEOUT = 3.0

_DETECT_CACHE = {}
_DETECT_LOCK = threading.Lock()


def _cache_key(host, port, timeout):
    return (host, port, timeout)


def _get_cache_entry_locked(key):
    return _DETECT_CACHE.setdefault(
        key, {"value": False, "timestamp": 0.0, "in_flight": False}
    )


def _set_cache_value(key, value, timestamp, in_flight=False):
    with _DETECT_LOCK:
        entry = _get_cache_entry_locked(key)
        entry["value"] = value
        entry["timestamp"] = timestamp
        entry["in_flight"] = in_flight


def _get_cached_value(key, ttl, now):
    with _DETECT_LOCK:
        entry = _get_cache_entry_locked(key)
        if now - entry["timestamp"] <= ttl:
            return entry["value"], True
        if entry["in_flight"]:
            return entry["value"], True
        entry["in_flight"] = True
        return entry["value"], False


def _detect_network_raw(
    host=_DEFAULT_HOST,
    port=_DEFAULT_PORT,
    timeout=_DEFAULT_TIMEOUT
):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connect_interface:
            connect_interface.settimeout(timeout)
            connect_interface.connect((host, port))
            return connect_interface.getsockname()[0]
    except OSError:
        return False


def detect_network(
    cache=True,
    ttl=5.0,
    host=_DEFAULT_HOST,
    port=_DEFAULT_PORT,
    timeout=_DEFAULT_TIMEOUT
):
    if cache:
        return _detect_network_cached(host, port, timeout, ttl)
    return _detect_network_raw(host, port, timeout)


async def detect_network_async(
    cache=True,
    ttl=5.0,
    host=_DEFAULT_HOST,
    port=_DEFAULT_PORT,
    timeout=_DEFAULT_TIMEOUT,
):
    # Non-blocking network check for asyncio contexts.
    if cache:
        return _detect_network_cached(host, port, timeout, ttl)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
    except Exception:
        return False

    try:
        sockname = writer.get_extra_info("sockname")
        return sockname[0] if sockname else False
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _refresh_detect_network_async(key, host, port, timeout):
    result = await detect_network_async(
        cache=False, host=host, port=port, timeout=timeout
    )
    _set_cache_value(key, result, time.monotonic(), in_flight=False)


def _schedule_refresh_async(key, host, port, timeout):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    loop.create_task(_refresh_detect_network_async(key, host, port, timeout))
    return True


def _detect_network_cached(host, port, timeout, ttl):
    # Non-blocking network check with background refresh.
    key = _cache_key(host, port, timeout)
    now = time.monotonic()
    cached_value, should_return = _get_cached_value(key, ttl, now)
    if should_return:
        return cached_value

    if _schedule_refresh_async(key, host, port, timeout):
        return cached_value

    # No running loop: refresh synchronously in this thread.
    result = _detect_network_raw(host, port, timeout)
    _set_cache_value(key, result, time.monotonic(), in_flight=False)
    return result
