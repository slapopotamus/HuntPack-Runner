"""Resolve CQL-Hub queries from the ByteRay-Labs/Query-Hub GitHub repo.

Mirrors the huntpack_source interface (LIBRARY_URL / list_library /
list_library_by_date / download_to) so the runner can treat CQL-Hub as an
interchangeable source via `--source cqlhub`.

Discovery uses the GitHub contents API (one request, returns the file list with
per-file download URLs). Downloads use those raw.githubusercontent URLs, which
are served from a CDN and are not subject to the API's hourly rate limit.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests

from .huntpack_source import LibraryEntry, fetch_text

LIBRARY_URL = "https://github.com/ByteRay-Labs/Query-Hub"
CONTENTS_API = "https://api.github.com/repos/ByteRay-Labs/Query-Hub/contents/queries"
_HEADERS = {"User-Agent": "HuntPackRunner/1.0", "Accept": "application/vnd.github+json"}
_TIMEOUT = 30


def _pretty(stem: str) -> str:
    return stem.replace("_", " ").strip()


def list_library(base_url: str = CONTENTS_API) -> list[LibraryEntry]:
    """Catalog of CQL-Hub queries, alphabetical (the repo has no dates)."""
    resp = requests.get(base_url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    entries: list[LibraryEntry] = []
    for item in resp.json():
        name = item.get("name", "")
        if item.get("type") == "file" and name.lower().endswith((".yml", ".yaml")):
            url = item.get("download_url") or ""
            if url:
                entries.append(LibraryEntry(title=_pretty(Path(name).stem),
                                            url=url, published="", category="cqlhub"))
    entries.sort(key=lambda e: e.title.lower())
    return entries


def list_library_by_date(feed_url: str = CONTENTS_API) -> list[LibraryEntry]:
    # No publish dates in the repo; alphabetical is the stable ordering.
    return list_library(feed_url)


def download_to(url: str, dest_dir: Path) -> Path:
    """Download a CQL-Hub .yml into dest_dir, returning the local path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(url).path).name or "query.yml"
    if not name.lower().endswith((".yml", ".yaml")):
        name += ".yml"
    dest = dest_dir / name
    dest.write_text(fetch_text(url), encoding="utf-8")
    return dest


if __name__ == "__main__":  # python -m src.cqlhub_source  -> print the catalog
    for e in list_library():
        print(f"{e.title}\n    {e.url}")
