"""Weather stage 1 (docs/superpowers/plans/2026-11-18-weather-stage-1-screens.md): the COURSE WEATHER screen after COURSE DIRECTION,
the direction screen's grey-out and hold, the weather byte, the HUD word and the no-record gate (`vrtools/arcade/weather/`).

Pascal, 17 Nov 2026: "When: an addition weather selection screen like the reverse but for weather"; 18 Nov: "btw i think storm and
rain shoudl be together (no separation on the course selection)" (two choices); after driving the prototype: "i think leave the
color the same on the selected one for the weather selection screen, you dont want the rain circuit dimmed", "the color change is
working", "i just notice a separate bug: selecting reverse or normal doesnt grey out the one not selected (will need a fix)". The
behaviour these tests hold is the prototype's they drove (out/p71weather).

The static part needs no MAME. The MAME part runs the session's set (`tests.test_tgp_build._seven`: the weather on) headless."""
import struct
from dataclasses import fields, replace

import pytest

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet


def _blank_set() -> RomSet:
    """A set of erased regions (every byte 0xff) of the real sizes: for the layout check's own logic."""
    return RomSet(program=b"\xff" * 0x100000, boot=b"\xff" * 0x40000, data=b"\xff" * 0x400000, polygons=b"\xff" * 0x1000000,
                  copro_data=b"\xff" * 0x200000, tgp_program=b"\xff" * 0x2000)


# --- static: the shared names, the tune values, the layout table, the art ------------------------------------------------------
def test_the_shared_names():
    """The names later stages rely on (master plan): the weather byte is the direction word's third byte (dirscreen.DIR_ARMED,
    free after the direction lock), DRY 0 and RAIN 1, and the modes the storm is on in (countdown, race, results, goal, the
    race-end ranking page's first two: the joined prototype's list, raining through GOAL and RESULT)."""
    from vrtools.arcade.dirscreen import DIR_ARMED
    from vrtools.arcade.weather import DRY, RAIN, RAIN_MODES, WEATHER_BYTE
    assert WEATHER_BYTE == 0x502296 == DIR_ARMED
    assert (DRY, RAIN) == (0, 1)
    assert RAIN_MODES == (0x12, 0x13, 0x14, 0x15, 0x16, 0x19, 0x1A, 0x1B, 0x1C)


def test_screen_tune_defaults_and_bounds():
    """ScreenTune's defaults are the design's (10 s, RAIN, a hold of 16 logic frames); the timer is the select countdown's start
    (32 steps a displayed second: 0x140 for 10 s, below the voice cue's 0x180); out-of-range values are refused."""
    from vrtools.arcade.weather.tune import ScreenTune
    t = ScreenTune()
    assert (t.timeout_s, t.rain_word, t.hold_frames) == (10, "RAIN", 16)
    assert t.timer == 0x140
    for bad in ({"timeout_s": 0}, {"timeout_s": 12}, {"rain_word": ""}, {"rain_word": "THUNDER"}, {"rain_word": "rain"},
                {"hold_frames": 0}, {"hold_frames": 256}):
        with pytest.raises(ValueError):
            ScreenTune(**bad)
    assert ScreenTune(rain_word="STORM").rain_word == "STORM"


def test_the_layout_table():
    """Every block has the five named fields; no two blocks of one ROM overlap; no erased-ROM block overlaps main's reserved blocks
    of the program ROM (tencourse.reserved_blocks) or the converted courses' spawn-list slots; every block lies in its space."""
    from vrtools.arcade.weather import layout
    assert [f.name for f in fields(layout.Block)] == ["name", "space", "start", "size", "owner"]
    bl = layout.blocks()
    assert bl and len({b.name for b in bl}) == len(bl)
    assert {b.space for b in bl} <= set(layout.SPACES)
    layout.check_table(bl)                                        # the table's own consistency (check(rs) adds the erased test)


@pytest.mark.parametrize("what", ["directory image", "spawn slot", "two of ours", "outside its space", "a site in a block"])
def test_the_layout_check_refuses_an_overlap(what):
    """`check_table` raises PatchError naming the two blocks for a block over main's directory image, over a spawn-list slot, over
    another of the feature's blocks, outside its space's ROM, and a site inside one of the feature's erased blocks."""
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.tencourse import CODE_FREE, spawn_list_address
    from vrtools.arcade.weather import layout
    bl = layout.blocks()
    code = next(b for b in bl if b.space == "program")
    extra = {"directory image": layout.Block("test", "program", CODE_FREE[0] + 0x100, 16, "test"),
             "spawn slot": layout.Block("test", "program", spawn_list_address(2) + 0x600, 16, "test"),
             "two of ours": layout.Block("test", "program", code.start + 8, 16, "test"),
             "outside its space": layout.Block("test", "bank0", 0x1FFFF8, 16, "test"),
             "a site in a block": layout.Block("test", "program site", code.start + 4, 4, "test")}[what]
    assert directory_layout()["end"] > CODE_FREE[0] + 0x110
    layout.check_table(bl)
    with pytest.raises(PatchError, match="'test'"):
        layout.check_table(bl + [extra])


def test_the_layout_check_wants_erased_blocks():
    """`check(rs)` (before the install) passes on an erased set and raises PatchError naming the block when one of the feature's
    erased-ROM blocks holds a byte other than 0xff (sites are not tested for erasure: they hold the game's code)."""
    from vrtools.arcade.weather import layout
    rs = _blank_set()
    layout.check(rs)
    for b in [b for b in layout.blocks() if b.space in ("program", "bank0")][:3]:
        region, base = ("program", 0x200000) if b.space == "program" else ("data", 0x100000)
        data = bytearray(getattr(rs, region))
        data[b.start - base + b.size - 1] = 0
        with pytest.raises(PatchError, match=b.name):
            layout.check(replace(rs, **{region: bytes(data)}))


def test_the_badge_and_the_caption():
    """The RAIN badge: 32 x 40 px (4 x 5 cells) of colours 0-5, a dark outline round a cloud and a bolt, transparent elsewhere; its
    converted-course tiles fit one block and its palette is BADGE_RGB's. The caption: dirgfx's strip (2 x 18 cells) in the panel's
    paper and ink, SELECT WEATHER in dirgfx's letters (W, A, H added in their style), centred, its characters one block."""
    import numpy as np
    from vrtools.arcade import dirgfx
    from vrtools.arcade.weather import screen
    bm = screen.badge_bitmap()
    assert bm.shape == (40, 32) and set(np.unique(bm)) == {0, 1, 2, 3, 4, 5}
    assert bm[0, 0] == 0 and (bm[bm > 0] > 0).any() and (bm == 1).sum() > 50
    m, chars, pal = screen.badge_tiles()
    assert m.shape == (5, 4) and len(chars) <= dirgfx.BLOCK_CHARS
    assert pal[0] == 0 and all(pal[k] == screen.rgb_word(c) for k, c in screen.BADGE_RGB.items())
    cap = screen.caption_bitmap()
    assert cap.shape == (16, 144) and set(np.unique(cap)) == {dirgfx.CAPTION_PAPER, dirgfx.CAPTION_INK}
    ink = np.nonzero((cap == dirgfx.CAPTION_INK).any(0))[0]
    assert abs((ink[0] + ink[-1] + 1) / 2 - 72) <= 1                       # centred
    assert set(screen.CAPTION.replace(" ", "")) <= set(screen.caption_glyphs())
    assert len(dirgfx._tiles(cap, empty_shared=True)[1]) <= dirgfx.BLOCK_CHARS


def test_the_grey_of_a_colour():
    """grey_word: the luminance (5 r + 9 g + 2 b) / 16 on all three guns, bit 15 set; rgb_word packs 8-bit guns to 5 bits."""
    from vrtools.arcade.weather.screen import grey_word, rgb_word
    assert grey_word(0x8000 | 31) == 0x8000 | 9 | 9 << 5 | 9 << 10
    assert grey_word(0xFFFF) == 0xFFFF
    assert rgb_word((255, 0, 8)) == 0x8000 | 1 << 10 | 31


