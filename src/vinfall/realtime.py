"""Threaded, latest-frame-only webcam inference for a single realtime session."""
from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from pathlib import Path
import threading
import time
from typing import Callable, Optional
import uuid

from .contracts import Detection
from .live_contracts import CapturedFrame, RealtimeSnapshot


_SESSION_LOCK = threading.Lock()


class CameraSource:
    """Drain one camera continuously and expose only the latest captured frame."""

    def __init__(self, camera_index=0, max_width=640, clock=time.monotonic,
                 capture_factory=None):
        self.camera_index = int(camera_index)
        self.max_width = int(max_width)
        if self.max_width <= 0:
            raise ValueError("max_width must be positive")
        self._clock = clock
        self._capture_factory = capture_factory
        self._condition = threading.Condition()
        self._stop_event = threading.Event()
        self._thread = None
        self._capture = None
        self._latest = None
        self._sequence = -1
        self._first_captured_at = None
        self._last_timestamp_ms = -1.0
        self._error = ""
        self._finished = False
        self._started = False

    @property
    def error(self):
        with self._condition:
            return self._error

    def start(self):
        with self._condition:
            if self._started:
                return False
            self._started = True
            self._thread = threading.Thread(target=self._capture_loop,
                                            name=f"VinFallCamera-{self.camera_index}", daemon=True)
            self._thread.start()
        return True

    def _make_capture(self, cv2, backend):
        if self._capture_factory is not None:
            try:
                return self._capture_factory(self.camera_index, backend)
            except TypeError as first_error:
                try:
                    return self._capture_factory(self.camera_index)
                except TypeError:
                    raise first_error
        if backend is None:
            return cv2.VideoCapture(self.camera_index)
        return cv2.VideoCapture(self.camera_index, backend)

    def _open_capture(self, cv2):
        attempts = []
        if hasattr(cv2, "CAP_DSHOW"):
            attempts.append((cv2.CAP_DSHOW, "DirectShow"))
        if hasattr(cv2, "CAP_MSMF"):
            attempts.append((cv2.CAP_MSMF, "Media Foundation"))
        if not attempts:
            attempts.append((None, "default"))
        failures = []
        for backend, label in attempts:
            if self._stop_event.is_set():
                return None
            capture = None
            try:
                capture = self._make_capture(cv2, backend)
                if capture is not None and capture.isOpened():
                    try:
                        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.max_width)
                    except Exception:
                        pass
                    self._capture = capture
                    return capture
                failures.append(label)
            except Exception as exc:
                failures.append(f"{label}: {exc}")
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass
        self._set_error(
            f"Không thể mở camera {self.camera_index}; hãy kiểm tra quyền truy cập hoặc đóng ứng dụng đang dùng camera."
        )
        return None

    def _set_error(self, message):
        with self._condition:
            if not self._error:
                self._error = str(message)
            self._condition.notify_all()

    def _capture_loop(self):
        capture = None
        try:
            if self._stop_event.is_set():
                return
            import cv2

            if self._stop_event.is_set():
                return
            capture = self._open_capture(cv2)
            if capture is None:
                return
            while not self._stop_event.is_set():
                ok, frame = capture.read()
                if not ok or frame is None:
                    if not self._stop_event.is_set():
                        self._set_error(f"Không đọc được khung hình từ camera {self.camera_index}.")
                    break
                captured_at = float(self._clock())
                if not math.isfinite(captured_at):
                    self._set_error("Đồng hồ capture camera trả về thời gian không hợp lệ.")
                    break
                try:
                    height, width = frame.shape[:2]
                    if width > self.max_width:
                        scaled_height = max(1, round(height * self.max_width / width))
                        frame = cv2.resize(frame, (self.max_width, scaled_height))
                except (AttributeError, TypeError, ValueError):
                    # Keep non-OpenCV test frames unchanged; real camera frames have shape.
                    pass
                with self._condition:
                    if self._first_captured_at is None:
                        self._first_captured_at = captured_at
                    timestamp_ms = max((captured_at - self._first_captured_at) * 1000.0,
                                       self._last_timestamp_ms + 0.001)
                    self._last_timestamp_ms = timestamp_ms
                    self._sequence += 1
                    self._latest = CapturedFrame(self._sequence, timestamp_ms, captured_at, frame)
                    self._condition.notify_all()
        except Exception as exc:
            self._set_error(f"Lỗi camera {self.camera_index}: {exc}")
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception as exc:
                    self._set_error(f"Không thể giải phóng camera {self.camera_index}: {exc}")
            with self._condition:
                self._capture = None
                self._finished = True
                self._condition.notify_all()

    def read_latest(self, after_sequence, timeout=0.2):
        timeout = max(0.0, float(timeout))
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                if self._latest is not None and self._latest.sequence > after_sequence:
                    return self._latest
                if self._finished or self._stop_event.is_set():
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)

    def request_stop(self):
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()

    def stop(self, timeout=2.0):
        self.request_stop()
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()


