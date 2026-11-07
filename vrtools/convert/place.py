"""Place a converted course so that its lap start sits at the arcade's grid pose.

The game puts the start grid at absolute positions (Big Forest: the player at (-230, -270) heading +z, road point
13 of the centreline), not on the course's road lines, so a converted course is rotated and shifted in arcade space
until a chosen lap point lies there heading +z, with the whole course inside the ±1024 collision map. Where on the
Saturn lap the start lands is a free choice: the candidate that keeps every tile inside the map and leaves the
most room wins (a known deviation: the start line moves).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from vrtools.arcade.course import course_table, road_lines
from vrtools.arcade.romset import RomSet
from vrtools.convert.geometry import TILE_GROUPS, ConvertError, course_quads, to_arcade
from vrtools.convert.lap import centreline, order_slices
from vrtools.saturn.course import SaturnCourse

GRID_POINT = 13                        # the arcade road point Big Forest's grid is built around (player 37 units to its left)
GRID_OF_COURSE = {0: (GRID_POINT, 37.0), 1: (0, 0.0), 2: (0, 0.0)}
# (road point, lateral offset to the left) of the player's spawn on each original course's road line 0 (menu index
# 0 BF, 1 BB, 2 AC), measured in MAME: Big Forest (-230.4, -269.6) is 37 units left of road point 13 (the grid is
# in the left lane of a wide straight), Bay Bridge (-205.4, 2.5) and Acropolis (-319.7, -190.8) sit on road point
# 0. The heading is +z on all three. A converted course inherits its template's spawn, so its road must pass there.
COURSE_OF_TEMPLATE = {2: 0, 0: 1, 1: 2}                      # data index (template) -> menu index of that course
START_STRAIGHT = 300.0                 # arcade units after the grid that should run straight: the sixteen-car field
                                       # funnelling into a hairpin right after the start piles up (Pacific Coast)
START_TURN_STEP = 15.0                 # degrees: starts are ranked by their first START_STRAIGHT units' turn in these steps
MAP_LIMIT = 970.0                      # keep the road this far inside the ±1024 map: the verge quads reach 40 + 4 units beyond it


@dataclass
class Placement:
    angle: float                       # rotation (geometry.set_placement convention)
    tx: float
    tz: float
    start_slice: int                   # the Saturn slice that becomes the lap start
    direction: tuple[float, float]     # direction of travel there, Saturn frame (for order_slices)
    start_point: int                   # the identity-placement centreline point chosen
    tiles_outside: int
    max_extent: float


def grid_pose(rs: RomSet, template_course: int, point: int | None = None, lateral: float | None = None) -> tuple[float, float, float, float]:
    """(x, z, dx, dz): where the player spawns on the original course `template_course` (menu index; GRID_OF_COURSE:
    a road-line-0 point and a lateral offset to the left of the direction of travel) and the direction of travel
    there. A converted course on that course's template puts its centreline point GRID_OF_COURSE[..][0] here."""
    if point is None:
        point = GRID_OF_COURSE[template_course][0]
    if lateral is None:
        lateral = GRID_OF_COURSE[template_course][1]
    c = road_lines(rs, course_table(rs)[template_course])[0]
    n = len(c)
    p, a, b = c[point], c[point - 1], c[(point + 1) % n]
    dx, dz = b.x - a.x, b.z - a.z
    m = math.hypot(dx, dz)
    dx, dz = dx / m, dz / m
    return p.x - dz * lateral, p.z + dx * lateral, dx, dz          # left of (dx, dz) is (-dz, dx)


