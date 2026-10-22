import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import time
from types import SimpleNamespace

import numpy as np

from modules.app_logger import app_logger
from modules.utils.synchronized_yaw import HeadingMotionResult, SynchronizedYaw

from .sensor_i2c import SensorI2C

G_MOTION_QUEUE_SIZE = 64


@dataclass(frozen=True)
class GyroInterval:
    epoch: int
    seq: int
    ts_ms: int
    dt_us: int
    angular_velocity: tuple[float, float, float]
    continuous: bool
    acceleration: tuple[float, float, float] | None = None
    received_at: float = math.nan

class SensorUARTBridge(SensorI2C):
    @property
    def supports_gyro_intervals(self):
        if not self.control_uart.connected:
            return False
        sample = self.control_uart.samples.get("bmi270")
        return self.control_uart.sensor_protocol == "sensors/2" or (
            sample is not None and sample.dt_us is not None
        )

    def __init__(self, config, values, control_uart):
        self.control_uart = control_uart
        self._epoch = control_uart.epoch
        self._last_seq = {}
        self._imu_dt_us = None
        self._previous_imu = None
        self._gyro_intervals = deque(maxlen=G_MOTION_QUEUE_SIZE)
        self._magnetic_observations = deque(maxlen=G_MOTION_QUEUE_SIZE)
        self._gyro_calibration_task = None
        self._gyro_calibration_ready = False
        super().__init__(config, values)
        self._heading_yaw = SynchronizedYaw(acc_rest_z_sign=self._acc_rest_z_sign)

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
        self._previous_imu = None
        self._gyro_intervals.clear()
        self._magnetic_observations.clear()
        self._gyro_calibration_ready = False
        self._heading_yaw.reset()

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

        imu_samples = self.control_uart.drain("bmi270")
        mag_samples = self.control_uart.drain("bmm150")
        if imu_recent is None:
            imu_samples.clear()
        if mag_recent is None:
            mag_samples.clear()
        # ControlUART has already rejected duplicate and out-of-order samples.
        for imu in imu_samples:
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
            self._heading_yaw.observe_clock(imu)
            self._imu_dt_us = imu.dt_us
            previous = self._previous_imu
            continuous = (
                imu.dt_us is not None
                and previous is not None
                and previous.dt_us is not None
                and previous.epoch == imu.epoch
                and (imu.seq - previous.seq) % 2**32 == 1
                and abs((imu.ts_ms - previous.ts_ms) * 1000 - imu.dt_us) <= 1000
            )
            if imu.dt_us is not None and not continuous:
                self.values["gyro"] = np.zeros(3)
            self.read_gyro()
            if imu.dt_us is not None:
                if len(self._gyro_intervals) == self._gyro_intervals.maxlen:
                    self._gyro_intervals.clear()
                    continuous = False
                self._gyro_intervals.append(
                    GyroInterval(
                        imu.epoch,
                        imu.seq,
                        imu.ts_ms,
                        imu.dt_us,
                        tuple(float(value) for value in self.values["gyro_mod"]),
                        continuous,
                        tuple(float(value) for value in self.values["acc_mod"]),
                        imu.received_at,
                    )
                )
            self._previous_imu = imu

        for mag in mag_samples:
            values = mag.values
            self.sensor["i2c_mag"].magnetic = (
                values["mx_ut"],
                values["my_ut"],
                values["mz_ut"],
            )
            self.read_mag()
            self._heading_yaw.observe_clock(mag)
            self._magnetic_observations.append((mag, tuple(self.values["mag"])))

        if (imu_samples or mag_samples) and imu_recent and mag_recent:
            previous_heading_time = self.values["heading_magnetic_timestamp"]
            self.calc_motion()
            if mag_samples:
                # Preserve source age; recalculating with a new IMU is not a new mag.
                self.values["heading_magnetic_timestamp"] = datetime.now() - timedelta(
                    seconds=self._heading_yaw.source_age(
                        mag_samples[-1], time.monotonic()
                    )
                )
            else:
                self.values["heading_magnetic_timestamp"] = previous_heading_time
        elif mag_recent is None:
            for key in ("mag_raw", "mag_mod", "mag"):
                self.values[key] = np.full(3, np.nan)
            self.values["yaw"] = np.nan
            self.values["heading_magnetic_raw_deg"] = np.nan
            self.values["heading_magnetic_deg"] = np.nan
            self.values["heading_magnetic_timestamp"] = None

        if imu_recent is None:
            self._previous_imu = None
            for key in ("acc_raw", "acc_mod", "acc", "gyro_raw", "gyro_mod", "gyro"):
                self.values[key] = np.full(3, np.nan)
            for key in ("pitch", "roll", "yaw", "motion"):
                self.values[key] = np.nan

        if not self.supports_gyro_intervals:
            self._gyro_intervals.clear()
            self._magnetic_observations.clear()
            self._heading_yaw.reset()

    def take_gyro_intervals(self):
        intervals = list(self._gyro_intervals)
        self._gyro_intervals.clear()
        return intervals

    def take_magnetic_observations(self):
        observations = list(self._magnetic_observations)
        self._magnetic_observations.clear()
        return observations

    def update_heading_motion(self, transform_heading, *, model_ready=False):
        if not self.supports_gyro_intervals:
            self.take_gyro_intervals()
            self.take_magnetic_observations()
            self._heading_yaw.reset()
            return None
        if self.do_mag_calibration or self.do_pitch_roll_calibration:
            # Calibration changes the physical basis while samples are arriving.
            self.take_gyro_intervals()
            self.take_magnetic_observations()
            self._heading_yaw.reset(physical=True)
            return HeadingMotionResult("CALIBRATING", None)
        pitch, roll = self.values["fixed_pitch"], self.values["fixed_roll"]
        observations = [
            (sample, math.degrees(self.get_yaw(magnetic, pitch, roll)) % 360)
            for sample, magnetic in self.take_magnetic_observations()
        ]
        return self._heading_yaw.update(
            intervals=self.take_gyro_intervals(),
            observations=observations,
            now_s=time.monotonic(),
            fixed_pitch=pitch,
            fixed_roll=roll,
            calibration_epoch=self.magnetic_heading_calibration_epoch,
            transform_heading=transform_heading,
            model_ready=model_ready,
        )

    def reanchor_heading_motion(self):
        return self._heading_yaw.reanchor()

    def read_gyro(self, return_raw=False):
        if self._imu_dt_us is None:
            return super().read_gyro(return_raw=return_raw)
        if not self.motion_sensor["GYRO"]:
            return
        # The nRF already subtracts bias before integrating; preserve its interval area.
        self.values["gyro_raw"] = self.change_axis(
            np.array(self.sensor["i2c_imu"].gyro)
        )
        if return_raw:
            return
        self.values["gyro_mod"] = self.values["gyro_raw"].copy()
        acc_angle = self._get_tilt_difference()
        self.values["gyro"] = (
            0.9
            * (
                self.values["gyro"]
                + self.values["gyro_mod"] * self._imu_dt_us / 1_000_000
            )
            + 0.1 * acc_angle
        )

    def update_pitch_roll_calibration_state(self, show_popup=True):
        super().update_pitch_roll_calibration_state(show_popup=show_popup)
        if self._gyro_calibration_task is not None:
            self._gyro_calibration_task.cancel()
        self._gyro_calibration_ready = False
        if self.do_pitch_roll_calibration:
            if self.supports_gyro_intervals:
                self._gyro_calibration_task = asyncio.create_task(
                    self._calibrate_gyro()
                )
            else:
                # Old firmware retains its existing pitch/roll calibration behavior.
                self._gyro_calibration_ready = True

    async def _calibrate_gyro(self):
        try:
            await self.control_uart.calibrate_gyro()
            self._gyro_calibration_ready = True
            self._previous_imu = None
            self._gyro_intervals.clear()
            # Require fresh mounting observations after the gyro-only calibration gap.
            self.moving[:] = 1
            self.acc_raw_hist[:] = np.nan
            app_logger.info("[GYRO] nRF stationary calibration completed")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.do_pitch_roll_calibration = False
            app_logger.warning("[GYRO] nRF calibration failed: %s", exc)
        finally:
            if self._gyro_calibration_task is asyncio.current_task():
                self._gyro_calibration_task = None

    def calibrate_pitch_roll_if_stopped(self):
        if not self._gyro_calibration_ready:
            return
        super().calibrate_pitch_roll_if_stopped()

    def quit(self):
        if self._gyro_calibration_task is not None:
            self._gyro_calibration_task.cancel()
        super().quit()

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
