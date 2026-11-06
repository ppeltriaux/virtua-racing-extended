import struct

import pytest

from vrtools.arcade import course
from vrtools.arcade.course import (COURSE_BANK, TILE_TABLE, BankHeader, CourseEntry, CourseError, RoadPoint, Segment,
                                   TileEntry, collision_cell, collision_map, course_table, encode_header, encode_road_point,
                                   encode_segment, encode_tile_record, gfx_uploads, road_centreline, road_lines, segments,
                                   tile_table, verify_lossless)
from vrtools.arcade.romset import REQUIRED_FILES, RomSet

W = 0x100000  # window base


def _bank(points=2, nseg=3):
    """Synthetic 1 MB course bank following the Big Forest layout, with tiny tables."""
    b = bytearray(b"\xff" * 0x100000)
    seg_off, lines_off, counts_off = 0x20, 0x300, 0x200
    # header
    hdr = struct.pack("<8I", W + 0x1000, W + seg_off, W + counts_off, W + counts_off + 4, W + counts_off + 8,
                      W + lines_off, W + lines_off, W + lines_off)
    b[0:32] = hdr
    b[0x20:0x28] = struct.pack("<4H", points, 0, nseg, 0)       # count = number of segments; entry 0 holds the counts
    for k in range(1, nseg + 1):
        b[0x20 + 8 * k:0x28 + 8 * k] = struct.pack("<4H", 2, k - 1, (k - 1) % points, 1)
    # counts block: two pointers then (ptr, count) pairs for 8 lines
    b[counts_off:counts_off + 8] = struct.pack("<2I", W + 0x2000, W + 0xa000)   # collision map, surface table
    pairs = b""
    for i in range(8):                                                             # (ptr, count) pairs from +8
        pairs += struct.pack("<2I", W + lines_off + 16 * points * i, points)
    b[counts_off + 8:counts_off + 8 + len(pairs)] = pairs
    for i in range(8):
        for p in range(points):
            off = lines_off + 16 * points * i + 16 * p
            b[off:off + 16] = struct.pack("<2f2I", 10.0 * p + i, -5.0 * p, 0x20000, p << 16)
    # graphics directory at 0x1000: pointers to (src, dst) pair lists (one per phase), 0-terminated;
    # the pair list at 0x1010; the src block at 0x1100 begins with a count word (copied << 4 halfwords)
    b[0x1000:0x1000 + 8] = struct.pack("<2I", W + 0x1010, 0)
    b[0x1010:0x1010 + 16] = struct.pack("<4I", W + 0x1100, 0x7e0000, 0, 0)
    b[0x1100:0x1104] = struct.pack("<I", 2)
    # collision map (0x8000 bytes) and surface table (0x100) live where the pointer block says: 0x2000 / 0xa000
    b[0x2000:0xa000] = bytes(0x8000)
    b[0xa000:0xa100] = bytes(0x100)
    # collision map region must exist (0xcf98..) -- leave 0xff
    return bytes(b)


def _rs(bank_bytes: dict[int, bytes], tile_tables: dict[int, bytes] | None = None) -> RomSet:
    files = {name: bytes(0x80000 if name.startswith(("epr-14882", "epr-14883", "mpr-148")) and not name.startswith("mpr-1489") else 0x20000)
             for name in REQUIRED_FILES}
    # data ROM pairs: build the 4 MB image then split lanes
    data = bytearray(b"\xff" * 0x400000)
    for bank, bb in bank_bytes.items():
        data[bank * 0x100000:(bank + 1) * 0x100000] = bb
    pairs = (("mpr-14880.6", "mpr-14881.7"), ("mpr-14884.8", "mpr-14885.9"), ("mpr-14886.10", "mpr-14887.11"), ("mpr-14888.12", "mpr-14889.13"))
    for i, (a, bname) in enumerate(pairs):
        chunk = data[i * 0x100000:(i + 1) * 0x100000]
        files[a], files[bname] = bytes(chunk[0::2]), bytes(chunk[1::2])
    prog = bytearray(b"\x00" * 0x100000)
    for addr, blob in (tile_tables or {}).items():
        prog[addr - 0x200000:addr - 0x200000 + len(blob)] = blob
    files["epr-14882.14"], files["epr-14883.15"] = bytes(prog[0::2]), bytes(prog[1::2])
    for name in ("mpr-14890.26", "mpr-14891.27", "mpr-14892.28", "mpr-14893.29", "mpr-14894.30", "mpr-14895.31", "mpr-14896.32", "mpr-14897.33"):
        files[name] = bytes(0x200000)
    for name in ("mpr-14898.39", "mpr-14899.40", "mpr-14900.41", "mpr-14901.42"):
        files[name] = bytes(0x80000)
    files["315-5573.bin"] = bytes(0x2000)
    for name in ("epr-14878a.4", "epr-14879a.5"):
        files[name] = bytes(0x20000)
    return RomSet.from_files(files)


