"""Build-and-race tests for the per-course race data (M6): need VR_ROMDIR and VR_SATURN_CUE; each MAME run takes minutes."""
import math
from pathlib import Path

import pytest

from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.directory import decode_directory
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.convert.reverse import reverse_points
from vrtools.convert.lap import arc_of
from vrtools.mame.runner import LUA_DIR, _no_hit, lap_progress, parse_attitude, parse_collision, parse_hudmap, run_mame, write_centreline
from tests.test_tgp_build import _build, _seven


def _drive_line(c):
    """The line the autopilot drives: the centreline moved sideways by the AI lines' shift (Phase 22n, `collision.lane_shift`):
    the centreline follows the lap route's one strip, which at the Oval's banking or Metropolis's hairpin is the road's edge
    one; a player drives the road, where the shifted lines run and the coverage fill lays tarmac."""
    import math
    pts = c.centreline; n = len(pts); lanes = (c.report or {}).get("lanes")
    if not lanes or len(lanes) != n or len(lanes[0]) < 3:
        return pts
    out = []
    for k, (x, z) in enumerate(pts):
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % n]
        d = math.hypot(bx - ax, bz - az) or 1.0
        rx, rz = (bz - az) / d, -(bx - ax) / d
        out.append((x + lanes[k][2] * rx, z + lanes[k][2] * rz))
    return out


def _drive_entry(tmp_path, out, romset_zip, entry, c, seconds=90, extra_env=None, autopilot=True, reverse=False):
    """Race menu entry `entry` of the ten-course set `out` under the autopilot; returns the collision samples. Phase 26:
    `reverse` sets the direction flag and drives the line read backwards. Stage 3 (plan D14): on an entry with a reverse variant
    the course lock opens the COURSE DIRECTION screen and autoplay.lua answers it (REVERSE with VR_DIRECTION=1, else NORMAL); on
    one without, where no screen sets the flag, direction.lua holds it at 1 on the select screen (VR_DIRECTION_FORCE)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    build = _build(tmp_path, romset_zip, out)
    wd = tmp_path / f"entry{entry}"
    env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS_AFTER_START": "600,2000"}
    if c is not None and autopilot:                            # without it (an original, or a swerve test) the autoplay's own steering drives
        line = _drive_line(c)
        env["VR_AUTOPILOT"] = str(write_centreline(wd / "centreline.csv", reverse_points(line) if reverse else line))
    if reverse:
        env["VR_DIRECTION"] = "1"
        if decode_directory(out)[entry].reverse is None:
            env.update({"VR_DIRECTION_FORCE": "1", "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"})
    env.update(extra_env or {})
    run_mame(LUA_DIR / "autoplay.lua", seconds, wd, build, env=env)
    return parse_collision(wd / "c.txt")


def test_pacific_coast_passes_the_bay_bridge_props(tmp_path, romset_zip, saturn_cue):
    """Phase 8: the car stopped dead at (272, −321) against Bay Bridge's board row; the host props are gone now
    (with the host list the 90 s run stalled at 2995 units; with its own list it reached 3802). Since the pointer
    block fix put all fifteen opponents on the grid, the player on a Bay Bridge-template course starts inside a
    field that does not drive yet (open item, see docs/spike/2026-11-balance.md) and spends the run threading
    through it: 1542 units measured. The gate therefore checks the start is not delayed and the car gets away;
    the "through the spot" check returns when the field races. Phase 11: the field races and the autopilot, which
    cannot overtake, follows the slowest opponent (performance 1.74, about 3.5 road points a second): 2837 units in
    90 s against 3791 with Phase 10's jammed field, 85 units short of the spot; the drive is 120 s now."""
    out, conv = _seven(romset_zip, saturn_cue)
    k = next(i for i, c in enumerate(conv) if c.entry.name == "PACIFIC COAST")
    samples = _drive_entry(tmp_path, out, romset_zip, 3 + k, conv[k], seconds=120)    # 120 s: behind the field the spot (~3000 units in) takes longer
    p = lap_progress(samples, lambda x, z: arc_of(conv[k].lap, x, z), conv[k].lap.length)
    assert p["forward"] > 3000 and samples[-1].frame - samples[0].frame > 2500, p      # past the old stall (2995) behind the field; no 15 s start delay
    assert min(math.dist((s.x, s.z), (272.5, -321.0)) for s in samples) < 15        # it drove through the spot


# Phase 9 A/B (90 s autopilot runs, forward units): banking on / off per course; the plan enables banking for a
# course only where forward progress improves by at least 15 % without more backward travel. Measured 31 Oct 2026
# against a stalled field: Surfers Oval 1044 flat / 857 banked (backward 71 / 116), Surfers Road 2361 flat / 559
# banked (71 / 93): banking stays off on both. Since Phase 10 the field drives and stands in the autopilot's way on
# these single-file starts, so the player's absolute progress is traffic (Oval 977 / 856, Surfers Road 587 / 871
# with 351 backward); the pinned floors are the Phase 10 measurements of the chosen (flat) setting.
BANKING_AB = {"SURFERS OVAL": (False, 977), "SURFERS ROAD": (False, 587)}


@pytest.mark.parametrize("name", sorted(BANKING_AB))
def test_banking_ab_on_the_surfers_courses(tmp_path, romset_zip, saturn_cue, name):
    from dataclasses import replace
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.tencourse import COURSES, build_all, ten_course_set
    plan = next(p for p in COURSES if p.name == name)
    results = {}
    for banking in (False, True):
        rs = RomSet.from_zip(romset_zip)
        out, conv = build_all(rs, saturn_cue, [replace(plan, banking=banking)])
        out = ten_course_set(out, conv)
        samples = _drive_entry(tmp_path / f"b{int(banking)}", out, romset_zip, 3, conv[0], seconds=90)
        results[banking] = lap_progress(samples, lambda x, z: arc_of(conv[0].lap, x, z), conv[0].lap.length)
    print("BANKING A/B", name, results)
    expected = BANKING_AB[name]
    if expected is not None:                                                     # pinned after the first run
        chosen, forward = expected
        assert plan.banking == chosen
        assert results[chosen]["forward"] >= 0.9 * forward, results


