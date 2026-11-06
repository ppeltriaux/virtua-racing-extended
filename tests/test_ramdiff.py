import struct

import pytest

from vrtools.arcade.ramdiff import Diff, Dump, RamDiffError, diff_dumps, find_smooth_vectors, load_dump


def test_load_dump_parses_frame_from_name(tmp_path):
    p = tmp_path / "trace.txt.ram.1250.bin"
    p.write_bytes(b"\x00" * 16)
    d = load_dump(p)
    assert d.frame == 1250 and d.base == 0x500000 and len(d.data) == 16


def test_diff_reports_changed_bytes():
    a = Dump(1, 0x500000, bytes([0, 1, 2, 3]))
    b = Dump(1, 0x500000, bytes([0, 9, 2, 7]))
    assert diff_dumps(a, b) == [Diff(0x500001, 1, 9), Diff(0x500003, 3, 7)]


def test_diff_width_4_reports_dwords():
    a = Dump(1, 0x500000, struct.pack("<II", 1, 2))
    b = Dump(1, 0x500000, struct.pack("<II", 1, 5))
    assert diff_dumps(a, b, width=4) == [Diff(0x500004, 2, 5)]


def test_size_mismatch_raises():
    with pytest.raises(RamDiffError, match="size"):
        diff_dumps(Dump(1, 0, b"\0\0"), Dump(1, 0, b"\0"))


def test_frame_mismatch_raises_unless_allowed():
    a, b = Dump(1, 0, b"\0"), Dump(2, 0, b"\1")
    with pytest.raises(RamDiffError, match="frame"):
        diff_dumps(a, b)
    assert diff_dumps(a, b, allow_frame_mismatch=True) == [Diff(0, 0, 1)]


def test_find_smooth_vectors_picks_monotone_float():
    def dump(frame, x, noise):
        return Dump(frame, 0x500000, struct.pack("<ffff", x, noise, 42.0, -x))
    dumps = [dump(f, 10.0 + 2.5 * i, (-1) ** i * 500.0) for i, f in enumerate(range(100, 160, 10))]
    found = dict(find_smooth_vectors(dumps))
    assert 0x500000 in found and found[0x500000] == pytest.approx([10.0, 12.5, 15.0, 17.5, 20.0, 22.5])
    assert 0x50000C in found                       # decreasing is monotone too
    assert 0x500004 not in found                   # jumps by 1000
    assert 0x500008 not in found                   # constant
