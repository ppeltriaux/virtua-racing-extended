import struct

import pytest

from vrtools.arcade.dlist import Cmd, parse_log, walk


def i32(v: int) -> list[int]:
    return [v & 0xFFFF, (v >> 16) & 0xFFFF]


def f32(v: float) -> list[int]:
    return i32(struct.unpack("<I", struct.pack("<f", v))[0])


def words(*items) -> list[int]:
    out: list[int] = []
    for it in items:
        out.extend(it if isinstance(it, list) else [it])
    return out


MAT = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 10.0, 20.0, 30.0]


def test_object_matrix_and_end():
    e = words(i32(0x0B), *[f32(m) for m in MAT], i32(0x01), i32(0x1234), i32(0x56789), i32(0), i32(0x0F))
    cmds = walk(e)
    assert cmds[0].kind == 0x0B and cmds[0].offset == 0
    assert cmds[0].args["mat"] == pytest.approx(MAT)
    assert cmds[1] == Cmd(0x01, 26, {"tex_adr": 0x1234, "poly_adr": 0x56789, "size": 0})
    assert cmds[2].kind == -1 and cmds[2].args["stopped_on"] == 0x0F and cmds[2].offset == 34


def test_above_hud_object_is_0x41():
    cmds = walk(words(i32(0x41), i32(1), i32(0x800010), i32(3), i32(0x0F)))
    assert cmds[0].kind == 0x41 and cmds[0].args["poly_adr"] == 0x800010


def test_direct_polys_are_skipped_like_mame():
    # header 18 words, then records: type 1 (20 words), type 2 (12 words), type 0 ends, +4 trailer
    rec1 = [0, 0, *i32(0x1)] + [0] * 16       # flags are read at record offset +2
    rec2 = [0, 0, *i32(0x2)] + [0] * 8
    end = [0, 0, *i32(0x0)]
    e = words(i32(0x02), i32(0x77), *([0] * 14), *rec1, *rec2, *end, i32(0x0F))
    cmds = walk(e)
    assert cmds[0].kind == 0x02
    assert cmds[1].kind == -1 and cmds[1].offset == 18 + 20 + 12 + 4


def test_unknown_command_stops_walk():
    cmds = walk(words(i32(0x0D), i32(0x01)))
    assert cmds[0].kind == -1 and cmds[0].args["stopped_on"] == 0x0D


def test_upload_poly_ram_adr_then_len_32bit_words():
    e = words(i32(0x05), i32(0x800000), i32(3), i32(0xAAAA), i32(0xBBBB), i32(0xCCCC), i32(0x0F))
    cmds = walk(e)
    assert cmds[0].kind == 0x05
    assert cmds[0].args == {"adr": 0x800000, "len": 3, "data": [0xAAAA, 0xBBBB, 0xCCCC]}
    assert cmds[1].offset == 6 + 2 * 3


def test_upload_color_table_uses_len_plus_one_16bit_values():
    e = words(i32(0x04), i32(0x40010), i32(1), 0x1234, 0xFFFF, 0x5678, 0x0000, i32(0x0F))
    cmds = walk(e)
    assert cmds[0].args == {"adr": 0x40010, "len": 2, "data": [0x1234, 0x5678]}
    assert cmds[1].offset == 6 + 2 * 2


def test_upload_lights_like_poly_ram():
    e = words(i32(0x06), i32(0x0), i32(1), i32(0x11223344), i32(0x0F))
    cmds = walk(e)
    assert cmds[0].args == {"adr": 0, "len": 1, "data": [0x11223344]}


def test_garbage_upload_length_stops_walk():
    e = words(i32(0x05), i32(0x800000), i32(0x0FFFFFFF), i32(0x0F))
    cmds = walk(e)
    assert cmds[0].kind == -1 and cmds[0].args == {"stopped_on": 0x05, "reason": "bad length"}


def test_viewport_fields_are_int16():
    e = words(i32(0x03), 0, 0, 248, 0, 0xFFFF, 0, 10, 0, 20, 0, 30, 0, 40, 0, i32(0x0F))
    cmds = walk(e)
    assert cmds[0].args == {"xc": 248, "yc": -1, "x1": 10, "y2": 20, "x2": 30, "y1": 40}
    assert cmds[1].offset == 16


def test_fixed_size_commands():
    e = words(i32(0x00), i32(0x07), i32(1), i32(0x08), i32(0), i32(0x09), f32(1.0), f32(1.0),
              i32(0x0A), f32(0.0), f32(1.0), f32(0.0), i32(0x0C), f32(2.0), f32(3.0), i32(0x0F))
    kinds = [c.kind for c in walk(e)]
    assert kinds == [0x00, 0x07, 0x08, 0x09, 0x0A, 0x0C, -1]


def test_walk_wraps_at_0x8000():
    e = [0] * 0x8000
    e[0x7FFE] = 0x01                       # object header straddles the wrap: tex at 0x8000 -> 0
    e[0x7FFF] = 0
    e[0] = 0x55
    cmds = walk(e, start=0x7FFE)
    assert cmds[0].kind == 0x01 and cmds[0].args["tex_adr"] == 0x55
    assert cmds[-1].kind == -1 and cmds[-1].args["stopped_on"] is None   # all-zero list: full-wrap guard


def test_parse_log_round_trip(tmp_path):
    e = words(i32(0x01), i32(7), i32(8), i32(0), i32(0x0F))
    hexline = "".join(f"{w:04x}" for w in e)
    log = tmp_path / "dl.txt"
    log.write_text(f"F 1400 600000 {hexline}\nF 1410 610000 {hexline}\n")
    frames = list(parse_log(log))
    assert [(f, b) for f, b, _ in frames] == [(1400, 0x600000), (1410, 0x610000)]
    assert frames[0][2][0].args["poly_adr"] == 8
