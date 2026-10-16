import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from vinfall.video import VideoSource
from vinfall.pose import PoseSession
from vinfall.contracts import PoseLandmarks


class FakeCapture:
    def __init__(self, path):
        self.open = path != "bad"
        self.pos = 0

    def isOpened(self): return self.open
    def get(self, prop): return 25.0
    def read(self):
        if self.pos >= 2: return False, None
        self.pos += 1
        return True, f"frame{self.pos}"
    def set(self, prop, value): self.pos = int(value); return True
    def release(self): pass


class FakeCV2:
    CAP_PROP_FPS = 1
    CAP_PROP_POS_FRAMES = 2
    def VideoCapture(self, path): return FakeCapture(path)
    def module(self):
        return SimpleNamespace(VideoCapture=self.VideoCapture,
                               CAP_PROP_FPS=self.CAP_PROP_FPS,
                               CAP_PROP_POS_FRAMES=self.CAP_PROP_POS_FRAMES)


class VideoTests(unittest.TestCase):
    def test_reads_video_timestamps_and_reset(self):
        fake = FakeCV2()
        with patch.dict(sys.modules, {"cv2": fake.module()}):
            source = VideoSource("clip.mp4")
            self.assertEqual(source.fps, 25)
            self.assertEqual(source.read(), (True, "frame1", 0.0))
            self.assertEqual(source.read(), (True, "frame2", 40.0))
            self.assertFalse(source.read()[0])
            source.reset()
            self.assertEqual(source.read()[2], 0.0)
            source.close()

    def test_invalid_source_and_override_raise_clear_value_error(self):
        fake = FakeCV2()
        with patch.dict(sys.modules, {"cv2": fake.module()}):
            with self.assertRaisesRegex(ValueError, "Could not open"):
                VideoSource("bad")
            with self.assertRaisesRegex(ValueError, "fps_override"):
                VideoSource("clip", fps_override=0)

    def test_pose_model_timestamps_remain_increasing_after_integer_conversion(self):
        calls = []
        session = PoseSession.__new__(PoseSession)
        session._last_timestamp = -1.0
        session._last_model_timestamp = -1
        session._mp = SimpleNamespace(Image=lambda **kwargs: kwargs, ImageFormat=SimpleNamespace(SRGB=1))
        session._landmarker = SimpleNamespace(detect_for_video=lambda image, ts: calls.append(ts) or SimpleNamespace(pose_landmarks=[]))
        cv2 = SimpleNamespace(cvtColor=lambda frame, code: frame, COLOR_BGR2RGB=1)
        with patch.dict(sys.modules, {"cv2": cv2}):
            self.assertIsNone(session.process("frame", .1))
            self.assertIsNone(session.process("frame", .2))
        self.assertEqual(calls, [0, 1])

    def test_pose_process_preserves_image_list_and_optional_world_landmarks(self):
        image_points = [SimpleNamespace(x=.5, y=.5, visibility=1.0) for _ in range(33)]
        world_points = [SimpleNamespace(x=0.0, y=0.0, z=0.0, visibility=1.0) for _ in range(33)]
        result = SimpleNamespace(pose_landmarks=[image_points], pose_world_landmarks=[world_points])
        session = PoseSession.__new__(PoseSession)
        session._last_timestamp = -1.0
        session._last_model_timestamp = -1
        session._mp = SimpleNamespace(Image=lambda **kwargs: kwargs, ImageFormat=SimpleNamespace(SRGB=1))
        session._landmarker = SimpleNamespace(detect_for_video=lambda image, ts: result)
        cv2 = SimpleNamespace(cvtColor=lambda frame, code: frame, COLOR_BGR2RGB=1)
        with patch.dict(sys.modules, {"cv2": cv2}):
            landmarks = session.process("frame", 0)
        self.assertIsInstance(landmarks, PoseLandmarks)
        self.assertEqual(len(landmarks), 33)
        self.assertIs(landmarks[0], image_points[0])
        self.assertIs(landmarks.world_landmarks, world_points)

        result.pose_world_landmarks = None
        session._last_timestamp = -1.0
        session._last_model_timestamp = -1
        with patch.dict(sys.modules, {"cv2": cv2}):
            no_world = session.process("frame", 0)
        self.assertIsInstance(no_world, PoseLandmarks)
        self.assertIsNone(no_world.world_landmarks)

    def test_draw_uses_cv2_without_mediapipe_solutions(self):
        calls = []
        cv2 = SimpleNamespace(line=lambda *args: calls.append("line"),
                              circle=lambda *args: calls.append("circle"))
        frame = SimpleNamespace(shape=(100, 100, 3))
        session = PoseSession.__new__(PoseSession)
        session._config = SimpleNamespace(visibility_min=.5)
        landmarks = PoseLandmarks([SimpleNamespace(x=.5, y=.5, visibility=1.0) for _ in range(33)],
                                  [SimpleNamespace(x=0.0, y=0.0, z=0.0) for _ in range(33)])
        with patch.dict(sys.modules, {"cv2": cv2}):
            self.assertIs(session.draw(frame, landmarks), frame)
        self.assertIn("line", calls)
        self.assertIn("circle", calls)


if __name__ == "__main__":
    unittest.main()
