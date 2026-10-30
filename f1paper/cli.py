"""Command-line interface for f1paper.

Commands:
    f1paper run [--resolution WxH] [--force] [--dry-run]
    f1paper config show
    f1paper config team <name> [--enable|--disable] [--weight N]
    f1paper config driver <name> [--enable|--disable] [--weight N]
    f1paper config source <name> [--enable|--disable]
    f1paper config resolution <WxH|auto>
    f1paper config sync-roster
    f1paper install-schedule
    f1paper history clear
"""
from __future__ import annotations

import argparse
import logging
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from f1paper import config as config_mod
from f1paper import history as history_mod
from f1paper import image_proc
from f1paper import schedule as schedule_mod
from f1paper import selection as selection_mod
from f1paper import wallpaper as wallpaper_mod
from f1paper.config import AppConfig, DriverConfig, TeamConfig
from f1paper.sources import f1_official, instagram_source, reddit_source, twitter_source

logger = logging.getLogger("f1paper")

SOURCE_MODULES = {
    "f1_official": f1_official,
    "reddit": reddit_source,
    "twitter": twitter_source,
    "instagram": instagram_source,
}

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _detect_target_resolution(config: AppConfig, override: Optional[str]) -> tuple[int, int]:
    if override:
        w, _, h = override.lower().partition("x")
        return int(w), int(h)

    explicit = config.parsed_resolution()
    if explicit:
        return explicit

    try:
        import screeninfo

        monitors = screeninfo.get_monitors()
        primary = next((m for m in monitors if getattr(m, "is_primary", False)), monitors[0])
        return primary.width, primary.height
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not auto-detect monitor resolution (%s); defaulting to 1920x1080", exc)
        return 1920, 1080


def cmd_run(args: argparse.Namespace) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config_mod.ensure_config_exists()
    config = config_mod.load_config()
    cache_dir = config_mod.default_cache_dir()

    now = datetime.now(timezone.utc)
    weekend = schedule_mod.get_active_weekend(now, buffer_days=config.off_week_buffer_days)

    if weekend is None:
        if args.force:
            weekend = schedule_mod.get_most_recent_weekend(now, buffer_days=config.off_week_buffer_days)
            if weekend is None:
                print("No race weekend data available at all. Nothing to do.")
                return 1
            print(f"No active race weekend; --force using most recent: {weekend.race_name}")
        else:
            print("No active F1 race weekend right now. Keeping current wallpaper.")
            return 0

    roster = schedule_mod.fetch_roster(weekend.season, cache_dir=cache_dir)

    candidates = []
    for source_name, enabled in config.sources.items():
        if not enabled:
            continue
        module = SOURCE_MODULES.get(source_name)
        if module is None:
            logger.warning("Unknown source in config: %s", source_name)
            continue
        try:
            found = module.fetch(weekend, roster, config)
            logger.info("%s: found %d candidate(s)", source_name, len(found))
            candidates.extend(found)
        except Exception as exc:  # noqa: BLE001 - one failing source must not kill the run
            logger.warning("%s: source failed (%s)", source_name, exc)

    if not candidates:
        print("No candidate photos found from any enabled source. Keeping current wallpaper.")
        return 0

    downloaded = image_proc.download_candidates(candidates, cache_dir / "downloads")
    if not downloaded:
        print("Could not download any candidate photos. Keeping current wallpaper.")
        return 0

    target_w, target_h = _detect_target_resolution(config, args.resolution)
    recent_hashes = history_mod.load_recent(cache_dir)

    pick = selection_mod.select_wallpaper(downloaded, config, target_w, target_h, recent_hashes)
    if pick is None:
        print("No candidate matched your team/driver/resolution settings. Keeping current wallpaper.")
        return 0

    final_image = image_proc.crop_resize_cover(pick.path, target_w, target_h)
    output_path = cache_dir / "current_wallpaper.jpg"
    cache_dir.mkdir(parents=True, exist_ok=True)
    final_image.save(output_path, "JPEG", quality=92)

    summary = (
        f"Selected photo from {pick.candidate.source} "
        f"(teams={pick.candidate.teams or '-'}, drivers={pick.candidate.drivers or '-'}) "
        f"native {pick.width}x{pick.height} -> {target_w}x{target_h}"
    )
    print(summary)

    if args.dry_run:
        print(f"[dry-run] Would set wallpaper to: {output_path}")
        return 0

    wallpaper_mod.set_wallpaper(output_path)
    history_mod.record_used(cache_dir, str(pick.phash), config.history_size)
    print(f"Wallpaper updated: {output_path}")
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    config = config_mod.load_config()
    print(f"Config path: {config_mod.default_config_path()}")
    print(f"Resolution: {config.resolution}")
    print(f"History size: {config.history_size}")
    print(f"Off-week buffer (days): {config.off_week_buffer_days}")
    print(f"Minimum resolution required: {config.min_resolution_required}")
    print("Sources:")
    for name, enabled in config.sources.items():
        print(f"  {name}: {'on' if enabled else 'off'}")
    print("Teams:")
    for name, team in sorted(config.teams.items()):
        print(f"  {name}: enabled={team.enabled} weight={team.weight}")
    print("Drivers:")
    for name, driver in sorted(config.drivers.items()):
        print(f"  {name} ({driver.team}): enabled={driver.enabled} weight={driver.weight}")
    return 0


def cmd_config_team(args: argparse.Namespace) -> int:
    config = config_mod.load_config()
    team = config.teams.get(args.name, TeamConfig())
    if args.enable:
        team.enabled = True
    if args.disable:
        team.enabled = False
    if args.weight is not None:
        team.weight = args.weight
    config.teams[args.name] = team
    config_mod.save_config(config)
    print(f"team '{args.name}': enabled={team.enabled} weight={team.weight}")
    return 0


