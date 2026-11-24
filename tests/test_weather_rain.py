"""Weather stage 2, the rain (spec 5.3 and 6; weather/rain.py on the carrier of weather/carrier.py): its objects, colours, tables
and skies equal the prototype's (spike 48 as joined in spike 70, out/p75storm; the values pinned here were computed from the
prototype's own functions and its palette dump), and in MAME a RAIN race on every course in both directions holds the gates: no
stale display list, every pass at most RAIN_BUSY_MAX_MS of V60 time, the overrun counter still, the render rate 28-29, no list of
the game's skipped, the records within the budget with only the rain trimmed; the start-up spread over passes that draw nothing;
the HUD unchanged and the start lights and READY board keeping their colours.

The MAME runs of this module and of tests/test_weather_carrier.py are made together (`storm_runs`), three MAME processes at a time,
at the first test that needs one; a selection of tests makes only the runs those tests read."""
import hashlib
import os
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.arcade.budget import FRAME_BUDGET
from vrtools.mame.framerate import RAIN_BUSY_MAX_MS, arcade_rate_misses, worst_busy
from vrtools.arcade.weather import carrier
from vrtools.mame.runner import LUA_DIR, parse_stale_log, parse_storm_log, run_mame

COURSES = [(e, False) for e in range(10)] + [(e, True) for e in range(10)]
RAIN_SECONDS = 150
LIST_BYTES, LIST_MARGIN = 0x10000, 4096   # W9: a display list buffer (0x600000 / 0x610000) and the room kept under its end (60
                                          # object entries of 68 bytes)
NAMES = ("big_forest", "bay_bridge", "acropolis", "alpine", "amazon_falls", "diablo_canyon", "metropolis", "pacific_coast",
         "surfers_oval", "surfers_road")
HUD_ENTRY = 6                           # Metropolis: its start gantry and READY board in view at the pit-less grid start
HUD_SNAPS = (240, 700)                  # frames after the race start: the countdown (the board, the red lamps lit), the race
HUD_BOXES = ((1, 3, 4, 12), (1, 3, 29, 33), (1, 5, 48, 60), (3, 6, 1, 13), (3, 6, 27, 33), (42, 47, 2, 12), (44, 46, 49, 59))
# (rows r0..r1-1, columns c0..c1-1 of 8-pixel cells): POSITION, TIME, LAP TIME, the position and time figures, SPEED, the course word
JOBS = 3
POST_MOVE_MAX_US = carrier.UNIT_MAX_US + carrier.TAIL_US     # on a pass of the storm's in which the vblank count moved: the time
                                        # from the move to the pass's end, the unit in flight and the tail; a reported figure since the
                                        # join (the session lead's split bound: each part held on its own, `post_move_over`)
# The game unchanged by the storm (test_rain_does_not_change_the_game): a DRY race's autopilot inputs replayed in RAIN on the same
# set. (entry, road line or None for the rate tests' line, seconds): Big Forest's heaviest place, and a converted course with a tunnel.
SAME_GAME = {"big_forest_line4": (0, 4, 300), "metropolis": (6, None, 150)}
# Storm modules left out of the RAIN build of that test: the ones meant to change the game. Stage 5's wet handling changes it by
# design (test_the_handling_changes_the_replayed_game: the same replay on the session's own set parts from the DRY race). The tests
# that compare a RAIN race with the same DRY race picture for picture (the HUD's, `hud`; after the rain's modes, `after`) race both
# on that set too: they test the storm's drawing and its release, the handling's own are tests/test_weather_handling.py's; so does
# the TEST switch in the results (`svc`, `window`), whose fixed frames are the results of race_end.lua's lap without the handling
# (the wet lap is longer; the TEST menu from a RAIN race, `svc`, `rain`, runs on the session's own set, the handling in it).
GAME_CHANGING_MODULES: tuple = ("handling",)


def _id(e, r):
    return f"{NAMES[e]}{'_reverse' if r else ''}"


# The RAIN race matrix's named subset (the session lead's rider R-S): VR_RAIN_SUBSET unset runs all twenty races (what stage 7 and
# the join run); "heavy6" the six with the highest busiest pass of the final per-course table (task-2 report, FINAL STATE: run
# final2 at 7def283) and Metropolis normal added as a seventh (both its tunnels); any other value a comma-separated list of race ids
# (`_id`), exactly those (a later stage adds the courses its feature needs). The others are skipped with a reason naming the
# variable; an unknown id is an error at collection.
HEAVY6 = ("pacific_coast_reverse",      # busiest 17.63 ms (frame 2191)
          "big_forest",                 # 17.60 (1943)
          "bay_bridge",                 # 17.57 (6337)
          "bay_bridge_reverse",         # 17.57 (2371)
          "acropolis_reverse",          # 17.48 (1951)
          "acropolis",                  # 17.47 (1983)
          "metropolis")                 # 16.62 (1927): not among the six; added for its two tunnels (stage 3's cover)
RACE_IDS = tuple(_id(e, r) for e, r in COURSES)


def rain_subset(value: str | None) -> frozenset | None:
    """The race ids VR_RAIN_SUBSET `value` selects: None (unset or empty: all twenty), HEAVY6 for "heavy6", else the comma-separated
    ids; ValueError naming an unknown id."""
    if not value or not value.strip():
        return None
    ids = HEAVY6 if value.strip() == "heavy6" else tuple(v.strip() for v in value.split(",") if v.strip())
    unknown = [i for i in ids if i not in RACE_IDS]
    if unknown or not ids:
        raise ValueError(f"VR_RAIN_SUBSET={value!r}: unknown race ids {unknown} (known: heavy6, {', '.join(RACE_IDS)})")
    return frozenset(ids)


def race_params(value: str | None) -> list:
    """COURSES as pytest params with their ids; under a subset the races outside it carry a skip mark naming VR_RAIN_SUBSET."""
    chosen = rain_subset(value)
    return [pytest.param(e, r, id=_id(e, r), marks=() if chosen is None or _id(e, r) in chosen else
                         pytest.mark.skip(reason=f"not in VR_RAIN_SUBSET={value} (unset: all twenty races)")) for e, r in COURSES]


RACES = race_params(os.environ.get("VR_RAIN_SUBSET"))      # raises at collection on an unknown id


# ---- static: the race matrix's subset ---------------------------------------------------------------------------------------------
def test_the_rain_subset_selection():
    """R-S: VR_RAIN_SUBSET unset (or empty) selects all twenty races; "heavy6" the six busiest of the final table and Metropolis
    normal; a comma-separated list exactly those ids; an unknown id is refused naming it. Under a subset the other races are skipped
    with a reason naming the variable, never dropped: twenty params always."""
    assert rain_subset(None) is None and rain_subset("") is None and len(RACE_IDS) == 20
    assert rain_subset("heavy6") == frozenset(HEAVY6) and len(HEAVY6) == 7 and "metropolis" in HEAVY6
    assert rain_subset("alpine, bay_bridge") == {"alpine", "bay_bridge"}
    for bad in ("heavy7", "alpine,alpne", ","):
        with pytest.raises(ValueError, match="VR_RAIN_SUBSET"):
            rain_subset(bad)
    for value, run in ((None, set(RACE_IDS)), ("heavy6", set(HEAVY6)), ("alpine,bay_bridge", {"alpine", "bay_bridge"})):
        params = race_params(value)
        assert [p.id for p in params] == list(RACE_IDS)
        assert {p.id for p in params if not p.marks} == run
        assert all(m.kwargs["reason"].startswith(f"not in VR_RAIN_SUBSET={value}") for p in params for m in p.marks)


# ---- static: the prototype's values ---------------------------------------------------------------------------------------------
def test_rain_tune_defaults_and_bounds():
    """RainTune: S5.3's values (300 drops in 60 clusters of 5, splashes within 35 units, 6-frame splashes); others refused."""
    from vrtools.arcade.weather.tune import RainTune
    t = RainTune()
    assert (t.drops, t.clusters, t.splash_range, t.splash_frames) == (300, 60, 35.0, 6)
    for bad in ({"drops": 299}, {"clusters": 61, "drops": 305}, {"clusters": 0, "drops": 0}, {"splash_range": 3.0},
                {"splash_range": 45.5}, {"splash_frames": 5}):
        with pytest.raises(ValueError):
            RainTune(**bad)
    assert RainTune(drops=200, clusters=40).clusters == 40


