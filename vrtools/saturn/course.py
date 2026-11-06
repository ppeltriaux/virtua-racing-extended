"""Decoders and encoders for the Saturn TRCK* course files (docs/formats/saturn-trck.md).

All multi-byte values are big-endian; coordinates are 16.16 fixed point.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from vrtools.saturn.trck import TrckFile

FIX = 65536.0
SEGMENT_SIZE = 76
SEGMENT_SECTION = 4
FX_LIMIT = 32768.0


class SaturnError(Exception):
    pass


def fx(v: int) -> float:
    return v / FIX


def to_fx(v: float) -> int:
    if not math.isfinite(v) or abs(v) >= FX_LIMIT:
        raise SaturnError(f"{v} does not fit 16.16 fixed point")
    return int(round(v * FIX))


def _section(t: TrckFile, index: int) -> bytes:
    for s in t.sections():
        if s.index == index:
            return bytes(s.data)
    raise SaturnError(f"section {index} is missing")


@dataclass(frozen=True)
class Plane:
    nx: float
    nz: float
    d: float


@dataclass(frozen=True)
class Segment:
    index: int
    planes: tuple[Plane, Plane, Plane, Plane]
    normal: tuple[float, float, float]
    words: tuple[int, int, int, int]          # raw words 15-18 (meaning TBD)

    @property
    def active_planes(self) -> tuple[Plane, ...]:
        """A slice is a convex polygon with 3 or 4 planes; an all-zero plane means 'absent'."""
        return tuple(p for p in self.planes if (p.nx, p.nz, p.d) != (0.0, 0.0, 0.0))

    def corners(self) -> tuple[tuple[float, float], ...] | None:
        """Polygon corners: intersections of consecutive active planes (lines n.p + d = 0 in the XZ plane).

        Returns None unless the planes bound a proper convex polygon: consecutive normals must not be
        near-parallel (|det| >= 1e-3 for unit normals), every corner must lie inside every active plane
        (n.p + d >= -1e-3) and the corners must turn consistently with non-zero area."""
        planes = self.active_planes
        if len(planes) < 3:
            return None
        out = []
        for k in range(len(planes)):
            a, b = planes[k], planes[(k + 1) % len(planes)]
            det = a.nx * b.nz - a.nz * b.nx
            if abs(det) < 1e-3:
                return None
            x = (-a.d * b.nz + b.d * a.nz) / det
            z = (-a.nx * b.d + b.nx * a.d) / det
            out.append((x, z))
        for x, z in out:
            if any(p.nx * x + p.nz * z + p.d < -1e-3 for p in planes):
                return None
        signs = set()
        for k in range(len(out)):
            (x0, z0), (x1, z1), (x2, z2) = out[k - 1], out[k], out[(k + 1) % len(out)]
            cross = (x1 - x0) * (z2 - z1) - (z1 - z0) * (x2 - x1)
            if abs(cross) < 1e-9:
                return None
            signs.add(cross > 0)
        if len(signs) != 1:
            return None
        return tuple(out)

    def _sides(self):
        c = self.corners()
        if c is None or len(c) != 4:
            return None
        v = [(c[(k + 1) % 4][0] - c[k][0], c[(k + 1) % 4][1] - c[k][1]) for k in range(4)]
        L = [math.hypot(*w) for w in v]
        a, b = (L[0] + L[2]) / 2.0, (L[1] + L[3]) / 2.0     # sides 0/2 lie on planes 1/3; sides 1/3 on planes 2/0
        return c, v, a, b

    @property
    def centre(self) -> tuple[float, float] | None:
        c = self.corners()
        if c is None:
            return None
        return (sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c))

    @property
    def angles(self) -> tuple[float, float, float]:
        """Words 15-17 as degrees: rotations in 1/2^32 of a turn (about Y?, Z = banking, X = slope)."""
        return tuple(w * 360.0 / 4294967296.0 for w in self.words[:3])

    @property
    def width(self) -> float | None:
        """Extent across the road: the larger of the two averaged side pairs (a slice is wider than long)."""
        r = self._sides()
        return None if r is None else max(r[2], r[3])

    @property
    def length(self) -> float | None:
        r = self._sides()
        return None if r is None else min(r[2], r[3])

    @property
    def heading(self) -> float | None:
        """Direction of travel: along the shorter side pair, oriented with plane 1's normal (radians)."""
        r = self._sides()
        if r is None:
            return None
        c, v, a, b = r
        if a <= b:                                   # sides 0/2 are the short (along-road) ones
            dx, dz = (v[0][0] - v[2][0]) / 2.0, (v[0][1] - v[2][1]) / 2.0
        else:
            dx, dz = (v[1][0] - v[3][0]) / 2.0, (v[1][1] - v[3][1]) / 2.0
        n = self.planes[1]
        if dx * n.nx + dz * n.nz < 0:
            dx, dz = -dx, -dz
        return math.atan2(dz, dx)


