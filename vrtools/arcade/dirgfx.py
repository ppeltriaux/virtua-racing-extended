"""Phase 26 stage 3 (plan Task 5, D5, D8, D11): the COURSE DIRECTION screen's only new graphics, drawn by this module's own code
at build time (nothing is cut from the game's graphics): two ring arrows of 96 px (12 x 12 tiles) that show which way round each
choice laps, laid on layer 0 over the two pictures (dirscreen.ARROW_CELLS), and the SELECT DIRECTION caption, laid over the
SELECT COURSE lettering cells of the game's wheel panel (map 0x1e0f71, dirscreen.WHEEL_PANEL). They live in one data block of at
most BLOCK_LIMIT bytes ending at BLOCK_END (plan D11, the top of the colour-table run; `tencourse.dirscreen_block`), with their
maps, the arrows' two palette sets and the screen's draw list ("rows", below); `dirscreen`'s `dirdraw` copies them into the middle
slot's character blocks (the middle slot is not shown on the direction screen; recon §3.2): the clockwise arrow into BLOCKS[0]
(characters 0x3480.., palette 0x69), the anticlockwise one into BLOCKS[1] (0x3500.., 0x6a), the caption into BLOCKS[2] (0x3580..,
0x6b). A tile word's palette is its character >> 7 (panel.py), so each block has its own palette.

- An arrow: a ring of RING_RADIUS through about 290 degrees, RING_WIDTH wide, ending in one head; a dark outline (colour 1) round
  it, the body colour 2 with a shade (colour 3) along its inner rim; colour 0 (transparent) elsewhere, so the picture shows
  through the ring. `arrow(False)` (anticlockwise as seen) is drawn; `arrow(True)` is its mirror image left to right, pixel for
  pixel (the hardware has no tile flips: the two are two character sets). The set on the NORMAL side's block is WHITE, the other's
  RED (plan D8), written by `dirdraw`.
- The caption: a CAPTION_SIZE strip (rows 1-2, columns 1-18 of the 13 x 20 panel, the cells of its SELECT COURSE lettering),
  paper everywhere and SELECT DIRECTION in ink, 15 px capitals of 3-px strokes in the panel lettering's style, 8 px wide where
  the panel's are 9 (16 letters do not fit the strip at the panel's width), centred. Paper and ink are colours CAPTION_PAPER and
  CAPTION_INK of the panel's own palette PANEL_PALETTE: `dirdraw` copies that palette (palette RAM, as the select screen
  uploaded it) to BLOCKS[2]'s, so the caption has the panel's colours without this module holding them.
- The draw list ("rows"): per drawing phase of `dirdraw` (dirscreen.DRAW_PHASES) up to ROWS_PER_PHASE - 1 rows of four words
  (source, destination, count, swap), then a row with source 0, which ends them: count > 0 copies `count` longwords from source
  to destination, count 0 blits the map at source to the tile address destination (0xff9436); when the chosen entry's lap is
  anticlockwise (dirscreen.SENSE_FIELD: its NORMAL side shows the anticlockwise arrow) the destination moves by `swap` first, which
  exchanges the two arrows' places and the two palette sets. The phase of DIR_SHOWN s has its rows at "rows" + PHASE_BYTES *
  (s - DRAW_PHASES[-1]).
"""
from __future__ import annotations

import struct
from functools import lru_cache

import numpy as np

BLOCK_END = 0x2C0000                   # the colour-table run's end (tencourse.COLOUR_RUN_TAIL)
BLOCK_LIMIT = 8192                     # plan D11
CHAR_RAM, CHAR_BYTES, BLOCK_CHARS = 0x780000, 32, 128
PALETTE_RAM = 0x900000
BLOCKS = (0x3480, 0x3500, 0x3580)      # the middle slot's three blocks (select.SLOT_CHAR[1]): clockwise arrow, anticlockwise, caption
EMPTY = 0xFFFF                         # an empty cell of `arrow`'s map
BLANK_TILE = 0x8020                    # what the blit writes for it (the boot font's space, as the cleared layer 0)
ARROW_PX = 96
ARROW_CELLS = ARROW_PX // 8            # 12 x 12 tiles
RING_RADIUS, RING_WIDTH = 33.0, 9.0    # the ring's centre line and body width (px); the outline adds a pixel each side
ARC = (25.0, 290.0)                    # degrees, anticlockwise from three o'clock: the body's start and the head's base
HEAD_WIDTH, HEAD_LENGTH = 27.0, 19.0   # the head: a triangle across the ring at ARC[1], its tip HEAD_LENGTH on along the tangent
OUTLINE, BODY, SHADE = 1, 2, 3         # arrow colours
# the palette sets (16 colour words: bit 15 set as the game's, 5-bit blue / green / red); colour 0 is never drawn
WHITE = (0, 0x8C63, 0xFFFF, 0xDEF7) + (0,) * 12
RED = (0, 0x8424, 0xA11F, 0x9093) + (0,) * 12
# the caption (recon §2.4: the panel's characters 0x3900..; its lettering's cells are 0x398a.., palette 0x73, colour 1 on 8)
PANEL_PALETTE = 0x73
CAPTION_PAPER, CAPTION_INK = 8, 1
CAPTION_SIZE = (2, 18)                 # rows, columns of tiles
CAPTION_PANEL_CELL = (1, 1)            # the strip's first cell inside the wheel panel's map
CAPTION = "SELECT DIRECTION"
LETTER_TOP, LETTER_HEIGHT, LETTER_GAP, WORD_GAP = 1, 15, 1, 7      # px, inside the strip
ROWS_PER_PHASE = 8
ROW_BYTES = 16
PHASE_BYTES = ROWS_PER_PHASE * ROW_BYTES

