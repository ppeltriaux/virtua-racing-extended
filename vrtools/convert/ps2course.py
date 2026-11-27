"""A PS2 course (vrtools.ps2.course) turned into what the arcade build takes from a Saturn course (Phase 90).

docs/spike/2026-11-phase90-ps2-disc-recon.md §6 measures the steps. The PS2 world is in arcade units: arcade = (−x, −y, −z) + the
host's start (`Frame.for_host`: road point 0 of the host's line 0 and the host's collision height there). The lap comes from the
racing line and the tarmac band scanned across it (`build_lap`); the collision from one tarmac quad per section pair, a verge each
side out to the drawn ground or a wall, a wall strip where a wall stands (`collision`, then `merge_straights` and `cell_lists`, the
Saturn path's own); the road tables from `road.road_tables` with the pitch and roll measured on the tarmac (`attitude`); the
scenery from the split-screen set, triangle pairs of one colour merged into quads and the small far faces thinned (`scenery`);
the checkpoints from the `chk.bin` gates; the tunnels from the lamp meshes; a backdrop from the sky pictures.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from vrtools.arcade.tgp import SURFACE_GRASS, SURFACE_TARMAC, SURFACE_WALL, Collision, Quad16
from vrtools.convert.collision import cell_lists, direction_attr, merge_straights, order_corners, tgp_height
from vrtools.convert.geometry import ConvertError, WorldQuad
from vrtools.convert.lap import Lap, centreline
from vrtools.convert.road import PITCH_CLAMP, PITCH_SIGN, ROLL_CLAMP, ROLL_SIGN
from vrtools.ps2 import vcp
from vrtools.ps2.course import Ps2Course, swatch_colours

ROAD_KINDS = (0, 0x0A, 0x0B)        # tarmac and the kinds lying on it (recon §3.3)
GROUND_KINDS = (1, 2, 3, 0x0D)      # kerb and verge
KERB_KINDS = (1,)                   # the kerb strips beside the tarmac (recon §3.3): in the collision's tarmac band
SCAN_REACH = 45.0                   # lateral scan, each side (units)
SCAN_STEP = 0.5
MAX_GROUND = 40.0                   # a verge reaches at most this far past the tarmac (collision.MARGIN)
SECTION_SPACING = 8.0               # cross-sections every 8 units (the Saturn slices' ~8.6)
WALL_STRIP = 4.0                    # the run-off's edge strip (surface 5) where a wall stands
MIN_VERGE = 1.0
INNER_MARGIN = 4.0                  # a wall crossing the scan line this far or more inside the tarmac edge, with tarmac beyond it,
                                    # stands IN the road (Beltway's divider of pylons at road points 54-64): not the road's edge
DIVIDER_MIN = 1.5                   # the narrowest divider wall quad (a single crossing: a thin wall)
THIN = 6.0                          # xz area under which a scenery face farther than 40 units from the road is left out (§6.2)
TUNNEL_REACH = 20.0                 # road points this near a tunnel lamp are in the tunnel
GATE_REACH = 20.0                   # a gate this near the centreline counts as crossing it


# ---- frame -------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Frame:
    tx: float
    ty: float
    tz: float

    def pts(self, p) -> np.ndarray:
        q = np.array(p, dtype=float)
        q[..., 0] = self.tx - q[..., 0]
        q[..., 1] = self.ty - q[..., 1]
        q[..., 2] = self.tz - q[..., 2]
        return q

    @staticmethod
    def for_host(rs, host: int) -> "Frame":
        """The PS2 origin (its start line, heading −z) on the host's road point 0 (heading +z), at the host's collision height
        there (the tarmac quad containing it, else the nearest quad's centre)."""
        from vrtools.arcade.bank import all_lines
        from vrtools.arcade.tgp import decode_collision
        from vrtools.convert.collision import _point_in_xz
        p0 = all_lines(rs, host)[0][0]
        col = decode_collision(rs, host)
        inside = [q for q in col.quads if _point_in_xz(q.corners, p0.x, p0.z)]
        if inside:
            y = max(tgp_height(q.corners, p0.x, p0.z) for q in inside)
        else:
            q = min(col.quads, key=lambda q: (q.centre[0] - p0.x) ** 2 + (q.centre[2] - p0.z) ** 2)
            y = q.centre[1]
        return Frame(float(p0.x), float(y), float(p0.z))


# ---- triangle queries --------------------------------------------------------------------------------------------

class _TriIndex:
    def __init__(self, tris: np.ndarray, cell: float = 8.0):
        self.cell = cell
        self.b = defaultdict(list)
        xz = tris[:, :, [0, 2]]
        lo = np.floor(xz.min(1) / cell).astype(int)
        hi = np.floor(xz.max(1) / cell).astype(int)
        for i in range(len(tris)):
            for cx in range(lo[i, 0], hi[i, 0] + 1):
                for cz in range(lo[i, 1], hi[i, 1] + 1):
                    self.b[(cx, cz)].append(i)
        self.a = xz[:, 0]
        self.v0, self.v1 = xz[:, 1] - xz[:, 0], xz[:, 2] - xz[:, 0]
        self.den = self.v0[:, 0] * self.v1[:, 1] - self.v1[:, 0] * self.v0[:, 1]
        self.y = tris[:, :, 1]

    def at(self, x: float, z: float) -> list[tuple[int, float]]:
        ids = self.b.get((int(math.floor(x / self.cell)), int(math.floor(z / self.cell))))
        if not ids:
            return []
        ids = np.array(ids)
        ids = ids[np.abs(self.den[ids]) > 1e-9]
        d = self.den[ids]
        px, pz = x - self.a[ids, 0], z - self.a[ids, 1]
        u = (px * self.v1[ids, 1] - self.v1[ids, 0] * pz) / d
        v = (self.v0[ids, 0] * pz - px * self.v0[ids, 1]) / d
        ok = (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
        return [(int(i), float(self.y[i, 0] + uu * (self.y[i, 1] - self.y[i, 0]) + vv * (self.y[i, 2] - self.y[i, 0])))
                for i, uu, vv in zip(ids[ok], u[ok], v[ok])]


class Ground:
    """The AT triangles in the arcade frame; `probe` = (kind, height) of the triangle under (x, z) nearest `h_ref`."""

    def __init__(self, road: list[vcp.CollisionSet], frame: Frame):
        s = vcp.merged(road)
        self.tris = frame.pts(s.triangles)
        self.kinds = s.kinds.astype(int)
        self.idx = _TriIndex(self.tris)

    def probe(self, x: float, z: float, h_ref: float | None, max_dy: float = 4.0):
        hits = self.idx.at(x, z)
        if not hits:
            return None, None
        if h_ref is None:
            i, y = max(hits, key=lambda h: h[1])
        else:
            i, y = min(hits, key=lambda h: abs(h[1] - h_ref))
            if abs(y - h_ref) > max_dy:
                return None, None
        return int(self.kinds[i]), y


class Walls:
    """The KB triangles' xz footprints as segments; `hit` = the nearest crossing of a ray standing at height `h`."""

    def __init__(self, walls: list[vcp.CollisionSet], frame: Frame, cell: float = 32.0):
        s = vcp.merged(walls)
        t = frame.pts(s.triangles)
        xz = t[:, :, [0, 2]]
        d = np.stack([np.linalg.norm(xz[:, 0] - xz[:, 1], axis=1), np.linalg.norm(xz[:, 0] - xz[:, 2], axis=1),
                      np.linalg.norm(xz[:, 1] - xz[:, 2], axis=1)], 1)
        pairs = np.array([(0, 1), (0, 2), (1, 2)])[np.argmax(d, 1)]
        r = np.arange(len(xz))
        self.a, self.b = xz[r, pairs[:, 0]], xz[r, pairs[:, 1]]
        self.ylo, self.yhi = t[:, :, 1].min(1), t[:, :, 1].max(1)
        self.cell = cell
        self.bk = defaultdict(list)
        lo = np.floor(np.minimum(self.a, self.b) / cell).astype(int)
        hi = np.floor(np.maximum(self.a, self.b) / cell).astype(int)
        for i in range(len(self.a)):
            for cx in range(lo[i, 0], hi[i, 0] + 1):
                for cz in range(lo[i, 1], hi[i, 1] + 1):
                    self.bk[(cx, cz)].append(i)

    def hit(self, p, r, reach: float, h: float) -> float | None:
        t = self.crossings(p, r, reach, h)
        return t[0] if t else None

    def near(self, p, dist: float, h: float) -> bool:
        """Whether a wall standing at height `h` passes within `dist` of the point `p` (x, z)."""
        ids = set()
        for dx in (-dist, 0.0, dist):
            for dz in (-dist, 0.0, dist):
                ids.update(self.bk.get((int(math.floor((p[0] + dx) / self.cell)), int(math.floor((p[1] + dz) / self.cell))), ()))
        if not ids:
            return False
        ids = np.array(sorted(ids))
        ids = ids[(self.ylo[ids] <= h + 2.0) & (self.yhi[ids] >= h + 0.3)]
        if not len(ids):
            return False
        a, e = self.a[ids], self.b[ids] - self.a[ids]
        w = np.clip(((p[0] - a[:, 0]) * e[:, 0] + (p[1] - a[:, 1]) * e[:, 1]) / ((e ** 2).sum(1) + 1e-12), 0, 1)
        return bool((np.hypot(a[:, 0] + w * e[:, 0] - p[0], a[:, 1] + w * e[:, 1] - p[1]) < dist).any())

    def crossings(self, p, r, reach: float, h: float) -> list[float]:
        """Every crossing of the ray (from `p`, direction `r`, within `reach`) with a wall standing at height `h`, nearest first."""
        ids = set()
        for s in np.linspace(0, reach, int(reach // 4.0) + 2):          # every 4 units: no bucket the ray crosses is skipped
            ids.update(self.bk.get((int(math.floor((p[0] + r[0] * s) / self.cell)), int(math.floor((p[1] + r[1] * s) / self.cell))), ()))
        if not ids:
            return []
        ids = np.array(sorted(ids))
        ids = ids[(self.ylo[ids] <= h + 2.0) & (self.yhi[ids] >= h + 0.3)]
        if not len(ids):
            return []
        a, e = self.a[ids], self.b[ids] - self.a[ids]
        den = r[0] * e[:, 1] - r[1] * e[:, 0]
        ok = np.abs(den) > 1e-9
        safe = np.where(ok, den, 1.0)
        ax, az = a[:, 0] - p[0], a[:, 1] - p[1]
        t = np.where(ok, (ax * e[:, 1] - az * e[:, 0]) / safe, np.inf)
        u = np.where(ok, (ax * r[1] - az * r[0]) / safe, -1.0)
        good = ok & (t > 0.5) & (t <= reach) & (u >= -1e-6) & (u <= 1 + 1e-6)
        return sorted(float(v) for v in t[good])


# ---- the lap -----------------------------------------------------------------------------------------------------

def smooth_closed(p: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return p
    h = window // 2
    ext = np.concatenate([p[-h:], p, p[:h]])
    k = np.ones(window) / window
    return np.stack([np.convolve(ext[:, j], k, mode="valid") for j in range(p.shape[1])], 1)[:len(p)]


def resample_closed(p: np.ndarray, step: float) -> np.ndarray:
    q = np.vstack([p, p[:1]])
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    t = np.arange(0.0, s[-1] - step / 2, step)
    return np.stack([np.interp(t, s, q[:, j]) for j in range(p.shape[1])], 1)


def tangents(p: np.ndarray) -> np.ndarray:
    d = np.roll(p, -1, 0) - np.roll(p, 1, 0)
    return d / np.linalg.norm(d, axis=1, keepdims=True)


@dataclass
class Section:
    centre: tuple[float, float]
    dirn: tuple[float, float]
    height: float
    left: float                 # tarmac edges, along the right-hand lateral from the centre (left < 0 < right)
    right: float
    h_left: float               # tarmac heights at the edges
    h_right: float
    ground_left: float          # outer ends of the drawn ground (kerb, verge), capped
    ground_right: float
    wall_left: float | None     # walls' distances from the centre, if within reach
    wall_right: float | None
    kerb_left: float = 0.0      # outer ends of the kerb strips (kind 1) touching the tarmac; the tarmac edge where there is none
    kerb_right: float = 0.0
    divider: tuple[float, float] | None = None   # a wall standing in the road (lateral offsets of its two faces), tarmac each side
    divider_end: float | None = None             # where that divider stops (or starts) toward the next section (`divider_ends`)

    def at(self, off: float, y: float | None = None) -> tuple[float, float, float]:
        r = (self.dirn[1], -self.dirn[0])
        if y is None:
            t = (off - self.left) / ((self.right - self.left) or 1.0)
            y = self.h_left + min(1.0, max(0.0, t)) * (self.h_right - self.h_left)
        return (self.centre[0] + off * r[0], y, self.centre[1] + off * r[1])


def scan(ground: Ground, walls: Walls | None, p, d, h_ref) -> Section | None:
    """The tarmac band across the point `p` (direction `d`) at the reference height: its edges and heights, the drawn ground
    beyond, the walls."""
    r = (d[1], -d[0])
    offs = np.arange(-SCAN_REACH, SCAN_REACH + SCAN_STEP / 2, SCAN_STEP)
    probes = [ground.probe(p[0] + o * r[0], p[1] + o * r[1], h_ref) for o in offs]
    kinds = [k for k, _ in probes]
    hs = [h for _, h in probes]
    road = np.array([k in ROAD_KINDS for k in kinds])
    if not road.any():
        return None
    mid = len(offs) // 2
    idx = np.flatnonzero(road)
    lo = hi = int(idx[np.argmin(np.abs(idx - mid))])
    while lo > 0 and road[lo - 1]:
        lo -= 1
    while hi < len(offs) - 1 and road[hi + 1]:
        hi += 1
    kl, kr = lo, hi
    while kl > 0 and kinds[kl - 1] in KERB_KINDS:
        kl -= 1
    while kr < len(offs) - 1 and kinds[kr + 1] in KERB_KINDS:
        kr += 1
    gl, gr = lo, hi
    drawn = lambda k: k is not None and (k in GROUND_KINDS or k in ROAD_KINDS)
    while gl > 0 and drawn(kinds[gl - 1]):
        gl -= 1
    while gr < len(offs) - 1 and drawn(kinds[gr + 1]):
        gr += 1
    left, right = offs[lo] - SCAN_STEP / 2, offs[hi] + SCAN_STEP / 2
    c = (left + right) / 2
    cen = (p[0] + c * r[0], p[1] + c * r[1])
    h = hs[(lo + hi) // 2]
    h = h_ref if h is None else h
    wl = wr = divider = None
    if walls is not None:
        wl, wr, divider = _walls_across(walls, cen, r, (right - left) / 2, h)
    third = max(1, (hi - lo + 1) // 3)                 # the edge heights: medians of the band's outer thirds (a kerb cell or a
    hl = float(np.median([y for y in hs[lo:lo + third] if y is not None] or [h]))      # neighbouring level at the very edge
    hr = float(np.median([y for y in hs[hi + 1 - third:hi + 1] if y is not None] or [h]))   # would tilt the whole band)
    return Section(cen, (float(d[0]), float(d[1])), float(h), float(left - c), float(right - c), hl, hr,
                   float(max(offs[gl] - c, left - c - MAX_GROUND)), float(min(offs[gr] - c, right - c + MAX_GROUND)), wl, wr,
                   float(offs[kl] - SCAN_STEP / 2 - c) if kl < lo else float(left - c),
                   float(offs[kr] + SCAN_STEP / 2 - c) if kr > hi else float(right - c), divider)


def _walls_across(walls: Walls, cen, r, half: float, h: float):
    """(left wall, right wall, divider) across a band of half-width `half` centred on `cen` (right-hand lateral `r`). The road's
    edge walls are the first crossings each side that are not INSIDE the band: a wall crossing farther than INNER_MARGIN inside
    the tarmac edge has tarmac beyond it and stands in the road (a divider: (lateral offsets of its faces), at least DIVIDER_MIN
    wide); taken as the edge, it made verges and wall strips over both carriageways (Beltway's pylons after the start)."""
    rc = walls.crossings(cen, r, SCAN_REACH, h)
    lc = walls.crossings(cen, (-r[0], -r[1]), SCAN_REACH, h)
    inner = [-t for t in lc if t < half - INNER_MARGIN] + [t for t in rc if t < half - INNER_MARGIN]
    wr = next((t for t in rc if t >= half - INNER_MARGIN), None)
    wl = next((t for t in lc if t >= half - INNER_MARGIN), None)
    divider = None
    if inner:
        lo_d, hi_d = min(inner), max(inner)
        if hi_d - lo_d < DIVIDER_MIN:
            m = (lo_d + hi_d) / 2
            lo_d, hi_d = m - DIVIDER_MIN / 2, m + DIVIDER_MIN / 2
        divider = (float(lo_d), float(hi_d))
    return wl, wr, divider


def _between(a: Section, b: Section, f: float, divider) -> Section:
    """The cross-section at fraction `f` from `a` to `b` (every field interpolated), with `divider`."""
    lerp = lambda u, v: u + f * (v - u)
    d = (lerp(a.dirn[0], b.dirn[0]), lerp(a.dirn[1], b.dirn[1]))
    dn = math.hypot(*d) or 1.0
    return Section((lerp(a.centre[0], b.centre[0]), lerp(a.centre[1], b.centre[1])), (d[0] / dn, d[1] / dn), lerp(a.height, b.height),
                   lerp(a.left, b.left), lerp(a.right, b.right), lerp(a.h_left, b.h_left), lerp(a.h_right, b.h_right),
                   lerp(a.ground_left, b.ground_left), lerp(a.ground_right, b.ground_right), a.wall_left, a.wall_right,
                   lerp(a.kerb_left, b.kerb_left), lerp(a.kerb_right, b.kerb_right), divider)


def divider_ends(walls: Walls, secs: list[Section], step: float = 0.5) -> None:
    """Where a divider begins or ends between two sections (one has it, the other not): `divider_end` on the pair's first
    section = the fraction from it to the next at which the divider's footprint stops (or starts), found every `step` units."""
    n = len(secs)
    for k in range(n):
        a, b = secs[k], secs[(k + 1) % n]
        if (a.divider is None) == (b.divider is None):
            continue
        length = math.dist(a.centre, b.centre)
        fs = [i * step / length for i in range(1, int(length / step))] if length > step else []
        has = []
        for f in fs:
            e = _between(a, b, f, None)
            r = (e.dirn[1], -e.dirn[0])
            has.append(_walls_across(walls, e.centre, r, (e.right - e.left) / 2, e.height)[2] is not None)
        if a.divider is not None:              # it ends: the last fraction still crossing it
            a.divider_end = max((f for f, h in zip(fs, has) if h), default=0.0)
        else:                                  # it begins: the first fraction crossing it
            a.divider_end = min((f for f, h in zip(fs, has) if h), default=1.0)


def build_lap(ground: Ground, walls: Walls, racing_line: np.ndarray, spacing: float = SECTION_SPACING) -> tuple[Lap, list[Section]]:
    """The lap from the racing line (x, z, arcade frame): densified and smoothed, the tarmac band scanned across it every 5 units,
    the band's middle smoothed and scanned again every `spacing` units. One Lap "slice" per section, in lap order from the start."""
    line = smooth_closed(resample_closed(np.asarray(racing_line, float), 1.0), 21)
    pts = resample_closed(line, 5.0)
    centres, h = [], None
    for p, d in zip(pts, tangents(pts)):
        s = scan(ground, None, p, d, h)
        if s is not None:
            h = s.height
        centres.append(s.centre if s is not None else tuple(p))
    c = resample_closed(smooth_closed(np.array(centres), 7), spacing)
    secs, h = [], None
    for p, d in zip(c, tangents(c)):
        s = scan(ground, walls, p, d, h)
        if s is None:
            hh = h if h is not None else 0.0
            s = Section((float(p[0]), float(p[1])), (float(d[0]), float(d[1])), hh, -6.0, 6.0, hh, hh, -6.0, 6.0, None, None, -6.0, 6.0)
        h = s.height
        secs.append(s)
    if walls is not None:
        divider_ends(walls, secs)
    cen = [s.centre for s in secs]
    arc = [0.0]
    for a, b in zip(cen, cen[1:]):
        arc.append(arc[-1] + math.dist(a, b))
    order = list(range(len(cen)))
    return Lap(order, arc, arc[-1] + math.dist(cen[-1], cen[0]), 0, cen, [], order, list(arc)), secs


# ---- collision ---------------------------------------------------------------------------------------------------

def _quad(corners, d) -> Quad16:
    c = order_corners(corners, d[0], d[1])
    centre = tuple(sum(p[i] for p in c) / 4 for i in range(3))
    return Quad16(tuple(tuple(float(v) for v in p) for p in c), centre, direction_attr(d[0], d[1]))


def collision(secs: list[Section], extra_tarmac: list[Quad16] = (), pair: int | None = None) -> tuple[Collision, dict[int, int]]:
    """The course's collision: per section pair a tarmac quad (the band out to the PS2's kerb strips: a kerb is driven as the
    road, and separate kerb quads made Mountain's collision 41 % larger than its slot holds), a verge each side out to the
    drawn ground or the wall
    (at the tarmac edge's height, as the Saturn path's verges), a wall strip where walls stand on both sections; straights merged
    (`merge_straights`); tarmac first, then verges, then walls; the cell lists with the tarmac last in each (`cell_lists`).
    Where both sections of a pair have a wall standing in the road (`Section.divider`: Beltway's pylons after the start), the
    band is two tarmac quads, one each side of a wall quad over the divider's footprint (the TGP gives tarmac the exact ties,
    so a wall over whole tarmac would never be read). Where the divider begins or ends between two sections (`divider_end`) the
    pair is cut there too: the divided part as above, the rest one band. Such a slice is not merged, and its other pieces follow
    its first in the tarmac list in lap order (credited their own road points, as the Saturn path's side strips)."""
    slices, walls = [], []
    seconds: dict[int, list[Quad16]] = {}           # slice -> its other tarmac pieces, in lap order

    def divided(a: Section, b: Section, d) -> list[Quad16]:
        (al, ar), (bl, br) = a.divider, b.divider
        walls.append(_quad([b.at(bl), b.at(br), a.at(ar), a.at(al)], d))
        return [_quad([b.at(b.kerb_left, b.h_left), b.at(bl), a.at(al), a.at(a.kerb_left, a.h_left)], d),
                _quad([b.at(br), b.at(b.kerb_right, b.h_right), a.at(a.kerb_right, a.h_right), a.at(ar)], d)]

    def band(a: Section, b: Section, d) -> Quad16:
        return _quad([b.at(b.kerb_left, b.h_left), b.at(b.kerb_right, b.h_right), a.at(a.kerb_right, a.h_right),
                      a.at(a.kerb_left, a.h_left)], d)

    n = len(secs)
    for k in range(n):
        a, b = secs[k], secs[(k + 1) % n]
        d = (b.centre[0] - a.centre[0], b.centre[1] - a.centre[1])
        if a.divider is not None and b.divider is not None:
            tar, *rest = divided(a, b, d)
            seconds[k] = rest
        elif (a.divider is None) != (b.divider is None) and a.divider_end is not None and 0.0 < a.divider_end < 1.0:
            e = _between(a, b, a.divider_end, a.divider or b.divider)
            if a.divider is not None:             # the divider ends at e: divided from a to e, one band from e to b
                pieces = divided(a, e, d) + [band(e, b, d)]
            else:                                 # it begins at e
                pieces = [band(a, e, d)] + divided(e, b, d)
            tar, *rest = pieces
            seconds[k] = rest
        else:
            tar = _quad([b.at(b.kerb_left, b.h_left), b.at(b.kerb_right, b.h_right), a.at(a.kerb_right, a.h_right),
                         a.at(a.kerb_left, a.h_left)], d)                # the band out to the kerbs' outer ends
        vs = []
        for side, sg in ((0, -1.0), (1, 1.0)):
            ea, eb = (a.kerb_left, b.kerb_left) if side == 0 else (a.kerb_right, b.kerb_right)
            ya, yb = (a.h_left, b.h_left) if side == 0 else (a.h_right, b.h_right)
            ga, gb = (a.ground_left, b.ground_left) if side == 0 else (a.ground_right, b.ground_right)
            wa, wb = (a.wall_left, b.wall_left) if side == 0 else (a.wall_right, b.wall_right)
            oa = sg * min(abs(ga), wa) if wa is not None else ga
            ob = sg * min(abs(gb), wb) if wb is not None else gb
            if abs(oa - ea) < MIN_VERGE and abs(ob - eb) < MIN_VERGE:
                vs.append(None)
            else:
                vs.append(_quad([b.at(eb, yb), b.at(ob, yb), a.at(oa, ya), a.at(ea, ya)], d))
            if wa is not None and wb is not None:
                walls.append(_quad([b.at(ob, yb), b.at(ob + sg * WALL_STRIP, yb), a.at(oa + sg * WALL_STRIP, ya), a.at(oa, ya)], d))
        slices.append((tar, tuple(vs)))
    tarmac, verges, merged = merge_straights(slices, keep=set(seconds))
    for k, rest in seconds.items():                 # a divided slice's other pieces right after its first (an unmerged single)
        i = next(i for i, t in enumerate(tarmac) if t is slices[k][0])
        tarmac[i + 1:i + 1] = rest
    extra = list(extra_tarmac)
    if pair is not None:                      # the pit entry quad twice in a row: the game's PIT WORK check reads the entry quad
        extra.insert(pair + 1, extra[pair])   # OR THE NEXT in the list (collision.pit_entry_quad's pair, Phase 22j)
    tarmac = tarmac + extra                   # after the lap's own tarmac (the segment array credits them to the nearest points)
    quads = tarmac + verges + walls
    surface = bytes([SURFACE_TARMAC] * len(tarmac) + [SURFACE_GRASS] * len(verges) + [SURFACE_WALL] * len(walls))
    lists, cells = cell_lists(quads, last=set(range(len(tarmac))))
    return Collision(lists, quads, surface, merged=merged), cells


def height_fn(secs: list[Section]):
    """A HeightFn: the height of the section nearest (x, z) (for the spawn list's furniture)."""
    c = np.array([s.centre for s in secs])
    h = np.array([s.height for s in secs])
    return lambda x, z: float(h[int(np.argmin((c[:, 0] - x) ** 2 + (c[:, 1] - z) ** 2))])


def attitude(lap: Lap, secs: list[Section], pts, spacing: float = 10.0) -> list[tuple[int, int]]:
    """(roll, pitch) per centreline point in 1/65536 turn, the game's signs (road.ROLL_SIGN / PITCH_SIGN): the pitch from the
    sections' heights along the lap, the roll from the tarmac's edge heights across, both averaged over three points, clamped."""
    arc = np.array(lap.arc + [lap.length])
    hs = np.array([s.height for s in secs] + [secs[0].height])
    cs = np.array(lap.centres)
    n = len(pts)
    raw = []
    for k, (x, z) in enumerate(pts):
        a = k * spacing
        rise = np.interp((a + spacing) % lap.length, arc, hs) - np.interp((a - spacing) % lap.length, arc, hs)
        pitch = PITCH_SIGN * int(round(math.atan2(rise, 2 * spacing) / (2 * math.pi) * 65536))
        s = secs[int(np.argmin((cs[:, 0] - x) ** 2 + (cs[:, 1] - z) ** 2))]
        w = (s.right - s.left) or 1.0
        roll = ROLL_SIGN * int(round(math.atan((s.h_right - s.h_left) / w) / (2 * math.pi) * 65536))
        raw.append((roll, max(-PITCH_CLAMP, min(PITCH_CLAMP, pitch))))
    out = []
    for k in range(n):
        r = round((raw[k - 1][0] + raw[k][0] + raw[(k + 1) % n][0]) / 3)
        out.append((max(-ROLL_CLAMP, min(ROLL_CLAMP, r)), raw[k][1]))
    return out


AI_MARGIN = 4.0                     # units the outermost AI line keeps inside the tarmac band's edge (§9: on Mountain's pass the
AI_REACH = 8.0                      # lines at +-8 ran on the band's edge and a car pinned itself on a wall strip for 60 s)
AI_SCALE_MIN = 0.3
WALL_CLEAR = 3.0                    # a wall within this of the outermost plain line pulls that side's lines in (AI_MARGIN from it)
AI_SMOOTH = 3                       # centreline points each side over which the narrowest scale holds


def lane_scales(secs: list[Section], pts, side: int = 1, walls: Walls | None = None) -> list[tuple]:
    """Per centreline point, (left, right) scales of the AI lines' offsets (`road.road_tables`' `lanes`): the band's half width on
    that side (out to the kerbs) less AI_MARGIN, over the lines' reach, at most 1, at least AI_SCALE_MIN, the narrowest within
    AI_SMOOTH points either side (no line steps sideways at a pinch). Where a divider stands in the road (`Section.divider`),
    every line keeps to ONE carriageway, `side` (+1 right, -1 left: the PS2's racing line's): (scale, scale, shift) putting the
    lines' reach inside that carriageway AI_MARGIN from the divider and from the edge, reached over DIVIDER_RAMP points before and
    left over as many after (`divider_lanes`). With `walls`, a wall standing at the road's height inside the band or at its edge
    (a post on the kerb: Beltway's at road points 104-107, 134, 214, 233, 240, 263, 313) bounds that side like the kerb, AI_MARGIN
    from it, measured across the line at each point and halfway to the next (`_wall_reach`)."""
    cs = np.array([s.centre for s in secs])
    raw, reaches, at = [], [], []
    n = len(pts)
    for k, (x, z) in enumerate(pts):
        s = secs[int(np.argmin((cs[:, 0] - x) ** 2 + (cs[:, 1] - z) ** 2))]
        at.append(s)
        reaches.append([abs(s.kerb_left), abs(s.kerb_right)])
        raw.append([min(1.0, max(AI_SCALE_MIN, (e - AI_MARGIN) / AI_REACH)) for e in reaches[-1]])
    smooth = lambda r: [tuple(min(r[(k + j) % n][i] for j in range(-AI_SMOOTH, AI_SMOOTH + 1)) for i in (0, 1)) for k in range(n)]
    lanes = smooth(raw)
    if walls is not None:                                # a wall the lines would pass within WALL_CLEAR of bounds that side
        for k in range(n):
            near = [any(walls.near(_lateral(pts, k, sg * AI_REACH * lanes[k][i], u), WALL_CLEAR, at[k].height) for u in (0.0, 0.5))
                    for i, sg in ((0, -1.0), (1, 1.0))]
            if any(near):
                w = _wall_reach(walls, pts, k, at[k], reaches[k])
                for i in (0, 1):
                    if near[i] and w[i] < reaches[k][i]:
                        reaches[k][i] = w[i]
                        raw[k][i] = min(raw[k][i], max(AI_SCALE_MIN, (w[i] - AI_MARGIN) / AI_REACH))
        lanes = smooth(raw)
    return divider_lanes(secs, pts, lanes, side, reaches)


def _lateral(pts, k: int, off: float, u: float = 0.0):
    """The point `off` units to the right of centreline point k (or of the point `u` of the way to the next)."""
    n = len(pts)
    a, b = pts[k], pts[(k + 1) % n]
    d = (b[0] - a[0], b[1] - a[1])
    dn = math.hypot(*d) or 1.0
    return (a[0] + u * d[0] + off * d[1] / dn, a[1] + u * d[1] - off * d[0] / dn)


def _wall_reach(walls: Walls, pts, k: int, s: Section, reach) -> list[float]:
    """(left, right): the nearest wall crossing each side of centreline point k (and of the point halfway to the next), within the
    band out to its kerbs plus a unit; a crossing more than INNER_MARGIN inside the kerb is a divider's, not an edge, and is
    left out."""
    n = len(pts)
    out = [math.inf, math.inf]
    for u in (0.0, 0.5):
        a, b = pts[k], pts[(k + 1) % n]
        p = (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]))
        d = (b[0] - a[0], b[1] - a[1])
        dn = math.hypot(*d) or 1.0
        r = (d[1] / dn, -d[0] / dn)
        for i, sg in ((0, -1.0), (1, 1.0)):
            for t in walls.crossings(p, (sg * r[0], sg * r[1]), reach[i] + 1.0, s.height):
                if t < reach[i] - INNER_MARGIN:          # tarmac beyond it: a divider (`_walls_across`), not this side's edge
                    continue
                out[i] = min(out[i], t)
                break
    return out


DIVIDER_RAMP = 10                   # centreline points over which the AI lines move onto (and back off) one carriageway
DIVIDER_GUARD = 6                   # points before and after a divider where they are already there (an opponent steers at its
                                    # cursor + 2 and closes on its line over about ten points: with 2 and 7 the cars from the far
                                    # side reached the divider still on their way across)
DIVIDER_CLEAR = 8.0                 # the lines' reach keeps this far from the divider's face: AI_MARGIN and 4 more, the opponents'
                                    # drift off their lines (cursor + 2) at the bend before Beltway's pylons, measured headless
DIVIDER_JOIN = 2 * DIVIDER_RAMP     # dividers this few points apart are passed as one (Beltway's two rows of pylons)


def _divider_at(secs: list[Section], cs, x: float, z: float):
    """The divider (lateral offsets from that section's centre, its kerbs) under centreline point (x, z), or None."""
    n = len(secs)
    i = int(np.argmin((cs[:, 0] - x) ** 2 + (cs[:, 1] - z) ** 2))
    a = secs[i]
    t = (x - a.centre[0]) * a.dirn[0] + (z - a.centre[1]) * a.dirn[1]
    j = i if t >= 0 else (i - 1) % n                     # the pair (j, j + 1) the point lies in
    a, b = secs[j], secs[(j + 1) % n]
    length = math.dist(a.centre, b.centre) or 1.0
    f = min(1.0, max(0.0, ((x - a.centre[0]) * (b.centre[0] - a.centre[0]) + (z - a.centre[1]) * (b.centre[1] - a.centre[1])) / length ** 2))
    if a.divider is not None and b.divider is not None:
        d = a.divider
    elif a.divider is not None and a.divider_end is not None and f <= a.divider_end:
        d = a.divider
    elif b.divider is not None and a.divider_end is not None and f >= a.divider_end:
        d = b.divider
    else:
        return None
    near = a if f < 0.5 else b
    return d, near.kerb_left, near.kerb_right


def divider_lanes(secs: list[Section], pts, lanes: list[tuple], side: int = 1, reaches=None) -> list[tuple]:
    """`lanes` with the stretches beside a divider replaced: every line on the `side` carriageway (see `lane_scales`); `reaches`:
    per point the (left, right) distance to the kerb or a wall, which bounds the carriageway over the run and its ramps."""
    n = len(pts)
    cs = np.array([s.centre for s in secs])
    at = [_divider_at(secs, cs, x, z) for x, z in pts]
    idx = [k for k in range(n) if at[k] is not None]
    if not idx:
        return lanes
    runs = [[idx[0], idx[0]]]
    for k in idx[1:]:
        if k - runs[-1][1] <= DIVIDER_JOIN:
            runs[-1][1] = k
        else:
            runs.append([k, k])
    out = list(lanes)
    i_side = 1 if side > 0 else 0
    # a point's outer bound on that side: the kerb or a wall there, the narrowest within AI_SMOOTH points
    outer = (lambda k: min(reaches[(k + j) % n][i_side] for j in range(-AI_SMOOTH, AI_SMOOTH + 1))) if reaches else (lambda k: math.inf)

    def edges(lane):                                      # the lines' reach (left edge, right edge) under a lanes entry
        sh = lane[2] if len(lane) > 2 else 0.0
        return (sh - AI_REACH * lane[0], sh + AI_REACH * lane[1])

    def entry(lo_e, hi_e):                                # the lanes entry putting the lines' reach on (lo_e, hi_e)
        if hi_e - lo_e < 1.0:                             # a carriageway too narrow for the margins: its middle
            m = (lo_e + hi_e) / 2
            lo_e, hi_e = m - 0.5, m + 0.5
        h = (hi_e - lo_e) / 2
        return (h / AI_REACH, h / AI_REACH, (lo_e + hi_e) / 2)

    for k0, k1 in runs:
        divided = [j for j in range(k0, k1 + 1) if at[j] is not None]
        span = range(k0 - DIVIDER_GUARD - DIVIDER_RAMP, k1 + DIVIDER_GUARD + DIVIDER_RAMP + 1)
        for k in span:
            (lo, hi), kl, kr = at[min(divided, key=lambda j: abs(j - k))]
            if side > 0:                                  # the carriageway: DIVIDER_CLEAR from the face, AI_MARGIN from the edge
                band = (hi + DIVIDER_CLEAR, min(kr, outer(k)) - AI_MARGIN)
            else:
                band = (max(kl, -outer(k)) + AI_MARGIN, lo - DIVIDER_CLEAR)
            r = max(k0 - DIVIDER_GUARD - k, k - k1 - DIVIDER_GUARD, 0)   # points into the ramp (0: beside it or in the guard)
            if r == 0:
                out[k % n] = entry(*band)
                continue
            w = 1.0 - r / (DIVIDER_RAMP + 1)              # smoothstep from the plain lanes to the carriageway and back
            w = w * w * (3 - 2 * w)
            b = edges(lanes[k % n])
            lo_e, hi_e = b[0] + w * (band[0] - b[0]), b[1] + w * (band[1] - b[1])
            if side > 0:                                  # never past this point's own edge on the way
                hi_e = min(hi_e, max(b[1], min(kr, outer(k)) - AI_MARGIN))
            else:
                lo_e = max(lo_e, min(b[0], max(kl, -outer(k)) + AI_MARGIN))
            out[k % n] = entry(lo_e, hi_e)
    return out


# ---- the pit lane ------------------------------------------------------------------------------------------------

PIT_SPACING = 8.0
PIT_JOIN = 8.0                      # the lane ends where its path comes within this of the centreline (it has rejoined the road)
PIT_ENTRY_SEPARATE = 12.0           # the entry quad: the first lane section whose tarmac does not touch the race band's
PIT_BOX_MIN_RUN = 40.0              # the game's pit autopilot drives straight from the entry quad to the box (collision.pit_box)


@dataclass
class PitLane:
    line: list[tuple[float, float]]           # the lane's polyline, mouth to exit
    quads: list[Quad16]                       # its tarmac, mouth to exit
    entry: int                                # index in `quads` of the entry quad
    box: tuple[float, float, float, int]      # where the pit sequence parks the car: x, y, z, heading (1/65536 turn)


def pit_lane(course: Ps2Course, frame: Frame, ground: Ground, secs: list[Section], pts) -> PitLane | None:
    """The PS2's pit lane in the arcade's terms (the Saturn path's `place.PitLane` and `collision.pit_lane_polygons` / `pit_box`):
    the path `PIT01` from its start to where it rejoins the road, its tarmac band scanned across it every PIT_SPACING units; the
    entry quad the first section clear of the race band; the box at `PIT00`'s farthest point from the road (the PS2's stop: on
    Island the kind-0xa box zone), its heading the lane's beside it (1/65536 turn; h gives the direction (-sin h, cos h)). None for a course without the two paths."""
    if "PIT01" not in course.paths or "PIT00" not in course.paths:
        return None
    path = frame.pts(course.paths["PIT01"])[:, [0, 2]]
    c = np.array(pts)
    dist = np.array([np.sqrt(((c - q) ** 2).sum(1)).min() for q in path])
    end = next((i for i in range(1, len(path)) if dist[i] < PIT_JOIN), len(path) - 1)
    line = resample_open(path[:end + 1], PIT_SPACING)
    href = float(np.median([s.height for s in secs[:5] + secs[-5:]]))
    lane_secs = []
    for p, d in zip(line, tangents_open(line)):
        sec = scan(ground, None, p, d, href)
        if sec is not None:
            href = sec.height
            lane_secs.append(sec)
    if len(lane_secs) < 4:
        return None
    quads = []
    for a, b in zip(lane_secs, lane_secs[1:]):
        dd = (b.centre[0] - a.centre[0], b.centre[1] - a.centre[1])
        quads.append(_quad([b.at(b.kerb_left, b.h_left), b.at(b.kerb_right, b.h_right), a.at(a.kerb_right, a.h_right),
                            a.at(a.kerb_left, a.h_left)], dd))
    clear = [min(np.sqrt(((c - np.array(q.centre)[[0, 2]]) ** 2).sum(1))) for q in quads]
    half = [math.dist(q.corners[0], q.corners[1]) / 2 for q in quads]
    entry = next((i for i in range(len(quads)) if clear[i] - half[i] > PIT_ENTRY_SEPARATE), None)
    if entry is None:
        return None
    stop = frame.pts(course.paths["PIT00"])[:, [0, 2]]
    sd = [np.sqrt(((c - q) ** 2).sum(1)).min() for q in stop]
    j = int(np.argmax(sd))
    bx, bz = (float(v) for v in stop[j])
    ex, ez = quads[entry].centre[0], quads[entry].centre[2]
    if math.dist((ex, ez), (bx, bz)) < PIT_BOX_MIN_RUN:
        raise ConvertError(f"{course.name}: the pit box lies {math.dist((ex, ez), (bx, bz)):.0f} units from the entry quad")
    k = int(np.argmin(((line - np.array([bx, bz])) ** 2).sum(1)))      # the lane's direction beside the box (PIT00 turns back to
    a_, b_ = line[max(0, k - 1)], line[min(len(line) - 1, k + 1)]        # the road after it)
    heading = round(-math.atan2(b_[0] - a_[0], b_[1] - a_[1]) * 65536 / (2 * math.pi)) % 65536
    _, y = ground.probe(bx, bz, href, max_dy=10.0)
    return PitLane([tuple(map(float, p)) for p in line], quads, entry, (bx, float(y if y is not None else href), bz, int(heading)))


def resample_open(p: np.ndarray, step: float) -> np.ndarray:
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    t = np.arange(0.0, s[-1] + 1e-9, step)
    return np.stack([np.interp(t, s, p[:, j]) for j in range(p.shape[1])], 1)


def tangents_open(p: np.ndarray) -> np.ndarray:
    d = np.empty_like(p)
    d[1:-1] = p[2:] - p[:-2]
    d[0], d[-1] = p[1] - p[0], p[-1] - p[-2]
    return d / np.linalg.norm(d, axis=1, keepdims=True)


# ---- scenery -----------------------------------------------------------------------------------------------------

def _convex(q, nrm) -> bool:
    s = [float(np.cross(q[(k + 1) % 4] - q[k], q[(k + 2) % 4] - q[(k + 1) % 4]) @ nrm) for k in range(4)]
    return all(v > 1e-6 for v in s) or all(v < -1e-6 for v in s)


def pair_triangles(tris: np.ndarray, rgb: np.ndarray, colour_tol: int = 6, cos_tol: float = 0.995) -> tuple[list[WorldQuad], int]:
    """Triangles as WorldQuads, two triangles sharing their LONGEST edges merged into one quad when they are one colour (within
    `colour_tol`), coplanar (normals within `cos_tol`) and convex together (greedy, largest first); an unpaired triangle keeps
    its third corner repeated, the Saturn path's convention. Returns (quads, pairs made)."""
    key = lambda p: (round(float(p[0]), 3), round(float(p[1]), 3), round(float(p[2]), 3))
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.where(ln > 0, ln, 1.0)[:, None]
    edges = defaultdict(list)
    for i in range(len(tris)):
        for e in ((0, 1), (1, 2), (2, 0)):
            a, b = key(tris[i, e[0]]), key(tris[i, e[1]])
            edges[(min(a, b), max(a, b))].append((i, e))
    el = np.stack([np.linalg.norm(tris[:, 1] - tris[:, 0], axis=1), np.linalg.norm(tris[:, 2] - tris[:, 1], axis=1),
                   np.linalg.norm(tris[:, 0] - tris[:, 2], axis=1)], 1)
    longest = [((0, 1), (1, 2), (2, 0))[k] for k in np.argmax(el, 1)]    # each triangle's longest edge
    used = np.zeros(len(tris), bool)
    out, pairs = [], 0
    for i in np.argsort(-ln, kind="stable"):
        if used[i]:
            continue
        used[i] = True
        best = None
        if ln[i] > 0:
            for e in ((0, 1), (1, 2), (2, 0)):
                if e != longest[i]:                    # only along the diagonal: a pair across two rectangles (a road dash and
                    continue                           # the next) made a long parallelogram the road's faces overdrew (§10)
                a, b = key(tris[i, e[0]]), key(tris[i, e[1]])
                for j, ej in edges[(min(a, b), max(a, b))]:
                    if used[j] or ln[j] == 0 or ej != longest[j] or np.abs(rgb[i].astype(int) - rgb[j].astype(int)).max() > colour_tol \
                            or abs(float(nrm[i] @ nrm[j])) < cos_tol:
                        continue
                    q = [tris[i, 3 - e[0] - e[1]], tris[i, e[0]], tris[j, 3 - ej[0] - ej[1]], tris[i, e[1]]]
                    if _convex(q, nrm[i]):
                        best = (j, q)
                        break
                if best:
                    break
        colour = tuple(int(v) for v in rgb[i])
        if best:
            used[best[0]] = True
            pairs += 1
            out.append(WorldQuad(tuple(tuple(float(v) for v in p) for p in best[1]), colour))
        else:
            t = [tuple(float(v) for v in p) for p in tris[i]]
            out.append(WorldQuad((t[0], t[1], t[2], t[2]), colour))
    return out, pairs


FLAT_NY = 0.7                       # a face this level (|ny| of its unit normal) is ground: lit as the originals' ground


def orient(quads: list[WorldQuad], road) -> tuple[list[WorldQuad], int]:
    """Each face wound so that the lighting normal its corners give (`geometry._normal`, Newell) points the way the arcade's own
    faces' do: away from the side that is seen. The originals' ground normals point down (Big Forest: 20 362 of 20 362), as the
    Saturn path's ground does (1 272 of 1 272 level faces on Pacific Coast). The PS2 frame is a point reflection of the arcade's,
    so its windings come out the other way (82 % of Island's level faces pointed up and were lit as facing away: the road and the
    ground near black). Level faces (|ny| > FLAT_NY) point down; the others point away from the nearest point of `road` (the
    centreline, x z), the side a driver sees being the road's. Returns (faces, faces turned)."""
    from vrtools.convert.geometry import _normal
    pts = np.asarray(road, float)
    out, turned = [], 0
    for q in quads:
        n = _normal(q.p)
        if abs(n[1]) > FLAT_NY:
            flip = n[1] > 0
        else:
            cx, cz = sum(p[0] for p in q.p) / 4, sum(p[2] for p in q.p) / 4
            k = int(np.argmin((pts[:, 0] - cx) ** 2 + (pts[:, 1] - cz) ** 2))
            flip = n[0] * (cx - pts[k, 0]) + n[2] * (cz - pts[k, 1]) < 0
        if flip:
            a, b, c, d = q.p
            q = WorldQuad((a, d, c, b), q.rgb, q.one_sided, q.palette)
            turned += 1
        out.append(q)
    return out, turned


NEAR_PROPS = 40.0                   # the one-player set's trees and props this near the road replace the split-screen set's (§8)


def _faces(meshes, frame: Frame, atlas, atlases: dict | None = None) -> tuple[list[WorldQuad], int, int]:
    atlases = atlases or {}
    if not meshes:
        return [], 0, 0
    tris = np.concatenate([frame.pts(m.triangles) for m in meshes])
    rgb = np.concatenate([swatch_colours(m, atlases.get(m.texture_name.split(".")[0].lower(), atlas), shade=False)   # each list's
                          for m in meshes])        # own atlas (Beltway's cous00b); unshaded: the arcade lights each face itself
    quads, pairs = pair_triangles(tris, rgb)                                         # (the PS2's vertex grey is its baked light)
    return quads, len(tris), pairs


def _road_distance(quads: list[WorldQuad], road) -> np.ndarray:
    pts = np.asarray(road, float)
    cen = np.array([[sum(p[0] for p in q.p) / 4, sum(p[2] for p in q.p) / 4] for q in quads]).reshape(-1, 2)
    out = np.empty(len(cen))
    for i in range(0, len(cen), 1024):
        out[i:i + 1024] = np.sqrt(((cen[i:i + 1024, None] - pts[None]) ** 2).sum(2)).min(1)
    return out


FILL_BUCKET = 32.0                  # units: the plan grid `uncovered` buckets the coarse faces by


def uncovered(fine: list[WorldQuad], coarse: list[WorldQuad]) -> list[WorldQuad]:
    """The faces of `fine` whose centre no face of `coarse` covers in plan: ground the split-screen mesh never had (far hills
    behind a ridge, which showed sky through it once the one-player mesh drew the ridge nearer)."""
    buckets: dict = {}
    for q in coarse:
        xs, zs = [p[0] for p in q.p], [p[2] for p in q.p]
        for bx in range(int(min(xs) // FILL_BUCKET), int(max(xs) // FILL_BUCKET) + 1):
            for bz in range(int(min(zs) // FILL_BUCKET), int(max(zs) // FILL_BUCKET) + 1):
                buckets.setdefault((bx, bz), []).append(q)
    out = []
    for q in fine:
        x, z = sum(p[0] for p in q.p) / 4, sum(p[2] for p in q.p) / 4
        cands = buckets.get((int(x // FILL_BUCKET), int(z // FILL_BUCKET)), [])
        if not any(_height_in(np.array(c.p, float), x, z) is not None for c in cands):
            out.append(q)
    return out


def _corner_distance(quads: list[WorldQuad], road) -> np.ndarray:
    """(n, 4): each corner's distance from the road (the nearest of `road`'s points), in plan."""
    pts = np.asarray(road, float)
    cor = np.array([[(p[0], p[2]) for p in q.p] for q in quads]).reshape(-1, 2)
    out = np.empty(len(cor))
    for i in range(0, len(cor), 4096):
        out[i:i + 4096] = np.sqrt(((cor[i:i + 4096, None] - pts[None]) ** 2).sum(2)).min(1)
    return out.reshape(-1, 4)


WATER_BELOW_ROAD = 0.6              # the sea lifted to this far under the lowest road point (§8)


def is_water(q: WorldQuad) -> bool:
    """The PS2's sea faces: level and blue (Island's three sea swatches have blue 189-202, red 62-80)."""
    r, g, b = q.rgb
    return b > r + 60 and b > 150 and max(p[1] for p in q.p) - min(p[1] for p in q.p) < 0.5


def lift_water(quads: list[WorldQuad], road_floor: float) -> tuple[list[WorldQuad], float | None]:
    """The sea plane raised to WATER_BELOW_ROAD under `road_floor` (the lowest road point) when it lies lower. Island's sea is one
    plane at y 27.9 running under the whole course, 1.8 units under its lowest road: from the road, the 2-4-unit coastal berms
    hid it everywhere (the PS2 shows it with its sky dome's sea band). Raised, it meets the low shores. Returns (faces, the
    sea's former height or None)."""
    water = [q for q in quads if is_water(q)]
    if not water:
        return quads, None
    level = float(np.median([q.p[0][1] for q in water]))
    target = road_floor - WATER_BELOW_ROAD
    if level >= target:
        return quads, level
    return [WorldQuad(tuple((p[0], target, p[2]) for p in q.p), q.rgb, q.one_sided, q.palette) if is_water(q) else q
            for q in quads], level


UPRIGHT_KEEP = 60.0                 # upright faces this near the road are never thinned: signs, posts, rails, trees, fronts (§10)


def picture_faces(course: Ps2Course, frame: Frame) -> list[WorldQuad]:
    """The faces the select picture is drawn from (`preview.course_picture`'s `faces`): the split-screen scenery, its props and the
    tunnels' meshes whole, coloured as `scenery`'s, neither thinned nor cut nor the sea lifted (seen from above, the thinned
    set lost Beltway's city blocks and Island's sea beyond 40 units of the road)."""
    return _faces(course.split_sections + course.split_props + course.tunnels, frame, course.atlases["cous00"], course.atlases)[0]


def thin_roadside(quads: list[WorldQuad], thin: float, road, far_cut: float | None = None,
                  upright_keep: float = UPRIGHT_KEEP) -> tuple[list[WorldQuad], int]:
    """The thinning that keeps the roadside: level faces under `thin` xz area farther than 40 units from the road go (as
    `geometry.thin_quads`), upright faces within UPRIGHT_KEEP of the road always stay, and with `far_cut` every face farther
    than that from the road goes. `thin_quads` judged uprights by their xz area too, which they hardly have: it removed
    Island's signs beyond 40 units; Beltway's true-area rule at its slot's room removed its roadside decor (§10). Returns
    (kept, dropped)."""
    from vrtools.convert.geometry import _normal
    if not quads:
        return quads, 0
    p = np.array([q.p for q in quads], float)
    x, z = p[:, :, 0], p[:, :, 2]
    xz = 0.5 * np.abs(np.sum(x * np.roll(z, -1, axis=1) - np.roll(x, -1, axis=1) * z, axis=1))
    level = np.array([abs(_normal(q.p)[1]) > FLAT_NY for q in quads])
    d = _road_distance(quads, road)
    drop = level & (xz < thin) & (d > 40.0)
    if far_cut is not None:
        drop |= d > far_cut
    drop &= ~(~level & (d < upright_keep))
    return [q for q, k in zip(quads, drop) if not k], int(drop.sum())


BANNER_GATE_REACH = 10              # road points: a checkpoint banner this near a gate stands at it


def place_banners(banners: list[list[WorldQuad]], pts, heights, gates: list[int]) -> tuple[list[list[WorldQuad]], list]:
    """The checkpoint banners at their gates. Island's and Mountain's st01 / st02 sit in world coordinates across their gates;
    Beltway's two both sit at the start line (road point 406 of 407), where the PS2 places them from its gates at run time.
    A banner whose nearest road point is farther than BANNER_GATE_REACH from every checkpoint gate (the gates but the start's)
    is moved to the k-th checkpoint gate (st01 the first, st02 the second): turned about y by the road's change of heading
    and carried with the road's height, its offset from the road kept. Returns (banners, [(from point, to point) or None])."""
    c = np.asarray(pts, float)
    n = len(c)
    h = np.asarray(heights, float)
    cps = [g for g in gates if min(g, n - g) > BANNER_GATE_REACH]
    out, moves = [], []
    for k, faces in enumerate(banners):
        if not faces or k >= len(cps):
            out.append(faces); moves.append(None)
            continue
        cen = np.array([p for q in faces for p in q.p]).mean(0)
        src = int(np.argmin(((c - cen[[0, 2]]) ** 2).sum(1)))
        if any(min(abs(src - g), n - abs(src - g)) <= BANNER_GATE_REACH for g in cps):
            out.append(faces); moves.append(None)
            continue
        dst = cps[k]
        heading = lambda i: math.atan2(*(c[(i + 1) % n] - c[i])[::-1])
        a = heading(dst) - heading(src)
        ca, sa = math.cos(a), math.sin(a)

        def move(p):
            dx, dz = p[0] - c[src][0], p[2] - c[src][1]
            return (c[dst][0] + ca * dx - sa * dz, p[1] - h[src] + h[dst], c[dst][1] + sa * dx + ca * dz)
        out.append([WorldQuad(tuple(move(p) for p in q.p), q.rgb, q.one_sided, q.palette) for q in faces])
        moves.append((src, dst))
    return out, moves


def merge_scenery(quads: list[WorldQuad], keep_last: int = 0, windows: bool = False) -> tuple[list[WorldQuad], int]:
    """`merge_coplanar` on every face but the last `keep_last` (the checkpoint banners and the start flags, which `scenery` puts
    last): a banner's "C.P" letters lie on its white panel, and folding them into the panel's colour erased them."""
    if keep_last <= 0:
        return merge_coplanar(quads, windows=windows)
    merged, n = merge_coplanar(quads[:-keep_last], windows=windows)
    return merged + quads[-keep_last:], n


def scenery(course: Ps2Course, frame: Frame, keep_near, thin: float = THIN, road_floor: float | None = None,
            far_cut: float | None = None, upright_keep: float = UPRIGHT_KEEP, near_detail: float | None = None,
            gates: list[int] | None = None, heights=None) -> tuple[list[WorldQuad], dict]:
    """The scenery as WorldQuads: the split-screen set, coloured from the course atlas's swatches (not times the vertex grey: the
    arcade lights the faces; the swatches already sit in the arcade's tones per surface, docs/spike/2026-11-phase90-ps2-disc-recon.md
    §8), triangle pairs merged; the one-player set's trees and props within NEAR_PROPS of `keep_near` (the centreline) replace the
    split-screen set's there. The roadside thinning (`thin_roadside`: level faces under `thin` xz area farther than 40 units
    from the road go, uprights within `upright_keep` stay, every face beyond `far_cut` goes), and every face is wound for the
    arcade's lighting (`orient`). With `near_detail`, the one-player set's ground and terrain (about three times finer) replace
    the split-screen set's within that distance of the road (§12). The banners and flags are added after the thinning: never
    thinned, never merged (`merge_scenery`'s keep_last), at their gates with `gates` and `heights`."""
    atlas = course.atlases["cous00"]
    quads, n, pairs = _faces(course.split_sections, frame, atlas, course.atlases)
    if near_detail is not None:
        fine, nf, pf = _faces(course.sections, frame, atlas, course.atlases)
        # the join closed on the coarse side: a split-screen face goes only when all its corners lie within the radius, a
        # one-player face comes when any corner does, so the two overlap along the join instead of leaving a ring of sky
        # between them (judged by the centres, a coarse face straddling the radius went and nothing covered its outer part)
        fd = _corner_distance(fine, keep_near)
        far_fill = uncovered([q for q, d in zip(fine, fd) if d.min() >= near_detail], quads)
        quads = [q for q, d in zip(quads, _corner_distance(quads, keep_near)) if d.max() >= near_detail] + \
                [q for q, d in zip(fine, fd) if d.min() < near_detail] + far_fill
        n, pairs = n + nf, pairs + pf
    props, n2, p2 = _faces(course.split_props + course.tunnels, frame, atlas, course.atlases)   # §13.4: the tunnels' meshes
                                                                 # (the hill over Island's tunnels) are one set for both modes
    if course.props:
        near, n3, p3 = _faces(course.props, frame, atlas, course.atlases)
        props = [q for q, d in zip(props, _road_distance(props, keep_near)) if d >= NEAR_PROPS] + \
                [q for q, d in zip(near, _road_distance(near, keep_near)) if d < NEAR_PROPS]
        n2, p2 = n2 + n3, p2 + p3
    quads, n, pairs = quads + props, n + n2, pairs + p2
    if not quads:
        raise ConvertError(f"{course.name}: no scenery meshes")
    kept, dropped = thin_roadside(quads, thin, keep_near, far_cut, upright_keep)
    banners = [_faces([m], frame, atlas, course.atlases) for m in course.banners]          # the checkpoint banners and the start
    moves = None                                                                           # flags: never thinned (§10), never merged
    if gates is not None and heights is not None:                                          # (`merge_scenery`), at their gates (§12.6)
        placed, moves = place_banners([b[0] for b in banners], keep_near, heights, gates)
        banners = [(q, b[1], b[2]) for q, b in zip(placed, banners)]
    flags = _faces(course.flags, frame, atlas, course.atlases)
    extra = [q for b in banners for q in b[0]] + flags[0]
    n4, p4 = sum(b[1] for b in banners) + flags[1], sum(b[2] for b in banners) + flags[2]
    kept, n, pairs = kept + extra, n + n4, pairs + p4
    kept, turned = orient(kept, keep_near)
    sea = None
    if road_floor is not None:
        kept, sea = lift_water(kept, road_floor)
    return kept, {"triangles": n, "pairs": pairs, "faces": len(quads), "thinned": dropped, "turned": turned, "sea_level": sea,
                  "banner_faces": len(extra), "banner_moves": moves}


MERGE_COLOUR_TOL = 12               # channel difference under which two faces count as one colour when merging (§11)
MERGE_PLANE_TOL = 0.05              # units a merged polygon's corners may leave its plane


def _poly_key(p) -> tuple:
    return (round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2))


def _clean_poly(poly: list) -> list:
    """Repeated corners and corners on a straight line between their neighbours removed."""
    out = []
    for v in poly:
        if not out or _poly_key(v) != _poly_key(out[-1]):
            out.append(v)
    if len(out) > 1 and _poly_key(out[0]) == _poly_key(out[-1]):
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = np.array(out[i - 1]), np.array(out[i]), np.array(out[(i + 1) % len(out)])
            if np.linalg.norm(np.cross(b - a, c - b)) < 1e-4 * max(1.0, np.linalg.norm(c - a) ** 2):
                out.pop(i)
                changed = True
                break
    return out


def _poly_area(poly: list) -> float:
    """A planar polygon's area (3-D: half the norm of the summed cross products)."""
    p = np.array(poly, float)
    return 0.5 * float(np.linalg.norm(sum(np.cross(p[i], p[(i + 1) % len(p)]) for i in range(len(p)))))


def _convex_poly(poly: list, n) -> bool:
    k = len(poly)
    s = [float(np.cross(np.subtract(poly[(i + 1) % k], poly[i]), np.subtract(poly[(i + 2) % k], poly[(i + 1) % k])) @ n) for i in range(k)]
    return all(v > -1e-6 for v in s) or all(v < 1e-6 for v in s)


def merge_coplanar(quads: list[WorldQuad], upright_only: bool = True, windows: bool = False,
                   colour_tol: int = MERGE_COLOUR_TOL) -> tuple[list[WorldQuad], int]:
    """A building's faces merged: faces in one plane and of one colour (within `colour_tol` a channel) that share a whole edge
    are joined while their union is a convex polygon of at most four corners, repeatedly, so a wall of window bands and
    strips becomes few quads. With `windows`, every face in a plane takes the plane's main colour (by area) first: the
    windows and bands drawn over a wall go into the wall. `upright_only`: level faces (the road, its markings, the ground)
    are left as they are. Returns (faces, merges made)."""
    from vrtools.convert.geometry import _normal
    groups: dict = {}
    keep = []
    for q in quads:
        n = np.array(_normal(q.p))
        if q.one_sided or q.palette is not None or (upright_only and abs(n[1]) > FLAT_NY):
            keep.append(q)
            continue
        if n[np.argmax(np.abs(n))] < 0:
            n = -n
        d = float(n @ np.array(q.p[0]))
        key = (tuple(np.round(n, 2)), round(d, 1))
        groups.setdefault(key, []).append(q)
    merges = 0
    out = list(keep)
    for (nk, _), faces in groups.items():
        n = np.array(nk, float)
        if windows:
            area: dict = {}
            for q in faces:
                p = np.array(q.p, float)
                area[q.rgb] = area.get(q.rgb, 0.0) + 0.5 * float(np.linalg.norm(np.cross(p[2] - p[0], p[3] - p[1])))
            main = max(area, key=area.get)
            faces = [WorldQuad(q.p, main, q.one_sided, q.palette) for q in faces]
        polys = [[_clean_poly(list(q.p)), q.rgb] for q in faces]
        alive = [len(p[0]) >= 3 for p in polys]
        changed = True
        while changed:
            changed = False
            edges: dict = {}
            for i, (poly, _) in enumerate(polys):
                if not alive[i]:
                    continue
                for k in range(len(poly)):
                    a, b = _poly_key(poly[k]), _poly_key(poly[(k + 1) % len(poly)])
                    edges.setdefault((min(a, b), max(a, b)), []).append((i, k))
            touched = set()
            for (_, _), users in edges.items():
                if len(users) != 2:
                    continue
                (i, ki), (j, kj) = users
                if not (alive[i] and alive[j]) or i == j or i in touched or j in touched:
                    continue
                ci, cj = polys[i][1], polys[j][1]
                if max(abs(a - b) for a, b in zip(ci, cj)) > colour_tol:
                    continue
                A, B = polys[i][0], polys[j][0]
                ka, kb = _poly_key(A[ki]), _poly_key(A[(ki + 1) % len(A)])
                # A walked from the shared edge's end round to its start, then B's other corners in its own order
                ra = A[(ki + 1) % len(A):] + A[:(ki + 1) % len(A)]     # from the edge's end (kb) round to its start (ka)
                bk = [_poly_key(v) for v in B]
                if ka not in bk or kb not in bk:
                    continue
                ia, ib, m = bk.index(ka), bk.index(kb), len(B)
                step = 1 if (ia + 1) % m != ib else -1                  # walk B from ka away from kb, round to kb
                walk, t = [], (ia + step) % m
                while t != ib:
                    walk.append(B[t])
                    t = (t + step) % m
                union = ra + walk
                union = _clean_poly(union)
                if not (3 <= len(union) <= 4) or not _convex_poly(union, n):
                    continue
                d0 = float(n @ np.array(union[0]))
                if any(abs(float(n @ np.array(v)) - d0) > MERGE_PLANE_TOL for v in union):
                    continue
                if abs(_poly_area(union) - _poly_area(A) - _poly_area(B)) > 0.01 * (_poly_area(A) + _poly_area(B)) + 1e-6:
                    continue                            # §13.4: the union must cover exactly the two faces (else a hill shows sky)
                polys[i] = [union, ci]
                alive[j] = False
                touched.update((i, j))
                merges += 1
                changed = True
        for (poly, rgb), ok in zip(polys, alive):
            if ok:
                pts = [tuple(float(v) for v in x) for x in poly]
                out.append(WorldQuad(tuple(pts + [pts[-1]] * (4 - len(pts))), rgb))
    return out, merges


# ---- far silhouettes ---------------------------------------------------------------------------------------------

CELL_ORDER_5 = [(dx, dz) for dx in range(-2, 3) for dz in range(-2, 3)]
VIEW_HALF_ANGLE = math.radians(45)  # Phase 28's visible-cell model (out/p28/cellmodel.py): 5 x 5 cells, kept where the square
VIEW_BACK = 10.0                    # meets a +-45 deg wedge from 10 units behind the car (Jaccard 0.84 against the logged lists)
FAR_AREA = 150.0                    # faces of at least this true area are far silhouettes when out of the drawn cells
FAR_MAX = 700.0                     # ... and within this of the camera, ahead
FAR_VOTES = 3                       # road points that must ask for a copy in the same nearer cell


def _cell(x: float, z: float) -> int:
    return (int((x + 1024) // 128) & 15) + 16 * (int((z + 1024) // 128) & 15)


def visible_cells(x: float, z: float, hx: float, hz: float, order=CELL_ORDER_5) -> list[int]:
    """The cells the game draws from a car at (x, z) heading (hx, hz) (Phase 28's model of 0xff7beb..0xff7e1e)."""
    cx, cz = x - VIEW_BACK * hx, z - VIEW_BACK * hz
    c = _cell(cx, cz)
    xc, zc = c & 15, c >> 4
    out = []
    for dx, dz in order:
        X, Z = xc + dx, zc + dz
        if not (0 <= X < 16 and 0 <= Z < 16):
            continue
        x0, z0 = X * 128 - 1024, Z * 128 - 1024
        hit = False
        for u in (0.0, 0.25, 0.5, 0.75, 1.0):
            for v in (0.0, 0.25, 0.5, 0.75, 1.0):
                px, pz = x0 + 128 * u - cx, z0 + 128 * v - cz
                d = math.hypot(px, pz)
                if d < 1e-6 or (px * hx + pz * hz) / d >= math.cos(VIEW_HALF_ANGLE):
                    hit = True
                    break
            if hit:
                break
        if hit:
            out.append(Z * 16 + X)
    return out


def far_copies(quads: list[WorldQuad], pts, area_min: float = FAR_AREA, far_max: float = FAR_MAX,
               votes: int = FAR_VOTES, max_copies: int = 1) -> dict[int, list[WorldQuad]]:
    """Far silhouettes brought in (Phase 31's idea for Metropolis's far buildings, `silhouette.py`): a face of at least
    `area_min` whose own cell the game does not draw from a road point that has it ahead within `far_max` is copied into the
    drawn cell nearest it from there; a copy goes to the cell most road points ask for (at least `votes`), in both directions,
    and to the next most asked-for cells up to `max_copies` cells.
    Returns {cell: copies}, for the copies to be added to those cells' objects."""
    pts = np.asarray(pts, float)
    n = len(pts)
    big = [q for q in quads if 0.5 * np.linalg.norm(np.cross(np.subtract(q.p[2], q.p[0]), np.subtract(q.p[3], q.p[1]))) >= area_min]
    if not big:
        return {}
    cen = np.array([[sum(p[0] for p in q.p) / 4, sum(p[2] for p in q.p) / 4] for q in big])
    own = np.array([_cell(x, z) for x, z in cen])
    ballots: list[dict] = [dict() for _ in big]
    for direction in (1, -1):
        for k in range(n):
            a, b = pts[(k - direction) % n], pts[(k + direction) % n]
            h = (b - a) / (np.linalg.norm(b - a) or 1.0)
            cam = pts[k] - VIEW_BACK * h
            vis = visible_cells(pts[k][0], pts[k][1], h[0], h[1])
            vset = set(vis)
            rel = cen - cam
            dist = np.linalg.norm(rel, axis=1)
            ahead = (rel @ h) / np.maximum(dist, 1e-6) >= math.cos(VIEW_HALF_ANGLE)
            vc = np.array([[(c & 15) * 128 - 960, (c >> 4) * 128 - 960] for c in vis])
            for i in np.flatnonzero(ahead & (dist <= far_max)):
                if own[i] in vset:
                    continue
                t = vis[int(np.argmin(((vc - cen[i]) ** 2).sum(1)))]
                ballots[i][t] = ballots[i].get(t, 0) + 1
    out: dict[int, list[WorldQuad]] = {}
    for q, bal in zip(big, ballots):
        for t, v in sorted(bal.items(), key=lambda kv: -kv[1])[:max_copies]:
            if v >= votes:
                out.setdefault(t, []).append(q)
    return out


# ---- gates, tunnels, backdrop ------------------------------------------------------------------------------------

def gate_points(course: Ps2Course, frame: Frame, pts) -> list[int]:
    """The road points the `chk.bin` gates stand across (each gate quad's centre within GATE_REACH of the centreline), sorted."""
    if course.checkpoints is None:
        return []
    quads = frame.pts(course.checkpoints.positions).reshape(-1, 6, 3).mean(axis=1)[:, [0, 2]]
    c = np.array(pts)
    out = set()
    for q in quads:
        d = ((c - q) ** 2).sum(1)
        k = int(np.argmin(d))
        if d[k] <= GATE_REACH ** 2:
            out.add(k)
    return sorted(out)


def tunnel_stretches(course: Ps2Course, frame: Frame, pts, gap: int = 2) -> tuple[tuple[int, int], ...]:
    """(first, last) road points within TUNNEL_REACH of a tunnel lamp (the `tunNN.bin` meshes), runs closer than `gap` joined."""
    if not course.tunnels:
        return ()
    v = np.concatenate([frame.pts(m.positions)[:, [0, 2]] for m in course.tunnels])
    c = np.array(pts)
    near = [k for k in range(len(c)) if ((v - c[k]) ** 2).sum(1).min() <= TUNNEL_REACH ** 2]
    runs: list[list[int]] = []
    for k in near:
        if runs and k <= runs[-1][1] + gap:
            runs[-1][1] = k
        else:
            runs.append([k, k])
    return tuple((a, b) for a, b in runs)


COVER_CLEAR = (3.0, 40.0)            # a face this far above the road's height at a road point covers it (an overpass, a roof)
COVER_MIN_RUN = 2                    # road points: a shorter run of cover is a sign or a banner, not a roof


def covered_stretches(quads: list[WorldQuad], pts, heights, gap: int = 2) -> tuple[tuple[int, int], ...]:
    """(first, last) road points with a face straight above the road (COVER_CLEAR over its height there): the overpasses and roofs
    the storm must not rain under; runs closer than `gap` joined, runs shorter than COVER_MIN_RUN points left out. The checkpoint
    banners and the start flags span the road too: they are left out by the run length (a banner covers one point or two)."""
    c = np.asarray(pts, float)
    h = np.asarray(heights, float)
    if not quads:
        return ()
    p = np.array([q.p for q in quads], float)
    lo, hi = p[:, :, [0, 2]].min(1), p[:, :, [0, 2]].max(1)
    hit = []
    for k in range(len(c)):
        x, z = c[k]
        cand = np.flatnonzero((lo[:, 0] <= x) & (x <= hi[:, 0]) & (lo[:, 1] <= z) & (z <= hi[:, 1]))
        for i in cand:
            y = _height_in(p[i], x, z)
            if y is not None and COVER_CLEAR[0] <= y - h[k] <= COVER_CLEAR[1]:
                hit.append(k)
                break
    runs: list[list[int]] = []
    for k in hit:
        if runs and k <= runs[-1][1] + gap:
            runs[-1][1] = k
        else:
            runs.append([k, k])
    return tuple((a, b) for a, b in runs if b - a + 1 >= COVER_MIN_RUN)


def _height_in(quad: np.ndarray, x: float, z: float) -> float | None:
    """The quad's height over (x, z) when (x, z) lies inside one of its two triangles (0, 1, 2), (0, 2, 3) in plan, else None."""
    for a, b, c in ((0, 1, 2), (0, 2, 3)):
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = quad[a], quad[b], quad[c]
        det = (x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)
        if abs(det) < 1e-9:
            continue
        u = ((x - x0) * (z2 - z0) - (x2 - x0) * (z - z0)) / det
        v = ((x1 - x0) * (z - z0) - (x - x0) * (z1 - z0)) / det
        if u >= 0 and v >= 0 and u + v <= 1:
            return y0 + u * (y1 - y0) + v * (y2 - y0)
    return None


def join_stretches(*groups, gap: int = 2) -> tuple[tuple[int, int], ...]:
    """The union of (first, last) stretches, runs closer than `gap` joined."""
    out: list[list[int]] = []
    for a, b in sorted(x for g in groups for x in g):
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return tuple((a, b) for a, b in out)


def panorama(course: Ps2Course):
    """The sky's two halves side by side as a Saturn-shaped panorama (1280 × 256, 256 RGB555 colours) for `convert_panorama`:
    the sky in rows 0..103 (the Saturn's horizon near row 100), below it the sea picture where the course has one, else the
    sky's last row. The halves' mapping onto a turn is assumed (recon §6.5)."""
    from vrtools.convert.backdrop import _kmeans, _nearest
    from vrtools.saturn.backdrop import SaturnPanorama
    sky = np.concatenate([course.skies["sky0a"].rgb(), course.skies["sky0b"].rgb()], axis=1).astype(float)
    below = (np.concatenate([course.skies["sea0"].rgb()] * 2, axis=1).astype(float) if "sea0" in course.skies
             else np.repeat(sky[-1:], 64, axis=0))

    def fit(img, h, w):
        ys = np.clip(((np.arange(h) + 0.5) * img.shape[0] / h).astype(int), 0, img.shape[0] - 1)
        xs = np.clip(((np.arange(w) + 0.5) * img.shape[1] / w).astype(int), 0, img.shape[1] - 1)
        return img[ys][:, xs]
    img = np.concatenate([fit(sky, 104, 1280), fit(below, 152, 1280)], axis=0)
    px = img.reshape(-1, 3) / 8.0
    cent, _ = _kmeans(px[::7], 256, iters=6)
    lab = _nearest(px, cent)
    pal = [int(min(31, round(c[0]))) | int(min(31, round(c[1]))) << 5 | int(min(31, round(c[2]))) << 10 for c in cent]
    pal += [0] * (256 - len(pal))
    return SaturnPanorama(lab.reshape(256, 1280).astype(np.uint8), tuple(pal))


# ---- the whole -------------------------------------------------------------------------------------------------------

@dataclass
class Ps2Conversion:
    name: str
    frame: Frame
    lap: Lap
    sections: list[Section]
    centreline: list[tuple[float, float]]
    collision: Collision
    cells: dict[int, int]
    attitude: list[tuple[int, int]]
    height: object
    scenery: list[WorldQuad]
    gates: list[int]
    tunnels: tuple[tuple[int, int], ...]
    report: dict = field(default_factory=dict)
    lanes: list | None = None              # (left, right) AI offset scales per centreline point (`lane_scales`)
    pit: PitLane | None = None
    pit_quad: int | None = None            # index of the pit entry quad in `collision.quads` (its duplicate follows)


def _racing_side(course: Ps2Course, frame: Frame, secs: list[Section]) -> int:
    """The side (+1 right, -1 left) of the PS2's racing line (NORMAL.PAT) beside the dividers (`Section.divider`): the
    carriageway the PS2 sends its cars down. +1 when there is no divider."""
    div = [s for s in secs if s.divider is not None]
    if not div:
        return 1
    line = frame.pts(course.paths["NORMAL"])[:, [0, 2]]
    total = 0.0
    for s in div:
        j = int(np.argmin(((line - np.array(s.centre)) ** 2).sum(1)))
        r = (s.dirn[1], -s.dirn[0])
        total += (line[j][0] - s.centre[0]) * r[0] + (line[j][1] - s.centre[1]) * r[1]
    return 1 if total >= 0 else -1


def convert(course: Ps2Course, frame: Frame, pit: bool = False, **detail) -> Ps2Conversion:
    """Everything the arcade build takes from the course, in the arcade frame `frame`; with `pit`, its pit lane (`pit_lane`) in
    the collision's tarmac, the entry quad doubled, and `pit_quad` naming it. `detail`: scenery's other options (far_cut,
    upright_keep, near_detail), passed through."""
    if "NORMAL" not in course.paths:
        raise ConvertError(f"{course.name}: no racing line (NORMAL.PAT)")
    ground, walls = Ground(course.road, frame), Walls(course.walls, frame)
    lap, secs = build_lap(ground, walls, frame.pts(course.paths["NORMAL"])[:, [0, 2]])
    pts = centreline(lap)
    lane = pit_lane(course, frame, ground, secs, pts) if pit else None
    col, cells = collision(secs, lane.quads if lane else (), lane.entry if lane else None)
    pit_quad = col.n_tarmac - (len(lane.quads) + 1) + lane.entry if lane else None
    cs, hs = np.array([s.centre for s in secs]), np.array([s.height for s in secs])
    heights = [hs[int(np.argmin(((cs - p) ** 2).sum(1)))] for p in pts]
    quads, srep = scenery(course, frame, pts, road_floor=min(s.height for s in secs), gates=gate_points(course, frame, pts), heights=heights, **detail)
    widths = [s.right - s.left for s in secs]
    rep = {"sections": len(secs), "lap_units": round(lap.length, 1), "road_points": len(pts),
           "width_median": float(np.median(widths)), "quads": len(col.quads), "tarmac": col.n_tarmac, "merged": col.merged,
           "tgp_words": col.list_words + 16 * len(col.quads),
           "divided": sum(1 for a, b in zip(secs, secs[1:] + secs[:1]) if a.divider is not None or b.divider is not None),
           **{f"scenery_{k}": v for k, v in srep.items()}}
    return Ps2Conversion(course.name, frame, lap, secs, pts, col, cells, attitude(lap, secs, pts), height_fn(secs), quads,
                         gate_points(course, frame, pts), tunnel_stretches(course, frame, pts), rep,
                         lane_scales(secs, pts, _racing_side(course, frame, secs), walls), lane, pit_quad)
