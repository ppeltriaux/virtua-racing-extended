"""Weather stage 5, the wet handling (spec 5.7 with 5.4, 3 and 6; weather/handling.py on the carrier of weather/carrier.py): its tune
is the design's table; its eight hook sites in the game's own physics code jump or call stubs whose dry path is the site's own
instructions (byte for byte) and whose wet path enters RAM routines that test the race mode first and keep the registers the game
relies on; in MAME, scripted inputs on Big Forest and Metropolis show each rule as the owner approved it after driving the prototype
(spike 54/59: "hangling is good now!"): the spin after a held full lock on full gas and none at half gas, the brake lock on a held
brake and none on taps, the take-off, none of it under cover, in the countdown, a put-back glide, a pit stop or after the goal, a
race ending mid-lock or mid-spin leaving the next game clean, the opponents 3 % slower; a DRY race's handling fields main's.

The MAME runs of this module are made together (`handling_runs`), at most two MAME processes at a time, at the first test that needs
one; a selection of tests makes only the runs those tests read."""
import os
import struct

import pytest

from vrtools.arcade.romset import V60_BOOT
from vrtools.arcade.weather import carrier
from vrtools.arcade.weather.tune import HandlingTune


# ---- static: the tune ------------------------------------------------------------------------------------------------------------
def test_the_tune_is_the_designs_table():
    """HandlingTune's defaults are S5.7's table: the slide from 420 (dry 546), building only with the gas above 128 of 255, the spin
    at a slide of 0x900 above 100 km/h with a 77-logic-frame cool-down, the grip base -16, the take-off traction x0.6 rising to x1 at
    60 km/h in gears 1-3, the lock at 80 % brake (pedal 204) for 8 logic frames at 100 km/h, released below 40 % (102) or at 20
    km/h, the brake clamp -1583, the squeal from 280, the opponents x0.97. Values out of range are refused."""
    t = HandlingTune()
    assert (t.slide_threshold, t.slide_gas, t.spin_slide, t.spin_kmh, t.spin_cooldown) == (420, 128, 0x900, 100, 77)
    assert (t.grip_change, t.wheelspin_m0, t.wheelspin_fade_kmh, t.wheelspin_gears) == (-16, 0.6, 60, 3)
    assert (t.lock_brake_pct, t.lock_frames, t.lock_kmh, t.release_brake_pct, t.release_kmh) == (80, 8, 100, 40, 20)
    assert (t.lock_brake, t.release_brake) == (204, 102)
    assert (t.brake_clamp, t.squeal_from, t.opponents) == (-1583.0, 280, 0.97)
    for bad in ({"slide_gas": 255}, {"spin_cooldown": 0}, {"wheelspin_m0": 0.05}, {"release_brake_pct": 80}, {"brake_clamp": -2000.0},
                {"brake_clamp": 0.0}, {"opponents": 1.2}, {"wheelspin_gears": 8}, {"lock_frames": 256}):
        with pytest.raises(ValueError, match="HandlingTune"):
            HandlingTune(**bad)
    assert HandlingTune(opponents=1.0).opponents == 1.0


# ---- static: the sites, the stubs, the wet routines ----------------------------------------------------------------------------
def _sets(romset_zip, saturn_cue):
    """(the stage-1 set the carrier starts from, the weather set built from it with the registry's modules, the build's report)."""
    from tests.test_weather_carrier import _stage1
    s1 = _stage1(romset_zip, saturn_cue)
    out, rep = carrier.build(s1, carrier.default_modules(s1))
    return s1, out, rep


def _text(lines):
    return [" ".join(l.text.split()) for l in lines]


def test_the_handling_is_registered_after_the_rain():
    """The registry's frame order (the join's: cover, lightning, rain, handling, sound): the handling after the rain, and before the
    sound when the sound is in. The handling's frame routine reads nothing of another module's."""
    names = [f.__name__ for f in carrier.REGISTRY]
    assert names.index("_handling_factory") > names.index("_rain_factory"), names
    if "_sound_factory" in names:
        assert names.index("_handling_factory") < names.index("_sound_factory"), names


def test_the_layout_names_the_handling_blocks():
    """Every site is a "boot site" block of the layout table owned by `handling`, its size the original instructions'; the stubs are
    an erased "boot" block of its own."""
    from vrtools.arcade.weather import handling, layout
    blocks = {b.name: b for b in layout.blocks()}
    for s in handling.SITES:
        b = blocks[f"handling site {s.name}"]
        assert (b.space, b.start, b.size, b.owner) == ("boot site", s.addr, len(s.original), "handling"), s.name
    sb = blocks["handling stubs"]
    assert (sb.space, sb.owner) == ("boot", "handling") and sb.start == handling.STUB_AT


def test_the_sites_and_their_stubs(romset_zip, saturn_cue):
    """Each site holds its original instructions in the stage-1 set (the prototype's, read in main's listing); built, it jumps to its
    stub, the rest of its bytes `nop` (never run: the stub jumps back past them); the stub tests the weather byte, then SWITCH, and
    jumps to the site's wet routine in the storm image."""
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.weather import WEATHER_BYTE, handling
    s1, out, rep = _sets(romset_zip, saturn_cue)
    lay = rep["layout"]
    labels = handling.stub_labels()
    for s in handling.SITES:
        o = s.addr - V60_BOOT
        assert s1.boot[o:o + len(s.original)] == s.original, s.name
        call = _text(listing(out, s.addr, 1))[0]
        assert call == f"jmp {labels[s.name]:X}", (s.name, call)
        jl = 6
        assert out.boot[o + jl:o + len(s.original)] == b"\xcd" * (len(s.original) - jl), s.name
        head = _text(listing(out, labels[s.name], 5))
        dry = f"{labels[s.name + '_dry']:X}"
        assert head == [f"cmp.b #1, {WEATHER_BYTE:X}", f"bne {dry}", f"cmp.b #0, {carrier.SWITCH:X}", f"be {dry}",
                        f"jmp {lay.label('handling', s.name):X}"], (s.name, head)


def test_each_dry_path_is_the_sites_original_instructions(romset_zip, saturn_cue):
    """From each stub's dry label: the site's original bytes, unchanged (the grip's PC-relative read of the grip base, `mov.w
    5011A8[PC], R20`, as the same read in the absolute form: its operand resolves to 0x5011a8 at the site), then the jump back to the
    instruction after the site."""
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.v60asm import asm
    from vrtools.arcade.weather import handling
    s1, out, rep = _sets(romset_zip, saturn_cue)
    labels = handling.stub_labels()
    for s in handling.SITES:
        at = labels[s.name + "_dry"] - V60_BOOT
        n = len(s.original)
        if s.name == "grip":
            disp = struct.unpack_from("<i", s.original, 3)[0]
            assert s.original[:3] == bytes.fromhex("2d34f2") and (s.addr + disp) & 0xFFFFFFFF == handling.GRIP_BASE
            want = asm("mov.w abs,reg", handling.GRIP_BASE, "r20")
        else:
            want = s.original
        assert len(want) == n and out.boot[at:at + n] == want, (s.name, out.boot[at:at + n].hex(), want.hex())
        back = _text(listing(out, labels[s.name + "_dry"] + n, 1))[0]
        assert back == f"jmp {s.addr + n:X}", (s.name, back)
    grip = _text(listing(s1, 0xFEB43D, 1))[0]
    assert grip == "mov.w 5011A8[PC], R20", grip


def _routines(s1):
    """({routine: its listing lines}, every line, the code's address, its bytes): the handling's code as the carrier lays it out in the
    storm image for the registry's modules on the stage-1 set `s1` (what `carrier.build` writes)."""
    from vrtools.arcade.disasm import listing_bytes
    from vrtools.arcade.weather import handling
    lay, pieces, _ = carrier.lay_out(carrier.default_modules(s1))
    at, code = pieces["handling"]
    lines = listing_bytes(code, at)
    starts = sorted((lay.label("handling", n), n) for n in (*handling.NAMES, "frame"))
    out = {}
    for k, (a, n) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else at + len(code)
        out[n] = [l for l in lines if a <= l.addr < end]
    return out, lines, at, code


def test_the_handling_code_disassembles(romset_zip, saturn_cue):
    """The handling's code as laid out in the image disassembles as instructions throughout (unidasm reads no byte as data), its
    eight entries and its frame routine at instruction starts."""
    from vrtools.arcade.weather import handling
    s1, out, rep = _sets(romset_zip, saturn_cue)
    routines, lines, at, code = _routines(s1)
    assert sum(len(l.bytes) for l in lines) == len(code)
    assert not [l for l in lines if l.text.startswith("$") or "illegal" in l.text.lower()][:3]
    assert set(routines) == {*handling.NAMES, "frame"} and all(routines.values())


