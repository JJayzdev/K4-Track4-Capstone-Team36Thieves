"""Camera and pose baseline. Fall detection is deliberately not implemented yet."""
import argparse
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description="VinFall Alert: pose baseline")
    parser.add_argument("--source", default="0", help="Camera index or video path")
    parser.add_argument("--model", default=str(Path(__file__).resolve().parents[2] / "models" / "pose_landmarker_lite.task"))
    args = parser.parse_args()
    if not Path(args.model).is_file():
        parser.error("Model missing. Run: python scripts/download_model.py")

    import cv2
    import mediapipe as mp

    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=args.model),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=1,
    )
    source = int(args.source) if args.source.isdecimal() else args.source
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        capture.release()
        raise SystemExit(f"Cannot open input: {args.source}")
    last_timestamp = -1
    start = time.monotonic()
    edges = [(11, 12), (11, 23), (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28)]
    try:
        with mp.tasks.vision.PoseLandmarker.create_from_options(options) as detector:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                # Video timestamps follow media time; camera timestamps follow wall time.
                raw_timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) if isinstance(source, str) else (time.monotonic() - start) * 1000
                timestamp = max(last_timestamp + 1, int(raw_timestamp))
                last_timestamp = timestamp
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
                height, width = frame.shape[:2]
                for pose in result.pose_landmarks:
                    for a, b in edges:
                        if min(pose[a].visibility or 0, pose[b].visibility or 0) < 0.5:
                            continue
                        p1 = (int(pose[a].x * width), int(pose[a].y * height))
                        p2 = (int(pose[b].x * width), int(pose[b].y * height))
                        cv2.line(frame, p1, p2, (0, 220, 0), 2)
                status = "POSE TRACKED" if result.pose_landmarks else "NO POSE"
                cv2.putText(frame, status + " | Fall detector: TODO | Q: quit", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
                cv2.imshow("VinFall Alert", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
