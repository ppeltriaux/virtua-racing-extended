import math
import struct

import pytest

from vrtools.saturn.course import FIX, Plane, SaturnError, Segment, encode_segment, fx, segments, to_fx
from vrtools.saturn.trck import LOAD_BASE, POINTER_COUNT, TrckFile

BASE = LOAD_BASE


def make_trck(sections: dict[int, bytes], length: int = 0x4000) -> TrckFile:
    """Synthetic TRCK file: pointer i -> section bytes placed sequentially after the table."""
    data = bytearray(length)
    off = 0xB0
    for idx, blob in sections.items():
        struct.pack_into(">I", data, idx * 4, BASE + off)
        data[off:off + len(blob)] = blob
        off += len(blob)
    end_idx = max(i for i in range(POINTER_COUNT) if i not in sections)      # end marker so lengths are exact
    struct.pack_into(">I", data, end_idx * 4, BASE + off)
    return TrckFile.from_bytes(bytes(data))


def seg_record(planes, normal=(0.0, 1.0, 0.0), words=(0, 0, 0, 0)) -> bytes:
    b = b""
    for nx, nz, d in planes:
        b += struct.pack(">3i", to_fx(nx), to_fx(nz), to_fx(d))
    b += struct.pack(">3i", *(to_fx(v) for v in normal))
    b += struct.pack(">4i", *words)
    assert len(b) == 76, len(b)
    return b


STRAIGHT = [(1.0, 0.0, -14.6), (0.0, 1.0, -41.992), (-1.0, 0.0, 17.09), (0.0, -1.0, 42.992)]


def test_fx_helpers():
    assert fx(0x00010000) == 1.0 and to_fx(-0.5) == -0x8000
    with pytest.raises(SaturnError):
        to_fx(40000.0)


def test_segment_decode_planes_and_centre():
    t = make_trck({4: seg_record(STRAIGHT, words=(1, 2, 3, 4))})
    s = segments(t)
    assert len(s) == 1 and s[0].index == 0
    assert s[0].planes[0] == Plane(1.0, 0.0, pytest.approx(-14.6, abs=1e-4))
    assert s[0].centre == pytest.approx((15.845, 42.492), abs=1e-3)
    assert s[0].width == pytest.approx(2.49, abs=1e-3)
    assert s[0].length == pytest.approx(1.0, abs=1e-3)
    assert s[0].heading == pytest.approx(math.pi / 2, abs=1e-3)      # along +z
    assert s[0].words == (1, 2, 3, 4)


def test_bad_section_length_raises():
    t = make_trck({4: seg_record(STRAIGHT) + b"\x00"})
    with pytest.raises(SaturnError, match="section 4"):
        segments(t)


def test_parallel_consecutive_planes_give_none_centre():
    skew = [(1.0, 0.0, -14.6), (1.0, 0.0, -41.992), (-1.0, 0.0, 17.09), (0.0, -1.0, 42.992)]   # planes 0 and 1 parallel
    s = segments(make_trck({4: seg_record(skew)}))
    assert s[0].centre is None and s[0].width is None and s[0].heading is None


def test_triangle_segment_has_centre_but_no_width():
    tri = [(1.0, 0.0, -14.6), (0.0, 1.0, -41.992), (-0.7071, -0.7071, 42.43), (0.0, 0.0, 0.0)]   # x+z <= 60: a real triangle
    s = segments(make_trck({4: seg_record(tri)}))[0]
    assert len(s.active_planes) == 3 and s.centre is not None and s.width is None and s.heading is None


def test_angles_from_words():
    s = segments(make_trck({4: seg_record(STRAIGHT, words=(0, 0, -11891315, 0))}))[0]
    assert s.angles[2] == pytest.approx(-0.997, abs=0.01)


def test_wedge_segment_has_centre():
    import math as m
    a = m.radians(10)
    nx, nz = m.sin(a), -m.cos(a)                                   # exit plane turned 10 deg, through (15.845, 42.992)
    wedge = [(1.0, 0.0, -14.6), (0.0, 1.0, -41.992), (-1.0, 0.0, 17.09), (nx, nz, -(nx * 15.845 + nz * 42.992))]
    s = segments(make_trck({4: seg_record(wedge)}))[0]
    assert s.centre is not None and 2.3 < s.width < 2.7


def test_encode_round_trip():
    rec = seg_record(STRAIGHT, words=(7, 8, 9, 10))
    s = segments(make_trck({4: rec}))[0]
    assert encode_segment(s) == rec
    with pytest.raises(SaturnError):
        encode_segment(Segment(0, s.planes, s.normal, (1 << 33, 0, 0, 0)))


COURSES = ["ACROPOLS/TRCKACRO", "ALPINE00/TRCKALPN", "AMAZON00/TRCKAMAZ", "BAYBRIDG/TRCKBAYB", "BIGFORES/TRCKBIGF",
           "DIABLO00/TRCKDIAB", "METROPOL/TRCKMETR", "PACCOAST/TRCKPACC", "SPEEDWAY/TRCKSPEE", "SURFER00/TRCKSURF"]


