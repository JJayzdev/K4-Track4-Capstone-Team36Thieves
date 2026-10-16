"""Pixel-space torso geometry and initial standing calibration."""
from __future__ import annotations

import math
import statistics
from collections import deque

from .contracts import Observation


class FeatureExtractor:
    # MediaPipe Pose landmark indices: shoulders, hips, ankles, nose.
    _SHOULDERS = (11, 12)
    _HIPS = (23, 24)
    _NOSE = 0
    _KNEES = (25, 26)
    _ANKLES = (27, 28)
    _FEET = (27, 28, 31, 32)

    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self._samples = []
        self._baseline_center = None
        self._baseline_height = None
        self._calibration_deadline = (self.config.calibration_ms
                                      + getattr(self.config, "calibration_grace_ms", 0.0))
        self._calibration_closed = False
        self.history = deque()

    def _finalize_calibration(self):
        if len(self._samples) < self.config.calibration_min_samples:
            return False
        self._baseline_center = statistics.median(sample[1] for sample in self._samples)
        self._baseline_height = statistics.median(sample[2] for sample in self._samples)
        self._calibration_closed = True
        return True

    @staticmethod
    def _point(landmarks, index, width, height, visibility_min):
        try:
            p = landmarks[index]
            x, y = float(p.x), float(p.y)
            visibility = float(getattr(p, "visibility", 1.0))
            if not all(math.isfinite(v) for v in (x, y, visibility)) or visibility < visibility_min:
                return None
            return x * width, y * height
        except (IndexError, AttributeError, TypeError, ValueError):
            return None

    def _world_tilt(self, landmarks):
        """Return torso tilt in world coordinates when all four anchors are usable."""
        try:
            world = landmarks.world_landmarks
            if world is None:
                return None
            shoulders = [world[i] for i in self._SHOULDERS]
            hips = [world[i] for i in self._HIPS]
            points = []
            for point in shoulders + hips:
                x, y, z = float(point.x), float(point.y), float(point.z)
                visibility = float(getattr(point, "visibility", 1.0))
                if (not all(math.isfinite(value) for value in (x, y, z, visibility))
                        or visibility < self.config.visibility_min):
                    return None
                points.append((x, y, z))
            shoulder_mid = tuple((points[0][axis] + points[1][axis]) / 2 for axis in range(3))
            hip_mid = tuple((points[2][axis] + points[3][axis]) / 2 for axis in range(3))
            dx = hip_mid[0] - shoulder_mid[0]
            dy = hip_mid[1] - shoulder_mid[1]
            dz = hip_mid[2] - shoulder_mid[2]
            horizontal = math.hypot(dx, dz)
            if horizontal == 0 and dy == 0:
                return None
            return math.degrees(math.atan2(horizontal, abs(dy)))
        except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
            return None

    def update(self, landmarks, width, height, timestamp_ms):
        timestamp_ms = float(timestamp_ms)
        if not math.isfinite(timestamp_ms):
            raise ValueError("timestamp_ms must be finite")
        try:
            valid_dimensions = math.isfinite(float(width)) and math.isfinite(float(height)) and width > 0 and height > 0
        except (TypeError, ValueError):
            valid_dimensions = False
        if not valid_dimensions:
            raise ValueError("frame width and height must be finite and greater than zero")
        if self._baseline_height is None and not self._calibration_closed:
            if timestamp_ms >= self.config.calibration_ms:
                self._finalize_calibration()
            if (self._baseline_height is None
                    and timestamp_ms > self._calibration_deadline):
                self._calibration_closed = True
        invalid = Observation(timestamp_ms, False, self._baseline_height is not None, reason="missing_or_unclear_landmarks")
        if landmarks is None or width <= 0 or height <= 0:
            return invalid
        vmin = self.config.visibility_min
        sh = [self._point(landmarks, i, width, height, vmin) for i in self._SHOULDERS]
        hp = [self._point(landmarks, i, width, height, vmin) for i in self._HIPS]
        angle_3d = self._world_tilt(landmarks)
        calibrating = self._baseline_height is None
        body_checks = ([self._point(landmarks, i, width, height, vmin)
                        for i in (self._NOSE,) + self._KNEES + self._ANKLES]
                       if calibrating else [])
        feet = [self._point(landmarks, i, width, height, vmin) for i in self._FEET]
        if any(p is None for p in sh + hp + body_checks):
            return invalid
        if any(not (0 <= p[0] < width and 0 <= p[1] < height) for p in sh + hp):
            return invalid
        if calibrating:
            required = sh + hp + body_checks + [p for p in feet if p is not None]
            if any(not (0 <= p[0] < width and 0 <= p[1] < height) for p in required):
                return Observation(timestamp_ms, True, False, reason="body_out_of_frame",
                                   angle_3d_deg=angle_3d)
        shoulder = (sum(p[0] for p in sh) / 2, sum(p[1] for p in sh) / 2)
        hip = (sum(p[0] for p in hp) / 2, sum(p[1] for p in hp) / 2)
        center = ((shoulder[0] + hip[0]) / 2, (shoulder[1] + hip[1]) / 2)
        torso_height = math.dist(shoulder, hip)
        standing_height = None
        if calibrating:
            nose = self._point(landmarks, self._NOSE, width, height, vmin)
            knee_points = [self._point(landmarks, i, width, height, vmin) for i in self._KNEES]
            ankle_points = [self._point(landmarks, i, width, height, vmin) for i in self._ANKLES]
            if any(p is None for p in knee_points + ankle_points) or not any(p is not None for p in feet):
                return invalid
            # Near-straight knee angles help distinguish standing from sitting.
            for side, knee_index in enumerate(self._KNEES):
                hip_point = self._point(landmarks, self._HIPS[side], width, height, vmin)
                knee = knee_points[side]
                ankle = ankle_points[side]
                a = (hip_point[0] - knee[0], hip_point[1] - knee[1])
                b = (ankle[0] - knee[0], ankle[1] - knee[1])
                denom = math.hypot(*a) * math.hypot(*b)
                if denom == 0:
                    return invalid
                knee_angle = math.degrees(math.acos(max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / denom))))
                if knee_angle < 145.0:
                    return Observation(timestamp_ms, True, False, reason="not_standing",
                                       angle_3d_deg=angle_3d)
            standing_height = max(p[1] for p in feet if p is not None) - nose[1]
        if torso_height <= 0 or (calibrating and (standing_height is None or standing_height <= 0)):
            return invalid
        dx, dy = hip[0] - shoulder[0], hip[1] - shoulder[1]
        angle = math.degrees(math.atan2(abs(dx), abs(dy)))

        if (calibrating and not self._calibration_closed
                and timestamp_ms <= self._calibration_deadline):
            if angle <= self.config.standing_max_angle_deg:
                self._samples.append((timestamp_ms, center[1], standing_height))
        if (self._baseline_height is None and not self._calibration_closed
                and timestamp_ms >= self.config.calibration_ms
                and len(self._samples) >= self.config.calibration_min_samples):
            self._finalize_calibration()
        calibrated = self._baseline_height is not None
        if not calibrated:
            reason = ("standing_baseline_unavailable"
                      if self._calibration_closed or timestamp_ms > self._calibration_deadline
                      else "calibrating")
            return Observation(timestamp_ms, True, False, angle_deg=angle, reason=reason,
                               angle_3d_deg=angle_3d)
        drop_ratio = (center[1] - self._baseline_center) / self._baseline_height
        self.history.append((timestamp_ms, angle, drop_ratio))
        cutoff = timestamp_ms - self.config.history_ms
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()
        return Observation(timestamp_ms, True, True, angle_deg=angle, drop_ratio=drop_ratio,
                           angle_3d_deg=angle_3d)
