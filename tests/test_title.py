"""The attract logo's "Extended" lettering (title.py): drawn in the logo's own red with its black drop shadow, in the
blue band under "V.R.", from the free characters at the end of the logo's character blocks."""
import struct

import numpy as np
import pytest

from vrtools.arcade.panel import char_pixels
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet
from vrtools.arcade.title import (BLUE, FREE_CHARS, LOWER_MAP, LOWER_MAP_ROW, RED, SHADOW, TEXT_AT, boot_uploads,
                                  install_title, lettering, title_canvas)


def test_the_lettering_is_the_word_in_one_piece():
    m = lettering()
    assert m.shape == (26, 162)
    assert m[:, 0].any() and m[:, -1].any() and m[0].any() and m[-1].any()      # trimmed to the word


def test_the_canvas_is_red_letters_over_a_black_shadow_on_blue():
    c, (r0, c0) = title_canvas()
    m = lettering()
    y, x = TEXT_AT[1] - r0 * 8, TEXT_AT[0] - c0 * 8
    assert set(np.unique(c)) == {BLUE, RED, SHADOW}
    assert (c[y:y + m.shape[0], x:x + m.shape[1]][m] == RED).all()
    assert (c == RED).sum() == m.sum()
    shadow = np.zeros_like(c, bool)
    shadow[y + 2:y + 2 + m.shape[0], x + 2:x + 2 + m.shape[1]] = m
    assert ((c == SHADOW) == (shadow & (c != RED))).all()                        # the shadow, 2 px right and down


def test_the_lettering_fits_the_free_characters():
    c, _ = title_canvas()
    tiles = {c[r:r + 8, q:q + 8].tobytes() for r in range(0, c.shape[0], 8) for q in range(0, c.shape[1], 8)}
    tiles.discard(np.full((8, 8), BLUE, np.uint8).tobytes())
    assert len(tiles) <= len(FREE_CHARS) == 75


def test_the_lettering_sits_in_the_blue_band_right_aligned_with_racing():
    c, (r0, c0) = title_canvas()
    m = lettering()
    assert abs(TEXT_AT[0] + m.shape[1] - 1 - 428) <= 1                          # "Racing"'s right edge (428)
    assert TEXT_AT[1] >= 256 + 8                                                # below the V.R.
    assert (r0 + c.shape[0] // 8) * 8 <= 384 and (c0 + c.shape[1] // 8) * 8 <= 496


def _lower_map(rs):
    base, mode, rows, cols = struct.unpack_from("<HHII", rs.program, LOWER_MAP - 0x200000)
    t = struct.unpack_from(f"<{rows * cols}H", rs.program, LOWER_MAP - 0x200000 + 12)
    return np.array([(base + v) & 0x3FFF for v in t]).reshape(rows, cols)


def _char_ram(rs):
    ram = {}
    for src, dst, count in boot_uploads(rs):
        o = src - 0x100000 + 4
        for k in range(count):
            ram[(dst - 0x780000) // 32 + k] = rs.data[o + 32 * k:o + 32 * k + 32]
    return ram


def test_install_title_letters_the_logos_lower_map(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    out = install_title(rs)
    before, after = _lower_map(rs), _lower_map(out)
    c, (r0, c0) = title_canvas()
    h, w = c.shape[0] // 8, c.shape[1] // 8
    mr = r0 - LOWER_MAP_ROW
    changed = np.argwhere(before != after)
    assert changed.size and changed[:, 0].min() >= mr and changed[:, 0].max() < mr + h
    assert changed[:, 1].min() >= c0 and changed[:, 1].max() < c0 + w            # only the lettering's tiles change
    ram = _char_ram(out)
    for r in range(h):
        for q in range(w):
            px = np.array(char_pixels(ram[after[mr + r, c0 + q]]))
            assert (px == c[r * 8:r * 8 + 8, q * 8:q * 8 + 8]).all(), (r, q)


def test_the_new_characters_load_with_the_boot_uploads(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    out = install_title(rs)
    old, new = boot_uploads(rs), boot_uploads(out)
    assert new[:-1] == old
    src, dst, count = new[-1]
    assert dst == 0x780000 + FREE_CHARS[0] * 32 and 0 < count <= len(FREE_CHARS)
    assert 0x100000 <= src < 0x200000                                            # bank 0: mapped when the boot loads it
    used = {(d - 0x780000) // 32 + k for _, d, n in old for k in range(n)}
    assert not used & set(FREE_CHARS)


def test_install_title_refuses_a_set_whose_lower_map_is_not_the_logo(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    program = bytearray(rs.program)
    struct.pack_into("<I", program, LOWER_MAP - 0x200000 + 4, 26)                   # rows
    bad = RomSet(bytes(program), rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    with pytest.raises(PatchError):
        install_title(bad)


def test_the_attract_logo_says_extended(tmp_path, romset_zip):
    """MAME: the patched set's attract logo shows the lettering where title_canvas puts it (red letters, black
    shadow, blue around), and the logo above it is the original's."""
    import shutil
    from PIL import Image
    from vrtools.mame.runner import LUA_DIR, run_mame

    build = tmp_path / "build"
    build.mkdir()
    install_title(RomSet.from_zip(romset_zip)).to_zip(build / "vr.zip", source=romset_zip)
    for extra in ("model1io.zip", "m1comm.zip"):
        shutil.copy(romset_zip.parent / extra, build / extra)
    run_mame(LUA_DIR / "attract_snaps.lua", 75, tmp_path / "run", build, timeout=900)
    c, (r0, c0) = title_canvas()
    logo = []
    for f in sorted((tmp_path / "run" / "snap").rglob("*.png")):
        im = np.array(Image.open(f).convert("RGB")).astype(int)
        if (im[300:384, :, 2] >= 240).mean() > 0.6:                              # the logo's blue screen
            s = im[r0 * 8:r0 * 8 + c.shape[0], c0 * 8:c0 * 8 + c.shape[1]]
            seen = np.full(c.shape, -1)
            seen[(s[..., 2] > 200) & (s[..., :2].max(-1) < 60)] = BLUE
            seen[(s[..., 0] > 200) & (s[..., 1:].max(-1) < 60)] = RED
            seen[s.max(-1) < 60] = SHADOW
            logo.append(seen)
    assert len(logo) >= 5
    still = [s for s in logo if (s == c).all()]                                  # frames where the lower layer is at rest
    assert len(still) >= len(logo) // 2, [int((s != c).sum()) for s in logo]
