import asyncio
import time

from modules.app_logger import app_logger


class Sensor:
    config = None
    values = None

    # for timer
    start_time = None
    wait_time = 1.0
    actual_loop_interval = None

    @property
    def course(self):
        return self.config.logger.course

    def __init__(self, config, values):
        self.config = config
        self.values = values
        self.sensor_init()

    def sensor_init(self):
        pass

    def quit(self):
        pass

    # async def update(self):
    def update(self):
        pass

    def get(self):
        pass

    def reset(self):
        pass

    async def sleep(self):
        await asyncio.sleep(self.wait_time)
        self.start_time = time.perf_counter()

    def get_sleep_time(self, interval=None):
        if not interval:
            interval = self.config.G_GPS_INTERVAL
        loop_time = time.perf_counter() - self.start_time
        d1, d2 = divmod(loop_time, interval)
        if d1 > interval * 10:  # [s]
            app_logger.warning(
                f"too long loop_time({self.__class__.__name__}):{loop_time:.2f}s, interval:{interval:.1f}"
            )
            d1 = d2 = 0
        self.wait_time = interval - d2
        self.actual_loop_interval = (d1 + 1) * interval
