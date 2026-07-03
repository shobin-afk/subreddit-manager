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
