"""The `vrtools` command: check the user's inputs, build the ten-course set (Phase 12, M7)."""
import shutil
import zipfile
from pathlib import Path

import pytest

from vrtools.arcade.romset import EXPECTED


def _rom_dir(tmp_path: Path, romset_zip: Path, rewrite: dict[str, bytes] | None = None, extra: dict[str, bytes] | None = None) -> Path:
    """A copy of the user's ROM directory under tmp_path: vr.zip (members rewritten / added as asked) plus the two extras."""
    d = tmp_path / "roms"
    d.mkdir()
    with zipfile.ZipFile(romset_zip) as src, zipfile.ZipFile(d / "vr.zip", "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            name = Path(info.filename).name
            dst.writestr(info.filename, (rewrite or {}).get(name, src.read(info.filename)))
        for name, blob in (extra or {}).items():
            dst.writestr(name, blob)
    for name in ("model1io.zip", "m1comm.zip"):
        if (romset_zip.parent / name).exists():
            shutil.copy(romset_zip.parent / name, d / name)
    return d


def test_check_names_a_missing_rom_dir(tmp_path, capsys):
    from vrtools.cli import main
    rc = main(["check", "--roms", str(tmp_path / "none"), "--saturn", str(tmp_path / "x.cue"), "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 1 and "none" in out and "vr.zip" in out


def test_check_lists_the_one_bad_crc(tmp_path, romset_zip, saturn_cue, capsys):
    from vrtools.cli import main
    bad = "epr-14878a.4"
    roms = _rom_dir(tmp_path, romset_zip, rewrite={bad: bytes(EXPECTED[bad][0])})
    rc = main(["check", "--roms", str(roms), "--saturn", str(saturn_cue), "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 1 and bad in out and f"{EXPECTED[bad][1]:08x}" in out
    assert not any(name in out for name in EXPECTED if name != bad), out


def test_check_refuses_out_inside_the_rom_dir(tmp_path, romset_zip, saturn_cue, capsys):
    from vrtools.cli import main
    roms = _rom_dir(tmp_path, romset_zip)
    rc = main(["check", "--roms", str(roms), "--saturn", str(saturn_cue), "--out", str(roms)])
    assert rc == 1 and "same directory" in capsys.readouterr().out


def test_check_names_the_missing_course_file(tmp_path, romset_zip, saturn_cue):
    from vrtools.arcade.tencourse import CoursePlan
    from vrtools.cli import check_inputs
    roms = _rom_dir(tmp_path, romset_zip)
    report = check_inputs(roms, saturn_cue, tmp_path / "out", plans=[CoursePlan("NOPE00/TRCKNOPE", "NOPE", 1, 4, 0, 1)])
    assert not report.ok
    assert any("VRSRCDIR/TRACKS00/NOPE00/TRCKNOPE" in line for line in report.lines), report.lines


def test_check_passes_on_the_real_inputs(tmp_path, romset_zip, saturn_cue, capsys):
    from vrtools.arcade.tencourse import COURSES
    from vrtools.cli import main
    roms = _rom_dir(tmp_path, romset_zip)
    rc = main(["check", "--roms", str(roms), "--saturn", str(saturn_cue), "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert f"{len(EXPECTED)} ROM files verified" in out
    assert all(plan.path in out for plan in COURSES), out


def test_parse_tune_reads_knobs_per_course():
    from vrtools.arcade.tencourse import COURSES
    from vrtools.cli import apply_tune, parse_tune
    assert parse_tune(["amazon falls:pace=1.1,laps=4", "ALPINE:time_factor=0.9"]) == {"AMAZON FALLS": {"pace": 1.1, "laps": 4}, "ALPINE": {"time_factor": 0.9}}
    with pytest.raises(ValueError, match="grip"):
        parse_tune(["ALPINE:grip=2"])
    with pytest.raises(ValueError, match="laps"):
        parse_tune(["ALPINE:laps=9"])
    with pytest.raises(ValueError, match="ALPINE"):
        apply_tune(COURSES, {"NOPE": {"laps": 3}})
    tuned = apply_tune(COURSES, {"AMAZON FALLS": {"pace": 1.2, "laps": 4}})
    amazon = next(p for p in tuned if p.name == "AMAZON FALLS")
    assert amazon.pace == 1.2 and amazon.laps == 4 and len(tuned) == len(COURSES)
    assert next(p for p in tuned if p.name == "ALPINE") == next(p for p in COURSES if p.name == "ALPINE")


def _built(tmp_path, romset_zip, saturn_cue, extra=None, tune=()):
    from vrtools.cli import main
    roms = _rom_dir(tmp_path, romset_zip, extra=extra)
    out = tmp_path / "o"
    args = ["build", "--roms", str(roms), "--saturn", str(saturn_cue), "--out", str(out)]
    for t in tune:
        args += ["--tune", t]
    return roms, out, main(args)


def test_build_writes_the_set_and_the_report(tmp_path, romset_zip, saturn_cue):
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.race import car_table, decode_race_blob
    from vrtools.arcade.romset import RomSet
    roms, out, rc = _built(tmp_path, romset_zip, saturn_cue, tune=["AMAZON FALLS:pace=1.2,laps=4"])
    assert rc == 0
    built = RomSet.from_zip(out / "vr.zip", verify=False)
    amazon = next(e for e in decode_directory(built) if e.name == "AMAZON FALLS")
    assert amazon.laps == 4
    original = car_table(RomSet.from_zip(romset_zip), 0)
    blob = decode_race_blob(built, amazon.race)
    assert blob.cars[1].perf == pytest.approx(original[1].perf * 1.2, rel=1e-5)
    alpine = next(e for e in decode_directory(built) if e.name == "ALPINE")
    assert alpine.laps == 5 and decode_race_blob(built, alpine.race).cars[1].perf == pytest.approx(original[1].perf, rel=1e-5)
    for name in ("model1io.zip", "m1comm.zip"):
        assert (out / name).exists() == (roms / name).exists()
    report = (out / "build-report.txt").read_text()
    assert report.startswith("TGP budget:")
    assert sum(1 for line in report.splitlines() if line.startswith("entry ")) == 7
    assert report.count("coverage") >= 7 and "mame vr -rompath" in report
    assert "polygon ROM left" in report.splitlines()[0]                  # Phase 18: the scenery layers' budget
    assert report.count("layers g0-g4, terrain thinned ") == 7 and report.count("terrain thinned ") == 7


def test_build_copies_a_clone_set_through(tmp_path, romset_zip, saturn_cue):
    roms, out, rc = _built(tmp_path, romset_zip, saturn_cue, extra={"epr-99999.99": bytes(16)})
    assert rc == 0
    with zipfile.ZipFile(out / "vr.zip") as z:
        assert "epr-99999.99" in z.namelist() and z.read("epr-99999.99") == bytes(16)


def test_build_refuses_out_inside_the_rom_dir(tmp_path, romset_zip, saturn_cue, capsys):
    from vrtools.cli import main
    roms = _rom_dir(tmp_path, romset_zip)
    before = sorted(p.name for p in roms.iterdir())
    rc = main(["build", "--roms", str(roms), "--saturn", str(saturn_cue), "--out", str(roms)])
    assert rc == 1 and "same directory" in capsys.readouterr().out
    assert sorted(p.name for p in roms.iterdir()) == before


def test_smoke_is_skipped_without_mame(tmp_path, monkeypatch):
    from vrtools.cli import run_smoke
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    ok, line = run_smoke(tmp_path)
    assert ok and "skipped" in line and "mame" in line


def test_smoke_drives_the_first_converted_entry(tmp_path, romset_zip, saturn_cue):
    if shutil.which("mame") is None:
        pytest.skip("mame is not on PATH")
    from vrtools.cli import run_smoke
    roms, out, rc = _built(tmp_path, romset_zip, saturn_cue)
    assert rc == 0
    ok, line = run_smoke(out)
    assert ok, line
    assert "ALPINE" in line and "28" in line


def test_paths_are_resolved_so_mame_finds_a_relative_out(tmp_path, monkeypatch):
    """A by-hand `vrtools build --out out/p12/build --smoke` failed: MAME runs in the smoke test's work directory and
    got the relative rompath ("Required files are missing"). The three paths are resolved when parsed."""
    from vrtools.cli import _parser, _paths
    monkeypatch.chdir(tmp_path)
    (tmp_path / "r").mkdir()
    parser = _parser()
    roms, saturn, out = _paths(parser.parse_args(["build", "--roms", "r", "--saturn", "d/x.cue", "--out", "o/build"]), parser)
    assert roms == (tmp_path / "r").resolve() and saturn == (tmp_path / "d/x.cue").resolve() and out == (tmp_path / "o/build").resolve()
    assert all(p.is_absolute() for p in (roms, saturn, out))


# --- review fix pass (Phase 12)

def test_numpy_is_a_runtime_dependency():
    """Review C1: the README's `pip install -e .` left a fresh venv without numpy, which convert/geometry.py imports:
    `vrtools --help` died. numpy is a runtime dependency, not a dev extra only."""
    import tomllib
    meta = tomllib.loads(Path("pyproject.toml").read_text())
    assert any(d.startswith("numpy") for d in meta["project"]["dependencies"]), meta["project"]["dependencies"]


def test_check_refuses_out_that_is_the_rom_dir_spelled_differently(tmp_path, romset_zip, saturn_cue, capsys):
    """Review C2: on macOS's case-insensitive filesystem `Path.resolve()` keeps the spelling, so `--out ROMS` for
    `--roms roms` passed both guards and the user's vr.zip was truncated. The guard compares the files themselves."""
    from vrtools.cli import main
    roms = _rom_dir(tmp_path, romset_zip)
    other = Path(str(roms).upper())
    if not other.exists():
        pytest.skip("case-sensitive filesystem")
    rc = main(["check", "--roms", str(roms), "--saturn", str(saturn_cue), "--out", str(other)])
    assert rc == 1 and "same directory" in capsys.readouterr().out


def test_to_zip_never_writes_over_its_source_and_writes_atomically(tmp_path, romset_zip):
    """Review C2: `RomSet.to_zip` compared paths by spelling and then opened the source for writing. It refuses the
    same file under any spelling or link, and writes through a temporary file so an interrupted write cannot leave a
    truncated vr.zip."""
    import os
    from vrtools.arcade.romset import RomSet, RomSetError
    roms = _rom_dir(tmp_path, romset_zip)
    rs = RomSet.from_zip(roms / "vr.zip")
    before = (roms / "vr.zip").read_bytes()
    alias = Path(str(roms).upper()) / "vr.zip" if Path(str(roms).upper()).exists() else None
    link = tmp_path / "link.zip"
    os.link(roms / "vr.zip", link)
    for same in filter(None, (alias, link)):
        with pytest.raises(RomSetError):
            rs.to_zip(same, source=roms / "vr.zip")
    assert (roms / "vr.zip").read_bytes() == before
    out = tmp_path / "o" / "vr.zip"
    out.parent.mkdir()
    rs.to_zip(out, source=roms / "vr.zip")
    assert out.exists() and not list(out.parent.glob("*.tmp")) and not list(out.parent.glob("*.part"))


def test_check_reports_a_corrupt_zip_and_an_odd_cue_without_a_traceback(tmp_path, saturn_cue, capsys):
    """Review I1: a vr.zip that is not a zip raised BadZipFile through `check`; a cue whose FILE names a path with a
    directory raised ValueError from `Path.with_name`."""
    from vrtools.cli import main
    roms = tmp_path / "roms"
    roms.mkdir()
    (roms / "vr.zip").write_bytes(b"not a zip at all")
    cue = tmp_path / "odd.cue"
    cue.write_text('FILE "sub/x.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')
    rc = main(["check", "--roms", str(roms), "--saturn", str(cue), "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 1 and "vr.zip" in out and "zip" in out.lower() and "x.bin" in out


def test_check_names_an_unwritable_output_directory(tmp_path, romset_zip, saturn_cue, capsys):
    """Review I2: a read-only output directory passed `check` and `build` died at the end with PermissionError."""
    import os
    if os.geteuid() == 0:
        pytest.skip("root writes anywhere")
    from vrtools.cli import main
    roms = _rom_dir(tmp_path, romset_zip)
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        rc = main(["check", "--roms", str(roms), "--saturn", str(saturn_cue), "--out", str(ro)])
        out = capsys.readouterr().out
    finally:
        ro.chmod(0o755)
    assert rc == 1 and "ro" in out and ("writ" in out or "permission" in out.lower())


def test_check_names_the_rom_files_mame_needs_beyond_the_build(tmp_path, romset_zip, saturn_cue, capsys):
    """Review I3: `check` verified the 25 files the build reads; MAME's vr set has 38 (audio, I/O board, TGP tables),
    and a set without them builds and then does not run. A missing one is a problem; a mismatched CRC a warning."""
    from vrtools.arcade.romset import OTHER_FILES
    from vrtools.cli import main
    assert len(OTHER_FILES) == 13 and "93c45.bin" in OTHER_FILES and "epr-14870a.7" in OTHER_FILES
    with zipfile.ZipFile(romset_zip) as z:
        names = {Path(i.filename).name for i in z.infolist()}
    if not set(OTHER_FILES) <= names:
        pytest.skip("the local vr.zip is not the full MAME set")
    d = tmp_path / "roms"
    d.mkdir()
    with zipfile.ZipFile(romset_zip) as src, zipfile.ZipFile(d / "vr.zip", "w") as dst:
        for info in src.infolist():
            name = Path(info.filename).name
            if name == "93c45.bin":
                continue
            dst.writestr(info.filename, bytes(OTHER_FILES[name][0]) if name == "epr-14870a.7" else src.read(info.filename))
    rc = main(["check", "--roms", str(d), "--saturn", str(saturn_cue), "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 1 and "93c45.bin" in out and "epr-14870a.7" in out and "warning" in out


def test_seconds_too_short_is_a_usage_error(tmp_path, romset_zip, saturn_cue):
    """Review I4: `--seconds 0` ran MAME without limit (it had to be killed) and `--seconds 20` failed with a blank
    render rate: the race starts about 28 s in. Fewer than 40 seconds is refused up front."""
    from vrtools.cli import main
    roms = _rom_dir(tmp_path, romset_zip)
    for secs in ("0", "-5", "20"):
        with pytest.raises(SystemExit) as e:
            main(["build", "--roms", str(roms), "--saturn", str(saturn_cue), "--out", str(tmp_path / "out"), "--smoke", "--seconds", secs])
        assert e.value.code == 2


def test_run_mame_has_a_timeout():
    """Review I4: `run_mame` had no timeout; a MAME that never ends hangs the build."""
    import inspect
    from vrtools.mame.runner import run_mame
    assert "timeout" in inspect.signature(run_mame).parameters


def test_parse_tune_rejects_nan_and_inf():
    """Review I5: `time_factor=inf` overflowed the race blob, `nan` passed every check and clamped every opponent."""
    from vrtools.cli import parse_tune
    for bad in ("ALPINE:pace=nan", "ALPINE:time_factor=inf", "ALPINE:pace=-inf"):
        with pytest.raises(ValueError):
            parse_tune([bad])
