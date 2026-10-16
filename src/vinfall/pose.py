"""MediaPipe Pose Landmarker wrapper (imports MediaPipe only when instantiated)."""
from __future__ import annotations

import math

from .contracts import PoseLandmarks


class PoseSession:
    def __init__(self, model_path, config):
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        self._mp = __import__("mediapipe")
        self._config = config
        self._last_timestamp = -1.0
        self._last_model_timestamp = -1
        options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

    def process(self, frame, timestamp_ms):
        import cv2

        ts = float(timestamp_ms)
        if not math.isfinite(ts) or ts < 0 or ts <= self._last_timestamp:
            raise ValueError("timestamp_ms must be finite and strictly increasing")
        self._last_timestamp = ts
        model_ts = max(self._last_model_timestamp + 1, int(ts))
        self._last_model_timestamp = model_ts
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, model_ts)
        if not result.pose_landmarks:
            return None
        world_sets = getattr(result, "pose_world_landmarks", None)
        if world_sets is None:
            world_sets = getattr(result, "world_landmarks", None)
        world_landmarks = world_sets[0] if world_sets else None
        return PoseLandmarks(result.pose_landmarks[0], world_landmarks)

    def draw(self, frame, landmarks):
        if not landmarks:
            return frame
        import cv2
        edges = ((0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8),
                 (9, 10), (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),
                 (17, 19), (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
                 (11, 23), (12, 24), (23, 24), (23, 25), (25, 27), (27, 29), (29, 31),
                 (27, 31), (24, 26), (26, 28), (28, 30), (30, 32), (28, 32))
        h, w = frame.shape[:2]
        visibility_min = self._config.visibility_min
        points = []
        for p in landmarks:
            x, y = float(p.x), float(p.y)
            vis = float(getattr(p, "visibility", 1.0))
            points.append((int(x * w), int(y * h)) if math.isfinite(x) and math.isfinite(y)
                          and math.isfinite(vis) and vis >= visibility_min else None)
        for start, end in edges:
            if start < len(points) and end < len(points) and points[start] and points[end]:
                cv2.line(frame, points[start], points[end], (0, 220, 0), 2)
        for point in points:
            if point:
                cv2.circle(frame, point, 3, (0, 0, 255), -1)
        return frame

    def close(self):
        self._landmarker.close()
