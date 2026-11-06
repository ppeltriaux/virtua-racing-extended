import struct

import pytest

from vrtools.saturn.iso import Iso2352
from vrtools.saturn.trck import LOAD_BASE, POINTER_COUNT, TrckError, TrckFile

BASE = LOAD_BASE


def build(pointers: list[int], length: int) -> bytes:
    assert len(pointers) == POINTER_COUNT
    data = bytearray(length)
    for i, p in enumerate(pointers):
        struct.pack_into(">I", data, i * 4, p)
    return bytes(data)


def test_pointer_table_and_offsets():
    t = TrckFile.from_bytes(build([BASE + 0x100, 0, BASE + 0xB0] + [0] * 41, 0x200))
    assert len(t.pointers) == 44
    assert t.pointers[0] == BASE + 0x100
    assert t.pointers[1] is None
    assert t.offset(0) == 0x100
    assert t.offset(1) is None
    assert t.offset(2) == 0xB0


def test_sections_run_to_next_distinct_offset_or_eof():
    t = TrckFile.from_bytes(build([BASE + 0x100, 0, BASE + 0xB0, BASE + 0x100] + [0] * 40, 0x200))
    secs = {s.offset: s for s in t.sections()}
    assert set(secs) == {0xB0, 0x100}
    assert secs[0xB0].length == 0x50
    assert secs[0x100].length == 0x100
    assert bytes(secs[0x100].data) == b"\x00" * 0x100
    assert sorted(s.index for s in t.sections()) == [0, 2, 3]


def test_pointer_outside_file_raises():
    with pytest.raises(TrckError, match="pointer 0 = 0x6000000"):
        TrckFile.from_bytes(build([0x6000000] + [0] * 43, 0x200))


def test_pointer_past_end_raises():
    with pytest.raises(TrckError, match="pointer 5"):
        TrckFile.from_bytes(build([0] * 5 + [BASE + 0x200] + [0] * 38, 0x200))


TRACKS = ["ACROPOLS/TRCKACRO", "ALPINE00/TRCKALPN", "AMAZON00/TRCKAMAZ", "BAYBRIDG/TRCKBAYB",
          "BIGFORES/TRCKBIGF", "DIABLO00/TRCKDIAB", "METROPOL/TRCKMETR", "PACCOAST/TRCKPACC",
          "SPEEDWAY/TRCKSPEE", "SURFER00/TRCKSURF"]


@pytest.mark.parametrize("name", TRACKS)
def test_all_tracks_parse(saturn_cue, name):
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    t = TrckFile.from_bytes(iso.read(f"VRSRCDIR/TRACKS00/{name}"))
    assert t.offset(4) == 0xB0
    assert sum(p is not None for p in t.pointers) >= 40