def _race(tmp_path, out, romset_zip, entry, c, seconds=150, reverse=False, extra_env=None):
    """Race `entry` under the autopilot with RAM and entity-pool dumps every 250 frames from 1600; returns the workdir.
    Phase 26: `extra_env` adds loggers (the reverse race's race, edge and field logs)."""
    from vrtools.mame.runner import DUMP_STEP
    frames = ",".join(str(f) for f in range(1600, int(seconds * 57.5), DUMP_STEP))
    wd = tmp_path / f"entry{entry}"
    _drive_entry(tmp_path, out, romset_zip, entry, c, seconds=seconds, reverse=reverse,
                 extra_env={"VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_DUMP": frames, "VR_TRACE_FROM": "0", "VR_TRACE_TO": "0",
                            "VR_RATE_LOG": str(wd / "rate.txt"), **(extra_env or {})})
    return wd


# The three originals under the same autopilot (its line = road line 0), 150 s, measured 31 Oct 2026 (extensions
# fired, frame the clock expired): Big Forest 6 / never, Bay Bridge 2 / 7350, Acropolis 4 / never. The autopilot is
# not the game's intended driver (45 units/s against ~100 for a human at pace), and a converted course's clock per
# unit of road equals its template's by construction, so this gate checks the mechanics — the entry's own tables
# are in use and its checkpoints fire — and leaves the balance to the playtest (design decision 11). The report is
# printed for the write-up. The Surfers Oval is exempt from the extension check: under this driver it crawls on the
# inner verge (Phase 8, `MIN_FORWARD`) and never reaches its first checkpoint 1290 units out.
TEMPLATE_BASELINE = {2: (6, None), 0: (2, 7350), 1: (4, None)}            # template data index -> (extensions, expired_at)
NO_EXTENSION_EXPECTED = {"SURFERS OVAL"}
# The field with the cursor rule (31 Oct 2026, 150 s): opponents that gained >= 100 road points / the leader's gain —
# Alpine 15 / 492, Amazon Falls 14 / 330, Diablo Canyon 12 / 309, Metropolis 13 / 592, Pacific Coast 12 / 300+,
# Surfers Oval 9 / 294, Surfers Road 9 / 212, regenerated Big Forest 11 / 607; the original Big Forest 15 / 877. On the
# Bay Bridge / Acropolis-template courses the game lines the field up single file in front of the player, the slowest car
# first, and our fixed-offset lines give the pack no overtaking room, so the field queues (open: AI lines).
# Phase 11 (tarmac under the field, verges from the road's measured edge; docs/spike/2026-11-field-coverage.md): every
# field moves 15 / 15 with no backstep, the leader gains 701–895 points in 150 s (6.5–7.6 points/s; the originals
# 858–1219, 7.5–10.4), and no opponent parks (Diablo Canyon 1 in its shorter window: its race expires at 8350).
MOVED_FLOOR, BACKSTEP_MAX, LEADER_FLOOR = 14, 25, 500
MOVED_FLOORS: dict[str, int] = {}
# Phase 11: opponents parked for good (no progress over the last 35 s of the race). Measured 0 on every course after
# the coverage fill and the road verges (Phase 10's build: 4–13 per course); per-course values above the default
# would carry their reason.
PARKED_DEFAULT = 2
PARKED_MAX: dict[str, int] = {}
# The originals' cursors lead the car's road point by at most 4 points; ours by up to one merged quad (14 points on
# the Saturn courses) plus a straddling end slice: measured 8–16 on the Phase 11 build (7–23 in Phase 10, 32 before
# its fix pass). A cursor far ahead means it ran away after the wrap (review).
CURSOR_LEAD_MAX = 20
# Phase 16 fix pass: on Metropolis opponent 1 runs wide onto the grass beside the start straight for ~10 s, 34-40 units
# out; its cursor stays where the car is (21, the car's nearest point 12-20) while its road point keeps the grass quad's
# 4. Not a runaway cursor: the road point lags on the verge.
CURSOR_LEAD_MAXES: dict[str, int] = {"METROPOLIS": 24, "PACIFIC COAST": 24, "SURFERS ROAD": 40}   # Phase 22a (Pascal: a separate pass): an opponent
# crawling over the 12-unit start-line band (traffic) is credited the last point that long and its cursor runs on (41 at
# 12 units/s), then it cuts across the grass towards it — the band's weakness, open
# Phase 22j (continuous tarmac): on Surfers Road opponents 1 and 2, the slowest, used to stall for good on the crest 25
# units before the line (road point 439 at 150 s, lead 10); on one surface they crawl over it and the band at ~34
# units/s and their cursors run on to 27-30 at the line (the band's mechanism above), then the car catches up by point
# 40 on the straight. Measured 5 Nov 2026: main 10 with the two stalled, the branch 27 with the whole field lapping.
# Phase 22k: 36 — the same run-on sampled later in the crossing (car 2 reached the line 4 s later than in 22j and its
# cursor ran to 43 at the usual ~12 points/s; nothing at the line changed); it then aimed past the first bend, cut the
# grass and was put back. Bounded at 40; the run-on itself is the band's open weakness (docs/follow-ups.md).
# Phase 22m: the run-on halved at its source — a quad is credited the last road point its front has reached, so the
# band alone carries n−1 (the piece before it, cut at the band's rear 12.5 units before the line, was nearest to the
# last point 10 units before it and took it too): Surfers Road measured 7 (per-frame log: cars sit on the last point
# 10–18 frames over 12–14 units, leads 4–8 at the wrap; the original's 8–14 frames, 3–6). The bound stays 40 until
# Pascal says otherwise (test-bound changes are his).
# The regenerated Big Forest is a harness course (the Saturn file's degenerate 1300-unit sliver, its pit strip beside
# the start straight): its cursors lead by 38–63 points at the start only (cars at road point 10 with cursors at
# 40–65 on the strip quads; it varies run to run), 4–14 afterwards. Not a deliverable: the lead is reported, not
# gated, there; the deliverable courses are gated at CURSOR_LEAD_MAX.
# Phase 10: the autopilot cannot overtake and on the Oval and Surfers Road it stood behind parked opponents, never
# clearing its first checkpoint. With no car parked (Phase 11) it gets 6 and 3 extensions there: the set is empty and
# the extension check runs on every course.
BOXED_IN: set[str] = set()
# Phase 18: with the Saturn's terrain, road paint and structures every course still renders at the arcade's 28-29 list
# switches per 57 frames (Pascal: 60 fps non-negotiable); the floor is the Phase 6 Alpine gate's.
RATE_FLOOR = 27


