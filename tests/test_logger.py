import unittest

from modules.logger.logger_csv import LoggerCsv
from modules.logger.logger_fit import LoggerFit


class LocalConfig:
    G_LOG_DB = "tests/data/log.db-Heart_of_St._Johns_Peninsula_Ride"
    G_LOG_DIR = "/tmp"  # nosec
    G_UNIT_ID_HEX = 0x12345678

    G_LOG_START_DATE = None


class TestLoggerCsv(unittest.TestCase):
    def test_write_log(self):
        config = LocalConfig()
        logger = LoggerCsv(config)
        result = logger.write_log()
        self.assertTrue(result)
        self.assertEqual(config.G_LOG_START_DATE, "2023-09-28_22-39-13")


class TestLoggerFit(unittest.TestCase):
    def test_write_logs(self):
        config = LocalConfig()
        logger = LoggerFit(config)
        result = logger.write_log_cython()
        self.assertTrue(result)
        self.assertEqual(config.G_LOG_START_DATE, "2023-09-28_22-39-13")

        filename = f"{config.G_LOG_DIR}/{config.G_LOG_START_DATE}.fit"

        with open(filename, "rb") as f:
            cython_data = f.read()

        result = logger.write_log_python()
        self.assertTrue(result)
        self.assertEqual(config.G_LOG_START_DATE, "2023-09-28_22-39-13")

        with open(filename, "rb") as f:
            python_data = f.read()

        self.assertEqual(cython_data, python_data)