def test_the_drop_objects():
    """8 shapes of 5 box drops, each in 5 variants (all its drops, then without the lowest, the two lowest, ...: 34, 27, 20, 13, 6
    records), padded to one size; the drop table (per shape and drop its x and bottom); the bytes are the prototype's (spike 48's
    narrower drops, seed 45)."""
    from vrtools.arcade.weather import rain
    objs, size, records, faces, table = rain.drop_objects()
    assert len(objs) == 40 and size == 1424 and records == 34 and all(len(o) == size for o in objs)
    assert faces[:7] == ["L", "H", "F", "R", "J", "T", "J"] and faces.count("T") == 5
    assert len(table) == 8 * 5 * 8
    assert hashlib.sha256(b"".join(objs)).hexdigest()[:16] == "e5bb302fb676e1d7"
    assert hashlib.sha256(table).hexdigest()[:16] == "3f78bdb14d994890"
    widths = [w for shape in rain.shapes() for _, _, w, _, _ in shape]
    assert len(widths) == 40 and 0.035 <= min(widths) and max(widths) <= 0.05          # Pascal: "narrower drops"


def test_the_splash_objects():
    """12 splash objects (two droplet layouts x 6 stages), each a ring of 8 records and 3 droplets of 2 (14 records), one size; the
    prototype's bytes."""
    from vrtools.arcade.weather import rain
    sp = rain.splash_objects(6)
    assert len(sp) == 12 and {len(o) for o in sp} == {24 + 14 * 40 + 40}
    assert hashlib.sha256(b"".join(sp)).hexdigest()[:16] == "f09536f35e8a09d7"


def test_the_colour_picks_are_the_prototypes(romset_zip, saturn_cue):
    """The colour words, picked from the program ROM's polygon palette (the boot's copy source; the two entries the game changes left
    out) with the prototype's targets under the grade, are the prototype's (picked from its palette dump): the drops' left,
    highlight, front, right and top faces 255, 124, 361, 222, 24; the splashes' ring 126, droplets 124, the ring's last stages 99."""
    from tests.test_tgp_build import _seven
    from vrtools.arcade.weather import rain
    out, _ = _seven(romset_zip, saturn_cue)
    pal = rain.polygon_palette(out)
    assert len(pal) == 897 and pal[40] == pal[41] == 0
    assert {f: rain.pick(pal, t) for f, t in rain.GLASS.items()} == {"L": 255, "H": 124, "F": 361, "R": 222, "T": 24}
    assert {c: rain.pick(pal, t) for c, t in rain.SPLASH_COLOURS.items()} == {"ring": 126, "drop": 124, "ring_late": 99}
    _, _, _, faces, _ = rain.drop_objects()
    drops, splashes = rain.colour_words(out, faces, 6)
    assert len(drops) == 34 and len(splashes) == 12 and all(w & 0xC00 == 0xC00 for w in drops + splashes)
    assert splashes[-4] & 0x3FF == splashes[-2] & 0x3FF == 99 and splashes[0] & 0x3FF == 126


def test_the_grey_sky():
    """Each course's backdrop greyed: Metropolis by its own blend (spike 46), every other course desaturated first (Big Forest's
    formula); every 16th colour and bit 15 kept; the values the prototype computes."""
    from vrtools.arcade.weather import rain
    cols = [0x1234, 0xFC00, 0x03E0, 0x001F, 0x5294, 0x8000 | (6 << 5) | 30 << 10, 12345 & 0x7FFF]
    assert [hex(w) for w in rain.grey_sky(cols, False)] == ["0x1234", "0xc9ac", "0x4e90", "0x41f1", "0x5693", "0xc9ed", "0x49f0"]
    assert [hex(w) for w in rain.grey_sky(cols, True)] == ["0x1234", "0xe5ac", "0x3eec", "0x3db6", "0x5693", "0xe5ec", "0x4db4"]
    many = list(range(0, 0x10000, 97))[:64]
    g = rain.grey_sky(many, False)
    assert all(g[k] == many[k] for k in range(0, 64, 16)) and all((a ^ b) & 0x8000 == 0 for a, b in zip(g, many))


def test_the_overcast_and_boot_tables():
    """The overcast table (spike 46: keep 66 % of the colour toward a light grey, 3-10 % darker; the c = 0 entries from 56 black) and
    the boot's table ((c (l + 1) + 2) >> 2), 96 rows of 64 halfwords each, are the prototype's."""
    from vrtools.arcade.weather import rain
    T0, TB = rain.overcast_table(), rain.boot_table()
    assert T0.shape == TB.shape == (3, 32, 64)
    assert (T0[:, 0, 56:] == 0).all() and int(TB[1, 3, 10]) == (3 * 11 + 2) >> 2 and int(TB[1, 31, 63]) == 0xFFFF   # 255 and over: 0xffff
    assert hashlib.sha256(rain.table_bytes(T0)).hexdigest()[:16] == "5253dcc213658b06"
    assert hashlib.sha256(rain.table_bytes(TB)).hexdigest()[:16] == "d41b52695c7f0352"
    assert len(rain.table_bytes(T0)) == 96 * 128


def test_the_rain_code_disassembles(romset_zip, saturn_cue):
    """The rain's code as laid out in the image disassembles as instructions throughout (unidasm reads no byte as data), from its
    start to its end; its three entry points are the module's."""
    from tests.test_tgp_build import _seven
    from vrtools.arcade.disasm import listing_bytes
    from vrtools.arcade.weather import carrier
    out, _ = _seven(romset_zip, saturn_cue)
    lay, pieces, image = carrier.lay_out(carrier.default_modules(out))
    at, code = pieces["rain"]
    lines = listing_bytes(code, at)
    assert sum(len(l.bytes) for l in lines) == len(code)
    assert not [l for l in lines if l.text.startswith("$") or "illegal" in l.text.lower()][:3]
    assert {lay.label("rain", k) for k in ("start", "frame", "release")} <= {l.addr for l in lines}


def test_the_load_psw_logger_knows_the_stub():
    """storm_log.lua's I lines (Task 7): the PSW at each load's entry, logged on the stub's own write of the load counter; the stub's
    bounds it names are the layout's block, and the parser reads the line."""
    from vrtools.arcade.weather import layout
    from vrtools.mame.runner import parse_storm_log
    b = layout.block("storm stub")
    lua = (LUA_DIR / "storm_log.lua").read_text()
    assert f"pc >= {b.start:#x} and pc < {b.start + b.size:#x}" in lua and carrier.NLOAD == 0x520008 and "0x520008, 0x52000b" in lua
    import tempfile
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as d:
        f = Path(d) / "storm.txt"
        f.write_text("I 1607 10040000\nEND\n")
        assert parse_storm_log(f).load_psw == ((1607, 0x10040000),)


def test_the_cap_covers_the_guard_bound():
    """The cap's arithmetic (the join's round 2, J2, the session lead's ruling): the latest vblank count move measured (17.486 ms into
    the pass) plus the longest unit in flight (carrier.UNIT_MAX_US) plus the longest tail (carrier.TAIL_US, re-measured: 149 us, forced
    in the first module with the sound's trigger sending two words) stays under RAIN_BUSY_MAX_MS, kept at 17.9 this round (the
    derivation gives 17.846); the sound's trigger, an allowed unguarded unit, inside the tail's measure and its own bound."""
    from vrtools.mame.framerate import DEADLINE_MS, RAIN_BUSY_MAX_MS
    assert carrier.TAIL_US == 160 and carrier.UNIT_MAX_US == 200 and RAIN_BUSY_MAX_MS == 17.9
    bound = 17.486 + (carrier.UNIT_MAX_US + carrier.TAIL_US) / 1000
    assert round(bound, 3) == 17.846 and bound <= RAIN_BUSY_MAX_MS < DEADLINE_MS - 0.9
    assert carrier.SOUND_TRIGGER_US < carrier.TAIL_US


