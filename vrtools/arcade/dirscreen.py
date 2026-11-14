"""Phase 26 stage 3: the COURSE DIRECTION screen (design §2 item 3, §6.6; docs/spike/2026-11-phase26-stage3-recon.md).

Task 1 (recon §6-§8): the room for the screen's routines (they join the directory image after the direction routines, plan
D10), the direction flag's life and the ranking gate.

- The flag `course.DIRECTION_RAM` stays the byte 0x502294; the word's three other bytes are the screen's cells (plan D12):
  DIR_PHASE (0 no direction screen, 1 choosing, 2 locked), DIR_ARMED (1 once the wheel has been at or left of the threshold),
  DIR_SHOWN (the choice the labels and frame show: 0, 1, or 0xff before the first draw). Every reader and writer of the flag
  in the project uses a byte access (`cmp.b`, `mov.b`), so the cells never meet another's write.
- Whenever a select screen starts the flag and the cells are 0: mode 0x10's state 0 (STATE0_SITE, the course select's and the
  operator's SHIFT MODE SELECTOR alike, every cabinet) begins with `mov.b #0, 5019C0[PC]`, which becomes `jsr dirclear`;
  `dirclear` does that clear and clears the word. A flag left from a reverse race, or poked before the coin, never reaches a
  course select, the operator's fixed course or a linked race (recon §7: the operator's path never reaches the course lock).
- The two linked course loads among `course.BANK_SITES` (LINKED_BANK_SITES: 0xfe2b07, mode 5; 0xfe1d37, a cabinet joining a
  linked race) call `bankdemo`, as the attract's two do (`directory.ATTRACT_BANK_SITES`): `bankdemo` is `bank` with the flag
  cleared first and nothing else, so a linked load right after a reverse race serves the normal record.
- A reverse race records nothing (recon §8, plan D9): at the race's end 0xfe4b49 calls 0xfc40ce, which clears the record flag
  0x5018fc and tests bit 1 of 0x501174 (the race finished); its `be FC417C` (rsr) skips the setter, the record and the bubble,
  and with 0x5018fc 0 the name entry is skipped (0xfe4b4f, 0xfe658c). RANK_SITE's two instructions become `jsr rankgate`;
  `rankgate` clears 0x5018fc as the original, then returns with Z set while the flag is set, else with the original `test1`'s
  flags, so the `be` that follows takes the race-without-a-record path in reverse.

Both sites are entered only at their first byte: the state table's `br FE3CCE` (0xfe3cb9) and `jsr FC40CE[PC]` (0xfe4b49) are
the only branches to them in the original boot ROM's listing, and no 32-bit word of the boot or program ROM points inside them.

Task 2 (recon §1.2 option (a), §4, §5): the screen as behaviour, drawn over the course select's tiles until Tasks 3-5.
- The course lock: the gas edge (or the course select's countdown) makes 0xfc26c5 install the lock handler 0xfc277c, which on
  the next logic frame sets the timer 0x50113c to 0x20 and, at LOCK_SITE, the handler 0xfc27be (`mov.w #FC27BE, A[R25]`, 9
  bytes; entered only from 0xfc277c's first byte, reached from 0xfc2750 / 0xfc2772). LOCK_SITE becomes `jsr dirlock`. `dirlock`
  installs 0xfc27be exactly as the original in linked play (`[0x40dc8c]` != 0), on the direction lock's own pass through
  0xfc277c (DIR_PHASE != 0, below) and on an entry whose word in the reverse table (`lay["reverse"]`) is 0; otherwise it hands
  the select entity to `dirsel` with the timer at DIR_TIMER (10 s on the countdown, below 0x180 so state 1's voice cue does not
  fire again), DIR_PHASE 1, DIR_ARMED 0, DIR_SHOWN 0xff and the flag 0. 0xfc277c's own writes around the site (the timer 0x20
  before it, the cursor object's fields after it) stay.
- `dirsel` runs every logic frame from the entity dispatcher in 0xfc26c5's place: on its first frame (DIR_SHOWN 0xff) it calls
  `dirdraw`; the wheel R10 = ([0x501060] + [0x50106c]) >> 1 as 0xfc26c5 computes it (not stored: the entity keeps the course
  select's last value); plan D6: DIR_ARMED becomes 1 on a frame with R10 <= THRESHOLD, and the choice is 1 (REVERSE) only when
  armed and R10 > THRESHOLD, so doing nothing is NORMAL whatever wheel chose the course; the choice goes to DIR_SHOWN (`dirshow`
  on a change); `dircursor`; then the lock, on a gas edge (`[0x501078]` != 0: the course press's edge is one logic frame long
  and gone two frames before `dirsel` first runs, so a held pedal waits for the countdown) or with the timer at or below 0x20,
  as 0xfc26c5 locks: the flag := the choice, DIR_PHASE := 2, the handler := the game's lock handler 0xfc277c. On the next logic
  frame 0xfc277c sets the timer to 0x20 and (through `dirlock`, DIR_PHASE 2) the handler to 0xfc27be, so the direction lock
  reaches mode 0x11 in the course lock's 198 video frames (recon §1.1) and the race loads on the frame it would have after a
  course lock on the same frame. `dirsel` never touches 0x501936 (the transmission the course select latched: 0xfc26c5 writes
  it through 0xfc31e4 every frame up to the course lock, the SHIFT MODE SELECTOR's 0xfc29b3 rewrites it from the wheel).
- `start` (select.py, every logic frame while the handler is 0xfc27be) begins with a test of DIR_PHASE: non-zero, `dirdone`
  (the cursor only in this task; Task 4 adds the lock look).
- `dircursor`: the game's course cursor frame (0xfc2880) at (SIDE_X[DIR_SHOWN], SIDE_Y) through the shim of recon §4: 0xfc2887's
  first three instructions done here, R13 on a position record of the table "dirsides", `jmp FC28A7` (its `rsr` returns to
  `dircursor`'s caller). From 0xfc28a7 the game reads R13's x and y, R25, R24 and [0x501144]: blinking while the handler is not
  0xfc27be (state <= 5), steady once it is.
- `dirshow`: `rsr` only (Task 4 fills it).

Task 3 (recon §2, plan D1-D4): the screen drawn. `dirsel` calls `dirdraw` and returns, nothing else, while DIR_SHOWN is above
DRAWN (unsigned): `dirlock` leaves 0xff, and each call of `dirdraw` runs the phase DIR_SHOWN names (DRAW_PHASES, one a logic
frame, for the margin measured below) and steps it down by one, so DIR_SHOWN reads 0xff, 0xfe, 0xfd while the screen draws and
DRAWN (0xfc) once it is drawn. DRAWN is neither choice (0, 1), so on the next logic frame `dirsel` writes the choice (and calls
`dirshow`) before `dircursor` first indexes "dirsides" with it, and the lock (which copies DIR_SHOWN to the flag) cannot come
while drawing (a gas edge in those three logic frames is not seen). Measured (MAME, the logic frame counter 0x501144): all of
it in one logic frame does not overrun it, but with one more checker redraw (0xfc358e, a few ms) it does; three phases keep
about two thirds of a frame spare on every one. The phases: 0xff layer 0 cleared (0xff92c9: the course select's pictures,
labels, AUTOMATIC row and bottom bar go), layer 2's checker redrawn (0xfc358e: Phase 7's slot overlays go), then on layer 0 the
game's maps (MAPS, table "dirmaps": the double arrow centred between the pictures, the SELECT COURSE wheel panel standing in for
SELECT DIRECTION until Task 5 (D5), the red arrow, STEP TO START!), the title in the countdown's bold yellow font (0xff870d,
D3) and both labels white (0xffe8fb, D4; since Task 4 through `dirshow`, DIR_SHOWN 0xff being neither choice); 0xfe and 0xfd
the chosen entry's own select picture (its record in lay["pictures"]) through select.`picture` into slot 0's blocks and palettes (NORMAL, left) and slot 2's (REVERSE, right), its
map on layer 2 (plan D2: Task 5's arrows go on layer 0 over it) at PICTURE_CELLS. The countdown is the game's (state 1 prints
it every logic frame, at row 39 or, with [0x40dc9b] = 0, row 40, columns 28-31: no piece meets it). The middle slot's blocks are
not used (Task 5's).

Task 4 (plan D4, design §6.6): the choice shown, and the lock look.
- `dirshow` (from `dirsel` once after the drawing and on every change of the choice, so with DIR_SHOWN 0 or 1; and from
  `dirdraw`'s first phase with 0xff) reprints the two labels through 0xffe8fb, the current choice with LABEL_YELLOW and the other
  with LABEL_WHITE (0xff: both white): one loop pass a label, the attribute, tile address and string pushed as
  `ranking.print_call` pushes them, then `ranking.STRING_CALL`. It writes R0 and R12-R14 (the printer saves what it uses).
- `dirdone` (from `start` every logic frame from the direction lock to the race load, as `start` re-colours the course select's
  slots every frame after a course lock): the chosen entry's picture record (as `dirdraw` takes it); slot 0's 48 palette words
  (the NORMAL side) := the record's `chosen` set if DIR_SHOWN (the flag's value since the lock) is 0, else its `grey` set, and
  slot 2's (REVERSE) the other way round; then it falls into `dircursor`, the next routine: the game's frame, steady now that the
  handler is 0xfc27be. It writes R10-R14 only.

Task 5 (plan D5, D8, D11): the arrows and the caption, drawn by dirgfx.py at build time into one data block below 0x2c0000
(`tencourse.dirscreen_block`). The block also holds the screen's draw list, dirgfx's "rows": `dirdraw` ends every phase with
the rows of that phase (at the block's start + dirgfx.PHASE_BYTES * (DIR_SHOWN - DRAW_PHASES[-1])), each a longword copy or a
blit (0xff9436) from the block, until a row with source 0. The game's four maps (MAPS, before Task 5 the table "dirmaps" in
this image) are rows of phase 0xff now, after the title and labels; then the caption's characters go to the middle slot's
third block (0x3580), the wheel panel's own palette (palette RAM 0x73, dirgfx.PANEL_PALETTE) to that block's palette 0x6b, and the caption's map over
the panel's SELECT COURSE cells (CAPTION_CELL), in the same phase as the panel, so SELECT COURSE is never shown. Phases 0xfe /
0xfd draw the pictures as before (no rows), 0xfc copies the clockwise arrow's characters to block 0x3480, 0xfb the
anticlockwise one's to 0x3500, and 0xfa writes the arrows' palettes and blits their maps: when the chosen entry's lap is
anticlockwise (its load record's SENSE_FIELD, the HUD map's cross shift, non-zero) each of those rows' destination moves by the
row's swap, so ARROW_CELLS[0] (NORMAL) always shows the arrow of the entry's own lap and ARROW_CELLS[1] the other, the NORMAL
side's block with the white set and the other's with the red (plan D8). `dirdone` never writes palettes 0x69-0x6b, so the
arrows and the caption keep their colours at the lock. One copy of up to 4 KB a phase at most (the arrows' characters), as
Task 3 measured the margin; DRAWN is DRAW_PHASES[-1] - 1. The rows use R0-R2, R8 and R9 (R1-R3, R7-R9 saved by `pushm`).
"""
from __future__ import annotations

