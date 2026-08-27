#!/usr/bin/env python3
"""Interactive configuration for the HuntPack-Runner.

Collects your CrowdStrike API credentials and Falcon region, then writes them
to the right files — telling you exactly where each value goes:

  * Client ID / Secret  ->  .env
  * Region              ->  config.yaml

Safe to re-run any time to update them. Called automatically by setup.bat, or
run directly:  python configure.py
"""
from __future__ import annotations

import re
import sys
from getpass import getpass
from pathlib import Path

from src.regions import menu as region_menu
from src.secure_io import restrict_file

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
CONFIG = ROOT / "config.yaml"

REGIONS = region_menu()   # [(name, host), ...] — single source of truth in src/regions.py

ENV_TEMPLATE = """\
# CrowdStrike Falcon API credentials for the HuntPack-Runner.
# Written by configure.py. Keep this private — never commit or share it.
# API client scope required: NGSIEM search (Read & Write).

FALCON_CLIENT_ID={client_id}
FALCON_CLIENT_SECRET={client_secret}

# Optional overrides (region normally lives in config.yaml):
# FALCON_REGION={region}
# FALCON_REPOSITORY=search-all
"""


def mask(s: str) -> str:
    s = s.strip()
    return "*" * len(s) if len(s) <= 6 else f"{s[:3]}{'*' * (len(s) - 6)}{s[-3:]}"


def prompt_nonempty(label: str) -> str:
    while True:
        v = input(label).strip()
        if v:
            return v
        print("     (required — please enter a value)")


def current_region() -> str | None:
    if CONFIG.exists():
        m = re.search(r"(?m)^\s*region\s*:\s*(\S+)", CONFIG.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return None


def choose_region(current: str | None) -> str:
    print("\n  Select your Falcon cloud / region:")
    default_idx = 1
    for i, (name, host) in enumerate(REGIONS, 1):
        if current == name:
            default_idx = i
        marker = "  <- current" if current == name else ""
        print(f"     {i}) {name:<9} ({host}){marker}")
    while True:
        raw = input(f"  Choice [{default_idx}]: ").strip()
        if not raw:
            return REGIONS[default_idx - 1][0]
        if raw.isdigit() and 1 <= int(raw) <= len(REGIONS):
            return REGIONS[int(raw) - 1][0]
        for name, _ in REGIONS:
            if raw.lower() == name:
                return name
        print("     (enter a number 1-5, or a region name like us-2)")


def set_region(region: str) -> None:
    if CONFIG.exists():
        txt = CONFIG.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s*region\s*:", txt):
            txt = re.sub(r"(?m)^(\s*region\s*:\s*)\S+(.*)$",
                         rf"\g<1>{region}\g<2>", txt, count=1)
        else:
            txt = f"region: {region}\n" + txt
        CONFIG.write_text(txt, encoding="utf-8")
    else:
        CONFIG.write_text(f"region: {region}\nrepository: search-all\n", encoding="utf-8")


def main() -> int:
    print("=" * 60)
    print(" HuntPack-Runner — configuration")
    print("=" * 60)

    write_creds = True
    if ENV.exists():
        print(f"\n  Credentials already exist at:\n    {ENV}")
        write_creds = input("  Overwrite them? [y/N]: ").strip().lower() in ("y", "yes")

    if write_creds:
        print("\n  Enter your CrowdStrike API credentials.")
        print("  (Falcon console -> Support and resources -> API clients and keys;")
        print("   scope: NGSIEM search, Read & Write.)")
        cid = prompt_nonempty("  Client ID: ")
        secret = getpass("  Client Secret (hidden while typing): ").strip()
        while not secret:
            secret = getpass("  (required) Client Secret: ").strip()
        region = choose_region(current_region())
        ENV.write_text(
            ENV_TEMPLATE.format(client_id=cid, client_secret=secret, region=region),
            encoding="utf-8",
        )
        restrict_file(ENV)   # owner-only perms on the credentials file
        set_region(region)
        print("\n  Saved:")
        print(f"    Client ID      -> {ENV}   [{mask(cid)}]")
        print(f"    Client Secret  -> {ENV}   [{mask(secret)}]")
        print(f"    Region ({region})  -> {CONFIG}")
        print("    (.env locked to your user account)")
    else:
        region = choose_region(current_region())
        set_region(region)
        print(f"\n  Region set to '{region}' in {CONFIG}. Credentials left unchanged.")

    print("\n  Done. Try it:")
    print("     python run_hunt.py --list-remote")
    print("     python run_hunt.py --latest 1 --start 24h")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n  Cancelled.")
        raise SystemExit(1)
