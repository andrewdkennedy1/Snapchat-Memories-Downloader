"""
Dependency checks and feature availability.

This project uses graceful degradation for optional features:
- Pillow (PIL) is optional: enables image overlay merging and broader image EXIF handling.
- piexif is optional: enables writing EXIF metadata.
- FFmpeg is optional (external binary): enables video overlay merging + multi-snap joining.

`requests` is required; we exit with a clear message if it's missing.
"""

from __future__ import annotations

import subprocess
import sys

from .subprocess_utils import run_capture

try:
    import requests  # type: ignore
except ImportError:
    print("Error: requests library not found!")
    print("Please install it with: pip install -r requirements.txt")
    sys.exit(1)

try:
    from PIL import Image  # type: ignore
except ImportError:
    print("Warning: Pillow not found. Overlay merging will be disabled.")
    print("Install with: pip install -r requirements.txt")
    Image = None  # type: ignore[assignment]

try:
    import piexif  # type: ignore
except ImportError:
    print("Warning: piexif not found. EXIF metadata writing will be disabled.")
    print("Install with: pip install -r requirements.txt")
    piexif = None  # type: ignore[assignment]


def _check_ffmpeg_available() -> bool:
    try:
        return (
            run_capture(["ffmpeg", "-version"], timeout=5).returncode
            == 0
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


ffmpeg_available = _check_ffmpeg_available()
if not ffmpeg_available:
    print("Warning: ffmpeg not found. Video overlay merging will be disabled.")
    print("Install: brew install ffmpeg (macOS) or apt-get install ffmpeg (Linux)")
