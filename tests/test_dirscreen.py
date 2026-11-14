"""Phase 26 stage 3 (plan Task 1): room for the COURSE DIRECTION screen's code, the direction flag's life and the ranking gate,
on the original set (docs/spike/2026-11-phase26-stage3-recon.md §6-§8).

The flag `course.DIRECTION_RAM` is cleared with the screen's three cells whenever a select screen starts (mode 0x10 state 0,
STATE0_SITE, both screens and every cabinet) and at the two linked course loads (they call `bankdemo`, as the attract's two
do); a reverse race records nothing in the rankings (RANK_SITE calls `rankgate`).

Plan Task 2: the course lock hands the select entity to `dirsel` on an entry with a reverse variant (LOCK_SITE calls `dirlock`);
the wheel and a new gas press decide, the flag is written, and the game's lock handler takes the race on; `start` sends the
locked screen to `dirdone`.

Plan Task 3: `dirdraw` draws the screen over DRAW_PHASES logic frames (layer 0 cleared and layer 2's checker, the chosen
course's picture in slot 0's and slot 2's blocks on layer 2, then the game's maps, the title and the labels on layer 0); `picture`
(select.py) takes its destination and tile base from its caller. Plan Task 5: every drawing phase ends with its rows of
dirgfx's block (the game's maps, the caption, the arrows' characters, palettes and maps), the lap sense read from the entry's load
record. Every routine is read back from the installed image."""
import hashlib
import re

import pytest

from vrtools.arcade.course import BANK_SITES, DIRECTION_RAM
from vrtools.arcade.directory import ATTRACT_BANK_SITES, ORIGINALS, directory_layout, install_directory
from vrtools.arcade.disasm import listing
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet
from vrtools.arcade.v60asm import asm