def test_the_routines_and_their_block():
    """The screen's routines in ROM order (wxsel first: the harness tells a set with the screen by its first word), laid out at the
    layout table's code block, fit it with the tables; every routine is assembled at the address the layout gives it."""
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.weather import layout, screen
    code = layout.block("screen code")
    lay = screen.code_layout(code.start, directory_layout(), screen.Inputs.placeholder())
    assert list(lay)[:len(screen.ROUTINES)] == list(screen.ROUTINES) and screen.ROUTINES[0] == "wxsel"
    assert lay["end"] - code.start <= code.size
    first = screen.routines(code.start, {**directory_layout(), **lay}, screen.Inputs.placeholder())["wxsel"]
    assert first[:len(screen.SIGNATURE)] == screen.SIGNATURE
    other = screen.Inputs(0x2F0000, 0x28F6A0, 0xFF5000, tuple(range(0x288000, 0x288000 + 40, 4)), tuple(range(0x289000, 0x289000 + 40, 4)))
    assert screen.code_layout(code.start, directory_layout(), other) == lay      # the addresses do not depend on what the code reads


def test_parse_weather_log(tmp_path):
    """weather_log.lua's P lines: per palette its (frame, 16 words) at each change; palette_at reads the words in force at a frame."""
    from vrtools.mame.runner import palette_at, parse_weather_log
    p = tmp_path / "wx.txt"
    w0, w1 = " ".join(["0"] * 16), " ".join(["8000"] + ["ffff"] * 15)
    p.write_text(f"P 1200 66 {w0}\nP 1200 6c {w0}\nP 1262 66 {w1}\nP 1262 bad\n")
    log = parse_weather_log(p)
    assert sorted(log) == [0x66, 0x6C] and log[0x66] == [(1200, (0,) * 16), (1262, (0x8000,) + (0xFFFF,) * 15)]
    assert palette_at(log, 0x66, 1199) is None and palette_at(log, 0x66, 1261) == (0,) * 16
    assert palette_at(log, 0x66, 1300) == (0x8000,) + (0xFFFF,) * 15 and palette_at(log, 0x6C, 5000) == (0,) * 16


def test_linked_play_never_reaches_the_screens(romset_zip, saturn_cue):
    """Linked play cannot be run here (one cabinet), so by the code path, on the session's set: `olock`'s linked-play branch still
    installs the game's own handler (its `mov.w #FC27BE, A[R25]` is there once) and only its two screen handlers became `wxdir`;
    both linked course loads (dirscreen.LINKED_BANK_SITES) and the attract's two call `bankdemo`, which now clears the whole
    direction word (`mov.w #0, 502294`), so a linked race after a RAIN game reads the weather byte 0; and the HUD word and the
    record gate read only that byte."""
    from vrtools.arcade import tencourse
    from vrtools.arcade.course import BANK_SITES, DIRECTION_RAM
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.dirscreen import HANDLER, LINKED_BANK_SITES, LOCK_PATTERN
    from vrtools.arcade.origpic import origpic_layout
    from vrtools.arcade.v60asm import asm
    from vrtools.arcade.weather import WEATHER_BYTE
    from tests.test_tgp_build import _seven
    out, _ = _seven(romset_zip, saturn_cue)
    lay = directory_layout()
    ol = origpic_layout(tencourse.origpic_address(), lay)
    olock = out.program[ol["olock"] - 0x200000:ol["orows"] - 0x200000]
    wl = _code()
    assert olock.count(LOCK_PATTERN) == 1 and olock.count(asm("mov.w imm,disp[reg]", wl["wxdir"], HANDLER, "r25")) == 2
    assert olock.count(asm("mov.w imm,disp[reg]", ol["osel"], HANDLER, "r25")) == 0
    demo = asm("jsr abs", lay["bankdemo"])
    for site in (0xFE2160, 0xFE2CF7) + LINKED_BANK_SITES:
        assert site in BANK_SITES and out.boot[site - 0xFC0000:site - 0xFC0000 + len(demo)] == demo, hex(site)
    assert out.program[lay["bankdemo"] - 0x200000:].startswith(asm("mov.w imm,abs", 0, DIRECTION_RAM))
    assert WEATHER_BYTE == DIRECTION_RAM + 2


# --- the screens in MAME ---------------------------------------------------------------------------------------------------------
# The runs, each made once a session (all of them started together, VR_MAME_JOBS at a time). The hand-driven ones (VR_DIR_ANSWER=0,
# dirscreen_drive.lua) press the course at 1200 as autoplay.lua does; on COURSE DIRECTION the wheel at 128 (NORMAL, armed) from 1210,
# then 200 (REVERSE) at 1240, 128 at 1260, 200 at 1280, the gas at 1300 (the lock on 1302: REVERSE); the hold; COURSE WEATHER opens
# on 1336 and is drawn by 1348; the wheel at 128 (DRY, armed) from 1310, 200 (RAIN) at 1360, 128 at 1376, 200 at 1388, the gas at
# 1400 (the lock on 1402: RAIN); the race loads on 1600, as main's after its direction lock on 1402.
from vrtools.arcade.course import DIRECTION_RAM as _DIRECTION_RAM                                    # noqa: E402
from vrtools.arcade.select import WHEEL_FOR_ENTRY as _WHEEL                                         # noqa: E402

METROPOLIS, BAY_BRIDGE, BIG_FOREST, ALPINE, SURFERS_ROAD = 6, 1, 0, 3, 9
STEERED = ((1210, 0, 128), (1240, 0, 200), (1260, 0, 128), (1280, 0, 200), (1300, 255, 200),
           (1310, 0, 128), (1360, 0, 200), (1376, 0, 128), (1388, 0, 200), (1400, 255, 200))
DIRECTION_LOCK, WEATHER_OPEN, WEATHER_LOCK, LOAD = 1302, 1336, 1402, 1600
PALETTES = tuple(range(0x60, 0x6F))     # the A homes 0x60-0x65 and the three slots' palettes 0x66-0x6e
WX_WINDOW = (1190, 1650)
WX_TIMEOUT_TO = 2600                    # the countdown runs' palette log reaches their race load (2588 on Surfers Road)
SNAP_DRY, SNAP_RAIN = range(1350, 1358), range(1366, 1374)      # weather screen, eight frames each (the frame blinks 4 on, 4 off)
SNAP_HOLD, SNAP_LOCKED = range(1310, 1318), range(1420, 1428)
DUMPS = (1236, 1256, 1320, 1356, 1372, 1430)                    # NORMAL, REVERSE, the hold, DRY, RAIN, RAIN locked
TITLE_BOTTOM = 24                       # the title's rows 0-2: pixels 0-23
COUNTDOWN = 575                         # a screen's countdown, video frames from its first frame (test_dirscreen_build's)
SLACK = 2
LOCK_TO_LOAD = 198
HOLD_VIDEO = 2 * 16                     # the hold: 16 logic frames
RATE_LOGS = {"VR_FRAME_LOG": "{wd}/frame.txt", "VR_STALE_LOG": "{wd}/stale_list.txt"}     # frame_rate.lua, stale_list.lua (Phase 79)
ATTRACT_CLEAR = 4                       # frames from the attract's first (mode 0x02) to bankdemo's clear at its course load (measured: 2)
COIN_AT, START_HELD = 1900, (1920, 2120)  # the timeout run's coin and START, on its weather screen (open ~1813 to ~2388)
_RUNS: dict = {}


def _steps(entry, steps):
    return {"VR_DIR_ANSWER": "0", "VR_DIR_DRIVE": ",".join(f"{f}:{g}:{w}" for f, g, w in ((1200, 255, _WHEEL[entry]),) + tuple(steps))}


