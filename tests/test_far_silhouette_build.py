"""Phase 31 (a prototype, kept on Pascal's word of 15 Nov, "yes it s good keep it"): the far silhouette on Metropolis in the built
ten-course set.

The set with the copies against the set without them, made from the same conversions (`ten_course_set` on build_all's result
with every `Converted.far_cells` taken away: main's set): what differs, byte by byte; and the race, fed the same recorded
inputs on both, pass for pass, in both directions. The arcade's rate on the set is tests/test_frame_rate.py's standing test
(entries 6 and 6 reverse)."""

import shutil
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from vrtools.arcade.budget import FRAME_BUDGET
from vrtools.arcade.course import tile_table_at
from vrtools.arcade.directory import decode_directory
from vrtools.arcade.polyrom import decode_object, quads as poly_quads
from vrtools.arcade.romset import V60_PROGRAM
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.arcade.tencourse import (METROPOLIS_BLOCK, METROPOLIS_FRONT, annex_regions, far_colour_block, max_colour_entry,
                                      ten_course_set)
from vrtools.arcade.tencourse import COURSES as PLANS
from vrtools.convert.reverse import reverse_points
from vrtools.mame.framerate import parse_frame_log, parse_pass_log
from vrtools.mame.runner import LUA_DIR, run_mame, write_centreline

METROPOLIS = 6                       # menu entry
K = METROPOLIS - 3                   # its place among the converted courses
SOURCES, INTO = (215, 216), (183, 184)
BLOCK_FACES = 15                     # the tall block's three walls and twelve window bands (cells 215 and 216)
FRONT_FACES = 30                     # the low building's six walls and twenty-four bands (cell 215)
COPIED = {183: FRONT_FACES + BLOCK_FACES, 184: BLOCK_FACES}
FACES = sum(COPIED.values())
SAME_SECONDS = 150                   # the start and the first lap, then the straight (normal) and the parallel street (reverse) again
JOBS = 2

_SETS: dict = {}


def _sets(romset_zip, saturn_cue):
    """(the session's set, the same set without the far copies, the conversions)."""
    from tests.test_tgp_build import _built, _seven
    key = str(romset_zip)
    if key not in _SETS:
        new, conv = _seven(romset_zip, saturn_cue)
        built, _ = _built(romset_zip, saturn_cue)
        plain = ten_course_set(built, [replace(c, far_cells=None, report=dict(c.report)) for c in conv])
        _SETS[key] = (new, plain, conv)
    return _SETS[key]


_PAIRS: dict = {}


def _pair(romset_zip, saturn_cue):
    """(the set without Phase 33's originals' reverse variants, the same without the far copies too, the first's Metropolis
    report): two sets that differ by the far copies alone. In the session's set the checkpoint lettering (Phase 33 stage 2,
    `install_checkpoint_lists`) is installed after the copies, first fit on what they leave, so in a set built without the
    copies it lands on their bytes; with `originals_reverse` False neither set has it."""
    from tests.test_tgp_build import _built
    key = str(romset_zip)
    if key not in _PAIRS:
        built, conv = _built(romset_zip, saturn_cue)
        mine = [replace(c, report=dict(c.report)) for c in conv]
        new = ten_course_set(built, mine, originals_reverse=False)
        plain = ten_course_set(built, [replace(c, far_cells=None, report=dict(c.report)) for c in conv], originals_reverse=False)
        _PAIRS[key] = (new, plain, mine[K].report["far_installed"])
    return _PAIRS[key]


def _faces(rs, table, cell):
    t = tile_table_at(rs, table)[cell]
    if not t.size:
        return []
    return [tuple(sorted(q.p)) for q in poly_quads(decode_object(rs.polygons, t.poly_adr, t.size), t.tex_adr)]


def _in(box, face, min_top):
    x0, z0, x1, z1 = box
    return all(x0 <= p[0] <= x1 and z0 <= p[2] <= z1 for p in face) and max(p[1] for p in face) >= min_top


