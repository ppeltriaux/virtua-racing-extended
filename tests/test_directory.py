"""The ten-entry course directory and the code that routes the game through it."""
from dataclasses import replace

import pytest

from vrtools.arcade.course import CODE_FREE
from vrtools.arcade.directory import EMPTY_SPAWN_WORDS, ORIGINALS, CourseEntry10, decode_directory, directory_layout, install_directory
from vrtools.arcade.disasm import listing
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet

SPANS = ({(0xFE48ED, 0xB7), (0xFE8E8F, 0xD), (0xFC270B, 4), (0xFC28A3, 4), (0xFC26DF, 0x1B), (0xFC3622, 0x79), (0xFC0BB8, 0xF), (0xFE8A91, 0x16),
          (0xFEABF5, 7), (0xFEBCDF, 12),                                  # Phase 14: the HUD cross draw, the off-course compare
          (0xFEAC10, 10),                                                  # Phase 22b: the HUD map's outline object list
          (0xFE98C7, 13), (0xFE96A4, 0x3C), (0xFE8BD8, 0x2B), (0xFE969E, 6), (0xFE9922, 6), (0xFE9A29, 6), (0xFE9C5A, 6), (0xFE9DDD, 6), (0xFE9E5D, 6),   # Phase 22i: the park,
          (0xFF27D8, 7), (0xFF2D69, 7), (0xFF33C7, 7), (0xFF3A1B, 7),      # the pit autopilot's and the crew spawns' calls of the box pose
          (0xFFE007, 7), (0xFFE49E, 7),                                   # Phase 18b: the backdrop directory readers
          (0xFC4208, 30), (0xFC3B78, 3), (0xFC3B4F, 7), (0xFC3B5E, 7), (0xFC3B6C, 12), (0xFC3BF6, 36),   # Phase 22r: the ranking setter, the
          (0xFE69F7, 7), (0xFE6A18, 7), (0xFC270F, 9)}      # S-RAM initialiser's count, arrays and slot stores, the magic, the id store, the boot clear
         | {(s, 0x16) for s in (0xFE1D37, 0xFE2160, 0xFE2B07, 0xFE2CF7, 0xFE415B)})


def _ten():
    return (ORIGINALS * 4)[:10]


def test_originals_directory_round_trips_and_patches_only_the_sites(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, _ten())
    lay = directory_layout(CODE_FREE[0])
    assert out.data == rs.data and out.polygons == rs.polygons and out.copro_data == rs.copro_data
    changed = [i + 0xFC0000 for i in range(len(rs.boot)) if rs.boot[i] != out.boot[i]]
    assert changed and all(any(s <= a < s + n for s, n in SPANS) for a in changed)
    assert out.program[:CODE_FREE[0] - 0x200000] == rs.program[:CODE_FREE[0] - 0x200000]
    assert out.program[lay["end"] - 0x200000:] == rs.program[lay["end"] - 0x200000:]
    texts = [l.text for l in listing(out, lay["loader"], 120)]
    assert any("501940" in t for t in texts) and any("6800000" in t for t in texts) and "rsr" in texts
    assert [l.text.split()[0] for l in listing(out, 0xFE48ED, 2)] == ["jmp", "nop"]
    assert [l.text.split()[0] for l in listing(out, 0xFE415B, 2)] == ["jsr", "nop"]
    assert [l.text.split()[0] for l in listing(out, 0xFE8E8F, 2)] == ["jsr", "nop"]
    for site in (0xFE1D37, 0xFE2160, 0xFE2B07, 0xFE2CF7):
        assert [l.text.split()[0] for l in listing(out, site, 2)] == ["jsr", "nop"] and listing(out, site + 0x16, 1)[0].text.startswith("jsr")
    assert listing(out, 0xFE2004, 1)[0].text == "mov.b   #1, E00004"            # bank 0 (shared graphics) sites stay
    assert listing(out, 0xFE8E9C, 1)[0].text.startswith("cmp.h")             # the instruction after the pit span is intact
    assert listing(out, 0xFC2708, 1)[0].text == f"movea.b {lay['select']:X}[R11], R13"
    assert decode_directory(out, CODE_FREE[0]) == _ten()
    assert out.program[lay["spawn"] - 0x200000:lay["spawn"] - 0x200000 + 4 * EMPTY_SPAWN_WORDS] == bytes(4 * EMPTY_SPAWN_WORDS)