def _specs():
    """label -> (entry, seconds, env, extra Lua scripts, autopilot line reversed or None for none)."""
    from vrtools.arcade.ranking import NEW_TABLES, TABLE_BYTES
    from vrtools.mame.runner import LUA_DIR
    from tests.test_originals_reverse import _record_spans
    spans = ",".join(f"{a:x}-{b - 1:x}" for a, b in _record_spans())
    snaps = ",".join(map(str, sorted(set(SNAP_DRY) | set(SNAP_RAIN) | set(SNAP_HOLD) | set(SNAP_LOCKED))))
    wx_logs = lambda to: {"VR_WX_LOG": "{wd}/wx.txt", "VR_WX_PALS": ",".join(f"{p:x}" for p in PALETTES), "VR_WX_FROM": str(WX_WINDOW[0]),
                          "VR_WX_TO": str(to)}
    screens = {"VR_SNAPS": snaps, "VR_SNAPS_AFTER_START": "", "VR_SELECT_DIR": "{wd}", "VR_SELECT_DUMP": ",".join(map(str, DUMPS)),
               **wx_logs(WX_WINDOW[1]), **RATE_LOGS}
    end = {"VR_END_LOG": "{wd}/end.txt", "VR_END_TABLE": spans}
    rank = lambda inputs: {"VR_RANK_LOG": "{wd}/rank.txt", "VR_RANK_INPUT": inputs}
    drive, wx, race_end, rank_lua = (str(LUA_DIR / n) for n in ("dirscreen_drive.lua", "weather_log.lua", "race_end.lua", "ranking_attract.lua"))
    return {
        "conv": (METROPOLIS, 480, {**_steps(METROPOLIS, STEERED), **screens, **end, "VR_END_NEXT": f"{_WHEEL[SURFERS_ROAD]}:0",
                                   "VR_SELECT_DUMP_SELECT": "300"}, [drive, wx, race_end], True),
        "orig": (BAY_BRIDGE, 45, {**_steps(BAY_BRIDGE, STEERED), **screens}, [drive, wx], None),
        "dry_wet": (METROPOLIS, 200, dict(end), [race_end], False),
        "dry_main": (METROPOLIS, 200, dict(end), [race_end], False),
        # autoplay.lua's own answer RAIN (VR_RAIN=1): dry_wet's one-lap race, which records when DRY (the harness's RAIN answer; the
        # RAIN no-record test's control)
        "rain_wet": (METROPOLIS, 200, {**end, "VR_RAIN": "1"}, [race_end], False),
        # nobody answers: the course's press held (a held pedal never confirms); a coin and START held on the weather screen
        "timeout": (SURFERS_ROAD, 80, {**_steps(SURFERS_ROAD, ()), **RATE_LOGS, **wx_logs(WX_TIMEOUT_TO),
                                       **rank(f"{COIN_AT}:Coin 1:10;{START_HELD[0]}:1 Player Start:{START_HELD[1] - START_HELD[0]}")},
                    [drive, rank_lua, wx], None),
        # the direction pressed (NORMAL), RAIN steered on the weather screen and left to its countdown
        "timeout_rain": (BIG_FOREST, 80, {**_steps(BIG_FOREST, ((1210, 0, 128), (1300, 255, 128), (1310, 0, 128), (1360, 0, 200))), **RATE_LOGS,
                                          **wx_logs(WX_TIMEOUT_TO)}, [drive, wx], None),
        # the test switch on the weather screen, the test menu left (its cursor starts on EXIT), the attract, a coin and START
        "service": (ALPINE, 105, {**_steps(ALPINE, ((1210, 0, 128), (1300, 255, 128), (1310, 0, 128))),
                                 **rank("1370:Service Mode:10;1900:VR4 (Green):10;3000:Coin 1:10;3100:1 Player Start:10")}, [drive, rank_lua], None),
        # the operator's fixed course with the direction word poked to a RAIN lock before the coin
        "operator": (0, 40, {"VR_POKE": f"40dca1=2,501103=2,{_DIRECTION_RAM:x}=1,{_DIRECTION_RAM + 1:x}=4,{_DIRECTION_RAM + 2:x}=1"}, [], None),
    }


def _make(tmp_path_factory, romset_zip, saturn_cue, label, build):
    from vrtools.convert.reverse import reverse_points
    from vrtools.mame.runner import LUA_DIR, run_mame, write_centreline
    from tests.test_race_build import _drive_line
    from tests.test_tgp_build import _seven
    entry, seconds, env, extra, line = _specs()[label]
    wd = tmp_path_factory.mktemp(label)
    env = {k: str(v).replace("{wd}", str(wd)) for k, v in env.items()}
    full = {"VR_COURSE": "0", "VR_WHEEL": str(_WHEEL[entry]), "VR_SNAPS": "", "VR_DIR_LOG": str(wd / "dir.txt"),
            "VR_DIRECTION_RAM": f"{_DIRECTION_RAM:x}", "VR_HUDROWS_LOG": str(wd / "rows.txt"), **env}
    if extra:
        full["VR_EXTRA_LUA"] = ";".join(extra)
    if line is not None:
        c = _seven(romset_zip, saturn_cue)[1][entry - 3]
        pts = _drive_line(c)
        full["VR_AUTOPILOT"] = str(write_centreline(wd / "line.csv", reverse_points(pts) if line else pts))
    run_mame(LUA_DIR / "autoplay.lua", seconds, wd, build, env=full, timeout=3600)
    return wd


def _run(tmp_path_factory, romset_zip, saturn_cue, label):
    """The work directory of run `label`; the first call makes every run (in parallel, VR_MAME_JOBS at a time)."""
    if not _RUNS:
        from concurrent.futures import ThreadPoolExecutor
        from tests.test_tgp_build import _build, _seven
        from tests.test_weather_dry import _seven_dry
        wet = _build(tmp_path_factory.mktemp("build_wet"), romset_zip, _seven(romset_zip, saturn_cue)[0])
        dry = _build(tmp_path_factory.mktemp("build_dry"), romset_zip, _seven_dry(romset_zip, saturn_cue)[0])
        labels = list(_specs())
        with ThreadPoolExecutor(len(labels)) as ex:
            done = ex.map(lambda l: _make(tmp_path_factory, romset_zip, saturn_cue, l, dry if l == "dry_main" else wet), labels)
            _RUNS.update(zip(labels, done))
    return _RUNS[label]


def _code():
    """The screen's routine addresses at the layout's code block."""
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.weather import layout, screen
    return screen.code_layout(layout.block("screen code").start, directory_layout(), screen.Inputs.placeholder())


def _lines(wd):
    from vrtools.mame.runner import parse_dir_log
    return parse_dir_log(wd / "dir.txt")


def _at(lines, frame):
    """The dir log's line in force at the end of `frame`."""
    return [l for l in lines if l.frame <= frame][-1]


def _first(lines, test, after=0):
    return next((l for l in lines if l.frame > after and test(l)), None)


def _events(lines):
    """(course lock, direction screen's first frame, direction lock, weather screen's first frame, weather lock, race load): the
    frames where the select entity's handler becomes the course lock (DIR_PHASE 0), DIR_PHASE becomes 1 and then 2 (the handler
    `wxdir`, then `wxsel`), DIR_PHASE OPEN, the course lock again with DIR_PHASE LOCKED, and the first mode-0x11 line. (By the
    direction word, not by the routines' addresses, so the same reading serves a prototype set.)"""
    from vrtools.arcade.dirscreen import COURSE_LOCK
    from vrtools.arcade.weather import screen
    course = _first(lines, lambda l: l.handler == COURSE_LOCK and l.phase == 0)
    first = course and _first(lines, lambda l: l.mode == 0x10 and l.phase == 1, course.frame)
    dlock = first and _first(lines, lambda l: l.phase == screen.DIRECTION_LOCKED, first.frame)
    opened = dlock and _first(lines, lambda l: l.phase == screen.OPEN, dlock.frame)
    wlock = opened and _first(lines, lambda l: l.handler == COURSE_LOCK and l.phase == screen.LOCKED, opened.frame)
    load = _first(lines, lambda l: l.mode == 0x11)
    return course, first, dlock, opened, wlock, load


def test_the_screens_chain_and_the_race_loads_where_it_did(tmp_path_factory, romset_zip, saturn_cue):
    """Both hand-driven runs: the course lock on 1202, COURSE DIRECTION from 1204, its lock on DIRECTION_LOCK (REVERSE, the
    handler `wxsel`), the hold (DIR_PHASE HOLDING, 16 logic frames), COURSE WEATHER open on WEATHER_OPEN, its lock on WEATHER_LOCK
    (RAIN: the weather byte 1, DIR_PHASE LOCKED, the game's lock handler), the race load LOCK_TO_LOAD frames later, on LOAD, as
    main's after its direction lock on 1402; the byte 1 and the flag 1 through the race."""
    from vrtools.arcade.weather import screen
    for label in ("conv", "orig"):
        lines = _lines(_run(tmp_path_factory, romset_zip, saturn_cue, label))
        course, first, dlock, opened, wlock, load = _events(lines)
        print("CHAIN", label, [e and e.frame for e in (course, first, dlock, opened, wlock, load)])
        assert (course.frame, first.frame, dlock.frame, opened.frame, wlock.frame, load.frame) == (1202, 1204, DIRECTION_LOCK, WEATHER_OPEN,
                                                                                               WEATHER_LOCK, LOAD), label
        wl = _code()
        assert first.handler == wl["wxdir"] and dlock.handler == wl["wxsel"], (first, dlock)
        assert dlock.flag == 1 and dlock.phase == screen.DIRECTION_LOCKED, dlock
        hold = [l for l in lines if dlock.frame < l.frame < opened.frame]
        assert {l.phase for l in hold} == {screen.HOLDING} and opened.frame - dlock.frame == HOLD_VIDEO + 2, (label, dlock, opened)
        assert wlock.armed == 1 and wlock.shown == 1 and wlock.flag == 1, wlock
        end = _first(lines, lambda l: not 0x11 <= l.mode <= 0x14, load.frame)
        race = [l for l in lines if load.frame <= l.frame < (end.frame if end else 1 << 30)]
        assert race and all(l.armed == 1 and l.flag == 1 for l in race), race[:3]


