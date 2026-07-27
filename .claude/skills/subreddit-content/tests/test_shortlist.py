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


def _typed(pt, score, i):
    return {"post_type": pt, "score": score, "title": f"{pt}-{i}", "url": f"u{pt}{i}"}


def test_floor_guarantees_one_image_and_one_video_even_if_low_score():
    scored = (
        [_typed("text", 100 - i, i) for i in range(20)]   # texts dominate by score
        + [_typed("video", 5, 0), _typed("image", 4, 0)]  # low-score media
    )
    out = build_shortlist(scored, {"media": 10, "text": 5, "news": 0}, 15,
                          floor={"min_images": 1, "min_videos": 1})
    types = [p["post_type"] for p in out]
    assert "video" in types and "image" in types


def test_floor_none_preserves_existing_behavior():
    scored = [_c("video", 90 - i, i) for i in range(15)]
    out = build_shortlist(scored, {"media": 15, "text": 0, "news": 0}, 15)
    assert [p["post_number"] for p in out] == list(range(1, 16))


def test_floor_video_short_does_not_crash_and_selects_available():
    scored = [_typed("image", 50 - i, i) for i in range(12)]  # zero videos
    out = build_shortlist(scored, {"media": 10, "text": 5, "news": 0}, 15,
                          floor={"min_images": 1, "min_videos": 1})
    assert any(p["post_type"] == "image" for p in out)
    assert all(p["post_type"] != "video" for p in out)  # none existed


def test_floor_counts_toward_media_quota_not_beyond():
    scored = (
        [_typed("video", 10 + i, i) for i in range(8)]
        + [_typed("image", 30 + i, i) for i in range(8)]
        + [_typed("text", 5 + i, i) for i in range(8)]
    )
    out = build_shortlist(scored, {"media": 10, "text": 5, "news": 0}, 15,
                          floor={"min_images": 1, "min_videos": 1})
    media = sum(1 for p in out if p["post_type"] in ("video", "image"))
    assert media == 10
    assert len(out) == 15


def test_floor_survives_when_mix_sum_exceeds_count():
    scored = ([_typed("video", 1, 0), _typed("image", 1, 0)]
              + [_typed("text", 100 - i, i) for i in range(12)])
    out = build_shortlist(scored, {"media": 10, "text": 10, "news": 0}, 5,
                          floor={"min_images": 1, "min_videos": 1})
    types = [p["post_type"] for p in out]
    assert len(out) == 5
    assert "video" in types and "image" in types
