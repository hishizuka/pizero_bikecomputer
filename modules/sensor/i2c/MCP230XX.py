import time
import asyncio

try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
except:
    # directly run this program
    import i2c


IODIR = 0x00
IOPOL = 0x01
GPPU  = 0x06


class ButtonIOExpander(i2c.i2c):
    # address
    SENSOR_ADDRESS = 0x20  #for MCP23008

    # for reset
    #RESET_ADDRESS = None
    #RESET_VALUE = None

    # for reading value
    VALUE_ADDRESS = 0x09
    #VALUE_BYTES = None

    # for test
    #TEST_ADDRESS = None  # chip_id
    #TEST_VALUE = (None,)

    # The amount of available channels (8 for MCP23008)
    CHANNELS = 8

    # Button reads per second.
    FPS = 20

    button_config = None
    quit_status = False

    def __init__(self, button_config):
        self.button_config = button_config
        super().__init__(reset=False)
 
    def init_sensor(self):
        self.states = 0b00011111

        self.bus.write_byte_data(self.SENSOR_ADDRESS, IODIR, 0b11111111)
        time.sleep(0.01)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, IOPOL, 0)
        time.sleep(0.01)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, GPPU, 0b11111111)
        time.sleep(0.01)

        self.handler = []
        for i in range(self.CHANNELS):
            h = {}
            h["t_pressed"] = 0
            h["hold_fired"] = False
            self.handler.append(h)

        if __name__ == "__main__":  # directly run this program
            asyncio.run(self._run())
        else:
            asyncio.create_task(self._run())

    def quit(self):
        self.quit_status = True

    async def _run(self):
        sleep_time = 1.0 / self.FPS
        _last_states = 0b11111111

        while not self.quit_status:
            try:
                _states = self.bus.read_byte_data(self.SENSOR_ADDRESS, self.VALUE_ADDRESS)
            except:
                await asyncio.sleep(sleep_time)
                continue

            for i in range(self.CHANNELS):
                last = (_last_states >> i) & 1
                curr = (_states >> i) & 1
                h = self.handler[i]

                if last > curr:
                    h["t_pressed"] = time.time()
                    h["hold_fired"] = False
                    continue

                if last < curr and not h["hold_fired"]:
                    self.press_button(f"GP{i}", 0) 
                    continue

                if curr == 0:
                    if (
                        not h["hold_fired"]
                        and (time.time() - h["t_pressed"]) > self.button_config.G_BUTTON_LONG_PRESS
                    ):
                        self.press_button(f"GP{i}", 1)
                        h["hold_fired"] = True

            _last_states = _states
            await asyncio.sleep(sleep_time)

    def press_button(self, button, index):
        self.button_config.press_button("IOExpander", button, index)


class MCP23008(ButtonIOExpander):
    # address
    SENSOR_ADDRESS = 0x20


class MCP23009(MCP23008):
    # address
    SENSOR_ADDRESS = 0x27


if __name__ == "__main__":
    class button_config:
        G_BUTTON_LONG_PRESS = 1
        def press_button(self, key, button, index):
            print(f"{key}, {button}, {index}")

    b = button_config()
    mcp = MCP23008(b)

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            mcp.quit()
            break

