"""Tests for the 2352-byte MODE1 ISO9660 reader using a synthetic image."""

import struct
from pathlib import Path

import pytest

from vrtools.saturn.iso import Iso2352

SECTOR = 2048
RAW = 2352


def _record(name: str, extent: int, size: int, flags: int = 0) -> bytes:
    ident = name.encode("ascii") if name not in ("\x00", "\x01") else name.encode("latin-1")
    length = 33 + len(ident)
    if length % 2:
        length += 1
    rec = bytearray(length)
    rec[0] = length
    rec[2:6] = struct.pack("<I", extent)
    rec[6:10] = struct.pack(">I", extent)
    rec[10:14] = struct.pack("<I", size)
    rec[14:18] = struct.pack(">I", size)
    rec[25] = flags
    rec[32] = len(ident)
    rec[33:33 + len(ident)] = ident
    return bytes(rec)


def _wrap(sectors: list[bytes]) -> bytes:
    out = bytearray()
    for i, data in enumerate(sectors):
        assert len(data) == SECTOR
        out += b"\x00" + b"\xff" * 10 + b"\x00" + bytes([0, 2, i & 0xFF, 1])  # 12-byte sync + 4-byte header
        out += data
        out += b"\x00" * 288
    return bytes(out)


def make_image(files: dict[str, bytes]) -> bytes:
    """ISO9660 image: PVD at 16, root dir at 18 (as many sectors as needed), files after."""
    names = list(files)
    # directory records: '\x00', '\x01', then one per file (with ';1' suffix as on real discs)
    dir_records = [_record("\x00", 18, 0, 2), _record("\x01", 18, 0, 2)]
    # lay out the directory first to know how many sectors it takes
    tmp = [_record(f"{n};1", 0, len(files[n])) for n in names]
    dir_bytes = bytearray()
    for rec in dir_records + tmp:
        if (len(dir_bytes) % SECTOR) + len(rec) > SECTOR:        # pad to next sector
            dir_bytes += b"\x00" * (SECTOR - len(dir_bytes) % SECTOR)
        dir_bytes += rec
    dir_sectors = (len(dir_bytes) + SECTOR - 1) // SECTOR
    first_file_lba = 18 + dir_sectors
    # now assign extents
    extents = {}
    lba = first_file_lba
    for n in names:
        extents[n] = lba
        lba += max(1, (len(files[n]) + SECTOR - 1) // SECTOR)
    dir_bytes = bytearray()
    for rec in dir_records + [_record(f"{n};1", extents[n], len(files[n])) for n in names]:
        if (len(dir_bytes) % SECTOR) + len(rec) > SECTOR:
            dir_bytes += b"\x00" * (SECTOR - len(dir_bytes) % SECTOR)
        dir_bytes += rec
    dir_bytes += b"\x00" * (dir_sectors * SECTOR - len(dir_bytes))

    pvd = bytearray(SECTOR)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    root = _record("\x00", 18, dir_sectors * SECTOR, 2)
    pvd[156:156 + len(root)] = root

    sectors = [bytes(SECTOR)] * 16 + [bytes(pvd), bytes(SECTOR)]  # 0..15 blank, 16 PVD, 17 terminator
    for i in range(dir_sectors):
        sectors.append(bytes(dir_bytes[i * SECTOR:(i + 1) * SECTOR]))
    for n in names:
        data = files[n]
        padded = data + b"\x00" * ((-len(data)) % SECTOR or 0)
        if not padded:
            padded = bytes(SECTOR)
        for i in range(0, len(padded), SECTOR):
            sectors.append(padded[i:i + SECTOR])
    return _wrap(sectors)


@pytest.fixture
def image(tmp_path) -> Path:
    p = tmp_path / "track01.bin"
    p.write_bytes(make_image({"A.BIN": b"x" * 5000, "B.TXT": b"hi"}))
    return p


def test_entries_strip_version_and_skip_dirs(image):
    iso = Iso2352(image)
    assert {e.path for e in iso.entries()} == {"A.BIN", "B.TXT"}


def test_read_spans_multiple_sectors(image):
    iso = Iso2352(image)
    assert iso.read("A.BIN") == b"x" * 5000
    assert iso.read("B.TXT") == b"hi"


def test_directory_padding_skips_to_next_sector(tmp_path):
    files = {f"F{i:03d}.DAT": bytes([i]) for i in range(64)}   # 64 records > one 2048-byte sector
    p = tmp_path / "big.bin"
    p.write_bytes(make_image(files))
    iso = Iso2352(p)
    assert len(iso.entries()) == 64
    assert iso.read("F063.DAT") == bytes([63])


def test_extract_all_excludes_pattern(tmp_path, image):
    out = tmp_path / "out"
    n = Iso2352(image).extract_all(out, exclude=("B.",))
    assert n == 1
    assert (out / "A.BIN").read_bytes() == b"x" * 5000
    assert not (out / "B.TXT").exists()


def test_real_disc_listing(saturn_cue):
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    sizes = {e.path.rsplit("/", 1)[-1]: e.size for e in iso.entries()}
    assert sizes["TRCKALPN"] == 422132
    assert sizes["TRCKBIGF"] == 396320
    assert sizes["VRCODELO"] == 122772
    assert len(iso.entries()) == 158
    assert sum(1 for e in iso.entries() if "MOVIE" in e.path) == 31
