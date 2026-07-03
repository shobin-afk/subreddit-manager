# subreddit-manager

A Claude Code skill — **`/subreddit-content`** — that sources weekly content ideas for a subreddit you manage.

Given one subreddit URL + niche, it:
- discovers fresh content across YouTube, TikTok, Instagram, Pinterest, news, and blogs (never Reddit),
- scores + shortlists ~15 post ideas at a balanced media / text / news mix,
- downloads media files for native Reddit uploads,
- writes a per-post folder deliverable with weekly dedup.

Deliverable-only — it never posts to Reddit. You schedule manually in Reddit's post scheduler.

## Install

Copy the skill into your Claude Code skills directory (project-level or `~/.claude/`):

```bash
cp -r .claude/skills/subreddit-content /path/to/your/project/.claude/skills/
# or, user-level:
cp -r .claude/skills/subreddit-content ~/.claude/skills/
```

Then in Claude Code:

```
/subreddit-content <subreddit-url> "<niche>" [--count 15] [--mix media=7,text=5,news=3] [--days 30] [--auto]
```

See [.claude/skills/subreddit-content/README.md](.claude/skills/subreddit-content/README.md) for full usage and output format.

## Requirements

- Claude Code with the `last30days` and `video-downloader` skills, plus Apify + Firecrawl MCP configured.
- Python 3.10+ for the helper scripts (stdlib only — no third-party runtime deps).

## Develop

```bash
cd .claude/skills/subreddit-content
python3 -m pytest -v
```

## Docs

- Design spec: [docs/2026-07-02-subreddit-content-workflow-design.md](docs/2026-07-02-subreddit-content-workflow-design.md)
- Implementation plan: [docs/2026-07-02-subreddit-content-workflow.md](docs/2026-07-02-subreddit-content-workflow.md)
