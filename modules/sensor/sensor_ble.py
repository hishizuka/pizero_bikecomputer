import asyncio
import os
import re
import signal
import sys
from typing import Optional

from modules.app_logger import app_logger
from modules.utils.cmd import start_process

from .sensor import Sensor

_HAS_ZWIFT_CLICK_V2 = False
try:
    from .ble import zwift_click_v2
    import bleak
    _HAS_ZWIFT_CLICK_V2 = True
except ImportError:
    pass

if _HAS_ZWIFT_CLICK_V2:
    app_logger.info("  BLE")


class SensorBLE(Sensor):
    _zwift_click_v2_stop_event: Optional[asyncio.Event] = None
    _zwift_click_v2_task: Optional[asyncio.Task] = None

    def __init__(self, config, values):
        super().__init__(config, values)
        self._fake_trainer_proc = None
        self._fake_trainer_check_handle = None
        self._zwift_click_v2_paused_for_fake_trainer = False

    def sensor_init(self):
        self.reset()

    def reset(self):
        self._zwift_click_v2_stop_event = asyncio.Event()
        self._zwift_click_v2_task = None

    def start_coroutine(self):
        self.connect_zwift_click_v2()

    def quit(self):
        self.stop_fake_trainer()
        self.disconnect_zwift_click_v2()

    def connect_zwift_click_v2(self) -> bool:
        """Start Zwift Click V2 listener if it is enabled and available."""
        if not self._is_zwift_click_v2_enabled():
            return False

        # Reset the stop event to allow re-start after a previous stop.
        self.reset()
        if not self._is_zwift_click_v2_enabled():
            return
        self._zwift_click_v2_task = asyncio.create_task(self._run_zwift_click_v2_listener())
        return True

    def disconnect_zwift_click_v2(self) -> None:
        """Stop Zwift Click V2 listener if running."""
        if self._zwift_click_v2_stop_event is not None:
            self._zwift_click_v2_stop_event.set()
        if self._zwift_click_v2_task is not None:
            self._zwift_click_v2_task.cancel()

    def _is_zwift_click_v2_enabled(self) -> bool:
        cfg = getattr(self.config, "G_ZWIFT_CLICK_V2", None)
        if not isinstance(cfg, dict):
            return False
        if not cfg.get("STATUS", False):
            return False
        if not _HAS_ZWIFT_CLICK_V2:
            return False
        return True

    async def _run_zwift_click_v2_listener(self) -> None:
        cfg = self.config.G_ZWIFT_CLICK_V2
        preferred_address = ""
        if isinstance(cfg, dict):
            preferred_address = str(cfg.get("ADDRESS", "")).strip()
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

        def on_connected(side: str, address: str, _name: Optional[str]) -> None:
            if not address:
                return
            if not isinstance(cfg, dict):
                return
            if cfg.get("ADDRESS") == address:
                return
            cfg["ADDRESS"] = address
            setting = getattr(self.config, "setting", None)
            if setting is not None:
                setting.write_config()

        try:
            await zwift_click_v2.listen(
                on_classified=on_classified,
                stop_event=self._zwift_click_v2_stop_event,
                scan_forever=True,
                preferred_address=preferred_address or None,
                on_connected=on_connected,
                log=log,
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE errors are runtime
            log(f"listener crashed: {exc}")

    def is_fake_trainer_running(self) -> bool:
        proc = self._fake_trainer_proc
        return proc is not None and proc.poll() is None

    def is_zwift_click_v2_running(self) -> bool:
        if self._zwift_click_v2_stop_event is None or self._zwift_click_v2_task is None:
            return False
        if self._zwift_click_v2_stop_event.is_set():
            return False
        return not self._zwift_click_v2_task.done()

    def toggle_fake_trainer(self) -> bool:
        if self.is_fake_trainer_running():
            self.stop_fake_trainer()
            if self._zwift_click_v2_paused_for_fake_trainer:
                self._zwift_click_v2_paused_for_fake_trainer = False
                self.connect_zwift_click_v2()
        else:
            started = self.start_fake_trainer()
            if started:
                if self.is_zwift_click_v2_running():
                    # Pause Click V2 while fake trainer is active.
                    self.disconnect_zwift_click_v2()
                    self._zwift_click_v2_paused_for_fake_trainer = True
                else:
                    self._zwift_click_v2_paused_for_fake_trainer = False
        return self.is_fake_trainer_running()

    def start_fake_trainer(self) -> bool:
        if self.is_fake_trainer_running():
            return True
        if getattr(self.config, "ble_uart", None) is None:
            app_logger.warning("Fake trainer start skipped: BLE UART not available")
            return False

        fake_trainer_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "ble",
                "fake_trainer.py",
            )
        )
        if not os.path.isfile(fake_trainer_path):
            app_logger.warning(f"Fake trainer not found: {fake_trainer_path}")
            return False

        try:
            self._fake_trainer_proc = start_process(
                [sys.executable, fake_trainer_path],
                cmd_print=False,
            )
        except Exception as exc:
            app_logger.warning(f"Fake trainer start failed: {exc}")
            self._fake_trainer_proc = None
            return False

        if self._fake_trainer_proc.poll() is not None:
            app_logger.warning("Fake trainer start failed: process exited early")
            self._fake_trainer_proc = None
            return False

        self._schedule_fake_trainer_check()
        app_logger.info("Fake trainer started")
        return True

    def _schedule_fake_trainer_check(self) -> None:
        try:
            loop = self.config.loop
        except Exception:
            loop = None
        if loop and loop.is_running():
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop is loop:
                loop.call_later(0.2, self._check_fake_trainer_process)
            else:
                loop.call_soon_threadsafe(
                    loop.call_later,
                    0.2,
                    self._check_fake_trainer_process,
                )
            return
        try:
            import threading
        except Exception:
            return
        timer = threading.Timer(0.2, self._check_fake_trainer_process)
        timer.daemon = True
        self._fake_trainer_check_handle = timer
        timer.start()

    def _check_fake_trainer_process(self) -> None:
        if self.is_fake_trainer_running():
            return
        self._fake_trainer_proc = None
        app_logger.warning("Fake trainer stopped unexpectedly")

    def stop_fake_trainer(self) -> None:
        proc = self._fake_trainer_proc
        if proc is None:
            return
        if proc.poll() is not None:
            self._fake_trainer_proc = None
            return

        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=1.0)
        except Exception:
            pass

        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                pass

        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:
                pass

        self._fake_trainer_proc = None
        app_logger.info("Fake trainer stopped")
