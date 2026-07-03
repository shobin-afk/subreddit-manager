"""Tests for input_parser — invocation args, flags, and mix parsing."""
import pytest

from input_parser import (
    parse_invocation,
    parse_mix,
    default_mix,
    InputError,
)


def test_default_mix_15_is_7_5_3():
    assert default_mix(15) == {"media": 7, "text": 5, "news": 3}


def test_default_mix_sums_to_count():
    for n in (5, 10, 12, 20, 21):
        m = default_mix(n)
        assert sum(m.values()) == n


def test_parse_mix_basic():
    assert parse_mix("media=10,text=3,news=2") == {"media": 10, "text": 3, "news": 2}


def test_parse_mix_rejects_unknown_key():
    with pytest.raises(InputError):
        parse_mix("video=10,text=3")


def test_parse_invocation_minimal():
    cfg = parse_invocation(["https://www.reddit.com/r/BackyardChickens/", "backyard chickens"])
    assert cfg["subreddit_name"] == "BackyardChickens"
    assert cfg["subreddit_slug"] == "backyardchickens"
    assert cfg["niche"] == "backyard chickens"
    assert cfg["count"] == 15
    assert cfg["mix"] == {"media": 7, "text": 5, "news": 3}
    assert cfg["days"] == 30
    assert cfg["auto"] is False


def test_parse_invocation_flags():
    cfg = parse_invocation([
        "reddit.com/r/foo", "some niche",
        "--count", "10", "--mix", "media=6,text=2,news=2",
        "--days", "7", "--auto",
    ])
    assert cfg["count"] == 10
    assert cfg["mix"] == {"media": 6, "text": 2, "news": 2}
    assert cfg["days"] == 7
    assert cfg["auto"] is True


def test_mix_overrides_count_when_both_given_mismatch():
    # explicit --mix wins; count is set to the mix sum
    cfg = parse_invocation(["reddit.com/r/foo", "n", "--count", "99", "--mix", "media=6,text=2,news=2"])
    assert cfg["count"] == 10


def test_bad_subreddit_url_raises():
    with pytest.raises(InputError):
        parse_invocation(["https://example.com/foo", "niche"])


def test_empty_niche_raises():
    with pytest.raises(InputError):
        parse_invocation(["reddit.com/r/foo", "   "])


def test_parse_mix_rejects_negative_bucket():
    with pytest.raises(InputError):
        parse_mix("media=-3,text=10,news=8")
