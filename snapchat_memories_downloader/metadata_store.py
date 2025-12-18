from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

metadata_lock = threading.Lock()

_PROGRESS_FIELDS = {"status", "files", "error", "skip_reason"}


def initialize_metadata(memories: list, output_path: Path) -> list:
    metadata_file = output_path / "metadata.json"

    if metadata_file.exists():
        print("Found existing metadata.json, loading...")
        existing = _load_json(metadata_file)
        if existing is None:
            _backup_corrupt_file(metadata_file)
            print("Warning: metadata.json was invalid JSON; rebuilding it.")
            fresh = _build_fresh_metadata(memories)
            save_metadata(fresh, output_path)
            return fresh
        merged = _merge_or_rebuild_metadata(memories, existing)
        if merged is not existing:
            save_metadata(merged, output_path)
        return merged

    print("Creating initial metadata...")
    metadata_list = _build_fresh_metadata(memories)

    save_metadata(metadata_list, output_path)

    print(f"Initialized metadata for {len(metadata_list)} memories")
    return metadata_list


def save_metadata(metadata_list: list, output_path: Path) -> None:
    metadata_file = output_path / "metadata.json"
    tmp_file = output_path / "metadata.json.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(metadata_list, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    tmp_file.replace(metadata_file)


def _load_json(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Warning: Failed to parse {path.name}: {exc}")
        return None


def _backup_corrupt_file(metadata_file: Path) -> None:
    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = metadata_file.with_name(f"{metadata_file.stem}.corrupt-{ts}{metadata_file.suffix}")
        metadata_file.replace(backup)
        print(f"Backed up corrupt metadata to: {backup}")
    except Exception as exc:
        print(f"Warning: Could not back up corrupt metadata.json: {exc}")


def _build_fresh_metadata(memories: list[dict]) -> list[dict]:
    metadata_list: list[dict] = []
    for idx, memory in enumerate(memories, start=1):
        metadata_list.append(
            {
                "number": idx,
                "date": memory.get("date", "Unknown"),
                "media_type": memory.get("media_type", "Unknown"),
                "latitude": memory.get("latitude", "Unknown"),
                "longitude": memory.get("longitude", "Unknown"),
                "url": memory.get("url", ""),
                "status": "pending",
                "files": [],
            }
        )
    return metadata_list


def _looks_like_metadata_list(obj: Any) -> bool:
    if not isinstance(obj, list):
        return False
    if not obj:
        return True
    first = obj[0]
    return isinstance(first, dict) and "url" in first and "status" in first


def _merge_or_rebuild_metadata(memories: list[dict], existing: Any) -> list[dict]:
    fresh = _build_fresh_metadata(memories)

    if not _looks_like_metadata_list(existing):
        print("Warning: Existing metadata.json has an unknown format; rebuilding it.")
        return fresh

    existing_list: list[dict] = existing
    if len(existing_list) == len(fresh):
        existing_urls = [m.get("url") for m in existing_list]
        fresh_urls = [m.get("url") for m in fresh]
        if existing_urls == fresh_urls:
            return existing_list

    existing_by_url: dict[str, dict] = {}
    for item in existing_list:
        url = item.get("url")
        if isinstance(url, str) and url and url not in existing_by_url:
            existing_by_url[url] = item

    kept = 0
    for item in fresh:
        url = item.get("url")
        if isinstance(url, str) and url in existing_by_url:
            old = existing_by_url[url]
            for field in _PROGRESS_FIELDS:
                if field in old:
                    item[field] = old[field]
            kept += 1

    print(
        "Warning: Existing metadata.json does not match the selected HTML "
        f"({len(existing_list)} metadata entries vs {len(fresh)} parsed). "
        f"Rebuilding metadata and preserving progress for {kept} matching URLs."
    )
    return fresh
