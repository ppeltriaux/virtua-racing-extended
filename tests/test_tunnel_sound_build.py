"""Phase 37 (prototype): the arcade's tunnel sound on the converted courses' named stretches (`CoursePlan.tunnels`), on the built
set against the same conversions built without the stretches ("main's": every plan's `tunnels` emptied, nothing else).

The mechanism (recon, docs/spike/2026-11-phase37-tunnel-sound-recon.md §1): bit 7 of the segment flag of the quad under the
player's car; boot 0xffa671 sends C201 when it comes on and C200 when it goes off; the sound board keeps one bit, which C200 and
the reset 8100 clear. Needs VR_ROMDIR and VR_SATURN_CUE; two conversions of the seven courses and about twenty MAME runs.

Weather Task 6J round 2 (the whole suite): both sets are built with the weather switch off (`ten_course_set(..., weather=False)`,
tests.test_weather_dry's `_seven_dry`): the comparison set without the stretches cannot carry the weather (the cover refuses a
course whose cover stretches are not tunnel-flagged: Alpine's 108-146), and the switch-off set is the game this module tested;
the weather set's DRY game is the switch-off set's, pass for pass (tests/test_weather_dry.py::test_dry_is_mains_race_pass_for_pass)
and the V60's sound words exactly, the tunnel's C201 / C200 among them, on Metropolis both ways
(tests/test_weather_dry.py::test_dry_sends_mains_sound_words, entry 6: the standing gate of the tunnel words on the WEATHER set),
and its RAIN cover by the same flags is tests/test_weather_cover.py's."""
import shutil
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from vrtools.arcade.course import DIRECTION_RAM, course_entry_at, course_table, road_lines, segments, _win
from vrtools.arcade.directory import decode_directory
from vrtools.arcade.romset import RomSet
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.arcade.tencourse import COURSES as PLANS
from vrtools.convert.reverse import reverse_points
from vrtools.convert.road import FLAG_PLAIN, FLAG_TUNNEL
from vrtools.mame.framerate import parse_pass_log
from vrtools.mame.pitpaths import normal_pit_path, pit_lane, reverse_pit_path, stop_frames
from vrtools.mame.runner import (LUA_DIR, PIT_HANDLER, PLAYER_HANDLER, RACE_MODE, SOUND_RESET, SOUND_TUNNEL_OFF, SOUND_TUNNEL_ON,
                                 parse_pit_log, parse_sound_log, run_mame, write_centreline)

BAY_BRIDGE, ALPINE, METROPOLIS = 1, 3, 6
STRETCHES = {ALPINE: ((108, 146),), METROPOLIS: ((50, 62), (251, 311))}     # what Pascal agreed (16 Nov), as the plans carry it
RACES = [(ALPINE, False), (ALPINE, True), (METROPOLIS, False), (METROPOLIS, True)]
SECONDS = 150               # a race: every stretch passed at least once in both directions
BAY_SECONDS = 60            # Bay Bridge: its tunnel (quads 69-88) lies 16 s after the green
ATTRACT_SECONDS = 300
TIMEOUT_SECONDS = 110       # the race runs out of time in Metropolis's first stretch, then the game's own way to the attract
CYCLE_SECONDS = 300         # a one-lap game to its end, the attract, a coin, a second game (race_end.lua)
PIT_SECONDS, REVERSE_PIT_SECONDS, REVERSE_AHEAD = 150, 180, 15              # as tests/test_pit_build.py's
COMMAND_FRAMES = 10         # video frames from the flag's change under the car (a frame end) to the command's low byte at the latch:
                            # the queue gives the engine's and the tyres' words their turns (measured 1-6 in the recon)
SETTLED = 12                # frames after a change of flag, mode or handler from which the board's bit must equal the flag's
ENTRY_POINTS = 6            # a pass begins on a quad credited within this many road points of the stretch's end it is entered by
                            # (consecutive tarmac quads step at most 6 points)
