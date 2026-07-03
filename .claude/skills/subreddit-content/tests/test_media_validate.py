"""Tests for media_validate — presence, size, duration limits."""
from media_validate import (
    validate_media,
    VIDEO_MAX_BYTES,
    IMAGE_MAX_BYTES,
    VIDEO_MAX_SECONDS,
)


def _make(tmp_path, name, nbytes):
    p = tmp_path / name
    p.write_bytes(b"\0" * nbytes)
    return p


def test_missing_file_fails(tmp_path):
    r = validate_media(tmp_path / "nope.mp4", "video")
    assert r["status"] == "media_failed"


def test_zero_byte_fails(tmp_path):
    p = _make(tmp_path, "z.jpg", 0)
    assert validate_media(p, "image")["status"] == "media_failed"


def test_small_image_ok(tmp_path):
    p = _make(tmp_path, "ok.jpg", 1024)
    assert validate_media(p, "image")["status"] == "ok"


def test_oversize_image_fails(tmp_path):
    p = _make(tmp_path, "big.jpg", IMAGE_MAX_BYTES + 1)
    assert validate_media(p, "image")["status"] == "media_failed"


def test_video_duration_over_limit_fails(tmp_path):
    p = _make(tmp_path, "v.mp4", 2048)
    r = validate_media(p, "video", duration=VIDEO_MAX_SECONDS + 1)
    assert r["status"] == "media_failed"


def test_video_within_limits_ok(tmp_path):
    p = _make(tmp_path, "v.mp4", 2048)
    r = validate_media(p, "video", duration=120)
    assert r["status"] == "ok"
