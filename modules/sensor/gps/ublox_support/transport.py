import errno
import time

import serial
from pyubx2 import POLL_LAYER_RAM, UBXMessage

UART_BAUDRATE = 9600
UART_AUTO_DETECT_DEVICES = ("/dev/serial0", "/dev/ttyS0", "/dev/ttyAMA0")
UART_DETECT_TIMEOUT = 2.0
I2C_BUS = 1
I2C_ADDRESS = 0x42
READ_TIMEOUT = 0.2


def is_interrupted_system_call(exc):
    return (
        isinstance(exc, InterruptedError)
        or getattr(exc, "errno", None) == errno.EINTR
        or (exc.args and exc.args[0] == errno.EINTR)
    )


def retry_interrupted_system_call(func, *args):
    while True:
        try:
            return func(*args)
        except Exception as exc:
            if is_interrupted_system_call(exc):
                continue
            raise


def has_valid_ubx_frame(buffer):
    start = 0
    while True:
        index = buffer.find(b"\xb5\x62", start)
        if index < 0:
            return False
        if len(buffer) < index + 8:
            return False

        payload_length = buffer[index + 4] | (buffer[index + 5] << 8)
        frame_length = payload_length + 8
        frame_end = index + frame_length
        if len(buffer) < frame_end:
            return False

        ck_a = 0
        ck_b = 0
        for value in buffer[index + 2 : frame_end - 2]:
            ck_a = (ck_a + value) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        if ck_a == buffer[frame_end - 2] and ck_b == buffer[frame_end - 1]:
            return True

        start = index + 2


def detect_uart_ublox_device():
    poll_cfg_rate_nav = UBXMessage.config_poll(
        POLL_LAYER_RAM,
        0,
        ["CFG_RATE_NAV"],
    ).serialize()
    for device in UART_AUTO_DETECT_DEVICES:
        try:
            with serial.Serial(
                device,
                UART_BAUDRATE,
                timeout=READ_TIMEOUT,
                write_timeout=0.5,
            ) as gps:
                gps.write(poll_cfg_rate_nav)
                buffer = bytearray()
                end_time = time.monotonic() + UART_DETECT_TIMEOUT
                while time.monotonic() < end_time:
                    buffer.extend(gps.read(256))
                    if has_valid_ubx_frame(buffer):
                        return device
        except Exception:
            continue
    return None


def detect_i2c_ublox():
    try:
        gps = I2CStream(I2C_BUS, I2C_ADDRESS, 0.1)
        gps.close()
        return True
    except Exception:
        return False


def detect_sensor_ublox():
    uart_device = detect_uart_ublox_device()
    if uart_device:
        return True, uart_device
    return detect_i2c_ublox(), None


class I2CStream:
    def __init__(self, bus, address, timeout):
        try:
            import smbus2
        except ImportError as exc:
            raise RuntimeError("smbus2 is required for u-blox I2C") from exc

        self.bus_number = bus
        self.address = address
        self.timeout = timeout
        self.buffer = bytearray()
        self.bus = smbus2.SMBus(bus)
        self.available()

    @property
    def name(self):
        return f"i2c:{self.bus_number}:0x{self.address:02x}"

    def available(self):
        data = self.bus.read_i2c_block_data(self.address, 0xFD, 2)
        return (data[0] << 8) | data[1]

    def read(self, size):
        end_time = time.monotonic() + self.timeout
        while len(self.buffer) < size:
            available = self.available()
            if not available:
                if time.monotonic() >= end_time:
                    break
                time.sleep(0.01)
                continue

            while available > 0 and len(self.buffer) < size:
                length = min(available, size - len(self.buffer), 32)
                self.buffer.extend(
                    self.bus.read_i2c_block_data(self.address, 0xFF, length)
                )
                available -= length

        out = bytes(self.buffer[:size])
        del self.buffer[:size]
        return out

    def write(self, data):
        data = bytes(data)
        for i in range(0, len(data), 32):
            self.bus.write_i2c_block_data(self.address, 0xFF, list(data[i : i + 32]))

    def close(self):
        if self.bus is not None:
            self.bus.close()
            self.bus = None
