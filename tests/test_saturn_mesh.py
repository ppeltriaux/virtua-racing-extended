import struct

import pytest

from vrtools.saturn.course import Face, Mesh, SaturnError, encode_mesh, meshes, to_fx
from vrtools.saturn.trck import LOAD_BASE, POINTER_COUNT, TrckFile

BASE = LOAD_BASE


def make_trck(sections: dict[int, bytes], length: int = 0x8000) -> TrckFile:
    data = bytearray(length)
    off = 0xB0
    placed = {}
    for idx, blob in sections.items():
        struct.pack_into(">I", data, idx * 4, BASE + off)
        data[off:off + len(blob)] = blob
        placed[idx] = off
        off += len(blob)
    end_idx = max(i for i in range(POINTER_COUNT) if i not in sections)
    struct.pack_into(">I", data, end_idx * 4, BASE + off)
    return TrckFile.from_bytes(bytes(data)), placed


def obj_bytes(vertices, normals=((0.0, 1.0, 0.0),), faces=(), tail: bytes = b"") -> bytes:
    out = struct.pack(">I", len(vertices)) + b"".join(struct.pack(">3i", *(to_fx(c) for c in v)) for v in vertices)
    out += struct.pack(">I", len(normals)) + b"".join(struct.pack(">3i", *(to_fx(c) for c in v)) for v in normals)
    out += struct.pack(">I", len(faces)) + b"".join(struct.pack(">7H", *f) for f in faces)
    return out + tail


def test_mesh_vertices_decode():
    tri = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
    quad = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 0.0, 2.0), (0.0, 0.0, 2.0)]
    o1 = obj_bytes(tri, faces=[(0x2D6B, 0, 1, 0, 1, 2, 2)])
    o2 = obj_bytes(quad, faces=[(0x35AD, 3, 1, 0, 1, 2, 3)], tail=b"\x00\x00")
    t, placed = make_trck({10: o1 + o2, 2: b""})
    plist = struct.pack(">2I", BASE + placed[10], BASE + placed[10] + len(o1))   # group 0 pointer list (section 2)
    t, placed = make_trck({10: o1 + o2, 2: plist})
    ms = meshes(t, group=0)
    assert [m.index for m in ms] == [0, 1]
    assert ms[0].vertices == tri and all(a == pytest.approx(b) for a, b in zip(ms[1].vertices, quad))
    assert ms[0].faces == [Face(0x2D6B, 0, 1, (0, 1, 2, 2))] and ms[0].normals == [(0.0, 1.0, 0.0)]
    assert ms[1].raw_tail == b"\x00\x00"


def test_face_vertex_out_of_range_raises():
    o = obj_bytes([(0.0, 0.0, 0.0)], faces=[(0, 0, 0, 0, 0, 0, 5)])
    t, placed = make_trck({10: o, 2: struct.pack(">I", BASE + 0xB0)})
    with pytest.raises(SaturnError, match="object 0: face 0"):
        meshes(t, group=0)


def test_vertex_count_past_blob_raises():
    blob = struct.pack(">I", 1000) + b"\x00" * 96
    t, placed = make_trck({10: blob, 2: struct.pack(">I", BASE + 0xB0)})
    with pytest.raises(SaturnError, match="object 0"):
        meshes(t, group=0)


def test_encode_round_trip():
    tri = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
    raw = obj_bytes(tri, faces=[(0x2D6B, 0, 1, 0, 1, 2, 2)], tail=b"\x01\x02\x03\x04")
    t, placed = make_trck({10: raw, 2: struct.pack(">I", BASE + 0xB0)})
    m = meshes(t, group=0)[0]
    assert encode_mesh(m) == raw
    with pytest.raises(SaturnError):
        encode_mesh(Mesh(0, [(40000.0, 0.0, 0.0)], m.normals, m.faces, m.raw_tail))
    with pytest.raises(SaturnError):
        encode_mesh(Mesh(0, m.vertices, m.normals, [Face(0x10000, 0, 0, (0, 0, 0, 0))], b""))


COURSES = ["ACROPOLS/TRCKACRO", "ALPINE00/TRCKALPN", "AMAZON00/TRCKAMAZ", "BAYBRIDG/TRCKBAYB", "BIGFORES/TRCKBIGF",
           "DIABLO00/TRCKDIAB", "METROPOL/TRCKMETR", "PACCOAST/TRCKPACC", "SPEEDWAY/TRCKSPEE", "SURFER00/TRCKSURF"]


