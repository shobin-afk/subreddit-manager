# Subreddit-Content v2 (Keyword Expansion + Parallel Discovery) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing `/subreddit-content` skill so thin niches still yield ≥15 posts: add a keyword seeding/expansion step (Claude seeds + DataForSEO), replace discovery with parallel per-platform Apify sub-agents (TikTok, Instagram, Pinterest, YouTube Shorts-only), and guarantee a media floor of ≥1 image AND ≥1 video via a pooled + gap-fill escalation ladder.

**Architecture:** New deterministic stdlib helpers (`keyword_expand`, `shorts_filter`, `discovery_gaps`, plus a media-floor option on `shortlist`) carry the testable logic. Two new sub-agents under `.claude/agents/` (`subreddit-content-keywords`, `subreddit-content-discovery`) carry the MCP/scraping work and return only normalized data. `SKILL.md` orchestrates: intake ∥ keyword expansion, then a parallel discovery fan-out with a bounded gap-fill loop, then the existing score→shortlist→media→assemble tail.

**Tech Stack:** Python 3.10+ stdlib only (runtime); `pytest` (dev). Existing helpers `slug`, `run_log`, `input_parser`, `history`, `scoring`, `shortlist`, `media_validate`, `post_schema`, `assemble`. DataForSEO MCP (`mcp__dataforseo__*`), Apify MCP (`mcp__apify__*`), WebFetch. Sub-agent pattern mirrors `.claude/skills/reddit-research/` + `.claude/agents/reddit-research-*.md`.

## Global Constraints

