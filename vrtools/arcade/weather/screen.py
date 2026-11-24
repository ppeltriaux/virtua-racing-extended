"""Weather stage 1: the COURSE WEATHER screen after COURSE DIRECTION (DRY or RAIN), the direction screen's grey-out and hold, the
weather byte, the HUD word and the no-record gate. Ported from spike 64 (branch `spike64-weather-screen`, de04235,
`vrtools/arcade/weather.py`; findings docs/spike/2026-11-spike64-weather-screen-findings.md); the behaviour is the one Pascal drove
in out/p71weather.

Pascal: "When: an addition weather selection screen like the reverse but for weather" (17 Nov 2026); "btw i think storm and rain
shoudl be together (no separation on the course selection)" (18 Nov: two choices, RAIN being the whole storm); after driving:
"i think leave the color the same on the selected one for the weather selection screen, you dont want the rain circuit dimmed";
"the color change is working"; "i just notice a separate bug: selecting reverse or normal doesnt grey out the one not selected
(will need a fix)". The session lead's calls, not yet Pascal's decisions (ScreenTune and the art): the word RAIN, the cloud-with-bolt
badge on all ten courses and none on DRY, the wheel at rest or left DRY and right RAIN, the 10 s countdown.

The direction word (course.DIRECTION_RAM, 0x502294..97: the flag, DIR_PHASE, DIR_ARMED, DIR_SHOWN) carries the two screens:
- DIR_PHASE: 1 the direction chosen (`dirsel`), 2 its lock, HOLDING (5) the direction's lock look held, OPEN (3) the weather chosen,
  LOCKED (4) the weather locked.
- DIR_ARMED: on COURSE DIRECTION the arming flag (dirscreen); during the hold the hold's countdown; on COURSE WEATHER its own arming
  flag; from the weather lock on the WEATHER BYTE (weather.WEATHER_BYTE: 0 DRY, 1 RAIN).
- DIR_SHOWN: the choice shown (0, 1), or a drawing phase (0xff..0xfc, DRAWN 0xfb after the last).
Every select screen's state 0 clears the word (`dirclear`); `bankdemo` (the attract's and linked play's course loads) clears it
whole here (its `mov.b #0, 502294` becomes `mov.w`, the same 8 bytes), so the attract, linked play and the operator's fixed
course (whose path never reaches the course lock) race dry.

The chain (all in the select entity, as the direction screen's):
- `olock` (origpic.py) installs `wxdir` in place of `osel` / `dirsel` (its two handler immediates, same length). `wxdir` runs
  the screen's own handler (`osel` for an original, `dirsel` otherwise), then, while the direction is chosen (DIR_PHASE 1, a choice
  shown), the direction's look every logic frame (`wxdlook`): the side shown in its normal colours, the other grey (the B
  palettes; an original's A palettes and its arrows' ring palettes too).
- `dirsel`'s direction lock writes the handler `mov.w #FC277C, A[R25]`: its immediate becomes `wxsel` (same length). `wxsel`'s
  first pass (DIR_PHASE 2) shows the direction's lock look (origpic's lock lists on an original; the record's chosen and grey
  sets otherwise) and holds it `hold_frames` logic frames (HOLDING, DIR_ARMED counting down; the game's countdown raised to
  LOCK_TIMER + the hold if lower, so it cannot lock meanwhile), the direction's frame kept on its choice. Then it opens the weather
  screen: DIR_PHASE OPEN, DIR_ARMED 0, DIR_SHOWN 0xff, the timer `ScreenTune.timer`, and it waits out the video frame's end
  (origpic.FIRST_WAIT passes, the Phase 33 second review's I-A) before the first clear.
- Four drawing phases, one a logic frame (`wxdraw`): 0xff layer 0 cleared, layer 2's checker, the title, the labels and the
  piece's rows (the game's double arrow, the wheel panel, the red arrow, STEP TO START!, the SELECT WEATHER caption on the middle
  slot's third block with the panel's palette, as dirgfx's caption); 0xfe the picture into slot 0 (DRY, left); 0xfd into slot 2
  (RAIN, right), an original's A map copied to the next art's A home and moved onto its characters (origpic's arrangement); 0xfc
  the badge (the middle slot's blocks 0x3480 / 0x3500; on an original composed over its B map at build time, as origpic composes
  the arrows).
- Choosing (as `dirsel`): R10 = the wheel's two last values halved; armed once R10 <= THRESHOLD; RAIN when armed and R10 above the
  threshold, which moves HYSTERESIS away from the choice shown (no chatter at the boundary). A change reprints the labels
  (`wxshow`) and writes the look (`wxlook`: the choice in full colour, the other grey, the badge with RAIN's side). The cursor
  frame (`wxcursor`, the game's at "wxsides").
- The lock, on a gas edge or the timer at or below LOCK_TIMER (a held pedal waits for the countdown, which locks the choice shown:
  DRY unless the player steered right): the weather byte := the choice, DIR_PHASE LOCKED, the lock look (the chosen picture in the
  record's chosen set, the other grey), the handler := the game's lock handler, so the race loads in the course lock's 198 video
  frames after the weather lock. `start`'s `jmp dirdone` becomes `jmp wxdone`: the steady frame on the weather's choice after a
  weather lock, else `dirdone` as before.
- `wxgate` at the race end's record test (0xfc40ce, `rankgate3`'s shape): the record flag cleared, then Z set while the weather is
  not DRY (its `be FC417C` skips the record and the name entry), else the site's own `test1`.
- `hudwx` at the HUD site (in place of `jsr hudorig`): `hudorig`, then in a RAIN race the word in white ([0x501434] = 3) on rows
  46-47, its last letter in column 58, or in a reverse race ending two columns left of REVERSE (52, or 51 on Bay Bridge and
  Acropolis).

Layout: COURSE DIRECTION's (pictures at columns 9 and 37, the double arrow between), one row lower, the title on rows 0-2, so the
cursor frame (9-12 px above a picture) never reaches the title. Where everything lies: weather/layout.py."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

from vrtools.arcade import dirgfx
from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.hudname import ATTR as HUD_ATTR, PRINTER as HUD_PRINTER
from vrtools.arcade.origpic import A_HOME, FIRST_WAIT, ORIGINALS_BELOW
from vrtools.arcade.origrev import RANK_PATTERN
from vrtools.arcade.dirscreen import (CHECKER, CLEAR_LAYER, COURSE_LOCK, CURSOR_BODY, CURSOR_OBJECT, DIR_ARMED, DIR_PHASE, DIR_SHOWN,
                                       DOUBLE_ARROW, DRAW_SAVED, EDGE, HANDLER, LABEL_WHITE, LABEL_YELLOW, LOCK_TIMER, OBJECT_NEW,
                                       PICTURE_CELLS, PICTURE_SIZE, RED_ARROW, SIDE_X, SIDE_Y, STEP_PANEL, THRESHOLD, TIMER, TITLE_PRINT,
                                       WHEEL, WHEEL_PANEL, WHEEL_PREV, tile_address)
from vrtools.arcade.patch import PatchError
from vrtools.arcade.ranking import STRING_CALL
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.arcade.select import MENU_INDEX, REC, SLOT_CHAR
from vrtools.arcade.v60asm import Block, asm
from vrtools.arcade.weather import WEATHER_BYTE
from vrtools.arcade.weather.tune import ScreenTune

# DIR_PHASE values (dirscreen's 0, 1 and 2 stay theirs)
OPEN, LOCKED, HOLDING = 3, 4, 5
DIRECTION_LOCKED = 2                    # `dirsel`'s lock: wxsel's first pass
PHASES = (0xFF, 0xFE, 0xFD, 0xFC)      # DIR_SHOWN while drawing: clears and fixed pieces, DRY's picture, RAIN's, the badge
DRAWN = PHASES[-1] - 1
HYSTERESIS = 4                          # the threshold moves this far away from the choice shown
SLOTS = (0, 2)                          # each choice's picture slot (DRY left, RAIN right), as the direction screen's sides
PIC_ROW = PICTURE_CELLS[0][0] + 1       # one row lower than COURSE DIRECTION's pictures
PIC_COLS = (PICTURE_CELLS[0][1], PICTURE_CELLS[1][1])
TITLE, TITLE_CELL = "COURSE WEATHER", (0, 17)
LABEL_ROW, LABEL_COLS, LABEL_SLOT = 27, (14, 41), 6      # each label centred under its picture, NUL-padded to LABEL_SLOT bytes
SIDES = tuple((x, SIDE_Y - 8) for x in SIDE_X)          # the cursor frame's centre per choice (8 px lower, as the pictures)
_GAP = PIC_COLS[1] - PIC_COLS[0] - PICTURE_SIZE[1]
DOUBLE_ARROW_CELL = (PIC_ROW + (PICTURE_SIZE[0] - 8) // 2, PIC_COLS[0] + PICTURE_SIZE[1] + (_GAP - 6) // 2)
CAPTION = "SELECT WEATHER"
PANEL_ROW = 31                          # the wheel and STEP TO START! panels, one row lower than COURSE DIRECTION's (30)
CAPTION_CELL = (PANEL_ROW + dirgfx.CAPTION_PANEL_CELL[0], 7 + dirgfx.CAPTION_PANEL_CELL[1])
CAPTION_BLOCK = dirgfx.BLOCKS[2]        # 0x3580, as COURSE DIRECTION's caption, with the wheel panel's palette
BADGE_BLOCKS = dirgfx.BLOCKS[:2]        # 0x3480, 0x3500: at most two palette groups
BADGE_CELL = (3, 9)                     # the badge's first cell inside the RAIN picture
BADGE_RGB = {1: (24, 24, 40), 2: (206, 214, 231), 3: (132, 148, 181), 4: (255, 222, 66), 5: (255, 255, 230)}
ORIGINALS = ORIGINALS_BELOW             # the three originals (menu entries 0-2)
# the race end's record test (origrev.RANK_SITE, the game's own sixteen bytes there) and the HUD site (hudname.HUD_SITE): where they
# lie is weather/layout.py's table; what they hold is checked by `sites`
RECORD_FLAG = 0x5018FC
TEST1_RACE_FINISHED = bytes.fromhex("8780e1f3") + (0x501174).to_bytes(4, "little")     # test1 #1, 501174 (absolute)
HUD_WHITE = 3                           # [HUD_ATTR] for the HUD font's fourth colour, white
ROUTINES = ("wxsel", "wxdraw", "wxshow", "wxlook", "wxdir", "wxdlook", "wxcursor", "wxdone", "wxgate", "hudwx")
TABLES = ("wxsides", "wxtext", "wxpieces", "wxdpieces")
SIGNATURE = asm("cmp.b imm,abs", DIRECTION_LOCKED, DIR_PHASE)[:4]      # wxsel's first word: how the harness tells the screen is in
PIECE_HEAD = 64                         # a piece: 8 list pointers, then 8 header words
LOOK_LISTS = 4                          # the look lists after the PHASES' lists: choosing 0, choosing 1, locked 0, locked 1


def grey_word(w: int) -> int:
    """A colour word's grey: the luminance (5 r + 9 g + 2 b) / 16 on the three guns, bit 15 set."""
    r, g, b = w & 31, (w >> 5) & 31, (w >> 10) & 31
    v = (5 * r + 9 * g + 2 * b) >> 4
    return 0x8000 | v | v << 5 | v << 10


