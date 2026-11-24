"""The arcade's rate on every course (Phase 28's standing test, for every later addition of scenery), and the draw budget's effect.

The game draws one picture and runs one logic step every second screen frame (57.52 Hz: 28.76 pictures a second). Holding that
cadence on every frame is the arcade's rate; it is measured three ways (`vrtools.mame.framerate`, the Phase 28 recon's §2.1):
- the game's own overrun counter 0x501148 (incremented at 0xfe13fe when a frame's work took more than two vblanks): it never
  moves, from the pass after the course load to the end of the race. It is the per-picture detector: one lost picture, one
  increment;
- the V60's busy time per logic frame (frame_rate.lua): under FRAME_US (34 770 us, two vblanks) over the same stretch; the worst
  is recorded (`record_property` "worst_busy_us" and the session's rate_summary.txt);
- the render rate, display-list switches per 57 screen frames (renderrate.lua): RATE_BOUNDS (28-29) in every window once the
  race is under way (from the green). It checks that pictures keep coming, not each picture: the windows alternate 28 and 29, and
  one lost picture in a 29-window reads 28 and passes (about half the positions); the counter catches that one.
The course load's own pass (the game builds the course in one pass of four vblanks or more, as the arcade does) is not counted.
The reference, main's tested set (out/p27play1): with the game's budget 28-29, 0 and at most 14.5 ms on every course (the recon's
14 runs); with the budget out of the way (every list drawn) 28-29, 0 and at most 14.6 ms in races, 18.0 ms in the attract
(docs/spike/2026-11-phase28-draw-budget-findings.md §5).
Phase 79: none of the three sees a stale display list (the rain spike's finding, out/p48/look/NOTE.txt): a pass whose work runs
past DEADLINE_MS (MAME's screen update after the wait) leaves the next pass rewriting the list just submitted, and every second
render shows the other, frozen list. The same three tests assert that no pass of their stretch wrote the list of the pass before
(`_stale`, stale_list.lua) and record the worst busy time against DEADLINE_MS in rate_summary.txt.

Each run: the session's ten-course set, the autopilot from the boot through the start with the full field and RATE_SECONDS in all
(about two laps), the race clock held (VR_HOLD_CLOCK, frame_rate.lua's harness switch) so the race does not time out. Besides the
20 races (Phase 33: the three originals in reverse too), the worst frames known (findings §13): Big Forest on road line 4 for WORST_SECONDS (9 704 records
in this run, booted on the session's battery RAM; the highest need known there, 9 886, is a line it does not sample), a lap through the pit lane on Big Forest and on Metropolis (a pit stop) and, in reverse, on Big Forest and on Acropolis, and the attract cycle for ATTRACT_SECONDS with
no input (the highest V60 busy time measured, 17 982 us). All runs of the module are made in parallel (three MAME processes) at
the first test that needs one; a replay waits for the run whose inputs it replays."""

import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from vrtools.arcade.budget import BUDGET_SITES, FRAME_BUDGET, IMM_OFFSET, ORIGINAL_BUDGET
from vrtools.arcade.course import course_entry_at, road_lines
from vrtools.arcade.directory import decode_directory
from vrtools.arcade.romset import V60_BOOT, RomSet
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.arcade.tencourse import COURSES as PLANS
from vrtools.convert.reverse import reverse_points
from vrtools.mame.framerate import (DEADLINE_MS, FRAME_US, RATE_BOUNDS, FrameSample, arcade_rate_misses, parse_frame_log,
                                    parse_pass_log, scene_loads, worst_busy)
from vrtools.mame.pitpaths import normal_pit_path, pit_lane
from vrtools.mame.runner import (LUA_DIR, PIT_HANDLER, parse_pit_log, parse_race_log, parse_rate, parse_stale_log, run_mame,
                                 write_centreline)

RATE_SECONDS = 150
SAME_SECONDS = 120
POKE_FRAME, POKE_ADDR = 2500, 0x400D00 + 0x280 * 3 + 0x1E    # J4's planted difference: car 3's x written 0.0 at that frame's end (its
                                                              # speed, +0x14, written 0 changed nothing: the game sets it each pass)
COURSES = [(e, False) for e in range(10)] + [(e, True) for e in range(10)]      # Phase 33: the three originals in reverse too
# Where the game's 5 500 cut lists (the recon's runs, §3): the originals' runs are the standing test's; the converted courses run
# again on the recon's autopilot lines (road line 0, Metropolis the AI lines' mean), which reach those frames: Diablo Canyon's start
# (road points 30-31), its reverse road point 178, Metropolis's start, Pacific Coast's road points 46 and 58.
CUT_BEFORE = [(0, False), (1, False), (2, False), (5, False), (5, True), (6, False), (7, False),
              (0, True), (1, True), (2, True)]         # Phase 33 fix wave (review I1): the three originals in reverse
RECON_LINE = {5: "line0", 6: "ai_mean", 7: "line0"}
SAME_RACE = (0, 2, 6)                                  # Big Forest, Acropolis and Metropolis
JOBS = 3
WORST_SECONDS = 300                                    # Big Forest line 4: 9 771 at frame 13 187 on no battery RAM until Phase 35
                                                       # (findings §3.1); 9 704 at frame 4 832 on the session's battery RAM
ATTRACT_SECONDS = 300
# The worst frames known (the review's I1): Big Forest on road line 4; a lap through the pit lane on an original (Big Forest) and on
# a converted course (Metropolis), each with a pit stop in the run.
# Phase 33: Big Forest in REVERSE on road line 1 read backwards, the highest need measured on any line of the three reverse
# originals (10 172 records at its reverse road point 42, the fairground; 328 under the budget: findings §7.2).
# Phase 33 stage 2: a REVERSE lap through the pit lane on Big Forest and on Acropolis, each with a pit stop in the run (the
# originals' reverse pit stop, with the checkpoint gantries' lettering from behind in the scene: 46 records more a gantry frame).
WORST = [("rate", 0, False, "line4"), ("pit", 0, False), ("pit", 6, False), ("rate", 0, True, "line1"), ("pit", 0, True), ("pit", 2, True)]
WORST_IDS = ["big_forest_line4", "big_forest_pit", "metropolis_pit", "big_forest_reverse_line1", "big_forest_reverse_pit",
             "acropolis_reverse_pit"]
