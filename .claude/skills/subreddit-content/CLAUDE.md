# CLAUDE.md — subreddit-content skill

Guidance for Claude Code when working on the `/subreddit-content` skill. These instructions override default behavior for this folder.

## What this is

A Claude Code skill that sources a week of post ideas for **a subreddit the operator manages**. Input: one subreddit URL + niche. Output: a timestamped folder of drafted posts (title + body + source + attribution) with downloaded media files, ready for the operator to schedule manually in Reddit's post scheduler.

Deliverable-only. It **never posts to Reddit** and **never sources ideas from Reddit** (discovery is cross-platform: YouTube, TikTok, Instagram, Pinterest, news, blogs). Do not add a posting path or a Reddit-scraping discovery path.

Not to be confused with the separate `reddit-research` skill (client brand-mention research) — different purpose, different repo history.

## Two-repo layout — read before committing

| Copy | Location | Role |
| --- | --- | --- |
| **Source of truth** | `.claude/skills/subreddit-content/` in the *Local Reddit Marketing Service* workspace | Full git history, branch, tests. Do all development here. |
| **Public mirror** | `github.com/shobin-afk/subreddit-manager` (PUBLIC) | Skill-only subtree + `docs/` the team pulls. No SOP, no pricing, no other skills. |

Develop and test in the source of truth. To publish an update to the team, re-sync the skill subtree to the mirror (clean copy, tracked files only — never the SOP/CLAUDE.md-pricing/reddit-research/agents from the parent workspace). The mirror is **public**: never add client PII, credentials, proxy auth, or real business pricing to any file under this skill.

## Architecture

Deterministic logic lives in stdlib-only Python helpers under `scripts/`, each with one responsibility and a unit test. Orchestration + judgment (niche relevance, hook rating, drafting titles/bodies) live in `SKILL.md`, which Claude executes. Keep that split: math/validation/IO in Python; language + decisions in the orchestrator.

### Helpers (`scripts/`) and their interfaces

- `slug.py` — `slugify(name) -> str` (raises `SlugError`). Folder/history naming.
- `run_log.py` — `append_event(path, **fields)`, `parse_log(path)`. Structured run log.
- `input_parser.py` — `parse_invocation(argv) -> config`, `parse_mix`, `default_mix`, `InputError`. Config keys: subreddit_url, subreddit_name, subreddit_slug, niche, count, mix, days, auto, seeds, max_queries, max_rounds, media_floor.
- `history.py` — `normalize_url`, `load_used(path) -> set`, `filter_unused(cands, used)`, `append_used(path, items, *, run_folder, date_used)`. Weekly dedup.
- `scoring.py` — `score_candidate`, `score_all(cands, *, today, days)`. `WEIGHTS` = engagement .35 / freshness .20 / relevance .30 / hook .15. 0..100.
- `shortlist.py` — `bucket_of(post_type)`, `build_shortlist(scored, mix, count, floor={"min_images","min_videos"})`. Media-floor-aware selection; bucket-fill to the mix, backfill, assign 1-based `post_number`.
- `media_validate.py` — `validate_media(path, post_type, *, duration=None) -> {status, reason}`. Reddit limits.
- `post_schema.py` — `validate_post(post, *, allowed_flairs=None) -> list[str]`. `REQUIRED_KEYS`, `TITLE_MAX=300`, `POST_TYPES`, `STATUSES`.
- `assemble.py` — `run_folder_name`, `render_post_md`, `write_post` (validates → raises `AssembleError`), `write_run_summary`.
- `keyword_expand.py` — `merge_and_rank(seeds, dataforseo_rows, *, max_queries, platform_max_words)`; ranked/deduped query set.
- `shorts_filter.py` — `is_short(url, duration)`, `filter_shorts(items)`; YouTube Shorts-only gate.
- `discovery_gaps.py` — `analyze_pool(pool, *, count, min_images, min_videos, media_total)`; floor/count gap analysis + platform targeting.

### Sub-agents (`.claude/agents/`)

- `subreddit-content-keywords` (Phase 1): Seeds keywords, queries DataForSEO, outputs keywords.json with query_set + platform_queries.
- `subreddit-content-discovery` (Phase 2): One per platform (TikTok, Instagram, Pinterest, YouTube Shorts), dispatched in parallel; each outputs candidates.<platform>.json.

### Data flow (mind the seams)

