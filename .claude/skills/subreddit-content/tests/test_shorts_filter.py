"""Tests for shorts_filter — YouTube Shorts-only gate."""
import json

from shorts_filter import is_short, filter_shorts


def test_shorts_url_is_short_regardless_of_duration():
    assert is_short("https://www.youtube.com/shorts/abc123", duration=999) is True


def test_watch_url_with_short_duration_is_short():
    assert is_short("https://www.youtube.com/watch?v=abc", duration=45) is True


def test_watch_url_with_long_duration_is_not_short():
    assert is_short("https://www.youtube.com/watch?v=abc", duration=120) is False


def test_watch_url_without_duration_is_not_short():
    # cannot confirm — drop it rather than risk posting long-form
    assert is_short("https://www.youtube.com/watch?v=abc", duration=None) is False


def test_filter_keeps_only_shorts():
    items = [
        {"url": "https://youtube.com/shorts/a", "duration": None},
        {"url": "https://youtube.com/watch?v=b", "duration": 30},
        {"url": "https://youtube.com/watch?v=c", "duration": 600},
    ]
    kept = filter_shorts(items)
    assert len(kept) == 2
    assert all("shorts" in i["url"] or (i.get("duration") or 999) <= 60 for i in kept)


def test_cli_json_file_path_filters_mixed_items(tmp_path):
    """Covers the path the shorts_filter.py __main__ CLI exercises: read a
    JSON array of mixed items from a file, filter via filter_shorts, and
    confirm only Shorts survive (long-form YouTube must not leak)."""
    items = [
        {"url": "https://youtube.com/shorts/a", "duration": None, "title": "short a"},
        {"url": "https://youtube.com/watch?v=b", "duration": 45, "title": "short-by-duration b"},
        {"url": "https://youtube.com/watch?v=c", "duration": 600, "title": "long-form c"},
        {"url": "https://youtube.com/watch?v=d", "duration": None, "title": "unknown-duration d"},
    ]
    src = tmp_path / "items.json"
    src.write_text(json.dumps(items), encoding="utf-8")

    loaded = json.loads(src.read_text(encoding="utf-8"))
    kept = filter_shorts(loaded)

    assert len(kept) == 2
    kept_titles = {i["title"] for i in kept}
    assert kept_titles == {"short a", "short-by-duration b"}
    assert all("/shorts/" in i["url"] or (i.get("duration") or 9999) <= 60 for i in kept)
