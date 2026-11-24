"""Every block of ROM and RAM the weather feature writes, in one table (`blocks`), and the check that none of them overlaps another,
main's reserved blocks of the program ROM (`tencourse.reserved_blocks`) or the converted courses' spawn-list slots, and that the
erased ones are still erased before the install (`check`). Later stages add their blocks to TABLE and their contents to CONTENTS.

Spaces: "program" (erased program ROM, 0x200000..0x2fffff), "bank0" (erased data bank 0 at its window 0x100000..0x1fffff, mapped
while the select screens run: graphics only, read while drawing), "program site" / "boot site" (the game's or main's code changed
in place, the same length), "ram" (work RAM the feature owns or shares).

Stage 1's placement is the prototype's (spike 64 at de04235: its best-fit search over the erased runs of main's set, read from its
report on main's build of this branch's base; out/p71weather), except "screen pieces 3": the prototype put those four pieces in
the tails of the spawn-list slots of Alpine (entry 3) and Pacific Coast (entry 7), room `tencourse.spawn_list_address` keeps for
up to MAX_ENTITIES objects a course (a course given more props would have failed the build there); they lie below the direction
screen's block now, in the colour-table run's erased tail (the findings list the move). A blob's place is CONTENTS' order in its
block, so the bytes do not depend on a search.

Stage 2 (the storm's carrier and the rain; weather/carrier.py) adds the spaces "boot" (the boot ROM's erased run 0xfff120..),
"bank3" (data bank 3's erased run from 0x1df4bc, by window address) and "polygon" (the polygon ROM's erased run from 0xfda424, by
byte address), and its blocks: the stub and its copy lists, the scenery call, the image, the static data and every course's data in
bank 3 (where spike 70 stored its image), the rain's polygon objects (spike 70's place) and colour words (spike 70's place), and the
storm's RAM (carrier.STORM_RAM, laid out there). The carrier places its pieces inside its blocks itself (carrier.install).

Stage 3 (the cover; weather/cover.py) adds one block: its 40 single-drop objects in the polygon ROM right after the rain's objects
(where spike 70 put them); its code, cells, table and per-course tables go in the storm's own blocks.

Stage 4 (the lightning; weather/lightning.py) adds three blocks: its bolt objects at the END of the polygon ROM's erased run (so the
run's start stays for stage 3's single drops), its colour words after the rain's in the program ROM (spike 70's place), and its
data (the white-out table, then per course three flash skies and the grids) in data bank 3's large erased run 0x173f30..0x1c0000,
copied to the storm's RAM at the load (the module's `course_copies`).

Stage 5 (the wet handling; weather/handling.py) adds its eight hook sites in the game's physics code ("boot site", owner "handling")
and the block of their stubs ("boot", at the top of the boot ROM's erased run that the storm stub starts).

Stage 6 (the storm's sound; weather/sound.py) adds the sound board's members: the spaces "sound" (the 68000 sound program's erased
run from 0xabfc, by 68000 address), "sound site" (its code and sound-number table changed in place), "pcm1" / "pcm2" (each MultiPCM
sample ROM's erased run 0x600..0x1ffff, by byte address) and "pcm1 site" / "pcm2 site" (sample-table entries, free in the original),
and its blocks. sound.board places its pieces inside them and checks them itself; `check` checks them when the set carries the
members (a set read from a vr.zip always does)."""
from __future__ import annotations

from dataclasses import dataclass

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet

SPACES = ("program", "bank0", "program site", "boot site", "ram", "boot", "bank3", "polygon",
          "sound", "sound site", "pcm1", "pcm1 site", "pcm2", "pcm2 site")
BOUNDS = {"program": (0x200000, 0x300000), "program site": (0x200000, 0x300000), "bank0": (0x100000, 0x200000),
          "boot site": (0xFC0000, 0x1000000), "ram": (0x500000, 0x600000), "boot": (0xFC0000, 0x1000000),
          "bank3": (0x100000, 0x200000), "polygon": (0, 0x1000000),
          "sound": (0, 0x20000), "sound site": (0, 0x20000), "pcm1": (0, 0x200000), "pcm1 site": (0, 0x600),
          "pcm2": (0, 0x200000), "pcm2 site": (0, 0x600)}