GLYPHS: dict[str, tuple[str, ...]] = {
    "S": (".######.", "########", "########", "###..###", "###.....", "###.....", "#######.", "########", ".#######", ".....###",
          ".....###", "###..###", "########", "########", ".######."),
    "E": ("########",) * 3 + ("###.....",) * 3 + ("#######.",) * 3 + ("###.....",) * 3 + ("########",) * 3,
    "L": ("###.....",) * 12 + ("########",) * 3,
    "C": (".######.", "########", "########", "###..###") + ("###.....",) * 7 + ("###..###", "########", "########", ".######."),
    "T": ("#######",) * 3 + ("..###..",) * 12,
    "D": ("#######.", "########", "########") + ("###..###",) * 9 + ("########", "########", "#######."),
    "I": ("###",) * 15,
    "R": ("#######.", "########", "########", "###..###", "###..###", "###..###", "########", "########", "#######.")
         + ("###..###",) * 6,
    "O": (".######.", "########", "########") + ("###..###",) * 9 + ("########", "########", ".######."),
    "N": ("###..###", "###..###") + ("####.###",) * 5 + ("########",) + ("###.####",) * 5 + ("###..###", "###..###"),
}


def _tiles(img: np.ndarray, empty_shared: bool) -> tuple[np.ndarray, list[bytes]]:
    """(map, characters) of a bitmap of colour indices, 8 x 8 tiles row by row: identical tiles share a character (numbered in
    order of first use); with `empty_shared` False an all-0 tile is an EMPTY cell and gets no character."""
    rows, cols = img.shape[0] // 8, img.shape[1] // 8
    m = np.full((rows, cols), EMPTY, np.uint16)
    chars: list[bytes] = []
    seen: dict[bytes, int] = {}
    for r in range(rows):
        for c in range(cols):
            t = img[8 * r:8 * r + 8, 8 * c:8 * c + 8]
            if not empty_shared and not t.any():
                continue
            b = char_bytes(t)
            if b not in seen:
                seen[b] = len(chars)
                chars.append(b)
            m[r, c] = seen[b]
    return m, chars


