"""Phase 22r: a ranking (best-time) table per course.

The game keeps three ranking tables in battery RAM (`0x400000..0x40ffff`), one per original course, 24 entries of
24 bytes: `rank:u32, time:u32 (1/32 s), 0:u32, -1:u32, time:u32, name:3 chars + NUL`, at `0x40e000 / 0x40e240 /
0x40e480` (Bay Bridge, Acropolis, Big Forest: the course's DATA index, the value the select record puts in
`0x501934`). A slot word per table at `0x40e6c0 / 0x40e6c4 / 0x40e6cc` holds the table base (the insert writes the
new entry's address into it). The setter `0xfc4208` (called at the race's end and for the attract-mode ranking page
with R0 = [0x501934]) masks R0 to 2 bits and indexes two 3-entry boot-ROM tables for `0x5018f0` (the table) and
`0x501918` (the slot). The S-RAM initialiser `0xfc3b49` (run when the magic "S-RAM CHECK OK !!" at `0x40e6d0` is
missing) walks three parallel arrays — the checkpoint record (`race.CHECKPOINT_TABLE`), the normal and the operator
variant's record set (`race.TIME_TABLES`), and (defaults `0xfc4dc0`, table) pairs — summing 5 laps × sectors of the
level-0 record's words, rounding up to the minute for the first default time (4'00 on Bay Bridge and Big Forest, 5'00
on Acropolis), and stepping 5 s an entry down the default names (YU., RNS, TKG...).

Until Phase 22r the converted courses shared the originals' tables through `0x501934` (their template's data index).
Now a converted course's menu entry index (3..9) is its ranking id: the select record's byte +0x15 (the id, stored
into RANKING_INDEX beside the data index by `id_store`), seven tables and ten slots in the persistent battery RAM's
untouched stretches,
ten-entry arrays in the directory's program ROM image, the setter replaced (`setter`), the initialiser's loop count
and arrays re-pointed and its three slot stores routed through `slot_init` (ten stores), and a new S-RAM magic so a
battery RAM from before this phase is initialised once (the originals' tables reset to their defaults with it).
"""
from __future__ import annotations

import struct

from vrtools.arcade.codepatch import patch_span
from vrtools.arcade.patch import PatchError
from vrtools.arcade.race import CHECKPOINT_TABLE, TIME_TABLES, race_blob_layout
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.arcade.v60asm import Block, asm

COURSES = 10
TABLE_BYTES = 0x240            # 24 entries of 24 bytes
ORIG_TABLES = (0x40E000, 0x40E240, 0x40E480)     # by data index: Bay Bridge, Acropolis, Big Forest
ORIG_SLOTS = (0x40E6C0, 0x40E6C4, 0x40E6CC)
NEW_TABLES = (0x40EA00, 0x40EC40, 0x40F100, 0x40F340, 0x40F580, 0x40F7C0, 0x40FA00)   # the seven converted courses' tables, in
                               # the persistent part of the battery RAM (0x40e000..0x40ffff: the boot clears everything below)
                               # where nothing reads or writes through boot, attract, coin-up and a race (MAME's memory taps):
                               # 0x40ea00..0x40f000 and 0x40f100..0x40fe00, 0xff-filled since the factory (the bookkeeping at
                               # 0x40e800/0x40e900, a record at 0x40f000, the stack at 0x40ff00). Work RAM below 0x40e000 that
                               # was never non-zero is read as zeros by the race (a first try there hung the race start).
NEW_SLOTS = 0x40FC40           # ten slot words (the originals' three stay where they are; these hold the converted courses')
RANKING_INDEX = 0x40FC68       # the course's ranking id (a byte), stored beside the data index [0x501934] at the course select;
                               # zeroed by the initialiser (left 0xff on a fresh battery RAM, the attract page's setter fetched a
                               # garbage table and the race start hung on it)
DEFAULT_NAMES = 0xFC4DC0       # the initialiser's default entries: rank, step, 0, 0, name (8 bytes each)
TABLE_RAM = 0x5018F0           # the game's RAM copies the setter fills: the table base ...
SLOT_RAM = 0x501918            # ... and the slot's address
DATA_INDEX = 0x501934
CHECKPOINTS_OFFSET = race_blob_layout(0)["checkpoints"]