ROM_OF = {"program": "program", "program site": "program", "bank0": "bank0", "boot site": "boot", "ram": "ram", "boot": "boot",
          "bank3": "bank3", "polygon": "polygon", "sound": "sound", "sound site": "sound", "pcm1": "pcm1", "pcm1 site": "pcm1",
          "pcm2": "pcm2", "pcm2 site": "pcm2"}
ERASED = ("program", "bank0", "boot", "bank3", "polygon", "sound", "pcm1", "pcm2")    # erased before the install
SOUND_ROMS = {"sound": "sound_program", "pcm1": "sound_pcm1", "pcm2": "sound_pcm2"}      # RomSet's field of each sound ROM
ALIGN = 4


@dataclass(frozen=True)
class Block:
    name: str
    space: str
    start: int
    size: int
    owner: str                          # the module that writes it


# The erased blocks (start, size: what stage 1 uses, rounded up, the code with a little room for the tune values' encodings).
TABLE = (
    Block("screen code", "program", 0x2DF9C0, 0x5C0, "screen"),            # in the erased run 0x2df9a9..0x2e0000
    Block("screen pieces 1", "program", 0x28F320, 0x290, "screen"),        # below the originals' picture block (0x28f5d0)
    Block("screen pieces 2", "program", 0x28FD80, 0x1F0, "screen"),        # above the start gantry's block (to 0x28fd70)
    Block("screen pieces 3", "program", 0x2BE160, 0x400, "screen"),        # below the direction screen's block (0x2be8b0)
    Block("screen graphics 1", "bank0", 0x1DF240, 0x9B0, "screen"),        # in bank 0's erased run 0x1df228..0x1e0000
    Block("screen graphics 2", "bank0", 0x1FFB10, 0x4C0, "screen"),        # in bank 0's erased run 0x1ffb00..0x200000
    Block("weather byte", "ram", 0x502296, 1, "screen"),                   # the direction word's third byte (weather.WEATHER_BYTE)
    # stage 2: the carrier (weather/carrier.py) and the rain (weather/rain.py)
    Block("storm stub", "boot", 0xFFF120, 0x5C0, "carrier"),              # the stub, its copy lists and bank table (the join: grown
                                                                          # from 0x500, the five modules' lists needed 1 276 of 1 280)
    Block("storm image", "bank3", 0x1DF4C0, 0x5000, "carrier"),           # code and small tables (spike 70's image at 0x1df4d0)
    Block("storm data", "bank3", 0x1E44C0, 0x6000, "carrier"),            # the static tables (the overcast and the boot's colour tables)
    Block("storm course data", "bank3", 0x1EA4C0, 0x3300, "carrier"),     # per course: its grey sky; stage 3: its cover table
    Block("rain objects", "polygon", 0xFDA424, 0xFBC0, "rain"),           # 40 drop objects, 12 splash objects
    Block("rain colours", "program", 0x28FF80, 0x60, "rain"),             # 34 drop and 12 splash colour words (spike 70's place)
    # stage 3: the cover (weather/cover.py)
    Block("cover objects", "polygon", 0xFE9FE4, 0x2F80, "cover"),         # 40 single-drop objects (spike 70's place, after the rain's)
    Block("storm RAM cells", "ram", 0x520000, 0x2000, "carrier"),         # carrier.CARRIER_CELLS, MODULE_CELLS
    Block("storm RAM image", "ram", 0x522000, 0x8000, "carrier"),         # carrier.IMAGE
    Block("storm RAM data", "ram", 0x52A000, 0x15000, "carrier"),         # carrier.DATA
    # stage 4: the lightning (weather/lightning.py)
    Block("lightning objects", "polygon", 0xFEF200, 0x10DE0, "lightning"),  # 12 bolts packed, at the end of the run from 0xfda424
    Block("lightning colours", "program", 0x28FFE0, 0x10, "lightning"),   # 8 colour words, after the rain's (spike 70's place)
    Block("lightning data", "bank3", 0x174000, 0x32000, "lightning"),     # the white-out table; per course 3 flash skies, the grids
    # stage 5: the wet handling (weather/handling.py): its eight sites' stubs, at the top of the boot ROM's erased run 0xfff120..0xfffff0
    # (the run's start is the storm stub's; the room between is left for the other stages)
    Block("handling stubs", "boot", 0xFFFEA0, 0x150, "handling"),
    # stage 6: the storm's sound (weather/sound.py) on the sound board's three members
    Block("sound code", "sound", 0xAC00, 0x500, "sound"),                  # routines, handlers, the rain loop, B074-B078's tracks
    Block("sound main loop", "sound site", 0x26E, 8, "sound"),             # `bsr 1c42; bsr c9e` -> `jsr duck; nop`
    Block("sound reset", "sound site", 0x548, 8, "sound"),                 # the reset 8100's `bsr 19d4; bra 1aec` -> `jmp reset; nop`
    Block("sound init clear", "sound site", 0x982, 10, "sound"),           # the boot's RAM clear's `lea; move.w` -> `jmp clear; nop x2`
    Block("sound tunnel word", "sound site", 0x550, 8, "sound"),           # C2xx's `andi.b #1, d0; beq` -> `jmp tunnel` (+ dead word)
    Block("sound numbers", "sound site", 0x922, 40, "sound"),              # the sound-number table's entries 0x74..0x78
    Block("sound level write", "sound site", 0x17F2, 8, "sound"),          # `btst #5, d7; bne` -> `jmp level` (+ dead word)
    Block("chip 1 samples", "pcm1", 0x600, 0xF000, "sound"),               # the rumble (61 368 bytes)
    Block("chip 1 sample table", "pcm1 site", 12 * 113, 24, "sound"),      # entries 113 (the rumble) and 114 (the distant one)
    Block("chip 2 crack entry", "pcm2 site", 12 * 110, 12, "sound"),       # entry 110 (the crack)
    Block("chip 2 rain entry", "pcm2 site", 12 * 115, 12, "sound"),        # entry 115 (the rain loop)
    Block("chip 2 samples", "pcm2", 0x600, 0xE300, "sound"),               # the crack (10 500 bytes) and the rain loop (47 445)
)
# What each erased block holds, in order (4-aligned one after the other): screen.build_data's blob names; "code" the routines.
CONTENTS = {
    "screen code": ("code",),
    "screen pieces 1": ("piece1", "dpiece0", "dpiece_conv"),
    "screen pieces 2": ("piece0",),
    "screen pieces 3": ("piece2", "dpiece2", "piece_conv", "dpiece1"),
    "screen graphics 1": ("obadge0", "cbadge", "obadge1", "obadge2", "omap2"),
    "screen graphics 2": ("caption_chars", "caption_map", "omap0", "omap1"),
}


