import sqlite3
import time
import datetime
import shutil

from modules.utils.cmd import exec_cmd
from .logger import Logger


class config_local:
    G_LOG_DB = "./log.db~"
    G_LOG_DIR = "./"
    G_PRODUCT = "Pizero BIKECOMPUTER"
    G_VERSION_MAJOR = 0
    G_VERSION_MINOR = 1
    G_UNIT_ID = "0000000000000000"


class LoggerCsv(Logger):
    def write_log(self):
        # get start date
        ## SQLite
        con = sqlite3.connect(
            self.config.G_LOG_DB,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        sqlite3.dbapi2.converters["DATETIME"] = sqlite3.dbapi2.converters["TIMESTAMP"]
        cur = con.cursor()
        cur.execute("SELECT timestamp, MIN(timestamp) FROM BIKECOMPUTER_LOG")
        first_row = cur.fetchone()
        if first_row is not None:
            start_date = first_row[0]
        else:
            return False

        offset = time.localtime().tm_gmtoff
        startdate_local = start_date + datetime.timedelta(seconds=offset)
        self.config.G_LOG_START_DATE = startdate_local.strftime("%Y%m%d%H%M%S")
        filename = self.config.G_LOG_DIR + self.config.G_LOG_START_DATE + ".csv"

        r = "\
lap,timer,timestamp,total_timer_time,elapsed_time,heart_rate,speed,cadence,power,distance,accumulated_power,\
position_long,position_lat,raw_long,raw_lat,altitude,gps_altitude,course_altitude,dem_altitude,gps_speed,gps_distance,gps_mode,gps_used_sats,gps_total_sats,gps_epx,gps_epy,gps_epv,gps_pdop,gps_hdop,gps_vdop,\
total_ascent,total_descent,pressure,temperature,heading,gps_track,motion,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,cpu_percent,light"
        # voltage_battery,current_battery,voltage_out,current_out,battery_percentage\
        # "
        # if sqlite3 command exists, use this command (much faster)
        if shutil.which("sh") is not None and shutil.which("sqlite3"):
            cur.close()
            con.close()
            sql_cmd = (
                "sqlite3 -header -csv "
                + self.config.G_LOG_DB
                + " 'SELECT "
                + r
                + " FROM BIKECOMPUTER_LOG;' > "
                + filename
            )
            sqlite3_cmd = ["sh", "-c", sql_cmd]
            exec_cmd(sqlite3_cmd)
        else:
            f = open(filename, "w", encoding="UTF-8")

            # get Lap Records
            f.write(r + "\n")
            for row in cur.execute("SELECT %s FROM BIKECOMPUTER_LOG" % r):
                f.write(",".join(map(str, row)) + "\n")
            f.close()

            cur.close()
            con.close()

        return True


if __name__ == "__main__":
    c = config_local()
    d = LoggerCsv(c)
    d.write_log()
