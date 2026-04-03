"""Self-update logic for linear CLI.

Follows Forma Protocol section 23 — Self-Update.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_latest_tag(repo_dir: str) -> str | None:
    """Get latest version tag from local git repo's remote."""
    result = subprocess.run(
        ["git", "-C", repo_dir, "ls-remote", "--tags", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    tags = []
    for line in result.stdout.strip().splitlines():
        if "refs/tags/" not in line:
            continue
        ref = line.split("refs/tags/")[-1].lstrip("v")
        if ref and not ref.endswith("^{}"):
            try:
                _version_tuple(ref)  # validate it's a numeric version
                tags.append(ref)
            except ValueError:
                pass
    return sorted(tags, key=_version_tuple)[-1] if tags else None


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def version_gt(a: str, b: str) -> bool:
    """Return True if version a is greater than version b."""
    try:
        return _version_tuple(a) > _version_tuple(b)
    except ValueError:
        return False


def do_update(tool_dir: str) -> bool:
    """Pull latest, re-lock, and reinstall via lockfile."""
    pull = subprocess.run(
        ["git", "-C", tool_dir, "pull", "--ff-only"],
        capture_output=True,
        text=True,
    )
    if pull.returncode != 0:
        return False
    lock = subprocess.run(
        ["uv", "lock", "--directory", tool_dir],
        capture_output=True,
        text=True,
    )
    if lock.returncode != 0:
        return False
    install = subprocess.run(
        ["uv", "sync", "--frozen", "--directory", tool_dir],
        capture_output=True,
        text=True,
    )
    return install.returncode == 0


def find_tool_dir() -> str:
    """Return the root of the git repo containing this file."""
    result = subprocess.run(
        ["git", "-C", str(Path(__file__).parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    # Fallback: two levels up from this file (src/linear_cli/update.py -> repo root)
    return str(Path(__file__).parent.parent.parent)