- Work inside the existing skill package `.claude/skills/subreddit-content/`. Agents go under repo `.claude/agents/` (same place as `reddit-research-*.md`).
- Python `>=3.10`, **stdlib only at runtime** (no third-party runtime deps); `pytest>=7.0` dev-only.
- Tests import helpers by bare module name via `tests/conftest.py` (already inserts `scripts/` on `sys.path`). Run from `.claude/skills/subreddit-content`.
- **Never auto-post to Reddit. Discovery never sources from Reddit.** Deliverable-only.
- **New default mix: `media=10, text=5`.** The `news` bucket stays in code but defaults to `0` (`_MIX_RATIO = {"media": 10, "text": 5, "news": 0}`). Backward compatible: `--mix` may still set `news`.
- **Media floor (hard): ≥1 image AND ≥1 video.** Constants `MIN_IMAGES=1`, `MIN_VIDEOS=1`; overridable via `--media-floor img,vid`.
- **YouTube: Shorts only** — keep an item only if its URL contains `/shorts/` OR its duration ≤ 60s. Long-form dropped at the agent boundary.
- Guarantee **≥15 posts** per run; if discovery falls short after the escalation ladder, backfill with text posts. Ladder bounded by `--max-rounds` (default 3). Keyword set capped by `--max-queries` (default 40).
- DataForSEO is **enrichment only** — on error/empty, proceed with Claude seeds; never fatal.
- `post_type ∈ {video, image, text, link}`; mix bucket ∈ `{media, text, news}` (`bucket_of`: video/image→media, text→text, link→news).
- Reddit limits unchanged: video ≤ `1073741824` B / ≤ `900` s; image ≤ `20971520` B. Title ≤ `300`.
- Candidate shape used across discovery/scoring: `{title, post_type, source_platform, url, engagement, date, thumbnail, media_url}` (a discovery candidate's URL field is `url`; the delivered post dict uses `source_url` — keep `history.append_used` accepting both).
- Commit after every task: `feat|fix|docs(subreddit-content): …`.

---

### Task 1: Config — new default mix, flags, and floor constants (`input_parser.py`)

**Files:**
- Modify: `.claude/skills/subreddit-content/scripts/input_parser.py`
- Test: `.claude/skills/subreddit-content/tests/test_input_parser.py`

**Interfaces:**
- Consumes: `slugify` from `slug` (already imported).
- Produces (config dict gains keys): `seeds: list[str]`, `max_queries: int`, `max_rounds: int`, `media_floor: {"min_images": int, "min_videos": int}`. New module constants `DEFAULT_MAX_QUERIES=40`, `DEFAULT_MAX_ROUNDS=3`, `MIN_IMAGES=1`, `MIN_VIDEOS=1`. `_MIX_RATIO` becomes `{"media": 10, "text": 5, "news": 0}`. New flags `--seeds`, `--max-queries`, `--max-rounds`, `--media-floor`.

- [ ] **Step 1: Update the existing failing tests + add new ones**

In `tests/test_input_parser.py`, change the two assertions that hardcode the old 7:5:3 default, and append new-flag tests:

```python
# CHANGE these two existing assertions:
def test_default_mix_15_is_10_5_0():
    from input_parser import default_mix
    assert default_mix(15) == {"media": 10, "text": 5, "news": 0}

# (delete/replace the old test_default_mix_15_is_7_5_3)

# In test_parse_invocation_minimal, the mix assertion becomes:
#     assert cfg["mix"] == {"media": 10, "text": 5, "news": 0}
# and add:
#     assert cfg["seeds"] == []
#     assert cfg["max_queries"] == 40
#     assert cfg["max_rounds"] == 3
#     assert cfg["media_floor"] == {"min_images": 1, "min_videos": 1}
```

Append these new tests:

```python
def test_seeds_flag_splits_on_comma():
    cfg = parse_invocation(["reddit.com/r/foo", "niche", "--seeds", "a, b ,c"])
    assert cfg["seeds"] == ["a", "b", "c"]


def test_max_queries_and_rounds_flags():
    cfg = parse_invocation(["reddit.com/r/foo", "n", "--max-queries", "20", "--max-rounds", "5"])
    assert cfg["max_queries"] == 20
    assert cfg["max_rounds"] == 5


def test_media_floor_flag_parses_two_ints():
    cfg = parse_invocation(["reddit.com/r/foo", "n", "--media-floor", "2,3"])
    assert cfg["media_floor"] == {"min_images": 2, "min_videos": 3}


def test_media_floor_bad_format_raises():
    with pytest.raises(InputError):
        parse_invocation(["reddit.com/r/foo", "n", "--media-floor", "2"])


def test_max_queries_out_of_range_raises():
    with pytest.raises(InputError):
        parse_invocation(["reddit.com/r/foo", "n", "--max-queries", "0"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_input_parser.py -v`
Expected: FAIL — new default-mix assertion mismatches; new flag keys absent (`KeyError`).

- [ ] **Step 3: Implement the config changes**

In `scripts/input_parser.py`:

Replace the ratio constant and add new constants near the top:
```python
_MIX_RATIO = {"media": 10, "text": 5, "news": 0}  # sums to 15
DEFAULT_MAX_QUERIES = 40
DEFAULT_MAX_ROUNDS = 3
MIN_IMAGES = 1
MIN_VIDEOS = 1
MAX_QUERIES_MIN, MAX_QUERIES_MAX = 1, 200
MAX_ROUNDS_MIN, MAX_ROUNDS_MAX = 1, 10
```

In `parse_invocation`, initialise the new locals alongside the existing ones:
```python
    seeds: list[str] = []
    max_queries = DEFAULT_MAX_QUERIES
    max_rounds = DEFAULT_MAX_ROUNDS
    media_floor = {"min_images": MIN_IMAGES, "min_videos": MIN_VIDEOS}
```

Add flag handling in the `while` loop (before the `elif tok.startswith("--")` catch-all):
```python
        elif tok == "--seeds":
            raw = _str_flag(argv, i, "--seeds")
            seeds = [s.strip() for s in raw.split(",") if s.strip()]
            i += 2
        elif tok == "--max-queries":
            max_queries = _int_flag(argv, i, "--max-queries")
            i += 2
        elif tok == "--max-rounds":
            max_rounds = _int_flag(argv, i, "--max-rounds")
            i += 2
        elif tok == "--media-floor":
            media_floor = _parse_media_floor(_str_flag(argv, i, "--media-floor"))
            i += 2
```

Add range validation after the existing `days` range check:
```python
    if not (MAX_QUERIES_MIN <= max_queries <= MAX_QUERIES_MAX):
        raise InputError(f"max_queries {max_queries} out of range [{MAX_QUERIES_MIN},{MAX_QUERIES_MAX}]")
    if not (MAX_ROUNDS_MIN <= max_rounds <= MAX_ROUNDS_MAX):
        raise InputError(f"max_rounds {max_rounds} out of range [{MAX_ROUNDS_MIN},{MAX_ROUNDS_MAX}]")
```

Add the new keys to the returned dict:
```python
        "seeds": seeds,
        "max_queries": max_queries,
        "max_rounds": max_rounds,
        "media_floor": media_floor,
```

Add the floor parser helper near `_str_flag`:
```python
def _parse_media_floor(spec: str) -> dict[str, int]:
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 2:
        raise InputError(f"--media-floor expects 'images,videos', got {spec!r}")
    try:
        imgs, vids = int(parts[0]), int(parts[1])
    except ValueError:
        raise InputError(f"--media-floor values must be ints, got {spec!r}")
    if imgs < 0 or vids < 0:
        raise InputError(f"--media-floor values must be >= 0, got {spec!r}")
    return {"min_images": imgs, "min_videos": vids}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_input_parser.py -v`
Expected: PASS (all input_parser tests).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/input_parser.py .claude/skills/subreddit-content/tests/test_input_parser.py
git commit -m "feat(subreddit-content): v2 config — 10/5 mix, seeds/max-queries/max-rounds/media-floor flags"
```

---

### Task 2: `keyword_expand.py` — merge Claude seeds + DataForSEO into a ranked query set

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/keyword_expand.py`
- Test: `.claude/skills/subreddit-content/tests/test_keyword_expand.py`

**Interfaces:**
- Produces:
  - `normalize_term(term: str) -> str` — lowercase, strip, collapse internal whitespace.
  - `merge_and_rank(seeds: list[str], dataforseo_rows: list[dict], *, max_queries: int = 40, platform_max_words: int = 4) -> dict` — returns `{"expanded": [{"term","volume","source"}], "query_set": [term,...], "platform_queries": [term,...], "broad_queries": [term,...]}`. `dataforseo_rows` items look like `{"keyword": str, "search_volume": int|None}`. Seeds get `source="seed"` and rank ahead of `source="dataforseo"`; within DataForSEO, higher `volume` first, then shorter term. Deduped by normalized term (seed wins). Capped at `max_queries`. `platform_queries` = query_set terms with ≤ `platform_max_words` words; `broad_queries` = full query_set.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_keyword_expand.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_keyword_expand.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keyword_expand'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/keyword_expand.py`:
```python
"""Merge Claude seed terms + DataForSEO rows into one ranked query set."""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def normalize_term(term: str) -> str:
    """Lowercase, strip, collapse internal whitespace."""
    return _WS.sub(" ", str(term).strip().lower())


def merge_and_rank(
    seeds: list[str],
    dataforseo_rows: list[dict],
    *,
    max_queries: int = 40,
    platform_max_words: int = 4,
) -> dict:
    """Return {expanded, query_set, platform_queries, broad_queries}.

    Seeds rank first (source='seed'); DataForSEO rows follow, higher volume
    first then shorter term. Deduped by normalized term (seed wins). Capped
    at max_queries."""
    rows: list[dict] = []
    seen: set[str] = set()

    for s in seeds:
        t = normalize_term(s)
        if t and t not in seen:
            seen.add(t)
            rows.append({"term": t, "volume": 0, "source": "seed"})

    dfs: list[dict] = []
    for r in dataforseo_rows:
        t = normalize_term(r.get("keyword", ""))
        if not t or t in seen:
            continue
        seen.add(t)
        vol = r.get("search_volume") or 0
        dfs.append({"term": t, "volume": int(vol), "source": "dataforseo"})

    # DataForSEO ordering: volume desc, then shorter term
    dfs.sort(key=lambda r: (-r["volume"], len(r["term"])))

    expanded = (rows + dfs)[:max_queries]
    query_set = [r["term"] for r in expanded]
    platform_queries = [t for t in query_set if len(t.split()) <= platform_max_words]
    return {
        "expanded": expanded,
        "query_set": query_set,
        "platform_queries": platform_queries,
        "broad_queries": list(query_set),
    }


if __name__ == "__main__":
    import json
    import sys
    seeds = sys.argv[1].split(",") if len(sys.argv) > 1 else []
    print(json.dumps(merge_and_rank([s for s in seeds], []), indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_keyword_expand.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/keyword_expand.py .claude/skills/subreddit-content/tests/test_keyword_expand.py
git commit -m "feat(subreddit-content): add keyword_expand helper"
```

---

### Task 3: `shorts_filter.py` — YouTube Shorts-only enforcement

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/shorts_filter.py`
- Test: `.claude/skills/subreddit-content/tests/test_shorts_filter.py`

**Interfaces:**
- Produces:
  - `SHORT_MAX_SECONDS = 60`.
  - `is_short(url: str, duration: float | None = None, *, max_seconds: int = SHORT_MAX_SECONDS) -> bool` — True if `/shorts/` in url (case-insensitive), else True if `duration is not None and duration <= max_seconds`, else False (unconfirmed long-form dropped).
  - `filter_shorts(items: list[dict]) -> list[dict]` — keep items where `is_short(item.get("url",""), item.get("duration"))`.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_shorts_filter.py`:
```python
"""Tests for shorts_filter — YouTube Shorts-only gate."""
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_shorts_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shorts_filter'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/shorts_filter.py`:
```python
"""Keep only YouTube Shorts (URL /shorts/ or duration <= 60s)."""
from __future__ import annotations

SHORT_MAX_SECONDS = 60


def is_short(url: str, duration: float | None = None, *, max_seconds: int = SHORT_MAX_SECONDS) -> bool:
    """True for a Short: /shorts/ URL, or a known duration within the cap.
    Unknown duration on a non-/shorts/ URL is treated as NOT a Short."""
    if "/shorts/" in (url or "").lower():
        return True
    if duration is not None:
        try:
            return float(duration) <= max_seconds
        except (TypeError, ValueError):
            return False
    return False


def filter_shorts(items: list[dict]) -> list[dict]:
    """Keep only items whose url/duration qualify as a Short."""
    return [i for i in items if is_short(i.get("url", ""), i.get("duration"))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_shorts_filter.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/shorts_filter.py .claude/skills/subreddit-content/tests/test_shorts_filter.py
git commit -m "feat(subreddit-content): add YouTube Shorts filter"
```

---

### Task 4: `discovery_gaps.py` — analyze the pool against count + media floor

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/discovery_gaps.py`
- Test: `.claude/skills/subreddit-content/tests/test_discovery_gaps.py`

**Interfaces:**
- Produces:
  - `PLATFORMS_FOR_VIDEO = ["youtube", "tiktok", "instagram"]`, `PLATFORMS_FOR_IMAGE = ["pinterest", "instagram"]`, `ALL_PLATFORMS = ["tiktok", "instagram", "pinterest", "youtube"]`.
  - `analyze_pool(pool: list[dict], *, count: int, min_images: int, min_videos: int, media_total: int) -> dict` — returns `{"need_count","need_images","need_videos","need_media","platforms","satisfied"}`. Counts `pool` by `post_type`. `platforms` is the deduped, ordered list of platforms to re-query this round (video gap → video platforms; image gap → image platforms; generic media/count gap → all platforms). `satisfied` is True when every `need_*` is 0.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_discovery_gaps.py`:
```python
"""Tests for discovery_gaps — floor/count gap analysis + platform targeting."""
from discovery_gaps import analyze_pool, PLATFORMS_FOR_VIDEO, PLATFORMS_FOR_IMAGE


def _pool(videos=0, images=0, texts=0):
    out = []
    out += [{"post_type": "video", "url": f"v{i}"} for i in range(videos)]
    out += [{"post_type": "image", "url": f"i{i}"} for i in range(images)]
    out += [{"post_type": "text", "url": f"t{i}"} for i in range(texts)]
    return out


def test_satisfied_when_floor_and_count_met():
    g = analyze_pool(_pool(videos=6, images=6, texts=5), count=15,
                     min_images=1, min_videos=1, media_total=10)
    assert g["satisfied"] is True
    assert g["platforms"] == []


def test_missing_video_targets_video_platforms():
    g = analyze_pool(_pool(videos=0, images=10, texts=5), count=15,
                     min_images=1, min_videos=1, media_total=10)
    assert g["need_videos"] == 1
    assert set(PLATFORMS_FOR_VIDEO).issubset(set(g["platforms"]))
    assert g["satisfied"] is False


def test_missing_image_targets_image_platforms():
    g = analyze_pool(_pool(videos=10, images=0, texts=5), count=15,
                     min_images=1, min_videos=1, media_total=10)
    assert g["need_images"] == 1
    assert set(PLATFORMS_FOR_IMAGE).issubset(set(g["platforms"]))


def test_media_total_shortfall_flags_need_media():
    g = analyze_pool(_pool(videos=2, images=2, texts=5), count=15,
                     min_images=1, min_videos=1, media_total=10)
    assert g["need_media"] == 6
    assert g["platforms"]  # non-empty


def test_count_shortfall_flags_need_count():
    g = analyze_pool(_pool(videos=3, images=3, texts=0), count=15,
                     min_images=1, min_videos=1, media_total=6)
    assert g["need_count"] == 9
    assert g["satisfied"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_discovery_gaps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery_gaps'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/discovery_gaps.py`:
```python
"""Analyze the discovery pool against the target count + media floor."""
from __future__ import annotations

PLATFORMS_FOR_VIDEO = ["youtube", "tiktok", "instagram"]
PLATFORMS_FOR_IMAGE = ["pinterest", "instagram"]
ALL_PLATFORMS = ["tiktok", "instagram", "pinterest", "youtube"]


def analyze_pool(
    pool: list[dict],
    *,
    count: int,
    min_images: int,
    min_videos: int,
    media_total: int,
) -> dict:
    """Return gap info + which platforms to re-query this round."""
    videos = sum(1 for c in pool if c.get("post_type") == "video")
    images = sum(1 for c in pool if c.get("post_type") == "image")
    media = videos + images

    need_videos = max(0, min_videos - videos)
    need_images = max(0, min_images - images)
    need_media = max(0, media_total - media)
    need_count = max(0, count - len(pool))

    platforms: list[str] = []

    def add(ps):
        for p in ps:
            if p not in platforms:
                platforms.append(p)

    if need_videos:
        add(PLATFORMS_FOR_VIDEO)
    if need_images:
        add(PLATFORMS_FOR_IMAGE)
    if need_media or need_count:
        add(ALL_PLATFORMS)

    satisfied = not (need_videos or need_images or need_media or need_count)
    return {
        "need_count": need_count,
        "need_images": need_images,
        "need_videos": need_videos,
        "need_media": need_media,
        "platforms": platforms,
        "satisfied": satisfied,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_discovery_gaps.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/discovery_gaps.py .claude/skills/subreddit-content/tests/test_discovery_gaps.py
git commit -m "feat(subreddit-content): add discovery gap analyzer"
```

---

### Task 5: Media-floor selection in `shortlist.py`

**Files:**
- Modify: `.claude/skills/subreddit-content/scripts/shortlist.py`
- Test: `.claude/skills/subreddit-content/tests/test_shortlist.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `build_shortlist(scored, mix, count, floor=None)` — new optional `floor: {"min_images": int, "min_videos": int} | None`. When given, guarantees at least `min_images` image-type and `min_videos` video-type candidates are selected (highest-scored of each), then fills the per-bucket mix quota (floor picks count toward the media quota) and backfills to `count`. `floor=None` preserves the existing behavior exactly. `bucket_of` unchanged.

- [ ] **Step 1: Write the failing test**

Append to `.claude/skills/subreddit-content/tests/test_shortlist.py`:
```python
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
```

(The existing `_c(...)` helper and prior tests stay unchanged — they exercise `floor=None`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_shortlist.py -v`
Expected: FAIL — `build_shortlist() got an unexpected keyword argument 'floor'`.

- [ ] **Step 3: Rewrite `build_shortlist` with the floor option**

Replace `build_shortlist` in `scripts/shortlist.py` with:
```python
def build_shortlist(scored: list[dict], mix: dict[str, int], count: int, floor: dict | None = None) -> list[dict]:
    """Select up to *count* candidates.

    If *floor* is given ({"min_images","min_videos"}), guarantee that many
    image/video candidates (highest-scored) are selected first. Then satisfy
    the per-bucket *mix* quota (floor picks count toward the media quota) and
    backfill from remaining highest-scored candidates. Adds a 1-based
    ``post_number`` in final score-desc order."""
    by_bucket: dict[str, list[dict]] = {"media": [], "text": [], "news": []}
    for c in scored:
        by_bucket[bucket_of(c.get("post_type", "link"))].append(c)
    for b in by_bucket.values():
        b.sort(key=lambda c: c.get("score", 0), reverse=True)

    chosen: list[dict] = []
    chosen_ids: set[int] = set()

    def take(c) -> bool:
        if id(c) in chosen_ids:
            return False
        chosen.append(c)
        chosen_ids.add(id(c))
        return True

    # 1) media floor — guarantee >= min video and >= min image (highest scored)
    if floor:
        for post_type, key in (("video", "min_videos"), ("image", "min_images")):
            need = floor.get(key, 0)
            pool = sorted(
                (c for c in scored if c.get("post_type") == post_type),
                key=lambda c: c.get("score", 0), reverse=True,
            )
            for c in pool:
                if need <= 0:
                    break
                if take(c):
                    need -= 1

    # 2) per-bucket quota (already-chosen items count toward their bucket)
    for bucket, quota in mix.items():
        in_bucket = sum(1 for c in chosen if bucket_of(c.get("post_type", "link")) == bucket)
        for c in by_bucket.get(bucket, []):
            if in_bucket >= quota:
                break
            if take(c):
                in_bucket += 1

    # 3) backfill to reach count, highest score first
    if len(chosen) < count:
        for c in sorted(scored, key=lambda c: c.get("score", 0), reverse=True):
            if len(chosen) >= count:
                break
            take(c)

    chosen.sort(key=lambda c: c.get("score", 0), reverse=True)
    out = []
    for n, c in enumerate(chosen[:count], start=1):
        cc = dict(c)
        cc["post_number"] = n
        out.append(cc)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_shortlist.py -v`
Expected: PASS — new floor tests plus all pre-existing shortlist tests (floor=None path unchanged).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/shortlist.py .claude/skills/subreddit-content/tests/test_shortlist.py
git commit -m "feat(subreddit-content): add media-floor option to shortlist"
```

---

### Task 6: Extend the integration seam test (keywords → gaps → floor shortlist)

**Files:**
- Modify: `.claude/skills/subreddit-content/tests/test_integration_seam.py`

**Interfaces:**
- Consumes: `keyword_expand.merge_and_rank`, `discovery_gaps.analyze_pool`, `scoring.score_all`, `shortlist.build_shortlist`, `post_schema.validate_post`, `assemble.write_post`, `history.append_used`/`load_used`/`filter_unused`.

- [ ] **Step 1: Add the new seam test**

Append to `.claude/skills/subreddit-content/tests/test_integration_seam.py`:
```python
def test_v2_seam_keywords_to_floor_shortlist(tmp_path):
    from datetime import date
    import keyword_expand
    import discovery_gaps
    import scoring
    import shortlist
    import post_schema
    import assemble
    import history

    # 1) keyword expansion (mock DataForSEO rows)
    kw = keyword_expand.merge_and_rank(
        ["backyard chickens"],
        [{"keyword": "chicken coop", "search_volume": 8000},
         {"keyword": "silkie chickens", "search_volume": 3000}],
        max_queries=10,
    )
    assert kw["query_set"][0] == "backyard chickens"

    # 2) a pool that meets the media floor + count
    today = date(2026, 7, 3)
    pool = (
        [{"post_type": "video", "source_platform": "tiktok", "url": f"https://tiktok.com/v{i}",
          "title": f"vid {i}", "engagement": 1000, "date": "2026-07-01", "relevance": 0.8, "hook": 0.7}
         for i in range(6)]
        + [{"post_type": "image", "source_platform": "pinterest", "url": f"https://pinterest.com/i{i}",
            "title": f"img {i}", "engagement": 500, "date": "2026-07-02", "relevance": 0.7, "hook": 0.6}
           for i in range(6)]
        + [{"post_type": "text", "source_platform": "web", "url": f"https://ex.com/t{i}",
            "title": f"txt {i}", "engagement": 0, "date": "2026-07-02", "relevance": 0.6, "hook": 0.6}
           for i in range(5)]
    )
    gaps = discovery_gaps.analyze_pool(pool, count=15, min_images=1, min_videos=1, media_total=10)
    assert gaps["satisfied"] is True

    # 3) score + floor-aware shortlist
    scored = scoring.score_all(pool, today=today, days=30)
    picks = shortlist.build_shortlist(scored, {"media": 10, "text": 5, "news": 0}, 15,
                                      floor={"min_images": 1, "min_videos": 1})
    assert len(picks) == 15
    types = [p["post_type"] for p in picks]
    assert "video" in types and "image" in types

    # 4) build a delivered post, validate, write, and dedup round-trip
    p = picks[0]
    post = {
        "post_number": 1, "post_type": p["post_type"], "title": "Seam v2 title",
        "suggested_flair": "", "nsfw": False, "source_platform": p["source_platform"],
        "source_url": p["url"], "attribution": "@x", "media_file": "",
        "engagement_note": "", "status": "media_failed", "body": "b",
    }
    assert post_schema.validate_post(post) == []
    assemble.write_post(tmp_path, post)
    assert (tmp_path / "post-01" / "post.md").exists()

    hist = tmp_path / ".history" / "r-test.jsonl"
    history.append_used(hist, [post], run_folder="rf", date_used="2026-07-03")
    used = history.load_used(hist)
    assert history.filter_unused([{"url": p["url"]}], used) == []
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_integration_seam.py -v`
Expected: PASS (the new test plus the existing v1 seam test).

- [ ] **Step 3: Run the whole suite**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest -q`
Expected: PASS — all helpers (Tasks 1–5) plus both seam tests green.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/subreddit-content/tests/test_integration_seam.py
git commit -m "test(subreddit-content): extend seam test for v2 keyword+floor path"
```

---

### Task 7: `subreddit-content-keywords` sub-agent

**Files:**
- Create: `.claude/agents/subreddit-content-keywords.md`

Authored agent definition (no unit test — verified by a structure check). Mirrors the front-matter + "Input / Output contract / Workflow" shape of `.claude/agents/reddit-research-serp.md`.

- [ ] **Step 1: Write the agent file**

`.claude/agents/subreddit-content-keywords.md`:
```markdown
---
name: subreddit-content-keywords
description: Phase 1 of the /subreddit-content pipeline. Generates niche seed terms (plus any operator-supplied seeds), expands them via DataForSEO (keyword ideas, suggestions, related keywords), then merges/ranks/dedups into a capped query set written to keywords.json. Single-purpose; called by the /subreddit-content orchestrator only.
tools: Read, Write, Bash, mcp__dataforseo__serp_locations, mcp__dataforseo__dataforseo_labs_google_keyword_ideas, mcp__dataforseo__dataforseo_labs_google_keyword_suggestions, mcp__dataforseo__dataforseo_labs_google_related_keywords
---

You are the Phase 1 keyword agent for the /subreddit-content pipeline. Your single job is to produce `keywords.json` in the working folder.

## Input

The orchestrator provides:
- `working_folder`: absolute path.
- `niche`: the target niche string.
- `seeds`: optional list of operator-supplied seed terms (may be empty).
- `subreddit_name`: the subreddit being filled (context for relevance).
- `max_queries`: int cap on the final query set (default 40).
- `country`: 2-letter code for DataForSEO location (default `us`).

## Output contract

Write `<working_folder>/keywords.json`:
```json
{
  "seeds": ["..."],
  "expanded": [{"term": "...", "volume": 1234, "source": "seed|dataforseo"}],
  "query_set": ["...ranked..."],
  "platform_queries": ["...short, social-friendly..."],
  "broad_queries": ["...full set..."],
  "generated_at": "<ISO-8601>"
}
```

## Workflow

1. **Resolve location** — call `mcp__dataforseo__serp_locations` for `country` to get a `location_code` (default to the US code if unresolved). Non-fatal on failure.
2. **Generate seeds** — write 8–15 seed terms for `niche`: core topics, subtopics, and platform-native variants (short/hashtag-style and phrase-style). Merge in the operator `seeds` (always keep them).
3. **Expand via DataForSEO (always)** — for the strongest seeds, call `dataforseo_labs_google_keyword_ideas`, `dataforseo_labs_google_keyword_suggestions`, and `dataforseo_labs_google_related_keywords`. Collect `{keyword, search_volume}` rows.
4. **Merge/rank/dedup** — write the seeds and the DataForSEO rows to temp JSON and call the deterministic helper:
   ```bash
   python3 ~/.claude/skills/subreddit-content/scripts/keyword_expand.py
   ```
   (Import `merge_and_rank(seeds, dataforseo_rows, max_queries=<max_queries>)` from `keyword_expand`; it returns `expanded / query_set / platform_queries / broad_queries`.)
5. **Write `keywords.json`** with the helper output plus `seeds` and `generated_at`.

## Failure handling

If DataForSEO errors or returns nothing, log it and proceed with Claude seeds only — expansion is enrichment, never a hard dependency. Note the degradation so the orchestrator can surface it in RUN-SUMMARY. Never fail the run for a DataForSEO error.

## This agent does NOT

Scrape platforms, score, or draft posts. It only produces the query set.
```

- [ ] **Step 2: Verify structure**

Run:
```bash
cd .claude/agents && python3 -c "
from pathlib import Path
t = Path('subreddit-content-keywords.md').read_text()
assert t.startswith('---') and 'name: subreddit-content-keywords' in t
for s in ['keywords.json','keyword_expand','dataforseo_labs_google_keyword_ideas','query_set','platform_queries','Failure handling']:
    assert s in t, f'missing: {s}'
print('keywords agent OK')
"
```
Expected: `keywords agent OK`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/subreddit-content-keywords.md
git commit -m "feat(subreddit-content): add keywords sub-agent"
```

---

### Task 8: `subreddit-content-discovery` sub-agent (parameterized by platform)

**Files:**
- Create: `.claude/agents/subreddit-content-discovery.md`

Authored agent definition, invoked once per platform (platform passed in the dispatch prompt), run concurrently. Verified by a structure check.

- [ ] **Step 1: Write the agent file**

`.claude/agents/subreddit-content-discovery.md`:
```markdown
---
name: subreddit-content-discovery
description: Phase 2 of the /subreddit-content pipeline. Discovers fresh content for ONE platform (passed by the orchestrator) using the expanded query set, applies the YouTube Shorts filter, normalizes + history-filters + dedups, and writes candidates.<platform>.json. Dispatched once per platform and run concurrently. Single-purpose; called by the /subreddit-content orchestrator only.
tools: Read, Write, Bash, WebFetch, mcp__apify__search-actors, mcp__apify__fetch-actor-details, mcp__apify__call-actor, mcp__apify__get-dataset-items
---

You are a Phase 2 discovery agent for the /subreddit-content pipeline. You cover EXACTLY ONE platform and produce `candidates.<platform>.json`.

## Input

The orchestrator provides:
- `working_folder`: absolute path.
- `platform`: one of `tiktok | instagram | pinterest | youtube`.
- `queries`: the query set (prefer `platform_queries` from keywords.json; fall back to `query_set`).
- `days`: freshness window (only keep items dated within the last `days` days).
- `history_path`: path to `.history/r-<sub-slug>.jsonl` for dedup.

## What to pull, per platform

- **tiktok** — recent/trending videos for the queries. `post_type: "video"`.
- **instagram** — reels (`post_type: "video"`) AND image posts (`post_type: "image"`) for the queries/hashtags.
- **pinterest** — pins for the queries. `post_type: "image"`.
- **youtube** — **Shorts only** (`post_type: "video"`). Never long-form.

## Fetch order (per the repo rule)

For each fetch, try in order and stop at the first that works: **plain WebFetch → Apify actor → Firecrawl** (Firecrawl only if available in this environment). For Apify: `mcp__apify__search-actors` / `fetch-actor-details` to pick and inspect an actor for the platform, then `call-actor`, then read results via `get-dataset-items`.

## YouTube Shorts enforcement

For `platform == youtube`, after collecting items, keep only Shorts using the helper:
```bash
python3 ~/.claude/skills/subreddit-content/scripts/shorts_filter.py
```
(Import `filter_shorts(items)` from `shorts_filter`: keeps an item only if its URL contains `/shorts/` or its duration ≤ 60s.) Drop everything else.

## Normalize + dedup

Emit each candidate in this exact shape:
```json
{"title": "...", "post_type": "video|image", "source_platform": "<platform>",
 "url": "...", "engagement": 1234, "date": "YYYY-MM-DD",
 "thumbnail": "...", "media_url": "..."}
```
Then:
- Drop items older than `days`.
- Run `history.filter_unused(candidates, history.load_used(history_path))` (import from `history`).
- Dedup within this platform via `history.normalize_url`.

## Output contract

Write `<working_folder>/candidates.<platform>.json` = a JSON list of normalized candidates. If the platform yields nothing, write `[]` and report the shortfall — do not fail the run.

## This agent does NOT

Score, draft, download media, or touch other platforms. One platform, normalized candidates only.
```

- [ ] **Step 2: Verify structure**

Run:
```bash
cd .claude/agents && python3 -c "
from pathlib import Path
t = Path('subreddit-content-discovery.md').read_text()
assert t.startswith('---') and 'name: subreddit-content-discovery' in t
for s in ['candidates.','shorts_filter','filter_shorts','WebFetch','Apify','history.filter_unused','Shorts only','media_url']:
    assert s in t, f'missing: {s}'
print('discovery agent OK')
"
```
Expected: `discovery agent OK`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/subreddit-content-discovery.md
git commit -m "feat(subreddit-content): add per-platform discovery sub-agent"
```

---

### Task 9: Rewrite `SKILL.md` Phases 0–3 + update run-summary template

**Files:**
- Modify: `.claude/skills/subreddit-content/SKILL.md`
- Modify: `.claude/skills/subreddit-content/templates/run-summary-template.md`

The orchestrator prose is rewritten to insert Phase 1 (keyword agent), rebuild Phase 2 (parallel discovery fan-out + gap-fill loop), update Phase 3 (media floor), and document the new config + escalation ladder. Verified by a structure check (no unit test — Claude-executed prose).

- [ ] **Step 1: Replace the Phase 1 + Phase 2 sections and update the phase table/config**

Edit `SKILL.md` so it contains these sections (replacing the old single "Phase 1 — Discovery" section). Keep the existing Phase 0 intake steps but add the parallel dispatch and the new config; keep Phases for media fetch + assemble as they are (renumbered to 4 and 5).

Phase table (near the top) becomes:
```markdown
| Phase | Does | Key tools |
| --- | --- | --- |
| 0 | Parse input (+ --seeds, mix 10/5, media floor), read sub rules/flairs, load history | input_parser.py, Apify reddit-scraper, history.py |
| 1 | Keyword seeding + DataForSEO expansion → query set | subreddit-content-keywords agent |
| 2 | Parallel per-platform discovery + gap-fill loop | subreddit-content-discovery agents, discovery_gaps.py, shorts_filter.py |
| 3 | Score, type, media-floor shortlist → review gate | scoring.py, shortlist.py |
| 4 | Download + validate media for the shortlist | video-downloader skill, media_validate.py |
| 5 | Assemble per-post folders + summary, append history | assemble.py, history.py |
```

Add/replace these sections:
````markdown
## Phase 0 — Intake + guardrails

1. Parse the invocation (now supports `--seeds "a, b, c"`, `--max-queries`, `--max-rounds`, `--media-floor img,vid`; default mix is `media=10, text=5`):
   ```bash
   python3 ~/.claude/skills/subreddit-content/scripts/input_parser.py <subreddit-url> "<niche>" [flags]
   ```
   Non-zero exit → surface verbatim and stop. Capture the config (adds `seeds`, `max_queries`, `max_rounds`, `media_floor`).
2. Confirm CWD writable (`touch`/`rm` a probe file).
3. **Parallel kickoff** — in a SINGLE message, both:
   - fetch the target subreddit sidebar/rules/flairs via `mcp__apify__harshmaur--reddit-scraper`, and
   - dispatch the `subreddit-content-keywords` agent (Phase 1).
   They are independent (rules feed drafting in Phase 3; keywords feed discovery), so they run concurrently.
4. Load history via `history.load_used(.history/r-<slug>.jsonl)`.
5. Create the run folder now via `assemble.run_folder_name(niche, subreddit_name, today)`; write `run-config.json` into it. Log start via `run_log.py`.
6. Announce sub, niche, count + mix (10/5), media floor, window, history-skip count.

## Phase 1 — Keyword expansion (agent)

Handled by the `subreddit-content-keywords` agent dispatched in Phase 0's parallel kickoff. When it returns, read `keywords.json` (`query_set`, `platform_queries`, `broad_queries`). If it degraded to seeds-only (DataForSEO failure), note it for RUN-SUMMARY. Do not gate — proceed straight to discovery.

## Phase 2 — Discovery (parallel fan-out + gap-fill loop)

1. **Fan out** — the moment `keywords.json` is available, dispatch the four `subreddit-content-discovery` agents **in a single message** (platforms: `tiktok`, `instagram`, `pinterest`, `youtube`) so they run concurrently. Pass each: platform, `platform_queries` (fallback `query_set`), `days`, `history_path`.
2. **Merge** each agent's `candidates.<platform>.json` into one pool (the agents already history-filtered + deduped within platform; dedup across platforms with `history.normalize_url`).
3. **Analyze gaps** with `discovery_gaps.analyze_pool(pool, count=<count>, min_images=<floor.min_images>, min_videos=<floor.min_videos>, media_total=<mix['media']>)`.
4. **Escalation ladder** — while `not satisfied` and rounds used `< max_rounds`, climb one rung per round, then re-dispatch ONLY `gaps["platforms"]` (in parallel) with the round's queries; re-merge; re-analyze:
   1. gap-fill: targeted re-queries for the missing floor categories.
   2. deepen: use `broad_queries` (more DataForSEO terms).
   3. relax freshness: widen `days` for this round.
   4. adjacent: Claude-generated adjacent-niche terms.
5. Stop when satisfied or `max_rounds` reached. Any residual `need_count` is filled with **text** posts in Phase 3. Record, per post, which ladder rung sourced it (for RUN-SUMMARY).

## Phase 3 — Score, type, media-floor shortlist

1. For each candidate attach `relevance` (0..1), `hook` (0..1), and finalize `post_type`.
2. `scoring.score_all(pool, today=<date>, days=<days>)` then
   `shortlist.build_shortlist(scored, mix, count, floor=<media_floor>)` — the floor guarantees ≥1 image AND ≥1 video. If a floor can't be met from the pool, select what exists and mark the shortfall (text backfill covers the count).
3. Draft `title` (≤300) + `body` per post (media/link → caption + credit; text → discussion prompt grounded in a real trend). `suggested_flair` only from the sub's real flairs.
4. Write `shortlist.json`. **Review gate** (unless `--auto`): show the table (#, type, platform, title, score, source, ladder-rung) via `AskUserQuestion` [Approve / Edit / Re-shortlist / Abort]. `--auto` prints + proceeds.
````

Also update the "Phase overview" numbering for the media-fetch and assemble sections to **Phase 4** and **Phase 5** (content otherwise unchanged), and update the run-mode/error-envelope references that mention phase numbers.

- [ ] **Step 2: Update the run-summary template**

Replace `.claude/skills/subreddit-content/templates/run-summary-template.md` with:
```markdown
# Run summary — r/<sub> (<niche>) — <YYYY-MM-DD>

**Run folder:** <folder name>
**Requested:** <count> posts | mix media=<m> text=<t> | window <days>d | floor img>=<i> vid>=<v>
**Keywords:** <n seeds> seeds → <n query_set> queries (DataForSEO: ok | degraded-to-seeds)

## Delivered
- Media posts:   <n> (images <ni>, videos <nv>; <n ok> with file, <n> media_failed → link-post fallback)
- Text posts:    <n>
- **Total:**     <n> / 15

## Sources (vet before scheduling)
| # | type | platform | attribution | source_url | ladder rung | status |
|---|------|----------|-------------|------------|-------------|--------|
| 01 | video | tiktok | @creator (TikTok) | https://... | broad pass | ready |

## Escalation
- Rounds used: <r> / <max_rounds>
- Rungs climbed: <e.g. broad → gap-fill(video) → deepen>
- Text backfill used to reach 15: <yes/no, how many>

## Skipped / failed
- <url> — <reason (already in history / download failed / oversize / long-form dropped)>

## Notes
- <partial platform outages, DataForSEO degradation, fallbacks used>
```

- [ ] **Step 3: Verify structure**

Run:
```bash
cd .claude/skills/subreddit-content && python3 -c "
from pathlib import Path
s = Path('SKILL.md').read_text()
for x in ['Phase 1 — Keyword expansion','subreddit-content-keywords','Phase 2 — Discovery','subreddit-content-discovery','discovery_gaps.analyze_pool','single message','Escalation ladder','floor=<media_floor>','max_rounds']:
    assert x in s, f'SKILL missing: {x}'
t = Path('templates/run-summary-template.md').read_text()
for x in ['ladder rung','floor img','Escalation','DataForSEO']:
    assert x in t, f'template missing: {x}'
print('SKILL + template OK')
"
```
Expected: `SKILL + template OK`.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/subreddit-content/SKILL.md .claude/skills/subreddit-content/templates/run-summary-template.md
git commit -m "feat(subreddit-content): v2 orchestration — keyword phase, parallel discovery, gap-fill ladder"
```

---

### Task 10: Update README, CLAUDE.md, smoke-test doc; full-suite green

**Files:**
- Modify: `.claude/skills/subreddit-content/README.md`
- Modify: `.claude/skills/subreddit-content/CLAUDE.md`
- Modify: `.claude/skills/subreddit-content/docs/smoke-test-procedure.md`

- [ ] **Step 1: Update README.md**

In `.claude/skills/subreddit-content/README.md`, update the invocation line and add a "What's new (v2)" note:
```markdown
    /subreddit-content <subreddit-url> "<niche>" [--count 15] [--mix media=10,text=5] [--days 30] [--seeds "a, b, c"] [--max-queries 40] [--max-rounds 3] [--media-floor 1,1] [--auto]
```
Add:
```markdown
## v2 — thin-niche coverage

Every run seeds keywords (Claude + DataForSEO) and expands them, then discovers
across TikTok, Instagram (reels+images), Pinterest, and **YouTube Shorts only**
using parallel per-platform sub-agents. It guarantees 15 posts with a media
floor of at least one image AND one video; if a thin niche runs short, an
escalation ladder widens the search and finally backfills with text posts.
`RUN-SUMMARY.md` records how each post was sourced.
```

- [ ] **Step 2: Update CLAUDE.md**

In `.claude/skills/subreddit-content/CLAUDE.md`, under the helper list add:
```markdown
- `keyword_expand.py` — `merge_and_rank(seeds, dataforseo_rows, *, max_queries, platform_max_words)`; ranked/deduped query set.
- `shorts_filter.py` — `is_short(url, duration)`, `filter_shorts(items)`; YouTube Shorts-only gate.
- `discovery_gaps.py` — `analyze_pool(pool, *, count, min_images, min_videos, media_total)`; floor/count gap analysis + platform targeting.
- `shortlist.build_shortlist(..., floor={"min_images","min_videos"})` — media-floor-aware selection.
```
Under agents add:
```markdown
- Sub-agents (`.claude/agents/`): `subreddit-content-keywords` (Phase 1), `subreddit-content-discovery` (Phase 2, one per platform, dispatched in parallel).
```
Update the invariants block: default mix is now **10 media / 5 text** (news defaults 0); **media floor ≥1 image AND ≥1 video**; **YouTube Shorts only**; **≥15 guaranteed** via the bounded escalation ladder (`--max-rounds`, default 3) with text backfill; keyword set capped by `--max-queries` (default 40); DataForSEO is enrichment-only.

- [ ] **Step 3: Update the smoke-test procedure**

In `.claude/skills/subreddit-content/docs/smoke-test-procedure.md`, add to the helper-CLI section:
```markdown
    python3 scripts/keyword_expand.py "backyard chickens, chicken coop"
Expect: JSON with query_set led by the seed terms.
```
And add a v2 pipeline section:
```markdown
## 5. v2 pipeline checks
- Phase 1: keywords agent writes keywords.json (query_set + platform_queries). DataForSEO failure degrades to seeds-only, run continues.
- Phase 2: the 4 discovery agents are dispatched in ONE message (parallel). YouTube results are Shorts only (no /watch? long-form). Each writes candidates.<platform>.json.
- Gap-fill: force a thin niche (e.g. --days 3) and confirm the escalation ladder climbs (RUN-SUMMARY "Escalation" shows rungs) and still delivers 15 with >=1 image and >=1 video (text backfill if needed).
- Phase 3: shortlist honors the media floor even when media scores low.
```

- [ ] **Step 4: Run the full suite**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest -v`
Expected: PASS — all v1 tests plus the new `keyword_expand`, `shorts_filter`, `discovery_gaps`, shortlist-floor, and v2 seam tests.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/README.md .claude/skills/subreddit-content/CLAUDE.md .claude/skills/subreddit-content/docs/smoke-test-procedure.md
git commit -m "docs(subreddit-content): v2 README/CLAUDE/smoke-test updates"
```

---

## Self-Review

**Spec coverage:**
- Keyword seeding + DataForSEO expansion every run → Task 2 (`keyword_expand`) + Task 7 (keywords agent). ✓
- Optional operator `--seeds` → Task 1. ✓
- Per-platform Apify discovery, parallel sub-agents → Task 8 + Task 9 Phase 2 fan-out. ✓
- YouTube Shorts only → Task 3 (`shorts_filter`) + Task 8 enforcement. ✓
- IG reels+images / TikTok / Pinterest images → Task 8 per-platform table. ✓
- ≥15 guarantee + escalation ladder + text backfill → Task 4 (`discovery_gaps`) + Task 9 Phase 2 loop. ✓
- Media floor ≥1 image AND ≥1 video → Task 1 constants + Task 5 (`shortlist` floor) + Task 9 Phase 3. ✓
- Default mix 10/5, drop news default → Task 1. ✓
- No keyword gate; keep shortlist gate → Task 9 (Phase 1 "do not gate"; Phase 3 review gate retained). ✓
- RUN-SUMMARY sourcing/ladder column → Task 9 template. ✓
- Parallelism seams (intake ∥ keywords; discovery fan-out; gap-fill fan-out) → Task 9 Phases 0 + 2. ✓
- Unchanged tail (media_validate, assemble, post_schema, history, review gate) → untouched; seam test Task 6 confirms they still compose. ✓
- Tests for each new deterministic helper + extended seam test → Tasks 2–6. ✓

**Placeholder scan:** No TBD/TODO. Every code step has concrete code; every doc step shows the exact text to add.

**Type consistency:** `merge_and_rank` return keys (`expanded/query_set/platform_queries/broad_queries`) match Task 6 seam usage, Task 7 agent output contract, and Task 9 Phase 2. `analyze_pool` return keys (`need_count/need_images/need_videos/need_media/platforms/satisfied`) match Task 6 + Task 9. `build_shortlist(scored, mix, count, floor=None)` signature consistent across Task 5, Task 6, Task 9. Config keys (`seeds/max_queries/max_rounds/media_floor`) consistent Task 1 ↔ Task 9. `post_type ∈ {video,image,text,link}` and mix buckets `{media,text,news}` unchanged from v1. Candidate shape (`url` field) consistent with `history` (`append_used` already accepts `url`/`source_url`).

No gaps found.
