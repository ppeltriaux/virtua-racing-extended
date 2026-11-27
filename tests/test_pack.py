"""Phase 90: the pack plans (arcade/pack.py), the wheel per pack (select.bands_for), the pack tag (the battery RAM magic), the
command line per pack, and the fix round's rules (the storm's sharing by plan, the grading's refusals, the worst views, the cuts).
Synthetic except where a test takes the arcade set (romset_zip) or the PS2 disc (VR_PS2_DISC)."""
import dataclasses

import pytest

from vrtools.arcade import pack as P
from vrtools.arcade.ranking import NEW_MAGIC, SRAM_MAGIC
from vrtools.arcade.select import BANDS, UNREACHABLE, WHEEL_FOR_ENTRY, band_of, bands_for, first_of, wheel_for
from vrtools.arcade.tencourse import COURSES


def test_pack_one_is_the_released_plan():
    assert P.SATURN.slots == tuple(COURSES) and P.SATURN.menu == 10 and P.SATURN.gantry == "frames"
    assert P.SATURN.magic == NEW_MAGIC and not P.SATURN.reserve_weather
    assert bands_for(10) == BANDS


def test_pack_two_is_the_ps2_courses_at_the_best_detail_the_frame_allows():
    assert P.ps2_names(P.PS2) == ["ISLAND", "MOUNTAIN", "BELTWAY"] and P.PS2.menu == 6
    assert P.PS2.slots[3:] == (P.Hidden(2),) * 4
    for s in P.PS2.slots[:3]:
        assert s.tiers and s.frame_records and s.frame_records < 10500
    assert P.PS2.slots[0].pit and P.PS2.slots[0].reverse and P.PS2.slots[2].windows and P.PS2.slots[2].far_cut == 60.0


def test_the_pack_tag_is_the_battery_ram_magic():
    assert P.PS2.magic != NEW_MAGIC != SRAM_MAGIC and P.PS2.magic != SRAM_MAGIC
    assert len(P.PS2.magic) == len(NEW_MAGIC) == len(SRAM_MAGIC) and P.PS2.magic.endswith(b"\0")


@pytest.mark.parametrize("change", [
    dict(slots=P.PS2.slots[:6]),                                                         # six slots
    dict(slots=P.PS2.slots[:2] + (P.PS2.slots[0],) + P.PS2.slots[3:]),                   # a course twice
    dict(slots=(dataclasses.replace(P.ISLAND, tgp_slot=6),) + P.PS2.slots[1:]),          # Mountain's TGP slot
    dict(slots=(dataclasses.replace(P.ISLAND, tgp_slot=1),) + P.PS2.slots[1:]),          # an original's TGP slot
    dict(slots=(dataclasses.replace(P.ISLAND, template=1),) + P.PS2.slots[1:]),          # bank 1 hosted by Acropolis
    dict(slots=P.PS2.slots[:6] + (P.Hidden(6),)),                                        # copies itself
    dict(menu=10),                                                                       # a hidden slot on the wheel
    dict(menu=8),
    dict(gantry="none"),
    dict(magic=b"S-RAM CHECK OK P2"),                                                    # no zero byte
])
def test_a_plan_that_cannot_be_built_is_refused(change):
    with pytest.raises(P.PackError):
        P.check(dataclasses.replace(P.PS2, **change))


def test_every_wheel_size_reaches_every_entry_inside_the_released_wheels_travel():
    """The owner's stick reaches the ten-entry wheel's outer bands (R10 beyond -102 and 102): for every wheel size the build makes,
    each entry is selected inside that travel (with its wheel_for value), the bands are in order and of the ten-entry wheel's
    width, and no entry past the wheel is ever selected ("for some reason i cant select beltway": the first six-entry wheel's
    last band began at 84, beyond what the stick gave with the gas pushed)."""
    reach = range(-115, 116)                                     # the released wheel's own band centres reach -115 .. 115
    for menu in range(6, 11):
        b = bands_for(menu)
        real = [t for t in b if t != UNREACHABLE]
        assert len(b) == len(BANDS) and len(real) == menu - 1 and real == sorted(real)
        assert all(25 <= hi - lo <= 26 for lo, hi in zip(real, real[1:]))
        assert {band_of(r, menu) for r in reach} == set(range(menu))
        assert {band_of(r, menu) for r in range(-127, 128)} == set(range(menu))      # nothing past the wheel
        for e in range(menu):
            r10 = round(1.72 * (wheel_for(e, menu) - 128))
            assert band_of(r10, menu) == e and -116 <= r10 <= 116      # the released wheel's own values: -115 .. 115
    assert [wheel_for(k) for k in range(10)] == list(WHEEL_FOR_ENTRY) and bands_for(10) == BANDS
    assert first_of(5, 6) == 3 and first_of(9) == 7 and first_of(0, 6) == 0
    with pytest.raises(ValueError):
        bands_for(5)


