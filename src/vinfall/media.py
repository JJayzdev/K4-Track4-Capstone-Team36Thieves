"""Local H.264 encoding for browser playback, without resampling video frames."""
from pathlib import Path
import subprocess


def encode_browser_video(source, destination):
    import imageio_ffmpeg
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
               "-i", str(source), "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "fast",
               "-crf", "20", "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
               "-fps_mode", "passthrough", "-movflags", "+faststart", str(destination)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=600,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Không thể chuyển mã video cho trình duyệt. Kiểm tra FFmpeg và thử clip ngắn hơn.") from exc
    if completed.returncode or not destination.is_file() or not destination.stat().st_size:
        raise RuntimeError("Chuyển mã H.264 thất bại: " + completed.stderr.strip()[-1200:])
    return destination
