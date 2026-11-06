"""Relocatable course blobs: a course's tables laid out for any window address inside a data bank (Phase 7).

An original course has its header at the bank window's base (0x100000); the ten-course directory lets the loader
read a header anywhere in the mapped bank, so a converted course can live in the free space of banks 1–3 next
to the host course, whose graphics directory (backdrop, palette) it inherits. Layout from the blob's base:
header (0x20) · segment array (+0x20, entry 0 = counts) · pointer block · eight road lines with wrap points ·
collision map (128 × 128 halfwords) · surface table (one byte per collision quad).
"""
from __future__ import annotations

from typing import Callable

from vrtools.arcade.bank import LINES, POINT_BYTES, WRAP_POINTS, BankError, encode_line
from vrtools.arcade.course import (BANK_SIZE, COURSE_BANK, WINDOW, BankHeader, PointerBlock, course_entry_at, encode_collision_map,
                                   encode_header, encode_pointer_block, encode_segment)
from vrtools.arcade.patch import PatchError, write_data
from vrtools.arcade.romset import RomSet
from vrtools.convert.road import RoadTables

COLLISION_BYTES = 128 * 128 * 2
MIN_FREE_RUN = 0x8000


def _align(n: int, a: int = 16) -> int:
    return (n + a - 1) // a * a


def build_course_blob(rs: RomSet, host_course: int, tables: RoadTables, collision_cells: list[int], surface: bytes,
                      window_base: int, gfx_dir: int | None = None) -> bytes:
    """The course's tables as one image to be placed at `window_base` of the host course's bank; every pointer
    is a window address. The graphics directory pointer is `gfx_dir` (Phase 18b: the course's own backdrop) or, without
    one, the host bank's own (backdrop and palette inherited)."""
    if not (WINDOW <= window_base < WINDOW + BANK_SIZE) or window_base % 16:
        raise BankError(f"window base {window_base:#x} is not a 16-aligned window address")
    host = course_entry_at(rs, COURSE_BANK[host_course])                         # menu index -> bank (BF 3, BB 1, AC 2)
    if len(tables.lines) != LINES or any(len(l) != len(tables.lines[0]) for l in tables.lines):
        raise BankError(f"{LINES} road lines of equal length are needed")
    n_pts, n_seg = len(tables.lines[0]), len(tables.segments)
    if not (WRAP_POINTS <= n_pts <= 0xFFFF) or not (1 <= n_seg <= 0xFFFE):
        raise BankError(f"{n_pts} road points / {n_seg} segments")
    if len(collision_cells) != 128 * 128:
        raise BankError("the collision map has 128 × 128 cells")
    import struct
    seg_off = 0x20
    seg_blob = struct.pack("<4H", n_pts, 0, n_seg, 0) + b"".join(encode_segment(s) for s in tables.segments)
    ptr_off = _align(seg_off + len(seg_blob))
    line_off = _align(ptr_off + 8 + 8 * LINES)
    stride = POINT_BYTES * (n_pts + WRAP_POINTS)
    col_off = _align(line_off + stride * LINES)
    sur_off = col_off + COLLISION_BYTES
    end = _align(sur_off + len(surface))
    if window_base - WINDOW + end > BANK_SIZE:
        raise BankError(f"a {end} byte course at {window_base:#x} runs past the bank")
    w = lambda off: window_base + off
    lines_ptrs = tuple((w(line_off + stride * k), n_pts) for k in range(LINES))
    header = BankHeader(host.header.gfx_dir if gfx_dir is None else gfx_dir, w(seg_off), w(ptr_off), w(ptr_off + 4), w(ptr_off + 8),
                        lines_ptrs[0][0], lines_ptrs[0][0], lines_ptrs[0][0], n_pts, n_seg)
    blob = bytearray(b"\xff" * end)
    blob[0:0x20] = encode_header(header)
    blob[seg_off:seg_off + len(seg_blob)] = seg_blob
    pb = encode_pointer_block(PointerBlock(w(col_off), w(sur_off), lines_ptrs))
    blob[ptr_off:ptr_off + len(pb)] = pb
    for k, line in enumerate(tables.lines):
        enc = encode_line(line)
        blob[line_off + stride * k:line_off + stride * k + len(enc)] = enc
    blob[col_off:col_off + COLLISION_BYTES] = encode_collision_map(collision_cells)
    blob[sur_off:sur_off + len(surface)] = surface
    return bytes(blob)


def free_runs(rs: RomSet, bank: int, min_size: int = MIN_FREE_RUN) -> list[tuple[int, int]]:
    """(bank offset, size) of the 0xff runs of at least `min_size` bytes in data bank `bank`, in address order."""
    if not (0 <= bank < len(rs.data) // BANK_SIZE):
        raise PatchError(f"bank {bank} is not in the data ROM")
    data = rs.data
    start, end = bank * BANK_SIZE, (bank + 1) * BANK_SIZE
    out = []
    i = start
    while i < end:
        if data[i] == 0xFF:
            j = i
            while j < end and data[j] == 0xFF:
                j += 1
            if j - i >= min_size:
                out.append((i - start, j - i))
            i = j
        else:
            i += 1
    return out


def place_blob(rs: RomSet, bank: int, build: Callable[[int], bytes]) -> tuple[RomSet, int]:
    """First-fit placement of a course blob in `bank`'s free space: `build(window_base)` returns the image for a
    candidate base (its pointers depend on it). Returns the new RomSet and the window base; PatchError when no
    run fits or the target is not all 0xff."""
    size = len(build(WINDOW))
    for off, n in free_runs(rs, bank):
        base = _align(off)
        if base + size <= off + n:
            blob = build(WINDOW + base)
            if len(blob) != size:
                raise PatchError("the blob's size depends on its base")
            abs_off = bank * BANK_SIZE + base
            if any(b != 0xFF for b in rs.data[abs_off:abs_off + size]):
                raise PatchError(f"bank {bank} +{base:#x} is not free")
            out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
            write_data(out, abs_off, blob)
            return out, WINDOW + base
    raise PatchError(f"no free run of {size} bytes in bank {bank} (runs: {[(hex(o), n // 1024) for o, n in free_runs(rs, bank)]})")
