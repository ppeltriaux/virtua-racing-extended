"""Phase 26: the reverse variants in the seven-course set (design §6.3; stage 2, design §6.7: all seven converted courses): each
entry's variant is its own header, segment array, pointer block and lines in the entry's data bank beside the normal blob, sharing
its collision map, surface table and backdrop (the four bank-1 courses store three lines, plan D2); the variants' load records,
maps records and race blobs in one annex (`tencourse.annex_regions()`, plan D1; one conversion per session).
Stage 1 Task 8: the reverse race in MAME against a normal-direction control run of the same session."""
import math
import struct

import pytest

from vrtools.arcade import blob
from vrtools.arcade.bank import POINT_BYTES, WRAP_POINTS, line_turn
from vrtools.arcade.course import BANK_SIZE, WINDOW, course_entry_at, decode_pointer_block, road_lines, segments
from vrtools.arcade.direction import FIGURE_RECORDS
from vrtools.arcade.directory import decode_directory, directory_layout
from vrtools.arcade.race import RACE_BLOB_BYTES, decode_race_blob, encode_race_blob
from vrtools.arcade.romset import V60_PROGRAM, RomSet
from vrtools.arcade.tencourse import OFF_COURSE_LIMIT, annex_regions, max_colour_entry, race_blob_for, ten_course_set
from vrtools.arcade.tencourse import COURSES as PLANS
from vrtools.convert.race import GATE_START_GAP, check_laps, lap_total
from vrtools.convert.reverse import _holds, reverse_points
from vrtools.mame.runner import LUA_DIR, parse_edges, parse_field, parse_race_log, race_report
from tests.test_race_build import (BACKSTEP_MAX, CURSOR_LEAD_MAX, CURSOR_LEAD_MAXES, LEADER_FLOOR, MOVED_FLOOR, PARKED_DEFAULT,
                                   RATE_FLOOR, _drive_entry, _drive_line, _race)
from tests.test_tencourse import BANK_ONE_FLOOR
from tests.test_tgp_build import _built, _seven

COURSES = {3: 452, 4: 330, 5: 457, 6: 365, 7: 410, 8: 387, 9: 441}   # Phase 26 stage 2: entry -> road points (recon §2)
METROPOLIS = 6              # the put-back and the warning's positive control stay on Metropolis (stage 2 Task 6: the races run on COURSES)
N = COURSES[METROPOLIS]     # Metropolis's road points (recon §3.1)
BAY_BRIDGE = 1              # an original course: no variant (the flag-without-variant test)


def _plan(entry):
    """The CoursePlan of directory entry `entry` (the plans fill entries 3-9 in order)."""
    return PLANS[entry - 3]


def _both(out, entry=METROPOLIS):
    d = decode_directory(out)
    n, rv = d[entry], d[entry].reverse.entry
    return d, n, rv, course_entry_at(out, n.bank, n.header_base), course_entry_at(out, rv.bank, rv.header_base)


def line_pointers(rs, entry):
    """The eight (pointer, count) pairs of the pointer block of directory record `entry` (a CourseEntry10)."""
    return decode_pointer_block(rs, course_entry_at(rs, entry.bank, entry.header_base)).lines


def _annex(d):
    """[lo, hi): from the first variant's load record to the end of the last variant's race blob."""
    rec = [e.reverse for e in d[3:10]]
    return min(r.at for r in rec), max(r.entry.race for r in rec) + RACE_BLOB_BYTES


def _variant_span(rs, rv):
    """[start, end) in the data ROM of a variant's blob: from its header to the end of its last stored line (the blob ends
    there, 16-aligned: `blob._road_part` with a collision named)."""
    lines = line_pointers(rs, rv)
    end = max(p for p, _ in lines) + POINT_BYTES * (lines[0][1] + WRAP_POINTS)
    start = rv.bank * BANK_SIZE + rv.header_base - WINDOW
    return start, rv.bank * BANK_SIZE + (end + 15) // 16 * 16 - WINDOW


REVERSE_PIT_QUADS = {"ALPINE": 250, "AMAZON FALLS": 32, "DIABLO CANYON": 58, "METROPOLIS": 86, "PACIFIC COAST": 241,
                     "SURFERS OVAL": 15, "SURFERS ROAD": 13}       # stage 4 Task 2's picks (tests/test_convert_reverse.py, PINNED)
METROPOLIS_REVERSE_BOX_Z = 269.74   # the one box moved up the lane (decision L3): in the tunnel, 40 units deeper than the normal box


def _f32(box):
    """A box as its maps record stores it: x, y, z as 32-bit floats, the heading."""
    return (*struct.unpack("<3f", struct.pack("<3f", *box[:3])), box[3])


def test_every_converted_course_has_a_reverse_record(romset_zip, saturn_cue):
    """Each of the seven converted entries has its variant record, sharing the entry's bank, slot, template, tables, music,
    laps, off-course limit and HUD map object, with its own HUD map shift; stage 4 (Task 3): with its own pit quad and box,
    the conversion's `reverse.reverse_pit` (the report's "reverse_pit_quad" and "reverse_pit_box"), pinned to Task 2's picks:
    not the normal pair's quad, the normal box turned half a turn (on Metropolis moved up the lane to z 269.74)."""
    out, conv = _seven(romset_zip, saturn_cue)
    d = decode_directory(out)
    assert [e.reverse is not None for e in d[:10]] == [False] * 3 + [True] * 7
    assert [e.name for e in d[3:10]] == [p.name for p in PLANS]
    for entry in COURSES:
        _, n, rv, _, _ = _both(out, entry)
        for f in ("bank", "tgp_slot", "template", "tile_table", "spawn_table", "music", "laps", "off_course", "map_obj"):
            assert getattr(rv, f) == getattr(n, f), (n.name, f)
        c = conv[entry - 3]
        assert c.entry.name == n.name
        assert (c.reverse.pit_quad, c.reverse.pit_box) == (c.report["reverse_pit_quad"], c.report["reverse_pit_box"]), n.name
        assert rv.pit_quad == c.report["reverse_pit_quad"] == REVERSE_PIT_QUADS[n.name], (n.name, rv.pit_quad)
        assert rv.pit_box == _f32(c.report["reverse_pit_box"]), (n.name, rv.pit_box, c.report["reverse_pit_box"])
        assert n.pit_quad is not None and rv.pit_quad != n.pit_quad, (n.name, n.pit_quad)
        assert rv.pit_box[3] == (n.pit_box[3] + 0x8000) & 0xFFFF, (n.name, rv.pit_box, n.pit_box)
        if n.name == "METROPOLIS":
            assert rv.pit_box[:3] != n.pit_box[:3] and abs(rv.pit_box[2] - METROPOLIS_REVERSE_BOX_Z) <= 0.05, (rv.pit_box, n.pit_box)
        else:
            assert rv.pit_box[:3] == n.pit_box[:3], (n.name, rv.pit_box, n.pit_box)
        shifted = (237.0, 22)                                    # the HUD map shifts right on an anticlockwise lap: each simple
        assert ((n.map_tx, n.map_cross) == shifted) != ((rv.map_tx, rv.map_cross) == shifted), n.name   # loop turns the other way in reverse
    _, n, rv, _, _ = _both(out)
    assert (n.map_tx, n.map_cross) == (149.0, 0)                 # Metropolis: clockwise forward ...
    assert (rv.map_tx, rv.map_cross) == (237.0, 22)              # ... anticlockwise in reverse: the HUD map shifts right


def _spans(a: bytes, b: bytes, base: int = 0) -> list[tuple[int, int]]:
    """[start, end) runs of the bytes that differ between a and b (same length), at `base` + offset."""
    out = []
    for i in (i for i in range(len(a)) if a[i] != b[i]):
        if out and out[-1][1] == base + i:
            out[-1] = (out[-1][0], base + i + 1)
        else:
            out.append((base + i, base + i + 1))
    return out


def test_the_reverse_pit_changes_only_the_variant_records(romset_zip, saturn_cue):
    """Stage 4 (Task 3): the seven-course set made from the session's conversion with each variant's pit (`Reversed.pit_quad`,
    `pit_box`) against the same set made with both None: the program ROM differs only inside the seven variants' load records
    (+0x10..+0x11, the pit quad over PIT_NONE) and maps records (+16..+31, the box over zeros); the normal entries' records and
    every other ROM are identical."""
    from dataclasses import replace
    from vrtools.arcade.directory import LOAD_SIZE, maps_offset
    out, conv = _seven(romset_zip, saturn_cue)
    built = _built(romset_zip, saturn_cue)[0]
    bare = ten_course_set(built, [replace(c, reverse=replace(c.reverse, pit_quad=None, pit_box=None)) for c in conv])
    for f in ("boot", "data", "polygons", "copro_data", "tgp_program"):
        assert getattr(out, f) == getattr(bare, f), f
    d, d0 = decode_directory(out), decode_directory(bare)
    assert [e.reverse.at for e in d[3:10]] == [e.reverse.at for e in d0[3:10]]
    allowed = []
    for e in d[3:10]:
        at = e.reverse.at
        allowed += [(at + 0x10, at + 0x12), (at + maps_offset() + 16, at + maps_offset() + 32)]
    spans = _spans(out.program, bare.program, V60_PROGRAM)
    assert spans and all(any(a <= s and t <= b for a, b in allowed) for s, t in spans), [(hex(s), t - s) for s, t in spans]
    for e in d[3:10]:                                            # what the allowed bytes hold in each set
        load, maps = e.reverse.at - V60_PROGRAM + 0x10, e.reverse.at - V60_PROGRAM + maps_offset() + 16
        v = e.reverse.entry
        assert (out.program[load:load + 2], bare.program[load:load + 2]) == (struct.pack("<H", v.pit_quad), b"\xfe\xff"), e.name
        assert (out.program[maps:maps + 16], bare.program[maps:maps + 16]) == (struct.pack("<3fHH", *v.pit_box, 1), bytes(16)), e.name
    lay = directory_layout()
    for i in range(10):                                          # the normal entries' load and maps records byte for byte
        for base in (lay["load"], lay["maps"]):
            lo = base - V60_PROGRAM + LOAD_SIZE * i
            assert out.program[lo:lo + LOAD_SIZE] == bare.program[lo:lo + LOAD_SIZE], (i, hex(base))
    for e, e0 in zip(d[3:10], d0[3:10]):
        assert e.reverse.entry == replace(e0.reverse.entry, pit_quad=e.reverse.entry.pit_quad, pit_box=e.reverse.entry.pit_box), e.name
        assert e0.reverse.entry.pit_quad is None and e0.reverse.entry.pit_box is None, e.name
    print("differing program ROM spans:", [(hex(s), t - s) for s, t in spans])


