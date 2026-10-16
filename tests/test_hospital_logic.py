"""Synthetic temporal controls for hospital-like daily activities.

These cases exercise detector logic only; they are not evidence of performance
on hospital video or patients.
"""
import unittest

from vinfall.config import Config
from vinfall.contracts import Observation
from vinfall.detector import FallDetector


def sample(ts, angle=10, drop=0, *, valid=True, calibrated=True):
    return Observation(ts, valid, calibrated,
                       angle if valid else None, drop if valid else None)


class HospitalLogicTests(unittest.TestCase):
    def setUp(self):
        self.detector = FallDetector(Config())

    def test_fast_sit_or_crouch_with_upright_torso_does_not_alert(self):
        # A fast height change alone is common in chair/bed transfers and
        # crouching; the torso angle never meets the fall-candidate condition.
        states = [self.detector.update(sample(0)).state]
        for ts in range(100, 2001, 100):
            states.append(self.detector.update(sample(ts, angle=18, drop=.32)).state)
        self.assertEqual(set(states), {"NORMAL"})

    def test_person_starting_lying_without_standing_calibration_is_not_alerted(self):
        # A person already in bed provides no observed fall transition and no
        # standing baseline. The analysis must remain uncalibrated.
        for ts in range(0, 3001, 100):
            result = self.detector.update(sample(ts, angle=75, drop=.45,
                                                 calibrated=False))
            self.assertEqual(result.state, "CALIBRATING")
            self.assertFalse(result.new_alert)

    def test_bed_occlusion_does_not_count_pending_confirmation_time(self):
        self.detector.update(sample(0))
        self.assertEqual(self.detector.update(sample(100, 70, .30)).state,
                         "SUSPECTED")
        # Accumulate 800 ms of valid low-pose confirmation, then lose the
        # person behind/within bed occlusion for longer than the reset limit.
        for ts in range(200, 1000, 100):
            self.detector.update(sample(ts, 70, .30))
        for ts in (1000, 1300, 1600):
            result = self.detector.update(sample(ts, valid=False))
            self.assertEqual(result.state, "NO_DATA")
            self.assertFalse(result.new_alert)

        resumed = self.detector.update(sample(1700, 70, .30))
        self.assertEqual(resumed.state, "NORMAL")
        self.assertFalse(resumed.new_alert)


if __name__ == "__main__":
    unittest.main()
