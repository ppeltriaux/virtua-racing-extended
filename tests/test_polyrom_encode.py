import pytest

from vrtools.arcade.polyrom import ConvertError, ObjectLayout, Quad, decode_object, encode_object, quads, split_quads

N = (0.0, 1.0, 0.0)


def q(x0, z0, tex, size=10.0):
    return Quad(((x0, 0.0, z0), (x0 + size, 0.0, z0), (x0 + size, 0.0, z0 + size), (x0, 0.0, z0 + size)), N, 0x201, tex)


def test_round_trip_geometry_flags_and_tex():
    src = [q(0, 0, 100), q(20, 0, 100), q(40, 0, 101)]
    blob, layout = encode_object(src, tex_start=100)
    assert layout == ObjectLayout(record_count=6, tex_first=100, tex_last=101)
    out = quads(decode_object(blob, 0, 0), tex_adr=100)
    assert [o.p for o in out] == [s.p for s in src]
    assert [o.tex_adr for o in out] == [100, 100, 101]
    assert all(o.normal == N for o in out)


def test_tex_decrease_raises():
    with pytest.raises(ConvertError, match="tex"):
        encode_object([q(0, 0, 5), q(20, 0, 4)], tex_start=5)


def test_tex_start_mismatch_raises():
    with pytest.raises(ConvertError, match="tex"):
        encode_object([q(0, 0, 7)], tex_start=5)


def test_too_many_records_raises_and_split_fits():
    many = [q(20 * i, 0, 100) for i in range(3000)]        # 6000 records (20 apart: no shared edge to chain)
    with pytest.raises(ConvertError, match="5500"):
        encode_object(many, tex_start=100)
    parts = split_quads(many, max_records=5500)
    assert len(parts) == 2 and sum(len(p) for p in parts) == 3000 and len(parts[0]) == 2750
    blob, layout = encode_object(parts[0], tex_start=100)
    assert layout.record_count == 5500


def test_no_cull_flag_and_size():
    blob, layout = encode_object([q(0, 0, 1)], tex_start=1, no_cull=True)
    out = decode_object(blob, 0, 0)
    assert out.records[1].no_cull and not out.records[0].no_cull
    assert len(blob) == 4 * (6 + 10 * 2 + 10)             # seeds + 2 records + end marker


def test_quads_sort_at_their_farthest_depth():
    """Bits 10-11 of a polygon record are its z mode (0 keep the old z, 1 nearest, 2 farthest). The originals' ground
    is mode 2 and the cars mode 1; a mode-0 ground quad under the car kept the previous polygon's depth and hid the
    car for whole stretches (Phase 14 recon)."""
    from vrtools.arcade.polyrom import Z_MODE_MAX
    blob, _ = encode_object([q(0, 0, 5), q(20, 0, 6)], tex_start=5, no_cull=True)
    flags = [r.flags for r in decode_object(blob, 0, 0).records]
    assert Z_MODE_MAX == 0x800
    assert all((f >> 10) & 3 == 2 for f in flags)                                       # every emitted record
    assert flags[0] & ~Z_MODE_MAX == 0x1 and flags[1] & ~Z_MODE_MAX == 0x1 | (2 << 8) | 0x4000   # the other bits are what they were
    assert flags[2] & ~Z_MODE_MAX == 0x1 | 0x1000                                        # tex advance on the second quad's first record


def _canon(p):
    """A polygon's corners rotated so the smallest comes first (cyclic order kept): equal for the same polygon."""
    k = min(range(4), key=lambda i: p[i])
    return tuple(p[k:] + p[:k])


def _decoded(blob, tex_start):
    return quads(decode_object(blob, 0, 0), tex_adr=tex_start)


def test_a_strip_of_quads_costs_one_record_each():
    """Neighbours share an edge (reversed, as a consistently wound mesh has it): after the first quad's two records,
    each next quad costs one record whose link keeps the shared edge as the next 'old' edge (Phase 18 recon §3)."""
    src = [q(10 * i, 0, 100) for i in range(10)]
    blob, layout = encode_object(src, tex_start=100)
    assert layout.record_count == 11
    assert len(blob) == 4 * (6 + 10 * 11 + 10)
    assert sorted(_canon(o.p) for o in _decoded(blob, 100)) == sorted(_canon(s.p) for s in src)