def test_directory_rejects_bad_entries(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    for bad in (dict(bank=4), dict(bank=0), dict(tgp_slot=16), dict(header_base=0x80000), dict(header_base=0x200000),
                dict(template=3), dict(name="TOO LONG A NAME"), dict(name="lower"), dict(label=3), dict(pit_quad=0xFFFE)):
        d = [replace(e, **bad) if i == 3 else e for i, e in enumerate(_ten())]
        with pytest.raises(PatchError):
            install_directory(rs, d)
    with pytest.raises(PatchError):
        install_directory(rs, ORIGINALS[:3])


def test_pit_quad_none_never_matches_a_quad():
    e = replace(ORIGINALS[1], pit_quad=None)
    assert ORIGINALS[1].pit_quad is None and e.pit_quad is None
    from vrtools.arcade.directory import PIT_NONE
    assert PIT_NONE == 0xFFFE                      # the check also tries pit_quad + 1: 0xffff was the original's "none", whose + 1 is quad 0


def test_load_record_layout_is_shared_by_the_encoder_and_the_routines():
    """The V60 routines read the load record by fixed offsets; the encoder must put the fields there."""
    import struct
    from vrtools.arcade.directory import LOAD_FIELDS, LOAD_SIZE, encode_directory
    from vrtools.arcade.select import select_routines
    from vrtools.arcade.disasm import listing_bytes

    e = replace(ORIGINALS[0], name="PACIFIC COAST", panel_b=0x1E06C0, art=7, pit_quad=1234, tgp_slot=9, bank=2, label=2)
    blob = encode_directory([e] * 10, CODE_FREE[0])
    rec = blob[10 * 24:10 * 24 + LOAD_SIZE]
    assert rec[LOAD_FIELDS["bank"]] == 2 and rec[LOAD_FIELDS["tgp_slot"]] == 9 and rec[LOAD_FIELDS["template"]] == 2 and rec[LOAD_FIELDS["label"]] == 2
    assert struct.unpack_from("<I", rec, LOAD_FIELDS["header_base"])[0] == 0x100000
    assert struct.unpack_from("<I", rec, LOAD_FIELDS["tile_table"])[0] == 0x2F2056 and struct.unpack_from("<I", rec, LOAD_FIELDS["spawn_table"])[0] == 0xFDB90B
    assert struct.unpack_from("<H", rec, LOAD_FIELDS["pit_quad"])[0] == 1234
    assert struct.unpack_from("<I", rec, LOAD_FIELDS["panel_b"])[0] == 0x1E06C0 and rec[LOAD_FIELDS["art"]] == 7
    assert rec[LOAD_FIELDS["name"]:LOAD_FIELDS["name"] + 13] == b"PACIFIC COAST"
    lay = directory_layout(CODE_FREE[0])
    draw = [l.text for l in listing_bytes(select_routines(lay)["draw"], lay["draw"])]
    assert any(t.startswith("mov.w") and f"{LOAD_FIELDS['panel_b']:X}[R11]" in t for t in draw)     # layer-B map read at its offset


def test_music_and_fallback_route_through_the_directory(romset_zip):
    """Issue from review: the race-start music table (0xfc117d, three halfwords) was indexed by the menu index, and
    every course load was keyed on the menu index even when the game chose the course through [0x501934]
    (operator setting, linked play, attract rotation). Now the music is a load-record field, and the routines use
    the menu entry only when its template equals [0x501934], else the original course for that data index."""
    import struct
    from vrtools.arcade.directory import LOAD_FIELDS, FALLBACK

    rs = RomSet.from_zip(romset_zip)
    assert [e.music for e in ORIGINALS] == [0xB001, 0xB00D, 0xB00E]
    assert FALLBACK == (1, 2, 0)                                           # data index BB/AC/BF -> menu entry
    out = install_directory(rs, _ten())
    lay = directory_layout(CODE_FREE[0])
    assert [l.text.split()[0] for l in listing(out, 0xFC0BB8, 2)] == ["jsr", "nop"] and listing(out, 0xFC0BC7, 1)[0].text.startswith("jsr")
    for name in ("loader", "bank", "pit", "music"):
        texts = [l.text for l in listing(out, lay[name], 40)]
        assert any("501934" in t for t in texts) and any(f"{lay['fallback']:X}" in t for t in texts), name
    rec = out.program[lay["load"] - 0x200000 + 3 * 64:lay["load"] - 0x200000 + 4 * 64]
    assert struct.unpack_from("<H", rec, LOAD_FIELDS["music"])[0] == 0xB001
    assert decode_directory(out)[3].music == 0xB001


def test_load_record_carries_race_blob_and_laps(romset_zip):
    import struct
    from vrtools.arcade.directory import LOAD_FIELDS, LOAD_FORMAT
    rs = RomSet.from_zip(romset_zip)
    d = list(ORIGINALS) + [replace(ORIGINALS[0], name=f"X{i}", race=0x280000 + 0x800 * i, laps=3 + i % 5) for i in range(7)]
    out = install_directory(rs, d)
    back = decode_directory(out)
    assert [e.race for e in back] == [0, 0, 0] + [0x280000 + 0x800 * i for i in range(7)]
    assert [e.laps for e in back] == [0, 0, 0] + [3 + i % 5 for i in range(7)]
    assert LOAD_FIELDS["race"] == 0x2C and LOAD_FIELDS["laps"] == 0x30 and struct.calcsize(LOAD_FORMAT) == 64
    for bad in (dict(laps=21), dict(race=0x1FFFFF)):
        with pytest.raises(PatchError):
            install_directory(rs, [replace(e, **bad) if i == 3 else e for i, e in enumerate(d)])


def test_loader_and_car_routines_serve_the_entry(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, list(ORIGINALS) + [replace(ORIGINALS[0], name=f"X{i}", race=0x280000, laps=5) for i in range(7)])
    lay = directory_layout()
    loader = [l.text for l in listing(out, lay["loader"], 90)]
    assert any("40DC8C" in t for t in loader) and any("501105" in t for t in loader)        # both variant flags still tested
    assert any(t.endswith("501968") for t in loader) and any(t.endswith("50195C") for t in loader) and any(t.endswith("5011A4") for t in loader)
    cars = [l.text for l in listing(out, lay["cars"], 40)]
    assert any("FCD395" in t for t in cars) and any("FCD195" in t for t in cars) and "rsr" in cars
    assert [l.text.split()[0] for l in listing(out, 0xFE8A91, 2)] == ["jsr", "nop"]
    assert listing(out, 0xFE8AA7, 1)[0].text.startswith("and.w")                            # the instruction after the span is intact
    assert directory_layout()["end"] - directory_layout()["loader"] < 4000                  # routines stay small (Phase 21: + picture (unrolled for speed), start; 22i: the pit
                                                                                            # routines; 22r: the ranking arrays and routines, 0x1b0 bytes)


def test_laps_are_written_only_in_the_normal_game_mode(romset_zip):
    """Review (Phase 9): the game sets 4 laps under the operator flag 0x40dc8c and 20 in linked play (both under
    that flag); writing the entry's 5 there would change those modes and leak into an original raced afterwards."""
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, list(ORIGINALS) + [replace(ORIGINALS[0], name=f"X{i}", race=0x280000, laps=5) for i in range(7)])
    lay = directory_layout()
    texts = [l.text for l in listing(out, lay["loader"], 120)]
    k = next(i for i, t in enumerate(texts) if t.endswith("5011A4"))
    before = texts[max(0, k - 6):k]
    assert any("40DC8C" in t for t in before) and any(t.startswith("bne") for t in before), before   # guarded by the operator flag


