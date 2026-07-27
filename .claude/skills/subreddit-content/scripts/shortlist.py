"""Bucket-fill scored candidates to hit the target mix, then number them."""
from __future__ import annotations

_BUCKET_MAP = {"video": "media", "image": "media", "text": "text", "link": "news"}


def bucket_of(post_type: str) -> str:
    """Map a post_type to its mix bucket (media / text / news)."""
    return _BUCKET_MAP.get(post_type, "news")


def build_shortlist(scored: list[dict], mix: dict[str, int], count: int, floor: dict | None = None) -> list[dict]:
    """Select up to *count* candidates.

    If *floor* is given ({"min_images","min_videos"}), guarantee that many
    image/video candidates (highest-scored) are selected first. Then satisfy
    the per-bucket *mix* quota (floor picks count toward the media quota) and
    backfill from remaining highest-scored candidates. Floor picks are
    guaranteed to be included even when sum(mix.values()) > count. When
    min_images + min_videos > mix["media"], floor picks intentionally take
    priority and media may exceed its quota. Adds a 1-based ``post_number``
    in final score-desc order."""
    by_bucket: dict[str, list[dict]] = {"media": [], "text": [], "news": []}
    for c in scored:
        by_bucket[bucket_of(c.get("post_type", "link"))].append(c)
    for b in by_bucket.values():
        b.sort(key=lambda c: c.get("score", 0), reverse=True)

    chosen: list[dict] = []
    chosen_ids: set[int] = set()
    floor_ids: set[int] = set()

    def take(c, is_floor: bool = False) -> bool:
        if id(c) in chosen_ids:
            return False
        chosen.append(c)
        chosen_ids.add(id(c))
        if is_floor:
            floor_ids.add(id(c))
        return True

    # 1) media floor — guarantee >= min video and >= min image (highest scored)
    if floor:
        for post_type, key in (("video", "min_videos"), ("image", "min_images")):
            need = floor.get(key, 0)
            pool = sorted(
                (c for c in scored if c.get("post_type") == post_type),
                key=lambda c: c.get("score", 0), reverse=True,
            )
            for c in pool:
                if need <= 0:
                    break
                if take(c, is_floor=True):
                    need -= 1

    # 2) per-bucket quota (already-chosen items count toward their bucket)
    for bucket, quota in mix.items():
        in_bucket = sum(1 for c in chosen if bucket_of(c.get("post_type", "link")) == bucket)
        for c in by_bucket.get(bucket, []):
            if in_bucket >= quota:
                break
            if take(c):
                in_bucket += 1

    # 3) backfill to reach count, highest score first
    if len(chosen) < count:
        for c in sorted(scored, key=lambda c: c.get("score", 0), reverse=True):
            if len(chosen) >= count:
                break
            take(c)

    # 4) finalize: preserve floor picks, slice by score for remaining
    chosen.sort(key=lambda c: c.get("score", 0), reverse=True)

    floor_picks = [c for c in chosen if id(c) in floor_ids]
    other_picks = [c for c in chosen if id(c) not in floor_ids]

    # Sort both by score
    floor_picks.sort(key=lambda c: c.get("score", 0), reverse=True)
    other_picks.sort(key=lambda c: c.get("score", 0), reverse=True)

    # Keep highest-scored floor picks up to count
    if len(floor_picks) > count:
        floor_picks = floor_picks[:count]
        other_picks = []
    else:
        # Keep all floor picks, take enough others to reach count
        other_picks = other_picks[:max(0, count - len(floor_picks))]

    final = floor_picks + other_picks
    final.sort(key=lambda c: c.get("score", 0), reverse=True)

    out = []
    for n, c in enumerate(final[:count], start=1):
        cc = dict(c)
        cc["post_number"] = n
        out.append(cc)
    return out
