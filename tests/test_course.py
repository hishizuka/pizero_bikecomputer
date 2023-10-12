import unittest
from tempfile import NamedTemporaryFile

from modules.course import Course


class Config:
    G_COURSE_INDEXING = False
    G_COURSE_FILE_PATH = None

    G_GPS_KEEP_ON_COURSE_CUTOFF = 60

    # for search point on course
    G_GPS_ON_ROUTE_CUTOFF = 50  # [m] #generate from course
    G_GPS_SEARCH_RANGE = 6  # [km] #100km/h -> 27.7m/s
    G_GPS_AZIMUTH_CUTOFF = 60  # degree(30/45/90): 0~G_GPS_AZIMUTH_CUTOFF, (360-G_GPS_AZIMUTH_CUTOFF)~G_GPS_AZIMUTH_CUTOFF

    # Graph color by slope
    G_CLIMB_DISTANCE_CUTOFF = 0.3  # [km]
    G_CLIMB_GRADE_CUTOFF = 2  # [%]
    G_SLOPE_CUTOFF = (1, 3, 6, 9, 12, float("inf"))  # by grade
    G_SLOPE_COLOR = (
        (128, 128, 128),  # gray(base)
        (0, 255, 0),  # green
        (255, 255, 0),  # yellow
        (255, 128, 0),  # orange
        (255, 0, 0),  # red
        (128, 0, 0),  # dark red
    )
    G_CLIMB_CATEGORY = [
        {"volume": 8000, "name": "Cat4"},
        {"volume": 16000, "name": "Cat3"},
        {"volume": 32000, "name": "Cat2"},
        {"volume": 64000, "name": "Cat1"},
        {"volume": 80000, "name": "HC"},
    ]

    G_THINGSBOARD_API = {"STATUS": False}

    def __init__(self, indexing=False):
        self.G_COURSE_INDEXING = indexing
        self.G_COURSE_FILE_PATH = NamedTemporaryFile().name


class TestCourse(unittest.TestCase):
    # TODO find/create a file where time is not set so distance is kept empty with no_indexing
    # def test_load_no_indexing(self):
    #     config = Config()
    #     course = Course(config)
    #     course.load(file="tests/data/tcx/Heart_of_St._Johns_Peninsula_Ride.tcx")
    #
    #     # downsampled from 184 to 31 points
    #     self.assertEqual(len(course.latitude), 31)
    #     self.assertEqual(len(course.course_points.latitude), 18)
    #
    #     # distance was not set since there's no indexing
    #     self.assertEqual(len(course.course_points.distance), 0)
    #
    #     self.assertEqual(len(course.colored_altitude), 31)

    def test_load_with_tcx_indexing(self):
        config = Config(indexing=True)
        course = Course(config)
        course.load(file="tests/data/tcx/Heart_of_St._Johns_Peninsula_Ride.tcx")

        # downsampled from 184 to 31 points
        self.assertEqual(len(course.latitude), 31)
        self.assertEqual(len(course.course_points.latitude), 18)
        self.assertEqual(len(course.course_points.distance), 18)

    def test_load_insert_course_point(self):
        config = Config(indexing=True)
        course = Course(config)
        course.load(
            file="tests/data/tcx/Heart_of_St._Johns_Peninsula_Ride-CP-Removed.tcx"
        )

        self.assertEqual(len(course.course_points.latitude), 18)
        self.assertEqual(len(course.course_points.distance), 18)

        self.assertEqual(course.course_points.name[0], "Start")
        self.assertEqual(course.course_points.latitude[0], 45.57873)
        self.assertEqual(course.course_points.longitude[0], -122.71318)
        self.assertEqual(course.course_points.distance[0], 0.0)

        self.assertEqual(course.course_points.name[-1], "End")
        self.assertEqual(course.course_points.latitude[-1], 45.5788)
        self.assertEqual(course.course_points.longitude[-1], -122.7135)
        self.assertEqual(course.course_points.distance[-1], 12.286501)
