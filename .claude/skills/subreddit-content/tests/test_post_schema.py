"""Tests for post_schema.validate_post."""
from post_schema import validate_post, TITLE_MAX


def _post(**kw):
    base = {
        "post_number": 1,
        "post_type": "text",
        "title": "A fine title",
        "suggested_flair": "",
        "nsfw": False,
        "source_platform": "youtube",
        "source_url": "https://youtube.com/x",
        "attribution": "@x (YouTube)",
        "media_file": "",
        "engagement_note": "1k likes",
        "status": "ready",
        "body": "Some body text.",
    }
    base.update(kw)
    return base


def test_valid_post_has_no_errors():
    assert validate_post(_post()) == []


def test_missing_required_key_flagged():
    p = _post()
    del p["title"]
    errs = validate_post(p)
    assert any("title" in e for e in errs)


def test_title_too_long_flagged():
    errs = validate_post(_post(title="x" * (TITLE_MAX + 1)))
    assert any("title" in e.lower() for e in errs)


def test_bad_post_type_flagged():
    errs = validate_post(_post(post_type="carousel"))
    assert any("post_type" in e for e in errs)


def test_media_type_requires_media_file():
    errs = validate_post(_post(post_type="video", media_file=""))
    assert any("media_file" in e for e in errs)


def test_media_failed_status_allows_empty_media_file():
    errs = validate_post(_post(post_type="video", media_file="", status="media_failed"))
    assert errs == []


def test_flair_not_in_allowed_list_flagged():
    errs = validate_post(_post(suggested_flair="Ghost"), allowed_flairs=["Funny", "News"])
    assert any("flair" in e.lower() for e in errs)


def test_empty_flair_always_allowed():
    assert validate_post(_post(suggested_flair=""), allowed_flairs=["Funny"]) == []
