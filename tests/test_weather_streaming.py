"""v0.4.1, the streaming rain (docs/superpowers/specs/2026-11-25-streaming-rain-design.md, as Pascal drove and approved it: "ok i
think we r good, let s publish this update, update the website rain video with this one and make a release"), in MAME:

- one RAIN race on Big Forest (the rate tests' autopilot line, TAPE_SECONDS, the clock held) driven on the released v0.4's set
  (the reference set VR_V04_SET, tests/reference_sets.py) records its inputs; the same inputs replayed on this tree's set and on
  its key-coloured copies race the same race frame for frame (the rain changes nothing of the game: tests/test_weather_rain.py's
  test_rain_does_not_change_the_game), so their pictures compare frame for frame:
    - at rest the rain falls as v0.4's: the axis vertical but for v0.4's wind slant, the drops land and spawn the splashes;
    - the lean measured at three speeds (the rain's own cells at each pass's end against the car's speed);
    - the fill at speed: the rain's pixels (rain_pixels.lua's magenta, every drop drawn in one key colour on a copy of each set, the
      plain set's count at the same frame taken off) against v0.4's at 130-170 km/h and at top speed: the total FILL_TOTAL, no
      third of the picture under FILL_THIRD_MIN (design point 3);
    - the band shares: the near, mid and far bands in three key colours: each at least BAND_SHARE_MIN of the rain's pixels at both
      speeds (design point 5);
    - the lit rain (design point 6) only on the passes of the lightning's sky flashes, the afterglow's passes after, nothing between
      strikes;
- the splash rate (design point 7) on every course against v0.4's on the same autopilot line: within SPLASH_TOL.

The lit rain under cover, its share of the picture on a flash pass and the flash rule read from the picture itself are
tests/test_weather_lightning.py's (its stress runs)."""
import math
import os
import shutil
import statistics
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.reference_sets import reference_set
from tests.test_weather_rain import NAMES, storm_runs  # noqa: F401 (the fixture)
from vrtools.mame.runner import LUA_DIR, parse_light_log, parse_rain_pixels, parse_storm_log, run_mame

V04 = "VR_V04_SET"
TAPE_ENTRY, TAPE_SECONDS = 0, 150       # Big Forest, the rate tests' line: v0.4's race recorded, replayed on this tree's sets
SPEED_BANDS = ("130-170", "top")        # km/h 130..170; the run's top speed less 25 and over
FILL_TOTAL = (0.9, 1.3)                 # design point 3: the rain's lit pixels against v0.4's, both speed bands
FILL_THIRD_MIN = 0.7                    # ... and no third of the picture under this, but for:
FILL_TOP_150_MIN = 0.6                  # the top third at 130-170 km/h (the session lead's ruling of 25 Nov 2026: the approved look
                                        # measures 0.67 there (dev1; 0.64 on the release build's last run), spike 87's play_fx3 0.66; the 0.7 was the lead's number, not the owner's)
BAND_SHARE_MIN = 0.1                    # each depth band's share of the rain's pixels, both speed bands
SPLASH_TOL = 0.10                       # the splash rate against v0.4's on the same line, each course
LEAN_SPEEDS = (100, 150, 250)           # km/h: the lean measured at the passes nearest these
LEAN_TOL_DEG = 0.5
KEYS = {"magenta": (31, 0, 31), "cyan": (0, 31, 31), "yellow": (31, 31, 0)}
# v0.4's layout (the reference set's, fixed): its 34 drop colour words at the start of its "rain colours" block, its rain state
# cells (the cover's and the lightning's cells before them are the same size in this tree: checked against the layout)
V04_DROP_WORDS = (0x28FF80, 34)
V04_RAIN_STATE = 0x5206A4
JOBS = int(os.environ.get("VR_MAME_JOBS") or 2)
WATCH = ("SPEED", "MOVE", "ZST", "LEANK", "LEANT", "ZFV", "SPAWNS", "LANDS", "AGLOW", "WCUR", "PN", "PM", "PF")


def fbits(v: int) -> float:
    return struct.unpack("<f", struct.pack("<I", v & 0xFFFFFFFF))[0]


