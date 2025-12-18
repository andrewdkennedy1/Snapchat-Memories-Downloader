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
import os
import zipfile
import shutil
import tempfile
from pathlib import Path

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


def _get_local_ffmpeg_path() -> Path:
    """Get the path to the local ffmpeg binary."""
    if getattr(sys, 'frozen', False):
        # If running as a frozen executable (e.g., PyInstaller)
        base_dir = Path(sys.executable).parent
    else:
        # Running from source
        base_dir = Path(__file__).parent.parent
        
    bin_dir = base_dir / "bin"
    if sys.platform == "win32":
        return bin_dir / "ffmpeg.exe"
    return bin_dir / "ffmpeg"


def _check_ffmpeg_available() -> str | None:
    """Check if ffmpeg is available on PATH or locally. Returns the path to the binary if found."""
    # 1. Check PATH
    try:
        if run_capture(["ffmpeg", "-version"], timeout=5).returncode == 0:
            return "ffmpeg"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2. Check local bin
    local_path = _get_local_ffmpeg_path()
    if local_path.exists():
        try:
            if run_capture([str(local_path), "-version"], timeout=5).returncode == 0:
                return str(local_path)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return None


ffmpeg_path = _check_ffmpeg_available()
ffmpeg_available = ffmpeg_path is not None

if not ffmpeg_available:
    print("Warning: ffmpeg not found. Video overlay merging will be disabled.")
    if sys.platform != "win32":
        print("Install: brew install ffmpeg (macOS) or apt-get install ffmpeg (Linux)")


def ensure_ffmpeg(interactive: bool = True) -> bool:
    """
    Ensure ffmpeg is available. If not, and on Windows, download it.
    Returns True if ffmpeg is available (after download if necessary).
    """
    global ffmpeg_path, ffmpeg_available
    
    if ffmpeg_available:
        return True
    
    if sys.platform != "win32":
        return False

    print("FFmpeg not found. Attempting to download it for Windows...")
    
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    local_bin = _get_local_ffmpeg_path().parent
    local_bin.mkdir(parents=True, exist_ok=True)
    
    try:
        import requests
        print(f"Downloading FFmpeg from {url}...")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            tmp_zip = tmp_file.name
            
        print("Extracting FFmpeg...")
        with zipfile.ZipFile(tmp_zip, 'r') as zip_ref:
            # Find the ffmpeg.exe in the zip
            ffmpeg_exe_member = None
            for member in zip_ref.namelist():
                if member.endswith("ffmpeg.exe"):
                    ffmpeg_exe_member = member
                    break
            
            if ffmpeg_exe_member:
                # Extract only the ffmpeg.exe to the local bin
                with zip_ref.open(ffmpeg_exe_member) as source, \
                     open(_get_local_ffmpeg_path(), "wb") as target:
                    shutil.copyfileobj(source, target)
                print(f"FFmpeg installed to {_get_local_ffmpeg_path()}")
            else:
                print("Error: Could not find ffmpeg.exe in the downloaded ZIP.")
                return False
                
        os.unlink(tmp_zip)
        
        # Re-check
        ffmpeg_path = _check_ffmpeg_available()
        ffmpeg_available = ffmpeg_path is not None
        return ffmpeg_available
        
    except Exception as e:
        print(f"Failed to download FFmpeg: {e}")
        return False
