"""Weather stage 3: where the cover is, from the set's own drawn faces (spec 5.4). For every flagged stretch (the arcade's tunnel flag,
bit 7 of a road quad's segment flag: Metropolis 251-311 and 50-62 with its pit lane, Alpine 108-146, Bay Bridge's own quads 69-88)
a `Stretch`: road-line chords ("boxes": origin, axis, length, the roof's lateral extent, the walls) and its two mouths (where the
roof ends on the centreline: the position at road height, the outward direction, the opening between the walls, the roof's height),
and per box which mouth can be seen from inside it. One table serves both directions (the reverse variants draw the same faces).

Ported from spike 57 (`spike/p57_geom.py`, branch `spike57-rain-tunnels`; the same values, rewritten): per road point of the
centreline the road under it (the drawn face nearest the previous point's road), the roof over it (the lowest face 2..60 above),
the roof's lateral extent (vertical rays every 0.5 unit across) and the side walls (horizontal rays 3 units above the road); then
samples every 1/20 of a point give the roofed run and its ends (the mouths); the run is cut into chords within `ang` degrees of every
segment they cover (and, with `ext_split`, where the roof widens by more than 4 units); interior chord joints overlap by 1.5 units,
the mouths are exact.

THE ROOF BY METROPOLIS'S PITS (road points 50-62) is not marched: its stretches are the prototype's measurements of its drawn faces
(spikes 61, 65 and 68, Pascal's "short tunnel is good" on the last), checked against the set at build time (`check_pits_roof`):
walls up to the roof at x -120 (outer), the divider (x -102.4 mid-roof, angling out to -99.9 at the entrance and -99.8 at the exit),
x -80.9 (the lane's) and -70.8; the roof slab's underside at y 1.2 over x -120..-84 from z 222.4 to 339.7; both ends open under the
roof, a fascia above. It is two closed stretches, the road (x -120..-99.1) and the pit lane (-99.1..-70.8), so the camera's own lane
picks its own end opening; the boxes meet mid-divider (no gap). Their mouths carry the curtain's placement bounds (the corridor's
walls beyond each end: x -120.6..-82.5 before the entrance, -119.9..-80.8 after the exit) and the end structure's extent on the end
plane (`kbox`: the fascia, roof edge, wall and divider ends), and their boxes the bit ROOF: the renderer's sort cannot be trusted with
this structure's few huge polygons, so its exit rain is placed along sight lines through the opening and drawn drop by drop at the
edges (weather/cover.py)."""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field, replace

import numpy as np

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet

ROOF = (2.0, 60.0)                      # a face this much above the road is a roof over it
SAMPLES = 20                            # samples a road point along the centreline
BRIDGE = 4                              # roofed samples this few apart are one run
JOINT = 1.5                             # interior chord joints overlap by this (no wedge gaps at bends); the mouths exact
METROPOLIS, ALPINE, BAY_BRIDGE = 6, 3, 1
BAY_QUADS = (69, 88)                    # Bay Bridge's own tunnel (the game's flag 0x81 on these quads; the stretch's road points)
# vis bits of a box: which mouth (0, 1) its middle can see; ROOF: a closed roof the sort cannot be trusted with (the curtain drawn
# only along sight lines through the end opening, drop by drop at its edges, no splashes); OPEN (spike 57, unused since spike 61)
SEE0, SEE1, OPEN, ROOFED = 1, 2, 4, 8
# The flagged stretches: (entry, first, last, ang, ext_split) marched from the faces; the pits roof (Metropolis 50-62) is measured
MARCHED = ((METROPOLIS, 251, 311, 4.0, True), (ALPINE, 108, 146, 4.0, True), (BAY_BRIDGE, BAY_QUADS[0], BAY_QUADS[1], 4.0, True))
PITS_ROOF = (50, 62)
# Phase 90 (packs): the tables are the course's, not the menu entry's: MARCHED's entries are pack 1's, read as the names below, so a
# course keeps its table wherever a pack puts it. A course of no Saturn or arcade name (a PS2 course of pack 2) is marched along its
# own flagged stretches (`flagged_stretches`: its converter flags the tunnels and overpasses it finds).
NAME_OF_ENTRY = {METROPOLIS: "METROPOLIS", ALPINE: "ALPINE", BAY_BRIDGE: "BAY BRIDGE"}
KNOWN_NAMES = ("BIG FOREST", "BAY BRIDGE", "ACROPOLIS", "ALPINE", "AMAZON FALLS", "DIABLO CANYON", "METROPOLIS", "PACIFIC COAST",
               "SURFERS OVAL", "SURFERS ROAD")
