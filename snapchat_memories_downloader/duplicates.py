from __future__ import annotations

import hashlib
import threading
from pathlib import Path


class DuplicateIndex:
    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path
        self._lock = threading.Lock()
        self._initialized = False
        self._size_to_paths: dict[int, set[Path]] = {}
        self._size_hash_to_path: dict[int, dict[str, Path]] = {}
        self._path_hash: dict[Path, str] = {}

    def build(self) -> None:
        self._ensure_initialized()

    def check_data(self, data: bytes) -> tuple[bool, str | None, str]:
        self._ensure_initialized()
        size = len(data)
        data_hash = compute_data_hash(data)

        with self._lock:
            hash_map = self._size_hash_to_path.get(size, {})
            cached_path = hash_map.get(data_hash)
            candidate_paths = list(self._size_to_paths.get(size, set()))

        if cached_path:
            if cached_path.exists():
                return True, cached_path.name, data_hash
            self._remove_path(cached_path, size)

        for path in candidate_paths:
            if not path.exists():
                self._remove_path(path, size)
                continue

            with self._lock:
                existing_hash = self._path_hash.get(path)

            if existing_hash is None:
                try:
                    existing_hash = compute_file_hash(path)
                except Exception:
                    self._remove_path(path, size)
                    continue

                with self._lock:
                    self._path_hash[path] = existing_hash
                    self._size_hash_to_path.setdefault(size, {})[existing_hash] = path

            if existing_hash == data_hash:
                return True, path.name, data_hash

        return False, None, data_hash

    def register_file(
        self,
        path: Path,
        *,
        data_hash: str | None = None,
        size: int | None = None,
    ) -> None:
        if not path.is_file():
            return
        if size is None:
            try:
                size = path.stat().st_size
            except OSError:
                return
        self._ensure_initialized()
        with self._lock:
            self._add_path_locked(path, size=size, data_hash=data_hash)

    def unregister_file(self, path: Path) -> None:
        self._remove_path(path)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._build_locked()
            self._initialized = True

    def _build_locked(self) -> None:
        if not self._output_path.exists():
            return
        for path in self._output_path.iterdir():
            self._add_path_locked(path)

    def _add_path_locked(
        self,
        path: Path,
        *,
        size: int | None = None,
        data_hash: str | None = None,
    ) -> None:
        if not path.is_file() or path.name == "metadata.json":
            return
        if size is None:
            try:
                size = path.stat().st_size
            except OSError:
                return
        self._size_to_paths.setdefault(size, set()).add(path)
        if data_hash is not None:
            self._path_hash[path] = data_hash
            self._size_hash_to_path.setdefault(size, {})[data_hash] = path

    def _remove_path(self, path: Path, size: int | None = None) -> None:
        with self._lock:
            if size is None:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = None

            if size is not None:
                paths = self._size_to_paths.get(size)
                if paths:
                    paths.discard(path)
                    if not paths:
                        self._size_to_paths.pop(size, None)

            existing_hash = self._path_hash.pop(path, None)
            if existing_hash and size is not None:
                hash_map = self._size_hash_to_path.get(size)
                if hash_map:
                    hash_map.pop(existing_hash, None)
                    if not hash_map:
                        self._size_hash_to_path.pop(size, None)


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


def check_duplicate(
    data: bytes,
    output_path: Path,
    check_duplicates: bool,
    duplicate_index: DuplicateIndex | None = None,
) -> tuple[bool, str | None, str | None]:
    if not check_duplicates:
        return (False, None, None)

    if duplicate_index is not None:
        is_dup, dup_name, data_hash = duplicate_index.check_data(data)
        return (is_dup, dup_name, data_hash)

    is_dup, dup_name = is_duplicate_file(data, output_path, check_duplicates)
    return (is_dup, dup_name, None)


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