def _installed(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    return rs, install_directory(rs, (ORIGINALS * 4)[:10]), directory_layout()


def _span(rs, site, n):
    """The instructions of `rs` inside [site, site + n)."""
    return [l for l in listing(rs, site, n) if l.addr < site + n]


def _routine(out, lay, name):
    """The listing of what `install_directory` wrote at lay[name], up to the next address of the layout (the next routine or
    table, or the image's end)."""
    end = min(a for a in lay.values() if a > lay[name])
    return [l for l in listing(out, lay[name], end - lay[name]) if l.addr < end]


def test_the_screen_cells_share_the_flags_word():
    """Plan D12: the flag stays the byte 0x502294; the word's three other bytes are the screen's."""
    from vrtools.arcade.dirscreen import DIR_ARMED, DIR_PHASE, DIR_SHOWN
    assert DIRECTION_RAM == 0x502294 and DIRECTION_RAM % 4 == 0
    assert (DIR_PHASE, DIR_ARMED, DIR_SHOWN) == (0x502295, 0x502296, 0x502297)


def test_the_state0_site_clears_the_flag_and_the_screen_cells(romset_zip):
    """Mode 0x10's state 0 (0xfe3cce, entered from the state table's `br FE3CCE` at 0xfe3cb9, the only branch to it) begins with
    `mov.b #0, 5019C0[PC]` (8 bytes): installed it is `jsr dirclear` and two nops; `dirclear` does the original's clear (the
    address absolute), clears the four bytes 0x502294..0x502297 and returns, with no register written."""
    from vrtools.arcade.dirscreen import STATE0_PATTERN, STATE0_SITE
    rs, out, lay = _installed(romset_zip)
    at = STATE0_SITE - 0xFC0000
    assert STATE0_SITE == 0xFE3CCE and len(STATE0_PATTERN) == 8 and rs.boot[at:at + 8] == STATE0_PATTERN
    assert listing(rs, STATE0_SITE, 1)[0].text == "mov.b   #0, 5019C0[PC]"
    lines = _span(out, STATE0_SITE, 8)
    assert lines[0].text == f"jsr     {lay['dirclear']:X}" and [l.text for l in lines[1:]] == ["nop", "nop"]
    assert listing(out, STATE0_SITE + 8, 3) == listing(rs, STATE0_SITE + 8, 3)
    texts = [l.text for l in _routine(out, lay, "dirclear")]
    assert texts == ["mov.b   #0, 5019C0", f"mov.w   #0, {DIRECTION_RAM:X}", "rsr"]
    assert not any(re.search(r"\bR\d+\b", t) for t in texts)


def test_the_rank_gate_skips_a_reverse_race(romset_zip):
    """At the race's end 0xfc40ce clears the record flag 0x5018fc and tests bit 1 of 0x501174 (the race finished); `be FC417C`
    (rsr) skips the setter and the record. Installed the two instructions (16 bytes, entered only from `jsr FC40CE[PC]` at
    0xfe4b49) are `jsr rankgate` and nops, and the `be` stays; `rankgate` clears 0x5018fc as the original, then returns with Z
    set when the flag is set (the flag compared with itself), else with the flags of the original `test1`."""
    from vrtools.arcade.dirscreen import RANK_PATTERN, RANK_SITE
    rs, out, lay = _installed(romset_zip)
    at = RANK_SITE - 0xFC0000
    assert RANK_SITE == 0xFC40CE and len(RANK_PATTERN) == 16 and rs.boot[at:at + 16] == RANK_PATTERN
    assert [l.text for l in listing(rs, RANK_SITE, 3)] == ["movz.bw #0, 5018FC[PC]", "test1   #1, 501174[PC]", "be      FC417C"]
    lines = _span(out, RANK_SITE, 16)
    assert lines[0].text == f"jsr     {lay['rankgate']:X}" and [l.text for l in lines[1:]] == ["nop"] * 10
    assert listing(out, RANK_SITE + 16, 1)[0].text == "be      FC417C"
    lines = _routine(out, lay, "rankgate")
    texts = [l.text for l in lines]
    assert texts == ["movz.bw #0, 5018FC", f"cmp.b   #0, {DIRECTION_RAM:X}", f"be      {lines[5].addr:X}",
                     f"cmp.b   {DIRECTION_RAM:X}, {DIRECTION_RAM:X}", "rsr", "test1   #1, 501174", "rsr"]


def test_the_linked_bank_sites_clear_the_flag(romset_zip):
    """Mode 5's linked course load (0xfe2b07) and a cabinet joining a linked race (0xfe1d37) call the routine the attract's two
    bank sites call, `bankdemo`, which is `bank` with the flag cleared first; mode 0x11's (0xfe415b) still calls `bank`."""
    from vrtools.arcade.dirscreen import LINKED_BANK_SITES
    rs, out, lay = _installed(romset_zip)
    assert LINKED_BANK_SITES == (0xFE2B07, 0xFE1D37) and set(LINKED_BANK_SITES) <= set(BANK_SITES)
    attract = {listing(out, site, 1)[0].text for site in ATTRACT_BANK_SITES}
    assert attract == {f"jsr     {lay['bankdemo']:X}"}
    for site in LINKED_BANK_SITES:
        assert out.boot[site - 0xFC0000:site - 0xFC0000 + 0x16] == asm("jsr abs", lay["bankdemo"]) + asm("nop") * (0x16 - 6), hex(site)
    assert listing(out, 0xFE415B, 1)[0].text == f"jsr     {lay['bank']:X}"
    assert [l.text for l in listing(out, lay["bankdemo"], 2)] == [f"mov.b   #0, {DIRECTION_RAM:X}", f"jmp     {lay['bank']:X}"]


@pytest.mark.parametrize("site,offset", [(0xFE3CCE, 2), (0xFC40CE, 11), (0xFE2B07, 0), (0xFE1D37, 0), (0xFC2788, 3)],
                         ids=["state0", "rank", "linked-mode5", "linked-join", "lock"])
def test_a_changed_site_is_refused(romset_zip, site, offset):
    rs = RomSet.from_zip(romset_zip)
    boot = bytearray(rs.boot)
    boot[site - 0xFC0000 + offset] ^= 0x01                       # state 0: #1 for #0; rank: test1 #0; linked: another opcode; lock: another handler
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match=f"{site:#x}"):
        install_directory(rs, (ORIGINALS * 4)[:10])


