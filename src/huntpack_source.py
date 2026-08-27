"""Resolve HuntPacks from either a local path or the online HuntPack library.

Local:  a .html file or a directory of them (current behaviour).
Remote: any hunt URL under https://slapopotamus.github.io/HuntPack/hunts/...,
        downloaded into huntpacks/ so a local copy is kept, then parsed.

``list_library()`` scrapes the library index page for the full hunt catalog.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import defusedxml.ElementTree as ET  # hardened parser: blocks entity-expansion / XXE
import requests
from bs4 import BeautifulSoup

LIBRARY_URL = "https://slapopotamus.github.io/HuntPack/"
FEED_URL = "https://slapopotamus.github.io/HuntPack/feed.xml"
_ATOM = "{http://www.w3.org/2005/Atom}"
_HEADERS = {"User-Agent": "HuntPackRunner/1.0"}
_TIMEOUT = 30


@dataclass
class LibraryEntry:
    title: str
    url: str
    published: str = ""   # ISO date, e.g. "2026-07-08" ("" if unknown)
    category: str = ""


def is_url(target: str | Path) -> bool:
    return str(target).lower().startswith(("http://", "https://"))


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def list_library_by_date(feed_url: str = FEED_URL) -> list[LibraryEntry]:
    """Return every hunt from the Atom feed, newest 'published' date first.

    ISO-8601 dates sort lexicographically == chronologically; the sort is
    stable, so hunts sharing a date keep the feed's own order."""
    root = ET.fromstring(fetch_text(feed_url))
    entries: list[LibraryEntry] = []
    for e in root.findall(f"{_ATOM}entry"):
        url = ""
        for link in e.findall(f"{_ATOM}link"):
            if link.get("rel", "alternate") == "alternate" and link.get("href"):
                url = link.get("href", "")
                break
        if not url:
            continue
        title = (e.findtext(f"{_ATOM}title") or "").strip()
        published = (e.findtext(f"{_ATOM}published")
                     or e.findtext(f"{_ATOM}updated") or "").strip()[:10]
        cat_el = e.find(f"{_ATOM}category")
        category = cat_el.get("term", "") if cat_el is not None else ""
        entries.append(LibraryEntry(title or Path(urlparse(url).path).stem,
                                     url, published, category))
    entries.sort(key=lambda e: e.published, reverse=True)
    return entries


def list_library(base_url: str = LIBRARY_URL) -> list[LibraryEntry]:
    """Fallback catalog from scraping the index page (alphabetical, no dates)."""
    soup = BeautifulSoup(fetch_text(base_url), "html.parser")
    found: dict[str, str] = {}  # url -> title
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "hunts/" in href and href.lower().endswith(".html"):
            url = urljoin(base_url, href)
            title = a.get_text(strip=True) or Path(urlparse(url).path).stem
            found.setdefault(url, title)
    entries = [LibraryEntry(t, u) for u, t in found.items()]
    entries.sort(key=lambda e: e.title.lower())
    return entries


def download_to(url: str, dest_dir: Path) -> Path:
    """Download a hunt HTML into dest_dir, returning the local path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(url).path).name or "huntpack.html"
    if not name.lower().endswith(".html"):
        name += ".html"
    dest = dest_dir / name
    dest.write_text(fetch_text(url), encoding="utf-8")
    return dest


if __name__ == "__main__":  # python -m src.huntpack_source  -> print the catalog
    for e in list_library_by_date():
        print(f"{e.published}  {e.title}\n    {e.url}")