def test_load_record_carries_the_map_and_off_course_words(romset_zip):
    """Round trip of the Phase 14 fields and their fixed offsets (the loader copies them by offset)."""
    import struct
    from vrtools.arcade.directory import LOAD_FIELDS, LOAD_SIZE, encode_directory
    e = replace(ORIGINALS[0], name="ALPINE", map_tx=237.0, map_cross=22, off_course=40)
    d = [e] + ORIGINALS[1:] + [ORIGINALS[0]] * 7
    blob = encode_directory(d, CODE_FREE[0])
    rec = blob[10 * 24:10 * 24 + LOAD_SIZE]
    assert LOAD_FIELDS["map_tx"] == 0x34 and LOAD_FIELDS["map_cross"] == 0x38 and LOAD_FIELDS["off_course"] == 0x3C
    assert struct.unpack_from("<fII", rec, 0x34) == (237.0, 22, 40)
    orig = blob[10 * 24 + LOAD_SIZE:10 * 24 + 2 * LOAD_SIZE]
    assert struct.unpack_from("<fII", orig, 0x34) == (149.0, 0, 128)          # an original keeps the game's values
    rs = RomSet.from_zip(romset_zip)
    assert decode_directory(install_directory(rs, d), CODE_FREE[0]) == d


def test_directory_rejects_bad_map_and_off_course_values():
    from vrtools.arcade.directory import encode_directory
    for bad in (dict(map_cross=-2), dict(map_cross=1), dict(map_cross=0x2000), dict(off_course=0), dict(off_course=0x8000)):
        with pytest.raises(PatchError):
            encode_directory([replace(ORIGINALS[0], **bad)] * 10, CODE_FREE[0])