def test_every_wet_routine_tests_the_race_mode_first(romset_zip, saturn_cue):
    """Each wet routine begins `cmp.b #14, 501138` (the race mode), then `be` past a `jmp` to its stub's dry label: outside the race
    (the countdown, the goal and results, and the states where SWITCH stays 1 outside a rain mode: mode 0x1d after the results, the
    test menu entered from a RAIN race) the game's own instructions run. The frame routine tests the time guard first."""
    from vrtools.arcade.weather import handling
    s1, out, rep = _sets(romset_zip, saturn_cue)
    routines, _, _, _ = _routines(s1)
    labels = handling.stub_labels()
    for n in handling.NAMES:
        t = _text(routines[n][:3])
        assert t[0] == "cmp.b #14, 501138" and t[1].startswith("be ") and t[2] == f"jmp {labels[n + '_dry']:X}", (n, t)
        assert int(t[1].split()[1], 16) == routines[n][3].addr, (n, t)
    f = _text(routines["frame"][:2])
    assert f[0] == f"cmp.b #0, {carrier.VBL:X}" and f[1].startswith("bne "), f


def test_every_player_rule_runs_the_whole_gate(romset_zip, saturn_cue):
    """Each player rule's routine (slide, brake, wheelspin, engine note, grip, squeal) holds the whole gate, in order: the player's race
    handler, no put-back glide, pit state 0, not under the tunnel flag (R25 the player in the physics code, R19 in the sound code)."""
    s1, _, _ = _sets(romset_zip, saturn_cue)
    routines, _, _, _ = _routines(s1)
    for name in ("slide", "brake", "wspin", "engine", "grip", "squeal"):
        r = "R19" if name in ("engine", "squeal") else "R25"
        want = [f"cmp.w #FE8E18, A[{r}]", "cmp.w #0, 501160", f"cmp.h #0, 191[{r}]", f"test1 #7, 152[{r}]"]
        text = _text(routines[name])
        at = [next((k for k, t in enumerate(text) if t == w), None) for w in want]
        assert None not in at and at == sorted(at), (name, list(zip(want, at)))
        assert all(text[k + 1].split()[0] in ("bne", "bgt") for k in at), (name, [text[k + 1] for k in at])


# What each wet routine may change (spec rule of the shared context: a site's stub and routine leave every register and flag the
# site's original code relies on as the original instructions would, unless changing a value is the hook's purpose): its outputs
# (the hook's purpose) and the registers dead at every exit (written before read on every path of the game's code from each exit,
# read in main's listing: weather/handling.py's SITES docstring). Every other register it writes must be saved (pushm / push) and
# restored.
OUTPUTS = {"slide": set(), "brake": {"R11"}, "wspin": {"R12"}, "steer": set(), "engine": {"R0"}, "grip": {"R20"}, "squeal": {"R0"},
           "opp": {"R0", "R19"}}                 # the opponents': R19 by the site's own second instruction, run in the routine
DEAD = {"slide": {"R0"}, "brake": {"R0"}, "wspin": {"R0"}, "steer": set(), "engine": set(), "grip": set(), "squeal": set(),
        "opp": set()}
NO_WRITE = ("cmp", "test", "jmp", "jsr", "b", "rsr", "push", "pop", "nop")


def _written(text: str) -> set:
    """The registers an instruction of the listing writes (the destination of a two-operand instruction, the register of `pop`;
    compares, tests, jumps and pushes write none; `negf.s Ra, Rb` writes Rb)."""
    import re
    mnem, _, ops = text.partition(" ")
    if mnem.startswith(NO_WRITE) and not mnem.startswith(("pop", "pushm")) or mnem in ("pushm", "popm"):
        return set()
    if mnem == "pop":
        return {ops.strip()}
    dst = ops.split(",")[-1].strip()
    return {dst} if re.fullmatch(r"R\d+", dst) else set()


def test_the_wet_routines_keep_the_registers(romset_zip, saturn_cue):
    """Every register a wet routine writes is its site's output, dead at its exits, or saved by the routine (pushed after the mode
    test and popped back as many times as the routine has exits to the game's code)."""
    import re
    from vrtools.arcade.weather import handling
    s1, out, rep = _sets(romset_zip, saturn_cue)
    routines, _, _, _ = _routines(s1)
    for n in handling.NAMES:
        t = _text(routines[n])
        written = set().union(*(_written(x) for x in t)) - {"R31"}
        saved = set()
        for x in t:
            m = re.fullmatch(r"(pushm|push) (.+)", x)
            if m and m.group(1) == "push":
                saved.add(m.group(2))
            elif m:
                v = int(m.group(2).lstrip("#"), 16)
                saved |= {f"R{k}" for k in range(32) if v >> k & 1}
        extra = written - OUTPUTS[n] - DEAD[n] - saved
        assert not extra, (n, sorted(extra))
        pops = [x for x in t if x.startswith(("pop ", "popm "))]
        pushes = [x for x in t if x.startswith(("push ", "pushm "))]
        exits = [x for x in t if x.startswith(("jmp ", "rsr"))]
        if pushes:
            assert len(pops) == len(pushes) * (len(exits) - 1), (n, pushes, pops, exits)   # every exit but the mode test's pops


# ---- the runs -----------------------------------------------------------------------------------------------------------------
import threading                                          # noqa: E402
from concurrent.futures import ThreadPoolExecutor        # noqa: E402
from pathlib import Path                                  # noqa: E402

from vrtools.arcade.select import WHEEL_FOR_ENTRY        # noqa: E402
from vrtools.mame.runner import LUA_DIR, PIT_HANDLER, parse_handling_log, run_mame, write_centreline   # noqa: E402

FPS = 1e6 / 17385                       # MAME's model1 video frames a second (two vblanks are 34 770 us); a logic frame is two
BIG_FOREST, METROPOLIS = 0, 6
JOBS = 2                                # the track's MAME processes at once
ST = "at0,wheel,128,0,560;at0,gas,147,0,560"       # the prototype's scripted start: wheel straight, gas under the slip, then the
                                                   # autopilot (spike 54's v3.sh / m58.sh)
HELD = "kmh280,brake,255,0,90;kmh280,gas,0,0,90;kmh280,wheel,128,0,90"     # at 280 km/h on Big Forest's back straight (spike 55)
EVERYTHING = "brake,255,0,{n};{t},wheel,255,0,{n};{t},gas,255,0,{n}"        # the brake, full lock and full gas at once
PUTBACK_QUAD = 80                       # Big Forest: a quad of an open stretch the autopilot crosses at speed (putback.lua's staging)
CHAIN_DRY_RAIN = f"{WHEEL_FOR_ENTRY[0]}:0;{WHEEL_FOR_ENTRY[0]}:0:1"         # after the first race: DRY Big Forest, then RAIN
NEXT_RAIN = f"{WHEEL_FOR_ENTRY[0]}:0:1"
SPIN_WINDOW_S = (1.4, 1.8)              # S5.7: "about 1.4-1.8 s of full lock at speed" (the prototype: 1.48 s after the wheel)
TAKEOFF_S = (1.9, 2.1)                  # S5.7: 0-100 km/h 1.96 s held (the dry 1.69)
STALE = "{t},slip,1,0,{n};{t},note,6000,0,{n}"   # a stale slip mark and engine note forced (the prototype could keep them there)
GRIP_SCRIPT = "kmh280,wheel,176,0,40;kmh280,gas,255,0,40"
GENTLE = "at0,gas,140,0,99999;at0,wheel,128,0,99999"   # the gas port 140 (the game's pedal 157: under the wheelspin's 179), straight
# DRY fields: scripted inputs only (the autopilot steers from samples grouped by MAME's frame end, which the hooks' few microseconds a
# pass can move: stage 2's finding), from the race start: full gas (autoplay), full lock on the start straight, a held brake with the
# wheel turned, brake taps, full lock the other way
SCRIPT = ("at700,wheel,255,0,90;at900,brake,255,0,90;at900,gas,0,0,90;at900,wheel,200,0,120;at1200,brake,255,0,96,12,4;"
          "at1400,wheel,0,0,120")


def everything(trigger: str, frames: int) -> str:
    return f"{trigger}," + EVERYTHING.format(n=frames, t=trigger)


