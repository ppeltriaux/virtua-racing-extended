"""Road height profile along a lap, from the Saturn ground mesh.

The Saturn road slices carry no height (segment word 18 is 0 everywhere), but the Saturn ground tiles hold the
road surface faces (docs/spike/2026-11-m3-recon.md §4). The profile samples the ground mesh under each ordered
slice centre, fills holes by linear interpolation along the lap, and refuses cliffs.
"""
from __future__ import annotations

import math

import numpy as np
from typing import Callable, Sequence

from vrtools.convert.collision import HeightFn, mesh_heights
from vrtools.convert.geometry import ConvertError, WorldQuad, course_quads
from vrtools.convert.lap import Lap
from vrtools.saturn.course import SaturnCourse

GROUND_GROUPS = (0,)
PROFILE_SAMPLE_SPACING = 2.5   # Phase 20: the route's centreline is sampled this often too (route centres over a hole in the
                               # ground contributed nothing: the profile cut under Diablo Canyon's first climb by 2.2 units)


def _ground_quads(source) -> list[WorldQuad]:
    if isinstance(source, SaturnCourse):
        return course_quads(source, groups=GROUND_GROUPS)
    return list(source)


def road_profile(source, lap: Lap, y_offset: float = 0.0, max_step: float = 5.0, bin_size: float = 10.0,
                 sample_spacing: float = PROFILE_SAMPLE_SPACING) -> list[float]:
    """Height at each lap centre (arcade units), in lap order, as a smooth function of arc length.

    `source` is a SaturnCourse (its ground group is used) or a list of WorldQuads in arcade space. The ground is
    sampled under every covered centre; samples are binned by arc length (bin_size units, median per bin, so
    strips side by side on a banked section average out: converted collision carries no banking), empty bins
    are interpolated cyclically, and a height change over max_step between neighbouring bins is a ConvertError.
    A lap with no covered centre at all is also an error. With a route, the route's centreline is sampled every
    `sample_spacing` units too, at its true arcs (`centreline_arcs`; Phase 20: 0 = the centres only)."""
    ground = _ground_quads(source)
    if not ground:
        raise ConvertError("no ground mesh to take the road height from")
    hs = mesh_heights(ground)
    nbins = max(1, int(math.ceil(lap.length / bin_size)))
    samples: list[list[list[float]]] = [[] for _ in range(nbins)]       # per bin: per centre, its candidate levels
    pos = {i: k for k, i in enumerate(lap.order)}
    route = lap.route or lap.order                                   # one road: the other branch of a fork is left out
    for i in route:
        (x, z), a = lap.centres[pos[i]], lap.arc[pos[i]]
        levels = hs(x, z)
        if levels:
            samples[min(nbins - 1, int(a // bin_size))].append([v + y_offset for v in levels])
    if sample_spacing and lap.route:
        from vrtools.convert.lap import centreline
        pts = centreline(lap, spacing=sample_spacing)
        for (x, z), a in zip(pts, centreline_arcs(lap, pts)):
            levels = hs(x, z)
            if levels:
                samples[min(nbins - 1, int(a // bin_size))].append([v + y_offset for v in levels])
    known = [k for k in range(nbins) if samples[k]]
    if not known:
        raise ConvertError("no ground polygon under any lap centre")
    med = lambda v: sorted(v)[len(v) // 2]
    # a bridge deck over water (or an overpass) puts two levels under a centre: follow the level closest to the
    # running profile, starting from the most common top level of the first known bin
    bins: list[float | None] = [None] * nbins
    ref = med([c[0] for c in samples[known[0]]])
    for k in known:
        picked = [min(c, key=lambda v: abs(v - ref)) for c in samples[k]]
        bins[k] = med(picked)
        ref = bins[k]
    # a single centre on a kerb or wall face can own a bin: moving median over the nearest known bins (cyclic)
    if len(known) >= 5:
        smoothed = {}
        for pos, k in enumerate(known):
            window = [bins[known[(pos + d) % len(known)]] for d in (-2, -1, 0, 1, 2)]
            smoothed[k] = med(window)
        for k, v in smoothed.items():
            bins[k] = v
    for k in range(nbins):
        if bins[k] is not None:
            continue
        prev = max((j for j in known if j < k), default=known[-1])
        nxt = min((j for j in known if j > k), default=known[0])
        a_prev = prev if prev < k else prev - nbins
        a_next = nxt if nxt > k else nxt + nbins
        t = 0.0 if a_next == a_prev else (k - a_prev) / (a_next - a_prev)
        bins[k] = bins[prev] + t * (bins[nxt] - bins[prev])
    for k in range(nbins):
        a, b = bins[k], bins[(k + 1) % nbins]
        if abs(b - a) > max_step:
            raise ConvertError(f"road height step of {abs(b - a):.1f} between arc {k * bin_size:.0f} and "
                               f"{((k + 1) % nbins) * bin_size:.0f} exceeds {max_step}")

    def at(a: float) -> float:
        pos = (a / bin_size - 0.5) % nbins                       # bin k represents arc (k + 0.5) * bin_size
        k = int(math.floor(pos))
        t = pos - k
        return bins[k % nbins] + t * (bins[(k + 1) % nbins] - bins[k % nbins])

    return [float(at(a)) for a in lap.arc]


def profile_height(lap: Lap, heights: Sequence[float]) -> HeightFn:
    """Height at an arcade (x, z): the profile interpolated between the two lap centres the point projects
    between (nearest centre and its neighbour along the lap); lateral offset is ignored."""
    if len(heights) != len(lap.centres):
        raise ConvertError("one height per lap centre is needed")
    cs = lap.centres
    n = len(cs)

    def height(x: float, z: float) -> float:
        k = min(range(n), key=lambda i: (cs[i][0] - x) ** 2 + (cs[i][1] - z) ** 2)
        best = heights[k]
        best_d = math.inf
        for j in ((k - 1) % n, (k + 1) % n):
            ax, az = cs[k]
            bx, bz = cs[j]
            dx, dz = bx - ax, bz - az
            l2 = dx * dx + dz * dz
            if l2 == 0:
                continue
            t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / l2))
            px, pz = ax + t * dx, az + t * dz
            d = math.hypot(x - px, z - pz)
            if d < best_d:
                best_d = d
                best = heights[k] + t * (heights[j] - heights[k])
        return float(best)

    return height


MAX_TILT = 8.0
MAX_CAMBER_UNITS = 3.0          # the most a cambered quad corner rises or drops against the profile (edges at ±13 units); Phase 22a: 1.3 -> 3.0 (the drawn banking reaches 12.8°: the car rolled half of it and sank into the road)


def banked_height(lap: Lap, heights: Sequence[float], mesh: HeightFn, max_tilt: float = MAX_TILT) -> HeightFn:
    """The profile plus the ground mesh's lateral delta against the nearest lap centre, clamped to ±max_tilt:
    banked sections tilt the collision quads (their corners carry their own heights) while the centre keeps the
    profile. Where the mesh has no answer at either point the delta is 0."""
    profile = profile_height(lap, heights)
    cs = lap.centres
    n = len(cs)

    def mesh_or_none(x: float, z: float) -> float | None:
        try:
            return mesh(x, z)
        except ConvertError:
            return None

    def foot(x: float, z: float) -> tuple[float, float]:
        """The nearest point of the centre polyline (so the delta is lateral, not the slope along the road)."""
        k = min(range(n), key=lambda i: (cs[i][0] - x) ** 2 + (cs[i][1] - z) ** 2)
        best, best_d = cs[k], math.inf
        for j in ((k - 1) % n, (k + 1) % n):
            (ax, az), (bx, bz) = cs[k], cs[j]
            dx, dz = bx - ax, bz - az
            l2 = dx * dx + dz * dz
            if l2 == 0:
                continue
            t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / l2))
            fx, fz = ax + t * dx, az + t * dz
            d = (fx - x) ** 2 + (fz - z) ** 2
            if d < best_d:
                best, best_d = (fx, fz), d
        return best

    def height(x: float, z: float) -> float:
        base = profile(x, z)
        fx, fz = foot(x, z)
        here, centre = mesh_or_none(x, z), mesh_or_none(fx, fz)
        if here is None or centre is None:
            return base
        return base + max(-max_tilt, min(max_tilt, here - centre))

    return height


def _arc_profile(lap: Lap, heights):
    """The profile as a function of arc length (arcade units), linear between lap centres, cyclic over the lap."""
    arcs = list(lap.arc)
    n = len(arcs)
    length = lap.length

    def at(a: float) -> float:
        a %= length
        k = max(i for i in range(n) if arcs[i] <= a) if arcs[0] <= a else n - 1
        a0, h0 = arcs[k], heights[k]
        if k + 1 < n:
            a1, h1 = arcs[k + 1], heights[k + 1]
        else:
            a1, h1 = length, heights[0]
            if a < a0:
                a += length
        if a1 <= a0:
            return float(h0)
        t = (a - a0) / (a1 - a0)
        return float(h0 + t * (h1 - h0))

    return at


def centreline_arcs(lap: Lap, pts: list[tuple[float, float]], window: float = 60.0) -> list[float]:
    """The arc (0..lap.length) of each point of a resampled centreline, from the lap's single route chain (`lap.route`,
    `lap.route_arc`: one slice after another from the start round to the line, no side-by-side strips): the nearest route
    centre among those whose arc lies within `window` of the point's expected arc (k / n of the lap), plus the point's
    offset along the chain there. The resampled centreline is the smoothed polyline and does not keep the lap's arc
    (Diablo 4530 vs 4564): taking point k at arc k x spacing drifted up to 50 units and put the collision up to 5 units off
    the drawn road; the lap order's centres zigzag through side-by-side strips and made the pitch jump 12 deg (Phase 16
    review). Falls back to k / n of the lap when the lap has no route."""
    L, n = lap.length, len(pts)
    if not lap.route:
        return [k * L / n for k in range(n)]
    pos = {s: i for i, s in enumerate(lap.order)}
    rc = [lap.centres[pos[s]] for s in lap.route]
    ra = list(lap.route_arc)
    m = len(rc)
    out = []
    for k, (x, z) in enumerate(pts):
        expected = k * L / n
        near = [j for j in range(m) if min(abs(ra[j] - expected), L - abs(ra[j] - expected)) <= window] or list(range(m))
        j = min(near, key=lambda i: (rc[i][0] - x) ** 2 + (rc[i][1] - z) ** 2)
        (ax, az), (bx, bz) = rc[max(j - 1, 0)], rc[min(j + 1, m - 1)]
        d = math.hypot(bx - ax, bz - az) or 1.0
        out.append((ra[j] + ((x - rc[j][0]) * (bx - ax) + (z - rc[j][1]) * (bz - az)) / d) % L)
    return out


BANK_REACH = 8.0                # Phase 22a: the drawn road's side slope is measured this far either side of the centreline
BANK_LEVEL = 6.0                # ... on the ground level within this of the profile (a deck or the ground below is not the road)


def arc_height(lap: Lap, heights: Sequence[float], segments=None, camber: bool = True, spacing: float = 10.0,
               max_units: float = MAX_CAMBER_UNITS, ground=None) -> HeightFn:
    """The collision's height at an arcade (x, z) (Phase 16): the arc profile at the arc of the point's projection onto
    the nearest point of the `spacing`-unit centreline (its true arc: `centreline_arcs`), plus, with `camber`, the slice
    normal's lateral slope (`right_slopes`' formula, the lap centre nearest that centreline point) times the distance to
    the right of the centreline point's own direction, clamped to ±max_units. No 2-D projection onto lap-order
    neighbours: the lap order zigzags through side-by-side strips and that projection stepped up to 20 units on Diablo
    Canyon (the player climbed in steps); no lap-order direction for the lateral (it flips on those strips).
    With `ground` (the SaturnCourse, or its ground WorldQuads; Phase 22a), the side slope is the drawn road's: the
    ground mesh BANK_REACH units either side of each centreline point (one side against the centre where the other is a
    hole), averaged with its two neighbours; the slice normal only where the mesh has no level there (the normals missed the drawn banking by up to 5 degrees)."""
    from vrtools.convert.geometry import normal_to_arcade
    from vrtools.convert.lap import centreline
    pts = centreline(lap, spacing=spacing)
    n = len(pts)
    arc_h = _arc_profile(lap, heights)
    arcs = centreline_arcs(lap, pts)
    cs = lap.centres
    dirs, slopes = [], []
    for k in range(n):
        (ax, az), (bx, bz) = pts[k - 1], pts[(k + 1) % n]
        d = math.hypot(bx - ax, bz - az) or 1.0
        dx, dz = (bx - ax) / d, (bz - az) / d
        dirs.append((dx, dz))
        slope = 0.0
        if camber and segments is not None:
            x, z = pts[k]
            j = min(range(len(cs)), key=lambda i: (cs[i][0] - x) ** 2 + (cs[i][1] - z) ** 2)
            nx, ny, nz = normal_to_arcade(*segments[lap.order[j]].normal)
            if ny > 0.1:
                slope = -(nx * dz + nz * -dx) / ny                  # right-hand lateral (dz, -dx): height per unit to the right
        slopes.append(slope)
    mesh = mesh_heights(_ground_quads(ground)) if camber and ground is not None else None
    if camber and ground is not None:
        drawn = []
        for k in range(n):
            (x, z), (dx, dz), ref = pts[k], dirs[k], arc_h(arcs[k])
            ends = []
            for lat in (-BANK_REACH, 0.0, BANK_REACH):
                near = [v for v in mesh(x + lat * dz, z - lat * dx) if abs(v - ref) < BANK_LEVEL]
                ends.append(min(near, key=lambda v: abs(v - ref)) if near else None)
            left, mid, right = ends
            if left is not None and right is not None:
                drawn.append((right - left) / (2 * BANK_REACH))
            elif mid is not None and (left is not None or right is not None):     # a hole on one side: the other half
                drawn.append((right - mid) / BANK_REACH if right is not None else (mid - left) / BANK_REACH)
            else:
                drawn.append(None)
        for k in range(n):
            got = [drawn[(k + j) % n] for j in (-1, 0, 1) if drawn[(k + j) % n] is not None]
            if got:
                slopes[k] = sum(got) / len(got)

    def estimate(k: int, along: float, lateral: float) -> float:
        base = arc_h(arcs[k] + max(-spacing, min(spacing, along)))     # the point's true arc (centreline_arcs)
        t = max(-1.0, min(1.0, along / spacing))                         # Phase 22a: the slope blends towards the
        slope = slopes[k] + abs(t) * (slopes[(k + (1 if t > 0 else -1)) % n] - slopes[k])   # neighbour (no step at the
        return base + max(-max_units, min(max_units, slope * lateral))  # boundary between two points' regions)

    resid = None
    if camber and ground is not None:                # Phase 22a rework: the drawn ground across the full width, rows
        sub, sdirs, sest = [], [], []                 # every spacing / MESH_ROWS along the lap
        for k in range(n):
            (x0, z0), (x1, z1) = pts[k], pts[(k + 1) % n]
            (u0, v0), (u1, v1) = dirs[k], dirs[(k + 1) % n]
            for q in range(MESH_ROWS):
                f = q / MESH_ROWS
                u, v = u0 + f * (u1 - u0), v0 + f * (v1 - v0)
                l = math.hypot(u, v) or 1.0
                sub.append((x0 + f * (x1 - x0), z0 + f * (z1 - z0))); sdirs.append((u / l, v / l)); sest.append((k, f * spacing))
        resid = _residuals(mesh, len(sub), sub, sdirs, lambda i, lat: estimate(sest[i][0], sest[i][1], lat))

    def in_frame(k: int, x: float, z: float) -> tuple[float, float]:
        """The height seen from centreline point k's frame, and the point's along offset in it."""
        dx, dz = dirs[k]
        along = (x - pts[k][0]) * dx + (z - pts[k][1]) * dz
        lateral = (x - pts[k][0]) * dz - (z - pts[k][1]) * dx
        y = estimate(k, along, lateral)
        u = (k + max(-1.0, min(1.0, along / spacing))) * MESH_ROWS          # the row position (fractional)
        i0 = math.floor(u); f = u - i0
        rows = len(resid)
        r0 = _lateral_interp(resid[i0 % rows], lateral)
        r1 = _lateral_interp(resid[(i0 + 1) % rows], lateral)
        return y + r0 + f * (r1 - r0), along

    def height(x: float, z: float, near_arc: float | None = None) -> float:
        """`near_arc` (Phase 22g): the point's own lap arc, when known; only race-line points within NEAR_ARC_WINDOW
        of it are taken (where the lap crosses itself the nearest point can lie on the other deck)."""
        if near_arc is None:
            k = min(range(n), key=lambda i: (pts[i][0] - x) ** 2 + (pts[i][1] - z) ** 2)
        else:
            L = lap.length
            near = [i for i in range(n) if abs((arcs[i] - near_arc + L / 2) % L - L / 2) <= NEAR_ARC_WINDOW] or range(n)
            k = min(near, key=lambda i: (pts[i][0] - x) ** 2 + (pts[i][1] - z) ** 2)
        if resid is None:
            dx, dz = dirs[k]
            along = (x - pts[k][0]) * dx + (z - pts[k][1]) * dz
            return estimate(k, along, (x - pts[k][0]) * dz - (z - pts[k][1]) * dx)
        total = weight = 0.0                              # 22a review: the frames of k and its two neighbours, each
        for i in range(k - 2, k + 3):                     # weighted by how near the point is along it (the frames
            y, along = in_frame(i % n, x, z)              # disagree between points on a curve; 20-28 out the height
            w = max(0.0, 1.0 - abs(along) / spacing)      # stepped 1.2-2.4 units with one frame)
            total += w * y; weight += w
        return total / weight if weight else in_frame(k, x, z)[0]

    height.takes_arc = True
    return height


NEAR_ARC_WINDOW = 150.0         # Phase 22g: a point with a lap arc looks for its race-line point within this of it
MESH_STEP = 2.0                 # Phase 22a rework: the drawn ground is sampled every 2 units across the road ...
MESH_REACH = 40.0               # ... out to here either side of the centreline
MESH_START = 3.0                # the surface is picked up at the level within this of the estimate nearest the centre ...
MESH_FOLLOW = 2.0               # ... and followed outward, each sample the level within this of the previous one (45 deg; a deck
                                # above or the ground below is not connected to the road surface and is never taken)
MESH_GAP = 4                    # at most this many samples (8 units) of holes are crossed while following
MESH_ROWS = 4                   # residual rows per centreline step (2.5 units at the 10-unit spacing)
MESH_ALONG = 8                  # a sample with no ground takes its lateral's value from tracked rows within this many rows
MESH_LATS = np.arange(-MESH_REACH, MESH_REACH + 0.001, MESH_STEP)


def _residuals(mesh, n, pts, dirs, estimate) -> np.ndarray:
    """(n, len(MESH_LATS)): the drawn ground minus the estimate at each centreline point and lateral, the surface
    followed outward from the centre; samples off the followed surface (holes, steep walls) interpolated across,
    then along the lap from neighbouring points; 0 where a whole lap has nothing."""
    m = len(MESH_LATS)
    r = np.full((n, m), np.nan)
    mid = m // 2
    for k in range(n):
        (x, z), (dx, dz) = pts[k], dirs[k]
        est = [estimate(k, float(lat)) for lat in MESH_LATS]
        levels = [mesh(x + lat * dz, z - lat * dx) for lat in MESH_LATS]
        start = None                                     # the sample nearest the centre with a level near the estimate
        for off in range(mid + 1):
            for j in (mid - off, mid + off):
                near = [v for v in levels[j] if abs(v - est[j]) <= MESH_START] if 0 <= j < m else []
                if near:
                    start = (j, min(near, key=lambda v: abs(v - est[j])))
                    break
            if start:
                break
        if start is None:
            continue
        j0, y0 = start
        r[k, j0] = y0 - est[j0]
        for step in (1, -1):
            prev, j, gap = y0, j0 + step, 1
            while 0 <= j < m:
                near = [v for v in levels[j] if abs(v - prev) <= MESH_FOLLOW * gap]   # the same steepest slope across holes
                if near:
                    prev = min(near, key=lambda v: abs(v - prev))
                    r[k, j] = prev - est[j]
                    gap = 1
                elif gap >= MESH_GAP:                     # lost: a wider hole or a cliff; what lies beyond is not this
                    break                                 # surface (Metropolis: another deck 16 units up across a gap)
                else:
                    gap += 1                              # a hole: skip it, keep following from the last level
                j += step
    tracked = ~np.isnan(r)                                # along first: a gap takes the same lateral of the rows within
    filled = r.copy()                                     # MESH_ALONG points either side (the ground's holes are patchy
    for j in range(m):                                    # across the road, the surface runs on along it)
        col = tracked[:, j]
        if not col.any():
            continue
        idx = np.flatnonzero(col)
        for k in np.flatnonzero(~col):
            d = (idx - k + n // 2) % n - n // 2           # signed cyclic distance to each tracked row
            before, after = d[d < 0], d[d > 0]
            if len(before) and len(after) and -before.max() <= MESH_ALONG and after.min() <= MESH_ALONG:
                a, b = (k + before.max()) % n, (k + after.min()) % n
                t = -before.max() / (after.min() - before.max())
                filled[k, j] = r[a, j] * (1 - t) + r[b, j] * t
    r = filled
    for k in range(n):                                    # across: interpolate the gaps, hold the ends
        ok = ~np.isnan(r[k])
        if ok.any():
            r[k] = np.interp(np.arange(m), np.flatnonzero(ok), r[k][ok])
    rows = ~np.isnan(r[:, 0])
    if not rows.any():
        return np.zeros((n, m))
    known = np.flatnonzero(rows)                          # along: rows with nothing take their neighbours' (cyclic)
    for k in np.flatnonzero(~rows):
        prev = known[known < k].max() if (known < k).any() else known.max() - n
        nxt = known[known > k].min() if (known > k).any() else known.min() + n
        t = (k - prev) / (nxt - prev)
        r[k] = r[prev % n] * (1 - t) + r[nxt % n] * t
    return r


def _lateral_interp(row: np.ndarray, lateral: float) -> float:
    return float(np.interp(lateral, MESH_LATS, row))
