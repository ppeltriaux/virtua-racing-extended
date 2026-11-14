"""Phase 26 (plan D6): the collision quads' direction of travel in a reverse race.

Word 15 of every collision quad is the direction of forward travel (1/65536 turn); the game asks the TGP for it with command
0x1800 (handler 0x431) at fourteen boot-ROM sites, ATTR_SITES, each `mov.w #18000000, [R24]; mov.w <quad>, [R24]; in.w [R23], R0`
(docs/spike/2026-11-phase26-reverse-recon.md §1, §6). The result seeds the heading at the start (0xfe8d0b, 0xff2205), turns the
car after a spin or a put-back and steers the assist (the ten stores of `+0xeb`, `mov.h R0, EB[R25]`, each follow one of the ten
`30[R25]` sites), and the wrong-way warning compares it with the yaw (0xff4c9e). A reverse variant races the SAME collision the
other way round, so each site loads its quad into R0 and calls `dirattr`, which sends the command and adds half a turn (0x8000)
when the direction flag `course.DIRECTION_RAM` is set; with the flag 0 it returns what `in.w` returned.

`dirattr` returns with the condition flags clobbered and, after the `add.w`, possibly another upper half of R0 than `in.w` left.
Read by disassembly of the original (11 Nov): after every site the game reads R0 only as a halfword (`mov.h`, `sub.h`, `shl.h`,
`cmp.h`, or replaces it whole with `in.w` at 0xfebda0) and sets the flags itself (`cmp.h`, `sub.h`) before testing them, and
the routines it calls next write R0 before reading it; the R1 and R12 operands (0xfec003, 0xfec152, 0xffcffc) are only read.
The seven command-0x1500 sites (the six edge values, `tgp.edge_values`) are untouched in stage 1: no signed permutation of the
values gives a reverse-authored quad's, and Task 10 did not run (docs/spike/2026-11-phase26-stage1-findings.md §4).

Stage 2 (plan D6, Pascal): the Big Forest template's crew start. Mode 0x11 sets bit 0x1e of the race-start task `[0x50134c]`
at START_BIT_SITE (`set1 #1E, 0[R0]`, after the checks for data index 2 and `[0x40d826]` < 2, and after the loader, 0xfe4177,
has written back the flag); with it the player starts at the template's fixed pit-start pose, yaw 0 (the normal way), and the
race waits for the crew. The site calls `startbit`, which sets the bit only when the flag is 0, so reverse Alpine takes the
standing grid start of the six other courses: the variant's car table on its reversed lines, the READY lights, mode 0x12 on
the timer (stage 2 recon §3; the Lua trial with the bit cleared: line point 0 at the line's yaw, mode 0x14 at load + 264).
Normal Alpine, Big Forest and the attract demo take the original path (the flag is 0 there). R0 is kept; the flags after
the site are not read (0xfe41df pushes R0, then replaces it).

Stage 2 (plan D7's first way, chosen by Pascal after the drive): the Acropolis template's three start figures (Metropolis,
Diablo Canyon) turned half a turn in reverse. The race-start task places pool objects 0-2 of `[0x501350]` (animated grid girls
on the pit crew's character system) at the player's position plus world-axis offsets, the same in both directions, so in a
reverse race they would stand behind and beside the car (stage 2 recon §3). The placement ends `clr1 #1E, 0[R19]; pop R19;
br FC0EEC` (FIGURES_SITE is the branch, three bytes: the span takes the two instructions before it for the six-byte `jmp`; no
branch lands inside it, 0xfc0bd6 targets 0xfc0eb3). `figures` re-emits those two and, with the flag set, reflects each figure
through the player (x' = px + (px - x), z' likewise) and adds 0x8000 to its heading `+0x2c` before it jumps on to 0xfc0eec;
with the flag 0 it jumps on at once. The floats are added by the TGP (command 0, as the placement adds its offsets at
0xfc0c10); a float is negated by adding 0x80000000 (its sign bit) as an integer.

The figures' animation is world-axis as well, so the placement's half turn alone left them drifting off the normal places in
the car's frame (up to 24.6 units over the walk-off); Pascal rejected that ("they have to be around the car", Task 13). A figure
is drawn T(position) T(root) T(record offset, 0 for the three) R_b0(+0xd1) R_a8(+0xd7) R_a0(+0xdd) R_a8(+0x2c) and its limbs
(0xff5df4, 0xff6bf3): the root offset (+0x17b x, +0x187 y, +0x193 z, keyed every fourth frame from the animation's table, stepped
in between, 0xff67e6 / 0xff68da / 0xff6a5d) and the body's three root rotations (the first joints of +0xcd) act outside the
heading, in world axes; an ended animation adds the root offset to the position (0xff6a14); the walk-off (state 0x27, which only
the figures reach) sets the walk heading `+0x36` = 0x4000 (0xff6712), along which the figure walks in world axes (0xff6b70).
A half turn about the vertical axis negates the root offset's x and z, negates the rotations about the two horizontal axes
(+0xd1, TGP 0xb0; +0xdd, 0xa0) and keeps the vertical one (+0xd7, 0xa8, the heading's axis), and adds 0x8000 to the walk
heading. So each of those uses (FIGURE_SITES: the draw's two root pushes, the end-of-animation add's two, the two rotation
pushes, the walk heading's store) calls a routine that re-emits the original instruction unless `figmirror` holds (the flag
set and the object's character record +0x1ab one of MIRRORED_RECORDS: the three figures' and, since stage 4 Task 5, the pit
crew's fourteen, whose character code is the figures') and then pushes the value negated (stores 0xc000). The stored animation is untouched; only its uses are mirrored. The figures' cell
(+0x34, a world-aligned 128-unit grid, 0xff7b6d) and the visibility cull on it (0xff5cef) are not mirrored. The original
Acropolis keeps its figures: the loader writes the flag back to 0 on a course without a variant before the race-start task runs.

Stage 4 (Task 5, decision P2, the lead's reading of Pascal's 'Ok'): the pit crew turned half a turn about the box in a reverse race. The pit sequence's work
states 1, 8, 11 and 14 (the state table 0xff2161, run by the player's pit handler 0xff2345 only) spawn the crew at CREW_SITES,
each `bsr <spawn>; inc.h 191[R25]` followed by the state's `rsr`: the spawn (0xff27d8, 0xff2d69, 0xff33c7, 0xff3a1b) places pool
objects 0..n-1 of [0x501350] (five in state 1, six in the others) at fixed world-axis offsets from the box (`pitboxcrew`: the
served record's box), sets their record +0x1ab, heading +0x2c and handler 0xff5c3d, and returns; nothing places them later
but the animation's end-of-animation add (a FIGURE_SITES site), and the handler computes their cell from the position on its
first run, after the spawn. So the box the game places a crew for faces +z (a car facing the box heading h stands among it
turned by h, on Alpine, Pacific Coast and Diablo Canyon in the normal race too), and the reverse car, at the same box turned
half a turn (Metropolis: its own box), needs the normal crew turned half a turn about that box: x' = 2 bx - x, z' = 2 bz - z,
heading + 0x8000. Each site calls its entry `crewturn<state>`, which runs the spawn (`jsr`) and the `inc.h` and, with the
direction flag set, calls `crewturn` with R3 = n: R10-R12 = `pitbox`'s box, each object reflected through it by two TGP adds
per axis as `figures` does, its heading + 0x8000. The flags after a site are dead (the handler's 0xff2381 `test.h` sets them).
The crew runs the figures' character code (handler 0xff5c3d/0xff5cbd, the draw 0xff5df4, 0xff69fa, 0xff6bf3; the walk 0xff6b6a
moves nothing, its speed +0x44 is never set for the crew, whose states 1-0x1a never reach 0xd-0x10 or 0x27), and its records'
offsets are (0, 0, 0): `figmirror` takes in its fourteen character records (CREW_RECORDS, written only at the four spawns'
stores), so the FIGURE_SITES routines mirror its world-axis animation too. The spawns' only callers are the four sites,
Alpine's PIT START (state 6 runs 0xff27d8 from 0xff25c9, not a site) and the attract mode's pit scene, which runs work state 1's
spawn 0xff27d8 from 0xfc007e (`jsr FF27D8[PC]`), so its objects 0-4 hold CREW_RECORDS[:5] (its other objects, its own
records and two figures'). A normal race, PIT START and the attract scene keep the game's crew because the flag is 0 there
(pinned for the attract by tests/test_dirscreen_build.py::test_the_flag_is_zero_whenever_a_select_screen_starts and
tests/test_direction.py::test_the_attract_demo_never_loads_a_reverse_record).
"""
from __future__ import annotations

