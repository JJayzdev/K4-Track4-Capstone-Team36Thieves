"""Prepare isolated real analyses for a multi-room video replay dashboard."""
import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vinfall.analysis import analyze_video
from vinfall.config import Config
from vinfall.library import available_samples
from vinfall.media import encode_browser_video


def prepare(clip_ids, model_variant, config_path):
    samples = {item["id"]: item for item in available_samples(ROOT, include_evaluation=True)}
    missing = [clip for clip in clip_ids if clip not in samples]
    if missing:
        raise ValueError("Missing declared clips: " + ", ".join(missing))
    config_path = Path(config_path)
    config = Config(**json.loads(config_path.read_text(encoding="utf-8")))
    model = ROOT / f"models/pose_landmarker_{model_variant}.task"
    folder = ROOT / "runs/dashboard" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    rooms = []
    combined_events = []
    for index, clip_id in enumerate(clip_ids):
        clip = samples[clip_id]
        room_id = f"room-{index + 1:02d}"
        room_name = f"Phòng mô phỏng {index + 1:02d}"
        output = folder / room_id
        result = analyze_video(clip["absolute_path"], output, model, config, crop=clip.get("crop", "full"))
        video = encode_browser_video(result.raw_video_path, output / "browser.mp4")
        transitions = []
        previous = None
        with result.trace_path.open(encoding="utf-8") as trace:
            for line in trace:
                detection = json.loads(line)
                if detection["state"] != previous:
                    transitions.append([detection["timestamp_ms"], detection["state"]])
                    previous = detection["state"]
        rooms.append({"id": room_id, "name": room_name, "clip_id": clip_id,
                      "context": clip["room"] + " · video công khai",
                      "video_path": str(video), "csv_path": str(result.csv_path),
                      "trace_path": str(result.trace_path), "summary_path": str(result.summary_path),
                      "calibrated": result.calibrated_frames > 0, "warnings": result.warnings,
                      "frame_count": result.frame_count, "fps": result.fps,
                      "duration_seconds": result.duration_seconds, "events": result.events,
                      "transitions": transitions, "hospital_footage": False})
        combined_events.extend({"room_id": room_id, "room_name": room_name, "clip_id": clip_id, **event} for event in result.events)
        print(f"READY {room_name}: {clip_id}, {result.frame_count} frames, {len(result.events)} alerts", flush=True)
    fields = ["room_id", "room_name", "clip_id", "video_timestamp_ms", "event_id", "state", "reason", "angle_deg", "drop_ratio", "angle_3d_deg"]
    with (folder / "events_all_rooms.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(combined_events)
    manifest = {"model_variant": model_variant, "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                "config_name": config_path.name, "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                "config": asdict(config), "rooms": rooms, "clinical_validation": False,
                "combined_csv": str(folder / "events_all_rooms.csv")}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = ROOT / "runs/dashboard/current.json"
    temporary = latest.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(latest)
    return manifest


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", default="R01,R04,R03,URFD-D02")
    parser.add_argument("--variant", choices=("lite", "full", "heavy"), default="full")
    parser.add_argument("--config", default=str(ROOT / "configs/hospital_calibration_v3.json"))
    args = parser.parse_args()
    prepare([clip.strip() for clip in args.clips.split(",") if clip.strip()], args.variant, args.config)
