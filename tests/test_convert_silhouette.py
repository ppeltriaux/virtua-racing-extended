"""Phase 31 (prototype): a far landmark's silhouette copied into nearer cells (convert/silhouette.py) and the replacement cell
objects installed after everything else (arcade/farcopy.py). Synthetic data only: no ROM, no Saturn disc."""

import struct

import pytest

from vrtools.arcade.course import tile_table_at
from vrtools.arcade.patch import PatchError, patch_course_tiles, write_tile_table
from vrtools.arcade.polyrom import decode_object, quads as poly_quads
from vrtools.arcade.romset import V60_PROGRAM, RomSet
from vrtools.convert.geometry import ConvertError, WorldQuad
from vrtools.convert.silhouette import FarCopy, far_copy_cells, silhouette_quads

GREY, RED, GREEN = (96, 96, 96), (240, 0, 0), (0, 240, 0)


def wall(x, z, base, top, rgb=GREY, width=20.0):
    return WorldQuad(((x, base, z), (x + width, base, z), (x + width, top, z), (x, top, z)), rgb)


def flat(x, z, y, rgb=GREEN, size=20.0):
    return WorldQuad(((x, y, z), (x + size, y, z), (x + size, y, z + size), (x, y, z + size)), rgb)


def test_the_silhouette_is_the_upright_faces_that_reach_the_height():
    """A face belongs to the silhouette when its highest corner is at or above `min_top` and it rises at least `min_rise`: the
    tall walls, not the ground, a low wall, or a roof (flat, however high)."""
    tower, low, roof, ground = wall(0, 0, 0, 90), wall(30, 0, 0, 20), flat(0, 0, 90), flat(0, 0, 0)
    upper = wall(60, 0, 50, 90)                                      # an upper storey: reaches the height, rises 40
    quads = [ground, tower, low, roof, upper]
    assert silhouette_quads(quads, min_top=60.0, min_rise=10.0) == [tower, upper]
    assert silhouette_quads(quads, min_top=60.0, min_rise=50.0) == [tower]
    assert silhouette_quads(quads, min_top=10.0, min_rise=10.0) == [tower, low, upper]
    assert silhouette_quads(quads, min_top=60.0, min_rise=0.0) == [tower, roof, upper]      # no rise asked: the roof too
    assert silhouette_quads(quads, min_top=200.0, min_rise=10.0) == []


def test_a_box_keeps_the_silhouette_to_one_structure():
    """`within` (x0, z0, x1, z1): only the faces with every corner inside the box (its edges included), so that one structure
    is taken from a cell that holds several; a face that straddles the box's edge is not part of it."""
    tower, other, straddling = wall(0, 0, 0, 90), wall(60, 0, 0, 90), wall(15, 5, 0, 90)
    quads = [tower, other, straddling]
    assert silhouette_quads(quads, 60.0, 10.0, within=(0.0, -1.0, 20.0, 1.0)) == [tower]
    assert silhouette_quads(quads, 60.0, 10.0, within=(0.0, -1.0, 80.0, 10.0)) == quads
    cells = {5: quads, 4: []}
    out, _ = far_copy_cells(cells, (FarCopy(5, (4,), 60.0, 10.0, within=(50.0, -1.0, 90.0, 1.0)),))
    assert out[4] == [other]


def test_a_far_copy_adds_the_exact_faces_to_the_nearer_cells_only():
    """The nearer cells get their own quads followed by the source's silhouette faces, the very same quads (points, colour,
    sidedness); only the named cells are returned, and the cells given are not changed."""
    lettering = WorldQuad(wall(40, 0, 0, 80, RED).p, RED, one_sided=True)
    cells = {5: [flat(0, 0, 0), wall(0, 0, 0, 80), lettering], 3: [flat(-300, 0, 0)], 4: [flat(-150, 0, 0), wall(-150, 0, 0, 12)],
             9: [flat(500, 0, 0)]}
    before = {c: list(q) for c, q in cells.items()}
    out, report = far_copy_cells(cells, (FarCopy(source=5, into=(3, 4), min_top=60.0, min_rise=10.0),))
    assert set(out) == {3, 4}
    assert out[3] == cells[3] + [cells[5][1], lettering] and out[4] == cells[4] + [cells[5][1], lettering]
    assert out[3][-1].one_sided and out[3][-2] is cells[5][1]
    assert cells == before
    assert report == {3: {"own": 1, "copied": 2, "from": [5]}, 4: {"own": 2, "copied": 2, "from": [5]}}


