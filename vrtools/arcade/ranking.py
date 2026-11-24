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

Phase 27 (docs/superpowers/specs/2026-11-14-reverse-ranking-design.md, recon docs/spike/2026-11-phase27-reverse-ranking-recon.md):
a reverse race on a converted course keeps its four best times. The game's own insert, name entry and page run on 4-entry
tables (the recon's mechanism 1): seven short tables in the free battery RAM (REVERSE_TABLES, recon §5), the ranking id of
a reverse table its entry + REVERSE_ID_SHIFT (10..16). The setter's arrays run on over ids 10..16. At the race's end and the
name entry (the boot ROM's 0xfc4208, both with the direction flag still 1 in a reverse race: recon §7) the setter adds
REVERSE_ID_SHIFT to an id of 3..9 while the flag is set; the attract page's entry (`common`) takes the id as given and never
reads the flag (it is cleared before the page). Every call writes both cells: the last entry's offset (0x228 for 24 entries,
0x48 for SHORT_ENTRIES) and the page's row count (6 or SHORT_ENTRIES). The insert's two `add.w #228` (INSERT_SITES, recon §1)
read the offset cell in place (7 bytes each); the page's end test (PAGE_END_SITE) calls `pagecmp` (past 24 entries, or past
SHORT_ENTRIES: one screen) and its row count (PAGE_ROWS_SITE) calls `pagerows` (recon §3). `rankgate` (dirscreen.py) is gone:
every entry that can set the flag has a table.

