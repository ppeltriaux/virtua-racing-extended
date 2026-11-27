"""Phase 90 fix round 1b (I7): pack 2's race gates, on pack 2 built FROM THE TREE once a session (tests/pack_sets.py), for Island,
Mountain and Beltway, normal and reverse. Needs MAME, VR_ROMDIR and VR_PS2_DISC; skips without them (without the disc it FAILS
under VR_REQUIRE_REFERENCE_SETS=1: tests/reference_sets.py).

Every measure is the released tests' own, imported, not copied: test_frame_rate's `Run` (the load, the green, the race's end, the
stretch), `arcade_rate_misses` / `worst_busy` (the rate's three measures and windows) and `_stale_result` (the stale display list);
framerate's RAIN_BUSY_MAX_MS (the rain's cap, test_weather_rain.test_rain_holds_the_rate's); test_race_build's BACKSTEP_MAX (an
opponent's progress never drops more: a put-back); test_weather_dry's `_from_load` and MIN_PASSES (the DRY identity's pass log
measure). The autopilot drives test_pack_rate's line for each course (COURSES: entry, road line, lookahead).

The runs (made together at the first test, JOBS MAME processes):
- ("rain", course, reverse): RAIN, the clock NOT held, RACE_SECONDS: the race runs to the game's own end (time over or the finish);
  the frame, rate, stale-list and race logs, the opponents each frame (race_log.lua's O lines). Gates a (RAIN) and b.
- ("dry", course, reverse): DRY, the clock held, DRY_SECONDS (the released rate test's form). Gate a (DRY). Island normal's DRY run
  replays the inputs of ("off", "island"): Island on pack 2 built with the weather off (--no-weather), the autopilot's inputs
  recorded. Gate e.

Fix round 1c (test_pit_build's, test_reverse_ranking's, test_dirscreen_build's and test_weather_lightning's helpers imported):
- ("pit", "island"): Island normal on the released pit test's normal pit path, the clock not held. Gate c.
- ("pit", "island", True) (task 2): Island reverse on the released reverse pit test's path (the normal pit run read backwards),
  the clock not held. Gate c in reverse.
- ("best", "beltway") then ("boot", "beltway"): a finished one-lap Beltway race on a fresh battery RAM (race_end.lua: the released
  ranking tests' finish, the clock held), then a new boot on its battery RAM (ranking_attract.lua). Gate d.
- ("finish", "island"): Island DRY, the clock held (VR_HOLD_CLOCK), every lap of the race to the game's own finish and on. Gate b.
- ("storm", course): pack 2 built with the lightning's stress tune (`GateSession.stress_set`, a pack_sets variant), RAIN, the
  released stress run's logs. Gate f."""
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

DISC = os.environ.get("VR_PS2_DISC")
JOBS = 3
RACE_SECONDS = 330                  # a RAIN race to its end: the time over (or the finish) and some 30 s of what follows
DRY_SECONDS = 150                   # the released rate test's RATE_SECONDS
STILL_FRAMES = 575                  # 10 s: an opponent whose x and z stay within STILL_UNITS that long is stationary
STILL_UNITS = 1.0
AFTER_END = 600                     # the machine still running passes this many frames after the race's end (no crash)
BEST_SECONDS = 270                  # gate d: a one-lap Beltway race (some 84 s on the autopilot) to its name entry and the attract
BOOT_SECONDS = 700                  # gate d's restart: the boot and the attract's pages round Bay Bridge's group (0, 17, Island 3,
                                    # 10, Beltway 5, 12) to Beltway's page (round 1c's 400 s run: 12, 0, 17 of it, at 4 650-7 000
                                    # frames apart)
FINISH_SECONDS = 400                # gate b's finish: Island's five laps (some 40 s each, the first 48) and what follows the finish
AFTER = {("dry", "island", False): ("off", "island"),    # the runs that read another's: the replay of the off race's tape,
         ("boot", "beltway"): ("best", "beltway"),       # the restart on the race's battery RAM, the reverse pit path read
         ("pit", "island", True): ("pit", "island")}     # from the normal pit run
ISLAND_ENTRY = 3                    # pack 2's menu entries: Island 3, Mountain 4, Beltway 5
CASES = [(c, r) for c in ("island", "mountain", "beltway") for r in (False, True)]
IDS = [f"{c}{'_reverse' if r else ''}" for c, r in CASES]



@pytest.fixture(autouse=True)
def _the_ps2_disc():
    """`mame` or VR_PS2_DISC missing: skip, or FAIL under VR_REQUIRE_REFERENCE_SETS=1 (tests/reference_sets.py's `missing_input`
    and `required_ps2_disc`)."""
    from tests.reference_sets import missing_input, required_ps2_disc
    if shutil.which("mame") is None:
        missing_input("needs MAME")
    required_ps2_disc()


