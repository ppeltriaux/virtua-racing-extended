import math
import statistics

import pytest

from vrtools.arcade.romset import RomSet
from vrtools.arcade.tgp import decode_collision
from vrtools.convert.geometry import ConvertError, WorldQuad, to_arcade
from vrtools.convert.lap import Lap, order_slices
from vrtools.convert.profile import profile_height, road_profile
from tests.test_convert_geometry import _saturn_course


def _lap_of(n, spacing=11.7):
    """A straight lap along +z (arcade frame) with n centres `spacing` apart."""
    centres = [(0.0, k * spacing) for k in range(n)]
    return Lap(list(range(n)), [k * spacing for k in range(n)], n * spacing, 0, centres)


def _ground(heights, hole=None, size=11.7):
    """Flat ground quads under each lap centre at the given heights; `hole` leaves that centre uncovered."""
    out = []
    for k, h in enumerate(heights):
        if k == hole:
            continue
        z = k * size
        out.append(WorldQuad(((-6, h, z - size / 2), (6, h, z - size / 2), (6, h, z + size / 2), (-6, h, z + size / 2)), (0, 0, 0)))
    return out


def test_profile_fills_holes_and_rejects_cliffs():
    lap = _lap_of(10)
    heights = road_profile(_ground([10.0] * 10, hole=4), lap)
    assert all(math.isfinite(h) for h in heights) and len(heights) == 10
    assert heights[4] == pytest.approx(10.0)
    sloped = road_profile(_ground([0.4 * k for k in range(10)], hole=4), lap)     # gentle: the closing wrap is 3.6
    assert sloped[4] == pytest.approx((sloped[3] + sloped[5]) / 2, abs=0.3)
    with pytest.raises(ConvertError, match="step"):
        road_profile(_ground([0.0] * 6 + [20.0] * 4), lap)
    with pytest.raises(ConvertError, match="ground"):
        road_profile([], lap)


def test_profile_height_interpolates_along_the_lap():
    lap = _lap_of(4)
    h = profile_height(lap, [0.0, 10.0, 20.0, 30.0])
    assert h(0.0, 11.7) == pytest.approx(10.0) and h(0.0, 11.7 * 1.5) == pytest.approx(15.0, abs=0.01)
    assert h(100.0, 11.7 * 2) == pytest.approx(20.0)                     # lateral offset does not matter


@pytest.mark.parametrize("course,name,tol", [(1, "BAYBRIDG/TRCKBAYB", 3.0), (2, "ACROPOLS/TRCKACRO", 3.0)])
def test_real_profile_matches_arcade_heights(romset_zip, saturn_cue, course, name, tol):
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, name)
    lap = order_slices(sat)
    heights = road_profile(sat, lap)
    arcade = decode_collision(rs, course)
    centres = {(round(q.centre[0]), round(q.centre[2])): q.centre[1] for q in arcade.quads}
    pairs = []
    for k in range(0, len(lap.order), 5):
        x, z = lap.centres[k]
        best = min(arcade.quads, key=lambda q: (q.centre[0] - x) ** 2 + (q.centre[2] - z) ** 2)
        if math.hypot(best.centre[0] - x, best.centre[2] - z) < 12:
            pairs.append((heights[k], best.centre[1]))
    assert len(pairs) > 40
    offset = statistics.median(a - s for s, a in pairs)
    assert statistics.median(abs((s + offset) - a) for s, a in pairs) < tol, (offset, len(pairs))


def test_banked_height_tilts_across_the_road_within_the_limit(saturn_cue):
    """Phase 9: the profile ignores lateral offset (no banking); `banked_height` adds the ground mesh's lateral
    delta against the lap centre, clamped, so the Surfers courses' banked turns tilt the collision quads."""
    from vrtools.convert.collision import mesh_height
    from vrtools.convert.lap import centreline
    from vrtools.convert.profile import _ground_quads, banked_height
    sat = _saturn_course(saturn_cue, "SPEEDWAY/TRCKSPEE")
    lap = order_slices(sat, min_coverage=0.8)
    heights = road_profile(sat, lap)
    flat, banked = profile_height(lap, heights), banked_height(lap, heights, mesh_height(_ground_quads(sat)))
    cl = centreline(lap)
    tilts = []
    for k in range(0, len(cl), 10):
        (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % len(cl)]
        d = math.hypot(bx - ax, bz - az); rx, rz = (bz - az) / d, -(bx - ax) / d
        x, z = cl[k]
        tilts.append(banked(x + 10 * rx, z + 10 * rz) - banked(x - 10 * rx, z - 10 * rz))
        assert abs(banked(x, z) - flat(x, z)) < 0.5                       # the centre keeps the profile
    assert max(abs(t) for t in tilts) <= 16.0 and max(abs(t) for t in tilts) > 2.0   # some banking, never beyond the clamp