def _looks(out, entry):
    """{(screen, look, choice): {palette: 16 words}} the palettes 0x60-0x6e must hold: screen "direction" or "weather", look
    "choosing" or "locked", choice 0 / 1 (the side shown or chosen). Independent of the weather code where main has the data:
    the picture record's normal / chosen / grey sets (B, slots 0 and 2); an original's A palettes (origpic.layers: its normal look
    on its own home, the right side's on the next art's) and its arrows' ring palettes (origpic.picture_data); the badge's
    (BADGE_RGB and its grey; an original's composed groups, screen.original_badge)."""
    import struct
    from vrtools.arcade import dirgfx, origpic, tencourse
    from vrtools.arcade.select import SLOT_PAL
    from vrtools.arcade.weather import screen
    from tests.test_tencourse import _records
    _, recs, read = _records(out)
    rec = recs[entry]
    sets = {k: struct.unpack("<48H", read(getattr(rec, f"{k}_addr"), 96)) for k in ("normal", "chosen", "grey")}
    slot_pal = [(SLOT_PAL[s] - 0x900000) // 32 for s in (0, 2)]
    res = {}
    for scr in ("direction", "weather"):
        for look in ("choosing", "locked"):
            for choice in (0, 1):
                pals = {}
                for side in (0, 1):
                    words = sets["normal" if look == "choosing" else "chosen"] if side == choice else sets["grey"]
                    for k in range(3):
                        pals[slot_pal[side] + k] = tuple(words[16 * k:16 * k + 16])
                res[(scr, look, choice)] = pals
    if entry >= 3:
        _, chars, bpal = screen.badge_tiles()
        for look in ("choosing", "locked"):
            for choice in (0, 1):
                res[("weather", look, choice)][screen.BADGE_BLOCKS[0] >> 7] = tuple(bpal if choice else [screen.grey_word(w) if w else 0 for w in bpal])
        return res
    art, nxt = entry, (entry + 1) % 3
    ly = origpic.layers(out, art)
    homes = (origpic.A_HOME[art] >> 7, origpic.A_HOME[nxt] >> 7)
    tab = struct.unpack_from("<6I", out.program, origpic.table_address(tencourse.origpic_address()) - 0x200000)
    _, _, info = origpic.picture_data(out, art, tab[art], tab[3 + art])
    rows, cols, bchars, blooks, words = screen.original_badge(out, art, list(sets["normal"]), list(sets["grey"]))
    for (scr, look, choice), pals in res.items():
        for side in (0, 1):
            mine = side == choice
            a = ly.a_looks["normal" if look == "choosing" else "chosen"] if mine else ly.a_looks["grey"]
            pals[homes[side]], pals[homes[side] + 1] = tuple(a[0]), tuple(a[1])
            if scr == "direction":
                for lk, blk in zip(info["ring"][side]["looks"], info["blocks"][side]):
                    pals[blk >> 7] = struct.unpack("<16H", read(lk[("normal" if look == "choosing" else "chosen") if mine else "grey"], 32))
        if scr == "weather":
            for lk, blk in zip(blooks, screen.BADGE_BLOCKS):
                pals[blk >> 7] = tuple(lk["normal" if choice else "grey"])
    return res


def _palettes(wd):
    from vrtools.mame.runner import parse_weather_log
    return parse_weather_log(wd / "wx.txt")


def _state(log, frame, pals):
    from vrtools.mame.runner import palette_at
    return {p: palette_at(log, p, frame) for p in pals}


# per run: (direction screen's changes, the choices it showed), (weather screen's changes, the choices it showed)
CHOOSING = {"conv": ((3, {0, 1}), (3, {0, 1})), "orig": ((3, {0, 1}), (3, {0, 1})),
            "timeout": ((0, {0}), (0, {0})), "timeout_rain": ((0, {0}), (1, {0, 1}))}


@pytest.mark.parametrize("label", list(CHOOSING))
def test_every_choosing_frame_shows_the_choice_in_colour_and_the_other_grey(tmp_path_factory, romset_zip, saturn_cue, label):
    """Pascal's "the color change is working" and their direction screen fix, as palette RAM (weather_log.lua, every frame): on
    both screens, on every frame while choosing whose choice was the same at the two frames before (the look is written in the
    logic frame of the change, and MAME can catch a palette half written on that frame), the side shown is in its normal colours
    and the other grey (`_looks`), on a converted course (Metropolis, Surfers Road) and an original (Bay Bridge, Big Forest): the
    steered runs change the choice three times on each screen; the countdown runs show NORMAL and DRY throughout (nobody
    answering), or DRY then RAIN (RAIN steered and left)."""
    from tests.test_tgp_build import _seven
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, label)
    out, _ = _seven(romset_zip, saturn_cue)
    entry = _specs()[label][0]
    lines, log = _lines(wd), _palettes(wd)
    looks = _looks(out, entry)
    course, first, dlock, opened, wlock, load = _events(lines)
    seen = {"direction": [0, set()], "weather": [0, set()]}
    changes = {"direction": 0, "weather": 0}
    for f in range(first.frame, wlock.frame):
        now, a, b = _at(lines, f), _at(lines, f - 1), _at(lines, f - 2)
        scr = {1: "direction", 3: "weather"}.get(now.phase)
        if scr is None or now.shown not in (0, 1):
            continue
        if a.shown != now.shown and a.shown in (0, 1):
            changes[scr] += 1
        if not (now.shown == a.shown == b.shown and now.phase == a.phase == b.phase):
            continue
        want = looks[(scr, "choosing", now.shown)]
        got = _state(log, f, want)
        wrong = [hex(p) for p, w in want.items() if got[p] != w]
        assert not wrong, (label, scr, f, now.shown, wrong)
        seen[scr][0] += 1
        seen[scr][1].add(now.shown)
    print("CHOOSING", label, {k: (v[0], sorted(v[1])) for k, v in seen.items()}, changes)
    (dc, ds), (wc, ws) = CHOOSING[label]
    assert seen["direction"][0] > 60 and seen["weather"][0] > 30 and (seen["direction"][1], seen["weather"][1]) == (ds, ws), seen
    assert changes == {"direction": dc, "weather": wc}, changes


# per run: the direction locked, the weather locked (the steered runs by gas, the countdown runs by their countdowns)
LOCKS = {"conv": (1, 1), "orig": (1, 1), "timeout": (0, 0), "timeout_rain": (0, 1)}


@pytest.mark.parametrize("label", list(LOCKS))
def test_the_lock_looks_and_the_hold(tmp_path_factory, romset_zip, saturn_cue, label):
    """From two frames after the direction lock to the weather screen's first frame (the hold, 16 logic frames) the palettes are
    the direction's lock look for its choice: the chosen side in the record's chosen set, the other grey (an original: origpic's
    chosen and grey A and ring palettes); from two frames after the weather lock to the race load, the weather's lock look for its
    choice (RAIN: the badge in its colours; DRY: grey). Locked by gas (Metropolis, Bay Bridge: REVERSE, RAIN) and by the countdowns
    (Surfers Road: NORMAL, DRY; Big Forest, an original: NORMAL by gas, RAIN by the countdown)."""
    from tests.test_tgp_build import _seven
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, label)
    out, _ = _seven(romset_zip, saturn_cue)
    entry = _specs()[label][0]
    lines, log = _lines(wd), _palettes(wd)
    looks = _looks(out, entry)
    course, first, dlock, opened, wlock, load = _events(lines)
    dchoice, wchoice = LOCKS[label]
    assert (dlock.flag, wlock.armed) == (dchoice, wchoice), (dlock, wlock)
    end = min(load.frame, int(_specs()[label][2]["VR_WX_TO"]))
    assert end - wlock.frame > 100, (wlock, end)
    for scr, choice, a, b in (("direction", dchoice, dlock.frame + 2, opened.frame), ("weather", wchoice, wlock.frame + 2, end)):
        want = looks[(scr, "locked", choice)]
        for f in range(a, b):
            got = _state(log, f, want)
            wrong = [hex(p) for p, w in want.items() if got[p] != w]
            assert not wrong, (label, scr, f, wrong)


