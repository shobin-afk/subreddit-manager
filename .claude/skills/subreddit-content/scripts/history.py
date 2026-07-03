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
                "url": it.get("url") or it.get("source_url", ""),
                "title": it.get("title", ""),
                "date_used": date_used,
                "run_folder": run_folder,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
