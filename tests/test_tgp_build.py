"""Build-and-drive tests for the TGP collision patcher (need VR_ROMDIR; each MAME run takes ~50 s)."""
import shutil

import pytest

from vrtools.arcade.patch import patch_collision
from vrtools.arcade.romset import RomSet
from vrtools.arcade.tgp import decode_collision
from vrtools.mame.runner import LUA_DIR, course_of, drive_summary, lap_progress, parse_collision, run_mame, write_centreline


def _build(tmp_path, romset_zip, rs):
    build = tmp_path / "build"
    build.mkdir()
    rs.to_zip(build / "vr.zip", source=romset_zip)
    for extra in ("model1io.zip", "m1comm.zip"):
        shutil.copy(romset_zip.parent / extra, build / extra)
    return build


def _drive(tmp_path, label, rom_dir, seconds=45, extra_env=None, centreline=None):
    """Race course 0 with the probe; with `centreline` (arcade (x, z) points in lap order) the autopilot steers."""
    wd = tmp_path / label
    env = {"VR_COURSE": "0", "VR_COLLISION_LOG": str(wd / "c.txt")}
    if centreline is not None:
        env["VR_AUTOPILOT"] = str(write_centreline(wd / "centreline.csv", centreline))
    env.update(extra_env or {})
    run_mame(LUA_DIR / "autoplay.lua", seconds, wd, rom_dir, env=env)
    return parse_collision(wd / "c.txt")


def test_relocated_big_forest_drives_identically(tmp_path, romset_zip):
    rs = RomSet.from_zip(romset_zip)
    col = decode_collision(rs, 0)
    out = patch_collision(rs, 0, col, slot=2, force=True, strict=False)   # same data copied into the free area
    assert out.copro_data[:4 * 0x4B170] != rs.copro_data[:4 * 0x4B170]   # the slot entry changed ...
    for lo, hi in ((0x30, 0x3FA1), (0x8000, 0xB547), (0x10000, 0x4B170)):   # ... the originals' blocks and pools did not
        assert out.copro_data[4 * lo:4 * hi] == rs.copro_data[4 * lo:4 * hi]  # (the zero fillers between them are allocation space)
    build = _build(tmp_path, romset_zip, out)
    orig = _drive(tmp_path, "orig", romset_zip.parent)
    reloc = _drive(tmp_path, "reloc", build)
    assert len(reloc) > 400 and drive_summary(reloc)["offroad"] == 0
    # the race may start at a different frame in each MAME run (autoplay detects it), so compare from the first
    # sample onwards over the common length: identical data must give identical answers to identical queries
    n = min(len(orig), len(reloc))
    assert n > 400
    assert [(s.quad, s.result_y) for s in reloc[:n]] == [(s.quad, s.result_y) for s in orig[:n]]


def test_saturn_collision_drives_big_forest(tmp_path, romset_zip, saturn_cue):
    from vrtools.convert.collision import saturn_collision
    from tests.test_convert_collision import _saturn_course

    from vrtools.convert.lap import order_slices
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    col, cells = saturn_collision(sat, height=lambda x, z: 30.0, lap=order_slices(sat))   # with road directions
    out = patch_collision(rs, 0, col, slot=2, force=True, cell_offsets=cells)
    build = _build(tmp_path, romset_zip, out)
    samples = _drive(tmp_path, "saturn", build, seconds=60, extra_env={"VR_SNAPS": "1700,2400,3200"})
    assert course_of(tmp_path / "saturn" / "c.txt") == (0, 2), "the run must be Big Forest (data index 2)"
    d = drive_summary(samples)
    assert d["calls"] > 500 and d["onroad_distance"] > 600, d            # the assist needs our segment array and road lines too: Task 6 raises the bar
    # after the exit the car sits in the field for the rest of the run, so the off-road share depends on how early
    # the race started; the stretch before the exit is what is being judged
    assert (d["offroad"] + d["nohit"]) / d["calls"] < 0.10 and d["noanswer"] == 0, d
    assert 28 <= d["ymin"] and d["ymax"] <= 32, d


@pytest.mark.xfail(reason="Phase 22j: without the 4-unit sideways growth the regenerated Big Forest's start area (side-by-side strips) "
                          "leaves seams the coverage fill does not close and the autopilot covers 1546 units in 90 s (was a lap); the "
                          "shipped set never regenerates an original: docs/follow-ups.md", strict=False)
