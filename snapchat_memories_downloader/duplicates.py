from __future__ import annotations

import hashlib
from pathlib import Path


def compute_file_hash(file_path: Path) -> str:
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def compute_data_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def is_duplicate_file(
    data: bytes, output_path: Path, check_duplicates: bool
) -> tuple[bool, str | None]:
    if not check_duplicates:
        return (False, None)

    new_hash = compute_data_hash(data)
    new_size = len(data)

    for existing_file in output_path.iterdir():
        if existing_file.is_file() and existing_file.name != "metadata.json":
            try:
                existing_size = existing_file.stat().st_size
                if existing_size == new_size:
                    existing_hash = compute_file_hash(existing_file)
                    if existing_hash == new_hash:
                        return (True, existing_file.name)
            except Exception:
                continue

    return (False, None)


def detect_and_remove_duplicates(folder_path: Path) -> dict:
    print("\n" + "=" * 60)
    print("Scanning for duplicate files...")
    print("=" * 60)

    all_files = [f for f in folder_path.iterdir() if f.is_file() and f.name != "metadata.json"]

    if not all_files:
        print("No files found to check for duplicates")
        return {"duplicates_found": 0, "files_deleted": 0, "space_saved": 0}

    file_info: dict[Path, dict] = {}
    print(f"Analyzing {len(all_files)} files...")

    for file_path in all_files:
        try:
            stat = file_path.stat()
            md5 = compute_file_hash(file_path)
            file_info[file_path] = {"md5": md5, "size": stat.st_size, "mtime": stat.st_mtime}
        except Exception as e:
            print(f"  Warning: Could not analyze {file_path.name}: {e}")

    groups: dict[tuple, list[Path]] = {}
    for file_path, info in file_info.items():
        key = (info["md5"], info["size"], info["mtime"])
        groups.setdefault(key, []).append(file_path)

    duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}

    if not duplicate_groups:
        print("No duplicate files found!")
        return {"duplicates_found": 0, "files_deleted": 0, "space_saved": 0}

    total_duplicates = 0
    files_deleted = 0
    space_saved = 0

    print(f"\nFound {len(duplicate_groups)} duplicate group(s):")

    for (md5, size, _mtime), file_list in duplicate_groups.items():
        total_duplicates += len(file_list)
        print(f"\n  Duplicate group (MD5: {md5[:8]}..., Size: {size:,} bytes):")

        keep_file = file_list[0]
        print(f"    KEEP: {keep_file.name}")

        for dup_file in file_list[1:]:
            try:
                dup_file.unlink()
                files_deleted += 1
                space_saved += size
                print(f"    DELETED: {dup_file.name}")
            except Exception as e:
                print(f"    ERROR deleting {dup_file.name}: {e}")

    print("\n" + "=" * 60)
    print("Duplicate removal complete!")
    print(f"  Duplicate files found: {total_duplicates}")
    print(f"  Files deleted: {files_deleted}")
    print(f"  Space saved: {space_saved:,} bytes ({space_saved / (1024 * 1024):.2f} MB)")
    print("=" * 60)

    return {"duplicates_found": total_duplicates, "files_deleted": files_deleted, "space_saved": space_saved}

