"""Best-effort filesystem permission hardening.

Restricts sensitive files/dirs (credentials, telemetry output) to the current
user. Always best-effort — a failure here must never break a hunt, so every
call swallows errors.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def restrict_file(path: Path) -> None:
    """Make a file readable/writable by the owner only (POSIX 600 / Win owner-full)."""
    _restrict(path, is_dir=False)


def restrict_dir(path: Path) -> None:
    """Make a directory accessible by the owner only (POSIX 700 / Win owner-full)."""
    _restrict(path, is_dir=True)


def _restrict(path: Path, is_dir: bool) -> None:
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
            if not user:
                return
            grant = f"{user}:(OI)(CI)F" if is_dir else f"{user}:F"
            # /inheritance:r removes inherited ACEs; /grant:r replaces the user's ACE.
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", grant],
                capture_output=True, check=False,
            )
        else:
            os.chmod(path, 0o700 if is_dir else 0o600)
    except Exception:
        pass  # hardening is best-effort; never break the caller
