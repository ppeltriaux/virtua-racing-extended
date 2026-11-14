"""Race parameters for a converted course (M6): checkpoints at thirds of the lap, time records scaled from the
template's by sector length, and the car table with a pace factor on the opponents. Decision 11 of the design:
the values are a starting point for playtesting; `CoursePlan.time_factor` and `.pace` are the knobs."""
from __future__ import annotations

from vrtools.arcade.race import EXTENSIONS, CarEntry, TimeRecord
from vrtools.convert.geometry import ConvertError

EXTENSION_MIN = 200            # clock units (1/32 s): the shortest and longest extension a converted sector may get
EXTENSION_MAX = 1200
PERF_MIN = 1.0                 # the car table's performance float: opponents 1.736..2.786, the player 2.847
PERF_MAX = 2.847


def checkpoints_for(n_points: int, count: int = 2) -> tuple[int, ...]:
    """The start line and `count` checkpoints at equal fractions of a lap of `n_points` road points."""
    if n_points < 3 * (count + 1):
        raise ConvertError(f"{n_points} road points are too few for {count} checkpoints")
    return (0,) + tuple(round(k * n_points / (count + 1)) for k in range(1, count + 1))


GATE_START_GAP = 50       # a Saturn gate within this many road points (500 units) after the start line is dropped: Phase 22i
                          # (Pascal: "some start right before a checkpoint"): six courses start far from the Saturn's flag, and
GATE_END_GAP = 8          # Surfers Road's, the Oval's and Pacific Coast's first gate sat 130-400 units after our line. A gate
                          # within GATE_END_GAP points before the line is the line's own (Phase 22e's rule; Phase 22l: 3 -> 8,
                          # the Oval's and Surfers Road's START gate stands 50-60 units before their line now)


def gate_checkpoints(gates: list[int], n_points: int, start_gap: int = GATE_START_GAP, end_gap: int = GATE_END_GAP) -> tuple[int, ...]:
    """Phase 22e (Pascal's choice A): the start line and every Saturn gate on the lap (road points), in lap order. A
    gate within `start_gap` points after the start line or `end_gap` before it is left out (the line fires instead)."""
    pts = sorted({g % n_points for g in gates if start_gap <= g % n_points <= n_points - end_gap})
    if not pts:
        raise ConvertError(f"no Saturn gate on the lap of {n_points} points (gates {gates})")
    return (0,) + tuple(pts)


def _sector_lengths(n_points: int, checkpoints: tuple[int, ...]) -> list[int]:
    """Gaps between consecutive checkpoints and from the last one back to the start line."""
    cps = list(checkpoints) + [n_points]
    return [b - a for a, b in zip(cps, cps[1:])]


def lap_total(record: TimeRecord, checkpoints: tuple[int, ...]) -> int:
    """Phase 26 stage 2: the clock a lap adds, the sum of the record's first `len(checkpoints)` extensions (one per
    checkpoint record entry, the start line included)."""
    return sum(record.extensions[:len(checkpoints)])


def time_records_for(template: TimeRecord, template_points: int, template_checkpoints: tuple[int, ...], n_points: int,
                     checkpoints: tuple[int, ...], factor: float = 1.0, lap_total: int | None = None) -> TimeRecord:
    """The template's initial clock; extension k (1-based) belongs to the converted sector `(k - 1) % sectors` and
    equals the template's first extension scaled by that sector's length over the template's mean sector, times
    `factor`, clamped to [EXTENSION_MIN, EXTENSION_MAX]. With `lap_total` (Phase 26 stage 2, plan D4: a reverse lap with
    another number of sectors than the normal one) every raw extension, before rounding and clamping, is also multiplied by
    `lap_total` over the first lap's sum of the record the same call gives without it: equal totals make the factor exactly 1
    and the same record."""
    if len(checkpoints) < 2 or checkpoints[0] != 0 or checkpoints[-1] >= n_points:
        raise ConvertError(f"checkpoints {checkpoints} do not fit a lap of {n_points} points")
    mean = template_points / len(template_checkpoints)
    sectors = _sector_lengths(n_points, checkpoints)

    def extensions(scale: float) -> tuple[int, ...]:
        return tuple(min(EXTENSION_MAX, max(EXTENSION_MIN, round(template.extensions[0] * sectors[k % len(sectors)] / mean * factor * scale)))
                     for k in range(EXTENSIONS))
    plain = extensions(1.0)
    if lap_total is None:
        return TimeRecord(template.initial, plain)
    return TimeRecord(template.initial, extensions(lap_total / sum(plain[:len(checkpoints)])))


def max_laps(checkpoints: tuple[int, ...]) -> int:
    """Every lap fires one extension per checkpoint record entry (the start line included): the record's 23 entries
    bound the race length."""
    return EXTENSIONS // len(checkpoints)


def check_laps(laps: int, checkpoints: tuple[int, ...]) -> None:
    if not (1 <= laps <= max_laps(checkpoints)):
        raise ConvertError(f"{laps} laps need more than the {EXTENSIONS} extensions a time record holds "
                           f"({len(checkpoints)} per lap: at most {max_laps(checkpoints)})")


def car_table_for(original: list[CarEntry], pace: float = 1.0, start_points: tuple[int, ...] | None = None) -> list[CarEntry]:
    """The original car table with the opponents' performance scaled by `pace` (the player, car 0, untouched). With
    `start_points` (Phase 26 stage 2, after the owner's drive: a reverse grid, `tencourse.BANK_ONE_GRID`) car k starts on road
    point `start_points[k]` instead; models, lines and performance stay. The grid may only rearrange the opponents on the
    table's own start points, the player's kept: ConvertError otherwise."""
    if start_points is not None:
        if len(start_points) != len(original) or start_points[0] != original[0].start_point \
                or sorted(start_points[1:]) != sorted(c.start_point for c in original[1:]):
            raise ConvertError(f"start points {start_points} do not rearrange the opponents of the grid "
                               f"{tuple(c.start_point for c in original)}")
    out = [original[0]]
    for k, c in enumerate(original[1:], 1):
        perf = min(PERF_MAX, max(PERF_MIN, c.perf * pace))
        out.append(CarEntry(c.models, c.line, c.start_point if start_points is None else start_points[k], perf))
    return out
