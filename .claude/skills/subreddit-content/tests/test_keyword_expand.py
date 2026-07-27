"""Tests for keyword_expand — merge/rank/dedup/split of the query set."""
from keyword_expand import normalize_term, merge_and_rank


def test_normalize_lowercases_and_collapses_ws():
    assert normalize_term("  Backyard   Chickens ") == "backyard chickens"


def test_seeds_rank_before_dataforseo():
    out = merge_and_rank(["chicken coop"], [{"keyword": "egg laying", "search_volume": 9000}])
    assert out["query_set"][0] == "chicken coop"


def test_dedup_seed_wins_over_dataforseo():
    out = merge_and_rank(["chicken coop"], [{"keyword": "Chicken Coop", "search_volume": 5000}])
    terms = out["query_set"]
    assert terms.count("chicken coop") == 1
    src = {r["term"]: r["source"] for r in out["expanded"]}
    assert src["chicken coop"] == "seed"


def test_dataforseo_ordered_by_volume_desc():
    out = merge_and_rank([], [
        {"keyword": "low", "search_volume": 100},
        {"keyword": "high", "search_volume": 9000},
    ])
    assert out["query_set"] == ["high", "low"]


def test_cap_at_max_queries():
    rows = [{"keyword": f"kw{i}", "search_volume": i} for i in range(50)]
    out = merge_and_rank(["seed"], rows, max_queries=10)
    assert len(out["query_set"]) == 10
    assert out["query_set"][0] == "seed"


def test_platform_queries_are_short():
    out = merge_and_rank(
        ["chickens", "how to build a chicken coop cheaply diy"],
        [], platform_max_words=4,
    )
    assert "chickens" in out["platform_queries"]
    assert "how to build a chicken coop cheaply diy" not in out["platform_queries"]
    assert "how to build a chicken coop cheaply diy" in out["broad_queries"]


def test_empty_dataforseo_uses_seeds_only():
    out = merge_and_rank(["a", "b"], [])
    assert out["query_set"] == ["a", "b"]


def test_missing_volume_treated_as_zero():
    out = merge_and_rank([], [{"keyword": "novol"}, {"keyword": "hasvol", "search_volume": 5}])
    assert out["query_set"] == ["hasvol", "novol"]
