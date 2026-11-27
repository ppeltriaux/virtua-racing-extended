"""vrtools.convert.ps2course on a synthetic ring course (no disc), and the two hooks it uses (geometry.encode_cells,
preview.course_picture's faces)."""

import math

import numpy as np
import pytest

from vrtools.arcade.tgp import SURFACE_GRASS, SURFACE_TARMAC, SURFACE_WALL
from vrtools.convert import ps2course as P
from vrtools.convert.geometry import WorldQuad
from vrtools.convert.lap import centreline
from vrtools.ps2 import model, vcp

R, HALF, VERGE, WALL = 200.0, 10.0, 25.0, 35.0      # ring radius, tarmac half width, verge reach, wall distance
KERB = 2.0                                           # a kerb strip on the outer side only


def _ring(r0, r1, kind, step=5.0, y=0.0):
    tris, attrs = [], []
    for a in np.arange(0, 360, step):
        a0, a1 = math.radians(a), math.radians(a + step)
        p = [(r0 * math.cos(a0), y, r0 * math.sin(a0)), (r1 * math.cos(a0), y, r1 * math.sin(a0)),
             (r1 * math.cos(a1), y, r1 * math.sin(a1)), (r0 * math.cos(a1), y, r0 * math.sin(a1))]
        tris += [(p[0], p[1], p[2]), (p[0], p[2], p[3])]
        attrs += [kind, kind]
    return np.array(tris, float), np.array(attrs, np.uint32)


def _wall(r, step=5.0):
    tris = []
    for a in np.arange(0, 360, step):
        a0, a1 = math.radians(a), math.radians(a + step)
        b0, b1 = (r * math.cos(a0), r * math.sin(a0)), (r * math.cos(a1), r * math.sin(a1))
        tris += [((b0[0], 10, b0[1]), (b1[0], 10, b1[1]), (b1[0], -10, b1[1])), ((b0[0], 10, b0[1]), (b1[0], -10, b1[1]), (b0[0], -10, b0[1]))]
    return np.array(tris, float)


