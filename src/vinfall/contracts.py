"""Shared immutable pipeline interfaces; timestamps are video milliseconds."""
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from typing import List, Dict, Any


@dataclass(frozen=True)
class Observation:
    timestamp_ms: float
    landmarks_valid: bool
    calibrated: bool = False
    angle_deg: Optional[float] = None
    drop_ratio: Optional[float] = None
    reason: str = ""
    angle_3d_deg: Optional[float] = None


class PoseLandmarks(list):
    """Image landmarks retain list compatibility; world landmarks are optional."""
    def __init__(self, landmarks, world_landmarks=None):
        super().__init__(landmarks)
        self.world_landmarks = world_landmarks


@dataclass(frozen=True)
class Detection:
    timestamp_ms: float
    state: str
    observation: Observation
    event_id: Optional[int] = None
    new_alert: bool = False
    reason: str = ""


@dataclass(frozen=True)
class AnalysisResult:
    raw_video_path: Path
    csv_path: Path
    trace_path: Path
    summary_path: Path
    frame_count: int
    fps: float
    duration_seconds: float
    processing_seconds: float
    valid_pose_frames: int
    calibrated_frames: int
    events: List[Dict[str, Any]]
    warnings: List[str]
