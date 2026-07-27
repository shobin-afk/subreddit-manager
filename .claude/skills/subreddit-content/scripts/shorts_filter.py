"""Keep only YouTube Shorts (URL /shorts/ or duration <= 60s)."""
from __future__ import annotations

SHORT_MAX_SECONDS = 60


def is_short(url: str, duration: float | None = None, *, max_seconds: int = SHORT_MAX_SECONDS) -> bool:
    """True for a Short: /shorts/ URL, or a known duration within the cap.
    Unknown duration on a non-/shorts/ URL is treated as NOT a Short."""
    if "/shorts/" in (url or "").lower():
        return True
    if duration is not None:
        try:
            return float(duration) <= max_seconds
        except (TypeError, ValueError):
            return False
    return False


def filter_shorts(items: list[dict]) -> list[dict]:
    """Keep only items whose url/duration qualify as a Short."""
    return [i for i in items if is_short(i.get("url", ""), i.get("duration"))]


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            items = json.load(f)
    else:
        items = json.load(sys.stdin)

    print(json.dumps(filter_shorts(items), indent=2))
