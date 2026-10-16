"""Launch the local-only VinFall web demo with the current Python interpreter."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if __name__ == "__main__":
    raise SystemExit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
        "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=true",
        "--browser.gatherUsageStats=false"], cwd=ROOT))
