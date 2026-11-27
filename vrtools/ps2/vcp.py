"""Collision files (`XXX_ATnn.VCP` road and ground, `XXX_KBnn.VCP` walls).

Layout (docs/spike/2026-11-phase90-ps2-disc-recon.md §3.3): four i32 grid bounds in cells (min x, min z, max x, max z),
f32 cell size (6.0 on every file), u32 triangle count twice, then 80 bytes per triangle: three vertices (x, y, z, 1.0)
as floats and eight words `0, 0, k, 0, attr, 0, 0, 0`; then per-cell triangle lists (not decoded). The low byte of
`attr` is the surface kind (measured against the racing line: 0 tarmac, 1 kerb or edge strip, 2 and 3 verge; 0xa, 0xb,
0xd unknown); the high byte's meaning is unknown. Walls carry kind 1.
"""

from __future__ import annotations

from vrtools.ps2 import Ps2ReadError

import struct
from dataclasses import dataclass

import numpy as np

HEADER = struct.Struct("<4if2I")
RECORD = 80
ATTR_WORD = 16                  # attr's index among the record's 20 words (12 vertex floats, then 0, 0, k, 0, attr)

KIND_TARMAC = 0
KIND_KERB = 1
KINDS_VERGE = (2, 3)


class VcpError(Ps2ReadError):
    pass


@dataclass(frozen=True)
class CollisionSet:
    bounds: tuple[int, int, int, int]
    cell: float
    triangles: np.ndarray       # (n, 3, 3) float32, PS2 frame
    attrs: np.ndarray           # (n,) uint32
    tail: int                   # bytes of cell lists after the records

    @property
    def kinds(self) -> np.ndarray:
        return self.attrs & 0xFF

    def __len__(self) -> int:
        return len(self.triangles)


def read_vcp(data: bytes) -> CollisionSet:
    if len(data) < HEADER.size:
        raise VcpError("too short for a VCP header")
    x0, z0, x1, z1, cell, n, n2 = HEADER.unpack_from(data, 0)
    if n != n2:
        raise VcpError(f"triangle counts differ ({n}, {n2})")
    end = HEADER.size + RECORD * n
    if end > len(data):
        raise VcpError(f"{n} triangles need {end} bytes, the file has {len(data)}")
    words = np.frombuffer(data, dtype="<u4", count=20 * n, offset=HEADER.size).reshape(n, 20)
    floats = words.view("<f4")
    verts = floats[:, :12].reshape(n, 3, 4)
    if n and not np.all(verts[:, :, 3] == 1.0):
        raise VcpError("a vertex's w is not 1.0")
    return CollisionSet((x0, z0, x1, z1), float(cell), verts[:, :, :3].copy(), words[:, ATTR_WORD].copy(), len(data) - end)


def merged(sets: list[CollisionSet]) -> CollisionSet:
    """All sections' triangles as one set (bounds and tail summed loosely: bounds of the union, tails added)."""
    if not sets:
        return CollisionSet((0, 0, 0, 0), 6.0, np.zeros((0, 3, 3), np.float32), np.zeros(0, np.uint32), 0)
    b = (min(s.bounds[0] for s in sets), min(s.bounds[1] for s in sets), max(s.bounds[2] for s in sets), max(s.bounds[3] for s in sets))
    return CollisionSet(b, sets[0].cell, np.concatenate([s.triangles for s in sets]), np.concatenate([s.attrs for s in sets]),
                        sum(s.tail for s in sets))
