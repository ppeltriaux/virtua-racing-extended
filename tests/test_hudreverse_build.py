"""Phase 32 on the seven-course set (`tests.test_tgp_build._seven`, one conversion per session): in a reverse race the word
REVERSE under the course's name in the race HUD, right-aligned with it.

Pascal, 15 Nov: "One additional idea, when playing a track in reverse it could have the word "reverse" under the track name(maybe
in a neon red style?)"; told the HUD font is flat-coloured tiles and a neon glow would need new graphics, "Ok maybe just a
shadows reverse then"; shown three stills and the lead's recommendations (red on every course; the placement as built; keep it
and send it to review), "Yes all your recommendation". They have not driven the set. The word is printed by the game's own
8 x 16 printer (0xff8926), whose glyph tiles carry the black outline the name has, in the game's EXPERT red.

hudrows_log.lua logs layer 0's rows 44-47 (all 64 columns; 62 are on screen) keyed on the mode byte: at the frame the name is
printed (load), 60 frames into mode 0x14 (race), every 500 frames after (lap), at the first frame of mode 0x1a (goal) and at
every mode after a race (m, m30); and the writes to those rows from column 19 on, from the race line to the race's end. A
row-46 word w other than a blank is the letter chr(((w & 0x7f) >> 1) + 0x20) in the colour base w & 0xff80, row 47's is w + 1
(the printer, as on rows 44-45). Blank cells are 0x8020 in a race (the cleared layer 0) and 0x0020 where the results cleared it.
Columns 0-18 of those rows are the game's (the SPEED figures on 2-11; with the manual transmission, [0x501936] != 0, the gear's
maps on columns 14 and 17, rows 44-46): the tests read from column 19.

Against main: MAIN_SET is a build of main without this phase (git-ignored; the tests that need it skip without it)."""
import os
from pathlib import Path

import pytest

from vrtools.arcade.course import DIRECTION_RAM, course_entry_at, road_lines
from vrtools.arcade.directory import decode_directory, directory_layout
from vrtools.arcade.hudname import REVERSE_ATTR, REVERSE_TEXT
from vrtools.arcade.romset import RomSet
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.arcade.tencourse import COURSES as PLANS
from vrtools.convert.reverse import reverse_points
from vrtools.mame.framerate import parse_pass_log
from vrtools.mame.pitpaths import normal_pit_path, pit_lane, reverse_pit_path
from vrtools.mame.runner import (LUA_DIR, PIT_HANDLER, parse_dir_log, parse_hudrows_log, parse_pit_log, run_mame,
                                 write_centreline)
from tests.test_race_build import _drive_entry, _drive_line
from tests.test_tgp_build import _build, _seven

BLANK = 0x8020                          # a cleared layer-0 cell in a race (0xff92c9)
BLANKS = (0x8020, 0x0020)               # and where mode 0x15 cleared it
BASES = (0x8100, 0xC180, 0xC100)        # by the record's label: blue (BEGINNER), orange (MEDIUM), red (EXPERT)
RED = (REVERSE_ATTR << 7 | 0x8000) & 0xFF80          # the word's colour base: 0xC100, the game's EXPERT red
LAST = 58                               # the name's and the word's last column
FIRST = LAST + 1 - len(REVERSE_TEXT)    # 52
FREE_FROM = 19                          # rows 44-47 from here on are the name's and the word's: the SPEED figures are on columns
                                        # 2-11 (to row 46), the manual transmission's gear maps on columns 14 and 17 (rows 44-46)
