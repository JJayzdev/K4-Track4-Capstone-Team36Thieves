"""Run a declared clip manifest with fixed config; never tune on evaluation clips."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/manifest.json")
    parser.add_argument("--config", required=True)
    parser.add_argument("--split", choices=("dev", "eval"), default="eval")
    parser.add_argument("--output-dir", default="logs/evaluation")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for clip in manifest["clips"]:
        if clip["split"] != args.split:
            continue
        clip_id = clip["id"]
        summary = output / f"{clip_id}.json"
        command = [sys.executable, str(ROOT / "main.py"), "--source", clip["path"],
                   "--config", args.config, "--headless", "--crop", clip.get("crop", "full"),
                   "--log", str(output / f"{clip_id}.csv"), "--trace", str(output / f"{clip_id}.jsonl"),
                   "--summary", str(summary), "--output", str(output / f"{clip_id}.mp4")]
        with (output / f"{clip_id}.stdout.txt").open("w", encoding="utf-8") as stdout:
            result = subprocess.run(command, stdout=stdout, stderr=subprocess.STDOUT, cwd=ROOT)
        row = {"clip_id": clip_id, "expected": clip["label"], "onset_ms": clip.get("onset_ms"),
               "alert_ms": None, "latency_ms": None, "status": "ERROR", "notes": ""}
        if result.returncode == 0:
            session = json.loads(summary.read_text())["sessions"][0]
            alerts = session["alerts_ms"]
            alert = alerts[0] if alerts else None
            row["alert_ms"] = alert
            if alert is not None and row["onset_ms"] is not None:
                row["latency_ms"] = alert - row["onset_ms"]
            detected_correctly = bool(alerts) == (clip["label"] == "fall")
            timely = row["latency_ms"] is None or 0 <= row["latency_ms"] <= 3000
            row["status"] = "PASS" if detected_correctly and timely else "FAIL"
            row["notes"] = f"frames={session['frames']}; calibrated_frames={session['calibrated_frames']}; valid_frames={session['valid_frames']}"
            if clip["label"] == "normal" and session["calibrated_frames"] == 0 and not alerts:
                row["status"] = "INCONCLUSIVE"
                row["notes"] += "; no alert observed, but detector never calibrated"
            if clip["label"] == "fall" and row["onset_ms"] is None:
                row["status"] = "UNVERIFIED_LATENCY" if alerts else "FAIL"
        rows.append(row)
        print(row, flush=True)
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["clip_id"])
        writer.writeheader()
        writer.writerows(rows)
    provenance = {"config_sha256": hashlib.sha256(Path(args.config).read_bytes()).hexdigest(),
                  "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
                  "split": args.split, "results": rows}
    (output / "results.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return 0 if rows and all(r["status"] == "PASS" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
