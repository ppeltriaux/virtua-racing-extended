import math
import os
from pathlib import Path

import pytest

from vrtools.arcade.romset import RomSet
from vrtools.arcade.tgp import Quad16, decode_collision, xz_area
from vrtools.convert.collision import ConvertError, cell_lists, mesh_height, saturn_collision, slice_quads
from vrtools.saturn.course import Plane, SaturnCourse, Segment, decode_course
from vrtools.saturn.iso import Iso2352
from vrtools.saturn.trck import TrckFile


def _quad(corners):
    c = [tuple(float(v) for v in p) for p in corners]
    centre = tuple(sum(p[j] for p in c) / 4 for j in range(3))
    return Quad16(tuple(c), centre, 0)


def _one_segment_course(corners):
    """A SaturnCourse with one rectangular slice (Saturn units): planes left, bottom, right, top (n.p + d >= 0 inside)."""
    (x0, z0), (x1, _), (_, z1), _ = corners
    planes = (Plane(1, 0, -x0), Plane(0, 1, -z0), Plane(-1, 0, x1), Plane(0, -1, z1))
    seg = Segment(0, planes, (0.0, 1.0, 0.0), (0, 0, 0, 0))
    return SaturnCourse(None, [seg], None, None, {}, {})


def _point_in_xz(q, x, z):
    c = q.corners
    signs = [((c[(k + 1) % 4][0] - c[k][0]) * (z - c[k][2]) - (c[(k + 1) % 4][2] - c[k][2]) * (x - c[k][0])) for k in range(4)]
    return all(s <= 0 for s in signs) or all(s >= 0 for s in signs)


def _saturn_course(cue, name):
    iso = Iso2352(Path(cue).with_name("Virtua Racing (Europe) (Track 01).bin"))
    return decode_course(TrckFile.from_bytes(iso.read(f"VRSRCDIR/TRACKS00/{name}")))


def test_cell_lists_cover_every_overlapped_cell_and_reject_outside():
    q = _quad(((-40, 0, -40), (40, 0, -40), (40, 0, -30), (-40, 0, -30)))     # x cells 61..66, z cells 61..62 (-32 is a boundary)
    lists, cells = cell_lists([q])
    assert sorted(cells) == [zc * 128 + xc for zc in (61, 62) for xc in range(61, 67)]
    assert all(lists[cells[c]] == [0] for c in cells) and min(cells.values()) == 1
    assert list(lists) == sorted(lists) and next(iter(lists)) == 1                 # consecutive from offset 1
    with pytest.raises(ConvertError):
        cell_lists([_quad(((1020, 0, 0), (1030, 0, 0), (1030, 0, 5), (1020, 0, 5)))])


def test_slice_quads_winding_and_height():
    sat = _one_segment_course(((0, 0), (2, 0), (2, 1), (0, 1)))          # 2 wide (across the road) x 1 long
    [q] = slice_quads(sat, height=lambda x, z: 30.0, margin=0)
    assert all(abs(c[1] - 30.0) < 1e-6 for c in q.corners) and xz_area(q) < 0
    assert max(c[0] for c in q.corners) - min(c[0] for c in q.corners) == pytest.approx(2 * 11.7)
    assert q.centre[1] == pytest.approx(30.0) and q.attr == 0
    from vrtools.convert.collision import OVERLAP
    [w] = slice_quads(sat, height=lambda x, z: 30.0, margin=10)        # margin widens across the road only
    assert max(c[0] for c in w.corners) - min(c[0] for c in w.corners) == pytest.approx(2 * 11.7 + 20)
    assert max(c[2] for c in w.corners) - min(c[2] for c in w.corners) == pytest.approx(11.7 + 2 * OVERLAP)


def test_slice_quads_overlap_along_the_road():
    """Consecutive Saturn slices leave 0.01-unit seams; each quad is stretched by OVERLAP at both ends to close them."""
    from vrtools.convert.collision import OVERLAP
    sat = _one_segment_course(((0, 0), (2, 0), (2, 1), (0, 1)))          # 2 across x 1 along (Saturn units)
    [q] = slice_quads(sat, height=lambda x, z: 30.0, margin=0)
    zs = [c[2] for c in q.corners]
    assert max(zs) - min(zs) == pytest.approx(11.7 + 2 * OVERLAP) and OVERLAP >= 0.5


def test_mesh_height_samples_the_ground_mesh():
    from vrtools.convert.geometry import WorldQuad
    ground = [WorldQuad(((0, 5, 0), (100, 5, 0), (100, 7, 100), (0, 7, 100)), (0, 0, 0))]
    h = mesh_height(ground)
    assert h(50, 50) == pytest.approx(6.0, abs=0.01)
    with pytest.raises(ConvertError):
        h(500, 500)


def test_real_big_forest_matches_arcade_collision(saturn_cue, romset_zip):
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    arcade = decode_collision(rs, 0)
    col, cells = saturn_collision(sat, height=lambda x, z: 30.0)
    col.check()
    assert 380 <= len(col.quads) <= 431 and len(cells) >= 700
    sample = arcade.quads[::20]
    covered = sum(any(_point_in_xz(q, aq.centre[0], aq.centre[2]) for q in col.quads) for aq in sample)
    assert covered / len(sample) > 0.85, f"{covered}/{len(sample)} arcade quad centres covered"   # 0.88 measured; the rest is run-off beyond the 30-unit margin


def test_widening_keeps_every_point_of_the_unwidened_slices(saturn_cue):
    """Widening must only add surface: no point of the tarmac may be uncovered by the widened quads."""
    import random
    from vrtools.convert.collision import _point_in_xz
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    plain = slice_quads(sat, height=lambda x, z: 30.0, margin=0)
    wide = slice_quads(sat, height=lambda x, z: 30.0)
    assert len(plain) == len(wide)
    rng = random.Random(5)
    lost = 0
    for p, w in zip(plain, wide):
        xs = [c[0] for c in p.corners]; zs = [c[2] for c in p.corners]
        for _ in range(40):
            x, z = rng.uniform(min(xs), max(xs)), rng.uniform(min(zs), max(zs))
            if _point_in_xz(p.corners, x, z) and not _point_in_xz(w.corners, x, z):
                lost += 1
    assert lost == 0


def test_cell_lists_follow_the_v60_truncation_on_the_negative_side():
    """The V60 computes the cell from int(x) (truncation toward zero): x = -16.5 lands in the cell of -16, not -17."""
    from vrtools.arcade.course import collision_cell
    q = _quad(((-40, 0, 0), (-16.3, 0, 0), (-16.3, 0, 5), (-40, 0, 5)))
    lists, cells = cell_lists([q])
    assert collision_cell(-16.5, 2.0) in cells
    assert collision_cell(-39.5, 2.0) in cells and collision_cell(-17.0, 2.0) in cells


# --- Phase 6: road direction from the lap ------------------------------------------------------------------------

def test_direction_attr_convention_and_wrap():
    from vrtools.convert.collision import direction_attr
    assert direction_attr(0.0, 1.0) == 0                                   # travelling +z
    assert direction_attr(1.0, 0.0) == 0xFFFFC000                          # +x: -90 deg = -0x4000, sign-extended
    assert direction_attr(-1.0, 0.0) == 0x4000
    assert direction_attr(0.0, -1.0) in (0x8000, 0xFFFF8000)
    assert direction_attr(0.0, 0.0) == 0


def test_real_big_forest_directions_match_the_arcade(romset_zip, saturn_cue):
    import math
    from vrtools.convert.lap import order_slices
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    col, cells = saturn_collision(sat, height=lambda x, z: 30.0, lap=lap)
    arcade = decode_collision(rs, 0)
    nonzero = [q for q in arcade.quads if q.attr & 0xFFFF]
    close = n = 0
    for q in col.quads[::3]:
        a = min(nonzero, key=lambda o: (o.centre[0] - q.centre[0]) ** 2 + (o.centre[2] - q.centre[2]) ** 2)
        if math.hypot(a.centre[0] - q.centre[0], a.centre[2] - q.centre[2]) > 12:
            continue
        n += 1
        diff = ((q.attr & 0xFFFF) - (a.attr & 0xFFFF) + 0x8000) % 0x10000 - 0x8000
        close += abs(diff) < 4096                                          # within 22 degrees
    assert n > 100 and close / n > 0.8, (close, n)


def test_converted_quads_use_the_arcade_corner_order(saturn_cue):
    """Front-left, front-right, back-right, back-left relative to the quad's own direction attribute."""
    import math
    from vrtools.convert.lap import order_slices
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    col, _ = saturn_collision(sat, height=lambda x, z: 30.0, lap=order_slices(sat))
    ok = 0
    for q in col.quads:
        a = q.attr & 0xFFFF
        ang = -(a if a < 0x8000 else a - 0x10000) / 65536 * 2 * math.pi
        dx, dz = math.sin(ang), math.cos(ang)
        rx, rz = dz, -dx
        cx, _, cz = q.centre
        pattern = "".join(("F" if (p[0] - cx) * dx + (p[2] - cz) * dz > 0 else "B") + ("R" if (p[0] - cx) * rx + (p[2] - cz) * rz > 0 else "L")
                          for p in q.corners)
        ok += pattern == "FLFRBRBL"
    assert ok / len(col.quads) > 0.9, ok


def test_tarmac_quads_come_first_in_lap_order_with_a_surface_table(saturn_cue):
    from vrtools.arcade.tgp import SURFACE_GRASS, SURFACE_TARMAC
    from vrtools.convert.lap import arc_of, order_slices
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    col, _ = saturn_collision(sat, height=lambda x, z: 30.0, lap=lap)
    n_tarmac = sum(1 for s in sat.segments if s.corners() is not None)
    assert n_tarmac < len(col.quads) <= 3 * n_tarmac
    assert col.surface[:n_tarmac] == bytes([SURFACE_TARMAC]) * n_tarmac and set(col.surface[n_tarmac:]) == {SURFACE_GRASS}
    from vrtools.convert.lap import centreline
    pts = centreline(lap)
    nearest = lambda q: min(range(len(pts)), key=lambda i: (pts[i][0] - q.centre[0]) ** 2 + (pts[i][1] - q.centre[2]) ** 2)
    idx = [nearest(q) for q in col.quads[:n_tarmac]]
    assert all(b >= a for a, b in zip(idx, idx[1:]))                            # lap order along the smoothed centreline


def _inside(q, x, z):
    pts = [(c[0], c[2]) for c in q.corners]; signs = set()
    for i in range(4):
        ax, az = pts[i]; bx, bz = pts[(i + 1) % 4]
        cr = (bx - ax) * (z - az) - (bz - az) * (x - ax)
        if abs(cr) > 1e-9:
            signs.add(cr > 0)
    return len(signs) == 1


def _convex(q):
    pts = [(c[0], c[2]) for c in q.corners]
    signs = set()
    for i in range(4):
        ax, az = pts[i]; bx, bz = pts[(i + 1) % 4]; cx, cz = pts[(i + 2) % 4]
        cr = (bx - ax) * (cz - bz) - (bz - az) * (cx - bx)
        if abs(cr) > 1e-6:
            signs.add(cr > 0)
    return len(signs) == 1


def test_merge_fuses_straight_slices_and_keeps_the_structure(saturn_cue):
    import math
    from vrtools.arcade.tgp import SURFACE_TARMAC, xz_area
    from vrtools.convert.lap import arc_of, centreline, order_slices
    sat = _saturn_course(saturn_cue, "ALPINE00/TRCKALPN")
    lap = order_slices(sat)
    h = lambda x, z: 0.0
    plain, _ = saturn_collision(sat, h, lap=lap)
    merged, cells = saturn_collision(sat, h, lap=lap, merge=True)
    n_tarmac = lambda c: sum(1 for b in c.surface if b == SURFACE_TARMAC)
    assert n_tarmac(merged) <= 0.85 * n_tarmac(plain) and merged.merged == n_tarmac(plain) - n_tarmac(merged)
    assert (merged.list_words + 16 * len(merged.quads)) <= 0.85 * (plain.list_words + 16 * len(plain.quads))
    tarmac = merged.quads[:n_tarmac(merged)]
    cl = centreline(lap)                                                                  # no point of the road loses its tarmac
    assert all(any(_inside(q, x, z) for q in tarmac) for x, z in cl)
    assert all(xz_area(q) < 0 for q in tarmac) and all(_convex(q) for q in tarmac)
    arcs = [arc_of(lap, q.centre[0], q.centre[2]) for q in tarmac]                       # still in lap order: a fused
    steps = [(b - a) % lap.length for a, b in zip(arcs, arcs[1:])]                       # quad spans up to ~70 units, and
    assert sum(1 for s in steps if s < 120) / len(steps) > 0.85                          # Alpine's start straight carries two
    assert plain.n_tarmac - merged.n_tarmac >= 100                                        # side-by-side strips (0.91 unmerged)
    turns = [abs(((a.attr - b.attr + 0x8000) % 0x10000) - 0x8000) for a, b in zip(tarmac, tarmac[1:])]
    assert sorted(turns)[int(0.95 * len(turns))] < 0x10000 * 15 / 360
    assert max(max(abs(c[0]), abs(c[2])) for q in tarmac for c in q.corners) < 1024


def test_merge_refuses_width_changes(saturn_cue):
    import math
    from vrtools.arcade.tgp import SURFACE_TARMAC
    from vrtools.convert.lap import order_slices
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    plain, _ = saturn_collision(sat, lambda x, z: 0.0, lap=lap)
    merged, _ = saturn_collision(sat, lambda x, z: 0.0, lap=lap, merge=True)
    n = sum(1 for b in merged.surface if b == SURFACE_TARMAC)
    original = {q.corners for q in plain.quads[:plain.n_tarmac]}
    fused = [q for q in merged.quads[:n] if q.corners not in original]
    assert fused
    for q in fused:                                                                 # a fused quad's ends agree in width
        rear, front = math.dist(q.corners[0], q.corners[1]), math.dist(q.corners[2], q.corners[3])
        assert abs(rear - front) <= 0.1 * max(rear, front) + 1.0


def _square_lap():
    from tests.test_convert_lap import _square_loop
    from vrtools.convert.lap import order_slices
    sat, _ = _square_loop(n_per_side=10)
    return sat, order_slices(sat)


def test_verges_share_the_tarmac_edge_height():
    import math
    """The TGP keeps the containing quad whose height is nearest the car's: a verge sampled from the road profile
    at its outer corners sits off the tarmac plane and captures a car in any overlap. A verge therefore takes its
    inner corners' heights straight across."""
    sat, lap = _square_lap()
    col, _ = saturn_collision(sat, height=lambda x, z: 0.1 * x + 0.05 * z, lap=lap)
    n = col.n_tarmac
    for v in col.quads[n:]:
        fl, fr, br, bl = v.corners
        assert fl[1] == pytest.approx(fr[1], abs=1e-6) and bl[1] == pytest.approx(br[1], abs=1e-6)


