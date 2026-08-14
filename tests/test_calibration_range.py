import unittest

from calibration import fit_distance_model


class CalibrationRangeTests(unittest.TestCase):
    def test_fit_records_min_max_distance(self):
        model = fit_distance_model([
            (6.0, 719.0),
            (8.0, 641.0),
            (10.0, 583.0),
        ])

        self.assertEqual(model.min_distance_m, 6.0)
        self.assertEqual(model.max_distance_m, 10.0)
        self.assertTrue(model.has_calibrated_range())
        self.assertTrue(model.is_within_calibrated_range(7.0))
        self.assertFalse(model.is_within_calibrated_range(12.0))


if __name__ == "__main__":
    unittest.main()
