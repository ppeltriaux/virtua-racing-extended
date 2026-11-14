"""Phase 26: a course's road tables read backwards from the same start line (the reverse race, design §3).

The same eight road lines are read the other way round: reversed point j is forward point (n - j) mod n, so point 0
stays on the start line and the lap wraps when the car reaches it, and each line keeps its physical place on the road.
Each collision quad is credited by its other edge (the forward REAR edge, which leads in reverse travel) by running
road.py's own walk on the reversed centreline with each quad turned round: there is no second implementation of it."""
from __future__ import annotations

import math
from dataclasses import dataclass

from vrtools.arcade.course import RoadPoint, Segment
from vrtools.arcade.tgp import Quad16
from vrtools.convert.collision import (PIT_LANE_HALF_WIDTH, SEAM_OVERLAP, _point_in_xz, _tarmac_quad_at, pit_box, pit_entry_quad,
                                       pit_lane_centres, pit_lane_polygons)
from vrtools.convert.geometry import ConvertError
from vrtools.convert.place import pit_lane_of
from vrtools.convert.race import GATE_START_GAP
from vrtools.convert.road import AI_OFFSETS, FLAG_PLAIN, RoadTables, _directions, segment_credits, segment_links, unwrap_headings
from vrtools.saturn.course import SaturnCourse

HALF_TURN_HEADING = 8192          # half a turn in the road line's heading unit (1/16384 turn)
HALF_TURN_ATTR = 0x8000           # ... and in the quad attribute's (1/65536 turn)


def _hi(word: int) -> int:
    return ((word >> 16) ^ 0x8000) - 0x8000


def _s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def reverse_points(pts: list) -> list:
    """Reversed point j is forward point (n - j) mod n: point 0 stays, the rest run backwards."""
    n = len(pts)
    return [pts[(n - j) % n] for j in range(n)]


def reverse_quad(q: Quad16) -> Quad16:
    """The quad turned round: corners (c2, c3, c0, c1) so its front is the forward rear edge, the centre kept, and its
    direction of travel turned half a turn in 16 bits, sign-extended as `collision.direction_attr` stores it."""
    c = q.corners
    v = ((q.attr & 0xFFFF) + HALF_TURN_ATTR) & 0xFFFF
    return Quad16((c[2], c[3], c[0], c[1]), q.centre, v | 0xFFFF0000 if v >= 0x8000 else v)


def _holds(q: Quad16, x: float, z: float) -> bool:
    """(x, z) lies inside quad q in plan, or within SEAM_OVERLAP of its edges (the head quad's seam is that wide)."""
    if _point_in_xz(q.corners, x, z):
        return True
    c = [(p[0], p[2]) for p in q.corners]
    for (ax, az), (bx, bz) in zip(c, c[1:] + c[:1]):
        dx, dz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz))) if dx or dz else 0.0
        if math.hypot(x - ax - t * dx, z - az - t * dz) <= SEAM_OVERLAP:
            return True
    return False


def reverse_segments(pts: list[tuple[float, float]], tarmac_quads: list[Quad16]) -> list[Segment]:
    """The segment array for the reverse race; `pts` is the FORWARD centreline. Quad k is credited the last reversed
    point its forward-rear edge has reached in reverse travel (`road.segment_credits` on the reversed list, the quads
    turned round and in reverse order; the first and last pinned to 0 and n-1 by the same END_SNAP rule).
    Stage 2 (plan D5, recon §2): a quad the walk credits n-1 that holds the start spot (point 0, which the reversed
    centreline shares) is credited 0. The forward head quad reaches SEAM_OVERLAP behind the line under the spawn, so in
    reverse it straddles the line and took n-1: on Amazon Falls (quad 0, along -0.5..+5.9) the player spawned credited
    329 and its first crossing counted no lap. Only quads holding the spot: crediting 0 every n-1 quad beginning within a
    unit of the line (the recon's trial) parked six opponents on Alpine.
    Stage 2 Task 6 (the lead's ruling): the change is withheld where it would leave no quad credited n-1 holding the
    reversed centreline before the line (`_before_line`): an opponent's line cursor wraps only when the car is credited
    n-1 before the line. On Surfers Oval and Surfers Road quad 0 was the road's only n-1 quad (apron quads beside it
    the others); credited 0, no car sat on n-1 at any of the 20 and 16 reverse crossings (8-20 frames in the normal race),
    the opponents' cursors stayed on 386 / 440 after their first wrap and the field stopped at the line (parked 10 and 5
    of 15; on Surfers Road every opponent ended the 150-s race there, the leader one lap, 441 points, on)."""
    m = len(tarmac_quads)
    walk = segment_credits(reverse_points(pts), [reverse_quad(q) for q in reversed(tarmac_quads)])
    n, (x, z) = len(pts), pts[0]
    credits = [walk[m - 1 - k].road_point for k in range(m)]
    moved = [0 if rp == n - 1 and _holds(q, x, z) else rp for q, rp in zip(tarmac_quads, credits)]
    before = _before_line(pts)
    if not any(rp == n - 1 and any(_point_in_xz(q.corners, px, pz) for px, pz in before) for q, rp in zip(tarmac_quads, moved)):
        moved = credits                                         # the road would keep no n-1 quad: the walk's credits stand
    return [Segment(k, rp, FLAG_PLAIN) for k, rp in enumerate(moved)]