def test_arc_height_follows_the_profile_and_the_camber_along_the_centreline():
    """Phase 16: the collision's height function takes the arc profile at the nearest 10-unit centreline point (no 2-D
    projection onto lap-order neighbours, which staircases on zigzag strips: Diablo's player climbed in 5-unit steps)
    plus the slice normal's camber along that point's right, clamped to MAX_CAMBER_UNITS."""
    from vrtools.convert.lap import centreline
    from vrtools.convert.profile import MAX_CAMBER_UNITS, arc_height
    from tests.test_convert_road import _ring_lap_with_slices
    lap, segs = _ring_lap_with_slices(n=40, spacing=10.0, bank_deg={**{k: 5.0 for k in range(30, 35)}, 36: 20.0})
    heights = [0.0] * 10 + [float(i) for i in range(1, 11)] + [10.0] * 20
    flat, cambered = arc_height(lap, heights, segs, camber=False), arc_height(lap, heights, segs)
    pts = centreline(lap)
    for k in (5, 12, 15, 25):
        x, z = pts[k]
        assert flat(x, z) == pytest.approx(cambered(x, z), abs=1e-6)                 # the centreline keeps the profile
    x, z = pts[15]                                                                    # on the climb: 1 unit per 10 of arc
    assert flat(x, z) - flat(*pts[14]) == pytest.approx(1.0, abs=0.15)
    def right_of(k, lat):
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % len(pts)]
        d = math.hypot(bx - ax, bz - az); rx, rz = (bz - az) / d, -(bx - ax) / d
        return (pts[k][0] + lat * rx, pts[k][1] + lat * rz)
    k32 = min(range(len(pts)), key=lambda i: math.dist(pts[i], lap.centres[32]))
    assert cambered(*right_of(k32, 8.0)) - flat(*right_of(k32, 8.0)) == pytest.approx(8.0 * math.tan(math.radians(5.0)), abs=0.1)
    k36 = min(range(len(pts)), key=lambda i: math.dist(pts[i], lap.centres[36]))
    assert cambered(*right_of(k36, 10.0)) - flat(*right_of(k36, 10.0)) == pytest.approx(MAX_CAMBER_UNITS, abs=1e-6)


def test_the_profile_follows_a_hump_over_holes_under_the_centres():
    """Phase 20 (recon §3): a route centre over a hole in the ground mesh contributed nothing and the profile bridged its
    neighbours with a straight line, which cut under a climb's curve (Diablo Canyon's first climb: 1.9 units under the
    drawn road). A hump 40 units high over a 351-unit lap of 2.5-unit ground tiles, no ground within 1.5 units of centres
    13-15: the profile there is within 0.4 of the ground (the route's centreline is sampled too; the 5-bin moving median
    rounds the crest by 0.3 with or without holes; before, 2.1 under)."""
    n, sp = 30, 11.7
    L = n * sp
    f = lambda z: 40.0 * math.sin(math.pi * z / L) ** 2
    lap = _lap_of(n, sp)
    lap.route, lap.route_arc = list(lap.order), list(lap.arc)
    holes = [k * sp for k in (13, 14, 15)]
    ground = []
    for i in range(int(L / 2.5)):
        z0, z1 = i * 2.5, (i + 1) * 2.5
        if any(z1 > hz - 1.5 and z0 < hz + 1.5 for hz in holes):
            continue
        ground.append(WorldQuad(((-6, f(z0), z0), (6, f(z0), z0), (6, f(z1), z1), (-6, f(z1), z1)), (0, 0, 0)))
    heights = road_profile(ground, lap)
    for k in (13, 14, 15):
        assert heights[k] == pytest.approx(f(k * sp), abs=0.4), (k, heights[k], f(k * sp))


def test_the_collision_stays_on_the_drawn_road_on_every_course(romset_zip, saturn_cue):
    """Phase 20 (recon §2): along each course's 5-unit centreline, wherever a ground level lies within 4 units of the
    collision, the drawn road and the collision differ by at most 1.25 units, and by over 0.5 at no more than 5 points
    per course; no point with ground under it has no level within 4 units of the collision. Before: 38 points over 1 unit
    (Diablo Canyon's first climb 2.21 under) and 5 beyond 4 (Pacific Coast 120-128, the car about 6 units over the road)."""
    import vrtools.arcade.tencourse as tc
    from vrtools.convert.collision import mesh_heights
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import _ground_quads, arc_height
    rs = RomSet.from_zip(romset_zip)
    bad = {}
    for plan in tc.COURSES:
        sat = tc.load_saturn_course(saturn_cue, plan.path)
        gc = COURSE_OF_TEMPLATE[plan.template]
        pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
            hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
            hs = mesh_heights(_ground_quads(sat))
            gaps, far = [], []
            for k, (x, z) in enumerate(centreline(lap, spacing=5.0)):
                c = hfn(x, z)
                levels = hs(x, z)
                near = [v for v in levels if abs(v - c) < 4.0]
                if near:
                    gaps.append((round(min(near, key=lambda v: abs(v - c)) - c, 2), k))
                elif levels:                                  # ground under the point, none near the collision (review:
                    far.append((round(min(levels, key=lambda v: abs(v - c)) - c, 2), k))   # Pacific 120-128 was 6 off)
        over = [g for g in gaps if abs(g[0]) > 0.5]
        if len(over) > 5 or any(abs(g[0]) > 1.25 for g in gaps) or far:
            bad[plan.name] = (len(over), sorted(gaps, key=lambda g: -abs(g[0]))[:4], far[:4])
    assert not bad, bad


