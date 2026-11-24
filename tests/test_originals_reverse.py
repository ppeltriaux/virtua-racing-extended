"""Phase 33 (a prototype): Big Forest, Bay Bridge and Acropolis in reverse, from their own arcade tables.

The build tests compare the session's set (`_seven`: the originals with their reverse variants) with the same set built without
them (`_seven_plain`, `ten_course_set(originals_reverse=False)`: the set as before Phase 33) and with the tables the ROM holds.
The MAME tests race each original in reverse and check what the phase promises: the race itself, the HUD's level word, and that a normal race on any of the ten courses is the plain set's race pass for pass.

Stage 2. Pascal, 16 Nov, after two runs of the stage 1 set: "reverse on original track is good but: - some checkpoint flags are
white without the C.P. the pit isnt working. relaunch"; after a third: "reverse is not showing in the reverse track during
gameplay, relaunch". So: the checkpoint gantries read C.P. from behind in reverse (their lettering mirrored behind the banner),
a reverse race on Big Forest and on Acropolis has a working pit stop (Bay Bridge has no pit lane), and the word REVERSE stands
under the level word in a reverse race (Phase 32's word, printed by `hudorig`).

Phase 35: a reverse race on an original keeps its best times (ranking.py; tests/test_reverse_times.py), so `rankgate3` and its
test that such a race records nothing are gone; the block holds `hudorig` alone."""
import struct

import numpy as np
import pytest

from vrtools.arcade.bank import POINT_BYTES, WRAP_POINTS
from vrtools.arcade.course import BANK_SIZE, DIRECTION_RAM, WINDOW, course_entry_at, decode_pointer_block, road_lines, segments
from vrtools.arcade.directory import LOAD_FIELDS, LOAD_SIZE, ORIGINALS, decode_directory, directory_layout, maps_offset
from vrtools.arcade.hudname import HUD_SITE
from vrtools.arcade.origrev import (BLOCK_BYTES, RANK_PATTERN, RANK_SITE, install_origrev, origrev_layout, origrev_routines)
from vrtools.arcade.patch import PatchError
from vrtools.arcade.race import RACE_BLOB_BYTES, checkpoints as checkpoints_at, decode_race_blob, time_record
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.arcade.tencourse import (MAP_CROSS_SHIFTED, MAP_TX_SHIFTED, ORIGINAL_REVERSE_GRID, ORIGINAL_REVERSE_PAIRS, annex_regions, origrev_address,
                                      picture_exclusions, start_gantry_address)
from vrtools.convert.race import lap_total
from vrtools.convert.reverse import reverse_original
from tests.test_tencourse import BANK_ONE_FLOOR
from tests.test_tgp_build import _seven, _seven_plain

NAMES = {0: "BIG FOREST", 1: "BAY BRIDGE", 2: "ACROPOLIS"}
POINTS = {0: 338, 1: 418, 2: 592}                       # road points (recon §3)
REVERSE_CHECKPOINTS = {0: (0, 108, 218), 1: (0, 197, 306), 2: (0, 169, 382)}     # the game's (0, 120, 230), (0, 112, 221), (0, 210, 423)
STORED_LINES = {0: 6, 1: 1, 2: 8}                       # Bay Bridge: one line, a stopgap (bank 1's room); Big Forest: BIG_FOREST_REVERSE_PAIRS
BLOB_BYTES = {0: 42_080, 1: 12_336, 2: 84_496}
EXTENSION = {0: 331, 1: 331, 2: 457}                    # the game's extension at every checkpoint, level 0, single play (1/32 s)
GRID = {0: (0, 1, 3, 2, 4, 5, 7, 6, 8, 9, 11, 13, 15, 10, 12, 14),      # the measured grids (findings §5), pinned
        1: tuple(range(0, 32, 2)), 2: tuple(range(0, 32, 2))}
ANNEX_SHIFT = 3 * LOAD_SIZE                             # the seven's race blobs move up by the three more maps records
USED_BYTES = 96                                         # of the block's 160: `hudorig` (Phase 33's `rankgate3`, 50, gone in Phase 35)
WORD_LAST = {0: 58, 1: 57, 2: 57}                       # the column of REVERSE's last letter: under the R of BEGINNER, the M of
                                                        # " MEDIUM ", the T of " EXPERT " (the level word is on columns 51-58)
PIT_QUAD = {0: 58, 1: None, 2: 54}                      # the reverse pit quad: the last but one of the lane's quads (30-59, 28-55)
PIT_BOX = {0: (-230.38, 30.0, -269.57), 2: (-346.42, 3.70, -58.96)}      # the game's own boxes (0xff40d9, 0xff40b1)


def _span(rs, rv):
    """[start, end) in the data ROM of a variant's blob (header to the end of its last stored line, 16-aligned)."""
    lines = decode_pointer_block(rs, course_entry_at(rs, rv.bank, rv.header_base)).lines
    end = max(p for p, _ in lines) + POINT_BYTES * (lines[0][1] + WRAP_POINTS)
    start = rv.bank * BANK_SIZE + rv.header_base - WINDOW
    return start, rv.bank * BANK_SIZE + (end + 15) // 16 * 16 - WINDOW


# ---- the two routines (no ROM) ----

def test_the_blocks_routine():
    """`hudorig` fits the block (Phase 35: alone, at its start; `rankgate3` is gone); it is compares, branches, two calls, a
    jump and a return: its size is pinned so that a change is seen."""
    code = origrev_routines(0x28F910, 0x27B300, 0x27B3F0)
    assert list(code) == ["hudorig"] and [len(c) for c in code.values()] == [96]
    assert sum(len(c) for c in code.values()) == USED_BYTES <= BLOCK_BYTES
    lay = origrev_layout(0x28F910)
    assert lay == {"hudorig": 0x28F910, "end": 0x28F910 + USED_BYTES}
    assert code["hudorig"][-6:] == bytes.fromhex("d6f3") + (0x27B300).to_bytes(4, "little")   # jmp hudname
    hud = code["hudorig"]
    printer = (0xFF8926).to_bytes(4, "little")
    assert hud.count(printer) == 2 and bytes.fromhex("d6f3") + printer not in hud             # the printer called twice (the game's
                                                                                              # word, then REVERSE), never jumped to
    assert hud.count((0x27B3F0).to_bytes(4, "little")) == 1                                   # Phase 32's text, by its address
    assert hud.count((0x501434).to_bytes(4, "little")) == 3                                   # the colour cell: read, set, written back
    assert hud[-7] == 0xCA                                                                    # rsr before `name: jmp hudname`


def test_reverse_stands_under_the_level_words_last_letter():
    """Where `hudorig` prints REVERSE: Phase 32's step from one past the word's 8th cell (two rows down, seven cells back) on
    Big Forest, whose BEGINNER fills the eight cells; one cell further left on Bay Bridge and Acropolis, whose " MEDIUM " and
    " EXPERT " end in a space, so that the word's last letter stands under the M and the T (the right-alignment to the visible
    letters the lead asked for if cheap: one compare, one branch, one subtract)."""
    from vrtools.arcade.hudname import REVERSE_STEP, REVERSE_TEXT
    from vrtools.arcade.origrev import PADDED_FROM
    from tests.test_hudname_build import GAME_WORDS
    assert REVERSE_STEP == 0x100 - 2 * len(REVERSE_TEXT) and PADDED_FROM == 1
    for entry, (word, _) in GAME_WORDS.items():
        assert len(word) == 8 and word.endswith(" ") == (entry >= PADDED_FROM), word
        assert WORD_LAST[entry] == 51 + len(word.rstrip()) - 1, word
    assert WORD_LAST == {0: 58, 1: 57, 2: 57}


def test_the_block_is_reserved_below_the_far_copies_colour_block():
    """The block's 160 bytes (96 used: `hudorig`; 146 from stage 2 to Phase 35, which removed `rankgate3`) lie
    right below Phase 31's colour block, which lies right below the start gantry's; the annex's code-area region ends at them
    and the select pictures' search leaves them out."""
    from vrtools.arcade.tencourse import far_colour_block
    at = origrev_address()
    assert BLOCK_BYTES == 160 and at % 16 == 0 and at + BLOCK_BYTES == far_colour_block()[0]
    assert far_colour_block()[1] == start_gantry_address()
    from vrtools.arcade.origpic import BLOCK_BYTES as PICTURE_BYTES
    from vrtools.arcade.tencourse import origpic_address
    assert annex_regions()[0][1] == origpic_address() == at - PICTURE_BYTES          # fix wave: the picture block right below it
    assert (origpic_address(), PICTURE_BYTES + BLOCK_BYTES) in picture_exclusions()


def test_no_two_reserved_blocks_of_the_program_rom_overlap(monkeypatch):
    """`reserved_blocks` names every reservation the first-fit writers are kept out of (the directory image, the originals'
    reverse block, the originals' picture block (fix wave), the far copies' colour block, the start gantry's block, the direction
    screen's block, the reverse spawn lists' run); none overlaps another, each of the code area's three is inside it, and `check_reserved_blocks` (run by
    `ten_course_set` before the originals' block is written) refuses a layout in which two do, naming both."""
    import vrtools.arcade.tencourse as T
    from vrtools.arcade.course import CODE_FREE
    blocks = T.reserved_blocks()
    assert len(blocks) == 7
    spans = sorted(blocks.values())
    assert all(a[0] < a[1] for a in spans) and all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), blocks
    for name in ("originals' reverse block", "originals' picture block", "far copies' colour block", "start gantry's block"):
        lo, hi = blocks[name]
        assert blocks["directory image"][1] <= lo and hi <= CODE_FREE[0] + CODE_FREE[1], name
    T.check_reserved_blocks()
    flo, fhi = T.far_colour_block()
    monkeypatch.setattr(T, "origrev_address", lambda code_base=None: flo + 16)       # where it was before the rebase: inside Phase 31's
    with pytest.raises(PatchError, match="far copies' colour block"):
        T.check_reserved_blocks()


def test_the_interleaved_grid_keeps_one_lines_cars_apart():
    """`interleaved_grid`: cars 1..15 on points 1..15, no two neighbours on one stored line, the first such arrangement in the
    game's order; Big Forest's reverse grid is the one measured; one line for all cars has none."""
    from vrtools.arcade.tencourse import BIG_FOREST_REVERSE_PAIRS, GAME_CAR_LINES, interleaved_grid
    for pairs in (BIG_FOREST_REVERSE_PAIRS, tuple(range(8)), (0, 7, 7, 5, 5, 5, 5, 7)):
        stored = tuple(pairs[l] for l in GAME_CAR_LINES)
        g = interleaved_grid(stored)
        assert g[0] == 0 and sorted(g[1:]) == list(range(1, 16))
        at = {g[c]: stored[c] for c in range(1, 16)}
        assert all(at[p] != at[p + 1] for p in range(1, 15)), (pairs, g)
    assert interleaved_grid(tuple(BIG_FOREST_REVERSE_PAIRS[l] for l in GAME_CAR_LINES)) == GRID[0] == ORIGINAL_REVERSE_GRID[0]
    assert interleaved_grid(tuple(range(8)[l] for l in GAME_CAR_LINES))[1:5] == (1, 3, 2, 4)
    with pytest.raises(PatchError, match="apart"):
        interleaved_grid((0,) * 16)


# ---- the build ----

def test_each_original_has_a_reverse_record(romset_zip, saturn_cue):
    """Entries 0-2 carry a variant: the entry's bank, TGP slot, template, tile table, music, laps, name, label and
    off-course limit; its own header in the entry's bank and its own race blob in the annex after the seven's; the HUD map
    where the game draws it (shifted as the seven's reversed laps are, the originals' own outlines left the screen: findings
    §6). Stage 2: Big Forest's and Acropolis's variants carry a pit quad (PIT_QUAD: the lane's last quad but one in lap order,
    the first pair a reverse car meets, more than ORIGINAL_PIT_MIN_RUN from the box) and the game's own box with the heading
    turned half a turn (0x8000: both lanes run along +z); Bay Bridge, which has no pit lane, neither."""
    out, _ = _seven(romset_zip, saturn_cue)
    d = decode_directory(out)
    seven_end = max(e.reverse.entry.race for e in d[3:10]) + RACE_BLOB_BYTES
    for k in range(3):
        n, rv = d[k], d[k].reverse.entry
        assert n.name == NAMES[k] and (n.race, n.header_base, n.pit_box, n.map_tx, n.map_cross) == (0, 0x100000, None, 149.0, 0)
        assert n.pit_quad == ORIGINALS[k].pit_quad
        for f in ("bank", "tgp_slot", "template", "tile_table", "music", "laps", "name", "label", "off_course", "map_obj",
                  "panel_b", "art"):
            assert getattr(rv, f) == getattr(n, f), (n.name, f)
        assert rv.pit_quad == PIT_QUAD[k], (n.name, rv.pit_quad)
        if PIT_QUAD[k] is None:
            assert rv.pit_box is None and n.pit_quad is None
        else:
            from vrtools.arcade.tencourse import FLAG_PIT_LANE, ORIGINAL_PIT_MIN_RUN, PIT_BOX_TABLES
            from vrtools.arcade.tgp import decode_collision
            segs = segments(out, course_entry_at(out, n.bank, n.header_base))
            lane = [q for q in range(n.pit_quad, len(segs)) if all(segs[i].flag == FLAG_PIT_LANE for i in range(n.pit_quad, q + 1))]
            assert rv.pit_quad == lane[-2] and len(lane) >= 20, (n.name, lane)
            assert rv.pit_box[:3] == pytest.approx(PIT_BOX[k], abs=0.01) and rv.pit_box[3] == 0x8000, (n.name, rv.pit_box)
            assert rv.pit_box[:3] == struct.unpack_from("<3f", out.boot, PIT_BOX_TABLES[n.template] - V60_BOOT)
            quads = decode_collision(out, k).quads
            for q in (rv.pit_quad, rv.pit_quad + 1):
                cx, cz = sum(c[0] for c in quads[q].corners) / 4, sum(c[2] for c in quads[q].corners) / 4
                assert ((cx - rv.pit_box[0]) ** 2 + (cz - rv.pit_box[2]) ** 2) ** 0.5 >= ORIGINAL_PIT_MIN_RUN, (n.name, q)
        assert (rv.map_tx, rv.map_cross) == (n.map_tx, n.map_cross) == (149.0, 0) != (MAP_TX_SHIFTED, MAP_CROSS_SHIFTED), n.name
        assert rv.header_base != n.header_base and WINDOW < rv.header_base < WINDOW + BANK_SIZE
        assert rv.race >= seven_end and d[k].reverse.at > max(e.reverse.at for e in d[3:10]), n.name
        s, t = _span(out, rv)
        assert t - s == BLOB_BYTES[k], (n.name, t - s)


