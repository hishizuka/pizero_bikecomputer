from .sensor import Sensor


class SensorKeyboard(Sensor):
    """Placeholder for board keyboard input until key mappings are defined."""

    def sensor_init(self):
        self.device_path = self.config.board_preset.keyboard_device

    @property
    def has_buttons(self):
        return False

    def start_coroutine(self):
        pass

    async def quit(self):
        pass