def test_the_course_lock_calls_dirlock(romset_zip):
    """The course lock handler 0xfc277c sets the timer to 0x20, then at 0xfc2788 the handler 0xfc27be (9 bytes, entered only
    through 0xfc277c's first byte): installed it is `jsr dirlock` and three nops, the instructions around it the original's.
    `dirlock` installs 0xfc27be exactly as the original (the same 9 bytes) in linked play ([0x40dc8c] != 0), on the direction
    lock's own pass (DIR_PHASE != 0) and when the reverse table's word for [0x501940] is 0; else the handler `dirsel`, the timer
    DIR_TIMER, DIR_PHASE 1, DIR_ARMED 0, DIR_SHOWN 0xff and the flag 0. Only R0 is used, pushed and popped."""
    from vrtools.arcade.dirscreen import DIR_ARMED, DIR_PHASE, DIR_SHOWN, DIR_TIMER, LOCK_PATTERN, LOCK_SITE
    rs, out, lay = _installed(romset_zip)
    at = LOCK_SITE - 0xFC0000
    assert LOCK_SITE == 0xFC2788 and LOCK_PATTERN == asm("mov.w imm,disp[reg]", 0xFC27BE, 0xA, "r25") and rs.boot[at:at + 9] == LOCK_PATTERN
    assert DIR_TIMER == 0x140
    assert [l.text for l in listing(rs, 0xFC277C, 2)] == ["mov.w   #20, 50113C[PC]", "mov.w   #FC27BE, A[R25]"]
    lines = _span(out, LOCK_SITE, 9)
    assert lines[0].text == f"jsr     {lay['dirlock']:X}" and [l.text for l in lines[1:]] == ["nop"] * 3
    assert listing(out, 0xFC277C, 1) == listing(rs, 0xFC277C, 1) and listing(out, LOCK_SITE + 9, 6) == listing(rs, LOCK_SITE + 9, 6)
    lines = _routine(out, lay, "dirlock")
    texts = [l.text for l in lines]
    orig = next(l for l in lines if l.text == "mov.w   #FC27BE, A[R25]")
    assert orig.bytes == LOCK_PATTERN
    assert texts == ["push    R0",
                     "cmp.b   #0, 40DC8C", f"bne     {orig.addr:X}",
                     f"cmp.b   #0, {DIR_PHASE:X}", f"bne     {orig.addr:X}",
                     "movz.bw 501940, R0", f"mov.w   {lay['reverse']:X}(R0), R0", "cmp.w   #0, R0", f"be      {orig.addr:X}",
                     f"mov.w   #{lay['dirsel']:X}, A[R25]", f"mov.w   #140, 50113C",
                     f"mov.b   #1, {DIR_PHASE:X}", f"mov.b   #0, {DIR_ARMED:X}", f"mov.b   #FF, {DIR_SHOWN:X}", f"mov.b   #0, {DIRECTION_RAM:X}",
                     "pop     R0", "rsr",
                     "mov.w   #FC27BE, A[R25]", "pop     R0", "rsr"]


def test_dirsel_chooses_and_locks(romset_zip):
    """`dirsel`, every logic frame in 0xfc26c5's place: while DIR_SHOWN is above DRAWN (unsigned: 0xff from `dirlock`, then one
    value a drawing phase, Task 3) it calls `dirdraw` and returns, nothing else; then R10 = ([0x501060] + [0x50106c]) >> 1 as
    0xfc26c5 computes it; D6: armed once R10 <= THRESHOLD, then the choice is R10 > THRESHOLD; the choice to DIR_SHOWN with
    `dirshow` on a change (DRAWN is neither choice, so the first frame after the drawing writes it); `dircursor`; the lock on a gas
    edge or the timer at or below 0x20 (0xfc26c5's tests): the flag := DIR_SHOWN, DIR_PHASE := 2, the handler := the game's lock
    handler 0xfc277c (it sets the timer to 0x20 on the next logic frame and, through `dirlock`, the handler 0xfc27be). So
    `dircursor` and the lock only ever see DIR_SHOWN 0 or 1."""
    from vrtools.arcade.dirscreen import DIR_ARMED, DIR_PHASE, DIR_SHOWN, DRAWN, THRESHOLD
    rs, out, lay = _installed(romset_zip)
    assert THRESHOLD == 0x1C and DRAWN not in (0, 1) and DRAWN >= 0x80
    lines = _routine(out, lay, "dirsel")
    texts = [l.text for l in lines]
    at = {t: lines[k].addr for k, t in enumerate(texts)}
    l1, l2, l3 = at["mov.w   501060, R10"], at["mov.w   #0, R11"], at[f"cmp.b   R11, {DIR_SHOWN:X}"]
    l4, lock, done = at[f"jsr     {lay['dircursor']:X}"], at[f"mov.b   {DIR_SHOWN:X}, {DIRECTION_RAM:X}"], lines[-1].addr
    assert texts == [f"cmp.b   #{DRAWN:X}, {DIR_SHOWN:X}", f"bnh     {l1:X}", f"jsr     {lay['dirdraw']:X}", "rsr",
                     "mov.w   501060, R10", "add.w   50106C, R10", "sha.w   #FF, R10",
                     "cmp.w   #1C, R10", f"bgt     {l2:X}", f"mov.b   #1, {DIR_ARMED:X}",
                     "mov.w   #0, R11", f"cmp.b   #0, {DIR_ARMED:X}", f"be      {l3:X}", "cmp.w   #1C, R10", f"ble     {l3:X}", "mov.w   #1, R11",
                     f"cmp.b   R11, {DIR_SHOWN:X}", f"be      {l4:X}", f"mov.b   R11, {DIR_SHOWN:X}", f"jsr     {lay['dirshow']:X}",
                     f"jsr     {lay['dircursor']:X}",
                     "cmp.w   #0, 501078", f"bne     {lock:X}", "cmp.w   #20, 50113C", f"bgt     {done:X}",
                     f"mov.b   {DIR_SHOWN:X}, {DIRECTION_RAM:X}", f"mov.b   #2, {DIR_PHASE:X}", "mov.w   #FC277C, A[R25]",
                     "rsr"]


