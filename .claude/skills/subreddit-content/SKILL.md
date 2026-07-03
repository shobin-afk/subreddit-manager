---
name: subreddit-content
description: Weekly content-sourcing workflow for a subreddit you manage. Given one subreddit URL and its niche, discovers fresh content across YouTube, TikTok, Instagram, Pinterest, news, and blogs (never Reddit), shortlists ~15 post ideas at a balanced media/text/news mix, downloads media files for native Reddit uploads, and writes a per-post folder deliverable (post-NN/post.md + media) with weekly dedup. Deliverable-only — never auto-posts. Use when the user gives a subreddit URL + niche and asks to source, ideate, draft, or fill weekly content for a sub they run.
---

# /subreddit-content

You orchestrate a five-phase content-sourcing pipeline for **one** subreddit the operator manages. You produce a review-ready deliverable; you NEVER post to Reddit.

Skill scripts live at `~/.claude/skills/subreddit-content/scripts/` (use the absolute install path). All output is written into CWD.

## Phase overview

| Phase | Does | Key tools |
| --- | --- | --- |
| 0 | Parse input, read sub rules/flairs, load history | input_parser.py, Apify reddit-scraper, history.py |
| 1 | Wide discovery across platforms (drop Reddit + history) | `last30days` skill |
| 2 | Score, assign type, bucket-fill shortlist → review gate | scoring.py, shortlist.py |
| 3 | Download + validate media for the shortlist | `video-downloader` skill, media_validate.py |
| 4 | Assemble per-post folders + summary, append history | assemble.py, history.py |

## Phase 0 — Intake + guardrails

1. Parse the invocation:
   ```bash
   python3 ~/.claude/skills/subreddit-content/scripts/input_parser.py <subreddit-url> "<niche>" [--count N] [--mix media=7,text=5,news=3] [--days 30] [--auto]
   ```
   If it exits non-zero, surface the error verbatim and stop. Capture the JSON config (`subreddit_name`, `subreddit_slug`, `niche`, `count`, `mix`, `days`, `auto`).
2. Confirm CWD is writable:
   ```bash
   touch .subreddit-content-permission-check && rm .subreddit-content-permission-check
   ```
3. Read the target subreddit's sidebar/rules/flairs via `mcp__apify__harshmaur--reddit-scraper` (fetch the sub URL). Capture: allowed post types, NSFW policy, self-promo rules, the **exact flair list**. If the scraper errors, log it and continue with an empty flair list (flairs become optional).
4. Load history: read `.history/r-<subreddit_slug>.jsonl` via `history.load_used`. If absent, start empty.
5. Create the run folder now — all inputs it needs (niche, subreddit_name, today's date) are already known: `assemble.run_folder_name(niche, subreddit_name, today)`, created under CWD.
6. Write `run-config.json` (the parsed config + resolved flair list + today's date) **into the run folder** and log start:
   ```bash
   python3 ~/.claude/skills/subreddit-content/scripts/run_log.py run.log phase=intake event=ok sub=<slug> count=<count>
   ```
7. Announce: sub, niche, target count + mix, freshness window, how many history URLs will be skipped. Then start Phase 1.

## Phase 1 — Discovery (wide, cheap)

1. Invoke the **`last30days`** skill with the niche keywords (and 2–4 obvious niche synonyms) to pull fresh posts across YouTube, TikTok, Instagram, Pinterest, news, and the web within the `days` window.
2. **Drop every Reddit-sourced item** — discovery must not surface other subreddits' content.
3. Normalize each candidate to: `{title, post_type_hint, source_platform, url, engagement, date (YYYY-MM-DD), thumbnail}`. `post_type_hint` ∈ {video, image, text, link}.
4. Filter against history with `history.filter_unused`.
5. Write `candidates.json`. If a platform errored, continue with the rest and log the gap (partial is fine, never fatal). If **zero** candidates survive, surface that (likely too-narrow niche or everything already used) and offer: widen synonyms / increase `--days` / abort.

## Phase 2 — Score, type, shortlist

1. For each candidate, judge and attach:
   - `relevance` (0..1) — how on-topic for this niche + this specific sub.
   - `hook` (0..1) — curiosity / humor / mild-controversy pull ("makes you click").
   - `post_type` — final type: `video`/`image` (has downloadable media), `text` (discussion prompt grounded in a trend), or `link` (news/blog).
2. Score:
   ```bash
   python3 - <<'PY'
   # illustrative: call scoring.score_all over candidates.json with today + days
   PY
   ```
   Use `scoring.score_all(candidates, today=<date>, days=<days>)`, then `shortlist.build_shortlist(scored, mix, count)`.
3. Draft, for each shortlisted idea, a Reddit `title` (≤300 chars) and `body`:
   - media/link → 2–4 sentence caption/framing + a credit line naming the creator.
   - text → a full discussion prompt, grounded in a real discovered trend (never invented).
   - Set `suggested_flair` only from the sub's real flair list (else empty). Respect the sub's rules (NSFW, self-promo).
4. Write `shortlist.json`. **Review gate** (unless `--auto`): present the shortlist as a table (#, type, platform, title, score, source) via `AskUserQuestion`:
   - `Approve — download media + assemble`
   - `Edit — I'll adjust shortlist.json, then continue`
   - `Re-shortlist with different mix/count`
   - `Abort`
   In `--auto`, print the table and proceed.

## Phase 3 — Media fetch (shortlist only)

For each post with `post_type` in {video, image}:
1. **video:** invoke the `video-downloader` skill on `source_url` (yt-dlp). **image:** fetch directly.
2. Fallback per item, in order: plain web-fetch → relevant Apify actor → Firecrawl. Only escalate when the prior step fails.
3. Save into the post's folder as `media.<ext>`. Validate:
   ```bash
   python3 ~/.claude/skills/subreddit-content/scripts/media_validate.py  # via import: validate_media(path, post_type, duration=...)
   ```
   If `media_failed`: set the post's `status: media_failed`, keep `source_url` (operator can link-post manually), and log the reason. Never hard-stop the run for one failed download.
Text/link posts: no download.

## Phase 4 — Assemble + record

1. The run folder was already created in Phase 0 (`assemble.run_folder_name(niche, subreddit_name, today)`); reuse that same path — do not recreate it.
2. For each post: `assemble.write_post(run_dir, post, allowed_flairs=<flair list>)`, then move its validated media file into `post-NN/`. On `AssembleError`, fix the offending field (title length / missing key) and retry that post.
3. Append the used source URLs of every delivered post to `.history/r-<slug>.jsonl` via `history.append_used(path, items, run_folder=<name>, date_used=<today>)`.
4. Fill `templates/run-summary-template.md` and write it with `assemble.write_run_summary` (counts, mix achieved, full source table, skipped/failed list).
5. Log done and print the final block: run folder path, totals (delivered by bucket, media_failed count, platforms used, history skips), and the reminder to vet sources + schedule manually in Reddit.

## Run mode

- **default (review):** stop at the Phase 2 gate via `AskUserQuestion`.
- **--auto:** skip the gate; still hard-stop on zero candidates or a non-writable CWD.

## Error envelope

1. Capture errors verbatim (Apify run ID, yt-dlp stderr, Python stderr).
2. Append to `run.log` via `run_log.py phase=<n> event=error message="..."`.
3. Surface with the artefacts that DID complete; offer retry / continue-partial / abort.
Never fail silently. Never delete intermediate artefacts on error.

## This skill does NOT

- Post or schedule to Reddit (operator does this manually in the Reddit scheduler).
- Source ideas from Reddit or other subreddits.
- Run more than one subreddit per invocation.
If asked for any of those, explain the boundary and stop.