def test_regenerated_big_forest_drives(tmp_path, romset_zip, saturn_cue):
    """Saturn-derived road tables and collision in the arcade bank: the unsteered car follows the road."""
    from vrtools.arcade.bank import build_bank, install_bank
    from vrtools.convert.collision import saturn_collision
    from vrtools.convert.lap import order_slices
    from vrtools.convert.road import road_tables
    from tests.test_convert_collision import _saturn_course

    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    col, cells = saturn_collision(sat, height=lambda x, z: 30.0, lap=lap, merge=True, cover=True)   # Phase 22j: the build's
    t = road_tables(lap, col.quads[:col.n_tarmac])                                                   # path (no sideways growth)
    out = install_bank(rs, 0, build_bank(rs, 0, t, [0] * 128 * 128, col.surface))
    out = patch_collision(out, 0, col, slot=2, force=True, cell_offsets=cells)
    build = _build(tmp_path, romset_zip, out)
    from vrtools.convert.lap import arc_of, centreline
    samples = _drive(tmp_path, "regen", build, seconds=90, extra_env={"VR_SNAPS_AFTER_START": "600,1500,2500"},
                     centreline=centreline(lap))
    d = drive_summary(samples)
    assert course_of(tmp_path / "regen" / "c.txt") == (0, 2)
    assert d["calls"] > 800 and d["noanswer"] == 0 and (d["offroad"] + d["nohit"]) / d["calls"] < 0.05, d
    pr = lap_progress(samples, lambda x, z: arc_of(lap, x, z), lap.length)
    assert pr["forward"] > 2000 and pr["backward"] < 0.1 * pr["forward"], pr        # the autopilot laps the converted road


def _alpine_set(rs, saturn_cue):
    """Alpine in Big Forest's slot: Saturn-derived road tables, collision (with heights and directions) and scenery."""
    from vrtools.arcade.bank import build_bank, install_bank
    from vrtools.arcade.patch import patch_course_tiles, patch_pit_entry
    from vrtools.convert.collision import saturn_collision
    from vrtools.convert.geometry import convert_tiles, placed
    from vrtools.convert.lap import order_slices
    from vrtools.convert.place import choose_placement, grid_pose
    from vrtools.convert.profile import profile_height, road_profile
    from vrtools.convert.road import road_tables
    from tests.test_convert_collision import _saturn_course

    sat = _saturn_course(saturn_cue, "ALPINE00/TRCKALPN")
    pl = choose_placement(sat, grid_pose(rs, 0))                 # the lap start sits at the arcade's grid
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction)
        heights = road_profile(sat, lap)
        col, cells = saturn_collision(sat, profile_height(lap, heights), lap=lap, merge=True)
        tables = road_tables(lap, col.quads[:col.n_tarmac])
        out = install_bank(rs, 0, build_bank(rs, 0, tables, [0] * 128 * 128, col.surface))
        out = patch_collision(out, 0, col, slot=2, force=True, cell_offsets=cells)
        objs, words, report = convert_tiles(sat, out, 0)
    out = patch_course_tiles(out, 0, objs, words)
    out = patch_pit_entry(out, 2, None)                           # no pit lane: quad 30 is plain tarmac on a converted course
    return out, lap, col, tables, report


def test_alpine_drives_in_the_big_forest_slot(tmp_path, romset_zip, saturn_cue):
    from vrtools.convert.lap import arc_of, centreline
    from vrtools.mame.runner import parse_rate

    rs = RomSet.from_zip(romset_zip)
    out, lap, col, tables, report = _alpine_set(rs, saturn_cue)
    build = _build(tmp_path, romset_zip, out)
    samples = _drive(tmp_path, "alpine", build, seconds=90, centreline=centreline(lap),
                     extra_env={"VR_RATE_LOG": str(tmp_path / "alpine" / "rate.txt"), "VR_SNAPS_AFTER_START": "600,1500,2500"})
    d = drive_summary(samples)
    assert course_of(tmp_path / "alpine" / "c.txt") == (0, 2)
    assert d["calls"] > 800 and d["noanswer"] == 0 and (d["offroad"] + d["nohit"]) / d["calls"] < 0.10, d
    pr = lap_progress(samples, lambda x, z: arc_of(lap, x, z), lap.length)
    assert pr["forward"] > 2000 and pr["backward"] < 0.1 * pr["forward"], pr        # progress along the Alpine lap
    rate = [n for f, n in parse_rate(tmp_path / "alpine" / "rate.txt") if f > 2000]
    assert rate and min(rate) >= 27, rate


