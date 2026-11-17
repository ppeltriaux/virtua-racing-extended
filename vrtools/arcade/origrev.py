"""Phase 33 (stages 1 and 2): what a reverse race on one of the three ORIGINAL courses needs beside its variant's tables.

The three originals get a reverse variant like the seven converted courses (`tencourse.reverse_of_original`, the directory's
`ReverseRecord`); every routine of Phase 26 is keyed on the direction flag or on the entry's word in the reverse table and
serves them unchanged. One thing is keyed on "a converted course" and is corrected here, by a small routine in a block
of their own (`BLOCK_BYTES` at `tencourse.origrev_address()`: erased program ROM below the far copies' colour block, Phase 31's,
which lies below the start gantry's block; `tencourse.reserved_blocks` names every such reservation and `check_reserved_blocks` refuses an overlap). They are NOT in
the directory image: its nine spare bytes before the first tile table would not hold them, and a longer image moves the seven
courses' tile tables, race blobs and spawn lists.

- **"rankgate3"** is gone (Phase 35): it made a reverse race on an original record nothing while the battery RAM had no table
  for it. The ranking setter now moves the ids 0..2 to their own reverse tables (ranking.py), and the race end's site 0xfc40ce
  (RANK_SITE) holds the game's own sixteen bytes again, as on the builds before Phase 33; `install_origrev` checks that it does.
- **"hudorig"** (hudname.HUD_SITE, in place of `jsr hudname`): the HUD's bottom-right label of a reverse race on an original is
  the game's own level word, as in its normal race, with Phase 32's word REVERSE under it (stage 2). `hudname` prints the
  course's name whenever the served record has a race blob, and a variant has one (its checkpoints). When the flag is set and
  the menu entry [0x501940] is below 3 the routine calls the game's printer (the level word, entered as the site entered it),
  then prints REVERSE as `hudname`'s reverse path does (the colour cell [0x501434] kept on the stack and set to
  hudname.REVERSE_ATTR, R1 moved by hudname.REVERSE_STEP and, on entries 1 and 2 whose words end in a space, one cell further
  left, R0 the layout's "hudrev", the printer, the cell written back) and returns; else it jumps to `hudname`. With the flag 0
  it is `hudname`. (On the fallback path, where the game chose the course itself, the flag is 0.)

`hudorig`'s reverse path leaves the registers as `hudname`'s reverse path does (R0-R3 and R8
are the printer's, R2 the game's colour word, all written before any read after the site: hudname.py's note on HUD_SITE); its
other path writes none. It sets condition flags only where nothing reads them."""
from __future__ import annotations

from vrtools.arcade import hudname
from vrtools.arcade.codepatch import patch_span
from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.arcade.v60asm import Block

BLOCK_BYTES = 160                      # the block. `hudorig` takes 96 bytes (since stage 2's REVERSE under the level word; Phase 33's
                                       # `rankgate3`, 50 bytes before it, is gone since Phase 35); reserved at 160 in stage 1 so that
                                       # it would not move
ORIGINALS_BELOW = 3                    # menu entries and ranking ids 0..2 are the three originals
PADDED_FROM = 1                        # menu entry 0 (Big Forest) shows BEGINNER, eight letters; 1 and 2 (Bay Bridge, Acropolis)
                                       # " MEDIUM " and " EXPERT ", whose 8th cell is a space
MENU_INDEX = 0x501940
RANKING_INDEX = 0x40FC68               # ranking.RANKING_INDEX (ranking.py imports nothing from here)
RANK_SITE = 0xFC40CE                   # movz.bw #0, 5018FC[PC]; test1 #1, 501174[PC]: the game's own, not patched (Phase 35)
RANK_PATTERN = bytes.fromhex("0d80e0f22ed853ff" "8780e1f29ed053ff")
ROUTINES = ("hudorig",)


