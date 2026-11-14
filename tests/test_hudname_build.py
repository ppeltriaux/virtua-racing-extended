"""Phase 26 stage 3 (plan Task 6) on the seven-course set (`tests.test_tgp_build._seven`, one conversion per session): the race HUD's
bottom-right label reads the converted course's name, right-aligned to column 58, in the colour of the entry's select-screen
level (Pascal, 13 Nov: H1-H4); the three originals keep the game's BEGINNER / MEDIUM / EXPERT.

hud_log.lua logs layer 0's rows 44 and 45, columns 40-61, and the colour cell [0x501434] 60 frames into mode 0x14, at the first
frame of mode 0x1a, and at the race load on the frame the label is printed (keyed on the mode byte, never on absolute frames). A row-44 word w other than 0x8020 (the cleared
layer's) is the letter chr(((w & 0x7f) >> 1) + 0x20) in the colour base w & 0xff80 (the printer 0xff8926: (attr << 7) − 0x40 +
2·ch | 0x8000), and row 45's word is w + 1. Each run is made once per session: 45 seconds with the game's own inputs (the gas
floored), autoplay.lua answering the COURSE DIRECTION screen on entries 3-9 (NORMAL, or REVERSE with VR_DIRECTION=1);
dirscreen_log.lua shows the flag the race loaded with."""
import pytest

from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.directory import LOAD_FIELDS, LOAD_SIZE, NAME_LEN, decode_directory, directory_layout
from vrtools.arcade.romset import V60_PROGRAM
from vrtools.mame.runner import HUD_COLUMNS, LUA_DIR, parse_dir_log, parse_hud_log
from tests.test_race_build import _drive_entry
from tests.test_tgp_build import _seven

BLANK = 0x8020                          # a cleared layer-0 cell (0xff92c9)
BASES = (0x8100, 0xC180, 0xC100)        # by the record's label: blue (BEGINNER), orange (MEDIUM), red (EXPERT)
LABELS = {3: 0, 4: 1, 5: 2, 6: 1, 7: 1, 8: 0, 9: 2}     # the select screen's level per converted entry (H2): Alpine and Surfers
                                        # Oval blue; Amazon Falls, Metropolis and Pacific Coast orange; Diablo Canyon and Surfers Road red
GAME_WORDS = {0: ("BEGINNER", 0x8100), 1: (" MEDIUM ", 0xC180), 2: (" EXPERT ", 0xC100)}    # the originals, as the game prints them
SAME_INDEX = {6: 2, 8: 1, 9: 1}         # the entries whose label differs from their template's word -> the original on that data index
LAST = 58                               # the game's word ends in column 58 (H3)
METROPOLIS = 6
RACE, GOAL = 0x14, 0x1A
LOADS = (0x11, 0x12, 0x13)              # the race load's modes: the label is printed in 0x11, three frames after the course load

_RUNS: dict = {}


def _col(c):
    return c - HUD_COLUMNS[0]


def _decode(row44, row45, first, last):
    """The text and the colour bases of columns first..last (row 44's words, row 45's the same + 1)."""
    text, bases = "", set()
    for c in range(first, last + 1):
        w, v = row44[_col(c)], row45[_col(c)]
        assert w != BLANK and v == w + 1, (c, hex(w), hex(v))
        text += chr(((w & 0x7F) >> 1) + 0x20)
        bases.add(w & 0xFF80)
    return text, bases


def _blank(row44, row45, first, last):
    return all(row44[_col(c)] == BLANK and row45[_col(c)] == BLANK for c in range(first, last + 1))


