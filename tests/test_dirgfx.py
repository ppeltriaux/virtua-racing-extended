"""Phase 26 stage 3 (plan Task 5): the COURSE DIRECTION screen's arrows and SELECT DIRECTION caption (dirgfx.py), drawn by the
module's own code, and the data block that carries them with their maps, palette sets and the screen's draw list (plan D11).
The wheel panel's caption area is measured on the game's own panel (map 0x1e0f71), decoded from the user's ROM at test time."""
import math
import struct

import numpy as np
import pytest

from vrtools.arcade import dirgfx as g


def _components(mask):
    """The 8-connected components of a boolean image, as lists of (y, x)."""
    seen, out = np.zeros_like(mask), []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack, comp = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    v, u = y + dy, x + dx
                    if 0 <= v < mask.shape[0] and 0 <= u < mask.shape[1] and mask[v, u] and not seen[v, u]:
                        seen[v, u] = True
                        stack.append((v, u))
        out.append(comp)
    return out


def _visual_angle(y, x):
    """Degrees anticlockwise as seen (screen y down) from three o'clock about the arrow's centre."""
    c = (g.ARROW_PX - 1) / 2
    return math.degrees(math.atan2(c - y, x - c)) % 360


@pytest.mark.parametrize("clockwise", [False, True])
def test_each_arrow_is_an_outlined_ring_with_one_head(clockwise):
    """96 px square; colours 0 (transparent), OUTLINE, BODY, SHADE only; the drawn part (body and shade) is one piece, enclosed by
    the outline (no drawn pixel touches a transparent one); most of it is a ring about the centre (radius RING_RADIUS ±
    RING_WIDTH / 2 + 1) that leaves a gap; outside that ring the drawn pixels are one piece, the head; and the head lies just past
    the ring's end in the arrow's sense: anticlockwise as seen for arrow(False), clockwise for arrow(True)."""
    img = g.arrow_bitmap(clockwise)
    assert img.shape == (g.ARROW_PX, g.ARROW_PX) == (96, 96)
    assert set(np.unique(img)) == {0, g.OUTLINE, g.BODY, g.SHADE}
    drawn = (img == g.BODY) | (img == g.SHADE)
    assert len(_components(drawn)) == 1
    p = np.pad(img == 0, 1)
    near_clear = np.zeros_like(drawn)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            near_clear |= p[1 + dy:1 + dy + 96, 1 + dx:1 + dx + 96]
    assert not (drawn & near_clear).any()                                  # the outline encloses it
    c = (g.ARROW_PX - 1) / 2
    y, x = np.mgrid[0:96, 0:96]
    r = np.hypot(x - c, y - c)
    ring = drawn & (np.abs(r - g.RING_RADIUS) <= g.RING_WIDTH / 2 + 1)
    assert ring.sum() > 0.7 * drawn.sum()
    angles = sorted({int(_visual_angle(v, u)) for v, u in zip(*np.nonzero(ring))})
    gaps = [(b - a, a, b) for a, b in zip(angles, angles[1:] + [angles[0] + 360])]
    gap, start, end = max(gaps)                                            # the ring runs from `end` round to `start`
    assert 30 <= gap <= 120 and 360 - gap >= 240, gaps[-3:]
    head = drawn & ~ring                                                   # what overhangs the ring: the head, both sides of it
    assert head.sum() > 0.04 * drawn.sum() and (head & (r < g.RING_RADIUS)).any() and (head & (r > g.RING_RADIUS)).any()
    # all of it at the ring's leading end, the gap's edge the arrow travels into (anticlockwise: the ring's last angle `start`,
    # clockwise: its first, `end`), none at its tail (the other edge)
    lead, tail = (start, end) if not clockwise else (end, start)
    wrap = lambda d: (d + 180) % 360 - 180
    angles = [_visual_angle(v, u) for v, u in zip(*np.nonzero(head))]
    sense = 1 if not clockwise else -1
    assert all(-45 < sense * wrap(a - lead) < gap / 2 for a in angles), (clockwise, lead, sorted(angles)[:3], sorted(angles)[-3:])
    assert all(abs(wrap(a - tail)) > 45 for a in angles), (clockwise, tail)


