"""The wheel-scrolled row of ten: band table, window rule, and the select routines' assembly."""
from vrtools.arcade.course import CODE_FREE
from vrtools.arcade.directory import ORIGINALS, directory_layout, install_directory
from vrtools.arcade.disasm import listing, listing_bytes
from vrtools.arcade.romset import RomSet
from vrtools.arcade.select import BANDS, WHEEL_FOR_ENTRY, band_of, first_of, select_routines, slot_of, visible_entries


def test_visible_window_rule():
    assert visible_entries(0) == (0, 1, 2) and visible_entries(1) == (0, 1, 2) and visible_entries(5) == (4, 5, 6)
    assert visible_entries(9) == (7, 8, 9) and visible_entries(8) == (7, 8, 9)
    assert [slot_of(i) for i in range(10)] == [0, 1, 1, 1, 1, 1, 1, 1, 1, 2]
    assert [first_of(i) for i in range(10)] == [0, 0, 1, 2, 3, 4, 5, 6, 7, 7]


def test_bands_cover_the_wheel_value_range():
    """R10 = ([0x501060] + [0x50106c]) >> 1 runs -127..127 (measured: about 1.72 × (wheel − 128), clamped)."""
    assert len(BANDS) == 9 and list(BANDS) == sorted(BANDS) and BANDS[0] > -127 and BANDS[-1] < 127
    assert band_of(-127) == 0 and band_of(127) == 9 and band_of(0) == 5 and band_of(-1) == 4
    assert [band_of(t) for t in BANDS] == list(range(1, 10))                  # a threshold starts the band above it
    assert len(WHEEL_FOR_ENTRY) == 10 and all(0 <= w <= 255 for w in WHEEL_FOR_ENTRY) and list(WHEEL_FOR_ENTRY) == sorted(WHEEL_FOR_ENTRY)


def test_select_routines_assemble_and_reference_their_tables():
    lay = directory_layout(CODE_FREE[0])
    code = select_routines(lay)
    for name in ("band", "draw"):
        ls = listing_bytes(code[name], lay[name])
        assert ls[-1].text == "rsr", name
    band = [l.text for l in listing_bytes(code["band"], lay["band"])]
    assert any(f"{lay['bands']:X}" in t for t in band) and any("501942" in t for t in band) and any(f"{lay['draw']:X}" in t for t in band)
    draw = [l.text for l in listing_bytes(code["draw"], lay["draw"])]
    assert sum(1 for t in draw if "FF9436" in t) == 2 and any(f"{lay['slot_a']:X}" in t for t in draw)
    assert any("501940" in t for t in draw)


def test_install_patches_the_three_select_sites(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, (ORIGINALS * 4)[:10])
    lay = directory_layout(CODE_FREE[0])
    assert [l.text.split()[0] for l in listing(out, 0xFC26DF, 2)] == ["jsr", "nop"] and listing(out, 0xFC26FA, 1)[0].text.startswith("movt.wh")
    assert [l.text.split()[0] for l in listing(out, 0xFC3622, 2)] == ["jsr", "rsr"]
    assert listing(out, 0xFC369B, 1)[0].text.startswith("cmp.h")                  # the dead on-change routine is left alone
    assert listing(out, 0xFC26DF, 1)[0].text.endswith(f"{lay['band']:X}")


def test_draw_copies_the_slot_picture():
    """Phase 21: per slot, `draw` takes the entry's picture record (lay["pictures"]); with one, the `picture` routine copies
    its three character runs to the slot's blocks (SLOT_CHAR), its palettes to SLOT_PAL and writes the 21 x 16 tile words
    0x8000 | (SLOT_CHAR + local) at SLOT_B; without one (0) layer B is blitted from the load record as before."""
    from vrtools.arcade.select import SLOT_CHAR, SLOT_PAL
    lay = directory_layout(CODE_FREE[0])
    code = select_routines(lay)
    draw = [l.text for l in listing_bytes(code["draw"], lay["draw"])]
    assert any(f"{lay['pictures']:X}" in t for t in draw) and any(f"{lay['picture']:X}" in t for t in draw)
    assert sum(1 for t in draw if "FF9436" in t) == 2                              # layer A, and layer B without a picture
    pic = [l.text for l in listing_bytes(code["picture"], lay["picture"])]
    assert pic[-1] == "rsr"
    for name in ("slot_char", "slot_pal", "slot_tile", "slot_b"):
        assert any(f"{lay[name]:X}" in t for t in pic), name
    assert SLOT_CHAR == (0x3300, 0x3480, 0x3600) and SLOT_PAL == (0x900CC0, 0x900D20, 0x900D80)


def test_start_greys_the_slots_not_chosen():
    """Phase 21 (recon §3): `start` reads [0x501940], the pictures table and both palette fields, and ends with the
    game's cursor frame (jsr 0xfc2880) and rsr."""
    lay = directory_layout(CODE_FREE[0])
    st = [l.text for l in listing_bytes(select_routines(lay)["start"], lay["start"])]
    assert any("501940" in t for t in st) and any(f"{lay['pictures']:X}" in t for t in st)
    assert any(f"{lay['slot_pal']:X}" in t for t in st)
    assert st[-2].startswith("jsr") and st[-2].endswith("FC2880") and st[-1] == "rsr"


def test_the_picture_routine_blanks_the_slot_before_copying():
    """Phase 21 review: the slot's tiles are pointed at BLANK_TILE before any character moves (a copy caught mid-way
    shows nothing, not a garbled panel), and characters move memory to memory (one instruction a word)."""
    from vrtools.arcade.select import BLANK_TILE
    lay = directory_layout(CODE_FREE[0])
    pic = [l.text for l in listing_bytes(select_routines(lay)["picture"], lay["picture"])]
    first_blank = next(i for i, t in enumerate(pic) if f"#{BLANK_TILE:X}" in t)
    first_move = next(i for i, t in enumerate(pic) if t.startswith("mov.w") and t.count("[") == 2)
    assert first_blank < first_move
    assert sum(1 for t in pic if t.startswith("mov.w") and t.count("[") == 2) == 24       # 8 words x 3 runs
    assert not any(t.startswith("mov.w") and t.endswith(", R0") and "[R3]" in t for t in pic)  # no load/store pair