import struct

from vrtools.arcade.codepatch import patch_span
from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, RomSet
from vrtools.arcade.ranking import STRING_CALL                 # 0xffe8fb's call and the pop of its arguments (`dirshow`)
from vrtools.arcade.select import BLIT, CURSOR_FRAME, MENU_INDEX, REC, SLOT_PAL, TILE_ROW
from vrtools.arcade.v60asm import Block, asm

DIR_PHASE = DIRECTION_RAM + 1          # 0x502295: 0 no direction screen, 1 choosing, 2 locked
DIR_ARMED = DIRECTION_RAM + 2          # 0x502296: 1 once the wheel has been at or left of the threshold on this screen (D6)
DIR_SHOWN = DIRECTION_RAM + 3          # 0x502297: the choice the labels and frame show (0, 1; 0xff before the first draw)
STATE0_SITE = 0xFE3CCE                 # mode 0x10 state 0's first instruction: mov.b #0, 5019C0[PC]
STATE0_PATTERN = bytes.fromhex("0980e0f2f2dc51ff")
STATE0_CLEAR = 0x5019C0                # the linked-play cell the original clears there
RANK_SITE = 0xFC40CE                   # movz.bw #0, 5018FC[PC]; test1 #1, 501174[PC] (the `be FC417C` after them stays)
RANK_PATTERN = bytes.fromhex("0d80e0f22ed853ff" "8780e1f29ed053ff")
RECORD_FLAG = 0x5018FC                 # set by the record (0xfc4174); the name entry follows when it is set
RACE_STATE = 0x501174                  # bit 1: the race finished
TEST1_RACE_FINISHED = bytes.fromhex("8780e1f3") + RACE_STATE.to_bytes(4, "little")    # test1 #1, 501174 (absolute: no asm form)
LINKED_BANK_SITES = (0xFE2B07, 0xFE1D37)    # mode 5's linked course load; a cabinet joining a linked race (course.BANK_SITES)
# Task 2 (recon §1, §4, §5)
COURSE_LOCK = 0xFC277C                 # the course select's lock handler: timer := 0x20, then LOCK_SITE, then the cursor object's fields
LOCKED = 0xFC27BE                      # the handler after a lock: `start` (select.py) through 0xfc27d6 every logic frame
LOCK_SITE = 0xFC2788                   # in COURSE_LOCK: mov.w #FC27BE, A[R25]
LOCK_PATTERN = asm("mov.w imm,disp[reg]", LOCKED, 0xA, "r25")
HANDLER = 0xA                          # the entity's handler field
LINKED = 0x40DC8C                      # non-zero in linked play (the course select's own test at 0xfc272c)
TIMER = 0x50113C                       # the select countdown, one step a logic frame (shown as timer >> 5)
EDGE = 0x501078                        # the gas edge: non-zero for the one logic frame the pedal crosses 128 upward (0xfe6812)
WHEEL, WHEEL_PREV = 0x501060, 0x50106C     # this and the previous logic frame's wheel value (0xfe67c1)
DIR_TIMER = 0x140                      # the screen's countdown: 10 s, below 0x180 (state 1's voice cue)
LOCK_TIMER = 0x20                      # the course select's lock threshold (0xfc2762) and the timer every lock sets
THRESHOLD = 0x1C                       # REVERSE is R10 > THRESHOLD, as the SHIFT MODE SELECTOR's 0xfc29d2
SIDE_X = (-112.0, 112.0)               # the cursor frame's centre per choice (NORMAL, REVERSE), recon §4's inferred mockup positions
SIDE_Y = 65.0                          # (Task 3 corrects the two from a snapshot)
OBJECT_NEW = 0xFF8474                  # 0xfc2887's first call (R0 = 3)
CURSOR_OBJECT = 0x502150               # the cursor object 0xfc2897 points the entity's E field at
CURSOR_BODY = CURSOR_FRAME + 0x27      # 0xfc28a7: the cursor frame from its read of R13's x (+0) and y (+4) on
# Task 3 (recon §2, §2.4, §3.1; plan D1-D4)
TILE_RAM, LAYER_BYTES = 0x700000, 0x2000   # layer k's tile map at TILE_RAM + k * LAYER_BYTES, 64 x 64 cells
PICTURE_CELLS = ((4, 9), (4, 37))      # (row, column) of each picture's first tile (NORMAL, REVERSE), on layer 2
PICTURE_SIZE = (21, 16)                # rows, columns (select.picture's)
TITLE_CELL = (1, 15)                   # COURSE DIRECTION, 16 letters of 2 x 3 tiles, layer 0
LABEL_CELLS = ((26, 11), (26, 38))     # NORMAL, REVERSE (2 x 3 tiles a letter), layer 0
ARROW_CELLS = ((8, 11), (8, 39))       # Task 5's 12 x 12-tile arrows over the pictures, layer 0
TITLE = "COURSE DIRECTION"
LABELS = ("NORMAL", "REVERSE")
LABEL_WHITE, LABEL_YELLOW = 0x8200, 0xC200     # 0xffe8fb's attributes (recon §3.1): white, yellow (bit 14)
CLEAR_LAYER = 0xFF92C9                 # R0 = a layer's base: its 0x1000 cells := 0x8020 (clobbers R0-R2)
CHECKER = 0xFC358E                     # layer 2's checker, 9 x 13 blits of map 0x1e0c18 (clobbers R0, R1, R7, R10, R11)
TITLE_PRINT = 0xFF870D                 # R0 string, R1 tile address: the countdown's font (clobbers R0-R3, R8)
DOUBLE_ARROW, WHEEL_PANEL, RED_ARROW, STEP_PANEL = 0x1E2205, 0x1E0F71, 0x1E1185, 0x1E13E1   # bank 0 maps (recon §2.4)
_GAP = PICTURE_CELLS[1][1] - PICTURE_CELLS[0][1] - PICTURE_SIZE[1]                       # the columns between the pictures
MAPS = ((DOUBLE_ARROW, (PICTURE_CELLS[0][0] + (PICTURE_SIZE[0] - 8) // 2, PICTURE_CELLS[0][1] + PICTURE_SIZE[1] + (_GAP - 6) // 2), (8, 6)),
        (WHEEL_PANEL, (30, 7), (13, 20)), (RED_ARROW, (32, 28), (5, 6)), (STEP_PANEL, (30, 35), (13, 20)))   # (map, cell, (rows, cols))
DRAW_PHASES = (0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA)     # DIR_SHOWN while drawing: the clears, the title, the labels, the game's
                                       # maps and the caption; slot 0's picture; slot 2's; the clockwise arrow's characters; the
                                       # anticlockwise one's; the arrows' palettes and maps (Task 5: the rows of dirgfx's block)
DRAWN = DRAW_PHASES[-1] - 1            # DIR_SHOWN once drawn, until the first choice is written
PAL_WORDS = 48                         # a slot's three palettes (select.SLOT_PAL), in halfwords
DRAW_SAVED = 0x38E                     # pushm mask: R1-R3, R7-R9 (dirdraw and what it calls; R0, R10-R14 are the handler's to clobber)
# Task 5 (plan D5, D8, D11): the arrows and the caption (dirgfx.py)
CAPTION_CELL = (31, 8)                 # the wheel panel's cell dirgfx.CAPTION_PANEL_CELL (MAPS: the panel at (30, 7)), the first of
                                       # its SELECT COURSE lettering's cells, where the SELECT DIRECTION caption goes
SENSE_FIELD = 0x38                     # the load record's map_cross (directory.LOAD_FIELDS): non-zero when the entry's lap is
                                       # anticlockwise (tencourse.interior_on_the_left: the HUD map shifts right), so its NORMAL side
                                       # shows the anticlockwise arrow
ROUTINES = ("dirclear", "rankgate", "dirlock", "dirsel", "dirdone", "dircursor", "dirdraw", "dirshow", "dirsides", "dirtext")
READS = ROUTINES + ("reverse", "pictures", "slot_tile", "picture", "load")     # the layout addresses the routines read


def tile_address(layer: int, row: int, col: int) -> int:
    """The tile RAM address of layer `layer`'s cell (row, col)."""
    return TILE_RAM + LAYER_BYTES * layer + TILE_ROW * row + 2 * col


def _text() -> bytes:
    """"dirtext": the title, then the labels, each NUL-ended."""
    return b"".join(t.encode() + b"\0" for t in (TITLE, *LABELS))


def dirscreen_routines(base: int, lay: dict[str, int]) -> dict[str, bytes]:
    """The screen's routines at `base`, in ROM order. Task 1: "dirclear" (from STATE0_SITE: the original's clear of 0x5019c0,
    then the flag and the screen's three cells; no register or condition flag written) and "rankgate" (from RANK_SITE: 0x5018fc
    cleared as the original; Z set when the flag is set, else the flags of the original `test1 #1, 501174`; no register
    written). Task 2: "dirlock", "dirsel", "dirdone", "dircursor", "dirdraw", "dirshow" (see the module's docstring) and the
    table "dirsides" (per choice the cursor frame's x, y as floats). Task 3: `dirdraw` filled, the tables "dirmaps" (per map of
    MAPS its address and layer-0 tile address) and "dirtext" (the title and labels, NUL-ended). Task 4: `dirshow` and `dirdone`
    filled (`dirdone` ends where `dircursor` begins, into which it falls). Task 5: `dirdraw` runs its phase's rows of dirgfx's
    block, and "dirmaps" is gone (its maps are rows of phase 0xff). `lay` is the directory's layout (READS: `lay["reverse"]`,
    `lay["pictures"]`, `lay["slot_tile"]`, `lay["picture"]`, `lay["load"]`, the routines' own addresses: `placeholders` when
    they are not laid out yet)."""
    out: dict[str, bytes] = {}

    def here() -> int:                                      # where the next routine starts
        return base + sum(len(c) for c in out.values())

    b = Block(here())
    b.emit("mov.b imm,abs", 0, STATE0_CLEAR)                # the original's own clear, its address absolute
    b.emit("mov.w imm,abs", 0, DIRECTION_RAM)               # the flag, DIR_PHASE, DIR_ARMED, DIR_SHOWN
    b.emit("rsr")
    out["dirclear"] = b.bytes()
    b = Block(here())
    b.emit("movz.bw imm,abs", 0, RECORD_FLAG)               # the original's own clear of the record flag
    b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)
    b.branch("be", "normal")
    b.emit("cmp.b abs,abs", DIRECTION_RAM, DIRECTION_RAM)   # a reverse race: Z set, the `be FC417C` after the site skips the record
    b.emit("rsr")
    b.label("normal")
    b.raw(TEST1_RACE_FINISHED)                              # the original's own test
    b.emit("rsr")
    out["rankgate"] = b.bytes()
    b = Block(here())                                       # dirlock, at LOCK_SITE in COURSE_LOCK; R0 kept
    b.emit("push reg", "r0")
    b.emit("cmp.b imm,abs", 0, LINKED)
    b.branch("bne", "orig")
    b.emit("cmp.b imm,abs", 0, DIR_PHASE)                   # the direction lock's own pass through COURSE_LOCK
    b.branch("bne", "orig")
    b.emit("movz.bw abs,reg", MENU_INDEX, "r0")
    b.emit("mov.w abs(reg),reg", lay["reverse"], "r0", "r0")
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("be", "orig")
    b.emit("mov.w imm,disp[reg]", lay["dirsel"], HANDLER, "r25")
    b.emit("mov.w imm,abs", DIR_TIMER, TIMER)
    b.emit("mov.b imm,abs", 1, DIR_PHASE)
    b.emit("mov.b imm,abs", 0, DIR_ARMED)
    b.emit("mov.b imm,abs", 0xFF, DIR_SHOWN)
    b.emit("mov.b imm,abs", 0, DIRECTION_RAM)
    b.emit("pop reg", "r0")
    b.emit("rsr")
    b.label("orig")
    b.raw(LOCK_PATTERN)                                     # the original instruction
    b.emit("pop reg", "r0")
    b.emit("rsr")
    out["dirlock"] = b.bytes()
    b = Block(here())                                       # dirsel, the select entity's handler while choosing
    b.emit("cmp.b imm,abs", DRAWN, DIR_SHOWN)               # drawing (DIR_SHOWN above DRAWN, unsigned): one phase, nothing else
    b.branch("bnh", "drawn")
    b.emit("jsr abs", lay["dirdraw"])
    b.emit("rsr")
    b.label("drawn")
    b.emit("mov.w abs,reg", WHEEL, "r10")                   # R10 as 0xfc26c8..0xfc26d6
    b.emit("add.w abs,reg", WHEEL_PREV, "r10")
    b.emit("sha.w imm,reg", -1, "r10")
    b.emit("cmp.w imm,reg", THRESHOLD, "r10")               # D6: armed once at or left of the threshold
    b.branch("bgt", "armed")
    b.emit("mov.b imm,abs", 1, DIR_ARMED)
    b.label("armed")
    b.emit("mov.w imm,reg", 0, "r11")                       # the choice
    b.emit("cmp.b imm,abs", 0, DIR_ARMED)
    b.branch("be", "chosen")
    b.emit("cmp.w imm,reg", THRESHOLD, "r10")
    b.branch("ble", "chosen")
    b.emit("mov.w imm,reg", 1, "r11")
    b.label("chosen")
    b.emit("cmp.b reg,abs", "r11", DIR_SHOWN)
    b.branch("be", "shown")
    b.emit("mov.b reg,abs", "r11", DIR_SHOWN)
    b.emit("jsr abs", lay["dirshow"])
    b.label("shown")
    b.emit("jsr abs", lay["dircursor"])
    b.emit("cmp.w imm,abs", 0, EDGE)                        # 0xfc26c5's two locks: a gas edge ...
    b.branch("bne", "lock")
    b.emit("cmp.w imm,abs", LOCK_TIMER, TIMER)              # ... or the timer at or below 0x20
    b.branch("bgt", "done")
    b.label("lock")
    b.emit("mov.b abs,abs", DIR_SHOWN, DIRECTION_RAM)
    b.emit("mov.b imm,abs", 2, DIR_PHASE)
    b.emit("mov.w imm,disp[reg]", COURSE_LOCK, HANDLER, "r25")
    b.label("done")
    b.emit("rsr")
    out["dirsel"] = b.bytes()
    out["dirdone"] = _dirdone(here(), lay)
    b = Block(here())                                       # dircursor: 0xfc2887's three instructions, R13, the game's frame
    b.emit("mov.w imm,reg", 3, "r0")
    b.emit("jsr abs", OBJECT_NEW)
    b.emit("mov.w imm,disp[reg]", CURSOR_OBJECT, 0xE, "r25")
    b.emit("movz.bw abs,reg", DIR_SHOWN, "r13")
    b.emit("shl.w imm,reg", 3, "r13")
    b.emit("add.w imm,reg", lay["dirsides"], "r13")
    b.emit("jmp abs", CURSOR_BODY)
    out["dircursor"] = b.bytes()
    out["dirdraw"] = _dirdraw(here(), lay)
    out["dirshow"] = _dirshow(here(), lay)
    out["dirsides"] = struct.pack("<4f", SIDE_X[0], SIDE_Y, SIDE_X[1], SIDE_Y)
    out["dirtext"] = _text()
    assert tuple(out) == ROUTINES and ROUTINES.index("dircursor") == ROUTINES.index("dirdone") + 1      # dirdone falls into it
    return out


def _dirdraw(base: int, lay: dict[str, int]) -> bytes:
    """One drawing phase, the one DIR_SHOWN names (DRAW_PHASES), then DIR_SHOWN - 1 (see the module's docstring)."""
    from vrtools.arcade.dirgfx import PHASE_BYTES, ROW_BYTES, block_start      # (dirgfx imports this module)
    assert PHASE_BYTES == 1 << 7
    text = lay["dirtext"]
    b = Block(base)
    b.emit("pushm imm", DRAW_SAVED)
    b.emit("cmp.b imm,abs", DRAW_PHASES[0], DIR_SHOWN)       # 0xff: the clears, the title and labels, then its rows
    b.branch("bne", "pictures")
    b.emit("mov.w imm,reg", tile_address(0, 0, 0), "r0")
    b.emit("jsr abs", CLEAR_LAYER)
    b.emit("jsr abs", CHECKER)
    b.emit("mov.w imm,reg", text, "r0")
    b.emit("mov.w imm,reg", tile_address(0, *TITLE_CELL), "r1")
    b.emit("jsr abs", TITLE_PRINT)
    b.emit("jsr abs", lay["dirshow"])                        # the labels: DIR_SHOWN 0xff is neither choice, both white
    b.branch("br", "rows")
    b.label("pictures")
    b.emit("cmp.b imm,abs", DRAW_PHASES[3], DIR_SHOWN)       # 0xfc and below: rows only
    b.branch("bnh", "rows")
    b.emit("movz.bw abs,reg", MENU_INDEX, "r11")            # 0xfe / 0xfd: the chosen entry's picture record
    b.emit("mov.w abs(reg),reg", lay["pictures"], "r11", "r11")
    b.emit("cmp.w imm,reg", 0, "r11")
    b.branch("be", "rows")
    b.emit("mov.w imm,reg", 0, "r10")                       # slot 0, the NORMAL side
    b.emit("mov.w imm,reg", tile_address(2, *PICTURE_CELLS[0]), "r12")
    b.emit("cmp.b imm,abs", DRAW_PHASES[1], DIR_SHOWN)
    b.branch("be", "slot")
    b.emit("mov.w imm,reg", 2, "r10")                       # slot 2, the REVERSE side
    b.emit("mov.w imm,reg", tile_address(2, *PICTURE_CELLS[1]), "r12")
    b.label("slot")
    b.emit("mov.w abs(reg),reg", lay["slot_tile"], "r10", "r13")
    b.emit("jsr abs", lay["picture"])
    b.label("rows")                                         # the phase's rows in dirgfx's block
    b.emit("movz.bw abs,reg", DIR_SHOWN, "r9")
    b.emit("shl.w imm,reg", 7, "r9")
    b.emit("add.w imm,reg", block_start() - PHASE_BYTES * DRAW_PHASES[-1], "r9")
    b.emit("movz.bw abs,reg", MENU_INDEX, "r8")             # R8: the entry's lap sense (its load record's SENSE_FIELD)
    b.emit("shl.w imm,reg", 4, "r8")                        # (64-byte records, the index scaled by the word)
    b.emit("mov.w abs(reg),reg", lay["load"] + SENSE_FIELD, "r8", "r8")
    b.label("row")
    b.emit("mov.w [reg],reg", "r9", "r0")                   # source; 0 ends the phase's rows
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("be", "step")
    b.emit("mov.w disp[reg],reg", 4, "r9", "r1")            # destination
    b.emit("cmp.w imm,reg", 0, "r8")
    b.branch("be", "kept")
    b.emit("add.w disp[reg],reg", 12, "r9", "r1")           # anticlockwise: moved by the row's swap
    b.label("kept")
    b.emit("mov.w disp[reg],reg", 8, "r9", "r2")            # count: 0 a blit, else longwords to copy
    b.emit("cmp.w imm,reg", 0, "r2")
    b.branch("bne", "copy")
    b.emit("jsr abs", BLIT)                                 # (0xff9436 keeps R0, R2-R6; R1 and R7 are written)
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
    b.label("step")
    b.emit("movz.bw abs,reg", DIR_SHOWN, "r0")
    b.emit("sub.w imm,reg", 1, "r0")
    b.emit("mov.b reg,abs", "r0", DIR_SHOWN)
    b.emit("popm imm", DRAW_SAVED)
    b.emit("rsr")
    return b.bytes()


def _dirshow(base: int, lay: dict[str, int]) -> bytes:
    """The two labels, one loop pass a label k: LABEL_YELLOW when k is DIR_SHOWN, else LABEL_WHITE (see the module's docstring)."""
    b = Block(base)
    b.emit("mov.w imm,reg", tile_address(0, *LABEL_CELLS[0]), "r12")
    b.emit("mov.w imm,reg", lay["dirtext"] + len(TITLE) + 1, "r13")     # "NORMAL", then "REVERSE" right after its NUL
    b.emit("mov.w imm,reg", 0, "r14")                       # k
    b.label("label")
    b.emit("mov.h imm,reg", LABEL_WHITE, "r0")              # (the printer reads the attribute's halfword only)
    b.emit("cmp.b reg,abs", "r14", DIR_SHOWN)
    b.branch("bne", "white")
    b.emit("mov.h imm,reg", LABEL_YELLOW, "r0")
    b.label("white")
    b.emit("push reg", "r0")                                # attribute, tile address, string: ranking.print_call's order
    b.emit("push reg", "r12")
    b.emit("push reg", "r13")
    b.raw(STRING_CALL)
    b.emit("add.w imm,reg", 2 * (LABEL_CELLS[1][1] - LABEL_CELLS[0][1]), "r12")
    b.emit("add.w imm,reg", len(LABELS[0]) + 1, "r13")
    b.emit("add.w imm,reg", 1, "r14")
    b.emit("cmp.w imm,reg", len(LABELS), "r14")
    b.branch("bne", "label")
    b.emit("rsr")
    return b.bytes()


def _dirdone(base: int, lay: dict[str, int]) -> bytes:
    """The lock look: per side the slot's palettes := the record's chosen or grey set, then (falling through) `dircursor`."""
    b = Block(base)
    b.emit("movz.bw abs,reg", MENU_INDEX, "r11")            # the chosen entry's picture record, as dirdraw takes it
    b.emit("mov.w abs(reg),reg", lay["pictures"], "r11", "r11")
    b.emit("cmp.w imm,reg", 0, "r11")
    b.branch("be", "cursor")
    b.emit("mov.w imm,reg", SLOT_PAL[0], "r13")             # slot 0's palettes: the NORMAL side
    b.emit("mov.w imm,reg", 0, "r10")                       # the side
    b.label("side")
    b.emit("movz.bw imm,reg", REC["grey"], "r12")
    b.emit("cmp.b reg,abs", "r10", DIR_SHOWN)
    b.branch("bne", "pick")
    b.emit("mov.w imm,reg", REC["chosen"], "r12")
    b.label("pick")
    b.emit("add.w reg,reg", "r11", "r12")
    b.emit("mov.w [reg],reg", "r12", "r12")                 # the set's address
    b.emit("movz.bw imm,reg", PAL_WORDS, "r14")
    b.label("copy")
    b.emit("mov.h [reg],[reg]", "r12", "r13")
    b.emit("add.w imm,reg", 2, "r12")
    b.emit("add.w imm,reg", 2, "r13")
    b.emit("sub.w imm,reg", 1, "r14")
    b.branch("bne", "copy")
    b.emit("add.w imm,reg", SLOT_PAL[2] - SLOT_PAL[0] - 2 * PAL_WORDS, "r13")     # on to slot 2's: the REVERSE side
    b.emit("add.w imm,reg", 1, "r10")
    b.emit("cmp.w imm,reg", 2, "r10")
    b.branch("bne", "side")
    b.label("cursor")                                       # the block's end: dircursor's first byte (ROUTINES' order)
    return b.bytes()


def placeholders(lay: dict[str, int], addr: int) -> dict[str, int]:
    """`lay` with every address the routines read and it lacks set to `addr` (the routines' sizes do not depend on the values
    as long as none is below 16, the short immediates)."""
    return {**lay, **{k: lay.get(k, addr) for k in READS}}


def dirscreen_size() -> int:
    return sum(len(c) for c in dirscreen_routines(0x100000, placeholders({}, 0x100000)).values())


def patch_dirscreen_sites(rs: RomSet, lay: dict[str, int]) -> None:
    """STATE0_SITE: `jsr dirclear`, nop-padded to its eight bytes; RANK_SITE: `jsr rankgate`, nop-padded to its sixteen;
    LOCK_SITE: `jsr dirlock`, nop-padded to its nine. All are checked before any is written; PatchError naming the first whose
    bytes are not its pattern. (The linked bank sites are routed by `directory.install_directory` with the other bank sites.)"""
    spans = []
    for site, pattern, name, what in ((STATE0_SITE, STATE0_PATTERN, "dirclear", "mode 0x10 state 0's clear"),
                                      (RANK_SITE, RANK_PATTERN, "rankgate", "ranking gate"),
                                      (LOCK_SITE, LOCK_PATTERN, "dirlock", "course lock's handler")):
        have = rs.boot[site - V60_BOOT:site - V60_BOOT + len(pattern)]
        if have != pattern:
            raise PatchError(f"{what} site at {site:#x} is not the expected sequence: {have.hex()} (expected {pattern.hex()})")
        b = Block(site); b.emit("jsr abs", lay[name])
        spans.append((site, b.bytes(), len(pattern)))
    for site, blob, n in spans:
        patch_span(rs, site, blob, n)