def recolour(src: Path, dst: Path, words: dict[int, tuple]) -> Path:
    """A copy of the set at `src` (vr.zip and its two companions) in `dst` with each colour word of the program ROM at the address
    (a key of `words`) pointing at the polygon palette's entry nearest its target under the grade (the word's mode bits kept; a word
    that is not a colour word refuses)."""
    from vrtools.arcade.romset import V60_PROGRAM, RomSet
    from vrtools.arcade.weather import rain
    rs = RomSet.from_zip(src / "vr.zip", verify=False)
    pal = rain.polygon_palette(rs)
    prog = bytearray(rs.program)
    for addr, target in words.items():
        o = addr - V60_PROGRAM
        w = struct.unpack_from("<H", prog, o)[0]
        assert w & 0xC00 == 0xC00, (hex(addr), hex(w), "not a colour word")
        struct.pack_into("<H", prog, o, (w & ~0x3FF) | rain.pick(pal, target))
    from dataclasses import replace
    dst.mkdir(parents=True, exist_ok=True)
    replace(rs, program=bytes(prog)).to_zip(dst / "vr.zip", source=src / "vr.zip")
    for extra in ("model1io.zip", "m1comm.zip"):
        shutil.copy(src / extra, dst / extra)
    return dst


def tone_addrs(set_index: int) -> list[int]:
    """The program ROM addresses of colour table set `set_index`'s words (rain.SETS' order) in this tree's layout."""
    from vrtools.arcade.weather import layout
    records = 29
    start = layout.block("rain tones").start + 2 * records * set_index
    return [start + 2 * k for k in range(records)]


class StreamSession:
    """The streaming rain's sets (v0.4's and this tree's key-coloured copies) and taped runs, made at the first use."""

    def __init__(self, storm, base: Path):
        from vrtools.arcade.weather import rain
        self.storm, self.rate, self.base = storm, storm.rate, base
        self.lay = storm.lay
        self.cells = {n: (rain.SPEED if n == "SPEED" else rain.cell(self.lay, n)) for n in WATCH}
        self.sets, self.runs, self.failed = {}, {}, {}
        self._lock, self._set_lock = threading.Lock(), threading.Lock()

    def v04(self) -> Path:
        return reference_set(V04)

    def set(self, kind) -> Path:
        """"v04" the reference set; "v04key" its drops in magenta; "key" this tree's drops (every set) in magenta; "band" the near,
        mid and far sets magenta, cyan, yellow (the lit set as built); "plain" this tree's set."""
        with self._set_lock:
            if kind not in self.sets:
                d = self.base / "sets" / kind
                if kind == "v04":
                    self.sets[kind] = self.v04()
                elif kind == "v04key":
                    a, n = V04_DROP_WORDS
                    self.sets[kind] = recolour(self.v04(), d, {a + 2 * k: KEYS["magenta"] for k in range(n)})
                elif kind == "key":
                    self.sets[kind] = recolour(self.storm.build, d, {a: KEYS["magenta"] for s in range(4) for a in tone_addrs(s)})
                elif kind == "band":
                    self.sets[kind] = recolour(self.storm.build, d, {a: KEYS[c] for s, c in enumerate(("magenta", "cyan", "yellow"))
                                                                     for a in tone_addrs(s)})
                else:
                    self.sets[kind] = self.storm.build
            return self.sets[kind]

    def _make(self, key):
        from tests.test_frame_rate import Run
        from vrtools.mame.runner import light_env
        kind = key[0]
        wd = self.base / "runs" / "_".join(str(k) for k in key)
        wd.mkdir(parents=True, exist_ok=True)
        logs = {"VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"), "VR_STALE_LOG": str(wd / "stale_list.txt")}
        if kind == "v04rate":                          # v0.4's RAIN race on the rate tests' line: its splashes (SPAWNS)
            entry = key[1]
            env = self.rate._env(wd, entry, False)
            env.update({**logs, "VR_HOLD_CLOCK": "1", "VR_RAIN": "1", "VR_STORM_LOG": str(wd / "storm.txt"),
                        "VR_STORM_RAIN": f"{V04_RAIN_STATE:x}", "VR_STORM_WATCH": f"{V04_RAIN_STATE + 4 * 18:x}"})
            run_mame(LUA_DIR / "autoplay.lua", TAPE_SECONDS, wd, self.set("v04"), env=env, timeout=3600)
            r = Run(wd)
            r.storm = parse_storm_log(wd / "storm.txt")
            return r
        setkind = {"tape": "v04key", "key": "key", "band": "band", "plain": "plain"}[kind]
        env = self.rate._env(wd, TAPE_ENTRY, False)
        env.update({**logs, "VR_HOLD_CLOCK": "1", "VR_RAIN": "1", "VR_EXTRA_LUA": str(LUA_DIR / "rain_pixels.lua"),
                    "VR_RPIX_LOG": str(wd / "rpix.txt"), "VR_INPUT_LOG": str(wd / "tape.txt")})
        if kind == "tape":
            env.update({"VR_STORM_LOG": str(wd / "storm.txt"), "VR_STORM_RAIN": f"{V04_RAIN_STATE:x}"})
        else:
            env.update({"VR_INPUT_REPLAY": str(self.run("tape").wd / "tape.txt"), "VR_STORM_LOG": str(wd / "storm.txt"),
                        "VR_STORM_RAIN": f"{self.lay.cell('rain', 'state'):x}",
                        "VR_STORM_WATCH": ",".join(f"{self.cells[n]:x}" for n in WATCH), **light_env(self.lay, wd)})
        shutil.copytree(self.rate.nvram(), wd / "nvram")
        run_mame(LUA_DIR / "autoplay.lua", TAPE_SECONDS, wd, self.set(setkind), env=env, timeout=3600)
        r = Run(wd)
        r.storm = parse_storm_log(wd / "storm.txt")
        r.pix = parse_rain_pixels(wd / "rpix.txt")
        if kind != "tape":
            r.light, _ = parse_light_log(wd / "light.txt")
            r.cells = {f: dict(zip(WATCH, v)) for f, v in r.storm.watches.items()}
        return r

    def prefetch(self, keys):
        keys = [k for k in dict.fromkeys(keys) if k not in self.runs]
        if any(k[0] != "v04rate" for k in keys):
            self.rate.nvram()
        first = [k for k in keys if k[0] in ("tape", "v04rate")]
        replays = [k for k in keys if k not in first]

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
            list(ex.map(make, first))
        with ThreadPoolExecutor(JOBS) as ex:           # each replays the tape: made after it
            list(ex.map(make, replays))

    def run(self, *key):
        if key in self.failed:
            raise AssertionError(f"the run {key} failed: {self.failed[key]!r}") from self.failed[key]
        if key not in self.runs:
            self.runs[key] = self._make(key)
        return self.runs[key]


