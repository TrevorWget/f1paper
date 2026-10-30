import random

from f1paper.config import AppConfig, DriverConfig, TeamConfig
from f1paper.image_proc import DownloadedImage
from f1paper.selection import effective_weight, select_wallpaper
from f1paper.sources.base import Candidate


def make_config(**overrides) -> AppConfig:
    config = AppConfig(
        teams={
            "ferrari": TeamConfig(enabled=True, weight=100),
            "mercedes": TeamConfig(enabled=False, weight=100),
            "mclaren": TeamConfig(enabled=True, weight=50),
        },
        drivers={
            "leclerc": DriverConfig(enabled=True, weight=100, team="ferrari"),
            "norris": DriverConfig(enabled=False, weight=100, team="mclaren"),
        },
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def make_image(candidate: Candidate, width: int, height: int, phash: str) -> DownloadedImage:
    return DownloadedImage(candidate=candidate, path=None, width=width, height=height, phash=phash)


def test_effective_weight_disabled_team_excludes_candidate():
    config = make_config()
    candidate = Candidate(url="x", source="test", teams=["mercedes"])
    assert effective_weight(candidate, config) == 0.0


def test_effective_weight_disabled_driver_excludes_candidate():
    config = make_config()
    candidate = Candidate(url="x", source="test", teams=["mclaren"], drivers=["norris"])
    assert effective_weight(candidate, config) == 0.0


def test_effective_weight_combines_team_and_driver_weights():
    config = make_config()
    candidate = Candidate(url="x", source="test", teams=["ferrari"], drivers=["leclerc"])
    # 100/100 * 100/100 = 1.0
    assert effective_weight(candidate, config) == 1.0


def test_effective_weight_unknown_team_is_not_penalized():
    config = make_config()
    candidate = Candidate(url="x", source="test", teams=["some_new_team"])
    assert effective_weight(candidate, config) == 1.0


def test_select_wallpaper_excludes_disabled_team():
    config = make_config()
    disabled = make_image(Candidate(url="a", source="test", teams=["mercedes"]), 1920, 1080, "hash_a")
    enabled = make_image(Candidate(url="b", source="test", teams=["ferrari"]), 1920, 1080, "hash_b")

    pick = select_wallpaper([disabled, enabled], config, 1920, 1080, recent_hashes=set(), rng=random.Random(0))

    assert pick is enabled


def test_select_wallpaper_prefers_matching_resolution_when_required():
    config = make_config(min_resolution_required=True)
    too_small = make_image(Candidate(url="a", source="test", teams=["ferrari"]), 800, 600, "hash_a")
    big_enough = make_image(Candidate(url="b", source="test", teams=["ferrari"]), 2560, 1440, "hash_b")

    pick = select_wallpaper(
        [too_small, big_enough], config, 1920, 1080, recent_hashes=set(), rng=random.Random(0)
    )

    assert pick is big_enough


def test_select_wallpaper_skips_recently_used_hash():
    config = make_config()
    recent = make_image(Candidate(url="a", source="test", teams=["ferrari"]), 1920, 1080, "hash_a")
    fresh = make_image(Candidate(url="b", source="test", teams=["ferrari"]), 1920, 1080, "hash_b")

    pick = select_wallpaper(
        [recent, fresh], config, 1920, 1080, recent_hashes={"hash_a"}, rng=random.Random(0)
    )

    assert pick is fresh


def test_select_wallpaper_returns_none_when_everything_excluded():
    config = make_config()
    disabled = make_image(Candidate(url="a", source="test", teams=["mercedes"]), 1920, 1080, "hash_a")

    pick = select_wallpaper([disabled], config, 1920, 1080, recent_hashes=set(), rng=random.Random(0))

    assert pick is None
