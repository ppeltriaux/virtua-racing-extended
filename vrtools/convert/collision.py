"""Saturn road slices -> arcade TGP collision quads and per-cell lists.

One arcade quad per Saturn segment (its plane-bounded XZ polygon, transformed with the Phase 3 similarity), with
the height taken from a HeightFn (a constant, or the Saturn ground mesh via mesh_height). Lists follow the arcade
rule: a quad is listed in every 16-unit collision cell its XZ polygon overlaps (docs/formats/model1-tgp-collision.md).
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Callable

import numpy as np

from dataclasses import dataclass

from vrtools.arcade.tgp import SURFACE_GRASS, SURFACE_TARMAC, SURFACE_WALL, Collision, Quad16, xz_area
from vrtools.convert.geometry import ConvertError, WorldQuad, course_quads, to_arcade
from vrtools.convert.lap import centreline
from vrtools.saturn.course import SaturnCourse

HeightFn = Callable[[float, float], float]
Point = tuple[float, float, float]

CELL = 16                      # collision cells are 16 arcade units; map covers -1024..1023 on both axes
MAP_HALF = 1024
MAP_SIDE = 128
FIRST_OFFSET = 1               # list offset 0 means off-road
CELL_GUARD = 1.0               # units added around each cell square when listing quads (V60 truncation, see cell_lists)
MESH_BUCKET = 32.0


def _point_in_xz(corners, x: float, z: float) -> bool:
    n = len(corners)
    signs = []
    for k in range(n):
        ax, az = corners[k][0], corners[k][2]
        bx, bz = corners[(k + 1) % n][0], corners[(k + 1) % n][2]
        signs.append((bx - ax) * (z - az) - (bz - az) * (x - ax))
    return all(s <= 1e-9 for s in signs) or all(s >= -1e-9 for s in signs)


def _tri_y(a, b, c, x: float, z: float) -> float | None:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    if abs(ny) < 1e-9:
        return None
    return a[1] - (nx * (x - a[0]) + nz * (z - a[2])) / ny


def tgp_height(corners, x: float, z: float) -> float:
    """The TGP's height of a quad at (x, z) (subroutine 0x693, measured on the Diablo replay's twisted quads within
    0.0006): the quad is two triangles on its corner-0/corner-2 diagonal, 0-1-2 on corner 1's side and 2-3-0 on the
    other, so it meets all four corners; a degenerate half (0-1-2 in a line: a Saturn triangle's mid-edge corner) gives
    way to the other, and a vertical quad answers its mean corner height."""
    c = corners
    side = lambda px, pz: (c[2][0] - c[0][0]) * (pz - c[0][2]) - (c[2][2] - c[0][2]) * (px - c[0][0])
    first = side(x, z) * side(c[1][0], c[1][2]) >= 0
    for tri in ((c[0], c[1], c[2]), (c[2], c[3], c[0])) if first else ((c[2], c[3], c[0]), (c[0], c[1], c[2])):
        y = _tri_y(*tri, x, z)
        if y is not None:
            return y
    return sum(p[1] for p in c) / 4


def _plane_y(corners, x: float, z: float) -> float | None:
    """y on the plane through the first three corners, or None if the polygon is vertical."""
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = corners[0], corners[1], corners[2]
    ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
    vx, vy, vz = x2 - x0, y2 - y0, z2 - z0
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    if abs(ny) < 1e-9:
        return None
    return y0 - (nx * (x - x0) + nz * (z - z0)) / ny


def mesh_heights(ground: list[WorldQuad]) -> Callable[[float, float], list[float]]:
    """All heights of ground polygons under (x, z), sorted descending (a bridge deck above water gives two)."""
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, q in enumerate(ground):
        xs = [p[0] for p in q.p]
        zs = [p[2] for p in q.p]
        for bx in range(int(min(xs) // MESH_BUCKET), int(max(xs) // MESH_BUCKET) + 1):
            for bz in range(int(min(zs) // MESH_BUCKET), int(max(zs) // MESH_BUCKET) + 1):
                buckets[(bx, bz)].append(i)

    def heights(x: float, z: float) -> list[float]:
        out = []
        for i in buckets.get((int(x // MESH_BUCKET), int(z // MESH_BUCKET)), ()):
            q = ground[i]
            if _point_in_xz(q.p, x, z):
                y = _plane_y(q.p, x, z)
                if y is not None:
                    out.append(y)
        return sorted(out, reverse=True)

    return heights


def mesh_lookup(ground: list[WorldQuad]) -> Callable[[float, float], list[tuple[float, tuple[int, int, int]]]]:
    """Phase 22p: as `mesh_heights`, with each level's polygon colour: (height, rgb) per polygon under (x, z)."""
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, q in enumerate(ground):
        xs = [p[0] for p in q.p]; zs = [p[2] for p in q.p]
        for bx in range(int(min(xs) // MESH_BUCKET), int(max(xs) // MESH_BUCKET) + 1):
            for bz in range(int(min(zs) // MESH_BUCKET), int(max(zs) // MESH_BUCKET) + 1):
                buckets[(bx, bz)].append(i)

    def lookup(x: float, z: float) -> list[tuple[float, tuple[int, int, int]]]:
        out = []
        for i in buckets.get((int(x // MESH_BUCKET), int(z // MESH_BUCKET)), ()):
            q = ground[i]
            if _point_in_xz(q.p, x, z):
                y = _plane_y(q.p, x, z)
                if y is not None:
                    out.append((y, tuple(q.rgb)))
        return out

    return lookup


def mesh_height(ground: list[WorldQuad]) -> HeightFn:
    """Height of the ground mesh under (x, z): the plane of the first polygon whose XZ projection contains the point.

    `ground` is in arcade world space (e.g. course_quads(sat, groups=(g,))). Raises ConvertError when nothing covers
    the point."""
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, q in enumerate(ground):
        xs = [p[0] for p in q.p]
        zs = [p[2] for p in q.p]
        for bx in range(int(min(xs) // MESH_BUCKET), int(max(xs) // MESH_BUCKET) + 1):
            for bz in range(int(min(zs) // MESH_BUCKET), int(max(zs) // MESH_BUCKET) + 1):
                buckets[(bx, bz)].append(i)

    def height(x: float, z: float) -> float:
        for i in buckets.get((int(x // MESH_BUCKET), int(z // MESH_BUCKET)), ()):
            q = ground[i]
            if _point_in_xz(q.p, x, z):
                y = _plane_y(q.p, x, z)
                if y is not None:
                    return y
        raise ConvertError(f"no ground polygon under ({x:.1f}, {z:.1f})")

    return height


MIN_AREA_QUAD = 1.0            # a verge quad thinner than this is not emitted
MARGIN = 40.0                  # arcade units added on each side of a slice: the arcade verge quads sit there, and the
                               # arcade start grid places the player 30 units left of the single lane past the grid


VERGE_SINK = 0.3               # a verge sits this far from the tarmac edge's height, away from zero (Phase 11: ties went to the verge)
GROUND_DECK = 2.0              # Phase 22o: the drawn ground is the verge's only where it continues the step's inner corner within this
                               # over GROUND_PROBE units (the Oval's kerb lip stands 1.0 at the edge and its bank 1.7 two units out;
                               # Metropolis's junction
                               # road, 4 units up from the first unit, is another deck: the autopilot climbed onto it), and then a level
                               # within the slope cap's reach
GROUND_PROBE = 2.0             # plus GROUND_DECK of the inner corner at the outer corner
TARMAC_REF_MAX = 3.0           # Phase 22o review: a verge's inner reference is the built tarmac's height at the edge when within
                               # this of the profile (another deck's road crossing under the edge point is not the edge)
GROUND_SLOPE_MAX = 0.75        # Phase 22o review: a drawn level the verge may climb towards lies within this a unit (37 degrees; a
                               # face past 45 is a barrier, BARRIER_STEEP) plus GROUND_DECK of the last drawn ground met along the
                               # span, the inner corner first (the Oval's stand roof 31 up over a hole in the ground mesh is not;
                               # its first curve's bank, 0.7 a unit and drawn at every sample, is)
REF_SCAN = 6.0                 # Phase 22o review: a run end between two points finds its tarmac edge within this of its corner
GROUND_AIR = 0.7               # Phase 22o review: the drawn ground between a verge's corners lies at most this far under the quad's
                               # plane (as the cap leaves it) at every GROUND_PROBE (the plane in the air: a flat run-off to a hill
                               # foot crossed the flat ground 2-4 units up, Amazon 475,-385); over the plane is the cap's doing (the
                               # Oval's kerb lip, its first curve's 0.7-a-unit bank); else the outer corner keeps the profile. A hole in the drawn mesh
                               # inside a drawn span is nothing (the Oval 234 R: none for 12 units, then the bank); a span with
                               # nothing drawn at all holds the line within GROUND_AIR over the profile (Amazon -118,-468)
VERGE_MAX_SLOPE = 0.25         # Phase 22k: the run-off (grass and wall) rises at most this much a unit from the road's measured edge,
                               # whatever the drawn ground does: the game takes a wheel-height difference over 1.2 across the car
                               # (2.0 along) for a wall hit — kick, spin, smoke — and the originals' run-off is flat; beside Diablo's
                               # canyon the grass climbed 0.5 a unit and the spin carried the car over the wall strip (rec91, 303)


def _away_from_zero(h: float, d: float) -> float:
    return h + d if h >= 0 else h - d


def _wall_step(ys: list[float], d: float) -> list[float]:
    """Phase 22a: a wall quad's corners `d` off their ground, all the same way: away from zero at the corner farthest
    from it (per corner, a quad over ground crossing zero ran from -d to +d and through the ground between: Diablo's
    first right, Pascal p22play17). Per corner as before if one way leaves a corner under d / 2 off in |height| (the
    TGP's pick compares |height|)."""
    s = 1.0 if max(ys, key=abs) >= 0 else -1.0
    out = [y + s * d for y in ys]
    if all(abs(abs(o) - abs(y)) >= d / 2 for o, y in zip(out, ys)):
        return out
    return [_away_from_zero(y, d) for y in ys]
TARMAC_GROW = 0.0              # arcade units each tarmac quad grows on each side when verges are built. Phases 5-22i: 4.0,
                               # for the seams between side-by-side strips of Saturn slices and the wedges between slices
                               # in bends (the TGP read the car in them as off road); Phase 22j: 0, the coverage fill's
                               # strips and fillers cover those (coverage_gaps), and the growth laid every quad 4 units
                               # over its neighbours across the road with its own surface (a banked road's rows: Alpine's
                               # three rows at 0-0.4, 0.4-1.5, 1.5-3.9 overlapped by 8 units with heights 0.3-0.5 apart,
                               # the game's pick flipped between them and the car's pitch rang: Pascal's camera jitter)
OVERLAP = 0.0                  # arcade units added at both ends of a slice along the road: consecutive Saturn slices (22j trial)
                               # leave ~0.01-unit seams (16.16 planes), and a seam under the car reads as "no road"


def _shift_line(a, b, cx, cz, amount):
    """The line through a, b (XZ) moved by `amount` away from the centroid: returns (point, direction)."""
    dx, dz = b[0] - a[0], b[2] - a[2]
    n = (dx * dx + dz * dz) ** 0.5
    if n < 1e-9:
        return (a[0], a[2]), (dx, dz)
    nx, nz = -dz / n, dx / n                                 # a unit normal
    mx, mz = (a[0] + b[0]) / 2 - cx, (a[2] + b[2]) / 2 - cz
    if nx * mx + nz * mz < 0:                                # point it outward
        nx, nz = -nx, -nz
    return (a[0] + amount * nx, a[2] + amount * nz), (dx, dz)


def _intersect(l1, l2):
    (px, pz), (dx, dz) = l1
    (qx, qz), (ex, ez) = l2
    den = dx * ez - dz * ex
    if abs(den) < 1e-9:
        return None
    t = ((qx - px) * ez - (qz - pz) * ex) / den
    return (px + t * dx, 0.0, pz + t * dz)


def _widen(pts, margin: float, overlap: float = OVERLAP):
    """Move the two short (along-road) edge lines outward by `margin` and the two long (across-road) edge lines
    outward by `overlap`, and take the intersections of consecutive lines as the new corners. Lines, not points,
    are moved, so neighbouring slices keep sharing their across-road lines and no tarmac is lost. pts: 4 (x, 0, z)
    in order; a slice with two collinear edges (a triangle given a fourth corner) is grown by `overlap` only."""
    cx, cz = sum(p[0] for p in pts) / 4, sum(p[2] for p in pts) / 4
    length = lambda k: ((pts[k][0] - pts[(k + 1) % 4][0]) ** 2 + (pts[k][2] - pts[(k + 1) % 4][2]) ** 2) ** 0.5
    short_pair = (1, 3) if length(1) + length(3) < length(0) + length(2) else (0, 2)
    amounts = [margin if k in short_pair else overlap for k in range(4)]
    lines = [_shift_line(pts[k], pts[(k + 1) % 4], cx, cz, amounts[k]) for k in range(4)]
    out = [_intersect(lines[k - 1], lines[k]) for k in range(4)]
    if any(c is None for c in out) or not _convex(out):
        # two collinear edges (a triangle given a fourth corner), or a sliver whose "sides" are really its ends
        # (lane-merge pieces): the margin would fold it into a bow-tie, so grow it by the overlap only
        lines = [_shift_line(pts[k], pts[(k + 1) % 4], cx, cz, overlap) for k in range(4)]
        out = [_intersect(lines[k - 1], lines[k]) if _intersect(lines[k - 1], lines[k]) is not None else pts[k] for k in range(4)]
    return out


def _convex(c) -> bool:
    turns = [(c[(k + 1) % 4][0] - c[k][0]) * (c[(k + 2) % 4][2] - c[(k + 1) % 4][2])
             - (c[(k + 1) % 4][2] - c[k][2]) * (c[(k + 2) % 4][0] - c[(k + 1) % 4][0]) for k in range(4)]
    return all(t <= 1e-9 for t in turns) or all(t >= -1e-9 for t in turns)


def direction_attr(dx: float, dz: float) -> int:
    """The quad attribute for a direction of travel (dx, dz): -atan2(dx, dz) in 1/65536 turn as a sign-extended
    16-bit value (the originals store 0xffffXXXX for negative angles); (0, 0) gives 0."""
    if dx == 0.0 and dz == 0.0:
        return 0
    v = int(round(-math.atan2(dx, dz) / (2 * math.pi) * 65536)) % 65536
    return v | 0xFFFF0000 if v >= 0x8000 else v


class _RouteDirections:
    """Direction of travel at the smoothed-centreline point nearest to an arcade (x, z)."""

    def __init__(self, lap, spacing: float = 10.0) -> None:
        from vrtools.convert.lap import centreline
        self.pts = centreline(lap, spacing=spacing)
        self.spacing = spacing
        n = len(self.pts)
        self.dirs = []
        for k in range(n):
            (ax, az), (bx, bz) = self.pts[k - 1], self.pts[(k + 1) % n]
            self.dirs.append((bx - ax, bz - az))

    def nearest(self, x: float, z: float) -> int:
        return min(range(len(self.pts)), key=lambda i: (self.pts[i][0] - x) ** 2 + (self.pts[i][1] - z) ** 2)

    def at(self, x: float, z: float) -> tuple[float, float]:
        return self.dirs[self.nearest(x, z)]

    def arc(self, x: float, z: float) -> float:
        """Arc length along the centreline (points are evenly spaced) of the nearest point."""
        return self.nearest(x, z) * self.spacing


MERGE_MAX_TURN = 3.0        # degrees of heading change between consecutive slices that may be fused
MERGE_WIDTH_TOL = 0.1       # relative width difference that may be fused
MERGE_MAX_RUN = 6           # slices per fused quad
MERGE_JOIN = 0.15           # fraction of the road width: the next slice's rear corners must sit this close to this
                            # slice's front corners (consecutive Saturn slices overlap by OVERLAP at each end)
MERGE_MAX_SLICE = 40.0      # arcade units: a longer "slice" is a degenerate polygon (Big Forest has a 1300-unit sliver)
MERGE_SPINE_TOL = 0.5       # arcade units a replaced slice's spine may sit outside the fused quad
MERGE_EDGE_TOL = 1.0        # arcade units a replaced slice's corners may sit off the fused quad's side lines
MERGE_HEIGHT_TOL = 0.75     # a fused quad's plane may not leave any member slice's corner heights by more (Phase 16: a fused
                            # straight bridged a 6-unit dip on Metropolis once the collision followed the drawn road)
MERGE_LOOKAHEAD = 4         # lap-order entries searched for the slice that continues this one: side-by-side strips of
                            # slices (start straights, the oval) interleave in lap order
                            # (the arc order interleaves side-by-side strips; fusing across strips leaves gaps)


def _fuse(first: Quad16, last: Quad16, attr_from_dir: bool = True) -> Quad16:
    """One quad from the rear corners of `first` and the front corners of `last` (arcade order FL, FR, BR, BL)."""
    fl, fr = last.corners[0], last.corners[1]
    br, bl = first.corners[2], first.corners[3]
    c = [fl, fr, br, bl]
    centre = _mean(c)
    fx, fz = (fl[0] + fr[0]) / 2 - (bl[0] + br[0]) / 2, (fl[2] + fr[2]) / 2 - (bl[2] + br[2]) / 2
    q = Quad16(tuple(c), centre, direction_attr(fx, fz) if attr_from_dir else first.attr)
    if xz_area(q) > 0:
        c.reverse()
        q = Quad16(tuple(c), centre, q.attr)
    return q


def _xz(p):
    return (p[0], p[2])


def _turn(a: Quad16, b: Quad16) -> float:
    return abs(((b.attr - a.attr + 0x8000) % 0x10000) - 0x8000) * 360.0 / 0x10000


def _length(q: Quad16) -> float:
    c = q.corners
    return math.dist(((c[0][0] + c[1][0]) / 2, (c[0][2] + c[1][2]) / 2), ((c[2][0] + c[3][0]) / 2, (c[2][2] + c[3][2]) / 2))


def _grown_triangle(q: Quad16) -> bool:
    """A Saturn triangle gets its fourth corner on its longest edge (slice_quads): three corners in a line. Such a
    quad has no front/rear pair to fuse along (the Surfers kerbs), so it stays as it is."""
    c = q.corners
    for k in range(4):
        (ax, _, az), (px, _, pz), (bx, _, bz) = c[k - 1], c[k], c[(k + 1) % 4]
        off = abs((bx - ax) * (pz - az) - (bz - az) * (px - ax)) / (math.hypot(bx - ax, bz - az) or 1.0)
        if off < 0.1:
            return True
    return False


def _can_fuse(a: Quad16, b: Quad16) -> bool:
    """b continues a: same heading within MERGE_MAX_TURN, same width within MERGE_WIDTH_TOL, b's rear corners on a's
    front corners (FL, FR, BR, BL order) within MERGE_JOIN of the width, and neither a degenerate sliver nor a
    grown triangle."""
    if _grown_triangle(a) or _grown_triangle(b):
        return False
    turn = _turn(a, b)
    wa = math.dist(a.corners[0], a.corners[1]); wb = math.dist(b.corners[0], b.corners[1])
    tol = MERGE_JOIN * max(wa, wb)
    joined = math.dist(_xz(a.corners[0]), _xz(b.corners[3])) <= tol and math.dist(_xz(a.corners[1]), _xz(b.corners[2])) <= tol
    return turn <= MERGE_MAX_TURN and abs(wa - wb) <= MERGE_WIDTH_TOL * max(wa, wb) and joined \
        and _length(a) <= MERGE_MAX_SLICE and _length(b) <= MERGE_MAX_SLICE


def _inside_within(corners, x: float, z: float, tol: float) -> bool:
    """Point-in-convex-polygon in xz, allowing the point to sit `tol` units outside any edge."""
    n = len(corners)
    d = []
    for k in range(n):
        ax, az = corners[k][0], corners[k][2]
        bx, bz = corners[(k + 1) % n][0], corners[(k + 1) % n][2]
        d.append(((bx - ax) * (z - az) - (bz - az) * (x - ax)) / (math.hypot(bx - ax, bz - az) or 1.0))
    return all(v <= tol for v in d) or all(v >= -tol for v in d)


def _mids(q: Quad16):
    c = q.corners
    return (((c[0][0] + c[1][0]) / 2, (c[0][2] + c[1][2]) / 2), (q.centre[0], q.centre[2]),
            ((c[2][0] + c[3][0]) / 2, (c[2][2] + c[3][2]) / 2))


def _line_distance(p, a, b) -> float:
    """Distance in xz from point p to the line through a and b."""
    ax, az, bx, bz = a[0], a[2], b[0], b[2]
    return abs((bx - ax) * (p[2] - az) - (bz - az) * (p[0] - ax)) / (math.hypot(bx - ax, bz - az) or 1.0)


def _sound(fused: Quad16, members: list[Quad16]) -> bool:
    """The TGP keeps, of all the quads containing the point, the one whose height is nearest the car's: quads at
    one height that overlap are picked by rounding noise. A fused quad must therefore cover exactly what its slices
    covered: convex, ends agreeing in width, and every slice's corners on the fused quad's side lines (within
    MERGE_EDGE_TOL) — a chain that drifts sideways or changes width would leave tarmac under a neighbour's verge
    (and verge over its own tarmac), and the car would be reported on grass at random."""
    c = fused.corners
    front, rear = math.dist(c[0], c[1]), math.dist(c[2], c[3])
    if not _convex(c) or abs(front - rear) > MERGE_WIDTH_TOL * max(front, rear):
        return False
    fl, fr, br, bl = c
    for m in members:
        mfl, mfr, mbr, mbl = m.corners
        if any(_line_distance(p, fl, bl) > MERGE_EDGE_TOL for p in (mfl, mbl)) \
                or any(_line_distance(p, fr, br) > MERGE_EDGE_TOL for p in (mfr, mbr)):
            return False
        if not all(_inside_within(c, x, z, MERGE_SPINE_TOL) for x, z in _mids(m)):
            return False
        ys = [(tgp_height(c, p[0], p[2]), p[1]) for p in m.corners]   # Phase 22a: the TGP's two triangles
        if any(y is None or abs(y - py) > MERGE_HEIGHT_TOL for y, py in ys):
            return False                                  # the fused plane would bridge a dip or a crest the slices follow
    return True


def _verges_fuse(first, last, members) -> bool:
    """Both slices carry verges on the same sides, and each side's fused verge is sound for the chain's verges."""
    for side in range(2):
        if (first[1][side] is None) != (last[1][side] is None):
            return False
        if first[1][side] is not None:
            vs = [m[1][side] for m in members]
            if any(v is None for v in vs) or not _sound(_fuse(first[1][side], last[1][side], attr_from_dir=False), vs):
                return False
    return True


MERGE_KEEP_UNITS = 100.0       # Phase 22l: and every slice within this of the lap's start or end along the lap (three slices
                               # were 30 units at the Oval's new line: a 70-unit merged straight before it read its last point,
                               # the field's road point jumped 376 -> 384 -> 386 and three opponents halted with the cursor at 385)
MERGE_KEEP_ENDS = 3            # slices at each end of the lap that never merge: the opponent cursor and the car's road point
                               # must cross the start line together (docs/formats/model1-course-tables.md §15)


def merge_straights(slices: list[tuple[Quad16, tuple[Quad16 | None, Quad16 | None]]],
                    keep_ends: int = MERGE_KEEP_ENDS) -> tuple[list[Quad16], list[Quad16], int]:
    """`slices` = (tarmac quad, (left verge, right verge)) in lap order. Chains of up to MERGE_MAX_RUN slices, each continuing
    the previous one (`_can_fuse`, found within the next MERGE_LOOKAHEAD entries because side-by-side strips
    interleave), whose heading changes by at most MERGE_MAX_TURN degrees in all, are fused into one tarmac quad
    (rear of the first, front of the last) and their verges alike. Output order = lap order of the chain heads.
    Returns (tarmac, verges, slices removed)."""
    tarmac: list[Quad16] = []
    verges: list[Quad16] = []
    used = [False] * len(slices)
    n = len(slices)
    cum = [0.0]                                                        # Phase 22l: distance along the lap to each slice's centre
    for a, b in zip(slices, slices[1:]):
        cum.append(cum[-1] + math.hypot(b[0].centre[0] - a[0].centre[0], b[0].centre[2] - a[0].centre[2]))
    total = cum[-1] + (math.hypot(slices[-1][0].centre[0] - slices[0][0].centre[0], slices[-1][0].centre[2] - slices[0][0].centre[2]) if n > 1 else 0.0)
    single = lambda i: (i < keep_ends or i >= n - keep_ends            # the lap's end slices stay as they are
                        or cum[i] < MERGE_KEEP_UNITS or total - cum[i] < MERGE_KEEP_UNITS)
    removed = 0
    for i in range(len(slices)):
        if used[i]:
            continue
        chain = [i]
        while len(chain) < MERGE_MAX_RUN and not single(i):
            j = chain[-1]
            k = next((k for k in range(j + 1, min(j + 1 + MERGE_LOOKAHEAD, len(slices)))
                      if not used[k] and not single(k) and _can_fuse(slices[j][0], slices[k][0])
                      and _turn(slices[i][0], slices[k][0]) <= MERGE_MAX_TURN
                      and _sound(_fuse(slices[i][0], slices[k][0]), [slices[m][0] for m in chain] + [slices[k][0]])
                      and _verges_fuse(slices[i], slices[k], [slices[m] for m in chain] + [slices[k]])),
                     None)
            if k is None:
                break
            chain.append(k)
        for m in chain:
            used[m] = True
        first, last = slices[chain[0]], slices[chain[-1]]
        if len(chain) == 1:
            tarmac.append(first[0]); verges.extend(v for v in first[1] if v is not None)
        else:
            tarmac.append(_fuse(first[0], last[0]))
            verges.extend(_fuse(fv, lv, attr_from_dir=False) for fv, lv in zip(first[1], last[1]) if fv is not None)
            removed += len(chain) - 1
    return tarmac, verges, removed


def slice_quads(sat: SaturnCourse, height: HeightFn, y_offset: float = 0.0, margin: float = MARGIN,
                overlap: float = OVERLAP, lap=None, verges: bool | None = None, merge: bool = False,
                side_verges: bool = True) -> list[Quad16] | tuple[list[Quad16], int]:
    """Collision quads for the Saturn segments with a usable polygon; triangles get a fourth corner on their
    longest edge. Without a `lap` (no direction known) each slice becomes one quad widened by `margin` on each
    side (Phase 5 behaviour). With a `lap` (convert.lap.Lap) each quad carries the road direction at the nearest
    smoothed-centreline point and the arcade's corner order, and the road is built as the arcade builds it: a
    tarmac quad at the slice's own width plus one verge quad of `margin` units on each side (`verges`, default
    on with a lap; with `side_verges` off the tarmac is still grown but the side verges are left to `road_verges`,
    which builds them from the road's measured edge after the coverage fill — the build's path, Phase 11): the
    game steers the player from the quad's edge distances (TGP command 0x1500), so the tarmac edges must be the
    real road edges. Tarmac quads come first in the list (lower indices), so a cell
    list tries them before the verges. With `merge` (and a lap) straight runs of slices are fused
    (`merge_straights`) and the result is (quads, slices removed)."""
    out = []
    verge_quads = []
    per_slice: list[tuple[Quad16, list[Quad16]]] = []
    skipped = 0
    dirs = _RouteDirections(lap) if lap is not None else None
    if verges is None:
        verges = dirs is not None
    reach = set(lap.order) if lap is not None else None
    import hashlib
    hinted = lap is not None and sat.trck is not None and hashlib.sha1(sat.trck.data).hexdigest()[:16] in DECK_HINT_COURSES
    arc_of = {i: a for i, a in zip(lap.order, lap.arc)} if hinted else {}
    base_height = height
    for seg in sat.segments:
        a = arc_of.get(seg.index)                               # Phase 22g: the slice's own deck where the lap crosses itself
        height = (lambda x, z, a=a: base_height(x, z, near_arc=a)) if a is not None and getattr(base_height, "takes_arc", False) \
            else base_height
        corners = seg.corners()
        if corners is None:
            skipped += 1
            continue
        unreached = reach is not None and seg.index not in reach    # the lap never gets there (the oval's infield): the
        # slice becomes a grass quad with no road tables and no verges of its own, so a car running wide still
        # finds a surface but no lap position
        pts = [to_arcade(cx, 0.0, cz) for cx, cz in corners]
        if len(pts) == 3:
            # grow the triangle first (three proper lines), then give it a fourth corner on its longest edge
            cx, cz = sum(p[0] for p in pts) / 3, sum(p[2] for p in pts) / 3
            lines = [_shift_line(pts[k], pts[(k + 1) % 3], cx, cz, overlap) for k in range(3)]
            grown = [_intersect(lines[k - 1], lines[k]) for k in range(3)]
            pts = grown if all(g is not None for g in grown) else pts
            k = max(range(3), key=lambda i: (pts[i][0] - pts[(i + 1) % 3][0]) ** 2 + (pts[i][2] - pts[(i + 1) % 3][2]) ** 2)
            a, b = pts[k], pts[(k + 1) % 3]
            pts.insert(k + 1, ((a[0] + b[0]) / 2, 0.0, (a[2] + b[2]) / 2))
        elif len(pts) == 4:
            pts = _widen(pts, 0.0 if verges else margin, overlap)
        else:
            raise ConvertError(f"segment {seg.index}: {len(pts)} corners")
        c = [(x, height(x, z) + y_offset, z) for x, _, z in pts]
        centre = _mean(c)
        if dirs is not None:
            dx, dz = dirs.at(centre[0], centre[2])
            c = order_corners(c, dx, dz)                        # front-left, front-right, back-right, back-left
            if verges and TARMAC_GROW > 0:
                c = [(x, height(x, z) + y_offset, z) for x, _, z in _grow_sides(c, TARMAC_GROW)]
                centre = _mean(c)
            attr = direction_attr(dx, dz)
        else:
            attr = 0
        q = Quad16(tuple(c), centre, attr)
        if xz_area(q) > 0:
            c.reverse()
            q = Quad16(tuple(c), centre, attr)
        if unreached:
            verge_quads.append(q)
            continue
        out.append(q)
        mine: list[Quad16 | None] = [None, None]                # (left verge, right verge)
        if verges and margin > 0 and side_verges:
            fl, fr, br, bl = c                                  # arcade order
            n = math.hypot(dx, dz) or 1.0
            lx, lz = -dz / n * margin, dx / n * margin          # left-hand offset of `margin` units
            for side, (sign, inner_f, inner_b) in enumerate(((1, fl, bl), (-1, fr, br))):
                ox, oz = sign * lx, sign * lz
                # the outer corners take the inner corners' heights: the TGP keeps the containing quad whose height is
                # nearest the car's, so a verge off the tarmac plane would capture a car wherever the two overlap;
                # the whole verge sits VERGE_SINK AWAY FROM ZERO of the tarmac edge's height: the TGP compares the
                # ABSOLUTE height of each containing quad with the car's (formats: | |height| − y |), so a verge
                # offset towards zero would win against the tarmac on a course near height 0 (a sink from +0.2 to
                # −0.1 gave |h| 0.1, nearer a car at 0.12 than the tarmac's 0.2: Diablo Canyon's and the Oval's whole
                # fields parked); away from zero the tarmac stays nearer for a car on it, the verge for a car on it
                yf, yb = _away_from_zero(inner_f[1], VERGE_SINK), _away_from_zero(inner_b[1], VERGE_SINK)
                vc = [(inner_f[0] + ox, yf, inner_f[2] + oz), (inner_f[0], yf, inner_f[2]), (inner_b[0], yb, inner_b[2]),
                      (inner_b[0] + ox, yb, inner_b[2] + oz)]
                vc = order_corners(vc, dx, dz)
                vq = Quad16(tuple(vc), _mean(vc), attr)
                if xz_area(vq) > 0:
                    vc.reverse()
                    vq = Quad16(tuple(vc), _mean(vc), attr)
                if abs(xz_area(vq)) > MIN_AREA_QUAD:
                    verge_quads.append(vq)
                    mine[side] = vq
        per_slice.append((q, tuple(mine)))
    if sat.segments and skipped > len(sat.segments) // 10:
        raise ConvertError(f"{skipped} of {len(sat.segments)} segments have no polygon")
    if dirs is not None:
        # the arcade stores its tarmac quads first, in lap order: the car's lap position is the index of the last
        # tarmac quad it touched, and the segment array maps that index to a road point
        per_slice.sort(key=lambda t: dirs.arc(t[0].centre[0], t[0].centre[2]))
        out = [t[0] for t in per_slice]
        if merge:
            tarmac, fused_verges, removed = merge_straights(per_slice)
            extra = [v for v in verge_quads if v not in {q for _, vs in per_slice for q in vs if q is not None}]
            return tarmac + fused_verges + extra, removed
    if merge:
        return out + verge_quads, 0
    return out + verge_quads


def _grow_sides(c, grow: float):
    """Corners in arcade order (FL, FR, BR, BL) with the left and right side lines moved outward by `grow`; the front
    and rear lines stay (neighbouring slices keep sharing them). Falls back to the input when the quad is degenerate."""
    fl, fr, br, bl = c
    cx, cz = sum(p[0] for p in c) / 4, sum(p[2] for p in c) / 4
    front, right, rear, left = (_shift_line(fl, fr, cx, cz, 0.0), _shift_line(fr, br, cx, cz, grow),
                                _shift_line(br, bl, cx, cz, 0.0), _shift_line(bl, fl, cx, cz, grow))
    out = [_intersect(left, front), _intersect(front, right), _intersect(right, rear), _intersect(rear, left)]
    if any(p is None for p in out) or not _convex(out):
        return list(c)
    return out


def _side_distance(q: Quad16, side: int, x: float, z: float) -> tuple[float, float]:
    """Distance from (x, z) to the quad's left (0: BL->FL) or right (1: FR->BR) side line, and where its foot falls along
    the side (0 at the first corner, 1 at the second)."""
    fl, fr, br, bl = q.corners
    a, b = (bl, fl) if side == 0 else (fr, br)
    dx, dz = b[0] - a[0], b[2] - a[2]
    l2 = dx * dx + dz * dz
    if l2 < 1e-9:
        return math.inf, 0.0
    t = ((x - a[0]) * dx + (z - a[2]) * dz) / l2
    return abs((x - a[0]) * dz - (z - a[2]) * dx) / math.sqrt(l2), t


def _edge_strip(c, side: int, amount: float, overlap: float = OVERLAP):
    """Phase 22j: corners (arcade order) of a strip `amount` wide outside the quad's left (0) or right (1) side. Its inner
    edge is the quad's side line (heights linear along it, as the quad's), so the two meet without a step; its front and
    rear are the quad's moved out by `overlap` (consecutive strips overlap like consecutive slices and leave no wedge on
    the outside of a bend). None when degenerate."""
    fl, fr, br, bl = c
    cx, cz = sum(p[0] for p in c) / 4, sum(p[2] for p in c) / 4
    front, rear = _shift_line(fl, fr, cx, cz, overlap), _shift_line(br, bl, cx, cz, overlap)
    a, b = (fr, br) if side == 1 else (bl, fl)                     # the side, first to second corner
    inner = _shift_line(a, b, cx, cz, 0.0)
    outer = _shift_line(a, b, cx, cz, amount)

    def on_side(p):
        """The point p on the side line with its height, linear between the side's corners (extrapolated past them)."""
        dx, dz = b[0] - a[0], b[2] - a[2]
        l2 = dx * dx + dz * dz or 1e-9
        t = ((p[0] - a[0]) * dx + (p[2] - a[2]) * dz) / l2
        return (p[0], a[1] + t * (b[1] - a[1]), p[2])
    if side == 1:
        fi, bi, fo, bo = _intersect(front, inner), _intersect(inner, rear), _intersect(front, outer), _intersect(outer, rear)
        out = None if None in (fi, bi, fo, bo) else [on_side(fi), (fo[0], fr[1], fo[2]), (bo[0], br[1], bo[2]), on_side(bi)]
    else:
        fi, bi, fo, bo = _intersect(inner, front), _intersect(rear, inner), _intersect(outer, front), _intersect(rear, outer)
        out = None if None in (fi, bi, fo, bo) else [(fo[0], fl[1], fo[2]), on_side(fi), on_side(bi), (bo[0], bl[1], bo[2])]
    if out is None or not _convex(out) or abs(xz_area(Quad16(tuple(out), _mean(out), 0))) < MIN_AREA_QUAD:
        return None
    return out


def _side_normal(q: Quad16, side: int) -> tuple[float, float]:
    """The unit normal of the quad's left (0) or right (1) side, pointing out of the quad."""
    fl, fr, br, bl = q.corners
    a, b = (bl, fl) if side == 0 else (fr, br)
    dx, dz = b[0] - a[0], b[2] - a[2]
    L = math.hypot(dx, dz) or 1e-9
    nx, nz = -dz / L, dx / L
    cx, cz = sum(p[0] for p in q.corners) / 4, sum(p[2] for p in q.corners) / 4
    mx, mz = (a[0] + b[0]) / 2, (a[2] + b[2]) / 2
    return (nx, nz) if (mx - cx) * nx + (mz - cz) * nz > 0 else (-nx, -nz)


def _strip_runs(tarmac: list[Quad16], strips: dict[tuple[int, int], float], corner_y) -> list[tuple[int, int, list]]:
    """Phase 22j: the edge strips, built so that strips of slices which share a side corner share their outer corner too
    (the corner moved out along the mean of the two sides' normals, by the larger reach, at one height): consecutive
    strips meet edge to edge like the slices, no wedge on the outside of a bend and no overlap on the inside. Each
    strip's inner edge is its slice's side, corner for corner. Returns (slice index, side, corners in arcade order)."""
    key = lambda p: (round(p[0], 3), round(p[2], 3))
    at_corner: dict[tuple, list[tuple[int, int, float]]] = {}      # inner corner -> the strips meeting there
    for (i, side), amount in strips.items():
        fl, fr, br, bl = tarmac[i].corners
        for p in ((fr, br) if side == 1 else (fl, bl)):
            at_corner.setdefault(key(p), []).append((i, side, amount))
    outer: dict[tuple, tuple] = {}

    def outer_of(p, i, side):
        k = key(p)
        if k not in outer:
            members = at_corner.get(k, [(i, side, strips[(i, side)])])
            nx = sum(_side_normal(tarmac[m], sd)[0] for m, sd, _ in members)
            nz = sum(_side_normal(tarmac[m], sd)[1] for m, sd, _ in members)
            L = math.hypot(nx, nz)
            if L < 1e-6:
                nx, nz = _side_normal(tarmac[i], side)
            else:
                nx, nz = nx / L, nz / L
            reach = max(a for _, _, a in members)
            x, z = p[0] + nx * reach, p[2] + nz * reach
            outer[k] = (x, corner_y(tarmac[i], x, z), z)
        return outer[k]
    out = []
    for (i, side), amount in strips.items():
        fl, fr, br, bl = tarmac[i].corners
        if side == 1:
            c = [fr, outer_of(fr, i, side), outer_of(br, i, side), br]
        else:
            c = [outer_of(fl, i, side), fl, bl, outer_of(bl, i, side)]
        if not _convex(c) or abs(xz_area(Quad16(tuple(c), _mean(c), 0))) < MIN_AREA_QUAD:
            own = _edge_strip(list(tarmac[i].corners), side, amount, overlap=0.0)   # a sharp bend: the strip on its own
            if own is None:
                continue
            c = [p if (k in (0, 3)) == (side == 1) else (p[0], corner_y(tarmac[i], p[0], p[2]), p[2]) for k, p in enumerate(own)]
        out.append((i, side, c))
    return out


def order_corners(c, dx: float, dz: float):
    """Corners in the arcade's order for a direction of travel (dx, dz): front-left, front-right, back-right,
    back-left (97-99 % of the original quads; the TGP's follow-up commands read the record's geometry)."""
    n = math.hypot(dx, dz)
    if n < 1e-9:
        return list(c)
    fx, fz = dx / n, dz / n
    rx, rz = fz, -fx
    cx = sum(p[0] for p in c) / len(c)
    cz = sum(p[2] for p in c) / len(c)
    def key(p):
        fwd = (p[0] - cx) * fx + (p[2] - cz) * fz
        right = (p[0] - cx) * rx + (p[2] - cz) * rz
        return (math.atan2(right, fwd) + math.pi / 2) % (2 * math.pi)    # FL ~ 45deg, FR ~ 135, BR ~ 225, BL ~ 315
    return sorted(c, key=key)


def _mean(c) -> Point:
    return (sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c), sum(p[2] for p in c) / len(c))


def _overlaps(corners, x0: float, z0: float, x1: float, z1: float) -> bool:
    """Separating-axis test between a convex XZ polygon and the axis-aligned square [x0,x1]×[z0,z1]."""
    poly = [(p[0], p[2]) for p in corners]
    square = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    axes = [(1.0, 0.0), (0.0, 1.0)]
    n = len(poly)
    for k in range(n):
        ex, ez = poly[(k + 1) % n][0] - poly[k][0], poly[(k + 1) % n][1] - poly[k][1]
        if ex or ez:
            axes.append((-ez, ex))
    for ax, az in axes:
        pa = [ax * x + az * z for x, z in poly]
        pb = [ax * x + az * z for x, z in square]
        if max(pa) < min(pb) or max(pb) < min(pa):
            return False
    return True


def _on_tarmac(v: Quad16, tarmac: list[Quad16], other_deck: bool = False) -> bool:
    """The verge's centre lies inside a tarmac quad (bounding-box pre-check, then the convex test), whatever the
    heights: where the road crosses over itself (Metropolis) the tarmac under a verge may be the other deck, and
    keeping such verges was measured to make things worse (16 deck-height jumps and 1795 units of backward arc
    in a 90 s drive against 2 and 52 without them: the TGP compares |height| with the car's height, and these
    courses lie below 0), so crossings stay an open item (docs/deviations.md). With `other_deck` only tarmac more than
    VERGE_HEIGHT_STEP from the verge's height counts (Phase 17: the build's grass over a side strip at the road's own
    height — Diablo's start area, Amazon — is kept, it closes the gap between the road and the strip)."""
    x, z = v.centre[0], v.centre[2]
    for t in tarmac:
        c = t.corners
        if min(p[0] for p in c) <= x <= max(p[0] for p in c) and min(p[2] for p in c) <= z <= max(p[2] for p in c) \
                and _point_in_xz(c, x, z):
            if not other_deck or abs(_plane_height(t, x, z) - v.centre[1]) > VERGE_HEIGHT_STEP:
                return True
    return False


def cell_lists(quads: list[Quad16], last: set[int] | None = None) -> tuple[dict[int, list[int]], dict[int, int]]:
    """Per-cell quad lists (offset -> indices, consecutive from offset 1) and the cell -> offset map.

    The TGP picks, among the quads containing the point, the one nearest the car's height, and the last of exact ties, so the indices in `last` (the
    tarmac quads) are placed after the others (the verges) wherever both overlap."""
    per_cell: dict[int, list[int]] = defaultdict(list)
    for i, q in enumerate(quads):
        xs = [p[0] for p in q.corners]
        zs = [p[2] for p in q.corners]
        if min(xs) < -MAP_HALF or max(xs) >= MAP_HALF or min(zs) < -MAP_HALF or max(zs) >= MAP_HALF:
            raise ConvertError(f"quad {i} leaves the collision map: x {min(xs):.0f}..{max(xs):.0f}, z {min(zs):.0f}..{max(zs):.0f}")
        # The V60 derives the cell from int(x), int(z): truncation toward zero, so on the negative half of each axis
        # its cells are shifted by up to one unit from the floor squares. Each cell's test square is grown by
        # CELL_GUARD on every side, which over-lists a little and never under-lists.
        for zc in range(max(0, int((min(zs) + MAP_HALF - CELL_GUARD) // CELL)), min(MAP_SIDE - 1, int((max(zs) + MAP_HALF + CELL_GUARD) // CELL)) + 1):
            for xc in range(max(0, int((min(xs) + MAP_HALF - CELL_GUARD) // CELL)), min(MAP_SIDE - 1, int((max(xs) + MAP_HALF + CELL_GUARD) // CELL)) + 1):
                x0, z0 = xc * CELL - MAP_HALF, zc * CELL - MAP_HALF
                if _overlaps(q.corners, x0 - CELL_GUARD, z0 - CELL_GUARD, x0 + CELL + CELL_GUARD, z0 + CELL + CELL_GUARD):
                    per_cell[zc * MAP_SIDE + xc].append(i)
    lists: dict[int, list[int]] = {}
    cells: dict[int, int] = {}
    pos = FIRST_OFFSET
    for cell in sorted(per_cell):
        idx = per_cell[cell]
        if last:
            idx = [i for i in idx if i not in last] + [i for i in idx if i in last]
        lists[pos] = idx
        cells[cell] = pos
        pos += 1 + len(idx)
    return lists, cells


COVERAGE_SPACING = 10.0        # the coverage is sampled on the road tables' centreline (road.road_tables' spacing)
COVERAGE_HALF_WIDTH = 10.0     # the road's width the tarmac must cover on each side of the centreline (the AI lines run at ±8)
COVERAGE_STEP = 1.0            # lateral sampling step (units)
COVERAGE_FILL_SPACING = 5.0    # the build's coverage fill samples every 5 units (Phase 17: holes between the 10-unit points)
COVERAGE_REACH = 40.0          # a gap is filled from a tarmac quad whose centre lies within this distance ...
COVERAGE_ARC = 60.0            # ... and whose lap arc is within this of the gap's point: never another part of the road
GROW_MAX = 14.0                # the most a quad is grown sideways for coverage (about half a road width)
FILLER_LENGTH = 10.0           # a filler quad: at most this many units of consecutive points' gaps ...
FILLER_MARGIN = 1.5            # ... and this much beyond the gaps on each side (Phase 22j; was at least 6 each side)
STRIP_SLACK = 0.25             # a gap counts as beside a slice's side within this share of the side's length past its ends


@dataclass(frozen=True)
class Gap:
    point: int                 # centreline point
    lateral: float             # right positive
    x: float
    z: float


def _dirs(pts):
    n = len(pts); out = []
    for k in range(n):
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % n]
        m = math.hypot(bx - ax, bz - az)
        out.append(((bx - ax) / m, (bz - az) / m) if m > 1e-9 else (0.0, 1.0))
    return out


def _smooth_dirs(pts, half: int = 2):
    """Unit directions averaged over 2·half+1 points: the resampled centreline zigzags a few units where the lap's
    seam joins side-by-side strips (Diablo Canyon's grid), and a lateral taken from one point's direction there
    swings back over the road."""
    d = _dirs(pts); n = len(pts); out = []
    for k in range(n):
        sx = sum(d[(k + j) % n][0] for j in range(-half, half + 1))
        sz = sum(d[(k + j) % n][1] for j in range(-half, half + 1))
        m = math.hypot(sx, sz)
        out.append((sx / m, sz / m) if m > 1e-9 else d[k])
    return out


def _bboxes(quads):
    return [(min(c[0] for c in q.corners), max(c[0] for c in q.corners), min(c[2] for c in q.corners), max(c[2] for c in q.corners))
            for q in quads]


def _covered(x: float, z: float, quads, boxes) -> bool:
    for q, (x0, x1, z0, z1) in zip(quads, boxes):
        if x0 <= x <= x1 and z0 <= z <= z1 and _point_in_xz(q.corners, x, z):
            return True
    return False


def _plane_height(q: Quad16, x: float, z: float) -> float:
    """The TGP's height of the quad at (x, z) (`tgp_height`; Phase 22a: it was the plane of the first three corners,
    which for a Saturn triangle's mid-edge corner fell back to the mean corner height: the coverage fill grew such a
    slice flat, Diablo 305-315)."""
    return tgp_height(q.corners, x, z)


def _height_near(x: float, z: float, quads, boxes, h: float) -> float | None:
    """The plane height at (x, z) of the containing quad whose height is nearest h, or None when no quad contains it."""
    best = None
    for q, (x0, x1, z0, z1) in zip(quads, boxes):
        if x0 <= x <= x1 and z0 <= z <= z1 and _point_in_xz(q.corners, x, z):
            ph = _plane_height(q, x, z)
            if best is None or abs(ph - h) < abs(best - h):
                best = ph
    return best


def _heading(q: Quad16) -> tuple[float, float]:
    """Direction of travel (dx, dz) from the quad's attribute (`direction_attr`: the road's direction at the quad, which
    a triangle slice's corner order does not give)."""
    a = -(((q.attr & 0xFFFF) + 0x8000) % 0x10000 - 0x8000) * 2 * math.pi / 65536
    return math.sin(a), math.cos(a)


def _front_points(quads: list[Quad16], pts, dirs) -> list[int]:
    """For each quad, the centreline point nearest its front edge among the points heading its way (within 60° of the
    quad's attribute direction): the nearest point of all is the other leg's where the road passes near itself
    (Amazon Falls), as `arc_of` found."""
    out = []
    for q in quads:
        c = q.corners
        fx, fz = (c[0][0] + c[1][0]) / 2, (c[0][2] + c[1][2]) / 2
        hx, hz = _heading(q)
        best, best_d = 0, math.inf
        for p, (x, z) in enumerate(pts):
            if dirs[p][0] * hx + dirs[p][1] * hz < 0.5:
                continue
            d = (x - fx) ** 2 + (z - fz) ** 2
            if d < best_d:
                best, best_d = p, d
        out.append(best)
    return out


VERGE_SCAN_STEP = 0.5          # lateral resolution of the road-edge scan (arcade units)
VERGE_SCAN_MAX = 40.0          # how far from the centreline the tarmac's edge is looked for
VERGE_GRASS = 30.0             # the grass run-off past the road's edge (Phase 16: then the wall; Phase 14's 80 units of grass only
                               # slowed a car that ran wide, and the game put it back after 40 frames)
WALL_WIDTH = 12.0              # the wall strip (surface 5) beyond the grass: the game stops a car that touches it (recon §4).
                               # Phase 22a: 6 -> 12 (Pascal drove through it at speed: past the grass's overlap the strip
                               # left 1.5-3.5 units of pure wall, under one logic step at speed)
WALL_CLEARANCE = 3.0           # a wall quad within this of a point of the centreline or an AI line is dropped (cars would scrape)
WALL_MAX_RUN = 12              # wall steps fuse longer than the grass (MERGE_MAX_RUN): the quad pool must stay one free block
WALL_EDGE_TOL = 3.0            # ... and across measured edges up to this far apart (the wall lies at the run's widest edge)
WALL_MAX_TURN = 8.0            # ... and through this much heading change (degrees): the wall follows bends more coarsely than the grass
GRASS_OVERLAP = 1.0            # the grass's inner line starts this far inside the run's narrowest edge (Phase 17: no seam where
                               # the road narrows or widens inside a run; the TGP keeps the tarmac, nearest the car's height)
GRASS_FLOOR = 8.5              # ... but never inside this lateral (the AI lines run at up to ±8) unless the tarmac ends there
SHORE_WALL_BACK = 2.5          # a shoreline wall starts this far inside the shore's grass width (Phase 19's place: before the water)
WALL_OVERLAP = 0.5             # the wall's inner line starts this far inside the grass's outer line (no collision-free gap between;
                               # Phase 22a: 2.5 -> 2.0, the grass now meets each point's wall: `_meet_walls`)
MAP_LIMIT = 1020.0             # the collision map covers -1024..1023: a verge's outer corner beyond it is pulled back to this
VERGE_EDGE_GAP = 8.0           # a hole in the tarmac narrower than this (a kerb's seam; Phase 17: a side strip's gap) does not end the road
VERGE_HEIGHT_STEP = 1.5        # tarmac more than this off the last sample's height, one scan step away, is another
                               # deck (a crossing); the road's own height changes far less across half a unit


def _edge_scan(tarmac: list[Quad16], boxes, x: float, z: float, rx: float, rz: float, sign: float, height: HeightFn) -> float:
    """The lateral (along sign * (rx, rz)) at which the tarmac at the road's height ends, from (x, z): `road_edges`' scan."""
    edge = 0.0; lat = 0.0; hole = 0.0
    h = _height_near(x, z, tarmac, boxes, height(x, z))
    if h is None:
        h = height(x, z)
    while lat <= VERGE_SCAN_MAX:
        sx, sz = x + sign * lat * rx, z + sign * lat * rz
        h2 = _height_near(sx, sz, tarmac, boxes, h)
        if h2 is None or abs(h2 - h) > VERGE_HEIGHT_STEP:          # Phase 22c: past the tracked surface, tarmac at the
            hp = height(sx, sz)                                    # height function's height is the road's (Surfers Oval
            h3 = _height_near(sx, sz, tarmac, boxes, hp)          # 56-57: the scan rode a lower slice off the bank's
            if h3 is not None and abs(h3 - hp) <= VERGE_HEIGHT_STEP:   # top; another deck is far from the profile)
                h2, h = h3, h3
        if h2 is not None and abs(h2 - h) <= VERGE_HEIGHT_STEP:
            edge, hole, h = lat + VERGE_SCAN_STEP, 0.0, h2
        else:
            hole += VERGE_SCAN_STEP
            if hole >= VERGE_EDGE_GAP:
                break
        lat += VERGE_SCAN_STEP
    return edge


def road_edges(tarmac: list[Quad16], pts, height: HeightFn) -> list[tuple[float, float]]:
    """Per centreline point, the lateral distance (left, right) at which the tarmac at the road's height ends: the
    scan walks outward in VERGE_SCAN_STEP steps, following the surface's height from the centreline (a quad on a
    steep course is twisted and its plane sits units off the profile, so the height is tracked sample to sample,
    not compared with the profile), and stops at the first hole VERGE_EDGE_GAP wide. Laterals follow the smoothed
    direction (`_smooth_dirs`), as the verge steps do."""
    boxes = _bboxes(tarmac); dirs = _smooth_dirs(pts)
    out = []
    for p, (x, z) in enumerate(pts):
        dx, dz = dirs[p]; rx, rz = dz, -dx
        out.append(tuple(_edge_scan(tarmac, boxes, x, z, rx, rz, sign, height) for sign in (-1.0, 1.0)))
    return out


MIN_RUNOFF = 3.5               # Phase 19: the narrowest grass before the wall where the Saturn's water reaches the road (the
                               # wall overlaps it by WALL_OVERLAP + a scan step: it starts at the road's edge, not on it) ...
SHORE_EDGE_TOL = 0.5           # a shoreline wall run's measured edges stay within this (it follows the road's edge: the wall
                               # starts at the run's widest edge, so a wider tolerance would start it into the water)
WALL_MIN_LATERAL = 12.5        # ... but the wall never starts inside this lateral: the AI lines (+-8) and WALL_CLEARANCE (3, plus
                               # a unit for the inner edge sagging between points on a bend) would
                               # drop it and leave the water open (Pacific Coast's seawalls)


def is_water(rgb) -> bool:
    """The Saturn's water faces are pure blue-cyan (red 0, blue 144-248); Alpine's pale-blue snow has red 128-184."""
    r, g, b = rgb
    return r < 40 and b >= 128 and b > g


def shore_widths(water, pts, edges, max_width: float = VERGE_GRASS, step: float = 0.5) -> list[tuple[float, float]]:
    """Per centreline point (left, right): the grass width from the road's measured edge to the first sample inside a
    water face (`WorldQuad`s), the nearest of the point and its two neighbours (no gap where the water juts in between
    points), clamped to [MIN_RUNOFF, max_width] (Phase 19)."""
    dirs = _smooth_dirs(pts); n = len(pts)
    bins: dict[tuple[int, int], list] = {}
    for q in water:
        xs = [p[0] for p in q.p]; zs = [p[2] for p in q.p]
        for bx in range(int(min(xs) // 16), int(max(xs) // 16) + 1):
            for bz in range(int(min(zs) // 16), int(max(zs) // 16) + 1):
                bins.setdefault((bx, bz), []).append(q.p)
    raw = []
    for k, ((x, z), (dx, dz)) in enumerate(zip(pts, dirs)):
        row = []
        for side, sign in ((0, -1.0), (1, 1.0)):
            e = edges[k][side]; w = max_width
            for i in range(int(max_width / step) + 1):
                lat = e + i * step
                px, pz = x + sign * lat * dz, z - sign * lat * dx
                if any(_point_in_xz(c, px, pz) for c in bins.get((int(px // 16), int(pz // 16)), ())):
                    w = i * step
                    break
            row.append(w)
        raw.append(row)
    floor = lambda k, s: max(MIN_RUNOFF, wall_min(k, s) + WALL_OVERLAP + VERGE_SCAN_STEP - edges[k][s])   # grass reaches the wall
    return [tuple(min(max_width, max(floor(k, s), min(raw[k - 1][s], raw[k][s], raw[(k + 1) % n][s]))) for s in (0, 1)) for k in range(n)]


WALL_STEP = 0.0                # Phase 22c: 0, as the originals (Big Forest's walls at the ground's height, measured on Pascal's
                               # drives; the 4-unit step let a slow car mount the Oval's banked wall and the put-back looped).
                               # Phase 22a: the wall strip lay this far from the ground's height, away from zero (as VERGE_SINK:
                               # the grass keeps the car where they overlap). The game's wall is a STEP in the collision height
                               # (0xfebe46: front and rear wheel heights more than 2.0 apart, or left and right more than 1.2 ->
                               # 0xfec003, the deflection, spin and, over speed 0x118, the crash); a surface-5 quad at the ground's
                               # height only slows a car (1.36 -> 1.27 units a frame across the strip, Pascal's Diablo replay)
BARRIER_GROUPS = (0, 1, 3)     # Phase 22a: the Saturn groups whose steep faces stop a car (ground, terrain, structures)
STEEP_GROUPS = (0, 2)          # Phase 22a: the groups whose steep faces only stop a car (the ground; the "paint" layer, flat on
                               # the road, also holds cliff faces: Diablo 168-170, a brown face at 35 the car drove up to)
SOLID_GROUPS = (1, 3)          # ... and whose every face does, steep or not, once it rises above the car's body: the terrain
                               # and structures beyond the road are scenery the collision does not follow (Pascal: "the rocks
                               # should stop the car"; Diablo 97-122: a rock on a grey ramp 2.6 over the road, under the line)
BARRIER_STEEP = 0.7            # a face whose normal's |y| is under this (steeper than ~45°: a cliff, a canyon side, a fence)
BARRIER_BODY = 1.0             # the car's body: a line this far above the collision, crossing outward
RAIL_BODY = 0.5                # ... and a lower line against vertical faces only (rails; a kerb is a sloped strip)
RAIL_VERTICAL = 0.1            # |normal y| under this: vertical
BARRIER_BODIES = (BARRIER_BODY,)       # (a low line at 0.3 took kerbs for walls: Pascal saw the run-off inside the road)
BARRIER_START = 4.0            # ... from this lateral (the car's own road)
BARRIER_MIN_RUNOFF = 1.0       # a barrier wall's narrowest grass (the shore's MIN_RUNOFF 3.5 put it past a face the road was
                               # trimmed to: Diablo 375, the face at 22.7, the wall at 23.5)
BARRIER_SETBACK = 1.5          # the wall starts this far inside the drawn face (p22play17 tried 0: Pascal "ok this way also", but it let the car reach the sea at 13 Surfers Road sides and opened 8 holes on Alpine)
                               # and its body reaches 1.5 past its centre (Pascal: the car went 4.4 units into Diablo's rock
                               # at point 120, "under the road")
CURB_TOP = 3.0                 # a face lower than this above the collision is a curb (no setback: Phase 22c)
JOIN_SLANT_MAX = 2.0           # Phase 22k: where a barrier wall's own lateral jumps by more than this between two points (the rock's
                               # corner), the run on the far side keeps that one segment to itself, so _join_wall_runs slants ten
                               # units of wall, not up to twelve points of it (Diablo 310-312 R: the wall at 16-21, the face 39.5)
BARRIER_CHORD_TOL = 2.0        # Phase 22k: a barrier wall run's inner line runs straight from one end's own lateral to the
                               # other's; the run breaks where a point between would be further than this from that line
                               # (the face bends: Pascal chose 2.0, 11 185 words left; 1.0 cost 2 600 more for half a unit),
                               # or where the line would pass under the point's wall_min (the AI lanes widening back between
                               # two narrowed ends: Amazon 39 L, a wall 2.8 from the -8 line)
BARRIER_LAT_TOL = 3.5          # a barrier wall run breaks where a point's edge + width differs from its first's by more
BARRIER_QUANT = 1.0            # a barrier width is rounded UP to this grid (Phase 22k; 2.5 rounded down, and with the wall's inner
                               # line WALL_OVERLAP + VERGE_SCAN_STEP inside the grass a wheel met the wall 2.5-5 units before the
                               # drawn rock — Pascal, rec98 Diablo 134-146 R: "stopped by something invisible")
BARRIER_EDGE_TOL = 2.0         # a barrier wall's run: measured edges within this (the shore's 0.5 follows the edge finer)
FACE_GAP = 6                   # Phase 22k: points where the scan found no face between two found ones on the same side, up to this
                               # many, take the line between them (the rock's outline; Diablo 313-315 between 39.5 and 17.5 out)
BARRIER_MAX_TURN = 8.0         # ... through this much heading change (degrees)
CURB_MARGIN = 1.0              # Phase 22k (3b): a drawn curb narrows the AI lines anywhere only where it stands this far beyond the
                               # road's filled, untrimmed edge (a real kerb at the edge); a low face measured over the road (Diablo
                               # 89-92 R: 8.5 out) does not — a course-wide rule once pulled Diablo's walls in to its white lines
PROP_MIN_LATERAL = 6.5         # Phase 22k (3a): a prop's face (group 4: gate posts, signs, buildings, rock objects) counts as a
                               # drawn face from this lateral out (LANE_MIN_WALL: the road is trimmed to it and the AI lines narrow,
                               # as at Amazon's curb); nearer, over the road, it is ignored (Metropolis 126-128 R: a building's
                               # faces 4-6 out). Props take no median (a post is one point) and no gap fill (no line between posts).
BARRIER_SPREAD = 2             # a point's width is the median over this many points either side (a lone tree or pillar
                               # is not a wall: wall_insets would pull the wall in over 12 points around it)


def is_barrier(q: WorldQuad) -> bool:
    """A drawn face steep enough to stop a car (Phase 22a)."""
    a = np.array(q.p, float)
    nrm = np.cross(a[2] - a[0], a[3] - a[1]); ln = float(np.linalg.norm(nrm))
    return ln > 1e-6 and abs(nrm[1]) / ln < BARRIER_STEEP


SHOULDER_GREY = 24              # a face whose colour channels lie within this of each other is grey


def is_shoulder(q: WorldQuad) -> bool:
    """Phase 22c (Pascal p22play21, Diablo's first right turn: "the wall impact when i actually pass over the white line
    which is before the wall"): a gentle (|ny| >= BARRIER_STEEP) grey face of the solid groups is a shoulder past the
    white line (Diablo 94-100 left: 184,184,176 at 20-30 degrees, the brown rock from 22), not a barrier; brown rock stays
    one at any slope (Pascal: the mountain blocks' gentle facets), a steep grey face (a concrete wall) too."""
    return max(q.rgb) - min(q.rgb) <= SHOULDER_GREY and not is_barrier(q)


def _first_crossing(o: np.ndarray, d: np.ndarray, tris: np.ndarray) -> int | None:
    """The first of the segments o[i] -> o[i] + d[i] (N x 3) that crosses one of the triangles (M x 3 x 3), or None."""
    if not len(tris):
        return None
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    e1, e2 = b - a, c - a
    p = np.cross(d[:, None, :], e2[None, :, :])                     # N x M x 3
    det = np.einsum("mk,nmk->nm", e1, p)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    t0 = o[:, None, :] - a[None, :, :]
    u = np.einsum("nmk,nmk->nm", t0, p) * inv
    q = np.cross(t0, e1[None, :, :])
    v = np.einsum("nk,nmk->nm", d, q) * inv
    t = np.einsum("mk,nmk->nm", e2, q) * inv
    hit = (ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t >= 0) & (t <= 1)).any(axis=1)
    idx = np.flatnonzero(hit)
    return int(idx[0]) if len(idx) else None


BARRIER_REACH = 60.0           # drawn faces are looked for this far from the centreline


def _vertical(q: WorldQuad) -> bool:
    a = np.array(q.p, float)
    nrm = np.cross(a[2] - a[0], a[3] - a[1]); ln = float(np.linalg.norm(nrm))
    return ln > 1e-6 and abs(nrm[1]) / ln < RAIL_VERTICAL


def fill_faces(faces: list[tuple[float, float]], max_gap: int = FACE_GAP) -> list[tuple[float, float]]:
    """Phase 22k: `barrier_faces` with the gaps of up to `max_gap` points between two found faces on a side filled by the
    straight line between them (around the lap). The wall's inset was the narrowest grass within 12 points, so across a
    gap the wall stood at the nearer rock's lateral (Diablo 310-312 R: 16-21 out, the face 39.5)."""
    n = len(faces); out = [list(f) for f in faces]
    for sd in (0, 1):
        found = [k for k in range(n) if math.isfinite(faces[k][sd])]
        if len(found) < 2:
            continue
        for a, b in zip(found, found[1:] + found[:1]):
            gap = (b - a - 1) % n
            if gap == 0 or gap > max_gap:
                continue
            for j in range(1, gap + 1):
                out[(a + j) % n][sd] = faces[a][sd] + (faces[b][sd] - faces[a][sd]) * j / (gap + 1)
    return [tuple(f) for f in out]


def narrowing_faces(faces, curbs, props, edges, margin: float = CURB_MARGIN, floor: float = PROP_MIN_LATERAL) -> list[tuple[float, float]]:
    """Phase 22k (3b): per point and side, the face that narrows the AI lines at every point (`lane_scales`' `always`):
    a drawn curb (`barrier_faces`' `curbs`) standing `margin` beyond the road's filled, untrimmed `edges`, or a prop's
    face from `floor` out; math.inf elsewhere."""
    n = len(faces)
    return [tuple(min(faces[k][s] if curbs[k][s] and faces[k][s] >= edges[k][s] + margin else math.inf,
                      props[k][s] if props is not None and props[k][s] >= floor else math.inf) for s in (0, 1)) for k in range(n)]


def merge_prop_faces(faces: list[tuple[float, float]], props: list[tuple[float, float]],
                     floor: float = PROP_MIN_LATERAL) -> list[tuple[float, float]]:
    """Phase 22k (3a): the drawn faces with the props' faces (`barrier_faces` over group 4, no median): the nearer of the
    two where the prop stands `floor` or further out; a prop's face nearer than that (over the road) is ignored."""
    return [tuple(min(f[s], p[s]) if p[s] >= floor else f[s] for s in (0, 1)) for f, p in zip(faces, props)]


MEDIAN_MAX = 6.0               # Phase 22p: a drawn barrier with tarmac beyond it within this is a median between two tarmac
                               # strips (Metropolis's pit wall: a 4-unit block between the race lane and the pit lane)
MEDIAN_MIN = 2.0               # a median wall is at least this wide (a rail on continuous ground: no gap in the drawn ground)
MEDIAN_IN = 0.5                # the wall starts this far inside the face (the face is the median over BARRIER_SPREAD points)
MEDIAN_NEAR = 1.5              # tarmac must lie this far inside the face for the face to stand between two strips
MEDIAN_MIN_RUN = 3             # a median needs this many consecutive points on a side (isolated finds, 1-2 points 15-50 out
                               # where some tarmac lies beyond a face, stood on every course: Alpine 188 R, Pacific 201 R)


def median_blocks(faces, pts, height: HeightFn, ground: Callable[[float, float], list[float]], tarmac: list[Quad16],
                  step: float = VERGE_SCAN_STEP) -> list[tuple[tuple[float, float] | None, tuple[float, float] | None]]:
    """Phase 22p (Pascal, p22play101 Metropolis: "between the pit lane and the race lane ... there is a wall between them
    but player and opponent can cross it without any impact"): per centreline point (left, right), the footprint of a
    drawn barrier standing BETWEEN two tarmac strips — a face (`barrier_faces`) with tarmac MEDIAN_NEAR inside it and
    tarmac again within MEDIAN_MAX beyond it — from MEDIAN_IN inside the face to where the drawn ground resumes
    (`ground`: `mesh_heights` of the ground polygons; the Saturn leaves the ground open under such a block), MEDIAN_MIN
    at least, over runs of MEDIAN_MIN_RUN points at least; None elsewhere. Our walls stood only at the run-off's edge and never inside WALL_MIN_LATERAL, the coverage
    fill paved the 4-unit gap and the measured edge ran on across the pit lane: the fence had no collision."""
    dirs = _smooth_dirs(pts); n = len(pts)
    boxes = _bboxes(tarmac); cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (x0, x1, z0, z1) in enumerate(boxes):
        for cx in range(int(x0 // MESH_BUCKET), int(x1 // MESH_BUCKET) + 1):
            for cz in range(int(z0 // MESH_BUCKET), int(z1 // MESH_BUCKET) + 1):
                cells[(cx, cz)].append(i)
    def covered(x, z):
        return any(boxes[i][0] <= x <= boxes[i][1] and boxes[i][2] <= z <= boxes[i][3] and _point_in_xz(tarmac[i].corners, x, z)
                   for i in cells.get((int(x // MESH_BUCKET), int(z // MESH_BUCKET)), ()))
    out = []
    for k in range(n):
        (x, z), (dx, dz) = pts[k], dirs[k]
        rx, rz = dz, -dx
        row = []
        for sd in (0, 1):
            f = faces[k][sd]; sign = -1.0 if sd == 0 else 1.0
            at = lambda lat: (x + sign * lat * rx, z + sign * lat * rz)
            block = None
            if math.isfinite(f) and covered(*at(f - MEDIAN_NEAR)):
                gap_start = resume = None                     # the drawn ground may run a little past the face (Metropolis 52:
                for j in range(1, int(MEDIAN_MAX / step) + 1):   # to 9.0, the face 8.5, the gap 9.5-12): the gap is looked for
                    lat = f + j * step                        # first, then where the ground resumes beyond it
                    g = bool(ground(*at(lat)))
                    if gap_start is None:
                        if not g:
                            gap_start = lat
                    elif resume is None and g:
                        lo, hi = lat - step, lat                  # the ground's edge to 1/64 of a unit: the wall ends where the
                        for _ in range(5):                        # far strip's tarmac begins (no tarmac under the wall, no
                            mid = (lo + hi) / 2                   # wheel reading tarmac inside its outline)
                            if ground(*at(mid)):
                                hi = mid
                            else:
                                lo = mid
                        resume = hi
                    f1 = f - MEDIAN_IN
                    if covered(*at(lat)) and (resume is not None or (gap_start is None and lat >= f1 + MEDIAN_MIN)):
                        if resume is not None:                    # the wall ends where the far strip's tarmac begins (its slice
                            lo, hi = lat - step, lat              # starts past the ground's edge: Metropolis 51, 12.2 vs 11.6, a
                            for _ in range(5):                    # coverage strip grew over the sliver and under the wall)
                                mid = (lo + hi) / 2
                                if covered(*at(mid)):
                                    hi = mid
                                else:
                                    lo = mid
                            resume = max(resume, hi)
                        block = (f1, resume if resume is not None else f1 + MEDIAN_MIN)
                        break
            row.append(block)
        out.append(row)
    for sd in (0, 1):                                            # runs shorter than MEDIAN_MIN_RUN points are dropped
        k = 0
        while k < n:
            if out[k][sd] is None:
                k += 1; continue
            j = k
            while j < n and out[j][sd] is not None:
                j += 1
            run = j - k
            if run < MEDIAN_MIN_RUN and not (k == 0 and out[n - 1][sd] is not None) and not (j == n and out[0][sd] is not None):
                for i in range(k, j):
                    out[i][sd] = None
            k = j
    return [tuple(row) for row in out]


def median_blocked(pts, blocks) -> Callable[[float, float], bool]:
    """A predicate: (x, z) lies inside the median block of its nearest centreline point (half a scan step of slack); the
    coverage and hole fills leave such samples alone (Phase 22p)."""
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for k, (x, z) in enumerate(pts):
        cells[(int(x // MESH_BUCKET), int(z // MESH_BUCKET))].append(k)
    dirs = _smooth_dirs(pts)
    def blocked(x: float, z: float) -> bool:
        cx, cz = int(x // MESH_BUCKET), int(z // MESH_BUCKET)
        near = [k for ddx in (-1, 0, 1) for ddz in (-1, 0, 1) for k in cells.get((cx + ddx, cz + ddz), ())]
        if not near:
            return False
        k = min(near, key=lambda j: (pts[j][0] - x) ** 2 + (pts[j][1] - z) ** 2)
        (px, pz), (dx, dz) = pts[k], dirs[k]
        lat = (x - px) * dz - (z - pz) * dx                  # right positive
        b = blocks[k][1 if lat >= 0 else 0]
        return b is not None and b[0] - VERGE_SCAN_STEP <= abs(lat) <= b[1] + VERGE_SCAN_STEP
    return blocked


def median_walls(pts, blocks, height: HeightFn) -> list[Quad16]:
    """Phase 22p: one wall quad (surface 5) per pair of consecutive points with a median block on the same side, over the
    blocks' footprint at the road's height (WALL_STEP 0: the originals' walls lie at the ground's height). The arcade's
    corner order and winding as `road_verges`'."""
    dirs = _smooth_dirs(pts); n = len(pts); out = []
    def at(k, sd, lat):
        (x, z), (dx, dz) = pts[k], dirs[k]
        sign = -1.0 if sd == 0 else 1.0
        px, pz = x + sign * lat * dz, z - sign * lat * dx
        return (px, height(px, pz), pz)
    for sd in (0, 1):
        for k in range(n):
            b0, b1 = blocks[k][sd], blocks[(k + 1) % n][sd]
            if b0 is None or b1 is None:
                continue
            inner_b, outer_b = at(k, sd, b0[0]), at(k, sd, b0[1])
            inner_f, outer_f = at((k + 1) % n, sd, b1[0]), at((k + 1) % n, sd, b1[1])
            c = [outer_f, inner_f, inner_b, outer_b] if sd == 0 else [inner_f, outer_f, outer_b, inner_b]
            dx, dz = pts[(k + 1) % n][0] - pts[k][0], pts[(k + 1) % n][1] - pts[k][1]
            vq = Quad16(tuple(c), _mean(c), direction_attr(dx, dz))
            if xz_area(vq) < -MIN_AREA_QUAD and _convex(c):
                out.append(vq)
    return out


def barrier_faces(barriers: list[WorldQuad], pts, height: HeightFn, step: float = VERGE_SCAN_STEP,
                  spread: int | None = None, curbs: list | None = None) -> list[tuple[float, float]]:
    """Per centreline point (left, right): the lateral where a line at the car's body height (the collision + each of
    BARRIER_BODIES), crossing outward from BARRIER_START, first meets a steep drawn face (`is_barrier`), the median over
    BARRIER_SPREAD points either side (math.inf: none within BARRIER_REACH). Phase 22a: the wall stood 30 units of grass
    out while the Saturn draws its cliffs and fences 10-25 from the centre (Pascal drove through Diablo's canyon side)."""
    dirs = _smooth_dirs(pts); n = len(pts)
    tris_of: dict[tuple[int, int], list] = {}
    for q in barriers:
        a = np.array(q.p, float)
        for bx in range(int(a[:, 0].min() // 16), int(a[:, 0].max() // 16) + 1):
            for bz in range(int(a[:, 2].min() // 16), int(a[:, 2].max() // 16) + 1):
                tris_of.setdefault((bx, bz), []).append(id(q))
    by_id = {id(q): np.array(q.p, float) for q in barriers}
    rails = {id(q) for q in barriers if _vertical(q)}
    lats = np.arange(BARRIER_START, BARRIER_REACH + step, step)
    raw = []
    for k, ((x, z), (dx, dz)) in enumerate(zip(pts, dirs)):
        row = []; low = []
        for side, sign in ((0, -1.0), (1, 1.0)):
            px, pz = x + sign * lats * dz, z - sign * lats * dx
            ground = np.array([height(a, b) for a, b in zip(px, pz)])
            near = {i for bx, bz in {(int(a // 16), int(b // 16)) for a, b in zip(px, pz)} for i in tris_of.get((bx, bz), ())}
            tris = np.array([t for i in near for t in (by_id[i][[0, 1, 2]], by_id[i][[0, 2, 3]])]).reshape(-1, 3, 3)
            hits = []
            for body in BARRIER_BODIES:
                line = np.stack([px, ground + body, pz], axis=1)
                h = _first_crossing(line[:-1], line[1:] - line[:-1], tris)
                if h is not None:
                    hits.append(h)
            rail_tris = np.array([t for i in near if i in rails for t in (by_id[i][[0, 1, 2]], by_id[i][[0, 2, 3]])]).reshape(-1, 3, 3)
            line = np.stack([px, ground + RAIL_BODY, pz], axis=1)   # Phase 22a: a low vertical rail (Diablo 246-248: a dark
            h = _first_crossing(line[:-1], line[1:] - line[:-1], rail_tris)   # strip 0.7 tall at 18-20; the car ran past it)
            if h is not None:
                hits.append(h)
            face = float(lats[min(hits)]) if hits else math.inf
            if hits:                                             # Phase 22c: a low curb (a line CURB_TOP up meets nothing
                top = np.stack([px, ground + CURB_TOP, pz], axis=1)   # within a unit beyond) takes no setback: its wall
                ht = _first_crossing(top[:-1], top[1:] - top[:-1], tris)   # stands at it (Pascal, Diablo 94-96: "at the curb")
                if ht is None or lats[ht] > face + 1.0:
                    face += BARRIER_SETBACK
                    low.append(True)                             # (Phase 22k: reported through `curbs`, a list to fill)
                else:
                    low.append(False)
            else:
                low.append(False)
            row.append(face)
        raw.append(row)
        if curbs is not None:
            curbs.append(tuple(low))
    spread = BARRIER_SPREAD if spread is None else spread
    return [tuple(float(np.median([raw[(k + j) % n][s] for j in range(-spread, spread + 1)])) for s in (0, 1))
            for k in range(n)]


def barrier_widths(faces: list[tuple[float, float]], edges, max_width: float = VERGE_GRASS) -> list[tuple[float, float]]:
    """Per centreline point (left, right), as `shore_widths`: the grass width that puts the wall's inner line (which
    `road_verges` lays WALL_OVERLAP + VERGE_SCAN_STEP inside the grass's outer line) BARRIER_SETBACK inside the drawn
    face (`barrier_faces`), clamped to [the wall's floor, max_width] and rounded up to BARRIER_QUANT (Phase 22k: it was
    rounded down to 2.5 without the inner line's offset, and the wall stood 2.5-5 units before the rock)."""
    n = len(faces)
    floor = lambda k, s: max(BARRIER_MIN_RUNOFF, wall_min(k, s) + WALL_OVERLAP + VERGE_SCAN_STEP - edges[k][s])
    snap = lambda w: w if w >= max_width else math.ceil(w / BARRIER_QUANT - 1e-9) * BARRIER_QUANT   # fewer width changes, fewer grass steps
    return [tuple(min(max_width, max(floor(k, s), snap(faces[k][s] - BARRIER_SETBACK - edges[k][s] + WALL_OVERLAP + VERGE_SCAN_STEP)))
                  for s in (0, 1)) for k in range(n)]


TRIM_STEP = 0.5                # the tarmac's trim line is checked every this many units of its quads' edges


LANE_MIN_SCALE = 0.5           # Phase 22c: the AI lines narrow at most to this share of their offsets (the +8 line at 4)
LANE_TAPER = 0.05              # ... and widen back by this much per centreline point (10 units) either side
LANE_REACH = 10                # ... over at most this many points
LANE_MIN_WALL = 6.5            # a wall place nearer the centre than this narrows nothing (a face measured over the road, Diablo
                               # 93-97 at 7 of 12; Amazon's curb at 10-11 lies under the slice's tarmac, which runs to 14-15)
LANE_START_CLEAR = 6           # ... and nothing narrows within this many points of the start line (Alpine's gantry legs, 9 out
                               # at points 0 and 4, pulled the wall over the grid and the start-line band)
_LANES: list[tuple[float, float]] | None = None   # the lane scales of the collision being built (saturn_collision sets them)


def lane_scales(faces, points=(), always=None) -> list[tuple[float, float]]:
    """Phase 22c (Pascal p22play28, Amazon's first right corner: a curb 10.5 out at the road's edge "should have stopped
    the car"; Diablo 321-327, rock at 8.5): per centreline point (left, right), the share of the AI lines' offsets that
    leaves a drawn barrier's wall place (the face less BARRIER_SETBACK; a curb's: the curb) WALL_CLEARANCE + 1.5 off the
    outer line, where that place lies inside WALL_MIN_LATERAL and not nearer the centre than LANE_MIN_WALL; 1 elsewhere,
    LANE_MIN_SCALE at least, tapering by LANE_TAPER per point over LANE_REACH points. Pascal (3 Nov): only at the
    centreline points he named (`points`: inclusive (first, last) ranges, CoursePlan.lane_points) — a course-wide rule
    pulled Diablo's walls in to its white lines ("never bring it back"); nowhere else does anything narrow. The points within LANE_START_CLEAR of the start line stay at 1 (the taper still reaches
    them). Phase 22k (3b, Pascal): a drawn curb's or a placed object's face (`always`, per point and side; math.inf
    elsewhere) narrows at every point: the car drove through curbs and objects the terrain's rule left alone."""
    n = len(faces)
    def scale(f):
        w = f - BARRIER_SETBACK
        if not math.isfinite(w) or w >= WALL_MIN_LATERAL or w < LANE_MIN_WALL:
            return 1.0
        return max(LANE_MIN_SCALE, (w - (WALL_MIN_LATERAL - 8.0)) / 8.0)
    start = lambda k: min(k, n - k) <= LANE_START_CLEAR
    named = lambda k: any(a <= k <= b for a, b in points)
    raw = [tuple(min(scale(faces[k][sd]) if named(k) else 1.0, scale(always[k][sd]) if always is not None else 1.0) for sd in (0, 1))
           if not start(k) else (1.0, 1.0) for k in range(n)]
    return [tuple(min(1.0, min(raw[(k + j) % n][sd] + LANE_TAPER * abs(j) for j in range(-LANE_REACH, LANE_REACH + 1)))
                  for sd in (0, 1)) for k in range(n)]


LINE_CLEAR = 3.0               # Phase 22n: the outer AI lines keep this far inside the Saturn's own tarmac band (WALL_CLEARANCE)
SHIFT_TAPER = 1.0              # ... and the lines' sideways shift changes by at most this per centreline point (10 units)
SHIFT_REACH = 60.0             # the band is measured this far either side of the centreline
SHIFT_GAP = 1.0                # slices this close across the road are one band
SHIFT_MIN_RUN = 8              # a shift needs its cause over at least this many consecutive points: a shorter notch in the band (a
                               # junction's mouth at Metropolis 186-191, 60 units) stays with the coverage fill, else the lines
                               # swung 11 units across the crossing and back and three cars read the other road's point
SHIFT_GRID_CLEAR = (20, 25)    # no shift within this many points before / after the start line: the grid's rows stand there at
                               # the game's fixed places (Surfers Road's right column lost its tarmac when the band moved 10 left).
                               # The build passes the template's own zone: Big Forest's grid stands 13 points before the line to 3
                               # after, Bay Bridge's and Acropolis's from the line to 15 after (Metropolis's building, 322-352,
                               # lies 13-43 before its line)
_SHIFT: list[float] | None = None   # the lines' shift (right positive) of the collision being built (saturn_collision sets it)
_NAMED: tuple = ()                 # the named lane-point ranges (CoursePlan.lane_points) of the collision being built: the wall's
                                   # floor follows the lines' shift only there (Pascal: walls never nearer than his validated state
                                   # except at the spots he names)


BAND_DECK = 4.0                # a quad whose corners all lie more than this above or below the road at the point is another deck
BAND_LAP_WINDOW = 15           # ... and only when its place on the lap (`_front_points`) is within this many points of the point: a road
                               # crossing at grade (Metropolis 206-210: a 38-unit slab the lap crosses again 150 points on) is not the band
BAND_STEP = 1.0                # ... and a strip joins the band only where its surface continues the band's within this at the join
                               # (a banking rises strip by strip; Metropolis's junction road, 4 units up, met the band in plan)


def tarmac_band(tarmac: list[Quad16], pts, height: HeightFn | None = None, places: list[int] | None = None) -> list[tuple[float, float]]:
    """Per centreline point (left, right): the lateral extent, in plan, of the tarmac band under the point — the quads the
    lateral line through the point crosses, chained from the one under the centreline across gaps of at most SHIFT_GAP
    (left negative, right positive; (0, 0) where no quad lies under the point). With `height`, a quad whose corners all
    lie more than BAND_DECK off the road's height at the point is left out (Metropolis's decks cross in plan); with
    `places` (each quad's point on the lap, `_front_points`), a quad placed more than BAND_LAP_WINDOW points away is
    left out too (a road crossing at grade)."""
    dirs = _smooth_dirs(pts); n = len(pts)
    boxes = _bboxes(tarmac)
    out = []
    for k, ((x, z), (dx, dz)) in enumerate(zip(pts, dirs)):
        rx, rz = dz, -dx
        y = height(x, z) if height is not None else None
        spans = []; others = []                                     # the band's candidates / another road's quads (far on the lap)
        for i, (q, b) in enumerate(zip(tarmac, boxes)):
            if b[0] > x + SHIFT_REACH or b[1] < x - SHIFT_REACH or b[2] > z + SHIFT_REACH or b[3] < z - SHIFT_REACH:
                continue
            far = places is not None and min(abs(places[i] - k), n - abs(places[i] - k)) > BAND_LAP_WINDOW
            if y is not None and all(abs(c[1] - y) > BAND_DECK for c in q.corners):
                continue
            al = [(c[0] - x) * dx + (c[2] - z) * dz for c in q.corners]
            la = [(c[0] - x) * rx + (c[2] - z) * rz for c in q.corners]
            cross = []
            for i in range(4):                                      # where the quad's edges cross the lateral line (along 0)
                a0, a1, l0, l1 = al[i], al[(i + 1) % 4], la[i], la[(i + 1) % 4]
                if (a0 > 0) != (a1 > 0) and abs(a1 - a0) > 1e-9:
                    cross.append(l0 + (l1 - l0) * (0 - a0) / (a1 - a0))
            if len(cross) >= 2:
                (others if far else spans).append((min(cross), max(cross), q))
        spans.sort(key=lambda sp: sp[:2])
        at_lat = lambda q, lat: tgp_height(q.corners, x + lat * rx, z + lat * rz)   # a quad's surface at a lateral
        here = [sp for sp in spans if sp[0] - SHIFT_GAP <= 0 <= sp[1] + SHIFT_GAP
                and (y is None or abs(at_lat(sp[2], 0.0) - y) <= BAND_STEP)]   # the quads under the point AT the road's height
        if not here:                                                # (Metropolis: the deck above seeded the band with its width)
            out.append((0.0, 0.0)); continue
        band = list(here)
        lo, hi = min(sp[0] for sp in here), max(sp[1] for sp in here)
        grown = True
        while grown:                                                # chain the strips beside it across the road, where their
            grown = False                                           # surface continues the band's at the join (BAND_STEP)
            for a, b, q in spans:
                if a <= hi + SHIFT_GAP and b >= lo - SHIFT_GAP and (a < lo or b > hi):
                    join = hi if b > hi else lo
                    edge = [sp for sp in band if sp[0] - 1e-6 <= join <= sp[1] + 1e-6]
                    if edge and abs(at_lat(q, join) - at_lat(edge[0][2], join)) > BAND_STEP:
                        continue
                    lo, hi = min(lo, a), max(hi, b); band.append((a, b, q)); grown = True
        for a, b, q in others:                                      # another road crossing at grade shares the slab: the band
            if y is not None and abs(at_lat(q, max(lo, min(hi, (a + b) / 2))) - y) > BAND_DECK:
                continue                                            # (not one on another level)
            if a > 0 and a < hi:                                    # ends where that road's quads begin (Metropolis 190-210:
                hi = max(0.0, a)                                    # the lines shifted onto the crossing and three cars read
            if b < 0 and b > lo:                                    # the other road's point, 172 -> 52)
                lo = min(0.0, b)
        out.append((lo, hi))
    return out


def lane_shift(tarmac: list[Quad16], pts, lanes=None, clear: float = LINE_CLEAR, taper: float = SHIFT_TAPER,
               height: HeightFn | None = None, grid_clear: tuple[int, int] = SHIFT_GRID_CLEAR) -> list[float]:
    """Phase 22n: per centreline point, how far the AI lines move sideways (right positive) so that their outer lines
    (+-8, scaled by `lanes`) keep `clear` inside the Saturn's own tarmac band (`tarmac_band`): the lap route follows ONE
    strip and the centreline is its middle, so where that strip is the road's edge one (the white line at Metropolis's
    hairpin, the inner strip of the Oval's banking) the lines straddled it onto the sidewalk or the painted grass. A side
    with room is never the reason to move (the pit lane beside the Oval's straight); a band too narrow for both sides
    centres the lines in it; nothing moves within `grid_clear` points of the start line (the grid's rows) nor for a cause
    shorter than SHIFT_MIN_RUN points (a junction's mouth); the shift tapers by
    `taper` per point, the move starting early rather than falling short."""
    from vrtools.convert.road import AI_OFFSETS
    n = len(pts); band = tarmac_band(tarmac, pts, height, _front_points(tarmac, pts, _dirs(pts)))
    outer = max(AI_OFFSETS)
    raw = []
    for k in range(n):
        lo, hi = band[k]
        if hi - lo < 1e-6 or k <= grid_clear[1] or n - k <= grid_clear[0]:
            raw.append(0.0); continue
        sl, sr = (lanes[k][0], lanes[k][1]) if lanes is not None else (1.0, 1.0)
        need_l, need_r = outer * sl + clear, outer * sr + clear
        if hi >= need_r and -lo >= need_l:
            raw.append(0.0)
        elif hi - lo < need_l + need_r:
            raw.append((lo + hi) / 2)
        elif hi < need_r:
            raw.append(max(hi - need_r, lo + need_l))
        else:
            raw.append(min(lo + need_l, hi - need_r))
    k = 0                                                       # a run of same-signed shifts shorter than SHIFT_MIN_RUN is a notch
    while k < n:
        if abs(raw[k]) < 1e-9:
            k += 1; continue
        e = k
        while e < n and abs(raw[e]) > 1e-9 and (raw[e] > 0) == (raw[k] > 0):
            e += 1
        if e - k < SHIFT_MIN_RUN:
            for j in range(k, e):
                raw[j] = 0.0
        k = e
    out = []
    for k in range(n):
        neg = min(min(raw[(k + j) % n], 0.0) + taper * abs(j) for j in range(-n // 2, n // 2 + 1))
        pos = max(max(raw[(k + j) % n], 0.0) - taper * abs(j) for j in range(-n // 2, n // 2 + 1))
        out.append(min(neg, 0.0) + max(pos, 0.0))
    return out


def wall_min(k: int, side: int) -> float:
    """The nearest a wall may stand at centreline point k on `side` (0 left, 1 right): WALL_MIN_LATERAL, less what the
    point's narrowed AI lines give back (Phase 22c, `lane_scales`)."""
    shift = _SHIFT[k] if _SHIFT is not None and 0 <= k < len(_SHIFT) else 0.0   # Phase 22n: the lines moved aside: on the side
    named = any(a <= k <= b for a, b in _NAMED)                                  # they moved towards the floor moves out with them
    base = WALL_MIN_LATERAL if _LANES is None or not (0 <= k < len(_LANES)) else WALL_MIN_LATERAL - 8.0 * (1.0 - _LANES[k][side])
    delta = shift if side == 1 else -shift                                       # (Amazon 59-85 L: the field parked on a wall at
    return base + (delta if delta > 0 or named else 0.0)                         # 12.5 with the lines at 16); on the side they
                                                                                 # left it may come in only at the named points


def grass_floor(k: int, side: int) -> float:
    """The nearest the grass's inner line may start at centreline point k on `side`: GRASS_FLOOR, less what the point's
    narrowed AI lines give back (Phase 22c review: as `wall_min`; a fixed 8.5 left holes before Diablo's curbs)."""
    return GRASS_FLOOR - (WALL_MIN_LATERAL - wall_min(k, side))


# Phase 22g (Pascal, rec65: Metropolis's "floor disappear" where the lap crosses itself): the courses whose road slices
# take their corner heights near their own lap arc (`arc_height`'s near_arc), so a corner over the deck below does not
# take that deck's height. Keyed by the TRCK file's SHA-1 prefix; Metropolis only (on Amazon Falls, where the road
# passes close to itself, it moved 285 corners, 6 of 20 measurable ones away from the drawn ground).
DECK_HINT_COURSES = {"ce590d8421e3ba76"}


def pit_lane_polygons(sat: SaturnCourse) -> list[list[tuple[float, float, float]]]:
    """Phase 22f: the arcade-space corners (y 0) of the course's pit-lane slices (`place.MAIN_ROAD_START`), or none."""
    import hashlib
    from vrtools.convert.place import MAIN_ROAD_START
    entry = MAIN_ROAD_START.get(hashlib.sha1(sat.trck.data).hexdigest()[:16]) if sat.trck is not None else None
    if entry is None:
        return []
    segs = {s.index: s for s in sat.segments}
    out = []
    for i in entry.slices:
        c = segs[i].corners() if i in segs else None
        if c:
            out.append([(p[0], 0.0, p[2]) for p in (to_arcade(x, 0.0, z) for x, z in c)])
    return out


def pit_lane_centres(sat: SaturnCourse, centreline) -> list[tuple[float, float]]:
    """Phase 22g: the course's pit lane as a polyline in arcade (x, z), from its mouth: the slice centres of
    `place.PitLane.path` in order, or else of its slices averaged per nearest race-line point and ordered along the lap
    from the first (the lane's slices lie two abreast in places). Empty for a course without one. Call inside the
    course's placement."""
    from vrtools.convert.place import pit_lane_of
    pit = pit_lane_of(sat)
    if pit is None:
        return []
    segs = {s.index: s for s in sat.segments}

    def centre(i):
        c = segs[i].corners() if i in segs else None
        if not c:
            return None
        x, _, z = to_arcade(sum(p[0] for p in c) / len(c), 0.0, sum(p[1] for p in c) / len(c))
        return x, z
    pa = np.array(centreline, float); n = len(pa)
    if pit.path:
        return [c for c in (centre(i) for i in pit.path) if c is not None]
    bins: dict[int, list[tuple[float, float]]] = {}
    for i in pit.slices:
        c = centre(i)
        if c is not None:
            k = int(np.argmin((pa[:, 0] - c[0]) ** 2 + (pa[:, 1] - c[1]) ** 2))
            bins.setdefault(k, []).append(c)
    if not bins:
        return []
    ks = sorted(bins)
    gaps = [((ks[(j + 1) % len(ks)] - ks[j]) % n, j) for j in range(len(ks))]
    first = ks[(max(gaps)[1] + 1) % len(ks)]                         # the lane starts after the largest gap round the lap
    order = sorted(ks, key=lambda k: (k - first) % n)
    return [(sum(p[0] for p in bins[k]) / len(bins[k]), sum(p[1] for p in bins[k]) / len(bins[k])) for k in order]


def pit_lane_line(sat: SaturnCourse, centreline) -> list[tuple[float, float]]:
    """Phase 22g: the pit lane's polyline for the HUD map's outline; Phase 22h (Pascal: the map's pit connection looked
    "cut"): both ends run on to the nearest race-line point."""
    line = pit_lane_centres(sat, centreline)
    if not line:
        return line
    pa = np.array(centreline, float)
    ends = [tuple(pa[int(np.argmin((pa[:, 0] - p[0]) ** 2 + (pa[:, 1] - p[1]) ** 2))]) for p in (line[0], line[-1])]
    return [(float(ends[0][0]), float(ends[0][1]))] + line + [(float(ends[1][0]), float(ends[1][1]))]


def _tarmac_quad_at(col, x: float, z: float) -> int | None:
    for k, q in enumerate(col.quads[:col.n_tarmac]):
        if abs(q.centre[0] - x) < 80 and abs(q.centre[2] - z) < 80 and _point_in_xz(q.corners, x, z):
            return k
    return None


PIT_ENTRY_DEPTH = 40.0        # a derived entry quad lies this far into the lane: the mouth's quad can reach onto the main road
                              # (Pacific Coast's is 56 units across; Pascal, rec82: PIT WORK "far outside the pit lane")
PIT_ENTRY_SPAN = 150.0        # ... and, failing a separated point, no farther than this
PIT_ENTRY_COVER = 0.9         # the game checks the entry quad and the next: the pair must cover the lane's width (a lane two quads
                              # wide let the car pass beside them) and, where it can, all the tarmac across the lane (Surfers Road's
                              # lane shares open tarmac with the road for 110 units and the car cut in past the pair: rec84)
PIT_ENTRY_ACROSS = 45         # units either side of the lane's centre for the all-tarmac test (the lane's width for the lane test: 30)


def pit_entry_coverage(sat: SaturnCourse, col, k: int, at: tuple[float, float], direction: tuple[float, float],
                       all_tarmac: bool = False, partner: int | None = None) -> float:
    """The share of the pit lane's width at `at` (across `direction`, sampled every 2 units over +-30; `all_tarmac`: of
    every tarmac point over +-PIT_ENTRY_ACROSS) that tarmac quads `k` and `k + 1` cover: the game's PIT WORK check fires
    on either."""
    nx, nz = -direction[1], direction[0]
    L = math.hypot(nx, nz) or 1e-9
    nx, nz = nx / L, nz / L
    tarmac = col.quads[:col.n_tarmac]
    if all_tarmac:
        pts = [(at[0] + t * nx, at[1] + t * nz) for t in range(-PIT_ENTRY_ACROSS, PIT_ENTRY_ACROSS + 1, 3)]
        pts = [q for q in pts if _tarmac_quad_at(col, *q) is not None]
    else:
        lane = [[(p[0], 0.0, p[2]) for p in poly] for poly in pit_lane_polygons(sat)]
        pts = [(at[0] + t * nx, at[1] + t * nz) for t in range(-30, 31, 2)]
        pts = [q for q in pts if any(_point_in_xz(poly, *q) for poly in lane)]
    if len(pts) < 3:
        return 0.0
    quads = [tarmac[i] for i in (k, k + 1 if partner is None else partner) if 0 <= i < len(tarmac)]
    return sum(1 for q in pts if any(_point_in_xz(qq.corners, *q) for qq in quads)) / len(pts)


def pit_entry_pair(sat: SaturnCourse, quads: list[Quad16], n_tarmac: int, k: int, centreline) -> tuple[list[Quad16], int, int]:
    """Phase 22j: the quad after the entry quad `k` in the list is made part of the lane's mouth, as the game fires PIT WORK
    on either: the side-by-side lane quad whose footprint with k's best covers the lane's width is moved to k + 1 (a lane
    two slices wide: the Oval, Surfers Road), or, when none widens the pair, k is duplicated there. Returns the quads,
    n_tarmac and the entry index (unchanged)."""
    from types import SimpleNamespace
    col = SimpleNamespace(quads=quads, n_tarmac=n_tarmac)
    lane_line = pit_lane_centres(sat, centreline)
    pa = np.array(centreline, float)
    q = quads[k]; x, z = q.centre[0], q.centre[2]
    i = min(range(len(lane_line)), key=lambda j: math.hypot(lane_line[j][0] - x, lane_line[j][1] - z))
    a, b = lane_line[max(0, i - 1)], lane_line[min(len(lane_line) - 1, i + 1)]
    direction = (b[0] - a[0], b[1] - a[1])
    best, best_cover = None, pit_entry_coverage(sat, col, k, (x, z), direction, partner=k)
    for j in range(n_tarmac - 1):                                     # (never the start-line band, the pinned last quad)
        if j == k:
            continue
        cx, cz = quads[j].centre[0], quads[j].centre[2]
        if math.hypot(cx - x, cz - z) > 30:
            continue
        d_lane = min(math.hypot(px - cx, pz - cz) for px, pz in lane_line)
        d_road = float(np.sqrt(((pa[:, 0] - cx) ** 2 + (pa[:, 1] - cz) ** 2).min()))
        if not (d_lane < PIT_LANE_HALF_WIDTH and d_lane < d_road):
            continue
        cover = pit_entry_coverage(sat, col, k, (x, z), direction, partner=j)
        if cover > best_cover + 0.05:
            best, best_cover = j, cover
    out = list(quads)
    if best is None:
        out.insert(k + 1, out[k])
    else:
        partner = out.pop(best)
        if best < k:
            k -= 1
        out.insert(k + 1, partner)
        return out, n_tarmac, k
    return out, n_tarmac + 1, k


ROAD_LEVEL = 1.0               # Phase 22p: drawn ground within this of the road's height, of a colour the road has under the
                               # centreline nearby, is the drawn road (the pit mouth: a widening of the race lane)
ROAD_BEYOND = (1.5, 3.0, 4.5, 6.0)   # ... sampled this far past a prop's face: drawn road under three of the four and the prop
                               # stands in the road (Metropolis 49 R: the pit fence's start post 7.5 out, the mouth to 20.5
                               # beyond it; the trim cut the mouth at 12.5 and the pit could not be entered)


def in_road_faces(prop_faces, pts, height: HeightFn, lookup, levels: float = ROAD_LEVEL) -> list[tuple[float, float]]:
    """Phase 22p: `prop_faces` with a face set to math.inf where the drawn road continues beyond it (`lookup`:
    `mesh_lookup` of the ground polygons; the road's colours are those under the centreline within two points): a post
    standing in the road is no road end — the trim and the run-off wall leave the tarmac beyond it alone."""
    dirs = _smooth_dirs(pts); n = len(pts); out = []
    def road_rgb(k):
        return {rgb for j in (-2, -1, 0, 1, 2) for y, rgb in lookup(*pts[(k + j) % n]) if abs(y - height(*pts[(k + j) % n])) <= levels}
    for k in range(n):
        (x, z), (dx, dz) = pts[k], dirs[k]
        row = []
        for sd in (0, 1):
            f = prop_faces[k][sd]
            if math.isfinite(f):
                sign = -1.0 if sd == 0 else 1.0
                rgbs = road_rgb(k)
                hits = 0
                for d in ROAD_BEYOND:
                    sx, sz = x + sign * (f + d) * dz, z - sign * (f + d) * dx
                    if any(rgb in rgbs and abs(y - height(sx, sz)) <= levels for y, rgb in lookup(sx, sz)):
                        hits += 1
                if hits >= 3:
                    f = math.inf
            row.append(f)
        out.append(tuple(row))
    return out


def pit_entry_quad(sat: SaturnCourse, col, centreline=None, require_pair: bool = True) -> int | None:
    """Phase 22f: the tarmac quad at the course's pit-lane mouth (`place.PitLane.entry_slice`, its centre; Phase 22i:
    else the first of `pit_lane_centres` at least PIT_ENTRY_DEPTH into the lane, so `centreline` is needed) for the
    entry's pit quad (the game's PIT WORK check), or None for a course without a pit lane."""
    from vrtools.convert.place import pit_lane_of
    pit = pit_lane_of(sat)
    if pit is None:
        return None
    lane = [[(p[0], 0.0, p[2]) for p in poly] for poly in pit_lane_polygons(sat)]
    lane_line = pit_lane_centres(sat, centreline) if centreline is not None else []
    pa = np.array(centreline, float) if centreline is not None else None

    def pair_in_lane(k: int) -> bool:
        """Phase 22j (Pascal, p22play56: "even on the main we get pulled into the pit"): the game fires PIT WORK on the entry
        quad OR THE NEXT IN THE LIST, so the next must belong to the lane too (the list now has strips and hole fillers
        beside their quads): its centre nearer the lane's line than the race line, and within the lane's half width of it."""
        if not require_pair:
            return True
        if k + 1 >= col.n_tarmac:
            return False
        q = col.quads[k + 1]
        if q.corners == col.quads[k].corners:                       # the build's duplicate of the entry quad
            return True
        x, z = q.centre[0], q.centre[2]
        if lane_line and pa is not None:
            d_lane = min(math.hypot(px - x, pz - z) for px, pz in lane_line)
            d_road = float(np.sqrt(((pa[:, 0] - x) ** 2 + (pa[:, 1] - z) ** 2).min()))
            return d_lane < PIT_LANE_HALF_WIDTH and d_lane < d_road
        return any(_point_in_xz(poly, x, z) for poly in lane)
    if pit.entry_slice is not None:
        seg = next(s for s in sat.segments if s.index == pit.entry_slice)
        c = seg.corners()
        x, _, z = to_arcade(sum(p[0] for p in c) / len(c), 0.0, sum(p[1] for p in c) / len(c))
        k = _tarmac_quad_at(col, x, z)
        if k is None:
            raise ConvertError(f"no tarmac at the pit lane's mouth ({x:.0f}, {z:.0f})")
        if pair_in_lane(k):
            return k
        for j in range(col.n_tarmac):                               # another lane quad under the mouth, or the nearest
            if j != k and pair_in_lane(j) and _point_in_xz(col.quads[j].corners, x, z):
                return j
        near = sorted((math.hypot(col.quads[j].centre[0] - x, col.quads[j].centre[2] - z), j) for j in range(col.n_tarmac)
                      if pair_in_lane(j) and any(_point_in_xz(poly, col.quads[j].centre[0], col.quads[j].centre[2]) for poly in lane))
        if not near or near[0][0] > 30:
            raise ConvertError(f"no pit entry quad pair in the lane near ({x:.0f}, {z:.0f})")
        return near[0][1]
    elif centreline is not None:
        line = pit_lane_centres(sat, centreline)
        if not line:
            return None
        cum = [0.0]
        for a, b_ in zip(line, line[1:]):
            cum.append(cum[-1] + math.dist(a, b_))
        far = max(PIT_ENTRY_SPAN, cum[-1] / 2 - PIT_BOX_MIN_RUN)          # short of the box (mid-lane) by the autopilot's run
        points = []
        for i in range(1, len(line)):
            if PIT_ENTRY_DEPTH <= cum[i] <= far and (k := _tarmac_quad_at(col, *line[i])) is not None and pair_in_lane(k):
                a, b_ = line[max(0, i - 1)], line[min(len(line) - 1, i + 1)]
                points.append((i, k, (b_[0] - a[0], b_[1] - a[1])))
        if not points:
            raise ConvertError("no tarmac along the pit lane for its entry quad")
        for i, k, d in points:                                             # a point where the pair spans all the tarmac across
            if pit_entry_coverage(sat, col, k, line[i], d, all_tarmac=True) >= PIT_ENTRY_COVER:
                return k
        best = None
        for i, k, d in points:                                             # else one where it spans the lane's width
            if cum[i] > PIT_ENTRY_SPAN and best is not None:
                break
            cover = pit_entry_coverage(sat, col, k, line[i], d)
            if best is None or cover > best[0]:
                best = (cover, k)
            if cover >= PIT_ENTRY_COVER:
                break
        return best[1]
    else:
        return None
    return None


PIT_BOX_MIN_RUN = 40.0        # the autopilot's straight run from the entry quad to the box, at least (it slows below 100 units)
PIT_BOX_DEPTH_MIN = 130.0     # a box lies mid-lane (Pascal, rec80: Pacific Coast's at 130 was "too early"), but at least this far in


def pit_box(sat: SaturnCourse, col, centreline) -> tuple[float, float, float, int] | None:
    """Phase 22i: where the pit sequence parks the car: (x, y, z, heading) for the entry's pit box. The game's pit autopilot
    (boot 0xfe968d) drives the car in a straight line from the entry quad to the box, so the box is the lane point
    `PitLane.depth` units from the mouth (Diablo's spawn, as `place._pit_placement` put it; by default half the lane's
    length, at least PIT_BOX_DEPTH_MIN), or the farthest nearer one
    the straight run reaches over tarmac; y is the tarmac's height there; the heading is the lane's direction at the box
    in the game's units (1/65536 turn; h gives the direction (-sin h, cos h)). None for a course without a pit lane."""
    from vrtools.convert.place import pit_lane_of
    pit = pit_lane_of(sat)
    if pit is None:
        return None
    line = pit_lane_centres(sat, centreline)
    k = pit_entry_quad(sat, col, centreline)
    if k is None or len(line) < 3:
        return None
    ex, ez = col.quads[k].centre[0], col.quads[k].centre[2]
    cum = [0.0]
    for a, b in zip(line, line[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    depth = pit.depth if pit.depth is not None else max(PIT_BOX_DEPTH_MIN, cum[-1] / 2)
    j0 = min(range(len(cum)), key=lambda i: abs(cum[i] - depth))
    tarmac = col.quads[:col.n_tarmac]

    def straight_run_on_tarmac(x, z) -> bool:
        run = math.dist((ex, ez), (x, z))
        return run >= PIT_BOX_MIN_RUN and all(
            _tarmac_quad_at(col, ex + (x - ex) * t / run, ez + (z - ez) * t / run) is not None for t in range(0, int(run) + 1, 4))
    for j in range(j0, 0, -1):
        x, z = line[j]
        if straight_run_on_tarmac(x, z):
            break
    else:
        raise ConvertError(f"no pit box reachable in a straight line from the pit entry ({ex:.0f}, {ez:.0f})")
    (ax, az), (bx, bz) = line[max(0, j - 1)], line[min(len(line) - 1, j + 1)]
    heading = round(-math.atan2(bx - ax, bz - az) * 65536 / (2 * math.pi)) % 65536
    under = _tarmac_quad_at(col, x, z)
    q = tarmac[under] if under is not None else min(tarmac, key=lambda q: (q.centre[0] - x) ** 2 + (q.centre[2] - z) ** 2)
    y = sum(c[1] for c in q.corners) / 4
    return float(x), float(y), float(z), int(heading)


def trim_tarmac(tarmac: list[Quad16], pts, faces, height_of=None, keep=()) -> tuple[list[Quad16], int]:
    """Phase 22a: the tarmac cut back to BARRIER_SETBACK inside the drawn face (never inside WALL_MIN_LATERAL) where the
    Saturn's road slice reaches past it (Diablo 115-122: tarmac to 29.5, the drawn road ends in a lip at 23.8 with
    nothing past it; a wall cannot stand over tarmac, so the car drove off the drawn edge). Each quad is clipped against
    the trim lines of its nearest centreline point (a line parallel to the road on each side); the new corners keep the
    quad's surface (`tgp_height`); a clipped five- or six-cornered piece is split into quads (a triangle carries its
    fourth corner mid-edge, as the Saturn's); a quad wholly past the line is dropped. A quad whose centre lies in one of
    the `keep` polygons (XZ corner lists: Phase 22f, a pit lane beside the main road, past the rock between them) is
    left whole. Returns (tarmac, quads changed)."""
    dirs = _smooth_dirs(pts); n = len(pts)
    out, changed = [], 0
    pa = np.array(pts, float)
    for q in tarmac:
        cx, cz = q.centre[0], q.centre[2]
        if any(_point_in_xz(pk, cx, cz) for pk in keep):
            out.append(q)
            continue
        k = int(np.argmin((pa[:, 0] - cx) ** 2 + (pa[:, 1] - cz) ** 2))
        poly = [(p[0], p[2]) for p in q.corners]
        cut = False
        for side, sign in ((0, -1.0), (1, 1.0)):
            f = min(faces[(k + j) % n][side] for j in (-1, 0, 1))
            if not math.isfinite(f):
                continue
            limit = max(f - BARRIER_SETBACK, wall_min(k, side))
            (x0, z0), (dx, dz) = pts[k], dirs[k]
            rx, rz = sign * dz, -sign * dx                    # outward on this side
            lat = lambda p: (p[0] - x0) * rx + (p[1] - z0) * rz
            if max(lat(p) for p in poly) <= limit + 1e-6:
                continue
            clipped = []
            for a, b in zip(poly, poly[1:] + poly[:1]):       # Sutherland-Hodgman against lat <= limit
                la, lb = lat(a), lat(b)
                if la <= limit:
                    clipped.append(a)
                if (la <= limit) != (lb <= limit):
                    t = (limit - la) / (lb - la)
                    clipped.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
            poly = clipped
            cut = True
            if len(poly) < 3:
                break
        if not cut:
            out.append(q)
            continue
        changed += 1
        if len(poly) < 3:
            continue
        pts3 = [(x, tgp_height(q.corners, x, z), z) for x, z in poly]
        pieces = [pts3] if len(pts3) <= 4 else [pts3[:4], [pts3[0], pts3[3], *pts3[4:]]]
        for piece in pieces:
            if len(piece) == 3:                               # a triangle: its fourth corner mid-edge (0-1-2 in a line: the
                a, b, c = piece                               # TGP takes 2-3-0)
                piece = [a, tuple((a[i] + b[i]) / 2 for i in range(3)), b, c]
            if len(piece) != 4:
                continue
            nq = Quad16(tuple(piece), _mean(piece), q.attr)
            if abs(xz_area(nq)) < MIN_AREA_QUAD:
                continue
            if xz_area(nq) > 0:                               # the arcade's winding (negative area)
                nq = Quad16(tuple(reversed(piece)), nq.centre, q.attr)
            out.append(nq)
    return out, changed


CLIP_DECK_OFFSET = 3.0         # Phase 22g: a corner further than this from the height function is on another deck (a
                               # sink or a bank's residual is a fraction of a unit)
CLIP_SLIVER = 0.1              # a wall cut may leave a sliver this thin uncovered along the wall's edge (Phase 22a: 0.25;
                               # Phase 22c: Pascal's Oval banked turn found a 0.25 seam, a wheel on no quad)
CLIP_OVERLAP = 0.0             # a cut ends this far inside the wall (Phase 22c tried 0.3: a slow car's wheel was inside the
                               # wall's outline before it read the wall, no edge crossed, it climbed the Oval's banked wall
                               # and the put-back to its own quad (the wall) looped)


SLIVER_AREA = 40.0             # Phase 22k: a tarmac quad smaller than this (xz units) whose corners all lie inside wall quads at its
SLIVER_HEIGHT = 2.0            # own height (within this) is dropped: Metropolis's hairpin, where a 20-unit sliver of the far road's
                               # slice lay under this road's wall and the TGP gave a car the sliver (0.17 nearer) over the wall


def drop_slivers_under_walls(tarmac: list[Quad16], walls: list[Quad16]) -> tuple[list[Quad16], int]:
    """Phase 22k: `tarmac` without the slivers (under SLIVER_AREA) whose four corners lie inside wall quads at their own
    height (SLIVER_HEIGHT), and how many went. A road-sized quad under a wall stays (the wall is the mistake there), and
    so does a sliver under a wall of another deck."""
    boxes = _bboxes(walls)
    def under(c):
        return any(b[0] <= c[0] <= b[1] and b[2] <= c[2] <= b[3] and _point_in_xz(w.corners, c[0], c[2])
                   and abs(tgp_height(w.corners, c[0], c[2]) - c[1]) <= SLIVER_HEIGHT for w, b in zip(walls, boxes))
    kept = [q for q in tarmac if abs(xz_area(q)) >= SLIVER_AREA or not all(under(c) for c in q.corners)]
    return kept, len(tarmac) - len(kept)


def clip_at_walls(grass: list[Quad16], walls: list[Quad16], height: HeightFn | None = None, guard: bool = False,
                  plane: bool = False) -> list[Quad16]:
    """Phase 22a: each grass (or tarmac) quad cut at the wall's inner edge (Pascal p22play17: the grass ran up to a unit under the
    wall; the TGP keeps a wheel on the grass there, so the V60's shallow-angle edge test (`0xfec3d7`) found no wall edge
    crossed and the car climbed the step). Along each of the quad's two lateral edges (corners 0-1 and 2-3), an end
    inside a wall moves to where the edge enters it (bisected; at `height` plus the moved corner's own offset from it, the verge's sink or the slice's; a quad that would lose its
    winding or convexity, or (`guard`: the tarmac, whose fill quads' corners 0-1 may run along the road) whose cut takes anything not
    under a wall, or with both ends of an edge inside, is kept as
    it was."""
    boxes = _bboxes(walls)
    bins: dict[tuple[int, int], list[int]] = {}
    for i, b in enumerate(boxes):
        for bx in range(int(b[0] // 16), int(b[1] // 16) + 1):
            for bz in range(int(b[2] // 16), int(b[3] // 16) + 1):
                bins.setdefault((bx, bz), []).append(i)
    def inside(x, z):
        return any(boxes[j][0] <= x <= boxes[j][1] and boxes[j][2] <= z <= boxes[j][3] and _point_in_xz(walls[j].corners, x, z)
                   for j in bins.get((int(x // 16), int(z // 16)), ()))
    def taken_under_walls(q, nq, step=0.25):
        """Every sample the cut takes from q (inside q, not inside nq) lies under a wall (Alpine 339.5: a fill quad's
        corners 0-1 ran along the road and its cut opened a hole from the centreline out)."""
        xs = [p[0] for p in q.corners]; zs = [p[2] for p in q.corners]
        x = min(xs)
        while x <= max(xs):
            z = min(zs)
            while z <= max(zs):
                if _point_in_xz(q.corners, x, z) and not _point_in_xz(nq.corners, x, z) \
                        and not any(inside(x + dx, z + dz) for dx in (-CLIP_SLIVER, 0.0, CLIP_SLIVER) for dz in (-CLIP_SLIVER, 0.0, CLIP_SLIVER)):
                    return False                         # (a sliver along the wall's edge: within CLIP_SLIVER of it)
                z += step
            x += step
        return True
    def cut_pair(q, pair):
        c = list(q.corners)
        for a, b in pair:
            ia, ib = inside(c[a][0], c[a][2]), inside(c[b][0], c[b][2])
            if ia == ib:
                continue
            o, i = (c[b], c[a]) if ia else (c[a], c[b])
            lo, hi = 0.0, 1.0                                    # o + t (i - o): outside at lo, inside at hi
            for _ in range(40):
                t = (lo + hi) / 2
                if inside(o[0] + t * (i[0] - o[0]), o[2] + t * (i[2] - o[2])):
                    hi = t
                else:
                    lo = t
            L = math.hypot(i[0] - o[0], i[2] - o[2]) or 1.0
            hi = min(1.0, hi + CLIP_OVERLAP / L)                 # Phase 22c: CLIP_OVERLAP into the wall
            cut = tuple(o[k] + hi * (i[k] - o[k]) for k in range(3))
            if plane:                                             # Phase 22k: the run-off is capped below the drawn ground
                cut = (cut[0], tgp_height(q.corners, cut[0], cut[2]), cut[2])   # (VERGE_MAX_SLOPE): the moved corner stays on
            elif height is not None:                                  # the quad's own plane, not back on the ground
                h0, h1 = height(i[0], i[2]), height(cut[0], cut[2]); off = i[1] - h0
                y = _away_from_zero(h1, abs(off)) if (off >= 0) == (h0 >= 0) else h1 + off   # a sink away from zero stays so
                if abs(off) > CLIP_DECK_OFFSET:                   # Phase 22g: the moved corner's height function read
                    y = tgp_height(q.corners, cut[0], cut[2])     # another deck (Metropolis's pit mouth: off 12.6, the
                                                                  # corner at +2.1 over a road at -10.5): the quad's own plane
                L = math.hypot(cut[0] - o[0], cut[2] - o[2])         # the ground's height there, a bank's too (Phase 22c:
                one = L < 1e-9 or _continuous(height, o[0], o[2], (cut[0] - o[0]) / L, (cut[2] - o[2]) / L, L)   # the
                cut = (cut[0], y if one else o[1], cut[2])           # Oval's steepest bank lay flat, the car under the road);
                                                                     # flat with the kept end where it jumps (another deck)
            c[a if ia else b] = cut
        if c == list(q.corners):
            return None
        nq = Quad16(tuple(c), _mean(c), q.attr)
        if _convex(c) and (xz_area(nq) < 0) == (xz_area(q) < 0) and abs(xz_area(nq)) > MIN_AREA_QUAD and taken_under_walls(q, nq):
            return nq
        return None
    out = []
    pairs = [((0, 1), (3, 2)), ((0, 1),), ((3, 2),)]          # both lateral edges, else one (a wall run nearer at one end:
    if guard:                                                # cut there, the run-off at the other end opens a hole)
        pairs += [((1, 2), (0, 3)), ((1, 2),), ((0, 3),)]    # (the tarmac: either pair may run across)
    for q in grass:
        nq = None
        for pair in pairs:
            nq = cut_pair(q, pair)
            if nq is not None:
                break
        out.append(q if nq is None else nq)
    return out


BANK_SPLIT_TOL = 0.75          # a road quad whose two triangles lie more than this under the height function is split across
BANK_SPLIT_DEPTH = 2           # ... at most this deep (a quad becomes at most 4)
BANK_SPLIT_DECK = 6.0          # samples further off than this are another deck, not a bank


def split_bank_quads(quads: list[Quad16], height: HeightFn, tol: float = BANK_SPLIT_TOL, depth: int = BANK_SPLIT_DEPTH) -> list[Quad16]:
    """Phase 22c (Pascal p22play26, Surfers Oval's first curve tiles: "went under the road"): a wide slice over a bank's
    knee (flat, then 45 degrees) is two flat triangles up to a unit under it. A quad whose TGP height (`tgp_height`) misses
    the height function by more than `tol` is split in two across one pair of opposite edges, at the fraction that fits
    best, and the parts again, at most `depth` deep; new corners take the height function's height. A quad no split
    improves stays."""
    def err(c):
        worst = 0.0
        for u in (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95):
            for v in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0):        # (on the edges too: Oval 55's quad was lowest on one)
                for uu, vv in ((u, v), (v, u)):                   # (fine along both pairs of edges)
                    x = (1 - uu) * (1 - vv) * c[0][0] + uu * (1 - vv) * c[1][0] + uu * vv * c[2][0] + (1 - uu) * vv * c[3][0]
                    z = (1 - uu) * (1 - vv) * c[0][2] + uu * (1 - vv) * c[1][2] + uu * vv * c[2][2] + (1 - uu) * vv * c[3][2]
                    d = height(x, z) - tgp_height(c, x, z)        # under the road (a car goes through it): over it a car
                    if d < BANK_SPLIT_DECK:                       # only rides a little high
                        worst = max(worst, d)
        return worst
    def at(a, b, t):
        x, z = a[0] + t * (b[0] - a[0]), a[2] + t * (b[2] - a[2])
        y = height(x, z)
        if abs(y - (a[1] + t * (b[1] - a[1]))) > BANK_SPLIT_DECK:
            y = a[1] + t * (b[1] - a[1])
        return (x, y, z)
    def bil(c, u, v):
        return ((1 - u) * (1 - v) * c[0][0] + u * (1 - v) * c[1][0] + u * v * c[2][0] + (1 - u) * v * c[3][0],
                (1 - u) * (1 - v) * c[0][2] + u * (1 - v) * c[1][2] + u * v * c[2][2] + (1 - u) * v * c[3][2])
    def dev(c, x, z):
        d = height(x, z) - tgp_height(c, x, z)
        return d if d < BANK_SPLIT_DECK else 0.0
    def split(q, d):
        c = list(q.corners); e0 = err(c)
        if e0 <= tol or d == 0:
            return [q]
        best = None                                               # cut where the quad misses the most (a knee), across
        for pair in (0, 1):                                       # either pair of opposite edges
            for i in range(3, 38):
                t = i / 40
                dv = max(dev(c, *(bil(c, t, w) if pair == 0 else bil(c, w, t))) for w in (0.0, 0.25, 0.5, 0.75, 1.0))
                if best is None or dv > best[0]:
                    best = (dv, pair, t)
        _, pair, t = best
        if pair == 0:
            P, R = at(c[0], c[1], t), at(c[3], c[2], t); A, B = [c[0], P, R, c[3]], [P, c[1], c[2], R]
        else:
            P, R = at(c[1], c[2], t), at(c[0], c[3], t); A, B = [c[0], c[1], P, R], [R, P, c[2], c[3]]
        if not (_convex(A) and _convex(B)) or min(abs(xz_area(Quad16(tuple(X), _mean(X), 0))) for X in (A, B)) < MIN_AREA_QUAD:
            return [q]
        parts = split(Quad16(tuple(A), _mean(A), q.attr), d - 1) + split(Quad16(tuple(B), _mean(B), q.attr), d - 1)
        return parts if max(err(list(x.corners)) for x in parts) < e0 - 0.1 else [q]
    out = []
    for q in quads:
        out.extend(split(q, depth))
    return out


def _meet_walls(widths, walls: list[Quad16], pts, edges, step: float = VERGE_SCAN_STEP):
    """Phase 22a: per point and side, the grass width that puts the grass's outer line WALL_OVERLAP inside the first wall
    sample outward from the road's measured edge (widened or cut, never past VERGE_GRASS); with no wall within reach, the
    width as given. Returns (widths, the (point, side) pairs with no wall within reach)."""
    dirs = _smooth_dirs(pts); boxes = _bboxes(walls); missing: set[tuple[int, int]] = set()
    bins: dict[tuple[int, int], list[int]] = {}
    for i, b in enumerate(boxes):
        for bx in range(int(b[0] // 16), int(b[1] // 16) + 1):
            for bz in range(int(b[2] // 16), int(b[3] // 16) + 1):
                bins.setdefault((bx, bz), []).append(i)
    out = []
    for k, ((x, z), (dx, dz)) in enumerate(zip(pts, dirs)):
        row = []
        for side, sign in ((0, -1.0), (1, 1.0)):
            e, w = edges[k][side], widths[k][side]
            wl = None
            for i in range(int((VERGE_GRASS + WALL_WIDTH) / step) + 1):
                lat = e + i * step
                px, pz = x + sign * lat * dz, z - sign * lat * dx
                if any(boxes[j][0] <= px <= boxes[j][1] and boxes[j][2] <= pz <= boxes[j][3] and _point_in_xz(walls[j].corners, px, pz)
                       for j in bins.get((int(px // 16), int(pz // 16)), ())):
                    wl = lat
                    break
            if wl is None:                                 # no wall within reach: the width as it was
                row.append(w)
            else:                                          # Phase 22a: the grass ends WALL_OVERLAP (or up to a unit more: whole
                row.append(min(VERGE_GRASS, max(VERGE_SCAN_STEP, math.ceil(wl + WALL_OVERLAP - e + VERGE_SCAN_STEP))))
                                                           # units, fewer steps) inside the wall, never past it: on grass under
                                                           # the wall a car keeps the grass (the TGP's nearest-height pick) and
                                                           # crosses (Pascal's Diablo replay, points 98-104)
            if wl is None:
                missing.add((k, side))
        out.append(tuple(row))
    return out, missing


BARRIER_RETRIES = 0            # rounds of the hole scan (`_gap_sides`) after the barrier-narrowed grass


OPEN_SEAM = 3.0                # a gap this narrow between the grass and its wall is a seam, not a run-off ending in nothing


def _open_sides(quads: list[Quad16], walls: set[int], grass: set[int], pts, step: float = VERGE_SCAN_STEP) -> set[tuple[int, int]]:
    """Phase 22a: the (point, side) pairs where a scan outward from the point (chord directions, to 80 units) leaves the
    grass for a sample under no quad before any wall sample: a car would run off the run-off."""
    boxes = _bboxes(quads)
    bins: dict[tuple[int, int], list[int]] = {}
    for i, b in enumerate(boxes):
        for bx in range(int(b[0] // 16), int(b[1] // 16) + 1):
            for bz in range(int(b[2] // 16), int(b[3] // 16) + 1):
                bins.setdefault((bx, bz), []).append(i)
    def under(x, z):
        return [i for i in bins.get((int(x // 16), int(z // 16)), ()) if boxes[i][0] <= x <= boxes[i][1]
                and boxes[i][2] <= z <= boxes[i][3] and _point_in_xz(quads[i].corners, x, z)]
    n = len(pts); out = set()
    for k in range(n):
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % n]
        d = math.hypot(bx - ax, bz - az) or 1.0
        rx, rz = (bz - az) / d, -(bx - ax) / d
        for side, sign in ((0, -1.0), (1, 1.0)):
            on_grass, lat = False, 0.0
            while lat <= 80.0:
                x, z = pts[k][0] + sign * lat * rx, pts[k][1] + sign * lat * rz
                ids = [i for i in bins.get((int(x // 16), int(z // 16)), ()) if boxes[i][0] <= x <= boxes[i][1]
                       and boxes[i][2] <= z <= boxes[i][3] and _point_in_xz(quads[i].corners, x, z)]
                if any(i in walls for i in ids):
                    break
                if not ids:
                    if on_grass and not any(any(j in walls for j in under(pts[k][0] + sign * (lat + t) * rx, pts[k][1] + sign * (lat + t) * rz))
                                            for t in np.arange(step, OPEN_SEAM + step, step)):
                        out.add((k, side))                    # (a seam under OPEN_SEAM with the wall after it is no open end)
                    break
                on_grass = all(i in grass for i in ids)
                lat += step
    return out


def _gap_sides(quads: list[Quad16], walls: set[int], pts, step: float = VERGE_SCAN_STEP) -> set[tuple[int, int]]:
    """Phase 22a: the (point, side) pairs where, from the point or the half-point after it (chord directions, as the hole
    gate), a sample under no quad lies between two quads before the first wall sample (or 80 units)."""
    boxes = _bboxes(quads)
    bins: dict[tuple[int, int], list[int]] = {}
    for i, b in enumerate(boxes):
        for bx in range(int(b[0] // 16), int(b[1] // 16) + 1):
            for bz in range(int(b[2] // 16), int(b[3] // 16) + 1):
                bins.setdefault((bx, bz), []).append(i)
    def under(x, z):
        return [i for i in bins.get((int(x // 16), int(z // 16)), ()) if boxes[i][0] <= x <= boxes[i][1] and boxes[i][2] <= z <= boxes[i][3]
                and _point_in_xz(quads[i].corners, x, z)]
    n = len(pts); out = set()
    for k2 in range(2 * n):
        k = k2 // 2
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % n]
        x, z = ((pts[k][0] + pts[(k + 1) % n][0]) / 2, (pts[k][1] + pts[(k + 1) % n][1]) / 2) if k2 % 2 else pts[k]
        d = math.hypot(bx - ax, bz - az) or 1.0
        rx, rz = (bz - az) / d, -(bx - ax) / d
        for side, sign in ((0, -1.0), (1, 1.0)):
            gap, lat, seen = False, 0.0, False
            while lat <= 80.0:
                ids = under(x + sign * lat * rx, z + sign * lat * rz)
                if ids:
                    if gap and seen:
                        out.add((k, side)); out.add(((k + k2 % 2) % n, side))
                        break
                    seen = True
                    if any(i in walls for i in ids):
                        break
                elif seen:
                    gap = True
                lat += step
    return out


def wall_insets(widths: list[tuple[float, float]], reach: int = MERGE_MAX_RUN) -> list[tuple[float, float]]:
    """The wall strip's inset per point: the narrowest grass width within `reach` points. A grass run (at most
    MERGE_MAX_RUN points, broken at any width change) takes its narrowest point's width; wall runs break only beyond
    WALL_EDGE_TOL, so a wall at a point's own width could start beyond grass cut short by a neighbour's water (Surfers
    Road 151-152). Eroded over the grass's longest run, any wall run's inset is within every overlapping grass run's."""
    n = len(widths)
    return [tuple(min(widths[(k + j) % n][s] for j in range(-reach, reach + 1)) for s in (0, 1)) for k in range(n)]


def road_verges(tarmac: list[Quad16], pts, height: HeightFn, width: float | list = MARGIN, inset: float | list = 0.0,
                follow: bool = False, fine: list | None = None, caps: list | None = None,
                ground: Callable[[float, float], list[float]] | None = None) -> list[Quad16]:
    """Verge quads built from the road's measured edge (`road_edges`), `width` units wide, one per centreline step on
    each side (a run of steps with the same edge and little turn makes one quad, as the merged straights do). A step's
    inner edge lies GRASS_OVERLAP inside the last tarmac sample of the run's narrowest edge (VERGE_SCAN_STEP inside the
    measured edge), so the grass meets the tarmac with no seam and overlaps only its outer band (Phase 17). The originals' quads never overlap (formats, TGP §5); a slice's own
    verge, built off the quad's side, lay across the road on triangle slices and the TGP kept any car that had touched
    it there (Phase 11). Corner heights: the road's at the inner edge, straight across, VERGE_SINK away from zero. With
    `ground` (the drawn ground's levels under a point, `mesh_heights`; Phase 22o) the corners take the drawn height nearest
    the road profile's instead of the profile, which beside a banked road continued the tilt sideways while the drawn
    infield bank climbed (the Oval: a car on the grass 2-9 units under the drawn mountain); VERGE_MAX_SLOPE still caps it."""
    def gh(x: float, z: float, ref: float | None = None, tol: float = GROUND_DECK, fallback: float | None = None) -> float:
        """The drawn ground's height at (x, z): the level nearest `ref` (the profile's own height without one) within `tol`
        of it — another deck's level is left alone — else `fallback` (the profile's height without one)."""
        h = height(x, z) if fallback is None else fallback
        if ground is None:
            return h
        levels = ground(x, z)
        if not levels:
            return h
        r = height(x, z) if ref is None else ref
        g = min(levels, key=lambda v: abs(v - r))
        return g if abs(g - r) <= tol else h

    boxes = _bboxes(tarmac); tarmac_cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for ti, (bx0, bx1, bz0, bz1) in enumerate(boxes):
        for cx in range(int(bx0 // MESH_BUCKET), int(bx1 // MESH_BUCKET) + 1):
            for cz in range(int(bz0 // MESH_BUCKET), int(bz1 // MESH_BUCKET) + 1):
                tarmac_cells[(cx, cz)].append(ti)

    def tarmac_h(x: float, z: float) -> float | None:
        """Phase 22o review: the built tarmac's own height under (x, z) — the surface a car leaves the road from; the
        quads follow the drawn surface across their width (22a) where the profile, one plane per point, under-reads a
        steep bank (the Oval's first curve: 7.1 at the edge, the profile 5.7, the wall strip a unit below the road).
        Of several (another deck's road crossing) the one nearest the profile, within TARMAC_REF_MAX; None off the tarmac."""
        h = height(x, z)
        hs = [tgp_height(tarmac[ti].corners, x, z) for ti in tarmac_cells.get((int(x // MESH_BUCKET), int(z // MESH_BUCKET)), ())
              if boxes[ti][0] <= x <= boxes[ti][1] and boxes[ti][2] <= z <= boxes[ti][3] and _point_in_xz(tarmac[ti].corners, x, z)]
        if not hs:
            return None
        th = min(hs, key=lambda v: abs(v - h))
        return th if abs(th - h) <= TARMAC_REF_MAX else None

    def ground_outer(ix, iz, ox, oz, y):
        """The drawn ground's height at an outer corner (ox, oz) seen from the inner one at height y: the ground must continue
        the inner corner over the first GROUND_PROBE units (within GROUND_DECK; a deck 4 units up does not), the level
        at the outer corner is the level nearest the inner corner's height `y` (unsunk), and the drawn ground between lies
        at most GROUND_AIR under the quad's plane as the cap will leave it (a bank, a kerb lip, a bank steeper than the cap
        — the plane under the drawn ground is the cap's doing; not a flat run-off to a hill foot, which the plane would
        cross in the air); a hole in the mesh is skipped, and a span with nothing drawn holds the plane within GROUND_AIR
        over the profile; else the profile's height there."""
        L = math.hypot(ox - ix, oz - iz)
        h = height(ox, oz)
        if ground is None or L < 1e-9:
            return h
        ux, uz = (ox - ix) / L, (oz - iz) / L
        levels = ground(ix + ux * min(GROUND_PROBE, L), iz + uz * min(GROUND_PROBE, L))
        if levels and min(abs(v - y) for v in levels) > GROUND_DECK:
            return h                                                # the drawn ground jumps at the edge: another deck
        g = gh(ox, oz, y, GROUND_SLOPE_MAX * L + GROUND_DECK)       # the level nearest the inner corner that a bank (not a
        if g == h:                                                  # barrier's face, BARRIER_STEEP) could reach: the span check
            return h                                                # and the cap decide, a bank steeper than the cap is climbed
                                                                    # at the cap (Oval 63 L: 0.7 a unit)
        steps = max(1, int(L // GROUND_PROBE))
        gc = y + max(-VERGE_MAX_SLOPE * L, min(VERGE_MAX_SLOPE * L, g - y))   # the quad's plane as the cap will leave it
        drawn_any = False; over_profile = 0.0
        last_v, last_d = y, 0.0                                     # the last drawn ground met and its distance out
        for i in range(1, steps):                                   # the span between the corners, under that plane
            f = i / steps
            line = y + (gc - y) * f
            sx, sz = ix + ux * L * f, iz + uz * L * f
            between = ground(sx, sz)
            if not between:
                over_profile = max(over_profile, line - height(sx, sz))
                continue
            drawn_any = True
            v = max(between, key=lambda v: -abs(v - line))
            if line - v > GROUND_AIR:
                return h                                            # the plane in the air over the drawn ground: as before 22o
            if v - last_v > GROUND_SLOPE_MAX * (L * f - last_d) + GROUND_DECK:
                return h                                            # the ground above what a bank could reach from the last
            last_v, last_d = v, L * f                               # ground met (a stand's roof over a hole in the mesh, Oval
        if g - last_v > GROUND_SLOPE_MAX * (L - last_d) + GROUND_DECK:   # 897,-540: the grass climbed towards it)
            return h
        if not drawn_any and over_profile > GROUND_AIR:             # (under the plane, the cap's doing beside a steep bank, is
            return h                                                # allowed: the Oval's kerb lip, its first curve's 0.7 a unit)
        return g

    edges = road_edges(tarmac, pts, height); dirs = _smooth_dirs(pts); n = len(pts)
    widths = width if isinstance(width, list) else [(width, width)] * n          # Phase 19: per point and side (shore widths)
    insets = inset if isinstance(inset, list) else [(inset, inset)] * n
    walls = any(i > 0 for pair in insets for i in pair)
    if walls and any(i < VERGE_GRASS for pair in insets for i in pair):   # Phase 19 review: the edge halfway between points
        mid_pts = [((pts[k][0] + pts[(k + 1) % n][0]) / 2, (pts[k][1] + pts[(k + 1) % n][1]) / 2) for k in range(n)]
        mid_dirs = [((a[0] + b[0]) / (math.hypot(a[0] + b[0], a[1] + b[1]) or 1.0), (a[1] + b[1]) / (math.hypot(a[0] + b[0], a[1] + b[1]) or 1.0))
                    for a, b in ((dirs[k], dirs[(k + 1) % n]) for k in range(n))]
        mid_edges = road_edges(tarmac, mid_pts, height)       # (side-area tarmac pokes out between points: a shoreline wall's
    else:                                                     # chord cut into it, Pacific Coast 308-317, 383-389)
        mid_pts = mid_dirs = mid_edges = None
    if not walls:                                                # Phase 17: the grass takes the nearer of the edges measured
        tb = _bboxes(tarmac); chord = _dirs(pts)                  # along the smoothed and the chord directions (on a bend the
        def nearer(e, ce):                                        # smoothed scan reached tarmac further on past a hole:
            return min(e, ce) if ce >= GRASS_FLOOR else e         # Alpine 303, a unit bare at 9); a chord edge inside the
        edges = [tuple(nearer(e, _edge_scan(tarmac, tb, pts[k][0], pts[k][1], chord[k][1], -chord[k][0], sg, height))  # AI
                       for e, sg in zip(edges[k], (-1.0, 1.0))) for k in range(n)]   # lines' reach is a tight bend's artifact
    out = []
    chain: list[tuple[float, int, int, int]] = []             # Phase 22a: (sign, p, q, index in out) of each wall step

    for side, sign in ((0, -1.0), (1, 1.0)):
        p = 0
        cap: dict[int, int] = {}                                  # Phase 22a: a barrier run split at its start point
        while p < n:
            run = 1
            max_run, tol, turn = (WALL_MAX_RUN, WALL_EDGE_TOL, WALL_MAX_TURN) if walls else (MERGE_MAX_RUN, 0.0, MERGE_MAX_TURN)
            shore = walls and insets[p][side] < VERGE_GRASS
            if shore:                                             # Phase 19: a shoreline wall lies a few units off the road: its
                tol, turn = SHORE_EDGE_TOL, MERGE_MAX_TURN        # run follows the edge (review: off the tarmac), halfway between
                if fine is not None and not fine[p][side]:        # Phase 22a: a drawn barrier's wall (not the water's) in longer
                    tol, turn = BARRIER_EDGE_TOL, BARRIER_MAX_TURN   # runs: the quad pool (all close walls at the shore's
                                                                  # tolerances: +1 300 quads, Surfers Road's block short by 15 691 words)
                                                                  # points too, and bends finely (a chord cut inside a gentle bend
            mid_ok = lambda k: not shore or mid_edges[k % n][side] - edges[p][side] <= tol   # of the Oval, 128-133)
            max_run = min(max_run, cap.get(p, max_run))
            own = lambda k: edges[k % n][side] + insets[k % n][side]       # Phase 22k: the wall's own lateral at a point
            jump = lambda k: walls and fine is not None and not fine[k % n][side] and abs(own(k + 1) - own(k)) > JOIN_SLANT_MAX
            def chord_ok(a, b):                                       # Phase 22k: every point between a and b lies within
                if not (walls and fine is not None and not fine[a % n][side]):   # BARRIER_CHORD_TOL of the line from a's
                    return True                                       # own lateral to b's (the run's inner line)
                line = lambda k: own(a) + (own(b) - own(a)) * (k - a) / (b - a)
                return all(abs(line(k) - own(k)) <= BARRIER_CHORD_TOL
                           and line(k) - VERGE_SCAN_STEP - WALL_OVERLAP >= wall_min(k % n, side) - 1e-6 for k in range(a + 1, b))
            if jump(p):                                           # a run starting with a jump segment keeps it alone
                max_run = 1
            while run < max_run and p + run < n and mid_ok(p) and mid_ok(p + run) and abs(edges[p + run][side] - edges[p][side]) <= tol \
                    and abs(widths[p + run][side] - widths[p][side]) <= (tol if walls else GRASS_WIDTH_TOL) and abs(insets[p + run][side] - insets[p][side]) <= tol \
                    and math.degrees(math.acos(max(-1.0, min(1.0, dirs[p][0] * dirs[p + run][0] + dirs[p][1] * dirs[p + run][1])))) <= turn \
                    and not (walls and fine is not None and not fine[p][side]
                             and abs(edges[p + run][side] + insets[p + run][side] - edges[p][side] - insets[p][side]) > BARRIER_LAT_TOL) \
                    and not (run >= 1 and jump(p + run)) \
                    and chord_ok(p, p + run + 1):                     # Phase 22k: the segment before a jump stays its own run
                run += 1                                          # (Phase 22a: a barrier run breaks where its points' own
                                                                  # lateral moves: Diablo 91-97, the rock curving away)
            if shore and run > 1 and edges[(p + run) % n][side] > max(edges[(p + j) % n][side] for j in range(run)):
                run -= 1                                          # Phase 19 review: a wider end point gets its own step (each
            q = (p + run) % n                                     # end then clears its own edge, not the run's widest)
            def at(k, lat):                                       # k: a point index, or ((x, z), (dx, dz)) between two
                (x0, z0), (dx, dz) = (pts[k], dirs[k]) if isinstance(k, int) else k
                rx, rz = dz, -dx
                return (x0 + sign * lat * rx, z0 + sign * lat * rz)
            run_edges = [edges[(p + j) % n][side] for j in range(run + 1)]     # the run and its shared end point
            lo, hi = min(run_edges), max(run_edges)
            width = (min if walls else max)(widths[(p + j) % n][side] for j in range(run + 1))   # Phase 22a: a grass run spans
            if caps is not None and not walls:                   # GRASS_WIDTH_TOL and takes its widest, the shared end point's
                width = min(width, min(caps[(p + j) % n][side] for j in range(run + 1)))   # too (Pascal's tested feel), never past
                                                                  # the water (`caps`: it took 30 at an 11.5 shore, 19 units on)
            inset = min(insets[(p + j) % n][side] for j in range(run + 1))
            if walls:
                # the wall strip (Phase 16): from the run's narrowest edge + inset (overlapping the grass, which ends at the local
                # edge + inset) to its widest edge + inset + width; both neighbours of a seam contain its shared point's interval,
                # so they overlap there
                back = SHORE_WALL_BACK if (fine is None or fine[p][side]) else WALL_OVERLAP   # Phase 22a: a shoreline wall
                base = lo - VERGE_SCAN_STEP + inset - back            # keeps Phase 19's place; never inside WALL_MIN_LATERAL
                if fine is not None and not fine[p][side]:            # Phase 22a: a drawn barrier's run at its nearest point's
                    med = lambda k: sorted(edges[(k + d) % n][side] for d in (-1, 0, 1))[1]   # Phase 22c: one point's edge
                    base = min(med(p + j) + insets[(p + j) % n][side] for j in range(run + 1)) - VERGE_SCAN_STEP - back
                    # glitch is no edge (Surfers Oval 56: 17.0 between 22.5-23.5, the 45-degree bank's slice off the height
                    # function; the wall stood on the bank's top, Pascal: "it doesnt register the inclination")
                    # own edge + width (the run's narrowest edge + narrowest width came from different points: Diablo 28-38,
                    # the wall 4-5 units before the face)
                if fine is not None and not fine[p][side]:            # Phase 22k: a drawn barrier's wall follows the face from
                    own_lat = lambda k: med(k) + insets[k % n][side] - VERGE_SCAN_STEP - back   # point to point: each end at
                    ep = max(own_lat(p), wall_min(p % n, side))       # its own lateral (the face less the setback), so the strip
                    eq = max(own_lat(q), wall_min(q, side))           # slants with a receding rock and consecutive runs meet at
                    dp = dq = 0.0                                     # the shared point (Pascal, rec98 Diablo 134-148 R: the wall
                                                                      # at 17 along a rock drawn 18-21.5 out — a run was a straight
                                                                      # strip at its nearest point, and the join slanted the next
                                                                      # one back down to it)
                elif shore:                                           # nor, at a shore, inside the tarmac (review: walls over their own
                    own = max(run_edges[:-1])                         # tarmac kept a car on the wall's surface): a run clears its own
                    ep = max(base, own, wall_min(p % n, side))        # points' widest edge, a single step each end's edge
                    eq = max(base, own if run > 1 else run_edges[-1], wall_min(q, side))
                    dp = max(0.0, base + (hi - lo) + back - ep)       # the outer line stays at the widest edge + inset + width
                    dq = max(0.0, base + (hi - lo) + back - eq)
                else:
                    ep, eq = max(base, wall_min(p % n, side)), max(base, wall_min(q, side))
                    dp = max(0.0, base + (hi - lo) + back - ep)       # the outer line stays at the widest edge + inset + width
                    dq = max(0.0, base + (hi - lo) + back - eq)
            else:
                # the grass (Phase 17): the inner line lies GRASS_OVERLAP inside the last tarmac sample of the run's NARROWEST
                # edge (it was the widest, which left a triangle of no quad wherever the road narrowed or widened inside the run:
                # 146-405 runs per course), never inside GRASS_FLOOR unless the whole run's tarmac ends there (the AI lines stay
                # off the grass: one narrow point drew a Diablo run's grass over them); the outer line stays at the widest edge + width. Where the road is wider than the inner line the
                # grass lies under the tarmac's outer band: the TGP keeps the tarmac there for a car on the road (its height is
                # nearest; VERGE_SINK sets the grass apart)
                floor = min(grass_floor(p % n, side), grass_floor(q, side))   # Phase 22c review: narrowed with the lines
                ep = eq = max(lo - VERGE_SCAN_STEP - GRASS_OVERLAP, min(hi - VERGE_SCAN_STEP, floor))
                dp = dq = hi - VERGE_SCAN_STEP - ep
            def step_quad(ep, eq, dp, dq, w, A=None, B=None):
                """The step's quad from end A (default p) to end B (default q), inner laterals ep, eq, outer ones ep + w + dp,
                eq + w + dq."""
                A = p if A is None else A; B = q if B is None else B
                (ix0, iz0), (ix1, iz1) = at(A, ep), at(B, eq)
                clamp = lambda v: max(-MAP_LIMIT, min(MAP_LIMIT, v))          # a wide verge must stay inside the collision map
                # consecutive steps share their end lines (each end's own lateral), so no wedge opens between them; inside a
                # tight bend the two laterals cross within the width and the quad would be a bow tie: the outer corners are
                # swapped, which gives the four points' convex hull — it covers both lobes (a car cutting a hairpin found
                # nothing beyond the crossing when the step was clamped to a triangle) and overlaps the neighbouring steps,
                # which is harmless between verges. Phase 14 (80-unit verges): a step whose hull crosses, or which lies over
                # another leg's road (Metropolis's decks, a hairpin's straights), is built at MARGIN instead, and dropped only
                # if the narrow step still lies over a road
                y0, y1 = _away_from_zero(gh(ix0, iz0), VERGE_SINK), _away_from_zero(gh(ix1, iz1), VERGE_SINK)
                dx, dz = ix1 - ix0, iz1 - iz0

                def ref_at(k, lat_inner):
                    """Phase 22k: the ground's height at end k's measured edge and that edge's lateral. Phase 22o review: the
                    built tarmac's own height there; between two points (a barrier wall's run end, no measured edge: the
                    reference was None and the wall's inner corner took the profile, a unit under the Oval's banked first
                    curve) the tarmac is looked for inward from the corner, REF_SCAN units at most."""
                    e = edges[k % n][side] if isinstance(k, int) else lat_inner   # (the measured edge lies VERGE_SCAN_STEP past
                    for j in range(int(REF_SCAN // VERGE_SCAN_STEP) + 1):          # the last tarmac sample: the scan starts there)
                        lat = e - j * VERGE_SCAN_STEP
                        if lat <= 0:
                            break
                        th = tarmac_h(*at(k, lat))
                        if th is not None:                        # the cap's anchor: the grass's inner line (GRASS_OVERLAP inside
                            return th, lat - GRASS_OVERLAP        # the last tarmac sample), the same for the grass and the wall
                                                                  # beyond it, so the wall's inner line continues the grass
                    if isinstance(k, int):
                        return gh(*at(k, e), None, 1.5), e
                    return None, 0.0

                def capped(g, r, lat, e):
                    """The ground height g at lateral `lat`, held within VERGE_MAX_SLOPE a unit of the edge's height r."""
                    if r is None or lat <= e:
                        return g
                    d = (lat - e) * VERGE_MAX_SLOPE
                    return r + max(-d, min(d, g - r))
                (r0, e0), (r1, e1) = ref_at(A, ep), ref_at(B, eq)

                def inner_h(ix, iz, r, lat, e):
                    """The inner corner's ground: the built tarmac under it, else the drawn level nearest the edge's height
                    within the cap's reach of it from the edge (plus GROUND_DECK: the Oval's first curve, the bank 2.35 up
                    at the wall's inner line 1.5 past the edge), else the profile's (a wall 10 units past the edge continues
                    the grass's climb: not the edge's height, a step down into the wall)."""
                    th = tarmac_h(ix, iz)
                    if th is not None:
                        return th
                    reach = VERGE_MAX_SLOPE * max(0.0, lat - e) + GROUND_DECK if r is not None and e is not None else 1.5
                    return gh(ix, iz, r, reach)
                g0, g1 = capped(inner_h(ix0, iz0, r0, ep, e0), r0, ep, e0), capped(inner_h(ix1, iz1, r1, eq, e1), r1, eq, e1)   # the inner corners: a wall's
                y0, y1 = _away_from_zero(g0, VERGE_SINK), _away_from_zero(g1, VERGE_SINK)           # continue the grass from the edge

                def build(w):
                    """The step's quad at width w and whether its laterals crossed; None when it is twisted or lies over a road."""
                    (ox0, oz0), (ox1, oz1) = at(A, ep + w + dp), at(B, eq + w + dq)
                    ox0, oz0, ox1, oz1 = clamp(ox0), clamp(oz0), clamp(ox1), clamp(oz1)
                    ux, uz, vx, vz = ox0 - ix0, oz0 - iz0, ox1 - ix1, oz1 - iz1
                    den = ux * vz - uz * vx
                    crossing = False
                    if abs(den) > 1e-9:
                        wx, wz = ix1 - ix0, iz1 - iz0
                        s_, t_ = (wx * vz - wz * vx) / den, (wx * uz - wz * ux) / den
                        crossing = 0.0 < s_ < 1.0 and 0.0 < t_ < 1.0
                    if crossing:
                        (ox0, oz0), (ox1, oz1) = (ox1, oz1), (ox0, oz0)
                    def outer_y(ix, iz, ox, oz, y, r, lat, e):
                        """Phase 22a: an outer corner at its own height (the run-off follows the drawn ground: flat at the
                        edge's height it lay under Diablo's canyon side), unless the ground between the corners jumps (the
                        outer corner over Metropolis's other deck: the grass was a ramp between the decks): flat, as before.
                        Phase 22k: within VERGE_MAX_SLOPE a unit of the edge's height (the game's wall-step check)."""
                        L = math.hypot(ox - ix, oz - iz)
                        if not follow or L < 1e-9 or not _continuous(height, ix, iz, (ox - ix) / L, (oz - iz) / L, L):
                            return y
                        return _away_from_zero(capped(ground_outer(ix, iz, ox, oz, y if r is None else r), r, lat, e), VERGE_SINK)
                    yo0 = outer_y(ix0, iz0, ox0, oz0, y0, g0, ep + w + dp, ep)   # the outer corners: from their own inner corner
                    yo1 = outer_y(ix1, iz1, ox1, oz1, y1, g1, eq + w + dq, eq)   # (the slope the game's wheels meet)
                    sy1, syo1, syo0, sy0 = _wall_step([y1, yo1, yo0, y0], WALL_STEP) if walls else (y1, yo1, yo0, y0)   # Phase 22a: the wall a step
                    inner_f, outer_f, outer_b, inner_b = (ix1, sy1, iz1), (ox1, syo1, oz1), (ox0, syo0, oz0), (ix0, sy0, iz0)
                    # arcade order FL, FR, BR, BL: the road is on the verge's right on the left side, on its left on the right
                    c = [outer_f, inner_f, inner_b, outer_b] if sign < 0 else [inner_f, outer_f, outer_b, inner_b]
                    if not _convex(c) and not walls:             # Phase 17: inside a tight bend a short grass step is a dart
                        c = _hull4(c)                             # (one corner reflex) and was skipped, leaving a 9-16 unit
                    vq = Quad16(tuple(c), _mean(c), direction_attr(dx, dz))   # hole (Surfers Road 31, 88, 115): its hull
                    if not (xz_area(vq) < -MIN_AREA_QUAD and _convex(c)) or _covers_road(vq, pts):   # the arcade's (negative)
                        return None, crossing                                                      # winding; a twisted step is skipped
                    return vq, crossing
                return build(w)
            variants = [(ep, eq, dp, dq)]
            if not walls:                                        # the per-end grass rejected (a bogus narrow edge inside a tight
                e_old = hi - VERGE_SCAN_STEP                      # bend puts its inner line on the road): the run's widest edge,
                variants.append((e_old, e_old, 0.0, 0.0))         # as before Phase 17
            vq = None
            for v in variants:
                vq, crossing = step_quad(*v, width)
                if (vq is None or crossing) and width > MARGIN:   # a wide step crossing inside a tight bend or lying over
                    vq, crossing = step_quad(*v, MARGIN)          # another leg's road is tried at the narrow width (Phase 14)
                if vq is not None:
                    break
            if shore and run == 1:                               # Phase 19 review: tarmac poking out halfway along a single
                m = max(base, mid_edges[p][side], min(wall_min(p % n, side), wall_min(q, side)))   # step: the step is split there, its middle end at that edge
                if m > (ep + eq) / 2 + VERGE_SCAN_STEP:
                    M = (mid_pts[p], mid_dirs[p])
                    dm = max(0.0, base + (hi - lo) + back - m)
                    halves = [step_quad(ep, m, dp, dm, width, B=M)[0], step_quad(m, eq, dm, dq, width, A=M)[0]]
                    if all(h is not None for h in halves):
                        out.extend(halves); p += run
                        continue
            barrier = walls and fine is not None and not fine[p][side]
            if barrier and vq is not None and run > 1 and _near_racing_lines(vq, pts):
                cap[p] = run // 2                                 # Phase 22a: a barrier run whose chord cuts inside a bend
                continue                                          # near the AI lines is split, not dropped (Alpine 112-124:
                                                                  # the rock at the road, a 90-unit run's chord at 11)
            if vq is not None:
                chain.append((sign, p % n, q, len(out)))
                out.append(vq)
            p += run
    if walls:
        _join_wall_runs(out, chain, pts, tarmac)
    return out


def _join_wall_runs(out: list[Quad16], chain, pts, tarmac: list[Quad16]) -> None:
    """Phase 22a (Pascal p22play19, Diablo 159: a run 16 units out, the next at 13): consecutive wall steps on a side
    meet at the nearer of their inner corners on the shared point's line, so the wall's inner line has no step. A step's
    end showed a car driving along the grass a 3-unit face; the V60 took the parallel hit as a slide along the step's
    edge (`0xfec2ac`), which put all four wheels on the wall and the car was put back. The farther step's inner line
    slants to the nearer one; a step that would lose its winding or convexity, or come over the road or near a racing
    line (the strip's filters then dropped it whole: Alpine 175-179, the Oval's shore 4-9), keeps its corner."""
    for (sa, pa, qa, ia), (sb, pb, qb, ib) in zip(chain, chain[1:]):
        if sa != sb or qa != pb:
            continue
        fa, bb = (1, 2) if sa < 0 else (0, 3)                     # FL, FR, BR, BL: the inner front of a, the inner back of b
        A, B = out[ia], out[ib]
        ca, cb = A.corners[fa], B.corners[bb]
        if math.hypot(ca[0] - cb[0], ca[2] - cb[2]) < 1e-6:
            continue
        cx, cz = pts[qa]
        near_a = math.hypot(ca[0] - cx, ca[2] - cz) < math.hypot(cb[0] - cx, cb[2] - cz)
        k, Q, c = (ib, B, bb) if near_a else (ia, A, fa)
        new = list(Q.corners); new[c] = ca if near_a else cb
        nq = Quad16(tuple(new), _mean(new), Q.attr)
        if _convex(new) and xz_area(nq) < -MIN_AREA_QUAD and not _covers_road(nq, pts) and not _on_tarmac(nq, tarmac) \
                and (_near_racing_lines(Q, pts) or not _near_racing_lines(nq, pts)):
            out[k] = nq


_LINES: dict = {}


def _racing_line_samples(pts, dense: bool = True) -> np.ndarray:
    """(x, z) of the centreline and the AI lines (`road.AI_OFFSETS`) every unit along the lap (dense: each point's lateral
    direction blended linearly towards the next point's; Phase 19 review: 10-unit samples let a wall corner come within
    0.33 of another leg's +8 line between them, Metropolis), or at the points only. Cached per point list."""
    key = (id(pts), len(pts), pts[0], pts[-1], dense, id(_LANES), id(_SHIFT))
    if key in _LINES:
        return _LINES[key]
    from vrtools.convert.road import AI_OFFSETS
    n = len(pts)
    normals = []
    for k in range(n):
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % n]
        d = math.hypot(bx - ax, bz - az) or 1.0
        normals.append(((bz - az) / d, -(bx - ax) / d))
    out = []
    offs = np.array((0.0,) + tuple(AI_OFFSETS))
    for k in range(n):
        (x0, z0), (x1, z1) = pts[k], pts[(k + 1) % n]
        steps = max(1, int(math.ceil(math.hypot(x1 - x0, z1 - z0)))) if dense else 1
        (u0, v0), (u1, v1) = normals[k], normals[(k + 1) % n]
        for t in np.arange(steps) / steps:
            x, z, u, v = x0 + t * (x1 - x0), z0 + t * (z1 - z0), u0 + t * (u1 - u0), v0 + t * (v1 - v0)
            o = offs
            if _LANES is not None and len(_LANES) == n:              # Phase 22c: the narrowed lines (lane_scales)
                sl = _LANES[k][0] + t * (_LANES[(k + 1) % n][0] - _LANES[k][0])
                sr = _LANES[k][1] + t * (_LANES[(k + 1) % n][1] - _LANES[k][1])
                o = np.where(offs > 0, offs * sr, offs * sl)
            if _SHIFT is not None and len(_SHIFT) == n:              # Phase 22n: the lines' shift onto the tarmac band
                o = o + _SHIFT[k] + t * (_SHIFT[(k + 1) % n] - _SHIFT[k])
            out.append(np.stack([x + o * u, z + o * v], 1))
    arr = np.concatenate(out)
    if len(_LINES) > 4:
        _LINES.clear()
    _LINES[key] = arr
    return arr


GRASS_WIDTH_TOL = 1.0          # Phase 22a: a grass run spans widths this far apart (it takes the widest: no gap before a wall)
GRASS_CLEARANCE = 0.5          # Phase 22a: grass over tarmac is dropped only this near a racing line (walls: WALL_CLEARANCE).
                               # Narrowed by a drawn barrier, a grass step's centre lies on the tarmac of a wider neighbour
                               # point and its inner line (GRASS_FLOOR) within 3 of the +8 line: dropped, a 4-unit hole
                               # (Alpine 300)


def _near_racing_lines(w: Quad16, pts, dense: bool = True, clearance: float = WALL_CLEARANCE) -> bool:
    """A point of the centreline or of an AI line (`road.AI_OFFSETS` laterally), sampled every unit along the lap (dense)
    or at the points, lies inside the quad or within WALL_CLEARANCE of its edges (segments): a wall there would make the
    cars on that line scrape (another leg in a hairpin, a deck). Grass over tarmac keeps the point samples (Phase 19
    review: densely, grass over a side area's tarmac 3 units off the +8 line was dropped, Pacific Coast 388)."""
    c = w.corners
    x0, x1 = min(p[0] for p in c) - clearance, max(p[0] for p in c) + clearance
    z0, z1 = min(p[2] for p in c) - clearance, max(p[2] for p in c) + clearance
    lines = _racing_line_samples(pts, dense)
    near = lines[(lines[:, 0] >= x0) & (lines[:, 0] <= x1) & (lines[:, 1] >= z0) & (lines[:, 1] <= z1)]
    for px, pz in near:
        if _point_in_xz(c, px, pz) or min(_segment_distance((px, pz), c[i], c[(i + 1) % 4]) for i in range(4)) < clearance:
            return True                                   # (Phase 19: the edge segment's distance; to its line, a wall step's
    return False                                          # end edge, radial, passed through its own point's AI points)


def _segment_distance(p, a, b) -> float:
    """Distance in xz from point p = (x, z) to the segment a-b (3-D corners)."""
    ax, az, bx, bz = a[0], a[2], b[0], b[2]
    dx, dz = bx - ax, bz - az
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - az) * dz) / ((dx * dx + dz * dz) or 1.0)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (az + t * dz))


def _covers_road(v: Quad16, pts) -> bool:
    """A centreline point lies inside the verge: on its own leg a verge starts at the road's measured edge, so this is
    another leg's road — a crossing deck (Metropolis) or a close leg (a hairpin's straights) — and the verge would lie
    over the road there (Phase 14: at 80 units Metropolis point 272 had its whole road band under the upper deck's verge)."""
    xs = [c[0] for c in v.corners]; zs = [c[2] for c in v.corners]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    return any(x0 <= x <= x1 and z0 <= z <= z1 and _point_in_xz(v.corners, x, z) for x, z in pts)


END_SPLIT_UNITS = 120.0        # Phase 22l: tarmac quads within this of the lap's end along the road are cut into pieces no
END_SPLIT_LATERAL = 40.0       # ... and whose centre lies within this of the centreline (the road and the Oval's apron beside it)
END_SPLIT_LEN = 15.0           # longer than this: the Oval's start straight was one 70-unit Saturn slice ending 33 units before
                               # the new line, credited one road point (384 for 377-384); the field's road point jumped 376 -> 384
                               # -> 386 and three opponents halted on it with the cursor at 385 (the credits step by one now)
START_BAND = 12.0              # the start-line band reaches this far before the line (arcade units); it ends at the line
BAND_SIDE = 5.0                # Phase 22n: the band cuts only the road at the line: a quad whose corners all lie this far beyond the
                               # road's measured width is left whole (Diablo's pit lane runs beside its start line, 77 units out;
                               # Amazon's and Surfers Road's side slabs 24-28 out were dropped as wholly inside the band's reach)
SEAM_OVERLAP = 0.5             # Phase 22j: the head quad reaches this far behind the line, under the spawn on road point 0 (a
                               # shared edge through the spawn gave the pit-phase placement no quad: Diablo, p22play66); under a unit


def _clip_quad(c, d, origin, at: float, keep_ahead: bool) -> list[list[tuple]]:
    """The part of a convex quad (FL, FR, BR, BL) on one side of the line `at` units past `origin` along d (ahead of it when
    keep_ahead, behind it otherwise), as quads: the clipped polygon has 3-5 corners; a triangle gets a fourth corner at its
    longest edge's middle (as slice_quads gives a Saturn triangle), a pentagon is split into a quad and such a triangle.
    New corners take the height along their edge (the quad keeps its plane). Each piece keeps the arcade winding and starts
    with its front edge (the edge furthest along d), as the segment walk reads it. [] when nothing a unit long is left."""
    along = lambda p_: (p_[0] - origin[0]) * d[0] + (p_[2] - origin[1]) * d[1]
    keep = (lambda v: v >= at - 1e-9) if keep_ahead else (lambda v: v <= at + 1e-9)
    poly = []
    for k in range(4):
        a, b = c[k], c[(k + 1) % 4]
        va, vb = along(a), along(b)
        if keep(va):
            poly.append(a)
        if keep(va) != keep(vb) and abs(va - vb) > 1e-12:
            t = (at - va) / (vb - va)
            poly.append(tuple(a[j] + t * (b[j] - a[j]) for j in range(3)))
    if len(poly) < 3:
        return []
    def tri(p3):
        k = max(range(3), key=lambda i: math.dist((p3[i][0], p3[i][2]), (p3[(i + 1) % 3][0], p3[(i + 1) % 3][2])))
        m = tuple((p3[k][j] + p3[(k + 1) % 3][j]) / 2 for j in range(3))
        return p3[:k + 1] + [m] + p3[k + 1:]
    pieces = [poly] if len(poly) == 4 else ([tri(poly)] if len(poly) == 3 else [poly[:4], tri([poly[3], poly[4], poly[0]])])
    out = []
    for pc in pieces:
        if _shoelace(pc) > 0:
            pc = pc[::-1]
        k = max(range(4), key=lambda i: along(pc[i]) + along(pc[(i + 1) % 4]))
        pc = pc[k:] + pc[:k]
        if max(along(p_) for p_ in pc) - min(along(p_) for p_ in pc) >= 1.0 and abs(_shoelace(pc)) > MIN_AREA_QUAD:
            out.append(pc)
    return out


def _hull4(c) -> list[tuple]:
    """The convex hull of four corners as four corners in the input's winding: a reflex corner is dropped and the
    triangle gets a fourth corner at its longest edge's middle (as slice_quads gives a Saturn triangle)."""
    pts = sorted(set(c), key=lambda p_: (p_[0], p_[2]))
    cross = lambda o, a, b: (a[0] - o[0]) * (b[2] - o[2]) - (a[2] - o[2]) * (b[0] - o[0])
    lower, upper = [], []
    for p_ in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p_) <= 0:
            lower.pop()
        lower.append(p_)
    for p_ in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p_) <= 0:
            upper.pop()
        upper.append(p_)
    hull = lower[:-1] + upper[:-1]                            # counter-clockwise in (x, z)
    if len(hull) == 3:
        k = max(range(3), key=lambda i: math.dist((hull[i][0], hull[i][2]), (hull[(i + 1) % 3][0], hull[(i + 1) % 3][2])))
        hull = hull[:k + 1] + [tuple((hull[k][j] + hull[(k + 1) % 3][j]) / 2 for j in range(3))] + hull[k + 1:]
    if len(hull) != 4:
        return list(c)
    if (_shoelace(hull) > 0) != (_shoelace(list(c)) > 0):
        hull = hull[::-1]
    return hull


def _shoelace(c) -> float:
    return 0.5 * sum(c[k][0] * c[(k + 1) % len(c)][2] - c[(k + 1) % len(c)][0] * c[k][2] for k in range(len(c)))


def split_quads_before_the_line(tarmac: list[Quad16], pts, height: HeightFn, units: float = END_SPLIT_UNITS,
                                length: float = END_SPLIT_LEN) -> tuple[list[Quad16], int]:
    """Phase 22l: `tarmac` with every quad whose centre lies within `units` of the lap's end (along `pts`) and which is
    longer than `length` along the road cut into equal pieces of at most `length` (`_clip_quad`: new corners on the
    quad's plane), in place; and how many quads were cut. The game credits a quad one road point, so a long quad
    before the line makes the field's road point jump and its cursor can wait for a point that never comes."""
    n = len(pts)
    if n < 3:
        return list(tarmac), 0
    spacing = math.dist(pts[0], pts[1]) or 10.0
    dirs = _smooth_dirs(pts)
    out: list[Quad16] = []; cut = 0
    for q in tarmac:
        cx, cz = q.centre[0], q.centre[2]
        k = min(range(n), key=lambda i: (pts[i][0] - cx) ** 2 + (pts[i][1] - cz) ** 2)
        if (n - k) * spacing > units or k == 0 or math.dist(pts[k], (cx, cz)) > END_SPLIT_LATERAL:
            out.append(q); continue                                # (END_SPLIT_LATERAL 40: the apron's slices too — split to
                                                                   # the road alone, the Oval's field stalled again: the walk
                                                                   # numbers the pieces by list order at the seam, follow-up)
        d = dirs[k]; o = pts[k]
        along = [(c[0] - o[0]) * d[0] + (c[2] - o[1]) * d[1] for c in q.corners]
        lo, hi = min(along), max(along)
        if hi - lo <= length + 1e-6:
            out.append(q); continue
        m = int(math.ceil((hi - lo) / length)); pieces = []
        rest = [list(q.corners)]
        for i in range(1, m):
            at = lo + (hi - lo) * i / m
            nxt = []
            for c in rest:
                pieces.extend(_clip_quad(c, d, o, at, False))
                nxt.extend(_clip_quad(c, d, o, at, True))
            rest = nxt
        pieces.extend(rest)
        out.extend(Quad16(tuple(pc), _mean(pc), q.attr) for pc in pieces); cut += 1
    return out, cut


def start_line_band(tarmac: list[Quad16], pts, height: HeightFn, reach: float = START_BAND) -> tuple[list[Quad16], dict]:
    """One quad across the road's measured width from `reach` units before the start line to the line, appended last
    (credited n−1 as a straddler, formats §15), with the quads around it cut back so that nothing else lies under a
    car in that band: a quad ending inside it loses its front to its rear edge, a head quad crossing the line loses
    its rear to the line (the first segment is pinned to road point 0), one wholly inside is dropped; the tail's
    straddlers are kept (credited n−1 too). The TGP breaks ties between overlapping quads by rounding, so a car was
    certain of the last point only where no other quad lay under it — on Diablo Canyon the first quad, credited 0,
    began 9 units before the line and three opponents stepped from 450 to 0 and waited at n−1 for good. The band
    ends AT the line: past it the Bay Bridge / Acropolis templates line the field up from road point 1, and a car
    standing on a quad credited n−1 through the countdown has its cursor run away (measured 125–131 points with a
    band reaching 10 units past the line). It is laid in the frame of the road's smoothed direction at point 0 (the
    centreline itself hooks at the lap seam)."""
    dirs = _smooth_dirs(pts)
    d = dirs[0]; r = (d[1], -d[0]); o = pts[0]
    along = lambda p: (p[0] - o[0]) * d[0] + (p[2] - o[1]) * d[1]
    # the band is as wide as the road anywhere in it (Phase 17: measured at point 0 alone it missed the tarmac it cut away
    # where the road is wider before the line — Alpine 14-16 units left, Amazon 13 — and left those samples bare)
    tb = _bboxes(tarmac)
    left = right = 0.0
    for a in [-reach * i / 6 for i in range(7)]:
        x, z = o[0] + a * d[0], o[1] + a * d[1]
        left = max(left, _edge_scan(tarmac, tb, x, z, r[0], r[1], -1.0, height))
        right = max(right, _edge_scan(tarmac, tb, x, z, r[0], r[1], 1.0, height))
    out = []; cut = dropped = 0; behind: list = []; behind_attr: list = []
    half = len(tarmac) // 2
    for k, q in enumerate(tarmac):
        c = q.corners
        if math.hypot(q.centre[0] - o[0], q.centre[2] - o[1]) > 4 * reach + 60:
            out.append(q); continue
        lats = [(p_[0] - o[0]) * r[0] + (p_[2] - o[1]) * r[1] for p_ in c]
        if min(lats) > right + BAND_SIDE or max(lats) < -left - BAND_SIDE:   # Phase 22n: beside the road, not on it (Diablo's
            out.append(q); continue                            # pit lane beside the line lost its slice after the entry)
        als = [along(p_) for p_ in c]                          # by the corners, not the edge mids: a skewed quad's corner
        f, b = max(als), min(als)                              # reaches into the band when its mid does not (Diablo's seam)
        crossing = b < 0.0 < f
        if k < half and not crossing and abs(b) < 1e-6:        # Phase 22j: a head quad starting exactly at the line reaches
            moved = [(p_[0] - d[0] * SEAM_OVERLAP, None, p_[2] - d[1] * SEAM_OVERLAP) if along(p_) < 1e-6 else p_ for p_ in c]
            moved = [(x, height(x, z), z) if y is None else (x, y, z) for x, y, z in moved]    # SEAM_OVERLAP behind it: the
            out.append(Quad16(tuple(moved), _mean(moved), q.attr)); cut += 1; continue           # spawn on road point 0 sits
        if (crossing and k >= half) or f <= -reach or b >= 0.0:   # a straddler of the lap's tail (credited n−1), or clear of the band
            out.append(q); continue                            # inside it, not on its edge (the placement query found no quad there)
        if crossing:                                           # a head quad across the line (the first segment is pinned to
            pieces = _clip_quad(list(c), d, o, -SEAM_OVERLAP, True)   # road point 0): it starts SEAM_OVERLAP before the line
            if b < -reach:                                     # now (Phase 22j), and keeps its part
                behind.extend(_clip_quad(list(c), d, o, -reach, False))   # behind the band if it reaches that far back — listed
                behind_attr.append(q.attr)                     # with the lap's tail, just before the band (in the head it read as
                                                               # the lap's end and the walk credited what followed n−1)
        elif b < -reach < f <= 0.0:
            pieces = _clip_quad(list(c), d, o, -reach, False)
        else:
            pieces = []
        # Phase 17: clipped as polygons (moving a skewed quad's corner pair along its sides lost tarmac outside the band:
        # Diablo Canyon's two head quads were dropped whole and left 8 units of no quad at the line, where the grid starts)
        if not pieces:
            dropped += 1; continue
        out.extend(Quad16(tuple(pc), _mean(pc), q.attr) for pc in pieces); cut += 1
    def at(a, lat):
        x, z = o[0] + a * d[0] + lat * r[0], o[1] + a * d[1] + lat * r[1]
        return (x, height(x, z), z)
    c = [at(0.0, -left), at(0.0, right), at(-reach - SEAM_OVERLAP, right), at(-reach - SEAM_OVERLAP, -left)]   # FL, FR, BR, BL
    # (Phase 22l: the band reaches SEAM_OVERLAP past its rear line over the quads cut there, so a sample on that shared
    # edge lies inside one of them — the Oval's half-unit grid landed on it: 7 holes of measure zero)
    band = Quad16(tuple(c), _mean(c), direction_attr(d[0], d[1]))
    if xz_area(band) > 0:
        c.reverse(); band = Quad16(tuple(c), _mean(c), band.attr)
    attr = behind_attr[0] if behind_attr else band.attr
    out.extend(Quad16(tuple(pc), _mean(pc), attr) for pc in behind)
    out.append(band)
    return out, {"band_cut": cut, "band_dropped": dropped}


def coverage_gaps(quads: list[Quad16], n_tarmac: int, pts, half_width: float = COVERAGE_HALF_WIDTH,
                  step: float = COVERAGE_STEP, edges: list[tuple[float, float]] | None = None,
                  shift: list[float] | None = None, blocked: Callable[[float, float], bool] | None = None) -> list[Gap]:
    """Sample points of the road (every centreline point, lateral offsets −half_width..half_width every `step`, moved
    sideways by `shift[p]` where given: Phase 22n, the AI lines' shift onto the Saturn's tarmac band) that no tarmac quad
    contains. An opponent whose AI line crosses such a spot is on verge and stops for good. With `edges` (`road_edges`
    for `pts`), each side is sampled out to the larger of the band and its measured edge less one scan step (Phase 17:
    the holes inside a wide road)."""
    tarmac = quads[:n_tarmac]; boxes = _bboxes(tarmac); dirs = _dirs(pts)
    k = int(round(half_width / step))
    base = [i * step for i in range(-k, k + 1)]
    fans = [dirs] if edges is None else [dirs, _smooth_dirs(pts)]   # Phase 17: on a bend the two directions sample different
    gaps = []                                                         # lines; a hole between them was missed (Surfers Road 398)
    for p, (x, z) in enumerate(pts):
        sh = shift[p] if shift is not None else 0.0                 # the band around the shifted lines (a band around both the
        offsets = [o + sh for o in base]                             # centreline and the lines cost Surfers Road 12,000 TGP words)
        if edges is not None:
            left = max(half_width - sh, edges[p][0] - VERGE_SCAN_STEP); right = max(half_width + sh, edges[p][1] - VERGE_SCAN_STEP)
            offsets = [-i * step for i in range(int(left / step), 0, -1)] + [i * step for i in range(0, int(right / step) + 1)]
        seen = set()
        for fan in fans:
            dx, dz = fan[p]; rx, rz = dz, -dx
            for lat in offsets:
                sx, sz = x + lat * rx, z + lat * rz
                if not _covered(sx, sz, tarmac, boxes) and (round(sx, 1), round(sz, 1)) not in seen:
                    seen.add((round(sx, 1), round(sz, 1)))
                    if blocked is not None and blocked(sx, sz):      # Phase 22p: a median block is no gap
                        continue
                    gaps.append(Gap(p, lat, sx, sz))
    return gaps


def _dist_to_quad(q: Quad16, x: float, z: float) -> float:
    best = math.inf
    for i in range(4):
        ax, az = q.corners[i][0], q.corners[i][2]; bx, bz = q.corners[(i + 1) % 4][0], q.corners[(i + 1) % 4][2]
        dx, dz = bx - ax, bz - az; l2 = dx * dx + dz * dz
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / l2))
        best = min(best, math.hypot(ax + t * dx - x, az + t * dz - z))
    return best


FILLER_STEP = 2.5            # Phase 22a rework: the height may change this much per 2 units out on a continuous surface


def _continuous(height: HeightFn, x: float, z: float, rx: float, rz: float, lat: float) -> bool:
    """From the centreline point (x, z) out to `lat` along (rx, rz), the height changes by at most FILLER_STEP per 2
    units: one surface (a bank), not a jump onto another deck."""
    steps = max(1, int(abs(lat) // 2))
    prev = height(x, z)
    for i in range(1, steps + 1):
        f = lat * i / steps
        y = height(x + f * rx, z + f * rz)
        if abs(y - prev) > FILLER_STEP * abs(lat) / steps / 2:
            return False
        prev = y
    return True


def fill_coverage(quads: list[Quad16], n_tarmac: int, lap, pts, height: HeightFn,
                  gaps: list[Gap], spacing: float = COVERAGE_SPACING) -> tuple[list[Quad16], int, dict]:
    """Cover `gaps`: the nearest tarmac quad of the same stretch (centre within COVERAGE_REACH, lap arc within
    COVERAGE_ARC) is grown sideways (at most GROW_MAX) until the gap lies inside it; gaps no quad can absorb get a
    filler quad (FILLER_LENGTH along the road, the gaps' lateral span ± FILLER_HALF_WIDTH across, at the road height,
    the nearest quad's direction attribute), inserted into the tarmac block in lap order. Returns (quads, n_tarmac, report)."""
    tarmac = list(quads[:n_tarmac]); verges = list(quads[n_tarmac:])
    dirs = _dirs(pts)
    # a quad's place on the lap is the centreline point nearest its front among the points heading its way: lap arcs
    # by the nearest slice centre (`arc_of`) named the other leg where the road passes near itself (Amazon Falls:
    # a filler for point 134 was inserted among the quads of point 188 and credited 188)
    fronts = _front_points(tarmac, pts, dirs)
    span = int(round(COVERAGE_ARC / spacing))                  # points of `pts` (every `spacing` units) in one stretch
    grow: dict[int, float] = {}
    leftover: dict[int, list[Gap]] = {}
    sboxes = _bboxes(tarmac)
    src = list(tarmac)

    def slice_y(x: float, z: float) -> float:
        """The height a new corner takes (Phase 17): the plane of the slice under it nearest the road's height there, so
        a filler's or a grown quad's edge meets the slices it overlaps (from `height` alone the edges stood 0.3-0.6 units
        apart on Diablo Canyon's climbs and the player's pitch jumped 6-15 deg crossing them); `height` where no slice is."""
        h = height(x, z)
        ys = [_plane_height(t, x, z) for t, b in zip(src, sboxes) if b[0] <= x <= b[1] and b[2] <= z <= b[3] and _point_in_xz(t.corners, x, z)]
        ys = [y for y in ys if abs(y - h) <= VERGE_HEIGHT_STEP]
        return min(ys, key=lambda y: abs(y - h)) if ys else h
    # Phase 22j (Pascal: the camera's up/down jitter on the darker tarmac): a gap beside a slice is covered by an EDGE STRIP
    # that shares the slice's side edge, corner for corner, so the slice's own surface is untouched and the strip meets it
    # without a step. Growing the slice sideways (Phases 11-17) bent its bilinear surface under the racing line, and a
    # filler laid over the slices (+-6 units) carried its own surface: the game picks, per wheel, whichever overlapping quad
    # is nearest the car's height, the pick flipped as the car bobbed, and its suspension rang on every 0.05-unit step
    # (Alpine rec70: +-1.5-3 degrees of pitch at a 10-frame period over 1.0 of road).
    strips: dict[tuple[int, int], float] = {}                  # (quad, side 0 left / 1 right) -> outward reach
    for g in gaps:
        cands = [i for i, q in enumerate(tarmac)
                 if math.hypot(q.centre[0] - g.x, q.centre[2] - g.z) < COVERAGE_REACH
                 and abs(fronts[i] - g.point) <= span]
        best = None
        for i in cands:
            for side in (0, 1):
                d, t = _side_distance(tarmac[i], side, g.x, g.z)
                if -STRIP_SLACK <= t <= 1 + STRIP_SLACK and (best is None or d < best[0]):
                    best = (d, i, side)
        if best is not None and best[0] + 1.0 <= GROW_MAX:
            strips[(best[1], best[2])] = max(strips.get((best[1], best[2]), 0.0), best[0] + 1.0)
            continue
        leftover.setdefault(g.point, []).append(g)
    grown = 0
    added: dict[int, list[Quad16]] = {}
    # a strip's outer corners meet the slices around them (`slice_y`) unless that height is another deck's (Phase 17: a
    # corner over Metropolis's other deck took that deck's height); then they follow the slice's own surface outward
    def corner_y(q, x, z):
        own, road = _plane_height(q, x, z), slice_y(x, z)
        return road if abs(road - own) <= VERGE_HEIGHT_STEP else own
    for i, side, c in _strip_runs(tarmac, strips, corner_y):
        added.setdefault(i, []).append(Quad16(tuple(c), _mean(c), tarmac[i].attr))
        grown += 1
    if added:                                                 # each strip right after its slice, with its slice's front
        merged_t, merged_f = [], []
        for i, q in enumerate(tarmac):
            merged_t.append(q); merged_f.append(fronts[i])
            for st in added.get(i, ()):
                merged_t.append(st); merged_f.append(fronts[i])
        tarmac, fronts = merged_t, merged_f
    boxes = _bboxes(tarmac)
    for g in gaps:                                                     # growth that fell short becomes a filler
        if not _covered(g.x, g.z, tarmac, boxes) and g not in leftover.get(g.point, []):
            leftover.setdefault(g.point, []).append(g)
    # consecutive points' leftovers share one filler, at most FILLER_LENGTH of points long (Phase 17: sampled every 5 units,
    # each point's own 10-unit filler overlapped its neighbour's and the quads doubled)
    per = max(1, int(round(FILLER_LENGTH / spacing)))
    groups: list[list[int]] = []
    for p in sorted(leftover):
        if groups and p == groups[-1][-1] + 1 and len(groups[-1]) < per:
            groups[-1].append(p)
        else:
            groups.append([p])
    fillers = []
    filler_points = []
    for grp in groups:
        gs = [g for p in grp for g in leftover[p]]
        # Phase 22j: a filler covers its gaps and FILLER_MARGIN around them, no more (it lay +-6 units over the slices with
        # its own surface), and spans its points' half-spacing at each end so consecutive fillers abut instead of overlapping
        lo, hi = min(g.lateral for g in gs) - FILLER_MARGIN, max(g.lateral for g in gs) + FILLER_MARGIN
        h = spacing / 2
        from vrtools.convert.profile import MAX_CAMBER_UNITS       # (profile imports this module)
        def at(p, lat, along):
            x, z = pts[p]; dx, dz = dirs[p]; rx, rz = dz, -dx
            px, pz = x + lat * rx + along * dx, z + lat * rz + along * dz
            y, ref = slice_y(px, pz), height(x + along * dx, z + along * dz)   # the road's own height beside it, on the centreline
            if abs(y - ref) > VERGE_HEIGHT_STEP + MAX_CAMBER_UNITS and not _continuous(height, x + along * dx, z + along * dz, rx, rz, lat):
                y = ref                                       # another deck's (Phase 17 review: a Metropolis filler spanned -6.6
            return (px, y, pz)                                # to -24.6); a bank rising smoothly from the centre is kept (22a)
        first, last = grp[0], grp[-1]
        corners = (at(last, lo, h), at(last, hi, h), at(first, hi, -h), at(first, lo, -h))   # FL, FR, BR, BL
        x, z = pts[last]
        near = min(range(len(tarmac)), key=lambda j: math.hypot(tarmac[j].centre[0] - x, tarmac[j].centre[2] - z))
        cx, cz = sum(c[0] for c in corners) / 4, sum(c[2] for c in corners) / 4
        fillers.append(Quad16(corners, (cx, height(cx, cz), cz), tarmac[near].attr))
        filler_points.append(last)                                     # in lap order as its front's point
    # fillers go into the tarmac block in lap order, after the last quad of their stretch whose FRONT is at or before
    # their point (the segment walk credits a quad its front's point, in quad order, within a window past the previous
    # quad's: a filler placed after a long quad whose front is ahead of it would be credited that front; one appended
    # at the end would be read as "just before the start line", road point n−1, stranding every car that touches it)
    merged = list(tarmac)
    merged_fronts = list(fronts)
    n_pts = len(pts)
    for f, p in zip(fillers, filler_points):
        # the lap's last quads straddle the line and their fronts have wrapped to 0–2: a filler for a point near the
        # start must go among the head quads, before that wrapped tail (review: fillers for Amazon's points 1–2 went
        # after the last straddler, the last segment became road point 2 and the pin at n−1 never fired)
        wrap = next((i for i in range(1, len(merged_fronts)) if merged_fronts[i] < merged_fronts[i - 1] - n_pts // 2), len(merged_fronts))
        limit = wrap if p < n_pts - span else len(merged_fronts)        # Phase 17: at 5-unit points the tail's wrapped
        # fronts (0-4) fell inside the window of fillers up to ~16 points in and drew them to the end of the lap
        at = 0
        for i, fp in enumerate(merged_fronts[:limit]):
            if p - span <= fp <= p:                                              # the last same-stretch quad at or before it
                at = i + 1
        if at == 0:                                                              # no such quad: after the last one before it
            for i, fp in enumerate(merged_fronts[:limit]):
                if fp <= p:
                    at = i + 1
        merged.insert(at, f); merged_fronts.insert(at, p)
    report = {"gaps": len(gaps), "grown": grown, "fillers": len(fillers)}
    return merged + verges, len(merged), report


HOLE_SCAN_STEP = 0.5           # Phase 22j: the road band is scanned this finely for holes the coverage fill cannot see (its
HOLE_MARGIN = 0.4              # samples are a unit apart): the Saturn tiles its wide areas with slivers and leaves sub-unit holes
HOLE_CLUSTER = 1.1             # between them, which the slices' old 1-unit overlap along the road papered over. Uncovered points
                               # within HOLE_CLUSTER of each other share one tight filler, HOLE_MARGIN beyond them, ...
HOLE_PIECE = 12.0              # ... at most this long along the road (a crack along a bend gets several, each in its own frame)
HOLE_MAX_SPAN = 30.0           # Phase 22n: a cluster of holes wider ACROSS the road than this is open ground, not a sliver, and gets
                               # no filler (Diablo: the scan of the pit lane met the ground between it and the loop's banked road and
                               # laid one 120-by-60 filler over both, credited by its front: the loop's cars read 129 for 300 units); a
                               # long narrow one (a pit lane's gaps) is pieced along as before


PIT_LANE_HALF_WIDTH = 20.0     # the pit lanes are scanned for holes this far either side of their line (the mouth's merge wedge)


def _resample_open(line, spacing: float):
    """Points every `spacing` units along an open polyline (both ends kept)."""
    out = [tuple(line[0])]
    carry = 0.0
    for a, b in zip(line, line[1:]):
        seg = math.dist(a, b)
        if seg < 1e-9:
            continue
        t = spacing - carry
        while t <= seg:
            out.append((a[0] + (b[0] - a[0]) * t / seg, a[1] + (b[1] - a[1]) * t / seg)); t += spacing
        carry = seg - (t - spacing)
    if math.dist(out[-1], line[-1]) > 1e-6:
        out.append(tuple(line[-1]))
    return out


def fill_holes(quads: list[Quad16], n_tarmac: int, pts, height: HeightFn, half_width: float = COVERAGE_HALF_WIDTH,
               step: float = HOLE_SCAN_STEP, blockers: bool = False, skip_end: float = 0.0,
               shift: list[float] | None = None, blocked: Callable[[float, float], bool] | None = None) -> tuple[list[Quad16], int, int]:
    """Scan the road band (`pts` every COVERAGE_FILL_SPACING, +-half_width + 1 across, moved sideways by `shift[k]`
    where given: Phase 22n) every `step` units along and
    across; cluster the points no tarmac quad contains; cover each cluster with a tight filler in the road's frame
    there, at the height of the nearest tarmac quad's surface, placed right after that quad in the list (the segment
    walk credits a quad its front's point, so a filler sits by its neighbour). Returns (quads, n_tarmac, fillers added)."""
    tarmac = list(quads[:n_tarmac]); rest = list(quads[n_tarmac:])
    grid: dict[tuple[int, int], list[int]] = {}
    scan = quads if blockers else tarmac                              # with `blockers`, a point under a verge or a wall is no hole
    for i, q in enumerate(scan):                                       # (the pass after the walls: a trim at a drawn face opened it)
        xs = [c[0] for c in q.corners]; zs = [c[2] for c in q.corners]
        if max(xs) - min(xs) < 1e-6 and max(zs) - min(zs) < 1e-6:
            continue
        for gx in range(int(min(xs) // CELL), int(max(xs) // CELL) + 1):
            for gz in range(int(min(zs) // CELL), int(max(zs) // CELL) + 1):
                grid.setdefault((gx, gz), []).append(i)

    def covered(x, z):
        return any(_point_in_xz(scan[i].corners, x, z) for i in grid.get((int(x // CELL), int(z // CELL)), ()))
    n = len(pts); dirs = _dirs(pts)
    holes = []                                                         # (x, z, dx, dz, lap point)
    across = int(half_width / step)
    spacing = math.dist(pts[0], pts[1]) if n > 1 else 1.0
    keep_out = int(math.ceil(skip_end / spacing)) if skip_end > 0 else 0   # the start-line band (Phase 11: the last point's
    for k in range(n):                                                 # band must lie under no other quad; a late filler there
        if keep_out and (k >= n - keep_out or k == 0):                 # held a car at n-1 past the line and its cursor ran 27
            continue                                                   # points ahead: Surfers Road, car 1)
        (ax, az), (bx, bz) = pts[k], pts[(k + 1) % n]
        seg = math.dist((ax, az), (bx, bz))
        if not 0 < seg < 4 * COVERAGE_FILL_SPACING:                   # (the lap's closing segment can be long)
            continue
        dx, dz = (bx - ax) / seg, (bz - az) / seg
        m = max(1, int(seg / step))
        sh = shift[k] if shift is not None else 0.0                 # the band around the shifted lines
        for j in range(m):
            cx, cz = ax + dx * seg * j / m, az + dz * seg * j / m
            for t in range(-across, across + 1):
                x, z = cx - dz * (t * step + sh), cz + dx * (t * step + sh)
                if not covered(x, z) and not (blocked is not None and blocked(x, z)):   # Phase 22p: a median block is no hole
                    holes.append((x, z, dx, dz, k))
    if not holes:
        return quads, n_tarmac, 0
    # clusters by proximity
    hgrid: dict[tuple[int, int], list[int]] = {}
    for i, (x, z, *_) in enumerate(holes):
        hgrid.setdefault((int(x // HOLE_CLUSTER), int(z // HOLE_CLUSTER)), []).append(i)
    parent = list(range(len(holes)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, (x, z, *_) in enumerate(holes):
        gx, gz = int(x // HOLE_CLUSTER), int(z // HOLE_CLUSTER)
        for ddx in (-1, 0, 1):
            for ddz in (-1, 0, 1):
                for j in hgrid.get((gx + ddx, gz + ddz), ()):
                    if j > i and math.hypot(holes[j][0] - x, holes[j][1] - z) <= HOLE_CLUSTER:
                        parent[find(j)] = find(i)
    clusters: dict[int, list[int]] = {}
    for i in range(len(holes)):
        clusters.setdefault(find(i), []).append(i)
    boxes = _bboxes(tarmac)
    fronts = _front_points(tarmac, pts, dirs)                          # each quad's place on the lap (its front's point)
    added: dict[int, list[Quad16]] = {}
    pieces = []
    for members in clusters.values():                                  # a long cluster in pieces of HOLE_PIECE along the road
        dx, dz = holes[members[0]][2], holes[members[0]][3]
        lats = [-holes[i][0] * dz + holes[i][1] * dx for i in members]
        if max(lats) - min(lats) > HOLE_MAX_SPAN:
            continue                                                   # open ground, not a sliver (HOLE_MAX_SPAN)
        members = sorted(members, key=lambda i: holes[i][0] * dx + holes[i][1] * dz)
        start = 0
        for e in range(1, len(members) + 1):
            if e == len(members) or (holes[members[e]][0] - holes[members[start]][0]) * dx + (holes[members[e]][1] - holes[members[start]][1]) * dz > HOLE_PIECE:
                pieces.append(members[start:e]); start = e
    for members in pieces:
        x0 = sum(holes[i][0] for i in members) / len(members); z0 = sum(holes[i][1] for i in members) / len(members)
        dx, dz = holes[members[0]][2], holes[members[0]][3]; nx, nz = -dz, dx
        alongs = [(holes[i][0] - x0) * dx + (holes[i][1] - z0) * dz for i in members]
        lats = [(holes[i][0] - x0) * nx + (holes[i][1] - z0) * nz for i in members]
        a0, a1 = min(alongs) - HOLE_MARGIN, max(alongs) + HOLE_MARGIN
        l0, l1 = min(lats) - HOLE_MARGIN, max(lats) + HOLE_MARGIN
        # the neighbour that lends its place in the list and its height: the nearest tarmac quad heading the hole's way
        # (within 60 degrees); the nearest of all can be the other leg where the road passes near itself, and a filler
        # credited that leg's road point threw the cars' lap position back (test_each_course_races_on_its_own_tables)
        want = direction_attr(dx, dz)
        kp = holes[members[0]][4]
        ref = height(*pts[kp]) if 0 <= kp < len(pts) else height(x0, z0)   # the road's height at the hole's own lap point:
        def same_way(i):                                                  # never the other deck's quad (Metropolis: a filler
            a = tarmac[i].attr & 0xFFFF                                   # credited the deck below threw a car back 115 points)
            return a == 0 or ((a - (want & 0xFFFF)) & 0xFFFF) <= 0x2AAB or ((want - a) & 0xFFFF) <= 0x2AAB
        def same_deck(i):
            return abs(tgp_height(tarmac[i].corners, x0, z0) - ref) <= 2 * VERGE_HEIGHT_STEP
        box_near = [i for i in range(len(tarmac)) if boxes[i][0] - 30 <= x0 <= boxes[i][1] + 30 and boxes[i][2] - 30 <= z0 <= boxes[i][3] + 30]
        cands = [i for i in box_near if same_way(i) and same_deck(i)] or [i for i in box_near if same_deck(i)] or box_near or list(range(len(tarmac)))
        # the neighbour is the one nearest ON THE LAP (its front's point against the hole's own point): the geometrically
        # nearest quad at a crossing or where the road passes near itself is credited another road point, and a filler
        # placed after it threw a car's lap position back (Metropolis, car 8: 252 -> 137)
        def lap_gap(i):
            d = abs(fronts[i] - kp)
            return min(d, n - d)
        near = min(cands, key=lambda i: (lap_gap(i), _dist_to_quad(tarmac[i], x0, z0)))
        nq = tarmac[near]
        if near == len(tarmac) - 1 and len(tarmac) > 1:              # never after the start-line band (the last quad is pinned
            near -= 1                                                 # to road point n-1: formats section 15)
        def at(a, l):
            x, z = x0 + dx * a + nx * l, z0 + dz * a + nz * l
            y = tgp_height(nq.corners, x, z)
            if abs(y - height(x, z)) > VERGE_HEIGHT_STEP:
                y = height(x, z)
            return (x, y, z)
        c = [at(a1, l0), at(a1, l1), at(a0, l1), at(a0, l0)]            # FL, FR, BR, BL
        added.setdefault(near, []).append(Quad16(tuple(c), _mean(c), nq.attr))
    out = []
    for i, q in enumerate(tarmac):
        out.append(q); out.extend(added.get(i, ()))
    return out + rest, len(out), sum(len(v) for v in added.values())


def saturn_collision(sat: SaturnCourse, height: HeightFn, y_offset: float = 0.0,
                     margin: float = MARGIN, lap=None, verges: bool | None = None,
                     merge: bool = False, cover: bool = False, lane_points=(),
                     grid_clear: tuple[int, int] = SHIFT_GRID_CLEAR) -> tuple[Collision, dict[int, int]]:
    side = not (cover and lap is not None)             # the build's verges come from the road's measured edge (below)
    lanes = None                                       # Phase 22c: the AI lane scales (the cover path sets them)
    quads, removed = slice_quads(sat, height, y_offset, margin, lap=lap, verges=verges, merge=True, side_verges=side) if merge \
        else (slice_quads(sat, height, y_offset, margin, lap=lap, verges=verges, side_verges=side), 0)
    reach = set(lap.order) if lap is not None else None
    n_tarmac = sum(1 for seg in sat.segments if seg.corners() is not None and (reach is None or seg.index in reach)) - removed   # tarmac first
    dropped = 0
    if merge and len(quads) > n_tarmac:
        # a verge whose centre lies on tarmac (side-by-side strips put one strip's verge over the other's road) is
        # left out: it covers nothing the car needs, costs list words and competes with the tarmac in the TGP's pick
        tarmac = quads[:n_tarmac]
        kept = [v for v in quads[n_tarmac:] if not _on_tarmac(v, tarmac)]
        dropped = len(quads) - n_tarmac - len(kept)
        quads = tarmac + kept
    coverage = None
    if cover and lap is not None:                      # every AI line on tarmac (Phase 11): grow or fill the gaps, sampled on
        pts = centreline(lap, spacing=COVERAGE_SPACING)   # the road tables' centreline (one point per 10 units)
        hfun = lambda x, z: height(x, z) + y_offset
        global _SHIFT, _NAMED                             # Phase 22n: the AI lines' sideways shift onto the Saturn's own tarmac
        _NAMED = tuple(lane_points)
        _SHIFT = shift = lane_shift(quads[:n_tarmac], pts, height=hfun, grid_clear=grid_clear)   # band (the route follows one strip); the coverage band and the
        shift_at = lambda dense: [shift[int(i * len(shift) / len(dense)) % len(shift)] for i in range(len(dense))]   # walls follow
        dense = centreline(lap, spacing=COVERAGE_FILL_SPACING)   # Phase 17: every 5 units and out to the measured edge
        medians = None; blocked = None
        if verges is None or verges:                                 # Phase 22p: a drawn barrier between two tarmac strips
            ground_levels = mesh_heights([q for q in course_quads(sat, groups=(0, 1)) if not is_water(q.rgb)])   # (Phase 22o: the
                                                                                                    # verges follow the drawn ground)
            barriers = [q for q in course_quads(sat, groups=STEEP_GROUPS) if is_barrier(q)] \
                + [q for q in course_quads(sat, groups=SOLID_GROUPS) if not is_water(q.rgb) and not is_shoulder(q)]   # Phase 22a: the drawn cliffs,
            curbs: list = []
            faces = fill_faces(barrier_faces(barriers, pts, hfun, curbs=curbs))                # canyon sides and fences;
            medians = median_blocks(faces, pts, hfun, ground_levels, quads[:n_tarmac])         # (Metropolis's pit wall) keeps
            if any(b for pair in medians for b in pair):                                       # its footprint open in the fills
                blocked = median_blocked(pts, medians)
        gaps = coverage_gaps(quads, n_tarmac, dense, edges=road_edges(quads[:n_tarmac], dense, hfun), shift=shift_at(dense), blocked=blocked)
        quads, n_tarmac, coverage = fill_coverage(quads, n_tarmac, lap, dense, hfun, gaps, spacing=COVERAGE_FILL_SPACING)
        quads, n_tarmac, coverage["holes"] = fill_holes(quads, n_tarmac, dense, hfun, shift=shift_at(dense), blocked=blocked)   # Phase 22j: the sub-unit holes
        pit_line = pit_lane_centres(sat, pts)                                            # ... and the pit lane's (Diablo's
        if len(pit_line) >= 2:                                                           # spawn is in it: Pascal "started in
            quads, n_tarmac, n_pit = fill_holes(quads, n_tarmac, _resample_open(pit_line, COVERAGE_FILL_SPACING), hfun,   # the air")
                                               half_width=PIT_LANE_HALF_WIDTH, blocked=blocked)
            coverage["holes"] += n_pit
        tarmac, coverage["end_split"] = split_quads_before_the_line(quads[:n_tarmac], pts, hfun)   # Phase 22l: short quads into the line
        tarmac, band = start_line_band(tarmac, pts, hfun)             # an uncontested last-point band before the line
        coverage.update(band)
        quads = tarmac + quads[n_tarmac:]; n_tarmac = len(tarmac)
        if verges is None or verges:                      # the side verges, from the tarmac's measured edge; the unreached
            water = [q for q in course_quads(sat, groups=(0, 1)) if is_water(q.rgb)]     # Phase 19: the grass stops at the
            props = course_quads(sat, groups=(4,))                                             # Phase 22k (3a): the placed objects
            prop_faces = barrier_faces(props, pts, hfun, spread=0) if props else None          # stop a car too (no median):
            if prop_faces:                                                                     # Phase 22p: not a post in the road
                prop_faces = in_road_faces(prop_faces, pts, hfun, mesh_lookup([q for q in course_quads(sat, groups=(0, 1)) if not is_water(q.rgb)]))
            if prop_faces:                                                                     # their faces join the drawn ones
                faces = merge_prop_faces(faces, prop_faces)                                    # from PROP_MIN_LATERAL out
            global _LANES                                                                      # Phase 22c: the AI lines
            always = narrowing_faces(faces, curbs, prop_faces, road_edges(tarmac, pts, hfun))   # narrow at Pascal's named points;
            always = [tuple(min(always[k][sd], medians[k][sd][0] + MEDIAN_IN if medians[k][sd] else math.inf) for sd in (0, 1))
                      for k in range(len(always))]                                             # Phase 22p: and at a median wall
            lanes = _LANES = [(a, b, shift[k]) for k, (a, b) in enumerate(lane_scales(faces, lane_points, always=always))]   # Phase 22k (3b): at a curb at the
                                                                                               # road's edge or a prop anywhere
            rest = quads[n_tarmac:]                                                            # (the slices' own grass)
            faces_walls = faces                                                                # Phase 22p: a median's face is the
            if medians is not None and any(b for pair in medians for b in pair):               # median wall's; the trim and the
                nn = len(faces)                                                                # run-off wall ignore it and its
                faces_walls = [tuple(math.inf if any(medians[(k + j) % nn][sd] for j in (-1, 0, 1)) else faces[k][sd]   # neighbours (the
                                     for sd in (0, 1)) for k in range(nn)]                     # trim at 12.5 from the fence's 9 cut
            tarmac, coverage["trimmed"] = trim_tarmac(tarmac, pts, faces_walls, keep=pit_lane_polygons(sat))   # the mouth's fill; the
                                                                                               # wall joined the fence's start at 20
                                                                                               # to the median at 9 across the mouth)
            n_split = len(tarmac); tarmac = split_bank_quads(tarmac, hfun)                     # Phase 22c: a bank's knee
            coverage["bank_split"] = len(tarmac) - n_split
            n_tarmac = len(tarmac)
            edges = road_edges(tarmac, pts, hfun)
            shore = shore_widths(water, pts, edges)                                          # Saturn's water, the wall starts there
            coverage["shore"] = sum(1 for pair in shore for w in pair if w < VERGE_GRASS)
            fence = barrier_widths(faces_walls, edges)                                         # and the wall there
            coverage["barrier"] = sum(1 for pair, wpair in zip(fence, shore) for f, w in zip(pair, wpair) if f < w)
            water_widths = shore
            shore = [tuple(min(a, b) for a, b in zip(s, f)) for s, f in zip(shore, fence)]
            # Phase 16: the run-off ends in a wall strip (surface 5); none over tarmac, none beside a racing line
            fine = [tuple(w < VERGE_GRASS for w in pair) for pair in wall_insets(water_widths)]
            water_insets = wall_insets(water_widths); reverted: set[tuple[int, int]] = set()
            def wall_strip(widths):                                    # (a reverted point takes the shore's wall inset too: the
                ins = wall_insets(widths)                              # narrowest within 12 points kept the dropped near wall)
                ins = [tuple(water_insets[k][sd] if (k, sd) in reverted else ins[k][sd] for sd in (0, 1)) for k in range(len(ins))]
                ins = [tuple(widths[k][sd] if fence[k][sd] < water_widths[k][sd] and (k, sd) not in reverted else ins[k][sd]
                             for sd in (0, 1)) for k in range(len(ins))]   # Phase 22a: a drawn barrier's wall at its own
                # point's width, not eroded (Pascal p22play20, Diablo's first right turn: rock at the road at 18-24 and 40-42
                # pulled the wall to the edge at 26-38, the face 17.5-29.5 out); _meet_walls and _join_wall_runs close the seams
                built = road_verges(tarmac, pts, hfun, width=WALL_WIDTH, inset=ins, follow=True, fine=fine, ground=ground_levels)
                return built, [w for w in built if not _on_tarmac(w, tarmac) and not _near_racing_lines(w, pts)]
            def grass(widths):                                         # slices' grass (quads[n_tarmac:]) stays
                built = road_verges(tarmac, pts, hfun, width=widths, follow=True, caps=water_widths, ground=ground_levels)
                return built, [v for v in built if not _on_tarmac(v, tarmac, other_deck=True)   # Phase 22a: grass over tarmac
                               and not (_on_tarmac(v, tarmac) and _near_racing_lines(v, pts, dense=False, clearance=GRASS_CLEARANCE))]
            n = len(pts)
            def problems(widths, ws, gr):                              # wall-less, holed and open sides of a build
                ws_ids_from = len(tarmac) + len(gr)
                wall_ids, grass_ids = set(range(ws_ids_from, ws_ids_from + len(ws))), set(range(len(tarmac), ws_ids_from))
                return (_meet_walls(widths, ws, pts, edges)[1] | _gap_sides(tarmac + gr + ws, wall_ids, pts)
                        | _open_sides(tarmac + gr + ws, wall_ids, grass_ids, pts))
            before = set()
            if coverage["barrier"]:                                    # the same problems without the barrier walls are not
                reverted = {(k, sd) for k in range(n) for sd in (0, 1)}   # theirs (far side areas, Metropolis's decks)
                before = problems(water_widths, wall_strip(water_widths)[1], grass(water_widths)[1])
                reverted = set()
            for attempt in range(BARRIER_RETRIES + 1):
                walls_built, walls = wall_strip(shore)
                if not coverage["barrier"]:
                    built, kept = grass(_meet_walls(shore, walls, pts, edges)[0])   # the grass meets the wall everywhere
                    break
                # Phase 22a: the grass reaches the wall that was built (a wall run clears its widest edge, raised past the
                # grass of a narrower point: holes of 1-7 units); a narrowed point with no wall within reach (its wall
                # dropped beside another deck: Metropolis 38-41 had none and nothing past 15 units of grass), or a hole
                # left before the wall (a grass step dropped over another deck or the tarmac at a measured edge's quirk),
                # takes the shore's width back with its neighbours: the run-off and wall as before
                widths, _ = _meet_walls(shore, walls, pts, edges)
                built, kept = grass(widths)
                if attempt == BARRIER_RETRIES:
                    break
                first_wall = len(tarmac) + len(kept)                   # Phase 22a: only a lost wall or a run-off ending in
                wall_ids, grass_ids = set(range(first_wall, first_wall + len(walls))), set(range(len(tarmac), first_wall))   # nothing
                bad = ((_meet_walls(shore, walls, pts, edges)[1] | _open_sides(tarmac + kept + walls, wall_ids, grass_ids, pts))
                       - before)                                       # (a half-unit seam is no reason: the gap-driven rounds
                                                                       # reverted 100-500 barrier sides per course)
                narrowed = lambda k, sd: shore[k % n][sd] < water_widths[k % n][sd]
                undo = set()                                           # the point and its neighbours; a bad side with none of them
                for k, sd in bad:                                      # narrowed lies in a wall run whose bounds moved with a
                    near = (-1, 0, 1) if any(narrowed(k + j, sd) for j in (-1, 0, 1)) else range(-WALL_MAX_RUN, WALL_MAX_RUN + 1)
                    undo |= {((k + j) % n, sd) for j in near if narrowed(k + j, sd)}   # narrowed point's (Surfers Oval 8-12:
                if not undo:                                           # the water side's wall then lay on the side area: dropped)
                    break
                reverted |= undo
                shore = [tuple(water_widths[k][sd] if (k, sd) in reverted else shore[k][sd] for sd in (0, 1)) for k in range(n)]
            coverage["walls_dropped"] = len(walls_built) - len(walls)
            median = median_walls(pts, medians, hfun)                 # Phase 22p: the wall over a median block (Metropolis's
            walls = walls + median; coverage["median_walls"] = len(median)   # pit wall), between the two tarmac strips
            coverage["walls"] = len(walls)
            coverage["barrier_reverted"] = sum(1 for k in range(n) for sd in (0, 1) if shore[k][sd] == water_widths[k][sd] and fence[k][sd] < water_widths[k][sd])
            coverage["verges"] = len(kept); coverage["verges_dropped"] = len(built) - len(kept)
            kept = clip_at_walls(kept, walls, hfun, plane=True)      # Phase 22a: no grass under a wall,
            tarmac = clip_at_walls(tarmac, walls, hfun, guard=True)              # no tarmac either (a slice's corners 0-1 and 2-3 run across)
            tarmac, coverage["slivers"] = drop_slivers_under_walls(tarmac, walls)   # Phase 22k: nor a sliver wholly under one
            n_tarmac = len(tarmac)
            quads = tarmac + kept + walls + rest
            # Phase 22j: the trim at the drawn faces and the clip under the walls open holes the earlier scan never saw
            # (Diablo's pit mouth: a 3-unit gap on the autopilot's line to the spawn); a point under no quad at all is filled
            quads, n_tarmac, n_late = fill_holes(quads, n_tarmac, dense, hfun, blockers=True, skip_end=START_BAND + COVERAGE_FILL_SPACING, blocked=blocked)
            if len(pit_line) >= 2:
                quads, n_tarmac, n_pit2 = fill_holes(quads, n_tarmac, _resample_open(pit_line, COVERAGE_FILL_SPACING), hfun,
                                                    half_width=PIT_LANE_HALF_WIDTH, blockers=True, blocked=blocked)
                n_late += n_pit2
            coverage["holes_late"] = n_late
            # Phase 22k: a late filler can land under a wall (Diablo's pit lane at 39-40 out from points 23 and 450: the main
            # road's run-off wall stood over a hole in the lane); no wall lies on tarmac, so those walls go now
            first, nw = n_tarmac + coverage["verges"], coverage["walls"]
            kept_walls = [w for w in quads[first:first + nw] if not _on_tarmac(w, quads[:n_tarmac])]
            coverage["walls_dropped"] += nw - len(kept_walls); coverage["walls"] = len(kept_walls)
            quads = quads[:first] + kept_walls + quads[first + nw:]
    if cover and lap is not None:
        # Phase 22j (Pascal, p22play56: "even on the main we get pulled into the pit"): the game's PIT WORK check fires on
        # the entry quad OR THE NEXT IN THE LIST, and the next is the adjacent main-road slice on Amazon (the Saturn's lane
        # and road slices alternate) or a filler: the entry quad is duplicated right after itself, so both are the mouth
        from types import SimpleNamespace
        k = pit_entry_quad(sat, SimpleNamespace(quads=quads, n_tarmac=n_tarmac), pts, require_pair=False)
        if k is not None:
            quads, n_tarmac, coverage["pit_entry"] = pit_entry_pair(sat, quads, n_tarmac, k, pts)
    lists, cells = cell_lists(quads, last=set(range(min(n_tarmac, len(quads)))) if len(quads) > n_tarmac else None)
    surface = None
    if lap is not None:
        surface = bytearray([SURFACE_TARMAC] * min(n_tarmac, len(quads)) + [SURFACE_GRASS] * max(0, len(quads) - n_tarmac))
        n_walls = (coverage or {}).get("walls", 0)              # only the cover path builds walls
        if n_walls:                                               # the wall strip follows the grass verges
            first = n_tarmac + coverage["verges"]
            surface[first:first + n_walls] = bytes([SURFACE_WALL] * n_walls)
        surface = bytes(surface)
    col = Collision(lists, quads, surface, removed, dropped, coverage=coverage, lanes=lanes)
    _LANES = None
    _SHIFT = None
    _NAMED = ()
    col.check()
    return col, cells
