"""Arcade road tables (centreline, AI lines, segment array) from an ordered Saturn lap.

The arcade's segment array has one entry per tarmac collision quad, in lap order: the car's lap position is the
index of the last tarmac quad it touched, and the entry maps it to a centreline road point (docs/formats/
model1-course-tables.md §3; findings in Phase 6). The centreline is the lap's smoothed centreline resampled every
`spacing` units; the four AI lines are lateral offsets of it (the arcade's are hand-made racing lines: a known
deviation).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from vrtools.arcade.course import RoadPoint, Segment
from vrtools.arcade.tgp import Quad16
from vrtools.convert.geometry import ConvertError
from vrtools.convert.lap import Lap, centreline
from vrtools.convert.profile import _arc_profile, centreline_arcs, profile_height

AI_OFFSETS = (-8.0, -3.0, 3.0, 8.0, 5.0, 0.0, -5.0)   # lateral offsets (arcade units, right positive) of the seven AI lines
LINES = 8                                              # centreline + seven AI lines (five addressed by the pointer block, three follow)
FLAG_PLAIN = 1
END_SNAP = 3                   # a first/last segment within this many points of 0 / n-1 is pinned to it
SEGMENT_WINDOW = 15            # a quad's road point is searched up to this many points past the previous quad's
SEGMENT_BACK = 8               # ... and this many behind it (Phase 22m: a side strip listed before the road's quads can lie ahead of them)
SEGMENT_MAX_LEN = 200.0        # a quad longer than this is a degenerate sliver and keeps the previous road point
SEGMENT_REACH = 60.0           # ... unless no point there is within this distance of the quad's front (side-by-side strips sit up to 60 units out)
FLAG_PIT = 66                            # the arcade's pit-lane segments (Big Forest quads 30-59, 1085-1088); never emitted here
MIN_POINT_GAP = 2.0


@dataclass
class RoadTables:
    lines: list[list[RoadPoint]]         # centreline then seven AI lines, equal lengths (the arcade stores eight lines)
    segments: list[Segment]              # one per tarmac quad, index k = quad k


# Phase 15/16 (docs/spike/2026-11-phase16-recon.md §1): the low halves of a road-line point's heading and link words are
# the pitch and the roll an opponent on that point takes (signed, 1/65536 turn): boot 0xfece55 moves the car's +0x2a (the
# PITCH, positive climbing) toward heading.lo and 0xfece67 its +0x2e (the ROLL, negative right side up) toward link.lo.
# Phase 15 wrote them the other way round; measured by tilting every Alpine quad (+0x2e followed a 13 deg tilt) and the
# player's climbs (+0x2a correlates +0.94 with the slope).
PITCH_SIGN = 1                  # the game draws a negative value nose-down (Alpine's first climb, out/p15/signcap): a climb is positive
ROLL_SIGN = -1                  # the game draws a negative value right-side-up (same frames): right side up is negative
PITCH_CLAMP = 3800
ROLL_CLAMP = 3800               # Big Forest's roll reaches 3821 (its banked bends), its pitch 994
ATTITUDE_REACH = 15.0           # a point farther than this from every lap centre takes no banking (another leg's slice)


def attitude_words(lap: Lap, segments, pts: list[tuple[float, float]], heights, spacing: float = 10.0) -> list[tuple[int, int]]:
    """Per centreline point, (roll, pitch) in 1/65536 turn. `pts` is the centreline resampled every `spacing` units of
    arc from the lap start (`lap.centreline`), so point k sits at arc k × spacing: the pitch is the atan of the arc
    profile's rise between arcs (k−1) and (k+1) × spacing — the profile interpolated along `lap.arc` cyclically, not
    projected in 2-D (the lap order zigzags through side-by-side strips and a 2-D projection plateaus and steps). The
    roll is the atan of the road's camber from the slice normal of the lap centre nearest the point (within
    ATTITUDE_REACH, else 0) measured along the POINT's own lateral (right of its direction along the centreline), not
    the lap order's, averaged over the point and its two neighbours. Both signed by PITCH_SIGN / ROLL_SIGN into the
    game's convention and clamped. `heights` is the profile per lap centre (as `profile_height` takes it)."""
    if len(heights) != len(lap.centres):
        raise ConvertError("one height per lap centre is needed")
    from vrtools.convert.geometry import normal_to_arcade
    cs = lap.centres
    n = len(pts)
    arc_h = _arc_profile(lap, heights)
    arcs = centreline_arcs(lap, pts)                         # each point's true arc (Phase 16 review)
    out = []
    for k, (x, z) in enumerate(pts):
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % n]
        dx, dz = bx - ax, bz - az
        d = math.hypot(dx, dz) or 1.0
        rx, rz = dz / d, -dx / d                                 # the point's right-hand lateral
        j = min(range(len(cs)), key=lambda i: (cs[i][0] - x) ** 2 + (cs[i][1] - z) ** 2)
        roll = 0
        if math.hypot(cs[j][0] - x, cs[j][1] - z) <= ATTITUDE_REACH:
            nx, ny, nz = normal_to_arcade(*segments[lap.order[j]].normal)
            if ny > 0.1:
                slope = -(nx * rx + nz * rz) / ny                # height per unit to the right (right side up positive)
                roll = ROLL_SIGN * int(round(math.atan(slope) / (2 * math.pi) * 65536))
        a0, a1 = arcs[k - 1], arcs[(k + 1) % n]
        run = (a1 - a0) % lap.length or 2 * spacing
        rise = arc_h(a0 + run) - arc_h(a0)
        pitch = PITCH_SIGN * int(round(math.atan2(rise, run) / (2 * math.pi) * 65536))
        out.append((roll, max(-PITCH_CLAMP, min(PITCH_CLAMP, pitch))))
    # the roll steps where one slice's banking ends and the next's begins (a 5 deg step between points 10 units apart
    # rocks the car): averaged over the point and its two ring neighbours, then clamped
    smoothed = []
    for k in range(n):
        r = round((out[k - 1][0] + out[k][0] + out[(k + 1) % n][0]) / 3)
        smoothed.append((max(-ROLL_CLAMP, min(ROLL_CLAMP, r)), out[k][1]))
    return smoothed


