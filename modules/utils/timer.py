import time

from logger import app_logger


class TimerError(Exception):
    """A custom exception used to report errors in use of Timer class"""


class Timer:
    def __init__(
        self,
        text="Elapsed time: {:0.4f} seconds",
        logger=app_logger.info,
        auto_log=False,
        auto_start=True,
    ):
        self._start_time = None
        self.text = text
        self.logger = logger
        self.elapsed_time = None
        self.auto_log = auto_log

        if auto_start:
            self.start()

    def start(self):
        """Start a new timer"""
        if self._start_time is not None:
            raise TimerError("Timer is running. Use .stop() to stop it")
        self.elapsed_time = None
        self._start_time = time.perf_counter()

    def stop(self):
        """Stop the timer, and report the elapsed time"""

        if self._start_time is None:
            raise TimerError("Timer is not running. Use .start() to start it")

        self.elapsed_time = time.perf_counter() - self._start_time

        self._start_time = None

        if self.auto_log:
            self.log()

        return self.elapsed_time

    def __enter__(self):
        """Start a new timer as a context manager"""
        self.start()
        return self

    def __exit__(self, *exc_info):
        """Stop the context manager timer"""
        self.stop()

    def log(self):
        if self.logger:
            self.logger(self.text.format(self.elapsed_time))
        else:
            app_logger.warning("Not logger defined for timer")


def log_timers(timers, text_total="total: {0:.3f} sec", logger=app_logger.info):
    total_time = 0
    for t in timers:
        t.log()
        total_time += t.elapsed_time
    logger(text_total.format(total_time))
    return total_time