def test_no_far_copy_is_no_change():
    assert far_copy_cells({5: [wall(0, 0, 0, 80)]}, ()) == ({}, {})


def test_two_landmarks_into_one_cell_and_a_cell_with_no_object_of_its_own():
    """Copies from two sources add up in a shared nearer cell (a silhouette binned across a cell border); a nearer cell with
    nothing of its own gets an object of the copies alone; a copy never takes another copy along."""
    cells = {5: [wall(0, 0, 0, 80)], 6: [wall(130, 0, 0, 90, RED)], 4: [flat(-150, 0, 0)]}
    out, report = far_copy_cells(cells, (FarCopy(5, (4, 2), 60.0, 10.0), FarCopy(6, (4, 5), 60.0, 10.0)))
    assert out[4] == cells[4] + cells[5] + cells[6]
    assert out[2] == cells[5]
    assert out[5] == cells[5] + cells[6]                              # cell 5's own wall, and cell 6's; not 5's copy of anything
    assert report[4] == {"own": 1, "copied": 2, "from": [5, 6]} and report[2] == {"own": 0, "copied": 1, "from": [5]}


@pytest.mark.parametrize("copy,message", [
    (FarCopy(5, (5,), 60.0, 10.0), "into itself"),
    (FarCopy(7, (4,), 60.0, 10.0), "no scenery"),
    (FarCopy(5, (4,), 500.0, 10.0), "no face"),
    (FarCopy(5, (300,), 60.0, 10.0), "not a cell"),
    (FarCopy(5, (4, 4), 60.0, 10.0), "twice"),
    (FarCopy(5, (), 60.0, 10.0), "no cell"),
])
def test_a_far_copy_that_cannot_be_made_is_an_error(copy, message):
    cells = {5: [flat(0, 0, 0), wall(0, 0, 0, 80)], 4: [flat(-150, 0, 0)]}
    with pytest.raises(ConvertError, match=message):
        far_copy_cells(cells, (copy,))


# ---- the installation, on a synthetic ROM image ----

TABLE = 0x280000                                    # a tile table in erased program ROM
PALETTE_AT = 0xEC980                                # colours.PALETTE_ROM
COLOUR_REGION = (0x290000, 0x290040)                # the block reserved for the copies' colour entries (32 entries)


def _rom():
    """An erased program and polygon ROM with a three-colour palette and one course's cells behind TABLE: cell 5 a tower on its
    ground, cell 4 ground, cell 9 ground; built as the converter does (convert_tiles' steps on given quads)."""
    from vrtools.arcade.colours import TABLE_BASE, palette_from_rom
    from vrtools.arcade.polyrom import encode_object
    from vrtools.convert.geometry import assign_colours
    prog = bytearray(b"\xff" * 0x100000)
    struct.pack_into("<3H", prog, PALETTE_AT, 0x8000 | (12 << 10) | (12 << 5) | 12, 0x801F, 0x83E0)   # grey, red, green
    struct.pack_into("<1021H", prog, PALETTE_AT + 6, *([0] * 1021))
    rs = RomSet(bytes(prog), b"", b"", b"\xff" * 0x1000000, b"", b"")
    write_tile_table(rs, TABLE)
    pal = palette_from_rom(rs, 0)
    cells = {5: [flat(0, 0, 0), wall(0, 0, 0, 80), wall(20, 0, 0, 80, RED)], 4: [flat(-150, 0, 0)], 9: [flat(500, 0, 0)]}
    tex, objects, words = TABLE_BASE + 0x1000, {}, {}
    for cell, cq in sorted(cells.items()):
        coloured, w = assign_colours(cq, pal, tex_start=tex)
        blob, layout = encode_object(coloured, tex_start=tex, no_cull=True)
        objects[cell] = (blob, layout, tex)
        words.update(w)
        tex += len(w)
    return patch_course_tiles(rs, 0, objects, words, tile_table=TABLE), cells


