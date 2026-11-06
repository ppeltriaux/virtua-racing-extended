"""Patch a RomSet with converted course data: polygon-ROM allocation, tile records, colour entries."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from vrtools.arcade.colours import TABLE_BASE, TABLE_ENTRIES, TILE_RECORD_ROM
from vrtools.arcade.course import PIT_ENTRY_TABLE, RECORD_SIZE, TILE_TABLE
from vrtools.arcade.polyrom import ObjectLayout
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet

# the erased (0xFF) tail of every 2 MB chip of the 16 MB polygon ROM, up to its chip boundary (bytes): unused padding
# (Phase 1 listed the two largest; Phase 18 takes all seven for the Saturn's scenery layers)
POLY_HOLES = [(0x2A7CA0, 0x158360), (0x5E440C, 0x1BBF4), (0x76F280, 0x90D80), (0x9D9290, 0x26D70), (0xBB2770, 0x4D890), (0xDEA914, 0x156EC), (0xEE2A9C, 0x11D564)]
POLY_ROM_WORDS = 0x400000


class PatchError(Exception):
    pass


@dataclass
class Allocator:
    holes: list[tuple[int, int]]                      # (start, size) free ranges, in address order
    used: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.free = sorted((s, s + n) for s, n in self.holes)
        for (s1, e1), (s2, e2) in zip(self.free, self.free[1:]):
            if s2 < e1:
                raise PatchError(f"free ranges overlap: {s1:#x}-{e1:#x} and {s2:#x}-{e2:#x}")

    def alloc(self, size: int, align: int = 4, window: int | None = None, unit: str = "units") -> int:
        """First fit, `align`ed; with `window` the range must not cross a multiple of `window` (the TGP reads ROM
        through 32K-word windows). The space skipped to reach a window boundary stays free."""
        if size <= 0:
            raise PatchError("allocation size must be positive")
        if window is not None and size > window:
            raise PatchError(f"{size} {unit} do not fit one window of {window}")
        for i, (s, e) in enumerate(self.free):
            start = (s + align - 1) // align * align
            if window is not None and start // window != (start + size - 1) // window:
                start = (start + size - 1) // window * window                  # the next window boundary
                start = (start + align - 1) // align * align
            if start + size <= e:
                if start > s:
                    self.free.insert(i, (s, start))                            # keep what was skipped
                    i += 1
                self.free[i] = (start + size, e)
                self.used.append((start, size))
                return start
        largest = max((e - s for s, e in self.free), default=0)
        raise PatchError(f"no free range for {size} {unit} (largest free {largest}): short by {size - largest}")


def poly_free_runs(rs: RomSet, min_bytes: int = 64) -> list[tuple[int, int]]:
    """(byte start, byte count) of the erased (0xFF) runs inside POLY_HOLES as the ROM stands, 4-byte aligned, so a
    second course's scenery lands after the first's."""
    runs = []
    poly = rs.polygons
    for start, size in POLY_HOLES:
        run = None
        for i in range(start, start + size + 1):
            erased = i < start + size and poly[i] == 0xFF
            if erased and run is None:
                run = i
            elif not erased and run is not None:
                a = (run + 3) // 4 * 4
                if i - a >= min_bytes:
                    runs.append((a, i - a))
                run = None
    return runs


def write_polygons(rs: RomSet, blob: bytes, byte_offset: int) -> int:
    """Write object bytes into polygon ROM at a 4-byte aligned byte offset; returns the word address.

    The target bytes must still be erased (0xFF): a second patch of the same hole is refused."""
    if byte_offset % 4 or byte_offset + len(blob) > len(rs.polygons):
        raise PatchError(f"polygon write at {byte_offset:#x} (+{len(blob)}) is misaligned or past the ROM")
    if any(b != 0xFF for b in rs.polygons[byte_offset:byte_offset + len(blob)]):
        raise PatchError(f"polygon space at {byte_offset:#x} (+{len(blob)}) is not free")
    poly = bytearray(rs.polygons)
    poly[byte_offset:byte_offset + len(blob)] = blob
    object.__setattr__(rs, "polygons", bytes(poly))
    return byte_offset // 4


TILE_TABLE_BYTES = 256 * 4 + 256 * RECORD_SIZE           # pointer table followed by its 256 records


def write_tile_table(rs: RomSet, address: int) -> None:
    """A new, empty tile table at program-ROM `address`: 256 pointers to 256 zero records right after it. The
    whole area must still be erased (0xff)."""
    off = address - V60_PROGRAM
    if not (0 <= off and off + TILE_TABLE_BYTES <= len(rs.program)) or address % 4:
        raise PatchError(f"tile table at {address:#x} is outside the program ROM or misaligned")
    if any(b != 0xFF for b in rs.program[off:off + TILE_TABLE_BYTES]):
        raise PatchError(f"program ROM at {address:#x} (+{TILE_TABLE_BYTES:#x}) is not free")
    prog = bytearray(rs.program)
    for cell in range(256):
        struct.pack_into("<I", prog, off + 4 * cell, address + 0x400 + RECORD_SIZE * cell)
    prog[off + 0x400:off + TILE_TABLE_BYTES] = bytes(256 * RECORD_SIZE)
    object.__setattr__(rs, "program", bytes(prog))


def write_program_blob(rs: RomSet, address: int, data: bytes) -> None:
    """Write `data` at program-ROM `address` (4-aligned); the area must still be erased (0xff)."""
    off = address - V60_PROGRAM
    if not (0 <= off and off + len(data) <= len(rs.program)) or address % 4:
        raise PatchError(f"blob at {address:#x} is outside the program ROM or misaligned")
    if any(b != 0xFF for b in rs.program[off:off + len(data)]):
        raise PatchError(f"program ROM at {address:#x} (+{len(data):#x}) is not free")
    prog = bytearray(rs.program)
    prog[off:off + len(data)] = data
    object.__setattr__(rs, "program", bytes(prog))


def write_tile_record(rs: RomSet, course_index: int, cell: int, poly_adr: int, tex_adr: int, size: int,
                      table: int | None = None) -> None:
    if poly_adr & 0x800000 or poly_adr >= POLY_ROM_WORDS or not (0 <= size < 0x10000):
        raise PatchError(f"cell {cell}: bad record (poly {poly_adr:#x}, size {size})")
    if not (0 <= tex_adr < TABLE_BASE + TABLE_ENTRIES):
        raise PatchError(f"cell {cell}: tex_adr {tex_adr:#x} out of range")
    tbl = TILE_TABLE[course_index] if table is None else table
    ptr = struct.unpack_from("<I", rs.read_v60(tbl + 4 * cell, 4))[0]
    off = ptr - V60_PROGRAM
    if not (0 <= off <= len(rs.program) - RECORD_SIZE):
        raise PatchError(f"cell {cell}: record pointer {ptr:#x} is not in program ROM")
    prog = bytearray(rs.program)
    struct.pack_into("<4I", prog, off, poly_adr, tex_adr, size, 0)
    object.__setattr__(rs, "program", bytes(prog))


def write_colour_entries(rs: RomSet, words: dict[int, int]) -> None:
    """Write colour-table entries; each target must be an unused (0xFFFF) entry below the tile records."""
    prog = bytearray(rs.program)
    for tex, w in words.items():
        if not (TABLE_BASE <= tex < TABLE_BASE + TILE_RECORD_ROM // 2):
            raise PatchError(f"colour entry {tex:#x} is outside the usable table")
        if not (0 <= w < 0x10000):
            raise PatchError(f"colour entry {tex:#x}: word {w:#x} does not fit u16")
        off = 2 * (tex - TABLE_BASE)
        if struct.unpack_from("<H", prog, off)[0] != 0xFFFF:
            raise PatchError(f"colour entry {tex:#x} is in use")
        struct.pack_into("<H", prog, off, w)
    object.__setattr__(rs, "program", bytes(prog))


def patch_course_tiles(rs: RomSet, course_index: int, cell_objects: dict[int, tuple[bytes, ObjectLayout, int]],
                       colour_words: dict[int, int], holes: list[tuple[int, int]] | None = None,
                       tile_table: int | None = None) -> RomSet:
    """Return a new RomSet whose course tile grid points at the given objects.

    cell_objects: cell -> (object bytes, layout, tex_start). Cells not listed become empty records.
    Every tex_adr an object reads (layout.tex_first..tex_last, starting at its record's tex_start) must be
    in colour_words; polygon space and colour entries must still be erased in `rs`. `tile_table` names a
    table written by write_tile_table instead of the original course's."""
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    alloc = Allocator(holes if holes is not None else poly_free_runs(rs))     # erased space left by earlier courses
    write_colour_entries(out, colour_words)
    for cell in range(256):
        if cell in cell_objects:
            blob, layout, tex_start = cell_objects[cell]
            if tex_start != layout.tex_first:
                raise PatchError(f"cell {cell}: record tex_start {tex_start:#x} != object tex_first {layout.tex_first:#x}")
            missing = [t for t in range(layout.tex_first, layout.tex_last + 1) if t not in colour_words]
            if missing:
                raise PatchError(f"cell {cell}: tex entries {missing[0]:#x}.. read by the object are not written")
            at = alloc.alloc(len(blob), align=4, unit="bytes")
            word = write_polygons(out, blob, at)
            write_tile_record(out, course_index, cell, word, tex_start, layout.record_count, table=tile_table)
        else:
            write_tile_record(out, course_index, cell, 0, 0, 0, table=tile_table)
    return out


# --- TGP (copro) data ROM -----------------------------------------------------------------------------------------

from vrtools.arcade.course import (COLLISION_CELLS, collision_map, course_table, decode_pointer_block,  # noqa: E402
                                   encode_collision_map, _win)
from vrtools.arcade.tgp import (FREE_WORD, QUAD_WORDS, SLOT_LIST, SLOT_OF_COURSE, SLOT_POOL, SLOTS, Collision,  # noqa: E402
                                encode_lists, encode_quads, slot_table)

COPRO_FREE = [(0x4B170, 0x80000 - 0x4B170)]                      # (word start, word count) of 0xffffffff words
COPRO_ZERO_GAPS = [(0x3FA1, 0x8000 - 0x3FA1), (0xB547, 0x10000 - 0xB547)]
ORIGINAL_SLOTS = (0, 1, 2)
DEFAULT_SLOT = (0x30, 0x12E00)                                   # unused slots hold Bay Bridge's addresses
MAX_BLOCK_WORDS = 0x10000                                        # collision-map ids are halfwords
TGP_WINDOW = 0x8000                                              # words: the TGP's ROM window (base & ~0x7fff | 15-bit index)


def copro_free_runs(rs: RomSet, min_words: int = 16) -> list[tuple[int, int]]:
    """(word start, word count) of the blank runs the TGP allocator may use: 0xffffffff words in the free tail and
    zero words in the fillers between the originals' list blocks, as the ROM stands (earlier installs excluded)."""
    runs = []
    for ranges, blank in ((COPRO_ZERO_GAPS, 0), (COPRO_FREE, FREE_WORD)):
        for start, count in ranges:
            words = struct.unpack_from(f"<{count}I", rs.copro_data, 4 * start)
            run = None
            for i, w in enumerate(words + (None,)):
                if w == blank and run is None:
                    run = i
                elif w != blank and run is not None:
                    if i - run >= min_words:
                        runs.append((start + run, i - run))
                    run = None
    return sorted(runs)


def write_copro_words(rs: RomSet, word_offset: int, blob: bytes, allow_zero: bool = False) -> None:
    """Write bytes at a word offset of the TGP data ROM; every target word must still be 0xffffffff (or 0)."""
    if len(blob) % 4:
        raise PatchError("copro write is not whole words")
    n = len(blob) // 4
    if not (0 <= word_offset and word_offset + n <= len(rs.copro_data) // 4):
        raise PatchError(f"copro write at word {word_offset:#x} (+{n}) is past the ROM")
    old = struct.unpack_from(f"<{n}I", rs.copro_data, 4 * word_offset)
    for i, w in enumerate(old):
        at = word_offset + i
        in_gap = any(g0 <= at < g0 + gn for g0, gn in COPRO_ZERO_GAPS)
        if w != FREE_WORD and not (allow_zero and w == 0 and in_gap):
            raise PatchError(f"copro word {at:#x} is not free ({w:#x})")
    data = bytearray(rs.copro_data)
    data[4 * word_offset:4 * word_offset + len(blob)] = blob
    object.__setattr__(rs, "copro_data", bytes(data))


def write_slot(rs: RomSet, slot: int, list_block: int, pool: int, force: bool = False) -> None:
    """Point a slot of the TGP course table at a list block and a quad pool (word addresses)."""
    if not (0 <= slot < SLOTS):
        raise PatchError(f"slot {slot} is not 0..15")
    if slot in ORIGINAL_SLOTS and not force:
        raise PatchError(f"slot {slot} belongs to an original course (force=True to repoint it)")
    if slot not in ORIGINAL_SLOTS and not force and slot_table(rs)[slot] != DEFAULT_SLOT:
        raise PatchError(f"slot {slot} is already in use ({slot_table(rs)[slot]}); force=True to repoint it")
    words = len(rs.copro_data) // 4
    if not (0 <= list_block < words and 0 <= pool < words):
        raise PatchError("slot addresses must be inside the data ROM")
    data = bytearray(rs.copro_data)
    struct.pack_into("<I", data, 4 * (SLOT_LIST + slot), list_block)
    struct.pack_into("<I", data, 4 * (SLOT_POOL + slot), pool)
    object.__setattr__(rs, "copro_data", bytes(data))


def write_data(rs: RomSet, byte_offset: int, blob: bytes) -> None:
    """Overwrite bytes of the V60 data ROM (course banks); bounds-checked, no free check (tables are rewritten)."""
    if not (0 <= byte_offset and byte_offset + len(blob) <= len(rs.data)):
        raise PatchError(f"data write at {byte_offset:#x} (+{len(blob)}) is past the ROM")
    data = bytearray(rs.data)
    data[byte_offset:byte_offset + len(blob)] = blob
    object.__setattr__(rs, "data", bytes(data))


def write_boot(rs: RomSet, byte_offset: int, blob: bytes) -> None:
    """Overwrite bytes of the V60 boot ROM (0xfc0000); bounds-checked."""
    if not (0 <= byte_offset and byte_offset + len(blob) <= len(rs.boot)):
        raise PatchError(f"boot write at {byte_offset:#x} (+{len(blob)}) is past the ROM")
    boot = bytearray(rs.boot)
    boot[byte_offset:byte_offset + len(blob)] = blob
    object.__setattr__(rs, "boot", bytes(boot))


def patch_pit_entry(rs: RomSet, slot: int, quad: int | None) -> RomSet:
    """A new RomSet whose course-data `slot` enters the pit sequence at lap-position quad `quad` (or quad + 1);
    None disables the pit lane for the slot, as the original does for Bay Bridge (course.pit_entry_table)."""
    if slot not in ORIGINAL_SLOTS:
        raise PatchError(f"slot {slot} is not one of {ORIGINAL_SLOTS}")
    if quad is not None and not (0 <= quad < 0xFFFF):
        raise PatchError(f"pit entry quad {quad} is not a quad index below 0xffff")
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    write_boot(out, PIT_ENTRY_TABLE - V60_BOOT + 2 * slot, struct.pack("<H", 0xFFFF if quad is None else quad))
    return out


def install_collision(rs: RomSet, collision: Collision, slot: int, holes: list[tuple[int, int]] | None = None,
                      force: bool = False, cell_offsets: dict[int, int] | None = None,
                      strict: bool = True) -> tuple[RomSet, list[int]]:
    """Write the collision's lists and quads into free TGP ROM and point `slot` at them; return the new RomSet
    and the 128 × 128 collision-map values (cell -> list offset) for the course's bank or blob to carry.
    No data bank is touched (patch_collision does that for an original course)."""
    collision.check()
    if not collision.lists:
        raise PatchError("collision has no lists")
    if cell_offsets is None:
        raise PatchError("install_collision needs cell_offsets (cell -> list offset)")
    first = next(iter(collision.lists))
    block_words = first + collision.list_words
    if block_words > MAX_BLOCK_WORDS:
        raise PatchError(f"list block of {block_words} words exceeds 0xffff (collision-map ids are halfwords)")
    cells = [0] * COLLISION_CELLS
    for cell, off in cell_offsets.items():
        if not (0 <= cell < COLLISION_CELLS):
            raise PatchError(f"cell {cell} is outside the 128x128 map")
        if off == 0:
            raise PatchError(f"cell {cell}: list offset 0 means off-road; lists must start at offset 1")
        if off not in collision.lists:
            raise PatchError(f"cell {cell}: no list at offset {off:#x}")
        cells[cell] = off
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    alloc = Allocator(holes if holes is not None else copro_free_runs(rs))   # what is still blank: the zero fillers
    lists = encode_lists(collision.lists)                                      # between the originals' blocks and the tail
    quads = encode_quads(collision.quads, strict=strict)
    # the TGP sets its ROM window from a list's or a quad's own address and walks on with a 15-bit index: a list
    # (count + entries) or a 16-word quad crossing a multiple of 0x8000 words would read I/O space instead. The
    # whole block stays inside one window; the pool is quad-aligned (0x8000 is a multiple of 16)
    block = alloc.alloc(block_words, align=4, window=TGP_WINDOW, unit="words")
    pool = alloc.alloc(len(quads) // 4, align=QUAD_WORDS, unit="words")
    write_copro_words(out, block + first, lists, allow_zero=True)
    if first > 0:
        # the TGP reads the count at block + id for every id, including 0 (off-road): the originals keep an
        # empty list (count 0) at offset 0, and an erased word there would make the quad loop run forever
        write_copro_words(out, block, bytes(4 * first), allow_zero=True)
    write_copro_words(out, pool, quads, allow_zero=True)
    write_slot(out, slot, block, pool, force=force)
    return out, cells


def patch_collision(rs: RomSet, course_index: int, collision: Collision, slot: int,
                    holes: list[tuple[int, int]] | None = None, force: bool = False,
                    cell_offsets: dict[int, int] | None = None, strict: bool = True) -> RomSet:
    """Return a new RomSet with the collision's lists and quads in free TGP ROM, the slot pointed at them, and the
    course bank's collision map carrying the list offsets.

    Without cell_offsets the existing map is kept where its value names a list in `collision.lists` and zeroed
    elsewhere (a relocation). With cell_offsets (cell -> list offset) the map is rebuilt from scratch."""
    if slot != SLOT_OF_COURSE.get(course_index):
        raise PatchError(f"course {course_index} loads TGP slot {SLOT_OF_COURSE.get(course_index)}, not {slot} "
                         "(the slot is the course's data index)")
    entry = course_table(rs)[course_index]
    if cell_offsets is None:
        old = collision_map(rs, entry)
        cell_offsets = {cell: v for cell, v in enumerate(old) if v in collision.lists and v != 0}
    out, cells = install_collision(rs, collision, slot, holes=holes, force=force, cell_offsets=cell_offsets, strict=strict)
    pb = decode_pointer_block(out, entry)
    write_data(out, _win(entry.base, pb.collision, "collision map pointer"), encode_collision_map(cells))
    if collision.surface is not None:
        # one byte per quad, read by the V60 as [surface_table](quad index); the original tables are exactly as
        # long as their quad pools, so a shorter table fits where the template's was
        write_data(out, _win(entry.base, pb.surface, "surface table pointer"), collision.surface)
    return out
