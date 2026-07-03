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