@pytest.mark.parametrize("k", range(7))
def test_each_course_races_on_its_own_tables(tmp_path, romset_zip, saturn_cue, k):
    from vrtools.arcade.race import race_blob_layout
    from vrtools.mame.runner import race_report
    out, conv = _seven(romset_zip, saturn_cue)
    c = conv[k]
    wd = _race(tmp_path, out, romset_zip, 3 + k, c, seconds=150)
    r = race_report(wd, len(c.centreline))
    print("RACE", c.entry.name, {kk: v for kk, v in r.items() if kk != "frames"})
    lay = race_blob_layout(c.entry.race)
    assert r["time_record"] == lay["records"] and r["checkpoint_record"] == lay["checkpoints"]   # its own blob, level 0
    assert r["laps_setting"] == 5
    if c.entry.name not in NO_EXTENSION_EXPECTED | BOXED_IN:
        assert r["extensions"] >= 1, r                                          # the converted checkpoints fire
    assert r["opponents_at_origin"] == 0, r                                     # every opponent spawned on its grid slot (eight line pointers)
    assert r["moved"] >= MOVED_FLOORS.get(c.entry.name, MOVED_FLOOR), {k: r[k] for k in ("moved", "cars")}   # the field drives (Phase 10)
    assert r["max_backstep"] <= BACKSTEP_MAX, {k: r[k] for k in ("max_backstep", "cars")}
    assert r["max_cursor_lead"] <= CURSOR_LEAD_MAXES.get(c.entry.name, CURSOR_LEAD_MAX), r["max_cursor_lead"]           # no cursor running away at the start line
    assert r["leader_points"] >= LEADER_FLOOR, r
    assert r["parked"] <= PARKED_MAX.get(c.entry.name, PARKED_DEFAULT), {k: r[k] for k in ("parked", "parked_cars")}   # Phase 11
    from vrtools.mame.runner import parse_rate
    rate = [n for f, n in parse_rate(wd / "rate.txt") if f > 2000]
    assert rate and min(rate) >= RATE_FLOOR, (c.entry.name, min(rate) if rate else None)      # Phase 18: the Saturn's layers keep the arcade's rate


def test_regenerated_big_forest_field_races(tmp_path, romset_zip, saturn_cue):
    """Phase 10: Big Forest regenerated from the Saturn data (Phase 6 tables in its own bank) had a field that did not
    move at all; with the end slices unmerged, the end road points pinned and floor-mapped links the opponents drive."""
    from vrtools.arcade.bank import build_bank, install_bank
    from vrtools.arcade.patch import patch_collision
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.tencourse import load_saturn_course
    from vrtools.convert.collision import saturn_collision
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.road import road_tables
    from vrtools.mame.runner import DUMP_STEP, race_report
    rs = RomSet.from_zip(romset_zip)
    sat = load_saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    col, cells = saturn_collision(sat, height=lambda x, z: 30.0, lap=lap, merge=True, cover=True)   # as the build (Phase 11)
    t = road_tables(lap, col.quads[:col.n_tarmac])
    out = install_bank(rs, 0, build_bank(rs, 0, t, [0] * 128 * 128, col.surface))
    out = patch_collision(out, 0, col, slot=2, force=True, cell_offsets=cells)
    build = _build(tmp_path, romset_zip, out)
    wd = tmp_path / "regen"
    frames = ",".join(str(f) for f in range(1600, int(150 * 57.5), DUMP_STEP))
    cl = centreline(lap)
    run_mame(LUA_DIR / "autoplay.lua", 150, wd, build, env={"VR_COURSE": "0", "VR_COLLISION_LOG": str(wd / "c.txt"),
             "VR_AUTOPILOT": str(write_centreline(wd / "centreline.csv", cl)), "VR_TRACE_LOG": str(wd / "trace.log"),
             "VR_TRACE_DUMP": frames, "VR_TRACE_FROM": "0", "VR_TRACE_TO": "0"})
    r = race_report(wd, len(cl))
    print("RACE regenerated Big Forest", {k: v for k, v in r.items() if k not in ("frames", "clock")})
    # a harness course (flat height, the Saturn file's 1300-unit sliver and its pit strip beside the start straight, where
    # the strip quads carry road points 40–65): Phase 11 measured 15 / 0 parked and 13 / 3 parked in two runs of the same
    # code; the deliverables are gated at MOVED_FLOOR, this one at Phase 10's 11, and its lead is reported, not gated
    assert r["moved"] >= 11 and r["max_backstep"] <= BACKSTEP_MAX and r["leader_points"] >= 350, r
    assert r["extensions"] >= 3, r                                               # the player is unaffected


def test_race_report_counts_parked_cars():
    """Phase 11: opponents that stop for good are what a player meets on the road. `parked` = opponents whose
    unwrapped progress did not change over the last 8 dumps of the race window (a running race only); the original
    Big Forest has none, the Phase 10 Metropolis build at least four (pairs at road points 43 and 264)."""
    import os
    from pathlib import Path
    from vrtools.mame.runner import race_report
    if not Path("out/p10/build/race0").is_dir():
        pytest.skip("needs the kept Phase 10 race dumps in out/p10/build")
    orig = race_report(Path("out/p10/build/race0"), 338)
    metro = race_report(Path("out/p10/build/race6"), 365)
    assert orig["parked"] == 0 and orig["parked_cars"] == []
    assert metro["parked"] >= 4 and len(metro["parked_cars"]) == metro["parked"] and all(1 <= c <= 15 for c in metro["parked_cars"])


