from __future__ import annotations

import json
import threading
from pathlib import Path

metadata_lock = threading.Lock()


def initialize_metadata(memories: list, output_path: Path) -> list:
    metadata_file = output_path / "metadata.json"

    if metadata_file.exists():
        print("Found existing metadata.json, loading...")
        with open(metadata_file, "r", encoding="utf-8") as f:
            return json.load(f)

    print("Creating initial metadata...")
    metadata_list = []

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

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata_list, f, indent=2, ensure_ascii=False)

    print(f"Initialized metadata for {len(metadata_list)} memories")
    return metadata_list


def save_metadata(metadata_list: list, output_path: Path) -> None:
    metadata_file = output_path / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata_list, f, indent=2, ensure_ascii=False)

