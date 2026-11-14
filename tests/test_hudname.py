"""Phase 26 stage 3 (plan Task 6): the course's name in the race HUD, on the original set (read back from the installed image).

Pascal's request of 13 Nov (H1-H4): during a race on a converted course the HUD's bottom-right label reads the course's name
where the game prints BEGINNER / MEDIUM / EXPERT (the host template's word); the three originals keep the game's word. The site
is the label's printer call at 0xff4799 in 0xff471b, the HUD entity's first handler, run once at the race load: it becomes
`jsr hudname`. `hudname` asks the loader's lookup `entry` for the served load record; on an original (`race` 0) it enters the
game's printer 0xff8926 exactly as the site did; otherwise it prints the record's NUL-ended name right-aligned to the end of the
game's 8-cell field (the last letter in column 58), in the colour of the entry's select-screen level (LEVEL_ATTR by the record's
`label`), and puts the game's colour cell back."""
import pytest

from vrtools.arcade.directory import (LOAD_FIELDS, LOAD_SIZE, NAME_LEN, ORIGINALS, ReverseRecord, _decode_record,
                                      directory_layout, install_directory, maps_offset)
from vrtools.arcade.disasm import listing
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet
from dataclasses import replace

PRINTER = 0xFF8926                     # the game's 8 x 16 printer: R0 string, R1 first cell; the glyph from [0x501434] and [0x50143c]
ATTR = 0x501434                        # the colour cell the printer reads (a word: the game writes it with movz.bw)


def _ten():
    return (ORIGINALS * 4)[:10]


def _installed(romset_zip, d=None):
    rs = RomSet.from_zip(romset_zip)
    return rs, install_directory(rs, d or _ten()), directory_layout()


def _routine(out, lay, name):
    """The listing of what `install_directory` wrote at lay[name], up to the next address of the layout."""
    end = min(a for a in lay.values() if a > lay[name])
    return [l for l in listing(out, lay[name], end - lay[name]) if l.addr < end]


def test_the_hud_label_calls_hudname(romset_zip):
    """0xff4799 (`jsr FF8926[PC]`, 6 bytes, the label's print at the race load; no branch of the original boot ROM lands inside
    it) is `jsr hudname` installed, the instructions around it the original's; a changed site is refused naming it; the span is
    one of tests/test_directory.py's allowed spans."""
    from vrtools.arcade.hudname import HUD_PATTERN, HUD_SITE
    from tests.test_directory import SPANS
    rs, out, lay = _installed(romset_zip)
    at = HUD_SITE - 0xFC0000
    assert HUD_SITE == 0xFF4799 and HUD_PATTERN == bytes.fromhex("e8f28d410000") and rs.boot[at:at + 6] == HUD_PATTERN
    assert listing(rs, HUD_SITE, 1)[0].text == f"jsr     {PRINTER:X}[PC]"
    lines = [l for l in listing(out, HUD_SITE, 6) if l.addr < HUD_SITE + 6]
    assert [l.text for l in lines] == [f"jsr     {lay['hudname']:X}"] and len(lines[0].bytes) == 6
    assert listing(out, HUD_SITE + 6, 4) == listing(rs, HUD_SITE + 6, 4)
    assert (HUD_SITE, 6) in SPANS
    boot = bytearray(rs.boot)
    boot[at + 2] ^= 0x01                                                     # another printer
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match=f"{HUD_SITE:#x}"):
        install_directory(rs, _ten())


