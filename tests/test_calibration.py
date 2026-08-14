import unittest
from calibration import fit_distance_model
class CalibrationTests(unittest.TestCase):
    def test_fit_exact(self):
        H, K = 150.0, 960.0
        samples = [(z, H + K/z) for z in (3.0,5.0,8.0,11.0)]
        m = fit_distance_model(samples)
        self.assertAlmostEqual(m.H, H, places=6)
        self.assertAlmostEqual(m.K, K, places=6)
        self.assertAlmostEqual(m.estimate(H + K/7), 7.0, places=6)
    def test_needs_three_points(self):
        with self.assertRaises(ValueError): fit_distance_model([(3,400),(10,250)])
if __name__ == '__main__': unittest.main()