def _cell_quads(rs, cell):
    t = tile_table_at(rs, TABLE)[cell]
    from vrtools.arcade.colours import colour_table
    table = colour_table(rs)
    return sorted((tuple(sorted(q.p)), table.entry(q.tex_adr)) for q in poly_quads(decode_object(rs.polygons, t.poly_adr, t.size), t.tex_adr))


def test_installing_the_copies_repoints_only_the_named_cells_and_writes_on_erased_rom_only():
    """`install_far_copies` writes each named cell a new object (its own quads and the copies, each with the colour it had) on
    erased polygon ROM, the colour entries it needs on erased program ROM inside the region given, and the cell's tile record;
    every other byte of the set is as it was: the old objects (the source's too), the other cells' records, the old colour
    entries."""
    from vrtools.arcade.farcopy import install_far_copies
    rs, cells = _rom()
    far, _ = far_copy_cells(cells, (FarCopy(5, (4,), 60.0, 10.0),))
    out, report = install_far_copies(rs, TABLE, 0, far, COLOUR_REGION)
    assert _cell_quads(out, 4) == sorted(_cell_quads(rs, 4) + [q for q in _cell_quads(rs, 5) if q[0][-1][1] == 80])
    assert len(_cell_quads(out, 4)) == 3 and {w for _, w in _cell_quads(out, 4)} == {0, 1, 2}        # grey, red and green entries
    assert _cell_quads(out, 5) == _cell_quads(rs, 5) and _cell_quads(out, 9) == _cell_quads(rs, 9)
    old, new = tile_table_at(rs, TABLE), tile_table_at(out, TABLE)
    assert [c for c in range(256) if old[c] != new[c]] == [4]
    # every byte that changed was erased before: polygon ROM, and program ROM outside the one tile record
    rec = struct.unpack_from("<I", rs.program, TABLE - V60_PROGRAM + 4 * 4)[0] - V60_PROGRAM
    poly_changed = [i for i in range(0, len(rs.polygons), 4) if rs.polygons[i:i + 4] != out.polygons[i:i + 4]]
    assert poly_changed and all(rs.polygons[i:i + 4] == b"\xff" * 4 for i in poly_changed)
    prog_changed = [i for i in range(len(rs.program)) if rs.program[i] != out.program[i]]
    colours = [i for i in prog_changed if not (rec <= i < rec + 16)]
    assert colours and all(rs.program[i] == 0xFF for i in colours)
    lo, hi = COLOUR_REGION[0] - V60_PROGRAM, COLOUR_REGION[1] - V60_PROGRAM
    assert all(lo <= i < lo + 6 for i in colours)                                    # the block's first three entries
    assert (out.boot, out.data, out.copro_data, out.tgp_program) == (rs.boot, rs.data, rs.copro_data, rs.tgp_program)
    assert report["cells"] == {4: {"records": new[4].size, "records_before": old[4].size, "bytes": 40 * (new[4].size + 1) + 24,
                                   "colour_entries": 3}}
    assert report["polygon_bytes"] == len(poly_changed) * 4 and report["colour_entries"] == 3
    assert report["colour_first"] == new[4].tex_adr and report["added_records"] == new[4].size - old[4].size


def test_installing_nothing_changes_nothing():
    from vrtools.arcade.farcopy import install_far_copies
    rs, _ = _rom()
    out, report = install_far_copies(rs, TABLE, 0, {}, COLOUR_REGION)
    assert (out.program, out.polygons) == (rs.program, rs.polygons) and report["cells"] == {}


