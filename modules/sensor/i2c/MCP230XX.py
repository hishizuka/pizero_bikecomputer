import time
import asyncio
from datetime import timedelta


try:
    import gpiod
    from gpiod.line import Direction, Edge
    try:
        # run from top directory (pizero_bikecomputer)
        from . import i2c
    except:
        # directly run this program
        import i2c
except:
    pass


IODIR   = 0x00
IOPOL   = 0x01
GPINTEN = 0x02
DEFVAL  = 0x03
INTCON  = 0x04
GPPU    = 0x06
INTF    = 0x07
INTCAP  = 0x08


class ButtonIOExpander(i2c.i2c):
    _GPIOCHIP_PATH = "/dev/gpiochip4"
    _GPIO_CONSUMER = "pizero_bikecomputer"

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
    FPS = 30

    blt = {} #bit lookup table with intf value

    button_config = None
    quit_status = False

    int_pin = None

    def __init__(self, button_config, int_pin=None):
        self.button_config = button_config
        self.int_pin = int_pin
        self._line_request = None
        self._event_task = None
        self.loop = None
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

        # Requires a running event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                "ButtonIOExpander requires a running asyncio event loop."
            ) from e
        asyncio.create_task(self._run_noint())

    def init_sensor_int(self):
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

        self._init_interrupt_gpio()

        # Requires a running event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                "ButtonIOExpander requires a running asyncio event loop."
            ) from e
        asyncio.create_task(self._run_int())

    def quit(self):
        self.quit_status = True
        if self._line_request is not None:
            try:
                self._line_request.release()
            except Exception:
                pass
            self._line_request = None

    def _init_interrupt_gpio(self):
        try:
            import gpiod
            from gpiod.line import Direction, Edge
        except ImportError as e:
            raise RuntimeError(
                "gpiod (libgpiod v2 Python bindings) is required for MCP230xx interrupt mode."
            ) from e

        pins = [self.int_pin]
        settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            edge_detection=Edge.FALLING,
        )
        config = {pin: settings for pin in pins}

        try:
            self._line_request = gpiod.request_lines(
                self._GPIOCHIP_PATH,
                consumer=self._GPIO_CONSUMER,
                config=config,
            )
        except OSError as e:
            raise RuntimeError(
                f"Failed to request MCP230xx interrupt GPIO via gpiod. chip={self._GPIOCHIP_PATH}, pins={pins}."
            ) from e

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
        if self._line_request is not None:
            self._event_task = asyncio.create_task(
                asyncio.to_thread(self._interrupt_event_loop)
            )
        while not self.quit_status:
            await asyncio.sleep(2)
        if self._event_task is not None:
            try:
                await self._event_task
            except Exception:
                pass
            self._event_task = None

    def _interrupt_event_loop(self):
        while not self.quit_status:
            if self._line_request is None:
                time.sleep(0.1)
                continue

            try:
                has_event = self._line_request.wait_edge_events(timedelta(seconds=1))
            except TypeError:
                # Some bindings may accept float seconds or no timeout argument.
                try:
                    has_event = self._line_request.wait_edge_events(1.0)
                except TypeError:
                    has_event = self._line_request.wait_edge_events()
            except Exception:
                time.sleep(0.1)
                continue

            if not has_event:
                continue

            try:
                events = self._line_request.read_edge_events()
            except TypeError:
                try:
                    events = self._line_request.read_edge_events(1)
                except Exception:
                    events = None
            except Exception:
                events = None

            event_list = None
            if events is not None:
                try:
                    event_list = list(events)
                except TypeError:
                    event_list = None

            if not event_list:
                # If edge events can't be read, still handle the interrupt once.
                self.interrupt_callback(self.int_pin, 0, 0)
                continue

            for _ in event_list:
                self.interrupt_callback(self.int_pin, 0, 0)

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
    import signal

    class button_config:
        G_BUTTON_LONG_PRESS = 1
        def press_button(self, key, button, index):
            print(f"{key}, {button}, {index}")

    async def _main():
        b = button_config()

        # Set int_pin (BCM) to enable interrupt mode.
        # int_pin = 23
        int_pin = None

        mcp = None
        try:
            mcp = MCP23008(b) if int_pin is None else MCP23008(b, int_pin=int_pin)

            stop_event = asyncio.Event()
            loop = asyncio.get_running_loop()

            def _request_shutdown():
                stop_event.set()

            # Graceful shutdown on SIGINT/SIGTERM.
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, _request_shutdown)
                except NotImplementedError:
                    # Some platforms (e.g. Windows) don't support signal handlers in asyncio.
                    pass

            await stop_event.wait()
        finally:
            # Ensure resources are released on CTRL+C / SIGINT.
            if mcp is not None:
                mcp.quit()
                try:
                    mcp.bus.close()
                except Exception:
                    pass

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        # Fallback when signal handlers are not available.
        pass
