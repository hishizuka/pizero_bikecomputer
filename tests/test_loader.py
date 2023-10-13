import unittest

from modules.loaders.tcx import TcxLoader


class TestLoader(unittest.TestCase):
    def test_tcx(self):
        data_course, data_course_points = TcxLoader.load_file(
            "tests/data/tcx/Mt_Angel_Abbey.tcx"
        )
        self.assertEqual(len(data_course["latitude"]), 946)
        self.assertEqual(len(data_course_points["latitude"]), 42)

        # validate that course_point distance was set correctly
        self.assertTrue(len(data_course_points["distance"]))
