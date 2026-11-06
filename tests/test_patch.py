import random
import struct
import zipfile

import pytest

from vrtools.arcade.patch import Allocator, PatchError, patch_course_tiles, write_colour_entries, write_polygons, write_tile_record
from vrtools.arcade.polyrom import ObjectLayout
from vrtools.arcade.romset import REQUIRED_FILES, RomSet, RomSetError


def _files(distinct=False):
    """Fake lane files. distinct=True gives every file its own random bytes so a lane mix-up is visible."""
    rng = random.Random(7)
    files = {name: (rng.randbytes(0x80000) if distinct else bytes(0x80000)) for name in REQUIRED_FILES}
    for n in ("mpr-14890.26", "mpr-14891.27", "mpr-14892.28", "mpr-14893.29", "mpr-14894.30", "mpr-14895.31", "mpr-14896.32", "mpr-14897.33"):
        files[n] = rng.randbytes(0x200000) if distinct else b"\xff" * 0x200000
    for n in ("epr-14878a.4", "epr-14879a.5"):
        files[n] = bytes(0x20000)
    files["315-5573.bin"] = bytes(0x2000)
    return files


def test_allocator_first_fit_and_shortfall():
    a = Allocator([(100, 50), (1000, 500)])
    assert a.alloc(40) == 100 and a.alloc(40) == 1000 and a.alloc(8, align=16) == 1040
    with pytest.raises(PatchError, match="short by"):
        a.alloc(10000)


def test_allocations_never_overlap_or_leave_holes():
    rng = random.Random(3)
    holes = [(0, 4096), (10000, 8192)]
    a = Allocator(holes)
    got = []
    for _ in range(200):
        n = rng.randint(1, 200)
        try:
            got.append((a.alloc(n, align=4), n))
        except PatchError:
            break
    got.sort()
    for (s1, n1), (s2, n2) in zip(got, got[1:]):
        assert s1 + n1 <= s2
    assert all(any(h0 <= s and s + n <= h0 + hn for h0, hn in holes) for s, n in got)


def test_to_files_inverts_from_files():
    files = _files(distinct=True)
    rs = RomSet.from_files(files)
    assert rs.to_files() == {k: files[k] for k in REQUIRED_FILES}


def test_zip_round_trip_keeps_every_lane(tmp_path):
    rs = RomSet.from_files(_files(distinct=True))
    p = tmp_path / "vr.zip"
    rs.to_zip(p)
    assert RomSet.from_zip(p, verify=False) == rs


def test_to_zip_refuses_to_overwrite_its_source(tmp_path):
    rs = RomSet.from_files(_files())
    p = tmp_path / "vr.zip"
    rs.to_zip(p)
    before = p.read_bytes()
    with pytest.raises(RomSetError, match="source"):
        rs.to_zip(p, source=tmp_path / "." / "vr.zip")
    assert p.read_bytes() == before


def test_zip_round_trip(tmp_path):
    rs = RomSet.from_files(_files())
    p = tmp_path / "vr.zip"
    rs.to_zip(p)
    with zipfile.ZipFile(p) as z:
        assert set(z.namelist()) == set(REQUIRED_FILES)
    back = RomSet.from_zip(p, verify=False)
    assert back.program == rs.program and back.polygons == rs.polygons and back.data == rs.data
    with pytest.raises(Exception):
        RomSet.from_zip(p)                         # CRCs differ from the real set


