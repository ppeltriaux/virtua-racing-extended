import struct

import pytest

from vrtools.arcade.race import (RACE_BLOB_BYTES, RaceBlob, TimeRecord, car_table, checkpoints, encode_car_table,
                                 encode_checkpoints, encode_race_blob, encode_time_record, race_blob_layout, time_record)
from vrtools.arcade.romset import RomSet


def test_time_records_match_the_recon(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    assert time_record(rs, 0, 2, 0) == TimeRecord(2080, (331,) * 23)        # Big Forest, normal, level 0
    assert time_record(rs, 0, 1, 2).extensions == (468,) * 23 and time_record(rs, 0, 1, 2).initial == 1760
    assert time_record(rs, 1, 0, 3) == TimeRecord(1600, (343,) * 23)
    assert time_record(rs, 2, 2, 0).initial == 8320
    r = time_record(rs, 0, 0, 1)
    assert encode_time_record(r) == rs.boot[0xFCE1AD - 0xFC0000:0xFCE1AD - 0xFC0000 + 96]


def test_checkpoints_and_car_table_match_the_recon(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    assert checkpoints(rs, 0) == (0, 112, 221) and checkpoints(rs, 1) == (0, 210, 423) and checkpoints(rs, 2) == (0, 120, 230)
    assert encode_checkpoints((0, 120, 230)) == rs.boot[0xFCF199 - 0xFC0000:0xFCF199 - 0xFC0000 + 16]
    cars = car_table(rs, 0)
    assert len(cars) == 16 and cars[0].line == 0 and cars[0].start_point == 0 and cars[0].perf == pytest.approx(2.847, abs=0.001)
    assert [c.line for c in cars] == [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 7]
    assert [c.start_point for c in cars] == list(range(16)) and cars[15].perf == pytest.approx(2.786, abs=0.001)
    assert encode_car_table(cars) == rs.boot[0xFCD395 - 0xFC0000:0xFCD395 - 0xFC0000 + 512]
    assert car_table(rs, 1)[8].line == 0                                    # the alternate table pairs lines differently


def test_race_blob_round_trips_through_its_layout(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    blob = RaceBlob({(v, l): time_record(rs, v, 2, l) for v in range(3) for l in range(4)}, (0, 150, 300), car_table(rs, 0))
    base = 0x280000
    data = encode_race_blob(blob, base)
    lay = race_blob_layout(base)
    assert len(data) == RACE_BLOB_BYTES and lay["end"] - base <= RACE_BLOB_BYTES
    ptrs = struct.unpack_from("<12I", data, 0)
    assert ptrs[0] == lay["records"] and ptrs[5] == lay["records"] + 5 * 96      # variant 1 level 1
    assert data[lay["checkpoints"] - base:lay["checkpoints"] - base + 16] == encode_checkpoints((0, 150, 300))
    assert data[lay["cars"] - base:lay["cars"] - base + 512] == encode_car_table(car_table(rs, 0))
    assert lay["cars"] % 4 == 0