@pytest.mark.parametrize("course", [0, 1])
def test_directory_build_drives_the_originals_identically(tmp_path, romset_zip, course):
    """The ten-entry directory with the three originals (repeated) loads exactly the data the original code did:
    the collision probe stream of a 45-second race is identical sample for sample."""
    from vrtools.arcade.directory import ORIGINALS, install_directory

    from vrtools.arcade.select import WHEEL_FOR_ENTRY

    rs = RomSet.from_zip(romset_zip)
    a = _drive(tmp_path, f"orig{course}", romset_zip.parent, seconds=45, extra_env={"VR_COURSE": str(course)})
    build = _build(tmp_path, romset_zip, install_directory(rs, (ORIGINALS * 4)[:10]))
    b = _drive(tmp_path, f"dir{course}", build, seconds=45,
               extra_env={"VR_COURSE": str(course), "VR_WHEEL": str(WHEEL_FOR_ENTRY[course])})   # the ten-band wheel
    assert course_of(tmp_path / f"dir{course}" / "c.txt") == course_of(tmp_path / f"orig{course}" / "c.txt")
    assert len(b) > 300 and [(s.x, s.z, s.quad) for s in b] == [(s.x, s.z, s.quad) for s in a]


@pytest.mark.parametrize("entry", range(10))
def test_wheel_selects_each_of_ten_entries(tmp_path, romset_zip, entry):
    """Holding the wheel at a band's centre selects that entry of the ten-course directory and loads its data
    (course_of reads the menu index and the data index the loader set, i.e. the entry's template)."""
    from dataclasses import replace
    from vrtools.arcade.directory import ORIGINALS, install_directory
    from vrtools.arcade.select import WHEEL_FOR_ENTRY

    rs = RomSet.from_zip(romset_zip)
    d = ORIGINALS + [replace(ORIGINALS[2], name=f"TEST {k}") for k in range(7)]      # seven copies of Acropolis under test names
    build = _build(tmp_path, romset_zip, install_directory(rs, d))
    _drive(tmp_path, f"sel{entry}", build, seconds=30, extra_env={"VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_SNAPS": "1200"})
    assert course_of(tmp_path / f"sel{entry}" / "c.txt") == (entry, d[entry].template)      # (menu index, data index = template)


def test_alpine_as_entry_three_drives(tmp_path, romset_zip, saturn_cue):
    """Alpine as a relocatable blob in Big Forest's bank, TGP slot 3, its own tile table, entry 3 of the ten-course
    directory: selected through the wheel it drives like the Phase 6 build; entry 0 still drives Big Forest."""
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.arcade.tencourse import convert_course, ten_course_set, tile_table_address
    from vrtools.convert.lap import arc_of
    from vrtools.mame.runner import parse_rate
    from tests.test_convert_collision import _saturn_course

    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "ALPINE00/TRCKALPN")
    out, alpine = convert_course(rs, sat, "ALPINE", bank=3, tgp_slot=3, template=2, tile_table=tile_table_address(0))
    out = ten_course_set(out, [alpine])
    build = _build(tmp_path, romset_zip, out)
    samples = _drive(tmp_path, "alpine3", build, seconds=90, centreline=alpine.centreline,
                     extra_env={"VR_WHEEL": str(WHEEL_FOR_ENTRY[3]), "VR_RATE_LOG": str(tmp_path / "alpine3" / "rate.txt"),
                                "VR_SNAPS_AFTER_START": "600,2500"})
    d = drive_summary(samples)
    assert course_of(tmp_path / "alpine3" / "c.txt") == (3, 2)                   # menu 3, Big Forest's template as the data index
    assert d["calls"] > 800 and d["noanswer"] == 0 and (d["offroad"] + d["nohit"]) / d["calls"] < 0.10, d
    pr = lap_progress(samples, lambda x, z: arc_of(alpine.lap, x, z), alpine.lap.length)
    assert pr["forward"] > 2000 and pr["backward"] < 0.1 * pr["forward"], pr
    rate = [n for f, n in parse_rate(tmp_path / "alpine3" / "rate.txt") if f > 2000]
    assert rate and min(rate) >= 27, rate
    bf = _drive(tmp_path, "bf0", build, seconds=45, extra_env={"VR_WHEEL": str(WHEEL_FOR_ENTRY[0])})
    orig = _drive(tmp_path, "orig0", romset_zip.parent, seconds=45, extra_env={"VR_COURSE": "0"})
    assert course_of(tmp_path / "bf0" / "c.txt") == (0, 2) and [(s.x, s.z, s.quad) for s in bf] == [(s.x, s.z, s.quad) for s in orig]