def stream_keys(items) -> list:
    need = {"test_at_rest_the_rain_falls_and_lands": lambda p: [("tape",), ("plain",)],
            "test_the_lean_measured_at_three_speeds": lambda p: [("tape",), ("plain",)],
            "test_the_fill_at_speed_against_v04": lambda p: [("tape",), ("key",), ("plain",)],
            "test_the_band_shares": lambda p: [("tape",), ("band",), ("plain",)],
            "test_the_lit_rain_only_on_the_flash_passes": lambda p: [("tape",), ("plain",)],
            "test_the_splash_rate_against_v04": lambda p: [("v04rate", p["entry"])]}
    keys = []
    for i in items:
        name = getattr(i, "originalname", None) or getattr(i, "name", "")
        p = getattr(getattr(i, "callspec", None), "params", {})
        if name in need and not i.get_closest_marker("skip"):
            keys += need[name](p)
    return keys


_SESSIONS: dict = {}


@pytest.fixture
def stream_runs(request, storm_runs, tmp_path_factory) -> StreamSession:  # noqa: F811 (the fixture)
    key = str(storm_runs.rate.romset_zip)
    if key not in _SESSIONS:
        s = StreamSession(storm_runs, tmp_path_factory.mktemp("stream"))
        if any(k[0] in ("tape", "v04rate") for k in stream_keys(request.session.items)):
            s.v04()                                    # skips (fails under VR_REQUIRE_REFERENCE_SETS=1) without v0.4's set
        s.prefetch(stream_keys(request.session.items))
        _SESSIONS[key] = s
    return _SESSIONS[key]


def _note(s: StreamSession, text: str) -> None:
    with open(s.base / "stream_summary.txt", "a") as out:
        out.write(text + "\n")


def race_pix(r):
    """{frame: P line} of the race's frames (from the green to the end)."""
    return {p.frame: p for p in r.pix if r.start <= p.frame < (r.end or 1 << 30)}


def band_frames(pix: dict) -> dict:
    """{band: [frames]}: 130-170 km/h; the top speed less 25 and over."""
    top = max(p.kmh for p in pix.values())
    return {"130-170": [f for f, p in pix.items() if 130 <= p.kmh <= 170], "top": [f for f, p in pix.items() if p.kmh >= top - 25]}


