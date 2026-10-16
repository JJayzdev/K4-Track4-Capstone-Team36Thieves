"""Model comparison report coverage with analysis calls isolated from inference."""
import csv
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import compare_models


class CompareModelsTests(unittest.TestCase):
    def test_comparison_continues_missing_models_and_reports_coverage_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "models").mkdir()
            (root / "configs").mkdir()
            (root / "models" / "pose_landmarker_lite.task").write_bytes(b"lite-model")
            (root / "models" / "pose_landmarker_full.task").write_bytes(b"full-model")
            (root / "configs" / "locked.json").write_text(json.dumps({}), encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"clips": [
                {"id": "R1-F01", "split": "dev", "path": "room1/fall.mp4", "label": "fall",
                 "crop": "full", "onset_ms": 1000, "room": "room-1"},
                {"id": "R2-N01", "split": "dev", "path": "room2/normal.mp4", "label": "normal",
                 "crop": "right-half", "onset_ms": None, "room": "room-2"},
            ]}), encoding="utf-8")
            calls = []

            def fake_analyze(source, output, model, config, crop):
                calls.append((Path(source), Path(output), Path(model), crop))
                fall = "fall" in str(source)
                events = ([{"video_timestamp_ms": 2450.0, "event_id": 1}] if fall else [])
                return SimpleNamespace(frame_count=100, fps=10.0, duration_seconds=10.0,
                                       processing_seconds=2.0, valid_pose_frames=80,
                                       calibrated_frames=75, events=events)

            with patch.object(compare_models, "ROOT", root), \
                 patch.object(compare_models, "analyze_video", side_effect=fake_analyze):
                report = compare_models.compare_models(
                    manifest, ("lite", "full", "heavy"), "dev", root / "results",
                    root / "configs" / "locked.json")

            self.assertEqual(len(report["results"]), 6)
            self.assertEqual(len(calls), 4)
            lite_fall = next(row for row in report["results"]
                             if row["model_variant"] == "lite" and row["clip_id"] == "R1-F01")
            self.assertEqual(lite_fall["status"], "FALL_DETECTED")
            self.assertEqual(lite_fall["latency_ms"], 1450.0)
            normal = next(row for row in report["results"] if row["clip_id"] == "R2-N01")
            self.assertEqual(normal["status"], "NO_ALERT")
            self.assertEqual(normal["room"], "room-2")
            self.assertAlmostEqual(lite_fall["pose_coverage"], .8)
            self.assertAlmostEqual(report["metrics"]["lite"]["valid_pose_coverage"], .8)
            self.assertIn("not accuracy", report["interpretation"])
            missing = [row for row in report["results"] if row["model_variant"] == "heavy"]
            self.assertTrue(all(row["status"] == "ERROR" and "Model is missing" in row["error"]
                                for row in missing))
            self.assertTrue((root / "results" / "comparison.csv").is_file())
            self.assertTrue((root / "results" / "comparison.json").is_file())
            with (root / "results" / "comparison.csv").open(encoding="utf-8", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 6)
            self.assertEqual(len({str(call[1]) for call in calls}), 4)

    def test_no_calibration_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "models").mkdir()
            (root / "models" / "pose_landmarker_lite.task").touch()
            config = root / "config.json"
            config.write_text(json.dumps({"use_world_tilt": True}), encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"clips": [{"id": "f", "split": "dev", "path": "f.mp4",
                                                          "label": "fall"}]}), encoding="utf-8")
            result = SimpleNamespace(frame_count=10, fps=10, duration_seconds=1,
                                     processing_seconds=.2, valid_pose_frames=10,
                                     calibrated_frames=0, events=[])
            seen_configs = []

            def fake_analyze(*args, **kwargs):
                seen_configs.append(args[3])
                return result

            with patch.object(compare_models, "ROOT", root), \
                 patch.object(compare_models, "analyze_video", side_effect=fake_analyze):
                report = compare_models.compare_models(manifest, ("lite",), "dev", root / "out", config)
            self.assertEqual(report["results"][0]["status"], "INCONCLUSIVE_NO_CALIBRATION")
            self.assertTrue(seen_configs[0].use_world_tilt)
            self.assertEqual(report["metrics"]["lite"]["clips"], 1)

    def test_unknown_is_unlabeled_and_room_counts_exclude_uncalibrated_fall_from_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "models").mkdir()
            (root / "models" / "pose_landmarker_lite.task").touch()
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"clips": [
                {"id": "R1-U", "split": "dev", "path": "unknown.mp4", "label": "unknown",
                 "room": "office"},
                {"id": "R1-F", "split": "dev", "path": "uncalibrated-fall.mp4", "label": "fall",
                 "room": "office"},
            ]}), encoding="utf-8")

            def fake_analyze(source, *args, **kwargs):
                uncalibrated = "uncalibrated" in str(source)
                return SimpleNamespace(
                    frame_count=20, fps=10, duration_seconds=2, processing_seconds=.2,
                    valid_pose_frames=15, calibrated_frames=0 if uncalibrated else 10,
                    events=[{"video_timestamp_ms": 1500, "event_id": 1}],
                )

            with patch.object(compare_models, "ROOT", root), \
                 patch.object(compare_models, "analyze_video", side_effect=fake_analyze):
                report = compare_models.compare_models(manifest, ("lite",), "dev", root / "out", config)

            unknown = next(row for row in report["results"] if row["expected"] == "unknown")
            uncalibrated_fall = next(row for row in report["results"] if row["expected"] == "fall")
            self.assertEqual(unknown["status"], "UNLABELED")
            self.assertEqual(unknown["event_count"], 1)
            self.assertEqual(uncalibrated_fall["status"], "INCONCLUSIVE_NO_CALIBRATION")
            metrics = report["metrics"]["lite"]
            self.assertEqual(metrics["fall_clips_detected"], 0)
            self.assertEqual(metrics["raw_fall_alert_clips"], 1)
            self.assertEqual(metrics["unlabeled_clips"], 1)
            room = metrics["by_room"]["office"]
            self.assertEqual(room["independent_clip_count"], 2)
            self.assertEqual(room["calibrated_clip_count"], 1)
            self.assertEqual(room["fall_detected_clip_count"], 0)
            self.assertEqual(room["fall_inconclusive_no_calibration_clip_count"], 1)
            self.assertEqual(room["raw_fall_alert_clip_count"], 1)
            self.assertEqual(room["false_alert_clip_count"], 0)
            self.assertEqual(room["unknown_label_clip_count"], 1)


if __name__ == "__main__":
    unittest.main()