@pytest.fixture(scope="module")
def synth():
    tbl = b"".join(struct.pack("<I", 0x2e9980 + 16 * i) for i in range(256))
    recs = b"".join(struct.pack("<4I", 0x100 + i, 0x40000 + i, 300 if i % 2 else 0, 0) for i in range(256))
    return _rs({3: _bank(), 1: _bank(points=3), 2: _bank()}, {TILE_TABLE[0]: tbl, 0x2e9980: recs})


def test_course_table_decodes_three_banks(synth):
    entries = course_table(synth)
    assert [e.bank for e in entries] == [3, 1, 2] and [e.index for e in entries] == [0, 1, 2]
    assert entries[0].header.road_points == 2 and entries[0].header.segment_count == 3
    assert entries[1].header.road_points == 3
    assert entries[0].header.gfx_dir == W + 0x1000


def test_course_table_rejects_bad_header():
    bad = bytearray(_bank()); bad[0:4] = struct.pack("<I", 0x7fffffff)
    with pytest.raises(CourseError, match="0x7fffffff"):
        course_table(_rs({3: bytes(bad), 1: _bank(), 2: _bank()}))


def test_road_lines_and_centreline(synth):
    e = course_table(synth)[0]
    lines = road_lines(synth, e)
    assert len(lines) == 8 and all(len(l) == 2 for l in lines)
    assert lines[0][1] == RoadPoint(10.0, -5.0, 0x20000, 1 << 16)
    assert lines[3][0].x == 3.0
    assert road_centreline(lines) == [(0.0, -0.0), (10.0, -5.0)]


def test_segments(synth):
    e = course_table(synth)[0]
    s = segments(synth, e)
    assert s == [Segment(0, 0, 1), Segment(1, 1, 1), Segment(2, 0, 1)]


def test_tile_table_and_cells(synth):
    t = tile_table(synth, 0)
    assert len(t) == 256 and t[17] == TileEntry(17, 1, 1, 0x111, 0x40011, 300)
    assert t[0].size == 0


def test_tile_record_guards():
    with pytest.raises(CourseError):
        encode_tile_record(TileEntry(0, 0, 0, 0x800010, 0, 1))      # RAM bit
    with pytest.raises(CourseError):
        encode_tile_record(TileEntry(0, 0, 0, 0x400000, 0, 1))      # past polygon ROM
    with pytest.raises(CourseError):
        encode_tile_record(TileEntry(0, 0, 0, 0x10, 0x100000, 1))   # tex out of range
    assert encode_tile_record(TileEntry(5, 0, 5, 0x10, 0x4000, 7)) == struct.pack("<4I", 0x10, 0x4000, 7, 0)


def test_collision_cell_formula():
    assert collision_cell(-1024.0, -1024.0) == 0
    assert collision_cell(-176.7, 59.9) == 53 + 128 * 67   # float->int truncates toward zero first; x low, z high
    with pytest.raises(CourseError):
        collision_cell(1024.0, 0.0)


def test_encoders_round_trip(synth):
    e = course_table(synth)[0]
    assert encode_header(e.header) == synth.data[e.base:e.base + 32]
    assert encode_road_point(road_lines(synth, e)[0][1]) == synth.data[e.base + 0x300 + 16:e.base + 0x300 + 32]
    assert encode_segment(segments(synth, e)[0]) == struct.pack("<4H", 2, 0, 0, 1)
    with pytest.raises(CourseError):
        encode_segment(Segment(70000, 0, 1))


def test_gfx_uploads(synth):
    e = course_table(synth)[0]
    assert gfx_uploads(synth, e) == [(W + 0x1100, 0x7e0000, 2 << 4)]


def test_verify_lossless_synthetic(synth):
    assert verify_lossless(synth, 0) == []


# --- real ROM ---------------------------------------------------------------

PHASE1_TILES = frozenset([0x67ec, 0x74bd, 0x9a4b, 0xa956, 0xc6d5, 0xf48a, 0x101c0, 0x12bdd, 0x1371f, 0x14fda, 0x16210, 0x1881d])


