"""Phase 90: pack 2 in MAME, built FROM THE TREE once a session (tests/pack_sets.py; fix round 1, I7: no longer a prebuilt set
named by a variable). Needs MAME, the arcade set (VR_ROMDIR) and the PS2 disc (VR_PS2_DISC); the gantry comparison needs the
Saturn disc too (pack 1, VR_SATURN_CUE). Skips without them.

- the LAST wheel entry chosen through the wheel port (not by script) and raced, in reverse and in the rain;
- I5: the six-entry wheel on pictures: for each entry, the yellow frame stands on that entry's panel and the entry loads;
- I3 (b): the pack tag both ways on the battery RAM: pack 2 booted on a battery RAM tagged as pack 1's starts on its own default
  tables (the foreign times gone) without a crash; booted on its own, a best time is kept;
- I12: the start gantry stored as the arcade's frames plus a lettering object (pack 2) looks, on an arcade course as the car comes
  back to the line at the end of its first lap (the gantry and its lettering in view), as pack 1's does, pixel for pixel; on a PS2
  course its lettering is drawn in the arcade's lettering colours (fix round 1b)."""
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from vrtools.arcade.pack import PACK2_MAGIC, PS2
from vrtools.arcade.select import wheel_for

DISC = os.environ.get("VR_PS2_DISC")
JOBS = 3


@pytest.fixture(autouse=True)
def _the_ps2_disc():
    """`mame` or VR_PS2_DISC missing: skip, or FAIL under VR_REQUIRE_REFERENCE_SETS=1 (tests/reference_sets.py's `missing_input`
    and `required_ps2_disc`)."""
    from tests.reference_sets import missing_input, required_ps2_disc
    if shutil.which("mame") is None:
        missing_input("needs MAME")
    required_ps2_disc()


@pytest.fixture
def pack2(tmp_path_factory) -> Path:
    from tests.pack_sets import built
    from tests.reference_sets import required_romset_zip
    return built("ps2", required_romset_zip(), tmp_path_factory, ps2_disc=DISC)


def test_the_last_entry_of_pack_twos_wheel_is_chosen_with_the_wheel_and_raced(pack2, tmp_path):
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.romset import RomSet
    from vrtools.mame.runner import LUA_DIR, course_of, parse_race_log, run_mame
    last = PS2.menu - 1
    rs = RomSet.from_zip(pack2 / "vr.zip", verify=False)
    entry = decode_directory(rs)[last]
    run_mame(LUA_DIR / "autoplay.lua", 75, tmp_path, pack2, env={
        "VR_COURSE": "0", "VR_WHEEL": str(wheel_for(last, PS2.menu)), "VR_DIRECTION": "1", "VR_RAIN": "1",
        "VR_COLLISION_LOG": str(tmp_path / "c.txt"), "VR_RACE_LOG": str(tmp_path / "race.txt"), "VR_RACE_LOG_FROM": "0"},
        timeout=900)
    assert course_of(tmp_path / "c.txt") == (last, entry.template)          # the wheel chose the last entry, and it loaded
    players = parse_race_log(tmp_path / "race.txt")[0]
    assert max(p.road_point for p in players) > 10                          # and the car raced it


# --- I5: the cursor on pictures -------------------------------------------------------------------------------------------
SELECT_SNAP = 1190                  # the select screen, the wheel held since VR_WHEEL_FROM, just before the gas locks the entry
SLOT_SPAN = ((0, 165), (165, 330), (330, 496))      # the three panels' columns on MAME's 496 x 384 snapshot
PANEL_X = (96, 248, 398)            # each panel's centre; its picture is cropped PANEL_HALF either side, rows PANEL_ROWS
PANEL_HALF, PANEL_ROWS = 46, (25, 160)
SAME, OTHER = 6.0, 12.0             # mean absolute difference (0..255) of two crops: the same panel under, different panels over


def _rgb(path: Path) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB")).astype(int)


def frame_slot(a: np.ndarray) -> int:
    """The slot the yellow frame is drawn around: the one whose column has frame rows (over 100 pure-yellow pixels in a row) in
    the panels' band. AssertionError unless exactly one has."""
    yellow = (a[..., 0] > 200) & (a[..., 1] > 200) & (a[..., 2] < 80)
    rows = [sum(1 for r in range(190) if yellow[r, x0:x1].sum() > 100) for x0, x1 in SLOT_SPAN]
    slots = [s for s, n in enumerate(rows) if n >= 8]
    assert len(slots) == 1, ("the yellow frame", rows)
    return slots[0]