# Review I1: the least margin under FRAME_BUDGET each worst run must keep (every run: 0, no list skipped). Big Forest in reverse
# on line 1 measured 10 172 of 10 500 (328 under) in stages 1 and 2 and in the fix wave; a floor of 300 fails the test when
# anything added to the reverse view eats a tenth of it. The reverse pit lap measures 448.
# Big Forest line 4: the need at its heavy stretch depends on the autopilot's exact line, and that line moves with any change of
# timing (the autopilot steers from samples grouped by MAME's frame end): on builds whose game is identical under the same inputs
# it measured 9 771 (no battery RAM, to Phase 35), 9 886 (no battery RAM after Phase 35's first-boot work), 9 704 (the session's
# battery RAM, Phase 79) and 9 791 (weather stage 2's set: its DRY switch test adds about 2 us a pass; fed the switch-off set's
# recorded inputs it needs 9 704, every pass identical); a RAIN race's line reached 10 302. A floor tighter than that spread is noise
# (Phase 79's 716, nine tenths of 796, was): 400, the run failing when line 4 needs more than 10 100, about 200 over the highest need
# a DRY line has shown (the session lead's ruling, weather stage 2's pre-review round).
MARGIN_FLOOR = {"big_forest_reverse_line1": 300, "big_forest_reverse_pit": 400, "big_forest_line4": 400}
# Big Forest's pit lap (the measurement's scratch path P0, findings §2): road line 0 with the pit lane's x (-226, beside the start
# line, where line 0 runs at -193) from road point 334 round to 29, blended in over the 12 points before and out over the 7 after.
BF_PIT_X, BF_LANE, BF_IN, BF_OUT = -226.0, (334, 29), 12, 7
LOADS_BEFORE_RACE = 2                                  # Phase 79: a race run's passes of two vblanks or more before its stretch
                                                       # on main's set (the boot's first attract scene at frame 275, the course load)
FINISH_STILL = 120                                     # frames of a still race clock after the green that mark the finish


# ---- the measure itself, on synthetic logs (no MAME): it passes a clean run and catches each kind of miss ----

