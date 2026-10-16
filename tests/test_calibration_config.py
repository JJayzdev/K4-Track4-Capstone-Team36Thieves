import unittest

from vinfall.config import Config


class CalibrationConfigTests(unittest.TestCase):
    def test_grace_is_explicit_and_zero_preserves_old_profiles(self):
        self.assertEqual(Config().calibration_grace_ms, 0)
        self.assertEqual(Config(calibration_grace_ms=1000).calibration_grace_ms, 1000)

    def test_invalid_grace_does_not_extend_window(self):
        for value in (-1, float("inf"), float("nan"), True, "1000"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "calibration_grace_ms"):
                Config(calibration_grace_ms=value)
