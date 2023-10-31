import os
import sqlite3
import signal
import shutil
import time
import asyncio
import traceback
from datetime import datetime, timedelta, timezone

import numpy as np
from crdp import rdp

from logger import app_logger
from modules.utils.cmd import exec_cmd
from modules.utils.date import datetime_myparser
from modules.utils.timer import Timer


class LoggerCore:
    config = None
    sensor = None

    # for db
    con = None
    cur = None
    lock = None
    event = None

    # for timer
    values = {
        "count": 0,
        "count_lap": 0,
        "lap": 0,
        "elapsed_time": 0,  # [s]
        "start_time": None,
        "gross_ave_spd": 0,  # [km/h]
        "gross_diff_time": "00:00",  # "+-hh:mm" (string)
    }
    record_stats = {
        "pre_lap_avg": {},
        "lap_avg": {},
        "entire_avg": {},
        "pre_lap_max": {},
        "lap_max": {},
        "entire_max": {},
    }
    lap_keys = [
        "heart_rate",
        "cadence",
        "distance",
        "speed",
        "power",
        "accumulated_power",
        "total_ascent",
        "total_descent",
    ]
    # for power and cadence (including / not including zero)
    average = {
        "lap": {"cadence": {"count": 0, "sum": 0}, "power": {"count": 0, "sum": 0}},
        "entire": {"cadence": {"count": 0, "sum": 0}, "power": {"count": 0, "sum": 0}},
    }

    # for update_track
    pre_lat = None
    pre_lon = None

    # for store_short_log_for_update_track
    short_log_dist = []
    short_log_lat = []
    short_log_lon = []
    short_log_timestamp = []
    short_log_limit = 120
    short_log_available = True
    short_log_lock = False

    # for debug
    position_log = np.array([])

    resume_status = False
    last_timestamp = None

    def __init__(self, config):
        super().__init__()
        self.config = config

    def start_coroutine(self):
        self.sql_queue = asyncio.Queue()
        asyncio.create_task(self.sql_worker())
        try:
            self.count_up_lock = False
            self.config.loop.add_signal_handler(signal.SIGALRM, self.count_up)
            signal.setitimer(
                signal.ITIMER_REAL,
                self.config.G_LOGGING_INTERVAL,
                self.config.G_LOGGING_INTERVAL,
            )
        except:
            # for windows
            traceback.print_exc()

    def delay_init(self):
        from .course import Course
        from .logger import logger_csv, logger_fit
        from . import sensor_core

        self.sensor = sensor_core.SensorCore(self.config)
        self.course = Course(self.config)
        self.logger_csv = logger_csv.LoggerCsv(self.config)
        self.logger_fit = logger_fit.LoggerFit(self.config)

        self.sensor.start_coroutine()

        self.course.load()

        for k in self.lap_keys:
            self.record_stats["pre_lap_avg"][k] = 0
            self.record_stats["lap_avg"][k] = 0
            self.record_stats["entire_avg"][k] = 0
            self.record_stats["pre_lap_max"][k] = 0
            self.record_stats["lap_max"][k] = 0
            self.record_stats["entire_max"][k] = 0

        # sqlite3
        # usage of sqlite3 is "insert" only, so check_same_thread=False
        self.con = sqlite3.connect(self.config.G_LOG_DB, check_same_thread=False)
        self.cur = self.con.cursor()
        self.init_db()
        self.cur.execute("SELECT timestamp FROM BIKECOMPUTER_LOG LIMIT 1")
        first_row = self.cur.fetchone()
        if first_row is None:
            self.reset()
        else:
            self.resume()
            self.resume_status = True

    async def resume_start_stop(self):
        if not self.resume_status:
            return

        # resume START/STOP status if temporary values exist
        self.config.G_MANUAL_STATUS = self.config.setting.get_config_pickle(
            "G_MANUAL_STATUS", self.config.G_MANUAL_STATUS
        )
        if self.config.G_MANUAL_STATUS == "START":
            # restore system time from self.last_timestamp or self.sensor.gps.get_utc_time(g.time)
            self.config.G_MANUAL_STATUS = "STOP"
            await self.restore_utc_time()
            self.start_and_stop_manual()

    async def restore_utc_time(self):
        # restore time from gps or last log(self.last_timestamp)
        count = 0
        count_max = 60
        while not self.sensor.sensor_gps.is_time_modified and count < count_max:
            await asyncio.sleep(1)
            count += 1

        if not self.sensor.sensor_gps.is_time_modified:
            delta = count + int(self.config.boot_time * 1.25)
            utctime = datetime.strptime(
                self.last_timestamp, "%Y-%m-%d %H:%M:%S.%f"
            ) + timedelta(seconds=delta)
            if utctime > datetime.utcnow():
                datecmd = [
                    "sudo",
                    "date",
                    "-u",
                    "--set",
                    utctime.strftime("%Y/%m/%d %H:%M:%S"),
                ]
                exec_cmd(datecmd)

    async def quit(self):
        await self.sensor.quit()

        await self.sql_queue.put(None)
        await asyncio.sleep(0.1)
        self.cur.close()
        self.con.close()

    def remove_handler(self):
        self.config.loop.remove_signal_handler(signal.SIGALRM)

    async def sql_worker(self):
        while True:
            sql = await self.sql_queue.get()
            if sql is None:
                break
            self.cur.execute(*sql)
            self.con.commit()
            self.sql_queue.task_done()

    def init_db(self):
        self.create_table_sql = """CREATE TABLE BIKECOMPUTER_LOG(
      timestamp DATETIME,
      lap INTEGER,
      timer INTEGER,
      total_timer_time INTEGER,
      elapsed_time INTEGER,
      position_lat FLOAT,
      position_long FLOAT,
      raw_lat FLOAT,
      raw_long FLOAT,
      gps_altitude FLOAT,
      gps_speed FLOAT,
      gps_distance FLOAT,
      gps_mode INTEGER,
      gps_used_sats INTEGER,
      gps_total_sats INTEGER,
      gps_track INTEGER,
      gps_epx FLOAT,
      gps_epy FLOAT,
      gps_epv FLOAT,
      gps_pdop FLOAT,
      gps_hdop FLOAT,
      gps_vdop FLOAT,
      heart_rate INTEGER,
      cadence INTEGER,
      distance FLOAT,
      speed FLOAT,
      power INTEGER,
      accumulated_power INTEGER,
      temperature FLOAT,
      pressure FLOAT,
      humidity INTEGER,
      altitude FLOAT,
      course_altitude FLOAT,
      dem_altitude FLOAT,
      heading INTEGER,
      motion INTEGER,
      acc_x FLOAT,
      acc_y FLOAT,
      acc_z FLOAT,
      gyro_x FLOAT,
      gyro_y FLOAT,
      gyro_z FLOAT,
      light INTEGER,
      cpu_percent INTEGER,
      total_ascent FLOAT,
      total_descent FLOAT,
      lap_heart_rate INTEGER,
      lap_cadence INTEGER,
      lap_distance FLOAT,
      lap_speed FLOAT,
      lap_power INTEGER,
      lap_accumulated_power INTEGER,
      lap_total_ascent FLOAT,
      lap_total_descent FLOAT,
      avg_heart_rate INTEGER,
      avg_cadence INTEGER,
      avg_speed FLOAT,
      avg_power INTEGER,
      lap_cad_count INTEGER,
      lap_cad_sum INTEGER,
      avg_cad_count INTEGER,
      avg_cad_sum INTEGER,
      lap_power_count INTEGER,
      lap_power_sum INTEGER,
      avg_power_count INTEGER,
      avg_power_sum INTEGER
    )"""
        self.cur.execute(
            "SELECT * FROM sqlite_master WHERE type='table' and name='BIKECOMPUTER_LOG'"
        )
        res = self.cur.fetchone()
        replace_flg = False
        if (
            res is not None
            and len(res) >= 5
            and res[4].replace(" ", "") != self.create_table_sql.replace(" ", "")
        ):
            log_db_moved = self.config.G_LOG_DB + "-old_layout"
            self.cur.close()
            self.con.close()

            shutil.move(self.config.G_LOG_DB, log_db_moved)
            app_logger.info(
                f"The layout of {self.config.G_LOG_DB} is changed to {log_db_moved}"
            )

            self.con = sqlite3.connect(self.config.G_LOG_DB, check_same_thread=False)
            self.cur = self.con.cursor()
            replace_flg = True
        if res is None or replace_flg:
            self.con.execute(self.create_table_sql)
            self.cur.execute("CREATE INDEX lap_index ON BIKECOMPUTER_LOG(lap)")
            self.cur.execute(
                "CREATE INDEX total_timer_time_index ON BIKECOMPUTER_LOG(total_timer_time)"
            )
            self.cur.execute(
                "CREATE INDEX timestamp_index ON BIKECOMPUTER_LOG(timestamp)"
            )
            self.con.commit()

    def count_up(self):
        self.calc_gross()
        if self.config.G_STOPWATCH_STATUS != "START" or self.count_up_lock:
            return
        self.count_up_lock = True
        self.values["count"] += 1
        self.values["count_lap"] += 1
        asyncio.create_task(self.record_log())
        self.count_up_lock = False

    def start_and_stop_manual(self):
        time_str = datetime.now().strftime("%Y%m%d %H:%M:%S")
        popup_extra = ""
        pre_status = self.config.G_MANUAL_STATUS

        if self.config.G_MANUAL_STATUS != "START":
            self.config.display.screen_flash_short()
            app_logger.info(f"->M START {time_str}")
            self.start_and_stop("STOP")
            self.config.G_MANUAL_STATUS = "START"
            if self.config.gui is not None:
                self.config.gui.change_start_stop_button(self.config.G_MANUAL_STATUS)
            if self.values["start_time"] is None:
                self.values["start_time"] = int(datetime.utcnow().timestamp())

            if pre_status == "INIT" and not np.isnan(
                self.sensor.values["integrated"]["dem_altitude"]
            ):
                asyncio.create_task(
                    self.sensor.sensor_i2c.update_sealevel_pa(
                        self.sensor.values["integrated"]["dem_altitude"]
                    )
                )
                popup_extra = "<br />altitude corrected: {}m".format(
                    int(self.sensor.values["integrated"]["dem_altitude"])
                )

        elif self.config.G_MANUAL_STATUS == "START":
            self.config.display.screen_flash_long()
            app_logger.info(f"->M STOP  {time_str}")
            self.start_and_stop("START")
            self.config.G_MANUAL_STATUS = "STOP"
            if self.config.gui is not None:
                self.config.gui.change_start_stop_button(self.config.G_MANUAL_STATUS)

        self.config.setting.set_config_pickle(
            "G_MANUAL_STATUS", self.config.G_MANUAL_STATUS, quick_apply=True
        )

        # send online
        if self.config.G_THINGSBOARD_API["STATUS"]:
            self.config.api.send_livetrack_data(quick_send=True)

        # show message
        self.config.gui.show_popup(self.config.G_MANUAL_STATUS + popup_extra)

    def start_and_stop(self, status=None):
        if status is not None:
            self.config.G_STOPWATCH_STATUS = status
        time_str = datetime.now().strftime("%Y%m%d %H:%M:%S")
        if self.config.G_STOPWATCH_STATUS != "START":
            self.config.G_STOPWATCH_STATUS = "START"
            app_logger.info(f"->START   {time_str}")
        elif self.config.G_STOPWATCH_STATUS == "START":
            self.config.G_STOPWATCH_STATUS = "STOP"
            app_logger.info(f"->STOP    {time_str}")

    def count_laps(self):
        if self.values["count"] == 0 or self.values["count_lap"] == 0:
            return
        self.config.display.screen_flash_short()
        lap_time = self.values["count_lap"]
        self.values["lap"] += 1
        self.values["count_lap"] = 0
        for k in self.lap_keys:
            self.record_stats["pre_lap_avg"][k] = self.record_stats["lap_avg"][k]
            self.record_stats["pre_lap_max"][k] = self.record_stats["lap_max"][k]
            self.record_stats["lap_max"][k] = 0
            self.record_stats["lap_avg"][k] = 0
        for k2 in ["cadence", "power"]:
            self.average["lap"][k2]["count"] = 0
            self.average["lap"][k2]["sum"] = 0
        asyncio.create_task(self.record_log())
        time_str = datetime.now().strftime("%Y%m%d %H:%M:%S")
        app_logger.info(f"->LAP:{self.values['lap']}   {time_str}")

        # show message
        value_str = (
            self.config.gui.gui_config.G_UNIT["Speed"]
            + ", "
            + self.config.gui.gui_config.G_UNIT["HeartRate"]
            + ", "
            + self.config.gui.gui_config.G_UNIT["Power"]
        )
        hour_sec = divmod(lap_time, 3600)
        min_sec = divmod(hour_sec[1], 60)
        lap_time_str = "{:}:{:02}".format(hour_sec[0], min_sec[0])
        self.config.gui.show_popup_multiline(
            "LAP {} ({}km, {})".format(
                self.values["lap"],
                round(self.record_stats["pre_lap_avg"]["distance"] / 1000, 1),
                lap_time_str,
            ),
            value_str.format(
                self.record_stats["pre_lap_avg"]["speed"] * 3.6,
                self.record_stats["pre_lap_avg"]["heart_rate"],
                self.record_stats["pre_lap_avg"]["power"],
            ),
        )

    def get_start_end_dates(self):
        # get start date and end_date of the current log
        start_date = end_date = None  # UTC time

        con = sqlite3.connect(
            self.config.G_LOG_DB,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        sqlite3.dbapi2.converters["DATETIME"] = sqlite3.dbapi2.converters["TIMESTAMP"]
        cur = con.cursor()
        cur.execute(
            'SELECT MIN(timestamp) as "ts [timestamp]", MAX(timestamp) as "ts [timestamp]" FROM BIKECOMPUTER_LOG'
        )
        first_row = cur.fetchone()

        if first_row is not None:
            start_date, end_date = first_row

            start_date = start_date.replace(tzinfo=timezone.utc)
            end_date = end_date.replace(tzinfo=timezone.utc)

        cur.close()
        con.close()

        return start_date, end_date

    def reset_count(self):
        if self.config.G_MANUAL_STATUS == "START" or self.values["count"] == 0:
            return

        # reset
        self.config.display.screen_flash_long()

        # close db connect
        self.cur.close()
        self.con.close()

        # get start date and end_date of the current log
        start_date, end_date = self.get_start_end_dates()

        if start_date is None and end_date is None:
            app_logger.info("No log found, nothing to write")
            return

        start_date_local = start_date.astimezone().strftime("%Y-%m-%d_%H-%M-%S")

        filename = os.path.join(self.config.G_LOG_DIR, start_date_local)
        fit_text = f"Write fit({self.logger_fit.mode}):"
        csv_text = f"Write csv{' ' * (len(self.logger_fit.mode) + 2)}:"

        timers = [
            Timer(auto_start=False, auto_log=True, text=f"{csv_text} {{:0.4f}} sec"),
            Timer(auto_start=False, auto_log=True, text=f"{fit_text} {{:0.4f}} sec"),
            Timer(auto_start=False, auto_log=True, text="DELETE : {:0.4f} sec"),
        ]

        if self.config.G_LOG_WRITE_CSV:
            with timers[0]:
                if not self.logger_csv.write_log(f"{filename}.csv"):
                    return

        if self.config.G_LOG_WRITE_FIT:
            with timers[1]:
                if not self.logger_fit.write_log(
                    f"{filename}.fit", start_date, end_date
                ):
                    return

        # backup and reset database
        with timers[2]:
            shutil.move(
                self.config.G_LOG_DB,
                f"{self.config.G_LOG_DB}-{start_date_local}",
            )

            self.reset()

            # restart db connect
            # usage of sqlite3 is "insert" only, so check_same_thread=False
            self.con = sqlite3.connect(self.config.G_LOG_DB, check_same_thread=False)
            self.cur = self.con.cursor()
            self.init_db()

        # reset temporary values
        self.config.setting.reset_config_pickle()

        # reset accumulated values
        self.sensor.reset()
        # reset course index
        self.course.index.reset()

    def reset(self):
        # clear lap
        self.values["count"] = 0
        self.values["count_lap"] = 0
        self.values["lap"] = 0
        self.values["elapsed_time"] = 0
        self.values["start_time"] = None
        self.values["gross_ave_spd"] = 0
        self.values["gross_diff_time"] = "00:00"

        for k in self.lap_keys:
            self.record_stats["pre_lap_avg"][k] = 0
            self.record_stats["lap_avg"][k] = 0
            self.record_stats["entire_avg"][k] = 0
            self.record_stats["pre_lap_max"][k] = 0
            self.record_stats["lap_max"][k] = 0
            self.record_stats["entire_max"][k] = 0
        for k1 in self.average.keys():
            for k2 in ["cadence", "power"]:
                self.average[k1][k2]["count"] = 0
                self.average[k1][k2]["sum"] = 0

    def reset_course(self, delete_course_file=False, replace=False):
        self.config.gui.reset_course()
        self.course.reset(delete_course_file=delete_course_file, replace=replace)
        self.course.index.reset()

    def set_new_course(self, course_file):
        self.course.load(course_file)

    async def record_log(self):
        # need to detect location delta for smart recording

        # get present value
        value = self.sensor.values["integrated"]

        # update lap stats if value is not Null
        for k, v in value.items():
            # skip when null value(np.nan)
            if k not in [
                "heart_rate",
                "cadence",
                "speed",
                "power",
                "distance",
                "accumulated_power",
            ]:
                continue
            if np.isnan(v):
                continue
            # get average
            if k in ["heart_rate", "cadence", "speed", "power"]:
                x1 = t1 = 0  # for lap_avg = x1 / t1
                x2 = t2 = 0  # for entire_ave = x2 / t2

                # heart_rate : hr_sum / t
                # speed : distance / t
                # power : power_sum / t (exclude/include zero)
                # cadence : cad_sum / t (exclude/include zero)
                if k in ["heart_rate"]:
                    x1 = (
                        self.record_stats["lap_avg"][k] * (self.values["count_lap"] - 1)
                        + v
                    )
                    t1 = self.values["count_lap"]
                    x2 = (
                        self.record_stats["entire_avg"][k] * (self.values["count"] - 1)
                        + v
                    )
                    t2 = self.values["count"]
                elif k in ["speed"]:
                    x1 = self.record_stats["lap_avg"]["distance"]  # [m]
                    t1 = self.values["count_lap"]  # [s]
                    x2 = value["distance"]  # [m]
                    t2 = self.values["count"]  # [s]
                # average including/excluding zero (cadence, power)
                elif k in ["cadence", "power"]:
                    if v == 0 and not self.config.G_AVERAGE_INCLUDING_ZERO[k]:
                        continue
                    for l_e in ["lap", "entire"]:
                        self.average[l_e][k]["sum"] += v
                        self.average[l_e][k]["count"] += 1
                    x1 = self.average["lap"][k]["sum"]
                    t1 = self.average["lap"][k]["count"]
                    x2 = self.average["entire"][k]["sum"]
                    t2 = self.average["entire"][k]["count"]
                # update lap average
                if t1 > 0:
                    self.record_stats["lap_avg"][k] = x1 / t1
                if t2 > 0:
                    self.record_stats["entire_avg"][k] = x2 / t2
            # get lap distance, accumulated_power
            elif k in ["distance", "accumulated_power"]:
                # v is valid value
                x1 = self.record_stats["pre_lap_max"][k]
                if np.isnan(x1):
                    x1 = 0
                self.record_stats["lap_avg"][k] = v - x1

            # update max
            if k in ["heart_rate", "cadence", "speed", "power"]:
                if self.record_stats["lap_max"][k] < v:
                    self.record_stats["lap_max"][k] = v
                if self.record_stats["entire_max"][k] < v:
                    self.record_stats["entire_max"][k] = v
            elif k in ["distance", "accumulated_power"]:
                self.record_stats["lap_max"][k] = v

        # get lap total_ascent, total_descent
        for k in ["total_ascent", "total_descent"]:
            x1 = self.record_stats["pre_lap_max"][k]
            x2 = self.sensor.values["I2C"][k]
            self.record_stats["lap_avg"][k] = x2 - x1
            self.record_stats["lap_max"][k] = x2

        ## SQLite
        now_time = datetime.utcnow()
        # self.cur.execute("""\
        sql = (
            """\
      INSERT INTO BIKECOMPUTER_LOG VALUES(\
        ?,?,?,?,?,\
        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,\
        ?,?,?,?,?,?,\
        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,\
        ?,?,?,?,?,?,?,?,\
        ?,?,?,?,\
        ?,?,?,?,?,?,?,?\
      )""",
            (
                now_time,
                self.values["lap"],
                self.values["count_lap"],
                self.values["count"],
                self.values["elapsed_time"],
                ###
                self.sensor.values["GPS"]["lat"],
                self.sensor.values["GPS"]["lon"],
                self.sensor.values["GPS"]["raw_lat"],
                self.sensor.values["GPS"]["raw_lon"],
                self.sensor.values["GPS"]["alt"],
                self.sensor.values["GPS"]["speed"],
                self.sensor.values["GPS"]["distance"],
                self.sensor.values["GPS"]["mode"],
                self.sensor.values["GPS"]["used_sats"],
                self.sensor.values["GPS"]["total_sats"],
                self.sensor.values["GPS"]["track"],
                self.sensor.values["GPS"]["epx"],
                self.sensor.values["GPS"]["epy"],
                self.sensor.values["GPS"]["epv"],
                self.sensor.values["GPS"]["pdop"],
                self.sensor.values["GPS"]["hdop"],
                self.sensor.values["GPS"]["vdop"],
                ###
                value["heart_rate"],
                value["cadence"],
                value["distance"],
                value["speed"],
                value["power"],
                value["accumulated_power"],
                ###
                value["temperature"],
                self.sensor.values["I2C"]["pressure"],
                self.sensor.values["I2C"]["humidity"],
                self.sensor.values["I2C"]["altitude"],
                self.course.index.altitude,
                value["dem_altitude"],
                self.sensor.values["I2C"]["heading"],
                self.sensor.values["I2C"]["m_stat"],
                # self.sensor.values['I2C']['acc'][0],
                # self.sensor.values['I2C']['acc'][1],
                # self.sensor.values['I2C']['acc'][2],
                self.sensor.values["I2C"]["acc_graph"][0],
                self.sensor.values["I2C"]["acc_graph"][1],
                self.sensor.values["I2C"]["acc_graph"][2],
                self.sensor.values["I2C"]["gyro_mod"][0],
                self.sensor.values["I2C"]["gyro_mod"][1],
                self.sensor.values["I2C"]["gyro_mod"][2],
                self.sensor.values["I2C"]["light"],
                value["cpu_percent"],
                self.sensor.values["I2C"]["total_ascent"],
                self.sensor.values["I2C"]["total_descent"],
                ###
                self.record_stats["lap_avg"]["heart_rate"],
                self.record_stats["lap_avg"]["cadence"],
                self.record_stats["lap_avg"]["distance"],
                self.record_stats["lap_avg"]["speed"],
                self.record_stats["lap_avg"]["power"],
                self.record_stats["lap_avg"]["accumulated_power"],
                self.record_stats["lap_avg"]["total_ascent"],
                self.record_stats["lap_avg"]["total_descent"],
                ###
                self.record_stats["entire_avg"]["heart_rate"],
                self.record_stats["entire_avg"]["cadence"],
                self.record_stats["entire_avg"]["speed"],
                self.record_stats["entire_avg"]["power"],
                ###
                self.average["lap"]["cadence"]["count"],
                self.average["lap"]["cadence"]["sum"],
                self.average["entire"]["cadence"]["count"],
                self.average["entire"]["cadence"]["sum"],
                self.average["lap"]["power"]["count"],
                self.average["lap"]["power"]["sum"],
                self.average["entire"]["power"]["count"],
                self.average["entire"]["power"]["sum"],
            ),
        )
        # self.con.commit()
        await self.sql_queue.put((sql))

        self.store_short_log_for_update_track(
            value["distance"],
            self.sensor.values["GPS"]["lat"],
            self.sensor.values["GPS"]["lon"],
            now_time,
        )

        # send online
        if self.config.G_THINGSBOARD_API["STATUS"]:
            self.config.api.send_livetrack_data(quick_send=False)

    def calc_gross(self):
        # elapsed_time
        if self.values["start_time"] is None:
            return
        # [s]
        self.values["elapsed_time"] = int(
            datetime.utcnow().timestamp() - self.values["start_time"]
        )

        # gross_ave_spd
        if self.values["elapsed_time"] == 0:
            return
        # [m]/[s]
        self.values["gross_ave_spd"] = (
            self.sensor.values["integrated"]["distance"] / self.values["elapsed_time"]
        )

        # gross_diff_time
        if self.config.G_GROSS_AVE_SPEED == 0:
            return
        # [km]/[km/h] = +-[h] -> +-[m]
        diff_time = (
            (
                self.sensor.values["integrated"]["distance"] / 1000
                - self.config.G_GROSS_AVE_SPEED * self.values["elapsed_time"] / 3600
            )
            / self.config.G_GROSS_AVE_SPEED
            * 60
        )
        diff_h, diff_m = divmod(abs(diff_time), 60)
        diff_m = int(diff_m)
        diff_time_sign = "+"
        if np.sign(diff_time) < 0:
            diff_time_sign = "-"
        if diff_h == 0 and diff_m == 0:
            diff_time_sign = ""
        self.values["gross_diff_time"] = "{:}{:02.0f}:{:02.0f}".format(
            diff_time_sign, diff_h, diff_m
        )

        # print(self.values['elapsed_time'], self.values['gross_ave_spd'], self.values['gross_diff_time'], round(diff_time,1))

    def resume(self):
        self.cur.execute("SELECT count(*) FROM BIKECOMPUTER_LOG")
        res = self.cur.fetchone()
        if res[0] == 0:
            return

        app_logger.info("resume existing rides...")
        row_all = "\
      timestamp,lap,timer,total_timer_time,\
      distance,accumulated_power,total_ascent,total_descent,altitude,\
      position_lat, position_long, \
      lap_heart_rate,lap_cadence,lap_distance,lap_speed,lap_power,\
      lap_accumulated_power,lap_total_ascent,lap_total_descent,\
      avg_heart_rate,avg_cadence,avg_speed,avg_power,\
      lap_cad_count,lap_cad_sum,lap_power_count,lap_power_sum,\
      avg_cad_count,avg_cad_sum,avg_power_count,avg_power_sum"
        self.cur.execute(
            "\
      SELECT %s FROM BIKECOMPUTER_LOG\
      WHERE total_timer_time = (SELECT MAX(total_timer_time) FROM BIKECOMPUTER_LOG) \
      AND lap = (SELECT MAX(lap) FROM BIKECOMPUTER_LOG)"
            % (row_all)
        )
        value = list(self.cur.fetchone())
        (
            self.last_timestamp,
            self.values["lap"],
            self.values["count_lap"],
            self.values["count"],
        ) = value[0:4]

        sn = self.sensor.values["integrated"]
        i2c = self.sensor.values["I2C"]
        gps = self.sensor.values["GPS"]
        sn["distance"] += value[4]
        sn["accumulated_power"] += value[5]
        i2c["total_ascent"] += value[6]
        i2c["total_descent"] += value[7]
        # None -> np.nan
        (i2c["pre_altitude"], gps["pre_lat"], gps["pre_lon"]) = np.array(
            value[8:11], dtype=np.float32
        )

        index = 11
        for k in self.lap_keys:
            self.record_stats["lap_avg"][k] = value[index]
            index += 1
        for k in ["heart_rate", "cadence", "speed", "power"]:
            self.record_stats["entire_avg"][k] = value[index]
            index += 1
        for k1 in ["lap", "entire"]:
            for k2 in ["cadence", "power"]:
                for k3 in ["count", "sum"]:
                    self.average[k1][k2][k3] = value[index]
                    index += 1
        # print(self.average)

        # get lap
        self.cur.execute("SELECT MAX(LAP) FROM BIKECOMPUTER_LOG")
        max_lap = (self.cur.fetchone())[0]

        # get max
        max_row = "MAX(heart_rate), MAX(cadence), MAX(speed), MAX(power)"
        main_item = ["heart_rate", "cadence", "speed", "power"]
        self.cur.execute("SELECT %s FROM BIKECOMPUTER_LOG" % (max_row))
        max_value = list(self.cur.fetchone())
        for i, k in enumerate(main_item):
            self.record_stats["entire_max"][k] = 0
            if max_value[i] is not None:
                self.record_stats["entire_max"][k] = max_value[i]

        # get lap max
        self.cur.execute(
            "SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s" % (max_row, max_lap)
        )
        max_value = list(self.cur.fetchone())
        for i, k in enumerate(main_item):
            self.record_stats["lap_max"][k] = 0
            if max_value[i] is not None:
                self.record_stats["lap_max"][k] = max_value[i]

        # get pre lap
        if max_lap >= 1:
            self.cur.execute(
                "\
        SELECT %s FROM BIKECOMPUTER_LOG\
        WHERE LAP = %s AND total_timer_time = (\
          SELECT MAX(total_timer_time) FROM BIKECOMPUTER_LOG\
          WHERE LAP = %s)"
                % (row_all, max_lap - 1, max_lap - 1)
            )
            value = list(self.cur.fetchone())

            index = 4
            for k in ["distance", "accumulated_power", "total_ascent", "total_descent"]:
                self.record_stats["pre_lap_max"][k] = value[index]
                index += 1
            index += 3
            for k in self.lap_keys:
                self.record_stats["pre_lap_avg"][k] = value[index]
                index += 1
            # max
            self.cur.execute(
                "SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s"
                % (max_row, max_lap - 1)
            )
            max_value = list(self.cur.fetchone())
            for i, k in enumerate(main_item):
                self.record_stats["pre_lap_max"][k] = max_value[i]
        # print(self.record_stats)
        # print(self.average)

        # start_time
        self.cur.execute("SELECT MIN(timestamp) FROM BIKECOMPUTER_LOG")
        first_row = self.cur.fetchone()
        if first_row[0] is not None:
            self.values["start_time"] = int(
                datetime_myparser(first_row[0]).timestamp() - 1
            )

        # if not self.config.G_IS_RASPI and self.config.G_DUMMY_OUTPUT:
        if self.config.G_DUMMY_OUTPUT:
            self.cur.execute(
                "SELECT position_lat,position_long,distance,gps_track FROM BIKECOMPUTER_LOG"
            )
            self.position_log = np.array(self.cur.fetchall())

    def store_short_log_for_update_track(self, dist, lat, lon, timestamp):
        if not self.short_log_available:
            return
        if np.isnan(lat) or np.isnan(lon):
            return
        if len(self.short_log_dist) and self.short_log_dist[-1] == dist:
            return
        if (len(self.short_log_lat) and self.short_log_lat[-1] == lat) and (
            len(self.short_log_lon) and self.short_log_lon[-1] == lon
        ):
            return
        if len(self.short_log_lat) > self.short_log_limit:
            self.clear_short_log()
            self.short_log_available = False
            return

        self.short_log_lock = True
        self.short_log_dist.append(dist)
        self.short_log_lat.append(lat)
        self.short_log_lon.append(lon)
        self.short_log_timestamp.append(timestamp)
        self.short_log_lock = False
        self.short_log_available = True
        # print("append", len(self.short_log_dist), len(self.short_log_lat), len(self.short_log_lon))

    def clear_short_log(self):
        while self.short_log_lock:
            app_logger.info("locked: clear_short_log")
            time.sleep(0.02)
        self.short_log_dist = []
        self.short_log_lat = []
        self.short_log_lon = []
        self.short_log_timestamp = []

    def update_track(self, timestamp):
        lon = np.array([])
        lat = np.array([])
        timestamp_new = timestamp
        # t = datetime.utcnow()

        timestamp_delta = None
        if timestamp is not None:
            timestamp_delta = (datetime.utcnow() - timestamp).total_seconds()

        # make_tmp_db = False
        lat_raw = np.array([])
        lon_raw = np.array([])
        dist_raw = np.array([])

        # get values from short_log to db in logging
        if timestamp_delta is not None and self.short_log_available:
            while self.short_log_lock:
                app_logger.info("locked: get values")
                time.sleep(0.02)
            lat_raw = np.array(self.short_log_lat)
            lon_raw = np.array(self.short_log_lon)
            dist_raw = np.array(self.short_log_dist)
            if len(self.short_log_lon):
                timestamp_new = self.short_log_timestamp[-1]
            self.clear_short_log()
            self.short_log_available = True
        # get values from copied db when initial execution or migration from short_log to db in logging
        else:
            db_file = self.config.G_LOG_DB + ".tmp"
            shutil.copy(self.config.G_LOG_DB, db_file)

            query = (
                "SELECT distance,position_lat,position_long FROM BIKECOMPUTER_LOG "
                + "WHERE position_lat is not null AND position_long is not null "
                + 'and typeof(position_lat) = "real" and typeof(position_long) = "real"'
            )
            if timestamp is not None:
                query = query + "AND timestamp > '%s'" % timestamp

            con = sqlite3.connect(db_file)
            cur = con.cursor()
            cur.execute(query)
            res_array = np.array(cur.fetchall())
            if len(res_array.shape) and res_array.shape[0] > 0:
                dist_raw = res_array[:, 0].astype("float32")  # [m]
                lat_raw = res_array[:, 1].astype("float32")
                lon_raw = res_array[:, 2].astype("float32")

            # timestamp
            cur.execute("SELECT MAX(timestamp) FROM BIKECOMPUTER_LOG")
            first_row = cur.fetchone()
            if first_row[0] is not None:
                timestamp_new = datetime_myparser(first_row[0])

            cur.close()
            con.close()
            os.remove(db_file)
            self.short_log_available = True

        # print("lat_raw", len(lat_raw))
        if len(lat_raw) and (len(lat_raw) == len(lon_raw) == len(dist_raw)):
            # downsampling
            try:
                cond = np.array(
                    rdp(
                        np.column_stack([lon_raw, lat_raw]),
                        epsilon=0.0001,
                        return_mask=True,
                    )
                )
                lat = lat_raw[cond]
                lon = lon_raw[cond]
            except:
                lat = lat_raw
                lon = lon_raw

        if timestamp is None:
            timestamp_new = datetime.utcnow()

        # print("\tlogger_core : update_track(new) ", (datetime.utcnow()-t).total_seconds(), "sec")

        return timestamp_new, lon, lat
