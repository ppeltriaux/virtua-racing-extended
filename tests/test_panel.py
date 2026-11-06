"""Select panels: the originals decode, generated ones fit the format and the free space."""
import math
import struct

import pytest

from vrtools.arcade.panel import (COLS, FREE_PALETTES, ORIGINAL_PANELS, ROWS, PanelMap, char_bitmap, char_bytes, char_pixels,
                                  decode_panel, encode_panel, free_chars, install_panels, render_panel, select_palette,
                                  select_uploads)
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet


def test_original_panels_decode(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    for art, (a, b) in ORIGINAL_PANELS.items():
        pa, pb = decode_panel(rs, a), decode_panel(rs, b)
        assert (pa.rows, pa.cols, pa.mode, pa.base) == (ROWS, COLS, 0, 0x3000 + 0x100 * art)
        assert (pb.rows, pb.cols, pb.mode, pb.base) == (ROWS, COLS, 1, 0x8000)
        assert len(pa.tiles) == ROWS * COLS and max(pa.tiles) < 256 and all(0x3300 <= t < 0x3800 for t in pb.tiles)
        assert encode_panel(pa) == rs.data[a - 0x100000:a - 0x100000 + 12 + ROWS * COLS]
        assert encode_panel(pb) == rs.data[b - 0x100000:b - 0x100000 + 12 + 2 * ROWS * COLS]
    bm = char_bitmap(rs, 0x3000 + 20)
    assert len(bm) == 8 and all(len(r) == 8 and all(0 <= v < 16 for v in r) for r in bm)
    assert char_pixels(char_bytes(bm)) == bm
    ups = select_uploads(rs)
    assert ups[0] == (0x14B92C, 0x7E0000, 146) and len(ups) == 9
    pal = select_palette(rs)
    assert pal["dst"] == 0x900C00 and pal["count"] == 0x1D0 and pal["words"][0] == 0xF81E


def test_free_chars_are_outside_the_select_screens_uploads(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    pool = free_chars(rs)
    covered = set()
    for src, dst, count in select_uploads(rs):
        if dst >= 0x780000:
            covered.update(range((dst - 0x780000) // 32, (dst - 0x780000) // 32 + count))
    slots = [c for lst in pool.slots.values() for c in lst]
    assert slots and not (set(slots) & covered) and all(0x3000 <= c < 0x4000 for c in slots)
    assert sum(len(v) for v in pool.slots.values()) >= 500                     # seven outline panels need about 420
    assert set(pool.roles) == set(pool.slots) and all(p in pool.roles for p in FREE_PALETTES)


def test_rendered_panel_fits_the_format(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    pool = free_chars(rs)
    pts = [(math.cos(a) * 300, math.sin(a) * 200) for a in [i / 50 * 2 * math.pi for i in range(50)]]
    r = render_panel(rs, pool, pts, "ALPINE", host_art=0)
    assert (r.a_map.rows, r.a_map.cols, r.a_map.mode, r.a_map.base) == (ROWS, COLS, 1, 0x8000) and (r.b_map.rows, r.b_map.cols) == (ROWS, COLS)
    assert 30 < len(r.chars) <= 120 and all(len(c) == 32 for c in r.chars.values())
    assert set(w & 0x3FFF for w in r.a_map.words()) <= set(r.chars)                          # the overlay only uses new characters (blank included)
    assert all(w & 0x8000 for w in r.a_map.words())                                          # high-priority category
    host_b = decode_panel(rs, ORIGINAL_PANELS[0][1])
    assert r.b_map.tiles[0] == host_b.tiles[0] and r.b_map.tiles[-1] == host_b.tiles[-1]        # frame kept
    mid = r.b_map.tiles[ROWS * COLS // 2 - 3:ROWS * COLS // 2 + 3]
    fill = char_pixels(r.chars[(host_b.base + mid[0]) & 0x3FFF])
    assert len(set(mid)) == 1 and len({v for row in fill for v in row}) == 1 and fill[0][0] != 0   # a new flat, non-transparent tile
    strip = r.b_map.tiles[19 * COLS + 1:19 * COLS + COLS - 1]
    assert len(set(strip)) == 1 and strip[0] != mid[0]                                         # the name strip flattened too (white)
    assert all(((host_b.base + t) & 0x3FFF) >> 7 in FREE_PALETTES for t in (mid[0], strip[0]))   # fills live in the generated palette block
    assert r.palettes and all(len(v) == 16 for v in r.palettes.values())
    from vrtools.arcade.panel import char_source
    assert char_source(rs, 0x3200 + 40) == rs.data[0x53D9C + 4 + 40 * 32:0x53D9C + 4 + 41 * 32]   # 0x7e4000 is Acropolis's upload (the last one covering it)
    assert set(r.palettes) <= set(FREE_PALETTES)


def test_install_panels_stays_in_bank0_free_space_and_extends_the_uploads(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    pool = free_chars(rs)
    pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    panels = [render_panel(rs, pool, pts, f"COURSE {k}", host_art=k % 3) for k in range(7)]
    out, addrs = install_panels(rs, panels)
    assert len(addrs) == 7 and all(0x1F2F80 <= a < 0x200000 and 0x1F2F80 <= b < 0x200000 for a, b in addrs)
    assert out.data[:0x4A324] == rs.data[:0x4A324] and out.data[0x4A32C:0xF2F83] == rs.data[0x4A32C:0xF2F83]   # only the phase-1 entry changes
    assert out.program == rs.program and out.boot == rs.boot
    ups = select_uploads(out)
    assert ups[:9] == select_uploads(rs) and len(ups) > 9 and all(0x780000 <= d < 0x800000 for _, d, _ in ups[9:])
    pal = select_palette(out)
    assert pal["dst"] == 0x900C00 and pal["count"] == 0x200 and pal["words"][:0x1D0] == select_palette(rs)["words"]
    end = pal["ptr"] - 0x100000 + 8 + 2 * pal["count"]
    assert struct.unpack_from("<2I", out.data, end) == (0, 0)                                  # the palette loader stops at dst 0
    a0 = decode_panel(out, addrs[0][0])
    assert a0.mode == 1 and set(w & 0x3FFF for w in a0.words()) <= set(panels[0].chars)
    with pytest.raises(PatchError):
        install_panels(out, panels)                                                           # the free tail is taken