def cmd_config_driver(args: argparse.Namespace) -> int:
    config = config_mod.load_config()
    driver = config.drivers.get(args.name, DriverConfig(team=args.team))
    if args.team:
        driver.team = args.team
    if args.enable:
        driver.enabled = True
    if args.disable:
        driver.enabled = False
    if args.weight is not None:
        driver.weight = args.weight
    config.drivers[args.name] = driver
    config_mod.save_config(config)
    print(f"driver '{args.name}': team={driver.team} enabled={driver.enabled} weight={driver.weight}")
    return 0


def cmd_config_source(args: argparse.Namespace) -> int:
    config = config_mod.load_config()
    if args.name not in SOURCE_MODULES:
        print(f"Unknown source '{args.name}'. Known sources: {', '.join(SOURCE_MODULES)}")
        return 1
    if args.enable:
        config.sources[args.name] = True
    if args.disable:
        config.sources[args.name] = False
    config_mod.save_config(config)
    print(f"source '{args.name}': {'on' if config.sources[args.name] else 'off'}")
    return 0


def cmd_config_resolution(args: argparse.Namespace) -> int:
    config = config_mod.load_config()
    config.resolution = args.value
    config_mod.save_config(config)
    print(f"resolution set to '{args.value}'")
    return 0


def cmd_config_sync_roster(args: argparse.Namespace) -> int:
    config = config_mod.load_config()
    now = datetime.now(timezone.utc)
    season = str(now.year)
    cache_dir = config_mod.default_cache_dir()
    roster = schedule_mod.fetch_roster(season, cache_dir=cache_dir, max_age_seconds=0)

    for team_id in roster.constructors:
        config.teams.setdefault(team_id, TeamConfig())
    for driver_id, info in roster.drivers.items():
        existing = config.drivers.get(driver_id)
        if existing:
            existing.team = info.get("team")
        else:
            config.drivers[driver_id] = DriverConfig(team=info.get("team"))

    config_mod.save_config(config)
    print(f"Synced roster for season {season}: {len(roster.constructors)} teams, {len(roster.drivers)} drivers.")
    return 0


def cmd_history_clear(args: argparse.Namespace) -> int:
    history_mod.clear(config_mod.default_cache_dir())
    print("History cleared.")
    return 0


def cmd_install_schedule(args: argparse.Namespace) -> int:
    system = platform.system()
    if system == "Windows":
        script = SCRIPTS_DIR / "install_task_windows.ps1"
        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Time", args.time],
            check=True,
        )
    elif system == "Linux":
        script = SCRIPTS_DIR / "install_timer_linux.sh"
        subprocess.run(["bash", str(script), args.time], check=True)
    else:
        print(f"Automatic scheduling is not supported on {system}. Run 'f1paper run' manually instead.")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="f1paper", description="Automated F1 wallpaper acquisition tool")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Fetch and set a new wallpaper for the current race weekend")
    run_p.add_argument("--resolution", help="Override target resolution, e.g. 2560x1440")
    run_p.add_argument("--force", action="store_true", help="Run even outside an active race weekend")
    run_p.add_argument("--dry-run", action="store_true", help="Pick and save the image but don't set it as wallpaper")
    run_p.set_defaults(func=cmd_run)

    config_p = sub.add_parser("config", help="View/edit configuration")
    config_sub = config_p.add_subparsers(dest="config_command", required=True)

    show_p = config_sub.add_parser("show", help="Print current configuration")
    show_p.set_defaults(func=cmd_config_show)

    team_p = config_sub.add_parser("team", help="Toggle/weight a team")
    team_p.add_argument("name")
    team_p.add_argument("--enable", action="store_true")
    team_p.add_argument("--disable", action="store_true")
    team_p.add_argument("--weight", type=float)
    team_p.set_defaults(func=cmd_config_team)

    driver_p = config_sub.add_parser("driver", help="Toggle/weight a driver")
    driver_p.add_argument("name")
    driver_p.add_argument("--team")
    driver_p.add_argument("--enable", action="store_true")
    driver_p.add_argument("--disable", action="store_true")
    driver_p.add_argument("--weight", type=float)
    driver_p.set_defaults(func=cmd_config_driver)

    source_p = config_sub.add_parser("source", help="Enable/disable a photo source")
    source_p.add_argument("name", choices=list(SOURCE_MODULES))
    source_p.add_argument("--enable", action="store_true")
    source_p.add_argument("--disable", action="store_true")
    source_p.set_defaults(func=cmd_config_source)

    resolution_p = config_sub.add_parser("resolution", help="Set target resolution ('auto' or WIDTHxHEIGHT)")
    resolution_p.add_argument("value")
    resolution_p.set_defaults(func=cmd_config_resolution)

    sync_p = config_sub.add_parser("sync-roster", help="Refresh team/driver list from the current season")
    sync_p.set_defaults(func=cmd_config_sync_roster)

    history_p = sub.add_parser("history", help="Manage wallpaper history")
    history_sub = history_p.add_subparsers(dest="history_command", required=True)
    history_clear_p = history_sub.add_parser("clear", help="Clear recently-used image history")
    history_clear_p.set_defaults(func=cmd_history_clear)

    install_p = sub.add_parser("install-schedule", help="Install an OS-level recurring schedule")
    install_p.add_argument("--time", default="09:00", help="Daily run time, HH:MM (default 09:00)")
    install_p.set_defaults(func=cmd_install_schedule)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
