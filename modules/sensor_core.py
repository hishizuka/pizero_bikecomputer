import asyncio
import math
import time
from datetime import datetime

import numpy as np

_IMPORT_PSUTIL = False
try:
    import psutil
    _IMPORT_PSUTIL = True
except ImportError:
    pass

from modules.app_logger import app_logger

app_logger.info("detected sensor modules:")

from modules.utils.timer import Timer, log_timers
from .sensor.gps import SensorGPS
from .sensor.sensor_ant import SensorANT
from .sensor.sensor_ble import SensorBLE
from .sensor.sensor_gpio import SensorGPIO
from .sensor.sensor_i2c import SensorI2C


class SensorCore:
    config = None
    sensor_gps = None
    sensor_ant = None
    sensor_ble = None
    sensor_i2c = None
    sensor_gpio = None
    values = {}
    integrated_value_keys = [
        "heart_rate",
        "speed",
        "cadence",
        "power",
        "normalized_power",
        "distance",
        "accumulated_power",
        "w_prime_balance",
        "w_prime_balance_normalized",
        "w_prime_power_sum",
        "w_prime_power_count",
        "w_prime_t",
        "w_prime_sum",
        "tss",
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
    brakelight_spd = []
    brakelight_spd_range = 4
    brakelight_spd_cutoff = 4  # 4*3.6 = 14.4 [km/h]
    auto_backlight_brightness = []
    auto_backlight_brightness_range = 3
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

    cpu_status_bar_color_low = "#000000"
    cpu_status_bar_color_mid = "#ffd166"
    cpu_status_bar_color_high = "#ff4d4d"

    status_quit = False
    _PERF_SENSOR_LOG_INTERVAL_SEC = 30.0

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
        self.brakelight_spd = [0] * self.brakelight_spd_range
        self.auto_backlight_brightness = \
            [self.config.G_AUTO_BACKLIGHT_CUTOFF+1] * self.auto_backlight_brightness_range
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
            Timer(auto_start=False, text="  ANT+ : {0:.3f} sec"),
            Timer(auto_start=False, text="  BLE  : {0:.3f} sec"),
            Timer(auto_start=False, text="  I2C  : {0:.3f} sec"),
        ]

        with timers[0]:
            self.sensor_ant = SensorANT(config, self.values["ANT+"])

        with timers[1]:
            self.sensor_ble = SensorBLE(config, self.values["BLE"])

        with timers[2]:
            self.sensor_i2c = SensorI2C(config, self.values["I2C"])

        self.sensor_gpio = SensorGPIO(config, None)
        self.sensor_gpio.update()

        app_logger.info("[sensor] Initialize:")
        log_timers(timers)

        # Emit debug metrics at a fixed cadence to reduce log volume.
        self._perf_sensor_window = max(
            1,
            int(
                round(
                    self._PERF_SENSOR_LOG_INTERVAL_SEC
                    / max(self.config.G_SENSOR_INTERVAL, 0.001)
                )
            ),
        )
        self._init_perf_sensor_metrics()

    @staticmethod
    def _safe_stat(values, func, *args):
        if not values:
            return float("nan")
        return float(func(values, *args))

    @staticmethod
    def _elapsed_since_timestamp(now_time, sensor_values):
        timestamp = sensor_values.get("timestamp")
        if timestamp is None:
            return None
        return (now_time - timestamp).total_seconds()

    def _update_delta_from_pages(self, now_time, source_values, pages, delta_target):
        for page in pages:
            elapsed = self._elapsed_since_timestamp(now_time, source_values[page])
            if elapsed is None:
                continue
            if isinstance(delta_target, dict):
                delta_target[page] = elapsed
            else:
                delta_target = elapsed
        return delta_target

    def _init_perf_sensor_metrics(self):
        self._perf_sensor_calls = 0
        self._perf_sensor_loop_ms = []
        self._perf_sensor_preprocess_ms_sum = 0.0
        self._perf_sensor_ant_update_ms_sum = 0.0
        self._perf_sensor_calc_ms_sum = 0.0
        self._perf_sensor_post_ms_sum = 0.0
        self._perf_sensor_adjust_ms_sum = 0.0
        self._perf_sensor_api_alt_ms_sum = 0.0
        self._perf_sensor_api_alt_calls = 0
        self._perf_sensor_api_wind_ms_sum = 0.0
        self._perf_sensor_api_wind_calls = 0

    def _maybe_log_perf_sensor_window(self):
        if self._perf_sensor_calls < self._perf_sensor_window:
            return

        loop_avg_ms = self._safe_stat(self._perf_sensor_loop_ms, np.mean)
        loop_p95_ms = self._safe_stat(self._perf_sensor_loop_ms, np.percentile, 95)
        loop_max_ms = self._safe_stat(self._perf_sensor_loop_ms, np.max)

        preprocess_avg_ms = (
            self._perf_sensor_preprocess_ms_sum / self._perf_sensor_calls
        )
        ant_update_avg_ms = (
            self._perf_sensor_ant_update_ms_sum / self._perf_sensor_calls
        )
        calc_avg_ms = self._perf_sensor_calc_ms_sum / self._perf_sensor_calls
        post_avg_ms = self._perf_sensor_post_ms_sum / self._perf_sensor_calls
        adjust_avg_ms = self._perf_sensor_adjust_ms_sum / self._perf_sensor_calls

        if self._perf_sensor_api_alt_calls > 0:
            api_alt_avg_ms = (
                self._perf_sensor_api_alt_ms_sum / self._perf_sensor_api_alt_calls
            )
        else:
            api_alt_avg_ms = float("nan")

        if self._perf_sensor_api_wind_calls > 0:
            api_wind_avg_ms = (
                self._perf_sensor_api_wind_ms_sum / self._perf_sensor_api_wind_calls
            )
        else:
            api_wind_avg_ms = float("nan")

        cpu_percent = self.values["integrated"].get("cpu_percent", np.nan)
        app_logger.debug(
            "[PERF_SENSOR] "
            f"win={self._perf_sensor_window} "
            f"calls={self._perf_sensor_calls} "
            f"loop_avg_ms={loop_avg_ms:.3f} "
            f"loop_p95_ms={loop_p95_ms:.3f} "
            f"loop_max_ms={loop_max_ms:.3f} "
            f"preprocess_avg_ms={preprocess_avg_ms:.3f} "
            f"ant_update_avg_ms={ant_update_avg_ms:.3f} "
            f"calc_avg_ms={calc_avg_ms:.3f} "
            f"post_avg_ms={post_avg_ms:.3f} "
            f"adjust_avg_ms={adjust_avg_ms:.3f} "
            f"wait_s={self.wait_time:.3f} "
            f"interval_s={self.actual_loop_interval:.3f} "
            f"cpu={cpu_percent}"
        )
        app_logger.debug(
            "[PERF_SENSOR_DETAIL] "
            f"win={self._perf_sensor_window} "
            f"api_alt_calls={self._perf_sensor_api_alt_calls} "
            f"api_alt_avg_ms={api_alt_avg_ms:.3f} "
            f"api_wind_calls={self._perf_sensor_api_wind_calls} "
            f"api_wind_avg_ms={api_wind_avg_ms:.3f} "
            f"stopwatch={self.config.G_STOPWATCH_STATUS} "
            f"manual={self.config.G_MANUAL_STATUS}"
        )

        self._init_perf_sensor_metrics()

    def start_coroutine(self):
        asyncio.create_task(self.integrate())
        self.sensor_ant.start_coroutine()
        self.sensor_ble.start_coroutine()
        self.sensor_gps.start_coroutine()
        self.sensor_i2c.start_coroutine()

    async def quit(self):
        self.status_quit = True
        self.sensor_i2c.quit()
        self.sensor_ant.quit()
        self.sensor_ble.quit()
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
        self.values["integrated"]["normalized_power"] = np.nan
        self.values["integrated"]["w_prime_balance"] = self.config.G_POWER_W_PRIME
        self.values["integrated"]["w_prime_power_sum"] = 0
        self.values["integrated"]["w_prime_power_count"] = 0
        self.values["integrated"]["w_prime_t"] = 0
        self.values["integrated"]["w_prime_sum"] = 0
        self.values["integrated"]["pwr_mean_under_cp"] = 0
        self.values["integrated"]["tau"] = 546 * np.exp(-0.01 * (self.config.G_POWER_CP - 0)) + 316

        self.values["integrated"]["tss"] = 0.0

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

        while not self.status_quit:
            await asyncio.sleep(self.wait_time)
            loop_start_perf = time.perf_counter()
            api_alt_elapsed_ms = 0.0
            api_wind_elapsed_ms = 0.0
            start_time = datetime.now()
            # print(start_time, self.wait_time)

            time_profile = [start_time,]
            hr = spd = cdc = pwr = temperature = self.config.G_ANT_NULLVALUE
            npwr = self.config.G_ANT_NULLVALUE
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
            ant_update_start = time.perf_counter()
            preprocess_elapsed_ms = (ant_update_start - loop_start_perf) * 1000.0
            self.sensor_ant.update()  # for dummy
            ant_update_elapsed_ms = (time.perf_counter() - ant_update_start) * 1000.0
            calc_start_perf = time.perf_counter()

            now_time = datetime.now()
            time_profile.append(now_time)

            ant_id_type = self.config.G_ANT["ID_TYPE"]
            delta = {
                "PWR": {0x10: float("inf"), 0x11: float("inf"), 0x12: float("inf")},
                "CDC-PWR": {0x12: float("inf"), 0x10: float("inf")},
            }
            for key in ["HR", "SPD", "CDC", "TEMP"]:
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
                elapsed = self._elapsed_since_timestamp(now_time, v[key])
                if elapsed is not None:
                    delta[key] = elapsed

            # override/page-based deltas from power profile pages
            page_delta_specs = (
                (
                    "CDC",
                    "CDC-PWR",
                    [0x12, 0x10],
                    self.config.G_ANT["USE"]["CDC"]
                    and self.config.G_ANT["TYPE"]["CDC"] == 0x0B,
                ),
                (
                    "SPD",
                    "SPD",
                    [0x11],
                    self.config.G_ANT["USE"]["SPD"]
                    and self.config.G_ANT["TYPE"]["SPD"] == 0x0B,
                ),
                (
                    "PWR",
                    "PWR",
                    [0x12, 0x11, 0x10],
                    self.config.G_ANT["USE"]["PWR"],
                ),
            )
            for sensor_key, delta_key, pages, enabled in page_delta_specs:
                if not enabled:
                    continue
                if sensor_key not in v:
                    continue
                delta[delta_key] = self._update_delta_from_pages(
                    now_time,
                    v[sensor_key],
                    pages,
                    delta[delta_key],
                )
            elapsed = self._elapsed_since_timestamp(now_time, v["GPS"])
            if elapsed is not None:
                delta["GPS"] = elapsed

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
                        if delta["CDC-PWR"][page] < self.time_threshold["CDC"]:
                            cdc = v["CDC"][page]["cadence"]
                            break

            # Power : ANT+(assumed crank type > wheel type)
            if self.config.G_ANT["USE"]["PWR"]:
                pwr = 0
                # page18 > 17 > 16, 16simple is not used
                for page in [0x12, 0x11, 0x10]:
                    if delta["PWR"][page] < self.time_threshold["PWR"]:
                        pwr = v["PWR"][page]["power"]
                        npwr = v["PWR"][page].get(
                            "normalized_power", self.config.G_ANT_NULLVALUE
                        )
                        break

            # Speed : ANT+(SPD&CDC, (PWR)) > GPS
            if self.config.G_ANT["USE"]["SPD"]:
                spd = 0
                if delta["SPD"] < self.time_threshold["SPD"]:
                    if self.config.G_ANT["TYPE"]["SPD"] in [0x79, 0x7B]:
                        spd = v["SPD"]["speed"]
                    elif self.config.G_ANT["TYPE"]["SPD"] == 0x0B:
                        spd = v["SPD"][0x11]["speed"]
                # complement from GPS speed when I2C acc sensor is available (using moving status)
                else:
                    if v["I2C"]["m_stat"] == 1 and v["GPS"]["speed"] > 0:
                        spd = v["GPS"]["speed"]
            elif not np.isnan(v["GPS"]["speed"]):
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
                api_alt_start = time.perf_counter()
                self.values["integrated"][
                    "dem_altitude"
                ] = await self.config.api.get_altitude(
                    [v["GPS"]["lon"], v["GPS"]["lat"]]
                )
                api_alt_elapsed_ms = (time.perf_counter() - api_alt_start) * 1000.0

            # wind
            if self.config.G_USE_WIND_DATA_SOURCE:
                api_wind_start = time.perf_counter()
                (
                    self.values["integrated"]["wind_speed"], 
                    self.values["integrated"]["wind_direction"],
                    self.values["integrated"]["wind_direction_str"],
                    self.values["integrated"]["headwind"]
                ) = await self.config.api.get_wind(
                    [v["GPS"]["lon"], v["GPS"]["lat"]], v["GPS"]["track"]
                )
                api_wind_elapsed_ms = (
                    time.perf_counter() - api_wind_start
                ) * 1000.0

            # grade (distance base)
            if dst_diff["USE"] > 0:
                diff_sources = {
                    "alt_diff": alt_diff,
                    "dst_diff": dst_diff,
                }
                for key in ["alt_diff", "dst_diff"]:
                    self.values["integrated"][key][0:-1] = self.values[
                        "integrated"
                    ][key][1:]
                    self.values["integrated"][key][-1] = diff_sources[key]["USE"]
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
                diff_sources_spd = {
                    "alt_diff_spd": alt_diff_spd,
                    "dst_diff_spd": dst_diff_spd,
                }
                for key in ["alt_diff_spd", "dst_diff_spd"]:
                    self.values["integrated"][key][0:-1] = self.values[
                        "integrated"
                    ][key][1:]
                    self.values["integrated"][key][-1] = diff_sources_spd[key]["ANT+"]
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
            # NP represents overall ride intensity; keep last value during stops.
            if not np.isnan(npwr):
                self.values["integrated"]["normalized_power"] = npwr
            self.values["integrated"]["distance"] += dst_diff["USE"]
            self.values["integrated"]["accumulated_power"] += ttlwork_diff
            self.values["integrated"]["grade"] = grade
            self.values["integrated"]["grade_spd"] = grade_spd
            self.values["integrated"]["glide_ratio"] = glide
            self.values["integrated"]["temperature"] = temperature
            
            #set self.values["integrated"]["w_prime_balance_normalized"] etc
            if self.config.G_ANT["USE"]["PWR"]:
                self.calc_w_prime_balance(pwr)
                self.calc_form_metrics(pwr)

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
            calc_elapsed_ms = (time.perf_counter() - calc_start_perf) * 1000.0
            post_start_perf = time.perf_counter()

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

            # auto backlight & brake light with brightness
            auto_light = False
            if (
                self.config.display.use_auto_backlight
                and not np.isnan(v["I2C"]["light"])
            ):
                self.auto_backlight_brightness[:-1] = self.auto_backlight_brightness[1:]
                self.auto_backlight_brightness[-1] = v["I2C"]["light"]
                brightness = int(np.mean(self.auto_backlight_brightness))

                if brightness <= self.config.G_AUTO_BACKLIGHT_CUTOFF:
                    self.config.display.set_minimum_brightness()
                    auto_light = True
                else:
                    self.config.display.set_brightness(0)

            # brake light with speed
            if not np.isnan(self.values["integrated"]["speed"]):
                self.brakelight_spd[:-1] = self.brakelight_spd[1:]
                self.brakelight_spd[-1] = self.values["integrated"]["speed"]

                # 1: all past speeds are less than brakelight_spd_cutoff
                cond_1 = all((s < self.brakelight_spd_cutoff for s in self.brakelight_spd))
                # 2-1: current speed exceeds brakelight_spd_cutoff
                cond_2_1 = self.values["integrated"]["speed"] > self.brakelight_spd_cutoff
                # 2-2: current speed reduced by 5% from the speed [brakelight_spd_range] seconds ago
                #  30km/h: 1.2km/h(4%), 20km/h: 0.8km/h(4%)
                cond_2_2 = self.brakelight_spd[0] - self.brakelight_spd[-1] > self.brakelight_spd[0]*0.04
                if (cond_1 or (cond_2_1 and cond_2_2)):
                    auto_light = True

            if self.config.G_ANT["USE_AUTO_LIGHT"] and self.config.G_MANUAL_STATUS == "START":
                if auto_light:
                    self.sensor_ant.set_light_mode("FLASH_LOW", auto=True)
                else:
                    self.sensor_ant.set_light_mode("OFF", auto=True)

            # cpu and memory
            if _IMPORT_PSUTIL:
                with self.process.oneshot():
                    self.values["integrated"]["cpu_percent"] = int(
                        self.process.cpu_percent(interval=None)
                    )
                    self._update_status_bar_color_by_cpu_usage()
                    self.values["integrated"][
                        "CPU_MEM"
                    ] = "{0:^2.0f}%({1}), {2:^2.0f}MB".format(
                        self.values["integrated"]["cpu_percent"],
                        self.process.num_threads(),
                        self.process.memory_info().rss/1024**2,
                    )

            # adjust loop time
            time_profile.append(datetime.now())
            post_elapsed_ms = (time.perf_counter() - post_start_perf) * 1000.0
            adjust_start_perf = time.perf_counter()
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
                    f"too long loop time, sec_diff: {sec_diff}"
                    f"(def/sensor_ant.update()/make variables(too long)/post-processing)"
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

            adjust_elapsed_ms = (time.perf_counter() - adjust_start_perf) * 1000.0
            loop_elapsed_ms = (time.perf_counter() - loop_start_perf) * 1000.0

            self._perf_sensor_calls += 1
            self._perf_sensor_loop_ms.append(loop_elapsed_ms)
            self._perf_sensor_preprocess_ms_sum += preprocess_elapsed_ms
            self._perf_sensor_ant_update_ms_sum += ant_update_elapsed_ms
            self._perf_sensor_calc_ms_sum += calc_elapsed_ms
            self._perf_sensor_post_ms_sum += post_elapsed_ms
            self._perf_sensor_adjust_ms_sum += adjust_elapsed_ms

            if self.config.G_USE_DEM_TILE:
                self._perf_sensor_api_alt_calls += 1
                self._perf_sensor_api_alt_ms_sum += api_alt_elapsed_ms
            if self.config.G_USE_WIND_DATA_SOURCE:
                self._perf_sensor_api_wind_calls += 1
                self._perf_sensor_api_wind_ms_sum += api_wind_elapsed_ms

            self._maybe_log_perf_sensor_window()

    @staticmethod
    def conv_grade(gr):
        g = gr
        if -1.5 < g < 1.5:
            g = 0
        return int(g)

    def _get_status_bar_color_by_cpu_usage(self, cpu_percent):
        if cpu_percent < 20:
            return self.cpu_status_bar_color_low
        if cpu_percent < 50:
            return self.cpu_status_bar_color_mid
        return self.cpu_status_bar_color_high

    def _update_status_bar_color_by_cpu_usage(self):
        gui = getattr(self.config, "gui", None)
        if gui is None:
            return

        status_bar = getattr(gui, "status_bar", None)
        if status_bar is None:
            return

        status_bar.set_background_color(
            self._get_status_bar_color_by_cpu_usage(
                self.values["integrated"]["cpu_percent"]
            )
        )

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
        dt = self.config.G_SENSOR_INTERVAL
        pwr_cp_diff = pwr - self.config.G_POWER_CP

        # Waterworth algorithm
        if self.config.G_POWER_W_PRIME_ALGORITHM == "WATERWORTH":
            if pwr < self.config.G_POWER_CP:
                v["w_prime_power_sum"] = v["w_prime_power_sum"] + pwr
                v["w_prime_power_count"] = v["w_prime_power_count"] + 1
                v["pwr_mean_under_cp"] = v["w_prime_power_sum"] / v["w_prime_power_count"]
                tau_new = (
                    546
                    * np.exp(-0.01 * (self.config.G_POWER_CP - v["pwr_mean_under_cp"]))
                    + 316
                )
                # When tau changes, rescale w_prime_sum so W'balance is continuous.
                # W'bal = W' - w_prime_sum * exp(-t/tau) must be preserved.
                if tau_new != v["tau"] and v["w_prime_t"] > 0:
                    w_bal = (
                        self.config.G_POWER_W_PRIME
                        - v["w_prime_sum"] * np.exp(-v["w_prime_t"] / v["tau"])
                    )
                    v["w_prime_sum"] = (
                        self.config.G_POWER_W_PRIME - w_bal
                    ) * np.exp(v["w_prime_t"] / tau_new)
                v["tau"] = tau_new

            # Accumulate: (P-CP)+ * exp(t/tau) * dt [J scaled for later exp(-T/tau)]
            v["w_prime_sum"] += max(0, pwr_cp_diff) * dt * np.exp(v["w_prime_t"] / v["tau"])
            v["w_prime_t"] += dt
            v["w_prime_balance"] = (
                self.config.G_POWER_W_PRIME
                - v["w_prime_sum"] * np.exp(-v["w_prime_t"] / v["tau"])
            )

        # Differential algorithm
        elif self.config.G_POWER_W_PRIME_ALGORITHM == "DIFFERENTIAL":
            cp_pwr_diff = -pwr_cp_diff
            if cp_pwr_diff < 0:
                # consume (P > CP): deplete proportional to excess power and time
                v["w_prime_balance"] += cp_pwr_diff * dt
            else:
                # recovery (P < CP): recover toward W' with exponential approach
                v["w_prime_balance"] += (
                    cp_pwr_diff
                    * (self.config.G_POWER_W_PRIME - v["w_prime_balance"])
                    / self.config.G_POWER_W_PRIME
                    * dt
                )

        # Clamp to [0, W']: balance cannot exceed full charge or go physically undefined
        v["w_prime_balance"] = min(
            max(v["w_prime_balance"], 0), self.config.G_POWER_W_PRIME
        )
        v["w_prime_balance_normalized"] = round(
            v["w_prime_balance"] / self.config.G_POWER_W_PRIME * 100,
            1
        )

    def calc_form_metrics(self, pwr):
        """Compute TSS each sensor interval.

        TSS (Training Stress Score):
            Incremental approximation: (P/CP)^2 * dt/3600 * 100 per second.
            Uses CP as a proxy for FTP.
        """
        v = self.values["integrated"]
        if not np.isnan(pwr) and pwr > 0:
            cp = self.config.G_POWER_CP
            dt = self.config.G_SENSOR_INTERVAL
            v["tss"] += (pwr / cp) ** 2 * dt / 3600 * 100
