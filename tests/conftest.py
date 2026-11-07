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


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """A fresh clone has no build/mame/unidasm (tools/build-mame.sh builds it): a test that needs it skips with that
    command instead of failing. Only the 'not found' error skips; any other disassembly error still fails."""
    outcome = yield
    rep = outcome.get_result()
    exc = call.excinfo
    if exc is not None and rep.failed and "unidasm not found" in str(exc.value):
        rep.outcome = "skipped"
        rep.longrepr = (str(item.path), item.location[1] or 0, "Skipped: needs unidasm, run tools/build-mame.sh")