PW, PHK, PHMAX, DEPTH = 10.0, 2.5, 25.0, 60.0     # a marched mouth's curtain: lateral beyond the opening, height k x H (at most),
                                                  # depth beyond the mouth (spike 57's PW, PHK/PHMAX and D)


@dataclass(frozen=True)
class Box:
    o: tuple[float, float]              # origin (x, z)
    a: tuple[float, float]              # axis (unit, along travel in the normal direction)
    L: float                            # length
    s: tuple[float, float]              # lateral extent on n = (-az, ax): the roof's (or the walls', the larger)
    w: tuple[float, float]              # the walls' lateral bounds
    t: tuple[float, float]              # road points covered
    vis: int                            # SEE0 | SEE1 | ROOFED


@dataclass(frozen=True)
class Mouth:
    c: tuple[float, float, float]       # centre at road height
    o: tuple[float, float]              # outward (unit)
    s: tuple[float, float]              # the opening's lateral bounds on n_o = (-oz, ox)
    H: float                            # the roof's height over the road
    t: float                            # road point
    p: tuple[float, float] | None = None              # the curtain's lateral placement bounds (None: the opening +- PW)
    kbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)   # the end structure's x and y extent on the end plane


@dataclass(frozen=True)
class Stretch:
    boxes: tuple[Box, ...]
    mouths: tuple[Mouth, Mouth]
    t: tuple[float, float]


# ==================================================================================================================== the faces
def course_faces(rs: RomSet, entry: int) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """The menu entry's drawn triangles (n x 3 x 3, from its tile table) and its centreline (road line 0, (x, z) per point)."""
    from vrtools.arcade.course import course_entry_at, road_lines, tile_table_at
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.polyrom import decode_object, quads
    e = decode_directory(rs)[entry]
    faces = np.array([q.p for t in tile_table_at(rs, e.tile_table) if t.size
                      for q in quads(decode_object(rs.polygons, t.poly_adr, t.size), t.tex_adr)], dtype=np.float64)
    tris = np.concatenate([faces[:, [0, 1, 2]], faces[:, [0, 2, 3]]])
    ce = course_entry_at(rs, e.bank, window_base=e.header_base)
    return tris, [(p.x, p.z) for p in road_lines(rs, ce)[0]]


class Caster:
    """Rays against the triangles (Moller-Trumbore), with a bounding-box prefilter."""

    def __init__(self, tris: np.ndarray):
        self.t, self.lo, self.hi = tris, tris.min(1), tris.max(1)

    def near(self, x: float, z: float, r: float) -> np.ndarray:
        m = (self.lo[:, 0] <= x + r) & (self.hi[:, 0] >= x - r) & (self.lo[:, 2] <= z + r) & (self.hi[:, 2] >= z - r)
        return self.t[m]

    @staticmethod
    def ray(t: np.ndarray, o, d) -> np.ndarray:
        """The distances along d (unit) from o to each triangle of t it hits."""
        if len(t) == 0:
            return np.zeros(0)
        e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
        p = np.cross(d, e2)
        det = (e1 * p).sum(1)
        ok = np.abs(det) > 1e-9
        inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
        s = o - t[:, 0]
        u = (s * p).sum(1) * inv
        q = np.cross(s, e1)
        v = (q * d).sum(1) * inv
        w = (e2 * q).sum(1) * inv
        hit = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (w > 1e-4)
        return w[hit]

    def heights(self, x: float, z: float, r: float = 1.0, t: np.ndarray | None = None) -> np.ndarray:
        """The heights of every face over (x, z) (a vertical ray from y 200)."""
        tt = self.near(x, z, r) if t is None else t
        return 200.0 - self.ray(tt, np.array([x, 200.0, z]), np.array([0.0, -1.0, 0.0]))

    def roof_over(self, x: float, z: float, road: float) -> float | None:
        """The lowest roof's height over the road at (x, z), or None."""
        ys = self.heights(x, z)
        a = ys[(ys > road + ROOF[0]) & (ys < road + ROOF[1])]
        return float(a.min() - road) if len(a) else None


