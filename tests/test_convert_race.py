import pytest

from vrtools.arcade.race import car_table, time_record
from vrtools.arcade.romset import RomSet
from vrtools.convert.geometry import ConvertError
from vrtools.convert.race import GATE_END_GAP, GATE_START_GAP, car_table_for, checkpoints_for, gate_checkpoints, time_records_for


def test_checkpoints_sit_at_thirds_of_the_lap():
    assert checkpoints_for(455) == (0, 152, 303) and checkpoints_for(338) == (0, 113, 225)
    with pytest.raises(ConvertError):
        checkpoints_for(8)


def test_time_records_scale_the_templates_extensions_by_sector_length(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    bf = time_record(rs, 0, 2, 0)                                   # 2080, 331 × 23; BF sectors ~113 points
    r = time_records_for(bf, 338, (0, 120, 230), 455, (0, 152, 303))
    assert r.initial == 2080 and len(r.extensions) == 23
    assert r.extensions[0] == round(331 * 152 / (338 / 3)) == 447 and r.extensions[1] == round(331 * 151 / (338 / 3))
    assert r.extensions[2] == round(331 * 152 / (338 / 3)) and r.extensions[3] == r.extensions[0]      # sectors cycle
    assert time_records_for(bf, 338, (0, 120, 230), 455, (0, 152, 303), factor=1.5).extensions[0] == round(447 * 1.5)
    assert time_records_for(bf, 338, (0, 120, 230), 100, (0, 33, 66)).extensions[0] == 200             # clamp


def test_car_table_pace_scales_the_opponents_only(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    cars = car_table_for(car_table(rs, 0), pace=1.2)
    assert cars[0].perf == pytest.approx(2.847, abs=0.001) and cars[1].perf == pytest.approx(1.736 * 1.2, abs=0.01)
    assert car_table_for(car_table(rs, 0), pace=2.0)[15].perf == pytest.approx(2.847, abs=0.001)       # clamped
    assert [c.line for c in cars] == [c.line for c in car_table(rs, 0)]


def test_laps_are_capped_by_the_time_record():
    """Review (Phase 9): every lap fires three extensions (two checkpoints and the start line) and a record holds 23,
    so more than 7 laps would read past the record into the next level's initial clock."""
    from vrtools.convert.race import max_laps
    assert max_laps((0, 150, 300)) == 7 and max_laps((0, 100)) == 11
    with pytest.raises(ConvertError):
        from vrtools.convert.race import check_laps
        check_laps(8, (0, 150, 300))
    check_laps(5, (0, 150, 300))


def test_the_saturn_gates_are_the_checkpoints():
    """Phase 22e (Pascal: two gates at every checkpoint, the one that fires too narrow; his choice A): every Saturn
    gate (its START/GOAL and its two C.P.) is a checkpoint after the start line, in lap order; a gate at the start
    line itself is the start line's (not counted twice)."""
    assert gate_checkpoints([293, 183, 426], 453) == (0, 183, 293, 426)
    assert gate_checkpoints([13, 149, 282], 441) == (0, 149, 282)            # Surfers Road: the gate 130 units after the start is dropped (22i)
    assert gate_checkpoints([40, 186, 320], 410) == (0, 186, 320)            # Pacific Coast's at 400 units too
    assert gate_checkpoints([GATE_START_GAP - 1, 100, 200], 300) == (0, 100, 200)
    assert gate_checkpoints([100, 200, 300 - GATE_END_GAP + 1], 300) == (0, 100, 200)
    assert gate_checkpoints([127, 299, 382], 387) == (0, 127, 299)              # Phase 22l: the Oval's START gate 50 units before its line
    with pytest.raises(ConvertError):
        gate_checkpoints([], 300)