def test_the_late_splash_path_is_constant_time(romset_zip, saturn_cue):
    """The join's round 2, J2 (the session lead's ruling): after a trip in the splash loop every remaining splash slot is dead from
    that pass on (the prototype's anti-blink rule), but the rain no longer visits them one by one: the late splash path (`slate`)
    has no loop (no branch in it to a label inside it) and clears the remaining slots with one string fill (movcfu.h), and the late
    splash trim count stays exact through a maintained count of live slots (state word SPLIVE: +1 when a spawn takes a dead slot,
    -1 when a splash ends, set to this pass's live count so far, LV, at a trip; TRIM_LSP += SPLIVE - LV)."""
    from tests.test_tgp_build import _seven
    from vrtools.arcade.v60asm import asm
    from vrtools.arcade.weather import carrier, rain as R
    out, _ = _seven(romset_zip, saturn_cue)
    mods = carrier.default_modules(out)
    lay = carrier.lay_out(mods)[0]
    items = next(m for m in mods if m.name == "rain").code(lay).items
    k0 = items.index(("label", "slate"))
    k1 = next(k for k in range(k0, len(items)) if isinstance(items[k], tuple) and items[k][0] == "br" and items[k][1] == "listout")
    region = items[k0:k1 + 1]
    inside = {it[1] for it in region if isinstance(it, tuple) and it[0] == "label"}
    loops = [it for it in region if isinstance(it, tuple) and it[0] != "label" and it[1] in inside]
    assert loops == [], loops
    code = b"".join(it for it in region if isinstance(it, bytes))
    assert asm("movcfu.h [reg],imm,[reg],reg", "r6", 0, "r6", "r3") in code
    splive, lv, trim = R.cell(lay, "SPLIVE"), R.cell(lay, "LV"), R.cell(lay, "TRIM_LSP")
    allcode = b"".join(it for it in items if isinstance(it, bytes))
    assert asm("add.w imm,abs", 1, splive) in allcode and asm("sub.w imm,abs", 1, splive) in allcode
    assert asm("add.w reg,abs", "r0", trim) in code and asm("mov.w abs,abs", lv, splive) in code
    assert list(R.STATE_NAMES[-2:]) == ["SPLIVE", "LV"] and R.STATE_NAMES.index("REC_OUT") == 26     # storm_log.lua's indices kept


