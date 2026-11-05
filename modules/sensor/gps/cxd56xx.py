"""CXD56xx I2C/UART GPS backends with shared position and DCR handling."""

import asyncio
import errno
import time
from datetime import datetime, timezone

from modules.app_logger import app_logger
from .base import AbstractSensorGPS
from .qzss.receiver import QzssDcrSupport
from ..i2c.detection import i2c_addr_present as _i2c_addr_present

# GNSS I2C slave address (7-bit).
CXD56XX_I2C_ADDR = 0x24


def detect_cxd56xx():
    if not _i2c_addr_present(CXD56XX_I2C_ADDR):
        return None
    try:
        from cxd56xx_gnss import CXD56xx
    except (ImportError, OSError) as exc:
        app_logger.warning(f"[CXD56xx] rpi-cxd56xx-gnss import failed: {exc}")
        return None
    return CXD56xx


class CXD56xxGPSBase(QzssDcrSupport, AbstractSensorGPS):
    WAIT_READY = True
    NULL_VALUE = None

    def sensor_init(self):
        super().sensor_init()
        self.init_qzss_dcr()
        self.dev = None
        self._update_task = None
        self._dcreports_dropped = 0

    def _create_device(self, enabled):
        raise NotImplementedError

    async def _open_device(self):
        enabled = self.config.G_GPS_QZSS_DCR["STATUS"]
        creation = asyncio.create_task(asyncio.to_thread(self._create_device, enabled))
        try:
            self.dev = await asyncio.shield(creation)
        except asyncio.CancelledError as cancelled:
            try:
                self.dev = await creation
            finally:
                await self._close_device()
                raise cancelled
        self.qzss_dcr_status.update(status="pending", error=None)
        if self.WAIT_READY:
            await self.device_call(self.dev.wait_ready, 15.0)
        self._dcreports_dropped = 0
        self.finish_qzss_dcr_change(enabled)

    async def _close_device(self):
        dev, self.dev = self.dev, None
        self._qzss_dcr_active = False
        self.init_values()
        if dev is not None:
            try:
                await self.device_call(dev.close)
            except OSError as exc:
                # The native API releases resources even when STOP acknowledgement fails.
                app_logger.warning(f"[CXD56xx] Close failed: {exc}")

    async def update(self):
        if self.quit_status:
            return
        self._update_task = asyncio.current_task()
        try:
            if self.config.G_GPS_QZSS_DCR["STATUS"]:
                await self.start_qzss_dcr()
            while not self.quit_status:
                self.start_time = time.perf_counter()
                try:
                    if self.dev is None:
                        async with self._qzss_dcr_lock:
                            if self.quit_status:
                                break
                            await self._open_device()
                    # Drain independent reports even when no position snapshot is available.
                    messages = self.dev.read_dcreports()
                    ready = self.qzss_dcr_ready()
                    for message in messages:
                        if ready:
                            self.ingest_qzss_dcr(
                                message.to_azarashi_packet(reconstruct_crc=True),
                                datetime.fromtimestamp(
                                    message.received_at, timezone.utc
                                ),
                            )
                        elif self._qzss_dcr_active and not self.qzss_dcr_changing:
                            self.qzss_dcr_counters["time_untrusted"] += 1
                    dropped = self.dev.dcreports_dropped
                    if dropped > self._dcreports_dropped:
                        app_logger.warning(
                            f"[CXD56xx] DCR queue overflow: +{dropped - self._dcreports_dropped}"
                        )
                    self._dcreports_dropped = dropped
                    ret = self.dev.peek()
                    if ret == 0:
                        ts = self.dev.timestamp
                        self._qzss_dcr_clock.observe_gnss(ts)
                        gps_time = (
                            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                            if ts is not None
                            else None
                        )
                        await self.get_basic_values(
                            self.dev.lat,
                            self.dev.lon,
                            self.dev.alt,
                            self.dev.speed,
                            self.dev.track,
                            self.dev.mode,
                            self.dev.status,
                            None,
                            (self.dev.pdop, self.dev.hdop, self.dev.vdop),
                            (self.dev.used_sats, self.dev.total_sats),
                            gps_time,
                        )
                    elif ret != -errno.EAGAIN:
                        raise OSError(-ret, "CXD56xx snapshot failed")
                except OSError as exc:
                    # Session errors are OSErrors; all read/startup failures require reopening.
                    self.qzss_dcr_status.update(status="error", error=str(exc))
                    app_logger.warning(f"[CXD56xx] Session unavailable: {exc}")
                    async with self._qzss_dcr_lock:
                        await self._close_device()
                    await asyncio.sleep(1.0)
                    continue
                self.get_sleep_time(self.config.G_GPS_INTERVAL)
                await self.sleep()
        finally:
            async with self._qzss_dcr_lock:
                await self._close_device()
            await self.stop_qzss_dcr()

    async def set_qzss_dcr_enabled(self, enabled):
        async with self._qzss_dcr_lock:
            if self.dev is None or self.quit_status:
                return False
            from cxd56xx_gnss import CXD56xxSessionError

            self.qzss_dcr_changing = True
            try:
                if enabled and not self._qzss_dcr_decoder_available:
                    await self.start_qzss_dcr()
                await self.device_call(self.dev.set_qzss_dcr_enabled, enabled)
            except OSError as exc:
                self.qzss_dcr_status.update(status="error", error=str(exc))
                if isinstance(exc, CXD56xxSessionError):
                    await self._close_device()
                return False
            except asyncio.CancelledError:
                # Restore the last committed setting through a fresh session.
                await self._close_device()
                raise
            else:
                self.finish_qzss_dcr_change(enabled)
                return True
            finally:
                self.qzss_dcr_changing = False

    async def quit(self):
        self.quit_status = True
        if (
            self._update_task is not None
            and self._update_task is not asyncio.current_task()
        ):
            self._update_task.cancel()
            await asyncio.gather(self._update_task, return_exceptions=True)
        else:
            async with self._qzss_dcr_lock:
                await self._close_device()
            await self.stop_qzss_dcr()
        await super().quit()


class CXD56xx_GPS(CXD56xxGPSBase):
    def _create_device(self, enabled):
        from cxd56xx_gnss import CXD56xx

        return CXD56xx(qzss_dcr_enabled=enabled)


class UARTCXD56xxGPS(CXD56xxGPSBase):
    WAIT_READY = False

    def __init__(self, config, values, *, device, baudrate, rtscts):
        self.device = device
        self.baudrate = baudrate
        self.rtscts = rtscts
        super().__init__(config, values)
        # The Android host owns system time and timezone.
        self.is_fixed = True

    def _create_device(self, enabled):
        from cxd56xx_gnss import CXD56xxUART

        return CXD56xxUART(
            self.device,
            baudrate=self.baudrate,
            rtscts=self.rtscts,
            qzss_dcr_enabled=enabled,
        )

    def get_utc_time(self, gps_time, mode=None):
        if gps_time is not None:
            stamp = datetime.fromisoformat(gps_time)
            self.values["time"] = stamp.strftime(self.datetime_format)
            self.values["utctime"] = stamp