PUTBACKS = {ALPINE: 93, METROPOLIS: 395}    # the quad (inside the mountain tunnel, the long tunnel) at which the wheel is held over
PUTBACK_SECONDS = {ALPINE: 80, METROPOLIS: 110}
PUTBACK_LIMIT = 1           # the off-course limit during the hold, logic frames (the walls keep a car on the tarmac in a tunnel)
BAY_QUADS = (69, 88)        # the arcade's own tunnel: flag 0x81 on these quads of Bay Bridge
MAME_WORKERS = 4            # threads; VR_MAME_JOBS bounds the MAME processes

_SESSION: dict = {}
_LOCK = threading.Lock()


def _zip_dir(base: Path, romset_zip: Path, rs: RomSet) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    rs.to_zip(base / "vr.zip", source=romset_zip)
    for extra in ("model1io.zip", "m1comm.zip"):
        shutil.copy(romset_zip.parent / extra, base / extra)
    return base


class Session:
    """The built set, the same built without the stretches, and every run of this module (made in two waves at the first use)."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        from tests.test_race_build import _drive_line
        from tests.test_weather_dry import _seven_dry
        from vrtools.arcade.tencourse import build_all, ten_course_set
        self.romset_zip, self.saturn_cue, self.base = romset_zip, saturn_cue, base
        self.source = RomSet.from_zip(romset_zip)
        self.out, self.conv = _seven_dry(romset_zip, saturn_cue)                     # the weather off (round 2: see above)
        plain, plain_conv = build_all(self.source, saturn_cue, [replace(p, tunnels=()) for p in PLANS])
        self.plain, self.plain_conv = ten_course_set(plain, plain_conv, weather=False), plain_conv
        self.sets = {"new": _zip_dir(base / "new", romset_zip, self.out), "main": _zip_dir(base / "main", romset_zip, self.plain)}
        self.dir = decode_directory(self.out)
        self.lines = {e: _drive_line(self.conv[e - 3]) for e in (ALPINE, METROPOLIS)}
        self.lines[BAY_BRIDGE] = [(p.x, p.z) for p in self.road(BAY_BRIDGE)[0]]
        self.runs: dict = {}
        self.failed: dict = {}
        self._made = False
        self._tunnel: dict = {}

    def entry(self, e: int, reverse: bool = False, rs: RomSet | None = None):
        d = decode_directory(rs or self.out)[e]
        rec = d.reverse.entry if reverse else d
        return course_entry_at(rs or self.out, rec.bank, window_base=rec.header_base)

    def road(self, e: int):
        return road_lines(self.out, self.entry(e))

    def tunnel(self, e: int) -> dict[int, int]:
        """{quad: index of its stretch} for the entry's flagged quads, from the conversion's report and the normal array's points."""
        if e not in self._tunnel:
            self._tunnel[e] = self._tunnel_of(e)
        return self._tunnel[e]

    def _tunnel_of(self, e: int) -> dict[int, int]:
        segs = segments(self.out, self.entry(e))
        out = {}
        for q in self.conv[e - 3].report["tunnel_quads"]:
            out[q] = next(i for i, (a, b) in enumerate(STRETCHES[e]) if a <= segs[q].road_point <= b)
        return out

    def _env(self, wd: Path, e: int, line, reverse: bool) -> dict:
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[e]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
               "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", line)), "VR_SOUND_LOG": str(wd / "sound.txt")}
        if reverse:
            env["VR_DIRECTION"] = "1"
        return env

    def _make(self, key):
        kind = key[0]
        wd = self.base / "runs" / "_".join(str(k) for k in key)
        wd.mkdir(parents=True, exist_ok=True)
        if kind == "race":                                     # main's set with the autopilot, its inputs taped; the set replays them
            _, e, reverse, which = key
            line = reverse_points(self.lines[e]) if reverse else self.lines[e]
            env = self._env(wd, e, line, reverse)
            env.update({"VR_HOLD_CLOCK": "1", "VR_PASS_LOG": str(wd / "pass.txt"), "VR_INPUT_LOG": str(wd / "tape.txt")})
            if which == "new":
                env["VR_INPUT_REPLAY"] = str(self._earlier(("race", e, reverse, "main")) / "tape.txt")
            run_mame(LUA_DIR / "autoplay.lua", SECONDS, wd, self.sets[which], env=env, timeout=3600)
        elif kind == "bay":
            env = self._env(wd, BAY_BRIDGE, self.lines[BAY_BRIDGE], False)
            env["VR_HOLD_CLOCK"] = "1"
            run_mame(LUA_DIR / "autoplay.lua", BAY_SECONDS, wd, self.sets[key[1]], env=env, timeout=3600)
        elif kind == "attract":
            run_mame(LUA_DIR / "attract_snaps.lua", ATTRACT_SECONDS, wd, self.sets["new"],
                     env={"VR_SNAP_FROM": "999999", "VR_SOUND_LOG": str(wd / "sound.txt")}, timeout=3600)
        elif kind == "timeout":
            env = self._env(wd, METROPOLIS, self.lines[METROPOLIS], False)
            env["VR_SOUND_TIMEOUT"] = "1"
            run_mame(LUA_DIR / "autoplay.lua", TIMEOUT_SECONDS, wd, self.sets["new"], env=env, timeout=3600)
        elif kind == "cycle":                                  # a normal game of one lap, the attract, a coin, a reverse game of one lap
            env = self._env(wd, METROPOLIS, self.lines[METROPOLIS], False)
            env.update({"VR_EXTRA_LUA": str(LUA_DIR / "race_end.lua"), "VR_END_LOG": str(wd / "end.txt"),
                        "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}", "VR_END_NEXT": f"{WHEEL_FOR_ENTRY[METROPOLIS]}:1",
                        "VR_END_NEXT_LINE": str(write_centreline(wd / "reverse.csv", reverse_points(self.lines[METROPOLIS])))})
            run_mame(LUA_DIR / "autoplay.lua", CYCLE_SECONDS, wd, self.sets["new"], env=env, timeout=3600)
        elif kind == "putback":                                # the review's staging (putback.lua), the same on both sets
            _, e, which = key
            line = [(p.x, p.z) for p in self.road(e)[6]]
            env = self._env(wd, e, line, False)
            env.update({"VR_HOLD_CLOCK": "1", "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0",
                        "VR_EXTRA_LUA": str(LUA_DIR / "putback.lua"), "VR_PUTBACK_QUAD": str(PUTBACKS[e]),
                        "VR_PUTBACK_LIMIT": str(PUTBACK_LIMIT), "VR_PUTBACK_LOG": str(wd / "putback.txt")})
            run_mame(LUA_DIR / "autoplay.lua", PUTBACK_SECONDS[e], wd, self.sets[which], env=env, timeout=3600)
        elif kind == "pit":
            reverse = key[1]
            line6 = [(p.x, p.z) for p in self.road(METROPOLIS)[6]]
            if reverse:
                path = reverse_pit_path(parse_pit_log(self._earlier(("pit", False, "new")) / "pit.txt"), line6)
            else:
                lane = pit_lane(self.source, self.saturn_cue, PLANS[METROPOLIS - 3], self.conv[METROPOLIS - 3].centreline)[0]
                path = normal_pit_path(line6, lane)
            env = self._env(wd, METROPOLIS, path, reverse)
            env.update({"VR_HOLD_CLOCK": "1", "VR_PIT_LOG": str(wd / "pit.txt")})
            if reverse:
                env["VR_AUTOPILOT_AHEAD"] = str(REVERSE_AHEAD)
            run_mame(LUA_DIR / "autoplay.lua", REVERSE_PIT_SECONDS if reverse else PIT_SECONDS, wd, self.sets[key[2]], env=env,
                     timeout=3600)                               # the same path on both sets (the reverse one from the set's normal run)
        else:
            raise KeyError(key)
        return wd

    def _earlier(self, key) -> Path:
        """A first-wave run a second-wave run is made from (its failure is the second's)."""
        if key in self.failed:
            raise self.failed[key]
        return self.runs[key]

    def _wave(self, keys):
        def one(k):
            try:
                self.runs[k] = self._make(k)
            except BaseException as e:                         # kept: the test that asks for the run raises it
                self.failed[k] = e
        with ThreadPoolExecutor(MAME_WORKERS) as pool:
            list(pool.map(one, [k for k in keys if k not in self.runs and k not in self.failed]))

    def run(self, key) -> Path:
        with _LOCK:
            if not self._made:
                self._made = True
                first = [("race", e, r, "main") for e, r in RACES] + [("bay", "new"), ("bay", "main"), ("attract",), ("timeout",),
                                                                      ("cycle",), ("pit", False, "new"), ("pit", False, "main")]
                first += [("putback", e, w) for e in PUTBACKS for w in ("new", "main")]
                self._wave(first)
                self._wave([("race", e, r, "new") for e, r in RACES] + [("pit", True, "new"), ("pit", True, "main")])
        if key in self.failed:
            raise self.failed[key]
        return self.runs[key]

    def sound(self, key):
        log = parse_sound_log(self.run(key) / "sound.txt")
        assert log.complete and log.commands and log.flags, (key, len(log.commands), len(log.flags))
        return log


