"""Actual YOLO inference and content-addressed caches, independent of event labels."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading

import cv2
import numpy as np

from .config import CACHE, MODELS, SAMPLE_FPS, ensure_directories

CACHE_VERSION = "yolov8n-pose-rgb384-10hz-v2"
FEATURE_SIZE = 57


def rgb_frame(frame: np.ndarray, combined: bool = True) -> np.ndarray:
    # UR's preview MP4s contain depth on the left and RGB on the right.
    return frame[:, frame.shape[1] // 2:].copy() if combined else frame


def features(points: np.ndarray, box: np.ndarray, aspect: float = 4 / 3) -> np.ndarray:
    """Translation/scale-normalized skeleton plus image-space motion context."""
    valid = points[:, 2] >= 0.25
    center = (points[11, :2] + points[12, :2]) / 2
    scale = max(float(box[3] - box[1]), 0.1)
    normalized = points.copy()
    normalized[:, :2] = (normalized[:, :2] - center) / scale
    normalized[:, 0] *= aspect / (4 / 3)
    normalized[~valid] = 0
    shoulder = (points[5, :2] + points[6, :2]) / 2
    torso = shoulder - center
    angle = np.arctan2(abs(torso[0]) * aspect / (4 / 3), abs(torso[1]) + 1e-6) / (np.pi / 2)
    context = [*center, (box[2] - box[0]) * aspect / (4 / 3), box[3] - box[1], angle, valid.mean()]
    return np.concatenate([normalized.flatten(), context]).astype(np.float32)


def cache_path(video: Path) -> Path:
    digest = hashlib.sha256(video.read_bytes()).hexdigest()[:16]
    return CACHE / f"{video.stem}-{digest}-{CACHE_VERSION}.npz"


class PoseExtractor:
    def __init__(self):
        ensure_directories()
        os.environ.setdefault("YOLO_CONFIG_DIR", str(MODELS / "ultralytics"))
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(min(4, os.cpu_count() or 2))
        self.model = YOLO(str(MODELS / "yolov8n-pose.pt"))
        self.lock = threading.Lock()

    def infer(self, frames):
        """Return all people; the live and replay paths use the same detections."""
        with self.lock:
            results = self.model.predict(frames, imgsz=384, conf=.3, verbose=False, device="cpu")
        people = []
        for frame, result in zip(frames, results):
            detections = []
            if result.keypoints is not None and len(result.boxes):
                boxes = result.boxes.xyxyn.cpu().numpy()
                xy = result.keypoints.xyn.cpu().numpy()
                confidence = result.keypoints.conf.cpu().numpy()
                for box, position, scores in zip(boxes, xy, confidence):
                    points = np.column_stack([position, scores]).astype(np.float32)
                    # Clothing colors help retain identity when detections change order.
                    h, w = frame.shape[:2]
                    x1, y1, x2, y2 = (box * [w, h, w, h]).astype(int)
                    crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
                    appearance = np.zeros(24, np.float32)
                    if crop.size:
                        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                        for channel, upper in enumerate((180, 256, 256)):
                            histogram = cv2.calcHist([hsv], [channel], None, [8], [0, upper]).flatten()
                            appearance[channel * 8:(channel + 1) * 8] = histogram / max(histogram.sum(), 1)
                    detections.append({'points': points, 'box': box.astype(np.float32), 'appearance': appearance})
            people.append(detections)
        return people

    def extract_people(self, video: Path):
        target = cache_path(video).with_name(cache_path(video).stem + '-all-people-v1.npz')
        if target.exists():
            with np.load(target, allow_pickle=False) as saved:
                return {key: saved[key] for key in saved.files}
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            raise ValueError(f"Cannot decode {video.name}")
        fps = capture.get(cv2.CAP_PROP_FPS) or 30
        stride = max(1, round(fps / SAMPLE_FPS))
        points, boxes, appearances, times, offsets = [], [], [], [], [0]
        pending, stamps = [], []
        aspect = 4 / 3

        def consume():
            for timestamp, detections in zip(stamps, self.infer(pending)):
                for detection in detections:
                    points.append(detection['points'])
                    boxes.append(detection['box'])
                    appearances.append(detection['appearance'])
                offsets.append(len(points))
                times.append(timestamp)
            pending.clear()
            stamps.clear()

        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % stride == 0:
                    image = rgb_frame(frame)
                    aspect = image.shape[1] / image.shape[0]
                    pending.append(image)
                    stamps.append(frame_index / fps)
                    if len(pending) == 8:
                        consume()
                frame_index += 1
            if pending:
                consume()
        finally:
            capture.release()
        if not times:
            raise ValueError(f"No frames decoded from {video.name}")
        data = {'points': np.asarray(points, dtype=np.float32).reshape(-1, 17, 3),
                'boxes': np.asarray(boxes, dtype=np.float32).reshape(-1, 4),
                'appearances': np.asarray(appearances, dtype=np.float32).reshape(-1, 24),
                'offsets': np.asarray(offsets), 'times': np.asarray(times),
                'duration': np.array(frame_index / fps), 'fps': np.array(fps),
                'frame_count': np.array(frame_index), 'aspect': np.array(aspect)}
        np.savez_compressed(target, **data)
        return data

    def extract(self, video: Path, progress=None) -> dict:
        """Single-person URFD training representation; monitoring uses extract_people."""
        target = cache_path(video)
        if target.exists():
            with np.load(target, allow_pickle=False) as saved:
                return {key: saved[key] for key in saved.files}
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            raise ValueError(f"Cannot decode {video.name}")
        fps = capture.get(cv2.CAP_PROP_FPS) or 30
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        stride = max(1, round(fps / SAMPLE_FPS))
        points, boxes, times, vectors = [], [], [], []
        pending, stamps = [], []

        def consume():
            with self.lock:
                predictions = self.model.predict(pending, imgsz=384, conf=0.3, verbose=False, device="cpu")
            for result, timestamp in zip(predictions, stamps):
                keypoints = np.zeros((17, 3), np.float32)
                box = np.zeros(4, np.float32)
                if result.keypoints is not None and len(result.boxes):
                    b = result.boxes.xyxyn.cpu().numpy()
                    sizes = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
                    index = int(np.argmax(sizes))
                    keypoints[:, :2] = result.keypoints.xyn[index].cpu().numpy()
                    keypoints[:, 2] = result.keypoints.conf[index].cpu().numpy()
                    box = b[index].astype(np.float32)
                points.append(keypoints)
                boxes.append(box)
                times.append(timestamp)
                vectors.append(features(keypoints, box))
            pending.clear()
            stamps.clear()

        try:
            frame_index = 0
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % stride == 0:
                    pending.append(rgb_frame(frame))
                    stamps.append(frame_index / fps)
                    if len(pending) == 8:
                        consume()
                        if progress:
                            progress(frame_index / max(count, 1))
                frame_index += 1
            if pending:
                consume()
        finally:
            capture.release()
        if not points:
            raise ValueError(f"No frames decoded from {video.name}")
        data = {"points": np.array(points), "boxes": np.array(boxes), "times": np.array(times),
                "features": np.array(vectors), "duration": np.array(frame_index / fps),
                "fps": np.array(fps), "frame_count": np.array(frame_index)}
        np.savez_compressed(target, **data)
        return data

