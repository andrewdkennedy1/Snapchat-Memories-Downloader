from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_path(path: Path) -> None:
    """Open a file/folder with the OS default handler (Explorer/Finder/xdg-open)."""
    resolved = Path(path).expanduser().resolve()

    if sys.platform == "win32":
        os.startfile(str(resolved))  # type: ignore[attr-defined]
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(resolved)])
        return

    subprocess.Popen(["xdg-open", str(resolved)])