@pytest.fixture
def s(romset_zip, saturn_cue, tmp_path_factory) -> Session:
    from tests.session_cache import cached                     # a failed build is cached, not rebuilt by every test (Task 7)
    return cached(_SESSION, str(romset_zip), lambda: Session(romset_zip, saturn_cue, tmp_path_factory.mktemp("tunnel")))


# --- the bytes -------------------------------------------------------------------------------------------------------------------

def _flag_offsets(s: Session, e: int, reverse: bool) -> list[int]:
    """The data-ROM offsets of the low bytes of the flags of the entry's tunnel quads, in its normal or reverse array."""
    ce = s.entry(e, reverse)
    base = _win(ce.base, ce.header.seg_array, "segment array")
    return [base + 8 * (q + 1) + 6 for q in sorted(s.tunnel(e))]


def test_the_set_is_main_s_byte_for_byte_but_the_named_flag_bytes(s):
    """Against the same conversions built without the stretches: the program, boot and polygon ROMs, the TGP's data (the collision)
    and program are identical; the data ROMs differ in exactly one byte per tunnel quad per array (the flag's low byte, 0x01 on
    main, 0x81 here), in Alpine's and Metropolis's normal and reverse segment arrays, and nowhere else."""
    for region in ("program", "boot", "polygons", "copro_data", "tgp_program"):
        assert getattr(s.out, region) == getattr(s.plain, region), region
    named = sorted(o for e in STRETCHES for r in (False, True) for o in _flag_offsets(s, e, r))
    differ = [i for i, (a, b) in enumerate(zip(s.out.data, s.plain.data)) if a != b]
    assert len(s.out.data) == len(s.plain.data) and differ == named
    assert all(s.plain.data[o] == FLAG_PLAIN and s.out.data[o] == FLAG_PLAIN | FLAG_TUNNEL and s.out.data[o + 1] == 0 for o in named)
    counts = {e: len(s.tunnel(e)) for e in STRETCHES}
    assert len(named) == 2 * sum(counts.values()) and all(counts.values()), counts