# name -> (set, entry, seconds, rain, actions, extras): extras "auto" (the autopilot; default on), "pit" (Big Forest's pit path),
# "putback" (putback.lua at PUTBACK_QUAD), "end" (race_end.lua with VR_END_NEXT = the value), "pass" (pass_state.lua), "stubs" (the hooks' calls); the F lines are
# per logic pass (at its end), their frame the video frame count then
RUNS = {
    "spin_full": ("wet", BIG_FOREST, 110, True, "rp240,wheel,255,0,150", {}),
    "spin_half": ("wet", BIG_FOREST, 110, True, "rp240,wheel,255,0,150;rp240,gas,124,0,150", {}),   # the port 124: in-game 127
    "lock_turn": ("wet", BIG_FOREST, 90, True, "rp82,brake,255,0,80;rp82,gas,0,0,80;rp82,wheel,200,0,140", {}),
    "hold": ("wet", BIG_FOREST, 60, True, f"{ST};{HELD}", {}),
    "lift": ("wet", BIG_FOREST, 60, True, f"{ST};kmh280,gas,0,0,90;kmh280,wheel,128,0,90", {}),
    "taps": ("wet", BIG_FOREST, 60, True, f"{ST};kmh280,brake,255,0,96,12,4;kmh280,gas,0,0,96;kmh280,wheel,128,0,96", {}),
    "takeoff": ("wet", BIG_FOREST, 45, True, "at0,wheel,128,0,1400", {"auto": False}),
    "takeoff_plain": ("plain", BIG_FOREST, 45, True, "at0,wheel,128,0,1400", {"auto": False}),
    "cover_lock": ("wet", METROPOLIS, 100, True, f"{ST};rp276,wheel,255,0,100", {}),
    "cover_brake": ("wet", METROPOLIS, 100, True, f"{ST};rp262,brake,255,0,60;rp262,gas,0,0,60", {}),
    "open_brake": ("wet", METROPOLIS, 100, True, f"{ST};rp316,brake,255,0,60;rp316,gas,0,0,60", {}),
    "states": ("wet", BIG_FOREST, 90, True, everything("at0", 400) + ";" + everything("glide", 60) + ";" + STALE.format(t="glide", n=60),
               {"putback": PUTBACK_QUAD}),
    "pit": ("wet", BIG_FOREST, 200, True, everything("pit", 500) + ";" + STALE.format(t="pit", n=500), {"pit": True}),
    "goal": ("wet", BIG_FOREST, 170, True, everything("mode19", 300), {"end": ""}),
    "end_locked": ("wet", BIG_FOREST, 420, True, f"{ST};{HELD};kmh280,clock,0,30,20;kmh150@2,brake,255,0,60;kmh150@2,gas,0,0,60;"
                   "kmh280@3,brake,255,0,90;kmh280@3,gas,0,0,90;kmh280@3,wheel,128,0,90", {"end": CHAIN_DRY_RAIN}),
    "end_spinning": ("wet", BIG_FOREST, 300, True, "rp240,wheel,255,0,150;fired1,clock,0,4,20;rp240@2,wheel,255,0,150",
                     {"end": NEXT_RAIN}),
    "opp_rain": ("wet", BIG_FOREST, 200, True, "at0,gas,0,0,99999;at0,wheel,128,0,99999", {"auto": False}),
    "opp_dry": ("wet", BIG_FOREST, 200, False, "at0,gas,0,0,99999;at0,wheel,128,0,99999", {"auto": False}),
    "fields_set": ("wet", BIG_FOREST, 70, False, SCRIPT, {"auto": False}),
    "fields_main": ("dry", BIG_FOREST, 70, False, SCRIPT, {"auto": False}),
    "cost_dry_set": ("wet", BIG_FOREST, 70, False, "", {"auto": False, "pass": True, "stubs": True}),
    "cost_dry_plain": ("plain", BIG_FOREST, 70, False, "", {"auto": False, "pass": True}),
    "cost_dry_main": ("dry", BIG_FOREST, 70, False, "", {"auto": False, "pass": True}),
    "cost_rain_probe": ("probe", BIG_FOREST, 70, True, GENTLE, {"auto": False, "pass": True, "stubs": True}),
    "cost_rain_plain": ("plain", BIG_FOREST, 70, True, GENTLE, {"auto": False, "pass": True}),
    "attract_set": ("wet", BIG_FOREST, 200, False, "", {"attract": True}),
    "attract_plain": ("plain", BIG_FOREST, 200, False, "", {"attract": True}),
    # under cover on any road (handling_log.lua's VR_HANDLING_COVER), RAIN against DRY on the probe set (the opponents' factor 1.0: the
    # same opponents), the same scripted inputs: every player rule at work outside cover, none under it
    "cover_twin_rain": ("probe", BIG_FOREST, 70, True, SCRIPT, {"auto": False, "cover": "0:99999"}),
    "cover_twin_dry": ("probe", BIG_FOREST, 70, False, SCRIPT, {"auto": False, "cover": "0:99999"}),
    # the grip base: the same RAIN race (the autopilot) under cover to 280 km/h, then open on one, still covered on the other; there
    # 38 % lock and full gas for 40 frames (spike 58's grip measure: wheel 176)
    "grip_open": ("probe", BIG_FOREST, 70, True, GRIP_SCRIPT, {"cover": "0:k280"}),
    "grip_cover": ("probe", BIG_FOREST, 70, True, GRIP_SCRIPT, {"cover": "0:99999"}),
    # the player out of the opponents' factor: GENTLE (no rule fires) on the weather set, RAIN against DRY
    "player_rain": ("wet", BIG_FOREST, 60, True, GENTLE, {"auto": False}),
    "player_dry": ("wet", BIG_FOREST, 60, False, GENTLE, {"auto": False}),
    # below full gas no wheelspin: the game's pedal 178 (the port 151), RAIN, the probe set (the opponents the same) against the set
    # without the handling
    "takeoff_part": ("probe", BIG_FOREST, 45, True, "at0,wheel,128,0,1400;at0,gas,151,0,1400", {"auto": False}),
    "takeoff_part_plain": ("plain", BIG_FOREST, 45, True, "at0,wheel,128,0,1400;at0,gas,151,0,1400", {"auto": False}),
}


class HRun:
    def __init__(self, wd: Path, attract: bool = False):
        from tests.test_frame_rate import Run
        self.wd = wd
        self.log = parse_handling_log(wd / "h.txt") if not attract else None
        self.f = self.log.frames if not attract else []
        self.rate = Run(wd, finish=False)

    def trigger(self, kind: str, race: int = 1) -> int:
        """The frame of the first trigger of `kind` (its name and number, as T lines write it)."""
        return next(t[0] for t in self.log.triggers if t[2] == kind and self.race_of(t[0]) == race)

    def race_of(self, frame: int) -> int:
        return next((x.race for x in self.f if x.frame >= frame), 0) or 1

    def at(self, frame: int):
        return next(x for x in self.f if x.frame >= frame)

    def window(self, a: int, b: int) -> list:
        return [x for x in self.f if a <= x.frame < b]

    def green(self, race: int = 1) -> int:
        """The race's first frame in the race mode."""
        return next(x.frame for x in self.f if x.race == race and x.mode == 0x14)