def panel(a: np.ndarray, s: int) -> np.ndarray:
    return a[PANEL_ROWS[0]:PANEL_ROWS[1], PANEL_X[s] - PANEL_HALF:PANEL_X[s] + PANEL_HALF]


def _differ(p, q) -> float:
    return float(np.abs(p - q).mean())


def test_each_entry_of_the_six_entry_wheel_has_the_yellow_frame_on_its_own_panel_and_loads(pack2, tmp_path):
    """I5 (fix round 1): the wheel port held at each entry's value; on the select screen's snapshot the panel under the yellow
    frame is that entry's: the six panels under the frame are all different; the frame steps right by 0 or 1 slot from one entry
    to the next, from the left slot to the right one; where it steps right the window did not scroll, so the next entry's panel
    is the one already drawn in that slot (a slot draws a panel the same way whichever snapshot: compared pixel for pixel; across
    slots a panel's colours differ); the gas then loads that entry. The cursor fault 2a18dd7 fixed drew Beltway's frame on
    Mountain's panel (on the set before it: frame slots [0, 1, 1, 1, 1, 1], the same panel under entries 4 and 5)."""
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.romset import RomSet
    from vrtools.mame.runner import LUA_DIR, course_of, run_mame
    d = decode_directory(RomSet.from_zip(pack2 / "vr.zip", verify=False))

    def shot(e):
        wd = tmp_path / f"entry{e}"
        run_mame(LUA_DIR / "autoplay.lua", 36, wd, pack2, env={
            "VR_COURSE": "0", "VR_WHEEL": str(wheel_for(e, PS2.menu)), "VR_SNAPS": str(SELECT_SNAP),
            "VR_COLLISION_LOG": str(wd / "c.txt")}, timeout=900)
        return _rgb(next((wd / "snap").rglob("*.png"))), course_of(wd / "c.txt")
    with ThreadPoolExecutor(JOBS) as ex:
        shots = list(ex.map(shot, range(PS2.menu)))
    for e, (_, loaded) in enumerate(shots):
        assert loaded == (e, d[e].template), (e, "loaded", loaded)
    slots = [frame_slot(a) for a, _ in shots]
    under = [panel(a, s) for (a, _), s in zip(shots, slots)]
    for e in range(PS2.menu):
        for f in range(e):
            assert _differ(under[e], under[f]) > OTHER, ("the same panel under the frame for entries", f, e, slots)
    assert slots[0] == 0 and slots[-1] == 2 and all(b - a in (0, 1) for a, b in zip(slots, slots[1:])), slots
    for e in range(PS2.menu - 1):                    # the frame stepped right: entry e + 1's panel is the one e's snapshot shows there
        if slots[e + 1] == slots[e] + 1:
            assert _differ(panel(shots[e][0], slots[e + 1]), under[e + 1]) < SAME, ("the panel right of", e, slots)


# --- I3 (b): the pack tag on the battery RAM ----------------------------------------------------------------------------------
NVRAM_BASE = 0x400000               # the battery RAM file's first byte is 0x400000 in the V60's space
MAGIC_AT = 0x40E6D0                 # ranking.py: the S-RAM magic
TIME_AT = 0x40E000                  # ranking.ORIG_TABLES[0]: the first original's best-time table
PLANTED = bytes(range(0x30, 0x38))  # eight bytes planted in the table's first record (12 bytes: the initialiser rewrites them)


def _planted(battery: bytes, magic: bytes) -> bytes:
    b = bytearray(battery)
    b[MAGIC_AT - NVRAM_BASE:MAGIC_AT - NVRAM_BASE + len(magic)] = magic
    b[TIME_AT - NVRAM_BASE:TIME_AT - NVRAM_BASE + len(PLANTED)] = PLANTED
    return bytes(b)


