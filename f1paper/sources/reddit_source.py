"""Pull race-weekend photo posts from r/formula1 via the official Reddit API (PRAW).

Requires a free Reddit "script" app: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET /
REDDIT_USER_AGENT environment variables (see .env.example).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List

import praw

from f1paper.config import AppConfig
from f1paper.schedule import RaceWeekend, Roster, match_roster_in_text
from f1paper.sources.base import Candidate

logger = logging.getLogger(__name__)

SUBREDDIT = "formula1"
IMAGE_DOMAINS = ("i.redd.it", "i.imgur.com")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def _is_direct_image_url(url: str) -> bool:
    url_lower = url.lower()
    return any(d in url_lower for d in IMAGE_DOMAINS) or url_lower.endswith(IMAGE_EXTENSIONS)


def _build_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "f1paper/0.1.0"),
        check_for_async=False,
    )


def fetch(weekend: RaceWeekend, roster: Roster, config: AppConfig) -> List[Candidate]:
    if "REDDIT_CLIENT_ID" not in os.environ or "REDDIT_CLIENT_SECRET" not in os.environ:
        logger.warning("reddit: REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not set, skipping source")
        return []

    reddit = _build_reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    candidates: List[Candidate] = []
    for submission in subreddit.new(limit=300):
        created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
        if created < weekend.window_start:
            # submissions come back newest-first; once we're older than the
            # window there's nothing more to find.
            break
        if created > weekend.window_end:
            continue
        if submission.over_18 or not _is_direct_image_url(submission.url):
            continue

        teams, drivers = match_roster_in_text(submission.title, roster)
        if not teams and not drivers and not config.reddit_include_untagged:
            continue

        candidates.append(
            Candidate(
                url=submission.url,
                source="reddit",
                teams=teams,
                drivers=drivers,
                caption=submission.title,
            )
        )

    return candidates


name = "reddit"