def start_turn(cl: list[tuple[float, float]], start: int, units: float = START_STRAIGHT, spacing: float = 10.0) -> float:
    """Degrees the centreline turns (sum of absolute heading changes) over `units` from point `start`."""
    n = len(cl)
    total = 0.0
    for j in range(start, start + int(units // spacing)):
        (ax, az), (bx, bz), (cx, cz) = cl[(j - 1) % n], cl[j % n], cl[(j + 1) % n]
        a1, a2 = math.atan2(bx - ax, bz - az), math.atan2(cx - bx, cz - bz)
        total += abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
    return math.degrees(total)


def _rotate(x: float, z: float, a: float) -> tuple[float, float]:
    c, s = math.cos(a), math.sin(a)
    return (x * c + z * s, -x * s + z * c)


@dataclass(frozen=True)
class PitLane:
    """Phase 22f (Pascal, p22play34: Diablo started in the pit lane, the main road's loop beside it missing; "the pit
    lane should force a pit stop ... similar to the normal track"). As on Big Forest, the lap starts on the main road
    at the pit lane's mouth (`start_slice`), the arcade's PIT START spawn lies `depth` units along the pit straight
    (`path`, in driving order from the mouth) past the pit-entry quad (the tarmac at `entry_slice`), and the course is
    turned `turn` of the way from the normal placement towards the pit straight's heading at the spawn (all the way
    does not fit the map). `slices`: the pit lane, kept whole by the trim at the drawn faces."""
    start_slice: int | None            # None: the lap and its placement stay (the pit lane lies mid-lap, beside the
    slices: tuple[int, ...]            # Saturn's own start straight: Amazon Falls, Pacific Coast)
    path: tuple[int, ...] = ()
    entry_slice: int | None = None
    depth: float | None = None     # the box's distance down the lane; None: mid-lane, at least collision.PIT_BOX_DEPTH_MIN
    turn: float = 0.2              # 0.25 left a scenery polygon at 1025 (map 1024)
    spawn_depth: float | None = None   # Phase 22n: the spawn's distance down the lane when not the box's (`depth`): nearer the
                                   # mouth the course can turn further towards the straight before its far end leaves the map
    pit_stop: bool = True          # the PIT WORK check at the entry quad; Phase 22i parks the car at the course's own box
                                   # (`collision.pit_box`; before that it drove to the host's, inside Diablo's rock)
    entry_separate: bool = False   # v0.1.1 (Pascal, rec118: Surfers Road's pit stop did not trigger): the entry quad goes where the
                                   # lane runs separate from the race lane (`collision.pit_lane_run`), not in the open tarmac the
                                   # mouth shares with it, where a car from the race side cut into the lane past the entry


# Keyed by the TRCK file's SHA-1 prefix; only the courses Pascal named (he stopped in front of each pit entry, 4 Nov).
PIT_LANES = {
    "a0a0bed1d9fca843": PitLane(                                     # Diablo Canyon: the loop slice level with the mouth,
        110, tuple(i for i in range(46, 66) if i not in (47, 61, 64)) + (72, 73, 74, 75, 76, 99, 93, 94, 95, 96, 97, 98),
        (46, 99, 73, 74, 76, 75, 72) + tuple(i for i in range(48, 66) if i not in (61, 64)) + (93, 94, 95, 96, 98, 97), 72, 130.0,   # (47, 61, 64 are the
        turn=0.55, spawn_depth=40.0),                                    # Phase 22n: the spawn 40 in, the course turned 0.55 of the way (the
                                                                         # straight 16 degrees off +z, was 30; at 0.6 a canyon rock 23 units from
                                                                         # the road's far end crosses the map's edge and is left out)
                                                                     # loop's: Pascal's map check), its path, the entry 70 in
    "362930359a24fa05": PitLane(None, (                             # Amazon Falls: 36 units right of race-line points
        302, 303, 304, 305, 306, 307, 309, 315, 317, 319, 321, 323, 325, 327, 329, 331, 332, 334, 336, 338, 340, 342,
        344, 346, 348, 350, 357, 359, 361, 362, 363, 364, 366)),      # 193-228, by the Saturn's START gate (Pascal's stop)
    "605058cec7430b9d": PitLane(None, tuple(range(44, 88))),          # Pacific Coast: 13-30 units right of points 160-210
    "d797f625f129ff8f": PitLane(None, (                             # Surfers Oval: 15-45 units left of the start straight
        105, 106, 107, 108, 109, 110, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 174, 175, 177, 178,
        180, 182, 183, 185, 186, 188, 190, 191, 194, 195, 196, 198, 200, 203, 204, 221, 223, 230, 362, 363, 364)),
    "ce590d8421e3ba76": PitLane(None, (78, 92, 95, 97, 99, 101, 103, 105, 107, 108, 110), depth=82.0),   # Metropolis: 17-22 right of 128-141;
                                                                     # Phase 22t (Pascal): the box in the tunnel (roof to z 340; the default
                                                                     # 130 put it at the lane's end, z 345, outside), 47 past the entry
    "f6f11957be802bd9": PitLane(None, (2, 5, 7, 9, 10, 13, 14, 17, 21, 24, 27, 43, 46, 48)),  # Alpine: 13-29 right of 184-209
    "4f4d8dc9681ad67e": PitLane(None, (                             # Surfers Road: 16-37 left of points 131-176
        139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 152, 153, 155, 156, 158, 160, 161, 163, 164, 166,
        168, 169, 172, 173, 174, 176, 178, 181, 182, 201, 208, 209), entry_separate=True),
}
MAIN_ROAD_START = PIT_LANES                                           # (Phase 22f's name)


def pit_lane_of(sat: SaturnCourse) -> PitLane | None:
    """Phase 22f: the course's pit lane (MAIN_ROAD_START, by its TRCK file), or None (also for a course without one)."""
    return PIT_LANES.get(hashlib.sha1(sat.trck.data).hexdigest()[:16]) if sat.trck is not None else None


def _pit_placement(sat: SaturnCourse, pose, pit: PitLane, base: Placement, cl, limit: float, tiles) -> Placement:
    """`base` turned `pit.turn` of the way towards the pit straight's heading at `pit.spawn_depth` (or `pit.depth`) along
    `pit.path`, and shifted so that point lands on the spawn (identity-frame centreline `cl` and tile centres for the extent)."""
    segs = {s.index: s for s in sat.segments}
    pts = []
    for i in pit.path:
        c = segs[i].corners() if i in segs else None
        if c:
            X, _, Z = to_arcade(sum(p[0] for p in c) / len(c), 0.0, sum(p[1] for p in c) / len(c))
            pts.append((X, Z))
    cum = [0.0]
    for a_, b_ in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a_, b_))
    depth = pit.spawn_depth if pit.spawn_depth is not None else pit.depth
    j = min(range(len(cum)), key=lambda k: abs(cum[k] - depth))
    (ax, az), (bx, bz) = pts[max(0, j - 2)], pts[min(len(pts) - 1, j + 2)]
    px, pz, dx, dz = pose
    full = math.atan2(dx, dz) - math.atan2(bx - ax, bz - az)
    a = base.angle + pit.turn * ((full - base.angle + math.pi) % (2 * math.pi) - math.pi)
    rx, rz = _rotate(pts[j][0], pts[j][1], a)
    tx, tz = px - rx, pz - rz
    ext = max(max(abs(qx + tx), abs(qz + tz)) for qx, qz in (_rotate(x, z, a) for x, z in cl))
    if ext >= limit:
        raise ConvertError(f"the pit-lane placement reaches {ext:.0f} (limit {limit:.0f})")
    outside = sum(1 for x, z in tiles if (lambda q: abs(q[0] + tx) >= 1024 or abs(q[1] + tz) >= 1024)(_rotate(x, z, a)))
    return Placement(a, tx, tz, pit.start_slice, base.direction, base.start_point, outside, ext)