def profile(c: Caster, line, first: int, last: int) -> list[dict]:
    """Per road point first..last (wrapped): position, travel axis, road height, roof height (or None), the roof's lateral extent
    each side and the walls each side (distance or None)."""
    n, prev_y, rows = len(line), None, []
    for i in range(first, last + 1):
        x, z = line[i % n]
        xa, za = line[(i - 1) % n]
        xb, zb = line[(i + 1) % n]
        dx, dz = xb - xa, zb - za
        L = math.hypot(dx, dz)
        ax, az = dx / L, dz / L
        lx, lz = -az, ax
        t = c.near(x, z, 40)
        ys = sorted(c.heights(x, z, t=t))
        if prev_y is None:
            road = min(ys) if ys else float("nan")
        else:
            cand = [y for y in ys if abs(y - prev_y) < 4]
            road = min(cand, key=lambda y: abs(y - prev_y)) if cand else (min(ys) if ys else float("nan"))
        prev_y = road
        above = [y for y in ys if road + ROOF[0] < y < road + ROOF[1]]
        roof = min(above) if above else None
        ext = []
        for side in (-1, 1):                        # march across: a roof over the local floor (a lane, a kerb) extends it; a face
            k = last_roof = 0.0                     # without a roof, or a gap of more than 3 units with no face, ends it
            while k < 40:
                k += 0.5
                px, pz = x + side * k * lx, z + side * k * lz
                yy = c.heights(px, pz)
                lo = yy.min() if len(yy) else road
                if ((yy > lo + ROOF[0]) & (yy < lo + ROOF[1])).any():
                    last_roof = k
                elif len(yy) or k - last_roof > 3.0:
                    break
            ext.append(last_roof if roof else 0.0)
        walls = []
        for side in (-1, 1):
            hit = c.ray(t, np.array([x, road + 3.0, z]), np.array([side * lx, 0.0, side * lz]))
            walls.append(float(hit.min()) if len(hit) else None)
        rows.append(dict(i=i, x=x, z=z, road=road, roof=roof, ext=ext, walls=walls))
    return rows