ARROW_BOARDS = {0: 4, 1: 10, 2: 0}
LETTER_QUADS = 23                                       # the letter quads of a checkpoint gantry frame ("C.P." twice: both faces)
POLY_LEFT_FLOOR = 150_000                               # polygon ROM left free after the four lettered lists (measured 182 760)


def test_no_record_reads_a_colour_entry_in_the_originals_blocks_or_the_spawn_room(romset_zip, saturn_cue):
    """The boot uploads the whole program ROM as the colour table (entry e is the word at 2 * (e - 0x40000)), so what is written
    into the originals' two blocks and into SPAWN_ROOM (the lettered checkpoint lists, the reverse spawn lists) would be read as
    colours by a record that named those entries. None does: over every record of the tile tables of all TEN entries and every
    lettering object of the four lettered lists, the entries it reads (its tex and one more for each advancing record of its
    object) lie outside both spans. (`max_colour_entry` reads entries 3-9 only and gives a maximum; the far copies' colour
    block, right above the originals' block, is theirs to read.)"""
    from vrtools.arcade.course import tile_table_at
    from vrtools.arcade.gantry import FRAMES
    from vrtools.arcade.polyrom import decode_object
    from vrtools.arcade.tencourse import SPAWN_ROOM, origpic_address
    out, _ = _seven(romset_zip, saturn_cue)
    entry_of = lambda addr: 0x40000 + (addr - V60_PROGRAM) // 2
    spans = [(entry_of(origpic_address()), entry_of(origrev_address() + BLOCK_BYTES)), (entry_of(SPAWN_ROOM[0]), entry_of(SPAWN_ROOM[1]))]
    records = [(t.poly_adr, t.tex_adr, t.size) for tbl in sorted({e.tile_table for e in decode_directory(out)}) for t in tile_table_at(out, tbl)]
    tables = len(records)
    for at in _lettered(out).values():
        for p in struct.unpack_from(f"<{FRAMES}I", out.program, at - V60_PROGRAM):
            rec = struct.unpack_from("<7I", out.program, p - V60_PROGRAM)
            records += [rec[0:3], rec[3:6]]
    read = []
    for poly, tex, size in records:
        if size:
            read.append((tex, tex + sum(1 for r in decode_object(out.polygons, poly, size).records if r.tex_advance)))
    inside = [(hex(lo), hex(hi)) for lo, hi in read for a, b in spans if lo < b and a <= hi]
    print("COLOUR ENTRIES", len(read), "objects read (", tables, "tile-table records ), lowest", hex(min(lo for lo, _ in read)), "highest",
          hex(max(hi for _, hi in read)), "the spans", [(hex(a), hex(b)) for a, b in spans])
    assert len(read) > 500 and inside == [], inside[:6]


def _lettered(out) -> dict[int, int]:
    """{the game's checkpoint object list: its lettered list} of the set: the four lists lie from SPAWN_ROOM's start, in the
    order of the game's lists' addresses (`install_reverse_spawn_lists`)."""
    from vrtools.arcade.gantry import CHECKPOINT_LIST_BYTES, CHECKPOINT_OBJECTS
    from vrtools.arcade.tencourse import SPAWN_MARGIN, SPAWN_ROOM
    return {o: SPAWN_ROOM[0] + SPAWN_MARGIN + CHECKPOINT_LIST_BYTES * k for k, o in enumerate(sorted(CHECKPOINT_OBJECTS))}


def test_each_checkpoint_gantry_has_a_list_with_its_lettering_behind_the_banner(romset_zip, saturn_cue):
    """Pascal, 16 Nov: "some checkpoint flags are white without the C.P.". The game's four checkpoint lists (Big Forest's and
    Bay Bridge's two, Acropolis's two) each get a list of 32 frames in SPAWN_ROOM: frame k is the game's own frame k (the same
    object, texture word and size) followed by one more object, in polygon ROM that was erased, of 2 * LETTER_QUADS records:
    each letter quad of the frame mirrored left to right about the banner's centre and set as far behind the banner as it
    stands in front (`gantry.mirrored_letters`), one-sided, reading the colour entry the game's letters read. The game's own lists,
    frames and colour entries are the stock ROM's, and the polygon ROM keeps POLY_LEFT_FLOOR free of the lettering and every phase before
    the weather (the join's round 2, J5: a floor set before the weather feature; the weather's polygon objects, its layout's "polygon"
    blocks, 145 696 bytes in spike 70's place, are that feature's planned use, accounted in its own room table, and counted back here)."""
    from vrtools.arcade.gantry import (CHECKPOINT_DEPTH, CHECKPOINT_LIST_BYTES, CHECKPOINT_OBJECTS, CHECKPOINT_RECORD_BYTES, FRAMES, frame_quads,
                                       frame_records, gantry_parts, mirrored_letters)
    from vrtools.arcade.tencourse import POLY_FLOOR_BYTES, poly_budget
    out, _ = _seven(romset_zip, saturn_cue)
    plain, _ = _seven_plain(romset_zip, saturn_cue)
    stock = RomSet.from_zip(romset_zip)
    lettered = _lettered(out)
    assert sorted(lettered) == sorted(CHECKPOINT_OBJECTS) and CHECKPOINT_LIST_BYTES == 1024 and FRAMES == 32
    objects = []
    for game, at in lettered.items():
        off = at - V60_PROGRAM
        assert all(x == 0xFF for x in plain.program[off:off + CHECKPOINT_LIST_BYTES]), hex(at)
        ptrs = struct.unpack_from(f"<{FRAMES}I", out.program, off)
        assert ptrs == tuple(at + 4 * FRAMES + CHECKPOINT_RECORD_BYTES * k for k in range(FRAMES))
        recs = frame_records(stock, game)
        assert frame_records(out, game) == recs                                       # the game's list as it was
        parts = gantry_parts([frame_quads(stock, r) for r in recs], CHECKPOINT_DEPTH)
        assert len(parts.letters) == LETTER_QUADS
        for k, p in enumerate(ptrs):
            poly, tex, size, lpoly, ltex, lsize, end = struct.unpack_from("<7I", out.program, p - V60_PROGRAM)
            assert (poly, tex, size) == recs[k] and end == 0 and lsize == 2 * LETTER_QUADS, (hex(game), k)
            qs = frame_quads(stock, recs[k])
            assert ltex == min(qs[i].tex_adr for i in parts.letters) - 1
            objects.append(lpoly)
            key = lambda q: tuple(tuple(round(c, 3) for c in v) for v in q.p)
            want = {key(q) for q in mirrored_letters(qs, parts, ltex)}
            got = {key(q) for q in frame_quads(out, (lpoly, ltex, lsize))}
            assert len(want) == LETTER_QUADS and want <= got, (hex(game), k, len(want - got))
            assert not want & {key(qs[i]) for i in parts.letters}                     # not the game's own faces again
    assert len(set(objects)) == 4 * FRAMES
    a, b = np.frombuffer(plain.polygons, np.uint8), np.frombuffer(out.polygons, np.uint8)
    diff = np.flatnonzero(a != b)
    assert len(diff) and (a[diff] == 0xFF).all()                                      # polygon ROM: erased bytes only
    from vrtools.arcade.weather import layout as weather_layout
    weather = sum(b.size for b in weather_layout.blocks() if b.space == "polygon")   # the weather's objects (stages 2-4): its own
    left = poly_budget(out) + weather                                                # room table's use, placed after this floor
    print("POLYGON ROM free", poly_budget(plain), "->", poly_budget(out), "+ the weather's", weather)
    assert left >= POLY_LEFT_FLOOR > POLY_FLOOR_BYTES, (left, weather)


def test_the_reverse_spawn_list_has_no_arrow_board_and_the_both_sided_start_gantry(romset_zip, saturn_cue):
    """Pascal's answers C3 and C4 (15 Nov, "Yes all your recommendation"): the variant has its own spawn list in the erased run
    that ends the program ROM (SPAWN_ROOM): the game's entities in the game's order, less the arrow boards (Big Forest 4, Bay
    Bridge 10), the start gantry drawing the converted courses' both-sided frames (`start_gantry_address()`), everything else
    the same record. Stage 2: each checkpoint gantry draws its lettered list (`_lettered`). The normal entry keeps the game's
    own list, whose bytes are the stock ROM's."""
    from dataclasses import replace
    from vrtools.arcade.gantry import START_GANTRY_OBJECTS
    from vrtools.arcade.spawn import ARROW_BOARD, CHECKPOINT_GANTRIES, SPAWN_LIST_BYTES, START_GANTRY, decode_spawn_list
    from vrtools.arcade.tencourse import SPAWN_ROOM
    out, _ = _seven(romset_zip, saturn_cue)
    stock = RomSet.from_zip(romset_zip)
    d = decode_directory(out)
    spans = [(a, a + 1024) for a in sorted(_lettered(out).values())]
    for k in range(3):
        n, rv = d[k], d[k].reverse.entry
        assert n.spawn_table == ORIGINALS[k].spawn_table and SPAWN_ROOM[0] <= rv.spawn_table < SPAWN_ROOM[1], n.name
        game, mine = decode_spawn_list(stock, n.spawn_table), decode_spawn_list(out, rv.spawn_table)
        assert decode_spawn_list(out, n.spawn_table) == game
        assert sum(e.handler == ARROW_BOARD for e in game) == ARROW_BOARDS[k] and not any(e.handler == ARROW_BOARD for e in mine)
        lettered = _lettered(out)
        want = [replace(e, objlist=start_gantry_address()) if e.handler == START_GANTRY
                else replace(e, objlist=lettered[e.objlist]) if e.handler in CHECKPOINT_GANTRIES else e
                for e in game if e.handler != ARROW_BOARD]
        assert sum(e.handler in CHECKPOINT_GANTRIES for e in mine) == 2 and all(e.objlist in lettered for e in game if e.handler in CHECKPOINT_GANTRIES)
        assert mine == want and len(mine) == len(game) - ARROW_BOARDS[k], n.name
        assert [e.objlist for e in game if e.handler == START_GANTRY] == [START_GANTRY_OBJECTS]
        spans.append((rv.spawn_table, rv.spawn_table + SPAWN_LIST_BYTES(len(mine))))
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])) and spans[-1][1] <= SPAWN_ROOM[1]
    assert struct.unpack_from("<I", out.program, start_gantry_address() - V60_PROGRAM)[0] != 0xFFFFFFFF      # the list is there


def test_the_variant_is_the_roms_own_tables_read_backwards(romset_zip, saturn_cue):
    """The variant's eight line pointers name the lines of ORIGINAL_REVERSE_PAIRS (Big Forest and Acropolis their eight, Bay
    Bridge the centreline eight times), and its lines and segment array are `reverse_original` of the tables the ROM holds for
    the normal course; the collision map and the surface table are the normal course's (one collision for both directions)."""
    out, _ = _seven(romset_zip, saturn_cue)
    stock = RomSet.from_zip(romset_zip)
    d = decode_directory(out)
    for k in range(3):
        n, rv = d[k], d[k].reverse.entry
        ne, re_ = course_entry_at(out, n.bank, n.header_base), course_entry_at(out, rv.bank, rv.header_base)
        want = reverse_original(road_lines(stock, course_entry_at(stock, n.bank)), segments(stock, course_entry_at(stock, n.bank)))
        got = road_lines(out, re_)
        from dataclasses import replace as _r
        from vrtools.arcade.tencourse import FLAG_NO_PUTBACK
        marked = [_r(sg, flag=sg.flag | FLAG_NO_PUTBACK) if sg.index in NO_PUTBACK[k] else sg for sg in want.segments]
        assert segments(out, re_) == marked, n.name                   # (second fix wave: the no-put-back mark on a few quads)
        for pair, line in zip(ORIGINAL_REVERSE_PAIRS[k], got):
            assert line == want.lines[pair], (n.name, pair)
        ptrs = [p for p, _ in decode_pointer_block(out, re_).lines]
        assert len(set(ptrs)) == STORED_LINES[k] == len(set(ORIGINAL_REVERSE_PAIRS[k])), n.name
        a, b = decode_pointer_block(out, ne), decode_pointer_block(out, re_)
        assert (a.collision, a.surface) == (b.collision, b.surface) and ne.header.gfx_dir == re_.header.gfx_dir, n.name
        assert (re_.header.road_points, re_.header.segment_count) == (POINTS[k], ne.header.segment_count)


