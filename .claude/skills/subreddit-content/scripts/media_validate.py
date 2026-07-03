"""Validate a downloaded media file against Reddit's native-upload limits."""
from __future__ import annotations

from pathlib import Path

VIDEO_MAX_BYTES = 1073741824   # 1 GB
VIDEO_MAX_SECONDS = 900        # 15 min
IMAGE_MAX_BYTES = 20971520     # 20 MB

_VIDEO_TYPES = {"video"}
_IMAGE_TYPES = {"image"}


def validate_media(path, post_type: str, *, duration: float | None = None) -> dict:
    """Return {"status","reason"}; status is "ok" or "media_failed"."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {"status": "media_failed", "reason": f"file not found: {p}"}
    size = p.stat().st_size
    if size <= 0:
        return {"status": "media_failed", "reason": "zero-byte file"}

    if post_type in _VIDEO_TYPES:
        if size > VIDEO_MAX_BYTES:
            return {"status": "media_failed", "reason": f"video {size}B > {VIDEO_MAX_BYTES}B limit"}
        if duration is not None and duration > VIDEO_MAX_SECONDS:
            return {"status": "media_failed", "reason": f"video {duration}s > {VIDEO_MAX_SECONDS}s limit"}
        return {"status": "ok", "reason": ""}

    if post_type in _IMAGE_TYPES:
        if size > IMAGE_MAX_BYTES:
            return {"status": "media_failed", "reason": f"image {size}B > {IMAGE_MAX_BYTES}B limit"}
        return {"status": "ok", "reason": ""}

    return {"status": "media_failed", "reason": f"unexpected post_type for media: {post_type!r}"}
