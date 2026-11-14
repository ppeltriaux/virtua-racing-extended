"""Phase 22b: the HUD map's outline for a converted course.

The game draws the in-race map as one section, car-centred and heading-up (Phase 14 recon), whose first object is the
course outline: on the originals a flat strip about 30 units wide along the road, at y 0.3, normals (0, -1, 0), one of
three fixed polygon-ROM objects (the object lists at 0x2e0040 / 0x2e0050 / 0x2e0060: Big Forest's, Bay Bridge's,
Acropolis's) picked by data index at boot 0xfeac10. A converted course drew its host's outline around its own car, so
the cross and the markers never sat on it. Here the outline is built from the course's own centreline (arcade
coordinates, as the road lines the markers follow) and encoded in the originals' style; the directory's `mapobj`
routine hands it to the map entity."""

from __future__ import annotations

import math
import struct

from vrtools.arcade.polyrom import ObjectLayout, Quad, encode_object

OUTLINE_WIDTH = 30.0      # the originals' strips: short sides 25-30 units
OUTLINE_Y = 0.3           # Big Forest's outline lies at y 0.3-0.35, 30-43 units under its road
OUTLINE_DROP = 1.0        # Phase 25: with the road's height given, the strip lies this far under its lowest point nearby
OUTLINE_TOL = 4.0         # the strip follows the centreline within this (Douglas-Peucker on the closed loop)
MITER_MAX = 1.4           # a sharp corner's joint is held to this share of the width (hairpins)
NORMAL = (0.0, -1.0, 0.0)


def _simplify(pts: list[tuple[float, float]], tol: float) -> list[int]:
    """Indices of a closed loop's points kept by Douglas-Peucker (the loop split at its first point and the point
    farthest from it)."""
    n = len(pts)
    far = max(range(n), key=lambda k: math.dist(pts[0], pts[k]))
    keep = {0, far}

    def dp(i: int, j: int) -> None:                      # the open run i..j (j may wrap past n)
        a, b = pts[i % n], pts[j % n]
        best, at = 0.0, None
        L = math.dist(a, b) or 1e-9
        for k in range(i + 1, j):
            p = pts[k % n]
            d = abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / L
            if d > best:
                best, at = d, k
        if at is not None and best > tol:
            keep.add(at % n)
            dp(i, at)
            dp(at, j)

    dp(0, far)
    dp(far, n)
    return sorted(keep)


def outline_quads(centreline: list[tuple[float, float]], width: float = OUTLINE_WIDTH, tol: float = OUTLINE_TOL,
                  extra: list[list[tuple[float, float]]] = (), floor=None) -> list[Quad]:
    """A strip `width` wide along the closed centreline (arcade x, z), one quad per simplified segment; each
    quad's corners are (left i, right i, right i+1, left i+1), so neighbouring quads share an edge (one record each).
    Phase 22g: each `extra` polyline (a pit lane) adds an open strip of its own after the loop's.
    Phase 25: the map section is drawn in perspective from above and sorted by depth, so a marker is hidden where its
    car is lower than the strip. Without `floor` the strip is flat at OUTLINE_Y (the originals', whose roads lie well
    above it); with `floor(x, z)` (the lowest height a car can have about a point) each joint lies OUTLINE_DROP under
    the lowest floor of the two spans it joins, so the strip follows the road from just below."""
    pts = list(centreline)
    idx = _simplify(pts, tol)
    m, n = len(idx), len(pts)
    ys = None
    if floor is not None:
        f = [floor(x, z) for x, z in pts]
        ys = []
        for k in range(m):
            a, b = idx[k - 1], idx[(k + 1) % m]
            span = range(a, b + 1) if a < b else list(range(a, n)) + list(range(0, b + 1))
            ys.append(min(f[i] for i in span) - OUTLINE_DROP)
    out = _strip([pts[i] for i in idx], width, closed=True, ys=ys)
    for line in extra:
        if len(line) >= 2:
            line = list(line)
            kept = _simplify_open(line, tol)
            ys = None
            if floor is not None:
                f = [floor(x, z) for x, z in line]
                at = [line.index(p) for p in kept]
                ys = [min(f[at[max(k - 1, 0)]:at[min(k + 1, len(at) - 1)] + 1]) - OUTLINE_DROP for k in range(len(at))]
            out += _strip(kept, width, closed=False, ys=ys)
    return out


def _simplify_open(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker on an open polyline (both ends kept)."""
    keep = {0, len(pts) - 1}

    def dp(i: int, j: int) -> None:
        a, b = pts[i], pts[j]
        L = math.dist(a, b) or 1e-9
        best, at = 0.0, None
        for k in range(i + 1, j):
            p = pts[k]
            d = abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / L
            if d > best:
                best, at = d, k
        if at is not None and best > tol:
            keep.add(at)
            dp(i, at)
            dp(at, j)

    dp(0, len(pts) - 1)
    return [pts[k] for k in sorted(keep)]


def _strip(v: list[tuple[float, float]], width: float, closed: bool, ys: list[float] | None = None) -> list[Quad]:
    """The strip's quads along `v` (mitred joints; an open strip's ends square to its first and last segments), each
    joint at its height in `ys` (flat at OUTLINE_Y without)."""
    m = len(v)
    left, right = [], []
    for k in range(m):
        a, b, c = v[k - 1], v[k], v[(k + 1) % m]
        if not closed and k == 0:
            a = (2 * b[0] - c[0], 2 * b[1] - c[1])
        if not closed and k == m - 1:
            c = (2 * b[0] - a[0], 2 * b[1] - a[1])
        d1 = (b[0] - a[0], b[1] - a[1]); d2 = (c[0] - b[0], c[1] - b[1])
        l1 = math.hypot(*d1) or 1e-9; l2 = math.hypot(*d2) or 1e-9
        n1 = (-d1[1] / l1, d1[0] / l1); n2 = (-d2[1] / l2, d2[0] / l2)
        nx, nz = n1[0] + n2[0], n1[1] + n2[1]
        ln = math.hypot(nx, nz)
        if ln < 1e-6:
            nx, nz, ln = n2[0], n2[1], 1.0
        nx, nz = nx / ln, nz / ln
        cos_half = max(1e-6, nx * n2[0] + nz * n2[1])
        s = min(MITER_MAX, 1.0 / cos_half) * width / 2
        y = OUTLINE_Y if ys is None else ys[k]
        left.append((b[0] + nx * s, y, b[1] + nz * s))
        right.append((b[0] - nx * s, y, b[1] - nz * s))
    return [Quad((left[k], right[k], right[(k + 1) % m], left[(k + 1) % m]), NORMAL, 0, 0) for k in range(m if closed else m - 1)]


def encode_outline(quads: list[Quad], tex: int) -> tuple[bytes, ObjectLayout]:
    """Polygon-ROM bytes for the outline, all quads on colour entry `tex`, with the originals' outline flags: 0x20000
    and z mode 1 on every record, 0x800000 on a chain's first record, 0x1000000 on the drawing ones (Big Forest:
    0x825501 / 0x1025601), no back-face cull."""
    blob, layout = encode_object([Quad(q.p, q.normal, q.flags, tex) for q in quads], tex_start=tex, no_cull=True)
    out = bytearray(blob)
    for off in range(24, len(out), 40):                  # after the two seed points (6 floats)
        f = struct.unpack_from("<I", out, off)[0]
        if not f & 3:
            continue
        f = (f & ~0xC00) | 0x400 | 0x20000 | 0x4000 | (0x800000 if (f >> 8) & 3 == 0 else 0x1000000)
        struct.pack_into("<I", out, off, f)
    return bytes(out), layout
