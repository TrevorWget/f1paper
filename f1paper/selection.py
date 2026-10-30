"""Weighted, resolution-aware selection of the final wallpaper image."""
from __future__ import annotations

import random
from typing import List, Optional, Set

from f1paper.config import AppConfig
from f1paper.image_proc import DownloadedImage
from f1paper.sources.base import Candidate


def effective_weight(candidate: Candidate, config: AppConfig) -> float:
    """Combine per-team and per-driver toggles/weights into one multiplier.

    A photo featuring any disabled (or zero-weight) team/driver is excluded
    entirely. Otherwise the weights of every team and driver pictured are
    multiplied together (each normalized against 100 = "default").
    """
    weight = 1.0

    for team_id in candidate.teams:
        team_cfg = config.teams.get(team_id)
        if team_cfg is None:
            continue  # unknown team id: don't penalize, just don't scale by it
        if not team_cfg.enabled or team_cfg.weight <= 0:
            return 0.0
        weight *= team_cfg.weight / 100.0

    for driver_id in candidate.drivers:
        driver_cfg = config.drivers.get(driver_id)
        if driver_cfg is None:
            continue
        if not driver_cfg.enabled or driver_cfg.weight <= 0:
            return 0.0
        weight *= driver_cfg.weight / 100.0

    return weight


def _aspect_fit_score(width: int, height: int, target_w: int, target_h: int) -> float:
    target_aspect = target_w / target_h
    aspect = width / height
    diff = abs(aspect - target_aspect)
    # Score decays from 1.0 (perfect match) towards a small floor so wildly
    # mismatched aspect ratios are heavily deprioritized but never impossible.
    return max(0.05, 1.0 - min(diff, 1.0))


def select_wallpaper(
    downloaded: List[DownloadedImage],
    config: AppConfig,
    target_w: int,
    target_h: int,
    recent_hashes: Set[str],
    rng: Optional[random.Random] = None,
) -> Optional[DownloadedImage]:
    rng = rng or random.Random()

    pool = [d for d in downloaded if str(d.phash) not in recent_hashes]
    if not pool:
        pool = downloaded  # history exhausted the whole pool; allow repeats as a last resort
    if not pool:
        return None

    weighted = [(d, effective_weight(d.candidate, config)) for d in pool]
    weighted = [(d, w) for d, w in weighted if w > 0]
    if not weighted:
        return None

    if config.min_resolution_required:
        fits = [(d, w) for d, w in weighted if d.width >= target_w and d.height >= target_h]
        pool_final = fits if fits else weighted
    else:
        pool_final = weighted

    scored = [
        (d, w * _aspect_fit_score(d.width, d.height, target_w, target_h))
        for d, w in pool_final
    ]
    total = sum(w for _, w in scored)
    if total <= 0:
        return None

    picks = rng.choices([d for d, _ in scored], weights=[w for _, w in scored], k=1)
    return picks[0]
