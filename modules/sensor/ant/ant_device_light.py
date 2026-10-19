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
    # Control a paired light directly (Bike Lights 5.6), without a shared network.
    ant_config = {
        "interval": (4084, 8168, 16336),  # 4084 for 8.02Hz / 8168 / 16336 / 32672
        "type": 0x23,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    elements = ()
    metadata_pages = (0x50, 0x51, 0x13)
    battery_page = 0x13
    page_34_count = 0
    # Bike Lights profile Rev 2.0 (section 5.4.1) suggests retrying a command
    # (using the same sequence number) if the sequence number in Data Page 1
    # does not match the sequence number that was sent.
    light_retry_timeout = 1.0  # [s]
    auto_light_min_duration = 5  # [s]
    controller_id = 0x5A

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

    pickle_key = "ant+_lgt_values"

    def init_value(self):
        self.state_lock = threading.RLock()
        self._pending_light_setting = None
        self.page_34_count = 0
        self._light_index = 0
        self._send_task = None
        self._workers_stopping = False
        super().init_value()

    def setup_channel_extra(self):
        # All light control messages go through a single queue/loop to keep
        # ordering and sequence numbers consistent.
        self.send_queue = asyncio.Queue()
        self._send_task = asyncio.create_task(self.send_worker())

    def _queue_send(self, payload, pending=None):
        """Enqueue payload on the configured event loop in a thread-safe way."""
        self.config.loop.call_soon_threadsafe(
            self.send_queue.put_nowait, (payload, pending)
        )

    def _send_queued(self, pending):
        # Check in the executor too: a command can become obsolete while waiting.
        with self.send_lock:
            with self.state_lock:
                if self._pending_light_setting is not pending:
                    return
                # Another controller may have formed a network since queuing.
                data = self._build_light_setting_payload(
                    pending["mode"], pending["seq_no"]
                )
                pending["light_index"] = data[1]
            return self._send_acknowledged(data)

    async def send_worker(self):
        while True:
            item = await self.send_queue.get()
            if item is None:
                self.send_queue.task_done()
                break
            data, pending = item
            try:
                if pending is None:
                    sent = await self.send_acknowledged(data)
                    if not sent and not self._closing and self.is_transport_available():
                        app_logger.error(
                            "ANT+ light acknowledged_data retry exhausted: [%s]",
                            bytes(data).hex(" "),
                        )
                    continue
                with self.state_lock:
                    if self._pending_light_setting is not pending:
                        continue
                    pending["response"] = asyncio.Event()
                for attempt in range(self.ack_retry_max):
                    try:
                        # openant waits for a radio event; keep it off the UI loop.
                        await asyncio.to_thread(self._send_queued, pending)
                    except Exception as exc:
                        app_logger.warning("ANT+ light send failed: %s", exc)

                    with self.state_lock:
                        if self._pending_light_setting is not pending:
                            break
                    # ACK loss and missing state share one total send budget.
                    try:
                        await asyncio.wait_for(
                            pending["response"].wait(), self.light_retry_timeout
                        )
                    except TimeoutError:
                        pass
                    with self.state_lock:
                        if self._pending_light_setting is not pending:
                            break
                        if attempt + 1 == self.ack_retry_max:
                            self._finish_pending_setting("failed")
                            app_logger.error(
                                "ANT+ light command retry exhausted: %s",
                                pending["mode"],
                            )
                        else:
                            app_logger.warning(
                                "ANT+ light command unconfirmed (attempt %s/%s): %s",
                                attempt + 1,
                                self.ack_retry_max,
                                pending["mode"],
                            )
            finally:
                self.send_queue.task_done()

    def _finish_pending_setting(self, status):
        with self.state_lock:
            pending = self._pending_light_setting
            self._pending_light_setting = None
            self.values["command_status"] = status
            if pending is not None and pending["response"] is not None:
                self.config.loop.call_soon_threadsafe(pending["response"].set)

    def reset_value(self):
        with self.state_lock:
            self.values["pre_light_mode"] = None
            self.values["light_mode"] = None
            self.values["light_state"] = (
                LightState.AUTO if self.config.G_AUTO_LIGHT else LightState.OFF
            )
            self.values["button_state"] = False
            self.values["auto_state"] = self.values["light_state"] == LightState.AUTO
            self.values["changed_timestamp"] = None
            self.values["auto_on_timestamp"] = None
            self._finish_pending_setting("idle")
            self.values["actual_light_mode"] = None
            self._auto_requested_on = False
            self._manual_on_mode = self.default_on_mode
            self._auto_on_mode = self.default_on_mode
        super().reset_value()

    def close_extra(self):
        self._finish_pending_setting("idle")
        try:
            if self.values["pre_light_mode"] not in (None, "OFF"):
                # Turn off our beam without dismantling another controller's network.
                self.page_34_count = (self.page_34_count + 1) % 256
                self.channel.send_acknowledged_data_with_retry(
                    self._build_light_setting_payload("OFF", self.page_34_count),
                    retry_max=self.ack_retry_max,
                )
        finally:
            if self.ant_state == "quit":
                self._stop_workers()
            self.reset_value()

    def _stop_workers(self):
        if self._workers_stopping:
            return
        self._workers_stopping = True
        self._finish_pending_setting("idle")
        if self._send_task is not None and not self._send_task.done():
            self.config.loop.call_soon_threadsafe(self.send_queue.put_nowait, None)

    def delete(self):
        self._closing = True
        self._stop_workers()
        super().delete()

    def get_light_mode(self, m):
        for k, v in self.light_modes[self.light_name].items():
            if m == v[0]:
                return k

    def on_data(self, data):
        if data[0] == 0x01:
            if data[1] not in (0, 1):
                return
            mode = self.get_light_mode(data[6] >> 2)
            seq_no = data[4]
            with self.state_lock:
                self._light_index = data[1]
                self.values["actual_light_mode"] = mode
                self.values["battery_status"] = self.battery_levels[
                    (data[2] >> 5) & 0b111
                ]
                # Data Page 1 (Table 7-3): Light Type is 3 bits (2:4)
                self.light_type = (data[2] >> 2) & 0b00111

                pending = self._pending_light_setting
                if (
                    pending is not None
                    and data[1] == pending["light_index"]
                    and seq_no == pending["seq_no"]
                ):
                    # A matching sequence confirms receipt, even if another
                    # controller changed the mode (Bike Lights 5.4.1).
                    if mode != pending["mode"]:
                        app_logger.warning(
                            "ANT+ light command observed but state mismatch: "
                            f"requested={pending['mode']}, actual={mode}, "
                            f"seq_no={seq_no}"
                        )
                    self._finish_pending_setting(
                        "success" if mode == pending["mode"] else "state_mismatch"
                    )
        elif data[0] == 0x13 and data[1] == self._light_index and data[2] & 0x07 == 0:
            self.values["battery_percentage"] = (
                data[7] if data[7] <= 100 else self.config.G_SENSOR_NULLVALUE
            )
        # Common Data Page 80 (0x50): Manufacturer’s Information
        elif data[0] == 0x50 and not self.values["stored_page"][0x50]:
            self.setCommonPage80(data, self.values)
        # Common Data Page 81 (0x51): Product Information
        elif data[0] == 0x51 and not self.values["stored_page"][0x51]:
            self.setCommonPage81(data, self.values)

    def _build_light_setting_payload(self, mode, seq_no):
        light_code = self.light_modes[self.light_name][mode][1]
        return array.array(
            "B",
            [
                0x22,
                self._light_index,
                0x28,
                seq_no,
                self.controller_id,
                0x10,
                light_code,
                0xFF,  # No beam adjustment (Table 7-39)
            ],
        )

    def build_page_request(self, page, descriptor1=0xFF, descriptor2=0xFF):
        request = super().build_page_request(page, descriptor1, descriptor2)
        # Common pages have no light index (Bike Lights 7.22.3.1).
        if page == self.battery_page:
            request[1] = self._light_index
        return request

    async def request_battery_status(self):
        if self._closing or not self.is_transport_available():
            return False
        self._queue_send(self.build_page_request(self.battery_page))
        return True

    async def request_device_information(self):
        if self._closing or not self.is_transport_available():
            return False
        for page in self.metadata_pages:
            self._queue_send(self.build_page_request(page))
        return True

    def send_light_setting(self, mode):
        with self.state_lock:
            self._finish_pending_setting("idle")
            self.page_34_count = (self.page_34_count + 1) % 256
            seq_no = self.page_34_count
            self.values["changed_timestamp"] = datetime.now()
            pending = self._pending_light_setting = {
                "mode": mode,
                "seq_no": seq_no,
                "light_index": self._light_index,
                "response": None,
            }
            self.values["command_status"] = "pending"

        payload = self._build_light_setting_payload(mode, seq_no)
        self._queue_send(payload, pending)

    def send_light_mode(self, mode, auto=False):
        if auto:
            with self.state_lock:
                self._auto_requested_on = mode != "OFF"
                if self._auto_requested_on:
                    self.values["auto_on_timestamp"] = datetime.now()
                    if mode in self.light_modes[self.light_name]:
                        self._auto_on_mode = mode
            self._apply_light_state()
        elif mode == "ON_OFF_FLASH_LOW":
            with self.state_lock:
                current = self.values["light_state"]
            if current == LightState.OFF:
                self._manual_on_mode = self.default_on_mode
                next_state = LightState.ON
            elif current == LightState.ON and self.config.G_AUTO_LIGHT:
                next_state = LightState.AUTO
            else:
                next_state = LightState.OFF
            self.set_light_state(next_state)
        elif mode == "OFF":
            self.set_light_state(LightState.OFF)
        else:
            self._manual_on_mode = (
                mode
                if mode in self.light_modes[self.light_name]
                else self.default_on_mode
            )
            self.set_light_state(LightState.ON)

    def set_light_state(self, state):
        try:
            state = LightState(state)
        except (ValueError, TypeError):
            return
        with self.state_lock:
            if self.values["light_state"] == state:
                return
            self.values["light_state"] = state
            self.values["auto_state"] = state == LightState.AUTO
            self.values["button_state"] = state == LightState.ON
        self._apply_light_state()

    def _apply_light_state(self):
        with self.state_lock:
            state = self.values["light_state"]
            desired_mode = "OFF"
            if state == LightState.ON:
                desired_mode = self._manual_on_mode
            elif state == LightState.AUTO and self.config.G_AUTO_LIGHT:
                last_on = self.values["auto_on_timestamp"]
                if self._auto_requested_on or (
                    last_on is not None
                    and (datetime.now() - last_on).total_seconds()
                    < self.auto_light_min_duration
                ):
                    desired_mode = self._auto_on_mode
            if desired_mode not in self.light_modes[self.light_name]:
                desired_mode = "OFF"
            self.values["light_mode"] = desired_mode
        self.change_light_mode()

    def change_light_mode(self):
        with self.state_lock:
            mode = self.values["light_mode"]
            if mode is None or mode == self.values["pre_light_mode"]:
                return
            self.values["pre_light_mode"] = mode
        self.send_light_setting(mode)
