import struct

import pytest

from vrtools.saturn.backdrop import (BASE_CONST, MAP_HEIGHT, MAP_WIDTH, BackdropError, BackdropHeader, map_cells,
                                     parse_header)


def test_parse_header_checks_size_invariant():
    blob = struct.pack(">2I", BASE_CONST, BASE_CONST + 100) + b"\x11" * 100 + bytes(512)      # the palette is at the end (Phase 18b)
    h = parse_header(blob)
    assert h == BackdropHeader(BASE_CONST, BASE_CONST + 100, 512, 100) and h.data_offset == 8
    with pytest.raises(BackdropError, match="size"):
        parse_header(blob[:-1])


def test_map_cells_is_permutation():
    m = b"".join(struct.pack(">H", i) for i in range(MAP_WIDTH * MAP_HEIGHT))
    cells = map_cells(m)
    assert len(cells) == 5120 and cells[0] == 0 and cells[-1] == 5119
    with pytest.raises(BackdropError, match="10240"):
        map_cells(m[:-2])


def test_real_backdrops(saturn_cue):
    from vrtools.saturn.iso import Iso2352
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    pairs = [(e.path, e.path.replace("/BGS", "/BGM")) for e in iso.entries() if "/BGS" in e.path]
    assert len(pairs) == 24
    for bgs_p, bgm_p in pairs:
        h = parse_header(iso.read(bgs_p))
        assert h.base == BASE_CONST and h.data_size > 0 and h.palette_size in (512, 1024)
        cells = map_cells(iso.read(bgm_p))
        assert len(cells) == 5120 and max(cells) < 5120
        if bgs_p.endswith(("1", "3")):
            assert len(set(cells)) == 5120            # full-detail variants use every cell once
        else:
            assert len(set(cells)) < 5120             # the 2/4 variants reuse cells


def test_lzss_literals_and_ring_references():
    """Flags LSB first, 1 = literal; a reference copies (b0 & 0x0F) + 2 bytes from ring position (b0 & 0xF0) << 4 | b1
    of a zero ring whose write index starts at 1 (Phase 18b recon §1)."""
    from vrtools.saturn.backdrop import decode_lzss
    assert decode_lzss(bytes([0b00000101, 0xAA, 0x01, 0x01, 0xBB]), 5) == bytes([0xAA, 0xAA, 0xAA, 0xAA, 0xBB])


def test_lzss_position_high_nibble():
    from vrtools.saturn.backdrop import decode_lzss
    lits = bytes(range(256)) + bytes(range(44))                            # 300 literals at ring positions 1..300
    stream = b"".join(bytes([0xFF]) + lits[k:k + 8] for k in range(0, 296, 8))
    stream += bytes([0b00001111]) + lits[296:300] + bytes([0x1F, 0x00])   # 4 literals, then 17 bytes from ring position 0x100
    out = decode_lzss(stream, 317)
    assert out[:300] == lits and out[300:] == lits[255:272]


def test_real_backdrops_decode_to_the_pinned_digests(saturn_cue):
    """Every converted course's backdrop decodes to the bytes the Saturn holds in VDP2 VRAM in a race (recon §5)."""
    import hashlib
    from vrtools.saturn.backdrop import BGS_OF_COURSE, decode_bgs, decode_lzss
    from vrtools.saturn.iso import Iso2352
    digests = {"ALPINE": ("5e03eb42332e18e5bcf70a5325b815ed60bfd053", "b8593f834ef694cef695cc97a895897c2908b157"),
               "AMAZON FALLS": ("f0300d05f7f1f69809abbc56d3cea545b96b2af2", "fd2a2871b336c0d4a87256f529f4749b5391c3eb"),
               "DIABLO CANYON": ("14d582d9b5e7d78da3bba3ae25861a7984650fc5", "c0792d82af4c6f99473e4647ba815f85bef73d06"),
               "METROPOLIS": ("10c890adcbb14d772b31668b78135a17fa937816", "fb53e62a7e19e36380ec6575eb64b8e3e5f1dee3"),
               "PACIFIC COAST": ("5ae342f4b2898cc347b2fcf3a90d27f3212890cd", "5de0167be3ff83f686030431476e487941f536d0"),
               "SURFERS OVAL": ("e2f049d72da722efff3520706329c3989f4cb779", "2600cb0ad4c0e85faacbfe18951c5738d75665c6"),
               "SURFERS ROAD": ("e2f049d72da722efff3520706329c3989f4cb779", "2600cb0ad4c0e85faacbfe18951c5738d75665c6")}
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    assert set(BGS_OF_COURSE) == set(digests)
    for name, path in BGS_OF_COURSE.items():
        bgs = iso.read("VRSRCDIR/TRACKS00/" + path)
        h = parse_header(bgs)
        cells = decode_lzss(bgs[h.data_offset:h.data_offset + h.data_size], 5120 * 64)
        assert (hashlib.sha1(cells).hexdigest(), hashlib.sha1(bgs[-512:]).hexdigest()) == digests[name], name
        pano = decode_bgs(bgs)
        assert pano.pixels.shape == (256, 1280) and len(pano.palette) == 256
        assert pano.pixels[0, :8].tobytes() == cells[:8] and pano.pixels[0, 320:328].tobytes() == cells[1280 * 64:1280 * 64 + 8]
