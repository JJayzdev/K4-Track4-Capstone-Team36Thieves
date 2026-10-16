from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "urfd"
CACHE = ROOT / "data" / "cache"
MODELS = ROOT / "models"
RUNTIME = ROOT / "runtime"
SAMPLE_FPS = 10
SEQUENCE_LENGTH = 16
DEMO_SEQUENCES = ["fall-01", "fall-03", "fall-06", "fall-09", "fall-10"]
EDGES = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
         (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]


def ensure_directories():
    for directory in (DATA, CACHE, MODELS, RUNTIME, RUNTIME / "evidence"):
        directory.mkdir(parents=True, exist_ok=True)

