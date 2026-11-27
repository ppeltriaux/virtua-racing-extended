"""Point lists (`NORMAL.PAT` racing line, `DIRLINE.PAT` guide line, `PIT00/01.PAT` pit paths, `RETURNnn.PAT` reset
points, `CAMnn.PAT` cameras, `MAPOBJ/YLnn.PAT`).

Layout (docs/spike/2026-11-phase90-ps2-disc-recon.md §3.4): u32 count, then 32 bytes per point: x, y, z as floats and
20 zero bytes. PS2 frame (arcade units, y down). The lines are sparse: one point per straight's end, a few per bend.
"""

from __future__ import annotations

from vrtools.ps2 import Ps2ReadError

import struct

import numpy as np

RECORD = 32


class PatError(Ps2ReadError):
    pass


def read_pat(data: bytes) -> np.ndarray:
    """(n, 3) float32 points."""
    if len(data) < 4:
        raise PatError("too short for a point count")
    n = struct.unpack_from("<I", data, 0)[0]
    if len(data) != 4 + RECORD * n:
        raise PatError(f"{n} points need {4 + RECORD * n} bytes, the file has {len(data)}")
    return np.frombuffer(data, dtype="<f4", count=8 * n, offset=4).reshape(n, 8)[:, :3].copy()


def densify(points: np.ndarray, step: float = 1.0, closed: bool = True) -> np.ndarray:
    """The polyline through `points` (n, 2 or 3) resampled every `step` units of arc (closed: back to the first)."""
    p = np.vstack([points, points[:1]]) if closed else np.asarray(points)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.arange(0.0, s[-1], step)
    return np.stack([np.interp(t, s, p[:, k]) for k in range(p.shape[1])], axis=1)