def _before_line(pts: list[tuple[float, float]], step: float = 0.5) -> list[tuple[float, float]]:
    """The reversed centreline before the line, from reversed point n-1 (forward point 1), inclusive, to the start spot,
    exclusive, sampled at most `step` units apart."""
    (ax, az), (bx, bz) = pts[1], pts[0]
    k = max(1, math.ceil(math.hypot(bx - ax, bz - az) / step))
    return [(ax + (bx - ax) * i / k, az + (bz - az) * i / k) for i in range(k)]


def reverse_tables(tables: RoadTables, tarmac_quads: list[Quad16]) -> RoadTables:
    """The tables for racing the course the other way: every line reversed from the start line, the heading turned half
    a turn (re-unwrapped so a lap is still continuous), pitch and roll targets negated, links renamed for the reversed
    segments. Raises ConvertError when the reversed unwrapped heading leaves 16 bits."""
    centre = tables.lines[0]
    n = len(centre)
    order = [(n - j) % n for j in range(n)]
    heads = unwrap_headings([(_hi(centre[k].heading) + HALF_TURN_HEADING) % 16384 for k in order])
    if heads and not (-32768 <= min(heads) and max(heads) <= 32767):
        raise ConvertError(f"the reversed heading runs {min(heads)}..{max(heads)}, outside 16 bits")
    segments = reverse_segments([(p.x, p.z) for p in centre], tarmac_quads)
    named = segment_links(segments, n)
    words = [((heads[j] & 0xFFFF) << 16) | (-_s16(centre[k].heading) & 0xFFFF) for j, k in enumerate(order)]
    links = [((named[j] & 0xFFFF) << 16) | (-_s16(centre[k].link) & 0xFFFF) for j, k in enumerate(order)]
    lines = [[RoadPoint(line[k].x, line[k].z, words[j], links[j]) for j, k in enumerate(order)] for line in tables.lines]
    return RoadTables(lines, segments)


def reverse_checkpoints(checkpoints: tuple[int, ...], n: int) -> tuple[int, ...]:
    """The reverse lap's checkpoints: the normal lap's renumbered for the reversed lap, (n − g) mod n sorted, the line 0
    staying 0, less any renumbered point p with 0 < p < `race.GATE_START_GAP` (Phase 22i's rule applied in reverse as it is
    forward: the line fires instead). Nothing fires in reverse that does not fire in the normal direction.
    Phase 26 stage 3 Task 8 (Pascal, 13 Nov, after driving stage 3's set): Diablo Canyon's START arch, forward point 421 of
    457, 36 points after the reverse start, stays scenery and fires nothing in reverse; three checkpoints, the normal lap's
    total spread over them (`race.time_records_for(lap_total=)`). This replaces stage 2's drive choice, under which it fired."""
    return tuple(p for p in sorted((n - g) % n for g in checkpoints) if p == 0 or p >= GATE_START_GAP)


# --- Phase 26 stage 4: the pit stop in reverse (design §6.8, recon docs/spike/2026-11-phase26-stage4-recon.md §2-§3, option A) ---
# In reverse the car meets the normal pit EXIT first. It enters the lane there and the game's own pit sequence takes it backwards
# up the lane to the box: the variant's load record names a pit quad q, and the player's handler starts a stop on a logic frame
# where the car's lap-position quad is q or q + 1 with its heading within 90 degrees of the quad's direction (boot 0xfe8e88; the
# direction is the attribute turned half a turn in a reverse race, so a car driving up the lane backwards passes the test).
# On all seven courses two lane quads already sit at adjacent list indices near the normal exit: no list change is needed.
# The rules are the session lead's ruling of 14 Nov (Task 2, after its first STOP): five hard rules, then a choice in order.

REVERSE_PIT_MIN_RUN = 64.0      # decision L3: the straight run from the pair to the box, at least (the shortest run measured to
                                # park, normal Metropolis's 64; Metropolis reverse from 26 units circled the box, recon §3)
