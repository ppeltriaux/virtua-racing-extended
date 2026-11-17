"""Phase 33 fix wave (review C1): an ORIGINAL course's picture on the COURSE DIRECTION screen.

The fault. The direction screen (dirscreen.py) draws the chosen entry's select picture twice, on layer 2, and the ring arrows
on layer 0 over it. A converted course's picture is one map (Phase 21). An original's is the game's own TWO maps: the front one
("B", layer 0 on the course select, the terrain, with see-through pixels) over the back one ("A", layer 2: the lake or sea, the
track, the name). The screen drew B alone, on the back layer, so every see-through pixel of it showed the palette's colour 0
(Acropolis's cyan, Bay Bridge's magenta) or nothing of the name (Big Forest's black). Since Phase 33 an original's course lock
opens the screen, so this showed in every single-play game on an original, in either direction.

The tile hardware has two planes (layers 0 and 2; 1 and 3 are their windows), and an original needs three things over one
another: A, B, the arrow. So for an original (menu entry below 3) the screen is drawn in another arrangement:
- layer 2: the A map, as the course select has it: the left picture the game's own map and characters (palettes at the art's
  `a_dst`), the right picture a copy of the map on the characters of the NEXT art's A blocks, to which the characters and the
  two palettes are copied, so that the two sides can be coloured apart at the lock;
- layer 0: the B map through select.`picture`, as the course select has it (slot 0's blocks on the left, slot 2's on the right);
- the arrows, also layer 0: in the cells an arrow has a pixel in ("ring cells", 60 of its 144) the cell is a character made at
  build time, the arrow's pixels over B's (B's see-through pixels stay see-through, so A shows); the other cells of the arrow's
  12 x 12 square hold B's own tile words. A ring cell's character needs the arrow's colours and the B colours it shows in ONE
  palette: the ring cells of a side are parted into at most two palettes (measured: 1 or 2 on the three courses), each with a
  character block of its own: the middle slot's block the plain arrow would use (dirgfx.BLOCKS[0] left, [1] right) and one block
  of the THIRD art's A blocks.
Everything a picture shows outside the arrow's pixels is then, pixel for pixel, what the course select shows for that original.
The lock look: `dirdone` writes the two slots' B palettes (chosen / grey) as for every course; here the A palettes of each
side and the ring cells' palettes follow (a colour of a ring palette is the arrow's, or B's with its chosen and its grey word
from the game's START tables).

The other arts' A blocks and the middle slot's blocks are characters of the course select; the direction screen leads to the
race only, and the next select screen uploads them again (mode 0x0f), as it does the middle slot's since Phase 26.

Code: two routines in a block of their own (`tencourse.origpic_address`, erased program ROM below the originals' reverse
block). NOTHING inside the directory image is changed; one boot ROM site is: LOCK_SITE's `jsr dirlock` becomes `jsr olock`.
- "olock" is `dirlock` (dirscreen.py) again with one difference: the handler the select entity gets when the screen opens is
  "osel" for an original and `dirsel` for every other entry. It runs **the same number of instructions as `dirlock` on every
  path a converted course takes** (it uses R10 and R11, the handler's to write, where `dirlock` saved R0: two instructions
  spared, spent on the entry's compare and branch; two `nop` on the paths that end in the original instruction). MAME's V60
  charges every instruction alike, so a converted course's frames from the course lock to the race load are the frames of
  the set without this module, pixel for pixel (tested; the second review found a frame end three cells further along the
  layer clear when a dispatch stood in front of `dirdraw`).
- "osel", an original's handler while the screen is open. On the screen's first logic frame (DIR_SHOWN 0xff) it first waits
  FIRST_WAIT passes of a two-instruction loop and then jumps to `dirsel`. Why: `dirdraw`'s first phase clears layer 0 before it
  redraws layer 2, and the handler starts a fraction of a millisecond before a video frame's end (measured: a blank of the
  slots placed here was caught after two of the three slots), so that frame showed layer 0 cleared and an original's A maps
  alone, in the wrong colours (second review, I-A; on a converted course layer 2 has nothing under the slots and the frame is
  black, as on main). After the wait the frame's end has passed with the complete course select on the screen, and the clears
  and the redraw all fall inside the next video frame. This rests on the emulator's timing; the standing test reads every
  frame of the transition. While drawing (DIR_SHOWN 0xfe..0xfa)
  it runs the phase itself: 0xfe / 0xfd `picture` into slot 0 / slot 2 at the picture's cells on LAYER 0 (no `picture` call when
  the entry has no picture record, as `dirdraw`; the phase's rows still run, as `dirdraw`'s do); then the phase's rows (source, destination, count: count 0 a blit by 0xff9436, else
  longwords copied; a zero word ends them); then DIR_SHOWN - 1, as `dirdraw` steps it. Once drawn it calls `dirsel` and, on
  the logic frame `dirsel` locks the direction (the handler it left is the game's lock handler 0xfc277c), copies the lock
  rows of the choice DIR_SHOWN: the two slots' B palettes, the two sides' A palettes and the ring palettes, each in its chosen
  or grey look, once, all in that logic frame. (`dirdone`, from `start` on every later logic frame, writes the same B
  palettes again; nothing writes the others before the race load.)
Data, per original, in two pieces, written at the very end of the build on what is still erased, so that nothing else of the
set moves: the DRAW piece (its five row lists, the right side's A map, the ring characters and the two 12 x 12 maps), read
only while the screen draws, and the LOCK piece (the ring palettes in three looks and the two lock lists), read on the
lock's logic frame, always in the boot ROM, which no bank switch unmaps (second review, minor 3). The six
addresses are the block's last 24 bytes."""
from __future__ import annotations

