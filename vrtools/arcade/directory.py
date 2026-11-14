"""The ten-entry course directory and the V60 routines that route the game through it (Phase 7, M4).

The game keys everything on a 3-way data index (`[0x501934]`): the data bank, the course header at the bank
window's base, the TGP collision slot, the tile table, the entity spawn list, the pit-entry quad and the in-race
per-course tables. The directory (free program ROM, `course.CODE_FREE`) is indexed by the menu entry
(`[0x501940]`, 0..9) and holds, per course: a 24-byte *select* entry in the game's own layout (the select screen
code keeps using it) and a 64-byte *load* entry (LOAD_FIELDS). The menu entry applies when its template equals
`[0x501934]`; when the game set `[0x501934]` itself (operator's fixed course, linked play, attract rotation) the
original course for that data index is taken. Code sites replaced by jumps into new routines:

- `course.LOADER` (0xfe48ed): copies the header from `header_base` instead of 0x100004.., sets `[0x501934]` to
  the entry's template (so the untouched in-race tables keep working), takes the tile table and spawn list from
  the entry and sends TGP `0x0680, tgp_slot`;
- the five `course.BANK_SITES` that compute `(data index + 1) << 4 | 1` (0xfe2160 is the attract demo's course
  load, 0xfe415b the race's): map the entry's bank — the attract demo therefore runs on entry 0 (Big Forest);
- `course.PIT_CHECK` (0xfe8e8f): loads the entry's pit-entry quad;
- `course.MUSIC_SITE` (0xfc0bb8): the race-start sound command from the entry (the original's three-entry table
  was indexed by the menu index);
- `course.CAR_TABLE_SITE` (0xfe8a91, Phase 9): the car setup takes the entry's car table (inside its race blob,
  `race.py`) instead of `0xfcd395` / `0xfcd195`; the loader also serves the entry's time records (`0x501968`),
  checkpoints (`0x50195c`) and lap count (`0x5011a4`) when the entry carries a race blob;
- the two select-table references, the wheel zones and the panel blits (select.py).

Phase 26: the routines find the record through one shared lookup, `entry` (it was inlined in eleven of them). An entry may
carry a reverse variant (`ReverseRecord`: a load record and a maps record outside the tables, reached through the reverse
table); `entry` serves it on the menu path only, when the direction flag byte `course.DIRECTION_RAM` is set. The loader
writes back 1 or 0 for what it served, and the attract cycle's two bank sites call `bankdemo`, which clears the flag first.
The fourteen sites that ask the TGP for a quad's direction call `dirattr` (direction.py, after the ranking block), which adds
half a turn while the flag is set; stage 2: mode 0x11's crew-start bit (0xfe41d6) is set through `startbit`, only while it is
clear (reverse Alpine starts on the grid), and the end of the Acropolis template's start-figure placement (0xfc0ea5) jumps
to `figures`, which turns the three figures half a turn round the player while it is set; stage 4 Task 5: the pit crew's four
spawn sites call `crewturn<state>`, which turns the crew half a turn about the served box while it is set.

Stage 3 (dirscreen.py): the COURSE DIRECTION screen's routines follow the direction routines (plan D10); Task 1: mode 0x10's
state 0 clears the flag and the screen's cells (`dirclear`), a reverse race records nothing (`rankgate`), and the two linked
bank sites call `bankdemo` as the attract's two do (BANKDEMO_SITES). Task 2: the course lock's handler site (0xfc2788) calls
`dirlock`, which on an entry with a reverse variant hands the select entity to the screen's `dirsel`; `start` sends the locked
screen to `dirdone`. Task 6 (hudname.py, after the screen's routines): the race HUD's level word (0xff4799) calls `hudname`,
which prints a converted course's name from its load record (the name field NUL-padded, names up to 13 letters).

docs/formats/model1-course-tables.md §13.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, replace

from vrtools.arcade.codepatch import patch_span
from vrtools.arcade.backdrop import GFX_MAGIC
from vrtools.arcade.direction import direction_routines, direction_size, patch_direction_sites
from vrtools.arcade.dirscreen import LINKED_BANK_SITES, dirscreen_routines, dirscreen_size, patch_dirscreen_sites, placeholders
from vrtools.arcade import hudname
from vrtools.arcade.course import (BANK_SITE_LEN, BANK_SITE_PATTERN, BANK_SITES, CAR_TABLE_PATTERN, CAR_TABLE_SITE, CAR_TABLE_SITE_LEN,
                                   CODE_FREE, CROSS_TILE_CELL, DIRECTION_RAM, LOADER, LOADER_LEN, MAP_CROSS_PATTERN, MAP_CROSS_RAM, MAP_CROSS_SITE,
                                   MAP_CROSS_SITE_LEN, MAP_OBJ_PATTERN, MAP_OBJ_SITE, MAP_OBJ_SITE_LEN, MAP_OBJ_TABLE, MAP_TX_RAM, MUSIC_SITE, MUSIC_SITE_LEN, OFF_COURSE_COUNTER, OFF_COURSE_PATTERN,
                                   OFF_COURSE_RAM, OFF_COURSE_SITE, OFF_COURSE_SITE_LEN, PIT_BOX_CALL_LEN, PIT_BOX_CALLS, PIT_CHECK,
                                   PIT_CHECK_LEN, PIT_CREW_CALL_LEN, PIT_CREW_CALLS, PIT_AIM_PATTERN, PIT_AIM_SITE, PIT_AIM_SITE_LEN, PIT_PARK_PATTERN, PIT_PARK_SITE, PIT_PARK_SITE_LEN,
                                   PIT_POSE, PIT_STOPS_MODE, PIT_STOPS_PATTERN, PIT_STOPS_SITE, PIT_STOPS_SITE_LEN, SELECT_TABLE_REFS, pit_box_call_pattern,
                                   pit_crew_call_pattern,
                                   GFX_DIR_PATTERN, GFX_DIR_SITES)
from vrtools.arcade.patch import PatchError
from vrtools.arcade.race import CAR_TABLES, LAP_COUNT, race_blob_layout
from vrtools.arcade.ranking import patch_ranking_sites, ranking_ids, ranking_image, ranking_layout, ranking_size
from vrtools.arcade.romset import V60_PROGRAM, RomSet
from vrtools.arcade.select import (BANDS, CHAR_RAM, DRAW_SITE, DRAW_SITE_LEN, SLOT_A, SLOT_B, SLOT_CHAR, SLOT_PAL, SLOT_X, SLOT_Y,
                                   START_SITE, START_SITE_LEN, ZONES, ZONES_LEN, encode_bands, select_routines, slot_of)
from vrtools.arcade.v60asm import Block

ENTRIES = 10
SELECT_ROUTINES = ("band", "draw", "picture", "start")
SELECT_SIZE = 24
LOAD_SIZE = 64
# offsets inside a load record, read by the V60 routines (select.py) and written by encode_directory
LOAD_FIELDS = {"bank": 0, "tgp_slot": 1, "template": 2, "label": 3, "header_base": 4, "tile_table": 8, "spawn_table": 0xC,
               "pit_quad": 0x10, "panel_b": 0x14, "art": 0x18, "name": 0x1C, "music": 0x2A, "race": 0x2C, "laps": 0x30,
               "map_tx": 0x34, "map_cross": 0x38, "off_course": 0x3C}
LOAD_FORMAT = "<4BIIIHHIB3x14sHIB3xfII"       # fields in LOAD_FIELDS order (pad after pit_quad, after art, after laps; 64 bytes)
assert (hudname.RACE, hudname.LABEL, hudname.NAME) == (LOAD_FIELDS["race"], LOAD_FIELDS["label"], LOAD_FIELDS["name"])   # its offsets
MAX_LAPS = 20
CHECKPOINTS_OFFSET = race_blob_layout(0)["checkpoints"]      # inside a race blob
CARS_OFFSET = race_blob_layout(0)["cars"]
FALLBACK = (1, 2, 0)              # data index (BB, AC, BF) -> the original's menu entry, used when [0x501934] was set by the game
NAME_LEN = 14                     # the name field's size: up to 13 letters ("DIABLO CANYON", "PACIFIC COAST") and NULs (stage 3
                                  # Task 6: `hudname` prints the name up to its NUL)
PIT_NONE = 0xFFFE                 # the check also tries quad + 1; the original's 0xffff + 1 is quad 0
PIT_BOX_OFFSET = 16               # Phase 22i: inside an entry's map record: x, y, z (floats), heading (u16), 1 (u16) when the entry has a box
EMPTY_SPAWN_WORDS = 0x100         # the spawn reader walks 0x100 pointer slots
TEMPLATE_TABLES = (0xFCD5B9, 0xFCD5C5, 0xFCD5D1, 0xFCF16D)      # per-template pointer tables the original loader indexes
MENU_INDEX = 0x501940
DATA_INDEX = 0x501934
# Phase 26: the attract cycle's two course loads among BANK_SITES call `bankdemo` (the flag cleared): 0xfe2160, the demo's (game
# mode 2), and 0xfe2cf7, mode 6's Big Forest load between demos, which saves the data index in the menu word first and so takes
# the menu path for entry 0 when that index is 0 (measured: frame 2258 of the attract, entry 0's variant with the flag held)
ATTRACT_BANK_SITES = (0xFE2160, 0xFE2CF7)
# Stage 3 (recon §7): and the two linked course loads (dirscreen.LINKED_BANK_SITES), so a linked load right after a reverse race
# serves the normal record; mode 0x11's race load (0xfe415b) keeps `bank`
BANKDEMO_SITES = ATTRACT_BANK_SITES + LINKED_BANK_SITES
assert set(BANKDEMO_SITES) <= set(BANK_SITES) and len(set(BANKDEMO_SITES)) == 4


@dataclass(frozen=True)
class CourseEntry10:
    name: str                 # up to 14 capitals/digits/spaces
    label: int                # 0 BEGINNER, 1 MEDIUM, 2 EXPERT
    bank: int                 # data bank 1..3
    header_base: int          # window address of the course header
    tgp_slot: int             # 0..15
    template: int             # data index whose in-race tables apply (0 BB, 1 AC, 2 BF)
    tile_table: int           # program-ROM address of the 256-entry tile pointer table
    spawn_table: int          # address of the entity spawn list (0x100 pointer slots)
    pit_quad: int | None      # lap-position quad that enters the pit; None = no pit lane
    panel_map: int            # window address (bank 0) of the select panel tile map (layer A)
    panel_b: int = 0          # window address of the panel's second-layer map (layer B)
    art: int = 0              # index into the art table (palette blocks of the panel's character pages)
    music: int = 0xB001       # race-start sound command (0xb001 Big Forest, 0xb00d Bay Bridge, 0xb00e Acropolis)
    race: int = 0             # program-ROM address of the entry's race blob (race.py); 0 = the template's original tables
    laps: int = 0             # race length written at course load; 0 = leave the game's setting (5)
    map_tx: float = 149.0     # the HUD map section's screen translate x (the game's 149.0; anticlockwise courses shift it right)
    map_cross: int = 0        # byte offset added to the player's cross tile cell (2 per cell; 0 = where the game draws it)
    off_course: int = 128     # logic frames with a wheel off the tarmac before the car is put back on the road (the game's 128)
    picture: int = 0          # Phase 21: address of the entry's select picture record (picture.py); 0 = the load record's layer-B map
    map_obj: tuple[int, int, int] | None = None   # Phase 22b: the HUD map outline (polygon word address, tex, size); None = the host's
    pit_box: tuple[float, float, float, int] | None = None   # Phase 22i: where the pit sequence parks the car (x, y, z, heading 1/65536 turn); None = the host's
    reverse: ReverseRecord | None = None     # Phase 26: the variant `entry` serves on the menu path when the direction flag is set


@dataclass(frozen=True)
class ReverseRecord:
    """Phase 26 (plan D4): an entry's reverse variant, outside the directory's tables: its 64-byte load record at `at` and its
    maps record at `at + maps_offset()`, so the routines that read the maps record by R8 + maps_offset() work unchanged.
    The select record is the normal entry's (the variant takes its panel_map)."""
    at: int                   # program-ROM address of the variant's 64-byte load record; its maps record is at at + maps_offset()
    entry: CourseEntry10      # the variant's whole record