# Phase 14: the HUD map is car-centred and heading-up; the player's cross is a 3x3 tile block the game draws once at race
# start. An anticlockwise course shifts both 11 cells right (directory map_tx 237.0, map_cross 22); the originals stay.
CROSS = {(0, 0): 0xA73A, (1, 0): 0xA73B, (2, 0): 0xA73C, (0, 1): 0xA73D, (1, 1): 0xA400, (2, 1): 0xA73E, (0, 2): 0xA73F, (1, 2): 0xA740, (2, 2): 0xA741}
BLANK = 0x8020


@pytest.mark.parametrize("entry,tx,col,limit", [(0, 149.0, 48, 128), (3, 237.0, 59, 128)])   # Big Forest as the game has it; Alpine shifted (22a: the limit is 128 everywhere)
def test_the_hud_map_and_the_cross_move_together(tmp_path, romset_zip, saturn_cue, entry, tx, col, limit):
    out, conv = _seven(romset_zip, saturn_cue)
    wd = tmp_path / f"hud{entry}"
    _drive_entry(wd, out, romset_zip, entry, conv[entry - 3] if entry >= 3 else None, seconds=50,
                 extra_env={"VR_HUDMAP_LOG": str(wd / f"entry{entry}" / "h.txt")})
    h = parse_hudmap(wd / f"entry{entry}" / "h.txt")
    assert (h["tx"], h["ty"]) == (tx, 12.0)
    assert h["ram"] == (tx, 2 * (col - 48), limit)             # the loader ran for this entry: an original carries the game's own
    other = 59 if col == 48 else 48                            # values (review focus 1), a shifted course its own
    assert all(h["cells"][(col + dx, 21 + dy)] == code for (dx, dy), code in CROSS.items()), h["cells"]
    assert all(h["cells"][(other + dx, 21 + dy)] == BLANK for dx in range(3) for dy in range(3)), h["cells"]


def _lateral(s, centreline):
    return min(math.hypot(s.x - px, s.z - pz) for px, pz in centreline)


@pytest.mark.parametrize("entry", [3, 7])                      # Alpine, Pacific Coast: anticlockwise, water beside the road
def test_a_swerve_meets_the_wall(tmp_path, romset_zip, saturn_cue, entry):
    """Phase 16: the run-off ends in a wall (surface 5) 30 units past the road's edge. A 50-frame wheel input from race
    start + 500 takes the car off the road: it never gets past the wall (the road's half-width is under 20 units: at most
    20 + 30 + 6), it is slowed by at least 30 % within 100 frames of the furthest point, it is never without a quad under
    it, and it is back within 10 units of the centreline inside 300 frames. (Phase 14 measured 111 units out on grass.)
    Phase 22a: the swerve's start is the first sample past 10 units (it was 20: the wall now stands at the drawn barrier,
    and Alpine's swerve meets it 13.6 out)."""
    out, conv = _seven(romset_zip, saturn_cue)
    c = conv[entry - 3]
    samples = _drive_entry(tmp_path / f"wall{entry}", out, romset_zip, entry, c, seconds=60, extra_env={"VR_RACE_STEER": "500:50:95"},
                           autopilot=False)
    start = samples[0].frame
    lat = [(s, _lateral(s, c.centreline)) for s in samples if s.frame >= start + 450]
    t0 = next(s.frame for s, d in lat if d > 10)              # Phase 22a: past the AI lines (the wall at a drawn barrier can
                                                                  # stand at 12.5: Alpine's swerve meets it 13.6 out, on the road)
    assert 0 <= t0 - (start + 500) <= 150, t0 - (start + 500)
    window = [(s, d) for s, d in lat if t0 <= s.frame <= t0 + 300]
    peak_s, peak = max(window, key=lambda sd: sd[1])
    assert peak <= 56.0, peak
    assert not any(_no_hit(s) for s, _ in window)
    def speed(i):
        a, b = window[i - 1][0], window[i][0]
        return math.hypot(b.x - a.x, b.z - a.z) / max(1, b.frame - a.frame)
    k = next(i for i, (s, _) in enumerate(window) if s is peak_s)
    before = max(speed(i) for i in range(1, max(2, k)))
    after = min(speed(i) for i in range(max(1, k), min(len(window), k + 50)))
    assert after <= 0.7 * before, (round(before, 2), round(after, 2))
    assert any(d < 10 for _, d in window), [round(d) for _, d in window][::5]


# Phase 15: an opponent's roll and pitch move toward the low halves of its road point's heading and link words; the converter
# wrote 0 and every opponent stayed flat (Alpine: sd 0.00). Big Forest's opponents measure roll (+0x2e) sd 4.7-5.2 deg, pitch
# (+0x2a) sd 1.2 (Phase 16 recon §1: the Phase 15 recon had the two names swapped).
DEG = 360 / 65536


def _moving(samples, car, step=3.0):
    """A car's samples while it moves (consecutive samples more than `step` units apart)."""
    own = [s for s in samples if s.car == car]
    return [b for a, b in zip(own, own[1:]) if math.hypot(b.x - a.x, b.z - a.z) > step]


@pytest.mark.parametrize("entry", [3, 7])                      # Alpine, Pacific Coast
def test_opponents_pitch_and_lean_on_converted_courses(tmp_path, romset_zip, saturn_cue, entry):
    import statistics
    out, conv = _seven(romset_zip, saturn_cue)
    c = conv[entry - 3]
    wd = tmp_path / f"att{entry}"
    _drive_entry(wd, out, romset_zip, entry, c, seconds=90, extra_env={"VR_ATTITUDE_LOG": str(wd / f"entry{entry}" / "a.txt"), "VR_ATTITUDE_CARS": "4"})
    samples = parse_attitude(wd / f"entry{entry}" / "a.txt")
    for car in (1, 2, 3):
        s = _moving(samples, car)
        assert len(s) > 100, (car, len(s))
        assert 1.0 < statistics.pstdev([q.pitch for q in s]) * DEG < 8.0, (car, statistics.pstdev([q.pitch for q in s]) * DEG)
        assert statistics.pstdev([q.roll for q in s]) * DEG > 0.5, (car, statistics.pstdev([q.roll for q in s]) * DEG)
        assert max(abs(q.pitch) for q in s) <= 3800 and max(abs(q.roll) for q in s) <= 3800


