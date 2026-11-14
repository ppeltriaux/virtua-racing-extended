"""The V60 encoder emits exactly the instruction unidasm reads back (one instruction, nothing left over)."""
import pytest

from vrtools.arcade.disasm import listing_bytes
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet
from vrtools.arcade.v60asm import Block, asm
from vrtools.arcade.codepatch import patch_span

FORMS = [
    ("mov.w abs,reg", (0x501940, "r10"), "mov.w 501940, R10"),
    ("mov.w reg,abs", ("r27", 0x5017F4), "mov.w R27, 5017F4"),
    ("mov.w imm,reg", (5, "r19"), "mov.w #5, R19"),
    ("mov.w imm,reg", (0x278D70, "r1"), "mov.w #278D70, R1"),
    ("mov.w imm,reg", (-1, "r1"), "mov.w #FFFFFFFF, R1"),
    ("mov.w imm,[reg]", (0x6800000, "r24"), "mov.w #6800000, [R24]"),
    ("mov.w imm,[reg]", (0, "r24"), "mov.w #0, [R24]"),
    ("mov.w reg,[reg]", ("r10", "r24"), "mov.w R10, [R24]"),
    ("mov.w disp[reg],reg", (0x18, "r25", "r0"), "mov.w 18[R25], R0"),
    ("mov.w disp[reg],reg", (0x1F2, "r19", "r0"), "mov.w 1F2[R19], R0"),
    ("mov.w [reg],reg", ("r10", "r1"), "mov.w [R10], R1"),
    ("mov.w [reg],abs", ("r11", 0x501954), "mov.w [R11], 501954"),
    ("mov.w [reg],[reg]", ("r0", "r1"), "mov.w [R0], [R1]"),                  # stage 3 Task 5: dirdraw's rows
    ("add.w disp[reg],reg", (0xC, "r9", "r1"), "add.w C[R9], R1"),
    ("mov.w abs,abs", (0x40D804, 0x40D808), "mov.w 40D804, 40D808"),
    ("mov.w abs(reg),reg", (0x278E00, "r10", "r0"), "mov.w 278E00(R10), R0"),
    ("mov.w abs(reg),abs", (0x278E00, "r10", 0x501948), "mov.w 278E00(R10), 501948"),
    ("mov.b reg,abs", ("r0", 0xE00004), "mov.b R0, E00004"),
    ("mov.b abs,reg", (0xC0001E, "r0"), "mov.b C0001E, R0"),
    ("mov.b imm,abs", (2, 0x501934), "mov.b #2, 501934"),
    ("mov.b reg,abs(reg)", ("r3", 0x40FC6A, "r0"), "mov.b R3, 40FC6A(R0)"),
    ("mov.h reg,abs", ("r0", 0x70A000), "mov.h R0, 70A000"),
    ("mov.h abs(reg),reg", (0x278E40, "r0", "r0"), "mov.h 278E40(R0), R0"),
    ("movz.bw abs,reg", (0x501934, "r0"), "movz.bw 501934, R0"),
    ("movz.bw disp[reg],reg", (3, "r12", "r13"), "movz.bw 3[R12], R13"),
    ("movz.bw abs(reg),reg", (0x278E80, "r10", "r0"), "movz.bw 278E80(R10), R0"),
    ("movz.hw disp[reg],reg", (0x36, "r25", "r0"), "movz.hw 36[R25], R0"),
    ("mul.w imm,reg", (0x18, "r11"), "mul.w #18, R11"),
    ("add.w imm,reg", (0x7006AC, "r1"), "add.w #7006AC, R1"),
    ("add.w reg,reg", ("r1", "r1"), "add.w R1, R1"),
    ("shl.w imm,reg", (2, "r0"), "shl.w #2, R0"),
    ("shl.w imm,reg", (-4, "r1"), "shl.w #FC, R1"),
    ("cmp.w imm,reg", (0x5DC, "r0"), "cmp.w #5DC, R0"),
    ("cmp.w reg,reg", ("r11", "r12"), "cmp.w R11, R12"),
    ("cmp.h imm,abs", (3, 0x501940), "cmp.h #3, 501940"),
    ("cmp.b imm,abs", (9, 0x501940), "cmp.b #9, 501940"),
    ("sub.w reg,reg", ("r1", "r0"), "sub.w R1, R0"),
    ("and.w imm,reg", (0xFF, "r10"), "and.w #FF, R10"),
    ("or.w imm,reg", (1, "r0"), "or.w #1, R0"),
    ("sha.w imm,reg", (-1, "r10"), "sha.w #FF, R10"),
    ("jsr abs", (0xFF8926,), "jsr FF8926"),
    ("jmp abs", (0xFE1054,), "jmp FE1054"),
    ("rsr", (), "rsr"),
    ("nop", (), "nop"),
    ("push reg", ("r25",), "push R25"),
    ("pop reg", ("r25",), "pop R25"),
    ("pushm imm", (0x38E,), "pushm #38E"),
    ("popm imm", (0x38E,), "popm #38E"),
]