def _clean(n=200, start=1000):
    frames = [FrameSample(start + 2 * i, 12_000, 0, 4000, 0, 5500, 3600) for i in range(n)]
    rate = [(start + 57 * k, 28 + k % 2) for k in range(1, (2 * n) // 57)]
    return frames, rate


def test_a_clean_log_has_no_miss():
    frames, rate = _clean()
    assert arcade_rate_misses(frames, rate, 1000) == []
    assert worst_busy(frames, 1000).busy_us == 12_000


def test_each_kind_of_miss_is_caught():
    """A render-rate window of 27 or of 30, a busy time of two vblanks, the overrun counter moving: each is a miss; a stretch that
    logged nothing is a miss too (a test that measured nothing does not pass)."""
    frames, rate = _clean()
    slow = [(f, 27 if i == 3 else n) for i, (f, n) in enumerate(rate)]
    fast = [(f, 30 if i == 4 else n) for i, (f, n) in enumerate(rate)]
    busy = [f._replace(busy_us=FRAME_US) if i == 50 else f for i, f in enumerate(frames)]
    over = [f._replace(overrun=1) if i >= 120 else f for i, f in enumerate(frames)]
    assert [m.split()[:3] for m in arcade_rate_misses(frames, slow, 1000)] == [["render", "rate", "27"]]
    assert [m.split()[:3] for m in arcade_rate_misses(frames, fast, 1000)] == [["render", "rate", "30"]]
    assert arcade_rate_misses(busy, rate, 1000) == [f"frame {busy[50].frame}: V60 busy {FRAME_US} us (two vblanks are {FRAME_US})"]
    assert arcade_rate_misses(over, rate, 1000) == [f"frame {over[120].frame}: overrun counter 0x501148 0 -> 1"]
    assert arcade_rate_misses([], rate, 1000) == ["no logic frame logged in [1000, None)"]
    assert arcade_rate_misses(frames, [], 1000) == ["no whole render-rate window in [1000, None)"]
    assert arcade_rate_misses(busy, rate, 1000, end=busy[50].frame) == []          # the stretch's end excludes the frame
    assert RATE_BOUNDS == (28, 29) and FRAME_US == 34_770


def test_one_lost_picture_is_the_counters_to_catch():
    """One pass of four vblanks (one picture lost) takes one display-list switch out of the 57-frame window it falls in. The
    windows alternate 28 and 29 (57 is odd), so in a 29-window it reads 28 and the render rate passes; in a 28-window it reads 27
    and fails. The overrun counter moves in both cases: it is the per-picture detector, the rate a check that pictures keep
    coming."""
    frames, rate = _clean()
    i29 = next(i for i, (f, n) in enumerate(rate) if n == 29)
    i28 = next(i for i, (f, n) in enumerate(rate) if n == 28)
    lost_in_29 = [(f, n - 1 if i == i29 else n) for i, (f, n) in enumerate(rate)]
    lost_in_28 = [(f, n - 1 if i == i28 else n) for i, (f, n) in enumerate(rate)]
    assert arcade_rate_misses(frames, lost_in_29, 1000) == []
    assert [m.split()[:3] for m in arcade_rate_misses(frames, lost_in_28, 1000)] == [["render", "rate", "27"]]
    over = [f._replace(overrun=1) if i >= 60 else f for i, f in enumerate(frames)]
    assert arcade_rate_misses(over, lost_in_29, 1000) == [f"frame {over[60].frame}: overrun counter 0x501148 0 -> 1"]


def test_only_the_named_scene_loads_may_take_longer():
    """The attract's scene changes take one pass of 41-52 ms on main's set too, with the counter still (findings §13): `excused`
    names those passes (the frames where main's set has one), and a pass of two vblanks anywhere else is still a miss."""
    frames, rate = _clean()
    load = frames[40].frame
    slow = [f._replace(busy_us=52_000) if i in (40, 90) else f for i, f in enumerate(frames)]
    assert arcade_rate_misses(slow, rate, 1000, excused={load}) == [
        f"frame {slow[90].frame}: V60 busy 52000 us (two vblanks are {FRAME_US})"]
    assert arcade_rate_misses(slow, rate, 1000, excused={load, slow[90].frame}) == []
    assert worst_busy(slow, 1000, excused={load, slow[90].frame}).busy_us == 12_000
    assert scene_loads(slow) == {load, slow[90].frame}


def test_frame_rate_lua_writes_what_the_parser_reads(tmp_path):
    """frame_rate.lua's F line (frame, busy us, 0x501148, records, lists skipped, 0x5011b0) is what `parse_frame_log` reads;
    autoplay.lua loads it with VR_FRAME_LOG (or VR_HOLD_CLOCK)."""
    text = (LUA_DIR / "frame_rate.lua").read_text()
    assert 'string.format("F %d %.0f %d %d %d %d %d\\n", frame, (t_enter - t_exit) * 1e6, prog:read_u32(0x501148), peak, skipped,' in text
    assert "prog:read_u32(0x5011b0), need))" in text and 'os.getenv("VR_HOLD_CLOCK") == "1"' in text
    assert ('if (os.getenv("VR_FRAME_LOG") or os.getenv("VR_HOLD_CLOCK")) and lua_dir then dofile(lua_dir .. "/frame_rate.lua") end'
            in (LUA_DIR / "autoplay.lua").read_text())
    p = tmp_path / "f.txt"
    p.write_text("F 1607 11844 0 4514 0 10500 4128\nF 1609\nS x\nF 1611 12100 0 5647 7 5500 5502\nEND\n")
    assert parse_frame_log(p) == [FrameSample(1607, 11844, 0, 4514, 0, 10500, 4128), FrameSample(1611, 12100, 0, 5647, 7, 5500, 5502)]
    assert 'if os.getenv("VR_PASS_LOG") and lua_dir then dofile(lua_dir .. "/pass_state.lua") end' in (LUA_DIR / "autoplay.lua").read_text()
    att = (LUA_DIR / "attract_snaps.lua").read_text()
    assert 'if os.getenv("VR_FRAME_LOG") and lua_dir then dofile(lua_dir .. "/frame_rate.lua") end' in att
    assert 'if os.getenv("VR_RATE_LOG") and lua_dir then dofile(lua_dir .. "/renderrate.lua") end' in att
    q = tmp_path / "w.txt"
    q.write_text("W 1 2 0 " + "0 0 0 0 0 " * 16 + "\nX\nEND\n")
    assert parse_pass_log(q) == ["W 1 2 0 " + "0 0 0 0 0 " * 16]


def test_a_stale_display_list_is_caught(tmp_path):
    """stale_list.lua's L line (the frame a pass's wait was left in, the game's display-list pointer 0x5017f4 there: the end of the
    list that pass wrote) is what `parse_stale_log` reads. A pass that wrote the same list (0x600000 or 0x610000) as the pass
    before it is a stale picture and is reported, by its frame; a clean log reports none; pointers outside the two lists (the
    boot's) are no list; a log with no list at all is an error (a run that measured nothing passes nothing)."""
    clean = tmp_path / "clean.txt"
    clean.write_text("L 3 0\nL 5 0\nL 1607 610e8c\nL 1609\nX 1\nL 1611 6012a0\nL 1613 611000\nL 1615 600010\nEND\n")
    assert parse_stale_log(clean) == []
    stale = tmp_path / "stale.txt"
    stale.write_text("L 1607 610e8c\nL 1609 6012a0\nL 1611 6025e8\nL 1613 611000\nL 1615 6004f0\nL 1617 600010\nEND\n")
    assert parse_stale_log(stale) == [1611, 1617]
    empty = tmp_path / "empty.txt"
    empty.write_text("L 3 0\nEND\n")
    with pytest.raises(ValueError):
        parse_stale_log(empty)
    broken = tmp_path / "broken.txt"                                  # no list between two passes on the same list: not stale
    broken.write_text("L 1607 610e8c\nL 1609 0\nL 1611 6125e8\nL 1613 600010\nEND\n")
    assert parse_stale_log(broken) == []


def test_the_display_list_deadline():
    assert DEADLINE_MS == 18.9                                        # MAME's screen update after the wait (out/p48/look/NOTE.txt)


def _synthetic_run(wd, passes, start, end=None):
    """A run of `passes` ((frame, list 0x60 or 0x61, busy us)): its stale_list.txt and frames, as `_stale` reads them."""
    wd.mkdir(exist_ok=True)
    (wd / "stale_list.txt").write_text("".join(f"L {f} {lst:x}0100\n" for f, lst, _ in passes) + "END\n")
    return SimpleNamespace(wd=wd, start=start, end=end, frames=[FrameSample(f, b, 0, 4000, 0, 10_500, 3600) for f, _, b in passes])


def test_stale_skips_only_the_passes_after_the_excused_loads(tmp_path):
    """`_stale`: the stale passes of the run's stretch (all of the run in the attract), less the one pass right after each load the
    rate logic excuses, if it is stale. A pass of four vblanks or more leaves the next pass in its list on main's set (frame_rate.lua's
    F lines and the L lines are written at the same wait exits, so a pass's frame is the same in both). The loads: in a race run, the
    passes of FRAME_US or more before its stretch, at most LOADS_BEFORE_RACE (main's set: the boot's first attract scene, frame 275,
    and the course load, the pass before `start`), a third one fails naming its frame; in the attract, those of the scene loads the
    attract test excuses (`excused`, main's) that are long passes in this run too. A load whose next pass is clean is no error; a
    long pass anywhere else, or one of main's loads that is short in this run, excuses nothing: the stale pass after it is
    reported (a long pass in the stretch is also a rate miss)."""
    P = [(275, 0x60, 52_400), (277, 0x60, 12_000), (279, 0x61, 10_000), (281, 0x60, 10_000),
         (1605, 0x61, 48_000), (1607, 0x61, 11_800),                     # the course load, then its skipped pass
         (1609, 0x60, 12_000), (1611, 0x61, 12_000),
         (1613, 0x60, FRAME_US + 1000), (1615, 0x60, 12_000),            # a long pass mid-race: the stale pass after it is REPORTED
         (1617, 0x61, 20_000), (1619, 0x61, 12_000), (1621, 0x60, 12_000)]   # a late pass (past the deadline, under two vblanks)
    assert _stale(_synthetic_run(tmp_path / "race", P, start=1606)) == [1615, 1619]
    assert _stale(_synthetic_run(tmp_path / "race", P, start=1606, end=1617)) == [1615]
    assert _stale(_synthetic_run(tmp_path / "attract", P, start=None), excused={275, 1605, 1613}) == [1619]
    assert LOADS_BEFORE_RACE == 2
    no_skip = [(f, 0x60 if f == 1605 else lst, b) for f, lst, b in P]                # the course load left no stale pass: fine
    assert _stale(_synthetic_run(tmp_path / "no_skip", no_skip, start=1606)) == [1615, 1619]
    third = [(f, lst, FRAME_US if f == 279 else b) for f, lst, b in P]               # a third long pass before the race
    with pytest.raises(AssertionError, match="279"):
        _stale(_synthetic_run(tmp_path / "third", third, start=1606))
    stale, text = _stale_result(_synthetic_run(tmp_path / "third", third, start=1606))  # the tests' form: never raises, so the
    assert stale is None and "279" in text                                            # summary line and the rate misses still come
    assert _stale_result(_synthetic_run(tmp_path / "race", P, start=1606)) == ([1615, 1619], "[1615, 1619]")
    assert _stale(_synthetic_run(tmp_path / "attract2", P, start=None), excused={275, 1605, 2259}) == [1615, 1619]   # 2259: none here
    short = [(f, lst, 12_000 if f == 1613 else b) for f, lst, b in P]                # main's load 1613 is short in this run ...
    assert _stale(_synthetic_run(tmp_path / "short", short, start=None), excused={275, 1605, 1613}) == [1615, 1619]  # ... 1615 reported


def test_stale_list_lua_writes_what_the_parser_reads():
    """stale_list.lua writes "L <frame> <0x5017f4 hex>" at each exit of the two-vblank wait (the write of 0 to 0x500501 from
    0xfe1400..0xfe140e, frame_rate.lua's own exit, so the frames match its F lines); autoplay.lua and attract_snaps.lua load it
    with VR_STALE_LOG."""
    text = (LUA_DIR / "stale_list.lua").read_text()
    assert 'out:write(string.format("L %d %x\\n", frame, prog:read_u32(0x5017f4)))' in text
    assert "pc >= 0xfe1400 and pc <= 0xfe140e" in text and 'out:write("END\\n")' in text
    load = 'if os.getenv("VR_STALE_LOG") and lua_dir then dofile(lua_dir .. "/stale_list.lua") end'
    assert load in (LUA_DIR / "autoplay.lua").read_text() and load in (LUA_DIR / "attract_snaps.lua").read_text()


def test_input_tape_lua_records_and_replays_the_autopilots_inputs():
    """input_tape.lua (autoplay.lua loads it after autopilot.lua with VR_INPUT_LOG or VR_INPUT_REPLAY) wraps the autopilot's wheel
    and pedal: it writes "I <frame> <wheel or -> <throttle>" for every call, and with a tape it returns the tape's values instead,
    ending MAME (status 3) when the run asks for a frame the tape lacks."""
    play = (LUA_DIR / "autoplay.lua").read_text()
    load = ('if (os.getenv("VR_INPUT_LOG") or os.getenv("VR_INPUT_REPLAY")) and lua_dir then dofile(lua_dir .. "/input_tape.lua") end')
    assert load in play and play.index('dofile(lua_dir .. "/autopilot.lua")') < play.index(load)
    tape = (LUA_DIR / "input_tape.lua").read_text()
    assert 'out:write(string.format("I %d %s %d\\n", frame, wheel_now and tostring(wheel_now) or "-", t))' in tape
    assert 'line:match("^I (%d+) (%S+) (%d+)$")' in tape and "os.exit(3)" in tape


def test_only_the_selected_tests_runs_are_made():
    """Phase 31: a selection of some parameters of this module's tests (-k entry_6) makes those tests' runs only, not every
    course's: `selected_keys` gives the runs the collected items read, by their parameters."""
    from types import SimpleNamespace as NS
    item = lambda name, **params: NS(originalname=name, callspec=NS(params=params))
    items = [item("test_every_course_holds_the_arcade_rate", entry=6, reverse=False),
             item("test_every_course_holds_the_arcade_rate", entry=6, reverse=True),
             item("test_no_list_is_skipped_where_the_games_budget_cut", entry=6, reverse=False),
             item("test_no_list_is_skipped_where_the_games_budget_cut", entry=1, reverse=False),
             item("test_the_worst_known_frames_hold_the_arcade_rate", key=("pit", 6, False)),
             item("test_the_game_is_the_same_pass_for_pass", entry=2),
             NS(originalname="test_a_clean_log_has_no_miss"), NS(name="test_of_another_module")]
    assert selected_keys(items) == {("rate", 6, False), ("rate", 6, True), ("cut", 6, False), ("rate", 1, False), ("pit", 6, False),
                                    ("same", 2, False, "main"), ("same", 2, False, "new")}
    assert selected_keys([item("test_the_attract_holds_the_arcade_rate")]) == {("attract", -1, False, "new"), ("attract", -1, False, "main")}
    assert selected_keys([]) == set()


def test_the_worst_known_frames_boot_on_the_sessions_battery_ram():
    """Phase 79 review: the worst-frame runs (WORST, with their margin floors) and the same-race runs boot on the battery RAM a
    30 s boot of the session's set made (`RateSession.nvram`), not on none. On no battery RAM the boot's first-boot work (Phase
    35's tables, `revinit`) moves where MAME's frame ends fall inside a pass; the autopilot steers from samples grouped by frame
    end, so the car's line moved (Big Forest line 4 from frame 3 314: 9 886 records at road point 263 against 9 771, the game's
    drawing pass for pass the same on the same inputs). The standing races keep booting on none."""
    assert all(boots_on_saved_battery(k) for k in WORST)
    assert boots_on_saved_battery(("same", 0, False, "main")) and boots_on_saved_battery(("same", 2, False, "new"))
    assert not any(boots_on_saved_battery(k) for k in [("rate", e, r) for e, r in COURSES] + [("cut", 5, False), ("attract", -1, False, "new")])


# ---- the runs ----

def selected_keys(items) -> set:
    """The runs the collected tests `items` of this module read, each by its parameters."""
    keys = set()
    for i in items:
        name = getattr(i, "originalname", None) or getattr(i, "name", "")
        p = getattr(getattr(i, "callspec", None), "params", {})
        if name == "test_every_course_holds_the_arcade_rate":
            keys.add(("rate", p["entry"], p["reverse"]))
        elif name == "test_no_list_is_skipped_where_the_games_budget_cut":
            keys.add(("rate" if p["entry"] < 3 else "cut", p["entry"], p["reverse"]))
        elif name == "test_the_worst_known_frames_hold_the_arcade_rate":
            keys.add(tuple(p["key"]))
        elif name == "test_the_attract_holds_the_arcade_rate":
            keys.update(("attract", -1, False, s) for s in ("new", "main"))
        elif name == "test_the_game_is_the_same_pass_for_pass":
            keys.update(("same", p["entry"], False, s) for s in ("main", "new"))
        elif name == "test_the_pass_comparison_sees_a_planted_difference":
            keys.update(("same", 2, False, s) for s in ("main", "poked"))
    return keys


def boots_on_saved_battery(key) -> bool:
    """The runs that boot on the session's battery RAM (`RateSession.nvram`) instead of none: the same-race pairs, and (Phase 79
    review) the worst-frame runs, whose margin floors held the car's line fixed and which a change to the boot's first-boot work
    moved (test_the_worst_known_frames_boot_on_the_sessions_battery_ram)."""
    return key[0] == "same" or tuple(key) in WORST


def _unbudgeted(rs: RomSet) -> RomSet:
    """`rs` with both budget immediates the game's again: main's set made from the same conversions."""
    boot = bytearray(rs.boot)
    for site, original in BUDGET_SITES:
        at = site - V60_BOOT + IMM_OFFSET
        boot[at:at + 4] = original.to_bytes(4, "little")
    return RomSet(rs.program, bytes(boot), rs.data, rs.polygons, rs.copro_data, rs.tgp_program)


def bf_pit_path(line0) -> list[tuple[float, float]]:
    """Big Forest's lap through its pit lane: road line 0 ((x, z) in lap order) with x moved to BF_PIT_X over BF_LANE (road
    points, wrapping past the start line), blended linearly over BF_IN points before it and BF_OUT points after it."""
    n = len(line0)
    first, last = BF_LANE
    lane = {k % n for k in range(first, last + n + 1)} if last < first else set(range(first, last + 1))
    out = []
    for k, (x, z) in enumerate(line0):
        if k in lane:
            x = BF_PIT_X
        else:
            before = (first - k) % n                    # points until the lane
            after = (k - last) % n                      # points since the lane
            if before <= BF_IN:
                x += (BF_PIT_X - x) * (BF_IN + 1 - before) / (BF_IN + 1)
            elif after <= BF_OUT:
                x += (BF_PIT_X - x) * (BF_OUT + 1 - after) / (BF_OUT + 1)
        out.append((x, z))
    return out


class Run:
    """A run's logs. `finish`: a race clock held still for FINISH_STILL frames after the green ends the stretch (the finish); off
    for a pit lap, whose clock stands still during the stop."""

    def __init__(self, wd: Path, finish: bool = True):
        self.wd = wd
        self.frames = parse_frame_log(wd / "frames.txt") if (wd / "frames.txt").exists() else []
        self.rate = parse_rate(wd / "rate.txt") if (wd / "rate.txt").exists() else []
        self.players = parse_race_log(wd / "race.txt")[0] if (wd / "race.txt").exists() else []
        clocks = [(p.frame, p.clock) for p in self.players]
        self.load = next((f for f, c in clocks if c > 0), None)
        self.green = next((clocks[i][0] for i in range(1, len(clocks)) if self.load and clocks[i][0] > self.load
                           and 0 < clocks[i][1] < clocks[i - 1][1]), None)
        # the race's end: the clock at 0 (time out), or held still for FINISH_STILL frames after the green (the finish stops it;
        # VR_HOLD_CLOCK only moves it up, below 30 s); the game's own scene change after the race is not counted
        self.end = next((clocks[i][0] for i in range(len(clocks)) if self.green and clocks[i][0] > self.green
                         and (clocks[i][1] == 0 or (finish and i >= FINISH_STILL and clocks[i - FINISH_STILL][0] > self.green
                                                    and all(c == clocks[i][1] for _, c in clocks[i - FINISH_STILL:i + 1])))), None)
        first = next((f for f in self.frames if self.load is not None and f.frame >= self.load), None)
        self.start = first.frame + 1 if first else None          # the pass after the course load's own

    def stretch(self):
        return [f for f in self.frames if self.start is not None and self.start <= f.frame and (self.end is None or f.frame < self.end)]


class RateSession:
    """The session's built set, main's equivalent (`_unbudgeted`, for the comparison) and every run of this module, made at the
    first use."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        from tests.test_race_build import _drive_line
        from tests.test_tgp_build import _build, _seven
        self.romset_zip, self.saturn_cue, self.base = romset_zip, saturn_cue, base
        self.out, self.conv = _seven(romset_zip, saturn_cue)
        conv = self.conv
        for d in ("new", "main"):
            (base / d).mkdir(parents=True, exist_ok=True)
        self.build = _build(base / "new", romset_zip, self.out)
        self.main = _build(base / "main", romset_zip, _unbudgeted(self.out))
        d = decode_directory(self.out)
        self.road = {e: road_lines(self.out, course_entry_at(self.out, d[e].bank, window_base=d[e].header_base)) for e in range(10)}
        self.recon_lines = {}
        for e, how in RECON_LINE.items():
            ls = self.road[e]
            self.recon_lines[e] = ([(p.x, p.z) for p in ls[0]] if how == "line0" else
                                   [(sum(l[k].x for l in ls[1:]) / 7, sum(l[k].z for l in ls[1:]) / 7) for k in range(len(ls[0]))])
        self.lines = {}
        for e in range(10):
            if e < 3:
                self.lines[e] = [(p.x, p.z) for p in self.road[e][0]]
            else:
                self.lines[e] = _drive_line(conv[e - 3])
        self.runs: dict[tuple, Run] = {}
        self.failed: dict[tuple, BaseException] = {}
        self._lock = threading.Lock()

    def pit_path(self, entry: int, reverse: bool = False) -> list[tuple[float, float]]:
        """A lap through the entry's pit lane: Big Forest's `bf_pit_path`; a converted course's the pit tests' (test_pit_build:
        line 6 with the lane's polyline spliced in, `pitpaths.normal_pit_path`); an original's in reverse the originals' reverse
        tests' (test_originals_reverse.lane_lap: line 0 along the lane, read backwards by `_env`)."""
        if reverse and entry < 3:
            from tests.test_originals_reverse import lane_lap
            return lane_lap(self.lines[entry], entry)
        if entry == 0:
            return bf_pit_path(self.lines[0])
        lane = pit_lane(RomSet.from_zip(self.romset_zip), self.saturn_cue, PLANS[entry - 3], self.conv[entry - 3].centreline)[0]
        return normal_pit_path([(p.x, p.z) for p in self.road[entry][6]], lane)

    def _env(self, wd: Path, entry: int, reverse: bool, line=None) -> dict:
        line = line or self.lines[entry]
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
               "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", reverse_points(line) if reverse else line)),
               "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0"}
        if reverse:
            env["VR_DIRECTION"] = "1"
        return env

    def _make(self, key) -> Run:
        kind, entry, reverse = key[:3]
        wd = self.base / "runs" / f"{kind}_{entry}{'r' if reverse else ''}{'_' + key[3] if len(key) > 3 else ''}"
        wd.mkdir(parents=True, exist_ok=True)
        rate_logs = {"VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"),
                     "VR_STALE_LOG": str(wd / "stale_list.txt")}           # Phase 79: the list each pass wrote
        if kind == "attract":                                  # no input: the attract cycle (its demo races and the scenes between)
            env = {"VR_SNAP_FROM": "999999", **rate_logs}
            run_mame(LUA_DIR / "attract_snaps.lua", ATTRACT_SECONDS, wd, self.build if key[3] == "new" else self.main, env=env,
                     timeout=3600)
            return Run(wd)
        if kind in ("rate", "cut", "pit"):
            line = (self.recon_lines[entry] if kind == "cut" else self.pit_path(entry, reverse) if kind == "pit"
                    else [(p.x, p.z) for p in self.road[entry][int(key[3][4:])]] if len(key) > 3 and key[3].startswith("line") else None)
            env = self._env(wd, entry, reverse, line)
            env.update({**rate_logs, "VR_HOLD_CLOCK": "1"})
            if kind == "pit":
                env["VR_PIT_LOG"] = str(wd / "pit.txt")
            seconds = WORST_SECONDS if len(key) > 3 and key[3].startswith("line") else RATE_SECONDS
            if boots_on_saved_battery(key):
                shutil.copytree(self.nvram(), wd / "nvram")
            run_mame(LUA_DIR / "autoplay.lua", seconds, wd, self.build, env=env, timeout=3600)
            return Run(wd, finish=kind != "pit")
        # "same": a normal race on the shared battery RAM, every game log; main's set records the autopilot's inputs, the set
        # replays them frame for frame (input_tape.lua) and writes what it fed
        shutil.copytree(self.nvram(), wd / "nvram")
        env = self._env(wd, entry, reverse)
        env.update({"VR_PIT_LOG": str(wd / "pit.txt"), "VR_PASS_LOG": str(wd / "pass.txt"), "VR_PASS_FIELDS": "1",
                    "VR_FRAME_LOG": str(wd / "frames.txt"), "VR_INPUT_LOG": str(wd / "tape.txt")})
        if key[3] in ("new", "poked"):
            env["VR_INPUT_REPLAY"] = str(self.run("same", entry, reverse, "main").wd / "tape.txt")
        if key[3] == "poked":                          # the join's round 2, J4: a game made to differ (one car's x poked)
            env.update({"VR_EXTRA_LUA": str(LUA_DIR / "storm_poke.lua"), "VR_STORM_POKE": f"{POKE_FRAME}:{POKE_ADDR:x}:0",
                        "VR_POKE_LOG": str(wd / "poke.txt")})
        run_mame(LUA_DIR / "autoplay.lua", SAME_SECONDS, wd, self.main if key[3] == "main" else self.build, env=env, timeout=3600)
        return Run(wd)

    def nvram(self) -> Path:
        """The battery RAM both sets' compared races and the worst-frame runs start from (`boots_on_saved_battery`): the set's
        after a 30 s boot to the attract (no input)."""
        wd = self.base / "runs" / "nvram_boot"
        if not (wd / "nvram").is_dir():
            run_mame(LUA_DIR / "attract_snaps.lua", 30, wd, self.build, env={"VR_SNAP_FROM": "999999"}, timeout=900)
        return wd / "nvram"

    def keys(self, names=None):
        """The runs the tests `names` (all of this module's when None) read."""
        names = names or {"test_every_course_holds_the_arcade_rate", "test_no_list_is_skipped_where_the_games_budget_cut",
                          "test_surfers_road_stays_inside_the_draw_budget",
                          "test_the_game_is_the_same_pass_for_pass", "test_the_worst_known_frames_hold_the_arcade_rate",
                          "test_the_attract_holds_the_arcade_rate"}
        keys = []
        if "test_every_course_holds_the_arcade_rate" in names:
            keys += [("rate", e, r) for e, r in COURSES]
        if "test_surfers_road_stays_inside_the_draw_budget" in names:
            keys += [("rate", 9, False), ("rate", 9, True)]
        if "test_no_list_is_skipped_where_the_games_budget_cut" in names:
            keys += [("rate" if e < 3 else "cut", e, r) for e, r in CUT_BEFORE]
        if "test_the_worst_known_frames_hold_the_arcade_rate" in names:
            keys += WORST
        if "test_the_attract_holds_the_arcade_rate" in names:
            keys += [("attract", -1, False, s) for s in ("new", "main")]
        if "test_the_game_is_the_same_pass_for_pass" in names:
            keys += [("same", e, False, s) for e in SAME_RACE for s in ("main", "new")]
        return list(dict.fromkeys(keys))

    def prefetch(self, names=None, only=None):
        """Make the runs the tests `names` read; with `only` (Phase 31: `selected_keys` of the collected items), those of them only."""
        keys = [k for k in self.keys(names) if only is None or k in only]
        if any(boots_on_saved_battery(k) for k in keys):           # made once, before the parallel runs
            self.nvram()

        def make(k):
            try:
                r = self._make(k)
            except Exception as e:                             # noqa: BLE001 (raised again by `run`)
                with self._lock:
                    self.failed[k] = e
                return
            with self._lock:
                self.runs[k] = r
        replays = [k for k in keys if k[0] == "same" and k[3] == "new"]          # each needs its main run's tape: made after them
        with ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(make, [k for k in keys if k not in self.runs and k not in replays]))
        with ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(make, [k for k in replays if k not in self.runs]))

    def run(self, *key) -> Run:
        if key in self.failed:
            raise AssertionError(f"the run {key} failed: {self.failed[key]!r}") from self.failed[key]
        if key not in self.runs:
            self.runs[key] = self._make(key)
        return self.runs[key]


