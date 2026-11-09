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


def test_the_attract_groups_put_each_original_first_then_the_courses_in_its_slot():
    """The attract mode's ranking page comes with the demo of an original course (its data index): it now shows that
    course's table, then on later loops the converted courses it hosts, one per loop."""
    from vrtools.arcade.ranking import attract_groups
    g = attract_groups(_directory())
    assert g == [[0, 3, 6, 9], [1, 4, 7], [2, 5, 8]]                              # _converted(i) is hosted by i % 3
    assert attract_groups((list(ORIGINALS) * 4)[:10]) == [[0], [1], [2]]           # copies of originals have no table of their own


def test_title_columns_centre_the_line_like_the_originals():
    """MEDIUM / EXPERT COURSE RANKING start at column 9, COURSE at 24, RANKING at 39 (2 columns a letter, 3 between
    words); the longest converted names still fit the 62 columns."""
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.ranking import title_columns
    assert title_columns("MEDIUM") == (9, 24, 39)
    for name in ("DIABLO CANYON", "PACIFIC COAST", "SURFERS ROAD", "ALPINE"):
        n, c, r = title_columns(name)
        assert n >= 0 and c == n + 2 * len(name) + 3 and r == c + 15 and r + 14 <= 62
        assert abs((n + r + 14) / 2 - 31) <= 1
    with pytest.raises(PatchError):
        title_columns("a lowercase name")
    with pytest.raises(PatchError):
        title_columns("A NAME FAR TOO LONG TO FIT")


def test_the_image_holds_the_attract_groups_and_a_title_per_ranking_id(romset_zip):
    """The originals' titles are the game's own routines (its jump table by data index); a converted course's prints
    its name in red (0x8300), then the game's COURSE and RANKING (0x8200), with the game's string printer."""
    from vrtools.arcade.disasm import listing_bytes
    from vrtools.arcade.ranking import (COURSE_STRING, RANKING_STRING, STRING_PRINT, TITLE_ROW, TITLE_TABLE, attract_groups,
                                        ranking_image, ranking_layout, title_columns)
    rs = RomSet.from_zip(romset_zip)
    d = _directory()
    base = CODE_FREE[0]
    lay = ranking_layout(base)
    img = ranking_image(rs, d, base)
    at = lambda a: a - base
    for k, g in enumerate(attract_groups(d)):
        row = img[at(lay["groups"]) + 16 * k: at(lay["groups"]) + 16 * k + 16]
        assert row[0] == len(g) and list(row[1:1 + len(g)]) == g
    titles = struct.unpack_from("<10I", img, at(lay["titles"]))
    for r in range(3):
        assert titles[r] == struct.unpack_from("<I", rs.boot, TITLE_TABLE - V60_BOOT + 4 * r)[0]
    for r in range(3, 10):
        code = img[at(titles[r]):at(titles[r]) + lay["title_bytes"]]
        texts = [l.text for l in listing_bytes(code, titles[r])]
        n, c, k = title_columns(d[r].name)
        name_at = lay["names"] + 16 * (r - 3)
        assert img[at(name_at):at(name_at) + len(d[r].name) + 1] == d[r].name.encode() + b"\0"
        want = []
        for attr, col, s in ((0x8300, n, name_at), (0x8200, c, COURSE_STRING), (0x8200, k, RANKING_STRING)):
            want += [f"movz.hw #{attr:X}, [-SP]", f"movea.b {TITLE_ROW + 2 * col:X}, [-SP]", f"movea.b {s:X}, [-SP]",
                     f"call    {STRING_PRINT:X}, [SP]", "add.w   #C, SP"]
        assert [" ".join(t.split()) for t in texts[:15]] == [" ".join(t.split()) for t in want]
        assert texts[15] == "rsr"


def test_install_ranking_routes_the_attract_page_and_the_title_through_the_image(romset_zip):
    from vrtools.arcade.ranking import ATTRACT_SITE, TITLE_SITE, install_ranking, ranking_layout
    rs = RomSet.from_zip(romset_zip)
    assert rs.boot[ATTRACT_SITE - V60_BOOT: ATTRACT_SITE - V60_BOOT + 10] == bytes.fromhex("0d20f33419500048ce05")
    out = install_ranking(rs, _directory(), CODE_FREE[0])
    lay = ranking_layout(CODE_FREE[0])
    boot = lambda addr, n: out.boot[addr - V60_BOOT: addr - V60_BOOT + n]
    assert boot(ATTRACT_SITE, 2) == b"\xe8\xf3" and struct.unpack_from("<I", boot(ATTRACT_SITE + 2, 4))[0] == lay["attract"]
    assert boot(TITLE_SITE, 2) == b"\xe8\xf3" and struct.unpack_from("<I", boot(TITLE_SITE + 2, 4))[0] == lay["title"]


def _title_words(rs: RomSet, text: str, col: int, attr: int) -> list[tuple[int, int]]:
    """(column, tile word) of the top row of `text` printed at `col` by the game's string printer (2 x 3 tiles a letter)."""
    glyphs = 0x2F2456 - 0x200000
    out = []
    for i, ch in enumerate(text):
        g = rs.program[glyphs + 6 * (ord(ch) & 0x3F): glyphs + 6 * (ord(ch) & 0x3F) + 2]
        out += [(col + 2 * i, attr | g[0]), (col + 2 * i + 1, attr | g[1])]
    return out