def _run(tmp_path_factory, romset_zip, saturn_cue, entry, reverse=False, goal=False):
    """{mode: HudFrame} of one race on `entry` (each logged mode once), and the direction flag at the race load. `goal`: the
    one-lap race of race_end.lua under the autopilot, to the goal (mode 0x1a)."""
    key = (entry, reverse, goal)
    if key not in _RUNS:
        out, conv = _seven(romset_zip, saturn_cue)
        base = tmp_path_factory.mktemp(f"hud{entry}{'r' if reverse else ''}{'g' if goal else ''}")
        env = {"VR_HUD_LOG": str(base / "hud.txt"), "VR_DIR_LOG": str(base / "dir.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"}
        if goal:
            env.update({"VR_EXTRA_LUA": str(LUA_DIR / "race_end.lua"), "VR_END_LOG": str(base / "end.txt")})
            _drive_entry(base, out, romset_zip, entry, conv[entry - 3], seconds=200, extra_env=env)
        else:
            _drive_entry(base, out, romset_zip, entry, None, seconds=45, reverse=reverse, extra_env=env)
        frames = {("load" if f.mode in LOADS else f.mode): f for f in parse_hud_log(base / "hud.txt")}
        load = next(l for l in parse_dir_log(base / "dir.txt") if l.mode == 0x11)
        _RUNS[key] = frames, load.flag
    return _RUNS[key]


def test_the_load_records_carry_the_names_the_hud_prints(romset_zip, saturn_cue):
    """No MAME: in the built set every load record's name field is the name and NULs (at most 13 letters), `race` is 0 on the
    three originals only, the converted entries' labels are LABELS; each of the seven reverse variants' records (the one `entry`
    serves at a reverse race load) has the menu entry's name, NUL-padded, and label, and a race blob."""
    out, _ = _seven(romset_zip, saturn_cue)
    d = decode_directory(out)
    lay = directory_layout()
    name = LOAD_FIELDS["name"]

    def field(rec):
        return out.program[rec - V60_PROGRAM + name:rec - V60_PROGRAM + name + NAME_LEN]

    for i, e in enumerate(d):
        assert len(e.name) < NAME_LEN and field(lay["load"] + LOAD_SIZE * i) == e.name.encode() + bytes(NAME_LEN - len(e.name)), e.name
        assert (e.race == 0) == (i < 3), e.name
    assert {i: d[i].label for i in LABELS} == LABELS
    assert [e.reverse is not None for e in d] == [False] * 3 + [True] * 7
    for e in d[3:]:
        v = e.reverse.entry
        assert (v.name, v.label) == (e.name, e.label) and v.race != 0, e.name
        assert field(e.reverse.at) == e.name.encode() + bytes(NAME_LEN - len(e.name)), e.name


@pytest.mark.parametrize("entry", range(3, 10))
def test_a_converted_course_shows_its_name(tmp_path_factory, romset_zip, saturn_cue, entry):
    """60 frames into the race: columns (59 − length)..58 of rows 44-45 read the entry's name in its label's colour base, columns
    40..(58 − length) are blank (the game's word is gone, the name's left part on cells the game leaves blank)."""
    out, _ = _seven(romset_zip, saturn_cue)
    e = decode_directory(out)[entry]
    frames, flag = _run(tmp_path_factory, romset_zip, saturn_cue, entry)
    f = frames[RACE]
    assert f.mode == RACE and flag == 0
    assert (frames["load"].row44, frames["load"].row45) == (f.row44, f.row45)      # printed at the load, kept
    first = LAST + 1 - len(e.name)
    assert _decode(f.row44, f.row45, first, LAST) == (e.name, {BASES[LABELS[entry]]}), (e.name, f)
    assert _blank(f.row44, f.row45, HUD_COLUMNS[0], first - 1), (e.name, f)


@pytest.mark.parametrize("entry", (3, 9))
def test_reverse_shows_the_same_name(tmp_path_factory, romset_zip, saturn_cue, entry):
    """REVERSE chosen on the COURSE DIRECTION screen (the flag 1 at the race load: `entry` serves the variant's record): the same
    cells as the normal race's."""
    frames, flag = _run(tmp_path_factory, romset_zip, saturn_cue, entry, reverse=True)
    normal, nflag = _run(tmp_path_factory, romset_zip, saturn_cue, entry)
    assert (flag, nflag) == (1, 0)
    assert (frames[RACE].row44, frames[RACE].row45) == (normal[RACE].row44, normal[RACE].row45)


@pytest.mark.parametrize("entry", range(3))
def test_the_originals_keep_the_games_word(tmp_path_factory, romset_zip, saturn_cue, entry):
    """Big Forest, Bay Bridge, Acropolis: columns 51-58 read the game's word in its colour, columns 40-50 are blank."""
    frames, _ = _run(tmp_path_factory, romset_zip, saturn_cue, entry)
    f = frames[RACE]
    word, colour = GAME_WORDS[entry]
    assert _decode(f.row44, f.row45, 51, LAST) == (word, {colour}), f
    assert _blank(f.row44, f.row45, HUD_COLUMNS[0], 50), f


def test_the_name_stays_to_the_goal(tmp_path_factory, romset_zip, saturn_cue):
    """Metropolis's one-lap race (race_end.lua, the autopilot): the cells at the goal (the first frame of mode 0x1a) are the
    race's, the name."""
    frames, _ = _run(tmp_path_factory, romset_zip, saturn_cue, METROPOLIS, goal=True)
    assert set(frames) == {"load", RACE, GOAL}
    race, goal = frames[RACE], frames[GOAL]
    assert (goal.row44, goal.row45) == (race.row44, race.row45)
    assert _decode(race.row44, race.row45, LAST + 1 - len("METROPOLIS"), LAST)[0] == "METROPOLIS"


@pytest.mark.parametrize("entry", sorted(SAME_INDEX))
def test_the_level_cell_is_the_games_after_the_load(tmp_path_factory, romset_zip, saturn_cue, entry):
    """Metropolis, Surfers Oval, Surfers Road (their label's colour is not their template's word's): the colour cell [0x501434]
    holds what it holds on the original of the same data index (`hudname` put the game's value back) at the end of the frame the
    label is printed: the load line is the evidence. (From the next frame on the HUD's per-frame code rewrites the cell: 60 frames
    into the race it is 3 on every course, so that line cannot tell.)"""
    frames, _ = _run(tmp_path_factory, romset_zip, saturn_cue, entry)
    original, _ = _run(tmp_path_factory, romset_zip, saturn_cue, SAME_INDEX[entry])
    out, _ = _seven(romset_zip, saturn_cue)
    d = decode_directory(out)
    assert d[entry].template == d[SAME_INDEX[entry]].template and BASES[d[entry].label] != GAME_WORDS[SAME_INDEX[entry]][1]
    assert frames["load"].attr == original["load"].attr and frames["load"].attr in (0x02, 0x82, 0x83)
    assert frames["load"].attr != (0x02, 0x83, 0x82)[d[entry].label]                  # not the colour the name was printed in