def test_dircursor_draws_the_games_frame_at_the_chosen_side(romset_zip):
    """`dircursor`: 0xfc2887's first three instructions (`mov.w #3, R0; jsr FF8474; mov.w #502150, E[R25]`), R13 on the
    position record of DIR_SHOWN in "dirsides" (x, y floats: (SIDE_X[side], SIDE_Y)), then `jmp FC28A7`, the game's cursor frame
    from its read of R13 on (its `rsr` returns to the caller). `dirdone` (from `start` while DIR_PHASE != 0) ends in it (Task 4's
    test below)."""
    import struct
    from vrtools.arcade.dirscreen import DIR_SHOWN, SIDE_X, SIDE_Y
    rs, out, lay = _installed(romset_zip)
    assert (SIDE_X, SIDE_Y) == ((-112.0, 112.0), 65.0)
    assert [l.text for l in listing(rs, 0xFC2887, 5)] == ["mul.w   #18, R11", "mov.w   #3, R0", "jsr     FF8474[PC]",
                                                          "mov.w   #502150, E[R25]", "movea.b FC35C7[R11], R13"]
    assert listing(rs, 0xFC28A7, 1)[0].text == "mov.w   E[R25], R14"
    assert [l.text for l in _routine(out, lay, "dircursor")] == [
        "mov.w   #3, R0", "jsr     FF8474", "mov.w   #502150, E[R25]",
        f"movz.bw {DIR_SHOWN:X}, R13", "shl.w   #3, R13", f"add.w   #{lay['dirsides']:X}, R13", "jmp     FC28A7"]
    off = lay["dirsides"] - 0x200000
    assert struct.unpack_from("<4f", out.program, off) == (SIDE_X[0], SIDE_Y, SIDE_X[1], SIDE_Y)
    assert lay["dirsides"] + 16 == min(a for a in lay.values() if a > lay["dirsides"])


def test_dirsel_never_writes_the_transmission(romset_zip):
    """Review Focus 4: the transmission the course select latched in 0x501936 (0xfc26c5 through 0xfc31e4, START held with the
    gas) survives the screen: no instruction of `dirlock`, `dirsel`, `dirdone`, `dircursor` references 0x501936 or calls
    0xfc31e4."""
    rs, out, lay = _installed(romset_zip)
    for name in ("dirlock", "dirsel", "dirdone", "dircursor"):
        texts = [l.text for l in _routine(out, lay, name)]
        assert texts and not any("501936" in t or "FC31E4" in t for t in texts), (name, texts)


# select._start as it was before the direction screen (d6768f7): its bytes are position independent (relative branches inside
# it, the directory's tables and 0xfc2880 absolute), so the body after the phase test must be these bytes
START_BEFORE = (227, "f6c89fe0b4e24334a8f66c589396fc221f131e829c0a7a0c02936e2a87bf1486")


def test_start_branches_on_the_phase(romset_zip):
    """`start`, jumped to from 0xfc27d6 every logic frame while the handler is 0xfc27be, begins with a test of DIR_PHASE:
    non-zero, `jmp dirdone`; zero, today's body byte for byte."""
    from vrtools.arcade.dirscreen import DIR_PHASE
    rs, out, lay = _installed(romset_zip)
    lines = _routine(out, lay, "start")
    assert [l.text for l in lines[:3]] == [f"cmp.b   #0, {DIR_PHASE:X}", f"be      {lines[3].addr:X}", f"jmp     {lay['dirdone']:X}"]
    end = min(a for a in lay.values() if a > lay["start"])
    body = out.program[lines[3].addr - 0x200000:end - 0x200000]
    assert (len(body), hashlib.sha256(body).hexdigest()) == START_BEFORE



