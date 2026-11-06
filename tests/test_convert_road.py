import math
import statistics

import pytest

from vrtools.arcade.course import course_table, road_lines
from vrtools.arcade.romset import RomSet
from vrtools.arcade.tgp import Quad16
from vrtools.convert.collision import saturn_collision
from vrtools.convert.geometry import ConvertError
from vrtools.convert.lap import Lap, order_slices
from vrtools.convert.road import RoadTables, heading_word, road_tables
from tests.test_convert_geometry import _saturn_course
from tests.test_convert_lap import _square_loop


def _circle_lap_and_quads(n=40, spacing=11.7):
    sat, _ = _square_loop(n_per_side=n // 4)
    lap = order_slices(sat, start_slice=0)
    quads = []
    for x, z in lap.centres:
        quads.append(Quad16(((x - 2, 0, z - 2), (x + 2, 0, z - 2), (x + 2, 0, z + 2), (x - 2, 0, z + 2)), (x, 0, z), 0))
    return lap, quads


def test_road_tables_shape_flags_and_links():
    lap, quads = _circle_lap_and_quads()
    t = road_tables(lap, quads, spacing=10.0)
    n = len(t.lines[0])
    assert isinstance(t, RoadTables) and all(len(l) == n for l in t.lines) and len(t.lines) == 8
    assert len(t.segments) == len(quads)
    assert [s.index for s in t.segments] == list(range(len(quads)))
    rp = [s.road_point for s in t.segments]
    assert all(0 <= p < n for p in rp) and all(b >= a for a, b in zip(rp, rp[1:]))
    assert all(s.flag == 1 for s in t.segments)          # flag 66 marks pit-lane segments; a converted course has no pit lane
    assert t.lines[0][0].link >> 16 == 0 and all((p.link >> 16) < len(quads) for p in t.lines[0])
    assert all(math.hypot(b.x - a.x, b.z - a.z) >= 2 for a, b in zip(t.lines[0], t.lines[0][1:]))
    assert all(math.hypot(b.x - a.x, b.z - a.z) >= 2 for a, b in zip(t.lines[1], t.lines[1][1:]))


def test_road_tables_rejects_bad_input():
    lap, quads = _circle_lap_and_quads()
    with pytest.raises(ConvertError):
        road_tables(lap, [], spacing=10.0)
    with pytest.raises(ConvertError):
        road_tables(lap, quads, spacing=0.5)                         # points closer than 2 units


def test_heading_word_convention(romset_zip):
    """The centreline heading word's high half is the direction in 1/16384 turn, the same angle as the quad
    attribute (-atan2(dx, dz)) at a quarter of the resolution: check against the arcade's own Big Forest line."""
    rs = RomSet.from_zip(romset_zip)
    c = road_lines(rs, course_table(rs)[0])[0]
    n = len(c); ok = 0
    for i in range(n):
        a, b = c[i - 1], c[(i + 1) % n]
        w = heading_word(b.x - a.x, b.z - a.z)
        diff = ((w >> 16) - (c[i].heading >> 16) + 8192) % 16384 - 8192
        ok += abs(diff) < 200                                           # 4.4 degrees
    assert ok / n > 0.9, ok


def test_real_big_forest_tables_match_the_arcade(romset_zip, saturn_cue):
    rs = RomSet.from_zip(romset_zip); e = course_table(rs)[0]
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    col, _ = saturn_collision(sat, height=lambda x, z: 30.0, lap=lap)
    n_tarmac = sum(1 for s in sat.segments if s.corners() is not None)
    t = road_tables(lap, col.quads[:n_tarmac])
    arcade = road_lines(rs, e)[0]
    d = [min(math.hypot(p.x - a.x, p.z - a.z) for a in arcade) for p in t.lines[0][::4]]
    assert statistics.median(d) < 8 and max(d) < 40, (statistics.median(d), max(d))
    assert abs(len(t.lines[0]) - len(arcade)) < 0.15 * len(arcade), (len(t.lines[0]), len(arcade))


def _hi(word):
    return ((word >> 16) ^ 0x8000) - 0x8000


def test_heading_words_are_unwrapped_and_continuous():
    """The arcade stores the heading unwrapped along the lap (Big Forest runs 56 → −16493 over one clockwise lap,
    largest step 778): no jump of a turn anywhere, and every line carries the same values."""
    lap, quads = _circle_lap_and_quads()
    t = road_tables(lap, quads, spacing=10.0)
    hi = [_hi(p.heading) for p in t.lines[0]]
    assert abs(hi[0]) <= 8192
    assert max(abs(b - a) for a, b in zip(hi, hi[1:])) < 1000
    assert abs(hi[-1] - hi[0]) > 15000                                   # a loop accumulates a full turn
    assert [_hi(p.heading) for p in t.lines[3]] == hi


def _big_forest_tables(saturn_cue):
    """Big Forest regenerated from the Saturn data with merged collision (the Phase 6 build)."""
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    col, _ = saturn_collision(sat, lambda x, z: 30.0, lap=lap, merge=True)
    return road_tables(lap, col.quads[:col.n_tarmac])


def test_segments_pin_the_lap_ends(saturn_cue):
    """Phase 10 (formats §15): the first segment maps to road point 0 and the last to n−1, so a car crossing the
    start line is credited with the line's last point before its road point wraps — the opponent cursor can wrap too."""
    from vrtools.convert.road import SEGMENT_BACK
    t = _big_forest_tables(saturn_cue)
    n = len(t.lines[0])
    assert t.segments[0].road_point == 0 and t.segments[-1].road_point == n - 1, (t.segments[0], t.segments[-1], n)
    progress = 0                                          # along the lap: never more than SEGMENT_BACK behind the walk's
    for s in t.segments:                                  # progress (Phase 22m: a quad listed after one further ahead keeps
        assert s.road_point >= progress - SEGMENT_BACK, (s, progress)   # its own front's point)
        progress = max(progress, s.road_point)


def test_links_name_a_segment_the_car_has_reached(saturn_cue):
    """Phase 10 (formats §15): an opponent's cursor advances past line point p only when the segment named by the
    point's link (high half) has a road point the car has reached, so every point names a segment with the GREATEST
    road point at or before it (the first segment before any; Phase 22m: by road point, not list position, since a
    credit may step back within SEGMENT_BACK); the named road points are monotone and exact at the pinned ends."""
    t = _big_forest_tables(saturn_cue)
    n = len(t.lines[0]); segs = t.segments
    for line in t.lines:
        named = [pt.link >> 16 for pt in line]
        assert all(segs[s].road_point <= p for p, s in enumerate(named)), [(p, s, segs[s].road_point) for p, s in enumerate(named) if segs[s].road_point > p][:5]
        assert all(segs[b].road_point >= segs[a].road_point for a, b in zip(named, named[1:]))
        assert segs[named[0]].road_point == 0 and segs[named[-1]].road_point == n - 1
        exact = sum(1 for p, s in enumerate(named) if segs[s].road_point == p)
        assert exact >= len({s.road_point for s in segs})
        assert all(segs[named[p]].road_point == max(s.road_point for s in segs if s.road_point <= p) for p in range(0, n, 7))


def test_segments_credit_the_front_of_each_quad(saturn_cue):
    """Phase 10 (formats §15): a car's road point is its lap-position quad's segment; with 60-unit merged quads a car
    in the front part of a quad credited with the quad's centre has its cursor's target (cursor + 2) at or behind
    it and stops. Each quad's road point is therefore the centreline point nearest its FRONT edge, so the car is
    never credited less than its own point."""
    import math
    from vrtools.convert.collision import saturn_collision
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    lap = order_slices(sat)
    col, _ = saturn_collision(sat, lambda x, z: 30.0, lap=lap, merge=True)
    quads = col.quads[:col.n_tarmac]
    t = road_tables(lap, quads)
    pts = [(p.x, p.z) for p in t.lines[0]]; n = len(pts)
    nearest = lambda x, z: min(range(n), key=lambda i: (pts[i][0] - x) ** 2 + (pts[i][1] - z) ** 2)
    ahead = 0
    for q, s in zip(quads, t.segments):
        fx, fz = (q.corners[0][0] + q.corners[1][0]) / 2, (q.corners[0][2] + q.corners[1][2]) / 2
        front = nearest(fx, fz); centre = nearest(q.centre[0], q.centre[2])
        if math.hypot(pts[front][0] - fx, pts[front][1] - fz) > 15 or math.hypot(pts[centre][0] - q.centre[0], pts[centre][1] - q.centre[2]) > 15:
            continue                                                          # the nearest point is on another part of the road: ambiguous
        if (front - centre) % n > 1 and abs(front - centre) < n // 2:          # a quad longer than a point: its road point is its front
            ahead += 1
            assert abs(s.road_point - front) <= 1 or s.road_point in (0, n - 1), (s, front, centre)
    assert ahead > 30


_TABLES: dict = {}


def _all_course_tables(saturn_cue):
    """Road tables of all seven converted courses (placed, merged collision), built once per session."""
    import os
    from vrtools.arcade.romset import RomSet
    import vrtools.arcade.tencourse as tc
    from vrtools.convert.collision import saturn_collision
    from vrtools.convert.geometry import placed
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    from vrtools.convert.profile import arc_height, profile_height, road_profile
    if not _TABLES:
        rs = RomSet.from_zip(__import__("pathlib").Path(os.environ["VR_ROMDIR"]) / "vr.zip")
        for plan in tc.COURSES:
            sat = tc.load_saturn_course(saturn_cue, plan.path)
            gc = COURSE_OF_TEMPLATE[plan.template]
            pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
            with placed(pl.angle, pl.tx, pl.tz):
                lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
                heights = road_profile(sat, lap); hfn = arc_height(lap, heights, sat.segments, camber=plan.camber, ground=sat)   # as the build
                col, _ = saturn_collision(sat, hfn, lap=lap, merge=True, cover=True)   # as the build
                from vrtools.convert.lap import centreline as _cl
                from vrtools.convert.road import attitude_words
                att = attitude_words(lap, sat.segments, _cl(lap), heights)             # Phase 15, as the build
                _TABLES[plan.name] = (road_tables(lap, col.quads[:col.n_tarmac], attitude=att), col.quads[:col.n_tarmac], hfn)
    return _TABLES


def test_segment_road_points_follow_the_lap_on_every_course(saturn_cue):
    """Review (Phase 10): on Amazon Falls two quads whose front lies 386 units from any centreline point fell back to
    the globally nearest point (117) and the monotone clamp dragged the next 91 quads there: the player's first
    checkpoint never fired. A quad's road point must stay within SEGMENT_REACH of its front (or keep the previous
    quad's when the front is nowhere near the line), and consecutive quads never jump more than one merged quad."""
    import math
    from vrtools.convert.road import SEGMENT_BACK, SEGMENT_REACH
    for name, (t, quads, _h) in _all_course_tables(saturn_cue).items():
        pts = [(p.x, p.z) for p in t.lines[0]]; n = len(pts)
        jumps = []
        for k, (q, s) in enumerate(zip(quads, t.segments)):
            fx, fz = (q.corners[0][0] + q.corners[1][0]) / 2, (q.corners[0][2] + q.corners[1][2]) / 2
            near = math.hypot(pts[s.road_point][0] - fx, pts[s.road_point][1] - fz) <= SEGMENT_REACH
            kept = k and s.road_point == t.segments[k - 1].road_point
            assert near or kept or s.road_point in (0, n - 1), (name, k, s, round(fx), round(fz))
            if k:
                jumps.append((s.road_point - t.segments[k - 1].road_point) % n)
        zone = lambda rp: rp >= n - 1 - 3 or rp <= 3                          # the start line: straddlers and side strips
        big = [(k + 1, j) for k, j in enumerate(jumps)                         # Phase 22m: back by up to SEGMENT_BACK (was 3)
               if 15 < j < n - SEGMENT_BACK and not (zone(t.segments[k].road_point) or zone(t.segments[k + 1].road_point))]
        assert not big, (name, big[:5])


def test_only_the_quads_at_the_line_are_credited_the_last_point(saturn_cue):
    """Review (Phase 10): every quad whose front was at or past the line got road point n−1 (Alpine 4 quads, Diablo
    Canyon 11), so a car was credited n−1 for ~50 units and its cursor, already wrapped, ran away one point a frame.
    Only the quads straddling the line (rear before it) take n−1; a quad entirely past it takes its own front."""
    from vrtools.convert.road import END_SNAP
    for name, (t, quads, _h) in _all_course_tables(saturn_cue).items():
        pts = [(p.x, p.z) for p in t.lines[0]]; n = len(pts)
        nearest = lambda x, z: min(range(n), key=lambda i: (pts[i][0] - x) ** 2 + (pts[i][1] - z) ** 2)
        last = [k for k, s in enumerate(t.segments) if s.road_point == n - 1]
        assert last, name
        for k in last:                                                        # every quad credited n-1 straddles the line:
            q = quads[k]                                                      # its rear within a slice length before it
            rear = nearest((q.corners[2][0] + q.corners[3][0]) / 2, (q.corners[2][2] + q.corners[3][2]) / 2)
            assert rear >= n - 1 - 7 or rear <= 1, (name, k, rear, n)            # a straddling end slice is at most ~60 units long


def test_the_tarmac_under_each_road_point_is_credited_near_it(saturn_cue):
    """Phase 11 (the Amazon Falls run-away): a filler quad for point 134 was inserted among the quads of point 188 —
    the lap arcs it was ordered by name the nearest slice centre, which on a stretch that passes near another is the
    other's — and credited 188: every car that touched it jumped 54 points and its cursor ran away (lead 67). At every
    centreline point and every AI offset, every tarmac quad at the road's height carries a road point from three
    behind the point (a side strip's quad at the Diablo Canyon line) to its own length ahead of it (a quad is credited its front's point: Alpine's 118-unit merged
    quad 300 credits 352 at point 341), or eight ahead for a short one (a quad of a side-by-side strip listed after
    the other strip's merged quad keeps that quad's front: Alpine 185–192), the lookahead Phase 10 accepted."""
    import math
    from vrtools.convert.collision import _bboxes, _point_in_xz
    from vrtools.convert.road import AI_OFFSETS
    def plane_h(q, x, z):
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = q.corners[:3]
        ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        return ay if abs(ny) < 1e-9 else ay - (nx * (x - ax) + nz * (z - az)) / ny
    for name, (t, quads, hfn) in _all_course_tables(saturn_cue).items():
        pts = [(p.x, p.z) for p in t.lines[0]]; n = len(pts)
        boxes = _bboxes(quads)
        bad = []
        for p, (x, z) in enumerate(pts):
            (ax, az), (bx, bz) = pts[p - 1], pts[(p + 1) % n]
            d = math.hypot(bx - ax, bz - az) or 1.0
            rx, rz = (bz - az) / d, -(bx - ax) / d
            for lat in (0.0,) + AI_OFFSETS:
                sx, sz = x + lat * rx, z + lat * rz
                for i, (q, b) in enumerate(zip(quads, boxes)):
                    if b[0] <= sx <= b[1] and b[2] <= sz <= b[3] and _point_in_xz(q.corners, sx, sz) \
                            and abs(plane_h(q, sx, sz) - hfn(sx, sz)) < 1.0:
                        ahead = (t.segments[i].road_point - p + n // 2) % n - n // 2
                        fx, fz = (q.corners[0][0] + q.corners[1][0]) / 2, (q.corners[0][2] + q.corners[1][2]) / 2
                        bx_, bz_ = (q.corners[2][0] + q.corners[3][0]) / 2, (q.corners[2][2] + q.corners[3][2]) / 2
                        if not -3 <= ahead <= max(8.0, math.hypot(fx - bx_, fz - bz_) / 10.0 + 2):
                            bad.append((p, lat, i, t.segments[i].road_point))
        assert not bad, (name, len(bad), bad[:6])


def _credits_at(t, quads, hfn, along, lat):
    """The road points the TGP may credit at a spot near the start line (every containing tarmac quad at the road's
    height: ties between overlapping quads go either way by rounding). The spot is `along` units past the line and
    `lat` units to the right of it, in the frame of the road's smoothed direction at point 0 (the centreline's own
    points hook sideways at the lap seam on Diablo Canyon)."""
    from vrtools.convert.collision import _bboxes, _point_in_xz, _plane_height, _smooth_dirs
    pts = [(p.x, p.z) for p in t.lines[0]]
    boxes = _bboxes(quads)
    dx, dz = _smooth_dirs(pts)[0]; rx, rz = dz, -dx
    x, z = pts[0][0] + lat * rx + along * dx, pts[0][1] + lat * rz + along * dz
    return {t.segments[i].road_point for i, (q, b) in enumerate(zip(quads, boxes))
            if b[0] <= x <= b[1] and b[2] <= z <= b[3] and _point_in_xz(q.corners, x, z) and abs(_plane_height(q, x, z) - hfn(x, z)) < 1.0}


def test_the_start_line_band_is_credited_the_last_point_alone(saturn_cue):
    """Review (Phase 11): three of Diablo Canyon's opponents stopped at the start line for good — driving straight
    through the line they stepped from a quad credited 450 into the first quad, credited 0 (its rear 9 units before
    the line), without ever being credited n−1, and their cursors, waiting at n−1 for a road point ≥ n−1 (formats
    §15), never moved again. The TGP breaks ties between overlapping quads by rounding, so only an uncontested
    stretch is a certain credit: across the road's ±10 band, from 11 units before the line to 1 unit before it, every
    spot lies under tarmac and every tarmac quad under it is credited n−1−END_SNAP or later (the band ends at the
    line: the Bay Bridge / Acropolis grids start at road point 1, and a car standing on a last-point quad through
    the countdown has its cursor run away)."""
    from vrtools.convert.road import END_SNAP
    for name, (t, quads, hfn) in _all_course_tables(saturn_cue).items():
        n = len(t.lines[0])
        bad = [(along, lat, sorted(vs)) for along in range(-11, 0, 2) for lat in range(-10, 11)
               for vs in [_credits_at(t, quads, hfn, along, lat)] if not vs or min(vs) < n - 1 - END_SNAP]
        assert not bad, (name, len(bad), bad[:8])


def _ring_quads(lap, length=14.0, half_width=8.0):
    """Tarmac quads `length` units long laid end to end round `_ring_lap_with_slices`'s ring (anticlockwise: left is inward),
    corners front-left, front-right, rear-right, rear-left — their fronts fall anywhere between the road points."""
    r = lap.length / (2 * math.pi)
    at = lambda s, rad: (rad * math.cos(s / r), 0.0, rad * math.sin(s / r))
    quads = []
    s = 0.0
    while s < lap.length - 1e-6:
        e = min(s + length, lap.length)
        c = (at(e, r - half_width), at(e, r + half_width), at(s, r + half_width), at(s, r - half_width))
        quads.append(Quad16(c, tuple(sum(v[i] for v in c) / 4 for i in range(3)), 0))
        s = e
    return quads


def test_a_quad_is_credited_the_last_road_point_its_front_has_reached():
    """Phase 22m: the arcade's quads are centred on their road points, so the point nearest a quad's front is the last
    one the front has passed. Our quads fall anywhere between the points, and the nearest point to a front lying up
    to half a spacing BEFORE a point was that point: the quad before the start band, its front cut 12.5 units before
    the line, was credited the last point (10 units before it) and a car was credited n−1 for 25 units instead of
    the band's 12.5 — twice the original's run-on of the already-wrapped cursor (formats §15; Surfers Road lead 11–14
    against Big Forest's 3–6). A quad's road point is the last point at or behind its front; the next point is ahead."""
    lap, _ = _ring_lap_with_slices(n=60, spacing=10.0)
    quads = _ring_quads(lap, length=14.0)
    t = road_tables(lap, quads, spacing=10.0)
    pts = [(p.x, p.z) for p in t.lines[0]]
    wrong = [(s.index, s.road_point) for q, s in list(zip(quads, t.segments))[1:-1]     # the first and last are pinned
             if not _credited_its_front(pts, q, s.road_point)]
    assert not wrong, (len(wrong), wrong[:6])


def _front_reached(pts, k, x, z):
    """The point (x, z) is at or past road point k along the road's direction there, averaged over five points as the
    walk measures it (`road_tables`: the centreline hooks at the lap seam and zigzags through side-by-side strips)."""
    n = len(pts)
    def d(i):
        (ax, az), (bx, bz) = pts[i - 1], pts[(i + 1) % n]
        m = math.hypot(bx - ax, bz - az)
        return (bx - ax) / m, (bz - az) / m
    sx, sz = (sum(v) for v in zip(*(d((k + j) % n) for j in range(-2, 3))))
    m = math.hypot(sx, sz)
    return (x - pts[k][0]) * sx / m + (z - pts[k][1]) * sz / m >= -1e-6


def _credited_its_front(pts, q, rp, slack=0):
    """Quad `q`'s road point `rp` is the last point its front has reached (or, with `slack`, up to that many points past it)."""
    fx, fz = (q.corners[0][0] + q.corners[1][0]) / 2, (q.corners[0][2] + q.corners[1][2]) / 2
    n = len(pts)
    reached = max((d for d in range(-slack, 1) if _front_reached(pts, (rp + d) % n, fx, fz)), default=None)
    return reached is not None and not _front_reached(pts, (rp + reached + 1) % n, fx, fz)


def test_a_quad_is_credited_by_its_place_not_by_the_quads_listed_before_it():
    """Phase 22m: the walk's progress never went back, so a side strip listed before the road's quads and reaching
    further ahead (the Oval's apron: five 14-unit pieces of the start straight all read 383 after an apron piece at
    383, and point 384 was never credited on the road) took the road's credits with it. A quad is credited the last
    point its own front has reached even when a quad listed before it lies up to SEGMENT_BACK points ahead."""
    from vrtools.convert.road import SEGMENT_BACK
    lap, _ = _ring_lap_with_slices(n=60, spacing=10.0)
    road = _ring_quads(lap, length=14.0)
    r = lap.length / (2 * math.pi)
    at = lambda s, rad: (rad * math.cos(s / r), 0.0, rad * math.sin(s / r))
    quads = []
    for q in road:                                           # before each road quad, an apron piece 4 points further on
        s = r * math.atan2(q.corners[3][2], q.corners[3][0]) % lap.length + 40.0
        c = (at(s + 14.0, r + 25.0), at(s + 14.0, r + 40.0), at(s, r + 40.0), at(s, r + 25.0))
        quads.append(Quad16(c, tuple(sum(v[i] for v in c) / 4 for i in range(3)), 0))
        quads.append(q)
    assert SEGMENT_BACK >= 5
    t = road_tables(lap, quads, spacing=10.0)
    pts = [(p.x, p.z) for p in t.lines[0]]; n = len(pts)
    wrong = [(s.index, s.road_point) for q, s in zip(quads, t.segments)
             if q in road and 3 < s.road_point < n - 4 and not _credited_its_front(pts, q, s.road_point)]
    assert not wrong, (len(wrong), wrong[:6])


def test_the_roads_quads_are_credited_their_own_fronts_on_every_course(saturn_cue):
    """Phase 22m (the Oval's start straight, above): on every course a quad of the road itself — its front within 12
    units of a centreline point — is credited the last point its front has reached, or at most one point past it
    (the walk keeps a credit from going back by more than SEGMENT_BACK); the lap's ends (pins, straddlers) excepted."""
    for name, (t, quads, _h) in _all_course_tables(saturn_cue).items():
        pts = [(p.x, p.z) for p in t.lines[0]]; n = len(pts)
        bad = []
        for q, s in zip(quads, t.segments):
            fx, fz = (q.corners[0][0] + q.corners[1][0]) / 2, (q.corners[0][2] + q.corners[1][2]) / 2
            if min(math.dist(p, (fx, fz)) for p in pts) > 12.0 or not 3 < s.road_point < n - 4:
                continue
            if not _credited_its_front(pts, q, s.road_point, slack=1):
                bad.append((s.index, s.road_point))
        assert not bad, (name, len(bad), bad[:8])


def test_the_last_point_is_credited_to_the_band_alone(saturn_cue):
    """Phase 22m: a car is credited n−1 only across the start band (START_BAND + SEAM_OVERLAP before the line to the
    line): one unit behind the band's rear, across the road's ±10, every tarmac quad under the spot is credited before
    n−1 (and still within END_SNAP of it: the lap's tail). On every course the quad before the band — its front cut at
    the band's rear, 12.5 units before the line, 2.5 before the last point — was credited n−1 by the nearest-point rule,
    and the already-wrapped cursor ran on for 25 units instead of 12.5 (Surfers Road lead 11–14, the original's 3–6)."""
    from vrtools.convert.collision import SEAM_OVERLAP, START_BAND
    from vrtools.convert.road import END_SNAP
    for name, (t, quads, hfn) in _all_course_tables(saturn_cue).items():
        n = len(t.lines[0])
        along = -(START_BAND + SEAM_OVERLAP + 1.0)
        bad = [(lat, sorted(vs)) for lat in range(-10, 11) for vs in [_credits_at(t, quads, hfn, along, lat)]
               if not vs or max(vs) >= n - 1 or min(vs) < n - 1 - END_SNAP]
        assert not bad, (name, len(bad), bad[:8])


def test_the_last_segment_and_the_last_link_are_pinned(saturn_cue):
    """Review (Phase 11): fillers for points 1–2 were inserted after the lap's final straddler, the last segment's road
    point became 2 and the pin did not fire; `link[n−1]` then named a segment at road point 2 and the cursors ran past
    the line while the cars were still at 320–329 (Amazon Falls, lead 16). The last segment is n−1 and the last line
    point's link names a segment at n−1−END_SNAP or later."""
    from vrtools.convert.road import END_SNAP
    for name, (t, quads, hfn) in _all_course_tables(saturn_cue).items():
        n = len(t.lines[0])
        assert t.segments[-1].road_point == n - 1, (name, t.segments[-1])
        named = t.segments[t.lines[0][-1].link >> 16].road_point
        assert named >= n - 1 - END_SNAP, (name, named)


# --- Phase 15: roll and pitch targets in the road-line points' low halves -------------------------------------------

def _s16(v):
    return v - 0x10000 if v >= 0x8000 else v


def _ring_lap_with_slices(n=40, spacing=10.0, climb=(), bank_deg=None):
    """A circular lap of n slice centres `spacing` apart (order = 0..n-1) and one Saturn Segment per slice whose normal
    tilts the road so that its RIGHT side (of the direction of travel) is up by `bank_deg[i]` degrees (level elsewhere),
    under the identity placement (arcade normal = (sx, YSIGN sy, sz): `normal_to_arcade`). `climb` is only documentation
    here: the heights are the caller's."""
    from vrtools.convert.geometry import YSIGN
    from vrtools.saturn.course import Plane, Segment
    radius = n * spacing / (2 * math.pi)
    centres = [(radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n)) for i in range(n)]
    lap = Lap(order=list(range(n)), arc=[i * spacing for i in range(n)], length=n * spacing, start=0, centres=centres,
              route=list(range(n)), route_arc=[i * spacing for i in range(n)])      # one chain round the ring (centreline needs it)
    flat = Plane(0.0, 0.0, 0.0)
    segs = []
    for i in range(n):
        bank = math.radians((bank_deg or {}).get(i, 0.0))
        a = 2 * math.pi * i / n
        dx, dz = -math.sin(a), math.cos(a)                     # travel direction (anticlockwise ring); right = (dz, -dx)
        rx, rz = dz, -dx
        ax, ay, az = -math.sin(bank) * rx, math.cos(bank), -math.sin(bank) * rz      # arcade normal, right side up by `bank`
        segs.append(Segment(i, (flat, flat, flat, flat), (ax, YSIGN * ay, az), (0, 0, 0, 0)))
    return lap, segs


def test_attitude_words_follow_the_slope_and_the_banking():
    """A ring of 40 lap centres climbing 1 unit per 10 units from centre 10 to 20 (5.7 deg) and banked +5 deg on slices 30-34
    and +30 deg on slices 36-38 (clamped at ROLL_CLAMP, 3800 = 20.9 deg; the roll is averaged over three points)."""
    from vrtools.convert.road import ATTITUDE_REACH, PITCH_CLAMP, PITCH_SIGN, ROLL_CLAMP, ROLL_SIGN, attitude_words
    lap, segs = _ring_lap_with_slices(n=40, spacing=10.0, climb=range(10, 20), bank_deg={**{k: 5.0 for k in range(30, 35)}, **{k: 30.0 for k in (36, 37, 38)}})
    pts = lap.centres
    heights = [0.0] * 10 + [float(i) for i in range(1, 11)] + [10.0] * 20
    att = attitude_words(lap, segs, pts, heights)
    assert len(att) == 40
    climb_pitch = att[15][1]
    assert abs(climb_pitch) == pytest.approx(math.degrees(math.atan(0.1)) / 360 * 65536, rel=0.05) and (climb_pitch > 0) == (PITCH_SIGN > 0)
    assert att[5][1] == 0 and att[30][1] == 0                                # flat stretches
    assert att[32][0] == pytest.approx(ROLL_SIGN * 5.0 / 360 * 65536, abs=2) and att[5][0] == 0
    assert att[37][0] == ROLL_SIGN * ROLL_CLAMP                                # 30 deg clamped
    assert all(-ROLL_CLAMP <= r <= ROLL_CLAMP and -PITCH_CLAMP <= p <= PITCH_CLAMP for r, p in att)
    radius = 40 * 10.0 / (2 * math.pi); grow = 1 + (ATTITUDE_REACH + 5) / radius
    far = [(x * grow, z * grow) for x, z in pts]                           # points too far (radially) from any slice: no roll
    assert all(r == 0 for r, _ in attitude_words(lap, segs, far, heights))


def test_road_tables_write_the_attitude_in_the_low_halves():
    lap, quads = _circle_lap_and_quads()
    plain = road_tables(lap, quads, spacing=10.0)
    n = len(plain.lines[0])
    att = [((k % 7) * 100 - 300, (k % 5) * 500 - 1000) for k in range(n)]
    t = road_tables(lap, quads, spacing=10.0, attitude=att)
    for line_plain, line in zip(plain.lines, t.lines):
        for k, (a, b) in enumerate(zip(line_plain, line)):
            assert (b.heading >> 16) == (a.heading >> 16) and (b.link >> 16) == (a.link >> 16)       # angle and segment untouched
            assert _s16(b.heading & 0xFFFF) == att[k][1] and _s16(b.link & 0xFFFF) == att[k][0]   # pitch -> heading.lo (+0x2a), roll -> link.lo (+0x2e)
    assert all((p.heading & 0xFFFF) == 0 and (p.link & 0xFFFF) == 0 for p in plain.lines[0])
    with pytest.raises(ConvertError):
        road_tables(lap, quads, spacing=10.0, attitude=att[:-1])                                     # one per point


def test_attitude_targets_are_bounded_and_smooth_on_every_course(saturn_cue):
    """Phase 15: every converted road point's roll and pitch targets sit inside the clamps, neighbours never differ by more
    than 20 degrees (the opponents approach the target over a few frames; a jump rocks the car), and each course carries
    real values (Alpine: 428 of 526 slices have an angle)."""
    from vrtools.convert.road import PITCH_CLAMP, ROLL_CLAMP
    for name, (t, _quads, _h) in _all_course_tables(saturn_cue).items():
        rolls = [_s16(p.link & 0xFFFF) for p in t.lines[0]]; pitches = [_s16(p.heading & 0xFFFF) for p in t.lines[0]]   # Phase 16 recon §1
        n = len(rolls)
        assert all(-ROLL_CLAMP <= r <= ROLL_CLAMP for r in rolls) and all(-PITCH_CLAMP <= p <= PITCH_CLAMP for p in pitches), name
        jump = max(max(abs(rolls[(k + 1) % n] - rolls[k]), abs(pitches[(k + 1) % n] - pitches[k])) for k in range(n))
        assert jump <= 3641, (name, jump)                                                        # 20 degrees
        assert sum(1 for r, p in zip(rolls, pitches) if r or p) >= n // 10, (name, n)
        # review (Phase 15): a target that swings against its neighbours rocks the car — the lap order's zigzag through
        # side-by-side strips gave Amazon roll flips of ±5.5 deg on consecutive points and Diablo a pitch staircase
        # (13.6 / 0 / 13.5 deg) from the 2-D height projection; the targets come from the point's own direction and the
        # arc profile now: pitch within 3 deg and roll within 2 deg of the neighbours' mean
        worst_p = max(abs(pitches[k] - (pitches[k - 1] + pitches[(k + 1) % n]) / 2) for k in range(n))
        worst_r = max(abs(rolls[k] - (rolls[k - 1] + rolls[(k + 1) % n]) / 2) for k in range(n))
        assert worst_p <= 3 * 182.04 and worst_r <= 2 * 182.04, (name, round(worst_p / 182.04, 1), round(worst_r / 182.04, 1))
        if name == "ALPINE":                                                                      # arcs 200-450 climb at 8-12 deg
            climb = pitches[20:46]                                                                # (-52 to -8 units; level by 520):
            assert all(v > 0 for v in climb) and statistics.mean(climb) > 5 * 182.04, [round(v / 182.04, 1) for v in climb]   # nose-up positive
        if name == "SURFERS OVAL":                                                                # a clockwise oval banked outside-up:
            nz = [v for v in rolls if v]                                                          # left side up -> value positive
            assert sum(1 for v in nz if v > 0) > 0.8 * len(nz), (sum(1 for v in nz if v > 0), len(nz))
        for line in t.lines[1:]:                                                                  # the seven AI lines share them
            assert [_s16(p.link & 0xFFFF) for p in line] == rolls and [_s16(p.heading & 0xFFFF) for p in line] == pitches


def test_attitude_pitch_crosses_the_lap_seam():
    """Review (Phase 15, focus 2): the gradient at point 0 and n-1 uses the ring neighbours; a climb that runs across the
    seam gives both ends a positive pitch of the same size as mid-climb."""
    from vrtools.convert.road import PITCH_SIGN, attitude_words
    lap, segs = _ring_lap_with_slices(n=40, spacing=10.0)
    heights = [float(((i + 5) % 40))  if ((i + 5) % 40) < 10 else 10.0 for i in range(40)]      # rises 1 per 10 units from i=35 to i=4
    att = attitude_words(lap, segs, lap.centres, heights)
    expected = PITCH_SIGN * round(math.atan(0.1) / (2 * math.pi) * 65536)
    assert att[0][1] == pytest.approx(expected, abs=3) and att[39][1] == pytest.approx(expected, abs=3) and att[2][1] == pytest.approx(expected, abs=3)
    assert att[20][1] == 0


def test_road_tables_take_per_point_lanes():
    """Phase 22c (Pascal: the curb at Amazon's first right corner should stop the car): road_tables' AI lines at each
    point's lane scale, right lines by the right side's, left lines by the left's; the other points as before."""
    from vrtools.convert.road import AI_OFFSETS
    lap, quads = _circle_lap_and_quads()
    plain = road_tables(lap, quads, spacing=10.0)
    n = len(plain.lines[0])
    lanes = [(1.0, 0.5 if k == 3 else 1.0) for k in range(n)]
    t = road_tables(lap, quads, spacing=10.0, lanes=lanes)
    c = t.lines[0][3]
    for i, off in enumerate(AI_OFFSETS):
        p = t.lines[1 + i][3]
        assert math.hypot(p.x - c.x, p.z - c.z) == pytest.approx(abs(off) * (0.5 if off > 0 else 1.0), abs=1e-3)
        assert (t.lines[1 + i][5].x, t.lines[1 + i][5].z) == (plain.lines[1 + i][5].x, plain.lines[1 + i][5].z)