class HandlingSession:
    """The track's sets (the weather set, the switch-off set, the weather set without the handling, the probe set with the
    opponents' factor 1.0) and every run of this module, made at the first use."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        from dataclasses import replace as _replace
        from tests.test_race_build import _drive_line
        from tests.test_tgp_build import _build, _seven
        from tests.test_weather_carrier import _stage1
        from tests.test_weather_dry import _seven_dry
        from vrtools.arcade.course import course_entry_at, road_lines
        from vrtools.arcade.directory import decode_directory
        from vrtools.arcade.weather import handling, rain
        from vrtools.arcade.weather.tune import RainTune
        self.base, self.romset_zip = base, romset_zip
        self.out, self.conv = _seven(romset_zip, saturn_cue)
        s1 = _stage1(romset_zip, saturn_cue)
        def swapped(**kw):                                       # the registry's modules, the handling's built with `kw`
            return [handling.module(s1, **kw) if m.name == "handling" else m for m in carrier.default_modules(s1)]
        sets = {"wet": self.out, "dry": _seven_dry(romset_zip, saturn_cue)[0],
                "plain": carrier.build(s1, [m for m in carrier.default_modules(s1) if m.name != "handling"])[0],
                "probe": carrier.build(s1, swapped(tune=HandlingTune(opponents=1.0)))[0]}
        if os.environ.get("VR_HANDLING_WITHOUT") == "1":       # the RED evidence: the runs of the weather set on the set without
            sets["wet"] = sets["probe"] = sets["plain"]        # the handling (stage 2's), the rest unchanged
        fault = os.environ.get("VR_HANDLING_FAULT")             # the RED evidence of the excluded states: a planted fault in the
        if fault:                                               # gate (handling.FAULTS) on the weather and probe sets
            sets["wet"] = carrier.build(s1, swapped(fault=fault))[0]
            sets["probe"] = carrier.build(s1, swapped(tune=HandlingTune(opponents=1.0), fault=fault))[0]
        self.sets = {}
        for k, rs in sets.items():
            (base / k).mkdir(parents=True, exist_ok=True)
            self.sets[k] = _build(base / k, romset_zip, rs)
        self.lay = carrier.lay_out(carrier.default_modules(self.out))[0]
        self.cells = self.lay.cell("handling", "state")
        d = decode_directory(self.out)
        line0 = [(p.x, p.z) for p in road_lines(self.out, course_entry_at(self.out, d[0].bank, window_base=d[0].header_base))[0]]
        self.lines = {BIG_FOREST: line0, METROPOLIS: _drive_line(self.conv[METROPOLIS - 3])}
        labels = handling.stub_labels()
        self.stubs = ",".join(f"{s.name}={labels[s.name]:x}-{labels[s.name + '_dry'] + len(s.original):x}" for s in handling.SITES)
        self.runs, self.failed = {}, {}
        self._lock = threading.Lock()

    def _make(self, name: str) -> HRun:
        from tests.test_frame_rate import bf_pit_path
        from vrtools.arcade.course import DIRECTION_RAM
        setname, entry, seconds, rain_on, acts, extra = RUNS[name]
        wd = self.base / "runs" / name
        wd.mkdir(parents=True, exist_ok=True)
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_SNAPS": "", "VR_HOLD_CLOCK": "1",   # (not with race_end)
               "VR_HANDLING_LOG": str(wd / "h.txt"), "VR_HANDLING_ACT": acts, "VR_RACE_LOG": str(wd / "race.txt"),
               "VR_RACE_LOG_FROM": "0", "VR_FRAME_LOG": str(wd / "frames.txt")}
        if setname in ("wet", "probe"):
            env["VR_HANDLING_CELLS"] = f"{self.cells:x}"
        if rain_on:
            env["VR_RAIN"] = "1"
        if extra.get("auto", True):
            line = bf_pit_path(self.lines[entry]) if extra.get("pit") else self.lines[entry]
            env["VR_AUTOPILOT"] = str(write_centreline(wd / "line.csv", line))
            env["VR_COLLISION_LOG"] = str(wd / "c.txt")         # the autopilot's position (collision_log.lua's vr_player)
        lua = []
        if "putback" in extra:
            lua.append(str(LUA_DIR / "putback.lua"))
            env.update({"VR_PUTBACK_QUAD": str(extra["putback"]), "VR_PUTBACK_LOG": str(wd / "putback.txt")})
        if "end" in extra:                                       # race_end.lua holds the clock itself, and a time over is wanted
            env.pop("VR_HOLD_CLOCK")
            lua.append(str(LUA_DIR / "race_end.lua"))
            env.update({"VR_END_LOG": str(wd / "end.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"})
            if extra["end"]:
                env["VR_END_NEXT"] = extra["end"]
        if extra.get("pass"):
            env["VR_PASS_LOG"] = str(wd / "pass.txt")
        if extra.get("stubs"):
            env["VR_HANDLING_STUBS"] = self.stubs
        if "cover" in extra:
            env["VR_HANDLING_COVER"] = extra["cover"]
        if extra.get("attract"):                                # the attract, no input (test_frame_rate's measure)
            env = {"VR_SNAP_FROM": "999999", "VR_FRAME_LOG": str(wd / "frames.txt")}
            run_mame(LUA_DIR / "attract_snaps.lua", seconds, wd, self.sets[setname], env=env, timeout=3600)
            return HRun(wd, attract=True)
        lua.append(str(LUA_DIR / "handling_log.lua"))          # last: its inputs win
        env["VR_EXTRA_LUA"] = ";".join(lua)
        run_mame(LUA_DIR / "autoplay.lua", seconds, wd, self.sets[setname], env=env, timeout=3600)
        return HRun(wd)

    def prefetch(self, names):
        names = [n for n in dict.fromkeys(names) if n not in self.runs]

        def make(n):
            try:
                r = self._make(n)
            except Exception as e:                              # noqa: BLE001 (raised again by `run`)
                with self._lock:
                    self.failed[n] = e
                return
            with self._lock:
                self.runs[n] = r
        with ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(make, names))

    def run(self, name: str) -> HRun:
        if name in self.failed:
            raise AssertionError(f"the run {name} failed: {self.failed[name]!r}") from self.failed[name]
        if name not in self.runs:
            self.runs[name] = self._make(name)
        return self.runs[name]

    def summary(self, text: str) -> None:
        with open(self.base / "handling_summary.txt", "a") as out:
            out.write(text.rstrip() + "\n")


NEEDS = {"test_full_lock_on_full_gas_spins": ["spin_full"], "test_full_lock_on_half_gas_does_not_spin": ["spin_half"],
         "test_a_held_brake_locks_the_front_wheels": ["lock_turn", "hold", "lift"], "test_brake_taps_do_not_lock": ["taps"],
         "test_the_take_off": ["takeoff", "takeoff_plain", "takeoff_part", "takeoff_part_plain"],
         "test_none_of_it_under_cover": ["cover_lock", "cover_brake", "open_brake", "cover_twin_rain", "cover_twin_dry"],
         "test_none_of_it_in_the_countdown_or_a_glide": ["states", "opp_rain", "opp_dry"], "test_none_of_it_in_a_pit_stop": ["pit"],
         "test_the_grip_base_and_the_player_out_of_the_opponents_factor": ["grip_open", "grip_cover", "player_rain", "player_dry"],
         "test_none_of_it_after_the_goal": ["goal"], "test_a_race_ending_mid_lock_leaves_the_next_games_clean": ["end_locked"],
         "test_a_race_ending_mid_spin_leaves_the_next_game_clean": ["end_spinning"],
         "test_the_opponents_lap_about_3_percent_slower": ["opp_rain", "opp_dry"],
         "test_a_dry_races_handling_fields_are_mains": ["fields_set", "fields_main"],
         "test_the_hooks_cost": ["cost_dry_set", "cost_dry_plain", "cost_dry_main", "cost_rain_probe", "cost_rain_plain", "attract_set",
                                 "attract_plain"]}
_SESSIONS: dict = {}


@pytest.fixture
def handling_runs(request, romset_zip, saturn_cue, tmp_path_factory) -> HandlingSession:
    from tests.session_cache import cached                     # a failed session build cached, not rebuilt (Task 7)

    def make():
        s = HandlingSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("handling"))
        want = []
        for i in request.session.items:
            name = getattr(i, "originalname", None) or getattr(i, "name", "")
            want += NEEDS.get(name, [])
        s.prefetch(want)
        return s
    return cached(_SESSIONS, str(romset_zip), make)


def engine_cmd(rpm: int) -> int:
    """The game's engine sound command from an rpm (0xffa390..0xffa3f0): clamped 2000..18000, (rpm - 2000) x 127 / 16000, at least 1,
    at most 127, | 0xc000."""
    v = int((min(max(rpm, 2000), 18000) - 2000) * 127 / 16000)
    return 0xC000 | min(max(v, 1), 127)


def squeal_cmd(lat: int, threshold: int = 364, slip: bool = False) -> int:
    """The game's squeal command from L (0xffa462..0xffa4a5) with the threshold `threshold` (the dry 364; the wet 280 and, while
    the wheels slip, at least SLIP_SQUEAL over it: weather/handling.py's squeal routine)."""
    from vrtools.arcade.weather.handling import SLIP_SQUEAL
    a = abs(lat) - threshold
    if slip and a < SLIP_SQUEAL:
        a = SLIP_SQUEAL
    v = 0 if a < 0 else min((int(a / 45) >> 2) + 3, 7) & 7
    return (0xC108 + (-v if lat < 0 else v)) & 0xFFFF


def assert_dry_sounds(passes, what: str) -> None:
    """On each pass the engine and squeal commands are the game's own (the dry formulas of the pass's rpm and L) while the slip mark
    and the engine note are forced (STALE): the wet values would differ on some of them."""
    assert passes and all(x.slip == 1 and x.note == 6000 for x in passes[2:]), (what, "the stale state was not forced")
    bad = [(x.frame, hex(x.engine), hex(engine_cmd(x.rpm)), hex(x.squeal), hex(squeal_cmd(x.lat))) for x in passes
           if x.engine != engine_cmd(x.rpm) or x.squeal != squeal_cmd(x.lat)]
    assert not bad, (what, bad[:5])
    wet = [x for x in passes[2:] if engine_cmd(x.rpm + x.note) != engine_cmd(x.rpm) or squeal_cmd(x.lat, 280, True) != squeal_cmd(x.lat)]
    assert wet, (what, "no pass where the wet values would differ: the check cannot fail")