def test_the_pack_tag_clears_the_other_packs_battery_ram_and_keeps_its_own(pack2, tmp_path):
    """I3 (b) (fix round 1; by design, the lead's ruling): pack 2 booted on a battery RAM tagged as pack 1's (NEW_MAGIC, a best
    time planted) starts on its own default tables, tagged as pack 2's, and runs its attract (no crash); booted twice on its own
    battery RAM with the same time planted, it keeps the time."""
    from tests.test_reverse_ranking import BOOT_SECONDS, _attract
    from vrtools.arcade.ranking import NEW_MAGIC
    fresh = _attract(tmp_path, pack2, "fresh", BOOT_SECONDS)
    at = lambda b, a, n: b[a - NVRAM_BASE:a - NVRAM_BASE + n]
    assert at(fresh.battery, MAGIC_AT, len(PACK2_MAGIC)) == PACK2_MAGIC
    default = at(fresh.battery, TIME_AT, len(PLANTED))
    assert default != PLANTED
    jobs = {"foreign": _planted(fresh.battery, NEW_MAGIC), "own": _planted(fresh.battery, PACK2_MAGIC)}
    with ThreadPoolExecutor(2) as ex:
        runs = dict(zip(jobs, ex.map(lambda kv: _attract(tmp_path, pack2, kv[0], BOOT_SECONDS, kv[1]), jobs.items())))
    foreign, own = runs["foreign"], runs["own"]
    assert foreign.pages and own.pages, "the attract's ranking pages after the boot (no crash)"
    assert at(foreign.battery, MAGIC_AT, len(PACK2_MAGIC)) == PACK2_MAGIC
    assert at(foreign.battery, TIME_AT, len(PLANTED)) == default             # the foreign time gone: the default table
    assert at(own.battery, TIME_AT, len(PLANTED)) == PLANTED                 # its own time kept
    again = _attract(tmp_path, pack2, "own2", BOOT_SECONDS, own.battery)
    assert at(again.battery, TIME_AT, len(PLANTED)) == PLANTED


# --- I12: the start gantry's lettering ---------------------------------------------------------------------------------------
# Fix round 1b: the start gantry stands at road point 0, and the grid starts past it (the cars line up ahead of the line on every
# course, and Big Forest starts from the pits): it is first in view at the END of the first lap, as the car comes back to the line
# (out/p90/fix1b/gantry_sheet.png). So: a drive on the autopilot records its inputs (input_tape.lua) and the race log, which gives
# the frame the lap ends; the same tape is replayed with snapshots over the GANTRY_WINDOW frames before that end, picked by
# autoplay.lua's snapshot log (VR_SNAP_LOG: the frame of each PNG; MAME's -str adds one picture of its own at the run's end, the
# extra picture round 1 counted).
GANTRY_WINDOW = range(-132, 1, 6)   # frames before the lap's end (the START banner grows from far to overhead over these)
GANTRY_ROWS = (0, 200)              # the picture's upper part: the gantry over the road
LAP_SECONDS, REPLAY_SECONDS = 140, 125
LETTER_RED = 150                    # the lettering's red: R over this, G and B under 90 (the arcade's 255,0,0 and its shades)
LETTERS_MIN = 400                   # lettering pixels on the banner in the best frame of the window (`lettering`'s mask: Big
                                    # Forest 699 at frame 5654, Island 737 at frame 4624 in round 1b's run)


def _lap_drive(set_dir: Path, wd: Path, wheel: int, line, hold: bool) -> int:
    """The autopilot on `line` from the grid: its tape (wd/tape.txt) and the frame its first lap ends (the lap byte 0 -> 1)."""
    from vrtools.mame.runner import LUA_DIR, parse_race_log, run_mame, write_centreline
    env = {"VR_COURSE": "0", "VR_WHEEL": str(wheel), "VR_SNAPS": "", "VR_COLLISION_LOG": str(wd / "c.txt"),
           "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", line)), "VR_INPUT_LOG": str(wd / "tape.txt"),
           "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0"}
    if hold:
        env["VR_HOLD_CLOCK"] = "1"
    run_mame(LUA_DIR / "autoplay.lua", LAP_SECONDS, wd, set_dir, env=env, timeout=1800)
    ends = [p.frame for p in parse_race_log(wd / "race.txt")[0] if p.frame > 1700 and p.lap == 1]
    assert ends, (wd.name, "the first lap did not end in", LAP_SECONDS, "s")
    return ends[0]


def snaps_by_frame(wd: Path) -> dict[int, np.ndarray]:
    """{frame: picture} of autoplay.lua's own snapshots, by its snapshot log (the n-th PNG is the log's n-th line)."""
    pngs = sorted((wd / "snap").rglob("*.png"))
    log = [l.split() for l in open(wd / "snaps.txt") if l.startswith("S ")]
    assert len(pngs) >= len(log), (wd.name, len(pngs), len(log))
    return {int(f): _rgb(pngs[int(n) - 1]) for _, n, f, _ in log}


def _replay(set_dir: Path, wd: Path, wheel: int, tape_wd: Path, frames, hold: bool) -> dict[int, np.ndarray]:
    from vrtools.mame.runner import LUA_DIR, run_mame
    env = {"VR_COURSE": "0", "VR_WHEEL": str(wheel), "VR_SNAPS": ",".join(map(str, frames)), "VR_SNAP_LOG": str(wd / "snaps.txt"),
           "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_AUTOPILOT": str(tape_wd / "line.csv"),
           "VR_INPUT_REPLAY": str(tape_wd / "tape.txt")}
    if hold:
        env["VR_HOLD_CLOCK"] = "1"
    run_mame(LUA_DIR / "autoplay.lua", REPLAY_SECONDS if max(frames) < REPLAY_SECONDS * 57 else LAP_SECONDS, wd, set_dir, env=env,
             timeout=1800)
    got = snaps_by_frame(wd)
    assert sorted(got) == sorted(frames), (wd.name, "snapshots at", sorted(got))
    return got


