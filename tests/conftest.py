from pathlib import Path

import pytest

from vrtools import config


@pytest.fixture
def romset_zip() -> Path:
    d = config.rom_dir()
    if d is None or not (d / "vr.zip").is_file():
        pytest.skip("set VR_ROMDIR to a directory containing vr.zip")
    return d / "vr.zip"


@pytest.fixture
def saturn_cue() -> Path:
    p = config.saturn_cue()
    if p is None or not p.is_file():
        pytest.skip("set VR_SATURN_CUE to the Saturn disc .cue")
    return p
