import math

import pytest

from vrtools.arcade.romset import RomSet
from vrtools.convert.geometry import placed, tile_to_arcade, to_arcade
from vrtools.convert.lap import centreline, order_slices
from vrtools.convert.place import Placement, choose_placement, grid_pose
from tests.test_convert_geometry import _saturn_course


def test_placement_rotates_and_translates_both_frames():
    road0, tile0 = to_arcade(1.0, 0.0, 2.0), tile_to_arcade(1.0, 0.0, 2.0)
    with placed(math.pi / 2, 100.0, -50.0):                              # quarter turn, then a shift
        road, tile = to_arcade(1.0, 0.0, 2.0), tile_to_arcade(1.0, 0.0, 2.0)
    # a quarter turn about the origin maps (x, z) -> (z, -x) in the (x right, z up) frame, then the shift
    assert road == pytest.approx((road0[2] + 100.0, 0.0, -road0[0] - 50.0))
    assert tile == pytest.approx((tile0[2] + 100.0, 0.0, -tile0[0] - 50.0))
    assert to_arcade(1.0, 0.0, 2.0) == pytest.approx(road0)              # cleared on exit


def test_grid_pose_is_big_forests_start(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    x, z, dx, dz = grid_pose(rs, 0)                                        # the player's spawn: 37 left of road point 13
    assert (round(x), round(z)) == (-230, -273) and (dx, dz) == pytest.approx((0.0, 1.0), abs=0.05)
    x, z, _, _ = grid_pose(rs, 0, lateral=0.0)                             # road point 13 itself
    assert (round(x), round(z)) == (-193, -273)


def test_choose_placement_fits_alpine_in_the_map(romset_zip, saturn_cue):
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "ALPINE00/TRCKALPN")
    pl = choose_placement(sat, grid_pose(rs, 0))
    assert isinstance(pl, Placement) and pl.tiles_outside == 0 and pl.max_extent < 1000
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction)
        cl = centreline(lap)
    x, z, dx, dz = grid_pose(rs, 0)
    k = min(range(len(cl)), key=lambda i: (cl[i][0] - x) ** 2 + (cl[i][1] - z) ** 2)
    assert math.hypot(cl[k][0] - x, cl[k][1] - z) < 12                   # the lap passes through the grid pose ...
    assert 10 <= k <= 16                                                   # ... at about road point 13 ...
    d = (cl[(k + 1) % len(cl)][0] - cl[k - 1][0], cl[(k + 1) % len(cl)][1] - cl[k - 1][1])
    assert d[1] > 0 and abs(d[0]) < 0.3 * d[1]                             # ... heading +z
    assert max(max(abs(px), abs(pz)) for px, pz in cl) < 1000



def test_grid_pose_is_the_player_spawn_of_the_template(romset_zip):
    """The game spawns the player relative to the course's road line 0: Big Forest at road point 13, 37 units to the
    left (the grid is in the left lane of a wide straight); Bay Bridge and Acropolis at road point 0 itself
    (measured in MAME: (-230.4, -269.6), (-205.4, 2.5), (-319.7, -190.8)), heading +z. A converted course must
    put its road there for its template, or the car starts beside the road."""
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE
    rs = RomSet.from_zip(romset_zip)
    for course, (x, z) in ((0, (-230.4, -269.6)), (1, (-205.4, 2.5)), (2, (-319.7, -190.8))):
        px, pz, dx, dz = grid_pose(rs, course)
        assert math.dist((px, pz), (x, z)) < 4.0, (course, px, pz)
        assert abs(dx) < 0.1 and dz > 0.99                                    # Acropolis's road point 0 heads 4° off +z
    assert GRID_OF_COURSE[0][0] == 13 and GRID_OF_COURSE[1][0] == GRID_OF_COURSE[2][0] == 0
    assert COURSE_OF_TEMPLATE == {2: 0, 0: 1, 1: 2}


def test_placement_prefers_a_straight_start(romset_zip, saturn_cue):
    """The arcade grids sit on straights: sixteen cars funnelling into a hairpin 100 units after the grid pile up
    (Pacific Coast's first start turned 189 degrees in 300 units and the player crashed into the pack four times).
    Among the starts that fit the map, the one whose first START_STRAIGHT units turn least wins."""
    from vrtools.convert.place import START_STRAIGHT, start_turn
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "PACCOAST/TRCKPACC")
    pl = choose_placement(sat, grid_pose(rs, 1), grid_point=0)
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction)
        cl = centreline(lap)
    assert START_STRAIGHT >= 300 and start_turn(cl, 0) < 60.0                 # was 189; the gentlest start that fits the map


