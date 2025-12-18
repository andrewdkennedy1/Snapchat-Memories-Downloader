from __future__ import annotations

import os
from pathlib import Path

from .deps import Image, ffmpeg_available
from .overlay import merge_image_overlay, merge_video_overlay


def merge_existing_files(folder_path: str) -> None:
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        print(f"Error: {folder_path} is not a valid directory!")
        return

    print(f"Scanning {folder_path} for -main/-overlay pairs...")
    print("=" * 60)

    main_files = list(folder.glob("*-main.*"))
    if not main_files:
        print("No -main files found in the specified folder!")
        return

    print(f"Found {len(main_files)} -main files")

    merged_count = 0
    skipped_count = 0
    error_count = 0

    for main_file in main_files:
        filename = main_file.name
        if "-main" not in filename:
            continue

        base_name = filename.replace("-main", "")
        extension = main_file.suffix

        overlay_file = list(folder.glob(f"{base_name.replace(extension, '')}-overlay.*"))
        if not overlay_file:
            print(f"\n[SKIP] {filename}")
            print("  No matching overlay file found")
            skipped_count += 1
            continue

        overlay_file = overlay_file[0]
        output_file = folder / base_name

        print(f"\n[{merged_count + skipped_count + error_count + 1}/{len(main_files)}] Merging: {filename}")
        print(f"  Main: {main_file.name} ({main_file.stat().st_size:,} bytes)")
        print(f"  Overlay: {overlay_file.name} ({overlay_file.stat().st_size:,} bytes)")

        try:
            is_video = extension.lower() in [".mp4", ".mov", ".avi"]
            is_image = extension.lower() in [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
                ".bmp",
                ".tiff",
                ".tif",
            ]

            if is_video:
                if not ffmpeg_available:
                    print("  ERROR: FFmpeg not available for video merging")
                    error_count += 1
                    continue

                print("  Merging videos (this may take a while)...")
                success = merge_video_overlay(main_file, overlay_file, output_file)
                if success:
                    print(f"  Success: {base_name} ({output_file.stat().st_size:,} bytes)")
                    main_stat = main_file.stat()
                    os.utime(output_file, (main_stat.st_atime, main_stat.st_mtime))
                    merged_count += 1
                else:
                    print("  ERROR: Video merge failed")
                    error_count += 1

            elif is_image:
                if Image is None:
                    print("  ERROR: Pillow not available for image merging")
                    error_count += 1
                    continue

                with open(main_file, "rb") as f:
                    main_data = f.read()
                with open(overlay_file, "rb") as f:
                    overlay_data = f.read()

                merged_data = merge_image_overlay(main_data, overlay_data)
                with open(output_file, "wb") as f:
                    f.write(merged_data)

                print(f"  Success: {base_name} ({len(merged_data):,} bytes)")
                main_stat = main_file.stat()
                os.utime(output_file, (main_stat.st_atime, main_stat.st_mtime))
                merged_count += 1
            else:
                print(f"  ERROR: Unknown file type {extension}")
                error_count += 1

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            error_count += 1

    print("\n" + "=" * 60)
    print("Merge complete!")
    print(f"Summary: {merged_count} merged, {skipped_count} skipped, {error_count} errors")
    print("\nNote: Original -main and -overlay files were NOT deleted")