SETTER = 0xFC4208; SETTER_LEN = 30                 # and.w #3, R0; mov.w FC4CD5[PC](R0), 5018F0[PC]; mov.w FC4CE1[PC](R0), 501918[PC]; rsr
SETTER_BYTES = bytes.fromhex("a420e3 2dc0c0f2ca0a0000f2e5d653ff 2dc0c0f2c90a0000f200d753ff ca".replace(" ", ""))
INIT_COUNT = 0xFC3B78                              # mov.w #3, R9: the initialiser's table count
INIT_COUNT_BYTES = bytes.fromhex("2d29e3")
INIT_ARRAYS = {"records": 0xFC3B4F, "records_oper": 0xFC3B5E}      # movea.b X[PC], R22 (7 bytes, 32-bit displacements)
INIT_ARRAY_TARGETS = {"records": TIME_TABLES[0], "records_oper": TIME_TABLES[1]}
INIT_PROLOGUE = 0xFC3B6C; INIT_PROLOGUE_LEN = 12                  # movea.b FCF16D[PC], R21 (7); movea.b FC3C1B[PC], R23 (5: a 16-bit
INIT_PROLOGUE_BYTES = bytes.fromhex("4035f201b60000 4037f1a800".replace(" ", ""))   # displacement, too short to re-point) -> `prologue`
INIT_SLOTS = 0xFC3BF6; INIT_SLOTS_LEN = 36         # three mov.w #table, slot[PC] (12 bytes each); the rsr after them stays
SRAM_MAGIC_SITES = (0xFE69F7, 0xFE6A18)            # movea.b FE6A35[PC], R1: the magic compared / copied at 0x40e6d0
SRAM_MAGIC_TARGET = 0xFE6A35
SRAM_MAGIC = b"S-RAM CHECK OK !!\x00"
NEW_MAGIC = b"S-RAM CHECK OK 10\x00"
RANKING_SITE = 0xFC270F; RANKING_SITE_LEN = 9      # mov.b 14[R13], 501934[PC]: the select record's data index -> 0x501934
RANKING_SITE_BYTES = bytes.fromhex("09800d14f225f253ff")
SELECT_ID_OFFSET = 0x15                            # the ranking id inside the select record (the data index word's second byte)

# Phase 23b: the attract page shows each original's own table again, then the converted courses it hosts; every ranking
# title names its course (the converted ones by name, the originals with the game's own BEGINNER / MEDIUM / EXPERT).
SHOWN_ID = 0x40FC69            # the ranking id whose table the setters last chose (the title reads it)
ATTRACT_COUNTERS = 0x40FC6A    # per data index (3 bytes): the next member of its attract group (0xff on a fresh battery RAM: clamped)
ATTRACT_SITE = 0xFC3C33; ATTRACT_SITE_LEN = 10     # movz.bw 501934, R0; bsr FC4208: the attract page's table, by the demo's data index
ATTRACT_SITE_BYTES = bytes.fromhex("0d20f33419500048ce05")
TITLE_SITE = 0xFC3CFF; TITLE_SITE_LEN = 19         # movz.bw 501934[PC], R0; add.w R0, R0 (x2); jsr [FC3DB6[R0]]: the title by data index
TITLE_SITE_BYTES = bytes.fromhex("0d20f235dc53ff844060844060e8c0b63dfc00")
TITLE_TABLE = 0xFC3DB6         # the game's three title routines, by data index (MEDIUM, EXPERT, BEGINNER)
STRING_PRINT = 0xFFE8FB        # (string, tile address, attribute) on the stack: 2 x 3 tiles a letter from the glyph table 0x2f2456
COURSE_STRING = 0xFC3FE9       # "COURSE"
RANKING_STRING = 0xFC3FF0      # "RANKING"
TITLE_ROW = 0x700200           # the title's tile row (layer 2, 0x80 bytes a row, 62 columns on screen)
TITLE_COLS = 62
NAME_ATTR, WORD_ATTR = 0x8300, 0x8200            # the course word red (as BEGINNER / MEDIUM / EXPERT), COURSE / RANKING white
NAME_BYTES = 16                # a converted course's name string slot (15 letters and the NUL)
GROUP_BYTES = 16               # an attract group: its size, then up to ten ranking ids (the attract routine shifts by 4)
TITLE_LETTERS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")


def ranking_ids(d) -> list[int]:
    """Per menu entry: the ranking id — an original's data index (its table), a converted course's menu entry index."""
    return [e.template if e.race == 0 else i for i, e in enumerate(d)]


