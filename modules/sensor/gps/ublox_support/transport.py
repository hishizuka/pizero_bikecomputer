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
I2C_READLINE_LIMIT = 512
I2C_REMOTE_IO_ERRNO = getattr(errno, "EREMOTEIO", 121)
I2C_TRANSFER_ATTEMPTS = 4
I2C_TRANSFER_RETRY_DELAY = 0.02


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


def is_i2c_remote_io_error(exc):
    return getattr(exc, "errno", None) == I2C_REMOTE_IO_ERRNO or (
        exc.args and exc.args[0] == I2C_REMOTE_IO_ERRNO
    )


def retry_i2c_remote_io(func, *args):
    for attempt in range(I2C_TRANSFER_ATTEMPTS):
        try:
            return func(*args)
        except OSError as exc:
            if not is_i2c_remote_io_error(exc) or attempt + 1 >= I2C_TRANSFER_ATTEMPTS:
                raise
            time.sleep(I2C_TRANSFER_RETRY_DELAY * (attempt + 1))


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

    def _read_block(self, register, length):
        return retry_i2c_remote_io(
            self.bus.read_i2c_block_data,
            self.address,
            register,
            length,
        )

    def _write_block(self, register, data):
        retry_i2c_remote_io(
            self.bus.write_i2c_block_data,
            self.address,
            register,
            data,
        )

    def available(self):
        data = self._read_block(0xFD, 2)
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
                self.buffer.extend(self._read_block(0xFF, length))
                available -= length

        out = bytes(self.buffer[:size])
        del self.buffer[:size]
        return out

    def readline(self, size=-1):
        limit = I2C_READLINE_LIMIT if size is None or size < 0 else size
        if limit <= 0:
            return b""

        end_time = time.monotonic() + self.timeout
        while b"\n" not in self.buffer and len(self.buffer) < limit:
            available = self.available()
            if not available:
                if time.monotonic() >= end_time:
                    break
                time.sleep(0.01)
                continue

            length = min(available, limit - len(self.buffer), 32)
            if length <= 0:
                break
            self.buffer.extend(self._read_block(0xFF, length))

        newline_index = self.buffer.find(b"\n")
        if newline_index >= 0:
            out_size = min(newline_index + 1, limit)
        else:
            out_size = min(len(self.buffer), limit)

        out = bytes(self.buffer[:out_size])
        del self.buffer[:out_size]
        return out

    def write(self, data):
        data = bytes(data)
        for i in range(0, len(data), 32):
            self._write_block(0xFF, list(data[i : i + 32]))

    def close(self):
        if self.bus is not None:
            self.bus.close()
            self.bus = None