_SESSIONS: dict[str, RateSession] = {}


@pytest.fixture
def rate_runs(request, romset_zip, saturn_cue, tmp_path_factory) -> RateSession:
    """The session's RateSession; at its first use it makes, in parallel, the runs the session's collected tests of this module read
    (Phase 31: of the collected parameters only, so that a selection of one course runs that course)."""
    key = str(romset_zip)
    if key not in _SESSIONS:
        s = RateSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("rate"))
        s.prefetch({getattr(i, "originalname", i.name) for i in request.session.items}, only=selected_keys(request.session.items))
        _SESSIONS[key] = s
    return _SESSIONS[key]


def _name(entry, reverse):
    return f"entry {entry}{' reverse' if reverse else ''}"


def _stale(run, excused=None) -> list[int]:
    """The frames of the run's passes that wrote the same display list as the pass before (stale_list.lua, `parse_stale_log`):
    in the run's stretch [start, end) when it has a race, else over the whole run (the attract), less the pass right after each
    load the rate logic excuses, if it is stale (a load leaves the next pass in its list on main's set; one whose next pass is
    clean is no error). The loads are long passes (FRAME_US or more) of this run: a race run's before its stretch, at most
    LOADS_BEFORE_RACE (the boot's first attract scene and the course load, the pass before `start`; AssertionError naming the
    frames when there are more); in the attract, those of `excused` (main's scene loads, as its test excuses them) that are long
    passes in this run too. A stale pass after any other pass is reported. The gap this closes is the pass under two vblanks but
    past DEADLINE_MS, which the rate measure passes."""
    stale = parse_stale_log(run.wd / "stale_list.txt")
    long = {f.frame for f in run.frames if f.busy_us >= FRAME_US}
    if excused is None:
        loads = sorted(f for f in long if f < run.start)
        assert len(loads) <= LOADS_BEFORE_RACE, (run.wd.name, "passes of two vblanks or more before the race", loads)
    else:
        loads = sorted(long & set(excused))
    after = {a.frame: b.frame for a, b in zip(run.frames, run.frames[1:])}
    skipped = {after[f] for f in loads if f in after}
    return [f for f in stale if f not in skipped
            and (run.start is None or (run.start <= f and (run.end is None or f < run.end)))]