def _snaps(wd, frames):
    import numpy as np
    from PIL import Image
    allf = sorted(set(SNAP_DRY) | set(SNAP_RAIN) | set(SNAP_HOLD) | set(SNAP_LOCKED))
    files = sorted((wd / "snap" / "vr").glob("*.png"))
    assert len(files) >= len(allf), (len(files), len(allf))
    return np.stack([np.asarray(Image.open(files[allf.index(f)]).convert("RGB")).astype(int) for f in frames])


def _moving(st):
    moving = (st.max(0) - st.min(0)).sum(2) > 0
    moving[240:] = False                # the countdown below changes too
    return moving


@pytest.mark.parametrize("label", ["conv", "orig"])
def test_the_frame_sits_round_the_choice_below_the_title(tmp_path_factory, romset_zip, saturn_cue, label):
    """The yellow cursor frame on COURSE WEATHER (the pixels that blink over eight snapshots, four on, four off): centred on the
    picture shown (DRY left, RAIN right: 16 x 21 cells from row PIC_ROW) within 2 px, round it, and never on the title (rows 0-2:
    its top below pixel TITLE_BOTTOM)."""
    import numpy as np
    from vrtools.arcade.weather import screen
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, label)
    lines = _lines(wd)
    for choice, frames in ((0, SNAP_DRY), (1, SNAP_RAIN)):
        assert {_at(lines, f).shown for f in range(frames[0] - 2, frames[-1] + 1)} == {choice}
        ys, xs = np.nonzero(_moving(_snaps(wd, frames)))
        assert len(xs) > 200, len(xs)
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
        c = screen.PIC_COLS[choice]
        px0, py0, px1, py1 = 8 * c, 8 * screen.PIC_ROW, 8 * (c + 16) - 1, 8 * (screen.PIC_ROW + 21) - 1
        print("FRAME", label, choice, (x0, y0, x1, y1), (px0, py0, px1, py1))
        assert abs((x0 + x1) - (px0 + px1)) <= 4 and abs((y0 + y1) - (py0 + py1)) <= 4, (label, choice)
        assert x0 < px0 and y0 < py0 and x1 > px1 and y1 > py1 and y0 >= TITLE_BOTTOM, (label, choice, y0)


@pytest.mark.parametrize("label", ["conv", "orig"])
def test_the_frame_is_steady_after_the_weather_lock(tmp_path_factory, romset_zip, saturn_cue, label):
    """After the weather lock (the game's handler 0xfc27be, `start` calling `wxdone`) the frame no longer blinks: in the eight
    SNAP_LOCKED snapshots every pixel that blinked while RAIN was chosen holds the frame's on look."""
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, label)
    before, after = _snaps(wd, SNAP_RAIN), _snaps(wd, SNAP_LOCKED)
    mask = _moving(before)
    looks = {img[mask].tobytes(): img[mask] for img in before}
    assert len(looks) == 2, len(looks)
    on = max(looks.values(), key=lambda px: (px[:, 0] + px[:, 1] - 2 * px[:, 2]).mean())
    assert all((img[mask] == on).all() for img in after), [int((img[mask] != on).any(1).sum()) for img in after]


@pytest.mark.parametrize("label", ["conv", "orig"])
def test_the_hold_keeps_the_directions_frame(tmp_path_factory, romset_zip, saturn_cue, label):
    """During the hold the direction's frame stays round its chosen side (REVERSE, the right picture, COURSE DIRECTION's
    geometry) and no weather screen piece shows yet: the blinking pixels of SNAP_HOLD centred on the direction's right picture."""
    import numpy as np
    from vrtools.arcade.dirscreen import PICTURE_CELLS
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, label)
    ys, xs = np.nonzero(_moving(_snaps(wd, SNAP_HOLD)))
    assert len(xs) > 200, len(xs)
    r, c = PICTURE_CELLS[1]
    assert abs((xs.min() + xs.max()) - (16 * c + 127)) <= 4 and abs((ys.min() + ys.max()) - (16 * r + 167)) <= 4, (xs.min(), ys.min(), xs.max(), ys.max())


@pytest.mark.parametrize("label", ["conv", "orig", "timeout", "timeout_rain"])
def test_no_logic_frame_is_skipped_on_the_screens(tmp_path_factory, romset_zip, saturn_cue, label):
    """From the course lock to the race load, through both screens, their drawing, the hold and the locks, the game's logic frame
    counter steps by one every two video frames, never more slowly."""
    lines = _lines(_run(tmp_path_factory, romset_zip, saturn_cue, label))
    course, first, dlock, opened, wlock, load = _events(lines)
    window = [l for l in lines if course.frame <= l.frame <= load.frame]
    steps, prev = [], None
    for l in window:
        if prev is None or l.counter != prev.counter:
            if prev is not None:
                steps.append((l.frame, l.frame - prev.frame, l.counter - prev.counter))
            prev = l
    print("STEPS", label, len(steps), course.frame, load.frame)
    assert len(steps) >= (load.frame - course.frame) // 2 - 1
    assert all(df == 2 and dc == 1 for _, df, dc in steps), [s for s in steps if s[1:] != (2, 1)][:6]


@pytest.mark.parametrize("label", ["conv", "orig", "timeout", "timeout_rain"])
def test_the_screens_frames_hold_the_rate(tmp_path_factory, record_property, romset_zip, saturn_cue, label):
    """frame_rate.lua and stale_list.lua (Phase 79) over both screens, from the course lock to the race load, on a converted course
    and an original, steered (`conv`, `orig`: choosing, four changes on each screen, both locks, the hold) and left to the
    countdowns (`timeout` converted, `timeout_rain` original): no stale display list (tests/test_frame_rate.py's `_stale` with the
    course lock as the stretch's start and the race load as its end: a race run's rule, which leaves out only the pass after the
    long passes before the stretch, the boot's; no pass on the screens is excused, and none is a long pass), the game's overrun
    counter still, no object list skipped; each screen's busiest pass is recorded against DEADLINE_MS, whatever the outcome, in
    the session's weather_rate_summary.txt (one line a run, as tests/test_frame_rate.py's rate_summary.txt) and as the test's
    properties (each screen's first pass waits out the video frame's end before its first clear, as main's direction screen does
    on an original)."""
    from types import SimpleNamespace
    from vrtools.mame.framerate import DEADLINE_MS, FRAME_US, parse_frame_log
    from tests.test_frame_rate import _stale
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, label)
    course, first, dlock, opened, wlock, load = _events(_lines(wd))
    every = parse_frame_log(wd / "frame.txt")
    frames = [f for f in every if course.frame <= f.frame < load.frame]
    try:
        stale = _stale(SimpleNamespace(wd=wd, frames=every, start=course.frame, end=load.frame))
    except (AssertionError, ValueError) as e:              # the summary line is written all the same (as _stale_result does)
        stale = f"stale-list check failed: {e}"
    worst = lambda a, b: max((f for f in frames if a <= f.frame < b), key=lambda f: f.busy_us)
    d, w = worst(first.frame, opened.frame), worst(opened.frame, load.frame)
    line = (f"{label} (entry {_specs()[label][0]}): passes {len(frames)} ({course.frame}-{load.frame}); COURSE DIRECTION and the hold: "
            f"worst busy {d.busy_us / 1000:.2f} ms at frame {d.frame}; COURSE WEATHER to the load: worst busy {w.busy_us / 1000:.2f} ms at "
            f"frame {w.frame}; against the {DEADLINE_MS} ms deadline (margins {DEADLINE_MS - d.busy_us / 1000:.2f} / "
            f"{DEADLINE_MS - w.busy_us / 1000:.2f} ms); 0x501148 {frames[0].overrun}->{frames[-1].overrun}; lists skipped "
            f"{sum(f.skipped for f in frames)}; stale lists {stale}")
    with open(tmp_path_factory.getbasetemp() / "weather_rate_summary.txt", "a") as out:
        out.write(line + "\n")
    record_property("direction_worst_busy_us", d.busy_us)
    record_property("weather_worst_busy_us", w.busy_us)
    record_property("deadline_ms", DEADLINE_MS)
    print("RATE", line)
    assert len(frames) > 150, len(frames)
    assert all(f.busy_us < FRAME_US for f in frames), [f for f in frames if f.busy_us >= FRAME_US][:3]
    assert stale == [], (label, stale)
    assert len({f.overrun for f in frames}) == 1 and all(f.skipped == 0 for f in frames), [f for f in frames if f.skipped][:3]


