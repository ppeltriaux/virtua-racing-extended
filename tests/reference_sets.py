"""The reference sets: built sets kept outside the repository that some gates compare this tree's build with (the final review's
W2). One behaviour for all of them: `reference_set(var)` returns the directory the environment variable `var` names when it holds
a vr.zip; otherwise the gate SKIPS, with a reason that names the variable, what the set is and how it is built. With
VR_REQUIRE_REFERENCE_SETS=1 (our own release runs) a missing reference set FAILS instead. README.md's test section and
local.env.example list them."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REQUIRE = "VR_REQUIRE_REFERENCE_SETS"
# variable: (what it is, how it is built)
REFERENCE_SETS = {
    "VR_PRE_WEATHER_SET": ("main's set before the weather (the released v0.3's game)",
                           "`python -m vrtools build` from a checkout of main at the weather branch's base (tag v0.3)"),
    "VR_RELEASED_SET": ("main's released set (v0.3)", "`python -m vrtools build` from a checkout of tag v0.3 (the same set as "
                        "VR_PRE_WEATHER_SET)"),
    "VR_P75_SET": ("the owner's approved joined storm prototype (out/p75storm, spike 75)",
                   "LOCAL ONLY: a throwaway spike build kept on the owner's machine; nobody else can rebuild it"),
    "VR_MAIN_SET": ("main without Phase 32 (Phases 29 and 31 merged, add9799)", "`python -m vrtools build` from a checkout of add9799"),
    "VR_V04_SET": ("the released v0.4's set (its falling rain: the streaming rain's tests compare their fill and splash rate with it)",
                   "`python -m vrtools build` from a checkout of v0.4's source, 19ac53c (main at 8798404 builds the same set)"),
}


def reference_set(var: str) -> Path:
    """The reference set `var` names (a directory holding vr.zip), else skip (fail under VR_REQUIRE_REFERENCE_SETS=1) saying why."""
    what, built = REFERENCE_SETS[var]
    value = os.environ.get(var)
    path = Path(value) if value else None
    if path is not None and (path / "vr.zip").is_file():
        return path
    why = f"{var} is not set" if path is None else f"{var}={path} holds no vr.zip"
    msg = f"{why}: {what}; built by {built}"
    if os.environ.get(REQUIRE) == "1":
        pytest.fail(f"{msg} ({REQUIRE}=1: a missing reference set fails)", pytrace=False)
    pytest.skip(msg)
