"""Saturn course geometry -> arcade world-space quads, cell binning and colour assignment (Phase 4)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from vrtools.arcade.colours import Palette, nearest
from vrtools.arcade.polyrom import Quad, decode_object, quads as poly_quads
from vrtools.arcade.romset import RomSet
from vrtools.arcade.course import tile_table
from vrtools.saturn.course import Mesh, Placement, SaturnCourse

SCALE = 11.7                 # arcade units per Saturn unit (Phase 3 position fit)
YSIGN = 1.0                  # Saturn and arcade are both Y-up (Phase 4 discovery)
TURN = 4294967296.0
Point = tuple[float, float, float]


class ConvertError(Exception):
    pass


@dataclass(frozen=True)
class WorldQuad:
    p: tuple[Point, Point, Point, Point]
    rgb: tuple[int, int, int]
    one_sided: bool = False      # Phase 26 stage 2: drawn only from the side the Saturn's winding shows it to (a gate's lettering
                                 # and its mirrored copy: gates.lettered_quads); every other face is drawn from both sides


_PLACEMENT = [1.0, 0.0, 0.0, 0.0]        # cos, sin, tx, tz of the course placement in arcade space (identity by default)


def _place(x: float, z: float) -> tuple[float, float]:
    c, s, tx, tz = _PLACEMENT
    return (x * c + z * s + tx, -x * s + z * c + tz)


def set_placement(angle: float = 0.0, tx: float = 0.0, tz: float = 0.0) -> None:
    """Rigid transform applied to every converted point after scaling: rotate by `angle` about the origin (the
    heading angle atan2(x, z) increases by `angle`), then shift by (tx, tz). Used to put a converted course's
    start at the arcade's grid pose (convert.place)."""
    _PLACEMENT[:] = [math.cos(angle), math.sin(angle), tx, tz]


def clear_placement() -> None:
    _PLACEMENT[:] = [1.0, 0.0, 0.0, 0.0]


class placed:
    """Context manager: `with placed(angle, tx, tz): ...` converts under that placement, then restores identity."""

    def __init__(self, angle: float, tx: float, tz: float) -> None:
        self.args = (angle, tx, tz)

    def __enter__(self):
        set_placement(*self.args)
        return self

    def __exit__(self, *exc):
        clear_placement()
        return False


def normal_to_arcade(nx: float, ny: float, nz: float) -> Point:
    """A Saturn slice normal in arcade axes: the placement rotation (no shift, no scale), unit length. Unlike the
    points, the normal's horizontal components are NOT negated: measured against the ground mesh (built from the
    points) on Alpine and the Oval, the negated form gave the opposite lateral slope at every banked centre (0 of
    68 and 0 of 113 agreeing), this form the same. Phase 15: the road's camber relative to the direction of travel
    comes from the slice normal, which is invariant to the lap's direction through the slices."""
    c, s, _tx, _tz = _PLACEMENT
    ax, az = nx * c + nz * s, -nx * s + nz * c
    ay = YSIGN * ny
    m = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
    return (ax / m, ay / m, az / m)


def to_arcade(x: float, y: float, z: float) -> Point:
    """Saturn road-slice frame -> arcade world (the reference frame: Phase 5 collision matched the arcade lanes),
    then the course placement."""
    px, pz = _place(-SCALE * x, -SCALE * z)
    return (px, SCALE * YSIGN * y, pz)


def tile_to_arcade(x: float, y: float, z: float) -> Point:
    """Saturn tile/prop placement frame -> arcade world, then the course placement. Placed geometry comes out
    half a turn from the slices (Phase 6 recon: Big Forest tiles overlap the arcade tiles at Jaccard 0.82 this
    way, 0.58 with to_arcade)."""
    px, pz = _place(SCALE * x, SCALE * z)
    return (px, SCALE * YSIGN * y, pz)


