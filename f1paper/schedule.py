"""Race weekend detection via the jolpica-f1 API (free, keyless Ergast successor)
and the current-season team/driver roster used for photo attribution.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
USER_AGENT = os.environ.get("F1PAPER_USER_AGENT", "f1paper/0.1.0 (personal wallpaper tool)")

SESSION_KEYS = [
    "FirstPractice",
    "SecondPractice",
    "ThirdPractice",
    "SprintQualifying",
    "Sprint",
    "Qualifying",
]

# Best-effort normalization of jolpica/Ergast constructorId -> our internal team ids.
# Update each season if team names/ids change (e.g. rebrands, new entrants).
CONSTRUCTOR_ID_MAP = {
    "mercedes": "mercedes",
    "red_bull": "red_bull",
    "ferrari": "ferrari",
    "mclaren": "mclaren",
    "aston_martin": "aston_martin",
    "alpine": "alpine",
    "williams": "williams",
    "rb": "racing_bulls",
    "racing_bulls": "racing_bulls",
    "sauber": "kick_sauber",
    "kick_sauber": "kick_sauber",
    "haas": "haas",
}


@dataclass
class RaceWeekend:
    season: str
    round: str
    race_name: str
    circuit_name: str
    country: str
    race_date: datetime
    window_start: datetime
    window_end: datetime
    sessions: Dict[str, datetime] = field(default_factory=dict)


@dataclass
class Roster:
    constructors: Dict[str, str]  # team_id -> display name
    drivers: Dict[str, dict]  # driver_id -> {"name": str, "team": team_id}


def _request(url: str, params: Optional[dict] = None) -> dict:
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _parse_session_dt(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    time_str = time_str or "00:00:00Z"
    raw = f"{date_str}T{time_str}"
    raw = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def build_weekend_from_race_dict(raw: dict, buffer_days: int = 1) -> RaceWeekend:
    """Pure function: turn one jolpica/Ergast 'Races' entry into a RaceWeekend.

    Kept free of network calls so it can be unit tested directly.
    """
    race_date = _parse_session_dt(raw.get("date"), raw.get("time"))
    sessions: Dict[str, datetime] = {}
    for key in SESSION_KEYS:
        block = raw.get(key)
        if block:
            dt = _parse_session_dt(block.get("date"), block.get("time"))
            if dt:
                sessions[key] = dt

    candidate_starts = list(sessions.values())
    if race_date:
        candidate_starts.append(race_date)
    window_start = min(candidate_starts) if candidate_starts else race_date
    window_end = (race_date or window_start) + timedelta(days=buffer_days)

    circuit = raw.get("Circuit", {})
    location = circuit.get("Location", {})
    return RaceWeekend(
        season=raw.get("season", ""),
        round=raw.get("round", ""),
        race_name=raw.get("raceName", ""),
        circuit_name=circuit.get("circuitName", ""),
        country=location.get("country", ""),
        race_date=race_date,
        window_start=window_start,
        window_end=window_end,
        sessions=sessions,
    )


def is_active(weekend: RaceWeekend, now: datetime) -> bool:
    if weekend.window_start is None or weekend.window_end is None:
        return False
    return weekend.window_start <= now <= weekend.window_end


def fetch_current_season_races(buffer_days: int = 1) -> List[RaceWeekend]:
    data = _request(f"{JOLPICA_BASE}/current.json")
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    return [build_weekend_from_race_dict(r, buffer_days=buffer_days) for r in races]


def get_active_weekend(now: Optional[datetime] = None, buffer_days: int = 1) -> Optional[RaceWeekend]:
    now = now or datetime.now(timezone.utc)
    for weekend in fetch_current_season_races(buffer_days=buffer_days):
        if is_active(weekend, now):
            return weekend
    return None


def get_most_recent_weekend(now: Optional[datetime] = None, buffer_days: int = 1) -> Optional[RaceWeekend]:
    """Used for --force manual runs outside an active race weekend."""
    now = now or datetime.now(timezone.utc)
    weekends = [w for w in fetch_current_season_races(buffer_days=buffer_days) if w.race_date and w.race_date <= now]
    if not weekends:
        return None
    return max(weekends, key=lambda w: w.race_date)


def _roster_cache_path(cache_dir: Path, season: str) -> Path:
    return cache_dir / f"roster_{season}.json"


def fetch_roster(season: str, cache_dir: Optional[Path] = None, max_age_seconds: int = 24 * 3600) -> Roster:
    if cache_dir:
        cache_path = _roster_cache_path(cache_dir, season)
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < max_age_seconds:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            return Roster(constructors=raw["constructors"], drivers=raw["drivers"])

    data = _request(f"{JOLPICA_BASE}/{season}/driverStandings.json", params={"limit": 100})
    lists = (
        data.get("MRData", {})
        .get("StandingsTable", {})
        .get("StandingsLists", [])
    )
    constructors: Dict[str, str] = {}
    drivers: Dict[str, dict] = {}
    if lists:
        for entry in lists[0].get("DriverStandings", []):
            driver = entry.get("Driver", {})
            driver_id = driver.get("driverId")
            full_name = f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
            team_entries = entry.get("Constructors", [])
            team_raw_id = team_entries[-1].get("constructorId") if team_entries else None
            team_id = CONSTRUCTOR_ID_MAP.get(team_raw_id, team_raw_id)
            team_name = team_entries[-1].get("name") if team_entries else None
            if driver_id:
                drivers[driver_id] = {"name": full_name, "team": team_id}
            if team_id and team_name:
                constructors[team_id] = team_name

    roster = Roster(constructors=constructors, drivers=drivers)

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _roster_cache_path(cache_dir, season).write_text(
            json.dumps({"constructors": roster.constructors, "drivers": roster.drivers}),
            encoding="utf-8",
        )
    return roster


def match_roster_in_text(text: str, roster: Roster) -> tuple[List[str], List[str]]:
    """Best-effort attribution: find team/driver names mentioned in free text
    (captions, post titles, tweet text, etc.)."""
    text_lower = text.lower()
    teams = [team_id for team_id, name in roster.constructors.items() if name.lower() in text_lower]
    drivers = [driver_id for driver_id, info in roster.drivers.items() if info["name"].lower() in text_lower]
    # Infer team from matched drivers even if the team name itself wasn't mentioned.
    for driver_id in drivers:
        team_id = roster.drivers[driver_id].get("team")
        if team_id and team_id not in teams:
            teams.append(team_id)
    return teams, drivers
