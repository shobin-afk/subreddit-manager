"""End-to-end seam test chaining real helper outputs across boundaries:
scoring -> shortlist -> post_schema -> assemble -> history.

Guards the append_used seam fix (delivered posts key their source URL as
``source_url``, not ``url``) and locks the overall pipeline shape.
"""
from datetime import date

from scoring import score_all
from shortlist import build_shortlist
from post_schema import validate_post
from assemble import write_post
from history import append_used, load_used, filter_unused

TODAY = date(2026, 7, 2)


def test_full_pipeline_seam_scoring_to_history(tmp_path):
    candidates = [
        {
            "title": "Chickens doing chicken things",
            "post_type": "video",
            "url": "https://tiktok.com/@x/video/1",
            "engagement": 500,
            "date": "2026-07-01",
            "relevance": 0.9,
            "hook": 0.8,
        },
        {
            "title": "Best coop bedding?",
            "post_type": "text",
            "url": "https://example.com/thread/2",
            "engagement": 10,
            "date": "2026-06-20",
            "relevance": 0.5,
            "hook": 0.3,
        },
    ]

    scored = score_all(candidates, today=TODAY, days=30)
    assert all("score" in c for c in scored)

    mix = {"media": 1, "text": 1, "news": 0}
    shortlist = build_shortlist(scored, mix, count=2)
    assert len(shortlist) == 2
    assert all("post_number" in c for c in shortlist)

    delivered_posts = []
    for c in shortlist:
        post = {
            "post_number": c["post_number"],
            "post_type": c["post_type"],
            "title": c["title"][:300],
            "suggested_flair": "",
            "nsfw": False,
            "source_platform": "tiktok" if c["post_type"] == "video" else "web",
            "source_url": c["url"],
            "attribution": "original creator",
            "media_file": "media.mp4" if c["post_type"] == "video" else "",
            "engagement_note": f"engagement={c['engagement']}",
            "status": "ready",
            "body": "A grounded body drafted from the discovered trend.",
        }
        errs = validate_post(post)
        assert errs == [], errs
        delivered_posts.append(post)

    run_dir = tmp_path / "chickens-r-backyardchickens-2026-07-02"
    for post in delivered_posts:
        post_dir = write_post(run_dir, post)
        assert (post_dir / "post.md").exists()

    history_path = tmp_path / ".history" / "r-backyardchickens.jsonl"
    append_used(history_path, delivered_posts, run_folder=run_dir.name,
                date_used=TODAY.isoformat())

    used = load_used(history_path)
    assert len(used) == 2

    # Second pass: a fresh candidate re-surfacing the same URL must be
    # filtered out by history dedup.
    reoffered = [{"url": "https://www.tiktok.com/@x/video/1?utm=1", "title": "dup"}]
    assert filter_unused(reoffered, used) == []