# ---- the runs -----------------------------------------------------------------------------------------------------------------
class StormSession:
    """The session's weather set and every storm run of this module and test_weather_carrier.py, made at the first use. Builds on
    test_frame_rate's RateSession (the set's zip, the autopilot lines, the session battery RAM)."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        from tests.test_frame_rate import RateSession
        from tests.test_tgp_build import _build
        from tests.test_weather_dry import _seven_dry
        from vrtools.arcade.weather import carrier
        self.rate = RateSession(romset_zip, saturn_cue, base)
        self.base, self.build = base, self.rate.build
        spin, keep = int(os.environ.get("VR_STORM_FAULT_SPIN") or 0), os.environ.get("VR_STORM_FAULT_KEEP_GRADE") == "1"
        if spin or keep:                               # a planted fault (the RED evidence of fix round 1, F3 and F5): every run on it
            self.build = self._fault_build(romset_zip, saturn_cue, base, spin, keep)
        dry, _ = _seven_dry(romset_zip, saturn_cue)
        (base / "dry").mkdir(parents=True, exist_ok=True)
        self.dry = _build(base / "dry", romset_zip, dry)
        self.lay = carrier.lay_out(carrier.default_modules(self.rate.out))[0]
        self.light = "lightning" in self.lay.codes         # stage 4: its log on every storm run (test_weather_lightning.py)
        self.rain_cells = self.lay.cell("rain", "state")
        self.runs, self.failed = {}, {}
        self._lock, self._probe_lock = threading.Lock(), threading.Lock()

    @staticmethod
    def _fault_build(romset_zip, saturn_cue, base, spin, keep) -> Path:
        """The session's weather set with a planted fault in the rain (rain.module's `fault_spin`, `fault_keep_grade`): test only."""
        from tests.test_tgp_build import _build
        from tests.test_weather_carrier import _stage1
        from vrtools.arcade.weather import rain
        from vrtools.arcade.weather.tune import RainTune
        s1 = _stage1(romset_zip, saturn_cue)
        (base / "fault").mkdir(parents=True, exist_ok=True)
        return _build(base / "fault", romset_zip, carrier.build(s1, [rain.module(s1, RainTune(), spin, keep)])[0])

    def probe_build(self) -> Path:
        """The weather set with test_weather_carrier.py's dummy hook-site module after the rain (F1)."""
        with self._probe_lock:                         # its RAIN and DRY runs are made at once: one build
            return self._probe_build()

    def _probe_build(self) -> Path:
        if not hasattr(self, "_probe"):
            from tests.test_tgp_build import _build
            from tests.test_weather_carrier import _stage1, probe_build
            out, rep = probe_build(_stage1(self.rate.romset_zip, self.rate.saturn_cue))
            (self.base / "probe").mkdir(parents=True, exist_ok=True)
            self._probe, self.probe_hits = _build(self.base / "probe", self.rate.romset_zip, out), rep["layout"].cell("probe", "hits")
        return self._probe

    def storm_env(self, wd: Path, trace=False, dumps=(), full=False, lay=None) -> dict:
        """The storm loggers' environment for a run on the session's set, or (`lay`, the join) on a set laid out as `lay`."""
        lay = lay or self.lay
        env = {"VR_STORM_LOG": str(wd / "storm.txt"), "VR_STORM_RAIN": f"{lay.cell('rain', 'state'):x}", "VR_STORM_FRAMES": "1"}
        if trace:
            env["VR_STORM_TRACE"] = "1"
        if dumps:
            env["VR_STORM_DUMPS"] = ",".join(map(str, dumps))
        if full:
            env["VR_STORM_FULL"] = "1"
        if "lightning" in lay.codes:
            from vrtools.mame.runner import light_env
            env.update(light_env(lay, wd))
        if "cover" in lay.codes:                       # the join: the cover's state with every S line (C lines: what a pass was)
            from vrtools.arcade.weather import cover
            env.update(cover.log_env(lay))
        if "sound" in lay.codes:                       # the join: the sound's thunders sent (its cell nthunder) on every W line
            env["VR_STORM_WATCH"] = f"{lay.cell('sound', 'nthunder'):x}"
        return env

    def _make(self, key):
        from tests.test_frame_rate import Run
        from vrtools.arcade.course import DIRECTION_RAM
        import shutil
        kind = key[0]
        wd = self.base / "storm" / "_".join(str(k) for k in key)
        wd.mkdir(parents=True, exist_ok=True)
        logs = {"VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"), "VR_STALE_LOG": str(wd / "stale_list.txt")}
        if kind in ("rain", "line4"):                  # the rate tests' autopilot races, RAIN, 150 s, the clock held
            entry, reverse = (key[1], key[2]) if kind == "rain" else (0, False)
            line = [(p.x, p.z) for p in self.rate.road[0][4]] if kind == "line4" else None
            env = self.rate._env(wd, entry, reverse, line)
            env.update({**logs, **self.storm_env(wd), "VR_HOLD_CLOCK": "1", "VR_RAIN": "1"})
            if kind == "line4":
                shutil.copytree(self.rate.nvram(), wd / "nvram")
            run_mame(LUA_DIR / "autoplay.lua", RAIN_SECONDS, wd, self.build, env=env, timeout=3600)
            return Run(wd)
        if kind == "same":                             # SAME_GAME: the DRY race records its inputs; RAIN replays them
            entry, line_no, seconds = SAME_GAME[key[1]]
            line = [(p.x, p.z) for p in self.rate.road[entry][line_no]] if line_no is not None else None
            env = self.rate._env(wd, entry, False, line)
            env.update({**logs, "VR_HOLD_CLOCK": "1", "VR_PASS_LOG": str(wd / "pass.txt"), "VR_PASS_FIELDS": "1",
                        "VR_INPUT_LOG": str(wd / "tape.txt")})
            if key[2] in ("rain", "handling"):         # "handling": the same replay on the session's own set (stage 5)
                env.update({**self.storm_env(wd), "VR_RAIN": "1",
                            "VR_INPUT_REPLAY": str(self.run("same", key[1], "dry").wd / "tape.txt")})
            shutil.copytree(self.rate.nvram(), wd / "nvram")
            run_mame(LUA_DIR / "autoplay.lua", seconds, wd, self.same_build() if key[2] == "rain" else self.build, env=env,
                     timeout=3600)
            return Run(wd)
        if kind == "hud":                              # Metropolis RAIN / DRY, snapshots and whole palette and tile dumps
            rain = key[1] == "rain"
            env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[HUD_ENTRY]), "VR_SNAPS": "",
                   "VR_SNAPS_AFTER_START": ",".join(map(str, HUD_SNAPS)), **logs,
                   **self.storm_env(wd, dumps=[1600 + s for s in HUD_SNAPS], full=True)}
            if rain:
                env["VR_RAIN"] = "1"
            run_mame(LUA_DIR / "autoplay.lua", 40, wd, self.same_build(), env=env, timeout=1800)   # both: the same game (stage 5)
            return Run(wd)
        if kind in ("dry_trace", "dry_main", "dry_same"):   # a DRY race on the set (traced), on the switch-off set and (stage 5) on
                                                       # the set without the game-changing modules: the same race
            env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[0]), **logs, "VR_RACE_LOG": str(wd / "race.txt"),
                   "VR_RACE_LOG_FROM": "0"}
            if kind == "dry_trace":
                env.update(self.storm_env(wd, trace=True))
            build = {"dry_trace": self.build, "dry_main": self.dry}.get(kind) or self.same_build()
            run_mame(LUA_DIR / "autoplay.lua", 70, wd, build, env=env, timeout=1800)
            return Run(wd)
        if kind == "attract_trace":                    # the attract, no input, traced
            env = {"VR_SNAP_FROM": "999999", **logs, **self.storm_env(wd, trace=True)}
            run_mame(LUA_DIR / "attract_snaps.lua", 200, wd, self.build, env=env, timeout=1800)
            return Run(wd)
        if kind == "end":                              # race_end.lua: RAIN Big Forest to its end, the attract, a second game
            second = {"dry": f"{WHEEL_FOR_ENTRY[6]}:0", "rain": f"{WHEEL_FOR_ENTRY[3]}:0:1"}[key[1]]
            env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[0]), "VR_RAIN": "1", **logs,
                   "VR_EXTRA_LUA": str(LUA_DIR / "race_end.lua"), "VR_END_LOG": str(wd / "end.txt"),
                   "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}", "VR_END_NEXT": second, **self.storm_env(wd, trace=True, dumps=END_DUMPS)}
            run_mame(LUA_DIR / "autoplay.lua", 260, wd, self.build, env=env, timeout=3600)
            return Run(wd, finish=False)
        if kind in ("svc", "reset", "chain"):           # B4: the TEST menu, a soft reset, three games
            env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[0]), **logs, **self.storm_env(wd, trace=True),
                   "VR_TEST_LOG": str(wd / "test.txt")}
            extra = [str(LUA_DIR / "test_inputs.lua")]
            if key[1:] != ("main",):
                env["VR_RAIN"] = "1"
            if kind == "chain" or key[1:] == ("window",):
                extra.append(str(LUA_DIR / "race_end.lua"))
                env.update({"VR_END_LOG": str(wd / "end.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"})
            if kind == "svc":
                env["VR_TEST_INPUT"] = SVC_INPUT if key[1] != "window" else f"{WINDOW_TEST}:Service Mode:10;{WINDOW_EXIT}:VR4 (Green):8"
            if kind == "reset":
                env["VR_SOFT_RESET"] = str(RESET_RACE if key[1] == "race" else RESET_WINDOW)
            if kind == "chain":
                env.update({"VR_END_NEXT": CHAIN, "VR_STORM_DUMP_AFTER_LOAD": str(CHAIN_DUMP)})
            env["VR_EXTRA_LUA"] = ";".join(extra)
            seconds = {"svc": 200, "reset": 170, "chain": 420}[kind] if key[1:] != ("race",) else 70
            build = self.dry if key[1:] == ("main",) else self.same_build() if key == ("svc", "window") else self.build
            run_mame(LUA_DIR / "autoplay.lua", seconds, wd, build, env=env, timeout=3600)   # ("svc", "window"): its fixed frames
            return Run(wd, finish=False)                                 # are race_end.lua's lap's results without the wet handling
        if kind == "after":                            # F3: RAIN / DRY Big Forest ended by time over, a coin and START in its results
            env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[0]), **logs, "VR_SNAPS": ",".join(map(str, AFTER_SNAPS)),
                   "VR_EXTRA_LUA": f"{LUA_DIR / 'clock_out.lua'};{LUA_DIR / 'test_inputs.lua'}", "VR_CLOCK_OUT": str(TOVER_AFTER),
                   "VR_TEST_LOG": str(wd / "test.txt"), "VR_TEST_INPUT": AFTER_INPUT, **self.storm_env(wd, dumps=AFTER_DUMPS, full=True)}
            if key[1] == "rain":
                env["VR_RAIN"] = "1"
            run_mame(LUA_DIR / "autoplay.lua", AFTER_SECONDS, wd, self.same_build(), env=env, timeout=1800)   # both: the same game
            return Run(wd, finish=False)
        if kind == "reload":                           # the join: a forced state for the reload branch (Big Forest RAIN, the
            sky = self.lay.data_at("rain", "sky") + 8      # countdown): ("reload", "key") pokes the load key to another entry's and
            poke = [f"{RELOAD_POKE}:{sky:x}:{RELOAD_JUNK:x}"]   # junk over the grey sky's first colours in the storm's DATA (the
            if key[1] == "key":                        # stand-in for the old course's data); ("reload", "control") the junk alone
                poke.insert(0, f"{RELOAD_POKE}:{carrier.LOADKEY:x}:{carrier.KEYMAGIC | RELOAD_OTHER:x}")
            env = self.rate._env(wd, 0, False)
            env.update({**logs, **self.storm_env(wd, dumps=RELOAD_DUMPS), "VR_HOLD_CLOCK": "1", "VR_RAIN": "1",
                        "VR_STORM_WATCH": f"{sky:x}", "VR_STORM_POKE": ";".join(poke), "VR_POKE_LOG": str(wd / "poke.txt"),
                        "VR_EXTRA_LUA": str(LUA_DIR / "storm_poke.lua")})
            run_mame(LUA_DIR / "autoplay.lua", RELOAD_SECONDS, wd, self.build, env=env, timeout=1800)
            return Run(wd, finish=False)
        if kind == "probe":                            # F1: the dummy hook-site module's set, Big Forest RAIN / DRY, traced
            build = self.probe_build()
            env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[0]), **logs, **self.storm_env(wd, trace=True),
                   "VR_STORM_WATCH": f"{self.probe_hits:x}"}
            if key[1] == "rain":
                env["VR_RAIN"] = "1"
            run_mame(LUA_DIR / "autoplay.lua", 70, wd, build, env=env, timeout=1800)
            return Run(wd, finish=False)
        if kind == "tover":                            # RAIN Big Forest, the race ended by time over at the race start + 200
            env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[0]), "VR_RAIN": "1", **logs,
                   "VR_EXTRA_LUA": str(LUA_DIR / "clock_out.lua"), "VR_CLOCK_OUT": str(TOVER_AFTER),
                   **self.storm_env(wd, trace=True, dumps=(1600 + TOVER_AFTER - 10,))}
            run_mame(LUA_DIR / "autoplay.lua", 90, wd, self.build, env=env, timeout=1800)
            return Run(wd, finish=False)
        raise ValueError(key)

    def same_build(self) -> Path:
        """The set test_rain_does_not_change_the_game's RAIN runs race on: the session's, or (GAME_CHANGING_MODULES not empty) the
        same weather set with those storm modules left out of the carrier."""
        if not GAME_CHANGING_MODULES:
            return self.build
        with self._probe_lock:                         # the replays are made at once (stage 5: one build, not two racing)
            return self._same_build()

    def _same_build(self) -> Path:
        if not hasattr(self, "_same"):
            from dataclasses import replace
            from tests.test_tgp_build import _build
            from tests.test_weather_dry import _seven_dry
            from vrtools.arcade.weather import carrier, screen
            from vrtools.arcade.weather.tune import ScreenTune
            s1 = replace(_seven_dry(self.rate.romset_zip, self.rate.saturn_cue)[0])
            screen.install(s1, ScreenTune())
            mods = [m for m in carrier.default_modules(s1) if m.name not in GAME_CHANGING_MODULES]
            (self.base / "same").mkdir(parents=True, exist_ok=True)
            self._same = _build(self.base / "same", self.rate.romset_zip, carrier.install(s1, modules=mods))
        return self._same

    def prefetch(self, keys):
        keys = [k for k in dict.fromkeys(keys) if k not in self.runs]
        if any(k[0] in ("line4", "same") for k in keys):
            self.rate.nvram()
        replays = [k for k in keys if k[0] == "same" and k[2] in ("rain", "handling")]
        keys = [k for k in keys if k not in replays]

        def make(k):
            try:
                r = self._make(k)
            except Exception as e:                     # noqa: BLE001 (raised again by `run`)
                with self._lock:
                    self.failed[k] = e
                return
            with self._lock:
                self.runs[k] = r
        with ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(make, keys))
        with ThreadPoolExecutor(JOBS) as ex:                   # each replays its DRY run's tape: made after them
            list(ex.map(make, replays))

    def run(self, *key):
        if key in self.failed:
            raise AssertionError(f"the run {key} failed: {self.failed[key]!r}") from self.failed[key]
        if key not in self.runs:
            self.runs[key] = self._make(key)
        r = self.runs[key]
        if not hasattr(r, "storm") and (r.wd / "storm.txt").exists():
            r.storm = parse_storm_log(r.wd / "storm.txt")
        return r


