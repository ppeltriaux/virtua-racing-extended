"""The `vrtools` command (Phase 12, M7): check the user's own ROM set and Saturn disc, build the ten-course set.

    vrtools check --roms DIR --saturn CUE --out DIR
    vrtools build --roms DIR --saturn CUE --out DIR [--tune "AMAZON FALLS:pace=0.9,laps=4"] [--smoke] [--seconds 60]

The three paths default to VR_ROMDIR, VR_SATURN_CUE and VR_OUT (`vrtools.config`). Nothing is read from or written
to the repository: the inputs are the user's, the output goes under --out, and the input set is never overwritten.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import dataclasses
import shutil

from vrtools import config
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import EXPECTED, OTHER_FILES, RomSet, RomSetError
from vrtools.arcade.tencourse import COURSES, CoursePlan, build_all, poly_budget, report_lines, ten_course_set, tgp_budget

EXTRA_ZIPS = ("model1io.zip", "m1comm.zip")          # MAME loads them beside vr.zip; the build only copies them
TUNE_KEYS = {"laps": int, "time_factor": float, "pace": float}   # the playtest knobs of a CoursePlan (spec decision 11)
MAX_LAPS = 7                                          # the time record holds 23 extensions, three per lap (Phase 9)
SMOKE_SECONDS = 60                                    # the autoplay script coins up, picks the entry and starts the race about 1600 frames (28 s) in
SMOKE_MIN_SECONDS = 40                                # the render rate is read after frame 2000 (~35 s): a shorter run measures nothing


@dataclass
class Report:
    ok: bool
    lines: list[str]


def _disc_track(cue: Path) -> Path | None:
    """The data track named by the cue's first FILE line, relative to the cue's directory; None without one."""
    m = re.search(r'FILE\s+"([^"]+)"', cue.read_text(errors="replace"))
    return cue.parent / m.group(1) if m else None


def _other_files(path: Path) -> tuple[list[str], list[str]]:
    """(missing, mismatched) among the 13 files MAME needs that the build does not read."""
    with zipfile.ZipFile(path) as z:
        infos = {Path(i.filename).name: i for i in z.infolist()}
    missing = [n for n in OTHER_FILES if n not in infos]
    bad = [f"{n}: size {infos[n].file_size:#x} crc32 {infos[n].CRC:08x}, expected {s:#x} {c:08x}"
           for n, (s, c) in OTHER_FILES.items() if n in infos and (infos[n].file_size != s or infos[n].CRC != c)]
    return missing, bad


def check_inputs(roms: Path, saturn: Path, out: Path, plans: list[CoursePlan] = COURSES) -> Report:
    """What a build needs, in order: the ROM directory with a good `vr.zip` (the two extra zips are a warning), the
    Saturn disc with every planned course file, and an output directory that is not the ROM directory."""
    from vrtools.saturn.iso import Iso2352, IsoError
    problems: list[str] = []
    notes: list[str] = []
    roms, saturn, out = Path(roms), Path(saturn), Path(out)
    if not roms.is_dir():
        problems.append(f"ROM directory {roms} does not exist (it must hold vr.zip, model1io.zip and m1comm.zip)")
    elif not (roms / "vr.zip").is_file():
        problems.append(f"{roms} holds no vr.zip (the MAME 0.289 `vr` set)")
    else:
        try:
            RomSet.from_zip(roms / "vr.zip")
            notes.append(f"{roms / 'vr.zip'}: {len(EXPECTED)} ROM files verified (sizes and CRCs of the MAME 0.289 set)")
            missing, bad = _other_files(roms / "vr.zip")
            if missing:
                problems.append(f"{roms / 'vr.zip'}: MAME needs these files too and they are missing: {', '.join(missing)}")
            for b in bad:
                notes.append(f"warning: {roms / 'vr.zip'}: {b} (not read by the build; MAME may refuse it)")
            if not missing and not bad:
                notes.append(f"{roms / 'vr.zip'}: the {len(OTHER_FILES)} other files of the set present (audio, I/O board, TGP tables)")
        except zipfile.BadZipFile:
            problems.append(f"{roms / 'vr.zip'} is not a zip file")
        except (RomSetError, OSError) as e:
            problems.append(str(e))
        for name in EXTRA_ZIPS:
            if (roms / name).is_file():
                notes.append(f"{roms / name}: present (copied beside the output)")
            else:
                notes.append(f"warning: {roms / name} is missing — the build does not need it, MAME does to run the set")
    if not saturn.is_file():
        problems.append(f"Saturn cue {saturn} does not exist (the .cue of Virtua Racing (Europe), its .bin beside it)")
    else:
        track = _disc_track(saturn)
        if track is None:
            problems.append(f"{saturn}: no FILE line — not a cue sheet")
        elif not track.is_file():
            problems.append(f"{saturn} names {track.name}, which is not beside it")
        else:
            try:
                iso = Iso2352(track)
                for plan in plans:
                    path = f"VRSRCDIR/TRACKS00/{plan.path}"
                    try:
                        iso.read(path)
                        notes.append(f"{track.name}: {path} found ({plan.name})")
                    except IsoError:
                        problems.append(f"{track.name}: no {path} — not the disc this build reads "
                                        f"(tested with Virtua Racing (Europe); another region's disc lays its files out differently)")
            except IsoError as e:
                problems.append(str(e))
            except OSError as e:
                problems.append(f"{track}: cannot be read: {e}")
    same = roms.resolve() == out.resolve() or (roms.exists() and out.exists() and os.path.samefile(roms, out))
    if same:
        problems.append(f"output directory {out} is the same directory as the ROM set: the input set is never overwritten")
    else:
        try:
            out.mkdir(parents=True, exist_ok=True)
            probe = out / ".vrtools-write-test"
            probe.write_bytes(b"")
            probe.unlink()
            notes.append(f"output directory {out}")
        except OSError as e:
            problems.append(f"output directory {out} cannot be written: {e}")
    return Report(not problems, [f"problem: {p}" for p in problems] + notes)


def parse_tune(specs: list[str]) -> dict[str, dict[str, float | int]]:
    """`"AMAZON FALLS:pace=1.1,laps=4"` → {"AMAZON FALLS": {"pace": 1.1, "laps": 4}}; the course name as in
    `CoursePlan.name` (any case); keys laps (1..MAX_LAPS), time_factor and pace (> 0). ValueError names the bad spec."""
    out: dict[str, dict[str, float | int]] = {}
    for spec in specs:
        name, sep, rest = spec.partition(":")
        if not sep or not rest.strip():
            raise ValueError(f"--tune {spec!r}: expected COURSE:KEY=VALUE[,KEY=VALUE]")
        knobs = out.setdefault(name.strip().upper(), {})
        for item in rest.split(","):
            key, eq, value = item.partition("=")
            key = key.strip()
            if not eq or key not in TUNE_KEYS:
                raise ValueError(f"--tune {spec!r}: {key!r} is not a knob (laps, time_factor, pace)")
            try:
                v = TUNE_KEYS[key](value.strip())
            except ValueError:
                raise ValueError(f"--tune {spec!r}: {key} needs a number, not {value.strip()!r}") from None
            if key == "laps" and not 1 <= v <= MAX_LAPS:
                raise ValueError(f"--tune {spec!r}: laps must be 1..{MAX_LAPS}")
            if key != "laps" and not (math.isfinite(v) and v > 0):
                raise ValueError(f"--tune {spec!r}: {key} must be a finite number above 0")
            knobs[key] = v
    return out


def apply_tune(plans: list[CoursePlan], tune: dict[str, dict[str, float | int]]) -> list[CoursePlan]:
    """The plans with the knobs replaced; ValueError lists the course names when one is unknown."""
    names = {p.name: p for p in plans}
    unknown = [n for n in tune if n not in names]
    if unknown:
        raise ValueError(f"--tune: no course named {', '.join(unknown)} (courses: {', '.join(names)})")
    return [dataclasses.replace(p, **tune[p.name]) if p.name in tune else p for p in plans]


def build(roms: Path, saturn: Path, out: Path, tune: dict[str, dict[str, float | int]] | None = None,
          smoke: bool = False, seconds: int = SMOKE_SECONDS) -> int:
    """Check the inputs, convert the seven courses into the user's set, write out/vr.zip (the input set's extra
    members copied through), copy the two extra zips, write out/build-report.txt. 0 when done; 1 when the inputs
    fail the check (its lines printed); 2 when a course does not fit (PatchError names it); 3 when the smoke test
    fails."""
    report = check_inputs(roms, saturn, out)
    if not report.ok:
        print("\n".join(report.lines))
        print("not ready: fix the problems above")
        return 1
    plans = apply_tune(COURSES, tune or {})
    rs = RomSet.from_zip(roms / "vr.zip")
    before = tgp_budget(rs)
    try:
        patched, converted = build_all(rs, saturn, plans)
        patched = ten_course_set(patched, converted)
    except PatchError as e:
        print(f"build failed: {e}")
        return 2
    patched.to_zip(out / "vr.zip", source=roms / "vr.zip")
    for name in EXTRA_ZIPS:
        if (roms / name).is_file():
            shutil.copy(roms / name, out / name)
    lines = report_lines(before, tgp_budget(patched), converted, plans, poly_left=poly_budget(patched))
    rc = 0
    if smoke:
        ok, line = run_smoke(out, seconds=seconds)
        lines.append(line)
        rc = 0 if ok else 3
    lines.append(f"run: mame vr -rompath {out}")
    (out / "build-report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return rc


def run_smoke(out: Path, entry: int = 3, seconds: int = SMOKE_SECONDS) -> tuple[bool, str]:
    """Drive converted `entry` in MAME for `seconds` with the autoplay script and report whether the set loaded
    that entry (the collision log's course words: menu index, template) and rendered at the arcade rate (27–29
    display-list switches per 57 frames after the start). (True, "skipped ...") without `mame` on PATH."""
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.mame.runner import LUA_DIR, MameError, course_of, parse_rate, run_mame
    if shutil.which("mame") is None:
        return True, "smoke test skipped: mame is not on PATH (install MAME 0.289 and run `mame vr -rompath <out>` yourself)"
    plan = COURSES[entry - 3]
    wd = Path(out) / "smoke"
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    try:
        run_mame(LUA_DIR / "autoplay.lua", seconds, wd, Path(out), env={
            "VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_RATE_LOG": str(wd / "rate.txt")},
            timeout=3 * seconds + 120)                      # MAME runs unthrottled (60 emulated s take ~15 s); a hung MAME is killed
    except MameError as e:
        return False, f"smoke test failed: {e}"
    loaded = course_of(wd / "c.txt") if (wd / "c.txt").exists() else None
    rates = [n for f, n in parse_rate(wd / "rate.txt") if f > 2000] if (wd / "rate.txt").exists() else []
    want = (entry, plan.template)
    if loaded != want:
        return False, f"smoke test failed: entry {entry} {plan.name} did not load (course words {loaded}, expected {want})"
    if not rates or min(rates) < 27 or max(rates) > 29:
        return False, f"smoke test failed: render rate {min(rates) if rates else '-'}–{max(rates) if rates else '-'} switches per 57 frames (expected 27–29)"
    return True, f"smoke test: entry {entry} {plan.name} loaded (course words {loaded}), render rate {min(rates)}–{max(rates)} switches per 57 frames in {seconds} s"


def _paths(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[Path, Path, Path]:
    roms = args.roms or config.rom_dir()
    saturn = args.saturn or config.saturn_cue()
    out = args.out or config._env_path("VR_OUT") or Path.cwd() / "out"
    missing = [n for n, v in (("--roms (VR_ROMDIR)", roms), ("--saturn (VR_SATURN_CUE)", saturn)) if v is None]
    if missing:
        parser.error("missing " + ", ".join(missing))
    return Path(roms).resolve(), Path(saturn).resolve(), Path(out).resolve()   # MAME runs in a work directory: a relative rompath would not resolve


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vrtools", description="Saturn Virtua Racing courses in the Model 1 arcade ROM set (stock MAME 0.289).")
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_ in (("check", "verify the ROM set, the Saturn disc and the output directory"),
                        ("build", "build the ten-course set from your own vr.zip and Saturn disc")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--roms", type=Path, help="directory with vr.zip, model1io.zip, m1comm.zip (default: $VR_ROMDIR)")
        s.add_argument("--saturn", type=Path, help="the Saturn 'Virtua Racing (Europe).cue', its .bin beside it (default: $VR_SATURN_CUE)")
        s.add_argument("--out", type=Path, help="output directory for the built set (default: $VR_OUT or ./out)")
        if name == "build":
            s.add_argument("--tune", action="append", default=[], metavar="COURSE:KEY=VALUE,...",
                           help='per-course knobs, e.g. "AMAZON FALLS:pace=0.9,laps=4" (keys: laps 1..7, time_factor, pace)')
            s.add_argument("--smoke", action="store_true", help="after the build, drive the first converted course in MAME (headless, 60 emulated seconds) to prove the set loads and renders")
            s.add_argument("--seconds", type=int, default=SMOKE_SECONDS,
                           help=f"length of the smoke test in emulated seconds (default {SMOKE_SECONDS}, at least {SMOKE_MIN_SECONDS}: the race starts about 28 s in)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    roms, saturn, out = _paths(args, parser)
    if args.command == "check":
        report = check_inputs(roms, saturn, out)
        print("\n".join(report.lines))
        print("ok: ready to build" if report.ok else "not ready: fix the problems above")
        return 0 if report.ok else 1
    try:
        tune = parse_tune(args.tune)
        apply_tune(COURSES, tune)
    except ValueError as e:
        parser.error(str(e))
    if args.seconds < SMOKE_MIN_SECONDS:
        parser.error(f"--seconds {args.seconds}: at least {SMOKE_MIN_SECONDS} (the race starts about 28 s in; 0 would run MAME without end)")
    return build(roms, saturn, out, tune, smoke=args.smoke, seconds=args.seconds)


if __name__ == "__main__":
    raise SystemExit(main())