ON_SCREEN = 62                          # columns 0-61 (496 pixels)
ALPINE, AMAZON_FALLS, DIABLO_CANYON, METROPOLIS = 3, 4, 5, 6      # a blue, an orange and a red name; the pit and two-game course
RACE_MODES = (0x11, 0x12, 0x13, 0x14, 0x19, 0x1A)
SESSION_SECONDS = 300                   # two one-lap games (tests/test_reverse_ranking.py's)
PIT_SECONDS = 150
REVERSE_PIT_SECONDS, REVERSE_AHEAD = 180, 15       # tests/test_pit_build.py's reverse stop (autopilot.lua's VR_AUTOPILOT_AHEAD)
# MAIN_SET: the reference set VR_MAIN_SET (tests/reference_sets.py, W2; no default): a build of main without Phase 32 (add9799:
# Phases 29 and 31 merged), made by `python -m vrtools build` from main's tree; git-ignored
TILE_FRAMES = (8, 60, 300, 400, 700, 1200, 1800, 2200)    # after the race load
SAME_SECONDS = 120

_RUNS: dict = {}


def _text(rows, row, first, last):
    """The text and the colour bases of columns first..last of `row` (the row below holding each word + 1)."""
    text, bases = "", set()
    for c in range(first, last + 1):
        w, v = rows[row][c], rows[row + 1][c]
        assert w not in BLANKS and v == w + 1, (row, c, hex(w), hex(v))
        text += chr(((w & 0x7F) >> 1) + 0x20)
        bases.add(w & 0xFF80)
    return text, bases


def _blank(rows, row, first, last):
    return all(rows[r][c] in BLANKS for r in (row, row + 1) for c in range(first, last + 1))


def _has_word(rows):
    """REVERSE on rows 46-47, columns 52-58, in red, and nothing else on those rows from column 19 on."""
    return (_text(rows, 46, FIRST, LAST) == (REVERSE_TEXT.decode(), {RED}) and _blank(rows, 46, FREE_FROM, FIRST - 1)
            and _blank(rows, 46, LAST + 1, 63))


WORD = tuple((RED - 0x40 + 2 * ch) & 0xFFFF for ch in REVERSE_TEXT)       # the word's row-46 tile words, column 52 on


def _no_word_cell(rows):
    """None of the word's 14 cells holds its tile word (row 46's, or row 47's: the same + 1): no letter of it is left."""
    return all(rows[46][FIRST + k] != w and rows[47][FIRST + k] != w + 1 for k, w in enumerate(WORD))


