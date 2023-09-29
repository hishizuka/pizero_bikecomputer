from datetime import datetime

from logger import app_logger


# replacement of dateutil.parser.parse
def datetime_myparser(ts):
    if len(ts) == 14:
        # 20190322232414 / 14 chars
        dt = datetime(
            int(ts[0:4]),  # %Y
            int(ts[4:6]),  # %m
            int(ts[6:8]),  # %d
            int(ts[8:10]),  # %H
            int(ts[10:12]),  # %M
            int(ts[12:14]),  # %s
        )
        return dt
    elif 24 <= len(ts) <= 26:
        # 2019-03-22T23:24:14.280604 / 26 chars
        # 2019-09-30T12:44:55.000Z   / 24 chars
        dt = datetime(
            int(ts[0:4]),  # %Y
            int(ts[5:7]),  # %m
            int(ts[8:10]),  # %d
            int(ts[11:13]),  # %H
            int(ts[14:16]),  # %M
            int(ts[17:19]),  # %s
        )
        return dt
    app_logger.error(f"Could not parse date {ts} {len(ts)}")