def test_real_course_table(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    e = course_table(rs)
    assert [x.bank for x in e] == [3, 1, 2]
    assert e[0].header.road_points == 0x152 and e[0].header.segment_count == 0x445
    assert e[1].header.road_points == 0x1a2 and e[2].header.road_points == 0x250


def test_real_big_forest_lines_and_tiles(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    e = course_table(rs)[0]
    lines = road_lines(rs, e)
    assert len(lines[0]) == 338 and abs(lines[0][0].x + 193.0) < 0.1
    c = road_centreline(lines)
    length = sum(((c[i + 1][0] - c[i][0]) ** 2 + (c[i + 1][1] - c[i][1]) ** 2) ** 0.5 for i in range(len(c) - 1))
    assert 2000 < length < 6000
    t = tile_table(rs, 0)
    assert {x.poly_adr for x in t} & PHASE1_TILES
    assert sum(1 for x in t if x.size) == 76
    assert len(segments(rs, e)) == 1093                                    # the count word is the segment count (Phase 6)
    m = collision_map(rs, e)
    assert len(m) == 16384 and m[collision_cell(-176.7, 59.9)] != 0 and m[collision_cell(600.0, 600.0)] == 0


@pytest.mark.parametrize("index", [0, 1, 2])
def test_real_round_trip(romset_zip, index):
    assert verify_lossless(RomSet.from_zip(romset_zip), index) == []


def test_collision_and_surface_follow_the_pointer_block(synth):
    e = course_table(synth)[0]
    assert len(collision_map(synth, e)) == 16384
    assert course.surface_table(synth, e) == bytes(256)
    bad = bytearray(synth.data[e.base:e.base + 0x100000])
    struct.pack_into("<I", bad, 0x200, 0x7fffffff)                  # collision ptr not a window address
    rs2 = _rs({3: bytes(bad), 1: _bank(points=3), 2: _bank()}, {TILE_TABLE[0]: b"", 0x2e9980: b""})
    with pytest.raises(CourseError, match="collision"):
        collision_map(rs2, course_table(rs2)[0])


def test_tile_table_validates_records():
    tbl = b"".join(struct.pack("<I", 0x2e9980 + 16 * i) for i in range(256))
    recs = bytearray(b"".join(struct.pack("<4I", 0x100 + i, 0x40000 + i, 1, 0) for i in range(256)))
    struct.pack_into("<I", recs, 16 * 7, 0x800100)                   # RAM bit in cell 7
    rs = _rs({3: _bank(), 1: _bank(points=3), 2: _bank()}, {TILE_TABLE[0]: tbl, 0x2e9980: bytes(recs)})
    with pytest.raises(CourseError, match="cell 7"):
        tile_table(rs, 0)
    with pytest.raises(CourseError, match="course index"):
        tile_table(rs, 9)


def test_every_encoder_rejects_oversized_values(synth):
    e = course_table(synth)[0]
    with pytest.raises(CourseError):
        encode_road_point(RoadPoint(1.0, 2.0, 1 << 32, 0))
    with pytest.raises(CourseError):
        encode_road_point(RoadPoint(1e40, 2.0, 0, 0))
    with pytest.raises(CourseError):
        encode_header(BankHeader(0x7fffffff, *([W] * 7), 1, 1))
    with pytest.raises(CourseError):
        course.encode_pointer_block(course.decode_pointer_block(synth, e)._replace(collision=0x5))
    with pytest.raises(CourseError):
        course.encode_collision_map([0] * 16383)
    with pytest.raises(CourseError):
        course.encode_surface_table(b"\x00" * 255)
    with pytest.raises(CourseError):
        course.encode_gfx_directory([(W, 0x7e0000)] + [(0x5, 0x7e0000)])


def test_gfx_uploads_follow_directory_of_lists(synth):
    e = course_table(synth)[0]
    assert gfx_uploads(synth, e) == [(W + 0x1100, 0x7e0000, 2 << 4)]
    assert gfx_uploads(synth, e, phase=1) == []


def test_decode_and_encode_course(synth):
    c = course.decode_course(synth, 0)
    out = course.encode_course(c)
    e = c.entry
    assert out[e.base] == synth.data[e.base:e.base + 32]
    assert out[e.base + 0x28] == synth.data[e.base + 0x28:e.base + 0x28 + 8 * 3]
    coll = course._win(e.base, c.pointers.collision, "")
    assert out[coll] == synth.data[coll:coll + 0x8000]
    assert out[e.base + 0x1010] == struct.pack("<3I", W + 0x1100, 0x7e0000, 0)
    assert TILE_TABLE[0] in out and len(out[TILE_TABLE[0]]) == 1024
    assert verify_lossless(synth, 0) == []
