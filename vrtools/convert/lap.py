"""Order the Saturn road slices into a lap.

The TRCK segment table stores slices in lap-ordered *runs* joined by jumps, and the slices tile the road as a 2-D
mesh (strips side by side, fans at the kerbs), so indices alone do not give the lap. `order_slices` builds the
shared-edge graph of the slices, cuts the edges crossing the start line, takes Dijkstra distances from the start
as the arc length and the shortest path back to the slice just behind the start line as the route (a fork keeps
its shorter branch). A lap that does not close, or leaves more than 2 % of the slices unreachable, is an error.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from vrtools.convert.geometry import SCALE, ConvertError, to_arcade
from vrtools.saturn.course import SaturnCourse, Segment

Point2 = tuple[float, float]


@dataclass
class Lap:
    order: list[int]              # slice indices in driving order, starting at `start`
    arc: list[float]              # cumulative arc length (arcade units) at each slice centre, arc[0] = 0
    length: float                 # lap length (arcade units), closing the loop
    start: int
    centres: list[Point2] = field(default_factory=list)   # arcade (x, z) of each ordered slice centre
    skipped: list[list[int]] = field(default_factory=list)  # runs left out (side lanes), as slice index lists
    route: list[int] = field(default_factory=list)        # one chain of slices from the start round to the start line
    route_arc: list[float] = field(default_factory=list)  # arc length (arcade units) at each route slice centre


def runs(sat: SaturnCourse, max_gap: float = 2.0) -> list[list[int]]:
    """Maximal runs of consecutive slice indices whose centres are within max_gap Saturn units."""
    out: list[list[int]] = []
    prev: Segment | None = None
    for s in sat.segments:
        c = s.centre
        if c is None:
            prev = None
            continue
        if prev is not None and prev.index == s.index - 1 and math.dist(prev.centre, c) < max_gap:
            out[-1].append(s.index)
        else:
            out.append([s.index])
        prev = s
    return out


def _poly(s: Segment) -> list[Point2]:
    return list(s.corners())


def _seg_dist(p: Point2, a: Point2, b: Point2) -> float:
    ax, az = a; bx, bz = b; px, pz = p
    dx, dz = bx - ax, bz - az
    l2 = dx * dx + dz * dz
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / l2))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


def poly_distance(p: list[Point2], q: list[Point2]) -> float:
    """Minimum distance between two convex polygons' boundaries (0 when they touch or overlap)."""
    best = math.inf
    for poly_a, poly_b in ((p, q), (q, p)):
        n = len(poly_b)
        for v in poly_a:
            for k in range(n):
                best = min(best, _seg_dist(v, poly_b[k], poly_b[(k + 1) % n]))
    return best


def _edges(poly: list[Point2]) -> list[tuple[Point2, Point2]]:
    return [(poly[k], poly[(k + 1) % len(poly)]) for k in range(len(poly))]


def _across_edges(poly: list[Point2]) -> list[int]:
    """Indices of the two across-road edges of a slice polygon: the opposite pair with the greater total length
    (slices are wider than long). A triangle returns all three edges."""
    e = _edges(poly)
    if len(e) != 4:
        return list(range(len(e)))
    length = lambda k: math.dist(*e[k])
    return [0, 2] if length(0) + length(2) >= length(1) + length(3) else [1, 3]


def edge_overlap(a: tuple[Point2, Point2], b: tuple[Point2, Point2], tolerance: float) -> float:
    """Length of the overlap of two nearly collinear edges (0 if they are more than `tolerance` apart or not
    parallel within ~15 degrees)."""
    (ax, az), (bx, bz) = a
    dx, dz = bx - ax, bz - az
    n = math.hypot(dx, dz)
    if n < 1e-9:
        return 0.0
    ux, uz = dx / n, dz / n
    (cx, cz), (ex, ez) = b
    m = math.hypot(ex - cx, ez - cz)
    if m < 1e-9 or abs((ex - cx) * ux + (ez - cz) * uz) / m < 0.96:
        return 0.0
    lat = max(abs((cx - ax) * -uz + (cz - az) * ux), abs((ex - ax) * -uz + (ez - az) * ux))
    if lat > tolerance:
        return 0.0
    t0, t1 = sorted(((cx - ax) * ux + (cz - az) * uz, (ex - ax) * ux + (ez - az) * uz))
    return max(0.0, min(n, t1) - max(0.0, t0))


TOUCH = 0.5          # Saturn units: polygons this close are adjacent even without a shared edge (T-junctions, overlaps)


