import unittest
import math

from vinfall.config import Config
from vinfall.contracts import Observation
from vinfall.detector import FallDetector


def obs(ts, angle=10, drop=0, valid=True, calibrated=True, angle_3d=None):
    return Observation(ts, valid, calibrated, angle if valid else None,
                       drop if valid else None, angle_3d_deg=angle_3d)


class FallDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = FallDetector(Config())

    def test_normal_and_calibration_do_not_alert(self):
        self.assertEqual(self.detector.update(obs(0, calibrated=False)).state, "CALIBRATING")
        for ts in range(100, 3001, 100):
            result = self.detector.update(obs(ts))
        self.assertEqual(result.state, "NORMAL")
        self.assertFalse(result.new_alert)

    def test_rapid_drop_and_tilt_confirm_once(self):
        self.detector.update(obs(0))
        first = self.detector.update(obs(100, 70, .30))
        self.assertEqual(first.state, "SUSPECTED")
        alerts = []
        for ts in range(200, 1501, 100):
            result = self.detector.update(obs(ts, 70, .30))
            if result.new_alert:
                alerts.append(result)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].timestamp_ms, 1300)
        self.assertEqual(self.detector.update(obs(1600, 70, .30)).state, "ALERT")

    def test_slow_lying_does_not_create_rapid_drop_evidence(self):
        self.detector.update(obs(0))
        states = []
        for i in range(1, 21):
            # Gradual lowering never drops 25% within the 700 ms window.
            states.append(self.detector.update(obs(i * 200, 70, i * .02)).state)
        self.assertNotIn("ALERT", states)

    def test_missing_data_is_visible_and_long_gap_clears_candidate(self):
        self.detector.update(obs(0))
        self.assertEqual(self.detector.update(obs(100, 70, .3)).state, "SUSPECTED")
        self.assertEqual(self.detector.update(obs(200, valid=False)).state, "NO_DATA")
        self.assertEqual(self.detector.update(obs(800, valid=False)).state, "NO_DATA")
        resumed = self.detector.update(obs(900, 70, .3))
        self.assertEqual(resumed.state, "NORMAL")
        self.assertFalse(resumed.new_alert)

    def test_short_missing_pauses_confirmation(self):
        self.detector.update(obs(0))
        self.detector.update(obs(100, 70, .3))
        for ts in range(200, 900, 100):
            self.detector.update(obs(ts, 70, .3))
        self.detector.update(obs(900, valid=False))
        result = self.detector.update(obs(1200, 70, .3))
        self.assertEqual(result.state, "SUSPECTED")
        self.assertFalse(result.new_alert)
        alerts = []
        for ts in range(1300, 1900, 100):
            result = self.detector.update(obs(ts, 70, .3))
            if result.new_alert:
                alerts.append(result.timestamp_ms)
        self.assertEqual(alerts, [1700])

    def test_reset_replays_deterministically(self):
        def run():
            self.detector.reset()
            states = [self.detector.update(obs(0)).state]
            for ts in range(100, 1501, 100):
                states.append(self.detector.update(obs(ts, 70, .3)).state)
            return states

        self.assertEqual(run(), run())

    def test_no_calibration_no_alert_and_reset_clears_latch(self):
        for ts in range(0, 2000, 100):
            self.detector.update(obs(ts, 70, .5, calibrated=False))
        self.assertEqual(self.detector.update(obs(2000, 70, .5, calibrated=False)).state, "CALIBRATING")
        self.detector.reset()
        self.detector.update(obs(0))
        self.detector.update(obs(100, 70, .3))
        result = None
        for ts in range(200, 1501, 100):
            result = self.detector.update(obs(ts, 70, .3))
        self.assertEqual(result.state, "ALERT")
        self.detector.reset()
        self.assertEqual(self.detector.update(obs(0)).state, "NORMAL")

    def test_timestamp_must_increase(self):
        self.detector.update(obs(10))
        with self.assertRaises(ValueError):
            self.detector.update(obs(10))

    def test_uncalibrated_missing_pose_is_no_data(self):
        result = self.detector.update(obs(0, valid=False, calibrated=False))
        self.assertEqual(result.state, "NO_DATA")

    def test_nonfinite_measurements_are_rejected(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                self.detector.update(obs(bad))
        for angle, drop in ((math.nan, .3), (70, math.inf)):
            with self.subTest(angle=angle, drop=drop), self.assertRaises(ValueError):
                self.detector.update(obs(0, angle, drop))

    def test_missing_pose_cannot_pair_pre_gap_drop_with_new_tilt(self):
        self.detector.update(obs(0))
        self.detector.update(obs(100, 10, .3))
        self.detector.update(obs(200, valid=False))
        result = self.detector.update(obs(300, 70, .3))
        self.assertEqual(result.state, "NORMAL")
        self.assertFalse(result.new_alert)

    def test_missing_reset_uses_elapsed_time_since_last_valid_frame(self):
        self.detector.update(obs(0))
        self.detector.update(obs(100, 70, .3))
        self.detector.update(obs(500, valid=False))
        # Only 500 ms since the valid frame: pending candidate is still retained.
        self.assertEqual(self.detector.update(obs(600, 70, .3)).state, "SUSPECTED")
        self.detector.reset()
        self.detector.update(obs(0))
        self.detector.update(obs(100, 70, .3))
        self.detector.update(obs(500, valid=False))
        # More than 500 ms from the last valid frame clears it, even though
        # the missing interval itself began only 400 ms ago.
        self.assertEqual(self.detector.update(obs(700, 70, .3)).state, "NORMAL")

    def test_angle_evidence_before_or_after_drop_can_coincide(self):
        for sequence in (
            ((0, 10, 0), (100, 70, 0), (300, 70, .3)),
            ((0, 10, 0), (100, 10, .3), (300, 70, .3)),
        ):
            with self.subTest(sequence=sequence):
                self.detector.reset()
                for sample in sequence[:-1]:
                    self.detector.update(obs(*sample))
                result = self.detector.update(obs(*sequence[-1]))
                self.assertEqual(result.state, "SUSPECTED")

    def test_recovered_candidate_clears_evidence_and_cannot_rearm_stale(self):
        self.detector.update(obs(0))
        self.assertEqual(self.detector.update(obs(100, 70, .3)).state, "SUSPECTED")
        self.assertEqual(self.detector.update(obs(200, 10, .3)).state, "NORMAL")
        result = self.detector.update(obs(300, 70, .3))
        self.assertEqual(result.state, "NORMAL")
        self.assertFalse(result.new_alert)

    def test_short_missing_interval_adds_no_confirmation_time(self):
        self.detector.update(obs(0))
        self.detector.update(obs(100, 70, .3))
        for ts in (200, 300, 400, 500):
            self.detector.update(obs(ts, 70, .3))
        self.assertEqual(self.detector._confirm_ms, 400)
        self.detector.update(obs(600, valid=False))
        self.detector.update(obs(900, 70, .3))
        self.assertEqual(self.detector._confirm_ms, 400)
        result = self.detector.update(obs(1000, 70, .3))
        self.assertFalse(result.new_alert)
        self.assertEqual(self.detector._confirm_ms, 500)

    def test_missing_gap_boundary_exactly_500_retains_candidate_over_500_clears(self):
        self.detector.update(obs(0))
        self.detector.update(obs(100, 70, .3))
        self.detector.update(obs(500, valid=False))
        self.assertEqual(self.detector.update(obs(600, 70, .3)).state, "SUSPECTED")

        self.detector.reset()
        self.detector.update(obs(0))
        self.detector.update(obs(100, 70, .3))
        self.detector.update(obs(501, valid=False))
        self.assertEqual(self.detector.update(obs(601, 70, .3)).state, "NORMAL")

    def test_alert_stays_latched_on_uncalibrated_missing_pose(self):
        self.detector.update(obs(0))
        self.detector.update(obs(100, 70, .3))
        alerted = False
        for ts in range(200, 1501, 100):
            result = self.detector.update(obs(ts, 70, .3))
            alerted = alerted or result.new_alert
        self.assertTrue(alerted)
        latched = self.detector.update(obs(1600, valid=False, calibrated=False))
        self.assertEqual(latched.state, "ALERT")
        self.assertFalse(latched.new_alert)

    def test_world_tilt_can_confirm_frontal_lying_only_when_enabled(self):
        for enabled, expected_reason in (
            (True, "rapid_drop_and_world_tilt_confirmed"),
            (False, None),
        ):
            detector = FallDetector(Config(use_world_tilt=enabled))
            detector.update(obs(0, 10, 0, angle_3d=10))
            events = []
            for ts in range(100, 1501, 100):
                result = detector.update(obs(ts, 10, .30, angle_3d=75))
                if result.new_alert:
                    events.append(result)
            if enabled:
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].timestamp_ms, 1300)
                self.assertEqual(events[0].reason, expected_reason)
            else:
                self.assertEqual(events, [])
                self.assertNotEqual(result.state, "ALERT")

    def test_world_tilt_alone_or_without_calibration_never_alerts(self):
        detector = FallDetector(Config(use_world_tilt=True))
        detector.update(obs(0, 10, 0, angle_3d=10))
        for ts in range(100, 2001, 100):
            result = detector.update(obs(ts, 10, 0, angle_3d=75))
            self.assertFalse(result.new_alert)
        self.assertNotEqual(result.state, "ALERT")

        detector.reset()
        for ts in range(0, 2001, 100):
            result = detector.update(obs(ts, 10, .30, calibrated=False,
                                         angle_3d=75))
            self.assertEqual(result.state, "CALIBRATING")
            self.assertFalse(result.new_alert)

    def test_world_tilt_cannot_bridge_long_missing_gap(self):
        detector = FallDetector(Config(use_world_tilt=True))
        detector.update(obs(0, 10, 0, angle_3d=10))
        self.assertEqual(detector.update(obs(100, 10, .30, angle_3d=75)).state,
                         "SUSPECTED")
        self.assertEqual(detector.update(obs(200, valid=False)).state, "NO_DATA")
        resumed = detector.update(obs(800, 10, .30, angle_3d=75))
        self.assertEqual(resumed.state, "NORMAL")
        self.assertFalse(resumed.new_alert)

    def test_world_tilt_is_ignored_when_landmarks_are_invalid(self):
        detector = FallDetector(Config(use_world_tilt=True))
        detector.update(obs(0, 10, 0, angle_3d=10))
        missing = detector.update(obs(100, 10, .30, valid=False, angle_3d=75))
        self.assertEqual(missing.state, "NO_DATA")
        self.assertFalse(missing.new_alert)
        resumed = detector.update(obs(200, 10, .30, angle_3d=75))
        self.assertEqual(resumed.state, "NORMAL")
        self.assertFalse(resumed.new_alert)

    def test_nonfinite_world_angle_is_rejected_even_when_world_tilt_disabled(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                self.detector.update(obs(0, angle_3d=bad))


if __name__ == "__main__":
    unittest.main()
