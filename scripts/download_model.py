"""Download the official MediaPipe Pose Landmarker Lite model."""
from pathlib import Path
from urllib.request import Request, urlopen
import time
import zipfile
import argparse

URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
target = Path(__file__).resolve().parents[1] / "models" / "pose_landmarker_lite.task"
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download an official Google MediaPipe pose model")
    parser.add_argument("--variant", choices=("lite", "full", "heavy"), default="lite")
    args = parser.parse_args()
    URL = f"https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_{args.variant}/float16/1/pose_landmarker_{args.variant}.task"
    target = Path(__file__).resolve().parents[1] / "models" / f"pose_landmarker_{args.variant}.task"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print(f"Already exists: {target}")
    else:
        temporary = target.with_suffix(".download")
        for attempt in range(5):
            offset = temporary.stat().st_size if temporary.exists() else 0
            try:
                request = Request(URL, headers={"Range": f"bytes={offset}-"} if offset else {})
                with urlopen(request, timeout=30) as response:
                    append = offset > 0 and response.status == 206
                    with temporary.open("ab" if append else "wb") as out:
                        while True:
                            chunk = response.read(64 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                with zipfile.ZipFile(temporary) as archive:
                    if archive.testzip() is not None:
                        raise ValueError("Model archive checksum failed")
                temporary.replace(target)
                print(f"Saved: {target}", flush=True)
                break
            except Exception as exc:
                print(f"Attempt {attempt + 1}/5: {exc}; partial model retained", flush=True)
                if attempt == 4:
                    raise SystemExit("Model download failed; retry this command to resume")
                time.sleep(1)