import struct

from vrtools.arcade.codepatch import patch_span
from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, RomSet
from vrtools.arcade.v60asm import Block, asm

COMMAND = bytes.fromhex("2d80f40000001878")             # mov.w #18000000, [R24]: TGP command 0x1800, the quad's direction
IN_R0 = bytes.fromhex("242077")                         # in.w [R23], R0
# the quad operand's store `mov.w <quad>, [R24]` -> the same operand loaded into R0 (an asm form and its operands, R0 appended)
QUAD_LOADS = {bytes.fromhex("2d80193078"): ("mov.w disp[reg],reg", 0x30, "r25"),      # 30[R25]: the car's current quad
              bytes.fromhex("2d80133078"): ("mov.w disp[reg],reg", 0x30, "r19"),      # 30[R19]
              bytes.fromhex("2d0178"): ("mov.w reg,reg", "r1"),                       # R1
              bytes.fromhex("2d0c78"): ("mov.w reg,reg", "r12")}                      # R12
_R25, _R19, _R1, _R12 = QUAD_LOADS
START_BIT_SITE = 0xFE41D6
START_BIT_PATTERN = bytes.fromhex("9780f41e0000000000")     # set1 #1E, 0[R0]: the crew start's bit of the race-start task
FIGURES_SITE = 0xFC0EB0                                  # br FC0EEC: the end of the start figures' placement
FIGURES_BEFORE = bytes.fromhex("a780f41e0000001300e773")  # clr1 #1E, 0[R19]; pop R19: the two instructions the jmp's span takes
FIGURES_PATTERN = FIGURES_BEFORE + bytes.fromhex("7a3c00")
FIGURES_SPAN = FIGURES_SITE - len(FIGURES_BEFORE)        # 0xfc0ea5 (no branch lands inside the span: 0xfc0bd6 targets 0xfc0eb3)
FIGURES_NEXT = 0xFC0EEC
FIGURES_POOL = 0x501350                                  # the pool's base pointer; the figures are its objects 0-2
FIGURES = 3
OBJECT_BYTES = 0x280
PLAYER = 0x501320                                        # the player's entity pointer
X, Z, HEADING = 0x1E, 0x26, 0x2C
FIGURE_RECORDS = (0xFD743B, 0xFD747F, 0xFD754B)          # the three figures' character records (+0x1ab), as the placement writes them
RECORD = 0x1AB
# Task 13: the uses of a figure's world-axis animation that a half turn must mirror, each site the original instruction (its bytes
# re-emitted by the routine on the flag-0 path) -> (routine, field). The root offset +0x17b (x) / +0x193 (z) where the draw pushes
# it (0xff5e13, 0xff5e1f, after the position: T(pos) T(root)) and where an ended animation adds it to the position (0xff6a18,
# 0xff6a2c); the body's first and third root rotations +0xd1 (TGP 0xb0) and +0xdd (0xa0), applied outside the heading in
# 0xff6bf3 (0xff6c25, 0xff6c41); the walk-off heading (state 0x27, 0xff6712, `mov.h #4000, 36[R25]`).
FIGURE_SITES = {0xFF5E13: (bytes.fromhex("2d80397b0178"), "figrootx"),     # mov.w 17B[R25], [R24]
                0xFF5E1F: (bytes.fromhex("2d8039930178"), "figrootz"),     # mov.w 193[R25], [R24]
                0xFF6A18: (bytes.fromhex("2d80397b0178"), "figrootx"),
                0xFF6A2C: (bytes.fromhex("2d8039930178"), "figrootz"),
                0xFF6C25: (bytes.fromhex("1c8039d10078"), "figrot0"),      # movs.hw D1[R25], [R24]
                0xFF6C41: (bytes.fromhex("1c8039dd0078"), "figrot2"),      # movs.hw DD[R25], [R24]
                0xFF6712: (bytes.fromhex("1b80f400401936"), "figwalk")}    # mov.h #4000, 36[R25]
