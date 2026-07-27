# subreddit-manager

A Claude Code skill — **`/subreddit-content`** — that sources weekly content ideas for a subreddit you manage.

Given one subreddit URL + niche, it:
- seeds + expands keywords (Claude + DataForSEO) so even thin niches have enough to search,
- discovers fresh content in parallel across TikTok, Instagram (reels + images), Pinterest, and **YouTube Shorts** (never long-form; never Reddit),
- scores + shortlists ~15 post ideas at a media/text mix, guaranteeing a media floor of **at least one image AND one video** (an escalation ladder widens the search for thin niches, with text-discussion backfill to always reach the count),
- downloads media files for native Reddit uploads,
- writes a per-post folder deliverable with weekly dedup.

Deliverable-only — it never posts to Reddit. You schedule manually in Reddit's post scheduler.

## Install

The skill uses two sub-agents, so copy **both** the skill and the agents into your Claude Code config (project-level or `~/.claude/`):

```bash
git clone https://github.com/shobin-afk/subreddit-manager.git
# skill:
cp -r subreddit-manager/.claude/skills/subreddit-content ~/.claude/skills/
# its sub-agents:
mkdir -p ~/.claude/agents
cp subreddit-manager/.claude/agents/subreddit-content-*.md ~/.claude/agents/
```

Already installed? Just `git pull` in your clone and re-copy the two directories.

Then in Claude Code:

```
/subreddit-content <subreddit-url> "<niche>" [--count 15] [--mix media=10,text=5] [--days 30] [--seeds "a, b, c"] [--max-queries 40] [--max-rounds 3] [--media-floor 1,1] [--auto]
```

Example:

```
/subreddit-content https://www.reddit.com/r/BackyardChickens/ "backyard chickens"
```

## Output

```
<niche-slug>-r-<sub-slug>-<YYYY-MM-DD>/
  run-config.json
  RUN-SUMMARY.md          # counts, mix, media floor, sources, escalation rungs
  post-01/
    post.md
    media.mp4             # only if a media post; ext varies
  post-02/
    post.md
  ...
```

Each `post.md` carries the title, body, source URL, attribution, suggested flair, and status. `RUN-SUMMARY.md` lists every source (vet before scheduling) and how each post was found.

## Requirements

- Claude Code with the `last30days` and `video-downloader` skills, plus Apify + DataForSEO MCP (Firecrawl optional). Discovery/keyword work runs through the two bundled sub-agents.
- Python 3.10+ for the helper scripts (stdlib only — nothing to `pip install`).

## Dedup

Used source URLs are logged to `.history/r-<sub-slug>.jsonl`; each run skips anything already used.

## Develop

```bash
cd .claude/skills/subreddit-content
python3 -m pytest -v
```

## Docs

- v1 design + plan: [docs/2026-07-02-subreddit-content-workflow-design.md](docs/2026-07-02-subreddit-content-workflow-design.md), [docs/2026-07-02-subreddit-content-workflow.md](docs/2026-07-02-subreddit-content-workflow.md)
- v2 (keyword expansion + parallel discovery): [docs/2026-07-03-subreddit-content-keyword-expansion-design.md](docs/2026-07-03-subreddit-content-keyword-expansion-design.md), [docs/2026-07-03-subreddit-content-keyword-expansion.md](docs/2026-07-03-subreddit-content-keyword-expansion.md)
- Skill usage + output detail: [.claude/skills/subreddit-content/README.md](.claude/skills/subreddit-content/README.md)
- Manual end-to-end check: [.claude/skills/subreddit-content/docs/smoke-test-procedure.md](.claude/skills/subreddit-content/docs/smoke-test-procedure.md)
