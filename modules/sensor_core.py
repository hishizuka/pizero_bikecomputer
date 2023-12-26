import asyncio
import math
from datetime import datetime

import numpy as np

_IMPORT_PSUTIL = False
try:
    import psutil

    _IMPORT_PSUTIL = True
except ImportError:
    pass

from logger import app_logger

app_logger.info("detected sensor modules:")

from modules.utils.timer import Timer, log_timers
from .sensor.gps import SensorGPS
from .sensor.sensor_ant import SensorANT
from .sensor.sensor_gpio import SensorGPIO
from .sensor.sensor_i2c import SensorI2C


# Todo: BLE


class SensorCore:
    config = None
    sensor_gps = None
    sensor_ant = None
    sensor_i2c = None
    sensor_gpio = None
    values = {}
    integrated_value_keys = [
        "heart_rate",
        "speed",
        "cadence",
        "power",
        "distance",
        "accumulated_power",
        "w_prime_balance",
        "w_prime_balance_normalized",
        "w_prime_power_sum",
        "w_prime_power_count",
        "w_prime_t",
        "w_prime_sum",
        "grade",
        "grade_spd",
        "glide_ratio",
        "dem_altitude",
        "wind_speed",
        "wind_direction",
        "wind_direction_str",
        "headwind",
        "temperature",
        "cpu_percent",
        "send_time",
    ]
    average_secs = [3, 30, 60]
    average_values = {"heart_rate": {}, "power": {}}
    process = None
    time_threshold = {
        "HR": 15,
        "SPD": 5,
        "CDC": 3,
        "PWR": 3,
        "TEMP": 45,
    }  # valid period of sensor [sec]
    grade_range = 9
    grade_window_size = 5
    graph_keys = [
        "hr_graph",
        "power_graph",
        "w_bal_graph",
        "altitude_gps_graph",
        "altitude_graph",
    ]
    diff_keys = [
        "alt_diff",
        "dst_diff",
        "alt_diff_spd",
        "dst_diff_spd",
    ]
    lp = 4

    def __init__(self, config):
        self.config = config
        self.values["GPS"] = {}
        self.values["ANT+"] = {}
        self.values["BLE"] = {}
        self.values["I2C"] = {}
        self.values["integrated"] = {}

        # reset
        for key in self.integrated_value_keys:
            self.values["integrated"][key] = np.nan
        self.reset_internal()

        for g in self.graph_keys:
            self.values["integrated"][g] = [
                np.nan
            ] * self.config.G_GUI_PERFORMANCE_GRAPH_DISPLAY_RANGE
        for d in self.diff_keys:
            self.values["integrated"][d] = [np.nan] * self.grade_range
        self.values["integrated"]["CPU_MEM"] = ""

        for s in self.average_secs:
            for v in self.average_values:
                self.average_values[v][s] = []
                self.values["integrated"][f"ave_{v}_{s}s"] = np.nan
        if _IMPORT_PSUTIL:
            self.process = psutil.Process()

        if SensorGPS:
            self.sensor_gps = SensorGPS(config, self.values["GPS"])

        timers = [
            Timer(auto_start=False, text="ANT+ : {0:.3f} sec"),
            Timer(auto_start=False, text="I2C  : {0:.3f} sec"),
        ]

        with timers[0]:
            self.sensor_ant = SensorANT(config, self.values["ANT+"])

        with timers[1]:
            self.sensor_i2c = SensorI2C(config, self.values["I2C"])

        self.sensor_gpio = SensorGPIO(config, None)
        self.sensor_gpio.update()

        app_logger.info("[sensor] Initialize:")
        log_timers(timers)

    def start_coroutine(self):
        asyncio.create_task(self.integrate())
        self.sensor_ant.start_coroutine()
        self.sensor_gps.start_coroutine()
        self.sensor_i2c.start_coroutine()

    async def quit(self):
        self.sensor_ant.quit()
        await self.sensor_gps.quit()
        self.sensor_gpio.quit()

    # reset accumulated values
    def reset(self):
        self.sensor_gps.reset()
        self.sensor_ant.reset()
        self.sensor_i2c.reset()
        self.reset_internal()

    def reset_internal(self):
        self.values["integrated"]["distance"] = 0
        self.values["integrated"]["accumulated_power"] = 0
        self.values["integrated"]["w_prime_balance"] = self.config.G_POWER_W_PRIME
        self.values["integrated"]["w_prime_power_sum"] = 0
        self.values["integrated"]["w_prime_power_count"] = 0
        self.values["integrated"]["w_prime_t"] = 0
        self.values["integrated"]["w_prime_sum"] = 0
        self.values["integrated"]["pwr_mean_under_cp"] = 0
        self.values["integrated"]["tau"] = 546 * np.exp(-0.01 * (self.config.G_POWER_CP - 0)) + 316

    async def integrate(self):
        pre_dst = {"ANT+": 0, "GPS": 0}
        pre_ttlwork = {"ANT+": 0}
        pre_alt = {"ANT+": np.nan, "GPS": np.nan}
        pre_alt_spd = {"ANT+": np.nan}
        pre_grade = pre_grade_spd = pre_glide = self.config.G_ANT_NULLVALUE
        diff_sum = {"alt_diff": 0, "dst_diff": 0, "alt_diff_spd": 0, "dst_diff_spd": 0}

        # for w_prime_balance
        # alias for self.values
        v = {"GPS": self.values["GPS"], "I2C": self.values["I2C"]}
        # loop control
        self.wait_time = self.config.G_SENSOR_INTERVAL
        self.actual_loop_interval = self.config.G_SENSOR_INTERVAL

        try:
            while True:
                await asyncio.sleep(self.wait_time)
                start_time = datetime.now()
                # print(start_time, self.wait_time)

                time_profile = [start_time,]
                hr = spd = cdc = pwr = temperature = self.config.G_ANT_NULLVALUE
                grade = grade_spd = glide = self.config.G_ANT_NULLVALUE
                ttlwork_diff = 0
                dst_diff = {"ANT+": 0, "GPS": 0, "USE": 0}
                alt_diff = {"ANT+": 0, "GPS": 0, "USE": 0}
                dst_diff_spd = {"ANT+": 0}
                alt_diff_spd = {"ANT+": 0}
                grade_use = {"ANT+": False, "GPS": False}
                time_profile.append(datetime.now())
                # self.sensor_i2c.update()
                # self.sensor_gps.update()
                self.sensor_ant.update()  # for dummy

                now_time = datetime.now()
                time_profile.append(now_time)

                ant_id_type = self.config.G_ANT["ID_TYPE"]
                delta = {
                    "PWR": {0x10: float("inf"), 0x11: float("inf"), 0x12: float("inf")}
                }
                for key in ["HR", "SPD", "CDC", "TEMP", "GPS"]:
                    delta[key] = float("inf")
                # need for ANT+ ID update
                for key in ["HR", "SPD", "CDC", "PWR", "TEMP"]:
                    if (
                        self.config.G_ANT["USE"][key]
                        and ant_id_type[key] in self.values["ANT+"]
                    ):
                        v[key] = self.values["ANT+"][ant_id_type[key]]

                # make intervals from timestamp
                for key in ["HR", "SPD", "CDC", "TEMP"]:
                    if not self.config.G_ANT["USE"][key]:
                        continue
                    if "timestamp" in v[key]:
                        delta[key] = (now_time - v[key]["timestamp"]).total_seconds()
                    # override:
                    # cadence from power
                    if self.config.G_ANT["TYPE"][key] == 0x0B and key == "CDC":
                        for page in [0x12, 0x10]:
                            if not "timestamp" in v[key][page]:
                                continue
                            delta[key] = (
                                now_time - v[key][page]["timestamp"]
                            ).total_seconds()
                            break
                    # speed from power
                    elif self.config.G_ANT["TYPE"][key] == 0x0B and key == "SPD":
                        if not "timestamp" in v[key][0x11]:
                            continue
                        delta[key] = (
                            now_time - v[key][0x11]["timestamp"]
                        ).total_seconds()
                # timestamp(power)
                if self.config.G_ANT["USE"]["PWR"]:
                    for page in [0x12, 0x11, 0x10]:
                        if not "timestamp" in v["PWR"][page]:
                            continue
                        delta["PWR"][page] = (
                            now_time - v["PWR"][page]["timestamp"]
                        ).total_seconds()
                if "timestamp" in v["GPS"]:
                    delta["GPS"] = (now_time - v["GPS"]["timestamp"]).total_seconds()

                # HeartRate : ANT+
                if self.config.G_ANT["USE"]["HR"]:
                    if delta["HR"] < self.time_threshold["HR"]:
                        hr = v["HR"]["heart_rate"]

                # Cadence : ANT+
                if self.config.G_ANT["USE"]["CDC"]:
                    cdc = 0
                    # get from cadence or speed&cadence sensor
                    if self.config.G_ANT["TYPE"]["CDC"] in [0x79, 0x7A]:
                        if delta["CDC"] < self.time_threshold["CDC"]:
                            cdc = v["CDC"]["cadence"]
                    # get from powermeter
                    elif self.config.G_ANT["TYPE"]["CDC"] == 0x0B:
                        for page in [0x12, 0x10]:
                            if not "timestamp" in v["CDC"][page]:
                                continue
                            if delta["CDC"] < self.time_threshold["CDC"]:
                                cdc = v["CDC"][page]["cadence"]
                                break

                # Power : ANT+(assumed crank type > wheel type)
                if self.config.G_ANT["USE"]["PWR"]:
                    pwr = 0
                    # page18 > 17 > 16, 16simple is not used
                    for page in [0x12, 0x11, 0x10]:
                        if delta["PWR"][page] < self.time_threshold["PWR"]:
                            pwr = v["PWR"][page]["power"]
                            break

                # Speed : ANT+(SPD&CDC, (PWR)) > GPS
                if self.config.G_ANT["USE"]["SPD"]:
                    spd = 0
                    if self.config.G_ANT["TYPE"]["SPD"] in [0x79, 0x7B]:
                        if delta["SPD"] < self.time_threshold["SPD"]:
                            spd = v["SPD"]["speed"]
                    elif self.config.G_ANT["TYPE"]["SPD"] == 0x0B:
                        if delta["SPD"] < self.time_threshold["SPD"]:
                            spd = v["SPD"][0x11]["speed"]
                    # complement from GPS speed when I2C acc sensor is available (using moving status)
                    if (
                        delta["SPD"] > self.time_threshold["SPD"]
                        and spd == 0
                        and v["I2C"]["m_stat"] == 1
                        and v["GPS"]["speed"] > 0
                    ):
                        spd = v["GPS"]["speed"]
                        # print("speed from GPS: delta {}s, {:.1f}km/h".format(delta['SPD'], v['GPS']['speed']*3.6))
                elif "timestamp" in v["GPS"]:
                    spd = 0
                    if (
                        not np.isnan(v["GPS"]["speed"])
                        and delta["GPS"] < self.time_threshold["SPD"]
                    ):
                        spd = v["GPS"]["speed"]

                # Distance: ANT+(SPD, (PWR)) > GPS
                if self.config.G_ANT["USE"]["SPD"]:
                    # normal speed meter
                    if self.config.G_ANT["TYPE"]["SPD"] in [0x79, 0x7B]:
                        if pre_dst["ANT+"] < v["SPD"]["distance"]:
                            dst_diff["ANT+"] = v["SPD"]["distance"] - pre_dst["ANT+"]
                        pre_dst["ANT+"] = v["SPD"]["distance"]
                    elif self.config.G_ANT["TYPE"]["SPD"] == 0x0B:
                        if pre_dst["ANT+"] < v["SPD"][0x11]["distance"]:
                            dst_diff["ANT+"] = (
                                v["SPD"][0x11]["distance"] - pre_dst["ANT+"]
                            )
                        pre_dst["ANT+"] = v["SPD"][0x11]["distance"]
                    dst_diff["USE"] = dst_diff["ANT+"]
                    grade_use["ANT+"] = True
                if "timestamp" in v["GPS"]:
                    if pre_dst["GPS"] < v["GPS"]["distance"]:
                        dst_diff["GPS"] = v["GPS"]["distance"] - pre_dst["GPS"]
                    pre_dst["GPS"] = v["GPS"]["distance"]
                    if not self.config.G_ANT["USE"]["SPD"] and dst_diff["GPS"] > 0:
                        dst_diff["USE"] = dst_diff["GPS"]
                        grade_use["GPS"] = True
                    # ANT+ sensor is not connected from the beginning of the ride
                    elif self.config.G_ANT["USE"]["SPD"]:
                        if (
                            delta["SPD"] == np.inf
                            and dst_diff["ANT+"] == 0
                            and dst_diff["GPS"] > 0
                        ):
                            dst_diff["USE"] = dst_diff["GPS"]
                            grade_use["ANT+"] = False
                            grade_use["GPS"] = True

                # Total Power: ANT+
                if self.config.G_ANT["USE"]["PWR"]:
                    # both type are not exist in same ID(0x12:crank, 0x11:wheel)
                    # if 0x12 or 0x11 exists, never take 0x10
                    for page in [0x12, 0x11, 0x10]:
                        if "timestamp" in v["PWR"][page]:
                            if (
                                pre_ttlwork["ANT+"]
                                < v["PWR"][page]["accumulated_power"]
                            ):
                                ttlwork_diff = (
                                    v["PWR"][page]["accumulated_power"]
                                    - pre_ttlwork["ANT+"]
                                )
                            pre_ttlwork["ANT+"] = v["PWR"][page]["accumulated_power"]
                            # never take other powermeter
                            break

                # Temperature : ANT+
                if self.config.G_ANT["USE"]["TEMP"]:
                    if delta["TEMP"] < self.time_threshold["TEMP"]:
                        temperature = v["TEMP"]["temperature"]
                elif not np.isnan(v["I2C"]["temperature"]):
                    temperature = v["I2C"]["temperature"]

                # altitude
                if not np.isnan(v["I2C"]["pre_altitude"]):
                    alt = v["I2C"]["altitude"]
                    # for grade (distance base)
                    for key in ["ANT+", "GPS"]:
                        if dst_diff[key] > 0:
                            alt_diff[key] = alt - pre_alt[key]
                        pre_alt[key] = alt
                    if self.config.G_ANT["USE"]["SPD"]:
                        alt_diff["USE"] = alt_diff["ANT+"]
                    elif not self.config.G_ANT["USE"]["SPD"] and dst_diff["GPS"] > 0:
                        alt_diff["USE"] = alt_diff["GPS"]
                    # for grade (speed base)
                    if self.config.G_ANT["USE"]["SPD"]:
                        if dst_diff["ANT+"] > 0:
                            alt_diff_spd["ANT+"] = alt - pre_alt_spd["ANT+"]
                        pre_alt_spd["ANT+"] = alt

                # dem_altitude
                if self.config.G_USE_DEM_TILE:
                    self.values["integrated"][
                        "dem_altitude"
                    ] = await self.config.api.get_altitude(
                        [v["GPS"]["lon"], v["GPS"]["lat"]]
                    )

                # wind
                if self.config.G_USE_WIND_OVERLAY_MAP:
                    (
                        self.values["integrated"]["wind_speed"], 
                        self.values["integrated"]["wind_direction"],
                        self.values["integrated"]["wind_direction_str"],
                        self.values["integrated"]["headwind"]
                    ) = await self.config.api.get_wind(
                        [v["GPS"]["lon"], v["GPS"]["lat"]], v["GPS"]["track"]
                    )

                # grade (distance base)
                if dst_diff["USE"] > 0:
                    for key in ["alt_diff", "dst_diff"]:
                        self.values["integrated"][key][0:-1] = self.values[
                            "integrated"
                        ][key][1:]
                        self.values["integrated"][key][-1] = eval(key + "['USE']")
                        # diff_sum[key] = np.mean(self.values['integrated'][key][-self.grade_window_size:])
                        diff_sum[key] = np.nansum(
                            self.values["integrated"][key][-self.grade_window_size :]
                        )
                    # set grade
                    gl = self.config.G_ANT_NULLVALUE
                    gr = self.config.G_ANT_NULLVALUE
                    x = self.config.G_ANT_NULLVALUE
                    y = diff_sum["alt_diff"]
                    if grade_use["ANT+"]:
                        x = math.sqrt(
                            abs(diff_sum["dst_diff"] ** 2 - diff_sum["alt_diff"] ** 2)
                        )
                    elif grade_use["GPS"]:
                        x = diff_sum["dst_diff"]
                    if x > 0:
                        # gr = int(round(100 * y / x))
                        gr = self.conv_grade(100 * y / x)
                    if y != 0.0:
                        gl = int(round(-1 * x / y))
                    grade = pre_grade = gr
                    glide = pre_glide = gl
                # for sometimes ANT+ distance is 0 although status is running
                elif dst_diff["USE"] == 0 and self.config.G_STOPWATCH_STATUS == "START":
                    grade = pre_grade
                    glide = pre_glide

                # grade (speed base)
                if self.config.G_ANT["USE"]["SPD"]:
                    dst_diff_spd["ANT+"] = spd * self.actual_loop_interval
                    for key in ["alt_diff_spd", "dst_diff_spd"]:
                        self.values["integrated"][key][0:-1] = self.values[
                            "integrated"
                        ][key][1:]
                        self.values["integrated"][key][-1] = eval(key + "['ANT+']")
                        diff_sum[key] = np.mean(
                            self.values["integrated"][key][-self.grade_window_size :]
                        )
                        # diff_sum[key] = np.nansum(self.values['integrated'][key][-self.grade_window_size:])
                    # set grade
                    x = diff_sum["dst_diff_spd"] ** 2 - diff_sum["alt_diff_spd"] ** 2
                    y = diff_sum["alt_diff_spd"]
                    gr = self.config.G_ANT_NULLVALUE
                    if x > 0:
                        x = math.sqrt(x)
                        gr = self.conv_grade(100 * y / x)
                    grade_spd = pre_grade_spd = gr
                # for sometimes speed sensor value is missing in running
                elif (
                    dst_diff_spd["ANT+"] == 0
                    and self.config.G_STOPWATCH_STATUS == "START"
                ):
                    grade_spd = pre_grade_spd

                self.values["integrated"]["heart_rate"] = hr
                self.values["integrated"]["speed"] = spd
                self.values["integrated"]["cadence"] = cdc
                self.values["integrated"]["power"] = pwr
                self.values["integrated"]["distance"] += dst_diff["USE"]
                self.values["integrated"]["accumulated_power"] += ttlwork_diff
                self.values["integrated"]["grade"] = grade
                self.values["integrated"]["grade_spd"] = grade_spd
                self.values["integrated"]["glide_ratio"] = glide
                self.values["integrated"]["temperature"] = temperature
                
                #set self.values["integrated"]["w_prime_balance_normalized"] etc
                if self.config.G_ANT["USE"]["PWR"]:
                    self.calc_w_prime_balance(pwr)

                for g in self.graph_keys:
                    self.values["integrated"][g][:-1] = self.values["integrated"][g][1:]
                self.values["integrated"]["hr_graph"][-1] = hr
                self.values["integrated"]["power_graph"][-1] = pwr
                self.values["integrated"]["w_bal_graph"][-1] = self.values[
                    "integrated"
                ]["w_prime_balance_normalized"]
                self.values["integrated"]["altitude_gps_graph"][-1] = v["GPS"]["alt"]
                self.values["integrated"]["altitude_graph"][-1] = v["I2C"]["altitude"]

                # average power, heart_rate
                if self.config.G_ANT["USE"]["PWR"] and not np.isnan(pwr):
                    self.get_ave_values("power", pwr)
                if self.config.G_ANT["USE"]["HR"] and not np.isnan(hr):
                    self.get_ave_values("heart_rate", hr)

                time_profile.append(datetime.now())

                # toggle auto stop
                # ANT+ or GPS speed is available
                if not np.isnan(spd) and self.config.G_MANUAL_STATUS == "START":
                    # speed from ANT+ or GPS
                    flag_spd = False
                    if spd >= self.config.G_AUTOSTOP_CUTOFF:
                        flag_spd = True

                    # use moving status of accelerometer because of excluding erroneous speed values when stopping
                    flag_moving = False
                    if v["I2C"]["m_stat"] == 1:
                        flag_moving = True

                    # flag_moving is not considered (set True) as follows,
                    # accelerometer is not available (nan)
                    # ANT+ speed sensor is available
                    if (
                        np.isnan(v["I2C"]["m_stat"])
                        or self.config.G_ANT["USE"]["SPD"]
                        or self.config.G_DUMMY_OUTPUT
                    ):
                        flag_moving = True

                    if (
                        self.config.G_STOPWATCH_STATUS == "STOP"
                        and flag_spd
                        and flag_moving
                        and self.config.logger is not None
                    ):
                        self.config.logger.start_and_stop()
                    elif (
                        self.config.G_STOPWATCH_STATUS == "START"
                        and (not flag_spd or not flag_moving)
                        and self.config.logger is not None
                    ):
                        self.config.logger.start_and_stop()

                # ANT+ or GPS speed is not available
                elif np.isnan(spd) and self.config.G_MANUAL_STATUS == "START":
                    # stop recording if speed is broken
                    if (
                        (self.config.G_ANT["USE"]["SPD"] or "timestamp" in v["GPS"])
                        and self.config.G_STOPWATCH_STATUS == "START"
                        and self.config.logger is not None
                    ):
                        self.config.logger.start_and_stop()

                # auto backlight
                if self.config.display.auto_brightness and not np.isnan(
                    v["I2C"]["light"]
                ):
                    if v["I2C"]["light"] <= self.config.G_AUTO_BACKLIGHT_CUTOFF:
                        self.config.display.set_brightness(3)

                        if self.config.G_MANUAL_STATUS == "START":
                            self.sensor_ant.set_light_mode("FLASH_LOW", auto=True)

                    else:
                        self.config.display.set_brightness(0)

                        if self.config.G_MANUAL_STATUS == "START":
                            self.sensor_ant.set_light_mode("OFF", auto=True)

                # cpu and memory
                if _IMPORT_PSUTIL:
                    self.values["integrated"]["cpu_percent"] = int(
                        self.process.cpu_percent(interval=None)
                    )
                    self.values["integrated"][
                        "CPU_MEM"
                    ] = "{0:^2.0f}% ({1}) / ALL {2:^2.0f}%,  {3:^2.0f}%".format(
                        self.values["integrated"][
                            "cpu_percent"
                        ],  # self.process.cpu_percent(interval=None),
                        self.process.num_threads(),
                        psutil.cpu_percent(interval=None),
                        self.process.memory_percent(),
                    )

                # adjust loop time
                time_profile.append(datetime.now())
                sec_diff = []
                time_progile_sec = 0
                for i in range(len(time_profile)):
                    if i == 0:
                        continue
                    sec_diff.append(
                        "{0:.6f}".format(
                            (time_profile[i] - time_profile[i - 1]).total_seconds()
                        )
                    )
                    time_progile_sec += (
                        time_profile[i] - time_profile[i - 1]
                    ).total_seconds()
                if time_progile_sec > 1.5 * self.config.G_SENSOR_INTERVAL:
                    app_logger.warning(
                        f"too long loop time: {datetime.now().strftime('%Y%m%d %H:%M:%S')}, sec_diff: {sec_diff}"
                    )

                loop_time = (datetime.now() - start_time).total_seconds()
                d1, d2 = divmod(loop_time, self.config.G_SENSOR_INTERVAL)
                if d1 > self.config.G_SENSOR_INTERVAL * 10:  # [s]
                    app_logger.warning(
                        f"too long loop_time({self.__class__.__name__}):{loop_time:.2f}, interval:{self.config.G_SENSOR_INTERVAL:.1f}"
                    )
                    d1 = d2 = 0
                self.wait_time = self.config.G_SENSOR_INTERVAL - d2
                self.actual_loop_interval = (d1 + 1) * self.config.G_SENSOR_INTERVAL
        except asyncio.CancelledError:
            pass

    @staticmethod
    def conv_grade(gr):
        g = gr
        if -1.5 < g < 1.5:
            g = 0
        return int(g)

    def get_lp_filtered_value(self, value, pre):
        # value must be initialized with None
        if np.isnan(pre):
            o = value
        else:
            o = pre * (self.lp - 1) / self.lp + value / self.lp
        p = value
        return o, p

    def get_ave_values(self, k, v):
        for sec in self.average_secs:
            if len(self.average_values[k][sec]) < sec:
                self.average_values[k][sec].append(v)
            else:
                self.average_values[k][sec][:-1] = self.average_values[k][sec][1:]
                self.average_values[k][sec][-1] = v
            self.values["integrated"]["ave_{}_{}s".format(k, sec)] = int(
                np.mean(self.average_values[k][sec])
            )

    def calc_w_prime_balance(self, pwr):
        # https://medium.com/critical-powers/comparison-of-wbalance-algorithms-8838173e2c15

        v = self.values["integrated"]
        pwr_cp_diff = pwr - self.config.G_POWER_CP
        # Waterworth algorighm
        if self.config.G_POWER_W_PRIME_ALGORITHM == "WATERWORTH":
            if pwr < self.config.G_POWER_CP:
                v["w_prime_power_sum"] = v["w_prime_power_sum"] + pwr
                v["w_prime_power_count"] = v["w_prime_power_count"] + 1
                v["pwr_mean_under_cp"] = v["w_prime_power_sum"] / v["w_prime_power_count"]
                v["tau"] = (
                    546
                    * np.exp(-0.01 * (self.config.G_POWER_CP - v["pwr_mean_under_cp"]))
                    + 316
                )
            v["w_prime_sum"] += max(0, pwr_cp_diff) * np.exp(v["w_prime_t"] / v["tau"])
            v["w_prime_t"] += self.config.G_SENSOR_INTERVAL
            v["w_prime_balance"] = (
                self.config.G_POWER_W_PRIME
                 - v["w_prime_sum"]*np.exp(-v["w_prime_t"] / v["tau"])
            )

        # Differential algorithm
        elif self.config.G_POWER_W_PRIME_ALGORITHM == "DIFFERENTIAL":
            cp_pwr_diff = -pwr_cp_diff
            if cp_pwr_diff < 0:
                # consume
                v["w_prime_balance"] += cp_pwr_diff
            else:
                # recovery
                v["w_prime_balance"] += (
                    cp_pwr_diff
                    * (self.config.G_POWER_W_PRIME - v["w_prime_balance"])
                    / self.config.G_POWER_W_PRIME
                )

        v["w_prime_balance_normalized"] = int(
            v["w_prime_balance"] / self.config.G_POWER_W_PRIME*100
        )
