# Subreddit-Content v2 — Keyword Expansion + Parallel Discovery — Design Spec

**Date:** 2026-07-03
**Status:** Approved (design), pending implementation plan
**Skill:** `/subreddit-content` (update to the existing skill)
**Owner:** shobin@ignitefirst.io
**Predecessor spec:** docs/superpowers/specs/2026-07-02-subreddit-content-workflow-design.md

---

## 1. Problem

A test run showed the skill under-supplies in **less-popular niches**: not enough fresh, relevant post ideas / image assets / video assets. Root cause: discovery relies on the generic `last30days` aggregator seeded with only the niche + 2–4 synonyms, and it can't guarantee per-platform depth or YouTube Shorts-only results.

## 2. Goals

- Add a **keyword-seeding + expansion step** before discovery (Claude seeds + DataForSEO MCP, every run) to widen and deepen the query set.
- **Guarantee ≥15 posts per run**, with a **media floor: ≥1 image AND ≥1 video** (aim ~10 media / 5 text).
- Source media from **Instagram (reels + images), TikTok (video), Pinterest (images), YouTube Shorts (video only — never long-form)**, plus text-discussion posts.
- **Parallelize** platform discovery across sub-agents; start discovery the instant keywords are ready.

## 3. Locked decisions (from brainstorming)

| Decision | Choice |
| --- | --- |
| Under-supply behavior | **Escalation ladder, then fill** — widen in ordered steps; if still short, backfill with text posts to reach 15, logging how each slot was sourced. |
| Target mix | **10 media / 5 text** by default; drop the news/link bucket from defaults. Media floor: **≥1 image AND ≥1 video**. |
| Discovery engine | **Per-platform Apify actors**, keyword-driven (replaces last30days as the discovery primary). |
| Keyword step | **Claude seeds + DataForSEO expansion every run.** Optional operator `--seeds`. |
| Keyword gate | **No gate** — auto-expand and proceed (only the existing shortlist gate remains). |
| Orchestration | **Pooled + targeted gap-fill (Approach C)** with a bounded escalation ladder. |
| Parallelism | **Sub-agent per platform**, dispatched concurrently; intake ∥ keyword expansion; gap-fill re-dispatches only needed platforms in parallel. |

## 4. Pipeline (new shape)

```
Phase 0  Intake + guardrails      (＋ optional --seeds; new default mix 10/5)
Phase 1  Keyword expansion  NEW   subreddit-content-keywords agent
Phase 2  Discovery          REBUILT  subreddit-content-discovery agents (parallel)
                                   + pooled/gap-fill loop
Phase 3  Score + shortlist  UPDATED  media-floor enforcement
Phase 4  Media fetch        UNCHANGED (download + media_validate Reddit limits)
Phase 5  Assemble + record  UNCHANGED (post-NN/, history append, RUN-SUMMARY)
```

### Escalation ladder (drives the Phase 2 gap-fill loop; stop as soon as ≥15 with floor met)
1. Broad pass on the expanded query set.
2. Gap-fill: targeted re-queries for missing floor categories (no video → YT Shorts + TikTok; no image → Pinterest + IG).
3. Deepen: pull more DataForSEO expansion terms, re-query.
4. Relax freshness: widen the `--days` window.
5. Adjacent-niche terms (Claude-generated), re-query.
6. Backfill remaining slots with text-discussion posts to guarantee 15.

Bounded by `--max-rounds` (default 3). `RUN-SUMMARY.md` records which rung sourced each post.

## 5. Orchestration & parallelism

Orchestrator (SKILL.md) stays thin; parallelizable work goes to sub-agents that return only normalized data (raw scraper output never enters orchestrator context).

**New agents (under `.claude/agents/`):**
- **`subreddit-content-keywords`** — Phase 1. One instance. Produces `keywords.json`.
- **`subreddit-content-discovery`** — Phase 2, **parameterized by platform**. One instance per platform, all dispatched in a single message → concurrent. Each owns its fallback chain (web-fetch → Apify → Firecrawl), Shorts filter, normalization, per-platform dedup. Produces `candidates.<platform>.json`.

**Parallelism seams:**
1. **Intake ∥ keywords** — after parsing input, the orchestrator fires the subreddit rules/flair fetch *and* dispatches the keywords agent in the same message (independent: rules feed drafting, keywords feed discovery).
2. **Discovery fan-out** — when `keywords.json` lands, all 4 platform agents launch together (one message, 4 Agent calls).
3. **Gap-fill fan-out** — on a floor/count miss, re-dispatch only the needed platform agents in parallel with laddered queries.

Sequential points remain only on real dependencies: keywords → discovery; full pool → scoring.

## 6. Phase 1 — Keyword expansion (agent detail)

**Inputs:** niche, optional `--seeds "a, b, c"`, `subreddit_name`, `location_code` (resolved once via DataForSEO `serp_locations`; default US).

