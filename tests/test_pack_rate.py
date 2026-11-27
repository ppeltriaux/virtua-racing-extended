"""Phase 90: pack 2's three PS2 courses in RAIN hold the arcade's draw budget with the released rate test's floor, and leave the
rain its room (the session lead's ruling on the max-detail round's figures).

Two different things are protected, so two assertions per course and direction:
- the scenery's object lists: `need` (frame_rate.lua: the highest record count the list walker compared with the budget, the
  least budget under which the frame skips no list) stays MARGIN_FLOOR under the game's FRAME_BUDGET, and no list is skipped.
  This is tests/test_frame_rate.py's worst-frame form (Big Forest's line 4 keeps 400): a far list skipped is a flicker;
- the rain not being cut short: `records` (the frame's peak count, the rain's clusters and splashes included) stays at or under
  RECORDS_MAX. The rain draws last and only while the count is under the budget (rain.py), so a frame at 10 500 is a frame of
  thinner rain, not a skipped list; the max-detail design held the storm's peak under 10 200, and that is the room kept.
Each run: pack 2 built once a session from the arcade set and the PS2 disc (tests/pack_sets.py), RAIN, the clock held, the
autopilot on the course's scripted line from the boot through the start with the whole field (the first lap's bunched field in
view) for RAIN_SECONDS (about two laps); every pass from the race's load on, the load's own pass excepted. Needs MAME, VR_ROMDIR
and VR_PS2_DISC; skips without them. The runs are made together at the first test (three MAME processes)."""
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from vrtools.arcade.budget import FRAME_BUDGET

DISC = os.environ.get("VR_PS2_DISC")
# course -> (menu entry in pack 2, the road line the autopilot drives, its lookahead in points): Island and Mountain on their
# centreline (lookahead 6: with 3 the scripted car crashed at Island's road points 152-160 and the stopped view reached 10 500);
# Beltway on its offset-0 AI line (the centreline away from the pylons, the right-hand carriageway beside them, ps2course's
# divider_lanes), lookahead 3 so it holds that carriageway; and Beltway again on the line the owner drove past the pylons (the
# centreline moved RIGHT_OFFSET to the right over RIGHT_STRETCH, ramped in and out): the race on which pack2g's first lap reached
# 10 494 records at road point 257, from which Beltway's `frame_cuts` were set
COURSES = {"island": (3, 0, 6), "mountain": (4, 0, 6), "beltway": (5, 6, 3), "beltway_right": (5, "right", 3)}
RIGHT_OFFSET, RIGHT_STRETCH, RIGHT_RAMP = 11.0, (48, 66), (6, 4)
RAIN_SECONDS = 200
MARGIN_FLOOR = 400                  # the released worst-frame floor (tests/test_frame_rate.py's MARGIN_FLOOR, Big Forest line 4)
RECORDS_MAX = 10_200                # the rain's room: the max-detail design's storm peak (pack.py's PS2 plans)
JOBS = 3
# I4 (fix round 1, the lead's ruling): the car PARKED in RAIN at each course's worst views (the build's own model: the three road
# points per direction with the most scenery records, `ps2entry.worst_views`, printed in the build report) and at Island's 152-160
# (where a stopped car once reached 10 500): held still on the road facing along it for PARK_FRAMES (park.lua)
PARK_FRAMES = 240
PARK_SECONDS = 260
EXTRA_PARKS = {("island", False): [156], ("island", True): [153]}      # Island 152-160 seen each way (reverse 309 - 156), unless
PARK_NEAR = 8                                                           # a worst view lies within PARK_NEAR of it already
PARK_AT = (-3, 15)                                                      # where the car came to rest, from the place asked
PARK_NEED_MAX = FRAME_BUDGET - MARGIN_FLOOR                             # the ruling: need <= 10 500 - 400



@pytest.fixture(autouse=True)
def _the_ps2_disc():
    """`mame` or VR_PS2_DISC missing: skip, or FAIL under VR_REQUIRE_REFERENCE_SETS=1 (tests/reference_sets.py's `missing_input`
    and `required_ps2_disc`)."""
    from tests.reference_sets import missing_input, required_ps2_disc
    if shutil.which("mame") is None:
        missing_input("needs MAME")
    required_ps2_disc()


