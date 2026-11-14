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


def test_parse_race_log_reads_player_and_jolt_lines(tmp_path):
    from vrtools.mame.runner import Jolt, PlayerSample, parse_race_log

    log = tmp_path / "r.txt"
    log.write_text("P 1400 -230.5000 -269.2500 -16384 16384 3 120 0 1 5200 0\n"
                   "J 1410 4 131 -100.0000 50.5000\n"
                   "P 1401 -230.0000 -268.0000 -16300 -16000 255 121 -1 2 5233 7\n")
    players, jolts = parse_race_log(log)
    assert players == [PlayerSample(1400, -230.5, -269.25, -16384, 16384, 3, 120, 0, 1, 5200, 0),
                       PlayerSample(1401, -230.0, -268.0, -16300, -16000, 255, 121, -1, 2, 5233, 7)]
    assert jolts == [Jolt(1410, 4, 131, -100.0, 50.5)]


def test_parse_race_cars_reads_the_opponent_lines(tmp_path):
    from vrtools.mame.runner import CarSample, parse_race_cars, parse_race_log

    log = tmp_path / "r.txt"
    log.write_text("O 1400 1 3 -1.5000 2.2500 -32000 0\n"                  # synthetic values: yaw signed, speed unsigned
                   "P 1400 -230.5000 -269.2500 -16384 16384 3 120 0 1 5200 0\n"
                   "O 1401 15 14 6.0000 -7.0000 1200 4096\n")
    assert parse_race_cars(log) == [CarSample(1400, 1, 3, -1.5, 2.25, -32000, 0), CarSample(1401, 15, 14, 6.0, -7.0, 1200, 4096)]
    assert len(parse_race_log(log)[0]) == 1 and not parse_race_log(log)[1]          # the race log's own reader skips them


def test_parse_start_log_reads_the_load_the_player_and_the_opponents(tmp_path):
    from vrtools.mame.runner import StartCar, StartSample, parse_start_log

    log = tmp_path / "s.txt"
    log.write_text("L 1234\n"
                   "S 0 1a 0 1 2 1.5000 -2.2500 -100 65000 3 -1\n"            # synthetic values: the mode is hex, yaw and lap signed
                   "O 0 1 7 -1 -3.5000 4.7500\n"
                   "S 7 0b 99 0 0 -0.5000 8.0000 300 12 -4 2\n"
                   "O 7 15 11 0 6.2500 -1.0000\n")
    load, player, cars = parse_start_log(log)
    assert load == 1234
    assert player == [StartSample(0, 0x1A, 0, 1, 2, 1.5, -2.25, -100, 65000, 3, -1),
                      StartSample(7, 0x0B, 99, 0, 0, -0.5, 8.0, 300, 12, -4, 2)]
    assert cars == [StartCar(0, 1, 7, -1, -3.5, 4.75), StartCar(7, 15, 11, 0, 6.25, -1.0)]


def test_parse_figures_log_reads_the_load_the_player_and_the_figures(tmp_path):
    from vrtools.mame.runner import FigureLoad, FigurePose, FigureSample, parse_figures_log

    log = tmp_path / "g.txt"
    log.write_text("L 321 1\n"
                   "P 0 10.5000 -20.2500 -300 1\n"                            # synthetic values: the flags are hex, the yaw signed
                   "G 0 0 c0000000 00abcdef 11.0000 -19.0000 0.2500 -0.7500 32768 16384\n"
                   "G 0 2 80000000 00000010 9.7500 -21.5000 0.0000 0.0000 0 0\n"
                   "P 4 10.0000 -20.0000 12 0\n"
                   "G 4 1 00000000 00000000 -1.5000 2.0000 -3.0000 1.5000 65535 7\n")
    load, player, figures = parse_figures_log(log)
    assert load == FigureLoad(321, 1)
    assert player == [FigurePose(0, 10.5, -20.25, -300, 1), FigurePose(4, 10.0, -20.0, 12, 0)]
    assert figures == [FigureSample(0, 0, 0xC0000000, 0xABCDEF, 11.0, -19.0, 0.25, -0.75, 0x8000, 0x4000),
                       FigureSample(0, 2, 0x80000000, 0x10, 9.75, -21.5, 0.0, 0.0, 0, 0),
                       FigureSample(4, 1, 0, 0, -1.5, 2.0, -3.0, 1.5, 0xFFFF, 7)]


def test_parse_dir_log_reads_the_screen_lines(tmp_path):
    from vrtools.mame.runner import DirFrame, parse_dir_log

    log = tmp_path / "d.txt"
    log.write_text("D 1204 10 1 320 27ac05 9 0 1 0 255 0 1 1 602\n"        # synthetic values: mode, handler and edge are hex,
                   "X 1205 not a screen line\n"                             # the timer signed; the last field the logic
                   "D 1402 10 1 -3 fc277c 9 1 2 1 1 ffff 0 0 701\n"         # frame counter (Task 3)
                   "D 1600 11 0 -1 0 9 1 2 1 1 0 1 1 800\n")
    assert parse_dir_log(log) == [DirFrame(1204, 0x10, 1, 320, 0x27AC05, 9, 0, 1, 0, 255, 0, 1, 1, 602),
                                  DirFrame(1402, 0x10, 1, -3, 0xFC277C, 9, 1, 2, 1, 1, 0xFFFF, 0, 0, 701),
                                  DirFrame(1600, 0x11, 0, -1, 0, 9, 1, 2, 1, 1, 0, 1, 1, 800)]