def test_loader_writes_the_map_and_off_course_words():
    """Three copies from the record into the game's RAM: the map section's translate x, the cross tile offset, the off-course limit."""
    from vrtools.arcade.course import MAP_CROSS_RAM, MAP_TX_RAM, OFF_COURSE_RAM
    from vrtools.arcade.directory import LOAD_FIELDS, _routines
    from vrtools.arcade.disasm import listing_bytes
    lay = directory_layout(CODE_FREE[0])
    texts = [l.text for l in listing_bytes(_routines(lay)["loader"], lay["loader"])]
    for field, ram in (("map_tx", MAP_TX_RAM), ("map_cross", MAP_CROSS_RAM), ("off_course", OFF_COURSE_RAM)):
        assert any(t.startswith("mov.w") and f"{LOAD_FIELDS[field]:X}[R8]" in t and f"{ram:X}" in t for t in texts), field


def test_boot_sites_route_the_cross_and_the_off_course_limit(romset_zip):
    from vrtools.arcade.course import CROSS_TILE_CELL, MAP_CROSS_RAM, MAP_CROSS_SITE, OFF_COURSE_COUNTER, OFF_COURSE_RAM, OFF_COURSE_SITE
    from vrtools.arcade.v60asm import asm
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, _ten())
    lay = directory_layout(CODE_FREE[0])
    assert out.boot[MAP_CROSS_SITE - 0xFC0000:MAP_CROSS_SITE - 0xFC0000 + 7] == asm("jsr abs", lay["cross"]) + asm("nop")
    assert listing(out, MAP_CROSS_SITE + 7, 1)[0].text == "mov.w   #2FA59A, R0"                 # the next instruction is intact
    assert out.boot[OFF_COURSE_SITE - 0xFC0000:OFF_COURSE_SITE - 0xFC0000 + 12] == asm("cmp.w abs,abs", OFF_COURSE_RAM, OFF_COURSE_COUNTER)
    assert listing(out, OFF_COURSE_SITE + 12, 1)[0].text.startswith("ble")
    cross = [l.text for l in listing(out, lay["cross"], 3)]
    assert cross == [f"mov.w   #{CROSS_TILE_CELL:X}, R1", f"add.w   {MAP_CROSS_RAM:X}, R1", "rsr"]