def test_the_clockwise_arrow_is_the_anticlockwise_one_mirrored():
    """arrow(True) is arrow(False) mirrored left to right, pixel for pixel, as decoded from its map and characters."""
    (mc, cc), (ma, ca) = g.arrow(True), g.arrow(False)
    assert np.array_equal(g.decode(mc, cc), g.decode(ma, ca)[:, ::-1])
    assert np.array_equal(g.decode(ma, ca), g.arrow_bitmap(False)) and np.array_equal(g.decode(mc, cc), g.arrow_bitmap(True))


@pytest.mark.parametrize("clockwise", [False, True])
def test_an_arrow_fits_one_block(clockwise):
    """A 12 x 12 map of local character numbers, EMPTY (0xffff) exactly where the tile is all transparent; at most 128 characters
    of 32 bytes, all different and none all transparent; colours 0-15 of one palette (four used)."""
    m, chars = g.arrow(clockwise)
    img = g.arrow_bitmap(clockwise)
    assert m.shape == (12, 12) and 0 < len(chars) <= 128 and all(len(c) == 32 for c in chars)
    assert len(set(chars)) == len(chars) and bytes(32) not in chars
    for (r, c), k in np.ndenumerate(m):
        empty = not img[8 * r:8 * r + 8, 8 * c:8 * c + 8].any()
        assert (k == g.EMPTY) == empty, (r, c, k)
        assert k == g.EMPTY or k < len(chars)
    assert set(m.flat) - {g.EMPTY} == set(range(len(chars)))
    assert max(max(b >> 4, b & 15) for ch in chars for b in ch) <= g.SHADE


def test_the_palette_sets():
    """WHITE and RED: 16 colour words each; the outline dark in both (every channel at most 4 of 31); the body white (every channel
    at least 30) in WHITE and red (red channel at least 28, green and blue at most 10) in RED; the shade between."""
    def rgb(w):
        return (w & 31, w >> 5 & 31, w >> 10 & 31)
    for pal in (g.WHITE, g.RED):
        assert len(pal) == 16 and max(rgb(pal[g.OUTLINE])) <= 4
    assert min(rgb(g.WHITE[g.BODY])) >= 30 and 20 <= min(rgb(g.WHITE[g.SHADE])) < 30
    r, gg, b = rgb(g.RED[g.BODY])
    assert r >= 28 and gg <= 10 and b <= 10 and rgb(g.RED[g.SHADE])[0] < r


def test_the_caption_strip():
    """The caption's map is CAPTION_SIZE (2 x 18 tiles), no cell empty, at most 128 characters (all different); it decodes to
    caption_bitmap: paper (CAPTION_PAPER) and ink (CAPTION_INK) only, the ink 15 rows high from strip row 1 (the panel lettering's
    rows), at least 2 px clear of either end."""
    m, chars = g.caption()
    assert m.shape == g.CAPTION_SIZE == (2, 18) and g.EMPTY not in m and len(chars) <= 128 and len(set(chars)) == len(chars)
    img = g.decode(m, chars)
    assert np.array_equal(img, g.caption_bitmap())
    assert set(np.unique(img)) == {g.CAPTION_PAPER, g.CAPTION_INK}
    ys, xs = np.nonzero(img == g.CAPTION_INK)
    assert (ys.min(), ys.max()) == (g.LETTER_TOP, g.LETTER_TOP + 14) == (1, 15)
    assert xs.min() >= 2 and xs.max() <= img.shape[1] - 3
    assert set(g.CAPTION.replace(" ", "")) <= set(g.GLYPHS) and all(len(v) == g.LETTER_HEIGHT for v in g.GLYPHS.values())


def _panel_pixels(rs, window):
    """The colour indices and per-cell characters of a select-screen map (panel.decode_panel), from the ROM's select uploads."""
    from vrtools.arcade.panel import char_pixels, char_source, decode_panel
    p = decode_panel(rs, window)
    img = np.zeros((8 * p.rows, 8 * p.cols), np.uint8)
    chars = np.zeros((p.rows, p.cols), int)
    for r in range(p.rows):
        for c in range(p.cols):
            ch = (p.base + p.tiles[r * p.cols + c]) & 0x3FFF
            chars[r, c] = ch
            img[8 * r:8 * r + 8, 8 * c:8 * c + 8] = char_pixels(char_source(rs, ch))
    return img, chars


