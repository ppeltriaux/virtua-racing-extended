"""Run MAME headless on the `vr` set with a Lua autoboot script."""

from __future__ import annotations

import math
import os
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

LUA_DIR = Path(__file__).resolve().parent / "lua"


class MameError(Exception):
    pass


def run_mame(script: Path, seconds: int, workdir: Path, rom_dir: Path, env: dict[str, str] | None = None,
             mame: str = "mame", timeout: float | None = None, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run MAME headless for `seconds` emulated seconds with the Lua `script`; MameError when it fails or, with
    `timeout` (wall-clock seconds), when it does not end in time (it is killed). `extra_args` go at the end of the
    command (e.g. `["-aviwrite", "run.avi"]`: MAME writes the AVI under its snapshot directory, with sound). The scripts get
    VR_LUA_DIR and (Phase 26 stage 3) VR_REVERSE_TABLE, the reverse table's address in this tree's directory layout (hex), with
    which autoplay.lua knows the courses whose lock opens the COURSE DIRECTION screen; `env` overrides either."""
    from vrtools.arcade.directory import directory_layout
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [mame, "vr", "-rompath", str(rom_dir), "-video", "none", "-sound", "none", "-window",
           "-nothrottle", "-str", str(seconds), "-skip_gameinfo", "-autoboot_script", str(script),
           "-snapshot_directory", str(workdir / "snap"), "-nvram_directory", str(workdir / "nvram"),
           "-cfg_directory", str(workdir / "cfg")] + list(extra_args or [])
    full_env = {**os.environ, "VR_LUA_DIR": str(LUA_DIR), "VR_REVERSE_TABLE": f"{directory_layout()['reverse']:x}", **(env or {})}
    try:
        proc = subprocess.run(cmd, cwd=workdir, env=full_env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise MameError(f"mame did not end within {timeout} s and was killed") from e
    if proc.returncode != 0 or "Average speed" not in proc.stdout:
        raise MameError(f"mame exited {proc.returncode}: {proc.stdout[-500:]}\n{proc.stderr[-1500:]}")
    return proc


def parse_rate(path: Path) -> list[tuple[int, int]]:
    """(frame, list switches in the preceding 57 frames) from renderrate.lua."""
    out = []
    for line in open(path):
        parts = line.split()
        if parts and parts[0] == "R":
            out.append((int(parts[1]), int(parts[2])))
    return out


class CollisionSample(NamedTuple):
    frame: int
    y: float
    id: int
    x: float
    z: float
    result_y: float
    quad: int


def parse_collision(path: Path) -> list[CollisionSample]:
    """C lines from collision_log.lua (the player's call and result, one per logic frame)."""
    out = []
    for line in open(path):
        p = line.split()
        if p and p[0] == "C" and len(p) == 8:
            out.append(CollisionSample(int(p[1]), float(p[2]), int(p[3], 16), float(p[4]), float(p[5]), float(p[6]), int(p[7], 16)))
    return out


class AttitudeSample(NamedTuple):
    frame: int
    car: int
    x: float
    y: float
    z: float
    pitch: int         # +0x2a, signed 1/65536 turn, positive climbing (Phase 16 recon §1: Phase 15 had pitch and roll swapped)
    roll: int          # +0x2e, negative = right side up
    disp_pitch: int    # +0x4c = +0x2a + +0xe5
    yaw: int           # +0x4e
    disp_roll: int     # +0x50 = +0x2e + +0xe9 (the lean from steering at speed)
    yaw_raw: int       # +0x6a


def parse_attitude(path: Path) -> list[AttitudeSample]:
    """A lines from attitude_log.lua (Phase 15)."""
    out = []
    for line in open(path):
        p = line.split()
        if p and p[0] == "A" and len(p) >= 12:                     # the recon's logger wrote one more field (speed)
            out.append(AttitudeSample(int(p[1]), int(p[2]), float(p[3]), float(p[4]), float(p[5]), *(int(v) for v in p[6:12])))
    return out


class PlayerSample(NamedTuple):
    frame: int
    x: float
    z: float
    yaw: int            # +0x6a, signed 1/65536 turn
    heading: int        # +0x36, signed
    attr: int           # +0xeb, the halfword (+0xeb..+0xec)
    road_point: int     # +0xa6
    lap: int            # +0x1b5
    checkpoints: int    # +0x57
    clock: int          # 0x50116c (1/32 s)
    off_course: int     # 0x50115c


class Jolt(NamedTuple):
    frame: int
    car: int            # 1..15
    road_point: int     # +0xa6
    x: float
    z: float


def parse_race_log(path: Path) -> tuple[list[PlayerSample], list[Jolt]]:
    """P and J lines from race_log.lua (Phase 26): the player each frame, and the frames an opponent's smoke counter
    (+0x1aa) rose from 0. Frames count from 1 (fieldtrace.lua's from 0: its frame f is this log's f + 1)."""
    players, jolts = [], []
    for line in open(path):
        p = line.split()
        if p and p[0] == "P" and len(p) == 12:
            players.append(PlayerSample(int(p[1]), float(p[2]), float(p[3]), *(int(v) for v in p[4:12])))
        elif p and p[0] == "J" and len(p) == 6:
            jolts.append(Jolt(int(p[1]), int(p[2]), int(p[3]), float(p[4]), float(p[5])))
    return players, jolts


class CarSample(NamedTuple):
    frame: int
    car: int            # 1..15
    road_point: int     # +0xa6
    x: float
    z: float
    yaw: int            # +0x36, signed 1/65536 turn (an opponent's yaw: the contact routines' steer writes it, boot 0xfece3d)
    speed: int          # +0x14, u32


def parse_race_cars(path: Path) -> list[CarSample]:
    """O lines from race_log.lua (Phase 26 stage 2, VR_RACE_CARS_TO): each opponent each frame before that frame."""
    out = []
    for line in open(path):
        p = line.split()
        if p and p[0] == "O" and len(p) == 8:
            out.append(CarSample(int(p[1]), int(p[2]), int(p[3]), float(p[4]), float(p[5]), int(p[6]), int(p[7])))
    return out


class StartSample(NamedTuple):
    frame: int          # from the course load: 0 = the first frame the mode byte 0x501139 reads 0x11
    mode: int           # 0x501139
    clock: int          # 0x50116c (1/32 s)
    flag: int           # the direction flag (course.DIRECTION_RAM)
    pit: int            # +0x191, the pit state (6: the Big Forest template's crew start)
    x: float
    z: float
    yaw: int            # +0x6a, signed 1/65536 turn
    attr: int           # +0xeb, the halfword (+0xeb..+0xec)
    road_point: int     # +0xa6
    lap: int            # +0x1b5


class StartCar(NamedTuple):
    frame: int          # from the course load, as StartSample
    car: int            # 1..15
    road_point: int     # +0xa6
    lap: int            # +0x1b5
    x: float
    z: float


def parse_start_log(path: Path) -> tuple[int | None, list[StartSample], list[StartCar]]:
    """start_log.lua (Phase 26 stage 2): the load's frame (counted from 1 at the first frame end; None when the race never
    loaded), the player's S line and the opponents' O lines of every frame from the load."""
    load, player, cars = None, [], []
    for line in open(path):
        p = line.split()
        if p and p[0] == "L" and len(p) == 2:
            load = int(p[1])
        elif p and p[0] == "S" and len(p) == 12:
            player.append(StartSample(int(p[1]), int(p[2], 16), int(p[3]), int(p[4]), int(p[5]), float(p[6]), float(p[7]),
                                      *(int(v) for v in p[8:12])))
        elif p and p[0] == "O" and len(p) == 7:
            cars.append(StartCar(int(p[1]), int(p[2]), int(p[3]), int(p[4]), float(p[5]), float(p[6])))
    return load, player, cars


class DirFrame(NamedTuple):
    frame: int          # counted from 1 at the first frame end
    mode: int           # 0x501139
    state: int          # 0x501180
    timer: int          # 0x50113c, signed
    handler: int        # the select entity's handler while the mode byte reads 0x10, else 0
    entry: int          # 0x501940
    flag: int           # course.DIRECTION_RAM
    phase: int          # dirscreen.DIR_PHASE
    armed: int          # dirscreen.DIR_ARMED
    shown: int          # dirscreen.DIR_SHOWN
    edge: int           # 0x501078 (the gas edge, 0xffff for one logic frame)
    manual: int         # 0x501936 (the transmission the course select latched)
    start: int          # bit 4 of 0x501050: the START button as the course select's 0xfc31e4 reads it
    counter: int        # 0x501144, the logic frame counter (one step every two video frames; Task 3's overrun test)


def parse_dir_log(path: Path) -> list[DirFrame]:
    """D lines from dirscreen_log.lua (Phase 26 stage 3): a line at every frame end at which a field changed."""
    out = []
    for line in open(path):
        p = line.split()
        if p and p[0] == "D" and len(p) == 15:
            out.append(DirFrame(int(p[1]), int(p[2], 16), int(p[3]), int(p[4]), int(p[5], 16), *(int(v) for v in p[6:11]),
                                int(p[11], 16), int(p[12]), int(p[13]), int(p[14])))
    return out


HUD_COLUMNS = range(40, 62)            # the columns hud_log.lua logs of layer 0's rows 44 and 45 (the level word: 51-58)


class HudFrame(NamedTuple):
    mode: int           # 0x501138: 0x11-0x13 (the race load: the frame the level word's last cell is printed), 0x14 (60 frames
                        # after its first frame) or 0x1a (its first frame)
    frame: int          # counted from 1 at the first frame end, as autoplay.lua counts
    attr: int           # the byte [0x501434], the level word printer's colour cell
    row44: tuple[int, ...]      # layer 0's tile words on row 44, columns 40-61 (HUD_COLUMNS)
    row45: tuple[int, ...]      # the same on row 45


def parse_hud_log(path: Path) -> list[HudFrame]:
    """H lines from hud_log.lua (Phase 26 stage 3, Task 6): H <frame> <mode> <attr> <row 44's words> <row 45's words>, hex but the
    frame, len(HUD_COLUMNS) words a row."""
    n = len(HUD_COLUMNS)
    out = []
    for line in open(path):
        p = line.split()
        if p and p[0] == "H" and len(p) == 4 + 2 * n:
            words = tuple(int(v, 16) for v in p[4:])
            out.append(HudFrame(int(p[2], 16), int(p[1]), int(p[3], 16), words[:n], words[n:]))
    return out


class FigureLoad(NamedTuple):
    frame: int          # the load's frame, counted from 1
    flag: int           # the direction byte on the select screen's last frame (Task 8: direction.lua's write reached it)


class FigurePose(NamedTuple):
    frame: int          # from the course load, as StartSample
    x: float
    z: float
    yaw: int            # +0x6a, signed 1/65536 turn (0: +z; forward is (-sin, cos))
    flag: int           # the direction byte this frame (the loader writes back what it served)


class FigureSample(NamedTuple):
    frame: int          # from the course load, as StartSample
    figure: int         # pool object 0..2 of [0x501350]
    flags: int          # +0: bit 31 live, bit 0x1e the animation has ended
    record: int         # +0x1ab, the character record (0xfd743b, 0xfd747f, 0xfd754b: the three figures)
    x: float
    z: float
    root_x: float       # +0x17b, the animation's translation so far (drawn at x + root_x; added to x when it ends)
    root_z: float       # +0x193
    heading: int        # +0x2c, unsigned halfword
    walk: int           # +0x36, unsigned halfword (state 0x27's walk-off heading, 0x4000 on the original)


def parse_figures_log(path: Path) -> tuple[FigureLoad | None, list[FigurePose], list[FigureSample]]:
    """figures_log.lua (Phase 26 stage 2 Task 7): the load (its frame counted from 1 and the direction byte on the select
    screen; None when the race never loaded), the player's P line and the three start figures' G lines of every frame from
    the load."""
    load, player, figures = None, [], []
    for line in open(path):
        p = line.split()
        if p and p[0] == "L" and len(p) == 3:
            load = FigureLoad(int(p[1]), int(p[2]))
        elif p and p[0] == "P" and len(p) == 6:
            player.append(FigurePose(int(p[1]), float(p[2]), float(p[3]), int(p[4]), int(p[5])))
        elif p and p[0] == "G" and len(p) == 11:
            figures.append(FigureSample(int(p[1]), int(p[2]), int(p[3], 16), int(p[4], 16), *(float(v) for v in p[5:9]),
                                        int(p[9]), int(p[10])))
    return load, player, figures


class FieldSample(NamedTuple):
    frame: int
    car: int
    point: int          # +0xa6, the road point
    lap: int            # +0x1b5, signed
    cursor: int         # the line cursor in points (+0xe1 is a byte offset, 16 per point)
    target: int         # +0x1b1
    quad: int           # +0x30
    perf: float         # +0x48, the working performance
    x: float
    z: float
    rank: int           # +0x123
    behind: int         # the ranking neighbours as car indices
    ahead: int


def parse_field(path: Path) -> list[FieldSample]:
    """Lines from fieldtrace.lua (Phase 26: the cursor is converted from its raw byte offset to points, 16 to the point)."""
    out = []
    for line in open(path):
        p = line.split()
        if len(p) == 13:
            out.append(FieldSample(int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4]) // 16, int(p[5]), int(p[6]), float(p[7]),
                                   float(p[8]), float(p[9]), int(p[10]), int(p[11]), int(p[12])))
    return out