def test_the_annex_lies_in_a_vetted_region_past_every_colour(romset_zip, saturn_cue):
    out, conv = _seven(romset_zip, saturn_cue)
    plain = ten_course_set(*_built(romset_zip, saturn_cue), reverse=False)
    d = decode_directory(out)
    lo, hi = _annex(d)
    assert any(a <= lo and hi <= b for a, b in annex_regions())
    assert set(plain.program[lo - V60_PROGRAM:hi - V60_PROGRAM]) == {0xFF}          # erased before the annex is written
    assert max_colour_entry(out) < 0x40000 + (lo - V60_PROGRAM) // 2               # no record's colours reach it


def test_the_direction_screens_block_lies_past_every_colour_and_the_annex(romset_zip, saturn_cue):
    """Stage 3 (plan D11, Task 5): the built set holds dirgfx's block at `dirscreen_block()` (written by build_all before any
    first-fit writer, on ROM erased in the original), past the colour entries any converted course's record names
    (`max_colour_entry`) and clear of the annex and of the start-gantry block."""
    from vrtools.arcade.dirgfx import block_image
    from vrtools.arcade.gantry import BLOCK_BYTES
    from vrtools.arcade.tencourse import dirscreen_block, start_gantry_address
    out, _ = _seven(romset_zip, saturn_cue)
    lo, hi = dirscreen_block()
    assert set(RomSet.from_zip(romset_zip).program[lo - V60_PROGRAM:hi - V60_PROGRAM]) == {0xFF}
    assert out.program[lo - V60_PROGRAM:hi - V60_PROGRAM] == block_image(lo)[0]
    assert max_colour_entry(out) < 0x40000 + (lo - V60_PROGRAM) // 2
    alo, ahi = _annex(decode_directory(out))
    assert ahi <= lo and (start_gantry_address() + BLOCK_BYTES <= lo)


def test_the_ten_course_set_writes_a_missing_direction_block(romset_zip, saturn_cue):
    """Stage 3 (Task 6, carry-over from Task 5's review): `dirdraw` runs its draw list from the block, and `ten_course_set` makes
    sure it is there: on build_all's result with the block's span erased, the set it makes is the session's set byte for byte
    (the block written); with a foreign byte in the span it refuses, naming the span."""
    from vrtools.arcade.dirgfx import block_image
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.tencourse import dirscreen_block
    out, conv = _built(romset_zip, saturn_cue)
    lo, hi = dirscreen_block()
    assert out.program[lo - V60_PROGRAM:hi - V60_PROGRAM] == block_image(lo)[0]          # build_all wrote it
    prog = bytearray(out.program)
    prog[lo - V60_PROGRAM:hi - V60_PROGRAM] = b"\xff" * (hi - lo)
    bare = RomSet(bytes(prog), out.boot, out.data, out.polygons, out.copro_data, out.tgp_program)
    made = ten_course_set(bare, conv)
    assert made.program[lo - V60_PROGRAM:hi - V60_PROGRAM] == block_image(lo)[0]
    assert made.program == _seven(romset_zip, saturn_cue)[0].program
    prog[lo - V60_PROGRAM + 1] = 0x00
    with pytest.raises(PatchError, match=f"{lo:#x}"):
        ten_course_set(RomSet(bytes(prog), out.boot, out.data, out.polygons, out.copro_data, out.tgp_program), conv)


def test_the_lap_sense_is_the_centrelines_on_every_entry(romset_zip, saturn_cue):
    """Stage 3 (Task 6, carry-over from Task 5's review): the lap sense the direction screen's `dirdraw` reads (dirscreen.SENSE_FIELD,
    the load record's map_cross) is, on each of the seven converted entries, non-zero exactly when the converted centreline's
    interior is on the left (anticlockwise), and the reverse variant's record holds the opposite."""
    from vrtools.arcade.tencourse import interior_on_the_left
    out, conv = _seven(romset_zip, saturn_cue)
    d = decode_directory(out)
    for entry in COURSES:
        left = interior_on_the_left(conv[entry - 3].centreline)
        assert (d[entry].map_cross != 0) == left, d[entry].name
        assert (d[entry].reverse.entry.map_cross != 0) == (not left), d[entry].name


STORED_LINES = {3: 8, 4: 3, 5: 8, 6: 6, 7: 3, 8: 3, 9: 3}   # entry -> distinct lines the variant stores (plan D2; Metropolis 6 since
                                                            # the owner's drive: METROPOLIS_PAIRS)


def test_bank_one_keeps_three_lines_a_course(romset_zip, saturn_cue):
    out, _ = _seven(romset_zip, saturn_cue)
    for k, e in enumerate(decode_directory(out)[3:10], 3):
        ptrs = {p for p, _ in line_pointers(out, e.reverse.entry)}
        assert len(ptrs) == STORED_LINES[k] == len(set(_plan(k).reverse_pairs)), e.name
        assert (len(ptrs) == 3) == (e.bank == 1), e.name
    assert max(size for _, size in blob.free_runs(out, 1, min_size=16)) >= BANK_ONE_FLOOR   # recon §2: 13 488 left


def test_metropolis_reverse_stores_six_lines(romset_zip, saturn_cue):
    """After the owner's drive (stage 2 findings §11.5): Metropolis's variant names the ±5 lines for the cars of the ±8 lines
    (pairs 1 and 4) and so stores six lines, two of 16 × (n + 8) bytes fewer than the eight it stored, in bank 2 beside the
    normal blob."""
    from vrtools.arcade.tencourse import METROPOLIS_PAIRS
    out, conv = _seven(romset_zip, saturn_cue)
    _, n, rv, _, re = _both(out)
    ptrs = line_pointers(out, rv)
    assert METROPOLIS_PAIRS == (0, 7, 2, 3, 5, 5, 6, 7) == _plan(METROPOLIS).reverse_pairs == conv[METROPOLIS - 3].reverse.pairs
    assert ptrs[1] == ptrs[7] and ptrs[4] == ptrs[5] and len({p for p, _ in ptrs}) == 6
    t = conv[METROPOLIS - 3].reverse.tables
    six, eight = (len(blob.build_variant_blob(t, WINDOW, WINDOW, WINDOW, WINDOW, p)) for p in (METROPOLIS_PAIRS, tuple(range(8))))
    start, end = _variant_span(out, rv)
    print("METROPOLIS variant", hex(rv.header_base), "bank", rv.bank, "bytes", end - start, "eight lines", eight,
          "bank 2 free runs", blob.free_runs(out, 2, min_size=16))
    assert eight - six == 2 * POINT_BYTES * (N + WRAP_POINTS) and end - start == (six + 15) // 16 * 16
    assert rv.bank == n.bank == 2


def test_the_bank_one_variants_start_on_the_interleaved_grid(romset_zip, saturn_cue):
    """After the owner's drive (stage 2 findings §11.5): each bank-1 variant's race blob starts car k on BANK_ONE_GRID[k] (the
    +5 line's cars on the odd points, the -5 line's on the even ones), its car table otherwise the normal one; every other
    variant's car table is the normal one; every normal race blob is what `race_blob_for` gives without a grid, its cars on
    the car table's own lines (the grid did not leak into the normal blobs; that they equal the previous build's is the one-off
    comparison of out/p26/stage2/t12/compare.txt, not this test)."""
    from dataclasses import replace
    from vrtools.arcade.tencourse import BANK_ONE_GRID
    from tests.test_convert_race import CAR_LINES
    out, _ = _seven(romset_zip, saturn_cue)
    rs = RomSet.from_zip(romset_zip)
    for entry, n_pts in COURSES.items():
        _, n, rv, _, _ = _both(out, entry)
        plan = _plan(entry)
        a, b = decode_race_blob(out, n.race), decode_race_blob(out, rv.race)
        plain = race_blob_for(rs, plan.template, n_pts, plan.time_factor, plan.pace, plan.laps, checkpoints=a.checkpoints)
        assert encode_race_blob(a, n.race) == encode_race_blob(plain, n.race), n.name
        assert [c.start_point for c in a.cars] == list(range(16)), n.name             # the normal grid: car k on point k
        assert [c.line for c in a.cars] == list(CAR_LINES), n.name                       # on the car table's own lines
        if n.bank == 1:
            assert [c.start_point for c in b.cars] == list(BANK_ONE_GRID), n.name
            assert [replace(c, start_point=0) for c in b.cars] == [replace(c, start_point=0) for c in a.cars], n.name
        else:
            assert b.cars == a.cars, n.name


def test_the_variant_shares_the_collision(romset_zip, saturn_cue):
    out, _ = _seven(romset_zip, saturn_cue)
    for entry, points in COURSES.items():
        _, n, rv, ne, re = _both(out, entry)
        assert rv.header_base != n.header_base, n.name
        a, b = decode_pointer_block(out, ne), decode_pointer_block(out, re)
        assert (a.collision, a.surface) == (b.collision, b.surface), n.name
        assert ne.header.gfx_dir == re.header.gfx_dir, n.name
        assert ne.header.road_points == re.header.road_points == points, n.name
        assert ne.header.segment_count == re.header.segment_count, n.name
    _, _, _, ne, re = _both(out)
    assert (ne.header.segment_count, re.header.segment_count) == (527, 527)


def test_the_variant_is_the_normal_tables_read_backwards(romset_zip, saturn_cue):
    """On every course: pair k of the variant's pointer block reads line `reverse_pairs[k]` of the normal blob backwards, its
    segment array is the conversion's reversed one (`Converted.reverse.tables`, which `convert.reverse.reverse_segments`
    makes); on Metropolis also stage 1's credits against the forward array."""
    out, conv = _seven(romset_zip, saturn_cue)
    for entry, n_pts in COURSES.items():
        _, n, _, ne, re = _both(out, entry)
        pairs = _plan(entry).reverse_pairs
        fl, rl = road_lines(out, ne), road_lines(out, re)
        for k in range(8):
            src = fl[pairs[k]]
            assert [(p.x, p.z) for p in rl[k]] == [(src[(n_pts - j) % n_pts].x, src[(n_pts - j) % n_pts].z) for j in range(n_pts)], (n.name, k)
            assert line_turn(rl[k]) == -line_turn(src), (n.name, k)          # the lap turns the other way
        assert segments(out, re) == conv[entry - 3].reverse.tables.segments, n.name
    _, _, _, ne, re = _both(out)
    assert all(line_turn(l) == 16384 for l in road_lines(out, re))          # Metropolis's clockwise lap
    f, r = [s.road_point for s in segments(out, ne)], [s.road_point for s in segments(out, re)]
    assert r[0] == 0 and r[1] == N - 1 and r[526] == 0                      # the lap's ends pinned (§6.3)
    assert [k for k in range(527) if r[k] == N - 1] == [1]
    assert all((f[k] + r[k]) % N in (0, 1, 2, 3, 362, 363, 364) for k in range(527)), [(k, f[k], r[k]) for k in range(527)
                                                                                        if (f[k] + r[k]) % N not in (0, 1, 2, 3, 362, 363, 364)]