def _stale_result(run, excused=None) -> tuple[list[int] | None, str]:
    """`_stale` computed once for a test: (its frames, the text for the summary line). When its guard fails or the log measured
    nothing, (None, that message): the summary line is still written and the test asserts it together with the rate misses."""
    try:
        frames = _stale(run, excused)
    except (AssertionError, ValueError) as e:
        return None, f"stale-list check failed: {e}"
    return frames, str(frames)


def _summary(rate_runs, name, r, w, stale_text):
    stretch = r.stretch()
    rf = r.green if r.green is not None else r.start
    with open(rate_runs.base / "rate_summary.txt", "a") as out:
        out.write(f"{name}: logic frames {len(stretch)} ({r.start}-{r.end or stretch[-1].frame}), green {r.green}, "
                  f"rate {min(n for f, n in r.rate if f - 57 >= rf)}-{max(n for f, n in r.rate if f - 57 >= rf)}, "
                  f"0x501148 {stretch[0].overrun}->{stretch[-1].overrun}, worst busy {w.busy_us} us at frame {w.frame}, "
                  f"records peak {max(f.records for f in stretch)}, need max {max(f.need for f in stretch)}, "
                  f"budget {sorted({f.budget for f in stretch})}, frames with a skipped list {sum(1 for f in stretch if f.skipped)}, "
                  f"worst busy {w.busy_us / 1000:.2f} ms against the {DEADLINE_MS} ms deadline, stale lists {stale_text}\n")