# --- Task 3: the screen drawn ------------------------------------------------------------------------------------------------
def test_the_screen_layout():
    """Plan D1-D4: the two pictures (16 x 21 tiles) at rows 4-24, columns 9-24 and 37-52; the title's 32 columns at rows 1-3 from
    column 15; the labels (12 and 14 columns) at rows 26-28 under their pictures; Task 5's 12 x 12 arrows on the pictures; the
    game's maps: the double arrow centred between the pictures, the wheel panel, the red arrow and STEP TO START! where the
    SHIFT MODE SELECTOR has them. No two pieces share a cell, and every piece is on the 62 x 48 visible tiles. tile_address is
    the tile RAM address of a layer's cell (layer stride 0x2000, row 0x80, column 2: the course select's slots)."""
    from vrtools.arcade.dirscreen import (ARROW_CELLS, LABEL_CELLS, LABELS, MAPS, PICTURE_CELLS, PICTURE_SIZE, TITLE, TITLE_CELL,
                                          tile_address)
    from vrtools.arcade.select import SLOT_A, SLOT_B
    assert PICTURE_CELLS == ((4, 9), (4, 37)) and TITLE_CELL == (1, 15) and LABEL_CELLS == ((26, 11), (26, 38))
    assert ARROW_CELLS == ((8, 11), (8, 39)) and PICTURE_SIZE == (21, 16)
    assert [tile_address(0, 1, 4 + 19 * s) for s in range(3)] == list(SLOT_B) and [tile_address(2, 1, 4 + 19 * s) for s in range(3)] == list(SLOT_A)
    assert (TITLE, LABELS) == ("COURSE DIRECTION", ("NORMAL", "REVERSE"))
    pieces = {"title": (TITLE_CELL, (3, 2 * len(TITLE))), **{f"label{k}": (LABEL_CELLS[k], (3, 2 * len(LABELS[k]))) for k in (0, 1)},
              **{f"map{m:X}": (cell, size) for m, cell, size in MAPS}}
    assert dict((m, (cell, size)) for m, cell, size in MAPS) == {0x1E2205: ((10, 28), (8, 6)), 0x1E0F71: ((30, 7), (13, 20)),
                                                                    0x1E1185: ((32, 28), (5, 6)), 0x1E13E1: ((30, 35), (13, 20))}
    cells = {}
    for name, ((r, c), (h, w)) in pieces.items():
        assert 0 <= r and r + h <= 48 and 0 <= c and c + w <= 62, name
        for cell in ((r + i, c + j) for i in range(h) for j in range(w)):
            assert cell not in cells, (name, cells.get(cell), cell)
            cells[cell] = name
    pictures = [{(r + i, c + j) for i in range(21) for j in range(16)} for r, c in PICTURE_CELLS]
    assert not pictures[0] & pictures[1] and not (pictures[0] | pictures[1]) & set(cells)    # (layer 2 against layer 0: no overlap anyway)
    for k, (r, c) in enumerate(LABEL_CELLS):                                                     # each label under its picture, centred
        assert r == PICTURE_CELLS[k][0] + 22 and abs((c + len(LABELS[k])) - (PICTURE_CELLS[k][1] + 8)) <= 1, k
    for k, (r, c) in enumerate(ARROW_CELLS):
        assert {(r + i, c + j) for i in range(12) for j in range(12)} <= pictures[k], k
    for tile in (0x7013B8, 0x701438):                         # the game's countdown (rows 3 x columns 4) on either [0x40dc9b] setting
        r, c = (tile - 0x700000) // 0x80, (tile - 0x700000) % 0x80 // 2
        assert not {(r + i, c + j) for i in range(3) for j in range(4)} & set(cells), hex(tile)
    (ra, ca), (ha, wa) = pieces["map1E2205"]
    assert (2 * ra + ha - 1) / 2 - (PICTURE_CELLS[0][0] + 10) in (-0.5, 0, 0.5)                 # centred on the pictures' rows ...
    assert ca - (PICTURE_CELLS[0][1] + 16) == PICTURE_CELLS[1][1] - (ca + wa)                  # ... and in the gap between them


