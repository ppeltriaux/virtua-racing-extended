"""Phase 90 fix round 1 (I8): from a failure of tests/test_pack_rate.py to a cut in pack 2's plan (`pack.Ps2Plan.frame_cuts`).

`BELTWAY_CUTS` and each PS2 plan's `frame_records` (arcade/pack.py) are MEASURED values: they were set from MAME runs of the
build they shipped with, and any change to the converter (vrtools/convert/ps2course.py), to the grading (arcade/ps2entry.py) or
to the plans' tiers invalidates them. To redo them:

1. build pack 2 and run `tests/test_pack_rate.py` (RAIN, every course both ways, the parked views included);
2. for a run over RECORDS_MAX, its work folder holds `frames.txt` and `race.txt`: `python -m tests.pack2_cuts <run folder>
   <direction>` (direction "normal" or "reverse") prints each frame over the room -> the player's road point at that frame ->
   the tile cells that view draws (Phase 28's model, `ps2course.visible_cells`) -> a `frame_cuts` entry (direction, first, last
   road point, records to take off those frames' caps: the excess plus MARGIN), adjacent road points merged;
3. add the entries to the course's `frame_cuts` (Beltway: BELTWAY_CUTS), rebuild, run the test again; the grading steps the
   farthest cells of those views down first (`ps2entry.grade`'s far_first);
4. `frame_records` (the cap on every view) is lowered only when the failures are everywhere on a course, by the excess seen.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

MARGIN = 100                    # records taken off a cut view's cap beyond the excess measured
RECORDS_MAX = 10_200            # tests/test_pack_rate.py's room for the rain


def overs(run: Path, records_max: int = RECORDS_MAX) -> list[tuple[int, int, int, list[int]]]:
    """(frame, records, the player's road point, the cells drawn from there) for each frame of `run` over `records_max`."""
    from vrtools.convert.ps2course import visible_cells
    from vrtools.mame.framerate import parse_frame_log
    from vrtools.mame.runner import parse_race_log
    players = parse_race_log(run / "race.txt")[0]
    by_frame = {p.frame: k for k, p in enumerate(players)}
    out = []
    for f in parse_frame_log(run / "frames.txt"):
        if f.records <= records_max:
            continue
        k = by_frame.get(f.frame) or min(range(len(players)), key=lambda i: abs(players[i].frame - f.frame))
        p, q = players[max(0, k - 4)], players[k]
        hx, hz = q.x - p.x, q.z - p.z
        if math.hypot(hx, hz) < 0.5:                   # standing still: the heading from the yaw (1/65536 turn)
            a = q.yaw / 65536 * 2 * math.pi
            hx, hz = math.sin(a), math.cos(a)
        d = math.hypot(hx, hz) or 1.0
        out.append((f.frame, f.records, q.road_point, visible_cells(q.x, q.z, hx / d, hz / d)))
    return out


def cuts(found, direction: str, records_max: int = RECORDS_MAX, margin: int = MARGIN) -> list[tuple[str, int, int, int]]:
    """`frame_cuts` entries for `overs`' frames: one per run of adjacent road points, the largest excess plus `margin`."""
    worst: dict[int, int] = {}
    for _, records, rp, _ in found:
        worst[rp] = max(worst.get(rp, 0), records - records_max)
    out = []
    for rp in sorted(worst):
        if out and rp <= out[-1][2] + 1:
            d, a, _, r = out[-1]
            out[-1] = (d, a, rp, max(r, worst[rp] + margin))
        else:
            out.append((direction, rp, rp, worst[rp] + margin))
    return out


if __name__ == "__main__":
    run, direction = Path(sys.argv[1]), sys.argv[2]
    found = overs(run)
    for frame, records, rp, cells in found:
        print(f"frame {frame}: {records} records at road point {rp}; cells drawn {cells}")
    print("frame_cuts:", cuts(found, direction))