def test_parse_hud_log_reads_the_label_rows(tmp_path):
    """hud_log.lua (Task 6): H <frame> <mode> <attr> then layer 0's row 44 and row 45, columns 40-61, 22 hex words each (synthetic
    values here); other lines and short H lines are skipped."""
    from vrtools.mame.runner import HudFrame, parse_hud_log

    row44 = [0x8020] * 18 + [0xC1A0, 0xC1A2, 0xC1A4, 0x8020]
    row45 = [0x8020] * 18 + [0xC1A1, 0xC1A3, 0xC1A5, 0x8020]
    words = " ".join(f"{w:x}" for w in row44 + row45)
    log = tmp_path / "h.txt"
    log.write_text(f"H 1960 14 83 {words}\n"
                   "X 1961 not a hud line\n"
                   "H 1962 14 83 8020\n"
                   f"H 5400 1a 3 {words}\n")
    assert parse_hud_log(log) == [HudFrame(0x14, 1960, 0x83, tuple(row44), tuple(row45)),
                                  HudFrame(0x1A, 5400, 0x03, tuple(row44), tuple(row45))]


def test_the_runner_gives_the_scripts_the_reverse_table(tmp_path, monkeypatch):
    """autoplay.lua answers the COURSE DIRECTION screen on the courses with a word in the reverse table: run_mame passes its
    address in this tree's layout (hex), and a caller's env overrides it."""
    import subprocess
    from vrtools.arcade.directory import directory_layout
    seen = []

    def fake(cmd, cwd, env, capture_output, text, timeout):
        seen.append(env)
        return subprocess.CompletedProcess(cmd, 0, "Average speed: 100%", "")
    monkeypatch.setattr(subprocess, "run", fake)
    run_mame(LUA_DIR / "autoplay.lua", 1, tmp_path, tmp_path)
    run_mame(LUA_DIR / "autoplay.lua", 1, tmp_path, tmp_path, env={"VR_REVERSE_TABLE": "0"})
    assert seen[0]["VR_REVERSE_TABLE"] == f"{directory_layout()['reverse']:x}" and seen[1]["VR_REVERSE_TABLE"] == "0"


def test_parse_field_reads_the_cursor_in_points(tmp_path):
    from vrtools.mame.runner import FieldSample, parse_field

    log = tmp_path / "f.txt"
    log.write_text("1500 0 12 0 192 14 43 1.74 -230.5 -269.2 1 15 1\n"
                   "1500 1 13 -1 208 15 44 1.80 -231.0 -270.0 2 0 2\n"
                   "1505 0 13 0 -16 15 45 1.74 -229.5 -268.2 1 15 1\n")
    s = parse_field(log)
    assert s == [FieldSample(1500, 0, 12, 0, 12, 14, 43, 1.74, -230.5, -269.2, 1, 15, 1),
                 FieldSample(1500, 1, 13, -1, 13, 15, 44, 1.80, -231.0, -270.0, 2, 0, 2),
                 FieldSample(1505, 0, 13, 0, -1, 15, 45, 1.74, -229.5, -268.2, 1, 15, 1)]


def test_parse_edges_reads_raw_words(tmp_path):
    from vrtools.mame.runner import EdgeSample, parse_edges

    log = tmp_path / "e.txt"
    # 0xc3668000 = -230.5 and 0xc386a000 = -269.25 as float bits; the last two columns the frames of the 0x1500 and the
    # attribute snapshots (Phase 26, Task 8: a line written for an attribute store alone carries an earlier frame's edge values)
    log.write_text("E 1700 0 2b c3668000 c386a000 1 2 3 4 5 ffffffff 2a 9 1700 1700\n"
                   "E 1701 3 0 0 3f800000 0 0 0 0 0 0 0 0 0 1701\n"
                   "E 1702 0 2c c3668000 c386a000 a b c d e f 2c c001 1700 1702\n")
    s = parse_edges(log)
    assert s[0] == EdgeSample(1700, 0, 0x2B, -230.5, -269.25, (1, 2, 3, 4, 5, 0xFFFFFFFF), 0x2A, 9, 1700, 1700)
    assert s[1].x == 0.0 and s[1].z == 1.0 and s[1].car == 3
    assert s[2].values == (10, 11, 12, 13, 14, 15) and s[2].attr_quad == 0x2C and s[2].attr == 0xC001
    assert [e.fresh for e in s] == [True, False, False]          # line 3: an attribute store, edge values from frame 1700
    assert [e.edge_frame for e in s] == [1700, 0, 1700] and [e.attr_frame for e in s] == [1700, 1701, 1702]


