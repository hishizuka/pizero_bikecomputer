from datetime import datetime
from types import SimpleNamespace

import numpy as np

from .sensor_i2c import SensorI2C


class SensorUARTBridge(SensorI2C):
    def __init__(self, config, values, control_uart):
        self.control_uart = control_uart
        self._epoch = control_uart.epoch
        self._last_seq = {}
        super().__init__(config, values)

    def sensor_init(self):
        super().sensor_init()
        self.sensor["i2c_imu"] = SimpleNamespace(acceleration=None, gyro=None)
        self.sensor["i2c_mag"] = SimpleNamespace(magnetic=None)
        self.sensor["i2c_baro_temp"] = SimpleNamespace(pressure=None, temperature=None)
        self.sensor["lux"] = SimpleNamespace(lux=None)
        self.available_sensors["MOTION"].update(BMI270=True, BMM150=True)
        self.available_sensors["PRESSURE"]["BMP581"] = True
        self.available_sensors["LIGHT"]["LTR308ALS"] = True
        self.motion_sensor.update(ACC=True, GYRO=True, MAG=True)

    def _invalidate_readings(self):
        preserved = {
            key: self.values[key]
            for key in (
                "total_ascent",
                "total_descent",
                "accumulated_altitude",
                "fixed_pitch",
                "fixed_roll",
            )
        }
        self.reset()
        self.values.update(preserved)
        self.values["heading_magnetic_timestamp"] = None
        self._last_seq.clear()

    def _new_sample(self, sample):
        if sample is None or self._last_seq.get(sample.sensor) == sample.seq:
            return None
        self._last_seq[sample.sensor] = sample.seq
        return sample

    async def update(self):
        if self._epoch != self.control_uart.epoch:
            self._epoch = self.control_uart.epoch
            self._invalidate_readings()

        self.values["timestamp"] = datetime.now()
        self.timestamp_array[0:-1] = self.timestamp_array[1:]
        self.timestamp_array[-1] = self.values["timestamp"]
        self._update_motion()
        self._update_baro()
        self._update_light()

    def _update_motion(self):
        imu_recent = self.control_uart.latest("bmi270")
        mag_recent = self.control_uart.latest("bmm150")
        self.motion_sensor["ACC"] = imu_recent is not None
        self.motion_sensor["GYRO"] = imu_recent is not None
        self.motion_sensor["MAG"] = mag_recent is not None

        imu = self._new_sample(imu_recent)
        if imu is not None:
            values = imu.values
            self.sensor["i2c_imu"].acceleration = (
                values["ax_g"],
                values["ay_g"],
                values["az_g"],
            )
            self.sensor["i2c_imu"].gyro = (
                values["gx_rads"],
                values["gy_rads"],
                values["gz_rads"],
            )
            self.read_acc()
            self.read_gyro()

        mag = self._new_sample(mag_recent)
        if mag is not None:
            values = mag.values
            self.sensor["i2c_mag"].magnetic = (
                values["mx_ut"],
                values["my_ut"],
                values["mz_ut"],
            )
            self.read_mag()

        if (imu is not None or mag is not None) and imu_recent and mag_recent:
            self.calc_motion()
        elif mag_recent is None:
            for key in ("mag_raw", "mag_mod", "mag"):
                self.values[key] = np.full(3, np.nan)
            self.values["yaw"] = np.nan
            self.values["heading_magnetic_raw_deg"] = np.nan
            self.values["heading_magnetic_deg"] = np.nan
            self.values["heading_magnetic_timestamp"] = None

        if imu_recent is None:
            for key in ("acc_raw", "acc_mod", "acc", "gyro_raw", "gyro_mod", "gyro"):
                self.values[key] = np.full(3, np.nan)
            for key in ("pitch", "roll", "yaw", "motion"):
                self.values[key] = np.nan

    def _update_baro(self):
        baro = self.control_uart.latest("bmp580")
        if self._new_sample(baro) is not None:
            self.sensor["i2c_baro_temp"].pressure = baro.values["pressure_hpa"]
            self.sensor["i2c_baro_temp"].temperature = baro.values["temperature_c"]
            self.read_baro_temp()
            self.calc_altitude()
        elif baro is None:
            for key in (
                "pressure_raw",
                "pressure_mod",
                "pressure",
                "temperature",
                "altitude",
                "pre_altitude",
                "vertical_speed",
            ):
                self.values[key] = np.nan

    def _update_light(self):
        light = self.control_uart.latest("ltr308als")
        if self._new_sample(light) is not None:
            self.sensor["lux"].lux = light.values["lux"]
            self.read_light()
        elif light is None:
            self.values["light"] = np.nan