ROOT_X, ROOT_Z, ROT_0, ROT_2, WALK = 0x17B, 0x193, 0xD1, 0xDD, 0x36
# Stage 4 Task 5: the crew spawns' sites, each `bsr <spawn>; inc.h 191[R25]` (7 bytes) -> (spawn, objects it places, entry routine),
# by the pit work state that runs it
CREW_SITES = {0xFF2518: (0xFF27D8, 5, "crewturn1"), 0xFF26F0: (0xFF2D69, 6, "crewturn8"), 0xFF2735: (0xFF33C7, 6, "crewturn11"),
              0xFF277A: (0xFF3A1B, 6, "crewturn14")}
CREW_INC = bytes.fromhex("da399101")                     # inc.h 191[R25]: the pit state's next
CREW_RECORDS = (0xFD7033, 0xFD7078, 0xFD70BD, 0xFD7102, 0xFD7147,              # the crew's character records: work state 1's five,
                0xFD7216, 0xFD725B, 0xFD6FEE, 0xFD71D1, 0xFD7AD5, 0xFD7B1A,     # 8's six,
                0xFD72A0, 0xFD72E5, 0xFD732A)                                   # 11's and 14's others (spawn order)
MIRRORED_RECORDS = FIGURE_RECORDS + CREW_RECORDS          # the objects `figmirror` holds for while the flag is set


