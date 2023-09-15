import struct
import datetime
import time

from . import ant_device
from . import ant_device_power


class ANT_Device_MultiScan(ant_device.ANT_Device):
    name = "SCAN"
    ant_config = {
        "interval": (),  # Not use
        "type": 0,  # ANY
        "transmission_type": 0x00,
        "channel_type": 0x40,  # Channel.Type.UNIDIRECTIONAL_RECEIVE_ONLY,
    }
    isUse = False
    mainAntDevice = None
    power_values = {}
    power_meter_value = {}
    pre_power_meter_value = {}

    def __init__(self, node, config):
        self.node = node
        self.config = config
        self.reset_value()
        self.make_channel(self.ant_config["channel_type"])
        self.ready_scan()
        self.dummyPowerDevice = ant_device_power.ANT_Device_Power(
            node=None, config=config, values={}, name="PWR"
        )

    def set_null_value(self):
        pass

    def reset_value(self):
        self.values = {}
        self.power_values = {}
        self.power_meter_value = {}
        self.pre_power_meter_value = {}

    def ready_scan(self):
        if self.config.G_ANT["STATUS"]:
            self.channel.set_rf_freq(57)
            self.channel.set_id(
                0, self.ant_config["type"], self.ant_config["transmission_type"]
            )

    def scan(self):
        if self.config.G_ANT["STATUS"]:
            self.channel.enable_extended_messages(1)
            try:
                self.channel.open_rx_scan_mode()
                self.isUse = True
            except:
                pass

    def stop_scan(self):
        self.disconnect(0.5)

    def stop(self):
        return self.disconnect(0)

    def disconnect(self, wait):
        if not self.config.G_ANT["STATUS"]:
            return False
        if not self.isUse:
            return False
        if self.state_check("CLOSE"):
            self.isUse = False
            return True
        try:
            self.channel.close()
            time.sleep(wait)
            self.set_null_value()
            self.isUse = False
            self.channel.enable_extended_messages(0)
            return True
        except:
            return False

    def set_main_ant_device(self, device):
        self.mainAntDevice = device

    def on_data(self, data):
        # get type and ID
        antType = antID = antIDType = 0
        if len(data) == 13:
            (antID, antType) = self.structPattern["ID"].unpack(data[9:12])
            antIDType = struct.pack("<HB", antID, antType)
        else:
            return

        # HR
        if antType in self.config.G_ANT["TYPES"]["HR"]:
            if antIDType == self.config.G_ANT["ID_TYPE"]["HR"]:
                self.mainAntDevice[antIDType].on_data(data)
            else:
                if antIDType not in self.values:
                    self.values[antIDType] = {}
                self.values[antIDType]["timestamp"] = datetime.datetime.now()
                self.values[antIDType]["hr"] = data[7]
        # Power
        elif antType in self.config.G_ANT["TYPES"]["PWR"]:
            if antIDType == self.config.G_ANT["ID_TYPE"]["PWR"]:
                self.mainAntDevice[antIDType].on_data(data)
            else:
                if antIDType not in self.values:
                    self.values[antIDType] = {}
                    self.power_values[antIDType] = {
                        0x10: {
                            "power": 0,
                            "accumulated_power": 0,
                            "on_data_timestamp": None,
                        },
                        0x11: {
                            "power": 0,
                            "accumulated_power": 0,
                            "distance": 0,
                            "on_data_timestamp": None,
                        },
                        0x12: {
                            "power": 0,
                            "accumulated_power": 0,
                            "on_data_timestamp": None,
                        },
                        0x50: {"manu_name": ""},
                    }
                    self.power_meter_value[antIDType] = {
                        0x10: [-1, -1, -1, -1],
                        0x11: [-1, -1, -1, -1],
                        0x12: [-1, -1, -1, -1],
                    }
                    self.pre_power_meter_value[antIDType] = {
                        0x10: [-1, -1, -1, -1],
                        0x11: [-1, -1, -1, -1],
                        0x12: [-1, -1, -1, -1],
                    }
                self.values[antIDType]["timestamp"] = datetime.datetime.now()
                if data[0] == 0x10:
                    self.dummyPowerDevice.on_data_power_0x10(
                        data,
                        self.power_meter_value[antIDType][0x10],
                        self.pre_power_meter_value[antIDType][0x10],
                        self.power_values[antIDType][0x10],
                    )
                    self.values[antIDType]["power"] = self.power_values[antIDType][
                        0x10
                    ]["power"]
                elif data[0] == 0x11:
                    self.dummyPowerDevice.on_data_power_0x11(
                        data,
                        self.power_meter_value[antIDType][0x11],
                        self.pre_power_meter_value[antIDType][0x11],
                        self.power_values[antIDType][0x11],
                    )
                    self.values[antIDType]["power"] = self.power_values[antIDType][
                        0x11
                    ]["power"]
                elif data[0] == 0x12:
                    self.dummyPowerDevice.on_data_power_0x12(
                        data,
                        self.power_meter_value[antIDType][0x12],
                        self.pre_power_meter_value[antIDType][0x12],
                        self.power_values[antIDType][0x12],
                    )
                    self.values[antIDType]["power"] = self.power_values[antIDType][
                        0x12
                    ]["power"]
                elif data[0] == 0x50:
                    self.setCommonPage80(data, self.power_values[antIDType][0x50])
                    self.values[antIDType]["manu_name"] = self.power_values[antIDType][
                        0x50
                    ]["manu_name"]
        # Speed
        elif antType in self.config.G_ANT["TYPES"]["SPD"]:
            if antIDType == self.config.G_ANT["ID_TYPE"]["SPD"]:
                self.mainAntDevice[antIDType].on_data(data)
        # Cadence
        elif antType in self.config.G_ANT["TYPES"]["CDC"]:
            if antIDType == self.config.G_ANT["ID_TYPE"]["CDC"]:
                self.mainAntDevice[antIDType].on_data(data)
