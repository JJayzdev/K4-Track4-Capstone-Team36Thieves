"""Frozen demo thresholds; see acceptance report for measured limitations."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Config:
    visibility_min: float = 0.5
    calibration_ms: float = 2000.0
    calibration_min_samples: int = 15
    standing_max_angle_deg: float = 20.0
    history_ms: float = 2000.0
    angle_threshold_deg: float = 60.0
    rapid_drop_ratio: float = 0.25
    rapid_drop_window_ms: float = 700.0
    coincidence_window_ms: float = 1000.0
    low_pose_drop_ratio: float = 0.25
    confirmation_ms: float = 1200.0
    missing_reset_ms: float = 500.0
    use_world_tilt: bool = False
    calibration_grace_ms: float = 0.0

    def __post_init__(self):
        for name, value in self.__dict__.items():
            if name == "use_world_tilt":
                if not isinstance(value, bool):
                    raise ValueError("use_world_tilt must be a boolean")
                continue
            if name == "calibration_grace_ms":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError("calibration_grace_ms must be finite and non-negative")
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Config {name} must be finite and positive")
        if self.visibility_min > 1:
            raise ValueError("visibility_min must be <= 1")
        if not isinstance(self.calibration_min_samples, int):
            raise ValueError("calibration_min_samples must be an integer")
        if self.standing_max_angle_deg >= self.angle_threshold_deg or self.angle_threshold_deg > 90:
            raise ValueError("Require standing_max_angle_deg < angle_threshold_deg <= 90")
        if self.history_ms < self.rapid_drop_window_ms:
            raise ValueError("history_ms must cover rapid_drop_window_ms")
