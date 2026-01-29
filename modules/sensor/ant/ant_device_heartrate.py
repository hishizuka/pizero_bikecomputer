from datetime import datetime

from . import ant_device


class ANT_Device_HeartRate(ant_device.ANT_Device):
    ant_config = {
        "interval": (8070, 16140, 32280),
        "type": 0x78,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    elements = ("heart_rate",)
    pickle_key = "ant+_hr_values"

    def on_data(self, data):
        page = data[0] & 0x7F  # Bit7 is toggle, bits 0-6 are page number
        self.values["heart_rate"] = data[7]
        self.values["timestamp"] = datetime.now()

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

        # Data Page 7 - Battery Status (0x07)
        if page == 0x07:
            frac = data[2]
            desc = data[3]
            status_code = (desc >> 4) & 0x07
            coarse = desc & 0x0F

            self.values["battery_status"] = self.battery_status.get(
                status_code, "Invalid"
            )
            if coarse == 0x0F:
                self.values["battery_voltage"] = self.config.G_ANT_NULLVALUE
            else:
                self.values["battery_voltage"] = round(coarse + (frac / 256.0), 2)

