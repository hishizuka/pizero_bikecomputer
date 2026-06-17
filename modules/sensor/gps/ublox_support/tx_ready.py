from datetime import timedelta

from modules.app_logger import app_logger

try:
    import gpiod
    from gpiod.line import Bias, Direction, Edge, Value

    _GPIOD_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    gpiod = None
    Bias = None
    Direction = None
    Edge = None
    Value = None
    _GPIOD_IMPORT_ERROR = exc


class TxReadyLine:
    def __init__(self, gpiochip, gpio, active_high=True):
        if _GPIOD_IMPORT_ERROR is not None:
            raise RuntimeError("gpiod is required for u-blox TX_READY") from (
                _GPIOD_IMPORT_ERROR
            )

        self.gpiochip = gpiochip
        self.gpio = gpio
        self.active_high = active_high
        self._request = None
        self.wait_count = 0
        self.active_count = 0
        self.timeout_count = 0

        settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            edge_detection=Edge.BOTH,
            bias=Bias.AS_IS,
        )
        self._request = gpiod.request_lines(
            gpiochip,
            consumer="pizero_bikecomputer-ublox-tx-ready",
            config={gpio: settings},
        )

    @property
    def name(self):
        return f"{self.gpiochip}:{self.gpio}"

    def is_active(self):
        if self._request is None:
            return False
        value = self._request.get_value(self.gpio)
        if self.active_high:
            return value == Value.ACTIVE
        return value == Value.INACTIVE

    def wait_active(self, timeout):
        if self._request is None:
            return False
        if self.is_active():
            self.active_count += 1
            return True

        self.wait_count += 1
        try:
            has_event = self._request.wait_edge_events(
                timedelta(seconds=max(timeout, 0.0))
            )
            if has_event:
                self._request.read_edge_events()
        except OSError as exc:
            app_logger.warning(f"[UBlox] TX_READY wait failed: {exc}")
            self.timeout_count += 1
            return False

        if self.is_active():
            self.active_count += 1
            return True

        self.timeout_count += 1
        return False

    def close(self):
        if self._request is not None:
            self._request.release()
            self._request = None