PIT_HANDLER = 0xFF2345              # the player's handler during a pit stop (stage 4 recon §1.1: 0xff222f sets it, the release restores
                                    # 0xfe8e18)
PARK_FLAG = 0x80                    # bit 7 of the player's +0, set by `pitpark` when the car stands at the box (recon §1.1)


@dataclass(frozen=True)
class PitFrame:
    """One P line of pit_log.lua (Phase 26 stage 4, Task 4): the player on one video frame (every logic frame is logged)."""
    frame: int          # counted from 1 at the first frame end (as race_log.lua; fieldtrace.lua's frame f is this f + 1)
    quad: int           # +0x150, the lap-position quad the pit check compares with the entry's pit quad and the next
    handler: int        # +0xa, the player's handler (PIT_HANDLER during a stop)
    state: int          # +0x191, the pit state
    stops: int          # +0x1bf, the stops left
    x: float
    z: float
    yaw: int            # +0x6a, the unsigned halfword (1/65536 turn; a maps record's box heading compares as it is)
    speed: float        # +0x14
    clock: int          # 0x50116c (1/32 s)
    cps: int            # +0x57, the checkpoint counter (the release adds one: recon §1.1)
    lap: int            # +0x1b5, signed
    crew: tuple[tuple[float, float, int], ...]    # each live crew object (pool objects 0-5 of [0x501350], slot order): x, z, heading
                                                  # (+0x2c, unsigned halfword)
    flags: int = 0      # +0, the player's flags (PARK_FLAG)
    smoke: int = 0      # +0x1aa, the smoke counter: it rises from 0 when the car hits a wall