def stretch_table(c: Caster, line, first: int, last: int, *, ang: float = 4.0, lmax: float = 80.0, ext_split: bool = True) -> Stretch:
    """One flagged stretch (road points first..last) as boxes and mouths (the module docstring)."""
    rows = profile(c, line, first - 4, last + 4)
    by_i = {r["i"]: r for r in rows}

    def at(t):
        i = int(math.floor(t))
        f = t - i
        r0, r1 = by_i[i], by_i[i + 1]
        return (r0["x"] + f * (r1["x"] - r0["x"]), r0["road"] + f * (r1["road"] - r0["road"]), r0["z"] + f * (r1["z"] - r0["z"]))

    def tangent(t):
        i = int(math.floor(t))
        r0, r1 = by_i[i], by_i[i + 1]
        dx, dz = r1["x"] - r0["x"], r1["z"] - r0["z"]
        L = math.hypot(dx, dz)
        return dx / L, dz / L

    S = []
    for r0, r1 in zip(rows, rows[1:]):
        for j in range(SAMPLES):
            f = j / SAMPLES
            x, z, y = (r0["x"] + f * (r1["x"] - r0["x"]), r0["z"] + f * (r1["z"] - r0["z"]), r0["road"] + f * (r1["road"] - r0["road"]))
            S.append((r0["i"] + f, x, y, z, c.roof_over(x, z, y)))
    on = [k for k, s in enumerate(S) if s[4] is not None]
    if not on:
        raise PatchError(f"no roof drawn over road points {first}-{last}")
    runs, cur = [], [on[0]]
    for k in on[1:]:
        if k - cur[-1] <= BRIDGE:
            cur.append(k)
        else:
            runs.append(cur)
            cur = [k]
    runs.append(cur)
    run = max(runs, key=len)
    t0, t1 = S[run[0]][0], S[run[-1]][0]
    ts = [t0] + [float(i) for i in range(math.ceil(t0), math.floor(t1) + 1) if t0 < i < t1] + [t1]
    spans, a = [], 0
    while a < len(ts) - 1:
        b = a + 1
        while b + 1 < len(ts):
            pa, pb = at(ts[a]), at(ts[b + 1])
            dx, dz = pb[0] - pa[0], pb[2] - pa[2]
            L = math.hypot(dx, dz)
            ok = L <= lmax
            e0 = [r["ext"] for r in rows if r["i"] == round(ts[a])]
            eb = [r["ext"] for r in rows if r["i"] == round(ts[b + 1])]
            if e0 and eb and ext_split:
                ok = ok and abs(e0[0][0] - eb[0][0]) <= 4 and abs(e0[0][1] - eb[0][1]) <= 4
            for k in range(a, b + 1):
                q0, q1 = at(ts[k]), at(ts[k + 1])
                sx, sz = q1[0] - q0[0], q1[2] - q0[2]
                ok = ok and (sx * dx + sz * dz) / (math.hypot(sx, sz) * L + 1e-9) > math.cos(math.radians(ang))
            if not ok:
                break
            b += 1
        spans.append((ts[a], ts[b]))
        a = b
    boxes = []
    for bi, (ta, tb) in enumerate(spans):
        pa, pb = at(ta), at(tb)
        dx, dz = pb[0] - pa[0], pb[2] - pa[2]
        L = math.hypot(dx, dz)
        ax, az = dx / L, dz / L
        ext0 = max([r["ext"][0] for r in rows if ta - 0.5 <= r["i"] <= tb + 0.5 and r["roof"] is not None] + [0.0])
        ext1 = max([r["ext"][1] for r in rows if ta - 0.5 <= r["i"] <= tb + 0.5 and r["roof"] is not None] + [0.0])
        w0 = min([r["walls"][0] or 40.0 for r in rows if ta <= r["i"] <= tb] or [ext0])
        w1 = min([r["walls"][1] or 40.0 for r in rows if ta <= r["i"] <= tb] or [ext1])
        pre = JOINT if bi > 0 else 0.0
        post = JOINT if bi < len(spans) - 1 else 0.0
        boxes.append(Box((pa[0] - pre * ax, pa[2] - pre * az), (ax, az), L + pre + post, (-max(ext0, w0), max(ext1, w1)),
                         (-w0, w1), (ta, tb), 0))
    mouths = []
    for k, (t, tin) in enumerate(((t0, t0 + 0.3), (t1, t1 - 0.3))):
        x, y, z = at(t)
        tx, tz = tangent(min(max(t, t0), t1 - 1e-6))
        ox, oz = (-tx, -tz) if k == 0 else (tx, tz)
        xi, yi, zi = at(tin)
        H = c.roof_over(xi, zi, yi) or 8.0
        rin = min(rows, key=lambda r: abs(r["i"] - tin))
        w0, w1 = rin["walls"][0] or 20.0, rin["walls"][1] or 20.0
        mouths.append(Mouth((x, float(y), z), (ox, oz), (-w1, w0) if k == 0 else (-w0, w1), H, t))

    def inside_walls(px, pz, shrink=1.0):
        for bx in boxes:
            u = (px - bx.o[0]) * bx.a[0] + (pz - bx.o[1]) * bx.a[1]
            s = (pz - bx.o[1]) * bx.a[0] - (px - bx.o[0]) * bx.a[1]
            if -0.5 <= u <= bx.L + 0.5 and bx.w[0] + shrink <= s <= bx.w[1] - shrink:
                return True
        return False
    out = []
    for bx in boxes:                                # a mouth is seen from a box when the sight line from its middle stays inside walls
        mx, mz = bx.o[0] + bx.a[0] * bx.L / 2, bx.o[1] + bx.a[1] * bx.L / 2
        vis = 0
        for k, mo in enumerate(mouths):
            cx, cz = mo.c[0], mo.c[2]
            n = max(2, int(math.hypot(cx - mx, cz - mz) / 2))
            if all(inside_walls(mx + (cx - mx) * j / n, mz + (cz - mz) * j / n) for j in range(int(n * 0.98) + 1)):
                vis |= 1 << k
        out.append(replace(bx, vis=vis))
    return Stretch(tuple(out), (mouths[0], mouths[1]), (t0, t1))


# ==================================================================================================================== the pits roof
ROOF_Z, ROOF_ROAD, ROOF_Y = (222.4, 339.7), (-10.45, -6.47), 1.2
ROOF_WALLS = {-111.0: (-120.0, -102.4), -89.65: (-98.4, -80.9)}    # mid-roof: the outer wall and the divider; the divider and the lane's


