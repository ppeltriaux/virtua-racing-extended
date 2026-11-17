"""Phase 31 (prototype): install the cells that carry a far landmark's silhouette (convert/silhouette.py).

Written after everything else in the set, on erased ROM only, so that no other object, colour entry or table moves: each
changed cell gets a NEW polygon-ROM object (its own quads and the copies) and its tile record is repointed; the cell's old
object stays where it was, unread. The new objects' colour entries go in a block of the program ROM the caller reserves for
them (the whole program ROM is the colour table: colours.py); they are never placed by searching for erased bytes."""

from __future__ import annotations

import struct

from vrtools.arcade.colours import TABLE_BASE, palette_from_rom
from vrtools.arcade.course import tile_table_at
from vrtools.arcade.patch import Allocator, PatchError, poly_free_runs, write_colour_entries, write_polygons, write_tile_record
from vrtools.arcade.polyrom import MAX_RECORDS, ConvertError as EncodeError, encode_object
from vrtools.arcade.romset import V60_PROGRAM, RomSet

def colour_run(rs: RomSet, block: tuple[int, int], entries: int) -> int:
    """The first colour-table entry (tex address) for `entries` new entries in the program-ROM block [start, end) the caller
    reserves for the far copies' colours: the entry after the last one in use in the block (a word other than 0xffff; a colour
    entry is a palette index, never 0xffff), so a second course's entries follow the first's. The ROM is never searched for
    erased bytes: outside the block nothing is taken. PatchError when the block is misaligned or has not the room."""
    lo, hi = block
    if lo % 2 or hi % 2 or not (V60_PROGRAM <= lo <= hi <= V60_PROGRAM + len(rs.program)):
        raise PatchError(f"the far copies' colour block {lo:#x}..{hi:#x} is misaligned or outside the program ROM")
    words = struct.unpack_from(f"<{(hi - lo) // 2}H", rs.program, lo - V60_PROGRAM)
    used = max((k + 1 for k, w in enumerate(words) if w != 0xFFFF), default=0)
    if used + entries > len(words):
        raise PatchError(f"the far copies' colour block {lo:#x}..{hi:#x} has room for {len(words) - used} more entries, "
                         f"{entries} needed")
    return TABLE_BASE + (lo - V60_PROGRAM) // 2 + used


def install_far_copies(rs: RomSet, tile_table: int, palette_course: int, far_cells: dict, colour_block: tuple[int, int],
                       max_records: int = MAX_RECORDS) -> tuple[RomSet, dict]:
    """A new RomSet in which each cell of `far_cells` ({cell: WorldQuads}, silhouette.far_copy_cells) of the tile table at
    `tile_table` draws a new object made of those quads, coloured from the palette of `palette_course` as the converter colours
    every cell (geometry.assign_colours). Writes, all on erased ROM: the objects (first fit in the polygon ROM's free runs as
    they stand), their colour entries (in `colour_block`, the block reserved for them: `colour_run`), and the cells' tile records
    (repointed). Returns the set
    and a report: "cells" {cell: records, records_before, bytes, colour_entries}, "polygon_bytes", "colour_entries",
    "colour_first", "added_records". PatchError when an object passes `max_records`, or the room is missing."""
    from vrtools.convert.geometry import assign_colours
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    report = {"cells": {}, "polygon_bytes": 0, "colour_entries": 0, "colour_first": None, "added_records": 0}
    if not far_cells:
        return out, report
    pal = palette_from_rom(rs, palette_course)
    entries = sum(len(assign_colours(q, pal, tex_start=TABLE_BASE)[1]) for q in far_cells.values())
    tex = report["colour_first"] = colour_run(rs, colour_block, entries)
    before = tile_table_at(rs, tile_table)
    alloc = Allocator(poly_free_runs(rs))
    for cell, quads in sorted(far_cells.items()):
        coloured, words = assign_colours(quads, pal, tex_start=tex)
        try:
            blob, layout = encode_object(coloured, tex_start=tex, no_cull=True, max_records=max_records)
        except EncodeError as e:                                      # too many records for one object
            raise PatchError(f"far copies, cell {cell}: {e}") from e
        write_colour_entries(out, words)
        word = write_polygons(out, blob, alloc.alloc(len(blob), align=4, unit="bytes"))
        write_tile_record(out, 0, cell, word, tex, layout.record_count, table=tile_table)
        report["cells"][cell] = {"records": layout.record_count, "records_before": before[cell].size, "bytes": len(blob),
                                 "colour_entries": len(words)}
        report["polygon_bytes"] += len(blob)
        report["colour_entries"] += len(words)
        report["added_records"] += layout.record_count - before[cell].size
        tex += len(words)
    return out, report