def test_nobody_answers_dry(tmp_path_factory, romset_zip, saturn_cue):
    """Review Focus 1: the course's press held and nothing else (a held pedal never confirms): COURSE DIRECTION locks on its
    countdown (NORMAL), the hold, COURSE WEATHER locks on its countdown COUNTDOWN frames after it opened with no gas edge
    meanwhile, DRY: the weather byte 0 at the lock, the load LOCK_TO_LOAD frames later and through the race. A coin (COIN_AT)
    and START held (START_HELD) on the weather screen change none of it, and the transmission stays the automatic latched at the
    course lock."""
    lines = _lines(_run(tmp_path_factory, romset_zip, saturn_cue, "timeout"))
    course, first, dlock, opened, wlock, load = _events(lines)
    print("TIMEOUT", [e and e.frame for e in (course, first, dlock, opened, wlock, load)])
    assert abs(dlock.frame - first.frame - COUNTDOWN) <= SLACK and dlock.flag == 0, (first, dlock)
    assert opened.frame - dlock.frame == HOLD_VIDEO + 2
    assert opened.frame < COIN_AT < START_HELD[1] < wlock.frame and abs(wlock.frame - opened.frame - COUNTDOWN) <= 2 * SLACK, (opened, wlock)
    assert not any(l.edge for l in lines if opened.frame <= l.frame <= wlock.frame)
    assert any(l.start for l in lines if START_HELD[0] < l.frame < START_HELD[1])     # START held, as the game reads it
    assert wlock.armed == 0 and load.frame - wlock.frame == LOCK_TO_LOAD, (wlock, load)
    race = [l for l in lines if l.frame >= load.frame and 0x11 <= l.mode <= 0x14]
    assert race and all(l.armed == 0 and l.flag == 0 and l.manual == course.manual == 0 for l in race), race[:3]


def test_the_countdown_locks_the_choice_shown(tmp_path_factory, romset_zip, saturn_cue):
    """As COURSE DIRECTION's countdown: RAIN steered (Big Forest) and left there, the countdown locks RAIN COUNTDOWN frames after
    the screen opened, with no gas edge; the byte 1 through the race."""
    lines = _lines(_run(tmp_path_factory, romset_zip, saturn_cue, "timeout_rain"))
    course, first, dlock, opened, wlock, load = _events(lines)
    assert dlock.frame == DIRECTION_LOCK and dlock.flag == 0, dlock
    assert abs(wlock.frame - opened.frame - COUNTDOWN) <= 2 * SLACK and wlock.armed == 1, (opened, wlock)
    assert not any(l.edge for l in lines if opened.frame + 2 <= l.frame <= wlock.frame)
    race = [l for l in lines if l.frame >= load.frame and 0x11 <= l.mode <= 0x14]
    assert race and all(l.armed == 1 for l in race)


def test_the_test_switch_on_the_weather_screen(tmp_path_factory, romset_zip, saturn_cue):
    """Review Focus 1: the test switch on COURSE WEATHER (frame 1370, the screen open, its byte the arming flag 1) enters the test
    mode, the game's select stops; leaving it (EXIT, frame 1900) restarts the game: from that restart every line has the whole
    direction word 0 through the attract; a coin and START (3000, 3100) open a select screen with the word 0, whose course lock
    (its countdown) opens COURSE DIRECTION again, then (nobody answering) the hold, COURSE WEATHER and its countdown lock (DRY), the
    race load LOCK_TO_LOAD frames later and the race's first frame (mode 0x12) with the word's weather byte and flag 0: no screen is
    stuck."""
    from vrtools.arcade.weather import screen
    lines = _lines(_run(tmp_path_factory, romset_zip, saturn_cue, "service"))
    on = _at(lines, 1368)
    assert on.mode == 0x10 and on.phase == screen.OPEN and on.armed == 1, on
    restart = _first(lines, lambda l: l.mode not in (0x10,), 1370)
    assert restart and 1900 < restart.frame < 2600, restart
    after = [l for l in lines if restart.frame <= l.frame < 3000]
    assert any(l.mode in (0x02, 0x03) for l in after) and all((l.flag, l.phase, l.armed) == (0, 0, 0) for l in after), after[:3]
    select = _first(lines, lambda l: l.mode == 0x10, 3000)
    assert select and (select.flag, select.phase, select.armed) == (0, 0, 0), select
    game = [l for l in lines if l.frame > 3000]
    course, first, dlock, opened, wlock, load = _events(game)
    print("SERVICE new game", [e and e.frame for e in (course, first, dlock, opened, wlock, load)])
    assert course and first and dlock and opened and wlock and load, (course, first, dlock, opened, wlock, load)
    assert wlock.armed == 0 and load.frame - wlock.frame == LOCK_TO_LOAD, (wlock, load)
    race = _first(game, lambda l: l.mode == 0x12, load.frame)
    assert race and race.armed == 0 and race.flag == 0, race


def test_the_byte_is_zero_after_a_rain_game_and_on_a_second_game(tmp_path_factory, romset_zip, saturn_cue):
    """Review Focus 5 (the conv run: a RAIN race on Metropolis, one lap, then the attract and a second game on Surfers Road,
    answered DRY by race_end.lua as autoplay.lua answers): the RAIN race reads 1 to its end, through the results and the ranking
    page; the game over's attract load clears the whole direction word (bankdemo) within the attract's first ATTRACT_CLEAR frames,
    before any other mode, and every line is 0 from there to the second game's select, which starts with it 0; its race is DRY."""
    from vrtools.arcade.weather import screen
    lines = _lines(_run(tmp_path_factory, romset_zip, saturn_cue, "conv"))
    load = _first(lines, lambda l: l.mode == 0x11)
    end = _first(lines, lambda l: not 0x11 <= l.mode <= 0x14, load.frame)
    assert all(l.armed == 1 for l in lines if load.frame <= l.frame < end.frame)
    attract = _first(lines, lambda l: l.mode == 0x02, end.frame)
    second = _first(lines, lambda l: l.mode == 0x10, attract.frame)
    assert attract and second, (attract, second)
    cleared = _first(lines, lambda l: (l.flag, l.phase, l.armed) == (0, 0, 0), attract.frame - 1)
    assert cleared.mode == 0x02 and cleared.frame - attract.frame <= ATTRACT_CLEAR, (attract, cleared)
    assert all((l.flag, l.phase, l.armed) == (0, 0, 0) for l in lines if cleared.frame <= l.frame < second.frame)
    assert (second.flag, second.phase, second.armed) == (0, 0, 0), second
    game = [l for l in lines if l.frame >= second.frame]
    c2, f2, d2, o2, w2, load2 = _events(game)
    assert w2 and load2 and w2.armed == 0 and w2.phase == screen.LOCKED, (w2, load2)
    assert all(l.armed == 0 for l in game if l.frame >= load2.frame and 0x11 <= l.mode <= 0x14)


