from dataclasses import replace

import pytest

from vrtools.arcade.race import EXTENSIONS, CarEntry, TimeRecord, car_table, time_record
from vrtools.arcade.romset import RomSet
from vrtools.convert.geometry import ConvertError
from vrtools.convert.race import GATE_END_GAP, GATE_START_GAP, car_table_for, checkpoints_for, gate_checkpoints, lap_total, time_records_for


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


T = TimeRecord(2000, (400,) * EXTENSIONS)       # a synthetic template: a mean sector of 150 points, so a 36-point sector is lifted to EXTENSION_MIN
TP, TC = 450, (0, 150, 300)


def test_a_reverse_lap_gets_the_normal_laps_total():
    """Phase 26 stage 2 (plan D4): four sectors one way, three the other: Diablo Canyon's shapes (stage 2's first reverse build,
    and again since stage 3 Task 8, Pascal's choice of 13 Nov: `reverse.reverse_checkpoints` drops the START arch 36 points after
    the reverse line, so the normal lap's total is spread over three reverse sectors)."""
    normal = time_records_for(T, TP, TC, 457, (0, 179, 289, 421))
    total = lap_total(normal, (0, 179, 289, 421))
    plain = time_records_for(T, TP, TC, 457, (0, 168, 278))
    scaled = time_records_for(T, TP, TC, 457, (0, 168, 278), lap_total=total)
    assert lap_total(plain, (0, 168, 278)) < total                       # the dropped gate's sector was lifted to EXTENSION_MIN
    assert abs(lap_total(scaled, (0, 168, 278)) - total) <= 3
    assert scaled.initial == plain.initial and scaled.extensions[3:6] == scaled.extensions[0:3]


def test_the_same_sectors_in_another_order_are_not_rescaled():
    normal = time_records_for(T, TP, TC, 365, (0, 122, 226))
    rev = (0, 139, 243)                                                   # the same three lengths reversed
    assert time_records_for(T, TP, TC, 365, rev, lap_total=lap_total(normal, (0, 122, 226))) == time_records_for(T, TP, TC, 365, rev)


# The car table's layout (docs/formats/model1-course-tables.md §4; stage 2 findings §11.5): the player on line 0, opponents 1-2 on
# line 1, 3-4 line 2, 5-6 line 3, 7-8 line 4, 9-10 line 5, 11-12 line 6, 13-15 line 7; car k starts on road point k.
CAR_LINES = (0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 7)
SYNTHETIC_CARS = [CarEntry((k, k + 1, k + 2, k + 3, k + 4), CAR_LINES[k], k, 2.0 + k / 100) for k in range(16)]   # synthetic models, perf


def test_a_reverse_grid_moves_the_start_points_only():
    """Phase 26 stage 2, after the owner's drive: `start_points` rearranges the opponents on the grid; models, lines,
    performance (paced) and the player stay those of the table without it."""
    from vrtools.arcade.tencourse import BANK_ONE_GRID
    plain = car_table_for(SYNTHETIC_CARS, pace=1.1)
    grid = car_table_for(SYNTHETIC_CARS, pace=1.1, start_points=BANK_ONE_GRID)
    assert [c.start_point for c in grid] == list(BANK_ONE_GRID)
    assert [replace(c, start_point=0) for c in grid] == [replace(c, start_point=0) for c in plain]
    assert grid[0] == plain[0] == SYNTHETIC_CARS[0]
    assert car_table_for(SYNTHETIC_CARS, start_points=tuple(range(16))) == car_table_for(SYNTHETIC_CARS)
    for bad in ((1, 0) + tuple(range(2, 16)),            # the player moved
                (0,) + tuple(range(2, 17)),              # a point the grid does not have
                tuple(range(15)),                        # a car short
                (0, 1, 1) + tuple(range(3, 16))):        # two cars on one point
        with pytest.raises(ConvertError):
            car_table_for(SYNTHETIC_CARS, start_points=bad)