def char_bytes(t: np.ndarray) -> bytes:
    """An 8 x 8 tile of colour indices as the hardware's 32 bytes (panel.char_bytes: high nibble first, byte-swapped halfwords)."""
    out = bytearray(CHAR_BYTES)
    for y in range(8):
        for x in range(8):
            out[y * 4 + ((x // 2) ^ 1)] |= (int(t[y, x]) & 15) << (4 if x % 2 == 0 else 0)
    return bytes(out)


def char_pixels(b: bytes) -> np.ndarray:
    """The inverse of char_bytes."""
    t = np.zeros((8, 8), np.uint8)
    for y in range(8):
        for x in range(8):
            v = b[y * 4 + ((x // 2) ^ 1)]
            t[y, x] = v >> 4 if x % 2 == 0 else v & 15
    return t


def decode(m: np.ndarray, chars: list[bytes]) -> np.ndarray:
    """The bitmap a (map, characters) pair draws (EMPTY cells transparent)."""
    out = np.zeros((8 * m.shape[0], 8 * m.shape[1]), np.uint8)
    for (r, c), k in np.ndenumerate(m):
        if k != EMPTY:
            out[8 * r:8 * r + 8, 8 * c:8 * c + 8] = char_pixels(chars[k])
    return out


def arrow_bitmap(clockwise: bool) -> np.ndarray:
    """The ARROW_PX square arrow in colour indices (see the module's docstring); clockwise = the anticlockwise one mirrored."""
    if clockwise:
        return arrow_bitmap(False)[:, ::-1].copy()
    c = (ARROW_PX - 1) / 2
    y, x = np.mgrid[0:ARROW_PX, 0:ARROW_PX].astype(float)
    dx, dy = x - c, c - y                                       # y up
    r = np.hypot(dx, dy)
    phi = np.degrees(np.arctan2(dy, dx)) % 360
    body = (np.abs(r - RING_RADIUS) <= RING_WIDTH / 2) & (phi >= ARC[0]) & (phi <= ARC[1])
    a = np.radians(ARC[1])
    base = np.array([c + RING_RADIUS * np.cos(a), c - RING_RADIUS * np.sin(a)])      # screen (x, y)
    t = np.array([-np.sin(a), -np.cos(a)])                      # the tangent, anticlockwise as seen
    n = np.array([np.cos(a), -np.sin(a)])                       # outwards
    pts = [base + n * HEAD_WIDTH / 2, base + t * HEAD_LENGTH, base - n * HEAD_WIDTH / 2]
    head = _inside(x, y, pts)
    shape = body | head
    out = np.zeros(shape.shape, np.uint8)
    p = np.pad(shape, 1)
    ring = np.zeros_like(shape)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            ring |= p[1 + oy:1 + oy + ARROW_PX, 1 + ox:1 + ox + ARROW_PX]
    out[ring & ~shape] = OUTLINE
    out[shape] = BODY
    out[body & ~head & (r < RING_RADIUS - RING_WIDTH / 2 + 2)] = SHADE
    return out


def _inside(x: np.ndarray, y: np.ndarray, pts) -> np.ndarray:
    """Pixels whose centres lie in the triangle `pts` (screen coordinates)."""
    def side(p, q):
        return (q[0] - p[0]) * (y - p[1]) - (q[1] - p[1]) * (x - p[0])
    s = [side(pts[k], pts[(k + 1) % 3]) for k in range(3)]
    return ((s[0] >= 0) & (s[1] >= 0) & (s[2] >= 0)) | ((s[0] <= 0) & (s[1] <= 0) & (s[2] <= 0))


def arrow(clockwise: bool) -> tuple[np.ndarray, list[bytes]]:
    """The arrow's ARROW_CELLS x ARROW_CELLS map of local character numbers (EMPTY: no character) and its characters."""
    m, chars = _tiles(arrow_bitmap(clockwise), empty_shared=False)
    assert len(chars) <= BLOCK_CHARS
    return m, chars


def caption_bitmap() -> np.ndarray:
    """The CAPTION_SIZE strip in the panel palette's colour indices: paper, CAPTION in ink, centred."""
    h, w = 8 * CAPTION_SIZE[0], 8 * CAPTION_SIZE[1]
    img = np.full((h, w), CAPTION_PAPER, np.uint8)
    words = CAPTION.split(" ")
    glyphs = [[np.array([[ch == "#" for ch in row] for row in GLYPHS[ch]]) for ch in word] for word in words]
    width = sum(g.shape[1] for word in glyphs for g in word) + LETTER_GAP * sum(len(w) - 1 for w in glyphs) + WORD_GAP * (len(words) - 1)
    x = (w - width) // 2
    for k, word in enumerate(glyphs):
        for j, g in enumerate(word):
            assert g.shape[0] == LETTER_HEIGHT
            img[LETTER_TOP:LETTER_TOP + LETTER_HEIGHT, x:x + g.shape[1]][g] = CAPTION_INK
            x += g.shape[1] + (LETTER_GAP if j < len(word) - 1 else 0)
        x += WORD_GAP
    return img


def caption() -> tuple[np.ndarray, list[bytes]]:
    """The caption strip's map (CAPTION_SIZE, local character numbers; no cell is empty) and its characters."""
    m, chars = _tiles(caption_bitmap(), empty_shared=True)
    assert len(chars) <= BLOCK_CHARS
    return m, chars


def map_blob(m: np.ndarray, block: int) -> bytes:
    """`m` as a map 0xff9436 blits (panel.encode_panel's format, mode 1): tile words 0x8000 | block + local, an EMPTY cell
    BLANK_TILE (the blitter adds the base in 16 bits)."""
    base = 0x8000 | block
    words = [BLANK_TILE if k == EMPTY else base + int(k) for k in m.flat]
    return struct.pack("<HHII", base, 1, *m.shape) + struct.pack(f"<{m.size}H", *((v - base) & 0xFFFF for v in words))


def char_address(block: int) -> int:
    return CHAR_RAM + CHAR_BYTES * block


def palette_address(block: int) -> int:
    """The palette RAM address of a character block's 16 colours (palette = character >> 7)."""
    return PALETTE_RAM + 32 * (block >> 7)


@lru_cache(maxsize=1)
def _parts() -> dict[str, bytes]:
    """The block's graphics in their order: characters, palette sets, maps."""
    (mc, cc), (ma, ca), (mt, ct) = arrow(True), arrow(False), caption()
    return {"cw_chars": b"".join(cc), "ccw_chars": b"".join(ca), "caption_chars": b"".join(ct),
            "white": struct.pack("<16H", *WHITE), "red": struct.pack("<16H", *RED),
            "cw_map": map_blob(mc, BLOCKS[0]), "ccw_map": map_blob(ma, BLOCKS[1]), "caption_map": map_blob(mt, BLOCKS[2])}


def _phase_rows(at: dict[str, int], sizes: dict[str, int]) -> dict[int, list[tuple[int, int, int, int]]]:
    """Per drawing phase (DIR_SHOWN) its rows (source, destination, count, swap)."""
    from vrtools.arcade.dirscreen import ARROW_CELLS as CELLS, CAPTION_CELL, DRAW_PHASES, MAPS, tile_address
    copy = lambda src, dst, n_bytes, swap=0: (src, dst, n_bytes // 4, swap)
    blit = lambda src, dst, swap=0: (src, dst, 0, swap)
    t0, t1 = tile_address(0, *CELLS[0]), tile_address(0, *CELLS[1])
    p0, p1 = palette_address(BLOCKS[0]), palette_address(BLOCKS[1])
    rows = {s: [] for s in DRAW_PHASES}
    rows[DRAW_PHASES[0]] = ([blit(m, tile_address(0, *cell)) for m, cell, _ in MAPS]                  # the game's maps, the wheel panel
                            + [copy(at["caption_chars"], char_address(BLOCKS[2]), sizes["caption_chars"]),   # among them, then the caption
                               copy(palette_address(PANEL_PALETTE << 7), palette_address(BLOCKS[2]), 32),     # over its lettering
                               blit(at["caption_map"], tile_address(0, *CAPTION_CELL))])
    rows[DRAW_PHASES[3]] = [copy(at["cw_chars"], char_address(BLOCKS[0]), sizes["cw_chars"])]
    rows[DRAW_PHASES[4]] = [copy(at["ccw_chars"], char_address(BLOCKS[1]), sizes["ccw_chars"])]
    rows[DRAW_PHASES[5]] = [copy(at["white"], p0, 32, p1 - p0), copy(at["red"], p1, 32, p0 - p1),
                            blit(at["cw_map"], t0, t1 - t0), blit(at["ccw_map"], t1, t0 - t1)]
    assert all(len(r) < ROWS_PER_PHASE for r in rows.values())
    return rows


@lru_cache(maxsize=1)
def block_size() -> int:
    """The data block's size, a multiple of 16 (independent of where it lies)."""
    from vrtools.arcade.dirscreen import DRAW_PHASES
    return (PHASE_BYTES * len(DRAW_PHASES) + sum((len(b) + 3) // 4 * 4 for b in _parts().values()) + 15) // 16 * 16


def block_start() -> int:
    """Where the block starts: BLOCK_END less its size (16-aligned, as BLOCK_END)."""
    return BLOCK_END - block_size()


def block_image(base: int) -> tuple[bytes, dict[str, int]]:
    """The data block at `base` and the addresses of its parts ("rows", "cw_chars", "ccw_chars", "caption_chars", "white", "red",
    "cw_map", "ccw_map", "caption_map"; and "end", where the last part ends). Gaps and the padding to block_size() are 0 bytes,
    not 0xff (no erased run inside it)."""
    from vrtools.arcade.dirscreen import DRAW_PHASES
    parts = _parts()
    at = {"rows": base}
    pos = base + PHASE_BYTES * len(DRAW_PHASES)
    for k, b in parts.items():
        at[k] = pos
        pos += (len(b) + 3) // 4 * 4
    at["end"] = pos
    image = bytearray(block_size())
    rows = _phase_rows(at, {k: len(b) for k, b in parts.items()})
    for s, rs in rows.items():
        o = PHASE_BYTES * (s - DRAW_PHASES[-1])
        for k, row in enumerate(rs):
            struct.pack_into("<IIIi", image, o + ROW_BYTES * k, *row)
    for k, b in parts.items():
        image[at[k] - base:at[k] - base + len(b)] = b
    assert len(image) == block_size() <= BLOCK_LIMIT, len(image)
    return bytes(image), at
