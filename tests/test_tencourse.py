"""Phase 8 (M5): the seven Saturn courses in their banks and TGP slots, budget-checked."""
import math

import pytest

from vrtools.arcade.patch import COPRO_FREE, COPRO_ZERO_GAPS, PatchError
from vrtools.arcade.romset import RomSet
from vrtools.arcade.tencourse import COURSES, OFF_COURSE_LIMIT, CoursePlan, build_all, tgp_budget
from vrtools.arcade.tgp import slot_table
from tests.test_convert_collision import _saturn_course


def replace_copro_free(rs: RomSet, words: int) -> RomSet:
    """A RomSet whose free TGP area keeps only `words` free words: the rest of every free run is filled with a
    marker word, so the allocator sees less space."""
    copro = bytearray(rs.copro_data)
    left = words
    for start, count in COPRO_ZERO_GAPS + COPRO_FREE:
        keep = min(left, count)
        left -= keep
        for w in range(start + keep, start + count):
            copro[4 * w:4 * w + 4] = b"\x11\x22\x33\x44"
    return RomSet(rs.program, rs.boot, rs.data, rs.polygons, bytes(copro), rs.tgp_program)


def test_course_plan_table_is_consistent():
    assert [p.tgp_slot for p in COURSES] == list(range(3, 10)) and len({p.name for p in COURSES}) == 7
    assert all(p.template == {1: 0, 2: 1, 3: 2}[p.bank] for p in COURSES)
    assert all(0 <= p.label <= 2 and 0.5 <= p.min_coverage <= 1.0 for p in COURSES)
    assert next(p for p in COURSES if "SPEEDWAY" in p.path).min_coverage == 0.8
    assert all(p.min_coverage == 0.98 for p in COURSES if "SPEEDWAY" not in p.path)
    assert isinstance(COURSES[0], CoursePlan) and COURSES[0].thin == 0.0


