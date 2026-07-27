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
_MIX_RATIO = {"media": 10, "text": 5, "news": 0}  # sums to 15
DEFAULT_MAX_QUERIES = 40
DEFAULT_MAX_ROUNDS = 3
MIN_IMAGES = 1
MIN_VIDEOS = 1
MAX_QUERIES_MIN, MAX_QUERIES_MAX = 1, 200
MAX_ROUNDS_MIN, MAX_ROUNDS_MAX = 1, 10

_SUBREDDIT_RE = re.compile(r"reddit\.com/r/(?P<name>[A-Za-z0-9_]+)", re.IGNORECASE)


class InputError(ValueError):
    """Raised on any invalid invocation argument."""


def default_mix(count: int) -> dict[str, int]:
    """Split *count* across buckets at the 10:5:0 ratio, summing to count."""
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
    for k in BUCKETS:
        if out[k] < 0:
            raise InputError(f"mix value for {k!r} must not be negative: {out[k]}")
    if sum(out.values()) <= 0:
        raise InputError("mix sums to zero")
    return out


def _parse_media_floor(spec: str) -> dict[str, int]:
    """Parse ``2,3`` into ``{"min_images": 2, "min_videos": 3}``."""
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 2:
        raise InputError(f"--media-floor expects 'images,videos', got {spec!r}")
    try:
        imgs, vids = int(parts[0]), int(parts[1])
    except ValueError:
        raise InputError(f"--media-floor values must be ints, got {spec!r}")
    if imgs < 0 or vids < 0:
        raise InputError(f"--media-floor values must be >= 0, got {spec!r}")
    return {"min_images": imgs, "min_videos": vids}


def parse_invocation(argv: list[str]) -> dict[str, Any]:
    """Parse positional URL + niche and optional flags into a config dict."""
    positional: list[str] = []
    count = None
    mix = None
    days = DEFAULT_DAYS
    auto = False
    seeds: list[str] = []
    max_queries = DEFAULT_MAX_QUERIES
    max_rounds = DEFAULT_MAX_ROUNDS
    media_floor = {"min_images": MIN_IMAGES, "min_videos": MIN_VIDEOS}

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
        elif tok == "--seeds":
            raw = _str_flag(argv, i, "--seeds")
            seeds = [s.strip() for s in raw.split(",") if s.strip()]
            i += 2
        elif tok == "--max-queries":
            max_queries = _int_flag(argv, i, "--max-queries")
            i += 2
        elif tok == "--max-rounds":
            max_rounds = _int_flag(argv, i, "--max-rounds")
            i += 2
        elif tok == "--media-floor":
            media_floor = _parse_media_floor(_str_flag(argv, i, "--media-floor"))
            i += 2
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
    if not (MAX_QUERIES_MIN <= max_queries <= MAX_QUERIES_MAX):
        raise InputError(f"max_queries {max_queries} out of range [{MAX_QUERIES_MIN},{MAX_QUERIES_MAX}]")
    if not (MAX_ROUNDS_MIN <= max_rounds <= MAX_ROUNDS_MAX):
        raise InputError(f"max_rounds {max_rounds} out of range [{MAX_ROUNDS_MIN},{MAX_ROUNDS_MAX}]")

    return {
        "subreddit_url": url,
        "subreddit_name": name,
        "subreddit_slug": slugify(name),
        "niche": niche.strip(),
        "count": count,
        "mix": mix,
        "days": days,
        "auto": auto,
        "seeds": seeds,
        "max_queries": max_queries,
        "max_rounds": max_rounds,
        "media_floor": media_floor,
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
