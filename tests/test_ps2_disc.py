"""The PS2 disc reader accepts a raw MODE2/2352 image and a plain 2048-byte-sector .iso, told apart by content. Synthetic images only."""

import struct

import pytest

from vrtools.arcade import pack
from vrtools.ps2 import disc
from vrtools.saturn.iso import IsoError

BODY = b"BOOT2 = cdrom0:\\SLPM_624.43;1\r\n"


def _dir_record(name: bytes, extent: int, size: int, flags: int = 0) -> bytes:
    length = 33 + len(name) + (1 - len(name) % 2)
    rec = bytearray(length)
    rec[0] = length
    rec[2:6] = struct.pack("<I", extent)
    rec[10:14] = struct.pack("<I", size)
    rec[25] = flags
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    return bytes(rec)


def _sectors() -> list[bytes]:
    root = _dir_record(b"\x00", 18, 2048, 2) + _dir_record(b"\x01", 18, 2048, 2) + _dir_record(b"SYSTEM.CNF;1", 19, len(BODY))
    pvd = bytearray(2048)
    pvd[0:6] = b"\x01CD001"
    pvd[156:190] = _dir_record(b"\x00", 18, 2048, 2)[:34]
    return [bytes(2048)] * 16 + [bytes(pvd), bytes(2048), root.ljust(2048, b"\0"), BODY.ljust(2048, b"\0")]


def plain_image() -> bytes:
    return b"".join(_sectors())


def raw_image() -> bytes:
    return b"".join(b"\0" * 24 + s + b"\0" * 280 for s in _sectors())


def test_both_forms_give_the_same_file(tmp_path):
    (tmp_path / "raw.bin").write_bytes(raw_image())
    (tmp_path / "plain.iso").write_bytes(plain_image())
    a, b = disc.Ps2Disc(tmp_path / "raw.bin"), disc.Ps2Disc(tmp_path / "plain.iso")
    assert (a.form, b.form) == (disc.RAW, disc.PLAIN)
    assert a.read("SYSTEM.CNF") == b.read("SYSTEM.CNF") == BODY
    assert [e.path for e in a.entries()] == [e.path for e in b.entries()] == ["SYSTEM.CNF"]


def test_form_is_decided_by_content_not_suffix(tmp_path):
    (tmp_path / "plain.bin").write_bytes(plain_image())
    (tmp_path / "raw.iso").write_bytes(raw_image())
    assert disc.Ps2Disc(tmp_path / "plain.bin").read("SYSTEM.CNF") == BODY
    assert disc.Ps2Disc(tmp_path / "raw.iso").read("SYSTEM.CNF") == BODY


@pytest.mark.parametrize("make,track", [(raw_image, "t.bin"), (plain_image, "t.iso")])
def test_cue_resolves_to_its_track_first(tmp_path, make, track):
    (tmp_path / track).write_bytes(make())
    (tmp_path / "t.cue").write_text(f'FILE "{track}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    assert disc.Ps2Disc(tmp_path / "t.cue").read("SYSTEM.CNF") == BODY


def test_neither_form_names_the_file(tmp_path):
    p = tmp_path / "notadisc.iso"
    p.write_bytes(bytes(40 * 2048))
    with pytest.raises(IsoError, match="notadisc.iso") as e:
        disc.Ps2Disc(p)
    assert "CD001" in str(e.value)


def test_image_shorter_than_the_descriptor_raises_iso_error(tmp_path):
    p = tmp_path / "tiny.iso"
    p.write_bytes(b"\0" * 100)
    with pytest.raises(IsoError, match="tiny.iso"):
        disc.Ps2Disc(p)


@pytest.mark.parametrize("make,keep", [(plain_image, 19 * 2048 + 100), (raw_image, 19 * 2352 + 100)])
def test_truncated_image_raises_iso_error(tmp_path, make, keep):
    p = tmp_path / "cut.img"
    p.write_bytes(make()[:keep])                  # the file's data sector is cut short
    d = disc.Ps2Disc(p)
    with pytest.raises(IsoError, match="cut.img"):
        d.read("SYSTEM.CNF")


@pytest.mark.parametrize("make,name", [(raw_image, "a.bin"), (plain_image, "a.iso")])
def test_check_ps2_reads_either_form(tmp_path, make, name):
    (tmp_path / name).write_bytes(make())
    problems, notes = pack.check_ps2(tmp_path / name)
    assert not any("not a PS2 disc image" in x for x in problems)
    assert any("SLPM_624.43" in n for n in notes)
