"""The Model 1 renderer's colour pipeline (docs/formats/model1-colours.md).

Each polygon record carries a 'texture address' `tex_adr` indexing the TGP colour table; the table is the
1 MB program ROM copied verbatim at boot (entry i at ROM byte 2*(i - TABLE_BASE)); a table word selects a
palette entry 0x1000 | (word & 0x3ff) (bit 0x400 = full bright), and palette entries are xBGR555.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from vrtools.arcade.romset import RomSet

TABLE_BASE = 0x40000               # tex_adr of program ROM byte 0
TABLE_ENTRIES = 0x80000            # the whole 1 MB program ROM
TILE_RECORD_ROM = 0xE0000          # program-ROM bytes from here hold tile records/tables, not usable as colours
RESERVED_CODE = (0x78D70, 92 * 1024)   # program-ROM bytes of the ten-course directory and its V60 routines (course.CODE_FREE)
PALETTE_BASE = 0x1000              # palette index of the first polygon colour
PALETTE_SIZE = 0x400
PALETTE_ROM = {0: 0xEC980, 1: 0xEC980, 2: 0xEC980}   # program-ROM offset of the 0x1000.. polygon palette: boot routine 0xfe6b04 copies 0x2ec980..0x2ed082 to palette RAM 0x902000 for every course
BRIGHT = 0x400


@dataclass(frozen=True)
class ColourTable:
    program: bytes

    def rom_offset(self, tex_adr: int) -> int:
        if not (TABLE_BASE <= tex_adr < TABLE_BASE + TABLE_ENTRIES):
            raise ValueError(f"tex_adr {tex_adr:#x} outside the colour table")
        return 2 * (tex_adr - TABLE_BASE)

    def entry(self, tex_adr: int) -> int:
        return struct.unpack_from("<H", self.program, self.rom_offset(tex_adr))[0]


@dataclass(frozen=True)
class Palette:
    entries: list[int]             # words for palette indices PALETTE_BASE..PALETTE_BASE+PALETTE_SIZE-1


def colour_table(rs: RomSet) -> ColourTable:
    return ColourTable(rs.program)


def free_runs(table: ColourTable, min_entries: int = 1024,
              reserved: tuple[int, int] | None = RESERVED_CODE) -> list[tuple[int, int]]:
    """(tex_adr, count) runs of 0xFFFF entries below the tile-record area, in file order; entries whose
    program-ROM bytes fall in `reserved` (offset, length) are never offered (the directory's code area)."""
    prog = table.program
    limit = min(len(prog), TILE_RECORD_ROM) // 2
    lo, hi = (reserved[0] // 2, (reserved[0] + reserved[1] + 1) // 2) if reserved else (0, 0)
    runs = []
    start = None
    for i in range(limit + 1):
        free = i < limit and prog[2 * i] == 0xFF and prog[2 * i + 1] == 0xFF and not (lo <= i < hi)
        if free and start is None:
            start = i
        elif not free and start is not None:
            if i - start >= min_entries:
                runs.append((TABLE_BASE + start, i - start))
            start = None
    return runs


def rgb(word: int) -> tuple[int, int, int]:
    return ((word & 0x1F) << 3, ((word >> 5) & 0x1F) << 3, ((word >> 10) & 0x1F) << 3)


def rgb555_word(r: int, g: int, b: int) -> int:
    return 0x8000 | ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)


def nearest(pal: Palette, colour: tuple[int, int, int]) -> int:
    """Palette index (PALETTE_BASE + i) of the entry closest to `colour` in RGB."""
    best = None
    for i, w in enumerate(pal.entries):
        r, g, b = rgb(w)
        d = (r - colour[0]) ** 2 + (g - colour[1]) ** 2 + (b - colour[2]) ** 2
        if best is None or d < best[0]:
            best = (d, i)
    return PALETTE_BASE + best[1]


def colour_of(table: ColourTable, pal: Palette, tex_adr: int) -> tuple[tuple[int, int, int], bool]:
    w = table.entry(tex_adr)
    return rgb(pal.entries[w & 0x3FF]), bool(w & BRIGHT)


def palette_from_dump(path: Path) -> Palette:
    """Palette RAM dump (V60 0x900000..0x91bfff) -> the polygon palette."""
    data = Path(path).read_bytes()
    off = 2 * PALETTE_BASE
    return Palette(list(struct.unpack_from(f"<{PALETTE_SIZE}H", data, off)))


def palette_from_rom(rs: RomSet, course_index: int) -> Palette:
    if course_index not in PALETTE_ROM:
        raise ValueError(f"palette ROM offset for course {course_index} is not known")
    off = PALETTE_ROM[course_index]
    return Palette(list(struct.unpack_from(f"<{PALETTE_SIZE}H", rs.program, off)))
