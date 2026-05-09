import time
import asyncio
from datetime import timedelta

from modules.app_logger import app_logger
from .sensor import Sensor


# GPIO Button (gpiod v2)
_SENSOR_GPIOD = False
try:
    import gpiod
    from gpiod.line import Direction, Edge, Bias
    _SENSOR_GPIOD = True
except ImportError:
    pass

if _SENSOR_GPIOD:
    app_logger.info("  GPIO (gpiod)")


class SensorGPIO(Sensor):
    _GPIOCHIP_PATH = "/dev/gpiochip4"
    _GPIO_CONSUMER = "pizero_bikecomputer"

    # Debounce time in milliseconds (matches original RPi.GPIO bouncetime=500)
    _DEBOUNCE_MS = 250

    button_state = {}
    mode = "MAIN"

    quit_status = False
    _line_request = None
    _event_task = None
    _loop = None
    _button_profile = None
    _pin_to_button = {}

    # Button profiles that require internal pull-up resistors.
    _PULLUP_BUTTON_PROFILES = [
        "PiTFT",
        "DFRobot_RPi_Display",
        "Pirate_Audio_old",
        "Pirate_Audio",
        "Display_HAT_Mini",
        "Custom_GPIO",
    ]
    # Button profiles that use external pull-up (no internal pull-up needed).
    _NO_PULLUP_BUTTON_PROFILES = [
        "Papirus",
    ]

    def sensor_init(self):
        self.button_state = {}
        self.quit_status = False
        self._button_profile = None
        self._pin_to_button = {}

        if not _SENSOR_GPIOD:
            return

        if getattr(self.config.button_config, "use_custom_gpio_buttons", False):
            self._set_custom_gpio_buttons()
        else:
            self._set_display_gpio_buttons()

        if self._button_profile is None:
            return

        button_keys = list(self._pin_to_button.keys())
        if not button_keys:
            return

        # Initialize button state tracking
        for key in button_keys:
            self.button_state[key] = {
                "pressed": False,
                "press_time": None,
                "long_press_fired": False,
                "last_action_time": 0,  # For software debouncing
            }

        use_pullup = self._button_profile in self._PULLUP_BUTTON_PROFILES

        try:
            self._init_gpiod(button_keys, use_pullup)
        except Exception as e:
            app_logger.error(f"Failed to initialize GPIO: {e}")
            self._line_request = None

    def _set_custom_gpio_buttons(self):
        profile = "Custom_GPIO"
        button_def = self.config.button_config.button_def.get(profile, {})
        valid_buttons = button_def.get("MAIN", {})
        button_map = getattr(self.config.button_config, "custom_gpio_buttons", {})

        for button_name, pin in button_map.items():
            if button_name not in valid_buttons:
                app_logger.warning(
                    f"Custom GPIO button '{button_name}' is not defined in {profile}"
                )
                continue
            try:
                gpio_pin = int(pin)
            except (TypeError, ValueError):
                app_logger.warning(
                    f"Custom GPIO button '{button_name}' has invalid pin: {pin!r}"
                )
                continue
            if gpio_pin in self._pin_to_button:
                app_logger.warning(
                    f"Custom GPIO pin {gpio_pin} is already assigned to "
                    f"'{self._pin_to_button[gpio_pin]}'"
                )
                continue
            self._pin_to_button[gpio_pin] = button_name

        if self._pin_to_button:
            self._button_profile = profile

    def _set_display_gpio_buttons(self):
        button_profiles = self._PULLUP_BUTTON_PROFILES + self._NO_PULLUP_BUTTON_PROFILES
        profile = self.config.G_DISPLAY
        if profile not in button_profiles:
            return

        button_def = self.config.button_config.button_def.get(profile, {})
        for button in button_def.get("MAIN", {}):
            try:
                gpio_pin = int(button)
            except (TypeError, ValueError):
                app_logger.warning(
                    f"GPIO button '{button}' in {profile} is not a valid pin"
                )
                continue
            self._pin_to_button[gpio_pin] = button

        if self._pin_to_button:
            self._button_profile = profile

    def _init_gpiod(self, pins, use_pullup):
        bias = Bias.PULL_UP if use_pullup else Bias.AS_IS

        # Hardware debounce via gpiod
        try:
            settings = gpiod.LineSettings(
                direction=Direction.INPUT,
                edge_detection=Edge.FALLING,
                bias=bias,
                debounce_period=timedelta(milliseconds=10),
            )
        except TypeError:
            # Fallback if debounce_period is not supported
            settings = gpiod.LineSettings(
                direction=Direction.INPUT,
                edge_detection=Edge.FALLING,
                bias=bias,
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
                f"Failed to request GPIO lines via gpiod. chip={self._GPIOCHIP_PATH}, pins={pins}."
            ) from e

    def update(self):
        if self._line_request is None:
            return

        # Requires a running event loop
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError as e:
            app_logger.error(f"SensorGPIO requires a running asyncio event loop: {e}")
            return

        self._event_task = asyncio.create_task(self._event_loop())

    async def _event_loop(self):
        """Main event loop for GPIO edge detection."""
        while not self.quit_status:
            if self._line_request is None:
                await asyncio.sleep(0.1)
                continue

            # Wait for edge events in a separate thread to avoid blocking
            try:
                has_event = await asyncio.to_thread(
                    self._wait_for_events, timedelta(seconds=0.5)
                )
            except Exception:
                await asyncio.sleep(0.1)
                continue

            if not has_event:
                # Check for pending long press timeouts
                await self._check_long_press()
                continue

            # Read and process events
            try:
                events = self._line_request.read_edge_events()
                for event in events:
                    await self._handle_edge_event(event)
            except Exception as e:
                app_logger.debug(f"Error reading edge events: {e}")
                continue

            # Also check long press after processing events
            await self._check_long_press()

    def _wait_for_events(self, timeout):
        """Wait for edge events (called in thread)."""
        try:
            return self._line_request.wait_edge_events(timeout)
        except TypeError:
            # Some bindings accept float seconds
            try:
                return self._line_request.wait_edge_events(timeout.total_seconds())
            except TypeError:
                return self._line_request.wait_edge_events()

    def _press_button(self, pin, index):
        button = self._pin_to_button.get(pin)
        if self._button_profile is None or button is None:
            return
        self.config.button_config.press_button(self._button_profile, button, index)

    async def _handle_edge_event(self, event):
        """Handle a single edge event (FALLING only - button press)."""
        pin = event.line_offset
        if pin not in self.button_state:
            return

        state = self.button_state[pin]
        current_time = time.time()

        # Software debounce: ignore events within debounce period
        if (current_time - state["last_action_time"]) < (self._DEBOUNCE_MS / 1000.0):
            return

        # FALLING edge = button pressed
        state["pressed"] = True
        state["press_time"] = current_time
        state["long_press_fired"] = False

        # Start monitoring for release/long press
        asyncio.create_task(self._monitor_button_release(pin))

    async def _monitor_button_release(self, pin):
        """Monitor button state for release or long press detection."""
        state = self.button_state[pin]
        long_press_threshold = self.config.button_config.button_long_press
        poll_interval = 0.01  # 10ms polling

        while not self.quit_status and state["pressed"]:
            # Read current pin value
            try:
                value = self._line_request.get_value(pin)
                # Value.ACTIVE (1) = released (pulled high), Value.INACTIVE (0) = pressed
                is_released = value.value == 1 if hasattr(value, 'value') else bool(value)
            except Exception:
                break

            if is_released:
                # Button released
                if not state["long_press_fired"]:
                    # Short press
                    self._press_button(pin, 0)
                state["pressed"] = False
                state["press_time"] = None
                state["long_press_fired"] = False
                state["last_action_time"] = time.time()
                return

            # Check for long press
            if (
                state["press_time"] is not None
                and not state["long_press_fired"]
            ):
                elapsed = time.time() - state["press_time"]
                if elapsed >= long_press_threshold:
                    # Long press detected
                    state["long_press_fired"] = True
                    self._press_button(pin, 1)
                    state["last_action_time"] = time.time()

            await asyncio.sleep(poll_interval)

    async def _check_long_press(self):
        """Check for buttons held long enough for long press."""
        current_time = time.time()
        long_press_threshold = self.config.button_config.button_long_press

        for pin, state in self.button_state.items():
            if (
                state["pressed"]
                and not state["long_press_fired"]
                and state["press_time"] is not None
            ):
                elapsed = current_time - state["press_time"]
                if elapsed >= long_press_threshold:
                    # Long press detected
                    state["long_press_fired"] = True
                    self._press_button(pin, 1)
                    state["last_action_time"] = current_time

    def quit(self):
        self.quit_status = True
        if self._line_request is not None:
            try:
                self._line_request.release()
            except Exception:
                pass
            self._line_request = None