def _decode_segment(index: int, rec: bytes) -> Segment:
    w = struct.unpack(">19i", rec)
    planes = tuple(Plane(fx(w[3 * k]), fx(w[3 * k + 1]), fx(w[3 * k + 2])) for k in range(4))
    normal = (fx(w[12]), fx(w[13]), fx(w[14]))
    return Segment(index, planes, normal, tuple(w[15:19]))


def segments(t: TrckFile) -> list[Segment]:
    sec = _section(t, SEGMENT_SECTION)
    if len(sec) % SEGMENT_SIZE:
        raise SaturnError(f"section {SEGMENT_SECTION}: length {len(sec)} is not a multiple of {SEGMENT_SIZE}")
    return [_decode_segment(i, sec[i * SEGMENT_SIZE:(i + 1) * SEGMENT_SIZE]) for i in range(len(sec) // SEGMENT_SIZE)]


def encode_segment(s: Segment) -> bytes:
    out = b""
    for p in s.planes:
        out += struct.pack(">3i", to_fx(p.nx), to_fx(p.nz), to_fx(p.d))
    out += struct.pack(">3i", *(to_fx(v) for v in s.normal))
    for v in s.words:
        if not (-(1 << 31) <= v < 1 << 31):
            raise SaturnError(f"segment {s.index}: word {v} does not fit i32")
    return out + struct.pack(">4i", *s.words)


# --- section 9: spatial grid -------------------------------------------------

GRID_SECTION = 9
GRID_CELLS = 256


@dataclass(frozen=True)
class Grid:
    cells: list[list[int]]          # 256 lists of segment indices (empty for unused cells)
    order: list[int]                # cells with a list, in file order (real files: all 256, empty cells have a 2-byte list)
    tail: bytes = b""               # bytes after the last list (real files end with one more empty list)


def grid(t: TrckFile, segment_count: int) -> Grid:
    from vrtools.saturn.trck import LOAD_BASE
    sec = next(s for s in t.sections() if s.index == GRID_SECTION)
    data = bytes(sec.data)
    if len(data) < 4 * GRID_CELLS:
        raise SaturnError(f"section {GRID_SECTION}: too short for 256 pointers ({len(data)} bytes)")
    section_base = LOAD_BASE + sec.offset
    cells: list[list[int]] = []
    order: list[tuple[int, int]] = []
    end = 4 * GRID_CELLS
    for c in range(GRID_CELLS):
        ptr = struct.unpack_from(">I", data, 4 * c)[0]
        if ptr == 0:
            cells.append([])
            continue
        off = ptr - section_base
        if not (4 * GRID_CELLS <= off < len(data) - 1):
            raise SaturnError(f"cell {c}: list pointer {ptr:#x} is outside section {GRID_SECTION}")
        n = struct.unpack_from(">H", data, off)[0]
        if off + 2 + 2 * n > len(data):
            raise SaturnError(f"cell {c}: list of {n} entries runs past section {GRID_SECTION}")
        idx = list(struct.unpack_from(f">{n}H", data, off + 2))
        bad = [i for i in idx if i >= segment_count]
        if bad:
            raise SaturnError(f"cell {c}: segment index {bad[0]} >= segment count {segment_count}")
        cells.append(idx)
        order.append((off, c))
        end = max(end, off + 2 + 2 * n)
    return Grid(cells, [c for _, c in sorted(order)], bytes(data[end:]))


def encode_grid(g: Grid, section_base: int) -> bytes:
    if len(g.cells) != GRID_CELLS:
        raise SaturnError(f"grid needs {GRID_CELLS} cells")
    lists = b""
    offsets: dict[int, int] = {}
    for c in g.order:
        offsets[c] = 4 * GRID_CELLS + len(lists)
        for i in g.cells[c]:
            if not (0 <= i < 0x10000):
                raise SaturnError(f"cell {c}: segment index {i} does not fit u16")
        lists += struct.pack(">H", len(g.cells[c])) + b"".join(struct.pack(">H", i) for i in g.cells[c])
    ptrs = b"".join(struct.pack(">I", section_base + offsets[c] if c in offsets else 0) for c in range(GRID_CELLS))
    return ptrs + lists + g.tail


def grid_bounds(segs: list[Segment]) -> tuple[float, float, float, float]:
    xs, zs = [], []
    for s in segs:
        c = s.corners()
        if c:
            xs += [p[0] for p in c]
            zs += [p[1] for p in c]
    return (min(xs), min(zs), max(xs), max(zs))


# --- sections 5-8: grid parameters ------------------------------------------

GRID_PARAM_SECTIONS = (5, 6, 7, 8)


@dataclass(frozen=True)
class GridParams:
    xmax: float          # section 5 holds -xmax
    zmax: float          # section 6 holds -zmax
    inv_w: float         # section 7: 16 / (xmax - xmin)
    inv_h: float         # section 8: 16 / (zmax - zmin)


def grid_params(t: TrckFile) -> GridParams:
    vals = []
    for i in GRID_PARAM_SECTIONS:
        sec = _section(t, i)
        if len(sec) < 4:
            raise SaturnError(f"section {i}: expected a 16.16 word")
        vals.append(fx(struct.unpack(">i", sec[:4])[0]))
    return GridParams(-vals[0], -vals[1], vals[2], vals[3])


def encode_grid_params(gp: GridParams) -> dict[int, bytes]:
    return {5: struct.pack(">i", to_fx(-gp.xmax)), 6: struct.pack(">i", to_fx(-gp.zmax)),
            7: struct.pack(">i", to_fx(gp.inv_w)), 8: struct.pack(">i", to_fx(gp.inv_h))}


def cell_of(gp: GridParams, x: float, z: float) -> int:
    """Grid cell index zc*16 + xc, counted from the (xmax, zmax) corner (axes flipped)."""
    xc = int((gp.xmax - x) * gp.inv_w)
    zc = int((gp.zmax - z) * gp.inv_h)
    if not (0 <= xc < 16 and 0 <= zc < 16):
        raise SaturnError(f"({x}, {z}) is outside the 16x16 grid")
    return zc * 16 + xc


# --- objects / meshes (geometry blobs referenced by the group pointer lists) --

GROUP_POINTER_SECTIONS = {0: 2, 1: 18, 2: 21, 3: 24, 4: 37}
FACE_SIZE = 14


@dataclass(frozen=True)
class Face:
    colour: int                      # RGB555 (u16)
    attr_a: int                      # u16, small values 0..11 (meaning TBD)
    attr_b: int                      # u16, not a normal index (out of range in 4 % of faces); meaning TBD
    vertex_ids: tuple[int, int, int, int]   # a triangle repeats an id


@dataclass(frozen=True)
class Mesh:
    index: int
    vertices: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]
    faces: list[Face]
    raw_tail: bytes = b""            # bytes between the last face and the next object (padding), kept for lossless encode


def _object_pointers(t: TrckFile, group: int) -> list[int]:
    """Object file offsets in slot order; trailing nulls end the list, an interior null is an error."""
    from vrtools.saturn.trck import LOAD_BASE
    if group not in GROUP_POINTER_SECTIONS:
        raise SaturnError(f"no object group {group}")
    sec = _section(t, GROUP_POINTER_SECTIONS[group])
    raw = [struct.unpack_from(">I", sec, i)[0] for i in range(0, len(sec) // 4 * 4, 4)]
    while raw and raw[-1] == 0:
        raw.pop()
    ptrs = []
    for slot, p in enumerate(raw):
        if p == 0:
            raise SaturnError(f"object group {group}: slot {slot} is a null pointer inside the list")
        if not (LOAD_BASE <= p < LOAD_BASE + len(t.data)):
            raise SaturnError(f"object group {group}: slot {slot} pointer {p:#x} is outside the file")
        ptrs.append(p - LOAD_BASE)
    return ptrs


def _decode_mesh(data: bytes, index: int, off: int, end: int) -> Mesh:
    def need(n: int, what: str, pos: int) -> None:
        if pos + n > end:
            raise SaturnError(f"object {index}: {what} runs past the object at {off:#x}")
    need(4, "vertex count", off)
    nv = struct.unpack_from(">I", data, off)[0]
    need(12 * nv, f"{nv} vertices", off + 4)
    p = off + 4
    verts = [tuple(fx(v) for v in struct.unpack_from(">3i", data, p + 12 * i)) for i in range(nv)]
    p += 12 * nv
    need(4, "normal count", p)
    nn = struct.unpack_from(">I", data, p)[0]
    need(12 * nn, f"{nn} normals", p + 4)
    p += 4
    normals = [tuple(fx(v) for v in struct.unpack_from(">3i", data, p + 12 * i)) for i in range(nn)]
    p += 12 * nn
    need(4, "face count", p)
    nf = struct.unpack_from(">I", data, p)[0]
    need(FACE_SIZE * nf, f"{nf} faces", p + 4)
    p += 4
    faces = []
    for i in range(nf):
        col, a, b, v0, v1, v2, v3 = struct.unpack_from(">7H", data, p + FACE_SIZE * i)
        if max(v0, v1, v2, v3) >= nv:
            raise SaturnError(f"object {index}: face {i} references a vertex out of range")
        faces.append(Face(col, a, b, (v0, v1, v2, v3)))
    p += FACE_SIZE * nf
    return Mesh(index, verts, normals, faces, bytes(data[p:end]))


def _all_object_starts(t: TrckFile) -> list[int]:
    starts: set[int] = set()
    present = {s.index for s in t.sections()}
    for g, psec in GROUP_POINTER_SECTIONS.items():
        if psec in present:
            starts.update(_object_pointers(t, g))
    return sorted(starts)


def meshes(t: TrckFile, group: int) -> list[Mesh]:
    """Meshes of one object group in slot order. An object's extent ends at the next object start of
    any group or at the end of its section, whichever comes first."""
    ptrs = _object_pointers(t, group)
    starts = _all_object_starts(t)
    out = []
    for k, o in enumerate(ptrs):
        sec = next((s for s in t.sections() if s.offset <= o < s.offset + s.length), None)
        end = (sec.offset + sec.length) if sec else len(t.data)
        nxt = next((q for q in starts if q > o), None)
        if nxt is not None:
            end = min(end, nxt)
        out.append(_decode_mesh(t.data, k, o, end))
    return out


def encode_mesh(m: Mesh) -> bytes:
    out = struct.pack(">I", len(m.vertices)) + b"".join(struct.pack(">3i", *(to_fx(c) for c in v)) for v in m.vertices)
    out += struct.pack(">I", len(m.normals)) + b"".join(struct.pack(">3i", *(to_fx(c) for c in v)) for v in m.normals)
    out += struct.pack(">I", len(m.faces))
    for f in m.faces:
        vals = (f.colour, f.attr_a, f.attr_b, *f.vertex_ids)
        if any(not (0 <= v < 0x10000) for v in vals):
            raise SaturnError(f"object {m.index}: face field out of u16 range")
        out += struct.pack(">7H", *vals)
    return out + m.raw_tail


# --- placement tables (sections 0, 16, 19, 22, 35 with counts in 1, 17, 20, 23, 36) --

GROUP_PLACEMENT_SECTIONS = {0: (0, 1), 1: (16, 17), 2: (19, 20), 3: (22, 23), 4: (35, 36)}
PLACEMENT_SIZE = 56
TURN = 4294967296.0


@dataclass(frozen=True)
class Placement:
    index: int
    mesh: int                        # index into the group's mesh list, -1 = empty slot
    x: float
    y: float
    z: float
    yaw: int                         # rotation about Y in 1/2^32 turn (raw word 3)
    flags: int                       # raw word 0 (0x1000 for ground tiles, 0 for props)
    radius: float                    # bounding radius (8*sqrt(2) = 11.314 for 16-unit tiles)
    raw: tuple[int, ...]             # all 14 raw words (words 2, 4, 8, 9, 10, 12, 13 are not interpreted)

    @property
    def yaw_degrees(self) -> float:
        return self.yaw * 360.0 / TURN


def placements(t: TrckFile, group: int) -> list[Placement]:
    if group not in GROUP_PLACEMENT_SECTIONS:
        raise SaturnError(f"no object group {group}")
    tsec, csec = GROUP_PLACEMENT_SECTIONS[group]
    tbl = _section(t, tsec)
    count = struct.unpack_from(">H", _section(t, csec), 0)[0]
    if len(tbl) < PLACEMENT_SIZE * count:
        raise SaturnError(f"section {tsec}: {count} placements do not fit in {len(tbl)} bytes")
    n_meshes = len(_object_pointers(t, group))
    out = []
    for i in range(count):
        w = struct.unpack_from(">14i", tbl, PLACEMENT_SIZE * i)
        mesh = w[1] >> 16
        if not (-1 <= mesh < n_meshes):
            raise SaturnError(f"placement {i} of group {group}: mesh index {mesh} >= mesh count {n_meshes}")
        out.append(Placement(i, mesh, fx(w[5]), fx(w[6]), fx(w[7]), w[3], w[0], fx(w[11]), tuple(w)))
    return out


def encode_placement(p: Placement) -> bytes:
    if not (-1 <= p.mesh < 0x8000):
        raise SaturnError(f"placement {p.index}: mesh index {p.mesh} does not fit i16")
    w = list(p.raw) if len(p.raw) == 14 else [0] * 14
    w[0], w[1], w[3] = p.flags, p.mesh << 16, p.yaw          # signed i16 index in the high half
    w[5], w[6], w[7], w[11] = to_fx(p.x), to_fx(p.y), to_fx(p.z), to_fx(p.radius)
    for v in w:
        if not (-(1 << 31) <= v < 1 << 31):
            raise SaturnError(f"placement {p.index}: word {v} does not fit i32")
    return struct.pack(">14i", *w)


# --- whole-course bundle, encoder and lossless check -------------------------

@dataclass(frozen=True)
class SaturnCourse:
    trck: TrckFile
    segments: list[Segment]
    grid_params: GridParams | None
    grid: Grid | None
    placements: dict[int, list[Placement]]      # group -> entries
    meshes: dict[int, list[Mesh]]               # group -> objects


def _has(t: TrckFile, *indices: int) -> bool:
    present = {s.index for s in t.sections()}
    return all(i in present for i in indices)


def decode_course(t: TrckFile) -> SaturnCourse:
    segs = segments(t)
    gp = grid_params(t) if _has(t, *GRID_PARAM_SECTIONS) else None
    g = grid(t, len(segs)) if _has(t, GRID_SECTION) else None
    pl: dict[int, list[Placement]] = {}
    ms: dict[int, list[Mesh]] = {}
    for group, (tsec, csec) in GROUP_PLACEMENT_SECTIONS.items():
        psec = GROUP_POINTER_SECTIONS[group]
        if _has(t, psec):
            ms[group] = meshes(t, group)
        if _has(t, tsec, csec, psec):
            pl[group] = placements(t, group)
    return SaturnCourse(t, segs, gp, g, pl, ms)


def _section_offset(t: TrckFile, index: int) -> int:
    off = t.offset(index)
    if off is None:
        raise SaturnError(f"section {index} is missing")
    return off


def encode_course(c: SaturnCourse) -> dict[int, bytes]:
    """Every decoded table re-encoded, keyed by file offset."""
    from vrtools.saturn.trck import LOAD_BASE
    t = c.trck
    out: dict[int, bytes] = {}
    out[_section_offset(t, SEGMENT_SECTION)] = b"".join(encode_segment(s) for s in c.segments)
    if c.grid_params is not None:
        for idx, blob in encode_grid_params(c.grid_params).items():
            out[_section_offset(t, idx)] = blob
    if c.grid is not None:
        off = _section_offset(t, GRID_SECTION)
        out[off] = encode_grid(c.grid, LOAD_BASE + off)
    for group, entries in c.placements.items():
        out[_section_offset(t, GROUP_PLACEMENT_SECTIONS[group][0])] = b"".join(encode_placement(p) for p in entries)
    for group, objs in c.meshes.items():
        for ptr, m in zip(_object_pointers(t, group), objs):
            out[ptr] = encode_mesh(m)
    return out


def verify_lossless(data: bytes) -> list[str]:
    """Decode, re-encode and compare against the file; returns a list of mismatching offsets."""
    t = TrckFile.from_bytes(data)
    c = decode_course(t)
    problems = []
    for off, blob in encode_course(c).items():
        if data[off:off + len(blob)] != blob:
            problems.append(f"@{off:#x} ({len(blob)} bytes)")
    return problems