import random
import struct
from dataclasses import dataclass

import numpy as np

from vrtools.arcade import dirgfx
from vrtools.arcade.dirscreen import (ARROW_CELLS, COURSE_LOCK, DIR_ARMED, DIR_PHASE, DIR_SHOWN, DIR_TIMER, DRAW_PHASES, DRAW_SAVED, DRAWN,
                                       HANDLER, LINKED, LOCK_PATTERN, LOCK_SITE, PICTURE_CELLS, TIMER, tile_address)
from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.select import SLOT_PAL
from vrtools.arcade.panel import ORIGINAL_PANELS, char_pixels, char_source, decode_panel, select_palette
from vrtools.arcade.patch import PatchError, write_program_blob
from vrtools.arcade.picture import START_TABLES, _boot_u32, original_map
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.arcade.select import BLIT, MENU_INDEX, SLOT_CHAR
from vrtools.arcade.v60asm import Block, asm

BLOCK_BYTES = 512                      # the code block: the routines (under 480 bytes), then the six data addresses
ORIGINALS_BELOW = 3
ROW_BYTES = 12                                     # source, destination, count
PHASES = DRAW_PHASES[1:]                           # 0xfe .. 0xfa: the phases "odraw" runs itself
A_HOME = (0x3000, 0x3100, 0x3200)                  # each art's A characters (two blocks; its two palettes at a_dst)
SIDE_SLOT = (0, 2)                                 # the picture slot of each side (NORMAL, REVERSE), as dirdraw
SIDE_CLOCKWISE = (True, False)                     # the originals lap clockwise: NORMAL shows the clockwise arrow, white
SIDE_ARROW = (dirgfx.WHITE, dirgfx.RED)
RING_PALETTES = 2                                  # at most, a side
LOOKS = ("normal", "chosen", "grey")
BOX = (ARROW_CELLS[0][0] - PICTURE_CELLS[0][0], ARROW_CELLS[0][1] - PICTURE_CELLS[0][1])     # the arrow's square inside a picture
ROUTINES = ("olock", "orows", "osel")
FIRST_WAIT = 4000                                  # "osel"'s wait on the screen's first logic frame, in loop passes of two instructions


def _palette(rs: RomSet, index: int) -> list[int]:
    sp = select_palette(rs)
    o = (0x900000 + 32 * index - sp["dst"]) // 2
    if not (0 <= o and o + 16 <= len(sp["words"])):
        raise PatchError(f"palette {index:#x} is not in the select screen's palette block")
    return sp["words"][o:o + 16]