def test_operator_fixed_course_still_loads_the_original(tmp_path, romset_zip):
    """With the operator's COURSE SELECT set to MIDDLE (0x40dca1 = 2) the game skips the select screen and picks
    the course through [0x501934]; the directory build must load Bay Bridge like the original."""
    from vrtools.arcade.directory import ORIGINALS, install_directory

    rs = RomSet.from_zip(romset_zip)
    poke = {"VR_POKE": "40dca1=2"}
    a = _drive(tmp_path, "origfix", romset_zip.parent, seconds=40, extra_env=poke)
    build = _build(tmp_path, romset_zip, install_directory(rs, (ORIGINALS * 4)[:10]))
    b = _drive(tmp_path, "dirfix", build, seconds=40, extra_env=poke)
    assert course_of(tmp_path / "origfix" / "c.txt")[1] == 0 and course_of(tmp_path / "dirfix" / "c.txt")[1] == 0
    assert len(b) > 200 and [(s.x, s.z, s.quad) for s in b] == [(s.x, s.z, s.quad) for s in a]


_SEVEN: dict = {}


def _seven(romset_zip, saturn_cue):
    """build_all + ten_course_set once per session (the six drives share it)."""
    from vrtools.arcade.tencourse import build_all, ten_course_set
    key = str(romset_zip)
    if key not in _SEVEN:
        rs = RomSet.from_zip(romset_zip)
        out, conv = build_all(rs, saturn_cue)
        _SEVEN[key] = (ten_course_set(out, conv), conv)
    return _SEVEN[key]


@pytest.mark.parametrize("k", range(1, 7))                                   # the six new courses (Alpine is Phase 7's gate)
def test_each_new_course_drives_at_the_arcade_rate(tmp_path, romset_zip, saturn_cue, k):
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.convert.lap import arc_of
    from vrtools.mame.runner import parse_rate
    out, conv = _seven(romset_zip, saturn_cue)
    build = _build(tmp_path, romset_zip, out)
    c = conv[k]
    entry = 3 + k
    label = f"course{entry}"
    samples = _drive(tmp_path, label, build, seconds=90, centreline=c.centreline,          # the race starts as late as frame 1603 and the countdown takes ~290 more
                     extra_env={"VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_RATE_LOG": str(tmp_path / label / "rate.txt"),
                                "VR_SNAPS_AFTER_START": "600,2000"})
    d = drive_summary(samples)
    assert course_of(tmp_path / label / "c.txt") == (entry, c.entry.template), c.entry.name
    assert d["calls"] > MIN_CALLS.get(c.entry.name, 500) and d["noanswer"] == 0 and (d["offroad"] + d["nohit"]) / d["calls"] < 0.10, (c.entry.name, d)
    pr = lap_progress(samples, lambda x, z: arc_of(c.lap, x, z), c.lap.length)
    floor = MIN_FORWARD.get(c.entry.name, 2000)                  # Phase 11: 2837–3533 measured on every course (1200 before)
    assert pr["forward"] > floor and pr["backward"] < MAX_BACKWARD.get(c.entry.name, 0.15) * pr["forward"], (c.entry.name, pr)
    rate = [n for f, n in parse_rate(tmp_path / label / "rate.txt") if f > 2000]
    assert rate and min(rate) >= 27, (c.entry.name, min(rate), rate[:20])


# Forward progress floors (units in a 90 s run) where a course is known to fall short of the 1200 default:
# the Surfers Oval's flat (unbanked) turns put the car on the inner verge at speed, where it crawls on grass
# (1044 measured; 1732 while the infield was still tarmac it could run on). Banking or a slower field is M6.
# Phase 10: the field drives now; on the Bay Bridge-template courses it starts single file right in front of the
# player and the autopilot, which cannot overtake, rams the queue (Surfers Oval 955 units and a crash-heavy probe,
# Surfers Road 587 in 90 s). The render-rate check is the hard part of this gate.
# Phase 11: with no opponent parked the 90 s autopilot drives 2837–3533 units forward on every converted course (the Oval
# 3278, Surfers Road 2919 against 977 and 587 behind the Phase 10 queues), backward at most 288 (Metropolis): the
# per-course allowances of Phase 10 are gone.
MIN_FORWARD: dict[str, float] = {}
MIN_CALLS: dict[str, int] = {}
MAX_BACKWARD: dict[str, float] = {}