def test_parse_pit_log_reads_the_player_and_the_crew(tmp_path):
    """pit_log.lua (stage 4 Task 4): P <frame> <quad> <handler hex> <state> <stops> <x> <z> <yaw> <speed> <clock> <cps> <lap>
    <flags hex> <smoke> <n> and n (x, z, heading) triples (invented values, none taken from a log; the handlers are the game's
    addresses); other lines and a line cut short are skipped."""
    from vrtools.mame.runner import PitFrame, parse_pit_log

    log = tmp_path / "pit.txt"
    log.write_text("P 1000 7 fe8e18 0 2 12.5000 -3.2500 1000 0 5000 0 -2 12 0 0\n"
                   "X 1001 not a pit line\n"
                   "P 5000 7 ff2345 3 1 1.2500 -2.5000 4096 123 1000 5 3 92 7 2 1.5000 -2.2500 1234 -3.0000 4.7500 50000\n"
                   "P 5002 8 ff2345 4 0 2.0000 -1.0000 8192 100 1000 5 3 92 0 2 1.5000 -2.2500\n")
    assert parse_pit_log(log) == [
        PitFrame(1000, 7, 0xFE8E18, 0, 2, 12.5, -3.25, 1000, 0.0, 5000, 0, -2, (), 0x12, 0),
        PitFrame(5000, 7, 0xFF2345, 3, 1, 1.25, -2.5, 4096, 123.0, 1000, 5, 3,
                 ((1.5, -2.25, 1234), (-3.0, 4.75, 50000)), 0x92, 7)]


def test_parse_crew_draw_log_reads_the_pushes(tmp_path):
    """crewdraw_log.lua (stage 4 Task 5): D <frame> <crew object> <pc hex> <word hex> (synthetic values here); other lines and a
    line cut short are skipped."""
    from vrtools.mame.runner import CrewPush, parse_crew_draw_log

    log = tmp_path / "crew.txt"
    log.write_text("D 4806 0 27ac10 3f800000\nX 4806 not a push\nD 4806 4 27ac44 ffffff00\nD 4808 1 27ac10 3f8\n")
    assert parse_crew_draw_log(log) == [CrewPush(4806, 0, 0x27AC10, 0x3F800000), CrewPush(4806, 4, 0x27AC44, 0xFFFFFF00)]


def test_autoplay_loads_the_crew_draw_log():
    """Stage 4 Task 5: VR_CREW_DRAW_LOG is handled as the other logs are, autoplay.lua running crewdraw_log.lua from VR_LUA_DIR
    after the FIFO tap it listens to is installed."""
    text = (LUA_DIR / "autoplay.lua").read_text()
    line = 'if os.getenv("VR_CREW_DRAW_LOG") and lua_dir then dofile(lua_dir .. "/crewdraw_log.lua") end'
    assert line in text and text.index("_G.vr_on_fifo_word =") < text.index(line)
    assert 'os.getenv("VR_CREW_DRAW_LOG")' in (LUA_DIR / "crewdraw_log.lua").read_text()


def test_the_autopilot_search_window_defaults_to_forty_points():
    """Stage 4 Task 4: VR_AUTOPILOT_AHEAD sets how far ahead autopilot.lua's nearest-point search looks; unset, it is the 40 points
    the script always searched (every existing run drives as before)."""
    text = (LUA_DIR / "autopilot.lua").read_text()
    assert 'local ahead = tonumber(os.getenv("VR_AUTOPILOT_AHEAD") or "40")' in text
    assert "for d = -10, ahead do" in text and "for d = -10, 40 do" not in text


def test_autoplay_loads_the_pit_log():
    """Stage 4 Task 4: VR_PIT_LOG is handled as the other logs are, autoplay.lua running pit_log.lua from VR_LUA_DIR."""
    text = (LUA_DIR / "autoplay.lua").read_text()
    assert 'if os.getenv("VR_PIT_LOG") and lua_dir then dofile(lua_dir .. "/pit_log.lua") end' in text
    assert (LUA_DIR / "pit_log.lua").is_file() and 'os.getenv("VR_PIT_LOG")' in (LUA_DIR / "pit_log.lua").read_text()


def test_the_pit_log_can_force_a_work_state():
    """Stage 4 fix wave (item 13): VR_PIT_DAMAGE makes pit_log.lua write that byte to the player's damage flags +0x1ab on every
    frame from the green (the clock counting) until the pit handler first runs, which picks the stop's work state from them."""
    text = (LUA_DIR / "pit_log.lua").read_text()
    assert 'local damage = tonumber(os.getenv("VR_PIT_DAMAGE") or "")' in text
    assert "if counting and mem:read_u32(b + 0xa) == 0xff2345 then damage = nil" in text
    assert "elseif counting then mem:write_u8(b + 0x1ab, damage) end" in text
