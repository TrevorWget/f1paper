"""Pull race-weekend photo posts from official team Instagram accounts via instaloader.

Works anonymously against public profiles but is heavily rate-limited by
Instagram; set INSTAGRAM_USERNAME/INSTAGRAM_PASSWORD to log in and reduce
throttling (session is cached to disk after the first successful login).
"""
from __future__ import annotations

import logging
import os
from datetime import timezone
from pathlib import Path
from typing import Dict, List

from f1paper.config import AppConfig, default_cache_dir
from f1paper.schedule import RaceWeekend, Roster
from f1paper.sources.base import Candidate

logger = logging.getLogger(__name__)

# Best-effort current official team handles. Update each season if they change.
TEAM_HANDLES: Dict[str, str] = {
    "mercedes": "mercedesamgf1",
    "red_bull": "redbullracing",
    "ferrari": "scuderiaferrari",
    "mclaren": "mclaren",
    "aston_martin": "astonmartinf1",
    "alpine": "alpinef1team",
    "williams": "williamsracing",
    "racing_bulls": "visacashapprbf1team",
    "kick_sauber": "stakef1team",
    "haas": "haasf1team",
}

POSTS_PER_ACCOUNT_LIMIT = 40


def _build_loader(cache_dir: Path):
    import instaloader

    loader = instaloader.Instaloader(
        download_videos=False,
        download_video_thumbnails=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        dirname_pattern=str(cache_dir / "instagram_tmp"),
        quiet=True,
    )

    username = os.environ.get("INSTAGRAM_USERNAME")
    password = os.environ.get("INSTAGRAM_PASSWORD")
    session_file = cache_dir / f"instagram_session_{username}" if username else None

    if username:
        try:
            if session_file and session_file.exists():
                loader.load_session_from_file(username, filename=str(session_file))
            elif password:
                loader.login(username, password)
                if session_file:
                    loader.save_session_to_file(filename=str(session_file))
        except Exception as exc:  # noqa: BLE001
            logger.warning("instagram: login failed, continuing anonymously (%s)", exc)

    return loader


def fetch(weekend: RaceWeekend, roster: Roster, config: AppConfig) -> List[Candidate]:
    try:
        import instaloader
    except ImportError:
        logger.warning("instagram: instaloader not installed, skipping source")
        return []

    cache_dir = default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    loader = _build_loader(cache_dir)

    candidates: List[Candidate] = []
    for team_id, handle in TEAM_HANDLES.items():
        team_cfg = config.teams.get(team_id)
        if team_cfg is not None and (not team_cfg.enabled or team_cfg.weight <= 0):
            continue

        try:
            profile = instaloader.Profile.from_username(loader.context, handle)
        except Exception as exc:  # noqa: BLE001
            logger.warning("instagram: failed to load profile @%s (%s)", handle, exc)
            continue

        try:
            count = 0
            for post in profile.get_posts():
                if count >= POSTS_PER_ACCOUNT_LIMIT:
                    break
                count += 1

                post_date = post.date_utc
                if post_date.tzinfo is None:
                    post_date = post_date.replace(tzinfo=timezone.utc)
                if post_date < weekend.window_start:
                    break  # posts are newest-first
                if post_date > weekend.window_end or post.is_video:
                    continue

                candidates.append(
                    Candidate(
                        url=post.url,
                        source="instagram",
                        teams=[team_id],
                        caption=post.caption or "",
                    )
                )
        except Exception as exc:  # noqa: BLE001 - best-effort source
            logger.warning("instagram: failed fetching posts for @%s (%s)", handle, exc)
            continue

    return candidates


name = "instagram"