def test_bay_bridge_is_on_one_line_because_bank_one_is_full(romset_zip, saturn_cue):
    """The stopgap, in numbers: bank 1 keeps BANK_ONE_FLOOR in its largest free run after Bay Bridge's one-line variant, and a
    second stored line (6 816 bytes) would not fit what is left."""
    from vrtools.arcade import blob
    out, _ = _seven(romset_zip, saturn_cue)
    plain, _ = _seven_plain(romset_zip, saturn_cue)
    left = max(size for _, size in blob.free_runs(out, 1, min_size=16))
    before = max(size for _, size in blob.free_runs(plain, 1, min_size=16))
    print("BANK 1 free before", before, "after", left)
    assert before - left == BLOB_BYTES[1] and left == BANK_ONE_FLOOR == 1_152
    assert left < POINT_BYTES * (POINTS[1] + WRAP_POINTS)


def test_the_reverse_race_blob_is_the_games_tables_with_the_gates_renumbered(romset_zip, saturn_cue):
    """The variant's checkpoints are the game's renumbered, (n - g) mod n; its twelve time records are the game's own records
    (the game pays one extension at every checkpoint of a course: EXTENSION at level 0 in the normal game); its car table is the game's
    but for the start points (ORIGINAL_REVERSE_GRID: Bay Bridge and Acropolis car k on point 2k, Big Forest its lines interleaved
    within the game's fifteen points)."""
    out, _ = _seven(romset_zip, saturn_cue)
    stock = RomSet.from_zip(romset_zip)
    d = decode_directory(out)
    from vrtools.arcade.race import car_table
    for k in range(3):
        rv = d[k].reverse.entry
        cps = checkpoints_at(stock, rv.template)
        b = decode_race_blob(out, rv.race)
        assert b.checkpoints == REVERSE_CHECKPOINTS[k] == tuple(sorted((POINTS[k] - g) % POINTS[k] for g in cps)), NAMES[k]
        game_cars = car_table(stock, 0)
        assert len(b.times) == 12 and [(c.models, c.line, c.perf) for c in b.cars] == [(c.models, c.line, c.perf) for c in game_cars]
        assert [c.start_point for c in game_cars] == list(range(16))                 # the game's grid: car k on point k
        assert [c.start_point for c in b.cars] == list(ORIGINAL_REVERSE_GRID[k]) == list(GRID[k]), NAMES[k]
        for (v, lvl), rec in b.times.items():
            game = time_record(stock, v, rv.template, lvl)
            assert rec == game and len(set(rec.extensions)) == 1, (NAMES[k], v, lvl)
            assert lap_total(rec, b.checkpoints) == lap_total(game, cps)
        assert b.times[(0, 0)].initial == 2080 and b.times[(0, 0)].extensions[0] == EXTENSION[k], NAMES[k]


def test_the_originals_variants_only_add_bytes(romset_zip, saturn_cue):
    """Against the set without them (the set before Phase 33), the set differs in exactly this:
    - data ROM: each variant's blob, on bytes that were erased, in its original's own bank;
    - program ROM: the three words of the reverse table; the originals' block (erased before); the four lettered checkpoint
      lists and the three reverse spawn lists in SPAWN_ROOM (erased before); and the annex, where the three
      new load and maps records and race blobs follow the seven's and the seven's race blobs lie ANNEX_SHIFT bytes higher (the
      same blobs, decoded) with their load records' race pointers moved by as much: nothing else of the seven's records changes;
    - boot ROM: HUD_SITE's six bytes (`jsr hudorig` for `jsr hudname`; Phase 35: RANK_SITE is the game's own on both, as
      `rankgate3` is gone); fix wave: the originals' direction-screen picture data in the erased run BOOT_FREE (and one
      original's in erased bank 0), the picture block below the originals' block, and LOCK_SITE's call (`jsr olock` for
      `jsr dirlock`); nothing inside the directory image but the reverse table's three words and (Phase 35) the ranking
      image's attract groups and `raceend`'s positions (each original's reverse id in its group);
    - polygon ROM: the checkpoint gantries' lettering objects (stage 2), on bytes that were erased;
    - TGP data and TGP program: nothing (one collision for both directions: 0 TGP words).
    (Weather stage 1: the session's set without the weather screen, which needs the originals' variants and adds its own blocks:
    tests/test_weather_dry.py::test_the_switch_changes_only_the_named_blocks.)"""
    from tests.test_weather_dry import _seven_dry
    a, _ = _seven_plain(romset_zip, saturn_cue)
    b, _ = _seven_dry(romset_zip, saturn_cue)
    assert (a.copro_data, a.tgp_program) == (b.copro_data, b.tgp_program)
    pa, pb = np.frombuffer(a.polygons, np.uint8), np.frombuffer(b.polygons, np.uint8)
    assert (pa[np.flatnonzero(pa != pb)] == 0xFF).all()
    da, db = decode_directory(a), decode_directory(b)
    assert all(e.reverse is None for e in da[:3]) and all(e.reverse is not None for e in db)
    # data
    ad, bd = np.frombuffer(a.data, np.uint8), np.frombuffer(b.data, np.uint8)
    data = np.flatnonzero(ad != bd)
    inside = np.zeros(len(data), bool)
    for k in range(3):
        s, t = _span(b, db[k].reverse.entry)
        assert s // BANK_SIZE == db[k].bank and (ad[s:t] == 0xFF).all(), NAMES[k]
        inside |= (s <= data) & (data < t)
    pictures = _picture_data(b)                                                       # fix wave: the originals' direction-screen data
    for art, (at, size, _, _, _) in pictures.items():
        if at < 0x200000:
            assert (ad[at - 0x100000:at - 0x100000 + size] == 0xFF).all(), art
            inside |= (at - 0x100000 <= data) & (data < at - 0x100000 + size)
    assert len(data) and inside.all(), [hex(i) for i in data[~inside][:8]]
    # boot
    ab, bb = np.frombuffer(a.boot, np.uint8), np.frombuffer(b.boot, np.uint8)
    boot = set(int(i) + V60_BOOT for i in np.flatnonzero(ab != bb))
    from vrtools.arcade.tencourse import BOOT_FREE
    assert (ab[BOOT_FREE[0] - V60_BOOT:BOOT_FREE[1] - V60_BOOT] == 0xFF).all()
    from vrtools.arcade.dirscreen import LOCK_SITE
    assert boot and boot <= (set(range(HUD_SITE, HUD_SITE + 6)) | set(range(*BOOT_FREE))
                             | set(range(LOCK_SITE, LOCK_SITE + 9))), sorted(hex(i) for i in boot)[:8]
    assert a.boot[RANK_SITE - V60_BOOT:RANK_SITE - V60_BOOT + 16] == b.boot[RANK_SITE - V60_BOOT:RANK_SITE - V60_BOOT + 16] == RANK_PATTERN
    # program
    ap, bp = np.frombuffer(a.program, np.uint8), np.frombuffer(b.program, np.uint8)
    prog = np.flatnonzero(ap != bp) + V60_PROGRAM
    table = directory_layout()["reverse"]
    block = origrev_address()
    lo = min(e.reverse.at for e in db)
    hi = max(e.reverse.entry.race for e in db) + RACE_BLOB_BYTES
    old_hi = max(e.reverse.entry.race for e in da[3:10]) + RACE_BLOB_BYTES
    assert hi == old_hi + ANNEX_SHIFT + 3 * RACE_BLOB_BYTES
    assert any(x <= lo and hi <= y for x, y in annex_regions())
    assert (ap[old_hi - V60_PROGRAM:hi - V60_PROGRAM] == 0xFF).all() and (ap[block - V60_PROGRAM:block - V60_PROGRAM + BLOCK_BYTES] == 0xFF).all()
    from vrtools.arcade.tencourse import SPAWN_ROOM
    assert (ap[SPAWN_ROOM[0] - V60_PROGRAM:SPAWN_ROOM[1] - V60_PROGRAM] == 0xFF).all()
    from vrtools.arcade import origpic
    from vrtools.arcade.tencourse import origpic_address
    pic = origpic_address()
    assert (ap[pic - V60_PROGRAM:block - V60_PROGRAM] == 0xFF).all()
    image_lo, image_hi = directory_layout()["dirclear"], directory_layout()["end"]   # second fix wave: nothing inside the directory
    from vrtools.arcade.ranking import GROUP_BYTES, IDS, ranking_layout                # image but the table (Phase 35: and the groups
    rl = ranking_layout(directory_layout()["ranking"])                                 # and positions, which hold the reverse ids)
    ranks = (((rl["groups"] <= prog) & (prog < rl["groups"] + 3 * GROUP_BYTES)) | ((rl["positions"] <= prog) & (prog < rl["positions"] + IDS)))
    allowed = (((table <= prog) & (prog < table + 12)) | ranks | ((pic <= prog) & (prog < block + BLOCK_BYTES)) | ((lo <= prog) & (prog < hi))
               | ((SPAWN_ROOM[0] <= prog) & (prog < SPAWN_ROOM[1])))
    assert not (((image_lo <= prog) & (prog < image_hi)) & ~((table <= prog) & (prog < table + 12)) & ~ranks).any()
    assert allowed.all(), [hex(i) for i in prog[~allowed][:8]]
    assert (ap[table - V60_PROGRAM:table - V60_PROGRAM + 12] == 0).all()
    # the seven's records: where they were, the same but for the race pointer; their blobs the same blobs, higher
    race = LOAD_FIELDS["race"]
    for ea, eb in zip(da[3:10], db[3:10]):
        assert ea.reverse.at == eb.reverse.at, ea.name
        ra = a.program[ea.reverse.at - V60_PROGRAM:ea.reverse.at - V60_PROGRAM + LOAD_SIZE]
        rb = b.program[eb.reverse.at - V60_PROGRAM:eb.reverse.at - V60_PROGRAM + LOAD_SIZE]
        assert ra[:race] == rb[:race] and ra[race + 4:] == rb[race + 4:], ea.name
        assert eb.reverse.entry.race == ea.reverse.entry.race + ANNEX_SHIFT, ea.name
        m = maps_offset()
        assert a.program[ea.reverse.at + m - V60_PROGRAM:][:LOAD_SIZE] == b.program[eb.reverse.at + m - V60_PROGRAM:][:LOAD_SIZE], ea.name
        assert decode_race_blob(a, ea.reverse.entry.race) == decode_race_blob(b, eb.reverse.entry.race), ea.name
        from dataclasses import replace
        assert replace(ea, reverse=None) == replace(eb, reverse=None), ea.name
        assert replace(ea.reverse.entry, race=0) == replace(eb.reverse.entry, race=0), ea.name
    for ea, eb in zip(da[:3], db[:3]):
        from dataclasses import replace
        assert ea == replace(eb, reverse=None), ea.name                      # the originals' normal records


