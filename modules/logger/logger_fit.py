import datetime
import os
import sqlite3
import struct
import time

from logger import app_logger
from modules.utils.date import datetime_myparser
from .logger import Logger

# cython
MODE = "Python"

try:
    import pyximport

    pyximport.install()
    from .cython.logger_fit import (
        write_log_cython,
        set_config,
        get_upload_file_name,
        get_start_date_str,
    )

    MODE = "Cython"
except ImportError:
    pass


class config_local:
    G_LOG_DB = "log/log.db"
    G_LOG_DIR = "log"
    G_UNIT_ID_HEX = 0x12345678


class LoggerFit(Logger):
    mode = None
    epoch_datetime = datetime.datetime(1989, 12, 31, 0, 0, 0, 0)
    profile = {
        0: {
            "name": "file_id",
            "field": {
                0: ("type", "enum"),  # file
                1: ("manufacturer", "uint16"),  # manufacturer
                2: ("product", "uint16"),  # or garmin_product
                3: ("serial_number", "uint32z"),
                4: ("time_created", "uint32"),  # date_time
                5: ("number", "uint16"),
                7: ("unknown_7", "uint32"),  # must need. what's this?
                8: ("product_name", "string"),  # string
            },
        },
        18: {
            "name": "session",
            "field": {
                253: ("timestamp", "uint32"),
                2: ("start_time", "uint32"),  # date_time
                5: ("sport", "enum"),
                7: ("total_elapsed_time", "uint32", 1000),  # with scale
                8: ("total_timer_time", "uint32", 1000),  # with scale
                9: ("total_distance", "uint32", 100),  # with scale
                14: ("avg_speed", "uint16", 1000),  # with scale
                15: ("max_speed", "uint16", 1000),  # with scale
                16: ("avg_heart_rate", "uint8"),
                17: ("max_heart_rate", "uint8"),
                18: ("avg_cadence", "uint8"),
                19: ("max_cadence", "uint8"),
                20: ("avg_power", "uint16"),
                21: ("max_power", "uint16"),
                22: ("total_ascent", "uint16"),
                23: ("total_descent", "uint16"),
                26: ("num_laps", "uint16"),
                48: ("total_work", "uint32"),
            },
        },
        19: {
            "name": "lap",
            "field": {
                253: ("timestamp", "uint32"),
                2: ("start_time", "uint32"),  # date_time
                7: ("total_elapsed_time", "uint32", 1000),  # with scale
                8: ("total_timer_time", "uint32", 1000),  # with scale
                9: ("total_distance", "uint32", 100),  # with scale
                13: ("avg_speed", "uint16", 1000),  # with scale
                14: ("max_speed", "uint16", 1000),  # with scale
                15: ("avg_heart_rate", "uint8"),
                16: ("max_heart_rate", "uint8"),
                17: ("avg_cadence", "uint8"),
                18: ("max_cadence", "uint8"),
                19: ("avg_power", "uint16"),
                20: ("max_power", "uint16"),
                21: ("total_ascent", "uint16"),
                22: ("total_descent", "uint16"),
                42: ("total_work", "uint32"),
            },
        },
        20: {
            "name": "record",
            "field": {
                253: ("timestamp", "uint32"),
                0: ("position_lat", "sint32"),  # need conversion to semicircles
                1: ("position_long", "sint32"),  # need conversion to semicircles
                2: ("altitude", "uint16", 5, 500),  # with scale and offset
                3: ("heart_rate", "uint8"),
                4: ("cadence", "uint8"),
                5: ("distance", "uint32", 100),  # with scale
                6: ("speed", "uint16", 1000),  # with scale
                7: ("power", "uint16"),
                13: ("temperature", "sint8"),
                29: ("accumulated_power", "uint32"),
            },
        },
        21: {"name": "event", "field": {}},
        34: {
            "name": "activity",
            "field": {
                0: ("total_timer_time", "uint32", 1000),
                1: ("num_sessions", "uint16"),
                2: ("type", "enum"),
                3: ("event", "enum"),
                4: ("event_type", "enum"),
                5: ("local_timestamp", "uint32"),
                6: ("event_group", "uint8"),
                253: ("timestamp", "uint32"),
            },
        },
        49: {
            "name": "file_creator",
            "field": {
                0: ("software_version", "uint16"),
                1: ("hardware_version", "uint8"),
            },
        },
    }
    local_num = {}
    struct_def_cache = {}
    # for getSummary (session, lap)
    sql = {
        # session
        18: {
            253: ("MAX(timestamp)"),  # time stamp
            2: ("MIN(timestamp)"),  # start_time
            7: ("MAX(timestamp),MIN(timestamp)"),  # total_elapsed_time
            8: ("MAX(total_timer_time)"),  # total_timer_time
            9: ("MAX(distance)"),
            14: ("avg_speed"),
            15: ("MAX(speed)"),
            16: ("avg_heart_rate"),
            17: ("MAX(heart_rate)"),
            18: ("avg_cadence"),
            19: ("MAX(cadence)"),
            20: ("avg_power"),
            21: ("MAX(power)"),
            22: ("MAX(total_ascent)"),
            23: ("MAX(total_descent)"),
            26: ("MAX(lap)"),
            48: ("MAX(accumulated_power)"),
        },
        # lap
        19: {
            253: ("MAX(timestamp)"),  # time stamp
            2: ("MIN(timestamp)"),  # start_time
            7: ("MAX(timestamp),MIN(timestamp)"),  # total_elapsed_time
            8: ("MAX(timer)"),  # total_timer_time
            9: ("MAX(lap_distance)"),
            13: ("lap_speed"),
            14: ("MAX(speed)"),
            15: ("lap_heart_rate"),
            16: ("MAX(heart_rate)"),
            17: ("lap_cadence"),
            18: ("MAX(cadence)"),
            19: ("lap_power"),
            20: ("MAX(power)"),
            21: ("MAX(lap_total_ascent)"),
            22: ("MAX(lap_total_descent)"),
            42: ("MAX(lap_accumulated_power)"),
        },
    }

    def __init__(self, config):
        self.config = config
        self.reset()
        self.mode = MODE
        if MODE == "Cython":
            set_config(config)

    def reset(self):
        self.fit_data = []
        self.local_num = {
            # 0:{"message_num":0,"field":(3,4,1,2,0)}, #file_id (2 is product id)
            0: {"message_num": 0, "field": (3, 4, 1, 0)},  # file_id (7, 5)
            1: {"message_num": 49, "field": (0, 1)},  # file_creator
        }
        self.struct_def_cache = {}

    @staticmethod
    def base_type_id_from_string(base_type_name):
        return {
            "enum": 0x00,  # 0
            "sint8": 0x01,  # 1
            "uint8": 0x02,  # 2
            "bool": 0x02,  # 2
            "sint16": 0x83,  # 3
            "uint16": 0x84,  # 4
            "sint32": 0x85,  # 5
            "uint32": 0x86,  # 6
            "string": 0x07,  # 7
            "float32": 0x88,  # 8
            "float64": 0x89,  # 9
            "uint8z": 0x0A,  # 10
            "uint16z": 0x8B,  # 11
            "uint32z": 0x8C,  # 12
            "byte": 0x0D,
        }[base_type_name]

    @staticmethod
    def base_type_size_from_id(base_type_id):
        #       0 1 2 3 4 5 6 7 8 910111213
        return [1, 1, 1, 2, 2, 4, 4, 1, 4, 8, 1, 2, 4, 1][base_type_id & 0xF]

    @staticmethod
    def base_type_format_from_id(base_type_id):
        #       01234567890123
        return "BbBhHiIsfdBHIs"[base_type_id & 0xF]

    def write(self, out):
        self.fit_data.append(out)

    # referenced by https://opensource.quarq.us/fit_json/
    def write_log(self):
        # try Cython if available/resolve to pure python if writing fails
        if MODE == "Cython" and self.write_log_cython():
            return True
        return self.write_log_python()

    def write_log_cython(self):
        res = write_log_cython(self.config.G_LOG_DB)
        if res:
            self.config.G_UPLOAD_FILE = get_upload_file_name()
            self.config.G_LOG_START_DATE = get_start_date_str()
        return res

    def write_log_python(self):
        # make sure crc16 is imported is we resolve to using python code
        from .cython.crc16_p import crc16

        ## SQLite
        con = sqlite3.connect(
            self.config.G_LOG_DB,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        sqlite3.dbapi2.converters["DATETIME"] = sqlite3.dbapi2.converters["TIMESTAMP"]
        cur = con.cursor()

        # get start_date
        # get datetime object (timestamp)
        cur.execute("SELECT timestamp, MIN(timestamp) FROM BIKECOMPUTER_LOG")
        first_row = cur.fetchone()
        if first_row is not None:
            start_date = first_row[0]
        else:
            return False
        # get end_date
        cur.execute("SELECT timestamp, MAX(timestamp) FROM BIKECOMPUTER_LOG")
        first_row = cur.fetchone()
        if first_row is not None:
            end_date = first_row[0]
        else:
            return False

        local_message_num = 0

        # file_id
        app_logger.debug("file_id")
        self.write_definition(local_message_num)
        struct_def = self.get_struct_def(local_message_num)
        self.write(
            struct.pack(
                struct_def,
                self.config.G_UNIT_ID_HEX,  # serial_number: XXXXXXXXXX
                self.get_epoch_time(start_date),  # timestamp
                255,  # manufacturer (255: development)
                # 2530,       #garmin product (Edge 820)
                4,
            )
        )  # type

        # file_creator
        local_message_num += 1
        app_logger.debug("file_creator")
        self.write_definition(local_message_num)
        struct_def = self.get_struct_def(local_message_num)
        self.write(struct.pack("<1H1B", 100, 1))

        # record
        app_logger.debug("record")
        # get Max Lap
        cur.execute("SELECT MAX(lap) FROM BIKECOMPUTER_LOG")
        max_lap = (cur.fetchone())[0]

        # get log by laps
        message_num = 20
        record_row = []
        record_index = []
        for k, v in self.profile[message_num]["field"].items():
            record_row.append(v[0])
            record_index.append(k)
        record_row = ",".join(record_row)

        for lap_num in range(max_lap + 1):
            cur.execute(
                "SELECT COUNT(lap) FROM BIKECOMPUTER_LOG WHERE lap = %s" % (lap_num)
            )
            if (cur.fetchone())[0] == 0:
                continue

            for row in cur.execute(
                "SELECT %s FROM BIKECOMPUTER_LOG WHERE lap = %s" % (record_row, lap_num)
            ):
                # search definition in localNum
                available_fields = []
                available_data = []
                if None in row:
                    for i, v in enumerate(row):
                        if v is None:
                            continue
                        available_fields.append(record_index[i])
                        available_data.append(
                            self.convertValue((v,), message_num, record_index[i])
                        )

                    # available_fields = [j for i, j in zip(row, record_index) if i is not None]
                    # available_data = list(map(self.convertValue, [(i,) for i in row if i is not None], [message_num]*len(available_fields), available_fields))

                    # available_data_gen = [(self.convertValue((i,),message_num,j), j) for i, j in zip(row, record_index) if i is not None]
                    # available_fields = [row[1] for row in available_data_gen]
                    # available_data = [row[0] for row in available_data_gen]
                else:
                    available_fields = record_index
                    available_data = list(
                        map(
                            self.convertValue,
                            [(i,) for i in row],
                            [message_num] * len(available_fields),
                            available_fields,
                        )
                    )

                l_num = self.get_local_message_num(message_num, available_fields)
                l_num_used = True
                if l_num == -1:
                    l_num_used = False
                    # write header if need
                    local_message_num = (local_message_num + 1) % 16
                    self.local_num[local_message_num] = {
                        "message_num": message_num,
                        "field": available_fields,
                    }
                    self.write_definition(local_message_num)
                    l_num = local_message_num
                # write data
                struct_def = self.get_struct_def(l_num, l_num_used)

                try:
                    self.write(struct.pack(struct_def, *available_data))
                except Exception:  # noqa
                    app_logger.exception("Failed writing struct")
                    app_logger.error(f"l_num = {l_num} message_num = {message_num}")
                    app_logger.error(available_fields)
                    app_logger.error(struct_def)
                    app_logger.error(available_data)
                    cur.close()
                    con.close()
                    return False

            # lap: 19
            app_logger.debug("lap")
            local_message_num = self.get_summary(19, local_message_num, lap_num, cur)

        # session: 18
        app_logger.debug("session")
        local_message_num = self.get_summary(18, local_message_num, 0, cur)

        # activity: 34
        app_logger.debug("activity")
        local_message_num = (local_message_num + 1) % 16
        self.local_num[local_message_num] = {
            "message_num": 34,
            "field": (253, 0, 1, 2, 3, 4, 5),
        }
        self.write_definition(local_message_num)
        struct_def = self.get_struct_def(local_message_num)
        offset = time.localtime().tm_gmtoff
        end_date_epochtime = self.get_epoch_time(end_date)
        self.write(
            struct.pack(
                struct_def,
                end_date_epochtime,
                (int(end_date.timestamp()) - int(start_date.timestamp())) * 1000,
                1,  # num of sessions: 1(fix)
                0,  # activity_type: general
                26,  # event: activity
                1,  # event_type: stop
                end_date_epochtime + offset,
            )
        )
        cur.close()
        con.close()

        ################
        # write fit file
        ################

        startdate_local = start_date + datetime.timedelta(seconds=offset)
        self.config.G_LOG_START_DATE = startdate_local.strftime("%Y%m%d%H%M%S")
        filename = os.path.join(
            self.config.G_LOG_DIR, f"{self.config.G_LOG_START_DATE}.fit"
        )
        # filename = "test.fit"
        fd = open(filename, "wb")
        write_data = b"".join(self.fit_data)

        # make file header
        file_header = struct.pack(
            "<BBHI4c",
            14,  # size
            0x10,  # protocol ver
            # 0x0514, #profile ver
            2014,  # profile ver
            len(write_data),
            b".",
            b"F",
            b"I",
            b"T",
        )

        # make crc
        crc = struct.pack("<H", crc16(file_header))
        fd.write(file_header)

        fd.write(crc)
        fd.write(write_data)
        crc = struct.pack("<H", crc16(file_header + crc + write_data))

        fd.write(crc)
        fd.close()

        # success
        self.reset()
        self.config.G_UPLOAD_FILE = filename
        return True

    def write_definition(self, local_message_num):
        m_num = self.local_num[local_message_num]["message_num"]
        l_field = self.local_num[local_message_num]["field"]
        # write definition header(0x40)
        self.write((local_message_num + 0x40).to_bytes(1, "little"))
        self.write(struct.pack("<BBHB", 0, 0, m_num, len(l_field)))
        # write field definition
        for f_id in l_field:
            f_type = self.profile[m_num]["field"][f_id][1]
            base_type_id = self.base_type_id_from_string(f_type)
            base_type_size = self.base_type_size_from_id(base_type_id)
            self.write(struct.pack("<BBB", f_id, base_type_size, base_type_id))

    def get_struct_def(self, local_message_num, l_num_used=False):
        if l_num_used and local_message_num in self.struct_def_cache:
            struct_def = self.struct_def_cache[local_message_num]
        else:
            m_num = self.local_num[local_message_num]["message_num"]
            struct_def = "<"
            for f_id in self.local_num[local_message_num]["field"]:
                f_type = self.profile[m_num]["field"][f_id][1]
                base_type_id = self.base_type_id_from_string(f_type)
                struct_def += "1" + self.base_type_format_from_id(base_type_id)
            self.struct_def_cache[local_message_num] = struct_def
        # write data header(0x00)
        self.write((local_message_num + 0x00).to_bytes(1, "little"))
        return struct_def

    def get_local_message_num(self, message_num, field):
        index = -1
        for i, v in self.local_num.items():
            if v["message_num"] == message_num and v["field"] == field:
                index = i
        return index

    def convertValue(self, v, message_num, defnum):
        field = self.profile[message_num]["field"][defnum]
        value = v[0]
        if field[0] in ["position_lat", "position_long"]:
            try:
                value = v[0] / 180 * (2**31)
            except:
                value = 0
        elif message_num in [18, 19] and field[0] in [
            "timestamp",
            "local_timestamp",
            "start_time",
        ]:
            # sqlite converter return not datetime but str when SQL includes MAX, MIN, etc
            value = self.get_epoch_time_str(v[0])
        elif field[0] in ["timestamp", "local_timestamp", "start_time"]:
            value = self.get_epoch_time(v[0])
        elif field[0] == "total_elapsed_time":  # message_num in [18, 19]
            value = field[2] * int(
                (datetime_myparser(v[0]) - datetime_myparser(v[1])).total_seconds()
            )
        elif len(field) == 4:  # with scale and offset (altitude)
            value = field[2] * (v[0] + field[3])
        elif len(field) == 3:  # with scale
            value = field[2] * v[0]
        return int(value)

    def get_summary(self, message_num, local_message_num, lap_num, cur):
        # get statistics
        lap_fields = []
        lap_data = []
        lap_sql = self.sql[message_num]
        for k in lap_sql.keys():
            if message_num == 19:  # lap
                if (
                    "MAX" not in lap_sql[k]
                    and "MIN" not in lap_sql[k]
                    and "AVG" not in lap_sql[k]
                ):
                    cur.execute(
                        "\
            SELECT %s FROM BIKECOMPUTER_LOG\
            WHERE LAP = %s AND TIMER = (\
              SELECT MAX(TIMER) FROM BIKECOMPUTER_LOG WHERE LAP = %s)"
                        % (lap_sql[k], lap_num, lap_num)
                    )
                else:
                    cur.execute(
                        "SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s"
                        % (lap_sql[k], lap_num)
                    )
            elif message_num == 18:  # session
                if "avg_" in lap_sql[k]:
                    cur.execute(
                        "\
            SELECT %s FROM BIKECOMPUTER_LOG\
            WHERE total_timer_time = (\
              SELECT MAX(total_timer_time) FROM BIKECOMPUTER_LOG)"
                        % (lap_sql[k])
                    )
                else:
                    cur.execute("SELECT %s FROM BIKECOMPUTER_LOG" % (lap_sql[k]))
            v = list((cur.fetchone()))
            if not len(v) or v[0] is None:
                continue
            lap_fields.append(k)
            lap_data.append(self.convertValue(v, message_num, k))
        # add sport = 2(cycling)
        if message_num == 18:
            lap_fields.append(5)
            lap_data.append(2)
        app_logger.debug(lap_fields, lap_data)
        l_num = self.get_local_message_num(message_num, lap_fields)
        if l_num == -1:
            # write header if needed
            local_message_num = (local_message_num + 1) % 16
            self.local_num[local_message_num] = {
                "message_num": message_num,
                "field": lap_fields,
            }
            self.write_definition(local_message_num)
            l_num = local_message_num

        # write data
        struct_def = self.get_struct_def(l_num)
        try:
            self.write(struct.pack(struct_def, *lap_data))
        except Exception:  # noqa
            app_logger.exception("Failed writing struct")
            app_logger.error(f"l_num = {l_num} message_num = {message_num}")
            app_logger.error(lap_fields)
            app_logger.error(struct_def)
            app_logger.error(lap_data)
            return -1
        return local_message_num

    def get_epoch_time(self, nowdate):
        seconds = int((nowdate - self.epoch_datetime).total_seconds())
        return seconds

    def get_epoch_time_str(self, strtime):
        return self.get_epoch_time(datetime_myparser(strtime))


if __name__ == "__main__":
    # from line_profiler import LineProfiler
    c = config_local()
    d = LoggerFit(c)
    d.write_log()

    # prf = LineProfiler()
    # prf.add_function(l.convertValue)
    # prf.add_function(l.getEpochTime)
    # prf.add_function(l.get_struct_def)
    # prf.add_function(l.crc)
    # prf.runcall(l.writeLog)
    # prf.print_stats()