# B4 (the fallback round): the TEST menu from a RAIN race (its MEMORY TEST run to its end, escaped, then EXIT: the game reboots),
# the TEST switch in the results after a RAIN race, a soft reset, three games in a row. Frames (MAME's, as autoplay.lua's).
SVC_INPUT = ("2500:Service Mode:10;" + ";".join(f"{2600 + 40 * k}:VR1 (Red):8" for k in range(8))     # the cursor EXIT -> MEMORY TEST
             + ";2950:VR4 (Green):8;6000:VR4 (Green):8;6100:VR1 (Red):8;6140:VR1 (Red):8;6200:VR4 (Green):8")  # escape, EXIT
SVC_EXIT = 6200
WINDOW_TEST, WINDOW_EXIT, RESET_RACE, RESET_WINDOW = 7500, 7700, 2500, 7500   # the results of race_end.lua's lap: 7340-7794
CHAIN = f"{WHEEL_FOR_ENTRY[6]}:0;{WHEEL_FOR_ENTRY[3]}:0:1"                    # after RAIN Big Forest: DRY Metropolis, RAIN Alpine
CHAIN_DUMP = 400                                                             # frames after each storm load (the grade made)
END_DUMPS = (2000, 9300)                # mid first race (the grade made); the second game's race (it loads on 8858)
TOVER_AFTER = 200
# F3: the same race RAIN and DRY ended by time over, a coin and START in the results (the game over 1938-2387, the results' last mode
# 0x1d 2388, the attract's opening from 2390 (released at its scenery call, 2393), the next game's selections from 2400 to the
# direction screen): every frame around the attract's opening, then every 8th through the selections.
AFTER_INPUT = "2100:Coin 1:10;2150:1 Player Start:10"
AFTER_SNAPS = tuple(range(2380, 2420)) + tuple(range(2420, 4300, 8))
AFTER_DUMPS = (2386, 2390, 2395, 2600, 3000, 3600, 4200)
AFTER_SECONDS = 80
# The join: the carrier's reload branch on a forced state (test_the_reload_branch_on_a_forced_state): Big Forest RAIN loads on frame
# 1600; in its countdown (the race starts after 1840: HUD_SNAPS) the load key is poked to entry RELOAD_OTHER's at the end of frame
# RELOAD_POKE, with junk over the grey sky's first two colours in the storm's DATA; dumps before and well after (the restart's start
# passes and the grade's rows done).
RELOAD_POKE, RELOAD_OTHER, RELOAD_JUNK = 1700, 5, 0x7C1F7C1F
RELOAD_DUMPS = (1690, 1830)
RELOAD_SECONDS = 40


def storm_keys(items) -> list:
    """The runs the collected tests `items` (of this module and test_weather_carrier.py) read."""
    need = {"test_rain_holds_the_rate": lambda p: [("rain", p["entry"], p["reverse"])],
            "test_the_start_up_is_spread": lambda p: [("rain", p["entry"], p["reverse"])],
            "test_every_strike_thunders_on_its_pass": lambda p: [("rain", p["entry"], p["reverse"])],
            "test_only_rain_is_trimmed": lambda p: [("line4",)],
            "test_rain_does_not_change_the_game": lambda p: [("same", p["name"], "dry"), ("same", p["name"], "rain")],
            "test_the_handling_changes_the_replayed_game": lambda p: [("same", "metropolis", "dry"), ("same", "metropolis", "handling")],
            "test_the_hud_lights_and_ready_board_keep_their_colours": lambda p: [("hud", "rain"), ("hud", "dry")],
            "test_dry_runs_no_storm_code": lambda p: [("dry_trace",), ("dry_main",), ("dry_same",), ("attract_trace",)],
            "test_a_rain_race_ends_clean": lambda p: [("end", "dry")],
            "test_time_over_mid_rain_ends_clean": lambda p: [("tover",)],
            "test_a_second_game_starts_clean": lambda p: [("end", "dry"), ("end", "rain")],
            "test_the_test_menu_from_a_rain_race": lambda p: [("svc", "rain"), ("svc", "main")],
            "test_the_test_switch_after_a_rain_race": lambda p: [("svc", "window")],
            "test_a_soft_reset_during_and_after_a_rain_race": lambda p: [("reset", "race"), ("reset", "window")],
            "test_three_games_rain_dry_rain": lambda p: [("chain",)],
            "test_nothing_of_the_storm_shows_after_its_modes": lambda p: [("after", "rain"), ("after", "dry")],
            "test_a_hook_site_runs_in_rain_only": lambda p: [("probe", "rain"), ("probe", "dry")],
            "test_the_reload_branch_on_a_forced_state": lambda p: [("reload", "key"), ("reload", "control")]}
    keys = []
    for i in items:
        if i.get_closest_marker("skip"):                   # deselected (VR_RAIN_SUBSET): no run made for it
            continue
        name = getattr(i, "originalname", None) or getattr(i, "name", "")
        p = getattr(getattr(i, "callspec", None), "params", {})
        if name in need:
            keys += need[name](p)
    return keys


_SESSIONS: dict = {}


@pytest.fixture
def storm_runs(request, romset_zip, saturn_cue, tmp_path_factory) -> StormSession:
    key = str(romset_zip)
    if key not in _SESSIONS:
        s = StormSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("storm"))
        s.prefetch(storm_keys(request.session.items))
        _SESSIONS[key] = s
    return _SESSIONS[key]


def post_move(r) -> dict:
    """{frame: microseconds from the vblank count's move to the pass's end} for every pass at whose end the storm was live (state not
    IDLE: the load, the starts, the shows) and in which the count moved before the pass's work ended (storm_log.lua's A lines): the
    passes a cluster, splash or grade guard stopped and the others: what a long unit of storm work stretches, whatever the pass's
    total. A pass on which the rain counted a late pass without an A line maps to None: a failure (the logger missed the move).
    (The release pass ends IDLE: it runs on the attract's opening scene load, the game's own long pass;
    test_nothing_of_the_storm_shows_after_its_modes holds it to the DRY pass plus carrier.RELEASE_US_MAX.)"""
    out, prev = {}, None
    for p in r.storm.passes:
        if p.state != 0:
            if p.frame in r.storm.after:
                out[p.frame] = r.storm.after[p.frame]
            elif prev is not None and p.late > prev.late:
                out[p.frame] = None
        prev = p
    return out