@pytest.mark.parametrize("entry,reverse", COURSES, ids=[_name(e, r).replace(" ", "_") for e, r in COURSES])
def test_every_course_holds_the_arcade_rate(rate_runs, record_property, entry, reverse):
    """The standing test: from the boot through the start with the full field and about two laps, the render rate 28-29 in
    every window from the green, the overrun counter still, the V60 busy under two vblanks in every frame from the pass after
    the course load (the race's end, if it ends, closes the stretch)."""
    r = rate_runs.run("rate", entry, reverse)
    assert r.load and r.green and r.start, (_name(entry, reverse), r.load, r.green)
    misses = arcade_rate_misses(r.frames, r.rate, r.start, r.end, rate_from=r.green)
    w = worst_busy(r.frames, r.start, r.end)
    record_property("worst_busy_us", w.busy_us)
    stale, stale_text = _stale_result(r)                            # Phase 79
    _summary(rate_runs, _name(entry, reverse), r, w, stale_text)
    assert misses == [] and stale == [], (_name(entry, reverse), misses[:10], "stale display lists", stale_text, w.busy_us)
    assert len(r.stretch()) > 2500                                  # about 90 s of race measured


@pytest.mark.parametrize("reverse", [False, True], ids=["entry_9", "entry_9_reverse"])
def test_surfers_road_stays_inside_the_draw_budget(rate_runs, reverse):
    """Phase 34 (review): Surfers Road carries 13 more of its own palms baked into its cells, which add records to every frame
    that has their cells in the visible block. The standing race (the same run as test_every_course_holds_the_arcade_rate's): no
    list skipped from the boot to the run's end and the set's budget in every frame. The last assertion (the need, the least
    budget under which a frame skips no list, under that budget) says the same as "no list skipped" in the measure's own number:
    it adds no condition, it is there so that a failure prints how far over a frame went."""
    r = rate_runs.run("rate", 9, reverse)
    stretch = r.stretch()
    assert len(stretch) > 2500
    skipped = [f for f in r.frames if f.skipped]
    assert skipped == [], (_name(9, reverse), f"{len(skipped)} frames skipped a list", skipped[:3])
    assert {f.budget for f in stretch} == {FRAME_BUDGET}, (_name(9, reverse), sorted({f.budget for f in stretch}))
    assert max(f.need for f in r.frames) < FRAME_BUDGET, (_name(9, reverse), max(f.need for f in r.frames))


