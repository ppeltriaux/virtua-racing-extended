import numpy as np
import pytest

from vrtools.saturn.backdrop import SaturnPanorama

FILL = 0x3991                       # Big Forest's layer-3 fill code (palette 115)


def _flat(colour=0x2D6B):
    return SaturnPanorama(np.zeros((256, 1280), np.uint8), (colour,) + (0,) * 255)


def _noise(seed=1):
    rng = np.random.default_rng(seed)
    return SaturnPanorama(rng.integers(0, 256, (256, 1280), dtype=np.uint8), tuple(int(c) for c in rng.integers(0, 0x8000, 256)))


def test_a_flat_panorama_is_two_tiles():
    from vrtools.convert.backdrop import convert_panorama
    p, report = convert_panorama(_flat(), top_row=40.0, column_offset=0, fill_code=FILL)
    assert len(p.tiles) <= 3 and report["palettes"] >= 1 and report["mean_error"] < 1.0


def test_limits_hold_on_noise():
    from vrtools.convert.backdrop import CODE_LIMIT, MAX_TILES, TOP_CODE, convert_panorama
    p, report = convert_panorama(_noise(), top_row=40.0, column_offset=100, fill_code=FILL)
    assert p.map.shape == (24, 256)
    assert len(p.palettes) <= (CODE_LIMIT - TOP_CODE) // 128 and len(p.tiles) <= MAX_TILES
    assert all(TOP_CODE <= c < CODE_LIMIT for c in p.tiles)
    assert all((c >> 7) in p.palettes for c in p.tiles)                     # a tile's palette is its code >> 7
    assert all(int(c) in p.tiles for c in np.unique(p.map))
    assert sum(len(d) for _, d in p.uploads) == 32 * len(p.tiles)


def test_the_reserved_tiles():
    """Layer 3 fills above and below the band with tile 0x3000 and the host's fill code (Review Focus 1)."""
    from vrtools.convert.backdrop import TOP_CODE, convert_panorama
    p, _ = convert_panorama(_noise(2), top_row=40.0, column_offset=0, fill_code=FILL)
    assert p.map[0, 0] == TOP_CODE and p.map[-1, 0] == FILL               # the game fills layer 3 from these two entries
    for code in (TOP_CODE, FILL):
        px = np.frombuffer(p.tiles[code], np.uint8)
        idx = np.stack([px >> 4, px & 15], -1).ravel()
        assert len(set(idx.tolist())) == 1 and idx[0] != 0, hex(code)


def test_real_panoramas_convert_within_budget(saturn_cue):
    from vrtools.arcade.backdrop import encode_panorama
    from vrtools.convert.backdrop import convert_panorama
    from vrtools.saturn.backdrop import BGS_OF_COURSE, decode_bgs
    from vrtools.saturn.iso import Iso2352
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    for name, path in sorted(set((n, p) for n, p in BGS_OF_COURSE.items() if n != "SURFERS OVAL")):
        p, report = convert_panorama(decode_bgs(iso.read("VRSRCDIR/TRACKS00/" + path)), top_row=40.0, column_offset=0, fill_code=FILL)
        blob, _ = encode_panorama(p, 0x100000)
        print(name, report, len(blob))
        assert report["mean_error"] < 14 and len(blob) <= 100 * 1024, (name, report, len(blob))


def _drawn(p):
    """The band as the arcade draws it: (rows * 8, 2048, 3), 0..31."""
    out = np.zeros((p.map.shape[0] * 8, p.map.shape[1] * 8, 3))
    for r in range(p.map.shape[0]):
        for c in range(p.map.shape[1]):
            code = int(p.map[r, c])
            px = np.frombuffer(p.tiles[code], np.uint8)
            idx = np.stack([px >> 4, px & 15], -1).reshape(8, 8)
            pal = np.array([[w & 31, (w >> 5) & 31, (w >> 10) & 31] for w in p.palettes[code >> 7]], float)
            out[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = pal[idx]
    return out


def test_the_bands_top_runs_into_the_flat_sky_above_it():
    """Phase 25 (Pascal: "an incorrect top filling sky color: diablo, pacific coast, surfers road"): the 48 pixels over
    the band are one flat colour (layer 3's fill, tile 0x3000), the mean of the band's top row; where clouds reach the
    top of the Saturn's picture (99 % of Diablo Canyon's top row is off its mean) the band started on a hard line under
    it. The band's first tile row is that fill itself and the picture fades in below it over TOP_FADE pixels."""
    from vrtools.convert.backdrop import TOP_CODE, TOP_FADE, convert_panorama
    px = np.zeros((256, 1280), np.uint8)
    px[:, 640:] = 1                                                           # half the turn dark blue sky, half white cloud
    sat = SaturnPanorama(px, (0x5000, 0x7FFF) + (0,) * 254)
    p, _ = convert_panorama(sat, top_row=40.0, column_offset=0, fill_code=FILL)
    d = _drawn(p)
    fill = d[0, 0]
    assert (p.map[0] == TOP_CODE).all()                                       # the first tile row is the fill
    assert np.abs(d[8] - fill).sum(1).max() < 4                               # no line under it (of 93)
    step = np.abs(d[1:8 + TOP_FADE] - d[:7 + TOP_FADE]).sum(2).max()
    assert step < 12, step                                                    # and none on the way down
    below = d[8 + TOP_FADE + 8]
    assert np.abs(below[100] - below[1500]).sum() > 40                        # under the fade: the picture as it was
