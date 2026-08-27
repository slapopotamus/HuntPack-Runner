"""Single source of truth for CrowdStrike Falcon regions.

Both the API client (``src/falcon_client.py``) and the interactive configurator
(``configure.py``) import from here so the region → host mapping is defined once.
"""
from __future__ import annotations

# Friendly region name -> Falcon API base URL.
REGIONS: dict[str, str] = {
    "us-1": "https://api.crowdstrike.com",
    "us-2": "https://api.us-2.crowdstrike.com",
    "eu-1": "https://api.eu-1.crowdstrike.com",
    "us-gov-1": "https://api.laggar.gcw.crowdstrike.com",
    "us-gov-2": "https://api.us-gov-2.crowdstrike.mil",
}


def base_url(region: str) -> str:
    """Return the API base URL for a region, or raise ValueError if unknown.

    This is the guard that stops a poisoned config/`--region` from redirecting
    credentials to an arbitrary host."""
    try:
        return REGIONS[region]
    except KeyError:
        raise ValueError(
            f"Unknown region '{region}'. Valid regions: {', '.join(REGIONS)}"
        ) from None


def host(region: str) -> str:
    """The bare API host for display, e.g. 'api.us-2.crowdstrike.com'."""
    return REGIONS[region].removeprefix("https://")


def menu() -> list[tuple[str, str]]:
    """(region, host) pairs for the configurator's selection menu."""
    return [(name, url.removeprefix("https://")) for name, url in REGIONS.items()]


def names() -> list[str]:
    return list(REGIONS)