Directory = list[CourseEntry10]

ORIGINALS: Directory = [
    CourseEntry10("BIG FOREST", 0, 3, 0x100000, 2, 2, 0x2F2056, 0xFDB90B, 30, 0x1E0000, 0x1E0414, 0, 0xB001),
    CourseEntry10("BAY BRIDGE", 1, 1, 0x100000, 0, 0, 0x2F1856, 0xFDA54F, None, 0x1E015C, 0x1E06C0, 1, 0xB00D),
    CourseEntry10("ACROPOLIS", 2, 2, 0x100000, 1, 1, 0x2F1C56, 0xFDB39F, 28, 0x1E02B8, 0x1E096C, 2, 0xB00E),
]


def _check(e: CourseEntry10) -> None:
    if not (1 <= e.bank <= 3):
        raise PatchError(f"{e.name}: bank {e.bank} (the vr set has data banks 1..3)")
    if not (0 <= e.tgp_slot < 16):
        raise PatchError(f"{e.name}: TGP slot {e.tgp_slot}")
    if not (0x100000 <= e.header_base < 0x200000 - 0x28):
        raise PatchError(f"{e.name}: header base {e.header_base:#x} is not inside the bank window")
    if not (0 <= e.template <= 2):
        raise PatchError(f"{e.name}: template {e.template}")
    if not (0 <= e.label <= 2):
        raise PatchError(f"{e.name}: label {e.label}")
    if e.pit_quad is not None and not (0 <= e.pit_quad < PIT_NONE):
        raise PatchError(f"{e.name}: pit quad {e.pit_quad}")
    if not (1 <= len(e.name) < NAME_LEN) or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 " for c in e.name):
        raise PatchError(f"name {e.name!r}: up to {NAME_LEN - 1} capitals, digits and spaces (the record keeps a NUL after it)")
    for a, what in ((e.tile_table, "tile table"), (e.spawn_table, "spawn table"), (e.panel_map, "panel map"), (e.panel_b, "panel B map")):
        if not (0 <= a < 1 << 32):
            raise PatchError(f"{e.name}: {what} address {a:#x}")
    if not (0 <= e.art < ENTRIES):
        raise PatchError(f"{e.name}: art {e.art}")
    if not (0 <= e.music < 0x10000):
        raise PatchError(f"{e.name}: music command {e.music:#x}")
    if e.race and not (V60_PROGRAM <= e.race < V60_PROGRAM + 0x100000 and e.race % 4 == 0):
        raise PatchError(f"{e.name}: race blob {e.race:#x} is not a 4-aligned program ROM address")
    if not (0 <= e.laps <= MAX_LAPS):
        raise PatchError(f"{e.name}: laps {e.laps} (0 = the game's setting, else 1..{MAX_LAPS})")
    if not math.isfinite(e.map_tx):
        raise PatchError(f"{e.name}: map translate {e.map_tx}")
    if not (0 <= e.map_cross < 0x2000 and e.map_cross % 2 == 0):
        raise PatchError(f"{e.name}: cross offset {e.map_cross} (an even byte offset inside the tile page)")
    if not (1 <= e.off_course <= 0x7FFF):
        raise PatchError(f"{e.name}: off-course limit {e.off_course} (1..32767 logic frames)")
    if e.map_obj is not None and not (0 < e.map_obj[0] < 1 << 24 and 0 <= e.map_obj[1] < 1 << 24 and 0 < e.map_obj[2] < 0x10000):
        raise PatchError(f"{e.name}: map outline {e.map_obj}")
    if e.pit_box is not None and not (len(e.pit_box) == 4 and all(abs(v) < 2048 for v in e.pit_box[:3]) and 0 <= e.pit_box[3] < 0x10000):
        raise PatchError(f"{e.name}: pit box {e.pit_box}")
    if e.reverse is not None:                      # Phase 26: the variant is loaded with the normal entry's bank and TGP slot, its
        v = e.reverse.entry                        # template's in-race tables; stage 4: with its own pit quad and box, or neither
        if v.reverse is not None:
            raise PatchError(f"{e.name}: a reverse variant has no variant of its own")
        _check(v)
        if (v.bank, v.tgp_slot, v.template) != (e.bank, e.tgp_slot, e.template):
            raise PatchError(f"{e.name}: the reverse variant's bank, TGP slot and template {(v.bank, v.tgp_slot, v.template)} are not the entry's "
                             f"{(e.bank, e.tgp_slot, e.template)}")
        # a pit quad without a box would park the car at the host's box (the quad's range and the box's values: `_check(v)` above)
        if (v.pit_quad is None) != (v.pit_box is None):
            raise PatchError(f"{e.name}: the reverse variant's pit quad {v.pit_quad} and pit box {v.pit_box}: both or neither")
        if e.reverse.at % 4:
            raise PatchError(f"{e.name}: the reverse record at {e.reverse.at:#x} is not 4-aligned")


