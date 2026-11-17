"""Phase 35: a best-time table for reverse races on all ten courses, four entries each.

Pascal, 16 Nov 2026, to the recon's five questions with their recommendations: "yes to all" (four per table on all ten; an
original's reverse page titled with its level word; straight after its own page in the attract; the seven's rule for the starting
times; in the same release as the originals in reverse). 17 Nov, asked whether to release without them: "Release with the
original best time". Recon and gate: docs/spike/2026-11-phase35-reverse-times-recon.md; findings:
docs/spike/2026-11-phase35-reverse-times-findings.md.

What is tested here (the seven's own tables and the shared routines: tests/test_reverse_ranking.py):
- static: where the three tables, their slots and their tag lie (the battery RAM the recon's gate found untouched), that they
  share no byte with anything of v0.2.1's layout (frozen below), the ranking ids and the attract groups;
- boots, on SYNTHETIC battery RAM built here (never a dump): a fresh one, one as v0.2.1 saves it (every table with its own
  times and names), one as v0.2 saves it, a second boot, the test mode's backup clear;
- games (one-lap races, the clock held: race_end.lua): a reverse race on each original records in its own table and asks a name,
  its page comes first in the attract; a time landing third; a slow time recording nothing; a reverse race on one of the seven
  and a backup clear after it; a normal race on each of the ten courses against main's set on the same inputs, pass for pass
  and battery write for battery write: a RELEASE RECORD, opt-in (`VR_P35_MAIN_SET`, below; skipped, with the reason, without it);
- the attract with no game against main's: the same pages in each group's order but for the three new ones."""
import os
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.directory import decode_directory, directory_layout
from vrtools.arcade.ranking import (ATTRACT_COUNTERS, NEW_SLOTS, NEW_TABLES, ORIG_SLOTS, ORIG_TABLES, RANKING_INDEX, REVERSE_SLOTS,
                                    REVERSE_TABLES, SHORT_ENTRIES, SHOWN_ID, TABLE_BYTES)
from vrtools.arcade.romset import V60_BOOT
from tests.test_dirscreen_build import NO_RECORD, RECORD
from tests.test_reverse_ranking import (BATTERY, BOOKKEEPING, CELLS, ENTRY, GAME_RECORD, MAIN_OUTSIDE, NORMAL_BLOCK, ORIG_BLOCK,
                                        PAGE_OWN, REVERSE_BLOCK, SHORT_PAGE, TEST_INPUT, BootRun, RankRun, _after_finish,
                                        _assert_page, _at, _attract, _boot_pc, _bytes, _driving, _parse_attract, _parse_rank,
                                        _race, _spans)

# ---- the layout (frozen: a saved battery RAM is read by these addresses for as long as the release lives) ----
B = 0x400000
ORIG_REVERSE_TABLES = (0x40E6E4, 0x40E744, 0x40F010)        # by ranking id: Bay Bridge, Acropolis, Big Forest
ORIG_REVERSE_SLOTS = (0x40FC40, 0x40FC44, 0x40FC48)
ORIG_TAG, ORIG_TAG_BYTES = 0x40FDB8, b"ORG4"
GATED = ((0x40E6E2, 0x40E800), (0x40F00C, 0x40F100), (0x40FC40, 0x40FC4C), (0x40FDB5, 0x40FE00))   # the recon's §11: neither read
                                                            # nor written in its 25 runs
# v0.2.1's reverse block, as released (15 Nov 2026): frozen here, not imported
V021_TABLES = (0x40EE80, 0x40EEE0, 0x40EF40, 0x40EFA0, 0x40FC70, 0x40FCD0, 0x40FD30)
V021_SLOTS, V021_TAG, V021_TAG_BYTES, V021_CELLS = 0x40FD90, 0x40FDAC, b"REV4", (0x40FDB0, 0x40FDB5)
MENU_OF_ID = {0: 1, 1: 2, 2: 0}                             # an original's menu entry by its ranking id (Bay Bridge, Acropolis, Big Forest)
ID_OF_MENU = {m: r for r, m in MENU_OF_ID.items()}
LEVEL = {0: "MEDIUM", 1: "EXPERT", 2: "BEGINNER"}
DEFAULT_FIRST = {0: 0x1E00, 1: 0x2580, 2: 0x1E00}          # 4'00, 5'00, 4'00 (1/32 s); then 5 s steps
# Release records (opt-in): the comparisons with the set BEFORE this phase (a normal race on each of the ten courses, pass for pass;
# the attract with no game) run only when VR_P35_MAIN_SET names a directory holding that set's vr.zip, model1io.zip and m1comm.zip:
# `python -m vrtools build` from a checkout of 47460b0 (main before Phase 35). Made for the Phase 35 release (findings §4.3 and §6);
# after this phase is merged main is no longer that set, so without the variable they skip and say why. (Not VR_MAIN_SET:
# tests/test_hudreverse_build.py reads that one for a set of its own.)
MAIN_ENV = "VR_P35_MAIN_SET"
MAIN_SET = Path(os.environ[MAIN_ENV]) if os.environ.get(MAIN_ENV) else None
NO_MAIN = (f"release record: set {MAIN_ENV} to a build of 47460b0 (main before Phase 35) to compare with it; "
           "the rest of this test ran on this set")
BOOT_SECONDS, CLEAR_SECONDS, GAME_SECONDS, ATTRACT_SECONDS = 150, 60, 290, 1450


def test_the_originals_block_s_addresses():
    from vrtools.arcade import ranking as R
    assert R.ORIG_REVERSE_TABLES == ORIG_REVERSE_TABLES and R.ORIG_REVERSE_SLOTS == ORIG_REVERSE_SLOTS[0] == NEW_SLOTS
    assert (R.ORIG_TAG, R.ORIG_TAG_BYTES, R.ORIG_REVERSE_SHIFT, R.IDS, R.SHORT_ENTRIES) == (ORIG_TAG, ORIG_TAG_BYTES, 17, 20, 4)
    assert (R.REVERSE_TABLES, R.REVERSE_SLOTS, R.REVERSE_TAG, R.REVERSE_TAG_BYTES) == (V021_TABLES, V021_SLOTS, V021_TAG, V021_TAG_BYTES)
    assert (R.LAST_OFFSET_CELL, R.ROWS_CELL + 1) == V021_CELLS and R.NEW_MAGIC == b"S-RAM CHECK OK 10\0"       # the magic: v0.2's