def parse_pit_log(path: Path) -> list[PitFrame]:
    """The P lines of pit_log.lua (VR_PIT_LOG): frame, quad, handler (hex), state, stops, x, z, yaw, speed, clock, checkpoints,
    lap, flags (hex), smoke, the crew's count and as many (x, z, heading) triples. Other and incomplete lines are skipped (MAME
    can end a run in the middle of a line)."""
    out = []
    for line in open(path):
        p = line.split()
        if len(p) < 16 or p[0] != "P":
            continue
        n = int(p[15])
        if len(p) != 16 + 3 * n:
            continue
        crew = tuple((float(p[16 + 3 * i]), float(p[17 + 3 * i]), int(p[18 + 3 * i])) for i in range(n))
        out.append(PitFrame(int(p[1]), int(p[2]), int(p[3], 16), int(p[4]), int(p[5]), float(p[6]), float(p[7]), int(p[8]),
                            float(p[9]), int(p[10]), int(p[11]), int(p[12]), crew, int(p[13], 16), int(p[14])))
    return out


class CrewPush(NamedTuple):
    """One D line of crewdraw_log.lua (Phase 26 stage 4, Task 5): a word the crew's animation pushed to the TGP through a figure
    routine (`figrootx`, `figrootz`, `figrot0`, `figrot2`) during a pit stop."""
    frame: int          # as PitFrame.frame
    crew: int           # pool object 0-5 of [0x501350] (R25)
    pc: int             # the V60 PC of the write: inside the routine that pushed it
    word: int           # the 32-bit FIFO word


