"""Phase 26 stage 3 in MAME: the COURSE DIRECTION screen on the seven-course set (`tests.test_tgp_build._seven`, one conversion
per session).

Task 1: the direction flag's life and the ranking gate. race_end.lua makes the race one lap long with the clock held (recon §8's
`finish.lua`), logs the modes, the flag, the record flag 0x5018fc and the select handler at every change, taps the course's
ranking table from the race load on, and puts a coin in after the attract's sixth pit scene. Three runs, each made once per
session:

- "reverse": Metropolis reverse under the autopilot (since Task 2 chosen on the screen, autoplay.lua answering REVERSE), its one
  lap, the results, the attract and its pit scenes, then a coin and START: the second game's select screen starts.
- "normal": the same race in the normal direction (the screen answered NORMAL), through its name entry to the attract.
- "operator": the operator's fixed course (`VR_POKE=40dca1=2,501103=2`) with the flag poked to 1 before the coin.

Task 2: the screen as behaviour (recon §1.2 (a), §5, §9). dirscreen_log.lua logs the select entity's handler, the timer, the
flag and the screen's three cells, the gas edge and the transmission at every change; 45-second runs with the game's own inputs
(no autopilot), each made once per session, autoplay.lua answering the screen (plan D14) unless VR_DIR_ANSWER=0, when
dirscreen_drive.lua sets the pedal and the wheel by hand.

Task 5: the arrows and the SELECT DIRECTION caption (dirgfx.py's block): on the drawn screen's dumps, layer 0's arrow cells
name the clockwise / anticlockwise arrow's block as the entry's lap sense says (Alpine anticlockwise, Surfers Road clockwise),
character RAM holds the built set's block characters, the arrows' palettes are the white and red sets on the right sides (kept
at the lock), the caption covers the wheel panel's lettering cells; and a second game's course select (after the reverse race
of Task 1's run) shows its middle picture's own characters and palettes in the middle slot's blocks again.

Task 7: Task 1's two Metropolis runs also log, every second video frame (one scan per logic frame), the visible cells of the tile layers that name the middle
slot's blocks (slot_log.lua) and dump tile RAM after every mode change from the race load on: no screen from the race load to the
next game's select upload shows the arrows' and caption's blocks.
"""
import struct
from dataclasses import dataclass

import pytest

from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.directory import directory_layout
from vrtools.arcade.ranking import NEW_TABLES, TABLE_BYTES
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.mame.runner import LUA_DIR, parse_dir_log, parse_start_log
from tests.test_race_build import _drive_entry
from tests.test_tgp_build import _seven

METROPOLIS = 6
TABLE = NEW_TABLES[METROPOLIS - 3]          # Metropolis's ranking table (0x40f340, 24 entries of 24 bytes)
PIT_SCENES = 6                              # the attract pit scenes (mode 0x07) watched before the coin (recon §7 measured six)
# The modes from the finish to the attract (recon §8): the finish (0x19, 0x1a), the results (0x15, 0x16), the race-end ranking
# page (0x1b-0x1d), the name entry (0x1e) only after a record, then the attract load (0x02)
NO_RECORD = (0x19, 0x1A, 0x15, 0x16, 0x1B, 0x1C, 0x1D, 0x02)
RECORD = (0x19, 0x1A, 0x15, 0x16, 0x1B, 0x1C, 0x1D, 0x1E, 0x02)
NAME_ENTRY = 0x1E
PIT_SCENE = 0x07
SELECT = 0x10
# the select entity's handlers (recon §1.1, §7 `fixed2`): mode 0x10 state 0 installs 0xfc267e, which takes the course select
# (0xfc26c5, its lock 0xfc277c, then 0xfc27be) or, on the operator's fixed course, the SHIFT MODE SELECTOR (0xfc29b3, its lock
# 0xfc2a1d, then 0xfc2a59)
STATE0_HANDLER = 0xFC267E
SHIFT_CHAIN = {0xFC29B3, 0xFC2A1D, 0xFC2A59}
COURSE_CHAIN = {0xFC26C5, 0xFC277C, 0xFC27BE}


@dataclass(frozen=True)
class Line:
    frame: int
    mode: int
    state: int
    flag: int
    record: int
    handler: int


@dataclass(frozen=True)
class EndLog:
    load: int                               # the race load's frame
    lines: list[Line]                       # M lines
    writes: list[tuple[int, int, int]]      # W lines: (frame, pc, address)
    coin: int | None                        # the coin's frame


def _parse(path) -> EndLog:
    load, lines, writes, coin = None, [], [], None
    for row in open(path):
        tag, *f = row.split()
        if tag == "L":
            load = int(f[0])
        elif tag == "M":
            lines.append(Line(int(f[0]), int(f[1], 16), int(f[2]), int(f[3], 16), int(f[4], 16), int(f[5], 16)))
        elif tag == "W":
            writes.append((int(f[0]), int(f[1], 16), int(f[2], 16)))
        elif tag == "C":
            coin = int(f[0])
    assert load is not None, path
    return EndLog(load, lines, writes, coin)


_RUNS: dict[str, EndLog] = {}
_DUMPS: dict[str, object] = {}
_SLOTS: dict[str, object] = {}              # Task 7: label -> the run's directory (slot.txt, slot/)
SELECT_DUMP_AFTER = 300                     # Task 5: frames from a select screen's start to its dump (the wheel settled, no lock yet)
SLOT_LOCKED_DUMP = 1462                     # Task 7: 60 frames after autoplay's direction lock (ANSWER_LOCK, 1402: autoplay.lua's second
                                            # press at 1400); the race loads at 1600


def _run(tmp_path_factory, romset_zip, saturn_cue, label) -> EndLog:
    if label not in _RUNS:
        out, conv = _seven(romset_zip, saturn_cue)
        base = tmp_path_factory.mktemp(label)
        log = base / "end.txt"
        env = {"VR_EXTRA_LUA": str(LUA_DIR / "race_end.lua"), "VR_END_LOG": str(log), "VR_SNAPS": "", "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"}
        if label == "operator":                                   # the game's own inputs: the race only has to load
            _drive_entry(base, out, romset_zip, 0, None, seconds=40, autopilot=False,
                         extra_env={**env, "VR_POKE": f"40dca1=2,501103=2,{DIRECTION_RAM:x}=1"})
        else:
            reverse = label == "reverse"
            c = conv[METROPOLIS - 3]
            assert c.entry.name == "METROPOLIS"
            env["VR_END_TABLE"] = f"{TABLE:x}-{TABLE + TABLE_BYTES - 1:x}"
            (base / "dumps").mkdir()                              # Task 7: the locked screen dumped (select_dump.lua), the middle
            (base / "slot").mkdir()                               # slot's cells on screen logged and dumped by mode (slot_log.lua)
            env.update({"VR_SELECT_DIR": str(base / "dumps"), "VR_SELECT_DUMP": str(SLOT_LOCKED_DUMP),
                        "VR_SLOT_LOG": str(base / "slot.txt"), "VR_SLOT_DUMP": str(base / "slot")})
            _DUMPS[label] = base / "dumps"
            _SLOTS[label] = base
            if reverse:                                           # the attract's six pit scenes, then the second game; Task 5: a
                env["VR_END_COIN"] = str(PIT_SCENES)              # dump SELECT_DUMP_AFTER frames into each select screen
                env["VR_SELECT_DUMP_SELECT"] = str(SELECT_DUMP_AFTER)
            _drive_entry(base, out, romset_zip, METROPOLIS, c, seconds=430 if reverse else 200, reverse=reverse, extra_env=env)
        _RUNS[label] = _parse(log)
    return _RUNS[label]


def _after_load(run):
    return [l for l in run.lines if l.frame >= run.load]


def _race(run):
    """The first race's mode-0x14 lines (the reverse run's second game may race again, with the flag 0)."""
    lines = _after_load(run)
    end = next((k for k, l in enumerate(lines) if not 0x11 <= l.mode <= 0x14), len(lines))
    return [l for l in lines[:end] if l.mode == 0x14]


def _modes_after_finish(run):
    """The modes from the race's end to the first attract load (0x02), each once in order."""
    lines = _after_load(run)
    end = next(k for k, l in enumerate(lines) if not 0x11 <= l.mode <= 0x14)
    modes = []
    for l in lines[end:]:
        if not modes or modes[-1] != l.mode:
            modes.append(l.mode)
        if l.mode == 0x02:
            return tuple(modes)
    return tuple(modes)


def test_a_reverse_race_records_nothing(tmp_path_factory, romset_zip, saturn_cue):
    """Recon §8: a finished reverse race wrote Metropolis's table and entered the name. With `rankgate` nothing is written into
    the table from the race load on, the record flag stays 0, mode 0x1e never comes, and the modes after the finish are a race
    without a record's."""
    run = _run(tmp_path_factory, romset_zip, saturn_cue, "reverse")
    race = _race(run)
    assert race and all(l.flag == 1 for l in race), race[:3]                 # the loader served the variant
    assert run.writes == [], run.writes[:5]
    assert all(l.record == 0 for l in _after_load(run)), [l for l in _after_load(run) if l.record][:3]
    assert NAME_ENTRY not in {l.mode for l in run.lines}
    assert _modes_after_finish(run) == NO_RECORD, [hex(m) for m in _modes_after_finish(run)]