def _table_layout(code_base: int) -> dict[str, int]:
    """The tables' addresses (everything before the routines) and "entry", where the routines start."""
    lay = {"select": code_base, "load": code_base + ENTRIES * SELECT_SIZE}
    lay["bands"] = lay["load"] + ENTRIES * LOAD_SIZE
    lay["slot_a"] = lay["bands"] + 4 * len(BANDS)
    lay["slot_b"] = lay["slot_a"] + 12
    lay["fallback"] = lay["slot_b"] + 12
    lay["spawn"] = lay["fallback"] + 4
    lay["pictures"] = lay["spawn"] + 4 * EMPTY_SPAWN_WORDS      # Phase 21: ten picture record addresses
    lay["slot_char"] = lay["pictures"] + 4 * ENTRIES            # per slot: its first character's address,
    lay["slot_pal"] = lay["slot_char"] + 12                     # its palettes' address,
    lay["slot_tile"] = lay["slot_pal"] + 12                     # its tile word base
    lay["maps"] = lay["slot_tile"] + 12                         # Phase 22b: per entry a 16-byte outline object list, 64-byte stride
                                                                # (the load record's address + a constant; zero = the host's)
    lay["reverse"] = lay["maps"] + LOAD_SIZE * ENTRIES          # Phase 26: per entry its ReverseRecord.at, 0 = none
    lay["entry"] = lay["reverse"] + 4 * ENTRIES
    return lay


def maps_offset() -> int:
    """From a load record to its maps record (the directory's, and a reverse variant's at `ReverseRecord.at`)."""
    lay = _table_layout(CODE_FREE[0])
    return lay["maps"] - lay["load"]


def directory_layout(code_base: int = CODE_FREE[0]) -> dict[str, int]:
    """Addresses inside the code area: select table, load table, band table, empty spawn list, maps table, reverse table,
    routines (ROUTINES order from "entry"; "loader" is the loader's own address), select routines, ranking block, the direction
    routines ("dirattr", "startbit", "figures", ...), the direction screen's routines ("dirclear", "rankgate", ...), the HUD name's
    ("hudname", "hudattr"), end."""
    lay = _table_layout(code_base)
    code = _routines(lay)
    addr = lay["entry"]
    for name in ROUTINES:
        lay[name] = addr
        addr += len(code[name])
    for name in SELECT_ROUTINES:                                 # sized with placeholder addresses (absolute code: size is stable)
        lay[name] = addr
        addr += len(select_routines({**lay, **{k: lay.get(k, addr) for k in SELECT_ROUTINES + ("dirdone",)}})[name])
    lay["ranking"] = addr                                        # Phase 22r: the ranking tables' arrays and routines
    addr += ranking_size()
    for name, routine in direction_routines(addr, lay["pitbox"]).items():    # Phase 26 (plan D6): the collision's direction (direction.py)
        lay[name] = addr
        addr += len(routine)
    assert addr - lay["ranking"] - ranking_size() == direction_size()
    start = addr
    for name, routine in dirscreen_routines(addr, placeholders(lay, addr)).items():  # Phase 26 stage 3 (plan D10): the direction
        lay[name] = addr                                                             # screen (dirscreen.py), sized with placeholders
        addr += len(routine)
    assert addr - start == dirscreen_size()
    start = addr
    for name, routine in hudname.hudname_routines(addr, hudname.placeholders(lay, addr)).items():   # stage 3 Task 6: the course's
        lay[name] = addr                                                                            # name in the race HUD
        addr += len(routine)
    assert addr - start == hudname.hudname_size()
    lay["end"] = addr
    return lay


def encode_directory(d: Directory, base: int) -> bytes:
    if len(d) != ENTRIES:
        raise PatchError(f"the directory has {len(d)} entries, {ENTRIES} are needed")
    for e in d:
        _check(e)
    ids = ranking_ids(d)                                          # Phase 22r: the ranking id in the data index word's second byte
    sel = b"".join(struct.pack("<ffIiiI", SLOT_X[slot_of(i)], SLOT_Y, e.panel_map, -128 + 85 * slot_of(i), -128 + 85 * slot_of(i) + 84,
                               e.template | (ids[i] << 8))
                   for i, e in enumerate(d))
    load = b"".join(_load_record(e) for e in d)
    return sel + load


def _load_record(e: CourseEntry10) -> bytes:
    """The 64-byte load record (LOAD_FIELDS), a directory entry's or a reverse variant's."""
    assert struct.calcsize(LOAD_FORMAT) == LOAD_SIZE
    return struct.pack(LOAD_FORMAT, e.bank, e.tgp_slot, e.template, e.label, e.header_base, e.tile_table, e.spawn_table,
                       PIT_NONE if e.pit_quad is None else e.pit_quad, 0, e.panel_b, e.art, e.name.encode().ljust(NAME_LEN, b"\0"), e.music,
                       e.race, e.laps, e.map_tx, e.map_cross, e.off_course)


