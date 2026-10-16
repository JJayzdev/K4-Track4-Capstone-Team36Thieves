"""Fetch a small declared multi-room Le2i subset from its public Kaggle mirror.

Mirror license metadata says Unknown: do not redistribute these videos or claim
clinical/hospital validation. Provenance is retained in the manifest.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vinfall.media import encode_browser_video

SOURCE = "https://www.kaggle.com/datasets/tuyenldvn/falldataset-imvia"
API = "https://www.kaggle.com/api/v1/datasets/download/tuyenldvn/falldataset-imvia/"
SELECTION = [
    ("R01", "dev", "Coffee_room_01", 1, "fall", 48, "Phòng có bàn ghế"),
    ("R02", "dev", "Home_01", 12, "fall", 161, "Phòng sinh hoạt"),
    ("R03", "dev", "Office", 14, "unknown", None, "Phòng làm việc"),
    ("R04", "dev", "Lecture_room", 27, "unknown", None, "Phòng rộng"),
    ("R05", "eval", "Coffee_room_01", 44, "fall", 54, "Phòng có bàn ghế"),
    ("R06", "eval", "Home_01", 24, "fall", 131, "Phòng sinh hoạt"),
    ("R07", "eval", "Home_02", 42, "normal", None, "Phòng sinh hoạt"),
    ("R08", "eval", "Home_02", 58, "normal", None, "Phòng sinh hoạt"),
]


def fetch(item):
    clip_id, split, room, number, label, onset_frame, title = item
    inner = "Lecture room" if room == "Lecture_room" else room
    prefix = f"{room}/{inner}" if room in ("Office", "Lecture_room") else f"{room}/{inner}/Videos"
    remote_name = f"{prefix}/video ({number}).avi"
    url = API + quote(remote_name, safe="")
    folder = ROOT / "data/multroom"
    folder.mkdir(parents=True, exist_ok=True)
    raw = folder / "raw" / f"{clip_id}.avi"
    raw.parent.mkdir(exist_ok=True)
    output = folder / f"{clip_id}.mp4"
    try:
        if not output.is_file():
            if not raw.is_file():
                partial = raw.with_suffix(".download")
                offset = partial.stat().st_size if partial.exists() else 0
                request = Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
                with urlopen(request, timeout=25) as response:
                    append = offset > 0 and response.status == 206
                    out = partial.open("ab" if append else "wb")
                    reported = offset // (2 * 1024 * 1024) if append else 0
                    with out:
                        while True:
                            block = response.read1(64 * 1024)
                            if not block:
                                break
                            out.write(block)
                            out.flush()
                            megabytes = out.tell() // (2 * 1024 * 1024)
                            if megabytes > reported:
                                reported = megabytes
                                print(f"DOWNLOADING {clip_id}: {out.tell() / 1024 / 1024:.1f} MB", flush=True)
                if zipfile.is_zipfile(partial):
                    with zipfile.ZipFile(partial) as archive:
                        names = [name for name in archive.namelist() if name.lower().endswith(".avi")]
                        if len(names) != 1:
                            raise ValueError("Expected exactly one AVI from single-file download")
                        with archive.open(names[0]) as source, raw.open("wb") as dest:
                            while True:
                                block = source.read(256 * 1024)
                                if not block:
                                    break
                                dest.write(block)
                else:
                    partial.replace(raw)
            import cv2
            source_capture = cv2.VideoCapture(str(raw))
            source_fps = source_capture.get(cv2.CAP_PROP_FPS)
            source_frames = int(source_capture.get(cv2.CAP_PROP_FRAME_COUNT))
            source_capture.release()
            if source_fps <= 0 or source_frames <= 0:
                raise ValueError("Source FPS or frame count is invalid; no guessing")
            encode_browser_video(raw, output)
        import cv2
        capture = cv2.VideoCapture(str(output))
        fps = capture.get(cv2.CAP_PROP_FPS)
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()
        if fps <= 0 or frames <= 0:
            raise ValueError("Downloaded clip has invalid FPS or no frames")
        result = {"id": clip_id, "split": split, "path": output.relative_to(ROOT).as_posix(),
                  "label": label, "crop": "full", "room": title, "room_source": room,
                  "hospital_footage": False, "onset_ms": (onset_frame - 1) * 1000 / fps if onset_frame else None,
                  "annotation": "Le2i provided onset frame (1-based)" if onset_frame else "No fall annotation" if label == "normal" else "Needs manual review",
                  "fps": fps, "frames": frames, "source": SOURCE, "source_file": remote_name,
                  "license": "Unknown in mirror metadata; original rights not verified",
                  "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
        print(f"READY {clip_id}: {title}, {frames} frames, {fps} FPS", flush=True)
        return result
    except Exception as exc:
        print(f"FAILED {clip_id}: {exc}", flush=True)
        return {"id": clip_id, "room": title, "split": split, "source_file": remote_name, "error": str(exc)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    results = {}
    pending = list(SELECTION)
    def save_manifest():
        manifest = {"source": SOURCE, "clinical_validation": False,
                    "clips": sorted([r for r in results.values() if "error" not in r], key=lambda r: r["id"]),
                    "failed_downloads": [r for r in results.values() if "error" in r]}
        target = ROOT / "data/hospital_manifest.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        return manifest
    for attempt in range(3):
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(fetch, item): item for item in pending}
            for future in as_completed(futures):
                result = future.result()
                results[result["id"]] = result
                save_manifest()
        pending = [item for item in pending if "error" in results[item[0]]]
        if not pending:
            break
        print(f"Retrying {len(pending)} incomplete downloads", flush=True)
    manifest = save_manifest()
    raise SystemExit(1 if manifest["failed_downloads"] else 0)
