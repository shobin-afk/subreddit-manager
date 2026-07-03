# Subreddit Content Workflow — Design Spec

**Date:** 2026-07-02
**Status:** Approved (design), pending implementation plan
**Skill name:** `/subreddit-content`
**Owner:** shobin@ignitefirst.io

---

## 1. Purpose

A weekly content-sourcing and drafting workflow for subreddits the operator *owns/manages* across various niches. Given one subreddit URL and its niche, the workflow discovers fresh content across YouTube, TikTok, Instagram, Pinterest, news sites, and niche blogs; shortlists 10–20 post ideas; downloads media files for native Reddit uploads; and produces a review-ready deliverable the operator manually schedules via Reddit's post scheduler.

### Explicitly NOT this workflow
- **Not** `/reddit-research`. That skill finds existing Reddit threads for *client brand mentions* (Month 1 marketing SOP). This workflow *creates original content* to populate subreddits the operator runs.
- **Does not** source ideas from Reddit or other subreddits — discovery deliberately excludes Reddit as a source platform.
- **Does not** auto-post to Reddit. No Reddit auth in this environment; account-safety rules apply. Deliverable-only.

---

## 2. Locked requirements (from brainstorming)

| Decision | Choice |
|----------|--------|
| Post model | **Native uploads** — download `.mp4`/`.jpg` files for native Reddit image/video posts. Attribution/source captured for operator vetting. |
| Run scope | **One subreddit per run.** Input = subreddit URL + niche (+ optional flags). |
| Sourcing engine | **Hybrid (Approach C):** `last30days` skill for wide discovery → targeted Apify actors on the shortlist for full media/metadata → `video-downloader` for files. Firecrawl last resort. |
| Content mix | **Balanced** default: ~7 media repost / ~5 text-discussion / ~3 news-link per 15. Overridable via `--mix`. |
| Dedup | **History log** per subreddit; weekly runs skip previously-used URLs. |
| Deliverable | Timestamped folder → one subfolder per post → `post.md` + media file inside each. Operator schedules manually. |

---

## 3. Tooling & reuse

