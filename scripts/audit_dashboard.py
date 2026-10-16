"""Audit actual prepared replay files against their frame traces and event CSVs."""
import csv
import hashlib
import json
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parents[1]


def audit():
    manifest = json.loads((ROOT / "runs/dashboard/current.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((ROOT / "configs" / manifest["config_name"]).read_bytes()).hexdigest() == manifest["config_sha256"]
    evidence = []
    paths = set()
    for room in manifest["rooms"]:
        assert room["trace_path"] not in paths, "Rooms must have isolated traces"
        paths.add(room["trace_path"])
        traces = [json.loads(line) for line in Path(room["trace_path"]).read_text(encoding="utf-8").splitlines()]
        assert len(traces) == room["frame_count"]
        for index, trace in enumerate(traces):
            assert abs(trace["timestamp_ms"] - index * 1000 / room["fps"]) < .001
        alerts = [t for t in traces if t["new_alert"]]
        with Path(room["csv_path"]).open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        assert len(rows) == len(alerts) == len(room["events"])
        assert len({r["event_id"] for r in rows}) == len(rows)
        for row, alert, event in zip(rows, alerts, room["events"]):
            assert abs(float(row["video_timestamp_ms"]) - alert["timestamp_ms"]) < .001
            assert abs(event["video_timestamp_ms"] - alert["timestamp_ms"]) < .001
        capture = cv2.VideoCapture(room["video_path"])
        assert capture.isOpened()
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = 0
        while capture.read()[0]:
            count += 1
        capture.release()
        assert count == room["frame_count"]
        assert abs(fps - room["fps"]) < .001
        evidence.append({"room": room["name"], "clip": room["clip_id"], "decoded_frames": count,
                         "fps": fps, "alerts_ms": [a["timestamp_ms"] for a in alerts],
                         "csv_matches_trace": True, "timestamps_match_frame_index": True})
    combined = list(csv.DictReader(Path(manifest["combined_csv"]).open(encoding="utf-8-sig", newline="")))
    assert len(combined) == sum(len(r["events"]) for r in manifest["rooms"])
    result = {"config_sha256": manifest["config_sha256"], "rooms": evidence, "combined_events": len(combined)}
    path = ROOT / "logs/web/dashboard_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