REVERSE_PIT_ROAD_CLEAR = 8.0    # a "clear" pair lies at least this far from all eight road lines (a choice, not a hard rule: the
                                # recon's driven pairs on Alpine and Metropolis lie 3.8 and 5.7 from the ±8 lines, 9.9+ from line 0)
REVERSE_PIT_EXIT_CLEAR = 10.0   # ... and its quads' feet on the lane's polyline at least this far from the lane's exit end
REVERSE_PIT_COVER_STEP = 0.5    # the lane's width at the pair is sampled this often, laterally and along the lane ...
REVERSE_PIT_COVER_REACH = 30.0  # ... this far either side of the lane's polyline (kept where a lane slice lies)
REVERSE_PIT_COVER_TIE = 0.05   # C3: covers within this of the best count as equal and C4 (nearest the exit) decides: a gap of a
                                # few percent of the lane's width is narrower than any line a car can hold and must not outrank a
                                # run twice as long (the lead, 14 Nov: Pacific Coast's 234 beat 241 on 1.000 against 0.976 and lay
                                # 163 units into the lane, a run of 71 at over 300 km/h, against 241's 135)
REVERSE_PIT_BOX_STEP = 0.1      # a box that must move for the run walks the lane's polyline towards the mouth in steps this long


@dataclass(frozen=True)
class ReversePit:
    quad: int                                  # q: the variant's pit quad; q + 1 is its partner
    box: tuple[float, float, float, int]       # x, y, z, heading (1/65536 turn), as collision.pit_box returns


def _foot(line, x: float, z: float) -> tuple[float, float, int]:
    """(arc length from the first point, distance, segment index) of the point of the open polyline `line` nearest (x, z)."""
    best, s0 = (0.0, math.inf, 0), 0.0
    for i, (a, b) in enumerate(zip(line, line[1:])):
        dx, dz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dz)
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (z - a[1]) * dz) / (L * L)))
        d = math.hypot(a[0] + t * dx - x, a[1] + t * dz - z)
        if d < best[1]:
            best = (s0 + t * L, d, i)
        s0 += L
    return best


def _length(line) -> float:
    """The open polyline's length, accumulated as `_foot` does, so that a foot at the end reads exactly the length (sum()
    compensates, and an exit-end foot read one ulp past it)."""
    length = 0.0
    for a, b in zip(line, line[1:]):
        length += math.hypot(b[0] - a[0], b[1] - a[1])
    return length


def _frame_at(line, s: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """The point of the open polyline `line` at arc length s from its first point, and the unit normal of its segment there."""
    last = len(line) - 2
    for i, (a, b) in enumerate(zip(line, line[1:])):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if s <= L or i == last:
            f = min(s, L) / L if L else 0.0
            n = (-(b[1] - a[1]) / L, (b[0] - a[0]) / L) if L else (0.0, 0.0)
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), n
        s -= L
    return line[-1], (0.0, 0.0)


def _seg_dist(x: float, z: float, a, b) -> float:
    dx, dz = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dz * dz
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (z - a[1]) * dz) / l2))
    return math.hypot(a[0] + t * dx - x, a[1] + t * dz - z)


def _crosses(a, b, c, d) -> bool:
    o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) <= 0 and o(c, d, a) * o(c, d, b) <= 0


def _distance_to_loop(q: Quad16, loop) -> float:
    """The least distance in plan from quad q's footprint to the closed polyline `loop`; 0 where the line enters the quad."""
    c = [(p[0], p[2]) for p in q.corners]
    edges = list(zip(c, c[1:] + c[:1]))
    x0, x1, z0, z1 = min(p[0] for p in c), max(p[0] for p in c), min(p[1] for p in c), max(p[1] for p in c)
    best, n = math.inf, len(loop)
    for i in range(n):
        a, b = loop[i], loop[(i + 1) % n]
        gx = max(0.0, min(a[0], b[0]) - x1, x0 - max(a[0], b[0]))
        gz = max(0.0, min(a[1], b[1]) - z1, z0 - max(a[1], b[1]))
        if math.hypot(gx, gz) >= best:
            continue
        if _point_in_xz(q.corners, *a) or any(_crosses(a, b, e, f) for e, f in edges):
            return 0.0
        best = min(best, min(_seg_dist(px, pz, a, b) for px, pz in c), min(_seg_dist(*p, e, f) for p in (a, b) for e, f in edges))
    return best


