---
name: subreddit-content
description: Weekly content-sourcing workflow for a subreddit you manage. Given one subreddit URL and its niche, discovers fresh content across YouTube, TikTok, Instagram, Pinterest, news, and blogs (never Reddit), shortlists ~15 post ideas at a media/text mix, downloads media files for native Reddit uploads, and writes a per-post folder deliverable (post-NN/post.md + media) with weekly dedup. Deliverable-only — never auto-posts. Use when the user gives a subreddit URL + niche and asks to source, ideate, draft, or fill weekly content for a sub they run.
---

# /subreddit-content

You orchestrate a six-phase content-sourcing pipeline for **one** subreddit the operator manages. You produce a review-ready deliverable; you NEVER post to Reddit.

Skill scripts live at `~/.claude/skills/subreddit-content/scripts/` (use the absolute install path). All output is written into CWD.

## Phase overview

| Phase | Does | Key tools |
| --- | --- | --- |
| 0 | Parse input (+ --seeds, mix 10/5, media floor), read sub rules/flairs, load history | input_parser.py, Apify reddit-scraper, history.py |
| 1 | Keyword seeding + DataForSEO expansion → query set | subreddit-content-keywords agent |
| 2 | Parallel per-platform discovery + gap-fill loop | subreddit-content-discovery agents, discovery_gaps.py, shorts_filter.py |
| 3 | Score, type, media-floor shortlist → review gate | scoring.py, shortlist.py |
| 4 | Download + validate media for the shortlist | video-downloader skill, media_validate.py |
| 5 | Assemble per-post folders + summary, append history | assemble.py, history.py |

## Phase 0 — Intake + guardrails

1. Parse the invocation (now supports `--seeds "a, b, c"`, `--max-queries`, `--max-rounds`, `--media-floor img,vid`; default mix is `media=10, text=5`):
   ```bash
   python3 ~/.claude/skills/subreddit-content/scripts/input_parser.py <subreddit-url> "<niche>" [flags]
   ```
   Non-zero exit → surface verbatim and stop. Capture the config (adds `seeds`, `max_queries`, `max_rounds`, `media_floor`).
2. Confirm CWD writable (`touch`/`rm` a probe file).
3. **Parallel kickoff** — in a SINGLE message, both:
   - fetch the target subreddit sidebar/rules/flairs via `mcp__apify__harshmaur--reddit-scraper`. Capture: allowed post types, NSFW policy, self-promo rules, and the exact flair list. If the scraper errors, log it and continue with an empty flair list (flairs become optional) — non-fatal.
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
2. **Text backfill (discharges the ≥`count` guarantee before shortlisting):** If, after the escalation ladder, the deduped pool has fewer than `count` items, draft synthetic **text-discussion** posts (post_type=text) grounded in the `query_set` / discovered trends — enough to bring the pool to `count`. These are real discussion prompts tied to the niche, never invented filler. Mark each in RUN-SUMMARY with ladder rung `text backfill`. Add these to the pool before scoring — this is the step that actually performs the backfill Phase 2 only promised.
3. `scoring.score_all(pool, today=<date>, days=<days>)` then
   `shortlist.build_shortlist(scored, mix, count, floor=<media_floor>)` — the floor guarantees ≥1 image AND ≥1 video from the discovered (non-backfill) candidates. Because step 2 already brought the pool to ≥`count`, `build_shortlist` has enough items to reach `count`; the media floor is a separate, best-effort guarantee — if discovery genuinely surfaced zero images or zero videos across the whole run, select what exists and mark the shortfall in RUN-SUMMARY rather than failing the run.
4. Draft `title` (≤300) + `body` per post (media/link → caption + credit; text → discussion prompt grounded in a real trend). `suggested_flair` only from the sub's real flairs. Respect the sub's rules captured in Phase 0 (NSFW policy, self-promo limits); set `nsfw` accordingly and never draft a post that violates them.
5. Write `shortlist.json`. **Review gate** (unless `--auto`): show the table (#, type, platform, title, score, source, ladder-rung) via `AskUserQuestion` [Approve / Edit / Re-shortlist / Abort]. `--auto` prints + proceeds.

## Phase 4 — Media fetch (shortlist only)

For each post with `post_type` in {video, image}:
1. **video:** invoke the `video-downloader` skill on `source_url` (yt-dlp). **image:** fetch directly.
2. Fallback per item, in order: plain web-fetch → relevant Apify actor → Firecrawl. Only escalate when the prior step fails.
3. Save into the post's folder as `media.<ext>`. Validate:
   ```bash
   python3 ~/.claude/skills/subreddit-content/scripts/media_validate.py  # via import: validate_media(path, post_type, duration=...)
   ```
   If `media_failed`: set the post's `status: media_failed`, keep `source_url` (operator can link-post manually), and log the reason. Never hard-stop the run for one failed download.
Text/link posts: no download.

## Phase 5 — Assemble + record

1. The run folder was already created in Phase 0 (`assemble.run_folder_name(niche, subreddit_name, today)`); reuse that same path — do not recreate it.
2. For each post: `assemble.write_post(run_dir, post, allowed_flairs=<flair list>)`, then move its validated media file into `post-NN/`. On `AssembleError`, fix the offending field (title length / missing key) and retry that post.
3. Append the used source URLs of every delivered post to `.history/r-<slug>.jsonl` via `history.append_used(path, items, run_folder=<name>, date_used=<today>)`.
4. Fill `templates/run-summary-template.md` and write it with `assemble.write_run_summary` (counts, mix achieved, full source table, skipped/failed list).
5. Log done and print the final block: run folder path, totals (delivered by bucket, media_failed count, platforms used, history skips), and the reminder to vet sources + schedule manually in Reddit.

## Run mode

- **default (review):** stop at the Phase 3 gate via `AskUserQuestion`.
- **--auto:** skip the gate; still hard-stop on zero candidates, a non-writable CWD, or (after Phase 3's text backfill) a shortlist that is still below `count` — never let `--auto` finish under-count silently.

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
