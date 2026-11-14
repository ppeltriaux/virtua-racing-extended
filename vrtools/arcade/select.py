"""The ten-course select: wheel bands, the three-slot window and the V60 routines that draw it (Phase 7, M4).

The original select screen (boot ROM 0xfc26c5) turns the wheel value `R10 = ([0x501060] + [0x50106c]) >> 1`
(−127..127; measured ≈ 1.72 × (wheel − 128), clamped at wheel ≈ 54 / 202) into a course with two thresholds,
blits three fixed panels (0xfc3622); the yellow frame follows the choice, and at START the chosen art gets a
highlighted palette (0xfc27d6). Here the wheel range is cut into ten bands, three consecutive
entries are shown in the three slots (the chosen one in the middle except at the ends) and the panels and their
second-layer maps are redrawn whenever the band changes.

Select screen facts (docs/formats/model1-course-tables.md §13): panel maps are blitted by 0xff9436 (R0 = map,
R1 = tile-RAM destination); slot s has its layer-A map at 0x704088 + 0x26·s and its layer-B map at
0x700088 + 0x26·s; an art's palette block is bound to its character page (0x3000 → palette RAM 0x900c00…).
"""
from __future__ import annotations

import struct

from vrtools.arcade.v60asm import Block

BANDS = (-102, -77, -51, -26, 0, 26, 51, 77, 102)          # band k = R10 >= BANDS[k-1] and < BANDS[k] (ten bands of 25.6)
WHEEL_FOR_ENTRY = (61, 76, 91, 106, 120, 135, 150, 165, 180, 195)   # paddle values at the band centres (R10 ≈ 1.72 × (w − 128))
SLOT_X = (-151.0, 1.0, 153.0)
SLOT_Y = 88.0
SLOT_A = (0x704088, 0x7040AE, 0x7040D4)                     # layer-A (panel) tile-RAM destinations per slot
SLOT_B = (0x700088, 0x7000AE, 0x7000D4)                     # layer-B (second map) destinations per slot
BLIT = 0xFF9436
MENU_INDEX = 0x501940
SHOWN_INDEX = 0x501942
# patch sites
ZONES = 0xFC26DF            # `xor R11,R11; cmp #1C …` -> R11 = course; 0x1b bytes up to `movt.wh R11, 501940`
ZONES_LEN = 0x1B
DRAW_SITE = 0xFC3622        # blits the three panels and their second maps; 0x79 bytes up to its rsr
DRAW_SITE_LEN = 0x79
# Phase 21: per-slot picture areas (docs/superpowers/specs/2026-11-01-select-previews-design.md). Slot s owns three
# character blocks (102 + 3s ..) and their palettes, the areas the originals' pictures had; `draw` copies the shown entry's
# picture into them and `start` (from 0xfc27d6) greys the slots not chosen.
SLOT_CHAR = (0x3300, 0x3480, 0x3600)                        # first character of each slot's three blocks
SLOT_PAL = (0x900CC0, 0x900D20, 0x900D80)                   # each slot's three palettes (48 halfwords)
CHAR_RAM = 0x780000
BLANK_TILE = 0x8020                                         # the boot font's space (character 0x20, all colour 0): a slot shows nothing
TILE_ROW = 0x80                                             # tile RAM bytes per tilemap row (the blitter's pitch)
CURSOR_FRAME = 0xFC2880                                     # the game's cursor frame builder (reads [0x501940] itself)
START_SITE = 0xFC27D6                                       # the START palette swap by data index; 0x4c bytes to its rsr
START_SITE_LEN = 0x4C
# picture record fields (picture.encode_record)
REC = {"chars": 0, "counts": 4, "normal": 8, "chosen": 12, "grey": 16, "map": 20, "a_dst": 24, "a_chosen": 28, "a_grey": 32}
# 0xfc369b (compare 0x501940 with 0x501942, re-colour) is dead code in the original: nothing references it, and the
# palette "highlight" only happens at START (0xfc27d6, by data index). The redraw therefore hangs off the per-frame
# band routine, which keeps the last drawn index in 0x501942.


def band_of(r10: int) -> int:
    return sum(1 for t in BANDS if r10 >= t)


def first_of(index: int) -> int:
    return max(0, min(7, index - 1))


def visible_entries(index: int) -> tuple[int, int, int]:
    f = first_of(index)
    return (f, f + 1, f + 2)


def slot_of(index: int) -> int:
    return index - first_of(index)


