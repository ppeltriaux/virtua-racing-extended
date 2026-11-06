"""Select-screen panels: the originals' tile maps and characters, and generated panels for converted courses.

A panel is two 16 × 21-tile maps (128 × 168 px, portrait) blitted by 0xff9436: the picture layer ("B", tile RAM
0x700088 + 0x26·slot, mode 1 = halfword tile words 0x8000 | char) and an overlay ("A", 0x704088 + 0x26·slot,
mode 0 = byte indices on a character page; colour 0 transparent) carrying the track outline and the name. Map
header: base:u16, mode:u16, rows:u32, cols:u32 (the blitter's outer loop is rows), then the indices. Characters
are 8 × 8 × 4 bpp, 32 bytes, pixel pairs in byte-swapped halfwords (high nibble first); a tile word's palette is
bits 7–14, i.e. the character index >> 7, so a 128-character block shares one 16-colour palette.

Generated panels keep the host's picture layer with its interior filled by one of the host's own flat terrain
characters, and draw the outline, a start mark and the name as an overlay in free characters (the unused tail of
each original overlay page plus characters 0x3e80–0x3fff, whose palettes 0x7d–0x7f are free on the select screen).
docs/formats/model1-course-tables.md §13.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from vrtools.arcade.font import HEIGHT, draw_text, text_width
from vrtools.arcade.patch import PatchError, write_data
from vrtools.arcade.romset import RomSet

ROWS, COLS = 21, 16
CHAR_BYTES = 32
TILE_WORDS_BASE_B = 0x8000
BANK0_DIR_PHASE1 = 0x4A324                 # bank 0: first word of the phase-1 entry = pointer to the select screen's pair list
BANK0_FREE = (0xF2F83 + 0x7D & ~0xF, 0x100000 - (0xF2F83 + 0x7D & ~0xF))   # 16-aligned start of bank 0's free tail
PALETTE_RAM = 0x900000
FREE_PALETTES = (0x7D, 0x7E, 0x7F)         # unused on the select screen; characters 0x3e80..0x3fff map to them
ORIGINAL_PANELS = {0: (0x1E0000, 0x1E0414), 1: (0x1E015C, 0x1E06C0), 2: (0x1E02B8, 0x1E096C)}   # art index -> (A, B) window addresses


@dataclass
class PanelMap:
    base: int
    mode: int
    rows: int
    cols: int
    tiles: list[int]                       # raw indices (byte or halfword values, without the base)

    def words(self) -> list[int]:
        return [(self.base + t) & 0xFFFF for t in self.tiles]      # the blitter adds the base in 16 bits


def decode_panel(rs: RomSet, window_addr: int) -> PanelMap:
    off = window_addr - 0x100000
    base, mode, rows, cols = struct.unpack_from("<HHII", rs.data, off)
    n = rows * cols
    if mode == 0:
        tiles = list(rs.data[off + 12:off + 12 + n])
    else:
        tiles = list(struct.unpack_from(f"<{n}H", rs.data, off + 12))
    return PanelMap(base, mode, rows, cols, tiles)


def encode_panel(p: PanelMap) -> bytes:
    if len(p.tiles) != p.rows * p.cols:
        raise PatchError("panel map size mismatch")
    head = struct.pack("<HHII", p.base, p.mode, p.rows, p.cols)
    if p.mode == 0:
        if any(not 0 <= t < 256 for t in p.tiles):
            raise PatchError("mode-0 panel indices must fit a byte")
        return head + bytes(p.tiles)
    return head + struct.pack(f"<{len(p.tiles)}H", *p.tiles)


def select_uploads(rs: RomSet) -> list[tuple[int, int, int]]:
    """(src window address, dst char-RAM/palette address, count in 32-byte units) of the select screen's upload
    list (bank 0 directory, phase 1)."""
    ptr = struct.unpack_from("<I", rs.data, BANK0_DIR_PHASE1)[0]
    off = ptr - 0x100000
    out = []
    while True:
        src, dst = struct.unpack_from("<2I", rs.data, off)
        if src == 0:
            return out
        out.append((src, dst, struct.unpack_from("<I", rs.data, src - 0x100000)[0]))
        off += 8


def char_source(rs: RomSet, index: int) -> bytes:
    """The 32 bytes of character `index` as the select-screen uploads put them in character RAM."""
    addr = 0x780000 + index * CHAR_BYTES
    found = None
    for src, dst, count in select_uploads(rs):                     # later uploads overwrite earlier ones
        if dst <= addr < dst + count * CHAR_BYTES:
            o = src - 0x100000 + 4 + (addr - dst)
            found = rs.data[o:o + CHAR_BYTES]
    if found is None:
        raise PatchError(f"character {index:#x} is not uploaded for the select screen")
    return found


def char_pixels(data: bytes) -> list[list[int]]:
    out = []
    for y in range(8):
        row = []
        for x in range(8):
            byte = data[y * 4 + ((x // 2) ^ 1)]
            row.append(byte >> 4 if x % 2 == 0 else byte & 15)
        out.append(row)
    return out


def char_bytes(pixels: list[list[int]]) -> bytes:
    out = bytearray(CHAR_BYTES)
    for y in range(8):
        for x in range(8):
            i = y * 4 + ((x // 2) ^ 1)
            v = pixels[y][x] & 15
            out[i] |= v << 4 if x % 2 == 0 else v
    return bytes(out)


def char_bitmap(rs: RomSet, index: int) -> list[list[int]]:
    return char_pixels(char_source(rs, index))


@dataclass
class CharPool:
    """Free character slots grouped by palette block (index >> 7), each with the palette's colour indices for
    the overlay roles (line, accent, text)."""
    slots: dict[int, list[int]]            # palette -> free char indices
    roles: dict[int, tuple[int, int, int]] # palette -> (line colour, accent colour, text colour) indices
    used: dict[int, int] = field(default_factory=dict)      # char index -> 1
    fills: dict[int, int] = field(default_factory=dict)     # flat colour index -> char index (shared by all panels)
    patterns: dict[tuple[int, ...], int] = field(default_factory=dict)   # overlay tile pattern -> char index (shared)


@dataclass
class Rendered:
    a_map: PanelMap                        # overlay (mode 1, any characters)
    b_map: PanelMap                        # picture (host's, interior flattened)
    chars: dict[int, bytes]                # new characters by index
    palettes: dict[int, list[int]]         # palette index -> 16 colour words (only for FREE_PALETTES)


def _fit(points: list[tuple[float, float]], w: int, h: int, margin: int) -> list[tuple[int, int]]:
    xs = [p[0] for p in points]; zs = [p[1] for p in points]
    sx, sz = max(xs) - min(xs) or 1.0, max(zs) - min(zs) or 1.0
    s = min((w - 2 * margin) / sx, (h - 2 * margin) / sz)
    ox = (w - sx * s) / 2 - min(xs) * s
    oz = (h - sz * s) / 2 - min(zs) * s
    return [(int(round(x * s + ox)), int(round(h - 1 - (z * s + oz)))) for x, z in points]       # z up -> screen down


def _line(put, a: tuple[int, int], b: tuple[int, int]) -> None:
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        put(x0, y0)
        if (x0, y0) == (x1, y1):
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy


STYLE_POINTS = 48              # the loop is resampled to this many points before smoothing
STYLE_PASSES = 3               # Chaikin corner-cutting passes (rounds every corner, as the arcade's hand-drawn maps do)
STROKE = 3                     # stroke width in pixels


def stylise(outline: list[tuple[float, float]], points: int = STYLE_POINTS, passes: int = STYLE_PASSES) -> list[tuple[float, float]]:
    """A smoothed, simplified closed loop: resample by arc length to `points`, then cut corners `passes` times.
    The arcade's select pictures are hand-drawn approximations, so the generated ones trade precision for the
    same rounded, legible look (Pascal's choice, Phase 7)."""
    if len(outline) < 3:
        return list(outline)
    closed = list(outline) + [outline[0]]
    seg = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(closed, closed[1:])]
    total = sum(seg) or 1.0
    out, k, acc = [], 0, 0.0
    for i in range(points):
        target = total * i / points
        while k < len(seg) - 1 and acc + seg[k] < target:
            acc += seg[k]; k += 1
        t = (target - acc) / seg[k] if seg[k] else 0.0
        (ax, az), (bx, bz) = closed[k], closed[k + 1]
        out.append((ax + (bx - ax) * t, az + (bz - az) * t))
    for _ in range(passes):
        nxt = []
        for a, b in zip(out, out[1:] + out[:1]):
            nxt.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            nxt.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out = nxt
    return out


