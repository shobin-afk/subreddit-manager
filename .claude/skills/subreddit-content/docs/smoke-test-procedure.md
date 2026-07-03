# Smoke test — subreddit-content

Manual end-to-end verification. Requires `last30days`, `video-downloader`,
Apify + Firecrawl MCP reachable.

## 1. Unit suite
    cd .claude/skills/subreddit-content && python3 -m pytest -v
Expect: all green.

## 2. Helper CLIs
    python3 scripts/input_parser.py "https://www.reddit.com/r/BackyardChickens/" "backyard chickens"
Expect: JSON config with subreddit_slug=backyardchickens, mix 7/5/3, count 15.

    python3 scripts/slug.py "Backyard Chickens"
Expect: backyard-chickens

## 3. Dry pipeline (small)
Invoke in a scratch folder:
    /subreddit-content https://www.reddit.com/r/BackyardChickens/ "backyard chickens" --count 5 --days 14

Verify:
- Phase 0 prints sub + flair list + history-skip count.
- Phase 1 writes candidates.json with NO reddit.com sources.
- Phase 2 shows a shortlist table and stops at the review gate.
- After approval, Phase 3 downloads at least one media file and validates it.
- Phase 4 produces `backyard-chickens-r-backyardchickens-<date>/` with
  `post-01..05/`, each holding a `post.md`; media posts also hold a file.
- `.history/r-backyardchickens.jsonl` gains one line per delivered post.
- Re-running immediately yields different candidates (history dedup working).

## 4. Failure paths
- Bad URL → Phase 0 stops with the parser error verbatim.
- Force a download failure → that post gets status: media_failed, run still finishes.
