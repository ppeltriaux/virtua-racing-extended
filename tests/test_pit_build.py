"""Phase 26 stage 4 (Task 4): pit stops driven headless on the seven converted courses, in each direction, on the session's built
set (`tests.test_tgp_build._seven`: one conversion per session). A normal stop per course (the baseline), a reverse stop per course
with the variant's pair and box (Task 3), and the controls: the plain reverse line never stops (Review Focus 3), two stops and no
third (Review Focus 2). What a stop does frame by frame, and what a pit test asserts: docs/spike/2026-11-phase26-stage4-recon.md
§1.1 and §7.

Each run is made once per session (`PitSession`, keyed by course and kind) and the runs a session's tests need are made in two
parallel waves at the first use (the normal and the plain runs, then the reverse runs, whose paths read the normal runs'
trajectories, and the long run). The paths are computed in the session (decision L4, `vrtools.mame.pitpaths`): nothing driven is
stored. The `pit_runs` fixture gives other tests (Task 5's crew comparison) the same runs: `pit_runs.run(entry, "normal")` and
`pit_runs.run(entry, "reverse")`, each a `PitRun` with its parsed pit log (`frames`, `runner.PitFrame`: the crew of every frame).

Task 5 (decision P2, the lead's reading of Pascal's 'Ok'): in a reverse race the crew is turned half a turn about the box
(`direction.crewturn`) and its world-axis animation mirrored (`figmirror` holds for the crew's records). Its tests compare the
crew of a reverse stop with a reference stop of the same pit work state, frame for frame from the park: the session's normal stop,
or on Metropolis (whose normal stop is work state 11 and reverse stop 14 in these runs: different crews) the reverse stop on the
set without Task 5's crew change (`PitSession.nocrew`, the game's own placement and animation, which the recon measured the same
in both directions for a work state). crewdraw_log.lua records what the crew's animation pushes to the TGP through the figure
routines.

Frames are video frames counted from 1 at the first frame end (pit_log.lua and race_log.lua; fieldtrace.lua's frame f is their
f + 1, memtrace.lua's likewise). The race loads at about 1600 and the green is at about 1864 in this harness."""
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from vrtools.arcade.course import course_entry_at, road_lines
from vrtools.arcade.directory import decode_directory, directory_layout
from vrtools.arcade.race import decode_race_blob
from vrtools.arcade.romset import RomSet
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.arcade.tencourse import COURSES as PLANS
from vrtools.arcade.tgp import QUAD_WORDS, decode_quad, slot_table, words as tgp_words
from vrtools.convert.collision import PIT_LANE_HALF_WIDTH, wall_trim_of
from vrtools.convert.reverse import reverse_points
from vrtools.mame.pitpaths import green as green_index, normal_pit_path, pit_lane, resample, reverse_pit_path
from vrtools.mame.runner import (LUA_DIR, PARK_FLAG, PIT_HANDLER, PitFrame, parse_crew_draw_log, parse_field, parse_pit_log,
                                 parse_race_log, run_mame, write_centreline)
from tests.test_reverse_build import COURSES, WARNING_READS
from tests.test_tgp_build import _build, _seven

# The game's code facts (stage 4 recon §1.1, read from the boot ROM and measured on every course in both directions):
PIT_WORK_FRAMES = 444       # release − park, video frames: the crew's work (state 2 waits for the park flag, state 3 for crew object 0)
PIT_EXTEND = 384            # the release adds [0xfcd5b5] to the clock (12 s); the clock stands still from the trigger to the release
STOPS_GRANTED = 2           # `pitstops` sets +0x1bf to 2 at the race start for an entry whose load record has a pit quad
LOGIC_STEP = 2              # video frames a logic frame: the player's handler tests last frame's +0x150, so the trigger comes one
                            # logic frame after the car is first logged on the pair
SECONDS = 150               # each run's game time (the recon's: every course's first stop lies inside it, in both directions)
REVERSE_SECONDS = 180       # a reverse run's: two gates after the release on every course (at 150 s Surfers Road reaches none, its lap
                            # counted under the pit autopilot and the line paid at the release, and Diablo Canyon one)
LONG_SECONDS = 240          # the two-stop run: three passes of Amazon Falls's lane in reverse
REVERSE_AHEAD = 15          # autopilot.lua's search window on a reverse pit path (VR_AUTOPILOT_AHEAD; recon §3 item 4: at 40 the car
                            # jumped from Diablo Canyon's lane to the road loop beside it)
SPOT_CENTRE = 2.0           # units: on Diablo Canyon the reverse car keeps the lane's centre through Task 1's trimmed spot
SPOT_WEST = 3.0             # units: the second line through Diablo Canyon's spot runs this far to the lane's west of its centre (the
                            # old wall covered the lane's west half up to the centre line)
SPOT_FULL, SPOT_RAMP = 50.0, 30.0   # units along the path: the west line's full offset either side of the spot, then its ramp to 0
                            # (longer than the autopilot's aim ahead, SPOT_LOOKAHEAD points of 10 units, so it is not cut)
SPOT_LOOKAHEAD = 3          # autopilot.lua's aim ahead on the spot runs (VR_AUTOPILOT_LOOKAHEAD, points; 6 by default). Scratch runs of
                            # 14 Nov on the trimmed set: at 6 the car ran 1.8-2.1 units west of its path through the band at 322 km/h
                            # (past SPOT_PATH, no wall hit), at 3 0.7-1.5 units on both lines
SPOT_SECONDS = 120          # the spot runs: the reverse car reaches Diablo Canyon's spot about 106 s in
SPOT_PATH = 2.0             # units: the car stays this near its own path through the spot's z band
SPOT_MARGIN = 20.0          # units of z either side of the band in which no wall is hit
SPOT_SPEED = 150            # km/h (+0x14) at least through the band: a real pass
CLOCK_READS = "50116c-50116f"     # memtrace.lua also taps the clock, which the race reads every frame: the taps' positive control
MAME_WORKERS = 7            # MAME runs at once in a wave
ALPINE = 3
AMAZON_FALLS = 4
DIABLO = 5
METROPOLIS = 6
# Task 5: the crew in reverse
CREW_TOL = 0.05             # units: a reverse crew object's x and z against the reference's reflected through the box (two TGP float
                            # adds per axis; the log prints 4 decimals)
CREW_EVERY = 20             # frames: the positions are compared every CREW_EVERY frames from the park to the release
# the reference stop of each crew test's course: the normal stop where its pit work state is the reverse stop's; Metropolis's
# normal stop is work state 11 and its reverse stop 14 (the player's damage flags +0x1ab pick it at the trigger, recon §1.1),
# whose six crew objects differ in records and places, so its reference is the reverse stop without Task 5's crew change
CREW_REFERENCE = {ALPINE: "normal", AMAZON_FALLS: "normal", DIABLO: "normal", METROPOLIS: "nocrew_reverse"}
CREW_UNCHANGED = (AMAZON_FALLS, METROPOLIS)    # Review Focus 4: their normal stops with and without Task 5's crew change
CREW_ROUTINES = ("figrootx", "figrootz", "figrot0", "figrot2")   # the figure routines that push the animation's world-axis uses
# The fix wave after the final review (item 13): the work state is picked at the trigger (0xff222f) from the player's damage flags
# +0x1ab: & 0xf = 0 state 1; else & 3 = 0 state 11 (0xb); else & 0xc = 0 state 8; else 14 (0xe). pit_log.lua's VR_PIT_DAMAGE writes
# the byte on every frame from the green to the trigger: 1 gives state 8, 4 state 11. Runs "normal_s8" / "reverse_s8" (and _s11)
# are the normal and reverse pit runs with that poke.
DAMAGE = {"s8": (1, 8), "s11": (4, 11)}     # kind suffix -> (the byte written to +0x1ab, the work state it picks)
# the crew tests' cases: (entry, the reverse run, its reference run of the same work state)
CREW_CASES = [(e, "reverse", k) for e, k in CREW_REFERENCE.items()] + [(AMAZON_FALLS, f"reverse_{d}", f"normal_{d}") for d in DAMAGE]
CREW_LOGGED = ({(e, k) for e in CREW_REFERENCE for k in ("normal", "reverse", "nocrew", "nocrew_reverse")}
               | {(e, k) for e, *ks in CREW_CASES for k in ks})           # the runs that carry crewdraw_log.lua's log
# (item 11) the plain reverse run on the road's outermost line on the pit lane's side at the normal exit
PACIFIC = 7
EDGE_LINE = 4               # road line 4, `road.AI_OFFSETS[3]` = +8 (right of the normal direction): on Alpine and Metropolis the
EDGE_OFFSET = 8.0           # outermost line nearer the lane's exit (line 1, -8, lies on the far side of the road)
EDGE_COURSES = (ALPINE, METROPOLIS)
# (item 12) reverse stops entered off the lane's centre: the reverse pit path shifted across the lane about the pair's middle (fully
# within ENTER_FULL along the path, then a ramp of ENTER_RAMP), toward the road ("road", +) or away from it ("garage", -)
ENTER_OFFSET = 3.0          # units from the lane's centre
ENTER_MARGIN = 2.0          # units: the widest entry ("_max") runs this far inside the lane's tarmac edge at the pair's middle
ENTER_FULL, ENTER_RAMP = 40.0, 30.0
ENTER_CASES = [(DIABLO, "enter_road"), (DIABLO, "enter_garage"), (PACIFIC, "enter_road"), (PACIFIC, "enter_garage"),
               (DIABLO, "enter_road_max"), (DIABLO, "enter_garage_max")]
