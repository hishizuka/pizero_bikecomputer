from datetime import datetime, timezone
import math
import asyncio
import os
from pathlib import Path
import time

import numpy as np

from modules.app_logger import app_logger
from modules.helper.network.http_client import get_json
from modules.utils.geo import get_dist_on_earth, get_track_str
from .sensor import Sensor
from .i2c_utils import i2c_addr_present as _i2c_addr_present

# I2C
_SENSOR_I2C = False
try:
    import smbus2
    _SENSOR_I2C = True
except ImportError:
    pass
if _SENSOR_I2C:
    app_logger.info("  I2C")

_MAG_DECLINATION_FETCH_TIMEOUT_SEC = 5.0
_MAG_DECLINATION_CACHE_DISTANCE_CUTOFF_M = 50000.0
_MAG_DECLINATION_API_URL = (
    "https://geomag.bgs.ac.uk/web_service/GMModels/wmm/2025/"
)

# acc
X = 0
Y = 1
Z = 2

G = 9.80665

# I2C addresses for Cython-based helpers (keep in sync with corresponding C headers).
BHI3_I2C_ADDR = 0x28
BHI3_CHIP_ID_REG = 0x2B
BHI360_CHIP_ID = 0x7A
BHI385_CHIP_ID = 0x7C
BHI3_HELPER_DIR = Path(__file__).resolve().parent / "i2c/cython/bhi360_shuttle_board_3"
BHI3_HELPER_GLOB = "bhi3_s_helper*.so"
BHI3_TARGET_MARKER = BHI3_HELPER_DIR / "__pycache__" / "bhi3_s_helper.target"
BMP5_I2C_ADDR = 0x47
BMI270_I2C_ADDR = 0x68
BMM150_I2C_ADDR = 0x13
BMM350_I2C_ADDR = 0x14


def _normalize_bhi3_target(target):
    target = (target or "").strip().lower()
    if target in ("360", "bhi360", "385", "bhi385"):
        return f"bhi{target[-3:]}"
    return ""


def _bhi3_target_sensor_name(target):
    target = _normalize_bhi3_target(target)
    if target == "bhi360":
        return "BHI360"
    if target == "bhi385":
        return "BHI385"
    return "BHI3_S"


def _remove_bhi3_helper_extensions():
    for path in BHI3_HELPER_DIR.glob(BHI3_HELPER_GLOB):
        path.unlink(missing_ok=True)


def _write_bhi3_target_marker(target):
    try:
        BHI3_TARGET_MARKER.parent.mkdir(exist_ok=True)
        BHI3_TARGET_MARKER.write_text(f"{target}\n")
    except OSError:
        pass


def _prepare_bhi3_build_target():
    chip_id = None
    if _SENSOR_I2C:
        bus = None
        try:
            bus = smbus2.SMBus(1)
            chip_id = bus.read_byte_data(BHI3_I2C_ADDR, BHI3_CHIP_ID_REG)
        except Exception:
            chip_id = None
        finally:
            if bus is not None:
                try:
                    bus.close()
                except Exception:
                    pass

    detected_target = ""
    if chip_id == BHI360_CHIP_ID:
        detected_target = "bhi360"
    elif chip_id == BHI385_CHIP_ID:
        detected_target = "bhi385"

    env_target = _normalize_bhi3_target(os.environ.get("BHI3_TARGET", ""))
    target = detected_target or env_target
    if not target:
        return ""

    if env_target and detected_target and env_target != detected_target:
        app_logger.warning(
            f"BHI3_TARGET={env_target} does not match chip id 0x{chip_id:02X}; using {detected_target}"
        )

    os.environ["BHI3_TARGET"] = target
    try:
        marker_target = _normalize_bhi3_target(BHI3_TARGET_MARKER.read_text().strip())
    except OSError:
        marker_target = ""

    if marker_target != target and any(BHI3_HELPER_DIR.glob(BHI3_HELPER_GLOB)):
        _remove_bhi3_helper_extensions()

    if chip_id is not None:
        app_logger.info(f"BHI3 chip id 0x{chip_id:02X}; target {target}")
    return target