def test_write_polygons_and_tile_record():
    rs = RomSet.from_files(_files())
    word = write_polygons(rs, b"\x01\x02\x03\x04" * 4, byte_offset=0x1000)
    assert word == 0x400 and rs.polygons[0x1000:0x1004] == b"\x01\x02\x03\x04"
    with pytest.raises(PatchError):
        write_polygons(rs, b"\x00" * 8, byte_offset=3)
    # a course tile table at the real address, record 0 at 0x2e9980
    prog = bytearray(rs.program)
    struct.pack_into("<I", prog, 0x2F2056 - 0x200000, 0x2E9980)
    rs2 = RomSet(prog, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    write_tile_record(rs2, 0, cell=0, poly_adr=0x1234, tex_adr=0x45000, size=99)
    assert struct.unpack_from("<4I", rs2.program, 0x2E9980 - 0x200000) == (0x1234, 0x45000, 99, 0)
    with pytest.raises(PatchError):
        write_tile_record(rs2, 0, cell=0, poly_adr=0x800000, tex_adr=0, size=1)


def _erased_table(rs):
    """The real set's free colour-table runs read 0xFFFF; give the fake program ROM an erased table."""
    prog = bytearray(rs.program)
    prog[:0xE0000] = b"\xff" * 0xE0000
    return RomSet(bytes(prog), rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)


def test_write_colour_entries_uses_rom_map():
    rs = _erased_table(RomSet.from_files(_files()))
    write_colour_entries(rs, {0x40010: 0x0002, 0x40011: 0x03FF})
    assert struct.unpack_from("<2H", rs.program, 0x20) == (0x0002, 0x03FF)
    with pytest.raises(PatchError):
        write_colour_entries(rs, {0x40010: 0x10000})
    with pytest.raises(PatchError):
        write_colour_entries(rs, {0x3FFFF: 1})


def test_patch_course_tiles_sets_unlisted_cells_empty():
    rs = _erased_table(RomSet.from_files(_files()))
    prog = bytearray(rs.program)
    for c in range(256):
        struct.pack_into("<I", prog, 0x2F2056 - 0x200000 + 4 * c, 0x2E9980 + 16 * c)
        struct.pack_into("<4I", prog, 0x2E9980 - 0x200000 + 16 * c, 7, 7, 7, 0)
    rs = RomSet(bytes(prog), rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    out = patch_course_tiles(rs, 0, {5: (b"\x00" * 64, ObjectLayout(2, 0x50000, 0x50000), 0x50000)}, {0x50000: 0x0001},
                             holes=[(0x1000, 0x1000)])
    rec5 = struct.unpack_from("<4I", out.program, 0x2E9980 - 0x200000 + 16 * 5)
    assert rec5[0] == 0x400 and rec5[1] == 0x50000 and rec5[2] == 2
    assert struct.unpack_from("<4I", out.program, 0x2E9980 - 0x200000 + 16 * 6) == (0, 0, 0, 0)
    assert out.polygons[0x1000:0x1040] == b"\x00" * 64


def test_allocator_rejects_overlapping_holes():
    with pytest.raises(PatchError, match="overlap"):
        Allocator([(0, 100), (52, 100)])


def _tiled_romset():
    rs = _erased_table(RomSet.from_files(_files()))
    prog = bytearray(rs.program)
    for c in range(256):
        struct.pack_into("<I", prog, 0x2F2056 - 0x200000 + 4 * c, 0x2E9980 + 16 * c)
    return RomSet(bytes(prog), rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)


def test_patch_refuses_polygon_space_that_is_not_free():
    rs = _tiled_romset()
    obj = {5: (b"\x00" * 64, ObjectLayout(2, 0x50000, 0x50000), 0x50000)}
    once = patch_course_tiles(rs, 0, obj, {0x50000: 1}, holes=[(0x1000, 0x1000)])
    again = {5: (b"\x00" * 64, ObjectLayout(2, 0x50001, 0x50001), 0x50001)}
    with pytest.raises(PatchError, match="not free"):
        patch_course_tiles(once, 0, again, {0x50001: 1}, holes=[(0x1000, 0x1000)])   # same hole, already written


def test_patch_refuses_colour_entries_that_are_in_use():
    rs = _tiled_romset()
    prog = bytearray(rs.program)
    struct.pack_into("<H", prog, 2 * (0x50000 - 0x40000), 0x0123)                  # a live entry
    rs = RomSet(bytes(prog), rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    with pytest.raises(PatchError, match="in use"):
        write_colour_entries(rs, {0x50000: 1})


def test_patch_refuses_records_whose_colours_are_not_written():
    rs = _tiled_romset()
    with pytest.raises(PatchError, match="tex"):
        patch_course_tiles(rs, 0, {5: (b"\x00" * 64, ObjectLayout(2, 0x50000, 0x50001), 0x50000)}, {0x50000: 1},
                           holes=[(0x1000, 0x1000)])                                  # 0x50001 is read but never written
    with pytest.raises(PatchError, match="tex"):
        patch_course_tiles(rs, 0, {5: (b"\x00" * 64, ObjectLayout(2, 0x50000, 0x50000), 0x50002)}, {0x50000: 1, 0x50002: 1},
                           holes=[(0x1000, 0x1000)])                                  # record tex_start disagrees with the layout


def test_patched_tiles_decode_to_the_assigned_colours():
    """assign_colours -> encode_object -> patch_course_tiles -> tile_table -> quads -> colour_of round trip."""
    from vrtools.arcade.colours import Palette, colour_of, colour_table
    from vrtools.arcade.course import tile_table
    from vrtools.arcade.polyrom import decode_object, encode_object, quads
    from vrtools.convert.geometry import WorldQuad, assign_colours

    pal = Palette([0x8000, 0x801F, 0x83E0, 0x7C00] + [0] * 1020)
    colours = [(240, 0, 0), (0, 240, 0), (0, 0, 240), (240, 0, 0), (0, 0, 240)]
    world = [WorldQuad(((i, 0, 0), (i, 0, 1), (i, 1, 1), (i, 1, 0)), c) for i, c in enumerate(colours)]
    coloured, words = assign_colours(world, pal, tex_start=0x50000)
    blob, layout = encode_object(coloured, tex_start=0x50000)
    out = patch_course_tiles(_tiled_romset(), 0, {9: (blob, layout, 0x50000)}, words, holes=[(0x1000, 0x1000)])
    entry = tile_table(out, 0)[9]
    got = quads(decode_object(out.polygons, entry.poly_adr, entry.size), entry.tex_adr)
    table = colour_table(out)
    assert [colour_of(table, pal, q.tex_adr)[0] for q in got] == [(248, 0, 0), (248, 0, 0), (0, 248, 0), (0, 0, 248), (0, 0, 248)]


# --- copro (TGP) ROM patcher -------------------------------------------------------------------------------------

from vrtools.arcade.course import collision_map, course_table          # noqa: E402
from vrtools.arcade.patch import patch_collision, write_copro_words, write_data, write_slot   # noqa: E402
from vrtools.arcade.tgp import Collision, Quad16, slot_table            # noqa: E402

CELL_A, CELL_B = 1000, 1001


def _flat_quad(i):
    x = 16.0 * i
    return Quad16(((x, 30, 0), (x + 4, 30, 0), (x + 4, 30, 8), (x, 30, 8)), (x + 2, 30, 4), 0)


def _copro_romset(bank_cells=None):
    """Fake set: real copro layout (slot table, zero gaps, 0xff free area) and a synthetic Big Forest bank."""
    from tests.test_course import _bank, _rs
    bank = bytearray(_bank())
    for cell, v in (bank_cells or {}).items():
        struct.pack_into("<H", bank, 0x2000 + 2 * cell, v)
    rs = _rs({3: bytes(bank), 1: _bank(), 2: _bank()})
    copro = bytearray(b"\xff" * len(rs.copro_data))
    for a, b in ((0x3FA1, 0x8000), (0xB547, 0x10000)):
        copro[4 * a:4 * b] = bytes(4 * (b - a))
    slots = [(0x30, 0x12E00)] * 16
    slots[1], slots[2] = (0x8000, 0x28A90), (0x10000, 0x3C170)
    for i, (blk, pool) in enumerate(slots):
        struct.pack_into("<I", copro, 4 * (0x10 + i), blk)
        struct.pack_into("<I", copro, 4 * (0x20 + i), pool)
    return RomSet(rs.program, rs.boot, rs.data, rs.polygons, bytes(copro), rs.tgp_program)


def test_write_copro_words_requires_free_space():
    rs = _copro_romset()
    write_copro_words(rs, 0x4B170, b"\x01\x00\x00\x00" * 4)
    assert rs.copro_data[4 * 0x4B170:4 * 0x4B170 + 4] == b"\x01\x00\x00\x00"
    with pytest.raises(PatchError, match="not free"):
        write_copro_words(rs, 0x4B170, b"\x02\x00\x00\x00")
    with pytest.raises(PatchError, match="not free"):
        write_copro_words(rs, 0x3FA1, b"\x02\x00\x00\x00")
    write_copro_words(rs, 0x3FA1, b"\x02\x00\x00\x00", allow_zero=True)
    with pytest.raises(PatchError):
        write_copro_words(rs, 0x7FFFF, b"\x02\x00\x00\x00" * 2)       # past the ROM


def test_write_slot_guards_original_slots():
    rs = _copro_romset()
    with pytest.raises(PatchError):
        write_slot(rs, 2, 0x50000, 0x60000)
    write_slot(rs, 2, 0x50000, 0x60000, force=True)
    write_slot(rs, 3, 0x50000, 0x60000)
    assert slot_table(rs)[3] == (0x50000, 0x60000) and slot_table(rs)[2] == (0x50000, 0x60000)
    with pytest.raises(PatchError):
        write_slot(rs, 16, 0, 0)


def test_write_data_is_bounds_checked():
    rs = _copro_romset()
    write_data(rs, 0x300000 + 0x2000, b"\x01\x02")
    assert rs.data[0x302000:0x302002] == b"\x01\x02"
    with pytest.raises(PatchError):
        write_data(rs, len(rs.data) - 1, b"\x01\x02")


def test_patch_collision_rewrites_map_and_rejects_long_blocks():
    rs = _copro_romset({CELL_A: 1, CELL_B: 2})
    col = Collision({0: [], 1: [0], 3: [0, 1]}, [_flat_quad(0), _flat_quad(1)])
    out = patch_collision(rs, 0, col, slot=2, force=True, holes=[(0x50000, 0x1000)])
    assert slot_table(out)[2] == (0x50000, 0x50010)                    # 6 list words, pool at the next 16-aligned word (a quad never straddles a TGP window)
    cm = collision_map(out, course_table(out)[0])
    assert cm[CELL_A] == 1 and cm[CELL_B] == 0                         # id 2 names no list any more
    assert out.copro_data[4 * 0x50000:4 * 0x50006] == struct.pack("<6I", 0, 1, 0, 2, 0, 1)
    assert rs.copro_data[4 * 0x50000:4 * 0x50005] == b"\xff" * 20     # input untouched
    with pytest.raises(PatchError, match="not free"):
        patch_collision(out, 0, col, slot=2, force=True, holes=[(0x50000, 0x1000)])
    with pytest.raises(PatchError, match="0xffff"):
        patch_collision(rs, 0, Collision({1 + i * 2: [0] for i in range(0x8001)}, [_flat_quad(0)]), slot=2, force=True,
                        holes=[(0x50000, 0x30000)])


def test_patch_collision_with_cell_offsets_and_zero_id():
    rs = _copro_romset({CELL_A: 1, CELL_B: 2})
    col = Collision({1: [0], 3: [0, 1]}, [_flat_quad(0), _flat_quad(1)])
    out = patch_collision(rs, 0, col, slot=2, force=True, holes=[(0x50000, 0x1000)], cell_offsets={CELL_A: 3, CELL_B: 1})
    cm = collision_map(out, course_table(out)[0])
    assert cm[CELL_A] == 3 and cm[CELL_B] == 1 and sum(1 for v in cm if v) == 2
    with pytest.raises(PatchError, match="offset 0"):
        patch_collision(rs, 0, Collision({0: [], 1: [0, 1]}, [_flat_quad(0), _flat_quad(1)]), slot=2, force=True,
                        holes=[(0x50000, 0x1000)], cell_offsets={CELL_A: 0})


def test_patch_collision_writes_the_empty_offroad_list_at_offset_zero():
    """The TGP reads the count at block + id; id 0 (off-road) must find a 0 count, not erased 0xffffffff."""
    rs = _copro_romset({CELL_A: 1, CELL_B: 2})
    col = Collision({1: [0], 3: [0, 1]}, [_flat_quad(0), _flat_quad(1)])
    out = patch_collision(rs, 0, col, slot=2, force=True, holes=[(0x50000, 0x1000)], cell_offsets={CELL_A: 3, CELL_B: 1})
    block, _ = slot_table(out)[2]
    assert out.copro_data[4 * block:4 * block + 4] == b"\x00\x00\x00\x00"
    assert out.copro_data[4 * block + 4:4 * block + 8] == struct.pack("<I", 1)


def test_write_slot_refuses_a_slot_already_in_use():
    rs = _copro_romset()
    write_slot(rs, 3, 0x50000, 0x60000)
    with pytest.raises(PatchError, match="in use"):
        write_slot(rs, 3, 0x70000, 0x78000)
    write_slot(rs, 3, 0x70000, 0x78000, force=True)


def test_patch_collision_ties_the_slot_to_the_course():
    rs = _copro_romset({CELL_A: 1, CELL_B: 2})
    col = Collision({1: [0], 3: [0, 1]}, [_flat_quad(0), _flat_quad(1)])
    with pytest.raises(PatchError, match="slot"):
        patch_collision(rs, 0, col, slot=3, holes=[(0x50000, 0x1000)])   # Big Forest loads slot 2
    out = patch_collision(rs, 0, col, slot=2, force=True, holes=[(0x50000, 0x1000)])
    assert slot_table(out)[2] == (0x50000, 0x50010)


def test_write_copro_words_allows_zero_only_inside_the_zero_gaps():
    rs = _copro_romset()
    data = bytearray(rs.copro_data)
    struct.pack_into("<I", data, 4 * 0x3C17F, 0)                           # a live zero word inside Big Forest's pool
    rs = RomSet(rs.program, rs.boot, rs.data, rs.polygons, bytes(data), rs.tgp_program)
    with pytest.raises(PatchError, match="not free"):
        write_copro_words(rs, 0x3C17F, b"\x01\x00\x00\x00", allow_zero=True)
    write_copro_words(rs, 0x3FA1, b"\x01\x00\x00\x00", allow_zero=True)   # inside COPRO_ZERO_GAPS


def test_pit_entry_table_and_patch(romset_zip):
    from vrtools.arcade.course import pit_entry_table
    from vrtools.arcade.patch import patch_pit_entry

    rs = RomSet.from_zip(romset_zip)
    assert pit_entry_table(rs) == (None, 28, 30)         # Bay Bridge: no pit lane; Acropolis quad 28; Big Forest quad 30
    out = patch_pit_entry(rs, 2, None)
    assert pit_entry_table(out) == (None, 28, None) and pit_entry_table(rs) == (None, 28, 30)
    assert pit_entry_table(patch_pit_entry(rs, 0, 500)) == (500, 28, 30)
    with pytest.raises(PatchError):
        patch_pit_entry(rs, 3, None)
    with pytest.raises(PatchError):
        patch_pit_entry(rs, 2, 0xFFFF)


def test_install_collision_writes_copro_and_returns_the_map_without_touching_a_bank():
    from vrtools.arcade.patch import install_collision
    from vrtools.arcade.tgp import slot_table

    rs = _copro_romset({CELL_A: 1, CELL_B: 2})
    col = Collision({0: [], 1: [0], 3: [0, 1]}, [_flat_quad(0), _flat_quad(1)])
    out, cells = install_collision(rs, col, slot=3, cell_offsets={CELL_A: 1, CELL_B: 3})
    assert len(cells) == 128 * 128 and cells[CELL_A] == 1 and cells[CELL_B] == 3 and sum(1 for c in cells if c) == 2
    assert slot_table(out)[3] != slot_table(rs)[3] and out.data == rs.data
    with pytest.raises(PatchError):
        install_collision(rs, col, slot=16, cell_offsets={CELL_A: 1})
    with pytest.raises(PatchError):
        install_collision(rs, col, slot=3, cell_offsets={CELL_A: 2})                 # no list at offset 2


def test_write_tile_table_and_patch_into_it(romset_zip):
    from vrtools.arcade.course import tile_table, tile_table_at
    from vrtools.arcade.patch import write_tile_table

    rs = RomSet.from_zip(romset_zip)
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    write_tile_table(out, 0x27A000)
    t = tile_table_at(out, 0x27A000)
    assert len(t) == 256 and all((e.poly_adr, e.tex_adr, e.size) == (0, 0, 0) for e in t)
    with pytest.raises(PatchError):
        write_tile_table(out, 0x27A000)                                               # no longer free
    with pytest.raises(PatchError):
        write_tile_table(rs, 0x2F2056)                                                # Big Forest's own table
    from vrtools.arcade.colours import TABLE_BASE, TILE_RECORD_ROM
    tex = next(t for t in range(TABLE_BASE, TABLE_BASE + TILE_RECORD_ROM // 2)
               if struct.unpack_from("<H", rs.program, 2 * (t - TABLE_BASE))[0] == 0xFFFF)          # a free colour entry
    out2 = patch_course_tiles(out, 0, {5: (b"\x00" * 64, ObjectLayout(2, tex, tex), tex)}, {tex: 0x0001},
                              holes=[(0x2A7CA0, 0x1000)], tile_table=0x27A000)
    assert tile_table_at(out2, 0x27A000)[5].size == 2 and tile_table(out2, 0) == tile_table(rs, 0)


def test_install_collision_refuses_original_and_used_slots():
    from vrtools.arcade.patch import install_collision

    rs = _copro_romset({CELL_A: 1})
    col = Collision({0: [], 1: [0]}, [_flat_quad(0)])
    with pytest.raises(PatchError):
        install_collision(rs, col, slot=2, cell_offsets={CELL_A: 1})                  # Big Forest's slot
    out, _ = install_collision(rs, col, slot=3, cell_offsets={CELL_A: 1})
    with pytest.raises(PatchError):
        install_collision(out, col, slot=3, cell_offsets={CELL_A: 1})                 # already taken


def test_polygon_holes_are_every_erased_chip_tail(romset_zip):
    """Phase 18: the polygon ROM is 2 MB chips; the erased (0xFF) tail of each, up to its chip boundary, is unused
    padding. POLY_HOLES lists every such tail of 64 KB or more (Phase 1 listed only the two largest)."""
    from vrtools.arcade.patch import POLY_HOLES
    p = RomSet.from_zip(romset_zip).polygons
    chip = 0x200000
    tails = []
    for end in range(chip, len(p) + 1, chip):
        start = end
        while start > end - chip and p[start - 1] == 0xFF:
            start -= 1
        if end - start >= 0x10000:
            tails.append((start, end - start))
    assert sorted(POLY_HOLES) == tails
    assert all(set(p[a:a + n]) == {0xFF} for a, n in POLY_HOLES)
