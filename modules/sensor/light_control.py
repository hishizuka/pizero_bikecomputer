from datetime import datetime
from enum import StrEnum


class LightState(StrEnum):
    OFF = "OFF"
    ON = "ON"
    AUTO = "AUTO"


class LightControlState:
    """Resolve protocol-independent light requests into one desired mode."""

    def __init__(
        self,
        modes,
        default_on_mode,
        *,
        auto_min_duration=5.0,
    ):
        self.modes = frozenset(modes)
        if "OFF" not in self.modes or default_on_mode not in self.modes:
            raise ValueError("Light modes must contain OFF and the default mode")
        self.default_on_mode = default_on_mode
        self.auto_min_duration = auto_min_duration
        self.reset(False)

    def reset(self, auto_enabled):
        self.state = LightState.AUTO if auto_enabled else LightState.OFF
        self.desired_mode = None
        self.auto_on_timestamp = None
        self.auto_requested_on = False
        self.manual_on_mode = self.default_on_mode
        self.auto_on_mode = self.default_on_mode

    @property
    def button_state(self):
        return self.state == LightState.ON

    @property
    def auto_state(self):
        return self.state == LightState.AUTO

    def request_mode(self, mode, *, auto, auto_enabled, now=None):
        timestamp = datetime.now() if now is None else now
        if auto:
            self.auto_requested_on = mode != "OFF"
            if self.auto_requested_on:
                self.auto_on_timestamp = timestamp
                if mode in self.modes:
                    self.auto_on_mode = mode
            return self._update_desired_mode(auto_enabled, timestamp)

        if mode == "ON_OFF_FLASH_LOW":
            if self.state == LightState.OFF:
                self.manual_on_mode = self.default_on_mode
                state = LightState.ON
            elif self.state == LightState.ON and auto_enabled:
                state = LightState.AUTO
            else:
                state = LightState.OFF
            return self.set_state(state, auto_enabled=auto_enabled, now=timestamp)

        if mode == "OFF":
            return self.set_state(
                LightState.OFF,
                auto_enabled=auto_enabled,
                now=timestamp,
            )

        self.manual_on_mode = mode if mode in self.modes else self.default_on_mode
        return self.set_state(
            LightState.ON,
            auto_enabled=auto_enabled,
            now=timestamp,
        )

    def set_state(self, state, *, auto_enabled, now=None):
        try:
            state = LightState(state)
        except (TypeError, ValueError):
            return False
        if self.state == state:
            return False
        self.state = state
        timestamp = datetime.now() if now is None else now
        return self._update_desired_mode(auto_enabled, timestamp)

    def _update_desired_mode(self, auto_enabled, now):
        desired_mode = "OFF"
        if self.state == LightState.ON:
            desired_mode = self.manual_on_mode
        elif self.state == LightState.AUTO and auto_enabled:
            recently_on = (
                self.auto_on_timestamp is not None
                and (now - self.auto_on_timestamp).total_seconds()
                < self.auto_min_duration
            )
            if self.auto_requested_on or recently_on:
                desired_mode = self.auto_on_mode
        if desired_mode not in self.modes:
            desired_mode = "OFF"
        changed = desired_mode != self.desired_mode
        self.desired_mode = desired_mode
        return changed
