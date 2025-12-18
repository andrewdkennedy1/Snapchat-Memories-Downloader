from __future__ import annotations

import io
import subprocess
from pathlib import Path

from .deps import Image, ffmpeg_available
from .subprocess_utils import run_capture


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


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


def build_ffmpeg_overlay_command(
    main_path: Path,
    overlay_path: Path,
    output_path: Path,
    *,
    copy_audio: bool,
) -> list[str]:
    overlay_is_image = overlay_path.suffix.lower() in _IMAGE_EXTS

    cmd = ["ffmpeg", "-hide_banner"]
    cmd += ["-y", "-i", str(main_path)]
    if overlay_is_image:
        cmd += ["-loop", "1", "-i", str(overlay_path)]
    else:
        cmd += ["-i", str(overlay_path)]

    filter_complex = (
        "[0:v]setsar=1[base];"
        "[1:v]setsar=1[ovr];"
        "[ovr][base]scale2ref[ovr_s][base_s];"
        "[base_s][ovr_s]overlay=eof_action=pass:format=auto[outv]"
    )

    cmd += [
        "-filter_complex",
        filter_complex,
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
        "-movflags",
        "+faststart",
    ]

    if copy_audio:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k"]

    cmd += [str(output_path)]
    return cmd


def _summarize_ffmpeg_stderr(stderr_text: str) -> str:
    lines = [ln.rstrip() for ln in stderr_text.splitlines() if ln.strip()]
    if not lines:
        return ""

    interesting = []
    needles = ("error", "failed", "invalid", "conversion failed", "could not", "unknown", "not found")
    for ln in lines:
        lower = ln.lower()
        if any(n in lower for n in needles):
            interesting.append(ln)

    tail = lines[-60:]
    out = []
    if interesting:
        out.append("---- ffmpeg highlights ----")
        out.extend(interesting[-20:])
    out.append("---- ffmpeg tail ----")
    out.extend(tail)
    text = "\n".join(out)
    return text[-8000:]


def merge_video_overlay(main_path: Path, overlay_path: Path, output_path: Path) -> bool:
    if not ffmpeg_available:
        raise RuntimeError("FFmpeg is not available")

    try:
        for copy_audio in (True, False):
            cmd = build_ffmpeg_overlay_command(
                main_path,
                overlay_path,
                output_path,
                copy_audio=copy_audio,
            )
            result = run_capture(cmd, timeout=600)

            if (
                result.returncode == 0
                and output_path.exists()
                and output_path.stat().st_size > 1000
            ):
                return True

            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass

            stderr_text = result.stderr.decode("utf-8", errors="ignore")
            audio_mode = "copy" if copy_audio else "aac"
            print(
                f"    FFmpeg failed (exit {result.returncode}, audio={audio_mode})"
            )
            summary = _summarize_ffmpeg_stderr(stderr_text)
            if summary:
                print(summary)

        return False

    except subprocess.TimeoutExpired:
        print("    FFmpeg timeout: video processing took too long")
        return False
    except Exception as e:
        print(f"    FFmpeg exception: {e}")
        return False
