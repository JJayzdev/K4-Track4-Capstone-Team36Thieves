"""Realtime interfaces: timestamps are elapsed monotonic capture time in ms."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .contracts import Detection


@dataclass(frozen=True)
class CapturedFrame:
    sequence: int
    timestamp_ms: float
    captured_at: float
    frame: Any


@dataclass(frozen=True)
class RealtimeSnapshot:
    status: str  # STARTING, RUNNING, STOPPING, STOPPED, ERROR
    frame: Any = None
    detection: Optional[Detection] = None
    events: Tuple[Dict[str, Any], ...] = ()
    frame_count: int = 0
    elapsed_ms: float = 0.0
    processing_ms: float = 0.0
    fps: float = 0.0
    frame_age_ms: float = 0.0
    error: str = ""
    csv_path: Optional[Path] = None
