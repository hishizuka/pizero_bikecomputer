import asyncio
import os
import subprocess

from modules.app_logger import app_logger


class BuzzerController:
    _STOP_TIMEOUT_SEC = 0.2
    _SUPPORTED_SOUNDS = {
        "sgx-ca600-poweron",
        "sgx-ca600-poweroff",
        "sgx-ca600-start",
        "sgx-ca600-stop",
        "sgx-ca600-lap",
        "sgx-ca600-cancel",
        "sgx-ca600-save",
        "beep",
        "beep-double",
        "beep-triple",
        "alert",
        "navi-turn",
    }

    def __init__(self, config):
        self.config = config
        self._proc = None
        self._lock = asyncio.Lock()
        self._script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "buzzer.sh")
        )
        self.play("sgx-ca600-poweron")

    def play(self, sound_name: str) -> None:
        if not self.config.G_USE_BUZZER:
            return
        if not self._is_supported_sound(sound_name):
            return
        if not self._has_buzzer_script():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._start_process_sync(sound_name)
            return
        if not loop.is_running():
            self._start_process_sync(sound_name)
            return
        loop.create_task(self._play(sound_name))

    async def _play(self, sound_name: str) -> None:
        if not self.config.G_USE_BUZZER:
            return
        if not self._is_supported_sound(sound_name):
            return
        if not self._has_buzzer_script():
            return

        async with self._lock:
            await self._stop_running_process()
            await self._start_process_async(sound_name)

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_running_process()
            if not self.config.G_USE_BUZZER:
                return
            if not self._has_buzzer_script():
                return
            await self._start_process_async("sgx-ca600-poweroff")

    async def _stop_running_process(self) -> None:
        if self._proc is None:
            return

        proc = self._proc
        self._proc = None

        if proc.returncode is not None:
            return

        try:
            proc.terminate()
        except ProcessLookupError:
            return
        except Exception as exc:
            app_logger.warning(f"Buzzer terminate failed: {exc}")
            return

        try:
            await asyncio.wait_for(proc.wait(), timeout=self._STOP_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                return
            except Exception as exc:
                app_logger.warning(f"Buzzer kill failed: {exc}")
                return
            try:
                await proc.wait()
            except Exception as exc:
                app_logger.warning(f"Buzzer wait after kill failed: {exc}")
        except Exception as exc:
            app_logger.warning(f"Buzzer wait failed: {exc}")

    def _has_buzzer_script(self) -> bool:
        if os.path.isfile(self._script_path):
            return True
        app_logger.warning(f"Buzzer script not found: {self._script_path}")
        return False

    def _is_supported_sound(self, sound_name: str) -> bool:
        if sound_name in self._SUPPORTED_SOUNDS:
            return True
        app_logger.warning(f"Unsupported buzzer sound requested: {sound_name}")
        return False

    async def _start_process_async(self, sound_name: str) -> None:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                "/bin/bash",
                self._script_path,
                sound_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception as exc:
            self._proc = None
            app_logger.warning(f"Buzzer start failed: {exc}")

    def _start_process_sync(self, sound_name: str) -> None:
        try:
            subprocess.Popen(
                ["/bin/bash", self._script_path, sound_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            app_logger.warning(f"Buzzer start failed: {exc}")