@pytest.mark.parametrize("name", COURSES)
def test_real_meshes(saturn_cue, name):
    from vrtools.saturn.iso import Iso2352
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    t = TrckFile.from_bytes(iso.read(f"VRSRCDIR/TRACKS00/{name}"))
    counts = []
    for g in range(5):
        try:
            ms = meshes(t, g)
        except SaturnError as e:
            if "no object group" in str(e) or "missing" in str(e):
                continue
            raise
        counts.append(len(ms))
        for m in ms:
            assert all(max(f.vertex_ids) < len(m.vertices) for f in m.faces)      # some objects are empty placeholders
        assert sum(len(m.faces) for m in ms) > 0
    if name.endswith("TRCKBIGF"):
        assert counts[:2] == [25, 31]


# --- Task 4: placements -----------------------------------------------------
from vrtools.saturn.course import Placement, encode_placement, placements


def placement_bytes(mesh, x, y, z, yaw=0, radius=11.314, flags=0x1000, extra=0):
    return struct.pack(">14i", flags, mesh << 16, 0, yaw, extra, to_fx(x), to_fx(y), to_fx(z), 0, 0, 0, to_fx(radius), 0, 0)   # mesh is a signed i16 in the high half


def test_placement_decode():
    tbl = placement_bytes(-1, -18.693, 0.0, -75.791) + placement_bytes(3, -2.693, 0.5, -75.791, yaw=0x40000000, radius=2.0)
    o = obj_bytes([(0.0, 0.0, 0.0)], faces=[(0, 0, 0, 0, 0, 0, 0)])
    plist = b"".join(struct.pack(">I", BASE + 0xB0 + len(tbl) + 2 + 8 * i) for i in range(4))   # 4 meshes
    t, placed = make_trck({0: tbl, 1: struct.pack(">H", 2), 2: plist, 10: o * 4})
    # fix: pointers must target the objects placed after the pointer list
    plist = b"".join(struct.pack(">I", BASE + placed[10] + len(o) * i) for i in range(4))
    t, placed = make_trck({0: tbl, 1: struct.pack(">H", 2), 2: plist, 10: o * 4})
    ps = placements(t, group=0)
    assert ps[0] == Placement(0, -1, pytest.approx(-18.693, abs=1e-3), 0.0, pytest.approx(-75.791, abs=1e-3), 0, 0x1000, pytest.approx(11.314, abs=1e-3), ps[0].raw)
    assert ps[1].mesh == 3 and ps[1].yaw_degrees == pytest.approx(90.0) and ps[1].radius == pytest.approx(2.0, abs=1e-3)


def test_mesh_index_out_of_range_raises():
    tbl = placement_bytes(7, 0.0, 0.0, 0.0)
    o = obj_bytes([(0.0, 0.0, 0.0)], faces=[(0, 0, 0, 0, 0, 0, 0)])
    t, placed = make_trck({0: tbl, 1: struct.pack(">H", 1), 2: struct.pack(">I", BASE + 0xB0 + len(tbl) + 2 + 4), 10: o})
    t, placed = make_trck({0: tbl, 1: struct.pack(">H", 1), 2: struct.pack(">I", BASE + placed[10]), 10: o})
    with pytest.raises(SaturnError, match="placement 0"):
        placements(t, group=0)


def test_placement_round_trip():
    raw = placement_bytes(2, 1.0, 0.25, -3.0, yaw=-0x15555540, radius=1.5, extra=-5461)
    o = obj_bytes([(0.0, 0.0, 0.0)], faces=[(0, 0, 0, 0, 0, 0, 0)])
    t, placed = make_trck({0: raw, 1: struct.pack(">H", 1), 2: struct.pack(">I", BASE + 0xB0), 10: o * 3})
    t, placed = make_trck({0: raw, 1: struct.pack(">H", 1), 2: b"".join(struct.pack(">I", BASE + placed[10] + len(o) * i) for i in range(3)), 10: o * 3})
    p = placements(t, group=0)[0]
    assert encode_placement(p) == raw
    with pytest.raises(SaturnError):
        encode_placement(Placement(0, 70000, 0, 0, 0, 0, 0, 1.0, p.raw))