def lettering(a: np.ndarray) -> np.ndarray:
    """The lettering's mask in the gantry's rows: red pixels with the white banner 6 rows above and below."""
    a = a[GANTRY_ROWS[0]:GANTRY_ROWS[1]]
    white = a.min(2) > 200
    red = (a[..., 0] > LETTER_RED) & (a[..., 1] < 90) & (a[..., 2] < 90)
    m = np.zeros_like(red)
    m[6:-6] = red[6:-6] & white[:-12] & white[12:]
    return m


def test_the_start_gantry_in_pack_two_looks_as_in_pack_one(pack2, tmp_path_factory, tmp_path):
    """I12 (fix round 1; round 1b: looking AT the gantry): Big Forest (an arcade course) driven on the autopilot to the end of its
    first lap in pack 1, its tape replayed in pack 1 and in pack 2: over GANTRY_WINDOW frames before the lap's end (the START banner
    from far to overhead) the gantry's rows are the same pixel for pixel in the two packs, and the lettering is in them (LETTERS_MIN
    lettering pixels in the best frame). Island (a PS2 course, pack 2's own copy of the gantry) driven the same way, the clock held:
    over its window the lettering shows in the arcade's lettering colours (the red colours Big Forest's lettering is drawn in, each
    of them seen, on a white banner), LETTERS_MIN pixels in its best frame. Stills: out/p90/fix1b/gantry_sheet.png."""
    from tests.pack_sets import built
    from tests.reference_sets import required_romset_zip, required_saturn_cue
    from tests.test_pack_rate import COURSES
    from vrtools.arcade.course import course_entry_at, road_lines
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.select import WHEEL_FOR_ENTRY

    def line(set_dir, entry, li):
        rs = RomSet.from_zip(set_dir / "vr.zip", verify=False)
        d = decode_directory(rs)
        return [(p.x, p.z) for p in road_lines(rs, course_entry_at(rs, d[entry].bank, window_base=d[entry].header_base))[li]]
    pack1 = built("saturn", required_romset_zip(), tmp_path_factory, saturn_cue=required_saturn_cue())
    island, _, _ = COURSES["island"]
    w1, w2, wi = WHEEL_FOR_ENTRY[0], wheel_for(0, PS2.menu), wheel_for(island, PS2.menu)
    with ThreadPoolExecutor(2) as ex:
        bf_end, is_end = ex.map(lambda a: _lap_drive(*a), [(pack1, tmp_path / "bf_tape", w1, line(pack1, 0, 0), False),
                                                          (pack2, tmp_path / "island_tape", wi, line(pack2, island, 0), True)])
    bf = [bf_end + k for k in GANTRY_WINDOW]
    isl = [is_end + k for k in GANTRY_WINDOW]
    with ThreadPoolExecutor(3) as ex:
        one, two, ps2 = ex.map(lambda a: _replay(*a), [(pack1, tmp_path / "bf_pack1", w1, tmp_path / "bf_tape", bf, False),
                                                       (pack2, tmp_path / "bf_pack2", w2, tmp_path / "bf_tape", bf, False),
                                                       (pack2, tmp_path / "island", wi, tmp_path / "island_tape", isl, True)])
    r0, r1 = GANTRY_ROWS
    for f in bf:
        diff = np.argwhere((one[f][r0:r1] != two[f][r0:r1]).any(2))
        assert diff.size == 0, (f, "pixels differ", len(diff), diff.min(0).tolist(), diff.max(0).tolist())
    best = max(bf, key=lambda f: lettering(one[f]).sum())
    assert lettering(one[best]).sum() >= LETTERS_MIN, ("Big Forest's lettering not in view", best, int(lettering(one[best]).sum()))
    a = one[best][r0:r1]
    from collections import Counter
    colours = {c for c, n in Counter(map(tuple, a[lettering(one[best])])).items() if n >= 20}      # the arcade's lettering colours
    ibest = max(isl, key=lambda f: lettering(ps2[f]).sum())
    b = ps2[ibest][r0:r1]
    seen = Counter(map(tuple, b[lettering(ps2[ibest])]))
    assert sum(seen[c] for c in colours) >= LETTERS_MIN and all(seen[c] for c in colours), \
        ("Island's lettering", ibest, {c: seen[c] for c in colours}, seen.most_common(4))