def test_tarmac_is_not_grown_across_the_road(monkeypatch):
    """Phases 5-22i grew each tarmac quad TARMAC_GROW (4) units sideways for the seams between side-by-side strips of
    Saturn slices; Phase 22j (Pascal: the camera's up/down jitter on the darker tarmac): the growth laid every quad over
    its neighbours across the road with its own surface (a banked road's rows, Alpine 148-157: three rows 8 units over
    each other, 0.3-0.5 apart; the game picks per wheel the overlapping quad nearest the car's height, the pick flipped
    and the suspension rang +-1.5-3 degrees). The coverage fill's strips cover the seams; the tarmac keeps the slice's
    own width and the verges start at its edge."""
    import math
    from vrtools.convert.collision import TARMAC_GROW
    assert TARMAC_GROW == 0.0
    sat, lap = _square_lap()
    col, _ = saturn_collision(sat, height=lambda x, z: 0.0, lap=lap)
    plain = slice_quads(sat, height=lambda x, z: 0.0, margin=0)          # no lap: the bare slice
    widths = sorted(round(math.dist(q.corners[0], q.corners[1]), 2) for q in col.quads[:col.n_tarmac])
    bare = sorted(round(max(math.dist(q.corners[k], q.corners[(k + 1) % 4]) for k in range(4)), 2) for q in plain)   # the across-road edge
    assert widths[len(widths) // 2] == pytest.approx(bare[len(bare) // 2], abs=0.05)
    tarmac, verges = col.quads[:col.n_tarmac], col.quads[col.n_tarmac:]
    corners = {(round(c[0], 4), round(c[2], 4)) for q in tarmac for c in q.corners}
    for v in verges:                                                      # a verge's inner edge is the tarmac's edge
        assert sum(1 for c in v.corners if (round(c[0], 4), round(c[2], 4)) in corners) == 2


def test_an_edge_gap_gets_a_strip_sharing_the_slices_edge():
    """Phase 22j: a gap beside a slice is covered by a strip that shares the slice's side edge, both corners exactly
    (position and height), and the slice itself is unchanged; growing the slice sideways bent its surface under the
    racing line (Phases 11-17 grew it, and the strip is where that growth went)."""
    from vrtools.convert.collision import OVERLAP, _point_in_xz, coverage_gaps, fill_coverage
    quads, pts, _ = _straight_road_near(0.0, half=5.0)
    slope = lambda x, z: 0.2 * x                                          # a banked road: the strip's outer corners climb
    quads = [_quad([(x, slope(x, z), z) for x, _, z in q.corners]) for q in quads]
    before = [q.corners for q in quads]
    gaps = coverage_gaps(quads, len(quads), pts, half_width=8.0)
    assert gaps and all(abs(g.lateral) >= 6 for g in gaps)
    filled, n_tarmac, report = fill_coverage(quads, len(quads), None, pts, slope, gaps)
    assert report["grown"] > 0 and report["fillers"] == 0, report
    tarmac = filled[:n_tarmac]
    assert [q.corners for q in tarmac if q.corners in before] == before   # every slice as it was, in order
    strips = [q for q in tarmac if q.corners not in before]
    for st in strips:                                                     # its inner edge lies on a slice's side (x = +-5),
        inner = [c for c in st.corners if abs(abs(c[0]) - 5.0) < 1e-6]   # with the slice's heights, and runs OVERLAP past
        outer = [c for c in st.corners if abs(abs(c[0]) - 5.0) >= 1e-6]  # the slice's corners at each end
        assert len(inner) == 2 and len(outer) == 2, st.corners
        assert all(c[1] == pytest.approx(slope(c[0], c[2]), abs=1e-6) for c in st.corners)
        zs = sorted(c[2] for c in inner)
        assert zs[1] - zs[0] == pytest.approx(10.0 + 2 * OVERLAP, abs=1e-6), zs
    assert not [g for g in coverage_gaps(filled, n_tarmac, pts, half_width=8.0)]
    assert not [(x, z) for z in range(5, 195, 10) for x in (-7.5, -6.5, 6.5, 7.5)
                if not any(_point_in_xz(q.corners, x, z) for q in tarmac)]


def test_strips_round_a_bend_share_their_outer_corners():
    """Phase 22j: strips of consecutive slices that share a side corner share their outer corner too (moved out along the
    mean of the two sides' normals), so they meet edge to edge round a bend: no wedge outside, no overlap inside. A
    quarter circle of 6-wide slices (radius 40, every 10 degrees) sampled to +-9 gets strips on both sides, and every
    inner corner shared by two slices has one outer corner for both."""
    import math
    from vrtools.convert.collision import _point_in_xz, coverage_gaps, fill_coverage
    R, HALF = 40.0, 6.0
    angs = [math.radians(a) for a in range(0, 100, 10)]
    ring = lambda r, a: (r * math.cos(a), 0.0, r * math.sin(a))
    quads, pts = [], []
    for a0, a1 in zip(angs, angs[1:]):
        quads.append(_quad([ring(R - HALF, a0), ring(R + HALF, a0), ring(R + HALF, a1), ring(R - HALF, a1)]))
        am = (a0 + a1) / 2; pts.append((R * math.cos(am), R * math.sin(am)))
    flat = lambda x, z: 0.0
    gaps = coverage_gaps(quads, len(quads), pts, half_width=9.0)
    assert gaps
    filled, n_tarmac, report = fill_coverage(quads, len(quads), None, pts, flat, gaps)
    assert report["grown"] >= 2 * (len(quads) - 1) and report["fillers"] <= 2, report    # (fillers: the open arc's two ends)
    tarmac = filled[:n_tarmac]
    strips = [q for q in tarmac if q not in quads and len([c for c in q.corners if (round(c[0], 3), round(c[2], 3)) in {(round(d[0], 3), round(d[2], 3)) for qq in quads for d in qq.corners}]) == 2]
    key = lambda c: (round(c[0], 3), round(c[2], 3))
    slice_corners = {key(c) for q in quads for c in q.corners}
    for st in strips:
        inner = [c for c in st.corners if key(c) in slice_corners]
        assert len(inner) == 2, st.corners
    outer_by_inner = {}
    for st in strips:                                                     # at each shared inner corner, one outer corner
        c = st.corners                                                    # arcade order: a right strip is (fr, out, out, br),
        pairs = ((0, 1), (3, 2)) if key(c[0]) in slice_corners else ((1, 0), (2, 3))   # a left one (out, fl, bl, out)
        for ii, oi in pairs:
            outer_by_inner.setdefault(key(c[ii]), set()).add(key(c[oi]))
    shared = [k for k, v in outer_by_inner.items() if sum(1 for q in quads for c in q.corners if key(c) == k) == 2]
    assert shared and all(len(outer_by_inner[k]) == 1 for k in shared), {k: outer_by_inner[k] for k in shared if len(outer_by_inner[k]) != 1}
    assert not coverage_gaps(filled, n_tarmac, pts, half_width=9.0)


def test_a_sub_unit_hole_between_slices_is_closed():
    """Phase 22j: with no overlap along the road, the Saturn's own tiling shows sub-unit holes (Metropolis's wide areas:
    slivers 0.2 wide and holes a unit across) that the coverage fill's 1-unit sampling never sees; the fine scan closes
    each with a tight filler at its neighbour's height, beside that neighbour in the list."""
    from vrtools.convert.collision import HOLE_MARGIN, _point_in_xz, fill_holes
    quads, pts, _ = _straight_road_near(0.0, half=12.0)
    slope = lambda x, z: 0.1 * z
    quads = [_quad([(x, slope(x, z), z) for x, _, z in q.corners]) for q in quads]
    c = list(quads[5].corners)                                            # z 50..60: its rear edge pulled to z 50.7 for x > 3
    quads[5] = _quad([c[0], c[1], c[2], c[3]])
    quads[5] = _quad([(-12.0, slope(-12, 50), 50.0), (3.0, slope(3, 50), 50.0), (3.0, slope(3, 60), 60.0), (-12.0, slope(-12, 60), 60.0)])
    quads.insert(6, _quad([(3.0, slope(3, 50.7), 50.7), (12.0, slope(12, 50.7), 50.7), (12.0, slope(12, 60), 60.0), (3.0, slope(3, 60), 60.0)]))
    pts5 = [(0.0, float(z)) for z in range(0, 200, 5)]
    before = [(x, z) for x in (4.0, 8.0, 11.0) for z in (50.2, 50.5) if not any(_point_in_xz(q.corners, x, z) for q in quads)]
    assert before
    filled, n_tarmac, added = fill_holes(quads, len(quads), pts5, slope, half_width=12.0)
    assert added == 1
    filler = [q for q in filled[:n_tarmac] if q not in quads][0]
    assert filled.index(filler) in (6, 7)                                  # beside the quad it borders
    xs = sorted(c[0] for c in filler.corners); zs = sorted(c[2] for c in filler.corners)
    assert zs[0] >= 50.0 - HOLE_MARGIN - 0.5 and zs[-1] <= 50.7 + HOLE_MARGIN + 0.5 and xs[0] >= 3.0 - HOLE_MARGIN - 0.5
    assert all(abs(c[1] - slope(c[0], c[2])) < 0.05 for c in filler.corners)
    assert not [(x, z) for x in (4.0, 8.0, 11.0) for z in (50.2, 50.5) if not any(_point_in_xz(q.corners, x, z) for q in filled[:n_tarmac])]


def test_fillers_abut_and_cover_their_gaps_only():
    """Phase 22j: consecutive fillers used to overlap by half a point and reach 6 units past their gaps over the slices,
    each with its own surface. A hole across the road gets fillers FILLER_MARGIN beyond its gaps, one per
    FILLER_LENGTH of points, meeting edge to edge."""
    from vrtools.convert.collision import FILLER_MARGIN, coverage_gaps, fill_coverage
    quads, pts, h = _straight_road_near(0.0, half=12.0)
    del quads[4:7]                                                        # z 40..70 bare across the road
    pts5 = [(0.0, float(z)) for z in range(0, 200, 5)]
    gaps = coverage_gaps(quads, len(quads), pts5)
    filled, n_tarmac, report = fill_coverage(quads, len(quads), None, pts5, h, gaps, spacing=5.0)
    fillers = [q for q in filled[:n_tarmac] if q not in quads]
    assert report["fillers"] == len(fillers) >= 3
    for f in fillers:
        xs = sorted(c[0] for c in f.corners)
        assert xs[0] >= -10.0 - FILLER_MARGIN - 1e-6 and xs[-1] <= 10.0 + FILLER_MARGIN + 1e-6
    spans = sorted((min(c[2] for c in f.corners), max(c[2] for c in f.corners)) for f in fillers)
    for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
        assert b0 == pytest.approx(a1, abs=1e-6), spans                   # edge to edge, no overlap


def test_alpines_race_line_has_few_disagreeing_surfaces(saturn_cue, romset_zip):
    """Phase 22j (Pascal, rec70: the pitch see-saws +-1.5-3 degrees over Alpine's dark bend): along the race line a wheel
    lay on two tarmac quads whose TGP heights differed by more than 0.08 for 788 units of the lap (the 4-unit sideways
    growth, grown slices and wide fillers); the game's suspension rings on each flip. Now under 160 units."""
    import math
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.collision import _point_in_xz, saturn_collision, tgp_height
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == "ALPINE")
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        col, _ = saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)
        cl = centreline(lap)
    tarmac = col.quads[:col.n_tarmac]
    grid = {}
    for i, q in enumerate(tarmac):
        xs = [c[0] for c in q.corners]; zs = [c[2] for c in q.corners]
        for gx in range(int(min(xs) // 16), int(max(xs) // 16) + 1):
            for gz in range(int(min(zs) // 16), int(max(zs) // 16) + 1):
                grid.setdefault((gx, gz), []).append(i)
    total = 0.0; n = len(cl)
    for k in range(n):
        (ax, az), (bx, bz) = cl[k], cl[(k + 1) % n]
        seg = math.dist((ax, az), (bx, bz)); dx, dz = (bx - ax) / seg, (bz - az) / seg; nx, nz = -dz, dx
        s = 0.0
        while s < seg:
            bad = False
            for lo, la in ((1.4, 0.9), (1.4, -0.9), (-1.4, 0.9), (-1.4, -0.9)):
                x, z = ax + dx * (s + lo) + nx * la, az + dz * (s + lo) + nz * la
                h = [tgp_height(tarmac[i].corners, x, z) for i in grid.get((int(x // 16), int(z // 16)), ()) if _point_in_xz(tarmac[i].corners, x, z)]
                assert h, (k, x, z)                                       # a wheel is always on tarmac on the race line
                if len(h) >= 2 and max(h) - min(h) > 0.08:
                    bad = True
            total += 1.0 if bad else 0.0
            s += 1.0
    assert total < 160, total


def test_verges_under_tarmac_are_dropped(saturn_cue):
    """Where strips of slices run side by side (Big Forest's start straight) one strip's verge lies over the other's
    tarmac: it adds nothing the car can use, costs list words, and competes with the tarmac in the TGP's pick."""
    from vrtools.convert.lap import order_slices
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    col, _ = saturn_collision(sat, height=lambda x, z: 30.0, lap=lap, merge=True)
    tarmac, verges = col.quads[:col.n_tarmac], col.quads[col.n_tarmac:]
    assert verges and not any(any(_inside(t, v.centre[0], v.centre[2]) for t in tarmac) for v in verges)
    assert col.dropped_verges > 0


def test_unreached_slices_get_no_collision(saturn_cue):
    """The oval file carries a 112-slice infield the lap never reaches (coverage 0.8): it must not become tarmac
    the car can drive onto with a borrowed lap position; it stays a grass surface so a car running wide does not
    fall into the void."""
    from vrtools.convert.lap import order_slices
    sat = _saturn_course(saturn_cue, "SPEEDWAY/TRCKSPEE")
    lap = order_slices(sat, min_coverage=0.8)
    col, _ = saturn_collision(sat, lambda x, z: 0.0, lap=lap, merge=True)
    reached = set(lap.order)
    infield = [s for s in sat.segments if s.corners() is not None and s.index not in reached]
    assert len(infield) > 100
    from vrtools.convert.geometry import to_arcade
    from vrtools.arcade.tgp import SURFACE_TARMAC
    tarmac = col.quads[:col.n_tarmac]
    covered = 0
    for s in infield:
        cx, cz = s.centre
        x, _, z = to_arcade(cx, 0.0, cz)
        assert not any(_inside(q, x, z) for q in tarmac), s.index
        covered += any(_inside(q, x, z) for q in col.quads[col.n_tarmac:])
    assert covered > 0.9 * len(infield)                                                   # grass, not void
    assert col.n_tarmac + col.merged == len(reached) and col.surface.count(SURFACE_TARMAC) == col.n_tarmac


def test_merge_keeps_the_lap_ends_single(saturn_cue):
    """Phase 10: an opponent's line cursor and its road point (from the lap-position quad) must cross the start line
    together (formats §15), so the three slices at each end of the lap are never fused: their quads are the bare
    per-slice quads, in place, while the middle still merges."""
    from vrtools.convert.collision import MERGE_KEEP_ENDS
    from vrtools.convert.lap import order_slices
    assert MERGE_KEEP_ENDS == 3
    for name in ("BIGFORES/TRCKBIGF", "SURFER00/TRCKSURF"):                       # a plain lap and one built from triangles and slivers
        sat = _saturn_course(saturn_cue, name); lap = order_slices(sat)
        h = lambda x, z: 0.0
        plain, _ = saturn_collision(sat, h, lap=lap)
        merged, _ = saturn_collision(sat, h, lap=lap, merge=True)
        assert merged.merged > 0
        np_, nm = plain.n_tarmac, merged.n_tarmac
        assert [q.corners for q in merged.quads[:3]] == [q.corners for q in plain.quads[:3]]
        assert [q.corners for q in merged.quads[nm - 3:nm]] == [q.corners for q in plain.quads[np_ - 3:np_]]


_COLS: dict = {}


def _all_course_collisions(saturn_cue):
    """(collision, lap, centreline) of the seven converted courses as the build makes them, once per session."""
    import os
    from pathlib import Path
    from vrtools.arcade.romset import RomSet
    import vrtools.arcade.tencourse as tc
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, profile_height, road_profile
    if not _COLS:
        rs = RomSet.from_zip(Path(os.environ["VR_ROMDIR"]) / "vr.zip")
        for plan in tc.COURSES:
            sat = tc.load_saturn_course(saturn_cue, plan.path)
            gc = COURSE_OF_TEMPLATE[plan.template]
            pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
            with placed(pl.angle, pl.tx, pl.tz):
                lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
                hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)   # as the build
                col, _ = saturn_collision(sat, hfn, lap=lap, merge=True)
                _COLS[plan.name] = (col, lap, centreline(lap, spacing=10.0), hfn)
    return _COLS


def test_ai_lines_run_on_tarmac_on_every_course(saturn_cue):
    """Phase 11: an opponent on verge stops for good (Metropolis car 7 at road points 45–47, 7 units off the
    centreline, where no tarmac quad reached its AI line). Every point of every AI line (the centreline at the
    arcade's lateral offsets) and the road's width ±10 must lie inside a tarmac quad whose road point is near."""
    from vrtools.convert.collision import COVERAGE_HALF_WIDTH, coverage_gaps, fill_coverage
    from vrtools.convert.road import AI_OFFSETS
    assert COVERAGE_HALF_WIDTH >= max(abs(o) for o in AI_OFFSETS)
    before = {}
    for name, (col, lap, cl, hfn) in _all_course_collisions(saturn_cue).items():
        gaps = coverage_gaps(col.quads, col.n_tarmac, cl)
        before[name] = len(gaps)
        quads, n_tarmac, report = fill_coverage(col.quads, col.n_tarmac, lap, cl, hfn, gaps)
        assert coverage_gaps(quads, n_tarmac, cl) == [], (name, report)
        assert report["gaps"] == len(gaps) and report["grown"] + report["fillers"] >= (1 if gaps else 0)
    assert before["METROPOLIS"] > 0 and before["PACIFIC COAST"] > 0, before
    assert any(g.point in (45, 46, 47) and g.lateral >= 6 for g in coverage_gaps(*[(c.quads, c.n_tarmac, cl) for c, _, cl, _ in [_all_course_collisions(saturn_cue)["METROPOLIS"]]][0]))


def test_fillers_stay_with_their_slice(saturn_cue):
    """A grown or filler quad covers its gap from the road there: its centre within 40 units of the gap and its
    lap arc within one slice of the gap's point, never bridging to another part of the road."""
    import math
    from vrtools.convert.collision import coverage_gaps, fill_coverage
    from vrtools.convert.lap import arc_of
    col, lap, cl, hfn = _all_course_collisions(saturn_cue)["METROPOLIS"]
    gaps = coverage_gaps(col.quads, col.n_tarmac, cl)
    quads, n_tarmac, report = fill_coverage(col.quads, col.n_tarmac, lap, cl, hfn, gaps)
    new = [q for q in quads[:n_tarmac] if q.corners not in {o.corners for o in col.quads[:col.n_tarmac]}]
    assert new, report
    for q in new:
        gap = min(gaps, key=lambda g: math.dist((g.x, g.z), (q.centre[0], q.centre[2])))
        assert math.dist((gap.x, gap.z), (q.centre[0], q.centre[2])) < 40.0, (gap, q.centre)
        da = (arc_of(lap, q.centre[0], q.centre[2]) - arc_of(lap, gap.x, gap.z) + lap.length / 2) % lap.length - lap.length / 2
        assert abs(da) < 60.0, (gap, da)


def test_verges_sit_level_with_the_tarmac():
    """Phase 24 (Pascal rec141: "the car seems to bank left/right when going from the road to grass"): the run-off's
    inner corners sit at the tarmac edge's height, as the originals' run-off does. Phase 11 had set the verges
    VERGE_SINK 0.3 away from zero (the TGP keeps the containing quad whose ABSOLUTE height is nearest the car's and
    breaks ties for the later list entry; verges overlapping the tarmac parked whole fields): a car with one side on
    the grass leaned 11.5 degrees. The verges no longer overlap the tarmac (measured edges, Phase 11's own fix), and
    all seven races pass with the offset at 0.05 and at 0."""
    import math
    from vrtools.convert.collision import VERGE_SINK
    assert VERGE_SINK == 0.0
    sat, lap = _square_lap()
    col, _ = saturn_collision(sat, height=lambda x, z: 0.1 * x + 0.05 * z, lap=lap)
    n = col.n_tarmac
    h = lambda x, z: 0.1 * x + 0.05 * z
    for q in col.quads[:n]:                                                      # tarmac corners sit on the height function
        assert all(c[1] == pytest.approx(h(c[0], c[2]), abs=1e-6) for c in q.corners)
    for v in col.quads[n:]:
        fl, fr, br, bl = v.corners
        assert fl[1] == pytest.approx(fr[1], abs=1e-6) and bl[1] == pytest.approx(br[1], abs=1e-6)      # straight across (Phase 8)
        away = lambda y: y + VERGE_SINK if y >= 0 else y - VERGE_SINK
        inner = min(v.corners, key=lambda c: abs(c[1] - away(h(c[0], c[2]))))                              # the inner corners ...
        assert inner[1] == pytest.approx(away(h(inner[0], inner[2])), abs=1e-6), (inner, h(inner[0], inner[2]))   # ... sit the offset away from zero
        assert abs(inner[1]) > abs(h(inner[0], inner[2])) - 1e-9                                            # never nearer zero than the tarmac


_COVERED: dict = {}
_WATER: dict = {}


def _all_covered_collisions(saturn_cue):
    """(collision, lap, centreline, height) of the seven courses with the coverage fill and the road verges (as the build)."""
    import os
    from pathlib import Path
    from vrtools.arcade.romset import RomSet
    import vrtools.arcade.tencourse as tc
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, profile_height, road_profile
    if not _COVERED:
        rs = RomSet.from_zip(Path(os.environ["VR_ROMDIR"]) / "vr.zip")
        for plan in tc.COURSES:
            sat = tc.load_saturn_course(saturn_cue, plan.path)
            gc = COURSE_OF_TEMPLATE[plan.template]
            pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
            with placed(pl.angle, pl.tx, pl.tz):
                lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
                hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)   # as the build
                col, _ = saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)
                _COVERED[plan.name] = (col, lap, centreline(lap, spacing=10.0), hfn)
                from vrtools.convert.collision import is_water
                from vrtools.convert.geometry import course_quads
                _WATER[plan.name] = [q for q in course_quads(sat, groups=(0, 1)) if is_water(q.rgb)]   # Phase 19
                from vrtools.convert.collision import mesh_heights
                from vrtools.convert.profile import _ground_quads
                _MESH[plan.name] = mesh_heights(_ground_quads(sat))       # the drawn road, in arcade space (placed)
                _DRAWN[plan.name] = mesh_heights([q for q in course_quads(sat, groups=(0, 1)) if not is_water(q.rgb)])   # Phase 22o:
    return _COVERED                                                        # the drawn ground the verges follow (placed)


_MESH: dict = {}
_DRAWN: dict = {}


def _plane_h(q, x, z):
    """The TGP's height of quad q at (x, z) (Phase 22a: two triangles on the 0-2 diagonal, `collision.tgp_height`)."""
    from vrtools.convert.collision import tgp_height
    return tgp_height(q.corners, x, z)


RUN_OFF_UNCOVERED_MAX = {"METROPOLIS": 0.03, "SURFERS OVAL": 0.045}
# Phase 22a (measured, 103 of 3650): points 38-41, where the near wall beside the other deck is dropped and the revert
# fallback is off (BARRIER_RETRIES 0: Pascal, "keep in mind to not disable the rock collision"); Pascal drove it: "look
# good no issue at all"; the Oval 157 of 3870: its beach, 101-103 (Pascal: no wall there, the off-course reset)


def test_verges_never_overlap_the_tarmac_on_every_course(saturn_cue):
    """Phase 11: the originals' quads do not overlap (formats, TGP §5: Big Forest and Acropolis 0 road samples under both
    a verge and a tarmac quad). Ours did — a slice's verge is built off the quad's own side, which on a triangle slice
    is a diagonal across the road (Surfers Road: 37 % of the road's ±10 band under a verge, at the centreline too) —
    and the TGP's pick keeps a car that once touched a verge on the verge wherever the two overlap (nearest height to
    the car's own): whole fields parked at the road's height + VERGE_SINK. The verges are built from the road's
    measured edge after the coverage fill. Phase 17: the grass starts GRASS_OVERLAP inside the run's narrowest edge
    (never inside GRASS_FLOOR) so no seam opens, and may lie under the road's outer band; no AI line (lateral −8..8) is
    ever under both a verge and a tarmac quad of the same height; the run-off beside the road (lateral 12..40) stays
    under some quad."""
    import math
    from vrtools.convert.collision import _bboxes, _line_distance
    from vrtools.convert.collision import _point_in_xz as _pin             # with the 1e-9 tolerance: samples on the shared
    def inner_edge_distance(v, x, z, cx, cz):                                # line of two steps are inside both
        c = v.corners
        edges = [(c[k], c[(k + 1) % 4]) for k in range(4)]
        inner = min(edges, key=lambda e: math.dist(((e[0][0] + e[1][0]) / 2, (e[0][2] + e[1][2]) / 2), (cx, cz)))
        return _line_distance((x, 0.0, z), inner[0], inner[1])
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        tarmac, verges = col.quads[:col.n_tarmac], col.quads[col.n_tarmac:]
        tb, vb = _bboxes(tarmac), _bboxes(verges)
        inside = lambda x, z, qs, bs: [q for q, b in zip(qs, bs) if b[0] <= x <= b[1] and b[2] <= z <= b[3] and _pin(q.corners, x, z)]
        walls = [q for i, q in enumerate(col.quads) if col.surface[i] == 5]; wb = _bboxes(walls)
        def behind_a_wall(x, z, rx, rz, lat):
            step = 0.5 if lat > 0 else -0.5
            return any(inside(x + k * step * rx, z + k * step * rz, walls, wb) for k in range(1, int(abs(lat) / 0.5)))
        n = len(cl); both = []; off = []; total = 0
        for p, (x, z) in enumerate(cl):
            (ax, az), (bx, bz) = cl[p - 1], cl[(p + 1) % n]
            d = math.hypot(bx - ax, bz - az) or 1.0
            rx, rz = (bz - az) / d, -(bx - ax) / d
            for lat in range(-10, 11):
                sx, sz = x + lat * rx, z + lat * rz
                vs = inside(sx, sz, verges, vb)
                over = [(v, t) for v in vs for t in inside(sx, sz, tarmac, tb) if abs(_plane_h(v, sx, sz) - _plane_h(t, sx, sz)) < 1.0]
                reach = 8 * (col.lanes[p][1 if lat > 0 else 0] if col.lanes else 1.0)   # Phase 22c: the lines the AI drives
                if over and abs(lat) <= reach:                                 # an AI line under grass and tarmac (Phase 17: the
                    both.append((p, lat))                                      # grass may lie under the road's outer band)
            for lat in (-40, -30, -20, -16, -12, 12, 16, 20, 30, 40):
                sx, sz = x + lat * rx, z + lat * rz
                total += 1
                if not inside(sx, sz, verges, vb) and not inside(sx, sz, tarmac, tb) and not behind_a_wall(x, z, rx, rz, lat):
                    off.append((p, lat))                                   # (Phase 19: beyond a shoreline wall is water)
        assert not both, (name, len(both), both[:8])
        assert len(off) / total <= RUN_OFF_UNCOVERED_MAX.get(name, 0.02), (name, len(off), total, off[:10], col.coverage, len(col.quads))
        from vrtools.convert.collision import VERGE_SINK, _away_from_zero
        for v in verges[:col.coverage["verges"]]:                               # the road verges (the oval's infield grass follows):
            if any(_line_distance(v.corners[(k + 1) % 4], v.corners[k], v.corners[(k + 2) % 4]) < 1e-6 for k in range(4)):
                continue                                                         # a dart's hull (Phase 17): a triangle and a mid-edge corner
                                                                                 # each corner at the collision's height there (Phase 22a:
            for c in v.corners:                                                  # no longer flat across), or, past a jump onto another
                own = _away_from_zero(hfn(c[0], c[2]), VERGE_SINK)               # deck, flat across as before
                flat = any(o is not c and c[1] == pytest.approx(o[1], abs=1e-6) for o in v.corners)
                assert c[1] == pytest.approx(own, abs=0.05) or flat, (name, v)


def _straight_road_near(x: float, half: float = 5.0, length: float = 200.0, step: float = 10.0):
    """A flat tarmac strip along +z at `x`, `2 * half` wide, in lap order: quads, centreline points and a height function."""
    pts = [(x, z) for z in range(0, int(length), int(step))]
    quads = [_quad([(x - half, 0.0, z), (x + half, 0.0, z), (x + half, 0.0, z + step), (x - half, 0.0, z + step)]) for _, z in pts]
    return quads, pts, (lambda px, pz: 0.0)


def test_grass_meets_a_narrowing_road_without_a_seam():
    """Phase 17 (recon §2 A): a grass run's inner line lay at the run's WIDEST measured edge, so where the road narrowed
    inside the run a strip between the tarmac's real edge and the grass had no quad (146-405 such runs per course). The
    grass now starts GRASS_OVERLAP inside each end's measured edge (never inside GRASS_FLOOR, the AI lines' reach): right
    of a road narrowed from half-width 12 to 10 for three quads, every sample from the tarmac's edge out 10 units lies in
    a tarmac or grass quad, and the grass reaches no further in than the narrow edge less the scan step and the overlap."""
    from vrtools.convert.collision import GRASS_OVERLAP, VERGE_GRASS, VERGE_SCAN_STEP, _point_in_xz, road_verges
    quads, pts, h = _straight_road_near(0.0, half=12.0)
    for i in (6, 7, 8):                                                   # z 60..90: the right edge at 10
        c = list(quads[i].corners)
        quads[i] = _quad([(10.0 if p[0] > 0 else p[0], p[1], p[2]) for p in c])
    grass = road_verges(quads, pts, h, width=VERGE_GRASS)
    right = [g for g in grass if min(p[0] for p in g.corners) > 0.0]
    holes = []
    for k2 in range(2, 2 * 14):                                           # points 1..14 and their half-points (an open road: the run
                                                                          # that wraps from its last point to its first is not a road)
        z = k2 * 5.0
        edge = 10.0 if 60.0 <= z <= 90.0 else 12.0
        x = edge
        while x <= edge + 10.0:
            if not any(_point_in_xz(q.corners, x, z) for q in quads + right):
                holes.append((z, x))
            x += 0.25
    assert not holes, holes[:10]
    inner = min(p[0] for g in right for p in g.corners)
    assert inner >= 12.0 - VERGE_SCAN_STEP - GRASS_OVERLAP - (12.0 - 10.0) - 1e-6, inner


def test_a_grass_run_ends_where_the_roads_slope_changes(monkeypatch):
    """Phase 25 (Pascal, rec147 Alpine: "going in the grass on the right of the track ... an angle or difference between
    the road and grass", one spot): a grass run spans up to six centreline points as one quad, its inner corners at the
    road's height at its two ends. Where the road's slope changes inside the run the quad's straight inner edge left
    the road's: at Alpine's point 238 (the road steepens from 0.45 to 1.15 a point) the grass lay 0.85 under the
    tarmac's edge and the car leaned 25 degrees with its right wheels on it. A run now ends where the road's height at
    its edge leaves the straight line between the run's ends by more than GRASS_CHORD_TOL (Alpine: 9-12 more quads;
    edges with a step over 0.5: 20 -> 4)."""
    import vrtools.convert.collision as C
    from vrtools.convert.collision import VERGE_GRASS, _point_in_xz, road_verges, tgp_height
    h = lambda px, pz: -0.115 * max(0.0, pz - 80.0)                       # level, then falling from z 80
    pts = [(0.0, float(z)) for z in range(0, 200, 10)]
    quads = [_quad([(-12.0, h(0, z), z), (12.0, h(0, z), z), (12.0, h(0, z + 10), z + 10.0), (-12.0, h(0, z + 10), z + 10.0)]) for _, z in pts]

    def worst():
        right = [g for g in road_verges(quads, pts, h, width=VERGE_GRASS) if min(c[0] for c in g.corners) > 0.0]
        gaps = []
        for g in right:
            x = min(c[0] for c in g.corners) + 0.05                      # just inside the quad's inner edge
            for z in [10.0 + 2.5 * i for i in range(64)]:                # points 1..17 (an open road's wrapping run is no road)
                if _point_in_xz(g.corners, x, z):
                    gaps.append(abs(tgp_height(g.corners, x, z) - h(x, z)))
        return max(gaps), len(right)
    step, count = worst()
    assert 0.1 <= C.GRASS_CHORD_TOL <= 0.2 and step <= C.GRASS_CHORD_TOL + 1e-6, step
    monkeypatch.setattr(C, "GRASS_CHORD_TOL", float("inf"))               # without the rule: a step at the kink
    old_step, old_count = worst()
    assert old_step > 0.5 and count > old_count, (old_step, old_count, count)


def test_grass_follows_a_road_that_widens_between_two_points():
    """Phase 17: where the road's edge jumps inside a 10-unit step (a pit or side area beginning: Alpine 325-326, the edge
    12.5 -> 33), a grass inner line at the run's widest edge left a triangle of no quad. The grass's inner line lies at
    the run's narrowest edge (less GRASS_OVERLAP), under the wide part's tarmac: right of a road whose half-width jumps
    from 12 to 30 at z = 63, every sample from the tarmac's edge out 10 units lies in a tarmac or grass quad."""
    from vrtools.convert.collision import VERGE_GRASS, _point_in_xz, road_verges
    quads, pts, h = _straight_road_near(0.0, half=12.0)
    quads[6] = _quad([(-12.0, 0.0, 60.0), (12.0, 0.0, 60.0), (12.0, 0.0, 63.0), (-12.0, 0.0, 63.0)])
    quads.insert(7, _quad([(-12.0, 0.0, 63.0), (30.0, 0.0, 63.0), (30.0, 0.0, 70.0), (-12.0, 0.0, 70.0)]))
    for i in range(8, len(quads)):                                        # wide from z = 63 on
        quads[i] = _quad([(30.0 if c[0] > 0 else c[0], c[1], c[2]) for c in quads[i].corners])
    grass = road_verges(quads, pts, h, width=VERGE_GRASS)
    right = [g for g in grass if min(c[0] for c in g.corners) > 0.0]
    holes = []
    for z in [60.0 + 0.5 * i for i in range(1, 20)]:                       # inside the step 60..70
        edge = 12.0 if z < 63.0 else 30.0
        x = edge
        while x <= edge + 10.0:
            if not any(_point_in_xz(q.corners, x, z) for q in quads + right):
                holes.append((z, x))
            x += 0.5
    assert not holes, holes[:10]


def test_coverage_fills_a_hole_between_road_points():
    """Phase 17 (recon §2 B): the coverage fill sampled the road only at the 10-unit points, so a hole between two
    points was never seen (Pacific Coast 318.5: 15.5 units at the centreline). Sampled every COVERAGE_FILL_SPACING (5)
    units, a 4 x 4 hole centred between two points is found and filled."""
    from vrtools.convert.collision import COVERAGE_FILL_SPACING, _point_in_xz, coverage_gaps, fill_coverage
    assert COVERAGE_FILL_SPACING == 5.0
    quads, pts10, h = _straight_road_near(0.0, half=12.0)
    hole = quads[4]                                                       # z 40..50: lateral -2..2 bare from z 43 to 47
    quads[4:5] = [_quad([(-12.0, 0.0, 40.0), (-2.0, 0.0, 40.0), (-2.0, 0.0, 50.0), (-12.0, 0.0, 50.0)]),
                  _quad([(2.0, 0.0, 40.0), (12.0, 0.0, 40.0), (12.0, 0.0, 50.0), (2.0, 0.0, 50.0)]),
                  _quad([(-2.0, 0.0, 40.0), (2.0, 0.0, 40.0), (2.0, 0.0, 43.0), (-2.0, 0.0, 43.0)]),
                  _quad([(-2.0, 0.0, 47.0), (2.0, 0.0, 47.0), (2.0, 0.0, 50.0), (-2.0, 0.0, 50.0)])]
    assert hole is not None
    assert not [g for g in coverage_gaps(quads, len(quads), pts10) if 41.0 < g.z < 49.0]     # the 10-unit points miss it
    pts5 = [(0.0, float(z)) for z in range(0, 200, 5)]
    gaps = coverage_gaps(quads, len(quads), pts5)
    assert any(43.0 < g.z < 47.0 for g in gaps), gaps
    filled, n_tarmac, report = fill_coverage(quads, len(quads), None, pts5, h, gaps, spacing=COVERAGE_FILL_SPACING)
    bare = [(x, z) for z in (44.0, 45.0, 46.0) for x in (-1.5, -0.5, 0.5, 1.5)
            if not any(_point_in_xz(q.corners, x, z) for q in filled[:n_tarmac])]
    assert not bare, (bare, report)


def test_a_grown_quad_keeps_its_own_plane():
    """Phase 17: the coverage fill now reaches the measured edge, and a quad grown out to it put a corner over Metropolis's
    other deck, whose height the height function returned: the quad tilted 3-5 units off the drawn road at its centre.
    A grown corner keeps the quad's own plane."""
    from vrtools.convert.collision import coverage_gaps, fill_coverage
    quads, pts, _ = _straight_road_near(0.0, half=5.0)
    two_decks = lambda x, z: 0.0 if x < 6.0 else -13.0                 # another deck from x = 6 on
    gaps = coverage_gaps(quads, len(quads), pts, half_width=7.0)
    assert gaps
    filled, n_tarmac, report = fill_coverage(quads, len(quads), None, pts, two_decks, gaps)
    assert report["grown"] > 0, report
    assert all(c[1] == pytest.approx(0.0, abs=1e-6) for q in filled[:n_tarmac] for c in q.corners), report


def test_road_edges_bridge_a_side_strip():
    """Phase 17 (recon §2 C): a side strip of tarmac beyond a gap of 3-8 units (Metropolis's start area, Amazon's wide
    stretches) ended the measured road at the gap, so neither the coverage fill nor the grass reached the gap. The edge
    scan now bridges holes narrower than VERGE_EDGE_GAP (8): a 10-wide road with a 6-wide strip 5 units beyond its right
    edge measures its right edge at the strip's outer edge."""
    from vrtools.convert.collision import VERGE_EDGE_GAP, road_edges
    assert VERGE_EDGE_GAP == 8.0
    quads, pts, h = _straight_road_near(0.0, half=5.0)
    strip = [_quad([(10.0, 0.0, z), (16.0, 0.0, z), (16.0, 0.0, z + 10.0), (10.0, 0.0, z + 10.0)]) for _, z in pts]
    edges = road_edges(quads + strip, pts, h)
    for left, right in edges[1:-1]:
        assert 15.5 <= right <= 16.5, edges
        assert 4.5 <= left <= 5.5, edges


def test_verge_corners_never_leave_the_collision_map():
    """The collision map covers -1024..1023; wide verges on an outer course reached past it and the build failed with
    'quad leaves the collision map'. Outer corners are clamped to ±MAP_LIMIT; inner corners (on the tarmac edge) are not moved."""
    from vrtools.convert.collision import MAP_LIMIT, VERGE_GRASS, WALL_WIDTH, road_verges
    tarmac, pts, hfun = _straight_road_near(x=990.0)
    verges = road_verges(tarmac, pts, hfun, width=VERGE_GRASS + WALL_WIDTH)
    assert MAP_LIMIT == 1020.0
    assert verges
    for v in verges:
        for cx, _, cz in v.corners:
            assert -MAP_LIMIT <= cx <= MAP_LIMIT and -MAP_LIMIT <= cz <= MAP_LIMIT
    outer = [c for v in verges for c in v.corners if c[0] > 1000]
    assert outer and all(c[0] == pytest.approx(MAP_LIMIT) for c in outer)        # the east verge was clamped, not dropped


def _hairpin(radius: float = 15.0, half: float = 5.0, n: int = 12):
    """A U-turn: a straight in, a semicircle of `radius` about the origin, a straight out; tarmac quads `2 * half` wide."""
    import math
    pts = [(-radius, z) for z in (-40.0, -30.0, -20.0, -10.0)]
    pts += [(-radius * math.cos(math.pi * k / n), radius * math.sin(math.pi * k / n)) for k in range(0, n + 1)]
    pts += [(radius, z) for z in (-10.0, -20.0, -30.0, -40.0)]
    quads = []
    for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
        dx, dz = x1 - x0, z1 - z0; d = math.hypot(dx, dz); rx, rz = dz / d, -dx / d
        quads.append(_quad([(x0 - half * rx, 0.0, z0 - half * rz), (x0 + half * rx, 0.0, z0 + half * rz),
                            (x1 + half * rx, 0.0, z1 + half * rz), (x1 - half * rx, 0.0, z1 - half * rz)]))
    return quads, pts, (lambda px, pz: 0.0)


def test_a_wide_verge_inside_a_hairpin_narrows_instead_of_covering_the_road():
    """Inside a bend tighter than the verge is wide, a step's two laterals cross and the convex-hull swap spreads the
    quad over the road ahead (Metropolis point 272 at 80 units: the whole -10..10 band under a verge at the road's
    height). Such a step is built at the narrow width (MARGIN) instead; the straights keep the full width."""
    from vrtools.convert.collision import MARGIN, road_verges
    tarmac, pts, hfun = _hairpin(radius=15.0)
    verges = road_verges(tarmac, pts, hfun, width=80.0)
    assert MARGIN == 40.0
    def extent(v):                                                   # inner -> outer corner, across the verge
        c = v.corners
        return math.dist((c[0][0], c[0][2]), (c[1][0], c[1][2]))
    def inside_the_bend(v):                                          # its inner corners on the arc, on the side of the arc's centre
        c = v.corners
        inner = [q for q in c if math.hypot(q[0], q[2]) < 12.0]
        return len(inner) >= 2 and all(q[2] > 1.0 for q in inner)
    bend = [v for v in verges if inside_the_bend(v)]
    assert bend, "no verge found inside the bend"
    assert all(extent(v) <= MARGIN + 0.5 for v in bend), sorted(extent(v) for v in bend)
    assert any(extent(v) >= 79.0 for v in verges)                    # the straights keep the full width


def test_a_verge_never_covers_a_road_point():
    """Where the road crosses itself (Metropolis's decks) or two legs run close (a hairpin's straights), an 80-unit verge
    of one leg reaches the other leg's road: Metropolis point 272 had its whole -10..10 band under the upper deck's
    verge. A verge that contains any centreline point is dropped (on its own leg a verge starts at the road's edge, so
    only another leg's road can be inside it)."""
    from vrtools.convert.collision import _point_in_xz, road_verges
    tarmac, pts, hfun = _hairpin(radius=15.0)
    verges = road_verges(tarmac, pts, hfun, width=80.0)
    covered = [(round(x, 1), round(z, 1)) for x, z in pts if any(_point_in_xz(v.corners, x, z) for v in verges)]
    assert not covered, covered
    assert len(verges) >= len(pts)                                    # the outside of the bend and the straights' far sides remain



def test_walls_lie_beyond_the_grass_on_a_straight():
    """Phase 16 (recon §4): the run-off ends in a wall — surface 5, the kind the game stops a car on. On a straight road
    the grass verge runs VERGE_GRASS (30) units past the road's edge and the wall strip WALL_WIDTH (12) beyond it (with no
    shore information, a wall starts SHORE_WALL_BACK inside the grass's width, as since Phase 19)."""
    from vrtools.convert.collision import SHORE_WALL_BACK, VERGE_GRASS, VERGE_SCAN_STEP, WALL_WIDTH, road_verges
    assert (VERGE_GRASS, WALL_WIDTH) == (30.0, 12.0)                    # Phase 22a: 6 -> 12 (a fast car skipped the strip)
    tarmac, pts, hfun = _straight_road_near(x=0.0, half=5.0)
    grass = road_verges(tarmac, pts, hfun, width=VERGE_GRASS)
    walls = road_verges(tarmac, pts, hfun, width=WALL_WIDTH, inset=VERGE_GRASS)
    edge = 5.0 - VERGE_SCAN_STEP
    assert grass and walls
    assert all(abs(c[0]) <= edge + VERGE_GRASS + 0.6 for v in grass for c in v.corners)
    for v in walls:
        lat = sorted(abs(c[0]) for c in v.corners)
        assert lat[0] == pytest.approx(edge + VERGE_GRASS - SHORE_WALL_BACK, abs=0.6) and lat[-1] == pytest.approx(edge + VERGE_GRASS + WALL_WIDTH, abs=0.6)


# Phase 19 review: wall samples (5 x 5 per quad) on tarmac of the wall's own level, measured after the fix: walls at the
# run-off's edge meeting side-area tarmac strips 40-64 units out, and samples beside Pacific Coast's jagged side-area
# shores (308-318, 384: at most 1 unit into the tarmac, the edge scan's resolution); before the fix the shoreline walls
# overlapped their road (Pacific 55 walls, up to 4 units). The Surfers courses' side areas reach past the edge scan's
# 40.5 units beside their shores (Oval 10-16, Road 141-145): the shore's eroded insets cut that wall into more quads
# Phase 22n: the Oval 70 -> 75 (71 measured: 67 on main; the far-side wall floor moves out with the shifted lines and the
# paddock's walls along the start straight's left, points 9-24 and 371-374, re-arranged by four samples)
OVER_TARMAC_MAX: dict[str, int] = {"ALPINE": 31, "AMAZON FALLS": 18, "DIABLO CANYON": 37, "METROPOLIS": 60, "PACIFIC COAST": 29,
                                   "SURFERS OVAL": 75, "SURFERS ROAD": 50}   # Road 31 -> 37: re-measured with the TGP's two-triangle rule
# Phase 22p: Metropolis 49 -> 60 (54 measured): the wall strip's inner line is anchored at the grass's inner line since the
# 22o review's second round, so the walls over a slice's last 1-3 units past the measured edge (points 16, 98, 133 L) sit
# within the test's 1.0 of the tarmac's height; the overlap itself is as before (clip_at_walls' guard keeps those slices).
# Phase 22l: Oval 36 -> 70 and Road 37 -> 50: their laps now start 50-60 units after the START gate, with the apron (kept
# as tarmac) beside the start straight under the run-off walls over a longer stretch (a modelling follow-up: the apron is not road)
# Phase 22k: Oval 29 -> 36: the walls left of its start straight (points 7-46, 27-42 out) lie a unit further out at the drawn
# face and overlap the Saturn's infield apron, kept as tarmac, by a few more samples (the TGP prefers the tarmac there)
# Phase 22c: Amazon 16 -> 18 (walls at the ground's height, WALL_STEP 0: a wall over a tarmac quad no cut could take is now
# at its level; Pascal drove Amazon on p22play28 without noticing; a follow-up)
# 22a review: Road 12 -> 13 (the fill guard fix). Phase 22a (Pascal's wall bug): the walls at the drawn barriers (was
# 0/4/8/7/6/19/13): where the Saturn's road slice reaches past a drawn cliff or fence, a barrier wall run (edges up to
# BARRIER_EDGE_TOL apart: the TGP budget's floor) lies on the slice's outer band at some samples, 12.5+ units out


def test_walls_stay_clear_of_every_racing_line_on_every_course(saturn_cue):
    """Phase 16: every converted course carries wall quads (surface 5) at the edge of its run-off; none lies over tarmac,
    and no point of the centreline or the seven AI lines (offsets AI_OFFSETS) is inside a wall quad or within 3 units of
    one (a wall beside a racing line would make the opponents scrape)."""
    from vrtools.convert.collision import _bboxes, _on_tarmac, _point_in_xz, _segment_distance
    from vrtools.convert.road import AI_OFFSETS
    from vrtools.arcade.tgp import SURFACE_WALL
    assert SURFACE_WALL == 5
    over_counts = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        walls = [q for q, k in zip(col.quads, col.surface) if k == SURFACE_WALL]
        assert walls and col.coverage["walls"] == len(walls), (name, len(walls), col.coverage.get("walls"))
        tarmac = col.quads[:col.n_tarmac]
        assert not [w for w in walls if _on_tarmac(w, tarmac)], name
        tb = _bboxes(tarmac); over = []                          # Phase 19 review: no point of a wall on its own level's tarmac
        for w in walls:
            xs = [p[0] for p in w.corners]; zs = [p[2] for p in w.corners]
            for fx in (0.1, 0.3, 0.5, 0.7, 0.9):
                for fz in (0.1, 0.3, 0.5, 0.7, 0.9):
                    sx, sz = min(xs) + fx * (max(xs) - min(xs)), min(zs) + fz * (max(zs) - min(zs))
                    if _point_in_xz(w.corners, sx, sz) and any(b[0] <= sx <= b[1] and b[2] <= sz <= b[3] and _point_in_xz(t.corners, sx, sz)
                                                               and abs(_plane_h(t, sx, sz) - _plane_h(w, sx, sz)) < 1.0 for t, b in zip(tarmac, tb)):
                        over.append((round(sx, 1), round(sz, 1)))
        if len(over) > OVER_TARMAC_MAX.get(name, 0):
            over_counts[name] = (len(over), over[:4])
        boxes = _bboxes(walls); n = len(cl); near = []
        for k, (x, z) in enumerate(cl):
          for f in (0.0, 0.25, 0.5, 0.75):                        # Phase 19 review: between the 10-unit points too
            (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
            d = math.hypot(bx - ax, bz - az) or 1.0
            rx, rz = (bz - az) / d, -(bx - ax) / d
            (nx, nz) = cl[(k + 1) % n]
            lanes = col.lanes[k] if col.lanes else (1.0, 1.0)          # Phase 22c: the AI drives the narrowed lines
            for off in (0.0,) + tuple(AI_OFFSETS):
                off = off * (lanes[1] if off > 0 else lanes[0])
                px, pz = x + f * (nx - x) + off * rx, z + f * (nz - z) + off * rz
                for w, b in zip(walls, boxes):
                    if b[0] - 3 <= px <= b[1] + 3 and b[2] - 3 <= pz <= b[3] + 3:
                        c = w.corners
                        dist = 0.0 if _point_in_xz(c, px, pz) else min(_segment_distance((px, pz), c[i], c[(i + 1) % 4]) for i in range(4))
                        if dist < 3.0:
                            near.append((k, off, round(dist, 1)))
        assert not near, (name, len(near), near[:6])
    assert not over_counts, "\n".join(f"{k}: {v}" for k, v in over_counts.items())



def _plane_height(q, x, z):
    from vrtools.convert.collision import tgp_height
    return tgp_height(q.corners, x, z)


def test_collision_follows_the_drawn_road_on_every_course(saturn_cue):
    """Phase 16 review (Critical): the collision under the car's centreline must match the drawn Saturn road (the ground
    mesh, nearest deck): more than 2 units off on at most 1.5 % of the points, more than 1 unit on at most 6 %. arc_height
    placed centreline point k at arc k x 10 although the smoothed centreline is shorter than the lap, and rode up to 4-5
    units off the drawn road on Diablo Canyon (53 of 384 points over 2) and Metropolis (44 of 332)."""
    from vrtools.convert.collision import _point_in_xz
    cols = _all_covered_collisions(saturn_cue)
    for name, (col, lap, cl, hfn) in cols.items():
        mesh = _MESH[name]; tarmac = col.quads[:col.n_tarmac]
        off = []
        for x, z in cl:
            under = [q for q in tarmac if _point_in_xz(q.corners, x, z)]
            drawn = mesh(x, z)
            if under and drawn:
                h = min((_plane_height(q, x, z) for q in under), key=lambda v: min(abs(v - d) for d in drawn))
                off.append(min(abs(h - d) for d in drawn))
        n = len(off)
        over2, over1 = sum(1 for o in off if o > 2.0), sum(1 for o in off if o > 1.0)
        assert over2 <= 0.015 * n and over1 <= 0.06 * n, (name, over2, over1, n, round(max(off), 2))


def test_the_start_band_leaves_no_hole_on_every_course(saturn_cue, monkeypatch):
    """Phase 17: the start-line band cuts the tarmac back across the 12 units before the line and lays one quad there,
    as wide as the road measured at point 0; where the road is wider before the line the band left the tarmac it cut
    away uncovered (Alpine 14-16 units left, Amazon 13). Every sample within 30 units of point 0 that the tarmac
    covered before the band (as the build calls it) is covered after it."""
    import vrtools.convert.collision as C
    import vrtools.arcade.tencourse as tc
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    seen = []
    real = C.start_line_band
    def spy(tarmac, pts, height, reach=C.START_BAND):
        out = real(tarmac, pts, height, reach)
        seen.append((list(tarmac), out[0], pts))
        return out
    monkeypatch.setattr(C, "start_line_band", spy)
    rs = RomSet.from_zip(Path(os.environ["VR_ROMDIR"]) / "vr.zip")
    bad = {}
    for plan in tc.COURSES:
        sat = tc.load_saturn_course(saturn_cue, plan.path)
        gc = COURSE_OF_TEMPLATE[plan.template]
        pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
            hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
            seen.clear()
            saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)            # as the build
        before, after, pts = seen[-1]
        bb, ba = C._bboxes(before), C._bboxes(after)
        inside = lambda qs, bs, x, z: any(b[0] <= x <= b[1] and b[2] <= z <= b[3] and C._point_in_xz(q.corners, x, z) for q, b in zip(qs, bs))
        o = pts[0]; holes = []
        for i in range(-60, 61):
            for j in range(-60, 61):
                x, z = o[0] + 0.5 * i, o[1] + 0.5 * j
                if inside(before, bb, x, z) and not inside(after, ba, x, z):
                    holes.append((0.5 * i, 0.5 * j))
        if holes:
            bad[plan.name] = (len(holes), holes[:6])
    assert not bad, bad


def test_the_coverage_fill_adds_no_steep_tarmac_on_every_course(saturn_cue, monkeypatch):
    """Phase 17 review (Important): a filler's corner took the height of the slice under it nearest `height`, and where
    `height` answered with Metropolis's other deck the filler spanned both decks (quad 138: corners -6.6 / -24.6, 63
    deg; quad 253: 51 deg) — a car running wide there got its height 8-17 units off the deck. Every quad the fill adds
    or grows (as the build calls it) slopes less than 25 deg between any two corners, or is under 3 units tall with every
    corner within 1.5 of the collision's height (Phase 22a rework: it follows the drawn ground, whose outer banks rise 26
    deg on Diablo; a deck span or a corner pulled off the height is still caught; Diablo's road climbs at up to 16;
    the slices that already span two levels, Amazon's and Metropolis's, are the Saturn's own and not the fill's)."""
    import vrtools.convert.collision as C
    import vrtools.arcade.tencourse as tc
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    seen = []
    real = C.fill_coverage
    def spy(quads, n_tarmac, *a, **k):
        out = real(quads, n_tarmac, *a, **k)
        seen.append(({q.corners for q in quads[:n_tarmac]}, out[0][:out[1]]))
        return out
    monkeypatch.setattr(C, "fill_coverage", spy)
    def slope(q):
        c = q.corners
        return max(math.degrees(math.atan2(abs(c[i][1] - c[j][1]), math.hypot(c[i][0] - c[j][0], c[i][2] - c[j][2])))
                   for i in range(4) for j in range(i + 1, 4) if math.hypot(c[i][0] - c[j][0], c[i][2] - c[j][2]) > 0.5)
    rs = RomSet.from_zip(Path(os.environ["VR_ROMDIR"]) / "vr.zip")
    bad = {}
    for plan in tc.COURSES:
        sat = tc.load_saturn_course(saturn_cue, plan.path)
        gc = COURSE_OF_TEMPLATE[plan.template]
        pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
            hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
            seen.clear()
            saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)
        before, after = seen[-1]
        def defect(q):                                                 # Phase 22a rework: steep AND spanning levels (the
            ys = [c[1] for c in q.corners]                             # deck spans: 13-18 units) or off the collision's own
            off = max(abs(c[1] - hfn(c[0], c[2])) for c in q.corners)  # height (the stale camber cap: 2.9 units); Diablo's
            return max(ys) - min(ys) > 3.0 or off > 1.5                # outer bank gives a 26 deg filler 1.9 units tall
        steep = sorted((round(slope(q), 1), [round(c[1], 1) for c in q.corners]) for q in after
                       if q.corners not in before and slope(q) >= 25.0 and defect(q))
        if steep:
            bad[plan.name] = steep[-4:]
    assert not bad, bad


def test_no_hole_between_the_centreline_and_the_wall_on_every_course(saturn_cue):
    """Phase 17 (recon §2; replaces Phase 16's grass-to-wall test and its tarmac-seam allowance): from every centreline
    point and half-point, on both sides, sampling outward every 0.5 units to the first wall sample (or 80 units), the
    runs of samples under no quad between two quads: none 1 unit or wider starts within 10.5 units of the centreline
    (the AI lines' and the field's band), beyond it at most the per-course count measured at the end of Phase 17
    (WIDE_BEYOND: tarmac-to-tarmac gaps beside wide side areas and Metropolis's crossing decks, whose grass stays
    dropped — docs/deviations.md), and at most 5 single samples per course. Before: 146-405 runs per course (seams
    between the tarmac and the grass, holes between road points, gaps beside side strips, the start band's cuts); a
    wheel over one gave the player a -87 deg pitch sample on Diablo Canyon."""
    WIDE_BEYOND = {"ALPINE": 2, "AMAZON FALLS": 5, "DIABLO CANYON": 3, "METROPOLIS": 8, "PACIFIC COAST": 0,
                   "SURFERS OVAL": 6, "SURFERS ROAD": 10}   # Phase 22a: Road 1 -> 3 (the banked edge); then the barrier
    # walls with no revert (BARRIER_RETRIES 0, Pascal: keep the rock walls): holes of 1-9 units between a wall run and
    # the next point's grass, 30-45 units out; Phase 22c (measured): wall cuts CLIP_OVERLAP into the wall with no sliver
    # (the seams Pascal's Oval banked turn found: a wheel on no quad) — Diablo 14 -> 3, Road 18 -> 8, Oval 13 -> 5
    SINGLE_MAX = {"ALPINE": 1, "AMAZON FALLS": 2, "DIABLO CANYON": 3, "METROPOLIS": 4, "PACIFIC COAST": 0,
                  "SURFERS OVAL": 9, "SURFERS ROAD": 3}
    from vrtools.arcade.tgp import SURFACE_WALL
    from vrtools.convert.collision import WALL_MIN_LATERAL, _bboxes, _point_in_xz
    bad = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        boxes = _bboxes(col.quads); walls = {i for i, k in enumerate(col.surface) if k == SURFACE_WALL}
        def hit(x, z):
            return [i for i, b in enumerate(boxes) if b[0] <= x <= b[1] and b[2] <= z <= b[3] and _point_in_xz(col.quads[i].corners, x, z)]
        n = len(cl); runs = []
        for k2 in range(2 * n):
            k = k2 // 2
            (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
            if k2 % 2:
                x, z = (cl[k][0] + cl[(k + 1) % n][0]) / 2, (cl[k][1] + cl[(k + 1) % n][1]) / 2
            else:
                x, z = cl[k]
            d = math.hypot(bx - ax, bz - az) or 1.0
            rx, rz = (bz - az) / d, -(bx - ax) / d
            for sign in (-1.0, 1.0):
                run, start, lat = 0.0, 0.0, 0.0
                while lat <= 80.0:
                    ids = hit(x + sign * lat * rx, z + sign * lat * rz)
                    if ids:
                        if run and not (run < 1.0 and any(i in walls for i in ids)):   # a hole between two quads (Phase
                            runs.append((k2 / 2, sign, start, run))       # 22c: not a seam of at most CLIP_SLIVER at a wall's
                                                                          # edge: a wheel there gets the wall's response early)
                        run = 0.0
                        if any(i in walls for i in ids):
                            break
                    else:
                        if not run:
                            start = lat
                        run += 0.5
                    lat += 0.5
        wide = [r for r in runs if r[3] >= 1.0]
        near = [r for r in wide if r[2] < 10.5]
        single = [r for r in runs if r[3] < 1.0]
        if near or len(wide) > WIDE_BEYOND[name] or len(single) > SINGLE_MAX.get(name, 5):
            bad[name] = (near, len(wide), len(single), sorted(wide, key=lambda r: -r[3])[:8])
    assert not bad, "\n".join(f"{k}: {v}" for k, v in bad.items())


def test_merge_refuses_to_bridge_a_dip():
    """Phase 16 fix pass: three straight slices whose middle dips 4 units must not fuse into one flat quad (Metropolis's
    start straight: a fused quad sat at -6 over a road dipping to -12)."""
    from vrtools.convert.collision import _fuse, _sound
    def slab(z0, y0, y1):
        return _quad([(-5, y1, z0 + 10), (5, y1, z0 + 10), (5, y0, z0), (-5, y0, z0)])
    flat = [slab(0, 0, 0), slab(10, 0, 0), slab(20, 0, 0)]
    dip = [slab(0, 0, -4), slab(10, -4, -4), slab(20, -4, 0)]
    assert _sound(_fuse(flat[0], flat[-1]), flat)
    assert not _sound(_fuse(dip[0], dip[-1]), dip)


def _water(x0, x1, z0, z1):
    from vrtools.convert.geometry import WorldQuad
    return WorldQuad(((x0, 0.0, z0), (x1, 0.0, z0), (x1, 0.0, z1), (x0, 0.0, z1)), (0, 200, 248))


def test_shore_widths_follow_the_water():
    """Phase 19: the grass is as wide as the distance from the road's edge to the Saturn's water (the nearest of a point
    and its neighbours), between MIN_RUNOFF and VERGE_GRASS."""
    from vrtools.convert.collision import MIN_RUNOFF, VERGE_GRASS, is_water, road_edges, shore_widths
    assert is_water((0, 200, 248)) and is_water((0, 48, 144)) and not is_water((168, 208, 232)) and not is_water((0, 160, 64))
    quads, pts, h = _straight_road_near(0.0, half=10.0)
    edges = road_edges(quads, pts, h)
    w = shore_widths([_water(22.0, 60.0, 30.0, 60.0)], pts, edges)
    assert all(abs(w[k][1] - (22.0 - edges[k][1])) <= 0.6 for k in (3, 4, 5)), w[:8]
    assert all(w[k][1] <= 22.0 - edges[k][1] + 0.6 for k in (2, 6))
    assert all(w[k][1] == VERGE_GRASS for k in range(9, len(pts) - 1)) and all(left == VERGE_GRASS for left, _ in w)
    near = shore_widths([_water(10.5, 60.0, 30.0, 60.0)], pts, edges)              # water at the edge: the narrowest grass
    from vrtools.convert.collision import VERGE_SCAN_STEP, WALL_MIN_LATERAL, WALL_OVERLAP     # that still meets a wall clear of
    assert near[4][1] == max(MIN_RUNOFF, WALL_MIN_LATERAL + WALL_OVERLAP + VERGE_SCAN_STEP - edges[4][1])   # the racing lines


def test_the_wall_starts_at_the_shore():
    from vrtools.convert.collision import WALL_WIDTH, _point_in_xz, road_edges, road_verges, shore_widths
    quads, pts, h = _straight_road_near(0.0, half=10.0)
    w = shore_widths([_water(22.0, 60.0, 30.0, 60.0)], pts, road_edges(quads, pts, h))
    grass = road_verges(quads, pts, h, width=w, caps=w)                       # as the build (Phase 22a: the water caps the grass)
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=w)
    assert not any(_point_in_xz(g.corners, x, 40.0) for g in grass for x in (23.5, 25.0, 30.0))        # no grass on the water
    # (Phase 22a: a grass run takes its widest point within GRASS_WIDTH_TOL, so it may reach a unit past the shore,
    # under the wall, which starts SHORE_WALL_BACK before it)
    assert any(_point_in_xz(v.corners, 23.0, 40.0) for v in walls)                                     # the wall is there
    assert any(_point_in_xz(g.corners, 35.0, 120.0) for g in grass)                                    # 30 units of grass elsewhere


def test_a_shore_at_the_road_keeps_the_wall_clear_of_the_racing_lines():
    """Phase 19: water at the road's edge (a seawall) must not pull the wall inside the racing lines' clearance (AI lines
    at +-8, WALL_CLEARANCE 3): such a wall was dropped and left the water open (Pacific Coast, 64-unit holes)."""
    from vrtools.convert.collision import WALL_MIN_LATERAL, WALL_WIDTH, _near_racing_lines, _point_in_xz, road_edges, road_verges, shore_widths
    quads, pts, h = _straight_road_near(0.0, half=9.0)
    w = shore_widths([_water(9.5, 60.0, 30.0, 60.0)], pts, road_edges(quads, pts, h))
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=w)
    kept = [v for v in walls if not _near_racing_lines(v, pts)]
    assert any(_point_in_xz(v.corners, WALL_MIN_LATERAL + 1.0, 40.0) for v in kept)          # the wall is there, kept
    assert not any(_point_in_xz(v.corners, WALL_MIN_LATERAL - 0.6, 40.0) for v in kept)


def _arc_road(radius=80.0, half=10.0, sweep=math.pi, steps=30):
    """A flat tarmac arc (left-hand bend) of `steps` 1-step quads: quads, centreline points, height function."""
    pts, quads = [], []
    for i in range(steps + 1):
        a = sweep * i / steps
        pts.append((radius * math.cos(a) - radius, radius * math.sin(a)))
    for i in range(steps):
        (x0, z0), (x1, z1) = pts[i], pts[i + 1]
        def edge(x, z, a, s):
            return (x + s * half * math.cos(a), 0.0, z + s * half * math.sin(a))
        a0, a1 = sweep * i / steps, sweep * (i + 1) / steps
        quads.append(_quad([edge(x0, z0, a0, 1), edge(x0, z0, a0, -1), edge(x1, z1, a1, -1), edge(x1, z1, a1, 1)]))
    return quads, pts[:-1], (lambda px, pz: 0.0)


def test_a_shoreline_wall_on_a_bend_stays_off_the_road():
    """Phase 19: a wall at the shore lies 2-4 units off the road; fused over a long run (WALL_MAX_RUN) its straight chord
    cut across a bend and the racing-line filter dropped it (Pacific Coast, a 110-unit wall over points 12-23): shore
    walls take the grass's short runs."""
    from vrtools.convert.collision import WALL_WIDTH, _near_racing_lines, road_edges, road_verges, shore_widths
    quads, pts, h = _arc_road()
    edges = road_edges(quads, pts, h)
    w = [(left, 4.0) for left, _ in shore_widths([], pts, edges)]                 # water 4 units off the right edge
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=w)
    outside = [v for v in walls if math.hypot(v.centre[0] + 80.0, v.centre[2]) > 90.0                    # the right side (the bend's
               and 3 <= min(range(len(pts)), key=lambda k: math.dist(pts[k], (v.centre[0], v.centre[2]))) <= len(pts) - 4]   # outside), away from the open arc's ends
    assert len(outside) >= 10 and not [v for v in outside if _near_racing_lines(v, pts)], len(outside)


def test_the_wall_meets_the_grass_around_a_patch_of_water():
    """Phase 19: grass runs break at any width change, wall runs only beyond WALL_EDGE_TOL; a grass run cut short by a
    neighbour's water left grass ending before a wall run kept at full width (Surfers Road 151-152: 10-unit holes). Every
    lateral scan from the edge meets grass or wall without a gap until the wall."""
    from vrtools.convert.collision import WALL_WIDTH, _point_in_xz, road_edges, road_verges, shore_widths, wall_insets
    quads, pts, h = _straight_road_near(0.0, half=10.0, length=400.0)          # middle window: the strip's ends wrap
    edges = road_edges(quads, pts, h)
    for x0, z0, z1 in ((24.0, 140.0, 160.0), (30.0, 145.0, 185.0), (38.0, 144.0, 152.0)):      # without the erosion: 6 gaps
        w = shore_widths([_water(x0, 80.0, z0, z1)], pts, edges)
        grass, walls = road_verges(quads, pts, h, width=w), road_verges(quads, pts, h, width=WALL_WIDTH, inset=wall_insets(w))
        for z in [k * 2.5 for k in range(40, 120)]:
            for x in [10.0 + 0.5 * i for i in range(1, 80)]:
                if any(_point_in_xz(v.corners, x, z) for v in walls):
                    break
                assert any(_point_in_xz(g.corners, x, z) for g in grass), (x0, z, x)


SEA_OPEN_MAX = {"SURFERS OVAL": 14}
# Phase 22a (measured): the Oval's beach, 27-30 and 129-131 (Pascal: "there is no wall for a reason, it s suppose to be
# representing the beach sand and reset the car when it get s off the track by too much")


def test_no_road_side_reaches_the_water_past_the_wall(saturn_cue):
    """Phase 19 (Pascal: the car on the sea is a bug): from every 10-unit point and side, scanning out from the
    centreline, a wall quad (surface 5) comes at or before the first sample on the Saturn's water (beyond the tarmac),
    1 unit of tolerance, or by WALL_MIN_LATERAL + 0.5 where the water starts inside it (the wall stays clear of the AI
    lines: a car can reach at most that band of water). At most 5 sides per course without (a wall dropped beside a line)."""
    import math
    from vrtools.convert.collision import WALL_MIN_LATERAL, _bboxes, _point_in_xz
    bad = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        tarmac = col.quads[:col.n_tarmac]; tb = _bboxes(tarmac)
        walls = [q for i, q in enumerate(col.quads) if col.surface[i] == 5]; wb = _bboxes(walls)
        water = _WATER[name]; xb = [(min(p[0] for p in q.p), max(p[0] for p in q.p), min(p[2] for p in q.p), max(p[2] for p in q.p)) for q in water]
        inside = lambda x, z, qs, bs, key: any(b[0] <= x <= b[1] and b[2] <= z <= b[3] and _point_in_xz(key(q), x, z) for q, b in zip(qs, bs))
        n = len(cl); misses = []
        for k, (x, z) in enumerate(cl):
            (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
            d = math.hypot(bx - ax, bz - az) or 1.0
            rx, rz = (bz - az) / d, -(bx - ax) / d
            for sg in (-1, 1):
                at = lambda lat: (x + sg * lat * rx, z + sg * lat * rz)
                for i in range(1, 161):
                    lat = 0.5 * i
                    if inside(*at(lat), water, xb, lambda q: q.p) and not inside(*at(lat), tarmac, tb, lambda q: q.corners):
                        reach = max(i + 2, int(2 * (WALL_MIN_LATERAL + 0.5)))      # by water + 1, or by the wall's minimum lateral
                        if not any(inside(*at(0.5 * j), walls, wb, lambda q: q.corners) for j in range(1, reach + 1)):   # (clear of the AI lines)
                            misses.append((k, sg, lat))
                        break
        if len(misses) > SEA_OPEN_MAX.get(name, 5):
            bad[name] = (len(misses), misses[:8])
    assert not bad, bad


def test_shoreline_walls_stay_off_the_tarmac():
    """Phase 19 review: with water at a wide road's edge the wall's inner line fell a unit inside the measured edge, and a
    wall run spanning edges up to WALL_EDGE_TOL apart started up to ~4 units over the tarmac (Pacific Coast's start area,
    Surfers Road 0-3): a car touching the wall kept its surface over the road. No point of a wall lies on its tarmac."""
    from vrtools.convert.collision import WALL_WIDTH, _point_in_xz, road_edges, road_verges, shore_widths, wall_insets
    quads, pts, h = _straight_road_near(0.0, half=14.0, length=400.0)
    for k in range(18, 22):                                                    # the road widens by 2 on the right for a few quads
        c = list(quads[k].corners)
        quads[k] = _quad([c[0], (16.0, c[1][1], c[1][2]), (16.0, c[2][1], c[2][2]), c[3]])
    w = shore_widths([_water(14.2, 80.0, 0.0, 400.0)], pts, road_edges(quads, pts, h))
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=wall_insets(w))
    assert walls
    for v in walls:
        xs = [p[0] for p in v.corners]; zs = [p[2] for p in v.corners]
        for fx in (0.1, 0.3, 0.5, 0.7, 0.9):
            for fz in (0.1, 0.5, 0.9):
                x = min(xs) + fx * (max(xs) - min(xs)); z = min(zs) + fz * (max(zs) - min(zs))
                if _point_in_xz(v.corners, x, z):
                    assert not any(_point_in_xz(q.corners, x, z) for q in quads), (x, z, v.corners)


def test_a_wall_beside_another_legs_line_is_dropped_between_its_samples():
    """Phase 19 review: the racing lines are sampled every 10 units; a wall corner 0.33 units from another leg's +8 line,
    halfway between two samples, was kept (Metropolis wall 134). The filter samples the lines densely."""
    from vrtools.convert.collision import _near_racing_lines
    from vrtools.arcade.tgp import Quad16
    pts = [(0.0, float(z)) for z in range(0, 100, 10)] + [(60.0, float(z)) for z in range(100, 0, -10)]   # a hairpin's two legs
    # leg B runs -z at x 60: its right (+8) line is x = 60 - 8 = 52; a wall reaching x 51.7 between z 55 and z 56
    c = ((40.0, 0.0, 55.0), (51.7, 0.0, 55.5), (40.0, 0.0, 56.0), (30.0, 0.0, 55.5))
    w = Quad16(c, (40.0, 0.0, 55.5), 0)
    assert _near_racing_lines(w, pts)


def test_a_shoreline_wall_stays_at_its_own_edge_before_the_road_widens():
    """Phase 19 review: a shoreline wall run took the widest edge of its points AND its shared end point, so where the road
    widened at the next point the whole run's wall moved out past the water's start (Surfers Road 64-73: water at the
    12.5 edge, the wall at 16). Water at a 12.5 road edge that widens to 16 for ten quads: before the widening the wall
    begins by 13.5 (its minimum lateral and the grass's floor), as it does with no widening."""
    from vrtools.convert.collision import WALL_WIDTH, _point_in_xz, road_edges, road_verges, shore_widths, wall_insets
    quads, pts, h = _straight_road_near(0.0, half=12.5, length=300.0)
    for k in range(20, 30):                                                    # the road widens to 16 on the right
        c = list(quads[k].corners)
        quads[k] = _quad([c[0], (16.0, c[1][1], c[1][2]), (16.0, c[2][1], c[2][2]), c[3]])
    water = [_water(12.5, 80.0, 0.0, 200.0), _water(16.0, 80.0, 200.0, 300.0)]
    w = shore_widths(water, pts, road_edges(quads, pts, h))
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=wall_insets(w))
    late = []
    for z in range(5, 185, 5):                                                 # before the widening (point 19, z 190)
        hit = next((0.5 * i for i in range(1, 60) if any(_point_in_xz(v.corners, 0.5 * i, float(z)) for v in walls)), None)
        if hit is None or hit > 13.5:
            late.append((z, hit))
    assert not late, late


def test_a_shoreline_wall_clears_tarmac_poking_out_between_two_points():
    """Phase 19 review: each end of a shoreline wall step clears its own point's edge, but side-area tarmac poking out
    halfway between two points lay under the step's straight inner line (Pacific Coast 308-317, 383-389: 15 walls up to
    2.25 units over the tarmac). A tarmac wedge reaching 17 halfway between two points of a 12.5 road at the water: no
    point of a wall lies on it, and the wall still begins by 13.5 at the points."""
    from vrtools.convert.collision import WALL_WIDTH, _point_in_xz, road_edges, road_verges, shore_widths, wall_insets
    quads, pts, h = _straight_road_near(0.0, half=12.5, length=300.0)
    poke = _quad([(12.4, 0.0, 135.0), (12.5, 0.0, 130.0), (17.0, 0.0, 135.0), (12.5, 0.0, 140.0)])
    quads.append(poke)
    w = shore_widths([_water(12.5, 80.0, 0.0, 300.0)], pts, road_edges(quads, pts, h))
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=wall_insets(w))
    over = [(x / 4, z / 4) for x in range(48, 72) for z in range(516, 564)
            if _point_in_xz(poke.corners, x / 4, z / 4) and any(_point_in_xz(v.corners, x / 4, z / 4) for v in walls)]
    assert not over, over[:6]
    for z in (120.0, 150.0):
        hit = next((0.5 * i for i in range(1, 60) if any(_point_in_xz(v.corners, 0.5 * i, z) for v in walls)), None)
        assert hit is not None and hit <= 13.5, (z, hit)


