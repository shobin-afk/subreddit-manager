# subreddit-content skill

Weekly content-sourcing workflow for a subreddit you manage. Given one
subreddit URL + niche, it discovers fresh cross-platform content (YouTube,
TikTok, Instagram, Pinterest — sourcing text ideas from news, blogs; never
Reddit), shortlists ~15 ideas at a balanced media/text mix, downloads media
for native Reddit uploads, and writes a per-post folder deliverable with
weekly dedup. Deliverable-only — never posts to Reddit.

## Invoke

    /subreddit-content <subreddit-url> "<niche>" [--count 15] [--mix media=10,text=5] [--days 30] [--seeds "a, b, c"] [--max-queries 40] [--max-rounds 3] [--media-floor 1,1] [--auto]

## Output

    <niche-slug>-r-<sub-slug>-<YYYY-MM-DD>/
      run-config.json
      RUN-SUMMARY.md
      post-01/
        post.md
        media.mp4        # only if a media post
      post-02/
        post.md
      ...

## v2 — thin-niche coverage

Every run seeds keywords (Claude + DataForSEO) and expands them, then discovers
across TikTok, Instagram (reels+images), Pinterest, and **YouTube Shorts only**
using parallel per-platform sub-agents. It guarantees 15 posts with a media
floor of at least one image AND one video; if a thin niche runs short, an
escalation ladder widens the search and finally backfills with text posts.
`RUN-SUMMARY.md` records how each post was sourced.

## Dedup

Used source URLs are logged to `.history/r-<sub-slug>.jsonl`; each run skips
anything already used.

## Dev

    cd .claude/skills/subreddit-content
    python3 -m pytest -v

Runtime helpers are stdlib-only. See `docs/smoke-test-procedure.md` for a
manual end-to-end check.
