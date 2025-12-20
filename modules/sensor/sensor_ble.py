import asyncio
import re
from typing import Optional

from modules.app_logger import app_logger

from .sensor import Sensor

_HAS_ZWIFT_CLICK_V2 = False
try:
    from .ble import zwift_click_v2
    import bleak
    _HAS_ZWIFT_CLICK_V2 = True
except ImportError:
    pass

if _HAS_ZWIFT_CLICK_V2:
    app_logger.info("  BLE (Zwift Click V2)")


class SensorBLE(Sensor):
    stop_event: Optional[asyncio.Event] = None
    task: Optional[asyncio.Task] = None

    def sensor_init(self):
        self.stop_event = asyncio.Event()
        self.task = None

    def connect_zwift_click_v2(self) -> bool:
        """Start Zwift Click V2 listener if it is enabled and available."""
        if not self._is_enabled():
            return False
        # Reset the stop event to allow re-start after a previous stop.
        self.sensor_init()
        self.start_coroutine()
        return True

    def disconnect_zwift_click_v2(self) -> None:
        """Stop Zwift Click V2 listener if running."""
        self.quit()

    def start_coroutine(self):
        if not self._is_enabled():
            return
        if self.task is not None and not self.task.done():
            return
        self.task = asyncio.create_task(self._run())

    def _is_enabled(self) -> bool:
        cfg = getattr(self.config, "G_ZWIFT_CLICK_V2", None)
        if not isinstance(cfg, dict):
            return False
        if not cfg.get("STATUS", False):
            return False
        if not _HAS_ZWIFT_CLICK_V2:
            return False
        return True

    async def _run(self) -> None:
        assert self.stop_event is not None

        cfg = self.config.G_ZWIFT_CLICK_V2
        button_hard = "Zwift_Click_V2"

        def normalize_button_key(button: str) -> str:
            """Normalize zwift_click_v2 button names into Button_Config keys."""
            if not button:
                return ""
            snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", button)
            snake = re.sub(r"[^A-Za-z0-9]+", "_", snake)
            return snake.upper().strip("_")

        def log(msg: str) -> None:
            app_logger.info(f"[ZwiftClickV2] {msg}")

        def on_classified(side: str, button: str, kind: str, duration: float) -> None:
            button_key = normalize_button_key(button)
            if not button_key:
                return

            index = 1 if kind == "long" else 0

            try:
                loop = self.config.loop
            except Exception:
                loop = None
            if loop and loop.is_running():
                loop.call_soon_threadsafe(
                    self.config.button_config.press_button,
                    button_hard,
                    button_key,
                    index,
                )
                return

            self.config.button_config.press_button(button_hard, button_key, index)

        try:
            await zwift_click_v2.listen(
                on_classified=on_classified,
                stop_event=self.stop_event,
                long_press_seconds=float(
                    cfg.get(
                        "LONG_PRESS_SECONDS",
                        zwift_click_v2.DEFAULT_LONG_PRESS_SECONDS,
                    )
                ),
                release_timeout_seconds=float(
                    cfg.get(
                        "RELEASE_TIMEOUT_SECONDS",
                        zwift_click_v2.DEFAULT_RELEASE_TIMEOUT_SECONDS,
                    )
                ),
                repeat_interval_seconds=float(
                    cfg.get(
                        "REPEAT_INTERVAL_SECONDS",
                        zwift_click_v2.DEFAULT_REPEAT_INTERVAL_SECONDS,
                    )
                ),
                scan_timeout_seconds=float(
                    cfg.get(
                        "SCAN_TIMEOUT_SECONDS",
                        zwift_click_v2.DEFAULT_SCAN_TIMEOUT_SECONDS,
                    )
                ),
                scan_forever=True,
                scan_interval_seconds=float(
                    cfg.get(
                        "SCAN_INTERVAL_SECONDS",
                        zwift_click_v2.DEFAULT_SCAN_INTERVAL_SECONDS,
                    )
                ),
                reconnect_delay_seconds=float(
                    cfg.get(
                        "RECONNECT_DELAY_SECONDS",
                        zwift_click_v2.DEFAULT_RECONNECT_DELAY_SECONDS,
                    )
                ),
                prefer_left=True,
                log=log,
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE errors are runtime
            log(f"listener crashed: {exc}")

    def quit(self):
        if self.stop_event is not None:
            self.stop_event.set()
        if self.task is not None:
            self.task.cancel()
