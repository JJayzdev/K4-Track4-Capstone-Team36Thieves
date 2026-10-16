"""Explicit hardware check; never saves camera images or video."""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vinfall.config import Config
from vinfall.realtime import RealtimeSession


def verify(camera_index=0):
    config = Config(**json.loads((ROOT / "configs/hospital_calibration_v3.json").read_text(encoding="utf-8")))
    directory = ROOT / "runs/webcam" / ("hardware-check-" + uuid.uuid4().hex)
    session = RealtimeSession(ROOT / "models/pose_landmarker_full.task", config,
                              directory, camera_index=camera_index)
    session.start()
    deadline = time.monotonic() + 90
    started = None
    snapshot = None
    try:
        while time.monotonic() < deadline:
            snapshot = session.snapshot()
            if snapshot.status == "ERROR":
                break
            if snapshot.frame_count:
                started = started or time.monotonic()
                if time.monotonic() - started >= 4:
                    break
            time.sleep(.1)
    finally:
        released = session.stop(timeout=5)
    final = session.snapshot(touch=False)
    evidence = {"camera_index": camera_index, "status": final.status, "released": released,
                "frame_count": final.frame_count, "elapsed_ms": final.elapsed_ms,
                "fps": final.fps, "processing_ms": final.processing_ms,
                "shape": list(final.frame.shape) if final.frame is not None else None,
                "last_capture_timestamp_ms": final.detection.timestamp_ms if final.detection else None,
                "detector_state": final.detection.state if final.detection else None,
                "events": list(final.events), "error": final.error,
                "csv": str(final.csv_path) if final.csv_path else None,
                "images_or_video_saved": False,
                "fall_detection_on_physical_camera_verified": False}
    destination = ROOT / "logs/webcam/hardware.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()
    result = verify(args.camera)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["frame_count"] > 0 and result["released"] and not result["error"] else 1)
