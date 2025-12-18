from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


_WINDOWS_RESERVED_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Keep filenames Windows/NTFS safe even when running on Linux (e.g. WSL on /mnt/c).
# Windows forbids: <>:"/\|?* and ASCII control chars; it also forbids trailing spaces/dots.
_WINDOWS_FILENAME_TRANSLATION = {
    **{ord(c): "_" for c in '<>"/\\|?*'},
    ord(":"): ".",  # keep timestamps readable: HH.MM.SS instead of HH_MM_SS
    **{i: "_" for i in range(32)},  # control chars 0-31
}


def get_file_extension(media_type: str) -> str:
    if media_type == "Video":
        return ".mp4"
    return ".jpg"


def parse_date_to_timestamp(date_str: str) -> float | None:
    try:
        date_str_clean = date_str.replace(" UTC", "")
        dt = datetime.strptime(date_str_clean, "%Y-%m-%d %H:%M:%S")
        return dt.timestamp()
    except (ValueError, AttributeError) as e:
        print(f"    Warning: Could not parse date '{date_str}': {e}")
        return None


def set_file_timestamp(file_path: Path, timestamp: float | None) -> None:
    if timestamp:
        os.utime(file_path, (timestamp, timestamp))


def make_filesystem_safe_stem(stem: str) -> str:
    safe = stem.translate(_WINDOWS_FILENAME_TRANSLATION)
    safe = safe.strip().rstrip(" .")

    if not safe:
        safe = "file"

    base = safe.split(".", 1)[0].upper()
    if base in _WINDOWS_RESERVED_DEVICE_NAMES:
        safe = f"_{safe}"

    return safe


def generate_filename(
    date_str: str,
    extension: str,
    use_timestamp: bool = False,
    fallback_num: str = "00",
) -> str:
    if use_timestamp:
        try:
            date_str_clean = date_str.replace(" UTC", "").strip()
            parts = date_str_clean.split(" ")
            if len(parts) == 2:
                date_part = parts[0].replace("-", ".")
                time_part = parts[1]
                stem = make_filesystem_safe_stem(f"{date_part}-{time_part}")
                return f"{stem}{extension}"
            print(f"    Warning: Unexpected date format '{date_str}', using sequential number")
            return f"{fallback_num}{extension}"
        except Exception as e:
            print(
                f"    Warning: Could not parse date for filename '{date_str}': {e}, using sequential number"
            )
            return f"{fallback_num}{extension}"

    stem = make_filesystem_safe_stem(str(fallback_num))
    return f"{stem}{extension}"
