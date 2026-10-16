"""Compare frozen pose model variants over one declared manifest split."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vinfall.analysis import analyze_video
from vinfall.config import Config


VARIANTS = ("lite", "full", "heavy")
RESULT_FIELDS = (
    "model_variant", "model_path", "model_sha256", "config_sha256", "clip_id", "split",
    "room", "expected", "onset_ms", "alert_ms", "latency_ms", "event_count", "status",
    "frame_count", "fps", "duration_seconds", "processing_seconds", "valid_pose_frames",
    "calibrated_frames", "pose_coverage", "calibrated_coverage", "source_path", "crop", "error",
)


def _resolve_path(value, relative_to):
    path = Path(value)
    if path.is_absolute():
        return path
    root_candidate = ROOT / path
    return root_candidate if root_candidate.exists() else relative_to / path


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _status(label, alerts, calibrated_frames):
    if label == "unknown":
        return "UNLABELED"
    if calibrated_frames == 0:
        return "INCONCLUSIVE_NO_CALIBRATION"
    if label == "fall":
        return "FALL_DETECTED" if alerts else "FALL_MISSED"
    return "FALSE_ALERT" if alerts else "NO_ALERT"


def _metrics(rows):
    result = {}
    for variant in VARIANTS:
        subset = [row for row in rows if row["model_variant"] == variant]
        completed = [row for row in subset if row["status"] != "ERROR"]
        total_frames = sum(row["frame_count"] or 0 for row in completed)
        valid_frames = sum(row["valid_pose_frames"] or 0 for row in completed)
        calibrated_frames = sum(row["calibrated_frames"] or 0 for row in completed)
        rooms = {}
        for row in subset:
            room_name = str(row["room"]) if row["room"] is not None else "unspecified"
            rooms.setdefault(room_name, []).append(row)
        room_metrics = {}
        for room_name, room_rows in rooms.items():
            valid_room_rows = [row for row in room_rows if row["status"] != "ERROR"]
            room_metrics[room_name] = {
                "independent_clip_count": len({row["clip_id"] for row in room_rows}),
                "calibrated_clip_count": sum((row["calibrated_frames"] or 0) > 0 for row in valid_room_rows),
                "uncalibrated_clip_count": sum((row["calibrated_frames"] or 0) == 0 for row in valid_room_rows),
                "fall_labeled_clip_count": sum(row["expected"] == "fall" for row in room_rows),
                "fall_detected_clip_count": sum(row["status"] == "FALL_DETECTED" for row in room_rows),
                "fall_missed_clip_count": sum(row["status"] == "FALL_MISSED" for row in room_rows),
                "fall_inconclusive_no_calibration_clip_count": sum(
                    row["expected"] == "fall" and row["status"] == "INCONCLUSIVE_NO_CALIBRATION"
                    for row in room_rows),
                "raw_fall_alert_clip_count": sum(row["expected"] == "fall" and row["event_count"] > 0
                                                  for row in room_rows),
                "false_alert_clip_count": sum(row["status"] == "FALSE_ALERT" for row in room_rows),
                "unknown_label_clip_count": sum(row["expected"] == "unknown" for row in room_rows),
            }
        result[variant] = {
            "clips": len(subset), "completed_clips": len(completed),
            "errors": sum(row["status"] == "ERROR" for row in subset),
            "fall_clips_detected": sum(row["status"] == "FALL_DETECTED" for row in subset),
            "fall_clips_missed": sum(row["status"] == "FALL_MISSED" for row in subset),
            "normal_clips_no_alert": sum(row["status"] == "NO_ALERT" for row in subset),
            "false_alerts": sum(row["status"] == "FALSE_ALERT" for row in subset),
            "unlabeled_clips": sum(row["status"] == "UNLABELED" for row in subset),
            "fall_labeled_clips": sum(row["expected"] == "fall" for row in subset),
            "raw_fall_alert_clips": sum(row["expected"] == "fall" and row["event_count"] > 0
                                         for row in subset),
            "inconclusive_no_calibration": sum(row["status"] == "INCONCLUSIVE_NO_CALIBRATION" for row in subset),
            "valid_pose_coverage": valid_frames / total_frames if total_frames else None,
            "calibrated_frame_coverage": calibrated_frames / total_frames if total_frames else None,
            "coverage_denominator_frames": total_frames,
            "by_room": room_metrics,
        }
    return result


def compare_models(manifest_path="data/manifest.json", variants=VARIANTS, split="dev",
                   output_dir="logs/model_comparison", config_path="configs/locked.json"):
    manifest_path = Path(manifest_path).resolve()
    config_path = _resolve_path(config_path, ROOT)
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("clips"), list):
        raise ValueError("Manifest must be a JSON object with a clips list")
    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    config = Config(**config_data)
    config_sha = _sha256(config_path)
    chosen = list(variants)
    if not chosen or any(name not in VARIANTS for name in chosen) or len(chosen) != len(set(chosen)):
        raise ValueError(f"variants must be unique values from: {', '.join(VARIANTS)}")
    clips = [clip for clip in manifest["clips"] if clip.get("split") == split]
    if not clips:
        raise ValueError(f"Manifest contains no clips for split '{split}'")

    model_paths = {variant: ROOT / "models" / f"pose_landmarker_{variant}.task" for variant in chosen}
    model_hashes = {variant: _sha256(path) if path.is_file() else None
                    for variant, path in model_paths.items()}
    rows = []
    for index, clip in enumerate(clips, start=1):
        clip_id = str(clip.get("id") or f"clip-{index}")
        if not clip.get("path") or clip.get("label") not in ("fall", "normal", "unknown"):
            raise ValueError(f"Clip {clip_id} must have path and label 'fall', 'normal', or 'unknown'")
        source_path = _resolve_path(clip["path"], manifest_path.parent)
        for variant in chosen:
            model_path = model_paths[variant]
            combo_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", clip_id)
            combo_dir = output_dir / variant / combo_name
            row = {
                "model_variant": variant, "model_path": str(model_path),
                "model_sha256": model_hashes[variant], "config_sha256": config_sha,
                "clip_id": clip_id, "split": split, "room": clip.get("room"),
                "expected": clip["label"], "onset_ms": clip.get("onset_ms"),
                "alert_ms": None, "latency_ms": None, "event_count": 0,
                "status": "ERROR", "frame_count": None, "fps": None,
                "duration_seconds": None, "processing_seconds": None,
                "valid_pose_frames": None, "calibrated_frames": None,
                "pose_coverage": None, "calibrated_coverage": None,
                "source_path": str(source_path), "crop": clip.get("crop", "full"), "error": "",
            }
            try:
                if not model_path.is_file():
                    raise FileNotFoundError(f"Model is missing: {model_path}")
                result = analyze_video(source_path, combo_dir, model_path, config, crop=row["crop"])
                row.update({
                    "frame_count": result.frame_count, "fps": result.fps,
                    "duration_seconds": result.duration_seconds,
                    "processing_seconds": result.processing_seconds,
                    "valid_pose_frames": result.valid_pose_frames,
                    "calibrated_frames": result.calibrated_frames,
                })
                row["pose_coverage"] = result.valid_pose_frames / result.frame_count if result.frame_count else None
                row["calibrated_coverage"] = result.calibrated_frames / result.frame_count if result.frame_count else None
                row["event_count"] = len(result.events)
                row["alert_ms"] = result.events[0]["video_timestamp_ms"] if result.events else None
                if row["alert_ms"] is not None and row["onset_ms"] is not None:
                    row["latency_ms"] = row["alert_ms"] - row["onset_ms"]
                row["status"] = _status(row["expected"], bool(result.events), result.calibrated_frames)
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    metrics = _metrics(rows)
    provenance = {
        "manifest_path": str(manifest_path), "manifest_sha256": _sha256(manifest_path),
        "split": split, "variants": chosen, "config_path": str(config_path),
        "config_sha256": config_sha, "config": asdict(config),
        "models": {name: {"path": str(model_paths[name]), "sha256": model_hashes[name]}
                   for name in chosen},
        "interpretation": "Coverage is the fraction of input frames with valid pose/calibration; it is not accuracy.",
        "metrics": metrics, "results": rows,
    }
    csv_path, json_path = output_dir / "comparison.csv", output_dir / "comparison.json"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/manifest.json")
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    parser.add_argument("--split", default="dev")
    parser.add_argument("--output-dir", default="logs/model_comparison")
    parser.add_argument("--config", default="configs/locked.json",
                        help="Config JSON; defaults to the frozen locked configuration")
    args = parser.parse_args(argv)
    report = compare_models(args.manifest, args.variants, args.split, args.output_dir,
                            args.config)
    print(json.dumps({"metrics": report["metrics"], "output_dir": str(Path(args.output_dir))}, indent=2))
    return 1 if any(row["status"] == "ERROR" for row in report["results"]) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