def _s(frames: int) -> float:
    return frames / FPS


# ---- MAME: the rules, by scripted inputs -----------------------------------------------------------------------------------
def test_full_lock_on_full_gas_spins(handling_runs):
    """Big Forest's long corner (road point 240), full lock held on full gas (the autopilot's): the slide builds and the game's flat
    spin-out fires SPIN_WINDOW_S after the wheel turns (the prototype: 1.48 s, at 324 km/h), above 100 km/h, on the tarmac (no
    crash), the game's spin-out animation runs; one spin, then the cool-down."""
    r = handling_runs.run("spin_full")
    t = r.trigger("rp240")
    before = r.at(t)
    fire = next(x for x in r.f if x.frame > t and x.spins > before.spins)
    dt = _s(fire.frame - t)
    handling_runs.summary(f"spin, full gas: wheel at {t} ({before.kmh} km/h, S {before.slide}), spin at {fire.frame} after {dt:.2f} s "
                          f"at {fire.kmh} km/h; S peak {max(abs(x.slide) for x in r.window(t, fire.frame))}")
    assert SPIN_WINDOW_S[0] <= dt <= SPIN_WINDOW_S[1], (dt, before, fire)
    assert fire.kmh > 100 and fire.crash == 0 and fire.cool > 0, fire
    after = r.window(fire.frame, fire.frame + 20)
    assert any(x.spinout != 0 for x in after), [x.spinout for x in after]
    assert all(x.spins == fire.spins for x in r.window(fire.frame, t + 150 + 60)), "a second spin within the action"


def test_full_lock_on_half_gas_does_not_spin(handling_runs):
    """The same corner and lock at half gas (the game's pedal value 127, at or below the gate 128; the prototype's: the pedal port
    maps (port - 56) x 255 / 136): no spin, the slide never builds (it only drains: the prototype's S stayed 0)."""
    r = handling_runs.run("spin_half")
    t = r.trigger("rp240")
    w = r.window(t, t + 150 + 30)
    assert {x.gas for x in r.window(t + 4, t + 150)} == {127}, {x.gas for x in r.window(t + 4, t + 150)}   # the game's pedal value
    handling_runs.summary(f"spin, half gas: wheel at {t} ({r.at(t).kmh} km/h), S at the wheel {r.at(t).slide}, |S| max after 1 s "
                          f"{max(abs(x.slide) for x in w[60:])}, spins {w[0].spins} -> {w[-1].spins}")
    assert w[-1].spins == w[0].spins
    assert all(abs(b.slide) <= abs(a.slide) for a, b in zip(w[4:], w[5:])), "the slide grew at half gas"


def _kmh_per_s(w) -> float:
    return (w[0].kmh - w[-1].kmh) / _s(w[-1].frame - w[0].frame)


def test_a_held_brake_locks_the_front_wheels(handling_runs):
    """A held hard brake above 100 km/h locks the front wheels after 8 logic frames: on Big Forest's approach to the road point 84
    corner, the wheel turned, the heading (yaw) does not turn while locked and the path barely (the slide draining), the game's lock
    sound timer is re-armed; the lock ends the logic frame after the brake is let go, and the car turns again. Held on the back
    straight at 280 km/h, the locked car slows as a lift does (the prototype: 49.4 km/h/s locked, 48.6 lifting; the dry brake
    102.9)."""
    r = handling_runs.run("lock_turn")
    t = r.trigger("rp82")
    first = next(x for x in r.f if x.frame >= t and x.lock)
    locked = [x for x in r.window(first.frame, t + 80) if x.lock]
    assert 14 <= first.frame - t <= 20 and first.kmh >= 100, (first.frame - t, first)
    assert len(locked) >= 25 and len({x.yaw for x in locked}) == 1, ({x.yaw for x in locked}, len(locked))
    turn = max(abs(((x.path - first.path + 0x8000) & 0xFFFF) - 0x8000) for x in locked)
    released = next(x for x in r.f if x.frame >= t + 80 and not x.lock)
    assert released.frame - (t + 80) <= 4, released
    later = r.at(released.frame + 58)
    yaw_turn = abs(((later.yaw - released.yaw + 0x8000) & 0xFFFF) - 0x8000)
    hold, lift = handling_runs.run("hold"), handling_runs.run("lift")
    th, tl = hold.trigger("kmh280"), lift.trigger("kmh280")
    assert hold.at(th - 1)[:20] == lift.at(tl - 1)[:20] and th == tl, "the two runs part before the trigger"
    hl = next(x for x in hold.f if x.frame >= th and x.lock)
    wh, wl = hold.window(hl.frame, th + 90), lift.window(hl.frame, tl + 90)
    rh, rl = _kmh_per_s(wh), _kmh_per_s(wl)
    handling_runs.summary(f"lock: locked {first.frame - t} frames after the brake at {first.kmh} km/h, {len(locked)} frames, the path "
                          f"turned {turn * 360 / 65536:.2f} deg, the yaw 0; released {released.frame - t - 80} frames after the brake's "
                          f"end, then turned {yaw_turn * 360 / 65536:.1f} deg in 1 s; at 280: locked {rh:.1f} km/h/s, lift {rl:.1f}")
    assert turn * 360 / 65536 < 1.0 and yaw_turn * 360 / 65536 > 5.0, (turn, yaw_turn)
    assert all(x.lock for x in wh) and 0.8 <= rh / rl <= 1.25, (rh, rl)
    assert any(x.lock_timer > 0 for x in locked[:4]), [x.lock_timer for x in locked[:4]]


def test_brake_taps_do_not_lock(handling_runs):
    """Taps of the brake at 280 km/h, 6 logic frames on and 2 off (the prototype's): never locked, the lock count at most 6."""
    r = handling_runs.run("taps")
    t = r.trigger("kmh280")
    w = r.window(t, t + 100)
    handling_runs.summary(f"taps: lock count max {max(x.lock_count for x in w)}, locked frames {sum(x.lock for x in w)}, "
                          f"{_kmh_per_s(w):.1f} km/h/s")
    assert not any(x.lock for x in w) and max(x.lock_count for x in w) <= 6 and max(x.lock_count for x in w) >= 5


def test_the_take_off(handling_runs):
    """Held full gas from the green, the wheel straight: 0-100 km/h in TAKEOFF_S (the prototype 1.96 s); on the same set without the
    handling 1.6-1.8 s (the dry 1.69). The design's curve: the wheels slip only in gears 1-3 at full gas below 60 km/h, the traction
    the game's own rule (0.5..1) times 0.6 + 0.4 km/h / 60; the engine note +1200 a slipping pass up to 6000, -1500 without, the
    engine sound reading rpm + the note. Below full gas (the game's pedal 178) no slip: the speed pass for pass the set's without
    the handling (on the probe set: the opponents the same)."""
    out = {}
    for name in ("takeoff", "takeoff_plain"):
        r = handling_runs.run(name)
        g = r.green()
        hit = next(x for x in r.f if x.frame >= g and x.kmh >= 100)
        out[name] = (_s(hit.frame - g), r, g)
    t_wet, r, g = out["takeoff"]
    t_dry = out["takeoff_plain"][0]
    w = r.window(g - 4, g + 400)
    slips = [(a, b) for a, b in zip(w, w[1:]) if b.slip]          # (the pass before, the slipping pass)
    m = [0.6 + 0.4 * a.kmh / 60 for a, _ in slips]                 # the design's factor at the speed the pass started from
    handling_runs.summary(f"take-off: 0-100 {t_wet:.2f} s (without the handling {t_dry:.2f} s); {len(slips)} slipping passes, the last "
                          f"from {max((a.kmh for a, _ in slips), default=None)} km/h; traction min "
                          f"{min((b.traction for _, b in slips), default=0):.3f} (at "
                          f"{min(slips, key=lambda ab: ab[1].traction)[0].kmh if slips else None} km/h), traction / m from "
                          f"{min((b.traction / k for (_, b), k in zip(slips, m)), default=0):.3f} to "
                          f"{max((b.traction / k for (_, b), k in zip(slips, m)), default=0):.3f}; the engine note {[b.note for _, b in slips][:6]}")
    assert TAKEOFF_S[0] <= t_wet <= TAKEOFF_S[1] and 1.6 <= t_dry <= 1.8, (t_wet, t_dry)
    # S5.7: x0.6 at a standstill rising to x1 at 60 km/h, gears 1-3, full gas: the traction is the game's own rule (0.5..1) times m
    assert slips and all(a.kmh < 60 and b.gear < 3 and b.gas > 179 for a, b in slips), slips[:3]
    assert all(0.5 * k - 0.01 <= b.traction <= k + 0.01 for (_, b), k in zip(slips, m)), [(a.kmh, b.traction) for a, b in slips][:5]
    # the engine note: +1200 a slipping pass to 6000, -1500 a pass without; the engine sound reads rpm + the note
    notes = [x.note for x in w]
    steps = [(p, q, x.slip) for p, q, x in zip(notes, notes[1:], w[1:])]
    assert all(q == (min(p + 1200, 6000) if sl else max(p - 1500, 0)) for p, q, sl in steps), steps[:8]
    assert max(notes) == 6000 and all(x.engine == engine_cmd(x.rpm + x.note) for x in w if x.mode == 0x14)
    # below full gas (the game's pedal 178) no wheelspin: the speed the set's without the handling, pass for pass
    a, b = handling_runs.run("takeoff_part"), handling_runs.run("takeoff_part_plain")
    ka, kb = [(x.frame, x.kmh) for x in a.f if x.mode == 0x14], [(x.frame, x.kmh) for x in b.f if x.mode == 0x14]
    assert {x.gas for x in a.f if x.mode == 0x14 and x.frame > a.green() + 4} == {178}
    assert not any(x.slip for x in a.f) and len(ka) > 200 and ka == kb[:len(ka)], (len(ka), next(((p, q) for p, q in zip(ka, kb) if p != q), None))


