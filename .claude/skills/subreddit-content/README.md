# subreddit-content skill

Weekly content-sourcing workflow for a subreddit you manage. Given one
subreddit URL + niche, it discovers fresh cross-platform content (YouTube,
TikTok, Instagram, Pinterest, news, blogs — never Reddit), shortlists ~15
ideas at a balanced media/text/news mix, downloads media for native Reddit
uploads, and writes a per-post folder deliverable with weekly dedup.
Deliverable-only — never posts to Reddit.

## Invoke

    /subreddit-content <subreddit-url> "<niche>" [--count 15] [--mix media=7,text=5,news=3] [--days 30] [--auto]

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

## Dedup

Used source URLs are logged to `.history/r-<sub-slug>.jsonl`; each run skips
anything already used.

## Dev

    cd .claude/skills/subreddit-content
    python3 -m pytest -v

Runtime helpers are stdlib-only. See `docs/smoke-test-procedure.md` for a
manual end-to-end check.
