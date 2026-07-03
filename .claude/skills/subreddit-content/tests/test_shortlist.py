"""Tests for shortlist — bucket-fill to mix, backfill, numbering."""
from shortlist import build_shortlist, bucket_of


def _c(pt, score, i):
    return {"post_type": pt, "score": score, "title": f"{pt}-{i}", "url": f"u{pt}{i}"}


def test_bucket_of_mapping():
    assert bucket_of("video") == "media"
    assert bucket_of("image") == "media"
    assert bucket_of("text") == "text"
    assert bucket_of("link") == "news"


def test_hits_mix_when_enough_supply():
    scored = (
        [_c("video", 90 - i, i) for i in range(10)]
        + [_c("text", 80 - i, i) for i in range(10)]
        + [_c("link", 70 - i, i) for i in range(10)]
    )
    out = build_shortlist(scored, {"media": 7, "text": 5, "news": 3}, 15)
    counts = {"media": 0, "text": 0, "news": 0}
    for p in out:
        counts[bucket_of(p["post_type"])] += 1
    assert counts == {"media": 7, "text": 5, "news": 3}
    assert len(out) == 15


def test_backfills_when_a_bucket_is_short():
    # only 2 text available though mix wants 5 -> backfill from media/news
    scored = (
        [_c("video", 90 - i, i) for i in range(20)]
        + [_c("text", 50 - i, i) for i in range(2)]
        + [_c("link", 40 - i, i) for i in range(10)]
    )
    out = build_shortlist(scored, {"media": 7, "text": 5, "news": 3}, 15)
    assert len(out) == 15


def test_post_numbers_are_sequential_from_one():
    scored = [_c("video", 90 - i, i) for i in range(15)]
    out = build_shortlist(scored, {"media": 15, "text": 0, "news": 0}, 15)
    assert [p["post_number"] for p in out] == list(range(1, 16))


def test_never_exceeds_available_supply():
    scored = [_c("video", 90, 0), _c("text", 80, 0)]
    out = build_shortlist(scored, {"media": 7, "text": 5, "news": 3}, 15)
    assert len(out) == 2
