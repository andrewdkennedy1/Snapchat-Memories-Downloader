from __future__ import annotations

from typing import Literal


FileKind = Literal[
    "zip",
    "jpeg",
    "png",
    "gif",
    "webp",
    "mp4",
    "mov",
    "heic",
    "unknown",
]


def detect_file_kind(data: bytes) -> FileKind:
    if len(data) >= 2 and data[:2] == b"PK":
        return "zip"

    if len(data) >= 3 and data[:3] == b"\xFF\xD8\xFF":
        return "jpeg"

    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"

    if len(data) >= 6 and (data[:6] == b"GIF87a" or data[:6] == b"GIF89a"):
        return "gif"

    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"

    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in {
            b"heic",
            b"heix",
            b"heim",
            b"hevc",
            b"hevx",
            b"mif1",
            b"msf1",
        }:
            return "heic"
        if brand == b"qt  ":
            return "mov"
        return "mp4"

    return "unknown"


def extension_for_kind(kind: FileKind, fallback: str) -> str:
    if kind == "zip":
        return ".zip"
    if kind == "jpeg":
        return ".jpg"
    if kind == "png":
        return ".png"
    if kind == "gif":
        return ".gif"
    if kind == "webp":
        return ".webp"
    if kind == "mp4":
        return ".mp4"
    if kind == "mov":
        return ".mov"
    if kind == "heic":
        return ".heic"
    return fallback