def order_slices(sat: SaturnCourse, start_slice: int = 0, tolerance: float = 0.35, forward: bool = True,
                 min_coverage: float = 0.98, gap_reach: float = 8.0, cut_width: float = 8.0,
                 report: dict | None = None, direction: tuple[float, float] | None = None) -> Lap:
    """Order the slices by road distance from the start.

    The slices tile the road surface two-dimensionally (strips side by side, fans of triangles at merges), so
    they are treated as a graph: two slices are adjacent when they share an edge (collinear within `tolerance`
    Saturn units, overlapping by at least 0.2); gaps between components are bridged by the nearest centre pair
    within gap_reach. The loop is cut at the start line: every adjacency crossing the line through the start
    slice's centre across the direction of travel, within cut_width Saturn units of it sideways (side lanes
    included), is removed, and the cut is checked (the slices just behind the line must carry the largest
    distances; a leak doubles the width, up to 4 times). Dijkstra distance from the start slice, measured centre
    to centre, is then the lap coordinate, and the shortest-path chain from the start to the slice just behind
    the start line is the `route`: one slice per step through the strips, which at a fork in the Saturn layout
    (Amazon Falls, Bay Bridge) follows the shorter branch — the arcade has no forks — and which the height profile
    and the road tables follow: every slice of the road, side lanes included, gets a position, and the order is
    the sort by that distance. Direction of travel: toward the slice with the next index (forward=True) or away
    from it; on every Saturn course inspected slice 0 → slice 1 heads the direction of travel. The start slice is
    moved to the first run of 5 or more slices when its own run is shorter (Bay Bridge's slice 0 is a side slice).
    Fewer than min_coverage of the usable slices reachable from the start, or no slice just behind the start line
    reachable (the lap does not close), is a ConvertError naming the longest disconnected run of slices."""
    import heapq
    segs = {s.index: s for s in sat.segments if s.corners() is not None}
    if start_slice not in segs:
        raise ConvertError(f"start slice {start_slice} has no polygon")
    all_runs = runs(sat)
    run_of = {i: rr for rr in all_runs for i in rr}
    if direction is None and len(run_of[start_slice]) < 5:
        long_runs = [rr for rr in all_runs if len(rr) >= 5]
        start_slice = (long_runs[0] if long_runs else max(all_runs, key=len))[0]
    polys = {i: _poly(s) for i, s in segs.items()}
    centre = lambda i: segs[i].centre
    cell = 4.0
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, p in polys.items():
        keys = {(int(x // cell), int(z // cell)) for x, z in p}
        for key in keys:
            buckets.setdefault(key, []).append(i)
    # adjacency by shared edges
    adj: dict[int, dict[int, float]] = {i: {} for i in segs}
    for key, members in buckets.items():
        cand = set(members)
        kx, kz = key
        for ix in (kx - 1, kx, kx + 1):
            for iz in (kz - 1, kz, kz + 1):
                cand.update(buckets.get((ix, iz), ()))
        for i in members:
            ei = _edges(polys[i])
            for j in cand:
                if j <= i or j in adj[i]:
                    continue
                ej = _edges(polys[j])
                if any(edge_overlap(a, b, tolerance) >= 0.2 for a in ei for b in ej) or poly_distance(polys[i], polys[j]) <= TOUCH:
                    w = math.dist(centre(i), centre(j))
                    adj[i][j] = w
                    adj[j][i] = w
    # bridge gaps between components (nearest centre pairs within gap_reach), repeatedly
    def components() -> list[set[int]]:
        seen: set[int] = set()
        out = []
        for i in segs:
            if i in seen:
                continue
            stack = [i]
            comp = set()
            while stack:
                v = stack.pop()
                if v in comp:
                    continue
                comp.add(v)
                stack.extend(adj[v])
            seen |= comp
            out.append(comp)
        return out
    comps = components()
    if report is not None:
        report["components"] = sorted((len(c) for c in comps), reverse=True)
        report["bridges"] = []
    while len(comps) > 1:
        main = max(comps, key=len)
        best = None
        for comp in comps:
            if comp is main:
                continue
            for i in comp:
                cx, cz = centre(i)
                for j in main:
                    d = math.dist((cx, cz), centre(j))
                    if d <= gap_reach and (best is None or d < best[0]):
                        best = (d, i, j)
        if best is None:
            break
        d, i, j = best
        adj[i][j] = d
        adj[j][i] = d
        if report is not None:
            report["bridges"].append((round(d, 2), i, j))
        comps = components()
    # direction and the cut
    sx, sz = centre(start_slice)
    if direction is not None:                        # explicit direction of travel at the start (Saturn frame)
        tx, tz = direction
    else:
        nxt = start_slice + 1 if start_slice + 1 in segs else None
        step = (centre(nxt)[0] - sx, centre(nxt)[1] - sz) if nxt is not None else (0.0, 0.0)
        if math.hypot(*step) >= 0.5:                 # index order is the direction of travel inside a run (BF, Alpine…)
            tx, tz = step
        else:
            # the Surfers files store slices in no useful order and open with kerb triangles: move the start to the
            # first proper quad slice (two long edges at least 1.5 × the short ones) and take its own axis (between
            # the midpoints of the long edges) with the sign that runs the lap clockwise (the course's centroid on
            # the right), as every Virtua Racing course is driven
            def shape(i):
                e = sorted((math.dist(*ed) for ed in _edges(polys[i])), reverse=True)
                return len(e) == 4 and e[1] >= 1.5 * e[2] and e[1] >= 1.0
            start_slice = next((i for i in sorted(segs) if i >= start_slice and shape(i)), start_slice)
            sx, sz = centre(start_slice)
            poly = polys[start_slice]
            edges = sorted(_edges(poly), key=lambda e: -math.dist(*e))[:2]
            (m1, m2) = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in edges]
            tx, tz = m2[0] - m1[0], m2[1] - m1[1]
            cx = sum(centre(i)[0] for i in segs) / len(segs)
            cz = sum(centre(i)[1] for i in segs) / len(segs)
            if tx * (cz - sz) - tz * (cx - sx) > 0:  # centroid on the left: flip
                tx, tz = -tx, -tz
    n = math.hypot(tx, tz)
    tx, tz = (tx / n, tz / n) if n > 1e-9 else (0.0, 1.0)
    if not forward and direction is None:
        tx, tz = -tx, -tz
    side = lambda i: (centre(i)[0] - sx) * tx + (centre(i)[1] - sz) * tz
    lateral = lambda i: abs((centre(i)[0] - sx) * -tz + (centre(i)[1] - sz) * tx)
    import heapq as _hq

    def run_dijkstra(width: float) -> tuple[dict[int, float], set[tuple[int, int]], dict[int, int]]:
        cut = set()
        for i in segs:
            if lateral(i) > width + 3.0:
                continue
            si = side(i) if i != start_slice else 0.0
            for j in adj[i]:
                sj = side(j) if j != start_slice else 0.0
                crosses = (si < 0 <= sj) or (sj < 0 <= si)
                if crosses and min(lateral(i), lateral(j)) <= width:
                    cut.add((min(i, j), max(i, j)))
        dist = {start_slice: 0.0}
        pred: dict[int, int] = {}
        heap = [(0.0, start_slice)]
        while heap:
            d, i = _hq.heappop(heap)
            if d > dist.get(i, math.inf):
                continue
            for j, w in adj[i].items():
                if (min(i, j), max(i, j)) in cut:
                    continue
                nd = d + w
                if nd < dist.get(j, math.inf):
                    dist[j] = nd
                    pred[j] = i
                    _hq.heappush(heap, (nd, j))
        return dist, cut, pred

    width = cut_width
    for attempt in range(5):
        dist, cut, pred = run_dijkstra(width)
        behind = [i for i in segs if i in dist and -3.0 <= side(i) < 0 and lateral(i) <= 3.0]
        # a loop whose only edge-sharing junction is the start line is one component before the cut and two after
        # it: bridge from the reached side to the nearest unreached slice (within gap_reach, not across the line)
        for _ in range(8):
            if behind:
                break
            best = None
            for i in dist:
                cx, cz = centre(i)
                for key in {(int(cx // cell) + dx, int(cz // cell) + dz) for dx in (-2, -1, 0, 1, 2) for dz in (-2, -1, 0, 1, 2)}:
                    for j in buckets.get(key, ()):
                        if j in dist or j in adj[i]:
                            continue
                        d = math.dist((cx, cz), centre(j))
                        if d <= gap_reach and (side(i) < -3.0 or side(j) < -3.0 or side(i) > 3.0 or side(j) > 3.0 or lateral(i) > cut_width) \
                                and (best is None or d < best[0]):
                            best = (d, i, j)
            if best is None:
                break
            d, i, j = best
            adj[i][j] = d
            adj[j][i] = d
            if report is not None:
                report.setdefault("bridges", []).append((round(d, 2), i, j))
            dist, cut, pred = run_dijkstra(width)
            behind = [i for i in segs if i in dist and -3.0 <= side(i) < 0 and lateral(i) <= 3.0]
        far = max(dist.values()) if dist else 0.0
        leak = behind and min(dist[i] for i in behind) < 0.8 * far
        if report is not None:
            report.setdefault("cuts", []).append((width, len(cut), bool(leak)))
        if not leak:
            break
        width *= 2
    else:
        raise ConvertError(f"the start-line cut at slice {start_slice} leaks even {width / 2:.0f} units wide: a side road bypasses the start")
    usable = len(segs)
    missing = sorted(i for i in segs if i not in dist)
    longest: list[int] = []
    run: list[int] = []
    for i in missing:
        run = run + [i] if run and i == run[-1] + 1 else [i]
        if len(run) > len(longest):
            longest = run
    where = f" (slices {longest[0]}–{longest[-1]} are disconnected)" if longest else ""
    if len(dist) < min_coverage * usable:
        raise ConvertError(f"only {len(dist)} of {usable} slices are reachable from slice {start_slice} on the road graph{where}")
    if not behind:
        raise ConvertError(f"the lap does not close: no slice just behind the start line is reachable from slice "
                           f"{start_slice}; the road ends {far * SCALE:.0f} units out{where}")
    order = sorted(dist, key=lambda i: (dist[i], i))
    skipped = [rr for rr in all_runs if not any(i in dist for i in rr)]
    # the route: shortest path from the start to the slice just behind the start line
    end = max(behind, key=lambda i: dist[i])
    route = [end]
    while route[-1] != start_slice:
        route.append(pred[route[-1]])
    route.reverse()
    route_arc = [dist[i] * SCALE for i in route]
    centres = []
    for i in order:
        cx, cz = centre(i)
        X, _, Z = to_arcade(cx, 0.0, cz)
        centres.append((X, Z))
    arc = [dist[i] * SCALE for i in order]
    length = route_arc[-1] + math.dist(centre(route[-1]), (sx, sz)) * SCALE     # the route's end, not a dead-end stub
    return Lap(order, arc, length, start_slice, centres, skipped, route, route_arc)


def arc_of(lap: Lap, x: float, z: float) -> float:
    """Arc length (arcade units) of the lap centre nearest to an arcade (x, z)."""
    best = min(range(len(lap.centres)), key=lambda k: (lap.centres[k][0] - x) ** 2 + (lap.centres[k][1] - z) ** 2)
    return lap.arc[best]


def centreline(lap: Lap, spacing: float = 10.0, bin_size: float = 10.0, window: int = 3) -> list[Point2]:
    """A smooth centreline of the lap (arcade x, z) resampled every `spacing` units of arc from the start.

    The route zigzags through side-by-side strips, so its centres are first averaged per bin of arc length
    (bin_size), the bins are smoothed with a cyclic moving average of `window` bins, and the closed polyline
    through the bin points is resampled at even arc steps."""
    if not lap.route:
        raise ConvertError("the lap has no route")
    pos = {i: k for k, i in enumerate(lap.order)}
    nbins = max(3, int(round(lap.length / bin_size)))
    sums = [[0.0, 0.0, 0] for _ in range(nbins)]
    for i, a in zip(lap.route, lap.route_arc):
        x, z = lap.centres[pos[i]]
        b = min(nbins - 1, int(a // bin_size))
        sums[b][0] += x
        sums[b][1] += z
        sums[b][2] += 1
    pts: list[Point2 | None] = [(sx / n, sz / n) if n else None for sx, sz, n in sums]
    known = [k for k, p in enumerate(pts) if p is not None]
    if len(known) < 3:
        raise ConvertError("the route is too short for a centreline")
    for k in range(nbins):                                   # fill empty bins by cyclic interpolation
        if pts[k] is not None:
            continue
        prev = max((j for j in known if j < k), default=known[-1])
        nxt = min((j for j in known if j > k), default=known[0])
        a_prev = prev if prev < k else prev - nbins
        a_next = nxt if nxt > k else nxt + nbins
        t = 0.0 if a_next == a_prev else (k - a_prev) / (a_next - a_prev)
        pts[k] = (pts[prev][0] + t * (pts[nxt][0] - pts[prev][0]), pts[prev][1] + t * (pts[nxt][1] - pts[prev][1]))
    half = window // 2
    smooth = []
    for k in range(nbins):
        xs = [pts[(k + d) % nbins][0] for d in range(-half, half + 1)]
        zs = [pts[(k + d) % nbins][1] for d in range(-half, half + 1)]
        smooth.append((sum(xs) / len(xs), sum(zs) / len(zs)))
    # resample the closed polyline at even arc steps
    seg_len = [math.dist(smooth[k], smooth[(k + 1) % nbins]) for k in range(nbins)]
    total = sum(seg_len)
    n_out = max(2, int(round(total / spacing)))
    step = total / n_out
    out = []
    k, carry = 0, 0.0                                        # position: segment k, distance into it
    for m in range(n_out):
        target = m * step
        while carry + seg_len[k] < target - 1e-9:
            carry += seg_len[k]
            k = (k + 1) % nbins
        t = 0.0 if seg_len[k] == 0 else (target - carry) / seg_len[k]
        a, b = smooth[k], smooth[(k + 1) % nbins]
        out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return out