@pytest.mark.parametrize("name", COURSES)
def test_real_placements(saturn_cue, name):
    from vrtools.saturn.iso import Iso2352
    from vrtools.saturn.course import grid_bounds, segments
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    t = TrckFile.from_bytes(iso.read(f"VRSRCDIR/TRACKS00/{name}"))
    xmin, zmin, xmax, zmax = grid_bounds(segments(t))
    for g in range(5):
        try:
            ps = placements(t, g)
        except SaturnError as e:
            if "missing" in str(e):
                continue
            raise
        assert ps
        if g < 4:                                                                 # ground tiles: a 16-unit lattice
            xs = sorted({round(p.x, 3) for p in ps}); zs = sorted({round(p.z, 3) for p in ps})
            assert all(abs((v - xs[0]) % 16.0) < 1e-2 or abs((v - xs[0]) % 16.0 - 16.0) < 1e-2 for v in xs)
            assert all(abs((v - zs[0]) % 16.0) < 1e-2 or abs((v - zs[0]) % 16.0 - 16.0) < 1e-2 for v in zs)
            assert all(p.flags == 0x1000 and abs(p.radius - 11.314) < 1e-2 for p in ps)
        else:                                                                     # props: any position (distant scenery exists)
            assert all(p.flags == 0 for p in ps)
    if name.endswith("TRCKBIGF"):
        g0 = placements(t, 0)
        assert len(g0) == 36 and len({round(p.x, 2) for p in g0}) == 4 and len({round(p.z, 2) for p in g0}) == 9


# --- review fixes: object extents and pointer lists -------------------------

def test_object_extent_stops_at_other_groups_objects():
    o0 = obj_bytes([(0.0, 0.0, 0.0)], faces=[(0, 0, 0, 0, 0, 0, 0)])
    o1 = obj_bytes([(1.0, 1.0, 1.0)], faces=[(0, 0, 0, 0, 0, 0, 0)])
    blob = o0 + o1 + o0                           # group 0 object, group 1 object, group 0 object
    t, placed = make_trck({10: blob, 2: b"", 18: b""})
    base = BASE + placed[10]
    t, placed = make_trck({10: blob, 2: struct.pack(">2I", base, base + 2 * len(o0)), 18: struct.pack(">I", base + len(o0))})
    ms = meshes(t, group=0)
    assert ms[0].raw_tail == b"" and len(ms[0].vertices) == 1                   # not swallowing the group-1 object


def test_object_extent_stops_at_section_end():
    o0 = obj_bytes([(0.0, 0.0, 0.0)], faces=[(0, 0, 0, 0, 0, 0, 0)])
    t, placed = make_trck({10: o0, 11: b"\x00\x00\x00\x09", 2: b""})
    t, placed = make_trck({10: o0, 11: b"\x00\x00\x00\x09", 2: struct.pack(">I", BASE + placed[10])})
    assert meshes(t, group=0)[0].raw_tail == b""


def test_vertex_count_cannot_run_into_next_section():
    bad = struct.pack(">I", 3) + bytes(12)        # claims 3 vertices, section holds one
    t, placed = make_trck({10: bad, 11: bytes(64), 2: b""})
    t, placed = make_trck({10: bad, 11: bytes(64), 2: struct.pack(">I", BASE + placed[10])})
    with pytest.raises(SaturnError, match="object 0"):
        meshes(t, group=0)


def test_interior_null_pointer_raises_and_range_checked():
    o0 = obj_bytes([(0.0, 0.0, 0.0)], faces=[(0, 0, 0, 0, 0, 0, 0)])
    t, placed = make_trck({10: o0 + o0, 2: b""})
    base = BASE + placed[10]
    t, _ = make_trck({10: o0 + o0, 2: struct.pack(">3I", base, 0, base + len(o0))})
    with pytest.raises(SaturnError, match="slot 1"):
        meshes(t, group=0)
    t, _ = make_trck({10: o0, 2: struct.pack(">I", 0x00001000)})
    with pytest.raises(SaturnError, match="outside the file"):
        meshes(t, group=0)


def test_encode_course_regions_do_not_overlap(saturn_cue):
    from vrtools.saturn.course import decode_course, encode_course
    from vrtools.saturn.iso import Iso2352
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    t = TrckFile.from_bytes(iso.read("VRSRCDIR/TRACKS00/BIGFORES/TRCKBIGF"))
    c = decode_course(t)
    regions = sorted((off, off + len(b)) for off, b in encode_course(c).items())
    assert all(regions[i][1] <= regions[i + 1][0] for i in range(len(regions) - 1))
    assert all(len(m.raw_tail) <= 16 for ms in c.meshes.values() for m in ms)
