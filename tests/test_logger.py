import os
import tempfile
import unittest
from datetime import datetime, timezone

from modules.logger.logger_csv import LoggerCsv
from modules.logger.logger_fit import LoggerFit


class LocalConfig:
    G_LOG_DB = "tests/data/log.db-Heart_of_St._Johns_Peninsula_Ride"
    G_UNIT_ID_HEX = 0x12345678


class TestLoggerCsv(unittest.TestCase):
    def test_write_log(self):
        config = LocalConfig()
        logger = LoggerCsv(config)
        _, path = tempfile.mkstemp()

        try:
            result = logger.write_log(path)
        finally:
            os.remove(path)

        self.assertTrue(result)


class TestLoggerFit(unittest.TestCase):
    def test_write_logs(self):
        config = LocalConfig()
        logger = LoggerFit(config)

        start = datetime(2023, 9, 28, 20, 39, 13, tzinfo=timezone.utc)
        end = datetime(2023, 9, 28, 21, 10, 53, tzinfo=timezone.utc)

        _, path = tempfile.mkstemp()

        try:
            result = logger.write_log_cython(path, start, end)

            self.assertTrue(result)

            with open(path, "rb") as f:
                cython_data = f.read()
        finally:
            os.remove(path)

        _, path = tempfile.mkstemp()

        try:
            result = logger.write_log_python(path, start, end)

            self.assertTrue(result)

            with open(path, "rb") as f:
                python_data = f.read()

        finally:
            os.remove(path)

        self.assertEqual(cython_data, python_data)
