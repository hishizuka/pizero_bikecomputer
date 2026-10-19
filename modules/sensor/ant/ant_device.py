import array
import asyncio
import struct
import threading
from datetime import datetime

from modules.app_logger import app_logger
from modules.utils.cycling_sensor import (
    MAX_CADENCE_RPM,
    POWER_SPIKE_THRESHOLD,
    SPEED_SPIKE_THRESHOLD,
)

from . import ant_code


class ANT_Device:
    config = None
    node = None
    channel = None
    timeout = 0xFF  # 0xFF #0: disable high priority search mode, 0xFF: infinite search timeout
    values = None
    ant_state = None
    name = ""
    elements = ()
    valid_time = 60
    structPattern = {
        "ID": struct.Struct("<HB"),
        0x50: struct.Struct("<xxxBHH"),
        0x51: struct.Struct("<xxBBL"),
    }
    common_page_elements = (
        "hw_ver",
        "manu_id",
        "manu_name",
        "model_num",
        "sw_ver",
        "serial_num",
        "battery_status",
        "battery_voltage",
        "battery_percentage",
        "operating_time",
        "sw_ver_main",
        "sw_ver_supplemental",
    )
    battery_status = {
        0: "None",
        1: "New",
        2: "Good",
        3: "Ok",
        4: "Low",
        5: "Critical",
        6: "None",
        7: "Invalid",
    }
    # detect spike for excluding erroneous value accumulation
    # (speed -> distance, power -> accumulated_power)
    # spike_threshold is defined by "new value - pre value"
    spike_threshold = {
        "speed": SPEED_SPIKE_THRESHOLD,  # m/s
        "power": POWER_SPIKE_THRESHOLD,  # w
        "cadence": MAX_CADENCE_RPM,  # rpm
    }
    ant_idle_interval = {"NORMAL": 0.20, "QUICK": 0.01, "SCAN": 0.20}
    ant_time_base = 32768
    stop_margin_periods = 2
    stop_missing_events = 1
    metadata_pages = ()
    battery_page = None
    ack_retry_max = 3
    ack_retry_backoff = (1.0, 2.0)

    def __init__(self, node=None, config=None, values=None, name="", auto_connect=True):
        self.node = node
        self.config = config
        self.name = name
        self.init_runtime_state()
        if values is None:
            self.values = {}
        else:
            self.values = values

        self.add_struct_pattern()
        self.init_value()

        if node is None:
            return  # for dummy device
        self.make_channel(self.ant_config["channel_type"])
        try:
            self.init_extra()
            self.ready_connect()
            if auto_connect:
                self.connect(isCheck=True, isChange=False)
        except Exception:
            if self.is_transport_available():
                try:
                    self.delete()
                except Exception as exc:
                    app_logger.warning("ANT+ channel cleanup failed: %s", exc)
            raise

    def init_runtime_state(self):
        self.structPattern = self.structPattern.copy()
        self.send_lock = threading.RLock()
        self._closing = False
        self._metadata_requested = False
        self._metadata_task = None
        self._battery_task = None
        self.last_data_timestamp = None

    def on_data(self):
        pass

    def add_struct_pattern(self):
        pass

    def init_value(self):
        self.set_null_value()
        self.reset_value()

    def init_extra(self):
        pass

    def set_null_value(self):
        for element in self.elements:
            self.values[element] = self.config.G_SENSOR_NULLVALUE
        self.init_common_page_status()

    def init_common_page_status(self):
        for element in self.common_page_elements:
            self.values[element] = self.config.G_SENSOR_NULLVALUE
        self.values["stored_page"] = dict.fromkeys(
            (*self.metadata_pages, 0x50, 0x51, 0x52), False
        )
        self.values["batteries"] = {}

    # reset total value with reset button
    def reset_value(self):
        if (
            self.battery_page is not None
            and self.channel is not None
            and not self._closing
            and self.is_transport_available()
        ):
            self.config.loop.call_soon_threadsafe(self._start_battery_request)

    def _start_battery_request(self):
        if self._closing or self.channel is None or not self.is_transport_available():
            return
        if self._battery_task is None or self._battery_task.done():
            self._battery_task = asyncio.create_task(self.request_battery_status())

    async def request_battery_status(self):
        if self.battery_page is None:
            return False
        return await self.send_acknowledged(self.build_page_request(self.battery_page))

    def set_message_interval(self):
        self.interval = (
            self.ant_config["interval"][self.config.G_ANT["INTERVAL"]]
            / self.ant_time_base
        )

    def get_stop_cutoff(
        self, last_event_interval, margin_periods=None, missing_events=None
    ):
        if last_event_interval is None or last_event_interval <= 0:
            return None
        if margin_periods is None:
            margin_periods = self.stop_margin_periods
        if missing_events is None:
            missing_events = self.stop_missing_events
        return last_event_interval * missing_events + margin_periods * self.interval

    def is_stopped_by_event_age(
        self,
        t,
        last_event_timestamp,
        last_event_interval,
        margin_periods=None,
        missing_events=None,
    ):
        cutoff = self.get_stop_cutoff(
            last_event_interval, margin_periods, missing_events
        )
        if last_event_timestamp is None or cutoff is None:
            return False
        return (t - last_event_timestamp).total_seconds() >= cutoff

    @staticmethod
    def extend_list(values, value_length):
        if len(values) < value_length:
            values.extend([-1] * (value_length - len(values)))

    def make_channel(self, c_type, ext_assign=None):
        if self.config.G_ANT["STATUS"] and self.channel is None:
            self.channel = self.node.new_channel(c_type, ext_assign=ext_assign)
            self.channel.on_broadcast_data = self._on_data
            self.channel.on_burst_data = self._on_data
            self.channel.on_acknowledge_data = self._on_data

    def _on_data(self, data):
        """Record reception before dispatching a packet to the device parser."""
        if len(data) < 8:
            return
        self.last_data_timestamp = datetime.now()
        self.on_data(data)
        if self.metadata_pages and not self._metadata_requested and not self._closing:
            self._metadata_requested = True
            self.config.loop.call_soon_threadsafe(self._start_metadata_request)

    def _start_metadata_request(self):
        if not self._closing:
            self._metadata_task = asyncio.create_task(self.request_device_information())

    @staticmethod
    def build_page_request(page, descriptor1=0xFF, descriptor2=0xFF):
        # Request two broadcast responses; never request sensor-to-display ACKs.
        return array.array(
            "B", [0x46, 0xFF, 0xFF, descriptor1, descriptor2, 2, page, 1]
        )

    def _send_acknowledged(self, payload):
        with self.send_lock:
            if self._closing or not self.is_transport_available():
                return False
            # Own the retry budget here instead of multiplying openant's retries.
            return self.channel.send_acknowledged_data_with_retry(payload, retry_max=1)

    async def send_acknowledged(self, payload):
        for attempt in range(self.ack_retry_max):
            if self._closing or not self.is_transport_available():
                return False
            try:
                if await asyncio.to_thread(self._send_acknowledged, payload):
                    return True
            except Exception as exc:
                app_logger.warning("ANT+ %s send failed: %s", self.name, exc)
            if attempt + 1 < self.ack_retry_max:
                await asyncio.sleep(self.ack_retry_backoff[attempt])
        return False

    async def request_device_information(self):
        if not self.metadata_pages:
            return False
        for page in self.metadata_pages:
            if page not in (4, 7, 0x52) and self.values["stored_page"][page]:
                continue
            if not await self.send_acknowledged(self.build_page_request(page)):
                return False
        return True

    def channel_set_id(self):  # for slave
        self.channel.set_id(
            self.config.G_SENSORS[self.name]["ID"],
            self.ant_config["type"],
            self.ant_config["transmission_type"],
        )

    def ready_connect(self):
        if self.config.G_ANT["STATUS"]:
            self.channel_set_id()
            self.channel.set_period(
                self.ant_config["interval"][self.config.G_ANT["INTERVAL"]]
            )
            self.set_timeout()
            self.channel.set_rf_freq(57)
            self.setup_channel_extra()

    def set_timeout(self):
        # for sending acknowledged messages (e.g.: LIGHT)
        # high priority search is off
        # and low priority search is on
        self.channel.set_search_timeout(0x00)
        self.channel.set_low_priority_search_timeout(self.timeout)

    def setup_channel_extra(self):
        # set_channel_tx_power, etc
        pass

    def connect(self, isCheck=True, isChange=False):
        if not self.is_transport_available():
            return False
        if isCheck:
            if not self.config.sensor_uses(self.name, self.config.SENSOR_PROTOCOL_ANT):
                return False
        if self.state_check("OPEN"):
            return self.is_transport_available()
        if not self.is_transport_available():
            return False
        try:
            self.channel.open()
            self._closing = False
            self._metadata_requested = False
            return self.is_transport_available()
        except Exception as exc:
            app_logger.warning("ANT+ %s channel open failed: %s", self.name, exc)
            return False

    def is_transport_available(self):
        return (
            self.config.G_ANT["STATUS"]
            and self.node is not None
            and not getattr(self.node, "transport_disconnected", False)
        )

    def init_after_connect(self):
        pass

    def disconnect(self, isCheck=True, isChange=False):
        if isCheck:
            if not self.config.sensor_uses(self.name, self.config.SENSOR_PROTOCOL_ANT):
                return
        self._closing = True
        for task in (self._metadata_task, self._battery_task):
            if task is not None:
                self.config.loop.call_soon_threadsafe(task.cancel)
        if not self.is_transport_available():
            return
        if self.state_check("CLOSE"):
            return
        if not self.is_transport_available():
            return
        try:
            with self.send_lock:
                try:
                    self.close_extra()
                finally:
                    self.channel.close()
            if self.is_transport_available():
                self.channel.wait_for_event([0x07])  # EVENT_CHANNEL_CLOSED
        except Exception as exc:
            app_logger.warning("ANT+ %s channel close failed: %s", self.name, exc)

    def delete(self):
        self._closing = True
        if self.channel is None:
            return
        with self.send_lock:
            self.node.delete_channel(self.channel)
            self.channel = None

    def state_check(self, mode):
        channel_state = self.get_channel_state()
        state = False
        if mode == "OPEN" and channel_state in (2, 3):
            state = True
        elif mode == "CLOSE" and channel_state in (0, 1):
            state = True
        return state

    def get_channel_state(self):
        """Return the ANT channel state bits, or None when unavailable."""
        if self.channel is None:
            return None
        try:
            result = self.channel.get_channel_status()
            # Bits 0~1: 0=unassigned, 1=assigned, 2=searching, 3=tracking.
            return result[2][0] & 0b00000011
        except Exception:
            return None

    def close_extra(self):
        pass

    def stop(self):
        self.disconnect(isCheck=True, isChange=False)

    ##############
    # ANT+ pages #
    ##############
    def setCommonPage80(self, data, values):
        values["hw_ver"], values["manu_id"], values["model_num"] = self.structPattern[
            0x50
        ].unpack(data[0:8])
        self.set_manufacturer_name(values)
        values["stored_page"][0x50] = True

    def setCommonPage81(self, data, values):
        sw1, sw2, values["serial_num"] = self.structPattern[0x51].unpack(data[0:8])
        values["sw_ver_main"] = sw2
        values["sw_ver_supplemental"] = (
            sw1 if sw1 != 0xFF else self.config.G_SENSOR_NULLVALUE
        )
        if sw1 != 0xFF:
            values["sw_ver"] = float((sw2 * 100 + sw1) / 1000)
        else:
            values["sw_ver"] = sw2
        if values["serial_num"] == 0xFFFFFFFF:
            values["serial_num"] = self.config.G_SENSOR_NULLVALUE
        values["stored_page"][0x51] = True

    # data is 2byte only (trim from common page 82 and page 4 of speed or cadence only sensor)
    def setCommonPage82(self, data, values):
        values["battery_status"] = self.battery_status[(data[1] >> 4) & 0b111]
        coarse = data[1] & 0x0F
        values["battery_voltage"] = (
            round(coarse + data[0] / 256, 2)
            if coarse != 0x0F
            else self.config.G_SENSOR_NULLVALUE
        )

    def set_battery_page(self, data, values):
        self.setCommonPage82(data[6:8], values)
        values["operating_time"] = int.from_bytes(data[3:6], "little") * (
            2 if data[7] & 0x80 else 16
        )
        if data[2] != 0xFF:
            values["batteries"][data[2] >> 4] = {
                "battery_status": values["battery_status"],
                "battery_voltage": values["battery_voltage"],
                "operating_time": values["operating_time"],
                "battery_count": data[2] & 0x0F,
            }
        values["stored_page"][0x52] = True

    def set_manufacturer_name(self, values):
        values["manu_name"] = ant_code.AntCode.MANUFACTURER.get(
            values["manu_id"], self.config.G_SENSOR_NULLVALUE
        )

    def set_profile_background_page(self, data):
        page = data[0] & 0x7F
        if page == 1:
            self.values["operating_time"] = int.from_bytes(data[1:4], "little") * 2
        elif page == 2:
            self.values["manu_id"] = data[1]
            self.set_manufacturer_name(self.values)
            self.values["serial_num"] = (
                int.from_bytes(data[2:4], "little") << 16
            ) | self.config.G_SENSORS[self.name]["ID"]
        elif page == 3:
            self.values["hw_ver"] = data[1]
            self.values["sw_ver"] = self.values["sw_ver_main"] = data[2]
            self.values["model_num"] = data[3]
        if page in self.metadata_pages:
            self.values["stored_page"][page] = True

    @staticmethod
    def print_spike(device_str, val, pre_val, delta, delta_t):
        app_logger.info(
            f"ANT+ {device_str} spike: {datetime.now().strftime('%Y%m%d %H:%M:%S')}, value:{val:.0f}, pre:{pre_val:.0f}, delta: {delta}, delta_t: {delta_t}"
        )

    def set_wait(self, interval):
        self.node.ant.set_wait(interval)

    # ant_idle_interval = {'NORMAL':0.20, 'QUICK':0.01, 'SCAN': 0.20}
    def set_wait_normal_mode(self):
        self.set_wait(self.ant_idle_interval["NORMAL"])

    def set_wait_quick_mode(self):
        self.set_wait(self.ant_idle_interval["QUICK"])

    def set_wait_scan_mode(self):
        self.set_wait(self.ant_idle_interval["SCAN"])
