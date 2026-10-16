"""Integration coverage for the headless analysis API."""
import csv
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as P
import unittest
from unittest.mock import patch

from vinfall.analysis import analyze_video
from vinfall.config import Config
from vinfall.contracts import Observation, PoseLandmarks
from vinfall.analysis import _overlay


def make_pose():
    pts = [P(x=.5, y=.5, visibility=1.0) for _ in range(33)]
    for i, y in ((0, .05), (11, .2), (12, .2), (23, .5), (24, .5),
                 (25, .7), (26, .7), (27, .95), (28, .95), (31, .95), (32, .95)):
        pts[i].y = y
    return pts


def make_fall_pose(timestamp):
    pts = make_pose()
    if timestamp >= 3000:
        for i, x, y in ((11, .2, .65), (12, .2, .65), (23, .8, .85), (24, .8, .85)):
            pts[i].x, pts[i].y = x, y
    return pts


def make_world_pose():
    pts = [P(x=0.0, y=0.0, z=0.0, visibility=1.0) for _ in range(33)]
    for i in (11, 12):
        pts[i] = P(x=0.0, y=0.0, z=0.0, visibility=1.0)
    for i in (23, 24):
        pts[i] = P(x=0.0, y=0.0, z=1.0, visibility=1.0)
    return pts


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV/numpy not installed")
        self.cv2, self.np = cv2, np
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.model = self.root / "fake.task"
        self.model.touch()

    def tearDown(self):
        self.temp.cleanup()

    def source(self, name="input.avi", frames=35):
        path = self.root / name
        writer = self.cv2.VideoWriter(str(path), self.cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 120))
        self.assertTrue(writer.isOpened())
        for _ in range(frames):
            writer.write(self.np.zeros((120, 160, 3), dtype=self.np.uint8))
        writer.release()
        return path

    def test_repeated_calls_have_fresh_sessions_and_consistent_artifacts(self):
        source = self.source()
        instances = []

        class SyntheticPose:
            def __init__(self, model, config):
                self.calls = []
                self.closed = False
                instances.append(self)
            def process(self, frame, timestamp):
                self.calls.append(timestamp)
                return make_pose()
            def draw(self, frame, landmarks):
                return frame
            def close(self):
                self.closed = True

        progress = []
        with patch("vinfall.pose.PoseSession", SyntheticPose):
            first = analyze_video(source, self.root / "out1", self.model, Config(),
                                  progress_callback=lambda done, total: progress.append((done, total)))
            second = analyze_video(source, self.root / "out2", self.model, Config())
        self.assertEqual(len(instances), 2)
        self.assertTrue(all(instance.closed for instance in instances))
        self.assertEqual(instances[0].calls, instances[1].calls)
        self.assertEqual(first.frame_count, 35)
        self.assertAlmostEqual(first.duration_seconds, 3.5, places=2)
        self.assertEqual(progress[0], (1, 35))
        self.assertEqual(progress[-1], (35, 35))
        self.assertTrue(first.raw_video_path.is_file())
        lines = [json.loads(line) for line in first.trace_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), first.frame_count)
        self.assertEqual(lines[-1]["timestamp_ms"], 3400.0)
        with first.csv_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), len(first.events))
        summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["frame_count"], first.frame_count)

    def test_fall_event_repeats_and_does_not_leak_into_next_video(self):
        source = self.source("fall.avi", frames=70)
        other = self.source("other.avi", frames=70)

        class SyntheticPose:
            def __init__(self, *args): pass
            def process(self, frame, timestamp):
                return PoseLandmarks(make_fall_pose(timestamp), make_world_pose())
            def draw(self, frame, landmarks): return frame
            def close(self): pass

        class NoPose:
            def __init__(self, *args): pass
            def process(self, frame, timestamp): return None
            def draw(self, frame, landmarks): return frame
            def close(self): pass

        with patch("vinfall.pose.PoseSession", SyntheticPose):
            first = analyze_video(source, self.root / "fall1", self.model, Config())
            repeated = analyze_video(source, self.root / "fall2", self.model, Config())
        self.assertEqual([event["video_timestamp_ms"] for event in first.events], [4200.0])
        self.assertEqual(first.events, repeated.events)
        self.assertAlmostEqual(first.events[0]["angle_3d_deg"], 90.0)
        traces = [json.loads(line) for line in first.trace_path.read_text(encoding="utf-8").splitlines()]
        alert_frames = [item for item in traces if item["new_alert"]]
        self.assertEqual(len(alert_frames), 1)
        self.assertEqual(alert_frames[0]["timestamp_ms"], 4200.0)
        with first.csv_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["video_timestamp_ms"]), 4200.0)
        decoded = self.cv2.VideoCapture(str(first.raw_video_path))
        decoded_count = 0
        while decoded.read()[0]:
            decoded_count += 1
        decoded.release()
        self.assertEqual(decoded_count, first.frame_count)

        with patch("vinfall.pose.PoseSession", NoPose):
            separate = analyze_video(other, self.root / "no_pose_after_fall", self.model, Config())
        self.assertEqual(separate.events, [])
        separate_trace = [json.loads(line) for line in separate.trace_path.read_text(encoding="utf-8").splitlines()]
        self.assertFalse(any(item["state"] == "ALERT" for item in separate_trace))

    def test_overlay_includes_3d_measurement_when_available(self):
        observation = Observation(100, True, True, angle_deg=5.0, drop_ratio=.1, angle_3d_deg=87.5)
        detection = P(observation=observation, state="NORMAL", timestamp_ms=100)
        frame = self.np.zeros((120, 320, 3), dtype=self.np.uint8)
        labels = []
        with patch.object(self.cv2, "putText", side_effect=lambda img, text, *a, **kw: labels.append(text)):
            rendered = _overlay(frame, detection)
        self.assertIs(rendered, frame)
        self.assertTrue(any("3D torso tilt: 87.5 deg" in label for label in labels))

    def test_no_pose_returns_video_and_warning(self):
        source = self.source("empty_pose.avi", frames=2)

        class NoPose:
            def __init__(self, *args): pass
            def process(self, frame, timestamp): return None
            def draw(self, frame, landmarks): return frame
            def close(self): pass

        with patch("vinfall.pose.PoseSession", NoPose):
            result = analyze_video(source, self.root / "no_pose", self.model, Config())
        self.assertEqual(result.frame_count, 2)
        self.assertTrue(result.raw_video_path.is_file())
        self.assertTrue(any("Không phát hiện" in warning for warning in result.warnings))

    def test_empty_or_unreadable_source_raises_clear_error(self):
        empty = self.source("zero.avi", frames=0)
        with self.assertRaisesRegex(ValueError, "Could not open video|no decodable frames"):
            analyze_video(empty, self.root / "empty", self.model, Config())
        with self.assertRaisesRegex(ValueError, "Could not open video"):
            analyze_video(self.root / "missing.avi", self.root / "missing", self.model, Config())

    def test_failure_closes_pose_session_and_invalid_fps_is_not_overridden(self):
        source = self.source()
        made = []

        class FailingPose:
            def __init__(self, *args):
                self.closed = False
                made.append(self)
            def process(self, frame, timestamp):
                raise RuntimeError("synthetic pose failure")
            def close(self):
                self.closed = True

        with patch("vinfall.pose.PoseSession", FailingPose):
            with self.assertRaisesRegex(RuntimeError, "synthetic pose failure"):
                analyze_video(source, self.root / "failed", self.model, Config())
        self.assertTrue(made[0].closed)

        class BadFpsCapture:
            def isOpened(self): return True
            def get(self, property_id): return 0.0
            def release(self): pass

        with patch.object(self.cv2, "VideoCapture", return_value=BadFpsCapture()), \
             patch("vinfall.pose.PoseSession") as pose_factory:
            with self.assertRaisesRegex(ValueError, "Video FPS is invalid"):
                analyze_video(source, self.root / "bad_fps", self.model, Config())
        pose_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