def test_the_ps2_disc_check_refuses_what_is_not_the_japanese_release(tmp_path):
    problems, _ = P.check_ps2(tmp_path / "none.cue")
    assert problems and "does not exist" in problems[0]
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"\0" * 4096)
    problems, _ = P.check_ps2(junk)
    assert problems and "not a PS2 disc image" in problems[0]


@pytest.mark.skipif(not __import__("os").environ.get("VR_PS2_DISC"), reason="needs the PS2 disc (VR_PS2_DISC)")
def test_the_owners_ps2_disc_is_the_japanese_release_with_the_three_courses():
    from vrtools.ps2.disc import ps2_disc
    problems, notes = P.check_ps2(ps2_disc())
    assert not problems and any("SLPM_624.43" in n for n in notes)
    assert sum("read" in n for n in notes) == 3


def test_grading_steps_down_the_cells_of_a_frame_over_its_cap_and_keeps_the_rest_rich():
    from vrtools.arcade.ps2entry import grade
    rich = {1: 500, 2: 500, 3: 500}
    poor = {1: 100, 2: 300, 3: 100}
    frames = [[1, 2], [3]]                                                  # frame 0 draws cells 1 and 2, frame 1 cell 3
    tier, totals = grade([rich, poor], frames, 700)
    assert tier == {1: 1, 2: 0, 3: 0} and totals == [600, 500]           # cell 1 saves most; cell 3's frame was within the cap
    tier, _ = grade([rich, poor], frames, 700, [{1: 9, 2: 9, 3: 9}, {1: 1, 2: 8, 3: 1}], budget=12)
    assert tier == {1: 1, 2: 0, 3: 1}                                     # then the byte budget steps down the biggest saving


def test_the_ps2_courses_set_asks_for_no_saturn_file(tmp_path, monkeypatch):
    """The PS2 courses' set plans no Saturn course, so its check reads no Saturn disc and its command line needs no --saturn;
    the Saturn courses' set still refuses to run without one."""
    from vrtools import cli
    assert not [p for p in P.PS2.slots if isinstance(p, P.CoursePlan)]
    report = cli.check_inputs(tmp_path / "roms", None, tmp_path / "out", [])
    assert not any("Saturn" in line for line in report.lines)
    monkeypatch.delenv("VR_SATURN_CUE", raising=False)
    monkeypatch.setenv("VR_ROMDIR", str(tmp_path))
    parser = cli._parser()
    roms, saturn, out = cli._paths(parser.parse_args(["build", "--pack", "ps2", "--out", str(tmp_path / "o")]), parser)
    assert saturn is None and roms == tmp_path.resolve()
    with pytest.raises(SystemExit):
        cli._paths(parser.parse_args(["build", "--out", str(tmp_path / "o")]), parser)
    assert "Saturn" in " ".join(cli.check_inputs(tmp_path / "roms", None, tmp_path / "out").lines)


@pytest.mark.skipif(not (__import__("os").environ.get("VR_PS2_DISC") and __import__("os").environ.get("VR_ROMDIR")),
                    reason="needs the arcade set (VR_ROMDIR) and the PS2 disc (VR_PS2_DISC)")
