"""Headless video analysis pipeline that produces reviewable run artifacts."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import time
from typing import Callable

from .contracts import AnalysisResult


def _overlay(frame, detection):
    """Draw a compact analysis-only HUD without importing UI controls."""
    import cv2

    obs = detection.observation
    color = (20, 25, 235) if detection.state == "ALERT" else (0, 220, 235)
    angle = f"{obs.angle_deg:.1f}" if obs.angle_deg is not None else "--"
    drop = f"{obs.drop_ratio:.3f}" if obs.drop_ratio is not None else "--"
    lines = [f"VinFall | {detection.state} | {detection.timestamp_ms / 1000:.2f}s",
             f"Angle: {angle} deg | Drop: {drop}"]
    if obs.angle_3d_deg is not None:
        lines.append(f"3D torso tilt: {obs.angle_3d_deg:.1f} deg")
    if not obs.calibrated:
        lines.append("WAITING FOR STANDING BASELINE")
    if detection.state == "ALERT":
        lines.append("FALL SUSPECTED - CHECK PERSON")
    panel = frame.copy()
    cv2.rectangle(panel, (0, 0), (min(frame.shape[1] - 1, 560), 18 * len(lines) + 8), (20, 20, 20), -1)
    cv2.addWeighted(panel, 0.58, frame, 0.42, 0, dst=frame)
    for i, line in enumerate(lines):
        available_width = max(1, frame.shape[1] - 20)
        measured_width = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        scale = min(0.5, 0.5 * available_width / max(1, measured_width))
        cv2.putText(frame, line, (10, 20 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, color, 1, cv2.LINE_AA)
    return frame


def analyze_video(source_path, output_dir, model_path, config, crop="full",
                  progress_callback: Callable[[int, int | None], None] | None = None) -> AnalysisResult:
    """Analyze one video; every call owns fresh model and detector state."""
    import cv2
    from .detector import FallDetector
    from .event_log import EventLogger
    from .features import FeatureExtractor
    from .pose import PoseSession
    from .video import VideoSource

    if crop not in ("full", "right-half"):
        raise ValueError("crop must be 'full' or 'right-half'")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path, model_path = Path(source_path), Path(model_path)
    if not model_path.is_file():
        raise ValueError(f"Model does not exist: {model_path}")
    raw_path = output_dir / "annotated_raw.mp4"
    csv_path = output_dir / "events.csv"
    trace_path = output_dir / "trace.jsonl"
    summary_path = output_dir / "summary.json"
    video = pose = writer = logger = trace = None
    started = time.perf_counter()
    frame_count = valid_frames = calibrated_frames = 0
    events, warnings = [], []
    try:
        video = VideoSource(source_path)
        # The source owns its capture; frame count is used only for progress reporting.
        total_frames = int(video._capture.get(cv2.CAP_PROP_FRAME_COUNT))
        total_frames = total_frames if total_frames > 0 else None
        features, detector = FeatureExtractor(config), FallDetector(config)
        logger = EventLogger(csv_path, source_path.stem)
        trace = trace_path.open("w", encoding="utf-8")
        while True:
            ok, frame, timestamp_ms = video.read()
            if not ok:
                break
            if pose is None:
                pose = PoseSession(model_path, config)
            if crop == "right-half":
                frame = frame[:, frame.shape[1] // 2:].copy()
            landmarks = pose.process(frame, timestamp_ms)
            height, width = frame.shape[:2]
            observation = features.update(landmarks, width, height, timestamp_ms)
            detection = detector.update(observation)
            logger.write(detection)
            if detection.new_alert:
                events.append({
                    "video_timestamp_ms": detection.timestamp_ms,
                    "event_id": detection.event_id,
                    "state": detection.state,
                    "reason": detection.reason,
                    "angle_deg": observation.angle_deg,
                    "angle_3d_deg": observation.angle_3d_deg,
                    "drop_ratio": observation.drop_ratio,
                })
            trace.write(json.dumps(asdict(detection), allow_nan=False) + "\n")
            pose.draw(frame, landmarks)
            annotated = _overlay(frame, detection)
            if writer is None:
                writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                         video.fps, (width, height))
                if not writer.isOpened():
                    raise ValueError(f"Cannot create output video: {raw_path}")
            writer.write(annotated)
            frame_count += 1
            valid_frames += int(observation.landmarks_valid)
            calibrated_frames += int(observation.calibrated)
            if progress_callback is not None:
                progress_callback(frame_count, total_frames)

        if frame_count == 0:
            raise ValueError("Video opened but contained no decodable frames")
        if valid_frames == 0:
            warnings.append("Không phát hiện được tư thế người trong video.")
        elif calibrated_frames == 0:
            deadline = (config.calibration_ms + config.calibration_grace_ms) / 1000
            warnings.append(f"Không đủ {config.calibration_min_samples} mẫu đứng hợp lệ trong {deadline:g} giây đầu để hiệu chuẩn; chọn clip thấy rõ toàn thân đứng trước khi ngã.")
        if frame_count and valid_frames / frame_count < 0.5:
            warnings.append("Tỷ lệ khung hình có tư thế hợp lệ thấp; kết quả có thể không đầy đủ.")
        processing_seconds = time.perf_counter() - started
        summary = {
            "source": str(source_path), "crop": crop, "model": str(model_path),
            "config": asdict(config), "frame_count": frame_count, "fps": video.fps,
            "duration_seconds": frame_count / video.fps,
            "processing_seconds": processing_seconds,
            "valid_pose_frames": valid_frames, "calibrated_frames": calibrated_frames,
            "events": events, "warnings": warnings,
        }
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return AnalysisResult(raw_path, csv_path, trace_path, summary_path, frame_count, video.fps,
                              frame_count / video.fps, processing_seconds, valid_frames,
                              calibrated_frames, events, warnings)
    finally:
        for resource in (logger, trace, writer, pose, video):
            if resource is not None:
                close = getattr(resource, "close", None)
                if close is not None:
                    close()
                elif hasattr(resource, "release"):
                    resource.release()
