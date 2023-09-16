import struct
import array

from . import ant_device


class ANT_Device_CTRL(ant_device.ANT_Device):
    ant_config = {
        "interval": (8192, 16384, 16384),  # 8192, 16384, 32768
        "type": 0x10,
        "transmission_type": 0x05,
        "channel_type": 0x10,  # Channel.Type.BIDIRECTIONAL_TRANSMIT,
        "master_id": 123,
    }
    elements = ("ctrl_cmd", "slave_id")
    send_data = False
    data_page_02 = array.array("B", [0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10])
    pickle_key = "ant+_ctrl_values"

    ctrl_cmd = {
        0x0024: ("LAP", 0),  # lap button
        0x0001: ("PAGE", 0),  # page button
        0x0000: ("PAGE", 1),  # page button (long press)
        0x8000: ("CUSTOM", 0),  # custom button
        0x8001: ("CUSTOM", 1),  # custom button (long press)
    }

    def channel_set_id(self):  # for master
        self.channel.set_id(
            self.ant_config["master_id"],
            self.ant_config["type"],
            self.ant_config["transmission_type"],
        )

    def init_extra(self):
        self.channel.on_broadcast_tx_data = self.on_tx_data
        self.channel.send_broadcast_data(self.data_page_02)

    def on_tx_data(self, data):
        if self.send_data:
            self.channel.send_broadcast_data(self.data_page_02)

    def add_struct_pattern(self):
        self.structPattern[self.name] = struct.Struct("<xxxxxxH")

    def on_data(self, data):
        (self.values["ctrl_cmd"],) = self.structPattern[self.name].unpack(data[0:8])
        if self.values["ctrl_cmd"] in self.ctrl_cmd.keys():
            self.config.press_button(
                "Edge_Remote", *(self.ctrl_cmd[self.values["ctrl_cmd"]])
            )
        else:
            if self.values["ctrl_cmd"] != 0xFFFF:
                print("ANT_Device_CTRL wrong cmd:", hex(self.values["ctrl_cmd"]))
