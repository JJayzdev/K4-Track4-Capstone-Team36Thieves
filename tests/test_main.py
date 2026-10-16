"""Integration tests use real video I/O and deterministic synthetic pose only."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as P
import unittest
from unittest.mock import patch

from vinfall.main import main


class MainTests(unittest.TestCase):
    def test_pipeline_replay_and_video_time_pause(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV/numpy not installed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 240))
            self.assertTrue(writer.isOpened())
            for _ in range(70):
                writer.write(np.zeros((240, 160, 3), dtype=np.uint8))
            writer.release()
            model = root / "fake.task"
            model.touch()

            class SyntheticPose:
                instances = 0
                def __init__(self, *args):
                    SyntheticPose.instances += 1
                def process(self, frame, timestamp):
                    pts = [P(x=.5, y=.5, visibility=1) for _ in range(33)]
                    for i, y in ((0, .05), (11, .2), (12, .2), (23, .5), (24, .5),
                                 (25, .7), (26, .7), (27, .95), (28, .95), (31, .95), (32, .95)):
                        pts[i].y = y
                    if timestamp >= 3000:
                        for i in (11, 12):
                            pts[i].x, pts[i].y = .2, .75
                        for i in (23, 24):
                            pts[i].x, pts[i].y = .8, .8
                    return pts
                def draw(self, frame, landmarks):
                    pass
                def close(self):
                    pass

            common = ["--source", str(source), "--model", str(model)]
            with patch("vinfall.pose.PoseSession", SyntheticPose):
                result = main(common + ["--headless", "--replays", "1", "--log", str(root / "events.csv"),
                                        "--summary", str(root / "headless.json")])
            self.assertEqual(result, 0)
            headless = json.loads((root / "headless.json").read_text())
            self.assertEqual(headless["sessions"][0]["alerts_ms"], [4200])
            self.assertEqual(headless["sessions"][0]["transitions"], headless["sessions"][1]["transitions"])
            self.assertEqual(SyntheticPose.instances, 2)
            keys = iter([32, -1, -1, 32] + [-1] * 80)
            def key(_):
                # Quit after EOF. The two paused polls do not consume frames.
                return next(keys, ord("q"))
            with patch("vinfall.pose.PoseSession", SyntheticPose), patch.object(cv2, "imshow"), \
                 patch.object(cv2, "waitKey", side_effect=key), \
                 patch.object(cv2, "getWindowProperty", return_value=1), patch.object(cv2, "destroyAllWindows"):
                main(common + ["--log", str(root / "paused.csv"), "--summary", str(root / "paused.json")])
            paused = json.loads((root / "paused.json").read_text())
            self.assertEqual(paused["sessions"][0]["alerts_ms"], [4200])
            self.assertEqual(paused["sessions"][0]["frames"], 70)


if __name__ == "__main__":
    unittest.main()
