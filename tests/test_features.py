import unittest
from types import SimpleNamespace as P

from vinfall.config import Config
from vinfall.contracts import PoseLandmarks
from vinfall.features import FeatureExtractor


def pose(shoulder_y=.2, hip_y=.5, feet_y=.95, shoulder_x=.5, hip_x=.5):
    points = [P(x=.5, y=.5, visibility=1.0) for _ in range(33)]
    for i in (11, 12):
        points[i] = P(x=shoulder_x, y=shoulder_y, visibility=1.0)
    for i in (23, 24):
        points[i] = P(x=hip_x, y=hip_y, visibility=1.0)
    points[0] = P(x=.5, y=.05 if shoulder_y <= .2 else shoulder_y - .15, visibility=1.0)
    for i in (25, 26):
        points[i] = P(x=.5, y=.7, visibility=1.0)
    for i in (27, 28):
        points[i] = P(x=.5, y=feet_y - .1, visibility=1.0)
    for i in (27, 28, 31, 32):
        points[i] = P(x=.5, y=feet_y, visibility=1.0)
    return points


def world_pose(orientation="upright"):
    points = [P(x=0.0, y=0.0, z=0.0, visibility=1.0) for _ in range(33)]
    if orientation == "upright":
        shoulder, hip = (0.0, 0.0, 0.0), (0.0, -1.0, 0.0)
    elif orientation == "toward_camera":
        shoulder, hip = (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    else:
        raise ValueError(orientation)
    for index in (11, 12):
        points[index] = P(x=shoulder[0], y=shoulder[1], z=shoulder[2], visibility=1.0)
    for index in (23, 24):
        points[index] = P(x=hip[0], y=hip[1], z=hip[2], visibility=1.0)
    return points


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(calibration_min_samples=3)
        self.extractor = FeatureExtractor(self.config)

    def test_standing_calibration_then_drop_increases_ratio(self):
        for n in range(3):
            obs = self.extractor.update(pose(), 640, 480, n * 1000)
        self.assertTrue(obs.calibrated)
        self.assertAlmostEqual(obs.drop_ratio, 0.0)
        low = self.extractor.update(pose(shoulder_y=.35, hip_y=.65, feet_y=.98), 640, 480, 2500)
        self.assertGreater(low.drop_ratio, .15)

    def test_initial_lying_pose_does_not_calibrate(self):
        lying = pose(shoulder_x=.35, hip_x=.65)
        for n in range(3):
            obs = self.extractor.update(lying, 640, 480, n * 1000)
        self.assertFalse(obs.calibrated)

    def test_calibration_waits_for_two_second_window_and_rejects_seated(self):
        for n in range(2):
            obs = self.extractor.update(pose(), 640, 480, n * 250)
        self.assertFalse(obs.calibrated)
        seated = pose()
        seated[25] = P(x=.5, y=.45, visibility=1)
        seated[26] = P(x=.5, y=.45, visibility=1)
        for n in range(2, 9):
            obs = self.extractor.update(seated, 640, 480, n * 250)
        self.assertFalse(obs.calibrated)

    def test_noninteger_frame_rate_calibrates_past_window_boundary(self):
        config = Config(calibration_min_samples=15)
        extractor = FeatureExtractor(config)
        for frame_index in range(61):
            timestamp = frame_index * 1000 / 29.97
            obs = extractor.update(pose(), 640, 480, timestamp)
        self.assertGreater(timestamp, config.calibration_ms)
        self.assertTrue(obs.calibrated)

    def test_window_finalizes_from_stored_samples_when_boundary_frame_lacks_pose(self):
        config = Config(calibration_min_samples=15)
        extractor = FeatureExtractor(config)
        for frame_index in range(60):
            extractor.update(pose(), 640, 480, frame_index * 1000 / 29.97)
        obs = extractor.update(None, 640, 480, 60 * 1000 / 29.97)
        self.assertFalse(obs.landmarks_valid)
        self.assertTrue(obs.calibrated)

    def test_invalid_time_dimensions_and_offscreen_calibration_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "timestamp_ms"):
            self.extractor.update(pose(), 640, 480, float("nan"))
        with self.assertRaisesRegex(ValueError, "width and height"):
            self.extractor.update(pose(), float("inf"), 480, 0)
        offscreen = pose()
        offscreen[0].y = -0.1
        self.assertFalse(self.extractor.update(offscreen, 640, 480, 0).calibrated)
        self.assertFalse(self.extractor.update(pose(), 640, 480, 1000).calibrated)
        self.assertFalse(self.extractor.update(pose(), 640, 480, 2000).calibrated)

    def test_calibrated_features_do_not_require_visible_legs(self):
        for n in range(3):
            self.extractor.update(pose(), 640, 480, n * 1000)
        upper_body = pose()
        for i in (0, 25, 26, 27, 28, 31, 32):
            upper_body[i].visibility = 0.0
        obs = self.extractor.update(upper_body, 640, 480, 2500)
        self.assertTrue(obs.landmarks_valid)
        self.assertTrue(obs.calibrated)

    def test_offscreen_torso_is_no_data_after_calibration(self):
        for n in range(3):
            self.extractor.update(pose(), 640, 480, n * 1000)
        offscreen = pose()
        offscreen[11].x = -0.01
        obs = self.extractor.update(offscreen, 640, 480, 2500)
        self.assertFalse(obs.landmarks_valid)
        self.assertTrue(obs.calibrated)

    def test_reports_unavailable_baseline_after_window(self):
        config = Config(calibration_min_samples=20)
        extractor = FeatureExtractor(config)
        obs = extractor.update(pose(), 640, 480, 2500)
        self.assertFalse(obs.calibrated)
        self.assertEqual(obs.reason, "standing_baseline_unavailable")

    def test_invalid_and_nonfinite_landmarks_are_no_data(self):
        self.assertFalse(self.extractor.update(None, 640, 480, 0).landmarks_valid)
        bad = pose()
        bad[11] = P(x=float("nan"), y=.2, visibility=1)
        self.assertFalse(self.extractor.update(bad, 640, 480, 10).landmarks_valid)

    def test_rejects_incomplete_visibility(self):
        pts = pose()
        pts[23].visibility = .1
        self.assertFalse(self.extractor.update(pts, 640, 480, 0).landmarks_valid)

    def test_reset_discards_calibration_and_history(self):
        for n in range(3):
            self.extractor.update(pose(), 640, 480, n * 100)
        self.extractor.reset()
        obs = self.extractor.update(pose(), 640, 480, 0)
        self.assertFalse(obs.calibrated)
        self.assertEqual(len(self.extractor.history), 0)

    def test_world_tilt_detects_lying_toward_camera_when_image_tilt_is_zero(self):
        image_pose = pose()
        upright = self.extractor.update(PoseLandmarks(image_pose, world_pose("upright")), 640, 480, 0)
        self.assertAlmostEqual(upright.angle_deg, 0.0)
        self.assertAlmostEqual(upright.angle_3d_deg, 0.0)

        toward_camera = self.extractor.update(
            PoseLandmarks(pose(), world_pose("toward_camera")), 640, 480, 100)
        self.assertTrue(toward_camera.landmarks_valid)
        self.assertAlmostEqual(toward_camera.angle_deg, 0.0)
        self.assertAlmostEqual(toward_camera.angle_3d_deg, 90.0)

    def test_world_tilt_missing_or_invalid_falls_back_safely(self):
        absent = self.extractor.update(PoseLandmarks(pose(), None), 640, 480, 0)
        self.assertTrue(absent.landmarks_valid)
        self.assertIsNone(absent.angle_3d_deg)

        malformed = world_pose()
        malformed[23].z = float("nan")
        bad_world = self.extractor.update(PoseLandmarks(pose(), malformed), 640, 480, 100)
        self.assertTrue(bad_world.landmarks_valid)
        self.assertIsNone(bad_world.angle_3d_deg)

        invalid_image = pose()
        invalid_image[11].x = float("nan")
        invalid = self.extractor.update(PoseLandmarks(invalid_image, world_pose("toward_camera")),
                                       640, 480, 200)
        self.assertFalse(invalid.landmarks_valid)
        self.assertIsNone(invalid.angle_3d_deg)

    def test_grace_calibrates_late_full_body_entry_without_changing_baseline_rules(self):
        config = Config(calibration_min_samples=15, calibration_grace_ms=1000)
        extractor = FeatureExtractor(config)
        for timestamp in range(1960, 2521, 40):
            obs = extractor.update(pose(), 640, 480, timestamp)
        self.assertTrue(obs.calibrated)
        self.assertEqual(timestamp, 2520)
        self.assertAlmostEqual(obs.drop_ratio, 0.0)

    def test_grace_deadline_is_hard_and_allows_exact_deadline_sample(self):
        config = Config(calibration_min_samples=15, calibration_grace_ms=1000)

        enough_at_deadline = FeatureExtractor(config)
        for timestamp in range(1960, 2481, 40):  # 14 valid standing samples
            enough_at_deadline.update(pose(), 640, 480, timestamp)
        for timestamp in range(2520, 3000, 40):
            enough_at_deadline.update(None, 640, 480, timestamp)
        obs = enough_at_deadline.update(pose(), 640, 480, 3000)
        self.assertTrue(obs.calibrated)

        too_late = FeatureExtractor(config)
        for timestamp in range(1960, 2481, 40):  # 14 samples by 2.48s
            too_late.update(pose(), 640, 480, timestamp)
        self.assertFalse(too_late.update(None, 640, 480, 3001).calibrated)
        after_deadline = too_late.update(pose(), 640, 480, 3040)
        self.assertFalse(after_deadline.calibrated)
        self.assertEqual(len(too_late._samples), 14)

    def test_grace_does_not_calibrate_seated_or_lying_pose(self):
        config = Config(calibration_min_samples=3, calibration_grace_ms=1000)
        seated = FeatureExtractor(config)
        bent = pose()
        bent[25] = P(x=.5, y=.45, visibility=1.0)
        bent[26] = P(x=.5, y=.45, visibility=1.0)
        for timestamp in range(0, 3041, 250):
            obs = seated.update(bent, 640, 480, timestamp)
        self.assertFalse(obs.calibrated)

    def test_reason_stays_calibrating_until_grace_deadline_closes(self):
        config = Config(calibration_min_samples=20, calibration_grace_ms=1000)
        extractor = FeatureExtractor(config)
        during_grace = extractor.update(pose(), 640, 480, 2200)
        self.assertFalse(during_grace.calibrated)
        self.assertEqual(during_grace.reason, "calibrating")

        after_deadline = extractor.update(pose(), 640, 480, 3001)
        self.assertFalse(after_deadline.calibrated)
        self.assertEqual(after_deadline.reason, "standing_baseline_unavailable")

        lying = FeatureExtractor(config)
        flat = pose(shoulder_x=.35, hip_x=.65)
        for timestamp in range(0, 3041, 250):
            obs = lying.update(flat, 640, 480, timestamp)
        self.assertFalse(obs.calibrated)

    def test_reset_reopens_and_clears_grace_calibration_window(self):
        config = Config(calibration_min_samples=3, calibration_grace_ms=1000)
        extractor = FeatureExtractor(config)
        for timestamp in (1960, 2000, 2040):
            extractor.update(pose(), 640, 480, timestamp)
        self.assertTrue(extractor.update(pose(), 640, 480, 2080).calibrated)
        extractor.reset()
        self.assertFalse(extractor._calibration_closed)
        self.assertEqual(extractor._samples, [])
        for timestamp in (0, 1000, 2000):
            obs = extractor.update(pose(), 640, 480, timestamp)
        self.assertTrue(obs.calibrated)


if __name__ == "__main__":
    unittest.main()
