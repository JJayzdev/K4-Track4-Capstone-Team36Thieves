"""Download the official YOLOv8n Pose weights and verify their SHA-256 digest."""
import hashlib
from pathlib import Path
from urllib.request import urlretrieve

URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt"
SHA256 = "c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212"
target = Path(__file__).resolve().parents[1] / "models" / "yolov8n-pose.pt"
if __name__ == "__main__":
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == SHA256:
        print(f"Already exists: {target}")
    else:
        temporary = target.with_suffix(".download")
        urlretrieve(URL, temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256:
            raise SystemExit("Model checksum mismatch; refusing to load the downloaded file")
        temporary.replace(target)
        print(f"Saved: {target}")