def rgb_word(c: tuple[int, int, int]) -> int:
    r, g, b = c
    return 0x8000 | (b >> 3) << 10 | (g >> 3) << 5 | (r >> 3)


# ---- the art (the project's own drawing) ------------------------------------------------------------------------------------
def _outline(shape: np.ndarray) -> np.ndarray:
    h, w = shape.shape
    p = np.pad(shape, 1)
    ring = np.zeros_like(shape)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            ring |= p[1 + oy:1 + oy + h, 1 + ox:1 + ox + w]
    return ring & ~shape


def _inside(px: np.ndarray, py: np.ndarray, pts) -> np.ndarray:
    """Even-odd test of the points (px, py) against the polygon `pts`."""
    ins = np.zeros(px.shape, bool)
    j = len(pts) - 1
    for i in range(len(pts)):
        (xi, yi), (xj, yj) = pts[i], pts[j]
        ins ^= ((yi > py) != (yj > py)) & (px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi)
        j = i
    return ins


def badge_bitmap() -> np.ndarray:
    """The RAIN badge, 32 x 40 px: a cloud (2 light, 3 its shaded underside) and a bolt below it (4, its core 5), a dark outline (1)
    round both, 0 transparent."""
    h, w = 40, 32
    y, x = np.mgrid[0:h, 0:w] + 0.5
    cloud = (((x - 11) ** 2 + (y - 13) ** 2 < 49) | ((x - 19) ** 2 + (y - 9) ** 2 < 64) | ((x - 25) ** 2 + (y - 15) ** 2 < 30)
             | ((y > 12) & (y < 20) & (x > 5) & (x < 29)))
    bolt_pts = [(17, 16), (24, 16), (19, 26), (24, 26), (12, 39), (15, 29), (10, 29)]
    bolt = _inside(x, y, bolt_pts) & (y > 18)
    out = np.zeros((h, w), np.uint8)
    out[_outline(cloud | bolt)] = 1
    out[cloud] = 2
    out[cloud & (y > 15)] = 3
    out[bolt] = 4
    out[bolt & _inside(x + 1.2, y, bolt_pts) & _inside(x - 1.2, y, bolt_pts)] = 5
    return out


def caption_glyphs() -> dict[str, tuple[str, ...]]:
    """dirgfx's caption letters with W, A and H added in their style (15 px, 3-px strokes)."""
    extra = {"W": ("###...###",) * 7 + ("###.#.###", "###.#.###", "#########", "#########", "####.####", "###...###", "##.....##",
                                         "#.......#"),
             "A": (".######.", "########", "########", "###..###", "###..###", "###..###", "########", "########", "########")
                  + ("###..###",) * 6,
             "H": ("###..###",) * 6 + ("########",) * 3 + ("###..###",) * 6}
    return {**dirgfx.GLYPHS, **extra}


