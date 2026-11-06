import math

import pytest

from vrtools.arcade.course import course_table, road_lines
from vrtools.arcade.romset import RomSet
from vrtools.convert.geometry import ConvertError
from vrtools.convert.lap import Lap, arc_of, order_slices, runs
from vrtools.saturn.course import Plane, SaturnCourse, Segment
from tests.test_convert_geometry import _saturn_course


def _slice(index, cx, cz, hx, hz, width=2.5, length=1.0):
    """A rectangular slice (Saturn units) centred at (cx, cz) whose direction of travel is (hx, hz)."""
    n = math.hypot(hx, hz); hx, hz = hx / n, hz / n
    lx, lz = -hz, hx                                   # left-hand lateral
    # planes n.p + d >= 0 inside: back, left, front, right (consecutive so corners() works)
    planes = (Plane(hx, hz, -(hx * (cx - hx * length / 2) + hz * (cz - hz * length / 2))),
              Plane(-lx, -lz, (lx * (cx + lx * width / 2) + lz * (cz + lz * width / 2))),
              Plane(-hx, -hz, (hx * (cx + hx * length / 2) + hz * (cz + hz * length / 2))),
              Plane(lx, lz, -(lx * (cx - lx * width / 2) + lz * (cz - lz * width / 2))))
    return Segment(index, planes, (0.0, 1.0, 0.0), (0, 0, 0, 0))


def _course(segs):
    return SaturnCourse(None, segs, None, None, {}, {})


def _course_from_centres(centres):
    return _course([_slice(i, x, z, 0, 1) for i, (x, z) in enumerate(centres)])


def _square_loop(n_per_side=10, broken_into=1, displace_run=None, by=0.0):
    """A circular lap of 4*n slices (gradual turns, like a real road) stored as `broken_into` runs in shuffled order."""
    n = 4 * n_per_side
    radius = n * 1.0 / (2 * math.pi)
    pts = []
    for i in range(n):
        a = 2 * math.pi * (i + 0.5) / n
        pts.append((radius * math.cos(a), radius * math.sin(a), -math.sin(a), math.cos(a)))   # centre, direction (counter-clockwise)
    cut = [0] + sorted({(n * k) // broken_into for k in range(1, broken_into)}) + [n]
    chunks = [pts[a:b] for a, b in zip(cut, cut[1:])]
    order = [0] + list(range(len(chunks) - 1, 0, -1))          # first run first, the rest reversed
    segs = []
    for ci in order:
        for x, z, hx, hz in chunks[ci]:
            if displace_run is not None and ci == displace_run:
                x += by
            segs.append(_slice(len(segs), x, z, hx, hz))
    expected = []
    base = 0
    starts = {}
    for ci in order:
        starts[ci] = base; base += len(chunks[ci])
    for ci in range(len(chunks)):
        expected.extend(range(starts[ci], starts[ci] + len(chunks[ci])))
    return _course(segs), expected


def test_runs_split_on_gaps():
    sat = _course_from_centres([(0, 0), (0, 1), (0, 2), (5, 9), (5, 10)])
    assert runs(sat) == [[0, 1, 2], [3, 4]]


def test_order_joins_runs_into_a_cycle():
    sat, expected = _square_loop(n_per_side=10, broken_into=3)
    lap = order_slices(sat, start_slice=0)
    assert isinstance(lap, Lap) and len(lap.order) == 40 and lap.order[0] == 0
    assert lap.order == expected
    assert lap.arc[0] == 0 and lap.arc[-1] < lap.length and abs(lap.length - 40 * 11.7) < 3 * 11.7


def test_order_reports_an_unjoinable_run():
    sat, _ = _square_loop(n_per_side=10, broken_into=3, displace_run=1, by=12.0)    # beyond the 8-unit merge reach
    with pytest.raises(ConvertError, match="slice"):
        order_slices(sat, start_slice=0)


def test_arc_of_nearest_centre():
    sat, _ = _square_loop(n_per_side=10)
    lap = order_slices(sat, start_slice=0)
    x0, z0 = lap.centres[0]
    assert arc_of(lap, x0 + 3, z0 - 3) == pytest.approx(0.0, abs=12)


def _arcade_lap_length(c):
    return sum(math.hypot(b.x - a.x, b.z - a.z) for a, b in zip(c, c[1:])) + math.hypot(c[0].x - c[-1].x, c[0].z - c[-1].z)


@pytest.mark.parametrize("course,name", [(0, "BIGFORES/TRCKBIGF"), (1, "BAYBRIDG/TRCKBAYB"), (2, "ACROPOLS/TRCKACRO")])
def test_real_lap_follows_the_arcade_centreline(romset_zip, saturn_cue, course, name):
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, name)
    lap = order_slices(sat)
    c = road_lines(rs, course_table(rs)[course])[0]
    arcs = [arc_of(lap, p.x, p.z) for p in c]
    steps = [(b - a) % lap.length for a, b in zip(arcs, arcs[1:])]
    forward = sum(1 for d in steps if d < 40)                   # ties count: arcade points are 10 units apart, slices 11.7
    backward = sum(1 for d in steps if d > lap.length - 40)
    assert forward / len(steps) > 0.97 and backward / len(steps) < 0.02, (forward, backward, len(steps))
    usable = sum(1 for s in sat.segments if s.corners() is not None)
    assert len(lap.order) >= 0.7 * usable                       # the grid / pit lane is a side lane, not part of the lap
    assert abs(lap.length - _arcade_lap_length(c)) / _arcade_lap_length(c) < 0.15   # graph distance zigzags through strips (Bay Bridge +12.6%); Task 5 checks the resampled centreline


def test_truncated_loop_is_rejected_naming_the_missing_run():
    """The last fifth of the loop (stored as slices 8-15) is 12 units off: 32 of 40 slices are reachable, nothing
    just behind the start line is, so the lap does not close and the error names the run."""
    sat, _ = _square_loop(n_per_side=10, broken_into=5, displace_run=4, by=12.0)
    with pytest.raises(ConvertError, match=r"slices 8.15"):
        order_slices(sat, start_slice=0)
    with pytest.raises(ConvertError, match=r"slices 8.15"):
        order_slices(sat, start_slice=0, min_coverage=0.5)              # even with the coverage gate lowered


@pytest.mark.parametrize("name,min_cov", [("PACCOAST/TRCKPACC", 0.98), ("SPEEDWAY/TRCKSPEE", 0.8), ("SURFER00/TRCKSURF", 0.98)])   # the oval file carries the unused infield (112 slices)
def test_touching_runs_order_into_a_lap(saturn_cue, name, min_cov):
    """Pacific Coast's 300-slice run and Surfers Oval's infield join the rest of the road by touching polygons
    (polygon gap 0.00) without a shared edge; the only edge-sharing junction is the start line, which the cut
    severs. Touching polygons must be adjacent too."""
    from tests.test_convert_geometry import _saturn_course
    sat = _saturn_course(saturn_cue, name)
    rep = {}
    lap = order_slices(sat, report=rep, min_coverage=min_cov)
    usable = sum(1 for s in sat.segments if s.corners() is not None)
    assert len(lap.order) >= min_cov * usable and lap.route and lap.length > 2000
