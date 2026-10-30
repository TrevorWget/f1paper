"""Download candidate images, verify their real pixel dimensions, compute a
perceptual hash for dedup, and cover-fit crop/resize the chosen image."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import imagehash
import requests
from PIL import Image, UnidentifiedImageError

from f1paper.sources.base import Candidate

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 20
MAX_IMAGE_BYTES = 30 * 1024 * 1024  # 30 MB safety cap


@dataclass
class DownloadedImage:
    candidate: Candidate
    path: Path
    width: int
    height: int
    phash: imagehash.ImageHash


def _cache_filename(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    suffix = Path(url.split("?")[0]).suffix or ".jpg"
    return cache_dir / f"candidate_{digest}{suffix}"


def download_candidate(
    candidate: Candidate, cache_dir: Path, session: Optional[requests.Session] = None
) -> Optional[DownloadedImage]:
    session = session or requests.Session()
    dest = _cache_filename(cache_dir, candidate.url)

    try:
        if not dest.exists():
            resp = session.get(candidate.url, timeout=DOWNLOAD_TIMEOUT, stream=True)
            resp.raise_for_status()
            content_length = int(resp.headers.get("Content-Length", 0) or 0)
            if content_length and content_length > MAX_IMAGE_BYTES:
                logger.warning("image_proc: skipping %s, too large (%d bytes)", candidate.url, content_length)
                return None
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as fh:
                written = 0
                for chunk in resp.iter_content(chunk_size=65536):
                    written += len(chunk)
                    if written > MAX_IMAGE_BYTES:
                        logger.warning("image_proc: aborting %s, exceeded size cap", candidate.url)
                        dest.unlink(missing_ok=True)
                        return None
                    fh.write(chunk)

        with Image.open(dest) as img:
            img.verify()
        with Image.open(dest) as img:
            width, height = img.size
            phash = imagehash.phash(img.convert("RGB"))

        return DownloadedImage(candidate=candidate, path=dest, width=width, height=height, phash=phash)

    except (requests.RequestException, UnidentifiedImageError, OSError) as exc:
        logger.warning("image_proc: failed to download/verify %s (%s)", candidate.url, exc)
        dest.unlink(missing_ok=True)
        return None


def download_candidates(
    candidates: List[Candidate], cache_dir: Path
) -> List[DownloadedImage]:
    session = requests.Session()
    downloaded: List[DownloadedImage] = []
    for candidate in candidates:
        result = download_candidate(candidate, cache_dir, session)
        if result:
            downloaded.append(result)
    return downloaded


def crop_resize_cover(image_path: Path, target_w: int, target_h: int) -> Image.Image:
    """Scale + center-crop the image so it exactly fills target_w x target_h
    with no letterboxing (standard 'cover' fit)."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        src_w, src_h = img.size
        scale = max(target_w / src_w, target_h / src_h)
        new_w, new_h = round(src_w * scale), round(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))
        return img.copy()
