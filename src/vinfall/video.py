"""Video file input with deterministic, video-time timestamps."""
from __future__ import annotations

import math
from pathlib import Path


class VideoSource:
    def __init__(self, path, fps_override=None):
        self.path = str(path)
        if fps_override is not None and (not math.isfinite(float(fps_override)) or float(fps_override) <= 0):
            raise ValueError("fps_override must be a finite number greater than zero")
        import cv2

        self._cv2 = cv2
        self._capture = cv2.VideoCapture(self.path)
        if not self._capture.isOpened():
            self._capture.release()
            raise ValueError(f"Could not open video source: {self.path}")
        reported = float(self._capture.get(cv2.CAP_PROP_FPS))
        self.fps = float(fps_override) if fps_override is not None else reported
        if not math.isfinite(self.fps) or self.fps <= 0:
            self._capture.release()
            raise ValueError("Video FPS is invalid; provide a positive fps_override")
        self._frame_index = 0

    def read(self):
        ok, frame = self._capture.read()
        timestamp_ms = self._frame_index * 1000.0 / self.fps
        if ok:
            self._frame_index += 1
        return bool(ok), frame, timestamp_ms

    def reset(self):
        if not self._capture.set(self._cv2.CAP_PROP_POS_FRAMES, 0):
            raise ValueError(f"Could not rewind video source: {self.path}")
        self._frame_index = 0

    def close(self):
        self._capture.release()
