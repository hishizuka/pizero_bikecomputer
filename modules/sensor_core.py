import asyncio
import math
import time
from datetime import datetime

import numpy as np
import psutil

from modules.app_logger import app_logger
from modules.sensor.performance_metrics import (
    NP_WINDOW_SIZE_DEFAULT,
    calc_form_metrics as perf_calc_form_metrics,
    calc_w_prime_balance as perf_calc_w_prime_balance,
    reset_performance_metrics_state,
    update_normalized_power as perf_update_normalized_power,
)

app_logger.info("detected sensor modules:")

from modules.utils.timer import Timer, log_timers
from modules.utils.wind import (
    get_speed_impact,
    get_wind_cost,
    get_wind_elevation,
    get_wind_impact,
)
from .sensor.gps import get_sensor_gps_class
from .sensor.sensor_ant import SensorANT
from .sensor.sensor_ble import SensorBLE
from .sensor.sensor_gpio import SensorGPIO
from .sensor.sensor_i2c import SensorI2C

SensorGPS = get_sensor_gps_class()


class SensorCore:
    NP_WINDOW_SIZE = NP_WINDOW_SIZE_DEFAULT
    WIND_ACCUMULATED_STATE_KEY = "wind_accumulated_values"

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
        "wind_power_delta",
        "wind_grade",
        "wind_cost_power",
        "wind_cost_grade",
        "wind_work",
        "wind_elevation",
        "wind_cost_work",
        "wind_cost_elevation",
        "wind_cost_available",
        "speed_impact",
        "wind_time",
        "temperature",
        "cpu_percent",
        "system_cpu_percent",
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
    brakelight_cad = []
    brakelight_cad_range = 2  # 2 samples at 1Hz loop
    brakelight_power = []
    brakelight_power_range = 2  # 2 samples at 1Hz loop
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
        integrated = self.values["integrated"]

        # reset
        for key in self.integrated_value_keys:
            integrated[key] = np.nan
        self.reset_internal()
        wind_accumulated_values = self.config.state.get_value(
            self.WIND_ACCUMULATED_STATE_KEY, (0.0, 0.0)
        )
        if len(wind_accumulated_values) == 2:
            wind_accumulated_values = (*wind_accumulated_values, 0.0)
        wind_work, wind_time, wind_cost_work = wind_accumulated_values
        integrated["wind_work"] = wind_work
        integrated["wind_elevation"] = get_wind_elevation(
            wind_work, self.config.G_POWER_TOTAL_WEIGHT
        )
        integrated["wind_cost_work"] = wind_cost_work
        integrated["wind_cost_elevation"] = get_wind_elevation(
            wind_cost_work, self.config.G_POWER_TOTAL_WEIGHT
        )
        integrated["wind_time"] = wind_time

        for g in self.graph_keys:
            integrated[g] = [np.nan] * self.config.G_GUI_PERFORMANCE_GRAPH_DISPLAY_RANGE
        for d in self.diff_keys:
            integrated[d] = [np.nan] * self.grade_range
        self.brakelight_spd = [0] * self.brakelight_spd_range
        self.brakelight_cad = [np.nan] * self.brakelight_cad_range
        self.brakelight_power = [np.nan] * self.brakelight_power_range
        self.auto_backlight_brightness = [
            self.config.G_AUTO_BACKLIGHT_CUTOFF + 1
        ] * self.auto_backlight_brightness_range
        integrated["CPU_MEM"] = ""

        for s in self.average_secs:
            for v in self.average_values:
                self.average_values[v][s] = []
                integrated[f"ave_{v}_{s}s"] = np.nan
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
    def _elapsed_since_timestamp(now_time, sensor_values, timestamp_key="timestamp"):
        timestamp = sensor_values.get(timestamp_key)
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
        self._perf_sensor_ble_update_ms_sum = 0.0
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
        ble_update_avg_ms = (
            self._perf_sensor_ble_update_ms_sum / self._perf_sensor_calls
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

        cpu_percent = self.values["integrated"]["cpu_percent"]
        system_cpu_percent = self.values["integrated"]["system_cpu_percent"]
        app_logger.debug(
            "[PERF_SENSOR] "
            f"win={self._perf_sensor_window} "
            f"calls={self._perf_sensor_calls} "
            f"loop_avg_ms={loop_avg_ms:.3f} "
            f"loop_p95_ms={loop_p95_ms:.3f} "
            f"loop_max_ms={loop_max_ms:.3f} "
            f"preprocess_avg_ms={preprocess_avg_ms:.3f} "
            f"ant_update_avg_ms={ant_update_avg_ms:.3f} "
            f"ble_update_avg_ms={ble_update_avg_ms:.3f} "
            f"calc_avg_ms={calc_avg_ms:.3f} "
            f"post_avg_ms={post_avg_ms:.3f} "
            f"adjust_avg_ms={adjust_avg_ms:.3f} "
            f"wait_s={self.wait_time:.3f} "
            f"interval_s={self.actual_loop_interval:.3f} "
            f"cpu_proc={cpu_percent} "
            f"cpu_sys={system_cpu_percent}"
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
        await self.sensor_gpio.quit()

    # reset accumulated values
    def reset(self):
        self.sensor_gps.reset()
        self.sensor_ant.reset()
        self.sensor_ble.reset()
        self.sensor_i2c.reset()
        self.reset_internal()

    def reset_internal(self):
        integrated = self.values["integrated"]
        for key in (
            "distance",
            "accumulated_power",
            "wind_work",
            "wind_elevation",
            "wind_cost_work",
            "wind_cost_elevation",
            "wind_time",
        ):
            integrated[key] = 0
        for key in ("wind_cost_power", "wind_cost_grade", "speed_impact"):
            integrated[key] = np.nan
        integrated["wind_cost_available"] = False
        reset_performance_metrics_state(self)
        self.brakelight_spd = [0] * self.brakelight_spd_range
        self.brakelight_cad = [np.nan] * self.brakelight_cad_range
        self.brakelight_power = [np.nan] * self.brakelight_power_range

    def update_normalized_power(self, pwr):
        perf_update_normalized_power(self, pwr)

    def _update_power_metrics(self, power):
        """Update source-independent power metrics from ANT+ or BLE power."""
        self.update_normalized_power(power)
        self.calc_w_prime_balance(power)
        self.calc_form_metrics(power)
        if not np.isnan(power):
            self.get_ave_values("power", power)

    @staticmethod
    def _shift_window_and_append(window, value):
        window[:-1] = window[1:]
        window[-1] = value

    def _update_zero_window_brake_hint(self, window, value):
        if np.isnan(value):
            return False

        self._shift_window_and_append(window, value)
        return all(v <= 0.0 for v in window)

    def _update_speed_brake_hint(self, speed):
        if np.isnan(speed):
            return False

        self._shift_window_and_append(self.brakelight_spd, speed)

        # 1: all past speeds are less than brakelight_spd_cutoff
        cond_1 = all((s < self.brakelight_spd_cutoff for s in self.brakelight_spd))
        # 2-1: current speed exceeds brakelight_spd_cutoff
        cond_2_1 = speed > self.brakelight_spd_cutoff
        # 2-2: current speed reduced by 5% from the speed [brakelight_spd_range] seconds ago
        #  30km/h: 1.2km/h(4%), 20km/h: 0.8km/h(4%)
        cond_2_2 = (
            self.brakelight_spd[0] - self.brakelight_spd[-1]
            > self.brakelight_spd[0] * 0.04
        )
        return cond_1 or (cond_2_1 and cond_2_2)

    def _update_cadence_brake_hint(self, cadence):
        return self._update_zero_window_brake_hint(self.brakelight_cad, cadence)

    def _update_power_brake_hint(self, power):
        return self._update_zero_window_brake_hint(self.brakelight_power, power)

    async def integrate(self):
        pre_dst = {"ANT+": 0, "BLE": 0, "GPS": 0}
        pre_ttlwork = {"ANT+": 0, "BLE": 0}
        pre_alt = {"ANT+": np.nan, "BLE": np.nan, "GPS": np.nan}
        pre_alt_spd = {"ANT+": np.nan, "BLE": np.nan}
        pre_grade = pre_grade_spd = pre_glide = self.config.G_SENSOR_NULLVALUE
        diff_sum = {"alt_diff": 0, "dst_diff": 0, "alt_diff_spd": 0, "dst_diff_spd": 0}

        # for w_prime_balance
        # alias for self.values
        v = {"GPS": self.values["GPS"], "I2C": self.values["I2C"]}
        integrated = self.values["integrated"]
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

            time_profile = [
                start_time,
            ]
            hr = spd = cdc = pwr = temperature = self.config.G_SENSOR_NULLVALUE
            grade = grade_spd = glide = self.config.G_SENSOR_NULLVALUE
            wind_force_delta = np.nan
            air_density = np.nan
            ttlwork_diff = 0
            dst_diff = {"ANT+": 0, "BLE": 0, "GPS": 0, "USE": 0}
            alt_diff = {"ANT+": 0, "BLE": 0, "GPS": 0, "USE": 0}
            dst_diff_spd = {"ANT+": 0, "BLE": 0}
            alt_diff_spd = {"ANT+": 0, "BLE": 0}
            grade_use = {"SENSOR": False, "GPS": False}
            time_profile.append(datetime.now())
            # self.sensor_i2c.update()
            # self.sensor_gps.update()
            ant_update_start = time.perf_counter()
            preprocess_elapsed_ms = (ant_update_start - loop_start_perf) * 1000.0
            self.sensor_ant.update()  # for dummy
            ant_update_elapsed_ms = (time.perf_counter() - ant_update_start) * 1000.0
            ble_update_start = time.perf_counter()
            self.sensor_ble.update()
            ble_update_elapsed_ms = (time.perf_counter() - ble_update_start) * 1000.0
            calc_start_perf = time.perf_counter()
            ant_use = {
                key: self.sensor_ant.is_sensor_available(key)
                for key in ["HR", "SPD", "CDC", "PWR", "TEMP", "LGT"]
            }
            ble_hr_configured = self.sensor_ble.is_sensor_available("HR")
            ble_spd_configured = self.sensor_ble.is_sensor_available("SPD")
            ble_cdc_configured = self.sensor_ble.is_sensor_available("CDC")
            ble_pwr_configured = self.sensor_ble.is_sensor_available("PWR")
            power_sensor_configured = ant_use["PWR"] or ble_pwr_configured
            power_sensor_live = False

            now_time = datetime.now()
            time_profile.append(now_time)

            ant_id_type = {
                role: self.config.get_ant_id_type(role)
                for role in ("HR", "SPD", "CDC", "PWR", "TEMP")
            }
            ant_type = {
                role: self.config.G_SENSORS[role]["TYPE"] for role in ("SPD", "CDC")
            }
            delta = {
                "PWR": {0x10: float("inf"), 0x11: float("inf"), 0x12: float("inf")},
                "CDC-PWR": {0x12: float("inf"), 0x10: float("inf")},
            }
            for key in ["HR", "SPD", "CDC", "TEMP"]:
                delta[key] = float("inf")
            # need for ANT+ ID update
            for key in ["HR", "SPD", "CDC", "PWR", "TEMP"]:
                if ant_use[key] and ant_id_type[key] in self.values["ANT+"]:
                    v[key] = self.values["ANT+"][ant_id_type[key]]

            # make intervals from timestamp
            for key in ["HR", "SPD", "CDC", "TEMP"]:
                if not ant_use[key]:
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
                    ant_use["CDC"] and ant_type["CDC"] == 0x0B,
                ),
                (
                    "SPD",
                    "SPD",
                    [0x11],
                    ant_use["SPD"] and ant_type["SPD"] == 0x0B,
                ),
                (
                    "PWR",
                    "PWR",
                    [0x12, 0x11, 0x10],
                    ant_use["PWR"],
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

            # Heart rate: ANT+ or BLE HRS
            if ant_use["HR"]:
                if delta["HR"] < self.time_threshold["HR"]:
                    hr = v["HR"]["heart_rate"]
            elif ble_hr_configured:
                ble_hr_data = self.values["BLE"]["HR"]
                if self.sensor_ble.is_sensor_connected("HR") and not np.isnan(
                    ble_hr_data["heart_rate"]
                ):
                    hr = ble_hr_data["heart_rate"]

            # Cadence: ANT+ or BLE CSCS
            if ant_use["CDC"]:
                cdc = 0
                # get from cadence or speed&cadence sensor
                if ant_type["CDC"] in [0x79, 0x7A]:
                    if delta["CDC"] < self.time_threshold["CDC"]:
                        cdc = v["CDC"]["cadence"]
                # get from powermeter
                elif ant_type["CDC"] == 0x0B:
                    for page in [0x12, 0x10]:
                        if not "timestamp" in v["CDC"][page]:
                            continue
                        if delta["CDC-PWR"][page] < self.time_threshold["CDC"]:
                            cdc = v["CDC"][page]["cadence"]
                            break
            elif ble_cdc_configured:
                ble_cdc_data = self.values["BLE"]["CDC"]
                if self.sensor_ble.is_sensor_connected("CDC") and not np.isnan(
                    ble_cdc_data["cadence"]
                ):
                    cdc = ble_cdc_data["cadence"]

            # Power : ANT+(assumed crank type > wheel type)
            if ant_use["PWR"]:
                pwr = 0
                # page18 > 17 > 16, 16simple is not used
                for page in [0x12, 0x11, 0x10]:
                    if delta["PWR"][page] < self.time_threshold["PWR"]:
                        pwr = v["PWR"][page]["power"]
                        power_sensor_live = True
                        break
            elif ble_pwr_configured:
                ble_pwr_data = self.values["BLE"]["PWR"]
                if self.sensor_ble.is_sensor_connected("PWR") and not np.isnan(
                    ble_pwr_data["power"]
                ):
                    pwr = ble_pwr_data["power"]
                    power_sensor_live = True

            # Speed: ANT+ or BLE CSCS > GPS
            ant_spd_packet_received_recently = False
            ble_spd_live = False
            if ant_use["SPD"]:
                spd_data = v["SPD"]
                if ant_type["SPD"] == 0x0B:
                    spd_data = v["SPD"][0x11]
                ant_spd_packet_received_recently = (
                    spd_data["on_data_timestamp"] is not None
                    and (now_time - spd_data["on_data_timestamp"]).total_seconds()
                    < self.time_threshold["SPD"]
                )

                spd = 0
                if delta["SPD"] < self.time_threshold["SPD"]:
                    spd = spd_data["speed"]
                # Keep zero speed while ANT+ speed packets continue during a wheel stop.
                elif ant_spd_packet_received_recently:
                    pass
                # Complement from GPS speed when I2C acc sensor is available (using moving status).
                elif v["I2C"]["m_stat"] == 1 and v["GPS"]["speed"] > 0:
                    spd = v["GPS"]["speed"]
            elif ble_spd_configured:
                ble_spd_data = self.values["BLE"]["SPD"]
                ble_spd_live = self.sensor_ble.is_sensor_connected(
                    "SPD"
                ) and not np.isnan(ble_spd_data["speed"])
                if ble_spd_live:
                    spd = ble_spd_data["speed"]
                elif not np.isnan(v["GPS"]["speed"]):
                    spd = v["GPS"]["speed"]
            elif not np.isnan(v["GPS"]["speed"]):
                spd = v["GPS"]["speed"]

            wheel_distance_source = None

            # Distance: ANT+ or BLE CSCS > GPS
            if ant_use["SPD"]:
                # normal speed meter
                if ant_type["SPD"] in [0x79, 0x7B]:
                    if pre_dst["ANT+"] < v["SPD"]["distance"]:
                        dst_diff["ANT+"] = v["SPD"]["distance"] - pre_dst["ANT+"]
                    pre_dst["ANT+"] = v["SPD"]["distance"]
                elif ant_type["SPD"] == 0x0B:
                    if pre_dst["ANT+"] < v["SPD"][0x11]["distance"]:
                        dst_diff["ANT+"] = v["SPD"][0x11]["distance"] - pre_dst["ANT+"]
                    pre_dst["ANT+"] = v["SPD"][0x11]["distance"]
                wheel_distance_source = "ANT+"
            elif ble_spd_live:
                ble_distance = self.values["BLE"]["SPD"]["distance"]
                if pre_dst["BLE"] < ble_distance:
                    dst_diff["BLE"] = ble_distance - pre_dst["BLE"]
                pre_dst["BLE"] = ble_distance
                wheel_distance_source = "BLE"

            if wheel_distance_source is not None:
                dst_diff["USE"] = dst_diff[wheel_distance_source]
                grade_use["SENSOR"] = True
            if "timestamp" in v["GPS"]:
                if pre_dst["GPS"] < v["GPS"]["distance"]:
                    dst_diff["GPS"] = v["GPS"]["distance"] - pre_dst["GPS"]
                pre_dst["GPS"] = v["GPS"]["distance"]
                if wheel_distance_source is None and dst_diff["GPS"] > 0:
                    dst_diff["USE"] = dst_diff["GPS"]
                    grade_use["GPS"] = True
                # Fall back to GPS distance when ANT+ speed packets are unavailable.
                elif ant_use["SPD"]:
                    if (
                        not ant_spd_packet_received_recently
                        and dst_diff["ANT+"] == 0
                        and dst_diff["GPS"] > 0
                    ):
                        dst_diff["USE"] = dst_diff["GPS"]
                        grade_use["SENSOR"] = False
                        grade_use["GPS"] = True

            # Total work: ANT+ or BLE
            if ant_use["PWR"]:
                # both type are not exist in same ID(0x12:crank, 0x11:wheel)
                # if 0x12 or 0x11 exists, never take 0x10
                for page in [0x12, 0x11, 0x10]:
                    if "timestamp" in v["PWR"][page]:
                        if pre_ttlwork["ANT+"] < v["PWR"][page]["accumulated_power"]:
                            ttlwork_diff = (
                                v["PWR"][page]["accumulated_power"]
                                - pre_ttlwork["ANT+"]
                            )
                        pre_ttlwork["ANT+"] = v["PWR"][page]["accumulated_power"]
                        # never take other powermeter
                        break
            elif ble_pwr_configured:
                accumulated_power = self.values["BLE"]["PWR"]["accumulated_power"]
                if accumulated_power < pre_ttlwork["BLE"]:
                    pre_ttlwork["BLE"] = accumulated_power
                elif pre_ttlwork["BLE"] < accumulated_power:
                    ttlwork_diff = accumulated_power - pre_ttlwork["BLE"]
                    pre_ttlwork["BLE"] = accumulated_power

            # Temperature : ANT+
            if ant_use["TEMP"]:
                if delta["TEMP"] < self.time_threshold["TEMP"]:
                    temperature = v["TEMP"]["temperature"]
            elif not np.isnan(v["I2C"]["temperature"]):
                temperature = v["I2C"]["temperature"]

            # altitude
            if not np.isnan(v["I2C"]["pre_altitude"]):
                alt = v["I2C"]["altitude"]
                # for grade (distance base)
                for key in ["ANT+", "BLE", "GPS"]:
                    if dst_diff[key] > 0:
                        alt_diff[key] = alt - pre_alt[key]
                    pre_alt[key] = alt
                if wheel_distance_source is not None:
                    alt_diff["USE"] = alt_diff[wheel_distance_source]
                elif dst_diff["GPS"] > 0:
                    alt_diff["USE"] = alt_diff["GPS"]
                # for grade (speed base)
                if wheel_distance_source is not None:
                    if dst_diff[wheel_distance_source] > 0:
                        alt_diff_spd[wheel_distance_source] = (
                            alt - pre_alt_spd[wheel_distance_source]
                        )
                    pre_alt_spd[wheel_distance_source] = alt

            # dem_altitude
            if self.config.G_USE_DEM_TILE:
                api_alt_start = time.perf_counter()
                integrated["dem_altitude"] = await self.config.api.get_altitude(
                    [v["GPS"]["lon"], v["GPS"]["lat"]]
                )
                api_alt_elapsed_ms = (time.perf_counter() - api_alt_start) * 1000.0

            # wind
            if self.config.G_USE_WIND_DATA_SOURCE:
                api_wind_start = time.perf_counter()
                (
                    integrated["wind_speed"],
                    integrated["wind_direction"],
                    integrated["wind_direction_str"],
                ) = await self.config.api.get_wind([v["GPS"]["lon"], v["GPS"]["lat"]])
                (
                    integrated["headwind"],
                    wind_force_delta,
                    integrated["wind_power_delta"],
                    integrated["wind_grade"],
                    air_density,
                ) = get_wind_impact(
                    spd,
                    integrated["wind_speed"],
                    integrated["wind_direction"],
                    v["GPS"]["track"],
                    temperature,
                    v["I2C"]["pressure"],
                    self.config.G_POWER_CDA,
                    self.config.G_POWER_TOTAL_WEIGHT,
                )
                api_wind_elapsed_ms = (time.perf_counter() - api_wind_start) * 1000.0

            # grade (distance base)
            if dst_diff["USE"] > 0:
                diff_sources = {
                    "alt_diff": alt_diff,
                    "dst_diff": dst_diff,
                }
                for key in ["alt_diff", "dst_diff"]:
                    self._shift_window_and_append(
                        integrated[key], diff_sources[key]["USE"]
                    )
                    # diff_sum[key] = np.mean(self.values['integrated'][key][-self.grade_window_size:])
                    diff_sum[key] = np.nansum(
                        integrated[key][-self.grade_window_size :]
                    )
                # set grade
                gl = self.config.G_SENSOR_NULLVALUE
                gr = self.config.G_SENSOR_NULLVALUE
                x = self.config.G_SENSOR_NULLVALUE
                y = diff_sum["alt_diff"]
                if grade_use["SENSOR"]:
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
            if wheel_distance_source is not None:
                dst_diff_spd[wheel_distance_source] = spd * self.actual_loop_interval
                diff_sources_spd = {
                    "alt_diff_spd": alt_diff_spd,
                    "dst_diff_spd": dst_diff_spd,
                }
                for key in ["alt_diff_spd", "dst_diff_spd"]:
                    self._shift_window_and_append(
                        integrated[key],
                        diff_sources_spd[key][wheel_distance_source],
                    )
                    diff_sum[key] = np.mean(integrated[key][-self.grade_window_size :])
                    # diff_sum[key] = np.nansum(self.values['integrated'][key][-self.grade_window_size:])
                # set grade
                x = diff_sum["dst_diff_spd"] ** 2 - diff_sum["alt_diff_spd"] ** 2
                y = diff_sum["alt_diff_spd"]
                gr = self.config.G_SENSOR_NULLVALUE
                if x > 0:
                    x = math.sqrt(x)
                    gr = self.conv_grade(100 * y / x)
                grade_spd = pre_grade_spd = gr
            # for sometimes speed sensor value is missing in running
            elif (
                all(value == 0 for value in dst_diff_spd.values())
                and self.config.G_STOPWATCH_STATUS == "START"
            ):
                grade_spd = pre_grade_spd

            model_grade = grade_spd if not np.isnan(grade_spd) else grade
            if np.isnan(model_grade):
                model_grade = 0.0
            speed_impact = get_speed_impact(
                spd,
                wind_force_delta,
                air_density,
                self.config.G_POWER_CDA,
                self.config.G_POWER_TOTAL_WEIGHT,
                self.config.G_POWER_CRR,
                model_grade,
            )
            integrated["speed_impact"] = speed_impact.delta
            wind_cost = get_wind_cost(
                pwr if power_sensor_live else np.nan,
                spd,
                speed_impact.still_air_speed,
                self.config.G_POWER_TOTAL_WEIGHT,
            )
            integrated["wind_cost_power"] = wind_cost.power
            integrated["wind_cost_grade"] = wind_cost.grade
            integrated["wind_cost_available"] = power_sensor_configured

            if (
                self.config.G_STOPWATCH_STATUS == "START"
                and dst_diff["USE"] > 0
                and not np.isnan(wind_force_delta)
            ):
                distance = dst_diff["USE"]
                integrated["wind_work"] += wind_force_delta * distance
                integrated["wind_elevation"] = get_wind_elevation(
                    integrated["wind_work"], self.config.G_POWER_TOTAL_WEIGHT
                )
                if speed_impact.still_air_speed > 0:
                    integrated["wind_time"] += distance * (
                        1 / spd - 1 / speed_impact.still_air_speed
                    )
                if not np.isnan(wind_cost.power):
                    integrated["wind_cost_work"] += wind_cost.power * distance / spd
                    integrated["wind_cost_elevation"] = get_wind_elevation(
                        integrated["wind_cost_work"],
                        self.config.G_POWER_TOTAL_WEIGHT,
                    )
                self.config.state.set_value(
                    self.WIND_ACCUMULATED_STATE_KEY,
                    (
                        integrated["wind_work"],
                        integrated["wind_time"],
                        integrated["wind_cost_work"],
                    ),
                )

            integrated["heart_rate"] = hr
            integrated["speed"] = spd
            integrated["cadence"] = cdc
            integrated["power"] = pwr
            integrated["distance"] += dst_diff["USE"]
            integrated["accumulated_power"] += ttlwork_diff
            integrated["grade"] = grade
            integrated["grade_spd"] = grade_spd
            integrated["glide_ratio"] = glide
            integrated["temperature"] = temperature

            # Update normalized power, W' balance, TSS and power averages.
            if power_sensor_configured:
                self._update_power_metrics(pwr)

            graph_values = {
                "hr_graph": hr,
                "power_graph": pwr,
                "w_bal_graph": integrated["w_prime_balance_normalized"],
                "altitude_gps_graph": v["GPS"]["alt"],
                "altitude_graph": v["I2C"]["altitude"],
            }
            for key, value in graph_values.items():
                self._shift_window_and_append(integrated[key], value)

            # average power, heart_rate
            if (ant_use["HR"] or ble_hr_configured) and not np.isnan(hr):
                self.get_ave_values("heart_rate", hr)

            time_profile.append(datetime.now())
            calc_elapsed_ms = (time.perf_counter() - calc_start_perf) * 1000.0
            post_start_perf = time.perf_counter()

            # toggle auto stop
            if self.config.G_AUTOSTOP_STATUS:
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
                        or ant_use["SPD"]
                        or ble_spd_live
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
                        (
                            ant_use["SPD"]
                            or ble_spd_configured
                            or "timestamp" in v["GPS"]
                        )
                        and self.config.G_STOPWATCH_STATUS == "START"
                        and self.config.logger is not None
                    ):
                        self.config.logger.start_and_stop()

            # Ambient light is shared by independent display and ANT+ light controls.
            is_dark = False
            if not np.isnan(v["I2C"]["light"]):
                self._shift_window_and_append(
                    self.auto_backlight_brightness, v["I2C"]["light"]
                )
                brightness = int(np.mean(self.auto_backlight_brightness))
                is_dark = brightness <= self.config.G_AUTO_BACKLIGHT_CUTOFF

                if self.config.display.use_auto_backlight:
                    if is_dark:
                        self.config.display.set_minimum_brightness()
                    else:
                        self.config.display.set_brightness(0)

            # brake light with speed/cadence/power conditions
            speed = self.values["integrated"]["speed"]
            cadence = self.values["integrated"]["cadence"]
            power = self.values["integrated"]["power"]

            speed_brake_hint = self._update_speed_brake_hint(speed)
            cadence_brake_hint = self._update_cadence_brake_hint(cadence)
            power_brake_hint = self._update_power_brake_hint(power)

            if (
                self.config.G_AUTO_LIGHT
                and ant_use["LGT"]
                and self.config.G_MANUAL_STATUS == "START"
            ):
                auto_light = is_dark
                if speed_brake_hint or cadence_brake_hint or power_brake_hint:
                    auto_light = True
                if auto_light:
                    self.sensor_ant.set_light_mode("FLASH_LOW", auto=True)
                else:
                    self.sensor_ant.set_light_mode("OFF", auto=True)

            # cpu and memory
            self.values["integrated"]["system_cpu_percent"] = int(
                sum(psutil.cpu_percent(interval=None, percpu=True))
            )
            with self.process.oneshot():
                self.values["integrated"]["cpu_percent"] = int(
                    self.process.cpu_percent(interval=None)
                )
                if self.config.G_DEBUG:
                    self._update_status_bar_color_by_cpu_usage()
                self.values["integrated"]["CPU_MEM"] = (
                    "{0:.0f}%/{1:.0f}%, {2:.0f}MB".format(
                        self.values["integrated"]["cpu_percent"],
                        self.values["integrated"]["system_cpu_percent"],
                        self.process.memory_info().rss / 1024**2,
                    )
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
                    f"(def/sensor updates/make variables(too long)/post-processing)"
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
            self._perf_sensor_ble_update_ms_sum += ble_update_elapsed_ms
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
        gui = self.config.gui
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
                self._shift_window_and_append(self.average_values[k][sec], v)
            self.values["integrated"]["ave_{}_{}s".format(k, sec)] = int(
                np.mean(self.average_values[k][sec])
            )

    def calc_w_prime_balance(self, pwr):
        perf_calc_w_prime_balance(self, pwr)

    def calc_form_metrics(self, pwr):
        perf_calc_form_metrics(self, pwr)