def road_line_points(centreline, lanes) -> list[list[tuple[float, float]]]:
    """The eight road lines' points as `road.road_tables` places them (the centreline, then the AI lines at `road.AI_OFFSETS`
    across each point's direction, scaled by the side's lane scale and moved by the shift: `Collision.lanes`). A copy of
    road_tables' formula: it computes the lines inline from a Lap, which `reverse_pit` is not given; the tests check the two
    agree on the seven conversions."""
    dirs, _ = _directions(centreline)
    lines = [list(centreline)]
    for off in AI_OFFSETS:
        line = []
        for k, (x, z) in enumerate(centreline):
            dx, dz = dirs[k]
            o = off * (lanes[k][1 if off > 0 else 0] if lanes is not None else 1.0) \
                + (lanes[k][2] if lanes is not None and len(lanes[k]) > 2 else 0.0)
            line.append((x + o * dz, z - o * dx))
        lines.append(line)
    return lines


def pair_cover(col, lane, polys, q: int) -> float:
    """The share of the pit lane's width at pair (q, q + 1) that a car driving along the lane cannot pass without crossing q
    or q + 1: over the pair's extent along the lane's polyline `lane` (its quads' corners' feet), each lateral offset every
    REVERSE_PIT_COVER_STEP over +-REVERSE_PIT_COVER_REACH is a line along the lane (the polyline moved by the offset, sampled
    every REVERSE_PIT_COVER_STEP); an offset is the lane's when a point of its line lies in a lane slice of `polys`, and
    covered when one lies in q or q + 1. The game's check fires on either quad, and two quads one behind the other (Alpine's
    250, 251) catch a car that a cross-section through one of them would show passing beside it."""
    length = _length(lane)
    feet = [_foot(lane, c[0], c[2])[0] for i in (q, q + 1) for c in col.quads[i].corners]
    s0, s1 = max(0.0, min(feet)), min(length, max(feet))
    steps = max(1, math.ceil((s1 - s0) / REVERSE_PIT_COVER_STEP))
    frames = [_frame_at(lane, s0 + (s1 - s0) * j / steps) for j in range(steps + 1)]
    boxes = [(min(p[0] for p in poly), max(p[0] for p in poly), min(p[2] for p in poly), max(p[2] for p in poly)) for poly in polys]
    pair = [col.quads[i] for i in (q, q + 1)]
    m = round(REVERSE_PIT_COVER_REACH / REVERSE_PIT_COVER_STEP)
    width = covered = 0
    for u in range(-m, m + 1):
        off = u * REVERSE_PIT_COVER_STEP
        pts = [(px + nx * off, pz + nz * off) for (px, pz), (nx, nz) in frames]
        if not any(b[0] <= x <= b[1] and b[2] <= z <= b[3] and _point_in_xz(poly, x, z)
                   for x, z in pts for poly, b in zip(polys, boxes)):
            continue
        width += 1
        if any(_point_in_xz(qq.corners, x, z) for x, z in pts for qq in pair):
            covered += 1
    return covered / width if width >= 3 else 0.0