def test_the_originals_opponents_are_unchanged(tmp_path, romset_zip, saturn_cue):
    """Big Forest's tables are untouched: its opponents keep their authored roll (+0x2e: sd 4.7-5.2 deg over 90 s on its
    banked bends; a 60 s run read 2.9); pins the logger and the reading of the right field."""
    import statistics
    out, _conv = _seven(romset_zip, saturn_cue)
    wd = tmp_path / "att0"
    _drive_entry(wd, out, romset_zip, 0, None, seconds=90, extra_env={"VR_ATTITUDE_LOG": str(wd / "entry0" / "a.txt"), "VR_ATTITUDE_CARS": "4"})
    samples = parse_attitude(wd / "entry0" / "a.txt")
    for car in (1, 2, 3):
        s = _moving(samples, car)
        assert len(s) > 100
        assert 2.0 < statistics.pstdev([q.roll for q in s]) * DEG < 8.0, (car, statistics.pstdev([q.roll for q in s]) * DEG)


def _pitch_follows_the_target(samples, build_zip, entry):
    """Per opponent (cars 1-3), the correlation of its +0x2a with the pitch target (heading low half) of the road point
    nearest it, over its moving samples."""
    import statistics
    from vrtools.arcade.course import course_entry_at, road_lines
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.romset import RomSet
    rs = RomSet.from_zip(build_zip, verify=False)
    e10 = decode_directory(rs)[entry]
    pts = road_lines(rs, course_entry_at(rs, e10.bank, window_base=e10.header_base))[0]
    target = [((p.heading & 0xFFFF) ^ 0x8000) - 0x8000 for p in pts]
    out = {}
    for car in (1, 2, 3):
        obs, tgt = [], []
        for s in _moving(samples, car):
            k = min(range(len(pts)), key=lambda j: (pts[j].x - s.x) ** 2 + (pts[j].z - s.z) ** 2)
            obs.append(s.pitch); tgt.append(target[k])
        mo, mt = statistics.mean(obs), statistics.mean(tgt)
        cov = sum((x - mo) * (y - mt) for x, y in zip(obs, tgt))
        var = math.sqrt(sum((x - mo) ** 2 for x in obs) * sum((y - mt) ** 2 for y in tgt)) or 1.0
        out[car] = cov / var
    return out


def test_opponents_pitch_with_the_slope(tmp_path, romset_zip, saturn_cue):
    """Phase 16: +0x2a is an opponent's PITCH (positive climbing) and moves toward its road point's heading low half,
    where the converter now writes the profile's slope (its sign pinned on Alpine's climb by the all-course road test).
    Each opponent's +0x2a must follow the target at the point it is on (correlation >= 0.8; measured 0.92-0.95). Its own
    height change is not the reference: the player's collision heights still staircase on zigzag strips until Task 2."""
    out, conv = _seven(romset_zip, saturn_cue)
    wd = tmp_path / "slope3"
    _drive_entry(wd, out, romset_zip, 3, conv[0], seconds=90, extra_env={"VR_ATTITUDE_LOG": str(wd / "entry3" / "a.txt"), "VR_ATTITUDE_CARS": "4"})
    corr = _pitch_follows_the_target(parse_attitude(wd / "entry3" / "a.txt"), wd / "build" / "vr.zip", 3)
    assert all(c >= 0.8 for c in corr.values()), corr


def _windows(samples, car, field, w=5, min_ds=30.0):
    """(own slope in radians, mean of `field`) over 2w-sample windows while the car moves."""
    import statistics
    own = [s for s in samples if s.car == car]
    out = []
    for i in range(w, len(own) - w):
        ds = sum(math.hypot(own[j + 1].x - own[j].x, own[j + 1].z - own[j].z) for j in range(i - w, i + w))
        if ds >= min_ds:
            out.append((math.atan2(own[i + w].y - own[i - w].y, ds), statistics.mean(getattr(q, field) for q in own[i - w:i + w])))
    return out


def _pitch_jumps(samples, car, over_deg, min_step=3.0):
    """(frame, change in degrees) for each pair of consecutive samples of `car` moving at least `min_step` units whose
    pitch changes by more than `over_deg` degrees."""
    own = [s for s in samples if s.car == car]
    return [(b.frame, round((b.pitch - a.pitch) * DEG, 1)) for a, b in zip(own, own[1:])
            if math.hypot(b.x - a.x, b.z - a.z) >= min_step and abs(b.pitch - a.pitch) * DEG > over_deg]


def test_the_player_pitch_is_smooth_on_diablo(tmp_path, romset_zip, saturn_cue):
    """Phase 16 (recon §3): the collision follows the arc profile, so the player's pitch (+0x2a) changes smoothly as it
    climbs Diablo Canyon instead of stepping: over 90 s, at most 10 pairs of consecutive moving samples (10 frames apart)
    whose pitch jumps by more than 6 deg, none by more than 15 deg (Phase 18b: 8 became 10 when the autopilot's line moved
    with the frame timing, on byte-identical collision; the staircase's jumps were -34/-20/+16 deg). Measured: the Phase 15 build's 2-D heights 15 (the staircase: -34, -20, +16 deg
    ...), this build 6, two of them one sample at -87 deg where a wheel crosses a hole in the tarmac that predates Phase 16
    (fix-pass ruling: the window correlation this test first used fell from 0.60 to 0.43 on that one sample, and a median
    or glitch-free correlation scores 0.95-0.99 on both builds, so it cannot tell a staircase from a smooth climb)."""
    out, conv = _seven(romset_zip, saturn_cue)
    k = next(i for i, c in enumerate(conv) if c.entry.name == "DIABLO CANYON")
    wd = tmp_path / "diablo"
    _drive_entry(wd, out, romset_zip, 3 + k, conv[k], seconds=90, extra_env={"VR_ATTITUDE_LOG": str(wd / f"entry{3 + k}" / "a.txt"), "VR_ATTITUDE_CARS": "1"})
    samples = parse_attitude(wd / f"entry{3 + k}" / "a.txt")
    assert len(_moving(samples, 0)) > 200, len(_moving(samples, 0))
    jumps = _pitch_jumps(samples, 0, 6.0)
    assert len(jumps) <= 10 and all(abs(d) <= 15.0 for _, d in jumps), jumps     # Phase 18b: the count follows the autopilot's
                                                                                    # line (10 at 6-11 deg on the same collision)


