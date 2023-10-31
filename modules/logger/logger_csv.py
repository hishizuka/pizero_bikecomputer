import os
import sqlite3
import shutil

from modules.utils.cmd import exec_cmd
from .logger import Logger


class LoggerCsv(Logger):
    def write_log(self, filename):
        r = (
            "lap,timer,timestamp,total_timer_time,elapsed_time,heart_rate,speed,cadence,power,distance,"
            "accumulated_power,position_long,position_lat,raw_long,raw_lat,altitude,gps_altitude,course_altitude,"
            "dem_altitude,gps_speed,gps_distance,gps_mode,gps_used_sats,gps_total_sats,gps_epx,gps_epy,gps_epv,"
            "gps_pdop,gps_hdop,gps_vdop,total_ascent,total_descent,pressure,temperature,heading,gps_track,"
            "motion,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,cpu_percent,light"
        )

        # voltage_battery,current_battery,voltage_out,current_out,battery_percentage\
        # "
        # if sqlite3 command exists, use this command (much faster)
        if shutil.which("sh") is not None and shutil.which("sqlite3"):
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
            con = sqlite3.connect(
                self.config.G_LOG_DB,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            sqlite3.dbapi2.converters["DATETIME"] = sqlite3.dbapi2.converters[
                "TIMESTAMP"
            ]
            cur = con.cursor()

            with open(filename, "w", encoding="UTF-8") as o:
                # get Lap Records
                o.write(r + "\n")

                for row in cur.execute("SELECT %s FROM BIKECOMPUTER_LOG" % r):
                    o.write(",".join(map(str, row)) + "\n")

            cur.close()
            con.close()

        return True
