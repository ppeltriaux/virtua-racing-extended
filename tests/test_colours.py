import struct
from pathlib import Path

import pytest

from vrtools.arcade.colours import (PALETTE_BASE, PALETTE_SIZE, TABLE_BASE, ColourTable, Palette, colour_of, colour_table,
                                    free_runs, nearest, palette_from_dump, palette_from_rom, rgb, rgb555_word)
from vrtools.arcade.romset import REQUIRED_FILES, RomSet


def _rs(program: bytes) -> RomSet:
    files = {name: bytes(8) for name in REQUIRED_FILES}
    files["epr-14882.14"], files["epr-14883.15"] = program[0::2], program[1::2]
    for n in ("mpr-14880.6", "mpr-14881.7", "mpr-14884.8", "mpr-14885.9", "mpr-14886.10", "mpr-14887.11", "mpr-14888.12", "mpr-14889.13"):
        files[n] = bytes(8)
    return RomSet.from_files(files)


def test_rgb_decode_xbgr555():
    assert rgb(0x801F) == (248, 0, 0)
    assert rgb(0x83E0) == (0, 248, 0)
    assert rgb(0xFC00) == (0, 0, 248)
    assert rgb555_word(248, 0, 0) == 0x801F


def test_nearest_picks_closest():
    pal = Palette([0x8000, 0x801F, 0x83E0, 0xFC00])      # black, red, green, blue at 0x1000..0x1003
    assert nearest(pal, (200, 10, 10)) == 0x1001
    assert nearest(pal, (5, 5, 5)) == 0x1000


def test_colour_table_is_program_rom():
    prog = bytes(0x20) + struct.pack("<4H", 0x0002, 0x00EE, 0xFFFF, 0x0400) + bytes(0x100000 - 0x28)
    t = colour_table(_rs(prog))
    assert t.entry(TABLE_BASE + 0x10) == 0x0002 and t.entry(TABLE_BASE + 0x11) == 0x00EE
    assert t.rom_offset(TABLE_BASE + 0x10) == 0x20
    with pytest.raises(ValueError):
        t.entry(TABLE_BASE - 1)


def test_free_runs_skip_tile_record_area():
    prog = bytearray(b"\xff" * 0x100000)
    prog[0:0x1000] = bytes(0x1000)
    runs = free_runs(colour_table(_rs(bytes(prog))), min_entries=1024)
    assert runs and runs[0][0] == TABLE_BASE + 0x800
    assert all(t.rom_offset(s) + 2 * n <= 0xE0000 for t, (s, n) in [(colour_table(_rs(bytes(prog))), r) for r in runs])


def test_colour_of_resolves_table_then_palette():
    prog = bytearray(0x100000)
    struct.pack_into("<H", prog, 0x20, 0x0001 | 0x400)          # entry TABLE_BASE+0x10 -> palette 0x1001, bright
    t = colour_table(_rs(bytes(prog)))
    pal = Palette([0x8000, 0x801F] + [0] * (PALETTE_SIZE - 2))
    assert colour_of(t, pal, TABLE_BASE + 0x10) == ((248, 0, 0), True)


def test_palette_from_dump(tmp_path):
    dump = bytearray(0x1C000)
    struct.pack_into("<2H", dump, 2 * PALETTE_BASE, 0x8000, 0x801F)
    p = tmp_path / "pal.bin"; p.write_bytes(dump)
    pal = palette_from_dump(p)
    assert len(pal.entries) == PALETTE_SIZE and pal.entries[1] == 0x801F


def test_real_table_and_palette(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    t = colour_table(rs)
    assert t.entry(0x45802) == 0x0002 and t.entry(0x45803) == 0x00EE          # Big Forest tiles' first records
    runs = free_runs(t, reserved=None)
    assert runs[0] == (0x7C6B8, 47432) and runs[1] == (0x98C21, 29663)
    assert free_runs(t)[0] == (0x98C21, 29663)                                 # the first run is the directory's reserved area
    pal = palette_from_rom(rs, 0)
    assert len(pal.entries) == PALETTE_SIZE and len(set(pal.entries)) > 400
    dump = Path("out/p4/pal/palette_2400.bin")
    if dump.exists():
        d = palette_from_dump(dump)
        assert sum(1 for a, b in zip(pal.entries, d.entries) if a == b) >= 850


def test_free_runs_reserve_the_code_area(romset_zip):
    """The directory and its routines live in unused colour-table bytes (program ROM 0x278d70, 92 KB): the colour
    allocator must never hand those entries out."""
    from vrtools.arcade.colours import RESERVED_CODE, TABLE_BASE, colour_table, free_runs
    from vrtools.arcade.romset import RomSet

    table = colour_table(RomSet.from_zip(romset_zip))
    lo, hi = TABLE_BASE + RESERVED_CODE[0] // 2, TABLE_BASE + (RESERVED_CODE[0] + RESERVED_CODE[1]) // 2
    assert any(a < hi and a + n > lo for a, n in free_runs(table, reserved=None))      # the area is free, so unreserved it shows
    assert all(a + n <= lo or a >= hi for a, n in free_runs(table))                     # reserved by default
    assert sum(n for _, n in free_runs(table)) >= 4096                                   # and plenty remains for the converters
