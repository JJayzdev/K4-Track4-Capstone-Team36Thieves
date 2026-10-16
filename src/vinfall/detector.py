"""Per-person temporal fall confirmation with missing-pose handling and latching."""
from __future__ import annotations

from collections import deque
import math


class FallDetector:
    def __init__(self, threshold=.65, confirm_seconds=.3):
        self.threshold = threshold
        self.confirm_seconds = confirm_seconds
        self.reset()

    def reset(self):
        self.state = "observing"
        self.history = deque()
        self.candidate_since = None
        self.transition_at = None
        self.was_upright = False
        self.latched = False
        self.reference = None
        self.last_valid = None
        self.last_timestamp = None
        self.confirmed_duration = 0.0
        self.previous_confirming = False
        self.standing_height = 0.0

    def update(self, timestamp, probability, points, box, aspect=4 / 3):
        if self.latched:
            self.state = "alert"
            return False
        valid = min(points[i][2] for i in (5, 6, 11, 12)) >= .25
        if not valid:
            self.state = "unknown"
            self.previous_confirming = False
            # A short occlusion pauses confirmation; unseen time never counts.
            if self.last_valid is None or timestamp - self.last_valid > .35:
                self.candidate_since = None
                self.confirmed_duration = 0
                self.history.clear()
                self.transition_at = None
                self.was_upright = False
                self.reference = None
                self.standing_height = 0.0
            self.last_timestamp = timestamp
            return False
        if self.last_valid is not None and timestamp - self.last_valid > .35:
            self.candidate_since = None
            self.confirmed_duration = 0
            self.history.clear()
            self.transition_at = None
            self.was_upright = False
            self.reference = None
            self.standing_height = 0.0
        self.last_valid = timestamp
        shoulder = [(points[5][i] + points[6][i]) / 2 for i in (0, 1)]
        hip = [(points[11][i] + points[12][i]) / 2 for i in (0, 1)]
        angle = math.degrees(math.atan2(abs(shoulder[0] - hip[0]) * aspect, abs(shoulder[1] - hip[1]) + 1e-6))
        height = max(box[3] - box[1], .05)
        standing_shape = height / max((box[2] - box[0]) * aspect, .05) > 1.2
        stable_height = height >= self.standing_height * .85
        if angle < 25 and probability < self.threshold and standing_shape and stable_height:
            self.was_upright = True
            self.reference = (hip[1], height)
            self.standing_height = max(self.standing_height, height)
        while self.history and timestamp - self.history[0][0] > 1.0:
            self.history.popleft()
        if self.was_upright:
            for old_t, old_y, old_h, old_angle in self.history:
                if timestamp - old_t < .15:
                    continue
                drop = (hip[1] - old_y) / max(old_h, .05)
                if drop > .18 or (angle - old_angle > 30 and angle > 45) or height / old_h < .68:
                    self.transition_at = timestamp
                    break
        self.history.append((timestamp, hip[1], height, angle))
        recent_transition = self.transition_at is not None and timestamp - self.transition_at <= 2.5
        low_hip = self.reference is not None and (hip[1] - self.reference[0]) / self.reference[1] > .18
        if probability >= self.threshold and recent_transition and low_hip:
            if self.candidate_since is None:
                self.candidate_since = timestamp
            if self.previous_confirming and self.last_timestamp is not None:
                self.confirmed_duration += min(timestamp - self.last_timestamp, .15)
            self.state = "suspected"
            self.previous_confirming = True
            self.last_timestamp = timestamp
            if self.confirmed_duration >= self.confirm_seconds - 1e-6:
                self.latched = True
                self.state = "alert"
                return True
        else:
            self.candidate_since = None
            self.confirmed_duration = 0
            self.previous_confirming = False
            self.state = "observing"
        self.last_timestamp = timestamp
        return False