NORMAL_KINDS = ("normal", "nocrew", "normal_s8", "normal_s11")
FIRST_WAVE = NORMAL_KINDS + ("plain", "edge")    # the runs whose paths need no other run


def spot_path(path, lane, trim, west):
    """The closed path `path` moved `west` units to the lane's west (the side of the lane's normal pointing to -x) about Task 1's
    spot (`trim`, x0, x1, z0, z1): fully within SPOT_FULL along the path of its point nearest the lane at the middle of the
    rectangle's z range, then less, linearly, to nothing SPOT_RAMP farther."""
    x0, x1, z0, z1 = trim
    zc = (z0 + z1) / 2
    a, b = next((a, b) for a, b in zip(lane, lane[1:]) if min(a[1], b[1]) <= zc <= max(a[1], b[1]))
    c = (a[0] + (b[0] - a[0]) * (zc - a[1]) / (b[1] - a[1]), zc)
    n = len(path)
    k = min(range(n), key=lambda i: math.dist(path[i], c))
    arc = {k: 0.0}
    for step in (1, -1):
        i, s = k, 0.0
        while s < SPOT_FULL + SPOT_RAMP:
            j = (i + step) % n
            s += math.dist(path[i], path[j])
            arc[j], i = s, j
    out = list(path)
    for i, s in arc.items():
        w = 1.0 if s <= SPOT_FULL else max(0.0, 1.0 - (s - SPOT_FULL) / SPOT_RAMP)
        if w == 0.0:
            continue
        x, z = path[i]
        p, q = min(zip(lane, lane[1:]), key=lambda pq: _seg_dist((x, z), *pq))
        L = math.dist(p, q)
        nx, nz = (q[1] - p[1]) / L, -(q[0] - p[0]) / L
        if nx > 0:
            nx, nz = -nx, -nz
        out[i] = (x + west * w * nx, z + west * w * nz)
    return out


def _enter_offset(c, quad: int, kind: str) -> float:
    """The signed shift (`shift_path`) of an "enter_*" run on course `c` whose reverse pair is (`quad`, `quad` + 1): ENTER_OFFSET
    toward the road ("enter_road") or away from it ("enter_garage"); "_max": the lane's tarmac extent on that side at the pair's
    middle less ENTER_MARGIN."""
    at = c.pair_middle(quad)
    side = c.road_side(at) * (1.0 if kind.startswith("enter_road") else -1.0)
    return side * (c.tarmac_extent(at, side) - ENTER_MARGIN if kind.endswith("_max") else ENTER_OFFSET)


def _seg_dist(p, a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dz * dz
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / l2))
    return math.hypot(a[0] + t * dx - p[0], a[1] + t * dz - p[1])


def lane_distance(lane, x, z):
    """Distance from (x, z) to the open polyline `lane`."""
    return min(_seg_dist((x, z), a, b) for a, b in zip(lane, lane[1:]))


def _lane_normal(p, q):
    """The unit normal (dz, -dx) / L of the lane's segment p -> q (the polyline runs from the mouth to the exit)."""
    L = math.dist(p, q)
    return (q[1] - p[1]) / L, -(q[0] - p[0]) / L


def lane_offset(lane, x, z):
    """(x, z)'s signed distance from the open polyline `lane`: positive on the side of its nearest segment's `_lane_normal`."""
    p, q = min(zip(lane, lane[1:]), key=lambda pq: _seg_dist((x, z), *pq))
    nx, nz = _lane_normal(p, q)
    d = _seg_dist((x, z), p, q)
    return d if (x - p[0]) * nx + (z - p[1]) * nz >= 0 else -d


def _west(lane, x, z) -> float:
    """The sign that makes `lane_offset` positive to the west (-x) at (x, z): `spot_path`'s side."""
    p, q = min(zip(lane, lane[1:]), key=lambda pq: _seg_dist((x, z), *pq))
    return -1.0 if _lane_normal(p, q)[0] > 0 else 1.0


def _in_poly(poly, x, z) -> bool:
    """(x, z) inside or on the convex polygon `poly` ((x, z) corners, either winding)."""
    sign = 0
    for k in range(len(poly)):
        a, b = poly[k], poly[(k + 1) % len(poly)]
        c = (b[0] - a[0]) * (z - a[1]) - (b[1] - a[1]) * (x - a[0])
        if c:
            if sign and (c > 0) != (sign > 0):
                return False
            sign = c
    return True


def shift_path(path, lane, centre, off, full=ENTER_FULL, ramp=ENTER_RAMP):
    """The closed path `path` moved `off` units along the lane's `_lane_normal` (signed) about the path's point nearest `centre`:
    fully within `full` along the path, then less, linearly, to nothing `ramp` farther (as `spot_path`). The shift is by `off`, not
    to a line `off` from the lane's centre: the reverse pit path (a normal run read backwards) wanders about 2 units either side of
    the centre, so the car's offset at the trigger is measured, not assumed (a shift to the line was tried in scratch: it moves the
    path's points on the road before the lane's exit too, and the car missed the stop)."""
    n = len(path)
    k = min(range(n), key=lambda i: math.dist(path[i], centre))
    arc = {k: 0.0}
    for step in (1, -1):
        i, s = k, 0.0
        while s < full + ramp:
            j = (i + step) % n
            s += math.dist(path[i], path[j])
            arc[j], i = s, j
    out = list(path)
    for i, s in arc.items():
        w = 1.0 if s <= full else max(0.0, 1.0 - (s - full) / ramp)
        if w:
            x, z = path[i]
            p, q = min(zip(lane, lane[1:]), key=lambda pq: _seg_dist((x, z), *pq))
            nx, nz = _lane_normal(p, q)
            out[i] = (x + off * w * nx, z + off * w * nz)
    return out