def test_the_sites_and_the_block_are_checked_before_anything_is_written(romset_zip, saturn_cue):
    """`install_origrev` refuses a set whose ranking site is not the game's, whose HUD site is not `jsr hudname`, or whose block
    is not erased, naming the address; on the plain set it writes the block and the HUD site and nothing else (Phase 35: the
    ranking site is checked, no longer written)."""
    plain, _ = _seven_plain(romset_zip, saturn_cue)
    lay = directory_layout()
    at = origrev_address()

    def copy(rs, boot=None, program=None):
        return RomSet(program or rs.program, boot or rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    made = copy(plain)
    install_origrev(made, at, lay["hudname"], lay["hudrev"])
    assert made.program[at - V60_PROGRAM:at - V60_PROGRAM + USED_BYTES] == b"".join(origrev_routines(at, lay["hudname"], lay["hudrev"]).values())
    diff = [i for i in range(len(plain.program)) if plain.program[i] != made.program[i]]
    assert diff and at - V60_PROGRAM <= min(diff) and max(diff) < at - V60_PROGRAM + BLOCK_BYTES
    boot = bytearray(plain.boot); boot[RANK_SITE - V60_BOOT] ^= 1
    with pytest.raises(PatchError, match=f"{RANK_SITE:#x}"):
        install_origrev(copy(plain, boot=bytes(boot)), at, lay["hudname"], lay["hudrev"])
    boot = bytearray(plain.boot); boot[HUD_SITE - V60_BOOT + 2] ^= 1
    with pytest.raises(PatchError, match=f"{HUD_SITE:#x}"):
        install_origrev(copy(plain, boot=bytes(boot)), at, lay["hudname"], lay["hudrev"])
    prog = bytearray(plain.program); prog[at - V60_PROGRAM + BLOCK_BYTES - 1] = 0
    with pytest.raises(PatchError, match=f"{at:#x}"):
        install_origrev(copy(plain, program=bytes(prog)), at, lay["hudname"], lay["hudrev"])


# ---- in MAME ----
# One run per session per label (the tests share them); VR_MAME_JOBS bounds the MAME processes when several sessions run.
# The autopilot drives road line 0 (the ROM's own centreline), read backwards in reverse.

RACE_SECONDS = 150
SAME_SECONDS = 120
LANE = {0: (-226.0, 334, 29, range(30, 60)), 2: (-342.9, 588, 27, range(28, 56))}     # the pit lane: x, first and last road point,
                                                                                    # its quads beside the straight (flag 66; recon §6.1)
LANE_IN, LANE_OUT = 12, 7                                # the lap's line blended into the lane over these points before / after it
EXTENSIONS_FLOOR = {0: 5, 1: 4, 2: 3}                    # clock extensions in RACE_SECONDS, reverse (measured 6, 5, 4)
LEADER_FLOOR = {0: 700, 1: 900, 2: 1000}                 # the leading opponent's road points gained (measured 842, 1 143, 1 225)
CURSOR_LEAD_MAX = {0: 8, 1: 20, 2: 8}                    # an opponent's line cursor over its road point (measured 6, 14, 3; Bay
                                                         # Bridge's sixteen cars share one line)
ORIG_TABLES = {0: 0x40E480, 1: 0x40E000, 2: 0x40E240}    # the originals' best-time tables by menu entry (ranking.ORIG_TABLES by data index)
BATTERY_RANKING = (0x40E000, 0x40FDFF)                   # every ranking table, slot, counter and cell (ranking.py)
NAME_ENTRY = 0x1E
_RUNS: dict = {}


def _centreline(rs, entry):
    e = decode_directory(rs)[entry]
    return [(p.x, p.z) for p in road_lines(rs, course_entry_at(rs, e.bank, e.header_base))[0]]


def lane_lap(line0, entry):
    """The lap through the pit lane: road line 0 with its x moved to the lane's over the lane's road points (both lanes run
    along +z beside the start straight), blended in over LANE_IN points before and LANE_OUT after (tests/test_frame_rate.py's
    `bf_pit_path`, for either course)."""
    x_lane, first, last, _ = LANE[entry]
    n = len(line0)
    lane = {k % n for k in range(first, last + n + 1)}
    out = []
    for k, (x, z) in enumerate(line0):
        if k in lane:
            x = x_lane
        else:
            before, after = (first - k) % n, (k - last) % n
            if before <= LANE_IN:
                x += (x_lane - x) * (LANE_IN + 1 - before) / (LANE_IN + 1)
            elif after <= LANE_OUT:
                x += (x_lane - x) * (LANE_OUT + 1 - after) / (LANE_OUT + 1)
        out.append((x, z))
    return out


def _mame(tmp_path_factory, romset_zip, saturn_cue, label, entry, reverse, seconds=RACE_SECONDS, plain=False, line=None, env=None,
          nvram=None, dry=False, setdir=None):
    """The work directory of one run of `entry` on the session's set (or the set without the originals' variants; `dry`: the
    session's set without the weather screen, tests.test_weather_dry._seven_dry; `setdir`: another set's directory, the session's
    set's autopilot line), made once."""
    from tests.test_tgp_build import _build
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.convert.reverse import reverse_points
    from vrtools.mame.runner import DUMP_STEP, LUA_DIR, run_mame, write_centreline
    if label not in _RUNS:
        from tests.test_weather_dry import _seven_dry
        out, _ = (_seven_plain if plain else _seven_dry if dry else _seven)(romset_zip, saturn_cue)
        key = "build_plain" if plain else "build_dry" if dry else "build"
        if key not in _RUNS and setdir is None:
            _RUNS[key] = _build(tmp_path_factory.mktemp(key), romset_zip, out)
        wd = tmp_path_factory.mktemp(label) / "wd"
        if nvram is not None:
            import shutil
            shutil.copytree(nvram, wd / "nvram")
        line = line or _centreline(out, entry)
        full = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
                "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", reverse_points(line) if reverse else line)),
                "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0", "VR_RACE_CARS_TO": "2700", "VR_HUD_LOG": str(wd / "hud.txt"),
                "VR_PIT_LOG": str(wd / "pit.txt"), "VR_HUDROWS_LOG": str(wd / "rows.txt"),
                "VR_FIELD_LOG": str(wd / "field.txt"), "VR_FIELD_FROM": "1400", "VR_FIELD_TO": "999999", "VR_FIELD_EVERY": "2",
                "VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_FROM": "0", "VR_TRACE_TO": "0",
                "VR_TRACE_DUMP": ",".join(str(f) for f in range(1600, int(seconds * 57.5), DUMP_STEP))}
        if reverse:
            full["VR_DIRECTION"] = "1"
        full["VR_SOUND_LOG"] = str(wd / "sound.txt")                # (third review: Bay Bridge's tunnel in reverse)
        full.update({k: str(v).replace("{wd}", str(wd)) for k, v in (env or {}).items()})
        run_mame(LUA_DIR / "autoplay.lua", seconds, wd, setdir or _RUNS[key], env=full, timeout=3600)
        _RUNS[label] = wd
    return _RUNS[label]


def _booted(tmp_path_factory, romset_zip, saturn_cue, setdir=None):
    """The nvram directory of a 30-s attract boot of the session's set (or the set at `setdir`) on no battery RAM, made once: the
    battery RAM every later boot of this set finds (the S-RAM magic, REV4, ORG4 and every table in place)."""
    from vrtools.mame.runner import LUA_DIR, run_mame
    if setdir is not None:
        if ("nvram", str(setdir)) not in _RUNS:
            boot = tmp_path_factory.mktemp("nvram_boot_ref")
            run_mame(LUA_DIR / "attract_snaps.lua", 30, boot, setdir, env={"VR_SNAP_FROM": "999999"}, timeout=900)
            _RUNS[("nvram", str(setdir))] = boot / "nvram"
        return _RUNS[("nvram", str(setdir))]
    if "nvram" not in _RUNS:
        from tests.test_tgp_build import _build
        out, _ = _seven(romset_zip, saturn_cue)
        if "build" not in _RUNS:
            _RUNS["build"] = _build(tmp_path_factory.mktemp("build"), romset_zip, out)
        boot = tmp_path_factory.mktemp("nvram_boot")
        run_mame(LUA_DIR / "attract_snaps.lua", 30, boot, _RUNS["build"], env={"VR_SNAP_FROM": "999999"}, timeout=900)
        _RUNS["nvram"] = boot / "nvram"
    return _RUNS["nvram"]


