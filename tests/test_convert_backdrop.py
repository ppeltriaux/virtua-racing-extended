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
