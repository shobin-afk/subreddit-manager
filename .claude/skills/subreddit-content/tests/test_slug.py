"""Tests for slug.slugify — filesystem-safe slug from niche / subreddit name."""
import pytest

from slug import slugify, SlugError


def test_simple_name_lowercases():
    assert slugify("Backyard Chickens") == "backyard-chickens"


def test_collapses_non_alphanumerics():
    assert slugify("r/AITA & Drama!!") == "r-aita-drama"


def test_strips_leading_trailing_hyphens():
    assert slugify("--Foo--") == "foo"


def test_numbers_preserved():
    assert slugify("Top 10 Fails") == "top-10-fails"


def test_empty_raises():
    with pytest.raises(SlugError):
        slugify("   ")
