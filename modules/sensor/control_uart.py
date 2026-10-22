import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass

import serial

from modules.app_logger import app_logger

SENSOR_FIELDS = {
    "bmi270": ("ax_g", "ay_g", "az_g", "gx_rads", "gy_rads", "gz_rads"),
    "bmm150": ("mx_ut", "my_ut", "mz_ut"),
    "bmp580": ("pressure_hpa", "temperature_c"),
    "ltr308als": ("lux", "raw"),
}
G_SENSOR_QUEUE_SIZE = 64


@dataclass(frozen=True)
class SensorSample:
    sensor: str
    seq: int
    ts_ms: int
    values: dict[str, float]
    received_at: float
    epoch: int
    proto: str = "sensors/1"
    dt_us: int | None = None


def parse_control_line(line):
    parts = line.split()
    if not parts or parts[0] not in {"HELLO", "BOOT", "STATUS", "OK", "ERR", "SENSOR"}:
        return None
    fields = {
        key: value
        for key, value in (part.split("=", 1) for part in parts[1:] if "=" in part)
    }
    fields["type"] = parts[0]
    return fields


def parse_sensor_sample(fields, received_at, epoch):
    proto = fields.get("proto")
    if fields["type"] != "SENSOR" or proto not in {"sensors/1", "sensors/2"}:
        return None
    name = fields.get("sensor")
    if name not in SENSOR_FIELDS:
        return None
    if proto == "sensors/2" and name != "bmi270":
        return None
    try:
        seq = int(fields["seq"])
        ts_ms = int(fields["ts_ms"])
        values = {key: float(fields[key]) for key in SENSOR_FIELDS[name]}
        dt_us = int(fields["dt_us"]) if proto == "sensors/2" else None
    except (KeyError, ValueError, OverflowError):
        return None
    if (
        not 0 <= seq < 2**32
        or ts_ms < 0
        or not all(map(math.isfinite, values.values()))
        or (dt_us is not None and not 0 < dt_us <= min(2**32 - 1, (ts_ms + 1) * 1000))
    ):
        return None
    return SensorSample(name, seq, ts_ms, values, received_at, epoch, proto, dt_us)