def heading_word(dx: float, dz: float) -> int:
    """The road-line heading word for one direction of travel: -atan2(dx, dz) in 1/16384 turn (the quad
    attribute's angle at a quarter of the resolution) in the high half, wrapped to 0..16383; low half 0. Lines
    store the unwrapped form (`unwrapped_headings`)."""
    if dx == 0.0 and dz == 0.0:
        return 0
    hi = int(round(-math.atan2(dx, dz) / (2 * math.pi) * 16384)) % 16384
    return hi << 16


def unwrap_headings(raw: list[int]) -> list[int]:
    """Raw headings (0..16383, 1/16384 turn) as signed continuous ones, as the arcade stores them: the first in
    -8192..8192, each next one the previous plus the shortest signed change, so a lap accumulates a full turn
    (Big Forest runs 56 → −16493) and no neighbouring points differ by a turn."""
    out = [((raw[0] + 8192) % 16384) - 8192] if raw else []
    for r in raw[1:]:
        out.append(out[-1] + ((r - out[-1] + 8192) % 16384) - 8192)
    return out


def unwrapped_headings(dirs: list[tuple[float, float]]) -> list[int]:
    """Signed headings (1/16384 turn) continuous along the lap (`unwrap_headings` of each direction's heading word)."""
    return unwrap_headings([heading_word(dx, dz) >> 16 for dx, dz in dirs])


def _directions(pts: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Each centreline point's direction (neighbour to neighbour, unit) and the same averaged over five."""
    n = len(pts)
    dirs = []
    for k in range(n):
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % n]
        m = math.hypot(bx - ax, bz - az)
        dirs.append(((bx - ax) / m, (bz - az) / m) if m > 1e-9 else (0.0, 1.0))
    smooth = []                                           # the road's direction at each point, averaged over five: the
    for k in range(n):                                    # centreline hooks at the lap seam (Alpine's point 450 sits 5 units
        sx = sum(dirs[(k + j) % n][0] for j in range(-2, 3))   # aside), and against one point's own direction a front at the
        sz = sum(dirs[(k + j) % n][1] for j in range(-2, 3))   # road's edge reads as past the point (collision._smooth_dirs)
        m = math.hypot(sx, sz)
        smooth.append((sx / m, sz / m) if m > 1e-9 else dirs[k])
    return dirs, smooth