def attract_groups(d) -> list[list[int]]:
    """Per data index (0 Bay Bridge, 1 Acropolis, 2 Big Forest): the ranking ids its attract page shows in turn, the
    original first, then the converted courses in its slot (entries with their own race blob), in menu order."""
    ids = ranking_ids(d)
    return [[k] + [ids[i] for i, e in enumerate(d) if i >= 3 and e.race and e.template == k] for k in range(3)]


def title_columns(name: str) -> tuple[int, int, int]:
    """The columns of the name, COURSE and RANKING on the title row: 2 columns a letter, 3 between the words, the line
    centred on column 31 as the game's MEDIUM / EXPERT lines are (9, 24, 39). PatchError when a letter is not in the
    game's title font or the line does not fit."""
    if not name or set(name) - TITLE_LETTERS or len(name) >= NAME_BYTES:
        raise PatchError(f"{name!r}: a course title takes up to {NAME_BYTES - 1} capitals, digits and spaces")
    width = 2 * len(name) + 3 + 12 + 3 + 14
    start = round(31 - width / 2)
    course = start + 2 * len(name) + 3
    if start < 0 or course + 15 + 14 > TITLE_COLS:
        raise PatchError(f"{name!r} COURSE RANKING does not fit the title row")
    return start, course, course + 15


# the call of STRING_PRINT once its three arguments are pushed (attribute, tile address, string: the string at 0[SP]), and the
# caller's pop of them; it saves what it uses (R1, R2, R10, R21-R23)
STRING_CALL = (b"\x49\x80\xf3" + struct.pack("<I", STRING_PRINT) + b"\x7f"      # call STRING_PRINT, [SP]
               + bytes.fromhex("843fec"))                                       # add.w #C, SP


def print_call(attr: int, tile: int, string: int) -> bytes:
    """The game's own call sequence for STRING_PRINT (as at 0xfc3ea0), with absolute operands."""
    return (bytes.fromhex("1da0f4") + struct.pack("<H", attr) + b"\xbf"            # movz.hw #attr, [-SP]
            + b"\x40\xa0\xf3" + struct.pack("<I", tile) + b"\xbf"                   # movea.b tile, [-SP]
            + b"\x40\xa0\xf3" + struct.pack("<I", string) + b"\xbf"                 # movea.b string, [-SP]
            + STRING_CALL)


def title_routine(name: str, name_string: int) -> bytes:
    """A converted course's title: its name in red, then COURSE and RANKING, on the title row; ends with rsr."""
    n, c, r = title_columns(name)
    return (print_call(NAME_ATTR, TITLE_ROW + 2 * n, name_string) + print_call(WORD_ATTR, TITLE_ROW + 2 * c, COURSE_STRING)
            + print_call(WORD_ATTR, TITLE_ROW + 2 * r, RANKING_STRING) + b"\xca")


TITLE_BYTES = len(title_routine("A", 0))


def ranking_layout(base: int) -> dict[str, int]:
    """Addresses inside the ranking image at `base`: the five ten-word arrays, the pairs, the magic, the routines, end."""
    lay = {"bases": base}
    lay["slots"] = lay["bases"] + 4 * COURSES
    lay["counts"] = lay["slots"] + 4 * COURSES
    lay["records"] = lay["counts"] + 4 * COURSES
    lay["records_oper"] = lay["records"] + 4 * COURSES
    lay["pairs"] = lay["records_oper"] + 4 * COURSES
    lay["magic"] = lay["pairs"] + 8 * COURSES
    lay["groups"] = lay["magic"] + 20                                                         # 3 x (count, ids...) in GROUP_BYTES
    lay["titles"] = lay["groups"] + 3 * GROUP_BYTES                                                        # ten title routine addresses
    lay["names"] = lay["titles"] + 4 * COURSES                                                # seven NAME_BYTES strings
    lay["setter"] = lay["names"] + NAME_BYTES * (COURSES - 3)
    lay["title_bytes"] = TITLE_BYTES
    zero = {"slot_init": 0, "id_store": 0, "prologue": 0, "attract": 0, "title": 0, "common": 0}
    code = _routines({**lay, **zero}, [NEW_TABLES[0]] * COURSES, [NEW_SLOTS] * COURSES)
    lay["common"] = lay["setter"] + len(asm("movz.bw abs,reg", RANKING_INDEX, "r0"))         # the setter after its id load
    lay["slot_init"] = lay["setter"] + len(code["setter"])                                   # (absolute code: sized with
    lay["id_store"] = lay["slot_init"] + len(code["slot_init"])                              # placeholder addresses)
    lay["prologue"] = lay["id_store"] + len(code["id_store"])
    lay["attract"] = lay["prologue"] + len(code["prologue"])
    lay["title"] = lay["attract"] + len(code["attract"])
    lay["title3"] = lay["title"] + len(code["title"])                                       # the converted courses' titles
    lay["end"] = lay["title3"] + TITLE_BYTES * (COURSES - 3)
    return lay


