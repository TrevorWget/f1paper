"""Pull race-weekend media tweets from official team/driver X (Twitter) accounts via twscrape.

twscrape (https://github.com/vladkens/twscrape) logs in as regular X accounts and
calls the same GraphQL endpoints the x.com web app uses. It is the actively
maintained successor to snscrape/twikit for this purpose (both effectively dead
as of 2025-2026), but it is still an unofficial integration: X can change its
internal API at any time and break this source. Requires at least one account
added to the twscrape pool beforehand, e.g.:

    twscrape add_accounts accounts.txt username:password:email:email_password
    twscrape login_accounts

Account session data lives in the sqlite DB pointed to by TWSCRAPE_DB_PATH.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import timezone
from typing import Dict, List

from f1paper.config import AppConfig
from f1paper.schedule import RaceWeekend, Roster
from f1paper.sources.base import Candidate

logger = logging.getLogger(__name__)

# Best-effort current official team accounts. Update each season if handles change.
TEAM_HANDLES: Dict[str, str] = {
    "mercedes": "MercedesAMGF1",
    "red_bull": "redbullracing",
    "ferrari": "ScuderiaFerrari",
    "mclaren": "McLarenF1",
    "aston_martin": "AstonMartinF1",
    "alpine": "AlpineF1Team",
    "williams": "WilliamsRacing",
    "racing_bulls": "visacashapprb",
    "kick_sauber": "stakef1team",
    "haas": "HaasF1Team",
}

TWEETS_PER_ACCOUNT_LIMIT = 50


async def _fetch_async(weekend: RaceWeekend, roster: Roster, config: AppConfig) -> List[Candidate]:
    try:
        from twscrape import API
    except ImportError:
        logger.warning("twitter: twscrape not installed, skipping source")
        return []

    db_path = os.environ.get("TWSCRAPE_DB_PATH")
    api = API(db_path) if db_path else API()

    accounts = await api.pool.accounts_info()
    if not accounts:
        logger.warning("twitter: no accounts in twscrape pool, skipping source (see module docstring)")
        return []

    candidates: List[Candidate] = []
    for team_id, handle in TEAM_HANDLES.items():
        team_cfg = config.teams.get(team_id)
        if team_cfg is not None and (not team_cfg.enabled or team_cfg.weight <= 0):
            continue

        try:
            async for tweet in api.search(f"from:{handle} filter:images", limit=TWEETS_PER_ACCOUNT_LIMIT):
                tweet_date = tweet.date
                if tweet_date.tzinfo is None:
                    tweet_date = tweet_date.replace(tzinfo=timezone.utc)
                if not (weekend.window_start <= tweet_date <= weekend.window_end):
                    continue

                media = getattr(tweet, "media", None)
                photos = getattr(media, "photos", None) if media else None
                if not photos:
                    continue

                for photo in photos:
                    candidates.append(
                        Candidate(
                            url=photo.url,
                            source="twitter",
                            teams=[team_id],
                            caption=tweet.rawContent or "",
                        )
                    )
        except Exception as exc:  # noqa: BLE001 - best-effort source, never kill the whole run
            logger.warning("twitter: failed fetching @%s (%s)", handle, exc)
            continue

    return candidates


def fetch(weekend: RaceWeekend, roster: Roster, config: AppConfig) -> List[Candidate]:
    return asyncio.run(_fetch_async(weekend, roster, config))


name = "twitter"
