"""Download a fixed development/evaluation split from the official URFD source.

URFD: Kwolek & Kepski (2014), CC BY-NC-SA 4.0, non-commercial academic use.
See https://fenix.ur.edu.pl/~mkepski/ds/uf.html .
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

BASE = "https://fenix.ur.edu.pl/~mkepski/ds/data/"
ROOT = Path(__file__).resolve().parents[1] / "data" / "urfd"
SPLIT = {"dev": ["fall-01", "adl-01", "fall-04"],
         "eval": ["fall-02", "fall-03", "adl-02", "adl-03"]}


def download(item):
    split, name = item
    target = ROOT / split / (name + "-cam0.mp4")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size:
        return str(target)
    temporary = target.with_suffix(".download")
    try:
        with urlopen(BASE + target.name, timeout=45) as response, temporary.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        temporary.replace(target)
        return str(target)
    except Exception as exc:
        return f"FAILED {name}: {exc}"


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(download, [(s, n) for s, names in SPLIT.items() for n in names]):
            print(result, flush=True)