def test_the_originals_block_lies_in_the_gated_battery_ram_and_overlaps_nothing():
    """The three 4-entry tables, their three slot words and the tag each lie inside one of the runs the recon's gate found
    untouched, and share no byte with one another, with v0.2.1's reverse block, with a normal table or its slot, with the
    magic, the game's record, the bookkeeping, the ranking id, the shown id, the attract counters or the stack's margin."""
    ours = ([(t, t + 24 * SHORT_ENTRIES) for t in ORIG_REVERSE_TABLES] + [(s, s + 4) for s in ORIG_REVERSE_SLOTS] + [(ORIG_TAG, ORIG_TAG + 4)])
    assert all(any(lo <= a and b <= hi for lo, hi in GATED) for a, b in ours), ours
    others = ([(t, t + TABLE_BYTES) for t in ORIG_TABLES + NEW_TABLES] + [(s, s + 4) for s in ORIG_SLOTS] + [(0x40E6C8, 0x40E6CC)]
              + [(NEW_SLOTS + 12, NEW_SLOTS + 40), (0x40E6D0, 0x40E6E2), (0x40E800, 0x40EA00), (0x40F000, 0x40F00C),
                 (RANKING_INDEX, RANKING_INDEX + 1), (SHOWN_ID, SHOWN_ID + 1), (ATTRACT_COUNTERS, ATTRACT_COUNTERS + 3),
                 (V021_SLOTS, V021_SLOTS + 28), (V021_TAG, V021_TAG + 4), V021_CELLS, (0x40FE00, 0x410000)]
              + [(t, t + 96) for t in V021_TABLES])
    spans = sorted(ours + others)
    assert all(b <= c for (_, b), (c, _) in zip(spans, spans[1:])), [(hex(a), hex(b)) for a, b in spans]
    assert ORIG_BLOCK == {a for lo, hi in ours for a in range(lo, hi)}


def test_the_originals_reverse_ids_and_their_place_in_the_attract(romset_zip, saturn_cue):
    """On the session's set: the three originals' reverse ids are 17, 18, 19 (their ranking id + 17); each stands straight after
    its original in its group (Bay Bridge's 0, 17, then the courses it hosts, each followed by its reverse id, ...); every id
    0..19 has its position in its group (`raceend`'s table). On a directory whose originals have no variant (the set before
    Phase 33) the groups and positions are as before."""
    from dataclasses import replace
    from vrtools.arcade.ranking import IDS, attract_groups, attract_positions, original_reverse_ids, reverse_ids
    from tests.test_tgp_build import _seven
    d = decode_directory(_seven(romset_zip, saturn_cue)[0])
    assert original_reverse_ids(d) == [17, 18, 19] and reverse_ids(d) == list(range(10, 17))
    groups = attract_groups(d)
    assert groups == [[0, 17, 4, 11, 7, 14, 8, 15, 9, 16], [1, 18, 5, 12, 6, 13], [2, 19, 3, 10]]
    pos = attract_positions(d)
    assert len(pos) == IDS and all(g[pos[i]] == i for g in groups for i in g)
    plain = [replace(e, reverse=None) if k < 3 else e for k, e in enumerate(d)]
    assert original_reverse_ids(plain) == [] and attract_groups(plain) == [[0, 4, 11, 7, 14, 8, 15, 9, 16], [1, 5, 12, 6, 13], [2, 3, 10]]
    assert attract_positions(plain)[17:] == [0, 0, 0]


def test_the_race_end_s_record_site_is_the_game_s_again(romset_zip, saturn_cue):
    """Phase 33's `rankgate3` is gone: on the session's set the race end's sixteen bytes at 0xfc40ce are the arcade's own, and
    the originals' block holds `hudorig` alone."""
    from vrtools.arcade.origrev import RANK_PATTERN, RANK_SITE, ROUTINES
    from vrtools.arcade.romset import RomSet
    from tests.test_tgp_build import _seven
    out = _seven(romset_zip, saturn_cue)[0]
    assert ROUTINES == ("hudorig",)
    assert out.boot[RANK_SITE - V60_BOOT:RANK_SITE - V60_BOOT + 16] == RomSet.from_zip(romset_zip).boot[RANK_SITE - V60_BOOT:RANK_SITE - V60_BOOT + 16] == RANK_PATTERN


# ---- synthetic battery RAM ----

def synthetic_v021(fresh: bytes) -> bytes:
    """A battery RAM as a v0.2.1 set leaves it after play, made from one this set made fresh (65 536 bytes, 0x400000 up): the
    originals' reverse block as v0.2.1 never wrote it (0xff); each of the seven reverse tables with four entries of its own (times
    from 4'16, each table's and entry's own view, player word and name), the seven slots on different entries (one on a fourth),
    the tag REV4; each of the ten normal tables with two entries of its own on top, the seven's slots on their second entry."""
    nv = bytearray(fresh)
    for a in ORIG_BLOCK:
        nv[a - B] = 0xFF
    for k, t in enumerate(V021_TABLES):
        for j in range(4):
            time = 0x2000 + 0x100 * k + 0x20 * j
            nv[t - B + 24 * j:t - B + 24 * j + 24] = ENTRY.pack(j + 1, time, (k + j) % 4, 0x100 * k + j, time, bytes([0x41 + k, 0x4B + j, 0x5A, 0]))
        nv[V021_SLOTS - B + 4 * k:V021_SLOTS - B + 4 * k + 4] = struct.pack("<I", t + 24 * (k % 4))
    nv[V021_TAG - B:V021_TAG - B + 4] = V021_TAG_BYTES
    for r, t in enumerate(ORIG_TABLES + NEW_TABLES):
        for j in range(2):
            time = 0x1000 + 0x40 * r + 0x10 * j
            nv[t - B + 24 * j + 4:t - B + 24 * j + 24] = ENTRY.pack(j + 1, time, (r + j) % 4, 0x200 * r + j, time, bytes([0x4E + r, 0x41 + j, 0x2E, 0]))[4:]
        if r >= 3:
            nv[NEW_SLOTS - B + 4 * r:NEW_SLOTS - B + 4 * r + 4] = struct.pack("<I", t + 24)
    return bytes(nv)


