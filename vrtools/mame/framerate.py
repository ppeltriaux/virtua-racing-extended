"""Phase 28: the arcade's rate, as three measures (docs/spike/2026-11-phase28-polygons-recon.md §2.1).

The game draws one picture and runs one logic step every second screen frame (the Model 1 screen is 57.52 Hz: 28.76 pictures a
second); "holding the arcade's rate" means every logic frame keeps that two-vblank cadence. It is measured three ways:
- the game's own overrun counter 0x501148 (incremented at 0xfe13fe when a frame's work took more than two vblanks): it never
  moves. It is the exact detector: one increment per picture lost. (It has a second writer, the debug routine at 0xfe03cf, run
  only with bit 5 of 0x501120 set; if it ever ran, a test would fail with nothing wrong, it cannot hide a lost picture.)
- the V60's busy time per logic frame (frame_rate.lua), under FRAME_US (two vblanks);
- the render rate: display-list switches per 57 screen frames (renderrate.lua), RATE_BOUNDS once the race is under way. It
  checks that pictures keep coming; it does not see every single lost picture: the windows do not overlap and alternate 28 and
  29 (57 is odd), so one lost picture in a 29-window reads 28 and passes (about half the positions); the counter catches it.
`arcade_rate_misses` lists every breach of the three in a stretch of a run; tests/test_frame_rate.py asserts it is empty.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

RATE_BOUNDS = (28, 29)                 # switches per 57 frames: one per two frames, 28.5 on average
RATE_WINDOW = 57                       # renderrate.lua's window, in screen frames
FRAME_US = 34_770                      # two vblanks at 57.52 Hz, in microseconds


class FrameSample(NamedTuple):
    frame: int          # MAME frame (from 1) at which the pass's wait was left
    busy_us: int        # the V60's work in that pass, emulated microseconds
    overrun: int        # 0x501148 at the pass's end
    records: int        # the frame's record count peak (0x5011a0)
    skipped: int        # object lists skipped (entered with the count above the budget)
    budget: int         # 0x5011b0
    need: int           # the least budget under which the frame skips no list (the highest count the walker compared)


def parse_frame_log(path: Path) -> list[FrameSample]:
    """F lines from frame_rate.lua; other and incomplete lines are skipped."""
    out = []
    for line in open(path):
        p = line.split()
        if p and p[0] == "F" and len(p) == 8:
            out.append(FrameSample(*(int(v) for v in p[1:])))
    return out


def arcade_rate_misses(frames: list[FrameSample], rate: list[tuple[int, int]], start: int, end: int | None = None,
                       rate_from: int | None = None, excused: frozenset[int] | set[int] = frozenset()) -> list[str]:
    """Every breach of the arcade's rate in the frames [start, end) (end None: to the run's end), one message each:
    - a logic frame whose busy time is FRAME_US or more, unless its frame is in `excused` (the attract's scene loads, which take
      that long on main's set too: `scene_loads` of main's run);
    - the overrun counter at any logic frame differing from its value at the first logic frame of the stretch;
    - a render-rate window (`rate`: (frame, switches in the 57 frames up to it), renderrate.lua) lying wholly inside
      [rate_from, end) (rate_from None: `start`) whose count is outside RATE_BOUNDS.
    An empty stretch (no logic frame, or no whole rate window) is itself a miss: a run that measured nothing passes nothing."""
    stop = end if end is not None else float("inf")
    rf = start if rate_from is None else rate_from
    fs = [f for f in frames if start <= f.frame < stop]
    ws = [(fr, n) for fr, n in rate if fr - RATE_WINDOW >= rf and fr < stop]
    misses = []
    if not fs:
        misses.append(f"no logic frame logged in [{start}, {end})")
    if not ws:
        misses.append(f"no whole render-rate window in [{rf}, {end})")
    for f in fs:
        if f.busy_us >= FRAME_US and f.frame not in excused:
            misses.append(f"frame {f.frame}: V60 busy {f.busy_us} us (two vblanks are {FRAME_US})")
    if fs:
        base = fs[0].overrun
        moved = [f for f in fs if f.overrun != base]
        if moved:
            misses.append(f"frame {moved[0].frame}: overrun counter 0x501148 {base} -> {moved[0].overrun}")
    lo, hi = RATE_BOUNDS
    for fr, n in ws:
        if not lo <= n <= hi:
            misses.append(f"render rate {n} in the 57 frames to {fr} (arcade: {lo}-{hi})")
    return misses


def worst_busy(frames: list[FrameSample], start: int, end: int | None = None,
               excused: frozenset[int] | set[int] = frozenset()) -> FrameSample:
    """The logic frame of [start, end), its frame not in `excused`, with the highest busy time."""
    stop = end if end is not None else float("inf")
    return max((f for f in frames if start <= f.frame < stop and f.frame not in excused), key=lambda f: f.busy_us)


def scene_loads(frames: list[FrameSample]) -> set[int]:
    """The frames of the passes of FRAME_US or more in a run: on main's set in the attract, its scene changes' loads (one pass of
    41-52 ms each, the overrun counter still), which the same frames of another set's run are excused."""
    return {f.frame for f in frames if f.busy_us >= FRAME_US}


def parse_pass_log(path: Path) -> list[str]:
    """W lines from pass_state.lua (the game's state at the end of every logic pass), as text: two runs of the same race compare
    line for line."""
    return [line.rstrip("\n") for line in open(path) if line.startswith("W ")]
