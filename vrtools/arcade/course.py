"""Decoders and encoders for the arcade's per-course data (see docs/formats/model1-course-tables.md).

A course owns one 1 MB data-ROM bank, mapped into the V60 window at 0x100000; every pointer inside the
bank is a window address (0x10xxxx). The visible-geometry grid (256 cells) lives in program ROM.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import NamedTuple

from vrtools.arcade.colours import RESERVED_CODE
from vrtools.arcade.romset import RomSet

WINDOW = 0x100000
BANK_SIZE = 0x100000
COURSE_BANK = {0: 3, 1: 1, 2: 2}            # menu order Big Forest, Bay Bridge, Acropolis -> data bank (measured)
TILE_TABLE = {0: 0x2F2056, 1: 0x2F1856, 2: 0x2F1C56}   # program-ROM tile pointer tables (RAM 0x501948 at runtime)
PIT_ENTRY_TABLE = 0xFE8E0C                  # boot ROM: halfword per course-data slot = first pit-lane quad (0xffff: no pit lane)
# Phase 7: the code sites the ten-course directory re-routes (docs/spike/2026-11-m4-recon.md)
SELECT_TABLE = 0xFC35C7                     # 24 bytes per menu entry; its base is a 32-bit displacement at the two refs
SELECT_TABLE_REFS = (0xFC270B, 0xFC28A3)
LOADER = 0xFE48ED                           # course loader (header copy, per-course tables, TGP 0x0680); whole routine
LOADER_LEN = 0xB7
BANK_SITES = (0xFE1D37, 0xFE2160, 0xFE2B07, 0xFE2CF7, 0xFE415B)   # `mov.b 501934,R0; inc.b; shl.b #4; add.b #1; mov.b R0,E00004`
BANK_SITE_LEN = 0x16                        # (0xfe2160 is the attract demo's course load, 0xfe415b the single-player race's;
BANK_SITE_PATTERN = bytes.fromhex("0920f2") + b"????" + bytes.fromhex("d960a920e48020e10900f30400e000")   # `mov.b #1, E00004` sites map bank 0)
PIT_CHECK = 0xFE8E8F                        # loads the pit-entry quad of the course into R0 (then cmp.h R0, 150[R25])
PIT_CHECK_LEN = 0xD
MUSIC_SITE = 0xFC0BB8                       # `movz.hw 501940,R0; mov.h FC117D[PC](R0),R0` -> R0 = race-start music command (then jsr FFA246)
MUSIC_SITE_LEN = 0xF
CAR_TABLE_SITE = 0xFE8A91                   # `mov.w #FCD395,R10; test.b 40DC8C; be +7; mov.w #FCD195,R10` -> R10 = car table (Phase 9)
CAR_TABLE_SITE_LEN = 0x16
CAR_TABLE_PATTERN = bytes.fromhex("2d2af495d3fc00f0f38cdc400064092d2af495d1fc00")
# Phase 14: the HUD map and the off-course limit (docs/spike/2026-11-presentation-recon.md §2-3)
MAP_TX_RAM = 0x50231C                       # the map section's screen translate x: the game's RAM copy of its boot ROM record 0xff9e9a,
                                            # made once at boot (149.0) and read by the display-list writer every frame
MAP_CROSS_RAM = 0x502328                    # our tile-byte offset of the player's cross (0 = the game's cell), in the never-touched padding
OFF_COURSE_RAM = 0x50232C                   # our off-course limit in logic frames (the game's immediate was 128), same padding
# Phase 18b: the backdrop's upload directory is word 0 of the course header; the game read it at window 0x100000 (the
# bank's original header). Both readers call the `gfx` routine, which takes the current entry's own header's directory
GFX_DIR_SITES = (0xFFE007, 0xFFE49E)        # `mov.w 100000, R20`: the course-load uploads (phases 0-1), the per-frame streaming
GFX_DIR_PATTERN = bytes.fromhex("2d34f300001000")
OFF_COURSE_COUNTER = 0x50115C               # the game's count of logic frames with a wheel off the tarmac; past the limit the car is put back
CROSS_TILE_CELL = 0x700AE0                  # tile page 0, cell (48, 21): where the game draws the 3x3 cross at race start
MAP_CROSS_SITE = 0xFEABF5                   # `movea.w #700AE0, R1` before `mov.w #2FA59A, R0; jsr FF9436` (draw the cross pattern)
MAP_CROSS_SITE_LEN = 7
MAP_CROSS_PATTERN = bytes.fromhex("4421f2eb5e71ff")
MAP_OBJ_SITE = 0xFEAC10                     # Phase 22b: `mov.w FEAC1B[PC](R0), 18[R25]`: the HUD map entity's outline object list by data
MAP_OBJ_SITE_LEN = 10                       # index (R0) from the three-entry table right after the routine's rsr
MAP_OBJ_PATTERN = bytes.fromhex("2dc0c0f20b0000001918")
MAP_OBJ_TABLE = 0xFEAC1B                    # (0x2e0050 Bay Bridge, 0x2e0060 Acropolis, 0x2e0040 Big Forest)
PIT_POSE = 0xFF4061                         # Phase 22i: R10, R11, R12 = the course's pit box (x, y, z) from Acropolis's or Big Forest's table by
                                            # data index; the PIT START grid is placed there too (0xfc005f, 0xff21a5, 0xff4165: left alone)
PIT_BOX_CALLS = (0xFE969E, 0xFE9922, 0xFE9A29, 0xFE9C5A, 0xFE9DDD, 0xFE9E5D)   # the pit autopilot's `jsr FF4061[PC]` (6 bytes each): the
PIT_BOX_CALL_LEN = 6                                                            # point it drives the car to -> `pitbox`
PIT_CREW_CALLS = (0xFF27D8, 0xFF2D69, 0xFF33C7, 0xFF3A1B)   # the four pit works' crew spawns: `bsr FF4061; mov.w #0, [R24]` (7 bytes) ->
PIT_CREW_CALL_LEN = 7                                       # `pitboxcrew` (the box, then that FIFO write)


def pit_box_call_pattern(site: int) -> bytes:
    return bytes.fromhex("e8f2") + struct.pack("<i", PIT_POSE - site)


def pit_crew_call_pattern(site: int) -> bytes:
    return b"\x48" + struct.pack("<h", PIT_POSE - site) + bytes.fromhex("2d80e078")


PIT_AIM_SITE = 0xFE96A4                     # the autopilot's aim and bearing: R9 = box.z - 10 while the car's z is short of it, else box.z;
PIT_AIM_SITE_LEN = 0x3C                     # R4 = bearing from the car to (R10, R9) (TGP 0x7800000). Along the lane only on a +z lane -> `pitaim`
PIT_AIM_PATTERN = bytes.fromhex("2d80f400008000782d0c782d80f400002041782429775cc06919267c06002d4c692d80f400008007782d09782d80191e78"
                                "2d801926782d0a78242477")
PIT_STOPS_SITE = 0xFE8BD8                   # the race start's pit stops left (+0x1bf): 0 for Bay Bridge's data index, 5 in linked play, else 2
PIT_STOPS_SITE_LEN = 0x2B                   # unless [0x40d826] >= 2 -> `pitstops` (0 for an entry without a pit quad, else as the game)
PIT_STOPS_PATTERN = bytes.fromhex("b04060b880e0f2598d51ff742000f0f21f8551ff7409000920e57a1100b880e2f2314c42ff7d06000920e2")
PIT_STOPS_MODE = 0x40D826
PIT_PARK_SITE = 0xFE98C7                    # the park at the box: `mov.w R10, 1E[R25]; mov.w R12, 26[R25]; mov.h #0, 6A[R25]` (facing +z)
PIT_PARK_SITE_LEN = 13
PIT_PARK_PATTERN = bytes.fromhex("2d0a191e2d0c19261b80e0196a")
OFF_COURSE_SITE = 0xFEBCDF                  # `cmp.w #80, 50115C[PC]; ble` after `inc.w 50115C[PC]`
OFF_COURSE_SITE_LEN = 12
OFF_COURSE_PATTERN = bytes.fromhex("bc80f480000000f27d5451ff")
MUSIC_TABLE = 0xFC117D                      # three halfwords: 0xb001 BF, 0xb00d BB, 0xb00e AC
TILE_TABLE_PTRS = 0xFE49A4                  # three program-ROM tile table addresses by data index
SPAWN_TABLE_PTRS = 0xFDA543                 # three entity spawn lists by data index (RAM 0x50197c)
CODE_FREE = (0x200000 + RESERVED_CODE[0], RESERVED_CODE[1])   # program ROM for the directory and the new routines (colours.RESERVED_CODE keeps the colour allocator out)
SEGMENT_ARRAY = 0x20                        # entry 0 holds the counts; entries 1..n are segments
LINE_COUNT = 8                              # (ptr, count) pairs in the pointer block: the centreline and seven AI lines (the car setup reads all eight)
COLLISION_CELLS = 128 * 128                 # halfword map, pointer in the bank's pointer block
SURFACE_SIZE = 256                          # byte table, pointer in the pointer block
RECORD_SIZE = 16
POLY_ROM_WORDS = 0x400000
TEX_LIMIT = 0x100000


class CourseError(Exception):
    pass


def _check_win(addr: int, what: str) -> None:
    if not (WINDOW <= addr < WINDOW + BANK_SIZE):
        raise CourseError(f"{what}: {addr:#x} is not a window address (0x100000..0x1fffff)")


@dataclass(frozen=True)
class BankHeader:
    gfx_dir: int          # +0x00 window address of the graphics-upload directory
    seg_array: int        # +0x04 window address of the segment array (counts entry)
    ptr_block: int        # +0x08 window address of the three-pointer block
    ptr_block_b: int      # +0x0c (ptr_block + 4)
    ptr_block_c: int      # +0x10 (ptr_block + 8)
    centre: int           # +0x14 window address of the centreline point list
    centre_b: int         # +0x18
    centre_c: int         # +0x1c
    road_points: int      # +0x20 (u16)
    segment_count: int    # +0x24 (u16): number of segments (= tarmac collision quads); entries 1..n follow the counts entry


@dataclass(frozen=True)
class CourseEntry:
    index: int
    bank: int
    base: int             # absolute offset of the bank in RomSet.data
    header: BankHeader


@dataclass(frozen=True)
class RoadPoint:
    x: float
    z: float
    heading: int          # raw u32 (16.16 heading in the centreline; 0 / 0x20000 in the other lines)
    link: int             # raw u32: high half = segment index, low half = TBD


@dataclass(frozen=True)
class Segment:
    index: int
    road_point: int
    flag: int             # 1 or 66


class PointerBlock(NamedTuple):
    collision: int                      # window address of the 128x128 collision map
    surface: int                        # window address of the surface byte table
    lines: tuple[tuple[int, int], ...]  # eight (ptr, count) pairs: centreline then seven AI lines


@dataclass(frozen=True)
class TileEntry:
    cell: int             # 0..255, cell = z_cell * 16 + x_cell
    x_cell: int
    z_cell: int
    poly_adr: int
    tex_adr: int
    size: int


def _win(entry_base: int, addr: int, what: str) -> int:
    """Window address -> absolute data offset, validated against the bank."""
    if not (WINDOW <= addr < WINDOW + BANK_SIZE):
        raise CourseError(f"{what}: {addr:#x} is not a window address (0x100000..0x1fffff)")
    return entry_base + (addr - WINDOW)


def _header(rs: RomSet, base: int) -> BankHeader:
    w = struct.unpack_from("<8I", rs.data, base)
    for i, v in enumerate(w):
        if not (WINDOW <= v < WINDOW + BANK_SIZE):
            raise CourseError(f"bank at {base:#x}: header word {i} = {v:#x} is not a window address")
    pts, segs = struct.unpack_from("<2H", rs.data, base + 0x20)[0], struct.unpack_from("<2H", rs.data, base + 0x24)[0]
    return BankHeader(*w, pts, segs)


def course_table(rs: RomSet) -> list[CourseEntry]:
    out = []
    for index, bank in COURSE_BANK.items():
        base = bank * BANK_SIZE
        out.append(CourseEntry(index, bank, base, _header(rs, base)))
    return out


def course_entry_at(rs: RomSet, bank: int, window_base: int = WINDOW) -> CourseEntry:
    """A course whose header sits at `window_base` inside data bank `bank` (the originals: 0x100000; relocated
    blobs: anywhere in the bank's free space)."""
    if not (0 <= bank < len(rs.data) // BANK_SIZE):
        raise CourseError(f"bank {bank} is not in the data ROM")
    base = bank * BANK_SIZE
    return CourseEntry(-1, bank, base, _header(rs, _win(base, window_base, "header")))


def encode_header(h: BankHeader) -> bytes:
    words = (h.gfx_dir, h.seg_array, h.ptr_block, h.ptr_block_b, h.ptr_block_c, h.centre, h.centre_b, h.centre_c)
    for v in words:
        if not (WINDOW <= v < WINDOW + BANK_SIZE):
            raise CourseError(f"header pointer {v:#x} is not a window address")
    return struct.pack("<8I", *words)


def decode_pointer_block(rs: RomSet, e: CourseEntry) -> PointerBlock:
    """Pointer block: collision map ptr, surface table ptr, then eight (ptr, count) line pairs (RAM 0x501960 points
    at the first pair; the car setup reads pair `line` for each car's AI line 0..7)."""
    off = _win(e.base, e.header.ptr_block, "ptr_block")
    collision, surface = struct.unpack_from("<2I", rs.data, off)
    lines = []
    for i in range(LINE_COUNT):
        ptr, cnt = struct.unpack_from("<2I", rs.data, off + 8 + 8 * i)
        _check_win(ptr, f"road line {i}")
        if cnt == 0 or (ptr - WINDOW) + 16 * cnt > BANK_SIZE:
            raise CourseError(f"road line {i}: count {cnt} runs outside the bank")
        lines.append((ptr, cnt))
    return PointerBlock(collision, surface, tuple(lines))


def encode_pointer_block(pb: PointerBlock) -> bytes:
    _check_win(pb.collision, "collision map pointer")
    _check_win(pb.surface, "surface table pointer")
    if len(pb.lines) != LINE_COUNT:
        raise CourseError(f"pointer block needs {LINE_COUNT} lines, got {len(pb.lines)}")
    out = struct.pack("<2I", pb.collision, pb.surface)
    for i, (ptr, cnt) in enumerate(pb.lines):
        _check_win(ptr, f"road line {i}")
        if not (0 < cnt < 0x10000):
            raise CourseError(f"road line {i}: bad count {cnt}")
        out += struct.pack("<2I", ptr, cnt)
    return out


def _line_table(rs: RomSet, e: CourseEntry) -> list[tuple[int, int]]:
    return [(cnt, ptr) for ptr, cnt in decode_pointer_block(rs, e).lines]


def road_lines(rs: RomSet, e: CourseEntry) -> list[list[RoadPoint]]:
    lines = []
    for cnt, ptr in _line_table(rs, e):
        off = _win(e.base, ptr, "road line")
        pts = []
        for i in range(cnt):
            x, z, heading, link = struct.unpack_from("<2f2I", rs.data, off + 16 * i)
            pts.append(RoadPoint(x, z, heading, link))
        lines.append(pts)
    return lines


F32_MAX = 3.4028234663852886e38


def encode_road_point(p: RoadPoint) -> bytes:
    for name, v in (("x", p.x), ("z", p.z)):
        if not math.isfinite(v) or abs(v) > F32_MAX:
            raise CourseError(f"road point {name}={v} does not fit a float32")
    for name, v in (("heading", p.heading), ("link", p.link)):
        if not (0 <= v < 1 << 32):
            raise CourseError(f"road point {name}={v} does not fit a u32")
    return struct.pack("<2f2I", p.x, p.z, p.heading, p.link)


def road_centreline(lines: list[list[RoadPoint]]) -> list[tuple[float, float]]:
    return [(p.x, p.z) for p in lines[0]]


def segments(rs: RomSet, e: CourseEntry) -> list[Segment]:
    base = _win(e.base, e.header.seg_array, "segment array")
    n = e.header.segment_count                    # the number of segments (entry 0 of the array holds the counts)
    out = []
    for k in range(1, n + 1):
        two, idx, point, flag = struct.unpack_from("<4H", rs.data, base + 8 * k)
        if two != 2 or idx != k - 1:                 # entries are 0-based; entry 0 of the array holds the counts
            raise CourseError(f"segment {k}: unexpected record ({two}, {idx}, {point}, {flag})")
        out.append(Segment(k - 1, point, flag))
    return out


def encode_segment(s: Segment) -> bytes:
    if not (0 <= s.index < 0x10000 and 0 <= s.road_point < 0x10000 and 0 <= s.flag < 0x10000):
        raise CourseError(f"segment fields out of range: {s}")
    return struct.pack("<4H", 2, s.index, s.road_point, s.flag)


def pit_entry_table(rs: RomSet) -> tuple[int | None, int | None, int | None]:
    """Per course-data slot (Bay Bridge, Acropolis, Big Forest): the collision quad index at which the player enters
    the pit sequence (its lap-position quad equal to it or the next), None when the slot has no pit lane. The
    player handler at 0xfe8e88 compares entity+0x150 (last tarmac quad) with this table; Big Forest's 30 is the
    first pit-lane quad beside the start line (segments flagged 66)."""
    return tuple(None if v == 0xFFFF else v for v in struct.unpack("<3H", rs.read_v60(PIT_ENTRY_TABLE, 6)))


def tile_table(rs: RomSet, index: int) -> list[TileEntry]:
    if index not in TILE_TABLE:
        raise CourseError(f"course index {index} has no tile table")
    return tile_table_at(rs, TILE_TABLE[index])


def tile_table_at(rs: RomSet, tbl: int) -> list[TileEntry]:
    """The 256-cell tile table whose pointer table is at program-ROM address `tbl`."""
    out = []
    for cell in range(256):
        ptr = struct.unpack_from("<I", rs.read_v60(tbl + 4 * cell, 4))[0]
        try:
            poly, tex, size, zero = struct.unpack("<4I", rs.read_v60(ptr, RECORD_SIZE))
        except Exception as exc:
            raise CourseError(f"tile cell {cell}: record pointer {ptr:#x} is not in program ROM") from exc
        if poly & 0x800000 or poly >= POLY_ROM_WORDS or tex >= TEX_LIMIT or zero != 0:
            raise CourseError(f"tile cell {cell}: bad record (poly {poly:#x}, tex {tex:#x}, size {size}, tail {zero})")
        out.append(TileEntry(cell, cell & 15, cell >> 4, poly, tex, size))
    return out


def encode_tile_record(t: TileEntry) -> bytes:
    if t.poly_adr & 0x800000 or t.poly_adr >= POLY_ROM_WORDS:
        raise CourseError(f"tile {t.cell}: polygon address {t.poly_adr:#x} is not a polygon-ROM word index")
    if not (0 <= t.tex_adr < TEX_LIMIT) or not (0 <= t.size < 0x10000):
        raise CourseError(f"tile {t.cell}: texture/size out of range")
    return struct.pack("<4I", t.poly_adr, t.tex_adr, t.size, 0)


def collision_cell(x: float, z: float) -> int:
    xc, zc = (int(x) + 0x400) >> 4, (int(z) + 0x400) >> 4
    if not (0 <= xc < 128 and 0 <= zc < 128):
        raise CourseError(f"({x}, {z}) is outside the 128x128 collision map")
    return xc + 128 * zc                     # x in the low 7 bits, z in the high 7 (FED52B)


def collision_map(rs: RomSet, e: CourseEntry) -> list[int]:
    pb = decode_pointer_block(rs, e)
    off = _win(e.base, pb.collision, "collision map pointer")
    return list(struct.unpack_from(f"<{COLLISION_CELLS}H", rs.data, off))


def encode_collision_map(cells: list[int]) -> bytes:
    if len(cells) != COLLISION_CELLS or any(not (0 <= v < 0x10000) for v in cells):
        raise CourseError(f"collision map needs {COLLISION_CELLS} u16 cells")
    return struct.pack(f"<{COLLISION_CELLS}H", *cells)


def surface_table(rs: RomSet, e: CourseEntry) -> bytes:
    pb = decode_pointer_block(rs, e)
    off = _win(e.base, pb.surface, "surface table pointer")
    return rs.data[off:off + SURFACE_SIZE]


def encode_surface_table(table: bytes) -> bytes:
    if len(table) != SURFACE_SIZE:
        raise CourseError(f"surface table must be {SURFACE_SIZE} bytes")
    return bytes(table)


def gfx_directory(rs: RomSet, e: CourseEntry) -> list[int]:
    """The directory at header+0: window pointers to (src, dst) pair lists, one per upload phase, 0-terminated."""
    off = _win(e.base, e.header.gfx_dir, "gfx directory")
    out: list[int] = []
    lowest = None
    while True:
        if lowest is not None and off >= lowest:
            return out                                          # the first pair list starts here (inline)
        ptr = struct.unpack_from("<I", rs.data, off)[0]
        if ptr == 0:
            return out
        _check_win(ptr, "gfx pair list")
        target = _win(e.base, ptr, "gfx pair list")
        lowest = target if lowest is None else min(lowest, target)
        out.append(ptr)
        off += 4


def gfx_uploads(rs: RomSet, e: CourseEntry, phase: int = 0) -> list[tuple[int, int, int]]:
    """(src window address, dst V60 address, halfword count) for one upload phase.

    The loader (0xffe583) is called with directory[phase]; each (src, dst) pair copies (word at src) << 4
    halfwords from src to dst (tile RAM 0x7exxxx/0x7fxxxx or palette 0x900xxx)."""
    lists = gfx_directory(rs, e)
    if phase >= len(lists):
        return []
    off = _win(e.base, lists[phase], "gfx pair list")
    out = []
    while True:
        src, dst = struct.unpack_from("<2I", rs.data, off)
        if src == 0:
            return out
        count = struct.unpack_from("<I", rs.data, _win(e.base, src, "gfx block"))[0] << 4
        out.append((src, dst, count))
        off += 8


def encode_gfx_directory(pairs: list[tuple[int, int]]) -> bytes:
    """Encode one (src, dst) pair list, 0-terminated."""
    out = b""
    for src, dst in pairs:
        _check_win(src, "gfx block")
        if not (0 <= dst < 1 << 32):
            raise CourseError(f"gfx destination {dst:#x} out of range")
        out += struct.pack("<2I", src, dst)
    return out + struct.pack("<I", 0)                   # a single zero word terminates the list


@dataclass(frozen=True)
class Course:
    entry: CourseEntry
    pointers: PointerBlock
    lines: list[list[RoadPoint]]
    segments: list[Segment]
    collision: list[int]
    surface: bytes
    tiles: list[TileEntry]
    gfx_lists: list[int]                     # directory entries (opaque beyond phase 0)
    gfx_pairs: list[list[tuple[int, int]]]   # (src, dst) pair list for phase 0 only (the verified loader path)


def decode_course(rs: RomSet, index: int) -> Course:
    e = course_table(rs)[index]
    lists = gfx_directory(rs, e)
    pairs = [[(src, dst) for src, dst, _ in gfx_uploads(rs, e, 0)]] if lists else []
    return Course(e, decode_pointer_block(rs, e), road_lines(rs, e), segments(rs, e), collision_map(rs, e),
                  surface_table(rs, e), tile_table(rs, index), lists, pairs)


def encode_course(c: Course) -> dict[int, bytes]:
    """Every table re-encoded, keyed by absolute data-ROM offset (bank pieces) or V60 address (program ROM)."""
    e = c.entry
    out: dict[int, bytes] = {}
    out[e.base] = encode_header(e.header)
    out[_win(e.base, e.header.ptr_block, "ptr_block")] = encode_pointer_block(c.pointers)
    for (ptr, cnt), pts in zip(c.pointers.lines, c.lines):
        if len(pts) != cnt:
            raise CourseError(f"line at {ptr:#x}: {len(pts)} points but count {cnt}")
        out[_win(e.base, ptr, "line")] = b"".join(encode_road_point(p) for p in pts)
    out[_win(e.base, e.header.seg_array, "segments") + 8] = b"".join(encode_segment(s) for s in c.segments)
    out[_win(e.base, c.pointers.collision, "collision")] = encode_collision_map(c.collision)
    out[_win(e.base, c.pointers.surface, "surface")] = encode_surface_table(c.surface)
    out[_win(e.base, e.header.gfx_dir, "gfx dir")] = b"".join(struct.pack("<I", p) for p in c.gfx_lists)   # pointers only; lists follow inline
    for ptr, pairs in zip(c.gfx_lists, c.gfx_pairs):
        out[_win(e.base, ptr, "gfx list")] = encode_gfx_directory(pairs)
    tbl = TILE_TABLE[e.index]
    out[tbl] = b"".join(struct.pack("<I", 0) for _ in c.tiles)   # placeholder; real pointers filled below
    return out


def verify_lossless(rs: RomSet, index: int) -> list[str]:
    """Re-encode every decoded table and compare with the ROM bytes; returns the names of mismatches."""
    c = decode_course(rs, index)
    e = c.entry
    problems = []
    for off, blob in encode_course(c).items():
        if off == TILE_TABLE[index]:
            continue                                            # pointer values are ROM facts, checked below
        if rs.data[off:off + len(blob)] != blob:
            problems.append(f"data @{off:#x}")
    tbl = TILE_TABLE[index]
    for t in c.tiles:
        ptr = struct.unpack_from("<I", rs.read_v60(tbl + 4 * t.cell, 4))[0]
        if encode_tile_record(t) != rs.read_v60(ptr, RECORD_SIZE):
            problems.append(f"tile {t.cell}")
    return problems