@pytest.mark.parametrize("key", WORST, ids=WORST_IDS)
def test_the_worst_known_frames_hold_the_arcade_rate(rate_runs, record_property, key):
    """The same three measures where the margin is thinnest (findings §13): Big Forest on road line 4 for WORST_SECONDS (its
    heavy stretch, road points 258-283, every lap; the run must reach frames needing more than 9 000 records), and a lap through
    the pit lane on Big Forest and on Metropolis, and in reverse on Big Forest and on Acropolis (the run must hold a pit stop:
    the player's pit handler for 300 frames or more after the green, inside the stretch). Phase 79 review: they boot on the
    session's battery RAM (`boots_on_saved_battery`)."""
    name = WORST_IDS[WORST.index(key)]
    r = rate_runs.run(*key)
    assert r.load and r.green and r.start, (name, r.load, r.green)
    stretch = r.stretch()
    misses = arcade_rate_misses(r.frames, r.rate, r.start, r.end, rate_from=r.green)
    w = worst_busy(r.frames, r.start, r.end)
    record_property("worst_busy_us", w.busy_us)
    stale, stale_text = _stale_result(r)                            # Phase 79
    _summary(rate_runs, name, r, w, stale_text)
    assert misses == [] and stale == [], (name, misses[:10], "stale display lists", stale_text, w.busy_us)
    assert len(stretch) > 2500, (name, len(stretch))
    need = max(f.need for f in stretch)                             # review I1: the margin itself, asserted
    skipped = [f for f in stretch if f.skipped]
    assert skipped == [] and {f.budget for f in stretch} == {FRAME_BUDGET}, (name, len(skipped), sorted({f.budget for f in stretch}))
    assert need <= FRAME_BUDGET - MARGIN_FLOOR.get(name, 0), (name, "the margin under the budget", FRAME_BUDGET - need, MARGIN_FLOOR.get(name, 0))
    record_property("need_max", need)
    if key[0] == "pit":
        stopped = [p.frame for p in parse_pit_log(r.wd / "pit.txt") if p.handler == PIT_HANDLER and p.frame > r.green + 200
                   and (r.end is None or p.frame < r.end)]
        assert len(stopped) >= 300, (name, "no pit stop in the run", len(stopped))
    else:
        assert max(f.need for f in stretch) > 9000, (name, "the heavy frames were not reached", max(f.need for f in stretch))