**Steps:**
1. **Seeds** — Claude writes 8–15 seed terms: core topics, subtopics, and platform-native variants (hashtag-style + phrase-style). Operator `--seeds` merged in and always kept.
2. **DataForSEO expansion (always)** — for the strongest seeds, call `dataforseo_labs_google_keyword_ideas`, `dataforseo_labs_google_keyword_suggestions`, `dataforseo_labs_google_related_keywords`. Capture term + search volume.
3. **Merge / rank / dedup** — helper `keyword_expand.py`: normalize case/whitespace, drop near-dupes, rank by blend of (seed-origin priority, DataForSEO volume, brevity for social search), cap at `--max-queries` (default 40). Split into `platform_queries` (short/hashtag-friendly) and `broad_queries`.
4. **Write `keywords.json`**: `{ seeds:[...], expanded:[{term, volume, source}], query_set:[...ranked], platform_queries:[...], broad_queries:[...], generated_at }`.

**Failure handling:** DataForSEO error/empty → log, proceed with Claude seeds only (expansion is enrichment, never a hard dependency). Surfaced in RUN-SUMMARY.

## 7. Phase 2 — Discovery (agent detail + loop)

Each platform agent receives: platform, `query_set`, `days`, history set. Returns normalized candidates for its platform only.

| Platform | Pulls | Media type |
| --- | --- | --- |
| TikTok | trending/recent videos for queries | video |
| Instagram | reels **and** image posts for queries/hashtags | video + image |
| Pinterest | pins for queries | image |
| YouTube | **Shorts only** | video |

Fallback per fetch: web-fetch → Apify → Firecrawl.

**YouTube Shorts enforcement** — helper `shorts_filter.py`: keep an item only if its URL contains `/shorts/` **or** its duration ≤ 60s. Applied at the agent boundary; long-form never enters the pool. Unit-tested on URL + duration cases.

**Normalization** — every agent emits the existing candidate shape `{title, post_type, source_platform, url, engagement, date, thumbnail, media_url}`, runs `history.filter_unused`, dedups within platform via `history.normalize_url`.

**Pooled + gap-fill loop (orchestrator):**
1. Launch 4 agents in parallel → merge into one pool.
2. Helper `discovery_gaps.py`: given pool, target count (15), and media floor (`min_images≥1`, `min_videos≥1`, media_total≥10), return `need_video`, `need_image`, `need_count`, and which platforms to hit per gap.
3. If gaps: climb the ladder — re-dispatch only needed platform agents in parallel with laddered queries. Cap at `--max-rounds` (default 3).
4. Stop when floor + count satisfiable, or rounds exhausted → remaining slots to text backfill in Phase 3.

`shorts_filter.py` and `discovery_gaps.py` are deterministic → unit-tested. Scraping lives in the agents.

## 8. Phase 3 — Score + shortlist (media floor)

Extend `shortlist` with a media-floor-aware selection (`build_shortlist_with_floor` or a `floor=` parameter on `build_shortlist`) taking `{min_images, min_videos, media_total}`:
- Guarantee ≥1 image and ≥1 video selected first, then fill the media quota by score, then text.
- If the pool can't meet a floor, select what exists and signal the shortfall → text backfill + honest RUN-SUMMARY.

Unit-tested: floor-met, image-short, video-short, everything-short. Scoring weights (`scoring.py`) unchanged.

## 9. Config changes (`input_parser.py`)

- New default mix: **`media=10, text=5`**. The `news`/`link` bucket remains in code, selectable via `--mix`, defaults to 0 (backward compatible).
- New flags: `--seeds "a, b, c"`, `--max-queries` (default 40), `--max-rounds` (default 3), optional `--media-floor img,vid`.
- Media-floor constants: `MIN_IMAGES=1`, `MIN_VIDEOS=1`.

## 10. New / changed artifacts

**New helpers (stdlib, unit-tested):** `keyword_expand.py`, `shorts_filter.py`, `discovery_gaps.py`, plus the shortlist floor logic.
**New agents:** `subreddit-content-keywords`, `subreddit-content-discovery` (per-platform).
**SKILL.md:** rewritten Phases 1–2, updated Phase 3 + config, escalation ladder + parallel fan-out documented; RUN-SUMMARY gains a "source / ladder rung" column.
**Templates:** `run-summary-template.md` gains the sourcing column; `keywords.json` shape documented.

## 11. Unchanged (explicitly)

Phase 4 media download + `media_validate` (Reddit limits: video ≤1073741824 B / ≤900 s, image ≤20971520 B); Phase 5 assemble + `post.md` schema (`post_schema.REQUIRED_KEYS`) + `history` append; the shortlist review gate; `slug`, `run_log`. Hard invariants hold: never auto-post, never source from Reddit, stdlib-only runtime, title ≤300, output tree `<niche-slug>-r-<sub-slug>-<YYYY-MM-DD>/`, `.history/r-<sub-slug>.jsonl` dedup.

## 12. Testing

- Each new deterministic helper gets a `test_*.py`.
- Extend the integration seam test to cover: keyword-set (mock) → `discovery_gaps` → floor-enforced shortlist.
- Agents exercised via the smoke-test doc (updated with the two new agents, the parallel fan-out, Shorts-only check, and a thin-niche escalation walk-through), not unit tests.

## 13. Out of scope (v2)

Auto-posting; sourcing from Reddit; multi-subreddit batch; making the claude.ai chat app a supported target. DataForSEO is enrichment only — no hard dependency.
