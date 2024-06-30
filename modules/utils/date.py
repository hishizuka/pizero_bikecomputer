from datetime import datetime, timezone

from logger import app_logger


# replacement of dateutil.parser.parse
def datetime_myparser(ts):
    if len(ts) not in [24, 26, 32]:
        app_logger.error(f"Could not parse date {ts} {len(ts)}")
        return None
    
    # 2024-06-24 00:58:54.801928+00:00  / 32 chars (from log.db)
    # 2019-09-30T12:44:55.000Z          / 24 chars (obsolete)
    # 2019-03-22T23:24:14.280604        / 26 chars (obsolete)
    dt = datetime(
        int(ts[0:4]),  # %Y
        int(ts[5:7]),  # %m
        int(ts[8:10]),  # %d
        int(ts[11:13]),  # %H
        int(ts[14:16]),  # %M
        int(ts[17:19]),  # %s
        tzinfo=timezone.utc,
    )
    return dt
    