def test_the_operator_fixed_course_is_dry(tmp_path_factory, romset_zip, saturn_cue):
    """Review Focus 5: the operator's fixed course with the direction word poked to a RAIN lock (flag 1, DIR_PHASE LOCKED, the byte
    1) before the coin: from the first select frame the word is 0, the select entity runs the SHIFT MODE SELECTOR's chain (no
    screen), and the race reads the byte 0; no RAIN on its HUD."""
    from vrtools.mame.runner import parse_hudrows_log
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, "operator")
    lines = _lines(wd)
    assert any(l.armed == 1 and l.frame < 600 for l in lines)
    select = [l for l in lines if l.mode == 0x10]
    assert select and all((l.flag, l.phase, l.armed) == (0, 0, 0) for l in select), select[:2]
    assert 0xFC29B3 in {l.handler for l in select}
    race = [l for l in lines if 0x11 <= l.mode <= 0x14]
    assert race and all(l.armed == 0 for l in race)
    rows = [r for r in parse_hudrows_log(wd / "rows.txt")[0] if r.tag == "race"]
    assert rows and _blank46(rows[0].rows, 19, 63)


# --- the HUD word -------------------------------------------------------------------------------------------------------------
BLANKS = (0x8020, 0x0020)


def _blank46(rows, a, b):
    return all(rows[r][c] in BLANKS for r in (46, 47) for c in range(a, b + 1))


def _word46(rows, a, b):
    """(text, colour bases) of rows 46-47's columns a..b (row 47 holding each word + 1, the printer's two halves)."""
    text, bases = "", set()
    for c in range(a, b + 1):
        w, v = rows[46][c], rows[47][c]
        assert w not in BLANKS and v == w + 1, (c, hex(w), hex(v))
        text += chr(((w & 0x7F) >> 1) + 0x20)
        bases.add(w & 0xFF80)
    return text, bases


@pytest.mark.parametrize("label,first,reverse_from", [("conv", 47, 52), ("orig", 46, 51), ("timeout_rain", 55, None), ("timeout", None, None),
                                                     ("dry_wet", None, None)])
def test_the_hud_word(tmp_path_factory, romset_zip, saturn_cue, label, first, reverse_from):
    """RAIN in white under the course's name in a RAIN race (its last letter in column 58: Big Forest), left of REVERSE in a reverse
    one (a space between: Metropolis, REVERSE from 52; Bay Bridge, REVERSE from 51); nothing on rows 46-47 in a DRY race but
    REVERSE in a reverse race (Surfers Road, Metropolis normal). Read 60 frames into the race (hudrows_log.lua's "race" line); the
    white is the HUD font's fourth colour, none of the three level words' (blue, orange, red)."""
    from vrtools.arcade.hudname import REVERSE_TEXT
    from vrtools.mame.runner import parse_hudrows_log
    from tests.test_hudreverse_build import BASES
    rows = [r for r in parse_hudrows_log(_run(tmp_path_factory, romset_zip, saturn_cue, label) / "rows.txt")[0] if r.tag == "race" and r.race == 1]
    assert rows, label
    rw = rows[0].rows
    if first is None:
        assert _blank46(rw, 19, 63), label
        return
    text, bases = _word46(rw, first, first + 3)
    print("HUD", label, text, [hex(b) for b in bases])
    assert text == "RAIN" and len(bases) == 1 and not bases & set(BASES), (text, bases)
    if reverse_from is None:
        assert _blank46(rw, 19, first - 1) and _blank46(rw, first + 4, 63)
    else:
        assert _word46(rw, reverse_from, reverse_from + 6)[0] == REVERSE_TEXT.decode()
        assert _blank46(rw, 19, first - 1) and _blank46(rw, first + 4, reverse_from - 1) and _blank46(rw, reverse_from + 7, 63)


# --- records ----------------------------------------------------------------------------------------------------------------------
def _end(wd):
    """race_end.lua's log: (the first race's load, its mode lines after the race up to the attract, the writes into the battery's
    best-time spans from the load to the attract)."""
    load, modes, writes, attract = None, [], [], None
    for row in open(wd / "end.txt"):
        tag, *f = row.split()
        if tag == "L" and load is None:
            load = int(f[0])
        elif tag == "M" and load is not None and attract is None and int(f[0]) >= load:
            m = int(f[1], 16)
            if m == 0x02:
                attract = int(f[0])
            if not modes or modes[-1] != m:
                modes.append(m)
        elif tag == "W" and load is not None and attract is None:
            writes.append((int(f[1], 16), int(f[2], 16), int(f[3], 16), int(f[4], 16)))
    return load, modes, writes, attract


def test_a_rain_race_records_nothing(tmp_path_factory, romset_zip, saturn_cue):
    """A one-lap RAIN race (the conv run: Metropolis in reverse, its screens steered by hand): from its load to the attract no write in
    any best-time table or slot of the battery RAM, and no name entry (mode 0x1e) among the modes after the finish. (This lap would
    not reach the reverse table's fourth time either: the control that the gate does the work is
    test_the_rain_race_s_lap_would_record_dry.)"""
    load, modes, writes, attract = _end(_run(tmp_path_factory, romset_zip, saturn_cue, "conv"))
    print("RAIN END modes", [hex(m) for m in modes], "writes", len(writes))
    assert load and attract and 0x1A in modes and 0x16 in modes, [hex(m) for m in modes]
    assert 0x1E not in modes and writes == [], (writes[:4],)


def test_autoplay_answers_rain_and_dry(tmp_path_factory, romset_zip, saturn_cue):
    """The harness's own answer (autoplay.lua) on the same race, Metropolis: with VR_RAIN=1 the weather screen locks RAIN on
    WEATHER_LOCK (the weather byte 1) and the race loads on LOAD, the byte 1 at its first frame; without it, DRY on the same frames,
    the byte 0. (Later stages' rain runs rely on VR_RAIN.)"""
    for label, want in (("rain_wet", 1), ("dry_wet", 0)):
        lines = _lines(_run(tmp_path_factory, romset_zip, saturn_cue, label))
        course, first, dlock, opened, wlock, load = _events(lines)
        print("AUTOPLAY", label, [e and e.frame for e in (course, first, dlock, opened, wlock, load)])
        assert (dlock.frame, dlock.flag, wlock.frame, wlock.armed, load.frame) == (DIRECTION_LOCK, 0, WEATHER_LOCK, want, LOAD), (label, dlock, wlock, load)
        assert load.armed == want and load.flag == 0, (label, load)


def test_the_rain_race_s_lap_would_record_dry(tmp_path_factory, romset_zip, saturn_cue):
    """The control the RAIN no-record tests need: the same one-lap race on Metropolis (autoplay's answer, its autopilot), DRY, writes
    into the best-time spans and shows the name entry; RAIN, it writes nothing and shows none. Both load on LOAD. (Measured in fix
    round 1: the conv run's one-lap REVERSE race does not reach the reverse table's fourth time, so test_a_rain_race_records_nothing
    alone could not fail on the record; this pair can.)"""
    dry = _end(_run(tmp_path_factory, romset_zip, saturn_cue, "dry_wet"))
    rain = _end(_run(tmp_path_factory, romset_zip, saturn_cue, "rain_wet"))
    print("CONTROL dry writes", len(dry[2]), [hex(m) for m in dry[1]], "rain writes", len(rain[2]), [hex(m) for m in rain[1]])
    assert dry[0] == rain[0] == LOAD and dry[3] and rain[3], (dry[0], rain[0], dry[3], rain[3])
    assert dry[2] and 0x1E in dry[1], dry[1]
    assert rain[2] == [] and 0x1E not in rain[1] and 0x16 in rain[1], rain[1]


def test_a_dry_race_records_as_main(tmp_path_factory, romset_zip, saturn_cue):
    """A one-lap DRY race on the weather set (Metropolis, autoplay's DRY) and the same race on the set without the switch: the same
    writes into the best-time spans, in the same order (pc, address, data, mask), and both reach the name entry."""
    a = _end(_run(tmp_path_factory, romset_zip, saturn_cue, "dry_wet"))
    b = _end(_run(tmp_path_factory, romset_zip, saturn_cue, "dry_main"))
    print("DRY END", len(a[2]), len(b[2]), a[0], b[0])
    assert a[0] == b[0] and a[2] and a[2] == b[2]
    assert 0x1E in a[1] and a[1] == b[1], ([hex(m) for m in a[1]], [hex(m) for m in b[1]])


# --- the screen drawn ----------------------------------------------------------------------------------------------------------
def _dump(wd, frame, entry):
    return tuple((wd / f"{frame}_{entry}_{k}.bin").read_bytes() for k in ("tile", "char", "pal", "work"))


def _cell(tile, layer, row, col):
    from vrtools.arcade.dirscreen import tile_address
    return struct.unpack_from("<H", tile, tile_address(layer, row, col) - 0x700000)[0]


