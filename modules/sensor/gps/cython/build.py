import time
from datetime import datetime, timezone

# Prefer a prebuilt extension if present, otherwise build in-place.
try:
    from cxd5610_helper import CXD5610  # noqa: E402
except Exception:
    import pyximport
    # Build/import Cython extension in-place.
    pyximport.install(inplace=True, language_level=3)
    from cxd5610_helper import CXD5610  # noqa: E402


def fmt(val):
    """Return val or '-' if None."""
    return "-" if val is None else val


def main():
    try:
        gps = CXD5610()
    except OSError as exc:
        # Early exit with errno for easier troubleshooting.
        print(f"[INIT] failed (errno={exc.errno}): {exc}")
        return

    print("[INIT] CXD5610 ready, polling every 1s. Ctrl+C to stop.")

    try:
        while True:
            try:
                ret = gps.poll(1000)  # wait up to 1s for a packet
                if ret < 0:
                    print(f"[WARN] poll returned {ret}")
            except OSError as exc:
                print(f"[ERROR] poll failed (errno={exc.errno}): {exc}")
                time.sleep(1)
                continue

            ts = gps.timestamp
            ts_str = "-" if ts is None else datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            print(
                f"time={ts_str} "
                f"lat={fmt(gps.lat)} lon={fmt(gps.lon)} alt={fmt(gps.alt)} "
                f"spd={fmt(gps.speed)} track={fmt(gps.track)} "
                f"mode={gps.mode} status={gps.status} "
                f"sat={gps.used_sats}/{gps.total_sats} "
                f"DOP(p/h/v)={fmt(gps.pdop)}/{fmt(gps.hdop)}/{fmt(gps.vdop)}"
            )
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[EXIT] stop requested.")


if __name__ == "__main__":
    main()
