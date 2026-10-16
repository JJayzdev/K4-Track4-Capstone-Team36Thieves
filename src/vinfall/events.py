"""Persistent room incidents, with camera-local person observations and alert kinds."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import uuid


class EventStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY, room_id TEXT NOT NULL, room_name TEXT NOT NULL,
            source TEXT NOT NULL, run_id TEXT NOT NULL, created_at TEXT NOT NULL,
            video_time REAL NOT NULL, cameras TEXT NOT NULL, acknowledged_at TEXT,
            UNIQUE(room_id, run_id))""")
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(alerts)")}
        if "available_cameras" not in columns:
            # Historical alerts were created when every source required both cameras.
            self.connection.execute("ALTER TABLE alerts ADD COLUMN available_cameras TEXT NOT NULL DEFAULT '[0,1]'")
        if "kind" not in columns:
            self.connection.execute("ALTER TABLE alerts ADD COLUMN kind TEXT NOT NULL DEFAULT 'fall'")
        if "observations" not in columns:
            self.connection.execute("ALTER TABLE alerts ADD COLUMN observations TEXT NOT NULL DEFAULT '[]'")
        self.connection.commit()

    def create(self, room_id, room_name, source, run_id, video_time, camera, available_cameras=None,
               kind='fall', details=None):
        with self.lock:
            available = set(available_cameras or [camera]) | {camera}
            observation = {**(details or {}), 'kind': kind, 'camera': camera, 'video_time': video_time}
            row = self.connection.execute("SELECT * FROM alerts WHERE room_id=? AND run_id=?", (room_id, run_id)).fetchone()
            if row:
                cameras = sorted(set(json.loads(row["cameras"])) | {camera})
                available.update(json.loads(row["available_cameras"]))
                observations = json.loads(row['observations'])
                if observation not in observations:
                    observations.append(observation)
                merged_kind = 'fall' if kind == 'fall' or row['kind'] == 'fall' else 'occlusion'
                self.connection.execute("UPDATE alerts SET cameras=?, available_cameras=?, kind=?, observations=? WHERE id=?",
                                        (json.dumps(cameras), json.dumps(sorted(available)), merged_kind,
                                         json.dumps(observations), row["id"]))
                self.connection.commit()
                return row["id"], False
            event_id = uuid.uuid4().hex
            self.connection.execute("""INSERT INTO alerts
                (id, room_id, room_name, source, run_id, created_at, video_time, cameras, available_cameras, kind, observations)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, room_id, room_name, source, run_id, datetime.now(timezone.utc).isoformat(), video_time,
                 json.dumps([camera]), json.dumps(sorted(available)), kind, json.dumps([observation])))
            self.connection.commit()
            return event_id, True

    def list(self, limit=200):
        with self.lock:
            rows = self.connection.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [{**dict(row), "cameras": json.loads(row["cameras"]),
                     "available_cameras": json.loads(row["available_cameras"]),
                     "observations": json.loads(row['observations'])} for row in rows]

    def acknowledge(self, event_id):
        with self.lock:
            cursor = self.connection.execute("UPDATE alerts SET acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?",
                                             (datetime.now(timezone.utc).isoformat(), event_id))
            self.connection.commit()
            return cursor.rowcount > 0

    def close(self):
        self.connection.close()