def test_chained_objects_decode_to_the_same_polygons():
    """A 6x5 grid with three cells split into two triangles (a quad with its last point repeated) and two colours:
    the decoded polygons are the input's, each with its own colour and normal, in fewer than two records each."""
    src = []
    for r in range(5):
        for c in range(6):
            a, b, cc, d = ((10 * c, 0.0, 10 * r), (10 * c + 10, 0.0, 10 * r), (10 * c + 10, 0.0, 10 * r + 10), (10 * c, 0.0, 10 * r + 10))
            tex = 100 if r < 3 else 101
            n = (0.0, 1.0, float(r * 6 + c))                       # a distinct normal per cell, to follow each polygon
            if (c, r) in ((1, 1), (3, 2), (4, 4)):
                src += [Quad((a, b, cc, cc), n, 0x201, tex), Quad((a, cc, d, d), n, 0x201, tex)]
            else:
                src.append(Quad((a, b, cc, d), n, 0x201, tex))
    blob, layout = encode_object(src, tex_start=100)
    out = _decoded(blob, 100)
    assert len(out) == len(src)
    assert {_canon(o.p): (o.tex_adr, o.normal) for o in out} == {_canon(s.p): (s.tex_adr, s.normal) for s in src}
    assert layout.record_count < 2 * len(src)


def _mixed():
    """A made-up object: strips, a second and a third tex run, a triangle (a repeated corner), a raised quad."""
    def tri(x0, z0, tex):
        return Quad(((x0, 0.0, z0), (x0 + 5, 0.0, z0), (x0 + 5, 0.0, z0 + 5), (x0 + 5, 0.0, z0 + 5)), (0.0, -1.0, 0.0), 0x201, tex)
    raised = Quad(tuple((x, 1.0, z) for x, _, z in q(310, 0, 8).p), N, 0x201, 8)
    return ([q(10 * i, 0, 7) for i in range(6)] + [q(0, 10 * j, 7) for j in range(1, 4)] + [tri(200, 0, 8), q(300, 0, 8), raised]
            + [q(500 + 10 * i, 50, 9) for i in range(5)])


def test_an_object_without_one_sided_quads_encodes_as_before():
    """Phase 26 stage 2: the per-quad one-sided mark changes nothing for an object that has none (digests of this object's
    bytes taken before the mark existed)."""
    import hashlib
    for nc, digest in ((False, "c1e3ba5b227f89f2c79aae7c12ee6668c229fee15092654bc14a444efd8270b2"),
                       (True, "59f55ddad1e02f99baff6a87ada03dd5aec8fdb769f843064c3da1357988d30d")):
        blob, layout = encode_object(_mixed(), tex_start=7, no_cull=nc)
        assert hashlib.sha256(blob).hexdigest() == digest and layout == ObjectLayout(23, 7, 9)


def test_one_sided_quads_clear_the_skip_back_face_bit_on_their_own_records_only():
    """Bit 14 ("skip back-face test") is per record: a one-sided quad's drawing record has it clear, every other drawing
    record of a no_cull object keeps it. A one-sided quad joins no strip (its own two records), so its winding is the
    one it was given."""
    from dataclasses import replace
    src = _mixed()
    one = {2, 7, 10, 12}                                     # inside the first strip, the triangle, the raised quad
    marked = [replace(s, one_sided=True) if i in one else s for i, s in enumerate(src)]
    blob, layout = encode_object(marked, tex_start=7, no_cull=True)
    drawn = _decoded(blob, 7)
    assert sorted(_canon(o.p) for o in drawn) == sorted(_canon(s.p) for s in src)
    one_drawn = [o for o in drawn if not o.flags & 0x4000]
    assert sorted(_canon(o.p) for o in one_drawn) == sorted(_canon(src[i].p) for i in one)
    for o in one_drawn:                                       # the given cyclic order (not reversed)
        s = next(src[i] for i in one if _canon(src[i].p) == _canon(o.p))
        assert any(tuple(s.p[k:] + s.p[:k]) == o.p for k in range(4))
    assert [r.no_cull for r in decode_object(blob, 0, 0).records if r.link].count(False) == len(one)


def test_a_one_sided_triangle_is_tested_on_three_distinct_corners():
    """MAME's back-face test takes the first three drawn corners (old_p1, old_p0, p0): with the repeated corner among
    them the determinant is 0 and the face is drawn from both sides."""
    t = Quad(((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (5.0, 0.0, 5.0)), N, 0x201, 1, one_sided=True)
    blob, _ = encode_object([t], tex_start=1, no_cull=True)
    (o,) = _decoded(blob, 1)
    assert len({o.p[0], o.p[1], o.p[2]}) == 3 and any(t.p[k:] + t.p[:k] == o.p for k in range(4))   # rotated, not reversed