def _course():
    parts = [_ring(R - HALF, R + HALF, 0), _ring(R + HALF, R + HALF + KERB, 1), _ring(R + HALF + KERB, R + VERGE, 2),
             _ring(R - VERGE, R - HALF, 2)]
    road = vcp.CollisionSet((0, 0, 0, 0), 6.0, np.concatenate([t for t, _ in parts]), np.concatenate([a for _, a in parts]), 0)
    walls = vcp.CollisionSet((0, 0, 0, 0), 6.0, np.concatenate([_wall(R + WALL), _wall(R - WALL)]), np.ones(288, np.uint32), 0)
    line = np.array([(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in range(0, 360, 10)])
    return road, walls, line


@pytest.fixture(scope="module")
def ring():
    road, walls, line = _course()
    frame = P.Frame(0.0, 0.0, 0.0)                    # arcade = (-x, -y, -z): the ring maps onto itself
    ground, wl = P.Ground([road], frame), P.Walls([walls], frame)
    lap, secs = P.build_lap(ground, wl, -line)
    return lap, secs


def test_frame_turns_half_a_turn_and_flips_y():
    f = P.Frame(10.0, 30.0, -5.0)
    np.testing.assert_allclose(f.pts([[1.0, 2.0, 3.0]]), [[9.0, 28.0, -8.0]])


def test_lap_follows_the_band(ring):
    lap, secs = ring
    assert abs(lap.length - 2 * math.pi * R) < 15
    assert abs(len(secs) - lap.length / P.SECTION_SPACING) <= 1
    w = np.array([s.right - s.left for s in secs])
    assert np.all(np.abs(w - 2 * HALF) <= 1.0)
    r = np.array([math.hypot(*s.centre) for s in secs])
    assert np.all(np.abs(r - R) <= 1.0)
    assert all(s.wall_left is not None and s.wall_right is not None for s in secs)
    assert all(abs(abs(s.wall_left) - WALL) < 1.5 and abs(s.wall_right - WALL) < 1.5 for s in secs)
    assert all(abs(s.ground_right - VERGE) <= 1.0 and abs(s.ground_left + VERGE) <= 1.0 for s in secs)


def test_collision_tarmac_first_then_verges_then_walls(ring):
    lap, secs = ring
    col, cells = P.collision(secs)
    col.check()
    sur = list(col.surface)
    n_t = col.n_tarmac
    assert sur[:n_t] == [SURFACE_TARMAC] * n_t and SURFACE_TARMAC not in sur[n_t:]
    assert set(sur[n_t:]) == {SURFACE_GRASS, SURFACE_WALL}
    import math as _m
    widths = [_m.dist(q.corners[0], q.corners[1]) for q in col.quads[:n_t]]
    assert min(widths) >= 2 * HALF + KERB - 1.5                 # the tarmac band reaches over the outer kerb
    assert sur.count(SURFACE_WALL) == 2 * len(secs)            # both sides walled all round
    assert all(abs(s.kerb_right - (HALF + KERB)) <= 0.75 and s.kerb_left == s.left for s in secs)
    assert set(cells.values()) <= set(col.lists)


def test_attitude_flat_ring_is_level(ring):
    lap, secs = ring
    att = P.attitude(lap, secs, centreline(lap))
    assert all(r == 0 and p == 0 for r, p in att)


def test_pairing_merges_a_square_and_keeps_colours_apart():
    sq = np.array([[(0, 0, 0), (10, 0, 0), (10, 0, 10)], [(0, 0, 0), (10, 0, 10), (0, 0, 10)]], float)
    same = np.array([(100, 50, 25)] * 2, np.uint8)
    quads, pairs = P.pair_triangles(sq, same)
    assert pairs == 1 and len(quads) == 1 and len(set(quads[0].p)) == 4
    two = np.array([(100, 50, 25), (10, 50, 25)], np.uint8)
    quads, pairs = P.pair_triangles(sq, two)
    assert pairs == 0 and len(quads) == 2 and all(q.p[2] == q.p[3] for q in quads)


def _mesh(tris):
    n = len(tris) * 3
    return model.Mesh(0, 0x1813, np.asarray(tris, np.float32).reshape(n, 3), np.zeros((n, 3), np.float32),
                      np.zeros((n, 2), np.float32), np.full((n, 4), 128.0, np.float32))


def test_gates_and_tunnels_on_the_ring(ring):
    lap, secs = ring
    pts = centreline(lap)
    k = len(pts) // 4
    x, z = pts[k]
    gate = [[(-x - 10, 0, -z), (-x + 10, 0, -z), (-x + 10, -5, -z)], [(-x - 10, 0, -z), (-x + 10, -5, -z), (-x - 10, -5, -z)]]

    class C:
        checkpoints = _mesh(gate)
        tunnels = [_mesh([[(-x, -8, -z), (-x + 1, -8, -z), (-x, -9, -z)]])]
    assert P.gate_points(C, P.Frame(0, 0, 0), pts) == [k]
    (a, b), = P.tunnel_stretches(C, P.Frame(0, 0, 0), pts)
    assert a <= k <= b and b - a <= 2 * P.TUNNEL_REACH / 10 + 1


def test_course_picture_takes_quads(ring):
    from vrtools.convert.preview import course_picture
    lap, _ = ring
    grass = [WorldQuad(((0, 0, 0), (5, 0, 0), (5, 0, 5), (0, 0, 5)), (40, 120, 40))] * 3
    sea = [WorldQuad(((300, 0, 300), (320, 0, 300), (320, 0, 320), (300, 0, 320)), (40, 60, 160))]
    pic = course_picture(None, lap, None, None, faces=grass + sea, sea=lambda q: q.rgb == (40, 60, 160))
    assert pic.shape == (168, 128, 3) and pic.dtype == np.uint8


def test_encode_cells_is_convert_tiles_last_stage(romset_zip):
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import TILE_GRID, assign_colours, bin_quads, encode_cells
    rs = RomSet.from_zip(romset_zip)
    quads = [WorldQuad(((x, 0, 0), (x + 8, 0, 0), (x + 8, 0, 8), (x, 0, 8)), (16 * (x % 13), 90, 40)) for x in range(-300, 300, 9)]
    cells, outside = bin_quads(quads, TILE_GRID)
    objs, words, capped = encode_cells(cells, rs, 1)
    assert not outside and not capped and set(objs) == set(cells)
    first = min(cells)
    coloured, w = assign_colours(cells[first], __import__("vrtools.arcade.colours", fromlist=["x"]).palette_from_rom(rs, 1),
                                 tex_start=objs[first][2])
    assert set(w) <= set(words) and objs[first][1].record_count >= len(cells[first])


def test_orient_ground_down_and_uprights_away_from_the_road():
    from vrtools.convert.geometry import _normal
    up = WorldQuad(((0, 0, 0), (0, 0, 10), (10, 0, 10), (10, 0, 0)), (90, 90, 90))       # level, normal +y or -y by winding
    if _normal(up.p)[1] < 0:
        up = WorldQuad(tuple(reversed(up.p)), up.rgb)
    wall = WorldQuad(((20, 0, 0), (20, 10, 0), (20, 10, 10), (20, 0, 10)), (90, 90, 90))  # upright at x 20, the road at x 0
    if _normal(wall.p)[0] > 0:
        wall = WorldQuad(tuple(reversed(wall.p)), wall.rgb)
    road = [(0.0, 0.0), (0.0, 10.0), (0.0, 20.0)]
    out, turned = P.orient([up, wall], road)
    assert turned == 2
    assert _normal(out[0].p)[1] < 0 and _normal(out[1].p)[0] > 0
    again, turned = P.orient(out, road)
    assert turned == 0 and again == out


def test_the_sea_is_lifted_to_just_under_the_road():
    sea = WorldQuad(((0, 27.9, 0), (50, 27.9, 0), (50, 27.9, 50), (0, 27.9, 50)), (70, 100, 202))
    rock = WorldQuad(((0, 30, 0), (5, 31, 0), (5, 32, 5), (0, 30, 5)), (120, 100, 80))
    out, level = P.lift_water([sea, rock], 29.7)
    assert abs(level - 27.9) < 1e-6 and out[1] == rock
    assert all(abs(p[1] - (29.7 - P.WATER_BELOW_ROAD)) < 1e-6 for p in out[0].p)
    assert P.lift_water([rock], 29.7) == ([rock], None)


def test_lane_scales_keep_the_lines_inside_a_narrow_band(ring):
    lap, secs = ring
    pts = centreline(lap)
    sc = P.lane_scales(secs, pts)
    assert len(sc) == len(pts)
    # the ring's band: 10 left, 12 right (the outer kerb): (10 - 4) / 8 and (12 - 4) / 8
    assert all(abs(l - 0.75) < 0.07 and abs(r - 1.0) < 0.07 for l, r in sc)


def test_the_pit_entry_quad_is_doubled_after_the_laps_tarmac(ring):
    lap, secs = ring
    extra = [P._quad([(0, 0, 5), (5, 0, 5), (5, 0, 0), (0, 0, 0)], (0.0, 1.0)), P._quad([(0, 0, 10), (5, 0, 10), (5, 0, 5), (0, 0, 5)], (0.0, 1.0))]
    plain, _ = P.collision(secs)
    col, _ = P.collision(secs, extra, pair=1)
    n = plain.n_tarmac
    assert col.n_tarmac == n + 3
    assert col.quads[n] == extra[0] and col.quads[n + 1] == col.quads[n + 2] == extra[1]


def test_pairing_keeps_a_dashed_strip_in_rectangles():
    # two dashes 10 long, end to end, each two triangles; the triangles meet across the dashes' common end too
    strip = np.array([[(0, 0, 0), (1, 0, 0), (1, 0, 10)], [(0, 0, 0), (1, 0, 10), (0, 0, 10)],
                      [(0, 0, 10), (1, 0, 10), (1, 0, 20)], [(0, 0, 10), (1, 0, 20), (0, 0, 20)]], float)
    quads, pairs = P.pair_triangles(strip, np.array([(240, 240, 240)] * 4, np.uint8))
    assert pairs == 2
    spans = sorted((min(p[2] for p in q.p), max(p[2] for p in q.p)) for q in quads)
    assert spans == [(0, 10), (10, 20)]


def test_roadside_thinning_keeps_uprights_near_the_road():
    road = [(0.0, z) for z in range(0, 200, 10)]
    sign = WorldQuad(((50, 0, 50), (50, 4, 50), (50, 4, 52), (50, 0, 52)), (200, 30, 30))        # upright, 50 from the road
    pebble = WorldQuad(((50, 0, 60), (51, 0, 60), (51, 0, 61), (50, 0, 61)), (90, 90, 90))       # level, small, far
    far_hill = WorldQuad(((400, 0, 0), (420, 30, 0), (420, 30, 20), (400, 0, 20)), (90, 120, 60))
    kept, dropped = P.thin_roadside([sign, pebble, far_hill], 10.0, road)
    assert kept == [sign, far_hill] and dropped == 1
    kept, dropped = P.thin_roadside([sign, pebble, far_hill], 10.0, road, far_cut=300.0)
    assert kept == [sign]


def test_merge_coplanar_joins_a_wall_and_folds_windows_in():
    # a wall 30 wide, 10 high in the plane x = 50, as three 10 x 10 squares, the middle one a window colour
    def sq(z0, rgb):
        return WorldQuad(((50, 0, z0), (50, 10, z0), (50, 10, z0 + 10), (50, 0, z0 + 10)), rgb)
    wall = [sq(0, (150, 150, 150)), sq(10, (60, 90, 160)), sq(20, (150, 150, 150))]
    plain, m0 = P.merge_coplanar(wall)
    assert m0 == 0 and len(plain) == 3                            # the window colour keeps the three apart
    folded, m1 = P.merge_coplanar(wall, windows=True)
    assert m1 == 2 and len(folded) == 1 and folded[0].rgb == (150, 150, 150)
    zs = sorted({p[2] for p in folded[0].p})
    assert zs == [0, 30]
    road = [WorldQuad(((0, 0, 0), (1, 0, 0), (1, 0, 10), (0, 0, 10)), (240, 240, 240))] * 1
    assert P.merge_coplanar(road)[0] == road                      # level faces untouched


def test_far_copies_bring_a_far_hill_into_a_drawn_cell():
    road = [(0.0, float(z)) for z in range(-1000, 1001, 10)]          # a straight road along x = 0, both ways
    hill = WorldQuad(((0, 0, 900), (40, 0, 900), (40, 30, 900), (0, 30, 900)), (90, 120, 60))   # 1 200 units^2, far ahead
    pebble = WorldQuad(((0, 0, 950), (1, 0, 950), (1, 1, 950), (0, 1, 950)), (90, 90, 90))
    out = P.far_copies([hill, pebble], road)
    copies = [q for qs in out.values() for q in qs]
    assert copies == [hill]
    (cell,) = out
    assert cell != P._cell(20, 900)                                   # into a nearer, drawn cell
    assert set(P.visible_cells(0.0, 0.0, 0.0, 1.0)) == set(P.visible_cells(0.0, 0.0, 0.0, 1.0))


def test_covered_stretches_find_an_overpass_not_a_banner():
    pts = [(0.0, float(z)) for z in range(0, 200, 10)]                 # 20 road points along x = 0
    heights = [0.0] * len(pts)
    deck = WorldQuad(((-20, 8, 45), (20, 8, 45), (20, 8, 95), (-20, 8, 95)), (120, 120, 120))   # covers z 50..90
    banner = WorldQuad(((-20, 9, 149), (20, 9, 149), (20, 12, 151), (-20, 12, 151)), (240, 240, 240))
    low = WorldQuad(((-20, 1, 0), (20, 1, 0), (20, 1, 30), (-20, 1, 30)), (90, 90, 90))      # under the clearance
    assert P.covered_stretches([deck, banner, low], pts, heights) == ((5, 9),)
    assert P.join_stretches(((1, 3),), ((4, 8), (20, 22))) == ((1, 8), (20, 22))


def _banner(z0):
    """A checkpoint banner across the road at z = z0: a white panel of two squares and a red letter square on it."""
    w = lambda x0, rgb: WorldQuad(((x0, 8, z0), (x0 + 5, 8, z0), (x0 + 5, 12, z0), (x0, 12, z0)), rgb)
    return [w(-5, (175, 175, 175)), w(0, (175, 175, 175)), WorldQuad(((-1, 9, z0), (1, 9, z0), (1, 11, z0), (-1, 11, z0)), (144, 8, 8))]


def test_a_checkpoint_banner_survives_merging_with_the_windows_folded():
    wall = [WorldQuad(((50, 0, z), (50, 10, z), (50, 10, z + 10), (50, 0, z + 10)), (150, 150, 150)) for z in (0, 10)]
    ban = _banner(30.0)
    out, merges = P.merge_scenery(wall + ban, keep_last=len(ban), windows=True)
    assert merges == 1 and out[-3:] == ban                         # the wall merged, the banner (and its red C.P) untouched
    folded, _ = P.merge_scenery(wall + ban, windows=True)
    assert (144, 8, 8) not in {q.rgb for q in folded}               # without the exemption the letters were folded away


def test_a_banner_far_from_its_gate_is_carried_to_it():
    pts = [(0.0, float(z)) for z in range(0, 400, 10)]               # 40 road points along +z
    heights = [0.0] * 20 + [3.0] * 20
    at_start = _banner(395.0)                                        # where Beltway's both sit: by the line
    near_gate = _banner(150.0)                                       # already at gate 15
    (moved, kept), moves = P.place_banners([at_start, near_gate], pts, heights, [0, 15, 25])
    assert moves[0] == (39, 15) and moves[1] is None and kept == near_gate
    zs = [p[2] for q in moved for p in q.p]
    assert 145 <= min(zs) and max(zs) <= 156                          # now across the road at road point 15
    assert {q.rgb for q in moved} == {q.rgb for q in at_start} and len(moved) == len(at_start)


def test_a_tiny_far_banner_survives_scenery_and_every_tier_of_the_grading(monkeypatch):
    """I6 (fix round 1): a banner far beyond every far cut, its faces smaller than any thinning keeps, on a synthetic course: it
    survives `scenery` (thinning, far cut, orienting) and every tier of every shipped plan (`ps2entry.tier_quads`: scenery at the
    tier's detail, then merged with the windows as the tier says), while a plain face of the same size at the same place is
    dropped. The meshes are stood in for by their faces (`_faces` replaced): what is tested is scenery's handling of them."""
    from types import SimpleNamespace as NS
    from vrtools.arcade import pack as PK
    from vrtools.arcade.ps2entry import tier_quads
    ground = [WorldQuad(((x, 0, z), (x + 10, 0, z), (x + 10, 0, z + 10), (x, 0, z + 10)), (90, 120, 60))
              for x in range(-20, 20, 10) for z in range(0, 100, 10)]
    tiny = lambda x0, z0, rgb: WorldQuad(((x0, 8, z0), (x0 + 0.5, 8, z0), (x0 + 0.5, 8.5, z0), (x0, 8.5, z0)), rgb)
    banner = [tiny(400.0, 400.0, (175, 175, 175)), tiny(400.5, 400.0, (175, 175, 175)), tiny(400.2, 400.0, (144, 8, 8))]
    plain = WorldQuad(((400, 0, 401), (400.5, 0, 401), (400.5, 0, 401.5), (400, 0, 401.5)), (90, 90, 90))   # level: thinned
    course = NS(name="SYNTH", atlases={"cous00": None}, split_sections=[ground + [plain]], sections=[ground + [plain]],
                split_props=[], tunnels=[], props=[], banners=[banner], flags=[])
    monkeypatch.setattr(P, "_faces", lambda meshes, frame, atlas, atlases: ([q for m in meshes for q in m], 0, 0))
    cl = [(0.0, float(z)) for z in range(0, 100, 10)]
    rgbs = lambda qs: sorted(q.rgb for q in qs if min(p[0] for p in q.p) >= 399)
    want = sorted(q.rgb for q in banner)
    q, rep = P.scenery(course, P.Frame(0.0, 0.0, 0.0), cl, far_cut=60.0)
    assert rgbs(q) == want and rep["banner_faces"] == 3                     # the plain face is thinned / cut, the banner kept
    for plan in (PK.ISLAND_TOP, PK.MOUNTAIN_TOP, PK.BELTWAY_TOP):
        for tier in tier_quads(course, P.Frame(0.0, 0.0, 0.0), cl, plan, None, None, None):
            assert rgbs(tier) == want, plan.name


def test_uncovered_finds_ground_the_coarse_mesh_never_had():
    coarse = [WorldQuad(((0, 0, 0), (10, 0, 0), (10, 0, 10), (0, 0, 10)), (90, 120, 60))]
    under = WorldQuad(((2, 0, 2), (4, 0, 2), (4, 0, 4), (2, 0, 4)), (90, 120, 60))
    beyond = WorldQuad(((20, 5, 20), (24, 5, 20), (24, 5, 24), (20, 5, 24)), (90, 120, 60))
    assert P.uncovered([under, beyond], coarse) == [beyond]


def test_merging_keeps_every_bit_of_a_surface():
    # a 4 x 4 wall of triangles (two per square, both diagonals), one colour: whatever merges, the area stays the same
    tris = []
    for i in range(4):
        for j in range(4):
            a, b, c, d = (50, i, j), (50, i + 1, j), (50, i + 1, j + 1), (50, i, j + 1)
            pair = ((a, b, c), (a, c, d)) if (i + j) % 2 else ((a, b, d), (b, c, d))
            tris += [WorldQuad(t + (t[-1],), (150, 150, 150)) for t in pair]
    area = lambda qs: sum(P._poly_area(P._clean_poly(list(q.p))) for q in qs)
    out, merges = P.merge_coplanar(tris)
    assert merges > 0 and abs(area(out) - area(tris)) < 1e-6 and abs(area(tris) - 16) < 1e-6


def _arc_wall(r, a0, a1, step=2.0):
    tris = []
    for a in np.arange(a0, a1, step):
        u0, u1 = math.radians(a), math.radians(min(a + step, a1))
        b0, b1 = (r * math.cos(u0), r * math.sin(u0)), (r * math.cos(u1), r * math.sin(u1))
        tris += [((b0[0], 10, b0[1]), (b1[0], 10, b1[1]), (b1[0], -10, b1[1])), ((b0[0], 10, b0[1]), (b1[0], -10, b1[1]), (b0[0], -10, b0[1]))]
    return tris


def _cap(a, r0, r1):
    u = math.radians(a)
    b0, b1 = (r0 * math.cos(u), r0 * math.sin(u)), (r1 * math.cos(u), r1 * math.sin(u))
    return [((b0[0], 10, b0[1]), (b1[0], 10, b1[1]), (b1[0], -10, b1[1])), ((b0[0], 10, b0[1]), (b1[0], -10, b1[1]), (b0[0], -10, b0[1]))]


def _inside(q, x, z):
    c = [(p[0], p[2]) for p in q.corners]
    s = [(c[(k + 1) % 4][0] - c[k][0]) * (z - c[k][1]) - (c[(k + 1) % 4][1] - c[k][1]) * (x - c[k][0]) for k in range(4)]
    return all(v >= -1e-6 for v in s) or all(v <= 1e-6 for v in s)


def test_a_divider_in_the_road_leaves_both_carriageways_tarmac():
    """Phase 90 (the owner on Beltway: "the road is split in half with pilon separating both side ... i went to the right side and
    keep getting reset"): a wall box standing in the middle of the tarmac (3 units wide, 30-50 degrees round the ring) is a wall
    quad over its footprint with tarmac each side, not the road's edge: no verge or wall strip over either carriageway, the edge
    walls where they were, the box's ends cut where they are (not at the nearest sections)."""
    road, walls, line = _course()
    box = _arc_wall(R - 1.5, 30, 50) + _arc_wall(R + 1.5, 30, 50) + _cap(30, R - 1.5, R + 1.5) + _cap(50, R - 1.5, R + 1.5)
    walls = vcp.CollisionSet((0, 0, 0, 0), 6.0, np.concatenate([walls.triangles, np.array(box, float)]),
                             np.ones(len(walls.triangles) + len(box), np.uint32), 0)
    frame = P.Frame(0.0, 0.0, 0.0)
    ground, wl = P.Ground([road], frame), P.Walls([walls], frame)
    lap, secs = P.build_lap(ground, wl, -line)
    div = [s for s in secs if s.divider is not None]
    assert div and all(abs(s.divider[0] + 1.5) < 0.6 and abs(s.divider[1] - 1.5) < 0.6 for s in div)
    assert all(abs(abs(s.wall_left) - WALL) < 1.5 and abs(s.wall_right - WALL) < 1.5 for s in secs)   # the edges unchanged
    col, cells = P.collision(secs)
    col.check()
    n_t = col.n_tarmac
    at = lambda r, a: (-r * math.cos(math.radians(a)), -r * math.sin(math.radians(a)))   # the arcade frame: (-x, -z)
    for a in (31.0, 35.0, 40.0, 45.0, 49.0):
        for r in (R - 6.0, R + 6.0):                                  # each carriageway: tarmac, under no verge or wall
            x, z = at(r, a)
            assert any(_inside(q, x, z) for q in col.quads[:n_t]), (r, a)
            assert not any(_inside(q, x, z) for q in col.quads[n_t:]), (r, a)
        x, z = at(R, a)                                               # the box: a wall, and no tarmac under it
        assert any(_inside(q, x, z) and s == SURFACE_WALL for q, s in zip(col.quads, col.surface)), a
        assert not any(_inside(q, x, z) for q in col.quads[:n_t]), a
    for a in (27.0, 53.0):                                            # past the box's ends: one band, no wall
        x, z = at(R, a)
        assert any(_inside(q, x, z) for q in col.quads[:n_t]) and not any(_inside(q, x, z) for q in col.quads[n_t:])


def test_beside_a_divider_every_ai_line_keeps_to_one_carriageway():
    """Phase 90 (the owner on pack2f: "seems the oponent didnt crash"; the lead: the opponents rode their lines through the pylons):
    beside the ring's divider box every AI line keeps to the racing side's carriageway, AI_MARGIN from the box and from the
    edge, and comes back to the plain lanes away from it; on the left side when asked."""
    from vrtools.convert.road import road_tables
    road, walls, line = _course()
    box = _arc_wall(R - 1.5, 30, 50) + _arc_wall(R + 1.5, 30, 50) + _cap(30, R - 1.5, R + 1.5) + _cap(50, R - 1.5, R + 1.5)
    walls = vcp.CollisionSet((0, 0, 0, 0), 6.0, np.concatenate([walls.triangles, np.array(box, float)]),
                             np.ones(len(walls.triangles) + len(box), np.uint32), 0)
    frame = P.Frame(0.0, 0.0, 0.0)
    ground, wl = P.Ground([road], frame), P.Walls([walls], frame)
    lap, secs = P.build_lap(ground, wl, -line)
    pts = centreline(lap)
    col, _ = P.collision(secs)
    plain = P.lane_scales(secs, pts, 1)
    for side in (1, -1):
        lanes = P.lane_scales(secs, pts, side, wl)
        t = road_tables(lap, col.quads[:col.n_tarmac], lanes=lanes)
        for k, (x, z) in enumerate(pts):
            a = math.degrees(math.atan2(-z, -x)) % 360            # the ring's angle in the PS2 frame (the box at 30-50)
            r = math.hypot(x, z)
            offs = [math.hypot(ln[k].x, ln[k].z) - r for ln in t.lines[1:]]   # radial: + outward
            if 29 <= a <= 51:                                    # beside the box: one side, AI_MARGIN clear of it and the edge
                inner = [abs(o) for o in offs]
                assert len({o > 0 for o in offs}) == 1, (k, a, offs)
                assert min(inner) >= 1.5 + P.AI_MARGIN - 0.6, (k, a, offs)
                assert max(inner) <= HALF + KERB - 1.0, (k, a, offs)              # on the tarmac (this carriageway is narrow)
            elif not (335 <= a or a <= 105):                      # past the ramps (16 points, about 46 degrees): the plain lanes
                assert lanes[k] == plain[k], (k, a)
        sides = {math.hypot(t.lines[1][k].x, t.lines[1][k].z) > math.hypot(*pts[k])
                 for k, (x, z) in enumerate(pts) if 32 <= math.degrees(math.atan2(-z, -x)) % 360 <= 48}
        assert len(sides) == 1