def test_none_of_it_under_cover(handling_runs):
    """Metropolis's long tunnel (the player's tunnel flag set): full lock on full gas in its bend builds the slide past 0x900 by the
    dry rule, and no spin; the brake held inside does not lock. After the exit (no flag) the brake held locks. And on Big Forest
    with the flag forced on the whole race (handling_log.lua's VR_HANDLING_COVER), SCRIPT's take-off, full lock, held brake and
    taps in RAIN equal, pass for pass, the same in DRY (the probe set: the opponents the same): the wheelspin's traction, the slide,
    the grip, the lock, the engine and squeal commands all the game's own."""
    r = handling_runs.run("cover_lock")
    t = r.trigger("rp276")
    w = [x for x in r.window(t, t + 100) if x.covered]
    handling_runs.summary(f"cover: lock in the tunnel at {r.at(t).kmh} km/h, |S| peak under cover {max(abs(x.slide) for x in w)}, "
                          f"spins {w[0].spins} -> {w[-1].spins}")
    assert len(w) > 30 and max(abs(x.slide) for x in w) > 0x900 and w[-1].spins == w[0].spins, (len(w), max(abs(x.slide) for x in w))
    r = handling_runs.run("cover_brake")
    t = r.trigger("rp262")
    w = r.window(t, t + 60)
    assert all(x.covered for x in w) and not any(x.lock for x in w) and w[0].kmh >= 100, (w[0].kmh, sum(x.covered for x in w))
    r = handling_runs.run("open_brake")
    t = r.trigger("rp316")
    w = r.window(t, t + 60)
    lk = [x for x in w if x.lock]
    handling_runs.summary(f"cover: brake inside {w[0].kmh} km/h no lock; outside: locked {lk[0].frame - t if lk else None} frames after")
    assert lk and not any(x.covered for x in lk), [(x.covered, x.lock) for x in w]
    # every rule's value under cover, against the DRY twin (design S6, Cover: "dry-handling values under cover")
    a, b = handling_runs.run("cover_twin_rain"), handling_runs.run("cover_twin_dry")
    fa, fb = [x[:29] + x[40:] for x in a.f], [x[:29] + x[40:] for x in b.f]   # the switch and the cells left out
    n = min(len(fa), len(fb))
    first = next((i for i in range(n) if fa[i] != fb[i]), None)
    race = [x for x in a.f if x.mode == 0x14]
    handling_runs.summary(f"cover twin: {n} passes RAIN under cover against DRY, first difference {first}; all covered "
                          f"{all(x.covered for x in race)}; the script's take-off slip, |S| {max(abs(x.slide) for x in race)}, brake "
                          f"{max(x.brake for x in race)}")
    assert n > 1000 and all(x.covered for x in race) and first is None, (first, fa[first] if first is not None else None,
                                                                         fb[first] if first is not None else None)
    assert max(abs(x.slide) for x in race) > 200 and max(x.brake for x in race) == 255 and max(x.gas for x in race) == 255   # S built


def test_none_of_it_in_the_countdown_or_a_glide(handling_runs):
    """The brake, full lock and full gas through the countdown (the storm on, SWITCH 1): nothing of the handling (its cells all 0),
    and the opponents' working performance the DRY race's (the same start, RAIN against DRY); the same through a put-back glide
    staged on Big Forest (putback.lua): no lock, no spin, the counters still, and with a stale slip mark and engine note forced
    (STALE) the engine and squeal commands the game's own (they run from the HUD every pass, also in a glide)."""
    r = handling_runs.run("states")
    cd = [x for x in r.f if x.race == 1 and x.mode in (0x12, 0x13)]
    assert len(cd) > 100 and all(x.switch for x in cd[-50:]), (len(cd), [x.switch for x in cd[-5:]])
    assert all((x.lock, x.cool, x.slip, x.lock_count, x.note, x.spins, x.locks, x.slip_frames, x.steer_skips) == (0,) * 9 for x in cd)
    t = r.trigger("glide0")
    k0 = next(k for k, x in enumerate(r.f) if x.frame >= t and x.glide > 0)
    gl = r.f[k0:next((k for k in range(k0, len(r.f)) if r.f[k].glide <= 0), len(r.f))]       # the glide's passes
    handling_runs.summary(f"countdown: {len(cd)} frames, cells 0; glide: {len(gl)} frames from {t}, counters "
                          f"{(gl[0].spins, gl[0].locks, gl[0].slip_frames)} -> {(gl[-1].spins, gl[-1].locks, gl[-1].slip_frames)}")
    assert len(gl) > 15, len(gl)
    assert not any(x.lock for x in gl)
    assert len({(x.spins, x.locks, x.locked_frames, x.slip_frames, x.steer_skips) for x in gl}) == 1
    assert_dry_sounds(gl, "glide")
    wet, dry = handling_runs.run("opp_rain"), handling_runs.run("opp_dry")     # the countdown: the opponents' factor not applied
    cw = {x.frame: x.opponents for x in wet.f if x.race == 1 and x.mode in (0x12, 0x13)}
    cd2 = {x.frame: x.opponents for x in dry.f if x.race == 1 and x.mode in (0x12, 0x13)}
    common = sorted(set(cw) & set(cd2))
    assert len(common) > 100 and [f for f in common if cw[f] != cd2[f]] == [], [f for f in common if cw[f] != cd2[f]][:5]


def test_none_of_it_in_a_pit_stop(handling_runs):
    """A pit stop on Big Forest in RAIN (the pit path), the brake, full lock and full gas held through it: while the pit handler
    runs, no lock, no spin, the counters still; with a stale slip mark and engine note forced through it (STALE), the engine and
    squeal commands the game's own."""
    r = handling_runs.run("pit")
    stops, cur = [], []
    for x in r.f:                                       # each stop: a run of race-mode frames on the pit handler (the grid start
        if x.handler == PIT_HANDLER and x.mode == 0x14:   # runs the pit handler too, for the crew, in the countdown)
            cur.append(x)
        elif cur:
            stops.append(cur)
            cur = []
    handling_runs.summary(f"pit stops: {[(s[0].frame, len(s)) for s in stops]} (first frame, frames on the pit handler); counters "
                          f"through each {[((s[0].spins, s[0].locks, s[0].slip_frames), (s[-1].spins, s[-1].locks, s[-1].slip_frames)) for s in stops]}")
    assert stops and max(len(s) for s in stops) > 150
    for s in stops:
        assert all(x.switch for x in s) and not any(x.lock for x in s)
        assert len({(x.spins, x.locks, x.locked_frames, x.slip_frames, x.steer_skips) for x in s}) == 1
    assert_dry_sounds(stops[0], "pit stop")