def test_the_colour_entries_go_in_the_reserved_block_after_the_entries_already_there():
    """The colour entries are never placed by searching the ROM for erased bytes: they go in the block the caller reserves, right
    after the last entry already written in it (a second course's copies follow the first's). A block without room, or one
    that is not wholly inside erased-or-entry words (odd bounds), is a PatchError and nothing is written."""
    from vrtools.arcade.farcopy import colour_run, install_far_copies
    from vrtools.arcade.colours import TABLE_BASE
    rs, cells = _rom()
    far, _ = far_copy_cells(cells, (FarCopy(5, (4,), 60.0, 10.0),))
    first = TABLE_BASE + (COLOUR_REGION[0] - V60_PROGRAM) // 2
    assert colour_run(rs, COLOUR_REGION, 3) == first
    out, report = install_far_copies(rs, TABLE, 0, far, COLOUR_REGION)
    assert report["colour_first"] == first and colour_run(out, COLOUR_REGION, 3) == first + 3
    again, report2 = install_far_copies(out, TABLE, 0, far_copy_cells(cells, (FarCopy(5, (9,), 60.0, 10.0),))[0], COLOUR_REGION)
    assert report2["colour_first"] == first + 3
    # a stray byte in the block's tail counts as an entry in use: the room after it is what is left
    prog = bytearray(rs.program)
    prog[COLOUR_REGION[1] - V60_PROGRAM - 4] = 0
    used = RomSet(bytes(prog), rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    assert colour_run(used, COLOUR_REGION, 1) == first + 31
    with pytest.raises(PatchError, match="colour block .* room for 1 "):
        install_far_copies(used, TABLE, 0, far, COLOUR_REGION)
    with pytest.raises(PatchError, match="colour block .* room for 32 "):
        colour_run(rs, COLOUR_REGION, 33)
    with pytest.raises(PatchError, match="misaligned"):
        colour_run(rs, (COLOUR_REGION[0] + 1, COLOUR_REGION[1]), 1)
    # 0xff bytes elsewhere in the program ROM are never taken: a long erased run just below the block is left alone
    assert set(out.program[COLOUR_REGION[0] - V60_PROGRAM - 0x800:COLOUR_REGION[0] - V60_PROGRAM]) == {0xFF}


def test_an_object_over_the_record_cap_or_without_polygon_room_is_a_patch_error():
    """M4: the installed object must fit the record cap (PatchError naming the cell, from the encoder's own error only), and the
    polygon ROM must have the room."""
    from vrtools.arcade.farcopy import install_far_copies
    rs, cells = _rom()
    far, _ = far_copy_cells(cells, (FarCopy(5, (4,), 60.0, 10.0),))
    with pytest.raises(PatchError, match="far copies, cell 4: .* records exceed the 3 cap"):
        install_far_copies(rs, TABLE, 0, far, COLOUR_REGION, max_records=3)
    full = RomSet(rs.program, rs.boot, rs.data, bytes(len(rs.polygons)), rs.copro_data, rs.tgp_program)
    with pytest.raises(PatchError, match="no free range"):
        install_far_copies(full, TABLE, 0, far, COLOUR_REGION)


def test_install_far_keeps_the_polygon_floor_and_uses_the_reserved_block():
    """`tencourse.install_far`: the entries land in `far_colour_block()` (the 256 bytes below the start gantry's block, left out
    of the select pictures' search and of the annex's regions, overlapping no other reserved block), and a set whose polygon
    ROM would fall under the floor is refused. (Phase 33 stacked its two blocks right below it, so the annex's first region now
    ends at those, not at it: what is checked is that no first-fit writer and no other reserved block can reach it.)"""
    from types import SimpleNamespace as NS
    from vrtools.arcade.patch import POLY_HOLES
    from vrtools.arcade.tencourse import (FAR_COLOUR_BYTES, POLY_FLOOR_BYTES, annex_regions, check_reserved_blocks,
                                          far_colour_block, install_far, picture_exclusions, reserved_blocks, start_gantry_address)
    lo, hi = far_colour_block()
    assert hi == start_gantry_address() and hi - lo == FAR_COLOUR_BYTES == 256 and lo % 16 == 0
    assert (lo, hi - lo) in picture_exclusions()                                    # the pictures' search leaves it out
    assert not any(a < hi and lo < a + n for a, n in picture_exclusions() if (a, n) != (lo, hi - lo))
    assert annex_regions()[0][0] < annex_regions()[0][1] <= lo                    # the annex's code-area region stops below it
    assert not any(s < hi and lo < e for s, e in annex_regions())                 # and no region of the annex reaches it
    blocks = reserved_blocks()
    assert blocks["far copies' colour block"] == (lo, hi)
    check_reserved_blocks()                                                        # no two reserved blocks overlap
    assert not any(s < hi and lo < e for name, (s, e) in blocks.items() if name != "far copies' colour block")
    rs, cells = _rom()
    far, _ = far_copy_cells(cells, (FarCopy(5, (4,), 60.0, 10.0),))
    c = NS(entry=NS(tile_table=TABLE, bank=3, name="SYNTHETIC"), far_cells=far)
    out, report = install_far(rs, c)
    assert report["colour_first"] == 0x40000 + (lo - V60_PROGRAM) // 2
    poly = bytearray(len(rs.polygons))                              # all in use but a window smaller than the floor
    start = POLY_HOLES[0][0]
    poly[start:start + POLY_FLOOR_BYTES - 4096] = b"\xff" * (POLY_FLOOR_BYTES - 4096)
    tight = RomSet(rs.program, rs.boot, rs.data, bytes(poly), rs.copro_data, rs.tgp_program)
    with pytest.raises(PatchError, match="SYNTHETIC: the far copies .* leave less than 65536"):
        install_far(tight, c)


def test_a_capped_cell_takes_no_part_in_a_far_copy():
    """M3: a cell over the record cap is installed as its first split only, so a far copy from it or into it would not be what
    the plan says: ConvertError naming the cell."""
    cells = {5: [flat(0, 0, 0), wall(0, 0, 0, 80)], 4: [flat(-150, 0, 0)]}
    copy = (FarCopy(5, (4,), 60.0, 10.0),)
    assert far_copy_cells(cells, copy, capped={9})[1][4]["copied"] == 1
    for capped in ({5}, {4}):
        with pytest.raises(ConvertError, match=f"cell {min(capped)} is over the record cap"):
            far_copy_cells(cells, copy, capped=capped)


def test_a_far_copy_can_pin_the_number_of_faces_it_selects():
    """M5: a hand-tuned box says how many faces it means (`faces`); any other count is a ConvertError (the Saturn data or the
    binning changed under the box), not a silently different building."""
    cells = {5: [flat(0, 0, 0), wall(0, 0, 0, 80), wall(30, 0, 0, 80)], 4: []}
    out, _ = far_copy_cells(cells, (FarCopy(5, (4,), 60.0, 10.0, faces=2),))
    assert len(out[4]) == 2
    with pytest.raises(ConvertError, match="selects 2 faces, not the 3 "):
        far_copy_cells(cells, (FarCopy(5, (4,), 60.0, 10.0, faces=3),))


def test_the_plans_default_is_no_far_copy():
    """Opt-in per course: a plan carries no far copy unless it names one; the shipped plans name them on one course only (the
    prototype's)."""
    from vrtools.arcade.tencourse import COURSES, CoursePlan
    assert CoursePlan("X/Y", "X", 1, 4, 0, 1).far_copies == ()
    with_copies = [p.name for p in COURSES if p.far_copies]
    assert len(with_copies) <= 1
    assert all(c.faces is not None for p in COURSES for c in p.far_copies)          # every shipped box pins its count