def _pages(log) -> list[tuple[int, int, int, list[int]]]:
    """(data index, shown id, table base, title row words) of each page the logger saw drawn (a red title)."""
    pages = []
    for line in log.read_text().splitlines():
        _, d, shown, table, row = line.split()
        words = [int(row[k:k + 4], 16) for k in range(0, len(row), 4)]
        if any(w >> 8 == 0x83 for w in words) and (not pages or pages[-1][:3] != (int(d), int(shown), int(table, 16))):
            pages.append((int(d), int(shown), int(table, 16), words))
    return pages


def test_attract_and_race_end_rankings_name_their_course(tmp_path, romset_zip, saturn_cue):
    """MAME, the full ten-course set: the attract mode's ranking pages show each original's own table under its own
    title (EXPERT shows Acropolis's 5'00 table again, not the last chosen course's), then, a loop later, the converted
    courses in its slot under their names; after a race on Amazon Falls the ranking is Amazon Falls' under its name."""
    import shutil
    from vrtools.arcade.directory import ORIGINALS
    from vrtools.arcade.ranking import NEW_TABLES, ORIG_TABLES, attract_groups, title_columns
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.arcade.tencourse import COURSES as PLANS, build_all, ten_course_set
    from vrtools.mame.runner import LUA_DIR, run_mame
    rs = RomSet.from_zip(romset_zip)
    out, conv = build_all(rs, saturn_cue)
    out = ten_course_set(out, conv)
    build = tmp_path / "build"; build.mkdir()
    out.to_zip(build / "vr.zip", source=romset_zip)
    for extra in ("model1io.zip", "m1comm.zip"):
        shutil.copy(romset_zip.parent / extra, build / extra)
    names = [e.name for e in ORIGINALS] + [p.name for p in PLANS]
    d = list(ORIGINALS) + [c.entry for c in conv]
    groups = attract_groups(d)
    table = lambda r: ORIG_TABLES[r] if r < 3 else NEW_TABLES[r - 3]
    original_title = {0: ("MEDIUM", 9), 1: ("EXPERT", 9), 2: ("BEGINNER", 8)}

    def check(page):
        d_index, shown, base, words = page
        assert base == table(shown), page[:3]
        if shown < 3:
            text, col = original_title[shown]
        else:
            text, col = d[shown].name, title_columns(d[shown].name)[0]
        for c, w in _title_words(out, text, col, 0x8300):
            assert words[c] == w, (text, c, hex(words[c]), hex(w))

    run_mame(LUA_DIR / "ranking_title_log.lua", 300, tmp_path / "a", build, env={"VR_RANKING_LOG": str(tmp_path / "a.log")}, timeout=1500)
    pages = _pages(tmp_path / "a.log")
    seen = [(p[0], p[1]) for p in pages]
    for k in range(3):
        assert (k, groups[k][0]) in seen                                               # each original's own table
    assert (0, groups[0][1]) in seen and (1, groups[1][1]) in seen                       # then the first converted ones
    for p in pages:
        assert p[1] in groups[p[0]], p[:3]
        check(p)
    env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[4]), "VR_COLLISION_LOG": str(tmp_path / "c.txt"),
           "VR_EXTRA_LUA": str(LUA_DIR / "ranking_title_log.lua"), "VR_RANKING_LOG": str(tmp_path / "r.log"), "VR_SNAPS": ""}
    run_mame(LUA_DIR / "autoplay.lua", 130, tmp_path / "r", build, env=env, timeout=1500)
    race = [p for p in _pages(tmp_path / "r.log") if p[1] == 4]                          # entry 4: Amazon Falls, timed out
    assert race and names[4] == "AMAZON FALLS"
    check(race[0])


def test_the_attract_and_title_routines_decode_as_intended(romset_zip):
    """MAME's disassembler on the two new routines: the attract page clamps the data index and the group counter
    (0xff on a fresh battery RAM), stores the next counter and jumps into the setter after its id load; the title
    takes the shown id (the data index when it was never set) and calls its title routine through the table."""
    from vrtools.arcade.disasm import listing_bytes
    from vrtools.arcade.ranking import ATTRACT_COUNTERS, SHOWN_ID, ranking_image, ranking_layout
    rs = RomSet.from_zip(romset_zip)
    base = CODE_FREE[0]
    lay = ranking_layout(base)
    img = ranking_image(rs, _directory(), base)
    text = lambda a, b: [" ".join(l.text.split()) for l in listing_bytes(img[lay[a] - base:lay[b] - base], lay[a])]
    attract = text("attract", "title")
    assert attract[2] == "movz.bw 501934, R0" and attract[-1] == f"jmp {lay['common']:X}"
    assert f"mov.b R3, {ATTRACT_COUNTERS:X}(R0)" in attract and f"movz.bw {lay['groups'] + 1:X}(R1), R0" in attract
    title = text("title", "title3")
    assert title[0] == f"movz.bw {SHOWN_ID:X}, R0" and title[-2:] == ["jsr [R0]", "rsr"]
    assert text("setter", "slot_init")[1] == f"mov.b R0, {SHOWN_ID:X}" and lay["common"] == lay["setter"] + 7