def test_boot_site_takes_the_hud_map_outline_from_the_entry(romset_zip):
    """Phase 22b (Pascal: the in-race map does not show where the car is): the map entity's outline is an object list the
    game picks from a three-entry table by data index (boot 0xfeac10: `mov.w FEAC1B[PC](R0), 18[R25]`: Bay Bridge's,
    Acropolis's, Big Forest's outline), so a converted course drew its host's outline around its own car. The site jumps
    to `mapobj`, which does the same, then takes the entry's own outline record when it has one (the directory's map
    table, a 16-byte object list per entry at a 64-byte stride; zero for the originals)."""
    import struct
    from vrtools.arcade.course import MAP_OBJ_SITE, MAP_OBJ_SITE_LEN, MAP_OBJ_TABLE
    from vrtools.arcade.v60asm import asm
    rs = RomSet.from_zip(romset_zip)
    d = [replace(e, map_obj=(0x123456, 0x402AA, 50)) if i == 3 else e for i, e in enumerate(_ten())]
    out = install_directory(rs, d)
    lay = directory_layout(CODE_FREE[0])
    at = MAP_OBJ_SITE - 0xFC0000
    assert MAP_OBJ_SITE_LEN == 10 and rs.boot[at:at + 10] == bytes.fromhex("2dc0c0f20b0000001918")
    assert out.boot[at:at + MAP_OBJ_SITE_LEN] == asm("jsr abs", lay["mapobj"]) + asm("nop") * (MAP_OBJ_SITE_LEN - len(asm("jsr abs", 0)))
    assert listing(out, MAP_OBJ_SITE + MAP_OBJ_SITE_LEN, 1)[0].text == "rsr"
    assert out.boot[MAP_OBJ_TABLE - 0xFC0000:MAP_OBJ_TABLE - 0xFC0000 + 12] == struct.pack("<3I", 0x2E0050, 0x2E0060, 0x2E0040)
    rec = lambda i: out.program[lay["maps"] + 64 * i - 0x200000:lay["maps"] + 64 * i + 16 - 0x200000]
    assert rec(3) == struct.pack("<4I", 0x123456, 0x402AA, 50, 0) and rec(0) == bytes(16) and rec(9) == bytes(16)
    texts = " ".join(l.text for l in listing(out, lay["mapobj"], 40))
    assert "FEAC1B" in texts and "18[R25]" in texts and "501940" in texts and "rsr" in texts
    assert decode_directory(out, CODE_FREE[0]) == d


def test_boot_sites_read_the_backdrop_directory_through_a_checked_routine(romset_zip):
    """0xffe007 (course-load uploads) and 0xffe49e (per-frame streaming, also at the title in bank 0) call the `gfx`
    routine: the current entry's header's directory when a GFX_MAGIC word precedes it (a converted course's own
    backdrop), else [0x100000] as before; the two boot-time readers (0xfe200c, 0xfe6b89) are left alone."""
    from vrtools.arcade.backdrop import GFX_MAGIC
    from vrtools.arcade.course import GFX_DIR_SITES
    from vrtools.arcade.directory import LOAD_FIELDS
    from vrtools.arcade.v60asm import asm
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, _ten())
    lay = directory_layout(CODE_FREE[0])
    for site in GFX_DIR_SITES:
        assert listing(rs, site, 1)[0].text == "mov.w   100000, R20"
        assert out.boot[site - 0xFC0000:site - 0xFC0000 + 7] == asm("jsr abs", lay["gfx"]) + asm("nop"), hex(site)
    texts = [l.text for l in listing(out, lay["gfx"], 30)]
    assert f"mov.w   {LOAD_FIELDS['header_base']:X}[R8], R20" in texts and "mov.w   [R20], R20" in texts
    assert any(t.startswith("cmp.w") and f"#{GFX_MAGIC:X}" in t for t in texts)
    assert "mov.w   100000, R20" in texts and "rsr" in texts
    assert any(t.startswith("cmp.w") and "#100004" in t for t in texts) and any(t.startswith("cmp.w") and "#200000" in t for t in texts)
    magic_read = next(i for i, t in enumerate(texts) if t.startswith("mov.w") and "-4[R20]" in t)
    assert max(i for i, t in enumerate(texts) if "#200000" in t) < magic_read            # range-checked before the -4 read (review)
    for site in (0xFE200C, 0xFE6B89):
        assert listing(out, site, 1)[0].text == "mov.w   100000, R20"


