from datetime import datetime
import random
import struct
import asyncio

import numpy as np

from modules.app_logger import app_logger
from .sensor import Sensor
from .ant import ant_device_heartrate
from .ant import ant_device_speed_cadence
from .ant import ant_device_power
from .ant import ant_device_light
from .ant import ant_device_ctrl
from .ant import ant_device_temperature
from .ant import ant_device_multiscan
from .ant import ant_device_search

# ANT+
_SENSOR_ANT = False

try:
    from ant.easy.node import Node
    from ant.base.driver import find_driver, DriverNotFound

    # device test
    _driver = find_driver()
    _SENSOR_ANT = True
except ImportError:
    pass
except DriverNotFound:
    pass
except Exception:
    pass

if _SENSOR_ANT:
    app_logger.info("  ANT")


class SensorANT(Sensor):
    # for openant
    node = None
    NETWORK_KEY = [0xB9, 0xA5, 0x21, 0xFB, 0xBD, 0x72, 0xC3, 0x45]
    NETWORK_NUM = 0x00
    scanner = None
    device = {}

    def _init_runtime_state(self):
        self._start_task = None

    def _init_transport_disconnect_state(self):
        self.transport_disconnected = False
        self.transport_error = None
        self._transport_disconnect_popup_pending = False
        self._transport_disconnect_popup_shown = False
        self._transport_disconnect_logged = False

    @staticmethod
    def _dummy_timestamp_fields():
        return {
            "timestamp": None,
            "on_data_timestamp": None,
        }

    @classmethod
    def _dummy_speed_values(cls):
        return {
            "speed": 0,
            "cadence": 0,
            "distance": 0,
            **cls._dummy_timestamp_fields(),
        }

    @classmethod
    def _dummy_power_page_values(cls, page):
        values = {
            "power": 0,
            "accumulated_power": 0,
            "last_event_timestamp": None,
            "last_event_interval": None,
            **cls._dummy_timestamp_fields(),
        }
        if page == 0x10:
            values.update(
                {
                    "power_16_simple": 0,
                    "cadence": 0,
                    "power_r": 0,
                    "power_l": 0,
                    "lr_balance": ":",
                }
            )
        elif page == 0x11:
            values.update(
                {
                    "speed": 0,
                    "distance": 0,
                    "cadence": 0,
                }
            )
        elif page == 0x12:
            values["cadence"] = 0
        return values

    @staticmethod
    def _touch_dummy_timestamp(values, timestamp):
        values["timestamp"] = timestamp
        values["on_data_timestamp"] = timestamp

    def sensor_init(self):
        self._init_runtime_state()
        self._init_transport_disconnect_state()

        if self.config.G_ANT["STATUS"] and not _SENSOR_ANT:
            self.config.G_ANT["STATUS"] = False

        if self.config.G_ANT["STATUS"]:
            self._create_node()

        # initialize scan channel (reserve ch0)
        if _SENSOR_ANT:
            app_logger.info("detected ANT+ sensors:")
        self._create_scan_search_devices()

        # auto connect ANT+ sensor from setting.conf
        if self.config.G_ANT["STATUS"] and not self.config.G_DUMMY_OUTPUT:
            for key in self.config.G_ANT["ID"].keys():
                if self.config.G_ANT["USE"][key]:
                    antID = self.config.G_ANT["ID"][key]
                    antType = self.config.G_ANT["TYPE"][key]
                    self.connect_ant_sensor(key, antID, antType, False)
            return
        # otherwise, initialize
        elif self.config.G_DUMMY_OUTPUT:
            for key in self.config.G_ANT["ID"].keys():
                self.config.G_ANT["USE"][key] = False
                self.config.G_ANT["ID"][key] = 0
                self.config.G_ANT["TYPE"][key] = 0

        # for dummy output
        if not self.config.G_ANT["STATUS"] and self.config.G_DUMMY_OUTPUT:
            # need to set dummy ANT+ device id 0
            self.config.G_ANT["USE"]["HR"] = True
            self.config.G_ANT["USE"]["SPD"] = True
            self.config.G_ANT["USE"]["CDC"] = True  # same as SPD
            self.config.G_ANT["USE"]["PWR"] = True
            self.config.G_ANT["USE"]["TEMP"] = False

            self.config.G_ANT["ID_TYPE"]["HR"] = struct.pack("<HB", 0, 0x78)
            self.config.G_ANT["ID_TYPE"]["SPD"] = struct.pack("<HB", 0, 0x79)
            self.config.G_ANT["ID_TYPE"]["CDC"] = struct.pack(
                "<HB", 0, 0x79
            )  # same as SPD
            self.config.G_ANT["ID_TYPE"]["PWR"] = struct.pack("<HB", 0, 0x0B)

            self.config.G_ANT["TYPE"]["HR"] = 0x78
            self.config.G_ANT["TYPE"]["SPD"] = 0x79
            self.config.G_ANT["TYPE"]["CDC"] = 0x79  # same as SPD
            self.config.G_ANT["TYPE"]["PWR"] = 0x0B

            ac = self.config.G_ANT["ID_TYPE"]
            self.values[ac["HR"]] = {
                "heart_rate": 0,
                **self._dummy_timestamp_fields(),
            }
            self.values[ac["SPD"]] = self._dummy_speed_values()
            self.values[ac["PWR"]] = {}
            for key in [0x10, 0x11, 0x12]:
                self.values[ac["PWR"]][key] = self._dummy_power_page_values(key)

        # for dummy device
        self.reset()

    def start_coroutine(self):
        self._start_task = asyncio.create_task(self.start())

    async def start(self):
        if self.config.G_ANT["STATUS"]:
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.node.start)
            finally:
                self._sync_transport_disconnect_from_node()
                self.notify_transport_disconnected()

    def update(self):
        self.notify_transport_disconnected()

        if self.config.G_ANT["STATUS"] or not self.config.G_DUMMY_OUTPUT:
            return

        hr_value = random.randint(70, 150)
        speed_value = random.randint(5, 30) / 3.6  # 5 - 30km/h [unit:m/s]
        cad_value = random.randint(60, 100)
        power_value = random.randint(0, 250)
        timestamp = datetime.now()

        ac = self.config.G_ANT["ID_TYPE"]
        self.values[ac["HR"]]["heart_rate"] = hr_value
        self.values[ac["SPD"]]["speed"] = speed_value
        self.values[ac["CDC"]]["cadence"] = cad_value
        self.values[ac["PWR"]][0x10]["power"] = power_value

        # TIMESTAMP
        self._touch_dummy_timestamp(self.values[ac["HR"]], timestamp)
        self._touch_dummy_timestamp(self.values[ac["SPD"]], timestamp)
        self._touch_dummy_timestamp(self.values[ac["PWR"]][0x10], timestamp)
        # DISTANCE, TOTAL_WORK
        if self.config.G_MANUAL_STATUS == "START":
            # DISTANCE: unit: m
            if not np.isnan(self.values[ac["SPD"]]["speed"]):
                self.values[ac["SPD"]]["distance"] += (
                    self.values[ac["SPD"]]["speed"] * self.config.G_SENSOR_INTERVAL
                )
            # TOTAL_WORK: unit: j
            if not np.isnan(self.values[ac["PWR"]][0x10]["power"]):
                self.values[ac["PWR"]][0x10]["accumulated_power"] += (
                    self.values[ac["PWR"]][0x10]["power"]
                    * self.config.G_SENSOR_INTERVAL
                )

    def reset(self):
        for dv in self.device.values():
            dv.reset_value()

    def _create_node(self):
        try:
            self.node = Node()
            self._register_transport_disconnect_callback()
            self.node.set_network_key(self.NETWORK_NUM, self.NETWORK_KEY)
            return True
        except Exception as e:
            app_logger.warning(f"ANT+ init failed: {e}")
            if self.node is not None:
                try:
                    self.node.stop()
                except Exception:
                    pass
            self.node = None
            self.config.G_ANT["STATUS"] = False
            return False

    def _create_scan_search_devices(self):
        self.scanner = ant_device_multiscan.ANT_Device_MultiScan(self.node, self.config)
        self.searcher = ant_device_search.ANT_Device_Search(
            self.node, self.config, self.values
        )
        self.scanner.set_main_ant_device(self.device)
        self.searcher.set_main_ant_device(self.device)

    def _drop_runtime_devices(self):
        devices = list({id(dv): dv for dv in self.device.values()}.values())
        for dv in devices:
            send_queue = getattr(dv, "send_queue", None)
            if send_queue is None:
                continue
            try:
                send_queue.put_nowait(None)
            except Exception:
                pass
        self.device.clear()

    def _ensure_node_started(self):
        if not self.config.G_ANT["STATUS"] or self.node is None:
            return
        if self._start_task is not None and not self._start_task.done():
            return
        try:
            loop = self.config.loop
        except (RuntimeError, AttributeError):
            return
        if loop.is_running():
            self._start_task = loop.create_task(self.start())

    def is_transport_available(self):
        return (
            self.config.G_ANT["STATUS"]
            and self.node is not None
            and not self.transport_disconnected
        )

    def is_sensor_available(self, ant_name):
        if self.config.G_DUMMY_OUTPUT and not self.config.G_ANT["STATUS"]:
            return self.config.G_ANT["USE"][ant_name]
        return self.is_transport_available() and self.config.G_ANT["USE"][ant_name]

    def invalidate_sensor_values(self, ant_name=None):
        devices = []
        if ant_name is None:
            devices = list({id(dv): dv for dv in self.device.values()}.values())
        else:
            ant_id_type = self.config.G_ANT["ID_TYPE"][ant_name]
            devices.append(self.device[ant_id_type])

        for dv in devices:
            try:
                dv.reset_value()
            except Exception:
                pass
            try:
                dv.set_null_value()
            except Exception:
                pass

    def enable_ant(self):
        if self.is_transport_available():
            return True

        self.config.G_ANT["STATUS"] = True
        if self.node is None or self.transport_disconnected:
            if self.node is not None:
                try:
                    self.node.stop()
                except Exception:
                    pass
            self.node = None
            self._drop_runtime_devices()
            self._init_transport_disconnect_state()
            if not self._create_node():
                return False
            self._create_scan_search_devices()
            self._ensure_node_started()

        for key in self.config.G_ANT["ID"].keys():
            if not self.config.G_ANT["USE"][key]:
                continue
            ant_id = self.config.G_ANT["ID"][key]
            ant_type = self.config.G_ANT["TYPE"][key]
            if ant_id == 0 or ant_type == 0:
                continue
            self.connect_ant_sensor(key, ant_id, ant_type, False)

        return True

    def disable_ant(self, reason="user"):
        if self.node is not None and not self.transport_disconnected:
            try:
                if self.scanner is not None:
                    self.scanner.stop()
            except Exception:
                pass
            try:
                if self.searcher is not None:
                    self.searcher.stop_search(resetWait=False)
            except Exception:
                pass
            for dv in list({id(dv): dv for dv in self.device.values()}.values()):
                try:
                    dv.ant_state = f"disable_ant:{reason}"
                    dv.disconnect(isCheck=False, isChange=False)
                except Exception:
                    pass

        self.invalidate_sensor_values()
        self.config.G_ANT["STATUS"] = False

    def _log_battery_status_on_quit(self):
        entries = []
        for dv in self.device.values():
            status = dv.values["battery_status"]
            if status is None:
                continue
            if isinstance(status, (float, np.floating)) and np.isnan(status):
                continue
            name = dv.name or "UNKNOWN"
            entries.append(f"{name}={status}")

        if entries:
            app_logger.info("ANT+ battery_status: " + ", ".join(entries))

    def quit(self):
        if self.node is None:
            return
        self._sync_transport_disconnect_from_node()
        if self.transport_disconnected:
            app_logger.info("Skip ANT+ quit after transport disconnect")
            try:
                self.node.stop()
            except Exception:
                pass
            return
        if not self.config.G_ANT["STATUS"]:
            try:
                self.node.stop()
            except Exception:
                pass
            return
        self.searcher.set_wait_quick_mode()
        self._log_battery_status_on_quit()
        # stop scanner and searcher
        if not self.scanner.stop():
            for dv in self.device.values():
                dv.ant_state = "quit"
                dv.disconnect(isCheck=True, isChange=False)  # USE: True -> True
            self.searcher.stop_search(resetWait=False)
        self.node.stop()

    def connect_ant_sensor(self, antName, antID, antType, connectStatus):
        if not self.is_transport_available():
            return
        self.config.G_ANT["ID"][antName] = antID
        self.config.G_ANT["TYPE"][antName] = antType
        self.config.G_ANT["ID_TYPE"][antName] = struct.pack("<HB", antID, antType)
        antIDType = self.config.G_ANT["ID_TYPE"][antName]
        self.searcher.stop_search(resetWait=False)

        self.config.G_ANT["USE"][antName] = True

        self.searcher.set_wait_normal_mode()

        # existing connection
        if connectStatus:
            return

        # reconnect
        if antIDType in self.device:
            self.device[antIDType].connect(
                isCheck=False, isChange=False
            )  # USE: True -> True)
            self.device[antIDType].ant_state = "connect_ant_sensor"
            self.device[antIDType].init_after_connect()
            return

        # newly connect
        self.values[antIDType] = {}
        if antType == 0x78:
            self.device[antIDType] = ant_device_heartrate.ANT_Device_HeartRate(
                self.node, self.config, self.values[antIDType], antName
            )
        elif antType == 0x79:
            self.device[antIDType] = ant_device_speed_cadence.ANT_Device_Speed_Cadence(
                self.node, self.config, self.values[antIDType], antName
            )
        elif antType == 0x7A:
            self.device[antIDType] = ant_device_speed_cadence.ANT_Device_Cadence(
                self.node, self.config, self.values[antIDType], antName
            )
        elif antType == 0x7B:
            self.device[antIDType] = ant_device_speed_cadence.ANT_Device_Speed(
                self.node, self.config, self.values[antIDType], antName
            )
        elif antType == 0x0B:
            self.device[antIDType] = ant_device_power.ANT_Device_Power(
                self.node, self.config, self.values[antIDType], antName
            )
        elif antType == 0x23:
            self.device[antIDType] = ant_device_light.ANT_Device_Light(
                self.node, self.config, self.values[antIDType], antName
            )
        elif antType == 0x10:
            self.device[antIDType] = ant_device_ctrl.ANT_Device_CTRL(
                self.node, self.config, self.values[antIDType], antName
            )
        elif antType == 0x19:
            self.device[antIDType] = ant_device_temperature.ANT_Device_Temperature(
                self.node, self.config, self.values[antIDType], antName
            )
        self.device[antIDType].ant_state = "connect_ant_sensor"
        self.device[antIDType].init_after_connect()

    def disconnect_ant_sensor(self, antName):
        antIDType = self.config.G_ANT["ID_TYPE"][antName]
        antNames = []
        for k, v in self.config.G_ANT["USE"].items():
            if v and k in self.config.G_ANT["ID_TYPE"]:
                if self.config.G_ANT["ID_TYPE"][k] == antIDType:
                    antNames.append(k)
        dv = self.device[antIDType]
        if self.is_transport_available():
            try:
                dv.ant_state = "disconnect_ant_sensor"
                dv.disconnect(isCheck=False, isChange=False)
                dv.delete()
            except Exception:
                pass
        self.invalidate_sensor_values(antName)
        self.device.pop(antIDType)

        for k in antNames:
            # USE: True -> False
            self.config.G_ANT["ID_TYPE"][k] = 0
            self.config.G_ANT["ID"][k] = 0
            self.config.G_ANT["TYPE"][k] = 0
            self.config.G_ANT["USE"][k] = False

    def continuous_scan(self):
        if not self.is_transport_available():
            return
        self.scanner.set_wait_quick_mode()
        for dv in self.device.values():
            dv.ant_state = "continuous_scan"
            dv.disconnect(isCheck=True, isChange=False)  # USE: True -> True
        self.scanner.set_wait_scan_mode()
        self.scanner.scan()
        app_logger.info("START ANT+ multiscan")

    def stop_continuous_scan(self):
        if not self.is_transport_available():
            return
        self.scanner.set_wait_quick_mode()
        self.scanner.stop_scan()
        antIDTypes = set()
        for k, v in self.config.G_ANT["USE"].items():
            antIDType = self.config.G_ANT["ID_TYPE"][k]
            if v and antIDType not in antIDTypes:
                antIDTypes.add(antIDType)
                self.device[antIDType].connect(
                    isCheck=True, isChange=False
                )  # USE: True -> True
                self.device[antIDType].ant_state = "connect_ant_sensor"
                self.device[antIDType].init_after_connect()
        self.scanner.set_wait_normal_mode()
        app_logger.info("STOP ANT+ multiscan")

    def set_light_mode(self, mode, auto=False):
        if not self.is_sensor_available("LGT"):
            return
        self.device[self.config.G_ANT["ID_TYPE"]["LGT"]].send_light_mode(mode, auto)

    def _register_transport_disconnect_callback(self):
        if self.node is None:
            return
        try:
            self.node.on_transport_disconnect = self._on_transport_disconnect
        except AttributeError:
            pass

    def _on_transport_disconnect(self, error):
        notify_user = self.config.G_ANT["STATUS"]
        self.transport_disconnected = True
        self.transport_error = error
        self.invalidate_sensor_values()
        if not self._transport_disconnect_logged:
            app_logger.warning(f"ANT+ transport disconnected: {error!r}")
            self._transport_disconnect_logged = True
        if notify_user and not self._transport_disconnect_popup_shown:
            self._transport_disconnect_popup_pending = True

        try:
            loop = self.config.loop
        except RuntimeError:
            return
        except AttributeError:
            return
        if loop.is_running():
            loop.call_soon_threadsafe(self.notify_transport_disconnected)

    def _sync_transport_disconnect_from_node(self):
        if self.node is None:
            return
        if not getattr(self.node, "transport_disconnected", False):
            return
        self._on_transport_disconnect(getattr(self.node, "transport_error", None))

    def notify_transport_disconnected(self):
        if (
            not self._transport_disconnect_popup_pending
            or self._transport_disconnect_popup_shown
        ):
            return False

        gui = self.config.gui
        if gui is None:
            return False

        if gui.msg_queue is None:
            return False
        show_dialog = gui.show_dialog_ok_only

        self._transport_disconnect_popup_pending = False
        self._transport_disconnect_popup_shown = True

        show_dialog(None, "ANT+ USB dongle disconnected.", buzzer_sound="alert")
        return True