def post_move_over(r) -> list:
    """The passes of `post_move` that break the split bound (the join, the session lead's ruling of 19 Nov 2026: a sum would hide a
    long unit behind a short tail): from the vblank count's move to the guard's trip (the unit in flight: storm_log.lua's B line)
    over carrier.UNIT_MAX_US, or from the trip to the pass's end (the tail) over carrier.TAIL_US; a pass whose count moved after the
    storm's last guard test (an A line, no B line: no test read it moved) holds its whole time from the move to the end to
    carrier.TAIL_US; a pass on which the rain counted a late pass without an A line (None) fails. As (frame, A us, (unit us, tail us)
    or None), the longest first."""
    pm = post_move(r)
    trip = getattr(r.storm, "trip", {}) or {}
    bad = []
    for f, a in pm.items():
        b = trip.get(f)
        if a is None or (b is None and a > carrier.TAIL_US) or (b is not None and (b[0] > carrier.UNIT_MAX_US or b[1] > carrier.TAIL_US)):
            bad.append((f, a, b))
    return sorted(bad, key=lambda x: -(x[1] or 1e9))


def post_move_parts(r) -> tuple[float, float]:
    """The longest unit in flight and the longest tail (B lines) over the passes of `post_move` (0 when none)."""
    pm, trip = post_move(r), getattr(r.storm, "trip", {}) or {}
    bs = [trip[f] for f in pm if f in trip]
    return max((b[0] for b in bs), default=0.0), max((b[1] for b in bs), default=0.0)


def rain_over_budget(shows) -> list:
    """The visible rain passes on which the rain took the frame's record count over FRAME_BUDGET (it may only add up to it; a frame
    the game's own lists left over it gets nothing)."""
    return [p for p in shows if p.rec_out > max(p.rec_in, FRAME_BUDGET) or (p.rec_out > FRAME_BUDGET and p.rec_out != p.rec_in)]


def show_passes(r):
    return [p for p in r.storm.passes if p.state == 2 and p.active]


def first_show(r):
    """The rain's first visible pass: the first pass that ended with clusters drawn."""
    return next(p for p in r.storm.passes if p.state == 2 and p.drawn > 0)


def _summary(s: StormSession, name: str, r, busiest, first, stale_text, start_up):
    stretch = r.stretch()
    shows = show_passes(r)
    last = r.storm.passes[-1]
    with open(s.base / "rain_summary.txt", "a") as out:
        out.write(f"{name}: passes {len(stretch)} ({r.start}-{r.end or stretch[-1].frame}), busiest {busiest.busy_us / 1000:.2f} ms at "
                  f"{busiest.frame}, first rain frame {first.busy_us / 1000:.2f} ms at {first.frame}, start-up "
                  f"{' '.join(f'{f}:{b / 1000:.2f}' for f, b in start_up)}, stale {stale_text}, records peak "
                  f"{max(f.records for f in stretch)}, need max {max(f.need for f in stretch)}, skipped "
                  f"{sum(f.skipped for f in stretch)}, clusters drawn median {statistics.median(p.drawn for p in shows)}, splashes "
                  f"median {statistics.median(p.splashes for p in shows)}, late passes {last.late}, budget trims {last.trim_cl}/"
                  f"{last.trim_sp}, late trims {last.trim_lcl}/{last.trim_lsp}, passes the count moved in {len(post_move(r))} (longest "
                  f"after the move {max((a or 0 for a in post_move(r).values()), default=0):.0f} us; the longest unit in flight "
                  f"{post_move_parts(r)[0]:.0f} us, tail {post_move_parts(r)[1]:.0f} us)\n")


@pytest.mark.parametrize("entry,reverse", RACES)
def test_rain_holds_the_rate(storm_runs, record_property, entry, reverse):
    """A RAIN race (the rate tests' autopilot line, RAIN_SECONDS, the clock held) from the pass after the load to the race's end:
    no stale display list; every pass at most RAIN_BUSY_MAX_MS of V60 time; the overrun counter still; the render rate 28-29 from
    the green; no list of the game's skipped and the records within FRAME_BUDGET; it rained (60 clusters drawn on the median
    visible pass) through the race; the rain never took a frame's records over the budget (`rain_over_budget`); on every pass of the
    storm's in which the vblank count moved, the unit in flight at most UNIT_MAX_US and the tail at most TAIL_US (`post_move_over`,
    the join's split bound), and an A line on every pass the rain counted late (`post_move`)."""
    from tests.test_frame_rate import _stale_result
    r = storm_runs.run("rain", entry, reverse)
    assert r.load and r.green and r.start, (_id(entry, reverse), r.load, r.green)
    stretch = r.stretch()
    misses = arcade_rate_misses(r.frames, r.rate, r.start, r.end, rate_from=r.green)
    stale, stale_text = _stale_result(r)
    busiest = worst_busy(r.frames, r.start, r.end)
    first = next(f for f in r.frames if f.frame == first_show(r).frame)
    start_up = [(f.frame, f.busy_us) for f in r.frames if r.start - 1 <= f.frame <= first.frame]
    _summary(storm_runs, _id(entry, reverse), r, busiest, first, stale_text, start_up)
    record_property("busiest_us", busiest.busy_us)
    assert post_move_over(r) == [], (_id(entry, reverse), "long after the count's move", post_move_over(r)[:3])
    over = [(f.frame, f.busy_us) for f in stretch if f.busy_us > RAIN_BUSY_MAX_MS * 1000]
    assert misses == [] and stale == [] and over == [], (_id(entry, reverse), misses[:5], stale_text, over[:5])
    shows = [p for p in show_passes(r) if r.start <= p.frame < (r.end or 1 << 30)]
    assert sum(f.skipped for f in stretch) == 0 and rain_over_budget(shows) == []
    assert len(shows) > 2500 and statistics.median(p.drawn for p in shows) == 60, (len(shows),)
    assert all(p.switch == 1 for p in shows) and r.storm.passes[-1].loads == 1
    assert all(p.sbr == 0xFFF000 for p in r.storm.passes)                 # the interrupt table never moved
    # Task 7 (the re-review): the load masks interrupts and enables them again unconditionally (carrier.IRQ_ON), right only because
    # the PSW's interrupt bit (0x40000) is set at the scenery call: asserted at every load's entry (storm_log.lua's I lines)
    assert len(r.storm.load_psw) == r.storm.passes[-1].loads == 1 and all(psw & 0x40000 for _, psw in r.storm.load_psw), \
        (_id(entry, reverse), [(f, hex(v)) for f, v in r.storm.load_psw])
    # the final review's W4: no unit of ANY module longer than UNIT_MAX_US between two guard tests (lightning_log.lua's G lines,
    # gap_us: whichever module's code the unit began in), not only when the vblank happens to land in it
    from vrtools.mame.runner import parse_light_log
    assert (r.wd / "light.txt").exists(), (_id(entry, reverse), "no lightning log: the normal set always has the lightning")
    _, gaps = parse_light_log(r.wd / "light.txt")
    long = sorted(((f, g.gap_us, hex(g.pc)) for f, g in gaps.items() if g.gap_us > carrier.UNIT_MAX_US), key=lambda x: -x[1])
    assert gaps and long == [], (_id(entry, reverse), "a unit over UNIT_MAX_US", long[:5])
    # W9: the display list's high-water mark (storm_log.lua's L lines) under its 64 KB buffer's end by LIST_MARGIN
    hw = {f: b for f, b in r.storm.list_hw.items() if r.start <= f < (r.end or 1 << 30)}
    assert hw and max(hw.values()) <= LIST_BYTES - LIST_MARGIN, (_id(entry, reverse), max(hw.values(), default=None))
    with open(storm_runs.base / "rain_summary.txt", "a") as out:
        out.write(f"W4/W9 {_id(entry, reverse)}: longest unit between guard tests "
                  f"{max((g.gap_us for g in gaps.values()), default=0) if (r.wd / 'light.txt').exists() else 0:.1f} us, display list "
                  f"high-water {max(hw.values())} bytes of {LIST_BYTES}\n")


