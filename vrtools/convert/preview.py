"""A converted course's select-screen picture (Phase 21, design docs/superpowers/specs/2026-11-01-select-previews-design.md):
a top-down low-polygon landscape like the originals' — a jittered triangle mesh, low along the road and rising away from
it, each facet flat-shaded and coloured by height from the course's own Saturn terrain (group 1) — the Saturn's water
polygons, the exact road (white edges, black tarmac, a yellow start mark), the orange frame and the name in the
originals' lettering. numpy only; deterministic (fixed seeds). Pascal picked the look from the spike `poly3` (cell 9 px).
Call inside the course's `placed(...)` context, as the other conversions."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np

from vrtools.arcade.lettering import draw_name
from vrtools.convert.collision import is_water
from vrtools.convert.geometry import course_quads
from vrtools.convert.lap import centreline

W, H = 128, 168                 # the panel
MAP_W, MAP_H = 112, 140         # the area the road is fitted into (above the name)
MARGIN = 9                      # half the fit's slack: the road keeps this far from the map area's edge
SS = 4                          # supersampling
CELL = 9.0                      # mesh spacing (panel px)
MESH_SEED = 20
NOISE = ((40, 0.55), (18, 0.30), (8, 0.15))    # (scale px, amplitude) per octave; octave k is seeded k
LIGHT = (-0.45, -0.55, 0.70)
ROAD_EDGE, ROAD_TARMAC = 5.5, 3.8              # stroke widths (px)
EDGE_RGB, TARMAC_RGB, START_RGB = (235, 235, 235), (20, 20, 20), (245, 225, 40)
FRAME = (232, 120, 24)
NAME_RIGHT, NAME_BOTTOM = 124, 164


def fit(cl: list[tuple[float, float]]) -> tuple[float, float, float]:
    """(centre x, centre z, scale) that fits the centreline into the map area."""
    xs = [p[0] for p in cl]; zs = [p[1] for p in cl]
    s = min((MAP_W - 2 * MARGIN) / ((max(xs) - min(xs)) or 1.0), (MAP_H - 2 * MARGIN) / ((max(zs) - min(zs)) or 1.0))
    return (max(xs) + min(xs)) / 2, (max(zs) + min(zs)) / 2, s


def to_panel(x: float, z: float, f: tuple[float, float, float]) -> tuple[float, float]:
    """Arcade (x, z) -> panel pixels (z up -> screen up)."""
    cx, cz, s = f
    return 8 + MAP_W / 2 + (x - cx) * s, 8 + MAP_H / 2 - (z - cz) * s


def _fill(canvas: np.ndarray, pts, rgb) -> None:
    """Even-odd fill of a polygon (supersampled pixel coordinates) at pixel centres."""
    p = np.asarray(pts, float)
    x0, x1 = max(0, int(p[:, 0].min())), min(canvas.shape[1], int(math.ceil(p[:, 0].max())) + 1)
    y0, y1 = max(0, int(p[:, 1].min())), min(canvas.shape[0], int(math.ceil(p[:, 1].max())) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1] + 0.5
    inside = np.zeros(yy.shape, bool)
    for (ax, ay), (bx, by) in zip(p, np.roll(p, -1, 0)):
        if ay == by:
            continue
        cross = ((ay > yy) != (by > yy)) & (xx < ax + (yy - ay) * (bx - ax) / (by - ay))
        inside ^= cross
    canvas[y0:y1, x0:x1][inside] = rgb


def _stroke(canvas: np.ndarray, pts: np.ndarray, width: float, rgb) -> None:
    """A polyline `width` wide (round joins and caps), supersampled coordinates."""
    r = width / 2
    for a, b in zip(pts[:-1], pts[1:]):
        x0, x1 = max(0, int(min(a[0], b[0]) - r)), min(canvas.shape[1], int(max(a[0], b[0]) + r) + 2)
        y0, y1 = max(0, int(min(a[1], b[1]) - r)), min(canvas.shape[0], int(max(a[1], b[1]) + r) + 2)
        if x0 >= x1 or y0 >= y1:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1] + 0.5
        d = b - a
        t = np.clip(((xx - a[0]) * d[0] + (yy - a[1]) * d[1]) / ((d ** 2).sum() or 1.0), 0, 1)
        on = np.hypot(xx - a[0] - t * d[0], yy - a[1] - t * d[1]) <= r
        canvas[y0:y1, x0:x1][on] = rgb


def _value_noise(px: np.ndarray, py: np.ndarray, scale: float, seed: int) -> np.ndarray:
    g = np.random.default_rng(seed).random((64, 64))
    fx, fy = px / scale + 3, py / scale + 3
    x0, y0 = fx.astype(int), fy.astype(int)
    tx, ty = fx - x0, fy - y0
    a = g[y0, x0] * (1 - tx) + g[y0, x0 + 1] * tx
    b = g[y0 + 1, x0] * (1 - tx) + g[y0 + 1, x0 + 1] * tx
    return a * (1 - ty) + b * ty


def _road_distance(px: np.ndarray, py: np.ndarray, road: np.ndarray) -> np.ndarray:
    best = np.full(px.shape, 1e9)
    for a, b in zip(road[:-1], road[1:]):
        d = b - a
        t = np.clip(((px - a[0]) * d[0] + (py - a[1]) * d[1]) / ((d ** 2).sum() or 1.0), 0, 1)
        best = np.minimum(best, np.hypot(px - (a[0] + t * d[0]), py - (a[1] + t * d[1])))
    return best


UPRIGHT = 0.3                   # top view: a face whose normal's height part is under this is a wall, not ground


def _top_view(faces, f, sea, shape) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Phase 90 (a course that is not a Saturn course): `faces` (WorldQuads, arcade y up) seen from straight above on the
    supersampled canvas: per sample the colour of the topmost face that is not upright (UPRIGHT) and whether it is sea (`sea`,
    a predicate on a WorldQuad). Returns (rgb, covered, sea) arrays."""
    h, w = shape
    top = np.full((h, w), -np.inf)
    rgb = np.zeros((h, w, 3)); wet = np.zeros((h, w), bool)
    for q in faces:
        p = np.array(q.p, float)
        n = np.cross(p[2] - p[0], p[1] - p[0]) + np.cross(p[3] - p[0], p[2] - p[0])
        if abs(n[1]) < UPRIGHT * (np.linalg.norm(n) or 1.0):
            continue
        s = np.array([to_panel(v[0], v[2], f) for v in p]) * SS
        is_sea = bool(sea(q))
        for a, b, c in ((0, 1, 2), (0, 2, 3)):
            A, B, C = s[a], s[b], s[c]
            det = (B[0] - A[0]) * (C[1] - A[1]) - (C[0] - A[0]) * (B[1] - A[1])
            if abs(det) < 1e-9:
                continue
            tri = np.array([A, B, C])
            x0, x1 = max(0, int(tri[:, 0].min())), min(w, int(math.ceil(tri[:, 0].max())) + 1)
            y0, y1 = max(0, int(tri[:, 1].min())), min(h, int(math.ceil(tri[:, 1].max())) + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            yy, xx = np.mgrid[y0:y1, x0:x1] + 0.5
            u = ((xx - A[0]) * (C[1] - A[1]) - (C[0] - A[0]) * (yy - A[1])) / det
            v = ((B[0] - A[0]) * (yy - A[1]) - (xx - A[0]) * (B[1] - A[1])) / det
            inside = (u >= 0) & (v >= 0) & (u + v <= 1)
            y = p[a][1] + u * (p[b][1] - p[a][1]) + v * (p[c][1] - p[a][1])
            win = inside & (y > top[y0:y1, x0:x1])
            top[y0:y1, x0:x1][win] = y[win]
            rgb[y0:y1, x0:x1][win] = q.rgb
            wet[y0:y1, x0:x1][win] = is_sea
    return rgb, np.isfinite(top), wet


SEA_OUTSIDE = 0.25              # beyond the faces outside the road's loop is sea when this share of the faces seen there is sea
ROAD_SHARE = 0.1                # a colour making this share of what lies under the road's tarmac is a tarmac colour,
ROAD_NEAR = 12                  # and so is one within this of it in every channel (Beltway's other roads: 65 grey by its 67)


def _beyond(top: np.ndarray, covered: np.ndarray, wet: np.ndarray, road: np.ndarray, fallback) -> None:
    """Fills `_top_view`'s samples no face covers (the PS2 models only the land near the road), in place: inside the road's loop
    the commonest colour seen inside it off the road (ROAD_EDGE + 2 px from the centreline) and not a tarmac colour (ROAD_SHARE, ROAD_NEAR),
    outside it the sea when at least SEA_OUTSIDE of the faces seen outside are sea, else the commonest such colour seen outside;
    `fallback` when none."""
    inside = np.zeros(covered.shape, bool)
    _fill(inside, road * SS, True)
    near = np.zeros(covered.shape, bool)
    _stroke(near, road * SS, (ROAD_EDGE + 2) * SS, True)
    under = np.zeros(covered.shape, bool)                   # the course's own tarmac colours: not a fill (Beltway's other roads)
    _stroke(under, road * SS, ROAD_TARMAC * SS, True)
    cols, n = np.unique(top[under & covered].astype(np.int64), axis=0, return_counts=True)
    tarmac = cols[n >= ROAD_SHARE * n.sum()] if len(n) else cols
    paved = (np.abs(top[..., None, :] - tarmac[None, None]).max(3) <= ROAD_NEAR).any(2) if len(tarmac) else np.zeros(covered.shape, bool)
    for part, outside in ((inside, False), (~inside, True)):
        hole = ~covered & part
        if not hole.any():
            continue
        seen = covered & part & ~near & ~paved
        is_sea = outside and seen.any() and wet[seen].mean() >= SEA_OUTSIDE
        pool = seen & (wet if is_sea else ~wet)
        if pool.any():
            cols, n = np.unique(top[pool].astype(np.int64), axis=0, return_counts=True)
            top[hole] = cols[n.argmax()]
        else:
            top[hole] = fallback
        wet[hole] = is_sea


def course_picture(sat, lap, name: str | None, masks: dict | None, faces=None, sea=None) -> np.ndarray:
    """The course's 168 x 128 RGB select picture (uint8); without `name`, no lettering (`with_name` adds it later). `faces`
    (Phase 90: the WorldQuads of a course that is not a Saturn course, `sat` then unused; `sea` the predicate naming its sea
    faces): the land takes the colour of the topmost ground face under each sample (`_top_view`), shaded by the same mesh as a
    Saturn picture's, the sea flat as the Saturn's water; the road, start mark, frame and name as on a Saturn picture."""
    cl = centreline(lap, spacing=5.0)
    f = fit(cl)
    road = np.array([to_panel(x, z, f) for x, z in cl + cl[:1]])
    if faces is None:
        terrain = course_quads(sat, groups=(1,))
        water = [q for q in course_quads(sat, groups=(0, 1)) if is_water(q.rgb)]
    else:
        terrain, water = faces, []
    counts = Counter(tuple(q.rgb) for q in terrain if not is_water(q.rgb)).most_common(10)
    ramp = np.array(sorted((np.array(c, float) for c, _ in counts), key=lambda c: c.sum())) if counts else np.array([[60.0, 120, 60]])

    # the mesh: a jittered vertex grid (panel px), heights rising away from the road
    rng = np.random.default_rng(MESH_SEED)
    gx = np.arange(-CELL, W + 2 * CELL, CELL)
    gy = np.arange(-CELL, H + 2 * CELL, CELL * 0.87)
    vx = np.zeros((len(gy), len(gx))); vy = np.zeros_like(vx)
    for j, y in enumerate(gy):
        vx[j] = gx + (CELL / 2 if j % 2 else 0) + rng.uniform(-0.3, 0.3, len(gx)) * CELL
        vy[j] = y + rng.uniform(-0.3, 0.3, len(gx)) * CELL
    noise = sum(_value_noise(vx, vy, sc, k) * amp for k, (sc, amp) in enumerate(NOISE))
    rise = np.clip((_road_distance(vx, vy, road) - 4) / 22, 0, 1)
    vz = (rise * (0.25 + noise) + 0.1 * noise) * 34
    zmax = vz.max() or 1.0
    light = np.array(LIGHT) / np.linalg.norm(LIGHT)
    canvas = np.empty((H * SS, W * SS, 3), np.float64)
    canvas[:] = ramp[0]
    shade = np.ones((H * SS, W * SS)) if faces is not None else None

    def facet(tri):
        a, b, c = (np.array(v) for v in tri)
        n = np.cross(b - a, c - a); n = n / (np.linalg.norm(n) or 1.0)
        if n[2] < 0:
            n = -n
        k = 0.45 + 0.75 * max(0.0, float(n @ light))
        if shade is not None:
            _fill(shade, [(v[0] * SS, v[1] * SS) for v in tri], k)
            return
        col = ramp[min(len(ramp) - 1, int((a[2] + b[2] + c[2]) / 3 / zmax * (len(ramp) - 0.01)))]
        _fill(canvas, [(v[0] * SS, v[1] * SS) for v in tri], np.minimum(255, col * k))
    for j in range(len(gy) - 1):
        for i in range(len(gx) - 1):
            A = (vx[j, i], vy[j, i], vz[j, i]); B = (vx[j, i + 1], vy[j, i + 1], vz[j, i + 1])
            C = (vx[j + 1, i], vy[j + 1, i], vz[j + 1, i]); D = (vx[j + 1, i + 1], vy[j + 1, i + 1], vz[j + 1, i + 1])
            if j % 2 == 0:
                facet((A, B, C)); facet((B, D, C))
            else:
                facet((A, B, D)); facet((A, D, C))
    if faces is not None:
        top, covered, wet = _top_view(faces, f, sea or (lambda q: False), canvas.shape[:2])
        _beyond(top, covered, wet, road, ramp[0])
        canvas = np.where(wet[..., None], top, np.minimum(255, top * shade[..., None]))
    for q in water:
        _fill(canvas, [(to_panel(p[0], p[2], f)[0] * SS, to_panel(p[0], p[2], f)[1] * SS) for p in q.p], q.rgb)
    _stroke(canvas, road * SS, ROAD_EDGE * SS, EDGE_RGB)
    _stroke(canvas, road * SS, ROAD_TARMAC * SS, TARMAC_RGB)
    (sx, sy), (qx, qy) = road[0], road[2]
    n = np.array([-(qy - sy), qx - sx]); n /= np.linalg.norm(n) or 1.0
    _stroke(canvas, np.array([(sx - n[0] * 2.6, sy - n[1] * 2.6), (sx + n[0] * 2.6, sy + n[1] * 2.6)]) * SS, 1.4 * SS, START_RGB)
    img = canvas.reshape(H, SS, W, SS, 3).mean((1, 3)).round().clip(0, 255).astype(np.uint8)
    img[:2] = img[-2:] = FRAME
    img[:, :2] = img[:, -2:] = FRAME
    if name is not None:
        draw_name(img, name, NAME_RIGHT, NAME_BOTTOM, masks)
    return img


def with_name(picture: np.ndarray, name: str, masks: dict) -> np.ndarray:
    """A copy of a picture made without a name, with `name` lettered on it."""
    img = picture.copy()
    draw_name(img, name, NAME_RIGHT, NAME_BOTTOM, masks)
    return img