def test_the_player_banks_on_a_cambered_course(tmp_path, romset_zip, saturn_cue):
    """Phase 16 (recon §2): the collision quads carry the slice camber, so the player's roll (+0x2e) follows the road's
    camber where the car is: on Surfers Oval (banked bends), over the moving samples on a stretch whose camber exceeds
    3 deg, the roll has the camber's sign (negative = right side up) on at least 70 % of them and is not flat (sd > 1 deg)."""
    import statistics
    from vrtools.arcade.course import course_entry_at, road_lines
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.romset import RomSet
    out, conv = _seven(romset_zip, saturn_cue)
    k = next(i for i, c in enumerate(conv) if c.entry.name == "SURFERS OVAL")
    wd = tmp_path / "oval"
    _drive_entry(wd, out, romset_zip, 3 + k, conv[k], seconds=90, extra_env={"VR_ATTITUDE_LOG": str(wd / f"entry{3 + k}" / "a.txt"), "VR_ATTITUDE_CARS": "1"})
    samples = _moving(parse_attitude(wd / f"entry{3 + k}" / "a.txt"), 0)
    rs = RomSet.from_zip(wd / "build" / "vr.zip", verify=False)
    e10 = decode_directory(rs)[3 + k]
    pts = road_lines(rs, course_entry_at(rs, e10.bank, window_base=e10.header_base))[0]
    camber = [((p.link & 0xFFFF) ^ 0x8000) - 0x8000 for p in pts]          # the roll target written for the point: the camber, game sign
    banked = []
    for s in samples:
        j = min(range(len(pts)), key=lambda i: (pts[i].x - s.x) ** 2 + (pts[i].z - s.z) ** 2)
        if abs(camber[j]) > 3 * 182 and math.hypot(pts[j].x - s.x, pts[j].z - s.z) < 10:
            banked.append((camber[j], s.roll))
    assert len(banked) > 20, len(banked)
    same = sum(1 for c, r in banked if (c > 0) == (r > 0) and abs(r) > 50)
    assert same >= 0.7 * len(banked), (same, len(banked))
    assert statistics.pstdev([r for _, r in banked]) * DEG > 1.0


def _slot_render(tile: bytes, char: bytes, pal: bytes, s: int):
    """Slot s's layer-B picture as the tile chip draws it from the dumped RAM (168 x 128 RGB)."""
    import struct
    import numpy as np
    from vrtools.arcade.panel import char_pixels
    from vrtools.arcade.select import SLOT_B
    img = np.zeros((168, 128, 3), int)
    for row in range(21):
        for col in range(16):
            w = struct.unpack_from("<H", tile, SLOT_B[s] - 0x700000 + row * 0x80 + col * 2)[0]
            c = w & 0x3FFF
            px = char_pixels(char[32 * c:32 * c + 32])
            for y in range(8):
                for x in range(8):
                    cw = struct.unpack_from("<H", pal, 2 * (16 * (c >> 7) + px[y][x]))[0]
                    img[row * 8 + y, col * 8 + x] = ((cw & 31) * 8, (cw >> 5 & 31) * 8, (cw >> 10 & 31) * 8)
    return img


def _select_run(tmp_path, romset_zip, saturn_cue, env):
    from tests.test_tencourse import _records
    out, conv = _seven(romset_zip, saturn_cue)
    build = _build(tmp_path, romset_zip, out)
    wd = tmp_path / "select"
    wd.mkdir(parents=True, exist_ok=True)
    run_mame(LUA_DIR / "autoplay.lua", 30, wd, build, env={"VR_COURSE": "0", "VR_SELECT_DIR": str(wd), **env})
    dumps = {}
    for f in wd.glob("*_tile.bin"):
        frame, menu = (int(v) for v in f.name.split("_")[:2])
        dumps[frame] = (menu, f.read_bytes(), (wd / f.name.replace("tile", "char")).read_bytes(), (wd / f.name.replace("tile", "pal")).read_bytes())
    return out, _records(out), dumps


def test_the_select_sweep_shows_every_picture(tmp_path, romset_zip, saturn_cue):
    """Phase 21: the wheel sweeps across all ten entries; at 1, 2, 3 and 10 frames after each change of the window every
    slot shows, from character, palette and tile RAM, exactly its entry's picture (the record rendered from the ROM),
    nothing (all its tile words the blank character), or, while the draw has not reached it, the previous window's
    picture whole (review: never a picture caught mid-copy); every entry
    is shown exactly at least once; character blocks 0-95 and palettes 0-95 never change from what the boot left."""
    import struct
    import numpy as np
    from vrtools.arcade.select import BLANK_TILE, SLOT_B, visible_entries
    from tests.test_tencourse import render_record
    out, (table, recs, read), dumps = _select_run(tmp_path, romset_zip, saturn_cue, {"VR_WHEEL": "61", "VR_WHEEL_SWEEP": "61:195:300"})
    base = dumps.pop(min(dumps))
    seen, bad, blank_seen, prev = set(), [], 0, None
    for frame, (menu, tile, char, pal) in sorted(dumps.items()):
        # the select screen: after START (720), before the course press: 1400 on an original, 1200 (autoplay.lua's DIR_PRESS) on an
        # entry with a reverse variant, whose lock opens the direction screen. The window is kept: this run dumps only on changes of
        # the shown index, and the sweep (735 + 300 frames) has stopped moving the index before 1200
        if frame < 735 or frame > 1390:
            prev = menu
            continue
        for s, entry in enumerate(visible_entries(menu)):
            words = {struct.unpack_from("<H", tile, SLOT_B[s] - 0x700000 + r * 0x80 + 2 * c)[0] for r in range(21) for c in range(16)}
            shown = _slot_render(tile, char, pal, s)
            if words == {BLANK_TILE}:
                blank_seen += 1
            elif np.array_equal(shown, render_record(read, recs[entry])):
                seen.add(entry)
            elif prev is not None and np.array_equal(shown, render_record(read, recs[visible_entries(prev)[s]])):
                pass                                                       # the draw has not reached this slot yet: its old picture, whole
            else:
                bad.append((frame, menu, s, entry))
        prev = menu
        assert char[:96 * 128 * 32] == base[2][:96 * 128 * 32], frame
        assert pal[:96 * 32] == base[3][:96 * 32], frame
        assert not any(char[32 * (BLANK_TILE & 0x3FFF):32 * (BLANK_TILE & 0x3FFF) + 32]), frame   # the blank stays transparent
    assert seen == set(range(10)), sorted(seen)
    assert not bad, bad[:6]