class GateSession:
    def __init__(self, romset_zip: Path, base: Path, tmp_path_factory):
        from tests.pack_sets import built
        self.base, self.romset_zip, self.factory = base, romset_zip, tmp_path_factory
        self.set = built("ps2", romset_zip, tmp_path_factory, ps2_disc=DISC)
        self.runs, self.failed, self._lock = {}, {}, threading.Lock()

    def off_set(self) -> Path:
        from tests.pack_sets import built
        return built("ps2", self.romset_zip, self.factory, ps2_disc=DISC, weather=False)

    def _env(self, wd: Path, course: str, reverse: bool, set_dir: Path) -> dict:
        from tests.test_pack_rate import COURSES, _moved_right
        from vrtools.arcade.course import course_entry_at, road_lines
        from vrtools.arcade.directory import decode_directory
        from vrtools.arcade.pack import PS2
        from vrtools.arcade.romset import RomSet
        from vrtools.arcade.select import wheel_for
        from vrtools.convert.reverse import reverse_points
        from vrtools.mame.runner import write_centreline
        entry, li, look = COURSES[course]
        rs = RomSet.from_zip(set_dir / "vr.zip", verify=False)
        d = decode_directory(rs)
        line = [(p.x, p.z) for p in road_lines(rs, course_entry_at(rs, d[entry].bank, window_base=d[entry].header_base))[
            0 if li == "right" else li]]
        line = _moved_right(line) if li == "right" else line
        env = {"VR_COURSE": "0", "VR_WHEEL": str(wheel_for(entry, PS2.menu)), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
               "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", reverse_points(line) if reverse else line)),
               "VR_AUTOPILOT_LOOKAHEAD": str(look), "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0",
               "VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"), "VR_STALE_LOG": str(wd / "stale_list.txt")}
        if reverse:
            env["VR_DIRECTION"] = "1"
        return env

    def _pit(self, wd: Path, env: dict, reverse: bool = False):
        """Gate c's run: Island, normal, on the released pit test's normal pit path (`pitpaths.normal_pit_path`: the ROM's line 6
        with the lane spliced in; the lane is the conversion's, `ps2course.convert(..., pit=True).pit.line`, read from the disc as
        the build reads it), PIT_SECONDS, the clock not held (test_pit_build's form). A `test_pit_build.PitRun` with the entry's
        pair and box, and `lane`. With `reverse` (task 2, the review's I11): the reverse race on the released reverse test's path
        (`pitpaths.reverse_pit_path`: the normal pit run read backwards joined to line 6 read backwards; VR_AUTOPILOT_AHEAD =
        REVERSE_AHEAD), REVERSE_SECONDS, the field logged (fieldtrace.lua) as the released reverse run's; the pair and box are the
        reverse variant's record's, checked against the build's rule (`ps2entry.reverse_pit_of` on the same conversion)."""
        from tests.test_pit_build import REVERSE_AHEAD, REVERSE_SECONDS, SECONDS as PIT_SECONDS, PitRun
        from vrtools.arcade import tencourse as T
        from vrtools.arcade.course import course_entry_at, road_lines
        from vrtools.arcade.directory import decode_directory
        from vrtools.arcade.pack import ISLAND
        from vrtools.arcade.romset import RomSet
        from vrtools.convert import ps2course as PC
        from vrtools.mame.pitpaths import normal_pit_path
        from vrtools.mame.runner import LUA_DIR, parse_pit_log, run_mame, write_centreline
        from vrtools.ps2.course import load_from_disc
        from vrtools.ps2.disc import Ps2Disc
        rs = RomSet.from_zip(self.set / "vr.zip", verify=False)
        e = decode_directory(rs)[ISLAND_ENTRY]
        conv = PC.convert(load_from_disc(Ps2Disc(DISC), ISLAND.index),
                          PC.Frame.for_host(RomSet.from_zip(self.romset_zip), T.HOST_OF_BANK[ISLAND.bank]), pit=True)
        assert e.name == "ISLAND" and e.pit_quad == conv.pit_quad and e.pit_box[3] == conv.pit.box[3] and \
            all(abs(a - b) <= 0.01 for a, b in zip(e.pit_box[:3], conv.pit.box[:3])), (e.pit_quad, e.pit_box, conv.pit_quad, conv.pit.box)
        # (the build's lane: its pair and box are the ROM's; the box's floats stored as float32)
        line6 = [(p.x, p.z) for p in road_lines(rs, course_entry_at(rs, e.bank, window_base=e.header_base))[6]]
        env.pop("VR_AUTOPILOT_LOOKAHEAD")                      # the pit tests' default aim
        if reverse:                                            # the wrong-way warning's and the clock's memory taps (memtrace.lua)
            from tests.test_pit_build import CLOCK_READS
            from tests.test_reverse_build import WARNING_READS
            env.update({"VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_READ": f"{WARNING_READS},{CLOCK_READS}",
                        "VR_TRACE_FROM": "0", "VR_TRACE_FINE": "1"})
        env["VR_PIT_LOG"] = str(wd / "pit.txt")
        rec, seconds = e, PIT_SECONDS
        if reverse:
            from vrtools.arcade.ps2entry import reverse_pit_of
            from vrtools.mame.pitpaths import reverse_pit_path
            rec, seconds = e.reverse.entry, REVERSE_SECONDS
            want = reverse_pit_of(conv)
            assert want is not None and rec.pit_quad == want.quad and rec.pit_box[3] == want.box[3] and \
                all(abs(a - b) <= 0.01 for a, b in zip(rec.pit_box[:3], want.box[:3])), (rec.pit_quad, rec.pit_box, want)
            path = reverse_pit_path(self.run("pit", "island").frames, line6)
            env.update({"VR_AUTOPILOT_AHEAD": str(REVERSE_AHEAD), "VR_FIELD_LOG": str(wd / "field.txt"), "VR_FIELD_FROM": "1600",
                        "VR_FIELD_TO": "999999", "VR_FIELD_EVERY": "2"})
        else:
            path = normal_pit_path(line6, conv.pit.line)
        env["VR_AUTOPILOT"] = str(write_centreline(wd / "path.csv", path))
        run_mame(LUA_DIR / "autoplay.lua", seconds, wd, self.set, env=env, timeout=3600)
        run = PitRun(ISLAND_ENTRY, "reverse" if reverse else "normal", wd, parse_pit_log(wd / "pit.txt"),
                     (rec.pit_quad, rec.pit_quad + 1), tuple(rec.pit_box))
        run.lane, run.normal_box, run.points = conv.pit.line, tuple(e.pit_box), len(line6)
        return run

    def stress_set(self) -> Path:
        """Gate f's set: pack 2 built with the lightning's stress tune (test_weather_lightning's STRESS interval, every other tune
        the default) through the pack's own build (`pack_sets.built(tunes=..., tag="stress")`)."""
        from dataclasses import replace
        from tests.pack_sets import built
        from tests.test_weather_lightning import STRESS
        from vrtools.arcade.weather.tune import Tunes
        t = Tunes()
        return built("ps2", self.romset_zip, self.factory, ps2_disc=DISC, tunes=replace(t, lightning=replace(t.lightning, interval_s=STRESS)),
                     tag="stress")

    def _best(self, wd: Path, env: dict):
        """Gate d's race: Beltway, normal, on a fresh battery RAM, the released ranking tests' finished race (race_end.lua: a
        one-lap race, the clock held; tests/test_reverse_ranking.py's JUMPS form, ranking_attract.lua beside it), BEST_SECONDS: to
        the name entry and the attract after it. A `Run` with `race` (`RankRun`), `attract` (`BootRun`) and `battery`."""
        from tests.test_frame_rate import Run
        from tests.test_reverse_ranking import BATTERY, TAP_AT, _parse_attract, _parse_rank
        from vrtools.arcade.course import DIRECTION_RAM
        from vrtools.mame.runner import LUA_DIR, run_mame
        env.update({"VR_EXTRA_LUA": f"{LUA_DIR / 'race_end.lua'};{LUA_DIR / 'ranking_attract.lua'}", "VR_END_LOG": str(wd / "end.txt"),
                    "VR_RANK_LOG": str(wd / "log.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}",
                    "VR_END_TABLE": f"{BATTERY[0]:x}-{BATTERY[1]:x}", "VR_END_TAP_AT": str(TAP_AT)})
        run_mame(LUA_DIR / "autoplay.lua", BEST_SECONDS, wd, self.set, env=env, timeout=3600)
        r = Run(wd)
        r.battery = (wd / "nvram" / "vr" / "nvram").read_bytes()
        r.race = _parse_rank(wd / "end.txt", ("normal",), r.battery)
        r.attract = _parse_attract(wd / "log.txt", None, r.battery)
        return r

    def _finish(self, wd: Path, env: dict):
        """Gate b's finished race: Island, normal, DRY, every lap of the game's own race on the autopilot with the clock held
        (frame_rate.lua's VR_HOLD_CLOCK: back to 60 s below 30 s; the finish stops it), the opponents logged, the modes logged
        (ranking_attract.lua beside autoplay), FINISH_SECONDS: past the finish to the name entry or the attract. A `Run` with
        `attract` (`BootRun`: its M lines are the modes)."""
        from tests.test_frame_rate import Run
        from tests.test_reverse_ranking import _parse_attract
        from vrtools.mame.runner import LUA_DIR, run_mame
        env.update({"VR_HOLD_CLOCK": "1", "VR_RACE_CARS_TO": str(10 ** 7), "VR_EXTRA_LUA": str(LUA_DIR / "ranking_attract.lua"),
                    "VR_RANK_LOG": str(wd / "log.txt")})
        run_mame(LUA_DIR / "autoplay.lua", FINISH_SECONDS, wd, self.set, env=env, timeout=5400)
        r = Run(wd)
        r.attract = _parse_attract(wd / "log.txt", None, (wd / "nvram" / "vr" / "nvram").read_bytes())
        return r

    def _storm(self, wd: Path, env: dict, course: str):
        """Gate f's run: the course, normal, RAIN, on the stress set, the clock held, the released stress run's logs
        (test_weather_lightning's `storm_env` on the stress build's own storm layout), STRESS_SECONDS."""
        from tests.pack_sets import layout
        from tests.test_frame_rate import Run
        from tests.test_weather_lightning import STRESS_SECONDS, storm_env
        from vrtools.mame.runner import LUA_DIR, parse_light_log, parse_storm_log, run_mame
        env.update({**storm_env(layout("ps2", tag="stress"), wd), "VR_HOLD_CLOCK": "1"})
        run_mame(LUA_DIR / "autoplay.lua", STRESS_SECONDS, wd, self.stress_set(), env=env, timeout=5400)
        r = Run(wd)
        r.storm = parse_storm_log(wd / "storm.txt")
        r.light, r.gaps = parse_light_log(wd / "light.txt")
        return r

    def _make(self, key):
        from tests.test_frame_rate import Run
        from vrtools.arcade.course import DIRECTION_RAM
        from vrtools.mame.runner import LUA_DIR, run_mame
        kind, course = key[:2]
        reverse = len(key) > 2 and key[2]
        if kind == "boot":                                   # gate d's restart: the attract on the race's battery RAM
            from tests.test_reverse_ranking import _attract
            return _attract(self.base, self.set, f"boot_{course}", BOOT_SECONDS, self.run("best", course).battery)
        wd = self.base / "_".join(str(k) for k in key)
        wd.mkdir(parents=True, exist_ok=True)
        set_dir = self.off_set() if kind == "off" else self.stress_set() if kind == "storm" else self.set
        env = self._env(wd, course, reverse, set_dir)
        if kind == "pit":
            return self._pit(wd, env, reverse)
        if kind == "best":
            return self._best(wd, env)
        if kind == "finish":
            return self._finish(wd, env)
        if kind == "storm":
            return self._storm(wd, env, course)
        if kind == "rain":
            env.update({"VR_RAIN": "1", "VR_RACE_CARS_TO": str(10 ** 7)})
            run_mame(LUA_DIR / "autoplay.lua", RACE_SECONDS, wd, set_dir, env=env, timeout=5400)
            return Run(wd)
        env.update({"VR_HOLD_CLOCK": "1", "VR_PASS_LOG": str(wd / "pass.txt"), "VR_PASS_FIELDS": "1",
                    "VR_DIR_LOG": str(wd / "dir.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"})
        if kind == "off":
            env["VR_INPUT_LOG"] = str(wd / "tape.txt")
        elif (course, reverse) == ("island", False):         # gate e: the weather-off race's inputs, frame for frame
            env.update({"VR_INPUT_REPLAY": str(self.run("off", "island").wd / "tape.txt"), "VR_INPUT_LOG": str(wd / "tape.txt")})
        run_mame(LUA_DIR / "autoplay.lua", DRY_SECONDS, wd, set_dir, env=env, timeout=3600)
        return Run(wd)

    def prefetch(self, keys):
        def make(k):
            try:
                r = self._make(k)
            except Exception as e:                     # noqa: BLE001 (raised again by `run`)
                with self._lock:
                    self.failed[k] = e
                return
            with self._lock:
                self.runs[k] = r
        keys = [k for k in dict.fromkeys(keys) if k not in self.runs]
        if any(k[0] == "storm" for k in keys):
            self.stress_set()                              # built once, here, before the runs' threads
        for wave in (False, True):                         # the runs that read another run's (AFTER) come second
            with ThreadPoolExecutor(JOBS) as ex:
                list(ex.map(make, [k for k in keys if (k in AFTER) == wave]))

    def run(self, *key):
        if key in self.failed:
            raise AssertionError(f"the run {key} failed: {self.failed[key]!r}") from self.failed[key]
        if key not in self.runs:
            self.runs[key] = self._make(key)
        return self.runs[key]


def gate_keys(items) -> list:
    need = {"test_pack_two_holds_the_rate_and_the_list_in_rain": lambda p: [("rain", p["course"], p["reverse"])],
            "test_pack_two_races_run_to_their_end": lambda p: [("rain", p["course"], p["reverse"])],
            "test_pack_two_holds_the_rate_and_the_list_dry": lambda p: [("dry", p["course"], p["reverse"])],
            "test_dry_is_pack_two_without_the_weather": lambda p: [("off", "island"), ("dry", "island", False)],
            "test_islands_pit_stop": lambda p: [("pit", "island")],
            "test_islands_reverse_pit_stop": lambda p: [("pit", "island"), ("pit", "island", True)],
            "test_a_best_time_on_beltway_shows_under_beltway_after_a_restart": lambda p: [("best", "beltway"), ("boot", "beltway")],
            "test_a_pack_two_race_finishes": lambda p: [("finish", "island")],
            "test_the_flash_rule_on_the_ps2_courses": lambda p: [("storm", p["course"])]}
    keys = []
    for i in items:
        name = getattr(i, "originalname", None) or getattr(i, "name", "")
        if name in need:
            keys += need[name](getattr(getattr(i, "callspec", None), "params", {}))
    return keys


_SESSION: dict = {}


@pytest.fixture
def gates(request, tmp_path_factory) -> GateSession:
    if "s" not in _SESSION:
        from tests.reference_sets import required_romset_zip
        s = GateSession(required_romset_zip(), tmp_path_factory.mktemp("pack2gates"), tmp_path_factory)
        s.prefetch(gate_keys(request.session.items))
        _SESSION["s"] = s
    return _SESSION["s"]


def _rate_and_list(r, name, rain: bool):
    """The released rate gates on run `r` (test_frame_rate.test_every_course_holds_the_arcade_rate's: the render rate 28-29 from
    the green, the overrun counter still, every pass under two vblanks, no stale display list over the stretch) and, in RAIN, no
    pass over RAIN_BUSY_MAX_MS (test_weather_rain.test_rain_holds_the_rate's cap)."""
    from tests.test_frame_rate import _stale_result
    from vrtools.mame.framerate import RAIN_BUSY_MAX_MS, arcade_rate_misses, worst_busy
    assert r.load and r.green and r.start, (name, r.load, r.green)
    stretch = r.stretch()
    misses = arcade_rate_misses(r.frames, r.rate, r.start, r.end, rate_from=r.green)
    stale, stale_text = _stale_result(r)
    w = worst_busy(r.frames, r.start, r.end)
    over = [(f.frame, f.busy_us) for f in stretch if f.busy_us > RAIN_BUSY_MAX_MS * 1000] if rain else []
    assert misses == [] and stale == [] and over == [], (name, misses[:5], "stale", stale_text, "over the rain's cap", over[:5],
                                                         "worst busy", w.busy_us, w.frame)
    assert len(stretch) > 2000, (name, len(stretch))
    return w


@pytest.mark.parametrize("course,reverse", CASES, ids=IDS)
def test_pack_two_holds_the_rate_and_the_list_in_rain(gates, record_property, course, reverse):
    """Gate a, RAIN: protects the arcade's rate (28.76 pictures a second, every picture) and the display list (no frozen picture)
    on the PS2 courses with the rain falling, and the rain's own time cap per pass (17.9 ms), from the green to the race's end."""
    w = _rate_and_list(gates.run("rain", course, reverse), f"{course} rain{' reverse' if reverse else ''}", rain=True)
    record_property("worst_busy_us", w.busy_us)


@pytest.mark.parametrize("course,reverse", CASES, ids=IDS)
def test_pack_two_holds_the_rate_and_the_list_dry(gates, record_property, course, reverse):
    """Gate a, DRY: the same rate and display-list gates on a DRY race (the clock held, the released test's DRY_SECONDS)."""
    w = _rate_and_list(gates.run("dry", course, reverse), f"{course} dry{' reverse' if reverse else ''}", rain=False)
    record_property("worst_busy_us", w.busy_us)


def opponents(path: Path) -> dict[int, list]:
    """{car: [(frame, road point, x, z)]} from race_log.lua's O lines."""
    from vrtools.mame.runner import parse_race_cars
    out: dict[int, list] = {}
    for c in parse_race_cars(path):
        out.setdefault(c.car, []).append((c.frame, c.road_point, c.x, c.z))
    return out


def still_stretches(samples, start: int, end: int) -> list[tuple[int, int]]:
    """(first, last) frames of each stretch of STILL_FRAMES or more in [start, end) over which the car stayed within STILL_UNITS of
    where the stretch began."""
    out, i = [], 0
    s = [t for t in samples if start <= t[0] < end]
    while i < len(s):
        j = i
        while j + 1 < len(s) and abs(s[j + 1][2] - s[i][2]) <= STILL_UNITS and abs(s[j + 1][3] - s[i][3]) <= STILL_UNITS:
            j += 1
        if s[j][0] - s[i][0] >= STILL_FRAMES:
            out.append((s[i][0], s[j][0]))
        i = j + 1
    return out


def backsteps(samples, n_points: int, start: int, end: int) -> list[tuple[int, int]]:
    """(frame, drop) where the car's unwrapped progress fell more than BACKSTEP_MAX road points (a put-back)."""
    from tests.test_race_build import BACKSTEP_MAX
    out, prog, prev = [], None, None
    for f, rp, _, _ in samples:
        if not start <= f < end:
            continue
        if prev is not None:
            d = (rp - prev + n_points // 2) % n_points - n_points // 2
            prog += d
            if d < -BACKSTEP_MAX:
                out.append((f, -d))
        else:
            prog = rp
        prev = rp
    return out


@pytest.mark.parametrize("course,reverse", CASES, ids=IDS)
def test_pack_two_races_run_to_their_end(gates, record_property, course, reverse):
    """Gate b: protects the race itself on a PS2 course. The RAIN race on the autopilot, the clock not held: it ends by the game's
    own end (`Run.end`: the clock at 0, the time over, or held still after the green, the finish); every checkpoint the car passes
    is the next one (the player's checkpoint count +0x57 steps by one, or back to 0 at a new lap) and brings its time extension
    (the clock rises within 4 frames); at least one is passed; all fifteen opponents run to the end: none stationary for 10 s
    (`still_stretches`), none put back (`backsteps`: no drop of its progress over BACKSTEP_MAX); the machine runs on after the end
    (frame log passes AFTER_END frames past it; run_mame raised on any MAME failure)."""
    name = f"{course}{' reverse' if reverse else ''}"
    r = gates.run("rain", course, reverse)
    assert r.green and r.end, (name, "the race did not end in", RACE_SECONDS, "s", r.green, r.end)
    ps = _race_runs(r, name, record_property)
    record_property("ended", "time over" if ps[-1].clock == 0 else "finish")


def _race_runs(r, name, record_property) -> list:
    """Gate b's measures on a race run `r` from its green to its end (`test_pack_two_races_run_to_their_end`'s docstring): the
    checkpoints in order with their time extensions (one at least), the fifteen opponents running to the end, none put back, the
    machine running AFTER_END frames past the end. Returns the player's race-log samples from the green to the end."""
    from vrtools.mame.runner import parse_race_log
    ps = [p for p in parse_race_log(r.wd / "race.txt")[0] if r.green <= p.frame <= r.end]
    clock = {p.frame: p.clock for p in ps}
    steps = [(a, b) for a, b in zip(ps, ps[1:]) if b.checkpoints != a.checkpoints]
    record_property("checkpoints", len(steps))
    assert steps, (name, "no checkpoint passed")
    bad = [(b.frame, a.checkpoints, b.checkpoints) for a, b in steps
           if not (b.checkpoints == a.checkpoints + 1 or (b.checkpoints == 0 and b.lap == a.lap + 1))]
    assert bad == [], (name, "a checkpoint out of order", bad[:5])
    no_ext = [b.frame for a, b in steps if not any(clock.get(b.frame + k, 0) > clock.get(b.frame + k - 1, 1 << 30) for k in range(-1, 5))]
    assert no_ext == [], (name, "a checkpoint without its time extension", no_ext[:5])
    cars = opponents(r.wd / "race.txt")
    assert sorted(cars) == list(range(1, 16)), (name, sorted(cars))
    n = max(max(t[1] for t in s) for s in cars.values()) + 1         # the lap's road points (the field covers the lap)
    still = {c: still_stretches(s, r.green, r.end) for c, s in cars.items()}
    back = {c: backsteps(s, n, r.green, r.end) for c, s in cars.items()}
    assert not any(still.values()), (name, "stationary opponents", {c: v for c, v in still.items() if v})
    assert not any(back.values()), (name, "opponents put back", {c: v for c, v in back.items() if v})
    assert r.frames[-1].frame >= r.end + AFTER_END, (name, "the machine stopped after the race", r.frames[-1].frame, r.end)
    return ps


def test_dry_is_pack_two_without_the_weather(gates):
    """Gate e: protects DRY as the game without the weather on a PS2 course. Island, normal: the autopilot's race on pack 2 built
    with the weather off records its inputs; pack 2 (the weather on, DRY answered) replays them frame for frame: from the race's
    load the game's state at the end of every pass (pass_state.lua with the cars' fields: test_weather_dry's `_from_load`) is the
    same, MIN_PASSES passes or more, and the race loads on the same frame."""
    from tests.test_weather_dry import MIN_PASSES, _from_load
    off, dry = gates.run("off", "island"), gates.run("dry", "island", False)
    ta, tb = (dry.wd / "tape.txt").read_text().splitlines(), (off.wd / "tape.txt").read_text().splitlines()
    assert len(ta) > 3000 and ta == tb, ("the replay did not feed the off race's inputs", len(ta), len(tb))
    (lo, po), (ld, pd) = _from_load(off.wd), _from_load(dry.wd)
    assert lo.frame == ld.frame and ld.armed == 0, (lo, ld)
    n = min(len(po), len(pd))
    assert n >= MIN_PASSES, n
    first = next((i for i in range(n) if po[i] != pd[i]), None)
    assert first is None, (first, po[first][:120], pd[first][:120])


def test_islands_pit_stop(gates):
    """Gate c: protects Island's pit stop (normal direction) in pack 2, as on a converted Saturn course with pits. The released pit
    test's form (tests/test_pit_build.py::test_a_normal_pit_stop, its helpers imported): the drive on the normal pit path, the clock
    not held; two stops granted at the green; the stop as `_assert_a_stop` (the trigger on the entry pair, the car parked at the
    entry's box until the release, PIT_WORK_FRAMES of work, the clock standing then PIT_EXTEND more, one stop spent). Rejoining (the
    released reverse test's checks): the car leaves the lane (`_left_lane`) with no trigger again on the way and one stop left, and
    the lap is counted after the trigger (Island's line lies in the lane: the lap counts during the stop)."""
    from tests.test_pit_build import STOPS_GRANTED, _assert_a_stop, _left_lane, _report
    from vrtools.mame.runner import PIT_HANDLER
    run = gates.run("pit", "island")
    f = run.frames
    assert f[run.green].stops == STOPS_GRANTED, f[run.green]
    s = run.stop()
    rep = _report(run, s) if s else None
    print("ISLAND STOP", "pair", run.pair, "box", run.box, "green", f[run.green].frame, rep)
    _assert_a_stop(run, s, STOPS_GRANTED)
    out = _left_lane(run, run.lane, s.release)
    assert out is not None, ("the car never left the lane after the release", f[s.release], f[-1])
    assert all(g.handler != PIT_HANDLER and g.stops == STOPS_GRANTED - 1 for g in f[s.release:out + 1]), f[out]
    assert rep["next lap"] is not None, ("no lap counted after the stop", f[s.trigger].lap, f[-1])
    print("ISLAND REJOINED", "left the lane at frame", f[out].frame, "next lap at frame", rep["next lap"])


def test_islands_reverse_pit_stop(gates):
    """Gate c in reverse (task 2, the review's I11): protects Island's reverse pit stop in pack 2, built by the Saturn path's rule
    (`reverse.reverse_pit_in`). The released reverse pit test's form (tests/test_pit_build.py::test_a_reverse_pit_stop, its
    helpers imported): the reverse race on the reverse pit path, the clock not held; the variant's pair and box as the build's rule
    gives them, the box heading the normal one turned half a turn; two stops granted at the green; the stop as `_assert_a_stop`
    (the trigger on the variant's pair, parked at its box until the release, PIT_WORK_FRAMES of work, the clock standing then
    PIT_EXTEND more, one stop spent); out of the lane (`_left_lane`) with no trigger again on the way and one stop left; the next
    lap counted, one more than at the trigger; two or more clock rises after the release at the reverse gates in order from the
    first ahead of the car; no read of the wrong-way warning from the green on (memtrace.lua's taps, the clock's reads their
    control); the fifteen opponents all advance during the stop."""
    from tests.test_pit_build import STOPS_GRANTED, _assert_a_stop, _left_lane, _progress, _report
    from vrtools.mame.runner import PIT_HANDLER, parse_field
    run = gates.run("pit", "island", True)
    f = run.frames
    assert run.box[3] == (run.normal_box[3] + 0x8000) & 0xFFFF, (run.box, run.normal_box)
    assert f[run.green].stops == STOPS_GRANTED, f[run.green]
    s = run.stop()
    rep = _report(run, s) if s else None
    print("ISLAND REVERSE STOP", "pair", run.pair, "box", run.box, "green", f[run.green].frame, rep)
    _assert_a_stop(run, s, STOPS_GRANTED)
    t, r = s.trigger, s.release
    out = _left_lane(run, run.lane, r)
    assert out is not None, ("the car never left the lane after the release", f[r], f[-1])
    assert all(g.handler != PIT_HANDLER and g.stops == STOPS_GRANTED - 1 for g in f[r:out + 1]), f[out]
    assert rep["next lap"] is not None, ("no lap counted after the stop", f[t].lap, f[-1])
    nl = next(g for g in f[t:] if g.lap > f[t].lap)
    assert nl.lap == f[t].lap + 1, (f[t].lap, nl)
    n = run.points
    # the gates after the release, as the released reverse test (the reverse race's checkpoints from the built set's record)
    from tests.test_pit_build import LOGIC_STEP, _fires, _gate_of, _warning_reads
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.race import decode_race_blob
    from vrtools.arcade.romset import RomSet
    rs = RomSet.from_zip(gates.set / "vr.zip", verify=False)
    gates_ = decode_race_blob(rs, decode_directory(rs)[ISLAND_ENTRY].reverse.entry.race).checkpoints
    players = run.race()
    rp = next((p.road_point for p in players if p.frame == f[r].frame), None)
    assert rp is not None, f"no race-log frame {f[r].frame} (the release)"
    nxt = run.stop(r)                                                    # the next stop's rises are its own
    until = f[nxt.trigger].frame if nxt else f[-1].frame + 1
    fires = [(fr, p, _gate_of(p, gates_, n)) for fr, p in _fires(players) if f[r].frame + 2 * LOGIC_STEP < fr < until]
    k = min(range(len(gates_)), key=lambda j: (gates_[j] - rp - 1) % n)  # the first gate ahead of the car at the release
    print("ISLAND REVERSE GATES release point", rp, "gates", gates_, "fires after the release (frame, point, gate)", fires,
          "first expected", gates_[k])
    assert len(fires) >= 2 and [g for _, _, g in fires] == [(k + i) % len(gates_) for i in range(len(fires))], (fires, gates_[k])
    # the wrong-way warning: no reads from the green on, the clock's reads the taps' control
    reads, control = _warning_reads(run)
    print("ISLAND REVERSE WRONG WAY reads", len(reads), reads[:8], "clock reads (the taps' control): frames", len(control),
          (control[0], control[-1]) if control else None)
    assert control and control[0] <= f[run.green].frame + 60 and control[-1] >= f[-1].frame - 60, (len(control), control[:2], control[-2:])
    assert not reads, reads[:8]
    cars: dict[int, list] = {}
    for x in parse_field(run.wd / "field.txt"):
        if f[t].frame <= x.frame + 1 <= f[r].frame and x.car:
            cars.setdefault(x.car, []).append(x)
    advance = {car: _progress(v, n) for car, v in sorted(cars.items())}
    print("ISLAND REVERSE REJOINED", "left the lane at frame", f[out].frame, "next lap at frame", rep["next lap"],
          "OPPONENTS during the stop", advance)
    assert len(advance) == 15 and all(a > 0 for a in advance.values()), advance


def _modes(boot) -> list:
    """ranking_attract.lua's M lines as test_dirscreen_build's `Line`s (no record byte or handler: 0), for `_after_finish`."""
    from tests.test_dirscreen_build import Line
    return [Line(f, m, s, flag, 0, 0) for f, m, s, flag in boot.lines]


def test_a_pack_two_race_finishes(gates, record_property):
    """Gate b, the finish: protects a PS2 race run to the game's own finish. Island, normal, DRY, the clock held so that the
    autopilot (too slow to beat the time) gets every lap: the race ends by the finish (the clock stopped, not at 0); the laps are
    counted one by one (the player's lap +0x1b5 steps by one, the race's laps of them, ISLAND_TOP.laps); gate b's measures over the
    race (`_race_runs`: the checkpoints, the opponents, the machine running on); after the finish the game's own sequence to the
    attract (`_after_finish`: the finish, the results, the ranking page, the name entry when a record, the attract load 0x02:
    test_dirscreen_build's RECORD or NO_RECORD), which is no crash."""
    from tests.test_dirscreen_build import NO_RECORD, RECORD
    from tests.test_reverse_ranking import _after_finish
    from vrtools.arcade.pack import ISLAND_TOP
    r = gates.run("finish", "island")
    assert r.green and r.end, ("island finish: the race did not end in", FINISH_SECONDS, "s", r.green, r.end)
    ps = _race_runs(r, "island finish", record_property)
    laps = [(b.frame, a.lap, b.lap) for a, b in zip(ps, ps[1:]) if b.lap != a.lap]
    record_property("laps", laps)
    print("ISLAND FINISH", "green", r.green, "end", r.end, "clock at the end", ps[-1].clock, "laps", laps)
    assert ps[-1].clock > 0, ("island finish: the race ended by the time over, not the finish", ps[-1])
    assert all(b == a + 1 for _, a, b in laps) and len(laps) == ISLAND_TOP.laps, ("the laps not counted one by one", laps)
    modes = _after_finish([m for m in _modes(r.attract) if m.frame >= r.green])
    print("ISLAND FINISH modes after the race", [hex(m) for m in modes])
    assert modes in (RECORD, NO_RECORD), [hex(m) for m in modes]


def test_a_best_time_on_beltway_shows_under_beltway_after_a_restart(gates):
    """Gate d: protects the best times of a PS2 course (Beltway, the wheel's last entry). A finished one-lap race on a fresh battery
    RAM (race_end.lua, the released ranking tests' finish) records: the game's sequence after the finish has the name entry
    (RECORD), its time (the T line) stands first in Beltway's table (NEW_TABLES[2]: rank 1, the time at +4 and +0x10, the blank name)
    and the race wrote no other course's table (normal or reverse). After a restart on that battery RAM (a new MAME boot,
    ranking_attract.lua): the table is kept byte for byte; the time is in Beltway's table and in no other table; the attract shows
    Beltway's page (id 5, Beltway's table, the title BELTWAY: `_assert_page`), no page of a hidden entry (the pack's `Hidden` slots
    6-9 and their reverse ids: they would show BELTWAY over another table; the ROM's directory does not mark them, so they are the
    plan's), every page drawn as its id's (`_assert_page`)."""
    from tests.test_dirscreen_build import RECORD
    from tests.test_reverse_ranking import ENTRY, _after_finish, _assert_page, _bytes, _race, _spans
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.pack import PS2, Hidden
    from vrtools.arcade.ranking import NEW_TABLES, ORIG_REVERSE_TABLES, ORIG_TABLES, REVERSE_TABLES, SHORT_ENTRIES, TABLE_BYTES
    from vrtools.arcade.romset import RomSet
    beltway = ISLAND_ENTRY + 2
    rs = RomSet.from_zip(gates.set / "vr.zip", verify=False)
    d = decode_directory(rs)
    hidden = {3 + k for k, p in enumerate(PS2.slots) if isinstance(p, Hidden)}
    assert d[beltway].name == "BELTWAY" and hidden == set(range(beltway + 1, 10)), ([e.name for e in d], hidden)
    best, boot = gates.run("best", "beltway"), gates.run("boot", "beltway")
    race = best.race
    assert _after_finish(_race(race, 0)) == RECORD, [hex(m) for m in _after_finish(_race(race, 0))]
    assert len(race.times) == 1, race.times
    t = race.times[0][1]
    table = NEW_TABLES[beltway - 3]
    first = ENTRY.unpack_from(best.battery, table - 0x400000)
    print("BELTWAY BEST", "time", t, f"({t / 32:.2f} s)", "first entry", first)
    assert first[0] == 1 and first[1] == first[4] == t and first[5] == b"   \0", (first, t)
    tables = {b: TABLE_BYTES for b in ORIG_TABLES + NEW_TABLES} | {b: 24 * SHORT_ENTRIES for b in REVERSE_TABLES + ORIG_REVERSE_TABLES}
    wrote = {b for f, _, a, _ in _bytes(race.writes) if f >= race.loads[0] for b, n in tables.items() if b <= a < b + n}
    assert wrote == {table}, ("the race wrote these tables", sorted(map(hex, wrote)))
    assert boot.before == best.battery and boot.battery[table - 0x400000:table - 0x400000 + TABLE_BYTES] == \
        best.battery[table - 0x400000:table - 0x400000 + TABLE_BYTES]
    holding = sorted(hex(b) for b, n in tables.items() for k in range(n // 24)
                     if ENTRY.unpack_from(boot.battery, b - 0x400000 + 24 * k)[1] == t)
    assert holding == [hex(table)], ("the time is in these tables", holding)
    pages = _spans(boot)
    print("RESTART PAGES", [(p["start"], p["di"], p["id"]) for p in pages])
    shown_hidden = sorted({p["id"] for p in pages} & (hidden | {h + 7 for h in hidden}))
    assert not shown_hidden, ("pages of hidden entries", shown_hidden)
    assert any(p["id"] == beltway for p in pages), ("no Beltway page in", BOOT_SECONDS, "s after the restart")
    for p in pages:
        _assert_page(p, rs, d)


@pytest.mark.parametrize("course", ["island", "mountain", "beltway"])
def test_the_flash_rule_on_the_ps2_courses(gates, course):
    """Gate f: protects the flash rule on the PS2 courses: never more than three full-screen flash onsets within a second. The
    released stress form (test_weather_lightning.test_the_flash_rule_under_stress's gates, `flash_rule`: the onsets read from
    palette RAM and the colour RAM at each pass's end, at least 20 strikes and their onsets, which asserts that flashes fired, the
    rate gates under the storm, the sound's cells following the strikes) on pack 2 built with the stress tune (a strike every
    0.4-1.2 s: `GateSession.stress_set`), RAIN, the course normal, the clock held, STRESS_SECONDS."""
    from tests.test_weather_lightning import flash_rule
    from vrtools.arcade.romset import RomSet
    from tests.test_pack_rate import COURSES
    r = gates.run("storm", course)
    on = flash_rule(r, RomSet.from_zip(gates.stress_set() / "vr.zip", verify=False), COURSES[course][0], f"pack 2 stress {course}",
                    lambda on: print("PACK 2 STRESS", course, "strikes", r.light[-1].s.get("NSTRIKE"), "onsets seen", len(on)))
    assert on, (course, "no flash onset")