def parse_crew_draw_log(path: Path) -> list[CrewPush]:
    """The D lines of crewdraw_log.lua (VR_CREW_DRAW_LOG); other and incomplete lines are skipped."""
    out = []
    for line in open(path):
        p = line.split()
        if len(p) == 5 and p[0] == "D" and len(p[4]) == 8:
            out.append(CrewPush(int(p[1]), int(p[2]), int(p[3], 16), int(p[4], 16)))
    return out


class EdgeSample(NamedTuple):
    frame: int
    car: int
    quad: int           # +0x30 when the 0x1500 call's parameters were written (+0x101 tap)
    x: float            # +0x1e, from its bits
    z: float            # +0x26, from its bits
    values: tuple[int, ...]       # the six words in return order: +0xf1 +0xed +0xf5 +0xf9 +0xfd +0x101, raw
    attr_quad: int      # +0x30 when +0xeb was written
    attr: int           # +0xeb, the halfword (+0xeb..+0xec)
    edge_frame: int     # the frame of the 0x1500 snapshot (quad, x, z, values); 0 if none yet
    attr_frame: int     # the frame of the +0xeb snapshot (attr_quad, attr); 0 if none yet

    @property
    def fresh(self) -> bool:
        """The edge values were taken in this line's frame: seven of the fourteen direction sites are not preceded by a
        0x1500 call, and a line written for an attribute store alone carries an earlier frame's quad, x, z and values."""
        return self.edge_frame == self.frame