@pytest.mark.parametrize("form,args,text", FORMS, ids=[f[0] + str(f[1]) for f in FORMS])
def test_every_form_disassembles_as_intended(form, args, text):
    blob = asm(form, *args)
    lines = listing_bytes(blob, 0x278D70)
    assert len(lines) == 1 and lines[0].text.split() == text.split() and len(lines[0].bytes) == len(blob)


@pytest.mark.parametrize("cond,target,text", [("be", 0x278D83, "be 278D83"), ("bne", 0x278D00, "bne 278D00"),
                                              ("br", 0x278E70, "br 278E70"), ("bgt", 0x27A000, "bgt 27A000"),
                                              ("ble", 0x278D70, "ble 278D70"), ("bnh", 0x278D90, "bnh 278D90"),
                                              ("bh", 0x278D60, "bh 278D60")])
def test_branches_are_relative_to_their_own_address(cond, target, text):
    blob = asm(cond, 0x278D70, target)                                   # (own address, target)
    [line] = listing_bytes(blob, 0x278D70)
    assert line.text.split() == text.split() and len(blob) == (2 if -128 <= target - 0x278D70 < 128 else 3)


def test_block_resolves_labels_and_branch_sizes():
    b = Block(0x278D70)
    b.emit("cmp.w imm,reg", 3, "r0")
    b.branch("ble", "done")
    b.emit("mov.w imm,reg", 1, "r0")
    b.label("done")
    b.emit("rsr")
    b.label("far")
    ls = listing_bytes(b.bytes(), 0x278D70)
    assert [l.text.split()[0] for l in ls] == ["cmp.w", "ble", "mov.w", "rsr"]
    assert ls[1].text.split()[1] == f"{b.addr('done'):X}" and b.addr("far") == 0x278D70 + len(b.bytes())
    b2 = Block(0x278D70)
    b2.branch("br", "end"); b2.emit("nop")
    for _ in range(100):
        b2.emit("mov.w imm,reg", 0x12345678, "r1")
    b2.label("end"); b2.emit("rsr")
    ls2 = listing_bytes(b2.bytes(), 0x278D70)
    assert ls2[0].text.split() == ["br", f"{b2.addr('end'):X}"] and len(ls2[0].bytes) == 3    # 16-bit branch


def test_patch_span_is_exact_length(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    before = rs.boot
    off = 0xFE48ED - 0xFC0000
    patch_span(rs, 0xFE48ED, asm("jsr abs", 0x278D70) + asm("rsr"), 0xB6)
    assert rs.boot[:off] == before[:off] and rs.boot[off + 0xB6:] == before[off + 0xB6:]
    ls = listing_bytes(rs.boot[off:off + 0xB6], 0xFE48ED)
    assert [l.text.split()[0] for l in ls[:2]] == ["jsr", "rsr"] and all(l.text == "nop" for l in ls[2:]) and len(ls) == 2 + 0xB6 - 7
    with pytest.raises(PatchError):
        patch_span(rs, 0xFE48ED, bytes(0xB7), 0xB6)
    with pytest.raises(PatchError):
        patch_span(rs, 0x300000, b"\xcd", 1)                               # not a code region


def test_register_indirect_indexed_form():
    [line] = listing_bytes(asm("mov.w [reg](reg),abs", "r0", "r1", 0x501968), 0x278D70)
    assert line.text.split() == ["mov.w", "[R0](R1),", "501968"]


@pytest.mark.parametrize("form,args,text", [
    ("mov.h [reg],reg", ("r1", "r0"), "mov.h [R1], R0"),
    ("mov.h reg,[reg]", ("r0", "r2"), "mov.h R0, [R2]"),
    ("mov.w reg,reg", ("r10", "r11"), "mov.w R10, R11"),
    ("sub.w imm,reg", (1, "r3"), "sub.w #1, R3"),
    ("mov.w abs(reg),reg", (0xFC374D, "r9", "r1"), "mov.w FC374D(R9), R1"),
])
def test_select_routine_forms(form, args, text):
    [line] = listing_bytes(asm(form, *args), 0x278D70)
    assert line.text.split() == text.split()
