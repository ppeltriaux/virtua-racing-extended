"""Phase 22r: a ranking table per course (the game keeps three in battery RAM, one per original course)."""
from __future__ import annotations

import struct

import pytest

from vrtools.arcade.course import CODE_FREE
from vrtools.arcade.directory import ORIGINALS, CourseEntry10
from vrtools.arcade.romset import RomSet, V60_BOOT


def _converted(i: int) -> CourseEntry10:
    return CourseEntry10(f"COURSE {i}", i % 3, 1 + i % 3, 0x100000, 3 + i, i % 3, 0x2F0000 + i * 0x1000, 0xFD0000 + i * 0x100, None,
                         0x1E0000, 0x1E0400, 0, 0xB001, race=0x2E0000 + i * 0x1000)


def _directory():
    return list(ORIGINALS) + [_converted(i) for i in range(3, 10)]


def test_ranking_ids_keep_the_originals_on_their_data_index_and_give_each_converted_course_its_own():
    """The game's three tables are indexed by the course's data index (0 Bay Bridge, 1 Acropolis, 2 Big Forest, the
    value the select record puts in 0x501934); the seven converted courses get indices 3..9, their menu entry."""
    from vrtools.arcade.ranking import ranking_ids
    ids = ranking_ids(_directory())
    assert ids[:3] == [e.template for e in ORIGINALS] == [2, 0, 1]
    assert ids[3:] == list(range(3, 10))


def test_the_ranking_image_holds_ten_entry_arrays_the_magic_and_the_three_routines(romset_zip):
    """Per ranking index: the table base, its slot word, the checkpoint record (the originals' from the boot ROM's
    table, a converted course's from its race blob), the normal and the operator variant's record sets (the race blob
    and the blob + 16: the init sums 5 laps × sectors of extensions from the level-0 record), the (defaults, table)
    pair the initialiser walks; the new S-RAM magic; the setter, the slot initialiser and the ranking-id store."""
    from vrtools.arcade.race import CHECKPOINT_TABLE, TIME_TABLES
    from vrtools.arcade.directory import CHECKPOINTS_OFFSET
    from vrtools.arcade.ranking import (DEFAULT_NAMES, NEW_MAGIC, NEW_SLOTS, NEW_TABLES, ORIG_SLOTS, ORIG_TABLES, RANKING_INDEX,
                                        TABLE_BYTES, ranking_image, ranking_layout, ranking_size)
    rs = RomSet.from_zip(romset_zip)
    d = _directory()
    base = CODE_FREE[0]
    lay = ranking_layout(base)
    img = ranking_image(rs, d, base)
    assert len(img) == ranking_size() == lay["end"] - base
    u32 = lambda name, k: struct.unpack_from("<I", img, lay[name] - base + 4 * k)[0]
    boot = lambda addr: struct.unpack_from("<I", rs.boot, addr - V60_BOOT)[0]
    for r in range(3):
        assert u32("bases", r) == ORIG_TABLES[r] and u32("slots", r) == ORIG_SLOTS[r]
        assert u32("counts", r) == boot(CHECKPOINT_TABLE + 4 * r)
        assert u32("records", r) == boot(TIME_TABLES[0] + 4 * r) and u32("records_oper", r) == boot(TIME_TABLES[1] + 4 * r)
    for r in range(3, 10):
        e = d[r]
        assert u32("bases", r) == NEW_TABLES[r - 3] and u32("slots", r) == NEW_SLOTS + 4 * r
        assert u32("counts", r) == e.race + CHECKPOINTS_OFFSET
        assert u32("records", r) == e.race and u32("records_oper", r) == e.race + 16
    for r in range(10):
        assert u32("pairs", 2 * r) == DEFAULT_NAMES and u32("pairs", 2 * r + 1) == u32("bases", r)
    assert img[lay["magic"] - base: lay["magic"] - base + len(NEW_MAGIC)] == NEW_MAGIC and len(NEW_MAGIC) == 18
    spans = sorted([(t, t + TABLE_BYTES) for t in NEW_TABLES] + [(NEW_SLOTS, NEW_SLOTS + 40), (RANKING_INDEX, RANKING_INDEX + 1)])
    assert all(b <= c for (_, b), (c, _) in zip(spans, spans[1:]))                               # no overlaps
    free = ((0x40EA00, 0x40F000), (0x40F100, 0x40FE00))                                          # the untouched persistent stretches
    assert all(any(lo <= a and b <= hi for lo, hi in free) for a, b in spans)
    assert lay["setter"] < lay["slot_init"] < lay["id_store"] < lay["prologue"] < lay["end"]