def test_a_normal_race_still_enters_the_name(tmp_path_factory, romset_zip, saturn_cue):
    """The same race in the normal direction: the table is written, the record flag set, and the name entry (mode 0x1e) comes."""
    run = _run(tmp_path_factory, romset_zip, saturn_cue, "normal")
    race = _race(run)
    assert race and all(l.flag == 0 for l in race), race[:3]
    assert run.writes and all(TABLE <= a < TABLE + TABLE_BYTES for _, _, a in run.writes)
    assert any(l.record & 1 for l in _after_load(run))
    assert _modes_after_finish(run) == RECORD, [hex(m) for m in _modes_after_finish(run)]


def test_the_flag_is_zero_whenever_a_select_screen_starts(tmp_path_factory, romset_zip, saturn_cue):
    """After the reverse race (the flag left at 1) the attract runs its pit scenes with the flag 0 on every frame, and after a
    coin and START the second game's select screen starts with the flag 0 (no Lua writes the flag) and keeps it 0 up to its
    course lock. Nobody answers that game (final review Minor 4): the course select's own countdown locks the course
    (SELECT_COUNTDOWN frames after its first frame, so not a gas edge), `dirsel` then runs until its own countdown lock COUNTDOWN
    frames after its first frame (as test_the_countdown_decides), the race loads LOCK_TO_LOAD frames after that lock, and the
    flag is 0 in that second race (the screen's countdown took NORMAL)."""
    run = _run(tmp_path_factory, romset_zip, saturn_cue, "reverse")
    lines = _after_load(run)
    attract = next(k for k, l in enumerate(lines) if l.mode == 0x02)
    assert lines[attract - 1].flag == 1, lines[attract - 1]                  # the race ended with the flag set
    assert run.coin is not None, "no coin: the run ended before the sixth pit scene"
    before = [l for l in lines[attract:] if l.frame < run.coin]
    scenes = sum(1 for a, b in zip(before, before[1:]) if b.mode == PIT_SCENE != a.mode)
    assert scenes >= PIT_SCENES, scenes
    assert all(l.flag == 0 for l in before if l.mode == PIT_SCENE), [l for l in before if l.mode == PIT_SCENE and l.flag][:3]
    second = [l for l in lines if l.frame > run.coin and l.mode == SELECT]
    assert second, "the second game's select screen did not start"
    assert second[0].flag == 0, second[0]
    choosing = [l for l in second[:next((k for k, l in enumerate(second) if l.handler not in (0, STATE0_HANDLER, 0xFC26C5)), len(second))]]
    assert all(l.flag == 0 for l in choosing), [l for l in choosing if l.flag][:3]
    game = [l for l in lines if l.frame > run.coin]
    course = _first(game, lambda l: l.mode == SELECT and l.handler == 0xFC26C5)
    course_lock = course and _first(game, lambda l: l.frame > course.frame and l.handler == COURSE_LOCK)
    first, lock, load = _phases(game)
    assert course and course_lock and first and lock and load, (course, course_lock, first, lock, load)
    print("SECOND GAME course select", course.frame, "course lock", course_lock.frame, "screen", first.frame, "lock", lock.frame, "load", load.frame)
    assert abs(course_lock.frame - course.frame - SELECT_COUNTDOWN) <= COUNTDOWN_SLACK, (course, course_lock)
    assert course_lock.frame < first.frame and lock.handler == COURSE_LOCK, (course_lock, first, lock)
    assert abs(lock.frame - first.frame - COUNTDOWN) <= COUNTDOWN_SLACK, (first, lock)
    assert load.frame - lock.frame == LOCK_TO_LOAD, (lock, load)
    race = [l for l in game if l.frame > load.frame and 0x12 <= l.mode <= 0x14]
    assert race and all(l.flag == 0 for l in race), race[:3]
    assert all(l.flag == 0 for l in game if l.frame <= load.frame), [l for l in game if l.flag and l.frame <= load.frame][:3]


def test_the_operator_fixed_course_never_sees_the_flag(tmp_path_factory, romset_zip, saturn_cue):
    """The operator's fixed course with the flag poked to 1 before the coin (no attract load runs between the coin and the
    select screen): the flag reads 0 from the first mode-0x10 frame, the select entity runs the SHIFT MODE SELECTOR's chain, never
    the course select's, and the race loads the normal record (the loader writes back 0)."""
    run = _run(tmp_path_factory, romset_zip, saturn_cue, "operator")
    assert any(l.flag == 1 and l.frame < 600 for l in run.lines)              # the poke took
    select = [l for l in run.lines if l.mode == SELECT]
    assert select and select[0].flag == 0, select[:2]
    assert all(l.flag == 0 for l in select), [l for l in select if l.flag][:3]
    handlers = {l.handler for l in select if l.handler}
    assert 0xFC29B3 in handlers and handlers <= SHIFT_CHAIN | {STATE0_HANDLER} and not handlers & COURSE_CHAIN, sorted(map(hex, handlers))
    race = _race(run)
    assert race and all(l.flag == 0 for l in race), race[:3]


def test_the_operator_fixed_course_never_shows_the_screen(tmp_path_factory, romset_zip, saturn_cue):
    """The operator's fixed course never reaches the course lock (recon §7 `fixed2`): as the test above, and the select entity's
    handler is never `dirsel`."""
    run = _run(tmp_path_factory, romset_zip, saturn_cue, "operator")
    select = [l for l in run.lines if l.mode == SELECT]
    handlers = {l.handler for l in select if l.handler}
    assert select and select[0].flag == 0 and all(l.flag == 0 for l in select), select[:2]
    assert 0xFC29B3 in handlers and directory_layout()["dirsel"] not in handlers, sorted(map(hex, handlers))
    race = _race(run)
    assert race and all(l.flag == 0 for l in race), race[:3]


# --- Task 2: the screen as behaviour ----------------------------------------------------------------------------------------
ALPINE, SURFERS_ROAD = 3, 9
SURFERS_ROAD_POINTS = 441       # its road points (test_reverse_build.COURSES): the normal race starts on the last, the reverse on 0
COURSE_LOCK = 0xFC277C          # the course select's lock handler; the direction lock hands the entity back to it
LOCKED = 0xFC27BE               # the handler after a lock (start, dirdone)
LOCK_TO_LOAD = 198              # video frames from a lock (the handler becoming COURSE_LOCK) to mode 0x11 (recon §1.1)
COUNTDOWN = 575                 # video frames from the screen's first frame (the timer 0x140) to its timer lock (recon §5 `proto_p2`)
COUNTDOWN_SLACK = 2
# video frames from the course select's first frame (the handler 0xfc26c5, the timer 0x27e) to the game's own timer lock at 0x20,
# one timer step per logic frame (recon §1.1): a course lock with no gas edge (Task 1's second game, nobody answering)
SELECT_COUNTDOWN = 2 * (0x27E - 0x20)
ANSWER_LOCK, ANSWER_LOAD = 1402, 1600   # autoplay's answer: the second press's edge at 1402, as the course press's before the screen
_SCREEN: dict[str, tuple] = {}
_WD: dict[str, object] = {}     # label -> the run's work directory (Task 3: its dumps and snapshots)


def _angle(a):
    return (a + 0x8000) % 0x10000 - 0x8000