def test_diablo_starts_on_the_main_road_beside_its_pit_lane(saturn_cue, romset_zip):
    """Phase 22f (Pascal, p22play34: "diablo start in the pit lane ... there is a contour to go around that is missing"):
    the lap had started on the pit straight (where the arcade's PIT START spawn lands) and the start-line cut left the
    main road's loop beside it a dead end. As on Big Forest (the line across the main straight, the pit lane beside
    it), Diablo's lap starts on the loop slice level with the spawn: the placement is unchanged, the race line runs
    the whole loop and the pit straight stays a side lane."""
    import math
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, MAIN_ROAD_START, choose_placement, grid_pose
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == "DIABLO CANYON")
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pose = grid_pose(rs, gc)
    pl = choose_placement(sat, pose, grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    assert pl.start_slice == 110 and sum(p.start_slice is not None for p in MAIN_ROAD_START.values()) == 1
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
        cl = centreline(lap)
    on = set(lap.route)
    assert all(i in on for i in list(range(77, 93)) + [100] + list(range(103, 112)))      # the loop
    assert sum(i in on for i in range(48, 66)) <= 2                                       # the pit straight, beside it
    # Pascal ("the pit lane should force a pit stop ... similar to the normal track"): as on Big Forest the spawn lies
    # inside the pit lane past its mouth (the pit-entry quad), so lap 1 starts without a stop: the course is placed
    # with the PIT START spawn PIT_SPAWN_DEPTH units along the pit straight, turned part of the way towards it
    # (all the way does not fit the map), inside MAP_LIMIT
    from vrtools.convert.collision import _point_in_xz
    from vrtools.convert.place import MAP_LIMIT
    with placed(pl.angle, pl.tx, pl.tz):
        segs = {s.index: s for s in sat.segments}
        from vrtools.convert.geometry import to_arcade
        polys = [[(lambda q: (q[0], 0.0, q[2]))(to_arcade(c[0], 0.0, c[1])) for c in segs[i].corners()]
                 for i in MAIN_ROAD_START["a0a0bed1d9fca843"].slices if segs[i].corners()]
    assert any(_point_in_xz(pq, pose[0], pose[1]) for pq in polys)                 # the spawn is on the pit straight
    assert 25 <= math.dist(cl[0], pose[:2]) <= 220 and pl.max_extent < MAP_LIMIT


def test_diablo_spawns_near_the_pit_mouth_so_the_course_can_turn_towards_its_straight(saturn_cue, romset_zip):
    """Phase 22n (Pascal: "the cars still start slanted"): with the spawn PitLane.depth 130 units down the lane the course
    could turn only a fifth of the way towards the pit straight (the loop's far end left the map), and the cars stood 30
    degrees across the straight. The spawn is a separate `spawn_depth` from the box's `depth`: 40 units in, the course
    turns 0.55 of the way (the straight within 17 degrees of the spawn's +z heading; at 0.6 a canyon rock 23 units from the road's far end crosses the map's edge), the road stays inside MAP_LIMIT with nothing drawn off the map and
    the box keeps its 130 (the pit stop parks mid-lane, Pascal's PIT_BOX_DEPTH_MIN)."""
    import math
    from vrtools.arcade.tencourse import COURSES, load_saturn_course
    from vrtools.convert.geometry import placed, to_arcade
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, MAP_LIMIT, choose_placement, grid_pose, pit_lane_of
    rs = RomSet.from_zip(romset_zip)
    plan = next(p for p in COURSES if p.name == "DIABLO CANYON")
    sat = load_saturn_course(saturn_cue, plan.path); gc = COURSE_OF_TEMPLATE[plan.template]
    pit = pit_lane_of(sat)
    assert pit.depth == 130.0 and pit.spawn_depth == 40.0 and pit.turn >= 0.55
    pose = grid_pose(rs, gc)
    pl = choose_placement(sat, pose, grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    assert pl.max_extent < MAP_LIMIT and pl.tiles_outside == 0
    segs = {s.index: s for s in sat.segments}
    with placed(pl.angle, pl.tx, pl.tz):
        line = [to_arcade(sum(c[0] for c in segs[i].corners()) / 4, 0.0, sum(c[1] for c in segs[i].corners()) / 4) for i in pit.path if segs[i].corners()]
    (ax, _, az), (bx, _, bz) = line[2], line[8]                                 # the straight's heading at the spawn
    off = math.degrees(math.atan2(bx - ax, bz - az))
    assert abs((off + 180) % 360 - 180) <= 17.0, off                             # within 17 degrees of +z (was 30)
