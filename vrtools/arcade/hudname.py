"""Phase 26 stage 3 (plan Task 6): the course's name in the race HUD, where the game prints the level word.

Pascal's request of 13 Nov and decisions H1-H4: on the seven converted courses the HUD's bottom-right label reads the course's
name, not BEGINNER / MEDIUM / EXPERT (the word the host template's data index picks); the three originals keep the game's word
(H1); the name takes the colour of the level the select screen shows for the entry, the record's `label` (H2: LEVEL_ATTR);
right-aligned, its last letter in column 58 where the game's 8-cell word ends (H3); the same name in reverse (H4: `entry` serves
the variant, whose name and label are the menu entry's).

The site (the original boot listing): 0xff4733..0xff4799 in 0xff471b, the HUD entity's first handler, run once at the race load
(mode 0x11), chooses the string and the colour cell [0x501434] (a word, written with `movz.bw`) by the data index [0x501934],
sets R1 to layer 0's row 44, column 51, and at HUD_SITE calls the printer 0xff8926 (R0 a NUL-ended string, R1 the first cell;
glyph word (`[0x501434]` << 7) − 0x40 + 2·ch | `[0x50143c]` on row 44, the same + 1 on row 45; it writes R0-R3 and R8). HUD_SITE
is entered only from the instruction before it (no branch of the original boot ROM lands in its six bytes). Nothing redraws the
label until mode 0x15 clears layer 0. The second copy at 0xff53ae..0xff53fa (a linked slave cabinet only) is left as it is.

HUD_SITE becomes `jsr hudname`. `hudname` saves R0, R1 and R8 (SAVED) around `entry` (the loader's lookup: R8 := the served load
record, the menu entry's, its reverse variant's or the original fallback's; it writes R0, R1 and R8 only). Then:
- `race` (+0x2C) 0, an original: the three restored, `jmp` to the printer, which is so entered with the registers and the stack
  as the site's `jsr` left them (its `rsr` returns to 0xff479f) and [0x501434] as the game set it. The printer reads no condition
  flag before its own `sha.h` sets them.
- otherwise: R2 := the record (R2, R3 are the printer's to write), the three restored, R0 := the record + 0x1C (the name), R1 :=
  the site's R1 + 16 − 2 a letter up to the NUL (so the last letter is in the game's 8th cell), the word [0x501434] pushed and
  set to LEVEL_ATTR[label] as the game's `movz.bw` sets it, the printer called, the pushed word written back, `rsr`. After it R1
  is one past the 8th cell, R3 0 and R8 [0x50143c] as after the game's word; R0 (past the name) is written at 0xff47b6 before
  any read; R2 (the restored word) is read by nothing before the entity loop writes it (0xfe1c25: 0xff9436, the only routine
  the handler calls before that which saves R2, restores it). No condition flag is read after the site before `test.b` at
  0xff47c3 sets them.
The record's name field (directory.NAME_LEN bytes) is NUL-padded (`directory._load_record`), names at most 13 letters.
"""
from __future__ import annotations

from vrtools.arcade.codepatch import patch_span
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, RomSet
from vrtools.arcade.v60asm import Block

HUD_SITE = 0xFF4799                    # in 0xff471b: jsr FF8926[PC], the level word's print at the race load
HUD_PATTERN = bytes.fromhex("e8f28d410000")
PRINTER = 0xFF8926                     # R0 string, R1 first cell (layer 0); writes R0-R3, R8
ATTR = 0x501434                        # the printer's colour cell (a word)
LEVEL_ATTR = (0x02, 0x83, 0x82)        # by the record's `label` (0 BEGINNER, 1 MEDIUM, 2 EXPERT): blue, orange, red, the game's
                                       # own cells for those words (0xff4733..0xff4771)
SAVED = 0x103                          # pushm / popm mask: R0, R1, R8 (what `entry` writes)
FIELD_CELLS = 8                        # the game's word fills 8 cells (columns 51-58)
RACE, LABEL, NAME = 0x2C, 3, 0x1C      # directory.LOAD_FIELDS (imported there: directory imports this module)
ROUTINES = ("hudname", "hudattr")
READS = ROUTINES + ("entry",)          # the layout addresses the routines read


def hudname_routines(base: int, lay: dict[str, int]) -> dict[str, bytes]:
    """"hudname" (see the module's docstring) and its table "hudattr" (LEVEL_ATTR, one byte a label) at `base`, in ROM order.
    `lay` is the directory's layout (READS: `placeholders` when they are not laid out yet)."""
    b = Block(base)
    b.emit("pushm imm", SAVED)
    b.emit("jsr abs", lay["entry"])                         # R8 = the served load record
    b.emit("cmp.w imm,disp[reg]", 0, RACE, "r8")
    b.branch("bne", "name")
    b.emit("popm imm", SAVED)                               # an original: the printer entered as the site entered it
    b.emit("jmp abs", PRINTER)
    b.label("name")
    b.emit("mov.w reg,reg", "r8", "r2")                     # the record
    b.emit("popm imm", SAVED)
    b.emit("mov.w reg,reg", "r2", "r0")
    b.emit("add.w imm,reg", NAME, "r0")                     # R0 = the name
    b.emit("add.w imm,reg", 2 * FIELD_CELLS, "r1")          # R1 = the site's + 2 (8 - length): right-aligned to the 8th cell
    b.emit("mov.w reg,reg", "r0", "r3")
    b.label("count")
    b.emit("cmp.b imm,[reg]", 0, "r3")
    b.branch("be", "print")
    b.emit("sub.w imm,reg", 2, "r1")
    b.emit("add.w imm,reg", 1, "r3")
    b.branch("br", "count")
    b.label("print")
    b.emit("mov.w abs,reg", ATTR, "r3")                     # the game's colour cell, kept on the stack
    b.emit("push reg", "r3")
    b.emit("movz.bw disp[reg],reg", LABEL, "r2", "r3")
    b.emit("movz.bw abs(reg),abs", lay["hudattr"], "r3", ATTR)
    b.emit("jsr abs", PRINTER)
    b.emit("pop reg", "r2")
    b.emit("mov.w reg,abs", "r2", ATTR)
    b.emit("rsr")
    out = {"hudname": b.bytes(), "hudattr": bytes(LEVEL_ATTR)}
    assert tuple(out) == ROUTINES
    return out


def placeholders(lay: dict[str, int], addr: int) -> dict[str, int]:
    """`lay` with every address the routines read and it lacks set to `addr` (sizes do not depend on the values)."""
    return {**lay, **{k: lay.get(k, addr) for k in READS}}


def hudname_size() -> int:
    return sum(len(c) for c in hudname_routines(0x100000, placeholders({}, 0x100000)).values())


def patch_hudname_sites(rs: RomSet, lay: dict[str, int]) -> None:
    """HUD_SITE: `jsr hudname` (its six bytes); PatchError naming it when its bytes are not HUD_PATTERN."""
    have = rs.boot[HUD_SITE - V60_BOOT:HUD_SITE - V60_BOOT + len(HUD_PATTERN)]
    if have != HUD_PATTERN:
        raise PatchError(f"HUD level word site at {HUD_SITE:#x} is not the expected sequence: {have.hex()} (expected {HUD_PATTERN.hex()})")
    b = Block(HUD_SITE); b.emit("jsr abs", lay["hudname"])
    blob = b.bytes()
    assert len(blob) == len(HUD_PATTERN)
    patch_span(rs, HUD_SITE, blob, len(HUD_PATTERN))
