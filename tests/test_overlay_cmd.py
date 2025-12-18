import unittest
from pathlib import Path

from snapchat_memories_downloader.overlay import build_ffmpeg_overlay_command


class TestOverlayCommand(unittest.TestCase):
    def test_image_overlay_uses_loop_input(self):
        cmd = build_ffmpeg_overlay_command(
            Path("main.mp4"),
            Path("overlay.png"),
            Path("out.mp4"),
            copy_audio=True,
        )
        cmd_str = " ".join(cmd)
        self.assertIn("-loop 1 -i overlay.png", cmd_str)
        self.assertIn("overlay=eof_action=pass", cmd_str)
        self.assertIn("scale2ref", cmd_str)

    def test_video_overlay_does_not_use_loop_input(self):
        cmd = build_ffmpeg_overlay_command(
            Path("main.mp4"),
            Path("overlay.mp4"),
            Path("out.mp4"),
            copy_audio=True,
        )
        cmd_str = " ".join(cmd)
        self.assertNotIn("-loop 1", cmd_str)
        self.assertIn("-i overlay.mp4", cmd_str)


if __name__ == "__main__":
    unittest.main()