def synthetic_v02(fresh: bytes) -> bytes:
    """As `synthetic_v021`, but as v0.2 leaves it: no reverse block at all (the seven tables, their slots, the tag and the two
    cells 0xff as well)."""
    nv = bytearray(synthetic_v021(fresh))
    for a in REVERSE_BLOCK | CELLS:
        nv[a - B] = 0xFF
    return bytes(nv)


def test_the_synthetic_images_are_what_they_claim():
    fresh = bytes([0xFF]) * 0x10000
    a, b = synthetic_v021(fresh), synthetic_v02(fresh)
    assert a[V021_TAG - B:V021_TAG - B + 4] == b"REV4" and b[V021_TAG - B:V021_TAG - B + 4] == b"\xff" * 4
    assert set(_at(a, ORIG_BLOCK)) == set(_at(b, ORIG_BLOCK)) == {0xFF} and set(_at(b, REVERSE_BLOCK)) == {0xFF}
    entries = [ENTRY.unpack_from(a, t - B + 24 * j) for t in V021_TABLES for j in range(4)]
    assert len({e[1:] for e in entries}) == 28 and all(x[1] < y[1] for x, y in zip(entries, entries[1:]))   # every entry its own
    assert struct.unpack_from("<I", a, V021_SLOTS - B + 12)[0] == V021_TABLES[3] + 72                       # a slot on a fourth entry
    assert _at(a, NORMAL_BLOCK) == _at(b, NORMAL_BLOCK)


# ---- the session's runs ----

def _orig_block(rs, d) -> dict[int, int]:
    """The originals' reverse block as `originit` makes it, by byte address: three tables of four entries (rank 1..4,
    `original_reverse_defaults`, +8 = 0, +0xc = -1, the time again, the game's first four default names), the slots, the tag."""
    from vrtools.arcade.ranking import original_reverse_defaults
    names = [rs.boot[0xFC4DC4 - V60_BOOT + 8 * j:0xFC4DC8 - V60_BOOT + 8 * j] for j in range(SHORT_ENTRIES)]
    blob = {}
    for r, (table, times) in enumerate(zip(ORIG_REVERSE_TABLES, original_reverse_defaults(rs, d))):
        data = b"".join(ENTRY.pack(j + 1, t, 0, -1, t, names[j]) for j, t in enumerate(times))
        blob.update({table + i: x for i, x in enumerate(data)})
        blob.update({ORIG_REVERSE_SLOTS[r] + i: x for i, x in enumerate(struct.pack("<I", table))})
    blob.update({ORIG_TAG + i: x for i, x in enumerate(ORIG_TAG_BYTES)})
    return blob


def _pcs(first: str, after: str) -> range:
    from vrtools.arcade.ranking import ranking_layout
    rl = ranking_layout(directory_layout()["ranking"])
    return range(rl[first], rl[after])


class Game:
    """One game's run: race_end.lua's log (`RankRun`), ranking_attract.lua's (`BootRun`), the work directory, the battery RAM
    it started on."""
    def __init__(self, wd: Path, direction: str, before: bytes):
        battery = (wd / "nvram" / "vr" / "nvram").read_bytes()
        self.wd, self.before, self.battery = wd, before, battery
        self.race: RankRun = _parse_rank(wd / "end.txt", (direction,), battery)
        self.boot: BootRun = _parse_attract(wd / "log.txt", before, battery)


