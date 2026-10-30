"""Cross-platform desktop wallpaper setter (Windows + Linux)."""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class WallpaperError(RuntimeError):
    pass


def _set_windows(path: Path) -> None:
    import ctypes

    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02

    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, str(path), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    )
    if not ok:
        raise WallpaperError("SystemParametersInfoW failed to set the wallpaper")


def _set_linux(path: Path) -> None:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    uri = path.resolve().as_uri()

    gnome_family = ("gnome", "unity", "cinnamon", "budgie", "pantheon")
    if any(d in desktop for d in gnome_family):
        base = ["gsettings", "set", "org.gnome.desktop.background"]
        subprocess.run(base + ["picture-uri", uri], check=True)
        subprocess.run(base + ["picture-uri-dark", uri], check=False)
        subprocess.run(base + ["picture-options", "zoom"], check=False)
        return

    if "kde" in desktop:
        try:
            subprocess.run(["plasma-apply-wallpaperimage", str(path.resolve())], check=True)
            return
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            logger.warning("wallpaper: plasma-apply-wallpaperimage failed (%s), trying feh", exc)

    if "xfce" in desktop:
        try:
            subprocess.run(
                [
                    "xfconf-query",
                    "-c",
                    "xfce4-desktop",
                    "-p",
                    "/backdrop/screen0/monitor0/workspace0/last-image",
                    "-s",
                    str(path.resolve()),
                ],
                check=True,
            )
            return
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            logger.warning("wallpaper: xfconf-query failed (%s), trying feh", exc)

    try:
        subprocess.run(["feh", "--bg-fill", str(path.resolve())], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise WallpaperError(
            f"Could not set wallpaper for desktop '{desktop or 'unknown'}'; "
            "install 'feh' as a fallback or add support for your desktop environment."
        ) from exc


def set_wallpaper(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        raise WallpaperError(f"Wallpaper image does not exist: {path}")

    system = platform.system()
    if system == "Windows":
        _set_windows(path)
    elif system == "Linux":
        _set_linux(path)
    else:
        raise WallpaperError(f"Unsupported platform: {system}")
