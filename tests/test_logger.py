import unittest

from modules.logger.logger_csv import LoggerCsv
from modules.logger.logger_fit import LoggerFit


class LocalConfig:
    G_LOG_DB = "tests/data/log.db-Heart_of_St._Johns_Peninsula_Ride"
    G_LOG_DIR = "/tmp"  # nosec
    G_UNIT_ID_HEX = 0x12345678


class TestLogger(unittest.TestCase):
    def test_logger_fit_cython(self):
        logger = LoggerFit(LocalConfig)
        result = logger.write_log_cython()
        self.assertTrue(result)

    def test_logger_fit_python(self):
        logger = LoggerFit(LocalConfig)
        result = logger.write_log_python()
        self.assertTrue(result)

    def test_logger_fit_csv(self):
        logger = LoggerCsv(LocalConfig)
        result = logger.write_log()
        self.assertTrue(result)