def load_track(saturn_cue, name: str) -> TrckFile:
    from vrtools.saturn.iso import Iso2352
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    return TrckFile.from_bytes(iso.read(f"VRSRCDIR/TRACKS00/{name}"))


@pytest.mark.parametrize("name", COURSES)
def test_real_segments(saturn_cue, name):
    t = load_track(saturn_cue, name)
    s = segments(t)
    sec4 = next(x for x in t.sections() if x.index == 4)
    assert len(s) == sec4.length // 76
    assert sum(1 for x in s if x.centre is not None) >= 0.98 * len(s)
    if name.endswith("TRCKBIGF"):
        import statistics
        widths = [x.width for x in s if x.width is not None]
        assert sum(1 for w in widths if 2.3 <= w <= 2.7) >= 0.6 * len(widths)     # measured: 69 % (pit lane, run-off differ)
        assert 2.3 <= statistics.median(widths) <= 2.6


# --- Task 2: grid -----------------------------------------------------------
from vrtools.saturn.course import Grid, encode_grid, grid, grid_bounds


def grid_section(cells: dict[int, list[int]], section_base: int) -> bytes:
    """256 pointers (absolute, relative to where the section loads) then count/index lists."""
    lists = b""
    offsets = {}
    for c in sorted(cells):
        offsets[c] = 0x400 + len(lists)
        lists += struct.pack(">H", len(cells[c])) + b"".join(struct.pack(">H", i) for i in cells[c])
    ptrs = b"".join(struct.pack(">I", section_base + offsets[c] if c in cells else 0) for c in range(256))
    return ptrs + lists


def test_grid_lists_and_round_trip():
    sec = grid_section({5: [1, 2], 17: [3], 255: [0, 4, 1]}, BASE + 0xB0)
    t = make_trck({9: sec})
    g = grid(t, segment_count=5)
    assert isinstance(g, Grid) and len(g.cells) == 256
    assert g.cells[5] == [1, 2] and g.cells[17] == [3] and g.cells[255] == [0, 4, 1] and g.cells[0] == []
    assert encode_grid(g, BASE + 0xB0) == sec


def test_index_out_of_range_raises():
    t = make_trck({9: grid_section({5: [1, 9]}, BASE + 0xB0)})
    with pytest.raises(SaturnError, match="cell 5"):
        grid(t, segment_count=5)


def test_grid_bounds():
    t = make_trck({4: seg_record(STRAIGHT) + seg_record([(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 2.0), (0.0, -1.0, 1.0)])})
    assert grid_bounds(segments(t)) == pytest.approx((0.0, 0.0, 17.09, 42.992), abs=1e-3)


@pytest.mark.parametrize("name", COURSES)
def test_real_grid(saturn_cue, name):
    t = load_track(saturn_cue, name)
    g = grid(t, segment_count=len(segments(t)))
    used = [c for c in g.cells if c]
    assert 60 <= len(used) <= 256          # measured: 71-109 cells used
    assert sum(len(c) for c in g.cells) >= len(segments(t))


from vrtools.saturn.course import GridParams, cell_of, grid_params


def test_grid_params_and_cell_of():
    secs = {5: struct.pack(">i", to_fx(-20.6)), 6: struct.pack(">i", to_fx(-61.9)), 7: struct.pack(">i", to_fx(0.3185)), 8: struct.pack(">i", to_fx(0.142))}
    t = make_trck(secs)
    gp = grid_params(t)
    assert gp == GridParams(pytest.approx(20.6, abs=1e-3), pytest.approx(61.9, abs=1e-3), pytest.approx(0.3185, abs=1e-4), pytest.approx(0.142, abs=1e-4))
    assert cell_of(gp, 20.6, 61.9) == 0                      # the (xmax, zmax) corner is cell 0
    assert cell_of(gp, 20.6 - 3.5, 61.9) == 1                # one cell width (3.14) to the left -> xc 1
    assert cell_of(gp, 20.6, 61.9 - 7.5) == 16               # one cell height (7.04) down -> zc 1
    with pytest.raises(SaturnError):
        cell_of(gp, 500.0, 0.0)


# --- review fixes: polygon validity -----------------------------------------

def test_near_parallel_consecutive_planes_give_none():
    eps = 2e-5
    skew = [(1.0, 0.0, -14.6), (math.cos(eps), math.sin(eps), -14.61), (-1.0, 0.0, 17.09), (0.0, -1.0, 42.992)]
    s = segments(make_trck({4: seg_record(skew)}))[0]
    assert s.centre is None


def test_same_facing_pair_is_not_a_polygon():
    unbounded = [(1.0, 0.0, -14.6), (0.0, 1.0, -41.992), (1.0, 0.0, -17.09), (0.0, -1.0, 42.992)]   # x >= 14.6 and x >= 17.09
    s = segments(make_trck({4: seg_record(unbounded)}))[0]
    assert s.centre is None and s.width is None


def test_corners_inside_all_planes():
    s = segments(make_trck({4: seg_record(STRAIGHT)}))[0]
    for x, z in s.corners():
        assert all(p.nx * x + p.nz * z + p.d >= -1e-3 for p in s.active_planes)