def test_every_flag_of_a_converted_course_is_plain_or_the_tunnel_s_and_both_arrays_flag_the_same_quads(s):
    for e in range(3, 10):
        for reverse in (False, True):
            segs = segments(s.out, s.entry(e, reverse))
            flagged = sorted(g.index for g in segs if g.flag != FLAG_PLAIN)
            assert {g.flag for g in segs} <= {FLAG_PLAIN, FLAG_PLAIN | FLAG_TUNNEL}, (e, reverse)
            assert flagged == (sorted(s.tunnel(e)) if e in STRETCHES else []), (e, reverse)
    for e, stretches in STRETCHES.items():
        segs = segments(s.out, s.entry(e))
        assert sorted(s.tunnel(e)) == [g.index for g in segs if any(a <= g.road_point <= b for a, b in stretches)]
        assert set(s.tunnel(e).values()) == set(range(len(stretches)))            # every stretch has quads


def test_metropolis_s_pit_quads_and_boxes_lie_on_flagged_quads_of_the_first_stretch(s):
    """Pascal's answer 4: the pit lane under roof A sounds like the road beside it. The lane's quads under the roof are credited to
    the stretch's own points, so the point list flags them: the normal entry's pit pair and the reverse variant's are among them."""
    d = s.dir[METROPOLIS]
    t = s.tunnel(METROPOLIS)
    for q in (d.pit_quad, d.pit_quad + 1, d.reverse.entry.pit_quad, d.reverse.entry.pit_quad + 1):
        assert t.get(q) == 0, (q, t.get(q))