def origrev_routines(base: int, hudname_at: int, hudrev_at: int) -> dict[str, bytes]:
    """"hudorig" at `base` (see the module's docstring). `hudname_at`: the directory's `hudname`;
    `hudrev_at`: its text "hudrev" (Phase 32's REVERSE and a NUL)."""
    out: dict[str, bytes] = {}
    b = Block(base)
    b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)
    b.branch("be", "name")
    b.emit("cmp.b imm,abs", ORIGINALS_BELOW, MENU_INDEX)
    b.branch("bge", "name")
    b.emit("jsr abs", hudname.PRINTER)                      # the game's word, the printer entered as the site entered it; after it
                                                            # R1 is one past the word's 8th cell (row 44), R3 0
    b.emit("mov.w abs,reg", hudname.ATTR, "r2")             # the game's colour cell, kept on the stack (R2 is the printer's to write)
    b.emit("push reg", "r2")
    b.emit("mov.w imm,abs", hudname.REVERSE_ATTR, hudname.ATTR)
    b.emit("add.w imm,reg", hudname.REVERSE_STEP, "r1")     # row 46, the word's last letter under the 8th cell
    b.emit("cmp.b imm,abs", PADDED_FROM, MENU_INDEX)
    b.branch("blt", "word")                                 # BEGINNER fills the eight cells
    b.emit("sub.w imm,reg", 2, "r1")                        # " MEDIUM " and " EXPERT " end in a space: one cell left, under the M, the T
    b.label("word")
    b.emit("mov.w imm,reg", hudrev_at, "r0")
    b.emit("jsr abs", hudname.PRINTER)
    b.emit("pop reg", "r2")
    b.emit("mov.w reg,abs", "r2", hudname.ATTR)             # as `hudname`'s end: R2 the game's word, R3 0, R8 [0x50143c]
    b.emit("rsr")
    b.label("name")
    b.emit("jmp abs", hudname_at)
    out["hudorig"] = b.bytes()
    assert tuple(out) == ROUTINES
    return out


def origrev_layout(base: int, hudname_at: int = 0x100000, hudrev_at: int = 0x100000) -> dict[str, int]:
    lay, addr = {}, base
    for name, code in origrev_routines(base, hudname_at, hudrev_at).items():
        lay[name] = addr
        addr += len(code)
    lay["end"] = addr
    return lay


def install_origrev(rs: RomSet, base: int, hudname_at: int, hudrev_at: int) -> None:
    """The block at `base` (erased program ROM, 4-aligned) and its site, in place: HUD_SITE becomes `jsr hudorig` in place of
    the directory's `jsr hudname`; RANK_SITE must hold the game's own bytes (Phase 35: nothing gates the record any more).
    Everything is checked before anything is written; PatchError naming what is not as expected."""
    code = origrev_routines(base, hudname_at, hudrev_at)
    image = b"".join(code.values())
    lay = origrev_layout(base, hudname_at, hudrev_at)
    off = base - V60_PROGRAM
    if len(image) > BLOCK_BYTES or base % 4 or not (0 <= off and off + BLOCK_BYTES <= len(rs.program)):
        raise PatchError(f"the originals' reverse block: {len(image)} bytes at {base:#x} (the block is {BLOCK_BYTES} bytes of program ROM)")
    if any(x != 0xFF for x in rs.program[off:off + BLOCK_BYTES]):
        raise PatchError(f"program ROM at {base:#x} (+{BLOCK_BYTES}) is not erased for the originals' reverse block")
    have = rs.boot[RANK_SITE - V60_BOOT:RANK_SITE - V60_BOOT + len(RANK_PATTERN)]
    if have != RANK_PATTERN:
        raise PatchError(f"the race end's record site at {RANK_SITE:#x} is not the game's own: {have.hex()} (expected {RANK_PATTERN.hex()})")
    b = Block(hudname.HUD_SITE); b.emit("jsr abs", hudname_at)
    want = b.bytes()
    have = rs.boot[hudname.HUD_SITE - V60_BOOT:hudname.HUD_SITE - V60_BOOT + len(want)]
    if have != want:
        raise PatchError(f"HUD level word site at {hudname.HUD_SITE:#x} is not `jsr hudname`: {have.hex()} (expected {want.hex()})")
    prog = bytearray(rs.program)
    prog[off:off + len(image)] = image
    object.__setattr__(rs, "program", bytes(prog))
    b = Block(hudname.HUD_SITE); b.emit("jsr abs", lay["hudorig"])
    assert len(b.bytes()) == len(want)
    patch_span(rs, hudname.HUD_SITE, b.bytes(), len(want))
