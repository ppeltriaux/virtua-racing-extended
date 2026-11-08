"""The attract logo's "Extended": the word under the V.R. / Virtua / Racing title, in the logo's own style.

The logo (shown twice per attract loop) is two tile maps in the program ROM, blitted to tile layers 1 (top) and 0
(bottom): the upper half `0x2f6b18` (21 x 62 tiles) and the lower half `LOWER_MAP` (27 x 62, from tile row 21), mode
1 (halfword tile words minus 0x8000). Its characters are block 62 on (0x1f00..), loaded once at boot by bank 0's
first upload list; their palettes 0x3e..0x42 hold blue (4), red (3), black (2) and white (1) on the logo screen, and
they follow the logo's own palette changes. The boot list loads 565 characters to 0x1f00, so 0x2135..0x217f, the
tail of block 66 (palette 0x42), are never loaded by anything: the lettering's characters go there. The boot list ends
right where another upload's source begins (0x100174), so it cannot grow in place: a copy with one more pair goes to
bank 0's free space and the directory's pointer to it (bank 0 +0x20) moves there; the original list stays as it was.

"Extended" is drawn in the colours of "Racing": hard-edged bold italic sans letters in red with a black shadow 2 px
right and down, about half Racing's height, right-aligned with "Racing" (x 428) in the blue band under the V.R. The letters are repo-authored pixel runs (below).
"""
from __future__ import annotations

import struct

import numpy as np

from vrtools.arcade.panel import char_bytes
from vrtools.arcade.patch import PatchError, write_data
from vrtools.arcade.romset import RomSet

UPPER_MAP = 0x2F6B18
LOWER_MAP = 0x2F7550
LOWER_MAP_ROW = 21                       # the lower map's first tile row on screen
MAP_SHAPE = (27, 62)
TILE_BASE = 0x8000
CHAR_RAM = 0x780000
LOGO_FIRST_CHAR = 0x1F00
FREE_CHARS = tuple(range(0x2135, 0x2180))
BLUE, RED, SHADOW = 4, 3, 2              # the logo palettes' indices
SHADOW_OFFSET = 2
TEXT_AT = (268, 268)                     # the lettering's top-left on screen: right edge 429 (Racing's 428), 12 px under the V.R.
BANK0 = 0x100000                         # bank 0's window base

# "Extended" in bold italic, 26 rows of `x+width` runs of lit pixels (162 px wide).
LETTERING = (
    "5+19 115+5 157+5",
    "5+19 115+5 157+5",
    "5+19 49+5 115+5 157+5",
    "5+19 48+6 115+5 157+5",
    "4+20 48+5 114+5 156+5",
    "4+6 48+5 114+5 156+5",
    "4+5 48+5 114+5 156+5",
    "4+5 26+6 38+6 45+11 64+6 79+5 87+6 105+6 114+5 128+6 147+6 156+5",
    "4+5 27+6 37+6 44+12 61+11 79+5 85+10 103+16 125+11 145+16",
    "3+6 27+6 36+6 44+12 60+13 79+16 102+16 124+13 144+16",
    "3+18 27+6 35+6 44+11 59+15 79+17 101+17 123+15 143+17",
    "3+18 28+6 35+5 47+5 58+6 68+6 78+7 89+7 100+7 111+7 122+6 132+6 142+7 153+7",
    "3+18 28+11 46+6 57+6 69+5 78+6 90+6 100+5 112+6 121+6 133+5 142+5 154+6",
    "3+17 29+9 46+5 57+5 69+5 78+5 90+5 99+5 112+5 121+5 133+5 141+5 154+5",
    "2+18 29+8 46+5 56+6 69+5 78+5 90+5 99+5 112+5 120+6 133+5 141+5 154+5",
    "2+5 30+7 46+5 56+18 78+5 90+5 98+6 112+5 120+18 140+6 154+5",
    "2+5 30+6 46+5 56+18 77+5 90+5 98+5 112+5 120+18 140+5 154+5",
    "2+5 29+8 45+6 56+18 77+5 89+6 98+5 112+5 120+18 140+5 154+5",
    "1+6 28+9 45+5 55+6 77+5 89+5 98+5 111+5 119+6 140+5 153+5",
    "1+6 27+10 45+5 55+6 77+5 89+5 98+5 111+5 119+6 140+5 153+5",
    "1+5 26+12 45+5 55+6 67+6 77+5 89+5 98+5 110+6 119+6 131+6 140+5 152+6",
    "1+20 25+6 33+5 44+6 56+6 66+6 76+5 89+5 98+6 108+8 120+6 130+6 140+6 150+8",
    "1+19 25+5 33+6 44+9 56+15 76+5 88+5 98+18 120+15 140+18",
    "0+20 24+6 33+6 44+8 57+13 76+5 88+5 99+16 121+13 141+16",
    "0+20 23+6 34+6 44+8 58+11 76+5 88+5 100+9 110+5 122+11 142+9 152+5",
    "0+20 21+7 34+6 45+7 60+6 75+5 88+5 101+6 110+5 124+6 143+6 152+5",
)


def lettering() -> np.ndarray:
    """(29, 175) bool: the word's lit pixels."""
    width = max(int(x) + int(n) for row in LETTERING for x, n in (r.split("+") for r in row.split()))
    m = np.zeros((len(LETTERING), width), bool)
    for y, row in enumerate(LETTERING):
        for run in row.split():
            x, n = (int(v) for v in run.split("+"))
            m[y, x:x + n] = True
    return m