def test_the_maps_are_the_games(romset_zip):
    """The four maps' sizes (rows, columns) are the original data ROM's (bank 0, mapped on the select screens)."""
    from vrtools.arcade.dirscreen import MAPS
    from vrtools.arcade.panel import decode_panel
    rs = RomSet.from_zip(romset_zip)
    for m, cell, size in MAPS:
        p = decode_panel(rs, m)
        assert (p.rows, p.cols) == size and p.base == 0x8000 and p.mode == 1, hex(m)


def test_dirdraw_draws_one_phase_a_logic_frame(romset_zip):
    """`dirdraw` (from `dirsel` while DIR_SHOWN is above DRAWN) runs the phase DIR_SHOWN names and steps DIR_SHOWN down by one:
    0xff layer 0 cleared (0xff92c9), layer 2's checker redrawn (0xfc358e: the slot overlays go), the title (0xff870d) and both
    labels white (0xffe8fb); 0xfe / 0xfd the chosen entry's picture record (lay["pictures"][[0x501940]]; none: nothing) through
    `picture` into slot 0's / slot 2's blocks and palettes, its map on layer 2 at PICTURE_CELLS[0] / [1] with the slot's tile base;
    0xfc and below no picture. The labels are `dirshow`'s (Task 4): called with DIR_SHOWN 0xff, neither choice, it prints both
    white. Task 5: every phase then runs its rows of dirgfx's block (test_dirgfx: the game's maps and the caption in 0xff, the
    arrows' characters in 0xfc and 0xfb, their palettes and maps in 0xfa): R9 = the block's start + PHASE_BYTES * (DIR_SHOWN -
    DRAW_PHASES[-1]); R8 = the chosen entry's load record's SENSE_FIELD (the record at lay["load"] + 64 * [0x501940]: the index
    times 16, scaled by the word); per row up to one with source 0: R0 = source, R1 = destination plus the row's swap when R8 is
    not 0, then count 0: the blit 0xff9436 (R0 map, R1 tile address), else `count` longwords from [R0] to [R1]. The registers it
    uses outside R0 and R10-R14 (what the game's own handler 0xfc26c5 clobbers) are saved with one pushm (the blit writes R1 and
    R7, keeps R0 and R2-R6)."""
    from vrtools.arcade.dirgfx import PHASE_BYTES, ROW_BYTES, block_start
    from vrtools.arcade.dirscreen import DIR_SHOWN, DRAW_PHASES, DRAWN, LABEL_WHITE, PICTURE_CELLS, SENSE_FIELD, TITLE_CELL, tile_address
    rs, out, lay = _installed(romset_zip)
    assert DRAW_PHASES == (0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA) and DRAWN == 0xF9 and LABEL_WHITE == 0x8200 and (PHASE_BYTES, ROW_BYTES) == (128, 16)
    lines = _routine(out, lay, "dirdraw")
    texts = [l.text for l in lines]
    at = {t: lines[k].addr for k, t in enumerate(texts)}
    pics, rows, slot = at["cmp.b   #FC, 502297"], at[f"movz.bw {DIR_SHOWN:X}, R9"], at[f"mov.w   {lay['slot_tile']:X}(R10), R13"]
    row, kept, copy = at["mov.w   [R9], R0"], at["mov.w   8[R9], R2"], at["mov.w   [R0], [R1]"]
    nxt, step = at["add.w   #10, R9"], at[f"movz.bw {DIR_SHOWN:X}, R0"]
    text = lay["dirtext"]
    assert texts == ["pushm   #38E",
                     f"cmp.b   #FF, {DIR_SHOWN:X}", f"bne     {pics:X}",
                     "mov.w   #700000, R0", "jsr     FF92C9", "jsr     FC358E",
                     f"mov.w   #{text:X}, R0", f"mov.w   #{tile_address(0, *TITLE_CELL):X}, R1", "jsr     FF870D",
                     f"jsr     {lay['dirshow']:X}", f"br      {rows:X}",
                     f"cmp.b   #FC, {DIR_SHOWN:X}", f"bnh     {rows:X}",
                     "movz.bw 501940, R11", f"mov.w   {lay['pictures']:X}(R11), R11", "cmp.w   #0, R11", f"be      {rows:X}",
                     "mov.w   #0, R10", f"mov.w   #{tile_address(2, *PICTURE_CELLS[0]):X}, R12", f"cmp.b   #FE, {DIR_SHOWN:X}", f"be      {slot:X}",
                     "mov.w   #2, R10", f"mov.w   #{tile_address(2, *PICTURE_CELLS[1]):X}, R12",
                     f"mov.w   {lay['slot_tile']:X}(R10), R13", f"jsr     {lay['picture']:X}",
                     f"movz.bw {DIR_SHOWN:X}, R9", "shl.w   #7, R9", f"add.w   #{block_start() - PHASE_BYTES * 0xFA:X}, R9",
                     "movz.bw 501940, R8", "shl.w   #4, R8", f"mov.w   {lay['load'] + SENSE_FIELD:X}(R8), R8",
                     "mov.w   [R9], R0", "cmp.w   #0, R0", f"be      {step:X}",
                     "mov.w   4[R9], R1", "cmp.w   #0, R8", f"be      {kept:X}", "add.w   C[R9], R1",
                     "mov.w   8[R9], R2", "cmp.w   #0, R2", f"bne     {copy:X}", "jsr     FF9436", f"br      {nxt:X}",
                     "mov.w   [R0], [R1]", "add.w   #4, R0", "add.w   #4, R1", "sub.w   #1, R2", f"bne     {copy:X}",
                     "add.w   #10, R9", f"br      {row:X}",
                     f"movz.bw {DIR_SHOWN:X}, R0", "sub.w   #1, R0", f"mov.b   R0, {DIR_SHOWN:X}",
                     "popm    #38E", "rsr"]
    assert listing(rs, 0xFF9436, 1)[0].text == "pushm   #7D"                   # the blit keeps R0, R2-R6


