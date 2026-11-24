"""Run MAME headless on the `vr` set with a Lua autoboot script."""

from __future__ import annotations

import math
import os
import struct
import subprocess
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NamedTuple

LUA_DIR = Path(__file__).resolve().parent / "lua"


class MameError(Exception):
    pass


class MameKilledWarning(UserWarning):
    """A MAME run ended by SIGKILL from outside the runner (not its own timeout), run once more (`run_mame`)."""


# Weather stage 1, round 2: no real input device reaches a run. With the providers left at their defaults MAME reads the host's
# keyboard, mouse (buttons mapped to keys), light guns and joysticks even with no window, and a key mapped to the gas pedal put a
# gas edge into a test run. The scripts set the ports themselves (Lua `set_value`) and `-playback` feeds a recorded file; neither
# goes through a provider.
INPUT_PROVIDERS_OFF = ("-keyboardprovider", "none", "-mouseprovider", "none", "-lightgunprovider", "none", "-joystickprovider", "none")


def mame_command(rom_dir: Path, seconds: int, script: Path, workdir: Path, extra_args: list[str] | None = None,
                 mame: str = "mame") -> list[str]:
    """The headless command of a test run: no video, no sound, no real input device (INPUT_PROVIDERS_OFF), unthrottled for
    `seconds` emulated seconds with the Lua `script`, snapshots, battery RAM and settings in `workdir`; `extra_args` at the end."""
    workdir = Path(workdir)
    return ([mame, "vr", "-rompath", str(rom_dir), "-video", "none", "-sound", "none", "-window", *INPUT_PROVIDERS_OFF,
             "-nothrottle", "-str", str(seconds), "-skip_gameinfo", "-autoboot_script", str(script),
             "-snapshot_directory", str(workdir / "snap"), "-nvram_directory", str(workdir / "nvram"),
             "-cfg_directory", str(workdir / "cfg")] + list(extra_args or []))


_SLOTS: dict[int, threading.BoundedSemaphore] = {}
_SLOTS_LOCK = threading.Lock()


def _slot():
    """VR_MAME_JOBS=n: at most n MAME processes of this Python process run at once (the test sessions start theirs in parallel
    threads); unset, no limit."""
    n = os.environ.get("VR_MAME_JOBS")
    if not n:
        return nullcontext()
    try:
        k = int(n)
    except ValueError:
        k = 0
    if k <= 0:
        raise MameError(f"VR_MAME_JOBS must be a positive integer, not {n!r}")
    with _SLOTS_LOCK:
        return _SLOTS.setdefault(k, threading.BoundedSemaphore(k))


_SNAP_SEQ = __import__("itertools").count()      # the safety copies' numbers in this process (thread-safe enough: next() under the GIL)
_SWEPT: set = set()                              # the directories this process has swept (`_sweep_once`)
_SWEPT_LOCK = threading.Lock()
_WINDOWS = os.name == "nt"                       # the system the sweep runs on (a module flag a test can patch, not os.name)


def _alive(pid: int) -> bool:
    """Whether process `pid` lives (the safety copies' sweep). On Windows there is no existence probe in the standard library
    (`os.kill(pid, 0)` sends CTRL_C_EVENT there) and no dependency is added for one: every process counts as alive, so the sweep
    removes nothing there (a dead session's copy stays until a sweep on another system or by hand)."""
    if _WINDOWS:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:                     # another user's live process
        return True
    except OSError:
        return False
    return True


def sweep_snapshots(root: Path) -> int:
    """Remove the safety copies run_mame's dead processes left under `root` (`.<name>.snap-<pid>-<n>` directories whose process no
    longer lives; a live process's copies are kept); returns how many went."""
    import re
    import shutil
    n = 0
    for p in Path(root).rglob(".*.snap-*"):
        m = re.fullmatch(r"\..+\.snap-(\d+)-\d+", p.name)
        if m and p.is_dir() and not p.is_symlink() and not _alive(int(m.group(1))):
            shutil.rmtree(p, ignore_errors=True)
            n += 1
    return n


