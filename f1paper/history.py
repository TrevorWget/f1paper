"""Local JSON store of recently-used image hashes, to avoid repeating wallpapers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Set


def _history_path(cache_dir: Path) -> Path:
    return cache_dir / "history.json"


def load_recent(cache_dir: Path) -> Set[str]:
    path = _history_path(cache_dir)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("recent_hashes", []))
    except (json.JSONDecodeError, OSError):
        return set()


def record_used(cache_dir: Path, image_hash: str, max_size: int) -> None:
    path = _history_path(cache_dir)
    recent: List[str] = []
    if path.exists():
        try:
            recent = json.loads(path.read_text(encoding="utf-8")).get("recent_hashes", [])
        except (json.JSONDecodeError, OSError):
            recent = []

    recent.append(image_hash)
    recent = recent[-max_size:]

    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"recent_hashes": recent}), encoding="utf-8")


def clear(cache_dir: Path) -> None:
    path = _history_path(cache_dir)
    if path.exists():
        path.unlink()