def test_tgp_budget_counts_the_free_words(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    full = tgp_budget(rs)
    assert full == sum(n for _, n in COPRO_ZERO_GAPS + COPRO_FREE)      # the 0xff tail plus the zero gaps
    assert tgp_budget(replace_copro_free(rs, 0x8000)) == 0x8000


SATURN_GATES = {"ALPINE": (65, 192, 333), "AMAZON FALLS": (0, 117, 237), "DIABLO CANYON": (179, 289, 421),   # 22h: Diablo's pit list (its lap
                "METROPOLIS": (0, 126, 222), "PACIFIC COAST": (40, 186, 320), "SURFERS OVAL": (127, 299, 382),      # start at the mouth) moved its
                "SURFERS ROAD": (127, 299, 436)}   # points by 4-5; Phase 22l: Amazon and Metropolis start at their START gate, the Oval and Road 50-60 units after it


def _expected_checkpoints(c) -> tuple[int, ...]:
    """The converted course's checkpoints: its Saturn gates (Phase 22e), less those the start rule drops (Phase 22i/22l)."""
    from vrtools.convert.race import gate_checkpoints
    return gate_checkpoints(list(SATURN_GATES[c.entry.name]), len(c.centreline))


def test_build_all_fits_the_budgets(romset_zip, saturn_cue):
    rs = RomSet.from_zip(romset_zip)
    before = tgp_budget(rs)
    out, conv = build_all(rs, saturn_cue)
    assert [c.entry.name for c in conv] == [p.name for p in COURSES]
    assert [c.entry.tgp_slot for c in conv] == list(range(3, 10))
    assert 0 <= tgp_budget(out) < before
    assert tgp_budget(out) >= 9_500                                      # Phase 22l: the flag starts' split before the line (9 621 left at p22play90 with the apron's slices split too — to the road alone the Oval's field stalled); Phase 22k (Pascal): walls following the drawn faces, BARRIER_CHORD_TOL 2.0 (11 185 left at p22play80; 10 725 at p22play85 with the wall_min floor of the run's line); Phase 22j: 12 000 (15 681 left at p22play61); Phase 19 review: 30 000 -> 25 000 (Pascal), Phase 22: 17 500
    assert slot_table(out)[:3] == slot_table(rs)[:3]                      # the originals' slots untouched
    bases = sorted((c.entry.bank, c.entry.header_base) for c in conv)
    for (b1, h1), (b2, h2) in zip(bases, bases[1:]):
        assert b1 != b2 or h2 - h1 >= 0x10000                             # two blobs in a bank never overlap (blobs are >= 64 KB)
    assert all(c.report["capped_cells"] == 0 for c in conv)
    # Phase 22o: one START arch — the host's start gantry only where the Saturn's gate is not at the line
    assert {c.entry.name: c.report["start_gantry"] for c in conv} == {"ALPINE": True, "AMAZON FALLS": False, "DIABLO CANYON": True,
                                                                        "METROPOLIS": False, "PACIFIC COAST": True, "SURFERS OVAL": False, "SURFERS ROAD": False}
    assert all(c.report["grid_boards"] is False for c in conv)             # Phase 22q: no host grid boards (the country flags' row)
    shifted = {c.entry.name for c in conv if c.entry.map_tx != 149.0}  # Phase 14: the anticlockwise courses shift the HUD map
    assert shifted == {"ALPINE", "PACIFIC COAST"}
    assert all((c.entry.map_tx, c.entry.map_cross) == (237.0, 22) for c in conv if c.entry.name in shifted)
    assert all((c.entry.map_tx, c.entry.map_cross) == (149.0, 0) for c in conv if c.entry.name not in shifted)
    assert all(c.entry.off_course == OFF_COURSE_LIMIT for c in conv)
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, grid_pose
    for c in conv:                                                        # the car spawns on the converted road
        if c.entry.name == "DIABLO CANYON":                               # Phase 22f: it spawns in its pit lane (22n: 40 units in), beside
            continue                                                      # the lap's road (the pit-lane placement)
        course = COURSE_OF_TEMPLATE[c.entry.template]
        point = GRID_OF_COURSE[course][0]
        px, pz, _, _ = grid_pose(rs, course)
        cl = c.centreline
        near = min(range(len(cl)), key=lambda i: math.dist(cl[i], (px, pz)))
        assert math.dist(cl[near], (px, pz)) < 5.0, (c.entry.name, cl[near], (px, pz))        # the road passes under the car
        assert abs(((near - point) + len(cl) // 2) % len(cl) - len(cl) // 2) <= 2, (c.entry.name, near, point)   # at its spawn point (±1 slice)
    oval = next(c for c in conv if c.entry.name == "SURFERS OVAL")
    usable = sum(1 for s in _saturn_course(saturn_cue, "SPEEDWAY/TRCKSPEE").segments if s.corners() is not None)
    assert len(oval.lap.order) < 0.9 * usable                             # the unused infield is left out
    import struct
    from vrtools.arcade.race import RACE_BLOB_BYTES, decode_race_blob, race_blob_layout
    from vrtools.arcade.tencourse import race_blob_address, tile_table_address
    for k, c in enumerate(conv):                                          # every course races on its own blob
        assert c.entry.race == race_blob_address(k) and c.entry.laps == 5
        lay = race_blob_layout(c.entry.race)
        ptrs = struct.unpack_from("<12I", out.program, c.entry.race - 0x200000)
        assert all(lay["records"] <= p < lay["checkpoints"] for p in ptrs)
        blob = decode_race_blob(out, c.entry.race)
        assert all(abs(a - b) <= 2 for a, b in zip(blob.checkpoints, _expected_checkpoints(c))) and len(blob.checkpoints) == len(_expected_checkpoints(c)), (c.entry.name, blob.checkpoints)
        assert blob.times[(0, 0)].initial == 2080
        assert len(blob.cars) == 16 and blob.cars[0].perf == pytest.approx(2.847, abs=0.001)
    assert race_blob_address(0) >= tile_table_address(7) and race_blob_address(1) - race_blob_address(0) == RACE_BLOB_BYTES
    from vrtools.arcade.spawn import GRID_BOARDS, KEEP_HANDLERS, MINIMAP, decode_spawn_list, road_relative
    from vrtools.arcade.tencourse import spawn_list_address
    for k, c in enumerate(conv):                                          # the host's props are gone, its furniture re-placed
        assert c.entry.spawn_table == spawn_list_address(k)
        ents = decode_spawn_list(out, c.entry.spawn_table)
        assert ents and {e.handler for e in ents} <= KEEP_HANDLERS
        cps = _expected_checkpoints(c)
        placed_at = {}
        for e in ents:
            if e.handler == MINIMAP:
                continue
            rp, lat, _ = road_relative(e, c.centreline)
            placed_at.setdefault(e.handler, []).append(rp)
            if abs(lat) < 13 and e.handler != GRID_BOARDS:                  # on the tarmac: only at the start line or a checkpoint
                assert min(abs(((rp - p) + len(c.centreline) // 2) % len(c.centreline) - len(c.centreline) // 2) for p in cps) <= 6, (c.entry.name, e)
        gantries = sorted(rp for h, rps in placed_at.items() if h not in (GRID_BOARDS,) and h != 0xFFB07F for rp in rps)
        assert all(abs(a - b) <= 3 for a, b in zip(gantries, cps[1:])), (c.entry.name, gantries, cps)
    assert spawn_list_address(0) >= race_blob_address(7)


def test_build_all_names_the_course_that_does_not_fit(romset_zip, saturn_cue):
    rs = RomSet.from_zip(romset_zip)
    small = replace_copro_free(rs, words=0x4000)                 # Alpine needs about 0x4800 words (929 quads and their lists)
    with pytest.raises(PatchError, match="ALPINE"):
        build_all(small, saturn_cue, plans=COURSES[:1])


def test_build_all_keeps_every_list_and_quad_inside_a_tgp_window(romset_zip, saturn_cue):
    """The TGP reads ROM through a 32K-word window: it sets the window base from a list's or a quad's address and
    walks on with a 15-bit index, so a list (count + entries) or a 16-word quad that straddles a multiple of
    0x8000 words continues from I/O address 0, not from ROM. The originals never straddle."""
    from vrtools.arcade import tgp
    rs = RomSet.from_zip(romset_zip)
    out, conv = build_all(rs, saturn_cue)
    words = tgp.words(out)
    for c in conv:
        block, pool = slot_table(out)[c.entry.tgp_slot]
        assert pool % tgp.QUAD_WORDS == 0, (c.entry.name, hex(pool))                  # a quad never crosses 0x8000
        # walk the lists as the TGP does: every referenced offset's count + entries inside one window
        offs = sorted({w for w in _list_offsets(out, c) if w})
        for off in offs:
            at = block + off
            count = words[at]
            assert (at // 0x8000) == ((at + count) // 0x8000), (c.entry.name, hex(at), count)


def _list_offsets(rs, c):
    """The list offsets a converted course's collision map carries (its blob's 128x128 halfword map)."""
    from vrtools.arcade.course import collision_map, course_entry_at
    e = course_entry_at(rs, c.entry.bank, c.entry.header_base)
    return collision_map(rs, e)


def test_interior_on_the_left_from_the_signed_area(romset_zip):
    """The HUD map is car-centred and heading-up: a course whose interior lies on the car's left (anticlockwise) hangs
    its outline to the left of the cross, into the middle of the screen (Phase 14). The sign of the centreline's
    shoelace area over (x, z) tells the side; the three originals are clockwise (recon: -505k, -449k, -656k)."""
    from vrtools.arcade.course import course_table, road_centreline, road_lines
    from vrtools.arcade.tencourse import interior_on_the_left
    square_ccw = [(0, 0), (10, 0), (10, 10), (0, 10)]          # heading +x first, turning towards +z: the interior on the left
    assert interior_on_the_left(square_ccw) and not interior_on_the_left(square_ccw[::-1])
    rs = RomSet.from_zip(romset_zip)
    for e in course_table(rs):
        assert not interior_on_the_left(road_centreline(road_lines(rs, e)))


def test_the_ten_course_set_keeps_polygon_rom_free(romset_zip, saturn_cue):
    """Phase 18: with the Saturn's terrain, road paint and structures on all seven courses the polygon ROM keeps
    POLY_FLOOR_BYTES free; only small distant terrain is thinned, never half of a course's terrain."""
    from vrtools.arcade.tencourse import POLY_FLOOR_BYTES, load_saturn_course, poly_budget, ten_course_set
    from vrtools.convert.geometry import course_quads
    rs = RomSet.from_zip(romset_zip)
    out, conv = build_all(rs, saturn_cue)
    out = ten_course_set(out, conv)
    assert poly_budget(out) >= POLY_FLOOR_BYTES
    for plan, c in zip(COURSES, conv):
        sat = load_saturn_course(saturn_cue, plan.path)
        terrain = len(course_quads(sat, (1,)))
        assert c.report["terrain_thinned"] < 0.5 * terrain, (plan.name, c.report["terrain_thinned"], terrain)
        if plan.terrain_thin == 0 and plan.thin == 0:                    # nothing thinned: every polygon of every layer is drawn
            assert c.report["quads"] == sum(len(course_quads(sat, (g,))) for g in range(5)), plan.name   # (review: no verge holes)


def test_every_course_has_its_own_backdrop(romset_zip, saturn_cue):
    """Phase 18b: each converted course's graphics-upload directory carries its own panorama (the converted Saturn
    backdrop), the host bank's other tile uploads kept; the three originals' backdrops are untouched; each bank keeps
    room."""
    import hashlib
    from vrtools.arcade.backdrop import read_panorama
    from vrtools.arcade.blob import free_runs
    from vrtools.arcade.course import course_entry_at
    from vrtools.arcade.tencourse import ten_course_set
    from vrtools.convert.backdrop import TOP_CODE
    rs = RomSet.from_zip(romset_zip)
    out, conv = build_all(rs, saturn_cue)
    out = ten_course_set(out, conv)
    for bank in (1, 2, 3):
        a, b = read_panorama(rs, course_entry_at(rs, bank)), read_panorama(out, course_entry_at(out, bank))
        assert a.tiles == b.tiles and a.palettes == b.palettes and (a.map == b.map).all() and a.uploads == b.uploads, bank
        assert sum(n for _, n in free_runs(out, bank)) >= 16 * 1024, bank
    for c in conv:
        host = read_panorama(rs, course_entry_at(rs, c.entry.bank))
        p = read_panorama(out, course_entry_at(out, c.entry.bank, c.entry.header_base))
        rep = c.report["backdrop"]
        assert hashlib.sha1(p.map.tobytes()).hexdigest() == rep["map_sha1"] and p.map.shape == (24, 256), c.entry.name
        assert TOP_CODE in p.tiles and len(p.palettes) == rep["palettes"] == 32 and rep["mean_error"] < 14, (c.entry.name, rep)
        assert p.map[0, 0] == TOP_CODE and all(c2 < 0x4000 for c2 in p.tiles), c.entry.name   # review: one code range, 32 palettes


def render_record(read, r):
    """A picture record rendered to RGB (168 x 128) from the ROM, as the select routines would draw it."""
    import struct
    import numpy as np
    from vrtools.arcade.panel import char_pixels
    n = [r.counts & 0xFF, r.counts >> 8 & 0xFF, r.counts >> 16 & 0xFF]
    data = read(r.chars_addr, 32 * sum(n))
    chars = {}
    for p in range(3):
        for k in range(n[p]):
            o = 32 * (sum(n[:p]) + k)
            chars[128 * p + k] = data[o:o + 32]
    pal = struct.unpack("<48H", read(r.normal_addr, 96)); m = struct.unpack("<336H", read(r.map_addr, 672))
    img = np.zeros((168, 128, 3), int)
    for i, local in enumerate(m):
        px = char_pixels(chars[local])
        for y in range(8):
            for x in range(8):
                w = pal[16 * (local >> 7) + px[y][x]]
                img[(i // 16) * 8 + y, (i % 16) * 8 + x] = ((w & 31) * 8, (w >> 5 & 31) * 8, (w >> 10 & 31) * 8)
    return img


def _records(out):
    import struct
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.picture import PictureRecord
    lay = directory_layout()
    table = struct.unpack_from("<10I", out.program, lay["pictures"] - 0x200000)
    def read(a, n):
        if a >= 0xFC0000:                                         # the originals' START sets live in the boot ROM
            return out.boot[a - 0xFC0000:a - 0xFC0000 + n]
        return out.data[a - 0x100000:a - 0x100000 + n] if a < 0x200000 else out.program[a - 0x200000:a - 0x200000 + n]
    return table, [PictureRecord(*struct.unpack("<9I", read(a, 36))) for a in table], read


def test_every_entry_has_a_picture_record(romset_zip, saturn_cue):
    """Phase 21: ten picture records; the originals' point at their own select-list characters (311 / 258 / 288 in
    three runs) and the START tables; the converted ones hold at most PICTURE_CHARS characters; every blob lies in
    bank 0 or the program ROM without overlapping another, and no record targets blocks or palettes 0-95."""
    from vrtools.arcade.panel import select_uploads
    from vrtools.arcade.picture import PICTURE_CHARS
    from vrtools.arcade.select import CHAR_RAM, SLOT_CHAR
    from vrtools.arcade.tencourse import ten_course_set
    rs = RomSet.from_zip(romset_zip)
    out, conv = build_all(rs, saturn_cue)
    out = ten_course_set(out, conv)
    table, recs, read = _records(out)
    n = lambda r: (r.counts & 0xFF) + (r.counts >> 8 & 0xFF) + (r.counts >> 16 & 0xFF)
    srcs = {d: s for s, d, _ in select_uploads(out)}
    for art, want in enumerate((311, 258, 288)):
        r = recs[art]
        assert n(r) == want and r.chars_addr == srcs[CHAR_RAM + 32 * SLOT_CHAR[art]] + 4
        assert r.a_dst == (0x900C00, 0x900C40, 0x900C80)[art] and r.chosen_addr >= 0xFC0000 and r.grey_addr >= 0xFC0000
    spans = []
    for r in recs[3:]:
        assert 0 < n(r) <= PICTURE_CHARS and r.a_dst == 0
        spans.append((r.chars_addr, r.map_addr + 672))
    spans.sort()
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    assert all(0x100000 <= a < 0x300000 for a, _ in spans)


def test_stand_in_entries_show_their_course_picture(romset_zip, saturn_cue):
    """Phase 21: a set with Alpine alone repeats it under the other Saturn names; their pictures are Alpine's, lettered
    with their own names: rendered back, the stand-ins match Alpine's entry above the name (rows 0-139: mean difference
    under 9 levels: two quantisations, each 3-8 off the source) and differ in the name's rows (over 12)."""
    import numpy as np
    from vrtools.arcade.tencourse import ten_course_set
    rs = RomSet.from_zip(romset_zip)
    out, conv = build_all(rs, saturn_cue, plans=[COURSES[0]])
    out = ten_course_set(out, conv)
    _, recs, read = _records(out)
    render = lambda r: render_record(read, r)
    first = render(recs[3])
    for r in recs[4:]:
        other = render(r)
        assert np.abs(other[:140] - first[:140]).mean() < 9.0
        assert np.abs(other[148:164] - first[148:164]).mean() > 12.0


def test_every_saturn_course_has_three_gates_on_its_lap(saturn_cue, romset_zip):
    """Phase 22e recon (docs/follow-ups.md): each Saturn course draws a START/GOAL gate and two C.P. gates as props
    spanning the road; on the converted laps (Pascal's choice A) they are the checkpoints."""
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.gates import saturn_gates
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    rs = RomSet.from_zip(romset_zip)
    want = SATURN_GATES
    for plan in COURSES:
        sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
        pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage,
                              flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
            got = saturn_gates(sat, centreline(lap))
        assert len(got) == 3 and all(abs(a - b) <= 2 for a, b in zip(got, want[plan.name])), (plan.name, got)


def test_the_lap_starts_at_the_saturns_flag_where_it_fits(saturn_cue):
    """Phase 22l (Pascal: "let's do the flag start"): a course whose plan names `flag_start` has its lap start that
    many centreline points after the Saturn's START gate (0: at it) — Amazon Falls and Metropolis at the flag (map
    extents 737 and 714 of 970), the Surfers Oval and Surfers Road 60 units after it (992 at the flag, 935 and 944
    there); Alpine (1202) and Pacific Coast (1139) cannot, Diablo starts by its flag through its pit-lane placement."""
    import os
    from pathlib import Path
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.gates import start_gate_point
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    rs = RomSet.from_zip(Path(os.environ["VR_ROMDIR"]) / "vr.zip")
    flagged = {p.name: p.flag_start for p in COURSES if p.flag_start is not None}
    assert flagged == {"AMAZON FALLS": 0, "METROPOLIS": 0, "SURFERS OVAL": 5, "SURFERS ROAD": 6}
    for plan in COURSES:
        if plan.flag_start is None:
            continue
        sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
        pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage,
                              flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
            cl = centreline(lap)
            k = start_gate_point(sat, cl)
        n = len(cl)
        assert k is not None and (n - k) % n <= plan.flag_start + 1 and (n - k) % n >= max(0, plan.flag_start - 1), (plan.name, k, n)