def tile_occupancy(quads, cell: float = 64.0) -> set[tuple[int, int]]:
    """The set of (x, z) cells of `cell` units that quad centroids fall in; quads have `.p` of 3-D points."""
    out = set()
    for q in quads:
        cx = sum(p[0] for p in q.p) / len(q.p)
        cz = sum(p[2] for p in q.p) / len(q.p)
        out.add((int(cx // cell), int(cz // cell)))
    return out


def rgb555(word: int) -> tuple[int, int, int]:
    """Saturn RGB555: r in the low bits, then g, then b (same order as the arcade palette)."""
    return ((word & 0x1F) << 3, ((word >> 5) & 0x1F) << 3, ((word >> 10) & 0x1F) << 3)


def face_quads(m: Mesh, p: Placement) -> list[WorldQuad]:
    """A placed mesh's faces as arcade world quads (triangles keep a repeated point)."""
    a = p.yaw * 2 * math.pi / TURN
    c, s = math.cos(a), math.sin(a)
    world = []
    for vx, vy, vz in m.vertices:
        rx, rz = vx * c + vz * s, -vx * s + vz * c          # rotation about Y
        world.append(tile_to_arcade(p.x + rx, p.y + vy, p.z + rz))
    out = []
    for f in m.faces:
        pts = tuple(world[i] for i in f.vertex_ids)
        out.append(WorldQuad(pts, rgb555(f.colour)))
    return out


ROAD_GROUP = 0                # the ground layer that carries the road
ROAD_GREYS = {40: 40, 48: 48, 56: 48, 64: 56, 72: 64, 80: 72, 88: 80, 96: 80, 104: 88, 112: 96, 120: 104, 128: 104}


def road_greys(quads: list[WorldQuad]) -> list[WorldQuad]:
    """Phase 24 (Pascal: align the converted road's colour with the arcade's): the ground layer's neutral greys at the
    arcade's levels. The Saturn shows its road greys unlit (Big Forest 64-104, mean 87); the arcade's own road sits lower
    in the palette (Big Forest 56-88, mean 77, at the same spots; the two games' tile-to-tile patterns are unrelated,
    correlation 0) and is lit on top, so converted roads stood at 107-140 on screen against the originals' 74-107.
    ROAD_GREYS takes Big Forest's Saturn greys onto the arcade's range and mean (77.5), the shades' order kept; a colour
    that is not a neutral grey of the table stays."""
    out = []
    for q in quads:
        r, g, b = q.rgb
        out.append(WorldQuad(q.p, (ROAD_GREYS[r],) * 3) if r == g == b and r in ROAD_GREYS else q)
    return out


def course_quads(sat: SaturnCourse, groups: tuple[int, ...] = (0, 1, 2, 3, 4)) -> list[WorldQuad]:
    """Groups 0-3 share one tile lattice with different meshes (layers, ~0.8-2k faces each); 4 = props."""
    out: list[WorldQuad] = []
    for g in groups:
        meshes = sat.meshes.get(g, [])
        for p in sat.placements.get(g, []):
            if p.mesh < 0 or p.mesh >= len(meshes):
                continue
            out.extend(face_quads(meshes[p.mesh], p))
    return out


@dataclass(frozen=True)
class CellGrid:
    x0: float
    z0: float
    cw: float
    ch: float

    def cell_of(self, x: float, z: float) -> int | None:
        xc = int(math.floor((x - self.x0) / self.cw))
        zc = int(math.floor((z - self.z0) / self.ch))
        if not (0 <= xc < 16 and 0 <= zc < 16):
            return None
        return zc * 16 + xc


TILE_GRID = CellGrid(-1024.0, -1024.0, 128.0, 128.0)   # the game's rule: tile cell = collision cell >> 3 (Phase 6: holds for
                                                       # all 223 arcade tile objects and the logged visible-cell lists)
TILE_GROUPS = (0, 1, 2, 3, 4)                          # the Saturn's layers (Phase 18 recon §1): 0 road and ground, 1 terrain,
                                                       # 2 road paint, 3 structures; 4 the props
TERRAIN_GROUP = 1
TERRAIN_KEEP_DISTANCE = 60.0   # arcade units: terrain this close to the centreline is never thinned (the roadside stays whole)


THIN_KEEP_DISTANCE = 40.0      # arcade units: a quad this close to a keep point (the lap centreline) is never thinned


def thin_quads(quads: list[WorldQuad], thin: float, keep_near: list[tuple[float, float]] | None,
               keep_distance: float = THIN_KEEP_DISTANCE) -> tuple[list[WorldQuad], int]:
    """Drop quads whose XZ area is below `thin` and whose centre is farther than `keep_distance` from every point of
    `keep_near`; returns (kept quads, dropped count). thin <= 0 keeps everything."""
    if thin <= 0 or not quads:
        return quads, 0
    pts = np.array([[p[0], p[2]] for q in quads for p in q.p], dtype=float).reshape(len(quads), -1, 2)
    x, z = pts[:, :, 0], pts[:, :, 1]
    area = 0.5 * np.abs(np.sum(x * np.roll(z, -1, axis=1) - np.roll(x, -1, axis=1) * z, axis=1))
    small = area < thin
    if keep_near:
        keep = np.array(keep_near, dtype=float)
        centres = pts.mean(axis=1)
        near = np.zeros(len(quads), dtype=bool)
        for i in range(0, len(quads), 2048):                                   # chunked: quads x keep points
            d2 = ((centres[i:i + 2048, None, :] - keep[None, :, :]) ** 2).sum(axis=2)
            near[i:i + 2048] = d2.min(axis=1) < keep_distance ** 2
        small &= ~near
    kept = [q for q, drop in zip(quads, small) if not drop]
    return kept, int(small.sum())


def scenery_quads(by_group: dict[int, list[WorldQuad]], keep_near: list[tuple[float, float]] | None,
                  terrain_thin: float = 0.0) -> tuple[list[WorldQuad], dict]:
    """Every group's quads, the terrain (group 1) thinned with `thin_quads` (`terrain_thin`, TERRAIN_KEEP_DISTANCE).
    Report key `terrain_thinned`. (A filter for terrain just under the road was removed in the Phase 18 review: against
    the drawn road no course has any, and measured against the collision profile it cut holes in Pacific's verges.)"""
    out: list[WorldQuad] = []
    thinned = 0
    for g in sorted(by_group):
        qs = by_group[g]
        if g == TERRAIN_GROUP:
            qs, thinned = thin_quads(qs, terrain_thin, keep_near, TERRAIN_KEEP_DISTANCE)
        out.extend(qs)
    return out, {"terrain_thinned": thinned}


OUTSIDE_MAP_MAX = 50           # Phase 22l: a lap start at the Saturn's flag may leave this many scenery quads past the map's edge
                               # (the Surfers Oval's and Road's 11 at x 1024); they are left out, not an error


def convert_tiles(sat: SaturnCourse, rs: RomSet, course_index: int, groups: tuple[int, ...] = TILE_GROUPS,
                  max_records: int = 5500, thin: float = 0.0,
                  keep_near: list[tuple[float, float]] | None = None, terrain_thin: float = 0.0,
                  outside_limit: int = 0, lettering: bool = True) -> tuple[dict[int, tuple[bytes, object, int]], dict[int, int], dict]:
    """The Phase 4 pipeline for a course's scenery: Saturn tiles (groups) -> world quads -> 128-unit cells ->
    coloured, encoded polygon-ROM objects, one per cell, with the colour-table entries they need.

    Returns (cell_objects {cell: (bytes, ObjectLayout, tex_start)}, colour_words {tex: word}, report). A quad
    whose centre leaves the collision map (|x| or |z| >= 1024) is a ConvertError: the course needs a translation —
    unless at most `outside_limit` do (Phase 22l: a flag start's trade-off), which are left out (report["outside"]).
    A cell over `max_records` keeps its first split (report["capped_cells"]). With `thin` > 0, quads smaller than
    `thin` (XZ area) and farther than THIN_KEEP_DISTANCE from every `keep_near` point are left out
    (report["thinned"]): the render-rate lever for the busiest courses. The terrain goes through `scenery_quads`
    first (`terrain_thin`; report["terrain_thinned"]). The props (group 4) come from `gates.lettered_quads`: a drawn gate's
    lettering one-sided with a mirrored one-sided copy facing the other way (Phase 26 stage 2; `lettering` False: every
    prop face two-sided, as before; report["lettering_copies"]: the copies added); the collision never sees them (it reads
    the Saturn course itself)."""
    from vrtools.arcade.colours import colour_table, free_runs, palette_from_rom
    from vrtools.arcade.polyrom import encode_object, split_quads
    from vrtools.convert.gates import GATE_GROUP, lettered_quads
    by_group = {g: course_quads(sat, groups=(g,)) for g in groups}
    copies = 0
    if lettering and GATE_GROUP in by_group:
        props = len(by_group[GATE_GROUP])
        by_group[GATE_GROUP] = lettered_quads(sat)          # Phase 26 stage 2: the gates' lettering reads from both sides (scenery only)
        copies = len(by_group[GATE_GROUP]) - props
    if ROAD_GROUP in by_group:
        by_group[ROAD_GROUP] = road_greys(by_group[ROAD_GROUP])          # Phase 24: the road at the arcade's grey levels
    layered, layer_report = scenery_quads(by_group, keep_near, terrain_thin)
    quads, thinned = thin_quads(layered, thin, keep_near)
    cells, outside = bin_quads(quads, TILE_GRID)
    if outside and len(outside) > outside_limit:
        q = outside[0]
        raise ConvertError(f"{len(outside)} scenery quads leave the collision map (first centre "
                           f"({sum(p[0] for p in q.p) / 4:.0f}, {sum(p[2] for p in q.p) / 4:.0f})): the course needs a translation")
    pal = palette_from_rom(rs, course_index)
    run_start, run_len = free_runs(colour_table(rs))[0]
    tex = run_start
    objects: dict[int, tuple[bytes, object, int]] = {}
    words: dict[int, int] = {}
    capped = 0
    for cell, cq in sorted(cells.items()):
        coloured, w = assign_colours(cq, pal, tex_start=tex)
        if tex + len(w) > run_start + run_len:
            raise ConvertError("colour table free run exhausted")
        words.update(w)
        parts = split_quads(coloured, max_records)
        if len(parts) > 1:
            capped += 1
        blob, layout = encode_object(parts[0], tex_start=tex, no_cull=True)
        objects[cell] = (blob, layout, tex)
        tex += len(w)
    report = {"outside": len(outside), "cells": len(objects), "quads": len(quads), "colour_entries": len(words),
              "polygon_bytes": sum(len(o[0]) for o in objects.values()), "capped_cells": capped, "thinned": thinned,
              "lettering_copies": copies, **layer_report}
    return objects, words, report


def cell_grid_from_arcade(rs: RomSet, course_index: int) -> CellGrid:
    """Fit the course's cell grid from the centroids of its existing tile objects."""
    xs: dict[int, list[float]] = {}
    zs: dict[int, list[float]] = {}
    for t in tile_table(rs, course_index):
        if not t.size:
            continue
        pts = np.array([pt for qd in poly_quads(decode_object(rs.polygons, t.poly_adr, t.size)) for pt in qd.p])
        cx, cz = float(pts[:, 0].mean()), float(pts[:, 2].mean())
        xs.setdefault(t.x_cell, []).append(cx)
        zs.setdefault(t.z_cell, []).append(cz)
    def fit(d: dict[int, list[float]]) -> tuple[float, float]:
        ks = np.array(sorted(d)); ms = np.array([np.median(d[k]) for k in ks])
        slope, intercept = np.polyfit(ks, ms, 1)
        return float(slope), float(intercept - slope / 2)          # origin at the edge of cell 0
    cw, x0 = fit(xs)
    ch, z0 = fit(zs)
    return CellGrid(x0, z0, cw, ch)


def bin_quads(quads: list[WorldQuad], grid: CellGrid) -> tuple[dict[int, list[WorldQuad]], list[WorldQuad]]:
    cells: dict[int, list[WorldQuad]] = {}
    outside: list[WorldQuad] = []
    for qd in quads:
        cx = sum(pt[0] for pt in qd.p) / 4.0
        cz = sum(pt[2] for pt in qd.p) / 4.0
        c = grid.cell_of(cx, cz)
        if c is None:
            outside.append(qd)
        else:
            cells.setdefault(c, []).append(qd)
    return cells, outside


def _normal(p: tuple[Point, ...]) -> Point:
    """The face's unit lighting normal on the side its winding gives, summed over every edge (Newell's method), so a
    triangle stored with a repeated corner faces the same way wherever the repeat sits. Phase 24: taking the first
    three corners alone fell back to straight up for a repeat among them, the opposite of every other ground face,
    and the arcade lit those triangles as if they faced away (black wedges on the road)."""
    v = np.array(p, dtype=float)
    v = v - v[0]                             # edges relative to a corner: no precision lost far from the origin
    n = np.cross(v, np.roll(v, -1, axis=0)).sum(axis=0)
    L = float(np.linalg.norm(n))
    if L < 1e-9:
        return (0.0, -1.0, 0.0)              # no area: the ground's own side (measured: road normals have y < 0)
    return tuple(float(v) for v in n / L)


def assign_colours(quads: list[WorldQuad], pal: Palette, tex_start: int) -> tuple[list[Quad], dict[int, int]]:
    """Sort quads by nearest palette index; one colour-table entry per colour change from tex_start.

    Returns polyrom Quads (with tex_adr set) and the table words {tex_adr: word} to write. A one-sided WorldQuad (Phase 26
    stage 2) becomes a one-sided Quad with its corners reversed under the lighting normal it had: the arcade draws a culled
    record from the side its corners' right-hand normal faces (the originals' culled ground faces up that way: 9 177 of
    9 793 horizontal records on Big Forest), the opposite of the Saturn's winding (the converted road's points down)."""
    keyed = sorted(((nearest(pal, qd.rgb), i, qd) for i, qd in enumerate(quads)), key=lambda k: (k[0], k[1]))
    out: list[Quad] = []
    words: dict[int, int] = {}
    tex = tex_start - 1
    last = None
    for idx, _, qd in keyed:
        if idx != last:
            tex += 1
            words[tex] = idx & 0x3FF
            last = idx
        if qd.one_sided:
            a, b, c, d = qd.p
            out.append(Quad((a, d, c, b), _normal(qd.p), 0x201, tex, one_sided=True))
        else:
            out.append(Quad(qd.p, _normal(qd.p), 0x201, tex))
    return out, words