@dataclass
class Course:
    """What the session knows of a converted entry: its directory record, line 6 of the normal entry ((x, z) in lap order), the
    pit lane's polyline from its mouth (`pitpaths.pit_lane`) and Task 1's trimmed rectangle (x0, x1, z0, z1) if it has one; (the
    fix wave) the normal entry's eight road lines (line 0 the centreline), the lane's tarmac slices ((x, z) polygons) and the
    built set's collision quads of the normal and the reverse pair ({index: (x, z) corners})."""
    entry: int
    record: object
    line6: list
    lane: list
    trim: tuple | None
    lines: list = field(default_factory=list)
    slices: list = field(default_factory=list)
    pair_quads: dict = field(default_factory=dict)

    def pair_middle(self, quad: int) -> tuple[float, float]:
        """The mean of the centres of quads `quad` and `quad` + 1."""
        cs = [(sum(x for x, _ in self.pair_quads[i]) / 4, sum(z for _, z in self.pair_quads[i]) / 4) for i in (quad, quad + 1)]
        return ((cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2)

    def on_lane_tarmac(self, x, z) -> bool:
        return any(_in_poly(p, x, z) for p in self.slices)

    def road_side(self, at) -> float:
        """+1 when the lane's `_lane_normal` at the point `at` points to the road (the centreline's nearest point), else -1."""
        p, q = min(zip(self.lane, self.lane[1:]), key=lambda pq: _seg_dist(at, *pq))
        nx, nz = _lane_normal(p, q)
        r = min(self.lines[0], key=lambda c: math.dist(c, at))
        return 1.0 if (r[0] - at[0]) * nx + (r[1] - at[1]) * nz > 0 else -1.0

    def tarmac_extent(self, at, side: float, step: float = 0.05) -> float:
        """How far the lane's tarmac slices reach from the lane's centre nearest `at` along `side` times its `_lane_normal`."""
        p, q = min(zip(self.lane, self.lane[1:]), key=lambda pq: _seg_dist(at, *pq))
        dx, dz = q[0] - p[0], q[1] - p[1]
        t = max(0.0, min(1.0, ((at[0] - p[0]) * dx + (at[1] - p[1]) * dz) / (dx * dx + dz * dz)))
        fx, fz = p[0] + t * dx, p[1] + t * dz
        nx, nz = _lane_normal(p, q)
        d = 0.0
        while self.on_lane_tarmac(fx + side * (d + step) * nx, fz + side * (d + step) * nz) and d < PIT_LANE_HALF_WIDTH:
            d += step
        return d


@dataclass(frozen=True)
class Stop:
    """Indices into a run's frames: the trigger (the first frame with PIT_HANDLER), the park (the first from it with the park flag),
    the release (the first after it without PIT_HANDLER); None for what did not happen. The park flag is set from Alpine's PIT START
    to its first stop's trigger, which clears it."""
    trigger: int
    park: int | None
    release: int | None


@dataclass
class PitRun:
    """One MAME run: `kind` is "normal" (the normal pit path), "reverse" (the reverse pit path), "plain" (line 6 read backwards),
    "long" (the reverse pit path for LONG_SECONDS), or "spot_centre" / "spot_west" (Diablo Canyon in reverse on the set without the
    variants' pits, the reverse pit path on the lane's centre or SPOT_WEST to its west through Task 1's spot, SPOT_SECONDS), or
    (Task 5) "nocrew" / "nocrew_reverse" (the normal / reverse run on the set without Task 5's crew change, `PitSession.nocrew`);
    SECONDS of game time, REVERSE_SECONDS for "reverse" and "nocrew_reverse". `pair` and `box` are the served record's (the
    variant's in reverse; None on the set without the variants' pits). Runs of the crew tests' courses (CREW_REFERENCE) carry
    crewdraw_log.lua's log (`crew_draw`)."""
    entry: int
    kind: str
    wd: Path
    frames: list[PitFrame]
    pair: tuple[int, int]
    box: tuple[float, float, float, int]
    green: int = field(init=False)

    def __post_init__(self):
        try:
            self.green = green_index(self.frames)                 # the clock's first count
        except ValueError as e:
            raise AssertionError(f"entry {self.entry} {self.kind} ({self.wd}): {e}") from e

    def stop(self, after: int | None = None) -> Stop | None:
        """The first stop whose trigger comes after index `after` (default: from the green)."""
        f = self.frames
        start = self.green if after is None else after + 1
        t = next((i for i in range(start, len(f)) if f[i].handler == PIT_HANDLER), None)
        if t is None:
            return None
        r = next((i for i in range(t, len(f)) if f[i].handler != PIT_HANDLER), None)
        p = next((i for i in range(t + 1, r if r is not None else len(f)) if f[i].flags & PARK_FLAG and not f[i - 1].flags & PARK_FLAG), None)
        return Stop(t, p, r)

    def race(self):
        return parse_race_log(self.wd / "race.txt")[0]

    def field_log(self):
        return parse_field(self.wd / "field.txt")

    def crew_draw(self):
        return parse_crew_draw_log(self.wd / "crew.txt")


class PitSession:
    """The session's built set and its pit runs (module cache `_SESSIONS`, keyed by the original set's path)."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        self.romset_zip, self.saturn_cue, self.base = romset_zip, saturn_cue, base
        self.out, self.conv = _seven(romset_zip, saturn_cue)
        self.build = _build(base, romset_zip, self.out)
        self.directory = decode_directory(self.out)
        self.courses: dict[int, Course] = {}
        self.runs: dict[tuple[int, str], PitRun] = {}
        self.failed: dict[tuple[int, str], BaseException] = {}
        self._bare = None
        self._nocrew = None
        self._lock = threading.Lock()

    @property
    def bare(self) -> Path:
        """The rom directory of the set made from the same conversions with every variant's pit quad and box None (as
        tests/test_reverse_build.py::test_the_reverse_pit_changes_only_the_variant_records makes it): no stop can start in a
        reverse race (`pitstops` grants 0 for the variant's 0xfffe); everything else is the session's set, the collision included."""
        if self._bare is None:
            from dataclasses import replace
            from vrtools.arcade.tencourse import ten_course_set
            from tests.test_tgp_build import _built
            rs = ten_course_set(_built(self.romset_zip, self.saturn_cue)[0],
                                [replace(c, reverse=replace(c.reverse, pit_quad=None, pit_box=None)) for c in self.conv])
            assert [e.reverse.entry.pit_quad for e in decode_directory(rs)[3:10]] == [None] * 7
            (self.base / "bare").mkdir()
            self._bare = _build(self.base / "bare", self.romset_zip, rs)
        return self._bare

    @property
    def nocrew(self) -> Path:
        """Task 5: the rom directory of the set made from the same conversions without Task 5's crew change (`ten_course_set(...,
        crew=False)`: the four crew spawn sites the original's, `figmirror` the start figures' only, every address the session
        set's). A normal race on it is Review Focus 4's baseline; a reverse race shows the game's own crew."""
        if self._nocrew is None:
            from vrtools.arcade.tencourse import ten_course_set
            from tests.test_tgp_build import _built
            rs = ten_course_set(_built(self.romset_zip, self.saturn_cue)[0], self.conv, crew=False)
            (self.base / "nocrew").mkdir()
            self._nocrew = _build(self.base / "nocrew", self.romset_zip, rs)
        return self._nocrew

    def course(self, entry: int) -> Course:
        if entry not in self.courses:
            rec = self.directory[entry]
            c = self.conv[entry - 3]
            assert c.entry.name == rec.name == PLANS[entry - 3].name
            lines = [[(p.x, p.z) for p in line] for line in road_lines(self.out, course_entry_at(self.out, rec.bank, rec.header_base))]
            lane, sat, slices = pit_lane(RomSet.from_zip(self.romset_zip), self.saturn_cue, PLANS[entry - 3], c.centreline)
            spot = wall_trim_of(sat)
            trim = spot.rect if spot is not None else None
            w = tgp_words(self.out)
            pool = slot_table(self.out)[rec.tgp_slot][1]
            quads = {i: [(x, z) for x, _, z in decode_quad(w, pool + QUAD_WORDS * i).corners]
                     for q in (rec.pit_quad, rec.reverse.entry.pit_quad) if q is not None for i in (q, q + 1)}
            self.courses[entry] = Course(entry, rec, lines[6], lane, trim, lines, slices, quads)
        return self.courses[entry]

    def _make(self, entry: int, kind: str) -> PitRun:
        c = self.course(entry)
        normal = kind in NORMAL_KINDS
        rec = c.record if normal else c.record.reverse.entry
        spot = kind.startswith("spot_")
        wd = self.base / kind / f"entry{entry}"
        wd.mkdir(parents=True, exist_ok=True)
        if normal:
            path = normal_pit_path(c.line6, c.lane)
        elif kind == "plain":
            path = reverse_points(c.line6)
        elif kind == "edge":
            path = reverse_points(c.lines[EDGE_LINE])
        else:
            try:
                path = reverse_pit_path(self.run(entry, "normal").frames, c.line6)
            except ValueError as e:
                raise AssertionError(f"entry {entry} {kind}: the normal run's trajectory: {e}") from e
            if kind == "spot_west":
                path = spot_path(path, c.lane, c.trim, SPOT_WEST)
            if kind.startswith("enter_"):
                path = shift_path(path, c.lane, c.pair_middle(rec.pit_quad), _enter_offset(c, rec.pit_quad, kind))
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_COLLISION_LOG": str(wd / "c.txt"),
               "VR_AUTOPILOT": str(write_centreline(wd / "path.csv", path)), "VR_PIT_LOG": str(wd / "pit.txt"),
               "VR_RACE_LOG": str(wd / "race.txt"),
               "VR_FIELD_LOG": str(wd / "field.txt"), "VR_FIELD_FROM": "1600", "VR_FIELD_TO": "999999", "VR_FIELD_EVERY": "2",
               "VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_READ": f"{WARNING_READS},{CLOCK_READS}", "VR_TRACE_FROM": "0",
               "VR_TRACE_FINE": "1",
               "VR_SNAPS": "1"}
        if not normal:
            env["VR_DIRECTION"] = "1"                        # autoplay.lua answers REVERSE on the COURSE DIRECTION screen
        if kind in ("reverse", "long", "nocrew_reverse") or spot or kind.startswith(("enter_", "reverse_")):
            env["VR_AUTOPILOT_AHEAD"] = str(REVERSE_AHEAD)
        if spot:
            env["VR_AUTOPILOT_LOOKAHEAD"] = str(SPOT_LOOKAHEAD)
        if kind.rpartition("_")[2] in DAMAGE:                                 # the fix wave: a work state forced
            env["VR_PIT_DAMAGE"] = str(DAMAGE[kind.rpartition("_")[2]][0])
        if (entry, kind) in CREW_LOGGED:                                      # Task 5
            lay = directory_layout()
            env["VR_CREW_DRAW_LOG"] = str(wd / "crew.txt")
            env["VR_CREW_DRAW_PCS"] = f"{lay[CREW_ROUTINES[0]]:x}-{lay[CREW_ROUTINES[-1]] + len(_routine(CREW_ROUTINES[-1])):x}"
        seconds = {"long": LONG_SECONDS, "reverse": REVERSE_SECONDS, "nocrew_reverse": REVERSE_SECONDS}.get(kind, SPOT_SECONDS if spot else SECONDS)
        rom = self.bare if spot else self.nocrew if kind.startswith("nocrew") else self.build
        run_mame(LUA_DIR / "autoplay.lua", seconds, wd, rom, env=env, timeout=3600)
        pair = (rec.pit_quad, rec.pit_quad + 1) if not spot else (None, None)
        return PitRun(entry, kind, wd, parse_pit_log(wd / "pit.txt"), pair, rec.pit_box if not spot else None)

    def run(self, entry: int, kind: str) -> PitRun:
        """The run, made now if no wave made it; a run that failed in a wave raises again (it is not made a second time)."""
        w = (entry, kind)
        if w in self.failed:
            raise AssertionError(f"the run entry {entry} {kind} failed earlier in this session: {self.failed[w]!r}") from self.failed[w]
        if w not in self.runs:
            try:
                self.runs[w] = self._make(entry, kind)
            except Exception as e:
                self.failed[w] = e
                raise
        return self.runs[w]

    def prefetch(self, wanted):
        """Make the runs `wanted` ((entry, kind) pairs) not yet made, in parallel: first the normal and plain ones (a reverse,
        long or spot run's path needs its course's normal run), then the others. Each run is stored as it completes; a run that
        fails is recorded in `failed` (`run` raises it again) and the others are kept."""
        wanted = set(wanted) | {(e, "normal") for e, k in wanted if k not in ("plain", "edge")}
        for e, _ in wanted:
            self.course(e)                                   # the placements and the set without pits, once, outside the threads
        if any(k.startswith("spot_") for _, k in wanted):
            self.bare
        if any(k.startswith("nocrew") for _, k in wanted):
            self.nocrew

        def make(w):
            try:
                r = self._make(*w)
            except Exception as e:                           # noqa: BLE001 (kept for the test that asks for the run)
                with self._lock:
                    self.failed[w] = e
                return
            with self._lock:
                self.runs[w] = r
        for wave in (FIRST_WAVE, None):                     # None: every other kind (their paths read the normal runs)
            todo = sorted(w for w in wanted if (w[1] in FIRST_WAVE) == (wave is not None) and w not in self.runs and w not in self.failed)
            with ThreadPoolExecutor(max_workers=MAME_WORKERS) as ex:
                list(ex.map(make, todo))


_SESSIONS: dict[str, PitSession] = {}
# The runs each test of this module asks for: test name -> (kinds, entry for a test not parametrized by `entry`). The fixture makes
# the runs of the collected tests named here in its parallel waves; a new test in this file (Task 5's, the fix wave's) must be added
# here to have its runs made in the waves, or else each run it asks for is made alone when it asks (`PitSession.run`). Kinds may be
# a function of the test's parameters (a dict).
_KINDS = {"test_a_normal_pit_stop": (("normal",), None), "test_a_reverse_pit_stop": (("reverse",), None),
          "test_the_plain_reverse_line_never_stops": (("plain",), None), "test_two_stops_and_no_third": (("long",), AMAZON_FALLS),
          "test_diablos_trimmed_spot_is_drivable_by_the_player": (("spot_centre", "spot_west"), DIABLO),
          "test_the_crew_stands_round_the_car_in_reverse": (lambda p: (p["kind"], p["reference"]), None),
          "test_the_crews_animation_is_mirrored_in_reverse": (lambda p: (p["kind"], p["reference"]), None),
          "test_a_normal_stops_crew_is_unchanged": (("normal", "nocrew"), None),
          "test_the_trimmed_spot_is_passed_in_the_normal_direction": (("normal",), DIABLO),
          "test_the_pit_side_edge_line_never_stops": (("edge",), None),
          "test_a_reverse_stop_entered_off_the_lanes_centre": (lambda p: (p["kind"],), None)}


def _wanted(items) -> set[tuple[int, str]]:
    """The (entry, kind) runs the collected `items` ask for: only the tests named in `_KINDS` count; any other item (another
    module's, parametrized or not) is skipped without reading its parameters. ValueError for a test named in `_KINDS` without a
    fixed entry and without an `entry` parameter."""
    wanted = set()
    for item in items:
        name = getattr(item, "originalname", item.name)
        if name not in _KINDS:
            continue
        kinds, entry = _KINDS[name]
        params = getattr(getattr(item, "callspec", None), "params", {})
        if entry is None:
            if "entry" not in params:
                raise ValueError(f"{item.name}: named in _KINDS without a fixed entry, but it has no `entry` parameter")
            entry = params["entry"]
        wanted |= {(entry, k) for k in (kinds(params) if callable(kinds) else kinds)}
    return wanted


def _routine(name: str) -> bytes:
    """The direction routine `name` as the session's set has it."""
    from vrtools.arcade.direction import direction_routines
    lay = directory_layout()
    return direction_routines(lay[name], lay["pitbox"])[name]


@pytest.fixture
def pit_runs(request, romset_zip, saturn_cue, tmp_path_factory) -> PitSession:
    """The session's PitSession; at its first use it makes, in parallel, every run the session's collected tests of this module
    ask for (by test name and `entry`; another test's runs are made when it asks, `PitSession.run`)."""
    key = str(romset_zip)
    if key not in _SESSIONS:
        s = PitSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("pit"))
        s.prefetch(_wanted(request.session.items))
        _SESSIONS[key] = s                                   # registered once its waves are made (a failed run is in `failed`)
    return _SESSIONS[key]


def _report(run: PitRun, s: Stop) -> dict:
    """The stop's numbers as the task's report lists them."""
    f = run.frames
    t, p, r = s.trigger, s.park, s.release
    lap = next((g.frame for g in f[t:] if g.lap > f[t].lap), None)
    return {"trigger": f[t].frame, "quad": f[t].quad, "speed": f[t].speed, "to box": round(math.dist((f[t].x, f[t].z), (run.box[0], run.box[2])), 1),
            "park": f[p].frame if p is not None else None, "release": f[r].frame if r is not None else None,
            "clock": (f[t].clock, f[r].clock if r is not None else None), "stops": (f[t - 1].stops, f[r].stops if r is not None else None),
            "next lap": lap}


def _assert_a_stop(run: PitRun, s: Stop | None, stops_before: int, since: int | None = None):
    """A stop as recon §7 lists it: the trigger on the first frame after the car is first logged on the served pair, the car parked
    at the served box (x, z within 0.01, the yaw its heading) until the release, release − park = PIT_WORK_FRAMES, the clock
    standing from the trigger to the release and then PIT_EXTEND more, one stop spent. `since`: the index the car's way to the pair
    is searched from (default the green)."""
    f = run.frames
    assert s is not None, (f"entry {run.entry} {run.kind}: no trigger", run.pair, [(g.frame, g.quad) for g in f[run.green::200]])
    t, p, r = s.trigger, s.park, s.release
    on_pair = next((i for i in range(run.green if since is None else since, len(f)) if f[i].quad in run.pair), None)
    assert on_pair is not None, (f"entry {run.entry} {run.kind}: the car is never logged on the pair {run.pair}", f[t])
    assert f[t].quad in run.pair and 0 < f[t].frame - f[on_pair].frame <= LOGIC_STEP, (f[on_pair], f[t])
    assert p is not None and r is not None, (f"entry {run.entry} {run.kind}: the car never parked or was never released", s, f[t], f[-1])
    bx, _, bz, heading = run.box
    assert abs(f[p].x - bx) <= 0.01 and abs(f[p].z - bz) <= 0.01 and f[p].yaw == heading, (f[p], run.box)
    assert all(abs(g.x - bx) <= 0.01 and abs(g.z - bz) <= 0.01 and g.yaw == heading for g in f[p:r]), run.box
    assert f[r].frame - f[p].frame == PIT_WORK_FRAMES, (f[p].frame, f[r].frame)
    assert {g.clock for g in f[t:r]} == {f[t].clock} and f[r].clock == f[t].clock + PIT_EXTEND, (f[t].clock, f[r].clock)
    assert f[t - 1].stops == stops_before and all(g.stops == stops_before - 1 for g in f[t:r + 1]), (f[t - 1], f[r])


@pytest.mark.parametrize("entry", list(COURSES))
def test_a_normal_pit_stop(pit_runs, entry):
    """The baseline: a normal race on the normal pit path (line 6 with the lane spliced in, `pitpaths.normal_pit_path`): +0x1bf = 2
    at the green, the first stop as `_assert_a_stop` with the normal entry's pair (q, q + 1) and box. Its trajectory is the
    reverse path's (`pitpaths.reverse_pit_path`)."""
    run = pit_runs.run(entry, "normal")
    f = run.frames
    assert f[run.green].stops == STOPS_GRANTED, f[run.green]
    s = run.stop()
    print("NORMAL STOP", PLANS[entry - 3].name, "pair", run.pair, "box", run.box, "green", f[run.green].frame,
          _report(run, s) if s else None)
    _assert_a_stop(run, s, STOPS_GRANTED)


def _warning_reads(run: PitRun):
    """(frames with a read of the wrong-way warning, frames with a read of the clock) from the green on, in memtrace.lua's log
    (its frame f is the pit log's f + 1). The clock is read every race frame: its reads show the taps were installed and recorded
    through the run, so no warning read means none happened (WARNING_READS' own positive control is tests/test_reverse_build.py's
    warning test)."""
    from vrtools.arcade.trace import parse_trace
    lo, hi = (int(v, 16) for v in CLOCK_READS.split("-"))
    ev = [e for e in parse_trace(run.wd / "trace.log") if e.kind == "R" and e.frame >= run.frames[run.green].frame - 1]
    return sorted({e.frame for e in ev if not lo <= e.addr <= hi}), sorted({e.frame for e in ev if lo <= e.addr <= hi})


def _left_lane(run: PitRun, lane, after: int) -> int | None:
    """The first index after `after` whose position lies farther than PIT_LANE_HALF_WIDTH from the lane's polyline."""
    return next((i for i in range(after, len(run.frames)) if lane_distance(lane, run.frames[i].x, run.frames[i].z) > PIT_LANE_HALF_WIDTH), None)


GATE_SLACK = 5              # points: the race log's road point at a gate's clock rise lies from 1 before the gate (Pacific Coast's reverse
                            # gate 90 at 89, both laps) to 5 after it (Diablo Canyon's line, crossed in its pit lane: the lane's quads
                            # credit coarse points) in the scratch runs of 14 Nov; the gates lie 80 or more points apart


def _gate_of(point, gates, n):
    """The index of the gate within GATE_SLACK of road point `point` (None if none is)."""
    d = [abs((point - g + n // 2) % n - n // 2) for g in gates]
    return d.index(min(d)) if min(d) <= GATE_SLACK else None


def _fires(players):
    """(frame, road point) of every clock rise in the race log while the clock runs."""
    return [(b.frame, b.road_point) for a, b in zip(players, players[1:]) if b.clock > a.clock > 0]


def _progress(samples, n):
    """A car's road points unwrapped: the progress from its first sample to its last."""
    cum = 0
    for a, b in zip(samples, samples[1:]):
        d = b.point - a.point
        cum += d - n if d > n // 2 else d + n if d < -n // 2 else d
    return cum


@pytest.mark.parametrize("entry", list(COURSES))
def test_a_reverse_pit_stop(pit_runs, entry):
    """The reverse race on the reverse pit path (the session's normal pit run read backwards joined to line 6 read backwards,
    `pitpaths.reverse_pit_path`; VR_AUTOPILOT_AHEAD = REVERSE_AHEAD): +0x1bf = 2 at the green and the first stop as
    `_assert_a_stop` with the variant's pair and box, the box heading the normal one + 0x8000; no trigger from the release until
    the car has left the lane (Review Focus 1); the lap counted after the trigger, and two or more of the clock's rises after the
    release and before the next stop's trigger, each at a gate (`_gate_of`) and the gates in their order from the first ahead of the
    car at the release (a gate crossed
    under the pit autopilot is paid at the release + 2 frames, which is left out: recon §2); no read of the wrong-way warning from
    the green on (memtrace.lua's taps, WARNING_READS); the 15 opponents all advance during the stop (fieldtrace.lua). On Diablo
    Canyon, Task 1's trimmed spot (`_assert_the_trimmed_spot_is_driven`)."""
    from vrtools.arcade.trace import parse_trace
    course = pit_runs.course(entry)
    run = pit_runs.run(entry, "reverse")
    f = run.frames
    n = COURSES[entry]
    name = PLANS[entry - 3].name
    assert run.box[3] == (course.record.pit_box[3] + 0x8000) & 0xFFFF, (run.box, course.record.pit_box)
    assert f[run.green].stops == STOPS_GRANTED, f[run.green]
    s = run.stop()
    rep = _report(run, s) if s else None
    print("REVERSE STOP", name, "pair", run.pair, "box", run.box, "green", f[run.green].frame, rep)
    _assert_a_stop(run, s, STOPS_GRANTED)
    t, r = s.trigger, s.release
    out = _left_lane(run, course.lane, r)
    assert out is not None, ("the car never left the lane after the release", f[r], f[-1])
    assert all(g.handler != PIT_HANDLER and g.stops == STOPS_GRANTED - 1 for g in f[r:out + 1]), f[out]
    # the next lap and the gates after the release
    assert rep["next lap"] is not None, ("no lap after the stop", f[t].lap, f[-1])
    nl = next(g for g in f[t:] if g.lap > f[t].lap)
    assert nl.lap == f[t].lap + 1, (f[t].lap, nl)                              # the lap after the stop: one more
    gates = decode_race_blob(pit_runs.out, course.record.reverse.entry.race).checkpoints
    players = run.race()
    rp = next((p.road_point for p in players if p.frame == f[r].frame), None)
    assert rp is not None, f"entry {entry} reverse: no race-log frame {f[r].frame} (the release)"
    nxt = run.stop(r)                                                           # the next stop's rises are its own
    until = f[nxt.trigger].frame if nxt else f[-1].frame + 1
    fires = [(fr, p, _gate_of(p, gates, n)) for fr, p in _fires(players) if f[r].frame + 2 * LOGIC_STEP < fr < until]
    k = min(range(len(gates)), key=lambda j: (gates[j] - rp - 1) % n)          # the first gate ahead of the car at the release
    print("GATES", name, "release point", rp, "gates", gates, "fires after the release (frame, point, gate)", fires, "first expected", gates[k])
    assert len(fires) >= 2 and [g for _, _, g in fires] == [(k + i) % len(gates) for i in range(len(fires))], (fires, gates[k])
    # the wrong-way warning and the field
    reads, control = _warning_reads(run)
    cars: dict[int, list] = {}
    for x in run.field_log():
        if f[t].frame <= x.frame + 1 <= f[r].frame and x.car:
            cars.setdefault(x.car, []).append(x)
    advance = {car: _progress(v, n) for car, v in sorted(cars.items())}
    print("WRONG WAY reads", len(reads), reads[:8], "clock reads (the taps' control): frames", len(control),
          (control[0], control[-1]) if control else None, "OPPONENTS during the stop", advance)
    assert control and control[0] <= f[run.green].frame + 60 and control[-1] >= f[-1].frame - 60, (len(control), control[:2], control[-2:])
    assert not reads, reads[:8]
    assert len(advance) == 15 and all(a > 0 for a in advance.values()), advance
    if entry == DIABLO:
        _assert_the_trimmed_spot_is_driven(pit_runs, course, run, s)


def _assert_the_trimmed_spot_is_driven(pit_runs, course, run, s):
    """Diablo Canyon (Task 1's trim, PIT_LANE_WALL_TRIMS): the rectangle covers the lane's west half up to its centre line, where
    the recon's car hit the wall quad on the centre line (recon §3 item 3). On the way to the box (the green to the release) the
    car passes through the rectangle and, over its z range, keeps within SPOT_CENTRE of the lane's centre line (no detour east), with
    no wall hit within 5 units of it (the smoke counter rising from 0); the reverse path keeps the centre there too."""
    assert course.trim is not None
    x0, x1, z0, z1 = course.trim
    f = run.frames[run.green:s.release + 1]
    near = lambda x, z: lane_distance(course.lane, x, z) <= PIT_LANE_HALF_WIDTH
    band = [g for g in f if z0 <= g.z <= z1 and near(g.x, g.z)]
    inside = [g for g in band if x0 <= g.x <= x1]
    dists = [lane_distance(course.lane, g.x, g.z) for g in band]
    hits = [b.frame for a, b in zip(f, f[1:]) if b.smoke > 0 == a.smoke and x0 - 5 <= b.x <= x1 + 5 and z0 - 5 <= b.z <= z1 + 5]
    path = [tuple(map(float, line.split(","))) for line in (run.wd / "path.csv").read_text().split()]
    on_path = [lane_distance(course.lane, x, z) for x, z in resample(path, 1.0) if z0 <= z <= z1 and near(x, z)]   # 10-unit points
                                                                                     # would step over the 12.5-unit band
    handlers = sorted({hex(g.handler) for g in band})
    print("DIABLO SPOT", course.trim, "frames in its z range", len(band), "inside it", [(g.frame, round(g.x, 2), round(g.z, 2)) for g in inside],
          "least / most from the lane centre", (round(min(dists), 2), round(max(dists), 2)) if dists else None, "handlers", handlers,
          "wall hits", hits, "the path's most", round(max(on_path), 2) if on_path else None)
    assert inside and band and max(dists) <= SPOT_CENTRE and not hits, (len(inside), dists, hits)
    assert on_path and max(on_path) <= SPOT_CENTRE, on_path


@pytest.mark.parametrize("entry", list(COURSES))
def test_the_plain_reverse_line_never_stops(pit_runs, entry):
    """Review Focus 3: a reverse race on line 6 read backwards passes the normal exit on the road (within PIT_LANE_HALF_WIDTH of
    the line 6 point nearest the lane's exit) and never stops: the handler never PIT_HANDLER, +0x1bf 2 from the green to the end."""
    course = pit_runs.course(entry)
    run = pit_runs.run(entry, "plain")
    f = run.frames[run.green:]
    ex = min(course.line6, key=lambda p: math.dist(p, course.lane[-1]))
    passes = [g.frame for a, g in zip(f, f[1:]) if math.dist((g.x, g.z), ex) <= PIT_LANE_HALF_WIDTH < math.dist((a.x, a.z), ex)]
    on_pair = sorted({g.quad for g in f if g.quad in run.pair})
    print("PLAIN", PLANS[entry - 3].name, "pair", run.pair, "exit passes", passes, "on the pair", on_pair, "stops", sorted({g.stops for g in f}),
          "handlers", sorted({hex(g.handler) for g in f}))
    assert passes, (ex, [(g.frame, g.x, g.z) for g in f[::300]])
    assert all(g.handler != PIT_HANDLER and g.stops == STOPS_GRANTED for g in f), next(g for g in f if g.handler == PIT_HANDLER or g.stops != STOPS_GRANTED)


def test_two_stops_and_no_third(pit_runs):
    """Review Focus 2: Amazon Falls in reverse for LONG_SECONDS on the reverse pit path: the first stop (2 -> 1), then the second
    at the next pass (1 -> 0, as `_assert_a_stop`), then a third pass over the pair after the car has left the lane starts nothing
    (the handler never PIT_HANDLER, +0x1bf stays 0 to the end)."""
    course = pit_runs.course(AMAZON_FALLS)
    run = pit_runs.run(AMAZON_FALLS, "long")
    f = run.frames
    first = run.stop()
    _assert_a_stop(run, first, STOPS_GRANTED)
    left = _left_lane(run, course.lane, first.release)
    second = run.stop(left)
    print("LONG first", _report(run, first), "second", _report(run, second) if second else None)
    _assert_a_stop(run, second, STOPS_GRANTED - 1, since=left)
    out = _left_lane(run, course.lane, second.release)
    assert out is not None, f[-1]
    third = [g.frame for a, g in zip(f[out:], f[out + 1:]) if g.quad in run.pair and a.quad not in run.pair]
    print("LONG third pass over the pair at", third, "last frame", f[-1].frame, "stops", f[-1].stops)
    assert third, ("no third pass over the pair", f[out], f[-1])
    assert all(g.handler != PIT_HANDLER and g.stops == 0 for g in f[second.release:]), next(
        g for g in f[second.release:] if g.handler == PIT_HANDLER or g.stops != 0)


# --- Task 5: the crew turned half a turn about the box in reverse (decision P2, the lead's reading of Pascal's 'Ok') ----------------

def _crew_stops(pit_runs, entry, kind="reverse", reference=None):
    """(reverse run, its stop, reference run, its stop) for a crew test: the reverse run `kind` and its `reference` (default
    CREW_REFERENCE's); both stops parked and released, and in the same pit work state (+0x191 at the trigger: 1, 8, 11 or 14), on
    a forced run (DAMAGE) the state its poke picks."""
    run, ref = pit_runs.run(entry, kind), pit_runs.run(entry, reference or CREW_REFERENCE[entry])
    s, r = run.stop(), ref.stop()
    for x, st in ((run, s), (ref, r)):
        assert st is not None and st.park is not None and st.release is not None, (f"entry {entry} {x.kind}: no complete stop", st)
    assert run.frames[s.trigger].state == ref.frames[r.trigger].state, (
        f"entry {entry}: work state {run.frames[s.trigger].state} in {kind}, {ref.frames[r.trigger].state} in {ref.kind}")
    if kind.rpartition("_")[2] in DAMAGE:
        assert run.frames[s.trigger].state == DAMAGE[kind.rpartition("_")[2]][1], (kind, run.frames[s.trigger])
    assert s.release - s.park == r.release - r.park, (s, r)
    return run, s, ref, r


CREW_IDS = [f"{e}-{k}" for e, k, _ in CREW_CASES]


@pytest.mark.parametrize("entry, kind, reference", CREW_CASES, ids=CREW_IDS)
def test_the_crew_stands_round_the_car_in_reverse(pit_runs, entry, kind, reference):
    """Every CREW_EVERY frames from the park to the release, each crew object of the reverse stop stands at the reference stop's
    same object reflected through the box: x' = 2·bx − x, z' = 2·bz − z within CREW_TOL, the reference's offset from its own box
    taken to the reverse run's box (the same box but on Metropolis, whose reverse box lies 40 units deeper), and its heading the
    reference's + 0x8000. The reference (CREW_REFERENCE) is the normal stop on Alpine, Amazon Falls and Diablo Canyon (work state 1,
    1, 14: five, five and six objects) and on Metropolis the reverse stop without Task 5's crew change (work state 14, six objects);
    (the fix wave) on Amazon Falls also work states 8 and 11, forced by the damage flags (DAMAGE) on both the reverse and the normal
    run. The stored positions include each ended animation's root offset (0xff6a14, mirrored by `figrootx` / `figrootz`)."""
    run, s, ref, r = _crew_stops(pit_runs, entry, kind, reference)
    f, g = run.frames, ref.frames
    bx, _, bz, _ = run.box
    gx, _, gz, _ = ref.box
    n = 5 if f[s.trigger].state == 1 else 6
    worst, frames = 0.0, 0
    for k in range(0, s.release - s.park, CREW_EVERY):
        a, b = f[s.park + k], g[r.park + k]
        assert len(a.crew) == len(b.crew) == n, (entry, k, len(a.crew), len(b.crew))
        for i, ((x, z, h), (x0, z0, h0)) in enumerate(zip(a.crew, b.crew)):
            want = (bx - (x0 - gx), bz - (z0 - gz))                  # = 2·bx − x0 when the boxes are the same
            d = max(abs(x - want[0]), abs(z - want[1]))
            worst = max(worst, d)
            assert d <= CREW_TOL and h == (h0 + 0x8000) & 0xFFFF, (entry, k, i, (x, z, hex(h)), want, hex(h0))
        frames += 1
    print("CREW", PLANS[entry - 3].name, kind, "reference", ref.kind, "work state", f[s.trigger].state, "objects", n, "frames compared", frames,
          "park", (f[s.park].frame, g[r.park].frame), "boxes", (run.box, ref.box), "largest difference from the reflection", round(worst, 4))


def _pushes(run, s):
    """{(frames from the park, crew object): [(routine, word), ...]} of crewdraw_log.lua from the park to the release, the routine
    named from the PC (CREW_ROUTINES' spans in the session's layout)."""
    lay = directory_layout()
    spans = [(lay[name], lay[name] + len(_routine(name)), name) for name in CREW_ROUTINES]
    park, release = run.frames[s.park].frame, run.frames[s.release].frame
    out: dict[tuple[int, int], list] = {}
    for p in run.crew_draw():
        if park <= p.frame < release:
            name = next(nm for lo, hi, nm in spans if lo <= p.pc < hi)
            out.setdefault((p.frame - park, p.crew), []).append((name, p.word))
    return out


def _mirrored(name: str, word: int) -> int:
    """What a mirrored crew object pushes where the unmirrored one pushes `word`: a root offset (float) with its sign bit flipped,
    a rotation (a halfword sign-extended to the word) negated."""
    if name in ("figrootx", "figrootz"):
        return word ^ 0x80000000
    return -(word - (1 << 32) if word & 0x80000000 else word) & 0xFFFFFFFF


@pytest.mark.parametrize("entry, kind, reference", CREW_CASES, ids=CREW_IDS)
def test_the_crews_animation_is_mirrored_in_reverse(pit_runs, entry, kind, reference):
    """The animation, not only the stored positions: on every frame from the park to the release, each crew object of the reverse
    stop pushes to the TGP through the figure routines (crewdraw_log.lua: the root offset's x and z at the draw, 0xff5e13 /
    0xff5e1f, and where an ended animation adds it to the position, 0xff6a18 / 0xff6a2c; the body's rotations about the horizontal
    axes, 0xff6c25 / 0xff6c41) the same words in the same order as the reference stop's same object (CREW_REFERENCE), mirrored: each
    root offset negated (its sign bit) and each rotation negated. The vertical rotation and the heading's push are not through a
    routine (the heading is the stored one, + 0x8000: the positions test). The cases: CREW_CASES."""
    run, s, ref, r = _crew_stops(pit_runs, entry, kind, reference)
    mine, theirs = _pushes(run, s), _pushes(ref, r)
    counts = {name: sum(1 for v in theirs.values() for nm, _ in v if nm == name) for name in CREW_ROUTINES}
    moving = {name: sum(1 for v in theirs.values() for nm, w in v if nm == name and w & 0x7FFFFFFF) for name in CREW_ROUTINES}
    print("CREW PUSHES", PLANS[entry - 3].name, kind, "reference", ref.kind, "frames with pushes", len({k for k, _ in theirs}),
          "pushes per routine", counts, "non-zero", moving, "reverse keys", len(mine), "reference keys", len(theirs))
    assert all(moving.values()), moving                              # every routine pushes non-zero words: the comparison has teeth
    assert sorted(mine) == sorted(theirs), (sorted(set(mine) ^ set(theirs))[:8])
    for key, pushes in theirs.items():
        want = [(nm, _mirrored(nm, w)) for nm, w in pushes]
        assert mine[key] == want, (entry, key, [(nm, hex(w)) for nm, w in mine[key]][:6], [(nm, hex(w)) for nm, w in want][:6])


@pytest.mark.parametrize("entry", CREW_UNCHANGED)
def test_a_normal_stops_crew_is_unchanged(pit_runs, entry):
    """Review Focus 4: Task 5's crew change does not reach a race with the flag 0. The normal run on the session's set and on the
    set without Task 5's crew change (`PitSession.nocrew`: the four sites the original's, `figmirror` the figures' only, every
    address the same) give pit logs identical line for line (the player and every crew object's x, z, heading on every frame) and
    identical crewdraw_log.lua logs (what the crew's animation pushes through the figure routines during the stop)."""
    run, base = pit_runs.run(entry, "normal"), pit_runs.run(entry, "nocrew")
    s = run.stop()
    assert s is not None and s.park is not None and s.release is not None, s
    lines = {k: (x.wd / "pit.txt").read_text().splitlines() for k, x in (("set", run), ("nocrew", base))}
    draws = {k: (x.wd / "crew.txt").read_text().splitlines() for k, x in (("set", run), ("nocrew", base))}
    crew_frames = sum(1 for g in run.frames if g.crew)
    print("UNCHANGED", PLANS[entry - 3].name, "pit log lines", {k: len(v) for k, v in lines.items()}, "frames with crew", crew_frames,
          "crew pushes", {k: len(v) for k, v in draws.items()}, "stop", _report(run, s))
    assert crew_frames > PIT_WORK_FRAMES and len(draws["set"]) > 1000
    for what, logs in (("pit log", lines), ("crew pushes", draws)):
        a, b = logs["set"], logs["nocrew"]
        assert a == b, (what, len(a), len(b), next(((i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y), None))



# --- the fix wave after the final review --------------------------------------------------------------------------------------

def _smoke_rises(frames) -> list:
    """The frames on which the smoke counter rises from 0 (a wall hit), as (frame, x, z)."""
    return [(b.frame, round(b.x, 2), round(b.z, 2)) for a, b in zip(frames, frames[1:]) if b.smoke > 0 == a.smoke]


def test_the_trimmed_spot_is_passed_in_the_normal_direction(pit_runs):
    """Final review (Minor 1): the normal Diablo Canyon run (`test_a_normal_pit_stop`'s) drives out of the lane after the release
    and passes Task 1's spot's z band: over its first pass from SPOT_MARGIN of z before the band to SPOT_MARGIN after it (near the
    lane) no wall is hit (the smoke counter never rises from 0). Where it passes is printed: in the scratch runs of 14 Nov it ran
    0.7-2.5 units east of the rectangle (its east side, x -388.0, is the old wall's edge plus 0.9), so it passes beside the trimmed
    footprint, not through it: the trim itself is driven through only by the reverse runs (`test_a_reverse_pit_stop`, the spot
    runs)."""
    course = pit_runs.course(DIABLO)
    run = pit_runs.run(DIABLO, "normal")
    s = run.stop()
    assert s is not None and s.release is not None, s
    x0, x1, z0, z1 = course.trim
    f = run.frames
    near = lambda g: lane_distance(course.lane, g.x, g.z) <= PIT_LANE_HALF_WIDTH
    idx = [i for i in range(s.release, len(f)) if z0 - SPOT_MARGIN <= f[i].z <= z1 + SPOT_MARGIN and near(f[i])]
    assert idx, ("the normal car never passes the spot after the release", f[s.release], f[-1])
    first = [idx[0]]
    for i in idx[1:]:
        if i - first[-1] > LOGIC_STEP:
            break
        first.append(i)
    window = f[first[0] - 1:first[-1] + 1]
    band = [g for g in window if z0 <= g.z <= z1]
    inside = [g for g in band if x0 <= g.x <= x1]
    west = _west(course.lane, band[0].x, band[0].z) if band else 1.0
    m = {"window": (window[0].frame, window[-1].frame), "band frames": len(band), "inside the rectangle": len(inside),
         "east of the rectangle by": (round(min(g.x - x1 for g in band), 2), round(max(g.x - x1 for g in band), 2)) if band else None,
         "west of the lane centre": (round(min(west * lane_offset(course.lane, g.x, g.z) for g in band), 2),
                                     round(max(west * lane_offset(course.lane, g.x, g.z) for g in band), 2)) if band else None,
         "speed": (min(g.speed for g in band), max(g.speed for g in band)) if band else None, "smoke rises": _smoke_rises(window)}
    print("NORMAL SPOT", m)
    assert band, m
    assert not m["smoke rises"], m


@pytest.mark.parametrize("entry", EDGE_COURSES)
def test_the_pit_side_edge_line_never_stops(pit_runs, entry):
    """Final review (I2, Review Focus 3 on the road's edge): a reverse race on road line EDGE_LINE read backwards (EDGE_OFFSET
    from the centreline, the outermost line on the pit lane's side at the normal exit) passes the normal exit on the road (within
    PIT_LANE_HALF_WIDTH of the line's point nearest the lane's exit) and never stops: the handler never PIT_HANDLER, +0x1bf 2 from
    the green to the end. Printed: the car's greatest distance from the centreline (line 0) toward the lane where it passes the
    reverse pair, and the pair quads' nearest corner to the centreline."""
    course = pit_runs.course(entry)
    run = pit_runs.run(entry, "edge")
    f = run.frames[run.green:]
    line = course.lines[EDGE_LINE]
    ex = min(line, key=lambda p: math.dist(p, course.lane[-1]))
    passes = [g.frame for a, g in zip(f, f[1:]) if math.dist((g.x, g.z), ex) <= PIT_LANE_HALF_WIDTH < math.dist((a.x, a.z), ex)]
    q = run.pair[0]
    mid = course.pair_middle(q)
    centre = course.lines[0] + course.lines[0][:1]
    cl = lambda x, z: min(_seg_dist((x, z), a, b) for a, b in zip(centre, centre[1:]))
    near = [g for g in f if math.dist((g.x, g.z), mid) <= 60.0]
    pair_near = min(cl(x, z) for i in run.pair for x, z in course.pair_quads[i])
    print("EDGE", PLANS[entry - 3].name, "line", EDGE_LINE, "pair", run.pair, "exit passes", passes, "on the pair",
          sorted({g.quad for g in f if g.quad in run.pair}), "stops", sorted({g.stops for g in f}),
          "handlers", sorted({hex(g.handler) for g in f}), "the car's most from the centreline within 60 of the pair",
          round(max(cl(g.x, g.z) for g in near), 2) if near else None, "the pair's nearest corner to the centreline", round(pair_near, 2))
    assert passes, (ex, [(g.frame, g.x, g.z) for g in f[::300]])
    assert all(g.handler != PIT_HANDLER and g.stops == STOPS_GRANTED for g in f), next(
        g for g in f if g.handler == PIT_HANDLER or g.stops != STOPS_GRANTED)


@pytest.mark.parametrize("entry, kind", ENTER_CASES, ids=[f"{e}-{k}" for e, k in ENTER_CASES])
def test_a_reverse_stop_entered_off_the_lanes_centre(pit_runs, entry, kind):
    """Final review (Minor 7): a reverse stop entered off the lane's centre (`shift_path` of the reverse pit path about the pair's
    middle, `_enter_offset`): ENTER_OFFSET toward the road or away from it on Diablo Canyon and Pacific Coast, and on Diablo the
    widest entry on each side (the lane's tarmac extent at the pair's middle less ENTER_MARGIN). The stop completes as
    `_assert_a_stop` checks, with no wall hit (the smoke counter rising from 0) from the trigger to the park. Printed: the path's
    shift, the car's offset from the lane's centre at the trigger (+ toward the road), whether its centre is on the lane's tarmac
    there, the tarmac's extent each side, and the pit steering's way to the box (its greatest distance from the straight line from
    the trigger to the box)."""
    course = pit_runs.course(entry)
    run = pit_runs.run(entry, kind)
    q = run.pair[0]
    mid = course.pair_middle(q)
    road = course.road_side(mid)
    shift = _enter_offset(course, q, kind) * road                                  # + toward the road
    s = run.stop()
    f = run.frames
    rep = _report(run, s) if s else None
    m = {"shift": round(shift, 2), "extent road / garage": (round(course.tarmac_extent(mid, road), 2), round(course.tarmac_extent(mid, -road), 2))}
    if s is not None:
        t = f[s.trigger]
        m.update({"trigger offset (+ road)": round(road * lane_offset(course.lane, t.x, t.z), 2), "at": (round(t.x, 2), round(t.z, 2)),
                  "on the lane's tarmac": course.on_lane_tarmac(t.x, t.z)})
        if s.park is not None:
            bx, bz = run.box[0], run.box[2]
            way = f[s.trigger:s.park + 1]
            m["pit steering: most off the straight line to the box"] = round(max(_seg_dist((g.x, g.z), (t.x, t.z), (bx, bz)) for g in way), 2)
            m["off the lane's tarmac on the way"] = [(g.frame, round(g.x, 2), round(g.z, 2)) for g in way if not course.on_lane_tarmac(g.x, g.z)][:6]
            m["smoke rises trigger..park"] = _smoke_rises(way)
    print("ENTER", PLANS[entry - 3].name, kind, rep, m)
    _assert_a_stop(run, s, STOPS_GRANTED)
    assert not m["smoke rises trigger..park"], m

# --- the paths on synthetic geometry (no ROM) ----------------------------------------------------------------------------------

def _circle(r, n=64, a0=0.0, a1=2 * math.pi):
    return [(r * math.cos(a0 + (a1 - a0) * k / n), r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n)]


def _frame(i, x, z, handler=0xFE8E18):
    return PitFrame(i, 0, handler, 0, 2, x, z, 0, 0.0, 9000 - i, 0, 0, ())          # the clock counting from the first frame


def _order(path, p):
    return min(range(len(path)), key=lambda i: math.dist(path[i], p))


def test_the_normal_pit_path_splices_the_lane_into_line_6():
    """`normal_pit_path`: a closed loop through every lane point, mouth before exit, its points PATH_STEP apart along it (up to 1.5
    steps where it closes: a last point nearer the first than half a step is dropped), whose road part runs round line 6 in its
    order (a circle of radius 100, the lane an arc of radius 80 over a quarter of it)."""
    from vrtools.mame.pitpaths import LINE_SKIP, PATH_STEP
    line = _circle(100.0)
    lane = _circle(80.0, 16, 0.2, 1.8)[1:]
    path = normal_pit_path(line, lane)
    assert all(math.dist(a, b) <= PATH_STEP + 1e-6 for a, b in zip(path, path[1:])) and math.dist(path[-1], path[0]) <= 1.5 * PATH_STEP
    assert all(lane_distance(path + path[:1], *p) < 1.0 for p in lane[1:])          # the resampling cuts the corner at the mouth
    mouth, exit_ = _order(path, lane[0]), _order(path, lane[-1])
    assert 0 < exit_ - mouth < len(path) // 2
    road = [min(range(len(line)), key=lambda k: math.dist(line[k], p)) for p in path if math.hypot(*p) > 95]
    assert sum((b - a) % len(line) <= LINE_SKIP + 1 for a, b in zip(road, road[1:])) >= len(road) - 2


def test_the_reverse_pit_path_reads_a_normal_run_backwards():
    """`reverse_pit_path`: from a normal run on the circle (road, the lane to the trigger, the pit autopilot to the box, the release,
    the lane out to the road again), a loop that passes every logged lane position, enters at the lane's exit end and reaches the
    box before the mouth, and runs round the road against line 6's order; frames under the pit handler before the green change
    nothing."""
    line = _circle(100.0)
    lane = _circle(80.0, 32, 0.2, 1.8)
    road_in = _circle(100.0, 64, -1.0, 0.2)[:-1]
    road_out = _circle(100.0, 64, 1.8, 3.0)
    frames, box = [], lane[len(lane) // 2]
    for p in road_in + lane[:6]:
        frames.append(_frame(len(frames), *p))
    for p in lane[6:len(lane) // 2 + 1] + [box] * 20:
        frames.append(_frame(len(frames), *p, handler=PIT_HANDLER))
    for p in lane[len(lane) // 2:] + road_out:
        frames.append(_frame(len(frames), *p))
    path = reverse_pit_path(frames, line)
    assert all(lane_distance(path + path[:1], *p) < 1.0 for p in lane[2:-2])
    exit_, at_box, mouth = _order(path, lane[-3]), _order(path, box), _order(path, lane[2])
    assert (at_box - exit_) % len(path) < (mouth - exit_) % len(path)
    road = [min(range(len(line)), key=lambda k: math.dist(line[k], p)) for p in path if math.hypot(*p) > 95 and abs(math.atan2(p[1], p[0]) - 1.0) > 2.2]
    assert sum((a - b) % len(line) <= 2 for a, b in zip(road, road[1:])) >= len(road) - 2
    # Alpine's PIT START runs under the pit handler before the green (the clock standing): the stop read is the first from the green
    start = [PitFrame(-1, 0, PIT_HANDLER, 6, 2, 0.0, 0.0, 0, 0.0, 9001, 0, 0, ())] * 5
    assert reverse_pit_path(start + frames, line) == path


def _assert_player_pass(course: Course, run: PitRun, path, west: bool = False) -> dict:
    """The player's own pass through Diablo Canyon's trimmed spot on a set where no stop can start: +0x1bf 0 at the green and the
    handler never PIT_HANDLER in the run; on its first pass the car has frames inside the rectangle, runs at SPOT_SPEED or more over
    the rectangle's z band (near the lane), and hits no wall (the smoke counter rising from 0) from SPOT_MARGIN of z before the band
    to SPOT_MARGIN after it. Over the band the centre line's car keeps within SPOT_PATH of its own path; the west line's (`west`,
    the final wave: against the lane's geometry, not a margin on its path) stays on the lane's tarmac slices and at least
    SPOT_WEST / 2 west of the lane's centre, in the half the old wall covered. Returns the numbers."""
    x0, x1, z0, z1 = course.trim
    f = run.frames
    near = lambda g: lane_distance(course.lane, g.x, g.z) <= PIT_LANE_HALF_WIDTH
    idx = [i for i in range(run.green, len(f)) if z0 <= f[i].z <= z1 and near(f[i])]
    assert idx, (f"entry {run.entry} {run.kind}: the car never reaches the spot's z band", f[-1])
    first = [idx[0]]
    for i in idx[1:]:
        if i - first[-1] > LOGIC_STEP:
            break
        first.append(i)
    a, b = first[0], first[-1]
    while a > run.green and z0 - SPOT_MARGIN <= f[a - 1].z <= z1 + SPOT_MARGIN and near(f[a - 1]):
        a -= 1
    while b + 1 < len(f) and z0 - SPOT_MARGIN <= f[b + 1].z <= z1 + SPOT_MARGIN and near(f[b + 1]):
        b += 1
    band = [f[i] for i in first]
    inside = [g for g in band if x0 <= g.x <= x1]
    closed = list(path) + [path[0]]
    to_path = [lane_distance(closed, g.x, g.z) for g in band]
    hits = [f[i].frame for i in range(a, b + 1) if f[i].smoke > 0 == f[i - 1].smoke]
    m = {"band": (band[0].frame, band[-1].frame), "inside": [(g.frame, round(g.x, 2), round(g.z, 2)) for g in inside],
         "speed": (min(g.speed for g in band), max(g.speed for g in band)), "to path": (round(min(to_path), 2), round(max(to_path), 2)),
         "to lane centre": (round(min(lane_distance(course.lane, g.x, g.z) for g in band), 2),
                            round(max(lane_distance(course.lane, g.x, g.z) for g in band), 2)),
         "west of the lane centre": (round(min(_west(course.lane, g.x, g.z) * lane_offset(course.lane, g.x, g.z) for g in band), 2),
                                     round(max(_west(course.lane, g.x, g.z) * lane_offset(course.lane, g.x, g.z) for g in band), 2)),
         "off the lane's tarmac": [g.frame for g in band if not course.on_lane_tarmac(g.x, g.z)],
         "window": (f[a].frame, f[b].frame), "smoke rises": hits, "stops at the green": f[run.green].stops,
         "pit handler frames": sum(1 for g in f if g.handler == PIT_HANDLER)}
    print("SPOT", run.kind, m)
    assert m["stops at the green"] == 0 and m["pit handler frames"] == 0, m
    assert inside, m
    if west:
        assert not m["off the lane's tarmac"] and m["west of the lane centre"][0] >= SPOT_WEST / 2, m
    else:
        assert max(to_path) <= SPOT_PATH, m
    assert not hits, m
    assert min(g.speed for g in band) >= SPOT_SPEED, m
    return m


def test_diablos_trimmed_spot_is_drivable_by_the_player(pit_runs):
    """Diablo Canyon in reverse on the set without the variants' pits (`PitSession.bare`: no stop can start), the Lua autopilot
    driving the reverse pit path up the lane through Task 1's spot, twice: on the lane's centre line ("spot_centre", the path as
    `pitpaths.reverse_pit_path` gives it) and SPOT_WEST to the lane's west through the rectangle ("spot_west", `spot_path`), where
    the old wall covered the lane's west half up to its centre line. Each pass as `_assert_player_pass`; the centre path keeps the
    lane's centre there within SPOT_CENTRE / 4, the west path lies SPOT_WEST to its west (signed: west of the centre) within
    SPOT_CENTRE / 4. Only the west run tells the trim: on main's build (out/p26play5) it hit the wall; the centre run at
    SPOT_LOOKAHEAD passes there on main's build too (0.08-0.49 units from the old quad's edges), so it shows only that the
    player's centre line is clean on the trimmed set."""
    course = pit_runs.course(DIABLO)
    assert course.trim is not None
    x0, x1, z0, z1 = course.trim
    for kind, off in (("spot_centre", 0.0), ("spot_west", SPOT_WEST)):
        run = pit_runs.run(DIABLO, kind)
        path = [tuple(map(float, line.split(","))) for line in (run.wd / "path.csv").read_text().split()]
        on = [_west(course.lane, x, z) * lane_offset(course.lane, x, z) for x, z in resample(path, 1.0)
              if z0 <= z <= z1 and lane_distance(course.lane, x, z) <= PIT_LANE_HALF_WIDTH]
        print("SPOT PATH", kind, "west of the lane centre over the band", (round(min(on), 2), round(max(on), 2)))
        assert on and all(abs(d - off) <= SPOT_CENTRE / 4 for d in on), on
        _assert_player_pass(course, run, path, west=kind == "spot_west")


def test_a_failed_run_keeps_the_others_and_is_not_made_again():
    """Review (Important 1): a run that fails in a wave is recorded; the wave's other runs are kept, and asking for the failed run
    raises again without making it a second time (no ROM: PitSession's waves over a stand-in `_make`)."""
    import threading as th
    s = PitSession.__new__(PitSession)
    s.runs, s.failed, s.courses, s._bare, s._lock = {}, {}, {}, None, th.Lock()
    s.course = lambda e: None
    made = []

    def make(entry, kind):
        made.append((entry, kind))
        if (entry, kind) == (5, "plain"):
            raise RuntimeError("mame died")
        return (entry, kind)
    s._make = make
    s.prefetch({(e, k) for e in (3, 4, 5) for k in ("normal", "plain", "reverse")})
    assert set(s.runs) == {(e, k) for e in (3, 4, 5) for k in ("normal", "plain", "reverse")} - {(5, "plain")}
    assert set(s.failed) == {(5, "plain")} and len(made) == 9
    with pytest.raises(AssertionError, match="entry 5 plain failed earlier"):
        s.run(5, "plain")
    assert s.run(3, "reverse") == (3, "reverse") and len(made) == 9


def test_the_wanted_runs_come_from_this_modules_tests_only():
    """Task 6: the fixture's wanted runs are read from this module's tests (`_KINDS`) only. A test of another module parametrized
    without `entry` (tests/test_race_build.py's `k`) or not parametrized at all is skipped without reading its parameters; a test
    of this module named in `_KINDS` without a fixed entry and without an `entry` parameter is a mistake here and raises a named
    error (no ROM: stand-in items)."""
    from types import SimpleNamespace as NS

    def item(name, **params):
        it = NS(name=f"{name}[x]" if params else name, originalname=name)
        if params:
            it.callspec = NS(params=params)
        return it
    items = [item("test_each_course_races_on_its_own_tables", k=2),                # foreign, parametrized by k only
             item("test_build_all_fits_the_budgets"),                                 # foreign, no callspec
             item("test_a_normal_pit_stop", entry=4),                                 # this module's, by entry
             item("test_two_stops_and_no_third"),                                     # this module's, fixed entry
             item("test_the_crew_stands_round_the_car_in_reverse", entry=METROPOLIS, kind="reverse",
                  reference="nocrew_reverse")]                                    # kinds a function of the parameters
    assert _wanted(items) == {(4, "normal"), (AMAZON_FALLS, "long"), (METROPOLIS, "reverse"), (METROPOLIS, "nocrew_reverse")}
    with pytest.raises(ValueError, match="test_a_reverse_pit_stop.*no `entry` parameter"):
        _wanted([item("test_a_reverse_pit_stop", k=1)])