def test_none_of_it_after_the_goal(handling_runs):
    """A one-lap RAIN race to its goal (race_end.lua), then the brake, full lock and full gas held: from the first frame after the race
    mode, nothing of the handling (the counters still, no lock, no slip) while it still rains (SWITCH 1), and the opponents run at
    their own performance again."""
    r = handling_runs.run("goal")
    end = next(x.frame for x in r.f if x.race == 1 and x.frame > r.green() and x.mode != 0x14)
    after = [x for x in r.f if end + 2 <= x.frame < end + 600 and x.race == 1]
    handling_runs.summary(f"goal: race mode left at {end} (mode {r.at(end).mode:x}), {len(after)} frames after it")
    assert len(after) > 200 and any(x.switch for x in after)
    assert not any(x.lock or x.slip or x.note for x in after)
    assert len({(x.spins, x.locks, x.locked_frames, x.slip_frames, x.steer_skips) for x in after}) == 1
    # the opponents' factor in the race mode only: in the race an opponent's working performance (+0x48) is never its base (+0x3c:
    # x0.97 of min(base, the bend limit)); after the goal it is its base on most passes (the bend limit above the base on straights),
    # as in a DRY race
    def at_base(passes):
        pairs = [(a, b) for x in passes for a, b in zip(x.opponents, x.opp_base)]
        return sum(a == b for a, b in pairs) / len(pairs)
    in_race, past = at_base([x for x in r.f if x.race == 1 and x.mode == 0x14]), at_base(after)
    handling_runs.summary(f"goal: the opponents at their base performance on {100 * in_race:.1f} % of the race's car-passes, "
                          f"{100 * past:.1f} % after the goal")
    assert in_race == 0 and past > 0.5, (in_race, past)


def test_a_race_ending_mid_lock_leaves_the_next_games_clean(handling_runs):
    """A RAIN race ended by time over while the brake is locked (Review Focus 2): the lock cleared at the next rain-mode pass; the next
    game DRY (Big Forest): SWITCH 0, the handling's cells untouched through its race while the brake is held at speed; the third
    game RAIN: its load zeroes the cells, its held brake locks as the first race's did."""
    r = handling_runs.run("end_locked")
    last = [x for x in r.f if x.race == 1 and x.mode == 0x14][-1]
    assert last.lock == 1, last
    after = [x for x in r.f if x.race == 1 and x.frame > last.frame][:12]
    assert after and after[-1].lock == 0 and after[-1].lock_count == 0, [(x.mode, x.lock) for x in after]
    two = [x for x in r.f if x.race == 2]
    assert len(two) > 300 and not any(x.switch for x in two)
    assert len({x[30:40] for x in two}) == 1, "the handling's cells changed in a DRY game"
    r.trigger("kmh150", 2)
    three = [x for x in r.f if x.race == 3]
    assert three and (three[0].spins, three[0].locks, three[0].lock) == (0, 0, 0), three[0]
    t = r.trigger("kmh280", 3)
    lk = next(x for x in r.f if x.frame >= t and x.lock)
    handling_runs.summary(f"end mid-lock: locked at the time over ({last.frame}), cleared by {after[-1].frame}; DRY game {len(two)} "
                          f"frames, cells still; RAIN game: cells 0 at its load, locked {lk.frame - t} frames after its brake")
    assert 14 <= lk.frame - t <= 20 and lk.locks == 1


def test_a_race_ending_mid_spin_leaves_the_next_game_clean(handling_runs):
    """A RAIN race ended by time over while the spin-out runs: the cool-down cleared at the next rain-mode pass; the next game RAIN:
    the cells zero at its load and its full lock on full gas spins as the first race's (SPIN_WINDOW_S)."""
    r = handling_runs.run("end_spinning")
    last = [x for x in r.f if x.race == 1 and x.mode == 0x14][-1]
    assert last.spinout != 0 and last.cool > 0 and last.spins >= 1, last
    after = [x for x in r.f if x.race == 1 and x.frame > last.frame][:12]
    assert after[-1].cool == 0, [(x.mode, x.cool) for x in after]
    two = [x for x in r.f if x.race == 2]
    assert two and (two[0].spins, two[0].cool) == (0, 0), two[0]
    t = r.trigger("rp240", 2)
    fire = next(x for x in r.f if x.frame > t and x.spins > r.at(t).spins)
    handling_runs.summary(f"end mid-spin: spinning at the time over ({last.frame}, cool-down {last.cool}), cleared; next game spins "
                          f"{_s(fire.frame - t):.2f} s after its wheel")
    assert SPIN_WINDOW_S[0] <= _s(fire.frame - t) <= SPIN_WINDOW_S[1]


def _laps(r) -> dict:
    """car -> {lap: the frame its lap counter became that lap}."""
    out: dict = {}
    for frame, _, car, lap in r.log.laps:
        out.setdefault(car, {}).setdefault(lap, frame)
    return out


def test_the_opponents_lap_about_3_percent_slower(handling_runs):
    """Big Forest with the player standing on the grid (the clock held), RAIN against DRY on the same set: each opponent's first
    flying lap (from its lap counter's change to 1 to its change to 2) about 3 % longer in RAIN (x0.97 on its working
    performance): 2-4.5 % on the mean over the opponents."""
    wet, dry = handling_runs.run("opp_rain"), handling_runs.run("opp_dry")
    lw, ld = _laps(wet), _laps(dry)
    ratios = []
    for car in range(1, 16):
        if all(k in x.get(car, {}) for x in (lw, ld) for k in (1, 2)):
            ratios.append((lw[car][2] - lw[car][1]) / (ld[car][2] - ld[car][1]))
    mean = sum(ratios) / len(ratios) if ratios else 0
    handling_runs.summary(f"opponents: {len(ratios)} flying laps, RAIN / DRY {mean:.4f} (min {min(ratios, default=0):.4f}, max "
                          f"{max(ratios, default=0):.4f})")
    assert len(ratios) >= 8 and 1.02 <= mean <= 1.045, (len(ratios), mean, ratios)


def test_a_dry_races_handling_fields_are_mains(handling_runs):
    """The same scripted DRY race (SCRIPT: full gas, full lock, a held brake with the wheel turned, brake taps, full lock the other
    way) on the weather set and on the switch-off set: the player's handling fields, the opponents' working performance, the engine
    and squeal sound commands identical on every frame from the race start."""
    a, b = handling_runs.run("fields_set"), handling_runs.run("fields_main")
    fa, fb = [x[:29] + x[40:] for x in a.f], [x[:29] + x[40:] for x in b.f]   # the switch and the cells left out
    n = min(len(fa), len(fb))
    first = next((i for i in range(n) if fa[i] != fb[i]), None)
    handling_runs.summary(f"DRY fields: {n} frames compared, first difference {first}")
    assert n > 1000 and first is None, (first, fa[first] if first is not None else None, fb[first] if first is not None else None)
    assert max(abs(x.slide) for x in a.f) > 200 and any(x.lock_timer for x in a.f), (max(abs(x.slide) for x in a.f),)   # S built


def test_the_grip_base_and_the_player_out_of_the_opponents_factor(handling_runs):
    """The grip base (S5.7: -16): the same RAIN race under cover to 280 km/h on both runs, then open on one: 38 % lock there; the
    grip (+0x164) on the open run settles 16 under the covered run's for 5 passes or more (the game moves the grip toward its target
    by at most 12 a pass down, at once up; later the wet slide from 420 parts the two paths). The player out of the opponents'
    factor: no rule firing (GENTLE: the wheel straight, under the wheelspin's gas), RAIN against DRY on the weather set, the
    opponents' factor at work: on the start straight, from the green to its first slowdown (the wheel held straight meets the first
    bend's wall; there the stopped car is passed by opponents whose timing differs), the player's speed and place the same on every
    pass, its top speed included; and on every race pass the player's own +0x48, which the opponents' site stores for the player
    too (on the passes its steering fade-in runs that code: here from the wall on), the DRY race's."""
    a, b = handling_runs.run("grip_open"), handling_runs.run("grip_cover")
    t = a.trigger("kmh280")
    assert t == b.trigger("kmh280")
    pa, pb = {x.frame: x for x in a.f}, {x.frame: x for x in b.f}
    before = [f for f in pa if f < t and f in pb]
    assert before and all(pa[f][:29] == pb[f][:29] for f in before), "the two runs part before the cover ends"
    after = [f for f in sorted(pa) if t <= f < t + 60 and f in pb]
    d = [pa[f].grip - pb[f].grip for f in after]
    handling_runs.summary(f"grip: from the lock at {t} ({pa[after[0]].kmh} km/h) open - covered {d[:16]}; covered grip "
                          f"{[pb[f].grip for f in after[:16]]}")
    run16 = max((len(list(g)) for k, g in __import__("itertools").groupby(d[:20]) if k == -16), default=0)
    assert all(-16 <= x <= 0 for x in d[:16]) and run16 >= 5, d[:20]      # settled 16 under (before the paths part: the slide)
    w, y = handling_runs.run("player_rain"), handling_runs.run("player_dry")
    rw, ry = [x for x in w.f if x.mode == 0x14], [x for x in y.f if x.mode == 0x14]
    n = next(k for k in range(10, len(rw)) if rw[k].kmh < rw[k - 1].kmh)        # the straight: to its first slowdown
    kw, ky = [(x.frame, x.kmh, x.x, x.z, x.player_perf) for x in rw[:n]], [(x.frame, x.kmh, x.x, x.z, x.player_perf) for x in ry[:n]]
    opp = sum(p.opponents != q.opponents for p, q in zip(rw[:n], ry[:n]))
    own = [(p.frame, hex(p.player_perf), hex(q.player_perf)) for p, q in zip(rw, ry) if p.player_perf != q.player_perf]
    handling_runs.summary(f"player: the start straight {n} race passes RAIN against DRY, speed and place the same on every one: "
                          f"{kw == ky}; top {max(k[1] for k in kw)} / {max(k[1] for k in ky)} km/h; the opponents' working "
                          f"performance differs on {opp} of those passes; the first speed difference later at pass "
                          f"{next((k for k, (p, q) in enumerate(zip(rw, ry)) if p.kmh != q.kmh), None)}; the player's +0x48 differs on "
                          f"{len(own)} of {min(len(rw), len(ry))} race passes")
    assert n > 200 and max(k[1] for k in kw) > 180 and kw == ky and opp > n // 2, (n, opp, next(((p, q) for p, q in zip(kw, ky) if p != q), None))
    assert len(rw) > 600 and not own and any(x.player_perf for x in rw), own[:5]