def test_every_load_record_name_ends_in_nul(romset_zip):
    """The load record's 14-byte name field (+0x1C) holds the name and NULs after it (the routine counts to the NUL), for the ten
    entries and a reverse variant; `_decode_record` gives the name back without them; names are at most 13 letters (NAME_LEN, the
    field's size, keeps a NUL)."""
    rs = RomSet.from_zip(romset_zip)
    lay = directory_layout()
    at = (lay["end"] + 0x43) // 4 * 4
    d = _ten()
    d[3] = replace(d[3], name="DIABLO CANYON")
    d[4] = replace(d[4], name="ALPINE", reverse=ReverseRecord(at, replace(d[4], name="ALPINE", header_base=0x150000, race=0x28F000,
                                                                              pit_quad=None)))
    out = install_directory(rs, d)
    name = LOAD_FIELDS["name"]
    assert NAME_LEN == 14 and LOAD_FIELDS["music"] == name + NAME_LEN
    records = [(lay["load"] + LOAD_SIZE * i, e.name) for i, e in enumerate(d)] + [(at, "ALPINE")]
    for rec, n in records:
        field = out.program[rec - 0x200000 + name:rec - 0x200000 + name + NAME_LEN]
        assert field == n.encode() + bytes(NAME_LEN - len(n)), (hex(rec), field)
        e = _decode_record(out.program, rec - 0x200000, rec - 0x200000 + maps_offset(), 0)
        assert e.name == n
    assert len("DIABLO CANYON") == NAME_LEN - 1
    for bad in ("DIABLO CANYONS", "A" * NAME_LEN):
        with pytest.raises(PatchError):
            install_directory(rs, [replace(e, name=bad) if i == 5 else e for i, e in enumerate(_ten())])
    with pytest.raises(PatchError):                                          # a variant's name too
        install_directory(rs, [replace(e, reverse=ReverseRecord(at, replace(e, name="A" * NAME_LEN, race=0x28F000, pit_quad=None)))
                               if i == 5 else e for i, e in enumerate(_ten())])


def _hudname(out, lay):
    """hudname's listing, its labels' addresses and the printer's two entries (the tail jump, the call)."""
    lines = _routine(out, lay, "hudname")
    return lines, [l.text for l in lines], {l.text: l.addr for l in lines}


def test_hudname_prints_the_games_word_on_an_original(romset_zip):
    """`hudname` saves R0, R1 and R8 (`pushm`), calls `entry` (R8 := the served load record; R0, R1 written), tests the record's
    `race` (+0x2C) against 0 and, on an original, restores the three (`popm`) and jumps to the printer: the printer is entered
    with the registers and the stack as the site's `jsr` left them (its `rsr` returns to 0xff479f), [0x501434] untouched. The
    printer reads no condition flag before its own `sha.h` sets them, and writes R8 before reading it."""
    from vrtools.arcade.hudname import SAVED
    rs, out, lay = _installed(romset_zip)
    assert SAVED == 0x103 and LOAD_FIELDS["race"] == 0x2C
    lines, texts, at = _hudname(out, lay)
    assert texts[:6] == ["pushm   #103", f"jsr     {lay['entry']:X}", "cmp.w   #0, 2C[R8]", f"bne     {lines[6].addr:X}",
                         "popm    #103", f"jmp     {PRINTER:X}"]
    assert [l.text for l in listing(rs, PRINTER, 4)] == ["movz.hw 50143C[PC], R8", "mov.w   501434[PC], R2", "sha.h   #7, R2",
                                                         "sub.w   #40, R2"]
    lines = _routine(out, lay, "entry")                                      # `entry` writes R0, R1 and R8 only (its exact listing:
    menu, done = lines[13].addr + 1, lines[-1].addr                           # a new write in it must meet this test, which guards
    assert [l.text for l in lines] == [                                       # `hudname`'s pushm #103)
        "movz.bw 501940, R8", "shl.w   #6, R8", f"add.w   #{lay['load']:X}, R8", "movz.bw 2[R8], R0", "movz.bw 501934, R1",
        "cmp.w   R0, R1", f"be      {menu:X}", "cmp.w   #3, R1", f"bge     {menu:X}",
        f"movz.bw {lay['fallback']:X}(R1), R8", "shl.w   #6, R8", f"add.w   #{lay['load']:X}, R8", "mov.w   #0, R0", "rsr",
        "mov.w   #0, R0", "cmp.b   #0, 502294", f"be      {done:X}", "movz.bw 501940, R1", f"mov.w   {lay['reverse']:X}(R1), R1",
        "cmp.w   #0, R1", f"be      {done:X}", "mov.w   R1, R8", "mov.w   #1, R0", "rsr"]


