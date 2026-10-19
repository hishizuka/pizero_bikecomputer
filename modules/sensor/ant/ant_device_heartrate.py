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
    metadata_pages = (2, 3, 7)
    battery_page = 7
    pickle_key = "ant+_hr_values"

    def on_data(self, data):
        page = data[0] & 0x7F  # Bit7 is toggle, bits 0-6 are page number
        self.values["heart_rate"] = data[7]
        self.values["timestamp"] = datetime.now()

        self.set_profile_background_page(data)
        # Data Page 7 - Battery Status (0x07)
        if page == 0x07:
            self.setCommonPage82(data[2:4], self.values)
            self.values["battery_percentage"] = (
                data[1] if data[1] <= 100 else self.config.G_SENSOR_NULLVALUE
            )
