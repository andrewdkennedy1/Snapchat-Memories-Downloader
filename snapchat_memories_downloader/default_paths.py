from __future__ import annotations

import sys
from pathlib import Path


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        unique.append(path)
        seen.add(path)
    return unique


def find_memories_history_html() -> Path | None:
    """
    Try to find a reasonable default memories_history.html without hardcoding a fixed folder.

    Checks the current working directory and the executable/script directory for:
      - memories_history.html
      - html/memories_history.html
    """
    bases: list[Path] = [Path.cwd()]

    try:
        bases.append(Path(sys.executable).parent)
    except Exception:
        pass

    try:
        if sys.argv and sys.argv[0]:
            bases.append(Path(sys.argv[0]).expanduser().resolve().parent)
    except Exception:
        pass

    for base in _unique_paths(bases):
        for candidate in (base / "memories_history.html", base / "html" / "memories_history.html"):
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def default_output_dir() -> Path:
    """Safe, portable default output directory (can be changed by the user)."""
    return Path.home() / "SnapchatMemories"


def suggest_output_dir_for_html(html_file: Path) -> Path:
    """Suggest an output folder near the export root based on the selected HTML file."""
    html_file = html_file.expanduser()
    parent = html_file.parent
    base = parent.parent if parent.name.lower() == "html" else parent
    return base / "memories"

