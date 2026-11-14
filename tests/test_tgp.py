import struct

import pytest

from vrtools.arcade.course import collision_map, course_table
from vrtools.arcade.romset import RomSet
from vrtools.arcade.tgp import (Collision, Quad16, TgpError, decode_collision, decode_quad, encode_lists, encode_quad,
                                slot_table, verify_lossless)


def _q(corners, attr=0):
    cx = sum(c[0] for c in corners) / 4; cy = sum(c[1] for c in corners) / 4; cz = sum(c[2] for c in corners) / 4
    return Quad16(tuple(corners), (cx, cy, cz), attr)


def test_slot_table_and_constants(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    t = slot_table(rs)
    assert t[2] == (0x10000, 0x3C170) and t[0] == (0x30, 0x12E00) and t[1] == (0x8000, 0x28A90)
    assert t[3:] == [(0x30, 0x12E00)] * 13


def test_quad_round_trip_and_zero_area():
    q = Quad16(((0, 1, 0), (4, 1, 0), (4, 1, 3), (0, 1, 3)), (2, 1, 1.5), 0xFFFF8702)
    assert decode_quad(struct.unpack("<16I", encode_quad(q)), 0) == q
    with pytest.raises(TgpError):
        encode_quad(Quad16(((0, 1, 0), (4, 1, 0), (8, 1, 0), (2, 1, 0)), (3.5, 1, 0), 0))


def test_encode_lists_rejects_bad_offsets_and_dangling():
    with pytest.raises(TgpError):
        encode_lists({0: [1], 3: [0]})            # second list must start at offset 2
    with pytest.raises(TgpError):
        Collision({0: [5]}, [_q(((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)))]).check()
    with pytest.raises(TgpError):
        Collision({0: [0]}, [_q(((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)))] * 2).check()   # quad 1 unreferenced
    assert encode_lists({0: [1], 2: [0, 1]}) == struct.pack("<5I", 1, 1, 2, 0, 1)


@pytest.mark.parametrize("course", [0, 1, 2])
def test_real_course_is_lossless(romset_zip, course):
    rs = RomSet.from_zip(romset_zip)
    c = decode_collision(rs, course)
    assert len(c.quads) == {0: 3840, 1: 5577, 2: 4974}[course]
    assert verify_lossless(rs, course) == []


def test_real_quads_sit_in_their_cells(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    c = decode_collision(rs, 0)
    cm = collision_map(rs, course_table(rs)[0])
    inside = total = 0
    for cell, v in enumerate(cm):
        if not v or cell % 7:
            continue
        x0, z0 = 16 * (cell % 128) - 1024, 16 * (cell // 128) - 1024
        for i in c.lists[v]:
            cx, _, cz = c.quads[i].centre
            total += 1
            inside += (x0 - 24 <= cx <= x0 + 40 and z0 - 24 <= cz <= z0 + 40)
    assert inside / total > 0.99


def test_words_follow_the_romset_not_a_recycled_id():
    """A second RomSet with different copro bytes must never read the first one's words (id reuse)."""
    from tests.test_patch import _copro_romset
    seen = []
    for v in (0x111, 0x222, 0x333):
        rs = _copro_romset()
        data = bytearray(rs.copro_data)
        struct.pack_into("<I", data, 4 * 0x13, v)
        rs = RomSet(rs.program, rs.boot, rs.data, rs.polygons, bytes(data), rs.tgp_program)
        seen.append(slot_table(rs)[3][0])
        del rs, data
    assert seen == [0x111, 0x222, 0x333]


def test_edge_values_of_two_synthetic_quads():
    """Phase 26 (Task 9): the six results of TGP command 0x1500 on synthetic quads, corners front-left, front-right, back-right,
    back-left; each value written out by hand from the fitted formulas in return order (+0xf1, +0xed, +0xf5, +0xf9, +0xfd, +0x101).
    First a 20 x 10 rectangle heading +z (attribute 0, so the direction u is +z and the right r is +x). The rectangle cannot tell
    c0 from c1 along u, or c2 from c3, and at attribute 0 the sine is 0. So, second (the whole-branch review), a skewed quad at
    attribute 0x4000 (a quarter turn: u = (-sin a, cos a) = (-1, 0), r = (u.z, -u.x) = (0, 1)) whose corners all differ in x:
    c0 for c1 in +0xf9, c3 for c2 in +0xfd, or +sin a in u would each change a value by 2 or more."""
    from vrtools.arcade.tgp import edge_values
    q = _q(((100, 0, 60), (120, 0, 60), (120, 0, 50), (100, 0, 50)), attr=0)
    for (x, z), want in (((105, 55), (-5, 15, -5, 5, -5, 0)),        # (c0-p).r, (c1-p).r, -mean, (c1-p).u, (c2-p).u, -mean
                         ((110, 58), (-10, 10, 0, 2, -8, 3)),
                         ((118, 51), (-18, 2, 8, 9, -1, -4))):
        assert edge_values(q, x, z) == pytest.approx(want, abs=1e-9), (x, z)
    q = _q(((10, 0, 20), (12, 0, 30), (40, 0, 32), (36, 0, 18)), attr=0x4000)    # c0, c1 at the front (small x), c2, c3 behind
    for (x, z), want in (((25, 24), (-4, 6, -1, 13, -15, 1)),         # r.(c0-p) = 20-24, 30-24; u.(c1-p) = -(12-25), -(40-25)
                         ((20, 26), (-6, 4, 1, 8, -20, 6))):          # c0 for c1: 15 and 10; c3 for c2: -11 and -16; +sin: -r, -u
        assert edge_values(q, x, z) == pytest.approx(want, abs=1e-9), (x, z)


def test_collision_rejects_a_real_list_at_offset_zero():
    q = _q(((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)))
    with pytest.raises(TgpError, match="offset 0"):
        Collision({0: [0], 2: [0]}, [q]).check()
    Collision({0: [], 1: [0]}, [q]).check()                                 # an empty off-road list is fine
