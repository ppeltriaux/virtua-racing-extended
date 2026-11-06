"""Build a course bank (1 MB of V60 data ROM) from generated road tables on top of a template course's bank.

Layout of an original bank (docs/formats/model1-course-tables.md §2–§5, Phase 6 recon):
header at +0 (pointers, counts) · segment array at +0x20 (entry 0 = counts, entries 1..n) · pointer block ·
eight road lines of 16-byte points, each followed by its points 0..7 again with the heading continued by the
lap's turn (five addressed by the pointer block, three more at the same stride) · collision map (128 × 128 u16) · surface table (one byte per
collision quad) · graphics-upload directory and data · free 0xff space (Big Forest: 595 KB from +0x2b390).

The builder copies the template bank and rewrites the header counts, the segment array, the pointer block, the
eight lines (in place when they fit before the collision map, else relocated into the bank's largest free run,
pointers updated), the collision map and the surface table. Everything else — graphics uploads, backdrop,
whatever the template holds — is inherited.
"""
from __future__ import annotations

import struct

from vrtools.arcade.course import (BANK_SIZE, WINDOW, BankHeader, PointerBlock, RoadPoint, Segment, course_table,
                                   decode_pointer_block, encode_collision_map, encode_header, encode_pointer_block,
                                   encode_road_point, encode_segment, _win)
from vrtools.arcade.patch import PatchError, write_data
from vrtools.arcade.romset import RomSet
from vrtools.convert.road import RoadTables

COLLISION_BYTES = 128 * 128 * 2
POINT_BYTES = 16
MIN_FREE_RUN = 4096
WRAP_POINTS = 8                          # every line repeats its points 0..7 after the last point, heading + the lap's net turn
LINES = 8                                # five lines addressed by the pointer block, three more follow at the same stride


class BankError(Exception):
    pass


def all_lines(rs: RomSet, course_index: int) -> list[list[RoadPoint]]:
    """The eight road lines of a course: the five of the pointer block and the three that follow them."""
    e = course_table(rs)[course_index]
    pb = decode_pointer_block(rs, e)
    n = pb.lines[0][1]
    stride = POINT_BYTES * (n + WRAP_POINTS)
    first = min(_win(e.base, ptr, "line") for ptr, _ in pb.lines)
    out = []
    for k in range(LINES):
        off = first + stride * k
        out.append([RoadPoint(*struct.unpack_from("<2f2I", rs.data, off + POINT_BYTES * i)) for i in range(n)])
    return out


def _hi(word: int) -> int:
    return ((word >> 16) ^ 0x8000) - 0x8000


def line_turn(points: list[RoadPoint]) -> int:
    """The net heading change over the lap in 1/16384 turn (±16384 for a loop, 0 for a figure of eight): the
    change from the first to the last point plus the shortest signed step back to the first."""
    h0, hl = _hi(points[0].heading), _hi(points[-1].heading)
    return hl - h0 + ((h0 - hl + 8192) % 16384) - 8192


def encode_line(points: list[RoadPoint]) -> bytes:
    """A line as stored: its points, then points 0..7 again with their heading continued past the lap's end
    (heading + line_turn; on the originals' clockwise laps that reads as heading | 0xc0000000)."""
    turn = line_turn(points)
    body = b"".join(encode_road_point(p) for p in points)
    wrap = b"".join(encode_road_point(RoadPoint(p.x, p.z, (((_hi(p.heading) + turn) & 0xFFFF) << 16) | (p.heading & 0xFFFF), p.link))
                    for p in points[:WRAP_POINTS])
    return body + wrap


def _free_runs(bank: bytes, start: int) -> list[tuple[int, int]]:
    """(offset, size) of 0xff runs of at least MIN_FREE_RUN bytes from `start`, largest first."""
    runs = []
    i = start
    n = len(bank)
    while i < n:
        if bank[i] == 0xFF:
            j = i
            while j < n and bank[j] == 0xFF:
                j += 1
            if j - i >= MIN_FREE_RUN:
                runs.append((i, j - i))
            i = j
        else:
            i += 1
    return sorted(runs, key=lambda r: -r[1])