def _run(tmp_path_factory, romset_zip, saturn_cue, entry, reverse=False, manual=False, coin=None):
    """(the R lines by tag, {race: writes}, the direction flag at the load) of a 45 s race on `entry` (the gas floored); `manual`:
    the manual transmission chosen (VR_MANUAL); `coin`: Coin 1 pressed that many frames after the race line."""
    key = (entry, reverse, manual, coin)
    if key not in _RUNS:
        out, conv = _seven(romset_zip, saturn_cue)
        base = tmp_path_factory.mktemp(f"hudrev{entry}{'r' if reverse else ''}{'m' if manual else ''}{'c' if coin else ''}")
        env = {"VR_HUDROWS_LOG": str(base / "rows.txt"), "VR_DIR_LOG": str(base / "dir.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"}
        if manual:
            env["VR_MANUAL"] = "1"
        if coin:
            env["VR_HUDROWS_COIN"] = str(coin)
        _drive_entry(base, out, romset_zip, entry, None, seconds=45, reverse=reverse, extra_env=env)
        lines, writes = parse_hudrows_log(base / "rows.txt")
        load = next(l for l in parse_dir_log(base / "dir.txt") if l.mode == 0x11)
        _RUNS[key] = {l.tag: l for l in lines}, writes, load.flag
        _RUNS[key + ("all",)] = lines, (base / "rows.txt").read_text()
    return _RUNS[key]


@pytest.mark.parametrize("entry", (ALPINE, AMAZON_FALLS, DIABLO_CANYON))
def test_a_reverse_race_shows_reverse_under_the_name(tmp_path_factory, romset_zip, saturn_cue, entry):
    """REVERSE chosen on the COURSE DIRECTION screen (the flag 1 at the race load), on a blue-, an orange- and a red-named course:
    rows 44-45 read the name in its level's colour as in a normal race; rows 46-47, columns 52-58, read REVERSE in the game's red
    (0xC100), its last letter under the name's; the rest of rows 46-47 from column 19 is blank; printed at the load and kept."""
    out, _ = _seven(romset_zip, saturn_cue)
    e = decode_directory(out)[entry]
    by_tag, _, flag = _run(tmp_path_factory, romset_zip, saturn_cue, entry, reverse=True)
    assert flag == 1 and {"load", "race"} <= set(by_tag)
    rows = by_tag["race"].rows
    assert by_tag["race"].mode == 0x14
    assert _text(rows, 44, LAST + 1 - len(e.name), LAST) == (e.name, {BASES[e.label]}), e.name
    assert _blank(rows, 44, 19, LAST - len(e.name)) and _blank(rows, 44, LAST + 1, 63)
    assert _has_word(rows), (e.name, [hex(w) for w in rows[46][40:]])
    load = by_tag["load"].rows
    assert all(load[r][FREE_FROM:] == rows[r][FREE_FROM:] for r in (46, 47)) and all(load[r][19:] == rows[r][19:] for r in (44, 45))
    assert LAST < ON_SCREEN and FIRST == 52


@pytest.mark.parametrize("entry", (0, 1, 2, DIABLO_CANYON))
def test_a_normal_race_shows_no_word(tmp_path_factory, romset_zip, saturn_cue, entry):
    """The three originals (their reverse race: tests/test_originals_reverse.py) and a converted course in the normal direction: rows 46-47 are blank from
    column 19 on at the load and in the race, rows 44-45 hold the label as before (tests/test_hudname_build.py reads it)."""
    by_tag, _, flag = _run(tmp_path_factory, romset_zip, saturn_cue, entry)
    assert flag == 0 and {"load", "race"} <= set(by_tag)
    for tag in ("load", "race"):
        rows = by_tag[tag].rows
        assert _blank(rows, 46, FREE_FROM, 63), (entry, tag, [hex(w) for w in rows[46][40:]])
        assert not _blank(rows, 44, 51, LAST)


def _two_games(tmp_path_factory, romset_zip, saturn_cue):
    """A reverse one-lap race then a normal one on Metropolis in one MAME session (race_end.lua: the clock held, the autopilot),
    with the results, the attract and the second select between them: (the R lines, {race: writes})."""
    if "two" not in _RUNS:
        out, conv = _seven(romset_zip, saturn_cue)
        base = tmp_path_factory.mktemp("hudrev_two")
        build = _build(base, romset_zip, out)
        wd = base / "run"
        line = _drive_line(conv[METROPOLIS - 3])
        paths = {d: write_centreline(wd / f"{d}.csv", reverse_points(line) if d == "reverse" else line) for d in ("reverse", "normal")}
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[METROPOLIS]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
               "VR_AUTOPILOT": str(paths["reverse"]), "VR_EXTRA_LUA": str(LUA_DIR / "race_end.lua"), "VR_END_LOG": str(wd / "end.txt"),
               "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}", "VR_DIRECTION": "1", "VR_END_NEXT": f"{WHEEL_FOR_ENTRY[METROPOLIS]}:0",
               "VR_END_NEXT_LINE": str(paths["normal"]), "VR_HUDROWS_LOG": str(wd / "rows.txt")}
        run_mame(LUA_DIR / "autoplay.lua", SESSION_SECONDS, wd, build, env=env)
        _RUNS["two"] = parse_hudrows_log(wd / "rows.txt")
    return _RUNS["two"]


