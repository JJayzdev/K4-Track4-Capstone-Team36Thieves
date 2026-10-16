from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import threading
import time
import uuid

import cv2
import httpx
import numpy as np

from .config import DATA, DEMO_SEQUENCES, RUNTIME, ensure_directories
from .events import EventStore
from .model import TemporalClassifier
from .pose import PoseExtractor, rgb_frame
from .tracking import PeopleMonitor, TrackingSettings

log = logging.getLogger(__name__)


@dataclass
class Camera:
    index: int
    path: Path | None
    data: dict
    monitor: PeopleMonitor
    cursor: int = -1


@dataclass
class Room:
    id: str
    name: str
    source: str
    delay: float
    cameras: list[Camera] = field(default_factory=list)
    duration: float = 0
    error: str | None = None
    loading: bool = False
    elapsed: float = 0
    alert_id: str | None = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: str = 'replay'
    incident_key: str | None = None
    incident_time: float = -100


class MonitorEngine:
    def __init__(self, runtime=RUNTIME):
        ensure_directories()
        self.runtime = Path(runtime)
        self.runtime.mkdir(parents=True, exist_ok=True)
        (self.runtime / "evidence").mkdir(exist_ok=True)
        self.events = EventStore(self.runtime / "alerts.sqlite3")
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.worker = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vinfall-tasks")
        self.rooms = [Room(str(101 + i), f"Phòng {101 + i}", source, i * 2.0) for i, source in enumerate(DEMO_SEQUENCES)]
        available = self.sources()
        saved = {}
        config = self.runtime / "rooms.json"
        if config.exists():
            try:
                saved = json.loads(config.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                log.warning("Invalid rooms.json; using default sources")
        for room in self.rooms:
            requested = saved.get(room.id, room.source)
            room.source = requested if requested in available else ""
        unused = iter(source for source in available if source not in {room.source for room in self.rooms})
        for room in self.rooms:
            if not room.source:
                room.source = next(unused, "")
        self.rooms.append(Room('106', 'Phòng 106 · Webcam laptop', 'webcam', 0, kind='live'))
        self.tracking_settings = TrackingSettings()
        settings_file = self.runtime / 'tracking.json'
        if settings_file.exists():
            try:
                self.tracking_settings = self.validate_tracking(json.loads(settings_file.read_text(encoding='utf-8')))
            except (OSError, ValueError, TypeError):
                log.warning('Invalid tracking.json; using default settings')
        self.live_lock = threading.Lock()
        self.clock = time.monotonic
        self.webcam_session = None
        self.webcam_started = 0
        self.webcam_received = None
        self.webcam_last_frames = {}
        self.playing = False
        self.speed = 1.0
        self.loop = False
        self.elapsed = 0.0
        self.status = "loading"
        self.message = "Đang nạp mô hình và phân tích video…"
        self.progress = 0
        self.extractor = None
        self.classifier = None
        self.webhook = os.environ.get("VINFALL_ALERT_WEBHOOK", "")
        self.webhook_status = "configured" if self.webhook else "disabled"

    @staticmethod
    def sources():
        return sorted({p.stem.rsplit("-cam", 1)[0] for p in DATA.glob("*.mp4")
                       if p.stem.endswith(("-cam0", "-cam1"))})

    @staticmethod
    def source_cameras(source):
        return [(index, path) for index in (0, 1)
                if (path := DATA / f"{source}-cam{index}.mp4").is_file()]

    def duration(self):
        return max((room.delay + room.duration for room in self.rooms
                    if room.kind == 'replay' and room.cameras and not room.error), default=0)

    def room(self, room_id):
        return next((room for room in self.rooms if room.id == room_id), None)

    def load_room(self, room, source):
        if room.kind == 'live':
            return
        cameras = []
        paths = self.source_cameras(source) if source else []
        if source and not paths:
            raise FileNotFoundError(f"Không có video cho nguồn {source}")
        for index, path in paths:
            data = self.extractor.extract_people(path)
            cameras.append(Camera(index, path, data, PeopleMonitor(self.classifier, self.replay_settings())))
        with self.lock:
            room.cameras = cameras
            room.duration = min((float(camera.data["duration"]) for camera in cameras), default=0)
            room.source = source
            room.error = None
            room.loading = False
            room.run_id = uuid.uuid4().hex
            room.alert_id = None
            room.elapsed = 0
            room.incident_key = None
            room.incident_time = -100

    def start(self):
        self.worker = threading.Thread(target=self.run, daemon=True, name="vinfall-monitor")
        self.worker.start()

    def close(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=15)
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.events.close()

    def run(self):
        try:
            self.classifier = TemporalClassifier()
            self.extractor = PoseExtractor()
            self.message = 'Đang khởi tạo xử lý webcam…'
            # Cached replay sources do not otherwise warm up YOLO. Do this before
            # advertising readiness so the first live frame does not stall tracking.
            self.extractor.infer([np.zeros((480, 640, 3), np.uint8)])
            for index, room in enumerate(self.rooms):
                self.message = f"Đang nạp {room.name} · {len(self.source_cameras(room.source)) if room.source else 0} camera"
                try:
                    self.load_room(room, room.source)
                except Exception as exc:
                    room.error = str(exc)
                    log.exception("Room initialization failed")
                self.progress = (index + 1) / len(self.rooms)
            self.status = "ready"
            self.message = "Sẵn sàng phát lại"
        except Exception as exc:
            self.status = "error"
            self.message = str(exc)
            log.exception("Monitor initialization failed")
        previous = time.monotonic()
        while not self.stop_event.wait(.08):
            now = time.monotonic()
            with self.lock:
                self.check_webcam_timeout(now)
                if self.playing and self.status == "ready":
                    self.elapsed += min(now - previous, .5) * self.speed
                    self.advance()
            previous = now

    def restart(self):
        self.elapsed = 0
        for room in self.rooms:
            if room.kind == 'live':
                continue
            room.run_id = uuid.uuid4().hex
            room.elapsed = 0
            room.alert_id = None
            room.incident_key = None
            room.incident_time = -100
            for camera in room.cameras:
                camera.cursor = -1
                camera.monitor.reset()

    def control(self, action, speed=None, loop=None):
        with self.lock:
            if self.status != "ready":
                raise ValueError("Video/model chưa sẵn sàng")
            if any(room.loading for room in self.rooms):
                raise ValueError("Đang đổi nguồn video, vui lòng chờ")
            if not any(room.kind == 'replay' and room.cameras and not room.error for room in self.rooms):
                raise ValueError("Không có bộ video hợp lệ")
            if speed is not None:
                if speed not in (.5, 1, 2):
                    raise ValueError("Tốc độ hỗ trợ: 0.5, 1, 2")
                self.speed = speed
            if loop is not None:
                self.loop = loop
            if action == "restart":
                self.restart()
                self.playing = True
            elif action == "play":
                if self.elapsed >= self.duration():
                    self.restart()
                self.playing = True
            elif action == "pause":
                self.playing = False
            elif action != "settings":
                raise ValueError("Unknown playback action")

    def advance(self):
        for room in self.rooms:
            if room.kind == 'live' or room.loading or room.error or not room.cameras:
                continue
            room.elapsed = min(max(self.elapsed - room.delay, 0), room.duration)
            if self.elapsed < room.delay:
                continue
            for camera in room.cameras:
                end = int(np.searchsorted(camera.data["times"], room.elapsed, side="right")) - 1
                while camera.cursor < end:
                    camera.cursor += 1
                    i = camera.cursor
                    timestamp = float(camera.data["times"][i])
                    start, stop = camera.data['offsets'][i:i + 2]
                    detections = [{'points': camera.data['points'][j], 'box': camera.data['boxes'][j],
                                   'appearance': camera.data['appearances'][j]} for j in range(start, stop)]
                    for details in camera.monitor.update(timestamp, detections, float(camera.data.get('aspect', 4 / 3))):
                        self.record_alert(room, camera, timestamp, details)
        available = [room for room in self.rooms if room.kind == 'replay' and room.cameras and not room.error]
        if available and all(self.elapsed >= room.delay + room.duration for room in available):
            if self.loop:
                self.restart()
            else:
                self.playing = False

    def record_alert(self, room, camera, timestamp, details, frame=None):
        details = {**details, 'camera': camera.index}
        # A short room incident joins views and retains every person's observation.
        # Later people/events can still alert without restarting a webcam session.
        if room.incident_key is None or abs(timestamp - room.incident_time) > 3:
            room.incident_key = f'{room.run_id}:{uuid.uuid4().hex}'
            room.incident_time = timestamp
        event_id, created = self.events.create(room.id, room.name, room.source, room.incident_key,
                                               timestamp, camera.index, [c.index for c in room.cameras],
                                               details['kind'], details)
        room.alert_id = event_id
        camera_sources = [(c.index, c.path) for c in room.cameras]
        last_frame = self.webcam_last_frames.get(details['track_id']) if frame is not None else None
        self.executor.submit(self.deliver_event, event_id, room.id, room.name, room.source, timestamp,
                             camera_sources, details, frame, last_frame, created)

    def deliver_event(self, event_id, room_id, room_name, source, timestamp, camera_sources,
                      details=None, frame=None, last_frame=None, notify=True):
        details = details or {'kind': 'fall'}
        if frame is not None and not (self.runtime / 'evidence' / f'{event_id}-cam0.jpg').exists():
            cv2.imwrite(str(self.runtime / 'evidence' / f'{event_id}-cam0.jpg'), frame)
        for index, path in camera_sources:
            if path is None or (self.runtime / 'evidence' / f'{event_id}-cam{index}.jpg').exists():
                continue
            capture = cv2.VideoCapture(str(path))
            try:
                capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                ok, frame = capture.read()
                if ok:
                    cv2.imwrite(str(self.runtime / "evidence" / f"{event_id}-cam{index}.jpg"), rgb_frame(frame))
            finally:
                capture.release()
        if details['kind'] == 'occlusion':
            track_id = details['track_id']
            index = details.get('camera', 0)
            if last_frame is None:
                source_path = next((p for i, p in camera_sources if i == index), None)
                if source_path:
                    capture = cv2.VideoCapture(str(source_path))
                    try:
                        capture.set(cv2.CAP_PROP_POS_MSEC, details['last_seen'] * 1000)
                        ok, image = capture.read()
                        if ok:
                            last_frame = rgb_frame(image)
                    finally:
                        capture.release()
            if last_frame is not None:
                evidence = last_frame.copy()
                if details.get('last_box'):
                    height, width = evidence.shape[:2]
                    x1, y1, x2, y2 = (np.clip(details['last_box'], 0, 1) * [width, height, width, height]).astype(int)
                    cv2.rectangle(evidence, (x1, y1), (x2, y2), (90, 220, 160), 2)
                    cv2.putText(evidence, f'ID {track_id}', (max(0, x1), max(18, y1-5)),
                                cv2.FONT_HERSHEY_SIMPLEX, .6, (90, 220, 160), 2)
                cv2.imwrite(str(self.runtime / 'evidence' / f'{event_id}-cam{index}-person{track_id}-last.jpg'), evidence)
        if self.webhook and notify:
            try:
                with httpx.Client(timeout=5) as client:
                    response = client.post(self.webhook, json={"event": "suspected_occluded_fall" if details['kind'] == 'occlusion' else "suspected_fall", "event_id": event_id,
                        "room_id": room_id, "room_name": room_name, "source": source, "video_time": timestamp,
                        "track_id": details.get('track_id'), "kind": details['kind'],
                        "details": details,
                        "message": f"Nghi té ngã do che khuất tại {room_name}" if details['kind'] == 'occlusion'
                        else f"Phát hiện nghi té ngã tại {room_name}"})
                    response.raise_for_status()
                self.webhook_status = "delivered"
            except Exception:
                self.webhook_status = "failed"
                log.warning("Alert webhook delivery failed; alert is retained locally")

    def change_source(self, room_id, source):
        with self.lock:
            room = self.room(room_id)
            if not room or room.kind != 'replay' or source not in self.sources():
                raise ValueError("Nguồn phải có ít nhất một video cam0 hoặc cam1")
            if self.status != "ready" or room.loading:
                raise ValueError("Hệ thống đang nạp dữ liệu")
            self.playing = False
            room.loading = True
        def task():
            try:
                self.load_room(room, source)
                with self.lock:
                    self.restart()
                    config = {r.id: r.source for r in self.rooms if r.kind == 'replay'}
                    (self.runtime / "rooms.json").write_text(json.dumps(config), encoding="utf-8")
            except Exception as exc:
                with self.lock:
                    room.error, room.loading = str(exc), False
        self.executor.submit(task)

    @staticmethod
    def validate_tracking(values):
        if not isinstance(values, dict):
            raise ValueError('Cấu hình theo dõi không hợp lệ')
        missing = float(values.get('missing_seconds', 8))
        minimum = float(values.get('minimum_seen', 1))
        margin = float(values.get('exit_margin', .08))
        zones = values.get('exit_zones', [])
        if not 2 <= missing <= 120 or not .5 <= minimum <= 10 or not .01 <= margin <= .25:
            raise ValueError('Mất dấu: 2–120 giây; quan sát: 0.5–10 giây; viền ra/vào: 1–25%')
        if not isinstance(zones, list) or len(zones) > 8:
            raise ValueError('Tối đa 8 vùng cửa ra/vào')
        for zone in zones:
            if not isinstance(zone, (list, tuple)) or len(zone) != 4:
                raise ValueError('Vùng cửa cần một hình chữ nhật hợp lệ')
            x1, y1, x2, y2 = zone
            if not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1:
                raise ValueError('Vùng cửa cần nằm trong khung hình')
        return TrackingSettings(missing, minimum, margin, zones)

    def replay_settings(self):
        s = self.tracking_settings
        return TrackingSettings(s.missing_seconds, s.minimum_seen, s.exit_margin)

    def configure_tracking(self, values):
        settings = self.validate_tracking(values)
        with self.lock:
            self.tracking_settings = settings
            for room in self.rooms:
                for camera in room.cameras:
                    camera.monitor.settings = settings if room.kind == 'live' else self.replay_settings()
            (self.runtime / 'tracking.json').write_text(json.dumps(vars(settings)), encoding='utf-8')

    def start_webcam(self):
        with self.lock:
            if self.status != 'ready' or self.classifier is None or self.extractor is None:
                raise ValueError('Mô hình chưa sẵn sàng')
            self.check_webcam_timeout(self.clock())
            if self.webcam_session:
                raise ValueError('Webcam đang được giám sát ở một tab khác. Dừng camera tại tab đó trước.')
            self.webcam_session = uuid.uuid4().hex
            self.webcam_started = self.clock()
            self.webcam_received = self.webcam_started
            self.webcam_last_frames.clear()
            room = self.room('106')
            room.cameras = [Camera(0, None, {}, PeopleMonitor(self.classifier, self.tracking_settings))]
            room.error = None
            room.elapsed = 0
            room.alert_id = None
            room.run_id = uuid.uuid4().hex
            room.incident_key = None
            room.incident_time = -100
            return self.webcam_session

    def stop_webcam(self, session):
        with self.lock:
            if session != self.webcam_session:
                raise ValueError('Phiên webcam đã hết hạn')
            self.webcam_session = None
            self.webcam_received = None
            self.webcam_last_frames.clear()
            room = self.room('106')
            room.cameras = []
            room.error = None
            room.alert_id = None

    def check_webcam_timeout(self, now):
        if self.webcam_session and self.webcam_received is not None and now - self.webcam_received > 5:
            # Stream loss/closing a tab is a camera fault, never a person's disappearance.
            self.webcam_session = None
            self.webcam_last_frames.clear()
            room = self.room('106')
            room.cameras = []
            room.error = 'Mất luồng webcam. Bật lại camera để tiếp tục giám sát.'

    def process_webcam(self, session, frame):
        if not self.live_lock.acquire(blocking=False):
            raise ValueError('Đang xử lý một khung hình khác')
        try:
            now = self.clock()
            with self.lock:
                self.check_webcam_timeout(now)
                if session != self.webcam_session or not session:
                    raise ValueError('Phiên webcam đã hết hạn')
                # Restart tracking after a transport gap. Never count a frozen stream as occlusion.
                if self.webcam_received is not None and now - self.webcam_received > 2:
                    self.room('106').cameras[0].monitor.reset()
                    self.webcam_last_frames.clear()
                self.webcam_received = now
            detections = self.extractor.infer([frame])[0]
            with self.lock:
                if session != self.webcam_session:
                    raise ValueError('Phiên webcam đã hết hạn')
                room = self.room('106')
                timestamp = now - self.webcam_started
                room.elapsed = timestamp
                camera = room.cameras[0]
                camera.data['aspect'] = frame.shape[1] / frame.shape[0]
                alerts = camera.monitor.update(timestamp, detections, camera.data['aspect'])
                retained = camera.monitor.people
                self.webcam_last_frames = {key: value for key, value in self.webcam_last_frames.items() if key in retained}
                for person in retained.values():
                    if person.last_seen == timestamp:
                        self.webcam_last_frames[person.id] = frame.copy()
                for details in alerts:
                    self.record_alert(room, camera, timestamp, details, frame.copy())
                return {'ok': True, 'people': camera.monitor.snapshot()}
        finally:
            self.live_lock.release()

    def snapshot(self):
        with self.lock:
            rooms = []
            for room in self.rooms:
                cameras = []
                for camera in room.cameras:
                    people = camera.monitor.snapshot()
                    visible = [p for p in people if p['visible']]
                    states = [p['state'] for p in people]
                    cameras.append({"index": camera.index,
                        "state": 'alert' if any(s in ('alert', 'occluded') for s in states) else
                        'suspected' if any(s in ('suspected', 'missing') for s in states) else 'observing',
                        'people': people, 'visible_count': len(visible),
                        'aspect': float(camera.data.get('aspect', 4 / 3)),
                        'video_url': None if room.kind == 'live' else
                        f"/api/rooms/{room.id}/video/{camera.index}?source={room.source}"})
                states = [c["state"] for c in cameras]
                state = ("error" if room.error else "offline" if room.kind == 'live' and not cameras else
                         "empty" if not room.source else "loading" if room.loading or not cameras else
                         "alert" if room.alert_id else "suspected" if "suspected" in states else
                         "unknown" if states and all(s == "unknown" for s in states) else "observing")
                rooms.append({"id": room.id, "name": room.name, "source": room.source, "state": state,
                    'kind': room.kind,
                    "error": room.error, "elapsed": room.elapsed, "duration": room.duration,
                    "waiting": room.kind == 'replay' and bool(cameras) and self.elapsed < room.delay,
                    "ended": room.kind == 'replay' and room.duration > 0 and room.elapsed >= room.duration,
                    "alert_id": room.alert_id, "cameras": cameras})
            return {"status": self.status, "message": self.message, "progress": self.progress,
                "playing": self.playing, "speed": self.speed, "loop": self.loop, "elapsed": self.elapsed,
                "duration": self.duration(),
                "rooms": rooms, "alerts": self.events.list(), "webhook": self.webhook_status,
                'tracking': vars(self.tracking_settings),
                'webcam': {'active': bool(self.webcam_session), 'room_id': '106'},
                "model": "YOLOv8n Pose + LSTM · Multi-person", "mode": "replay+live"}