SPOT_KEPT = {8, 9}          # Task 6's rule: D5 withheld (the spot's quad, the road's only n−1 one, keeps n−1): Surfers Oval and Road


def test_the_road_keeps_a_quad_credited_the_last_point_before_the_reverse_line(romset_zip, saturn_cue):
    """Stage 2 Task 6 (the lead's ruling on plan D5): on every course some tarmac quad of the course's TGP pool (pool index =
    segment index) credited n−1 in the variant's segment array holds a point of the reversed centreline before the line
    (reversed point n−1 to the spot, `reverse._before_line`): an opponent's line cursor wraps only when the car is
    credited n−1 there (Task 6 measured the field stopped at the line on Surfers Oval and Road, no car ever on n−1, with
    D5 crediting their quad 0 point 0). Where D5 applies, no quad holding the spot (point 0, within SEAM_OVERLAP) is
    credited n−1 (Amazon Falls's player had spawned on 329 and its first crossing counted no lap); where a quad holding
    the spot keeps n−1, crediting it 0 would leave no such quad (D5 withheld), on SPOT_KEPT exactly. Metropolis keeps its
    one n−1 quad (quad 1, +3.9..+15.6). Away from the line each quad's reverse credit is n − its forward one plus about
    its length in points (forward credits the front edge, reverse the rear): (forward + reverse) mod n measured −3..+10 on
    the seven (Task 4, Alpine's quad 242 the +10), so an array not read backwards (hundreds of points off) fails here."""
    from vrtools.arcade import tgp
    from vrtools.convert.collision import _point_in_xz
    from vrtools.convert.reverse import _before_line
    out, _ = _seven(romset_zip, saturn_cue)
    w = tgp.words(out)
    kept = set()
    for entry, n_pts in COURSES.items():
        _, n, _, ne, re = _both(out, entry)
        _, pool = tgp.slot_table(out)[n.tgp_slot]
        rps = [s.road_point for s in segments(out, re)]
        quads = [tgp.decode_quad(w, pool + tgp.QUAD_WORDS * k) for k in range(len(rps))]
        line = road_lines(out, re)[0]
        spot = line[0]
        before = _before_line([(spot.x, spot.z), (line[n_pts - 1].x, line[n_pts - 1].z)])
        last = [k for k in range(len(rps)) if rps[k] == n_pts - 1 and any(_point_in_xz(quads[k].corners, x, z) for x, z in before)]
        under = [k for k in range(len(rps)) if _holds(quads[k], spot.x, spot.z)]
        assert last, (n.name, [k for k in range(len(rps)) if rps[k] == n_pts - 1])
        assert under, n.name
        if any(rps[k] == n_pts - 1 for k in under):
            kept.add(entry)
            assert set(last) <= set(under), (n.name, last, under)               # withheld only where D5 would leave none
        f = [s.road_point for s in segments(out, ne)]
        off = {k: (f[k] + rps[k] + n_pts // 2) % n_pts - n_pts // 2 for k in range(len(rps)) if 10 <= f[k] <= n_pts - 10}
        assert all(-3 <= v <= 12 for v in off.values()), (n.name, [(k, f[k], rps[k]) for k, v in off.items() if not -3 <= v <= 12])
    assert kept == SPOT_KEPT, kept
    _, _, _, _, re = _both(out)
    assert [k for k, s in enumerate(segments(out, re)) if s.road_point == N - 1] == [1]


def test_the_variants_race_blob(romset_zip, saturn_cue):
    out, _ = _seven(romset_zip, saturn_cue)
    _, n, rv, _, _ = _both(out)
    a, b = decode_race_blob(out, n.race), decode_race_blob(out, rv.race)
    assert rv.race != n.race
    assert b.checkpoints == (0, 143, 239)                       # the normal checkpoints 0, 126, 222 numbered backwards
    assert b.times[(0, 0)].initial == 2080
    assert b.times[(0, 0)].extensions[:6] == (381, 256, 336, 381, 256, 336)
    assert a.times[(0, 0)].extensions[:3] == (336, 256, 381)    # the normal blob: its sectors in forward order
    assert b.cars == a.cars


# The variant's checkpoints are the normal lap's renumbered for the reversed lap, less any within GATE_START_GAP points after the
# line (stage 3 Task 8, Pascal, 13 Nov, after driving stage 3's set: Diablo Canyon's START arch, 36 points after the reverse line,
# stays scenery and fires nothing; it replaces their stage 2 drive choice, under which it fired). The six other courses' did not
# change with either rule.
REVERSE_CHECKPOINTS = {3: (0, 119, 260, 387), 4: (0, 93, 213), 5: (0, 168, 278), 6: (0, 143, 239), 7: (0, 90, 224),
                       8: (0, 88, 260), 9: (0, 142, 314)}
DIABLO_REVERSE_EXTENSIONS = {0: (432, 283, 460), 1: (418, 274, 445)}   # level 0, variants 0 and 1: stage 2 findings §11.4's
                                                                      # "reverse before" row (its first reverse build, scaled)
DIABLO_ARCH = 36            # Diablo Canyon's START arch in reverse: forward point 421 of 457, no checkpoint since Task 8


def test_the_variants_checkpoints_are_the_normal_ones_renumbered(romset_zip, saturn_cue):
    """On all seven courses the variant's race blob fires the normal blob's checkpoints, each g at (n − g) mod n of the reversed
    lap, less any within GATE_START_GAP points after the line: nothing fires in reverse that does not fire forward (Diablo
    Canyon's START arch, forward point 421, 36 points after the reverse start, is the one point left out)."""
    out, _ = _seven(romset_zip, saturn_cue)
    for entry, n_pts in COURSES.items():
        _, n, rv, _, _ = _both(out, entry)
        a, b = decode_race_blob(out, n.race), decode_race_blob(out, rv.race)
        assert b.checkpoints == tuple(p for p in sorted((n_pts - g) % n_pts for g in a.checkpoints)
                                      if p == 0 or p >= GATE_START_GAP), (n.name, a.checkpoints, b.checkpoints)
        assert b.checkpoints == REVERSE_CHECKPOINTS[entry], (n.name, b.checkpoints)


def test_a_reverse_lap_has_the_normal_laps_time(romset_zip, saturn_cue):
    """Stage 2 (plan D4): on every course and each of the 12 time records the reverse lap's first-lap sum is the normal lap's
    and the course's laps fit the record (`check_laps`); Metropolis, whose reverse
    sectors are the normal ones in another order, keeps the blob `race_blob_for` gives without `lap_totals`. The six courses
    whose variant has the normal lap's sectors in reverse order have equal sums; Diablo Canyon's three reverse sectors (stage 3
    Task 8) have the normal lap's total spread over them, equal within `len(checkpoints)` (rounding), with level 0's
    extensions those of stage 2's first reverse build (findings §11.4)."""
    out, _ = _seven(romset_zip, saturn_cue)
    for entry in COURSES:
        _, n, rv, _, _ = _both(out, entry)
        a, b = decode_race_blob(out, n.race), decode_race_blob(out, rv.race)
        assert sorted(a.times) == sorted(b.times) and len(a.times) == 12
        check_laps(rv.laps, b.checkpoints)
        for key in a.times:
            rsum, nsum = lap_total(b.times[key], b.checkpoints), lap_total(a.times[key], a.checkpoints)
            if entry == DIABLO:
                assert abs(rsum - nsum) <= len(b.checkpoints), (n.name, key, rsum, nsum)
            else:
                assert rsum == nsum, (n.name, key)
        if entry == DIABLO:
            print("DIABLO reverse sums", [lap_total(b.times[k], b.checkpoints) for k in sorted(b.times)],
                  "normal", [lap_total(a.times[k], a.checkpoints) for k in sorted(a.times)])
            for v, ext in DIABLO_REVERSE_EXTENSIONS.items():
                assert b.times[(v, 0)].extensions[:3] == ext, (v, b.times[(v, 0)].extensions[:6])
    _, n, rv, _, _ = _both(out)
    plan = _plan(METROPOLIS)
    b = decode_race_blob(out, rv.race)
    plain = race_blob_for(RomSet.from_zip(romset_zip), plan.template, N, plan.time_factor, plan.pace, plan.laps, checkpoints=b.checkpoints)
    assert encode_race_blob(b, rv.race) == encode_race_blob(plain, rv.race)


def test_the_variant_only_adds_bytes(romset_zip, saturn_cue):
    """With the variants, the set is the set without them plus bytes on erased ROM: the annex [lo, hi) in the program ROM, each
    variant's blob in its entry's data bank, and the entries' words of the directory's reverse table: nothing of the normal
    build moves or is overwritten. The boot ROM is the same: the direction sites are patched with or without the variants."""
    import numpy as np
    a = ten_course_set(*_built(romset_zip, saturn_cue), reverse=False)
    b, _ = _seven(romset_zip, saturn_cue)
    assert (a.boot, a.polygons, a.copro_data, a.tgp_program) == (b.boot, b.polygons, b.copro_data, b.tgp_program)
    d = decode_directory(b)
    assert all(e.reverse is None for e in decode_directory(a))
    ad, bd = np.frombuffer(a.data, np.uint8), np.frombuffer(b.data, np.uint8)
    data = np.flatnonzero(ad != bd)
    spans = [_variant_span(b, e.reverse.entry) for e in d[3:10]]
    assert len(data) and (ad[data] == 0xFF).all()
    inside = np.zeros(len(data), bool)
    for s, t in spans:
        inside |= (s <= data) & (data < t)
    assert inside.all(), [hex(i) for i in data[~inside][:8]]                     # each variant's blob, in its own bank
    lo, hi = _annex(d)
    table = directory_layout()["reverse"] - V60_PROGRAM                         # the ten words of the reverse table
    ap, bp = np.frombuffer(a.program, np.uint8), np.frombuffer(b.program, np.uint8)
    prog = np.flatnonzero(ap != bp)
    assert len(prog)
    words = (table <= prog) & (prog < table + 40)
    assert ((lo - V60_PROGRAM <= prog[~words]) & (prog[~words] < hi - V60_PROGRAM)).all(), [hex(V60_PROGRAM + i) for i in prog[~words][:8]]
    assert (ap[prog[~words]] == 0xFF).all()                                      # the annex was erased
    assert (ap[table:table + 40] == 0).all()                                     # no reverse record in the set without


# --- Phase 26 (Task 8): the reverse race in MAME, against a normal-direction control run in the same session -----------------
# Stage 2 Task 6: on each of the seven courses (COURSES), each direction raced once per session (`_direction_race`'s cache).
# Each race: 150 s of the entry under the autopilot (the drive line, read backwards in reverse), RAM dumps every 250 frames,
# the race log (the player per frame, a J line per opponent jolt), the edge log and the field log every second frame. The
# loggers' frames: race_log.lua and edges_log.lua count from 1, fieldtrace.lua samples from 0 (its frame f is their f + 1).
# The wrong-way warning (boot 0xff4c9e, recon §6): when the yaw is within 0x800 of opposite the quad's direction it draws the
# tile map 0x2F4D36 if [0x40DC9B] is 0, or else prints the string "REVERSE" at 0xFF4D0F. On this set it takes the string path:
# measured 12 Nov on the reverse variant with the flag held at 0 from the race on (the quads' direction as authored), the
# string is read by 0xff871e on 278 frames of 60 s and the tile map only by the boot's copy at frame 258; with the flag 1, on
# none. Both are tapped.
WARNING_READS = "2f4d36-2f4d39,ff4d10-ff4d15"
WARNING_STRING = (0xFF4D10, 0xFF4D15)       # the string's bytes read by 0xff871e (the taps' second range)
START_LOAD_FRAME = 1600     # the course load in this harness (figures_log.lua's L line; STANDING_GREEN's recon: 1864 - 1600)
CARS_TO = 2700              # race_log.lua's O lines (the opponents each frame) end here: the green + START_FRAMES and more on every race
_RACES: dict[tuple[int, bool], tuple] = {}


def _direction_race(tmp_path, romset_zip, saturn_cue, entry, reverse):
    """(workdir, Converted, race_report) of 150 s of `entry` in one direction, run once per session per (entry, reverse)."""
    if (entry, reverse) not in _RACES:
        out, conv = _seven(romset_zip, saturn_cue)
        c = conv[entry - 3]
        assert c.entry.name == _plan(entry).name
        base = tmp_path / ("reverse" if reverse else "normal")
        wd = base / f"entry{entry}"
        logs = {"VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_CARS_TO": str(CARS_TO),
                "VR_EDGES_LOG": str(wd / "edges.txt"), "VR_FIELD_LOG": str(wd / "field.txt"),
                "VR_FIELD_FROM": "1400", "VR_FIELD_TO": "999999", "VR_FIELD_EVERY": "2",
                "VR_TRACE_READ": WARNING_READS, "VR_TRACE_TO": "999999"}         # the dumps' tracer also taps the wrong-way warning
        wd = _race(base, out, romset_zip, entry, c, seconds=150, reverse=reverse, extra_env=logs)
        _RACES[entry, reverse] = (wd, c, race_report(wd, COURSES[entry]))
    return _RACES[entry, reverse]


def _reverse_race(tmp_path, romset_zip, saturn_cue, entry):
    """(workdir, Converted, race_report) of the reverse race of `entry`, run once per session."""
    return _direction_race(tmp_path, romset_zip, saturn_cue, entry, True)


def _normal_race(tmp_path, romset_zip, saturn_cue, entry):
    """The same race in the normal direction: the control every reverse bound is measured against."""
    return _direction_race(tmp_path, romset_zip, saturn_cue, entry, False)


def _lead_max(entry):
    """The normal test's cursor-lead bound of the course (test_race_build's own constants)."""
    return CURSOR_LEAD_MAXES.get(_plan(entry).name, CURSOR_LEAD_MAX)


def _window(player):
    """The race in race-log frames [start, end): from the first frame the clock counts down to the first it has run out
    (or the end of the log)."""
    start = next(b.frame for a, b in zip(player, player[1:]) if 0 < b.clock < a.clock)
    end = next((p.frame for p in player if p.frame > start and p.clock <= 0), player[-1].frame + 1)
    return start, end


def _player(wd):
    """The player's P lines inside the race, the J lines inside it, and the window."""
    player, jolts = parse_race_log(wd / "race.txt")
    start, end = _window(player)
    return [p for p in player if start <= p.frame < end], [j for j in jolts if start <= j.frame < end], (start, end)


def _cars(wd, window):
    """The field log inside the race window, per car (fieldtrace's frame f is the race log's f + 1)."""
    start, end = window
    cars: dict[int, list] = {}
    for s in parse_field(wd / "field.txt"):
        if start <= s.frame + 1 < end:
            cars.setdefault(s.car, []).append(s)
    return cars


def _crossings(cars, n=N):
    """Per car: steps back over the line (the road point jumping up by more than n - 100), wraps whose lap byte did not
    rise by one, the wraps counted, the opponents' largest cursor lead over the road point, and per wrap the frames the
    car sat on point n - 1 before it (two frames per field sample)."""
    back, bad_lap, wraps, lead, on_last = [], [], {}, 0, []
    for car, s in cars.items():
        wraps[car] = 0
        for k in range(1, len(s)):
            a, b = s[k - 1], s[k]
            if b.point - a.point > n - 100:
                back.append((car, a.frame, a.point, b.point))
            if a.point - b.point > 100:
                wraps[car] += 1
                if b.lap != a.lap + 1:
                    bad_lap.append((car, b.frame, a.lap, b.lap))
                run = 0
                while k - 1 - run >= 0 and s[k - 1 - run].point == n - 1:
                    run += 1
                on_last.append(2 * run)
        if car:
            lead = max([lead] + [(q.cursor - q.point + n // 2) % n - n // 2 for q in s])
    return {"back": back, "bad_lap": bad_lap, "wraps": wraps, "lead": lead, "on_last": on_last}


@pytest.mark.parametrize("entry", list(COURSES))
def test_the_reverse_race_runs_on_its_own_tables(tmp_path, romset_zip, saturn_cue, entry):
    """Stage 2 Task 6 adds: at the first frame of the race (the clock's first count) the player stands on the variant's road
    point 0 (Amazon Falls's trial spawned on 329, credited n−1, before plan D5; Alpine's on 440 under the crew start before
    plan D6), and the wrong-way string is read on no frame of the run."""
    from vrtools.arcade.race import race_blob_layout
    from vrtools.arcade.trace import parse_trace
    from vrtools.mame.runner import parse_rate
    wd, c, r = _reverse_race(tmp_path, romset_zip, saturn_cue, entry)
    out, _ = _seven(romset_zip, saturn_cue)
    rv = decode_directory(out)[entry].reverse.entry
    player, _, window = _player(wd)
    lo, hi = WARNING_STRING
    string = sorted({e.frame for e in parse_trace(wd / "trace.log") if e.kind == "R" and lo <= e.addr <= hi})
    print("RACE reverse", c.entry.name, {k: v for k, v in r.items() if k not in ("frames", "clock", "cars")},
          "window", window, "start point", player[0].road_point, "string frames", len(string), string[:8])
    lay = race_blob_layout(rv.race)
    assert r["time_record"] == lay["records"] and r["checkpoint_record"] == lay["checkpoints"]   # the variant's blob, level 0
    assert r["laps_setting"] == 5
    assert r["opponents_at_origin"] == 0, r
    rates = parse_rate(wd / "rate.txt")
    rate = [k for f, k in rates if f > 2000]
    assert rate and min(rate) >= RATE_FLOOR, min(rate) if rate else None
    # The start (stage 2 fix wave): the 57-frame windows that end after the course load and by frame 2000 (the first, ending
    # at 1653, holds the figures' first 49 frames and 3 frames before the load; it read 29 in every log), the
    # frames of the mirrored start figures (load + 5 .. about + 456), the gantry behind the car on Alpine, Diablo Canyon and
    # Pacific Coast, the Saturn START gate and its lettering copies, the grid and the green (load + 266). The load is frame
    # 1600 in this harness (figures_log.lua's L line, every Metropolis and Diablo Canyon run of t7/ and t13/). The boot's
    # first window (frame 57) reads 24 in every run and is left out; every other window of every existing rate log (the seven
    # courses, both directions, on the integrated tree and before it) read 28-29, and on the merged set out/p26play3 the
    # reverse starts of Diablo Canyon and Metropolis 28-29 in every window from the load to the green + 400 (findings §11.6).
    start = [(f, k) for f, k in rates if START_LOAD_FRAME < f <= 2000]
    assert start and min(k for _, k in start) >= RATE_FLOOR, start
    assert player[0].road_point == 0, player[0]
    assert not string, string[:8]


@pytest.mark.parametrize("entry", list(COURSES))
def test_every_car_counts_a_lap_at_each_reverse_crossing(tmp_path, romset_zip, saturn_cue, entry):
    """Every crossing of every car in the field log (every second frame; review focus 3): no car steps back over the line, each wrap
    raises the lap byte by one, no opponent's cursor runs on past the course's bound in the normal test. The normal run is the
    control: the lap-byte form asserted is the one its log satisfies, and the reverse run is held to the same."""
    n = COURSES[entry]
    seen = {}
    for name, race in (("normal", _normal_race), ("reverse", _reverse_race)):
        wd, c, _ = race(tmp_path, romset_zip, saturn_cue, entry)
        _, _, window = _player(wd)
        x = seen[name] = _crossings(_cars(wd, window), n)
        print("CROSSINGS", c.entry.name, name, {k: v for k, v in x.items() if k != "on_last"}, f"on point {n - 1}:", sorted(x["on_last"]))
    for name in ("normal", "reverse"):
        x = seen[name]
        assert not x["back"], (name, x["back"][:8])
        assert not x["bad_lap"], (name, x["bad_lap"][:8])
        assert x["lead"] <= _lead_max(entry), (name, x["lead"])
        assert x["wraps"][0] >= 1 and sum(1 for car in range(1, 16) if x["wraps"].get(car, 0) >= 1) >= 14, (name, x["wraps"])


@pytest.mark.parametrize("entry", list(COURSES))
def test_reverse_checkpoints_fire_in_order_and_extend_the_time(tmp_path, romset_zip, saturn_cue, entry):
    """The variant's gates fire in their order from its first past the line, each adding its extension of the level-0 record
    (or one less: the clock sampled a frame after its own count)."""
    wd, c, _ = _reverse_race(tmp_path, romset_zip, saturn_cue, entry)
    out, _ = _seven(romset_zip, saturn_cue)
    rb = decode_race_blob(out, decode_directory(out)[entry].reverse.entry.race)
    gates, ext = rb.checkpoints, rb.times[(0, 0)].extensions
    player, _, window = _player(wd)
    fires = [(b.road_point, b.clock - a.clock) for a, b in zip(player, player[1:]) if b.clock > a.clock > 0]
    print("FIRES reverse", c.entry.name, "gates", gates, "extensions", ext[:2 * len(gates)], "window", window, fires)
    assert len(fires) >= 3
    for i, (rp, gain) in enumerate(fires):
        assert 0 <= (rp - gates[(i + 1) % len(gates)]) % COURSES[entry] <= 4 and gain in (ext[i], ext[i] - 1), (i, rp, gain)
    # Nothing fires between the green and the first checkpoint: the clock only falls while the player's road point goes from 0
    # to gates[1]. On Diablo Canyon (stage 3 Task 8) the player is seen past the START arch, forward point 421, reverse point
    # 36, which no longer fires, so the check cannot pass on an empty stretch.
    first = next(k for k, p in enumerate(player) if gates[1] <= p.road_point < COURSES[entry] // 2)
    run = player[:first + 1]
    assert all(b.clock <= a.clock for a, b in zip(run, run[1:])), [(a.frame, a.road_point, a.clock, b.clock)
                                                                   for a, b in zip(run, run[1:]) if b.clock > a.clock][:4]
    if entry == DIABLO:
        arch = [p for p in run if DIABLO_ARCH <= p.road_point < gates[1]]
        print("DIABLO green to point", gates[1], "frames", run[0].frame, run[-1].frame, "clock", run[0].clock, run[-1].clock,
              "past the arch at", arch[0].frame if arch else None, arch[0].clock if arch else None)
        assert arch, [(p.frame, p.road_point) for p in run[::50]]


@pytest.mark.parametrize("entry", list(COURSES))
def test_the_reverse_field_races(tmp_path, romset_zip, saturn_cue, entry):
    _, c, r = _reverse_race(tmp_path, romset_zip, saturn_cue, entry)
    print("FIELD reverse", c.entry.name, {k: r[k] for k in ("moved", "parked", "parked_cars", "max_backstep", "max_cursor_lead", "leader_points")},
          [g[-1] - g[0] for g in r["cars"]])
    assert r["moved"] >= MOVED_FLOOR, {k: r[k] for k in ("moved", "cars")}
    assert r["parked"] <= PARKED_DEFAULT, {k: r[k] for k in ("parked", "parked_cars")}
    assert r["max_backstep"] <= BACKSTEP_MAX, {k: r[k] for k in ("max_backstep", "cars")}
    assert r["max_cursor_lead"] <= _lead_max(entry), r["max_cursor_lead"]           # the normal test's bound for the course
    assert r["leader_points"] >= LEADER_FLOOR, r["leader_points"]
    assert all(g[-1] - g[0] > 0 for g in r["cars"]), [g[-1] - g[0] for g in r["cars"]]


@pytest.mark.parametrize("entry", list(COURSES))
def test_reverse_jolts_are_of_the_order_of_the_normal_race(tmp_path, romset_zip, saturn_cue, entry):
    """The off-tarmac jolts (an opponent's smoke counter rising from 0) inside the race window, against the normal race of
    the same course in the same session (Phase 25's survey counted 57 on normal Metropolis)."""
    count = {}
    for name, race in (("normal", _normal_race), ("reverse", _reverse_race)):
        wd, c, _ = race(tmp_path, romset_zip, saturn_cue, entry)
        _, jolts, window = _player(wd)
        count[name] = len(jolts)
        print("JOLTS", c.entry.name, name, len(jolts), "window", window)
    assert count["reverse"] <= 1.5 * count["normal"] + 10, count


# --- Stage 2, after the owner's drive (stage 2 findings §11.5): the standing grid and the start -----------------------------------
# Pascal on Surfers Road in reverse: "lot of opponent crashes between each other right at the start trying to overtake". Measured
# cause: on the standing grid the game's "car directly behind" avoidance (contact B) turned cars standing 10 units nose to tail on one
# stored line towards a corner of their link word's quad, behind or beside them in reverse; six cars started turned 52-68 degrees and
# three ran onto the run-off at the green. The bank-1 variants now start on BANK_ONE_GRID. Both measures read race_log.lua's O lines
# (each opponent each frame to CARS_TO) and J lines of the races above; the green is the race window's start (the clock's first count).
#
# The direction of travel of a standing car is that of its own stored line ahead: at standstill the game turns an unpushed car at once
# to face its line's target (the steer divides by 1 there), 30-70 units ahead (Phase 25), so the measure is the yaw against the
# direction from the car to its line's point k ahead, the best of k = 3..7. Measured 12 Nov on this tree (one run per course, the runs
# are deterministic; out/p26/stage2/t12/): every unpushed car 0.0 degrees; against the local tangent instead (point j − 1 to j + 1),
# bank-1 grids on bends read up to 24.4 (Pacific Coast's last rows on its 28-degree bend) with no car turned.
GRID_FRAMES = 60            # the standing grid: the last frames before the green (the field is placed and turned about 260 frames before it)
START_FRAMES = 200          # the start: the green to 200 frames (3.5 s) after it. The bank-1 courses' first-bend jolts come 219-417 frames
                            # after the green (Pacific Coast's cut 159, counted); the grid pushes' 57-81. It is the investigation's start
                            # window in effect: that took the green 400 frames early (a stale speed) and so ended 200 frames after it
GRID_YAW_MAX = {4: 5.0, 7: 5.0, 8: 5.0, 9: 5.0,   # degrees. The bank-1 courses on BANK_ONE_GRID: 0.0 measured on all four (before it
                                                 # 62.3, 56.2, 74.5, 67.2: three to six cars turned); 5 is the investigation's figure
                3: 64.4,     # KNOWN FAULT (Alpine, not fixed here; findings §11.5): cars 3, 9 and 15 stand turned 30, 24 and 63.9
                5: 37.9,     # KNOWN FAULT (Diablo Canyon): cars 4, 5, 7, 9, 11, 13, 14 turned 10-37.4
                6: 36.0}     # KNOWN FAULT (Metropolis, on METROPOLIS_PAIRS): cars 3, 5, 6, 7, 10 turned 23-35.5 (on eight lines, the
                             # investigation's run: cars 5, 7, 10, 28-31.8).
                             # The three bounds are the measurement plus 0.5 degree, so a change shows; the normal grids have cars
                             # turned 16-45.5 on every course, harmlessly (the push corners ahead of the car there)
START_CARS_MAX = {4: 0, 8: 0, 9: 0,   # opponents whose smoke counter rises in START_FRAMES, as measured: the bank-1 grid ones 0 (before
                                      # it Amazon Falls 1, Surfers Oval 3, Surfers Road 3, all three pushed to the edge from the grid)
                  7: 1,      # Pacific Coast: car 15 cutting the first sharp bend at reverse point 20, 159 frames after the green (before: 3,
                             # the same cut). Looser than the normal run's 0, the one stated exception: the cut is on the -5 line, the open
                             # AI-lines item, not the grid (ruling of the session lead)
                  3: 1,      # Alpine: car 1 at reverse point 3, 34 frames after the green; a measured regression bound (car 1 is not
                             # turned on the grid; the normal run counted 3, cars 2, 5, 6)
                  5: 2,      # Diablo Canyon: cars 7 and 8, 75 and 161 frames after the green; a measured regression bound (the normal
                             # run counted 3, cars 6, 8, 9)
                  6: 0}      # Metropolis


def _grid_and_start(wd, out, entry, reverse):
    """({car: largest |yaw − direction of travel| in degrees over the GRID_FRAMES before the green}, the opponents with a J line in the
    START_FRAMES after it, the green, the speeds seen on the grid). The direction of travel of a car: from it to the point k ahead
    of the line its car-table entry names in the served pointer block, the best of k = 3..7 (above)."""
    from vrtools.mame.runner import parse_race_cars
    _, n, rv, ne, re = _both(out, entry)
    served = rv if reverse else n
    lines = road_lines(out, re if reverse else ne)
    cars = decode_race_blob(out, served.race).cars
    _, jolts, (green, _) = _player(wd)
    assert green + START_FRAMES <= CARS_TO, green
    yaw, speeds = {}, set()
    for s in parse_race_cars(wd / "race.txt"):
        if green - GRID_FRAMES <= s.frame < green:
            line = lines[cars[s.car].line]
            off = min(abs((s.yaw * 360 / 65536 - math.degrees(math.atan2(-(p.x - s.x), p.z - s.z)) + 180) % 360 - 180)  # yaw: +z 0, +x −0x4000
                      for p in (line[(s.road_point + k) % len(line)] for k in range(3, 8)))
            yaw[s.car] = max(yaw.get(s.car, 0.0), off)
            speeds.add(s.speed)
    start = sorted({j.car for j in jolts if j.frame < green + START_FRAMES})
    return yaw, start, green, speeds


@pytest.mark.parametrize("entry", list(COURSES))
def test_no_opponent_stands_turned_on_the_reverse_grid(tmp_path, romset_zip, saturn_cue, entry):
    """On the standing grid before the green, no opponent's yaw differs from the direction of travel by more than the course's
    bound (GRID_YAW_MAX); the normal race's grid is printed beside it (the same push turns cars there too, harmlessly)."""
    out, _ = _seven(romset_zip, saturn_cue)
    seen = {}
    for name, race in (("normal", _normal_race), ("reverse", _reverse_race)):
        wd, c, _ = race(tmp_path, romset_zip, saturn_cue, entry)
        yaw, start, green, speeds = seen[name] = _grid_and_start(wd, out, entry, name == "reverse")
        print("GRID", c.entry.name, name, "green", green, "largest", round(max(yaw.values()), 1),
              {car: round(v, 1) for car, v in sorted(yaw.items())}, "speeds", sorted(speeds))
    yaw, _, _, speeds = seen["reverse"]
    assert sorted(yaw) == list(range(1, 16)) and speeds == {0}, (sorted(yaw), speeds)       # the fifteen, standing
    assert max(yaw.values()) <= GRID_YAW_MAX[entry], {car: round(v, 1) for car, v in yaw.items() if v > GRID_YAW_MAX[entry]}


@pytest.mark.parametrize("entry", list(COURSES))
def test_few_opponents_leave_the_tarmac_at_the_reverse_start(tmp_path, romset_zip, saturn_cue, entry):
    """The opponents whose smoke counter rises in the START_FRAMES after the green stay within the course's bound
    (START_CARS_MAX); the normal race's are printed beside them."""
    out, _ = _seven(romset_zip, saturn_cue)
    seen = {}
    for name, race in (("normal", _normal_race), ("reverse", _reverse_race)):
        wd, c, _ = race(tmp_path, romset_zip, saturn_cue, entry)
        _, start, green, _ = seen[name] = _grid_and_start(wd, out, entry, name == "reverse")
        print("STARTCARS", c.entry.name, name, "green", green, "cars", start)
    assert len(seen["reverse"][1]) <= START_CARS_MAX[entry], seen["reverse"][1]


@pytest.mark.parametrize("entry", list(COURSES))
def test_the_game_sees_the_quads_turned_round(tmp_path, romset_zip, saturn_cue, entry):
    """The direction half only (the seven TGP-0x1500 sites, the six edge values, are untouched in stage 1: findings §4): the
    attribute every car stores at +0xeb is its quad's direction in the course's TGP pool, turned half a turn in the reverse
    race and as authored in the normal one, on at least 99 % of the E lines inside the race. Uses the attribute's own
    snapshot (attr quad, attr): fresh on every store. The game's own wrong-way warning, which compares that direction with the
    yaw, is never read during either race (its positive control is the next test)."""
    from vrtools.arcade import tgp
    from vrtools.arcade.trace import parse_trace
    out, conv = _seven(romset_zip, saturn_cue)
    slot = conv[entry - 3].entry.tgp_slot
    assert slot == decode_directory(out)[entry].tgp_slot
    w = tgp.words(out)
    _, pool = tgp.slot_table(out)[slot]
    quad = {}
    for name, race, turn in (("normal", _normal_race, 0), ("reverse", _reverse_race, 0x8000)):
        wd, c, _ = race(tmp_path, romset_zip, saturn_cue, entry)
        _, _, (start, end) = _player(wd)
        lines = [e for e in parse_edges(wd / "edges.txt") if start <= e.frame < end and e.attr_frame]
        for e in lines:
            if e.attr_quad not in quad:
                quad[e.attr_quad] = tgp.decode_quad(w, pool + tgp.QUAD_WORDS * e.attr_quad).attr
        good = sum(1 for e in lines if e.attr == (quad[e.attr_quad] + turn) & 0xFFFF)
        warned = sorted({e.frame for e in parse_trace(wd / "trace.log") if e.kind == "R" and start <= e.frame < end})
        print("ATTR", c.entry.name, name, good, "of", len(lines), "warning frames", len(warned))
        assert lines and good >= 0.99 * len(lines), (name, good, len(lines))
        assert not warned, (name, warned[:8])                   # the game's wrong-way check stays silent the whole race


def test_the_wrong_way_warning_is_read_when_the_game_sees_the_car_against_its_quads(tmp_path, romset_zip, saturn_cue):
    """The positive control of the warning taps (the whole-branch review): 60 s of the reverse race under the reverse autopilot,
    once with the flag forced back to 0 from the race on (direction_off.lua, mode 0x14: the loader has served the variant and
    written back 1, so the car drives the reversed tables while `dirattr` returns the quads' direction as authored, and the game
    sees the car travel against its quads) and once with the flag left at 1. The warning's string ("REVERSE", 0xFF4D0F: this
    set's path, read by 0xff871e) must be read on many frames of the race window in the first run (278 frames in the 12 Nov
    scratch run; the floor 50) and nothing of WARNING_READS on any frame of it in the second."""
    from vrtools.arcade.trace import parse_trace
    out, conv = _seven(romset_zip, saturn_cue)
    c = conv[3]
    seen = {}
    from vrtools.arcade.course import DIRECTION_RAM
    for label, extra in (("dropped", {"VR_EXTRA_LUA": str(LUA_DIR / "direction_off.lua"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"}), ("held", {})):
        base = tmp_path / label
        wd = base / f"entry{METROPOLIS}"
        _drive_entry(base, out, romset_zip, METROPOLIS, c, seconds=60, reverse=True,
                     extra_env={"VR_RACE_LOG": str(wd / "race.txt"), "VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_READ": WARNING_READS,
                                "VR_TRACE_FROM": "0", "VR_TRACE_FINE": "1", **extra})
        _, _, (start, end) = _player(wd)
        reads = [e for e in parse_trace(wd / "trace.log") if e.kind == "R" and start <= e.frame < end]
        seen[label] = (sorted({e.frame for e in reads if 0xFF4D10 <= e.addr <= 0xFF4D15}), sorted({e.frame for e in reads}))
        print("WARNING", label, "window", (start, end), "string frames", len(seen[label][0]), "frames with any warning read",
              len(seen[label][1]), "readers", sorted({hex(e.pc) for e in reads}))
    assert len(seen["dropped"][0]) >= 50, seen["dropped"][0][:8]
    assert not seen["held"][1], seen["held"][1][:8]


# The steer, per direction raced: (drive-line point of that direction, wheel, frames held). The plan's point 60 with the
# wheel at 20 for 350 frames made no put-back in either direction (measured 12 Nov: off-course counter at most 18 normal,
# 5 reverse): Metropolis's walls stand 0-9 units past the tarmac's edge all round the lap, on both sides, and a car driven
# at them is turned back onto the road by the wall code before the counter reaches 128. Tuned on [normal] first (Task 8
# sweep: 18 holds at 17 points normal, 17 at 13 points reverse); the place found where a car stays off the tarmac for 128
# logic frames is the run-off around (-270, -478), beside forward points 330-334 (reversed 31-35), and each direction
# reaches it from its own side: normal from point 330 with the wheel right, reverse from point 22 with the wheel left.
# Point 330 is reached about 66 s into the race, so the run is 120 s.
STEER = {"normal": (330, 236, 200), "reverse": (22, 20, 350)}
RETUNE = ("The steer is finely tuned (STEER: one run-off, found by the Task 8 sweep of 35 holds described above it, the only place "
          "where a car stays off the tarmac for 128 logic frames): a change to the drive line, the autopilot, the field or the "
          "walls can move the car off it, and STEER may need a retune by the same sweep before this says anything about facing.")


def _angle(a):
    return (a + 0x8000) % 0x10000 - 0x8000


@pytest.mark.parametrize("direction", ["normal", "reverse"])
def test_a_car_put_back_faces_the_direction_of_the_race(tmp_path, romset_zip, saturn_cue, direction):
    """Review focus 4: the wheel held from a point of the direction raced (STEER) takes the car off the road; the game puts
    it back facing the direction raced (the put-back turns the yaw to the quad's direction, half a turn added in reverse), and
    its wrong-way warning (the tile map 0x2F4D36 or the string "REVERSE") is never read while the car drives that direction
    before the steer."""
    from vrtools.arcade.trace import parse_trace
    reverse = direction == "reverse"
    out, conv = _seven(romset_zip, saturn_cue)
    c = conv[3]
    line = _drive_line(c)
    point, wheel, frames = STEER[direction]
    x, z = (reverse_points(line) if reverse else line)[point]
    base = tmp_path / direction
    wd = base / f"entry{METROPOLIS}"
    _drive_entry(base, out, romset_zip, METROPOLIS, c, seconds=120, reverse=reverse,
                 extra_env={"VR_RACE_LOG": str(wd / "race.txt"), "VR_EXTRA_LUA": str(LUA_DIR / "steer_at.lua"),
                            "VR_STEER_AT": f"{x}:{z}:{wheel}:{frames}", "VR_STEER_LOG": str(wd / "steer.txt"),
                            "VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_READ": WARNING_READS, "VR_TRACE_FROM": "0"})
    log = wd / "steer.txt"                                   # written when the hold begins: no file, the steer never triggered
    assert log.exists(), "the steer never triggered: the car never came within 12 units of STEER's point. " + RETUNE
    _, steer, race_start = log.read_text().split()
    steer, race_start = int(steer), int(race_start)
    assert race_start > 0 and steer > race_start + 300, (race_start, steer)
    warned = sorted({e.frame for e in parse_trace(wd / "trace.log") if e.kind == "R"})
    assert not [f for f in warned if race_start + 300 <= f < steer], [f for f in warned if race_start + 300 <= f < steer][:8]
    e10 = decode_directory(out)[METROPOLIS]
    e10 = e10.reverse.entry if reverse else e10
    raced = road_lines(out, course_entry_at(out, e10.bank, e10.header_base))[0]
    player = [p for p in parse_race_log(wd / "race.txt")[0] if p.frame >= steer]
    full = next((i for i, p in enumerate(player) if p.off_course >= OFF_COURSE_LIMIT), None)
    assert full is not None, f"no put-back: the off-course counter reached {max(p.off_course for p in player)}, not {OFF_COURSE_LIMIT}. " + RETUNE
    back = next((i for i in range(full, len(player)) if player[i].off_course == 0), None)
    assert back is not None, "no put-back: the counter reached the limit but never returned to 0. " + RETUNE
    t0 = player[back].frame
    after = {p.frame: p for p in player if t0 <= p.frame <= t0 + 400}

    def nearest(p):
        return min(raced, key=lambda q: (q.x - p.x) ** 2 + (q.z - p.z) ** 2)
    p60 = after[t0 + 60]
    facing = _angle(p60.yaw - 4 * (nearest(p60).heading >> 16))          # the heading's high half, 1/16384 turn; the yaw 1/65536
    dist = min(math.hypot(nearest(p).x - p.x, nearest(p).z - p.z) for p in after.values())
    rise = max((p.road_point - player[back].road_point + N // 2) % N - N // 2 for p in after.values())
    print("PUTBACK", direction, {"steer": steer, "race_start": race_start, "full": player[full].frame, "back": t0, "facing": facing,
                                 "nearest": round(dist, 1), "rise": rise, "warning reads": len(warned)})
    assert abs(facing) <= 0x1000, hex(facing)
    assert dist <= 10.0, dist
    assert rise >= 5, rise


def test_a_set_flag_changes_nothing_on_a_course_without_a_variant(tmp_path, romset_zip, saturn_cue):
    """Phase 26 Task 12: on a course without a reverse record a direction flag set to 1 before the race load is served the
    normal record and written back 0 by the loader: the two 45-second drives (the game's own inputs, no autopilot, so they
    are deterministic) give the same (x, z, quad) probe stream, and the byte reads 0 in the RAM dump at frame 2200. Stage 2
    Task 6: Bay Bridge (entry 1, an original), since stage 2 gave stage 1's Diablo Canyon (entry 5) its variant. Stage 3: the
    flag is held at 1 on the select screen by direction.lua (mode 0x10's state 0 clears a flag poked before the coin)."""
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.mame.runner import parse_collision

    out, conv = _seven(romset_zip, saturn_cue)
    assert out is not None and decode_directory(out)[BAY_BRIDGE].reverse is None
    dump = {"VR_TRACE_DUMP": "2200", "VR_TRACE_FROM": "0", "VR_TRACE_TO": "0"}
    streams = {}
    for label in ("plain", "flag"):
        base = tmp_path / label
        wd = base / f"entry{BAY_BRIDGE}"
        _drive_entry(base, out, romset_zip, BAY_BRIDGE, None, seconds=45, autopilot=False, reverse=label == "flag",
                     extra_env={"VR_TRACE_LOG": str(wd / "trace.log"), **dump})
        streams[label] = [(s.x, s.z, s.quad) for s in parse_collision(wd / "c.txt")]
        ram = (wd / "trace.log.ram.2200.bin").read_bytes()
        assert ram[DIRECTION_RAM - 0x500000] == 0, label
    assert len(streams["plain"]) > 300 and streams["flag"] == streams["plain"]


# --- Phase 26 stage 2 Task 5 (plan D6): the Big Forest template's start in both directions ------------------------------------
# Mode 0x11 sets the crew-start bit (0xfe41d6) through `startbit`, only with the direction flag 0: Big Forest and normal Alpine
# keep the crew ("PIT START") start, reverse Alpine starts on the grid as the six other courses (stage 2 recon §3). Each run:
# 45 s with the game's own inputs (no autopilot: the wheel centred and the gas floored from the load, so a run is
# deterministic), start_log.lua's per-frame log from the course load (frames counted from the first mode-0x11 frame) and the
# read taps on the wrong-way warning. The recon's frames, on out/p26play1 without the autopilot: the load at 1600, mode 0x14 at
# 1864 with the standing start (load + 264), about 1926 with the crew start (load + 326).
STANDING_GREEN = 264        # the six courses' first mode-0x14 frame after the load (recon: 1864 - 1600), +- START_SLACK
START_SLACK = 4
CREW_WAIT = 300             # the crew start's mode 0x14 comes later than this after the load (recon: 1926 - 1600)
PIT_START = 6               # the player's pit state +0x191 during the crew start


def _start_run(tmp_path, romset_zip, rs, entry, reverse, label):
    """(load frame, player S samples, opponents' O samples, frames of wrong-way warning reads from the load on) of 45 s of
    `entry` on the set `rs`, reverse when `reverse` (`_drive_entry`: through the COURSE DIRECTION screen on an entry with a
    variant, else the flag held at 1 on the select screen by direction.lua)."""
    from vrtools.arcade.trace import parse_trace
    from vrtools.mame.runner import parse_start_log
    base = tmp_path / label
    wd = base / f"entry{entry}"
    _drive_entry(base, rs, romset_zip, entry, None, seconds=45, autopilot=False, reverse=reverse,
                 extra_env={"VR_START_LOG": str(wd / "start.txt"), "VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_READ": WARNING_READS,
                            "VR_TRACE_FROM": "0", "VR_TRACE_FINE": "1"})
    load, player, cars = parse_start_log(wd / "start.txt")
    assert load is not None and len(player) > 900, (label, load, len(player))
    warned = sorted({e.frame for e in parse_trace(wd / "trace.log") if e.kind == "R" and e.frame >= load - 1})   # memtrace's f = our f + 1
    return load, player, cars, warned


def _green(player):
    """The player's sample at the first mode-0x14 frame."""
    return next(s for s in player if s.mode == 0x14)


def _stream(player):
    return [(s.frame, s.mode, s.pit, s.x, s.z) for s in player]


def _same_stream(a, b):
    """The two runs' (frame, mode, pit state, x, z) streams agree over the frames both logged (the runs end 45 s after boot)."""
    n = min(len(a), len(b))
    assert n > 900 and _stream(a[:n]) == _stream(b[:n]), next((x, y) for x, y in zip(_stream(a), _stream(b)) if x != y)


def _print_start(label, player, cars):
    """The per-frame numbers round the start, and the opponents at the first mode-0x14 frame, for the report."""
    g = _green(player)
    for s in player:
        if s.frame in (0, 1, 2, 3, 4, 5, 10) or g.frame - 3 <= s.frame <= g.frame + 3 or (s.frame % 50 == 0 and s.frame <= g.frame + 100):
            print("START", label, tuple(s))
    placed = next(s.frame for s in player if s.mode == 0x12) + 4               # the field is placed by then (recon: mode 0x12 from load + 4)
    at = {c.car: c for c in cars if c.frame == g.frame}
    early = {c.car: c for c in cars if c.frame == placed}
    moved = {car: round(math.hypot(at[car].x - early[car].x, at[car].z - early[car].z), 2) for car in at if car in early}
    print("FIELD", label, "at green", g.frame, [(car, c.road_point, c.lap) for car, c in sorted(at.items())],
          "at", placed, [(car, c.road_point, c.lap) for car, c in sorted(early.items())], "moved between", moved)


def test_the_flag_leaves_big_forests_pit_start_alone(tmp_path, romset_zip, saturn_cue):
    """The original Big Forest (entry 0, no variant) with the flag held at 1 on the select screen: the loader serves the normal
    record and writes back 0 before 0xfe41d6, so the crew start is taken (pit state 6 during mode 0x12, the green after the
    crew's wait) and the run is the run with the flag 0, frame for frame."""
    out, _ = _seven(romset_zip, saturn_cue)
    runs = {r: _start_run(tmp_path, romset_zip, out, 0, r, f"bigforest_{'flag' if r else 'plain'}") for r in (True, False)}
    for r, (load, player, cars, _) in runs.items():
        _print_start(f"bigforest flag={int(r)}", player, cars)
        assert any(s.pit == PIT_START and s.mode == 0x12 for s in player), r
        assert _green(player).frame > CREW_WAIT, (r, _green(player).frame)
    _same_stream(runs[True][1], runs[False][1])


def test_normal_alpine_keeps_its_crew_start(tmp_path, romset_zip, saturn_cue):
    """Alpine (entry 3) with the flag 0 takes the crew start, and the same run on the set built without the variants
    (`reverse=False`: the same boot ROM) gives the same stream."""
    out, _ = _seven(romset_zip, saturn_cue)
    plain = ten_course_set(*_built(romset_zip, saturn_cue), reverse=False)
    runs = {label: _start_run(tmp_path, romset_zip, rs, 3, False, f"alpine_{label}") for label, rs in (("stage2", out), ("noreverse", plain))}
    for label, (load, player, cars, _) in runs.items():
        _print_start(f"alpine normal {label}", player, cars)
        assert any(s.pit == PIT_START for s in player), label
    _same_stream(runs["stage2"][1], runs["noreverse"][1])


def test_reverse_alpine_starts_on_the_grid_facing_the_race(tmp_path, romset_zip, saturn_cue):
    """Alpine (entry 3) with the flag 1: no crew start (pit state 6 never seen), the green at the six courses' frame after the
    load, and at the first mode-0x14 frame the player stands on the variant's road point 0 with the lap byte reverse Metropolis
    (entry 6, the control run of this test) has at its first mode-0x14 frame, facing the quads' turned direction (yaw within
    0x400 of the attribute), and the wrong-way warning is read on no frame from the load on. The boot ROM's site calls
    `startbit` in the stage 2 set."""
    from vrtools.arcade.direction import START_BIT_PATTERN, START_BIT_SITE
    from vrtools.arcade.v60asm import asm
    out, _ = _seven(romset_zip, saturn_cue)
    jsr = asm("jsr abs", directory_layout()["startbit"])
    assert out.boot[START_BIT_SITE - 0xFC0000:][:len(START_BIT_PATTERN)] == jsr + asm("nop") * (len(START_BIT_PATTERN) - len(jsr))
    load, player, cars, warned = _start_run(tmp_path, romset_zip, out, 3, True, "alpine_reverse")
    _, metro, metro_cars, _ = _start_run(tmp_path, romset_zip, out, METROPOLIS, True, "metropolis_reverse")
    _print_start("alpine reverse", player, cars)
    _print_start("metropolis reverse", metro, metro_cars)
    g, m = _green(player), _green(metro)
    print("GREEN alpine", tuple(g), "metropolis", tuple(m), "warning read frames", warned[:8])
    assert g.flag == 1 and m.flag == 1                                          # the variants were served
    assert not [s.frame for s in player if s.pit == PIT_START], [s.frame for s in player if s.pit == PIT_START][:8]
    assert abs(g.frame - STANDING_GREEN) <= START_SLACK, g.frame
    assert g.road_point == 0 and g.lap == m.lap, (g, m)
    assert abs(_angle(g.yaw - g.attr)) < 0x400, (hex(g.yaw & 0xFFFF), hex(g.attr))
    assert not warned, warned[:8]


# --- Phase 26 stage 2 (plan D7, Task 13): the Acropolis template's start figures mirrored in reverse ------------------------------
# The race-start task of the Acropolis template (Metropolis, Diablo Canyon) places three animated figures, pool objects 0-2 of
# [0x501350], at world-axis offsets from the player, so in reverse they would stand behind and beside the car (stage 2 recon §3).
# `figures` (end of the placement, 0xfc0ea5) reflects them through the player and turns them half a turn while the flag is set;
# their animation is world-axis too (the root offset, the body's rotations about the horizontal axes, the walk-off heading), and
# Pascal rejected the half turn without it (Task 10: up to 24.6 units off the normal places in the car's frame: "they have to be
# around the car"). Task 13 mirrors those uses (direction.FIGURE_SITES). Each run: 60 s with the game's own inputs (no autopilot,
# so it is deterministic) and figures_log.lua's per-frame log from the course load.
DIABLO = 5
ACROPOLIS = 2               # the original: no variant


def _figures_run(tmp_path, romset_zip, rs, entry, reverse, label):
    """(load, player P samples, figures G samples) of 60 s of `entry` on the set `rs`, the flag held at 1 on the select screen
    when `reverse` (`_drive_entry`: through the COURSE DIRECTION screen on an entry with a variant, else direction.lua)."""
    from vrtools.mame.runner import parse_figures_log
    base = tmp_path / label
    wd = base / f"entry{entry}"
    _drive_entry(base, rs, romset_zip, entry, None, seconds=60, autopilot=False, reverse=reverse,
                 extra_env={"VR_FIGURES_LOG": str(wd / "g.txt")})
    load, player, figures = parse_figures_log(wd / "g.txt")
    assert load is not None and len(player) > 1500, (label, load, len(player))
    return load, player, figures


def _placed(figures):
    """{figure: the frames it is live (bit 31) with its own character record}."""
    return {i: [g.frame for g in figures if g.figure == i and g.flags >> 31 and g.record == FIGURE_RECORDS[i]] for i in range(3)}


FIGURE_PLACE_TOL = 0.01    # units: the reflection is two TGP float adds per axis; the log prints 4 decimals
FIGURE_GATE = 0.5           # units, per axis in the car's frame: plan D7's gate for a figure's drawn position, reverse against normal
                            # (forward and right, from x and z; height, y, is neither gated nor measured: a figure follows the ground
                            # at its mirrored spot)
FIGURE_SPAN_SLACK = 6       # frames between the directions' last live frames. Measured (Task 13): +4 on Metropolis (452 / 456), +6 on
                            # Diablo Canyon (448 / 454). Not the figures' code: a figure is ended (0xff5cef) two frames after its cell
                            # (+0x34, 101 / 100, the start's, the same in both directions, never updated) leaves the visible-cell set
                            # 0x501ac0, which happens later in reverse as the car drives off along the other road. By then every
                            # figure has been out of view for over 100 frames (contact sheets: none in view from race start + 340).


def _car_frame(pose):
    """(forward, right) of a world point in the car's frame at `pose` (yaw 0 faces +z; forward = (−sin, cos))."""
    th = pose.yaw * 2 * math.pi / 65536
    return lambda x, z: ((x - pose.x) * -math.sin(th) + (z - pose.z) * math.cos(th), (x - pose.x) * math.cos(th) + (z - pose.z) * math.sin(th))


def test_the_start_figures_are_mirrored_in_reverse(tmp_path, romset_zip, saturn_cue):
    """Metropolis (entry 6) and Diablo Canyon (entry 5), normal and reverse: the three figures are placed in both directions on
    the same frame after the load; at that frame the player stands on the same spot, half a turn round (the variant was
    served), and each reverse figure stands at its normal place reflected through the player, its heading `+0x2c` the normal
    one + 0x8000. Plan D7's gate: on every frame both runs show a figure live (the animation and the walk-off), its drawn position
    in the car's frame at placement is within FIGURE_GATE of the normal run's on both axes. The drawn position is the stored one
    plus the root offset as the draw pushes it: + root in normal, − root (x, z) in reverse, where `figrootx` / `figrootz` negate
    it (the log reads the stored root). Each figure's last live frame differs between the directions by at most
    FIGURE_SPAN_SLACK. The boot ROM's placement end jumps to `figures` in the stage 2 set."""
    from vrtools.arcade.direction import FIGURES_PATTERN, FIGURES_SPAN
    from vrtools.arcade.v60asm import asm
    out, _ = _seven(romset_zip, saturn_cue)
    jmp = asm("jmp abs", directory_layout()["figures"])
    assert out.boot[FIGURES_SPAN - 0xFC0000:][:len(FIGURES_PATTERN)] == jmp + asm("nop") * (len(FIGURES_PATTERN) - len(jmp))
    for entry in (METROPOLIS, DIABLO):
        runs = {r: _figures_run(tmp_path, romset_zip, out, entry, r, f"entry{entry}_{'reverse' if r else 'normal'}") for r in (False, True)}
        live = {r: {i: {g.frame: g for g in figures if g.figure == i and g.flags >> 31 and g.record == FIGURE_RECORDS[i]} for i in range(3)}
                for r, (_, _, figures) in runs.items()}
        print("FIGURES", entry, {r: {i: (min(f), max(f), len(f)) if f else None for i, f in p.items()} for r, p in live.items()})
        assert all(live[r][i] for r in (False, True) for i in range(3)), (entry, {r: {i: len(f) for i, f in p.items()} for r, p in live.items()})
        first = {r: min(min(f) for f in p.values()) for r, p in live.items()}
        assert first[True] == first[False] and all(min(live[r][i]) == first[r] for r in (False, True) for i in range(3)), (entry, first)
        f0 = first[False]
        pose = {r: next(p for p in player if p.frame == f0) for r, (_, player, _) in runs.items()}
        assert math.hypot(pose[True].x - pose[False].x, pose[True].z - pose[False].z) <= FIGURE_PLACE_TOL, (entry, pose)
        assert abs(_angle(pose[True].yaw - pose[False].yaw - 0x8000)) < 0x400, (entry, pose)
        px, pz = pose[False].x, pose[False].z
        frame = {r: _car_frame(pose[r]) for r in (False, True)}
        sign = {False: 1, True: -1}
        gate = {}
        for i in range(3):
            a, b = live[False][i][f0], live[True][i][f0]
            print("FIGURE", entry, i, "first frame", f0, "normal", (a.x, a.z, hex(a.heading)), "reverse", (b.x, b.z, hex(b.heading)),
                  "normal reflected", (round(2 * px - a.x, 4), round(2 * pz - a.z, 4)))
            assert b.heading == (a.heading + 0x8000) & 0xFFFF, (entry, i, hex(a.heading), hex(b.heading))
            assert abs(b.x - (2 * px - a.x)) <= FIGURE_PLACE_TOL and abs(b.z - (2 * pz - a.z)) <= FIGURE_PLACE_TOL, (entry, i, a, b, (px, pz))
            drawn = {r: {f: frame[r](g.x + sign[r] * g.root_x, g.z + sign[r] * g.root_z) for f, g in live[r][i].items()} for r in (False, True)}
            both = sorted(set(drawn[False]) & set(drawn[True]))
            d = [(f, abs(drawn[False][f][0] - drawn[True][f][0]), abs(drawn[False][f][1] - drawn[True][f][1])) for f in both]
            gate[i] = {"dF": round(max(t[1] for t in d), 3), "dR": round(max(t[2] for t in d), 3), "worst frame": max(d, key=lambda t: max(t[1:]))[0],
                       "frames": (both[0], both[-1]), "last live": (max(live[False][i]), max(live[True][i]))}
        print("GATE", entry, gate)
        assert all(g["dF"] <= FIGURE_GATE and g["dR"] <= FIGURE_GATE for g in gate.values()), (entry, gate)
        assert all(abs(g["last live"][1] - g["last live"][0]) <= FIGURE_SPAN_SLACK for g in gate.values()), (entry, gate)


def test_the_flag_leaves_acropolis_figures_alone(tmp_path, romset_zip, saturn_cue):
    """The original Acropolis (entry 2, no variant) with the flag held at 1 on the select screen: the loader serves the normal
    record and writes back 0 before the race-start task runs, so the three figures are placed and their stream (flags, record,
    position, animation offset, headings) and the player's are the flag-0 run's, frame for frame. Task 8 (the Task 7 review: the
    test could pass with a flag that never reached the byte): the byte read 1 on the select screen's last frame in the flag run
    and 0 in the plain run, and 0 in both from the figures' first frame on (the loader's write-back)."""
    out, _ = _seven(romset_zip, saturn_cue)
    runs = {r: _figures_run(tmp_path, romset_zip, out, ACROPOLIS, r, f"acropolis_{'flag' if r else 'plain'}") for r in (True, False)}
    for r, (load, player, figures) in runs.items():
        placed = _placed(figures)
        assert all(placed[i] for i in range(3)), (r, placed)
        first = min(f[0] for f in placed.values())
        print("FLAG acropolis", "flag" if r else "plain", "select", load.flag, "first placed", first,
              "flag 1 on frames", [p.frame for p in player if p.flag][:8])
        assert load.flag == int(r), (r, load)
        assert not [p.frame for p in player if p.frame >= first and p.flag], r
    for k, what in ((2, "figures"), (1, "player")):           # the runs end 60 s after boot: compare the frames both logged
        a, b = runs[True][k], runs[False][k]
        if what == "player":                                    # the flag column differs until the write-back: compared above
            a, b = [p[:4] for p in a], [p[:4] for p in b]
        n = min(len(a), len(b))
        assert n > 1500 and a[:n] == b[:n], (what, next((x, y) for x, y in zip(a, b) if x != y))


# --- Phase 26 stage 2 Task 8 (recon §1's pin): who reads the annex --------------------------------------------------------------
# The annex (load records, maps records and race blobs of the seven variants) lies in the colour-table run's tail, which the boot's
# colour-table upload (PC 0xfe6b64: 128 chunks of 0x1000 halfwords from 0x200000, the whole program ROM once) reads before frame 268.
# The recon's taps on out/p26play1 found no other reader of the tail (attract 240 s; reverse Metropolis, Big Forest and Surfers Oval
# 330 s each). Each run: 60 s of Surfers Oval (entry 8, a course of bank 1) with the game's own inputs (no autopilot) and
# memtrace.lua's read taps over the annex at exact addresses from frame 0.
COLOUR_UPLOAD = 0xFE6B64
SURFERS_OVAL = 8


def _annex_reads(tmp_path, romset_zip, rs, entry, reverse, label):
    """The R events of the read taps over the annex [lo, hi) in 60 s of `entry`, reverse when `reverse` (`_drive_entry`)."""
    from vrtools.arcade.trace import parse_trace
    lo, hi = _annex(decode_directory(rs))
    base = tmp_path / label
    wd = base / f"entry{entry}"
    _drive_entry(base, rs, romset_zip, entry, None, seconds=60, autopilot=False, reverse=reverse,
                 extra_env={"VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_READ": f"{lo:x}-{hi - 1:x}", "VR_TRACE_FROM": "0",
                            "VR_TRACE_FINE": "1"})
    return [e for e in parse_trace(wd / "trace.log") if e.kind == "R"]


def test_only_the_colour_upload_and_the_served_variant_read_the_annex(tmp_path, romset_zip, saturn_cue):
    """In the normal race every read of the annex comes from the colour-table upload, one per halfword of the span (the positive
    control: the taps see the whole span); in the reverse race the upload reads it the same way, and from the course load on (the
    loader's first read) every other read falls in entry 8's own variant: its load record, its maps record (load + maps_offset())
    and its race blob. The one exception comes before the load: when direction.lua held the flag at 1 on the select screen
    (before stage 3's COURSE DIRECTION screen), `entry` served the highlighted entry's variant on the menu path and `gfx` read
    that variant's load record as the wheel passed over it (measured 12 Nov: PC 0x279a82 reading bytes +4..+7, the header word,
    of Diablo Canyon's and Metropolis's on the way to entry 8, frames 618-739, the load at 1603): only those four bytes of a
    variant's load record are allowed, from `gfx`, before the load (the screen leaves the flag 0 until its lock)."""
    from vrtools.arcade.directory import LOAD_SIZE, maps_offset
    out, _ = _seven(romset_zip, saturn_cue)
    d = decode_directory(out)
    lay = directory_layout()
    lo, hi = _annex(d)
    rv = d[SURFERS_OVAL].reverse
    own = ((rv.at, rv.at + LOAD_SIZE), (rv.at + maps_offset(), rv.at + maps_offset() + LOAD_SIZE), (rv.entry.race, rv.entry.race + RACE_BLOB_BYTES))
    headers = [(e.reverse.at + 4, e.reverse.at + 8) for e in d[3:10]]                 # each variant's header word (load record +4)
    for reverse in (False, True):
        reads = _annex_reads(tmp_path, romset_zip, out, SURFERS_OVAL, reverse, "reverse" if reverse else "normal")
        upload = [e for e in reads if e.pc == COLOUR_UPLOAD]
        other = [e for e in reads if e.pc != COLOUR_UPLOAD]
        print("ANNEX", "reverse" if reverse else "normal", f"span {lo:#x}..{hi:#x}", "upload reads", sum(e.count for e in upload),
              "halfwords", len({e.addr for e in upload}), "frames", (min(e.frame for e in upload), max(e.frame for e in upload)) if upload else None,
              "other readers", {hex(pc): (sum(e.count for e in other if e.pc == pc), hex(min(e.addr for e in other if e.pc == pc)),
                                          hex(max(e.addr for e in other if e.pc == pc))) for pc in sorted({e.pc for e in other})})
        assert sum(e.count for e in upload) == (hi - lo) // 2 and len({e.addr for e in upload}) == (hi - lo) // 2, reverse
        if not reverse:
            assert not other, sorted({(hex(e.pc), hex(e.addr)) for e in other})[:8]
        else:
            loads = [e.frame for e in other if lay["loader"] <= e.pc < lay["bank"]]       # the loader reads the served record
            assert loads, "the loader never read the annex: the variant was not served"
            load = min(loads)
            after, before = [e for e in other if e.frame >= load], [e for e in other if e.frame < load]
            print("ANNEX reverse load at", load, "select-screen reads per variant header word",
                  {hex(s): sum(e.count for e in before if s <= e.addr < t) for s, t in headers})
            assert after                                                        # the variant was served: its records are read
            stray = [e for e in other if not any(s <= e.addr < t for s, t in own)
                     and not (e.frame < load and lay["gfx"] <= e.pc < lay["mapobj"] and any(s <= e.addr < t for s, t in headers))]
            assert not stray, sorted({(e.frame, hex(e.pc), hex(e.addr)) for e in stray})[:8]
