import struct
from datetime import datetime

from . import ant_device


class ANT_Device_Temperature(ant_device.ANT_Device):
    ant_config = {
        "interval": (8192, 65535, 65535),
        "type": 0x19,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    elements = ("temperature",)
    pickle_key = "ant+_temperature_values"

    def add_struct_pattern(self):
        # (page), x, (evt_count), (2byte), (Low Temp: 1.5Byte), (High Temp: 1.5Byte),  Current Temp(2byte)
        self.structPattern[self.name] = struct.Struct("<xxxxxxh")

    def on_data(self, data):
        if data[0] == 0x01:
            self.values["temperature"] = round(
                self.structPattern[self.name].unpack(data[0:8])[0] / 100, 1
            )
            self.values["timestamp"] = datetime.now()
