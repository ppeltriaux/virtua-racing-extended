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


def time_records_for(template: TimeRecord, template_points: int, template_checkpoints: tuple[int, ...], n_points: int,
                     checkpoints: tuple[int, ...], factor: float = 1.0) -> TimeRecord:
    """The template's initial clock; extension k (1-based) belongs to the converted sector `(k - 1) % sectors` and
    equals the template's first extension scaled by that sector's length over the template's mean sector, times
    `factor`, clamped to [EXTENSION_MIN, EXTENSION_MAX]."""
    if len(checkpoints) < 2 or checkpoints[0] != 0 or checkpoints[-1] >= n_points:
        raise ConvertError(f"checkpoints {checkpoints} do not fit a lap of {n_points} points")
    mean = template_points / len(template_checkpoints)
    sectors = _sector_lengths(n_points, checkpoints)
    ext = []
    for k in range(EXTENSIONS):
        v = round(template.extensions[0] * sectors[k % len(sectors)] / mean * factor)
        ext.append(min(EXTENSION_MAX, max(EXTENSION_MIN, v)))
    return TimeRecord(template.initial, tuple(ext))


def max_laps(checkpoints: tuple[int, ...]) -> int:
    """Every lap fires one extension per checkpoint record entry (the start line included): the record's 23 entries
    bound the race length."""
    return EXTENSIONS // len(checkpoints)


def check_laps(laps: int, checkpoints: tuple[int, ...]) -> None:
    if not (1 <= laps <= max_laps(checkpoints)):
        raise ConvertError(f"{laps} laps need more than the {EXTENSIONS} extensions a time record holds "
                           f"({len(checkpoints)} per lap: at most {max_laps(checkpoints)})")


def car_table_for(original: list[CarEntry], pace: float = 1.0) -> list[CarEntry]:
    """The original car table with the opponents' performance scaled by `pace` (the player, car 0, untouched)."""
    out = [original[0]]
    for c in original[1:]:
        perf = min(PERF_MAX, max(PERF_MIN, c.perf * pace))
        out.append(CarEntry(c.models, c.line, c.start_point, perf))
    return out
