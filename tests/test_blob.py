"""Relocatable course blobs placed in a bank's free space."""
import struct

import pytest

from vrtools.arcade.bank import BankError, RoadPoint, all_lines
from vrtools.arcade.blob import build_course_blob, build_variant_blob, free_runs, place_blob
from vrtools.arcade.course import Segment, collision_map, course_entry_at, decode_course, decode_pointer_block, road_lines, segments, surface_table
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet
from vrtools.convert.road import RoadTables


def test_blob_decodes_like_a_bank_at_any_window_base(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    c = decode_course(rs, 0)
    tables = RoadTables(all_lines(rs, 0), c.segments)
    out, base = place_blob(rs, 3, lambda b: build_course_blob(rs, 0, tables, c.collision, c.surface, b))
    assert base % 16 == 0 and 0x100000 + 0x2B390 <= base < 0x200000                   # first fit in Big Forest's bank's free run
    e = course_entry_at(out, 3, base)
    assert e.header.gfx_dir == course_entry_at(out, 3, 0x100000).header.gfx_dir     # the host bank's graphics directory
    assert road_lines(out, e) == c.lines and segments(out, e) == c.segments
    assert collision_map(out, e) == c.collision and surface_table(out, e) == c.surface
    assert out.data[0x300000:0x300000 + 0x2B390] == rs.data[0x300000:0x300000 + 0x2B390]    # the host's own tables untouched
    assert out.program == rs.program and out.boot == rs.boot


def test_place_blob_refuses_overflow_and_never_overlaps(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    runs = free_runs(rs, 3)
    assert runs and runs[0][1] >= 500 * 1024 and all(n >= 0x8000 for _, n in runs)
    with pytest.raises(PatchError):
        place_blob(rs, 3, lambda b: b"\x00" * (800 * 1024))
    out, base = place_blob(rs, 3, lambda b: b"\x01" * 0x40000)
    out2, base2 = place_blob(out, 3, lambda b: b"\x02" * 0x40000)
    assert base2 >= base + 0x40000 and out2.data[0x300000 + base - 0x100000] == 1 and out2.data[0x300000 + base2 - 0x100000] == 2
    with pytest.raises(PatchError):
        place_blob(rs, 4, lambda b: b"\x00")


def test_pointer_block_addresses_all_eight_lines(romset_zip):
    """Phase 9 review of the field: the car setup (0xfe8ac1) reads car i's line pointer at pointer block + 8 × line
    for lines 0..7, and the originals carry eight (ptr, count) pairs there; a blob with five pairs put line 0's first
    points where pairs 5–7 belong, so the seven cars on lines 5–7 spawned at the world origin."""
    import struct
    from vrtools.arcade.course import COURSE_BANK, course_entry_at, decode_pointer_block, road_lines
    rs = RomSet.from_zip(romset_zip)
    for course, bank in COURSE_BANK.items():
        e = course_entry_at(rs, bank)
        pb = decode_pointer_block(rs, e)
        assert len(pb.lines) == 8 and len(road_lines(rs, e)) == 8, course
        stride = 16 * (pb.lines[0][1] + 8)
        assert all(pb.lines[k][0] - pb.lines[0][0] in (stride * k, stride * k - 32) for k in range(8)), course   # BB line 6 has two points fewer
    c = decode_course(rs, 0)
    tables = RoadTables(all_lines(rs, 0), c.segments)
    blob = build_course_blob(rs, 0, tables, c.collision, c.surface, 0x140000)
    ptr_block = struct.unpack_from("<I", blob, 0x10)[0] - 0x140000 - 8          # header+0x10 -> pointer block + 8
    pairs = [struct.unpack_from("<2I", blob, ptr_block + 8 + 8 * k) for k in range(8)]
    n = len(tables.lines[0])
    assert all(c == n for _, c in pairs) and all(pairs[k][0] - pairs[0][0] == 16 * (n + 8) * k for k in range(8))
    assert pairs[0][0] - 0x140000 >= ptr_block + 8 + 64                        # line 0 starts after the eighth pair


def test_a_variant_blob_shares_the_courses_collision_and_backdrop(romset_zip):
    """Phase 26 (plan D3): a reverse variant's blob holds only its header, segment array, pointer block and eight lines;
    its pointer block names the normal course's collision map and surface table, its header word 0 the backdrop directory.
    Big Forest's own tables as a variant in its bank read back through the new header as the course's."""
    rs = RomSet.from_zip(romset_zip)
    c = decode_course(rs, 0)
    host = course_entry_at(rs, 3)
    pb = decode_pointer_block(rs, host)
    tables = RoadTables(all_lines(rs, 0), c.segments)
    out, base = place_blob(rs, 3, lambda b: build_variant_blob(tables, b, host.header.gfx_dir, pb.collision, pb.surface))
    e = course_entry_at(out, 3, base)
    assert base != 0x100000 and e.header.gfx_dir == host.header.gfx_dir
    assert road_lines(out, e) == c.lines and segments(out, e) == c.segments
    assert collision_map(out, e) == c.collision and surface_table(out, e) == c.surface
    vpb = decode_pointer_block(out, e)
    assert (vpb.collision, vpb.surface) == (pb.collision, pb.surface)                  # the original's addresses, not copies
    assert len(build_variant_blob(tables, base, host.header.gfx_dir, pb.collision, pb.surface)) < 60_000


# Phase 26 stage 2 (plan D2): a variant blob stores each distinct line once behind its eight pointer pairs.
_BASE, _GFX, _COL, _SUR = 0x140000, 0x100200, 0x150000, 0x158000
_N = 20


def _tables():
    """Eight different lines of _N points each, and three segments."""
    lines = [[RoadPoint(float(100 * k + i), float(i), (i * 64) << 16 | k, i) for i in range(_N)] for k in range(8)]
    return RoadTables(lines, [Segment(i, i, 1) for i in range(3)])


def _line_pointers(blob, base):
    """The eight (pointer, count) pairs of the blob's pointer block (header word 2 is the block's window address)."""
    import struct
    ptr_block = struct.unpack_from("<I", blob, 0x8)[0] - base
    return [struct.unpack_from("<2I", blob, ptr_block + 8 + 8 * k) for k in range(8)]


def _line_at(blob, base, ptr_count):
    ptr, count = ptr_count
    return blob[ptr - base:ptr - base + 16 * (count + 8)]


def test_a_variant_blob_stores_each_distinct_line_once():
    tables = _tables()
    full = build_variant_blob(tables, _BASE, _GFX, _COL, _SUR)
    three = build_variant_blob(tables, _BASE, _GFX, _COL, _SUR, pairs=(0, 7, 7, 5, 5, 5, 5, 7))
    assert len(full) - len(three) == 5 * 16 * (_N + 8)                      # one line = 16 x (n + 8) bytes (recon §2)
    ptrs = _line_pointers(three, _BASE)
    assert len({p for p, _ in ptrs}) == 3
    assert [ptrs[k][0] for k in (1, 2, 7)] == [ptrs[1][0]] * 3 and [ptrs[k][0] for k in (3, 4, 5, 6)] == [ptrs[3][0]] * 4
    full_ptrs = _line_pointers(full, _BASE)
    assert _line_at(three, _BASE, ptrs[0]) == _line_at(full, _BASE, full_ptrs[0])
    assert _line_at(three, _BASE, ptrs[1]) == _line_at(full, _BASE, full_ptrs[7])                # pair 1 reads line 7's points
    assert _line_at(three, _BASE, ptrs[3]) == _line_at(full, _BASE, full_ptrs[5])
    assert struct.unpack_from("<I", three, 0x14)[0] == ptrs[0][0] and ptrs[0][0] < ptrs[1][0] < ptrs[3][0]   # stored in order of first use


def test_the_default_pairs_give_the_stage_1_blob():
    assert build_variant_blob(_tables(), _BASE, _GFX, _COL, _SUR, pairs=(0, 1, 2, 3, 4, 5, 6, 7)) == build_variant_blob(_tables(), _BASE, _GFX, _COL, _SUR)


@pytest.mark.parametrize("pairs", [(1, 1, 2, 3, 4, 5, 6, 7), (0, 1, 2), (0, 1, 2, 3, 4, 5, 6, 8)])
def test_bad_pairs_are_refused(pairs):
    with pytest.raises(BankError):
        build_variant_blob(_tables(), _BASE, _GFX, _COL, _SUR, pairs=pairs)