def _table(rs: RomSet, addr: int, n: int) -> list[int]:
    return list(struct.unpack_from(f"<{n}H", rs.boot, addr - V60_BOOT))


@dataclass(frozen=True)
class Layers:
    """An original's picture as the course select draws it: per cell (row-major, 16 x 21) the A and B characters' pixels
    (colour indices), their character numbers and, per layer, the three looks of its palettes (`LOOKS`: lists of 16-word
    palettes)."""
    art: int
    a_codes: tuple[int, ...]
    b_local: tuple[int, ...]
    a_pixels: tuple
    b_pixels: tuple
    a_looks: dict
    b_looks: dict
    tables: dict

    def colour(self, layer: str, cell: int, value: int, look: str) -> int:
        if layer == "a":
            return self.a_looks[look][(self.a_codes[cell] - A_HOME[self.art]) >> 7][value]
        return self.b_looks[look][self.b_local[cell] >> 7][value]


def layers(rs: RomSet, art: int) -> Layers:
    a = decode_panel(rs, ORIGINAL_PANELS[art][0])
    codes = tuple(w & 0x7FFF for w in a.words())
    if a.mode != 0 or a.base != A_HOME[art] or (a.rows, a.cols) != (21, 16) or not all(A_HOME[art] <= c < A_HOME[art] + 0x100 for c in codes):
        raise PatchError(f"art {art}: its A map is not 21 x 16 bytes on the two blocks at {A_HOME[art]:#x}")
    local = tuple(original_map(rs, art))
    t = {k: _boot_u32(rs, ad + 4 * art) for k, ad in START_TABLES.items()}
    if t["a_dst"] != 0x900000 + 32 * (A_HOME[art] >> 7):
        raise PatchError(f"art {art}: its A palettes are at {t['a_dst']:#x}")
    split = lambda words: [words[16 * k:16 * k + 16] for k in range(len(words) // 16)]
    a_looks = {"normal": [_palette(rs, (A_HOME[art] >> 7) + k) for k in range(2)], "chosen": split(_table(rs, t["a_chosen"], 32)),
               "grey": split(_table(rs, t["a_grey"], 32))}
    b_looks = {"normal": [_palette(rs, (SLOT_CHAR[art] >> 7) + k) for k in range(3)], "chosen": split(_table(rs, t["b_chosen"], 48)),
               "grey": split(_table(rs, t["b_grey"], 48))}
    px = lambda code: np.array(char_pixels(char_source(rs, code)), np.uint8)
    return Layers(art, codes, local, tuple(px(c) for c in codes), tuple(px(SLOT_CHAR[art] + l) for l in local), a_looks, b_looks, t)


def _partition(sets: list[frozenset], cap: int = 15) -> list[list]:
    """`sets` parted into the fewest groups found whose unions hold at most `cap` keys: first fit by size, then 200 seeded
    shuffles (deterministic). Each group is the sorted list of its keys."""
    best = None
    rng = random.Random(33)
    items = sorted(set(sets), key=lambda s: (-len(s), sorted(s)))
    for attempt in range(201):
        if attempt:
            rng.shuffle(items)
        bins: list[set] = []
        for s in items:
            fit = [b for b in bins if len(b | s) <= cap]
            if fit:
                min(fit, key=lambda b: len(s - b)).update(s)
            else:
                bins.append(set(s))
        if best is None or len(bins) < len(best):
            best = bins
    return [sorted(b) for b in best]


@dataclass(frozen=True)
class Ring:
    """One side's ring cells: per palette group its characters (32 bytes each) and its three looks (16 words each), and the
    12 x 12 square's tile words (a ring cell: 0x8000 | its block + its character; another cell: B's own word in the side's slot)."""
    chars: tuple[tuple[bytes, ...], ...]
    looks: tuple[dict, ...]
    words: tuple[int, ...]
    blocks: tuple[int, ...]


def ring_blocks(art: int, side: int) -> tuple[int, int]:
    """The two character blocks a side's ring characters may take: the middle slot's block of the plain arrow of that side, and
    one block of the third art's A blocks."""
    return dirgfx.BLOCKS[side], A_HOME[(art + 2) % 3] + 0x80 * side


def ring(ly: Layers, side: int) -> Ring:
    """The arrow of `side` over the original's B map (see the module's docstring). PatchError when a side needs more than
    RING_PALETTES palettes."""
    arrow = dirgfx.arrow_bitmap(SIDE_CLOCKWISE[side])
    colours = SIDE_ARROW[side]
    cells = {}
    for r in range(dirgfx.ARROW_CELLS):
        for c in range(dirgfx.ARROW_CELLS):
            t = arrow[8 * r:8 * r + 8, 8 * c:8 * c + 8]
            if not t.any():
                continue
            cell = (r + BOX[0]) * 16 + c + BOX[1]
            keys = np.empty((8, 8), object)
            for y in range(8):
                for x in range(8):
                    if t[y, x]:
                        keys[y, x] = (colours[int(t[y, x])],) * 3
                    elif ly.b_pixels[cell][y, x]:
                        keys[y, x] = tuple(ly.colour("b", cell, int(ly.b_pixels[cell][y, x]), look) for look in LOOKS)
                    else:
                        keys[y, x] = None
            cells[(r, c)] = keys
    groups = _partition([frozenset(k for k in keys.flat if k is not None) for keys in cells.values()])
    if len(groups) > RING_PALETTES:
        raise PatchError(f"art {ly.art}: the arrow's cells on side {side} need {len(groups)} palettes, more than {RING_PALETTES}")
    blocks = ring_blocks(ly.art, side)
    chars: list[list[bytes]] = [[] for _ in groups]
    seen: list[dict] = [{} for _ in groups]
    slot_base = 0x8000 | SLOT_CHAR[SIDE_SLOT[side]]
    words = []
    for r in range(dirgfx.ARROW_CELLS):
        for c in range(dirgfx.ARROW_CELLS):
            cell = (r + BOX[0]) * 16 + c + BOX[1]
            if (r, c) not in cells:
                words.append(slot_base + ly.b_local[cell])
                continue
            keys = cells[(r, c)]
            need = {k for k in keys.flat if k is not None}
            g = next(i for i, grp in enumerate(groups) if need <= set(grp))
            index = {k: 1 + n for n, k in enumerate(groups[g])}
            t = np.array([[index[keys[y, x]] if keys[y, x] is not None else 0 for x in range(8)] for y in range(8)], np.uint8)
            b = dirgfx.char_bytes(t)
            if b not in seen[g]:
                seen[g][b] = len(chars[g])
                chars[g].append(b)
            words.append((0x8000 | blocks[g]) + seen[g][b])
    if any(len(c) > dirgfx.BLOCK_CHARS for c in chars):
        raise PatchError(f"art {ly.art}: more than {dirgfx.BLOCK_CHARS} ring characters in a block")
    looks = tuple({look: [0] + [k[n] for k in grp] + [0] * (15 - len(grp)) for n, look in enumerate(LOOKS)} for grp in groups)
    return Ring(tuple(tuple(c) for c in chars), looks, tuple(words), blocks[:len(groups)])


def expected_picture(ly: Layers, look: str = "normal", side: int | None = None) -> np.ndarray:
    """The original's picture as the course select shows it, 168 x 128 colour words (0: neither layer has a pixel): B over A in
    `look`. With `side`, the direction screen's picture of that side: the arrow's pixels in the arrow's colours over it."""
    out = np.zeros((168, 128), np.uint16)
    for cell in range(336):
        r, c = divmod(cell, 16)
        for y in range(8):
            for x in range(8):
                b, a = int(ly.b_pixels[cell][y, x]), int(ly.a_pixels[cell][y, x])
                out[8 * r + y, 8 * c + x] = ly.colour("b", cell, b, look) if b else ly.colour("a", cell, a, look) if a else 0
    if side is not None:
        arrow = dirgfx.arrow_bitmap(SIDE_CLOCKWISE[side])
        ys, xs = np.nonzero(arrow)
        out[ys + 8 * BOX[0], xs + 8 * BOX[1]] = np.array(SIDE_ARROW[side], np.uint16)[arrow[ys, xs]]
    return out


def _map_words(words, rows: int, cols: int) -> bytes:
    """A map 0xff9436 blits, mode 1 with base 0: the tile words themselves."""
    return struct.pack("<HHII", 0, 1, rows, cols) + struct.pack(f"<{len(words)}H", *words)


def char_address(code: int) -> int:
    return dirgfx.CHAR_RAM + dirgfx.CHAR_BYTES * code


def data_sizes(rs: RomSet, art: int) -> tuple[int, int]:
    """(the draw piece's size, the lock piece's size) of original `art` (independent of where they lie)."""
    draw, lock, _ = picture_data(rs, art, 0x100000, 0x180000)
    return len(draw), len(lock)


def picture_data(rs: RomSet, art: int, draw_at: int, lock_at: int) -> tuple[bytes, bytes, dict]:
    """Original `art`'s two data pieces (see the module's docstring) at `draw_at` and `lock_at` (4-aligned), and where their
    parts lie: {"lists": the five drawing phases' row lists (index DIR_SHOWN - 0xfa), "lock": the two lock lists (by choice),
    "a_map", "ring": per side {"chars": [...], "looks": [{look: address}], "map"}, "blocks"}. Each piece starts with the
    pointers to its lists; a row is ROW_BYTES (source, destination, count), a list ends with a zero word."""
    if draw_at % 4 or lock_at % 4:
        raise PatchError(f"the originals' picture data at {draw_at:#x} / {lock_at:#x} is not 4-aligned")
    images = {"draw": bytearray(4 * len(PHASES)), "lock": bytearray(4 * 2)}
    base = {"draw": draw_at, "lock": lock_at}

    def put(piece: str, b: bytes) -> int:
        image = images[piece]
        while len(image) % 4:
            image.append(0)
        o = base[piece] + len(image)
        image.extend(b)
        return o
    ly = layers(rs, art)
    nxt = (art + 1) % 3
    a = decode_panel(rs, ORIGINAL_PANELS[art][0])
    a_map = put("draw", struct.pack("<HHII", A_HOME[nxt], 0, a.rows, a.cols) + bytes(a.tiles))
    rings = [ring(ly, side) for side in range(2)]
    ring_at = []
    for rg in rings:
        ring_at.append({"chars": [put("draw", b"".join(c)) for c in rg.chars],
                        "looks": [{look: put("lock", struct.pack("<16H", *lk[look])) for look in LOOKS} for lk in rg.looks],
                        "map": put("draw", _map_words(rg.words, dirgfx.ARROW_CELLS, dirgfx.ARROW_CELLS))})
    copy = lambda src, dst, n_bytes: (src, dst, (n_bytes + 3) // 4)
    blit = lambda src, dst: (src, dst, 0)
    a_chars = max(a.tiles) + 1
    a_dst = [0x900000 + 32 * (A_HOME[k] >> 7) for k in range(3)]
    rows = {s: [] for s in PHASES}
    rows[PHASES[0]] = [blit(ORIGINAL_PANELS[art][0], tile_address(2, *PICTURE_CELLS[0]))]
    rows[PHASES[1]] = [copy(char_address(A_HOME[art]), char_address(A_HOME[nxt]), 32 * a_chars), copy(a_dst[art], a_dst[nxt], 64),
                       blit(a_map, tile_address(2, *PICTURE_CELLS[1]))]
    for side in range(2):
        rows[PHASES[2 + side]] = [copy(src, char_address(blk), 32 * len(ch))
                                  for src, blk, ch in zip(ring_at[side]["chars"], rings[side].blocks, rings[side].chars)]
    rows[PHASES[4]] = ([copy(lk["normal"], dirgfx.palette_address(blk), 32) for side in range(2)
                        for lk, blk in zip(ring_at[side]["looks"], rings[side].blocks)]
                       + [blit(ring_at[side]["map"], tile_address(0, *ARROW_CELLS[side])) for side in range(2)])
    lock = []
    for choice in range(2):
        ls = []
        for side in range(2):
            look = "chosen" if side == choice else "grey"
            ls.append(copy(ly.tables["b_chosen" if side == choice else "b_grey"], SLOT_PAL[SIDE_SLOT[side]], 96))    # as dirdone
            ls.append(copy(ly.tables["a_chosen" if side == choice else "a_grey"], a_dst[art] if side == 0 else a_dst[nxt], 64))
            ls += [copy(lk[look], dirgfx.palette_address(blk), 32) for lk, blk in zip(ring_at[side]["looks"], rings[side].blocks)]
        lock.append(ls)
    at = {"draw": [], "lock": []}
    for piece, lists in (("draw", [rows[s] for s in sorted(PHASES)]), ("lock", lock)):      # 0xfa first: index DIR_SHOWN - 0xfa
        for k, rs_ in enumerate(lists):
            o = put(piece, b"".join(struct.pack("<III", *row) for row in rs_) + bytes(4))
            struct.pack_into("<I", images[piece], 4 * k, o)
            at[piece].append(o)
    for image in images.values():
        while len(image) % 16:
            image.append(0)
    return bytes(images["draw"]), bytes(images["lock"]), {"lists": at["draw"], "lock": at["lock"], "a_map": a_map, "ring": ring_at,
                                                           "blocks": [rg.blocks for rg in rings]}


def table_address(base: int) -> int:
    """The six data addresses' place (the three draw pieces', then the three lock pieces'): the block's last 24 bytes."""
    return base + BLOCK_BYTES - 8 * ORIGINALS_BELOW


def origpic_routines(base: int, lay: dict[str, int]) -> dict[str, bytes]:
    """"olock", "orows" (the row lists' interpreter) and "osel" at `base` (see
    the module's docstring). `lay`: the directory's layout (reverse, dirsel, pictures, slot_tile, picture). They read the
    originals' data addresses at `table_address(base)`."""
    draw_at = table_address(base)
    lock_at = draw_at + 4 * ORIGINALS_BELOW
    out: dict[str, bytes] = {}

    def build(osel_at: int) -> None:
        out.clear()
        b = Block(base)                                         # olock: dirlock's instruction count on every path (see above)
        b.emit("cmp.b imm,abs", 0, LINKED)
        b.branch("bne", "orig")
        b.emit("cmp.b imm,abs", 0, DIR_PHASE)                   # the direction lock's own pass through the lock handler
        b.branch("bne", "orig")
        b.emit("movz.bw abs,reg", MENU_INDEX, "r10")
        b.emit("mov.w abs(reg),reg", lay["reverse"], "r10", "r11")
        b.emit("cmp.w imm,reg", 0, "r11")
        b.branch("be", "orig")
        b.emit("cmp.w imm,reg", ORIGINALS_BELOW, "r10")
        b.branch("bge", "seven")
        b.emit("mov.w imm,disp[reg]", osel_at, HANDLER, "r25")
        b.branch("br", "open")
        b.label("seven")
        b.emit("mov.w imm,disp[reg]", lay["dirsel"], HANDLER, "r25")
        b.label("open")
        b.emit("mov.w imm,abs", DIR_TIMER, TIMER)
        b.emit("mov.b imm,abs", 1, DIR_PHASE)
        b.emit("mov.b imm,abs", 0, DIR_ARMED)
        b.emit("mov.b imm,abs", 0xFF, DIR_SHOWN)
        b.emit("mov.b imm,abs", 0, DIRECTION_RAM)
        b.emit("rsr")
        b.label("orig")
        b.emit("nop")                                           # dirlock's push and pop of R0, in instructions
        b.emit("nop")
        b.raw(LOCK_PATTERN)                                     # the original instruction
        b.emit("rsr")
        out["olock"] = b.bytes()
        run_rows = base + len(out["olock"])
        b = Block(run_rows)                                     # orows: the rows at R9; R0-R2 written (and what the blit writes)
        b.label("row")
        b.emit("mov.w [reg],reg", "r9", "r0")                   # source; 0 ends the rows
        b.emit("cmp.w imm,reg", 0, "r0")
        b.branch("be", "end")
        b.emit("mov.w disp[reg],reg", 4, "r9", "r1")
        b.emit("mov.w disp[reg],reg", 8, "r9", "r2")
        b.emit("cmp.w imm,reg", 0, "r2")
        b.branch("bne", "copy")
        b.emit("jsr abs", BLIT)
        b.branch("br", "next")
        b.label("copy")
        b.emit("mov.w [reg],[reg]", "r0", "r1")
        b.emit("add.w imm,reg", 4, "r0")
        b.emit("add.w imm,reg", 4, "r1")
        b.emit("sub.w imm,reg", 1, "r2")
        b.branch("bne", "copy")
        b.label("next")
        b.emit("add.w imm,reg", ROW_BYTES, "r9")
        b.branch("br", "row")
        b.label("end")
        b.emit("rsr")
        out["orows"] = b.bytes()
        b = Block(run_rows + len(out["orows"]))                 # osel: R10-R14 are the handler's
        b.emit("cmp.b imm,abs", DRAW_PHASES[0], DIR_SHOWN)
        b.branch("be", "first")
        b.emit("cmp.b imm,abs", DRAWN, DIR_SHOWN)
        b.branch("bnh", "drawn")
        b.emit("pushm imm", DRAW_SAVED)
        b.emit("cmp.b imm,abs", PHASES[2], DIR_SHOWN)           # 0xfc and below (unsigned): rows only
        b.branch("bnh", "rows")                                 # 0xfe / 0xfd: B into the side's slot, on layer 0
        b.emit("movz.bw abs,reg", MENU_INDEX, "r11")
        b.emit("mov.w abs(reg),reg", lay["pictures"], "r11", "r11")
        b.emit("cmp.w imm,reg", 0, "r11")                       # no picture record (a set without pictures): as dirdraw
        b.branch("be", "rows")
        b.emit("mov.w imm,reg", SIDE_SLOT[0], "r10")
        b.emit("mov.w imm,reg", tile_address(0, *PICTURE_CELLS[0]), "r12")
        b.emit("cmp.b imm,abs", PHASES[0], DIR_SHOWN)
        b.branch("be", "slot")
        b.emit("mov.w imm,reg", SIDE_SLOT[1], "r10")
        b.emit("mov.w imm,reg", tile_address(0, *PICTURE_CELLS[1]), "r12")
        b.label("slot")
        b.emit("mov.w abs(reg),reg", lay["slot_tile"], "r10", "r13")
        b.emit("jsr abs", lay["picture"])
        b.label("rows")
        b.emit("movz.bw abs,reg", DIR_SHOWN, "r9")
        b.emit("sub.w imm,reg", PHASES[-1], "r9")
        b.emit("shl.w imm,reg", 2, "r9")
        b.emit("movz.bw abs,reg", MENU_INDEX, "r8")
        b.emit("mov.w abs(reg),reg", draw_at, "r8", "r8")       # the original's draw piece: its row lists' addresses first
        b.emit("add.w reg,reg", "r8", "r9")
        b.emit("mov.w [reg],reg", "r9", "r9")                   # the phase's rows
        b.emit("jsr abs", run_rows)
        b.emit("movz.bw abs,reg", DIR_SHOWN, "r0")
        b.emit("sub.w imm,reg", 1, "r0")
        b.emit("mov.b reg,abs", "r0", DIR_SHOWN)
        b.emit("popm imm", DRAW_SAVED)
        b.emit("rsr")
        b.label("drawn")                                        # the screen as every course's; then, at the lock, the lock look
        b.emit("jsr abs", lay["dirsel"])
        b.emit("cmp.w imm,disp[reg]", COURSE_LOCK, HANDLER, "r25")
        b.branch("bne", "out")
        b.emit("pushm imm", DRAW_SAVED)
        b.emit("movz.bw abs,reg", DIR_SHOWN, "r9")              # the choice (0, 1)
        b.emit("shl.w imm,reg", 2, "r9")
        b.emit("movz.bw abs,reg", MENU_INDEX, "r8")
        b.emit("mov.w abs(reg),reg", lock_at, "r8", "r8")       # the original's lock piece: its two lists' addresses first
        b.emit("add.w reg,reg", "r8", "r9")
        b.emit("mov.w [reg],reg", "r9", "r9")
        b.emit("jsr abs", run_rows)
        b.emit("popm imm", DRAW_SAVED)
        b.label("out")
        b.emit("rsr")
        b.label("first")                                        # wait out the video frame's end (see the module's docstring)
        b.emit("mov.w imm,reg", FIRST_WAIT, "r10")
        b.label("wait")
        b.emit("sub.w imm,reg", 1, "r10")
        b.branch("bne", "wait")
        b.label("plain")
        b.emit("jmp abs", lay["dirsel"])
        out["osel"] = b.bytes()
    build(0x100000)                                             # the sizes do not depend on the address
    sizes = {k: len(v) for k, v in out.items()}
    build(base + sizes["olock"] + sizes["orows"])
    assert {k: len(v) for k, v in out.items()} == sizes and tuple(out) == ROUTINES
    return out


def origpic_layout(base: int, lay: dict[str, int]) -> dict[str, int]:
    out, addr = {}, base
    for name, code in origpic_routines(base, lay).items():
        out[name] = addr
        addr += len(code)
    out["end"] = addr
    return out


def lock_site(target: int) -> bytes:
    """LOCK_SITE's nine bytes calling `target`: the `jsr`, nop-padded, as dirscreen.patch_dirscreen_sites writes it for `dirlock`."""
    b = Block(LOCK_SITE)
    b.emit("jsr abs", target)
    return b.bytes() + asm("nop") * (len(LOCK_PATTERN) - len(b.bytes()))


def install_origpic(rs: RomSet, base: int, lay: dict[str, int], draw_at: list[int], lock_at: list[int]) -> None:
    """The code block at `base` (erased program ROM) with the six data addresses at its end, and LOCK_SITE's call, in place; the
    data must already lie there, the lock pieces in the boot ROM. Everything is checked before anything is written."""
    code = origpic_routines(base, lay)
    image = b"".join(code.values())
    if len(image) > BLOCK_BYTES - 8 * ORIGINALS_BELOW or len(draw_at) != ORIGINALS_BELOW or len(lock_at) != ORIGINALS_BELOW:
        raise PatchError(f"the originals' picture block: {len(image)} bytes of code (the block is {BLOCK_BYTES}, 24 of them the table)")
    if any(a < V60_BOOT for a in lock_at):
        raise PatchError(f"an original's lock data is not in the boot ROM: {[hex(a) for a in lock_at]}")
    have = rs.boot[LOCK_SITE - V60_BOOT:LOCK_SITE - V60_BOOT + len(LOCK_PATTERN)]
    if have != lock_site(lay["dirlock"]):
        raise PatchError(f"the course lock site at {LOCK_SITE:#x} does not call dirlock: {have.hex()}")
    image = image.ljust(BLOCK_BYTES - 8 * ORIGINALS_BELOW, b"\0") + struct.pack("<6I", *draw_at, *lock_at)
    off = base - V60_PROGRAM
    if any(x != 0xFF for x in rs.program[off:off + BLOCK_BYTES]):
        raise PatchError(f"program ROM at {base:#x} (+{BLOCK_BYTES}) is not erased for the originals' picture block")
    write_program_blob(rs, base, image)
    boot = bytearray(rs.boot)
    boot[LOCK_SITE - V60_BOOT:LOCK_SITE - V60_BOOT + len(LOCK_PATTERN)] = lock_site(origpic_layout(base, lay)["olock"])
    object.__setattr__(rs, "boot", bytes(boot))