class SensorI2C(Sensor):
    sensor = {}
    available_sensors = {
        "PRESSURE": {},
        "MOTION": {},  # includes acc, gyro and mag
        "LIGHT": {},
        "UV": {},
        "GAS": {},
        "BUTTON": {},
        "BATTERY": {},
    }
    motion_sensor = {
        "ACC": False,
        "GYRO": False,
        "MAG": False,
        "EULER": False,
        "QUATERNION": False,
    }
    elements = (
        "temperature",
        "pressure_raw",
        "pressure_mod",
        "pressure",
        "humidity",
        "discomfort_index",
        "altitude",
        "pre_altitude",
        "vertical_speed",
        "light",
        "infrared",
        "uvi",
        "voc_index",
        "raw_gas",
        "pitch",
        "roll",
        "yaw",
        "yaw_for_heading",
        "fixed_pitch",
        "fixed_roll",
        "grade_pitch",
        "raw_heading",
        "heading",
        "heading_str",
        "motion",
        "m_stat",
        "voltage_battery",
        "current_battery",
        "voltage_out",
        "current_out",
        "battery_percentage",
    )
    elements_vec = (
        "acc_raw",
        "acc_mod",
        "acc",
        "acc_graph",
        "gyro_raw",
        "gyro_mod",
        "gyro",
        "mag_raw",
        "mag_center",
        "mag_scale",
        "mag_mod",
        "mag",
        "quaternion",
        "acc_variance",
    )

    values_mod = {}  # mag_min, mag_max, gyro_ave
    elements_vec_mod = ("gyro_ave",)
    sensor_label = {
        "MAG": "",
    }
    do_mag_calibration = False
    do_pitch_roll_calibration = False
    mag_calib_ready = False

    # for graph
    graph_values = {}
    graph_keys = ("g_acc",)

    # for LP filter
    pre_value = {}
    # for modify magnetic north
    is_mag_declination_modified = False
    # for median filter and hampel filter(outlier=spike detection)
    median_keys = ["pressure_mod"]
    pre_values_array = {}
    median_val = {}
    pre_value_window_size = 10
    # for average
    average_keys = ["altitude"]
    average_val = {}
    ave_window_size = 7

    # constants
    # for moving detection
    moving_threshold = 0
    moving_threshold_min = 0
    # for altitude
    sealevel_pa = 1013.25
    sealevel_temp = 273.15 + 20  # The temperature is fixed at 20 degrees Celsius.
    sealevel_altitude_calibrated = False
    total_ascent_threshold = 2  # [m]

    # for vertical speed
    vspeed_array = []
    vspeed_window_duration = 2  # [s]
    vspeed_window_size = vspeed_window_duration
    timestamp_array = []
    timestamp_duration = vspeed_window_duration  # [s]
    timestamp_size = timestamp_duration

    quit_status = False

    def sensor_init(self):
        self.bhi3_s_target = ""
        self.reset()
        self.is_mag_declination_modified = False
        self._mag_declination_task = None
        self._mag_declination_fetch_started = False
        self._mag_declination_cache = self._load_mag_declination_cache()

        if not _SENSOR_I2C:
            return

        if self.config.G_USE_PCB_PIZERO_BIKECOMPUTER:
            # BHI3 Shuttle Board 3.0
            self.set_bhi3_s()
            if self.detect_light_vncl4040():
                self.available_sensors["LIGHT"]["VCNL4040"] = True
                self.sensor["lux"] = self.sensor_vcnl4040
            elif self.detect_light_ltr308als():
                self.available_sensors["LIGHT"]["LTR308ALS"] = True
                self.sensor["lux"] = self.sensor_ltr308als
            if self.detect_button_mcp230xx():
                self.available_sensors["BUTTON"]["MCP23008"] = True

            self.print_sensors()
        else:
            self.detect_sensors()
            self.set_sensors()
        
        #self.reset()

        restored_sealevel_pa = self.config.state.get_value("sealevel_pa", None)
        if restored_sealevel_pa is not None:
            self.sealevel_pa = restored_sealevel_pa

        restored_sealevel_temp = self.config.state.get_value("sealevel_temp", None)
        if restored_sealevel_temp is not None:
            self.sealevel_temp = restored_sealevel_temp

        if restored_sealevel_pa is not None or restored_sealevel_temp is not None:
            self.sealevel_altitude_calibrated = True

        for k in ("mag_min", "mag_max"):
            self.values_mod[k] = self.config.state.get_value(
                f"{k}_{self.sensor_label['MAG']}", None
            )
        if (
            self.values_mod["mag_min"] is not None
            and self.values_mod["mag_max"] is not None
        ):
            self.calc_mag_scales()

        for k in ("fixed_pitch", "fixed_roll"):
            self.values[k] = self.config.state.get_value(k, 0.0)

    def detect_sensors(self):
        # pressure sensors
        self.available_sensors["PRESSURE"]["LPS3XHW"] = self.detect_pressure_lps3xhw()
        if not self.available_sensors["PRESSURE"]["LPS3XHW"]:
            self.available_sensors["PRESSURE"][
                "LPS3XHW_ORIG"
            ] = self.detect_pressure_lps3xhw_orig()
        self.available_sensors["PRESSURE"]["BMP280"] = self.detect_pressure_bmp280()
        if not self.available_sensors["PRESSURE"]["BMP280"]:
            self.available_sensors["PRESSURE"][
                "BMP280_ORIG"
            ] = self.detect_pressure_bmp280_orig()
        self.available_sensors["PRESSURE"]["BMP3XX"] = self.detect_pressure_bmp3xx()
        self.available_sensors["PRESSURE"]["MS5637"] = self.detect_pressure_ms5637()
        self.available_sensors["PRESSURE"]["BME280"] = self.detect_pressure_bme280()
        self.available_sensors["PRESSURE"]["BMP581"] = self.detect_pressure_bmp581()

        # motion sensors
        # assume accelerometer range is 2g. moving_threshold is affected.
        self.available_sensors["MOTION"][
            "LSM303_ORIG"
        ] = self.detect_motion_lsm303_orig()
        self.available_sensors["MOTION"]["LIS3MDL"] = self.detect_motion_lis3mdl()
        self.available_sensors["MOTION"]["LSM6DS"] = self.detect_motion_lsm6ds()
        self.available_sensors["MOTION"]["ISM330DHCX"] = self.detect_motion_ism330dhcx()
        self.available_sensors["MOTION"]["MMC5983MA"] = self.detect_motion_mmc5983ma()
        self.available_sensors["MOTION"]["LSM9DS1"] = self.detect_motion_lsm9ds1()
        self.available_sensors["MOTION"]["BMX160"] = self.detect_motion_bmx160()
        self.available_sensors["MOTION"]["BNO055"] = self.detect_motion_bno055()
        self.available_sensors["MOTION"]["ICM20948"] = self.detect_motion_icm20948()
        self.available_sensors["MOTION"]["BMI270"] = self.detect_motion_bmi270()
        self.available_sensors["MOTION"]["BMM150"] = self.detect_motion_bmm150()
        self.available_sensors["MOTION"]["BMM350"] = self.detect_motion_bmm350()

        if self.available_sensors["MOTION"]["LSM303_ORIG"]:
            self.motion_sensor["ACC"] = True
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = "LSM303"
        if self.available_sensors["MOTION"]["LIS3MDL"]:
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = "LIS3MDL"
        if self.available_sensors["MOTION"]["LSM6DS"]:
            self.motion_sensor["ACC"] = True
            self.motion_sensor["GYRO"] = True
        if self.available_sensors["MOTION"]["ISM330DHCX"]:
            self.motion_sensor["ACC"] = True
            self.motion_sensor["GYRO"] = True
        if self.available_sensors["MOTION"]["MMC5983MA"]:
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = "MMC5983MA"
        if self.available_sensors["MOTION"]["LSM9DS1"]:
            self.motion_sensor["ACC"] = True
            self.motion_sensor["GYRO"] = True
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = "LSM9DS1"
        if self.available_sensors["MOTION"]["BMX160"]:
            self.motion_sensor["ACC"] = True
            self.motion_sensor["GYRO"] = True
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = "BMX160"
        if self.available_sensors["MOTION"]["BNO055"]:
            self.motion_sensor["ACC"] = True
            # self.motion_sensor['GYRO'] = True
            self.motion_sensor["MAG"] = True
            # self.motion_sensor['EULER'] = True
            self.motion_sensor["QUATERNION"] = True
            self.sensor_label["MAG"] = "BNO055"
        if self.available_sensors["MOTION"]["ICM20948"]:
            self.motion_sensor["ACC"] = True
            self.motion_sensor["GYRO"] = True
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = "ICM20948"
        if self.available_sensors["MOTION"]["BMI270"]:
            self.motion_sensor["ACC"] = True
            self.motion_sensor["GYRO"] = True
        if self.available_sensors["MOTION"]["BMM150"]:
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = "BMM150"
        if self.available_sensors["MOTION"]["BMM350"]:
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = "BMM350"

        # light sensors
        self.available_sensors["LIGHT"]["TCS3472"] = self.detect_light_tcs3472()
        self.available_sensors["LIGHT"]["VCNL4040"] = self.detect_light_vncl4040()
        self.available_sensors["LIGHT"]["LTR308ALS"] = self.detect_light_ltr308als()
        self.available_sensors["LIGHT"]["TSL2591"] = self.detect_light_tsl2591()

        # uv sensor
        self.available_sensors["UV"]["LTR390"] = self.detect_light_ltr390()

        # gas
        self.available_sensors["GAS"]["SGP40"] = self.detect_gas_sgp40()

        # button
        self.available_sensors["BUTTON"][
            "BUTTON_SHIM"
        ] = self.detect_button_button_shim()
        self.available_sensors["BUTTON"]["MCP23008"] = self.detect_button_mcp230xx()

        # battery
        self.available_sensors["BATTERY"]["PIJUICE"] = self.detect_battery_pijuice()
        self.available_sensors["BATTERY"]["PISUGAR3"] = self.detect_battery_pisugar3()

        # BHI3 Shuttle Board 3.0
        self.set_bhi3_s()

        # print
        self.print_sensors()

    def print_sensors(self):
        app_logger.info("detected I2C sensors:")
        for k in self.available_sensors.keys():
            for kk in self.available_sensors[k]:
                if self.available_sensors[k][kk]:
                    app_logger.info(f"  {k}: {self._sensor_log_name(kk)}")

    def _sensor_log_name(self, sensor_name):
        if sensor_name == "BHI3_S":
            return self._bhi3_s_log_name()
        return sensor_name

    def _bhi3_s_log_name(self):
        return _bhi3_target_sensor_name(self.bhi3_s_target)

    def set_bhi3_s(self):
        self.bhi3_s_target = ""
        if self.detect_bhi3_s_c():
            self.available_sensors["MOTION"]["BHI3_S"] = True
            self.sensor["i2c_imu"] = self.sensor_bhi3_s
            self.motion_sensor["ACC"] = True
            self.motion_sensor["GYRO"] = True
            self.motion_sensor["MAG"] = True
            self.sensor_label["MAG"] = self._bhi3_s_log_name()
            self.available_sensors["PRESSURE"]["BHI3_S"] = True  # includes BMP581 and BME688
            self.sensor["i2c_baro_temp"] = self.sensor_bhi3_s
            self.bhi3_s_heading_corr = 0
            if (
                not self.config.G_IMU_AXIS_SWAP_XY["STATUS"]
                and self.config.G_IMU_AXIS_CONVERSION["STATUS"]
                and list(self.config.G_IMU_AXIS_CONVERSION["COEF"]) == [1.0, -1.0, -1.0]
            ):
                self.bhi3_s_heading_corr = 90

    def set_sensors(self):
        # barometic pressure & temperature sensor
        if self.available_sensors["PRESSURE"].get("BMP280"):
            self.sensor["i2c_baro_temp"] = self.sensor_bmp280
        elif self.available_sensors["PRESSURE"].get("BMP280_ORIG"):
            self.sensor["i2c_baro_temp"] = self.sensor_bmp280
        elif self.available_sensors["PRESSURE"].get("BME280"):
            self.sensor["i2c_baro_temp"] = self.sensor_bme280
        elif self.available_sensors["PRESSURE"].get("LPS3XHW"):
            self.sensor["i2c_baro_temp"] = self.sensor_lps35hw
        elif self.available_sensors["PRESSURE"].get("LPS3XHW_ORIG"):
            self.sensor["i2c_baro_temp"] = self.sensor_lps33hw
        elif self.available_sensors["PRESSURE"].get("BMP3XX"):
            self.sensor["i2c_baro_temp"] = self.sensor_bmp3xx
        elif self.available_sensors["PRESSURE"].get("MS5637"):
            self.sensor["i2c_baro_temp"] = self.sensor_ms5637
        elif self.available_sensors["PRESSURE"].get("BMP581"):
            self.sensor["i2c_baro_temp"] = self.sensor_bmp581

        # accelerometer & magnetometer sensor
        # acc + gyro
        if self.available_sensors["MOTION"].get("BMI270"):
            self.sensor["i2c_imu"] = self.sensor_bmi270
        elif self.available_sensors["MOTION"].get("LSM6DS"):
            self.sensor["i2c_imu"] = self.sensor_lsm6ds
        # acc + mag
        if self.available_sensors["MOTION"].get("ISM330DHCX"):
            self.sensor["i2c_imu"] = self.sensor_ism330dhcx
        elif self.available_sensors["MOTION"].get("LSM303_ORIG"):
            self.sensor["i2c_imu"] = self.sensor_lsm303
        # mag
        if self.available_sensors["MOTION"].get("BMM150"):
            self.sensor["i2c_mag"] = self.sensor_bmm150
        elif self.available_sensors["MOTION"].get("BMM350"):
            self.sensor["i2c_mag"] = self.sensor_bmm350
        elif self.available_sensors["MOTION"].get("MMC5983MA"):
            self.sensor["i2c_mag"] = self.sensor_mmc5983ma
        elif self.available_sensors["MOTION"].get("LIS3MDL"):
            self.sensor["i2c_mag"] = self.sensor_lis3mdl
        # acc + gyro + mag
        if self.available_sensors["MOTION"].get("BMX160"):
            self.sensor["i2c_imu"] = self.sensor_bmx160
        elif self.available_sensors["MOTION"].get("LSM9DS1"):
            self.sensor["i2c_imu"] = self.sensor_lsm9ds1
        elif self.available_sensors["MOTION"].get("ICM20948"):
            self.sensor["i2c_imu"] = self.sensor_icm20948
        # euler and quaternion
        if self.available_sensors["MOTION"].get("BNO055"):
            self.sensor["i2c_imu"] = self.sensor_bno055

        # light sensor
        if self.available_sensors["LIGHT"].get("VCNL4040"):
            self.sensor["lux"] = self.sensor_vcnl4040
        elif self.available_sensors["LIGHT"].get("LTR308ALS"):
            self.sensor["lux"] = self.sensor_ltr308als
        elif self.available_sensors["LIGHT"].get("TCS3472"):
            self.sensor["lux"] = self.sensor_tcs3472
        elif self.available_sensors["LIGHT"].get("TSL2591"):
            self.sensor["lux"] = self.sensor_tsl2591

        # uv sensor
        if self.available_sensors["UV"].get("LTR390"):
            self.sensor["uv"] = self.sensor_ltr390

        # gas sensor
        if self.available_sensors["GAS"].get("SGP40"):
            self.sensor["gas"] = self.sensor_sgp40
        
        if self.available_sensors["MOTION"].get("BHI3_S"):
            self.sensor["i2c_imu"] = self.sensor_bhi3_s
        if self.available_sensors["PRESSURE"].get("BHI3_S"):
            self.sensor["i2c_baro_temp"] = self.sensor_bhi3_s

    def reset(self):
        for key in self.elements:
            self.values[key] = np.nan
        for key in self.elements_vec:
            self.values[key] = np.zeros(3)
        self.values["mag_scale"] = np.ones(3)
        self.do_mag_calibration = False
        self.do_pitch_roll_calibration = False
        self.mag_calib_ready = False
        # for LP filter
        for key in self.elements:
            self.pre_value[key] = np.nan
        for key in self.elements_vec:
            self.pre_value[key] = np.full(3, np.nan)
        # for median filter
        for key in self.median_keys:
            self.pre_values_array[key] = np.full(self.pre_value_window_size, np.nan)
        # for average filter
        for key in self.average_keys:
            self.average_val[key] = np.full(self.ave_window_size, np.nan)
        # for quaternions (4 elements)
        self.values["quaternion"] = np.zeros(4)
        self.pre_value["quaternion"] = np.zeros(4)

        # for temporary values
        for key in self.elements_vec_mod:
            self.values_mod[key] = np.zeros(3)
        for key in ("mag_min", "mag_max"):
            self.values_mod.setdefault(key, None)
        self.gyro_average_array = np.zeros((3, int(2 / self.config.G_I2C_INTERVAL) + 1))

        self.values["total_ascent"] = 0
        self.values["total_descent"] = 0
        self.values["accumulated_altitude"] = 0

        self.graph_values = {}
        for g in self.graph_keys:
            self.graph_values[g] = np.full(
                (3, self.config.G_GUI_ACC_TIME_RANGE), np.nan
            )

        # for moving status
        self.mov_window_size = int(2 / self.config.G_I2C_INTERVAL) + 1
        self.acc_raw_hist = np.zeros((3, self.mov_window_size))
        self.acc_hist = np.zeros((3, self.mov_window_size))
        self.euler_array = np.zeros((2, self.mov_window_size))
        self.acc_variance = np.zeros(3)
        self.moving = np.ones(self.mov_window_size)

        samples_per_second = max(1, int(1 / self.config.G_I2C_INTERVAL))
        self.vspeed_window_size = self.vspeed_window_duration * samples_per_second
        self.timestamp_size = self.timestamp_duration * samples_per_second
        self.timestamp_array = [None] * self.timestamp_size
        self.vspeed_array = [np.nan] * self.vspeed_window_size

        if (
            self.values_mod["mag_min"] is not None
            and self.values_mod["mag_max"] is not None
        ):
            self.calc_mag_scales()

        self._bhi3_raw_data_record_status = "INIT"
        self._mag_calibration_prev_i2c_interval = None

    def start_coroutine(self):
        asyncio.create_task(self.start())

    async def start(self):
        while not self.quit_status:
            await self.sleep()
            await self.update()
            self.get_sleep_time(self.config.G_I2C_INTERVAL)
    
    def quit(self):
        self.quit_status = True
        if self._mag_declination_task is not None:
            self._mag_declination_task.cancel()
        if self.available_sensors["BUTTON"].get("MCP23008", False):
            self.sensor_mcp23008.quit()

    @staticmethod
    def _parse_datetime_value(value):
        if value is None:
            return None

        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None

        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _is_valid_number(value):
        if value is None:
            return False
        try:
            return bool(np.isfinite(value))
        except TypeError:
            return False

    def _load_mag_declination_cache(self):
        state = self.config.state
        if state is None:
            return None

        declination = state.get_value("mag_declination_deg", None)
        updated_at = self._parse_datetime_value(
            state.get_value("mag_declination_updated_at", None)
        )
        lat = state.get_value("mag_declination_lat", None)
        lon = state.get_value("mag_declination_lon", None)

        if (
            not self._is_valid_number(declination)
            or updated_at is None
            or not self._is_valid_number(lat)
            or not self._is_valid_number(lon)
        ):
            return None

        return {
            "deg": float(declination),
            "updated_at": updated_at,
            "lat": float(lat),
            "lon": float(lon),
        }

    def _store_mag_declination_cache(self, declination, lat, lon, gps_time):
        state = self.config.state
        if state is None:
            return

        updated_at = gps_time.astimezone(timezone.utc).isoformat()
        state.set_value("mag_declination_deg", float(declination))
        state.set_value("mag_declination_updated_at", updated_at)
        state.set_value("mag_declination_lat", float(lat))
        state.set_value("mag_declination_lon", float(lon), force_apply=True)
        self._mag_declination_cache = {
            "deg": float(declination),
            "updated_at": self._parse_datetime_value(updated_at),
            "lat": float(lat),
            "lon": float(lon),
        }

    def _is_mag_declination_position_valid(
        self, gps_sensor, lat, lon, mode, status, dop, satellites
    ):
        if (
            not self._is_valid_number(lat)
            or not self._is_valid_number(lon)
            or abs(float(lat)) > 90
            or abs(float(lon)) > 180
        ):
            return False

        try:
            mode_value = int(mode)
        except (TypeError, ValueError):
            return False
        if mode_value < 3:
            return False

        if len(dop) != 3:
            return False
        cutoff = getattr(gps_sensor, "valid_cutoff_dof", (99.0, 99.0, 99.0))
        for value, value_cutoff in zip(dop, cutoff):
            if not self._is_valid_number(value) or float(value) >= value_cutoff:
                return False

        try:
            used_sats = int(satellites[0])
        except (TypeError, ValueError):
            return False

        status_ok = False
        if gps_sensor is not None and hasattr(gps_sensor, "check_3DGPS_FIX_status"):
            status_ok = gps_sensor.check_3DGPS_FIX_status(status)
        if not status_ok and used_sats <= 3:
            return False

        return True

    def _get_mag_declination_context(self):
        logger = self.config.logger
        sensor_core = logger.sensor if logger is not None else None
        if sensor_core is None:
            return None

        gps_sensor = sensor_core.sensor_gps
        gps_values = sensor_core.values["GPS"]

        lat = gps_values["lat"]
        lon = gps_values["lon"]
        dop = (
            gps_values["pdop"],
            gps_values["hdop"],
            gps_values["vdop"],
        )
        satellites = (
            gps_values["used_sats"],
            gps_values["total_sats"],
        )
        if not self._is_mag_declination_position_valid(
            gps_sensor,
            lat,
            lon,
            gps_values["mode"],
            gps_values["status"],
            dop,
            satellites,
        ):
            return None

        gps_time = self._parse_datetime_value(gps_values["time"])
        if gps_time is None or gps_time.year < 2000:
            return None

        return {
            "lat": float(lat),
            "lon": float(lon),
            "gps_time": gps_time,
        }

    def _is_mag_declination_cache_hit(self, cache, lat, lon, gps_time):
        if cache is None:
            return False

        if gps_time.strftime("%Y-%m") != cache["updated_at"].strftime("%Y-%m"):
            return False

        distance = get_dist_on_earth(cache["lon"], cache["lat"], lon, lat)
        return distance <= _MAG_DECLINATION_CACHE_DISTANCE_CUTOFF_M

    def _apply_mag_declination(self, declination):
        self.config.G_IMU_MAG_DECLINATION = float(declination)
        self.is_mag_declination_modified = True

    def _schedule_mag_declination_update(self):
        if self.is_mag_declination_modified:
            return

        context = self._get_mag_declination_context()
        if context is None:
            return

        cache = self._mag_declination_cache
        if self._is_mag_declination_cache_hit(
            cache, context["lat"], context["lon"], context["gps_time"]
        ):
            self._apply_mag_declination(cache["deg"])
            app_logger.info(
                "mag declination cache hit: %.3f deg", cache["deg"]
            )
            return

        if self._mag_declination_fetch_started:
            return

        self._mag_declination_fetch_started = True
        app_logger.info("mag declination cache miss")
        self._mag_declination_task = asyncio.create_task(
            self._update_mag_declination_async(
                context["lat"], context["lon"], context["gps_time"]
            )
        )

    async def _fetch_mag_declination_from_bgs(self, lat, lon, gps_time):
        response = await get_json(
            _MAG_DECLINATION_API_URL,
            params={
                "latitude": f"{lat:.8f}",
                "longitude": f"{lon:.8f}",
                "altitude": "0",
                "date": gps_time.date().isoformat(),
                "format": "json",
            },
            timeout=_MAG_DECLINATION_FETCH_TIMEOUT_SEC,
        )
        if response is None:
            raise RuntimeError("failed to fetch magnetic declination")

        try:
            return float(
                response["geomagnetic-field-model-result"]["field-value"][
                    "declination"
                ]["value"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("invalid magnetic declination response") from exc

    async def _update_mag_declination_async(self, lat, lon, gps_time):
        cache = self._mag_declination_cache
        app_logger.info("mag declination fetch started")

        try:
            declination = await self._fetch_mag_declination_from_bgs(
                lat,
                lon,
                gps_time,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if cache is not None:
                self._apply_mag_declination(cache["deg"])
                app_logger.warning(
                    "mag declination fetch timed out/failed; using stale cache: %s",
                    exc,
                )
            else:
                self.is_mag_declination_modified = True
                app_logger.warning(
                    "mag declination fetch timed out/failed: %s",
                    exc,
                )
            return

        self._apply_mag_declination(declination)
        self._store_mag_declination_cache(declination, lat, lon, gps_time)
        app_logger.info("mag declination fetch succeeded: %.3f deg", declination)

    async def update(self):
        # timestamp
        self.values["timestamp"] = datetime.now()
        self.timestamp_array[0:-1] = self.timestamp_array[1:]
        self.timestamp_array[-1] = self.values["timestamp"]

        self.read_bhi3_s()

        self.read_acc()
        self.read_gyro()
        self.read_mag()
        self.read_quaternion()
        self.calc_motion()

        self.read_baro_temp()
        self.calc_altitude()

        self.read_light()
        self.read_gas()

        self.read_battery()

    def update_bhi3_raw_log_state(self):
        if not self.available_sensors["MOTION"].get("BHI3_S"):
            return

        imu = self.sensor.get("i2c_imu")
        if imu is None:
            return

        msg = None
        if self._bhi3_raw_data_record_status != "START":
            if not imu.raw_log_enabled:
                imu.start_and_stop()
                if imu.raw_log_enabled:
                    self._bhi3_raw_data_record_status = "START"
                    msg = "[BHI3] raw log started"
        elif self._bhi3_raw_data_record_status == "START":
            if imu.raw_log_enabled:
                imu.start_and_stop()
                self._bhi3_raw_data_record_status = "STOP"
                msg = "[BHI3] raw log stopped"
        
        if msg is not None:
            if self.config.gui is not None:
                self.config.gui.show_popup(msg, 5)
            app_logger.debug(msg)

    def update_mag_calibration_state(self):
        if not self.motion_sensor["MAG"]:
            msg = "[MAG] calibration unavailable"
        elif self.do_mag_calibration:
            self.do_mag_calibration = False
            if self._mag_calibration_prev_i2c_interval is not None:
                self.config.G_I2C_INTERVAL = self._mag_calibration_prev_i2c_interval
                self._mag_calibration_prev_i2c_interval = None

            raw_mags = getattr(self, "raw_mags", None)
            if raw_mags:
                np.savetxt("log/raw_mags.csv", raw_mags, delimiter=",", fmt="%.6f")
            if (
                self.values_mod["mag_min"] is not None
                and self.values_mod["mag_max"] is not None
            ):
                self.config.state.write()
            msg = "[MAG] calibration stopped"
        else:
            self.mag_calib_ready = False
            self.values_mod["mag_min"] = None
            self.values_mod["mag_max"] = None
            self.raw_mags = []
            self._mag_calibration_prev_i2c_interval = self.config.G_I2C_INTERVAL
            self.config.G_I2C_INTERVAL = 0.1
            self.do_mag_calibration = True
            msg = "[MAG] calibration started"

        if self.config.gui is not None:
            self.config.gui.show_popup(msg, 5)
        app_logger.info(msg)

    def update_pitch_roll_calibration_state(self):
        if not self.motion_sensor["ACC"] and not self.motion_sensor["QUATERNION"]:
            msg = "[PITCH_ROLL] calibration unavailable"
        elif self.do_pitch_roll_calibration:
            self.do_pitch_roll_calibration = False
            msg = "[PITCH_ROLL] calibration canceled"
        else:
            self.do_pitch_roll_calibration = True
            msg = "[PITCH_ROLL] calibration started"

        if self.config.gui is not None:
            self.config.gui.show_popup(msg, 5)
        app_logger.info(msg)

    def read_bhi3_s(self):
        if not self.available_sensors["MOTION"].get("BHI3_S"):
            return

        imu = self.sensor["i2c_imu"]
        if not imu.ready:
            return

        # self.values["raw_heading"] = (
        #     int(imu.heading) - self.bhi3_s_heading_corr + self.config.G_IMU_MAG_DECLINATION
        # ) % 360
        # self.values["heading"] = self.values["raw_heading"]
        # self.values["heading_str"] = get_track_str(self.values["heading"])

        # BHI3 Shuttle mounting can be corrected by the common heading offset.
        # Map BHI roll -> bike pitch (look down is plus),
        # and BHI pitch -> bike roll with the same sign trend.
        self.values["pitch"] = math.radians(((float(imu.roll) + 360) % 360 - 180))
        self.values["roll"] = math.radians(((float(imu.pitch) + 180) % 360 - 180))
        self.values["grade_pitch"] = 100 * math.tan(self.values["pitch"])

    def read_light(self):
        if not self.available_sensors["LIGHT"] and not self.available_sensors["UV"]:
            return
        try:
            if (
                self.available_sensors["LIGHT"].get("VCNL4040")
                or self.available_sensors["LIGHT"].get("LTR308ALS")
                or self.available_sensors["LIGHT"].get("TSL2591")
            ):
                self.values["light"] = int(self.sensor["lux"].lux)
            elif self.available_sensors["LIGHT"].get("TCS3472"):
                self.values["light"] = int(self.sensor["lux"].light())
            if self.available_sensors["LIGHT"].get("TSL2591"):
                self.values["infrared"] = int(self.sensor["lux"].infrared)
            if self.available_sensors["UV"].get("LTR390"):
                self.values["uvi"] = int(self.sensor["uv"].uvi)
        except:
            return

    def read_gas(self):
        if not self.available_sensors["GAS"]:
            return
        try:
            if (
                self.available_sensors["GAS"].get("SGP40")
                and self.available_sensors["PRESSURE"].get("BME280")
            ):
                self.values["voc_index"] = int(
                    self.sensor["gas"].measure_index(
                        temperature=self.values["temperature"],
                        relative_humidity=self.values["humidity"],
                    )
                )
                self.values["raw_gas"] = int(self.sensor["gas"].raw)
        except:
            return

    def read_battery(self):
        if not self.available_sensors["BATTERY"]:
            return
        try:
            if self.available_sensors["BATTERY"].get("PIJUICE"):
                bv = self.sensor_pijuice.status.GetBatteryVoltage()
                bc = self.sensor_pijuice.status.GetBatteryCurrent()
                iv = self.sensor_pijuice.status.GetIoVoltage()
                ic = self.sensor_pijuice.status.GetIoCurrent()
                bl = self.sensor_pijuice.status.GetChargeLevel()
                if bv["error"] == "NO_ERROR":
                    self.values["voltage_battery"] = bv["data"] / 1000
                if bc["error"] == "NO_ERROR":
                    self.values["current_battery"] = bc["data"] / 1000
                if iv["error"] == "NO_ERROR":
                    self.values["voltage_out"] = iv["data"] / 1000
                if ic["error"] == "NO_ERROR":
                    self.values["current_out"] = ic["data"] / 1000
                if bl["error"] == "NO_ERROR":
                    self.values["battery_percentage"] = bl["data"]
            elif self.available_sensors["BATTERY"].get("PISUGAR3"):
                self.sensor_pisugar3.read()
                self.values["battery_percentage"] = self.sensor_pisugar3.battery_level
        except:
            pass

    def change_axis(self, a, is_mag=False):
        # acc
        # X: to North (up rotation is plus)
        # Y: to West (up rotation is plus)
        # Z: to down (plus)

        # gyro(usually same as acc)
        # X: to North (right rotation is plus)
        # Y: to West (down rotation is plus)
        # Z: to down (Counterclockwise is plus)

        # mag(sometimes different from acc or gyro)
        # X: to North (north is max, south is min)
        # Y: to West (east is max, west is min)
        # Z: to down (minus)
        # Check that the azimuth can be obtained with math.atan2(y, x) in the horizontal state.

        # X-Y swap
        if is_mag and self.config.G_IMU_MAG_AXIS_SWAP_XY["STATUS"]:
            a[0:2] = a[1::-1]
        elif not is_mag and self.config.G_IMU_AXIS_SWAP_XY["STATUS"]:
            a[0:2] = a[1::-1]

        # X, Y, Zinversion
        if is_mag and self.config.G_IMU_MAG_AXIS_CONVERSION["STATUS"]:
            a = a * self.config.G_IMU_MAG_AXIS_CONVERSION["COEF"]
        elif not is_mag and self.config.G_IMU_AXIS_CONVERSION["STATUS"]:
            a = a * self.config.G_IMU_AXIS_CONVERSION["COEF"]

        return a

    def read_acc(self, return_raw=False):
        if not self.motion_sensor["ACC"]:
            return
        try:
            # get raw acc (normalized by gravitational acceleration, g = 9.80665)
            if self.available_sensors["MOTION"].get("BHI3_S"):
                self.values["acc_raw"] = np.array(self.sensor["i2c_imu"].acc)
            elif (
                self.available_sensors["MOTION"].get("LSM303_ORIG")
                or self.available_sensors["MOTION"].get("BMI270")
            ):
                self.sensor["i2c_imu"].read_acc()
                self.values["acc_raw"] = np.array(self.sensor["i2c_imu"].values["acc"])
            elif (
                self.available_sensors["MOTION"].get("LSM6DS")
                or self.available_sensors["MOTION"].get("ISM330DHCX")
                or self.available_sensors["MOTION"].get("BNO055")
                or self.available_sensors["MOTION"].get("ICM20948")
            ):
                # sometimes BNO055 returns [None, None, None] array occurs
                self.values["acc_raw"] = (
                    np.array(self.sensor["i2c_imu"].acceleration) / G
                )
            elif self.available_sensors["MOTION"].get("LSM9DS1"):
                self.values["acc_raw"] = (
                    np.array(list(self.sensor["i2c_imu"].acceleration)) / G
                )
            elif self.available_sensors["MOTION"].get("BMX160"):
                self.values["acc_raw"] = np.array(self.sensor["i2c_imu"].accel) / G
        except:
            return
        self.values["acc_raw"] = self.change_axis(self.values["acc_raw"])

        if return_raw:
            return

        self.values["acc_mod"] = self.values["acc_raw"].copy()
        # LP filter
        # self.lp_filter('acc_mod', 4)

    def read_gyro(self, return_raw=False):
        if not self.motion_sensor["GYRO"]:
            return
        try:
            if self.available_sensors["MOTION"].get("BHI3_S"): # rad/sec
                self.values["gyro_raw"] = np.array(self.sensor["i2c_imu"].gyro)
            elif self.available_sensors["MOTION"].get("BMI270"): # rad/sec
                self.values["gyro_raw"] = np.array(self.sensor["i2c_imu"].values["gyro"])
            elif (
                self.available_sensors["MOTION"].get("LSM6DS") # rad/sec
                or self.available_sensors["MOTION"].get("ISM330DHCX") # rad/sec
                or self.available_sensors["MOTION"].get("BMX160") # deg/sec
                or self.available_sensors["MOTION"].get("ICM20948") # deg/sec
            ):
                self.values["gyro_raw"] = np.array(self.sensor["i2c_imu"].gyro)
            elif self.available_sensors["MOTION"].get("LSM9DS1"): # rad/sec
                self.values["gyro_raw"] = np.array(list(self.sensor["i2c_imu"].gyro))
            elif self.available_sensors["MOTION"].get("BNO055"): # rad/sec
                # sometimes BNO055 returns [None, None, None] array occurs
                self.values["gyro_raw"] = np.array(self.sensor["i2c_imu"].gyro) / 1.0
        except:
            return
        self.values["gyro_raw"] = self.change_axis(self.values["gyro_raw"])

        # convert units (degree -> radians)
        if (
            self.available_sensors["MOTION"].get("BMX160")
            or self.available_sensors["MOTION"].get("ICM20948")
        ):
            self.values["gyro_raw"] = np.radians(self.values["gyro_raw"])

        if return_raw:
            return

        # BHI3_S gyro is already preprocessed in the C layer.
        # Skip python-side calibration / LP / fusion path.
        if self.available_sensors["MOTION"].get("BHI3_S"):
            self.values["gyro_mod"] = self.values["gyro_raw"].copy()
            return

        # calibration
        self.gyro_average_array[:, 0:-1] = self.gyro_average_array[:, 1:]
        self.gyro_average_array[:, -1] = self.values["gyro_raw"]
        #if self.do_position_calibration:
        #    self.values_mod["gyro_ave"] = np.nanmean(self.gyro_average_array, axis=1)
        self.values["gyro_mod"] = self.values["gyro_raw"].copy()  # - self.values_mod["gyro_ave"]

        # LP filter
        self.lp_filter("gyro_mod", 5)

        # finalize gyro
        # angle from fixed_roll and fixed_pitch
        acc_angle = np.zeros(3)
        ratio = 0.9
        if not np.isnan(self.values["pitch"]) and not np.isnan(self.values["roll"]):
            acc_angle[0] = self.values["roll"] - self.values["fixed_roll"]
            acc_angle[1] = self.values["pitch"] - self.values["fixed_pitch"]
        self.values["gyro"] = (
            ratio
            * (
                self.values["gyro"]
                + self.values["gyro_mod"] * self.config.G_I2C_INTERVAL
            )
            + (1 - ratio) * acc_angle
        )

    def read_mag(self):
        if not self.motion_sensor["MAG"]:
            return
        try:
            if self.available_sensors["MOTION"].get("BHI3_S"):
                self.values["mag_raw"] = np.array(self.sensor["i2c_imu"].mag)
            elif (
                self.available_sensors["MOTION"].get("MMC5983MA")
                or self.available_sensors["MOTION"].get("BMM150")
                or self.available_sensors["MOTION"].get("BMM350")
                or self.available_sensors["MOTION"].get("LIS3MDL")
            ):
                self.values["mag_raw"] = np.array(self.sensor["i2c_mag"].magnetic)
            elif (
                self.available_sensors["MOTION"].get("LSM303_ORIG")
                or self.available_sensors["MOTION"].get("ICM20948")
            ):
                self.values["mag_raw"] = np.array(self.sensor["i2c_imu"].magnetic)
            elif self.available_sensors["MOTION"].get("LSM9DS1"):
                self.values["mag_raw"] = np.array(list(self.sensor["i2c_imu"].magnetic))
            elif self.available_sensors["MOTION"].get("BMX160"):
                self.values["mag_raw"] = np.array(self.sensor["i2c_imu"].mag)
            elif self.available_sensors["MOTION"].get("BNO055"):
                # sometimes BNO055 returns [None, None, None] array occurs
                self.values["mag_raw"] = np.array(self.sensor["i2c_imu"].magnetic) / 1.0
        except Exception as e:
            app_logger.debug("read_mag error: %s", e)
            return
        self.values["mag_raw"] = self.change_axis(self.values["mag_raw"], is_mag=True)

        self.values["mag_mod"] = self.values["mag_raw"].copy()

        # calibration(hard/soft iron distortion)
        if self.do_mag_calibration:
            self.update_mag_calibration(self.values["mag_mod"])
            self.raw_mags.append(list(self.values["mag_raw"]))

        if self.mag_calib_ready:
            # hard iron distortion: - self.values['mag_center']
            # soft iron distortion: * self.values['mag_scale']
            self.values["mag_mod"] = (self.values["mag_mod"] - self.values['mag_center']) * self.values['mag_scale']

        # LP filter
        # self.lp_filter('mag_mod', 4)

        # finalize mag
        self.values["mag"] = self.values["mag_mod"]

    def calc_mag_scales(self):
        self.values['mag_center'] = (self.values_mod["mag_max"] + self.values_mod["mag_min"]) / 2
        axis = (self.values_mod["mag_max"] - self.values_mod["mag_min"]) / 2
        if np.any(np.isnan(axis)):
            self.mag_calib_ready = False
            return

        positive_axis = axis > 0
        if not np.any(positive_axis):
            self.mag_calib_ready = False
            return

        mag_scale = np.ones(3)
        mag_scale[positive_axis] = np.mean(axis[positive_axis]) / axis[positive_axis]
        self.values['mag_scale'] = mag_scale
        self.mag_calib_ready = True

    def update_mag_calibration(self, mag_sample):
        if np.any(np.isnan(mag_sample)) or not np.all(np.isfinite(mag_sample)):
            return

        pre_min = self.values_mod["mag_min"]
        pre_max = self.values_mod["mag_max"]
        if pre_min is None or pre_max is None:
            self.values_mod["mag_min"] = mag_sample.copy()
            self.values_mod["mag_max"] = mag_sample.copy()
        else:
            self.values_mod["mag_min"] = np.minimum(pre_min, mag_sample)
            self.values_mod["mag_max"] = np.maximum(pre_max, mag_sample)

        # store
        update_mag_min_max = False
        for pre, k in zip((pre_min, pre_max), ("mag_min", "mag_max")):
            if pre is None or np.any(pre != self.values_mod[k]):
                update_mag_min_max = True
                self.config.state.set_value(
                    k + "_" + self.sensor_label["MAG"], self.values_mod[k]
                )
                app_logger.info(f"update {k}: {self.values_mod[k]}")
        if update_mag_min_max:
            self.calc_mag_scales()

    def read_quaternion(self):
        if not self.motion_sensor["QUATERNION"]:
            return
        try:
            if self.available_sensors["MOTION"].get("BNO055"):
                # sometimes [None, None, None] array occurs
                self.values["quaternion"] = (
                    np.array(self.sensor["i2c_imu"].quaternion) / 1.0
                )
        except:
            return

    def calc_motion(self):
        # get pitch, roll and yaw into self.values
        self.get_pitch_roll_yaw()

        # detect start/stop status and position(fixed_pitch, fixed_roll)
        self.detect_motion()

        # calc acc based on fixed_pitch and fixed_roll
        self.modified_acc()

        # calc heading using yaw_for_heading, fixed_pitch and fixed_roll
        #self.calc_heading()
        self.calc_heading(self.values["yaw_for_heading"])

    def get_pitch_roll_yaw(self):
        # pitch : the direction to look down is plus
        # roll  : the direction to left up is plus
        # yaw   : clockwise rotation is plus, and the north is 0 (-180~+180)
        if self.motion_sensor["QUATERNION"]:
            self.calc_pitch_roll_yaw_from_quaternion()
        elif self.motion_sensor["ACC"] and self.motion_sensor["MAG"]:
            self.calc_pitch_roll_yaw_from_acc_mag()

    def calc_pitch_roll_yaw_from_quaternion(self):
        if not all(self.values["quaternion"]):
            return

        w, x, y, z = self.values["quaternion"]
        y2 = y * y
        self.values["roll"] = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y2))

        sinp = 2 * (w * y - z * x)
        if abs(sinp) >= 1:
            self.values["pitch"] = math.copysign(math.pi / 2, sinp)
        else:
            self.values["pitch"] = math.asin(sinp)

        self.values["yaw"] = math.atan2(1 - 2 * (y2 + z * z), 2 * (w * z + x * y))
        self.values["yaw_for_heading"] = self.values["yaw"]

    def calc_pitch_roll_yaw_from_acc_mag(self):
        if not self.motion_sensor["ACC"] or not self.motion_sensor["MAG"]:
            return

        self.values["pitch"], self.values["roll"] = self.get_pitch_roll(
            self.values["acc_mod"]
        )
        self.values["yaw"] = self.get_yaw(
            self.values["mag"], self.values["pitch"], self.values["roll"]
        )

        self.values["yaw_for_heading"] = self.get_yaw(
            self.values["mag"], self.values["fixed_pitch"], self.values["fixed_roll"]
        )

    def calc_heading(self, yaw):
        self._schedule_mag_declination_update()

        if np.isnan(yaw):
            if self.motion_sensor["MAG"]:
                self.values["raw_heading"] = int(
                    math.degrees(
                        math.atan2(self.values['mag'][1], self.values['mag'][0])
                    )
                    + self.config.G_IMU_MAG_DECLINATION
                ) % 360        
                self.values["heading_str"] = get_track_str(self.values["raw_heading"])
                self.values["heading"] = self.values["raw_heading"]
            return

        # set heading with yaw
        tilt_heading = yaw + math.radians(self.config.G_IMU_MAG_DECLINATION)
        if tilt_heading < 0:
            tilt_heading += 2 * math.pi
        elif tilt_heading > 2 * math.pi:
            tilt_heading -= 2 * math.pi

        self.values["heading"] = int(math.degrees(tilt_heading))
        self.values["heading_str"] = get_track_str(self.values["heading"])

    @staticmethod
    def get_pitch_roll(acc):
        pitch = math.atan2(-acc[X], (math.sqrt(acc[Y] ** 2 + acc[Z] ** 2)))
        roll = math.atan2(acc[Y], acc[Z])
        return pitch, roll

    @staticmethod
    def get_yaw(mag, pitch, roll):
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)
        cos_r = math.cos(roll)
        sin_r = math.sin(roll)
        tiltcomp_x = mag[X] * cos_p + mag[Z] * sin_p
        tiltcomp_y = mag[X] * sin_r * sin_p + mag[Y] * cos_r - mag[Z] * sin_r * cos_p
        yaw = math.atan2(tiltcomp_y, tiltcomp_x)
        return yaw

    def detect_motion(self):
        # require acc
        if not self.motion_sensor["ACC"]:
            return

        self.update_moving_threshold()

        moving = 1
        if self.acc_variance[Z] < self.moving_threshold:
            moving = 0
        self.moving[0:-1] = self.moving[1:]
        self.moving[-1] = moving
        # moving status (0:off=stop, 1:on=running)
        self.values["m_stat"] = self.moving[-1]

        self.calibrate_pitch_roll_if_stopped()

    def calibrate_pitch_roll_if_stopped(self):
        # calibrate position
        if not self.do_pitch_roll_calibration or sum(self.moving) != 0:
            return

        pitch = roll = np.nan
        if self.motion_sensor["ACC"]:
            pitch, roll = self.get_pitch_roll(
                [
                    np.average(self.acc_raw_hist[0]),
                    np.average(self.acc_raw_hist[1]),
                    np.average(self.acc_raw_hist[2]),
                ]
            )
        elif self.motion_sensor["QUATERNION"]:
            pitch = np.average(self.euler_array[0])
            roll = np.average(self.euler_array[1])

        if not np.any(np.isnan((pitch, roll))):
            self.values["fixed_pitch"] = pitch
            self.values["fixed_roll"] = roll
            self.config.state.set_value("fixed_pitch", pitch)
            self.config.state.set_value("fixed_roll", roll, force_apply=True)
            self.values["gyro"] = np.zeros(3)
            app_logger.info(
                f"calibrated position: pitch:{int(math.degrees(pitch))}, roll:{int(math.degrees(roll))}"
            )
            self.do_pitch_roll_calibration = False

    def update_moving_threshold(self):
        if self.motion_sensor["ACC"]:
            self.acc_raw_hist[:, 0:-1] = self.acc_raw_hist[:, 1:]
            self.acc_raw_hist[:, -1] = self.values["acc_raw"]
        elif self.motion_sensor["QUATERNION"]:
            self.euler_array[:, 0:-1] = self.euler_array[:, 1:]
            self.euler_array[:, -1] = [self.values["pitch"], self.values["roll"]]

        self.acc_hist[:, 0:-1] = self.acc_hist[:, 1:]
        self.acc_hist[:, -1] = self.values["acc"]
        self.acc_variance = np.var(self.acc_hist, axis=1)

        if np.any(self.acc_variance == 0):
            return

        variance_order = np.floor(np.log10(self.acc_variance))
        self.values["acc_variance"] = variance_order
        o = variance_order[Z]
        # if np.sum(variance_order == o) >= 2 and o < self.moving_threshold_min:
        if o < self.moving_threshold_min:
            self.moving_threshold_min = o
            self.moving_threshold = pow(10, 0.57 * o)

    def modified_acc(self):
        # require acc
        if not self.motion_sensor["ACC"]:
            return
        # convert absolute coordinates
        cos_p = math.cos(self.values["pitch"])
        sin_p = math.sin(self.values["pitch"])
        cos_r = math.cos(self.values["roll"])
        sin_r = math.sin(self.values["roll"])
        # cos_y = math.cos(self.values['yaw'])
        # sin_y = math.sin(self.values['yaw'])
        m_pitch = np.array([[cos_p, 0, sin_p], [0, 1, 0], [-sin_p, 0, cos_p]])
        m_roll = np.array([[1, 0, 0], [0, cos_r, -sin_r], [0, sin_r, cos_r]])
        # m_yaw   = np.array([[cos_y,-sin_y,0],[sin_y,cos_y,0],[0,0,1]])
        # m_acc   = np.array([[ax],[ay],[az]])
        m_acc = np.array(self.values["acc_mod"]).reshape(3, 1)

        m_acc_mod = m_roll @ m_pitch @ m_acc
        # m_acc_mod = m_yaw@m_roll@m_pitch@m_acc

        # finalize acc
        self.values["acc"] = m_acc_mod.reshape(3)
        # remove gravity (converted acceleration - gravity)
        self.values["acc"][Z] -= 1.0

        # test
        cos_p = math.cos(self.values["fixed_pitch"])
        sin_p = math.sin(self.values["fixed_pitch"])
        cos_r = math.cos(self.values["fixed_roll"])
        sin_r = math.sin(self.values["fixed_roll"])
        m_pitch = np.array([[cos_p, 0, sin_p], [0, 1, 0], [-sin_p, 0, cos_p]])
        m_roll = np.array([[1, 0, 0], [0, cos_r, -sin_r], [0, sin_r, cos_r]])
        m_acc = np.array(self.values["acc_mod"]).reshape(3, 1)
        m_acc_mod = m_roll @ m_pitch @ m_acc
        self.values["acc_graph"] = m_acc_mod.reshape(3)
        if self.available_sensors["MOTION"].get("BHI3_S"):
            self.values["acc_graph"][Z] += 1.0
        self.lp_filter("acc_graph", 3)

        # position quaternion
        # cosRoll = math.cos(roll*0.5)
        # sinRoll = math.sin(roll*0.5)
        # cosPitch = math.cos(pitch*0.5)
        # sinPitch = math.sin(pitch*0.5)
        # cosYaw = math.cos(yaw*0.5)
        # sinYaw = math.sin(yaw*0.5)
        # q0 = cosRoll * cosPitch * cosYaw + sinRoll * sinPitch * sinYaw
        # q1 = sinRoll * cosPitch * cosYaw - cosRoll * sinPitch * sinYaw
        # q2 = cosRoll * sinPitch * cosYaw + sinRoll * cosPitch * sinYaw
        # q3 = cosRoll * cosPitch * sinYaw - sinRoll * sinPitch * cosYaw

        # convert acceleration to earth coordinates
        # self.values['acc'][X] = (q0**2+q1**2-q2**2-q3**2)*ax + 2*(q1*q2-q0*q3)*ay + 2*(q0*q2+q1*q3)*az
        # self.values['acc'][Y] = 2*(q0*q3+q1*q2)*ax + (q0**2-q1**2+q2**2-q3**2)*ay + 2*(q2*q3-q0*q1)*az
        # self.values['acc'][Z] = 2*(q1*q3-q0*q2)*ax + 2*(q0*q1+q2*q3)*ay + (q0**2-q1**2-q2**2+q3**2)*az

        # motion
        self.values["motion"] = math.sqrt(
            sum(list(map(lambda x: x**2, self.values["acc_mod"])))
        )

        # put into graph
        for g in self.graph_keys:
            if g not in self.graph_values:
                continue
            self.graph_values[g][:, 0:-1] = self.graph_values[g][:, 1:]
            self.graph_values[g][:, -1] = self.values['acc_graph']

    def read_baro_temp(self):
        if not self.available_sensors["PRESSURE"]:
            return

        sp = self.available_sensors["PRESSURE"]

        def get_temperature():
            self.values["temperature"] = round(
                self.sensor["i2c_baro_temp"].temperature, 1
            )

        def get_discomfort_index():
            if not any(np.isnan([self.values["humidity"], self.values["temperature"]])):
                self.values["discomfort_index"] = 0.81*self.values["temperature"] + 0.01*self.values["humidity"]*(0.99*self.values["temperature"]-14.3) + 46.3


        if sp.get("BHI3_S"):
            get_temperature()
            self.values["pressure"] = self.sensor["i2c_baro_temp"].pressure
            # Keep compatibility for downstream users that read pressure_mod.
            self.values["pressure_mod"] = self.values["pressure"]
            self.values["humidity"] = self.sensor["i2c_baro_temp"].humidity
            get_discomfort_index()
            return

        try:
            if (
                sp.get("LPS3XHW_ORIG")
                or sp.get("BMP280_ORIG")
                or sp.get("BME280")
                or sp.get("BMP3XX")
                or sp.get("MS5637")
                or sp.get("BMP581")
            ):
                self.sensor["i2c_baro_temp"].read()
            get_temperature()
            self.values["pressure_raw"] = self.sensor["i2c_baro_temp"].pressure
            if sp.get("BME280"):
                self.values["humidity"] = self.sensor["i2c_baro_temp"].relative_humidity
                get_discomfort_index()
        except:
            return

        self.values["pressure_mod"] = self.values["pressure_raw"]

        # spike detection
        self.median_filter("pressure_mod")
        # outlier(spike) detection
        # sigma is not 3 but 10 for detecting pressure diff 0.3hPa around 1000hPa
        self.hampel_filter("pressure_mod", sigma=10, diff_min=0.02)

        # finalize
        self.values["pressure"] = self.values["pressure_mod"]

    def calc_altitude(self):
        if np.isnan(self.values["pressure"]):
            return

        altitude_raw = (
            self.sealevel_temp
            / 0.0065
            * (1 - pow(self.values["pressure"] / self.sealevel_pa, 1.0 / 5.257))
        )

        if self.available_sensors["PRESSURE"].get("BHI3_S"):
            self.values["altitude"] = round(altitude_raw, 1)
        else:
            # average filter
            self.average_val["altitude"][0:-1] = self.average_val["altitude"][1:]
            self.average_val["altitude"][-1] = altitude_raw
            self.values["altitude"] = round(np.nanmean(self.average_val["altitude"]), 1)

        if self.config.G_STOPWATCH_STATUS == "START":
            # total ascent/descent
            v = self.values["altitude"]
            if np.isnan(self.values["pre_altitude"]) and not np.isnan(v):
                self.values["pre_altitude"] = v
            else:
                alt_diff = v - self.values["pre_altitude"]
                if abs(alt_diff) > self.total_ascent_threshold:
                    if alt_diff > 0:
                        self.values["total_ascent"] += alt_diff
                    elif alt_diff < 0:
                        self.values["total_descent"] += -alt_diff
                    self.values["accumulated_altitude"] += alt_diff
                    self.values["pre_altitude"] = v

            # vertical speed (m/s)
            self.vspeed_array[0:-1] = self.vspeed_array[1:]
            # self.vspeed_array[-1] = self.values['altitude']
            self.vspeed_array[-1] = self.values["pre_altitude"]
            if (
                self.timestamp_array[0] is not None
                and self.timestamp_array[-1] is not None
            ):
                i = 0
                time_delta = (
                    self.timestamp_array[-1] - self.timestamp_array[i]
                ).total_seconds()
                if time_delta > 0:
                    altitude_delta = self.vspeed_array[-1] - self.vspeed_array[i]
                    self.values["vertical_speed"] = altitude_delta / time_delta

    async def update_sealevel_pa(self, alt, force=False):
        if (
            (not force and self.sealevel_altitude_calibrated)
            or np.isnan(self.values["pressure"])
            or np.isnan(self.values["temperature"])
            or np.isnan(alt)
        ):
            return
        if self.config.logger is None:
            return

        # get temperature
        temperature = None

        ant_value = np.nan
        if (
            self.config.G_ANT["ID_TYPE"]["TEMP"]
            in self.config.logger.sensor.values["ANT+"]
        ):
            ant_value = self.config.logger.sensor.values["ANT+"][
                self.config.G_ANT["ID_TYPE"]["TEMP"]
            ]["temperature"]

        # from ANT+ sensor (tempe), not use I2C sensor because of inaccuracy
        if (
            self.config.G_ANT["USE"]["TEMP"]
            and self.config.G_ANT["ID_TYPE"]["TEMP"] != 0
            and not np.isnan(ant_value)
        ):
            temperature = ant_value
            self.sealevel_temp = 273.15 + ant_value + 0.0065 * alt

        # from Open-Meteo API with current point
        else:
            v = self.config.logger.sensor.values["GPS"]
            try:
                api_data = await self.config.api.get_openmeteo_temperature_data(
                    v["lon"], v["lat"]
                )
                if api_data is not None and "current" in api_data:
                    temperature = api_data["current"]["temperature_2m"]
                    self.sealevel_temp = temperature + 273.15 + 0.0065 * alt
            except:
                pass

        self.sealevel_pa = self.values["pressure"] * pow(
            (self.sealevel_temp - 0.0065 * alt) / self.sealevel_temp, -5.257
        )
        self.config.state.set_value("sealevel_pa", self.sealevel_pa)
        self.config.state.set_value(
            "sealevel_temp", self.sealevel_temp, force_apply=True
        )

        # reset historical altitude
        self.average_val["altitude"] = np.full(self.ave_window_size, np.nan)
        self.values["pre_altitude"] = np.nan

        app_logger.info("update sealevel pressure")
        app_logger.info(f"altitude: {alt} m")
        app_logger.info(f"pressure: {round(self.values['pressure'], 3)} hPa")
        if temperature is not None:
            app_logger.info(f"temp: {round(temperature, 1)} C")
        app_logger.info(
            f"sealevel temperature: {round(self.sealevel_temp - 273.15, 1)} C"
        )
        app_logger.info(f"sealevel pressure: {round(self.sealevel_pa, 3)} hPa")

        self.sealevel_altitude_calibrated = True

    def lp_filter(self, key, filter_val):
        if key not in self.values:
            return
        if not np.any(np.isnan(self.pre_value[key])):
            self.values[key] = (
                self.values[key] + (filter_val - 1) * self.pre_value[key]
            ) / filter_val
        self.pre_value[key] = self.values[key]

    def median_filter(self, key):
        if key not in self.median_keys:
            return
        self.pre_values_array[key][0:-1] = self.pre_values_array[key][1:]
        self.pre_values_array[key][-1] = self.values[key]
        self.median_val[key] = np.nanmedian(self.pre_values_array[key])

    def hampel_filter(self, key, sigma=3, diff_min=0):
        if key not in self.median_keys:
            return
        hampel_std = 1.4826 * np.nanmedian(
            np.abs(self.pre_values_array[key] - self.median_val[key])
        )
        if np.isnan(hampel_std):
            return
        hampel_value = np.abs(self.values[key] - self.median_val[key])
        if (hampel_value > diff_min) and (hampel_value > sigma * hampel_std):
            app_logger.info(
                f"pressure spike:{datetime.now().strftime('%Y%m%d %H:%M:%S')}, {self.values[key]:.3f}hPa, diff:{hampel_value:.3f}, threshold:{sigma * hampel_std:.3f}"
            )
            self.values[key] = self.median_val[key]

    async def led_blink(self, sec):
        if not self.available_sensors["BUTTON"].get("BUTTON_SHIM"):
            return
        t = sec
        while t > 0:
            self.sensor_button_shim.set_pixel(0x00, 0xFF, 0x00)
            await asyncio.sleep(0.5)
            self.sensor_button_shim.set_pixel(0x00, 0x00, 0x00)
            await asyncio.sleep(0.5)
            t -= 1

    def detect_bhi3_s_c(self):
        if not _i2c_addr_present(BHI3_I2C_ADDR):
            return False
        try:
            bhi3_target = _prepare_bhi3_build_target()
            # Prefer a prebuilt Cython extension if available.
            try:
                from .i2c.cython.bhi360_shuttle_board_3.bhi3_s_helper import BHI3_S
            except Exception:
                import pyximport
                pyximport.install(inplace=True, language_level=3)
                from .i2c.cython.bhi360_shuttle_board_3.bhi3_s_helper import BHI3_S

            self.sensor_bhi3_s = BHI3_S(1)
            if not self.sensor_bhi3_s.status:
                self.sensor_bhi3_s.close()
                del self.sensor_bhi3_s
                return False

            # Wait briefly so bootstrap can report failure before use.
            for _ in range(20):  # ~1s
                if self.sensor_bhi3_s.last_error != 0:
                    break
                if self.sensor_bhi3_s.ready:
                    break
                time.sleep(0.05)

            if self.sensor_bhi3_s.last_error != 0:
                self.sensor_bhi3_s.close()
                del self.sensor_bhi3_s
                return False

            sensor_is_bhi385 = self.sensor_bhi3_s.is_bhi385

            if bhi3_target:
                is_target_bhi385 = bhi3_target == "bhi385"
                if sensor_is_bhi385 != is_target_bhi385:
                    self.sensor_bhi3_s.close()
                    del self.sensor_bhi3_s
                    _remove_bhi3_helper_extensions()
                    return False
                _write_bhi3_target_marker(bhi3_target)

            self.bhi3_s_target = bhi3_target or (
                "bhi385" if sensor_is_bhi385 else "bhi360"
            )

            return True
        except:
            return False

    def detect_pressure_bmp280(self):
        try:
            import board
            import busio
            import adafruit_bmp280

            i2c = busio.I2C(board.SCL, board.SDA)
            self.sensor_bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c)
            self.sensor_bmp280.mode = adafruit_bmp280.MODE_NORMAL
            # STANDBY_TC_0_5, STANDBY_TC_10, STANDBY_TC_20, STANDBY_TC_62_5,
            # STANDBY_TC_125, STANDBY_TC_250, STANDBY_TC_500, STANDBY_TC_1000,
            self.sensor_bmp280.standby_period = adafruit_bmp280.STANDBY_TC_250
            # IIR_FILTER_DISABLE, IIR_FILTER_X2, IIR_FILTER_X4, IIR_FILTER_X8, IIR_FILTER_X16,
            self.sensor_bmp280.iir_filter = adafruit_bmp280.IIR_FILTER_X2
            # OVERSCAN_DISABLE, OVERSCAN_X1, OVERSCAN_X2, OVERSCAN_X4, OVERSCAN_X8, OVERSCAN_X16
            self.sensor_bmp280.overscan_pressure = adafruit_bmp280.OVERSCAN_X8
            self.sensor_bmp280.overscan_temperature = adafruit_bmp280.OVERSCAN_X1
            return True
        except:
            return False

    def detect_pressure_bmp280_orig(self):
        try:
            from .i2c.BMP280 import BMP280

            # device test
            if not BMP280.test():
                return False
            self.sensor_bmp280 = BMP280()
            return True
        except:
            return False

    def detect_pressure_lps3xhw(self):
        try:
            import board
            import adafruit_lps35hw

            self.sensor_lps35hw = adafruit_lps35hw.LPS35HW(board.I2C())
            self.sensor_lps35hw.low_pass_enabled = True
            # self.sensor_lps35hw.data_rate = adafruit_lps35hw.DataRate.RATE_1_HZ
            return True
        except:
            return False

    def detect_pressure_lps3xhw_orig(self):
        try:
            from .i2c.LPS33HW import LPS33HW

            if not LPS33HW.test():
                return False
            self.sensor_lps33hw = LPS33HW()
            return True
        except:
            return False

    def detect_pressure_bmp3xx(self):
        try:
            from .i2c.BMP3XX import BMP3XX

            # device test
            if not BMP3XX.test():
                return False
            self.sensor_bmp3xx = BMP3XX()
            return True
        except:
            return False

    def detect_pressure_ms5637(self):
        try:
            from .i2c.MS5637 import MS5637

            # device test
            if not MS5637.test():
                return False
            self.sensor_ms5637 = MS5637()
            return True
        except:
            return False

    def detect_pressure_bme280(self):
        try:
            import board
            from adafruit_bme280 import advanced as adafruit_bme280

            # for Waveshare Environment Sensor HAT
            self.sensor_bme280 = adafruit_bme280.Adafruit_BME280_I2C(
                board.I2C(), address=0x76
            )
            self.sensor_bme280.mode = adafruit_bme280.MODE_NORMAL
            # STANDBY_TC_0_5, STANDBY_TC_10, STANDBY_TC_20, STANDBY_TC_62_5,
            # STANDBY_TC_125, STANDBY_TC_250, STANDBY_TC_500, STANDBY_TC_1000,
            self.sensor_bme280.standby_period = adafruit_bme280.STANDBY_TC_250
            # IIR_FILTER_DISABLE, IIR_FILTER_X2, IIR_FILTER_X4, IIR_FILTER_X8, IIR_FILTER_X16,
            self.sensor_bme280.iir_filter = adafruit_bme280.IIR_FILTER_X2
            # OVERSCAN_DISABLE, OVERSCAN_X1, OVERSCAN_X2, OVERSCAN_X4, OVERSCAN_X8, OVERSCAN_X16
            self.sensor_bme280.overscan_pressure = adafruit_bme280.OVERSCAN_X8
            self.sensor_bme280.overscan_temperature = adafruit_bme280.OVERSCAN_X1
            return True
        except:
            return False

    def detect_pressure_bmp581(self):
        if self.detect_pressure_bmp581_c():
            return True

        try:
            from .i2c.BMP581 import BMP581

            # device test
            if not BMP581.test():
                return False
            self.sensor_bmp581 = BMP581()
            return True
        except:
            return False
    
    def detect_pressure_bmp581_c(self):
        if not _i2c_addr_present(BMP5_I2C_ADDR):
            return False
        try:
            # Prefer a prebuilt Cython extension if available.
            try:
                from .i2c.cython.i2c_helper import BMP5_C
            except Exception:
                import pyximport
                pyximport.install(inplace=True, language_level=3)
                from .i2c.cython.i2c_helper import BMP5_C

            self.sensor_bmp581 = BMP5_C(1)
            if self.sensor_bmp581.status:
                return True
            else:
                del(self.sensor_bmp581)
                return False
        except:
            return False

    def detect_motion_lsm6ds(self):
        try:
            import board
            import busio
            import adafruit_lsm6ds.lsm6ds33

            try:
                self.sensor_lsm6ds = adafruit_lsm6ds.lsm6ds33.LSM6DS33(
                    busio.I2C(board.SCL, board.SDA)
                )
            except:
                # For BerryGPS-IMU v4
                adafruit_lsm6ds.lsm6ds33.LSM6DS33.CHIP_ID = 0x6A
                self.sensor_lsm6ds = adafruit_lsm6ds.lsm6ds33.LSM6DS33(
                    busio.I2C(board.SCL, board.SDA)
                )
            self.sensor_lsm6ds.accelerometer_range = adafruit_lsm6ds.AccelRange.RANGE_2G
            self.sensor_lsm6ds.gyro_range = adafruit_lsm6ds.GyroRange.RANGE_125_DPS
            self.sensor_lsm6ds.accelerometer_data_rate = (
                adafruit_lsm6ds.Rate.RATE_12_5_HZ
            )
            self.sensor_lsm6ds.gyro_data_rate = adafruit_lsm6ds.Rate.RATE_12_5_HZ
            return True
        except:
            return False

    def detect_motion_ism330dhcx(self):
        try:
            import board
            import busio
            import adafruit_lsm6ds.ism330dhcx

            try:
                self.sensor_ism330dhcx = adafruit_lsm6ds.ism330dhcx.ISM330DHCX(
                    busio.I2C(board.SCL, board.SDA)
                )
            except:
                # For Sparkfun
                self.sensor_ism330dhcx = adafruit_lsm6ds.ism330dhcx.ISM330DHCX(
                    busio.I2C(board.SCL, board.SDA), address=0x6B
                )
            self.sensor_ism330dhcx.accelerometer_range = (
                adafruit_lsm6ds.AccelRange.RANGE_2G
            )
            self.sensor_ism330dhcx.gyro_range = adafruit_lsm6ds.GyroRange.RANGE_125_DPS
            self.sensor_ism330dhcx.accelerometer_data_rate = (
                adafruit_lsm6ds.Rate.RATE_12_5_HZ
            )
            self.sensor_ism330dhcx.gyro_data_rate = adafruit_lsm6ds.Rate.RATE_12_5_HZ
            return True
        except:
            return False

    def detect_motion_lis3mdl(self):
        try:
            import board
            import busio
            import adafruit_lis3mdl

            self.sensor_lis3mdl = adafruit_lis3mdl.LIS3MDL(
                busio.I2C(board.SCL, board.SDA)
            )
            return True
        except:
            return False

    def detect_motion_mmc5983ma(self):
        try:
            from .i2c.MMC5983MA import MMC5983MA

            # device test
            if not MMC5983MA.test():
                return False
            self.sensor_mmc5983ma = MMC5983MA()
            return True
        except:
            return False

    def detect_motion_lsm303_orig(self):
        try:
            from .i2c.LSM303D import LSM303D

            # device test
            if not LSM303D.test():
                return False
            self.sensor_lsm303 = LSM303D()
            return True
        except:
            return False

    def detect_motion_lsm9ds1(self):
        try:
            import board
            import busio
            import adafruit_lsm9ds1

            # self.sensor_lsm9ds1 = adafruit_lsm9ds1.LSM9DS1_I2C(busio.I2C(board.SCL, board.SDA),mag_address=0x1C, xg_address=0x6A)
            self.sensor_lsm9ds1 = adafruit_lsm9ds1.LSM9DS1_I2C(
                busio.I2C(board.SCL, board.SDA)
            )
            return True
        except:
            return False

    def detect_motion_bmx160(self):
        try:
            import board
            import busio
            import BMX160

            self.sensor_bmx160 = BMX160.BMX160_I2C(busio.I2C(board.SCL, board.SDA))
            self.sensor_bmx160.accel_range = BMX160.BMX160_ACCEL_RANGE_2G
            self.sensor_bmx160.accel_odr = 50
            self.sensor_bmx160.gyro_range = BMX160.BMX160_GYRO_RANGE_250_DPS
            return True
        except:
            return False

    def detect_motion_bno055(self):
        try:
            import board
            import busio
            import adafruit_bno055

            self.sensor_bno055 = adafruit_bno055.BNO055_I2C(
                busio.I2C(board.SCL, board.SDA)
            )
            return True
        except:
            return False

    def detect_motion_icm20948(self):
        try:
            import board
            import busio
            import adafruit_icm20x

            # for Waveshare Environment Sensor HAT
            self.sensor_icm20948 = adafruit_icm20x.ICM20948(
                busio.I2C(board.SCL, board.SDA), address=0x68
            )
            return True
        except:
            return False

    def detect_motion_bmi270(self):
        if self.detect_motion_bmi270_c():
            return True

        try:
            from .i2c.BMI270 import BMI270

            # device test
            if not BMI270.test():
                return False
            self.sensor_bmi270 = BMI270()
            return True
        except:
            return False

    def detect_motion_bmi270_c(self):
        if not _i2c_addr_present(BMI270_I2C_ADDR):
            return False
        try:
            # Prefer a prebuilt Cython extension if available.
            try:
                from .i2c.cython.i2c_helper import BMI270_C
            except Exception:
                import pyximport
                pyximport.install(inplace=True, language_level=3)
                from .i2c.cython.i2c_helper import BMI270_C

            self.sensor_bmi270 = BMI270_C(1)
            if self.sensor_bmi270.status:
                return True
            else:
                del(self.sensor_bmi270)
                return False
        except:
            return False

    def detect_motion_icm20948(self):
        try:
            import board
            import busio
            import adafruit_icm20x

            # for Waveshare Environment Sensor HAT
            self.sensor_icm20948 = adafruit_icm20x.ICM20948(
                busio.I2C(board.SCL, board.SDA), address=0x68
            )
            return True
        except:
            return False

    def detect_motion_bmm150(self):
        if self.detect_motion_bmm150_c():
            return True

        try:
            from .i2c.BMM150 import BMM150

            # device test
            if BMM150.test():
                self.sensor_bmm150 = BMM150()
            elif BMM150.test(address=0x12):
                self.sensor_bmm150 = BMM150(address=0x12)
            else:
                return False
            return True
        except:
            return False

    def detect_motion_bmm150_c(self):
        if not _i2c_addr_present(BMM150_I2C_ADDR):
            return False
        try:
            # Prefer a prebuilt Cython extension if available.
            try:
                from .i2c.cython.i2c_helper import BMM150_C
            except Exception:
                import pyximport
                pyximport.install(inplace=True, language_level=3)
                from .i2c.cython.i2c_helper import BMM150_C

            self.sensor_bmm150 = BMM150_C(1)
            if self.sensor_bmm150.status:
                return True
            else:
                del(self.sensor_bmm150)
                return False
        except:
            return False

    def detect_motion_bmm350(self):
        if not _i2c_addr_present(BMM350_I2C_ADDR):
            return False
        try:
            # Prefer a prebuilt Cython extension if available.
            try:
                from .i2c.cython.i2c_helper import BMM350_C
            except Exception:
                import pyximport
                pyximport.install(inplace=True, language_level=3)
                from .i2c.cython.i2c_helper import BMM350_C

            self.sensor_bmm350 = BMM350_C(1)
            if self.sensor_bmm350.status:
                return True
            else:
                del(self.sensor_bmm350)
                return False
        except:
            return False

    def detect_light_tcs3472(self):
        try:
            from envirophat import light

            light.light()
            self.sensor_tcs3472 = light
            return True
        except:
            return False

    def detect_light_vncl4040(self):
        try:
            from .i2c.VCNL4040 import VCNL4040

            if not VCNL4040.test():
                return False
            self.sensor_vcnl4040 = VCNL4040()
            self.sensor_vcnl4040.proximity_shutdown = True
            return True
        except:
            return False

    def detect_light_ltr308als(self):
        try:
            from .i2c.LTR308ALS import LTR308ALS

            if not LTR308ALS.test():
                return False
            self.sensor_ltr308als = LTR308ALS()
            return True
        except:
            return False

    def detect_light_tsl2591(self):
        try:
            import board
            import busio
            import adafruit_tsl2591

            self.sensor_tsl2591 = adafruit_tsl2591.TSL2591(
                busio.I2C(board.SCL, board.SDA)
            )
            self.sensor_tsl2591.gain = adafruit_tsl2591.GAIN_LOW
            # GAIN_LOW(1x gain), GAIN_MED(25x gain, default), GAIN_HIGH(428x gain), GAIN_MAX(9876x gain)
            # self.sensor_tsl2591.integration_time = adafruit_tsl2591.INTEGRATIONTIME_100MS
            # INTEGRATIONTIME_100MS(default), INTEGRATIONTIME_200MS, INTEGRATIONTIME_300MS,
            # INTEGRATIONTIME_400MS, INTEGRATIONTIME_500MS, INTEGRATIONTIME_600MS
            return True
        except:
            return False

    def detect_light_ltr390(self):
        try:
            import board
            import busio
            import adafruit_ltr390

            self.sensor_ltr390 = adafruit_ltr390.LTR390(busio.I2C(board.SCL, board.SDA))
            # self.sensor_ltr390.resolution = adafruit_ltr390.Resolution.RESOLUTION_16BIT
            # RESOLUTION_13BIT, RESOLUTION_16BIT(default), RESOLUTION_17BIT, RESOLUTION_18BIT, RESOLUTION_19BIT, RESOLUTION_20BIT
            # self.sensor_ltr390.gain = adafruit_ltr390.Gain.GAIN_1X
            # GAIN_1X, GAIN_3X, GAIN_6X, GAIN_9X, GAIN_18X
            # self.sensor_ltr390.measurement_delay = adafruit_ltr390.MeasurementDelay.DELAY_25MS
            # DELAY_25MS, DELAY_50MS, DELAY_100MS, DELAY_200MS, DELAY_500MS, DELAY_1000MS, DELAY_2000MS
            return True
        except:
            return False

    def detect_gas_sgp40(self):
        try:
            import board
            import busio
            import adafruit_sgp40

            self.sensor_sgp40 = adafruit_sgp40.SGP40(busio.I2C(board.SCL, board.SDA))
            return True
        except:
            return False

    def detect_button_button_shim(self):
        try:
            from .i2c.button_shim import ButtonShim

            self.sensor_button_shim = ButtonShim(self.config.button_config)
            return True
        except:
            return False

    def detect_button_mcp230xx(self):
        try:
            from .i2c.MCP230XX import MCP23008

            self.sensor_mcp23008 = MCP23008(self.config.button_config)
            #self.sensor_mcp23008 = MCP23008(self.config.button_config, int_pin=23)
            return True
        except:
            return False

    def detect_battery_pijuice(self):
        try:
            from pijuice import PiJuice

            # device test
            self.sensor_pijuice = PiJuice(1, 0x14)
            res = self.sensor_pijuice.status.GetStatus()
            if res["error"] == "COMMUNICATION_ERROR":
                return False
            return True
        except:
            return False

    def detect_battery_pisugar3(self):
        try:
            from .i2c.PiSugar3 import PiSugar3

            # device test
            if not PiSugar3.test():
                return False
            self.sensor_pisugar3 = PiSugar3()
            return True
        except:
            return False
