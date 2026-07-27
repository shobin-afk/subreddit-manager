"""Analyze the discovery pool against the target count + media floor."""
from __future__ import annotations

PLATFORMS_FOR_VIDEO = ["youtube", "tiktok", "instagram"]
PLATFORMS_FOR_IMAGE = ["pinterest", "instagram"]
ALL_PLATFORMS = ["tiktok", "instagram", "pinterest", "youtube"]


def analyze_pool(
    pool: list[dict],
    *,
    count: int,
    min_images: int,
    min_videos: int,
    media_total: int,
) -> dict:
    """Return gap info + which platforms to re-query this round."""
    videos = sum(1 for c in pool if c.get("post_type") == "video")
    images = sum(1 for c in pool if c.get("post_type") == "image")
    media = videos + images

    need_videos = max(0, min_videos - videos)
    need_images = max(0, min_images - images)
    need_media = max(0, media_total - media)
    need_count = max(0, count - len(pool))

    platforms: list[str] = []

    def add(ps):
        for p in ps:
            if p not in platforms:
                platforms.append(p)

    if need_videos:
        add(PLATFORMS_FOR_VIDEO)
    if need_images:
        add(PLATFORMS_FOR_IMAGE)
    if need_media or need_count:
        add(ALL_PLATFORMS)

    satisfied = not (need_videos or need_images or need_media or need_count)
    return {
        "need_count": need_count,
        "need_images": need_images,
        "need_videos": need_videos,
        "need_media": need_media,
        "platforms": platforms,
        "satisfied": satisfied,
    }