def test_hudname_prints_the_name_right_aligned_in_the_levels_colour(romset_zip):
    """On a converted course: R2 := the record (R2 and R3 are the printer's to write), R0, R1, R8 restored, R0 := the record +
    0x1C (the name), R1 := the site's R1 + 16 − 2 per letter up to the NUL (the last letter in the game's 8th cell, column 58: a
    13-letter name from column 46), [0x501434] (the word) pushed, := LEVEL_ATTR[label] (the record's +3: blue, orange, red) zero-
    extended as the game's own `movz.bw` writes it, the printer called, the pushed word written back (by R2, which nothing after
    the site reads before the entity loop writes it at 0xfe1c25), `rsr`. The printer leaves R1 one past the 8th cell, R3 0 and R8
    [0x50143c] as after the game's word; R0 is written at 0xff47b6 before any read."""
    from vrtools.arcade.hudname import LEVEL_ATTR
    rs, out, lay = _installed(romset_zip)
    assert LEVEL_ATTR == (0x02, 0x83, 0x82) and LOAD_FIELDS["label"] == 3 and LOAD_FIELDS["name"] == 0x1C
    lines, texts, at = _hudname(out, lay)
    count, done = at["cmp.b   #0, [R3]"], at[f"mov.w   {ATTR:X}, R3"]
    assert texts[6:] == ["mov.w   R8, R2", "popm    #103", "mov.w   R2, R0", "add.w   #1C, R0", "add.w   #10, R1", "mov.w   R0, R3",
                         "cmp.b   #0, [R3]", f"be      {done:X}", "sub.w   #2, R1", "add.w   #1, R3", f"br      {count:X}",
                         f"mov.w   {ATTR:X}, R3", "push    R3", "movz.bw 3[R2], R3", f"movz.bw {lay['hudattr']:X}(R3), {ATTR:X}",
                         f"jsr     {PRINTER:X}", "pop     R2", f"mov.w   R2, {ATTR:X}", "rsr"]
    assert lines[-1].addr + 1 == lay["hudattr"]
    assert out.program[lay["hudattr"] - 0x200000:lay["hudattr"] - 0x200000 + 3] == bytes(LEVEL_ATTR)
    assert lay["hudattr"] + 3 == lay["end"]
    assert [l.text for l in listing(rs, 0xFF479F, 3)] == ["mov.h   #51, 12[R25]", "mov.w   #5020C0, E[R25]", "movea.w 7000BA[PC], R1"]
    assert listing(rs, 0xFF47B6, 1)[0].text == "mov.w   #2F278E, R0"
    assert [l.text for l in listing(rs, 0xFE1C15, 5)][-1] == "mov.w   FD26E0[PC], R2"


def test_hudname_follows_the_direction_screens_routines(romset_zip):
    """The routine and its 3-byte table join the directory image after the direction screen's "dirtext" (plan D10's room); the
    image stays inside the 6 500-byte bound (tests/test_directory.py's; stage 4 Task 5, decision L2: 6 000 -> 6 500)."""
    from vrtools.arcade.dirscreen import LABELS, TITLE
    from vrtools.arcade.hudname import ROUTINES, hudname_size
    rs, out, lay = _installed(romset_zip)
    assert ROUTINES == ("hudname", "hudattr")
    assert lay["hudname"] == lay["dirtext"] + len(TITLE) + 1 + sum(len(t) + 1 for t in LABELS)
    assert lay["dirtext"] < lay["hudname"] < lay["hudattr"] < lay["end"] and lay["end"] - lay["hudname"] == hudname_size()
    assert lay["end"] - lay["loader"] < 6500
