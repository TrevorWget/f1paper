"""Load, save, and manipulate the f1paper YAML configuration.

The configuration holds:
- the target wallpaper resolution (or "auto" to detect the primary monitor)
- which photo sources are enabled
- per-team and per-driver enabled/weight toggles
- misc tuning knobs (history size, off-week buffer, etc.)
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

DEFAULT_TEAMS = [
    "mercedes",
    "red_bull",
    "ferrari",
    "mclaren",
    "aston_martin",
    "alpine",
    "williams",
    "racing_bulls",
    "kick_sauber",
    "haas",
]


@dataclass
class TeamConfig:
    enabled: bool = True
    weight: float = 100.0


@dataclass
class DriverConfig:
    enabled: bool = True
    weight: float = 100.0
    team: Optional[str] = None


@dataclass
class AppConfig:
    resolution: str = "auto"
    history_size: int = 30
    off_week_buffer_days: int = 1
    min_resolution_required: bool = True
    reddit_include_untagged: bool = False
    sources: Dict[str, bool] = field(
        default_factory=lambda: {
            "f1_official": True,
            "reddit": True,
            "twitter": True,
            "instagram": True,
        }
    )
    teams: Dict[str, TeamConfig] = field(
        default_factory=lambda: {t: TeamConfig() for t in DEFAULT_TEAMS}
    )
    drivers: Dict[str, DriverConfig] = field(default_factory=dict)

    def parsed_resolution(self) -> Optional[tuple[int, int]]:
        """Return (width, height) if an explicit resolution is set, else None for 'auto'."""
        if self.resolution.lower() == "auto":
            return None
        w, _, h = self.resolution.lower().partition("x")
        return int(w), int(h)


def default_config_dir() -> Path:
    override = os.environ.get("F1PAPER_CONFIG_DIR")
    if override:
        return Path(override)
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "f1paper"
    return Path.home() / ".config" / "f1paper"


def default_config_path() -> Path:
    return default_config_dir() / "config.yaml"


def default_cache_dir() -> Path:
    return default_config_dir() / "cache"


def _team_config_from_dict(d: dict) -> TeamConfig:
    return TeamConfig(enabled=bool(d.get("enabled", True)), weight=float(d.get("weight", 100.0)))


def _driver_config_from_dict(d: dict) -> DriverConfig:
    return DriverConfig(
        enabled=bool(d.get("enabled", True)),
        weight=float(d.get("weight", 100.0)),
        team=d.get("team"),
    )


def load_config(path: Optional[Path] = None) -> AppConfig:
    path = path or default_config_path()
    if not path.exists():
        return AppConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    teams = {
        name: _team_config_from_dict(val or {})
        for name, val in (raw.get("teams") or {}).items()
    } or {t: TeamConfig() for t in DEFAULT_TEAMS}

    drivers = {
        name: _driver_config_from_dict(val or {})
        for name, val in (raw.get("drivers") or {}).items()
    }

    sources = {
        "f1_official": True,
        "reddit": True,
        "twitter": True,
        "instagram": True,
    }
    sources.update(raw.get("sources") or {})

    return AppConfig(
        resolution=raw.get("resolution", "auto"),
        history_size=int(raw.get("history_size", 30)),
        off_week_buffer_days=int(raw.get("off_week_buffer_days", 1)),
        min_resolution_required=bool(raw.get("min_resolution_required", True)),
        reddit_include_untagged=bool(raw.get("reddit_include_untagged", False)),
        sources=sources,
        teams=teams,
        drivers=drivers,
    )


def save_config(config: AppConfig, path: Optional[Path] = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    raw = {
        "resolution": config.resolution,
        "history_size": config.history_size,
        "off_week_buffer_days": config.off_week_buffer_days,
        "min_resolution_required": config.min_resolution_required,
        "reddit_include_untagged": config.reddit_include_untagged,
        "sources": config.sources,
        "teams": {
            name: {"enabled": t.enabled, "weight": t.weight}
            for name, t in config.teams.items()
        },
        "drivers": {
            name: {"enabled": d.enabled, "weight": d.weight, "team": d.team}
            for name, d in config.drivers.items()
        },
    }
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def ensure_config_exists(path: Optional[Path] = None) -> Path:
    path = path or default_config_path()
    if not path.exists():
        save_config(AppConfig(), path)
    return path
