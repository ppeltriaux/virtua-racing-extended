import struct

import pytest

from vrtools.arcade import disasm
from vrtools.arcade.disasm import DisasmError, find_refs, immediates, listing
from vrtools.arcade.romset import REQUIRED_FILES, RomSet

N = 64


def _rs(program: bytes) -> RomSet:
    files = {name: bytes(N) for name in REQUIRED_FILES}
    a, b = program[0::2], program[1::2]
    files["epr-14882.14"] = a + bytes(N - len(a))
    files["epr-14883.15"] = b + bytes(N - len(b))
    return RomSet.from_files(files)


def test_find_refs_locates_little_endian_value():
    prog = bytes(16) + struct.pack("<I", 0x123456) + bytes(8) + struct.pack("<I", 0x123456)
    rs = _rs(prog)
    assert find_refs(rs, 0x123456, regions=("program",)) == [0x200010, 0x20001C]


def test_find_refs_24bit_match_reported_separately():
    prog = bytes(4) + bytes([0x56, 0x34, 0x12, 0x99])
    rs = _rs(prog)
    assert find_refs(rs, 0x123456, regions=("program",), width=3) == [0x200004]
    assert find_refs(rs, 0x123456, regions=("program",)) == []


def test_immediates_extracts_addresses():
    lines = [disasm.Line(0, b"", "mov.w   #123456h, R1"), disasm.Line(4, b"", "jmp     FE1469"),
             disasm.Line(8, b"", "mov.b   #12h, R0"), disasm.Line(12, b"", "mov.w   [R2+0x600000], R3")]
    assert immediates(lines) == {0x123456, 0xFE1469, 0x600000}


def test_listing_requires_unidasm(monkeypatch, tmp_path):
    monkeypatch.setattr(disasm, "UNIDASM", tmp_path / "missing")
    with pytest.raises(DisasmError, match="build-mame"):
        listing(_rs(bytes(32)), 0x200000, 2)


def test_listing_real_boot_rom(romset_zip):
    if not disasm.UNIDASM.exists():
        pytest.skip("unidasm not built")
    lines = listing(RomSet.from_zip(romset_zip), 0xFC0000, 4)
    assert len(lines) == 4 and lines[0].addr == 0xFC0000
    assert lines[1].addr == 0xFC0000 + len(lines[0].bytes)
