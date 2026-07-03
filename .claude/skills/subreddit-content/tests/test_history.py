"""Tests for history — URL normalization, load, filter, append."""
import json

from history import normalize_url, load_used, filter_unused, append_used


def test_normalize_strips_scheme_www_query_fragment():
    a = normalize_url("https://www.tiktok.com/@x/video/1?foo=bar#frag")
    b = normalize_url("http://tiktok.com/@x/video/1")
    assert a == b


def test_normalize_strips_trailing_slash():
    assert normalize_url("https://youtube.com/shorts/ab/") == normalize_url("https://youtube.com/shorts/ab")


def test_load_missing_file_is_empty(tmp_path):
    assert load_used(tmp_path / "nope.jsonl") == set()


def test_append_then_load_round_trip(tmp_path):
    p = tmp_path / "r-foo.jsonl"
    append_used(p, [{"url": "https://tiktok.com/@x/video/1", "title": "T"}],
                run_folder="foo-2026-07-02", date_used="2026-07-02")
    used = load_used(p)
    assert normalize_url("https://www.tiktok.com/@x/video/1?utm=1") in used


def test_filter_unused_drops_seen(tmp_path):
    p = tmp_path / "r-foo.jsonl"
    append_used(p, [{"url": "https://youtube.com/shorts/aaa", "title": "A"}],
                run_folder="f", date_used="2026-07-02")
    used = load_used(p)
    cands = [
        {"url": "https://www.youtube.com/shorts/aaa?si=1", "title": "dup"},
        {"url": "https://www.youtube.com/shorts/bbb", "title": "fresh"},
    ]
    kept = filter_unused(cands, used)
    assert len(kept) == 1
    assert kept[0]["title"] == "fresh"


def test_append_writes_all_required_keys(tmp_path):
    p = tmp_path / "r-foo.jsonl"
    append_used(p, [{"url": "https://x.com/1", "title": "T"}],
                run_folder="rf", date_used="2026-07-02")
    rec = json.loads(p.read_text().strip())
    assert set(rec) == {"url", "title", "date_used", "run_folder"}


def test_append_used_accepts_delivered_post_shape_with_source_url(tmp_path):
    """Delivered posts key their source URL as source_url, not url (see
    post_schema.REQUIRED_KEYS). append_used must resolve it so dedup doesn't
    silently no-op on the append seam."""
    p = tmp_path / "r-foo.jsonl"
    delivered_post = {
        "post_number": 1,
        "title": "T",
        "source_url": "https://tiktok.com/@x/video/42",
    }
    append_used(p, [delivered_post], run_folder="rf", date_used="2026-07-02")

    rec = json.loads(p.read_text().strip())
    assert rec["url"] == "https://tiktok.com/@x/video/42"

    used = load_used(p)
    candidate = {"url": "https://www.tiktok.com/@x/video/42?utm=1"}
    assert filter_unused([candidate], used) == []
