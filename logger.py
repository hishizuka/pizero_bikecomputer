import logging
import os
import re
import sys
from datetime import datetime, timedelta

from logging.handlers import RotatingFileHandler


class StreamToLogger:
    logger = None
    level = None

    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())

    def flush(self):
        pass


class CustomRotatingFileHandler(RotatingFileHandler):
    def doRollover(self):
        datetime_format = "%Y-%m-%d_%H-%M-%S"

        if self.stream:
            self.stream.close()
            self.stream = None
            # remove file older than one month (30 days)
            base_filename_no_ext, ext = os.path.splitext(self.baseFilename)
            regex = rf"{base_filename_no_ext}-(.*?){ext}"
            cut_out_date = datetime.now() - timedelta(days=30)
            for root, dirs, files in os.walk(os.path.dirname(self.baseFilename)):
                for file in files:
                    f = os.path.join(root, file)
                    match = re.match(regex, f)
                    if match:
                        try:
                            date = datetime.strptime(match.group(1), datetime_format)
                            if date < cut_out_date:
                                os.remove(f)
                        except Exception:
                            # not our file ? keep it
                            pass

            # we can't get the creation date of the file easily, so use the mt_time
            # e.g. last log time of the file instead
            last_date = datetime.fromtimestamp(int(os.stat(self.baseFilename).st_mtime))

            self.rotate(
                self.baseFilename,
                f"{base_filename_no_ext}-{last_date.strftime(datetime_format)}{ext}",
            )
        if not self.delay:
            self.stream = self._open()

    # never do a rollover "live"
    def shouldRollover(self, record):
        return False


app_logger = logging.getLogger("bike_computer")

# change level in regard to config G_DEBUG
app_logger.setLevel(level=logging.INFO)

# Add simple stream handler
sh = logging.StreamHandler()

app_logger.addHandler(sh)

sys.stdout = StreamToLogger(app_logger, logging.INFO)
sys.stderr = StreamToLogger(app_logger, logging.ERROR)
