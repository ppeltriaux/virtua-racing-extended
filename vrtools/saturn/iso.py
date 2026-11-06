"""Minimal ISO9660 reader for a raw 2352-byte-per-sector MODE1 data track.

Only what the Saturn Virtua Racing disc needs: the primary volume descriptor,
directory records (recursed), file extents. No Joliet, no interleaving.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

RAW_SECTOR = 2352
SECTOR = 2048
SYNC_HEADER = 16
PVD_SECTOR = 16


class IsoError(Exception):
    pass


@dataclass(frozen=True)
class Entry:
    path: str
    lba: int
    size: int


class Iso2352:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._f = open(self.path, "rb")
        pvd = self.sector(PVD_SECTOR)
        if pvd[1:6] != b"CD001":
            raise IsoError(f"{self.path}: no ISO9660 volume descriptor at sector {PVD_SECTOR}")
        root = pvd[156:190]
        self._root_lba = struct.unpack_from("<I", root, 2)[0]
        self._root_size = struct.unpack_from("<I", root, 10)[0]
        self._entries: list[Entry] | None = None

    def sector(self, n: int) -> bytes:
        self._f.seek(n * RAW_SECTOR + SYNC_HEADER)
        data = self._f.read(SECTOR)
        if len(data) != SECTOR:
            raise IsoError(f"{self.path}: sector {n} past end of image")
        return data

    def _read_extent(self, lba: int, size: int) -> bytes:
        count = (size + SECTOR - 1) // SECTOR
        return b"".join(self.sector(lba + i) for i in range(count))[:size]

    def _records(self, lba: int, size: int) -> Iterator[tuple[str, int, int, int]]:
        data = self._read_extent(lba, size)
        off = 0
        while off < len(data):
            length = data[off]
            if length == 0:                       # padding: skip to the next sector
                off = (off // SECTOR + 1) * SECTOR
                continue
            rec = data[off:off + length]
            extent = struct.unpack_from("<I", rec, 2)[0]
            fsize = struct.unpack_from("<I", rec, 10)[0]
            flags = rec[25]
            name_len = rec[32]
            name = rec[33:33 + name_len].decode("latin-1")
            yield name, extent, fsize, flags
            off += length

    def _walk(self, lba: int, size: int, prefix: str) -> Iterator[Entry]:
        for name, extent, fsize, flags in self._records(lba, size):
            if name in ("\x00", "\x01"):
                continue
            if flags & 2:
                yield from self._walk(extent, fsize, f"{prefix}{name}/")
            else:
                yield Entry(prefix + name.split(";")[0], extent, fsize)

    def entries(self) -> list[Entry]:
        if self._entries is None:
            self._entries = list(self._walk(self._root_lba, self._root_size, ""))
        return self._entries

    def read(self, path: str) -> bytes:
        for e in self.entries():
            if e.path == path:
                return self._read_extent(e.lba, e.size)
        raise IsoError(f"{self.path}: no file {path!r}")

    def extract_all(self, out: Path, exclude: tuple[str, ...] = ("MOVIE",)) -> int:
        out = Path(out)
        written = 0
        for e in self.entries():
            if any(x in e.path for x in exclude):
                continue
            target = out / e.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self._read_extent(e.lba, e.size))
            written += 1
        return written
