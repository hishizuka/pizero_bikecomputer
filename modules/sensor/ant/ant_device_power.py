import struct
from datetime import datetime
import math
from collections import deque

from modules.app_logger import app_logger
from . import ant_device


class ANT_Device_Power(ant_device.ANT_Device):
    ant_config = {
        "interval": (8182, 16364, 32728),
        "type": 0x0B,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    pre_values = {0x10: [], 0x11: [], 0x12: [], 0x13: []}
    pre_delta = {0x10: [], 0x11: [], 0x12: [], 0x13: []}
    power_values = {0x10: [], 0x11: [], 0x12: [], 0x13: []}
    elements = {
        0x10: (
            "power",
            "power_l",
            "power_r",
            "lr_balance",
            "power_16_simple",
            "cadence",
            "accumulated_power",
            "normalized_power",
        ),
        0x11: ("power", "speed", "distance", "accumulated_power", "normalized_power"),
        0x12: ("power", "cadence", "accumulated_power", "normalized_power"),
        0x13: ("torque_eff", "pedal_sm"),
    }
    stop_cutoff = 3

    pickle_key = "ant+_pwr_values"

    def add_struct_pattern(self):
        self.structPattern[self.name] = {
            # (page), evt_count, lr_balance, cadence, accumulated power(2byte), instantaneous power(2byte)
            0x10: struct.Struct("<xBBBHH"),
            # (page), evt_count, wheel_ticks, x, wheel period(2byte), accumulatd power(2byte)
            0x11: struct.Struct("<xBBxHH"),
            # (page), x, x, cadence, period(2byte), accumulatd power(2byte)
            0x12: struct.Struct("<xxxBHH"),
            # (page), x, torque effectiveness(left, right), pedal smoothness(left, right), x, x
            0x13: struct.Struct("<xxBBBBxx"),
        }

    def set_null_value(self):
        for page in self.elements:
            self.values[page] = {}
        for page in self.elements:
            for element in self.elements[page]:
                self.values[page][element] = self.config.G_ANT_NULLVALUE
        self.init_common_page_status()

    def reset_value(self):
        self.interval = (
            self.ant_config["interval"][self.config.G_ANT["INTERVAL"]]
            / self.ant_config["interval"][-1]
        )
        self.values[0x10]["accumulated_power"] = 0.0
        self.values[0x11]["distance"] = 0.0
        self.values[0x11]["accumulated_power"] = 0.0
        self.values[0x12]["accumulated_power"] = 0.0
        for page in self.pre_values:
            self.pre_values[page] = [-1, -1, -1, -1]
            self.pre_delta[page] = [-1, -1, -1, -1]
            self.power_values[page] = [-1, -1, -1, -1]
            self.values[page]["on_data_timestamp"] = None
            self.values[page]["stop_timestamp"] = None
        self.np_reset_all_pages()

    def np_ensure_state(self, values):
        if "normalized_power" not in values:
            values["normalized_power"] = self.config.G_ANT_NULLVALUE
        if "np_sec_epoch" not in values:
            values["np_sec_epoch"] = None
        if "np_sec_sum" not in values:
            values["np_sec_sum"] = 0.0
        if "np_sec_count" not in values:
            values["np_sec_count"] = 0
        if "np_window_30s" not in values or not isinstance(values["np_window_30s"], deque):
            values["np_window_30s"] = deque()
        if "np_window_sum" not in values:
            values["np_window_sum"] = 0.0
        if "np_sum_ma4" not in values:
            values["np_sum_ma4"] = 0.0
        if "np_count_ma4" not in values:
            values["np_count_ma4"] = 0

    def np_reset_state(self, values):
        self.np_ensure_state(values)
        values["normalized_power"] = self.config.G_ANT_NULLVALUE
        values["np_sec_epoch"] = None
        values["np_sec_sum"] = 0.0
        values["np_sec_count"] = 0
        values["np_window_30s"].clear()
        values["np_window_sum"] = 0.0
        values["np_sum_ma4"] = 0.0
        values["np_count_ma4"] = 0

    def np_pause_state(self, values):
        self.np_ensure_state(values)
        if values["np_sec_count"] > 0:
            np_second_power = values["np_sec_sum"] / values["np_sec_count"]
            self.np_add_second_power(values, np_second_power)
        # Clear only the short-term 30s window on pause so resume does not mix
        # old pre-pause samples into the first post-resume moving-average values.
        values["np_window_30s"].clear()
        values["np_window_sum"] = 0.0
        values["np_sec_epoch"] = None
        values["np_sec_sum"] = 0.0
        values["np_sec_count"] = 0

    def np_reset_all_pages(self):
        for page in (0x10, 0x11, 0x12):
            if page in self.values:
                self.np_reset_state(self.values[page])

    def np_pause_all_pages(self):
        for page in (0x10, 0x11, 0x12):
            if page in self.values:
                self.np_pause_state(self.values[page])

    def np_add_second_power(self, values, np_second_power):
        self.np_ensure_state(values)
        np_window_30s = values["np_window_30s"]
        np_window_30s.append(np_second_power)
        values["np_window_sum"] += np_second_power
        if len(np_window_30s) > 30:
            values["np_window_sum"] -= np_window_30s.popleft()

        # Only accumulate once the 30s window is full.
        # Partial-window averages are biased low and contaminate the overall NP.
        if len(np_window_30s) >= 30:
            np_ma30 = values["np_window_sum"] / 30
            values["np_sum_ma4"] += np_ma30**4
            values["np_count_ma4"] += 1
            values["normalized_power"] = (values["np_sum_ma4"] / values["np_count_ma4"]) ** 0.25

    def np_update(self, values, power, sample_time):
        if self.config.G_STOPWATCH_STATUS != "START":
            return
        self.np_ensure_state(values)

        np_power = max(float(power), 0.0)
        if math.isnan(np_power):
            np_power = 0.0
        np_second = int(sample_time.timestamp())
        np_sec_epoch = values["np_sec_epoch"]

        if np_sec_epoch is None:
            values["np_sec_epoch"] = np_second
            values["np_sec_sum"] = np_power
            values["np_sec_count"] = 1
            return
        if np_second < np_sec_epoch:
            self.np_reset_state(values)
            values["np_sec_epoch"] = np_second
            values["np_sec_sum"] = np_power
            values["np_sec_count"] = 1
            return
        if np_second == np_sec_epoch:
            values["np_sec_sum"] += np_power
            values["np_sec_count"] += 1
            return

        np_second_power = 0.0
        if values["np_sec_count"] > 0:
            np_second_power = values["np_sec_sum"] / values["np_sec_count"]
        self.np_add_second_power(values, np_second_power)

        # Skip data gaps instead of inserting 0W.
        # A missed ANT+ message is not zero power output.

        values["np_sec_epoch"] = np_second
        values["np_sec_sum"] = np_power
        values["np_sec_count"] = 1

    @staticmethod
    def _format_raw8(data):
        return "[" + " ".join(f"{int(v):02x}" for v in data[0:8]) + "]"

    def on_data(self, data):
        # standard power-only main data page (0x10)
        if data[0] == 0x10:
            self.on_data_power_0x10(
                data, self.power_values[0x10], self.pre_values[0x10], self.pre_delta[0x10], self.values[0x10]
            )
        # Standard Wheel Torque Main Data Page (0x11) #not verified (not own)
        elif data[0] == 0x11:
            self.on_data_power_0x11(
                data, self.power_values[0x11], self.pre_values[0x11], self.pre_delta[0x11], self.values[0x11]
            )
        # standard crank power torque main data page (0x12)
        elif data[0] == 0x12:
            self.on_data_power_0x12(
                data, self.power_values[0x12], self.pre_values[0x12], self.pre_delta[0x12], self.values[0x12]
            )
        # Torque Effectiveness and Pedal Smoothness Main Data Page (0x13)
        elif data[0] == 0x13:

            def setValue(data, key, i):
                self.values[0x13][key] = ""
                if data[i] == 0xFF:
                    self.values[0x13][key] += "--%/"
                else:
                    self.values[0x13][key] += "{0:02d}%/".format(int(data[i] / 2))
                if data[i + 1] == 0xFF:
                    self.values[0x13][key] += "--%"
                else:
                    self.values[0x13][key] += "{0:02d}%".format(int(data[i + 1] / 2))

            setValue(data, "torque_eff", 2)
            setValue(data, "pedal_sm", 4)
        # Common Data Page 80 (0x50): Manufacturer’s Information
        elif data[0] == 0x50 and not self.values["stored_page"][0x50]:
            self.setCommonPage80(data, self.values)
        # Common Data Page 81 (0x51): Product Information
        elif data[0] == 0x51 and not self.values["stored_page"][0x51]:
            self.setCommonPage81(data, self.values)
        # Common Data Page 82 (0x52): Battery Status
        elif data[0] == 0x52:
            self.setCommonPage82(data[6:8], self.values)

        # self.channel.send_acknowledged_data(array.array('B',[0x46,0xFF,0xFF,0xFF,0xFF,0x88,0x02,0x01]))

    def on_data_power_0x10(self, data, power_values, pre_values, pre_delta, values):
        # (page), evt_count, balance, cadence, accumulated power(2byte), instantaneous power(2byte)
        (
            power_values[0],
            lr_balance,
            cadence,
            power_values[1],
            power_16_simple,
        ) = self.structPattern[self.name][0x10].unpack(data[0:8])
        t = datetime.now()
        np_power = None

        if pre_values[0] == -1:
            pre_values[0:2] = power_values[0:2]
            values["on_data_timestamp"] = t
            values["power"] = 0
            np_power = 0.0
            self.np_update(values, np_power, t)
            return

        delta = [a - b for (a, b) in zip(power_values, pre_values)]
        if -255 <= delta[0] < 0:
            delta[0] += 256
        if -65535 <= delta[1] < 0:
            delta[1] += 65536
        delta_t = (t - values["on_data_timestamp"]).total_seconds()

        if delta[0] > 0 and delta[1] >= 0 and delta_t < self.valid_time:
            pwr = delta[1] / delta[0]
            # max value in .fit file is 65536 [w]
            if pwr <= 65535 and (pwr - values["power"]) < self.spike_threshold["power"]:
                values["power"] = pwr
                np_power = pwr
                values["power_16_simple"] = power_16_simple
                values["cadence"] = cadence
                if (
                    self.config.G_MANUAL_STATUS == "START"
                    and values["on_data_timestamp"] is not None
                ):
                    # unit: J
                    values["accumulated_power"] += pwr * round(
                        (t - values["on_data_timestamp"]).total_seconds()
                    )
                # lr_balance
                if lr_balance < 0xFF and lr_balance >> 7 == 1:
                    right_balance = lr_balance & 0b01111111
                    values["power_r"] = pwr * right_balance / 100
                    values["power_l"] = pwr - values["power_r"]
                    values["lr_balance"] = "{}:{}".format(
                        (100 - right_balance), right_balance
                    )
                # refresh timestamp called from sensor_core
                values["timestamp"] = t
            else:
                self.print_spike("Power(16)", pwr, values["power"], delta, delta_t)
        elif delta[0] == 0 and delta[1] == 0:
            np_power = 0.0
            if pre_delta[0:2] != [0, 0]:
                values["stop_timestamp"] = t
            elif (t - values["stop_timestamp"]).total_seconds() >= self.stop_cutoff:
                values["power"] = 0
                values["power_16_simple"] = 0
                values["cadence"] = 0
                values["power_r"] = 0
                values["power_l"] = 0
                values["lr_balance"] = ":"
        else:
            app_logger.error(f"ANT+ Power(16) err: {delta}")

        pre_values[0:2] = power_values[0:2]
        # on_data timestamp
        values["on_data_timestamp"] = t
        pre_delta = delta[:]
        if np_power is not None:
            self.np_update(values, np_power, t)

        # store raw power
        self.config.state.set_value("ant+_power_values_16", power_values[1])

    def on_data_power_0x11(self, data, power_values, pre_values, pre_delta, values, resume=True):
        # (page), evt_count, wheel_ticks, x, wheel period(2byte), accumulated power(2byte)
        (
            power_values[2],
            power_values[3],
            power_values[0],
            power_values[1],
        ) = self.structPattern[self.name][0x11].unpack(data[0:8])
        t = datetime.now()
        np_power = None

        if pre_values[0] == -1:
            pre_values = power_values
            values["on_data_timestamp"] = t
            values["power"] = 0
            np_power = 0.0
            self.np_update(values, np_power, t)

            if not resume:
                return

            pre_pwr_value = self.config.state.get_value(
                "ant+_power_values_17", pre_values
            )
            pwr_diff = pre_values[1] - pre_pwr_value[1]
            spd_diff = pre_values[3] - pre_pwr_value[3]
            if -65535 <= pwr_diff < 0:
                pwr_diff += 65536
            if -255 <= spd_diff < 0:
                spd_diff += 256
            if pwr_diff > 0:
                values["accumulated_power"] += 128 * math.pi * pwr_diff / 2048
            if spd_diff > 0:
                values["distance"] += self.config.G_WHEEL_CIRCUMFERENCE * spd_diff
            return

        delta = [a - b for (a, b) in zip(power_values, pre_values)]
        if -65535 <= delta[0] < 0:
            delta[0] += 65536
        if -65535 <= delta[1] < 0:
            delta[1] += 65536
        if -255 <= delta[2] < 0:
            delta[2] += 256
        if -255 <= delta[3] < 0:
            delta[3] += 256
        delta_t = (t - values["on_data_timestamp"]).total_seconds()

        if (
            delta[0] > 0
            and delta[1] >= 0
            and delta[2] >= 0
            and delta_t < self.valid_time
        ):
            pwr = 128 * math.pi * delta[1] / delta[0]
            # max value in .fit file is 65536 [w]
            if pwr <= 65535 and (pwr - values["power"]) < self.spike_threshold["power"]:
                values["power"] = pwr
                np_power = pwr
                if self.config.G_MANUAL_STATUS == "START":
                    # unit: J
                    # values['power'] * delta[0] / 2048 #the unit of delta[0] is 1/2048s
                    values["accumulated_power"] += 128 * math.pi * delta[1] / 2048
                # refresh timestamp called from sensor_core
                values["timestamp"] = t
            else:
                self.print_spike("Power(17)", pwr, values["power"], delta, delta_t)

            spd = 3.6 * self.config.G_WHEEL_CIRCUMFERENCE * delta[2] / (delta[0] / 2048)
            # max value in .fit file is 65.536 [m/s]
            if spd <= 65 and (spd - values["speed"]) < self.spike_threshold["speed"]:
                values["speed"] = spd
                if self.config.G_MANUAL_STATUS == "START":
                    values["distance"] += self.config.G_WHEEL_CIRCUMFERENCE * delta[3]
                # refresh timestamp called from sensor_core
                values["timestamp"] = t
            else:
                self.print_spike("Speed(17)", spd, values["speed"], delta, delta_t)
        elif delta[0] == 0 and delta[1] == 0 and delta[2] == 0:
            np_power = 0.0
            if pre_delta[0:3] != [0, 0, 0]:
                values["stop_timestamp"] = t
            elif (t - values["stop_timestamp"]).total_seconds() >= self.stop_cutoff:
                values["power"] = 0
                values["speed"] = 0
        else:
            app_logger.error(f"ANT+ Power(17) err: {delta}")

        pre_values = power_values
        # on_data timestamp
        values["on_data_timestamp"] = t
        pre_delta = delta[:]
        if np_power is not None:
            self.np_update(values, np_power, t)

        # store raw power
        self.config.state.set_value("ant+_power_values_17", power_values)

    def on_data_power_0x12(self, data, power_values, pre_values, pre_delta, values, resume=True):
        # (page), x, x, cadence, period(2byte), accumulatd power(2byte)
        (
            cadence,
            power_values[0],
            power_values[1],
        ) = self.structPattern[self.name][0x12].unpack(data[0:8])
        t = datetime.now()
        np_power = None

        if pre_values[0] == -1:
            pre_values[0:2] = power_values[0:2]
            values["on_data_timestamp"] = t
            values["power"] = 0
            np_power = 0.0
            self.np_update(values, np_power, t)

            if not resume:
                return
            # Exclude when not started. (Pioneer SGY-PM910Z only)
            if self.config.state.get_value("G_MANUAL_STATUS", None) is None:
                return

            pre_pwr_value = self.config.state.get_value(
                "ant+_power_values_18", pre_values[1]
            )
            diff = pre_values[1] - pre_pwr_value
            if -65535 <= diff < 0:
                diff += 65536
            if diff > 0:
                values["accumulated_power"] += 128 * math.pi * diff / 2048
                app_logger.info(
                    f"### resume pwr: diff:{diff} = {pre_values[1]} - {pre_pwr_value} ###"
                )
                app_logger.info(
                    f"### resume pwr: {int(values['accumulated_power'])} [J], +{int(128 * math.pi * diff / 2048)} [J] ###"
                )
            return

        delta = [a - b for (a, b) in zip(power_values, pre_values)]
        if -65535 <= delta[0] < 0:
            delta[0] += 65536
        if -65535 <= delta[1] < 0:
            delta[1] += 65536
        delta_t = (t - values["on_data_timestamp"]).total_seconds()

        if delta[0] > 0 and delta[1] >= 0 and delta_t < self.valid_time:
            pwr = 128 * math.pi * delta[1] / delta[0]
            # max value in .fit file is 65536 [w]
            if pwr <= 65535 and (pwr - values["power"]) < self.spike_threshold["power"]:
                values["power"] = pwr
                np_power = pwr
                values["cadence"] = cadence
                if self.config.G_MANUAL_STATUS == "START":
                    # unit: J
                    # values['power'] * delta[0] / 2048 #the unit of delta[0] is 1/2048s
                    values["accumulated_power"] += 128 * math.pi * delta[1] / 2048
                # refresh timestamp called from sensor_core
                values["timestamp"] = t
            else:
                self.print_spike("Power(18)", pwr, values["power"], delta, delta_t)
        elif delta[0] == 0 and delta[1] == 0:
            np_power = 0.0
            if pre_delta[0:2] != [0, 0]:
                values["stop_timestamp"] = t
            elif (t - values["stop_timestamp"]).total_seconds() >= self.stop_cutoff:
                values["power"] = 0
                values["cadence"] = 0
        else:
            if self.values["manu_id"] == 48 and self.values["model_num"] == 910:
                # Pioneer SGY-PM910Z powermeter mode fix (not pedaling monitor mode)
                # keep increasing accumulated_power at stopping, so it causes a spike at restart
                pass
            else:
                app_logger.error(f"ANT+ Power(18) err: {delta}")

        pre_values[0:2] = power_values[0:2]
        # on_data timestamp
        values["on_data_timestamp"] = t
        pre_delta = delta[:]
        if np_power is not None:
            self.np_update(values, np_power, t)

        # store raw power
        self.config.state.set_value("ant+_power_values_18", power_values[1])
