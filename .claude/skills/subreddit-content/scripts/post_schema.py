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