def test_install_ranking_patches_the_boot_sites_it_expects_and_points_them_at_the_image(romset_zip):
    """Each site's original bytes are checked before the patch (the setter, the initialiser's loop count, its four
    array loads, its three slot stores, the S-RAM magic loads, the ranking-id store); afterwards the loads' PC-relative
    displacements reach the image's arrays and the magic, the setter jumps into the image."""
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.ranking import (INIT_ARRAYS, INIT_COUNT, INIT_PROLOGUE, RANKING_SITE, SETTER, SRAM_MAGIC_SITES, install_ranking,
                                        ranking_layout)
    rs = RomSet.from_zip(romset_zip)
    d = _directory()
    base = CODE_FREE[0]
    out = install_ranking(rs, d, base)
    lay = ranking_layout(base)
    boot = lambda addr, n: out.boot[addr - V60_BOOT: addr - V60_BOOT + n]
    disp = lambda site: site + struct.unpack("<i", boot(site + 3, 4))[0]
    for name, site in INIT_ARRAYS.items():
        assert disp(site) == lay[name], name
    for site in SRAM_MAGIC_SITES:
        assert disp(site) == lay["magic"]
    assert boot(INIT_COUNT, 3) == bytes.fromhex("2d29ea")                       # mov.w #10, R9
    assert boot(SETTER, 1) == b"\xd6" and struct.unpack_from("<I", boot(SETTER + 2, 4))[0] == lay["setter"]   # jmp abs
    assert boot(RANKING_SITE, 1) == b"\xe8" and struct.unpack_from("<I", boot(RANKING_SITE + 2, 4))[0] == lay["id_store"]
    assert boot(INIT_PROLOGUE, 1) == b"\xe8" and struct.unpack_from("<I", boot(INIT_PROLOGUE + 2, 4))[0] == lay["prologue"]
    with pytest.raises(PatchError):                                              # a second install sees patched sites
        install_ranking(out, d, base)


def test_a_fresh_battery_ram_gets_ten_ranking_tables_from_the_game_s_own_initialiser(tmp_path, romset_zip):
    """MAME boots the patched set with no battery RAM: the S-RAM check misses the new magic, the initialiser runs the
    patched loop over ten tables — the originals' three as before and seven new ones in the never-touched run — each
    24 entries of rank 1..24, the default names (YU., RNS, TKG...) and times stepping 5 s (0xa0) from a base the
    game rounds up to the minute from 5 laps × sectors of the level-0 record's words; the ten slots hold their table.
    A second boot on the same battery RAM keeps the new tables (they lie in the persistent part)."""
    import math
    import shutil
    from vrtools.arcade.directory import install_directory
    from vrtools.arcade.race import CHECKPOINT_TABLE, TIME_TABLES
    from vrtools.arcade.ranking import NEW_MAGIC, NEW_SLOTS, NEW_TABLES, ORIG_SLOTS, ORIG_TABLES, TABLE_BYTES, ranking_ids
    from vrtools.mame.runner import LUA_DIR, run_mame
    rs = RomSet.from_zip(romset_zip)
    d = (list(ORIGINALS) * 4)[:10]                              # the seven "converted" entries are originals' copies here
    out = install_directory(rs, d)
    build = tmp_path / "build"; build.mkdir()
    out.to_zip(build / "vr.zip", source=romset_zip)
    for extra in ("model1io.zip", "m1comm.zip"):
        shutil.copy(romset_zip.parent / extra, build / extra)
    dump = tmp_path / "ranking.bin"; dump2 = tmp_path / "ranking2.bin"
    run_mame(LUA_DIR / "ranking_dump.lua", 8, tmp_path / "run", build, env={"VR_RANKING_DUMP": str(dump), "VR_DUMP_FRAME": "300"}, timeout=300)
    run_mame(LUA_DIR / "ranking_dump.lua", 8, tmp_path / "run", build, env={"VR_RANKING_DUMP": str(dump2), "VR_DUMP_FRAME": "300"}, timeout=300)
    mem = dump.read_bytes(); at = lambda addr: addr - 0x40C900
    mem2 = dump2.read_bytes()
    for t in NEW_TABLES:                                                                          # a second boot keeps them
        assert mem2[at(t):at(t) + TABLE_BYTES] == mem[at(t):at(t) + TABLE_BYTES]
    assert mem2[at(NEW_SLOTS):at(NEW_SLOTS) + 40] == mem[at(NEW_SLOTS):at(NEW_SLOTS) + 40]
    assert mem[at(0x40E6D0):at(0x40E6D0) + 18] == NEW_MAGIC
    boot = lambda addr: struct.unpack_from("<I", rs.boot, addr - V60_BOOT)[0]
    names = [rs.boot[0xFC4DC4 - V60_BOOT + 8 * k: 0xFC4DC4 - V60_BOOT + 8 * k + 4] for k in range(24)]
    for r in range(10):
        t = d[r].template if r >= 3 else r                        # the template whose records the init sums
        rec = boot(boot(TIME_TABLES[0] + 4 * t))                  # level-0 record of the normal variant
        sectors = boot(boot(CHECKPOINT_TABLE + 4 * t))
        total = sum(struct.unpack_from(f"<{5 * sectors}I", rs.boot, rec - V60_BOOT))
        base_time = math.ceil(total / 1920) * 1920
        table = ORIG_TABLES[r] if r < 3 else NEW_TABLES[r - 3]
        slot = ORIG_SLOTS[r] if r < 3 else NEW_SLOTS + 4 * r
        assert struct.unpack_from("<I", mem, at(slot))[0] == table, r
        for k in range(24):
            e = at(table) + 24 * k
            rank, time, zero, minus, time2 = struct.unpack_from("<5I", mem, e)
            assert (rank, time, zero, minus, time2) == (k + 1, base_time + 0xA0 * k, 0, 0xFFFFFFFF, base_time + 0xA0 * k), (r, k)
            assert mem[e + 0x14:e + 0x18] == names[k], (r, k)
    assert ranking_ids(d)[:3] == [2, 0, 1]
