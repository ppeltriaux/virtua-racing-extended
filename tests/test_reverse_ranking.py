"""Phase 27: a best-time table for reverse races (docs/superpowers/specs/2026-11-14-reverse-ranking-design.md; recon
docs/spike/2026-11-phase27-reverse-ranking-recon.md).

Task 1, static (no MAME): the reverse block's battery RAM (design §4, recon §5), the setter's choice of table, slot, last-entry
offset and row count (recon §6, §7), the two insert operands that read the last-entry offset cell in place of `#228` (recon
§1) and the page's two hooks that read the row-count cell (recon §3), read back with MAME's disassembler.

Task 2, MAME (the `rank_runs` fixture, below): a reverse race records in its own 4-entry table and writes nothing else of the
battery RAM but its slot, the two cells and what a normal race on main writes too; a normal race writes as on main, byte for
byte and frame for frame; in a session of two games the cells hold each race's offset at its insert and follow every setter
call.

Task 3: static, `reverse_defaults` (the course's normal table's first four defaults: the session lead's ruling of 15 Nov on L5),
the attract groups (L3), the titles' columns (L4), the
image's arrays and the three routines (`revinit`, `revtag`, `revtitle`) read back, the S-RAM check's site; MAME (the `boot_runs`
fixture), a fresh battery RAM, one saved by main's set with a best time (the upgrade), a second boot, the attract's pages over
every member of each group, and the test mode's backup clear.

Task 4, MAME (the `place_runs` fixture; race_end.lua's VR_END_PRESET writes the table round the race's own time at its results):
a reverse time landing 2nd, 3rd and 4th, one slower than the fourth (no record, no write), ties with the last entry on a reverse
and on a normal table (the same outcome), and on `rank_runs`' two-game sessions each direction's table holding its own race's time
only."""
from __future__ import annotations

import re
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from vrtools.arcade.course import CODE_FREE, DIRECTION_RAM
from vrtools.arcade.directory import ORIGINALS, ReverseRecord, decode_directory, directory_layout, install_directory
from vrtools.arcade.disasm import listing, listing_bytes
from vrtools.arcade.patch import PatchError
from vrtools.arcade.ranking import (ATTRACT_COUNTERS, INSERT_SITES, LAST_OFFSET, LAST_OFFSET_CELL, NEW_SLOTS, NEW_TABLES,
                                    ORIG_SLOTS, ORIG_TABLES, RANKING_INDEX, REVERSE_SLOTS, REVERSE_TABLES, ROWS, ROWS_CELL,
                                    SHORT_ENTRIES, SHORT_LAST_OFFSET, SHOWN_ID, TABLE_BYTES)
from vrtools.arcade.romset import V60_BOOT, RomSet
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.convert.reverse import reverse_points
from vrtools.mame.runner import LUA_DIR, run_mame, write_centreline

FREE_RUNS = ((0x40EE80, 0x40F000), (0x40FC6D, 0x40FE00))     # recon §5: untouched through boot, attract, both races, name entry


def _converted(i: int):
    """A made-up converted entry; its race blob address lies in erased program ROM (0x2b1900..0x2c0000 on the original set), where
    `_with_blobs` writes a blob: the build reads its records for the normal and the reverse table's default times."""
    from vrtools.arcade.directory import CourseEntry10
    return CourseEntry10(f"COURSE {i}", i % 3, 1 + i % 3, 0x100000, 3 + i, i % 3, 0x2F0000 + i * 0x1000, 0xFD0000 + i * 0x100, None,
                         0x1E0000, 0x1E0400, 0, 0xB001, race=0x2B2000 + i * 0x800)


def _directory(reverse=range(3, 10)):
    """The originals and seven made-up converted entries; the variants have no race blob of their own (race 0)."""
    d = list(ORIGINALS) + [_converted(i) for i in range(3, 10)]
    return [replace(e, reverse=ReverseRecord(0x2C0000 + 0x80 * i, replace(e, race=0))) if i in reverse else e for i, e in enumerate(d)]


def _with_blobs(rs, d):
    """`rs` with a race blob (`_blob`) at each converted entry's race address (erased ROM), 3 + entry sectors: the build reads the
    blob's records for the course's default times (the stock initialiser's rule: `ranking.reverse_defaults`)."""
    for i, e in enumerate(d):
        if i >= 3 and e.race:
            rs, _ = _blob(rs, e.race, 3 + i, 0x100 * i)
    return rs


def test_the_reverse_block_s_addresses_are_the_design_s():
    from vrtools.arcade.ranking import (LAST_OFFSET_CELL, REVERSE_ID_SHIFT, REVERSE_SLOTS, REVERSE_TABLES, REVERSE_TAG, ROWS_CELL,
                                        SHORT_ENTRIES)
    assert REVERSE_TABLES == (0x40EE80, 0x40EEE0, 0x40EF40, 0x40EFA0, 0x40FC70, 0x40FCD0, 0x40FD30)
    assert (REVERSE_SLOTS, REVERSE_TAG, LAST_OFFSET_CELL, ROWS_CELL) == (0x40FD90, 0x40FDAC, 0x40FDB0, 0x40FDB4)
    assert (SHORT_ENTRIES, REVERSE_ID_SHIFT) == (4, 7)


def test_the_reverse_block_lies_in_the_free_battery_ram_and_overlaps_nothing():
    """The seven 4-entry tables, the seven slot words, the tag and the two cells each lie inside one of the two free runs, and
    no two of them (nor the converted courses' tables, NEW_SLOTS, RANKING_INDEX, SHOWN_ID, ATTRACT_COUNTERS) share a byte."""
    from vrtools.arcade.ranking import (ATTRACT_COUNTERS, LAST_OFFSET_CELL, NEW_SLOTS, NEW_TABLES, RANKING_INDEX, REVERSE_SLOTS,
                                        REVERSE_TABLES, REVERSE_TAG, ROWS_CELL, SHORT_ENTRIES, SHOWN_ID, TABLE_BYTES)
    ours = ([(t, t + 24 * SHORT_ENTRIES) for t in REVERSE_TABLES] + [(REVERSE_SLOTS, REVERSE_SLOTS + 4 * len(REVERSE_TABLES)),
            (REVERSE_TAG, REVERSE_TAG + 4), (LAST_OFFSET_CELL, LAST_OFFSET_CELL + 4), (ROWS_CELL, ROWS_CELL + 1)])
    assert all(any(lo <= a and b <= hi for lo, hi in FREE_RUNS) for a, b in ours)
    others = ([(t, t + TABLE_BYTES) for t in NEW_TABLES] + [(NEW_SLOTS, NEW_SLOTS + 40), (RANKING_INDEX, RANKING_INDEX + 1),
              (SHOWN_ID, SHOWN_ID + 1), (ATTRACT_COUNTERS, ATTRACT_COUNTERS + 3)])
    spans = sorted(ours + others)
    assert all(b <= c for (_, b), (c, _) in zip(spans, spans[1:])), spans


def test_reverse_ids_are_the_entries_with_a_reverse_variant_plus_seven():
    from vrtools.arcade.ranking import reverse_ids
    assert reverse_ids(_directory()) == list(range(10, 17))
    assert reverse_ids(_directory(reverse=(4, 6))) == [11, 13]
    assert reverse_ids((ORIGINALS * 4)[:10]) == []


SITES = {"insert": 0xFC40F9, "bubble": 0xFC4184, "page_end": 0xFC3CA1, "page_rows": 0xFC3D8C}
ORIGINAL = {"insert": ("8421f428020000", ["add.w #228, R1"]), "bubble": ("8420f428020000", ["add.w #228, R0"]),
            "page_end": ("b880f4181936", ["cmp.b #18, 36[R25]"]),
            "page_rows": ("2d01f298db53ff2d23e6", ["mov.w R1, 501924[PC]", "mov.w #6, R3"])}


def _text(lines):
    return [" ".join(l.text.split()) for l in lines]


def _span(rs, site, n):
    return [l for l in listing(rs, site, n) if l.addr < site + n]


