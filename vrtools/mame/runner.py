"""Run MAME headless on the `vr` set with a Lua autoboot script."""

from __future__ import annotations

import math
import os
import subprocess
from pathlib import Path
from typing import NamedTuple

LUA_DIR = Path(__file__).resolve().parent / "lua"


class MameError(Exception):
    pass


def run_mame(script: Path, seconds: int, workdir: Path, rom_dir: Path, env: dict[str, str] | None = None,
             mame: str = "mame", timeout: float | None = None, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run MAME headless for `seconds` emulated seconds with the Lua `script`; MameError when it fails or, with
    `timeout` (wall-clock seconds), when it does not end in time (it is killed). `extra_args` go at the end of the
    command (e.g. `["-aviwrite", "run.avi"]`: MAME writes the AVI under its snapshot directory, with sound)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [mame, "vr", "-rompath", str(rom_dir), "-video", "none", "-sound", "none", "-window",
           "-nothrottle", "-str", str(seconds), "-skip_gameinfo", "-autoboot_script", str(script),
           "-snapshot_directory", str(workdir / "snap"), "-nvram_directory", str(workdir / "nvram"),
           "-cfg_directory", str(workdir / "cfg")] + list(extra_args or [])
    full_env = {**os.environ, "VR_LUA_DIR": str(LUA_DIR), **(env or {})}
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