# Phase 21's test_start_greys_the_other_courses (Diablo Canyon, entry 5: the chosen slot in colour, its neighbours grey at
# 1406/1415) is retired with Phase 26 stage 3: on a course with a reverse variant the course lock opens the COURSE DIRECTION
# screen (plan D7), and a converted course's START look is the direction screen's, pinned from Task 4 by
# tests/test_dirscreen_build.py::test_the_lock_keeps_the_chosen_picture_in_colour.


def test_start_on_an_original_greys_its_neighbours(tmp_path, romset_zip, saturn_cue):
    """Phase 21 review: with Acropolis chosen (entry 2: window 1, 2, 3) slot 1 gets Acropolis's chosen picture set and its
    layer-A palettes their chosen set; slot 0 (Bay Bridge) and its layer-A palettes their grey sets; slot 2 (the first
    new course) its grey set: an original's sets copied into a slot other than its own."""
    import struct
    from vrtools.arcade.select import SLOT_PAL, WHEEL_FOR_ENTRY
    out, (table, recs, read), dumps = _select_run(tmp_path, romset_zip, saturn_cue, {"VR_WHEEL": str(WHEEL_FOR_ENTRY[2]), "VR_SELECT_DUMP": "1406,1415"})
    got = {f: d for f, d in dumps.items() if f in (1406, 1415)}
    assert got, sorted(dumps)
    for frame, (menu, tile, char, pal) in got.items():
        assert menu == 2
        words = lambda addr, n: struct.unpack_from(f"<{n}H", pal, addr - 0x900000)
        assert words(SLOT_PAL[1], 48) == struct.unpack("<48H", read(recs[2].chosen_addr, 96)), frame
        assert words(SLOT_PAL[0], 48) == struct.unpack("<48H", read(recs[1].grey_addr, 96)), frame
        assert words(SLOT_PAL[2], 48) == struct.unpack("<48H", read(recs[3].grey_addr, 96)), frame
        assert words(recs[2].a_dst, 32) == struct.unpack("<32H", read(recs[2].a_chosen_addr, 64)), frame
        assert words(recs[1].a_dst, 32) == struct.unpack("<32H", read(recs[1].a_grey_addr, 64)), frame


def test_the_player_rolls_with_a_banked_curve(tmp_path, romset_zip, saturn_cue):
    """Phase 22a (recon §1): on Surfers Road's banked curves the player's roll (+0x2e, negative = right side up) follows
    the drawn road: on samples where it banks more than 8 degrees the roll has the opposite sign and its mean magnitude
    is at least 75 % of the mean drawn bank (measured: 49 % with the side tilt capped at 1.3 units, the car sinking into
    the road; 110 % with the drawn banking)."""
    import vrtools.arcade.tencourse as tc
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.collision import mesh_heights
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import _ground_quads, arc_height, road_profile
    out, conv = _seven(romset_zip, saturn_cue)
    k = next(i for i, c in enumerate(conv) if c.entry.name == "SURFERS ROAD")
    wd = tmp_path / "bank"
    _drive_entry(wd, out, romset_zip, 3 + k, conv[k], seconds=90,
                 extra_env={"VR_ATTITUDE_LOG": str(wd / f"entry{3 + k}" / "a.txt"), "VR_ATTITUDE_CARS": "1", "VR_ATTITUDE_EVERY": "5"})
    samples = [s for s in parse_attitude(wd / f"entry{3 + k}" / "a.txt") if s.car == 0]
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in tc.COURSES if p.name == "SURFERS ROAD")
    sat = tc.load_saturn_course(saturn_cue, plan.path)
    gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    pairs = []
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        hs = mesh_heights(_ground_quads(sat))
        cl = centreline(lap, spacing=5.0)
        n = len(cl)
        for s in samples:
            j = min(range(n), key=lambda i: (cl[i][0] - s.x) ** 2 + (cl[i][1] - s.z) ** 2)
            (ax, az), (bx, bz) = cl[j - 1], cl[(j + 1) % n]
            d = math.hypot(bx - ax, bz - az) or 1.0
            rx, rz = (bz - az) / d, -(bx - ax) / d
            ends = []
            for lat in (-8.0, 8.0):
                px, pz = cl[j][0] + lat * rx, cl[j][1] + lat * rz
                near = [v for v in hs(px, pz) if abs(v - hfn(px, pz)) < 8.0]
                ends.append(min(near, key=lambda v: abs(v - hfn(px, pz))) if near else None)
            if None not in ends:
                bank = math.degrees(math.atan2(ends[1] - ends[0], 16.0))
                if abs(bank) > 8.0:
                    pairs.append((bank, s.roll * 360 / 65536))
    assert len(pairs) >= 20, len(pairs)
    assert sum(1 for b, r in pairs if b * r < 0) >= 0.9 * len(pairs), pairs[:10]
    mean_bank = sum(abs(b) for b, _ in pairs) / len(pairs)
    mean_roll = sum(abs(r) for _, r in pairs) / len(pairs)
    assert mean_roll >= 0.75 * mean_bank, (round(mean_roll, 1), round(mean_bank, 1))


