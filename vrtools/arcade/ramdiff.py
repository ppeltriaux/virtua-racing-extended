"""Compare work-RAM dumps written by memtrace.lua and find smoothly changing values."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

RAM_BASE = 0x500000


class RamDiffError(Exception):
    pass


@dataclass(frozen=True)
class Dump:
    frame: int
    base: int
    data: bytes


@dataclass(frozen=True)
class Diff:
    addr: int
    value_a: int
    value_b: int


def load_dump(path: Path) -> Dump:
    m = re.search(r"\.ram\.(\d+)\.bin$", str(path))
    if not m:
        raise RamDiffError(f"{path}: expected a name ending in .ram.<frame>.bin")
    return Dump(int(m.group(1)), RAM_BASE, Path(path).read_bytes())


_FMT = {1: "<B", 2: "<H", 4: "<I"}


def diff_dumps(a: Dump, b: Dump, width: int = 1, allow_frame_mismatch: bool = False) -> list[Diff]:
    if len(a.data) != len(b.data):
        raise RamDiffError(f"dump size mismatch: {len(a.data)} vs {len(b.data)} bytes")
    if a.frame != b.frame and not allow_frame_mismatch:
        raise RamDiffError(f"dump frame mismatch: {a.frame} vs {b.frame} (pass allow_frame_mismatch=True)")
    fmt = _FMT[width]
    out: list[Diff] = []
    for off in range(0, len(a.data) - width + 1, width):
        va = struct.unpack_from(fmt, a.data, off)[0]
        vb = struct.unpack_from(fmt, b.data, off)[0]
        if va != vb:
            out.append(Diff(a.base + off, va, vb))
    return out


def find_smooth_vectors(dumps: list[Dump], stride: int = 4, max_step: float = 10.0) -> list[tuple[int, list[float]]]:
    """Addresses holding a 32-bit float that moves monotonically by less than max_step between consecutive dumps."""
    if len(dumps) < 3:
        raise RamDiffError("need at least three dumps")
    n = min(len(d.data) for d in dumps)
    out: list[tuple[int, list[float]]] = []
    for off in range(0, n - 3, stride):
        vals = []
        ok = True
        for d in dumps:
            v = struct.unpack_from("<f", d.data, off)[0]
            if v != v or abs(v) > 1e6:            # NaN / absurd
                ok = False
                break
            vals.append(v)
        if not ok:
            continue
        steps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
        if all(s == 0 for s in steps):
            continue
        if any(abs(s) >= max_step for s in steps):
            continue
        if all(s >= 0 for s in steps) or all(s <= 0 for s in steps):
            out.append((dumps[0].base + off, vals))
    return out
