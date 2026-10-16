"""Extract real YOLO keypoints once; replay remains smooth on a CPU-only laptop."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vinfall.config import DATA, DEMO_SEQUENCES
from vinfall.pose import PoseExtractor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-only", action="store_true")
    args = parser.parse_args()
    extractor = PoseExtractor()
    videos = sorted(DATA.glob("*.mp4"))
    if args.demo_only:
        videos = [p for p in videos if any(p.stem.startswith(s + "-") for s in DEMO_SEQUENCES)]
    if not videos:
        raise SystemExit("No videos. Run scripts/download_data.py --full first.")
    for index, video in enumerate(videos, 1):
        data = extractor.extract(video)
        valid = (data["points"][:, :, 2] >= .25).sum(axis=1)
        print(f"[{index}/{len(videos)}] {video.name}: {len(valid)} samples, {float(data['duration']):.1f}s, valid {int((valid >= 8).sum())}", flush=True)


if __name__ == "__main__":
    main()
