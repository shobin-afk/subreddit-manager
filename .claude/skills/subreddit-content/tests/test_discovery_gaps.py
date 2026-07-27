"""Tests for discovery_gaps — floor/count gap analysis + platform targeting."""
from discovery_gaps import analyze_pool, PLATFORMS_FOR_VIDEO, PLATFORMS_FOR_IMAGE


def _pool(videos=0, images=0, texts=0):
    out = []
    out += [{"post_type": "video", "url": f"v{i}"} for i in range(videos)]
    out += [{"post_type": "image", "url": f"i{i}"} for i in range(images)]
    out += [{"post_type": "text", "url": f"t{i}"} for i in range(texts)]
    return out


def test_satisfied_when_floor_and_count_met():
    g = analyze_pool(_pool(videos=6, images=6, texts=5), count=15,
                     min_images=1, min_videos=1, media_total=10)
    assert g["satisfied"] is True
    assert g["platforms"] == []


def test_missing_video_targets_video_platforms():
    g = analyze_pool(_pool(videos=0, images=10, texts=5), count=15,
                     min_images=1, min_videos=1, media_total=10)
    assert g["need_videos"] == 1
    assert set(PLATFORMS_FOR_VIDEO).issubset(set(g["platforms"]))
    assert g["satisfied"] is False


def test_missing_image_targets_image_platforms():
    g = analyze_pool(_pool(videos=10, images=0, texts=5), count=15,
                     min_images=1, min_videos=1, media_total=10)
    assert g["need_images"] == 1
    assert set(PLATFORMS_FOR_IMAGE).issubset(set(g["platforms"]))


def test_media_total_shortfall_flags_need_media():
    g = analyze_pool(_pool(videos=2, images=2, texts=5), count=15,
                     min_images=1, min_videos=1, media_total=10)
    assert g["need_media"] == 6
    assert g["platforms"]  # non-empty


def test_count_shortfall_flags_need_count():
    g = analyze_pool(_pool(videos=3, images=3, texts=0), count=15,
                     min_images=1, min_videos=1, media_total=6)
    assert g["need_count"] == 9
    assert g["satisfied"] is False