def test_the_three_originals_segment_arrays_are_the_source_set_s(s):
    """Byte for byte the arcade's, in the banks where the arcade has them; Bay Bridge's tunnel is its quads 69-88 and nothing else
    of the three carries bit 7."""
    for c, ce in enumerate(course_table(s.source)):
        base = _win(ce.base, ce.header.seg_array, "segment array")
        size = 8 * (ce.header.segment_count + 1)
        assert s.out.data[base:base + size] == s.source.data[base:base + size], c
        on = [g.index for g in segments(s.out, ce) if g.flag & FLAG_TUNNEL]
        assert on == (list(range(BAY_QUADS[0], BAY_QUADS[1] + 1)) if c == 1 else []), c


# --- the commands ----------------------------------------------------------------------------------------------------------------

def _edges(log):
    """(frame, bit, quad, road point) at each change of the flag's bit 7 under the car in the race (mode 0x14)."""
    out, prev = [], None
    for f in log.flags:
        bit = f.flag >> 7 & 1
        if f.mode == RACE_MODE and prev is not None and bit != prev:
            out.append((f.frame, bit, f.quad, f.road_point))
        prev = bit
    return out


def _board_follows(log, key):
    """From SETTLED frames after any change of the flag's bit, the mode or the handler, in the race, the board's bit is the flag's."""
    since, state, bad = None, None, []
    for f in log.flags:
        now = (f.flag >> 7 & 1, f.mode, f.handler)
        if now != state:
            state, since = now, f.frame
        elif f.mode == RACE_MODE and f.frame - since >= SETTLED and log.bit_at(f.frame) != now[0]:
            bad.append((f.frame, now, log.bit_at(f.frame)))
    assert bad == [], (key, bad[:5])


def _commands_match_edges(log, key):
    """One C201 for each time the bit comes on under the car and one C200 for each time it goes off, in order, each within
    COMMAND_FRAMES of the change, and no other C2xx in the run."""
    edges = _edges(log)
    c2 = [(f, c) for f, c in log.commands if c >> 8 == 0xC2]
    assert [c for _, c in c2] == [SOUND_TUNNEL_ON if bit else SOUND_TUNNEL_OFF for _, bit, _, _ in edges], (key, c2[:6], edges[:6])
    late = [(e[0], f) for e, (f, _) in zip(edges, c2) if not 0 <= f - e[0] <= COMMAND_FRAMES]
    assert late == [], (key, late)
    return edges


