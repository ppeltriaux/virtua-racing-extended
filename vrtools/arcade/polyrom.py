"""Decode Model 1 polygon ROM / RAM objects into quads.

Mirrors MAME's model1_state::push_object (src/mame/sega/model1_v.cpp,
BSD-3-Clause, Olivier Galibert): an object is two seed points followed by
records of ten 32-bit words [flags, nx, ny, nz, x0, y0, z0, x1, y1, z1].
See docs/formats/model1-polygon-rom.md.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

Point = tuple[float, float, float]


class PolyError(Exception):
    pass


@dataclass(frozen=True)
class Record:
    flags: int
    normal: Point
    p0: Point
    p1: Point

    @property
    def type(self) -> int:
        return self.flags & 3

    @property
    def link(self) -> int:
        return (self.flags >> 8) & 3

    @property
    def zmode(self) -> int:
        return (self.flags >> 10) & 3

    @property
    def tex_advance(self) -> bool:
        return bool(self.flags & 0x1000)

    @property
    def moire(self) -> bool:
        return bool(self.flags & 0x2000)

    @property
    def no_cull(self) -> bool:
        return bool(self.flags & 0x4000)

    @property
    def light_mode(self) -> int:
        return ((self.flags >> 17) & 15) | (0x80 if self.flags & 0x400000 else 0)


@dataclass(frozen=True)
class Object:
    seed0: Point
    seed1: Point
    records: list[Record]
    word_count: int


@dataclass(frozen=True)
class Quad:
    p: tuple[Point, Point, Point, Point]
    normal: Point
    flags: int
    tex_adr: int
    one_sided: bool = False      # encode_object: drawn from one side only (bit 14 clear on its record) whatever `no_cull` says:
                                 # from the side its first three corners' right-hand normal faces (Phase 26 stage 2, measured)


def decode_object(words: bytes, poly_adr: int, size: int = 0, max_records: int = 65536) -> Object:
    """`poly_adr` is a 32-bit word index into `words` (RAM bit 0x800000 already stripped)."""
    total_words = len(words) // 4

    def floats(idx: int, n: int) -> tuple[float, ...]:
        if idx + n > total_words:
            raise PolyError(f"object at word {poly_adr:#x} runs past end of buffer at word {idx:#x}")
        return struct.unpack_from(f"<{n}f", words, idx * 4)

    seed = floats(poly_adr, 6)
    idx = poly_adr + 6
    records: list[Record] = []
    limit = size if size else max_records + 1
    while len(records) < limit:
        if idx + 10 > total_words:
            raise PolyError(f"object at word {poly_adr:#x} runs past end of buffer at word {idx:#x}")
        flags = struct.unpack_from("<I", words, idx * 4)[0]
        if flags & 3 == 0:
            idx += 10                      # the end marker belongs to the object
            break
        if len(records) >= max_records:
            raise PolyError(f"object at word {poly_adr:#x} exceeds {max_records} records")
        f = struct.unpack_from("<9f", words, idx * 4 + 4)
        records.append(Record(flags, f[0:3], f[3:6], f[6:9]))
        idx += 10
    return Object(seed[0:3], seed[3:6], records, idx - poly_adr)


def quads(obj: Object, tex_adr: int = 0) -> list[Quad]:
    old_p0, old_p1 = obj.seed0, obj.seed1
    out: list[Quad] = []
    for r in obj.records:
        if r.tex_advance:
            tex_adr += 1
        p0, p1 = r.p0, (r.p0 if r.type == 2 else r.p1)
        if r.link:
            out.append(Quad((old_p1, old_p0, p0, p1), r.normal, r.flags, tex_adr))
        if r.link in (0, 2):
            old_p0, old_p1 = p0, p1
        elif r.link == 1:
            old_p1 = p0
        else:
            old_p0 = p1
    return out


# --- encoding (converter side) -----------------------------------------------

MAX_RECORDS = 5500           # the display-list builder passes this cap as the object size


class ConvertError(Exception):
    pass


@dataclass(frozen=True)
class ObjectLayout:
    record_count: int
    tex_first: int
    tex_last: int


def _pack_record(flags: int, normal: Point, p0: Point, p1: Point) -> bytes:
    return struct.pack("<I", flags) + struct.pack("<9f", *normal, *p0, *p1)


Z_MODE_MAX = 2 << 10           # flag bits 10-11 = 2: the polygon sorts at the FARTHEST of its four depths. The originals'
                               # ground polygons carry it (Big Forest: 0x1a01 / 0x1801 on 13 500 of 25 000 records) and the
                               # cars sort at their nearest (0x5601, z mode 1); with z mode 0 ("keep the old z") our ground
                               # sorted in front of the car and hid it for whole stretches (Phase 14 recon)


def _key(pt: Point) -> tuple[float, float, float]:
    return (round(pt[0], 3), round(pt[1], 3), round(pt[2], 3))


def _one_sided_corners(p: tuple[Point, Point, Point, Point]) -> tuple[Point, Point, Point, Point]:
    """`p` rotated (cyclic order kept) so its first three corners are distinct where it has three: MAME's back-face test
    takes the drawn polygon's first three corners, and a repeated corner among them (a triangle) gives a determinant of
    0, drawn from both sides."""
    for k in range(4):
        r = p[k:] + p[:k]
        if len({_key(r[0]), _key(r[1]), _key(r[2])}) == 3:
            return r
    return p


def _chains(run: list[Quad]) -> list[list[tuple[tuple[Point, Point, Point, Point], int, Quad]]]:
    """Chains of one tex run: lists of (drawn corners, exit link, quad). A record with link 1, 2 or 3 draws
    D = (old_p1, old_p0, p0, p1) and keeps as the next old edge (D1, D2), (D2, D3) or (D3, D0) respectively; the next
    polygon starts with that edge reversed, so a polygon sharing an edge with the previous one costs one record.
    Chains start in input order and take the lowest-index unused neighbour (ties: link 2, 1, 3); the last
    polygon of a chain keeps link 2. A one-sided quad (Phase 26 stage 2) is a chain of its own, its corners as given
    (`_one_sided_corners`): its winding decides the side it is drawn from."""
    index: dict[tuple, list[tuple[int, int]]] = {}
    for i, qd in enumerate(run):
        if qd.one_sided:
            continue
        for k in range(4):
            a, b = _key(qd.p[k]), _key(qd.p[(k + 1) % 4])
            if a != b:
                index.setdefault((a, b), []).append((i, k))
    used = [False] * len(run)
    out = []
    for s in range(len(run)):
        if used[s]:
            continue
        used[s] = True
        if run[s].one_sided:
            out.append([(_one_sided_corners(tuple(run[s].p)), 2, run[s])])
            continue
        d = tuple(run[s].p)
        chain = [[d, 2, run[s]]]
        while True:
            best = None
            for link, (a, b) in ((2, (d[2], d[3])), (1, (d[1], d[2])), (3, (d[3], d[0]))):
                ka, kb = _key(a), _key(b)
                if ka == kb:
                    continue
                for j, k in index.get((kb, ka), []):
                    if not used[j] and (best is None or j < best[1]):
                        best = (link, j, k, b, a)
            if best is None:
                break
            link, j, k, b, a = best
            used[j] = True
            r = run[j].p
            rot = r[k:] + r[:k]
            d = (b, a, rot[2], rot[3])                         # drawn with the previous record's points for the shared edge
            chain[-1][1] = link
            chain.append([d, 2, run[j]])
        out.append([tuple(c) for c in chain])
    return out


def encode_object(quads: list[Quad], tex_start: int, no_cull: bool = False, max_records: int = MAX_RECORDS) -> tuple[bytes, ObjectLayout]:
    """Quads (with non-decreasing tex_adr starting at tex_start) -> polygon-ROM object bytes.

    A chain starts with a link-0 record setting the 'old' points (quad.p[1], quad.p[0]) and a record (quad.p[2],
    quad.p[3]) that draws (old_p1, old_p0, p0, p1) = the quad; each following quad of the same tex sharing an edge
    with the polygon just drawn costs one record (`_chains`; Phase 18). Quads of one tex may be reordered and their
    corners rotated (cyclic order kept). The advance flag (0x1000) goes on the first record of the first chain of a
    tex one more than the previous."""
    if not quads:
        raise ConvertError("no quads")
    if quads[0].tex_adr != tex_start:
        raise ConvertError(f"first quad tex {quads[0].tex_adr:#x} != tex_start {tex_start:#x}")
    runs: list[list[Quad]] = []
    tex = tex_start
    for i, qd in enumerate(quads):
        if qd.tex_adr < tex:
            raise ConvertError(f"quad {i}: tex {qd.tex_adr:#x} decreases below {tex:#x}")
        if qd.tex_adr > tex + 1:
            raise ConvertError(f"quad {i}: tex {qd.tex_adr:#x} skips entries after {tex:#x}")
        if not runs or qd.tex_adr != tex:
            runs.append([])
        runs[-1].append(qd)
        tex = qd.tex_adr
    out = struct.pack("<6f", *quads[0].p[1], *quads[0].p[0])
    records = 0
    tex = tex_start
    draw = 0x1 | Z_MODE_MAX | (0x4000 if no_cull else 0)
    for run in runs:
        advance = 0x1000 if run[0].tex_adr == tex + 1 else 0
        tex = run[0].tex_adr
        for chain in _chains(run):
            d0, _, q0 = chain[0]
            out += _pack_record(0x1 | Z_MODE_MAX | advance, q0.normal, d0[1], d0[0])
            advance = 0
            for d, link, qd in chain:
                out += _pack_record((draw & ~0x4000 if qd.one_sided else draw) | (link << 8), qd.normal, d[2], d[3])
            records += 1 + len(chain)
    if records > max_records:
        raise ConvertError(f"{records} records exceed the {max_records} cap; split the object")
    out += _pack_record(0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return out, ObjectLayout(records, tex_start, tex)


def split_quads(quads: list[Quad], max_records: int = MAX_RECORDS) -> list[list[Quad]]:
    per = max_records // 2
    return [quads[i:i + per] for i in range(0, len(quads), per)]
