"""TGP (MB86233) collision data in the copro data ROM: slot table, quad-index lists, 16-word quads.

Addresses are 32-bit little-endian *words* of `RomSet.copro_data`. See docs/formats/model1-tgp-collision.md
and docs/spike/2026-11-tgp-collision.md.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from vrtools.arcade.course import collision_map, course_table
from vrtools.arcade.romset import RomSet

SLOT_OF_COURSE = {0: 2, 1: 0, 2: 1}      # course index (BF, BB, AC) -> slot = course data index
SLOT_LIST = 0x10                         # word offset of the 16 list-block addresses
SLOT_POOL = 0x20                         # word offset of the 16 quad-pool addresses
SLOTS = 16
QUAD_WORDS = 16
FREE_WORD = 0xFFFFFFFF
MAX_LIST = 256                           # a cell list longer than this is not a list (arcade max is 45)
MIN_AREA = 1e-6


class TgpError(Exception):
    pass


Point = tuple[float, float, float]


@dataclass(frozen=True)
class Quad16:
    corners: tuple[Point, Point, Point, Point]
    centre: Point
    attr: int                            # raw u32 (sign-extended 16-bit in the originals; meaning unknown)


SURFACE_TARMAC = 1                       # surface byte kinds (low nibble): 1 tarmac, 8 kerb zone, 2 grass, 5 run-off
SURFACE_GRASS = 2
SURFACE_WALL = 5                         # the run-off's edge: the game stops a car on it (wheel kind 0x20 = 1 << 5; Phase 16 recon §4)


@dataclass(frozen=True)
class Collision:
    lists: dict[int, list[int]]          # word offset inside the list block -> quad indices, in offset order
    quads: list[Quad16]
    surface: bytes | None = None         # one byte per quad (the course bank's surface table); None = leave the bank's
    merged: int = 0                      # slices fused into longer quads on straights (convert.collision, merge=True)
    dropped_verges: int = 0              # verge quads left out because their centre lay on tarmac
    coverage: dict | None = None         # convert.collision.fill_coverage's report (gaps, grown, fillers), when run
    lanes: list | None = None            # Phase 22c: per centreline point (left, right) AI lane scale (convert.collision.lane_scales)

    @property
    def n_tarmac(self) -> int:
        """Tarmac quads (surface kind 1), which come first in `quads` in lap order; 0 without a surface table."""
        return sum(1 for b in self.surface if b == SURFACE_TARMAC) if self.surface else 0

    def check(self) -> None:
        """Every index names a quad and every quad is referenced; offsets are consecutive from the first."""
        n = len(self.quads)
        seen = [False] * n
        pos = None
        if self.lists.get(0):
            raise TgpError("the list at offset 0 is the off-road list and must be empty")
        for off in self.lists:
            if pos is not None and off != pos:
                raise TgpError(f"list at {off:#x} does not follow the previous list (expected {pos:#x})")
            pos = off + 1 + len(self.lists[off])
            for i in self.lists[off]:
                if not (0 <= i < n):
                    raise TgpError(f"list at {off:#x} references quad {i}, pool has {n}")
                seen[i] = True
        if not all(seen):
            raise TgpError(f"quad {seen.index(False)} is referenced by no list")
        if self.surface is not None and len(self.surface) != n:
            raise TgpError(f"surface table has {len(self.surface)} bytes for {n} quads")

    @property
    def list_words(self) -> int:
        return sum(1 + len(v) for v in self.lists.values())


_cache: list = [None, None]              # [the copro_data bytes object itself, its words]: a kept reference, compared by identity


def words(rs: RomSet) -> tuple[int, ...]:
    if _cache[0] is not rs.copro_data:
        _cache[0] = rs.copro_data
        _cache[1] = struct.unpack(f"<{len(rs.copro_data) // 4}I", rs.copro_data)
    return _cache[1]


def slot_table(rs: RomSet) -> list[tuple[int, int]]:
    w = words(rs)
    return [(w[SLOT_LIST + i], w[SLOT_POOL + i]) for i in range(SLOTS)]


def _f(x: int) -> float:
    return struct.unpack("<f", struct.pack("<I", x))[0]


def _u(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def decode_quad(w, at: int) -> Quad16:
    q = w[at:at + QUAD_WORDS]
    if len(q) < QUAD_WORDS:
        raise TgpError(f"quad at {at:#x} runs past the ROM")
    corners = tuple((_f(q[3 * k]), _f(q[3 * k + 1]), _f(q[3 * k + 2])) for k in range(4))
    return Quad16(corners, (_f(q[12]), _f(q[13]), _f(q[14])), q[15])


def xz_area(q: Quad16) -> float:
    c = q.corners
    return sum(c[k][0] * c[(k + 1) % 4][2] - c[(k + 1) % 4][0] * c[k][2] for k in range(4)) / 2


def encode_quad(q: Quad16, strict: bool = True) -> bytes:
    """strict: refuse a quad with no XZ area (the TGP's edge-sign test is meaningless on it). The originals
    contain one such quad (Acropolis index 4973, a vertical wall), so re-emission passes strict=False."""
    if len(q.corners) != 4:
        raise TgpError("a quad has four corners")
    if strict and abs(xz_area(q)) < MIN_AREA:
        raise TgpError(f"quad has no XZ area: {q.corners}")
    if not (0 <= q.attr <= 0xFFFFFFFF):
        raise TgpError(f"attr {q.attr:#x} does not fit u32")
    vals = [_u(v) for c in q.corners for v in c] + [_u(v) for v in q.centre] + [q.attr]
    return struct.pack("<16I", *vals)


def encode_quads(quads: list[Quad16], strict: bool = True) -> bytes:
    return b"".join(encode_quad(q, strict) for q in quads)


def encode_lists(lists: dict[int, list[int]]) -> bytes:
    out = []
    pos = None
    for off, idx in lists.items():
        if pos is None:
            pos = off
        if off != pos:
            raise TgpError(f"list at {off:#x} does not follow the previous list (expected {pos:#x})")
        if len(idx) > MAX_LIST or any(not (0 <= i <= 0xFFFFFFFF) for i in idx):
            raise TgpError(f"list at {off:#x}: bad length or index")
        out.append(struct.pack(f"<{1 + len(idx)}I", len(idx), *idx))
        pos = off + 1 + len(idx)
    return b"".join(out)


def _block_and_pool(rs: RomSet, course_index: int) -> tuple[int, int]:
    if course_index not in SLOT_OF_COURSE:
        raise TgpError(f"course {course_index} has no TGP slot")
    return slot_table(rs)[SLOT_OF_COURSE[course_index]]


def decode_collision(rs: RomSet, course_index: int) -> Collision:
    """The course's lists (walked from the first collision-map id to the last) and every quad they reference."""
    w = words(rs)
    block, pool = _block_and_pool(rs, course_index)
    ids = sorted({v for v in collision_map(rs, course_table(rs)[course_index]) if v})
    if not ids:
        raise TgpError(f"course {course_index}: collision map is empty")
    idset = set(ids)
    lists: dict[int, list[int]] = {}
    pos = ids[0]
    while pos <= ids[-1]:
        if pos not in idset:
            raise TgpError(f"course {course_index}: list at {pos:#x} is referenced by no cell")
        count = w[block + pos]
        if count > MAX_LIST:
            raise TgpError(f"course {course_index}: list at {pos:#x} has count {count}")
        lists[pos] = list(w[block + pos + 1: block + pos + 1 + count])
        pos += 1 + count
    missing = idset - set(lists)
    if missing:
        raise TgpError(f"course {course_index}: cell ids without a list: {sorted(missing)[:4]}")
    n = 1 + max((i for v in lists.values() for i in v), default=-1)
    if pool + QUAD_WORDS * n > len(w):
        raise TgpError(f"course {course_index}: {n} quads at {pool:#x} run past the ROM")
    quads = [decode_quad(w, pool + QUAD_WORDS * i) for i in range(n)]
    col = Collision(lists, quads)
    col.check()
    return col


def verify_lossless(rs: RomSet, course_index: int) -> list[str]:
    """Re-encode the course's lists and quads and compare with the ROM bytes; names of mismatches."""
    col = decode_collision(rs, course_index)
    block, pool = _block_and_pool(rs, course_index)
    first = next(iter(col.lists))
    problems = []
    lists = encode_lists(col.lists)
    at = 4 * (block + first)
    if rs.copro_data[at:at + len(lists)] != lists:
        problems.append("lists")
    quads = encode_quads(col.quads, strict=False)
    at = 4 * pool
    if rs.copro_data[at:at + len(quads)] != quads:
        problems.append("quads")
    return problems