def crew_site_pattern(site: int) -> bytes:
    return b"\x48" + struct.pack("<h", CREW_SITES[site][0] - site) + CREW_INC


ATTR_SITES = tuple([(a, _R25) for a in (0xFE8D0B, 0xFE8F97, 0xFE9147, 0xFE92FD, 0xFEA927, 0xFEAA82, 0xFEAB05, 0xFEBD50, 0xFF2205, 0xFF241C)]
                   + [(0xFF4C9E, _R19), (0xFEC003, _R1), (0xFEC152, _R1), (0xFFCFFC, _R12)])


def direction_routines(base: int, pitbox: int, crew: bool = True) -> dict[str, bytes]:
    """The routines at `base`, in order: "dirattr" (R0 = the quad in, its direction out, half a turn added when the direction
    flag is set; flags clobbered), "startbit" (R0 = the race-start task: its bit 0x1e set when the flag is 0; flags
    clobbered), "figures" (entered by `jmp` from FIGURES_SPAN: the original's two instructions, the start figures turned
    round the player when the flag is set, then `jmp FC0EEC`; R0-R3 kept, flags clobbered as 0xfc0eec's `push` ignores them),
    and Task 13's figure routines: "figmirror" (Z set when the flag is set and R25's character record +0x1ab is one of
    MIRRORED_RECORDS), "figrootx" / "figrootz" (the root offset's x / z pushed to the TGP, negated for a mirrored figure),
    "figrot0" / "figrot2" (the body's rotations +0xd1 / +0xdd pushed, negated likewise) and "figwalk" (the walk-off heading
    0x4000 stored, 0xc000 for a mirrored figure), each entered by `jsr` from its FIGURE_SITES site and re-emitting that site's
    original instruction otherwise; stage 4 Task 5 (`pitbox`: the directory's routine of that name): "crewturn" (R3 = a count:
    pool objects 0..R3-1 reflected through `pitbox`'s box, their headings + 0x8000; the registers it uses kept, R3 the caller's)
    and its four entries "crewturn1" ... "crewturn14", each entered by `jsr` from its CREW_SITES site: the site's spawn and `inc.h
    191[R25]`, then with the flag set `crewturn` for the spawn's objects; flags clobbered. `figmirror` holds for MIRRORED_RECORDS;
    with `crew` False (the tests' set without Task 5's crew change, `patch_direction_sites`) for FIGURE_RECORDS only, nop-padded
    to the same length, so every routine keeps its address."""
    b = Block(base)
    b.emit("mov.w imm,[reg]", 0x18000000, "r24")
    b.emit("mov.w reg,[reg]", "r0", "r24")
    b.raw(IN_R0)
    b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)
    b.branch("be", "done")
    b.emit("add.w imm,reg", 0x8000, "r0")
    b.label("done")
    b.emit("rsr")
    out = {"dirattr": b.bytes()}
    b = Block(base + len(out["dirattr"]))
    b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)
    b.branch("bne", "done")
    b.raw(START_BIT_PATTERN)                                # the original's own instruction
    b.label("done")
    b.emit("rsr")
    out["startbit"] = b.bytes()
    b = Block(base + len(out["dirattr"]) + len(out["startbit"]))
    b.raw(FIGURES_BEFORE)                                   # the original's own instructions
    b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)
    b.branch("be", "done")
    for r in ("r0", "r1", "r2", "r3"):
        b.emit("push reg", r)
    b.emit("mov.w abs,reg", PLAYER, "r1")
    b.emit("mov.w abs,reg", FIGURES_POOL, "r2")
    b.emit("mov.w imm,reg", FIGURES, "r3")
    b.label("figure")
    for off in (X, Z):                                      # x' = px + (px + -x): two TGP adds
        b.emit("mov.w disp[reg],reg", off, "r2", "r0")
        b.emit("add.w imm,reg", 0x80000000, "r0")
        for _ in range(2):
            b.emit("mov.w imm,[reg]", 0, "r24")
            b.emit("mov.w disp[reg],[reg]", off, "r1", "r24")
            b.emit("mov.w reg,[reg]", "r0", "r24")
            b.raw(IN_R0)
        b.emit("mov.w reg,disp[reg]", "r0", off, "r2")
    b.emit("movz.hw disp[reg],reg", HEADING, "r2", "r0")
    b.emit("add.w imm,reg", 0x8000, "r0")
    b.emit("mov.h reg,disp[reg]", "r0", HEADING, "r2")
    b.emit("add.w imm,reg", OBJECT_BYTES, "r2")
    b.emit("sub.w imm,reg", 1, "r3")
    b.branch("bne", "figure")
    for r in ("r3", "r2", "r1", "r0"):
        b.emit("pop reg", r)
    b.label("done")
    b.emit("jmp abs", FIGURES_NEXT)
    out["figures"] = b.bytes()
    at = base + sum(len(c) for c in out.values())

    def figmirror(records) -> bytes:
        b = Block(at)                                       # Task 13: Z set when the flag is set and R25 is one of the figures
        b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)           # (stage 4 Task 5: or of the crew)
        b.branch("be", "plain")
        for k, rec in enumerate(records):
            b.emit("cmp.w imm,disp[reg]", rec, RECORD, "r25")
            if k < len(records) - 1:
                b.branch("be", "done")
        b.label("done")
        b.emit("rsr")
        b.label("plain")
        b.emit("cmp.b imm,abs", 1, DIRECTION_RAM)           # the flag is 0 here: Z clear
        b.emit("rsr")
        return b.bytes()
    out["figmirror"] = figmirror(MIRRORED_RECORDS)
    if not crew:                                            # the figures' only, padded: the layout is the product's
        out["figmirror"] = figmirror(FIGURE_RECORDS).ljust(len(out["figmirror"]), bytes(asm("nop")))
    mirror = at

    def negated(name: str, original: bytes, load: list, negate: list) -> None:
        """The original instruction pushing a field to the TGP, or (a mirrored figure) the field negated pushed instead."""
        start = base + sum(len(c) for c in out.values())
        b = Block(start)
        b.emit("jsr abs", mirror)
        b.branch("be", "neg")
        b.raw(original)                                     # the original's own instruction
        b.emit("rsr")
        b.label("neg")
        b.emit("push reg", "r0")
        for ins in load + negate:
            b.emit(*ins)
        b.emit("mov.w reg,[reg]", "r0", "r24")
        b.emit("pop reg", "r0")
        b.emit("rsr")
        out[name] = b.bytes()
    float_neg = [("add.w imm,reg", 0x80000000, "r0")]      # a float's sign bit
    half_neg = [("shl.w imm,reg", 16, "r0"), ("sha.w imm,reg", -16, "r0"), ("mul.w imm,reg", -1, "r0")]   # sign-extended, negated
    sites = {}
    for pattern, name in FIGURE_SITES.values():            # the sites sharing a routine share its re-emitted instruction
        assert sites.setdefault(name, pattern) == pattern, (name, sites[name].hex(), pattern.hex())
    negated("figrootx", sites["figrootx"], [("mov.w disp[reg],reg", ROOT_X, "r25", "r0")], float_neg)
    negated("figrootz", sites["figrootz"], [("mov.w disp[reg],reg", ROOT_Z, "r25", "r0")], float_neg)
    negated("figrot0", sites["figrot0"], [("movz.hw disp[reg],reg", ROT_0, "r25", "r0")], half_neg)
    negated("figrot2", sites["figrot2"], [("movz.hw disp[reg],reg", ROT_2, "r25", "r0")], half_neg)
    b = Block(base + sum(len(c) for c in out.values()))
    b.raw(sites["figwalk"])                                 # the original's own instruction: the walk-off heading 0x4000
    b.emit("jsr abs", mirror)
    b.branch("bne", "done")
    b.emit("mov.h imm,disp[reg]", 0xC000, WALK, "r25")      # a mirrored figure walks off the other way
    b.label("done")
    b.emit("rsr")
    out["figwalk"] = b.bytes()
    turn = base + sum(len(c) for c in out.values())
    b = Block(turn)                                         # stage 4 Task 5: R3 crew objects reflected through the served box
    for r in ("r0", "r2", "r10", "r11", "r12"):
        b.emit("push reg", r)
    b.emit("jsr abs", pitbox)                               # R10, R11, R12 = the box (`pitboxcrew`'s, the spawn's); R0, R1, R8 kept
    b.emit("mov.w abs,reg", FIGURES_POOL, "r2")
    b.label("object")
    for off, box in ((X, "r10"), (Z, "r12")):               # x' = bx + (bx + -x): two TGP adds
        b.emit("mov.w disp[reg],reg", off, "r2", "r0")
        b.emit("add.w imm,reg", 0x80000000, "r0")
        for _ in range(2):
            b.emit("mov.w imm,[reg]", 0, "r24")
            b.emit("mov.w reg,[reg]", box, "r24")
            b.emit("mov.w reg,[reg]", "r0", "r24")
            b.raw(IN_R0)
        b.emit("mov.w reg,disp[reg]", "r0", off, "r2")
    b.emit("movz.hw disp[reg],reg", HEADING, "r2", "r0")
    b.emit("add.w imm,reg", 0x8000, "r0")
    b.emit("mov.h reg,disp[reg]", "r0", HEADING, "r2")
    b.emit("add.w imm,reg", OBJECT_BYTES, "r2")
    b.emit("sub.w imm,reg", 1, "r3")
    b.branch("bne", "object")
    for r in ("r12", "r11", "r10", "r2", "r0"):
        b.emit("pop reg", r)
    b.emit("rsr")
    out["crewturn"] = b.bytes()
    for spawn, objects, name in CREW_SITES.values():        # each site's entry: its spawn and `inc.h`, then the turn with the flag
        b = Block(base + sum(len(c) for c in out.values()))
        b.emit("jsr abs", spawn)
        b.raw(CREW_INC)                                     # the original's own instruction
        b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)
        b.branch("be", "done")
        b.emit("push reg", "r3")
        b.emit("mov.w imm,reg", objects, "r3")
        b.emit("jsr abs", turn)
        b.emit("pop reg", "r3")
        b.label("done")
        b.emit("rsr")
        out[name] = b.bytes()
    return out


