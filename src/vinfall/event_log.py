"""CSV event log with one row per newly emitted alert."""
import csv
from pathlib import Path


class EventLogger:
    FIELDS = ("video_id", "event_id", "video_timestamp_ms", "angle_deg", "drop_ratio", "reason")

    def __init__(self, path, video_id):
        self.video_id = video_id
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDS, extrasaction="ignore")
        self._writer.writeheader()
        self._written = set()

    def write(self, detection):
        if self._file.closed or not detection.new_alert:
            return
        event_id = detection.event_id
        if event_id in self._written:
            return
        observation = detection.observation
        self._writer.writerow({
            "video_id": self.video_id,
            "event_id": event_id,
            "video_timestamp_ms": detection.timestamp_ms,
            "angle_deg": observation.angle_deg,
            "drop_ratio": observation.drop_ratio,
            "reason": detection.reason or observation.reason,
        })
        self._file.flush()
        self._written.add(event_id)

    def close(self):
        if not self._file.closed:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