def test_the_lap_sense_is_the_hud_maps_cross_shift():
    """The entry's lap sense `dirdraw` reads is its load record's map_cross (directory.LOAD_FIELDS, a 32-bit field): non-zero
    exactly when the lap is anticlockwise (tencourse.convert_course: MAP_CROSS_SHIFTED when `interior_on_the_left`, else 0)."""
    from vrtools.arcade.directory import LOAD_FIELDS, LOAD_FORMAT
    from vrtools.arcade.dirscreen import SENSE_FIELD
    from vrtools.arcade.tencourse import MAP_CROSS_SHIFTED
    import struct
    assert SENSE_FIELD == LOAD_FIELDS["map_cross"] and MAP_CROSS_SHIFTED != 0
    assert struct.calcsize(LOAD_FORMAT[:LOAD_FORMAT.index("f") + 1]) == SENSE_FIELD and LOAD_FORMAT[LOAD_FORMAT.index("f") + 1] == "I"


def test_dirdraw_tables(romset_zip):
    """"dirtext": the title and the two labels, each ended by a NUL (the printers stop there), right after "dirsides"; the screen's
    routines end there (Task 5: the game's maps, before "dirmaps" here, are rows of dirgfx's block; Task 6: the HUD name's
    `hudname` follows)."""
    from vrtools.arcade.dirscreen import LABELS, ROUTINES, TITLE
    rs, out, lay = _installed(romset_zip)
    assert "dirmaps" not in lay and ROUTINES[-2:] == ("dirsides", "dirtext")
    blob = (TITLE + "\0" + LABELS[0] + "\0" + LABELS[1] + "\0").encode()
    assert lay["dirtext"] == lay["dirsides"] + 16 and out.program[lay["dirtext"] - 0x200000:lay["dirtext"] - 0x200000 + len(blob)] == blob
    assert lay["dirtext"] + len(blob) == lay["hudname"]