@pytest.mark.parametrize("e,reverse", RACES)
def test_each_stretch_switches_the_sound_on_at_its_mouth_and_off_at_its_exit_once_a_pass(s, e, reverse):
    """The set's race (main's inputs replayed): every time the car comes onto a flagged quad the game sends C201 within
    COMMAND_FRAMES frames, every time it leaves one C200, and nothing else moves the board's bit during the race. Each pass lies in
    one stretch, begins within ENTRY_POINTS road points of the end it is entered by (the first point in the normal direction, the
    last in reverse) and ends on a quad outside; every stretch is passed, in both directions."""
    key = ("race", e, reverse, "new")
    log = s.sound(key)
    edges = _commands_match_edges(log, key)
    _board_follows(log, key)
    t, segs = s.tunnel(e), segments(s.out, s.entry(e))
    assert len(edges) >= 2 * len(STRETCHES[e]) and edges[0][1] == 1
    passes = [(a, b) for a, b in zip(edges, edges[1:]) if a[1] == 1]
    seen = set()
    for (f_on, _, q_on, _), (f_off, bit, q_off, _) in passes:
        k = t[q_on]
        first, last = STRETCHES[e][k]
        inside = [f.quad for f in log.flags if f_on <= f.frame < f_off]
        assert bit == 0 and q_off not in t and all(t.get(q) == k for q in inside), (key, f_on, f_off, q_off)
        p = segs[q_on].road_point                                    # the normal array's point of the quad the pass begins on
        assert (last - p if reverse else p - first) <= ENTRY_POINTS, (key, f_on, q_on, p, first, last)
        seen.add(k)
    assert seen == set(range(len(STRETCHES[e]))), (key, seen)
    assert not [c for f, c in log.tunnel() if c == SOUND_RESET and edges[0][0] <= f <= edges[-1][0]]   # no reset inside the race


def _same_other_commands(new, main, key):
    """The set's commands other than C2xx against main's: the same words, as many of each; the k-th sending of a word comes no
    earlier than main's k-th and at most COMMAND_FRAMES frames later. The order between different words is not compared."""
    by_word = lambda log: {w: [f for f, c in log.commands if c == w] for w in {c for _, c in log.commands if c >> 8 != 0xC2}}
    a, b = by_word(new), by_word(main)
    assert {w: len(v) for w, v in a.items()} == {w: len(v) for w, v in b.items()}, key
    shift = [fa - fb for w in a for fa, fb in zip(a[w], b[w])]
    assert min(shift) >= 0 and max(shift) <= COMMAND_FRAMES, (key, min(shift), max(shift))


@pytest.mark.parametrize("e,reverse", RACES)
def test_the_race_is_main_s_pass_for_pass_and_its_other_sound_commands_are_main_s(s, e, reverse):
    """Main's set (no stretch) with the autopilot, then the set on the same wheel and pedal frame for frame (input_tape.lua): the
    game's state at the end of every logic pass (pass_state.lua: the clock, all 16 cars' x, z, road point, speed and lap, and the
    frame each pass ends in) is identical over the whole run. The sound commands other than C2xx are the same words, as many of
    each, and each comes no earlier than on main's set and at most COMMAND_FRAMES frames later (`_same_other_commands`: a C2xx
    takes a turn of the queue, so a queued command behind it comes later and can change places with a revs or tyre word, which
    are not queued; the review's staged put-back showed such a swap). Main's run sends no C2xx."""
    old, new = s.run(("race", e, reverse, "main")), s.run(("race", e, reverse, "new"))
    ta, tb = (new / "tape.txt").read_text().splitlines(), (old / "tape.txt").read_text().splitlines()
    assert len(ta) > 3000 and ta == tb, (e, reverse, len(ta), len(tb))
    a, b = parse_pass_log(new / "pass.txt"), parse_pass_log(old / "pass.txt")
    assert len(a) > 3000 and len(a) == len(b), (e, reverse, len(a), len(b))
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    assert first is None, (e, reverse, first, a[first][:120], b[first][:120])
    la, lb = s.sound(("race", e, reverse, "new")), s.sound(("race", e, reverse, "main"))
    assert not [c for _, c in lb.commands if c >> 8 == 0xC2]
    assert len(lb.commands) > 1000
    _same_other_commands(la, lb, (e, reverse))