def direction_size() -> int:
    return sum(len(c) for c in direction_routines(0, 0).values())


def patch_direction_sites(rs: RomSet, addrs: dict[str, int], crew: bool = True) -> None:
    """The fourteen sites, in place: `mov.w <quad>, R0; jsr dirattr`, nop-padded to the original's length; and START_BIT_SITE:
    `jsr startbit`, nop-padded to its nine bytes; FIGURES_SPAN: `jmp figures`, nop-padded up to 0xfc0eb3; and the seven
    FIGURE_SITES (Task 13): `jsr <its figure routine>`, nop-padded to the original instruction's length; and (stage 4 Task 5)
    the four CREW_SITES: `jsr crewturn<state>` and a nop, unless `crew` is False (a switch for the tests only: the set without
    Task 5's crew change, Review Focus 4 and the game's own reverse crew, whose image is built with `direction_routines(...,
    crew=False)`). Every site is checked before any is written; PatchError naming the first site whose bytes are not its
    pattern."""
    spans = []
    for site, operand in ATTR_SITES:
        pattern = COMMAND + operand + IN_R0
        have = rs.boot[site - V60_BOOT:site - V60_BOOT + len(pattern)]
        if have != pattern:
            raise PatchError(f"collision direction site at {site:#x} is not the expected sequence: {have.hex()} (expected {pattern.hex()})")
        form, *args = QUAD_LOADS[operand]
        b = Block(site); b.emit(form, *args, "r0"); b.emit("jsr abs", addrs["dirattr"])
        spans.append((site, b.bytes(), len(pattern)))
    have = rs.boot[START_BIT_SITE - V60_BOOT:START_BIT_SITE - V60_BOOT + len(START_BIT_PATTERN)]
    if have != START_BIT_PATTERN:
        raise PatchError(f"start bit site at {START_BIT_SITE:#x} is not the expected sequence: {have.hex()} (expected {START_BIT_PATTERN.hex()})")
    b = Block(START_BIT_SITE); b.emit("jsr abs", addrs["startbit"])
    spans.append((START_BIT_SITE, b.bytes(), len(START_BIT_PATTERN)))
    have = rs.boot[FIGURES_SPAN - V60_BOOT:FIGURES_SPAN - V60_BOOT + len(FIGURES_PATTERN)]
    if have != FIGURES_PATTERN:
        raise PatchError(f"start figures site at {FIGURES_SITE:#x} is not the expected sequence from {FIGURES_SPAN:#x}: {have.hex()} (expected {FIGURES_PATTERN.hex()})")
    b = Block(FIGURES_SPAN); b.emit("jmp abs", addrs["figures"])
    spans.append((FIGURES_SPAN, b.bytes(), len(FIGURES_PATTERN)))
    for site, (pattern, name) in FIGURE_SITES.items():     # Task 13: the figures' world-axis animation
        have = rs.boot[site - V60_BOOT:site - V60_BOOT + len(pattern)]
        if have != pattern:
            raise PatchError(f"start figures' animation site at {site:#x} is not the expected sequence: {have.hex()} (expected {pattern.hex()})")
        b = Block(site); b.emit("jsr abs", addrs[name])
        spans.append((site, b.bytes(), len(pattern)))
    for site, (spawn, _, name) in CREW_SITES.items():      # stage 4 Task 5: the crew spawns
        pattern = crew_site_pattern(site)
        have = rs.boot[site - V60_BOOT:site - V60_BOOT + len(pattern)]
        if have != pattern:
            raise PatchError(f"pit crew spawn site at {site:#x} is not the expected sequence: {have.hex()} (expected {pattern.hex()})")
        b = Block(site); b.emit("jsr abs", addrs[name])
        if crew:
            spans.append((site, b.bytes(), len(pattern)))
    for site, blob, n in spans:
        patch_span(rs, site, blob, n)
