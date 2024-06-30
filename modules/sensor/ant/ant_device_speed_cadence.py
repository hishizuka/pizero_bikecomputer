import struct
import datetime

from logger import app_logger
from . import ant_device
from . import ant_code


class ANT_Device_Speed_Cadence(ant_device.ANT_Device):
    ant_config = {
        "interval": (8086, 16172, 32344),
        "type": 0x79,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    sc_values = []  # cad_time, cad, speed_time, speed
    pre_values = []  # cad_time, cad, speed_time, speed
    delta = []  # cad_time, cad, speed_time, speed
    elements = ("speed", "cadence", "distance")

    pickle_key = "ant+_sc_values"

    def add_struct_pattern(self):
        self.structPattern[self.name] = struct.Struct("<HHHH")

    def reset_value(self):
        self.values["distance"] = 0.0
        self.sc_values = [-1, -1, -1, -1]
        self.pre_values = [-1, -1, -1, -1]
        self.delta = [-1, -1, -1, -1]
        self.values["on_data_timestamp"] = None

    def on_data(self, data):
        self.sc_values = self.structPattern[self.name].unpack(data[0:8])
        t = datetime.datetime.now()

        if self.pre_values[0] == -1:
            self.pre_values = list(self.sc_values)
            self.values["speed"] = 0
            self.values["cadence"] = 0
            self.values["on_data_timestamp"] = t

            pre_speed_value = self.config.state.get_value(
                self.pickle_key, self.pre_values[3]
            )
            diff = self.pre_values[3] - pre_speed_value
            if -65535 <= diff < 0:
                diff += 65536
            if diff > 0:
                self.values["distance"] += self.config.G_WHEEL_CIRCUMFERENCE * diff
                app_logger.info(
                    f"### resume spd {self.pre_values[3]} {pre_speed_value} {diff} ###"
                )
                app_logger.info(
                    f"### resume spd {int(self.values['distance'])} {int(self.config.G_WHEEL_CIRCUMFERENCE * diff)} [m] ###"
                )

            return

        # cad_time, cad, speed_time, speed
        self.delta = [a - b for (a, b) in zip(self.sc_values, self.pre_values)]
        for i in range(len(self.delta)):
            if -65535 <= self.delta[i] < 0:
                self.delta[i] += 65536

        # speed
        if self.delta[2] > 0 and 0 <= self.delta[3] < 6553:  # for spike
            # unit: m/s
            spd = (
                self.config.G_WHEEL_CIRCUMFERENCE * self.delta[3] * 1024 / self.delta[2]
            )
            # max value in .fit file is 65.536 [m/s]
            if (
                spd <= 65
                and (spd - self.values["speed"]) < self.spike_threshold["speed"]
            ):
                self.values["speed"] = spd
                if self.config.G_MANUAL_STATUS == "START":
                    # unit: m
                    self.values["distance"] += (
                        self.config.G_WHEEL_CIRCUMFERENCE * self.delta[3]
                    )
                # refresh timestamp called from sensor_core
                self.values["timestamp"] = t
            else:
                self.print_spike(
                    "Speed(S&C)", spd, self.values["speed"], self.delta, []
                )
        elif self.delta[2] == 0 and self.delta[3] == 0:
            # if self.values['on_data_timestamp'] is not None and (t - self.values['on_data_timestamp']).total_seconds() >= self.stop_cutoff:
            self.values["speed"] = 0
        else:
            app_logger.error(f"ANT+ S&C(speed) err: {self.delta}")
        # store raw speed
        self.config.state.set_value(self.pickle_key, self.sc_values[3])

        # cadence
        if self.delta[0] > 0 and 0 <= self.delta[1] < 6553:  # for spike
            cad = 60 * self.delta[1] * 1024 / self.delta[0]
            if cad <= 255:  # max value in .fit file is 255 [rpm]
                self.values["cadence"] = cad
                # refresh timestamp called from sensor_core
                self.values["timestamp"] = t
        elif self.delta[0] == 0 and self.delta[1] == 0:
            # if self.values['on_data_timestamp'] is not None and (t - self.values['on_data_timestamp']).total_seconds() >= self.stop_cutoff:
            self.values["cadence"] = 0
        else:
            app_logger.error(f"ANT+ S&C(cadence) err: {self.delta}")
        self.pre_values = list(self.sc_values)
        # on_data timestamp
        self.values["on_data_timestamp"] = t


class ANT_Device_Cadence(ant_device.ANT_Device):
    ant_config = {
        "interval": (8102, 16204, 32408),
        "type": 0x7A,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    sc_values = []  # time, value
    pre_values = []
    delta = []
    elements = ("cadence",)
    const = 60
    fit_max = 255

    pickle_key = "ant+_cdc_values"

    def add_struct_pattern(self):
        self.structPattern[self.name] = struct.Struct("<xxxxHH")

    def reset_value(self):
        self.sc_values = [-1, -1]
        self.pre_values = [-1, -1]
        self.delta = [-1, -1]
        self.values["on_data_timestamp"] = None
        self.resetExtra()

    def resetExtra(self):
        pass

    def on_data(self, data):
        self.sc_values = self.structPattern[self.name].unpack(data[0:8])
        t = datetime.datetime.now()

        if self.pre_values[0] == -1:
            self.pre_values = list(self.sc_values)
            self.values[self.elements[0]] = 0
            self.values["on_data_timestamp"] = t
            self.resumeAccumulatedValue()
            return

        # time, value
        self.delta = [a - b for (a, b) in zip(self.sc_values, self.pre_values)]
        for i in range(len(self.delta)):
            if -65535 <= self.delta[i] < 0:
                self.delta[i] += 65536

        if self.delta[0] > 0 and 0 <= self.delta[1] < 6553:  # for spike
            val = self.const * self.delta[1] * 1024 / self.delta[0]
            # max value in .fit file is fit_max
            if (
                val <= self.fit_max
                and (val - self.values[self.elements[0]])
                < self.spike_threshold[self.elements[0]]
            ):
                self.values[self.elements[0]] = val
                self.accumulateValue()
                # refresh timestamp called from sensor_core
                self.values["timestamp"] = t
            else:
                self.print_spike(
                    self.elements[0], val, self.values[self.elements[0]], self.delta, []
                )
        elif self.delta[0] == 0 and self.delta[1] == 0:
            # if self.values['on_data_timestamp'] is not None and (t - self.values['on_data_timestamp']).total_seconds() >= self.stop_cutoff:
            self.values[self.elements[0]] = 0
        else:
            app_logger.error(f"ANT+ {self.elements[0]} err: {self.delta}")
        self.pre_values = list(self.sc_values)
        # on_data timestamp
        self.values["on_data_timestamp"] = t

        page = data[0] & 0b111
        # Data Page 2: Manufacturer ID
        if page == 2:
            self.values["manu_id"] = data[1]
            if self.values["manu_id"] in ant_code.AntCode.MANUFACTURER:
                self.values["manu_name"] = ant_code.AntCode.MANUFACTURER[
                    self.values["manu_id"]
                ]
            self.values["serial_num"] = data[3] * 256 + data[2]
        # Data Page 3: Product ID
        elif page == 3:
            self.values["hw_ver"] = data[1]
            self.values["sw_ver"] = data[2]
            self.values["model_num"] = data[3]
        # Data Page 4: Battery Status
        elif page == 4:
            self.setCommonPage82(data[2:4], self.values)

    def resumeAccumulatedValue(self):
        pass

    def accumulateValue(self):
        pass


class ANT_Device_Speed(ANT_Device_Cadence):
    ant_config = {
        "interval": (8118, 16236, 32472),
        "type": 0x7B,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    elements = ("speed", "distance")
    const = None
    fit_max = 65

    pickle_key = "ant+_spd_values"

    def resetExtra(self):
        self.values["distance"] = 0.0
        self.const = self.config.G_WHEEL_CIRCUMFERENCE

    def resumeAccumulatedValue(self):
        pre_speed_value = self.config.state.get_value(
            self.pickle_key, self.pre_values[1]
        )
        diff = self.pre_values[1] - pre_speed_value
        if -65535 <= diff < 0:
            diff += 65536
        if diff > 0:
            self.values["distance"] += self.config.G_WHEEL_CIRCUMFERENCE * diff
            app_logger.info(
                f"### resume spd {self.pre_values[1]}, {pre_speed_value}, {diff} ###"
            )
            app_logger.info(f"### resume spd {int(self.values['distance'])} [m] ###")

    def accumulateValue(self):
        if self.config.G_MANUAL_STATUS == "START":
            # unit: m
            self.values["distance"] += self.config.G_WHEEL_CIRCUMFERENCE * self.delta[1]
        # store raw speed
        self.config.state.set_value(self.pickle_key, self.sc_values[1])