class TimesSession:
    """The session's set and its runs, each group made once at its first use, two MAMEs at a time."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        from vrtools.convert.lap import centreline, order_slices
        from tests.test_convert_collision import _saturn_course
        from tests.test_originals_reverse import _centreline
        from tests.test_race_build import _drive_line
        from tests.test_reverse_ranking import BAY_BRIDGE_TRACK
        from tests.test_tgp_build import _build, _seven
        out, conv = _seven(romset_zip, saturn_cue)
        self.rs, self.d, self.base = out, decode_directory(out), base
        self.build = _build(base, romset_zip, out)
        self.lines = {e: (_drive_line(conv[e - 3]) if e >= 3 else _centreline(out, e)) for e in range(10)}
        # a NORMAL race on Bay Bridge: the autopilot on the ROM's line 0 does not finish the lap (dev run: stuck on both sets, no
        # time in 290 s); Phase 27b's recipe does (tests/test_reverse_ranking.py's "bay" run: the Saturn track's centreline,
        # lookahead 3). The reverse race keeps the ROM's line read backwards (it finished on every run)
        self.normal_lines = {**self.lines, 1: centreline(order_slices(_saturn_course(saturn_cue, BAY_BRIDGE_TRACK)))}
        if MAIN_SET is not None and not (MAIN_SET / "vr.zip").is_file():
            raise FileNotFoundError(f"{MAIN_ENV}={MAIN_SET} holds no vr.zip")
        self.main = MAIN_SET
        self._groups: dict[str, dict] = {}

    def _game(self, label, rom, entry, reverse, before, extra=None, seconds=GAME_SECONDS) -> Game:
        from vrtools.arcade.select import WHEEL_FOR_ENTRY
        from vrtools.convert.reverse import reverse_points
        from vrtools.mame.runner import LUA_DIR, run_mame, write_centreline
        wd = self.base / label
        (wd / "nvram" / "vr").mkdir(parents=True)
        (wd / "nvram" / "vr" / "nvram").write_bytes(before)
        line = write_centreline(wd / "line.csv", reverse_points(self.lines[entry]) if reverse else self.normal_lines[entry])
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
               "VR_AUTOPILOT": str(line), "VR_EXTRA_LUA": f"{LUA_DIR / 'race_end.lua'};{LUA_DIR / 'ranking_attract.lua'}",
               "VR_END_LOG": str(wd / "end.txt"), "VR_RANK_LOG": str(wd / "log.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}",
               "VR_END_TABLE": f"{BATTERY[0]:x}-{BATTERY[1]:x}", "VR_END_TAP_AT": "1", "VR_PASS_LOG": str(wd / "pass.txt"),
               "VR_INPUT_LOG": str(wd / "tape.txt"), **(extra or {})}
        if reverse:
            env["VR_DIRECTION"] = "1"
        run_mame(LUA_DIR / "autoplay.lua", seconds, wd, rom, env=env, timeout=3600)
        return Game(wd, "reverse" if reverse else "normal", before)

    def _group(self, name: str, make) -> dict:
        if name not in self._groups:
            self._groups[name] = make()
        return self._groups[name]

    def boots(self) -> dict[str, BootRun]:
        """"fresh" (no battery RAM) and "fresh2" (its second boot); "upgrade" (on `synthetic_v021` of fresh's) and "upgrade2";
        "v02" (on `synthetic_v02`)."""
        def make():
            fresh = _attract(self.base, self.build, "fresh", BOOT_SECONDS)
            jobs = {"fresh2": fresh.battery, "upgrade": synthetic_v021(fresh.battery), "v02": synthetic_v02(fresh.battery)}
            with ThreadPoolExecutor(2) as ex:
                runs = dict(zip(jobs, ex.map(lambda kv: _attract(self.base, self.build, kv[0], BOOT_SECONDS, kv[1]), jobs.items())))
            runs["fresh"] = fresh
            runs["upgrade2"] = _attract(self.base, self.build, "upgrade2", BOOT_SECONDS, runs["upgrade"].battery)
            return runs
        return self._group("boots", make)

    def upgraded(self) -> bytes:
        """The battery RAM this set leaves after its first boot on the synthetic v0.2.1 image."""
        return self.boots()["upgrade"].battery

    def reverses(self) -> dict:
        """On `upgraded`: "rev0", "rev1", "rev2" (a reverse race on the original of that menu entry, a record); "third" and "slow"
        (Big Forest in reverse, its table preset round the race's time: third, and slower than the fourth); then, on rev0's
        battery RAM, "seven" (Amazon Falls in reverse, a record) and on that one "clear" (the test mode's backup clear)."""
        def make():
            u = self.upgraded()
            table = ORIG_REVERSE_TABLES[ID_OF_MENU[0]]

            def chain():
                a = self._game("rev0", self.build, 0, True, u)
                b = self._game("seven", self.build, 4, True, a.battery, seconds=220)
                c = _attract(self.base, self.build, "clear", CLEAR_SECONDS, b.battery, {"VR_RANK_INPUT": TEST_INPUT})
                return {"rev0": a, "seven": b, "clear": c}
            jobs = [chain, lambda: {"rev1": self._game("rev1", self.build, 1, True, u)},
                    lambda: {"rev2": self._game("rev2", self.build, 2, True, u)},
                    lambda: {"third": self._game("third", self.build, 0, True, u, {"VR_END_PRESET": f"{table:x}:-64,-32,32,64"})},
                    lambda: {"slow": self._game("slow", self.build, 0, True, u, {"VR_END_PRESET": f"{table:x}:-128,-96,-64,-32"})}]
            out = {}
            with ThreadPoolExecutor(2) as ex:
                for got in ex.map(lambda f: f(), jobs):
                    out.update(got)
            return out
        return self._group("reverses", make)

    def normals(self) -> dict:
        """For each menu entry 0..9, on `upgraded`: ("main", e), a normal one-lap race to its name entry and the attract's first
        page on main's set, its wheel and pedal taped; (e,), the same on this set, fed that tape (without main's set: driven by
        the autopilot)."""
        def make():
            u = self.upgraded()

            def pair(e):
                from tests.test_reverse_ranking import BAY_LOOKAHEAD
                seconds = 240 if e >= 3 else GAME_SECONDS
                look = {"VR_AUTOPILOT_LOOKAHEAD": BAY_LOOKAHEAD} if e == 1 else {}
                if self.main is None:
                    return {(e,): self._game(f"normal{e}", self.build, e, False, u, look, seconds=seconds)}
                old = self._game(f"normal{e}_main", self.main, e, False, u, look, seconds=seconds)
                new = self._game(f"normal{e}", self.build, e, False, u, {**look, "VR_INPUT_REPLAY": str(old.wd / "tape.txt")}, seconds=seconds)
                return {("main", e): old, (e,): new}
            out = {}
            with ThreadPoolExecutor(2) as ex:
                for got in ex.map(pair, range(10)):
                    out.update(got)
            return out
        return self._group("normals", make)

    def attracts(self) -> dict[str, BootRun]:
        """ATTRACT_SECONDS of attract with no input on a fresh battery RAM: "new" (this set), "main" (main's, when it is there)."""
        def make():
            jobs = {"new": self.build, **({"main": self.main} if self.main else {})}
            with ThreadPoolExecutor(2) as ex:
                return dict(zip(jobs, ex.map(lambda kv: _attract(self.base, kv[1], "attract_" + kv[0], ATTRACT_SECONDS), jobs.items())))
        return self._group("attracts", make)


_TIMES: dict[str, TimesSession] = {}


@pytest.fixture
def times(romset_zip, saturn_cue, tmp_path_factory) -> TimesSession:
    key = str(romset_zip)
    if key not in _TIMES:
        _TIMES[key] = TimesSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("times"))
    return _TIMES[key]


SAVED = NORMAL_BLOCK | REVERSE_BLOCK                        # every saved byte of a v0.2.1 battery RAM's best times: the ten normal
                                                            # tables, their slots, the magic, the ranking id; the seven reverse
                                                            # tables, their slots, the tag
QUIET = CELLS | PAGE_OWN | set(BOOKKEEPING) | GAME_RECORD   # what a boot and its attract pages write besides


# ---- boots ----

def test_a_fresh_battery_ram_gets_the_three_tables(times):
    """A boot on no battery RAM: the three tables of four entries with ranks 1..4, the seven's rule for the times (the first four
    of the original's own normal table as the game's initialiser writes it in this very boot: Bay Bridge and Big Forest 4'00,
    4'05, 4'10, 4'15, Acropolis 5'00 .. 5'15), +8 = 0, +0xc = -1, the game's first four default names; the three slots on their
    tables; the tag. Written by `originit` alone, on the S-RAM check's frame, twice (from `revtag`, the tag missing, then from
    `slot_init` inside the stock initialiser, the magic missing)."""
    run = times.boots()["fresh"]
    want = _orig_block(times.rs, times.d)
    assert {a: run.battery[a - B] for a in want} == want
    first4 = lambda t: [ENTRY.unpack_from(run.battery, t - B + 24 * j)[1] for j in range(4)]
    assert [first4(t) for t in ORIG_REVERSE_TABLES] == [first4(t) for t in ORIG_TABLES] == [[DEFAULT_FIRST[r] + 0xA0 * j for j in range(4)] for r in range(3)]
    assert [ENTRY.unpack_from(run.battery, t - B + 24 * j)[5] for t in ORIG_REVERSE_TABLES for j in range(4)] == [b"YU.\0", b"RNS\0", b"TKG\0", b"NAG\0"] * 3
    ours = [(f, pc) for f, pc, a, _ in _bytes(run.writes) if a in ORIG_BLOCK]
    assert len(ours) == 2 * len(ORIG_BLOCK) and len({f for f, _ in ours}) == 1 and all(pc in _pcs("originit", "title3") for _, pc in ours)
    assert run.battery[V021_TAG - B:V021_TAG - B + 4] == V021_TAG_BYTES and run.battery[0x40E6D0 - B:0x40E6D0 - B + 18] == b"S-RAM CHECK OK 10\0"


def test_a_v0_2_1_battery_ram_keeps_every_saved_byte(times):
    """The upgrade from v0.2.1 (the synthetic image: every table with its own times, views and names, slots on different
    entries): after this set's first boot and its attract, every byte of the ten normal tables, their slots, the magic, the
    ranking id, the seven reverse tables, their slots and the tag REV4 is the byte it was, and NONE of them was written. The
    three new tables, their slots and their tag are made once, by `originit` from `revtag`, on the S-RAM check's frame; neither
    `revinit` nor the stock initialiser runs. Everything else the boot writes is the game's record, the bookkeeping and the
    attract pages' own cells."""
    run = times.boots()["upgrade"]
    before = run.before
    assert before[V021_TAG - B:V021_TAG - B + 4] == b"REV4" and set(_at(before, ORIG_BLOCK)) == {0xFF}
    written = _bytes(run.writes)
    assert not {a for _, _, a, _ in written} & SAVED, sorted(hex(a) for _, _, a, _ in written if a in SAVED)[:10]
    assert _at(run.battery, SAVED) == _at(before, SAVED)
    want = _orig_block(times.rs, times.d)
    assert {a: run.battery[a - B] for a in want} == want
    ours = [(f, pc) for f, pc, a, _ in written if a in ORIG_BLOCK]
    assert len(ours) == len(ORIG_BLOCK) and len({f for f, _ in ours}) == 1 and all(pc in _pcs("originit", "title3") for _, pc in ours)
    assert not any(pc in _pcs("revinit", "revtag") or 0xFC3B49 <= pc < 0xFC3C1B for _, pc, _, _ in written)
    others = {a for _, _, a, _ in written} - ORIG_BLOCK - QUIET
    assert not others, sorted(map(hex, others))[:10]


def test_a_v0_2_battery_ram_gets_all_ten_reverse_tables(times):
    """The upgrade from v0.2 (the synthetic image without any reverse block): the ten normal tables, their slots, the magic and
    the ranking id are kept, unwritten; the seven reverse tables are made with their defaults by `revinit` (as v0.2.1 made
    them) and the three by `originit`."""
    from tests.test_reverse_ranking import _reverse_block
    run = times.boots()["v02"]
    written = _bytes(run.writes)
    assert not {a for _, _, a, _ in written} & NORMAL_BLOCK and _at(run.battery, NORMAL_BLOCK) == _at(run.before, NORMAL_BLOCK)

    class Set:
        rs, d = times.rs, times.d
    want = {**_reverse_block(Set), **_orig_block(times.rs, times.d)}
    assert {a: run.battery[a - B] for a in want} == want
    assert not any(0xFC3B49 <= pc < 0xFC3C1B for _, pc, _, _ in written)


@pytest.mark.parametrize("label", ["fresh2", "upgrade2"])
def test_a_second_boot_writes_no_table(times, label):
    run = times.boots()[label]
    written = {a for _, _, a, _ in _bytes(run.writes)}
    assert not written & (SAVED | ORIG_BLOCK), sorted(map(hex, written & (SAVED | ORIG_BLOCK)))[:10]
    assert written <= QUIET, sorted(map(hex, written - QUIET))[:10]
    assert _at(run.battery, SAVED | ORIG_BLOCK) == _at(run.before, SAVED | ORIG_BLOCK)


# ---- a reverse race on an original ----

def _own(ident: int) -> tuple[int, int, set[int]]:
    table, slot = ORIG_REVERSE_TABLES[ident], ORIG_REVERSE_SLOTS[ident]
    return table, slot, set(range(table, table + 96)) | set(range(slot, slot + 4))


def _first_page(g: Game) -> dict:
    """The attract's first ranking page after the game."""
    pages = [p for p in _spans(g.boot) if p["start"] > g.race.loads[0]]
    assert pages, "no ranking page after the game"
    return pages[0]


@pytest.mark.parametrize("entry", [0, 1, 2], ids=["big_forest", "bay_bridge", "acropolis"])
def test_a_reverse_race_on_an_original_records_in_its_own_table(times, entry):
    """A one-lap reverse race on an original, on the upgraded v0.2.1 image: the loader served the variant (the flag 1 through
    the race), the record flag is set and the name entry comes (the modes after the finish are a record's). Of every table,
    slot and tag in the battery RAM, the race writes its own reverse table's entries (all but the rank numbers: the new time
    bubbles from fourth to first) and its slot, nothing else: every saved byte of the v0.2.1 image but the ranking id is
    unwritten and unchanged, and so are the two other originals' reverse tables. The table ends with the race's time first
    (the name entry's three spaces: the autoplay enters no letter), the three first defaults below it, ranks 1..4; the slot on
    entry 0. Then (Phase 27b) `raceend` points the original's group at its reverse table and the attract's first ranking page
    is that table's: one screen of four rows under "<LEVEL> REVERSE RANKING"."""
    from vrtools.arcade.ranking import attract_groups, attract_positions
    g = times.reverses()[f"rev{entry}"]
    ident = ID_OF_MENU[entry]
    table, slot, ours = _own(ident)
    lines = _race(g.race, 0)
    race = _driving(lines)
    assert race and all(l.flag == 1 for l in race), race[:3]
    assert any(l.record & 1 for l in lines) and _after_finish(lines) == RECORD, [hex(m) for m in _after_finish(lines)]
    written = {a for f, _, a, _ in _bytes(g.race.writes) if f >= g.race.loads[0] - 600}
    everything = SAVED | ORIG_BLOCK
    fields = {table + 24 * k + o for k in range(4) for o in range(4, 24)}
    assert written & everything == fields | set(range(slot, slot + 4)) | {RANKING_INDEX}, sorted(map(hex, (written & everything) ^ fields))[:12]
    assert written <= ours | CELLS | set(BOOKKEEPING) | MAIN_OUTSIDE, sorted(map(hex, written - ours - CELLS - set(BOOKKEEPING) - MAIN_OUTSIDE))[:10]
    keep = SAVED - {RANKING_INDEX}
    assert _at(g.battery, keep) == _at(g.before, keep)
    assert _at(g.battery, ORIG_BLOCK - ours) == _at(g.before, ORIG_BLOCK - ours)
    entries = [ENTRY.unpack_from(g.battery, table - B + 24 * k) for k in range(4)]
    (_, time), = g.race.times
    names = [times.rs.boot[0xFC4DC4 - V60_BOOT + 8 * j:0xFC4DC8 - V60_BOOT + 8 * j] for j in range(3)]
    print("REVERSE RECORD", LEVEL[ident], "time", time, f"({time / 32:.2f} s)", "view", entries[0][2])
    assert [e[0] for e in entries] == [1, 2, 3, 4]
    assert entries[0][1] == entries[0][4] == time and 0 < time < DEFAULT_FIRST[ident] and entries[0][2] in range(4) and entries[0][5] == b"   \0"
    assert [(e[1], e[2], e[3], e[4], e[5]) for e in entries[1:]] == [(DEFAULT_FIRST[ident] + 0xA0 * j, 0, -1, DEFAULT_FIRST[ident] + 0xA0 * j, names[j]) for j in range(3)]
    assert struct.unpack_from("<I", g.battery, slot - B)[0] == table
    # the attract's first page
    group = attract_groups(times.d)[ident]
    assert group[1] == ident + 17 and attract_positions(times.d)[ident + 17] == 1
    counter = [(pc, v) for f, pc, a, v in _bytes(g.race.writes) if a == ATTRACT_COUNTERS + ident and g.race.loads[0] <= f]
    assert counter and counter[0][1] == 1 and counter[0][0] in _pcs("raceend", "originit"), counter[:3]
    page = _first_page(g)
    assert (page["id"], page["di"], page["table"]) == (ident + 17, ident, table) and page["end"] - page["start"] == SHORT_PAGE
    _assert_page(page, times.rs, times.d)


def test_a_reverse_time_on_an_original_lands_third(times):
    """Big Forest's reverse table preset round the race's time at its results (two faster, two slower): the race's time lands
    third (the name entry comes), the two faster stay first and second, the slower one moves to fourth, the slowest is gone."""
    g = times.reverses()["third"]
    table, slot, _ = _own(ID_OF_MENU[0])
    (_, time), = g.race.times
    entries = [ENTRY.unpack_from(g.battery, table - B + 24 * k) for k in range(4)]
    assert _after_finish(_race(g.race, 0)) == RECORD
    assert [e[1] for e in entries] == [time - 64, time - 32, time, time + 32] and [e[0] for e in entries] == [1, 2, 3, 4]
    assert [e[5] for e in entries] == [b"AAA\0", b"BBB\0", b"   \0", b"CCC\0"]
    assert struct.unpack_from("<I", g.battery, slot - B)[0] == table + 48


def test_a_reverse_time_on_an_original_slower_than_the_fourth_records_nothing(times):
    """The table preset with four faster times: no record flag, no name entry, the table as preset; the attract's first page
    is still Big Forest's reverse table (every finished race jumps: Phase 27b)."""
    g = times.reverses()["slow"]
    table, slot, _ = _own(ID_OF_MENU[0])
    (_, time), = g.race.times
    lines = _race(g.race, 0)
    assert not any(l.record & 1 for l in lines) and _after_finish(lines) == NO_RECORD
    entries = [ENTRY.unpack_from(g.battery, table - B + 24 * k) for k in range(4)]
    assert [e[1] for e in entries] == [time - 128, time - 96, time - 64, time - 32]
    assert _first_page(g)["id"] == 19


# ---- the seven, and the backup clear ----

def test_a_reverse_record_on_one_of_the_seven_after_it_keeps_the_rest(times):
    """On the battery RAM the Big Forest reverse race left: a one-lap reverse race on Amazon Falls. Its v0.2.1 table (the
    synthetic four entries) takes the race's time first and moves its three first entries down whole (time, view, player word,
    name), the fourth gone, as on main; every other saved byte of the image, and the three originals' tables (Big Forest's
    with its record), is unwritten and unchanged."""
    g = times.reverses()["seven"]
    k = 4 - 3
    table, slot = V021_TABLES[k], V021_SLOTS + 4 * k
    ours = set(range(table, table + 96)) | set(range(slot, slot + 4))
    assert _after_finish(_race(g.race, 0)) == RECORD
    written = {a for f, _, a, _ in _bytes(g.race.writes) if f >= g.race.loads[0] - 600}
    assert written & (SAVED | ORIG_BLOCK) <= ours | {RANKING_INDEX}, sorted(map(hex, (written & (SAVED | ORIG_BLOCK)) - ours))[:10]
    keep = (SAVED | ORIG_BLOCK) - ours - {RANKING_INDEX}
    assert _at(g.battery, keep) == _at(g.before, keep)
    was = [ENTRY.unpack_from(g.before, table - B + 24 * j) for j in range(4)]
    now = [ENTRY.unpack_from(g.battery, table - B + 24 * j) for j in range(4)]
    (_, time), = g.race.times
    assert [e[0] for e in now] == [1, 2, 3, 4] and now[0][1] == now[0][4] == time < was[0][1] and now[0][5] == b"   \0"
    assert [e[1:] for e in now[1:]] == [e[1:] for e in was[:3]]


def test_the_backup_clear_resets_all_twenty_tables(times):
    """The test mode's BACKUP RAM CLEAR on that battery RAM (the v0.2.1 image's times, a record on an original's reverse table
    and one on Amazon Falls's): the ten normal tables come back to their defaults (as this set's fresh boot makes them), the
    seven reverse tables to theirs (`revinit`) and the three originals' to theirs (`originit`: the stock clear does not write
    their bytes, the project's own `slot_init` calls it), with their slots and tags; the +0xc word of the arcade's own three
    tables is left as it was (the stock clear's own behaviour)."""
    from tests.test_reverse_ranking import _reverse_block
    r = times.reverses()
    run, fresh = r["clear"], times.boots()["fresh"]
    assert _at(run.before, ORIG_BLOCK) != _at(fresh.battery, ORIG_BLOCK) and _at(run.before, REVERSE_BLOCK) != _at(fresh.battery, REVERSE_BLOCK)
    clear = [f for f, pc, _, _ in _bytes(run.writes) if 0xFC3B49 <= pc < 0xFC3C1B]
    assert clear and min(clear) > 2500

    class Set:
        rs, d = times.rs, times.d
    want = {**_reverse_block(Set), **_orig_block(times.rs, times.d)}
    assert {a: run.battery[a - B] for a in want} == want
    # the stock clear leaves the +0xc word of the arcade's own three tables as it finds it (dev run: the synthetic image's player
    # words in their first two entries survived it; `slot_init` sets the word to -1 on the seven's tables only, since Phase 22r):
    # the arcade's behaviour, not this phase's (the clear's own code is not patched)
    plus_c = {t + 24 * k + 0xC + i for t in ORIG_TABLES for k in range(TABLE_BYTES // 24) for i in range(4)}
    normal = NORMAL_BLOCK - {RANKING_INDEX} - plus_c
    assert _at(run.battery, normal) == _at(fresh.battery, normal)
    assert _at(run.battery, plus_c) == _at(run.before, plus_c)
    ours = [(f, pc) for f, pc, a, _ in _bytes(run.writes) if a in ORIG_BLOCK]
    assert len(ours) == len(ORIG_BLOCK) and {f for f, _ in ours} <= set(clear) and all(pc in _pcs("originit", "title3") for _, pc in ours)


# ---- the normal direction ----

@pytest.mark.parametrize("entry", range(10))
def test_a_normal_race_records_as_on_main(times, entry):
    """A normal one-lap race on each of the ten courses, on the upgraded v0.2.1 image, to its name entry and the attract's first
    page. On this set: the record goes into the course's own normal table (an original's: the arcade's own table) and its slot,
    no reverse table, slot or tag is written, and the attract's first page is the course's normal table. Against main's set
    (47460b0) on the same battery RAM and the same wheel and pedal, frame for frame: the game's state at the end of every logic
    pass is the same up to the start of the attract's second ranking page after the race (where one of the three new
    pages may stand, and after which every frame moves), and so are the race_end log's lines; from the race's load to that first page's end the battery writes are main's, write
    for write (frame, address, bytes, value; the PC where it lies in the boot ROM), but for the value `raceend` puts in the
    group's counter (an original's own reverse page now stands before the pages after it) and the counter after it."""
    from vrtools.arcade.ranking import ranking_ids
    from vrtools.mame.framerate import parse_pass_log
    runs = times.normals()
    g = runs[(entry,)]
    ident = ranking_ids(times.d)[entry]
    table = (ORIG_TABLES + NEW_TABLES)[ident]
    slot = ORIG_SLOTS[ident] if ident < 3 else NEW_SLOTS + 4 * ident
    lines = _race(g.race, 0)
    assert all(l.flag == 0 for l in lines) and _after_finish(lines) == RECORD
    written = {a for f, _, a, _ in _bytes(g.race.writes) if f >= g.race.loads[0] - 600}
    ours = set(range(table, table + TABLE_BYTES)) | set(range(slot, slot + 4))
    assert written & (SAVED | ORIG_BLOCK) <= ours | {RANKING_INDEX} and written & ours, sorted(map(hex, (written & (SAVED | ORIG_BLOCK)) - ours))[:10]
    assert _at(g.battery, REVERSE_BLOCK | ORIG_BLOCK) == _at(g.before, REVERSE_BLOCK | ORIG_BLOCK)
    first = ENTRY.unpack_from(g.battery, table - B)
    (_, time), = g.race.times
    assert first[0] == 1 and first[1] == time and first[5] == b"   \0"
    page = _first_page(g)
    assert (page["id"], page["table"]) == (ident, table)
    _assert_page(page, times.rs, times.d)
    if ("main", entry) not in runs:
        pytest.skip(NO_MAIN)
    m = runs[("main", entry)]
    assert (g.wd / "tape.txt").read_text() == (m.wd / "tape.txt").read_text()
    # up to the attract's SECOND ranking page after the race, which may legitimately differ: the member of a group after the
    # course raced is another one when the group holds one of the three new reverse ids, or it is one of them (one screen,
    # where main shows a page of four screens), and every frame of the attract after it moves (dev run: after a normal Big
    # Forest race the second page was Acropolis's reverse table, 396 frames, on this set and Alpine's, 1 584, on main's; the
    # next scene loaded 1 188 frames sooner). `_spans` lists whole pages only, so a page cut by the run's end is missing from
    # one log: the window ends at the first second page either log has, or at the run's end
    seconds = [ps[1] for ps in ([p["start"] for p in _spans(r.boot) if p["start"] > r.race.loads[0]] for r in (g, m)) if len(ps) > 1]
    upto = min(seconds, default=10 ** 9)
    a = [w for w in parse_pass_log(g.wd / "pass.txt") if int(w.split()[2]) < upto]
    b = [w for w in parse_pass_log(m.wd / "pass.txt") if int(w.split()[2]) < upto]
    diff = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    assert len(a) > 3000 and len(a) == len(b) and diff is None, (entry, upto, len(a), len(b), diff)
    lines = lambda r: [(l.frame, l.mode, l.state, l.flag, l.record, _boot_pc(l.handler)) for l in r.race.lines if l.frame < upto]
    assert g.race.loads == m.race.loads and g.race.times == m.race.times and lines(g) == lines(m)  # (the select's handlers moved)
    end = page["end"]
    assert _first_page(m)["end"] == end and (_first_page(m)["id"], _first_page(m)["table"]) == (ident, table)
    key = lambda w: (w[0], _boot_pc(w[1]), w[2], w[4])
    span = lambda r: [w for w in r.race.writes if r.race.loads[0] <= w[0] < end]
    assert [key(w) for w in span(g)] == [key(w) for w in span(m)]
    differ = {(w[2], w[4]) for w, x in zip(span(g), span(m)) if w[3] != x[3]}
    counters = set(range(ATTRACT_COUNTERS & ~1, ATTRACT_COUNTERS + 3))      # the three groups' counter bytes (as the bus logs them:
    assert {a for a, _ in differ} <= counters, differ                        # the even address of a byte pair, a lane mask)
    assert _at(g.battery, SAVED | ORIG_BLOCK) == _at(m.battery, SAVED | ORIG_BLOCK)   # (main's set does not write the originals' block)


def test_a_normal_race_on_an_original_jumps_to_its_normal_page_then_its_reverse_page_follows(times):
    """After a normal Bay Bridge race (Phase 27b's recipe: the Saturn track's centreline, lookahead 3) the attract's first page
    is Bay Bridge's own table (`raceend` wrote position 0) and the next page of its group is its reverse table, id 17 (precheck
    on the play set: pages 0, then Alpine's 3 of Big Forest's group, then 17)."""
    from tests.test_reverse_ranking import _assert_page
    g = times.normals()[(1,)]
    pages = [p for p in _spans(g.boot) if p["start"] > g.race.loads[0]]
    assert pages and (pages[0]["id"], pages[0]["di"]) == (0, 0), [(p["start"], p["id"]) for p in pages]
    nxt = next(p for p in pages[1:] if p["di"] == 0)
    assert nxt["id"] == 17, [(p["start"], p["id"]) for p in pages]
    _assert_page(nxt, times.rs, times.d)


# ---- the attract with no game ----

def test_the_attract_shows_the_three_new_pages_in_their_places(times):
    """ATTRACT_SECONDS of attract on a fresh battery RAM: every member of each group comes, in its group's order (each
    original's reverse table straight after its own); each page is its id's page (`_assert_page`: an original's reverse page
    one screen of four rows, rows five and six empty, SHORT_PAGE frames, under "MEDIUM / EXPERT / BEGINNER REVERSE RANKING",
    the level word and REVERSE in red, RANKING in white); the direction flag is 0 throughout. Against main's set: the pages of
    each data index, the three new pages left out, are main's pages of that data index in main's order, each with main's
    table, screens, length, title and rows; and up to the first new page's setter call the two attracts are the same frame for
    frame (modes, pages, titles, rows)."""
    from vrtools.arcade.ranking import attract_groups
    runs = times.attracts()
    run = runs["new"]
    assert {flag for _, _, _, flag in run.lines} == {0}
    pages = _spans(run)
    groups = attract_groups(times.d)
    print("PAGES", [(p["start"], p["di"], p["id"]) for p in pages])
    for k, g in enumerate(groups):
        shown = [p["id"] for p in pages if p["di"] == k]
        assert set(shown) == set(g), (k, shown, g)
        start = g.index(shown[0])
        assert shown == [g[(start + j) % len(g)] for j in range(len(shown))], (k, shown)
    for p in pages:
        _assert_page(p, times.rs, times.d)
    assert {p["id"] for p in pages} >= {17, 18, 19}
    if "main" not in runs:
        pytest.skip(NO_MAIN)
    main = runs["main"]
    page = lambda p: (p["id"], p["table"], p["firsts"], p["end"] - p["start"], p["titles"][-1], p["rows"][-1])
    for k in range(3):
        mine = [page(p) for p in pages if p["di"] == k and p["id"] < 17]
        theirs = [page(p) for p in _spans(main) if p["di"] == k]
        n = min(len(mine), len(theirs))
        assert n >= 3 and mine[:n] == theirs[:n], (k, [x[0] for x in mine], [x[0] for x in theirs])
    new = next(f for f, _, a, v in _bytes(run.writes) if a == SHOWN_ID and v >= 17)
    upto = lambda rows: [r for r in rows if r[0] < new]
    assert new > 4000 and upto(run.lines) == upto(main.lines) and upto(run.pages) == upto(main.pages)
    assert upto(run.titles) == upto(main.titles) and upto(run.rows) == upto(main.rows)
