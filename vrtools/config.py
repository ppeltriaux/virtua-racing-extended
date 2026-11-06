"""Locations of local game data, taken from environment variables.

Game data (ROM sets, disc images) is never part of the repository; every
consumer resolves it through these helpers so tests can skip cleanly when
the data is absent.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def rom_dir() -> Path | None:
    """Directory holding vr.zip, model1io.zip and m1comm.zip (VR_ROMDIR)."""
    return _env_path("VR_ROMDIR")


def saturn_cue() -> Path | None:
    """Path to the Saturn 'Virtua Racing (Europe).cue' (VR_SATURN_CUE)."""
    return _env_path("VR_SATURN_CUE")


def out_dir() -> Path:
    """Scratch output directory (VR_OUT, default <repo>/out); created on demand."""
    d = _env_path("VR_OUT") or REPO_ROOT / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d
