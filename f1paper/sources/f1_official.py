"""Scrape formula1.com 'GALLERY' / 'In pictures' articles for the current race weekend.

Formula1.com does not expose a public photo API; galleries are regular HTML
articles with a sequence of images whose captions name the drivers/teams
pictured (e.g. "Lewis Hamilton (GBR) Mercedes AMG F1 ... Sunday 19 April 2015").

This scraper is inherently best-effort: formula1.com can change its page
markup at any time. The selectors below target the common patterns observed
on the site (article body images with figcaption/alt text) and are written
defensively (several fallbacks, never raises on a single bad article) so a
markup change degrades results instead of crashing the whole run.
"""
from __future__ import annotations

import logging
import re
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from f1paper.config import AppConfig
from f1paper.schedule import RaceWeekend, Roster, match_roster_in_text
from f1paper.sources.base import Candidate

logger = logging.getLogger(__name__)

BASE_URL = "https://www.formula1.com"
LATEST_LISTING_URLS = [
    f"{BASE_URL}/en/latest/all",
    f"{BASE_URL}/en/latest/all.html",
]
GALLERY_HINT_RE = re.compile(r"gallery|in pictures|best images|best photos", re.IGNORECASE)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; f1paper/0.1.0; personal wallpaper tool)"}


def _find_gallery_article_links(session: requests.Session, weekend: RaceWeekend) -> List[str]:
    keywords = [weekend.race_name, weekend.country, weekend.circuit_name]
    keywords = [k for k in keywords if k]
    links: List[str] = []

    for listing_url in LATEST_LISTING_URLS:
        try:
            resp = session.get(listing_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("f1_official: failed to fetch listing %s (%s)", listing_url, exc)
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if not text or not GALLERY_HINT_RE.search(text):
                continue
            if keywords and not any(k.lower() in text.lower() for k in keywords):
                continue
            links.append(urljoin(BASE_URL, a["href"]))

        if links:
            break

    # de-dup while preserving order
    seen = set()
    unique_links = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)
    return unique_links


def _best_src_from_img(img) -> str | None:
    srcset = img.get("srcset") or img.get("data-srcset")
    if srcset:
        # srcset entries look like "url 640w, url 1280w, ..."; take the widest.
        candidates = []
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            bits = part.split()
            url = bits[0]
            width = 0
            if len(bits) > 1 and bits[1].endswith("w"):
                try:
                    width = int(bits[1][:-1])
                except ValueError:
                    width = 0
            candidates.append((width, url))
        if candidates:
            return max(candidates, key=lambda c: c[0])[1]
    return img.get("src") or img.get("data-src")


def _parse_gallery_article(session: requests.Session, url: str, roster: Roster) -> List[Candidate]:
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("f1_official: failed to fetch article %s (%s)", url, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    candidates: List[Candidate] = []

    # Prefer <figure><img/><figcaption> structures; fall back to any <img> with
    # a reasonably long alt text (F1 embeds full photo credit captions in alt).
    figures = soup.find_all("figure")
    containers = figures if figures else soup.find_all("img")

    for node in containers:
        img = node if node.name == "img" else node.find("img")
        if img is None:
            continue
        src = _best_src_from_img(img)
        if not src:
            continue
        src = urljoin(url, src)

        caption = ""
        figcaption = node.find("figcaption") if node.name == "figure" else None
        if figcaption:
            caption = figcaption.get_text(" ", strip=True)
        if not caption:
            caption = img.get("alt", "") or ""
        if not caption or len(caption) < 10:
            # Too little context to attribute this image to a team/driver; skip.
            continue

        teams, drivers = match_roster_in_text(caption, roster)
        candidates.append(
            Candidate(url=src, source="f1_official", teams=teams, drivers=drivers, caption=caption)
        )

    return candidates


def fetch(weekend: RaceWeekend, roster: Roster, config: AppConfig) -> List[Candidate]:
    session = requests.Session()
    article_links = _find_gallery_article_links(session, weekend)
    if not article_links:
        logger.info("f1_official: no gallery articles found for %s", weekend.race_name)
        return []

    candidates: List[Candidate] = []
    for link in article_links[:10]:
        candidates.extend(_parse_gallery_article(session, link, roster))
    return candidates


name = "f1_official"
