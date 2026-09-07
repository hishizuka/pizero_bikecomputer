import asyncio
import errno
import time
from datetime import datetime, timezone

from modules.app_logger import app_logger
from .base import AbstractSensorGPS
from ..i2c_utils import i2c_addr_present as _i2c_addr_present

_SENSOR_GPS_CXD56XX = False

# GNSS I2C slave address (7-bit).
CXD56XX_I2C_ADDR = 0x24


if _i2c_addr_present(CXD56XX_I2C_ADDR):
    try:
        from cxd56xx_gnss import CXD56xx
    except (ImportError, OSError) as exc:
        app_logger.warning(f"[CXD56xx] rpi-cxd56xx-gnss import failed: {exc}")
    else:
        _SENSOR_GPS_CXD56XX = True


class CXD56xx_GPS(AbstractSensorGPS):
    NULL_VALUE = None

    def sensor_init(self):
        super().sensor_init()
        self.dev = None
        if not _SENSOR_GPS_CXD56XX:
            app_logger.warning("[CXD56xx] Module not available")
            self.quit_status = True
            return
        try:
            self.dev = CXD56xx()
        except OSError as exc:
            if exc.errno == errno.ENODEV:
                app_logger.info("[CXD56xx] Disabled (device not detected)")
            else:
                app_logger.error(f"[CXD56xx] Init failed: {exc}")
            self.dev = None
            self.quit_status = True
        except Exception as exc:
            app_logger.error(f"[CXD56xx] Init failed: {exc}")
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
                app_logger.error(f"[CXD56xx] Read error: {exc}")
                await asyncio.sleep(1.0)
                continue

            if ret < 0:
                if ret != -errno.EAGAIN:
                    app_logger.warning(f"[CXD56xx] Read returned {ret}")
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