REC = Path(__file__).resolve().parent.parent / "out" / "rec"       # Pascal's recorded drive (local, never committed)


def test_pascals_diablo_drive_stays_on_the_drawn_road(tmp_path, romset_zip, saturn_cue):
    """Phase 22a rework: Pascal's Diablo Canyon drive (out/rec/inp/drive.inp, recorded from the saved state out/rec/start),
    replayed on this build with cars 0-3 logged every frame: during the race every car is within 1.5 units of the drawn
    ground (the Saturn ground mesh, the level nearest the car) at 99 % of its samples with ground under it. Before: the
    player and the opponents drifted 13-32 units out on the banked curves and sat 1-7 units under the drawn road at 5-6 %
    of their samples."""
    import shutil
    import subprocess
    import os
    import vrtools.arcade.tencourse as tc
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.collision import mesh_heights
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import _ground_quads
    if not ((REC / "inp" / "drive.inp").is_file() and (REC / "start" / "nvram").is_dir()):
        pytest.skip("no recorded drive in out/rec")
    out, conv = _seven(romset_zip, saturn_cue)
    build = _build(tmp_path, romset_zip, out)
    wd = tmp_path / "replay"
    shutil.copytree(REC / "start" / "nvram", wd / "nvram")
    shutil.copytree(REC / "start" / "cfg", wd / "cfg")
    cmd = ["mame", "vr", "-rompath", str(build), "-video", "none", "-sound", "none", "-window", "-nothrottle", "-str", "130",
           "-skip_gameinfo", "-autoboot_script", str(LUA_DIR / "replay.lua"), "-snapshot_directory", str(wd / "snap"),
           "-nvram_directory", str(wd / "nvram"), "-cfg_directory", str(wd / "cfg"), "-input_directory", str(REC / "inp"),
           "-playback", "drive.inp"]
    env = {**os.environ, "VR_LUA_DIR": str(LUA_DIR), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_ATTITUDE_LOG": str(wd / "a.txt"),
           "VR_ATTITUDE_CARS": "4", "VR_ATTITUDE_EVERY": "1", "VR_ATTITUDE_FROM": "1200", "VR_SNAP_EVERY": "100000"}
    subprocess.run(cmd, cwd=wd, env=env, capture_output=True, text=True, timeout=1800, check=True)
    samples = parse_attitude(wd / "a.txt")
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in tc.COURSES if p.name == "DIABLO CANYON")
    sat = tc.load_saturn_course(saturn_cue, plan.path)
    gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        hs = mesh_heights(_ground_quads(sat))
    player = {s.frame: s for s in samples if s.car == 0}
    moving = {f for f, s in player.items() if f - 1 in player and math.hypot(s.x - player[f - 1].x, s.z - player[f - 1].z) > 0.05}
    bad = {}
    for car in range(4):
        gaps = []
        for s in samples:
            if s.car == car and s.frame in moving:
                near = [v for v in hs(s.x, s.z) if abs(v - s.y) < 8.0]
                if near:
                    gaps.append(abs(min(near, key=lambda v: abs(v - s.y)) - s.y))
        assert len(gaps) > 1000, (car, len(gaps))
        over = sum(1 for g in gaps if g > 1.5)
        if over > 0.01 * len(gaps):
            bad[car] = (over, len(gaps), round(max(gaps), 2))
    assert not bad, bad


@pytest.mark.parametrize("at", [(-837.3, 562.8), (-777.7, 746.1)])   # point 92 (the first right turn), point 116 (the next)
def test_a_hard_steer_into_diablos_first_right_turn_meets_the_wall(tmp_path, romset_zip, saturn_cue, at):
    """Phase 22a (Pascal: "I drive to the wall at speed and I don't get the crash, instead I go through and then get the
    position reset"): under the autopilot at speed, the wheel held at full lock (20) for 80 frames from Diablo Canyon's
    point 92, into the outside of the first right turn. The car stays inside the wall: over points 85-115 it never gets
    further than 35 units from the centreline (the barrier wall stands 17-29 out there) and never stands over no quad.
    Measured: the build with grass under the wall reached 58.2 units and nothing; with the grass meeting the wall, 16.9.
    Point 116 (Pascal's drive: the road slice runs 6 units past the drawn lip at 23.8, nothing drawn beyond): 58.5 units
    and a fall into a hole in the run-off before the tarmac was trimmed to the drawn edge; 16.0 after."""
    from vrtools.convert.collision import _bboxes, _point_in_xz
    out, conv = _seven(romset_zip, saturn_cue)
    k = next(i for i, c in enumerate(conv) if c.entry.name == "DIABLO CANYON")
    c = conv[k]
    wd = tmp_path / "hit"
    pts = c.centreline
    x92, z92 = min(pts, key=lambda p: math.dist(p, at))                       # the trigger on the centreline
    _drive_entry(wd, out, romset_zip, 3 + k, c, seconds=70,
                 extra_env={"VR_ATTITUDE_LOG": str(wd / f"entry{3 + k}" / "a.txt"), "VR_ATTITUDE_CARS": "1", "VR_ATTITUDE_EVERY": "1",
                            "VR_EXTRA_LUA": str(LUA_DIR / "steer_at.lua"), "VR_STEER_AT": f"{x92}:{z92}:20:80"})
    samples = [a for a in parse_attitude(wd / f"entry{3 + k}" / "a.txt") if a.car == 0]
    cl = [(p[0], p[1]) for p in pts]
    near = [(a, min(range(len(cl)), key=lambda i: math.dist(cl[i], (a.x, a.z)))) for a in samples]
    window = [(a, i) for a, i in near if math.dist(cl[i], at) < 160]          # the turn
    assert len(window) > 100, len(window)
    far = max(math.dist(cl[i], (a.x, a.z)) for a, i in window)
    assert far <= 35.0, far
    assert not any(_no_hit(s) for s in parse_collision(wd / f"entry{3 + k}" / "c.txt") if math.dist((s.x, s.z), at) < 160)