def test_the_run_off_follows_the_drawn_ground_on_every_course(saturn_cue):
    """Phase 22a (Pascal's Diablo replay: at point 107 the car ran 30 units out onto the run-off and sat under the drawn
    canyon side): the grass and wall quads took the road edge's height straight across. Every corner of a grass or wall
    quad is within 1.0 of the collision's height function at that corner (the sink aside) at 99 % of the corners — of
    the corners the ground reaches from the quad's corner nearest the road without a jump (beyond one, over Metropolis's
    other deck, the grass stays flat: it was a ramp between the decks). Phase 22k: or, within 1.0 of the run-off's cap —
    an outer corner (of the across pairs 0-1 and 3-2) climbs at most VERGE_MAX_SLOPE a unit from its inner partner
    (the game's wall-step check); the inner corners stay on the ground. Phase 22o: or on the drawn ground (the non-water
    ground polygons' heights) — an outer corner on a drawn level within GROUND_DECK + VERGE_MAX_SLOPE a unit of its
    inner partner (GROUND_SLOPE_MAX a unit: a bank's reach) or at the cap's reach towards it, an inner corner on one
    within 1.5 of the profile (the Oval's infield bank climbs where the banked road's profile tilts down: `road_verges(ground=)`)."""
    import math
    from vrtools.arcade.tgp import SURFACE_GRASS, SURFACE_WALL
    from vrtools.convert.collision import GROUND_DECK, GROUND_SLOPE_MAX, VERGE_MAX_SLOPE, WALL_STEP, _continuous
    bad = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        drawn = _DRAWN[name]
        offs = []
        for q, k in zip(col.quads[col.n_tarmac:], col.surface[col.n_tarmac:]):
            if k not in (SURFACE_GRASS, SURFACE_WALL):
                continue
            step = WALL_STEP if k == SURFACE_WALL else 0.0              # Phase 22a: a wall lies WALL_STEP off the ground
            dist = lambda c: min((c[0] - x) ** 2 + (c[2] - z) ** 2 for x, z in cl)
            for a, b in ((0, 1), (3, 2)):
                inner, outer = sorted((q.corners[a], q.corners[b]), key=dist)
                L = math.hypot(outer[0] - inner[0], outer[2] - inner[2])
                if L > 1e-9 and not _continuous(hfn, inner[0], inner[2], (outer[0] - inner[0]) / L, (outer[2] - inner[2]) / L, L):
                    continue
                ground = hfn(outer[0], outer[2])
                reach = inner[1] + max(-VERGE_MAX_SLOPE * L, min(VERGE_MAX_SLOPE * L, ground - inner[1]))
                near = [v for v in drawn(outer[0], outer[2]) if abs(v - inner[1]) <= GROUND_DECK + GROUND_SLOPE_MAX * L]   # a bank's reach
                levels = [ground, reach] + near + [inner[1] + max(-VERGE_MAX_SLOPE * L, min(VERGE_MAX_SLOPE * L, v - inner[1])) for v in near]
                offs.append(min(abs(abs(outer[1] - v) - step) for v in levels))
                if k == SURFACE_GRASS:
                    hi = hfn(inner[0], inner[2])
                    offs.append(min(abs(inner[1] - v) for v in [hi] + [v for v in drawn(inner[0], inner[2]) if abs(v - hi) <= 1.5]))
                else:
                    offs.append(0.0)
        over = sum(1 for o in offs if o > 1.0)
        if over > 0.01 * len(offs):
            bad[name] = (over, len(offs), round(max(offs), 2))
    assert not bad, bad