def test_the_collision_leans_with_the_drawn_banking(romset_zip, saturn_cue):
    """Phase 22a (recon §1): where the drawn road (the ground mesh 8 units either side of the 5-unit centreline) banks
    more than 6 degrees, the collision's tilt between the same two points is within 1.5 degrees of it, except at most
    three points per course (a one-point peak the three-point average smooths), none off by more than 3.5. Before: the
    side tilt came from the slice normals (up to 5 degrees off the drawn road) capped at 1.3 units (9.2 degrees at the
    AI lines) against 12.8 drawn on Surfers Road: 3-36 points per course."""
    import vrtools.arcade.tencourse as tc
    from vrtools.convert.collision import mesh_heights
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import _ground_quads, arc_height
    rs = RomSet.from_zip(romset_zip)
    bad = {}
    for plan in tc.COURSES:
        sat = tc.load_saturn_course(saturn_cue, plan.path)
        gc = COURSE_OF_TEMPLATE[plan.template]
        pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
            hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
            hs = mesh_heights(_ground_quads(sat))
            cl = centreline(lap, spacing=5.0)
            n, miss = len(cl), []
            for k, (x, z) in enumerate(cl):
                (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
                d = math.hypot(bx - ax, bz - az) or 1.0
                rx, rz = (bz - az) / d, -(bx - ax) / d
                ends = []
                for lat in (-8.0, 8.0):
                    px, pz = x + lat * rx, z + lat * rz
                    col = hfn(px, pz)
                    near = [v for v in hs(px, pz) if abs(v - col) < 8.0]
                    if not near:
                        break
                    ends.append((min(near, key=lambda v: abs(v - col)), col))
                if len(ends) == 2:
                    drawn = math.degrees(math.atan2(ends[1][0] - ends[0][0], 16.0))
                    coll = math.degrees(math.atan2(ends[1][1] - ends[0][1], 16.0))
                    if abs(drawn) > 6.0 and abs(drawn - coll) > 1.5:
                        miss.append((k, round(drawn, 1), round(coll, 1)))
        if len(miss) > 3 or any(abs(d - c) > 3.5 for _, d, c in miss):
            bad[plan.name] = (len(miss), miss[:4])
    assert not bad, bad


def test_the_collision_is_the_drawn_road_out_to_the_walls(romset_zip, saturn_cue):
    """Phase 22a rework (Pascal's replay: on Diablo's banked curves the cars drift 13-32 units out, where the drawn ground
    rose 1-7 units above the collision): from every 10-unit centreline point, both sides, every 2 units out to the first
    wall (or 28 units), wherever the ground mesh has a level within 8 units of the collision's height function, it is
    within 1.0 of the nearest level at 99 % of the samples and within 3.0 at all (measured 2.3-2.8 at 20-28 out where
    the ground thins; the old height function was 7.8 off there)."""
    from tests.test_convert_collision import _all_covered_collisions
    import vrtools.arcade.tencourse as tc
    from vrtools.arcade.tgp import SURFACE_WALL
    from vrtools.convert.collision import _bboxes, _point_in_xz, mesh_heights
    from vrtools.convert.geometry import placed
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import _ground_quads
    rs = RomSet.from_zip(romset_zip)
    bad = {}
    for plan in tc.COURSES:
        col, lap, cl, hfn = _all_covered_collisions(saturn_cue)[plan.name]
        sat = tc.load_saturn_course(saturn_cue, plan.path)
        gc = COURSE_OF_TEMPLATE[plan.template]
        pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            hs = mesh_heights(_ground_quads(sat))
        walls = [q for q, k in zip(col.quads, col.surface) if k == SURFACE_WALL]
        wb = _bboxes(walls)
        in_wall = lambda x, z: any(b[0] <= x <= b[1] and b[2] <= z <= b[3] and _point_in_xz(w.corners, x, z) for w, b in zip(walls, wb))
        n, gaps = len(cl), []
        for k, (x, z) in enumerate(cl):
            (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
            d = math.hypot(bx - ax, bz - az) or 1.0
            rx, rz = (bz - az) / d, -(bx - ax) / d
            for sign in (-1, 1):
                for lat in range(0, 29, 2):
                    px, pz = x + sign * lat * rx, z + sign * lat * rz
                    if in_wall(px, pz):
                        break
                    c = hfn(px, pz)
                    near = [v for v in hs(px, pz) if abs(v - c) < 8.0]
                    if near:
                        gaps.append((abs(min(near, key=lambda v: abs(v - c)) - c), k, sign * lat))
        over1 = sum(1 for g in gaps if g[0] > 1.0)
        worst = max(gaps)
        if over1 > 0.01 * len(gaps) or worst[0] > 3.0:
            bad[plan.name] = (over1, len(gaps), tuple(round(v, 2) for v in worst))
    assert not bad, bad


def test_the_drawn_surface_is_followed_never_another_deck():
    """Phase 22a rework (Metropolis 541-544: the road at -24.6, another deck at -8 beyond a gap; a follower allowed to
    grow its reach across holes ramped the collision 16 units up to it): a flat road at 0 with a deck at +16 from
    lateral 22 on, holes between: the collision stays at 0 out to the deck and never climbs towards it."""
    from vrtools.convert.profile import arc_height
    n, sp = 30, 11.7
    lap = _lap_of(n, sp)
    lap.route, lap.route_arc = list(lap.order), list(lap.arc)
    L = n * sp
    road = [WorldQuad(((-14, 0.0, z), (14, 0.0, z), (14, 0.0, z + 2.5), (-14, 0.0, z + 2.5)), (0, 0, 0))
            for z in [i * 2.5 for i in range(int(L / 2.5))]]
    deck = [WorldQuad(((22, 16.0, z), (40, 16.0, z), (40, 16.0, z + 2.5), (22, 16.0, z + 2.5)), (0, 0, 0))
            for z in [i * 2.5 for i in range(int(L / 2.5))]]
    h = arc_height(lap, road_profile(road, lap), None, camber=True, ground=road + deck)
    for z in (50.0, 120.0, 200.0):
        for x in (0.0, 10.0, 16.0, 20.0):
            assert abs(h(x, z)) < 0.3, (x, z, h(x, z))


def test_the_height_has_no_step_between_centreline_points(romset_zip, saturn_cue):
    """Phase 22a review: the residual row was looked up in the nearest centreline point's own frame; halfway between two
    points on a curve the two frames disagree, and 20-28 units out the height stepped 1.2-1.8 units (Surfers Road 31-34,
    89-90; Diablo 313). Walking each course 0.25 units at a time along laterals 16-28, the height never changes by more
    than 1.0 between two samples where the drawn ground under both changes by less than 0.25 (inside a tight bend, where
    the nearest centreline point jumps by more than one between samples, several legs' frames meet: not measured)."""
    import vrtools.arcade.tencourse as tc
    from vrtools.convert.collision import mesh_heights
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import _ground_quads, arc_height
    rs = RomSet.from_zip(romset_zip)
    bad = {}
    for name in ("SURFERS ROAD", "DIABLO CANYON", "AMAZON FALLS"):
        plan = next(p for p in tc.COURSES if p.name == name)
        sat = tc.load_saturn_course(saturn_cue, plan.path)
        gc = COURSE_OF_TEMPLATE[plan.template]
        pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
            hfn = arc_height(lap, road_profile(sat, lap), sat.segments, camber=plan.camber, ground=sat)
            hs = mesh_heights(_ground_quads(sat))
            cl = centreline(lap, spacing=0.25)
            cl10 = centreline(lap, spacing=10.0)
            n, m, steps = len(cl), len(cl10), []
            nearest = lambda x, z: min(range(m), key=lambda i: (cl10[i][0] - x) ** 2 + (cl10[i][1] - z) ** 2)
            for lat in (-28, -20, 20, 28):
                prev = None
                for k in range(n):
                    (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
                    d = math.hypot(bx - ax, bz - az) or 1.0
                    px, pz = cl[k][0] + lat * (bz - az) / d, cl[k][1] - lat * (bx - ax) / d
                    h = hfn(px, pz)
                    g = hs(px, pz)
                    p10 = nearest(px, pz)
                    jump = prev is not None and min((p10 - prev[2]) % m, (prev[2] - p10) % m) > 1   # inside a tight bend
                    if prev is not None and not jump and g and prev[1] and abs(min(g) - min(prev[1])) < 0.25 and abs(h - prev[0]) > 1.0:
                        steps.append((k // 40, lat, round(h - prev[0], 2)))
                    prev = (h, g, p10)
        if steps:
            bad[name] = (len(steps), steps[:4])
    assert not bad, bad
