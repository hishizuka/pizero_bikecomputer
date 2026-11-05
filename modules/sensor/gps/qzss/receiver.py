import asyncio
import time
from functools import cached_property

from modules.app_logger import app_logger
from .clock import QzssDcrClock
from .area import QzssDcrAreaResolver
from .dcr import build_qzss_dcr_test_event, decode_report, report_to_dcr
from .store import QzssDcrStore


class QzssDcrSupport:
    supports_qzss_dcr = True

    def init_qzss_dcr(self):
        self.qzss_dcr_status = {"status": "pending", "error": None}
        self.qzss_dcr_counters = {"decode_rejected": 0, "time_untrusted": 0}
        self.qzss_dcr_changing = False
        self._qzss_dcr_active = False
        self._qzss_dcr_lock = asyncio.Lock()
        self._qzss_dcr_clock = QzssDcrClock()
        self._qzss_dcr_generation = self._qzss_dcr_clock.generation
        self._qzss_dcr_clock_task = None
        self._qzss_dcr_decoder_available = False

    @cached_property
    def qzss_dcr_store(self):
        return QzssDcrStore()

    async def start_qzss_dcr(self):
        if self._qzss_dcr_clock_task is None:
            self._qzss_dcr_clock_task = asyncio.create_task(self._qzss_dcr_clock.run())
        try:
            # Loading the decoder is optional for positioning and relatively expensive.
            await asyncio.to_thread(self._load_qzss_decoder)
        except ImportError as exc:
            app_logger.warning(
                "[QZSS DCR] Install azarashi>=0.17.1 to decode reports: %s", exc
            )
            self.qzss_dcr_status["error"] = f"azarashi>=0.17.1 is required: {exc}"
        else:
            self._qzss_dcr_decoder_available = True
            if self.qzss_dcr_store.area_resolver is None:
                self.qzss_dcr_store.area_resolver = await asyncio.to_thread(
                    QzssDcrAreaResolver
                )

    @staticmethod
    def _load_qzss_decoder():
        from azarashi import AzarashiReadOn

        return AzarashiReadOn

    async def stop_qzss_dcr(self):
        if self._qzss_dcr_clock_task is not None:
            self._qzss_dcr_clock_task.cancel()
            await asyncio.gather(self._qzss_dcr_clock_task, return_exceptions=True)
            self._qzss_dcr_clock_task = None
        if any(self.qzss_dcr_counters.values()):
            app_logger.info(f"[QZSS DCR] session counts: {self.qzss_dcr_counters}")

    def qzss_dcr_ready(self):
        trusted = self._qzss_dcr_clock.check()
        generation = self._qzss_dcr_clock.generation
        boundary = generation != self._qzss_dcr_generation
        self._qzss_dcr_generation = generation
        return (
            trusted
            and not boundary
            and self._qzss_dcr_active
            and not self.qzss_dcr_changing
            and self._qzss_dcr_decoder_available
        )

    def ingest_qzss_dcr(self, packet, received_at):
        from azarashi import AzarashiReadOn

        if packet[1] not in (0x53, 0x9A, 0xC6):
            self.qzss_dcr_counters["decode_rejected"] += 1
            return None
        try:
            report = decode_report(packet, "net", received_at)
        except AzarashiReadOn:
            self.qzss_dcr_counters["decode_rejected"] += 1
            return None
        dcr = report_to_dcr(report)
        if dcr["is_null_message"]:
            return None
        result = self.qzss_dcr_store.ingest(dcr, received_at=received_at)
        if result["is_new_content"]:
            app_logger.info(f"[QZSS DCR] {dcr['sentence']}")
            app_logger.info(f"[QZSS DCR] text:\n{dcr['report_text']}")
        return result["event"]

    def inject_qzss_dcr_test_event(self, alert_level="urgent"):
        dcr = build_qzss_dcr_test_event(time.time_ns(), alert_level)
        result = self.qzss_dcr_store.ingest(dcr, received_at=dcr["timestamp"])
        app_logger.info(f"[QZSS DCR][TEST] injected id={result['event']['id']}")
        return result["event"]

    def finish_qzss_dcr_change(self, enabled):
        self._qzss_dcr_active = bool(enabled)
        self.qzss_dcr_status.update(
            status="enabled" if enabled else "disabled", error=None
        )
        if not enabled:
            self.qzss_dcr_store.clear_pending_popups()

    @staticmethod
    async def device_call(function, *args, **kwargs):
        # Cancellation must not abandon a device operation that still owns hardware.
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError as cancelled:
            try:
                await task
            finally:
                raise cancelled