def build_bank(rs: RomSet, template_course: int, tables: RoadTables, collision_cells: list[int], surface: bytes) -> bytes:
    """A bank image for `tables` (eight lines, segments) on the template course's bank: header counts, segment
    array, pointer block, the eight lines with their wrap points (in place when they fit before the collision
    map, else relocated into the largest free run), collision map and surface table at the template's offsets."""
    e = course_table(rs)[template_course]
    h = e.header
    pb = decode_pointer_block(rs, e)
    bank = bytearray(rs.data[e.base:e.base + BANK_SIZE])
    if len(tables.lines) != LINES:
        raise BankError(f"{LINES} road lines are needed, got {len(tables.lines)}")
    n_pts = len(tables.lines[0])
    if any(len(l) != n_pts for l in tables.lines):
        raise BankError("all road lines must have the same number of points")
    if not (WRAP_POINTS <= n_pts <= 0xFFFF):
        raise BankError(f"{n_pts} road points (need {WRAP_POINTS}..65535)")
    n_seg = len(tables.segments)
    if not (1 <= n_seg <= 0xFFFE):
        raise BankError(f"{n_seg} segments")
    # 1. segment array: entry 0 = counts, entries 1..n; it must fit where the template's did (before the pointer block)
    seg_off = _win(e.base, h.seg_array, "seg array") - e.base
    ptr_off = _win(e.base, h.ptr_block, "pointer block") - e.base
    if seg_off + 8 * (n_seg + 1) > ptr_off:
        raise BankError(f"{n_seg} segments do not fit before the pointer block (room for {(ptr_off - seg_off) // 8 - 1})")
    seg_blob = struct.pack("<4H", n_pts, 0, n_seg, 0) + b"".join(encode_segment(s) for s in tables.segments)
    bank[seg_off:seg_off + len(seg_blob)] = seg_blob
    end_seg = seg_off + len(seg_blob)
    if ptr_off > end_seg:
        bank[end_seg:ptr_off] = b"\xff" * (ptr_off - end_seg)
    # 2. the eight lines, contiguous at one stride
    blobs = [encode_line(line) for line in tables.lines]
    stride = POINT_BYTES * (n_pts + WRAP_POINTS)
    total = stride * LINES
    old_first = min(_win(e.base, ptr, "line") for ptr, _ in pb.lines) - e.base
    old_total = POINT_BYTES * (pb.lines[0][1] + WRAP_POINTS) * LINES
    next_table = min(v - e.base for v in (_win(e.base, pb.collision, "c"), _win(e.base, pb.surface, "s"),
                                           _win(e.base, h.gfx_dir, "g")) if v - e.base > old_first)
    if old_first + total <= next_table:
        start = old_first
    else:
        bank[old_first:old_first + old_total] = b"\xff" * old_total          # no stale copy of the template's lines
        runs = _free_runs(bytes(bank), next_table)
        fit = [r for r in runs if r[1] >= total + 16]
        if not fit:
            raise BankError(f"road lines need {total} bytes; largest free run {runs[0][1] if runs else 0}")
        start = (fit[0][0] + 15) // 16 * 16
    for k, blob in enumerate(blobs):
        bank[start + stride * k:start + stride * k + len(blob)] = blob
    ptrs = tuple((WINDOW + start + stride * k, n_pts) for k in range(LINES))
    # 3. pointer block and header
    pb_blob = encode_pointer_block(PointerBlock(pb.collision, pb.surface, ptrs))
    bank[ptr_off:ptr_off + len(pb_blob)] = pb_blob
    centre_ptr = ptrs[0][0]
    new_h = BankHeader(h.gfx_dir, h.seg_array, h.ptr_block, h.ptr_block_b, h.ptr_block_c,
                       centre_ptr, centre_ptr, centre_ptr, n_pts, n_seg)
    bank[0:32] = encode_header(new_h)
    struct.pack_into("<H", bank, 0x20, n_pts)
    struct.pack_into("<H", bank, 0x24, n_seg)
    # 4. collision map and surface table at the template's offsets
    col_off = _win(e.base, pb.collision, "collision") - e.base
    bank[col_off:col_off + COLLISION_BYTES] = encode_collision_map(collision_cells)
    sur_off = _win(e.base, pb.surface, "surface") - e.base
    sur_room = (_win(e.base, h.gfx_dir, "g") - e.base) - sur_off
    if len(surface) > sur_room:
        raise BankError(f"surface table of {len(surface)} bytes exceeds the {sur_room} bytes before the graphics directory")
    bank[sur_off:sur_off + len(surface)] = surface
    return bytes(bank)


def install_bank(rs: RomSet, course_index: int, bank: bytes) -> RomSet:
    """A new RomSet with the course's bank replaced."""
    if len(bank) != BANK_SIZE:
        raise BankError(f"a bank is {BANK_SIZE} bytes, got {len(bank)}")
    e = course_table(rs)[course_index]
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    try:
        write_data(out, e.base, bank)
    except PatchError as exc:
        raise BankError(str(exc)) from exc
    return out
