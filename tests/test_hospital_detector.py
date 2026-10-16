"""Focused regression cases for the frozen hospital detector config."""
import json
from pathlib import Path
import unittest

from vinfall.config import Config
from vinfall.contracts import Observation
from vinfall.detector import FallDetector


LOCKED_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "hospital_locked.json"


def sample(ts, angle=10, drop=0, *, valid=True, calibrated=True, world=10):
    return Observation(ts, valid, calibrated,
                       angle if valid else None, drop if valid else None,
                       angle_3d_deg=world if valid else None)


def locked_detector():
    config = Config(**json.loads(LOCKED_CONFIG.read_text(encoding="utf-8")))
    return FallDetector(config)


class HospitalLockedDetectorTests(unittest.TestCase):
    def test_fast_point_two_one_drop_and_world_tilt_alert(self):
        detector = locked_detector()
        detector.update(sample(0, world=10))
        alert = None
        for ts in range(100, 1501, 100):
            result = detector.update(sample(ts, angle=10, drop=.21, world=75))
            if result.new_alert:
                alert = result
        self.assertIsNotNone(alert)
        self.assertEqual(alert.timestamp_ms, 1300)
        self.assertEqual(alert.reason, "rapid_drop_and_world_tilt_confirmed")

    def test_slow_bending_or_sitting_does_not_trigger_rapid_drop(self):
        detector = locked_detector()
        detector.update(sample(0, world=10))
        states = []
        # Gradual lowering grows the drop by only .02 every 200 ms, below the
        # locked .15 rapid-drop requirement in every 700 ms history window.
        for i in range(1, 36):
            result = detector.update(sample(i * 200, angle=10,
                                            drop=i * .02, world=75))
            states.append(result.state)
            self.assertFalse(result.new_alert)
        self.assertNotIn("ALERT", states)

    def test_missing_landmarks_pause_confirmation_without_adding_elapsed_gap(self):
        detector = locked_detector()
        detector.update(sample(0, world=10))
        detector.update(sample(100, drop=.21, world=75))
        for ts in range(200, 700, 100):
            detector.update(sample(ts, drop=.21, world=75))
        self.assertEqual(detector._confirm_ms, 500)

        detector.update(sample(700, valid=False))
        detector.update(sample(800, valid=False))
        resumed = detector.update(sample(900, drop=.21, world=75))
        self.assertEqual(resumed.state, "SUSPECTED")
        self.assertFalse(resumed.new_alert)
        self.assertEqual(detector._confirm_ms, 500)

        alert = None
        for ts in range(1000, 1700, 100):
            result = detector.update(sample(ts, drop=.21, world=75))
            if result.new_alert:
                alert = result
        self.assertIsNotNone(alert)
        self.assertEqual(alert.timestamp_ms, 1600)

    def test_new_detector_and_reset_do_not_inherit_another_session_alert(self):
        first = locked_detector()
        first.update(sample(0, world=10))
        alert = None
        for ts in range(100, 1401, 100):
            result = first.update(sample(ts, drop=.21, world=75))
            if result.new_alert:
                alert = result
        self.assertIsNotNone(alert)

        separate = locked_detector()
        self.assertEqual(separate.update(sample(0, world=10)).state, "NORMAL")
        self.assertFalse(separate.update(sample(100, world=15)).new_alert)

        first.reset()
        replay_start = first.update(sample(0, world=10))
        self.assertEqual(replay_start.state, "NORMAL")
        self.assertFalse(replay_start.new_alert)


if __name__ == "__main__":
    unittest.main()
