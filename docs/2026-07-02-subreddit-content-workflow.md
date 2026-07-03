# Subreddit Content Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/subreddit-content` skill — a weekly workflow that, given one subreddit URL + niche, discovers fresh cross-platform content, shortlists ~15 post ideas at a balanced type mix, downloads media for native Reddit uploads, and writes a per-post folder deliverable with weekly dedup.

**Architecture:** A self-contained skill package at `.claude/skills/subreddit-content/`, mirroring `.claude/skills/reddit-research/`. Deterministic logic (arg parsing, URL dedup, scoring, bucket-fill, media validation, folder assembly) lives in unit-tested Python helpers under `scripts/`. Orchestration, discovery, and drafting live in `SKILL.md` (Claude), which invokes the existing `last30days` skill (discovery) and `video-downloader` skill (media files), with a web-fetch → Apify → Firecrawl fallback chain. Review-gated between shortlist and download.

**Tech Stack:** Python 3.10+ stdlib only (no runtime deps; `pytest` for tests). Existing skills `last30days`, `video-downloader`. Apify + Firecrawl MCP. yt-dlp (via video-downloader).

## Global Constraints

- Skill directory: `.claude/skills/subreddit-content/` — mirror the layout of `.claude/skills/reddit-research/`.
- Python: `requires-python = ">=3.10"`; **stdlib only** for runtime helpers (no `openpyxl`/third-party at runtime); `pytest>=7.0` dev-only.
- Never auto-post to Reddit. Deliverable-only. Human schedules manually.
- Discovery must **exclude Reddit** as a source platform.
- Reddit file limits enforced pre-delivery: **video ≤ 1073741824 bytes (1 GB) and ≤ 900 seconds (15 min); image ≤ 20971520 bytes (20 MB)**.
- Reddit **title max = 300 characters**.
- Default content mix ratio **media:text:news = 7:5:3**; default `count = 15`; default freshness window `days = 30`.
- Output tree: `<niche-slug>-r-<sub-slug>-<YYYY-MM-DD>/` containing `run-config.json`, `RUN-SUMMARY.md`, and `post-NN/` subfolders (zero-padded, 1-based) each with `post.md` (+ media file only if the post has media).
- History log path: `.history/r-<sub-slug>.jsonl` at the skill working root; one JSON object per line: `{"url", "title", "date_used", "run_folder"}`.
- Every reposted item records `attribution` + `source_url`; `RUN-SUMMARY.md` lists all sources for operator vetting.
- Test import convention: `tests/conftest.py` inserts `scripts/` onto `sys.path`; tests import helpers by bare module name (e.g. `from slug import slugify`).
- Commit after every task with a `feat:`/`test:`/`docs:` message.

---

### Task 1: Skill package scaffold + `slug.py`

**Files:**
- Create: `.claude/skills/subreddit-content/pyproject.toml`
- Create: `.claude/skills/subreddit-content/scripts/__init__.py`
- Create: `.claude/skills/subreddit-content/tests/__init__.py`
- Create: `.claude/skills/subreddit-content/tests/conftest.py`
- Create: `.claude/skills/subreddit-content/scripts/slug.py`
- Test: `.claude/skills/subreddit-content/tests/test_slug.py`

**Interfaces:**
- Produces: `slugify(name: str) -> str` (lowercase ASCII, non-alnum → single `-`, stripped; raises `SlugError` on empty result). `SlugError(ValueError)`.

- [ ] **Step 1: Create the package skeleton files**

`.claude/skills/subreddit-content/pyproject.toml`:
```toml
[project]
name = "subreddit-content-skill"
version = "0.1.0"
description = "IgniteFirst subreddit content-sourcing workflow — weekly post ideation + media"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
```

`.claude/skills/subreddit-content/scripts/__init__.py`: empty file.

`.claude/skills/subreddit-content/tests/__init__.py`: empty file.

`.claude/skills/subreddit-content/tests/conftest.py`:
```python
"""Pytest configuration — make scripts/ importable from tests/."""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
```

- [ ] **Step 2: Write the failing test**

`.claude/skills/subreddit-content/tests/test_slug.py`:
```python
"""Tests for slug.slugify — filesystem-safe slug from niche / subreddit name."""
import pytest

from slug import slugify, SlugError


def test_simple_name_lowercases():
    assert slugify("Backyard Chickens") == "backyard-chickens"


def test_collapses_non_alphanumerics():
    assert slugify("r/AITA & Drama!!") == "r-aita-drama"


def test_strips_leading_trailing_hyphens():
    assert slugify("--Foo--") == "foo"


def test_numbers_preserved():
    assert slugify("Top 10 Fails") == "top-10-fails"


def test_empty_raises():
    with pytest.raises(SlugError):
        slugify("   ")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_slug.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'slug'`.

- [ ] **Step 4: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/slug.py`:
```python
"""Slugify a niche or subreddit name into a filesystem-safe identifier."""
import re


class SlugError(ValueError):
    """Raised when a name cannot produce a non-empty slug."""


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lowercase ASCII slug: non-alphanumerics collapse to a single ``-``,
    leading/trailing ``-`` stripped. Raises ``SlugError`` if empty."""
    if not isinstance(name, str):
        raise SlugError(f"name must be str, got {type(name).__name__}")
    ascii_only = name.encode("ascii", errors="ignore").decode("ascii").lower()
    slug = _NON_ALNUM.sub("-", ascii_only).strip("-")
    if not slug:
        raise SlugError(f"name {name!r} produces empty slug after normalisation")
    return slug


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("usage: slug.py <name>", file=sys.stderr)
        sys.exit(2)
    try:
        print(slugify(sys.argv[1]))
    except SlugError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_slug.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/subreddit-content/
git commit -m "feat(subreddit-content): scaffold package + slug helper"
```

---

### Task 2: `run_log.py` — append-only structured run log

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/run_log.py`
- Test: `.claude/skills/subreddit-content/tests/test_run_log.py`

**Interfaces:**
- Produces: `append_event(path, **fields) -> None` (writes `<ISO-UTC-timestamp> key=value ...`, quoting values with spaces); `parse_log(path) -> list[dict]` (each dict has `timestamp` plus the key/values).

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_run_log.py`:
```python
"""Tests for run_log — append/parse round-trip of structured events."""
from run_log import append_event, parse_log


def test_round_trip_simple(tmp_path):
    log = tmp_path / "run.log"
    append_event(log, phase="discovery", event="ok", candidates=42)
    events = parse_log(log)
    assert len(events) == 1
    assert events[0]["phase"] == "discovery"
    assert events[0]["event"] == "ok"
    assert events[0]["candidates"] == "42"
    assert "timestamp" in events[0]


def test_quotes_values_with_spaces(tmp_path):
    log = tmp_path / "run.log"
    append_event(log, phase="media", event="error", message="download failed hard")
    events = parse_log(log)
    assert events[0]["message"] == "download failed hard"


def test_appends_multiple_lines(tmp_path):
    log = tmp_path / "run.log"
    append_event(log, event="a")
    append_event(log, event="b")
    assert len(parse_log(log)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_run_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_log'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/run_log.py`:
```python
"""Append-only structured log for the subreddit-content skill.