# ---- at rest ------------------------------------------------------------------------------------------------------------------
def test_at_rest_the_rain_falls_and_lands(stream_runs):
    """Design point 1: at rest (the countdown on the grid, the car's speed 0) the rain is v0.4's: no lean (LEANT 0, the y column's
    scale LEANK 1: the axis vertical but for v0.4's wind slant SLV), no depth step, MOVE 0 (the drops land), and the landings spawn
    the splashes (SPAWNS and LANDS grow on those passes); at racing speed (150 km/h and over, in the race: from its start to its end,
    the passes the rain ran on; the attract's demo race before the game, also at speed, has no rain) MOVE is 1 and nothing lands."""
    r = stream_runs.run("plain")
    rest = [(f, c) for f, c in sorted(r.cells.items()) if f < r.green and c["SPEED"] == 0 and fbits(c["LEANK"]) != 0.0]
    assert len(rest) > 50, len(rest)
    assert all(fbits(c["LEANT"]) == 0.0 and fbits(c["LEANK"]) == 1.0 and fbits(c["ZST"]) == 0.0 and c["MOVE"] == 0 for _, c in rest)
    assert rest[-1][1]["SPAWNS"] > rest[0][1]["SPAWNS"] and sum(c["LANDS"] for _, c in rest) > 0
    fast = [c for f, c in r.cells.items() if r.start <= f < (r.end or 1 << 30) and c["SPEED"] >= 150 and fbits(c["LEANK"]) != 0.0]
    assert fast and all(c["MOVE"] == 1 and c["LANDS"] == 0 for c in fast)
    _note(stream_runs, f"at rest: {len(rest)} passes, splashes spawned {rest[-1][1]['SPAWNS'] - rest[0][1]['SPAWNS']}, landings "
                       f"{sum(c['LANDS'] for _, c in rest)}")


def test_the_lean_measured_at_three_speeds(stream_runs):
    """Design point 2 in MAME: at the passes nearest 100, 150 and 250 km/h on the taped race, the drops' axis from the rain's cells
    (the y column's depth share over its height, LEANT / LEANK) leans atan(v / 170 km/h) from the vertical (30, 41 and 56 degrees)
    within LEAN_TOL_DEG, its length LEANK sqrt(1 + t^2) the length curve's, the depth step ZST = FALL t; never over 60 degrees on
    any pass."""
    from tests.test_weather_rain import lean_model
    from vrtools.arcade.weather import rain
    r = stream_runs.run("plain")
    race = {f: c for f, c in r.cells.items() if r.start <= f < (r.end or 1 << 30)}
    out = []
    for v in LEAN_SPEEDS:
        f, c = min(race.items(), key=lambda fc: abs(fc[1]["SPEED"] - v))
        assert abs(c["SPEED"] - v) <= 3, (v, c["SPEED"])
        k, t = fbits(c["LEANK"]), fbits(c["LEANT"])
        deg = math.degrees(math.atan2(t, k))
        m = lean_model(c["SPEED"])
        assert abs(deg - m["deg"]) < LEAN_TOL_DEG and abs(k * math.sqrt(1 + (t / k) ** 2) - m["length"]) < 0.02, (v, deg, m)
        assert abs(fbits(c["ZST"]) - rain.FALL * m["tan"]) < 1e-3
        out.append(f"{c['SPEED']} km/h at {f}: {deg:.1f} degrees, length {k * math.sqrt(1 + (t / k) ** 2):.2f}")
    assert max(math.degrees(math.atan2(fbits(c["LEANT"]), fbits(c["LEANK"]))) for c in race.values()) <= 60.0 + 1e-3
    _note(stream_runs, "lean: " + "; ".join(out))


# ---- the picture ----------------------------------------------------------------------------------------------------------------
def fill(r, plain, frames) -> dict:
    """The mean rain pixels over `frames` (magenta less the plain set's at the same frame): total, top, middle, bottom."""
    pk, pp = race_pix(r), race_pix(plain) if plain is not None else None
    rows = []
    for f in frames:
        if f in pk and (pp is None or f in pp):
            rows.append([pk[f].magenta[k] - (pp[f].magenta[k] if pp else 0) for k in range(3)])
    m = [statistics.mean(x[k] for x in rows) for k in range(3)]
    return {"total": sum(m), "top": m[0], "middle": m[1], "bottom": m[2], "n": len(rows)}


