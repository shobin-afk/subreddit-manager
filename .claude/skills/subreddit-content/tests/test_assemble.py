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
