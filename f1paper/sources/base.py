"""Shared data model for all photo sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from f1paper.config import AppConfig
from f1paper.schedule import RaceWeekend, Roster


@dataclass
class Candidate:
    url: str
    source: str
    teams: List[str] = field(default_factory=list)
    drivers: List[str] = field(default_factory=list)
    caption: str = ""
    width: Optional[int] = None  # hint only; image_proc verifies the real size
    height: Optional[int] = None


class PhotoSource(Protocol):
    name: str

    def fetch(self, weekend: RaceWeekend, roster: Roster, config: AppConfig) -> List[Candidate]:
        ...