def test_the_word_stays_to_the_goal_and_goes_with_the_race(tmp_path_factory, romset_zip, saturn_cue):
    """Metropolis, a reverse race to the goal: the word is there at the load, 60 frames in, at every 500th frame and at the goal
    (mode 0x1a), the cells the same every time, and nothing wrote the name's or the word's cells between (the write tap: 0).
    From the results on, on every logged frame of every mode up to the next race load (the results 0x15-0x1d, the name entry
    0x1e, the attract 0x02 / 0x03, the coin and the next select 0x0f / 0x10), none of the word's 14 cells holds its tile word:
    the game's own layer clear at mode 0x15 takes it (rows 46-47 blank from column 19 through the results), no code of the
    project's; the later screens draw their own tiles on those rows."""
    lines, writes = _two_games(tmp_path_factory, romset_zip, saturn_cue)
    first = [l for l in lines if l.race == 1]
    racing = [l for l in first if l.tag in ("load", "race", "lap", "goal")]
    assert {"load", "race", "lap", "goal"} == {l.tag for l in racing} and all(l.mode in RACE_MODES for l in racing)
    assert all(_has_word(l.rows) for l in racing), [(l.tag, l.frame) for l in racing if not _has_word(l.rows)]
    assert _text(racing[0].rows, 44, LAST + 1 - len("METROPOLIS"), LAST) == ("METROPOLIS", {BASES[1]})
    assert all(l.rows[r][19 if r < 46 else FREE_FROM:] == racing[0].rows[r][19 if r < 46 else FREE_FROM:] for l in racing for r in range(44, 48))
    assert writes[1] == 0
    after = [l for l in first if l.tag in ("m", "m30")]
    assert {0x15, 0x16, 0x1B, 0x1C, 0x1D, 0x1E, 0x02, 0x03, 0x0F, 0x10} <= {l.mode for l in after}, sorted({l.mode for l in after})
    assert WORD == tuple(racing[0].rows[46][FIRST:LAST + 1])
    assert all(_no_word_cell(l.rows) for l in after), [(l.tag, l.frame, hex(l.mode)) for l in after if not _no_word_cell(l.rows)]
    results = [l for l in after if l.mode in (0x15, 0x16, 0x1B, 0x1C, 0x1D)]
    assert all(_blank(l.rows, 46, FREE_FROM, 63) for l in results), [(l.tag, l.frame, hex(l.mode)) for l in results]


def test_the_next_normal_race_shows_no_stale_word(tmp_path_factory, romset_zip, saturn_cue):
    """The same session's second game, Metropolis in the normal direction: the name at the load, in the race and at the goal, and
    rows 46-47 blank from column 19 on every logged frame of it."""
    lines, writes = _two_games(tmp_path_factory, romset_zip, saturn_cue)
    second = [l for l in lines if l.race == 2 and l.tag in ("load", "race", "lap", "goal")]
    assert {"load", "race", "goal"} <= {l.tag for l in second}, sorted({l.tag for l in second})
    for l in second:
        assert _blank(l.rows, 46, FREE_FROM, 63), (l.tag, l.frame)
        assert _text(l.rows, 44, LAST + 1 - len("METROPOLIS"), LAST) == ("METROPOLIS", {BASES[1]})
    assert writes[2] == 0