def test_no_other_bank_holds_a_false_backdrop_marker():
    """The `gfx` routine reads [header_base] in whatever bank is mapped; ten_course_set refuses a set where another bank's
    word there points just after a GFX_MAGIC (the routine would take a foreign directory)."""
    import struct
    from vrtools.arcade.backdrop import GFX_MAGIC
    from vrtools.arcade.tencourse import check_backdrop_markers
    data = bytearray(4 * 0x100000)
    struct.pack_into("<I", data, 0 * 0x100000 + 0x50000, 0x160004)            # bank 0, at the header's window offset
    struct.pack_into("<I", data, 0 * 0x100000 + 0x60000, GFX_MAGIC)           # ... a marker before its target
    with pytest.raises(Exception, match="GFX_MAGIC"):
        check_backdrop_markers(bytes(data), [(1, 0x150000)])
    struct.pack_into("<I", data, 0x60000, 0)
    check_backdrop_markers(bytes(data), [(1, 0x150000)])


def test_start_routine_replaces_the_highlight_when_there_are_pictures(romset_zip):
    """Phase 21: with picture records, 0xfc27d6 jumps to `start` (the rest of the old routine is left as it was, dead);
    without any, it stays the game's."""
    from dataclasses import replace
    from vrtools.arcade.course import CODE_FREE
    from vrtools.arcade.directory import directory_layout, install_directory
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.select import START_SITE, START_SITE_LEN
    rs = RomSet.from_zip(romset_zip)
    plain = install_directory(rs, (ORIGINALS * 4)[:10])
    assert plain.boot[START_SITE - 0xFC0000:START_SITE - 0xFC0000 + START_SITE_LEN] == rs.boot[START_SITE - 0xFC0000:START_SITE - 0xFC0000 + START_SITE_LEN]
    with_pics = install_directory(rs, [replace(e, picture=0x2B6700) for e in (ORIGINALS * 4)[:10]])
    lay = directory_layout(CODE_FREE[0])
    first = listing(with_pics, START_SITE, 1)[0]
    assert first.text.startswith("jmp") and first.text.endswith(f"{lay['start']:X}")
    n = len(first.bytes)
    assert with_pics.boot[START_SITE - 0xFC0000 + n:START_SITE - 0xFC0000 + START_SITE_LEN] == rs.boot[START_SITE - 0xFC0000 + n:START_SITE - 0xFC0000 + START_SITE_LEN]
    table = [int.from_bytes(with_pics.program[lay["pictures"] - 0x200000 + 4 * k:lay["pictures"] - 0x200000 + 4 * k + 4], "little") for k in range(10)]
    assert table == [0x2B6700] * 10