_BARRIERS: dict = {}


def _drawn_barriers(saturn_cue):
    """Per course: the drawn faces that stop a car, as the build: every non-water face of groups 1 and 3 (terrain,
    structures), the faces steeper than 45° of groups 0 and 2 (ground, paint), in arcade space."""
    if not _BARRIERS:
        import os
        from pathlib import Path
        import numpy as np
        from vrtools.arcade.romset import RomSet
        import vrtools.arcade.tencourse as tc
        from vrtools.convert.geometry import placed, course_quads
        from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
        rs = RomSet.from_zip(Path(os.environ["VR_ROMDIR"]) / "vr.zip")
        for plan in tc.COURSES:
            sat = tc.load_saturn_course(saturn_cue, plan.path)
            gc = COURSE_OF_TEMPLATE[plan.template]
            pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
            from vrtools.convert.collision import is_water
            with placed(pl.angle, pl.tx, pl.tz):
                steep = []                                               # Phase 22a: as the build (collision.barrier_faces):
                for g in (0, 1, 2, 3):                                   # every non-water face of the terrain and structures,
                    for q in course_quads(sat, groups=(g,)):             # the steep faces of the ground and paint groups
                        a = np.array(q.p, float); nrm = np.cross(a[2] - a[0], a[3] - a[1]); ln = np.linalg.norm(nrm)
                        if ln < 1e-6:
                            continue
                        if (g in (1, 3) and not is_water(q.rgb)) or abs(nrm[1]) / ln < 0.7:
                            steep.append(a)
            _BARRIERS[plan.name] = steep
    return _BARRIERS


BARRIER_LATE = {"AMAZON FALLS": 0.11, "METROPOLIS": 0.24, "SURFERS OVAL": 0.12, "SURFERS ROAD": 0.055}
# Metropolis: its plazas (tarmac out to 40-46, the wall 2-4 late) and its decks, where a near wall was dropped beside
# the other leg and the run-off and wall went back to Phase 19's (94 of 395 sides); Amazon 32 of 306 and the Oval 6 of
# 118: wall runs at BARRIER_EDGE_TOL start at their widest edge, 2-4 units late (a finer run breaks the TGP floor);
# Phase 22a's last round (measured, Pascal drove both): the Oval 53 of 446, Road 23 of 458, the beach and shore sides
# where the shore's wall (SHORE_WALL_BACK) comes before the face's


