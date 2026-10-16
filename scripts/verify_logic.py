"""Persist a labeled synthetic-observation alert/CSV smoke test; no video inference."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vinfall.config import Config
from vinfall.contracts import Observation
from vinfall.detector import FallDetector
from vinfall.event_log import EventLogger


if __name__ == "__main__":
    output = ROOT / "logs/acceptance/synthetic_logic"
    output.mkdir(parents=True, exist_ok=True)
    config = Config(**json.loads((ROOT / "configs/locked.json").read_text()))
    detector = FallDetector(config)
    transitions, alerts = [], []
    previous = None
    with EventLogger(output / "events.csv", "SYNTHETIC_OBSERVATIONS_NOT_VIDEO") as logger, \
            (output / "trace.jsonl").open("w", encoding="utf-8") as trace:
        for ts in range(0, 6001, 100):
            falling = ts >= 3000
            observation = Observation(ts, True, ts >= 2000,
                                      70.0 if falling else 10.0,
                                      .30 if falling else 0.0)
            detection = detector.update(observation)
            logger.write(detection)
            trace.write(json.dumps(asdict(detection)) + "\n")
            if detection.state != previous:
                transitions.append([ts, detection.state])
                previous = detection.state
            if detection.new_alert:
                alerts.append(ts)
    assert alerts == [4200], alerts
    assert len((output / "events.csv").read_text().splitlines()) == 2
    result = {"input_kind": "synthetic_observations_not_video", "status": "PASS",
              "alerts_ms": alerts, "transitions": transitions, "csv_event_rows": 1}
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
