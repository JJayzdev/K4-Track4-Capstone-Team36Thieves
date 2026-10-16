"""Read declared local demo clips; metadata never controls detection decisions."""
import json
from pathlib import Path


def available_samples(root, include_evaluation=False):
    root = Path(root).resolve()
    samples = []
    for name in ("hospital_manifest.json", "manifest.json"):
        path = root / "data" / name
        if not path.is_file():
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for clip in manifest.get("clips", []):
            candidate = (root / clip["path"]).resolve()
            if root not in candidate.parents or not candidate.is_file():
                continue
            item = dict(clip, absolute_path=candidate)
            if name == "manifest.json":
                if clip["split"] != "dev" and not include_evaluation:
                    continue
                item["id"] = "URFD-" + clip["id"]
                item["room"] = "Phòng có giường" if "adl-" in candidate.name else "Phòng làm việc URFD"
                item["hospital_footage"] = False
            samples.append(item)
    return samples