def render_overlay(outline: list[tuple[float, float]], name: str) -> list[list[int]]:
    """A 128 × 168 role bitmap: 0 transparent, 1 line, 2 accent (start mark), 3 text; the loop is stylised
    (`stylise`) and drawn STROKE pixels wide; the name sits on the bottom strip the original frames leave white."""
    W, H = COLS * 8, ROWS * 8
    img = [[0] * W for _ in range(H)]

    def put(role):
        def f(x, y):
            if 0 <= x < W and 0 <= y < H:
                img[y][x] = role
        return f
    pts = _fit(stylise(outline), W, 146, 12)
    pts = [(x, y + 2) for x, y in pts]
    r = STROKE // 2
    def brush(x, y):
        for dx in range(-r, STROKE - r):
            for dy in range(-r, STROKE - r):
                put(1)(x + dx, y + dy)
    for a, b in zip(pts, pts[1:] + pts[:1]):
        _line(brush, a, b)
    sx, sy = pts[0]
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            put(2)(sx + dx, sy + dy)
    tw = text_width(name)
    draw_text(put(3), max(2, (W - tw) // 2), H - 10 - HEIGHT + 4, name)
    return img


def rendered_tiles(img: list[list[int]]) -> list[tuple[int, ...]]:
    """The 336 tiles of a role bitmap, row-major, each a 64-tuple of roles."""
    out = []
    for ty in range(ROWS):
        for tx in range(COLS):
            out.append(tuple(img[ty * 8 + y][tx * 8 + x] for y in range(8) for x in range(8)))
    return out


# ---- palettes and free characters -------------------------------------------------------------------------------

def select_palette(rs: RomSet) -> dict:
    """The select screen's palette block (bank 0 directory, phase 1, second word): dst, count (entries), words."""
    ptr = struct.unpack_from("<I", rs.data, BANK0_DIR_PHASE1 + 4)[0]
    off = ptr - 0x100000
    dst, count = struct.unpack_from("<2I", rs.data, off)
    words = list(struct.unpack_from(f"<{count}H", rs.data, off + 8))
    return {"ptr": ptr, "dst": dst, "count": count, "words": words}


def _rgb(v: int) -> tuple[int, int, int]:
    return ((v & 31) * 8, ((v >> 5) & 31) * 8, ((v >> 10) & 31) * 8)


def _roles(colours: list[int]) -> tuple[int, int, int]:
    """(line, accent, text) colour indices of a 16-entry palette: nearest to black, orange, and black again (the
    name sits on the white strip)."""
    def nearest(target):
        return min(range(1, 16), key=lambda i: sum((a - b) ** 2 for a, b in zip(_rgb(colours[i]), target)))
    dark = nearest((0, 0, 0))
    return dark, nearest((255, 64, 0)), dark


GENERATED_PALETTE = [0x0000, 0x8000, 0xFFFF, 0x821F, 0x8000 | (4 << 10) | (18 << 5) | 4, 0x8000 | (24 << 10) | (10 << 5) | 2,
                     0x8000 | (14 << 10) | (22 << 5) | 26, 0xFFFF, 0x8000, 0xFFFF, 0x8000, 0xFFFF, 0x8000, 0xFFFF, 0x8000, 0xFFFF]
# 1 black, 2 white, 3 orange, 4..6 terrain colours (replaced per host by the picture's dominant colour)


def free_chars(rs: RomSet) -> CharPool:
    """Free character slots for generated overlays: in the three overlay pages (0x30..0x32), the indices the
    select screen never uploads; plus 0x3e80..0x3fff, whose palettes (0x7d..0x7f) the screen leaves free."""
    covered = set()
    for src, dst, count in select_uploads(rs):
        if 0x780000 <= dst < 0x800000:
            first = (dst - 0x780000) // CHAR_BYTES
            covered.update(range(first, first + count))
    pal = select_palette(rs)
    slots: dict[int, list[int]] = {}
    roles: dict[int, tuple[int, int, int]] = {}
    for c in list(range(0x3000, 0x3780)) + list(range(0x3E80, 0x4000)):      # overlay pages, picture pages, the free top
        if c in covered:
            continue
        p = c >> 7
        slots.setdefault(p, []).append(c)
    for p in list(slots):
        if p in FREE_PALETTES:
            roles[p] = (1, 3, 1)                                    # GENERATED_PALETTE: black line, orange mark, black text
        else:
            i = (p - 0x60) * 16
            if i + 16 > len(pal["words"]):
                del slots[p]
                continue
            roles[p] = _roles(pal["words"][i:i + 16])
    return CharPool(slots, roles)


# ---- rendering and allocation -----------------------------------------------------------------------------------

FILL_WHITE = 2                 # GENERATED_PALETTE entries: 1 black, 2 white, 3 orange, 4..6 the hosts' terrain colours
FILL_TERRAIN = 4


def _dominant(rs: RomSet, b_map: PanelMap, rows: range) -> int:
    """The most common non-transparent colour word in `rows` (columns 1..14) of the host's picture."""
    from collections import Counter
    pal = select_palette(rs)["words"]
    counts: Counter = Counter()
    for r in rows:
        for c in range(1, b_map.cols - 1):
            ch = (b_map.base + b_map.tiles[r * b_map.cols + c]) & 0x3FFF
            i = ((ch >> 7) - 0x60) * 16
            for row in char_bitmap(rs, ch):
                for v in row:
                    if v:
                        counts[pal[i + v]] += 1
    return counts.most_common(1)[0][0]


def _flat_char(pool: CharPool, colour_index: int, chars: dict[int, bytes]) -> int:
    """A flat character in the generated palette block filled with `colour_index`, shared across panels."""
    if colour_index in pool.fills:
        c = pool.fills[colour_index]
        chars[c] = char_bytes([[colour_index] * 8 for _ in range(8)])
        return c
    for p in FREE_PALETTES:
        if pool.slots.get(p):
            c = pool.slots[p].pop(0)
            chars[c] = char_bytes([[colour_index] * 8 for _ in range(8)])
            pool.used[c] = 1
            pool.fills[colour_index] = c
            return c
    raise PatchError("no free character left in the generated palette block for a flat fill")


def render_panel(rs: RomSet, pool: CharPool, outline: list[tuple[float, float]], name: str, host_art: int) -> Rendered:
    """A generated panel: the host's picture layer with a flat interior, and an overlay with the outline, start
    mark and name drawn into free characters taken from `pool` (shared across calls, so a set of panels fits)."""
    host_b = decode_panel(rs, ORIGINAL_PANELS[host_art][1])
    chars: dict[int, bytes] = {}
    palettes: dict[int, list[int]] = {}
    gen = list(GENERATED_PALETTE)
    gen[FILL_TERRAIN + host_art] = _dominant(rs, host_b, range(1, ROWS - 3))
    flat = _flat_char(pool, FILL_TERRAIN + host_art, chars)                     # terrain, the host's dominant colour
    strip = _flat_char(pool, FILL_WHITE, chars)                                 # the white name strip
    blank = _flat_char(pool, 0, chars)                                          # fully transparent, for empty overlay tiles
    for c in (flat, strip, blank):
        palettes[c >> 7] = gen
    b_tiles = list(host_b.tiles)
    for r in range(1, ROWS - 1):
        for c in range(1, COLS - 1):
            b_tiles[r * COLS + c] = (flat - host_b.base) & 0xFFFF if r < ROWS - 3 else (strip - host_b.base) & 0xFFFF
    b_map = PanelMap(host_b.base, 1, ROWS, COLS, b_tiles)
    img = render_overlay(outline, name) if outline else render_overlay([(0, 0), (1, 0), (1, 1)], name)
    if not outline:
        for y in range(0, ROWS * 8 - 20):
            img[y] = [0] * (COLS * 8)
    tiles = rendered_tiles(img)
    assigned: dict[tuple[int, ...], int] = {}
    words = []
    for t in tiles:
        if not any(t):
            words.append(blank)
            continue
        if t in assigned:
            words.append(assigned[t])
            continue
        if t in pool.patterns:                                        # the same tile in an earlier panel
            c = pool.patterns[t]
            assigned[t] = c
            chars.setdefault(c, char_bytes([[{0: 0, 1: pool.roles[c >> 7][0], 2: pool.roles[c >> 7][1], 3: pool.roles[c >> 7][2]}[t[y * 8 + x]] for x in range(8)] for y in range(8)]))
            if (c >> 7) in FREE_PALETTES:
                palettes[c >> 7] = gen
            words.append(c)
            continue
        for p in sorted(pool.slots, key=lambda q: (q not in FREE_PALETTES, q)):          # the generated block first (true black), page tails as overflow
            if pool.slots[p]:
                c = pool.slots[p].pop(0)
                break
        else:
            raise PatchError("no free characters left for the generated panels")
        pool.patterns[t] = c
        line, accent, text = pool.roles[p]
        colour = {0: 0, 1: line, 2: accent, 3: text}
        px = [[colour[t[y * 8 + x]] for x in range(8)] for y in range(8)]
        chars[c] = char_bytes(px)
        assigned[t] = c
        pool.used[c] = 1
        if p in FREE_PALETTES:
            palettes[p] = gen
        words.append(c)
    # base 0x8000: tile words with bit 15 are the high-priority category (segaic24 tile_info), drawn over the picture
    return Rendered(PanelMap(TILE_WORDS_BASE_B, 1, ROWS, COLS, words), b_map, chars, palettes)   # tile = char; word = 0x8000 | char


def install_panels(rs: RomSet, panels: list[Rendered]) -> tuple[RomSet, list[tuple[int, int]]]:
    """Write the panels' characters, maps, a relocated select-upload list (old pairs + one per character run)
    and an extended palette block into bank 0's free tail; point the directory's phase-1 entry at them.
    Returns the new RomSet and each panel's (A, B) window addresses."""
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    start, room = BANK0_FREE
    if any(b != 0xFF for b in rs.data[start:start + room]):
        raise PatchError("bank 0's free tail is not free")
    image = bytearray()
    def place(blob: bytes) -> int:                                 # window address of blob, 16-aligned
        while len(image) % 16:
            image.append(0xFF)
        at = 0x100000 + start + len(image)
        image.extend(blob)
        return at
    chars: dict[int, bytes] = {}
    for p in panels:
        chars.update(p.chars)
    runs: list[tuple[int, int]] = []                               # (first char, count) contiguous
    for c in sorted(chars):
        if runs and runs[-1][0] + runs[-1][1] == c:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((c, 1))
    pairs = list((src, dst) for src, dst, _ in select_uploads(rs))
    for first, count in runs:
        src = place(struct.pack("<I", count) + b"".join(chars[c] for c in range(first, first + count)))
        pairs.append((src, 0x780000 + first * CHAR_BYTES))
    addrs = []
    for p in panels:
        a = place(encode_panel(p.a_map))
        b = place(encode_panel(p.b_map))
        addrs.append((a, b))
    pal = select_palette(rs)
    words = list(pal["words"])
    top = max(FREE_PALETTES) + 1
    needed = (top - 0x60) * 16
    words += [0] * (needed - len(words))
    for p in panels:
        for idx, colours in p.palettes.items():
            words[(idx - 0x60) * 16:(idx - 0x60) * 16 + 16] = colours
    pal_ptr = place(struct.pack("<2I", pal["dst"], len(words)) + struct.pack(f"<{len(words)}H", *words) + struct.pack("<2I", 0, 0))
    list_ptr = place(b"".join(struct.pack("<2I", s, d) for s, d in pairs) + struct.pack("<2I", 0, 0))
    if len(image) > room:
        raise PatchError(f"generated panels need {len(image)} bytes, bank 0 has {room}")
    write_data(out, start, bytes(image))
    write_data(out, BANK0_DIR_PHASE1, struct.pack("<2I", list_ptr, pal_ptr))
    return out, addrs