def _race(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """RACE_SECONDS of `entry` under the autopilot, booted on `_booted`'s battery RAM (Phase 35 fix wave: on no battery
    RAM the boot's own initialisation, longer since Phase 35 by `originit`, moves where MAME's frame ends fall inside a pass;
    the autopilot samples the car there, so its steering, not the game, changed: Bay Bridge in reverse ran out of time on
    its second lap. On a battery RAM an earlier boot of the same set made, the boot initialises nothing, as on the set before;
    findings §6). The join's round 2, J5: the same holds for any set whose passes take other times (the weather's dry paths):
    Bay Bridge in reverse on the weather set, untaped, parts from v0.3's at pass 1042 (the player's x in its last bits, after
    another wheel value) and gets 3 extensions against v0.3's 5, while fed v0.3's inputs it is v0.3's game pass for pass (5
    extensions; out/p80j/j5bb.txt). So the race is driven by the inputs the autopilot gave on the set before the weather
    (`_ref_tape`: VR_PRE_WEATHER_SET, the released v0.3, on its own battery RAM), replayed frame for frame (input_tape.lua);
    without that set the race is not run: the test skips naming the variable (fails with VR_REQUIRE_REFERENCE_SETS=1), never
    untaped (untaped, Bay Bridge reverse gets 3 extensions against the floor of 4: J5's measure)."""
    tape = _ref_tape(tmp_path_factory, romset_zip, saturn_cue, entry, reverse)
    env = {"VR_INPUT_REPLAY": str(tape), "VR_INPUT_LOG": "{wd}/tape.txt"}
    return _mame(tmp_path_factory, romset_zip, saturn_cue, f"race{entry}{'r' if reverse else 'n'}", entry, reverse,
                 nvram=_booted(tmp_path_factory, romset_zip, saturn_cue), env=env)


def _ref_tape(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """The autopilot's inputs (input_tape.lua's log) on `_race`'s race on the set before the weather (test_weather_dry's
    reference set VR_PRE_WEATHER_SET), booted on that set's own battery RAM; skipped (failed with VR_REQUIRE_REFERENCE_SETS=1)
    when that set is not there."""
    from tests.reference_sets import reference_set
    PRE_WEATHER_SET = reference_set("VR_PRE_WEATHER_SET")
    wd = _mame(tmp_path_factory, romset_zip, saturn_cue, f"refrace{entry}{'r' if reverse else 'n'}", entry, reverse,
               nvram=_booted(tmp_path_factory, romset_zip, saturn_cue, PRE_WEATHER_SET), setdir=PRE_WEATHER_SET,
               env={"VR_INPUT_LOG": "{wd}/tape.txt"})
    return wd / "tape.txt"


def _window(wd):
    """The race's player samples: from the clock's first count to its end (or the log's)."""
    from vrtools.mame.runner import parse_race_log
    player, jolts = parse_race_log(wd / "race.txt")
    start = next(b.frame for a, b in zip(player, player[1:]) if 0 < b.clock < a.clock)
    end = next((p.frame for p in player if p.frame > start and p.clock <= 0), player[-1].frame + 1)
    return [p for p in player if start <= p.frame < end], [j for j in jolts if start <= j.frame < end]


@pytest.mark.parametrize("entry", [0, 1, 2])
def test_an_original_races_in_reverse_on_its_variant(tmp_path_factory, romset_zip, saturn_cue, entry):
    """RACE_SECONDS of the original in reverse under the autopilot: the loader served the variant's race blob, the player
    starts on road point 0 and the flag stays 1; every lap of every car is counted at its crossing and no car steps back over
    the line; the checkpoints extend the clock; all fifteen opponents move, none is parked, their line cursors stay with them."""
    from vrtools.arcade.race import race_blob_layout
    from vrtools.mame.runner import parse_field, race_report
    wd = _race(tmp_path_factory, romset_zip, saturn_cue, entry, True)
    tape = _ref_tape(tmp_path_factory, romset_zip, saturn_cue, entry, True)
    if tape:                                                                  # fed exactly the reference run's inputs (J5)
        assert (wd / "tape.txt").read_text() == tape.read_text() and len(tape.read_text().splitlines()) > 3000, NAMES[entry]
    out, _ = _seven(romset_zip, saturn_cue)
    rv = decode_directory(out)[entry].reverse.entry
    n = POINTS[entry]
    r = race_report(wd, n)
    player, jolts = _window(wd)
    lay = race_blob_layout(rv.race)
    assert r["time_record"] == lay["records"] and r["checkpoint_record"] == lay["checkpoints"], NAMES[entry]
    assert player[0].road_point == 0 and r["opponents_at_origin"] == 0
    cars = {}
    for s in parse_field(wd / "field.txt"):
        if player[0].frame <= s.frame + 1 <= player[-1].frame:
            cars.setdefault(s.car, []).append(s)
    wraps = {c: sum(1 for a, b in zip(s, s[1:]) if a.point - b.point > 100) for c, s in cars.items()}
    bad = [(c, b.frame) for c, s in cars.items() for a, b in zip(s, s[1:]) if a.point - b.point > 100 and b.lap != a.lap + 1]
    back = [(c, b.frame) for c, s in cars.items() for a, b in zip(s, s[1:]) if b.point - a.point > n - 100]
    lead = max((q.cursor - q.point + n // 2) % n - n // 2 for c, s in cars.items() if c for q in s)
    rises = sum(1 for a, b in zip(player, player[1:]) if b.clock > a.clock)
    print("ORIGINAL reverse", NAMES[entry], {k: v for k, v in r.items() if k not in ("frames", "clock", "cars")}, "wraps", wraps,
          "lead", lead, "extensions", rises, "jolts", len(jolts))
    assert len(cars) == 16 and wraps[0] >= 1 and not bad and not back, (NAMES[entry], wraps, bad[:4], back[:4])
    assert rises >= EXTENSIONS_FLOOR[entry] and r["extensions"] >= EXTENSIONS_FLOOR[entry], (NAMES[entry], rises, r["extensions"])
    assert r["moved"] == 15 and r["parked"] == 0 and r["max_backstep"] == 0, (NAMES[entry], r["moved"], r["parked_cars"])
    assert r["leader_points"] >= LEADER_FLOOR[entry] and lead <= CURSOR_LEAD_MAX[entry], (NAMES[entry], r["leader_points"], lead)


GRID_TURN_MAX = 10.0        # degrees between an opponent's yaw and its own line's heading at its grid point, at the green (measured
                            # at most 4.4 on the three; on the game's one-point grid 25-56 for 3 to 10 cars a course)
EARLY_FRAMES, EARLY_JOLTS_MAX = 400, 2                   # opponents onto the verge in the first seven seconds (measured 0-1; Bay
                                                         # Bridge on the one-point grid: 7)


@pytest.mark.parametrize("entry", [0, 1, 2])
def test_no_opponent_stands_turned_on_an_originals_reverse_grid(tmp_path_factory, romset_zip, saturn_cue, entry):
    """The reverse grid (ORIGINAL_REVERSE_GRID): at the green every opponent stands on its grid point of its
    own line, its yaw within GRID_TURN_MAX of that line's heading there, and at most EARLY_JOLTS_MAX opponents touch the verge
    in the first EARLY_FRAMES frames of the race."""
    from vrtools.mame.runner import parse_race_log
    wd = _race(tmp_path_factory, romset_zip, saturn_cue, entry, True)
    out, _ = _seven(romset_zip, saturn_cue)
    rv = decode_directory(out)[entry].reverse.entry
    lines = road_lines(out, course_entry_at(out, rv.bank, rv.header_base))
    table = decode_race_blob(out, rv.race).cars
    player, jolts = _window(wd)
    green = player[0].frame
    at = {}
    for row in open(wd / "race.txt"):
        p = row.split()
        if p and p[0] == "O" and int(p[1]) == green - 1:
            at[int(p[2])] = (int(p[3]), int(p[6]))
    assert sorted(at) == list(range(1, 16)), sorted(at)
    turn = {}
    for car, (point, yaw) in at.items():
        heading = ((((lines[table[car].line][point].heading >> 16) ^ 0x8000) - 0x8000) * 4)
        turn[car] = abs(((yaw - heading + 0x8000) % 0x10000) - 0x8000) * 360 / 65536
    early = [(j.car, j.frame - green) for j in jolts if j.frame < green + EARLY_FRAMES]
    print("GRID reverse", NAMES[entry], "points", {c: p for c, (p, _) in sorted(at.items())}, "worst turn", round(max(turn.values()), 1), "early jolts", early)
    assert {c: p for c, (p, _) in at.items()} == {c: GRID[entry][c] for c in range(1, 16)}, NAMES[entry]
    assert max(turn.values()) <= GRID_TURN_MAX, (NAMES[entry], {c: round(t, 1) for c, t in turn.items() if t > GRID_TURN_MAX})
    assert len(early) <= EARLY_JOLTS_MAX, (NAMES[entry], early)


@pytest.mark.parametrize("entry", [0, 1, 2])
def test_the_game_sees_an_originals_quads_turned_round(tmp_path_factory, romset_zip, saturn_cue, entry):
    """The half turn of the collision's direction applies to the originals' own quads: over the reverse race the player's yaw is
    within an eighth of a turn of the direction the game stored for its quad (+0xeb) on nine frames in ten (measured 94-99 %; the
    rest are the autopilot's contacts and put-backs), and in the normal race on the same set as well."""
    for reverse in (True, False):
        player, _ = _window(_race(tmp_path_factory, romset_zip, saturn_cue, entry, reverse))
        near = sum(1 for p in player if abs(((p.yaw - p.attr + 0x8000) % 0x10000) - 0x8000) < 0x2000)
        print("ATTR", NAMES[entry], "reverse" if reverse else "normal", near, len(player))
        assert near >= 0.9 * len(player), (NAMES[entry], reverse, near, len(player))


@pytest.mark.parametrize("entry", [0, 1, 2])
def test_a_reverse_race_shows_reverse_under_the_level_word(tmp_path_factory, romset_zip, saturn_cue, entry):
    """`hudorig` (Pascal, 16 Nov: "reverse is not showing in the reverse track during gameplay"): in a reverse race on an
    original, rows 44-45 hold the game's own level word in the game's colour, cell for cell what the normal race shows
    (BEGINNER / " MEDIUM " / " EXPERT " on columns 51-58), and rows 46-47 hold Phase 32's word REVERSE in the game's red, its
    last letter in column WORD_LAST (under the word's last visible letter), nothing else on those rows from column 19; it is
    there at the race load, 60 frames into the race and at every 500th frame after, and nothing wrote those cells in between.
    In the normal race rows 46-47 are blank from column 19 (tests/test_hudreverse_build.py reads that on the three as well).
    The printer's colour cell [0x501434] is the game's after the print in both (hud_log.lua's `attr`)."""
    from vrtools.arcade.hudname import REVERSE_TEXT
    from vrtools.mame.runner import parse_hud_log, parse_hudrows_log
    from tests.test_hudname_build import GAME_WORDS
    from tests.test_hudreverse_build import FREE_FROM, ON_SCREEN, RED, _blank, _text
    word, colour = GAME_WORDS[entry]
    last = WORD_LAST[entry]
    first = last + 1 - len(REVERSE_TEXT)
    runs = {r: parse_hudrows_log(_race(tmp_path_factory, romset_zip, saturn_cue, entry, r) / "rows.txt") for r in (True, False)}
    for r, (lines, writes) in runs.items():
        racing = [l for l in lines if l.tag in ("load", "race", "lap")]
        assert {"load", "race", "lap"} <= {l.tag for l in racing}, (NAMES[entry], r, sorted({l.tag for l in lines}))
        for l in racing:
            assert _text(l.rows, 44, 51, 58) == (word, {colour}), (NAMES[entry], r, l.tag, l.frame)
            assert _blank(l.rows, 44, FREE_FROM, 50) and _blank(l.rows, 44, 59, 63)
            if r:
                assert _text(l.rows, 46, first, last) == (REVERSE_TEXT.decode(), {RED}), (NAMES[entry], l.tag, [hex(w) for w in l.rows[46][44:]])
                assert _blank(l.rows, 46, FREE_FROM, first - 1) and _blank(l.rows, 46, last + 1, 63), (NAMES[entry], l.tag)
            else:
                assert _blank(l.rows, 46, FREE_FROM, 63), (NAMES[entry], l.tag, l.frame)
        assert writes[1] == 0, (NAMES[entry], r, writes)
    assert 51 <= first and last < ON_SCREEN
    logs = {r: {h.mode: h for h in parse_hud_log(_race(tmp_path_factory, romset_zip, saturn_cue, entry, r) / "hud.txt")} for r in (True, False)}
    load = [m for m in logs[True] if 0x11 <= m <= 0x14]
    assert 0x14 in load and all(logs[True][m].attr == logs[False][m].attr for m in load if m in logs[False]), NAMES[entry]


PIT_SECONDS = 200
STOP_FRAMES_MIN = 300                                    # a whole stop: the player's pit handler without a break
BOX_NEAR = 0.5                                           # the parked car from the box


def _pit_lap(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """A race along the pit lane with the clock held (`lane_lap`; in reverse the same lap read backwards: in by the normal exit):
    (the work directory, the player's window, the pit log inside it, the frames [first, release) of its first stop)."""
    from vrtools.mame.runner import PIT_HANDLER, parse_pit_log
    out, _ = _seven(romset_zip, saturn_cue)
    wd = _mame(tmp_path_factory, romset_zip, saturn_cue, f"lane{entry}{'r' if reverse else 'n'}", entry, reverse, seconds=PIT_SECONDS,
               line=lane_lap(_centreline(out, entry), entry), env={"VR_HOLD_CLOCK": "1"})
    player, _ = _window(wd)
    pit = [p for p in parse_pit_log(wd / "pit.txt") if player[0].frame <= p.frame <= player[-1].frame]
    first = next((p.frame for p in pit if p.handler == PIT_HANDLER), None)
    release = next((p.frame for p in pit if first is not None and p.frame > first and p.handler != PIT_HANDLER), None)
    return wd, player, pit, (first, release)


@pytest.mark.parametrize("entry", [0, 2])
def test_a_reverse_race_has_a_working_pit_stop(tmp_path_factory, romset_zip, saturn_cue, entry):
    """Pascal, 16 Nov: "the pit isnt working". A reverse race on Big Forest and on Acropolis driven along the pit lane, entered
    by the normal exit: the green grants the stops the normal race grants; in the lane the game's own pit sequence takes the car
    (the player's pit handler without a break for STOP_FRAMES_MIN frames or more), the crew stands round it, it is parked on the
    game's own box within BOX_NEAR, facing the reverse way (yaw 0x8000, the normal stop's 0 turned half a turn); the stop takes
    one of the stops left; the car is released, drives on along the reverse lap and its next crossing of the line counts a lap.
    Against the same lane driven in the normal direction on the same set: the same number of stops granted, the same handler
    states in the same order, the same crew, and the same time on the box to the frame (from the parked state's first frame to
    the release: measured 442 frames both ways on both courses; the drive up the lane differs with its length from either
    end, the whole stop within a fifth). The word REVERSE and the level word are on
    their cells before, during and after the stop, and no write reached them."""
    from vrtools.arcade.hudname import REVERSE_TEXT
    from vrtools.mame.runner import parse_hudrows_log
    from tests.test_hudreverse_build import RED, _text
    res = {}
    for reverse in (True, False):
        wd, player, pit, (first, release) = _pit_lap(tmp_path_factory, romset_zip, saturn_cue, entry, reverse)
        assert first is not None and release is not None and release - first >= STOP_FRAMES_MIN, (NAMES[entry], reverse, first, release)
        stop = [p for p in pit if first <= p.frame < release]
        states = [a.state for a, b in zip(stop, stop[1:] + [None]) if b is None or b.state != a.state]
        parked = stop[-1]
        after = [p for p in pit if p.frame >= release]             # `moved`: the farthest the car got from the box after the release
        on_box = next(p.frame for p in stop if p.state == states[-2])
        res[reverse] = dict(granted=pit[0].stops, entered_quad=stop[0].quad, states=states, frames=release - first, work=release - on_box,
                            crew=max(len(p.crew) for p in stop),
                            parked=(round(parked.x, 2), round(parked.z, 2)), yaw=parked.yaw % 0x10000, stops_after=after[0].stops,
                            lap_before=stop[0].lap, lap_end=after[-1].lap, moved=round(max(abs(p.z - parked.z) + abs(p.x - parked.x) for p in after), 1))
        print("PIT", NAMES[entry], "reverse" if reverse else "normal", res[reverse])
        res[reverse]["wd"], res[reverse]["span"] = wd, (first, release)
    rv, nm = res[True], res[False]
    out, _ = _seven(romset_zip, saturn_cue)
    box = decode_directory(out)[entry].reverse.entry.pit_box
    assert rv["entered_quad"] in (PIT_QUAD[entry], PIT_QUAD[entry] + 1), (NAMES[entry], rv["entered_quad"])
    assert abs(rv["parked"][0] - box[0]) <= BOX_NEAR and abs(rv["parked"][1] - box[2]) <= BOX_NEAR, (NAMES[entry], rv["parked"], box)
    assert rv["yaw"] == 0x8000 and nm["yaw"] == 0, (NAMES[entry], rv["yaw"], nm["yaw"])
    assert rv["parked"] == nm["parked"], (NAMES[entry], rv["parked"], nm["parked"])                 # the one box
    assert rv["granted"] == nm["granted"] >= 1 and rv["stops_after"] == rv["granted"] - 1 and nm["stops_after"] == nm["granted"] - 1
    assert rv["states"] == nm["states"] and rv["crew"] == nm["crew"] >= 4, (NAMES[entry], rv["states"], nm["states"], rv["crew"], nm["crew"])
    assert len(rv["states"]) == 4 and rv["work"] == nm["work"] >= STOP_FRAMES_MIN, (NAMES[entry], rv["work"], nm["work"])
    assert abs(rv["frames"] - nm["frames"]) <= nm["frames"] / 5, (NAMES[entry], rv["frames"], nm["frames"])
    assert rv["lap_end"] > rv["lap_before"] and rv["moved"] > 50, (NAMES[entry], rv["lap_before"], rv["lap_end"], rv["moved"])
    lines, writes = parse_hudrows_log(rv["wd"] / "rows.txt")
    first, release = rv["span"]
    racing = [l for l in lines if l.tag in ("race", "lap")]
    assert any(l.frame < first for l in racing) and any(first < l.frame < release for l in racing) and any(l.frame > release for l in racing), \
        (NAMES[entry], [l.frame for l in racing], first, release)
    last = WORD_LAST[entry]
    for l in racing:
        assert _text(l.rows, 46, last + 1 - len(REVERSE_TEXT), last) == (REVERSE_TEXT.decode(), {RED}), (NAMES[entry], l.frame)
        assert l.rows[44][19:] == racing[0].rows[44][19:] and l.rows[45][19:] == racing[0].rows[45][19:], (NAMES[entry], l.frame)
    assert writes[1] == 0, (NAMES[entry], writes)


def test_bay_bridge_has_no_pit_lane_in_either_direction(romset_zip, saturn_cue):
    """Bay Bridge has no pit lane in the game (no pit quad in its record, no quad flagged as lane), so its variant has none."""
    from vrtools.arcade.tencourse import FLAG_PIT_LANE, original_reverse_pit
    out, _ = _seven(romset_zip, saturn_cue)
    e = decode_directory(out)[1]
    assert e.pit_quad is None and e.reverse.entry.pit_quad is None and original_reverse_pit(RomSet.from_zip(romset_zip), 1) is None
    assert not any(s.flag == FLAG_PIT_LANE for s in segments(out, course_entry_at(out, e.bank, e.header_base)))


def _end(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """A one-lap race with the clock held (race_end.lua) and what follows it to the attract, write taps on the battery RAM's
    ranking area from the race load on: (W lines as (frame, pc, address), the modes after the race in order)."""
    from vrtools.mame.runner import LUA_DIR
    lo, hi = BATTERY_RANKING
    wd = _mame(tmp_path_factory, romset_zip, saturn_cue, f"end{entry}{'r' if reverse else 'n'}", entry, reverse, seconds=260,
               env={"VR_EXTRA_LUA": str(LUA_DIR / "race_end.lua"), "VR_END_LOG": "{wd}/end.txt", "VR_END_TABLE": f"{lo:x}-{hi:x}",
                    "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"})
    load, modes, writes = None, [], []
    for row in open(wd / "end.txt"):
        tag, *f = row.split()
        if tag == "L" and load is None:
            load = int(f[0])
        elif tag == "M":
            modes.append((int(f[0]), int(f[1], 16)))
        elif tag == "W":
            writes.append((int(f[0]), int(f[1], 16), int(f[2], 16)))
    assert load is not None
    after = [m for fr, m in modes if fr >= load]
    end = next(k for k, m in enumerate(after) if not 0x11 <= m <= 0x14)
    seq = []
    for m in after[end:]:
        if not seq or seq[-1] != m:
            seq.append(m)
        if m == 0x02:
            break
    return writes, seq, wd


def _record_spans():
    """Every best-time table and slot word of the battery RAM (ranking.py): the three originals' tables and slots, the seven
    converted courses' tables and the ten slot words, the seven reverse tables, their slots and the tag; Phase 35: the
    originals' three reverse tables and their tag (their slots are NEW_SLOTS' first three words)."""
    from vrtools.arcade.ranking import (NEW_SLOTS, NEW_TABLES, ORIG_SLOTS, ORIG_TABLES as ORIGS, REVERSE_SLOTS, REVERSE_TABLES, REVERSE_TAG,
                                        SHORT_ENTRIES, TABLE_BYTES)
    spans = [(t, t + TABLE_BYTES) for t in ORIGS + NEW_TABLES] + [(s, s + 4) for s in ORIG_SLOTS] + [(NEW_SLOTS, NEW_SLOTS + 40)]
    from vrtools.arcade.ranking import ORIG_REVERSE_TABLES, ORIG_TAG
    spans += [(t, t + 24 * SHORT_ENTRIES) for t in ORIG_REVERSE_TABLES] + [(ORIG_TAG, ORIG_TAG + 4)]
    return spans + [(t, t + 24 * SHORT_ENTRIES) for t in REVERSE_TABLES] + [(REVERSE_SLOTS, REVERSE_SLOTS + 28), (REVERSE_TAG, REVERSE_TAG + 4)]


def test_a_normal_race_on_an_original_still_records(tmp_path_factory, romset_zip, saturn_cue):
    """A one-lap race on Big Forest in the normal direction writes its own table (0x40e480..) and no other original's, and
    reaches the name entry. (Until Phase 35 the control of a test that a reverse race on an original records nothing; that
    race now records in its own reverse table: tests/test_reverse_times.py.)"""
    writes, seq, _ = _end(tmp_path_factory, romset_zip, saturn_cue, 0, False)
    table = ORIG_TABLES[0]
    hit = [w for w in writes if table <= w[2] < table + 0x240]
    print("END normal BIG FOREST modes", [hex(m) for m in seq], "writes", len(writes), "in its table", len(hit))
    assert NAME_ENTRY in seq and hit, ([hex(m) for m in seq], len(writes))
    assert not [w for w in writes if any(t <= w[2] < t + 0x240 for k, t in ORIG_TABLES.items() if k != 0)]
    assert any(lo <= w[2] < hi for w in writes for lo, hi in _record_spans())            # the spans catch a record


SAME = [(e, None) for e in range(10)] + [(0, "grandprix"), (6, "reverse")]           # stage 2: all ten in the normal direction
GRAND_PRIX = "40dca3=1,501105=1"        # the test menu's GAME MODE: GRANDPRIX (battery 0x40dca3, copied to 0x501105 at 0xfe1b12)


@pytest.mark.parametrize("entry,how", SAME, ids=[f"entry{e}{'_' + h if h else ''}" for e, h in SAME])
def test_the_normal_game_is_the_set_before_pass_for_pass(tmp_path_factory, romset_zip, saturn_cue, entry, how):
    """SAME_SECONDS of a race on the set without the originals' variants (the set before Phase 33: main's bytes) under the
    autopilot, its wheel and pedal recorded; the same race on the session's set fed those inputs frame for frame (input_tape.lua),
    from the same battery RAM: the game's state at the end of every logic pass (pass_state.lua: the clock and sixteen cars' x, z,
    road point, speed and lap) is identical over the whole run. All ten courses in the normal direction (the three originals: on the session's
    set the race passes through the COURSE DIRECTION screen, answered NORMAL, and loads on the same frame); Big Forest with the
    operator's GAME MODE set to GRANDPRIX (on a single cabinet: the 20-lap race needs the link, where the screen is not shown);
    Metropolis in reverse as well (a converted course: its records lie where they were, its reverse race blob 192 bytes
    higher)."""
    from vrtools.mame.framerate import parse_pass_log
    from vrtools.mame.runner import LUA_DIR, run_mame
    from tests.test_race_build import _drive_line
    _booted(tmp_path_factory, romset_zip, saturn_cue)
    reverse = how == "reverse"
    line = _drive_line(_seven(romset_zip, saturn_cue)[1][entry - 3]) if entry >= 3 else None
    extra = {"VR_PASS_LOG": "{wd}/pass.txt", "VR_INPUT_LOG": "{wd}/tape.txt", **({"VR_POKE": GRAND_PRIX} if how == "grandprix" else {})}
    tag = f"same{entry}{how or ''}"
    old = _mame(tmp_path_factory, romset_zip, saturn_cue, tag + "_before", entry, reverse, seconds=SAME_SECONDS, plain=True, line=line,
                env=extra, nvram=_RUNS["nvram"])
    new = _mame(tmp_path_factory, romset_zip, saturn_cue, tag + "_set", entry, reverse, seconds=SAME_SECONDS, line=line,
                env={**extra, "VR_INPUT_REPLAY": str(old / "tape.txt")}, nvram=_RUNS["nvram"])
    ta, tb = (new / "tape.txt").read_text().splitlines(), (old / "tape.txt").read_text().splitlines()
    assert len(ta) > 3000 and ta == tb, (entry, how, "the replay did not feed the recorded inputs", len(ta), len(tb))
    a, b = parse_pass_log(new / "pass.txt"), parse_pass_log(old / "pass.txt")
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    print("SAME", entry, how, "passes", len(a), len(b), "first difference", first)
    assert len(a) > 3000 and len(a) == len(b) and first is None, (entry, how, len(a), len(b), first, a[first][:120] if first is not None else "")
    if how == "grandprix":                                           # the setting reached the game in both runs
        for wd in (old, new):
            ram = sorted(wd.glob("trace.log.ram.*.bin"), key=lambda p: int(p.name.split(".")[-2]))[2].read_bytes()
            assert ram[0x501105 - 0x500000] == 1, wd


# ---- fix wave (review C1): an original's picture on the COURSE DIRECTION screen ----
# Pascal, 16 Nov, on out/p33play2: "i think bay bridge work but the colors in the track select looks bugged with ping
# highlighted on the track". An original's select picture is two maps, B (the terrain, see-through in places) over A (the water,
# the track, the name); the direction screen drew B alone on the back layer (origpic.py).

PICTURE_AT = {"select": lambda slot: (8, 32 + 152 * slot), "direction": lambda side: (32, 72 + 224 * side)}    # (y, x) on the screen
FRAME_YELLOW = (255, 255, 0)            # the cursor frame (a polygon over the tiles): it covers a picture's outer pixels
FRAME_BAND = 8                          # ... within this many pixels of the picture's edge
SCREEN_SNAPS = (1100, 1300, 1320)       # the course select (no lock yet), the direction screen drawn (the choice shown), the lock look
                                        # (weather stage 1: autoplay locks the direction on 1302, the lock look held to 1336)


def _rgb(words):
    """Colour words as MAME shows them (5 bits a gun, red lowest; 0..255 by v << 3 | v >> 2)."""
    v = np.stack([(words >> s) & 31 for s in (0, 5, 10)], -1).astype(np.uint8)
    return (v << 3) | (v >> 2)


def _picture_data(out):
    """Per art, its direction-screen data as installed: (the draw piece's address, its size, origpic.picture_data's info, the
    lock piece's address, its size), the bytes of both checked."""
    from vrtools.arcade import origpic
    from vrtools.arcade.tencourse import origpic_address
    table = struct.unpack_from("<6I", out.program, origpic.table_address(origpic_address()) - V60_PROGRAM)
    res = {}
    for art in range(3):
        draw_at, lock_at = table[art], table[3 + art]
        draw, lock, info = origpic.picture_data(out, art, draw_at, lock_at)
        for at, blob in ((draw_at, draw), (lock_at, lock)):
            rom, base = (out.boot, V60_BOOT) if at >= V60_BOOT else (out.data, 0x100000) if at < 0x200000 else (out.program, V60_PROGRAM)
            assert rom[at - base:at - base + len(blob)] == blob, (art, hex(at))
        res[art] = (draw_at, len(draw), info, lock_at, len(lock))
    return res


def test_the_arrows_cells_draw_the_arrow_over_an_originals_picture(romset_zip, saturn_cue):
    """The data `odraw` draws from, decoded from the built set: for each original and each side the 12 x 12 square's tile words
    are, in the cells the arrow has a pixel in, a character of the side's own blocks (at most two blocks, each with a palette
    of at most 15 colours) and elsewhere B's own word in the side's slot; and rendered over the A map in each of the three looks
    (normal, chosen, grey) the square is, pixel for pixel, the course select's picture (B over A from the stock ROM's maps,
    characters and palettes) with the arrow's pixels in the arrow's colours over it. The right side's A map is the game's map
    on the next art's characters."""
    from vrtools.arcade import dirgfx, origpic
    from vrtools.arcade.panel import ORIGINAL_PANELS, decode_panel
    from vrtools.arcade.select import SLOT_CHAR
    out, _ = _seven(romset_zip, saturn_cue)
    stock = RomSet.from_zip(romset_zip)
    data = _picture_data(out)
    read = lambda at, n: (out.boot[at - V60_BOOT:at - V60_BOOT + n] if at >= V60_BOOT else out.data[at - 0x100000:at - 0x100000 + n])
    for art in range(3):
        at, size, info, lock_at, lock_size = data[art]
        assert lock_at >= V60_BOOT                                                    # the lock piece: always mapped
        ly = origpic.layers(stock, art)
        a = decode_panel(stock, ORIGINAL_PANELS[art][0])
        hdr = struct.unpack("<HHII", read(info["a_map"], 12))
        assert hdr == (origpic.A_HOME[(art + 1) % 3], 0, 21, 16) and read(info["a_map"] + 12, 336) == bytes(a.tiles), art
        for side in range(2):
            blocks = info["blocks"][side]
            assert 1 <= len(blocks) <= origpic.RING_PALETTES and blocks == origpic.ring_blocks(art, side)[:len(blocks)]
            words = struct.unpack("<144H", read(info["ring"][side]["map"] + 12, 288))
            arrow = dirgfx.arrow_bitmap(origpic.SIDE_CLOCKWISE[side])
            slot = 0x8000 | SLOT_CHAR[origpic.SIDE_SLOT[side]]
            for look in origpic.LOOKS:
                want = origpic.expected_picture(ly, look, side)
                plain = origpic.expected_picture(ly, look)
                for k, w in enumerate(words):
                    r, c = divmod(k, 12)
                    cell = (r + origpic.BOX[0]) * 16 + c + origpic.BOX[1]
                    y0, x0 = 8 * (r + origpic.BOX[0]), 8 * (c + origpic.BOX[1])
                    in_ring = bool(arrow[8 * r:8 * r + 8, 8 * c:8 * c + 8].any())
                    if not in_ring:
                        assert w == slot + ly.b_local[cell], (art, side, r, c, hex(w))
                        continue
                    g = next(i for i, b in enumerate(blocks) if (0x8000 | b) <= w < (0x8000 | b) + dirgfx.BLOCK_CHARS)
                    px = dirgfx.char_pixels(read(info["ring"][side]["chars"][g] + 32 * (w - (0x8000 | blocks[g])), 32))
                    pal = struct.unpack("<16H", read(info["ring"][side]["looks"][g][look], 32))
                    got = np.where(px != 0, np.array(pal, np.uint16)[px], np.where(ly.a_pixels[cell] != 0, [[ly.colour("a", cell, int(v), look) if v else 0
                                                                                                           for v in row] for row in ly.a_pixels[cell]], 0))
                    assert (got == want[y0:y0 + 8, x0:x0 + 8]).all(), (art, side, look, r, c)
                assert ((want != plain) == (np.pad(arrow != 0, ((8 * origpic.BOX[0], 168 - 96 - 8 * origpic.BOX[0]),
                                                               (8 * origpic.BOX[1], 128 - 96 - 8 * origpic.BOX[1]))) & (want != plain))).all()
        print("PICTURE DATA art", art, "at", hex(at), size, "bytes; ring blocks", [[hex(b) for b in s] for s in info["blocks"]])


def test_the_picture_block_and_the_lock_site(romset_zip, saturn_cue):
    """`olock`, `orows` and `osel` lie in their own block right below the originals' reverse block, with the six data
    addresses in the block's last 24 bytes; the boot ROM's LOCK_SITE calls `olock` where the set without the originals'
    variants calls `dirlock`; the draw pieces lie in the boot ROM's erased run (BOOT_FREE) or in erased bank 0, the lock
    pieces (read on the lock's logic frame) all in the boot ROM, which no bank switch unmaps. (Weather stage 1: on the set
    without the weather screen, which rewrites `olock`'s two handler immediates: tests/test_weather_screen.py.)"""
    from vrtools.arcade import origpic
    from vrtools.arcade.dirscreen import LOCK_SITE
    from vrtools.arcade.tencourse import BOOT_FREE, origpic_address
    from tests.test_weather_dry import _seven_dry
    out, _ = _seven_dry(romset_zip, saturn_cue)
    plain, _ = _seven_plain(romset_zip, saturn_cue)
    lay = directory_layout()
    base = origpic_address()
    assert base + origpic.BLOCK_BYTES == origrev_address() and base % 16 == 0
    code = origpic.origpic_routines(base, lay)
    image = b"".join(code.values())
    assert list(code) == ["olock", "orows", "osel"] and len(image) <= origpic.BLOCK_BYTES - 24
    assert out.program[base - V60_PROGRAM:base - V60_PROGRAM + len(image)] == image
    assert all(x == 0xFF for x in plain.program[base - V60_PROGRAM:base - V60_PROGRAM + origpic.BLOCK_BYTES])
    site = lambda rs: rs.boot[LOCK_SITE - V60_BOOT:LOCK_SITE - V60_BOOT + 9]
    assert site(plain) == origpic.lock_site(lay["dirlock"]) and site(out) == origpic.lock_site(base) != site(plain)
    for art, (a, size, _, lock_at, lock_size) in _picture_data(out).items():
        assert (BOOT_FREE[0] <= a and a + size <= BOOT_FREE[1]) or (0x100000 <= a and a + size <= 0x200000), (art, hex(a))
        assert BOOT_FREE[0] <= lock_at and lock_at + lock_size <= BOOT_FREE[1], (art, hex(lock_at))
        for at, n in ((a, size), (lock_at, lock_size)):
            rom, off = (plain.boot, at - V60_BOOT) if at >= V60_BOOT else (plain.data, at - 0x100000)
            assert all(x == 0xFF for x in rom[off:off + n]), (art, hex(at))


def test_olock_runs_dirlocks_instruction_count_on_a_converted_courses_paths():
    """Why a converted course's frames are main's (origpic.py): MAME's V60 charges every instruction alike, and `olock` runs as
    many as `dirlock` on each path a converted course takes. Counted here from the two routines' own listings (no ROM): the
    path that opens the screen (17), and the three that end in the original instruction (linked play 6, the direction lock's
    own pass 8, an entry without a variant 12)."""
    pytest.importorskip("vrtools.arcade.disasm")
    from vrtools.arcade import disasm, origpic
    from vrtools.arcade.dirscreen import dirscreen_routines, placeholders
    lay = placeholders(directory_layout(), 0x100000)
    try:
        new = disasm.listing_bytes(origpic.origpic_routines(0x28F600, lay)["olock"], 0x28F600)
        old = disasm.listing_bytes(dirscreen_routines(directory_layout()["dirclear"], lay)["dirlock"], directory_layout()["dirlock"])
    except disasm.DisasmError as e:
        pytest.skip(f"needs unidasm, run tools/build-mame.sh ({e})")

    def paths(lines):
        """The instruction count of each path from the first instruction to an `rsr`, by the taken branches (in order)."""
        at = {l.addr: i for i, l in enumerate(lines)}
        out = {}

        def walk(i, n, taken):
            while True:
                text = lines[i].text
                n += 1
                if text.startswith("rsr"):
                    out[taken] = n
                    return
                op = text.split()[0]
                if op in ("be", "bne", "bge"):
                    walk(at[int(text.split()[1], 16)], n, taken + (len([l for l in lines[:i + 1] if l.text.split()[0] in ("be", "bne", "bge")]),))
                elif op == "br":
                    i = at[int(text.split()[1], 16)]
                    continue
                i += 1
        walk(0, 0, ())
        return out
    a, b = paths(old), paths(new)
    print("PATHS dirlock", a, "olock", b)
    assert a == {(): 17, (1,): 6, (2,): 8, (3,): 12}, a
    assert b[(4,)] == 17 and b[(1,)] == 6 and b[(2,)] == 8 and b[(3,)] == 12, b       # (4,): the entry's compare taken, a converted course
    assert b[()] == 18                                                                # an original: one `br` more


def _crop(im, where, k):
    y, x = PICTURE_AT[where](k)
    return im[y:y + 168, x:x + 128]


def _framed(*crops):
    """The pixels the cursor frame may cover: frame yellow in any of `crops`, within FRAME_BAND of the picture's edge."""
    band = np.ones((168, 128), bool)
    band[FRAME_BAND:-FRAME_BAND, FRAME_BAND:-FRAME_BAND] = False
    return band & np.any([(c == FRAME_YELLOW).all(-1) for c in crops], 0)


@pytest.mark.parametrize("entry", [0, 1, 2])
@pytest.mark.parametrize("reverse", [False, True])
def test_an_originals_picture_on_the_direction_screen_is_the_course_selects(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """Review C1, on the shipped set, screen pixels (MAME snapshots): the course select shows the original's picture as the
    stock ROM's two maps give it (B over A, the normal palettes); the direction screen, drawn, shows that picture on BOTH sides,
    pixel for pixel, with the white arrow's pixels over the left and the red arrow's over the right (weather stage 1: the side
    shown in the normal look, the other in the grey look, A, B and the ring all grey; before, both in the normal look); after the
    lock the chosen side shows it in the game's chosen palettes and the other in the game's grey ones (the START tables), the arrows as they
    were. Every pixel of the 128 x 168 picture is compared but those the yellow cursor frame covers at its edge. This is also
    the lock look of an original on the shipped set (tests/test_race_build.py's course-select lock look is dumped on the set
    without the originals' variants: with them an original's lock opens this screen)."""
    from PIL import Image
    from vrtools.arcade import dirgfx, origpic
    from vrtools.arcade.select import first_of
    from tests.test_dirscreen_build import _WD, _screen
    label = f"origpic{entry}{'r' if reverse else 'n'}"
    lines, _ = _screen(tmp_path_factory, romset_zip, saturn_cue, label, entry, reverse=reverse, env={"VR_SNAPS": ",".join(map(str, SCREEN_SNAPS)), "VR_SNAPS_AFTER_START": ""})
    snaps = sorted(_WD[label].rglob("*.png"))
    assert len(snaps) >= len(SCREEN_SNAPS), snaps                                 # (autoplay.lua adds one after the race's start)
    sel, drawn, locked = (np.array(Image.open(p).convert("RGB")) for p in snaps[:len(SCREEN_SNAPS)])
    at = lambda frame: [l for l in lines if l.frame <= frame][-1]                # the log has a line where a field changed
    from vrtools.arcade.weather.screen import HOLDING
    assert at(SCREEN_SNAPS[1]).phase == 1 and at(SCREEN_SNAPS[1]).shown == int(reverse) and at(SCREEN_SNAPS[2]).phase == HOLDING, (at(SCREEN_SNAPS[1]), at(SCREEN_SNAPS[2]))
    assert at(SCREEN_SNAPS[2]).flag == int(reverse)
    ly = origpic.layers(RomSet.from_zip(romset_zip), entry)
    normal = origpic.expected_picture(ly)
    assert (normal != 0).all()                                                     # every pixel has a colour of A or B
    s = _crop(sel, "select", entry - first_of(entry))
    bad = (s != _rgb(normal)).any(-1) & ~_framed(s)
    assert not bad.any(), (NAMES[entry], "the course select", int(bad.sum()))
    for side in range(2):
        arrow = np.zeros((168, 128), bool)
        arrow[8 * origpic.BOX[0]:8 * origpic.BOX[0] + 96, 8 * origpic.BOX[1]:8 * origpic.BOX[1] + 96] = dirgfx.arrow_bitmap(origpic.SIDE_CLOCKWISE[side]) != 0
        d = _crop(drawn, "direction", side)
        frame = _framed(s, d)
        shown = side == int(reverse)
        if shown:
            bad = (d != s).any(-1) & ~arrow & ~frame                               # the course select's own pixels
            assert not bad.any(), (NAMES[entry], side, "drawn against the course select", int(bad.sum()))
        bad = (d != _rgb(origpic.expected_picture(ly, "normal" if shown else "grey", side))).any(-1) & ~frame
        assert not bad.any(), (NAMES[entry], side, "drawn", int(bad.sum()))
        look = "chosen" if side == int(reverse) else "grey"
        k = _crop(locked, "direction", side)
        bad = (k != _rgb(origpic.expected_picture(ly, look, side))).any(-1) & ~_framed(k)
        assert not bad.any(), (NAMES[entry], side, look, int(bad.sum()))
        assert int(arrow.sum()) > 2000 and int(_framed(s, d, k).sum()) < 1200


SELECT_CHARS = range(0x3000, 0x3780)    # the select pictures' characters: the three arts' A blocks, the three slots' blocks
SELECT_PALETTES = range(0x60, 0x6F)


def test_the_course_select_is_the_same_after_an_originals_direction_screen_and_race(tmp_path_factory, romset_zip, saturn_cue):
    """The direction screen of an original writes character blocks and palettes of the course select (the other arts' A blocks,
    the middle slot's, origpic.py). A one-lap race on Acropolis (race_end.lua; the screen answered NORMAL), then a second game
    on the same wheel, on the set and on the set without the originals' variants (main's bytes, where an original has no
    direction screen); 300 frames into each course select:
    - the first game's select on the set is the other set's, byte for byte: the pictures' characters (SELECT_CHARS), their
      palettes (SELECT_PALETTES), the two tile layers' picture rows;
    - the SECOND game's select on the set is the other set's second, byte for byte, the same three: what the direction screen
      wrote is gone, and what a race leaves in the characters no picture uses is what it leaves on main;
    - on the set, what the second select SHOWS in the picture rows (each cell's tile word, its character's 32 bytes and its
      palette) is what the first shows."""
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.mame.runner import LUA_DIR
    env = {"VR_EXTRA_LUA": str(LUA_DIR / "race_end.lua"), "VR_END_LOG": "{wd}/end.txt", "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}",
           "VR_SELECT_DIR": "{wd}", "VR_SELECT_DUMP_SELECT": "300", "VR_END_NEXT": f"{WHEEL_FOR_ENTRY[2]}:0"}
    runs = {plain: _mame(tmp_path_factory, romset_zip, saturn_cue, f"select_twice{'_plain' if plain else ''}", 2, False, seconds=300, plain=plain, env=env)
            for plain in (False, True)}

    def selects(wd):
        """(the first game's, the second game's) dump 300 frames into its course select: (frame, char, pal, tile)."""
        loads = [int(l.split()[1]) for l in open(wd / "end.txt") if l.startswith("L ")]
        assert len(loads) == 2, loads
        out = []
        for lo, hi in ((0, loads[0]), (loads[0], loads[1])):
            files = [f for f in wd.glob("*_2_char.bin") if lo < int(f.name.split("_")[0]) < hi]
            assert files, (wd, lo, hi)
            f = max(files, key=lambda f: int(f.name.split("_")[0]))            # the last before the lock: the dump 300 frames in
            out.append((int(f.name.split("_")[0]), f.read_bytes(), f.with_name(f.name.replace("_char", "_pal")).read_bytes(),
                        f.with_name(f.name.replace("_char", "_tile")).read_bytes()))
        return out

    def parts(d):
        _, char, pal, tile = d
        rows = b"".join(tile[layer * 0x2000 + 0x80 * r:layer * 0x2000 + 0x80 * r + 0x80] for layer in (0, 2) for r in range(1, 22))
        return (char[32 * SELECT_CHARS[0]:32 * SELECT_CHARS[-1] + 32], pal[32 * SELECT_PALETTES[0]:32 * SELECT_PALETTES[-1] + 32], rows)

    def shown(d):
        _, char, pal, tile = d
        out = []
        for layer in (0, 2):
            for r in range(1, 22):
                for c in range(64):
                    w = struct.unpack_from("<H", tile, layer * 0x2000 + 0x80 * r + 2 * c)[0]
                    code = w & 0x7FFF
                    out.append((w, char[32 * code:32 * code + 32], pal[32 * (code >> 7):32 * (code >> 7) + 32]))
        return out
    new, old = selects(runs[False]), selects(runs[True])
    print("SELECT dumps", [d[0] for d in new], [d[0] for d in old])
    for game in range(2):
        for k, what in enumerate(("characters", "palettes", "tile rows")):
            assert parts(new[game])[k] == parts(old[game])[k], (f"game {game + 1}'s select against the set without the variants", what)
    assert shown(new[1]) == shown(new[0])


# ---- second fix wave: the lock's transition, frame by frame; the put-back in reverse ----

TRANSITION = range(1196, 1300)          # every video frame from before the course lock (1202) until the screen is drawn
LOCK_TO_LOAD = range(1196, 1612)        # ... and to the race load, for a converted course against the set without the variants


def _snap_run(tmp_path_factory, romset_zip, saturn_cue, label, entry, reverse, frames, plain=False, dry=False):
    """The snapshots (RGB arrays, in `frames`' order) of a run of `entry` on the session's set (`dry`: without the weather screen)
    or the set without the variants."""
    from PIL import Image
    wd = _mame(tmp_path_factory, romset_zip, saturn_cue, label, entry, reverse, seconds=30, plain=plain, dry=dry,
               env={"VR_SNAPS": ",".join(map(str, frames)), "VR_SNAPS_AFTER_START": ""})
    snaps = sorted(wd.rglob("*.png"))[:len(frames)]
    assert len(snaps) == len(frames), (label, len(snaps))
    return [np.array(Image.open(p).convert("RGB")) for p in snaps]


@pytest.mark.parametrize("entry,reverse", [(0, False), (1, False), (2, False), (1, True)])
def test_no_frame_of_an_originals_lock_shows_a_half_drawn_picture(tmp_path_factory, romset_zip, saturn_cue, entry, reverse):
    """Second review, I-A: at an original's course lock one video frame showed the select pictures' back maps alone, in the
    wrong colours (`dirdraw` clears the front layer before it redraws the back one, across a frame's end). Every frame of
    TRANSITION is read: up to the first frame in which a select slot's picture has changed, each of the three slots shows what
    it showed before the lock, pixel for pixel (but under the cursor frame); from that frame on, each direction picture's place shows either none of the
    picture (the place is what the screen shows there with no picture: the checker) or the whole picture of the stock ROM's
    two maps (weather stage 1: in the normal look or the grey one, the side not shown greying while the direction is chosen, or
    on the frame its palettes change each pixel in one of the two); and both pictures are whole by the last frame."""
    from vrtools.arcade import origpic
    frames = _snap_run(tmp_path_factory, romset_zip, saturn_cue, f"transition{entry}{'r' if reverse else ''}", entry, reverse, list(TRANSITION))
    # (the course lock is at frame 1202 whatever the answer; `reverse`: the wheel is turned for REVERSE from frame 1300, after
    # TRANSITION. The second lock, at 1402, clears nothing: the lock look is palette words, read by
    # test_an_originals_picture_on_the_direction_screen_is_the_course_selects.)
    ly = origpic.layers(RomSet.from_zip(romset_zip), entry)
    whole = _rgb(origpic.expected_picture(ly))
    grey = _rgb(origpic.expected_picture(ly, "grey"))
    first = frames[0]
    slots = lambda im: [_crop(im, "select", k) for k in range(3)]
    inner = lambda im: [c[FRAME_BAND:-FRAME_BAND, FRAME_BAND:-FRAME_BAND] for c in slots(im)]
    cleared = next(i for i, f in enumerate(frames) if not all((a == b).all() for a, b in zip(inner(f), inner(first))))
    assert 4 <= cleared <= 20, cleared                                           # (the lock is at frame 1202)
    for i in range(cleared):
        for k, (a, b) in enumerate(zip(slots(frames[i]), slots(first))):
            bad = (a != b).any(-1) & ~_framed(a, b)
            assert not bad.any(), (NAMES[entry], "before the clear", TRANSITION[i], k, int(bad.sum()))
    empty = [_crop(frames[cleared + 1], "direction", side) for side in range(2)] # the checker under each picture's place: the frame
                                                                                 # after the first changed one (the pictures come later)
    states = []
    for i in range(cleared, len(frames)):
        row = []
        for side in range(2):
            c = _crop(frames[i], "direction", side)
            ring = np.zeros((168, 128), bool)
            ring[8 * origpic.BOX[0]:8 * origpic.BOX[0] + 96, 8 * origpic.BOX[1]:8 * origpic.BOX[1] + 96] = True      # the arrow's square
            frame = _framed(c)
            if not ((c != empty[side]).any(-1) & ~frame).any():
                row.append("none")
            elif not ((c != whole).any(-1) & (c != grey).any(-1) & ~ring & ~frame).any():
                row.append("whole")
            else:
                row.append("PART")
        states.append(tuple(row))
    print("TRANSITION", NAMES[entry], "cleared at", TRANSITION[cleared], [(TRANSITION[cleared + i], s) for i, s in enumerate(states) if i == 0 or s != states[i - 1]])
    assert all("PART" not in s for s in states), [(TRANSITION[cleared + i], s) for i, s in enumerate(states) if "PART" in s][:6]
    assert states[-1] == ("whole", "whole")


def test_a_converted_courses_lock_frames_are_the_set_befores(tmp_path_factory, romset_zip, saturn_cue):
    """Second review, minor 5: Diablo Canyon answered REVERSE, every video frame from before the course lock to the race load
    (LOCK_TO_LOAD, 416 frames), on the session's set and on the set without the originals' variants: the same pixels in every
    frame. (`olock` in `dirlock`'s place costs a converted course no instruction more.) Weather stage 1: the session's set is
    taken without the weather screen (`dry`), which changes these frames by design and is not what this compares; the weather
    set's own frames: tests/test_weather_screen.py."""
    new = _snap_run(tmp_path_factory, romset_zip, saturn_cue, "lockframes5", 5, True, list(LOCK_TO_LOAD), dry=True)
    old = _snap_run(tmp_path_factory, romset_zip, saturn_cue, "lockframes5_plain", 5, True, list(LOCK_TO_LOAD), plain=True)
    differ = [LOCK_TO_LOAD[i] for i, (a, b) in enumerate(zip(new, old)) if (a != b).any()]
    assert differ == [], differ[:10]
    assert len({f.tobytes() for f in new}) > 20                                   # the frames do change over the transition


NO_PUTBACK = {0: (60, 61), 1: (501, 509, 510, 511, 660, 661, 662), 2: (386, 394, 402, 410, 418, 426)}     # reverse_no_putback, pinned:
                                        # Bay Bridge's 660-662 before the fork's nose; its 509-511 on the stub the board row closes
PUTBACK_ANGLE_MAX = 45.0                # degrees between a reverse put-back pose and the reversed lap's direction there
OBJECT_CLEAR = 2.5                      # units between a put-back pose's first PUTBACK_CLEAR units and a spawned object


def test_no_reverse_put_back_on_an_original_faces_a_wall(romset_zip, saturn_cue):
    """Pascal, 16 Nov, Bay Bridge in reverse: "it did put me back on bay bridge after a while but i ended up right in an
    obstacle." The game puts a car back on the centre of the last quad it remembered, along the quad's direction (0xfebc94);
    in reverse the last quad before Bay Bridge's fork faces the nose of the fork's divider, four units ahead. On the built
    set, for each original's REVERSE variant: its segment array is the game's read backwards but for the flag bit
    FLAG_NO_PUTBACK on the quads NO_PUTBACK (the game then never remembers them); every quad a put-back can still choose
    (the game's rule, 0xfebcbf: none of the flag's bits 0x3c; so the pit lanes' 0x42 and Bay Bridge's 0x02 quads too) has PUTBACK_CLEAR units of tarmac or kerb straight ahead of its reverse pose, on three
    lines; on the lap's own road (flag bit 0) the pose is within PUTBACK_ANGLE_MAX of the reversed lap's direction at its road
    point (Bay Bridge's side-road quads, flag 0x02, lie along the side road: up to 108 degrees off the lap they are credited
    to, in the normal direction as well); and no object of the
    variant's spawn list lies within OBJECT_CLEAR of those first PUTBACK_CLEAR units. The NORMAL entries' segments are the
    stock ROM's, and the normal direction has such spots of its own (printed: the arcade's, not touched)."""
    import math
    from vrtools.arcade.spawn import CHECKPOINT_GANTRIES, START_GANTRY, decode_spawn_list
    from vrtools.arcade.tencourse import FLAG_NO_PUTBACK, PUTBACK_CLEAR, putback_clear, reverse_no_putback
    from vrtools.arcade.tgp import decode_collision
    out, _ = _seven(romset_zip, saturn_cue)
    stock = RomSet.from_zip(romset_zip)
    d = decode_directory(out)
    for k in range(3):
        n, rv = d[k], d[k].reverse.entry
        ne = course_entry_at(stock, n.bank, n.header_base)
        game = segments(stock, ne)
        assert segments(out, course_entry_at(out, n.bank, n.header_base)) == game, NAMES[k]            # the normal race's flags
        mine = {s.index: s for s in segments(out, course_entry_at(out, rv.bank, rv.header_base))}
        marked = tuple(sorted(i for i, s in mine.items() if s.flag & FLAG_NO_PUTBACK and not next(g for g in game if g.index == i).flag & FLAG_NO_PUTBACK))
        assert marked == NO_PUTBACK[k] == reverse_no_putback(stock, k), (NAMES[k], marked)
        points = len(road_lines(stock, ne)[0])
        for g in game:
            want = g.flag | (FLAG_NO_PUTBACK if g.index in marked else 0)
            assert (mine[g.index].flag, mine[g.index].road_point) == (want, (points - g.road_point) % points), (NAMES[k], g.index)
        clear = putback_clear(stock, k, True)
        spots = [i for i, s in mine.items() if not s.flag & 0x3C]
        assert spots and all(i in clear for i in spots)
        worst = min(clear[i] for i in spots)
        assert worst >= PUTBACK_CLEAR, (NAMES[k], worst, [i for i in spots if clear[i] < PUTBACK_CLEAR][:8])
        quads = decode_collision(stock, k).quads
        line = road_lines(out, course_entry_at(out, rv.bank, rv.header_base))[0]
        objects = [(e.x, e.z) for e in decode_spawn_list(out, rv.spawn_table) if e.handler != START_GANTRY and e.handler not in CHECKPOINT_GANTRIES
                   and (e.x, e.z) != (0.0, 0.0)]
        off, near = 0.0, []
        for i in spots:
            q = quads[i]
            yaw = ((q.attr & 0xFFFF) + 0x8000) & 0xFFFF
            p = mine[i].road_point
            a, b = line[p], line[(p + 1) % len(line)]
            lap = (-math.atan2(b.x - a.x, b.z - a.z) / (2 * math.pi) * 65536) % 65536
            if mine[i].flag & 1:                                      # a quad of the lap's own road (a side road's or a pit lane's quad
                off = max(off, abs((yaw - lap + 0x8000) % 0x10000 - 0x8000) * 360 / 65536)      # lies along its own way, not the lap's)
            fx, fz = -math.sin(yaw / 65536 * 2 * math.pi), math.cos(yaw / 65536 * 2 * math.pi)
            for ox, oz in objects:
                t = (ox - q.centre[0]) * fx + (oz - q.centre[2]) * fz
                side = abs((ox - q.centre[0]) * -fz + (oz - q.centre[2]) * fx)
                if -OBJECT_CLEAR <= t <= PUTBACK_CLEAR and side < OBJECT_CLEAR:
                    near.append((i, round(ox, 1), round(oz, 1)))
        arcade = putback_clear(stock, k, False)
        print("PUT-BACK", NAMES[k], "reverse spots", len(spots), "least clear", worst, "marked", marked, "largest angle off the lap", round(off, 1),
              "objects on a pose's path", near[:4], "| NORMAL (the arcade's own): spots under", PUTBACK_CLEAR, sorted((v, i) for i, v in arcade.items() if v < PUTBACK_CLEAR))
        assert off <= PUTBACK_ANGLE_MAX and near == [], (NAMES[k], off, near[:6])


def test_a_put_back_before_bay_bridges_fork_in_reverse_has_room(tmp_path_factory, romset_zip, saturn_cue):
    """Pascal's run, by the test driver: Bay Bridge in reverse, the wheel held straight from the first metres (steer_at.lua),
    so the car runs straight on where the race road bends right and onto the fork's side arm, the off-course counter runs out
    and the game puts it back. The first set-down is on none of the marked quads: it lies before the fork (z above the nose's
    by PUTBACK_CLEAR or more; the set without the marks set the car down at z -110.6, four units from the nose at about
    -114), facing the reverse lap; and after it the car comes away and drives on round the lap."""
    from vrtools.arcade.tencourse import PUTBACK_CLEAR
    from vrtools.mame.runner import LUA_DIR, parse_race_log
    wd = _mame(tmp_path_factory, romset_zip, saturn_cue, "putback_bb", 1, True, seconds=80,
               env={"VR_HOLD_CLOCK": "1", "VR_EXTRA_LUA": str(LUA_DIR / "steer_at.lua"), "VR_STEER_AT": "-205.2:-20.0:128:640", "VR_STEER_LOG": "{wd}/steer.txt"})
    player, _ = parse_race_log(wd / "race.txt")
    back = next((i for i, (a, b) in enumerate(zip(player, player[1:])) if a.off_course >= 100 and b.off_course < a.off_course - 50), None)
    assert back is not None, "no put-back in the run"
    assert player[back].x < -188.0 and player[back].z < -150.0, (player[back].x, player[back].z)        # taken on the side arm
    glide = player[back + 1:back + 200]
    rest = max(glide, key=lambda p: p.z)                                          # the set-down: the glide's end, before the car drives on (-z)
    turn = abs(((rest.yaw - 0x8000 + 0x8000) % 0x10000) - 0x8000) * 360 / 65536
    print("PUT-BACK run: taken at", (round(player[back].x, 1), round(player[back].z, 1)), "set down at", (round(rest.x, 1), round(rest.z, 1)), "yaw off -z",
          round(turn, 1), "last", (round(player[-1].x, 1), round(player[-1].z, 1), player[-1].road_point))
    assert rest.z >= -114.0 + PUTBACK_CLEAR and abs(rest.x + 187.5) < 3.0, (rest.x, rest.z)
    assert turn <= 20.0, turn
    assert player[-1].road_point > 80 and abs(player[-1].z + 100) > 100, (player[-1].road_point, player[-1].x, player[-1].z)


def test_a_marked_quad_keeps_its_other_flag_bits():
    """`mark_no_putback` (no ROM): the mark is OR-ed in; a tunnel quad's 0x81 becomes 0x85, a pit lane's 0x42 becomes 0x46,
    an unmarked segment and every index and road point are untouched."""
    from vrtools.arcade.course import Segment
    from vrtools.arcade.tencourse import FLAG_NO_PUTBACK, mark_no_putback
    segs = [Segment(0, 5, 0x01), Segment(1, 6, 0x81), Segment(2, 7, 0x42), Segment(3, 8, 0x01), Segment(4, 9, 0x05)]
    out = mark_no_putback(segs, (1, 2, 3, 4))
    assert FLAG_NO_PUTBACK == 4 and [s.flag for s in out] == [0x01, 0x85, 0x46, 0x05, 0x05]
    assert [(s.index, s.road_point) for s in out] == [(s.index, s.road_point) for s in segs] and segs[1].flag == 0x81


def test_bay_bridges_own_tunnel_sounds_in_a_reverse_race(tmp_path_factory, romset_zip, saturn_cue):
    """Phase 37 (main) gave the converted courses the arcade's tunnel sound: bit 7 of the segment flag under the car, C201 when
    it comes on, C200 when it goes off. Bay Bridge's own tunnel (the game's flag 0x81 on quads 69-88) in a REVERSE race is a
    case neither phase tested: the variant's segment array is the game's read backwards, so the car comes onto quad 88 first.
    In the reverse race of RACE_SECONDS: the variant keeps 0x81 on exactly those twenty quads; the sound comes on as the car
    comes onto quad 88 and goes off as it comes onto quad 68, once a pass, each command within the queue's few frames of the
    change, and no other C2xx is sent."""
    from vrtools.mame.runner import SOUND_TUNNEL_OFF, SOUND_TUNNEL_ON, parse_sound_log
    from tests.test_tunnel_sound_build import BAY_QUADS, _commands_match_edges
    out, _ = _seven(romset_zip, saturn_cue)
    rv = decode_directory(out)[1].reverse.entry
    flagged = sorted(s.index for s in segments(out, course_entry_at(out, rv.bank, rv.header_base)) if s.flag & 0x80)
    assert flagged == list(range(BAY_QUADS[0], BAY_QUADS[1] + 1)), flagged
    log = parse_sound_log(_race(tmp_path_factory, romset_zip, saturn_cue, 1, True) / "sound.txt")
    edges = _commands_match_edges(log, "bay bridge reverse")
    print("TUNNEL reverse Bay Bridge edges", edges)
    assert edges and len(edges) % 2 == 0, edges
    assert [(bit, q) for _, bit, q, _ in edges] == [(1, BAY_QUADS[1]), (0, BAY_QUADS[0] - 1)] * (len(edges) // 2), edges
    assert {c for _, c in log.commands if c >> 8 == 0xC2} == {SOUND_TUNNEL_ON, SOUND_TUNNEL_OFF}
