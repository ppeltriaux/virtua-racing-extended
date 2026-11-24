"""Weather stage 1, the identity gates (spec section 6): the switch off builds the set as before the weather feature, member for
member; the switch on changes only the blocks weather/layout.py names; and a DRY race, pressed or left to the countdown, is main's
race pass for pass from the load on, on all ten courses and three reverse races, its pictures the same at fixed race frames.

"Main" here is the session's own set built with `weather=False` (test_weather_off_is_mains_set_member_for_member ties it to main's
set at this branch's base, a build of main kept outside the repository: the reference set VR_PRE_WEATHER_SET; that test skips
without it, fails with VR_REQUIRE_REFERENCE_SETS=1). The race runs have no autopilot: from the race start the wheel is centred and the gas floored (autoplay.lua), so the
inputs are the same race-relative ones on every run whatever frame the race loads on."""
import os
from pathlib import Path

import pytest

from vrtools.arcade.course import DIRECTION_RAM
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.mame.runner import LUA_DIR, parse_dir_log, run_mame
from tests.test_tgp_build import _build, _built, _seven

from tests.reference_sets import reference_set   # noqa: E402  (W2: VR_PRE_WEATHER_SET, skip / fail as every reference set)
REGIONS = ("program", "boot", "data", "polygons", "copro_data", "tgp_program", "sound_program", "sound_pcm1", "sound_pcm2")
_DRY: dict = {}


def _seven_dry(romset_zip, saturn_cue):
    """The session's set with the switch off (the same conversions as `_seven`), made once."""
    from vrtools.arcade.tencourse import ten_course_set
    from tests.session_cache import cached                     # a failed build cached, not rebuilt (Task 7)

    def make():
        out, conv = _built(romset_zip, saturn_cue)
        return ten_course_set(out, conv, weather=False), conv
    return cached(_DRY, str(romset_zip), make)


def test_weather_off_returns_the_set_itself(romset_zip, saturn_cue):
    """install_weather with the switch off returns the set it was given, untouched (no copy, no write)."""
    from vrtools.arcade.weather import install_weather
    dry, conv = _seven_dry(romset_zip, saturn_cue)
    assert install_weather(dry, conv, weather=False) is dry


def test_weather_off_is_mains_set_member_for_member(romset_zip, saturn_cue):
    """The switch off gives main's set at this branch's base (a CLI build of main, VR_PRE_WEATHER_SET), every region byte for
    byte; and the switch on does not (stage 2: the polygon ROM too, the rain's objects; stage 6: the sound board's three members,
    which main's build copied from the user's set unchanged)."""
    zp = reference_set("VR_PRE_WEATHER_SET") / "vr.zip"
    main = RomSet.from_zip(zp, verify=False)
    dry, _ = _seven_dry(romset_zip, saturn_cue)
    wet, _ = _seven(romset_zip, saturn_cue)
    assert [r for r in REGIONS if getattr(dry, r) != getattr(main, r)] == []
    assert [r for r in REGIONS if getattr(wet, r) != getattr(main, r)] == ["program", "boot", "data", "polygons", "sound_program",
                                                                           "sound_pcm1", "sound_pcm2"]


def _differing(a: bytes, b: bytes, base: int) -> list[int]:
    import numpy as np
    x, y = np.frombuffer(a, np.uint8), np.frombuffer(b, np.uint8)
    return [base + int(i) for i in np.nonzero(x != y)[0]]


def test_the_switch_changes_only_the_named_blocks(romset_zip, saturn_cue):
    """Every byte the switch changes lies in a block of weather.layout.blocks() (the erased blocks, the sites), and every block of
    ROM is written (the table names nothing the build does not use). Only the program ROM, the boot ROM, data banks 0 and 3 and
    the polygon ROM change (stage 2: the storm's image and data in bank 3, the rain's objects in the polygon ROM), and the sound
    board's three members (stage 6)."""
    from vrtools.arcade.weather import layout
    dry, _ = _seven_dry(romset_zip, saturn_cue)
    wet, _ = _seven(romset_zip, saturn_cue)
    spans = {"program": [], "boot": [], "bank0": [], "bank3": [], "polygon": [], "sound": [], "pcm1": [], "pcm2": []}
    for b in layout.blocks():
        rom = layout.ROM_OF[b.space]
        if rom in spans:
            spans[rom].append(b)
    diff = {"program": _differing(dry.program, wet.program, V60_PROGRAM), "boot": _differing(dry.boot, wet.boot, V60_BOOT),
            "bank0": _differing(dry.data[:0x100000], wet.data[:0x100000], 0x100000),
            "bank3": _differing(dry.data[0x300000:], wet.data[0x300000:], 0x100000), "polygon": _differing(dry.polygons, wet.polygons, 0),
            "sound": _differing(dry.sound_program, wet.sound_program, 0), "pcm1": _differing(dry.sound_pcm1, wet.sound_pcm1, 0),
            "pcm2": _differing(dry.sound_pcm2, wet.sound_pcm2, 0)}
    assert dry.data[0x100000:0x300000] == wet.data[0x100000:0x300000] and all(getattr(dry, r) == getattr(wet, r) for r in ("copro_data", "tgp_program"))
    for rom, addrs in diff.items():
        outside = [a for a in addrs if not any(b.start <= a < b.start + b.size for b in spans[rom])]
        assert not outside, (rom, [hex(a) for a in outside[:8]])
        unused = [b.name for b in spans[rom] if not any(b.start <= a < b.start + b.size for a in addrs)]
        assert not unused, (rom, unused)