def test_bay_bridge_still_fires_at_its_own_quads_and_its_stream_is_main_s(s):
    """The arcade's tunnel on the built set: C201 as the car comes onto quad 69, C200 as it comes onto quad 89, once each in the
    run; the whole command stream, frame for frame, is the one main's set sends."""
    log, main = s.sound(("bay", "new")), s.sound(("bay", "main"))
    edges = _commands_match_edges(log, "bay")
    assert [(bit, q) for _, bit, q, _ in edges] == [(1, BAY_QUADS[0]), (0, BAY_QUADS[1] + 1)], edges
    assert log.commands == main.commands and log.flags == main.flags


def test_the_attract_sends_no_tunnel_command(s):
    """ATTRACT_SECONDS of the set's attract: no C2xx at all, although the demo's car crosses flagged quads in it (Bay Bridge's
    demo drives through the arcade's tunnel, quads 69-88, flag 0x81 under the car on 20 or more logged frames: the demo's car
    does not run the player's race handler and the race sounds are gated off). The attract's demos in this time show the three
    originals; no demo of a converted course's stretch is in it."""
    log = s.sound(("attract",))
    assert not [(f, c) for f, c in log.commands if c >> 8 == 0xC2]
    crossed = [f for f in log.flags if f.flag & FLAG_TUNNEL and f.mode == 0x03]
    assert len(crossed) >= 20 and {f.quad for f in crossed} <= set(range(BAY_QUADS[0], BAY_QUADS[1] + 1)), len(crossed)
    assert log.flags[-1].frame > 50 * ATTRACT_SECONDS and len({f.mode for f in log.flags}) > 3


# --- nothing leaves the effect on ------------------------------------------------------------------------------------------------

def test_a_race_that_runs_out_of_time_inside_a_stretch_is_followed_by_the_reset(s):
    """The clock is run out on the first frame the car is on a flagged quad (Metropolis's first stretch): C201 was sent; the
    game's own reset 8100 follows the race's end, the board's bit is clear from then on, through GAME OVER and the attract to
    the run's end, and nothing sets it again."""
    log = s.sound(("timeout",))
    moves = log.tunnel()
    on = [f for f, c in moves if c == SOUND_TUNNEL_ON]
    assert len(on) == 1, moves
    end = next(f.frame for f in log.flags if f.frame > on[0] and f.mode != RACE_MODE)
    assert end - on[0] < 60, (on, end)                                      # the race ended inside the stretch, the bit still set
    assert log.bit_at(end - 1) == 1
    reset = next((f for f, c in moves if f > on[0] and c == SOUND_RESET), None)
    assert reset is not None and reset - end <= COMMAND_FRAMES, (on, end, reset, moves)
    assert log.bit_at(reset) == 0 and log.bit_at(log.flags[-1].frame) == 0
    assert {f.mode for f in log.flags if f.frame > reset} - {0x15, 0x16} and log.flags[-1].frame - reset > 2000   # on into the attract


def test_a_finished_game_the_attract_a_coin_and_a_second_game_start_with_the_effect_off(s):
    """A one-lap normal game on Metropolis to its finish, results and attract, a coin, and a one-lap reverse game (race_end.lua):
    in each game the commands follow the flag (both stretches in each), a reset follows each game's last C200, the board's bit is
    clear at every frame outside the two races and at each race's green, and the second game's first tunnel command is a C201."""
    log = s.sound(("cycle",))
    _commands_match_edges(log, "cycle")
    _board_follows(log, "cycle")
    races, cur = [], None
    for f in log.flags:
        if f.mode == RACE_MODE and cur is None:
            cur = f.frame
        elif f.mode != RACE_MODE and cur is not None:
            races.append((cur, f.frame))
            cur = None
    assert len(races) == 2, races
    moves = log.tunnel()
    for k, (a, b) in enumerate(races):
        inside = [c for f, c in moves if a <= f < b]
        assert log.bit_at(a) == 0 and inside[0] == SOUND_TUNNEL_ON and inside.count(SOUND_TUNNEL_ON) == inside.count(SOUND_TUNNEL_OFF) >= 2, (k, inside)
        assert log.bit_at(b) == 0
        assert next(c for f, c in moves if f >= b) == SOUND_RESET, k
    assert not [(f.frame, f.mode) for f in log.flags if not any(a <= f.frame < b for a, b in races) and log.bit_at(f.frame)]