def test_boot_sites_take_the_pit_box_from_the_entry(romset_zip):
    """Phase 22i (Pascal: "the pit lane should force a pit stop ... similar to the normal track"): the pit sequence drives the
    car in a straight line to one absolute point per course (boot 0xff4061: Acropolis's box (-346.4, 3.7, -59.0), Big
    Forest's (-230.4, 30.0, -269.6), by data index; the crew stands at fixed offsets from it) and parks it facing +z
    (0xfe98c7: `mov.w R10, 1E[R25]; mov.w R12, 26[R25]; mov.h #0, 6A[R25]`). A converted course's box went to its host's
    point (inside Diablo's rock). 0xff4061 also places the PIT START grid (Pascal, rec73: rerouting it started Alpine's
    race in the pit lane), so it stays: the autopilot's six calls go to `pitbox` and the crew spawns' four to `pitboxcrew`,
    which serve the entry's box (x, y, z after the map record, +16) when it has one and the game's otherwise; the park
    site calls `pitpark`, which also sets the entry's heading (+28, the game's 1/65536-turn units; 0 = +z)."""
    import struct
    from vrtools.arcade.course import (PIT_BOX_CALLS, PIT_CREW_CALLS, PIT_PARK_SITE, PIT_PARK_SITE_LEN, PIT_POSE, pit_box_call_pattern,
                                       pit_crew_call_pattern)
    from vrtools.arcade.v60asm import asm
    rs = RomSet.from_zip(romset_zip)
    d = [replace(e, pit_box=(-100.5, 3.0, 250.0, 0x1234)) if i == 4 else e for i, e in enumerate(_ten())]
    out = install_directory(rs, d)
    lay = directory_layout(CODE_FREE[0])
    assert [l.text for l in listing(rs, PIT_POSE, 2)] == ["push    R19", "cmp.b   #0, 501934[PC]"]
    assert out.boot[PIT_POSE - 0xFC0000:PIT_POSE - 0xFC0000 + 80] == rs.boot[PIT_POSE - 0xFC0000:PIT_POSE - 0xFC0000 + 80]
    for site in PIT_BOX_CALLS:
        at = site - 0xFC0000
        assert rs.boot[at:at + 6] == pit_box_call_pattern(site) and listing(rs, site, 1)[0].text == "jsr     FF4061[PC]"
        assert out.boot[at:at + 6] == asm("jsr abs", lay["pitbox"])
    for site in PIT_CREW_CALLS:
        at = site - 0xFC0000
        assert rs.boot[at:at + 7] == pit_crew_call_pattern(site) and [l.text for l in listing(rs, site, 2)] == ["bsr     FF4061", "mov.w   #0, [R24]"]
        assert out.boot[at:at + 7] == asm("jsr abs", lay["pitboxcrew"]) + asm("nop")
        assert listing(out, site + 7, 1)[0].text == listing(rs, site + 7, 1)[0].text
    for site in (0xFC005F, 0xFF21A5, 0xFF4165):                                 # the grid's own calls stay
        assert listing(out, site, 2) == listing(rs, site, 2)
    at = PIT_PARK_SITE - 0xFC0000
    assert PIT_PARK_SITE_LEN == 13 and rs.boot[at:at + 13] == bytes.fromhex("2d0a191e2d0c19261b80e0196a")
    assert out.boot[at:at + 13] == asm("jsr abs", lay["pitpark"]) + asm("nop") * 7
    assert listing(out, PIT_PARK_SITE + PIT_PARK_SITE_LEN, 1)[0].text == "mov.w   #0, 44[R25]"              # the park goes on
    rec = lambda i: out.program[lay["maps"] + 64 * i + 16 - 0x200000:lay["maps"] + 64 * i + 32 - 0x200000]
    assert rec(4) == struct.pack("<3fHH", -100.5, 3.0, 250.0, 0x1234, 1) and rec(0) == bytes(16) and rec(9) == bytes(16)
    texts = " ".join(l.text for l in listing(out, lay["pitbox"], 60))
    assert "501940" in texts and "FF4061" in texts and "R10" in texts and "R11" in texts and "R12" in texts and "rsr" in texts
    assert [l.text for l in listing(out, lay["pitboxcrew"], 3)] == [f"jsr     {lay['pitbox']:X}", "mov.w   #0, [R24]", "rsr"]
    texts = " ".join(l.text for l in listing(out, lay["pitpark"], 60))
    assert "1E[R25]" in texts and "26[R25]" in texts and "6A[R25]" in texts and "rsr" in texts
    assert decode_directory(out, CODE_FREE[0]) == d