def reverse_pit(sat: SaturnCourse, col, centreline) -> ReversePit | None:
    """Phase 26 stage 4: the reverse variant's pit quad and box, or None when the course has no pit stop in the normal
    direction (no lane, `PitLane.pit_stop` false, or no pit entry quad). Call inside the course's placement.

    A candidate is the pair (q, q + 1) under these hard rules: H1 both are lane quads (tarmac, the centre within
    PIT_LANE_HALF_WIDTH of the lane's polyline and nearer it than the race centreline: `pit_entry_quad`'s pair rule, but
    measured to the polylines' segments where `pit_entry_quad` measures to their points); H2 neither holds the box (the
    parked car would stand on the pit quad with a stop left: recon §3 item 2) nor is the normal pair's quad or its partner;
    H3 no point of any of the eight road lines (between their points too) lies inside either; H4 both centres' feet on the
    lane's polyline lie deeper than the box's (nearer the normal exit); H5 the straight run from the pair's nearer centre to
    the box is at least REVERSE_PIT_MIN_RUN, over tarmac every 4 units (as `collision.pit_box`'s run).
    Then, in order: C1 the box is the normal box with its heading turned half a turn (P1, the lead's reading of Pascal's
    'Ok') if any candidate passes with it; only if none does, it moves up the lane's polyline towards the mouth (in
    REVERSE_PIT_BOX_STEP), at the height of the tarmac quad under it, and the candidates needing the least move are kept
    (Metropolis: the normal box 35 units from the exit, L3). C2 the "clear" candidates (all of both quads at least
    REVERSE_PIT_ROAD_CLEAR from the eight road lines, both quads' centres' feet on the lane's polyline at least
    REVERSE_PIT_EXIT_CLEAR from its exit end) are kept if there are any, else those of the greatest clearance from the eight
    lines. C3 the best `pair_cover`, covers within REVERSE_PIT_COVER_TIE of the best
    counting as equal. C4 of those, the pair nearest the normal exit.
    ConvertError when no pair or no box satisfies the hard rules."""
    pit = pit_lane_of(sat)
    if pit is None or not pit.pit_stop:
        return None
    k = pit_entry_quad(sat, col, centreline)
    box = pit_box(sat, col, centreline) if k is not None else None
    if box is None:                    # an entry quad but no box: pit_box gives none for a lane of fewer than three points
        return None                    # (a lane found by its `entry_slice` alone): no box to turn round, none of the seven
    lane = pit_lane_centres(sat, centreline)
    polys = [[(p[0], 0.0, p[2]) for p in poly] for poly in pit_lane_polygons(sat)]
    lines = road_line_points(centreline, col.lanes)
    quads, n = col.quads, col.n_tarmac
    length = _length(lane)
    heading = (box[3] + HALF_TURN_ATTR) % 0x10000
    nc = len(centreline)

    def lane_quad(i: int) -> bool:                                                       # H1
        x, z = quads[i].centre[0], quads[i].centre[2]
        d = _foot(lane, x, z)[1]
        return d < PIT_LANE_HALF_WIDTH and d < min(_seg_dist(x, z, centreline[j], centreline[(j + 1) % nc]) for j in range(nc))
    near = [i for i in range(n) if _foot(lane, quads[i].centre[0], quads[i].centre[2])[1] < PIT_LANE_HALF_WIDTH]
    in_lane = {i for i in near if lane_quad(i)}
    depth = {i: _foot(lane, quads[i].centre[0], quads[i].centre[2])[0] for i in in_lane}
    pairs = [q for q in sorted(in_lane) if q + 1 in in_lane and not {q, q + 1} & {k, k + 1}]             # H1, H2's normal pair
    clearance = {q: min(_distance_to_loop(quads[i], line) for i in (q, q + 1) for line in lines) for q in pairs}
    pairs = [q for q in pairs if clearance[q] > 0.0]                                                      # H3

    def fits(q: int, x: float, z: float) -> bool:
        """H2 (the box), H4 and H5 for the pair at q with the box at (x, z)."""
        sb = _foot(lane, x, z)[0]
        if not all(sb < depth[i] for i in (q, q + 1)):
            return False
        if any(_point_in_xz(quads[i].corners, x, z) for i in (q, q + 1)):
            return False
        ex, ez = min(((quads[i].centre[0], quads[i].centre[2]) for i in (q, q + 1)), key=lambda c: math.dist(c, (x, z)))
        run = math.dist((ex, ez), (x, z))
        return run >= REVERSE_PIT_MIN_RUN and all(
            _tarmac_quad_at(col, ex + (x - ex) * t / run, ez + (z - ez) * t / run) is not None for t in range(0, int(run) + 1, 4))

    found = [q for q in pairs if fits(q, box[0], box[2])]                                                 # C1
    chosen = (box[0], box[1], box[2], heading)
    if not found:
        s = _foot(lane, box[0], box[2])[0] - REVERSE_PIT_BOX_STEP
        while s >= 0.0 and not found:
            (x, z), _ = _frame_at(lane, s)
            under = _tarmac_quad_at(col, x, z)
            if under is not None:
                found = [q for q in pairs if fits(q, x, z)]
                chosen = (float(x), sum(c[1] for c in quads[under].corners) / 4, float(z), heading)
            s -= REVERSE_PIT_BOX_STEP
    if not found:
        raise ConvertError(f"no reverse pit pair in the lane: {len(pairs)} lane pairs under no road line, none with a box "
                           f"{REVERSE_PIT_MIN_RUN:.0f} units away over tarmac")
    clear = [q for q in found if clearance[q] >= REVERSE_PIT_ROAD_CLEAR
             and all(length - depth[i] >= REVERSE_PIT_EXIT_CLEAR for i in (q, q + 1))]                    # C2
    if clear:
        found = clear
    else:
        most = max(clearance[q] for q in found)
        found = [q for q in found if clearance[q] == most]
    cover = {q: pair_cover(col, lane, polys, q) for q in found}                                           # C3
    best = max(cover.values())
    found = [q for q in found if cover[q] >= best - REVERSE_PIT_COVER_TIE]
    q = min(found, key=lambda q: (length - max(depth[q], depth[q + 1]), q))                               # C4
    return ReversePit(q, chosen)
