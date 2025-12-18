from __future__ import annotations

import io
import zipfile
from pathlib import Path

from . import deps
from .duplicates import is_duplicate_file
from .exif_utils import add_exif_metadata
from .files import generate_filename, parse_date_to_timestamp, set_file_timestamp
from .magic_bytes import detect_file_kind, extension_for_kind
from .overlay import merge_image_overlay, merge_video_overlay


def is_zip_file(content: bytes) -> bool:
    return content[:2] == b"PK"


def download_and_extract(
    url: str,
    base_path: Path,
    file_num: str,
    extension: str,
    merge_overlays: bool = False,
    defer_video_overlays: bool = False,
    date_str: str = "Unknown",
    latitude: str = "Unknown",
    longitude: str = "Unknown",
    overlays_only: bool = False,
    use_timestamp_filenames: bool = False,
    check_duplicates: bool = False,
) -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    response = deps.requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    content = response.content
    files_saved: list[dict] = []

    if len(content) < 100:
        print(
            f"    WARNING: Downloaded file is very small ({len(content)} bytes) - may be invalid or expired URL"
        )

    if is_zip_file(content):
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            filenames = zf.namelist()
            has_overlay = any("-overlay" in f.lower() for f in filenames)

            if overlays_only and not has_overlay:
                return []

            extracted_files: dict[str, dict] = {}
            main_file = None
            overlay_file = None

            for zip_info in filenames:
                file_data = zf.read(zip_info)
                original_ext = Path(zip_info).suffix
                if "-overlay" in zip_info.lower():
                    overlay_file = file_data
                    extracted_files["overlay"] = {"data": file_data, "ext": original_ext}
                else:
                    main_file = file_data
                    extracted_files["main"] = {"data": file_data, "ext": original_ext}

            main_ext = extracted_files.get("main", {}).get("ext") or extension
            is_image = str(main_ext).lower() in [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
                ".bmp",
                ".tiff",
                ".tif",
            ]
            is_video = str(main_ext).lower() in [".mp4", ".mov", ".avi"]
            merge_attempted = False

            if merge_overlays and has_overlay and main_file and overlay_file:
                if is_image and deps.Image is not None:
                    try:
                        merged_data = merge_image_overlay(main_file, overlay_file)
                        merged_data = add_exif_metadata(
                            merged_data, date_str, latitude, longitude
                        )

                        is_dup, dup_file = is_duplicate_file(
                            merged_data, base_path, check_duplicates
                        )
                        if is_dup and dup_file:
                            print(f"    Skipped: Duplicate of existing file '{dup_file}'")
                            files_saved.append(
                                {
                                    "path": dup_file,
                                    "size": len(merged_data),
                                    "type": "duplicate",
                                    "duplicate_of": dup_file,
                                }
                            )
                            merge_attempted = True
                        else:
                            output_filename = generate_filename(
                                date_str, extension, use_timestamp_filenames, file_num
                            )
                            output_path = base_path / output_filename
                            with open(output_path, "wb") as f:
                                f.write(merged_data)
                            files_saved.append(
                                {
                                    "path": output_filename,
                                    "size": len(merged_data),
                                    "type": "merged",
                                }
                            )
                            merge_attempted = True
                    except Exception as e:
                        print(f"    Warning: Failed to merge image overlay: {e}")
                        print("    Saving separate files instead...")
                        merge_overlays = False

                elif is_video and deps.ffmpeg_available and not defer_video_overlays:
                    try:
                        main_ext = extracted_files.get("main", {}).get("ext") or extension
                        overlay_ext = extracted_files.get("overlay", {}).get("ext") or ".png"

                        temp_main = base_path / f"{file_num}-temp-main{main_ext}"
                        temp_overlay = base_path / f"{file_num}-temp-overlay{overlay_ext}"
                        output_filename = generate_filename(
                            date_str, str(main_ext), use_timestamp_filenames, file_num
                        )
                        output_path = base_path / output_filename

                        with open(temp_main, "wb") as f:
                            f.write(main_file)
                        with open(temp_overlay, "wb") as f:
                            f.write(overlay_file)

                        print("    Merging video overlay (this may take a while)...")
                        success = merge_video_overlay(temp_main, temp_overlay, output_path)

                        if success:
                            files_saved.append(
                                {
                                    "path": output_filename,
                                    "size": output_path.stat().st_size,
                                    "type": "merged",
                                }
                            )
                            print(f"    Merged video: {output_filename}")

                            timestamp = parse_date_to_timestamp(date_str)
                            set_file_timestamp(output_path, timestamp)

                            base_filename = generate_filename(
                                date_str, extension, use_timestamp_filenames, file_num
                            )
                            base_name_no_ext = base_filename.rsplit(".", 1)[0]

                            for potential_main in base_path.glob(
                                f"{base_name_no_ext}-main.*"
                            ):
                                potential_main.unlink()
                                print(f"    Deleted separate file: {potential_main.name}")

                            for potential_overlay in base_path.glob(
                                f"{base_name_no_ext}-overlay.*"
                            ):
                                potential_overlay.unlink()
                                print(f"    Deleted separate file: {potential_overlay.name}")

                            merge_attempted = True
                        else:
                            print(
                                "    Warning: Video merge failed, saving separate files instead..."
                            )
                            merge_overlays = False

                        temp_main.unlink(missing_ok=True)
                        temp_overlay.unlink(missing_ok=True)

                    except Exception as e:
                        print(f"    Warning: Failed to merge video overlay: {e}")
                        print("    Saving separate files instead...")
                        if "temp_main" in locals():
                            temp_main.unlink(missing_ok=True)  # type: ignore[name-defined]
                        if "temp_overlay" in locals():
                            temp_overlay.unlink(missing_ok=True)  # type: ignore[name-defined]
                        merge_overlays = False

            if not merge_attempted:
                is_deferred = is_video and has_overlay and defer_video_overlays and merge_overlays
                if is_deferred:
                    print("    Deferring video overlay merge until end")

                for file_type, file_info in extracted_files.items():
                    file_data = file_info["data"]
                    file_ext = file_info["ext"]

                    is_image_file = file_ext.lower() in [
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".gif",
                        ".bmp",
                        ".tiff",
                        ".tif",
                    ]
                    if is_image_file:
                        file_data = add_exif_metadata(
                            file_data, date_str, latitude, longitude
                        )

                    is_dup, dup_file = is_duplicate_file(
                        file_data, base_path, check_duplicates
                    )
                    if is_dup and dup_file:
                        print(f"    Skipped: Duplicate of existing file '{dup_file}'")
                        file_info_dict: dict = {
                            "path": dup_file,
                            "size": len(file_data),
                            "type": "duplicate",
                            "duplicate_of": dup_file,
                        }
                        files_saved.append(file_info_dict)
                    else:
                        base_filename = generate_filename(
                            date_str, file_ext, use_timestamp_filenames, file_num
                        )
                        base_name_no_ext = base_filename.rsplit(".", 1)[0]

                        if file_type == "overlay":
                            output_filename = f"{base_name_no_ext}-overlay{file_ext}"
                        else:
                            output_filename = f"{base_name_no_ext}-main{file_ext}"

                        output_path = base_path / output_filename
                        with open(output_path, "wb") as f:
                            f.write(file_data)

                        timestamp = parse_date_to_timestamp(date_str)
                        set_file_timestamp(output_path, timestamp)

                        file_info_dict = {
                            "path": output_filename,
                            "size": len(file_data),
                            "type": file_type,
                        }
                        if is_deferred:
                            file_info_dict["deferred"] = True
                        files_saved.append(file_info_dict)

    else:
        if overlays_only:
            return []

        kind = detect_file_kind(content)
        detected_ext = extension_for_kind(kind, extension)

        is_video = detected_ext.lower() in [".mp4", ".mov", ".avi"]
        if is_video and len(content) >= 8:
            if content[4:8] not in [b"ftyp", b"mdat", b"moov", b"wide"]:
                print("    WARNING: File may not be a valid video (invalid MP4 signature)")
                print(f"    First 20 bytes: {content[:20]}")
                print("    This might be an HTML error page or expired download link")

        is_image = detected_ext.lower() in [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".bmp",
            ".tiff",
            ".tif",
        ]
        if is_image:
            content = add_exif_metadata(content, date_str, latitude, longitude)

        is_dup, dup_file = is_duplicate_file(content, base_path, check_duplicates)
        if is_dup and dup_file:
            print(f"    Skipped: Duplicate of existing file '{dup_file}'")
            files_saved.append(
                {
                    "path": dup_file,
                    "size": len(content),
                    "type": "duplicate",
                    "duplicate_of": dup_file,
                }
            )
        else:
            output_filename = generate_filename(
                date_str, detected_ext, use_timestamp_filenames, file_num
            )
            output_path = base_path / output_filename
            with open(output_path, "wb") as f:
                f.write(content)
            files_saved.append({"path": output_filename, "size": len(content), "type": "single"})

    return files_saved
