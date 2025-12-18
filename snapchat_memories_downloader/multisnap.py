from __future__ import annotations

import os
from pathlib import Path

from .deps import ffmpeg_available, ffmpeg_path
from .subprocess_utils import run_capture


def join_multi_snaps(folder_path: Path, time_threshold_seconds: int = 10) -> dict:
    if not ffmpeg_available:
        print("\nWarning: FFmpeg not available, cannot join multi-snaps")
        return {"groups_found": 0, "videos_joined": 0, "files_deleted": 0}

    print("\n" + "=" * 60)
    print("Detecting multi-snap videos...")
    print("=" * 60)

    video_extensions = [".mp4", ".mov", ".avi"]
    all_videos = [f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in video_extensions]

    if len(all_videos) < 2:
        print("Not enough videos to check for multi-snaps")
        return {"groups_found": 0, "videos_joined": 0, "files_deleted": 0}

    video_info = [{"path": video_path, "mtime": video_path.stat().st_mtime} for video_path in all_videos]
    video_info.sort(key=lambda x: x["mtime"])

    groups: list[list[dict]] = []
    current_group = [video_info[0]]
    for i in range(1, len(video_info)):
        time_diff = abs(video_info[i]["mtime"] - current_group[-1]["mtime"])
        if time_diff <= time_threshold_seconds:
            current_group.append(video_info[i])
        else:
            if len(current_group) > 1:
                groups.append(current_group)
            current_group = [video_info[i]]
    if len(current_group) > 1:
        groups.append(current_group)

    if not groups:
        print("No multi-snap video groups found")
        return {"groups_found": 0, "videos_joined": 0, "files_deleted": 0}

    print(f"\nFound {len(groups)} multi-snap group(s):")

    total_videos_joined = 0
    files_deleted = 0

    for group_idx, group in enumerate(groups, start=1):
        print(f"\n  Group {group_idx} ({len(group)} videos):")
        for video in group:
            print(f"    - {video['path'].name}")

        first_video = group[0]["path"]
        output_name = first_video.stem + "-joined" + first_video.suffix
        output_path = folder_path / output_name

        concat_list_path = folder_path / f"concat_list_{group_idx}.txt"
        try:
            with open(concat_list_path, "w", encoding="utf-8") as f:
                for video in group:
                    escaped_path = str(video["path"].absolute()).replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            cmd = [
                ffmpeg_path or "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-c",
                "copy",
                "-y",
                str(output_path),
            ]

            result = run_capture(cmd, timeout=300)

            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
                print(f"    Joined: {output_name} ({output_path.stat().st_size:,} bytes)")
                first_stat = first_video.stat()
                os.utime(output_path, (first_stat.st_atime, first_stat.st_mtime))

                for video in group:
                    video["path"].unlink()
                    files_deleted += 1

                total_videos_joined += len(group)
            else:
                error_msg = result.stderr.decode("utf-8", errors="ignore")
                print("    ERROR: Failed to join videos")
                print(f"    FFmpeg error: {error_msg[-200:]}")

        except Exception as e:
            print(f"    ERROR: {str(e)}")
        finally:
            if concat_list_path.exists():
                concat_list_path.unlink()

    print("\n" + "=" * 60)
    print("Multi-snap joining complete!")
    print(f"  Groups found: {len(groups)}")
    print(f"  Videos joined: {total_videos_joined}")
    print(f"  Files deleted: {files_deleted}")
    print("=" * 60)

    return {"groups_found": len(groups), "videos_joined": total_videos_joined, "files_deleted": files_deleted}
