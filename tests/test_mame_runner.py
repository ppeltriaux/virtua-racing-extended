import pytest

from vrtools.arcade.dlist import parse_log
from vrtools.mame.runner import LUA_DIR, MameError, run_mame


def test_attract_mode_draws_objects(tmp_path, romset_zip):
    log = tmp_path / "dl.txt"
    run_mame(LUA_DIR / "dlist_log.lua", 25, tmp_path, romset_zip.parent,
             env={"VR_DLIST_LOG": str(log), "VR_DLIST_FROM": "900", "VR_DLIST_EVERY": "60"})
    frames = list(parse_log(log))
    assert frames
    assert any(c.kind == 0x01 for _, _, cmds in frames for c in cmds)


def test_bad_rompath_raises(tmp_path):
    with pytest.raises(MameError):
        run_mame(LUA_DIR / "dlist_log.lua", 1, tmp_path, tmp_path / "nowhere")


def test_parse_rate_reads_render_rate_lines(tmp_path):
    from vrtools.mame.runner import parse_rate

    log = tmp_path / "rate.txt"
    log.write_text("X junk\nR 57 28\nR 114 29\nE 3450\n")
    assert parse_rate(log) == [(57, 28), (114, 29)]


def test_parse_collision_and_summary(tmp_path):
    from vrtools.mame.runner import drive_summary, parse_collision

    log = tmp_path / "c.txt"
    log.write_text("C 1700 29.990 1587 -230.400 -269.600 29.990 2b\nC 1702 29.990 1587 -231.300 -267.800 30.260 2c\n"
                   "C 1704 29.990 0 -231.300 -267.800 0.000 0\nEND 1705\n")
    s = parse_collision(log)
    assert s[0].quad == 0x2B and s[1].result_y == 30.26 and s[1].id == 0x1587
    d = drive_summary(s)
    assert d["calls"] == 3 and d["offroad"] == 1 and d["noanswer"] == 0 and abs(d["distance"] - 2.0125) < 1e-3
    assert d["ymin"] == 29.99 and d["ymax"] == 30.26                     # the off-road sample has no height
    assert d["onroad_calls"] == 2 and abs(d["onroad_distance"] - 2.0125) < 1e-3
    log.write_text("C 1700 29.990 1587 -230.400 -269.600 29.990 2b\nC 1702 29.990 1587 -231.300 -267.800 0.000 2b\nEND 1705\n")
    d = drive_summary(parse_collision(log))
    assert d["nohit"] == 1 and d["offroad"] == 0 and d["onroad_calls"] == 1 and d["ymax"] == 29.99


def test_original_big_forest_drives(tmp_path, romset_zip):
    from vrtools.mame.runner import drive_summary, parse_collision

    wd = tmp_path / "run"
    run_mame(LUA_DIR / "autoplay.lua", 45, wd, romset_zip.parent,
             env={"VR_COURSE": "0", "VR_COLLISION_LOG": str(wd / "c.txt")})
    d = drive_summary(parse_collision(wd / "c.txt"))
    assert d["calls"] > 400 and d["distance"] > 500 and d["offroad"] == 0
    assert 29 <= d["ymin"] and d["ymax"] <= 47