def test_the_fill_at_speed_against_v04(stream_runs):
    """Design point 3 (Pascal on the 0.7 build: "at speed i got the feeling the rain doesnt feel the screen or is less intense"):
    on the same race frame for frame, the rain's pixels (every drop in one key colour) against v0.4's at 130-170 km/h and at top
    speed: the total within FILL_TOTAL, each third of the picture (top, middle, bottom) at least FILL_THIRD_MIN, but the top third
    at 130-170 km/h at least FILL_TOP_150_MIN: measured 0.67 there on the approved look (0.64 on the release build's last run; the build Pascal drove, spike 87's play_fx3,
    measured 0.66), and any placement change alters the picture he approved (the session lead's ruling of 25 Nov 2026: the top of
    the picture is a third thinner than v0.4's at that speed, as the owner drove it)."""
    tape, key, plain = stream_runs.run("tape"), stream_runs.run("key"), stream_runs.run("plain")
    bands = band_frames(race_pix(tape))
    lines, bad = [], []
    for b in SPEED_BANDS:
        old, new = fill(tape, None, bands[b]), fill(key, plain, bands[b])
        assert old["n"] > 100 and new["n"] > 100, (b, old["n"], new["n"])
        ratio = {k: new[k] / old[k] for k in ("total", "top", "middle", "bottom")}
        lines.append(f"{b}: frames {new['n']}, v0.4 {old['total']:.0f} px, now {new['total']:.0f} px, ratios " +
                     " ".join(f"{k} {v:.2f}" for k, v in ratio.items()))
        floors = {"top": FILL_TOP_150_MIN if b == "130-170" else FILL_THIRD_MIN, "middle": FILL_THIRD_MIN, "bottom": FILL_THIRD_MIN}
        if not FILL_TOTAL[0] <= ratio["total"] <= FILL_TOTAL[1] or any(ratio[k] < f for k, f in floors.items()):
            bad.append((b, ratio))
    _note(stream_runs, "fill: " + "; ".join(lines))
    assert bad == [], (bad, lines)


def test_the_band_shares(stream_runs):
    """Design point 5: the near, mid and far bands (cut at 0.33 and 0.55 of the placement's far depth) each hold at least
    BAND_SHARE_MIN of the rain's pixels at 130-170 km/h and at top speed (the bands in magenta, cyan and yellow on a copy of the set;
    the plain set's own pixels of those colours at the same frame taken off; the passes of a lit rain left out)."""
    band, plain = stream_runs.run("band"), stream_runs.run("plain")
    pb, pp = race_pix(band), race_pix(plain)
    lit = {f for f, c in band.cells.items() if c["AGLOW"] or fbits(c["WCUR"]) != 1.0}
    lit |= {f + d for f in lit for d in range(1, 5)}
    bands = band_frames(pb)
    lines = []
    for b in SPEED_BANDS:
        rows = [(sum(pb[f].magenta) - sum(pp[f].magenta), pb[f].cyan - pp[f].cyan, pb[f].yellow - pp[f].yellow)
                for f in bands[b] if f in pp and f not in lit]
        tot = [statistics.mean(x[k] for x in rows) for k in range(3)]
        share = [v / sum(tot) for v in tot]
        lines.append(f"{b}: frames {len(rows)}, near {share[0]:.2f}, mid {share[1]:.2f}, far {share[2]:.2f}")
        assert len(rows) > 100 and min(share) >= BAND_SHARE_MIN, (b, share, len(rows))
    _note(stream_runs, "bands: " + "; ".join(lines))


