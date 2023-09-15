import time
import datetime
import asyncio


class Sensor:
    config = None
    values = None

    # for timer
    start_time = None
    wait_time = 1.0
    actual_loop_interval = None

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
        self.start_time = datetime.datetime.now()

    def get_sleep_time(self, interval):
        loop_time = (datetime.datetime.now() - self.start_time).total_seconds()
        d1, d2 = divmod(loop_time, interval)
        if d1 > interval * 10:  # [s]
            print(
                "too long loop_time({}):{:.2f}s, interval:{:.1f}".format(
                    self.__class__.__name__, loop_time, interval
                )
            )
            d1 = d2 = 0
        self.wait_time = interval - d2
        self.actual_loop_interval = (d1 + 1) * interval
