import struct
import zlib

import pytest

from vrtools.arcade.romset import REQUIRED_FILES, RomSet, RomSetError

N = 8  # tiny synthetic ROM size


def _files(**override):
    files = {name: bytes([i + 1] * N) for i, name in enumerate(REQUIRED_FILES)}
    files.update(override)
    return files


def test_program_interleaves_byte_lanes():
    a, b = bytes(range(0, N)), bytes(range(0x10, 0x10 + N))
    rs = RomSet.from_files(_files(**{"epr-14882.14": a, "epr-14883.15": b}))
    assert rs.program[:4] == bytes([0x00, 0x10, 0x01, 0x11])
    assert len(rs.program) == 2 * N


def test_boot_and_data_lanes():
    rs = RomSet.from_files(_files(**{"epr-14878a.4": b"A" * N, "epr-14879a.5": b"B" * N,
                                     "mpr-14880.6": b"a" * N, "mpr-14881.7": b"b" * N,
                                     "mpr-14888.12": b"y" * N, "mpr-14889.13": b"z" * N}))
    assert rs.boot == b"A" * N + b"B" * N                 # ROM_LOAD: the two boot chips are flat and consecutive (0xfc0000, 0xfe0000)
    assert rs.data[:4] == b"abab"
    assert rs.data[-4:] == b"yzyz"
    assert len(rs.data) == 8 * N


def test_polygons_are_32bit_words_from_two_roms():
    a = bytes([0xA0, 0xA1, 0xA2, 0xA3] + [0] * (N - 4))
    b = bytes([0xB0, 0xB1, 0xB2, 0xB3] + [0] * (N - 4))
    rs = RomSet.from_files(_files(**{"mpr-14890.26": a, "mpr-14891.27": b}))
    assert rs.polygons[:8] == bytes([0xA0, 0xA1, 0xB0, 0xB1, 0xA2, 0xA3, 0xB2, 0xB3])
    assert len(rs.polygons) == 4 * 2 * N          # four pairs, no padding in synthetic mode
    assert rs.poly_word(0) == 0xB1B0A1A0
    assert rs.poly_float(0) == struct.unpack("<f", bytes([0xA0, 0xA1, 0xB0, 0xB1]))[0]


def test_copro_data_four_byte_lanes():
    rs = RomSet.from_files(_files(**{"mpr-14898.39": b"a" * N, "mpr-14899.40": b"b" * N,
                                     "mpr-14900.41": b"c" * N, "mpr-14901.42": b"d" * N}))
    assert rs.copro_data[:8] == b"abcdabcd"


def test_read_v60_maps_regions():
    rs = RomSet.from_files(_files(**{"epr-14882.14": b"P" * N, "epr-14883.15": b"p" * N,
                                     "epr-14878a.4": b"B" * N, "epr-14879a.5": b"b" * N,
                                     "mpr-14880.6": b"D" * N, "mpr-14881.7": b"d" * N}))
    assert rs.read_v60(0x200000, 2) == b"Pp"
    assert rs.read_v60(0xFC0000 + 2, 2) == b"BB"
    assert rs.read_v60(0xFC0000 + N, 2) == b"bb"              # the second boot chip follows the first
    assert rs.read_v60(0x1000000, 4) == b"DdDd"
    with pytest.raises(RomSetError):
        rs.read_v60(0x500000, 1)


def test_missing_files_listed_in_error():
    files = _files()
    del files["mpr-14897.33"]
    del files["315-5573.bin"]
    with pytest.raises(RomSetError, match="mpr-14897.33") as e:
        RomSet.from_files(files)
    assert "315-5573.bin" in str(e.value)


def test_old_dump_names_rejected(tmp_path):
    import zipfile
    p = tmp_path / "vr.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("vr-tgp.bin", b"\0" * 8)
        z.writestr("mpr-14879.33", b"\0" * 8)
    with pytest.raises(RomSetError, match="mpr-14897.33"):
        RomSet.from_zip(p)


def test_dump_regions_writes_named_files(tmp_path):
    rs = RomSet.from_files(_files())
    written = rs.dump_regions(tmp_path)
    assert {p.name for p in written} == {"v60_program.bin", "v60_boot.bin", "v60_data.bin",
                                         "polygons.bin", "copro_data.bin", "tgp_program.bin"}
    assert (tmp_path / "v60_program.bin").stat().st_size == 2 * N


def test_real_romset(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    assert len(rs.program) == 1 << 20
    assert rs.program[0x78D70:0x78D70 + 0x17290] == b"\xff" * 0x17290
    assert len(rs.polygons) == 16 << 20
    rom_a = bytearray(2 << 20)                      # rebuild mpr-14890.26 from the word lanes
    rom_a[0::2] = rs.polygons[0:4 << 20:4]
    rom_a[1::2] = rs.polygons[1:4 << 20:4]
    assert zlib.crc32(rom_a) == 0xDCBE006B
    assert zlib.crc32(rs.copro_data[0::4]) == 0x61DA2BB6
    assert zlib.crc32(rs.tgp_program) == 0x3335A19B


def test_pair_size_mismatch_rejected():
    files = _files(**{"mpr-14890.26": b"\0" * N, "mpr-14891.27": b"\0" * (N - 2)})
    with pytest.raises(RomSetError, match="mpr-14891.27"):
        RomSet.from_files(files)


def test_lane_size_mismatch_rejected():
    files = _files(**{"mpr-14900.41": b"\0" * (N - 2)})
    with pytest.raises(RomSetError, match="mpr-14900.41"):
        RomSet.from_files(files)


def test_zip_wrong_size_and_crc_reported(tmp_path):
    import zipfile
    from vrtools.arcade.romset import EXPECTED
    p = tmp_path / "vr.zip"
    with zipfile.ZipFile(p, "w") as z:
        for name, (size, crc) in EXPECTED.items():
            z.writestr(name, b"\0" * (size if name != "epr-14882.14" else 16))   # wrong size for one, wrong CRC for all
    with pytest.raises(RomSetError) as e:
        RomSet.from_zip(p)
    msg = str(e.value)
    assert "epr-14882.14" in msg and "size" in msg
    assert "mpr-14890.26" in msg and "crc" in msg.lower()


def test_expected_table_covers_required_files():
    from vrtools.arcade.romset import EXPECTED
    assert set(EXPECTED) == set(REQUIRED_FILES)