def caption_bitmap() -> np.ndarray:
    """The SELECT WEATHER strip in dirgfx's caption style (dirgfx.caption_bitmap with CAPTION)."""
    glyphs = caption_glyphs()
    h, w = 8 * dirgfx.CAPTION_SIZE[0], 8 * dirgfx.CAPTION_SIZE[1]
    img = np.full((h, w), dirgfx.CAPTION_PAPER, np.uint8)
    words = [[np.array([[c == "#" for c in row] for row in glyphs[ch]]) for ch in word] for word in CAPTION.split(" ")]
    width = (sum(g.shape[1] for word in words for g in word) + dirgfx.LETTER_GAP * sum(len(word) - 1 for word in words)
             + dirgfx.WORD_GAP * (len(words) - 1))
    x = (w - width) // 2
    for word in words:
        for j, g in enumerate(word):
            img[dirgfx.LETTER_TOP:dirgfx.LETTER_TOP + dirgfx.LETTER_HEIGHT, x:x + g.shape[1]][g] = dirgfx.CAPTION_INK
            x += g.shape[1] + (dirgfx.LETTER_GAP if j < len(word) - 1 else 0)
        x += dirgfx.WORD_GAP
    return img


def badge_tiles():
    """(map, characters, 16-word palette) of a converted course's badge: its own block (BADGE_BLOCKS[0]) on layer 0 over the
    picture, its transparent cells left out (dirgfx.EMPTY)."""
    m, chars = dirgfx._tiles(badge_bitmap(), empty_shared=False)
    pal = [0] * 16
    for k, c in BADGE_RGB.items():
        pal[k] = rgb_word(c)
    return m, chars, pal


# ---- reading the set -------------------------------------------------------------------------------------------------------
def _read(rs: RomSet, addr: int, n: int) -> bytes:
    """`n` bytes at a V60 address of the boot ROM, the program ROM or data bank 0 (mapped at 0x100000 on the select screens)."""
    if addr >= V60_BOOT:
        return rs.boot[addr - V60_BOOT:addr - V60_BOOT + n]
    if addr >= V60_PROGRAM:
        return rs.program[addr - V60_PROGRAM:addr - V60_PROGRAM + n]
    return rs.data[addr - 0x100000:addr - 0x100000 + n]


def _u16s(rs: RomSet, addr: int, n: int) -> list[int]:
    return list(struct.unpack(f"<{n}H", _read(rs, addr, 2 * n)))


def _u32(rs: RomSet, addr: int) -> int:
    return struct.unpack("<I", _read(rs, addr, 4))[0]


def char_address(code: int) -> int:
    return dirgfx.CHAR_RAM + dirgfx.CHAR_BYTES * code


def original_badge(rs: RomSet, art: int, b_normal: list[int], b_grey: list[int]):
    """An original's badge composed over its B map in the RAIN slot (B is on layer 0, the badge's only plane), as origpic composes
    the arrows: the badge cells' keys (badge colour or B's normal / grey word) parted into palette groups (origpic._partition), each
    group's characters and its two looks (normal, grey), and the badge rectangle's tile words (a badge cell: (group, local
    character); another: B's own word in the slot). (rows, cols, chars, looks, words)."""
    from vrtools.arcade.origpic import _partition, layers
    ly = layers(rs, art)
    bm = badge_bitmap()
    rows, cols = bm.shape[0] // 8, bm.shape[1] // 8
    cells = {}
    for r in range(rows):
        for c in range(cols):
            t = bm[8 * r:8 * r + 8, 8 * c:8 * c + 8]
            if not t.any():
                continue
            cell = (BADGE_CELL[0] + r) * 16 + BADGE_CELL[1] + c
            bpx, pal = ly.b_pixels[cell], ly.b_local[cell] >> 7
            keys = np.empty((8, 8), object)
            for yy in range(8):
                for xx in range(8):
                    if t[yy, xx]:
                        w = rgb_word(BADGE_RGB[int(t[yy, xx])])
                        keys[yy, xx] = (w, grey_word(w))
                    elif bpx[yy, xx]:
                        keys[yy, xx] = (b_normal[16 * pal + int(bpx[yy, xx])], b_grey[16 * pal + int(bpx[yy, xx])])
                    else:
                        keys[yy, xx] = None
            cells[(r, c)] = keys
    groups = _partition([frozenset(k for k in keys.flat if k is not None) for keys in cells.values()])
    chars = [[] for _ in groups]
    seen = [{} for _ in groups]
    words = []
    for r in range(rows):
        for c in range(cols):
            cell = (BADGE_CELL[0] + r) * 16 + BADGE_CELL[1] + c
            if (r, c) not in cells:
                words.append((0x8000 | SLOT_CHAR[SLOTS[1]]) + ly.b_local[cell])
                continue
            keys = cells[(r, c)]
            need = {k for k in keys.flat if k is not None}
            g = next(i for i, grp in enumerate(groups) if need <= set(grp))
            index = {k: 1 + n for n, k in enumerate(groups[g])}
            t = np.array([[index[keys[yy, xx]] if keys[yy, xx] is not None else 0 for xx in range(8)] for yy in range(8)], np.uint8)
            b = dirgfx.char_bytes(t)
            if b not in seen[g]:
                seen[g][b] = len(chars[g])
                chars[g].append(b)
            words.append((g, seen[g][b]))
    if len(groups) > len(BADGE_BLOCKS) or any(len(c) > dirgfx.BLOCK_CHARS for c in chars):
        raise PatchError(f"art {art}: the badge needs {len(groups)} palettes ({[len(c) for c in chars]} characters)")
    looks = [{look: [0] + [k[i] for k in grp] + [0] * (15 - len(grp)) for i, look in enumerate(("normal", "grey"))} for grp in groups]
    return rows, cols, chars, looks, words


# ---- the data: one "piece" per entry kind (the seven converted share one; each original its own) ----------------------------
@dataclass
class Blob:
    name: str
    size: int
    build: object               # {blob name: address} -> bytes (its size never depends on the addresses)


def _rows(rows) -> bytes:
    """A row list: (source, destination, count) rows (count 0: a blit by 0xff9436, else longwords), ended by a zero word."""
    return b"".join(struct.pack("<III", *r) for r in rows) + bytes(4)


def _piece(base: int, phase_rows, look_rows, header) -> bytes:
    """A piece at `base`: 8 list pointers (the PHASES' 4 lists, then LOOK_LISTS looks: choosing DRY, choosing RAIN, locked DRY,
    locked RAIN), 8 header words (+32: the two choices' picture cells, an original's A palettes' address (0 on a converted course),
    0, the A map's character delta, the RAIN side's A cell, 0, 0), then the lists."""
    assert len(phase_rows) == len(PHASES) and len(look_rows) == LOOK_LISTS
    head = bytearray(PIECE_HEAD)
    body = b""
    for k, lst in enumerate([_rows(r) for r in phase_rows] + [_rows(r) for r in look_rows]):
        struct.pack_into("<I", head, 4 * k, base + PIECE_HEAD + len(body))
        body += lst
    struct.pack_into("<8I", head, 32, *header)
    return bytes(head) + body


def _map_words(words, rows: int, cols: int) -> bytes:
    return struct.pack("<HHII", 0, 1, rows, cols) + struct.pack(f"<{len(words)}H", *words)