def pits_roof() -> tuple[Stretch, Stretch]:
    """The road and the pit lane under the roof by Metropolis's pits, as measured (spikes 61, 65, 68; the module docstring). The
    boxes' lateral is n = (-1, 0) (s = xc - x); a mouth's on n_o = (-oz, ox)."""
    (z0, z1), (y0, y1), roof = ROOF_Z, ROOF_ROAD, ROOF_Y

    def stretch(xc, smin, smax, o0, o1, p0, p1):
        box = Box((xc, z0), (0.0, 1.0), z1 - z0, (smin, smax), (smin, smax), (49.5, 61.3), SEE0 | SEE1 | ROOFED)
        m0 = Mouth((xc, y0, z0), (0.0, -1.0), o0, roof - y0, 49.5, p0, (-145.9, -70.8, -10.6, 58.7))
        m1 = Mouth((xc, y1, z1), (0.0, 1.0), o1, roof - y1, 61.3, p1, (-154.5, -70.8, -7.0, 58.7))
        return Stretch((box,), (m0, m1), (49.5, 61.3))
    road = stretch(-111.0, -11.9, 9.0, (-9.0, 11.1), (-11.2, 8.9), (-9.6, 28.5), (-30.2, 8.9))           # x -120..-99.1
    lane = stretch(-89.65, -18.85, 9.45, (-8.75, 8.75), (-8.75, 8.75), (-30.95, 7.15), (-8.85, 30.25))   # x -99.1..-70.8
    return road, lane


def check_pits_roof(c: Caster) -> None:
    """The measured pits roof against the set's faces: its underside at y 1.2 (+-0.3) over the road and the lane along its length,
    no roof over them just beyond its ends, and mid-roof the walls either side of each stretch's middle where measured (ROOF_WALLS:
    horizontal rays 3 units above the road meet them within 0.5 unit). PatchError naming the miss otherwise."""
    (z0, z1), (y0, y1), roof = ROOF_Z, ROOF_ROAD, ROOF_Y
    for st in pits_roof():
        xc = st.boxes[0].o[0]
        for f in (0.05, 0.5, 0.95):
            z = z0 + f * (z1 - z0)
            road = y0 + f * (y1 - y0)
            ys = c.heights(xc, z)
            under = ys[(ys > road + ROOF[0]) & (ys < road + ROOF[1])]
            if not len(under) or abs(under.min() - roof) > 0.3:
                raise PatchError(f"the pits roof is not drawn where measured: over x {xc} z {z:.1f} {sorted(under)[:3]}, expected {roof}")
        for z, road in ((z0 - 2.0, y0), (z1 + 2.0, y1)):
            ys = c.heights(xc, z)
            low = ys[(ys > road + ROOF[0]) & (ys < roof + 0.5)]
            if len(low):
                raise PatchError(f"the pits roof reaches past its measured end at z {z:.1f} (x {xc}): {sorted(low)[:3]}")
        zm, ym = (z0 + z1) / 2, (y0 + y1) / 2 + 3.0
        for x_wall in ROOF_WALLS[xc]:                  # mid-roof, the walls either side of the stretch's middle
            side = 1.0 if x_wall > xc else -1.0
            hit = c.ray(c.near(xc, zm, 40), np.array([xc, ym, zm]), np.array([side, 0.0, 0.0]))
            want = abs(x_wall - xc)
            if not len(hit) or abs(hit.min() - want) > 0.5:
                raise PatchError(f"the pits roof's wall at x {x_wall} (from x {xc} at z {zm:.1f}): {sorted(hit)[:2]}, expected {want:.2f}")


# ==================================================================================================================== the tables
def flagged_points(rs: RomSet, entry: int) -> list[int]:
    """The road points credited to the entry's tunnel-flagged quads (bit 7 of the segment flag), normal direction."""
    from vrtools.arcade.course import course_entry_at, segments
    from vrtools.arcade.directory import decode_directory
    e = decode_directory(rs)[entry]
    return sorted({s.road_point for s in segments(rs, course_entry_at(rs, e.bank, window_base=e.header_base)) if s.flag & 0x80})


def flagged_stretches(points: list[int], gap: int = 2) -> list[tuple[int, int]]:
    """Runs of flagged road points (closer than `gap` joined) as (first, last)."""
    runs: list[list[int]] = []
    for p in sorted(points):
        if runs and p <= runs[-1][1] + gap:
            runs[-1][1] = p
        else:
            runs.append([p, p])
    return [(a, b) for a, b in runs]