def _sites() -> list[Block]:
    """The in-place changes (this table owns their addresses and sizes; screen.sites checks what they hold): found in the routines
    that hold them as main's layout assembles them (no ROM needed), and the two boot sites of main's modules."""
    from vrtools.arcade import tencourse
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.dirscreen import COURSE_LOCK, HANDLER, dirscreen_routines
    from vrtools.arcade.origpic import origpic_layout, origpic_routines
    from vrtools.arcade.select import select_routines
    from vrtools.arcade.v60asm import asm
    from vrtools.arcade.hudname import HUD_PATTERN, HUD_SITE
    from vrtools.arcade.origrev import RANK_PATTERN, RANK_SITE
    lay = directory_layout()
    base = tencourse.origpic_address()
    ol = origpic_layout(base, lay)

    def find(name, at, code, old):
        if code.count(old) != 1:
            raise PatchError(f"the weather layout's {name}: {old.hex()} not found once")
        return Block(name, "program site", at + code.index(old), len(old), "screen")
    olock = origpic_routines(base, lay)["olock"]
    return [find("dirsel's lock", lay["dirsel"], dirscreen_routines(lay["dirclear"], lay)["dirsel"],
                 asm("mov.w imm,disp[reg]", COURSE_LOCK, HANDLER, "r25")),
            find("start's jmp dirdone", lay["start"], select_routines(lay)["start"], asm("jmp abs", lay["dirdone"])),
            Block("bankdemo's clear", "program site", lay["bankdemo"], len(asm("mov.b imm,abs", 0, DIRECTION_RAM)), "screen"),
            find("olock's original handler", ol["olock"], olock, asm("mov.w imm,disp[reg]", ol["osel"], HANDLER, "r25")),
            find("olock's converted handler", ol["olock"], olock, asm("mov.w imm,disp[reg]", lay["dirsel"], HANDLER, "r25")),
            Block("the race end's record test", "boot site", RANK_SITE, len(RANK_PATTERN), "screen"),
            Block("the HUD's call", "boot site", HUD_SITE, len(HUD_PATTERN), "screen"),
            Block("the scenery call", "boot site", 0xFEE144, 6, "carrier")] + _handling_sites()