Each event is one line: ``<ISO-timestamp> key=value key=value ...``. Values
containing whitespace are double-quoted.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_NEEDS_QUOTING = re.compile(r"\s")


def append_event(path: str | Path, **fields: Any) -> None:
    """Append a single event line with the given ``key=value`` fields."""
    p = Path(path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = [ts]
    for k, v in fields.items():
        s = str(v)
        if _NEEDS_QUOTING.search(s):
            s = '"' + s.replace('"', '\\"') + '"'
        parts.append(f"{k}={s}")
    with p.open("a", encoding="utf-8") as fh:
        fh.write(" ".join(parts) + "\n")


def parse_log(path: str | Path) -> list[dict[str, str]]:
    """Parse a run.log file back into a list of event dicts."""
    events: list[dict[str, str]] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or " " not in line:
            continue
        ts, _, rest = line.partition(" ")
        event: dict[str, str] = {"timestamp": ts}
        for token in _tokenise(rest):
            if "=" in token:
                k, _, v = token.partition("=")
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1].replace('\\"', '"')
                event[k] = v
        events.append(event)
    return events


def _tokenise(s: str) -> list[str]:
    """Split a log payload, respecting double-quoted values."""
    out: list[str] = []
    buf: list[str] = []
    in_quote = False
    for ch in s:
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
        elif ch == " " and not in_quote:
            if buf:
                out.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: run_log.py <log-path> [key=value ...]", file=sys.stderr)
        sys.exit(2)
    kwargs: dict[str, Any] = {}
    for arg in sys.argv[2:]:
        if "=" in arg:
            k, _, v = arg.partition("=")
            kwargs[k] = v
    append_event(sys.argv[1], **kwargs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_run_log.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/run_log.py .claude/skills/subreddit-content/tests/test_run_log.py
git commit -m "feat(subreddit-content): add run_log helper"
```

---

### Task 3: `input_parser.py` — parse invocation args + mix

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/input_parser.py`
- Test: `.claude/skills/subreddit-content/tests/test_input_parser.py`

**Interfaces:**
- Consumes: `slugify` from `slug`.
- Produces:
  - `default_mix(count: int) -> dict[str, int]` — split `count` at ratio 7:5:3 into `{"media","text","news"}`, summing exactly to `count`.
  - `parse_mix(spec: str) -> dict[str, int]` — parse `"media=7,text=5,news=3"`; raises `InputError` on unknown keys/non-ints.
  - `parse_invocation(argv: list[str]) -> dict` — returns config dict with keys `subreddit_url`, `subreddit_name`, `subreddit_slug`, `niche`, `count`, `mix` (dict), `days`, `auto`. Raises `InputError` on bad URL / empty niche / out-of-range numbers.
  - `InputError(ValueError)`.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_input_parser.py`:
```python
"""Tests for input_parser — invocation args, flags, and mix parsing."""
import pytest

from input_parser import (
    parse_invocation,
    parse_mix,
    default_mix,
    InputError,
)


def test_default_mix_15_is_7_5_3():
    assert default_mix(15) == {"media": 7, "text": 5, "news": 3}


def test_default_mix_sums_to_count():
    for n in (5, 10, 12, 20, 21):
        m = default_mix(n)
        assert sum(m.values()) == n


def test_parse_mix_basic():
    assert parse_mix("media=10,text=3,news=2") == {"media": 10, "text": 3, "news": 2}


def test_parse_mix_rejects_unknown_key():
    with pytest.raises(InputError):
        parse_mix("video=10,text=3")


def test_parse_invocation_minimal():
    cfg = parse_invocation(["https://www.reddit.com/r/BackyardChickens/", "backyard chickens"])
    assert cfg["subreddit_name"] == "BackyardChickens"
    assert cfg["subreddit_slug"] == "backyardchickens"
    assert cfg["niche"] == "backyard chickens"
    assert cfg["count"] == 15
    assert cfg["mix"] == {"media": 7, "text": 5, "news": 3}
    assert cfg["days"] == 30
    assert cfg["auto"] is False


def test_parse_invocation_flags():
    cfg = parse_invocation([
        "reddit.com/r/foo", "some niche",
        "--count", "10", "--mix", "media=6,text=2,news=2",
        "--days", "7", "--auto",
    ])
    assert cfg["count"] == 10
    assert cfg["mix"] == {"media": 6, "text": 2, "news": 2}
    assert cfg["days"] == 7
    assert cfg["auto"] is True


def test_mix_overrides_count_when_both_given_mismatch():
    # explicit --mix wins; count is set to the mix sum
    cfg = parse_invocation(["reddit.com/r/foo", "n", "--count", "99", "--mix", "media=6,text=2,news=2"])
    assert cfg["count"] == 10


def test_bad_subreddit_url_raises():
    with pytest.raises(InputError):
        parse_invocation(["https://example.com/foo", "niche"])


def test_empty_niche_raises():
    with pytest.raises(InputError):
        parse_invocation(["reddit.com/r/foo", "   "])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_input_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'input_parser'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/input_parser.py`:
```python
"""Parse the /subreddit-content invocation into a validated config dict."""
from __future__ import annotations

import re
from typing import Any

from slug import slugify

BUCKETS = ("media", "text", "news")
DEFAULT_COUNT = 15
DEFAULT_DAYS = 30
COUNT_MIN, COUNT_MAX = 1, 50
DAYS_MIN, DAYS_MAX = 1, 90
_MIX_RATIO = {"media": 7, "text": 5, "news": 3}  # sums to 15

_SUBREDDIT_RE = re.compile(r"reddit\.com/r/(?P<name>[A-Za-z0-9_]+)", re.IGNORECASE)


class InputError(ValueError):
    """Raised on any invalid invocation argument."""


def default_mix(count: int) -> dict[str, int]:
    """Split *count* across buckets at the 7:5:3 ratio, summing to count."""
    total = sum(_MIX_RATIO.values())
    out = {k: (count * v) // total for k, v in _MIX_RATIO.items()}
    # distribute the remainder to media, then text, then news
    remainder = count - sum(out.values())
    for k in BUCKETS:
        if remainder <= 0:
            break
        out[k] += 1
        remainder -= 1
    return out


def parse_mix(spec: str) -> dict[str, int]:
    """Parse ``media=7,text=5,news=3`` into a bucket->int dict."""
    out: dict[str, int] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise InputError(f"bad mix segment {part!r}")
        k, _, v = part.partition("=")
        k = k.strip().lower()
        if k not in BUCKETS:
            raise InputError(f"unknown mix bucket {k!r}; allowed: {BUCKETS}")
        try:
            out[k] = int(v)
        except ValueError:
            raise InputError(f"mix value for {k!r} is not an int: {v!r}")
    for k in BUCKETS:
        out.setdefault(k, 0)
    if sum(out.values()) <= 0:
        raise InputError("mix sums to zero")
    return out


def parse_invocation(argv: list[str]) -> dict[str, Any]:
    """Parse positional URL + niche and optional flags into a config dict."""
    positional: list[str] = []
    count = None
    mix = None
    days = DEFAULT_DAYS
    auto = False

    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--count":
            count = _int_flag(argv, i, "--count")
            i += 2
        elif tok == "--mix":
            mix = parse_mix(_str_flag(argv, i, "--mix"))
            i += 2
        elif tok == "--days":
            days = _int_flag(argv, i, "--days")
            i += 2
        elif tok == "--auto":
            auto = True
            i += 1
        elif tok.startswith("--"):
            raise InputError(f"unknown flag {tok!r}")
        else:
            positional.append(tok)
            i += 1

    if len(positional) < 2:
        raise InputError("usage: <subreddit-url> <niche> [flags]")
    url, niche = positional[0], positional[1]

    m = _SUBREDDIT_RE.search(url)
    if not m:
        raise InputError(f"not a valid subreddit URL: {url!r}")
    name = m.group("name")

    if not niche.strip():
        raise InputError("niche must be non-empty")

    if mix is not None:
        count = sum(mix.values())
    if count is None:
        count = DEFAULT_COUNT
    if not (COUNT_MIN <= count <= COUNT_MAX):
        raise InputError(f"count {count} out of range [{COUNT_MIN},{COUNT_MAX}]")
    if mix is None:
        mix = default_mix(count)
    if not (DAYS_MIN <= days <= DAYS_MAX):
        raise InputError(f"days {days} out of range [{DAYS_MIN},{DAYS_MAX}]")

    return {
        "subreddit_url": url,
        "subreddit_name": name,
        "subreddit_slug": slugify(name),
        "niche": niche.strip(),
        "count": count,
        "mix": mix,
        "days": days,
        "auto": auto,
    }


def _int_flag(argv: list[str], i: int, name: str) -> int:
    if i + 1 >= len(argv):
        raise InputError(f"{name} requires a value")
    try:
        return int(argv[i + 1])
    except ValueError:
        raise InputError(f"{name} value not an int: {argv[i + 1]!r}")


def _str_flag(argv: list[str], i: int, name: str) -> str:
    if i + 1 >= len(argv):
        raise InputError(f"{name} requires a value")
    return argv[i + 1]


if __name__ == "__main__":
    import json
    import sys
    try:
        print(json.dumps(parse_invocation(sys.argv[1:]), indent=2))
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_input_parser.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/input_parser.py .claude/skills/subreddit-content/tests/test_input_parser.py
git commit -m "feat(subreddit-content): add invocation + mix parser"
```

---

### Task 4: `history.py` — weekly dedup log

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/history.py`
- Test: `.claude/skills/subreddit-content/tests/test_history.py`

**Interfaces:**
- Produces:
  - `normalize_url(url: str) -> str` — lowercase host, drop scheme/`www.`/query/fragment/trailing slash.
  - `load_used(path) -> set[str]` — set of normalized URLs from a `.jsonl` history file (missing file → empty set).
  - `filter_unused(candidates: list[dict], used: set[str]) -> list[dict]` — keep candidates whose `url` normalizes to something not in `used`.
  - `append_used(path, items: list[dict], run_folder: str, date_used: str) -> None` — append one JSON line per item with keys `url`, `title`, `date_used`, `run_folder`.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_history.py`:
```python
"""Tests for history — URL normalization, load, filter, append."""
import json

from history import normalize_url, load_used, filter_unused, append_used


def test_normalize_strips_scheme_www_query_fragment():
    a = normalize_url("https://www.tiktok.com/@x/video/1?foo=bar#frag")
    b = normalize_url("http://tiktok.com/@x/video/1")
    assert a == b


def test_normalize_strips_trailing_slash():
    assert normalize_url("https://youtube.com/shorts/ab/") == normalize_url("https://youtube.com/shorts/ab")


def test_load_missing_file_is_empty(tmp_path):
    assert load_used(tmp_path / "nope.jsonl") == set()


def test_append_then_load_round_trip(tmp_path):
    p = tmp_path / "r-foo.jsonl"
    append_used(p, [{"url": "https://tiktok.com/@x/video/1", "title": "T"}],
                run_folder="foo-2026-07-02", date_used="2026-07-02")
    used = load_used(p)
    assert normalize_url("https://www.tiktok.com/@x/video/1?utm=1") in used


def test_filter_unused_drops_seen(tmp_path):
    p = tmp_path / "r-foo.jsonl"
    append_used(p, [{"url": "https://youtube.com/shorts/aaa", "title": "A"}],
                run_folder="f", date_used="2026-07-02")
    used = load_used(p)
    cands = [
        {"url": "https://www.youtube.com/shorts/aaa?si=1", "title": "dup"},
        {"url": "https://www.youtube.com/shorts/bbb", "title": "fresh"},
    ]
    kept = filter_unused(cands, used)
    assert len(kept) == 1
    assert kept[0]["title"] == "fresh"


def test_append_writes_all_required_keys(tmp_path):
    p = tmp_path / "r-foo.jsonl"
    append_used(p, [{"url": "https://x.com/1", "title": "T"}],
                run_folder="rf", date_used="2026-07-02")
    rec = json.loads(p.read_text().strip())
    assert set(rec) == {"url", "title", "date_used", "run_folder"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_history.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'history'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/history.py`:
```python
"""Per-subreddit dedup history — normalize URLs, load/filter/append."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit


def normalize_url(url: str) -> str:
    """Canonical form for dedup: lowercase host without ``www.``, path with no
    trailing slash, no query, no fragment, no scheme."""
    s = urlsplit(url.strip())
    host = (s.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = s.path.rstrip("/")
    if not host and path:
        # url given without scheme, e.g. "tiktok.com/x" -> parsed as path
        raw = url.strip().lower()
        raw = raw.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        if raw.startswith("www."):
            raw = raw[4:]
        return raw
    return f"{host}{path}"


def load_used(path: str | Path) -> set[str]:
    """Return the set of normalized URLs recorded in a history .jsonl file."""
    p = Path(path)
    if not p.exists():
        return set()
    used: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "url" in rec:
            used.add(normalize_url(rec["url"]))
    return used


def filter_unused(candidates: list[dict], used: set[str]) -> list[dict]:
    """Keep only candidates whose normalized ``url`` is not in *used*."""
    out: list[dict] = []
    for c in candidates:
        if normalize_url(c.get("url", "")) not in used:
            out.append(c)
    return out


def append_used(path: str | Path, items: list[dict], *, run_folder: str, date_used: str) -> None:
    """Append one JSON line per item with url/title/date_used/run_folder."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for it in items:
            rec = {
                "url": it.get("url", ""),
                "title": it.get("title", ""),
                "date_used": date_used,
                "run_folder": run_folder,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_history.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/history.py .claude/skills/subreddit-content/tests/test_history.py
git commit -m "feat(subreddit-content): add dedup history helper"
```

---

### Task 5: `scoring.py` — candidate scoring

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/scoring.py`
- Test: `.claude/skills/subreddit-content/tests/test_scoring.py`

**Interfaces:**
- Consumes: candidate dicts with `engagement` (int/float, raw count), `date` (ISO `YYYY-MM-DD`), `relevance` (0..1, Claude-supplied), `hook` (0..1, Claude-supplied).
- Produces:
  - `WEIGHTS = {"engagement":0.35,"freshness":0.20,"relevance":0.30,"hook":0.15}`.
  - `score_candidate(cand: dict, *, today: date, days: int) -> float` — returns a 0..100 score.
  - `score_all(cands: list[dict], *, today: date, days: int) -> list[dict]` — returns candidates with a `score` key added, sorted score-desc.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_scoring.py`:
```python
"""Tests for scoring — component weighting, freshness decay, bounds."""
from datetime import date

from scoring import score_candidate, score_all, WEIGHTS


TODAY = date(2026, 7, 2)


def _cand(**kw):
    base = {"engagement": 0, "date": "2026-07-02", "relevance": 0.0, "hook": 0.0}
    base.update(kw)
    return base


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_score_in_bounds():
    s = score_candidate(_cand(engagement=1_000_000, relevance=1.0, hook=1.0),
                         today=TODAY, days=30)
    assert 0.0 <= s <= 100.0


def test_all_zero_is_zero():
    s = score_candidate(_cand(engagement=0, date="2026-07-02", relevance=0.0, hook=0.0),
                        today=TODAY, days=30)
    # freshness of a same-day post is 1.0, weighted 0.20 -> 20
    assert abs(s - 20.0) < 1e-6


def test_fresher_scores_higher():
    fresh = score_candidate(_cand(date="2026-07-01"), today=TODAY, days=30)
    stale = score_candidate(_cand(date="2026-06-05"), today=TODAY, days=30)
    assert fresh > stale


def test_older_than_window_freshness_floored_at_zero():
    s = score_candidate(_cand(date="2026-01-01"), today=TODAY, days=30)
    assert abs(s - 0.0) < 1e-6


def test_score_all_sorts_desc_and_adds_key():
    cands = [_cand(relevance=0.1), _cand(relevance=0.9)]
    out = score_all(cands, today=TODAY, days=30)
    assert "score" in out[0]
    assert out[0]["score"] >= out[1]["score"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scoring'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/scoring.py`:
```python
"""Score discovery candidates 0..100 for shortlisting."""
from __future__ import annotations

import math
from datetime import date

WEIGHTS = {
    "engagement": 0.35,
    "freshness": 0.20,
    "relevance": 0.30,
    "hook": 0.15,
}

# log10(1 + engagement) / _ENGAGEMENT_LOG_REF, clamped to [0,1].
# _ENGAGEMENT_LOG_REF = 6 means ~1,000,000 engagements maps to ~1.0.
_ENGAGEMENT_LOG_REF = 6.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _engagement_norm(raw: float) -> float:
    if raw <= 0:
        return 0.0
    return _clamp01(math.log10(1.0 + raw) / _ENGAGEMENT_LOG_REF)


def _freshness(cand_date: str, today: date, days: int) -> float:
    try:
        d = date.fromisoformat(cand_date)
    except (ValueError, TypeError):
        return 0.0
    age = (today - d).days
    if age < 0:
        age = 0
    return _clamp01(1.0 - age / days)


def score_candidate(cand: dict, *, today: date, days: int) -> float:
    """Return a 0..100 weighted score for a single candidate."""
    eng = _engagement_norm(float(cand.get("engagement", 0) or 0))
    fresh = _freshness(str(cand.get("date", "")), today, days)
    rel = _clamp01(float(cand.get("relevance", 0.0) or 0.0))
    hook = _clamp01(float(cand.get("hook", 0.0) or 0.0))
    total = (
        WEIGHTS["engagement"] * eng
        + WEIGHTS["freshness"] * fresh
        + WEIGHTS["relevance"] * rel
        + WEIGHTS["hook"] * hook
    )
    return round(total * 100.0, 4)


def score_all(cands: list[dict], *, today: date, days: int) -> list[dict]:
    """Return candidates with a ``score`` key, sorted highest first."""
    out = []
    for c in cands:
        cc = dict(c)
        cc["score"] = score_candidate(c, today=today, days=days)
        out.append(cc)
    out.sort(key=lambda c: c["score"], reverse=True)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_scoring.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/scoring.py .claude/skills/subreddit-content/tests/test_scoring.py
git commit -m "feat(subreddit-content): add candidate scoring"
```

---

### Task 6: `shortlist.py` — bucket-fill to the mix

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/shortlist.py`
- Test: `.claude/skills/subreddit-content/tests/test_shortlist.py`

**Interfaces:**
- Consumes: scored candidate dicts, each with a `post_type` in `{"video","image","text","link"}` and a `score`.
- Produces:
  - `bucket_of(post_type: str) -> str` — maps `video`/`image` → `"media"`, `text` → `"text"`, `link` → `"news"`.
  - `build_shortlist(scored: list[dict], mix: dict[str,int], count: int) -> list[dict]` — pick per-bucket by score to hit `mix`, backfill from any remaining highest-scored candidates to reach `count`, then assign 1-based `post_number` in final score-desc order.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_shortlist.py`:
```python
"""Tests for shortlist — bucket-fill to mix, backfill, numbering."""
from shortlist import build_shortlist, bucket_of


def _c(pt, score, i):
    return {"post_type": pt, "score": score, "title": f"{pt}-{i}", "url": f"u{pt}{i}"}


def test_bucket_of_mapping():
    assert bucket_of("video") == "media"
    assert bucket_of("image") == "media"
    assert bucket_of("text") == "text"
    assert bucket_of("link") == "news"


def test_hits_mix_when_enough_supply():
    scored = (
        [_c("video", 90 - i, i) for i in range(10)]
        + [_c("text", 80 - i, i) for i in range(10)]
        + [_c("link", 70 - i, i) for i in range(10)]
    )
    out = build_shortlist(scored, {"media": 7, "text": 5, "news": 3}, 15)
    counts = {"media": 0, "text": 0, "news": 0}
    for p in out:
        counts[bucket_of(p["post_type"])] += 1
    assert counts == {"media": 7, "text": 5, "news": 3}
    assert len(out) == 15


def test_backfills_when_a_bucket_is_short():
    # only 2 text available though mix wants 5 -> backfill from media/news
    scored = (
        [_c("video", 90 - i, i) for i in range(20)]
        + [_c("text", 50 - i, i) for i in range(2)]
        + [_c("link", 40 - i, i) for i in range(10)]
    )
    out = build_shortlist(scored, {"media": 7, "text": 5, "news": 3}, 15)
    assert len(out) == 15


def test_post_numbers_are_sequential_from_one():
    scored = [_c("video", 90 - i, i) for i in range(15)]
    out = build_shortlist(scored, {"media": 15, "text": 0, "news": 0}, 15)
    assert [p["post_number"] for p in out] == list(range(1, 16))


def test_never_exceeds_available_supply():
    scored = [_c("video", 90, 0), _c("text", 80, 0)]
    out = build_shortlist(scored, {"media": 7, "text": 5, "news": 3}, 15)
    assert len(out) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_shortlist.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shortlist'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/shortlist.py`:
```python
"""Bucket-fill scored candidates to hit the target mix, then number them."""
from __future__ import annotations

_BUCKET_MAP = {"video": "media", "image": "media", "text": "text", "link": "news"}


def bucket_of(post_type: str) -> str:
    """Map a post_type to its mix bucket (media / text / news)."""
    return _BUCKET_MAP.get(post_type, "news")


def build_shortlist(scored: list[dict], mix: dict[str, int], count: int) -> list[dict]:
    """Select up to *count* candidates hitting *mix* per bucket where supply
    allows, backfilling from remaining highest-scored candidates. Adds a
    1-based ``post_number`` in final score-desc order."""
    by_bucket: dict[str, list[dict]] = {"media": [], "text": [], "news": []}
    for c in scored:
        by_bucket[bucket_of(c.get("post_type", "link"))].append(c)
    for b in by_bucket.values():
        b.sort(key=lambda c: c.get("score", 0), reverse=True)

    chosen: list[dict] = []
    chosen_ids: set[int] = set()

    # first pass: satisfy the per-bucket quota
    for bucket, quota in mix.items():
        for c in by_bucket.get(bucket, [])[:quota]:
            chosen.append(c)
            chosen_ids.add(id(c))

    # backfill to reach count from all remaining, highest score first
    if len(chosen) < count:
        remaining = [c for c in sorted(scored, key=lambda c: c.get("score", 0), reverse=True)
                     if id(c) not in chosen_ids]
        for c in remaining:
            if len(chosen) >= count:
                break
            chosen.append(c)
            chosen_ids.add(id(c))

    chosen.sort(key=lambda c: c.get("score", 0), reverse=True)
    out = []
    for n, c in enumerate(chosen[:count], start=1):
        cc = dict(c)
        cc["post_number"] = n
        out.append(cc)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_shortlist.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/shortlist.py .claude/skills/subreddit-content/tests/test_shortlist.py
git commit -m "feat(subreddit-content): add mix bucket-fill shortlist"
```

---

### Task 7: `media_validate.py` — Reddit file-limit enforcement

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/media_validate.py`
- Test: `.claude/skills/subreddit-content/tests/test_media_validate.py`

**Interfaces:**
- Produces:
  - Constants `VIDEO_MAX_BYTES = 1073741824`, `VIDEO_MAX_SECONDS = 900`, `IMAGE_MAX_BYTES = 20971520`.
  - `validate_media(path, post_type: str, *, duration: float | None = None) -> dict` — returns `{"status": "ok"|"media_failed", "reason": str}`. `media_failed` when: file missing, size 0, over the size limit for its type, or (video) over the duration limit.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_media_validate.py`:
```python
"""Tests for media_validate — presence, size, duration limits."""
from media_validate import (
    validate_media,
    VIDEO_MAX_BYTES,
    IMAGE_MAX_BYTES,
    VIDEO_MAX_SECONDS,
)


def _make(tmp_path, name, nbytes):
    p = tmp_path / name
    p.write_bytes(b"\0" * nbytes)
    return p


def test_missing_file_fails(tmp_path):
    r = validate_media(tmp_path / "nope.mp4", "video")
    assert r["status"] == "media_failed"


def test_zero_byte_fails(tmp_path):
    p = _make(tmp_path, "z.jpg", 0)
    assert validate_media(p, "image")["status"] == "media_failed"


def test_small_image_ok(tmp_path):
    p = _make(tmp_path, "ok.jpg", 1024)
    assert validate_media(p, "image")["status"] == "ok"


def test_oversize_image_fails(tmp_path):
    p = _make(tmp_path, "big.jpg", IMAGE_MAX_BYTES + 1)
    assert validate_media(p, "image")["status"] == "media_failed"


def test_video_duration_over_limit_fails(tmp_path):
    p = _make(tmp_path, "v.mp4", 2048)
    r = validate_media(p, "video", duration=VIDEO_MAX_SECONDS + 1)
    assert r["status"] == "media_failed"


def test_video_within_limits_ok(tmp_path):
    p = _make(tmp_path, "v.mp4", 2048)
    r = validate_media(p, "video", duration=120)
    assert r["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_media_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'media_validate'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/media_validate.py`:
```python
"""Validate a downloaded media file against Reddit's native-upload limits."""
from __future__ import annotations

from pathlib import Path

VIDEO_MAX_BYTES = 1073741824   # 1 GB
VIDEO_MAX_SECONDS = 900        # 15 min
IMAGE_MAX_BYTES = 20971520     # 20 MB

_VIDEO_TYPES = {"video"}
_IMAGE_TYPES = {"image"}


def validate_media(path, post_type: str, *, duration: float | None = None) -> dict:
    """Return {"status","reason"}; status is "ok" or "media_failed"."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {"status": "media_failed", "reason": f"file not found: {p}"}
    size = p.stat().st_size
    if size <= 0:
        return {"status": "media_failed", "reason": "zero-byte file"}

    if post_type in _VIDEO_TYPES:
        if size > VIDEO_MAX_BYTES:
            return {"status": "media_failed", "reason": f"video {size}B > {VIDEO_MAX_BYTES}B limit"}
        if duration is not None and duration > VIDEO_MAX_SECONDS:
            return {"status": "media_failed", "reason": f"video {duration}s > {VIDEO_MAX_SECONDS}s limit"}
        return {"status": "ok", "reason": ""}

    if post_type in _IMAGE_TYPES:
        if size > IMAGE_MAX_BYTES:
            return {"status": "media_failed", "reason": f"image {size}B > {IMAGE_MAX_BYTES}B limit"}
        return {"status": "ok", "reason": ""}

    return {"status": "media_failed", "reason": f"unexpected post_type for media: {post_type!r}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_media_validate.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/media_validate.py .claude/skills/subreddit-content/tests/test_media_validate.py
git commit -m "feat(subreddit-content): add media limit validation"
```

---

### Task 8: `post_schema.py` — post dict validation

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/post_schema.py`
- Test: `.claude/skills/subreddit-content/tests/test_post_schema.py`

**Interfaces:**
- Produces:
  - `TITLE_MAX = 300`, `POST_TYPES = {"video","image","text","link"}`, `STATUSES = {"ready","media_failed","needs_review"}`, `REQUIRED_KEYS` (the front-matter keys).
  - `validate_post(post: dict, *, allowed_flairs: list[str] | None = None) -> list[str]` — returns a list of human-readable error strings; empty means valid.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_post_schema.py`:
```python
"""Tests for post_schema.validate_post."""
from post_schema import validate_post, TITLE_MAX


def _post(**kw):
    base = {
        "post_number": 1,
        "post_type": "text",
        "title": "A fine title",
        "suggested_flair": "",
        "nsfw": False,
        "source_platform": "youtube",
        "source_url": "https://youtube.com/x",
        "attribution": "@x (YouTube)",
        "media_file": "",
        "engagement_note": "1k likes",
        "status": "ready",
        "body": "Some body text.",
    }
    base.update(kw)
    return base


def test_valid_post_has_no_errors():
    assert validate_post(_post()) == []


def test_missing_required_key_flagged():
    p = _post()
    del p["title"]
    errs = validate_post(p)
    assert any("title" in e for e in errs)


def test_title_too_long_flagged():
    errs = validate_post(_post(title="x" * (TITLE_MAX + 1)))
    assert any("title" in e.lower() for e in errs)


def test_bad_post_type_flagged():
    errs = validate_post(_post(post_type="carousel"))
    assert any("post_type" in e for e in errs)


def test_media_type_requires_media_file():
    errs = validate_post(_post(post_type="video", media_file=""))
    assert any("media_file" in e for e in errs)


def test_media_failed_status_allows_empty_media_file():
    errs = validate_post(_post(post_type="video", media_file="", status="media_failed"))
    assert errs == []


def test_flair_not_in_allowed_list_flagged():
    errs = validate_post(_post(suggested_flair="Ghost"), allowed_flairs=["Funny", "News"])
    assert any("flair" in e.lower() for e in errs)


def test_empty_flair_always_allowed():
    assert validate_post(_post(suggested_flair=""), allowed_flairs=["Funny"]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_post_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'post_schema'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/post_schema.py`:
```python
"""Validate an assembled post dict against the deliverable schema."""
from __future__ import annotations

TITLE_MAX = 300
POST_TYPES = {"video", "image", "text", "link"}
MEDIA_TYPES = {"video", "image"}
STATUSES = {"ready", "media_failed", "needs_review"}
REQUIRED_KEYS = (
    "post_number", "post_type", "title", "suggested_flair", "nsfw",
    "source_platform", "source_url", "attribution", "media_file",
    "engagement_note", "status", "body",
)


def validate_post(post: dict, *, allowed_flairs: list[str] | None = None) -> list[str]:
    """Return a list of error strings (empty == valid)."""
    errors: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in post:
            errors.append(f"missing required key: {key}")
    if errors:
        return errors  # can't validate values reliably with keys missing

    title = post["title"]
    if not isinstance(title, str) or not title.strip():
        errors.append("title must be a non-empty string")
    elif len(title) > TITLE_MAX:
        errors.append(f"title length {len(title)} exceeds {TITLE_MAX}")

    pt = post["post_type"]
    if pt not in POST_TYPES:
        errors.append(f"post_type {pt!r} not in {sorted(POST_TYPES)}")

    if post["status"] not in STATUSES:
        errors.append(f"status {post['status']!r} not in {sorted(STATUSES)}")

    if not isinstance(post["nsfw"], bool):
        errors.append("nsfw must be a bool")

    if pt in MEDIA_TYPES and not post["media_file"] and post["status"] != "media_failed":
        errors.append("media_file required for media posts unless status is media_failed")

    flair = post["suggested_flair"]
    if flair and allowed_flairs is not None and flair not in allowed_flairs:
        errors.append(f"suggested_flair {flair!r} not in sub flair list {allowed_flairs}")

    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_post_schema.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/post_schema.py .claude/skills/subreddit-content/tests/test_post_schema.py
git commit -m "feat(subreddit-content): add post schema validation"
```

---

### Task 9: `assemble.py` — write the deliverable tree

**Files:**
- Create: `.claude/skills/subreddit-content/scripts/assemble.py`
- Test: `.claude/skills/subreddit-content/tests/test_assemble.py`

**Interfaces:**
- Consumes: `slugify` from `slug`; `validate_post` from `post_schema`.
- Produces:
  - `run_folder_name(niche: str, subreddit_name: str, run_date: date) -> str` → `"<niche-slug>-r-<sub-slug>-<YYYY-MM-DD>"`.
  - `render_post_md(post: dict) -> str` — front-matter block (keys in `post_schema.REQUIRED_KEYS` order except `body`) + blank line + body.
  - `write_post(run_dir, post: dict, *, allowed_flairs=None) -> Path` — validates (raises `AssembleError` on schema errors), makes `post-NN/`, writes `post.md`; returns the post dir.
  - `write_run_summary(run_dir, summary_md: str) -> Path` — writes `RUN-SUMMARY.md`.
  - `AssembleError(ValueError)`.

- [ ] **Step 1: Write the failing test**

`.claude/skills/subreddit-content/tests/test_assemble.py`:
```python
"""Tests for assemble — folder naming, post.md rendering, tree writing."""
from datetime import date

import pytest

from assemble import (
    run_folder_name,
    render_post_md,
    write_post,
    write_run_summary,
    AssembleError,
)


def _post(**kw):
    base = {
        "post_number": 3,
        "post_type": "text",
        "title": "Hello",
        "suggested_flair": "",
        "nsfw": False,
        "source_platform": "youtube",
        "source_url": "https://youtube.com/x",
        "attribution": "@x (YouTube)",
        "media_file": "",
        "engagement_note": "1k",
        "status": "ready",
        "body": "Body line one.\nBody line two.",
    }
    base.update(kw)
    return base


def test_run_folder_name_format():
    n = run_folder_name("Backyard Chickens", "BackyardChickens", date(2026, 7, 2))
    assert n == "backyard-chickens-r-backyardchickens-2026-07-02"


def test_render_has_frontmatter_and_body():
    md = render_post_md(_post())
    assert md.startswith("---\n")
    assert "title: \"Hello\"" in md
    assert md.strip().endswith("Body line two.")


def test_write_post_creates_zero_padded_folder(tmp_path):
    d = write_post(tmp_path, _post(post_number=3))
    assert d.name == "post-03"
    assert (d / "post.md").exists()


def test_write_post_rejects_invalid(tmp_path):
    with pytest.raises(AssembleError):
        write_post(tmp_path, _post(title="x" * 400))


def test_write_run_summary(tmp_path):
    p = write_run_summary(tmp_path, "# Summary\nok")
    assert p.name == "RUN-SUMMARY.md"
    assert "Summary" in p.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_assemble.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'assemble'`.

- [ ] **Step 3: Write minimal implementation**

`.claude/skills/subreddit-content/scripts/assemble.py`:
```python
"""Assemble the per-post deliverable tree: run folder, post-NN/, post.md."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from slug import slugify
from post_schema import validate_post, REQUIRED_KEYS

# front-matter key order = REQUIRED_KEYS minus the free-text body
_FRONTMATTER_KEYS = tuple(k for k in REQUIRED_KEYS if k != "body")
# keys whose values are rendered quoted (may contain spaces/colons)
_QUOTED = {"title", "suggested_flair", "attribution", "engagement_note"}


class AssembleError(ValueError):
    """Raised when a post fails schema validation before writing."""


def run_folder_name(niche: str, subreddit_name: str, run_date: date) -> str:
    """Return ``<niche-slug>-r-<sub-slug>-<YYYY-MM-DD>``."""
    return f"{slugify(niche)}-r-{slugify(subreddit_name)}-{run_date.isoformat()}"


def render_post_md(post: dict) -> str:
    """Render YAML-ish front-matter + body for a single post."""
    lines = ["---"]
    for key in _FRONTMATTER_KEYS:
        val = post.get(key, "")
        if isinstance(val, bool):
            rendered = "true" if val else "false"
        elif key in _QUOTED:
            rendered = '"' + str(val).replace('"', '\\"') + '"'
        else:
            rendered = str(val)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    lines.append("")
    lines.append(post.get("body", ""))
    return "\n".join(lines) + "\n"


def write_post(run_dir, post: dict, *, allowed_flairs=None) -> Path:
    """Validate then write ``post-NN/post.md`` under *run_dir*; return post dir."""
    errs = validate_post(post, allowed_flairs=allowed_flairs)
    if errs:
        raise AssembleError(f"post {post.get('post_number')}: " + "; ".join(errs))
    n = int(post["post_number"])
    post_dir = Path(run_dir) / f"post-{n:02d}"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "post.md").write_text(render_post_md(post), encoding="utf-8")
    return post_dir


def write_run_summary(run_dir, summary_md: str) -> Path:
    """Write RUN-SUMMARY.md under *run_dir*; return its path."""
    p = Path(run_dir) / "RUN-SUMMARY.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(summary_md, encoding="utf-8")
    return p
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest tests/test_assemble.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the whole suite to confirm no cross-helper breakage**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest -v`
Expected: PASS (all tasks 1–9 green).

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/subreddit-content/scripts/assemble.py .claude/skills/subreddit-content/tests/test_assemble.py
git commit -m "feat(subreddit-content): add deliverable tree assembler"
```

---

### Task 10: Templates — `post-template.md` + `run-summary-template.md`

**Files:**
- Create: `.claude/skills/subreddit-content/templates/post-template.md`
- Create: `.claude/skills/subreddit-content/templates/run-summary-template.md`

These are Claude-facing reference templates for drafting (the front-matter must match `post_schema.REQUIRED_KEYS`). No code, no test — a `grep` check guards the key set.

- [ ] **Step 1: Write `post-template.md`**

`.claude/skills/subreddit-content/templates/post-template.md`:
```markdown
---
post_number: <int, 1-based>
post_type: <video | image | text | link>
title: "<Reddit title, <=300 chars>"
suggested_flair: "<one of the sub's real flairs, or empty>"
nsfw: <true | false>
source_platform: <youtube | tiktok | instagram | pinterest | news | web>
source_url: <direct URL to the original content>
attribution: "<creator handle (Platform)>"
media_file: <filename in this folder, or empty for text/link>
engagement_note: "<e.g. 1.2M likes, posted 4 days ago>"
status: <ready | media_failed | needs_review>
---

<Post body pasted into Reddit.
- media/link posts: 2-4 sentence framing/caption, then a credit line.
- text posts: the full discussion prompt.>
```

- [ ] **Step 2: Write `run-summary-template.md`**

`.claude/skills/subreddit-content/templates/run-summary-template.md`:
```markdown
# Run summary — r/<sub> (<niche>) — <YYYY-MM-DD>

**Run folder:** <folder name>
**Requested:** <count> posts | mix media=<m> text=<t> news=<n> | window <days>d

## Delivered
- Media posts:   <n> (<n ok> with file, <n> media_failed → link-post fallback)
- Text posts:    <n>
- News/link:     <n>
- **Total:**     <n>

## Sources (vet before scheduling)
| # | type | platform | attribution | source_url | status |
|---|------|----------|-------------|------------|--------|
| 01 | video | tiktok | @creator (TikTok) | https://... | ready |

## Skipped / failed
- <url> — <reason (already in history / download failed / oversize)>

## Notes
- <partial platform outages, fallbacks used, anything the operator should know>
```

- [ ] **Step 3: Verify template keys match the schema**

Run:
```bash
cd .claude/skills/subreddit-content && python3 -c "
from pathlib import Path
import re, sys
sys.path.insert(0, 'scripts')
from post_schema import REQUIRED_KEYS
tpl = Path('templates/post-template.md').read_text()
missing = [k for k in REQUIRED_KEYS if k != 'body' and not re.search(rf'(?m)^{k}:', tpl)]
print('MISSING:', missing)
assert not missing, missing
print('template OK')
"
```
Expected: `template OK`.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/subreddit-content/templates/
git commit -m "docs(subreddit-content): add post + run-summary templates"
```

---

### Task 11: `SKILL.md` — orchestrator

**Files:**
- Create: `.claude/skills/subreddit-content/SKILL.md`

Authored orchestration doc (Claude executes it). No unit test; a structure check guards required sections. It must direct Claude through the five phases, invoke helpers by absolute path, invoke the `last30days` and `video-downloader` skills, honor the review gate + `--auto`, and follow the error envelope.

- [ ] **Step 1: Write `SKILL.md`**

`.claude/skills/subreddit-content/SKILL.md`:
````markdown
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
5. Write `run-config.json` (the parsed config + resolved flair list + today's date) and log start:
   ```bash
   python3 ~/.claude/skills/subreddit-content/scripts/run_log.py run.log phase=intake event=ok sub=<slug> count=<count>
   ```
6. Announce: sub, niche, target count + mix, freshness window, how many history URLs will be skipped. Then start Phase 1.

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

1. Create the run folder `assemble.run_folder_name(niche, subreddit_name, today)` in CWD.
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
````

- [ ] **Step 2: Verify SKILL.md front-matter + required sections**

Run:
```bash
cd .claude/skills/subreddit-content && python3 -c "
from pathlib import Path
t = Path('SKILL.md').read_text()
assert t.startswith('---'), 'missing front-matter'
for s in ['name: subreddit-content', 'Phase 0', 'Phase 1', 'Phase 2', 'Phase 3', 'Phase 4', 'Error envelope', 'last30days', 'video-downloader']:
    assert s in t, f'missing: {s}'
print('SKILL.md OK')
"
```
Expected: `SKILL.md OK`.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/subreddit-content/SKILL.md
git commit -m "feat(subreddit-content): add orchestrator SKILL.md"
```

---

### Task 12: README + smoke-test doc + full-suite green

**Files:**
- Create: `.claude/skills/subreddit-content/README.md`
- Create: `.claude/skills/subreddit-content/docs/smoke-test-procedure.md`

- [ ] **Step 1: Write `README.md`**

`.claude/skills/subreddit-content/README.md`:
```markdown
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
```

- [ ] **Step 2: Write `docs/smoke-test-procedure.md`**

`.claude/skills/subreddit-content/docs/smoke-test-procedure.md`:
```markdown
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
```

- [ ] **Step 3: Run the full suite one final time**

Run: `cd .claude/skills/subreddit-content && python3 -m pytest -v`
Expected: PASS — every test from Tasks 1–9 green.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/subreddit-content/README.md .claude/skills/subreddit-content/docs/
git commit -m "docs(subreddit-content): add README + smoke-test procedure"
```

---

## Self-Review

**Spec coverage:**
- Native downloads + validation → Tasks 7 (limits), 11 Phase 3. ✓
- One subreddit per run → input_parser (single URL), SKILL boundary section. ✓
- Hybrid sourcing (last30days → media download → firecrawl fallback) → SKILL Phases 1 & 3. ✓
- Balanced mix default 7:5:3 + overridable → Task 3 (`default_mix`/`parse_mix`), Task 6 (bucket-fill). ✓
- History dedup → Task 4, SKILL Phases 0 & 4. ✓
- Per-post folder output + post.md schema → Tasks 8, 9, 10. ✓
- Review gate + `--auto` → SKILL Phase 2 + Run mode. ✓
- Error envelope, never auto-post → SKILL sections. ✓
- Attribution/source vetting → post_schema fields, run-summary template. ✓
- Reddit title/file limits → Global Constraints, Tasks 7 & 8. ✓
- Package mirrors reddit-research → Tasks 1, 12. ✓

**Placeholder scan:** No "TBD/TODO". The one `python3 - <<'PY'` block in SKILL.md Phase 2 is explicitly labelled *illustrative* and immediately followed by the concrete `score_all`/`build_shortlist` call names — acceptable in an orchestration doc (SKILL.md is Claude-executed prose, not a unit under test).

**Type consistency:** `post_type` set `{video,image,text,link}` consistent across `post_schema`, `shortlist.bucket_of`, `media_validate`, templates, SKILL. `mix` buckets `{media,text,news}` consistent across `input_parser`, `shortlist`, templates. `REQUIRED_KEYS` drives both `post_schema.validate_post` and `assemble` front-matter order + the Task-10 template grep. History record keys `{url,title,date_used,run_folder}` consistent Task 4 ↔ SKILL Phase 4.

No gaps found.
