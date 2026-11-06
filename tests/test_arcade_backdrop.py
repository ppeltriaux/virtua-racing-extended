import dataclasses

import numpy as np
import pytest

from vrtools.arcade.romset import RomSet

ORIGINAL_BANKS = {"BIG FOREST": 3, "BAY BRIDGE": 1, "ACROPOLIS": 2}


def test_the_originals_backdrops_read(romset_zip):
    """Phase 18b recon §2: phase 0 the tiles, phase 1 the palettes, phases 2-9 eight 32-column tilemap blocks."""
    from vrtools.arcade.backdrop import read_panorama
    from vrtools.arcade.course import course_entry_at
    rs = RomSet.from_zip(romset_zip)
    shapes = {}
    for name, bank in ORIGINAL_BANKS.items():
        p = read_panorama(rs, course_entry_at(rs, bank))
        shapes[name] = (p.map.shape, len(p.palettes))
        codes = p.map & 0x3fff
        assert all(int(c) in p.tiles for c in np.unique(codes)), name
        assert all((int(c) >> 7) in p.palettes for c in np.unique(codes)), name
        assert all(len(t) == 32 for t in p.tiles.values()) and all(len(c) == 16 for c in p.palettes.values())
    assert shapes["BIG FOREST"] == ((20, 256), 20) and shapes["ACROPOLIS"] == ((23, 256), 21) and shapes["BAY BRIDGE"][1] == 32


def test_a_panorama_round_trips(romset_zip):
    from vrtools.arcade.backdrop import encode_panorama, read_panorama
    from vrtools.arcade.blob import free_runs
    from vrtools.arcade.course import WINDOW, course_entry_at
    rs = RomSet.from_zip(romset_zip)
    for name, bank in ORIGINAL_BANKS.items():
        e = course_entry_at(rs, bank)
        p = read_panorama(rs, e)
        off, n = free_runs(rs, bank)[-1]
        blob, directory = encode_panorama(p, WINDOW + off)
        assert len(blob) <= n
        data = bytearray(rs.data)
        data[bank * 0x100000 + off: bank * 0x100000 + off + len(blob)] = blob
        out = RomSet(rs.program, rs.boot, bytes(data), rs.polygons, rs.copro_data, rs.tgp_program)
        q = read_panorama(out, dataclasses.replace(e, header=dataclasses.replace(e.header, gfx_dir=directory)))
        assert q.tiles == p.tiles and q.palettes == p.palettes and (q.map == p.map).all() and q.uploads == p.uploads, name


def test_the_image_opens_with_the_magic_word():
    """The boot routine `gfx` takes a header's directory only when GFX_MAGIC precedes it (Phase 18b)."""
    import struct
    from vrtools.arcade.backdrop import GFX_MAGIC, ArcadePanorama, encode_panorama
    p = ArcadePanorama({0x3000: bytes(32)}, {96: (0x8000,) * 16}, np.full((2, 256), 0x3000, np.uint16), [(0x7e0000, bytes(32))])
    blob, directory = encode_panorama(p, 0x150000)
    assert struct.unpack_from("<I", blob, 0)[0] == GFX_MAGIC and directory == 0x150004