def _sweep_once(d: Path) -> None:
    """At the first run beside `d` in this process: the dead processes' copies directly in `d` swept."""
    import re
    import shutil
    d = Path(d).resolve()
    with _SWEPT_LOCK:
        if d in _SWEPT:
            return
        _SWEPT.add(d)
    for p in d.iterdir():
        m = re.fullmatch(r"\..+\.snap-(\d+)-\d+", p.name)
        if m and p.is_dir() and not p.is_symlink() and not _alive(int(m.group(1))):
            shutil.rmtree(p, ignore_errors=True)


def run_mame(script: Path, seconds: int, workdir: Path, rom_dir: Path, env: dict[str, str] | None = None,
             mame: str = "mame", timeout: float | None = None, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run MAME headless for `seconds` emulated seconds with the Lua `script`; MameError when it fails or, with
    `timeout` (wall-clock seconds), when it does not end in time (it is killed). `extra_args` go at the end of the
    command (e.g. `["-aviwrite", "run.avi"]`: MAME writes the AVI under its snapshot directory, with sound). The scripts get
    VR_LUA_DIR, (Phase 26 stage 3) VR_REVERSE_TABLE, the reverse table's address in this tree's directory layout (hex), with
    which autoplay.lua knows the courses whose lock opens the COURSE DIRECTION screen, and (weather stage 1) VR_WEATHER_SELECT
    and VR_WEATHER_WORD, where the COURSE WEATHER screen's first routine lies and its first word (hex), with which it knows a
    set that has that screen; `env` overrides any of them. With VR_MAME_JOBS
    set in the environment, at most that many of these calls run MAME at once (`_slot`). Round 2 of weather stage 1: the command
    is `mame_command`'s (no real input device); a run that MAME ends with SIGKILL (exit status -9; POSIX only: where the signal
    module has no SIGKILL, as on Windows, no status is told apart and every failing one raises) sent from outside the runner
    (its own timeout raises before any status is read) is run once more from the work directory as it was before the first
    attempt, with a MameKilledWarning naming it; a second -9, any other failing status and the timeout raise MameError at once.
    That copy (weather Task 6J) lies beside the work directory, on its volume (`.<name>.snap-<pid>-<n>`), never in the system temp
    folder, and is removed in a `finally`; the first run beside a directory in a process sweeps the copies that dead processes left
    there (`sweep_snapshots`)."""
    import shutil
    import signal
    import warnings
    from vrtools.arcade.directory import directory_layout
    killed = getattr(signal, "SIGKILL", None)           # absent on Windows: no status there counts as "killed from outside"
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    _sweep_once(workdir.parent)
    cmd = mame_command(rom_dir, seconds, script, workdir, extra_args, mame)
    from vrtools.arcade.weather import screen as weather_screen
    from vrtools.arcade.weather.layout import block as weather_block
    full_env = {**os.environ, "VR_LUA_DIR": str(LUA_DIR), "VR_REVERSE_TABLE": f"{directory_layout()['reverse']:x}",
                "VR_WEATHER_SELECT": f"{weather_block('screen code').start:x}",
                "VR_WEATHER_WORD": f"{int.from_bytes(weather_screen.SIGNATURE, 'little'):x}", **(env or {})}
    before = workdir.parent / f".{workdir.name}.snap-{os.getpid()}-{next(_SNAP_SEQ)}"
    try:
        shutil.copytree(workdir, before, symlinks=True)          # the work directory as the caller left it (a retry starts from it)
        for attempt in (1, 2):
            try:
                with _slot():
                    proc = subprocess.run(cmd, cwd=workdir, env=full_env, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as e:
                raise MameError(f"mame did not end within {timeout} s and was killed") from e
            except FileNotFoundError as e:                       # no such program: say so instead of the system's own error
                raise MameError(f"{mame!r} was not found: MAME 0.289 must be on the PATH (mame.exe on Windows)") from e
            if killed is not None and proc.returncode == -killed and attempt == 1:
                warnings.warn(f"mame was killed (SIGKILL) from outside the runner in {workdir}; run once more from the work directory "
                              f"as it was", MameKilledWarning, stacklevel=2)
                for p in workdir.iterdir():
                    shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
                shutil.copytree(before, workdir, symlinks=True, dirs_exist_ok=True)
                continue
            break
    finally:
        shutil.rmtree(before, ignore_errors=True)
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


DISPLAY_LISTS = (0x60, 0x61)        # the two display lists, 0x600000 and 0x610000, by the address's top byte


def parse_stale_log(path: Path) -> list[int]:
    """The frames of the passes that wrote the same display list as the pass before them (a stale picture: MAME shows the other
    list, frozen, on every second render), from stale_list.lua's L lines (the frame, the list pointer 0x5017f4 at the pass's end).
    A pointer outside both lists (the boot's 0) is no list and breaks the sequence. ValueError when the log holds no list at all:
    a run that measured nothing passes nothing."""
    stale, prev, seen = [], None, 0
    for line in open(path):
        parts = line.split()
        if len(parts) != 3 or parts[0] != "L":
            continue
        lst = int(parts[2], 16) >> 16
        if lst not in DISPLAY_LISTS:
            prev = None
            continue
        seen += 1
        if lst == prev:
            stale.append(int(parts[1]))
        prev = lst
    if not seen:
        raise ValueError(f"{path}: no pass wrote a display list")
    return stale


class StormPass(NamedTuple):
    """storm_log.lua's S line: the storm's carrier and rain at a pass's end (weather/carrier.py, weather/rain.py)."""
    frame: int
    state: int          # carrier.STATE: 0 idle, 1 starting, 2 show
    switch: int         # carrier.SWITCH
    loads: int          # the carrier's counters (cumulative)
    starts: int
    shows: int
    sbr: int            # the V60's vector table base
    drawn: int          # clusters drawn this pass
    splashes: int       # splashes drawn this pass
    late: int           # the rain's late passes (cumulative), then its trims (cumulative): budget clusters, splashes; late
                        # (the vblank-count guard) clusters, splashes
    trim_cl: int
    trim_sp: int
    trim_lcl: int
    trim_lsp: int
    primed: int         # clusters placed by the start passes
    active: int         # 1 from the rain's first visible pass
    xleft: int          # the grade's rows still to make
    rec_in: int         # the frame's record count before the rain, after it
    rec_out: int


class StormLog(NamedTuple):
    passes: list
    traces: list        # (frame, writes into the storm RAM, first pc, its address, timer writes)
    frames: list        # VR_STORM_FRAMES: (frame, mode, state, switch, SBR) at each frame end where one changed
    after: dict         # frame -> microseconds from the vblank count's move to the pass's end (the passes it moved in)
    dumps: dict         # frame -> {"X": 96 x 64 colour-RAM halfwords, "P": 512 backdrop colours; VR_STORM_FULL: "Q" the palette RAM,
                        # "M" the tile maps 0x700000..0x707fff (halfwords)}
    watch: dict         # VR_STORM_WATCH: frame -> the word there at the pass's end
    # (a NamedTuple cannot take dataclasses' default_factory: the defaults below are immutable empties, never a shared list / dict;
    # parse_storm_log always passes its own)
    cover: tuple = ()   # VR_STORM_COVER / VR_STORM_UC (weather stage 3): a CoverPass per pass
    trip: Mapping = MappingProxyType({})     # B lines (the join): frame -> (us from the count's move to the guard's trip, us from the
                                             # trip to the pass's end)
    watches: Mapping = MappingProxyType({})  # VR_STORM_WATCH with several addresses (the join): frame -> every word, in order
                                             # (`watch` the first)
    list_hw: Mapping = MappingProxyType({})  # L lines (the final review's W9): frame -> the display list's high-water mark in the
                                             # pass, bytes from its buffer's start
    load_psw: tuple = ()                     # I lines (Task 7): (frame, the PSW at a load's entry), one per load


class CoverPass(NamedTuple):
    """storm_log.lua's C line: the cover's state at a pass's end (weather/cover.py)."""
    frame: int
    mode: int           # 0 no cover near, 1 near (camera outside), 2 inside (no exit in view), 3 inside, the curtain at a mouth
    under_cover: int
    hidden: int         # clusters the cover hid this pass
    curtain: int        # curtain clusters left to the rain to draw this pass
    drops: int          # single drops the cover drew this pass (the pits roof's edges)
    placed: int         # curtain placements this pass
    roof: int           # nonzero under the pits roof's curtain
    walk: int           # clusters the rain walked
    nosplash: int
    late: int           # the cover's late passes (cumulative)
    spawns: int         # the rain's splashes spawned (cumulative)
    cx: float           # the camera's world position
    cy: float
    cz: float
    box: int            # the box holding the camera (RAM), 0 none
    drawn: int          # the rain's clusters drawn this pass
    py: float = float("nan")    # the player's car's y (fix round 1; nan in older logs)


def parse_storm_log(path: Path) -> StormLog:
    """storm_log.lua's S, T, A, B, F, W, C, L, I, X, P, Q and M lines; other and incomplete lines are skipped."""
    passes, traces, dumps, frames, after, watch, cover, trip, watches, list_hw, load_psw = [], [], {}, [], {}, {}, [], {}, {}, {}, []
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == "S" and len(p) == 20:
            v = [int(x, 16) if k == 7 else int(x) for k, x in enumerate(p)  if k > 0]
            passes.append(StormPass(*v))
        elif p[0] == "T" and len(p) == 6:
            traces.append((int(p[1]), int(p[2]), int(p[3], 16), int(p[4], 16), int(p[5])))
        elif p[0] == "A" and len(p) == 3:
            after[int(p[1])] = float(p[2])
        elif p[0] == "B" and len(p) == 4:
            trip[int(p[1])] = (float(p[2]), float(p[3]))
        elif p[0] == "L" and len(p) == 3:
            list_hw[int(p[1])] = int(p[2])
        elif p[0] == "I" and len(p) == 3:
            load_psw.append((int(p[1]), int(p[2], 16)))
        elif p[0] == "W" and len(p) >= 3:
            watch[int(p[1])] = int(p[2], 16)
            watches[int(p[1])] = tuple(int(x, 16) for x in p[2:])
        elif p[0] == "C" and len(p) in (18, 19):
            cover.append(CoverPass(*(int(x, 16) if k == 15 else float(x) if k in (12, 13, 14, 17) else int(x) for k, x in enumerate(p[1:]))))
        elif p[0] == "F" and len(p) == 6:
            frames.append((int(p[1]), int(p[2], 16), int(p[3]), int(p[4]), int(p[5], 16)))
        elif p[0] in ("X", "P", "Q", "M") and len(p) == 3:
            h = p[2]
            dumps.setdefault(int(p[1]), {})[p[0]] = [int(h[i:i + 4], 16) for i in range(0, len(h), 4)]
    return StormLog(passes=passes, traces=traces, frames=frames, dumps=dumps, after=after, watch=watch, cover=cover, trip=trip,
                    watches=watches, list_hw=list_hw, load_psw=tuple(load_psw))


class HandlingFrame(NamedTuple):
    """handling_log.lua's F line (weather stage 5): the player's handling at a frame end, the handling module's cells, the opponents'
    working performance."""
    frame: int
    rel: int            # frames from the race start (autoplay.lua's: the first race's load)
    race: int           # the run's race (1, 2, ...: counted at each countdown's start)
    mode: int
    handler: int
    flags: int
    gas: int
    brake: int
    gear: int           # +0x156: 0 = first gear
    kmh: int
    traction: float     # +0x5c
    lock_timer: int     # +0x64 (the game's lock sound and smoke)
    smoke: int          # +0x65 (the game's wheelspin smoke)
    yaw: int
    path: int           # +0x36, the heading the car travels along
    lat: int            # L, +0x154
    slide: int          # S, +0x14e
    grip: int           # +0x164
    spinout: int        # +0x6c
    crash: int          # +0x56
    x: float
    z: float
    covered: int        # bit 7 of +0x152 (the tunnel flag)
    pit: int            # +0x191
    glide: int          # 0x501160
    road_point: int     # +0xa6
    lap: int
    engine: int         # 0x503004, the engine sound's command
    squeal: int         # 0x503008, the squeal's command
    switch: int         # carrier.SWITCH
    lock: int           # the handling's cells (0 when not logged): the lock, the spin cool-down, the slip mark, the lock count,
    cool: int           # the engine note, then its counters
    slip: int
    lock_count: int
    note: int
    spins: int
    locks: int
    locked_frames: int
    slip_frames: int
    steer_skips: int
    opponents: tuple    # the fifteen opponents' +0x48 (the float's bits)
    rpm: int = 0        # +0x15a
    opp_base: tuple = ()    # the fifteen opponents' +0x3c (their base performance, the float's bits)
    player_perf: int = 0    # the player's own +0x48 (the float's bits: the opponents' site stores it for the player too)


class HandlingLog(NamedTuple):
    frames: list
    laps: list          # (frame, rel, car, lap) at each change of a car's lap counter
    triggers: list      # (frame, rel, trigger, port)
    calls: list         # VR_HANDLING_STUBS: (frame, (calls of each stub in that frame))
    trace: Mapping = MappingProxyType({})    # VR_HANDLING_TRACE: (site index, exit) -> (calls, median us, mean us, min us, max us)
                                             # (an immutable empty default: never a shared dict)


def parse_handling_log(path: Path) -> HandlingLog:
    """handling_log.lua's F, L, T and C lines; other and incomplete lines are skipped."""
    frames, laps, triggers, calls, trace = [], [], [], [], {}
    hexes = {3, 4, 5, 27, 28}
    floats = {10, 20, 21}
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == "F" and len(p) == 45:
            v = [int(x, 16) if k in hexes else float(x) if k in floats else int(x) for k, x in enumerate(p[1:41])]
            frames.append(HandlingFrame(*v, tuple(int(h, 16) for h in p[41].split(",")), int(p[42]),
                                        tuple(int(h, 16) for h in p[43].split(",")), int(p[44], 16)))
        elif p[0] == "L" and len(p) == 5:
            laps.append(tuple(int(x) for x in p[1:]))
        elif p[0] == "T" and len(p) == 5:
            triggers.append((int(p[1]), int(p[2]), p[3], p[4]))
        elif p[0] == "C" and len(p) > 2:
            calls.append((int(p[1]), tuple(int(x) for x in p[2:])))
        elif p[0] == "P" and len(p) == 8:
            trace[(int(p[1]), int(p[2]))] = (int(p[3]), float(p[4]), float(p[5]), float(p[6]), float(p[7]))
    return HandlingLog(frames=frames, laps=laps, triggers=triggers, calls=calls, trace=trace)


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


def parse_weather_log(path: Path) -> dict[int, list[tuple[int, tuple[int, ...]]]]:
    """P lines from weather_log.lua (weather stage 1): per palette number, its (frame, 16 words) at every frame end it changed."""
    out: dict[int, list[tuple[int, tuple[int, ...]]]] = {}
    for line in open(path):
        p = line.split()
        if p and p[0] == "P" and len(p) == 19:
            out.setdefault(int(p[2], 16), []).append((int(p[1]), tuple(int(v, 16) for v in p[3:])))
    return out


def palette_at(log: dict[int, list[tuple[int, tuple[int, ...]]]], palette: int, frame: int) -> tuple[int, ...] | None:
    """Palette `palette`'s words at the end of `frame` by a parse_weather_log result (None before its first line)."""
    seen = [w for f, w in log.get(palette, []) if f <= frame]
    return seen[-1] if seen else None


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


class HudRows(NamedTuple):
    """One R line of hudrows_log.lua (Phase 32): layer 0's rows 44-47, all 64 columns."""
    frame: int          # counted from 1 at the first frame end, as autoplay.lua counts
    mode: int           # 0x501138
    tag: str            # load, race, lap, goal, m, m30 (hudrows_log.lua)
    race: int           # the session's race, from 1
    rows: dict[int, tuple[int, ...]]        # row (44-47) -> its 64 tile words


def parse_hudrows_log(path: Path) -> tuple[list[HudRows], dict[int, int]]:
    """hudrows_log.lua's lines: the R lines, and {race: writes} from the T lines (the writes to rows 44-47 from column 19 on,
    from the race line to the race's end: each race's last T line). Incomplete lines are skipped (MAME can end a run in the
    middle of a line)."""
    rows, writes = [], {}
    for line in open(path):
        p = line.split()
        if p and p[0] == "R" and len(p) == 5 + 4 * 64:
            w = tuple(int(v, 16) for v in p[5:])
            rows.append(HudRows(int(p[1]), int(p[2], 16), p[3], int(p[4]), {44 + k: w[64 * k:64 * k + 64] for k in range(4)}))
        elif p and p[0] == "T" and len(p) == 4:
            writes[int(p[2])] = int(p[3])
    return rows, writes


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


SOUND_HIGH_PC = 0xFFA2A6            # Phase 37: the instruction that writes a sound command's high byte to the latch 0xc40000 ...
SOUND_LOW_PC = 0xFFA36A             # ... and the one that writes its low byte, a logic frame later
SOUND_TUNNEL_ON, SOUND_TUNNEL_OFF, SOUND_RESET = 0xC201, 0xC200, 0x8100
RACE_MODE = 0x14                    # the mode byte 0x501139 from the green to the race's end
PLAYER_HANDLER = 0xFE8E18           # the player's handler in a race (stage 4 recon: the pit release restores it)


class SoundFlag(NamedTuple):
    """One F line of sound_log.lua: the player at a frame end at which the mode, the gate, the handler, the quad or a flag changed."""
    frame: int
    mode: int           # 0x501139
    gate: int           # 0x501120 (bits 18 and 20 let a race sound through 0xffa24b)
    handler: int        # +0xa
    quad: int           # +0x30, the lap-position quad whose segment flag the player copies
    flag: int           # +0x152, that flag
    previous: int       # +0x195, last logic frame's copy
    road_point: int     # +0xa6


class SoundLog(NamedTuple):
    commands: list[tuple[int, int]]      # (frame of the low byte, 16-bit command) in the order sent
    flags: list[SoundFlag]
    complete: bool                       # the log ends with END

    def tunnel(self) -> list[tuple[int, int]]:
        """The commands that move the sound board's tunnel bit: C201 sets it, C200 and the reset 8100 clear it."""
        return [(f, c) for f, c in self.commands if c in (SOUND_TUNNEL_ON, SOUND_TUNNEL_OFF, SOUND_RESET)]

    def bit_at(self, frame: int) -> int:
        """The sound board's tunnel bit after every command sent up to `frame` (0 at power-on: the board's own reset clears it)."""
        bit = 0
        for f, c in self.tunnel():
            if f > frame:
                break
            bit = 1 if c == SOUND_TUNNEL_ON else 0
        return bit


def parse_sound_log(path: Path) -> SoundLog:
    """sound_log.lua's log (VR_SOUND_LOG). A command is a high byte from SOUND_HIGH_PC followed by the next byte from SOUND_LOW_PC;
    MameError for any other byte or order (the boot's own writes before the game runs, from other PCs, are skipped)."""
    commands, flags, high, complete = [], [], None, False
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == "END":
            complete = True
        elif p[0] == "S" and len(p) == 4:
            frame, byte, pc = int(p[1]), int(p[2], 16), int(p[3], 16)
            if pc == SOUND_HIGH_PC:
                if high is not None:
                    raise MameError(f"{path}: two high bytes in a row at frame {frame}")
                high = byte
            elif pc == SOUND_LOW_PC:
                if high is None:
                    raise MameError(f"{path}: a low byte without its high byte at frame {frame}")
                commands.append((frame, high << 8 | byte))
                high = None
        elif p[0] == "F" and len(p) == 9:
            flags.append(SoundFlag(int(p[1]), *(int(v, 16) for v in p[2:8]), int(p[8])))
    return SoundLog(commands, flags, complete)


class PcmWrite(NamedTuple):
    """One P line of pcm_log.lua: a data write to a MultiPCM voice's register."""
    frame: int
    time: float
    chip: int           # 1 or 2
    voice: int          # the voice selector (0..0x1f; 7, 15, 23, 31 select nothing)
    reg: int            # 0 pan, 1 sample, 2/3 pitch, 4 key (bit 7 on), 5 level (total level = value >> 1), 6/7 LFO
    value: int


class PcmLog(NamedTuple):
    """pcm_log.lua's log (weather stage 6): the sound board's MultiPCM writes and the V60's sound words, with emulated times."""
    writes: list[PcmWrite]
    words: list[tuple[int, float, int]]          # (frame of the low byte, its time, the 16-bit word), in the order sent
    modes: list[tuple[int, float, int]]          # (frame, time, mode 0x501138) where it changed
    frames: list[tuple[int, float]]              # (frame, time) of every frame end (frames count from 1 again after a reset)
    boots: list[float]                           # the times the script (re)started: a soft reset adds one
    complete: bool

    def voice(self, chip: int, voice: int) -> list[PcmWrite]:
        return [w for w in self.writes if w.chip == chip and w.voice == voice]

    def keyed(self, chip: int, voice: int, end: float | None = None) -> list[tuple[float, float]]:
        """[on, off) times of a voice's key (register 4 bit 7); a key still on at the log's end closes at `end` (default: the last
        frame's time)."""
        out, on = [], None
        for w in self.voice(chip, voice):
            if w.reg != 4:
                continue
            if w.value & 0x80 and on is None:
                on = w.time
            elif not w.value & 0x80 and on is not None:
                out.append((on, w.time))
                on = None
        if on is not None:
            out.append((on, end if end is not None else (self.frames[-1][1] if self.frames else on)))
        return out

    def level_at(self, chip: int, voice: int, t: float) -> int | None:
        """The voice's last level byte written before time `t` (None before any)."""
        lv = None
        for w in self.voice(chip, voice):
            if w.time >= t:
                break
            if w.reg == 5:
                lv = w.value
        return lv

    def mode_at(self, t: float) -> int | None:
        m = None
        for _, mt, mode in self.modes:
            if mt > t:
                break
            m = mode
        return m


def parse_pcm_log(path: Path) -> PcmLog:
    """pcm_log.lua's log (VR_PCM_LOG). A word is a high byte from SOUND_HIGH_PC followed by the next byte from SOUND_LOW_PC (bytes
    from other PCs, the boot's, are skipped; a high byte left without its low one by a reset is dropped)."""
    writes, words, modes, frames, boots, high, complete = [], [], [], [], [], None, False
    for line in open(path):
        p = line.split()
        if not p:
            continue
        k = p[0]
        if k == "P" and len(p) == 7:
            writes.append(PcmWrite(int(p[1]), float(p[2]), int(p[3]), int(p[4], 16), int(p[5], 16), int(p[6], 16)))
        elif k == "S" and len(p) == 5:
            byte, pc = int(p[3], 16), int(p[4], 16)
            if pc == SOUND_HIGH_PC:
                high = byte
            elif pc == SOUND_LOW_PC and high is not None:
                words.append((int(p[1]), float(p[2]), high << 8 | byte))
                high = None
        elif k == "M" and len(p) == 4:
            modes.append((int(p[1]), float(p[2]), int(p[3], 16)))
        elif k == "F" and len(p) == 3:
            frames.append((int(p[1]), float(p[2])))
        elif k == "B" and len(p) == 2:
            boots.append(float(p[1]))
            high = None
        elif k == "END":
            complete = True
    return PcmLog(writes, words, modes, frames, boots, complete)


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


# ---- weather stage 4: the lightning's log (lightning_log.lua) ----------------------------------------------------------------
def light_env(lay, wd: Path) -> dict:
    """autoplay.lua's environment for lightning_log.lua (weather stage 4) on a storm set laid out as `lay` (a carrier.Layout)."""
    from vrtools.arcade.weather import carrier, lightning
    tables = min(lay.tables.values())
    return {"VR_LIGHT_LOG": str(wd / "light.txt"), "VR_LIGHT_STATE": f"{lay.cell('lightning', 'state'):x}",
            "VR_LIGHT_WORDS": str(len(lightning.STATE_NAMES)), "VR_LIGHT_SEQ": f"{lay.cell('lightning', 'strike_seq'):x}",
            "VR_LIGHT_BAND": f"{lay.cell('lightning', 'strike_band'):x}", "VR_LIGHT_COVER": f"{lay.cell('cover', 'under_cover'):x}",
            "VR_LIGHT_IMAGE": f"{carrier.IMAGE[0]:x},{carrier.IMAGE[1]:x}",
            "VR_LIGHT_CODE": f"{lay.code('lightning'):x},{lay.code('rain'):x}", "VR_LIGHT_RAIN": f"{lay.code('rain'):x},{tables:x}",
            "VR_LIGHT_NSHOW": f"{carrier.NSHOW:x}"}


class LightPass(NamedTuple):
    """lightning_log.lua's L line: the lightning at a pass's end (weather/lightning.py)."""
    frame: int
    s: dict             # the state words by STATE_NAMES (ints; the float cells' bits)
    seq: int
    band: int
    cover: int
    sky: tuple          # backdrop colours 1..3 in palette RAM
    probes: tuple       # the colour RAM's two probes (the white-out's first and last rows)


class Gap(NamedTuple):
    """lightning_log.lua's G line: the pass's guard tests from the storm's code and the units between them."""
    tests: int
    gap_us: float
    pc: int
    light_us: float
    to_rain_us: float
    pre_us: float       # from the carrier's body (its show counter) to the pass's first guard test


def parse_light_log(path: Path, units: dict | None = None) -> tuple[list, dict]:
    """(the L lines as LightPass, the G lines by frame); `units` (when given) gets the U lines: pc -> (longest us, count)."""
    from vrtools.arcade.weather import lightning
    names = lightning.STATE_NAMES
    passes, gaps = [], {}
    for line in open(path):
        p = line.split()
        if p and p[0] == "L" and len(p) == 2 + len(names) + 8:
            w = [int(x, 16) for x in p[2:]]
            s = {n: (v - (1 << 32) if v >= 1 << 31 else v) for n, v in zip(names, w)}
            r = w[len(names):]
            passes.append(LightPass(int(p[1]), s, r[0], r[1], r[2], tuple(r[3:6]), tuple(r[6:8])))
        elif p and p[0] == "G" and len(p) == 8:
            gaps[int(p[1])] = Gap(int(p[2]), float(p[3]), int(p[4], 16), float(p[5]), float(p[6]), float(p[7]))
        elif p and p[0] == "U" and len(p) == 4 and units is not None:
            units[int(p[1], 16)] = (float(p[2]), int(p[3]))
    return passes, gaps