class PackRainSession:
    def __init__(self, romset_zip: Path, base: Path, tmp_path_factory):
        from tests.pack_sets import built
        self.base = base
        self.set = built("ps2", romset_zip, tmp_path_factory, ps2_disc=DISC)           # the session's pack 2 (shared)
        self.runs, self._lock = {}, threading.Lock()
        self.views = worst_views_of(self.set / "build-report.txt")

    def parks(self, course: str, reverse: bool) -> list[int]:
        entry = COURSES[course][0]
        views = self.views[entry]["reverse" if reverse else "normal"]
        return views + [x for x in EXTRA_PARKS.get((course, reverse), []) if all(abs(x - v) >= PARK_NEAR for v in views)]

    def _make(self, course: str, reverse: bool, park: bool = False):
        from vrtools.arcade.course import course_entry_at, road_lines
        from vrtools.arcade.directory import decode_directory
        from vrtools.arcade.pack import PS2
        from vrtools.arcade.romset import RomSet
        from vrtools.arcade.select import wheel_for
        from vrtools.convert.reverse import reverse_points
        from vrtools.mame.framerate import parse_frame_log
        from vrtools.mame.runner import LUA_DIR, run_mame, write_centreline
        entry, li, look = COURSES[course]
        wd = self.base / f"{course}{'_reverse' if reverse else ''}{'_parked' if park else ''}"
        wd.mkdir(parents=True, exist_ok=True)
        rs = RomSet.from_zip(self.set / "vr.zip", verify=False)
        d = decode_directory(rs)
        lines = road_lines(rs, course_entry_at(rs, d[entry].bank, window_base=d[entry].header_base))
        line = [(p.x, p.z) for p in lines[0 if li == "right" else li]]
        if li == "right":
            line = _moved_right(line)
        env = {"VR_COURSE": "0", "VR_WHEEL": str(wheel_for(entry, PS2.menu)), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
               "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", reverse_points(line) if reverse else line)),
               "VR_AUTOPILOT_LOOKAHEAD": str(look), "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0",
               "VR_FRAME_LOG": str(wd / "frames.txt"), "VR_HOLD_CLOCK": "1", "VR_RAIN": "1"}
        if reverse:
            env["VR_DIRECTION"] = "1"
        if park:
            env.update({"VR_EXTRA_LUA": str(LUA_DIR / "park.lua"), "VR_PARK": ",".join(map(str, self.parks(course, reverse))),
                        "VR_PARK_N": str(len(line)), "VR_PARK_FRAMES": str(PARK_FRAMES), "VR_PARK_LOG": str(wd / "park.txt")})
        run_mame(LUA_DIR / "autoplay.lua", PARK_SECONDS if park else RAIN_SECONDS, wd, self.set, env=env, timeout=3600)
        load = next(int(l.split()[1]) for l in open(wd / "race.txt")
                    if l.startswith("P ") and int(l.split()[1]) > 1700 and float(l.split()[2]) != 0.0)
        frames = [f for f in parse_frame_log(wd / "frames.txt") if f.frame > load + 4]     # the load's own pass excepted
        if park:
            held = [tuple(int(v) for v in l.split()[1:5]) for l in open(wd / "park.txt") if l.startswith("PARK ")]
            return frames, held
        return frames

    def prefetch(self, keys):
        keys = [k for k in keys if k not in self.runs]
        with ThreadPoolExecutor(JOBS) as ex:
            for k, r in zip(keys, ex.map(lambda k: self._make(*k), keys)):
                self.runs[k] = r

    def run(self, course, reverse, park=False):
        key = (course, reverse) + ((True,) if park else ())
        if key not in self.runs:
            self.runs[key] = self._make(*key)
        return self.runs[key]


def worst_views_of(report: Path) -> dict[int, dict[str, list[int]]]:
    """{menu entry: the build's worst views} from the build report's PS2 lines ("worst views {...}")."""
    import ast
    import re
    out = {}
    for line in report.read_text().splitlines():
        m = re.match(r"entry (\d+) .*worst views (\{.*?\})", line)
        if m:
            out[int(m.group(1))] = ast.literal_eval(m.group(2))
    return out


