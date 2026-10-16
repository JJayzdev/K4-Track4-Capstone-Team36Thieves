"""Temporal fall-candidate detector operating solely on video timestamps."""
from collections import deque
import math

from .config import Config
from .contracts import Detection, Observation


class FallDetector:
    """Combine rapid vertical drop and body tilt, then confirm a low pose."""

    def __init__(self, config: Config):
        self.config = config
        self.reset()

    def reset(self) -> None:
        self._last_timestamp = None
        self._history = deque()
        self._last_angle_evidence = None
        self._last_drop_evidence = None
        self._last_valid_timestamp = None
        self._previous_was_valid = False
        self._missing_since = None
        self._candidate = False
        self._confirm_ms = 0.0
        self._event_id = 0
        self._alert_latched = False

    def update(self, observation: Observation) -> Detection:
        ts = observation.timestamp_ms
        if not math.isfinite(ts):
            raise ValueError("observation timestamp must be finite")
        if (observation.angle_deg is not None and not math.isfinite(observation.angle_deg)):
            raise ValueError("observation angle must be finite")
        if (observation.drop_ratio is not None and not math.isfinite(observation.drop_ratio)):
            raise ValueError("observation drop ratio must be finite")
        if (observation.angle_3d_deg is not None and
                not math.isfinite(observation.angle_3d_deg)):
            raise ValueError("observation 3D angle must be finite")
        if self._last_timestamp is not None and ts <= self._last_timestamp:
            raise ValueError("observation timestamps must be strictly increasing")
        self._last_timestamp = ts

        if not observation.calibrated:
            self._history.clear()
            self._last_angle_evidence = self._last_drop_evidence = None
            self._candidate = False
            self._confirm_ms = 0.0
            self._last_valid_timestamp = None
            self._previous_was_valid = False
            self._missing_since = None
            state = "ALERT" if self._alert_latched else (
                "NO_DATA" if not observation.landmarks_valid else "CALIBRATING")
            return self._result(observation, state)

        valid = (observation.landmarks_valid and observation.angle_deg is not None
                 and observation.drop_ratio is not None)
        if not valid:
            if self._missing_since is None:
                self._missing_since = ts
                # Do not let an event seen before occlusion combine with evidence after it.
                self._history.clear()
                self._last_angle_evidence = self._last_drop_evidence = None
            self._previous_was_valid = False
            if (self._last_valid_timestamp is not None and
                    ts - self._last_valid_timestamp > self.config.missing_reset_ms):
                self._candidate = False
                self._confirm_ms = 0.0
            return self._result(observation, "ALERT" if self._alert_latched else "NO_DATA")

        if self._missing_since is not None:
            if (self._last_valid_timestamp is not None and
                    ts - self._last_valid_timestamp > self.config.missing_reset_ms):
                self._candidate = False
                self._confirm_ms = 0.0
            self._missing_since = None

        elif (self._last_valid_timestamp is not None and
              ts - self._last_valid_timestamp > self.config.missing_reset_ms):
            # Sparse input can hide a long period without an observation too.
            self._candidate = False
            self._confirm_ms = 0.0
            self._history.clear()
            self._last_angle_evidence = self._last_drop_evidence = None
            self._previous_was_valid = False

        image_angle, drop = observation.angle_deg, observation.drop_ratio
        world_angle = (observation.angle_3d_deg
                       if self.config.use_world_tilt else None)
        angle = max(image_angle, world_angle) if world_angle is not None else image_angle
        cutoff = ts - self.config.rapid_drop_window_ms
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()
        rapid_now = (bool(self._history) and
                     drop - min(x[1] for x in self._history) >= self.config.rapid_drop_ratio)
        rapid_before = (len(self._history) > 1 and
                        self._history[-1][1] - min(x[1] for x in list(self._history)[:-1])
                        >= self.config.rapid_drop_ratio)
        if rapid_now and not rapid_before:
            self._last_drop_evidence = ts
        if angle >= self.config.angle_threshold_deg:
            self._last_angle_evidence = ts
        self._history.append((ts, drop))

        coincidence = self.config.coincidence_window_ms
        has_angle = self._last_angle_evidence is not None and ts - self._last_angle_evidence <= coincidence
        has_drop = self._last_drop_evidence is not None and ts - self._last_drop_evidence <= coincidence
        was_candidate = self._candidate
        if has_angle and has_drop:
            if not self._candidate:
                self._confirm_ms = 0.0
                self._last_valid_timestamp = ts
                self._previous_was_valid = False
            self._candidate = True

        low_tilt = angle >= self.config.angle_threshold_deg and drop >= self.config.low_pose_drop_ratio
        if self._alert_latched:
            return self._result(observation, "ALERT")
        if self._candidate and low_tilt:
            if self._last_valid_timestamp is not None and self._previous_was_valid:
                # A missing interval is paused: the first valid frame after it adds no time.
                self._confirm_ms += max(0.0, ts - self._last_valid_timestamp)
            self._previous_was_valid = True
            if self._confirm_ms >= self.config.confirmation_ms:
                self._alert_latched = True
                self._event_id += 1
                self._candidate = False
                world_tilt_confirmed = (
                    world_angle is not None and
                    world_angle >= self.config.angle_threshold_deg and
                    image_angle < self.config.angle_threshold_deg)
                return self._result(observation, "ALERT", new_alert=True,
                                    event_id=self._event_id,
                                    reason=("rapid_drop_and_world_tilt_confirmed"
                                            if world_tilt_confirmed else
                                            "rapid_drop_and_tilt_confirmed"))
            self._last_valid_timestamp = ts
            return self._result(observation, "SUSPECTED")

        recovered = was_candidate and not low_tilt
        self._candidate = False
        self._confirm_ms = 0.0
        self._last_valid_timestamp = ts
        self._previous_was_valid = True
        if recovered:
            self._history.clear()
            self._last_angle_evidence = self._last_drop_evidence = None
        return self._result(observation, "NORMAL")

    def _result(self, observation, state, new_alert=False, event_id=None, reason=None):
        return Detection(observation.timestamp_ms, state, observation,
                         event_id=event_id, new_alert=new_alert,
                         reason=reason if reason is not None else observation.reason)