class RealtimeSession:
    """Own model, feature/detection state, event log, and one camera capture."""

    VALID_STATUSES = ("STARTING", "RUNNING", "STOPPING", "STOPPED", "ERROR")

    def __init__(self, model_path, config, output_dir, camera_index=0, max_width=640,
                 idle_timeout_s=20.0, source_factory=None, pose_factory=None,
                 clock=time.monotonic, start_delay_s=0.0):
        self.model_path = Path(model_path)
        self.config = config
        self.output_dir = Path(output_dir)
        self.camera_index = int(camera_index)
        self.max_width = int(max_width)
        self.idle_timeout_s = float(idle_timeout_s)
        self.start_delay_s = float(start_delay_s)
        if not math.isfinite(self.idle_timeout_s) or self.idle_timeout_s <= 0:
            raise ValueError("idle_timeout_s must be finite and positive")
        if not math.isfinite(self.start_delay_s) or self.start_delay_s < 0:
            raise ValueError("start_delay_s must be finite and non-negative")
        self._clock = clock
        self._source_factory = source_factory or CameraSource
        self._pose_factory = pose_factory
        self._status = "STOPPED"
        self._error = ""
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None
        self._source = None
        self._pose = None
        self._logger = None
        self._csv_path = None
        self._owns_session_lock = False
        self._started_once = False
        self._session_started_at = None
        self._last_touch = self._clock()
        self._last_sequence = -1
        self._frame = None
        self._detection: Optional[Detection] = None
        self._events = []
        self._frame_count = 0
        self._first_processed_timestamp_ms = None
        self._last_processed_timestamp_ms = None
        self._processing_ms = 0.0
        self._last_frame_captured_at = None

    @property
    def status(self):
        with self._lock:
            return self._status

    def start(self):
        with self._lock:
            if self._started_once or self._status not in ("STOPPED",):
                return False
            self._started_once = True
            if not _SESSION_LOCK.acquire(blocking=False):
                self._status = "ERROR"
                self._error = "Đang có một phiên camera VinFall khác hoạt động."
                return False
            self._owns_session_lock = True
            self._session_started_at = float(self._clock())
            self._last_touch = self._session_started_at
            self._status = "STARTING"
            self._thread = threading.Thread(target=self._run, name="VinFallRealtime", daemon=True)
            try:
                self._thread.start()
            except Exception as exc:
                self._status = "ERROR"
                self._error = f"Không thể khởi chạy phiên webcam: {exc}"
                self._release_session_lock()
                return False
        return True

    def _set_error(self, message):
        with self._lock:
            if not self._error:
                self._error = str(message)
            self._status = "ERROR"
            self._stop_event.set()

    def _make_pose(self):
        if self._pose_factory is not None:
            return self._pose_factory(self.model_path, self.config)
        from .pose import PoseSession
        return PoseSession(self.model_path, self.config)

    def _make_source(self):
        return self._source_factory(self.camera_index, self.max_width, self._clock)

    def _snapshot_frame(self, frame):
        if frame is None:
            return None
        try:
            return frame.copy()
        except AttributeError:
            return copy.copy(frame)

    def snapshot(self, touch=True):
        now = float(self._clock())
        with self._lock:
            if touch:
                self._last_touch = now
            # Detection timestamps begin with the first camera packet and stay
            # frozen when the session stops; model/start-delay time is excluded.
            elapsed_ms = self._detection.timestamp_ms if self._detection is not None else 0.0
            span_ms = ((self._last_processed_timestamp_ms - self._first_processed_timestamp_ms)
                       if self._frame_count > 1 else 0.0)
            fps = ((self._frame_count - 1) / (span_ms / 1000.0)
                   if span_ms > 0 else 0.0)
            frame_age_ms = (max(0.0, (now - self._last_frame_captured_at) * 1000.0)
                            if self._last_frame_captured_at is not None else 0.0)
            return RealtimeSnapshot(
                status=self._status,
                frame=self._snapshot_frame(self._frame),
                detection=self._detection,
                events=tuple(dict(event) for event in self._events),
                frame_count=self._frame_count,
                elapsed_ms=elapsed_ms,
                processing_ms=self._processing_ms,
                fps=fps,
                frame_age_ms=frame_age_ms,
                error=self._error,
                csv_path=self._csv_path,
            )

    def _run(self):
        from .detector import FallDetector
        from .event_log import EventLogger
        from .features import FeatureExtractor
        from .analysis import _overlay
        import cv2

        source = pose = logger = None
        try:
            # Construct the model before opening the camera, preserving startup frames.
            self._pose = pose = self._make_pose()
            features = FeatureExtractor(self.config)
            detector = FallDetector(self.config)
            if self._stop_event.wait(self.start_delay_s):
                return
            if self._stop_event.is_set():
                return
            if float(self._clock()) - self._last_touch >= self.idle_timeout_s:
                self._stop_event.set()
                return
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._csv_path = self.output_dir / f"events_{uuid.uuid4().hex}.csv"
            logger = EventLogger(self._csv_path, f"webcam-{self.camera_index}")
            self._logger = logger
            source = self._make_source()
            with self._lock:
                self._source = source
            if self._stop_event.is_set():
                return
            source.start()
            while not self._stop_event.is_set():
                now = float(self._clock())
                if now - self._last_touch >= self.idle_timeout_s:
                    self._stop_event.set()
                    break
                packet = source.read_latest(self._last_sequence, timeout=0.2)
                if packet is None:
                    if source.error:
                        self._set_error(source.error)
                        break
                    continue
                if packet.sequence <= self._last_sequence:
                    continue
                self._last_sequence = packet.sequence
                if self._stop_event.is_set():
                    break
                with self._lock:
                    self._status = "RUNNING"
                frame = self._snapshot_frame(packet.frame)
                process_started = float(self._clock())
                landmarks = pose.process(frame, packet.timestamp_ms)
                height, width = frame.shape[:2]
                observation = features.update(landmarks, width, height, packet.timestamp_ms)
                detection = detector.update(observation)
                logger.write(detection)
                if detection.new_alert:
                    event = {
                        "video_timestamp_ms": detection.timestamp_ms,
                        "event_id": detection.event_id,
                        "state": detection.state,
                        "reason": detection.reason,
                        "angle_deg": observation.angle_deg,
                        "angle_3d_deg": observation.angle_3d_deg,
                        "drop_ratio": observation.drop_ratio,
                    }
                else:
                    event = None
                pose.draw(frame, landmarks)
                rendered = _overlay(frame, detection)
                finished_at = float(self._clock())
                with self._lock:
                    self._frame_count += 1
                    if self._first_processed_timestamp_ms is None:
                        self._first_processed_timestamp_ms = packet.timestamp_ms
                    self._last_processed_timestamp_ms = packet.timestamp_ms
                    self._processing_ms = max(0.0, (finished_at - process_started) * 1000.0)
                    self._last_frame_captured_at = packet.captured_at
                    self._frame = rendered
                    self._detection = detection
                    if event is not None:
                        self._events.append(event)
            if source.error and not self._error:
                self._set_error(source.error)
        except Exception as exc:
            self._set_error(f"Lỗi khi chạy phân tích webcam: {exc}")
        finally:
            self._stop_event.set()
            # Keep the global session lock until the capture thread has released the device.
            if source is not None:
                try:
                    source.stop(timeout=None)
                except Exception as exc:
                    self._set_error(f"Lỗi khi dừng camera: {exc}")
            if logger is not None:
                try:
                    logger.close()
                except Exception as exc:
                    self._set_error(f"Lỗi khi đóng file log: {exc}")
            if pose is not None:
                try:
                    pose.close()
                except Exception as exc:
                    self._set_error(f"Lỗi khi giải phóng model tư thế: {exc}")
            with self._lock:
                self._status = "ERROR" if self._error else "STOPPED"
                self._source = None
                self._pose = None
                self._logger = None
            self._release_session_lock()

    def _release_session_lock(self):
        with self._lock:
            if self._owns_session_lock:
                self._owns_session_lock = False
                _SESSION_LOCK.release()

    def stop(self, timeout=2.0):
        with self._lock:
            if self._status in ("STARTING", "RUNNING", "ERROR"):
                self._status = "STOPPING"
            self._stop_event.set()
            source = self._source
            thread = self._thread
        if source is not None:
            try:
                if hasattr(source, "request_stop"):
                    source.request_stop()
                else:
                    source.stop(timeout=0.0)
            except Exception:
                pass
        if thread is None:
            # No worker means the session never acquired owned resources, or
            # its worker has already exited; in either case retry is safe.
            with self._lock:
                self._status = "ERROR" if self._error else "STOPPED"
            return True
        thread.join(timeout)
        with self._lock:
            if thread.is_alive():
                self._status = "STOPPING"
            else:
                self._status = "ERROR" if self._error else "STOPPED"
            # ERROR is terminal too: report success once cleanup has completed
            # so the UI can offer a fresh camera attempt.
            return not thread.is_alive()

