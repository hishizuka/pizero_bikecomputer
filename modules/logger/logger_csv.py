import argparse
import csv
import shlex
import sqlite3
import shutil
from contextlib import closing
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    # Allow running as a script by adding repo root to sys.path.
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from modules.utils.cmd import exec_cmd
from modules.logger import (
    G_MAGNETIC_HEADING_COLUMNS,
)
from modules.logger.logger import Logger


class LoggerCsv(Logger):
    def write_log(self, filename):
        r = (
            "lap,timer,timestamp,total_timer_time,elapsed_time,heart_rate,speed,cadence,power,distance,"
            "accumulated_power,position_long,position_lat,raw_long,raw_lat,altitude,gps_altitude,raw_gps_altitude,course_altitude,"
            "dem_altitude,gps_speed,gps_distance,gps_mode,gps_used_sats,gps_total_sats,"
            "gps_position_quality_state,gps_position_quality_reason,gps_position_distance_ratio,"
            "gps_position_distance_error,distance_source,gps_epx,gps_epy,gps_epv,"
            "gps_pdop,gps_hdop,gps_vdop,total_ascent,total_descent,pressure,temperature,humidity,"
            "heading_gps_deg,heading_gps_quality,heading_magnetic_deg,"
            "heading_deg,heading_source,pitch,roll,"
            "wind_speed,wind_direction,headwind,"
            "motion,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,cpu_percent,system_cpu_percent,light"
        )
        columns = r.split(",") + [
            name for name, _ in G_MAGNETIC_HEADING_COLUMNS
        ]

        with closing(
            sqlite3.connect(
                self.config.G_LOG_DB,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
        ) as con:
            sqlite3.dbapi2.converters["DATETIME"] = sqlite3.dbapi2.converters[
                "TIMESTAMP"
            ]
            table_columns = {
                row[1] for row in con.execute("PRAGMA table_info(BIKECOMPUTER_LOG)")
            }
            selected = [column for column in columns if column in table_columns]
            if not selected:
                return False

            query = f"SELECT {','.join(selected)} FROM BIKECOMPUTER_LOG;"
            # Prefer the sqlite3 command when available; it is much faster.
            if shutil.which("sh") is not None and shutil.which("sqlite3"):
                sql_cmd = (
                    f"sqlite3 -csv -header {shlex.quote(self.config.G_LOG_DB)} "
                    f"{shlex.quote(query)} > {shlex.quote(filename)}"
                )
                if exec_cmd(["sh", "-c", sql_cmd], cmd_print=False) == 0:
                    return True

            with open(filename, "w", encoding="UTF-8", newline="") as o:
                writer = csv.writer(o, lineterminator="\n")
                writer.writerow(selected)
                writer.writerows(con.execute(query))
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