def _f32_bits(u: int) -> float:
    return struct.unpack("<f", struct.pack("<I", u))[0]


def parse_edges(path: Path) -> list[EdgeSample]:
    """E lines from edges_log.lua (Phase 26): frame, car and the two snapshot frames decimal, every other number raw hex; x and
    z are decoded from their float bits. Frames count from 1 (fieldtrace.lua's from 0)."""
    out = []
    for line in open(path):
        p = line.split()
        if p and p[0] == "E" and len(p) == 16:
            out.append(EdgeSample(int(p[1]), int(p[2]), int(p[3], 16), _f32_bits(int(p[4], 16)), _f32_bits(int(p[5], 16)),
                                  tuple(int(v, 16) for v in p[6:12]), int(p[12], 16), int(p[13], 16), int(p[14]), int(p[15])))
    return out


def parse_hudmap(path: Path) -> dict:
    """hudmap_log.lua's one-shot record: {"tx", "ty"} (the HUD map section's screen translate), "ram" (the loader's
    three words: map translate, cross offset, off-course limit) and "cells" {(col, row): tile word} for the cross's
    possible places (columns 48..50 and 59..61, rows 21..23)."""
    out: dict = {"cells": {}}
    for line in open(path):
        p = line.split()
        if p and p[0] == "T":
            out["tx"], out["ty"] = float(p[1]), float(p[2])
        elif p and p[0] == "R":
            out["ram"] = (float(p[1]), int(p[2]), int(p[3]))
        elif p and p[0] == "H":
            row = int(p[1])
            for col, word in zip((48, 49, 50, 59, 60, 61), p[2:]):
                out["cells"][(col, row)] = int(word, 16)
    return out


def _no_hit(s: CollisionSample) -> bool:
    """The TGP found no quad under the car: it answers height 0 while the car is still well above 0."""
    return s.id == 0 or (s.result_y == 0.0 and s.y > 1.0)


def course_of(path: Path) -> tuple[int, int] | None:
    """(menu index [0x501940], data index [0x501934]) from the last S line of a collision log, or None. With the
    ten-course directory the data index is the entry's template (Phase 7)."""
    last = None
    for line in open(path):
        p = line.split()
        if p and p[0] == "S" and len(p) >= 4:
            last = (int(p[2], 16), int(p[3], 16))
    return last


def drive_summary(samples: list[CollisionSample]) -> dict:
    """calls, XZ distance travelled, off-road samples (id 0), no-hit samples (listed cell but no quad under the car),
    unanswered samples (NaN result), and for the stretch before the car first left the quads: its height range
    (ymin / ymax), calls and distance (onroad_calls / onroad_distance)."""
    dist = sum(math.hypot(b.x - a.x, b.z - a.z) for a, b in zip(samples, samples[1:]))
    answered = [s for s in samples if not math.isnan(s.result_y)]
    first_off = next((i for i, s in enumerate(samples) if math.isnan(s.result_y) or _no_hit(s)), len(samples))
    head = samples[:first_off]                       # the stretch before the car first left the quads
    return {"calls": len(samples), "distance": dist,
            "offroad": sum(1 for s in samples if s.id == 0),
            "nohit": sum(1 for s in answered if s.id and _no_hit(s)),
            "noanswer": len(samples) - len(answered),
            "ymin": min(s.result_y for s in head) if head else None, "ymax": max(s.result_y for s in head) if head else None,
            "onroad_calls": len(head),
            "onroad_distance": sum(math.hypot(b.x - a.x, b.z - a.z) for a, b in zip(head, head[1:]))}