def test_the_hooks_cost(handling_runs):
    """The hooks' time, measured: a DRY race (the wheel straight, the gas floored) on the weather set, on the set without the handling
    and on the switch-off set, pass for pass the same game: the handling's dry paths cost the busy-time difference set - without;
    a RAIN race whose inputs fire no rule (GENTLE: the game's pedal 157, under the wheelspin's gas, the wheel straight) on the probe set (the handling with the opponents' factor 1.0:
    every gate evaluated, nothing changed) against the set without the handling, the same game: the wet routines' cost. The calls
    per pass of each hook from the stubs' reads of the weather byte. Written to the summary; DRY at most DRY_COST_MAX_US on the mean
    pass. The attract's busiest pass (outside its scene loads) with the handling at most DRY_COST_MAX_US above the set without it,
    with no lower bound (the session lead's ruling of 19 Nov 2026, at the join: the busiest pass of two differently laid-out sets is
    not a sum; on the joined sets it measured 17.702 ms with the handling against 17.708 ms without, the same pass, while the
    per-pass difference over the attract ran from -30 to +93 us, mean +23.6; alone, stage 5 had measured +26 us); the difference
    and the per-pass range are written to the summary."""
    from vrtools.mame.framerate import parse_pass_log
    from vrtools.arcade.weather import handling

    def busy(r):
        return {f.frame: f.busy_us for f in r.rate.frames if r.rate.start and f.frame >= r.rate.start}

    def same(a, b):
        pa, pb = parse_pass_log(a.wd / "pass.txt"), parse_pass_log(b.wd / "pass.txt")
        n = min(len(pa), len(pb))
        return n > 1500 and pa[:n] == pb[:n]

    def diff(a, b, modes=None):
        ba, bb = busy(a), busy(b)
        mode = {x.frame: x.mode for x in a.f}
        common = [f for f in sorted(set(ba) & set(bb)) if modes is None or mode.get(f) in modes]
        d = [ba[f] - bb[f] for f in common]
        return sum(d) / len(d), sorted(d)[len(d) // 2], len(d)

    def calls(r):
        per = [0] * len(handling.SITES)
        frames = [c for c in r.log.calls if r.rate.start and c[0] >= r.rate.start]
        for _, cs in frames:
            per = [p + c for p, c in zip(per, cs)]
        return {s.name: round(2 * p / max(len(frames), 1), 2) for s, p in zip(handling.SITES, per)}   # a pass is two frames
    runs = {n: handling_runs.run(n) for n in NEEDS["test_the_hooks_cost"]}
    assert same(runs["cost_dry_set"], runs["cost_dry_plain"]) and same(runs["cost_dry_set"], runs["cost_dry_main"])
    assert same(runs["cost_rain_probe"], runs["cost_rain_plain"])
    hd = diff(runs["cost_dry_set"], runs["cost_dry_plain"])
    td = diff(runs["cost_dry_set"], runs["cost_dry_main"])
    wr = diff(runs["cost_rain_probe"], runs["cost_rain_plain"], modes=(0x14,))
    wc = diff(runs["cost_rain_probe"], runs["cost_rain_plain"], modes=(0x12, 0x13))
    handling_runs.summary(f"cost: DRY race passes {hd[2]}: the handling's dry paths mean {hd[0]:.2f} us a pass (median {hd[1]}); the "
                          f"whole storm's DRY cost against the switch-off set mean {td[0]:.2f} (median {td[1]}); calls a pass DRY "
                          f"{calls(runs['cost_dry_set'])}; RAIN race passes {wr[2]}: the wet routines (no rule fired) mean {wr[0]:.2f} us "
                          f"(median {wr[1]}), countdown passes {wc[2]}: mean {wc[0]:.2f} (median {wc[1]}); calls a pass RAIN "
                          f"{calls(runs['cost_rain_probe'])}")
    assert 0 <= hd[0] <= DRY_COST_MAX_US and wr[0] >= hd[0], (hd, td, wr)
    # the attract (its demo races run the opponents' site): its busiest pass outside the scene loads, the set against the set without
    # the handling (the session lead's ruling of 19 Nov 2026: at most the handling's dry path)
    frames = {k: {f.frame: f.busy_us for f in handling_runs.run(k).rate.frames if f.busy_us < 34_770}
              for k in ("attract_set", "attract_plain")}
    att = {k: max(v.values()) for k, v in frames.items()}
    per = sorted(frames["attract_set"][f] - frames["attract_plain"][f] for f in set(frames["attract_set"]) & set(frames["attract_plain"]))
    handling_runs.summary(f"cost: the attract's busiest pass (outside its scene loads, 200 s) {att['attract_set'] / 1000:.3f} ms, without "
                          f"the handling {att['attract_plain'] / 1000:.3f} ms: {att['attract_set'] - att['attract_plain']:+d} us; per pass "
                          f"(the set less the set without) {per[0]:+d} to {per[-1]:+d} us, mean {sum(per) / len(per):+.1f}, {len(per)} passes")
    assert att["attract_set"] - att["attract_plain"] <= DRY_COST_MAX_US, att      # no lower bound: the lead's ruling (docstring)


# The handling's dry paths on a DRY race pass, and on the attract's busiest: measured 41.5 us on the mean DRY race pass (about 22 calls
# a pass, 15 of them the opponents' site); the session lead's ruling of 19 Nov 2026 accepts this cost, bounded here (docs/deviations.md).
DRY_COST_MAX_US = 50


def test_the_designs_values_are_the_codes(romset_zip, saturn_cue):
    """Each value of S5.7's table is the immediate of its test in the wet routines (as built from HandlingTune's defaults): the slide
    from 420 and the gas gate 128, the spin at 0x900 above 100 km/h and its cool-down 77, the grip base -16, the take-off's x0.6 fading
    at 60 km/h in gears 1-3, the lock at the pedal 204 for 8 logic frames at 100 km/h, its release under 102 or at 20 km/h, the clamp
    -1583.0, the squeal from 280, the opponents x0.97."""
    from vrtools.arcade.v60asm import float_bits
    s1, _, _ = _sets(romset_zip, saturn_cue)
    routines, _, _, _ = _routines(s1)
    want = {"slide": ["cmp.w #1A4, R1", "cmp.w #80, R0", "cmp.w #900, R0", "cmp.w #900, R1", "cmp.w #64, 14[R25]", "mov.b #4D, "],
            "grip": ["add.w #FFFFFFF0, R20"],
            "wspin": [f"subf.s #{float_bits(0.6):X}, R14", f"addf.s #{float_bits(0.6):X}, R12", f"divf.s #{float_bits(60.0):X}, R12",
                      "cmp.w #3C, 14[R25]", "cmp.w #3, 156[R25]"],
            "brake": ["cmp.w #CC, R0", "cmp.w #8, R0", "cmp.w #64, 14[R25]", "cmp.w #66, R0", "cmp.w #14, 14[R25]",
                      f"cmpf.s #{float_bits(-1583.0):X}, R11", f"mov.w #{float_bits(-1583.0):X}, R11"],
            "squeal": ["sub.w #118, R0"], "opp": [f"mulf.s #{float_bits(0.97):X}, R0"]}
    for name, items in want.items():
        text = _text(routines[name])
        missing = [w for w in items if not any(t.startswith(w) for t in text)]
        assert not missing, (name, missing)
