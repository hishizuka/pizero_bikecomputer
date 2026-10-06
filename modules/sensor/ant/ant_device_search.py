import struct
import threading
from datetime import datetime

from modules.app_logger import app_logger

from . import ant_device
from . import ant_device_ctrl


class ANT_Device_Search(ant_device.ANT_Device):
    name = "SEARCH"
    ant_config = {
        "interval": (),  # Not use
        "type": 0,  # ANY
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    isUse = False
    searchList = None
    searchState = False
    mainAntDevice = None
    _ctrl_searcher_owned = False

    def __init__(self, node, config, values=None):
        self.node = node
        self.config = config
        self.antName = None
        self.searchList = {}
        self.searchState = False
        self.ctrl_searcher = None
        self._ctrl_previous_state = None
        self._search_lock = threading.RLock()
        if self.config.G_ANT["STATUS"]:
            # special use of make_channel(c_type, search=False)
            self.make_channel(self.ant_config["channel_type"], ext_assign=0x01)

    def set_main_ant_device(self, device):
        """Set reference to the main ANT device map for reusing channels."""
        self.mainAntDevice = device

    def _find_existing_ctrl_device(self):
        """Find an existing CTRL device instance to reuse its channel when searching."""
        if not self.mainAntDevice:
            return None
        for dv in self.mainAntDevice.values():
            if (
                isinstance(dv, ant_device_ctrl.ANT_Device_CTRL)
                and dv.channel is not None
            ):
                return dv
        return None

    def on_data(self, data):
        with self._search_lock:
            if not self.searchState:
                return
            if len(data) == 13:
                antID, antType = self.structPattern["ID"].unpack(data[9:12])
                if antType in self.config.G_ANT_SENSOR_TYPES[self.antName]:
                    self._add_detected_sensor(antID, antType)

    def on_data_ctrl(self, data):
        with self._search_lock:
            if not self.searchState:
                return
            if len(data) == 8:
                (antID,) = struct.Struct("<H").unpack(data[1:3])
                antType = 0x10
                if antType in self.config.G_ANT_SENSOR_TYPES[self.antName]:
                    self._add_detected_sensor(antID, antType)

    def _add_detected_sensor(self, ant_id, ant_type):
        existing = self.searchList.get(ant_id)
        if existing is not None and existing[1]:
            return
        self.searchList[ant_id] = (ant_type, False)

    def search(self, antName):
        if self.searchState:
            return self.antName == antName
        self.searchList = {}
        for k in self.config.G_SENSORS:
            if k == antName:
                continue
            ant_id_type = self.config.get_ant_id_type(k)
            if ant_id_type:
                antID, antType = struct.unpack("<HB", ant_id_type)
                if antType in self.config.G_ANT_SENSOR_TYPES[antName]:
                    # already connected
                    self.searchList[antID] = (antType, True)

        if not self.is_transport_available():
            return False
        self.antName = antName

        try:
            connected = (
                self._search_ctrl() if antName == "CTRL" else self._search_background()
            )

            with self._search_lock:
                if not connected or not self.is_transport_available():
                    raise RuntimeError("Search channel did not open")
                self.searchState = True
            return True
        except Exception as exc:
            app_logger.warning("ANT+ %s search failed: %s", antName, exc)
            self.stop_search()
            return False

    def _search_background(self):
        for action in [
            self.set_wait_quick_mode,
            lambda: self.channel.set_search_timeout(0),
            lambda: self.channel.set_rf_freq(57),
            lambda: self.channel.set_id(0, 0, 0),
            lambda: self.channel.enable_extended_messages(1),
            lambda: self.channel.set_low_priority_search_timeout(0xFF),
            lambda: self.node.set_lib_config(0x80),
        ]:
            if not self.is_transport_available():
                raise RuntimeError("Transport disconnected during search setup")
            action()
        return self.connect(isCheck=False, isChange=False)

    def _search_ctrl(self):
        # Borrow an existing master channel to preserve the limited channel slots.
        existing = self._find_existing_ctrl_device()
        ctrl = existing or ant_device_ctrl.ANT_Device_CTRL(
            self.node, self.config, {}, "CTRL", auto_connect=False
        )
        with self._search_lock:
            if not self.is_transport_available():
                raise RuntimeError("Transport disconnected during CTRL setup")
            self.ctrl_searcher = ctrl
            self._ctrl_searcher_owned = existing is None
            self._ctrl_previous_state = ctrl.send_data, ctrl.channel.on_acknowledge_data
            ctrl.channel.on_acknowledge_data = self.on_data_ctrl
            ctrl.send_data = True
        return ctrl.connect(isCheck=False, isChange=False)

    def stop_search(self, resetWait=True, transport_available=True):
        with self._search_lock:
            ant_name = self.antName
            self.antName = None
            self.searchState = False
            self.searchList = {}
            ctrl = self.ctrl_searcher
            owned = self._ctrl_searcher_owned
            self.ctrl_searcher = None
            self._ctrl_searcher_owned = False
            if ctrl is not None:
                ctrl.send_data, ctrl.channel.on_acknowledge_data = (
                    self._ctrl_previous_state
                )
            self._ctrl_previous_state = None
        if ant_name is None:
            return

        if ant_name == "CTRL":
            if ctrl is None:
                return
            actions = (
                [lambda: ctrl.disconnect(isCheck=False, isChange=False), ctrl.delete]
                if owned
                else []
            )
        else:
            actions = [
                lambda: self.disconnect(isCheck=False, isChange=False),
                lambda: self.channel.enable_extended_messages(0),
                lambda: self.node.set_lib_config(0x00),
                lambda: self.channel.set_low_priority_search_timeout(0x00),
            ]
            if resetWait:
                actions.append(self.set_wait_normal_mode)

        for action in actions:
            if not transport_available or not self.is_transport_available():
                break
            try:
                action()
            except Exception as exc:
                app_logger.warning("ANT+ %s search cleanup failed: %s", ant_name, exc)

    def getSearchList(self):
        if self.config.G_ANT["STATUS"]:
            with self._search_lock:
                return self.searchList.copy()
        else:
            # dummy
            timestamp = datetime.now()
            if 0 < timestamp.second % 30 < 15:
                return {
                    12345: (0x79, False),
                    23456: (0x7A, False),
                    6789: (0x78, False),
                }
            elif 15 < timestamp.second % 30 < 30:
                return {
                    12345: (0x79, False),
                    23456: (0x7A, False),
                    34567: (0x7B, False),
                    45678: (0x0B, False),
                    45679: (0x0B, True),
                    56789: (0x78, False),
                    6789: (0x78, False),
                }
            else:
                return {}
