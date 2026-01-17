import struct
from datetime import datetime
import array
import asyncio
import threading
from enum import StrEnum

from modules.app_logger import app_logger
from . import ant_device


class LightState(StrEnum):
    OFF = "OFF"
    ON = "ON"
    AUTO = "AUTO"


class ANT_Device_Light(ant_device.ANT_Device):
    ant_config = {
        "interval": (4084, 16336, 32672),  # 4084 / 8168 / 16336 / 32672
        "type": 0x23,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    elements = ()
    page_34_count = 0
    # Bike Lights profile Rev 2.0 (section 5.4.1) suggests retrying a command
    # (using the same sequence number) if the sequence number in Data Page 1
    # does not match the sequence number that was sent.
    light_retry_timeout = 1.0  # [s]
    light_retry_max = 3
    auto_light_min_duration = 5  # [s]
    ack_retry_max = 3
    ack_retry_backoff = (1.0, 2.0, 6.0)

    light_modes = {
        "bontrager_flare_rt": {
            "OFF": (0, 0x01),
            "STEADY_HIGH": (1, 0x06),  # mode 1, 4.5 hours
            "STEADY_MID": (5, 0x16),  # mode 5, 13.5 hours
            "FLASH_HIGH": (7, 0x1E),  # mode 7, 6 hours
            "FLASH_MID": (8, 0x22),  # mode 8, 12 hours
            "FLASH_LOW": (63, 0xFE),  # mode 63, 15 hours
        },
    }
    light_name = "bontrager_flare_rt"
    default_on_mode = "FLASH_LOW"

    battery_levels = {
        0x00: "Not Use",
        0x01: "New/Full",
        0x02: "Good",
        0x03: "OK",
        0x04: "Low",
        0x05: "Critical",
        0x06: "Charging",
        0x07: "Invalid",
    }

    state_lock = None
    _pending_light_setting = None

    def _ensure_lock(self):
        if self.state_lock is None:
            self.state_lock = threading.RLock()
        return self.state_lock

    pickle_key = "ant+_lgt_values"

    def set_timeout(self):
        self.channel.set_search_timeout(self.timeout)

    def setup_channel_extra(self):
        # 0:-18 dBm, 1:-12 dBm, 2:-6 dBm, 3:0 dBm, 4:N/A
        self.channel.set_channel_tx_power(0)

        # Protect shared state across ANT callback thread and UI/auto threads.
        self.state_lock = self._ensure_lock()

        # All light control messages go through a single queue/loop to keep
        # ordering and sequence numbers consistent.
        self.send_queue = asyncio.Queue()
        asyncio.create_task(self.send_worker())

    def _queue_send(self, payload):
        """Enqueue payload on the configured event loop in a thread-safe way."""
        loop = getattr(self.config, "loop", None)
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.send_queue.put(payload), loop)
        else:
            asyncio.create_task(self.send_queue.put(payload))

    @staticmethod
    def format_list(l):
        return "[" + " ".join(map(lambda a: str.format("{0:02x}", a), l)) + "]"

    async def send_worker(self):
        while True:
            data = await self.send_queue.get()
            if data is None:
                break
            send_ok = False
            for attempt in range(self.ack_retry_max):
                try:
                    # openant's acknowledged send can block; run it in a worker thread
                    # to keep the main asyncio loop responsive (e.g., MCP230xx buttons).
                    loop = asyncio.get_running_loop()
                    send_ok = await loop.run_in_executor(
                        None, self.channel.send_acknowledged_data_with_retry, data
                    )
                except Exception as e:
                    app_logger.error(f"{e}")
                    send_ok = False

                if send_ok:
                    break

                backoff = self.ack_retry_backoff[min(attempt, len(self.ack_retry_backoff) - 1)]
                app_logger.error(
                    f"ANT+ light ack failed (attempt {attempt + 1}/{self.ack_retry_max}), backoff {backoff}s: {self.format_list(data)}"
                )
                await asyncio.sleep(backoff)

            if not send_ok:
                app_logger.error(
                    f"ANT+ light acknowledged_data retry exhausted: {self.format_list(data)}"
                )
            self.send_queue.task_done()

    def reset_value(self):
        lock = self._ensure_lock()
        with lock:
            self.values["pre_light_mode"] = None
            self.values["light_mode"] = None
            self.values["light_state"] = self._default_light_state()
            self.values["button_state"] = False
            self.values["auto_state"] = self.values["light_state"] == LightState.AUTO
            self.values["changed_timestamp"] = None
            self.values["auto_on_timestamp"] = None
            self._pending_light_setting = None
            self._auto_requested_on = False
            self._auto_last_on = None
            self._manual_on_mode = self.default_on_mode
            self._auto_on_mode = self.default_on_mode

    def _default_light_state(self):
        if self.config.G_ANT["USE_AUTO_LIGHT"]:
            return LightState.AUTO
        return LightState.OFF

    def close_extra(self):
        self.send_disconnect_light()
        if self.ant_state == "quit":
            asyncio.create_task(self.send_queue.put(None))
        self.reset_value()

    def init_after_connect(self):
        if (
            self.values["pre_light_mode"] is None
            and self.values["light_mode"] is None
            and self.ant_state in ["connect_ant_sensor"]
        ):
            self.send_connect_light()

    def get_light_mode(self, m):
        for k, v in self.light_modes[self.light_name].items():
            if m == v[0]:
                return k

    def on_data(self, data):
        resend_mode = None
        if data[0] == 0x01:
            mode = self.get_light_mode(data[6] >> 2)
            seq_no = data[4]
            lock = self._ensure_lock()
            with lock:
                self.battery_status = self.battery_levels[data[2] >> 5]
                # Data Page 1 (Table 7-3): Light Type is 3 bits (2:4)
                self.light_type = (data[2] >> 2) & 0b00111

                pending = self._pending_light_setting
                if pending is not None:
                    if seq_no == pending["seq_no"]:
                        # The command was received by the light. If the mode still
                        # doesn't match, avoid repeatedly forcing a state; the spec
                        # warns about conflicting controllers (section 5.4.1).
                        if mode != pending["mode"]:
                            app_logger.warning(
                                "ANT+ light command observed but state mismatch: "
                                f"requested={pending['mode']}, actual={mode}, "
                                f"seq_no={seq_no}"
                            )
                        self._pending_light_setting = None
                    else:
                        time_delta = (datetime.now() - pending["last_sent"]).total_seconds()
                        if time_delta > self.light_retry_timeout:
                            if pending["retry_count"] >= self.light_retry_max:
                                app_logger.error(
                                    "ANT+ light command retry exhausted: "
                                    f"requested={pending['mode']}, "
                                    f"rx_seq_no={seq_no}, tx_seq_no={pending['seq_no']}"
                                )
                                self._pending_light_setting = None
                            else:
                                app_logger.info(
                                    "Retry ANT+ light command due to seq mismatch: "
                                    f"requested={pending['mode']}, actual={mode}, "
                                    f"rx_seq_no={seq_no}, tx_seq_no={pending['seq_no']}, "
                                    f"time_delta={round(time_delta, 2)}s"
                                )
                                resend_mode = pending["mode"]
        elif data[0] == 0x02:
            pass
        # Common Data Page 80 (0x50): Manufacturer’s Information
        elif data[0] == 0x50 and not self.values["stored_page"][0x50]:
            self.setCommonPage80(data, self.values)
        # Common Data Page 81 (0x51): Product Information
        elif data[0] == 0x51 and not self.values["stored_page"][0x51]:
            self.setCommonPage81(data, self.values)

        if resend_mode is not None:
            self.send_light_setting_on_data(resend_mode)

    def _build_light_setting_payload(self, mode, seq_no):
        light_code = self.light_modes[self.light_name][mode][1]
        return array.array(
            "B",
            [
                0x22,
                0x01,
                0x28,
                seq_no,
                0x5A,
                0x10,
                light_code,
                0xFF,  # No beam adjustment (Table 7-39)
            ],
        )

    def send_connect_light(self):
        self._queue_send(
            array.array(
                "B",
                struct.pack(
                    "<BBBBBHB",
                    0x21,
                    0x01,
                    0xFF,
                    0x5A,
                    0b01001000,
                    self.config.G_ANT["ID"][self.name],
                    0x00,
                ),
            )
        )
        # 5th field:
        #  ON:  0b01010000 (0x50): steady
        #       0b01011000 (0x58): steady
        #  OFF: 0b01001000 (0x48): off
        self.values["pre_light_mode"] = "OFF"
        self.values["light_mode"] = "OFF"

    def send_disconnect_light(self):
        self.channel.send_acknowledged_data_with_retry(
            array.array("B", [0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        )

    def send_light_setting(self, mode):
        lock = self._ensure_lock()
        with lock:
            self.page_34_count = (self.page_34_count + 1) % 256
            seq_no = self.page_34_count
            now = datetime.now()
            self.values["changed_timestamp"] = now
            self._pending_light_setting = {
                "mode": mode,
                "seq_no": seq_no,
                "retry_count": 0,
                "last_sent": now,
            }

        payload = self._build_light_setting_payload(mode, seq_no)
        self._queue_send(payload)

    def send_light_setting_on_data(self, mode):
        lock = self._ensure_lock()
        with lock:
            pending = self._pending_light_setting
            if pending is None or pending["mode"] != mode:
                # Mode changed while a retry was queued; drop the retry.
                return
            pending["retry_count"] += 1
            pending["last_sent"] = datetime.now()
            seq_no = pending["seq_no"]

        payload = self._build_light_setting_payload(mode, seq_no)
        self._queue_send(payload)

    def send_light_mode(self, mode, auto=False):
        if auto:
            self._handle_auto_command(mode)
        else:
            self._handle_manual_command(mode)

    def _handle_manual_command(self, mode):
        if mode == "ON_OFF_FLASH_LOW":
            lock = self._ensure_lock()
            with lock:
                current = self.values.get("light_state", LightState.OFF)
            if current == LightState.OFF:
                self._manual_on_mode = self.default_on_mode
                next_state = LightState.ON
            elif current == LightState.ON:
                if self.config.G_ANT["USE_AUTO_LIGHT"]:
                    next_state = LightState.AUTO
                else:
                    next_state = LightState.OFF
            else:
                next_state = LightState.OFF
            self.set_light_state(next_state)
            lock = self._ensure_lock()
            with lock:
                state = self.values.get("light_state", LightState.OFF)
            # app_logger.info(f"ANT+ light manual button state: {state}")
            return

        if mode == "OFF":
            self.set_light_state(LightState.OFF)
            return

        if mode in self.light_modes[self.light_name]:
            self._manual_on_mode = mode
        else:
            self._manual_on_mode = self.default_on_mode
        self.set_light_state(LightState.ON)

    def _handle_auto_command(self, mode):
        auto_on = mode != "OFF"
        lock = self._ensure_lock()
        with lock:
            self._auto_requested_on = auto_on
            if auto_on:
                self._auto_last_on = datetime.now()
                self.values["auto_on_timestamp"] = self._auto_last_on
                if mode in self.light_modes[self.light_name]:
                    self._auto_on_mode = mode
        self._apply_light_state()

    def set_light_state(self, state):
        normalized = self._normalize_state(state)
        if normalized is None:
            return
        lock = self._ensure_lock()
        with lock:
            if self.values.get("light_state") == normalized:
                return
            self.values["light_state"] = normalized
            self.values["auto_state"] = normalized == LightState.AUTO
            self.values["button_state"] = normalized == LightState.ON
        self._apply_light_state()

    def _normalize_state(self, state):
        if state is None:
            return None
        try:
            return LightState(state)
        except (ValueError, TypeError):
            return None

    def _auto_should_on(self):
        lock = self._ensure_lock()
        with lock:
            requested_on = self._auto_requested_on
            last_on = self._auto_last_on
        if requested_on:
            return True
        if last_on is None:
            return False
        elapsed = (datetime.now() - last_on).total_seconds()
        return elapsed < self.auto_light_min_duration

    def _resolve_desired_mode(self):
        lock = self._ensure_lock()
        with lock:
            state = self.values.get("light_state", LightState.OFF)
            manual_on_mode = self._manual_on_mode
            auto_on_mode = self._auto_on_mode
        if state == LightState.OFF:
            return "OFF"
        if state == LightState.ON:
            return manual_on_mode
        if state == LightState.AUTO:
            if not self.config.G_ANT["USE_AUTO_LIGHT"]:
                return "OFF"
            return auto_on_mode if self._auto_should_on() else "OFF"
        return "OFF"

    def _apply_light_state(self):
        desired_mode = self._resolve_desired_mode()
        if desired_mode not in self.light_modes[self.light_name]:
            desired_mode = "OFF"
        lock = self._ensure_lock()
        with lock:
            self.values["light_mode"] = desired_mode
        self.change_light_mode()

    def change_light_mode(self):
        lock = self._ensure_lock()
        with lock:
            if (
                self.values["light_mode"] is not None
                and self.values["light_mode"] != self.values["pre_light_mode"]
            ):
                self.values["pre_light_mode"] = self.values["light_mode"]
                mode = self.values["light_mode"]
            else:
                return

        self.send_light_setting(mode)