def ranking_size() -> int:
    return ranking_layout(0)["end"]


def _routines(lay: dict[str, int], bases: list[int], slots: list[int]) -> dict[str, bytes]:
    """The setter (R0 clobbered as before, R1 too), the slot initialiser and the ranking-id store, absolute code."""
    b = Block(lay["setter"])
    b.emit("movz.bw abs,reg", RANKING_INDEX, "r0")
    b.emit("mov.b reg,abs", "r0", SHOWN_ID)                                   # `common`: the table of ranking id R0
    b.emit("mov.w abs(reg),reg", lay["bases"], "r0", "r1")
    b.emit("mov.w reg,abs", "r1", TABLE_RAM)
    b.emit("mov.w abs(reg),reg", lay["slots"], "r0", "r1")
    b.emit("mov.w reg,abs", "r1", SLOT_RAM)
    b.emit("rsr")
    setter = b.bytes()
    b = Block(lay["slot_init"])
    b.emit("push reg", "r0"); b.emit("push reg", "r1")
    for k, table in enumerate(NEW_TABLES):                                    # the new entries' +0xc word: -1 as the originals'
        b.emit("mov.w imm,reg", table + 0xC, "r1")                            # (a fresh battery RAM is 0xff there already)
        b.emit("mov.w imm,reg", TABLE_BYTES // 24, "r0")
        b.label(f"fill{k}")
        b.emit("mov.w imm,[reg]", 0xFFFFFFFF, "r1")
        b.emit("add.w imm,reg", 24, "r1")
        b.emit("sub.w imm,reg", 1, "r0")
        b.emit("cmp.w imm,reg", 0, "r0")
        b.branch("bne", f"fill{k}")
    b.emit("pop reg", "r1"); b.emit("pop reg", "r0")
    b.emit("mov.b imm,abs", 0, RANKING_INDEX)                                  # the id: 0 until the first course select
    for base, slot in zip(bases, slots):
        b.emit("mov.w imm,abs", base, slot)
    b.emit("rsr")
    slot_init = b.bytes()
    b = Block(lay["id_store"])
    b.emit("mov.b disp[reg],abs", 0x14, "r13", DATA_INDEX)                   # as the instruction replaced
    b.emit("mov.b disp[reg],abs", SELECT_ID_OFFSET, "r13", RANKING_INDEX)
    b.emit("rsr")
    id_store = b.bytes()
    b = Block(lay["prologue"])                                                # the initialiser's R21 (counts) and R23 (pairs)
    b.emit("mov.w imm,reg", lay["counts"], "r21")
    b.emit("mov.w imm,reg", lay["pairs"], "r23")
    b.emit("rsr")
    prologue = b.bytes()
    b = Block(lay["attract"])                                                 # the attract page: the demo's group, in turn
    b.emit("push reg", "r2"); b.emit("push reg", "r3")
    b.emit("movz.bw abs,reg", DATA_INDEX, "r0")
    b.emit("cmp.w imm,reg", 3, "r0")
    b.branch("blt", "d_ok")
    b.emit("mov.w imm,reg", 0, "r0")
    b.label("d_ok")
    b.emit("movz.bw abs(reg),reg", ATTRACT_COUNTERS, "r0", "r2")             # the group's next member
    b.emit("mov.w reg,reg", "r0", "r1")
    b.emit("shl.w imm,reg", 4, "r1")                                         # x GROUP_BYTES
    b.emit("movz.bw abs(reg),reg", lay["groups"], "r1", "r3")                # the group's size
    b.emit("cmp.w reg,reg", "r3", "r2")
    b.branch("blt", "c_ok")
    b.emit("mov.w imm,reg", 0, "r2")                                         # past the end (or 0xff): back to the original
    b.label("c_ok")
    b.emit("mov.w reg,reg", "r2", "r3")
    b.emit("add.w imm,reg", 1, "r3")
    b.emit("mov.b reg,abs(reg)", "r3", ATTRACT_COUNTERS, "r0")
    b.emit("add.w reg,reg", "r2", "r1")
    b.emit("movz.bw abs(reg),reg", lay["groups"] + 1, "r1", "r0")            # the ranking id
    b.emit("pop reg", "r3"); b.emit("pop reg", "r2")
    b.emit("jmp abs", lay["common"])
    attract = b.bytes()
    b = Block(lay["title"])                                                   # the title of the table the setters chose
    b.emit("movz.bw abs,reg", SHOWN_ID, "r0")
    b.emit("cmp.w imm,reg", COURSES, "r0")
    b.branch("blt", "id_ok")
    b.emit("movz.bw abs,reg", DATA_INDEX, "r0")                               # never set yet: by data index, as the game
    b.label("id_ok")
    b.emit("mov.w abs(reg),reg", lay["titles"], "r0", "r0")
    b.raw(bytes([0xE8, 0x60]))                                                # jsr [R0]
    b.emit("rsr")
    return {"setter": setter, "slot_init": slot_init, "id_store": id_store, "prologue": prologue, "attract": attract,
            "title": b.bytes()}


def _arrays(rs: RomSet, d) -> dict[str, list[int]]:
    """Per ranking id: the table base, the slot, the checkpoint record, the normal and the operator record sets."""
    if len(d) != COURSES:
        raise PatchError(f"the directory has {len(d)} entries, {COURSES} are needed")
    boot = lambda addr: struct.unpack_from("<I", rs.boot, addr - V60_BOOT)[0]
    out: dict[str, list[int]] = {k: [] for k in ("bases", "slots", "counts", "records", "records_oper")}
    for r in range(COURSES):
        if r < 3:
            out["bases"].append(ORIG_TABLES[r]); out["slots"].append(ORIG_SLOTS[r])
            out["counts"].append(boot(CHECKPOINT_TABLE + 4 * r))
            out["records"].append(boot(TIME_TABLES[0] + 4 * r)); out["records_oper"].append(boot(TIME_TABLES[1] + 4 * r))
        else:
            e = d[r]
            out["bases"].append(NEW_TABLES[r - 3]); out["slots"].append(NEW_SLOTS + 4 * r)
            if e.race:
                out["counts"].append(e.race + CHECKPOINTS_OFFSET)
                out["records"].append(e.race); out["records_oper"].append(e.race + 16)
            else:                                                 # an original's copy (a test directory): its template's
                t = e.template                                    # inputs; its ranking id is the template's (`ranking_ids`)
                out["counts"].append(boot(CHECKPOINT_TABLE + 4 * t))
                out["records"].append(boot(TIME_TABLES[0] + 4 * t)); out["records_oper"].append(boot(TIME_TABLES[1] + 4 * t))
    return out


def ranking_image(rs: RomSet, d, base: int) -> bytes:
    """The image at `base` in the program ROM: the arrays, the pairs, the magic and the three routines."""
    lay = ranking_layout(base)
    arr = _arrays(rs, d)
    img = b"".join(struct.pack(f"<{COURSES}I", *arr[k]) for k in ("bases", "slots", "counts", "records", "records_oper"))
    img += b"".join(struct.pack("<II", DEFAULT_NAMES, b) for b in arr["bases"])
    img += NEW_MAGIC.ljust(20, b"\0")
    for g in attract_groups(d):
        img += bytes([len(g), *g]).ljust(GROUP_BYTES, b"\0")
    names = [lay["names"] + NAME_BYTES * (r - 3) for r in range(3, COURSES)]
    titles = [struct.unpack_from("<I", rs.boot, TITLE_TABLE - V60_BOOT + 4 * r)[0] for r in range(3)]
    titles += [lay["title3"] + TITLE_BYTES * (r - 3) for r in range(3, COURSES)]
    img += struct.pack(f"<{COURSES}I", *titles)
    for r in range(3, COURSES):
        title_columns(d[r].name)
        img += d[r].name.encode().ljust(NAME_BYTES, b"\0")
    code = _routines(lay, arr["bases"], arr["slots"])
    for name in ("setter", "slot_init", "id_store", "prologue", "attract", "title"):
        assert base + len(img) == lay[name], name
        img += code[name]
    for r in range(3, COURSES):
        img += title_routine(d[r].name, names[r - 3])
    assert len(img) == lay["end"] - base
    return img


def _expect(rs: RomSet, addr: int, expected: bytes, what: str) -> None:
    got = rs.boot[addr - V60_BOOT: addr - V60_BOOT + len(expected)]
    if got != expected:
        raise PatchError(f"{what} at {addr:#x}: expected {expected.hex()}, found {got.hex()}")


def _repoint(rs: RomSet, site: int, target: int, expected_target: int, what: str) -> None:
    """A 7-byte `movea.b X[PC], Rn` (or any 32-bit PC-relative displacement at +3): the displacement re-pointed."""
    ins = bytearray(rs.boot[site - V60_BOOT: site - V60_BOOT + 7])
    if ins[2] != 0xF2 or site + struct.unpack("<i", ins[3:7])[0] != expected_target:
        raise PatchError(f"{what} at {site:#x}: expected a PC-relative load of {expected_target:#x}, found {bytes(ins).hex()}")
    ins[3:7] = struct.pack("<i", target - site)
    patch_span(rs, site, bytes(ins), 7)


def patch_ranking_sites(rs: RomSet, lay: dict[str, int]) -> None:
    """The boot-ROM sites, in place (exact lengths): the setter jumps into the image, the initialiser counts ten tables
    and reads the image's arrays and stores the slots through `slot_init`, the S-RAM check compares the new magic, the
    select record's ranking id is stored beside the data index. PatchError when a site does not hold the original."""
    _expect(rs, SETTER, SETTER_BYTES, "the ranking setter")
    b = Block(SETTER); b.emit("jmp abs", lay["setter"]); patch_span(rs, SETTER, b.bytes(), SETTER_LEN)
    _expect(rs, INIT_COUNT, INIT_COUNT_BYTES, "the initialiser's table count")
    patch_span(rs, INIT_COUNT, asm("mov.w imm,reg", COURSES, "r9"), len(INIT_COUNT_BYTES))
    for name, site in INIT_ARRAYS.items():
        _repoint(rs, site, lay[name], INIT_ARRAY_TARGETS[name], f"the initialiser's {name} array")
    _expect(rs, INIT_PROLOGUE, INIT_PROLOGUE_BYTES, "the initialiser's counts and pairs loads")
    b = Block(INIT_PROLOGUE); b.emit("jsr abs", lay["prologue"]); patch_span(rs, INIT_PROLOGUE, b.bytes(), INIT_PROLOGUE_LEN)
    for k, base in enumerate(ORIG_TABLES):
        _expect(rs, INIT_SLOTS + 12 * k, bytes.fromhex("2d80f4") + struct.pack("<I", base), "the initialiser's slot store")
    _expect(rs, INIT_SLOTS + INIT_SLOTS_LEN, b"\xca", "the initialiser's return")
    b = Block(INIT_SLOTS); b.emit("jsr abs", lay["slot_init"]); patch_span(rs, INIT_SLOTS, b.bytes(), INIT_SLOTS_LEN)
    for site in SRAM_MAGIC_SITES:
        _repoint(rs, site, lay["magic"], SRAM_MAGIC_TARGET, "the S-RAM magic load")
    _expect(rs, RANKING_SITE, RANKING_SITE_BYTES, "the data index store")
    b = Block(RANKING_SITE); b.emit("jsr abs", lay["id_store"]); patch_span(rs, RANKING_SITE, b.bytes(), RANKING_SITE_LEN)
    _expect(rs, ATTRACT_SITE, ATTRACT_SITE_BYTES, "the attract page's table setter call")
    b = Block(ATTRACT_SITE); b.emit("jsr abs", lay["attract"]); patch_span(rs, ATTRACT_SITE, b.bytes(), ATTRACT_SITE_LEN)
    _expect(rs, TITLE_SITE, TITLE_SITE_BYTES, "the ranking title's jump by data index")
    b = Block(TITLE_SITE); b.emit("jsr abs", lay["title"]); patch_span(rs, TITLE_SITE, b.bytes(), TITLE_SITE_LEN)


def install_ranking(rs: RomSet, d, base: int) -> RomSet:
    """A new RomSet with the ranking image at `base` (free program ROM) and the boot sites patched (on its own, for
    tests; the build appends the image to the directory's and calls `patch_ranking_sites`)."""
    img = ranking_image(rs, d, base)
    off = base - V60_PROGRAM
    if any(x != 0xFF for x in rs.program[off:off + len(img)]):
        raise PatchError(f"program ROM at {base:#x} is not free")
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    prog = bytearray(rs.program); prog[off:off + len(img)] = img
    object.__setattr__(out, "program", bytes(prog))
    patch_ranking_sites(out, ranking_layout(base))
    return out