@pytest.mark.parametrize("entry,reverse", RACES)
def test_every_strike_thunders_on_its_pass(storm_runs, entry, reverse):
    """The join's round 2, J1 (the session lead's ruling: the sound's trigger is exempt from the guard): on the twenty-race matrix
    (the normal set, the real lightning), every strike's thunder word is queued on the pass the lightning's `strike_seq` changes
    (lightning_log.lua's L lines) and never on a later one: the sound's `nthunder` (storm_log's W lines) moves on exactly those
    passes."""
    from vrtools.mame.runner import parse_light_log
    r = storm_runs.run("rain", entry, reverse)
    light, _ = parse_light_log(r.wd / "light.txt")
    seq = [p.frame for p0, p in zip(light, light[1:]) if p.seq != p0.seq]
    w = sorted(r.storm.watch.items())
    thunder = [f for (f0, v0), (f, v) in zip(w, w[1:]) if v != v0]
    assert seq and thunder == seq, (_id(entry, reverse), seq, thunder)


@pytest.mark.parametrize("entry,reverse", RACES)
def test_the_start_up_is_spread(storm_runs, entry, reverse):
    """The storm's start (the stage plan's D5, the fallback round's quotas): its first scenery call loads (the copy) and draws
    nothing; the next passes place the clusters, at most rain.START_QUOTA a pass (the vblank count the backstop), nothing drawn,
    until all 60 are placed (three start passes, a fourth when the backstop cut one short); then the rain shows: its first visible
    pass draws every cluster, writes the sky and starts the grade. SBR the boot's at every pass (nothing of the storm moves the
    interrupt table); each of these passes at most RAIN_BUSY_MAX_MS."""
    from vrtools.arcade.weather import rain as rainmod
    r = storm_runs.run("rain", entry, reverse)
    passes = r.storm.passes
    assert all(p.sbr == 0xFFF000 for p in passes)
    f0 = next(p for p in passes if p.state != 0)                        # the storm's first scenery call (none before the race)
    assert f0.state == 1 and f0.loads == 1 and f0.drawn == 0 and f0.primed == 0, f0
    first = first_show(r)
    between = [p for p in passes if f0.frame <= p.frame < first.frame]      # the load, the start passes (the last ends in SHOW)
    steps = [b.primed - a.primed for a, b in zip(between, between[1:])]
    assert 4 <= len(between) <= 5 and all(p.drawn == 0 and p.splashes == 0 for p in between), between
    assert all(0 < k <= rainmod.START_QUOTA for k in steps), steps
    assert all(p.state == 1 for p in between[:-1]) and between[-1].state == 2 and between[-1].primed == 60, between
    assert first.drawn == 60 and first.active == 1, first
    busy = {f.frame: f.busy_us for f in r.frames}
    assert all(busy[p.frame] <= RAIN_BUSY_MAX_MS * 1000 for p in between + [first]), [(p.frame, busy[p.frame]) for p in between]


def test_only_rain_is_trimmed(storm_runs):
    """Big Forest on road line 4 in RAIN (its heaviest stretch, 9 704 records of the game's there on the session battery RAM): the
    records budget trims the rain (clusters and splashes left out, counted) and never a list of the game's (none skipped; the
    game's need is its own, under the budget); the rain never takes the count over the budget, and on a frame whose own lists end
    past it (the game's walker tests the budget before each list, and its last can run over) the rain draws nothing; the passes at
    most RAIN_BUSY_MAX_MS."""
    r = storm_runs.run("line4")
    stretch = r.stretch()
    last = r.storm.passes[-1]
    shows = [p for p in show_passes(r) if r.start <= p.frame < (r.end or 1 << 30)]
    assert max(f.need for f in stretch) > 9000, max(f.need for f in stretch)
    assert sum(f.skipped for f in stretch) == 0 and max(f.need for f in stretch) <= FRAME_BUDGET
    assert rain_over_budget(shows) == []
    full = [p for p in shows if p.rec_in > FRAME_BUDGET]                     # the game's own last list past the budget: no rain
    assert all(p.rec_out == p.rec_in and p.drawn == p.splashes == 0 for p in full), full[:3]
    assert last.trim_cl + last.trim_sp > 0, last
    assert max(f.busy_us for f in stretch) <= RAIN_BUSY_MAX_MS * 1000
    assert last.late > 0 and post_move_over(r) == [], (last.late, post_move_over(r)[:3])     # the guards stopped passes here
    with open(storm_runs.base / "rain_summary.txt", "a") as out:
        out.write(f"big_forest_line4: need max {max(f.need for f in stretch)}, records peak {max(f.records for f in stretch)} "
                  f"(the game's own lists past the budget on {len(full)} passes), "
                  f"budget trims {last.trim_cl}/{last.trim_sp}, late trims {last.trim_lcl}/{last.trim_lsp}, busiest "
                  f"{max(f.busy_us for f in stretch) / 1000:.2f} ms\n")