def segment_credits(pts: list[tuple[float, float]], tarmac_quads: list[Quad16]) -> list[Segment]:
    """The segment array's walk: segment k = tarmac quad k, road point = the last centreline point of `pts` the quad's
    front edge has reached (the wrap and straddler branches, the END_SNAP pins), flag FLAG_PLAIN."""
    n = len(pts)
    _, smooth = _directions(pts)

    def nearest(x: float, z: float, around: int | None = None, reached: bool = False) -> int:
        """The centreline point nearest (x, z); with `around`, among the points from SEGMENT_BACK behind to SEGMENT_WINDOW
        ahead of it (the quads come in lap order: the globally nearest point can lie on another part of the road). With
        `reached`, the nearest of the points at or behind (x, z) along the road — the last point a quad's front has
        reached (Phase 22m: the arcade's quads are centred on their points, ours fall anywhere between them, and a front
        up to half a spacing short of a point was credited it: the quad before the start band took n−1 and a car was
        credited the last point for 25 units, twice the band) — or the nearest of all when none is behind."""
        idx = range(n) if around is None else [(around + d) % n for d in range(-SEGMENT_BACK, SEGMENT_WINDOW)]
        dist = lambda i: (pts[i][0] - x) ** 2 + (pts[i][1] - z) ** 2
        if reached:
            behind = [i for i in idx if (x - pts[i][0]) * smooth[i][0] + (z - pts[i][1]) * smooth[i][1] >= -1e-6]
            if behind:
                return min(behind, key=dist)
        return min(idx, key=dist)

    segments = []
    last = 0
    for k, q in enumerate(tarmac_quads):
        # the quad's road point is the last point its FRONT edge has reached (corners: front-left, front-right, ...): a
        # car anywhere in the quad is credited with at least its own point less one, so an opponent's cursor target
        # (cursor + 2, formats §15) is always ahead of it — credited with the centre, a car in the front part of a
        # 60-unit merged quad had its target behind it and stopped; credited with the point NEAREST the front, the
        # quad before the start band took the last point and the wrapped cursor ran on for twice the band (Phase 22m)
        fx, fz = (q.corners[0][0] + q.corners[1][0]) / 2, (q.corners[0][2] + q.corners[1][2]) / 2
        if k and math.dist(q.corners[0], q.corners[3]) > SEGMENT_MAX_LEN:
            rp = segments[-1].road_point                  # a degenerate sliver (Big Forest's 1300-unit one): the previous quad's
        else:
            rp = nearest(fx, fz, around=last if k else None, reached=True)
            if math.hypot(pts[rp][0] - fx, pts[rp][1] - fz) > SEGMENT_REACH:
                g = nearest(fx, fz, reached=True)         # nothing plausible in the window (a skipped stretch): global ...
                rp = g if math.hypot(pts[g][0] - fx, pts[g][1] - fz) <= SEGMENT_REACH else (segments[-1].road_point if segments else 0)   # ... or the previous quad's
        if k and rp < last and last - rp > n // 2:        # the front is past the start line (wrapped)
            bx, bz = (q.corners[2][0] + q.corners[3][0]) / 2, (q.corners[2][2] + q.corners[3][2]) / 2
            rear = nearest(bx, bz, around=last)
            if rear < n - 8:                              # entirely past the line (a side strip's or a filler quad): its own
                segments.append(Segment(k, rp, FLAG_PLAIN))   # point, and the lap's progress (`last`) stays before the line
                continue
            segments.append(Segment(k, n - 1, FLAG_PLAIN))    # straddling the line: the last point; the lap's progress
            last = max(last, rear)                        # advances only to its rear, so the quads beside it keep their own
            continue
        if k and rp > last and rp - last > n // 2:         # just past the line, a quad whose front reads as just before it
            rp = last                                     # (Phase 17: a sliver the start band clipped from a head quad on
        if last - rp <= n // 2 and rp < last - SEGMENT_BACK:   # Diablo's hooked seam, credited n-1, took the walk's progress
            rp = last                                     # to the lap's end and the side strips after it with it). Phase 22m: a
        last = max(last, rp)                              # quad is credited its own front even when one listed before it lies
        segments.append(Segment(k, rp, FLAG_PLAIN))       # ahead (the Oval's apron before the road's pieces), within SEGMENT_BACK;
                                                          # farther behind the walk's progress it keeps the progress, as before
    # the lap's ends: the first quad is road point 0 and the last is n-1 (within END_SNAP), so a car crossing the
    # start line is credited with the last point before its road point wraps (the opponent cursor rule, formats §15)
    if segments[0].road_point <= END_SNAP:
        segments[0] = Segment(0, 0, FLAG_PLAIN)
    if segments[-1].road_point >= n - 1 - END_SNAP:
        segments[-1] = Segment(len(segments) - 1, n - 1, FLAG_PLAIN)
    return segments