def test_the_ps2_courses_set_builds_without_the_saturn_disc(tmp_path, monkeypatch):
    from vrtools import cli
    monkeypatch.delenv("VR_SATURN_CUE", raising=False)
    assert cli.main(["build", "--pack", "ps2", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "vr.zip").is_file() and "Saturn" not in (tmp_path / "build-report.txt").read_text()


def test_the_cursor_stands_on_the_panel_the_installed_window_draws_for_every_entry(romset_zip):
    """I5 (fix round 1; the owner's "one row before"): for every wheel size 6..10, the select records that `install_directory`
    writes are DECODED from the set, and each entry's cursor (the record's x and its band) is compared with the slot in which the
    INSTALLED draw routine's window shows that entry: the window's clamp is read from the routine's own bytes (`cmp.w #c, r9` then
    `mov.w #c, r9`, after the low clamp at 0), not taken from select.py. The six-entry wheel's Beltway (entry 5) is the window's right panel. Fails when
    `menu` is dropped from `encode_directory` (2a18dd7's change) or the clamp is wrong."""
    import struct
    from dataclasses import replace
    from vrtools.arcade.directory import ORIGINALS, directory_layout, install_directory
    from vrtools.arcade.romset import V60_PROGRAM, RomSet
    from vrtools.arcade.select import SLOT_X, select_routines
    from vrtools.arcade.v60asm import Block
    rs = RomSet.from_zip(romset_zip)
    lay = directory_layout()

    def clamp_pattern(c):
        b = Block(0)
        b.emit("cmp.w imm,reg", c, "r9")
        cmp_ = b.bytes()
        b = Block(0)
        b.emit("mov.w imm,reg", c, "r9")
        return cmp_, b.bytes()
    for menu in range(6, 11):
        d = [replace(e, hidden=k >= menu) for k, e in enumerate((ORIGINALS * 4)[:10])]
        out = install_directory(rs, d, menu=menu)
        at = lay["draw"] - V60_PROGRAM
        draw = bytes(out.program[at:at + len(select_routines(lay, menu)["draw"])])
        found = []                                                      # (where, c): `cmp.w #c, r9`, a branch, `mov.w #c, r9`
        for c in range(8):
            cmp_, mov = clamp_pattern(c)
            at_ = draw.find(cmp_)
            while at_ >= 0:
                if mov in draw[at_ + len(cmp_):at_ + len(cmp_) + 8]:
                    found.append((at_, c))
                at_ = draw.find(cmp_, at_ + 1)
        found.sort()
        assert len(found) == 2 and found[0][1] == 0, (menu, found)     # the low clamp (0), then the high one
        clamps = [found[1][1]]
        for e in range(menu):
            x, _, _, lo, hi, _ = struct.unpack_from("<ffIiiI", out.program, lay["select"] - V60_PROGRAM + 24 * e)
            shown = e - max(0, min(clamps[0], e - 1))              # the slot the installed window draws entry e in
            assert (x, lo, hi) == (SLOT_X[shown], -128 + 85 * shown, -128 + 85 * shown + 84), (menu, e, x, shown)
        if menu == 6:
            assert struct.unpack_from("<f", out.program, lay["select"] - V60_PROGRAM + 24 * 5)[0] == SLOT_X[2]
    trace = [128] * 30 + [255] * 88 + [128] * 26 + [0] * 38 + [255] * 48 + [128] * 30    # the owner's replayed port values
    picks = [band_of(round(1.72 * (w - 128)), 6) for w in trace]
    assert set(picks) == {0, 3, 5} and picks[30 + 87] == 5 and picks[-1] == 3


def test_the_storm_shares_storage_only_for_the_plans_hidden_entries():
    """C1 (fix round 1): the storm's course data and the lightning's blobs are shared by the PLAN (a Hidden slot's `of`), never
    because two entries' bytes are equal: pack 1 (no hidden entry) never shares, whatever its data."""
    from types import SimpleNamespace as NS
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.weather.carrier import hidden_copies, shared_with

    def conv(hidden=False, of=None):
        return NS(entry=NS(hidden=hidden), report={} if of is None else {"hidden_copy_of": of})
    assert hidden_copies([conv() for _ in range(7)]) == {} and hidden_copies(None) == {}
    assert hidden_copies([conv(), conv(), conv(), conv(True, 5), conv(True, 5), conv(True, 5), conv(True, 5)]) == \
        {6: 5, 7: 5, 8: 5, 9: 5}
    kept = {3: (b"same", "at 3")}
    assert shared_with(4, b"same", {}, kept) is None                        # equal bytes, no hidden entry: its own storage
    assert shared_with(4, b"same", None, kept) is None
    assert shared_with(4, b"same", {4: 3}, kept) == "at 3"                  # a hidden copy of entry 3: entry 3's storage
    with pytest.raises(PatchError):
        shared_with(4, b"other", {4: 3}, kept)                               # a copy whose data are not its course's
    with pytest.raises(PatchError):
        shared_with(4, b"same", {4: 5}, kept)                                # a copy of an entry not stored yet


def test_grading_that_does_not_settle_is_refused_with_what_is_over():
    """I1 (fix round 1): the grading's rounds end in a PatchError naming the course, what is over and by how much, not in a set
    shipped with a frame over its cap or the scenery over its polygon budget."""
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.ps2entry import settle
    seen = []

    def settles(cap, budget):
        seen.append((cap, budget))
        return "graded", 120 if len(seen) == 1 else 0, 0
    assert settle(settles, 6000, 900000, "ISLAND") == "graded" and seen == [(6000, 900000), (5830, 900000)]
    with pytest.raises(PatchError, match=r"MOUNTAIN.*a frame 30 records over its cap after 8 rounds"):
        settle(lambda cap, budget: (None, 30, 0), 6000, None, "MOUNTAIN")
    with pytest.raises(PatchError, match=r"BELTWAY.*the scenery 5000 bytes over its polygon budget"):
        settle(lambda cap, budget: (None, 0, 5000), 6000, 1000000, "BELTWAY")


def test_a_ps2_cell_over_the_records_a_cell_is_refused():
    """I10 (fix round 1): a capped cell on a PS2 course is a PatchError (its last faces would silently not be drawn)."""
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.ps2entry import check_capped
    check_capped("ISLAND", set())
    with pytest.raises(PatchError, match=r"ISLAND: 2 scenery cells .*\[17, 40\]"):
        check_capped("ISLAND", {40, 17})


def test_tune_reaches_the_chosen_packs_courses(tmp_path, monkeypatch, capsys):
    """I2 (fix round 1): --tune is checked against the chosen pack's courses and applied to its plan: ISLAND:pace=1.1 is taken for
    pack ps2 (and reaches Island's plan in build_pack_set), and refused for pack saturn with the Saturn courses listed."""
    from vrtools import cli
    from vrtools.arcade.patch import PatchError
    seen = {}
    real_build = cli.build
    monkeypatch.setattr(cli, "build", lambda *a, **k: seen.update(tune=a[3], pack=k["pack"]) or 0)
    monkeypatch.setenv("VR_ROMDIR", str(tmp_path))
    monkeypatch.setenv("VR_SATURN_CUE", str(tmp_path / "saturn.cue"))
    assert cli.main(["build", "--pack", "ps2", "--tune", "ISLAND:pace=1.1", "--out", str(tmp_path / "o")]) == 0
    assert seen == {"tune": {"ISLAND": {"pace": 1.1}}, "pack": "ps2"}
    with pytest.raises(SystemExit):
        cli.main(["build", "--tune", "ISLAND:pace=1.1", "--out", str(tmp_path / "o")])
    err = capsys.readouterr().err
    assert "no course named ISLAND" in err and all(p.name in err for p in COURSES) and "BELTWAY" not in err
    with pytest.raises(SystemExit):
        cli.main(["build", "--pack", "ps2", "--tune", "ALPINE:pace=1.1", "--out", str(tmp_path / "o")])
    assert "ISLAND, MOUNTAIN, BELTWAY" in capsys.readouterr().err
    monkeypatch.setattr(cli, "build", real_build)                      # the tune applied: the plan build_pack is handed
    monkeypatch.setattr(cli, "check_inputs", lambda *a, **k: cli.Report(True, []))
    monkeypatch.setattr(P, "check_ps2", lambda *a, **k: ([], []))
    monkeypatch.setattr(cli.RomSet, "from_zip", staticmethod(lambda path: None))
    monkeypatch.setattr(cli, "tgp_budget", lambda rs: 0)
    planned = []

    def stop(rs, plan, ps2):
        planned.append(plan)
        raise PatchError("stop here")
    monkeypatch.setattr(P, "build_pack", stop)
    assert cli.build_pack_set(tmp_path, None, tmp_path / "o", "ps2", tmp_path / "ps2.cue", {"ISLAND": {"pace": 1.1}}) == 2
    assert planned[0].slots[0].pace == 1.1 and planned[0].slots[1:] == P.PS2.slots[1:]


def test_the_ps2_courses_set_runs_with_its_own_battery_ram_folder(tmp_path):
    """I3 (fix round 1): pack 2's run line gives its own -nvram_directory (the pack tag clears the other pack's memory, and MAME's
    default folder is shared); pack 1's line is as released."""
    from vrtools import cli
    assert cli.run_line(tmp_path) == f"run: mame vr -rompath {tmp_path}"
    assert cli.run_line(tmp_path, "ps2") == f"run: mame vr -rompath {tmp_path} -nvram_directory {tmp_path / 'nvram'}"


def test_the_worst_views_are_the_models_highest_frames_each_way_and_apart():
    """I4 (fix round 1): the parked check's places: per direction the road points with the most records by the build's model,
    in the direction's own numbering (reverse road point j is frame n + (n - j) mod n), at least WORST_APART apart."""
    from vrtools.arcade.ps2entry import worst_views
    n = 40
    totals = [0] * (2 * n)
    totals[5], totals[7], totals[20], totals[33] = 900, 950, 800, 700        # 5 and 7 are one place: 7 kept
    totals[n + 10], totals[n + 30] = 600, 500                                # reverse frames of normal points 10, 30
    w = worst_views(totals, n, apart=10)
    assert w["normal"] == [7, 20, 33]
    assert w["reverse"][:2] == [30, 10]                                      # reverse road points (40 - 10), (40 - 30)


def test_a_rate_failure_becomes_frame_cuts_for_its_road_points():
    """I8 (fix round 1): tests/pack2_cuts.py's last step: frames over the room at adjacent road points become one frame_cuts entry
    taking the largest excess plus the margin off those views."""
    from tests.pack2_cuts import MARGIN, RECORDS_MAX, cuts
    found = [(100, RECORDS_MAX + 50, 180, []), (104, RECORDS_MAX + 120, 181, []), (110, RECORDS_MAX + 10, 183, []),
             (300, RECORDS_MAX + 294, 257, [])]
    assert cuts(found, "normal") == [("normal", 180, 181, 120 + MARGIN), ("normal", 183, 183, 10 + MARGIN),
                                     ("normal", 257, 257, 294 + MARGIN)]


@pytest.mark.parametrize("error", ["convert", "pack", "reader"])
def test_the_ps2_courses_set_reports_a_conversion_or_reader_error_as_a_problem(tmp_path, monkeypatch, capsys, error):
    """Minor (fix round 1): ConvertError, PackError and the readers' errors (one base, vrtools.ps2.Ps2ReadError) end the build
    with "build failed" and exit code 2, as a PatchError does, not with a traceback."""
    from vrtools import cli
    from vrtools.convert.geometry import ConvertError
    from vrtools.ps2.pac import PacError
    exc = {"convert": ConvertError("no racing line"), "pack": P.PackError("no disc"), "reader": PacError("LZSS stream ended")}[error]
    monkeypatch.setattr(cli, "check_inputs", lambda *a, **k: cli.Report(True, []))
    monkeypatch.setattr(P, "check_ps2", lambda *a, **k: ([], []))
    monkeypatch.setattr(cli.RomSet, "from_zip", staticmethod(lambda path: None))
    monkeypatch.setattr(cli, "tgp_budget", lambda rs: 0)

    def fail(*a):
        raise exc
    monkeypatch.setattr(P, "build_pack", fail)
    assert cli.build_pack_set(tmp_path, None, tmp_path / "o", "ps2", tmp_path / "ps2.cue") == 2
    assert f"build failed: {exc}" in capsys.readouterr().out
