"""Recorded-video demo with deterministic video time and run artifacts."""
import argparse
from dataclasses import asdict
import json
import hashlib
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import time
from .config import Config

ROOT = Path(__file__).resolve().parents[2]


def build_parser():
    p = argparse.ArgumentParser(description="VinFall recorded-video fall alert demo")
    p.add_argument("--source", required=True, help="Recorded video path")
    p.add_argument("--model", default=str(ROOT / "models/pose_landmarker_lite.task"))
    p.add_argument("--fps", type=float, help="Explicit FPS override")
    p.add_argument("--config", help="JSON Config field overrides")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--log", default=str(ROOT / "logs/events.csv"))
    p.add_argument("--trace", help="Per-frame JSONL trace")
    p.add_argument("--summary", help="JSON run summary")
    p.add_argument("--output", help="Annotated MP4 backup")
    p.add_argument("--replays", type=int, default=0)
    p.add_argument("--crop", choices=("full", "right-half"), default="full",
                   help="URFD preview videos place RGB in the right half")
    return p


def overlay(frame, detection, paused=False, ended=False):
    import cv2
    obs = detection.observation
    color = (30, 30, 240) if detection.state == "ALERT" else (0, 230, 240)
    angle = f"{obs.angle_deg:.1f}" if obs.angle_deg is not None else "--"
    drop = f"{obs.drop_ratio:.3f}" if obs.drop_ratio is not None else "--"
    lines = [f"VinFall | {detection.state} | {obs.timestamp_ms / 1000:.2f}s",
             f"angle: {angle} deg | drop: {drop}", "SPACE pause | R replay | Q quit"]
    if not obs.calibrated:
        lines.append("WAITING FOR STANDING BASELINE")
    if detection.state == "ALERT":
        lines.append("FALL SUSPECTED - CHECK PERSON")
    if paused or ended:
        lines.append("END OF VIDEO" if ended else "PAUSED")
    panel = frame.copy()
    cv2.rectangle(panel, (0, 0), (min(frame.shape[1], 650), 20 * len(lines) + 8), (20, 20, 20), -1)
    cv2.addWeighted(panel, 0.55, frame, 0.45, 0, dst=frame)
    for i, line in enumerate(lines):
        text_width = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0]
        scale = min(0.6, 0.6 * max(1, frame.shape[1] - 24) / max(1, text_width))
        cv2.putText(frame, line, (12, 20 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
    return frame


def run(args):
    import cv2
    from .video import VideoSource
    from .pose import PoseSession
    from .features import FeatureExtractor
    from .detector import FallDetector
    from .event_log import EventLogger
    overrides = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
    config = Config(**overrides)
    if args.replays < 0:
        raise ValueError("--replays must be nonnegative")
    if not Path(args.model).is_file():
        raise ValueError("Model missing. Run: python scripts/download_model.py")
    video = pose = logger = writer = trace = None
    sessions = []
    started = time.perf_counter()
    try:
        video = VideoSource(args.source, args.fps)
        if args.trace:
            Path(args.trace).parent.mkdir(parents=True, exist_ok=True)
            trace = open(args.trace, "w", encoding="utf-8")
        replay = 0
        while True:
            pose = PoseSession(args.model, config)
            features, detector = FeatureExtractor(config), FallDetector(config)
            log_path = Path(args.log)
            if replay:
                log_path = log_path.with_name(f"{log_path.stem}.replay{replay}{log_path.suffix}")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            logger = EventLogger(log_path, Path(args.source).stem)
            stats = {"replay": replay, "frames": 0, "valid_frames": 0, "calibrated_frames": 0,
                     "alerts_ms": [], "transitions": [], "fps": video.fps}
            previous_state = None
            paused = ended = restart = False
            last_frame = last_detection = None
            while True:
                if not paused and not ended:
                    ok, frame, timestamp = video.read()
                    if not ok:
                        ended = True
                    else:
                        if args.crop == "right-half":
                            frame = frame[:, frame.shape[1] // 2:].copy()
                        landmarks = pose.process(frame, timestamp)
                        height, width = frame.shape[:2]
                        obs = features.update(landmarks, width, height, timestamp)
                        detection = detector.update(obs)
                        logger.write(detection)
                        stats["frames"] += 1
                        stats["valid_frames"] += int(obs.landmarks_valid)
                        stats["calibrated_frames"] += int(obs.calibrated)
                        if detection.state != previous_state:
                            stats["transitions"].append([timestamp, detection.state])
                            print(f"{timestamp:.1f} ms: {detection.state}", flush=True)
                            previous_state = detection.state
                        if detection.new_alert:
                            stats["alerts_ms"].append(timestamp)
                        if trace:
                            trace.write(json.dumps({"replay": replay, **asdict(detection)}, allow_nan=False) + "\n")
                        pose.draw(frame, landmarks)
                        last_frame, last_detection = frame, detection
                        if args.output and replay == 0:
                            if writer is None:
                                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                                writer = cv2.VideoWriter(args.output, cv2.VideoWriter_fourcc(*"mp4v"), video.fps, (width, height))
                                if not writer.isOpened():
                                    raise ValueError(f"Cannot create output video: {args.output}")
                            writer.write(overlay(frame.copy(), detection))
                if ended and (args.headless or replay < args.replays):
                    restart = replay < args.replays
                    break
                if not args.headless:
                    if last_frame is not None:
                        cv2.imshow("VinFall Alert", overlay(last_frame.copy(), last_detection, paused, ended))
                    key = cv2.waitKey(max(1, round(1000 / video.fps))) & 0xFF
                    if key in (ord("q"), 27):
                        break
                    if key == ord("r"):
                        restart = True
                        break
                    if key == ord(" ") and not ended:
                        paused = not paused
                    if last_frame is not None and cv2.getWindowProperty("VinFall Alert", cv2.WND_PROP_VISIBLE) < 1:
                        break
            sessions.append(stats)
            if stats["frames"] == 0:
                raise ValueError("Video opened but contained no decodable frames")
            logger.close()
            logger = None
            pose.close()
            pose = None
            if not restart:
                break
            video.reset()
            replay += 1
        packages = {}
        for name in ("mediapipe", "opencv-contrib-python", "opencv-python", "numpy", "protobuf"):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                pass
        summary = {"source": str(args.source), "crop": args.crop, "model": str(args.model),
                   "model_sha256": hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
                   "packages": packages, "config": asdict(config), "sessions": sessions,
                   "processing_seconds": time.perf_counter() - started}
        if args.summary:
            Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
            Path(args.summary).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        for resource in (logger, pose, video):
            if resource is not None:
                resource.close()
        if writer is not None:
            writer.release()
        if trace is not None:
            trace.close()
        if not args.headless:
            cv2.destroyAllWindows()


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ValueError, OSError, RuntimeError, TypeError, ImportError) as exc:
        parser.exit(2, f"VinFall: {exc}\n")
