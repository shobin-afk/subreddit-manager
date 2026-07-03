"""Tests for scoring — component weighting, freshness decay, bounds."""
from datetime import date

from scoring import score_candidate, score_all, WEIGHTS


TODAY = date(2026, 7, 2)


def _cand(**kw):
    base = {"engagement": 0, "date": "2026-07-02", "relevance": 0.0, "hook": 0.0}
    base.update(kw)
    return base


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_score_in_bounds():
    s = score_candidate(_cand(engagement=1_000_000, relevance=1.0, hook=1.0),
                         today=TODAY, days=30)
    assert 0.0 <= s <= 100.0


def test_all_zero_is_zero():
    s = score_candidate(_cand(engagement=0, date="2026-07-02", relevance=0.0, hook=0.0),
                        today=TODAY, days=30)
    # freshness of a same-day post is 1.0, weighted 0.20 -> 20
    assert abs(s - 20.0) < 1e-6


def test_fresher_scores_higher():
    fresh = score_candidate(_cand(date="2026-07-01"), today=TODAY, days=30)
    stale = score_candidate(_cand(date="2026-06-05"), today=TODAY, days=30)
    assert fresh > stale


def test_older_than_window_freshness_floored_at_zero():
    s = score_candidate(_cand(date="2026-01-01"), today=TODAY, days=30)
    assert abs(s - 0.0) < 1e-6


def test_score_all_sorts_desc_and_adds_key():
    cands = [_cand(relevance=0.1), _cand(relevance=0.9)]
    out = score_all(cands, today=TODAY, days=30)
    assert "score" in out[0]
    assert out[0]["score"] >= out[1]["score"]


def test_dict_shaped_engagement_does_not_crash_and_scores_as_zero():
    with_dict = score_candidate(_cand(engagement={"likes": 500, "shares": 10}),
                                 today=TODAY, days=30)
    zero_eng = score_candidate(_cand(engagement=0), today=TODAY, days=30)
    assert with_dict == zero_eng


def test_non_numeric_string_engagement_does_not_crash_and_scores_as_zero():
    with_str = score_candidate(_cand(engagement="1.2M"), today=TODAY, days=30)
    zero_eng = score_candidate(_cand(engagement=0), today=TODAY, days=30)
    assert with_str == zero_eng