def test_only_metropolis_carries_far_copies():
    assert [p.name for p in PLANS if p.far_copies] == ["METROPOLIS"]
    assert sorted({c.source for c in PLANS[K].far_copies}) == list(SOURCES)
    assert sorted({cell for c in PLANS[K].far_copies for cell in c.into}) == list(INTO)


def test_the_set_differs_from_the_set_without_the_copies_only_where_the_copies_are_written(romset_zip, saturn_cue):
    """The hard gates on the bytes. Against the set without the copies: the boot ROM, the data ROM (every course's blob), the
    TGP data ROM (the collision) and the TGP program are identical; the polygon ROM differs only in bytes that were erased (the
    two new objects); the program ROM differs only in Metropolis's two tile records (cells 183 and 184) and in bytes that were
    erased inside the block reserved for them (`far_colour_block`: the new objects' colour entries). So every directory entry, every other tile
    record of all ten courses and every object they name are the same bytes.
    Since Phase 33 the set built without the copies is not that set: its checkpoint lettering, installed after the copies first
    fit, lands on their bytes. So the comparison is made on the two sets without the originals' reverse variants (`_pair`: they
    differ by the copies alone), and the session's set is then checked by address: its far-copy words, records and colour
    entries are those bytes, and everything it adds to that set (the lettering) went on bytes erased there."""
    new, plain, rep = _pair(romset_zip, saturn_cue)
    shipped, full_plain, conv = _sets(romset_zip, saturn_cue)
    assert rep == conv[K].report["far_installed"]                      # the copies installed the same in the session's set
    assert ((shipped.boot, shipped.data, shipped.copro_data, shipped.tgp_program)
            == (full_plain.boot, full_plain.data, full_plain.copro_data, full_plain.tgp_program))
    assert (new.boot, new.data, new.copro_data, new.tgp_program) == (plain.boot, plain.data, plain.copro_data, plain.tgp_program)
    poly = [i for i in range(0, len(new.polygons), 4) if new.polygons[i:i + 4] != plain.polygons[i:i + 4]]
    assert poly and all(plain.polygons[i:i + 4] == b"\xff\xff\xff\xff" for i in poly)
    assert 4 * len(poly) == rep["polygon_bytes"] == sum(c["bytes"] for c in rep["cells"].values())     # every word of the two objects
    table = decode_directory(new)[METROPOLIS].tile_table
    records = {}
    for cell in INTO:
        at = struct.unpack_from("<I", new.program, table - V60_PROGRAM + 4 * cell)[0] - V60_PROGRAM
        records.update({at + k: cell for k in range(16)})
    prog = [i for i in range(len(new.program)) if new.program[i] != plain.program[i]]
    colours = [i for i in prog if i not in records]
    assert {records[i] for i in prog if i in records} == set(INTO)
    lo, hi = (a - V60_PROGRAM for a in far_colour_block())            # the block reserved for them (review I1)
    first = 2 * (rep["colour_first"] - 0x40000)
    assert colours and all(plain.program[i] == 0xFF and lo <= i < hi for i in colours)
    assert set(plain.program[lo:hi]) == {0xFF} and first == lo           # the block was untouched, the entries start it
    assert all(first <= i < first + 2 * rep["colour_entries"] for i in colours)
    assert decode_directory(new) == decode_directory(plain)
    for e in range(10):                                           # belt and braces: each entry's cells, record by record
        tn, tp = tile_table_at(new, decode_directory(new)[e].tile_table), tile_table_at(plain, decode_directory(plain)[e].tile_table)
        assert [c for c in range(256) if tn[c] != tp[c]] == (list(INTO) if e == METROPOLIS else []), e
    assert max_colour_entry(new) == max_colour_entry(plain)       # the new entries lie below the conversions' (the colour run's head)
    assert rep["colour_first"] + rep["colour_entries"] <= 0x40000 + (annex_regions()[1][0] - V60_PROGRAM) // 2
    # the session's set, by address: the copies' every word, the two records and the colour block are the bytes above; the two
    # objects the records name are exactly those words; and what the set adds to `new` in the polygon ROM went on erased bytes
    assert all(shipped.polygons[i:i + 4] == new.polygons[i:i + 4] for i in poly)
    sn = tile_table_at(shipped, decode_directory(shipped)[METROPOLIS].tile_table)
    tn = tile_table_at(new, table)
    assert [sn[c] for c in INTO] == [tn[c] for c in INTO]
    assert set(poly) == {4 * sn[c].poly_adr + 4 * w for c in INTO for w in range(rep["cells"][c]["bytes"] // 4)}
    assert shipped.program[lo:hi] == new.program[lo:hi]
    added = [i for i in range(0, len(shipped.polygons), 4) if shipped.polygons[i:i + 4] != new.polygons[i:i + 4]]
    assert added and all(new.polygons[i:i + 4] == b"\xff\xff\xff\xff" for i in added) and not set(added) & set(poly)


def test_the_nearer_cells_draw_their_own_faces_and_the_far_buildings(romset_zip, saturn_cue):
    """Cell 183 of the set draws what it drew plus the low building's 30 faces (cell 215's faces inside METROPOLIS_FRONT
    reaching 15 units: six walls, twenty-four bands) and the tall block's 15 (the faces of cells 215 and 216 inside
    METROPOLIS_BLOCK reaching 20: three walls, twelve bands); cell 184 what it drew plus the block's 15; point for point. Cells
    215 and 216 are untouched; the records added and the report agree."""
    new, plain, conv = _sets(romset_zip, saturn_cue)
    table = decode_directory(new)[METROPOLIS].tile_table
    block = sorted(f for s in SOURCES for f in _faces(plain, table, s) if _in(METROPOLIS_BLOCK, f, 20.0))
    front = sorted(f for f in _faces(plain, table, 215) if _in(METROPOLIS_FRONT, f, 15.0))
    assert (len(block), len(front)) == (BLOCK_FACES, FRONT_FACES)
    assert max(p[1] for f in block for p in f) == pytest.approx(92.4, abs=0.1)
    assert max(p[1] for f in front for p in f) == pytest.approx(59.6, abs=0.1)
    for cell, far in ((183, front + block), (184, block)):
        own = _faces(plain, table, cell)
        assert sorted(_faces(new, table, cell)) == sorted(own + far), cell
        assert not any(_in(METROPOLIS_BLOCK, f, 0.0) or _in(METROPOLIS_FRONT, f, 0.0) for f in own)
    for cell in SOURCES:
        assert _faces(new, table, cell) == _faces(plain, table, cell)
    rep, counts = conv[K].report["far_installed"], conv[K].report["far_copies"]
    assert counts == {183: {"own": len(_faces(plain, table, 183)), "copied": COPIED[183], "from": [215, 215, 216]},
                      184: {"own": len(_faces(plain, table, 184)), "copied": COPIED[184], "from": [215, 216]}}
    tn, tp = tile_table_at(new, table), tile_table_at(plain, table)
    assert {c: (v["records"], v["records_before"]) for c, v in rep["cells"].items()} == {c: (tn[c].size, tp[c].size) for c in INTO}
    assert rep["added_records"] == sum(tn[c].size - tp[c].size for c in INTO)
    assert all(0 < tn[c].size - tp[c].size <= 2 * COPIED[c] for c in INTO)       # at most two records a face


# ---- the race, on the same inputs ----

class _Runs:
    def __init__(self, romset_zip, saturn_cue, base):
        from tests.test_race_build import _drive_line
        from tests.test_tgp_build import _build
        new, plain, conv = _sets(romset_zip, saturn_cue)
        self.base = base
        for d in ("new", "main"):
            (base / d).mkdir(parents=True, exist_ok=True)
        self.sets = {"new": _build(base / "new", romset_zip, new), "main": _build(base / "main", romset_zip, plain)}
        self.line = _drive_line(conv[K])
        nv = base / "nvram_boot"
        run_mame(LUA_DIR / "attract_snaps.lua", 30, nv, self.sets["main"], env={"VR_SNAP_FROM": "999999"}, timeout=900)
        self.nvram = nv / "nvram"
        with ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(lambda r: self._make("main", r), (False, True)))
        with ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(lambda r: self._make("new", r), (False, True)))

    def wd(self, which, reverse):
        return self.base / f"same_{which}{'_r' if reverse else ''}"

    def _make(self, which, reverse):
        wd = self.wd(which, reverse)
        wd.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.nvram, wd / "nvram")
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[METROPOLIS]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
               "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", reverse_points(self.line) if reverse else self.line)),
               "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0", "VR_PASS_LOG": str(wd / "pass.txt"),
               "VR_FRAME_LOG": str(wd / "frames.txt"), "VR_INPUT_LOG": str(wd / "tape.txt")}
        if reverse:
            env["VR_DIRECTION"] = "1"
        if which == "new":
            env["VR_INPUT_REPLAY"] = str(self.wd("main", reverse) / "tape.txt")
        run_mame(LUA_DIR / "autoplay.lua", SAME_SECONDS, wd, self.sets[which], env=env, timeout=3600)


