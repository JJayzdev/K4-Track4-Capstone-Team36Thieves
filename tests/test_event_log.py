import csv
import tempfile
import unittest
from pathlib import Path

from vinfall.contracts import Detection, Observation
from vinfall.event_log import EventLogger


class EventLoggerTests(unittest.TestCase):
    def test_exact_schema_and_one_row_per_new_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "events.csv"
            observation = Observation(1250, True, True, 72.5, .31, "tilted and low")
            alert = Detection(1250, "ALERT", observation, event_id=4,
                              new_alert=True, reason="fall confirmed")
            non_alert = Detection(1200, "SUSPECTED", observation, event_id=4)
            with EventLogger(path, "demo.mp4") as logger:
                logger.write(non_alert)
                logger.write(alert)
                logger.write(alert)  # duplicate delivery must not duplicate the CSV row
            with path.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(list(rows[0]), ["video_id", "event_id", "video_timestamp_ms",
                                              "angle_deg", "drop_ratio", "reason"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0], {
                "video_id": "demo.mp4", "event_id": "4", "video_timestamp_ms": "1250",
                "angle_deg": "72.5", "drop_ratio": "0.31", "reason": "fall confirmed",
            })

    def test_world_tilt_reason_is_logged_while_angle_column_stays_image_angle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            observation = Observation(1300, True, True, 10.0, .30,
                                      angle_3d_deg=75.0)
            alert = Detection(1300, "ALERT", observation, event_id=1,
                              new_alert=True,
                              reason="rapid_drop_and_world_tilt_confirmed")
            with EventLogger(path, "synthetic") as logger:
                logger.write(alert)
            with path.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["angle_deg"], "10.0")
            self.assertEqual(rows[0]["reason"],
                             "rapid_drop_and_world_tilt_confirmed")


if __name__ == "__main__":
    unittest.main()