@pytest.mark.parametrize("reverse", [False, True])
def test_a_pit_stop_under_metropolis_s_roof_keeps_the_effect_on_and_ends_it_at_the_way_out(s, reverse):
    """A lap through Metropolis's pit lane, which runs under the first stretch's roof (normal: in at the mouth; reverse: in at the
    normal exit, to the reverse box 40 units deeper). The stop starts on a flagged quad with the board's bit set; from the trigger to
    the release (the pit sequence's handler, the crew's work) no command moves the bit and it stays set; after the release the
    car leaves the roof and one C200 follows; the commands match the flag's changes over the whole run and the bit follows the
    flag."""
    key = ("pit", reverse, "new")
    log = s.sound(key)
    _commands_match_edges(log, key)
    _board_follows(log, key)
    frames = parse_pit_log(s.run(key) / "pit.txt")
    trigger, release = stop_frames(frames)
    t0, t1 = frames[trigger].frame, frames[release].frame
    assert t1 - t0 > 300
    during = [f for f in log.flags if t0 <= f.frame < t1]
    assert during and all(f.handler == PIT_HANDLER or f.frame == t0 for f in during)
    assert all(f.flag & FLAG_TUNNEL and f.quad in s.tunnel(METROPOLIS) for f in during), [(f.frame, f.quad, f.flag) for f in during][:4]
    assert log.bit_at(t0) == 1 and log.bit_at(t1) == 1 and not [c for f, c in log.tunnel() if t0 <= f <= t1]
    after = [(f, c) for f, c in log.tunnel() if f > t1]
    assert after and after[0][1] == SOUND_TUNNEL_OFF and after[0][0] - t1 < 600, after[:3]
    back = next(f for f in log.flags if f.frame >= t1 and f.handler == PLAYER_HANDLER)
    assert back.frame - t1 <= 4
    main = s.run(("pit", reverse, "main"))                          # the same lap on main's set: the same stop, frame for frame
    for name in ("pit.txt", "c.txt"):
        assert (s.run(key) / name).read_bytes() == (main / name).read_bytes(), (key, name)
    _same_other_commands(log, s.sound(("pit", reverse, "main")), key)


@pytest.mark.parametrize("e", sorted(PUTBACKS))
def test_a_put_back_inside_a_stretch_leaves_the_bit_with_the_flag(s, e):
    """The review's staging (theirs: the wheel held, the off-course limit poked down; putback.lua), on both sets: from the frame
    the car is on quad PUTBACKS[e], inside the stretch, the paddle is held hard over for 120 frames with the limit at
    PUTBACK_LIMIT logic frames; the game puts the car back (its timer 0x501160 set) onto a flagged quad. The race log and the
    collision log are byte for byte main's, the put-backs the same; the commands match the flag's changes, C201 and C200 in
    turn, the board's bit follows the flag, and the stretch ends with a C200."""
    new, main = s.run(("putback", e, "new")), s.run(("putback", e, "main"))
    for name in ("race.txt", "c.txt", "putback.txt"):
        assert (new / name).read_bytes() == (main / name).read_bytes(), (e, name)
    lines = [l.split() for l in (new / "putback.txt").read_text().splitlines()]
    assert lines[-1] == ["END"] and lines[0][0] == "H"
    backs = [(int(l[1]), int(l[2]), int(l[3])) for l in lines if l[0] == "B"]
    t = s.tunnel(e)
    assert backs and all(after in t for _, _, after in backs), backs
    log = s.sound(("putback", e, "new"))
    edges = _commands_match_edges(log, ("putback", e))
    _board_follows(log, ("putback", e))
    assert log.bit_at(backs[0][0]) == 1
    assert [bit for f, bit, _, _ in edges if f > backs[0][0]][:1] == [0]
    _same_other_commands(log, s.sound(("putback", e, "main")), ("putback", e))
