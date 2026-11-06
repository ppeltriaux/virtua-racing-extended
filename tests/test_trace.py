import pytest

from vrtools.arcade.trace import Event, TraceError, by_page, by_pc, data_rom_addr, parse_trace, summary

LOG = """B 1200 0
R 1200 fe1469 100000 0 12
W 1200 fe2000 600000 3
B 1201 2
R 1201 fe1469 123400 2 5
D 1250 /tmp/x.ram.1250.bin
END 2 4
"""


def test_parse_trace_round_trip(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text(LOG)
    ev = parse_trace(p)
    assert ev[0] == Event("B", 1200, 0, 0, 0, 0)
    assert ev[1] == Event("R", 1200, 0xFE1469, 0x100000, 0, 12)
    assert ev[2] == Event("W", 1200, 0xFE2000, 0x600000, 0, 3)
    assert ev[4] == Event("R", 1201, 0xFE1469, 0x123400, 2, 5)
    assert ev[5].kind == "D" and ev[5].addr == 0 and ev[5].frame == 1250
    assert len(ev) == 6


def test_missing_end_line_raises(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("R 1 1 1 0 1\n")
    with pytest.raises(TraceError, match="END"):
        parse_trace(p)


def test_data_rom_addr_bank_mapping():
    assert data_rom_addr(0x123456, 2) == 0x223456
    assert data_rom_addr(0x100000, 0) == 0
    assert data_rom_addr(0x1FFFFF, 3) == 0x3FFFFF
    assert data_rom_addr(0x500000, 0) is None
    assert data_rom_addr(0x0FFFFF, 0) is None


def test_by_pc_counts_data_rom_pages():
    ev = [Event("R", 1, 0xAA, 0x100000, 0, 2), Event("R", 2, 0xAA, 0x123400, 2, 5), Event("R", 2, 0xBB, 0x500000, 0, 9)]
    bp = by_pc(ev)
    assert bp[0xAA] == {0x000000: 2, 0x223400: 5}
    assert 0xBB not in bp                       # RAM read, not data ROM
    assert by_page(ev)[0x223400] == {0xAA: 5}


def test_empty_window_gives_zero_events(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("END 0 0\n")
    assert parse_trace(p) == []
    assert "0 events" in summary([])


def test_memtrace_integration(tmp_path, romset_zip):
    from vrtools.mame.runner import LUA_DIR, run_mame
    log = tmp_path / "trace.txt"
    run_mame(LUA_DIR / "autoplay.lua", 30, tmp_path, romset_zip.parent,
             env={"VR_TRACE_LOG": str(log), "VR_TRACE_READ": "100000-1fffff", "VR_TRACE_WRITE": "600000-61ffff",
                  "VR_TRACE_FROM": "1200", "VR_TRACE_TO": "1260", "VR_TRACE_DUMP": "1250"})
    ev = parse_trace(log)
    assert any(e.kind == "R" for e in ev) and any(e.kind == "W" for e in ev)
    dumps = [e for e in ev if e.kind == "D"]
    assert dumps and (tmp_path / "trace.txt.ram.1250.bin").stat().st_size == 0x40000
    assert len(by_pc(ev)) >= 1


def test_error_lines_are_tolerated(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("END 0 0\nE 1205 attempt to index a nil value\nR 1206 fe0000 100000 0 1\nEND 1 1\n")
    ev = parse_trace(p)
    assert [e.kind for e in ev] == ["E", "R"]
    assert ev[0].frame == 1205
