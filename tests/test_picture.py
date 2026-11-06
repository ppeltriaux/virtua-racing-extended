import struct

import numpy as np

from vrtools.arcade.romset import RomSet


def _render(p) -> np.ndarray:
    """A Picture back to RGB (5-bit channels x 8)."""
    from vrtools.arcade.panel import char_pixels
    out = np.zeros((168, 128, 3), np.uint8)
    for i, local in enumerate(p.map):
        px = char_pixels(p.chars[local])
        pal = p.palettes[16 * (local >> 7):16 * (local >> 7) + 16]
        for y in range(8):
            for x in range(8):
                w = pal[px[y][x]]
                out[(i // 16) * 8 + y, (i % 16) * 8 + x] = ((w & 31) * 8, ((w >> 5) & 31) * 8, ((w >> 10) & 31) * 8)
    return out


def test_a_picture_fits_the_panel():
    """Phase 21: at most PICTURE_CHARS characters, 3 palettes of 16 words (bit 15 set, as the select palettes), every map
    entry's palette is its local index >> 7, and no pixel uses colour 0 (transparent)."""
    from vrtools.arcade.panel import char_pixels
    from vrtools.arcade.picture import PICTURE_CHARS, quantise
    rgb = np.random.default_rng(1).integers(0, 256, (168, 128, 3), dtype=np.uint8)
    p = quantise(rgb)
    assert len(p.palettes) == 48 and all(w & 0x8000 for w in p.palettes)
    assert len(p.map) == 336 and len(set(p.map)) <= PICTURE_CHARS
    assert all(0 <= m < 384 for m in p.map) and all(m in p.chars for m in p.map)
    assert all(v != 0 for m in set(p.map) for row in char_pixels(p.chars[m]) for v in row)


def test_quantise_keeps_a_flat_picture_exact():
    from vrtools.arcade.picture import quantise
    rgb = np.zeros((168, 128, 3), np.uint8)
    rgb[:, :64] = (8, 16, 24); rgb[:, 64:] = (200, 40, 0); rgb[80:, :] = (0, 128, 248); rgb[160:, 100:] = (248, 248, 248)
    assert np.array_equal(_render(quantise(rgb)), rgb)


def test_grey_matches_the_originals(romset_zip):
    """The originals' 'not chosen' sets (recon §3) are greys 10-22 that keep the frame colour and the brightness order of
    each ramp; `grey` of Big Forest's uploaded picture palettes is grey, in 10-22, keeps (31,18,0), keeps the luminance
    order within each palette, and its mean is within 2 levels of the ROM's grey set."""
    from vrtools.arcade.panel import select_palette
    from vrtools.arcade.picture import grey
    rs = RomSet.from_zip(romset_zip)
    sp = select_palette(rs)
    k0 = (0x900cc0 - 0x900000) // 2 - (sp["dst"] - 0x900000) // 2
    normal = sp["words"][k0:k0 + 48]
    frame = 0x8000 | 18 << 5 | 31
    g = grey(normal, keep=(frame,))
    rom = struct.unpack_from("<48H", rs.boot, 0xFC3A29 - 0xFC0000)
    ch = lambda w: (w & 31, (w >> 5) & 31, (w >> 10) & 31)
    lum = lambda w: 0.3 * ch(w)[0] + 0.59 * ch(w)[1] + 0.11 * ch(w)[2]
    levels = []
    for i, (a, b) in enumerate(zip(normal, g)):
        if i % 16 == 0:
            continue
        if a == frame:
            assert b == frame
            continue
        r, gg, bb = ch(b)
        assert r == gg == bb and 10 <= r <= 22, (i, ch(a), ch(b))
        levels.append(r)
    for p in range(3):
        idx = [i for i in range(16 * p + 1, 16 * p + 16) if normal[i] != frame]
        for i in idx:
            for j in idx:
                if lum(normal[i]) < lum(normal[j]):
                    assert ch(g[i])[0] <= ch(g[j])[0]
    rom_levels = [ch(w)[0] for i, w in enumerate(rom) if i % 16 and normal[i] != frame]
    assert abs(sum(levels) / len(levels) - sum(rom_levels) / len(rom_levels)) <= 2.0


def test_records_encode_little_endian():
    from vrtools.arcade.picture import RECORD_BYTES, PictureRecord, encode_record
    r = PictureRecord(*range(1, 10))
    assert encode_record(r) == struct.pack("<9I", *range(1, 10)) and RECORD_BYTES == 36


def test_a_picture_blob_lays_out_its_parts():
    """Each palette's characters as one run (local 128 p .. 128 p + n_p - 1), the runs back to back; then the normal, chosen
    (= normal) and grey palettes, then the map; the record holds their addresses and counts = n0 | n1 << 8 | n2 << 16."""
    from vrtools.arcade.picture import grey, picture_blob, quantise
    rgb = np.zeros((168, 128, 3), np.uint8); rgb[:, 64:] = (200, 40, 0); rgb[100:, :] = (0, 0, 200)
    p = quantise(rgb)
    n = [sum(1 for k in p.chars if k >> 7 == q) for q in range(3)]
    for q in range(3):
        assert sorted(k for k in p.chars if k >> 7 == q) == list(range(128 * q, 128 * q + n[q]))
    blob, rec = picture_blob(p, 0x1000)
    assert rec.counts == n[0] | n[1] << 8 | n[2] << 16 and rec.chars_addr == 0x1000
    assert rec.normal_addr == 0x1000 + 32 * sum(n) and rec.chosen_addr == rec.normal_addr + 96
    assert rec.grey_addr == rec.chosen_addr + 96 and rec.map_addr == rec.grey_addr + 96
    assert len(blob) == rec.map_addr + 672 - 0x1000 and (rec.a_dst, rec.a_chosen_addr, rec.a_grey_addr) == (0, 0, 0)
    assert list(struct.unpack_from("<48H", blob, rec.grey_addr - 0x1000)) == grey(p.palettes)
    assert list(struct.unpack_from("<336H", blob, rec.map_addr - 0x1000)) == p.map