def encode_bands() -> bytes:
    return b"".join(struct.pack("<i", t) for t in BANDS)


def select_routines(lay: dict[str, int]) -> dict[str, bytes]:
    """`band` (R10 -> R11, redrawing the row when the band changed) and `draw` (the window for [0x501940]) at
    lay["band"], lay["draw"]; tables at lay["bands"], lay["slot_a"], lay["slot_b"], lay["select"], lay["load"]."""
    sel, load = lay["select"], lay["load"]
    # --- band: R11 = number of thresholds at or below R10; on a change, write it and redraw
    b = Block(lay["band"])
    for r in ("r1", "r8", "r9"):
        b.emit("push reg", r)
    b.emit("mov.w imm,reg", 0, "r11")
    b.emit("mov.w imm,reg", lay["bands"], "r9")
    b.emit("mov.w imm,reg", len(BANDS), "r8")
    b.label("loop")
    b.emit("mov.w [reg],reg", "r9", "r1")
    b.emit("cmp.w reg,reg", "r1", "r10")                        # R10 - R1
    b.branch("blt", "skip")                                     # count thresholds <= R10
    b.emit("add.w imm,reg", 1, "r11")
    b.label("skip")
    b.emit("add.w imm,reg", 4, "r9")
    b.emit("sub.w imm,reg", 1, "r8")
    b.branch("bne", "loop")
    b.emit("movz.hw abs,reg", SHOWN_INDEX, "r1")
    b.emit("cmp.w reg,reg", "r11", "r1")
    b.branch("be", "same")
    b.emit("mov.h reg,abs", "r11", SHOWN_INDEX)
    b.emit("mov.b reg,abs", "r11", MENU_INDEX)                  # the caller stores it too; draw reads it
    b.emit("jsr abs", lay["draw"])
    b.label("same")
    for r in ("r9", "r8", "r1"):
        b.emit("pop reg", r)
    b.emit("rsr")
    band = b.bytes()
    # --- draw: three slots of the window around [0x501940]
    b = Block(lay["draw"])
    for r in ("r1", "r8", "r9", "r10", "r11", "r12", "r13"):
        b.emit("push reg", r)
    b.emit("movz.bw abs,reg", MENU_INDEX, "r12")
    b.emit("mov.w reg,reg", "r12", "r9")
    b.emit("sub.w imm,reg", 1, "r9")
    b.emit("cmp.w imm,reg", 0, "r9")
    b.branch("bge", "lo")
    b.emit("mov.w imm,reg", 0, "r9")
    b.label("lo")
    b.emit("cmp.w imm,reg", 7, "r9")
    b.branch("ble", "hi")
    b.emit("mov.w imm,reg", 7, "r9")
    b.label("hi")
    b.emit("mov.w imm,reg", 0, "r10")                           # slot
    b.label("slot")
    b.emit("mov.w reg,reg", "r9", "r8")
    b.emit("add.w reg,reg", "r10", "r8")                        # r8 = entry
    b.emit("mov.w reg,reg", "r8", "r11")
    b.emit("mul.w imm,reg", 24, "r11")
    b.emit("add.w imm,reg", sel, "r11")                         # select entry
    b.emit("mov.w disp[reg],reg", 8, "r11", "r0")               # layer-A map
    b.emit("mov.w abs(reg),reg", lay["slot_a"], "r10", "r1")
    b.emit("jsr abs", BLIT)
    b.emit("mov.w abs(reg),reg", lay["pictures"], "r8", "r11")  # Phase 21: the entry's picture record
    b.emit("cmp.w imm,reg", 0, "r11")
    b.branch("be", "plain")
    b.emit("mov.w abs(reg),reg", lay["slot_b"], "r10", "r12")   # the slot's layer-B destination
    b.emit("mov.w abs(reg),reg", lay["slot_tile"], "r10", "r13")  # and its tile base
    b.emit("jsr abs", lay["picture"])                           # r10 slot, r11 record, r12 destination, r13 tile base
    b.branch("br", "next")
    b.label("plain")
    b.emit("mov.w reg,reg", "r8", "r11")
    b.emit("shl.w imm,reg", 6, "r11")
    b.emit("add.w imm,reg", load, "r11")                        # load entry
    from vrtools.arcade.directory import LOAD_FIELDS                   # (import here: directory imports select)
    b.emit("mov.w disp[reg],reg", LOAD_FIELDS["panel_b"], "r11", "r0")  # layer-B map
    b.emit("mov.w abs(reg),reg", lay["slot_b"], "r10", "r1")
    b.emit("jsr abs", BLIT)
    b.label("next")
    b.emit("add.w imm,reg", 1, "r10")
    b.emit("cmp.w imm,reg", 3, "r10")
    b.branch("blt", "slot")
    for r in ("r13", "r12", "r11", "r10", "r9", "r8", "r1"):
        b.emit("pop reg", r)
    b.emit("rsr")
    draw = b.bytes()
    return {"band": band, "draw": draw, "picture": _picture(lay), "start": _start(lay)}