def _screen(tmp_path_factory, romset_zip, saturn_cue, label, entry, reverse=False, env=None):
    """(dirscreen_log lines, start_log's (load, player, cars)) of 45 s of `entry` with the game's own inputs, made once per
    session per label; `{wd}` in an env value is the run's work directory (kept in _WD[label])."""
    if label not in _SCREEN:
        out, _ = _seven(romset_zip, saturn_cue)
        base = tmp_path_factory.mktemp(label)
        wd = base / f"entry{entry}"
        logs = {"VR_DIR_LOG": str(wd / "dir.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}", "VR_START_LOG": str(wd / "start.txt"),
                "VR_SNAPS": ""}
        _drive_entry(base, out, romset_zip, entry, None, seconds=45, autopilot=False, reverse=reverse,
                     extra_env={**logs, **{k: str(v).replace("{wd}", str(wd)) for k, v in (env or {}).items()}})
        _SCREEN[label] = (parse_dir_log(wd / "dir.txt"), parse_start_log(wd / "start.txt"))
        _WD[label] = wd
    return _SCREEN[label]


def _drive(steps):
    """dirscreen_drive.lua by hand (VR_DIR_ANSWER=0): steps = ((frame, gas, paddle), ...)."""
    return {"VR_DIR_ANSWER": "0", "VR_EXTRA_LUA": str(LUA_DIR / "dirscreen_drive.lua"),
            "VR_DIR_DRIVE": ",".join(f"{f}:{g}:{w}" for f, g, w in steps)}


def _first(lines, test):
    return next((l for l in lines if test(l)), None)


def _phases(lines):
    """(the screen's first line, its lock's line (the handler leaving `dirsel`), the first mode-0x11 line)."""
    dirsel = directory_layout()["dirsel"]
    first = _first(lines, lambda l: l.handler == dirsel)
    lock = first and _first(lines, lambda l: l.frame > first.frame and l.handler != dirsel)
    return first, lock, _first(lines, lambda l: l.mode == 0x11)


def _flags(lines):
    """(the flag on the last mode-0x10 line, the flags of the race's lines from mode 0x12 on)."""
    select = [l for l in lines if l.mode == SELECT]
    return select[-1].flag, {l.flag for l in lines if 0x12 <= l.mode <= 0x14}


def _green(start):
    """start_log's player sample at the first mode-0x14 frame."""
    load, player, _ = start
    assert load is not None
    return next(s for s in player if s.mode == 0x14)


@pytest.mark.parametrize("entry", [ALPINE, SURFERS_ROAD])
def test_wheel_right_and_a_second_press_race_in_reverse(tmp_path_factory, romset_zip, saturn_cue, entry):
    """autoplay.lua's answer with VR_DIRECTION=1 (the wheel left to 128, then right to 200, a second gas press): the screen's
    handler runs, the flag reads 1 on the last select-screen frame and through the race (the loader's write-back: the variant was
    served), and at the green the player stands on road point 0 facing the quads' turned direction (the reverse race's start
    pose, as stage 2's `test_reverse_alpine_starts_on_the_grid_facing_the_race`); on Surfers Road half a turn from the normal
    race's start."""
    lines, start = _screen(tmp_path_factory, romset_zip, saturn_cue, f"reverse{entry}", entry, reverse=True)
    first, lock, load = _phases(lines)
    assert first and lock and load, (first, lock, load)
    last, race = _flags(lines)
    assert last == 1 and race == {1}, (last, race)
    g = _green(start)
    print("REVERSE", entry, "screen", first.frame, "lock", lock.frame, "load", load.frame, "green", tuple(g))
    assert g.flag == 1 and g.road_point == 0 and abs(_angle(g.yaw - g.attr)) < 0x400, (g, hex(g.yaw & 0xFFFF), hex(g.attr))
    if entry == SURFERS_ROAD:
        n = _green(_screen(tmp_path_factory, romset_zip, saturn_cue, "normal9", SURFERS_ROAD)[1])
        assert abs(_angle(g.yaw - n.yaw)) > 0x6000, (hex(g.yaw & 0xFFFF), hex(n.yaw & 0xFFFF))


def test_wheel_straight_and_a_second_press_race_normally(tmp_path_factory, romset_zip, saturn_cue):
    """autoplay.lua's answer without VR_DIRECTION (the wheel at 128, a second gas press) on Surfers Road: the screen runs, the
    flag reads 0 on the last select-screen frame and through the race, and the player starts as in the normal race, on the
    normal line's last road point (behind the line) facing its quads as authored."""
    lines, start = _screen(tmp_path_factory, romset_zip, saturn_cue, "normal9", SURFERS_ROAD)
    first, lock, load = _phases(lines)
    assert first and lock and load, (first, lock, load)
    last, race = _flags(lines)
    assert last == 0 and race == {0}, (last, race)
    g = _green(start)
    assert g.flag == 0 and g.road_point == SURFERS_ROAD_POINTS - 1 and abs(_angle(g.yaw - g.attr)) < 0x400, (g, hex(g.yaw & 0xFFFF), hex(g.attr))


def test_the_countdown_decides(tmp_path_factory, romset_zip, saturn_cue):
    """Review Focus 2 (plan D6): Surfers Road is chosen with the wheel right of the threshold. The gas pressed at 1400 locks the
    course, then is lifted on the screen and never pressed again; with the wheel left where it chose the course the countdown
    locks the screen COUNTDOWN frames after its first frame with NORMAL; with the wheel at 128, then 200, with REVERSE."""
    seen = {}
    for label, steps in (("count_none", ((1410, 0, WHEEL_FOR_ENTRY[SURFERS_ROAD]),)), ("count_steer", ((1410, 0, 128), (1500, 0, 200)))):
        lines, _ = _screen(tmp_path_factory, romset_zip, saturn_cue, label, SURFERS_ROAD, env=_drive(steps))
        first, lock, load = _phases(lines)
        assert first and lock and load, (label, first, lock, load)
        seen[label] = (lock.frame - first.frame, _flags(lines))
        print("COUNTDOWN", label, "screen", first.frame, "lock", lock.frame, "load", load.frame, seen[label])
        assert abs(lock.frame - first.frame - COUNTDOWN) <= COUNTDOWN_SLACK, (label, first, lock)
        assert not any(l.edge for l in lines if first.frame <= l.frame <= lock.frame), label
    assert seen["count_none"][1] == (0, {0}) and seen["count_steer"][1] == (1, {1}), seen


def test_the_course_press_does_not_confirm(tmp_path_factory, romset_zip, saturn_cue):
    """Review Focus 1: the gas floored at 1400 and held (VR_DIR_ANSWER=0, nobody answers): the course press's edge locks the
    course, and the screen waits for its countdown (no lock before COUNTDOWN - COUNTDOWN_SLACK frames after its first frame,
    no edge while it runs), then races in the normal direction."""
    lines, _ = _screen(tmp_path_factory, romset_zip, saturn_cue, "held9", SURFERS_ROAD, env={"VR_DIR_ANSWER": "0"})
    first, lock, load = _phases(lines)
    assert first and lock and load, (first, lock, load)
    print("HELD screen", first.frame, "lock", lock.frame, "load", load.frame)
    assert any(l.edge for l in lines if l.frame < first.frame and l.handler in (0xFC26C5, COURSE_LOCK))       # the course press
    assert lock.frame - first.frame >= COUNTDOWN - COUNTDOWN_SLACK, (first, lock)
    assert not any(l.edge for l in lines if first.frame <= l.frame <= lock.frame)
    assert _flags(lines) == (0, {0})


@pytest.mark.parametrize("entry", [0, 1, 2])
def test_an_original_never_shows_the_screen(tmp_path_factory, romset_zip, saturn_cue, entry):
    """An original (no reverse variant): the select entity's handler is never `dirsel`, the course lock (the handler
    COURSE_LOCK) reaches mode 0x11 in the game's LOCK_TO_LOAD frames, and the flag is 0 on the select screen and in the race."""
    lines, _ = _screen(tmp_path_factory, romset_zip, saturn_cue, f"orig{entry}", entry)
    assert directory_layout()["dirsel"] not in {l.handler for l in lines}
    lock, load = _first(lines, lambda l: l.handler == COURSE_LOCK), _first(lines, lambda l: l.mode == 0x11)
    assert lock and load and load.frame - lock.frame == LOCK_TO_LOAD, (lock, load)
    assert all(l.flag == 0 for l in lines if l.mode == SELECT) and _flags(lines)[1] == {0}


def test_the_transmission_survives_the_screen(tmp_path_factory, romset_zip, saturn_cue):
    """Review Focus 4: START held with the course's gas press (VR_MANUAL=1) latches the manual transmission in 0x501936 at the
    course lock; the screen does not read START again. In the manual run START is released on the screen (VR_DIR_START_OFF=1:
    from the lift after the early press to the race load; the D log's START bit reads 0 there, so a re-latch would show) and
    0x501936 is still 1 at the race load; without VR_MANUAL it is 0 at the course lock and at the load."""
    for label, env, want in (("manual9", {"VR_MANUAL": "1", "VR_DIR_START_OFF": "1"}, 1), ("normal9", None, 0)):
        lines, _ = _screen(tmp_path_factory, romset_zip, saturn_cue, label, SURFERS_ROAD, env=env)
        first, lock, load = _phases(lines)
        course = _first(lines, lambda l: l.handler == COURSE_LOCK)
        assert first and lock and course and load and course.frame < first.frame, (label, course, first, load)
        assert course.manual == load.manual == want, (label, course, load)
        if want:
            on_screen = [l for l in lines if first.frame <= l.frame < load.frame]
            assert course.start == 1, course                                  # START held at the course lock ...
            released = [l for l in on_screen if l.start == 0]
            assert released and released[0].frame < lock.frame, on_screen[:3]  # ... released while the screen chooses
            assert all(l.start == 0 for l in on_screen if l.frame >= released[0].frame), [l for l in on_screen if l.start][:3]


def test_the_lock_to_load_timing_is_the_games(tmp_path_factory, romset_zip, saturn_cue):
    """The direction lock hands the entity to the game's lock handler, so it reaches mode 0x11 in the course lock's LOCK_TO_LOAD
    frames (0xfc277c's timer 0x20 on the next logic frame, state 1, state 6). autoplay.lua's answer locks on frame ANSWER_LOCK,
    the course select's lock frame before the screen, so the race loads on ANSWER_LOAD as it did (plan D14)."""
    lines, _ = _screen(tmp_path_factory, romset_zip, saturn_cue, f"reverse{SURFERS_ROAD}", SURFERS_ROAD, reverse=True)
    first, lock, load = _phases(lines)
    assert lock.handler == COURSE_LOCK and lock.phase == 2, lock
    assert _first(lines, lambda l: l.frame > lock.frame and l.handler != COURSE_LOCK).handler == LOCKED
    assert load.frame - lock.frame == LOCK_TO_LOAD, (lock, load)
    assert (lock.frame, load.frame) == (ANSWER_LOCK, ANSWER_LOAD), (lock, load)


# --- Task 3: the screen drawn ---------------------------------------------------------------------------------------------
# autoplay.lua's answer opens the screen at the same frames on every run: `dirlock` installs `dirsel` at 1204 (the first log line
# with that handler) and `dirsel`'s first run shows at the end of DIRSEL_FIRST (DIR_SHOWN leaves 0xff: the first drawing phase;
# measured, the logic's writes show at the frame end after the counter's step); the screen's 20th frame (video frames counted from
# that one) is dumped (select_dump.lua) and the frame is snapshot on NORMAL (the paddle at 128, armed) and on REVERSE (200 from
# 1300) over eight frames each: the frame blinks four frames on, four off while choosing.
DIRSEL_FIRST = 1207
TWENTIETH = DIRSEL_FIRST + 19
LATE = 1390                                 # a dump just before the answer's lock (1402): the countdown has been reprinted ~90 times
SNAPS = {0: range(1250, 1258), 1: range(1370, 1378)}       # per choice (NORMAL, REVERSE) eight consecutive snapshot frames
# Task 4: after autoplay's lock (ANSWER_LOCK) eight more consecutive snapshots, and a dump 60 frames on (the race loads at 1600)
LOCKED_SNAPS = range(ANSWER_LOCK + 38, ANSWER_LOCK + 46)
LOCKED_DUMP = ANSWER_LOCK + 60
CHECKER_MAP = 0x1E0C18                      # the map layer 2's checker 0xfc358e blits (dirscreen.CHECKER; recon §2.2)
BLANK = 0x8020
GAME_MARK = {(2, 59)}                       # a layer-0 cell (0xa780) the game draws on every screen, from the attract on; it is back
                                            # after the screen's clear (not the course select's)


def _snap_frames():
    return sorted([f for r in SNAPS.values() for f in r] + list(LOCKED_SNAPS))


def _draw_env():
    return {"VR_SELECT_DIR": "{wd}", "VR_SELECT_DUMP": f"{TWENTIETH},{LATE},{LOCKED_DUMP}", "VR_SNAPS": ",".join(map(str, _snap_frames())),
            "VR_SNAPS_AFTER_START": ""}


def _drawn(tmp_path_factory, romset_zip, saturn_cue, entry, label=None, env=None, reverse=None):
    """The dir log and work directory of `entry` answered REVERSE (NORMAL shown first, then REVERSE; by default when `env` is not
    given) or NORMAL, with the dumps and snapshots of _draw_env; DIRSEL_FIRST checked against the log, so the dumped frame is
    the screen's 20th."""
    label = label or f"draw{entry}"
    reverse = env is None if reverse is None else reverse
    lines, _ = _screen(tmp_path_factory, romset_zip, saturn_cue, label, entry, reverse=reverse, env={**_draw_env(), **(env or {})})
    dirsel = directory_layout()["dirsel"]
    first = _first(lines, lambda l: l.handler == dirsel)
    run = first and _first(lines, lambda l: l.frame > first.frame and l.shown != 0xFF)
    assert run and run.frame == DIRSEL_FIRST, (first, run)
    return lines, _WD[label]


def _dump(wd, frame, entry):
    return tuple((wd / f"{frame}_{entry}_{k}.bin").read_bytes() for k in ("tile", "char", "pal"))


def _title_font(wd, frame, entry):
    """(character base, attribute) of the countdown font's printer 0xff870d at a dumped frame: [0x501438] << 7 (`sha.h #7`) and
    [0x50143c], read by select_dump.lua (the work file)."""
    shift, attr = struct.unpack("<2I", (wd / f"{frame}_{entry}_work.bin").read_bytes())
    return (shift << 7) & 0xFFFF, attr


def _shown_at(lines, frame):
    """DIR_SHOWN at the end of `frame` (the log's last line at or before it)."""
    return [l for l in lines if l.frame <= frame][-1].shown


def _cell(tile, layer, row, col):
    from vrtools.arcade.dirscreen import tile_address
    return struct.unpack_from("<H", tile, tile_address(layer, row, col) - 0x700000)[0]


def _label(out, k, attr):
    """{(row, col): tile word} of label k (0 NORMAL, 1 REVERSE) printed by 0xffe8fb with `attr`: attr | the glyph table 0x2f2456's
    six bytes a letter, 2 x 3 tiles."""
    from vrtools.arcade.dirscreen import LABEL_CELLS, LABELS
    (r, c), want = LABEL_CELLS[k], {}
    for n, ch in enumerate(LABELS[k]):
        g = out.program[0x2F2456 - 0x200000 + 6 * (ord(ch) & 0x3F):][:6]
        want.update({(r + i, c + 2 * n + j): attr | g[2 * i + j] for i in range(3) for j in range(2)})
    return want


def _block(out):
    """The built set's direction-screen block (tencourse.dirscreen_block): {part: bytes} for dirgfx.block_image's parts, the
    characters cut to their counts (dirgfx.arrow, caption) and each map whole, read from the set's program ROM."""
    from vrtools.arcade import dirgfx
    from vrtools.arcade.tencourse import dirscreen_block
    lo, hi = dirscreen_block()
    _, at = dirgfx.block_image(lo)
    n = {"cw_chars": 32 * len(dirgfx.arrow(True)[1]), "ccw_chars": 32 * len(dirgfx.arrow(False)[1]), "caption_chars": 32 * len(dirgfx.caption()[1]),
         "white": 32, "red": 32, "cw_map": 300, "ccw_map": 300, "caption_map": 84}
    return {k: out.program[at[k] - 0x200000:at[k] - 0x200000 + v] for k, v in n.items()}


def _map_words(blob):
    """{(row, col): tile word} of a map in 0xff9436's format (mode 1), relative to its first cell."""
    base, mode, rows, cols = struct.unpack_from("<HHII", blob)
    assert mode == 1
    tiles = struct.unpack_from(f"<{rows * cols}H", blob, 12)
    return {(i, j): (base + tiles[i * cols + j]) & 0xFFFF for i in range(rows) for j in range(cols)}


def _anticlockwise(out, entry):
    """The entry's lap sense as `dirdraw` reads it: its load record's map_cross (dirscreen.SENSE_FIELD) non-zero."""
    from vrtools.arcade.directory import decode_directory
    return decode_directory(out)[entry].map_cross != 0


def _block_pieces(out, entry):
    """{(row, col): tile word} of Task 5's layer-0 cells, from the built set's block: the caption's map at CAPTION_CELL (over the
    wheel panel's SELECT COURSE lettering) and the two arrows' maps (12 x 12, the blank 0x8020 in their empty cells): at
    ARROW_CELLS[0] (NORMAL) the anticlockwise arrow's when the entry's lap is anticlockwise, else the clockwise one's, at
    ARROW_CELLS[1] the other."""
    from vrtools.arcade.dirscreen import ARROW_CELLS, CAPTION_CELL
    blk = _block(out)
    ccw = _anticlockwise(out, entry)
    want = {}
    for key, (r, c) in (("caption_map", CAPTION_CELL), ("ccw_map" if ccw else "cw_map", ARROW_CELLS[0]), ("cw_map" if ccw else "ccw_map", ARROW_CELLS[1])):
        want.update({(r + i, c + j): w for (i, j), w in _map_words(blk[key]).items()})
    return want


def _layer0_pieces(out, font, shown, entry):
    """{(row, col): tile word} of every layer-0 cell Tasks 3-5 draw, from the built set: the four maps (each tile its map's base
    plus its index, as 0xff9436 writes it), the title (0xff870d: (letter - 0x20) * 6 + base | attribute, 2 x 3 a letter; `font`
    = (base, attribute) read in the run, _title_font), the two labels (_label: LABEL_YELLOW for the label of the choice
    `shown`, LABEL_WHITE for the other; both white when `shown` is neither, while drawing), and over them Task 5's caption and
    arrows for `entry` (_block_pieces)."""
    from vrtools.arcade.dirscreen import LABEL_WHITE, LABEL_YELLOW, MAPS, TITLE, TITLE_CELL
    from vrtools.arcade.panel import decode_panel
    want = {}
    for m, (r, c), (h, w) in MAPS:
        p = decode_panel(out, m)
        assert (p.rows, p.cols) == (h, w)
        want.update({(r + i, c + j): (p.base + p.tiles[i * w + j]) & 0xFFFF for i in range(h) for j in range(w)})
    r, c = TITLE_CELL
    base, attr = font
    for k, ch in enumerate(TITLE):
        t = ((ord(ch) - 0x20) * 6 + base) | attr
        want.update({(r + i, c + 2 * k + j): t + 2 * i + j for i in range(3) for j in range(2)})
    for k in (0, 1):
        want.update(_label(out, k, LABEL_YELLOW if k == shown else LABEL_WHITE))
    want.update(_block_pieces(out, entry))
    return want


def test_the_checker_routine_blits_the_checker_map(romset_zip):
    """CHECKER_MAP is the map the game's checker routine (dirscreen.CHECKER, 0xfc358e) blits: up to its `rsr` it loads that one
    map address into R0 and calls the blit 0xff9436 with it, no other map."""
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.dirscreen import CHECKER
    from vrtools.arcade.romset import RomSet
    lines = listing(RomSet.from_zip(romset_zip), CHECKER, 0x40)
    body = [l.text for l in lines[:next(k for k, l in enumerate(lines) if l.text == "rsr") + 1]]
    loads = [k for k, t in enumerate(body) if t.endswith(", R0")]
    assert CHECKER == 0xFC358E and [body[k] for k in loads] == [f"mov.w   #{CHECKER_MAP:X}, R0"], body
    assert body[loads[0] + 1] == "jsr     FF9436[PC]" and sum(t.startswith("jsr") for t in body) == 1, body


def _checker_chars(out):
    """The characters of layer 2's checker: its map's (CHECKER_MAP, decoded from the built set) base plus each index."""
    from vrtools.arcade.panel import decode_panel
    p = decode_panel(out, CHECKER_MAP)
    assert p.base & 0x8000 == 0, hex(p.base)                    # the checker's tile words have bit 15 clear
    return {(p.base + t) & 0xFFFF for t in p.tiles}


def _countdown(setting_zero):
    """The game's countdown cells (rows 3 x columns 4 from 0x7013b8, or 0x701438 when [0x40dc9b] = 0; recon §1.1)."""
    r = 40 if setting_zero else 39
    return {(r + i, 28 + j) for i in range(3) for j in range(4)}


@pytest.mark.parametrize("entry", [ALPINE, SURFERS_ROAD])
def test_the_screen_shows_the_picked_course_twice(tmp_path_factory, romset_zip, saturn_cue, entry):
    """At the screen's 20th frame: layer 2 holds the chosen entry's picture twice, at PICTURE_CELLS[0] with slot 0's tile words
    and at PICTURE_CELLS[1] with slot 2's (0x8000 | SLOT_CHAR + the picture map's index, in the map's order), slot 0's and slot
    2's character blocks hold the record's characters and their palettes its normal set, and every other visible layer-2 cell is
    the checker (bit 15 clear, its map's characters: no slot overlay left). Layer 0 holds the four maps, the title and the
    labels (the shown choice's yellow, Task 4) where Step 2 puts them, Task 5's caption and arrows, the countdown's cells, and nothing else (every other visible cell the blank 0x8020: no cell of
    the course select, its pictures, BEGINNER / MEDIUM / EXPERT, AUTOMATIC row and bottom bar, rows 23-28 and 43-46)."""
    from vrtools.arcade.dirscreen import PICTURE_CELLS
    from vrtools.arcade.select import SLOT_CHAR, SLOT_PAL
    from tests.test_tencourse import _records
    lines, wd = _drawn(tmp_path_factory, romset_zip, saturn_cue, entry)
    out, _ = _seven(romset_zip, saturn_cue)
    _, recs, read = _records(out)
    rec = recs[entry]
    m = struct.unpack("<336H", read(rec.map_addr, 672))
    n = [rec.counts & 0xFF, rec.counts >> 8 & 0xFF, rec.counts >> 16 & 0xFF]
    chars = read(rec.chars_addr, 32 * sum(n))
    tile, char, pal = _dump(wd, TWENTIETH, entry)
    pictures = set()
    for slot, (r, c) in zip((0, 2), PICTURE_CELLS):
        got = [_cell(tile, 2, r + i, c + j) for i in range(21) for j in range(16)]
        assert got == [(0x8000 | SLOT_CHAR[slot]) + v for v in m], (entry, slot)
        pictures |= {(r + i, c + j) for i in range(21) for j in range(16)}
        for p in range(3):
            at = 32 * (SLOT_CHAR[slot] + 128 * p)
            assert char[at:at + 32 * n[p]] == chars[32 * sum(n[:p]):32 * sum(n[:p + 1])], (entry, slot, p)
        assert pal[SLOT_PAL[slot] - 0x900000:][:96] == read(rec.normal_addr, 96), (entry, slot)
    chars = _checker_chars(out)
    checker = [(r, c) for r in range(48) for c in range(62) if (r, c) not in pictures and _cell(tile, 2, r, c) not in chars]
    assert not checker, [(rc, hex(_cell(tile, 2, *rc))) for rc in checker[:8]]
    assert _shown_at(lines, TWENTIETH) == 0
    want = _layer0_pieces(out, _title_font(wd, TWENTIETH, entry), 0, entry)
    wrong = [(rc, hex(_cell(tile, 0, *rc)), hex(w)) for rc, w in want.items() if _cell(tile, 0, *rc) != w]
    assert not wrong, wrong[:8]
    count = _countdown(False)
    assert any(_cell(tile, 0, *rc) != BLANK for rc in count)
    stray = [(r, c) for r in range(48) for c in range(62) if (r, c) not in want and (r, c) not in count and _cell(tile, 0, r, c) != BLANK]
    attract = _dump(wd, 600, 0)[0]                              # before the coin: what the game draws on every screen
    kept = {rc for rc in stray if _cell(tile, 0, *rc) == _cell(attract, 0, *rc)}
    assert kept <= GAME_MARK, sorted(kept)                      # (the game's own mark, back after the clear)
    stray = [rc for rc in stray if rc not in kept]
    assert not stray, [(rc, hex(_cell(tile, 0, *rc))) for rc in stray[:8]]


def _snaps(wd, frames):
    """The snapshots of `frames` (of _snap_frames) as an (n, h, w, 3) int array. MAME numbers them in frame order
    (snap/vr/NNNN.png); the run's VR_SNAPS frames are the first files and MAME's own snapshot at -str's end the last, so the
    count is checked: a missing or extra snapshot fails here instead of shifting every frame by one."""
    import numpy as np
    from PIL import Image
    all_frames = _snap_frames()
    files = sorted((wd / "snap" / "vr").glob("*.png"))
    assert len(files) == len(all_frames) + 1, (len(files), len(all_frames))
    return np.stack([np.asarray(Image.open(files[all_frames.index(f)]).convert("RGB")).astype(int) for f in frames])


def _blinking(st):
    """The pixels above the panels (y < 240: the countdown below changes too) not the same in all snapshots of `st`."""
    moving = (st.max(0) - st.min(0)).sum(2) > 0
    moving[240:] = False
    return moving


def _frame_box(wd, choice):
    """The cursor frame's bounding box (x0, y0, x1, y1), pixels inclusive, in the eight snapshots of SNAPS[choice]: the pixels
    that blink (_blinking), the frame being on in four and off in the other four."""
    import numpy as np
    moving = _blinking(_snaps(wd, SNAPS[choice]))
    ys, xs = np.nonzero(moving)
    assert len(xs) > 200, len(xs)                              # the frame showed (four of the eight frames)
    return xs.min(), ys.min(), xs.max(), ys.max()


@pytest.mark.parametrize("entry", [ALPINE, SURFERS_ROAD])
def test_the_frame_sits_round_the_chosen_picture(tmp_path_factory, romset_zip, saturn_cue, entry):
    """In the snapshots the yellow cursor frame (the game's course cursor at dirscreen.SIDE_X[choice], SIDE_Y) is centred on the
    chosen picture's rectangle (PICTURE_CELLS, 16 x 21 tiles of 8 px) within 2 px on each axis, on NORMAL and on REVERSE, and
    surrounds it."""
    from vrtools.arcade.dirscreen import PICTURE_CELLS
    lines, wd = _drawn(tmp_path_factory, romset_zip, saturn_cue, entry)
    for choice in (0, 1):
        shown = {l.shown for l in lines if min(SNAPS[choice]) - 2 <= l.frame <= max(SNAPS[choice])}
        assert shown == {choice}, (choice, shown)
        r, c = PICTURE_CELLS[choice]
        px0, py0, px1, py1 = 8 * c, 8 * r, 8 * (c + 16) - 1, 8 * (r + 21) - 1
        x0, y0, x1, y1 = _frame_box(wd, choice)
        print("FRAME", entry, choice, (x0, y0, x1, y1), "picture", (px0, py0, px1, py1))
        assert abs((x0 + x1) - (px0 + px1)) <= 4 and abs((y0 + y1) - (py0 + py1)) <= 4, (choice, (x0, y0, x1, y1), (px0, py0, px1, py1))
        assert x0 < px0 and y0 < py0 and x1 > px1 and y1 > py1, (choice, (x0, y0, x1, y1))


@pytest.mark.parametrize("entry", [ALPINE, SURFERS_ROAD])
def test_drawing_the_screen_skips_no_logic_frame(tmp_path_factory, romset_zip, saturn_cue, entry):
    """Step 4: from the course lock (the handler COURSE_LOCK) to the direction lock, through the screen's drawing phases (DIR_SHOWN
    0xff down to DRAWN), the game's logic frame counter [0x501144] rises by one every two video frames, never more slowly: no
    logic frame is lost while the screen draws."""
    from vrtools.arcade.dirscreen import DRAW_PHASES, DRAWN
    lines, _ = _drawn(tmp_path_factory, romset_zip, saturn_cue, entry)
    first, lock, _ = _phases(lines)
    course = _first(lines, lambda l: l.handler == COURSE_LOCK)
    assert course and lock and course.frame < first.frame, (course, first, lock)
    window = [l for l in lines if course.frame <= l.frame <= lock.frame]
    assert {l.shown for l in window} >= set(DRAW_PHASES) | {DRAWN, 0, 1}, sorted({l.shown for l in window})
    _every_logic_frame(window, entry, course.frame, lock.frame)


def _every_logic_frame(window, tag, a, b):
    """The logic frame counter's steps over the log lines `window` (frames a..b): one every two video frames, each by one."""
    steps, prev = [], None
    for l in window:
        if prev is None or l.counter != prev.counter:
            if prev is not None:
                steps.append((l.frame, l.frame - prev.frame, l.counter - prev.counter))
            prev = l
    print("STEPS", tag, len(steps), "from", a, "to", b)
    assert len(steps) >= (b - a) // 2 - 1, (len(steps), a, b)
    assert all(df == 2 and dc == 1 for _, df, dc in steps), [s for s in steps if s[1:] != (2, 1)][:6]


def test_the_screen_is_sound_with_the_other_select_setting(tmp_path_factory, romset_zip, saturn_cue):
    """Review Focus 5: with the operator's select-screen setting [0x40dc9b] = 0 (VR_POKE before the coin) the game prints the
    countdown from 0x701438 (rows 40-42, recon §1.1), which shows the setting held to the screen: those cells are the countdown's
    and row 39's are blank, and none of them is a piece of the screen (static: test_dirscreen's layout); at the 20th frame and
    just before the lock every piece's cells still hold their tile words (a countdown printed over one would show). The screen
    locks (autoplay's answer, NORMAL) and the race loads LOCK_TO_LOAD frames later."""
    lines, wd = _drawn(tmp_path_factory, romset_zip, saturn_cue, SURFERS_ROAD, label="setting0", env={"VR_POKE": "40dc9b=0"})
    out, _ = _seven(romset_zip, saturn_cue)
    count = _countdown(True)
    for frame in (TWENTIETH, LATE):
        want = _layer0_pieces(out, _title_font(wd, frame, SURFERS_ROAD), _shown_at(lines, frame), SURFERS_ROAD)
        assert not count & set(want)
        tile = _dump(wd, frame, SURFERS_ROAD)[0]
        assert any(_cell(tile, 0, *rc) != BLANK for rc in count), frame
        assert all(_cell(tile, 0, 39, 28 + j) == BLANK for j in range(4)), frame
        wrong = [(rc, hex(_cell(tile, 0, *rc)), hex(w)) for rc, w in want.items() if _cell(tile, 0, *rc) != w]
        assert not wrong, (frame, wrong[:8])
    first, lock, load = _phases(lines)
    assert first and lock and load and load.frame - lock.frame == LOCK_TO_LOAD, (first, lock, load)
    assert _flags(lines) == (0, {0})


# --- Task 4: the choice shown, and the lock look ----------------------------------------------------------------------------
WHEEL_STEPS = ((1410, 0, 128), (1500, 0, 200), (1600, 0, 128))     # dirscreen_drive: NORMAL (armed), REVERSE, NORMAL again
WHEEL_DUMPS = (1490, 1590, 1690)                                    # one dump at the end of each step (the countdown locks ~1980)
LOCK_RUNS = [(ALPINE, True), (SURFERS_ROAD, False), (SURFERS_ROAD, True)]


def test_the_labels_follow_the_wheel(tmp_path_factory, romset_zip, saturn_cue):
    """Plan D4: Surfers Road, the course pressed at 1400, then by hand (VR_DIR_ANSWER=0, dirscreen_drive.lua) the gas lifted and
    the wheel at 128 (NORMAL, armed), at 200 (REVERSE) from 1500, at 128 again from 1600. At the end of each step the log's
    DIR_SHOWN is the step's choice and the label cells (tile dumps) hold the current choice's label in LABEL_YELLOW and the other
    in LABEL_WHITE, glyph bytes and all: the attributes swap when the wheel crosses the threshold, both ways."""
    from vrtools.arcade.dirscreen import LABEL_WHITE, LABEL_YELLOW
    env = {**_drive(WHEEL_STEPS), "VR_SELECT_DIR": "{wd}", "VR_SELECT_DUMP": ",".join(map(str, WHEEL_DUMPS))}
    lines, _ = _screen(tmp_path_factory, romset_zip, saturn_cue, "wheel9", SURFERS_ROAD, env=env)
    wd = _WD["wheel9"]
    out, _ = _seven(romset_zip, saturn_cue)
    first, lock, _ = _phases(lines)
    assert first and lock and first.frame < WHEEL_STEPS[0][0] and lock.frame > WHEEL_DUMPS[-1], (first, lock)
    for frame, choice in zip(WHEEL_DUMPS, (0, 1, 0)):
        assert _shown_at(lines, frame) == choice, (frame, choice)
        tile = _dump(wd, frame, SURFERS_ROAD)[0]
        for k in (0, 1):
            attr = LABEL_YELLOW if k == choice else LABEL_WHITE
            wrong = [(rc, hex(_cell(tile, 0, *rc)), hex(w)) for rc, w in _label(out, k, attr).items() if _cell(tile, 0, *rc) != w]
            assert not wrong, (frame, k, wrong[:6])


def _locked(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """The draw run of `entry` answered REVERSE (Task 3's) or NORMAL, its lock checked on ANSWER_LOCK with the choice."""
    label = f"draw{entry}" if reverse else f"drawnormal{entry}"
    lines, wd = _drawn(tmp_path_factory, romset_zip, saturn_cue, entry, label=label, reverse=reverse)
    first, lock, load = _phases(lines)
    assert lock and load and lock.frame == ANSWER_LOCK and lock.flag == int(reverse) and load.frame == ANSWER_LOAD, (lock, load)
    return lines, wd, lock, load


@pytest.mark.parametrize("entry,reverse", LOCK_RUNS)
def test_the_lock_keeps_the_chosen_picture_in_colour(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """LOCKED_DUMP frames (60) after the direction lock: palette RAM's 48 words of the chosen side's slot (slot 0 NORMAL, slot 2
    REVERSE) are the picture record's `chosen` set, the other side's its `grey` set (the two differ), on Alpine REVERSE and on
    Surfers Road both ways. (In place of the converted-entry case of test_race_build's `test_start_greys_the_other_courses`,
    retired in Task 2: a converted course's START look is the direction screen's.)"""
    from vrtools.arcade.select import SLOT_PAL
    from tests.test_tencourse import _records
    lines, wd, lock, load = _locked(tmp_path_factory, romset_zip, saturn_cue, entry, reverse)
    out, _ = _seven(romset_zip, saturn_cue)
    _, recs, read = _records(out)
    rec = recs[entry]
    chosen, grey = read(rec.chosen_addr, 96), read(rec.grey_addr, 96)
    assert chosen != grey
    assert _shown_at(lines, LOCKED_DUMP) == int(reverse)
    pal = _dump(wd, LOCKED_DUMP, entry)[2]
    sides = [pal[SLOT_PAL[slot] - 0x900000:][:96] for slot in (0, 2)]
    assert sides[int(reverse)] == chosen, (entry, reverse)
    assert sides[1 - int(reverse)] == grey, (entry, reverse)


@pytest.mark.parametrize("entry,reverse", LOCK_RUNS)
def test_the_frame_is_steady_after_the_lock(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """The cursor frame blinks while choosing and is steady after the lock (the game's cursor code, the handler 0xfc27be): the
    pixels that blink in the eight snapshots of SNAPS[choice] (_blinking) take two looks there, on (the frame, the yellower) and
    off; in the eight consecutive LOCKED_SNAPS after the lock every one of those pixels is as in the on look."""
    import numpy as np
    lines, wd, lock, load = _locked(tmp_path_factory, romset_zip, saturn_cue, entry, reverse)
    choice = int(reverse)
    assert {l.shown for l in lines if min(SNAPS[choice]) - 2 <= l.frame <= max(SNAPS[choice])} == {choice}
    assert lock.frame < min(LOCKED_SNAPS) and max(LOCKED_SNAPS) < load.frame
    before, after = _snaps(wd, SNAPS[choice]), _snaps(wd, LOCKED_SNAPS)
    mask = _blinking(before)
    assert mask.sum() > 200, mask.sum()
    looks = {}
    for img in before:
        looks.setdefault(img[mask].tobytes(), img[mask])
    assert len(looks) == 2, len(looks)                        # on and off, nothing else blinks above the panels
    yellow = lambda px: (px[:, 0] + px[:, 1] - 2 * px[:, 2]).mean()
    on = max(looks.values(), key=yellow)
    frame = on[(on[:, 0] - on[:, 2] > 60) & (on[:, 1] - on[:, 2] > 60)]       # the on look is the yellow frame: most of its
    assert len(frame) > 0.6 * len(on), (len(frame), len(on))                  # pixels have red and green well above blue
    assert frame[:, 0].mean() > 200 and frame[:, 1].mean() > 160 and frame[:, 2].mean() < 100, frame.mean(0)
    print("STEADY", entry, reverse, int(mask.sum()), [int((img[mask] == on).all(1).sum()) for img in before],
          [int((img[mask] == on).all(1).sum()) for img in after])
    assert all((img[mask] == on).all() for img in after), [int((img[mask] != on).any(1).sum()) for img in after]


@pytest.mark.parametrize("entry,reverse", LOCK_RUNS)
def test_the_lock_look_skips_no_logic_frame(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """From the direction lock to the race load (mode 0x11), while `dirdone` re-colours the two slots every logic frame, the
    logic frame counter rises by one every two video frames, never more slowly."""
    lines, wd, lock, load = _locked(tmp_path_factory, romset_zip, saturn_cue, entry, reverse)
    _every_logic_frame([l for l in lines if lock.frame <= l.frame <= load.frame], (entry, reverse), lock.frame, load.frame)


# --- Task 5: the arrows and the SELECT DIRECTION caption ---------------------------------------------------------------------
def _ram_block(char, block, n):
    """n characters of character RAM from character `block` on (a select_dump char file)."""
    return char[32 * block:32 * block + 32 * n]


def _pal(pal, palette):
    """The 16 colours of `palette` in a select_dump palette file (32 bytes)."""
    return pal[32 * palette:32 * palette + 32]


@pytest.mark.parametrize("entry", [ALPINE, SURFERS_ROAD])
def test_the_arrows_show_each_direction(tmp_path_factory, romset_zip, saturn_cue, entry):
    """Alpine's lap is anticlockwise, Surfers Road's clockwise (the load record's map_cross, which `dirdraw` reads, agrees with the
    centreline's signed area, tencourse.interior_on_the_left). At the screen's 20th frame (NORMAL shown) and just before the lock
    (LATE, REVERSE shown): layer 0's 12 x 12 cells at ARROW_CELLS[0] (NORMAL) are the map of the arrow of the entry's own lap, their
    characters in that arrow's block (clockwise 0x3480, anticlockwise 0x3500), and at ARROW_CELLS[1] the other arrow's, in the
    other block; character RAM at 0x3480 and 0x3500 holds the built set's block characters of the clockwise and anticlockwise
    arrows; the palette of the NORMAL side's block (0x69 for 0x3480, 0x6a for 0x3500) is the block's white set and the other's
    the red set (plan D8). LOCKED_DUMP frames (60) after the lock the three middle-slot palettes 0x69-0x6b are as before it
    (`dirdone` never writes them: the arrows and the caption keep their colours)."""
    from vrtools.arcade.dirgfx import BLOCKS
    from vrtools.arcade.dirscreen import ARROW_CELLS
    from vrtools.arcade.tencourse import interior_on_the_left
    lines, wd = _drawn(tmp_path_factory, romset_zip, saturn_cue, entry)
    out, conv = _seven(romset_zip, saturn_cue)
    ccw = _anticlockwise(out, entry)
    assert ccw == (entry == ALPINE) == interior_on_the_left(conv[entry - 3].centreline)
    blk = _block(out)
    normal, other = ("ccw", "cw") if ccw else ("cw", "ccw")
    block = {"cw": BLOCKS[0], "ccw": BLOCKS[1]}
    for frame, shown in ((TWENTIETH, 0), (LATE, 1)):
        assert _shown_at(lines, frame) == shown
        tile, char, pal = _dump(wd, frame, entry)
        for side, arrow in ((0, normal), (1, other)):
            r, c = ARROW_CELLS[side]
            want = _map_words(blk[f"{arrow}_map"])
            got = {(i, j): _cell(tile, 0, r + i, c + j) for i in range(12) for j in range(12)}
            assert got == want, (frame, side, arrow)
            drawn = {w & 0x3FFF for w in got.values() if w != BLANK}
            assert drawn and {ch >> 7 for ch in drawn} == {block[arrow] >> 7}, (frame, side, sorted(map(hex, drawn))[:4])
        for arrow in ("cw", "ccw"):
            assert _ram_block(char, block[arrow], len(blk[f"{arrow}_chars"]) // 32) == blk[f"{arrow}_chars"], (frame, arrow)
        assert _pal(pal, block[normal] >> 7) == blk["white"] and _pal(pal, block[other] >> 7) == blk["red"], frame
    before, after = _dump(wd, LATE, entry)[2], _dump(wd, LOCKED_DUMP, entry)[2]
    assert [_pal(after, p) for p in (0x69, 0x6A, 0x6B)] == [_pal(before, p) for p in (0x69, 0x6A, 0x6B)]


def test_the_caption_reads_select_direction(tmp_path_factory, romset_zip, saturn_cue):
    """Plan D5: at the screen's 20th frame (Surfers Road) the wheel panel's 2 x 18 SELECT COURSE lettering cells from CAPTION_CELL
    hold the built set's caption map, every character in block 0x3580; character RAM there is the block's caption characters;
    and the block's palette 0x6b is the wheel panel's own palette (dirgfx.PANEL_PALETTE, as palette RAM holds it on the screen),
    so the caption is in the panel's colours. The rest of the panel is the game's map (test_the_screen_shows_the_picked_course_twice
    checks every layer-0 cell)."""
    from vrtools.arcade.dirgfx import BLOCKS, PANEL_PALETTE
    from vrtools.arcade.dirscreen import CAPTION_CELL
    lines, wd = _drawn(tmp_path_factory, romset_zip, saturn_cue, SURFERS_ROAD)
    out, _ = _seven(romset_zip, saturn_cue)
    blk = _block(out)
    tile, char, pal = _dump(wd, TWENTIETH, SURFERS_ROAD)
    r, c = CAPTION_CELL
    want = _map_words(blk["caption_map"])
    got = {(i, j): _cell(tile, 0, r + i, c + j) for i in range(2) for j in range(18)}
    assert got == want and {w & 0x3FFF for w in got.values()} <= set(range(BLOCKS[2], BLOCKS[2] + 128))
    assert _ram_block(char, BLOCKS[2], len(blk["caption_chars"]) // 32) == blk["caption_chars"]
    assert _pal(pal, BLOCKS[2] >> 7) == _pal(pal, PANEL_PALETTE)


# The state the title and the labels rest on without `dirdraw` setting it (final review Minor 5): 0xff870d's font cells
# [0x501438] (the character base >> 7) and [0x50143c] (the attribute), set by mode 0x0f's upload before every select screen
# (0xfe6bb9..0xfe6bc9; every game caller of the printer but 0xfc2df4 sets them itself), and the palettes the screen's text uses:
# the labels' (LABEL_WHITE 0x8200 and LABEL_YELLOW 0xc200 with the glyph bytes: palettes 4, 5, 0x84, 0x85) and the title's (the
# attribute 0x8000 on the font's characters from 0x400: palettes 8-10).
TITLE_FONT_SHIFT, TITLE_FONT_ATTR = 8, 0x8000
TEXT_PALETTES = (4, 5, 0x84, 0x85, 8, 9, 10)


def test_the_course_select_after_a_reverse_race_is_clean(tmp_path_factory, romset_zip, saturn_cue):
    """Task 1's reverse run (Metropolis through the screen, its race, the attract, a coin and START): SELECT_DUMP_AFTER frames into
    each course select (the first game's and the second's, no lock yet) the middle slot's three character blocks hold the
    picture record of the entry in the middle of the window (select.visible_entries of the shown index) and its palettes
    0x69-0x6b the record's normal set: the arrows and the caption the direction screen put there are gone in the second game,
    whose middle slot is as a first game's (and the same as the first game's when it shows the same entry). Final review Minor 5:
    `dirdraw` prints the title through 0xff870d and the labels through 0xffe8fb without setting their font cells or palettes, so
    at both dumps the countdown font's cells read [0x501438] = 8 and [0x50143c] = 0x8000, and the palettes the labels and the
    title use are the same in the second game's select as in the first's."""
    from vrtools.arcade.select import SLOT_CHAR, SLOT_PAL, visible_entries
    from tests.test_tencourse import _records
    run = _run(tmp_path_factory, romset_zip, saturn_cue, "reverse")
    out, _ = _seven(romset_zip, saturn_cue)
    _, recs, read = _records(out)
    starts = [b.frame for a, b in zip([None] + run.lines, run.lines) if b.mode == SELECT and (a is None or a.mode != SELECT)]
    assert len(starts) >= 2 and starts[0] < run.load < run.coin < starts[-1], (starts, run.load, run.coin)
    seen, pals = {}, []
    for start in (starts[0], starts[-1]):
        frame = start + SELECT_DUMP_AFTER
        files = sorted(_DUMPS["reverse"].glob(f"{frame}_*_char.bin"))
        assert len(files) == 1, (frame, files)
        index = int(files[0].name.split("_")[1])
        char = files[0].read_bytes()
        pal = files[0].with_name(files[0].name.replace("_char", "_pal")).read_bytes()
        # the countdown font's cells as dirdraw finds them: mode 0x0f's upload sets them before every select (0xfe6bb9..0xfe6bc9)
        work = files[0].with_name(files[0].name.replace("_char", "_work")).read_bytes()
        assert struct.unpack("<2I", work) == (TITLE_FONT_SHIFT, TITLE_FONT_ATTR), (frame, struct.unpack("<2I", work))
        pals.append({p: _pal(pal, p) for p in TEXT_PALETTES})
        rec = recs[visible_entries(index)[1]]
        n = [rec.counts & 0xFF, rec.counts >> 8 & 0xFF, rec.counts >> 16 & 0xFF]
        chars = read(rec.chars_addr, 32 * sum(n))
        for p in range(3):
            at = 32 * (SLOT_CHAR[1] + 128 * p)
            assert char[at:at + 32 * n[p]] == chars[32 * sum(n[:p]):32 * sum(n[:p + 1])], (frame, index, p)
        assert pal[SLOT_PAL[1] - 0x900000:][:96] == read(rec.normal_addr, 96), (frame, index)
        seen.setdefault(index, []).append((char[32 * SLOT_CHAR[1]:32 * (SLOT_CHAR[1] + sum(n))], pal[SLOT_PAL[1] - 0x900000:][:96]))
        print("SELECT", start, frame, "index", index, "middle entry", visible_entries(index)[1])
    for index, both in seen.items():
        assert all(x == both[0] for x in both), index
    assert pals[0] == pals[1], [hex(p) for p in TEXT_PALETTES if pals[0][p] != pals[1][p]]


# --- Task 7: no screen after the lock shows the middle slot's blocks ---------------------------------------------------------
# Since Task 5 the middle slot's character blocks (0x3480..0x35ff, palettes 0x69-0x6b) hold the arrows and the caption from the
# direction screen on, where the game left the chosen course's picture. slot_log.lua scans every second video frame (one scan per logic frame; a cell shown on one odd video frame only would be
# missed) the visible cells of
# the four tile layers (by their scroll words, as MAME draws them): the cells that name a character of those blocks, and those of
# them whose character still holds the locked screen's (non-blank) data; it dumps tile RAM and the blocks' characters 2, 60 and
# 300 frames after every change of the mode byte 0x501138 from the race load on. Task 1's two Metropolis runs (`_run`): the reverse
# one to the attract, its pit scenes and the second game's select (mode 0x0f uploads the select characters again); the normal one
# through the name entry (a reverse race records nothing, so it has none). Measured: the race load uploads the race's own
# characters over all three blocks, and the race's backdrop layer (2) names characters of them in the race, at the goal and in
# the attract's demo race, as the game does on main.
MIDDLE = range(0x3480, 0x3600)
SLOT_WINDOW_END = 0x0F                      # the next game's upload of the select characters (mode 0x0f)
SLOT_MODES = {"race": {0x14}, "goal": {0x19, 0x1A}, "results": {0x15, 0x16}, "ranking page": {0x1B, 0x1C, 0x1D},
              "attract": {0x02, 0x03}}


@dataclass(frozen=True)
class SlotLine:
    frame: int
    mode: int
    named: tuple[int, int, int, int]        # per layer the visible cells naming the middle slot; -1: the layer is not drawn
    shows: tuple[int, int, int, int]        # of those, the cells whose character holds the locked screen's (non-blank) data
    kept: int                               # the middle slot's characters still the locked screen's non-blank ones (-1: not yet)
    hit: str


def _parse_slot(path):
    """slot_log.lua's R frame, S lines and D lines ((frame, mode, tile file name))."""
    ref, lines, dumps = None, [], []
    for row in open(path):
        tag, *f = row.split()
        if tag == "R":
            ref = int(f[0])
        elif tag == "S":
            lines.append(SlotLine(int(f[0]), int(f[1], 16), tuple(int(x) for x in f[2:6]), tuple(int(x) for x in f[6:10]), int(f[10]), f[11]))
        elif tag == "D":
            dumps.append((int(f[0]), int(f[1], 16), f[2]))
    return ref, lines, dumps


def _span(origin, pixels):
    """The cells (0..63) a window of `pixels` pixels from pixel `origin` covers on a 512-pixel layer (wrapping)."""
    return sorted({((origin + p) & 0x1FF) >> 3 for p in range(pixels)})


def _middle_cells(tile):
    """Per tile layer of a tile RAM dump (0x700000..0x70ffff): None when the layer is not drawn (its vertical scroll word's bit
    15), else the visible cells naming a character of the middle slot's blocks, [(row, col, word)]. As MAME's
    segas24_tile_device::draw_common: layer n's scroll words at 0x70a000 + 2n (horizontal) and 0x70a008 + 2n (vertical), its control
    word at 0x70a008 + 2 (n & 2); plain scrolling shows the 496 x 384 pixels from x = (-hscr) & 0x1ff, y = vscr & 0x1ff; a
    per-line scroll table (hscr bit 15) counts every column of those rows, a special window mode (ctrl & 0x6000) every cell. The
    same rule as slot_log.lua's."""
    word = lambda a: struct.unpack_from("<H", tile, a)[0]
    out = []
    for n in range(4):
        hscr, vscr, ctrl = word(0xA000 + 2 * n), word(0xA008 + 2 * n), word(0xA008 + 2 * (n & 2))
        if vscr & 0x8000:
            out.append(None)
            continue
        if ctrl & 0x6000:
            rows = cols = list(range(64))
        else:
            rows = _span(vscr & 0x1FF, 384)
            cols = list(range(64)) if hscr & 0x8000 else _span(-hscr & 0x1FF, 496)
        cells = [(r, c, word(0x2000 * n + 0x80 * r + 2 * c)) for r in rows for c in cols]
        out.append([(r, c, w) for r, c, w in cells if w & 0x3FFF in MIDDLE])
    return out


def _screen_chars(out):
    """{character: its 32 bytes} of what the direction screen writes into the middle slot (the built set's block): the clockwise
    arrow's from 0x3480, the anticlockwise one's from 0x3500, the caption's from 0x3580; blank characters (all colour 0) left out."""
    from vrtools.arcade.dirgfx import BLOCKS
    blk, want = _block(out), {}
    for part, block in (("cw_chars", BLOCKS[0]), ("ccw_chars", BLOCKS[1]), ("caption_chars", BLOCKS[2])):
        for k in range(len(blk[part]) // 32):
            data = blk[part][32 * k:32 * k + 32]
            if any(data):
                want[block + k] = data
    return want


def _showing(cells, mid, screen):
    """Of _middle_cells' cells, per layer, those whose character holds the direction screen's data in `mid` (the middle slot's
    384 characters from 0x3480)."""
    hold = {ch for ch, data in screen.items() if mid[32 * (ch - MIDDLE[0]):32 * (ch - MIDDLE[0] + 1)] == data}
    return [None if c is None else [x for x in c if x[2] & 0x3FFF in hold] for c in cells]


def _slot_at(lines, frame):
    """The S line in force at the end of `frame` (lines are written on a change, every second frame)."""
    return [l for l in lines if l.frame <= frame][-1]


@pytest.mark.parametrize("label", ["reverse", "normal"])
def test_no_screen_after_the_lock_shows_the_middle_slot(tmp_path_factory, romset_zip, saturn_cue, label):
    """Task 5's review: from the race load (the mode byte 0x501138 at 0x11) to the next game's select upload (0x0f), or the run's
    end, no visible cell of a drawn tile layer shows the direction screen's characters (a cell naming a character of the middle
    slot's blocks that still holds the arrows' or the caption's data): on no scan (slot_log.lua's, every second video frame, against the
    locked screen's characters) and in no dump (this module's own reading of the scroll words, against the built set's block).
    The run reaches the race, the goal, the results, the race-end ranking page and the attract, the normal run its name entry too,
    the reverse run the second game's select; each of those modes has a dump. Positive controls: on the locked screen
    (SLOT_LOCKED_DUMP) character RAM holds the built set's arrows and caption in those blocks, and the scan and this module's
    reading of that frame's dump find the same cells naming them on layer 0 and showing them, as many as the built arrow and
    caption maps' non-empty cells and none on another layer."""
    from vrtools.arcade.dirgfx import BLOCKS
    run = _run(tmp_path_factory, romset_zip, saturn_cue, label)
    out, _ = _seven(romset_zip, saturn_cue)
    ref, lines, dumps = _parse_slot(_SLOTS[label] / "slot.txt")
    assert lines and ref is not None and ref < run.load, (ref, run.load)
    screen = _screen_chars(out)
    # the locked screen: the middle slot's blocks hold the arrows and the caption, on screen on layer 0
    blk = _block(out)
    tile = (_DUMPS[label] / f"{SLOT_LOCKED_DUMP}_{METROPOLIS}_tile.bin").read_bytes()
    char = (_DUMPS[label] / f"{SLOT_LOCKED_DUMP}_{METROPOLIS}_char.bin").read_bytes()
    for part, block in (("cw_chars", BLOCKS[0]), ("ccw_chars", BLOCKS[1]), ("caption_chars", BLOCKS[2])):
        assert _ram_block(char, block, len(blk[part]) // 32) == blk[part], part
    cells = _middle_cells(tile)
    showing = _showing(cells, char[32 * MIDDLE[0]:32 * (MIDDLE[-1] + 1)], screen)
    count = lambda cs: tuple(-1 if c is None else len(c) for c in cs)
    scanned = _slot_at(lines, SLOT_LOCKED_DUMP)
    on_screen = sum(1 for k in ("cw_map", "ccw_map", "caption_map") for w in _map_words(blk[k]).values() if w != BLANK)
    assert count(showing) == (on_screen, 0, 0, 0), (count(showing), on_screen)      # the two arrows' and the caption's non-empty cells
    assert scanned.mode == SELECT and scanned.named == count(cells), (scanned, count(cells))
    assert scanned.shows == tuple(max(n, 0) for n in count(showing)), (scanned, count(showing))
    print(label, "locked screen: cells naming / showing the middle slot per layer", count(cells), count(showing), "scan", scanned)
    # from the race load to the next select's upload
    first = next(k for k, l in enumerate(lines) if 0x11 <= l.mode <= 0x14)
    end = next((k for k in range(first, len(lines)) if lines[k].mode == SLOT_WINDOW_END), len(lines))
    window = lines[first:end]
    last = lines[end].frame if end < len(lines) else None
    shown = [l for l in window if any(l.shows)]
    assert not shown, shown[:5]
    modes = {l.mode for l in window}
    want = dict(SLOT_MODES, **({"name entry": {NAME_ENTRY}} if label == "normal" else {}))
    assert all(modes & m for m in want.values()), {k: sorted(map(hex, m)) for k, m in want.items() if not modes & m}
    if label == "reverse":
        assert last is not None, "the run ended before the second game's select"
    inside = [(f, m, name) for f, m, name in dumps if window[0].frame <= f and (last is None or f < last)]
    named = {}
    for f, m, name in inside:
        cells = _middle_cells((_SLOTS[label] / "slot" / name).read_bytes())
        mid = (_SLOTS[label] / "slot" / name.replace("tile", "mid")).read_bytes()
        assert not any(_showing(cells, mid, screen)), (f, hex(m))
        named[m] = max(named.get(m, 0), sum(max(n, 0) for n in count(cells)))
    dumped = set(named)
    assert all(dumped & m for m in want.values()), {k: sorted(map(hex, m)) for k, m in want.items() if not dumped & m}
    print(label, "window frames", window[0].frame, "to", last, "modes", sorted(map(hex, modes)), "dumps", len(inside),
          "most cells naming the middle slot in a dump, per mode", {hex(m): n for m, n in sorted(named.items())},
          "kept at the window's start and end", window[0].kept, window[-1].kept)