def _pit_runs(tmp_path_factory, romset_zip, saturn_cue):
    """Metropolis through its pit lane with a stop, in the normal direction (tests/test_frame_rate.py's pit path) and then in
    reverse (tests/test_pit_build.py's: the normal run's own trajectory read backwards, `pitpaths.reverse_pit_path`):
    {"normal" | "reverse": (the R lines, {race: writes}, the pit log's frames)}."""
    if "pit" not in _RUNS:
        out, conv = _seven(romset_zip, saturn_cue)
        base = tmp_path_factory.mktemp("hudrev_pit")
        build = _build(base, romset_zip, out)
        d = decode_directory(out)
        road = road_lines(out, course_entry_at(out, d[METROPOLIS].bank, window_base=d[METROPOLIS].header_base))
        line6 = [(p.x, p.z) for p in road[6]]
        lane = pit_lane(RomSet.from_zip(romset_zip), saturn_cue, PLANS[METROPOLIS - 3], conv[METROPOLIS - 3].centreline)[0]
        runs = {}
        for kind in ("normal", "reverse"):
            wd = base / kind
            path = normal_pit_path(line6, lane) if kind == "normal" else reverse_pit_path(runs["normal"][2], line6)
            env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[METROPOLIS]), "VR_COLLISION_LOG": str(wd / "c.txt"),
                   "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", path)), "VR_HOLD_CLOCK": "1", "VR_PIT_LOG": str(wd / "pit.txt"),
                   "VR_HUDROWS_LOG": str(wd / "rows.txt"), "VR_SNAPS": "",
                   "VR_SNAPS_AFTER_START": ",".join(str(f) for f in range(600, 10000, 200))}
            if kind == "reverse":
                env.update({"VR_DIRECTION": "1", "VR_AUTOPILOT_AHEAD": str(REVERSE_AHEAD)})
            run_mame(LUA_DIR / "autoplay.lua", PIT_SECONDS if kind == "normal" else REVERSE_PIT_SECONDS, wd, build, env=env)
            runs[kind] = parse_hudrows_log(wd / "rows.txt") + (parse_pit_log(wd / "pit.txt"),)
        _RUNS["pit"] = runs
    return _RUNS["pit"]


def _stop(lines, pit):
    """(the race and lap lines, the first and last frame of the run's first pit stop: the player's pit handler without a break)
    of one pit run, having checked that the stop lasts 300 frames or more and that a line was logged before it, one inside it
    and a lap line after it."""
    racing = [l for l in lines if l.tag in ("race", "lap")]
    stopped = [p.frame for p in pit if p.handler == PIT_HANDLER and p.frame > racing[0].frame]
    assert stopped, "no pit stop in the run"
    first = stopped[0]
    last = next((p.frame for p in pit if p.frame > first and p.handler != PIT_HANDLER), None)      # the release
    assert last is not None and last - first >= 300, ("the stop is not a whole one", first, last)
    assert any(l.frame < first for l in racing) and any(first < l.frame < last for l in racing) \
        and any(l.frame > last and l.tag == "lap" for l in racing), ([l.frame for l in racing], first, last)
    return racing, (first, last)


def test_a_pit_stop_writes_none_of_the_cells(tmp_path_factory, romset_zip, saturn_cue):
    """A lap through Metropolis's pit lane with a stop, in the normal direction: from the race line to the last lap line (after
    the stop) no write reaches rows 44-47 from column 19 (the tap: 0), the logged rows are the same before, during and after
    the stop, the name on them and rows 46-47 blank."""
    lines, writes, pit = _pit_runs(tmp_path_factory, romset_zip, saturn_cue)["normal"]
    racing, stopped = _stop(lines, pit)
    for l in racing:
        assert _blank(l.rows, 46, FREE_FROM, 63) and _text(l.rows, 44, LAST + 1 - len("METROPOLIS"), LAST)[0] == "METROPOLIS", l.frame
    assert writes[1] == 0


def test_the_word_stays_through_a_pit_stop_in_a_reverse_race(tmp_path_factory, romset_zip, saturn_cue):
    """The same lane in a reverse race, the word on screen: a stop is made (the player's pit handler for 300 frames or more);
    before it, during it and after it the name and the word are on their cells and nothing else is on rows 44-47 from column 19;
    no write reached those cells from the race line to the last lap line. So the stop neither clears nor overwrites the word,
    and whatever the game shows during a stop it writes none of it into those cells (they are layer 0's: a message of the
    game's there would be a write to them)."""
    lines, writes, pit = _pit_runs(tmp_path_factory, romset_zip, saturn_cue)["reverse"]
    racing, stopped = _stop(lines, pit)
    for l in racing:
        assert _has_word(l.rows) and _text(l.rows, 44, LAST + 1 - len("METROPOLIS"), LAST) == ("METROPOLIS", {BASES[1]}), l.frame
        assert _blank(l.rows, 44, FREE_FROM, LAST - len("METROPOLIS"))
    assert writes[1] == 0