def test_the_site_constants_hold_the_recon_s_original_bytes(romset_zip):
    """Recon §1 and §3, on the original set: the two `add.w #228` of the insert (the qualify test and the bubble), the page's
    end test and its first row's store with the row count."""
    from vrtools.arcade.ranking import (INSERT_BYTES, INSERT_SITES, PAGE_END_BYTES, PAGE_END_SITE, PAGE_ROWS_BYTES, PAGE_ROWS_SITE)
    rs = RomSet.from_zip(romset_zip)
    assert INSERT_SITES == (SITES["insert"], SITES["bubble"]) and (PAGE_END_SITE, PAGE_ROWS_SITE) == (SITES["page_end"], SITES["page_rows"])
    have = dict(zip(SITES, (*INSERT_BYTES, PAGE_END_BYTES, PAGE_ROWS_BYTES)))
    for name, site in SITES.items():
        want, texts = ORIGINAL[name]
        assert have[name].hex() == want and rs.boot[site - V60_BOOT:site - V60_BOOT + len(want) // 2].hex() == want, name
        assert _text(_span(rs, site, len(want) // 2)) == texts, name


@pytest.mark.parametrize("name,offset", [("insert", 3), ("bubble", 4), ("page_end", 4), ("page_rows", 9)])
def test_a_changed_site_is_refused(romset_zip, name, offset):
    site = SITES[name]
    rs = RomSet.from_zip(romset_zip)
    boot = bytearray(rs.boot)
    boot[site - V60_BOOT + offset] ^= 0x01
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match=f"{site:#x}"):
        install_directory(rs, (ORIGINALS * 4)[:10])


def _installed(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    return rs, install_directory(rs, (ORIGINALS * 4)[:10]), directory_layout()


def test_the_insert_reads_the_last_entry_offset_from_its_cell(romset_zip):
    """Both `add.w #228` become `add.w LAST_OFFSET_CELL, Rn` in place, exactly 7 bytes; the instructions around them are the
    original's."""
    from vrtools.arcade.ranking import INSERT_SITES, LAST_OFFSET_CELL
    rs, out, _ = _installed(romset_zip)
    for site, reg in zip(INSERT_SITES, ("R1", "R0")):
        lines = _span(out, site, 7)
        assert _text(lines) == [f"add.w {LAST_OFFSET_CELL:X}, {reg}"] and len(lines) == 1, hex(site)
        assert listing(out, site + 7, 3) == listing(rs, site + 7, 3)
        assert listing(out, site - 7, 1) == listing(rs, site - 7, 1)


def _routine(out, lay, name):
    end = min(a for a in lay.values() if a > lay[name])
    return [l for l in listing(out, lay[name], end - lay[name]) if l.addr < end]


def test_the_page_calls_pagecmp_and_pagerows(romset_zip):
    """The end test (6 bytes) is `jsr pagecmp`, its `bnl FC3CEC` kept (the flags survive `rsr`); `pagecmp` compares the first
    entry shown (+0x36) with 24 as the original, or with SHORT_ENTRIES when the row-count cell holds SHORT_ENTRIES (one screen).
    The row store and count (10 bytes) are `jsr pagerows` and four nops; `pagerows` stores the first row's tile address as the
    original and loads R3 (the `dbr` count) from the row-count cell."""
    from vrtools.arcade.ranking import PAGE_END_SITE, PAGE_ROWS_SITE, ROWS_CELL, ranking_layout
    rs, out, lay = _installed(romset_zip)
    rl = ranking_layout(lay["ranking"])
    assert _text(_span(out, PAGE_END_SITE, 6)) == [f"jsr {rl['pagecmp']:X}"]
    assert _text(listing(out, PAGE_END_SITE + 6, 1)) == ["bnl FC3CEC"] and listing(out, PAGE_END_SITE + 6, 3) == listing(rs, PAGE_END_SITE + 6, 3)
    assert _text(_span(out, PAGE_ROWS_SITE, 10)) == [f"jsr {rl['pagerows']:X}"] + ["nop"] * 4
    assert listing(out, PAGE_ROWS_SITE + 10, 3) == listing(rs, PAGE_ROWS_SITE + 10, 3)
    cmp = _routine(out, rl, "pagecmp")
    assert _text(cmp) == [f"cmp.b #4, {ROWS_CELL:X}", f"be {cmp[4].addr:X}", "cmp.b #18, 36[R25]", "rsr", "cmp.b #4, 36[R25]", "rsr"]
    assert _text(_routine(out, rl, "pagerows")) == ["mov.w R1, 501924", f"movz.bw {ROWS_CELL:X}, R3", "rsr"]


def _paths(lines, start):
    """Every path through the decoded routine from `start` to an `rsr`: the list of instruction texts along it."""
    at = {l.addr: k for k, l in enumerate(lines)}
    out = []

    def walk(k, seen):
        while True:
            t = " ".join(lines[k].text.split())
            seen = seen + [t]
            if t == "rsr":
                out.append(seen)
                return
            m = re.fullmatch(r"(b\w+) ([0-9A-F]+)", t)
            if m:
                target = at[int(m.group(2), 16)]
                assert target > k, t                                   # forward branches only: every path ends
                if m.group(1) == "br":
                    k = target
                    continue
                walk(target, seen)
            k += 1
    walk(at[start], [])
    return out


def test_the_setter_chooses_by_the_flag_at_the_race_and_by_the_id_in_the_attract(romset_zip):
    """MAME's disassembler on the setter: from its entry (the race's end and the name entry, through 0xfc4208) it takes the
    ranking id and adds REVERSE_ID_SHIFT when the direction flag is set and the id is 3..9; from `common` (the attract page's
    entry, which never reads the flag) it stores the shown id, takes the table and slot of the id from the image's arrays (ids
    10..16 the reverse ones) and writes BOTH cells on every path: 0x228 and 6 for ids 0..9, 0x48 and 4 for ids 10..16."""
    from vrtools.arcade.ranking import (LAST_OFFSET_CELL, RANKING_INDEX, ROWS_CELL, SHOWN_ID, SLOT_RAM, TABLE_RAM, ranking_image,
                                        ranking_layout)
    rs = _with_blobs(RomSet.from_zip(romset_zip), _directory())
    base = CODE_FREE[0]
    lay = ranking_layout(base)
    img = ranking_image(rs, _directory(), base)
    lines = listing_bytes(img[lay["setter"] - base:lay["slot_init"] - base], lay["setter"])
    texts = _text(lines)
    at = {l.addr: k for k, l in enumerate(lines)}
    c = at[lay["common"]]
    assert texts[:c] == [f"movz.bw {RANKING_INDEX:X}, R0", f"cmp.b #0, {DIRECTION_RAM:X}", f"be {lay['common']:X}",
                         "cmp.w #3, R0", f"blt {lay['common']:X}", "cmp.w #A, R0", f"bge {lay['common']:X}", "add.w #7, R0"]
    short = lines[c + 10].addr
    assert texts[c:] == [f"mov.b R0, {SHOWN_ID:X}", f"mov.w {lay['bases']:X}(R0), R1", f"mov.w R1, {TABLE_RAM:X}",
                         f"mov.w {lay['slots']:X}(R0), R1", f"mov.w R1, {SLOT_RAM:X}", "cmp.w #A, R0", f"bge {short:X}",
                         f"mov.w #228, {LAST_OFFSET_CELL:X}", f"mov.b #6, {ROWS_CELL:X}", "rsr",
                         f"mov.w #48, {LAST_OFFSET_CELL:X}", f"mov.b #4, {ROWS_CELL:X}", "rsr"]
    for entry, count in ((lay["setter"], 8), (lay["common"], 2)):
        paths = _paths(lines, entry)
        assert len(paths) == count
        for p in paths:                                                # each cell written exactly once on every path
            assert sum(t.endswith(f", {LAST_OFFSET_CELL:X}") for t in p) == 1 and sum(t.endswith(f", {ROWS_CELL:X}") for t in p) == 1, p
    assert not any(f"{DIRECTION_RAM:X}" in t for t in texts[c:])       # the attract page's entry never reads the flag


def test_the_image_s_arrays_run_on_over_the_reverse_ids(romset_zip):
    """The setter's two arrays are indexed by the ranking id 0..16: ids 10..16 (entries 3..9 + REVERSE_ID_SHIFT) hold the
    reverse tables and their slots, in entry order; ids 0..9 are as before."""
    from vrtools.arcade.ranking import (NEW_SLOTS, NEW_TABLES, ORIG_SLOTS, ORIG_TABLES, REVERSE_ID_SHIFT, REVERSE_SLOTS,
                                        REVERSE_TABLES, ranking_image, ranking_layout)
    rs = _with_blobs(RomSet.from_zip(romset_zip), _directory())
    base = CODE_FREE[0]
    lay = ranking_layout(base)
    img = ranking_image(rs, _directory(), base)
    bases = struct.unpack_from("<17I", img, lay["bases"] - base)
    slots = struct.unpack_from("<17I", img, lay["slots"] - base)
    assert bases[:10] == ORIG_TABLES + NEW_TABLES and slots[:10] == ORIG_SLOTS + tuple(NEW_SLOTS + 4 * r for r in range(3, 10))
    for entry in range(3, 10):
        k = entry - 3
        assert bases[entry + REVERSE_ID_SHIFT] == REVERSE_TABLES[k] and slots[entry + REVERSE_ID_SHIFT] == REVERSE_SLOTS + 4 * k


def test_race_end_can_tap_from_a_frame_and_drive_a_second_game():
    """Task 2's harness switches (race_end.lua's header documents each): VR_END_TABLE takes several ranges, VR_END_READS a read
    tap, VR_END_TAP_AT the frame the taps go in, VR_END_NEXT a second game (its race held as the first) and VR_END_NEXT_LINE its
    autopilot line, handed over at its load through autopilot.lua's `vr_autopilot_load`. W lines carry the bus mask."""
    text = (LUA_DIR / "race_end.lua").read_text()
    for name in ("VR_END_TABLE", "VR_END_READS", "VR_END_TAP_AT", "VR_END_NEXT", "VR_END_NEXT_LINE"):
        assert f'os.getenv("{name}")' in text and f"\n--   {name} " in text, name
    assert 'out:write(string.format("W %d %x %x %x %x\\n", frame, cpu.state["PC"].value, offset, data, mask))' in text
    assert "_G.vr_autopilot_load(next_line)" in text
    pilot = (LUA_DIR / "autopilot.lua").read_text()
    assert 'local pts = read_line(os.getenv("VR_AUTOPILOT"))' in pilot and "_G.vr_autopilot_load = function(path)" in pilot


# --- Task 2 (MAME): a reverse race records in its own table; a normal race writes as on main ----------------------------------
# One-lap races of race_end.lua under the autopilot on the session's seven-course set (`tests.test_tgp_build._seven`), made once
# per session and in parallel by `rank_runs`: write taps over the battery RAM below the stack (BATTERY) and a read tap on the two
# cells from the coin (TAP_AT) on, the mode log, and the battery RAM MAME saves when the run ends.
from tests.test_dirscreen_build import NO_RECORD, RECORD, Line      # noqa: E402  (the modes after a finish without, with a record)
from tests.test_race_build import _drive_line                        # noqa: E402
from tests.test_tgp_build import _build, _seven                      # noqa: E402

METROPOLIS, AMAZON_FALLS = 6, 4
MAIN_SET = Path(__file__).resolve().parents[1] / "out" / "p26play6"  # main's tested set (e7c52ae's product code; git-ignored)
MAIN_REVERSE_TABLE = 0x2797EC          # directory_layout()["reverse"] on e7c52ae's tree (autoplay.lua answers the screen by it):
                                       # the same address as this tree's, measured on both
BATTERY = (0x40E000, 0x40FDFF)         # the persistent battery RAM up to the stack's margin (0x40fe00..: the stack, written by
                                       # every call; recon §5)
BOOKKEEPING = range(0x40E800, 0x40EA00)
TAP_AT = 600                           # the coin: autoplay.lua's VR_POKE (the preset) writes on frames 1..599
# What a normal race on main writes in BATTERY besides the tables, the slots and the bookkeeping, measured on main's two runs
# here (out/p26play6): the game's record 0x40f000..0x40f007 (0xfe0ced at the coin, 0xfe0d03 at the game's end), the ranking id
# (`id_store` at the course select), the shown id (the setter) and the attract page's group counters.
MAIN_OUTSIDE = (set(range(0x40F000, 0x40F008)) | {RANKING_INDEX, SHOWN_ID} | set(range(ATTRACT_COUNTERS, ATTRACT_COUNTERS + 3)))
CELLS = set(range(LAST_OFFSET_CELL, LAST_OFFSET_CELL + 4)) | {ROWS_CELL}
TABLES = set().union(*(range(t, t + TABLE_BYTES) for t in ORIG_TABLES + NEW_TABLES), *(range(a, a + 4) for a in ORIG_SLOTS),
                     range(NEW_SLOTS, NEW_SLOTS + 40))
# The reverse table's preset (poked before the coin, as recon run E did, over the table `revinit` made at boot: known times; the
# initialised content is asserted by the Task 3 tests): ranks 1..4, run E's times 5'00..5'15 (1/32 s, slower than any one-lap
# race: Task 2's Amazon Falls reverse record was 52.59 s), +8 = 0, +0xc = -1, a name.
PRESET_TIMES = (0x2580, 0x2620, 0x26C0, 0x2760)
PRESET_NAME = b"AAA\0"
ENTRY = struct.Struct("<IIiiI4s")      # rank, time, view, player, time, name (the game's 24 bytes)
RUNS = [("normal", METROPOLIS), ("reverse", METROPOLIS), ("normal", AMAZON_FALLS), ("reverse", AMAZON_FALLS),
        ("main", METROPOLIS), ("main", AMAZON_FALLS), ("reverse,normal", METROPOLIS), ("normal,reverse", AMAZON_FALLS)]
RUN_SECONDS, SESSION_SECONDS = 200, 300     # one game to the attract after its name entry; two games (the second's name entry)


@dataclass(frozen=True)
class RankRun:
    races: tuple[str, ...]                  # the directions raced, in order
    loads: list[int]                        # each race's load frame
    lines: list[Line]                       # M lines
    writes: list[tuple[int, int, int, int, int]]    # W lines: (frame, pc, address, data, mask): a 16-bit bus, even addresses
    reads: list[tuple[int, int, int, int, int]]     # R lines, the same fields
    battery: bytes                          # MAME's saved battery RAM, 0x400000..0x40ffff
    times: tuple[tuple[int, int], ...] = ()                 # T lines (Task 4): (frame, the race's time [0x501168]), a race each
    presets: tuple[tuple[int, int, bytes], ...] = ()        # P lines (VR_END_PRESET): (frame, table, the bytes read back)
    snaps: tuple[int, ...] = ()                             # S lines (VR_END_SNAP): the snapshots' frames


def _parse_rank(path, races, battery) -> RankRun:
    loads, lines, writes, reads, times, presets, snaps = [], [], [], [], [], [], []
    for row in open(path):
        tag, *f = row.split()
        if tag == "L":
            loads.append(int(f[0]))
        elif tag == "M":
            lines.append(Line(int(f[0]), int(f[1], 16), int(f[2]), int(f[3], 16), int(f[4], 16), int(f[5], 16)))
        elif tag in ("W", "R"):
            (writes if tag == "W" else reads).append((int(f[0]),) + tuple(int(x, 16) for x in f[1:5]))
        elif tag == "T":
            times.append((int(f[0]), int(f[1])))
        elif tag == "P":
            presets.append((int(f[0]), int(f[1], 16), bytes.fromhex(f[2])))
        elif tag == "S":
            snaps.append(int(f[0]))
    return RankRun(races, loads, lines, writes, reads, battery, tuple(times), tuple(presets), tuple(snaps))


def _preset(entry: int) -> str:
    """autoplay.lua's VR_POKE for the entry's reverse table (decimal bytes)."""
    blob = b"".join(ENTRY.pack(k + 1, t, 0, -1, t, PRESET_NAME) for k, t in enumerate(PRESET_TIMES))
    return ",".join(f"{REVERSE_TABLES[entry - 3] + i:x}={b}" for i, b in enumerate(blob))


def _make(base: Path, build: Path, conv, kind: str, entry: int, label: str | None = None, extra: dict | None = None,
          boot_preset: bool = True) -> RankRun:
    """One run of `kind` ("normal", "reverse", "main", or two directions "a,b": two games) on `entry`, in base / `label`; `extra`
    is added to the environment (Task 4: race_end.lua's VR_END_PRESET, VR_END_SNAP); without `boot_preset` the reverse table is
    not poked before the coin (it holds `revinit`'s)."""
    races = ("normal",) if kind == "main" else tuple(kind.split(","))
    wd = base / (label or f"{kind.replace(',', '-')}{entry}")
    line = _drive_line(conv[entry - 3])
    paths = {d: write_centreline(wd / f"{d}.csv", reverse_points(line) if d == "reverse" else line) for d in set(races)}
    env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
           "VR_AUTOPILOT": str(paths[races[0]]), "VR_EXTRA_LUA": str(LUA_DIR / "race_end.lua"), "VR_END_LOG": str(wd / "end.txt"),
           "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}", "VR_END_TABLE": f"{BATTERY[0]:x}-{BATTERY[1]:x}",
           "VR_END_READS": f"{LAST_OFFSET_CELL:x}-{ROWS_CELL + 1:x}", "VR_END_TAP_AT": str(TAP_AT)}
    if races[0] == "reverse":
        env["VR_DIRECTION"] = "1"
    if len(races) > 1:
        env.update({"VR_END_NEXT": f"{WHEEL_FOR_ENTRY[entry]}:{int(races[1] == 'reverse')}", "VR_END_NEXT_LINE": str(paths[races[1]])})
    if "reverse" in races and boot_preset:
        env["VR_POKE"] = _preset(entry)
    env.update(extra or {})
    rom = build
    if kind == "main":
        rom, env["VR_REVERSE_TABLE"] = MAIN_SET, f"{MAIN_REVERSE_TABLE:x}"
    run_mame(LUA_DIR / "autoplay.lua", SESSION_SECONDS if len(races) > 1 else RUN_SECONDS, wd, rom, env=env)
    return _parse_rank(wd / "end.txt", races, (wd / "nvram" / "vr" / "nvram").read_bytes())


class RankSession:
    """The session's runs (RUNS), made in parallel at the first use; a run that failed raises its error when asked for."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        out, conv = _seven(romset_zip, saturn_cue)
        build = _build(base, romset_zip, out)
        kinds = [k for k in RUNS if k[0] != "main" or (MAIN_SET / "vr.zip").is_file()]
        with ThreadPoolExecutor(len(kinds)) as ex:
            futures = {k: ex.submit(_make, base, build, conv, *k) for k in kinds}
        self.runs: dict[tuple[str, int], RankRun | BaseException] = {}
        for k, f in futures.items():
            self.runs[k] = f.exception() or f.result()

    def run(self, kind: str, entry: int) -> RankRun:
        if (kind, entry) not in self.runs:
            pytest.skip(f"main's set is not at {MAIN_SET}")
        r = self.runs[(kind, entry)]
        if isinstance(r, BaseException):
            raise r
        return r


_RANK: dict[str, RankSession] = {}


@pytest.fixture
def rank_runs(romset_zip, saturn_cue, tmp_path_factory) -> RankSession:
    key = str(romset_zip)
    if key not in _RANK:
        _RANK[key] = RankSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("rank"))
    return _RANK[key]


def _window(run: RankRun, k: int) -> range:
    """The frames of race k's game: from its load to the next race's load (or the run's end)."""
    return range(run.loads[k], run.loads[k + 1] if k + 1 < len(run.loads) else 1 << 30)


def _bytes(writes):
    """W lines as byte writes: (frame, pc, address, value)."""
    out = []
    for f, pc, a, d, m in writes:
        out += [(f, pc, a + k, d >> 8 * k & 0xFF) for k in (0, 1) if m >> 8 * k & 0xFF]
    return out


def _race(run: RankRun, k: int) -> list[Line]:
    return [l for l in run.lines if l.frame in _window(run, k)]


def _driving(lines):
    """The race's mode-0x12..0x14 lines (its load up to the first mode outside 0x11..0x14)."""
    end = next((k for k, l in enumerate(lines) if not 0x11 <= l.mode <= 0x14), len(lines))
    return [l for l in lines[:end] if 0x12 <= l.mode <= 0x14]


def _after_finish(lines):
    """The modes from the race's end to its game's attract load (0x02), each once in order."""
    end = next(k for k, l in enumerate(lines) if not 0x11 <= l.mode <= 0x14)
    modes = []
    for l in lines[end:]:
        if not modes or modes[-1] != l.mode:
            modes.append(l.mode)
        if l.mode == 0x02:
            break
    return tuple(modes)


@pytest.mark.parametrize("entry", [METROPOLIS, AMAZON_FALLS])
def test_a_reverse_race_records_in_its_own_table(rank_runs, entry):
    """A one-lap reverse race, its reverse table preset (known times over `revinit`'s): the record flag is set, the name entry (mode
    0x1e) comes, and the modes after the finish are a record's. From the coin to the run's end every battery write lies in that
    course's reverse table, its slot word, the two cells, the bookkeeping 0x40e800..0x40e9ff, or MAIN_OUTSIDE (what a normal race
    on main writes besides the tables); no normal table or slot is written. The table ends as the game's insert leaves it: entry
    0 holds the race's time at +4 and +0x10 and the name entry's three spaces, the preset entries moved down one with their
    times, the old fourth gone; the rank fields are the preset's 1..4 (the insert never writes +0). The slot holds entry 0."""
    run = rank_runs.run("reverse", entry)
    table, slot = REVERSE_TABLES[entry - 3], REVERSE_SLOTS + 4 * (entry - 3)
    lines = _race(run, 0)
    race = _driving(lines)
    assert race and all(l.flag == 1 for l in race), race[:3]                 # the loader served the variant
    assert any(l.record & 1 for l in lines)
    assert _after_finish(lines) == RECORD, [hex(m) for m in _after_finish(lines)]
    written = {a for _, _, a, _ in _bytes(run.writes)}
    ours = set(range(table, table + 24 * SHORT_ENTRIES)) | set(range(slot, slot + 4))
    allowed = ours | CELLS | set(BOOKKEEPING) | MAIN_OUTSIDE
    assert written <= allowed, sorted(map(hex, written - allowed))[:10]
    assert not written & TABLES, sorted(map(hex, written & TABLES))[:10]
    fields = {table + 24 * k + o for k in range(SHORT_ENTRIES) for o in range(4, 24)}    # all but the ranks: a 4th-to-1st bubble
    assert written & ours == fields | set(range(slot, slot + 4)) and CELLS <= written, sorted(map(hex, ours - written))[:10]
    entries = [ENTRY.unpack_from(run.battery, table - 0x400000 + 24 * k) for k in range(SHORT_ENTRIES)]
    rank, time, view, _, time2, name = entries[0]
    print("REVERSE RECORD", entry, "time", time, f"({time / 32:.2f} s)", "view", view)
    assert [e[0] for e in entries] == [1, 2, 3, 4]
    assert time == time2 and 0 < time < PRESET_TIMES[0] and view in range(4) and name == b"   \0", entries[0]
    assert [(e[1], e[2], e[3], e[4], e[5]) for e in entries[1:]] == [(t, 0, -1, t, PRESET_NAME) for t in PRESET_TIMES[:3]]
    assert struct.unpack_from("<I", run.battery, slot - 0x400000)[0] == table


def _boot_pc(pc: int):
    """A PC kept for the comparison with main only in the boot ROM: the project's routines in the program ROM moved (Task 1)."""
    return pc if pc >= V60_BOOT else None


@pytest.mark.parametrize("entry", [METROPOLIS, AMAZON_FALLS])
def test_a_normal_race_writes_as_on_main(rank_runs, entry):
    """The same one-lap normal race on main's set (out/p26play6, built from e7c52ae's tree): the course's normal table and slot
    get the identical write log (frame, PC, address, data); the mode log is identical frame for frame (the select handler
    compared where it is a boot ROM address); every other battery write is identical (frame, address, data and the PC where it
    is in the boot ROM) but the two cells, which main does not have and this set writes at every setter call; main's writes
    besides the tables, slots and bookkeeping are MAIN_OUTSIDE's."""
    run, main = rank_runs.run("normal", entry), rank_runs.run("main", entry)
    table, slot = NEW_TABLES[entry - 3], NEW_SLOTS + 4 * entry
    mine = lambda w: table <= w[2] < table + TABLE_BYTES or slot <= w[2] < slot + 4
    log = [w for w in run.writes if mine(w)]
    assert log and log == [w for w in main.writes if mine(w)], (len(log), len([w for w in main.writes if mine(w)]))
    assert _after_finish(_race(run, 0)) == RECORD == _after_finish(_race(main, 0))
    frames = lambda r: [(l.frame, l.mode, l.state, l.flag, l.record, _boot_pc(l.handler)) for l in r.lines]
    assert run.loads == main.loads and frames(run) == frames(main)
    outside = {a for _, _, a, _ in _bytes(main.writes)} - TABLES - set(BOOKKEEPING)
    assert outside <= MAIN_OUTSIDE and set(range(0x40F000, 0x40F008)) | {RANKING_INDEX, SHOWN_ID} <= outside, sorted(map(hex, outside))
    cells = lambda w: LAST_OFFSET_CELL <= w[2] <= ROWS_CELL
    key = lambda w: (w[0], _boot_pc(w[1]), w[2], w[3], w[4])
    assert [key(w) for w in run.writes if not cells(w)] == [key(w) for w in main.writes]
    assert any(cells(w) for w in run.writes)


@pytest.mark.parametrize("kind,entry", [("reverse,normal", METROPOLIS), ("normal,reverse", AMAZON_FALLS)])
def test_the_cells_follow_every_setter_call(rank_runs, kind, entry):
    """Two games in one MAME session (race_end.lua's VR_END_NEXT): a reverse race then a normal one on Metropolis, a normal then
    a reverse one on Amazon Falls. Each race is served its direction and records; at each insert both sites (the qualify test
    and the bubble) read the last-entry offset cell once, holding 0x48 in a reverse race and 0x228 in a normal one. Every setter
    call (its store of the shown id) is followed in the same frame by its writes of both cells, by the id: 0x48 and 4 for a
    reverse id (10..16), 0x228 and 6 for the others; no cell is written otherwise. The calls include each race's end and name
    entry (the reverse race's with the course's reverse id) and the attract pages between and after the games. This is not
    cross-game coverage: the attract page between the games resets both cells to 0x228 / 6, so in the reverse-then-normal order
    that reset alone would satisfy the second insert's 0x228; only the normal-then-reverse order shows the race's own setter
    call at work."""
    run = rank_runs.run(kind, entry)
    assert len(run.loads) == 2, run.loads
    calls, last = [], None
    for f, pc, a, d, m in run.writes:
        if a == SHOWN_ID & ~1 and m & 0xFF00:
            last = {"frame": f, "id": d >> 8, "cells": []}
            calls.append(last)
        elif LAST_OFFSET_CELL <= a <= ROWS_CELL:
            assert last is not None and last["frame"] == f, (f, hex(pc), hex(a))
            last["cells"].append((a, d & m, m))
    print("SETTER CALLS", kind, entry, [(c["frame"], c["id"]) for c in calls])
    for c in calls:
        offset, rows = (SHORT_LAST_OFFSET, SHORT_ENTRIES) if c["id"] >= 10 else (LAST_OFFSET, ROWS)
        assert c["cells"] == [(LAST_OFFSET_CELL, offset, 0xFFFF), (LAST_OFFSET_CELL + 2, 0, 0xFFFF), (ROWS_CELL, rows, 0xFF)], c
    names = []                                                                       # the name entries' calls
    for k, direction in enumerate(run.races):
        lines = _race(run, k)
        race = _driving(lines)
        assert race and all(l.flag == (direction == "reverse") for l in race), (k, race[:3])
        assert _after_finish(lines) == RECORD, (k, [hex(m) for m in _after_finish(lines)])
        want = SHORT_LAST_OFFSET if direction == "reverse" else LAST_OFFSET
        reads = [(f, pc, a, d & m) for f, pc, a, d, m in run.reads if f in _window(run, k) and pc in INSERT_SITES]
        halves = ((LAST_OFFSET_CELL, want), (LAST_OFFSET_CELL + 2, 0))               # a 32-bit read on the 16-bit bus
        assert [r[1:] for r in reads] == [(site, a, v) for site in INSERT_SITES for a, v in halves], (k, reads)
        at = next(j for j, c in enumerate(calls) if c["frame"] == reads[0][0])       # the race end's call, on the insert's frame
        ident = entry + 7 if direction == "reverse" else entry
        assert calls[at]["id"] == ident and calls[at + 1]["id"] == ident, calls[at:at + 2]     # and the name entry's
        names.append(calls[at + 1]["frame"])
    pages = [c for c in calls if c["frame"] > names[0] and c["frame"] not in _window(run, 1) or c["frame"] > names[1]]
    assert any(c["frame"] < run.loads[1] for c in pages) and any(c["frame"] > names[1] for c in pages), pages


# --- Task 3: the reverse block's initialiser, its boot tag, the attract groups and the titles ----------------------------------
def _planned(reverse=range(3, 10)):
    """_directory with the seven planned courses' names and hosts (tencourse.COURSES: Alpine on Big Forest's slot, Diablo Canyon
    and Metropolis on Acropolis's, the other four on Bay Bridge's)."""
    from vrtools.arcade.tencourse import COURSES as PLANS
    d = _directory(reverse)
    for i, p in enumerate(PLANS, 3):
        e = replace(d[i], name=p.name, template=p.template)
        d[i] = replace(e, reverse=replace(e.reverse, entry=replace(e, race=0, reverse=None)) if e.reverse else None)
    return d


def test_the_attract_groups_put_each_reverse_id_straight_after_its_course(romset_zip):
    """L3: a reverse table follows its own course's table in its host's group: Bay Bridge's nine members, Acropolis's five, Big
    Forest's three on the planned set; only entries with a reverse variant get one. The image's 16-byte groups hold them."""
    from vrtools.arcade.ranking import GROUP_BYTES, attract_groups, ranking_image, ranking_layout
    groups = attract_groups(_planned())
    assert groups == [[0, 4, 11, 7, 14, 8, 15, 9, 16], [1, 5, 12, 6, 13], [2, 3, 10]] and [len(g) for g in groups] == [9, 5, 3]
    assert attract_groups(_planned(reverse=(4, 6))) == [[0, 4, 11, 7, 8, 9], [1, 5, 6, 13], [2, 3]]
    rs = _with_blobs(RomSet.from_zip(romset_zip), _planned())
    base = CODE_FREE[0]
    lay = ranking_layout(base)
    img = ranking_image(rs, _planned(), base)
    for k, g in enumerate(groups):
        row = img[lay["groups"] - base + GROUP_BYTES * k:lay["groups"] - base + GROUP_BYTES * (k + 1)]
        assert row == bytes([len(g), *g]).ljust(GROUP_BYTES, b"\0"), k


def _blob(rs, at, sectors, seed):
    """A race blob at `at` (erased program ROM) whose records' words are known: (variant, level) record words seed + 37 * word
    index + 1000 * (4 * variant + level), `sectors` checkpoints. Returns the RomSet and the words of the records in blob order."""
    from vrtools.arcade.race import EXTENSIONS, LEVELS, VARIANTS, RaceBlob, TimeRecord, car_table, encode_race_blob
    times, words = {}, []
    for v in range(VARIANTS):
        for level in range(LEVELS):
            w = [seed + 37 * j + 1000 * (4 * v + level) for j in range(EXTENSIONS + 1)]
            times[(v, level)] = TimeRecord(w[0], tuple(w[1:]))
            words += w
    blob = encode_race_blob(RaceBlob(times, tuple(range(0, 40 * sectors, 40)), car_table(rs, 0)), at)
    prog = bytearray(rs.program)
    assert all(x == 0xFF for x in prog[at - 0x200000:at - 0x200000 + len(blob)])
    prog[at - 0x200000:at - 0x200000 + len(blob)] = blob
    out = RomSet(bytes(prog), rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    return out, words


def test_reverse_defaults_are_the_course_s_normal_table_defaults(romset_zip):
    """The session lead's ruling of 15 Nov (replacing L5's first wording), per entry 3..9: its reverse table's four default times
    are entries 0..3 of what the stock initialiser (0xfc3b91..0xfc3bdd) gives the course's NORMAL table — the first 5 x sectors words
    from the normal race blob's level-0 record (variant 0; past its 24 words the sum runs on into the next record, as the game's
    loop does) summed, rounded up to the minute (0x780), then +5 s (0xa0) an entry. The reverse variant's blob plays no part. An
    original's copy (race 0) takes its template's original tables (Bay Bridge and Big Forest 4'00, Acropolis 5'00, as
    test_ranking's fresh battery RAM measures them). A normal blob address that holds no checkpoint record is refused."""
    from vrtools.arcade.race import RACE_BLOB_BYTES
    from vrtools.arcade.ranking import reverse_defaults
    rs = RomSet.from_zip(romset_zip)
    d = _planned()
    want = []
    for k, i in enumerate(range(3, 10)):
        sectors = 3 + k * 3                                                     # 3..21 sectors: up to 105 words, five records
        rs, words = _blob(rs, d[i].race, sectors, 0x1F3 + 0x51 * k)
        total = sum(words[:5 * sectors])
        first = (total + 0x77F) // 0x780 * 0x780
        want.append([first, first + 0xA0, first + 0x140, first + 0x1E0])
    assert reverse_defaults(rs, d) == want
    for k, i in enumerate(range(3, 10)):                                        # the variants' own blobs: other sums, no effect
        at = 0x28C000 + RACE_BLOB_BYTES * k
        rs, _ = _blob(rs, at, 21 - k * 3, 0x9000 + 0x77 * k)
        d[i] = replace(d[i], reverse=replace(d[i].reverse, entry=replace(d[i].reverse.entry, race=at)))
    assert reverse_defaults(rs, d) == want
    stock = {0: 0x1E00, 1: 0x2580, 2: 0x1E00}                                   # 4'00, 5'00, 4'00 (by data index)
    copies = (list(ORIGINALS) * 4)[:10]
    assert reverse_defaults(rs, copies) == [[stock[e.template] + 0xA0 * j for j in range(4)] for e in copies[3:]]
    bad = [replace(e, race=0x28F000) if i == 4 else e for i, e in enumerate(d)]
    with pytest.raises(PatchError, match="0x28f"):
        reverse_defaults(rs, bad)


def test_reverse_titles_fit_the_line(romset_zip):
    """L4, measured with `title_columns`' rule on the 62 columns: "<NAME> REVERSE RANKING" fits every planned name — the longest,
    DIABLO CANYON and PACIFIC COAST (13 letters), takes 60 columns from column 1; ALPINE (the shortest) 46 from column 8 — and
    any name up to 14 letters; a 15-letter name (the most the title font's name slot takes) gets "<NAME> REVERSE", RANKING
    dropped."""
    from vrtools.arcade.ranking import TITLE_COLS, reverse_title_columns
    from vrtools.arcade.tencourse import COURSES as PLANS
    names = [p.name for p in PLANS]
    assert max(map(len, names)) == 13 and min(map(len, names)) == 6
    for name in names + ["A" * 14]:
        n, c, r = reverse_title_columns(name)
        assert c == n + 2 * len(name) + 3 and r == c + 14 + 3 and n >= 0 and r + 14 <= TITLE_COLS, name
        assert abs((n + r + 14) / 2 - 31) <= 1, name
    assert reverse_title_columns("PACIFIC COAST") == reverse_title_columns("DIABLO CANYON") == (1, 30, 47)
    assert reverse_title_columns("ALPINE") == (8, 23, 40)
    n, c, r = reverse_title_columns("A" * 15)
    assert r is None and c == n + 33 and abs((n + c + 14) / 2 - 31) <= 1
    with pytest.raises(PatchError):
        reverse_title_columns("lowercase")


def test_the_image_holds_the_reverse_titles_and_first_defaults(romset_zip):
    """The titles by ranking id 0..16: ids 10..16 all `revtitle`; "REVERSE"; the seven first default times (`reverse_defaults`'
    first column: `revinit` steps 5 s from it); `revtitle`'s five arrays by reverse entry: the name string, the tiles of the name,
    REVERSE and the third word on the title row, the third word's string (RANKING, or the "" after REVERSE when it does not fit)."""
    from vrtools.arcade.ranking import (RANKING_STRING, TITLE_ROW, ranking_image, ranking_layout, reverse_defaults,
                                        reverse_title_columns)
    d = _planned()
    rs = _with_blobs(RomSet.from_zip(romset_zip), d)
    d[9] = replace(d[9], name="A" * 15)                                         # one name too long for RANKING
    base = CODE_FREE[0]
    lay = ranking_layout(base)
    img = ranking_image(rs, d, base)
    at = lambda a: a - base
    titles = struct.unpack_from("<17I", img, at(lay["titles"]))
    assert titles[10:] == (lay["revtitle"],) * 7 and lay["revtitle"] not in titles[:10]
    assert img[at(lay["revword"]):at(lay["revword"]) + 8] == b"REVERSE\0"
    assert list(struct.unpack_from("<7I", img, at(lay["firsts"]))) == [t[0] for t in reverse_defaults(rs, d)]
    args = [struct.unpack_from("<7I", img, at(lay["revargs"]) + 28 * f) for f in range(5)]
    for k, e in enumerate(d[3:]):
        n, c, r = reverse_title_columns(e.name)
        assert args[0][k] == lay["names"] + 16 * k and img[at(args[0][k]):at(args[0][k]) + len(e.name) + 1] == e.name.encode() + b"\0"
        assert (args[1][k], args[2][k]) == (TITLE_ROW + 2 * n, TITLE_ROW + 2 * c), e.name
        if r is None:
            assert args[3][k] == lay["revword"] + 7 and img[at(args[3][k])] == 0, e.name
        else:
            assert (args[3][k], args[4][k]) == (RANKING_STRING, TITLE_ROW + 2 * r), e.name


def test_revinit_revtag_and_revtitle_decode_as_intended(romset_zip):
    """MAME's disassembler on the image: `slot_init` ends by calling `revinit`; `revinit` saves R0-R4 and, for each of the seven
    reverse tables (base and slot from the setter's arrays at ids 10..16), stores the base in the slot and writes four entries:
    the rank 1..4, the time from its first default stepping 0xa0, +8 = 0, +0xc = -1, the time again, the name word from
    DEFAULT_NAMES + 4 stepping 8; then the tag. `revtag` compares the tag, calls `revinit` when it differs and loads the magic's
    length absolute (the instruction it replaces). `title` takes ids up to 16 through its table; `revtitle` prints the name and
    REVERSE in red and the third word in white, by the shown id, with the game's string printer."""
    from vrtools.arcade.ranking import (DEFAULT_NAMES, MAGIC_LENGTH, REVERSE_TAG, REVERSE_TAG_BYTES, STRING_PRINT, ranking_image,
                                        ranking_layout)
    rs = _with_blobs(RomSet.from_zip(romset_zip), _planned())
    base = CODE_FREE[0]
    lay = ranking_layout(base)
    img = ranking_image(rs, _planned(), base)
    text = lambda a, b: _text(listing_bytes(img[lay[a] - base:lay[b] - base], lay[a]))
    assert text("slot_init", "id_store")[-2:] == [f"jsr {lay['revinit']:X}", "rsr"]
    tag = struct.unpack("<I", REVERSE_TAG_BYTES)[0]
    init = listing_bytes(img[lay["revinit"] - base:lay["revtag"] - base], lay["revinit"])
    table, entry = init[2].addr, init[8].addr
    assert _text(init) == ["pushm #1F", "mov.w #0, R0", f"mov.w {lay['bases'] + 40:X}(R0), R1", f"mov.w {lay['slots'] + 40:X}(R0), R2",
                           "mov.w R1, [R2]", f"mov.w {lay['firsts']:X}(R0), R2", f"mov.w #{DEFAULT_NAMES + 4:X}, R3", "mov.w #1, R4",
                           "mov.w R4, [R1]", "mov.w R2, 4[R1]", "mov.w #0, 8[R1]", "mov.w #FFFFFFFF, C[R1]", "mov.w R2, 10[R1]",
                           "mov.w [R3], 14[R1]", "add.w #8, R3", "add.w #A0, R2", "add.w #18, R1", "add.w #1, R4", "cmp.w #5, R4",
                           f"bne {entry:X}", "add.w #1, R0", "cmp.w #7, R0", f"bne {table:X}", f"mov.w #{tag:X}, {REVERSE_TAG:X}",
                           "popm #1F", "rsr"]
    check = listing_bytes(img[lay["revtag"] - base:lay["revtitle"] - base], lay["revtag"])
    assert _text(check) == [f"cmp.w #{tag:X}, {REVERSE_TAG:X}", f"be {check[3].addr:X}", f"jsr {lay['revinit']:X}",
                            f"mov.w {MAGIC_LENGTH:X}, R0", "rsr"]
    title = text("title", "pagecmp")
    assert title[1] == "cmp.w #11, R0" and title[-3:] == [f"mov.w {lay['titles']:X}(R0), R0", "jsr [R0]", "rsr"]
    arg = lambda f: f"{lay['revargs'] + 28 * f - 40:X}(R0)"
    want = [f"movz.bw {SHOWN_ID:X}, R0"]
    for attr, tile, string in (("8300", arg(1), arg(0)), ("8300", arg(2), None), ("8200", arg(4), arg(3))):
        want += [f"movz.hw #{attr}, [-SP]", f"mov.w {tile}, [-SP]",
                 f"mov.w {string}, [-SP]" if string else f"movea.b {lay['revword']:X}, [-SP]", f"call {STRING_PRINT:X}, [SP]",
                 "add.w #C, SP"]
    assert text("revtitle", "title3") == want + ["rsr"]


def test_the_s_ram_check_calls_revtag_first(romset_zip):
    """TAG_SITE holds the recon's `mov.w FE6A47[PC], R0` (7 bytes, the magic's length, 18, for the compare loop; the boot's only
    call of the check is 0xfe69dc's `bsr`); installed it is `jsr revtag` and a nop, the compare loop after the magic's load the
    original's; a changed byte there is refused."""
    from vrtools.arcade.ranking import MAGIC_LENGTH, TAG_SITE, TAG_SITE_BYTES, ranking_layout
    rs = RomSet.from_zip(romset_zip)
    assert TAG_SITE == 0xFE69F0 and TAG_SITE_BYTES.hex() == "2d20f257000000" and MAGIC_LENGTH == 0xFE6A47
    assert rs.boot[TAG_SITE - V60_BOOT:TAG_SITE - V60_BOOT + 7] == TAG_SITE_BYTES
    assert _text(_span(rs, TAG_SITE, 7)) == ["mov.w FE6A47[PC], R0"]
    assert struct.unpack_from("<I", rs.boot, MAGIC_LENGTH - V60_BOOT)[0] == 18
    _, out, lay = _installed(romset_zip)
    assert _text(_span(out, TAG_SITE, 7)) == [f"jsr {ranking_layout(lay['ranking'])['revtag']:X}", "nop"]
    assert listing(out, TAG_SITE + 14, 4) == listing(rs, TAG_SITE + 14, 4)        # (TAG_SITE + 7: the magic's load, Phase 22r's)
    boot = bytearray(rs.boot)
    boot[TAG_SITE - V60_BOOT + 3] ^= 0x01
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match=f"{TAG_SITE:#x}"):
        install_directory(rs, (ORIGINALS * 4)[:10])


# --- Task 3 (MAME): a boot on a fresh battery RAM, on one saved by main's set, a second boot, the attract, the backup clear --------
# ranking_attract.lua (no input but the test mode's) on the session's seven-course set: write taps over BATTERY from the script's
# load (before the boot's S-RAM check), the modes, each ranking page's first entry shown, title row and rows; made once per session
# and in parallel by `boot_runs`. Main's battery RAM with a best time is `rank_runs`' main Metropolis race's (Task 2: a one-lap
# race_end.lua race on out/p26play6 to its name entry, the battery RAM MAME saved at its end).
from tests.test_ranking import _title_words                          # noqa: E402

ATTRACT_SECONDS = 1250      # every member of each attract group: measured, the last (Bay Bridge's ninth) at video frame 64 104 (1 115 s)
BOOT_SECONDS = 150          # a boot and the attract's first page
CLEAR_SECONDS = 60          # the test mode's backup clear (TEST_INPUT)
BLANK = "0020"              # an empty column of the page's layer (every page starts on a cleared layer: recon §3)
NORMAL_PAGE, SHORT_PAGE = 1584, 396                 # recon §3: four screens of 396 frames; one
TEST_INPUT = ";".join(["600:Service Mode:10"] + [f"{1000 + 100 * k}:VR1 (Red):10" for k in range(9)]       # the cursor from EXIT to
                      + ["2000:VR4 (Green):10", "2300:VR1 (Red):10", "2600:VR4 (Green):10"])              # BACKUP RAM CLEAR; NO, YES
CLEAR_FRAME = 2602          # the clear's frame end (YES chosen at 2600; measured: the stock initialiser's writes on 2603)


def test_ranking_attract_documents_its_switches():
    """ranking_attract.lua's switches are read from the environment and documented in its header (as race_end.lua's): the tap
    from the script's load, the page snapshots, the battery pokes, the buttons (the test mode). A poke is read back through the
    CPU's bus on its frame end (a K line, documented), so a test can confirm it landed."""
    text = (LUA_DIR / "ranking_attract.lua").read_text()
    for name in ("VR_RANK_LOG", "VR_RANK_TAP", "VR_RANK_SNAPS", "VR_RANK_POKE", "VR_RANK_INPUT"):
        assert f'os.getenv("{name}")' in text and f"\n--   {name} " in text, name
    assert 'out:write(string.format("W %d %x %x %x %x\\n", frame, cpu.state["PC"].value, offset, data, mask))' in text
    assert "\n--   K <frame> <address> <hexbytes>" in text
    assert 'out:write(string.format("K %d %x %s\\n", frame, p[2], table.concat(back)))' in text


@dataclass(frozen=True)
class BootRun:
    lines: list[tuple[int, int, int, int]]                  # M: (frame, mode, state, flag)
    pages: list[tuple[int, int, int, int, int]]             # P: (frame, shown id, data index, table, first entry shown)
    titles: list[tuple[int, list[int]]]                     # T: (frame, the title row's 62 words)
    rows: list[tuple[int, list[set[str]]]]                  # B: (frame, per row 1..6 its distinct words)
    writes: list[tuple[int, int, int, int, int]]            # W: (frame, pc, address, data, mask)
    before: bytes | None                                    # the battery RAM it booted on (None: fresh)
    battery: bytes                                          # MAME's saved battery RAM at its end
    pokes: tuple[tuple[int, int, str], ...] = ()            # K: (frame, address, the bytes read back after the poke, hex)


def _parse_attract(path, before, battery) -> BootRun:
    lines, pages, titles, rows, writes, pokes = [], [], [], [], [], []
    for row in open(path):
        tag, *f = row.split()
        if tag == "M":
            lines.append((int(f[0]), int(f[1], 16), int(f[2]), int(f[3], 16)))
        elif tag == "P":
            pages.append((int(f[0]), int(f[1]), int(f[2]), int(f[3], 16), int(f[4], 16)))
        elif tag == "T":
            titles.append((int(f[0]), [int(f[1][k:k + 4], 16) for k in range(0, len(f[1]), 4)]))
        elif tag == "B":
            rows.append((int(f[0]), [set(r.split(",")) for r in f[1].split("/")]))
        elif tag == "W":
            writes.append((int(f[0]),) + tuple(int(x, 16) for x in f[1:5]))
        elif tag == "K":
            pokes.append((int(f[0]), int(f[1], 16), f[2]))
    return BootRun(lines, pages, titles, rows, writes, before, battery, tuple(pokes))


def _attract(base: Path, rom: Path, label: str, seconds: int, before: bytes | None = None, env=None) -> BootRun:
    wd = base / label
    if before is not None:
        (wd / "nvram" / "vr").mkdir(parents=True)
        (wd / "nvram" / "vr" / "nvram").write_bytes(before)
    run_mame(LUA_DIR / "ranking_attract.lua", seconds, wd, rom, env={"VR_RANK_LOG": str(wd / "log.txt"),
             "VR_RANK_TAP": f"{BATTERY[0]:x}-{BATTERY[1]:x}", **(env or {})})
    return _parse_attract(wd / "log.txt", before, (wd / "nvram" / "vr" / "nvram").read_bytes())


class BootSession:
    """The session's boot runs, made in parallel at the first use: "fresh" (this set, no battery RAM, ATTRACT_SECONDS) then
    "fresh2" (its second boot); "main" (main's set, no battery RAM); "upgrade" (this set on main's battery RAM with a best time)
    then "upgrade2"; "mainboot" (main's set on that battery RAM); "clear" (this set, no battery RAM, a reverse table poked, the
    test mode's backup clear)."""

    def __init__(self, romset_zip, saturn_cue, base: Path, main_battery: bytes | None):
        out, conv = _seven(romset_zip, saturn_cue)
        self.rs, self.d = out, decode_directory(out)
        build = _build(base, romset_zip, out)
        poke = ";".join(f"300:{a:x}={b}" for a, b in self.poked().items())

        def chain(*steps):
            got = []
            for label, rom, seconds, env, prev in steps:
                got.append(_attract(base, rom, label, seconds, got[-1].battery if prev == "prev" else prev, env))
            return got

        jobs = {("fresh", "fresh2"): ((("fresh", build, ATTRACT_SECONDS, None, None), ("fresh2", build, BOOT_SECONDS, None, "prev"))),
                ("clear",): (("clear", build, CLEAR_SECONDS, {"VR_RANK_POKE": poke, "VR_RANK_INPUT": TEST_INPUT}, None),)}
        if (MAIN_SET / "vr.zip").is_file():
            jobs[("main",)] = (("main", MAIN_SET, BOOT_SECONDS, None, None),)
        if main_battery is not None:
            jobs[("upgrade", "upgrade2")] = (("upgrade", build, BOOT_SECONDS, None, main_battery),
                                             ("upgrade2", build, BOOT_SECONDS, None, "prev"))
            jobs[("mainboot",)] = (("mainboot", MAIN_SET, BOOT_SECONDS, None, main_battery),)
        with ThreadPoolExecutor(len(jobs)) as ex:
            futures = {k: ex.submit(chain, *steps) for k, steps in jobs.items()}
        self.runs: dict[str, BootRun | BaseException] = {}
        for labels, f in futures.items():
            for k, label in enumerate(labels):
                self.runs[label] = f.exception() or f.result()[k]

    @staticmethod
    def poked() -> dict[int, str]:
        """The clear run's pokes at frame 300 (hex bytes by address): entry 6's reverse table's first entry (rank 9, time 0x123, a
        name) and its slot pointed at its second entry, the tag kept; Metropolis's normal table's first time."""
        t, s = REVERSE_TABLES[3], REVERSE_SLOTS + 4 * 3
        return {t: ENTRY.pack(9, 0x123, 0, -1, 0x123, b"ZZZ\0").hex(), s: struct.pack("<I", t + 24).hex(),
                NEW_TABLES[3] + 4: struct.pack("<I", 0x321).hex()}

    def run(self, label: str) -> BootRun:
        if label not in self.runs:
            pytest.skip(f"main's set is not at {MAIN_SET}")
        r = self.runs[label]
        if isinstance(r, BaseException):
            raise r
        return r


_BOOT: dict[str, BootSession] = {}


@pytest.fixture
def boot_runs(romset_zip, saturn_cue, tmp_path_factory, rank_runs) -> BootSession:
    key = str(romset_zip)
    if key not in _BOOT:
        main = rank_runs.runs.get(("main", METROPOLIS))
        battery = main.battery if isinstance(main, RankRun) else None
        _BOOT[key] = BootSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("boot"), battery)
    return _BOOT[key]


NORMAL_BLOCK = (set().union(*(range(t, t + TABLE_BYTES) for t in ORIG_TABLES + NEW_TABLES), *(range(a, a + 4) for a in ORIG_SLOTS),
                            range(NEW_SLOTS, NEW_SLOTS + 40), range(0x40E6D0, 0x40E6D0 + 18)) | {RANKING_INDEX})   # + the S-RAM magic
REVERSE_BLOCK = set().union(*(range(t, t + 24 * SHORT_ENTRIES) for t in REVERSE_TABLES), range(REVERSE_SLOTS, REVERSE_SLOTS + 28),
                            range(0x40FDAC, 0x40FDB0))                                                  # tables, slots, the tag
GAME_RECORD = set(range(0x40F000, 0x40F00C))   # the game's record (0x40f000..0x40f00b, recon §5), written at every boot (0xfe05ae..)
PAGE_OWN = {SHOWN_ID} | set(range(ATTRACT_COUNTERS, ATTRACT_COUNTERS + 3))   # what an attract page rewrites (its setter call, `common`,
                                                                             # the shown id; `attract`, its group's counter)


def _at(battery: bytes, addresses) -> bytes:
    return bytes(battery[a - 0x400000] for a in sorted(addresses))


def _reverse_block(boot_runs) -> dict[int, int]:
    """The reverse block as `revinit` makes it, by byte address: the seven tables' entries (rank 1..4, `reverse_defaults` of the
    built set, +8 = 0, +0xc = -1, the time again, the game's first four default names YU., RNS, TKG, NAG), the slots, the tag."""
    from vrtools.arcade.ranking import REVERSE_TAG, REVERSE_TAG_BYTES, reverse_defaults
    names = [boot_runs.rs.boot[0xFC4DC4 - V60_BOOT + 8 * j:0xFC4DC8 - V60_BOOT + 8 * j] for j in range(SHORT_ENTRIES)]
    blob = {}
    for k, (table, times) in enumerate(zip(REVERSE_TABLES, reverse_defaults(boot_runs.rs, boot_runs.d))):
        data = b"".join(ENTRY.pack(j + 1, t, 0, -1, t, names[j]) for j, t in enumerate(times))
        blob.update({table + i: x for i, x in enumerate(data)})
        blob.update({REVERSE_SLOTS + 4 * k + i: x for i, x in enumerate(struct.pack("<I", table))})
    blob.update({REVERSE_TAG + i: x for i, x in enumerate(REVERSE_TAG_BYTES)})
    return blob


def _revinit_pcs(boot_runs) -> range:
    from vrtools.arcade.ranking import ranking_layout
    rl = ranking_layout(directory_layout()["ranking"])
    return range(rl["revinit"], rl["revtag"])


def test_a_fresh_battery_ram_gets_the_reverse_block(boot_runs):
    """A boot on a fresh battery RAM: the seven reverse tables of four entries — ranks 1..4 (the insert never writes them: they
    are the initialiser's), the default times of `reverse_defaults` (the session lead's ruling of 15 Nov: each course's normal
    table's first four, as the game's own initialiser writes them in this boot, checked directly; on the seven-course set:
    Alpine and Diablo Canyon 5'00, the other five 4'00), +8 = 0, +0xc = -1, the first four default names — the seven slots
    holding their table and the tag, written only by `revinit`, all on the boot's S-RAM check's frame (twice: from `revtag`, the
    tag missing, then from `slot_init` inside the stock initialiser, the magic missing). The ten normal tables, their slots, the
    magic and the ranking id end as main's set leaves them on a fresh battery RAM."""
    run, main = boot_runs.run("fresh"), boot_runs.run("main")
    want = _reverse_block(boot_runs)
    assert {a: run.battery[a - 0x400000] for a in want} == want
    times = [struct.unpack_from("<I", run.battery, t - 0x400000 + 4)[0] for t in REVERSE_TABLES]
    print("REVERSE DEFAULTS", [f"{t // 1920}'{t % 1920 // 32:02d}" for t in times])
    first4 = lambda t: [ENTRY.unpack_from(run.battery, t - 0x400000 + 24 * j)[1] for j in range(SHORT_ENTRIES)]
    assert [first4(t) for t in REVERSE_TABLES] == [first4(t) for t in NEW_TABLES]    # the game-made normal table's entries 0..3
    assert [[ENTRY.unpack_from(run.battery, t - 0x400000 + 24 * j)[0] for j in range(4)] for t in REVERSE_TABLES] == [[1, 2, 3, 4]] * 7
    pcs = _revinit_pcs(boot_runs)
    ours = [(f, pc, a, v) for f, pc, a, v in _bytes(run.writes) if a in REVERSE_BLOCK]
    assert {a for _, _, a, _ in ours} == REVERSE_BLOCK, sorted(map(hex, REVERSE_BLOCK - {a for _, _, a, _ in ours}))[:10]
    assert all(pc in pcs for _, pc, _, _ in ours), sorted({hex(pc) for _, pc, _, _ in ours})
    frames = {f for f, _, _, _ in ours}
    assert len(frames) == 1 and len(ours) == 2 * len(REVERSE_BLOCK), (frames, len(ours))
    stock = [f for f, pc, _, _ in _bytes(run.writes) if 0xFC3B49 <= pc < 0xFC3C1B]           # the stock initialiser's own writes
    assert stock and set(stock) == frames
    assert _at(run.battery, NORMAL_BLOCK) == _at(main.battery, NORMAL_BLOCK)
    assert run.battery[0x40E6D0 - 0x400000:0x40E6D0 - 0x400000 + 18] == b"S-RAM CHECK OK 10\0"


def test_a_battery_ram_saved_by_main_keeps_every_time(boot_runs, rank_runs):
    """The upgrade (design §5 proof 6): main's set (out/p26play6) after a one-lap normal Metropolis race to its name entry
    (rank_runs' main run) saved a battery RAM with that best time first in Metropolis's table, the magic and no reverse block
    (0xff). This set boots on it: every byte of the ten normal tables, their slots, the magic and the ranking id is the same
    after the boot and its attract as before, and none of them is written; the shown id and the attract groups' counters are
    written only by the attract pages (PAGE_OWN: the setter's `common` and `attract`); the reverse block is made once, by
    `revtag`'s call of `revinit` on the boot's S-RAM check's frame, the stock initialiser not running (the magic is there).
    Besides, the battery writes are those of main's set booting the same battery RAM (rank_runs' battery, "mainboot"), write for
    write, up to the first attract page that shows a reverse table (the reverse block's and the cells' writes aside)."""
    before, run = rank_runs.run("main", METROPOLIS).battery, boot_runs.run("upgrade")
    assert run.before == before
    table = NEW_TABLES[METROPOLIS - 3]
    kept = ENTRY.unpack_from(before, table - 0x400000)
    assert kept[0] == 1 and kept[1] < 0x1E00 and kept[5] == b"   \0", kept           # the race's time (59 s), first
    assert set(_at(before, REVERSE_BLOCK)) == {0xFF} and before[0x40E6D0 - 0x400000:0x40E6D0 - 0x400000 + 18] == b"S-RAM CHECK OK 10\0"
    assert _at(run.battery, NORMAL_BLOCK) == _at(before, NORMAL_BLOCK) and ENTRY.unpack_from(run.battery, table - 0x400000) == kept
    written = _bytes(run.writes)
    assert not {a for _, _, a, _ in written} & NORMAL_BLOCK
    want = _reverse_block(boot_runs)
    assert {a: run.battery[a - 0x400000] for a in want} == want
    ours = [(f, pc) for f, pc, a, _ in written if a in REVERSE_BLOCK]
    assert len(ours) == len(REVERSE_BLOCK) and len({f for f, _ in ours}) == 1 and all(pc in _revinit_pcs(boot_runs) for _, pc in ours)
    assert not any(0xFC3B49 <= pc < 0xFC3C1B for _, pc, _, _ in written)              # the stock initialiser did not run
    from vrtools.arcade.ranking import ranking_layout
    rl = ranking_layout(directory_layout()["ranking"])
    own = [(pc, a) for _, pc, a, _ in written if a in PAGE_OWN]
    in_page = lambda pc, a: rl["common"] <= pc < rl["slot_init"] if a == SHOWN_ID else rl["attract"] <= pc < rl["title"]
    assert own and all(in_page(pc, a) for pc, a in own), own
    for a in PAGE_OWN:                                                                 # the page's rewrites stand at the end
        last = [v for _, _, b, v in written if b == a]
        assert run.battery[a - 0x400000] == (last[-1] if last else before[a - 0x400000]), hex(a)
    others = {a for _, _, a, _ in written} - REVERSE_BLOCK - CELLS - PAGE_OWN - set(BOOKKEEPING) - GAME_RECORD
    assert not others, sorted(map(hex, others))
    main = boot_runs.run("mainboot")
    reverse_page = next(f for f, _, a, v in written if a == SHOWN_ID and v >= 10)     # its setter call (mode 0x03 state 2)
    key = lambda w: (w[0], _boot_pc(w[1]), w[2], w[3], w[4])
    mine = [key(w) for w in run.writes if w[0] < reverse_page and not (w[2] in REVERSE_BLOCK or LAST_OFFSET_CELL <= w[2] <= ROWS_CELL)]
    assert mine == [key(w) for w in main.writes if w[0] < reverse_page]


@pytest.mark.parametrize("label", ["fresh2", "upgrade2"])
def test_a_second_boot_writes_no_table(boot_runs, label):
    """A second boot of this set on the battery RAM the first left (fresh, and after the upgrade): the tag is there, `revtag` does
    not call `revinit`, the magic is there, the stock initialiser does not run: no write to a normal or a reverse table, a slot,
    the tag, the magic or the ranking id; those bytes end as they began. Its battery writes are the boot's game record, the
    bookkeeping and the attract pages' (PAGE_OWN and the cells)."""
    run = boot_runs.run(label)
    written = {a for _, _, a, _ in _bytes(run.writes)}
    assert not written & (NORMAL_BLOCK | REVERSE_BLOCK), sorted(map(hex, written & (NORMAL_BLOCK | REVERSE_BLOCK)))[:10]
    assert written <= CELLS | PAGE_OWN | set(BOOKKEEPING) | GAME_RECORD, sorted(map(hex, written - CELLS - PAGE_OWN - set(BOOKKEEPING)))
    assert _at(run.battery, NORMAL_BLOCK | REVERSE_BLOCK) == _at(run.before, NORMAL_BLOCK | REVERSE_BLOCK)


def _spans(run: BootRun) -> list[dict]:
    """The attract's ranking pages: each mode 0x03 state 3 span (start, end), its P lines' shown id, data index, table and first
    entries shown, its title rows and its rows (T and B lines)."""
    out, cur = [], None
    for f, mode, state, _ in run.lines:
        if (mode, state) == (3, 3):
            cur = {"start": f}
        elif cur is not None:
            cur["end"] = f
            out.append(cur)
            cur = None
    for p in out:
        lines = [x for x in run.pages if p["start"] <= x[0] < p["end"]]
        p["id"], p["di"], p["table"] = lines[0][1:4]
        assert all(x[1:4] == lines[0][1:4] for x in lines), lines
        p["firsts"] = [x[4] for x in lines]
        p["titles"] = [w for f, w in run.titles if p["start"] <= f < p["end"]]
        p["rows"] = [r for f, r in run.rows if p["start"] <= f < p["end"]]
    return out


def test_the_attract_shows_every_member_of_each_group(boot_runs):
    """The attract after a fresh boot (design §5 proof 5), ATTRACT_SECONDS: every member of each group comes, in its group's order,
    one member a page of its data index; each page shows its id's table. A normal page: four screens of six rows (first entries
    0, 6, 12, 18), NORMAL_PAGE frames, its course's title as the game and Phase 23b print it. A reverse page: one screen (first
    entry 0, then 6 past the end), SHORT_PAGE frames, rows 1..4 drawn and rows 5 and 6 empty (BLANK) on every frame, the title
    "<NAME> REVERSE RANKING": the name and REVERSE in red (0x8300), RANKING in white (0x8200), at `reverse_title_columns`. The
    direction flag is 0 on every frame."""
    from vrtools.arcade.ranking import attract_groups, reverse_title_columns, title_columns
    run, rs, d = boot_runs.run("fresh"), boot_runs.rs, boot_runs.d
    assert {flag for _, _, _, flag in run.lines} == {0}
    groups = attract_groups(d)
    bases = list(ORIG_TABLES + NEW_TABLES + REVERSE_TABLES)
    pages = _spans(run)
    print("PAGES", [(p["start"], p["id"], p["end"] - p["start"]) for p in pages])
    for k, g in enumerate(groups):
        shown = [p["id"] for p in pages if p["di"] == k]
        assert set(shown) == set(g), (k, shown, g)
        start = g.index(shown[0])
        assert shown == [g[(start + j) % len(g)] for j in range(len(shown))], (k, shown)
    original = {0: ("MEDIUM", 9), 1: ("EXPERT", 9), 2: ("BEGINNER", 8)}
    for p in pages:
        ident = p["id"]
        assert p["table"] == bases[ident], (p["start"], ident)
        if ident < 10:
            assert p["firsts"] == [0, 6, 12, 18, 24] and p["end"] - p["start"] == NORMAL_PAGE, (p["start"], ident, p["firsts"])
            assert all(r[j] - {BLANK} for j in range(6) for r in p["rows"][-1:]), p["start"]      # six rows a screen
            text, col = original[ident] if ident < 3 else (d[ident].name, title_columns(d[ident].name)[0])
            want = _title_words(rs, text, col, 0x8300)
        else:
            assert p["firsts"] == [0, 6] and p["end"] - p["start"] == SHORT_PAGE, (p["start"], ident, p["firsts"])
            assert p["rows"] and all(r[4] == r[5] == {BLANK} for r in p["rows"]), p["start"]
            assert all(r[j] - {BLANK} for j in range(4) for r in p["rows"][-1:]), p["start"]      # (drawn over two frames)
            name = d[ident - 7].name
            n, c, r = reverse_title_columns(name)
            want = _title_words(rs, name, n, 0x8300) + _title_words(rs, "REVERSE", c, 0x8300) + _title_words(rs, "RANKING", r, 0x8200)
        assert p["titles"] and all(t[col] == w for t in p["titles"][-1:] for col, w in want), (p["start"], ident)


def test_the_backup_clear_resets_the_reverse_tables(boot_runs):
    """The test mode's BACKUP RAM CLEAR (design §5 proof 7), driven headless: Service Mode, Red nine times (EXIT to BACKUP RAM
    CLEAR), Green, Red (NO to YES), Green. Before it a reverse table, its slot and a normal table were poked (`poked`); on the
    clear's frame the stock initialiser (0xfc3b49, from 0xfc76eb) rewrites the ten normal tables and `slot_init` calls `revinit`:
    the whole reverse block is written again and ends as a fresh battery RAM's, the poked normal time back to its default. The
    pokes landed: read back through the CPU's bus on frame 300 they are the poked bytes, and nothing writes those bytes again
    before the clear."""
    run, fresh = boot_runs.run("clear"), boot_runs.run("fresh")
    assert run.before is None
    assert {a: h for f, a, h in run.pokes if f == 300} == BootSession.poked(), run.pokes
    later = [(f, pc, a) for f, pc, a, _ in _bytes(run.writes) if f > 300]
    clear = [f for f, pc, _ in later if 0xFC3B49 <= pc < 0xFC3C1B]
    assert clear and min(clear) > CLEAR_FRAME - 10, clear[:3]
    poked = {a + i for a, h in BootSession.poked().items() for i in range(len(h) // 2)}
    assert not [(f, hex(a)) for f, _, a in later if f < min(clear) and a in poked]
    rev = [(f, pc) for f, pc, a in later if a in REVERSE_BLOCK]
    assert {a for f, _, a in later if a in REVERSE_BLOCK} == REVERSE_BLOCK and all(pc in _revinit_pcs(boot_runs) for _, pc in rev)
    assert min(f for f, _ in rev) >= min(clear)
    want = _reverse_block(boot_runs)
    assert {a: run.battery[a - 0x400000] for a in want} == want
    assert _at(run.battery, NORMAL_BLOCK - {RANKING_INDEX}) == _at(fresh.battery, NORMAL_BLOCK - {RANKING_INDEX})


# --- Task 4: ranks two to four, a slow time, ties, both directions on one course ---------------------------------------------
# One-lap races (race_end.lua, the autopilot) on the session's seven-course set, made once per session by `place_runs`, four at a
# time. An autopilot race can finish on another frame, so with another time, when the boot before it differs (Task 3 fix round A:
# the harness's frame phase, not the ROM), so no time is hard-coded: race_end.lua's VR_END_PRESET writes the raced course's table
# at the race's results (mode 0x16, the time final; the insert ran three frames later in every run here), entry k = rank k + 1,
# the race's own time [0x501168] + the deltas' k-th, view 0, -1, the name 'A' + k three times. Each test reads the time the run
# logged (its T line) and the table read back (its P line), so every preset is tied to the time measured in the same run.
STEP = 32                   # one second (1/32 s): the presets' spacing round the race's time
PLACES = {                  # label: (direction, entry, the deltas from the race's time of the table's entries 0..n-1)
    "second": ("reverse", METROPOLIS, (-STEP, STEP, 2 * STEP, 3 * STEP)),
    "third": ("reverse", AMAZON_FALLS, (-2 * STEP, -STEP, STEP, 2 * STEP)),
    "fourth": ("reverse", METROPOLIS, (-3 * STEP, -2 * STEP, -STEP, STEP)),
    "slow": ("reverse", AMAZON_FALLS, (-4 * STEP, -3 * STEP, -2 * STEP, -STEP)),
    "tie": ("reverse", METROPOLIS, (-3 * STEP, -2 * STEP, -STEP, 0)),                     # the fourth's time = the race's
    "tie2": ("reverse", AMAZON_FALLS, (-2 * STEP, -STEP, 0, 0)),                          # the third's and the fourth's
    "normaltie": ("normal", METROPOLIS, tuple(STEP * (k - 23) for k in range(TABLE_BYTES // 24))),     # a normal table: the 24th's
    "normaltie2": ("normal", AMAZON_FALLS, tuple(STEP * (k - 22) for k in range(23)) + (0,)),       # the 23rd's and the 24th's
}
NAME_SNAP = 300             # race_end.lua's VR_END_SNAP: frames into the name entry ("Your Ranking is ...", the rank shown)
BLANK_NAME = b"   \0"       # the name entry's buffer when no letter is entered (the autoplay enters none: the timer runs out)


def test_race_end_presets_a_table_round_the_race_s_time():
    """Task 4's harness switches (race_end.lua's header documents each): VR_END_PRESET writes the table at the race's results
    (mode 0x16) through the nvram share, so no W line, from the time it reads there, then reads it back through the bus (a P
    line); every race's time is logged there (a T line); VR_END_SNAP takes a snapshot that many frames into the name entry."""
    text = (LUA_DIR / "race_end.lua").read_text()
    for name in ("VR_END_PRESET", "VR_END_SNAP"):
        assert f'os.getenv("{name}")' in text and f"\n--   {name} " in text, name
    for line in ("T <frame> <time>", "P <frame> <table> <hexbytes>", "S <frame>"):
        assert f"\n--   {line} " in text, line
    assert "if not racing and races > results and mode == 0x16 then" in text
    assert "local time = mem:read_i32(0x501168)" in text and 'out:write(string.format("T %d %d\\n", frame, time))' in text
    assert "local words = {k, time + d, 0, -1, time + d, letter | letter << 8 | letter << 16}" in text
    assert "nvram:write_u8(base + 24 * (k - 1) + 4 * (w - 1) + j, (v >> 8 * j) & 0xFF)" in text
    assert 'out:write(string.format("P %d %x %s\\n", frame, p[1], table.concat(back)))' in text
    assert "manager.machine.video:snapshot()" in text


def _preset_blob(time: int, deltas) -> bytes:
    """The bytes VR_END_PRESET writes round `time`."""
    return b"".join(ENTRY.pack(k + 1, time + d, 0, -1, time + d, bytes([0x41 + k] * 3) + b"\0") for k, d in enumerate(deltas))


def _own(direction: str, entry: int, n: int) -> tuple[int, int, set[int]]:
    """The raced course's table, its slot word and their bytes: the reverse table (4 entries) or the normal one (24)."""
    if direction == "reverse":
        table, slot = REVERSE_TABLES[entry - 3], REVERSE_SLOTS + 4 * (entry - 3)
    else:
        table, slot = NEW_TABLES[entry - 3], NEW_SLOTS + 4 * entry
    return table, slot, set(range(table, table + 24 * n)) | set(range(slot, slot + 4))


class PlaceSession:
    """The session's PLACES runs, made at the first use four at a time; a run that failed raises its error when asked for."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        out, conv = _seven(romset_zip, saturn_cue)
        build = _build(base, romset_zip, out)
        with ThreadPoolExecutor(4) as ex:
            futures = {label: ex.submit(_make, base, build, conv, direction, entry, label,
                                        {"VR_END_PRESET": f"{_own(direction, entry, len(d))[0]:x}:{','.join(map(str, d))}",
                                         "VR_END_SNAP": str(NAME_SNAP)}, False)
                       for label, (direction, entry, d) in PLACES.items()}
        self.runs = {label: f.exception() or f.result() for label, f in futures.items()}

    def run(self, label: str) -> RankRun:
        r = self.runs[label]
        if isinstance(r, BaseException):
            raise r
        return r


_PLACE: dict[str, PlaceSession] = {}


@pytest.fixture
def place_runs(romset_zip, saturn_cue, tmp_path_factory) -> PlaceSession:
    key = str(romset_zip)
    if key not in _PLACE:
        _PLACE[key] = PlaceSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("place"))
    return _PLACE[key]


def _preset_round_the_time(run: RankRun, label: str) -> tuple[int, int]:
    """The run's time and its insert's frame, once its preset is confirmed: one T line, on the frame end the mode first reads
    0x16 after the race; the P line on that frame end holds `_preset_blob` of that time, read back through the bus; the insert
    (the qualify test's read of the last-entry offset cell) runs later, on the frame end the mode first reads 0x1b or the next
    (measured: the same frame end on Metropolis and Amazon Falls reverse, the next on Amazon Falls normal: the game's step and
    the video frame's end fall either way)."""
    direction, entry, deltas = PLACES[label]
    lines = _race(run, 0)
    (tf, time), = run.times
    results = next(l.frame for l in lines if l.mode == 0x16)
    insert = next(f for f, pc, *_ in run.reads if pc == INSERT_SITES[0])
    assert tf == results < insert and insert - next(l.frame for l in lines if l.mode == 0x1B) in (0, 1), (tf, results, insert)
    assert run.presets == ((tf, _own(direction, entry, len(deltas))[0], _preset_blob(time, deltas)),), run.presets
    race = _driving(lines)
    assert race and all(l.flag == (direction == "reverse") for l in race), race[:3]
    print("PLACE", label, "time", time, f"({time / 32:.2f} s)", "results", tf, "insert", insert)
    return time, insert


def _assert_placed(run: RankRun, label: str, place: int):
    """The race's time recorded in place `place` (1-based) of its course's own table, as the listing's insert and bubble leave it
    (recon §1): the rank fields stay 1..n by position (+0 is never written); above the place the preset entries as they were;
    in the place the race's time at +4 and +0x10, a view 0..3 and the name entry's blank name; below it the preset entries from
    the place on, each moved down one with its fields; the preset's last entry gone. Only +4..+0x17 of the entries from the place
    to the last and the slot word are written, all on the insert's frame but the name (+0x14 of the new entry, by the name
    entry); every other battery write is a cell, the bookkeeping or MAIN_OUTSIDE's, no other table or slot. Both insert sites
    read the last-entry offset (0x48 short, 0x228 normal). The record flag is set, the modes are a record's, and the slot holds
    the new entry, whose rank field (what the name entry prints) is `place`; the name entry's snapshot was taken."""
    direction, entry, deltas = PLACES[label]
    n = len(deltas)
    table, slot, ours = _own(direction, entry, n)
    time, insert = _preset_round_the_time(run, label)
    lines = _race(run, 0)
    assert any(l.record & 1 for l in lines) and _after_finish(lines) == RECORD, [hex(m) for m in _after_finish(lines)]
    writes = _bytes(run.writes)
    written = {a for _, _, a, _ in writes}
    allowed = ours | CELLS | set(BOOKKEEPING) | MAIN_OUTSIDE
    assert written <= allowed, sorted(map(hex, written - allowed))[:10]
    assert not written & (TABLES | REVERSE_BLOCK) - ours, sorted(map(hex, written & (TABLES | REVERSE_BLOCK) - ours))[:10]
    new = table + 24 * (place - 1)
    fields = {table + 24 * k + o for k in range(place - 1, n) for o in range(4, 24)}
    expect = fields | set(range(slot, slot + 4))
    assert written & ours == expect, sorted(map(hex, (written & ours) ^ expect))[:10]
    name = set(range(new + 0x14, new + 0x18))
    assert {f for f, _, a, _ in writes if a in ours and a not in name} == {insert}
    halves = ((LAST_OFFSET_CELL, LAST_OFFSET if direction == "normal" else SHORT_LAST_OFFSET), (LAST_OFFSET_CELL + 2, 0))
    reads = [(f, pc, a, d & m) for f, pc, a, d, m in run.reads if pc in INSERT_SITES]
    assert reads == [(insert, site, a, v) for site in INSERT_SITES for a, v in halves], reads
    entries = [ENTRY.unpack_from(run.battery, table - 0x400000 + 24 * k) for k in range(n)]
    old = [ENTRY.unpack_from(_preset_blob(time, deltas), 24 * k) for k in range(n)]
    assert [e[0] for e in entries] == list(range(1, n + 1))
    assert [e[1:] for e in entries[:place - 1]] == [e[1:] for e in old[:place - 1]]
    assert [e[1:] for e in entries[place:]] == [e[1:] for e in old[place - 1:n - 1]]
    rank, t, view, _, t2, nm = entries[place - 1]
    assert (rank, t, t2, nm) == (place, time, time, BLANK_NAME) and view in range(4), entries[place - 1]
    assert struct.unpack_from("<I", run.battery, slot - 0x400000)[0] == new
    assert len(run.snaps) == 1 and run.snaps[0] > insert, run.snaps


@pytest.mark.parametrize("label,place", [("second", 2), ("third", 3), ("fourth", 4)])
def test_a_reverse_time_lands_in_its_place(place_runs, label, place):
    """A one-lap reverse race on a table preset round its own time (PLACES: entries 1 s apart, `place` - 1 of them faster):
    the time lands in `place` (2nd on Metropolis, 3rd on Amazon Falls, 4th on Metropolis), the entries below it shifted, the old
    fourth gone, the name entry's slot on the new entry (`_assert_placed`). The snapshot 300 frames into the name entry reads
    "Your Ranking is 2nd" (3rd, 4th): out/p27/task4/snaps/ (copied from this run's snap/vr/0000.png)."""
    _assert_placed(place_runs.run(label), label, place)


def test_a_reverse_time_slower_than_the_fourth_records_nothing(place_runs):
    """A one-lap reverse race on Amazon Falls, its table preset all four faster than its time (1..4 s): the modes after the finish
    are today's no-record sequence (NO_RECORD: no name entry), the record flag never set, no write to any table or slot (every
    battery write a cell, the bookkeeping or MAIN_OUTSIDE's); the table and slot end as the preset left them; only the qualify
    test's site read the last-entry offset (0x48: the last entry is faster, so the bubble never ran)."""
    run = place_runs.run("slow")
    direction, entry, deltas = PLACES["slow"]
    table, slot, _ = _own(direction, entry, len(deltas))
    time, insert = _preset_round_the_time(run, "slow")
    lines = _race(run, 0)
    assert _after_finish(lines) == NO_RECORD and not any(l.record & 1 for l in run.lines), [hex(m) for m in _after_finish(lines)]
    written = {a for _, _, a, _ in _bytes(run.writes)}
    allowed = CELLS | set(BOOKKEEPING) | MAIN_OUTSIDE
    assert written <= allowed, sorted(map(hex, written - allowed))[:10]
    assert run.battery[table - 0x400000:table - 0x400000 + 24 * len(deltas)] == _preset_blob(time, deltas)
    assert struct.unpack_from("<I", run.battery, slot - 0x400000)[0] == table              # `revinit`'s
    reads = [(f, pc, a, d & m) for f, pc, a, d, m in run.reads if pc in INSERT_SITES]
    halves = ((LAST_OFFSET_CELL, SHORT_LAST_OFFSET), (LAST_OFFSET_CELL + 2, 0))
    assert reads == [(insert, INSERT_SITES[0], a, v) for a, v in halves], reads
    assert not run.snaps


@pytest.mark.parametrize("label,place", [("tie", 4), ("tie2", 3), ("normaltie", 24), ("normaltie2", 23)])
def test_a_tie_with_the_last_entry_records_above_the_equal_times(place_runs, label, place):
    """A time equal to the last entry's records (the qualify test's `blt` branches only on a last entry faster than the new time)
    and the bubble moves it up past every equal time (its `blt` stops only on an entry faster): measured, on a reverse table
    with the fourth's time equal (the new entry 4th, the old fourth gone) and with the third's and fourth's equal (the new entry
    3rd, the old third 4th, the old fourth gone); the same on a NORMAL 24-entry table of a normal race, whose 24th (and 23rd)
    entries hold the race's time: 24th (23rd). The short tables do on a tie what the normal ones do (`_assert_placed`)."""
    _assert_placed(place_runs.run(label), label, place)


@pytest.mark.parametrize("kind,entry", [("reverse,normal", METROPOLIS), ("normal,reverse", AMAZON_FALLS)])
def test_both_directions_on_one_course_keep_their_own_times(rank_runs, kind, entry):
    """The two-game sessions of `rank_runs` (Task 2: a reverse then a normal race on Metropolis, a normal then a reverse one on
    Amazon Falls, the reverse table preset slower than any one-lap race, the normal one the game's defaults): each race's time
    (its T line) differs from the other's; the normal table holds the normal race's time in entry 0 (+4 and +0x10) and the
    reverse one's nowhere, the reverse table the reverse race's in entry 0 and the normal one's nowhere; each slot holds its
    table's entry 0; in the normal game no reverse table, slot or tag is written, in the reverse game no normal table or slot."""
    run = rank_runs.run(kind, entry)
    assert len(run.times) == 2 and [f for f, _ in run.times] == sorted(f for f, _ in run.times), run.times
    times = {d: t for d, (_, t) in zip(run.races, run.times)}
    print("BOTH ORDERS", kind, entry, times)
    assert times["normal"] != times["reverse"]
    for direction, other in (("normal", "reverse"), ("reverse", "normal")):
        n = SHORT_ENTRIES if direction == "reverse" else TABLE_BYTES // 24
        table, slot, ours = _own(direction, entry, n)
        entries = [ENTRY.unpack_from(run.battery, table - 0x400000 + 24 * k) for k in range(n)]
        assert entries[0][1] == entries[0][4] == times[direction], (direction, entries[0])
        assert not [e for e in entries if times[other] in (e[1], e[4])], (direction, times[other])
        assert struct.unpack_from("<I", run.battery, slot - 0x400000)[0] == table
        k = run.races.index(direction)
        game = {a for f, _, a, _ in _bytes(run.writes) if f in _window(run, k)}
        foreign = REVERSE_BLOCK if direction == "normal" else TABLES
        assert game & ours and not game & foreign, (direction, sorted(map(hex, game & foreign))[:10])
