import asyncio
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone

from modules.app_logger import app_logger

from .base import (
    NMEA_MODE_2D,
    NMEA_MODE_3D,
    NMEA_MODE_NO_FIX,
    NMEA_MODE_UNKNOWN,
    AbstractSensorGPS,
)

_OPTIONAL_DEPENDENCIES = {"serial", "pyubx2", "pynmeagps"}
_UBLOX_IMPORT_ERROR = None

try:
    import serial
    from pyubx2 import (
        ERR_IGNORE,
        POLL,
        SET_LAYER_RAM,
        TXN_NONE,
        UBXMessage,
        UBXReader,
        UBX_PROTOCOL,
    )
    from pyubx2.ubxhelpers import process_monver

    from .ublox_support.assistnow import AssistNowClient
    from .ublox_support.power_save import (
        STATE_RECEIVER_MODEL as _STATE_RECEIVER_MODEL,
        full_power_config,
        low_power_config_for_receiver,
        normalized_receiver_model,
    )
    from .ublox_support.qzss_dcr import (
        build_qzss_dcr_event,
        build_qzss_dcr_test_event,
        parse_qzqsm_sentence,
        qzss_dcr_blocked_by_power_save,
        qzss_dcr_cfg_data,
        qzss_dcr_configure_status,
        qzss_dcr_enabled,
        qzss_dcr_output_status,
        sfrbx_to_qzqsm,
    )
    from .ublox_support.transport import (
        I2CStream,
        I2C_ADDRESS as _I2C_ADDRESS,
        I2C_BUS as _I2C_BUS,
        READ_TIMEOUT as _READ_TIMEOUT,
        UART_BAUDRATE as _UART_BAUDRATE,
        detect_sensor_ublox as _detect_sensor_ublox,
        is_interrupted_system_call as _is_interrupted_system_call,
        retry_interrupted_system_call as _retry_interrupted_system_call,
    )
    from .ublox_support.tx_ready import TxReadyLine
except ModuleNotFoundError as exc:
    missing_dependency = (exc.name or "").split(".", maxsplit=1)[0]
    if missing_dependency not in _OPTIONAL_DEPENDENCIES:
        raise
    _UBLOX_IMPORT_ERROR = exc

_POLL_INTERVAL = 0.05
_INFO_POLL_ATTEMPTS = 3
_INFO_POLL_INTERVAL = 0.15
_WRITE_QUEUE_WAIT_TIMEOUT = 10.0
_ASSISTNOW_CACHE_FALLBACK_DELAY = 30.0
_I2C_CONFIG_MESSAGE_MAX_LENGTH = 32
_I2C_CONFIG_CHUNK_DELAY = 0.02


if _UBLOX_IMPORT_ERROR is None:
    _SENSOR_GPS_UBLOX, _DETECTED_UART_DEVICE = _detect_sensor_ublox()
else:
    _SENSOR_GPS_UBLOX, _DETECTED_UART_DEVICE = False, None