def test_the_layout_check_on_the_built_sets(romset_zip, saturn_cue):
    """layout.check passes on the set before the install (every erased block erased) and refuses the installed set."""
    from vrtools.arcade.weather import layout
    dry, _ = _seven_dry(romset_zip, saturn_cue)
    wet, _ = _seven(romset_zip, saturn_cue)
    layout.check(dry)
    with pytest.raises(PatchError, match="not erased"):
        layout.check(wet)


def test_the_layout_check_refuses_a_block_in_the_annex(romset_zip, saturn_cue, monkeypatch):
    """The reverse variants' annex as the built set holds it (layout.annex_span: from the first load record to the end of the last
    race blob) lies outside every block of the table, and a block placed inside it is refused by layout.check, by name, as an overlap
    with the annex (not only as ROM that is not erased)."""
    from vrtools.arcade.weather import layout
    dry, _ = _seven_dry(romset_zip, saturn_cue)
    lo, hi = layout.annex_span(dry)
    assert 0x200000 <= lo < hi <= 0x300000, (hex(lo), hex(hi))
    assert not [b.name for b in layout.blocks() if b.space == "program" and b.start < hi and lo < b.start + b.size]
    layout.check(dry)
    inside = layout.Block("test", "program", (lo + hi) // 2 // 16 * 16, 16, "test")
    monkeypatch.setattr(layout, "TABLE", layout.TABLE + (inside,))
    with pytest.raises(PatchError, match="'test'.*annex"):
        layout.check(dry)


def test_the_install_checks_every_site_before_writing(romset_zip, saturn_cue):
    """Each in-place site of the install (weather.screen.sites) holding other bytes than expected makes install_weather raise
    PatchError naming it, and the set given is left as it was."""
    from dataclasses import replace
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.weather import install_weather, screen
    dry, conv = _seven_dry(romset_zip, saturn_cue)
    before = {r: getattr(dry, r) for r in REGIONS}
    site_list = screen.sites(dry, directory_layout())[0]
    assert len(site_list) == 7
    for s in site_list:
        region, base = ("program", V60_PROGRAM) if s.space == "program" else ("boot", V60_BOOT)
        data = bytearray(getattr(dry, region))
        data[s.addr - base] ^= 0xFF
        bad = replace(dry, **{region: bytes(data)})
        with pytest.raises(PatchError):
            install_weather(bad, conv)
        assert getattr(bad, region) == bytes(data)
    assert all(getattr(dry, r) == v for r, v in before.items())


# --- DRY is main's race, pass for pass --------------------------------------------------------------------------------------
CASES = [(e, False) for e in range(10)] + [(0, True), (6, True), (9, True)]
RACE_SECONDS = 70                       # main's race loads on 1600 (26.7 s): about 1 250 logic passes of race
TIMEOUT_EXTRA = 12                      # the weather screen's countdown and the hold: about 640 frames more before the load
MIN_PASSES = 1000
RACE_SNAPS = (600, 1200)                # frames after the race start, pictured on every run
_RUNS: dict = {}


def _timeout_steps(entry, reverse):
    """dirscreen_drive.lua's steps (VR_DIR_ANSWER=0) answering the direction screen as autoplay.lua does on a set with the
    weather screen (the course pressed at 1200, REVERSE steered from 1260, the press at 1300) and then nothing: the gas lifted, the
    wheel at 128 (the weather screen's DRY side) until the countdown locks DRY."""
    steps = [(1200, 255, WHEEL_FOR_ENTRY[entry]), (1210, 0, 128)] + ([(1260, 0, 200)] if reverse else [])
    return steps + [(1300, 255, 200 if reverse else 128), (1310, 0, 128)]


def _race_run(tmp_path_factory, romset_zip, saturn_cue, entry, reverse, how):
    """The work directory of a race on `entry`: how = "main" (the switch off, autoplay's answer), "pressed" (the switch on, DRY by
    autoplay's answer: the weather lock where main's direction lock was) or "timeout" (the switch on, the weather screen left to its
    countdown), made once."""
    key = (entry, reverse, how)
    if key not in _RUNS:
        out, _ = (_seven_dry if how == "main" else _seven)(romset_zip, saturn_cue)
        bkey = "build_dry" if how == "main" else "build_wet"
        if bkey not in _RUNS:
            _RUNS[bkey] = _build(tmp_path_factory.mktemp(bkey), romset_zip, out)
        wd = tmp_path_factory.mktemp(f"race{entry}{'r' if reverse else ''}_{how}")
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_SNAPS": "", "VR_SNAPS_AFTER_START": ",".join(map(str, RACE_SNAPS)),
               "VR_PASS_LOG": str(wd / "pass.txt"), "VR_PASS_FIELDS": "1", "VR_DIR_LOG": str(wd / "dir.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}",
               "VR_SOUND_LOG": str(wd / "sound.txt"), "VR_PCM_LOG": str(wd / "pcm.txt"), "VR_EXTRA_LUA": str(LUA_DIR / "pcm_log.lua")}
        if reverse:
            env["VR_DIRECTION"] = "1"
        seconds = RACE_SECONDS
        if how == "timeout":
            steps = _timeout_steps(entry, reverse)
            env.update({"VR_DIR_ANSWER": "0", "VR_EXTRA_LUA": f"{LUA_DIR / 'dirscreen_drive.lua'};{LUA_DIR / 'pcm_log.lua'}",
                        "VR_DIR_DRIVE": ",".join(f"{f}:{g}:{w}" for f, g, w in steps)})
            env.pop("VR_DIRECTION", None)
            seconds += TIMEOUT_EXTRA
        run_mame(LUA_DIR / "autoplay.lua", seconds, wd, _RUNS[bkey], env=env, timeout=1800)
        _RUNS[key] = wd
    return _RUNS[key]


def _from_load(wd):
    """(the race load's frame, the game's state at every pass from it: the W lines without the pass and frame numbers, the race's
    weather byte and flag at the load)."""
    lines = parse_dir_log(wd / "dir.txt")
    load = next(l for l in lines if l.mode == 0x11)
    passes = []
    for row in open(wd / "pass.txt"):
        p = row.split()
        if p and p[0] == "W" and int(p[2]) >= load.frame:
            assert len(p) == 4 + 16 * 12, ("the pass log lacks the cars' fields (VR_PASS_FIELDS)", len(p))   # the final review's W7
            passes.append(" ".join(p[3:]))
    return load, passes


@pytest.mark.parametrize("entry,reverse", CASES, ids=[f"entry{e}{'_reverse' if r else ''}" for e, r in CASES])
def test_dry_is_mains_race_pass_for_pass(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """Main's race (the switch off) against DRY pressed (the race loads on main's frame) and DRY by the weather screen's countdown
    (the race loads later): from the load on, the game's state at the end of every logic pass (pass_state.lua: the clock, the
    sixteen cars' x, z, road point, speed and lap) is the same on all three, over MIN_PASSES passes or more; the weather byte is 0
    and the flag the direction at the load; the pictures at RACE_SNAPS frames after the race start are the same. Strict: no
    tolerance."""
    import numpy as np
    from PIL import Image
    runs = {how: _race_run(tmp_path_factory, romset_zip, saturn_cue, entry, reverse, how) for how in ("main", "pressed", "timeout")}
    got = {how: _from_load(wd) for how, wd in runs.items()}
    (lm, pm), (lp, pp), (lt, pt) = got["main"], got["pressed"], got["timeout"]
    print("DRY", entry, reverse, "loads", lm.frame, lp.frame, lt.frame, "passes", len(pm), len(pp), len(pt))
    assert lp.frame == lm.frame and lt.frame > lm.frame + 500, (lm.frame, lp.frame, lt.frame)
    assert lm.flag == lp.flag == lt.flag == int(reverse), (lm, lp, lt)
    assert lp.armed == lt.armed == 0, (lp, lt)              # the weather byte DRY (on main the byte is the direction screen's arming flag)
    n = min(len(pm), len(pp), len(pt))
    assert n >= MIN_PASSES, n
    for how, ps in (("pressed", pp), ("timeout", pt)):
        first = next((i for i in range(n) if ps[i] != pm[i]), None)
        assert first is None, (how, first, pm[first][:100], ps[first][:100])
    snaps = {how: sorted((wd / "snap").rglob("*.png"))[:len(RACE_SNAPS)] for how, wd in runs.items()}
    assert all(len(s) == len(RACE_SNAPS) for s in snaps.values()), snaps
    for k in range(len(RACE_SNAPS)):
        ref = np.asarray(Image.open(snaps["main"][k]))
        for how in ("pressed", "timeout"):
            assert (np.asarray(Image.open(snaps[how][k])) == ref).all(), (how, RACE_SNAPS[k])


SOUND_CASES = [(0, False), (6, False), (9, True)]


@pytest.mark.parametrize("entry,reverse", SOUND_CASES, ids=[f"entry{e}{'_reverse' if r else ''}" for e, r in SOUND_CASES])
def test_dry_sends_mains_sound_words(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """Weather stage 6: a DRY race (pressed, the race loading on main's frame) sends the sound board exactly main's words from the
    race load on, at the same frames (sound_log.lua's latch); no storm word (B074-B078) in it."""
    from vrtools.mame.runner import parse_sound_log
    main, pressed = (_race_run(tmp_path_factory, romset_zip, saturn_cue, entry, reverse, how) for how in ("main", "pressed"))
    lm, lp = _from_load(main)[0], _from_load(pressed)[0]
    assert lm.frame == lp.frame
    sm, sp = parse_sound_log(main / "sound.txt"), parse_sound_log(pressed / "sound.txt")
    cm, cp = [c for c in sm.commands if c[0] >= lm.frame], [c for c in sp.commands if c[0] >= lp.frame]
    print("DRY sound", entry, reverse, "words from the load", len(cm), len(cp))
    assert sm.complete and sp.complete and len(cm) > 100 and cm == cp, (len(cm), len(cp), next(((a, b) for a, b in zip(cm, cp) if a != b), None))
    assert not [c for c in cp if 0xB074 <= c[1] <= 0xB078]


# Weather stage 6, F4 (fix round 2, the session lead's ruling replacing ruling A): a DRY game's sound board on the weather set does
# what v0.3's does, write for write, except that a word arriving within 3.8 us of a tick boundary may be read one tick (17.96 ms)
# apart (the main loop's timer poll at 0x1164 is a 38-cycle loop; none in the three test races). The level hook (patch 3a) costs every register write a few cycles; before fix round 2 its cost on
# the 168 writes of the power-on initialisation, before the YM3438's timer A starts, put every tick 828.8 us behind v0.3's, so
# commands near a tick boundary were read a tick apart and the dynamic effect voices were allocated differently (effects cut short or
# run longer by up to ~1.9 s). Patch 4 (sound.clear_routine) gives those cycles back before the timer starts, and the reset 8100's
# timer reload stays in place: the ticks are v0.3's. Within a tick the hook still delays each write by microseconds (reported).
TICK_S = 0.017957                       # the sound program's tick as measured in MAME 0.289
SPARE = {(2, 0x14), (2, 0x19), (1, 0x15)}                    # the storm's voices: unused by the game


ONE_TICK_EVENTS_MAX = 2                 # a race's words read one tick apart at most (R3-3, the session lead's ruling)


def _quiet_end(main, wet) -> float:
    """The cut: the last moment before 0.1 s ahead of the shorter run's last frame at which neither board writes within 2 ms (a cut
    inside a tick's burst would take a write of one run and not its twin: the weather set's writes land up to ~0.8 ms later)."""
    import bisect
    ts = [sorted(x.time for x in log.writes) for log in (main, wet)]
    end = min(main.frames[-1][1], wet.frames[-1][1]) - 0.1
    quiet = lambda c: all(bisect.bisect_left(t, c + 0.002) == bisect.bisect_left(t, c - 0.002) for t in ts)
    return next(end - k / 1000 for k in range(5000) if quiet(end - k / 1000))


def _by_tick(writes, t_from: float) -> dict:
    """{tick index: the writes of that tick, in order} for the writes from `t_from` (the board writes a burst a tick; a gap over 3 ms
    starts the next burst, whose index is the previous one's plus the gap in ticks, rounded)."""
    out, idx, start, prev = {}, 0, None, None
    for w in writes:
        if w.time < t_from:
            continue
        if prev is not None and w.time - prev > 0.003:
            idx += max(1, round((w.time - start) / TICK_S))
            start = w.time
        if start is None:
            start = w.time
        out.setdefault(idx, []).append(w)
        prev = w.time
    return out


def one_tick_events(wm: list, ww: list, t_from: float) -> tuple[list, list]:
    """The ONE shape the exact comparison recognises besides equality (R3-3): a word of the game read one tick apart on the weather
    set's board. `wm`, `ww`: v0.3's and the weather set's writes (the spare voices apart), equal before `t_from`. The ticks where the
    two differ form clusters of at most two consecutive ticks; in each, every (chip, voice, register) that differs is shifted by
    exactly one tick, all in the same direction (its writes in the cluster's ticks on the weather set are v0.3's of the tick before,
    the word read later, or of the tick after, read earlier; values and order identical, and its writes just past the cluster agree),
    the registers that do not differ are v0.3's, and within each tick the shifted registers' writes and the others' each keep v0.3's
    order. Returns (problems, events: (the cluster's first tick's time, its direction, the shifted registers))."""
    key = lambda w: (w.chip, w.voice, w.reg, w.value)
    tm, tw = _by_tick(wm, t_from), _by_tick(ww, t_from)
    reg = lambda w: (w.chip, w.voice, w.reg)
    diff = sorted(i for i in set(tm) | set(tw) if [key(w) for w in tm.get(i, [])] != [key(w) for w in tw.get(i, [])])
    clusters = []
    for i in diff:
        if clusters and i == clusters[-1][-1] + 1:
            clusters[-1].append(i)
        else:
            clusters.append([i])
    problems, events = [], []
    for c in clusters:
        if len(c) > 2:
            problems.append(("ticks differ, more than two in a row", len(c), round(tm.get(c[0], tw.get(c[0]))[0].time, 3)))
            continue
        per = lambda t, i, r: [key(w) for w in t.get(i, []) if reg(w) == r]
        regs = {reg(w) for i in c for w in tm.get(i, []) + tw.get(i, [])}
        shifted = {r for r in regs if any(per(tm, i, r) != per(tw, i, r) for i in c)}
        found = None
        for d in (1, -1):                                   # 1: the word read a tick later on the weather set; -1: earlier
            ok = all(per(tw, i, r) == per(tm, i - d, r) for r in shifted for i in c)
            if d == 1:                                      # v0.3's writes of the cluster's last tick are the weather set's next tick's
                ok = ok and all(per(tm, c[-1], r) == per(tw, c[-1] + 1, r) for r in shifted)
            else:                                           # the weather set's tick before the cluster holds v0.3's first tick's
                ok = ok and all(per(tm, c[0], r) == per(tw, c[0] - 1, r) for r in shifted)
            for i in c:                                     # the order within each tick: shifted ones as v0.3's moved tick, others in place
                ok = ok and [key(w) for w in tw.get(i, []) if reg(w) in shifted] == \
                    [key(w) for w in tm.get(i - d, []) if reg(w) in shifted]
                ok = ok and [key(w) for w in tw.get(i, []) if reg(w) not in shifted] == \
                    [key(w) for w in tm.get(i, []) if reg(w) not in shifted]
            if ok and shifted:
                found = d
                break
        first = (tm.get(c[0]) or tw.get(c[0]))[0].time
        if found is None:
            problems.append(("ticks differ, not a word read a tick apart", round(first, 3), sorted(shifted)[:6]))
        else:
            events.append((round(first, 3), "later" if found == 1 else "earlier", sorted(shifted)))
    if len(events) > ONE_TICK_EVENTS_MAX:
        problems.append(("words read a tick apart, more than allowed", len(events), ONE_TICK_EVENTS_MAX))
    return problems, events


def exact_board_differences(main, wet) -> tuple[list, dict]:
    """The board on the switch-off set (`main`) and on the weather set (`wet`), parse_pcm_log logs of the same inputs, from the boot to
    a quiet moment just before the shorter run's end (`_quiet_end`): (problems, figures). Exact by default: every chip write (chip,
    voice, register, value), the storm's spare voices apart, in the same order; where they differ, only `one_tick_events`' shape is
    recognised (a game word read one tick apart, at most ONE_TICK_EVENTS_MAX a race); a spare voice written other than the key-offs
    the weather set's reset 8100 adds (three a reset the board heard) is a problem too. Figures: the writes compared; the time deltas
    (the weather set's write less v0.3's) of the writes in place from 1 s after the boot, on the ticks where the two agree (a recognised
    event's ticks left out: the join): min (the tick boundaries' offset: the
    earliest write of some tick pays no hook) and max; the one-tick events; the spare voices' extra key-offs; the resets."""
    import collections
    end = _quiet_end(main, wet)
    wm = [x for x in main.writes if (x.chip, x.voice) not in SPARE and x.time < end]
    ww = [x for x in wet.writes if (x.chip, x.voice) not in SPARE and x.time < end]
    key = lambda x: (x.chip, x.voice, x.reg, x.value)
    problems, fig = [], {"writes": (len(wm), len(ww)), "events": []}
    first = next((i for i in range(min(len(wm), len(ww))) if key(wm[i]) != key(ww[i])), None)
    if first is not None or len(wm) != len(ww):
        t_from = 1.0
        if first is not None and wm[first].time < t_from:
            problems.append(("a write differs before the ticks start", first, wm[first], ww[first]))
        else:
            p, fig["events"] = one_tick_events(wm, ww, t_from)
            problems += p
    tm, tw = _by_tick(wm, 1.0), _by_tick(ww, 1.0)      # the deltas on the ticks where the two agree (the join's first fix: paired by
    same = [(x, y) for i in set(tm) & set(tw)          # position, a recognised one-tick event paired writes a tick apart, ~18 ms)
            if [key(w) for w in tm[i]] == [key(w) for w in tw[i]] for x, y in zip(tm[i], tw[i])]
    d = [y.time - x.time for x, y in same]
    fig["delta_us"] = (round(min(d) * 1e6, 1), round(max(d) * 1e6, 1)) if d else None
    sp = lambda log: collections.Counter(key(x) for x in log.writes if (x.chip, x.voice) in SPARE)
    extra = sp(wet) - sp(main)
    fig["spare_keyoffs"] = sum(extra.values())
    fig["resets"] = sum(1 for _, _, w in wet.words if w == 0x8100)
    if any(k[2] != 4 or k[3] != 0 for k in extra) or sp(main) - sp(wet) or fig["spare_keyoffs"] % 3 or \
            fig["spare_keyoffs"] > 3 * fig["resets"]:
        problems.append(("spare voices", dict(extra), fig["resets"]))
    return problems, fig


def _shift_word(log, at: float, change: bool = False):
    """A copy of `log` with what a game word read one tick later looks like, planted at the first tick i after `at` where some
    registers take new values that tick i + 1 holds: their writes in tick i get tick i - 1's values (the same count). `change`: one
    moved value altered as well (not that shape). Returns (the copy, tick i's time, the moved registers)."""
    reg = lambda w: (w.chip, w.voice, w.reg)
    t = _by_tick([w for w in log.writes if (w.chip, w.voice) not in SPARE], at)
    vals = lambda i, r: [w.value for w in t.get(i, []) if reg(w) == r]
    for i in sorted(t)[1:-1]:
        moved = {r for r in {reg(w) for w in t[i]} if vals(i, r) != vals(i - 1, r) and len(vals(i - 1, r)) == len(vals(i, r))
                 and vals(i + 1, r) == vals(i, r)}
        if not moved:
            continue
        old = {r: vals(i - 1, r) for r in moved}
        repl, changed = {}, False
        for w in t[i]:
            if reg(w) in moved:
                v = old[reg(w)].pop(0)
                if change and not changed:
                    v, changed = v ^ 0x40, True
                repl[id(w)] = w._replace(value=v)
        return log._replace(writes=[repl.get(id(w), w) for w in log.writes]), round(t[i][0].time, 3), sorted(moved)
    raise AssertionError("no tick to plant a shifted word in")


def _synthetic_logs(event: str | None, offset_us: float = 3.0):
    """Two pcm logs without MAME (the join's first fix): v0.3's board writing a burst a tick (TICK_S) from 0.5 s to 30 s (a level held
    on chip 1 voice 1, a pitch on voice 2 changing every seventh tick, the level written once more in one tick, 20 s in: a game word),
    and the weather set's, the same writes `offset_us` later; `event` "later" / "earlier": that extra write a tick later / earlier on
    the weather set's (a word read one tick apart, the poll race's one recognised shape)."""
    from vrtools.mame.runner import PcmLog, PcmWrite
    n_word = round(19.5 / TICK_S)

    def burst(i, t, extra):
        ws = [PcmWrite(0, t, 1, 1, 5, 0x20), PcmWrite(0, t + 0.0002, 1, 2, 2, (i // 7) & 0xFF)]
        if extra:
            ws.append(PcmWrite(0, t + 0.0004, 1, 1, 5, 0x20))
        return ws
    ticks = range(round(29.5 / TICK_S))
    main, wet = [], []
    shift = {"later": 1, "earlier": -1, None: 0}[event]
    for i in ticks:
        t = 0.5 + i * TICK_S
        main += burst(i, t, i == n_word)
        wet += [w._replace(time=w.time + offset_us * 1e-6) for w in burst(i, t, i == n_word + shift)]
    frames = [(k, k / 60) for k in range(1, 30 * 60)]
    mk = lambda ws: PcmLog(writes=ws, words=[], modes=[], frames=frames, boots=[0.0], complete=True)
    return mk(main), mk(wet)


def test_the_offset_figure_outside_a_recognised_event():
    """The join's first fix (Task 6's last review): exact_board_differences' time deltas are taken on the writes of the ticks where the
    two boards agree, not paired by position across a recognised one-tick event (which paired a write with its twin a tick away:
    a figure of about 18 ms that tripped the test's 10 us bound on the tick boundaries' offset). A word read a tick later or earlier
    is one event, no problem, and the figures are the offset's (3 us) as without it."""
    for event in (None, "later", "earlier"):
        problems, fig = exact_board_differences(*_synthetic_logs(event))
        assert problems == [] and len(fig["events"]) == (event is not None), (event, problems, fig["events"])
        assert fig["delta_us"] == (3.0, 3.0), (event, fig["delta_us"])
        assert abs(fig["delta_us"][0]) < 10 and fig["delta_us"][1] < TICK_S * 1e6 / 2


def test_the_one_tick_recogniser_on_planted_shifts(tmp_path_factory, romset_zip, saturn_cue):
    """one_tick_events without new MAME runs (R3-3), on v0.3's DRY Big Forest log: one planted word read a tick later (a burst of held
    values moved one tick) is recognised as one event; the same shift with one moved value changed is not (a problem); three such
    shifts fail (more than ONE_TICK_EVENTS_MAX); the log against itself has none."""
    from vrtools.mame.runner import parse_pcm_log
    lm = parse_pcm_log(_race_run(tmp_path_factory, romset_zip, saturn_cue, 0, False, "main") / "pcm.txt")
    assert exact_board_differences(lm, lm) == ([], exact_board_differences(lm, lm)[1]) and exact_board_differences(lm, lm)[1]["events"] == []
    one, t1, regs = _shift_word(lm, 20.0)
    p, fig = exact_board_differences(lm, one)
    assert p == [] and len(fig["events"]) == 1 and fig["events"][0][1] == "later", (p, fig["events"], t1, regs)
    bad = _shift_word(lm, 20.0, change=True)[0]
    assert exact_board_differences(lm, bad)[0] != []
    three, t2, _ = _shift_word(_shift_word(one, 30.0)[0], 40.0)
    p, fig = exact_board_differences(lm, three)
    assert len(fig["events"]) == 3 and any("more than allowed" in x[0] for x in p), (p, fig["events"])


def test_the_exact_comparison_sees_a_planted_fault(tmp_path_factory, romset_zip, saturn_cue):
    """exact_board_differences on a DRY run's logs against themselves (no problem), then with one write changed in a copy: a level, a
    sample, a pitch, the voice of a fixed voice's write, the voice of a dynamic effect voice's key-on (another of the five), a key-off
    dropped, two writes swapped, a spare voice keyed on: each is a problem (the RED of fix round 2's gate besides the board before it,
    `out/p80s/r2`)."""
    from vrtools.mame.runner import parse_pcm_log
    lm = parse_pcm_log(_race_run(tmp_path_factory, romset_zip, saturn_cue, 0, False, "main") / "pcm.txt")
    assert exact_board_differences(lm, lm)[0] == []
    w = lm.writes
    at = lambda f: next(i for i, x in enumerate(w) if x.time > 30 and f(x))
    lvl, smp, pit = at(lambda x: x.reg == 5 and x.voice == 0x1A), at(lambda x: x.reg == 1 and x.voice < 0x10), at(lambda x: x.reg == 2)
    dyn = at(lambda x: x.chip == 1 and 0x10 <= x.voice < 0x15 and x.reg == 4 and x.value & 0x80)
    off = at(lambda x: x.reg == 4 and not x.value & 0x80 and (x.chip, x.voice) not in SPARE)
    faults = {"level": w[:lvl] + [w[lvl]._replace(value=w[lvl].value ^ 0x10)] + w[lvl + 1:],
              "sample": w[:smp] + [w[smp]._replace(value=w[smp].value ^ 1)] + w[smp + 1:],
              "pitch": w[:pit] + [w[pit]._replace(value=w[pit].value ^ 4)] + w[pit + 1:],
              "a fixed voice's write on another voice": w[:lvl] + [w[lvl]._replace(voice=0x08)] + w[lvl + 1:],
              "a dynamic effect on another of the five": w[:dyn] + [w[dyn]._replace(voice=0x10 + (w[dyn].voice - 0x0F) % 5)] + w[dyn + 1:],
              "a key-off dropped": w[:off] + w[off + 1:],
              "two writes swapped": w[:lvl] + [w[lvl + 1], w[lvl]] + w[lvl + 2:],
              "a spare voice keyed on": w[:lvl] + [w[lvl]._replace(chip=2, voice=0x19, reg=4, value=0x80)] + w[lvl:]}
    for name, writes in faults.items():
        assert exact_board_differences(lm, lm._replace(writes=writes))[0] != [], name


@pytest.mark.parametrize("entry,reverse", SOUND_CASES, ids=[f"entry{e}{'_reverse' if r else ''}" for e, r in SOUND_CASES])
def test_dry_plays_mains_sounds(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """F4 (fix rounds 2 and 3, the session lead's rulings): a DRY race on the weather set (pressed) against main's (the switch-off
    set), the same inputs, from the boot to a quiet moment before the run's end: every write to both MultiPCM chips identical in voice,
    register, value and order (fixed and dynamic voices: key-ons, key-offs, levels, pitches, samples), the only extra writes the
    storm's spare voices' key-offs at a reset (`exact_board_differences`); the one shape recognised besides, a game word read one tick
    apart (its writes identical, shifted by exactly one tick: `one_tick_events`), at most ONE_TICK_EVENTS_MAX a race, counted and
    printed (none in the three races measured). The tick boundaries' offset (the least delta of a write in place) within 10 us: the
    alarm for INIT_SURPLUS_CYCLES if the initialisation's writes or the hook's cost change (the board before fix round 2: +358 us
    on Big Forest, +781 us on Metropolis, out/p80s/r3/check.py). Within a tick each write lands later by the level hook's cost on
    the writes before it (up to ~0.8 ms, measured); no write crosses a tick. It failed on the board before fix round 2 (f86d475; out/p80s/r2/red.py):
    Big Forest's first difference 2.21 s after the load (an effect keyed a tick earlier, on dynamic voice 0x14 where v0.3 used 0x10),
    Metropolis's 6.24 s after it (the engine voice 0x1a's pitch a tick early)."""
    from vrtools.mame.runner import parse_pcm_log
    main, wet = (_race_run(tmp_path_factory, romset_zip, saturn_cue, entry, reverse, how) for how in ("main", "pressed"))
    problems, fig = exact_board_differences(*(parse_pcm_log(w / "pcm.txt") for w in (main, wet)))
    print("DRY board", entry, reverse, fig)
    assert problems == [], problems
    # the tick boundaries' offset within 10 us: the direct alarm for INIT_SURPLUS_CYCLES (the board before fix round 2: +358 / +781 us)
    assert fig["writes"][0] > 50000 and abs(fig["delta_us"][0]) < 10 and fig["delta_us"][1] < TICK_S * 1e6 / 2, fig


# --- the attract is main's: state, pictures, sound (the final review's W3) -------------------------------------------------------
ATTRACT_SECONDS = 200                   # long enough for the attract's demo races (the test reports which it showed)
ATTRACT_SNAP_FROM, ATTRACT_SNAP_TO, ATTRACT_SNAP_EVERY = 1500, 11400, 450    # pictures at fixed frames: 23
_ATTRACT: dict = {}


def _attract_run(tmp_path_factory, romset_zip, saturn_cue, which):
    """The attract with no game, ATTRACT_SECONDS, on the normal set ("on": the weather installed) or the `weather=False` set ("off"):
    the pass state with the full fields, the sound board's writes, the mode / menu log, pictures at fixed frames; made once."""
    from tests.test_tgp_build import _build
    from vrtools.mame.runner import LUA_DIR, run_mame
    if which not in _ATTRACT:
        out = (_seven if which == "on" else _seven_dry)(romset_zip, saturn_cue)[0]
        base = tmp_path_factory.mktemp(f"attract_{which}")
        setdir = _build(base, romset_zip, out)
        wd = base / "run"
        wd.mkdir()
        env = {"VR_SNAP_FROM": str(ATTRACT_SNAP_FROM), "VR_SNAP_TO": str(ATTRACT_SNAP_TO), "VR_SNAP_EVERY": str(ATTRACT_SNAP_EVERY),
               "VR_PASS_LOG": str(wd / "pass.txt"), "VR_PASS_FIELDS": "1", "VR_PCM_LOG": str(wd / "pcm.txt"),
               "VR_EXTRA_LUA": str(LUA_DIR / "pcm_log.lua"), "VR_ATTRACT_LOG": str(wd / "attract.txt")}
        run_mame(LUA_DIR / "attract_snaps.lua", ATTRACT_SECONDS, wd, setdir, env=env, timeout=3600)
        _ATTRACT[which] = wd
    return _ATTRACT[which]


def demo_races(wd) -> list:
    """The demo races the attract showed: (frame, menu entry) at each start of its demo race mode (0x03: the attract cycles 0x02 the
    course load, 0x03 the demo race, about 34 s, then 0x06-0x08 its scenes) in attract.txt."""
    rows = [r.split() for r in open(wd / "attract.txt") if r.startswith("A ")]
    out, prev = [], None
    for _, f, mode, menu in rows:
        if mode == "03" and prev != "03":
            out.append((int(f), int(menu)))
        prev = mode
    return out


def attract_differences(off, on, races: int) -> tuple[list, dict]:
    """(problems, figures) of two attract runs (`off` the weather=False set's work directory, `on` the normal set's): the pass logs
    line for line (the first difference), the pictures pixel for pixel, the sound board's writes with exact_board_differences (the
    recognised one-tick shape allowed, ONE_TICK_EVENTS_MAX a demo race)."""
    import numpy as np
    from PIL import Image
    from vrtools.mame.framerate import parse_pass_log
    from vrtools.mame.runner import parse_pcm_log
    problems = []
    a, b = parse_pass_log(off / "pass.txt"), parse_pass_log(on / "pass.txt")
    if not a or len(a[0].split()) != 4 + 16 * 12:
        problems.append(("the pass log lacks the cars' fields (VR_PASS_FIELDS)", len(a)))
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    if first is not None or len(a) != len(b):
        problems.append(("the game's state differs", first, len(a), len(b), (a[first][:80], b[first][:80]) if first is not None else None))
    pa, pb = sorted((off / "snap").rglob("*.png")), sorted((on / "snap").rglob("*.png"))
    if len(pa) != len(pb):
        problems.append(("pictures", len(pa), len(pb)))
    for x, y in zip(pa, pb):
        if not np.array_equal(np.asarray(Image.open(x).convert("RGB")), np.asarray(Image.open(y).convert("RGB"))):
            problems.append(("a picture differs", x.name))
            break
    bp, fig = exact_board_differences(parse_pcm_log(off / "pcm.txt"), parse_pcm_log(on / "pcm.txt"))
    problems += [p for p in bp if p[0] != "words read a tick apart, more than allowed"]
    if len(fig["events"]) > ONE_TICK_EVENTS_MAX * max(1, races):
        problems.append(("words read a tick apart, more than allowed", len(fig["events"]), ONE_TICK_EVENTS_MAX * max(1, races)))
    fig.update({"passes": (len(a), len(b)), "pictures": len(pa)})
    return problems, fig


def test_with_no_game_the_attract_is_mains(tmp_path_factory, romset_zip, saturn_cue):
    """Requirement 1's attract half (the final review's W3): with no game, ATTRACT_SECONDS of the attract on the normal set and on the
    `weather=False` set (v0.3's game) are the same game: the state at every pass end with the full fields (the demo races run the
    handling's opponents' site every pass) identical pass for pass, the pictures at fixed frames pixel for pixel, the sound board's
    writes exact (exact_board_differences: only the recognised one-tick shape, ONE_TICK_EVENTS_MAX a demo race, counted). The
    comparison can fail: a pass field, a pixel and a board write planted into a copy of the normal set's logs are each reported."""
    import shutil
    from concurrent.futures import ThreadPoolExecutor
    from PIL import Image
    for which in ("on", "off"):                         # the builds first, in this thread (they are cached; mktemp is not thread-safe)
        (_seven if which == "on" else _seven_dry)(romset_zip, saturn_cue)
    with ThreadPoolExecutor(2) as ex:
        on, off = ex.map(lambda w: _attract_run(tmp_path_factory, romset_zip, saturn_cue, w), ("on", "off"))
    races = demo_races(on)
    assert races == demo_races(off) and races, (races, demo_races(off))
    problems, fig = attract_differences(off, on, len(races))
    print(f"attract: demo races (frame, entry) {races}; passes {fig['passes']}, pictures {fig['pictures']}, board writes "
          f"{fig['writes']}, one-tick events {len(fig['events'])}")
    assert problems == [], problems[:3]
    # the planted differences (on copies of the normal set's logs)
    bad = tmp_path_factory.mktemp("attract_planted")
    for name, plant in (("pass", "pass.txt"), ("pixel", "snap"), ("board", "pcm.txt")):
        d = bad / name
        shutil.copytree(on, d)
        if name == "pass":
            rows = (d / "pass.txt").read_text().splitlines()
            k = next(i for i, r in enumerate(rows) if r.startswith("W ") and i > len(rows) // 2)
            t = rows[k].split()
            t[-1] = format(int(t[-1], 16) ^ 1, "x")      # the last car's last field, one bit
            rows[k] = " ".join(t)
            (d / "pass.txt").write_text("\n".join(rows) + "\n")
        elif name == "pixel":
            f = sorted((d / "snap").rglob("*.png"))[len(races)]
            im = Image.open(f).convert("RGB")
            px = im.getpixel((200, 100))
            im.putpixel((200, 100), (px[0] ^ 8, px[1], px[2]))
            im.save(f)
        else:
            rows = (d / "pcm.txt").read_text().splitlines()
            k = next(i for i, r in enumerate(rows) if r.startswith("P ") and i > len(rows) // 2)
            t = rows[k].split()
            t[-1] = format(int(t[-1], 16) ^ 1, "x")      # one write's value, one bit
            rows[k] = " ".join(t)
            (d / "pcm.txt").write_text("\n".join(rows) + "\n")
        assert attract_differences(off, d, len(races))[0] != [], name