def test_the_hud_lights_and_ready_board_keep_their_colours(storm_runs):
    """Metropolis RAIN against DRY at the same frames (the countdown with the board and its red lamps, and the race): the HUD is
    unchanged: the whole palette RAM equal but for the backdrop's colours (the grey sky) and the tile maps equal but for the HUD word
    RAIN (layer 0's rows 46-47), and the HUD's text pixels (yellow, white) of the DRY picture equal in the RAIN picture; the READY
    board and the lamps, 3D objects under the grade, keep their colours as the prototype (spike 44: "the board's blue and the lamps'
    red keep their saturation"): the board's band stays blue, the lit lamps red."""
    import numpy as np
    from PIL import Image
    from vrtools.arcade.weather import rain as rainmod
    wet, dry = storm_runs.run("hud", "rain"), storm_runs.run("hud", "dry")
    n = rainmod.course_sky(storm_runs.rate.out, HUD_ENTRY)[2]
    for f in wet.storm.dumps:
        q, qd = wet.storm.dumps[f]["Q"], dry.storm.dumps[f]["Q"]
        sky = range((rainmod.SKY_DST - 0x900000) // 2, (rainmod.SKY_DST - 0x900000) // 2 + n)
        diff = [k for k in range(len(q)) if q[k] != qd[k]]
        assert diff and set(diff) <= set(sky), (f, [hex(0x900000 + 2 * k) for k in diff if k not in sky][:8])
        mw, md = wet.storm.dumps[f]["M"], dry.storm.dumps[f]["M"]
        mdiff = [k for k in range(len(mw)) if mw[k] != md[k]]
        assert all(k < 64 * 64 and k // 64 in (46, 47) for k in mdiff), [(k // 64, k % 64) for k in mdiff][:8]
    sw, sd = sorted((wet.wd / "snap").rglob("*.png")), sorted((dry.wd / "snap").rglob("*.png"))
    assert len(sw) == len(sd) == len(HUD_SNAPS)
    for k, (a, b) in enumerate(zip(sw, sd)):
        w, d = (np.asarray(Image.open(p).convert("RGB")).astype(int) for p in (a, b))
        cells = np.zeros(d.shape[:2], bool)                                                           # the HUD's boxes
        for r0, r1, c0, c1 in HUD_BOXES:
            cells[8 * r0:8 * r1, 8 * c0:8 * c1] = True
        text = (((d[..., 0] > 200) & (d[..., 1] > 150) & (d[..., 2] < 90)) | (d.min(-1) > 235)) & cells   # its yellow and white
        assert text.sum() > 1500 and (w[text] == d[text]).all(), (HUD_SNAPS[k], int(text.sum()), int((w[text] != d[text]).any(-1).sum()))
        if k == 0:                                                                                    # the countdown: the board
            band = (slice(40, 58), slice(175, 315))
            bw, bd = w[band].reshape(-1, 3).mean(0), d[band].reshape(-1, 3).mean(0)
            assert bd[2] > 1.8 * max(bd[:2]) and bw[2] > 1.8 * max(bw[:2]), (bd, bw)
            lamps = (slice(75, 135), slice(160, 330))
            red = (d[lamps][..., 0] > 150) & (d[lamps][..., 1] < 90)                               # the lit lamps in DRY
            lw = w[lamps][red].mean(0)                                                                # the same pixels in RAIN
            assert red.sum() > 200 and lw[0] > 150 and lw[0] > 3 * max(lw[1:]), (int(red.sum()), lw)


def test_the_handling_changes_the_replayed_game(storm_runs):
    """Stage 5: the switch of test_rain_does_not_change_the_game is real. The DRY race's inputs (Metropolis, SAME_GAME) replayed in
    RAIN on the session's own set, the wet handling in it: the same inputs fed, the game the DRY race's through the countdown (the
    handling acts only in the race mode), then it parts from it from the green on (the take-off's wheelspin: the first race pass,
    the gas floored)."""
    from vrtools.mame.framerate import parse_pass_log
    dry, wet = storm_runs.run("same", "metropolis", "dry"), storm_runs.run("same", "metropolis", "handling")
    ta, tb = (dry.wd / "tape.txt").read_text().splitlines(), (wet.wd / "tape.txt").read_text().splitlines()
    assert len(ta) > 3000 and ta == tb, ("the replay did not feed the DRY race's inputs", len(ta), len(tb))
    load = dry.load
    assert load and wet.load == load and dry.green == wet.green, (dry.load, wet.load, dry.green, wet.green)
    wa = [l.split()[2:] for l in parse_pass_log(dry.wd / "pass.txt")]
    wb = [l.split()[2:] for l in parse_pass_log(wet.wd / "pass.txt")]
    wa, wb = [w for w in wa if int(w[0]) >= load], [w for w in wb if int(w[0]) >= load]
    first = next((i for i, (x, y) in enumerate(zip(wa, wb)) if x != y), None)
    assert first is not None, "the RAIN replay with the handling is the DRY race: the handling changed nothing"
    frame = int(wa[first][0])
    with open(storm_runs.base / "rain_summary.txt", "a") as out:
        out.write(f"handling replay metropolis: the game parts from the DRY race at pass {first} (frame {frame}; the green "
                  f"{dry.green})\n")
    assert frame >= dry.green, (frame, dry.green)             # the countdown the same; the first race pass already parts (the
                                                              # take-off's wheelspin with the gas floored)


@pytest.mark.parametrize("name", list(SAME_GAME))
def test_rain_does_not_change_the_game(storm_runs, name):
    """In this stage the storm only draws: a RAIN race fed exactly the inputs of a DRY race on the same set (the autopilot's wheel and
    pedal recorded on the DRY race, input_tape.lua, replayed from the race start) is the same game. From the race load to the run's
    end: the game's state at the end of every pass (pass_state.lua with VR_PASS_FIELDS: the clock and the sixteen cars' x, z, road
    point, speed, lap, line cursor, target, performance, rank and neighbours) identical; the game's own lists the same (the need, the highest count the walker compared, equal at every pass, and the DRY
    frame's record count equal to the RAIN frame's count before the rain, less the lightning's records drawn before it (stage 4), on
    every visible rain pass); the storm did run (loaded once,
    the rain drawn). SAME_GAME: Big Forest on road line 4 (its heaviest place, the session battery RAM) and Metropolis (a converted
    course, its long tunnel). Stage 5's wet handling changes the game by design: GAME_CHANGING_MODULES leaves it out of the RAIN
    build here (test_the_handling_changes_the_replayed_game: with it in, the same replay parts from the DRY race)."""
    from vrtools.mame.framerate import parse_pass_log
    dry, rain = storm_runs.run("same", name, "dry"), storm_runs.run("same", name, "rain")
    ta, tb = (dry.wd / "tape.txt").read_text().splitlines(), (rain.wd / "tape.txt").read_text().splitlines()
    assert len(ta) > 3000 and ta == tb, (name, "the replay did not feed the DRY race's inputs", len(ta), len(tb))
    load = dry.load
    assert load and rain.load == load, (dry.load, rain.load)
    wa = [l.split() for l in parse_pass_log(dry.wd / "pass.txt")]
    wb = [l.split() for l in parse_pass_log(rain.wd / "pass.txt")]
    assert wa and len(wa[0]) == 4 + 16 * 12, ("the pass log lacks the cars' fields (VR_PASS_FIELDS)", len(wa[0]) if wa else 0)
    wa, wb = [w[2:] for w in wa if int(w[2]) >= load], [w[2:] for w in wb if int(w[2]) >= load]
    assert len(wa) > 3000 and len(wa) == len(wb), (name, len(wa), len(wb))
    first = next((i for i, (x, y) in enumerate(zip(wa, wb)) if x != y), None)
    assert first is None, (name, "the game state differs from pass", first, "frame", wa[first][0], wa[first][:12], wb[first][:12])
    na = {f.frame: f for f in dry.frames if f.frame >= load}
    nb = {f.frame: f for f in rain.frames if f.frame >= load}
    assert sorted(na) == sorted(nb)
    need = [fr for fr in sorted(na) if na[fr].need != nb[fr].need]
    assert need == [], (name, "the game's need differs", [(fr, na[fr].need, nb[fr].need) for fr in need[:5]])
    shows = [p for p in show_passes(rain) if p.frame in na]
    bolt = {}                                           # stage 4: the lightning's records on each pass (drawn before the rain)
    if (rain.wd / "light.txt").exists():
        from vrtools.mame.runner import parse_light_log
        bolt = {p.frame: p.s["REC"] for p in parse_light_log(rain.wd / "light.txt")[0]}
    own = [p.frame for p in shows if na[p.frame].records != p.rec_in - bolt.get(p.frame, 0)]
    assert len(shows) > 3000 and own == [], (name, "the game's own records differ", [(fr, na[fr].records) for fr in own[:5]])
    assert rain.storm.passes[-1].loads == 1 and statistics.median(p.drawn for p in shows) == 60
    with open(storm_runs.base / "rain_summary.txt", "a") as out:
        out.write(f"same game {name}: {len(wa)} passes from the load identical, need max {max(f.need for f in na.values())} in both, "
                  f"{len(shows)} visible rain passes with the game's own records equal\n")


def test_the_split_bound_after_the_count_moves():
    """The join (the session lead's split bound): post_move_over holds the unit in flight (the count's move to the guard's trip,
    storm_log.lua's B line) to carrier.UNIT_MAX_US and the tail (the trip to the pass's end) to carrier.TAIL_US, each on its own; a
    pass with an A line and no B line (the count moved after the storm's last guard test) holds its whole time to TAIL_US; a late
    pass without an A line fails. Planted logs, no MAME: a pass of 35 + 149 us (a unit in flight and round 2's worst forced tail)
    passes, where the old sum would have let a 220 us unit with a 10 us tail through."""
    from types import SimpleNamespace
    from vrtools.mame.runner import StormLog, StormPass
    U, T = carrier.UNIT_MAX_US, carrier.TAIL_US

    def log(after, trip, late_frames=()):
        passes, late = [], 0
        for f in range(10, 30, 2):
            late += f in late_frames
            passes.append(StormPass(f, 2, 1, 1, 3, f, 0xFFF000, 60, 10, late, 0, 0, 0, 0, 60, 1, 0, 9000, 9500))
        return SimpleNamespace(storm=StormLog(passes=passes, traces=[], frames=[], dumps={}, after=after, watch={}, cover=[], trip=trip))
    assert post_move_over(log({12: 184.0}, {12: (35.0, 149.0)})) == []
    assert [x[0] for x in post_move_over(log({12: 230.0}, {12: (220.0, 10.0)}))] == [12]           # a long unit: the sum hid it
    assert [x[0] for x in post_move_over(log({12: U + T + 1.0}, {12: (20.0, T + 1.0)}))] == [12]    # a long tail
    assert post_move_over(log({12: 25.0}, {})) == []                                                 # moved after the last test
    assert [x[0] for x in post_move_over(log({12: T + 5.0}, {}))] == [12]
    assert [x[0] for x in post_move_over(log({}, {}, late_frames=(14,)))] == [14]                     # late, no A line
    assert post_move_parts(log({12: 184.0, 16: 100.0}, {12: (35.0, 149.0), 16: (90.0, 10.0)})) == (90.0, 149.0)