def _handling_sites() -> list[Block]:
    """Stage 5's eight sites in the game's physics code (weather/handling.py's SITES: the addresses and the original instructions'
    lengths)."""
    from vrtools.arcade.weather.handling import SITES
    return [Block(f"handling site {s.name}", "boot site", s.addr, len(s.original), "handling") for s in SITES]


def blocks() -> list[Block]:
    """Every block the feature writes: TABLE's, then the sites."""
    return list(TABLE) + _sites()


def block(name: str) -> Block:
    return next(b for b in TABLE if b.name == name)


def _reserved() -> list[tuple[str, int, int]]:
    """Main's reserved [start, end) of the program ROM: tencourse.reserved_blocks, and the spawn-list slots of the seven converted
    courses (each SPAWN_LIST_BYTES(MAX_ENTITIES), a course's objects growing into its slot's tail)."""
    from vrtools.arcade import tencourse
    from vrtools.arcade.spawn import SPAWN_LIST_BYTES
    out = [(n, a, e) for n, (a, e) in tencourse.reserved_blocks().items()]
    first = tencourse.spawn_list_address(0)
    out.append(("spawn-list slots", first, tencourse.spawn_list_address(tencourse.NEW_COURSES - 1)
                + SPAWN_LIST_BYTES(tencourse.MAX_ENTITIES)))
    return out


def check_table(bl: list[Block]) -> None:
    """PatchError naming the blocks: one outside its space, two of one memory overlapping, an erased-program block over main's
    reserved blocks."""
    for b in bl:
        lo, hi = BOUNDS[b.space]
        if b.size <= 0 or not (lo <= b.start and b.start + b.size <= hi):
            raise PatchError(f"the weather block {b.name!r} ({b.start:#x}, {b.size} bytes) is not inside the {b.space}")
    for rom in set(ROM_OF.values()):
        mine = sorted((b for b in bl if ROM_OF[b.space] == rom), key=lambda b: b.start)
        for a, b in zip(mine, mine[1:]):
            if b.start < a.start + a.size:
                raise PatchError(f"the weather blocks {a.name!r} and {b.name!r} overlap")
    reserved = _reserved()
    for b in bl:
        if b.space != "program":
            continue
        for name, lo, hi in reserved:
            if b.start < hi and lo < b.start + b.size:
                raise PatchError(f"the weather block {b.name!r} ({b.start:#x}, {b.size} bytes) overlaps main's {name} ({lo:#x}..{hi:#x})")


def annex_span(rs: RomSet) -> tuple[int, int] | None:
    """[start, end) of the reverse variants' annex as `rs` holds it (tencourse.reverse_annex: the first load record to the end of
    the last race blob), from the directory's reverse table; None when no entry of `rs` has a variant (the table erased or 0)."""
    import struct
    from vrtools.arcade.directory import ENTRIES, decode_directory, directory_layout
    from vrtools.arcade.race import RACE_BLOB_BYTES
    at = directory_layout()["reverse"] - 0x200000
    if all(w in (0, 0xFFFFFFFF) for w in struct.unpack_from(f"<{ENTRIES}I", rs.program, at)):
        return None
    rv = [e.reverse for e in decode_directory(rs) if e.reverse is not None]
    return min(r.at for r in rv), max(r.entry.race for r in rv) + RACE_BLOB_BYTES


