import math
import unittest

from geometry import (
    WGS84_A_M,
    WGS84_F,
    bearing_to_compass,
    gps_from_bearing_distance,
    normalize_bearing,
    normalize_longitude,
    pixel_to_bearing,
)


class GeometryTests(unittest.TestCase):

    # ========================================================
    # Pixel -> Bearing regression
    # ========================================================

    def test_center(self):
        self.assertAlmostEqual(
            pixel_to_bearing(
                90,
                640,
                1280,
                56.14,
            ),
            90.0,
            places=6,
        )

    def test_left_of_north_wraps(self):
        self.assertAlmostEqual(
            pixel_to_bearing(
                0,
                0,
                1280,
                60.0,
            ),
            330.0,
            places=6,
        )

    def test_right_of_north(self):
        self.assertAlmostEqual(
            pixel_to_bearing(
                0,
                1280,
                1280,
                60.0,
            ),
            30.0,
            places=6,
        )

    # ========================================================
    # WGS84
    # ========================================================

    def test_wgs84_constants(self):

        self.assertEqual(
            WGS84_A_M,
            6378137.0,
        )

        self.assertAlmostEqual(
            WGS84_F,
            1.0 / 298.257223563,
            places=15,
        )

    # ========================================================
    # Vincenty Direct
    # ========================================================

    def test_gps_zero_distance(self):

        lat1 = 18.79
        lon1 = 98.98

        lat2, lon2 = (
            gps_from_bearing_distance(
                lat1,
                lon1,
                0.0,
                123.0,
            )
        )

        self.assertEqual(
            lat2,
            lat1,
        )

        self.assertAlmostEqual(
            lon2,
            lon1,
            places=12,
        )

    def test_gps_north(self):

        lat1 = 18.79
        lon1 = 98.98

        lat2, lon2 = (
            gps_from_bearing_distance(
                lat1,
                lon1,
                100.0,
                0.0,
            )
        )

        self.assertGreater(
            lat2,
            lat1,
        )

        self.assertAlmostEqual(
            lon2,
            lon1,
            places=10,
        )

    def test_gps_east(self):

        lat1 = 18.79
        lon1 = 98.98

        lat2, lon2 = (
            gps_from_bearing_distance(
                lat1,
                lon1,
                100.0,
                90.0,
            )
        )

        self.assertGreater(
            lon2,
            lon1,
        )

        self.assertLess(
            abs(lat2 - lat1),
            0.00001,
        )

    def test_gps_south(self):

        lat1 = 18.79
        lon1 = 98.98

        lat2, lon2 = (
            gps_from_bearing_distance(
                lat1,
                lon1,
                100.0,
                180.0,
            )
        )

        self.assertLess(
            lat2,
            lat1,
        )

    def test_gps_west(self):

        lat1 = 18.79
        lon1 = 98.98

        lat2, lon2 = (
            gps_from_bearing_distance(
                lat1,
                lon1,
                100.0,
                270.0,
            )
        )

        self.assertLess(
            lon2,
            lon1,
        )

    def test_wgs84_reference(self):
        """
        Published WGS84 direct-geodesic regression case.
        """

        lat2, lon2 = (
            gps_from_bearing_distance(
                40.63972222,
                -73.77888889,
                5_850_000.0,
                53.5,
            )
        )

        self.assertAlmostEqual(
            lat2,
            49.01467,
            places=5,
        )

        self.assertAlmostEqual(
            lon2,
            2.56106,
            places=5,
        )

    # ========================================================
    # Validation
    # ========================================================

    def test_negative_distance(self):

        with self.assertRaises(
            ValueError
        ):
            gps_from_bearing_distance(
                18.79,
                98.98,
                -1.0,
                0.0,
            )

    def test_invalid_latitude(self):

        with self.assertRaises(
            ValueError
        ):
            gps_from_bearing_distance(
                91.0,
                98.98,
                10.0,
                0.0,
            )

    def test_nonfinite_input(self):

        with self.assertRaises(
            ValueError
        ):
            gps_from_bearing_distance(
                math.nan,
                98.98,
                10.0,
                0.0,
            )

    def test_longitude_normalization(self):

        self.assertAlmostEqual(
            normalize_longitude(181),
            -179.0,
            places=12,
        )

        self.assertAlmostEqual(
            normalize_longitude(-181),
            179.0,
            places=12,
        )

    def test_bearing_normalization(self):

        self.assertEqual(
            normalize_bearing(360),
            0.0,
        )

        self.assertEqual(
            normalize_bearing(-45),
            315.0,
        )

    def test_compass(self):

        self.assertEqual(
            bearing_to_compass(0),
            "N",
        )

        self.assertEqual(
            bearing_to_compass(90),
            "E",
        )

        self.assertEqual(
            bearing_to_compass(225),
            "SW",
        )


if __name__ == "__main__":
    unittest.main()