def test_the_wall_stands_at_the_drawn_barrier_on_every_course(saturn_cue):
    """Phase 22a (Pascal: "the car is able to go outside the wall", Diablo and Surfers Road): the wall stood 30 units of
    grass past the road's edge (35-45 from the centre) while the Saturn draws its cliffs, canyon sides and fences 10-25
    out, so a car drove up to 25 units into the scenery. At each 10-unit centreline point and side where a line at the
    car's body height (the collision + 1) crossing outward from lateral 4 meets a drawn polygon steeper than 45°, and
    the next two points either side meet one too (a lone tree or pillar is not a wall), the collision wall starts within
    1.5 units beyond it (never inside 12.5, the AI lines' clearance; where the face stands on the Saturn's road slice,
    beyond the tarmac's end: Diablo's canyon side at 11 over tarmac to 16, a wall at 19.5 on Metropolis's start straight
    over tarmac to 23.5) at at least 95 % of those sides."""
    import math
    import numpy as np
    from vrtools.arcade.tgp import SURFACE_WALL
    from vrtools.convert.collision import _bboxes, _point_in_xz, _plane_height, WALL_MIN_LATERAL, VERGE_GRASS
    def crossing(o, d, a, b, c):
        e1, e2 = b - a, c - a; p = np.cross(d, e2); det = e1 @ p
        if abs(det) < 1e-9: return False
        t0 = o - a; u = (t0 @ p) / det
        if u < 0 or u > 1: return False
        q = np.cross(t0, e1); v = (d @ q) / det
        if v < 0 or u + v > 1: return False
        return 0 <= (e2 @ q) / det <= 1
    bad = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        P = _drawn_barriers(saturn_cue)[name]
        lo = np.array([p.min(0) for p in P]); hi = np.array([p.max(0) for p in P])
        wall = [col.quads[i] for i, s in enumerate(col.surface) if s == SURFACE_WALL]; wb = _bboxes(wall)
        tarmac_boxes = _bboxes(col.quads[:col.n_tarmac])
        n = len(cl); hits = {}
        for k in range(n):
            (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]; d = math.hypot(bx - ax, bz - az) or 1
            rx, rz = (bz - az) / d, -(bx - ax) / d
            cx, cz = cl[k]
            for sign in (1, -1):
                ex, ez = cx + sign * 50 * rx, cz + sign * 50 * rz
                sel = np.where((hi[:, 0] >= min(cx, ex) - 1) & (lo[:, 0] <= max(cx, ex) + 1) & (hi[:, 2] >= min(cz, ez) - 1) & (lo[:, 2] <= max(cz, ez) + 1))[0]
                hit = None
                for i in range(8, 100):
                    L0, L1 = i * 0.5, (i + 1) * 0.5
                    x0, z0, x1, z1 = cx + sign * L0 * rx, cz + sign * L0 * rz, cx + sign * L1 * rx, cz + sign * L1 * rz
                    o = np.array([x0, hfn(x0, z0) + 1.0, z0]); dv = np.array([x1, hfn(x1, z1) + 1.0, z1]) - o
                    if any(crossing(o, dv, P[j][0], P[j][1], P[j][2]) or crossing(o, dv, P[j][0], P[j][2], P[j][3]) for j in sel):
                        hit = L0; break
                tb = tarmac_boxes
                def road_at(L):                                                  # tarmac at the car's own level (not the other deck)
                    x, z = cx + sign * L * rx, cz + sign * L * rz
                    return any(b[0] <= x <= b[1] and b[2] <= z <= b[3] and _point_in_xz(t.corners, x, z) and abs(_plane_height(t, x, z) - hfn(x, z)) < 1.5
                               for t, b in zip(col.quads[:col.n_tarmac], tb))
                end = next((i * 0.5 for i in range(int((hit or 0) / 0.5), 100) if not road_at(i * 0.5)), 50.0)
                edge = next((i * 0.5 for i in range(8, 100) if not road_at(i * 0.5)), 50.0)
                if hit is not None and hit > edge + VERGE_GRASS:
                    hit = None                                                   # beyond the default run-off: the wall is nearer already
                if hit is not None:
                    hit = max(hit, end + 4.0)                                    # (a face standing on the Saturn's road slice: the wall
                                                                                 # stands at the tarmac's end as Phases 5-22i grew it, 4 units
                                                                                 # out; Phase 22j ungrew the tarmac and left the walls (the
                                                                                 # no-closer rule), so the expectation keeps the band)
                ours = next((i * 0.5 for i in range(100) if any(b[0] <= cx + sign * i * 0.5 * rx <= b[1] and b[2] <= cz + sign * i * 0.5 * rz <= b[3]
                             and _point_in_xz(w.corners, cx + sign * i * 0.5 * rx, cz + sign * i * 0.5 * rz) for w, b in zip(wall, wb))), None)
                hits[(k, sign)] = (hit, ours)
        sides = [(k, s) for (k, s), (h, _) in hits.items() if h is not None and all(hits[((k + j) % n, s)][0] is not None for j in (-2, -1, 1, 2))]
        late = [(k, s, hits[(k, s)]) for k, s in sides if hits[(k, s)][1] is None or hits[(k, s)][1] > max(hits[(k, s)][0], WALL_MIN_LATERAL) + 1.5]
        if len(late) > BARRIER_LATE.get(name, 0.05) * len(sides):
            excess = sorted(round((o if o is not None else 99) - max(h, WALL_MIN_LATERAL), 1) for _, _, (h, o) in late)
            bad[name] = (len(late), len(sides), excess[::max(1, len(excess) // 8)], late[:4])
    assert not bad, "\n".join(f"{k}: {v}" for k, v in bad.items())


def _grass_ends_in_nothing(col, cl):
    """(point, side, lateral) where a scan outward from the centreline point (chord directions, every 0.5 units to 80)
    leaves the grass (surface 2) for a sample under no quad before any wall sample: a car runs off the run-off."""
    import math
    from vrtools.arcade.tgp import SURFACE_GRASS, SURFACE_WALL
    from vrtools.convert.collision import _bboxes, _point_in_xz
    boxes = _bboxes(col.quads)
    bins: dict = {}
    for i, b in enumerate(boxes):
        for bx in range(int(b[0] // 16), int(b[1] // 16) + 1):
            for bz in range(int(b[2] // 16), int(b[3] // 16) + 1):
                bins.setdefault((bx, bz), []).append(i)
    n = len(cl); out = []
    for k in range(n):
        (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
        d = math.hypot(bx - ax, bz - az) or 1.0
        rx, rz = (bz - az) / d, -(bx - ax) / d
        for sign in (-1.0, 1.0):
            on_grass, lat = False, 0.0
            while lat <= 80.0:
                x, z = cl[k][0] + sign * lat * rx, cl[k][1] + sign * lat * rz
                kinds = {col.surface[i] for i in bins.get((int(x // 16), int(z // 16)), ())
                         if boxes[i][0] <= x <= boxes[i][1] and boxes[i][2] <= z <= boxes[i][3] and _point_in_xz(col.quads[i].corners, x, z)}
                if SURFACE_WALL in kinds:
                    break
                if not kinds:
                    if on_grass:
                        out.append((k, sign, lat))
                    break
                on_grass = kinds == {SURFACE_GRASS}
                lat += 0.5
    return out


RUN_OFF_OPEN_MAX = {"ALPINE": 4, "AMAZON FALLS": 17, "DIABLO CANYON": 20, "METROPOLIS": 40, "PACIFIC COAST": 8,
                    "SURFERS OVAL": 57, "SURFERS ROAD": 31}
# measured after Phase 22a's barrier walls with no revert (before them: 0-4; BARRIER_RETRIES 0, Pascal: keep the rock
# walls): far side areas 55-77 out, Metropolis's decks (38-42), wall runs that start a point late, and the seams a grass
# cut leaves along a wall (clip_at_walls: Diablo 11 -> 20)


def test_the_run_off_never_ends_before_a_wall_on_every_course(saturn_cue):
    """Phase 22a: narrowing the grass to a drawn barrier must not leave a run-off that ends in nothing before any wall
    (Metropolis 38-41: the near wall was dropped beside the other deck and 15 units of grass ended in nothing; Surfers
    Oval 8-12: the water side's wall run moved onto the side area and was dropped). At most the counts measured before
    the barrier walls (RUN_OFF_OPEN_MAX: far side areas, 55-74 units out)."""
    bad = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        open_ = _grass_ends_in_nothing(col, cl)
        if len(open_) > RUN_OFF_OPEN_MAX.get(name, 0):
            bad[name] = (len(open_), open_[:6])
    assert not bad, "\n".join(f"{k}: {v}" for k, v in bad.items())



def test_tgp_height_is_two_triangles_on_the_0_2_diagonal():
    """Phase 22a: the TGP's interpolation (subroutine 0x693) splits a quad on its corner-0/corner-2 diagonal: the plane
    of corners 0-1-2 on corner 1's side, of 2-3-0 on the other (Diablo replay, 131 samples on twisted quads: within
    0.0006). It meets all four corners of a twisted quad, and a triangle with its fourth corner mid-edge at corner 1
    (0-1-2 in a line) answers the plane of 2-3-0."""
    from vrtools.convert.collision import tgp_height
    twisted = ((0.0, 0.0, 10.0), (10.0, 4.0, 10.0), (10.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    for x, y, z in twisted:
        assert tgp_height(twisted, x, z) == pytest.approx(y, abs=1e-9)
    tri = ((0.0, 0.0, 10.0), (5.0, 1.0, 5.0), (10.0, 2.0, 0.0), (0.0, 6.0, 0.0))                   # 0-1-2 in a line
    assert tgp_height(tri, 2.0, 2.0) == pytest.approx(4.0, abs=1e-9)          # y = 6 - 0.4 x - 0.6 z through 2, 3, 0
    assert tgp_height(tri, 0.0, 0.0) == pytest.approx(6.0, abs=1e-9)


def test_the_road_quads_answer_the_collision_height(saturn_cue):
    """Phase 22a (the Diablo pitch gate's +-22 deg at points 305-315): the coverage fill grew a Saturn triangle slice (its
    fourth corner mid-edge at corner 1) on "the slice's plane", which for 0-1-2 in a line fell back to the mean corner
    height: a 20 x 38 side-area slice lay flat at 60.13 over ground from 58.0 to 62.0, 1.4 under its neighbours, and a
    wheel dropping onto it pitched the car. Over every tarmac quad (3 x 3 samples inside it), the TGP's height
    (`tgp_height`) is within 1.0 of the collision's height function at 99 % of the samples (a jump of more than 6,
    another deck, aside)."""
    from vrtools.convert.collision import _point_in_xz, tgp_height
    bad = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        offs = []
        for q in col.quads[:col.n_tarmac]:
            c = q.corners; xs = [p[0] for p in c]; zs = [p[2] for p in c]
            for fx in (0.15, 0.5, 0.85):
                for fz in (0.15, 0.5, 0.85):
                    x, z = min(xs) + fx * (max(xs) - min(xs)), min(zs) + fz * (max(zs) - min(zs))
                    if _point_in_xz(c, x, z):
                        o = abs(tgp_height(c, x, z) - hfn(x, z))
                        if o <= 6.0:
                            offs.append(o)
        over = sum(1 for o in offs if o > 1.0)
        if over > ROAD_OFF_MAX.get(name, 0.01) * len(offs):
            bad[name] = (over, len(offs), round(max(offs), 2))
    assert not bad, "\n".join(f"{k}: {v}" for k, v in bad.items())


ROAD_OFF_MAX = {"AMAZON FALLS": 0.02, "SURFERS OVAL": 0.03, "SURFERS ROAD": 0.03}
# measured after the fix (43 of 2425, 79 of 2850, 105 of 3840): side-area slices 25-44 units across with their corners
# on the height function and the drawn ground curving 1-2.5 inside them; two flat triangles cannot follow it (splitting
# them costs TGP words, and the build is at the 25 000 floor)


WALL_PURE = 5.0   # Phase 22a: at least this much of a wall strip has no grass under it (a car's logic step at speed: about 3)


def _grass_through_walls(col, cl, step=0.5):
    """(point or half-point, side, wall lateral, grass lateral) where a scan outward from the centreline (chord
    directions) meets the wall and then, within the strip's last WALL_PURE units, still finds grass: a car on the grass keeps it (the TGP's nearest-height pick) and crosses
    the wall on it (Pascal's Diablo replay, points 98-104: grass under the whole wall and on to 49 units)."""
    import math
    from vrtools.arcade.tgp import SURFACE_GRASS, SURFACE_WALL
    from vrtools.convert.collision import WALL_OVERLAP, WALL_WIDTH, _bboxes, _point_in_xz
    boxes = _bboxes(col.quads)
    bins: dict = {}
    for i, b in enumerate(boxes):
        for bx in range(int(b[0] // 16), int(b[1] // 16) + 1):
            for bz in range(int(b[2] // 16), int(b[3] // 16) + 1):
                bins.setdefault((bx, bz), []).append(i)
    def kinds(x, z):
        return {col.surface[i] for i in bins.get((int(x // 16), int(z // 16)), ())
                if boxes[i][0] <= x <= boxes[i][1] and boxes[i][2] <= z <= boxes[i][3] and _point_in_xz(col.quads[i].corners, x, z)}
    n = len(cl); out = []
    for k2 in range(2 * n):
        k = k2 // 2
        (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
        x0, z0 = ((cl[k][0] + cl[(k + 1) % n][0]) / 2, (cl[k][1] + cl[(k + 1) % n][1]) / 2) if k2 % 2 else cl[k]
        d = math.hypot(bx - ax, bz - az) or 1.0
        rx, rz = (bz - az) / d, -(bx - ax) / d
        for sign in (-1.0, 1.0):
            lw, lat = None, 0.0
            while lat <= 80.0:
                ks = kinds(x0 + sign * lat * rx, z0 + sign * lat * rz)
                if lw is None and SURFACE_WALL in ks:
                    lw = lat
                elif lw is not None and lat > lw + WALL_WIDTH + 1.0:
                    break                                          # past the wall strip
                elif lw is not None and lat > lw + WALL_WIDTH - WALL_PURE and SURFACE_GRASS in ks:
                    out.append((k2 / 2, sign, lw, lat))
                    break
                lat += step
    return out


GRASS_THROUGH_MAX = {"ALPINE": 32, "AMAZON FALLS": 21, "DIABLO CANYON": 42, "METROPOLIS": 59, "PACIFIC COAST": 17,
                     "SURFERS OVAL": 24, "SURFERS ROAD": 34}
# measured (sides at points and half-points, of 900-1 800 per course; before this fix 337-922 with 3.5 units of overlap
# allowed): where a grass run's widest point or its end point (a side area's 40-unit edge) carries it into a wall's last
# 5 units. Narrower grass runs (their own points only, or each end at its own point's wall) cut these to 0-36 but left
# holes where the wall moves out, and the fallback reverted 137-499 barrier sides per course instead of 8-103


def test_no_grass_runs_through_a_wall_on_every_course(saturn_cue):
    """Phase 22a (Pascal: "I drive to the wall at speed ... I go through and then get the position reset"): at the
    first right turn of Diablo Canyon the grass lay under the whole wall strip and on past it, so a car on the grass
    crossed the wall. Every wall strip (12 units) keeps its last WALL_PURE units clear of grass."""
    bad = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        through = _grass_through_walls(col, cl)
        if len(through) > GRASS_THROUGH_MAX.get(name, 0):
            bad[name] = (len(through), through[:6])
    assert not bad, "\n".join(f"{k}: {v}" for k, v in bad.items())


TARMAC_LATE = {"PACIFIC COAST": 0.14, "SURFERS OVAL": 0.17, "SURFERS ROAD": 0.16}
# measured (80 of 757, 51 of 537, 47 of 552): the start areas and the shore sides, where the slice's tarmac stays under
# the shore's wall (trim_tarmac follows the face, not the water); Pascal drove all three. Phase 22c (104, 84, 83): the
# tarmac reaches a low curb (no setback, Pascal: "at the curb"), and this test's 0.3 line meets kerbs the builder's 1.0 does not


def test_the_tarmac_ends_at_the_drawn_barrier_on_every_course(saturn_cue):
    """Phase 22a (Pascal's Diablo drive, points 115-122: the Saturn's road slice reaches 29.5 units out, the drawn road
    ends in a lip at 23.8 with nothing past it; a wall cannot stand over tarmac, so the car drove off the drawn edge and
    fell): where a drawn face (a line 0.3 or 1.0 above the collision, from lateral 4, meets a face steeper than 45°; the
    two points either side too) stands on our tarmac, the tarmac ends BARRIER_SETBACK inside it (never inside 12.5): no
    tarmac of the car's level more than 1.5 units past that line, at 95 % of those sides."""
    import math
    import numpy as np
    from vrtools.convert.collision import BARRIER_SETBACK, CURB_TOP, WALL_MIN_LATERAL, _bboxes, _plane_height, _point_in_xz
    def crossing(o, d, a, b, c):
        e1, e2 = b - a, c - a; p = np.cross(d, e2); det = e1 @ p
        if abs(det) < 1e-9: return False
        t0 = o - a; u = (t0 @ p) / det
        if u < 0 or u > 1: return False
        q = np.cross(t0, e1); v = (d @ q) / det
        if v < 0 or u + v > 1: return False
        return 0 <= (e2 @ q) / det <= 1
    bad = {}
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        P = _drawn_barriers(saturn_cue)[name]
        lo = np.array([p.min(0) for p in P]); hi = np.array([p.max(0) for p in P])
        tar = col.quads[:col.n_tarmac]; tb = _bboxes(tar)
        n = len(cl); faces = {}; curbs = {}
        frames = []
        for k in range(n):
            (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]; d = math.hypot(bx - ax, bz - az) or 1
            frames.append(((bz - az) / d, -(bx - ax) / d))
        for k in range(n):
            rx, rz = frames[k]; cx, cz = cl[k]
            for sign in (1, -1):
                ex, ez = cx + sign * 50 * rx, cz + sign * 50 * rz
                sel = np.where((hi[:, 0] >= min(cx, ex) - 1) & (lo[:, 0] <= max(cx, ex) + 1) & (hi[:, 2] >= min(cz, ez) - 1) & (lo[:, 2] <= max(cz, ez) + 1))[0]
                hit = None
                for i in range(8, 100):
                    L0, L1 = i * 0.5, (i + 1) * 0.5
                    x0, z0, x1, z1 = cx + sign * L0 * rx, cz + sign * L0 * rz, cx + sign * L1 * rx, cz + sign * L1 * rz
                    for body in (0.3, 1.0):
                        o = np.array([x0, hfn(x0, z0) + body, z0]); dv = np.array([x1, hfn(x1, z1) + body, z1]) - o
                        if any(crossing(o, dv, P[j][0], P[j][1], P[j][2]) or crossing(o, dv, P[j][0], P[j][2], P[j][3]) for j in sel):
                            hit = L0; break
                    if hit is not None: break
                if hit is not None:                              # Phase 22c: a low curb (a line CURB_TOP up meets nothing
                    curb = True                                  # within a unit beyond) takes no setback: the tarmac
                    for i in range(int(2 * hit), int(2 * (hit + 1.0)) + 1):   # reaches it
                        L0, L1 = i * 0.5, (i + 1) * 0.5
                        x0, z0, x1, z1 = cx + sign * L0 * rx, cz + sign * L0 * rz, cx + sign * L1 * rx, cz + sign * L1 * rz
                        o = np.array([x0, hfn(x0, z0) + CURB_TOP, z0]); dv = np.array([x1, hfn(x1, z1) + CURB_TOP, z1]) - o
                        if any(crossing(o, dv, P[j][0], P[j][1], P[j][2]) or crossing(o, dv, P[j][0], P[j][2], P[j][3]) for j in sel):
                            curb = False; break
                    curbs[(k, sign)] = curb
                faces[(k, sign)] = hit
        sides = late = 0; worst = []
        for (k, sign), L in faces.items():
            if L is None or not all(faces[((k + j) % n, sign)] is not None for j in (-2, -1, 1, 2)):
                continue
            limit = max(L - (0.0 if curbs.get((k, sign)) else BARRIER_SETBACK), WALL_MIN_LATERAL)
            rx, rz = frames[k]; cx, cz = cl[k]
            x, z = cx + sign * (limit + 1.5) * rx, cz + sign * (limit + 1.5) * rz
            sides += 1
            if any(b[0] <= x <= b[1] and b[2] <= z <= b[3] and _point_in_xz(t.corners, x, z) and abs(_plane_height(t, x, z) - hfn(x, z)) < 1.5 for t, b in zip(tar, tb)):
                late += 1; worst.append((k, sign, L))
        if sides and late > TARMAC_LATE.get(name, 0.05) * sides:
            bad[name] = (late, sides, worst[:6])
    assert not bad, "\n".join(f"{k}: {v}" for k, v in bad.items())


def test_no_barrier_wall_is_reverted(saturn_cue):
    """Phase 22a (Pascal: "keep in mind to not disable the rock collision"): a fallback that put the old 30-unit run-off
    back where the barrier-narrowed grass left a seam or lost a wall removed the walls at Diablo's rocks (56 sides; "the
    collision with the element is gone"). No barrier side is ever reverted, and Diablo's rocks left of points 97-122
    (a rock on a grey ramp, 21-26 out) keep a wall within 30 units."""
    import math
    from vrtools.arcade.tgp import SURFACE_WALL
    from vrtools.convert.collision import _bboxes, _point_in_xz
    for name, (col, lap, cl, hfn) in _all_covered_collisions(saturn_cue).items():
        assert col.coverage.get("barrier_reverted", 0) == 0, (name, col.coverage.get("barrier_reverted"))
    col, lap, cl, hfn = _all_covered_collisions(saturn_cue)["DIABLO CANYON"]
    walls = [q for q, k in zip(col.quads, col.surface) if k == SURFACE_WALL]; wb = _bboxes(walls); n = len(cl)
    far = []
    for k in range(100, 122):
        (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]; d = math.hypot(bx - ax, bz - az)
        rx, rz = (bz - az) / d, -(bx - ax) / d
        hit = next((i * 0.5 for i in range(120) if any(b[0] <= cl[k][0] - i * 0.5 * rx <= b[1] and b[2] <= cl[k][1] - i * 0.5 * rz <= b[3]
                    and _point_in_xz(w.corners, cl[k][0] - i * 0.5 * rx, cl[k][1] - i * 0.5 * rz) for w, b in zip(walls, wb))), None)
        if hit is None or hit > 30.0:
            far.append((k, hit))
    assert not far, far


def test_a_wall_step_never_crosses_the_ground():
    """Phase 22a (Pascal p22play17, "reset before crashing in the wall"): the step went away from zero per corner, so a
    wall quad over ground crossing zero (Diablo's first right, quad 0x528: ground -0.02 at the road, +0.37 out) ran from
    -4.3 to +4.7 and through the ground between: no step, the car climbed it to four wall wheels and was put back. A
    quad's corners step the same way, and every corner stands at least WALL_STEP / 2 off its ground."""
    from vrtools.convert.collision import WALL_STEP, _wall_step
    for ys in ([-0.02, 0.37, 0.38, -0.01], [0.0, 0.0, 0.0, 0.0], [-3.0, -3.1, -2.9, -3.0], [1.2, 1.3, -0.4, -0.2]):
        out = _wall_step(ys, WALL_STEP)
        signs = {o - y > 0 for o, y in zip(out, ys)}
        assert len(signs) == 1, (ys, out)
        assert all(abs(abs(o) - abs(y)) >= WALL_STEP / 2 for o, y in zip(out, ys)), (ys, out)


def test_the_grass_ends_at_the_walls_inner_edge():
    """Phase 22a (Pascal p22play17, "reset before crashing in the wall"; Diablo 2601, 3785): the grass ran up to a unit
    under the wall; there the TGP keeps the wheel on the grass (the nearer height), so when it first reads the wall it is
    already inside the wall's outline, and the V60's shallow-angle test (`0xfec3d7`: the wheel's move against the wall
    quad's edges) finds no edge crossed: the car climbed the step to four wall wheels and was put back. A grass quad is
    cut at the wall's inner edge: its outer corners on that edge, its inner corners where they were."""
    from vrtools.convert.collision import CLIP_OVERLAP, _point_in_xz, clip_at_walls
    q = lambda c: Quad16(tuple(c), tuple(sum(p[i] for p in c) / 4 for i in range(3)), 0)
    grass = q([(14.0, 0.0, 10.0), (10.0, 0.0, 10.0), (10.0, 0.0, 0.0), (14.0, 0.0, 0.0)])     # lateral 10..14
    wall = q([(25.0, 4.0, 10.0), (12.5, 4.0, 10.0), (13.0, 4.0, 0.0), (25.0, 4.0, 0.0)])      # inner edge 12.5 .. 13
    (cut,) = clip_at_walls([grass], [wall])
    xs = sorted((round(c[0], 3), c[2]) for c in cut.corners)
    assert xs == [(10.0, 0.0), (10.0, 10.0), (12.5 + CLIP_OVERLAP, 10.0), (13.0 + CLIP_OVERLAP, 0.0)], cut.corners   # (22c)
    both = [(x / 4, z / 4) for x in range(40, 60) for z in range(1, 40)
            if _point_in_xz(cut.corners, x / 4, z / 4) and _point_in_xz(wall.corners, x / 4, z / 4)
            and not x / 4 - (12.5 + (13.0 - 12.5) * (1 - z / 40)) <= CLIP_OVERLAP + 0.01]     # (the cut's overlap)
    assert not both, both[:5]
    far = q([(9.0, 0.0, 10.0), (5.0, 0.0, 10.0), (5.0, 0.0, 0.0), (9.0, 0.0, 0.0)])           # clear of the wall: unchanged
    assert clip_at_walls([far], [wall]) == [far]


def test_a_wall_cut_never_opens_a_hole():
    """Phase 22a (Alpine 339.5: a hole from the centreline out to 4 units after the first cut): a coverage-fill quad's
    corners 0-1 can run along the road, and cutting that edge at a wall over its corner took road from under no wall. A
    cut is kept only when all it takes lies under a wall."""
    from vrtools.convert.collision import clip_at_walls
    q = lambda c: Quad16(tuple(c), tuple(sum(p[i] for p in c) / 4 for i in range(3)), 0)
    road = q([(10.0, 0.0, 20.0), (10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 20.0)])      # 0-1 along z
    wall = q([(20.0, 4.0, 30.0), (20.0, 4.0, 15.0), (8.0, 4.0, 15.0), (8.0, 4.0, 30.0)])    # over corner 0 only
    assert clip_at_walls([road], [wall], guard=True) == [road]


def test_the_walls_inner_line_has_no_step_between_runs():
    """Phase 22a (Pascal p22play19, "reset before impacting the wall" in Diablo's first corner, frame 3291): a wall run
    nearer the road than the one before it showed its 3-unit end to a car driving along the grass; the V60 took the
    parallel hit as a slide along the run's edge (`0xfec2ac`), which put all four wheels on the wall and the car was put
    back. Consecutive runs meet at the nearer inner corner: scanning out from the road along it, the first wall
    sample's lateral never jumps by a unit or more between samples 0.5 apart."""
    from vrtools.convert.collision import WALL_WIDTH, _point_in_xz, road_verges
    quads, pts, h = _straight_road_near(0.0, half=16.0, length=300.0)
    for i in range(10, 30):                                                      # the road narrows to 13 (Diablo 158-159)
        quads[i] = _quad([(13.0 if p[0] > 0 else p[0], p[1], p[2]) for p in quads[i].corners])
    n = len(pts)
    ins = [(2.5, 2.5) if k < 10 else (1.0, 1.0) for k in range(n)]               # the drawn face nearer there too
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=ins, fine=[(False, False)] * n)
    def first(z):
        x = 12.0
        while x < 60.0:
            if any(_point_in_xz(w.corners, x, z) for w in walls):
                return x
            x += 0.1
        return None
    lats = [(z / 2, first(z / 2)) for z in range(120, 340)]
    jumps = [(a, b) for a, b in zip(lats, lats[1:]) if a[1] is not None and b[1] is not None and abs(a[1] - b[1]) >= 1.0]
    assert not jumps, jumps


def test_diablos_first_right_turn_walls_at_the_drawn_rock(saturn_cue):
    """Phase 22a (Pascal p22play20: "on the very first right turn (the elevated one) i feel i cannot reach that wall"):
    the drawn face stands 17.5-29.5 out at points 26-38 on the right, but the wall stood at the road's edge (12.5-16.5):
    the strip's inset is the narrowest width within MERGE_MAX_RUN points (`wall_insets`, the shore's erosion), and the
    rock at the road at 18-24 and 40-42 pulled it in. A drawn barrier's wall takes its own point's width: from points 28
    to 38 (30 on: 28 shares its run with 26) the first wall sample lies within 3.5 units of the face less BARRIER_SETBACK."""
    from vrtools.convert.collision import BARRIER_SETBACK, COVERAGE_SPACING, _point_in_xz, _smooth_dirs
    col, lap, cl, hfn = _all_covered_collisions(saturn_cue)["DIABLO CANYON"]
    from vrtools.convert.lap import centreline
    pts = centreline(lap, spacing=COVERAGE_SPACING); dirs = _smooth_dirs(pts)
    walls = [q for i, q in enumerate(col.quads) if col.surface[i] == 5]
    faces = {30: 26.5, 32: 26.5, 34: 26.5, 36: 27.5, 38: 28.5}     # measured (barrier_faces, right side; 28 is the run's
                                                                   # shared end with 26, where the face is 17.5)
    import math                                                    # Phase 22f: the lap starts on the main road's loop, so the
    anchor = lap.centres[lap.order.index(96)]                      # turn is found by its Saturn slice (96, the old point 30)
    shift = min(range(len(pts)), key=lambda k: math.dist(pts[k], anchor)) - 30
    early = []
    for k, face in faces.items():
        (x, z), (dx, dz) = pts[k + shift], dirs[k + shift]
        lat = 4.0
        while lat < 60.0 and not any(_point_in_xz(w.corners, x + lat * dz, z - lat * dx) for w in walls):
            lat += 0.5
        if lat < face - BARRIER_SETBACK - 3.5:
            early.append((k, lat, face))
    assert not early, early

def test_a_low_curb_takes_no_setback():
    """Phase 22c (Pascal p22play21, Diablo 94-96 left: "the wall impact when i actually pass over the white line"; Pascal
    chose "at the curb"): the face there is a low vertical curb (1-3 units) one unit past the white line, and the wall
    stood BARRIER_SETBACK before it, on the line. A face that a line CURB_TOP above the collision does not meet within a
    unit beyond is a curb: its wall stands at it (the face reported BARRIER_SETBACK further out); a tall face keeps it."""
    from vrtools.convert.collision import BARRIER_SETBACK, barrier_faces
    from vrtools.convert.geometry import WorldQuad
    quads, pts, h = _straight_road_near(0.0, half=10.0, length=200.0)
    def wall(top):                                                          # a vertical face along z at x = 20
        return [WorldQuad(((20.0, 0.0, z), (20.0, top, z), (20.0, top, z + 10.0), (20.0, 0.0, z + 10.0)), (64, 64, 88))
                for z in range(0, 200, 10)]
    curb = barrier_faces(wall(1.5), pts, h)
    rock = barrier_faces(wall(12.0), pts, h)
    for k in range(4, 14):
        assert rock[k][1] == pytest.approx(20.0, abs=0.6), rock[k]
        assert curb[k][1] == pytest.approx(20.0 + BARRIER_SETBACK, abs=0.6), curb[k]


def test_a_wall_cut_leaves_no_seam():
    """Phase 22c (Pascal p22play22, Surfers Oval's banked turn, frame 9143: a wheel read no quad, the game's wall response
    fired before the wall): a cut that left up to CLIP_SLIVER uncovered along a bending wall edge opened a seam between
    the road and the wall. Every sample of the quad before the cut lies in the cut quad or under a wall, and the cut ends
    at most CLIP_OVERLAP inside the wall."""
    from vrtools.convert.collision import CLIP_OVERLAP, CLIP_SLIVER, _point_in_xz, clip_at_walls
    q = lambda c: Quad16(tuple(c), tuple(sum(p[i] for p in c) / 4 for i in range(3)), 0)
    grass = q([(14.0, 0.0, 10.0), (10.0, 0.0, 10.0), (10.0, 0.0, 0.0), (14.0, 0.0, 0.0)])
    walls = [q([(25.0, 4.0, 5.0), (13.2, 4.0, 5.0), (13.0, 4.0, 0.0), (25.0, 4.0, 0.0)]),     # an inner edge bending out by
             q([(25.0, 4.0, 10.0), (13.0, 4.0, 10.0), (13.2, 4.0, 5.0), (25.0, 4.0, 5.0)])]    # 0.2 at z 5 (over CLIP_SLIVER)
    (cut,) = clip_at_walls([grass], walls)
    holes = [(x / 10, z / 10) for x in range(100, 141) for z in range(0, 101)
             if _point_in_xz(grass.corners, x / 10, z / 10) and not _point_in_xz(cut.corners, x / 10, z / 10)
             and not any(_point_in_xz(w.corners, x / 10 + dx, z / 10) for w in walls for dx in (0.0, CLIP_SLIVER + 1e-6))]
    assert not holes, holes[:5]                                               # (at most CLIP_SLIVER from the wall)
    assert max(c[0] for c in cut.corners) in (14.0,) or max(c[0] for c in cut.corners) <= 13.2 + CLIP_OVERLAP + 1e-6   # cut, or kept


def test_a_wall_cut_keeps_the_banks_height():
    """Phase 22c (Pascal p22play23, Surfers Oval's steepest bank: "the car didnt bank to follow the road, in place it went
    through the road"): a cut corner whose ground was more than a unit off the straight line along the edge took the
    kept end's height (meant for a jump onto another deck), and a bank's knee lay flat. Across a 45 degree knee the cut
    corner keeps the ground's height."""
    from vrtools.convert.collision import clip_at_walls
    q = lambda c: Quad16(tuple(c), tuple(sum(p[i] for p in c) / 4 for i in range(3)), 0)
    h = lambda x, z: max(0.0, x - 15.0)                                          # flat to 15, then 45 degrees up
    road = q([(20.0, 5.0, 10.0), (10.0, 0.0, 10.0), (10.0, 0.0, 0.0), (20.0, 5.0, 0.0)])
    wall = q([(30.0, 9.0, 10.0), (17.0, 9.0, 10.0), (17.0, 9.0, 0.0), (30.0, 9.0, 0.0)])
    (cut,) = clip_at_walls([road], [wall], h, guard=True)                    # (the straight line: 3.5 there)
    moved = [c for c in cut.corners if abs(c[0] - 17.0) < 1e-3]
    assert len(moved) == 2 and all(c[1] == pytest.approx(2.0, abs=0.05) for c in moved), cut.corners


def test_one_points_edge_glitch_does_not_pull_a_rock_wall_in():
    """Phase 22c (Pascal p22play25, Surfers Oval's steepest bank: "it doesnt register the inclination of the maximum
    angle"): the road's measured edge read 17.0 at one point between 22.5-23.5 (the 45-degree bank's slice off the height
    function), and the barrier run's nearest point put the wall on the bank's top. A barrier run takes each point's edge
    as the median of it and its neighbours: a one-point dip leaves the wall where its neighbours put it."""
    from vrtools.convert.collision import WALL_WIDTH, _point_in_xz, road_verges
    quads, pts, h = _straight_road_near(0.0, half=23.0, length=300.0)
    quads[15] = _quad([(17.0 if p[0] > 0 else p[0], p[1], p[2]) for p in quads[15].corners])   # one slice short
    n = len(pts)
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=[(1.0, 1.0)] * n, fine=[(False, False)] * n)
    for z in (140.0, 150.0, 155.0, 160.0):
        x = 12.0
        while x < 60.0 and not any(_point_in_xz(w.corners, x, z) for w in walls):
            x += 0.5
        assert x >= 21.0, (z, x)


def test_the_edge_scan_rejoins_the_bank_past_a_lower_slice():
    """Phase 22c (Pascal p22play25, Surfers Oval 56-57: the wall stood on the 45-degree bank's top): two slices overlap on
    the bank, the bank itself and a flatter one 2-3 units under it; the scan, following the nearest height sample to
    sample, rode the lower slice, which ends at 16, and took the bank (2.5 above it) for another deck: the road "ended"
    at 17 of 23. Past a hole the scan rejoins tarmac at the height function's height."""
    from vrtools.convert.collision import road_edges
    bank = lambda x, z: 0.0 if x < 10 else 0.5 * (x - 10.0)                         # flat to 10, then rising
    pts = [(0.0, z) for z in range(0, 200, 10)]
    slab = lambda x0, x1, y0, y1, z: _quad([(x0, y0, z), (x1, y1, z), (x1, y1, z + 10.0), (x0, y0, z + 10.0)])
    quads = [slab(-10.0, 10.0, 0.0, 0.0, z) for _, z in pts] + [slab(10.0, 23.0, 0.0, 6.5, z) for _, z in pts] \
        + [slab(8.0, 16.0, 0.0, 0.4, z) for _, z in pts]                            # the lower, flatter slice
    edges = road_edges(quads, pts, bank)
    assert all(e[1] >= 22.0 for e in edges[3:-3]), [e[1] for e in edges]


def test_a_road_quad_over_a_banks_knee_is_split():
    """Phase 22c (Pascal p22play26, Surfers Oval's first curve tiles: "the car didnt detect the beginning of the turn at
    max incline and went under the road"): a slice from 5 to 23 units out over a bank flat to 18, then 45 degrees to 21,
    is two flat triangles a unit under the bank's top (points 53-55: 4.9 and 6.0 for 5.8 and 7.1). A road quad that
    lies more than BANK_SPLIT_TOL under the height function (a car goes through the road there) is split across (at most
    twice); over it a car only rides a little high (the TGP budget: splitting both ways cost 470 quads)."""
    from vrtools.convert.collision import BANK_SPLIT_TOL, split_bank_quads, tgp_height, _point_in_xz
    h = lambda x, z: max(0.0, min(4.0, x - 17.0))                               # 45 degrees from 17, flat on top from 21
    c = [(17.0, h(17, 0), 10.0), (23.0, h(23, 0), 10.0), (23.0, h(23, 0), 0.0), (17.0, h(17, 0), 0.0)]
    road = Quad16(tuple(c), tuple(sum(p[i] for p in c) / 4 for i in range(3)), 7)
    parts = split_bank_quads([road], h)
    assert 2 <= len(parts) <= 4
    worst = max(h(x / 4, z / 4) - tgp_height(q.corners, x / 4, z / 4)          # (under the road)
                for x in range(68, 93) for z in range(1, 40) for q in parts if _point_in_xz(q.corners, x / 4, z / 4))
    assert worst <= BANK_SPLIT_TOL + 0.05, worst
    assert all(q.attr == 7 for q in parts)
    flat = Quad16(tuple((x, 0.0, z) for x, _, z in c), road.centre, 7)
    assert split_bank_quads([flat], lambda x, z: 0.0) == [flat]


def test_a_kerb_at_the_roads_edge_does_not_split_the_road():
    """Phase 24 (Pascal rec137, Metropolis: two bumps after the start line): the height function read exactly on a road
    quad's edge answers the neighbouring kerb (0.79 over the road at the left edge 110 units after the line), the quad
    counted as under the road and was cut into two parts that do not lie in a plane: a 0.7 hump on the driving line.
    A step that stands at the edge is not a knee under the quad: the quad stays whole."""
    from vrtools.convert.collision import split_bank_quads
    kerb = lambda x, z: 0.8 if x <= 0.0 and 6.0 < z < 18.0 else -0.05 * x       # a kerb beside a cambered road, along part of it
    c = [(0.0, 0.0, 0.0), (20.0, -1.0, 0.0), (20.0, -1.0, 24.0), (0.0, 0.0, 24.0)]
    road = Quad16(tuple(c), tuple(sum(p[i] for p in c) / 4 for i in range(3)), 7)
    assert split_bank_quads([road], kerb) == [road]


def test_lanes_narrow_where_a_curb_stands_at_the_road():
    """Phase 22c (Pascal p22play28, Amazon's first right corner: "that is the curb it should have stopped the car"; Diablo
    321-327: rock at 8.5): the curb stands 10.5 out at the road's edge (10), but no wall came inside WALL_MIN_LATERAL
    (12.5: the AI lines' +-8 and their clearance), so a car ran 2 units over it. Where a drawn barrier's wall place lies
    inside 12.5 (and not nearer the centre than LANE_MIN_WALL), that side's AI lines narrow (to LANE_MIN_SCALE at least), tapering over
    LANE_REACH points, and the wall may stand that much nearer."""
    from vrtools.convert.collision import BARRIER_SETBACK, LANE_MIN_SCALE, WALL_MIN_LATERAL, lane_scales
    n = 40
    faces = [(30.0, 30.0)] * n
    faces[20] = (30.0, 10.5 + BARRIER_SETBACK)                                   # a curb at 10.5 on the right (as barrier_faces
    s = lane_scales(faces, ((15, 25),))                                          # reports a curb: a setback further out)
    assert s[20][0] == 1.0 and s[20][1] == pytest.approx((10.5 - (WALL_MIN_LATERAL - 8.0)) / 8.0)   # 0.75: the +8 line at 6
    assert s[19][1] > s[20][1] and s[10][1] == 1.0                             # it tapers, and ends
    inside = [(30.0, 30.0)] * n
    inside[20] = (30.0, 7.0)                                                     # a face over the road (Diablo 93-97: its wall
    assert lane_scales(inside, ((15, 25),))[20][1] == 1.0                                     # place 5.5, under LANE_MIN_WALL): no narrowing
    deep = [(30.0, 30.0)] * n
    deep[20] = (30.0, 8.5)                                                       # Diablo 321-327's rock: the wall place 7
    assert lane_scales(deep, ((15, 25),))[20][1] == LANE_MIN_SCALE


def test_the_grass_floor_narrows_with_the_lanes():
    """Phase 22c review (suite s40): Diablo 99-103 and 363-372 draw curbs 8-9.5 out; the narrowed lines let the tarmac be
    trimmed to 7.5-8 there, but the grass never started inside GRASS_FLOOR (8.5, kept off the +-8 AI lines), so 1-2 units
    of no quad opened before the wall. The grass floor narrows as the lines do: GRASS_FLOOR less 8 x what they give back."""
    import vrtools.convert.collision as CC
    from vrtools.convert.collision import GRASS_FLOOR, grass_floor
    assert grass_floor(3, 1) == GRASS_FLOOR                                     # no lanes being built: the plain floor
    CC._LANES = [(1.0, 1.0)] * 3 + [(1.0, 0.5)] + [(1.0, 1.0)] * 3
    try:
        assert grass_floor(3, 0) == GRASS_FLOOR
        assert grass_floor(3, 1) == pytest.approx(GRASS_FLOOR - 4.0)             # the +8 line at 4: the floor 4 nearer
    finally:
        CC._LANES = None


def test_a_hole_wider_than_a_sliver_gets_no_filler():
    """Phase 22n: `fill_holes` covers the sub-unit holes between slices (Phase 22j). With the coverage band moved onto the
    shifted lines, the scan of Diablo's pit lane met the open ground between the lane and the main road's banked loop and
    laid one 120-by-60-unit filler over both, credited by its front: every car on the loop read road point 129 for 300
    units and the field slowed. A cluster of holes wider across the road than HOLE_MAX_SPAN is no sliver and gets no
    filler; a long narrow one (a pit lane's gaps run for hundreds of units) is pieced along as before."""
    from vrtools.arcade.tgp import Quad16
    from vrtools.convert.collision import HOLE_MAX_SPAN, fill_holes
    pts = [(0.0, 5.0 * k) for k in range(40)]                                   # a +z straight, every 5 units (the dense points)
    def slab(x0, x1, z0, z1):
        c = ((x0, 0.0, z1), (x1, 0.0, z1), (x1, 0.0, z0), (x0, 0.0, z0))
        return Quad16(c, ((x0 + x1) / 2, 0.0, (z0 + z1) / 2), 7)
    road = [slab(-12.0, 12.0, 0.0, 200.0)]                                       # the road, whole
    gapped = [slab(-12.0, 12.0, 0.0, 95.0), slab(-12.0, 12.0, 95.6, 200.0)]      # a 0.6-unit sliver across it at z 95
    torn = [slab(-12.0, 12.0, 0.0, 60.0), slab(-12.0, 12.0, 140.0, 200.0)]       # 80 units of open ground across a 24-unit road
    wide = [slab(-25.0, 25.0, 0.0, 60.0), slab(-25.0, 25.0, 140.0, 200.0)]       # ... and across a 50-unit one
    assert 10.0 <= HOLE_MAX_SPAN <= 40.0
    _, _, n_sliver = fill_holes(gapped, 2, pts, lambda x, z: 0.0)
    _, _, n_torn = fill_holes(torn, 2, pts, lambda x, z: 0.0)
    _, _, n_wide = fill_holes(wide, 2, pts, lambda x, z: 0.0, half_width=25.0)
    _, _, n_whole = fill_holes(road, 1, pts, lambda x, z: 0.0)
    assert n_sliver >= 1 and n_whole == 0
    assert n_torn >= 1, n_torn                                                  # narrow: a lane's gap, pieced along
    assert n_wide == 0, n_wide                                                  # wide: open ground


def test_the_tarmac_band_follows_a_banked_surface_but_not_another_deck():
    """Phase 22n: the band across the road (`tarmac_band`) chains the strips beside the route's; a strip joins only where its
    surface continues the band's within BAND_STEP at the join (a banking rises strip by strip), so another road meeting
    the band in plan a few units higher (Metropolis's junction, 4 units up: three cars shifted onto it read its road
    point, 172 -> 52) stays out even inside BAND_DECK."""
    from vrtools.arcade.tgp import Quad16
    from vrtools.convert.collision import BAND_STEP, tarmac_band
    pts = [(0.0, 10.0 * k) for k in range(60)]
    def strip(x0, x1, y0, y1):                                                   # a +z strip from z 0 to 600, y0 at x0 to y1 at x1
        return [Quad16(((x0, y0, z + 10.0), (x1, y1, z + 10.0), (x1, y1, z), (x0, y0, z)), ((x0 + x1) / 2, (y0 + y1) / 2, z + 5.0), 7)
                for z in range(0, 600, 10)]
    banked = strip(-4.0, 4.0, 0.0, 0.0) + strip(-14.0, -4.0, 0.9, 0.0) + strip(-24.0, -14.0, 2.4, 0.9)   # rises 0.9 then 1.5
    deck = strip(-4.0, 4.0, 0.0, 0.0) + strip(-14.0, -4.0, 3.5, 3.5)                                   # a level 3.5 up beside it
    assert 0.5 <= BAND_STEP <= 2.0
    lo, hi = tarmac_band(banked, pts, lambda x, z: 0.0)[10]
    assert lo < -23.0 and hi > 3.0, (lo, hi)                                      # the banking is one band
    lo, hi = tarmac_band(deck, pts, lambda x, z: 0.0)[10]
    assert lo > -5.0 and hi > 3.0, (lo, hi)                                       # the other deck is not
    # a road crossing at grade (Metropolis 206-210: the lap's own road comes back across a 38-unit slab, credited its own
    # far point; shifted onto it three cars read 172 -> 52): a quad whose place on the lap is more than BAND_LAP_WINDOW
    # points from the point stays out, whatever its height
    from vrtools.convert.collision import BAND_LAP_WINDOW, _dirs
    crossing = strip(-4.0, 4.0, 0.0, 0.0) + strip(4.0, 20.0, 0.0, 0.0) \
        + [Quad16(((40.0, 0.0, 295.0), (40.0, 0.0, 315.0), (6.0, 0.0, 315.0), (6.0, 0.0, 295.0)), (23.0, 0.0, 305.0), 7)]
    places = list(range(60)) * 2 + [0]                                           # the slab's own place: point 0, 30 points from 30
    lo, hi = tarmac_band(crossing, pts, lambda x, z: 0.0, places=places)[30]
    assert lo > -5.0 and 5.5 <= hi <= 6.5 and 10 <= BAND_LAP_WINDOW <= 25, (lo, hi)   # the band ends where the crossing's slab begins
    lo, hi = tarmac_band(crossing, pts, lambda x, z: 0.0, places=places)[10]
    assert lo > -5.0 and hi > 19.0, (lo, hi)                                      # away from it, the whole 24-unit road


def test_the_lines_shift_onto_the_saturns_tarmac_where_the_route_strip_is_at_its_edge():
    """Phase 22n (Pascal: Metropolis's building soft at 325-349 R): the lap route follows ONE Saturn strip and the centreline
    is that strip's middle, so where the strip is the road's edge one (the white line at Metropolis's hairpin, the inner
    strip of the Oval's banking) the AI lines at +-8 straddle it onto the sidewalk or the painted grass, and the coverage
    fill lays tarmac there. `lane_shift` moves the lines sideways, per point, so the outer lines keep LINE_CLEAR inside
    the Saturn's own tarmac band (the slices contiguous across the road at that point): a road from -22 to +3 shifts
    them 8 left, a symmetric road not at all, and the shift tapers by SHIFT_TAPER per point."""
    from vrtools.arcade.tgp import Quad16
    from vrtools.convert.collision import LINE_CLEAR, SHIFT_TAPER, lane_shift
    from vrtools.convert.collision import SHIFT_GRID_CLEAR, SHIFT_MIN_RUN
    assert 4 <= SHIFT_MIN_RUN <= 10
    pts = [(0.0, 10.0 * k) for k in range(200)]                                 # a +z straight, points every 10
    quads = []
    for k in range(200):
        z = 10.0 * k
        if 100 <= k < 120:                                                      # the band -22..+3: a 7-unit route strip at the
            strips = ((-22.0, -14.0), (-14.0, -4.0), (-4.0, 3.0))               # right edge, two more to its left
        elif 5 <= k < 25:                                                       # the same band inside the grid's zone after the line
            strips = ((-22.0, -14.0), (-14.0, -4.0), (-4.0, 3.0))
        elif 150 <= k < 153:                                                    # a three-point notch (a junction's mouth): no shift
            strips = ((-22.0, -14.0), (-14.0, -4.0), (-4.0, 3.0))
        else:
            strips = ((-12.0, 0.0), (0.0, 12.0))                                 # symmetric
        for a, b in strips:
            c = ((a, 0.0, z + 10.0), (b, 0.0, z + 10.0), (b, 0.0, z), (a, 0.0, z))
            quads.append(Quad16(c, ((a + b) / 2, 0.0, z + 5.0), 7))
    shift = lane_shift(quads, pts)
    assert len(shift) == 200 and LINE_CLEAR >= 2.0 and 0.5 <= SHIFT_TAPER <= 2.0 and SHIFT_GRID_CLEAR[1] >= 24
    assert all(abs(s) < 1e-6 for s in shift[:92] + shift[128:]), shift          # the symmetric road, the grid's zone, the notch: no shift
    assert all(abs(s - (3.0 - 8.0 - LINE_CLEAR)) < 0.26 for s in shift[106:114]), shift[106:114]   # the +8 line LINE_CLEAR inside +3
    assert all(abs(b - a) <= SHIFT_TAPER + 1e-6 for a, b in zip(shift, shift[1:])), shift


def test_lanes_narrow_only_at_the_named_points():
    """Pascal (3 Nov, p22play30: "diablo is screwed again", "never bring it back"): a course-wide narrowing pulled
    Diablo's walls in to its white lines. Nothing narrows outside the points a course plan names; only Amazon's first
    corner is named."""
    from vrtools.arcade.tencourse import COURSES
    from vrtools.convert.collision import lane_scales
    n = 40
    faces = [(9.0, 9.0)] * n                                                     # a curb at 9 everywhere
    assert all(s == (1.0, 1.0) for s in lane_scales(faces))                      # no points named: nothing narrows
    s = lane_scales(faces, ((20, 22),))
    assert all(s[k] == (1.0, 1.0) for k in range(n) if not 20 - 10 <= k <= 22 + 10)   # the taper's reach at most
    assert {p.name: p.lane_points for p in COURSES if p.lane_points} == {"AMAZON FALLS": ((152, 191), (20, 37)),   # 22l: re-indexed from 29-68;
                                                                          "METROPOLIS": ((318, 356),)}    # v0.1.1: the pit exit (Pascal, rec120);
                                                                                                          # 22n: the hairpin's building


def test_lanes_stay_full_at_the_start_line():
    """Phase 22c review (suite s40): Alpine's start gantry legs (drawn 9 out on the left, points 0 and 4) narrowed the
    lines and pulled the wall over the grid and the start-line band (18 spots with no tarmac, grass over the tarmac at
    451). Within LANE_START_CLEAR points of the line either way nothing narrows; narrowing further on tapers up to it."""
    from vrtools.convert.collision import LANE_START_CLEAR, lane_scales
    n = 60
    faces = [(30.0, 30.0)] * n
    for k in (0, 4, n - 2):
        faces[k] = (9.0, 9.0)
    s = lane_scales(faces, ((0, n - 1),))
    for k in list(range(LANE_START_CLEAR + 1)) + list(range(n - LANE_START_CLEAR, n)):
        assert s[k] == (1.0, 1.0), (k, s[k])


@pytest.mark.parametrize("name", ["DIABLO CANYON", "AMAZON FALLS", "PACIFIC COAST", "SURFERS OVAL", "METROPOLIS"])
def test_the_pit_lanes_keep_their_road_beside_the_main_road(saturn_cue, romset_zip, name):
    """Phase 22f: with Diablo's lap on the main road's loop, the pit straight beside it (where the arcade's PIT START
    spawn lands) lies past the rock between the two roads; the trim at the drawn faces had cut it away (9 of 26 slices
    left), as it had cut the loop when the lap ran the pit straight (Pascal: "a contour to go around that is missing").
    The pit lane's slices (place.PIT_LANES) keep their tarmac, and no wall stands on them. Phase 22g (Pascal: "do the
    same as Diablo"): Amazon Falls' and Pacific Coast's pit lanes beside the Saturn's start straight, mid-lap for us
    (an invisible wall closed Amazon's entrance); their lap and placement stay."""
    import os
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.collision import _point_in_xz, saturn_collision
    from vrtools.convert.geometry import placed, to_arcade
    from vrtools.convert.lap import order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, MAIN_ROAD_START, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    rs = RomSet.from_zip(romset_zip)
    from vrtools.convert.place import pit_lane_of
    plan = next(p for p in COURSES if p.name == name)
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    pit = pit_lane_of(sat).slices
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        col, _ = saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)
        segs = {s.index: s for s in sat.segments}
        polys = [[(lambda q: (q[0], 0.0, q[2]))(to_arcade(c[0], 0.0, c[1])) for c in segs[i].corners()] for i in pit if segs[i].corners()]
    tarmac = col.quads[:col.n_tarmac]
    centre = lambda pq: (sum(p[0] for p in pq) / len(pq), sum(p[2] for p in pq) / len(pq))
    bare = [k for k, pq in enumerate(polys) if not any(_point_in_xz(t.corners, *centre(pq)) for t in tarmac)]
    assert not bare, (len(bare), len(polys))
    walls = [q for q, k in zip(col.quads, col.surface) if k == 5]
    assert not [w for w in walls if any(_point_in_xz(pq, *centre(w.corners)) for pq in polys)]



def test_diablos_pit_entry_quad_is_on_the_pit_lane_before_the_spawn(saturn_cue, romset_zip):
    """Phase 22f: the game's pit check (boot 0xfe8e88) sends the player to PIT WORK when the lap-position quad equals
    the entry's pit quad (or that + 1); Diablo's is the tarmac quad at the pit lane's mouth (PitLane.entry_slice),
    away from the main road's loop and before the spawn, so lap 1 starts past it."""
    import math
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.collision import _point_in_xz, pit_entry_quad, saturn_collision
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == "DIABLO CANYON")
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pose = grid_pose(rs, gc)
    pl = choose_placement(sat, pose, grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        col, _ = saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)
        k = pit_entry_quad(sat, col)
        cl = centreline(lap)
    q = col.quads[k]
    assert 0 <= k < col.n_tarmac
    c = (q.centre[0], q.centre[2])
    assert min(math.dist(c, p) for p in cl) > 30                                    # off the main road
    assert not _point_in_xz(q.corners, pose[0], pose[1]) and math.dist(c, pose[:2]) > 30   # before the spawn, not under it


def test_metropolis_upper_deck_takes_no_height_from_the_deck_below(saturn_cue, romset_zip):
    """Phase 22g (Pascal, rec65: at Metropolis's pit entry "the floor disappear"; the car sank 6 units under the drawn
    road): where the lap crosses over itself the nearest race-line point can lie on the other deck (point 126 at -10.5
    over point 277 at -22.9), and a road slice's corner took the lower deck's height (one corner at -21.7, the quad
    tilted 11 units). A slice's corners take their height near its own place on the lap."""
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.collision import _point_in_xz, saturn_collision
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == "METROPOLIS")
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        col, _ = saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)
    # Pascal's stop (rec65), and the pit lane's mouth just past it (rec67: the car ran up quad 0xa4 to +0.4: the cut at
    # the wall had moved a corner keeping its offset from the lower deck's height, 12.6 units, so it stood at +2.1)
    for spot in ((314.7, -257.1), (332.5, -274.0), (336.3, -276.7), (339.7, -279.2)):
        under = [q for q in col.quads[:col.n_tarmac] if _point_in_xz(q.corners, *spot)]
        assert under and all(abs(c[1] - (-10.3)) < 2.0 for q in under for c in q.corners), (spot, [[round(c[1], 1) for c in q.corners] for q in under])


@pytest.mark.parametrize("name", ["DIABLO CANYON", "AMAZON FALLS", "PACIFIC COAST", "SURFERS OVAL", "METROPOLIS", "ALPINE", "SURFERS ROAD"])
def test_the_pit_lane_line_joins_the_race_line_at_both_ends(saturn_cue, romset_zip, name):
    """Phase 22h (Pascal, p22play43: on the HUD map "the pit connection is sometime 'cut' like on diablo, it doesnt merge
    back smoothly into the main road"): the pit lane's strip ended where its own slices end, short of the loop's strip;
    the line starts and ends on the race line."""
    import math
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.collision import pit_lane_line
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == name)
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        cl = centreline(lap)
        line = pit_lane_line(sat, cl)
    assert len(line) >= 3
    assert min(math.dist(line[0], p) for p in cl) < 1.0 and min(math.dist(line[-1], p) for p in cl) < 1.0


@pytest.mark.parametrize("name", ["DIABLO CANYON", "AMAZON FALLS", "PACIFIC COAST", "SURFERS OVAL", "METROPOLIS", "ALPINE", "SURFERS ROAD"])
def test_the_pit_box_lies_down_the_pit_lane_straight_ahead_of_the_entry(saturn_cue, romset_zip, name):
    """Phase 22i (Pascal: "the pit lane should force a pit stop ... similar to the normal track"): the game's pit autopilot
    (boot 0xfe968d) drives the car in a straight line from where PIT WORK fires to the course's pit box and parks it there
    facing the box's heading. Each course's box is `PitLane.depth` units down the lane from its mouth: on a pit-lane quad,
    off the main road, reachable from the entry quad over tarmac only, facing along the lane (the game's heading h gives
    the direction (-sin h, cos h), 1/65536 turn), at the tarmac's height; Diablo's is the spawn, as placed in Phase 22f. Boxes lie mid-lane, at least 130 units in."""
    import math
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.collision import _point_in_xz, pit_box, pit_entry_quad, pit_lane_centres, pit_lane_polygons, saturn_collision
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose, pit_lane_of
    from vrtools.convert.profile import arc_height, road_profile
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == name)
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pose = grid_pose(rs, gc)
    pl = choose_placement(sat, pose, grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        col, _ = saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)
        cl = centreline(lap)
        k = pit_entry_quad(sat, col, cl)
        box = pit_box(sat, col, cl)
        lane = pit_lane_polygons(sat)
    assert k is not None and 0 <= k < col.n_tarmac
    nxt = col.quads[k + 1]                                                     # Phase 22j (Pascal, p22play56: "even on the main we get
    with placed(pl.angle, pl.tx, pl.tz):                                        # pulled into the pit"): the game also fires on the next
        lane_line = pit_lane_centres(sat, cl)                                   # quad in the list, which must belong to the lane: nearer
    nx_, nz_ = nxt.centre[0], nxt.centre[2]                                     # its line than the race line (the build's rule; a
    d_lane = min(math.dist((nx_, nz_), p) for p in lane_line)                   # duplicate of the entry quad, or a side-by-side partner)
    assert d_lane < 20 and d_lane < min(math.dist((nx_, nz_), p) for p in cl), (k, d_lane)
    x, y, z, h = box
    assert 0 <= h < 0x10000
    tarmac = col.quads[:col.n_tarmac]
    assert any(_point_in_xz([(p[0], 0, p[2]) for p in poly], x, z) for poly in lane), "the box is on a pit-lane slice"
    assert min(math.dist((x, z), p) for p in cl) > 10, "off the main road"
    ex, ez = col.quads[k].centre[0], col.quads[k].centre[2]
    run = math.dist((ex, ez), (x, z))
    assert run >= 40, run
    for t in range(0, int(run), 4):                                             # the autopilot's straight line stays on tarmac
        px, pz = ex + (x - ex) * t / run, ez + (z - ez) * t / run
        assert any(_point_in_xz(q.corners, px, pz) for q in tarmac if abs(q.centre[0] - px) < 120 and abs(q.centre[2] - pz) < 120), (t, px, pz)
    under = [q for q in tarmac if _point_in_xz(q.corners, x, z)]
    assert under and min(abs(c[1] - y) for q in under for c in q.corners) < 2.0
    th = h * 2 * math.pi / 65536
    along = ((x - ex) / run, (z - ez) / run)                                    # the lane's run from the entry to the box
    assert -math.sin(th) * along[0] + math.cos(th) * along[1] > 0.8, (h, along)
    if name == "DIABLO CANYON":                                                # Phase 22n: the spawn 40 down the lane, the box 130
        pit = pit_lane_of(sat); gap = pit.depth - pit.spawn_depth
        assert gap - 8 <= math.dist((x, z), pose[:2]) <= gap + 8, ((x, z), pose[:2], gap)
        assert (-math.sin(th) * (x - pose[0]) + math.cos(th) * (z - pose[1])) > 0.9 * gap - 8   # the box ahead of the spawn
    else:                                                                       # Phase 22i (rec84): the entry quad and the next span the
        from vrtools.convert.collision import pit_entry_coverage, pit_lane_centres   # lane's width, so a car cannot pass beside them
        with placed(pl.angle, pl.tx, pl.tz):                                     # (the lane polygons take the placement)
            line = pit_lane_centres(sat, cl)
            i = min(range(len(line)), key=lambda j: math.dist(line[j], (ex, ez)))
            a, b = line[max(0, i - 1)], line[min(len(line) - 1, i + 1)]
            cover = pit_entry_coverage(sat, col, k, line[i], (b[0] - a[0], b[1] - a[1]))
        assert cover >= 0.9, cover
    assert pit_lane_of(sat).pit_stop



@pytest.mark.parametrize("name", ["SURFERS ROAD"])
def test_the_pit_box_cannot_be_reached_from_the_race_line_past_the_entry_pair(saturn_cue, romset_zip, name):
    """v0.1.1 (Pascal, rec118 on Surfers Road: "the pit stop didnt trigger"): the game fires PIT WORK only on the entry quad
    and the next. Surfers Road's lane shares open tarmac with the race lane for its first 140 units, then runs separate:
    an entry in the shared part let a car from the race side cut into the lane past it. On a course whose entry goes where
    the lane runs separate (`PitLane.entry_separate`; the other six keep the open mouths Pascal drove in Phase 22i), every
    way over tarmac from the race line to the box crosses the pair: flood fill from the box over the tarmac within 30 units
    of the lane's line up to the box, the pair's footprint removed, reaches no cell within 6 units of the race centreline."""
    import math
    from vrtools.arcade.tencourse import COURSES, GRID_CLEAR_OF_COURSE, load_saturn_course
    from vrtools.convert.collision import _point_in_xz, _tarmac_quad_at, pit_box, pit_entry_quad, pit_lane_centres, saturn_collision
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == name)
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        col, _ = saturn_collision(sat, hfn, lap=lap, merge=True, cover=True, lane_points=plan.lane_points, grid_clear=GRID_CLEAR_OF_COURSE[gc])
        cl = centreline(lap)
        k = pit_entry_quad(sat, col, cl)
        bx, _, bz, _ = pit_box(sat, col, cl)
        line = pit_lane_centres(sat, cl)
    ib = min(range(len(line)), key=lambda j: math.dist(line[j], (bx, bz)))
    region = line[:ib + 1]
    pair = (col.quads[k].corners, col.quads[k + 1].corners)
    step = 2.0
    def cell(x, z):
        return (round(x / step), round(z / step))
    def open_(c):
        x, z = c[0] * step, c[1] * step
        if min(math.dist((x, z), p) for p in region) > 30:
            return False
        if any(_point_in_xz(q, x, z) for q in pair):
            return False
        return _tarmac_quad_at(col, x, z) is not None
    start = cell(bx, bz); seen = {start}; todo = [start]; reached = []
    near = [p for p in cl if min(math.dist(p, r) for r in region) < 40]
    while todo:
        c = todo.pop()
        x, z = c[0] * step, c[1] * step
        if near and min(math.dist((x, z), p) for p in near) < 6:
            reached.append((x, z))
            continue
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + d[0], c[1] + d[1])
            if n not in seen and open_(n):
                seen.add(n); todo.append(n)
    assert not reached, (name, k, reached[:3])


def test_amazons_pit_exit_wall_stands_at_the_drawn_rock(saturn_cue, romset_zip):
    """v0.1.1 (Pascal, rec120: after the pit stop "i got out of the track boundaries at the exit of the pit where the road
    reconnect with the main road"): past Amazon Falls' pit exit (centreline points 26-35, 40-130 units on) the drawn rock
    on the right stands 7-10 units out, but the wall's floor (WALL_MIN_LATERAL, 12.5) held the wall 2-6 units BEHIND it:
    the car drove into the rock, out of the course, onto the run-off wall. Pascal named the spot (and the other courses'
    exits: only Amazon's has a wall behind a face there): the exit zone is one of the course's named points
    (`CoursePlan.lane_points`) and the wall stands at the face less BARRIER_SETBACK, as on the first corner."""
    import math
    from vrtools.arcade.tencourse import COURSES, GRID_CLEAR_OF_COURSE, load_saturn_course
    from vrtools.arcade.tgp import SURFACE_WALL
    import vrtools.convert.collision as C
    from vrtools.convert.geometry import course_quads, placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == "AMAZON FALLS")
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        col, _ = C.saturn_collision(sat, hfn, lap=lap, merge=True, cover=True, lane_points=plan.lane_points, grid_clear=GRID_CLEAR_OF_COURSE[gc])
        pts = centreline(lap, spacing=C.COVERAGE_SPACING)
        barriers = [q for q in course_quads(sat, groups=C.STEEP_GROUPS) if C.is_barrier(q)] \
            + [q for q in course_quads(sat, groups=C.SOLID_GROUPS) if not C.is_water(q.rgb) and not C.is_shoulder(q)]
        faces = C.fill_faces(C.barrier_faces(barriers, pts, hfn, curbs=[]))
        ex = C.pit_lane_line(sat, pts)[-1]                                         # (the lane takes the placement)
    assert min(range(len(pts)), key=lambda i: math.dist(pts[i], ex)) == 22        # the exit's point (the zone is named by number)
    boxes = C._bboxes(col.quads); dirs = C._smooth_dirs(pts)
    walls = {i for i, k in enumerate(col.surface) if k == SURFACE_WALL}
    late = []
    for k in range(26, 36):
        (x, z), (dx, dz) = pts[k], dirs[k]
        rx, rz = dz, -dx                                                           # the right side (`road_edges`' sign +1)
        lat = 0.0
        while lat <= 40.0:
            px, pz = x + lat * rx, z + lat * rz
            if any(i in walls and b[0] <= px <= b[1] and b[2] <= pz <= b[3] and C._point_in_xz(col.quads[i].corners, px, pz)
                   for i, b in enumerate(boxes)):
                break
            lat += 0.25
        if lat > faces[k][1] + 0.5:
            late.append((k, lat, faces[k][1]))
    assert not late, late


_DIABLO_TRIM: dict = {}
DIABLO_KEY = "a0a0bed1d9fca843"                                                   # Diablo Canyon's TRCK key (place.PIT_LANES)


def _diablo_trim_builds(romset_zip, saturn_cue):
    """Phase 26 stage 4, Task 1: Diablo Canyon's collision as `tencourse.convert_course` makes it (through the builder it uses,
    `tencourse.course_placement` and `course_collision`), built with the named spot's trim (`collision.PIT_LANE_WALL_TRIMS`)
    off (the constant emptied for the call) and on, once per session: {"off" / "on": (col, cells, pts, lane slices)}, pts
    the centreline at COVERAGE_SPACING. convert_course returns no collision."""
    import vrtools.arcade.tencourse as tc
    import vrtools.convert.collision as C
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline
    if not _DIABLO_TRIM:
        rs = RomSet.from_zip(romset_zip)
        plan = next(p for p in tc.COURSES if p.name == "DIABLO CANYON")
        assert not plan.banking
        sat = tc.load_saturn_course(saturn_cue, plan.path)
        pl = tc.course_placement(rs, sat, plan.template, min_coverage=plan.min_coverage, flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            for label in ("off", "on"):
                saved = dict(C.PIT_LANE_WALL_TRIMS)
                if label == "off":
                    C.PIT_LANE_WALL_TRIMS.clear()
                try:
                    b = tc.course_collision(sat, pl, plan.template, min_coverage=plan.min_coverage, banking=plan.banking,
                                            camber=plan.camber, lane_points=plan.lane_points)
                finally:
                    C.PIT_LANE_WALL_TRIMS.clear(); C.PIT_LANE_WALL_TRIMS.update(saved)
                _DIABLO_TRIM[label] = (b.col, b.cells, centreline(b.lap, spacing=C.COVERAGE_SPACING), C.pit_lane_polygons(b.sat))
    return _DIABLO_TRIM


def _inside_by(corners, x, z, margin):
    """(x, z) inside the convex xz polygon `corners` by at least `margin` from every edge (a negative margin: within -margin
    outside it); either winding."""
    n = len(corners); d = []
    for k in range(n):
        ax, az = corners[k][0], corners[k][2]; bx, bz = corners[(k + 1) % n][0], corners[(k + 1) % n][2]
        L = math.hypot(bx - ax, bz - az)
        if L > 1e-12:
            d.append(((bx - ax) * (z - az) - (bz - az) * (x - ax)) / L)
    return all(v >= margin for v in d) or all(v <= -margin for v in d)


def _spot_walls(col, rect):
    """(index, quad) of the wall quads whose footprint lies inside the rectangle (x0, x1, z0, z1)."""
    from vrtools.arcade.tgp import SURFACE_WALL
    x0, x1, z0, z1 = rect
    return [(i, q) for i, q in enumerate(col.quads) if col.surface[i] == SURFACE_WALL
            and all(x0 <= c[0] <= x1 and z0 <= c[2] <= z1 for c in q.corners)]


def _grid(x0, x1, z0, z1, step=0.25):
    import numpy as np
    return [(float(x), float(z)) for x in np.arange(math.ceil(x0 / step) * step, x1 + 1e-9, step)
            for z in np.arange(math.ceil(z0 / step) * step, z1 + 1e-9, step)]


def test_diablos_pit_lane_is_clear_of_walls_at_the_named_spot(saturn_cue, romset_zip):
    """Phase 26 stage 4, Task 1 (recon §3 item 3: driving up Diablo Canyon's pit lane at its centre, a reverse car hit a wall at
    (-389.7, 41.4), lane point about 23, and was thrown onto the sand; Pascal, 14 Nov: trim the wall off the lane): no sample
    point (0.25-unit grid) of the lane's tarmac slices inside the named spot's rectangle lies inside a wall quad's footprint
    (more than 1e-6 inside: a point on the lane's edge is the wall's edge). Built as the build makes it; with the trim off the
    wall step between centreline points 23 and 24 lies over the lane's west half."""
    import vrtools.convert.collision as C
    from vrtools.arcade.tgp import SURFACE_WALL
    col, _, _, polys = _diablo_trim_builds(romset_zip, saturn_cue)["on"]
    rect = C.PIT_LANE_WALL_TRIMS[DIABLO_KEY].rect
    x0, x1, z0, z1 = rect
    walls = [q for i, q in enumerate(col.quads) if col.surface[i] == SURFACE_WALL
             and max(c[0] for c in q.corners) >= x0 and min(c[0] for c in q.corners) <= x1
             and max(c[2] for c in q.corners) >= z0 and min(c[2] for c in q.corners) <= z1]
    lane = [p for p in polys if max(c[0] for c in p) >= x0 and min(c[0] for c in p) <= x1
            and max(c[2] for c in p) >= z0 and min(c[2] for c in p) <= z1]
    assert walls and lane
    samples = [(x, z) for x, z in _grid(*rect) if any(_inside_by(p, x, z, -1e-9) for p in lane)]
    walled = [(x, z) for x, z in samples if any(_inside_by(q.corners, x, z, 1e-6) for q in walls)]
    assert not walled, (len(walled), walled[:5])
    tarmac = [q for q in col.quads[:col.n_tarmac] if max(c[0] for c in q.corners) >= x0 and min(c[0] for c in q.corners) <= x1
              and max(c[2] for c in q.corners) >= z0 and min(c[2] for c in q.corners) <= z1]
    bare = [(x, z) for x, z in samples if not any(_inside_by(q.corners, x, z, -1e-6) for q in tarmac)]   # (the review: no hole
    assert not bare, (len(bare), bare[:5])                                     # left by clip_at_walls / drop_slivers_under_walls)


def test_the_trim_keeps_the_wall_off_the_lane(saturn_cue, romset_zip):
    """Phase 26 stage 4, Task 1 (Pascal's rule: no wall at a drawn rock is removed, moved or disabled; their decision of 14 Nov:
    only the part over the lane's tarmac goes; Review Focus 5): the wall quad at the spot stands partly on the drawn rock
    between the road and the lane. With the trim on, every sample point (0.25-unit grid) of the old quad's footprint that is
    not on the lane's tarmac slices is still inside a wall quad; the new wall quads at the spot lie inside the old footprint
    (nothing new, nothing nearer the road or the lane); and the old quad's road-facing edge (its corners 30 and 36 units out,
    right of centreline points 23 and 24) is an edge of one of them."""
    import vrtools.convert.collision as C
    builds = _diablo_trim_builds(romset_zip, saturn_cue)
    rect = C.PIT_LANE_WALL_TRIMS[DIABLO_KEY].rect
    off, _, pts, polys = builds["off"]
    on = builds["on"][0]
    old = _spot_walls(off, rect)
    assert len(old) == 1, old                                                   # the one quad of the history
    old = old[0][1]
    assert sorted((round(c[0], 1), round(c[2], 1)) for c in old.corners) == \
        sorted([(-400.5, 42.8), (-388.9, 40.0), (-397.1, 31.7), (-408.7, 34.5)])
    new = [q for _, q in _spot_walls(on, rect)]
    assert new
    for q in new:                                                               # convex quads: corners inside, all inside
        assert all(_inside_by(old.corners, c[0], c[2], -1e-6) for c in q.corners), q.corners
    xs = [c[0] for c in old.corners]; zs = [c[2] for c in old.corners]
    lost = [(x, z) for x, z in _grid(min(xs), max(xs), min(zs), max(zs)) if _inside_by(old.corners, x, z, 1e-6)
            and not any(_inside_by(p, x, z, -1e-6) for p in polys)
            and not any(_inside_by(q.corners, x, z, -1e-6) for q in new)]
    assert not lost, (len(lost), lost[:5])
    for q in new:                                                               # heights: an old corner its own y, a new one
        for c in q.corners:                                                     # the old quad's TGP plane at its x, z
            same = [o for o in old.corners if o[0] == c[0] and o[2] == c[2]]
            assert c[1] == (same[0][1] if same else C.tgp_height(old.corners, c[0], c[2])), (c, same)
    dirs = C._smooth_dirs(pts)
    def lateral(c, k):                                                          # (along, right) of corner c from point k
        (x, z), (dx, dz) = pts[k], dirs[k]
        return ((c[0] - x) * dx + (c[2] - z) * dz, (c[0] - x) * dz - (c[2] - z) * dx)
    road = []
    for k, out in ((23, 30.0), (24, 36.0)):
        c = min(old.corners, key=lambda c: abs(lateral(c, k)[0]) + abs(lateral(c, k)[1] - out))
        along, right = lateral(c, k)
        assert abs(along) < 1.0 and abs(right - out) < 0.6, (k, along, right)
        road.append((c[0], c[2]))
    edges = {frozenset(((round(q.corners[j][0], 6), round(q.corners[j][2], 6)), (round(q.corners[(j + 1) % 4][0], 6),
                                                                                   round(q.corners[(j + 1) % 4][2], 6))))
             for q in new for j in range(4)}
    assert frozenset((round(x, 6), round(z, 6)) for x, z in road) in edges


def test_a_named_spot_that_trims_nothing_is_refused():
    """Phase 26 stage 4, Task 1 (the review): a named spot (`PIT_LANE_WALL_TRIMS`) whose rectangle holds no wall quad, or only
    wall quads off the lane, would let the lane wall come back without a word if the course's geometry moved:
    `trim_walls_off_the_lane` refuses it (ConvertError). The control: a wall half over a lane slice is trimmed to its other half."""
    import vrtools.convert.collision as C
    lane = [[(10.0, 0.0, 0.0), (20.0, 0.0, 0.0), (20.0, 0.0, 10.0), (10.0, 0.0, 10.0)]]
    wall = _quad([(5.0, 0.0, 10.0), (15.0, 0.0, 10.0), (15.0, 0.0, 0.0), (5.0, 0.0, 0.0)])
    out, n = C.trim_walls_off_the_lane([wall], lane, (0.0, 30.0, -1.0, 11.0))
    assert n == 1 and len(out) == 1 and sorted((c[0], c[2]) for c in out[0].corners) == [(5.0, 0.0), (5.0, 10.0), (10.0, 0.0), (10.0, 10.0)]
    with pytest.raises(ConvertError):                                           # the wall pokes out of the rectangle
        C.trim_walls_off_the_lane([wall], lane, (6.0, 30.0, -1.0, 11.0))
    off_lane = _quad([(-15.0, 0.0, 10.0), (-5.0, 0.0, 10.0), (-5.0, 0.0, 0.0), (-15.0, 0.0, 0.0)])
    with pytest.raises(ConvertError):                                           # a wall in the rectangle, none of it on the lane
        C.trim_walls_off_the_lane([off_lane], lane, (-20.0, 30.0, -1.0, 11.0))



def test_a_named_spot_trims_the_number_of_quads_it_names():
    """Final review (Minor 6): a named spot carries the number of wall quads it is expected to trim (`WallTrim.quads`; 1 on
    Diablo Canyon), and `trim_walls_off_the_lane` given that number refuses another (ConvertError), as it refuses a zero trim,
    so a second quad drifting into the rectangle stops the build. The zero-trim message names the late wall drop (a wall on
    tarmac goes before the trim) as a possible cause."""
    import vrtools.convert.collision as C
    assert C.PIT_LANE_WALL_TRIMS[DIABLO_KEY] == C.WallTrim((-409.5, -388.0, 31.0, 43.5), 1)
    lane = [[(10.0, 0.0, 0.0), (20.0, 0.0, 0.0), (20.0, 0.0, 10.0), (10.0, 0.0, 10.0)]]
    a = _quad([(5.0, 0.0, 10.0), (15.0, 0.0, 10.0), (15.0, 0.0, 0.0), (5.0, 0.0, 0.0)])         # half over the slice, west
    b = _quad([(15.0, 0.0, 10.0), (25.0, 0.0, 10.0), (25.0, 0.0, 0.0), (15.0, 0.0, 0.0)])       # half over it, east
    rect = (0.0, 30.0, -1.0, 11.0)
    assert C.trim_walls_off_the_lane([a, b], lane, rect, quads=2)[1] == 2
    assert C.trim_walls_off_the_lane([a], lane, rect, quads=1)[1] == 1
    with pytest.raises(ConvertError, match="trims 2 wall quads where it names 1"):
        C.trim_walls_off_the_lane([a, b], lane, rect, quads=1)
    with pytest.raises(ConvertError, match="trims 1 wall quads where it names 2"):
        C.trim_walls_off_the_lane([a], lane, rect, quads=2)
    off_lane = _quad([(-15.0, 0.0, 10.0), (-5.0, 0.0, 10.0), (-5.0, 0.0, 0.0), (-15.0, 0.0, 0.0)])
    with pytest.raises(ConvertError, match="late wall drop"):
        C.trim_walls_off_the_lane([off_lane], lane, (-20.0, 30.0, -1.0, 11.0), quads=1)

def test_the_named_spot_changes_nothing_else(saturn_cue, romset_zip):
    """Phase 26 stage 4, Task 1 (one named spot only): Diablo Canyon built with the trim off and on. The tarmac and verge quads,
    their order and indices are identical (the pit pairs, normal and reverse, are tarmac indices); the quad lists differ only in
    wall quads whose footprint lies inside the spot's rectangle, the other quads keeping their order; a quad in both keeps its
    surface byte (the new ones are walls); and the per-cell lists, read as quads, differ only in cells that meet the rectangle."""
    import vrtools.convert.collision as C
    from vrtools.arcade.tgp import SURFACE_WALL
    builds = _diablo_trim_builds(romset_zip, saturn_cue)
    rect = C.PIT_LANE_WALL_TRIMS[DIABLO_KEY].rect
    (off, off_cells, _, _), (on, on_cells, _, _) = builds["off"], builds["on"]
    assert off.n_tarmac == on.n_tarmac and off.coverage["verges"] == on.coverage["verges"]
    fixed = off.n_tarmac + off.coverage["verges"]
    assert on.quads[:fixed] == off.quads[:fixed] and on.surface[:fixed] == off.surface[:fixed]
    spot_off = {i for i, _ in _spot_walls(off, rect)}; spot_on = {i for i, _ in _spot_walls(on, rect)}
    rest_off = [(q, off.surface[i]) for i, q in enumerate(off.quads) if i not in spot_off]
    rest_on = [(q, on.surface[i]) for i, q in enumerate(on.quads) if i not in spot_on]
    assert rest_on == rest_off
    assert all(on.surface[i] == SURFACE_WALL for i in spot_on)
    x0, x1, z0, z1 = rect
    g = C.CELL_GUARD
    def cell_meets(cell):
        cx0, cz0 = (cell % C.MAP_SIDE) * C.CELL - C.MAP_HALF, (cell // C.MAP_SIDE) * C.CELL - C.MAP_HALF
        return cx0 - g <= x1 and cx0 + C.CELL + g >= x0 and cz0 - g <= z1 and cz0 + C.CELL + g >= z0
    def content(col, cells, cell):
        return [col.quads[i] for i in col.lists[cells[cell]]] if cell in cells else []
    changed = [cell for cell in set(off_cells) | set(on_cells) if content(off, off_cells, cell) != content(on, on_cells, cell)]
    assert all(cell_meets(cell) for cell in changed), [cell for cell in changed if not cell_meets(cell)]


def test_metropolis_pit_box_stands_in_the_tunnel(saturn_cue, romset_zip):
    """Phase 22t (Pascal, 8 Nov: "pit stop on metropolis is too far (outside the tunnel, should be mid of the tunnel"):
    Metropolis's pit lane runs through a tunnel (drawn geometry 8-11 units over the lane from its mouth to about z 340);
    the default box, half the lane's length but at least PIT_BOX_DEPTH_MIN 130 in, fell at the lane's last point, just
    outside it. The box stands under the roof, at least 20 units inside its end, and at least PIT_BOX_MIN_RUN past the
    entry (the game's pit autopilot drives the straight run in between)."""
    import math
    from vrtools.arcade.tencourse import COURSES, GRID_CLEAR_OF_COURSE, load_saturn_course
    import vrtools.convert.collision as C
    from vrtools.convert.geometry import course_quads, placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, road_profile
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == "METROPOLIS")
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
        col, _ = C.saturn_collision(sat, hfn, lap=lap, merge=True, cover=True, lane_points=plan.lane_points, grid_clear=GRID_CLEAR_OF_COURSE[gc])
        cl = centreline(lap)
        x, y, z, h = C.pit_box(sat, col, cl)
        k = C.pit_entry_quad(sat, col, cl)
        line = C.pit_lane_line(sat, cl)
        drawn = C.mesh_heights(course_quads(sat, groups=(0, 1, 2, 3, 4)))
    def roofed(px, pz):
        return any(4 < v - hfn(px, pz) < 60 for v in drawn(px, pz))
    assert roofed(x, z), (x, z)
    d = ((-math.sin(h * 2 * math.pi / 65536)), math.cos(h * 2 * math.pi / 65536))      # on along the lane: still under the roof
    assert all(roofed(x + d[0] * t, z + d[1] * t) for t in range(0, 21, 2)), "within 20 units of the tunnel's end"
    ex, ez = col.quads[k].centre[0], col.quads[k].centre[2]
    assert math.dist((ex, ez), (x, z)) >= C.PIT_BOX_MIN_RUN

# --- Phase 22j: the lap seam under the spawn ---------------------------------------------------------------------------
def _straight_slices(z0: float, z1: float, step: float, w: float = 12.0):
    """Straight +z slices (FL, FR, BR, BL) from z0 to z1, `step` long, flat at y 0, listed from the one at the line (z 0)."""
    from vrtools.arcade.tgp import Quad16
    out = []
    z = z0
    while z < z1 - 1e-9:
        c = ((-w, 0.0, z + step), (w, 0.0, z + step), (w, 0.0, z), (-w, 0.0, z))
        out.append(Quad16(c, (0.0, 0.0, z + step / 2), 7))
        z += step
    return [q for q in out if q.corners[0][2] > 0] + [q for q in out if q.corners[0][2] <= 0]   # in lap order: the head first


def test_the_start_band_leaves_a_strip_beside_the_line_alone():
    """Phase 22n: with Diablo turned 0.55 of the way towards its pit straight, the pit lane's slice after the entry quad
    lay 77 units beside the start line within the band's 108-unit radius, and the band dropped it as a quad wholly
    inside its reach (the lane lost its tarmac right after the entry; the pit box fell back behind it). The band cuts
    only the road at the line: a quad whose corners all lie more than BAND_SIDE beyond the road's measured width stays
    whole (Amazon Falls' and Surfers Road's side slabs 24-28 units out, dropped the same way, left holes the band test
    found)."""
    from vrtools.arcade.tgp import Quad16
    from vrtools.convert.collision import BAND_SIDE, START_BAND, start_line_band
    pts = [(0.0, 10.0 * k) for k in range(30)] + [(0.0, -10.0 * k) for k in range(10, 0, -1)]
    road = _straight_slices(-100.0, 300.0, 10.0)
    side = Quad16(((60.0, 0.0, 8.0), (72.0, 0.0, 8.0), (72.0, 0.0, -8.0), (60.0, 0.0, -8.0)), (66.0, 0.0, 0.0), 7)   # 60 units aside
    out, report = start_line_band(road + [side], pts, lambda x, z: 0.0)
    assert 3.0 <= BAND_SIDE <= 10.0 and START_BAND <= 15.0
    assert any(q.corners == side.corners for q in out), report                   # the strip is untouched
    assert sum(1 for q in out if q.corners == side.corners) == 1


@pytest.mark.parametrize("z0", [-45.0, -40.0])          # a slice straddling the line / one starting exactly at it
def test_the_first_quad_reaches_behind_the_line_under_the_spawn(z0):
    """Phase 22j (Pascal, p22play66 Diablo: the car hangs in the air through the pit phase): the player spawns on road
    point 0, the line, and the placement query finds no quad on a shared edge there once the slices abut exactly — the
    band ends at the line and the head quad began at it. The head quad reaches SEAM_OVERLAP behind the line (under a unit:
    the band stays the certain last-point credit from 11 to 1 units before it)."""
    from vrtools.convert.collision import SEAM_OVERLAP, _point_in_xz, start_line_band
    pts = [(0.0, z) for z in range(0, 50, 10)] + [(0.0, z) for z in range(-50, 0, 10)]
    out, _ = start_line_band(_straight_slices(z0, 45.0, 10.0), pts, lambda x, z: 0.0)
    heads = [q for q in out if min(c[2] for c in q.corners) < 0.5 and max(c[2] for c in q.corners) > 1.0]
    assert heads, [q.corners for q in out]
    assert all(min(c[2] for c in q.corners) == pytest.approx(-SEAM_OVERLAP, abs=0.01) for q in heads), [q.corners for q in heads]
    assert 0.0 < SEAM_OVERLAP < 1.0
    assert any(_point_in_xz(q.corners, 0.0, 0.0) and _point_in_xz(q.corners, 0.0, -SEAM_OVERLAP / 2) for q in heads)
    band = [q for q in out if max(c[2] for c in q.corners) == pytest.approx(0.0, abs=0.01)]
    assert band                                                          # the band still ends at the line


# --- Phase 22k: the run-off's slope and the walls at the drawn faces ------------------------------------------------
def test_the_run_off_rises_no_steeper_than_the_game_takes_for_a_wall():
    """Phase 22k (Pascal: resets with nothing touched; rec91 Diablo 303): the game reads a left/right wheel-height
    difference over 1.2 (front/rear 2.0) as a wall hit — kick, spin, smoke — and the originals' run-off is flat (Big
    Forest: tarmac, kerb, grass and wall at one height). Our run-off follows the drawn ground (Phase 22a), which beside
    a canyon climbs 0.5 a unit, so the spin fired at the tarmac's edge and carried the car over the wall strip into the
    void. Beside a road whose ground climbs 0.6 a unit, every grass and wall quad rises at most VERGE_MAX_SLOPE a unit
    from its inner to its outer line, and the wall's inner line continues the grass (no step between them)."""
    from vrtools.convert.collision import VERGE_GRASS, VERGE_MAX_SLOPE, WALL_WIDTH, road_verges
    quads, pts, _ = _straight_road_near(0.0, half=12.0)
    steep = lambda x, z: 0.0 if abs(x) <= 12.0 else (abs(x) - 12.0) * 0.6
    grass = road_verges(quads, pts, steep, width=VERGE_GRASS, follow=True)
    walls = road_verges(quads, pts, steep, width=WALL_WIDTH, inset=10.0, follow=True)
    assert grass and walls and 0.0 < VERGE_MAX_SLOPE <= 0.3
    for q in grass + walls:
        inner = min(q.corners, key=lambda c: abs(c[0])); outer = max(q.corners, key=lambda c: abs(c[0]))
        rise, run = abs(outer[1] - inner[1]), abs(abs(outer[0]) - abs(inner[0]))
        assert rise <= VERGE_MAX_SLOPE * run + 0.05, (q.corners, rise, run)
    def surface_at(qs, x):
        """The quads' height at (x, z 55), the nearest one across."""
        from vrtools.convert.collision import _point_in_xz, tgp_height
        hs = [tgp_height(q.corners, x, 55.0) for q in qs if _point_in_xz(q.corners, x, 55.0)]
        assert hs, x
        return hs[0]
    for x in (22.3, -22.3):                                           # the wall's inner line (edge 12 + inset 10): grass meets wall
        assert abs(surface_at(walls, x) - surface_at(grass, x)) <= 0.35, x      # (VERGE_SINK apart at most)


def test_the_run_off_follows_the_drawn_ground_up_beside_a_banked_road():
    """Phase 22o (Pascal, p22play99 Oval: "I end up under the grass / mountain"): the verge took its heights from the road
    profile, a plane per centreline point that continues the banked road's tilt sideways, so beside the Oval's second
    banked curve the grass went down 0.13 a unit while the drawn infield bank climbed 0.2 a unit, and a car on the
    grass sat 2-9 units under the drawn mountain. With `ground` (the drawn ground's levels, `mesh_heights`) the verge
    takes the drawn height, still held within VERGE_MAX_SLOPE a unit of the road's edge, so it climbs with the bank."""
    from vrtools.convert.collision import VERGE_GRASS, VERGE_MAX_SLOPE, road_verges
    quads, pts, _ = _straight_road_near(0.0, half=12.0)
    road = lambda x, z: -0.15 * x                                       # banked: down to the right, 1.8 under at the right edge
    quads = [_quad([(c[0], road(c[0], c[2]), c[2]) for c in q.corners]) for q in quads]   # the tarmac on that bank (22o review:
    drawn = lambda x, z: [road(x, z)] if abs(x) <= 12.0 else [road(12.0 if x > 0 else -12.0, z) + (abs(x) - 12.0) * 0.2]   # the bank climbs
    tilted = road_verges(quads, pts, road, width=VERGE_GRASS, follow=True)
    follows = road_verges(quads, pts, road, width=VERGE_GRASS, follow=True, ground=drawn)
    right = lambda vs: [q for q in vs if min(c[0] for c in q.corners) > 5.0]
    assert right(tilted) and right(follows)
    for q in right(follows):                                             # outer corners above the inner ones, within the cap
        inner = min(q.corners, key=lambda c: c[0]); outer = max(q.corners, key=lambda c: c[0])
        run = outer[0] - inner[0]
        assert outer[1] > inner[1] + 0.05 * run, (q.corners,)
        assert outer[1] - inner[1] <= VERGE_MAX_SLOPE * run + 0.05, (q.corners,)
    for q in right(tilted):                                              # the profile alone continues down
        inner = min(q.corners, key=lambda c: c[0]); outer = max(q.corners, key=lambda c: c[0])
        assert outer[1] < inner[1], (q.corners,)
    # another deck 4 units up beside the road (Metropolis's junction: the autopilot climbed onto it and lost the race) is
    # not the verge's ground: the drawn ground must continue the step's inner corner within GROUND_DECK over the first
    # GROUND_PROBE units (a bank rises gradually, a deck jumps), else the profile stands
    from vrtools.convert.collision import GROUND_DECK
    deck = lambda x, z: [road(x, z)] if abs(x) <= 12.0 else [road(12.0 if x > 0 else -12.0, z) + 4.0]
    kept = road_verges(quads, pts, road, width=VERGE_GRASS, follow=True, ground=deck)
    assert 1.0 <= GROUND_DECK <= 2.5
    for q in right(kept):
        inner = min(q.corners, key=lambda c: c[0]); outer = max(q.corners, key=lambda c: c[0])
        assert outer[1] < inner[1] + 0.5, (q.corners,)                     # no step up onto the deck


def test_the_run_off_stays_flat_where_the_drawn_ground_is_flat_until_a_hill_foot():
    """Phase 22o review (the every-course run-off test: 3 % of the grass corners 2-6 units in the air on every course,
    none before): the outer corner, 30 units out, took the drawn hillside's height there while the drawn ground between
    was flat to a hill foot near the wall, so the grass was a ramp in the air over the flat ground, and the clip at the
    wall left its corner 4 units up (Amazon 475, -385). The drawn ground is the outer corner's only where it continues
    the quad's plane (as the cap leaves it) at every GROUND_PROBE along the span, at most GROUND_AIR under it (a bank and a
    kerb lip do, a flat run-off to a hill foot does not; a hole in the mesh is nothing, a span with nothing drawn holds the
    plane to the profile); else the profile's height stands, as before."""
    from vrtools.convert.collision import GROUND_AIR, GROUND_DECK, VERGE_GRASS, road_verges
    assert GROUND_AIR <= 1.0
    quads, pts, _ = _straight_road_near(0.0, half=12.0)
    road = lambda x, z: 0.0
    right = lambda vs: [q for q in vs if min(c[0] for c in q.corners) > 5.0]
    def climb(ground):
        built = right(road_verges(quads, pts, road, width=VERGE_GRASS, follow=True, ground=ground))
        assert built
        return [(max(q.corners, key=lambda c: c[0])[1] - min(q.corners, key=lambda c: c[0])[1], q.corners) for q in built]
    foot = lambda x, z: [0.0] if abs(x) <= 34.0 else [(abs(x) - 34.0) * 1.0]   # flat to 22 units past the edge, then a hillside
    for rise, corners in climb(foot):
        assert abs(rise) <= GROUND_AIR, corners                                   # flat: the hill foot beyond is the wall's
    bank = lambda x, z: [0.0] if abs(x) <= 12.0 else [(abs(x) - 12.0) * 0.2]   # a steady bank is followed
    for rise, corners in climb(bank):
        assert rise > 3.0, corners
    lip = lambda x, z: [0.0] if abs(x) <= 12.0 else [1.3 + (abs(x) - 12.0) * 0.17]   # the Oval 232 R: a kerb lip 1.3 up at the
    for rise, corners in climb(lip):                                               # edge, then the bank: the plane runs under
        assert rise > 3.0, corners                                                 # the lip (GROUND_DECK), the bank followed
    assert GROUND_DECK >= 1.5
    hole = lambda x, z: [0.0] if abs(x) <= 12.0 else ([] if abs(x) < 24.0 else [(abs(x) - 12.0) * 0.2])   # the Oval 234 R:
    for rise, corners in climb(hole):                                              # nothing drawn for 12 units, then the bank
        assert rise > 3.0, corners
    nothing = lambda x, z: [0.0] if abs(x) <= 12.0 else ([] if abs(x) < 41.0 else [6.0])   # a span with nothing drawn but a
    for rise, corners in climb(nothing):                                           # level 6 up at its far corner: the profile
        assert abs(rise) <= GROUND_AIR, corners                                    # (flat) holds the plane down


def test_the_verge_starts_at_the_built_tarmac_edge_height_not_the_profile():
    """Phase 22o review (Pascal, rec112 Oval: "a bug at the top of the curve"): on the first banked curve (point 63 L)
    the tarmac quads, which follow the drawn surface across their width (22a), climbed to 7.1 at the edge while the
    profile read 5.7 there, and the verge's inner corner took the profile — the wall strip beyond the edge lay a unit
    BELOW the banked road, a step down the game never reads as a wall: the car rolled over it, off the collision beyond
    and dropped to the floor. The verge's inner corner now takes the built tarmac's own height under it (the surface
    the car arrives from); the profile only where no tarmac lies under the corner."""
    from vrtools.convert.collision import VERGE_GRASS, VERGE_SINK, road_verges
    quads, pts, flat = _straight_road_near(0.0, half=12.0)
    banked = [_quad([(c[0], 2.0 * (c[0] + 12.0) / 24.0, c[2]) for c in q.corners]) for q in quads]   # 0 at the left edge, 2 at the right
    built = road_verges(banked, pts, flat, width=VERGE_GRASS, follow=True)
    right = [q for q in built if min(c[0] for c in q.corners) > 5.0]
    assert right
    for q in right:
        inner = min(q.corners, key=lambda c: c[0])
        assert inner[1] >= 1.5 + VERGE_SINK - 0.3, (q.corners,)                # from the banked edge, not the flat profile
    left = [q for q in built if max(c[0] for c in q.corners) < -5.0]
    for q in left:
        inner = max(q.corners, key=lambda c: c[0])
        assert abs(inner[1]) <= 0.6, (q.corners,)                              # the left edge is at 0: as before


def test_a_bank_steeper_than_the_cap_is_climbed_at_the_cap_not_left_flat():
    """Phase 22o review (the Oval's first banked curve, point 63 L: the drawn bank beyond the edge rises 0.7 a unit; the
    verge took the profile, 3-7 units under it): a drawn level beyond GROUND_DECK + VERGE_MAX_SLOPE × L of the inner
    corner was left alone and the profile stood. The outer corner now takes the drawn level the span check accepts and
    the cap holds it at VERGE_MAX_SLOPE a unit: the verge climbs towards the bank as steeply as the game allows."""
    from vrtools.convert.collision import VERGE_GRASS, VERGE_MAX_SLOPE, road_verges
    quads, pts, flat = _straight_road_near(0.0, half=12.0)
    steep = lambda x, z: [0.0] if abs(x) <= 12.0 else [(abs(x) - 12.0) * 0.7]   # 0.7 a unit (the Oval's): beyond the cap's reach
    built = road_verges(quads, pts, flat, width=VERGE_GRASS, follow=True, ground=steep)
    right = [q for q in built if min(c[0] for c in q.corners) > 5.0]
    assert right
    for q in right:
        inner = min(q.corners, key=lambda c: c[0]); outer = max(q.corners, key=lambda c: c[0])
        run = outer[0] - inner[0]
        assert outer[1] - inner[1] >= (VERGE_MAX_SLOPE - 0.03) * run, (q.corners,)
        assert outer[1] - inner[1] <= VERGE_MAX_SLOPE * run + 0.05, (q.corners,)
    # a roof 31 units up at the far corner over a hole in the ground mesh (the Oval's stand, 897,-540) is no bank: the ground
    # met along the span must stay within GROUND_SLOPE_MAX a unit (plus GROUND_DECK) of the last ground met
    from vrtools.convert.collision import GROUND_SLOPE_MAX
    assert GROUND_SLOPE_MAX <= 0.8
    roof = lambda x, z: [0.0] if abs(x) <= 12.0 else ([] if abs(x) < 38.0 else [31.0])
    built = road_verges(quads, pts, flat, width=VERGE_GRASS, follow=True, ground=roof)
    for q in [q for q in built if min(c[0] for c in q.corners) > 5.0]:
        inner = min(q.corners, key=lambda c: c[0]); outer = max(q.corners, key=lambda c: c[0])
        assert abs(outer[1] - inner[1]) <= 0.5, (q.corners,)


def test_a_drawn_barrier_between_two_tarmac_strips_gets_a_median_wall_and_the_fill_leaves_its_footprint_open():
    """Phase 22p (Pascal, p22play101 Metropolis: the wall between the pit lane and the race lane "player and opponent can
    cross without any impact"): at points 50-61 the Saturn draws a 4-unit block (two vertical rails, no ground between)
    between the race lane (to 8.8 R) and the pit lane (from 12.8 R). `barrier_faces` finds its near rail at 8.5-9, but the
    coverage fill paved the gap (the band reaches 10-11 and the measured edge runs on across the pit lane), and the wall
    strip never starts inside WALL_MIN_LATERAL. `median_blocks` names, per point and side, a drawn face with tarmac
    beyond it within MEDIAN_MAX as a block from the face to where the drawn ground resumes (at least MEDIAN_MIN wide);
    the fills skip samples inside a block (`blocked`); `median_walls` lays wall quads over each block at the road's
    height; the block's face joins `always`, so the AI lines narrow there (lane_scales)."""
    import math
    from vrtools.convert.collision import (MEDIAN_MAX, MEDIAN_MIN, fill_holes, median_blocked, median_blocks, median_walls,
                                           _point_in_xz, tgp_height)
    race, pts, flat = _straight_road_near(0.0, half=8.8)                  # the race lane: x -8.8..8.8
    pit = [_quad([(c[0] + 21.6, c[1], c[2]) for c in q.corners]) for q in race]   # the pit lane: x 12.8..30.4
    n = len(pts)
    faces = [(math.inf, 8.75) if 4 <= k <= 14 or k == 17 else (math.inf, math.inf) for k in range(n)]   # the near rail, points
    from vrtools.convert.collision import MEDIAN_MIN_RUN                                               # 4-14; an isolated find at 17
    assert 2 <= MEDIAN_MIN_RUN <= 4
    ground = lambda x, z: [] if 8.8 < x < 12.8 else [0.0]                 # no drawn ground in the gap
    blocks = median_blocks(faces, pts, flat, ground, race + pit)
    assert len(blocks) == n and all(b[0] is None for b in blocks)
    assert all(blocks[k][1] is None for k in range(n) if not 4 <= k <= 14)                         # (17: a run of one, dropped)
    for k in range(4, 15):
        f1, f2 = blocks[k][1]
        assert f1 == pytest.approx(8.75 - 0.5, abs=0.3) and 12.3 <= f2 <= 13.3, (k, blocks[k])
    assert 3.0 <= MEDIAN_MAX <= 8.0 and 1.5 <= MEDIAN_MIN <= 3.0
    # a face with no tarmac beyond it is no median (an ordinary edge barrier); a rail on continuous ground gets MEDIAN_MIN
    alone = median_blocks(faces, pts, flat, ground, race)
    assert all(b[1] is None for b in alone)
    on_ground = median_blocks(faces, pts, flat, lambda x, z: [0.0], race + pit)
    assert on_ground[8][1][1] - on_ground[8][1][0] == pytest.approx(MEDIAN_MIN, abs=0.3)
    # the drawn ground may run a little past the face before the gap (Metropolis 52 R: ground to 9.0, the face 8.5, the gap
    # 9.5-12): the block still reaches the ground's resumption beyond the gap, not the ground just past the face
    past = lambda x, z: [] if 9.3 < x < 12.8 else [0.0]
    f1, f2 = median_blocks(faces, pts, flat, past, race + pit)[8][1]
    assert 12.3 <= f2 <= 13.3, (f1, f2)
    # the fills leave the footprint open
    blocked = median_blocked(pts, blocks)
    assert blocked(10.5, 80.0) and not blocked(10.5, 10.0) and not blocked(5.0, 80.0) and not blocked(14.0, 80.0)
    quads, n_tarmac, added = fill_holes(race + pit, len(race + pit), pts, flat, half_width=14.0, blocked=blocked)
    for z in (60.0, 100.0, 140.0):
        assert not any(_point_in_xz(q.corners, 10.5, z) for q in quads[:n_tarmac]), ("the gap was paved", z)
    # the wall quads cover the footprint at the road's height, between the points' blocks only
    walls = median_walls(pts, blocks, flat)
    assert 9 <= len(walls) <= 11
    for z in (50.0, 80.0, 130.0):
        under = [w for w in walls if _point_in_xz(w.corners, 10.5, z)]
        assert under and abs(tgp_height(under[0].corners, 10.5, z)) < 0.05, z
    assert not any(_point_in_xz(w.corners, 10.5, 20.0) for w in walls)
    assert not any(_point_in_xz(w.corners, 7.0, 80.0) for w in walls) and not any(_point_in_xz(w.corners, 14.0, 80.0) for w in walls)


def test_a_prop_with_drawn_road_beyond_it_is_a_post_in_the_road_not_a_road_end():
    """Phase 22p (Pascal, p22play104 Metropolis: "we cant enter the pit"): the pit fence's start post, a placed object 7.5 R
    at point 49, made a face, and the trim cut every quad whose centre is nearest that point back to 12.5 — the Saturn's
    segment widens into the pit mouth there (to 20.5 R), so the mouth went with it and the car met grass and the fence.
    `in_road_faces` drops a prop's face where the drawn ground past it (ROAD_BEYOND samples) has a colour the road has
    under the centreline nearby, at the road's height (`mesh_lookup`): a post in the road; a prop with grass beyond it
    (Amazon's curbs and posts, Phase 22k) keeps its face."""
    import math
    from vrtools.convert.collision import ROAD_BEYOND, ROAD_LEVEL, in_road_faces, mesh_lookup
    from vrtools.convert.geometry import WorldQuad
    _, pts, flat = _straight_road_near(0.0, half=8.8)
    grey, green = (64, 64, 64), (40, 120, 40)
    ground = lambda x0, x1, z0, z1, rgb: WorldQuad(((x0, 0.0, z0), (x1, 0.0, z0), (x1, 0.0, z1), (x0, 0.0, z1)), rgb)
    drawn = [ground(-8.8, 8.8, 0.0, 200.0, grey), ground(8.8, 20.5, 80.0, 120.0, grey),     # the race lane and the mouth
             ground(8.8, 30.0, 0.0, 80.0, green), ground(20.5, 30.0, 80.0, 200.0, green)]   # grass beside the road
    lookup = mesh_lookup(drawn)
    n = len(pts)
    props = [(math.inf, 7.5) if k == 10 else (math.inf, 10.0) if k == 4 else (math.inf, math.inf) for k in range(n)]   # z 100: the post
    out = in_road_faces(props, pts, flat, lookup)                                                # in the mouth; z 40: a post with grass beyond
    assert out[10] == (math.inf, math.inf) and out[4] == (math.inf, 10.0) and len(out) == n
    assert 3 <= len(ROAD_BEYOND) <= 6 and 0.5 <= ROAD_LEVEL <= 1.5
    raised = [ground(8.8, 20.5, 80.0, 120.0, grey)]                                              # the same colour 4 units up: another deck
    raised[0] = WorldQuad(tuple((p[0], 4.0, p[2]) for p in raised[0].p), grey)
    assert in_road_faces(props, pts, flat, mesh_lookup(drawn[:1] + raised))[10] == (math.inf, 7.5)

def test_a_drawn_face_is_followed_across_the_points_where_the_scan_missed_it():
    """Phase 22k (Diablo 310-316 R: the face at 39.5, none found at 313-315, then 17.5): a wall's inset was the narrowest
    grass within 12 points, so the wall stood at 16-21 where the rock was 39.5 out. Between two found faces on a side,
    the missing points take the straight line between them (the rock's outline), within FACE_GAP points; a longer gap
    or a side with no face stays open."""
    from vrtools.convert.collision import FACE_GAP, fill_faces
    inf = math.inf
    faces = [(inf, 39.5)] * 3 + [(inf, inf)] * 3 + [(inf, 17.5)] * 3 + [(inf, inf)] * (FACE_GAP + 2) + [(inf, 20.0)] * 2
    out = fill_faces(faces)
    assert [f[1] for f in out[2:7]] == pytest.approx([39.5, 34.0, 28.5, 23.0, 17.5])
    assert all(f[0] == inf for f in out)                              # the left side: no face anywhere
    assert all(f[1] == inf for f in out[9:9 + FACE_GAP + 2])          # the long gap stays open
    assert len(out) == len(faces)


def test_a_prop_beside_the_road_makes_a_face_but_one_over_the_road_does_not():
    """Phase 22k (3a; Pascal: "go through a wall in full"): the Saturn's placed objects (group 4: gate posts, signs,
    buildings, rock objects) made no wall. Their faces now join the drawn faces from PROP_MIN_LATERAL out (the road is
    trimmed to them and the lanes narrow, as at Amazon's curb); nearer, over the road, they are ignored (Metropolis
    126-128 R: a building's faces 4-6 out would have cut the road), and a prop's face is never nearer than the terrain's own."""
    from vrtools.convert.collision import PROP_MIN_LATERAL, merge_prop_faces
    inf = math.inf
    faces = [(inf, 30.0), (inf, inf), (25.0, inf)]
    props = [(inf, 16.0), (inf, 5.0), (40.0, 9.0)]
    out = merge_prop_faces(faces, props)
    assert out[0] == (inf, 16.0)                          # the prop is the face now
    assert out[1] == (inf, inf)                           # a prop face over the road (5 < PROP_MIN_LATERAL): ignored
    assert out[2] == (25.0, 9.0)                          # the terrain's nearer face stays; a post 9 out counts
    assert 6.0 <= PROP_MIN_LATERAL <= 8.5


def test_a_curb_or_prop_narrows_the_lanes_anywhere_but_a_cliff_only_where_named():
    """Phase 22k (3b; Pascal: "the curb is not detected"): a drawn curb or a placed object inside WALL_MIN_LATERAL gets
    its wall, with the AI lines narrowed there, at every point of the lap (`always`); the terrain's faces keep narrowing
    only at the named points (a course-wide rule pulled Diablo's walls in to its white lines, Phase 22c)."""
    from vrtools.convert.collision import LANE_START_CLEAR, WALL_MIN_LATERAL, lane_scales
    inf = math.inf
    n = 60
    faces = [(inf, inf)] * n
    faces[30] = (inf, 10.0)                                   # a cliff measured 10 out at an unnamed point
    always = [(inf, inf)] * n
    always[45] = (10.0, inf)                                  # a curb 10 out on the left at an unnamed point
    s = lane_scales(faces, (), always=always)
    assert s[30] == (1.0, 1.0)                                # the cliff narrows nothing unnamed
    assert s[45][0] < 1.0 and s[45][1] == 1.0                 # the curb narrows its side
    assert s[45][0] >= 0.5
    s2 = lane_scales(faces, ((28, 32),), always=always)
    assert s2[30][1] < 1.0 and s2[45][0] < 1.0               # named: the cliff too
    assert all(v == (1.0, 1.0) for v in lane_scales(faces, ())) and WALL_MIN_LATERAL > 10.0 and LANE_START_CLEAR < 28


def test_only_a_curb_at_the_roads_edge_or_a_prop_narrows_the_lanes_everywhere():
    """Phase 22k (3b): the faces that narrow the AI lines at every point are a drawn curb standing CURB_MARGIN beyond
    the road's (filled, untrimmed) edge, and a prop's face from PROP_MIN_LATERAL out; a low face measured over the
    road (Diablo 89-92 R: 8.5 out, the road 10 wide — a course-wide rule once pulled the walls in to the white lines)
    narrows nothing unnamed."""
    from vrtools.convert.collision import CURB_MARGIN, PROP_MIN_LATERAL, narrowing_faces
    inf = math.inf
    faces = [(inf, 8.5), (12.5, inf), (inf, 10.0), (inf, inf)]
    curbs = [(False, True), (True, False), (False, True), (False, False)]
    props = [(inf, inf), (inf, inf), (inf, inf), (9.0, 5.0)]
    edges = [(10.0, 10.0), (10.0, 10.0), (10.0, 8.0), (10.0, 10.0)]
    out = narrowing_faces(faces, curbs, props, edges)
    assert out[0] == (inf, inf)                               # a curb 1.5 inside the edge: no
    assert out[1] == (12.5, inf)                              # a curb 2.5 beyond the edge: yes
    assert out[2] == (inf, 10.0)                              # a curb 2 beyond a narrower edge: yes
    assert out[3] == (9.0, inf)                               # a prop 9 out: yes; one 5 out (under PROP_MIN_LATERAL): no
    assert 0.5 <= CURB_MARGIN <= 2.0 and PROP_MIN_LATERAL == 6.5


def test_a_tarmac_sliver_wholly_under_a_wall_is_dropped_but_a_road_or_another_deck_is_not():
    """Phase 22k (Metropolis's hairpin, points 272 / 134: the two roads' tarmacs nearly touch, and a 20-unit sliver of
    the far road's slice lay wholly under this road's wall strip; the TGP gave a car there the sliver, 0.17 nearer its
    height than the wall, and the car was credited the far road — backstep 116). A tarmac quad smaller than
    SLIVER_AREA whose four corners lie inside wall quads at its own height goes; a road-sized quad stays (a wall over a
    road is the wall's mistake), and so does a sliver under a wall of another deck."""
    from vrtools.arcade.tgp import Quad16
    from vrtools.convert.collision import SLIVER_AREA, drop_slivers_under_walls
    def quad(x0, x1, z0, z1, y):
        c = ((x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0)); return Quad16(c, (sum(p[0] for p in c) / 4, y, sum(p[2] for p in c) / 4), 7)
    wall = quad(10.0, 22.0, 0.0, 100.0, 5.0)
    sliver = quad(12.0, 15.0, 40.0, 44.0, 5.1)              # 12 units, under the wall at its height
    road = quad(11.0, 21.0, 10.0, 90.0, 5.0)                # 800 units: a road under a wall is kept
    deck = quad(12.0, 15.0, 60.0, 64.0, 25.0)               # a sliver 20 units above the wall: another deck
    kept, dropped = drop_slivers_under_walls([sliver, road, deck], [wall])
    assert kept == [road, deck] and dropped == 1
    assert 12.0 < SLIVER_AREA <= 60.0


def test_the_wall_meets_the_drawn_face_at_the_setback_not_a_grid_step_before_it():
    """Phase 22k (Pascal, rec98 Diablo 134-146 R: "stopped by something invisible" — the rock drawn 18-21.5 out, the wall
    at 13.5-16.5): the barrier width took the setback, then rounded DOWN to a 2.5-unit grid, and the wall's inner line
    lies WALL_OVERLAP + VERGE_SCAN_STEP inside the grass, so a wheel met the wall 2.5-5 units before the rock. The
    width now lands the wall's inner line within [face - BARRIER_SETBACK, face - BARRIER_SETBACK + BARRIER_QUANT)."""
    from vrtools.convert.collision import BARRIER_QUANT, BARRIER_SETBACK, VERGE_GRASS, VERGE_SCAN_STEP, WALL_OVERLAP, barrier_widths
    inf = math.inf
    for face in (18.0, 20.0, 21.5, 33.3):
        (wl, wr), = barrier_widths([(inf, face)], [(12.0, 12.0)])
        inner = 12.0 + wr - WALL_OVERLAP - VERGE_SCAN_STEP                  # where road_verges puts the wall's inner line
        assert face - BARRIER_SETBACK - 1e-9 <= inner < face - BARRIER_SETBACK + BARRIER_QUANT, (face, wr, inner)
        assert wl == VERGE_GRASS
    assert BARRIER_QUANT <= 1.0


def test_a_barrier_wall_follows_the_drawn_face_from_point_to_point():
    """Phase 22k (Pascal, rec98 Diablo 134-148 R: the rock 18-21.5 out, the wall at 17 along the whole stretch): a wall
    run was a straight strip at the nearest of its points' laterals, and the join slanted the next run back down to it,
    so the wall could never follow a receding face. A barrier run's inner line now runs from one end's own lateral to
    the other's (the face less BARRIER_SETBACK), so along a face stepping 18, 20, 21.5 the wall stands within a unit of
    each point's own place, and consecutive runs meet without a step."""
    from vrtools.convert.collision import (BARRIER_CHORD_TOL, BARRIER_SETBACK, WALL_WIDTH, _bboxes, _point_in_xz, barrier_widths, road_verges,
                                           wall_insets)
    quads, pts, h = _straight_road_near(0.0, half=12.0, length=200.0)
    n = len(pts); inf = math.inf
    face = [18.0] * 5 + [20.0] * 7 + [21.5] * 8
    faces = [(inf, face[k]) for k in range(n)]
    from vrtools.convert.collision import road_edges
    edges = road_edges(quads, pts, h)                                      # as the build: the measured edge (12.5 here)
    fence = barrier_widths(faces, edges)
    ins = [tuple(fence[k][s] for s in (0, 1)) for k in range(n)]            # a drawn barrier's wall at its own point's width
    fine = [(True, False)] * n                                               # the right side is a drawn barrier, not a shore
    walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=ins, follow=True, fine=fine)
    boxes = _bboxes(walls)
    for k in range(2, n - 2):
        x, z = pts[k]
        lat = 4.0
        while lat < 40 and not any(b[0] <= x + lat <= b[1] and b[2] <= z <= b[3] and _point_in_xz(w.corners, x + lat, z) for w, b in zip(walls, boxes)):
            lat += 0.25
        assert abs(lat - (face[k] - BARRIER_SETBACK)) <= BARRIER_CHORD_TOL + 0.3, (k, face[k], lat)   # Pascal: 2.0 (the TGP budget)


def test_a_barrier_wall_run_never_comes_nearer_than_a_point_between_its_ends():
    """Phase 22k (Amazon 39 L on p22play82: a wall 2.8 from the -8 line): a barrier run's straight inner line may pass
    within BARRIER_CHORD_TOL of a point between its ends, but never under that point's wall_min (the AI lines' clearance)
    — the run breaks there instead. Here the AI lanes are
    narrowed to half at both ends of a stretch and taper back to full over five points (wall_min 8.5 at the ends, 12.5
    between, 0.4 a point in between), along a curb drawn 10 units out."""
    import vrtools.convert.collision as C
    from vrtools.convert.collision import WALL_WIDTH, _bboxes, _point_in_xz, barrier_widths, road_edges, road_verges, wall_min
    quads, pts, h = _straight_road_near(0.0, half=12.0, length=200.0)
    n = len(pts); inf = math.inf
    taper = lambda k: min(1.0, 0.5 + 0.1 * min(k, n - 1 - k))             # 0.5 at the ends, 1.0 from point 5 to 14
    C._LANES = [(1.0, taper(k)) for k in range(n)]
    try:
        edges = road_edges(quads, pts, h)
        fence = barrier_widths([(inf, 10.0)] * n, edges)
        walls = road_verges(quads, pts, h, width=WALL_WIDTH, inset=[tuple(f) for f in fence], follow=True, fine=[(True, False)] * n)
        mins = [wall_min(k, 1) for k in range(n)]
    finally:
        C._LANES = None
    boxes = _bboxes(walls)
    for k in range(2, n - 2):
        x, z = pts[k]
        lat = 4.0
        while lat < 40 and not any(b[0] <= x + lat <= b[1] and b[2] <= z <= b[3] and _point_in_xz(w.corners, x + lat, z) for w, b in zip(walls, boxes)):
            lat += 0.25
        assert lat >= mins[k] - 0.3, (k, lat, mins[k])                  # never under the point's own floor


def test_the_slices_near_the_lap_ends_stay_single_so_the_credits_step_by_one():
    """Phase 22l (the Surfers Oval's new line: opponents 1-3 halted 35-47 units before it for the rest of the race):
    a merged straight right before the line was credited its last point along its whole 70 units (384 for points
    377-384), the next quads read n-1, and the field's road point jumped 376 -> 384 -> 386 with the cursor stuck at
    385. MERGE_KEEP_ENDS kept the last three SLICES single, here 30 units; now every slice within MERGE_KEEP_UNITS
    of the lap's start or end stays single too, so the credits step by one point there."""
    from vrtools.convert.collision import MERGE_KEEP_UNITS, merge_straights
    quads, pts, h = _straight_road_near(0.0, half=12.0, length=400.0)     # 40 slices of 10 units
    tarmac, verges, removed = merge_straights([(q, (None, None)) for q in quads])
    singles_each_end = int(MERGE_KEEP_UNITS // 10)
    assert 80.0 <= MERGE_KEEP_UNITS <= 150.0
    assert len(tarmac) >= 2 * singles_each_end + 1, (len(tarmac), removed)
    # the quads at both ends are the slices themselves (10 units long)
    ends = sorted(tarmac, key=lambda q: min(c[2] for c in q.corners))
    assert all(max(c[2] for c in q.corners) - min(c[2] for c in q.corners) <= 10.01 for q in ends[:singles_each_end - 1] + ends[-(singles_each_end - 1):])



def test_long_tarmac_quads_are_split_lap_wide_so_the_cursors_stay_near_their_cars():
    """Phase 22u (Pascal, 8 Nov: "opponents crash randomly in the decor too often ... on most tracks"): an opponent's line
    cursor advances to a point only once the car is credited that point's segment, and steers two points beyond it; a
    long tarmac quad (merged straights, long Saturn slices: up to 70-116 units) credits one point for its whole length,
    so the cursor ran up to 9 points ahead and the car left the road. Measured over a 150-s race per course (out/crash/):
    off-tarmac speed dips 98 -> 43 over the seven courses with every tarmac quad cut to MID_SPLIT_LEN 40 (30: 30, but
    the TGP budget fell to 3 724). Mid-lap quads longer than MID_SPLIT_LEN are cut into equal pieces; the pit lanes'
    quads stay whole (their PIT WORK entry pairs)."""
    from vrtools.arcade.tgp import Quad16
    from vrtools.convert.collision import MID_SPLIT_LEN, split_quads_before_the_line
    assert MID_SPLIT_LEN == 40.0
    pts = [(0.0, float(z)) for z in range(0, 1000, 10)]                  # a straight lap of 100 points along +z
    long_q = Quad16(((-12.0, 0.0, 600.0), (12.0, 0.0, 600.0), (12.0, 0.0, 500.0), (-12.0, 0.0, 500.0)), (0.0, 0.0, 550.0), 7)
    out, cut = split_quads_before_the_line([long_q], pts, lambda x, z: 0.0, units=math.inf, length=MID_SPLIT_LEN)
    assert cut == 1 and len(out) == 3
    assert all(max(c[2] for c in q.corners) - min(c[2] for c in q.corners) <= MID_SPLIT_LEN + 1e-6 for q in out)
    lane = [[(-15.0, 0.0, 450.0), (15.0, 0.0, 450.0), (15.0, 0.0, 650.0), (-15.0, 0.0, 650.0)]]
    kept, cut = split_quads_before_the_line([long_q], pts, lambda x, z: 0.0, units=math.inf, length=MID_SPLIT_LEN, keep=lane)
    assert cut == 0 and kept == [long_q]

def test_long_tarmac_quads_before_the_line_are_split_so_the_credits_step_by_one():
    """Phase 22l (the Surfers Oval's new line): the Saturn's start straight is one 70-unit slice ending 33 units before
    the line, credited one road point (384 for points 377-384); the field's road point jumped 376 -> 384 -> 386 and
    three opponents halted on it with the cursor at 385. Tarmac quads within END_SPLIT_UNITS of the lap's end are cut
    into pieces no longer than END_SPLIT_LEN along the road; the same quad mid-lap stays whole."""
    from vrtools.arcade.tgp import Quad16
    from vrtools.convert.collision import END_SPLIT_LEN, END_SPLIT_UNITS, split_quads_before_the_line
    pts = [(0.0, z) for z in range(0, 600, 10)]                           # a 600-unit straight lap (open: the test's road)
    def slab(z0, z1):
        c = ((-12.0, 0.0, z1), (12.0, 0.0, z1), (12.0, 0.0, z0), (-12.0, 0.0, z0)); return Quad16(c, (0.0, 0.0, (z0 + z1) / 2), 7)
    end_slice = slab(500.0, 570.0)                                        # 70 units, ending 30 before the line (600)
    mid_slice = slab(200.0, 270.0)
    out, n_split = split_quads_before_the_line([mid_slice, end_slice], pts, lambda x, z: 0.0)
    pieces = [q for q in out if min(c[2] for c in q.corners) >= 499.0]
    assert n_split == 1 and len(pieces) >= 5 and all(max(c[2] for c in q.corners) - min(c[2] for c in q.corners) <= END_SPLIT_LEN + 0.01 for q in pieces)
    assert mid_slice in out                                              # mid-lap: untouched
    assert sum(1 for q in out if min(c[2] for c in q.corners) < 300) == 1
    assert 10.0 <= END_SPLIT_LEN <= 20.0 and 100.0 <= END_SPLIT_UNITS <= 200.0