def build_data(rs: RomSet, lay: dict[str, int]) -> tuple[dict[str, Blob], list[str], list[str]]:
    """The blobs by name, and per menu entry the name of its weather piece and of its direction-look piece."""
    from vrtools.arcade import tencourse
    from vrtools.arcade.origpic import ORIGINALS_BELOW, picture_data, table_address
    from vrtools.arcade.panel import ORIGINAL_PANELS, decode_panel, select_palette
    from vrtools.arcade.picture import START_TABLES, _boot_u32
    blobs: dict[str, Blob] = {}

    def add(name, build):
        blobs[name] = Blob(name, len(build({})), build)
    cmap, cchars = dirgfx._tiles(caption_bitmap(), empty_shared=True)
    add("caption_chars", lambda at: b"".join(cchars))
    add("caption_map", lambda at: dirgfx.map_blob(cmap, CAPTION_BLOCK))
    bmap, bchars, bpal = badge_tiles()
    bgrey = [grey_word(w) if w else 0 for w in bpal]
    bmap_blob = dirgfx.map_blob(bmap, BADGE_BLOCKS[0])
    add("cbadge", lambda at: b"".join(bchars) + bmap_blob + struct.pack("<16H", *bpal) + struct.pack("<16H", *bgrey))
    nchars, nmap = dirgfx.CHAR_BYTES * len(bchars), len(bmap_blob)
    badge_cell = tile_address(0, PIC_ROW + BADGE_CELL[0], PIC_COLS[1] + BADGE_CELL[1])
    badge_pal = dirgfx.palette_address(BADGE_BLOCKS[0])

    def panel_rows(at):
        """Phase 0xff's rows: the game's maps, then the caption's characters, the panel's palette for them and the caption's map."""
        return [(DOUBLE_ARROW, tile_address(0, *DOUBLE_ARROW_CELL), 0), (WHEEL_PANEL, tile_address(0, PANEL_ROW, 7), 0),
                (RED_ARROW, tile_address(0, PANEL_ROW + 2, 28), 0), (STEP_PANEL, tile_address(0, PANEL_ROW, 35), 0),
                (at.get("caption_chars", 0), char_address(CAPTION_BLOCK), len(cchars) * 8),
                (dirgfx.palette_address(dirgfx.PANEL_PALETTE << 7), dirgfx.palette_address(CAPTION_BLOCK), 8),
                (at.get("caption_map", 0), tile_address(0, *CAPTION_CELL), 0)]

    def conv_piece(at):
        o = at.get("cbadge", 0)
        normal, grey = (o + nchars + nmap, badge_pal, 8), (o + nchars + nmap + 32, badge_pal, 8)
        phases = [panel_rows(at), [], [], [(o, char_address(BADGE_BLOCKS[0]), nchars // 4), normal, (o + nchars, badge_cell, 0)]]
        return _piece(at.get("piece_conv", 0), phases, [[grey], [normal], [grey], [normal]],
                      (tile_address(2, PIC_ROW, PIC_COLS[0]), tile_address(2, PIC_ROW, PIC_COLS[1]), 0, 0, 0, 0, 0, 0))
    add("piece_conv", conv_piece)
    pieces = ["piece_conv"] * 10
    sp = select_palette(rs)
    pictures = [_u32(rs, lay["pictures"] + 4 * k) for k in range(10)]
    a_dst = [0x900000 + 32 * (A_HOME[k] >> 7) for k in range(ORIGINALS)]
    a_src = [sp["ptr"] + 8 + (a_dst[k] - sp["dst"]) for k in range(ORIGINALS)]     # each art's A palettes, normal (bank 0)
    starts = [{k: _boot_u32(rs, ad + 4 * art) for k, ad in START_TABLES.items()} for art in range(ORIGINALS)]
    for art in range(ORIGINALS):
        if pictures[art] == 0:
            continue
        if starts[art]["a_dst"] != a_dst[art]:
            raise PatchError(f"art {art}: its A palettes are at {starts[art]['a_dst']:#x}")
        b_normal = _u16s(rs, _u32(rs, pictures[art] + REC["normal"]), 48)
        b_grey = _u16s(rs, _u32(rs, pictures[art] + REC["grey"]), 48)
        nxt = (art + 1) % ORIGINALS
        a_chars = max(decode_panel(rs, ORIGINAL_PANELS[art][0]).tiles) + 1
        rows, cols, chars, looks, words = original_badge(rs, art, b_normal, b_grey)
        add(f"obadge{art}", lambda at, chars=chars, looks=looks: b"".join(b"".join(g) for g in chars)
            + b"".join(struct.pack("<16H", *lk["normal"]) + struct.pack("<16H", *lk["grey"]) for lk in looks))
        ws = [w if isinstance(w, int) else (0x8000 | BADGE_BLOCKS[w[0]]) + w[1] for w in words]
        add(f"omap{art}", lambda at, ws=ws, rows=rows, cols=cols: _map_words(ws, rows, cols))

        def orig_piece(at, art=art, chars=chars, looks=looks, nxt=nxt, a_chars=a_chars):
            t = starts[art]
            o = at.get(f"obadge{art}", 0)
            badge_rows, greys, normals = [], [], []
            for g, blk in zip(chars, BADGE_BLOCKS):
                badge_rows.append((o, char_address(blk), 8 * len(g)))
                o += dirgfx.CHAR_BYTES * len(g)
            for lk, blk in zip(looks, BADGE_BLOCKS):
                badge_rows.append((o, dirgfx.palette_address(blk), 8))
                normals.append((o, dirgfx.palette_address(blk), 8))
                greys.append((o + 32, dirgfx.palette_address(blk), 8))
                o += 64
            badge_rows.append((at.get(f"omap{art}", 0), badge_cell, 0))
            cell_a = lambda k: tile_address(2, PIC_ROW, PIC_COLS[k])
            phases = [panel_rows(at),
                      [(a_src[art], a_dst[art], 16), (ORIGINAL_PANELS[art][0], cell_a(0), 0)],
                      [(char_address(A_HOME[art]), char_address(A_HOME[nxt]), 8 * a_chars), (ORIGINAL_PANELS[art][0], cell_a(1), 0),
                       (a_src[art], a_dst[nxt], 16)],
                      badge_rows]
            looks_ = [[(a_src[art], a_dst[art], 16), (t["a_grey"], a_dst[nxt], 16)] + greys,          # choosing DRY
                      [(t["a_grey"], a_dst[art], 16), (a_src[art], a_dst[nxt], 16)] + normals,        # choosing RAIN
                      [(t["a_chosen"], a_dst[art], 16), (t["a_grey"], a_dst[nxt], 16)] + greys,       # locked DRY
                      [(t["a_grey"], a_dst[art], 16), (t["a_chosen"], a_dst[nxt], 16)] + normals]     # locked RAIN
            delta = (A_HOME[nxt] - A_HOME[art]) & 0xFFFFFFFF
            return _piece(at.get(f"piece{art}", 0), phases, looks_,
                          (tile_address(0, PIC_ROW, PIC_COLS[0]), tile_address(0, PIC_ROW, PIC_COLS[1]), a_dst[art], 0, delta,
                           cell_a(1), 0, 0))
        add(f"piece{art}", orig_piece)
        pieces[art] = f"piece{art}"
    # COURSE DIRECTION's looks (wxdlook reads the look lists only: choosing NORMAL, choosing REVERSE, locked NORMAL, locked REVERSE).
    # A converted course: nothing beyond the B palettes (the arrows keep their colours, as main's lock look); its piece's eight
    # pointers all name one empty list. An original: its A palettes (left on its own A home, right on the next art's) and its
    # arrows' ring palettes, the side shown normal and the other grey; locked: origpic's own lock lists.
    tab = table_address(tencourse.origpic_address())
    addrs = struct.unpack_from(f"<{2 * ORIGINALS_BELOW}I", rs.program, tab - V60_PROGRAM)
    draw_at, lock_at = addrs[:ORIGINALS_BELOW], addrs[ORIGINALS_BELOW:]
    add("dpiece_conv", lambda at: struct.pack("<8I", *[at.get("dpiece_conv", 0) + 32] * 8) + bytes(4))
    dpieces = ["dpiece_conv"] * 10
    for art in range(ORIGINALS):
        if pictures[art] == 0:
            continue
        _, lock, info = picture_data(rs, art, draw_at[art], lock_at[art])
        if _read(rs, lock_at[art], len(lock)) != lock:
            raise PatchError(f"art {art}: origpic's lock data is not where its table says")
        sides_a = (a_dst[art], a_dst[(art + 1) % ORIGINALS])

        def dir_piece(at, art=art, info=info, sides_a=sides_a):
            lists = []
            for choice in range(2):
                rows = []
                for side in range(2):
                    rows.append((a_src[art] if side == choice else starts[art]["a_grey"], sides_a[side], 16))
                    for lk, blk in zip(info["ring"][side]["looks"], info["blocks"][side]):
                        rows.append((lk["normal" if side == choice else "grey"], dirgfx.palette_address(blk), 8))
                lists.append(_rows(rows))
            base = at.get(f"dpiece{art}", 0)
            ptrs = [base + 32] * 4 + [base + 36, base + 36 + len(lists[0]), info["lock"][0], info["lock"][1]]
            return struct.pack("<8I", *ptrs) + bytes(4) + lists[0] + lists[1]
        add(f"dpiece{art}", dir_piece)
        dpieces[art] = f"dpiece{art}"
    return blobs, pieces, dpieces


# ---- the code ------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Inputs:
    """What the routines call or read beyond the directory's layout: origpic's row interpreter `orows` and handler `osel`, the
    HUD site's own callee `hudorig`, and per menu entry the address of its weather piece and of its direction-look piece."""
    orows: int
    osel: int
    hudorig: int
    pieces: tuple[int, ...] = field(default=(0,) * 10)
    dpieces: tuple[int, ...] = field(default=(0,) * 10)

    @staticmethod
    def placeholder() -> "Inputs":
        """Stand-in addresses of the real length, for sizing."""
        return Inputs(0x100000, 0x100000, 0x100000)


def _text(tune: ScreenTune) -> bytes:
    """"wxtext": the title NUL-ended, then the two labels, each NUL-padded to LABEL_SLOT bytes."""
    return TITLE.encode() + b"\0" + b"".join(c.encode().ljust(LABEL_SLOT, b"\0") for c in ("DRY", tune.rain_word))


def routines(base: int, lay: dict[str, int], inputs: Inputs, tune: ScreenTune = ScreenTune()) -> dict[str, bytes]:
    """The routines and tables (ROUTINES, then TABLES) at `base`, in ROM order. `lay`: the directory's layout and this code's own
    (`code_layout`; addresses not laid out yet read as 0x100000, which assembles to the same length)."""
    out: dict[str, bytes] = {}
    at = lambda name: lay.get(name, 0x100000)
    here = lambda: base + sum(len(c) for c in out.values())
    choices = ("DRY", tune.rain_word)
    label_text = at("wxtext") + len(TITLE) + 1

    def saved_call(b: Block, r13: int, target: str):
        """A look routine called with R13 (0 choosing, 2 locked), the drawing registers saved round it."""
        b.emit("pushm imm", DRAW_SAVED)
        b.emit("mov.w imm,reg", r13, "r13")
        b.emit("jsr abs", at(target))
        b.emit("popm imm", DRAW_SAVED)

    # wxsel: the select entity's handler from the direction lock to the weather lock ------------------------------------------
    b = Block(here())
    b.emit("cmp.b imm,abs", DIRECTION_LOCKED, DIR_PHASE)    # the direction lock's first pass here: its lock look, the hold
    b.branch("bne", "hold")
    b.emit("mov.b imm,abs", HOLDING, DIR_PHASE)
    b.emit("mov.b imm,abs", tune.hold_frames, DIR_ARMED)
    b.emit("cmp.w imm,abs", LOCK_TIMER + tune.hold_frames, TIMER)    # the game's countdown must not lock during the hold
    b.branch("bge", "timer_ok")
    b.emit("mov.w imm,abs", LOCK_TIMER + tune.hold_frames, TIMER)
    b.label("timer_ok")
    saved_call(b, 2, "wxdlook")                              # the direction's lock look: the chosen side in colour, the other grey
    b.emit("jsr abs", lay["dircursor"])
    b.emit("rsr")
    b.label("hold")
    b.emit("cmp.b imm,abs", HOLDING, DIR_PHASE)
    b.branch("bne", "weather")
    b.emit("jsr abs", lay["dircursor"])                     # the direction's frame on its choice
    b.emit("movz.bw abs,reg", DIR_ARMED, "r10")
    b.emit("sub.w imm,reg", 1, "r10")
    b.emit("mov.b reg,abs", "r10", DIR_ARMED)
    b.branch("be", "open")
    b.emit("rsr")
    b.label("open")                                          # the hold is over: the weather screen opens
    b.emit("mov.b imm,abs", OPEN, DIR_PHASE)
    b.emit("mov.b imm,abs", 0, DIR_ARMED)
    b.emit("mov.b imm,abs", 0xFF, DIR_SHOWN)
    b.emit("mov.w imm,abs", tune.timer, TIMER)
    b.emit("mov.w imm,reg", FIRST_WAIT, "r10")              # the video frame's end passes before the first clear
    b.label("wait")
    b.emit("sub.w imm,reg", 1, "r10")
    b.branch("bne", "wait")
    b.label("weather")
    b.emit("cmp.b imm,abs", DRAWN, DIR_SHOWN)
    b.branch("bnh", "drawn")
    b.emit("jsr abs", at("wxdraw"))
    b.emit("rsr")
    b.label("drawn")
    b.emit("mov.w abs,reg", WHEEL, "r10")                   # R10: the wheel, as dirsel reads it
    b.emit("add.w abs,reg", WHEEL_PREV, "r10")
    b.emit("sha.w imm,reg", -1, "r10")
    b.emit("cmp.w imm,reg", THRESHOLD, "r10")
    b.branch("bgt", "armed")
    b.emit("mov.b imm,abs", 1, DIR_ARMED)
    b.label("armed")
    b.emit("mov.w imm,reg", 0, "r11")                       # R11: the choice
    b.emit("cmp.b imm,abs", 0, DIR_ARMED)
    b.branch("be", "chosen")
    b.emit("mov.w imm,reg", THRESHOLD + HYSTERESIS, "r13")  # from DRY (or the first pass) RAIN needs more than THRESHOLD + 4 ...
    b.emit("cmp.b imm,abs", 1, DIR_SHOWN)
    b.branch("bne", "compare")
    b.emit("mov.w imm,reg", THRESHOLD - HYSTERESIS, "r13")  # ... from RAIN, DRY needs THRESHOLD - 4 or less
    b.label("compare")
    b.emit("cmp.w reg,reg", "r13", "r10")
    b.branch("ble", "chosen")
    b.emit("mov.w imm,reg", 1, "r11")
    b.label("chosen")
    b.emit("cmp.b reg,abs", "r11", DIR_SHOWN)
    b.branch("be", "shown")
    b.emit("mov.b reg,abs", "r11", DIR_SHOWN)
    b.emit("jsr abs", at("wxshow"))                         # the labels
    saved_call(b, 0, "wxlook")                              # the pictures: the choice in full colour, the other grey
    b.label("shown")
    b.emit("jsr abs", at("wxcursor"))
    b.emit("cmp.w imm,abs", 0, EDGE)
    b.branch("bne", "lock")
    b.emit("cmp.w imm,abs", LOCK_TIMER, TIMER)
    b.branch("bgt", "done")
    b.label("lock")
    b.emit("mov.b abs,abs", DIR_SHOWN, WEATHER_BYTE)
    b.emit("mov.b imm,abs", LOCKED, DIR_PHASE)
    saved_call(b, 2, "wxlook")                              # the lock look
    b.emit("mov.w imm,disp[reg]", COURSE_LOCK, HANDLER, "r25")
    b.label("done")
    b.emit("rsr")
    out["wxsel"] = b.bytes()

    # wxdraw: one drawing phase (DIR_SHOWN), then DIR_SHOWN - 1 -----------------------------------------------------------------
    b = Block(here())

    def piece_r8():
        b.emit("movz.bw abs,reg", MENU_INDEX, "r8")
        b.emit("mov.w abs(reg),reg", at("wxpieces"), "r8", "r8")
    b.emit("pushm imm", DRAW_SAVED)
    b.emit("cmp.b imm,abs", PHASES[0], DIR_SHOWN)
    b.branch("bne", "pictures")
    b.emit("mov.w imm,reg", tile_address(0, 0, 0), "r0")
    b.emit("jsr abs", CLEAR_LAYER)
    b.emit("jsr abs", CHECKER)
    b.emit("mov.w imm,reg", at("wxtext"), "r0")
    b.emit("mov.w imm,reg", tile_address(0, *TITLE_CELL), "r1")
    b.emit("jsr abs", TITLE_PRINT)
    b.emit("jsr abs", at("wxshow"))
    b.branch("br", "rows")
    b.label("pictures")
    b.emit("cmp.b imm,abs", PHASES[-1], DIR_SHOWN)
    b.branch("be", "rows")
    piece_r8()
    b.emit("movz.bw abs,reg", DIR_SHOWN, "r0")
    b.emit("mov.w imm,reg", PHASES[1], "r9")
    b.emit("sub.w reg,reg", "r0", "r9")                      # the choice k: 0xfe - DIR_SHOWN
    b.emit("mov.w reg,reg", "r9", "r10")
    b.emit("add.w reg,reg", "r9", "r10")                     # its slot: 2k
    b.emit("movz.bw abs,reg", MENU_INDEX, "r11")
    b.emit("mov.w abs(reg),reg", lay["pictures"], "r11", "r11")
    b.emit("cmp.w imm,reg", 0, "r11")
    b.branch("be", "rows")
    b.emit("mov.w reg,reg", "r9", "r12")
    b.emit("shl.w imm,reg", 2, "r12")
    b.emit("add.w reg,reg", "r8", "r12")
    b.emit("mov.w disp[reg],reg", 32, "r12", "r12")         # the choice's picture cell (header word k)
    b.emit("mov.w abs(reg),reg", lay["slot_tile"], "r10", "r13")
    b.emit("jsr abs", lay["picture"])
    b.label("rows")
    piece_r8()
    b.emit("mov.w imm,reg", PHASES[0], "r9")
    b.emit("movz.bw abs,reg", DIR_SHOWN, "r0")
    b.emit("sub.w reg,reg", "r0", "r9")
    b.emit("shl.w imm,reg", 2, "r9")
    b.emit("add.w reg,reg", "r8", "r9")
    b.emit("mov.w [reg],reg", "r9", "r9")
    b.emit("jsr abs", inputs.orows)
    b.emit("cmp.b imm,abs", PHASES[2], DIR_SHOWN)           # an original's A map on the RAIN side, blitted on its own art's
    b.branch("bne", "step")                                 # characters by the rows: moved onto the copy's
    b.emit("mov.w disp[reg],reg", 40, "r8", "r0")
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("be", "step")
    b.emit("mov.w disp[reg],reg", 48, "r8", "r2")
    b.emit("mov.w disp[reg],reg", 52, "r8", "r1")
    b.emit("mov.w imm,reg", PICTURE_SIZE[0], "r3")
    b.label("a_row")
    b.emit("mov.w imm,reg", PICTURE_SIZE[1], "r9")
    b.label("a_cell")
    b.emit("movz.hw [reg],reg", "r1", "r0")
    b.emit("add.w reg,reg", "r2", "r0")
    b.emit("mov.h reg,[reg]", "r0", "r1")
    b.emit("add.w imm,reg", 2, "r1")
    b.emit("sub.w imm,reg", 1, "r9")
    b.branch("bne", "a_cell")
    b.emit("add.w imm,reg", 0x80 - 2 * PICTURE_SIZE[1], "r1")
    b.emit("sub.w imm,reg", 1, "r3")
    b.branch("bne", "a_row")
    b.label("step")
    b.emit("movz.bw abs,reg", DIR_SHOWN, "r0")
    b.emit("sub.w imm,reg", 1, "r0")
    b.emit("mov.b reg,abs", "r0", DIR_SHOWN)
    b.emit("popm imm", DRAW_SAVED)
    b.emit("rsr")
    out["wxdraw"] = b.bytes()

    # wxshow: the two labels, the one DIR_SHOWN names in yellow -----------------------------------------------------------------
    b = Block(here())
    b.emit("mov.w imm,reg", tile_address(0, LABEL_ROW, LABEL_COLS[0]), "r12")
    b.emit("mov.w imm,reg", label_text, "r13")
    b.emit("mov.w imm,reg", 0, "r14")
    b.label("label")
    b.emit("mov.h imm,reg", LABEL_WHITE, "r0")
    b.emit("cmp.b reg,abs", "r14", DIR_SHOWN)
    b.branch("bne", "white")
    b.emit("mov.h imm,reg", LABEL_YELLOW, "r0")
    b.label("white")
    b.emit("push reg", "r0")
    b.emit("push reg", "r12")
    b.emit("push reg", "r13")
    b.raw(STRING_CALL)
    b.emit("add.w imm,reg", 2 * (LABEL_COLS[1] - LABEL_COLS[0]), "r12")
    b.emit("add.w imm,reg", LABEL_SLOT, "r13")
    b.emit("add.w imm,reg", 1, "r14")
    b.emit("cmp.w imm,reg", len(choices), "r14")
    b.branch("bne", "label")
    b.emit("rsr")
    out["wxshow"] = b.bytes()

    def look(table: str) -> bytes:
        """wxlook / wxdlook: R13 0 choosing, 2 locked; DIR_SHOWN the choice. The B palettes (as COURSE DIRECTION's): the side shown
        in the record's normal set (locked: its chosen set, the course select's highlight), the other in its grey set; then the
        piece's look list (an original's A palettes, the badge's or the ring's). Writes R0, R8-R14 (the callers save R1-R3, R7-R9)."""
        b = Block(here())
        b.emit("movz.bw abs,reg", MENU_INDEX, "r11")
        b.emit("mov.w abs(reg),reg", lay["pictures"], "r11", "r11")
        b.emit("cmp.w imm,reg", 0, "r11")
        b.branch("be", "list")
        b.emit("mov.w imm,reg", 0, "r10")                   # the side k, its slot 2k
        b.label("side")
        b.emit("movz.bw imm,reg", REC["grey"], "r12")
        b.emit("cmp.b reg,abs", "r10", DIR_SHOWN)
        b.branch("bne", "pick")
        b.emit("movz.bw imm,reg", REC["normal"], "r12")
        b.emit("cmp.w imm,reg", 0, "r13")
        b.branch("be", "pick")
        b.emit("movz.bw imm,reg", REC["chosen"], "r12")
        b.label("pick")
        b.emit("add.w reg,reg", "r11", "r12")
        b.emit("mov.w [reg],reg", "r12", "r12")
        b.emit("mov.w reg,reg", "r10", "r9")
        b.emit("add.w reg,reg", "r10", "r9")
        b.emit("mov.w abs(reg),reg", lay["slot_pal"], "r9", "r0")
        b.emit("movz.bw imm,reg", 48, "r14")
        b.label("copy")
        b.emit("mov.h [reg],[reg]", "r12", "r0")
        b.emit("add.w imm,reg", 2, "r12")
        b.emit("add.w imm,reg", 2, "r0")
        b.emit("sub.w imm,reg", 1, "r14")
        b.branch("bne", "copy")
        b.emit("add.w imm,reg", 1, "r10")
        b.emit("cmp.w imm,reg", 2, "r10")
        b.branch("bne", "side")
        b.label("list")
        b.emit("movz.bw abs,reg", MENU_INDEX, "r8")
        b.emit("mov.w abs(reg),reg", at(table), "r8", "r8")
        b.emit("movz.bw abs,reg", DIR_SHOWN, "r9")
        b.emit("add.w reg,reg", "r13", "r9")
        b.emit("shl.w imm,reg", 2, "r9")
        b.emit("add.w reg,reg", "r8", "r9")
        b.emit("mov.w disp[reg],reg", 4 * len(PHASES), "r9", "r9")
        b.emit("jsr abs", inputs.orows)
        b.emit("rsr")
        return b.bytes()
    out["wxlook"] = look("wxpieces")

    # wxdir: the handler while COURSE DIRECTION is open (olock installs it): the screen's own, then the choosing look ------------
    b = Block(here())
    b.emit("cmp.b imm,abs", ORIGINALS, MENU_INDEX)
    b.branch("bge", "converted")
    b.emit("jsr abs", inputs.osel)
    b.branch("br", "after")
    b.label("converted")
    b.emit("jsr abs", lay["dirsel"])
    b.label("after")
    b.emit("cmp.b imm,abs", 1, DIR_PHASE)
    b.branch("bne", "out")
    b.emit("cmp.b imm,abs", 1, DIR_SHOWN)
    b.branch("bh", "out")
    saved_call(b, 0, "wxdlook")
    b.label("out")
    b.emit("rsr")
    out["wxdir"] = b.bytes()
    out["wxdlook"] = look("wxdpieces")

    # wxcursor: the game's cursor frame at "wxsides"[DIR_SHOWN] (dircursor's shim) ------------------------------------------------
    b = Block(here())
    b.emit("mov.w imm,reg", 3, "r0")
    b.emit("jsr abs", OBJECT_NEW)
    b.emit("mov.w imm,disp[reg]", CURSOR_OBJECT, 0xE, "r25")
    b.emit("movz.bw abs,reg", DIR_SHOWN, "r13")
    b.emit("shl.w imm,reg", 3, "r13")
    b.emit("add.w imm,reg", at("wxsides"), "r13")
    b.emit("jmp abs", CURSOR_BODY)
    out["wxcursor"] = b.bytes()

    # wxdone (from `start`): after a weather lock the steady frame on the choice, else dirdone --------------------------------------
    b = Block(here())
    b.emit("cmp.b imm,abs", LOCKED, DIR_PHASE)
    b.branch("be", "weather")
    b.emit("jmp abs", lay["dirdone"])
    b.label("weather")
    b.emit("jmp abs", at("wxcursor"))
    out["wxdone"] = b.bytes()

    # wxgate (RANK_SITE): no record while the weather is not DRY ------------------------------------------------------------------
    b = Block(here())
    b.emit("movz.bw imm,abs", 0, RECORD_FLAG)
    b.emit("cmp.b imm,abs", 0, WEATHER_BYTE)
    b.branch("be", "dry")
    b.emit("cmp.b abs,abs", WEATHER_BYTE, WEATHER_BYTE)     # Z set: the site's following `be FC417C` skips the record
    b.emit("rsr")
    b.label("dry")
    b.raw(TEST1_RACE_FINISHED)                              # the site's own test, absolute
    b.emit("rsr")
    out["wxgate"] = b.bytes()

    # hudwx (HUD_SITE): hudorig, then in a RAIN race the word in white on rows 46-47 ----------------------------------------------
    b = Block(here())
    word = tune.rain_word
    b.emit("jsr abs", inputs.hudorig)
    b.emit("cmp.b imm,abs", 0, WEATHER_BYTE)
    b.branch("be", "out")
    b.emit("mov.w abs,reg", HUD_ATTR, "r2")
    b.emit("push reg", "r2")
    b.emit("mov.w imm,abs", HUD_WHITE, HUD_ATTR)
    b.emit("mov.w imm,reg", label_text + LABEL_SLOT, "r0")
    b.emit("mov.w imm,reg", tile_address(0, 46, 59 - len(word)), "r1")     # the last letter in column 58
    b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)
    b.branch("be", "print")
    b.emit("mov.w imm,reg", tile_address(0, 46, 51 - len(word)), "r1")     # the last letter in column 50, REVERSE from 52
    b.emit("cmp.b imm,abs", 1, MENU_INDEX)
    b.branch("blt", "print")
    b.emit("cmp.b imm,abs", ORIGINALS, MENU_INDEX)
    b.branch("bge", "print")
    b.emit("sub.w imm,reg", 2, "r1")                        # Bay Bridge and Acropolis: REVERSE from 51
    b.label("print")
    b.emit("jsr abs", HUD_PRINTER)
    b.emit("pop reg", "r2")
    b.emit("mov.w reg,abs", "r2", HUD_ATTR)
    b.label("out")
    b.emit("rsr")
    out["hudwx"] = b.bytes() + bytes((-(here() + len(b.bytes()))) % 4)    # the tables after it 4-aligned

    out["wxsides"] = b"".join(struct.pack("<2f", *s) for s in SIDES)
    t = _text(tune)
    out["wxtext"] = t + bytes((-len(t)) % 4)
    out["wxpieces"] = struct.pack("<10I", *inputs.pieces)
    out["wxdpieces"] = struct.pack("<10I", *inputs.dpieces)
    assert tuple(out) == ROUTINES + TABLES
    return out


def code_layout(base: int, lay: dict[str, int], inputs: Inputs, tune: ScreenTune = ScreenTune()) -> dict[str, int]:
    """Each routine's and table's address at `base`, and "end", settled (a branch's length can follow an address)."""
    mine: dict[str, int] = {}
    for _ in range(4):
        addrs, a = {}, base
        for name, code in routines(base, {**lay, **mine}, inputs, tune).items():
            addrs[name] = a
            a += len(code)
        addrs["end"] = a
        if addrs == mine:
            return mine
        mine = addrs
    raise PatchError("the weather screen's code layout does not settle")


# ---- installation ----------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Site:
    """An in-place change: `old` at `addr` (checked first) becomes `new(addresses)`, the same length."""
    name: str
    space: str                  # "program" or "boot"
    addr: int
    old: bytes
    new: object


def sites(rs: RomSet, lay: dict[str, int]) -> tuple[list[Site], int, int, int]:
    """The in-place changes at the addresses weather/layout.py gives them, each checked on `rs` before anything is written (the
    bytes there what main leaves: PatchError naming the site otherwise), and the three addresses read from the set: origpic's
    `orows` and `osel`, and the HUD site's callee `hudorig`."""
    from vrtools.arcade import tencourse
    from vrtools.arcade.origpic import origpic_layout
    from vrtools.arcade.weather import layout
    ol = origpic_layout(tencourse.origpic_address(), lay)
    at = {b.name: b for b in layout.blocks() if b.space.endswith(" site") and b.owner == "screen"}
    hud_site = at["the HUD's call"]
    hud = rs.boot[hud_site.start - V60_BOOT:hud_site.start - V60_BOOT + hud_site.size]
    if hud[:2] != asm("jsr abs", 0)[:2]:
        raise PatchError(f"the HUD site {hud_site.start:#x} is not a jsr abs: {hud.hex()}")
    hudorig = struct.unpack_from("<I", hud, 2)[0]

    def call(name, target):
        b = Block(at[name].start)
        b.emit("jsr abs", target)
        return b.bytes() + asm("nop") * (at[name].size - len(b.bytes()))
    handler = lambda target: asm("mov.w imm,disp[reg]", target, HANDLER, "r25")
    expect = {"dirsel's lock": (handler(COURSE_LOCK), lambda L: handler(L["wxsel"])),
              "start's jmp dirdone": (asm("jmp abs", lay["dirdone"]), lambda L: asm("jmp abs", L["wxdone"])),
              "bankdemo's clear": (asm("mov.b imm,abs", 0, DIRECTION_RAM), lambda L: asm("mov.w imm,abs", 0, DIRECTION_RAM)),
              "olock's original handler": (handler(ol["osel"]), lambda L: handler(L["wxdir"])),
              "olock's converted handler": (handler(lay["dirsel"]), lambda L: handler(L["wxdir"])),
              "the race end's record test": (RANK_PATTERN, lambda L: call("the race end's record test", L["wxgate"])),
              "the HUD's call": (hud, lambda L: call("the HUD's call", L["hudwx"]))}
    if set(expect) != set(at):
        raise PatchError(f"the weather layout's sites {sorted(at)} are not the screen's {sorted(expect)}")
    out = []
    for name, (old, new) in expect.items():
        b = at[name]
        space, region, base = ("program", rs.program, V60_PROGRAM) if b.space == "program site" else ("boot", rs.boot, V60_BOOT)
        have = region[b.start - base:b.start - base + b.size]
        if have != old:
            raise PatchError(f"{name} at {b.start:#x}: {have.hex()}, expected {old.hex()}")
        out.append(Site(name, space, b.start, old, new))
    return out, ol["orows"], ol["osel"], hudorig


def _write(rs: RomSet, space: str, addr: int, data: bytes, erased: bool) -> None:
    """`data` at `addr` of the program ROM, the boot ROM or data bank 0 (window 0x100000), in place; `erased`: the bytes there must
    be 0xff."""
    region, base = {"program": ("program", V60_PROGRAM), "boot": ("boot", V60_BOOT), "bank0": ("data", 0x100000)}[space]
    buf = bytearray(getattr(rs, region))
    o = addr - base
    if not (0 <= o and o + len(data) <= len(buf)):
        raise PatchError(f"{addr:#x} (+{len(data)}) is outside the {space}")
    if erased and any(x != 0xFF for x in buf[o:o + len(data)]):
        raise PatchError(f"{space} at {addr:#x} (+{len(data)}) is not erased for the weather screen")
    buf[o:o + len(data)] = data
    object.__setattr__(rs, region, bytes(buf))


def install(rs: RomSet, tune: ScreenTune = ScreenTune()) -> dict:
    """The screen on a built set (the directory, the direction screen and origpic installed), in place, on the blocks of
    weather/layout.py (checked erased first) and the sites (checked first). Returns where everything went."""
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.weather import layout
    lay = directory_layout()
    layout.check(rs)
    site_list, orows, osel, hudorig = sites(rs, lay)
    blobs, piece_names, dpiece_names = build_data(rs, lay)
    at = layout.place({n: b.size for n, b in blobs.items()})
    images = {n: blobs[n].build(at) for n in blobs}
    for n, img in images.items():
        if len(img) != blobs[n].size:
            raise PatchError(f"the weather screen's {n}: {len(img)} bytes, sized {blobs[n].size}")
    code_block = layout.block("screen code")
    inputs = Inputs(orows, osel, hudorig, tuple(at[n] for n in piece_names), tuple(at[n] for n in dpiece_names))
    wl = code_layout(code_block.start, lay, inputs, tune)
    if wl["end"] > code_block.start + code_block.size:
        raise PatchError(f"the weather screen's code ({wl['end'] - code_block.start} bytes) does not fit its block ({code_block.size})")
    code = b"".join(routines(code_block.start, {**lay, **wl}, inputs, tune).values())
    _write(rs, "program", code_block.start, code, erased=True)
    for n, img in images.items():
        _write(rs, layout.space_of(at[n]), at[n], img, erased=True)
    L = {**lay, **wl}
    for s in site_list:
        new = s.new(L)
        if len(new) != len(s.old):
            raise PatchError(f"{s.name}: {len(new)} bytes in place of {len(s.old)}")
        _write(rs, s.space, s.addr, new, erased=False)
    return {"code": (code_block.start, len(code)), "blobs": {n: (at[n], blobs[n].size) for n in blobs}, "layout": wl,
            "sites": {s.name: s.addr for s in site_list}}