Priority chain for any fetch (operator's rule): **web-fetch → Apify actor → Firecrawl.**

- `last30days` skill — wide discovery sweep across platforms (Reddit source stripped).
- `video-downloader` skill (yt-dlp) — media file download.
- Apify MCP — `apify--google-search-scraper` (news/blogs), platform scraper actors (TikTok/IG/YT/Pinterest) for shortlist metadata + media URLs, `harshmaur--reddit-scraper` for the *target* sub's sidebar/rules/flairs only.
- Firecrawl MCP — fallback scrape/extract when web-fetch + Apify both fail.
- DataForSEO MCP (optional) — niche keyword expansion / trend signal for seed terms.

Deterministic work (scoring math, validation, history, folder assembly) → Python helpers. Judgment work (niche relevance, hook rating, drafting titles/bodies) → Claude.

---

## 4. Architecture — five phases

### Phase 0 — Intake + guardrails
- Parse subreddit URL + niche + optional flags: `--count` (default 15), `--mix` (default `media=7,text=5,news=3`), `--days` (default 30), `--auto` (skip review gates).
- Fetch target subreddit sidebar/rules/flairs via `harshmaur--reddit-scraper`. Capture: allowed post types, NSFW policy, self-promo rules, existing flair list.
- Load history log `.history/r-<sub>.jsonl` → build set of already-used URLs.
- Write `run-config.json`.

### Phase 1 — Discovery (wide, cheap)
- Run `last30days` on niche keywords → candidates across YouTube, TikTok, Instagram, Pinterest, news, web.
- **Drop** any Reddit-sourced items.
- **Drop** any URL present in history.
- Emit `candidates.json`: `{title, platform, url, engagement, date, thumbnail}`.
- Partial platform failure is non-fatal — continue with whatever returned, log the gap.

### Phase 2 — Score + shortlist + assign type
- Score each candidate 0–100:
  - engagement (per-platform normalized) — 35%
  - freshness (within `--days`) — 20%
  - niche relevance (Claude judgment) — 30%
  - hook (curiosity/funny/controversy) — 15%
- Bucket-fill to the mix ratio (reserve text/news slots even if media scores higher).
- Text/news posts are drafted *from* discovered trends (a trending video → discussion prompt; an article → link post + take) — grounded in real fresh signal, never invented.
- Emit `shortlist.json` (top N).
- **Review gate** (default): operator approves the shortlist before Phase 3. `--auto` skips.

### Phase 3 — Media fetch (precise, shortlist only)
- Per media idea: `video-downloader` (yt-dlp) for video; direct fetch for images.
- Fallback per item: web-fetch → Apify actor → Firecrawl.
- Validate: non-zero, valid container, within Reddit limits (video ≤ 1GB / 15 min, images ≤ 20MB; downscale or flag if over).
- Unrecoverable → `status: media_failed`; post still written with `source_url` for manual link-post fallback.
- Text/news posts: no download.

### Phase 4 — Assemble + write
- Build `post-NN/` folders, one `post.md` each, media file dropped alongside.
- Append used URLs to history log.
- Write `RUN-SUMMARY.md` (counts, mix achieved, failures, all source URLs for vetting).

Review gate default between Phase 2 and Phase 3.

---

## 5. I/O contract

**Invocation:**
```
/subreddit-content <subreddit-url> "<niche>" [--count 15] [--mix media=7,text=5,news=3] [--days 30] [--auto]
```

**Output tree:**
```
<niche-slug>-r-<sub>-<YYYY-MM-DD>/
  run-config.json
  RUN-SUMMARY.md
  post-01/
    post.md
    media.mp4          # only if media post; ext varies
  post-02/
    post.md            # text post, no media
  ...
  post-15/
```

**`post.md` schema:**
```markdown
---
post_number: 3
post_type: video          # video | image | text | link
title: "Title — <=300 chars (Reddit limit)"
suggested_flair: "Funny"  # from sub's real flair list, or ""
nsfw: false
source_platform: tiktok
source_url: https://www.tiktok.com/@creator/video/123
attribution: "@creator (TikTok)"
media_file: media.mp4     # "" if none
engagement_note: "1.2M likes, posted 4 days ago"
status: ready             # ready | media_failed | needs_review
---

<post body: the description / self-text to paste into Reddit.
Media/link posts: 2–4 sentence framing/caption + credit line.
Text posts: full discussion prompt.>
```

Front-matter is machine-checkable (validator enforces title length, flair ∈ sub flair list, media_file exists when type is media). Body reads plainly for copy-paste.

---

## 6. History / dedup

- File: `.history/r-<sub>.jsonl`, persisted across runs at the skill working root.
- One line per used item: `{url, title, date_used, run_folder}`.
- Phase 1 filters candidates against it; Phase 4 appends.
- Normalized-URL fingerprint (strip query params) so the same media surfaced via two search paths dedups.

---

## 7. Error handling

- Structured error envelope in `RUN-SUMMARY.md` (mirrors `reddit-research` pattern). Run never dies silently — operator always gets whatever succeeded.
- Discovery: partial platform failure → continue + log.
- Media: full fallback chain exhausted → `media_failed`, not a hard stop.
- Every failure recorded with the reason and the surviving fallback (e.g. source_url for manual link-post).

---

## 8. Safety & compliance constraints

- **Attribution captured for every reposted item**; `RUN-SUMMARY.md` lists all sources so the operator vets copyright / subreddit rules before scheduling.
- Drafts respect the *target sub's own* sidebar rules and flair list (Phase 0).
- **Never auto-posts.** Human reviews and schedules in the Reddit UI.
- Reddit file limits enforced pre-delivery.

---

## 9. Packaging

Self-contained skill directory, mirroring `.claude/skills/reddit-research/`:
```
.claude/skills/subreddit-content/
  SKILL.md
  README.md
  scripts/           # scoring, validation, history, folder assembly (Python)
  templates/         # post.md template, RUN-SUMMARY template
  docs/
  tests/             # pytest suite (scoring, dedup, validation, assembly)
  pyproject.toml
```

Deterministic logic in Python + unit tests; orchestration and drafting in `SKILL.md` (Claude).

---

## 10. Out of scope (v1)

- Batch mode across multiple subreddits (single-sub per run only; config format left open for later).
- Auto-posting / Reddit scheduler API integration.
- Sourcing from Reddit itself.
- Cross-subreddit content reuse.
