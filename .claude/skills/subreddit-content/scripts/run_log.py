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