def _moved_right(line):
    """The centreline moved RIGHT_OFFSET to the right over RIGHT_STRETCH (road points), ramped in over RIGHT_RAMP[0] points before
    and out over RIGHT_RAMP[1] after."""
    import math
    n = len(line)
    (a0, a1), (r0, r1) = RIGHT_STRETCH, RIGHT_RAMP
    out = []
    for k, (x, z) in enumerate(line):
        w = 1.0 if a0 <= k <= a1 else (k - (a0 - r0)) / r0 if a0 - r0 <= k < a0 else ((a1 + r1) - k) / r1 if a1 < k <= a1 + r1 else 0.0
        (ax, az), (bx, bz) = line[(k - 1) % n], line[(k + 1) % n]
        dn = math.hypot(bx - ax, bz - az) or 1.0
        out.append((x + RIGHT_OFFSET * w * (bz - az) / dn, z - RIGHT_OFFSET * w * (bx - ax) / dn))
    return out


_SESSION: dict = {}


@pytest.fixture
def pack_rain(request, tmp_path_factory) -> PackRainSession:
    if "s" not in _SESSION:
        from tests.reference_sets import required_romset_zip
        s = PackRainSession(required_romset_zip(), tmp_path_factory.mktemp("pack2rain"), tmp_path_factory)
        keys = [(i.callspec.params["course"], i.callspec.params["reverse"]) for i in request.session.items
                if getattr(i, "originalname", "") == "test_pack_two_holds_the_budget_and_the_rains_room_in_rain"]
        keys += [(i.callspec.params["course"], i.callspec.params["reverse"], True) for i in request.session.items
                 if getattr(i, "originalname", "") == "test_pack_two_parked_at_its_worst_views_leaves_the_rain_its_room"]
        s.prefetch(keys)
        _SESSION["s"] = s
    return _SESSION["s"]


@pytest.mark.parametrize("reverse", [False, True], ids=["normal", "reverse"])
@pytest.mark.parametrize("course", list(COURSES))
def test_pack_two_holds_the_budget_and_the_rains_room_in_rain(pack_rain, record_property, course, reverse):
    frames = pack_rain.run(course, reverse)
    assert len(frames) > 2000, (course, reverse, len(frames))
    need = max(f.need for f in frames)
    records = max(f.records for f in frames)
    skipped = [f.frame for f in frames if f.skipped]
    record_property("need_max", need)
    record_property("records_max", records)
    assert skipped == [] and {f.budget for f in frames} == {FRAME_BUDGET}, (course, reverse, skipped[:5])
    assert need <= FRAME_BUDGET - MARGIN_FLOOR, (course, reverse, "the scenery's margin under the budget", FRAME_BUDGET - need)
    assert records <= RECORDS_MAX, (course, reverse, "the rain's room", records,
                                    max(frames, key=lambda f: f.records).frame)


@pytest.mark.parametrize("reverse", [False, True], ids=["normal", "reverse"])
@pytest.mark.parametrize("course", ["island", "mountain", "beltway"])
def test_pack_two_parked_at_its_worst_views_leaves_the_rain_its_room(pack_rain, record_property, course, reverse):
    """I4 (fix round 1): in RAIN, the car held still on the road facing along it for PARK_FRAMES at each of the course's worst
    views (the build's model, both ways) and at Island's 152-160: at every parked frame no list is skipped, `need` stays under the
    budget by MARGIN_FLOOR and `records` within RECORDS_MAX."""
    frames, held = pack_rain.run(course, reverse, park=True)
    asked = pack_rain.parks(course, reverse)
    assert sorted(h[0] for h in held) == sorted(asked), (course, reverse, "places not parked at", asked, held)
    worst = {}
    for rp, at, first, last in held:
        assert PARK_AT[0] <= at - rp <= PARK_AT[1], (course, reverse, "parked at", at, "for", rp)
        fs = [f for f in frames if first <= f.frame <= last]
        assert len(fs) > PARK_FRAMES // 3, (course, reverse, rp, len(fs))
        worst[rp] = (at, max(f.need for f in fs), max(f.records for f in fs), sum(f.skipped for f in fs))
    record_property("parked", worst)
    for rp, (at, need, records, skipped) in worst.items():
        assert skipped == 0, (course, reverse, rp, "lists skipped while parked")
        assert need <= PARK_NEED_MAX, (course, reverse, rp, at, "need", need)
        assert records <= RECORDS_MAX, (course, reverse, rp, at, "records", records)
