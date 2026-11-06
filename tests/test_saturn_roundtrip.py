import struct

import pytest

from vrtools.saturn import course
from vrtools.saturn.course import SaturnCourse, SaturnError, decode_course, encode_course, verify_lossless
from vrtools.saturn.trck import TrckFile

COURSES = ["ACROPOLS/TRCKACRO", "ALPINE00/TRCKALPN", "AMAZON00/TRCKAMAZ", "BAYBRIDG/TRCKBAYB", "BIGFORES/TRCKBIGF",
           "DIABLO00/TRCKDIAB", "METROPOL/TRCKMETR", "PACCOAST/TRCKPACC", "SPEEDWAY/TRCKSPEE", "SURFER00/TRCKSURF"]


def test_encoder_guards():
    with pytest.raises(SaturnError):
        course.to_fx(32768.0)
    with pytest.raises(SaturnError):
        course.encode_grid_params(course.GridParams(40000.0, 0.0, 0.1, 0.1))
    with pytest.raises(SaturnError):
        course.encode_grid(course.Grid([[70000]] + [[]] * 255, [0]), 0x06096000)


def test_verify_lossless_synthetic():
    from tests.test_saturn_course import STRAIGHT, make_trck, seg_record
    secs = {4: seg_record(STRAIGHT), 5: struct.pack(">i", course.to_fx(-20.6)), 6: struct.pack(">i", course.to_fx(-61.9)),
            7: struct.pack(">i", course.to_fx(0.3185)), 8: struct.pack(">i", course.to_fx(0.142))}
    t = make_trck(secs)
    c = decode_course(t)
    assert isinstance(c, SaturnCourse) and len(c.segments) == 1 and c.grid is None
    out = encode_course(c)
    assert out[0xB0] == seg_record(STRAIGHT)
    assert verify_lossless(t.data) == []


@pytest.mark.parametrize("name", COURSES)
def test_all_ten_files_round_trip(saturn_cue, name):
    from vrtools.saturn.iso import Iso2352
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    assert verify_lossless(iso.read(f"VRSRCDIR/TRACKS00/{name}")) == []