# ---- the lit rain ---------------------------------------------------------------------------------------------------------------
def lit_errors(cells, light, storm, tune=None):
    """The lit rain pass by pass: `cells` {frame: the rain's WCUR, AGLOW, PN, PM, PF}, `light` the lightning log's passes (LEVEL,
    the cover's byte), `storm` the storm log. On a pass whose lightning LEVEL is a flash (lightning.FLASH_OF_LEVEL not 0) in the open
    every band the lit set at lit_width, AGLOW = afterglow; after it while AGLOW runs (one less a pass) near lit, mid near, far mid at
    width 1; under cover (the cover's byte) the depth sets at width 1 and AGLOW 0; every other pass the depth sets at width 1. The
    passes the guard stopped before the choices (late, nothing drawn) keep the last pass's cells and are skipped. (flash passes,
    afterglow passes, passes under cover, errors)."""
    from vrtools.arcade.weather import layout, lightning, rain
    t = tune
    if t is None:
        from vrtools.arcade.weather.tune import RainTune
        t = RainTune()
    base = rain.tex(layout.block("rain tones").start)
    ptr = [base + s * 29 for s in range(4)]
    lp = {p.frame: p for p in light}
    passes = {p.frame: p for p in storm.passes}
    early, last = set(), 0
    for p in storm.passes:
        if p.late > last and p.drawn == 0:
            early.add(p.frame)
        last = p.late
    flashes = glow = under = 0
    prev, errs = None, []
    for f, c in sorted(cells.items()):
        if f not in lp or f not in passes or c["PN"] == 0 or f in early:   # before the rain's first visible pass; late
            prev = c
            continue
        sets = (c["PN"], c["PM"], c["PF"])
        level = lp[f].s["LEVEL"]
        if lp[f].cover:
            under += 1
            want = ((ptr[0], ptr[1], ptr[2]), 1.0, 0)
        elif lightning.FLASH_OF_LEVEL[level]:
            flashes += 1
            want = ((ptr[3],) * 3, t.lit_width, t.afterglow)
        elif prev is not None and prev["AGLOW"]:
            glow += 1
            want = ((ptr[3], ptr[0], ptr[1]), 1.0, prev["AGLOW"] - 1)
        else:
            want = ((ptr[0], ptr[1], ptr[2]), 1.0, 0)
        if (sets, fbits(c["WCUR"]), c["AGLOW"]) != want:
            errs.append((f, level, lp[f].cover, sets, fbits(c["WCUR"]), c["AGLOW"], want))
        prev = c
    return flashes, glow, under, errs


def test_the_lit_rain_only_on_the_flash_passes(stream_runs):
    """Design point 6 on the taped race (the normal tune: a strike every 20-40 s): on every pass whose lightning LEVEL is a flash (the
    sky flashes and the white-out: lightning.FLASH_OF_LEVEL not 0) every band is the lit set at lit_width; on the afterglow passes
    after it (AGLOW counting afterglow - 1 .. 0) the near band the lit set, the mid the near set, the far the mid set, at width 1; on
    every other pass the depth sets at width 1: nothing between strikes. At least one strike flashed."""
    from vrtools.arcade.weather.tune import RainTune
    r = stream_runs.run("plain")
    lay = stream_runs.lay
    flashes, glow, under, errs = lit_errors(r.cells, r.light, r.storm)
    _note(stream_runs, f"lit rain: {flashes} flash passes, {glow} afterglow passes, errors {len(errs)}")
    assert flashes > 0 and glow >= RainTune().afterglow and errs == [], errs[:5]
    assert lay.cell("rain", "state") == V04_RAIN_STATE            # v0.4's rain cells at the same place (the v04 runs' logger)


# ---- the splashes ---------------------------------------------------------------------------------------------------------------
def splash_rate(r, spawns) -> float:
    """Splashes spawned a race second (the race from the green to its end; 57.52 video frames a second)."""
    race = sorted((f, v) for f, v in spawns.items() if r.green <= f < (r.end or 1 << 30))
    return (race[-1][1] - race[0][1]) / ((race[-1][0] - race[0][0]) / 57.52)


@pytest.mark.parametrize("entry", [pytest.param(e, id=NAMES[e]) for e in range(10)])
def test_the_splash_rate_against_v04(stream_runs, entry):
    """Design point 7: on each course (the rate tests' RAIN race on its autopilot line, TAPE_SECONDS) the splashes spawned a second
    (the rain's SPAWNS: landings below splash_kmh, the rule's above it) within SPLASH_TOL of v0.4's on the same line."""
    from vrtools.arcade.weather import rain
    old = stream_runs.run("v04rate", entry)
    new = stream_runs.storm.run("rain", entry, False)
    assert min(len(v) for v in new.storm.watches.values()) >= 2, "the rate runs watch the rain's SPAWNS second (storm_env)"
    a = splash_rate(old, old.storm.watch)
    b = splash_rate(new, {f: v[1] for f, v in new.storm.watches.items()})
    _note(stream_runs, f"splashes {NAMES[entry]}: v0.4 {a:.1f}/s, now {b:.1f}/s ({b / a:.2f})")
    assert abs(b / a - 1) <= SPLASH_TOL, (NAMES[entry], a, b)
    assert rain.cell(stream_runs.lay, "SPAWNS") == V04_RAIN_STATE + 4 * 18