def _copy(b: Block, src: str, dst: str, count: str, size: str, tag: str) -> None:
    """[dst] <- [src], `count` units of `size` ("w" or "h"); src and dst advance; nothing when count is 0."""
    step = 4 if size == "w" else 2
    b.emit("cmp.w imm,reg", 0, count)
    b.branch("be", f"{tag}_done")
    b.label(f"{tag}_loop")
    b.emit(f"mov.{size} [reg],reg", src, "r0")
    b.emit(f"mov.{size} reg,[reg]", "r0", dst)
    b.emit("add.w imm,reg", step, src)
    b.emit("add.w imm,reg", step, dst)
    b.emit("sub.w imm,reg", 1, count)
    b.branch("bne", f"{tag}_loop")
    b.label(f"{tag}_done")


def _picture(lay: dict[str, int]) -> bytes:
    """r10 = slot, r11 = picture record, r12 = the map's tile RAM destination (its top-left cell), r13 = the tile base (the
    slot's 0x8000 | SLOT_CHAR). The 16 x 21 cells at r12 first all point at BLANK_TILE (review: a copy the beam catches half
    done would otherwise show for a frame), then the record's three character runs go to the slot's blocks and its normal
    palettes to the slot's palettes, then its map as tile words r13 + local. Memory-to-memory moves, one character (8 words)
    and one map row (16 tiles) per loop pass (the first version's load/store loop took ~28 ms a wheel step). The course
    select's `draw` passes the slot's SLOT_B and tile base; Phase 26 stage 3's direction screen (dirscreen.py) other cells
    on layer 2. R0-R7 saved; R12, R13 not written."""
    b = Block(lay["picture"])
    regs = ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7")
    for r in regs:
        b.emit("push reg", r)
    b.emit("mov.w reg,reg", "r12", "r6")                             # 1. blank the destination
    b.emit("mov.w imm,reg", 21, "r4")
    b.label("blank")
    for c in range(16):
        b.emit("mov.h imm,disp[reg]", BLANK_TILE, 2 * c, "r6")
    b.emit("add.w imm,reg", TILE_ROW, "r6")
    b.emit("sub.w imm,reg", 1, "r4")
    b.branch("bne", "blank")
    b.emit("mov.w abs(reg),reg", lay["slot_char"], "r10", "r2")      # 2. the characters: three runs
    b.emit("mov.w disp[reg],reg", REC["chars"], "r11", "r3")
    b.emit("mov.w disp[reg],reg", REC["counts"], "r11", "r4")
    for p in range(3):
        b.emit("mov.w reg,reg", "r4", "r5")
        if p:
            b.emit("shl.w imm,reg", -8 * p, "r5")                     # a negative count shifts right
        b.emit("and.w imm,reg", 0xFF, "r5")
        b.emit("mov.w reg,reg", "r2", "r6")
        if p:
            b.emit("add.w imm,reg", 128 * 32 * p, "r6")
        b.emit("cmp.w imm,reg", 0, "r5")
        b.branch("be", f"run{p}_done")
        b.label(f"run{p}")
        for k in range(8):
            b.emit("mov.w disp[reg],disp[reg]", 4 * k, "r3", 4 * k, "r6")
        b.emit("add.w imm,reg", 32, "r3")
        b.emit("add.w imm,reg", 32, "r6")
        b.emit("sub.w imm,reg", 1, "r5")
        b.branch("bne", f"run{p}")
        b.label(f"run{p}_done")
    b.emit("mov.w disp[reg],reg", REC["normal"], "r11", "r3")         # 3. the palettes
    b.emit("mov.w abs(reg),reg", lay["slot_pal"], "r10", "r6")
    for k in range(48):
        b.emit("mov.h disp[reg],disp[reg]", 2 * k, "r3", 2 * k, "r6")
    b.emit("mov.w disp[reg],reg", REC["map"], "r11", "r3")            # 4. the map
    b.emit("mov.w reg,reg", "r12", "r6")
    b.emit("mov.w reg,reg", "r13", "r7")
    b.emit("mov.w imm,reg", 21, "r4")
    b.label("row")
    for c in range(16):
        b.emit("movz.hw disp[reg],reg", 2 * c, "r3", "r0")
        b.emit("add.w reg,reg", "r7", "r0")
        b.emit("mov.h reg,disp[reg]", "r0", 2 * c, "r6")
    b.emit("add.w imm,reg", 32, "r3")
    b.emit("add.w imm,reg", TILE_ROW, "r6")
    b.emit("sub.w imm,reg", 1, "r4")
    b.branch("bne", "row")
    for r in reversed(regs):
        b.emit("pop reg", r)
    b.emit("rsr")
    return b.bytes()


