import datetime

from . import ant_device


class ANT_Device_HeartRate(ant_device.ANT_Device):
    ant_config = {
        "interval": (8070, 16140, 32280),
        "type": 0x78,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    elements = ("hr",)
    pickle_key = "ant+_hr_values"

    def on_data(self, data):
        self.values["hr"] = data[7]
        self.values["timestamp"] = datetime.datetime.now()
        # self.channel.send_acknowledged_data(array.array('B',[0x46,0xFF,0xFF,0xFF,0xFF,0x88,0x06,0x01]))
        # if data[0] & 0b1111 == 0b000: # 0x00 or 0x80
        #  print("0x00 : ", format_list(data))
        # elif data[0] & 0b1111 == 0b010: # 0x02 or 0x82
        #  print("HR serial: {0:05d}".format(data[3]*256+data[2]))
        # elif data[0] & 0b1111 == 0b011: # 0x03 or 0x83
        #  print("0x03 : ", format_list(data))
        # elif data[0] & 0b1111 == 0b110: # 0x06 or 0x86
        #  print("0x06 capabilities: ", format_list(data))
        # elif data[0] & 0b1111 == 0b111: # 0x07 or 0x87
        #  print("0x07 battery status: ", format_list(data))
