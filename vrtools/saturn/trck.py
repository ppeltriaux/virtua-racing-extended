"""Header of the Saturn per-course TRCK* files.

Each file begins with a table of 44 big-endian 32-bit pointers into Saturn
high work RAM. The file is loaded at LOAD_BASE, so pointer - LOAD_BASE is a
file offset. What each section holds is still being decoded; see
docs/formats/saturn-trck.md.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

LOAD_BASE = 0x06096000
POINTER_COUNT = 44
TABLE_SIZE = POINTER_COUNT * 4


class TrckError(Exception):
    pass


@dataclass(frozen=True)
class Section:
    index: int
    offset: int
    length: int
    data: memoryview


@dataclass(frozen=True)
class TrckFile:
    data: bytes
    pointers: list[int | None]

    @classmethod
    def from_bytes(cls, data: bytes) -> "TrckFile":
        if len(data) < TABLE_SIZE:
            raise TrckError(f"file too short for pointer table ({len(data)} bytes)")
        pointers: list[int | None] = []
        for i in range(POINTER_COUNT):
            p = struct.unpack_from(">I", data, i * 4)[0]
            if p == 0:
                pointers.append(None)
                continue
            if not (LOAD_BASE <= p < LOAD_BASE + len(data)):
                raise TrckError(f"pointer {i} = {p:#x} outside file [{LOAD_BASE:#x}, {LOAD_BASE + len(data):#x})")
            pointers.append(p)
        return cls(data, pointers)

    def offset(self, i: int) -> int | None:
        p = self.pointers[i]
        return None if p is None else p - LOAD_BASE

    def sections(self) -> list[Section]:
        offsets = sorted({o for o in (self.offset(i) for i in range(POINTER_COUNT)) if o is not None})
        ends = {o: (offsets[k + 1] if k + 1 < len(offsets) else len(self.data)) for k, o in enumerate(offsets)}
        view = memoryview(self.data)
        out = []
        for i in range(POINTER_COUNT):
            o = self.offset(i)
            if o is None:
                continue
            out.append(Section(i, o, ends[o] - o, view[o:ends[o]]))
        return out
