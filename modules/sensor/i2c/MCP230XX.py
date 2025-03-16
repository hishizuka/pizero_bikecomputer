import time
import asyncio


try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
    import pigpio
except:
    # directly run this program
    import i2c
    import pigpio


IODIR   = 0x00
IOPOL   = 0x01
GPINTEN = 0x02
DEFVAL  = 0x03
INTCON  = 0x04
GPPU    = 0x06
INTF    = 0x07
INTCAP  = 0x08


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

    blt = {} #bit lookup table with intf value

    button_config = None
    quit_status = False

    int_pin = None

    def __init__(self, button_config, int_pin=None):
        self.button_config = button_config
        self.int_pin = int_pin
        super().__init__(reset=False)
 
    def init_sensor(self):
        self.bus.write_byte_data(self.SENSOR_ADDRESS, IODIR, 0b11111111)
        time.sleep(0.01)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, IOPOL, 0)
        time.sleep(0.01)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, GPPU, 0b11111111)
        time.sleep(0.01)

        if self.int_pin is None:
            self.init_sensor_noint()
        else:
            self.init_sensor_int()

    def init_sensor_noint(self):
        self.states = 0b11111111

        self.handler = []
        for i in range(self.CHANNELS):
            h = {}
            h["t_pressed"] = 0
            h["hold_fired"] = False
            self.handler.append(h)

        if __name__ == "__main__":  # directly run this program
            asyncio.run(self._run_noint())
        else:
            asyncio.create_task(self._run_noint())

    def init_sensor_int(self):
        self.pi = pigpio.pi()

        self.states = [True] * self.CHANNELS
        for i in range(self.CHANNELS):
            self.blt[2**i] = i
        self.pressed = None
        self.watch_btn = [False] * self.CHANNELS
        self.watch_time = [None] * self.CHANNELS

        self.bus.write_byte_data(self.SENSOR_ADDRESS, GPINTEN, 0b11111111)
        time.sleep(0.01)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, INTCON, 0b00000000)
        time.sleep(0.01)
        _ = self.bus.read_byte_data(self.SENSOR_ADDRESS, self.VALUE_ADDRESS)
        _ = self.bus.read_byte_data(self.SENSOR_ADDRESS, INTCAP)

        self.pi.set_mode(self.int_pin, pigpio.INPUT)
        cb = self.pi.callback(self.int_pin, pigpio.FALLING_EDGE, self.interrupt_callback)

        if __name__ == "__main__":  # directly run this program
            asyncio.run(self._run_int())
        else:
            asyncio.create_task(self._run_int())

    def quit(self):
        self.quit_status = True

    async def _run_noint(self):
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
                    self.press_button(f"GP{i}", 0) # release
                    continue

                if curr == 0:
                    if (
                        not h["hold_fired"]
                        and (time.time() - h["t_pressed"]) > self.button_config.G_BUTTON_LONG_PRESS
                    ):
                        self.press_button(f"GP{i}", 1) # hold
                        h["hold_fired"] = True

            _last_states = _states
            await asyncio.sleep(sleep_time)

    def press_button(self, button, index):
        self.button_config.press_button("IOExpander", button, index)

    async def _run_int(self):
        self.loop = asyncio.get_running_loop()
        while not self.quit_status:
            await asyncio.sleep(60)

    def interrupt_callback(self, gpio, level, tick):
        intf = self.bus.read_byte_data(self.SENSOR_ADDRESS, INTF)
        intcap = self.bus.read_byte_data(self.SENSOR_ADDRESS, INTCAP)        
        if intf == 0:
            return

        b = self.blt[intf]
        state = bool((intcap >> b) & 0b00000001)

        asyncio.run_coroutine_threadsafe(self.buton_loop(b, state), self.loop)

    async def buton_loop(self, b, state):
        if self.states[b] and not state:
            self.watch_time[b] = time.time()
        elif not self.states[b] and state:
            if self.watch_time[b] is not None:
                self.press_button(f"GP{b}", 0)
                self.watch_time[b] = None
            self.states[b] = state
            return
        
        self.states[b] = state

        await asyncio.sleep(self.button_config.G_BUTTON_LONG_PRESS)
        
        if (
            not self.states[b] and
            not state and
            time.time() - self.watch_time[b] >= self.button_config.G_BUTTON_LONG_PRESS
        ):
            self.watch_time[b] = None
            self.press_button(f"GP{b}", 1)


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
    #mcp = MCP23008(b)
    mcp = MCP23008(b, int_pin=23)

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            mcp.quit()
            break

