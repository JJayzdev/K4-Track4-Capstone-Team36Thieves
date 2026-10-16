"""Download the official MediaPipe Pose Landmarker Lite model."""
from pathlib import Path
from urllib.request import urlretrieve

URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
target = Path(__file__).resolve().parents[1] / "models" / "pose_landmarker_lite.task"
if __name__ == "__main__":
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print(f"Already exists: {target}")
    else:
        temporary = target.with_suffix(".download")
        urlretrieve(URL, temporary)
        temporary.replace(target)
        print(f"Saved: {target}")
