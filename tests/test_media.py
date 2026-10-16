"""Exercise the actual browser codec conversion and preserve frame sequence."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from vinfall.media import encode_browser_video


class MediaTests(unittest.TestCase):
    def test_h264_preserves_frames_fps_and_order(self):
        import cv2
        import numpy as np
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 29.97, (160, 120))
            self.assertTrue(writer.isOpened())
            for index in range(20):
                frame = np.zeros((120, 160, 3), dtype=np.uint8)
                frame[:, :, 2] = index * 10
                writer.write(frame)
            writer.release()
            output = encode_browser_video(source, root / "result.mp4")
            capture = cv2.VideoCapture(str(output))
            self.assertAlmostEqual(capture.get(cv2.CAP_PROP_FPS), 29.97, places=2)
            colors = []
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                colors.append(float(frame[:, :, 2].mean()))
            capture.release()
            self.assertEqual(len(colors), 20)
            for index, color in enumerate(colors):
                self.assertAlmostEqual(color, index * 10, delta=8)
            info = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(output)],
                                  capture_output=True, text=True,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertIn("Video: h264", info.stderr)

    def test_invalid_input_raises_clear_encoding_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "H.264"):
                encode_browser_video(Path(directory) / "missing.mp4", Path(directory) / "result.mp4")