def title_canvas() -> tuple[np.ndarray, tuple[int, int]]:
    """The tile-aligned block of screen the lettering covers, as palette indices, and its first (tile row, tile col)."""
    m = lettering()
    x, y = TEXT_AT
    h, w = m.shape[0] + SHADOW_OFFSET, m.shape[1] + SHADOW_OFFSET
    r0, c0 = y // 8, x // 8
    r1, c1 = -(-(y + h) // 8), -(-(x + w) // 8)
    c = np.full(((r1 - r0) * 8, (c1 - c0) * 8), BLUE, np.uint8)
    oy, ox = y - r0 * 8, x - c0 * 8
    c[oy + SHADOW_OFFSET:oy + SHADOW_OFFSET + m.shape[0], ox + SHADOW_OFFSET:ox + SHADOW_OFFSET + m.shape[1]][m] = SHADOW
    c[oy:oy + m.shape[0], ox:ox + m.shape[1]][m] = RED
    return c, (r0, c0)


def _boot_entry(rs: RomSet) -> int:
    """Bank-0 offset of the boot's directory entry (pair list, palette block): directory word 0."""
    return struct.unpack_from("<I", rs.data, 0)[0] - BANK0


def _boot_list(rs: RomSet) -> int:
    """Bank-0 offset of the boot's character upload list."""
    return struct.unpack_from("<I", rs.data, _boot_entry(rs))[0] - BANK0


def boot_uploads(rs: RomSet) -> list[tuple[int, int, int]]:
    """(src window address, dst, count of 32-byte units) of the boot upload list, in order."""
    off, out = _boot_list(rs), []
    while True:
        src, dst = struct.unpack_from("<2I", rs.data, off)
        if src == 0:
            return out
        out.append((src, dst, struct.unpack_from("<I", rs.data, src - BANK0)[0]))
        off += 8


def _free_bank0_run(rs: RomSet, size: int) -> int:
    """A 16-aligned bank-0 offset with `size` erased (0xff) bytes, 16 bytes clear of anything before it."""
    from vrtools.arcade.picture import free_runs
    for at, n in free_runs(rs, [], min_size=size):
        if at < BANK0 + 0x100000 and n >= size:
            return at - BANK0
    raise PatchError(f"no free run of {size} bytes in bank 0 for the title lettering")


def install_title(rs: RomSet) -> RomSet:
    """A copy of `rs` whose attract logo says "Extended" under "Racing". PatchError when the set's logo or boot list
    is not the one this was drawn for."""
    base, mode, rows, cols = struct.unpack_from("<HHII", rs.program, LOWER_MAP - 0x200000)
    if (base, mode, (rows, cols)) != (TILE_BASE, 1, MAP_SHAPE):
        raise PatchError(f"the logo's lower map at {LOWER_MAP:#x} is not the expected 27 x 62 tile map")
    tiles = list(struct.unpack_from(f"<{rows * cols}H", rs.program, LOWER_MAP - 0x200000 + 12))
    uploads = boot_uploads(rs)
    loaded = {(d - CHAR_RAM) // 32 + k for _, d, n in uploads for k in range(n)}
    if loaded & set(FREE_CHARS) or LOGO_FIRST_CHAR not in loaded:
        raise PatchError("the boot upload list does not leave the logo block's tail free")

    canvas, (r0, c0) = title_canvas()
    blue_tile = np.full((8, 8), BLUE, np.uint8).tobytes()
    blue_char = tiles[0]                                                       # the map's corner: plain blue
    mr = r0 - LOWER_MAP_ROW
    chars: list[bytes] = []
    index: dict[bytes, int] = {}
    for r in range(canvas.shape[0] // 8):
        for q in range(canvas.shape[1] // 8):
            k = (mr + r) * cols + c0 + q
            if tiles[k] != blue_char:
                raise PatchError(f"the logo's lower map is not plain blue at tile ({mr + r}, {c0 + q})")
            t = canvas[r * 8:r * 8 + 8, q * 8:q * 8 + 8]
            if t.tobytes() == blue_tile:
                continue
            if t.tobytes() not in index:
                if len(chars) == len(FREE_CHARS):
                    raise PatchError("the title lettering needs more characters than the logo block has free")
                index[t.tobytes()] = FREE_CHARS[len(chars)]
                chars.append(char_bytes(t.tolist()))
            tiles[k] = index[t.tobytes()]

    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    blob = struct.pack("<I", len(chars)) + b"".join(chars)
    at = _free_bank0_run(out, len(blob))
    write_data(out, at, blob)
    old = _boot_list(rs)
    pairs = rs.data[old:old + 8 * len(uploads)] + struct.pack("<2I", BANK0 + at, CHAR_RAM + FREE_CHARS[0] * 32)
    new_list = pairs + bytes(8)                                                # src 0 ends the list
    lst = _free_bank0_run(out, len(new_list))
    write_data(out, lst, new_list)
    write_data(out, _boot_entry(rs), struct.pack("<I", BANK0 + lst))
    from vrtools.arcade.codepatch import patch_span
    body = struct.pack(f"<{len(tiles)}H", *tiles)
    patch_span(out, LOWER_MAP + 12, body, len(body))
    return out