class ControlUART:
    def __init__(
        self,
        device="/dev/serial0",
        period_ms=1000,
        expected_profile=None,
        rtscts=False,
        nrf_reset_gpiochip=None,
        nrf_reset_gpio=None,
        reset_allowed=None,
        on_configured=None,
    ):
        self.device = device
        self.period_ms = period_ms
        self.expected_profile = expected_profile
        self.rtscts = rtscts
        self.nrf_reset_gpiochip = nrf_reset_gpiochip
        self.nrf_reset_gpio = nrf_reset_gpio
        self.reset_allowed = reset_allowed
        self.on_configured = on_configured
        self._ever_configured = False
        self._response_failures = 0
        self._reset_attempts = 0
        self.port = None
        self.task = None
        self.quit_status = False
        self.connected = False
        self.epoch = 0
        self.samples = {}
        self.sensor_status = {}
        self.system_status = {}
        self._hello_event = asyncio.Event()
        self._pending = None
        self._request_lock = asyncio.Lock()
        self._sample_queues = {
            name: deque(maxlen=G_SENSOR_QUEUE_SIZE) for name in ("bmi270", "bmm150")
        }
        self.queue_drops = {name: 0 for name in self._sample_queues}
        self.gyro_status = {}
        self.sensor_protocol = None
        self._gyro_calibration_event = asyncio.Event()
        self._gyro_calibration_started = False

    def start_coroutine(self):
        self.task = asyncio.create_task(self.run())

    def latest(self, sensor, max_age=2.0):
        sample = self.samples.get(sensor)
        if sample is None or not self.connected:
            return None
        if time.monotonic() - sample.received_at > max_age:
            return None
        return sample

    def _invalidate(self):
        self.epoch += 1
        self.samples.clear()
        self.sensor_status.clear()
        self.system_status.clear()
        for samples in self._sample_queues.values():
            samples.clear()
        self.gyro_status.clear()
        self.sensor_protocol = None
        self._gyro_calibration_event.set()

    def drain(self, sensor):
        samples = self._sample_queues[sensor]
        result = list(samples) if self.connected else []
        samples.clear()
        return result

    def _handle_line(self, line):
        fields = parse_control_line(line)
        if fields is None:
            return
        kind = fields["type"]
        if kind == "HELLO":
            self._invalidate()
            self._hello_event.set()
            if self._pending is not None:
                self._pending[3].set_exception(ConnectionError("controller restarted"))
                self._pending = None
            return
        if kind == "SENSOR":
            self._handle_sample(fields)
            return
        if kind == "STATUS":
            self._handle_status(fields)
        self._match_response(fields, line)

    def _handle_sample(self, fields):
        sample = parse_sensor_sample(fields, time.monotonic(), self.epoch)
        if sample is None:
            return
        previous = self.samples.get(sample.sensor)
        if previous is not None:
            step = (sample.seq - previous.seq) % 2**32
            if step == 0 or step >= 2**31 or sample.ts_ms < previous.ts_ms:
                return
        self.samples[sample.sensor] = sample
        if sample.sensor in self._sample_queues:
            samples = self._sample_queues[sample.sensor]
            if len(samples) == samples.maxlen:
                self.queue_drops[sample.sensor] += 1
            samples.append(sample)

    @staticmethod
    def _warn_increased_counters(label, fields, previous, counters):
        for counter in counters:
            try:
                increased = int(fields.get(counter, 0)) > int(previous.get(counter, 0))
            except (TypeError, ValueError):
                continue
            if increased:
                app_logger.warning(
                    "control UART %s %s=%s", label, counter, fields[counter]
                )

    def _handle_status(self, fields):
        if fields.get("svc") == "imu":
            app_logger.debug("control UART imu status: %s", fields)
        elif fields.get("svc") == "gyro":
            self.gyro_status = fields
            if fields.get("state") == "running":
                self._gyro_calibration_started = True
            if self._gyro_calibration_started and fields.get("state") in {
                "done",
                "failed",
            }:
                self._gyro_calibration_event.set()
        elif fields.get("svc") == "sensors":
            self.sensor_protocol = fields.get("proto")
        elif fields.get("svc") == "sensor" and "sensor" in fields:
            name = fields["sensor"]
            self._warn_increased_counters(
                name,
                fields,
                self.sensor_status.get(name, {}),
                ("errors", "tx_drop"),
            )
            self.sensor_status[name] = fields
        elif fields.get("svc") == "sys":
            self._warn_increased_counters(
                "sys", fields, self.system_status, ("ctrl_rx_drop", "ctrl_tx_drop")
            )
            self.system_status = fields

    def _match_response(self, fields, line):
        if self._pending is None:
            return
        kind = fields["type"]
        expected_kind, expected_svc, expected_op, future = self._pending
        if kind == "ERR" and fields.get("svc") == expected_svc:
            self._pending = None
            future.set_exception(RuntimeError(line))
        elif (
            kind == expected_kind
            and fields.get("svc") == expected_svc
            and (expected_op is None or fields.get("op") == expected_op)
        ):
            self._pending = None
            future.set_result(fields)

    async def _read_loop(self):
        buffer = bytearray()
        while not self.quit_status:
            chunk = await asyncio.to_thread(self.port.read, 256)
            if not chunk:
                continue
            buffer.extend(chunk)
            if len(buffer) > 1024:
                buffer.clear()
                continue
            while b"\n" in buffer:
                raw, _, remainder = buffer.partition(b"\n")
                buffer = bytearray(remainder)
                if len(raw) <= 512:
                    self._handle_line(
                        raw.rstrip(b"\r").decode("ascii", errors="replace")
                    )

    async def _request(self, command, kind, svc, op=None):
        async with self._request_lock:
            future = asyncio.get_running_loop().create_future()
            self._pending = (kind, svc, op, future)
            try:
                await asyncio.to_thread(
                    self.port.write, (command + "\n").encode("ascii")
                )
                return await asyncio.wait_for(future, 3.0)
            finally:
                self._pending = None

    async def calibrate_gyro(self):
        self._gyro_calibration_event.clear()
        self._gyro_calibration_started = False
        self.gyro_status.clear()
        epoch = self.epoch
        try:
            await self._request("sensors gyro calibrate", "OK", "gyro", "calibrate")
            await asyncio.wait_for(self._gyro_calibration_event.wait(), 35.0)
            if self.epoch != epoch or self.gyro_status.get("state") != "done":
                raise RuntimeError("gyro calibration did not complete")
        except (asyncio.CancelledError, TimeoutError):
            if self.connected and self.epoch == epoch:
                try:
                    await self._request("sensors gyro cancel", "OK", "gyro", "cancel")
                except (TimeoutError, ConnectionError, RuntimeError):
                    pass
            raise

    async def _configure(self):
        self._hello_event.clear()
        await self._request("ping", "OK", "ctrl", "ping")
        status = await self._request("status", "STATUS", "sys")
        if self.expected_profile and status.get("profile") != self.expected_profile:
            raise RuntimeError(
                f"unexpected controller profile: {status.get('profile')}"
            )
        expected_flow = "rtscts" if self.rtscts else "none"
        if status.get("ctrl_flow") != expected_flow:
            raise RuntimeError(f"unexpected controller flow: {status.get('ctrl_flow')}")
        await self._request("sensors status", "STATUS", "sensors")
        await self._request(
            f"sensors period {self.period_ms}", "OK", "sensors", "period"
        )
        await self._request("sensors on", "OK", "sensors", "on")
        reconfigured = self._ever_configured
        self._ever_configured = True
        self._response_failures = 0
        app_logger.info("control UART configured (reconfigured=%s)", reconfigured)
        if self.on_configured is not None:
            self.on_configured(reconfigured)

    def _reset_nrf52840(self):
        import gpiod
        from gpiod.line import Direction, Value

        request = gpiod.request_lines(
            self.nrf_reset_gpiochip,
            consumer="pizero_bikecomputer_nrf52840_reset",
            config={
                self.nrf_reset_gpio: gpiod.LineSettings(
                    direction=Direction.OUTPUT,
                    output_value=Value.INACTIVE,
                )
            },
        )
        try:
            request.set_value(self.nrf_reset_gpio, Value.ACTIVE)
            time.sleep(0.1)
        finally:
            request.set_value(self.nrf_reset_gpio, Value.INACTIVE)
            request.release()

    async def _maybe_reset(self):
        if (
            self._response_failures < 3
            or not self._ever_configured
            or self._reset_attempts >= 1
            or self.nrf_reset_gpio is None
            or self.nrf_reset_gpiochip is None
            or self.reset_allowed is None
            or not self.reset_allowed()
        ):
            return
        self._reset_attempts += 1
        try:
            await asyncio.to_thread(self._reset_nrf52840)
            app_logger.warning("nRF52840 reset after repeated control UART timeouts")
        except Exception as exc:
            app_logger.error("nRF52840 reset failed: %s", exc)

    async def _run_session(self):
        self.port = await asyncio.to_thread(
            serial.Serial,
            self.device,
            115200,
            timeout=0.2,
            write_timeout=0.5,
            rtscts=self.rtscts,
            xonxoff=False,
            exclusive=True,
        )
        self.connected = True
        self._invalidate()
        reader = asyncio.create_task(self._read_loop())
        try:
            while not self.quit_status and not reader.done():
                await self._configure()
                while not self.quit_status and not reader.done():
                    try:
                        await asyncio.wait_for(self._hello_event.wait(), 10.0)
                        break
                    except TimeoutError:
                        await self._request("ping", "OK", "ctrl", "ping")
                        await self._request("status", "STATUS", "sys")
                        await self._request("sensors status", "STATUS", "sensors")
            if reader.done():
                await reader
        finally:
            self.connected = False
            self._invalidate()
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            self.port.close()
            self.port = None

    async def run(self):
        while not self.quit_status:
            try:
                await self._run_session()
            except asyncio.CancelledError:
                raise
            except TimeoutError as exc:
                self._response_failures += 1
                app_logger.warning("control UART response timeout: %s", exc)
                await self._maybe_reset()
            except Exception as exc:
                app_logger.warning("control UART unavailable: %s", exc)
            if not self.quit_status:
                await asyncio.sleep(2.0)

    async def quit(self):
        self.quit_status = True
        if self.port is not None and self.connected:
            try:
                await asyncio.to_thread(self.port.write, b"sensors off\n")
            except Exception:
                pass
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
