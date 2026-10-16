"""Exercise real pose/video pipeline with injected UI keys (no desktop required).

This verifies the control path, not physical keyboard/window interaction.
"""
import argparse
from contextlib import redirect_stdout, ExitStack
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vinfall.main import main


def verify():
    import cv2
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--crop", default="right-half")
    parser.add_argument("--output-dir", default="logs/controls")
    parser.add_argument("--show", action="store_true", help="Exercise an actual OpenCV window with automatic keys")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    common = ["--source", args.source, "--config", args.config, "--crop", args.crop]
    with (output / "stdout.txt").open("w", encoding="utf-8") as stream, redirect_stdout(stream):
        main(common + ["--headless", "--summary", str(output / "baseline.json"),
                       "--trace", str(output / "baseline.jsonl"), "--log", str(output / "baseline.csv")])
        count = 0
        replayed = False
        cap = cv2.VideoCapture(args.source)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        real_wait_key = cv2.waitKey

        def keys(_):
            nonlocal count, replayed
            if args.show:
                real_wait_key(1)
            count += 1
            if count == 10:
                return ord(" ")
            if count == 15:
                return ord(" ")
            # After EOF the last frame is held; request replay once, then quit.
            if count == frame_count + 10:
                replayed = True
                return ord("r")
            if replayed and count > 2 * frame_count + 20:
                return ord("q")
            return -1

        with ExitStack() as stack:
            stack.enter_context(patch.object(cv2, "waitKey", side_effect=keys))
            if not args.show:
                stack.enter_context(patch.object(cv2, "imshow"))
                stack.enter_context(patch.object(cv2, "getWindowProperty", return_value=1))
                stack.enter_context(patch.object(cv2, "destroyAllWindows"))
            main(common + ["--summary", str(output / "controlled.json"),
                           "--trace", str(output / "controlled.jsonl"), "--log", str(output / "controlled.csv")])
    baseline = json.loads((output / "baseline.json").read_text())["sessions"][0]
    controlled = json.loads((output / "controlled.json").read_text())["sessions"]
    fields = ("frames", "valid_frames", "calibrated_frames", "transitions", "alerts_ms")
    assert len(controlled) == 2, controlled
    assert all(all(s[f] == baseline[f] for f in fields) for s in controlled), "Control sequence changed detection"
    # Compare per-frame observation and detection fields, including timestamps.
    expected = [json.loads(line) for line in (output / "baseline.jsonl").read_text().splitlines()]
    actual = [json.loads(line) for line in (output / "controlled.jsonl").read_text().splitlines()]
    for session in range(2):
        records = [dict(r, replay=0) for r in actual if r["replay"] == session]
        assert records == expected, f"Trace mismatch on replay {session}"
    result = {"status": "PASS", "window_display_tested": args.show,
              "physical_keyboard_tested": False, "sessions": 2,
              "frames_per_session": baseline["frames"], "alerts_ms": baseline["alerts_ms"],
              "checks": ["pause_trace_equal", "manual_replay_trace_equal", "EOF_holds", "Q_returns_and_closes"]}
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    verify()