def segment_links(segments: list[Segment], n: int) -> list[int]:
    """Per road point (of `n`) the segment its link names."""
    # segment named by each road point's link. An opponent's line cursor passes a point only once the car's own road
    # point (its lap-position quad's segment) has reached the named segment's road point (formats §15), and the car
    # steers at the cursor + 2 points. Phase 25: each point names the segment with the smallest road point at or AFTER it
    # (the last listed of them; the greatest of all past the last), so the cursor stops one point past the front of the
    # car's own quad. Phase 10-24 named the greatest at or BEFORE it: the points inside the next quad then named the
    # car's own and the cursor ran on to the next quad's front, the target 60-100 units ahead on 40-unit quads (the
    # originals: 30-40), and the opponents turned in early and ran wide off the tarmac (Alpine: 148 jolts in 150 s
    # against 78). Phase 6-9's "segment at or after" stalled the field because a quad was then credited its centre;
    # it is credited its front since Phase 10. (Phase 22m: the credits do not rise with the list: by road point.)
    by_point: dict[int, int] = {}
    for s in segments:
        by_point[s.road_point] = s.index
    rps = sorted(by_point)
    seg_at = [0] * n
    j = 0
    for p in range(n):
        while j < len(rps) - 1 and rps[j] < p:
            j += 1
        seg_at[p] = by_point[rps[j]]
    return seg_at


def road_tables(lap: Lap, tarmac_quads: list[Quad16], spacing: float = 10.0,
                ai_offsets: tuple[float, ...] = AI_OFFSETS, attitude: list[tuple[int, int]] | None = None,
                lanes: list[tuple[float, float]] | None = None) -> RoadTables:
    """Centreline (resampled every `spacing` units from the lap start), seven AI lines at `ai_offsets` (the arcade's
    are hand-made racing lines within about 13 units of the centre), and the segment array: segment k = tarmac
    quad k, road point = the centreline point nearest to the quad's front edge, flag 1 throughout (66 is the arcade's
    pit lane; a converted course has none). Every line point carries its own heading word and, in the high half of
    `link`, the index of the segment whose road point is the first at or after it (the opponent cursor rule, formats §15; Phase 25);
    the first and last segments are pinned to road points 0 and n-1 (END_SNAP). With `attitude` (one (roll, pitch) per
    centreline point, `attitude_words`) the low halves of every line point's heading and link words carry them (Phase 15);
    without it they are 0. With `lanes` (one (left, right) scale per centreline point, `collision.lane_scales`) each
    point's AI offsets are scaled by their side's (Phase 22c: the lines narrow where a curb stands at the road, so its wall
    can stand there); a third entry moves the seven lines sideways by that much (Phase 22n, `collision.lane_shift`: onto
    the Saturn's own tarmac band where the route's strip is the road's edge one). Raises ConvertError when there are no tarmac quads, when a line
    would have fewer than 2 or more than 0xffff points, when points come closer than 2 units, or when `attitude` has not
    one entry per point."""
    if not tarmac_quads:
        raise ConvertError("no tarmac quads to build the segment array from")
    if len(ai_offsets) != LINES - 1:
        raise ConvertError(f"{LINES - 1} AI lines are needed")
    pts = centreline(lap, spacing=spacing)
    n = len(pts)
    if not (2 <= n <= 0xFFFF):
        raise ConvertError(f"{n} centreline points (need 2..65535)")
    for a, b in zip(pts, pts[1:]):
        if math.dist(a, b) < MIN_POINT_GAP:
            raise ConvertError(f"centreline points closer than {MIN_POINT_GAP} units (spacing {spacing})")
    dirs, _ = _directions(pts)
    segments = segment_credits(pts, tarmac_quads)
    seg_at = segment_links(segments, n)
    if attitude is not None and len(attitude) != n:
        raise ConvertError(f"attitude has {len(attitude)} entries for {n} road points")
    att = attitude or [(0, 0)] * n
    words = [((h & 0xFFFF) << 16) | (att[k][1] & 0xFFFF) for k, h in enumerate(unwrapped_headings(dirs))]   # pitch -> +0x2a
    links = [(seg_at[k] << 16) | (att[k][0] & 0xFFFF) for k in range(n)]                                    # roll -> +0x2e
    centre = [RoadPoint(x, z, words[k], links[k]) for k, (x, z) in enumerate(pts)]
    lines = [centre]
    if lanes is not None and len(lanes) != n:
        raise ConvertError(f"lanes has {len(lanes)} entries for {n} road points")
    for off in ai_offsets:
        line = []
        for k, (x, z) in enumerate(pts):
            dx, dz = dirs[k]
            rx, rz = dz, -dx                                  # right-hand lateral
            o = off * (lanes[k][1 if off > 0 else 0] if lanes is not None else 1.0) + (lanes[k][2] if lanes is not None and len(lanes[k]) > 2 else 0.0)   # 22n: the shift
            line.append(RoadPoint(x + o * rx, z + o * rz, words[k], links[k]))
        lines.append(line)
    return RoadTables(lines, segments)