# --- Task 4: the choice shown, and the lock look ------------------------------------------------------------------------------
def test_dirshow_prints_the_choice_yellow(romset_zip):
    """`dirshow` (from `dirsel` after each change of DIR_SHOWN, and from `dirdraw`'s first phase with DIR_SHOWN 0xff) prints the two
    labels of "dirtext" at LABEL_CELLS through the ranking titles' printer 0xffe8fb, one loop pass a label k (0 NORMAL, 1
    REVERSE): the attribute LABEL_YELLOW when k is DIR_SHOWN, else LABEL_WHITE (plan D4), pushed with the tile address and the
    string as `ranking.print_call` pushes them, then `ranking.STRING_CALL` (the call and the pop of the 12 bytes). So the two
    labels' attributes swap with the choice, and with DIR_SHOWN 0xff both are white. It writes R0, R12-R14 only (the printer saves
    what it uses): `dirsel`'s and `dirdraw`'s callers let the game's handler clobber R0 and R10-R14."""
    from vrtools.arcade.dirscreen import DIR_SHOWN, LABEL_CELLS, LABEL_WHITE, LABEL_YELLOW, LABELS, TITLE, tile_address
    from vrtools.arcade.ranking import STRING_CALL, STRING_PRINT
    rs, out, lay = _installed(romset_zip)
    assert (LABEL_WHITE, LABEL_YELLOW) == (0x8200, 0xC200) and LABEL_CELLS[1][0] == LABEL_CELLS[0][0]
    lines = _routine(out, lay, "dirshow")
    texts = [l.text for l in lines]
    at = {t: lines[k].addr for k, t in enumerate(texts)}
    loop, white = at["mov.h   #8200, R0"], at["push    R0"]
    first = lay["dirtext"] + len(TITLE) + 1
    assert texts == [f"mov.w   #{tile_address(0, *LABEL_CELLS[0]):X}, R12", f"mov.w   #{first:X}, R13", "mov.w   #0, R14",
                     "mov.h   #8200, R0", f"cmp.b   R14, {DIR_SHOWN:X}", f"bne     {white:X}", "mov.h   #C200, R0",
                     "push    R0", "push    R12", "push    R13", f"call    {STRING_PRINT:X}, [SP]", "add.w   #C, SP",
                     f"add.w   #{2 * (LABEL_CELLS[1][1] - LABEL_CELLS[0][1]):X}, R12", f"add.w   #{len(LABELS[0]) + 1:X}, R13",
                     "add.w   #1, R14", "cmp.w   #2, R14", f"bne     {loop:X}", "rsr"]
    call = next(l for l in lines if l.text.startswith("call"))
    assert out.program[call.addr - 0x200000:call.addr - 0x200000 + len(STRING_CALL)] == STRING_CALL
    assert listing(rs, STRING_PRINT, 1)[0].text == "pushm   #E00406"          # R1, R2, R10, R21-R23: R0, R12-R14 survive it ...
    assert listing(rs, STRING_PRINT + 0x69, 2)[1].text == "ret     #0"         # ... and the caller pops the arguments


def test_dirdone_greys_the_picture_not_chosen(romset_zip):
    """`dirdone` (from `start` every logic frame after the direction lock, while DIR_PHASE != 0): with the chosen entry's picture
    record (lay["pictures"][[0x501940]], as `dirdraw` takes it; none: the cursor only), per side k (0 NORMAL: slot 0, 1 REVERSE:
    slot 2) the slot's 48 palette words (select.SLOT_PAL) := the record's `chosen` set when k is DIR_SHOWN (the flag's value
    since the lock), else its `grey` set (select.REC's fields, as `start` gives the course select's slots), one halfword a pass;
    then it falls into `dircursor` (the next routine), the game's frame, steady now that the handler is 0xfc27be. It writes R10-R14
    only (`start` runs in the select entity's handler context)."""
    from vrtools.arcade.dirscreen import DIR_SHOWN
    from vrtools.arcade.select import REC, SLOT_PAL
    rs, out, lay = _installed(romset_zip)
    assert (REC["chosen"], REC["grey"]) == (12, 16) and SLOT_PAL[0] == 0x900CC0 and SLOT_PAL[2] - SLOT_PAL[0] == 2 * 96
    lines = _routine(out, lay, "dirdone")
    texts = [l.text for l in lines]
    at = {t: lines[k].addr for k, t in enumerate(texts)}
    side, pick, copy = at["movz.bw #10, R12"], at["add.w   R11, R12"], at["mov.h   [R12], [R13]"]
    assert texts == ["movz.bw 501940, R11", f"mov.w   {lay['pictures']:X}(R11), R11", "cmp.w   #0, R11", f"be      {lay['dircursor']:X}",
                     "mov.w   #900CC0, R13", "mov.w   #0, R10",
                     "movz.bw #10, R12", f"cmp.b   R10, {DIR_SHOWN:X}", f"bne     {pick:X}", "mov.w   #C, R12",
                     "add.w   R11, R12", "mov.w   [R12], R12", "movz.bw #30, R14",
                     "mov.h   [R12], [R13]", "add.w   #2, R12", "add.w   #2, R13", "sub.w   #1, R14", f"bne     {copy:X}",
                     "add.w   #60, R13", "add.w   #1, R10", "cmp.w   #2, R10", f"bne     {side:X}"]
    assert lines[-1].addr + len(lines[-1].bytes) == lay["dircursor"]          # falls into dircursor