def _maps_record(e: CourseEntry10) -> bytes:
    """The 64-byte maps record: the HUD map's outline object list (Phase 22b), then the pit box (Phase 22i, PIT_BOX_OFFSET)."""
    return ((struct.pack("<4I", *e.map_obj, 0) if e.map_obj else bytes(16))
            + (struct.pack("<3fHH", *e.pit_box, 1) if e.pit_box else bytes(16)) + bytes(LOAD_SIZE - 32))


def _decode_record(prog: bytes, load: int, maps: int, panel: int) -> CourseEntry10:
    """The entry whose load record is at program-ROM offset `load` and maps record at `maps` (no reverse record)."""
    bank, slot, template, label, header, tile, spawn, pit, _, panel_b, art, name, music, race, laps, map_tx, map_cross, off_course = \
        struct.unpack_from(LOAD_FORMAT, prog, load)
    poly, tex, size, _ = struct.unpack_from("<4I", prog, maps)
    bx, by, bz, heading, has_box = struct.unpack_from("<3fHH", prog, maps + PIT_BOX_OFFSET)
    return CourseEntry10(name.rstrip(b"\0 ").decode(), label, bank, header, slot, template, tile, spawn,
                         None if pit == PIT_NONE else pit, panel, panel_b, art, music, race, laps, map_tx, map_cross, off_course,
                         map_obj=(poly, tex, size) if poly else None, pit_box=(bx, by, bz, heading) if has_box else None)


def decode_directory(rs: RomSet, base: int = CODE_FREE[0]) -> Directory:
    off = base - V60_PROGRAM
    lay = _table_layout(base)
    maps, reverse = lay["maps"] - V60_PROGRAM, lay["reverse"] - V60_PROGRAM
    out = []
    for i in range(ENTRIES):
        _, _, panel, _, _, _ = struct.unpack_from("<ffIiiI", rs.program, off + i * SELECT_SIZE)
        e = _decode_record(rs.program, off + ENTRIES * SELECT_SIZE + i * LOAD_SIZE, maps + i * LOAD_SIZE, panel)
        at = struct.unpack_from("<I", rs.program, reverse + 4 * i)[0]
        if at:                                                   # Phase 26: the variant's records, with the entry's panel map
            v = _decode_record(rs.program, at - V60_PROGRAM, at - V60_PROGRAM + maps_offset(), panel)
            e = replace(e, reverse=ReverseRecord(at, v))
        out.append(e)
    return out


ROUTINES = ("entry", "loader", "bank", "bankdemo", "pit", "music", "cars", "cross", "gfx", "mapobj", "pitbox", "pitboxcrew", "pitaim",
            "pitpark", "pitstops")


def _entry(lay: dict[str, int]) -> bytes:
    """Phase 26 (plan D4, D5): the entry lookup the eleven routines call (`jsr`), once inlined in each. R8 = address of the
    course's load record. The menu entry [0x501940] is used when its template equals the data index [0x501934]; otherwise
    the game chose the course through [0x501934] itself (operator's fixed course, linked play, attract rotation) and the
    original course for that data index is taken (FALLBACK). On the menu path only, with the direction flag set and a
    reverse record in the entry's word of the reverse table, R8 = that record. R0 = 1 when the record served is a variant's,
    else 0; R1 clobbered. With the flag 0 the condition flags at the return are the inlined lookup's (`mov` sets none): the
    fallback path's `add.w`, and on the menu path an equal compare (`cmp.b #0` of a 0 byte, as `cmp.w R0, R1` was)."""
    b = Block(lay["entry"])
    b.emit("movz.bw abs,reg", MENU_INDEX, "r8")
    b.emit("shl.w imm,reg", 6, "r8")
    b.emit("add.w imm,reg", lay["load"], "r8")
    b.emit("movz.bw disp[reg],reg", LOAD_FIELDS["template"], "r8", "r0")
    b.emit("movz.bw abs,reg", DATA_INDEX, "r1")
    b.emit("cmp.w reg,reg", "r0", "r1")
    b.branch("be", "menu")
    b.emit("cmp.w imm,reg", 3, "r1")
    b.branch("bge", "menu")                                       # a data index outside 0..2: keep the menu entry
    b.emit("movz.bw abs(reg),reg", lay["fallback"], "r1", "r8")   # fallback path: the flag is not read
    b.emit("shl.w imm,reg", 6, "r8")
    b.emit("add.w imm,reg", lay["load"], "r8")
    b.emit("mov.w imm,reg", 0, "r0")
    b.emit("rsr")
    b.label("menu")
    b.emit("mov.w imm,reg", 0, "r0")
    b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)
    b.branch("be", "done")
    b.emit("movz.bw abs,reg", MENU_INDEX, "r1")
    b.emit("mov.w abs(reg),reg", lay["reverse"], "r1", "r1")
    b.emit("cmp.w imm,reg", 0, "r1")
    b.branch("be", "done")
    b.emit("mov.w reg,reg", "r1", "r8")
    b.emit("mov.w imm,reg", 1, "r0")
    b.label("done")
    b.emit("rsr")
    return b.bytes()


