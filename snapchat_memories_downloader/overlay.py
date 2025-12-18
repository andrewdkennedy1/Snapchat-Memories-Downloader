from __future__ import annotations

import io
import subprocess
from pathlib import Path

from .deps import Image, ffmpeg_available


def merge_image_overlay(main_data: bytes, overlay_data: bytes) -> bytes:
    if Image is None:
        raise ImportError("Pillow is required for overlay merging")

    main_img = Image.open(io.BytesIO(main_data))
    overlay_img = Image.open(io.BytesIO(overlay_data))

    original_format = main_img.format or "JPEG"

    if overlay_img.mode != "RGBA":
        overlay_img = overlay_img.convert("RGBA")

    if main_img.mode not in ["RGB", "RGBA"]:
        main_img = main_img.convert("RGB")

    if overlay_img.size != main_img.size:
        overlay_img = overlay_img.resize(main_img.size, Image.Resampling.LANCZOS)

    main_img.paste(overlay_img, (0, 0), overlay_img)

    output = io.BytesIO()

    if original_format in ["JPEG", "JPG"]:
        if main_img.mode == "RGBA":
            main_img = main_img.convert("RGB")
        main_img.save(output, format="JPEG", quality=95)
    elif original_format == "PNG":
        main_img.save(output, format="PNG")
    elif original_format == "WEBP":
        main_img.save(output, format="WEBP", quality=95)
    elif original_format in ["GIF", "BMP", "TIFF"]:
        if main_img.mode == "RGBA":
            main_img = main_img.convert("RGB")
        main_img.save(output, format=original_format)
    else:
        if main_img.mode == "RGBA":
            main_img = main_img.convert("RGB")
        main_img.save(output, format="JPEG", quality=95)

    return output.getvalue()


def merge_video_overlay(main_path: Path, overlay_path: Path, output_path: Path) -> bool:
    if not ffmpeg_available:
        raise RuntimeError("FFmpeg is not available")

    try:
        cmd = [
            "ffmpeg",
            "-i",
            str(main_path),
            "-i",
            str(overlay_path),
            "-filter_complex",
            (
                "[0:v]fps=30,setsar=1[base];"
                "[1:v]fps=30,setsar=1,"
                "loop=loop=-1:size=32767:start=0,setpts=N/FRAME_RATE/TB[ovr_tmp];"
                "[ovr_tmp][base]scale2ref[ovr][base];"
                "[base][ovr]overlay=format=auto:shortest=1[outv]"
            ),
            "-map",
            "[outv]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=False,
        )

        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
            return True

        error_msg = result.stderr.decode("utf-8", errors="ignore")
        print(f"    FFmpeg error: {error_msg[-500:]}")
        return False

    except subprocess.TimeoutExpired:
        print("    FFmpeg timeout: video processing took too long")
        return False
    except Exception as e:
        print(f"    FFmpeg exception: {e}")
        return False