def _start(lay: dict[str, int]) -> bytes:
    """Jumped to from 0xfc27d6 (the START palette swap): each slot with a picture gets its chosen palettes if it shows
    [0x501940], else its grey ones; a slot holding an original also its layer-A set; then the game's cursor frame. Phase 26
    stage 3: first, with the COURSE DIRECTION screen's phase cell non-zero (the screen locked), `jmp dirdone` instead; the rest
    is the routine as it was."""
    from vrtools.arcade.dirscreen import DIR_PHASE              # (dirscreen imports this module)
    b = Block(lay["start"])
    b.emit("cmp.b imm,abs", 0, DIR_PHASE)
    b.branch("be", "course")
    b.emit("jmp abs", lay["dirdone"])
    b.label("course")
    regs = ("r0", "r1", "r3", "r4", "r5", "r6", "r8", "r9", "r10", "r11", "r12")
    for r in regs:
        b.emit("push reg", r)
    b.emit("movz.bw abs,reg", MENU_INDEX, "r12")
    b.emit("mov.w reg,reg", "r12", "r9")
    b.emit("sub.w imm,reg", 1, "r9")
    b.emit("cmp.w imm,reg", 0, "r9")
    b.branch("bge", "lo")
    b.emit("mov.w imm,reg", 0, "r9")
    b.label("lo")
    b.emit("cmp.w imm,reg", 7, "r9")
    b.branch("ble", "hi")
    b.emit("mov.w imm,reg", 7, "r9")
    b.label("hi")
    b.emit("mov.w imm,reg", 0, "r10")
    b.label("slot")
    b.emit("mov.w reg,reg", "r9", "r8")
    b.emit("add.w reg,reg", "r10", "r8")                        # r8 = entry
    b.emit("mov.w abs(reg),reg", lay["pictures"], "r8", "r11")
    b.emit("cmp.w imm,reg", 0, "r11")
    b.branch("be", "next")
    b.emit("mov.w imm,reg", REC["grey"], "r1")
    b.emit("mov.w imm,reg", REC["a_grey"], "r4")
    b.emit("cmp.w reg,reg", "r8", "r12")
    b.branch("bne", "pick")
    b.emit("mov.w imm,reg", REC["chosen"], "r1")
    b.emit("mov.w imm,reg", REC["a_chosen"], "r4")
    b.label("pick")
    b.emit("add.w reg,reg", "r11", "r1")
    b.emit("mov.w [reg],reg", "r1", "r3")                       # the B set
    b.emit("mov.w abs(reg),reg", lay["slot_pal"], "r10", "r6")
    b.emit("mov.w imm,reg", 48, "r5")
    _copy(b, "r3", "r6", "r5", "h", "b")
    b.emit("mov.w disp[reg],reg", REC["a_dst"], "r11", "r6")
    b.emit("cmp.w imm,reg", 0, "r6")
    b.branch("be", "next")
    b.emit("add.w reg,reg", "r11", "r4")
    b.emit("mov.w [reg],reg", "r4", "r3")                       # the A set (originals)
    b.emit("mov.w imm,reg", 32, "r5")
    _copy(b, "r3", "r6", "r5", "h", "a")
    b.label("next")
    b.emit("add.w imm,reg", 1, "r10")
    b.emit("cmp.w imm,reg", 3, "r10")
    b.branch("blt", "slot")
    for r in reversed(regs):
        b.emit("pop reg", r)
    b.emit("jsr abs", CURSOR_FRAME)
    b.emit("rsr")
    return b.bytes()