def check(rs: RomSet) -> None:
    """check_table on `blocks()`; no erased-program block inside the reverse variants' annex as `rs` holds it (`annex_span`: room
    main's writers fill first-fit, its extent known only from the set); every erased-space block still erased in `rs` (call it
    before the install)."""
    bl = blocks()
    check_table(bl)
    span = annex_span(rs)
    for b in bl:
        if span and b.space == "program" and b.start < span[1] and span[0] < b.start + b.size:
            raise PatchError(f"the weather block {b.name!r} ({b.start:#x}, {b.size} bytes) overlaps the reverse variants' annex "
                             f"({span[0]:#x}..{span[1]:#x})")
        if b.space not in ERASED or (ROM_OF[b.space] in SOUND_ROMS and getattr(rs, SOUND_ROMS[ROM_OF[b.space]]) is None):
            continue                                    # a set made without the sound members: sound.board refuses it itself
        if not erased(rs, b):
            raise PatchError(f"the weather block {b.name!r} ({b.start:#x}, {b.size} bytes) is not erased")


def rom_bytes(rs: RomSet, b: Block) -> bytes:
    """The bytes of ROM block `b` in `rs` (its space's region); PatchError when the block reaches past the region's end."""
    rom = ROM_OF[b.space]
    if rom in SOUND_ROMS:
        region, off = getattr(rs, SOUND_ROMS[rom]), b.start
        if region is None:
            raise PatchError(f"the weather block {b.name!r}: the set carries no {SOUND_ROMS[rom]}")
    else:
        region, off = {"program": (rs.program, b.start - 0x200000), "program site": (rs.program, b.start - 0x200000),
                       "bank0": (rs.data, b.start - 0x100000), "bank3": (rs.data, 3 * 0x100000 + b.start - 0x100000),
                       "boot": (rs.boot, b.start - 0xFC0000), "boot site": (rs.boot, b.start - 0xFC0000),
                       "polygon": (rs.polygons, b.start)}[b.space]
    if off < 0 or off + b.size > len(region):
        raise PatchError(f"the weather block {b.name!r} ({b.start:#x}, {b.size} bytes) reaches past the end of its ROM region")
    return region[off:off + b.size]


def erased(rs: RomSet, b: Block) -> bool:
    return all(x == 0xFF for x in rom_bytes(rs, b))


def room(rs: RomSet, report: dict) -> list[tuple[str, str, int, int, int]]:
    """(block, space, start, size, used) for every block of `blocks()` in the weather set `rs` built with the carrier's `report`
    (`carrier.build`): the storm's blocks as the carrier reports them (the stub with its lists, the image, the static tables, the
    course data, the modules' ROM blocks; in RAM the cells to the last module's, the image, the data to their end); a site its size;
    stage 1's ROM blocks from their start to their last byte that is not 0xff; the weather byte 1. The findings' table of the room
    left (stage 2, fix round 1) is this, rendered by a script."""
    from vrtools.arcade.weather import carrier
    lay = report["layout"]
    known = {"storm RAM cells": lay.carrier["cells_end"] - carrier.CARRIER_CELLS, "storm RAM image": report["image"][1],
             "storm RAM data": report["data_end"] - carrier.DATA[0], "storm stub": report["stub"][1],
             "storm image": report["image"][1], "storm data": report["static_data_end"] - block("storm data").start,
             "storm course data": report["course_data_end"] - block("storm course data").start, **report["rom"]}
    out = []
    for b in blocks():
        if b.name in known:
            used = known[b.name]
        elif b.space == "ram":
            used = b.size
        elif b.space.endswith(" site"):
            used = b.size
        else:
            data = rom_bytes(rs, b)
            used = max((k + 1 for k in range(len(data)) if data[k] != 0xFF), default=0)
        out.append((b.name, b.space, b.start, b.size, used))
    return out


def place(sizes: dict[str, int]) -> dict[str, int]:
    """Each blob's address (CONTENTS' order in its block, 4-aligned); PatchError when a block overflows or a blob has no block."""
    at: dict[str, int] = {}
    for name, held in CONTENTS.items():
        b = block(name)
        a = b.start
        for n in held:
            if n == "code":
                continue
            a = (a + ALIGN - 1) // ALIGN * ALIGN
            at[n] = a
            a += sizes[n]
        if a > b.start + b.size:
            raise PatchError(f"the weather block {name!r} holds {a - b.start} bytes, {b.size} at most")
    missing = set(sizes) - set(at)
    if missing:
        raise PatchError(f"no weather block holds {sorted(missing)}")
    return at


def space_of(addr: int) -> str:
    return "bank0" if addr < 0x200000 else "program"