def test_the_caption_fits_the_wheel_panels_caption_area(romset_zip):
    """The game's SELECT COURSE wheel panel (dirscreen.WHEEL_PANEL), decoded from the ROM: its lettering above the wheel (colour
    CAPTION_INK in the panel's top three cell rows) lies wholly in the CAPTION_SIZE cells from CAPTION_PANEL_CELL, which hold
    only paper and ink (colours CAPTION_PAPER and CAPTION_INK) of palettes whose paper and ink are PANEL_PALETTE's (0x72 and
    0x73 there), ink the palette's darkest colour; so the caption replaces those cells whole and nothing of SELECT COURSE stays. The game's
    lettering is 15 rows high from the strip's row 1, as the caption's; the caption fits the strip, its letters 8 px wide where
    the game's are 9 (CAPTION's 16 letters at 9 px and the game's spacing would need more than the strip's 144)."""
    from vrtools.arcade.dirscreen import CAPTION_CELL, MAPS, WHEEL_PANEL
    from vrtools.arcade.panel import select_palette
    from vrtools.arcade.romset import RomSet
    rs = RomSet.from_zip(romset_zip)
    img, chars = _panel_pixels(rs, WHEEL_PANEL)
    (r0, c0), (h, w) = g.CAPTION_PANEL_CELL, g.CAPTION_SIZE
    cell = next(cell for m, cell, _ in MAPS if m == WHEEL_PANEL)
    assert CAPTION_CELL == (cell[0] + r0, cell[1] + c0)
    ink = np.zeros_like(img, bool)
    ink[:24] = img[:24] == g.CAPTION_INK
    ys, xs = np.nonzero(ink)
    assert len(ys) > 200                                                      # SELECT COURSE
    assert 8 * r0 <= ys.min() and ys.max() < 8 * (r0 + h) and 8 * c0 <= xs.min() and xs.max() < 8 * (c0 + w), (ys.min(), ys.max(), xs.min(), xs.max())
    area = img[8 * r0:8 * (r0 + h), 8 * c0:8 * (c0 + w)]
    assert set(np.unique(area)) == {g.CAPTION_PAPER, g.CAPTION_INK}
    sp = select_palette(rs)
    colours = lambda p: sp["words"][(p << 4) - (sp["dst"] - 0x900000) // 2:][:16]
    words = colours(g.PANEL_PALETTE)
    used = {ch >> 7 for ch in chars[r0:r0 + h, c0:c0 + w].flat}
    assert g.PANEL_PALETTE in used and all(colours(p)[k] == words[k] for p in used for k in (g.CAPTION_PAPER, g.CAPTION_INK))
    lum = lambda wd: (wd & 31) + (wd >> 5 & 31) + (wd >> 10 & 31)
    assert lum(words[g.CAPTION_INK]) == min(lum(wd) for wd in words[1:]) and lum(words[g.CAPTION_PAPER]) > lum(words[g.CAPTION_INK])
    assert (ys.min() - 8 * r0, ys.max() - 8 * r0) == (g.LETTER_TOP, g.LETTER_TOP + g.LETTER_HEIGHT - 1)
    letters = [len(c) for c in _components(ink)]
    assert len(letters) == len("SELECTCOURSE")
    widths = sorted({max(x for _, x in comp) - min(x for _, x in comp) + 1 for comp in _components(ink)})
    assert widths[-1] == 9 and max(len(v[0]) for v in g.GLYPHS.values()) == 8
    mine = np.nonzero(g.caption_bitmap() == g.CAPTION_INK)[1]
    assert mine.min() >= 2 and mine.max() <= 8 * w - 3
    need = 9 * sum(1 for ch in g.CAPTION if ch != " ") - 2 * 6 + (len(g.CAPTION) - 2) + g.WORD_GAP     # I 3 wide, 1-px gaps
    assert need > 8 * w - 4


def test_the_block_holds_the_graphics_and_the_draw_list():
    """block_image: block_size() bytes (at most BLOCK_LIMIT) from block_start(), 16-aligned, ending at BLOCK_END (0x2c0000), the
    padding after its last part 0 bytes; its parts do not
    overlap and hold the arrows' and caption's characters, the WHITE and RED sets and the three maps as 0xff9436 blits them (mode
    1, base 0x8000 | the block's first character: tile words 0x8000 | block + local, BLANK_TILE for an empty cell); the rows of
    each drawing phase (dirscreen.DRAW_PHASES) at "rows" + PHASE_BYTES * (DIR_SHOWN - DRAW_PHASES[-1]) are, in order: phase
    0xff the game's four maps on layer 0 (dirscreen.MAPS), the caption's characters to block 0x3580, the panel's palette (palette
    RAM of PANEL_PALETTE) to 0x3580's, the caption's map at CAPTION_CELL; 0xfe and 0xfd none; 0xfc the clockwise arrow's
    characters to block 0x3480; 0xfb the anticlockwise one's to 0x3500; 0xfa the WHITE set to 0x3480's palette and RED to
    0x3500's, the clockwise map at ARROW_CELLS[0] and the anticlockwise at ARROW_CELLS[1], each with the swap that exchanges the
    pair (an anticlockwise entry). No run of 16 0xff bytes in it (the free-run searches never take it for erased room)."""
    from vrtools.arcade.dirscreen import ARROW_CELLS, CAPTION_CELL, DRAW_PHASES, MAPS, tile_address
    from vrtools.arcade.panel import PanelMap, encode_panel
    base = g.block_start()
    image, at = g.block_image(base)
    assert base % 16 == 0 and base + len(image) <= g.BLOCK_END == 0x2C0000 and len(image) <= g.BLOCK_LIMIT == 8192
    assert len(image) == g.block_size() and base + len(image) == g.BLOCK_END and 0 <= base + len(image) - at["end"] < 16
    assert image[at["end"] - base:] == bytes(base + len(image) - at["end"])
    get = lambda k, n: image[at[k] - base:at[k] - base + n]
    (mc, cc), (ma, ca), (mt, ct) = g.arrow(True), g.arrow(False), g.caption()
    for k, chars in (("cw_chars", cc), ("ccw_chars", ca), ("caption_chars", ct)):
        assert get(k, 32 * len(chars)) == b"".join(chars), k
    assert get("white", 32) == struct.pack("<16H", *g.WHITE) and get("red", 32) == struct.pack("<16H", *g.RED)
    for k, m, block in (("cw_map", mc, g.BLOCKS[0]), ("ccw_map", ma, g.BLOCKS[1]), ("caption_map", mt, g.BLOCKS[2])):
        base_word = 0x8000 | block
        words = [0x8020 if v == g.EMPTY else base_word + int(v) for v in m.flat]
        blob = encode_panel(PanelMap(base_word, 1, *m.shape, [(wd - base_word) & 0xFFFF for wd in words]))
        assert get(k, len(blob)) == blob, k
    spans = sorted((at[k], at[k] + n) for k, n in (("cw_chars", 32 * len(cc)), ("ccw_chars", 32 * len(ca)), ("caption_chars", 32 * len(ct)),
                                                 ("white", 32), ("red", 32), ("cw_map", 300), ("ccw_map", 300), ("caption_map", 84)))
    spans.insert(0, (at["rows"], at["rows"] + g.PHASE_BYTES * len(DRAW_PHASES)))
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    assert g.BLOCKS == (0x3480, 0x3500, 0x3580) and g.PANEL_PALETTE == 0x73

    def rows(s):
        o, out = at["rows"] - base + g.PHASE_BYTES * (s - DRAW_PHASES[-1]), []
        while True:
            row = struct.unpack_from("<IIIi", image, o)
            if row[0] == 0:
                return out
            out.append(row)
            o += g.ROW_BYTES
    char = lambda b: 0x780000 + 32 * b
    pal = lambda b: 0x900000 + 32 * (b >> 7)
    t0, t1 = tile_address(0, *ARROW_CELLS[0]), tile_address(0, *ARROW_CELLS[1])
    assert DRAW_PHASES == (0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA)
    assert rows(0xFF) == [(m, tile_address(0, *cell), 0, 0) for m, cell, _ in MAPS] + [
        (at["caption_chars"], char(0x3580), 8 * len(ct), 0), (0x900000 + 32 * g.PANEL_PALETTE, pal(0x3580), 8, 0), (at["caption_map"], tile_address(0, *CAPTION_CELL), 0, 0)]
    assert rows(0xFE) == rows(0xFD) == []
    assert rows(0xFC) == [(at["cw_chars"], char(0x3480), 8 * len(cc), 0)]
    assert rows(0xFB) == [(at["ccw_chars"], char(0x3500), 8 * len(ca), 0)]
    assert rows(0xFA) == [(at["white"], pal(0x3480), 8, pal(0x3500) - pal(0x3480)), (at["red"], pal(0x3500), 8, pal(0x3480) - pal(0x3500)),
                          (at["cw_map"], t0, 0, t1 - t0), (at["ccw_map"], t1, 0, t0 - t1)]
    assert b"\xff" * 16 not in image
    assert g.block_image(base + 0x100)[1]["rows"] == base + 0x100                   # the addresses follow the base
