"""Phase 90 fix round 1 (I7): the two packs built FROM THE TREE once a session, shared by the gated tests that race them
(tests/test_pack_rate.py, tests/test_pack_mame.py, tests/test_pack_gates.py). Each is built at its first use into a folder of the
session's temporary directory and kept for the session; a failed build is kept too (its error raised again, not built twice).
Fix round 1b: `weather=False` builds the pack without the weather (`--no-weather`), a set of its own (the DRY identity gate).
Fix round 1c: `tunes` (a weather.tune.Tunes) with `tag` builds the pack with those weather tunes (the flash rule's stress build), a
set of its own; every build's storm layout (the carrier.Layout its weather was laid out with) is kept for `layout`."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

_SETS: dict[str, Path | BaseException] = {}
_LAYOUTS: dict[str, object] = {}
_LOCK = threading.Lock()                 # one build at a time (the layout's recorder is the module's)


@contextmanager
def _layouts():
    """The carrier.Layout of each storm laid out while it is open (`carrier.lay_out` wrapped, its result unchanged)."""
    from vrtools.arcade.weather import carrier
    seen, real = [], carrier.lay_out

    def recorded(*a, **k):
        got = real(*a, **k)
        seen.append(got[0])
        return got
    carrier.lay_out = recorded
    try:
        yield seen
    finally:
        carrier.lay_out = real


def built(name: str, romset_zip: Path, tmp_path_factory, saturn_cue: Path | None = None, ps2_disc: Path | None = None,
          weather: bool = True, tunes=None, tag: str = "") -> Path:
    """The folder holding pack `name`'s vr.zip ("saturn": `cli.build` with the Saturn disc; "ps2": `cli.build_pack_set` with the
    PS2 disc; `weather` False: without the weather, as --no-weather; `tunes` with `tag`: with those weather tunes (pack 2 only)),
    built at the first call of the session."""
    key = _key(name, weather, tag)
    if tunes is not None and (not tag or name == "saturn"):
        raise ValueError("a tuned build is pack 2's and needs a tag naming it")
    with _LOCK:
        if key not in _SETS:
            _build(key, name, romset_zip, tmp_path_factory, saturn_cue, ps2_disc, weather, tunes)
    got = _SETS[key]
    if isinstance(got, BaseException):
        raise got
    return got


def _build(key, name, romset_zip, tmp_path_factory, saturn_cue, ps2_disc, weather, tunes) -> None:
    """Builds variant `key` into a new folder; `_SETS[key]` its folder or its error (raised)."""
    from vrtools import cli
    out = tmp_path_factory.mktemp(f"pack_{key}")
    try:
        with _layouts() as lays:
            rc = cli.build(romset_zip.parent, saturn_cue, out, weather=weather) if name == "saturn" else \
                cli.build_pack_set(romset_zip.parent, None, out, name, Path(ps2_disc), weather=weather, weather_tunes=tunes)
        _LAYOUTS[key] = lays[-1] if len(lays) == 1 else None
        if rc != 0:
            raise AssertionError(f"pack {key}: the build returned {rc} (see {out})")
        _SETS[key] = out
    except BaseException as e:                     # kept: every later test gets the same failure
        _SETS[key] = e
        raise


def _key(name: str, weather: bool = True, tag: str = "") -> str:
    return (name if weather else f"{name}_dry") + (f"_{tag}" if tag else "")


def layout(name: str, weather: bool = True, tag: str = ""):
    """The storm layout (carrier.Layout) the session's build of that variant laid its weather out with (built first by `built`);
    AssertionError when it was not laid out exactly once."""
    lay = _LAYOUTS.get(_key(name, weather, tag))
    assert lay is not None, (_key(name, weather, tag), "no single storm layout recorded for this build")
    return lay
