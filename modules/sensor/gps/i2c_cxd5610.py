import asyncio
import errno
import time
from datetime import datetime, timezone

from modules.app_logger import app_logger
from .base import AbstractSensorGPS
from ..i2c_utils import i2c_addr_present as _i2c_addr_present

_SENSOR_GPS_CXD5610 = False

# Keep the same name/value as modules/sensor/gps/cython/cxd5610_rpi.h
CXD5610_I2C_ADDR = 0x24


try:
    # Prefer a prebuilt Cython extension if available.
    from .cython.cxd5610_helper import CXD5610 as CXD5610_C
    _SENSOR_GPS_CXD5610 = True
except Exception:
    # Fallback to an in-place build so future boots can import the .so directly.
    try:
        if _i2c_addr_present(CXD5610_I2C_ADDR, bus=1):
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
            self.quit_status = True
            return
        try:
            self.dev = CXD5610_C()
        except OSError as exc:
            if exc.errno == errno.ENODEV:
                app_logger.info("[CXD5610] Disabled (device not detected)")
            else:
                app_logger.error(f"[CXD5610] Init failed: {exc}")
            self.dev = None
            self.quit_status = True
        except Exception as exc:
            app_logger.error(f"[CXD5610] Init failed: {exc}")
            self.dev = None
            self.quit_status = True

    async def update(self):
        if self.dev is None:
            return

        while not self.quit_status:
            self.start_time = time.perf_counter()
            try:
                # Read the latest data snapshot updated by the C worker thread.
                ret = self.dev.peek()
            except Exception as exc:
                app_logger.error(f"[CXD5610] Read error: {exc}")
                await asyncio.sleep(1.0)
                continue

            if ret < 0:
                if ret != -errno.EAGAIN:
                    app_logger.warning(f"[CXD5610] Read returned {ret}")
                self.get_sleep_time(self.config.G_GPS_INTERVAL)
                await self.sleep()
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
