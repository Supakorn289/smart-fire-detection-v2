import unittest
from geometry import pixel_to_bearing, gps_from_bearing_distance
class GeometryTests(unittest.TestCase):
    def test_center(self):
        self.assertAlmostEqual(pixel_to_bearing(90, 640, 1280, 56.14), 90.0, places=6)
    def test_left_of_north_wraps(self):
        self.assertAlmostEqual(pixel_to_bearing(0, 0, 1280, 60.0), 330.0, places=6)
    def test_right_of_north(self):
        self.assertAlmostEqual(pixel_to_bearing(0, 1280, 1280, 60.0), 30.0, places=6)
    def test_gps_north(self):
        lat1, lon1 = 18.79, 98.98
        lat2, lon2 = gps_from_bearing_distance(lat1, lon1, 100.0, 0.0)
        self.assertGreater(lat2, lat1)
        self.assertAlmostEqual(lon2, lon1, places=6)
if __name__ == '__main__': unittest.main()