def _expected_layer0(out, entry, font, shown):
    """{(row, col): word} of COURSE WEATHER's layer 0 from the built set: the four game maps at their cells, the caption map, the
    title (the countdown font, `font` = (base, attribute) as select_dump reads it), the labels (DRY / RAIN, the one shown yellow),
    and the badge's map over the RAIN picture (a converted course; an original's composed map words)."""
    from vrtools.arcade import dirgfx
    from vrtools.arcade.dirscreen import DOUBLE_ARROW, LABEL_WHITE, LABEL_YELLOW, RED_ARROW, STEP_PANEL, WHEEL_PANEL
    from vrtools.arcade.panel import decode_panel
    from vrtools.arcade.weather import screen
    from tests.test_dirscreen_build import _map_words
    want = {}
    for m, (r, c) in ((DOUBLE_ARROW, screen.DOUBLE_ARROW_CELL), (WHEEL_PANEL, (screen.PANEL_ROW, 7)), (RED_ARROW, (screen.PANEL_ROW + 2, 28)),
                      (STEP_PANEL, (screen.PANEL_ROW, 35))):
        p = decode_panel(out, m)
        want.update({(r + i, c + j): (p.base + p.tiles[i * p.cols + j]) & 0xFFFF for i in range(p.rows) for j in range(p.cols)})
    cm, _ = dirgfx._tiles(screen.caption_bitmap(), empty_shared=True)
    r, c = screen.CAPTION_CELL
    want.update({(r + i, c + j): w for (i, j), w in _map_words(dirgfx.map_blob(cm, screen.CAPTION_BLOCK)).items()})
    base, attr = font
    r, c = screen.TITLE_CELL
    for k, ch in enumerate(screen.TITLE):
        t = ((ord(ch) - 0x20) * 6 + base) | attr
        want.update({(r + i, c + 2 * k + j): t + 2 * i + j for i in range(3) for j in range(2)})
    for k, word in enumerate(("DRY", "RAIN")):
        a = LABEL_YELLOW if k == shown else LABEL_WHITE
        for n, ch in enumerate(word):
            g = out.program[0x2F2456 - 0x200000 + 6 * (ord(ch) & 0x3F):][:6]
            want.update({(screen.LABEL_ROW + i, screen.LABEL_COLS[k] + 2 * n + j): a | g[2 * i + j] for i in range(3) for j in range(2)})
    r, c = screen.PIC_ROW + screen.BADGE_CELL[0], screen.PIC_COLS[1] + screen.BADGE_CELL[1]
    if entry >= 3:
        bm, _, _ = screen.badge_tiles()
        want.update({(r + i, c + j): w for (i, j), w in _map_words(dirgfx.map_blob(bm, screen.BADGE_BLOCKS[0])).items() if w != dirgfx.BLANK_TILE})
    return want


@pytest.mark.parametrize("label,frame,shown", [("conv", 1356, 0), ("conv", 1372, 1), ("orig", 1356, 0), ("orig", 1372, 1)])
def test_the_weather_screen_is_drawn(tmp_path_factory, romset_zip, saturn_cue, label, frame, shown):
    """At a dumped frame of COURSE WEATHER (DRY, then RAIN shown): layer 0 holds the game's four maps one row lower than COURSE
    DIRECTION's, the SELECT WEATHER caption over the wheel panel's lettering, the title COURSE WEATHER on rows 0-2, the labels (the
    one shown yellow) and the badge's cells; the caption's characters are in block 0x3580 with the wheel panel's palette; on the
    converted course layer 2 holds the picture twice in slot 0's and slot 2's words, the badge's characters are in block 0x3480,
    and nothing else of layer 0 is drawn but the countdown and the game's mark (the course select's pieces are gone)."""
    from vrtools.arcade import dirgfx
    from vrtools.arcade.select import SLOT_CHAR
    from vrtools.arcade.weather import screen
    from tests.test_dirscreen_build import BLANK, GAME_MARK, _countdown
    from tests.test_tencourse import _records
    from tests.test_tgp_build import _seven
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, label)
    out, _ = _seven(romset_zip, saturn_cue)
    entry = _specs()[label][0]
    assert _at(_lines(wd), frame).shown == shown
    tile, char, pal, work = _dump(wd, frame, entry)
    shift, attr = struct.unpack("<2I", work)
    want = _expected_layer0(out, entry, ((shift << 7) & 0xFFFF, attr), shown)
    wrong = [(rc, hex(_cell(tile, 0, *rc)), hex(w)) for rc, w in want.items() if _cell(tile, 0, *rc) != w]
    assert not wrong, wrong[:8]
    _, cchars = dirgfx._tiles(screen.caption_bitmap(), empty_shared=True)
    at = 32 * screen.CAPTION_BLOCK
    assert char[at:at + 32 * len(cchars)] == b"".join(cchars)
    assert pal[32 * (screen.CAPTION_BLOCK >> 7):][:32] == pal[32 * dirgfx.PANEL_PALETTE:][:32]
    if entry < 3:
        return
    _, bchars, _ = screen.badge_tiles()
    at = 32 * screen.BADGE_BLOCKS[0]
    assert char[at:at + 32 * len(bchars)] == b"".join(bchars)
    _, recs, read = _records(out)
    rec = recs[entry]
    m = struct.unpack("<336H", read(rec.map_addr, 672))
    for slot, c in zip((0, 2), screen.PIC_COLS):
        got = [_cell(tile, 2, screen.PIC_ROW + i, c + j) for i in range(21) for j in range(16)]
        assert got == [(0x8000 | SLOT_CHAR[slot]) + v for v in m], slot
    count = _countdown(False)
    stray = [(r, c) for r in range(48) for c in range(62) if (r, c) not in want and (r, c) not in count and (r, c) not in GAME_MARK
             and _cell(tile, 0, r, c) != BLANK]
    assert not stray, [(rc, hex(_cell(tile, 0, *rc))) for rc in stray[:8]]


def test_the_course_select_is_intact_on_a_second_game(tmp_path_factory, romset_zip, saturn_cue):
    """After the conv run's RAIN game (whose weather screen put its caption and badge into the middle slot's blocks) and the attract,
    the second game's course select, 300 frames in: each of the three slots' character blocks holds its entry's picture record's
    characters and its palettes the record's normal set (the screens' pieces are gone), and the palettes the screens' text uses are
    those of the first game's select. (After an original's screens: tests/test_originals_reverse.py's
    test_the_course_select_is_the_same_after_an_originals_direction_screen_and_race, on the weather set.)"""
    from vrtools.arcade.select import SLOT_CHAR, SLOT_PAL, visible_entries
    from tests.test_dirscreen_build import TEXT_PALETTES
    from tests.test_tencourse import _records
    from tests.test_tgp_build import _seven
    wd = _run(tmp_path_factory, romset_zip, saturn_cue, "conv")
    out, _ = _seven(romset_zip, saturn_cue)
    _, recs, read = _records(out)
    lines = _lines(wd)
    starts = [b.frame for a, b in zip([None] + lines, lines) if b.mode == 0x10 and (a is None or a.mode != 0x10)]
    assert len(starts) >= 2, starts
    text = []
    for start in (starts[0], starts[-1]):
        files = sorted(wd.glob(f"{start + 300}_*_char.bin"))
        assert len(files) == 1, (start, files)
        index = int(files[0].name.split("_")[1])
        char = files[0].read_bytes()
        pal = files[0].with_name(files[0].name.replace("_char", "_pal")).read_bytes()
        text.append([pal[32 * p:32 * p + 32] for p in TEXT_PALETTES])
        for slot, e in enumerate(visible_entries(index)):
            rec = recs[e]
            n = [rec.counts & 0xFF, rec.counts >> 8 & 0xFF, rec.counts >> 16 & 0xFF]
            chars = read(rec.chars_addr, 32 * sum(n))
            for p in range(3):
                at = 32 * (SLOT_CHAR[slot] + 128 * p)
                assert char[at:at + 32 * n[p]] == chars[32 * sum(n[:p]):32 * sum(n[:p + 1])], (start, index, slot, p)
            assert pal[SLOT_PAL[slot] - 0x900000:][:96] == read(rec.normal_addr, 96), (start, index, slot)
        print("SELECT", start, "index", index, visible_entries(index))
    assert text[0] == text[1]