def test_boot_site_aims_the_pit_autopilot_along_the_entrys_lane(romset_zip):
    """Phase 22i (Pascal, rec74: on Alpine the car "missed the actual stop location and spun indefinitely"): the game's
    autopilot aims 10 units short of the box along -z until the car is level with that point, then at the box, which
    lines the car up on a +z pit lane (TGP 0x800000 is a subtract: the probe of 4 Nov). On Alpine's -x lane the short
    aim lay on the car's own line, so it ran straight until level, then had to turn 90 degrees to a box 10 units aside
    at a turning radius of 8 and orbited it. `pitaim` lays the short aim along the box's heading (`pit_box`), and runs
    the original sequence for an entry without a box."""
    from vrtools.arcade.course import PIT_AIM_PATTERN, PIT_AIM_SITE, PIT_AIM_SITE_LEN
    from vrtools.arcade.v60asm import asm
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, _ten())
    lay = directory_layout(CODE_FREE[0])
    at = PIT_AIM_SITE - 0xFC0000
    assert rs.boot[at:at + PIT_AIM_SITE_LEN] == PIT_AIM_PATTERN
    orig = [l.text for l in listing(rs, PIT_AIM_SITE, 14)]
    assert orig[0] == "mov.w   #800000, [R24]" and orig[4] == "cmpf.s  R9, 26[R25]" and orig[5] == "blt     FE96C5" and orig[12] == "in.w    [R23], R4"
    assert out.boot[at:at + PIT_AIM_SITE_LEN] == asm("jsr abs", lay["pitaim"]) + asm("nop") * (PIT_AIM_SITE_LEN - 6)
    assert listing(out, PIT_AIM_SITE + PIT_AIM_SITE_LEN, 1)[0].text == "sub.h   6A[R25], R4"
    lines = [l.text for l in listing(out, lay["pitaim"], 120) if l.addr < lay["pitpark"]]
    texts = " ".join(lines)
    for w in ("#7800000, [R24]", "#E800000, [R24]", "#F000000, [R24]", "#800000, [R24]", "#41200000, [R24]", "cmpf.s  #C1200000, R9", "in.w    [R23], R4",
              "1E[R25], [R24]", "26[R25], [R24]", "501940", "R10, R1", "R12, R9"):
        assert w in texts, w
    assert lines.count("rsr") == 2 and texts.count("cmpf.s  R9, 26[R25]") == 1          # the entry's path, then the original's


def test_directory_rejects_a_bad_pit_box():
    from vrtools.arcade.directory import _check
    with pytest.raises(PatchError):
        _check(replace(ORIGINALS[0], pit_box=(0.0, 0.0, 0.0, 0x10000)))


def test_boot_site_grants_pit_stops_to_every_entry_with_a_pit_quad(romset_zip):
    """Phase 22i (Pascal, rec77: "on amazon i didnt get any pit"): the race start sets the pit stops left (+0x1bf) at
    0xfe8bd8: 0 when the data index is Bay Bridge's (no pit lane), 5 in linked play, else 2 unless [0x40d826] >= 2. A
    converted course on Bay Bridge's template got none. `pitstops` decides by the entry's pit quad instead."""
    from vrtools.arcade.course import PIT_STOPS_PATTERN, PIT_STOPS_SITE, PIT_STOPS_SITE_LEN
    from vrtools.arcade.v60asm import asm
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, _ten())
    lay = directory_layout(CODE_FREE[0])
    at = PIT_STOPS_SITE - 0xFC0000
    assert rs.boot[at:at + PIT_STOPS_SITE_LEN] == PIT_STOPS_PATTERN
    orig = [l.text for l in listing(rs, PIT_STOPS_SITE, 11)]
    assert orig[0] == "xor.b   R0, R0" and orig[1] == "cmp.b   #0, 501934[PC]" and orig[9] == "mov.b   #2, R0" and orig[10] == "mov.b   R0, 1BF[R25]"
    assert out.boot[at:at + PIT_STOPS_SITE_LEN] == asm("jsr abs", lay["pitstops"]) + asm("nop") * (PIT_STOPS_SITE_LEN - 6)
    assert listing(out, PIT_STOPS_SITE + PIT_STOPS_SITE_LEN, 1)[0].text == "mov.b   R0, 1BF[R25]"
    lines = [l.text for l in listing(out, lay["pitstops"], 60) if l.addr < lay["end"]]
    texts = " ".join(lines)
    for w in ("501940", "10[R8], R1", "#FFFE, R1", "501105", "#5, R0", "40D826", "#2, R0", "rsr"):
        assert w in texts, w