def choose_placement(sat: SaturnCourse, pose: tuple[float, float, float, float], step: int = 3,
                     limit: float = MAP_LIMIT, grid_point: int = GRID_POINT, spacing: float = 10.0,
                     min_coverage: float = 0.98, flag_start: int | None = None) -> Placement:
    """Search the lap (identity placement) for a centreline point whose placement at `pose` keeps the road within
    `limit` and the fewest tiles outside the map; the lap start is put `grid_point` centreline points (of
    `spacing` units) before it, where the arcade's start line is relative to its grid. ConvertError when no
    point fits. `min_coverage` is the lap's (the Surfers oval file carries an unused infield). Phase 22l: with
    `flag_start` the only candidate is the point `flag_start` points after the Saturn's START gate (plus `grid_point`:
    the lap start lands at that point) — ConvertError when it does not fit the map."""
    from vrtools.convert.gates import start_gate_point
    lap = order_slices(sat, min_coverage=min_coverage)
    cl = centreline(lap, spacing=spacing)
    n = len(cl)
    only = None
    if flag_start is not None:
        flag = start_gate_point(sat, cl)
        if flag is None:
            raise ConvertError("flag_start: the course draws no START gate")
        only = (flag + flag_start + grid_point) % n
    tiles = [(sum(p[0] for p in q.p) / len(q.p), sum(p[2] for p in q.p) / len(q.p)) for q in course_quads(sat, groups=TILE_GROUPS)]
    px, pz, dx, dz = pose
    target = math.atan2(dx, dz)
    candidates = []
    for k in (range(0, n, step) if only is None else (only,)):
        (ax, az), (bx, bz) = cl[k - 1], cl[(k + 1) % n]
        a = target - math.atan2(bx - ax, bz - az)              # heading angle atan2(x, z) grows by `a` under _rotate
        rx, rz = _rotate(cl[k][0], cl[k][1], a)
        tx, tz = px - rx, pz - rz
        ext = 0.0
        for x, z in cl:
            qx, qz = _rotate(x, z, a)
            ext = max(ext, abs(qx + tx), abs(qz + tz))
        if ext >= limit:
            continue
        outside = 0
        for x, z in tiles:
            qx, qz = _rotate(x, z, a)
            if abs(qx + tx) >= 1024 or abs(qz + tz) >= 1024:
                outside += 1
        turn = start_turn(cl, k, spacing=spacing)                        # the road after the grid: straight starts first
        candidates.append(((int(turn // START_TURN_STEP), outside, ext), k, a, tx, tz))
    if not candidates:
        raise ConvertError("no lap start places the course inside the map at the grid pose (translate or shrink it)" if only is None
                           else f"flag_start: the lap start {flag_start} points after the START gate puts the road past {limit:.0f}")
    pos = {i: j for j, i in enumerate(lap.order)}
    route = lap.route
    segs = {s.index: s for s in sat.segments if s.centre is not None}
    failed = None
    for (_, outside, ext), k, a, tx, tz in sorted(candidates, key=lambda c: c[0]):
        # the lap start: the Saturn slice nearest the centreline point grid_point points before the chosen one, and
        # the direction of travel there in the Saturn frame
        sx, sz = cl[(k - grid_point) % n]
        r = min(range(len(route)), key=lambda j: (lap.centres[pos[route[j]]][0] - sx) ** 2 + (lap.centres[pos[route[j]]][1] - sz) ** 2)
        prev_c, next_c = segs[route[r - 1]].centre, segs[route[(r + 1) % len(route)]].centre
        ddx, ddz = next_c[0] - prev_c[0], next_c[1] - prev_c[1]
        m = math.hypot(ddx, ddz) or 1.0
        direction = (ddx / m, ddz / m)
        try:
            # the lap must order from this start (a start inside a side lane or next to a cut can leave slices
            # unreached): the next-best candidate is taken when it does not
            lap2 = order_slices(sat, start_slice=route[r], direction=direction, min_coverage=min_coverage)
        except ConvertError as e:
            failed = failed or e
            continue
        # the final lap's centreline (smoothed from this start) sits a few units off the identity one: re-aim so
        # that its point `grid_point` lands on the pose heading +z, where the player spawns
        cl2 = centreline(lap2, spacing=spacing)
        n2 = len(cl2)
        (ax, az), (bx, bz) = cl2[(grid_point - 1) % n2], cl2[(grid_point + 1) % n2]
        a = target - math.atan2(bx - ax, bz - az)
        rx, rz = _rotate(cl2[grid_point % n2][0], cl2[grid_point % n2][1], a)
        tx, tz = px - rx, pz - rz
        ext = max(max(abs(qx + tx), abs(qz + tz)) for qx, qz in (_rotate(x, z, a) for x, z in cl2))
        if ext >= limit:
            failed = failed or ConvertError(f"start {k}: the re-aimed road reaches {ext:.0f}")
            continue
        pit = PIT_LANES.get(hashlib.sha1(sat.trck.data).hexdigest()[:16])
        if pit is not None and pit.start_slice is not None:
            return _pit_placement(sat, pose, pit, Placement(a, tx, tz, pit.start_slice, direction, k, outside, ext), cl, limit, tiles)
        return Placement(a, tx, tz, route[r], direction, k, outside, ext)
    raise ConvertError(f"no lap start both fits the map and orders the lap: {failed}")