The reverse block is made by `revinit` (design §4, L5 as the session lead ruled it on 15 Nov, L6): the seven tables' four entries
(rank 1..4, the build-time default times of `reverse_defaults` — the course's normal table's first four — stepping 5 s, +8 = 0,
+0xc = -1, the game's first four default names), the seven slots and the tag
REVERSE_TAG_BYTES. It runs from `slot_init` (the stock initialiser on a battery RAM without the magic, and the test mode's backup
clear at 0xfc76eb, both through 0xfc3b49) and from `revtag`, which the boot's S-RAM check calls first (TAG_SITE): a battery RAM
with the magic but not the tag (one saved by a set before this phase) gets the reverse block alone, every saved time kept; the
magic does not change. In the attract, each reverse id follows its course's id in its host's group (L3) and its page has the
title `revtitle` prints: the course's name and REVERSE in red, RANKING in white (L4, `reverse_title_columns`).

Phase 27b: the attract's first ranking page after a game shows the table just raced. The race end's setter call (RACE_END_SITE,
0xfc40e1: `movz.bw 501934[PC], R0; bsr FC4208`, 10 bytes; the setter loads the ranking id itself) becomes `bsr FC4208;
jsr raceend; nop`: after the setter (its entry: the course's id, + 7 in a reverse race; R0 kept by `common`) `raceend` writes the
id's position in its group (`attract_positions`, the image's `positions`) into the counter of the data index's group
(ATTRACT_COUNTERS + [0x501934]: the raced course's host, the group the first page after the game reads). That page's `attract`
then shows the member at that position and stores position + 1 as before. Every finished race calls the setter there (before the
qualify test: a record or not); a race that does not finish (time over) skips the insert and the setter and leaves the counter.
The name entry's call (0xfc4226) and the attract page's are not touched; nothing else of the battery RAM is written.

Phase 35 (recon and gate docs/spike/2026-11-phase35-reverse-times-recon.md; Pascal, 16 Nov: "yes to all", four per table on all
ten): a reverse race on one of the three ORIGINALS keeps its four best times too. Three more 4-entry tables (ORIG_REVERSE_TABLES,
by the original's ranking id 0..2, in two runs of the battery RAM that nothing read or wrote in the gate's 25 runs), their slots
in the three words of NEW_SLOTS that ids 0..2 never used, and a tag of their own (ORIG_TAG). Their ranking ids are the original's
id + ORIG_REVERSE_SHIFT (17..19); the seven's ids, tables, slots and tag REV4 are where v0.2.1 put them and no byte of them is
written by this phase's upgrade (a v0.2.1 set finds its block as it left it). The setter adds ORIG_REVERSE_SHIFT to an id of 0..2
while the direction flag is set; `originit` (the three tables as `revinit` makes the seven's, from `original_reverse_defaults`, the
slots, ORIG_TAG) runs from `revtag` when ORIG_TAG is missing (a battery RAM saved by v0.2.1 or before) and from `slot_init` (a
battery RAM without the magic, and the test mode's backup clear, which resets them with the others). In the attract each original's
reverse page follows its own page (`attract_groups`) under the title `revtitle` prints with the game's own level word (MEDIUM,
EXPERT, BEGINNER: ORIG_NAME_STRINGS) in the name's place. Phase 33's `rankgate3` (origrev.py) is gone.
"""
from __future__ import annotations

import dataclasses
import struct

from vrtools.arcade.codepatch import patch_span
from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.patch import PatchError
from vrtools.arcade.race import CHECKPOINT_TABLE, MAX_CHECKPOINTS, TIME_TABLES, race_blob_layout
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
RACE_END_SITE = 0xFC40E1; RACE_END_SITE_LEN = 10   # Phase 27b: movz.bw 501934[PC], R0; bsr FC4208: the race end's setter call
RACE_END_SITE_BYTES = bytes.fromhex("0d20f253d853ff482001")       # (the insert follows at 0xfc40eb; the setter loads the id itself)
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

# Phase 27: the reverse block (design §4, recon §5: the free runs 0x40ee80..0x40efff and 0x40fc6d..0x40fdff, untouched through
# boot, attract, coin-up, both races' ends and the name entry; 709 of their 787 bytes)
SHORT_ENTRIES = 4              # a reverse table's entries (the game's 24 bytes each)
REVERSE_TABLES = (0x40EE80, 0x40EEE0, 0x40EF40, 0x40EFA0, 0x40FC70, 0x40FCD0, 0x40FD30)   # entries 3..9's reverse tables
REVERSE_SLOTS = 0x40FD90       # seven slot words, entry order
REVERSE_TAG = 0x40FDAC         # the reverse block's own tag (Task 3: the S-RAM magic does not change)
LAST_OFFSET_CELL = 0x40FDB0    # the last entry's offset (word) the insert's two INSERT_SITES add to the table base
ROWS_CELL = 0x40FDB4           # the page's row count (byte): `pagerows`' count, `pagecmp`'s choice of end
REVERSE_ID_SHIFT = 7           # a reverse table's ranking id: its entry + 7 (10..16)
# Phase 35: the three originals' reverse tables, by ranking id 0..2 (Bay Bridge, Acropolis, Big Forest): 4 entries each, in the runs
# 0x40e6e2..0x40e7ff (after the S-RAM magic) and 0x40f00c..0x40f0ff (after the game's record), 0xff since the factory and neither
# read nor written through every test-menu page, the backup clear, the races, the name entry and the attract (the recon's §11)
ORIG_REVERSE_TABLES = (0x40E6E4, 0x40E744, 0x40F010)
ORIG_REVERSE_SLOTS = NEW_SLOTS                     # their slot words: NEW_SLOTS' first three (ids 0..2 keep ORIG_SLOTS; never used)
ORIG_TAG = 0x40FDB8                                # the originals' block's own tag (0xff on a battery RAM saved before Phase 35)
ORIG_TAG_BYTES = b"ORG4"
ORIG_REVERSE_SHIFT = COURSES + len(REVERSE_TABLES)  # an original's reverse table's ranking id: its id + 17 (17..19)
ORIG_NAME_STRINGS = (0xFC400B, 0xFC4012, 0xFC4019)  # the game's own "MEDIUM", "EXPERT", "BEGINNER" (NUL-ended, beside COURSE and
ORIG_NAMES = ("MEDIUM", "EXPERT", "BEGINNER")       # RANKING), by ranking id 0..2: the level words its own titles print
REVERSE_IDS = len(REVERSE_TABLES) + len(ORIG_REVERSE_TABLES)   # ids 10..19
IDS = COURSES + REVERSE_IDS                        # the setter's arrays: ranking ids 0..19
LAST_OFFSET = TABLE_BYTES - 24                     # 0x228: a 24-entry table's last entry
SHORT_LAST_OFFSET = 24 * (SHORT_ENTRIES - 1)       # 0x48
ROWS = 6                                           # the page's rows a screen (the original's `mov.w #6, R3`)
INSERT_SITES = (0xFC40F9, 0xFC4184)                # add.w #228, R1 (the qualify test); add.w #228, R0 (the bubble)
INSERT_BYTES = (bytes.fromhex("8421f428020000"), bytes.fromhex("8420f428020000"))
INSERT_REGS = ("r1", "r0")
PAGE_END_SITE = 0xFC3CA1                           # cmp.b #18, 36[R25] (6 bytes; its `bnl FC3CEC` stays): past 24 entries
PAGE_END_BYTES = bytes.fromhex("b880f4181936")
FIRST_SHOWN = 0x36                                 # the page entity's first entry shown (+6 a screen)
PAGE_ROWS_SITE = 0xFC3D8C                          # mov.w R1, 501924[PC]; mov.w #6, R3 (10 bytes): the first row, six rows
PAGE_ROWS_BYTES = bytes.fromhex("2d01f298db53ff2d23e6")
ROW_TILE = 0x501924                                # the row's tile address the page's row loop steps
# Phase 27 Task 3: the reverse block's initialiser, its boot tag and its titles
REVERSE_TAG_BYTES = b"REV4"                        # at REVERSE_TAG once the reverse block is made (0xff on a fresh battery RAM)
TAG_SITE = 0xFE69F0                                # mov.w FE6A47[PC], R0 (7 bytes): the S-RAM check's first instruction, the
TAG_SITE_BYTES = bytes.fromhex("2d20f257000000")   # magic's length (18) for its compare loop -> `jsr revtag` + nop
MAGIC_LENGTH = 0xFE6A47                            # the word that instruction loads (`revtag` loads it absolute)
MINUTE = 0x780                                     # 60 s in 1/32 s: the stock initialiser rounds the first default up to it
DEFAULT_STEP = 0xA0                                # 5 s: the stock initialiser's step from one default entry to the next
DEFAULT_NAME_STEP = 8                              # DEFAULT_NAMES' entries (the name at +4)
REVERSE_WORD = "REVERSE"
REVERSE_ATTR = NAME_ATTR                           # REVERSE in the title's red, the name's (the direction screen prints no red
                                                   # text: its red is the arrows', maps with their own palettes)
REVERSE_ARGS = 5                                   # per reverse id, `revtitle`'s words: name string, name tile, REVERSE tile,
                                                   # third string (RANKING, or "" when the line does not fit), third tile


def ranking_ids(d) -> list[int]:
    """Per menu entry: the ranking id — an original's data index (its table), a converted course's menu entry index."""
    return [e.template if e.race == 0 else i for i, e in enumerate(d)]


def reverse_ids(d) -> list[int]:
    """The ranking ids (10..16) of the converted entries that have a reverse variant: the entry + REVERSE_ID_SHIFT."""
    return [i + REVERSE_ID_SHIFT for i, e in enumerate(d) if i >= 3 and e.reverse is not None]


def original_reverse_ids(d) -> list[int]:
    """Phase 35: the ranking ids (17..19) of the originals that have a reverse variant: the original's ranking id (its data
    index) + ORIG_REVERSE_SHIFT, in id order."""
    return sorted(e.template + ORIG_REVERSE_SHIFT for e in d[:3] if e.race == 0 and e.reverse is not None)


def attract_groups(d) -> list[list[int]]:
    """Per data index (0 Bay Bridge, 1 Acropolis, 2 Big Forest): the ranking ids its attract page shows in turn, the
    original first, then the converted courses in its slot (entries with their own race blob), in menu order, each followed
    by its reverse id when it has a reverse variant (Phase 27, L3); Phase 35: the original too (its id + ORIG_REVERSE_SHIFT
    straight after it)."""
    ids = ranking_ids(d)
    hosted = [i for i, e in enumerate(d) if i >= 3 and e.race]
    own = original_reverse_ids(d)
    return [[k] + [k + ORIG_REVERSE_SHIFT] * (k + ORIG_REVERSE_SHIFT in own)
            + [x for i in hosted if d[i].template == k for x in [ids[i]] + ([i + REVERSE_ID_SHIFT] if d[i].reverse else [])]
            for k in range(3)]


def attract_positions(d) -> list[int]:
    """Per ranking id 0..19 (Phase 27b; Phase 35: the originals' reverse ids): its position in the attract group that holds it (`attract_groups`), the value `raceend`
    puts in that group's counter at a race's end so that the attract's next page of the group shows the id's table; 0 (the
    group's first member) for an id in no group (a reverse id of an entry without a variant: never chosen at a race's end)."""
    pos = [0] * IDS
    for g in attract_groups(d):
        for k, r in enumerate(g):
            pos[r] = k
    return pos


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


def reverse_title_columns(name: str) -> tuple[int, int, int | None]:
    """A reverse table's title (L4): the columns of the name, REVERSE and RANKING for "<NAME> REVERSE RANKING", centred as
    `title_columns` centres its line; when that does not fit the 62 columns (a name of 15 letters: 64), "<NAME> REVERSE"
    centred, RANKING's column None. PatchError as `title_columns` for a name the title font cannot print."""
    title_columns(name)
    words = 2 * len(name) + 3 + 2 * len(REVERSE_WORD)
    width = words + 3 + 14
    start = round(31 - width / 2)
    if start >= 0 and start + width <= TITLE_COLS:
        return start, start + 2 * len(name) + 3, start + words + 3
    start = round(31 - words / 2)
    return start, start + 2 * len(name) + 3, None


def _rom_words(rs: RomSet, addr: int, count: int) -> tuple[int, ...]:
    """`count` 32-bit words at a boot or program ROM address; PatchError when they are not inside either."""
    for region, base in ((rs.boot, V60_BOOT), (rs.program, V60_PROGRAM)):
        if base <= addr and addr + 4 * count <= base + len(region):
            return struct.unpack_from(f"<{count}I", region, addr - base)
    raise PatchError(f"{addr:#x} (+{4 * count}) is not inside the boot or program ROM")


def _first_default(rs: RomSet, records: int, counts: int) -> int:
    """The stock initialiser's first default time (0xfc3b91..0xfc3bb9): the 5 laps x sectors words from the level-0 record
    (the first word of the record set at `records`) summed, the sectors the word at `counts`, rounded up to the minute."""
    rec, = _rom_words(rs, records, 1)
    sectors, = _rom_words(rs, counts, 1)
    if not 1 <= sectors <= MAX_CHECKPOINTS:
        raise PatchError(f"the checkpoint record at {counts:#x} holds {sectors} sectors (1..{MAX_CHECKPOINTS})")
    total = sum(_rom_words(rs, rec, 5 * sectors)) & 0xFFFFFFFF
    return -(-total // MINUTE) * MINUTE


def reverse_defaults(rs: RomSet, d) -> list[list[int]]:
    """Per converted entry 3..9 (REVERSE_TABLES' order), its reverse table's four default times (1/32 s): entries 0..3 of what the
    stock initialiser gives the course's NORMAL table (the session lead's ruling of 15 Nov, replacing L5's rule on the variant's
    blob) — `_first_default` on the records and the checkpoint count the initialiser reads for the course's ranking id (`_arrays`:
    the normal race blob's, or its template's original tables for an original's copy), then 5 s an entry. Computed at build time
    from the ROM: the battery's normal table holds the player's times after an upgrade. The reverse variant's blob plays no part;
    an entry without a variant (it never sets the direction flag) still gets its table, with the same defaults."""
    arr = _arrays(rs, d)
    out = []
    for r in range(3, COURSES):
        first = _first_default(rs, arr["records"][r], arr["counts"][r])
        out.append([first + DEFAULT_STEP * k for k in range(SHORT_ENTRIES)])
    return out


def original_reverse_defaults(rs: RomSet, d) -> list[list[int]]:
    """Phase 35: per original's ranking id 0..2 (ORIG_REVERSE_TABLES' order), its reverse table's four default times: the seven's
    rule (`reverse_defaults`), the first four of what the stock initialiser gives the original's NORMAL table (Bay Bridge and Big
    Forest 4'00 .. 4'15, Acropolis 5'00 .. 5'15 on the arcade's set)."""
    arr = _arrays(rs, d)
    return [[_first_default(rs, arr["records"][r], arr["counts"][r]) + DEFAULT_STEP * k for k in range(SHORT_ENTRIES)]
            for r in range(3)]


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
    """Addresses inside the ranking image at `base`: the five arrays (bases and slots by ranking id 0..19 (Phase 35: 0..16
    before), the other three ten words), the pairs, the magic, the groups, the titles (by ranking id 0..19), the names, REVERSE,
    the reverse tables' first default times and `revtitle`'s arguments (ids 10..19), the positions (Phase 27b: a byte by ranking
    id 0..19), the routines, end."""
    lay = {"bases": base}
    lay["slots"] = lay["bases"] + 4 * IDS
    lay["counts"] = lay["slots"] + 4 * IDS
    lay["records"] = lay["counts"] + 4 * COURSES
    lay["records_oper"] = lay["records"] + 4 * COURSES
    lay["pairs"] = lay["records_oper"] + 4 * COURSES
    lay["magic"] = lay["pairs"] + 8 * COURSES
    lay["groups"] = lay["magic"] + 20                                                         # 3 x (count, ids...) in GROUP_BYTES
    lay["titles"] = lay["groups"] + 3 * GROUP_BYTES                                           # title routine addresses by id 0..19
    lay["names"] = lay["titles"] + 4 * IDS                                                    # seven NAME_BYTES strings
    lay["revword"] = lay["names"] + NAME_BYTES * (COURSES - 3)                                # Phase 27: "REVERSE" and its NUL
    lay["firsts"] = lay["revword"] + len(REVERSE_WORD) + 1                                    # ten first default times (ids 10..19)
    lay["revargs"] = lay["firsts"] + 4 * REVERSE_IDS                                          # REVERSE_ARGS arrays of ten words
    lay["positions"] = lay["revargs"] + 4 * REVERSE_ARGS * REVERSE_IDS                        # Phase 27b: `attract_positions`
    lay["setter"] = lay["positions"] + IDS
    lay["title_bytes"] = TITLE_BYTES
    zero = {"slot_init": 0, "id_store": 0, "prologue": 0, "attract": 0, "title": 0, "common": 0, "pagecmp": 0, "pagerows": 0,
            "revinit": 0, "revtag": 0, "revtitle": 0, "raceend": 0, "originit": 0}
    code = _routines({**lay, **zero}, [NEW_TABLES[0]] * COURSES, [NEW_SLOTS] * COURSES)
    lay["common"] = _setter(lay).addr("common")                                              # the setter after its id choice
    lay["slot_init"] = lay["setter"] + len(code["setter"])                                   # (absolute code: sized with
    lay["id_store"] = lay["slot_init"] + len(code["slot_init"])                              # placeholder addresses)
    lay["prologue"] = lay["id_store"] + len(code["id_store"])
    lay["attract"] = lay["prologue"] + len(code["prologue"])
    lay["title"] = lay["attract"] + len(code["attract"])
    lay["pagecmp"] = lay["title"] + len(code["title"])                                      # Phase 27: the page's two hooks
    lay["pagerows"] = lay["pagecmp"] + len(code["pagecmp"])
    lay["revinit"] = lay["pagerows"] + len(code["pagerows"])                                # Phase 27 Task 3: the reverse block's
    lay["revtag"] = lay["revinit"] + len(code["revinit"])                                   # initialiser, its boot check, its title
    lay["revtitle"] = lay["revtag"] + len(code["revtag"])
    lay["raceend"] = lay["revtitle"] + len(code["revtitle"])                                # Phase 27b: the race end's jump
    lay["originit"] = lay["raceend"] + len(code["raceend"])                                 # Phase 35: the originals' reverse tables
    lay["title3"] = lay["originit"] + len(code["originit"])                                 # the converted courses' titles
    lay["end"] = lay["title3"] + TITLE_BYTES * (COURSES - 3)
    return lay


def ranking_size() -> int:
    return ranking_layout(0)["end"]


def _setter(lay: dict[str, int]) -> Block:
    """The setter (R0 and R1 clobbered, as before). From its entry (0xfc4208's jump: the race's end and the name entry) the
    course's ranking id, + REVERSE_ID_SHIFT for an entry 3..9 while the direction flag is set; from `common` (the attract page's
    jump, with the id in R0; the flag is not read there) the shown id, the id's table and slot, and both cells on every path:
    LAST_OFFSET and ROWS for ids 0..9, SHORT_LAST_OFFSET and SHORT_ENTRIES for the reverse ids 10..19."""
    b = Block(lay["setter"])
    b.emit("movz.bw abs,reg", RANKING_INDEX, "r0")
    b.emit("cmp.b imm,abs", 0, DIRECTION_RAM)                                 # a normal race (or a name entry after one)
    b.branch("be", "common")
    b.emit("cmp.w imm,reg", 3, "r0")                                          # an original's id: its reverse table (Phase 35)
    b.branch("blt", "original")
    b.emit("cmp.w imm,reg", COURSES, "r0")
    b.branch("bge", "common")
    b.emit("add.w imm,reg", REVERSE_ID_SHIFT, "r0")                           # the entry's reverse table
    b.label("common")                                                         # `common`: the table of ranking id R0
    b.emit("mov.b reg,abs", "r0", SHOWN_ID)
    b.emit("mov.w abs(reg),reg", lay["bases"], "r0", "r1")
    b.emit("mov.w reg,abs", "r1", TABLE_RAM)
    b.emit("mov.w abs(reg),reg", lay["slots"], "r0", "r1")
    b.emit("mov.w reg,abs", "r1", SLOT_RAM)
    b.emit("cmp.w imm,reg", COURSES, "r0")
    b.branch("bge", "short")
    b.emit("mov.w imm,abs", LAST_OFFSET, LAST_OFFSET_CELL)                   # a 24-entry table: the insert and page as the game's
    b.emit("mov.b imm,abs", ROWS, ROWS_CELL)
    b.emit("rsr")
    b.label("short")
    b.emit("mov.w imm,abs", SHORT_LAST_OFFSET, LAST_OFFSET_CELL)             # a reverse table: 4 entries, one screen of 4 rows
    b.emit("mov.b imm,abs", SHORT_ENTRIES, ROWS_CELL)
    b.emit("rsr")
    b.label("original")                                                       # Phase 35, out of line: ids 0..2 with the flag set
    b.emit("add.w imm,reg", ORIG_REVERSE_SHIFT, "r0")
    b.branch("br", "common")
    return b


def _routines(lay: dict[str, int], bases: list[int], slots: list[int]) -> dict[str, bytes]:
    """The setter, the slot initialiser, the ranking-id store, the initialiser's prologue, the attract page, the title, the
    page's two hooks and (Phase 27 Task 3) the reverse block's initialiser, its boot check and its title, absolute code.
    `bases` / `slots`: the ten normal tables' (`revinit` and `originit` take the reverse tables' from the image's arrays at ids 10..16 and 17..19)."""
    setter = _setter(lay).bytes()
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
    b.emit("jsr abs", lay["revinit"])                                          # Phase 27: the reverse block with the others
    b.emit("jsr abs", lay["originit"])                                         # Phase 35: and the originals' reverse tables
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
    b.emit("cmp.w imm,reg", IDS, "r0")                                        # (ids 10..19: `revtitle`)
    b.branch("blt", "id_ok")
    b.emit("movz.bw abs,reg", DATA_INDEX, "r0")                               # never set yet: by data index, as the game
    b.label("id_ok")
    b.emit("mov.w abs(reg),reg", lay["titles"], "r0", "r0")
    b.raw(bytes([0xE8, 0x60]))                                                # jsr [R0]
    b.emit("rsr")
    title = b.bytes()
    b = Block(lay["pagecmp"])                                                 # PAGE_END_SITE: the flags of the end test (the
    b.emit("cmp.b imm,abs", SHORT_ENTRIES, ROWS_CELL)                         # `bnl` after the site reads them; `rsr` keeps them)
    b.branch("be", "short")
    b.emit("cmp.b imm,disp[reg]", TABLE_BYTES // 24, FIRST_SHOWN, "r25")      # the original's: past 24 entries (four screens)
    b.emit("rsr")
    b.label("short")
    b.emit("cmp.b imm,disp[reg]", SHORT_ENTRIES, FIRST_SHOWN, "r25")          # past 4 entries: after the first screen
    b.emit("rsr")
    pagecmp = b.bytes()
    b = Block(lay["pagerows"])                                                # PAGE_ROWS_SITE: the original's store, the count
    b.emit("mov.w reg,abs", "r1", ROW_TILE)                                   # from the cell (R3: the row loop's `dbr` count)
    b.emit("movz.bw abs,reg", ROWS_CELL, "r3")
    b.emit("rsr")
    pagerows = b.bytes()
    first_reverse = 4 * COURSES                                               # ids 10..19's offset in a word array by id

    def tables(at: int, first: int, last: int, tag: bytes, tag_at: int) -> bytes:
        """The reverse tables first..last-1 (id 10 + k), their slots and `tag`: `revinit` (the seven) and `originit` (Phase 35:
        the three originals', k = 7..9)."""
        b = Block(at)
        b.emit("pushm imm", 0x1F)                                             # R0-R4
        b.emit("mov.w imm,reg", first, "r0")                                  # k: the reverse table (id 10 + k)
        b.label("table")
        b.emit("mov.w abs(reg),reg", lay["bases"] + first_reverse, "r0", "r1")
        b.emit("mov.w abs(reg),reg", lay["slots"] + first_reverse, "r0", "r2")
        b.emit("mov.w reg,[reg]", "r1", "r2")                                 # the slot: the table's base
        b.emit("mov.w abs(reg),reg", lay["firsts"], "r0", "r2")               # the first default time
        b.emit("mov.w imm,reg", DEFAULT_NAMES + 4, "r3")                      # the game's default names (YU., RNS, TKG, ...)
        b.emit("mov.w imm,reg", 1, "r4")                                      # the rank
        b.label("entry")
        b.emit("mov.w reg,[reg]", "r4", "r1")
        b.emit("mov.w reg,disp[reg]", "r2", 4, "r1")
        b.emit("mov.w imm,disp[reg]", 0, 8, "r1")
        b.emit("mov.w imm,disp[reg]", -1, 0xC, "r1")
        b.emit("mov.w reg,disp[reg]", "r2", 0x10, "r1")
        b.emit("mov.w [reg],disp[reg]", "r3", 0x14, "r1")
        b.emit("add.w imm,reg", DEFAULT_NAME_STEP, "r3")
        b.emit("add.w imm,reg", DEFAULT_STEP, "r2")
        b.emit("add.w imm,reg", 24, "r1")
        b.emit("add.w imm,reg", 1, "r4")
        b.emit("cmp.w imm,reg", SHORT_ENTRIES + 1, "r4")
        b.branch("bne", "entry")
        b.emit("add.w imm,reg", 1, "r0")
        b.emit("cmp.w imm,reg", last, "r0")
        b.branch("bne", "table")
        b.emit("mov.w imm,abs", struct.unpack("<I", tag)[0], tag_at)
        b.emit("popm imm", 0x1F)
        b.emit("rsr")
        return b.bytes()

    revinit = tables(lay["revinit"], 0, len(REVERSE_TABLES), REVERSE_TAG_BYTES, REVERSE_TAG)
    originit = tables(lay["originit"], len(REVERSE_TABLES), REVERSE_IDS, ORIG_TAG_BYTES, ORIG_TAG)
    b = Block(lay["revtag"])                                                  # TAG_SITE: the reverse block made once, then the
    b.emit("cmp.w imm,abs", struct.unpack("<I", REVERSE_TAG_BYTES)[0], REVERSE_TAG)   # instruction replaced (absolute)
    b.branch("be", "made")
    b.emit("jsr abs", lay["revinit"])
    b.label("made")
    b.emit("cmp.w imm,abs", struct.unpack("<I", ORIG_TAG_BYTES)[0], ORIG_TAG)        # Phase 35: the originals' tables, once
    b.branch("be", "both")
    b.emit("jsr abs", lay["originit"])
    b.label("both")
    b.emit("mov.w abs,reg", MAGIC_LENGTH, "r0")
    b.emit("rsr")
    revtag = b.bytes()
    b = Block(lay["revtitle"])                                                # a reverse id's title: three prints by the shown
    b.emit("movz.bw abs,reg", SHOWN_ID, "r0")                                 # id (STRING_PRINT keeps R0)
    arg = lambda k: lay["revargs"] + 4 * REVERSE_IDS * k - first_reverse
    push_arg = lambda k: bytes.fromhex("2de0c0f3") + struct.pack("<I", arg(k)) + b"\xbf"          # mov.w X(R0), [-SP]
    push_attr = lambda attr: bytes.fromhex("1da0f4") + struct.pack("<H", attr) + b"\xbf"           # movz.hw #attr, [-SP]
    b.raw(push_attr(NAME_ATTR) + push_arg(1) + push_arg(0) + STRING_CALL)                         # the name
    b.raw(push_attr(REVERSE_ATTR) + push_arg(2) + b"\x40\xa0\xf3" + struct.pack("<I", lay["revword"]) + b"\xbf"   # REVERSE
          + STRING_CALL)
    b.raw(push_attr(WORD_ATTR) + push_arg(4) + push_arg(3) + STRING_CALL)                         # RANKING (or "")
    b.emit("rsr")
    revtitle = b.bytes()
    b = Block(lay["raceend"])                                                 # Phase 27b, after the race end's setter call: the
    b.emit("movz.bw abs,reg", DATA_INDEX, "r1")                               # raced course's group (R1: the caller reloads it)
    b.emit("mov.b abs(reg),abs(reg)", lay["positions"], "r0", ATTRACT_COUNTERS, "r1")   # := the chosen id's position in it
    b.emit("rsr")
    return {"setter": setter, "slot_init": slot_init, "id_store": id_store, "prologue": prologue, "attract": attract,
            "title": title, "pagecmp": pagecmp, "pagerows": pagerows, "revinit": revinit, "revtag": revtag, "revtitle": revtitle,
            "raceend": b.bytes(), "originit": originit}


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
    """The image at `base` in the program ROM: the arrays, the pairs, the magic, the groups, the titles and the routines."""
    lay = ranking_layout(base)
    arr = _arrays(rs, d)
    reverse = {"bases": REVERSE_TABLES + ORIG_REVERSE_TABLES,                                                   # ids 10..16, 17..19
               "slots": [REVERSE_SLOTS + 4 * k for k in range(len(REVERSE_TABLES))] + [ORIG_REVERSE_SLOTS + 4 * r for r in range(3)]}
    img = b"".join(struct.pack(f"<{IDS}I", *arr[k], *reverse[k]) for k in ("bases", "slots"))
    img += b"".join(struct.pack(f"<{COURSES}I", *arr[k]) for k in ("counts", "records", "records_oper"))
    img += b"".join(struct.pack("<II", DEFAULT_NAMES, b) for b in arr["bases"])
    img += NEW_MAGIC.ljust(20, b"\0")
    for g in attract_groups(d):
        img += bytes([len(g), *g]).ljust(GROUP_BYTES, b"\0")
    names = [lay["names"] + NAME_BYTES * (r - 3) for r in range(3, COURSES)]
    titles = [struct.unpack_from("<I", rs.boot, TITLE_TABLE - V60_BOOT + 4 * r)[0] for r in range(3)]
    titles += [lay["title3"] + TITLE_BYTES * (r - 3) for r in range(3, COURSES)]
    titles += [lay["revtitle"]] * REVERSE_IDS                                             # Phase 27: ids 10..16; Phase 35: 17..19
    img += struct.pack(f"<{IDS}I", *titles)
    for r in range(3, COURSES):
        title_columns(d[r].name)
        img += d[r].name.encode().ljust(NAME_BYTES, b"\0")
    img += REVERSE_WORD.encode() + b"\0"
    img += struct.pack(f"<{REVERSE_IDS}I", *(times[0] for times in reverse_defaults(rs, d) + original_reverse_defaults(rs, d)))
    for r, word in enumerate(ORIG_NAMES):                                                 # Phase 35: the game's own level words
        _expect(rs, ORIG_NAME_STRINGS[r], word.encode() + b"\0", f"the game's title word {word}")
    cols = [reverse_title_columns(d[r].name) for r in range(3, COURSES)] + [reverse_title_columns(w) for w in ORIG_NAMES]
    empty = lay["revword"] + len(REVERSE_WORD)                                            # "": the NUL after REVERSE
    args = ([names + list(ORIG_NAME_STRINGS), [TITLE_ROW + 2 * n for n, _, _ in cols], [TITLE_ROW + 2 * c for _, c, _ in cols],
             [empty if r is None else RANKING_STRING for _, _, r in cols], [TITLE_ROW + 2 * (r or 0) for _, _, r in cols]])
    img += b"".join(struct.pack(f"<{REVERSE_IDS}I", *a) for a in args)
    img += bytes(attract_positions(d))                                                    # Phase 27b: `raceend`'s positions
    code = _routines(lay, arr["bases"], arr["slots"])
    for name in ("setter", "slot_init", "id_store", "prologue", "attract", "title", "pagecmp", "pagerows", "revinit", "revtag",
                 "revtitle", "raceend", "originit"):
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
    select record's ranking id is stored beside the data index, the attract page and its title go through the image; Phase 27:
    the insert's two `add.w #228` read LAST_OFFSET_CELL (in place), the page's end test calls `pagecmp` and its row count
    `pagerows`, the S-RAM check's first instruction calls `revtag`; Phase 27b: the race end's setter call is followed by
    `jsr raceend`. PatchError when a site does not hold the original."""
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
    for site, expected, reg in zip(INSERT_SITES, INSERT_BYTES, INSERT_REGS):          # Phase 27: the last entry's offset
        _expect(rs, site, expected, "the insert's last-entry offset")                # from its cell, in place
        patch_span(rs, site, asm("add.w abs,reg", LAST_OFFSET_CELL, reg), len(expected))
    _expect(rs, PAGE_END_SITE, PAGE_END_BYTES, "the ranking page's end test")
    b = Block(PAGE_END_SITE); b.emit("jsr abs", lay["pagecmp"]); patch_span(rs, PAGE_END_SITE, b.bytes(), len(PAGE_END_BYTES))
    _expect(rs, PAGE_ROWS_SITE, PAGE_ROWS_BYTES, "the ranking page's row count")
    b = Block(PAGE_ROWS_SITE); b.emit("jsr abs", lay["pagerows"]); patch_span(rs, PAGE_ROWS_SITE, b.bytes(), len(PAGE_ROWS_BYTES))
    _expect(rs, TAG_SITE, TAG_SITE_BYTES, "the S-RAM check's magic length load")               # Phase 27 Task 3: the reverse
    b = Block(TAG_SITE); b.emit("jsr abs", lay["revtag"]); patch_span(rs, TAG_SITE, b.bytes(), len(TAG_SITE_BYTES))   # block's tag
    _expect(rs, RACE_END_SITE, RACE_END_SITE_BYTES, "the race end's setter call")             # Phase 27b: the setter (a 16-bit
    b = Block(RACE_END_SITE); b.raw(b"\x48" + struct.pack("<h", SETTER - RACE_END_SITE))      # bsr, from the site's first byte),
    b.emit("jsr abs", lay["raceend"]); patch_span(rs, RACE_END_SITE, b.bytes(), RACE_END_SITE_LEN)   # then `raceend`


def install_ranking(rs: RomSet, d, base: int) -> RomSet:
    """A new RomSet with the ranking image at `base` (free program ROM) and the boot sites patched (on its own, for
    tests; the build appends the image to the directory's and calls `patch_ranking_sites`)."""
    img = ranking_image(rs, d, base)
    off = base - V60_PROGRAM
    if any(x != 0xFF for x in rs.program[off:off + len(img)]):
        raise PatchError(f"program ROM at {base:#x} is not free")
    out = dataclasses.replace(rs)
    prog = bytearray(rs.program); prog[off:off + len(img)] = img
    object.__setattr__(out, "program", bytes(prog))
    patch_ranking_sites(out, ranking_layout(base))
    return out
