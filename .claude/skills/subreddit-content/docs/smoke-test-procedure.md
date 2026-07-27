# Smoke test — subreddit-content

Manual end-to-end verification. Requires `last30days`, `video-downloader`,
Apify + Firecrawl MCP reachable.

## 1. Unit suite
    cd .claude/skills/subreddit-content && python3 -m pytest -v
Expect: all green.

## 2. Helper CLIs
    python3 scripts/input_parser.py "https://www.reddit.com/r/BackyardChickens/" "backyard chickens"
Expect: JSON config with subreddit_slug=backyardchickens, mix 10/5, count 15.

    python3 scripts/slug.py "Backyard Chickens"
Expect: backyard-chickens

    python3 scripts/keyword_expand.py "backyard chickens, chicken coop"
Expect: JSON with query_set led by the seed terms.

## 3. Dry pipeline (small)
Invoke in a scratch folder:
    /subreddit-content https://www.reddit.com/r/BackyardChickens/ "backyard chickens" --count 5 --days 14

Verify (v2 phase numbering: keyword=1, discovery=2, shortlist gate=3, media=4, assemble=5):
- Phase 0 prints sub + flair list + history-skip count.
- Phase 1 (keyword agent) writes keywords.json with a query_set (DataForSEO ok or degraded-to-seeds noted).
- Phase 2 (discovery) writes candidates.<platform>.json per platform with NO reddit.com sources.
- Phase 3 shows a shortlist table and stops at the review gate.
- After approval, Phase 4 downloads at least one media file and validates it.
- Phase 5 produces `backyard-chickens-r-backyardchickens-<date>/` with
  `post-01..05/`, each holding a `post.md`; media posts also hold a file.
- `.history/r-backyardchickens.jsonl` gains one line per delivered post.
- Re-running immediately yields different candidates (history dedup working).

## 4. Failure paths
- Bad URL → Phase 0 stops with the parser error verbatim.
- Force a download failure → that post gets status: media_failed, run still finishes.

## 5. v2 pipeline checks
- Phase 1: keywords agent writes keywords.json (query_set + platform_queries). DataForSEO failure degrades to seeds-only, run continues.
- Phase 2: the 4 discovery agents are dispatched in ONE message (parallel). YouTube results are Shorts only (no /watch? long-form). Each writes candidates.<platform>.json.
- Gap-fill: force a thin niche (e.g. --days 3) and confirm the escalation ladder climbs (RUN-SUMMARY "Escalation" shows rungs) and still delivers 15 with >=1 image and >=1 video (text backfill if needed).
- Phase 3: shortlist honors the media floor even when media scores low.