def write_centreline(path: Path, points) -> Path:
    """A centreline CSV ("x,z" per line, lap order) for autopilot.lua (VR_AUTOPILOT)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{x:.3f},{z:.3f}\n" for x, z in points))
    return path


def lap_progress(samples: list[CollisionSample], arc, length: float) -> dict:
    """Progress along a lap: `arc(x, z)` gives the lap coordinate of a point. Returns forward distance, backward
    distance, the share of forward steps and the number of laps completed (wraps of the coordinate)."""
    arcs = [arc(s.x, s.z) for s in samples]
    fwd = back = 0.0
    wraps = 0
    for a, b in zip(arcs, arcs[1:]):
        d = (b - a + length / 2) % length - length / 2
        if d > 0:
            fwd += d
        else:
            back -= d
        if a > 0.8 * length and b < 0.2 * length:
            wraps += 1
    steps = len(arcs) - 1
    forward_share = sum(1 for a, b in zip(arcs, arcs[1:]) if 0 <= (b - a + length / 2) % length - length / 2) / steps if steps else 0.0
    return {"forward": fwd, "backward": back, "forward_share": forward_share, "laps": wraps, "last_arc": arcs[-1] if arcs else None}


DUMP_STEP = 250                      # frames between RAM dumps in a race run (memtrace.lua VR_TRACE_DUMP)
PARKED_DUMPS = 8                     # an opponent with no road-point change over this many dumps (35 s) counts as parked
CLOCK = 0x50116C                     # race clock, 1/32 s on the HUD (M6 recon)
ELAPSED = 0x501168
TIME_RECORD_PTR = 0x501968
CHECKPOINT_RECORD_PTR = 0x50195C
LAPS_SETTING = 0x5011A4
CAR_POOL = 0x400D00                  # entity 0 = the player; opponents follow at CAR_STRIDE
CAR_STRIDE = 0x280
CAR_ROAD_POINT, CAR_LAP, CAR_CHECKPOINTS, CAR_CURSOR = 0xA6, 0x1B5, 0x57, 0xE1
RAM_DUMP_BASE, POOL_DUMP_BASE = 0x500000, 0x400000


def race_report(workdir: Path, n_points: int) -> dict:
    """From a run's RAM dumps (`trace.log.ram.<frame>.bin` / `.nvram.`): the clock per dump, the number of clock
    increases (checkpoint extensions), the first frame with the clock expired (or None), the player's laps, the
    leader's pace in road points per second and road points gained, each opponent's progress per dump (`cars`,
    unwrapped from its road point over the race window: first running clock to expiry), how many opponents gained
    at least 100 points (`moved`), the largest drop between dumps (`max_backstep`), the largest lead of an opponent's
    line cursor over its road point during the race (`max_cursor_lead`, points: the originals stay within 4; a cursor
    far ahead means it ran away at the start line), the opponents parked for good (`parked`, `parked_cars`: no
    progress over the last PARKED_DUMPS dumps of the race window), the number of opponents sitting
    at the world origin at the race start (a bad line pointer), the lap setting and
    the two per-course record pointers (read at the second dump inside the race: before it the attract mode's course
    was loaded, after the race the game may load another one)."""
    import glob
    import struct
    workdir = Path(workdir)
    dumps = sorted(glob.glob(str(workdir / "trace.log.ram.*.bin")), key=lambda p: int(p.split(".")[-2]))
    if not dumps:
        raise MameError(f"no RAM dumps in {workdir}")
    clocks, frames, leader = [], [], []
    player_laps = 0
    at_origin = None
    rps = []                                   # per dump: the 15 opponents' road points (progress is unwrapped from these:
                                               # the opponents' lap byte is not reliable at the grid)
    leads = []                                 # per dump: the largest cursor lead over the road point among the opponents
    for p in dumps:
        frame = int(p.split(".")[-2])
        ram = Path(p).read_bytes()
        pool = Path(p.replace(".ram.", ".nvram.")).read_bytes()
        rd = lambda a, fmt: struct.unpack_from(fmt, ram, a - RAM_DUMP_BASE)[0]
        clocks.append(rd(CLOCK, "<i"))
        frames.append(frame)
        progress = []
        for car in range(16):
            base = CAR_POOL + CAR_STRIDE * car - POOL_DUMP_BASE
            lap = pool[base + CAR_LAP]
            lap = lap - 256 if lap > 127 else lap
            rp = struct.unpack_from("<H", pool, base + CAR_ROAD_POINT)[0]
            progress.append(lap * n_points + rp)
            if car == 0:
                player_laps = max(player_laps, lap)
        leader.append(max(progress[1:]))
        rps.append(progress[1:])
        lead = 0
        for car in range(1, 16):
            base = CAR_POOL + CAR_STRIDE * car - POOL_DUMP_BASE
            cur = struct.unpack_from("<h", pool, base + CAR_CURSOR)[0] // 16
            rp = struct.unpack_from("<h", pool, base + CAR_ROAD_POINT)[0]
            d = (cur - rp + n_points // 2) % n_points - n_points // 2
            lead = max(lead, d)
        leads.append(lead)
        if clocks[-1] > 0 and at_origin is None:          # opponents spawned at the world origin (a bad line pointer)
            at_origin = sum(1 for car in range(1, 16)
                            if max(abs(v) for v in struct.unpack_from("<3f", pool, CAR_POOL + CAR_STRIDE * car - POOL_DUMP_BASE + 0x1E)) < 20.0)
        in_race = len([c for c in clocks if c > 0])
        if clocks[-1] > 0 and in_race <= 2:            # the second dump inside the race (or the first if there is no second): before
            last = (rd(LAPS_SETTING, "<B"), rd(TIME_RECORD_PTR, "<I"), rd(CHECKPOINT_RECORD_PTR, "<I"))   # the race the attract's course
            # is loaded, after it the game may load another one; a race that started just before a dump leaves its pointers stale in it
    if clocks and not any(c > 0 for c in clocks):
        raise MameError(f"the race never started in {workdir}")
    started = [i for i, c in enumerate(clocks) if c > 0]
    extensions = sum(1 for a, b in zip(clocks, clocks[1:]) if b > a > 0)
    expired = next((f for f, c in zip(frames, clocks) if c < 0), None)
    # the race window: from the first dump with a running clock to the last before it expired (after that the attract
    # mode may run its own race); progress per opponent unwrapped from its road point alone
    race = [i for i, c in enumerate(clocks) if c > 0]
    if expired is not None:
        race = [i for i in race if frames[i] < expired]
    cars = []
    for car in range(15):
        prog, cum = [], 0
        for k, i in enumerate(race):
            rp = rps[i][car] % n_points
            if k:
                d = rp - (rps[race[k - 1]][car] % n_points)
                if d < -n_points // 2:
                    d += n_points
                elif d > n_points // 2:
                    d -= n_points
                cum += d
            prog.append(cum)
        cars.append(prog)
    gains = [c[-1] - c[0] for c in cars if len(c) > 1]
    moved = sum(1 for g in gains if g >= 100)
    tail = PARKED_DUMPS
    parked_cars = [car + 1 for car, c in enumerate(cars) if len(c) > tail and c[-1] == c[-1 - tail]]   # no progress over the last dumps
    backsteps = [a - b for c in cars for a, b in zip(c, c[1:])]
    max_backstep = max([0] + backsteps)
    max_lead = max([leads[i] for i in race] or [0])
    gained = max(gains) if gains else 0
    if len(race) > 1:
        pace = gained / ((frames[race[-1]] - frames[race[0]]) / 57.52)
    else:
        pace = 0.0
    return {"clock": clocks, "frames": frames, "extensions": extensions, "expired_at": expired, "player_laps": player_laps,
            "leader_points_per_s": round(pace, 2), "leader_points": gained, "opponents_at_origin": at_origin or 0,
            "cars": cars, "moved": moved, "max_backstep": max_backstep, "max_cursor_lead": max_lead,
            "parked": len(parked_cars), "parked_cars": parked_cars,
            "laps_setting": last[0], "time_record": last[1], "checkpoint_record": last[2]}
