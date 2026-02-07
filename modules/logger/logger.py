import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class LoggerCommandConfig:
    G_LOG_DB: str
    G_LOG_DIR: str
    G_UNIT_ID_HEX: int = 0x12345678
    G_UPLOAD_FILE: str = ""


class Logger:
    config = None
    _LOG_DB_NAME_PATTERN = re.compile(
        r"^log\.db-(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})$"
    )

    def __init__(self, config):
        self.config = config

    @classmethod
    def resolve_db_path(cls, db_path):
        path = Path(db_path)
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    @classmethod
    def create_command_config(cls, db_path, unit_id_hex=0x12345678):
        path = Path(db_path)
        return LoggerCommandConfig(
            G_LOG_DB=str(path),
            G_LOG_DIR=str(path.parent),
            G_UNIT_ID_HEX=unit_id_hex,
        )

    @classmethod
    def get_output_stem(cls, db_path):
        db_name = Path(db_path).name
        match = cls._LOG_DB_NAME_PATTERN.match(db_name)
        if match:
            return match.group(1)
        if db_name.endswith(".db"):
            return db_name[:-3]
        return db_name

    @classmethod
    def get_default_output_path(cls, db_path, extension):
        suffix = extension if extension.startswith(".") else f".{extension}"
        output_stem = cls.get_output_stem(db_path)
        return Path(db_path).with_name(f"{output_stem}{suffix}")

    @staticmethod
    def _to_utc_datetime(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if isinstance(value, str):
            value = value.replace("Z", "+00:00")
            date_value = datetime.fromisoformat(value)
            if date_value.tzinfo is None:
                return date_value.replace(tzinfo=timezone.utc)
            return date_value.astimezone(timezone.utc)
        raise TypeError(f"Unsupported datetime value type: {type(value)}")

    def get_db_start_end_dates(self):
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
        cur.close()
        con.close()

        if first_row is None:
            return None, None

        start_date, end_date = first_row
        return self._to_utc_datetime(start_date), self._to_utc_datetime(end_date)
