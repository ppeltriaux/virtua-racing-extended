import struct

import pytest

from vrtools.arcade.polyrom import PolyError, Record, decode_object, quads

N = (0.0, 1.0, 0.0)
S0, S1 = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)
A, B, C, D = (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 0.0, 2.0), (1.0, 0.0, 2.0)
Z = (9.0, 9.0, 9.0)


def strip(*recs, seeds=(S0, S1)) -> bytes:
    out = b"".join(struct.pack("<3f", *p) for p in seeds)
    for flags, n, p0, p1 in recs:
        out += struct.pack("<I", flags) + struct.pack("<9f", *n, *p0, *p1)
    return out


def test_records_and_word_count():
    obj = decode_object(strip((0x201, N, A, B), (0x201, N, C, D), (0x000, N, Z, Z)), 0)
    assert obj.seed0 == S0 and obj.seed1 == S1
    assert len(obj.records) == 2
    assert obj.records[0] == Record(0x201, N, A, B)
    assert obj.word_count == 6 + 3 * 10


def test_two_quads_link2():
    obj = decode_object(strip((0x201, N, A, B), (0x201, N, C, D), (0x000, N, Z, Z)), 0)
    q = quads(obj)
    assert [x.p for x in q] == [(S1, S0, A, B), (B, A, C, D)]
    assert q[0].normal == N and q[0].flags == 0x201


def test_link0_emits_nothing_but_shifts_both():
    obj = decode_object(strip((0x001, N, A, B), (0x201, N, C, D), (0x000, N, Z, Z)), 0)
    assert [x.p for x in quads(obj)] == [(B, A, C, D)]


def test_link1_updates_only_old_p1_with_p0():
    obj = decode_object(strip((0x101, N, A, B), (0x201, N, C, D), (0x000, N, Z, Z)), 0)
    assert [x.p for x in quads(obj)] == [(S1, S0, A, B), (A, S0, C, D)]


def test_link3_updates_only_old_p0_with_p1():
    obj = decode_object(strip((0x301, N, A, B), (0x201, N, C, D), (0x000, N, Z, Z)), 0)
    assert [x.p for x in quads(obj)] == [(S1, S0, A, B), (S1, B, C, D)]


def test_type2_point_copies_p0():
    obj = decode_object(strip((0x202, N, A, Z), (0x000, N, Z, Z)), 0)
    assert quads(obj)[0].p == (S1, S0, A, A)


def test_tex_advance_increments_before_emit():
    obj = decode_object(strip((0x201, N, A, B), (0x1201, N, C, D), (0x000, N, Z, Z)), 0)
    assert [x.tex_adr for x in quads(obj, 5)] == [5, 6]


def test_size_limits_records():
    obj = decode_object(strip((0x201, N, A, B), (0x201, N, C, D), (0x201, N, A, B)), 0, size=2)
    assert len(obj.records) == 2


def test_unlimited_size_stops_at_end_marker():
    data = strip((0x201, N, A, B), (0x000, N, Z, Z), (0x201, N, C, D))
    assert len(decode_object(data, 0, size=0).records) == 1


def test_runs_off_end_raises():
    data = strip((0x201, N, A, B), (0x201, N, C, D))
    with pytest.raises(PolyError):
        decode_object(data, len(data) // 4 - 3)


def test_max_records_guard_raises():
    data = strip(*([(0x201, N, A, B)] * 5))
    with pytest.raises(PolyError):
        decode_object(data, 0, max_records=3)


def test_poly_adr_is_word_index():
    data = b"\xee" * 8 + strip((0x201, N, A, B), (0x000, N, Z, Z))
    assert decode_object(data, 2).seed0 == S0


def test_record_flag_properties():
    r = Record(0x1 | (3 << 8) | (2 << 10) | 0x1000 | 0x2000 | 0x4000 | (9 << 17) | 0x400000, N, A, B)
    assert (r.type, r.link, r.zmode) == (1, 3, 2)
    assert r.tex_advance and r.moire and r.no_cull
    assert r.light_mode == 0x89
