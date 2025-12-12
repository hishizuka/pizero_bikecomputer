import asyncio
import time
from datetime import datetime, timezone

from modules.app_logger import app_logger
from .base import AbstractSensorGPS

_SENSOR_GPS_CXD5610 = False
try:
    # Prefer a prebuilt Cython extension if available.
    from .cython.cxd5610_helper import CXD5610 as CXD5610_C
    _SENSOR_GPS_CXD5610 = True
except Exception:
    # Fallback to an in-place build so future boots can import the .so directly.
    try:
        import pyximport
        pyximport.install(inplace=True, language_level=3)
        from .cython.cxd5610_helper import CXD5610 as CXD5610_C
        _SENSOR_GPS_CXD5610 = True
    except Exception as exc:
        app_logger.warning(f"[CXD5610] Cython import failed: {exc}")


class CXD5610_GPS(AbstractSensorGPS):
    NULL_VALUE = None

    def sensor_init(self):
        super().sensor_init()
        self.dev = None
        if not _SENSOR_GPS_CXD5610:
            app_logger.warning("[CXD5610] Module not available")
            return
        try:
            self.dev = CXD5610_C()
        except Exception as exc:
            # Keep Python side alive even if the C helper is missing.
            app_logger.error(f"[CXD5610] Init failed: {exc}")
            self.dev = None

    async def update(self):
        if self.dev is None:
            return

        while not self.quit_status:
            self.start_time = time.perf_counter()
            try:
                ret = self.dev.poll(int(self.config.G_GPS_INTERVAL * 1000))
            except Exception as exc:
                app_logger.error(f"[CXD5610] Poll error: {exc}")
                await asyncio.sleep(1.0)
                continue

            if ret < 0:
                app_logger.warning(f"[CXD5610] Read returned {ret}")
                await asyncio.sleep(0.5)
                continue

            ts = self.dev.timestamp
            gps_time = None
            if ts is not None:
                gps_time = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

            dop = tuple(
                val if val is not None else self.NULL_VALUE
                for val in (self.dev.pdop, self.dev.hdop, self.dev.vdop)
            )

            satellites = (self.dev.used_sats, self.dev.total_sats)

            await self.get_basic_values(
                self.dev.lat,
                self.dev.lon,
                self.dev.alt,
                self.dev.speed,
                self.dev.track,
                self.dev.mode,
                self.dev.status,
                None,  # accuracy error vector not provided by the chip
                dop,
                satellites,
                gps_time,
            )

            self.get_sleep_time(self.config.G_GPS_INTERVAL)
            await self.sleep()

    async def quit(self):
        await super().quit()
        self.dev = None
