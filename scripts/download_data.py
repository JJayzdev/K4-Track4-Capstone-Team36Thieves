"""Download the original paired RGB videos from the UR Fall Detection Dataset."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://fenix.ur.edu.pl/~mkepski/ds/data/"
DEMO_SEQUENCES = ["fall-01", "fall-03", "fall-06", "fall-09", "fall-10"]


def download(name: str, directory: Path) -> dict:
    destination = directory / name
    if not destination.exists() or destination.stat().st_size < 1000:
        for attempt in range(3):
            try:
                request = urllib.request.Request(BASE + name, headers={"User-Agent": "FallGuard-Research-Demo/1.0"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    partial = destination.with_suffix(destination.suffix + ".part")
                    with partial.open("wb") as handle:
                        while chunk := response.read(1024 * 256):
                            handle.write(chunk)
                partial.replace(destination)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
    print(f"OK {name} ({destination.stat().st_size:,} bytes)", flush=True)
    return {"file": name, "url": BASE + name, "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Also download 30 paired falls and 40 ADL videos for training")
    args = parser.parse_args()
    directory = ROOT / "data" / "urfd"
    directory.mkdir(parents=True, exist_ok=True)
    sequences = [f"fall-{i:02d}" for i in range(1, 31)] if args.full else DEMO_SEQUENCES
    names = [f"{sequence}-cam{camera}.mp4" for sequence in sequences for camera in (0, 1)]
    if args.full:
        names += [f"adl-{i:02d}-cam0.mp4" for i in range(1, 41)]
    names += ["urfall-cam0-falls.csv", "urfall-cam0-adls.csv"]
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(download, name, directory): name for name in names}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                raise RuntimeError(f"Failed to download {futures[future]}: {exc}") from exc
    manifest = {"dataset": "UR Fall Detection Dataset", "source": "https://fenix.ur.edu.pl/~mkepski/ds/uf.html",
                "description": "Original research videos; staged falls, not recordings of elderly patients.",
                "files": sorted(results, key=lambda item: item["file"])}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Downloaded {len(results)} files to {directory}", flush=True)


if __name__ == "__main__":
    main()