def tables(rs: RomSet, entry: int) -> tuple[Stretch, ...]:
    """The cover table of a menu entry: () for a course with no flagged stretch, else its stretches (Metropolis: the pits roof's road
    and lane, then the long tunnel; Alpine and Bay Bridge one each), marched from the set's faces. PatchError when the set's flags do
    not name the stretches the table knows or the pits roof is not drawn where measured."""
    from vrtools.arcade.directory import decode_directory
    name = decode_directory(rs)[entry].name
    flagged = flagged_points(rs, entry)
    marched = [m for m in MARCHED if NAME_OF_ENTRY[m[0]] == name]
    if name not in KNOWN_NAMES:
        marched = [(None, f, l, 4.0, True) for f, l in flagged_stretches(flagged)]
    metropolis = name == "METROPOLIS"
    known = [(f, l) for _, f, l, _, _ in marched] + ([PITS_ROOF] if metropolis else [])
    if not known:
        if flagged:
            raise PatchError(f"menu entry {entry}: tunnel-flagged road points {flagged[:4]}.. but no cover table for them")
        return ()
    stray = [p for p in flagged if not any(f - 1 <= p <= l + 1 for f, l in known)]
    missing = [(f, l) for f, l in known if not any(f - 1 <= p <= l + 1 for p in flagged)]
    if stray or missing:
        raise PatchError(f"menu entry {entry}: the tunnel flags (points {stray[:4]} outside) do not match the cover's stretches "
                         f"{known} (none flagged in {missing})")
    tris, line = course_faces(rs, entry)
    c = Caster(tris)
    out = []
    if metropolis:
        check_pits_roof(c)
        out += list(pits_roof())
    for _, first, last, ang, split in marched:
        out.append(stretch_table(c, line, first, last, ang=ang, ext_split=split))
    return tuple(out)


STRSZ, BOXSZ, MOUTHSZ = 20, 40, 64      # the table's records (bytes)
# the records' fields (byte offsets; `table_bytes`): a stretch, a box, a mouth (fix round 1, M4: read by name in weather/cover.py)
STR_CX, STR_CZ, STR_RR, STR_BOX, STR_NBOX = 0, 4, 8, 12, 16
BOX_OX, BOX_OZ, BOX_AX, BOX_AZ, BOX_L, BOX_SMIN, BOX_SMAX, BOX_MOUTH, BOX_VIS = 0, 4, 8, 12, 16, 20, 24, 28, 36   # mouth1: BOX_MOUTH + 4
(MOUTH_MX, MOUTH_MY, MOUTH_MZ, MOUTH_OX, MOUTH_OZ, MOUTH_SMIN, MOUTH_SMAX, MOUTH_H, MOUTH_PMIN, MOUTH_PMAX, MOUTH_PH, MOUTH_D,
 MOUTH_KX0, MOUTH_KX1, MOUTH_KY0, MOUTH_KY1) = range(0, 64, 4)
NEAR_PAD = 45.0                         # a stretch's circle: its chords' reach + the widest lateral extent + the near radius


def table_bytes(stretches, near: float) -> bytes:
    """The table as the cover's code reads it (offsets from the table's start, little-endian):
      nstr; per stretch (STRSZ) cx cz rr (the circle within which the camera may be near a box: radius squared) first-box nbox;
      per box (BOXSZ) ox oz ax az L smin smax mouth0 mouth1 vis;
      per mouth (MOUTHSZ) mx my mz ox oz smin smax H pmin pmax PH D kx0 kx1 ky0 ky1."""
    nstr = len(stretches)
    boxes = [(si, b) for si, st in enumerate(stretches) for b in st.boxes]
    box_at = 4 + STRSZ * nstr
    mouth_at = box_at + BOXSZ * len(boxes)
    mptr = {(si, j): mouth_at + MOUTHSZ * (2 * si + j) for si in range(nstr) for j in range(2)}
    out = struct.pack("<I", nstr)
    k = 0
    for st in stretches:
        pts = [b.o for b in st.boxes] + [(b.o[0] + b.a[0] * b.L, b.o[1] + b.a[1] * b.L) for b in st.boxes]
        cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
        cz = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2
        r = max(math.hypot(p[0] - cx, p[1] - cz) for p in pts) + NEAR_PAD + near
        out += struct.pack("<3f2I", cx, cz, r * r, box_at + BOXSZ * k, len(st.boxes))
        k += len(st.boxes)
    for si, b in boxes:
        out += struct.pack("<7f3I", b.o[0], b.o[1], b.a[0], b.a[1], b.L, b.s[0], b.s[1], mptr[(si, 0)], mptr[(si, 1)], b.vis)
    for st in stretches:
        for mo in st.mouths:
            p = mo.p if mo.p is not None else (mo.s[0] - PW, mo.s[1] + PW)
            out += struct.pack("<16f", *mo.c, *mo.o, *mo.s, mo.H, *p, min(PHK * mo.H, PHMAX), DEPTH, *mo.kbox)
    return out