def test_the_attract_holds_the_arcade_rate(rate_runs, record_property):
    """The attract cycle with no input for ATTRACT_SECONDS (its demo races and the scenes between; the highest V60 busy measured,
    17 982 us, is one of its scenes): from the main loop's first pass, the overrun counter still, the render rate 28-29 in every
    window, the V60 busy under two vblanks in every pass but the scene loads: the passes of two vblanks or more that main's set
    (the game's budget) makes at the same frames (one pass of 41-52 ms per scene change, its counter still too)."""
    new, main = rate_runs.run("attract", -1, False, "new"), rate_runs.run("attract", -1, False, "main")
    start = new.frames[0].frame
    loads = scene_loads(main.frames)
    assert 0 < len(loads) < 60, sorted(loads)
    misses = arcade_rate_misses(new.frames, new.rate, start, excused=loads)
    w = worst_busy(new.frames, start, excused=loads)
    record_property("worst_busy_us", w.busy_us)
    stale, stale_text = _stale_result(new, loads)                   # Phase 79
    with open(rate_runs.base / "rate_summary.txt", "a") as out:
        out.write(f"attract: logic frames {len(new.frames)} (from {start}), scene loads {len(loads)} (main's), new's passes of two "
                  f"vblanks or more {len(scene_loads(new.frames))}, rate {min(n for f, n in new.rate if f - 57 >= start)}-"
                  f"{max(n for f, n in new.rate if f - 57 >= start)}, 0x501148 {new.frames[0].overrun}->{new.frames[-1].overrun}, "
                  f"worst busy outside the loads {w.busy_us} us at frame {w.frame}, records peak {max(f.records for f in new.frames)}, "
                  f"need max {max(f.need for f in new.frames)}, frames with a skipped list {sum(1 for f in new.frames if f.skipped)}, "
                  f"worst busy {w.busy_us / 1000:.2f} ms against the {DEADLINE_MS} ms deadline, stale lists {stale_text}\n")
    assert misses == [] and stale == [], (misses[:10], "stale display lists", stale_text, w.busy_us)
    assert len(new.frames) > 5000


@pytest.mark.parametrize("entry,reverse", CUT_BEFORE, ids=[_name(e, r).replace(" ", "_") for e, r in CUT_BEFORE])
def test_no_list_is_skipped_where_the_games_budget_cut(rate_runs, entry, reverse):
    """The frames the game's 5 500 cut (the recon: the originals on 3-22 % of race frames; Diablo Canyon's start and its reverse
    road point 178, Metropolis's start, Pacific Coast's road points 46 and 58) are in the run, their need above 5 500, and with the
    set's budget (FRAME_BUDGET in every frame) no list is skipped from the boot to the run's end."""
    r = rate_runs.run("rate" if entry < 3 else "cut", entry, reverse)
    stretch = r.stretch()
    cut = [f for f in stretch if f.need > ORIGINAL_BUDGET]
    assert cut, (_name(entry, reverse), "no frame above 5 500 in this run: it shows nothing", max(f.need for f in stretch))
    skipped = [f for f in r.frames if f.skipped]
    assert skipped == [], (_name(entry, reverse), f"{len(skipped)} frames skipped a list", skipped[:3], f"{len(cut)} frames above 5 500")
    assert {f.budget for f in stretch} == {FRAME_BUDGET}, (_name(entry, reverse), sorted({f.budget for f in stretch}))
    assert max(f.need for f in r.frames) <= FRAME_BUDGET


@pytest.mark.parametrize("entry", SAME_RACE)
def test_the_game_is_the_same_pass_for_pass(rate_runs, entry):
    """A normal race of SAME_SECONDS on the same battery RAM, on main's set (the same conversions, the game's budget) with the
    autopilot, then on the set fed exactly the wheel and pedal the autopilot gave on main's, frame for frame (input_tape.lua): the
    game's state at the end of every logic pass (pass_state.lua with VR_PASS_FIELDS: the clock and all 16 cars' x, z, road point,
    speed and lap, line cursor, target, lap-position quad, working performance, rank and ranking neighbours, and the frame each pass
    ends in) is identical over the whole run, main's run skipped lists and the set's none.
    The same inputs are needed: the autopilot steers from the player's TGP calls grouped by MAME's frame end, and a set whose passes
    take another time can see a position one frame earlier or later and steer otherwise, after which the races part (findings §13).
    The join's round 2, J4 (the session lead's ruling): the cars' fields are compared at pass ends, where the game's state is defined,
    no longer from a frame-end log: MAME's frame end falls inside a pass, so a set whose passes take other times (the wet handling's
    dry paths, about 42 us a pass) can sample a car in the middle of its update while the game is the same (Acropolis, frame 3510,
    the player's x and z half updated). test_the_pass_comparison_sees_a_planted_difference shows the comparison fails on a game that
    differs."""
    old, new = rate_runs.run("same", entry, False, "main"), rate_runs.run("same", entry, False, "new")
    ta, tb = (new.wd / "tape.txt").read_text().splitlines(), (old.wd / "tape.txt").read_text().splitlines()
    assert len(ta) > 3000 and ta == tb, (entry, "the replay did not feed main's inputs", len(ta), len(tb))
    assert sum(1 for f in old.frames if f.skipped) > 0, (entry, "main's run skipped no list: it is not main's set")
    assert sum(1 for f in new.frames if f.skipped) == 0, (entry, "the set skipped a list")
    first, a, b = pass_difference(new, old)
    assert len(a) > 3000 and len(a) == len(b), (entry, len(a), len(b))
    assert first is None, (entry, first, a[first][:160], b[first][:160])


def pass_difference(new, old):
    """(the first pass whose state differs or None, the two pass logs) of two same-race runs (pass_state.lua with VR_PASS_FIELDS:
    every car's fields at every pass end)."""
    a, b = parse_pass_log(new.wd / "pass.txt"), parse_pass_log(old.wd / "pass.txt")
    assert a and len(a[0].split()) == 4 + 16 * 12, ("the pass log lacks the cars' fields (VR_PASS_FIELDS)", len(a[0].split()) if a else 0)
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None), a, b


def test_the_pass_comparison_sees_a_planted_difference(rate_runs):
    """J4's control: the same replayed race (Acropolis) on the set with one car's x written 0.0 at the end of frame POKE_FRAME
    (storm_poke.lua): `pass_difference` finds the game differing from main's from that frame on."""
    old, poked = rate_runs.run("same", 2, False, "main"), rate_runs.run("same", 2, False, "poked")
    assert (poked.wd / "poke.txt").read_text().split()[:2] == ["POKE", str(POKE_FRAME)]
    first, a, b = pass_difference(poked, old)
    assert first is not None and POKE_FRAME <= int(a[first].split()[2]) <= POKE_FRAME + 2, (first, a[first][:80] if first else None)
