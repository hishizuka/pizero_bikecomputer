import argparse
import shlex
import sqlite3
import shutil
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    # Allow running as a script by adding repo root to sys.path.
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

try:
    from modules.utils.cmd import exec_cmd
    from modules.logger.logger import Logger
except ImportError:  # pragma: no cover
    from modules.utils.cmd import exec_cmd
    from .logger import Logger


class LoggerCsv(Logger):
    def write_log(self, filename):
        r = (
            "lap,timer,timestamp,total_timer_time,elapsed_time,heart_rate,speed,cadence,power,distance,"
            "accumulated_power,position_long,position_lat,raw_long,raw_lat,altitude,gps_altitude,raw_gps_altitude,course_altitude,"
            "dem_altitude,gps_speed,gps_distance,gps_mode,gps_used_sats,gps_total_sats,gps_epx,gps_epy,gps_epv,"
            "gps_pdop,gps_hdop,gps_vdop,total_ascent,total_descent,pressure,temperature,humidity,heading,pitch,roll,"
            "gps_track,wind_speed,wind_direction,headwind,"
            "motion,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,cpu_percent,light"
        )
        columns = r.split(",")

        # voltage_battery,current_battery,voltage_out,current_out,battery_percentage\
        # "
        # if sqlite3 command exists, use this command (much faster)
        con = sqlite3.connect(
            self.config.G_LOG_DB,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        sqlite3.dbapi2.converters["DATETIME"] = sqlite3.dbapi2.converters["TIMESTAMP"]
        cur = con.cursor()
        table_columns = [
            row[1]
            for row in cur.execute("PRAGMA table_info(BIKECOMPUTER_LOG)")
        ]
        available = [col for col in columns if col in table_columns]
        if not available:
            cur.close()
            con.close()
            print("ERROR: no matching columns found in BIKECOMPUTER_LOG")
            return False

        select_cols = ",".join(available)
        header = select_cols
        if shutil.which("sh") is not None and shutil.which("sqlite3"):
            sql_cmd = (
                "sqlite3 -header -csv "
                + shlex.quote(self.config.G_LOG_DB)
                + " 'SELECT "
                + select_cols
                + " FROM BIKECOMPUTER_LOG;' > "
                + shlex.quote(filename)
            )
            sqlite3_cmd = ["sh", "-c", sql_cmd]
            result = exec_cmd(sqlite3_cmd, cmd_print=False)
            if result == 0:
                cur.close()
                con.close()
                return True

        with open(filename, "w", encoding="UTF-8") as o:
            o.write(header + "\n")
            for row in cur.execute("SELECT %s FROM BIKECOMPUTER_LOG" % select_cols):
                o.write(",".join(map(str, row)) + "\n")

        cur.close()
        con.close()

        return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export BIKECOMPUTER_LOG from a sqlite3 DB to CSV."
    )
    parser.add_argument(
        "db_path",
        help="Path to sqlite3 database file (e.g. log/log.db-YYYY-MM-DD_HH-MM-SS).",
    )
    parser.add_argument(
        "--output",
        help="Output CSV path. Default: same folder and timestamp based .csv",
    )
    args = parser.parse_args()

    try:
        db_path = Logger.resolve_db_path(args.db_path)
    except FileNotFoundError:
        print(f"ERROR: db file not found: {args.db_path}")
        return 1

    output_path = (
        Path(args.output)
        if args.output
        else Logger.get_default_output_path(db_path, ".csv")
    )
    logger = LoggerCsv(Logger.create_command_config(db_path))
    if not logger.write_log(str(output_path)):
        print(f"ERROR: failed to export csv: {db_path}")
        return 1

    print(f"Done. output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