_RUNS: dict = {}


@pytest.fixture
def same_runs(romset_zip, saturn_cue, tmp_path_factory) -> _Runs:
    key = str(romset_zip)
    if key not in _RUNS:
        _RUNS[key] = _Runs(romset_zip, saturn_cue, tmp_path_factory.mktemp("far"))
    return _RUNS[key]


@pytest.mark.parametrize("reverse", [False, True], ids=["normal", "reverse"])
def test_the_race_is_the_same_pass_for_pass_and_the_frame_stays_in_the_budget(same_runs, record_property, reverse):
    """Metropolis for SAME_SECONDS on the same battery RAM, on the set without the copies with the autopilot, then on the set fed
    exactly the wheel and pedal the autopilot gave, frame for frame (input_tape.lua): the game's state at the end of every logic
    pass (pass_state.lua: the clock and all 16 cars' x, z, road point, speed and lap, and the frame each pass ends in) is
    identical over the whole run. The frame's records, pass by pass: never fewer than without the copies, never more than the
    two cells' added records above it, the copies drawn in the run (some pass has more), no list skipped, the overrun counter
    still, and every pass far inside the budget. The added records' median and maximum over the passes that draw a copy go to
    far_summary.txt."""
    old, new = same_runs.wd("main", reverse), same_runs.wd("new", reverse)
    ta, tb = (new / "tape.txt").read_text().splitlines(), (old / "tape.txt").read_text().splitlines()
    assert len(ta) > 3000 and ta == tb, ("the replay did not feed the recorded inputs", len(ta), len(tb))
    a, b = parse_pass_log(new / "pass.txt"), parse_pass_log(old / "pass.txt")
    assert len(a) > 3500 and len(a) == len(b), (len(a), len(b))
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    assert first is None, (first, a[first][:120], b[first][:120])
    fa, fb = parse_frame_log(new / "frames.txt"), parse_frame_log(old / "frames.txt")
    assert len(fa) == len(fb) and [f.frame for f in fa] == [f.frame for f in fb]
    added = [x.records - y.records for x, y in zip(fa, fb)]
    assert min(added) == 0 and 0 < max(added) <= 2 * FACES, (min(added), max(added))     # at most two records a copied face
    drawn = sorted(d for d in added if d)
    assert not any(f.skipped for f in fa) and {f.overrun for f in fa} == {fa[0].overrun}
    assert max(f.records for f in fa) < FRAME_BUDGET and max(f.need for f in fa) < FRAME_BUDGET
    line = (f"{'reverse' if reverse else 'normal'}: passes {len(a)} identical; passes drawing a copy {len(drawn)} of {len(added)}, added "
            f"records median {drawn[len(drawn) // 2]} max {drawn[-1]}; records peak {max(f.records for f in fa)} "
            f"(without {max(f.records for f in fb)}), need max {max(f.need for f in fa)}, budget {FRAME_BUDGET}; "
            f"worst busy from frame 2000 {max(f.busy_us for f in fa if f.frame >= 2000)} us "
            f"(without {max(f.busy_us for f in fb if f.frame >= 2000)})")
    record_property("far_summary", line)
    with open(same_runs.base / "far_summary.txt", "a") as out:
        out.write(line + "\n")
