import struct

import pytest

from vrtools.arcade.bank import BankError, all_lines, build_bank, encode_line, install_bank
from vrtools.arcade.course import (RoadPoint, course_table, decode_course, decode_pointer_block, road_lines, segments,
                                   verify_lossless)
from vrtools.arcade.romset import RomSet
from vrtools.convert.road import RoadTables


def test_rebuilt_big_forest_bank_decodes_and_round_trips(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    c = decode_course(rs, 0)
    tables = RoadTables(all_lines(rs, 0), c.segments)                           # the arcade's own eight lines
    out = install_bank(rs, 0, build_bank(rs, 0, tables, c.collision, c.surface))
    assert verify_lossless(out, 0) == []
    e = course_table(out)[0]
    assert road_lines(out, e) == c.lines and segments(out, e) == c.segments
    assert all_lines(out, 0) == tables.lines
    # everything outside the lines' wrap points is byte-identical (wrap headings are regenerated as heading | flag;
    # the originals' wrap headings differ by a unit here and there)
    first = min(ptr for ptr, _ in c.pointers.lines) - 0x100000
    n = len(c.lines[0]); stride = 16 * (n + 8)
    orig, new = rs.data[e.base:e.base + 0x100000], out.data[e.base:e.base + 0x100000]
    assert orig[:first] == new[:first] and orig[first + 8 * stride:] == new[first + 8 * stride:]
    for k in range(8):
        a = first + k * stride
        assert orig[a:a + 16 * n] == new[a:a + 16 * n]


def test_bank_relocates_longer_lines_and_still_decodes(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    c = decode_course(rs, 0)
    longer = [line + line[:100] for line in all_lines(rs, 0)]                   # 438 points: does not fit in place
    out = install_bank(rs, 0, build_bank(rs, 0, RoadTables(longer, c.segments), c.collision, c.surface))
    e = course_table(out)[0]
    assert road_lines(out, e) == longer and all_lines(out, 0) == longer and segments(out, e) == c.segments
    assert verify_lossless(out, 0) == []


def test_bank_rejects_tables_that_do_not_fit(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    c = decode_course(rs, 0)
    with pytest.raises(BankError):
        build_bank(rs, 0, RoadTables([c.lines[0] * 40] * 8, c.segments), c.collision, c.surface)
    lines8 = all_lines(rs, 0)
    with pytest.raises(BankError):
        build_bank(rs, 0, RoadTables(lines8, c.segments * 3), c.collision, c.surface)   # more segments than the array holds
    with pytest.raises(BankError):
        build_bank(rs, 0, RoadTables(lines8, c.segments), c.collision, bytes(5000))     # surface table longer than the template's
    with pytest.raises(BankError):
        build_bank(rs, 0, RoadTables(c.lines[:5], c.segments), c.collision, c.surface)  # five lines are not enough


def _hi(word):
    return ((word >> 16) ^ 0x8000) - 0x8000


def _line(headings):
    return [RoadPoint(float(k), 0.0, ((h & 0xFFFF) << 16) | 7, 0) for k, h in enumerate(headings)]


def test_encode_line_wrap_points_continue_the_heading_by_the_lap_turn():
    """A line's wrap points repeat points 0..7 as the lap continues: heading + the net turn of the lap
    (one turn either way, or none), low half kept."""
    for headings, turn in ((list(range(0, -16001, -400)), -16384),        # clockwise: 0 → −16000, as the arcade's
                           (list(range(0, 16001, 400)), 16384),           # counter-clockwise
                           ([0, 3000, 6000, 3000, 0, -3000, -6000, -3000, 0], 0)):   # no net turn
        blob = encode_line(_line(headings))
        n = len(headings)
        for w in range(8):
            p = RoadPoint(*struct.unpack_from("<2f2I", blob, 16 * (n + w)))
            assert _hi(p.heading) == headings[w] + turn and p.heading & 0xFFFF == 7 and (p.x, p.z) == (float(w), 0.0)


def test_encode_line_reproduces_the_arcades_wrap_points(romset_zip):
    """The originals' wrap headings are heading − one turn within a rounding unit (their low halves, positions and
    links identical) on every line of Big Forest and Acropolis and the five addressed lines of Bay Bridge (its
    unaddressed lines 6–7 are shifted by two points in the ROM itself)."""
    rs = RomSet.from_zip(romset_zip)
    for course, lines in ((0, range(8)), (2, range(8)), (1, range(6))):
        e = course_table(rs)[course]
        first = min(ptr for ptr, _ in decode_pointer_block(rs, e).lines) - 0x100000
        for k, line in enumerate(all_lines(rs, course)):
            if k not in lines:
                continue
            n = len(line); stride = 16 * (n + 8)
            mine = encode_line(line); orig = rs.data[e.base + first + k * stride:e.base + first + (k + 1) * stride]
            assert mine[:16 * n] == orig[:16 * n]
            for w in range(8):
                a = RoadPoint(*struct.unpack_from("<2f2I", mine, 16 * (n + w)))
                b = RoadPoint(*struct.unpack_from("<2f2I", orig, 16 * (n + w)))
                assert (a.x, a.z, a.link, a.heading & 0xFFFF) == (b.x, b.z, b.link, b.heading & 0xFFFF), (course, k, w)
                assert _hi(b.heading) - _hi(a.heading) in (0, 1), (course, k, w)
