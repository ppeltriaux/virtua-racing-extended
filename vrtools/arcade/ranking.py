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


def ranking_ids(d) -> list[int]:
    """Per menu entry: the ranking id — an original's data index (its table), a converted course's menu entry index."""
    return [e.template if e.race == 0 else i for i, e in enumerate(d)]


def ranking_layout(base: int) -> dict[str, int]:
    """Addresses inside the ranking image at `base`: the five ten-word arrays, the pairs, the magic, the routines, end."""
    lay = {"bases": base}
    lay["slots"] = lay["bases"] + 4 * COURSES
    lay["counts"] = lay["slots"] + 4 * COURSES
    lay["records"] = lay["counts"] + 4 * COURSES
    lay["records_oper"] = lay["records"] + 4 * COURSES
    lay["pairs"] = lay["records_oper"] + 4 * COURSES
    lay["magic"] = lay["pairs"] + 8 * COURSES
    lay["setter"] = lay["magic"] + 20
    code = _routines({**lay, "slot_init": 0, "id_store": 0, "prologue": 0}, [NEW_TABLES[0]] * COURSES, [NEW_SLOTS] * COURSES)
    lay["slot_init"] = lay["setter"] + len(code["setter"])                                   # (absolute code: sized with
    lay["id_store"] = lay["slot_init"] + len(code["slot_init"])                              # placeholder addresses)
    lay["prologue"] = lay["id_store"] + len(code["id_store"])
    lay["end"] = lay["prologue"] + len(code["prologue"])
    return lay


def ranking_size() -> int:
    return ranking_layout(0)["end"]


def _routines(lay: dict[str, int], bases: list[int], slots: list[int]) -> dict[str, bytes]:
    """The setter (R0 clobbered as before, R1 too), the slot initialiser and the ranking-id store, absolute code."""
    b = Block(lay["setter"])
    b.emit("movz.bw abs,reg", RANKING_INDEX, "r0")
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
    return {"setter": setter, "slot_init": slot_init, "id_store": id_store, "prologue": b.bytes()}


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
    code = _routines(lay, arr["bases"], arr["slots"])
    for name in ("setter", "slot_init", "id_store", "prologue"):
        assert base + len(img) == lay[name], name
        img += code[name]
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
