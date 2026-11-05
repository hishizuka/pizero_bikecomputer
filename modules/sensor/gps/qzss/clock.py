import asyncio
import subprocess
import shutil
import time
from datetime import datetime


class QzssDcrClock:
    """Qualify host UTC independently of position fixes and detect clock steps."""

    def __init__(self):
        self.generation = 0
        self._trusted = False
        self._system_synced = False
        self._gnss_until = 0.0
        self._sample = (time.time(), time.monotonic())

    def check(self):
        utc, tick = time.time(), time.monotonic()
        previous_utc, previous_tick = self._sample
        self._sample = utc, tick
        if abs((utc - previous_utc) - (tick - previous_tick)) > 2.0:
            self._system_synced = False
            self._gnss_until = 0.0
            self.generation += 1
        trusted = self._system_synced or tick < self._gnss_until
        if trusted != self._trusted:
            self.generation += 1
            self._trusted = trusted
        return trusted

    def observe_gnss(self, timestamp):
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp).timestamp()
        if timestamp is not None and timestamp >= 946684800:
            self.check()
            if abs(timestamp - time.time()) <= 2.0:
                self._gnss_until = time.monotonic() + 10.0

    @staticmethod
    def _system_time_synced():
        executable = shutil.which("timedatectl")
        if executable is None:
            return False
        try:
            result = subprocess.run(
                [executable, "show", "--property=NTPSynchronized", "--value"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and result.stdout.strip() == "yes"

    async def run(self):
        while True:
            self._system_synced = await asyncio.to_thread(self._system_time_synced)
            self.check()
            await asyncio.sleep(10.0)