class UBlox(AbstractSensorGPS):
    NULL_VALUE = None

    def sensor_init(self):
        super().sensor_init()
        if _UBLOX_IMPORT_ERROR is not None:
            raise RuntimeError(
                "u-blox GPS optional dependency is not available: "
                f"{_UBLOX_IMPORT_ERROR.name}"
            ) from _UBLOX_IMPORT_ERROR
        self.uart_device = _DETECTED_UART_DEVICE
        self.transport = None
        self.transport_type = None
        self._reader = None
        self._write_queue = queue.Queue()
        self._read_loop_active = False
        self._transport_open_time = None
        self._dop = (99.0, 99.0, 99.0)
        self._used_sats = 0
        self._total_sats = 0
        self._last_dcr_sentence = None
        self._raw_mon_ver = None
        self._raw_sec_uniqid = None
        self._receiver_model = None
        self._has_fix = False
        self._power_save_applied = False
        self._power_save_applying = False
        self._periodic_output_configured = False
        self._sec_uniqid_poll_sent = False
        self._last_mon_ver_poll = 0.0
        self._tx_ready_line = None
        self._tx_ready_configured = False
        assistnow_config = self.config.G_GPS_UBLOX["ASSISTNOW"]
        self._assistnow_client = AssistNowClient(
            assistnow_config,
            self.config.state,
            self.config.api,
        )
        self._assistnow_task = None
        self._assistnow_skip_logged = False
        self._qzss_dcr_power_save_skip_logged = False
        self.receiver_info = {
            "model": None,
            "transport": None,
        }
        self.assistnow_status = {
            "status": self._initial_assistnow_status(),
            "messages": None,
            "bytes": None,
            "error": None,
        }
        self.power_save_status = {
            "status": "pending" if self._power_save_enabled() else "disabled",
            "mode": None,
            "error": None,
        }
        self.qzss_dcr_status = {
            "status": self._qzss_dcr_configure_status(),
        }
        self.tx_ready_status = {
            "status": "pending" if self._tx_ready_requested() else "disabled",
            "gpio": self.config.G_GPS_UBLOX["TX_READY"]["GPIO"],
            "error": None,
        }
        self.latest_qzss_dcr = None
        self.latest_qzss_dcr_sentence = None
        self.latest_qzss_dcr_event = None
        self.qzss_dcr_history = deque(maxlen=20)
        self._qzss_dcr_event_seq = 0

    async def quit(self):
        await super().quit()
        if self._assistnow_task is not None:
            self._assistnow_task.cancel()
        self._close_transport()

    async def update(self):
        while not self.quit_status:
            try:
                self._open_transport()
                self._configure_receiver()
                await self._read_loop()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                app_logger.error(f"[UBlox] {exc}")
                self._close_transport()
                await asyncio.sleep(1.0)

    def _open_transport(self):
        if self.transport is not None:
            return

        try:
            if self.uart_device:
                self.transport = serial.Serial(
                    self.uart_device,
                    _UART_BAUDRATE,
                    timeout=_READ_TIMEOUT,
                    write_timeout=0.5,
                )
                self.transport_type = "uart"
            else:
                self.transport = I2CStream(_I2C_BUS, _I2C_ADDRESS, _READ_TIMEOUT)
                self.transport_type = "i2c"
            self.receiver_info["transport"] = self._transport_name()
            self._reader = UBXReader(
                self.transport,
                protfilter=UBX_PROTOCOL,
                quitonerror=ERR_IGNORE,
            )
            app_logger.info(f"[UBlox] connected via {self._transport_name()}")
            self._reset_receiver_state()
            self._transport_open_time = time.monotonic()
        except Exception:
            self._close_transport()
            raise

    def _close_transport(self):
        if self.transport is None:
            return
        try:
            self._restore_i2c_tx_ready()
            self.transport.close()
        except Exception:
            app_logger.exception("[UBlox] failed to close transport")
        finally:
            self._close_tx_ready_line()
            self._reader = None
            self.transport = None
            self.transport_type = None
            self.receiver_info["transport"] = None
            self._transport_open_time = None
            self._clear_write_queue(RuntimeError("receiver transport is closed"))
            self._reset_receiver_state()

    def _reset_receiver_state(self):
        self._raw_mon_ver = None
        self._raw_sec_uniqid = None
        self._receiver_model = None
        self._has_fix = False
        self.receiver_info["model"] = None
        self._power_save_applied = False
        self._power_save_applying = False
        self._periodic_output_configured = False
        self._sec_uniqid_poll_sent = False
        self._last_mon_ver_poll = 0.0
        self._tx_ready_configured = False

    def _read_transport(self):
        try:
            return _retry_interrupted_system_call(self._reader.read)
        except Exception as exc:
            if _is_interrupted_system_call(exc):
                return None, None
            raise

    def _write_transport_now(self, data):
        if self.transport is None:
            raise RuntimeError("receiver transport is closed")
        _retry_interrupted_system_call(self.transport.write, data)
        flush = getattr(self.transport, "flush", None)
        if flush is not None:
            _retry_interrupted_system_call(flush)

    def _write_transport(self, data, delay=0.0, wait=False, direct=False):
        if self.transport is None:
            raise RuntimeError("receiver transport is closed")
        if direct or not self._read_loop_active:
            self._write_transport_now(data)
            if delay:
                time.sleep(delay)
            return

        done = threading.Event() if wait else None
        item = {
            "data": bytes(data),
            "delay": delay,
            "done": done,
            "future": None,
            "error": None,
        }
        self._write_queue.put(item)
        if not wait:
            return
        if not done.wait(_WRITE_QUEUE_WAIT_TIMEOUT):
            raise TimeoutError("u-blox write queue timed out")
        if item["error"] is not None:
            raise item["error"]

    def _queue_write_future(self, data, delay=0.0):
        if self.transport is None:
            raise RuntimeError("receiver transport is closed")
        future = asyncio.get_running_loop().create_future()
        self._write_queue.put(
            {
                "data": bytes(data),
                "delay": delay,
                "done": None,
                "future": future,
                "error": None,
            }
        )
        return future

    async def _write_transport_async(self, data, delay=0.0):
        if not self._read_loop_active:
            await asyncio.to_thread(self._write_transport_now, data)
            if delay:
                await asyncio.sleep(delay)
            return
        await self._queue_write_future(data, delay)

    def _complete_write_item(self, item, error=None):
        item["error"] = error
        future = item["future"]
        if future is not None and not future.done():
            loop = future.get_loop()
            if error is None:
                loop.call_soon_threadsafe(future.set_result, None)
            else:
                loop.call_soon_threadsafe(future.set_exception, error)
        done = item["done"]
        if done is not None:
            done.set()

    def _clear_write_queue(self, error):
        while True:
            try:
                item = self._write_queue.get_nowait()
            except queue.Empty:
                return
            self._complete_write_item(item, error)
            self._write_queue.task_done()

    async def _drain_write_queue(self):
        while True:
            try:
                item = self._write_queue.get_nowait()
            except queue.Empty:
                return
            try:
                await asyncio.to_thread(self._write_transport_now, item["data"])
                if item["delay"]:
                    await asyncio.sleep(item["delay"])
                self._complete_write_item(item)
            except Exception as exc:
                self._complete_write_item(item, exc)
            finally:
                self._write_queue.task_done()

    def _config_set_message(self, cfg_data):
        return UBXMessage.config_set(SET_LAYER_RAM, TXN_NONE, cfg_data).serialize()

    def _config_chunks_for_transport(self, cfg_data):
        if self.transport_type != "i2c":
            return [cfg_data]

        chunks = []
        current = []
        for item in cfg_data:
            candidate = current + [item]
            if (
                current
                and len(self._config_set_message(candidate))
                > _I2C_CONFIG_MESSAGE_MAX_LENGTH
            ):
                chunks.append(current)
                current = [item]
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _write_config(self, cfg_data, wait=False, direct=False):
        chunks = self._config_chunks_for_transport(cfg_data)
        for i, chunk in enumerate(chunks):
            delay = _I2C_CONFIG_CHUNK_DELAY if i + 1 < len(chunks) else 0.0
            self._write_transport(
                self._config_set_message(chunk),
                delay=delay,
                wait=wait,
                direct=direct,
            )

    def _write_config_sequence(self, cfg_data, direct=False):
        for cfg_item in cfg_data:
            self._write_config([cfg_item], direct=direct)
            if self.transport_type == "i2c":
                time.sleep(_I2C_CONFIG_CHUNK_DELAY)

    def _clear_pending_input(self):
        if self.transport_type != "uart":
            return
        reset_input_buffer = getattr(self.transport, "reset_input_buffer", None)
        if reset_input_buffer is not None:
            reset_input_buffer()

    def _quiet_uart_output(self, direct=False):
        if self.transport_type != "uart":
            return

        # Keep the 9600 bps UART quiet until MON-VER and SEC-UNIQID are read.
        port = "UART1"
        quiet_cfg_data = [
            (f"CFG_MSGOUT_UBX_NAV_PVT_{port}", 0),
            (f"CFG_MSGOUT_UBX_NAV_DOP_{port}", 0),
            (f"CFG_MSGOUT_UBX_NAV_SAT_{port}", 0),
            (f"CFG_MSGOUT_UBX_RXM_SFRBX_{port}", 0),
        ]
        quiet_message = UBXMessage.config_set(
            SET_LAYER_RAM,
            TXN_NONE,
            quiet_cfg_data,
        ).serialize()
        for i in range(_INFO_POLL_ATTEMPTS):
            self._write_transport(quiet_message, direct=direct)
            if i + 1 < _INFO_POLL_ATTEMPTS:
                time.sleep(0.05)

    def _poll_mon_ver(self, force=False, direct=False):
        if self._raw_mon_ver is not None:
            return
        now = time.monotonic()
        if not force and now - self._last_mon_ver_poll < 2.0:
            return
        self._last_mon_ver_poll = now
        attempts = _INFO_POLL_ATTEMPTS if self.transport_type == "uart" else 1
        for i in range(attempts):
            self._write_transport(
                UBXMessage("MON", "MON-VER", POLL).serialize(),
                direct=direct,
            )
            if i + 1 < attempts:
                time.sleep(_INFO_POLL_INTERVAL)

    def _transport_name(self):
        if self.transport_type == "uart":
            return f"uart:{self.transport.port}@{self.transport.baudrate}"
        return self.transport.name

    def _configure_receiver(self):
        if self.transport is None:
            return

        full_power_attempts = 3 if self.transport_type == "uart" else 1
        self._set_power_mode(False, "startup", attempts=full_power_attempts)
        if self.transport_type == "uart":
            time.sleep(0.5)

        if self.transport_type == "uart":
            self._quiet_uart_output()
            time.sleep(_INFO_POLL_INTERVAL)
            self._clear_pending_input()

        self._configure_i2c_tx_ready()
        self._poll_mon_ver(force=True)

        self.qzss_dcr_status["status"] = self._qzss_dcr_configure_status()
        self._log_qzss_dcr_power_save_skip()

        if not self._assistnow_client.enabled and not self._assistnow_skip_logged:
            app_logger.info("[UBlox] AssistNow disabled")
            self._assistnow_skip_logged = True
        elif (
            not self._assistnow_client.has_credentials
            and not self._assistnow_skip_logged
        ):
            app_logger.info("[UBlox] AssistNow skipped: no ZTP token")
            self._assistnow_skip_logged = True

    def _tx_ready_requested(self):
        return bool(self.config.G_GPS_UBLOX["TX_READY"]["STATUS"])

    def _tx_ready_config(self):
        return self.config.G_GPS_UBLOX["TX_READY"]

    def _close_tx_ready_line(self):
        if self._tx_ready_line is not None:
            self._tx_ready_line.close()
            self._tx_ready_line = None

    def _tx_ready_active_high(self):
        return int(self._tx_ready_config()["POLARITY"]) == 0

    def _i2c_tx_ready_enable_cfg_data(self):
        tx_ready_config = self._tx_ready_config()
        return [
            ("CFG_UART1OUTPROT_NMEA", 0),
            ("CFG_UART1OUTPROT_UBX", 0),
            ("CFG_UART1_ENABLED", 0),
            ("CFG_TXREADY_INTERFACE", int(tx_ready_config["INTERFACE"])),
            ("CFG_TXREADY_PIN", int(tx_ready_config["PIN"])),
            ("CFG_TXREADY_POLARITY", int(tx_ready_config["POLARITY"])),
            ("CFG_TXREADY_THRESHOLD", int(tx_ready_config["THRESHOLD"])),
            ("CFG_TXREADY_ENABLED", 1),
        ]

    def _i2c_tx_ready_restore_cfg_data(self):
        return [
            ("CFG_TXREADY_ENABLED", 0),
            ("CFG_TXREADY_INTERFACE", 0),
            ("CFG_TXREADY_PIN", 0),
            ("CFG_TXREADY_POLARITY", 0),
            ("CFG_TXREADY_THRESHOLD", 0),
            ("CFG_UART1_ENABLED", 1),
            ("CFG_UART1OUTPROT_NMEA", 1),
            ("CFG_UART1OUTPROT_UBX", 1),
        ]

    def _configure_i2c_tx_ready(self):
        if self.transport_type != "i2c":
            self.tx_ready_status["status"] = "disabled_transport"
            self.tx_ready_status["error"] = None
            return
        if not self._tx_ready_requested():
            self.tx_ready_status["status"] = "disabled"
            self.tx_ready_status["error"] = None
            return
        if self._tx_ready_configured:
            return

        tx_ready_config = self._tx_ready_config()
        if tx_ready_config["GPIO"] is None:
            self.tx_ready_status["status"] = "disabled_no_gpio"
            self.tx_ready_status["error"] = None
            app_logger.info("[UBlox] TX_READY disabled: GPIO is not configured")
            return

        try:
            self._tx_ready_line = TxReadyLine(
                tx_ready_config["GPIOCHIP"],
                int(tx_ready_config["GPIO"]),
                active_high=self._tx_ready_active_high(),
            )
            self._write_config_sequence(
                self._i2c_tx_ready_enable_cfg_data(),
                direct=True,
            )
            self.transport.set_tx_ready(self._tx_ready_line)
        except Exception as exc:
            self.tx_ready_status["status"] = "fallback_polling"
            self.tx_ready_status["error"] = str(exc)
            self._close_tx_ready_line()
            app_logger.warning(f"[UBlox] TX_READY unavailable: {exc}")
            return

        self._tx_ready_configured = True
        self.tx_ready_status["status"] = "enabled"
        self.tx_ready_status["error"] = None
        threshold_bytes = int(tx_ready_config["THRESHOLD"]) * 8
        app_logger.info(
            "[UBlox] TX_READY enabled "
            f"(gpio={self._tx_ready_line.name}, "
            f"interface={int(tx_ready_config['INTERFACE'])}, "
            f"pin={int(tx_ready_config['PIN'])}, "
            f"polarity={int(tx_ready_config['POLARITY'])}, "
            f"threshold={threshold_bytes} bytes)"
        )

    def _restore_i2c_tx_ready(self):
        if self.transport_type != "i2c":
            return
        if not self._tx_ready_configured:
            return
        try:
            if self.transport is not None:
                self.transport.set_tx_ready(None)
            self._write_config_sequence(
                self._i2c_tx_ready_restore_cfg_data(),
                direct=True,
            )
        except Exception as exc:
            app_logger.warning(f"[UBlox] TX_READY restore failed: {exc}")
        finally:
            self._tx_ready_configured = False
            self.tx_ready_status["status"] = "restored"

    def _initial_assistnow_status(self):
        if self._assistnow_client.has_credentials:
            return "pending"
        if self._assistnow_client.enabled:
            return "missing_ztp_token"
        return "disabled"

    def set_assistnow_enabled(self, enabled):
        self.config.G_GPS_UBLOX["ASSISTNOW"]["STATUS"] = bool(enabled)
        self._assistnow_skip_logged = False
        if not enabled and self._assistnow_task is not None:
            self._assistnow_task.cancel()
        self.assistnow_status["status"] = self._initial_assistnow_status()
        self.assistnow_status["error"] = None
        return True

    def _power_save_enabled(self):
        return bool(self.config.G_GPS_UBLOX["POWER_SAVE"])

    def _qzss_dcr_requested(self):
        return bool(self.config.G_GPS_UBLOX["QZSS_DCR"])

    def _qzss_dcr_blocked_by_power_save(self):
        return qzss_dcr_blocked_by_power_save(
            self._qzss_dcr_requested(),
            self._power_save_enabled(),
        )

    def _qzss_dcr_enabled(self):
        return qzss_dcr_enabled(
            self._qzss_dcr_requested(),
            self._power_save_enabled(),
        )

    def _qzss_dcr_configure_status(self):
        return qzss_dcr_configure_status(
            self._qzss_dcr_requested(),
            self._power_save_enabled(),
        )

    def _qzss_dcr_output_status(self, enabled):
        return qzss_dcr_output_status(
            enabled,
            self._qzss_dcr_requested(),
            self._power_save_enabled(),
        )

    def _qzss_dcr_cfg_data(self, enabled):
        return qzss_dcr_cfg_data(self.transport_type, enabled)

    async def set_qzss_dcr_enabled(self, enabled):
        return await asyncio.to_thread(
            self._set_qzss_dcr_enabled,
            enabled,
            "menu",
        )

    def _set_qzss_dcr_enabled(self, enabled, reason):
        if self.transport is None:
            self.qzss_dcr_status["status"] = self._qzss_dcr_configure_status()
            return False
        if enabled and self._power_save_enabled():
            self.qzss_dcr_status["status"] = "disabled_power_save"
            self._log_qzss_dcr_power_save_skip()
            return False

        cfg_data = self._qzss_dcr_cfg_data(enabled)
        try:
            self._write_config(cfg_data, wait=True)
        except Exception as exc:
            self.qzss_dcr_status["status"] = "error"
            self.qzss_dcr_status["error"] = str(exc)
            app_logger.warning(f"[UBlox] QZSS DC Report change failed: {exc}")
            return False

        self.qzss_dcr_status["status"] = self._qzss_dcr_output_status(enabled)
        self.qzss_dcr_status["error"] = None
        cfg_summary = ", ".join(f"{key}={value}" for key, value in cfg_data)
        app_logger.info(
            "[UBlox] QZSS DC Report output set " f"({cfg_summary}, {reason})"
        )
        return True

    def _log_qzss_dcr_power_save_skip(self):
        if not self._qzss_dcr_blocked_by_power_save():
            return
        if self._qzss_dcr_power_save_skip_logged:
            return
        app_logger.warning(
            "[UBlox] QZSS DC Report disabled because power save is enabled"
        )
        self._qzss_dcr_power_save_skip_logged = True

    def _poll_sec_uniqid(self, direct=False):
        if not self._assistnow_client.has_credentials:
            return
        if self._raw_sec_uniqid is not None or self._sec_uniqid_poll_sent:
            return

        attempts = _INFO_POLL_ATTEMPTS if self.transport_type == "uart" else 1
        for i in range(attempts):
            self._write_transport(
                UBXMessage("SEC", "SEC-UNIQID", POLL).serialize(),
                direct=direct,
            )
            if i + 1 < attempts:
                time.sleep(_INFO_POLL_INTERVAL)
        self._sec_uniqid_poll_sent = True

    def _maybe_configure_periodic_output(self, direct=False):
        if self._periodic_output_configured:
            return
        if self._receiver_model is None:
            return
        if self._assistnow_client.has_credentials and self._raw_sec_uniqid is None:
            return

        port = "I2C" if self.transport_type == "i2c" else "UART1"
        qzss_dcr_enabled = int(self._qzss_dcr_enabled())
        cfg_data = [
            (f"CFG_MSGOUT_UBX_NAV_PVT_{port}", 1),
            (f"CFG_MSGOUT_UBX_NAV_DOP_{port}", 1),
            (f"CFG_MSGOUT_UBX_NAV_SAT_{port}", 1),
        ]
        cfg_data.extend(self._qzss_dcr_cfg_data(qzss_dcr_enabled))
        self._write_config(cfg_data, direct=direct)
        self._periodic_output_configured = True
        app_logger.info(
            "[UBlox] periodic output configured "
            f"({', '.join(f'{key}={value}' for key, value in cfg_data)})"
        )
        self.qzss_dcr_status["status"] = self._qzss_dcr_output_status(qzss_dcr_enabled)

    def _normalized_receiver_model(self):
        return normalized_receiver_model(self._receiver_model)

    def _cache_receiver_model(self, model):
        if not model:
            return
        self.config.state.set_value(
            _STATE_RECEIVER_MODEL,
            model,
            force_apply=True,
        )

    def _cached_receiver_model(self):
        model = self.config.state.get_value(_STATE_RECEIVER_MODEL, "")
        if not isinstance(model, str) or not model:
            return None
        return model

    def _restore_cached_receiver_model(self):
        if self._receiver_model is not None:
            return True
        if not self._assistnow_client.has_cached_chipcode:
            return False
        model = self._cached_receiver_model()
        if model is None:
            return False
        self._receiver_model = model
        self.receiver_info["model"] = model
        app_logger.warning(f"[UBlox] receiver model restored from cache: {model}")
        return True

    def _set_power_mode(self, low_power, reason, attempts=1, wait=False, direct=False):
        if self.transport is None:
            self.power_save_status["status"] = "no_transport"
            self.power_save_status["error"] = None
            return False

        if low_power:
            mode_name, cfg_data = low_power_config_for_receiver(self._receiver_model)
            if not cfg_data:
                self.power_save_status["status"] = "unsupported"
                self.power_save_status["mode"] = None
                self.power_save_status["error"] = self._receiver_model
                app_logger.warning(
                    "[UBlox] power save unsupported receiver: "
                    f"{self._receiver_model}"
                )
                return False
            status = "enabled"
        else:
            mode_name = "full_power"
            cfg_data = full_power_config()
            status = "full_power" if self._power_save_enabled() else "disabled"

        try:
            message = UBXMessage.config_set(
                SET_LAYER_RAM,
                TXN_NONE,
                cfg_data,
            ).serialize()
            for i in range(attempts):
                self._write_transport(message, wait=wait, direct=direct)
                if i + 1 < attempts:
                    time.sleep(0.05)
        except Exception as exc:
            self._power_save_applying = False
            self.power_save_status["status"] = "error"
            self.power_save_status["error"] = str(exc)
            app_logger.warning(f"[UBlox] power mode change failed: {exc}")
            return False

        self.power_save_status["status"] = status
        self.power_save_status["mode"] = mode_name
        self.power_save_status["error"] = None
        self._power_save_applied = low_power
        self._power_save_applying = False
        cfg_summary = ", ".join(f"{key}={value}" for key, value in cfg_data)
        app_logger.info(
            f"[UBlox] power mode set to {mode_name} " f"({cfg_summary}, {reason})"
        )
        return True

    async def set_power_save_enabled(self, enabled):
        return await asyncio.to_thread(
            self._set_power_save_enabled,
            enabled,
            "menu",
            True,
        )

    def _set_power_save_enabled(self, enabled, reason, wait=False):
        if not enabled:
            return self._set_power_mode(False, reason, wait=wait)
        if self._maybe_apply_power_save(reason, wait=wait):
            return True
        if self.power_save_status["status"] in (
            "pending_model",
            "waiting_assistnow",
            "waiting_fix",
        ):
            app_logger.info(
                "[UBlox] power save deferred "
                f"({self.power_save_status['status']}, {reason})"
            )
            return True
        return False

    def _maybe_apply_power_save(self, reason, direct=False, wait=False):
        if not self._power_save_enabled():
            return False
        if self._power_save_applied or self._power_save_applying:
            return True
        self._restore_cached_receiver_model()
        if self._receiver_model is None:
            self.power_save_status["status"] = "pending_model"
            return False
        if (
            self._assistnow_client.has_credentials
            and self.assistnow_status["status"] != "injected"
        ):
            if self.assistnow_status["status"] == "failed":
                self.power_save_status["status"] = "assistnow_error"
                self.power_save_status["error"] = self.assistnow_status["error"]
                return False
            self.power_save_status["status"] = "waiting_assistnow"
            return False
        if "MAXM10S" in self._normalized_receiver_model() and not self._has_fix:
            self.power_save_status["status"] = "waiting_fix"
            return False
        self._power_save_applying = True
        if self._set_power_mode(True, reason, wait=wait, direct=direct):
            return True
        self._power_save_applying = False
        return False

    async def _read_loop(self):
        self._read_loop_active = True
        try:
            while not self.quit_status:
                if (
                    self._receiver_model is None
                    and time.monotonic() - self._last_mon_ver_poll >= 2.0
                ):
                    if self.transport_type == "uart":
                        self._quiet_uart_output(direct=True)
                        self._clear_pending_input()
                    self._poll_mon_ver(force=True, direct=True)
                self._maybe_start_assistnow()
                await self._drain_write_queue()
                raw, parsed = await asyncio.to_thread(self._read_transport)
                if parsed is not None:
                    await self._handle_reader_message(raw, parsed)
                else:
                    await asyncio.sleep(_POLL_INTERVAL)
        finally:
            self._read_loop_active = False

    async def _handle_reader_message(self, raw, parsed):
        identity = getattr(parsed, "identity", "")
        if identity == "NAV-PVT":
            await self._handle_nav_pvt(parsed)
        elif identity == "NAV-DOP":
            self._handle_nav_dop(parsed)
        elif identity == "NAV-SAT":
            self._handle_nav_sat(parsed)
        elif identity == "RXM-SFRBX":
            self._handle_rxm_sfrbx(parsed)
        elif identity == "MON-VER":
            self._handle_mon_ver(raw, parsed)
        elif identity == "SEC-UNIQID":
            self._handle_sec_uniqid(raw)
        elif identity == "ACK-NAK":
            app_logger.warning(f"[UBlox] UBX command NAK: {parsed}")
        elif identity.startswith("MGA-ACK"):
            app_logger.info(f"[UBlox] AssistNow ACK: {parsed}")

    async def _handle_nav_pvt(self, parsed):
        if parsed.fixType >= 3:
            mode = NMEA_MODE_3D
        elif parsed.fixType == 2:
            mode = NMEA_MODE_2D
        elif parsed.fixType == 0:
            mode = NMEA_MODE_NO_FIX
        else:
            mode = NMEA_MODE_UNKNOWN

        gps_time = None
        if getattr(parsed, "validDate", 0) and getattr(parsed, "validTime", 0):
            gps_time = datetime(
                parsed.year,
                parsed.month,
                parsed.day,
                parsed.hour,
                parsed.min,
                parsed.second,
                tzinfo=timezone.utc,
            ).isoformat()

        pdop = parsed.pDOP
        hdop, vdop = self._dop[1], self._dop[2]
        if hdop >= 99.0:
            hdop = pdop
        if vdop >= 99.0:
            vdop = pdop
        self._dop = (pdop, hdop, vdop)

        await self.get_basic_values(
            parsed.lat,
            parsed.lon,
            parsed.hMSL / 1000.0,
            max(parsed.gSpeed, 0) / 1000.0,
            parsed.headMot % 360,
            mode,
            2 if getattr(parsed, "diffSoln", 0) else 1,
            (
                parsed.hAcc / 1000.0,
                parsed.hAcc / 1000.0,
                parsed.vAcc / 1000.0,
            ),
            self._dop,
            (
                self._used_sats or parsed.numSV,
                self._total_sats or parsed.numSV,
            ),
            gps_time,
        )
        if parsed.fixType >= 3:
            self._has_fix = True
            self._maybe_apply_power_save("first fix", direct=True)

    def _handle_nav_dop(self, parsed):
        self._dop = (parsed.pDOP, parsed.hDOP, parsed.vDOP)

    def _handle_nav_sat(self, parsed):
        num_svs = parsed.numSvs
        used = sum(getattr(parsed, f"svUsed_{i:02d}", 0) for i in range(1, num_svs + 1))
        self._total_sats = num_svs
        self._used_sats = used or self._used_sats

    def inject_qzss_dcr_test_event(self):
        self._qzss_dcr_event_seq += 1
        dcr, dcr_event = build_qzss_dcr_test_event(self._qzss_dcr_event_seq)

        self.latest_qzss_dcr = dcr
        self.latest_qzss_dcr_sentence = dcr["sentence"]
        self.latest_qzss_dcr_event = dcr_event
        self.qzss_dcr_history.appendleft(dcr_event)

        app_logger.info(
            "[QZSS DCR][TEST] injected "
            f"id={self._qzss_dcr_event_seq}, "
            f"title={dcr_event['title']}, "
            f"priority={dcr_event['priority']}"
        )

    def _handle_rxm_sfrbx(self, parsed):
        if not self._qzss_dcr_enabled():
            return

        sentence = sfrbx_to_qzqsm(parsed)
        if not sentence:
            return

        if sentence == self._last_dcr_sentence:
            return
        self._last_dcr_sentence = sentence

        dcr = parse_qzqsm_sentence(sentence)
        if dcr is None:
            return

        received_at = datetime.now().isoformat()
        dcr["timestamp"] = received_at
        self._qzss_dcr_event_seq += 1
        dcr_event = build_qzss_dcr_event(
            dcr,
            event_id=self._qzss_dcr_event_seq,
            received_at=received_at,
        )
        self.latest_qzss_dcr = dcr
        self.latest_qzss_dcr_sentence = sentence
        self.latest_qzss_dcr_event = dcr_event
        self.qzss_dcr_history.appendleft(dcr_event)
        app_logger.info(f"[UBlox] QZSS DC Report: {sentence}")
        if dcr.get("report_text"):
            app_logger.info(f"[UBlox] QZSS DC Report text:\n{dcr['report_text']}")
        elif dcr.get("report_decoder_error"):
            app_logger.warning(
                "[UBlox] QZSS DC Report decode failed: "
                f"{dcr['report_decoder_error']}"
            )

    def _handle_mon_ver(self, raw, parsed):
        if self._raw_mon_ver is not None:
            return
        self._raw_mon_ver = raw
        version = process_monver(parsed)
        model = version["hwversion"] or version["swversion"]
        self._receiver_model = model
        self.receiver_info["model"] = model
        self._cache_receiver_model(model)
        app_logger.info(f"[UBlox] receiver model: {model}")
        if (
            self.transport_type == "i2c"
            and "MAXM10N" in self._normalized_receiver_model()
        ):
            app_logger.warning("[UBlox] MAX-M10N does not have an I2C interface")
        self._poll_sec_uniqid(direct=True)
        self._maybe_start_assistnow()
        self._maybe_configure_periodic_output(direct=True)
        self._maybe_apply_power_save("receiver identified", direct=True)

    def _handle_sec_uniqid(self, raw):
        if self._raw_sec_uniqid is not None:
            return
        self._raw_sec_uniqid = raw
        app_logger.info("[UBlox] SEC-UNIQID received for AssistNow")
        self._maybe_start_assistnow()
        self._maybe_configure_periodic_output(direct=True)

    def _maybe_start_assistnow(self):
        if not self._assistnow_client.has_credentials:
            return
        if self.assistnow_status["status"] == "failed":
            return
        if self.assistnow_status["status"] in ("fetching", "injecting", "injected"):
            return
        if self._assistnow_task is not None and not self._assistnow_task.done():
            return
        use_cached_chipcode = False
        if self._raw_mon_ver is None or self._raw_sec_uniqid is None:
            if not self._assistnow_cache_fallback_ready():
                return
            self._restore_cached_receiver_model()
            use_cached_chipcode = True
            app_logger.warning(
                "[UBlox] AssistNow using cached chipcode "
                "because receiver identity poll is unavailable"
            )
        app_logger.info("[UBlox] AssistNow started")
        self._assistnow_task = asyncio.create_task(
            self._run_assistnow(use_cached_chipcode)
        )

    def _assistnow_cache_fallback_ready(self):
        if self._transport_open_time is None:
            return False
        if (
            time.monotonic() - self._transport_open_time
            < _ASSISTNOW_CACHE_FALLBACK_DELAY
        ):
            return False
        return self._assistnow_client.has_cached_chipcode

    async def _run_assistnow(self, use_cached_chipcode=False):
        try:
            self.assistnow_status["status"] = "fetching"
            app_logger.info("[UBlox] AssistNow fetching")
            if use_cached_chipcode:
                messages = await self._assistnow_client.get_messages()
            else:
                messages = await self._assistnow_client.get_messages(
                    self._raw_sec_uniqid,
                    self._raw_mon_ver,
                )
            self.assistnow_status["status"] = "injecting"
            self.assistnow_status["messages"] = len(messages)
            self.assistnow_status["bytes"] = sum(len(message) for message in messages)
            app_logger.info(
                "[UBlox] AssistNow injecting "
                f"{self.assistnow_status['messages']} messages, "
                f"{self.assistnow_status['bytes']} bytes"
            )
            await self._inject_assistnow_messages(messages)
            self.assistnow_status["status"] = "injected"
            self.assistnow_status["error"] = None
            app_logger.info(
                "[UBlox] AssistNow injected "
                f"{self.assistnow_status['messages']} messages, "
                f"{self.assistnow_status['bytes']} bytes"
            )
            await asyncio.to_thread(
                self._maybe_apply_power_save,
                "AssistNow injected",
                False,
                True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.assistnow_status["status"] = "failed"
            self.assistnow_status["error"] = str(exc)
            if self._power_save_enabled():
                self.power_save_status["status"] = "assistnow_error"
                self.power_save_status["error"] = str(exc)
            app_logger.warning(f"[UBlox] AssistNow failed: {exc}")

    async def _inject_assistnow_messages(self, messages):
        futures = []
        for message in messages:
            if self.transport_type == "uart":
                delay = max(0.01, len(message) * 10 / _UART_BAUDRATE)
            else:
                delay = 0.01

            if self._read_loop_active:
                futures.append(self._queue_write_future(message, delay))
            else:
                await self._write_transport_async(message, delay)

        if futures:
            await asyncio.gather(*futures)
