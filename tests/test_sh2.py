import struct

import pytest

from vrtools.saturn import sh2
from vrtools.saturn.sh2 import Sh2Error, find_refs, listing, vrcodelo_load_address


def test_find_refs_big_endian():
    blob = bytes(8) + struct.pack(">I", 0x06096000) + bytes(4) + struct.pack(">I", 0x06096000)
    assert find_refs(blob, 0x06010000, 0x06096000) == [0x06010008, 0x06010010]
    assert find_refs(blob, 0x06010000, 0x00609600) == []


def test_listing_requires_unidasm(monkeypatch, tmp_path):
    monkeypatch.setattr(sh2, "UNIDASM", tmp_path / "missing")
    with pytest.raises(Sh2Error, match="build-mame"):
        listing(bytes(64), 0x06010000, 0x06010000, 4)


def test_vrcodelo_load_address_from_ip_constants():
    ip = bytes(0x100) + struct.pack(">3I", 0x06010034, 0x06074E80, 0x06010208)
    assert vrcodelo_load_address(ip) == 0x06010000


def test_real_listing(saturn_cue):
    from vrtools.saturn.iso import Iso2352
    if not sh2.UNIDASM.exists():
        pytest.skip("unidasm not built")
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    base = vrcodelo_load_address(iso.read("0"))
    code = iso.read("VRSRCDIR/VRCODELO")
    lines = listing(code, base, base, 8)
    assert len(lines) == 8 and lines[0].addr == base and lines[1].addr == base + 2   # SH-2 instructions are 16-bit
