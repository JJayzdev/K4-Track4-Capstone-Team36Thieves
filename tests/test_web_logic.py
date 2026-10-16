"""Temporal web-analysis checks using synthetic observations only.

These tests exercise session isolation and alert persistence at the boundary
between the detector and CSV logger without relying on evaluation clips.
"""
import csv
import tempfile
import unittest
from pathlib import Path

from vinfall.config import Config
from vinfall.contracts import Observation
from vinfall.detector import FallDetector
from vinfall.event_log import EventLogger


def run_session(samples, csv_path, video_id, config=None):
    detector = FallDetector(config or Config())
    alerts = []
    with EventLogger(csv_path, video_id) as logger:
        for sample in samples:
            detection = detector.update(sample)
            logger.write(detection)
            if detection.new_alert:
                alerts.append((detection.event_id, detection.timestamp_ms,
                               detection.reason))
    return alerts


class WebLogicTests(unittest.TestCase):
    def test_repeated_analysis_sessions_match_and_fresh_normal_session_has_no_stale_alert(self):
        # The angle evidence and rapid-drop evidence occur on different frames.
        falling = [
            Observation(0, True, True, 10, 0),
            Observation(100, True, True, 70, 0),
            Observation(300, True, True, 70, .30),
            *[Observation(ts, True, True, 70, .30)
              for ts in range(400, 1701, 100)],
            # Alert remains visible through an occlusion, without a new event.
            Observation(1800, False, True, None, None),
            Observation(1900, False, True, None, None),
        ]
        normal = [
            Observation(0, True, True, 10, 0),
            Observation(100, False, True, None, None),
            Observation(200, True, True, 10, 0),
            Observation(300, True, True, 15, .02),
        ]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = run_session(falling, root / "first.csv", "synthetic")
            second = run_session(falling, root / "second.csv", "synthetic")
            fresh_normal = run_session(normal, root / "normal.csv", "synthetic")

            self.assertEqual(first, second)
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0][1], 1500)
            self.assertEqual(fresh_normal, [])

            with (root / "first.csv").open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["video_timestamp_ms"], "1500")
            self.assertEqual(rows[0]["event_id"], "1")

    def test_world_tilt_analysis_sessions_are_independent_and_deterministic(self):
        config = Config(use_world_tilt=True)
        frontal_fall = [
            Observation(0, True, True, 10, 0, angle_3d_deg=10),
            *[Observation(ts, True, True, 10, .30, angle_3d_deg=75)
              for ts in range(100, 1501, 100)],
        ]
        normal = [
            Observation(0, True, True, 10, 0, angle_3d_deg=10),
            Observation(100, True, True, 12, .02, angle_3d_deg=15),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = run_session(frontal_fall, root / "world1.csv", "synthetic", config)
            second = run_session(frontal_fall, root / "world2.csv", "synthetic", config)
            next_normal = run_session(normal, root / "normal.csv", "synthetic", config)

        self.assertEqual(first, second)
        self.assertEqual(first, [(1, 1300, "rapid_drop_and_world_tilt_confirmed")])
        self.assertEqual(next_normal, [])


if __name__ == "__main__":
    unittest.main()