def test_the_word_with_the_manual_transmission(tmp_path_factory, romset_zip, saturn_cue):
    """Alpine in reverse with the manual transmission chosen (START held at the course lock: [0x501936] != 0, the HUD's first
    handler then blits the gear's maps at row 44, columns 14 and 17, three rows each, 0xff47c3..0xff4802): the gear is on rows
    44-46 left of column 19 (the run must show it: a cell there differs from the automatic run's), the name and the word are
    where they are in the automatic run and the rest of rows 44-47 from column 19 is blank."""
    manual, _, flag = _run(tmp_path_factory, romset_zip, saturn_cue, ALPINE, reverse=True, manual=True)
    auto, _, _ = _run(tmp_path_factory, romset_zip, saturn_cue, ALPINE, reverse=True)
    rows, ref = manual["race"].rows, auto["race"].rows
    assert flag == 1 and _has_word(rows)
    assert all(rows[r][FREE_FROM:] == ref[r][FREE_FROM:] for r in range(44, 48))
    gear = [(r, c) for r in range(44, 47) for c in range(12, FREE_FROM) if rows[r][c] != ref[r][c]]
    assert gear and {c for _, c in gear} <= {13, 14, 15, 16, 17, 18} and any(r == 46 for r, _ in gear), gear


def test_a_coin_during_a_reverse_race_leaves_the_word(tmp_path_factory, romset_zip, saturn_cue):
    """Diablo Canyon in reverse, Coin 1 pressed 300 frames after the race line (hudrows_log.lua's VR_HUDROWS_COIN): the word and
    the name are on their cells at the next lap lines as before the coin, and no write reached rows 44-47 from column 19."""
    by_tag, writes, flag = _run(tmp_path_factory, romset_zip, saturn_cue, DIABLO_CANYON, reverse=True, coin=300)
    lines, text = _RUNS[(DIABLO_CANYON, True, False, 300, "all")]
    coin = [int(l.split()[1]) for l in text.splitlines() if l.startswith("C ")]
    laps = [l for l in lines if l.tag == "lap"]
    assert flag == 1 and len(coin) == 1 and coin[0] == by_tag["race"].frame + 300
    assert laps and laps[-1].frame > coin[0] + 60, (coin, [l.frame for l in laps])
    for l in [by_tag["race"]] + laps:
        assert _has_word(l.rows) and all(l.rows[r][FREE_FROM:] == by_tag["race"].rows[r][FREE_FROM:] for r in range(44, 48)), l.frame
    assert writes[1] == 0


def _main_set():
    from tests.reference_sets import reference_set
    return reference_set("VR_MAIN_SET")


@pytest.mark.parametrize("entry", (0, 1, 2, DIABLO_CANYON))
def test_a_normal_race_draws_mains_tiles(tmp_path_factory, romset_zip, saturn_cue, entry):
    """The three originals and Diablo Canyon in the normal direction, autoplay.lua's own inputs (the gas floored), on main's set
    (MAIN_SET) and on the session's: the race loads on the same frame and the whole tile RAM (0x700000-0x70ffff: the four tile
    layers, the HUD's among them, their scroll words and window masks; tile_dump.lua) is byte-identical TILE_FRAMES after the
    load."""
    main = _main_set()
    out, _ = _seven(romset_zip, saturn_cue)
    base = tmp_path_factory.mktemp(f"hudrev_tiles{entry}")
    build = _build(base, romset_zip, out)
    dumps = {}
    for name, rom in (("main", main), ("new", build)):
        wd = base / name
        wd.mkdir()
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_SNAPS": "", "VR_TILE_DUMP_DIR": str(wd),
               "VR_TILE_DUMP_AT": ",".join(str(f) for f in TILE_FRAMES)}
        run_mame(LUA_DIR / "autoplay.lua", 70, wd, rom, env=env)
        dumps[name] = (wd / "frames.txt").read_text(), [(wd / f"tile_{f:05d}.bin").read_bytes() for f in TILE_FRAMES]
    assert dumps["main"][0] == dumps["new"][0] and len(dumps["main"][0].splitlines()) == len(TILE_FRAMES)
    assert all(len(x) == 0x10000 for x in dumps["new"][1])
    differ = [f for f, x, y in zip(TILE_FRAMES, dumps["main"][1], dumps["new"][1]) if x != y]
    assert differ == [], (entry, differ)
    assert len(set(dumps["new"][1])) >= 6                       # the dumps are of a moving race, not one picture


