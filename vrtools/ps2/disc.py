"""The disc: an ISO 9660 file system in one of two forms, told apart by its content (never by the file's suffix).

The owner's image is given by `VR_PS2_DISC`: a `.cue` (its first FILE line names the track file), a `.bin`, or a plain `.iso`.
- raw: MODE2/2352 sectors, user data at +24 of each (the volume descriptor at byte 16*2352 + 24);
- plain: 2048-byte sectors, the user data only (the volume descriptor at byte 16*2048).
Tests that need the real disc skip without it.
"""

from __future__ import annotations

import os
from pathlib import Path

from vrtools.saturn.iso import PVD_SECTOR, RAW_SECTOR, SECTOR, Iso2352, IsoError

MODE2_HEADER = 24               # sync 12, header 4, subheader 8
ENV = "VR_PS2_DISC"
EXECUTABLE = "SLPM_624.43"
COURSE_DIR = "DATA/COURSE"


def ps2_disc() -> Path | None:
    """The `.cue` (or `.bin`) of the PS2 disc (VR_PS2_DISC), or None."""
    value = os.environ.get(ENV)
    return Path(value) if value else None


def bin_of(path: Path) -> Path:
    """The track file of a `.cue` (its first FILE line), or `path` itself."""
    path = Path(path)
    if path.suffix.lower() != ".cue":
        return path
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if line.upper().startswith("FILE"):
            name = line[line.index('"') + 1:line.rindex('"')] if '"' in line else line.split()[1]
            return path.parent / name
    raise IsoError(f"{path}: no FILE line")


PLAIN = 0                       # form of an image of bare 2048-byte sectors
RAW = 1                         # form of an image of MODE2/2352 sectors


def _has_pvd(f, offset: int) -> bool:
    f.seek(offset)
    head = f.read(6)
    return head == b"\x01CD001"


def image_form(path: Path) -> int:
    """PLAIN or RAW, by where the primary volume descriptor (type 1, `CD001`) is; IsoError if it is in neither place."""
    path = Path(path)
    with open(path, "rb") as f:
        if _has_pvd(f, PVD_SECTOR * RAW_SECTOR + MODE2_HEADER):
            return RAW
        if _has_pvd(f, PVD_SECTOR * SECTOR):
            return PLAIN
    raise IsoError(f"{path}: no ISO 9660 volume descriptor (type 1, 'CD001') at byte {PVD_SECTOR * SECTOR} "
                   f"(plain 2048-byte sectors) or at byte {PVD_SECTOR * RAW_SECTOR + MODE2_HEADER} (MODE2/2352 sectors)")


class Ps2Disc(Iso2352):
    """`Iso2352` over either form: MODE2 Form 1 sectors (user data at +24 of 2352) or a plain 2048-byte-sector image."""

    def __init__(self, path: Path):
        track = bin_of(path)
        self.form = image_form(track)           # before the base class reads the volume descriptor through `sector`
        super().__init__(track)

    def sector(self, n: int) -> bytes:
        if self.form == PLAIN:
            self._f.seek(n * SECTOR)
        else:
            self._f.seek(n * RAW_SECTOR + MODE2_HEADER)
        data = self._f.read(SECTOR)
        if len(data) != SECTOR:
            raise IsoError(f"{self.path}: sector {n} past end of image")
        return data