```
input_parser.parse_invocation
   → subreddit-content-keywords agent: keyword_expand.merge_and_rank(seeds, dataforseo_rows)
        → keywords.json {query_set, platform_queries, broad_queries}
   → subreddit-content-discovery agents (parallel, one per platform: tiktok/instagram/pinterest/youtube)
        → candidates.<platform>.json
        {title, url, engagement, date, source_platform, post_type}
   → merge pool across platforms → discovery_gaps.analyze_pool(pool, count, min_images, min_videos, media_total)
        → escalation ladder: re-dispatch discovery agents for gaps["platforms"] until satisfied or max_rounds
   → text backfill (Phase 3) tops the pool up to `count` with synthetic post_type=text candidates
   → scoring.score_all → shortlist.build_shortlist
   → Claude drafts a post dict shaped by post_schema.REQUIRED_KEYS
   → post_schema.validate_post → assemble.write_post
   → history.append_used
```

**Vocab that must stay consistent across every module, the templates, and SKILL.md:**
- `post_type` ∈ `{video, image, text, link}`
- mix bucket ∈ `{media, text, news}` (`bucket_of`: video/image→media, text→text, link→news)
- `status` ∈ `{ready, media_failed, needs_review}`
- the post dict's URL field is **`source_url`**, but a *discovery candidate*'s URL field is **`url`**. `history.append_used` accepts both (`url` or `source_url`) — keep it that way. This mismatch already caused a silent dedup break once; guard it.

## Hard invariants (do not regress)

- **stdlib only** at runtime — no third-party runtime deps. `pytest` is dev-only.
- **Never auto-post; discovery never touches Reddit.**
- Reddit limits, exact: video ≤ `1073741824` B and ≤ `900` s; image ≤ `20971520` B.
- Title ≤ `300` chars.
- **Defaults (v2):** mix `media=10,text=5` (news defaults 0), `count=15`, `days=30`, `max-queries=40`, `max-rounds=3`.
- **Media floor (v2):** ≥1 image AND ≥1 video guaranteed.
- **YouTube Shorts only (v2):** no /watch? long-form videos; discovery via parallel sub-agents (TikTok, Instagram, Pinterest, YouTube Shorts).
- **≥15 guaranteed (v2):** bounded escalation ladder (loops up to `--max-rounds`, default 3) widens search; text backfill if media runs short.
- **Keyword set (v2):** capped by `--max-queries` (default 40); DataForSEO is enrichment-only, not a gate.
- Output tree: `<niche-slug>-r-<sub-slug>-<YYYY-MM-DD>/` with zero-padded 1-based `post-NN/` folders, each `post.md` (+ media file only for media posts), plus `run-config.json` + `RUN-SUMMARY.md`.
- History: `.history/r-<sub-slug>.jsonl`, one JSON object per line `{url, title, date_used, run_folder}`.
- `post.md` front-matter is driven by `post_schema.REQUIRED_KEYS` (order = REQUIRED_KEYS minus `body`). Change the schema and the template + renderer follow automatically — don't hardcode a parallel key list.

## Development

```bash
cd .claude/skills/subreddit-content
python3 -m pytest -v          # expect 88 passing (v1 tests + v2 keyword/shorts/gaps/floor/seam tests + shorts_filter CLI test)
python3 scripts/<helper>.py   # several helpers have a CLI entrypoint
```

- **TDD for every change**: write/adjust the failing test first, then the code. Match the existing test style (bare-module imports via `tests/conftest.py`; `tmp_path` for filesystem).
- When you add or change a helper that sits on a data-flow seam, extend `tests/test_integration_seam.py` — the per-helper tests miss cross-module field/type drift.
- Keep each `scripts/*.py` single-purpose and small. If one grows unwieldy, split by responsibility, not by layer.
- Commit style: `feat|fix|docs(subreddit-content): …`.

## claude.ai chat limitation (known)

This skill targets **Claude Code** (local Bash, filesystem, the `last30days` + `video-downloader` skills, Apify/Firecrawl MCP). It does **not** run unmodified in the claude.ai chat app: no Bash, ephemeral sandbox (dedup history won't persist), network-restricted (native media download blocked), and the two dependency skills are absent. For browser use, point the team at **claude.ai/code** (Claude Code on the web), which runs it as-is. Don't try to make the chat app a supported target without an explicit decision to build a degraded variant.

## Out of scope (v1)

Batch mode across multiple subreddits; auto-posting / scheduler-API integration; sourcing from Reddit; cross-subreddit reuse. Confirm scope before adding any of these.