def _routines(lay: dict[str, int]) -> dict[str, bytes]:
    """The routines in ROUTINES order, each laid out right after the previous one from lay["entry"]; absolute addressing
    makes them independent of their own address except for branches. Needs only the table addresses (_table_layout).
    Phase 26: the eleven callers of `entry` save R8, and R0 and R1 as the inlined lookup (which clobbered both) required:
    cars, gfx, pitbox, pitaim and pitpark save both; bank, pit, music and pitstops save R1 and return a result in R0;
    the loader clobbers both as the original did; mapobj saves R1 and leaves R0 = the served flag where the inlined lookup
    left the menu template, dead there: the map entity's init returns to the entity loop (0xfe1c15), which writes R0
    before any read on both of its paths."""
    code: dict[str, bytes] = {}

    def here() -> int:                                         # where the next routine starts
        return lay["entry"] + sum(len(c) for c in code.values())

    code["entry"] = _entry(lay)
    # --- loader: replaces 0xfe48ed..0xfe49a3 (entered by jmp, so it ends with rsr like the original)
    b = Block(here())
    for r in ("r8", "r9", "r2"):                               # R0, R1, R10 (= data index), R11 are clobbered as in the original
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("mov.b reg,abs", "r0", DIRECTION_RAM)               # Phase 26: the flag records what was served (1 = a variant)
    b.emit("movz.bw disp[reg],reg", LOAD_FIELDS["template"], "r8", "r10")   # R10 = template data index
    b.emit("mov.b reg,abs", "r10", DATA_INDEX)
    b.emit("mov.w disp[reg],reg", LOAD_FIELDS["header_base"], "r8", "r9")   # R9 = header base
    b.emit("mov.w disp[reg],reg", 4, "r9", "r11")              # header+4 -> segment array: counts, then entry 1
    b.emit("mov.w [reg],abs", "r11", 0x501954)
    b.emit("add.w imm,reg", 4, "r11")
    b.emit("mov.w [reg],abs", "r11", 0x501958)
    b.emit("add.w imm,reg", 4, "r11")
    b.emit("mov.w reg,abs", "r11", 0x501950)
    b.emit("movz.bw abs,reg", 0x501110, "r1")                  # R1 = level
    b.emit("mov.w disp[reg],reg", LOAD_FIELDS["race"], "r8", "r2")          # R2 = the entry's race blob (0: original tables)
    b.emit("cmp.w imm,reg", 0, "r2")
    b.branch("be", "chain_orig")
    b.emit("mov.w disp[reg],reg", LOAD_FIELDS["race"], "r8", "r0")          # R0 = variant table inside the blob, chosen as the original does
    b.emit("cmp.b imm,abs", 0, 0x40DC8C)
    b.branch("be", "race_pick")
    b.emit("add.w imm,reg", 16, "r0")
    b.emit("cmp.b imm,abs", 0, 0x501105)
    b.branch("be", "race_pick")
    b.emit("add.w imm,reg", 16, "r0")
    b.label("race_pick")
    b.emit("mov.w [reg](reg),abs", "r0", "r1", 0x501968)                      # the level's time record
    b.emit("add.w imm,reg", CHECKPOINTS_OFFSET, "r2")
    b.emit("mov.w reg,abs", "r2", 0x50195C)                                   # the blob's checkpoint record
    b.branch("br", "chain_done")
    b.label("chain_orig")                                     # the original's per-template pointer chain -> 0x501968
    b.emit("mov.w abs(reg),reg", TEMPLATE_TABLES[0], "r10", "r0")
    b.emit("cmp.b imm,abs", 0, 0x40DC8C)
    b.branch("be", "chain")
    b.emit("mov.w abs(reg),reg", TEMPLATE_TABLES[1], "r10", "r0")
    b.emit("cmp.b imm,abs", 0, 0x501105)
    b.branch("be", "chain")
    b.emit("mov.w abs(reg),reg", TEMPLATE_TABLES[2], "r10", "r0")
    b.label("chain")
    b.emit("mov.w [reg](reg),abs", "r0", "r1", 0x501968)
    b.emit("mov.w abs(reg),reg", TEMPLATE_TABLES[3], "r10", "r0")
    b.emit("mov.w reg,abs", "r0", 0x50195C)
    b.label("chain_done")
    b.emit("mov.w disp[reg],reg", LOAD_FIELDS["tile_table"], "r8", "r0")    # tile table
    b.emit("mov.w reg,abs", "r0", 0x501948)
    b.emit("mov.w disp[reg],reg", 0x10, "r9", "r0")            # header+0x10 -> line table pointer
    b.emit("mov.w reg,abs", "r0", 0x501960)
    b.emit("mov.w disp[reg],reg", 8, "r9", "r0")               # *(header+8) -> collision map
    b.emit("mov.w [reg],reg", "r0", "r1")
    b.emit("mov.w reg,abs", "r1", 0x50196C)
    b.emit("mov.w disp[reg],reg", 0xC, "r9", "r0")             # *(header+0xc) -> surface table
    b.emit("mov.w [reg],reg", "r0", "r1")
    b.emit("mov.w reg,abs", "r1", 0x501970)
    b.emit("mov.w disp[reg],reg", LOAD_FIELDS["spawn_table"], "r8", "r0")   # spawn list
    b.emit("mov.w reg,abs", "r0", 0x50197C)
    b.emit("movz.bw disp[reg],reg", LOAD_FIELDS["tgp_slot"], "r8", "r10")   # TGP slot
    b.emit("mov.w imm,[reg]", 0x6800000, "r24")
    b.emit("mov.w reg,[reg]", "r10", "r24")
    b.emit("cmp.b imm,abs", 0, 0x40DC8C)                       # lap count: the entry's when non-zero, in the normal game mode
    b.branch("bne", "no_laps")                                  # only (the operator flag selects 4 laps, linked play 20)
    b.emit("movz.bw disp[reg],reg", LOAD_FIELDS["laps"], "r8", "r0")
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("be", "no_laps")
    b.emit("mov.b reg,abs", "r0", LAP_COUNT)
    b.label("no_laps")
    for field, ram in (("map_tx", MAP_TX_RAM), ("map_cross", MAP_CROSS_RAM), ("off_course", OFF_COURSE_RAM)):   # Phase 14: the HUD map's
        b.emit("mov.w disp[reg],abs", LOAD_FIELDS[field], "r8", ram)                                        # translate, the cross offset,
    for r in ("r2", "r9", "r8"):                                                                             # the off-course limit
        b.emit("pop reg", r)
    b.emit("rsr")
    code["loader"] = b.bytes()
    # --- bank switch: replaces 0xfe415b..0xfe4170 (entered by jsr); writes (bank << 4) | 1 to 0xe00004
    b = Block(here())
    for r in ("r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("movz.bw disp[reg],reg", LOAD_FIELDS["bank"], "r8", "r0")
    b.emit("shl.w imm,reg", 4, "r0")
    b.emit("or.w imm,reg", 1, "r0")
    b.emit("mov.b reg,abs", "r0", 0xE00004)
    for r in ("r8", "r1"):
        b.emit("pop reg", r)
    b.emit("rsr")
    code["bank"] = b.bytes()
    # --- bankdemo (Phase 26, plan D5): the attract cycle's two bank sites (ATTRACT_BANK_SITES) clear the direction flag before the
    # bank switch's lookup, so the attract never loads a reverse record (each calls the backdrop upload and the loader right after
    # it, 0xfe2176 / 0xfe217c and 0xfe2d0d / 0xfe2d13; the loader then writes back 0). Stage 3: the two linked loads call it too
    # (BANKDEMO_SITES): it is `bank` with the clear and nothing else
    bank_at = here() - len(code["bank"])
    b = Block(here())
    b.emit("mov.b imm,abs", 0, DIRECTION_RAM)
    b.emit("jmp abs", bank_at)
    code["bankdemo"] = b.bytes()
    # --- pit check: replaces 0xfe8e8f..0xfe8e9b (entered by jsr); R0 = the entry's pit quad
    b = Block(here())
    for r in ("r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("movz.hw disp[reg],reg", LOAD_FIELDS["pit_quad"], "r8", "r0")
    for r in ("r8", "r1"):
        b.emit("pop reg", r)
    b.emit("rsr")
    code["pit"] = b.bytes()
    # --- music: replaces 0xfc0bb8..0xfc0bc6 (entered by jsr); R0 = the entry's race-start sound command
    b = Block(here())
    for r in ("r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("movz.hw disp[reg],reg", LOAD_FIELDS["music"], "r8", "r0")
    for r in ("r8", "r1"):
        b.emit("pop reg", r)
    b.emit("rsr")
    code["music"] = b.bytes()
    # --- car table: replaces 0xfe8a91..0xfe8aa6 (entered by jsr); R10 = the car table (the entry's, inside its race
    # blob, or the original's by the operator flag as the replaced code chose)
    b = Block(here())
    for r in ("r0", "r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("mov.w disp[reg],reg", LOAD_FIELDS["race"], "r8", "r10")
    b.emit("cmp.w imm,reg", 0, "r10")
    b.branch("be", "cr_orig")
    b.emit("add.w imm,reg", CARS_OFFSET, "r10")
    b.branch("br", "cr_done")
    b.label("cr_orig")
    b.emit("mov.w imm,reg", CAR_TABLES[0], "r10")
    b.emit("cmp.b imm,abs", 0, 0x40DC8C)
    b.branch("be", "cr_done")
    b.emit("mov.w imm,reg", CAR_TABLES[1], "r10")
    b.label("cr_done")
    for r in ("r8", "r1", "r0"):
        b.emit("pop reg", r)
    b.emit("rsr")
    code["cars"] = b.bytes()
    # --- cross: replaces `movea.w #700AE0, R1` at MAP_CROSS_SITE (Phase 14): the player's HUD cross is drawn at the game's cell
    # plus the per-course byte offset the loader put in MAP_CROSS_RAM (0 at boot and for the originals = the game's own cell)
    b = Block(here())
    b.emit("mov.w imm,reg", CROSS_TILE_CELL, "r1")
    b.emit("add.w abs,reg", MAP_CROSS_RAM, "r1")
    b.emit("rsr")
    code["cross"] = b.bytes()
    # --- gfx: replaces `mov.w 100000, R20` at GFX_DIR_SITES (Phase 18b): the current entry's header's directory when an encoded
    # backdrop image is there (GFX_MAGIC before it: a converted course, its bank mapped), else the bank's original header's.
    # The course-load upload runs before the loader in the same frame, so the entry is found here, as the bank switch does
    b = Block(here())
    for r in ("r0", "r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("mov.w disp[reg],reg", LOAD_FIELDS["header_base"], "r8", "r20")
    b.emit("mov.w [reg],reg", "r20", "r20")
    b.emit("cmp.w imm,reg", 0x100004, "r20")                    # a window address (another bank mapped: arbitrary data;
    b.branch("blt", "gx_old")                                   # never read I/O space through it)
    b.emit("cmp.w imm,reg", 0x200000, "r20")
    b.branch("bge", "gx_old")
    b.emit("mov.w disp[reg],reg", -4, "r20", "r0")
    b.emit("cmp.w imm,reg", GFX_MAGIC, "r0")
    b.branch("be", "gx_own")
    b.label("gx_old")
    b.emit("mov.w abs,reg", 0x100000, "r20")
    b.label("gx_own")
    for r in ("r8", "r1", "r0"):
        b.emit("pop reg", r)
    b.emit("rsr")
    code["gfx"] = b.bytes()
    # --- mapobj: replaces `mov.w FEAC1B[PC](R0), 18[R25]` at MAP_OBJ_SITE (Phase 22b): the map entity's outline object list,
    # the host's by data index (R0) as the game picked it, then the entry's own when its map record has an object
    b = Block(here())
    for r in ("r1", "r8"):
        b.emit("push reg", r)
    b.emit("mov.w abs(reg),reg", MAP_OBJ_TABLE, "r0", "r1")
    b.emit("mov.w reg,disp[reg]", "r1", 0x18, "r25")
    b.emit("jsr abs", lay["entry"])
    b.emit("add.w imm,reg", lay["maps"] - lay["load"], "r8")
    b.emit("mov.w [reg],reg", "r8", "r1")
    b.emit("cmp.w imm,reg", 0, "r1")
    b.branch("be", "mo_done")
    b.emit("mov.w reg,disp[reg]", "r8", 0x18, "r25")
    b.label("mo_done")
    for r in ("r8", "r1"):
        b.emit("pop reg", r)
    b.emit("rsr")
    code["mapobj"] = b.bytes()
    # --- pitbox (Phase 22i): R10, R11, R12 = the entry's pit box when it has one, else the game's (PIT_POSE: the host's table).
    # Replaces the pit autopilot's six `jsr FF4061[PC]` (PIT_BOX_CALLS); the PIT START grid's own calls of 0xff4061 stay
    box = lay["maps"] - lay["load"] + PIT_BOX_OFFSET
    at = here()                                                            # pitbox's address (pitboxcrew calls it)
    b = Block(at)
    for r in ("r0", "r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("add.w imm,reg", box, "r8")
    b.emit("movz.hw disp[reg],reg", 14, "r8", "r0")
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("be", "pb_host")
    for off, r in ((0, "r10"), (4, "r11"), (8, "r12")):
        b.emit("mov.w disp[reg],reg", off, "r8", r)
    for r in ("r8", "r1", "r0"):
        b.emit("pop reg", r)
    b.emit("rsr")
    b.label("pb_host")
    for r in ("r8", "r1", "r0"):
        b.emit("pop reg", r)
    b.emit("jsr abs", PIT_POSE)
    b.emit("rsr")
    code["pitbox"] = b.bytes()
    # --- pitboxcrew: replaces `bsr FF4061; mov.w #0, [R24]` at the four crew spawns (PIT_CREW_CALLS, entered by jsr)
    b = Block(here())
    b.emit("jsr abs", at)
    b.emit("mov.w imm,[reg]", 0, "r24")
    b.emit("rsr")
    code["pitboxcrew"] = b.bytes()
    # --- pitaim: replaces the autopilot's aim and bearing at PIT_AIM_SITE (entered by jsr): the game aims 10 units short of the box
    # along -z until the car is level with that point, then at the box, which lines the car up on a +z pit lane; on a course with its
    # own box the aim lies 10 units short along the box's heading h (direction (-sin h, cos h)), level = the car's run past the box
    # along h >= -10. R4 = the bearing (TGP 0x7800000); R0, R1 saved, R9 scratch as in the original. TGP: 0 add, 0x800000 subtract,
    # 0xE800000 s*sin(a), 0xF000000 s*cos(a) (a in 1/65536 turn), by the probe of 4 Nov
    TEN = 0x41200000
    def fifo(words):                                                       # each word: an immediate, a register or (disp, reg)
        for w in words:
            if isinstance(w, tuple):
                b.emit("mov.w disp[reg],[reg]", w[0], w[1], "r24")
            elif isinstance(w, str):
                b.emit("mov.w reg,[reg]", w, "r24")
            else:
                b.emit("mov.w imm,[reg]", w, "r24")
    def in_w(reg: str):
        b.raw(bytes([0x24, 0x20 | int(reg[1:]), 0x77]))                    # in.w [R23], reg
    b = Block(here())
    for r in ("r0", "r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("add.w imm,reg", box, "r8")
    b.emit("movz.hw disp[reg],reg", 14, "r8", "r0")
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("be", "pa_host")
    b.emit("movz.hw disp[reg],reg", 12, "r8", "r0")                        # R0 = h
    fifo([0x800000, (0, "r8"), (0x1E, "r25")]); in_w("r1")                 # R1 = bx - cx
    fifo([0xE800000, "r0", "r1"]); in_w("r1")                              # R1 = (bx - cx) sin h
    fifo([0x800000, (0x26, "r25"), (8, "r8")]); in_w("r9")                 # R9 = cz - bz
    fifo([0xF000000, "r0", "r9"]); in_w("r9")                              # R9 = (cz - bz) cos h
    fifo([0, "r1", "r9"]); in_w("r9")                                      # R9 = the car's run past the box along h
    b.raw(bytes.fromhex("5ca0f4") + struct.pack("<I", 0xC1200000) + bytes([0x69]))   # cmpf.s #-10.0, R9
    b.branch("blt", "pa_short")
    b.emit("mov.w reg,reg", "r10", "r1")                                   # level or past: aim at the box
    b.emit("mov.w reg,reg", "r12", "r9")
    b.branch("br", "pa_bearing")
    b.label("pa_short")
    fifo([0xE800000, "r0", TEN]); in_w("r1")                               # 10 sin h
    fifo([0, "r10", "r1"]); in_w("r1")                                     # aim x = bx + 10 sin h
    fifo([0xF000000, "r0", TEN]); in_w("r9")                               # 10 cos h
    fifo([0x800000, "r12", "r9"]); in_w("r9")                              # aim z = bz - 10 cos h
    b.label("pa_bearing")
    fifo([0x7800000, "r9", (0x1E, "r25"), (0x26, "r25"), "r1"]); in_w("r4")
    for r in ("r8", "r1", "r0"):
        b.emit("pop reg", r)
    b.emit("rsr")
    b.label("pa_host")
    for r in ("r8", "r1", "r0"):
        b.emit("pop reg", r)
    b.raw(PIT_AIM_PATTERN)                                                 # the original aim and bearing, whole (its branch is inside)
    b.emit("rsr")
    code["pitaim"] = b.bytes()
    # --- pitpark: replaces the park at PIT_PARK_SITE (entered by jsr): the car at the box, facing the entry's heading (the
    # original's +z when the entry has no box)
    b = Block(here())
    b.emit("mov.w reg,disp[reg]", "r10", 0x1E, "r25")
    b.emit("mov.w reg,disp[reg]", "r12", 0x26, "r25")
    b.emit("mov.h imm,disp[reg]", 0, 0x6A, "r25")
    for r in ("r0", "r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("add.w imm,reg", box, "r8")
    b.emit("movz.hw disp[reg],reg", 14, "r8", "r0")
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("be", "pk_done")
    b.emit("mov.h disp[reg],disp[reg]", 12, "r8", 0x6A, "r25")
    b.label("pk_done")
    for r in ("r8", "r1", "r0"):
        b.emit("pop reg", r)
    b.emit("rsr")
    code["pitpark"] = b.bytes()
    # --- pitstops: replaces the race start's choice of pit stops left at PIT_STOPS_SITE (entered by jsr; R0 -> +0x1bf after it):
    # 0 for an entry without a pit quad (the game's Bay Bridge case), else the game's 5 in linked play or 2 below mode 2
    b = Block(here())
    for r in ("r1", "r8"):
        b.emit("push reg", r)
    b.emit("jsr abs", lay["entry"])
    b.emit("movz.hw disp[reg],reg", LOAD_FIELDS["pit_quad"], "r8", "r1")
    b.emit("mov.w imm,reg", 0, "r0")
    b.emit("cmp.w imm,reg", PIT_NONE, "r1")
    b.branch("be", "ps_done")
    b.emit("cmp.b imm,abs", 0, 0x501105)
    b.branch("be", "ps_normal")
    b.emit("mov.w imm,reg", 5, "r0")
    b.branch("br", "ps_done")
    b.label("ps_normal")
    b.emit("cmp.b imm,abs", 2, PIT_STOPS_MODE)
    b.branch("bge", "ps_done")
    b.emit("mov.w imm,reg", 2, "r0")
    b.label("ps_done")
    for r in ("r8", "r1"):
        b.emit("pop reg", r)
    b.emit("rsr")
    code["pitstops"] = b.bytes()
    assert tuple(code) == ROUTINES
    return code


def install_directory(rs: RomSet, d: Directory, code_base: int = CODE_FREE[0], crew: bool = True) -> RomSet:
    """A new RomSet with the directory and routines at `code_base` and the three code sites routed through them. `crew` False
    (a switch for the tests only, stage 4 Task 5): the set without Task 5's crew change, the pit crew's four spawn sites left as
    the original's and `figmirror` holding for the start figures only (padded: every address is the product's)."""
    blob = encode_directory(d, code_base)
    lay = directory_layout(code_base)
    code = _routines(lay)
    image = bytearray(blob)
    assert code_base + len(image) == lay["bands"]
    image += encode_bands() + struct.pack("<3I", *SLOT_A) + struct.pack("<3I", *SLOT_B) + bytes(FALLBACK) + b"\x00"
    assert code_base + len(image) == lay["spawn"]
    image += bytes(4 * EMPTY_SPAWN_WORDS)
    assert code_base + len(image) == lay["pictures"]
    image += struct.pack(f"<{ENTRIES}I", *(e.picture for e in d))
    image += struct.pack("<3I", *(CHAR_RAM + 32 * c for c in SLOT_CHAR)) + struct.pack("<3I", *SLOT_PAL)
    image += struct.pack("<3I", *(0x8000 | c for c in SLOT_CHAR))
    assert code_base + len(image) == lay["maps"]
    image += b"".join(_maps_record(e) for e in d)
    assert code_base + len(image) == lay["reverse"]
    image += struct.pack(f"<{ENTRIES}I", *(e.reverse.at if e.reverse else 0 for e in d))      # Phase 26
    sel_code = select_routines(lay)
    for name in ROUTINES + SELECT_ROUTINES:
        assert code_base + len(image) == lay[name], name
        image += code.get(name) or sel_code[name]
    assert code_base + len(image) == lay["ranking"]
    image += ranking_image(rs, d, lay["ranking"])                # Phase 22r
    for name, routine in direction_routines(code_base + len(image), lay["pitbox"], crew=crew).items():     # Phase 26 (stage 4 Task 5:
                                                                                                          # the layout is the same)
        assert code_base + len(image) == lay[name], name
        image += routine
    for name, routine in dirscreen_routines(code_base + len(image), lay).items():    # Phase 26 stage 3
        assert code_base + len(image) == lay[name], name
        image += routine
    for name, routine in hudname.hudname_routines(code_base + len(image), lay).items():    # stage 3 Task 6
        assert code_base + len(image) == lay[name], name
        image += routine
    assert code_base + len(image) == lay["end"]
    if len(image) > CODE_FREE[1]:
        raise PatchError("directory and routines exceed the free program ROM")
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    off = code_base - V60_PROGRAM
    if any(x != 0xFF for x in rs.program[off:off + len(image)]):
        raise PatchError(f"program ROM at {code_base:#x} is not free")
    prog = bytearray(rs.program)
    prog[off:off + len(image)] = image
    for e in d:                                                  # Phase 26: the reverse variants' load and maps records
        if e.reverse is None:
            continue
        for at, rec in ((e.reverse.at, _load_record(e.reverse.entry)), (e.reverse.at + maps_offset(), _maps_record(e.reverse.entry))):
            if at < code_base + len(image) and code_base < at + LOAD_SIZE:
                raise PatchError(f"{e.name}: the reverse record at {at:#x} is inside the directory image ({code_base:#x}..{code_base + len(image):#x})")
            if not (V60_PROGRAM <= at and at + LOAD_SIZE <= V60_PROGRAM + len(prog)):
                raise PatchError(f"{e.name}: the reverse record at {at:#x} is not in the program ROM")
            if any(x != 0xFF for x in prog[at - V60_PROGRAM:at - V60_PROGRAM + LOAD_SIZE]):       # (also another variant's record)
                raise PatchError(f"{e.name}: program ROM at {at:#x} is not erased for the reverse record")
            prog[at - V60_PROGRAM:at - V60_PROGRAM + LOAD_SIZE] = rec
    object.__setattr__(out, "program", bytes(prog))
    b = Block(LOADER); b.emit("jmp abs", lay["loader"]); patch_span(out, LOADER, b.bytes(), LOADER_LEN)
    patch_ranking_sites(out, ranking_layout(lay["ranking"]))     # Phase 22r: a ranking table per course
    patch_direction_sites(out, lay, crew=crew)                   # Phase 26 (plan D6): the fourteen command-0x1800 sites call `dirattr`,
                                                                 # the crew-start bit's site `startbit` (stage 2 D6), the start
                                                                 # figures' `figures` (stage 2 D7), the crew spawns `crewturn<state>`
                                                                 # (stage 4 Task 5)
    patch_dirscreen_sites(out, lay)                              # stage 3: mode 0x10 state 0's `dirclear`, the ranking gate's `rankgate`
    hudname.patch_hudname_sites(out, lay)                        # stage 3 Task 6: the HUD's level word, `hudname`
    for site in BANK_SITES:
        have = rs.boot[site - 0xFC0000:site - 0xFC0000 + BANK_SITE_LEN]
        if any(p != ord("?") and p != h for p, h in zip(BANK_SITE_PATTERN, have)):
            raise PatchError(f"bank switch at {site:#x} is not the expected sequence: {have.hex()}")
        b = Block(site); b.emit("jsr abs", lay["bankdemo" if site in BANKDEMO_SITES else "bank"]); patch_span(out, site, b.bytes(), BANK_SITE_LEN)
    b = Block(PIT_CHECK); b.emit("jsr abs", lay["pit"]); patch_span(out, PIT_CHECK, b.bytes(), PIT_CHECK_LEN)
    b = Block(MUSIC_SITE); b.emit("jsr abs", lay["music"]); patch_span(out, MUSIC_SITE, b.bytes(), MUSIC_SITE_LEN)
    have = rs.boot[CAR_TABLE_SITE - 0xFC0000:CAR_TABLE_SITE - 0xFC0000 + CAR_TABLE_SITE_LEN]
    if have != CAR_TABLE_PATTERN:
        raise PatchError(f"car table site at {CAR_TABLE_SITE:#x} is not the expected sequence: {have.hex()}")
    b = Block(CAR_TABLE_SITE); b.emit("jsr abs", lay["cars"]); patch_span(out, CAR_TABLE_SITE, b.bytes(), CAR_TABLE_SITE_LEN)
    for ref in SELECT_TABLE_REFS:
        patch_span(out, ref, struct.pack("<I", lay["select"]), 4)
    for site, n, pattern, what in ((MAP_CROSS_SITE, MAP_CROSS_SITE_LEN, MAP_CROSS_PATTERN, "cross draw"),
                                   (MAP_OBJ_SITE, MAP_OBJ_SITE_LEN, MAP_OBJ_PATTERN, "map outline pick"),
                                   (PIT_PARK_SITE, PIT_PARK_SITE_LEN, PIT_PARK_PATTERN, "pit park"),
                                   (PIT_AIM_SITE, PIT_AIM_SITE_LEN, PIT_AIM_PATTERN, "pit aim"),
                                   (PIT_STOPS_SITE, PIT_STOPS_SITE_LEN, PIT_STOPS_PATTERN, "pit stops"),
                                   *((site, PIT_BOX_CALL_LEN, pit_box_call_pattern(site), "pit autopilot call") for site in PIT_BOX_CALLS),
                                   *((site, PIT_CREW_CALL_LEN, pit_crew_call_pattern(site), "pit crew call") for site in PIT_CREW_CALLS),
                                   (OFF_COURSE_SITE, OFF_COURSE_SITE_LEN, OFF_COURSE_PATTERN, "off-course compare")):
        have = rs.boot[site - 0xFC0000:site - 0xFC0000 + n]
        if have != pattern:
            raise PatchError(f"{what} site at {site:#x} is not the expected sequence: {have.hex()}")
    b = Block(MAP_CROSS_SITE); b.emit("jsr abs", lay["cross"]); b.emit("nop"); patch_span(out, MAP_CROSS_SITE, b.bytes(), MAP_CROSS_SITE_LEN)
    b = Block(MAP_OBJ_SITE); b.emit("jsr abs", lay["mapobj"]); patch_span(out, MAP_OBJ_SITE, b.bytes(), MAP_OBJ_SITE_LEN)
    for site in PIT_BOX_CALLS:                                                                                          # Phase 22i
        b = Block(site); b.emit("jsr abs", lay["pitbox"]); patch_span(out, site, b.bytes(), PIT_BOX_CALL_LEN)
    for site in PIT_CREW_CALLS:
        b = Block(site); b.emit("jsr abs", lay["pitboxcrew"]); patch_span(out, site, b.bytes(), PIT_CREW_CALL_LEN)
    b = Block(PIT_PARK_SITE); b.emit("jsr abs", lay["pitpark"]); patch_span(out, PIT_PARK_SITE, b.bytes(), PIT_PARK_SITE_LEN)
    b = Block(PIT_AIM_SITE); b.emit("jsr abs", lay["pitaim"]); patch_span(out, PIT_AIM_SITE, b.bytes(), PIT_AIM_SITE_LEN)
    b = Block(PIT_STOPS_SITE); b.emit("jsr abs", lay["pitstops"]); patch_span(out, PIT_STOPS_SITE, b.bytes(), PIT_STOPS_SITE_LEN)
    b = Block(OFF_COURSE_SITE); b.emit("cmp.w abs,abs", OFF_COURSE_RAM, OFF_COURSE_COUNTER)       # the game's `cmp.w #128, counter`
    patch_span(out, OFF_COURSE_SITE, b.bytes(), OFF_COURSE_SITE_LEN)                             # with the limit read from RAM
    for site in GFX_DIR_SITES:                                     # Phase 18b: the checked backdrop-directory reader
        have = rs.boot[site - 0xFC0000:site - 0xFC0000 + len(GFX_DIR_PATTERN)]
        if have != GFX_DIR_PATTERN:
            raise PatchError(f"backdrop directory site at {site:#x} is not the expected sequence: {have.hex()}")
        b = Block(site); b.emit("jsr abs", lay["gfx"]); b.emit("nop"); patch_span(out, site, b.bytes(), len(GFX_DIR_PATTERN))
    b = Block(ZONES); b.emit("jsr abs", lay["band"]); patch_span(out, ZONES, b.bytes(), ZONES_LEN)
    b = Block(DRAW_SITE); b.emit("jsr abs", lay["draw"]); b.emit("rsr"); patch_span(out, DRAW_SITE, b.bytes(), DRAW_SITE_LEN)
    if any(e.picture for e in d):                                  # Phase 21: START greys the slots not chosen
        b = Block(START_SITE); b.emit("jmp abs", lay["start"])
        jmp = b.bytes()
        patch_span(out, START_SITE, jmp, len(jmp))                 # the rest of the old routine stays, unreached
    return out


def spawn_empty(lay: dict[str, int]) -> int:
    return lay["spawn"]