def test_a_reverse_race_is_mains_pass_for_pass(tmp_path_factory, romset_zip, saturn_cue):
    """Diablo Canyon in reverse for SAME_SECONDS from the same battery RAM: main's set (MAIN_SET) driven by the autopilot, its
    wheel and pedal recorded every frame (input_tape.lua); the session's set fed that tape frame for frame. The tapes are equal
    and the game's state at the end of every logic pass (pass_state.lua: the clock, the 16 cars' x, z, road point, speed and lap,
    and the frame the pass ends in) is identical over the whole run; both races loaded with the direction flag 1; main's rows
    46-47 are blank and the set's hold the word (so the two sets are the two builds). As tests/test_frame_rate.py's
    test_the_game_is_the_same_pass_for_pass, in reverse and against main's own built set."""
    import shutil
    main = _main_set()
    out, conv = _seven(romset_zip, saturn_cue)
    base = tmp_path_factory.mktemp("hudrev_same")
    build = _build(base, romset_zip, out)
    run_mame(LUA_DIR / "attract_snaps.lua", 30, base / "boot", build, env={"VR_SNAP_FROM": "999999"}, timeout=900)
    line = write_centreline(base / "line.csv", reverse_points(_drive_line(conv[DIABLO_CANYON - 3])))
    for name, rom in (("main", main), ("new", build)):
        wd = base / name
        wd.mkdir()
        shutil.copytree(base / "boot" / "nvram", wd / "nvram")
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[DIABLO_CANYON]), "VR_SNAPS": "", "VR_DIRECTION": "1",
               "VR_AUTOPILOT": str(line), "VR_PASS_LOG": str(wd / "pass.txt"), "VR_INPUT_LOG": str(wd / "tape.txt"),
               "VR_HUDROWS_LOG": str(wd / "rows.txt"), "VR_DIR_LOG": str(wd / "dir.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}",
               "VR_REVERSE_TABLE": f"{directory_layout()['reverse']:x}"}      # (main's table is at the same address: the tables
        if name == "new":                                                      # come before the routines; autoplay.lua stops the
            env["VR_INPUT_REPLAY"] = str(base / "main" / "tape.txt")           # run with an error if the screen is not answered)
        run_mame(LUA_DIR / "autoplay.lua", SAME_SECONDS, wd, rom, env=env, timeout=3600)
    ta, tb = [(base / n / "tape.txt").read_text().splitlines() for n in ("main", "new")]
    assert len(ta) > 3000 and ta == tb, ("the replay did not feed main's inputs", len(ta), len(tb))
    a, b = [parse_pass_log(base / n / "pass.txt") for n in ("main", "new")]
    assert len(a) > 3000 and len(a) == len(b), (len(a), len(b))
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    assert first is None, (first, a[first][:120], b[first][:120])
    for name, word in (("main", False), ("new", True)):
        assert next(l for l in parse_dir_log(base / name / "dir.txt") if l.mode == 0x11).flag == 1, name
        rows = next(l for l in parse_hudrows_log(base / name / "rows.txt")[0] if l.tag == "race").rows
        assert (_has_word(rows) if word else _blank(rows, 46, FREE_FROM, 63)), name
        assert _text(rows, 44, LAST + 1 - len("DIABLO CANYON"), LAST) == ("DIABLO CANYON", {BASES[2]}), name
