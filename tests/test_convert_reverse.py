"""Phase 26: a course's road tables read backwards from the same start line (vrtools/convert/reverse.py)."""
import math

import pytest

from vrtools.arcade.bank import line_turn
from vrtools.arcade.course import RoadPoint
from vrtools.arcade.tgp import Quad16
from vrtools.convert.collision import PIT_LANE_HALF_WIDTH, SEAM_OVERLAP
from vrtools.convert.geometry import ConvertError
from vrtools.convert.race import GATE_START_GAP
from vrtools.convert.reverse import reverse_checkpoints, reverse_points, reverse_quad, reverse_segments, reverse_tables
from vrtools.convert.road import RoadTables, road_tables, segment_credits, segment_links
from tests.test_convert_road import _credited_its_front, _cursor_stop, _hi, _ring_lap_with_slices, _ring_quads, _s16

N = 60


def _forward_and_reverse():
    lap, _ = _ring_lap_with_slices(n=N, spacing=10.0)
    quads = _ring_quads(lap, length=14.0)
    t = road_tables(lap, quads, spacing=10.0, attitude=[(3 * k - 90, 2 * k - 60) for k in range(N)])
    return quads, t, reverse_tables(t, quads)


def test_reversed_points_keep_the_start_line():
    assert reverse_points([0, 1, 2, 3, 4]) == [0, 4, 3, 2, 1]
    assert reverse_points(reverse_points([0, 1, 2, 3, 4])) == [0, 1, 2, 3, 4]


def test_a_reversed_quad_swaps_front_and_rear():
    c = tuple((float(i), 0.0, float(i * i)) for i in range(4))
    for attr, want in ((0xFFFFFFF9, 0x7FF9), (0x0DC5, 0xFFFF8DC5)):
        q = Quad16(c, (1.0, 2.0, 3.0), attr)
        r = reverse_quad(q)
        assert r.corners == (c[2], c[3], c[0], c[1]) and r.centre == q.centre and r.attr == want
    q = Quad16(c, (1.0, 2.0, 3.0), 0xFFFFFFF9)
    assert reverse_quad(reverse_quad(q)).corners == q.corners
    assert reverse_quad(reverse_quad(q)).attr == q.attr
    q = Quad16(c, (1.0, 2.0, 3.0), 0x0DC5)
    assert reverse_quad(reverse_quad(q)).attr == 0x0DC5


def test_reversed_lines_are_the_same_points_from_the_same_line():
    quads, t, r = _forward_and_reverse()
    assert len(r.lines) == 8
    for L in range(8):
        assert len(r.lines[L]) == N
        for j in range(N):
            f = t.lines[L][(N - j) % N]
            assert (r.lines[L][j].x, r.lines[L][j].z) == (f.x, f.z)
    for j in range(N):
        f = t.lines[0][(N - j) % N]
        assert (_hi(r.lines[0][j].heading) - _hi(f.heading)) % 16384 == 8192
        assert _s16(r.lines[0][j].heading & 0xFFFF) == -_s16(f.heading & 0xFFFF)
        assert _s16(r.lines[0][j].link & 0xFFFF) == -_s16(f.link & 0xFFFF)
        for L in range(1, 8):
            assert r.lines[L][j].heading == r.lines[0][j].heading and r.lines[L][j].link == r.lines[0][j].link
    hs = [_hi(p.heading) for p in r.lines[0]]
    assert all(abs(a - b) < 1000 for a, b in zip(hs, hs[1:]))
    assert line_turn(r.lines[0]) == -line_turn(t.lines[0])


def test_reversed_segments_are_credited_by_the_rear_edge():
    quads, t, r = _forward_and_reverse()
    m = len(quads)
    assert [s.index for s in r.segments] == list(range(m)) and all(s.flag == 1 for s in r.segments)
    assert r.segments[m - 1].road_point == 0
    assert r.segments[0].road_point == N - 1                  # the walk's n−1: its rear edge runs through point 0, but it is the
                                                              # ring's only n−1 quad before the line, so D5 is withheld (Task 6)
    rpts = [(p.x, p.z) for p in r.lines[0]]
    for k in range(1, m - 1):
        assert _credited_its_front(rpts, reverse_quad(quads[k]), r.segments[k].road_point), k
    rps = [s.road_point for s in r.segments]
    assert all(a >= b for a, b in zip(rps[1:], rps[2:]))


def _ring_with_breaks(breaks):
    """The N-point ring of spacing 10 and one 16-unit-wide quad per pair of arc lengths in `breaks` (forward order), with
    the walk's reverse credits: (forward centreline, quads, walked credits)."""
    lap, _ = _ring_lap_with_slices(n=N, spacing=10.0)
    r = lap.length / (2 * math.pi)
    at = lambda s, rad: (rad * math.cos(s / r), 0.0, rad * math.sin(s / r))
    quads = []
    for s, e in zip(breaks, breaks[1:] + [lap.length]):                                   # the last quad ends on the line
        c = (at(e, r - 8.0), at(e, r + 8.0), at(s, r + 8.0), at(s, r - 8.0))
        quads.append(Quad16(c, tuple(sum(v[i] for v in c) / 4 for i in range(3)), 0))
    pts, m = lap.centres, len(quads)
    walk = segment_credits(reverse_points(pts), [reverse_quad(q) for q in reversed(quads)])
    return pts, quads, [walk[m - 1 - k].road_point for k in range(m)]


def test_the_quad_under_the_reverse_start_spot_is_credited_point_0():
    """Plan D5 (recon §2, Amazon Falls): the forward-first quad begins SEAM_OVERLAP behind the line, under the spawn on
    point 0, and the walk credits it n−1 (it straddles the line in reverse travel): the player spawned credited the last
    point and its first crossing of the line counted no lap. A quad credited n−1 that contains the start spot is credited
    0 when another quad credited n−1 still holds the centreline before the line (here quad 1, s 6..14, over reversed point
    n−1 at s 10): that one keeps n−1, and every other credit is the walk's."""
    pts, quads, walked = _ring_with_breaks([-SEAM_OVERLAP, 6.0] + [14.0 * k for k in range(1, 43)])
    m = len(quads)
    assert walked[0] == N - 1 and walked[1] == N - 1 and walked[m - 1] == 0      # the walk alone: the spot's quad is n−1
    got = [s.road_point for s in reverse_segments(pts, quads)]
    assert got[0] == 0                                         # under the spot (6 units past the line, SEAM_OVERLAP behind it)
    assert got[1] == N - 1                                     # wholly before the line in reverse travel: still the last point
    assert got[1:] == walked[1:]                               # the last quad also holds the spot but is credited 0 already


def test_the_start_spot_rule_leaves_the_road_a_quad_credited_the_last_point():
    """Stage 2 Task 6 (the lead's ruling): where the quad under the spot is the only one credited n−1 on the centreline
    before the line (Surfers Oval's and Surfers Road's quad 0), D5 is withheld and it keeps n−1: with it credited 0 no car
    was credited n−1 at any reverse crossing, the opponents' line cursors stayed on n−1 after the wrap and the field
    stopped at the line (parked 10 and 5 of 15). Here quad 0 runs from SEAM_OVERLAP behind the line to s 12, past reversed
    point n−1 (s 10), and quad 1 (s 12..26) does not reach it."""
    pts, quads, walked = _ring_with_breaks([-SEAM_OVERLAP, 12.0] + [12.0 + 14.0 * k for k in range(1, 42)])
    m = len(quads)
    assert walked[0] == N - 1 and walked[1] == N - 2 and walked[m - 1] == 0      # quad 0 alone carries n−1
    assert [s.road_point for s in reverse_segments(pts, quads)] == walked


def test_reversed_links_name_the_segment_ahead():
    quads, t, r = _forward_and_reverse()
    rps = [s.road_point for s in r.segments]
    named = [r.segments[p.link >> 16].road_point for p in r.lines[1]]
    for p in range(N):
        assert named[p] == min((c for c in rps if c >= p), default=max(rps)), p     # past the greatest credit: the greatest
                                                                                     # (the ring's n−1 quad, kept by Task 6's rule)
    for c in sorted(set(rps))[:-1]:
        assert _cursor_stop(named, c, start=0) == c + 1, c


# The seven converted courses: road points, the normal blob's checkpoints (decoded from the conversion's blobs, the playtest
# set out/p26play4) and the reverse checkpoints under Task 8's rule (tests/test_reverse_build.py's REVERSE_CHECKPOINTS).
SEVEN = {"Alpine": (452, (0, 65, 192, 333), (0, 119, 260, 387)),
         "Amazon Falls": (330, (0, 117, 237), (0, 93, 213)),
         "Diablo Canyon": (457, (0, 179, 289, 421), (0, 168, 278)),
         "Metropolis": (365, (0, 126, 222), (0, 143, 239)),
         "Pacific Coast": (410, (0, 186, 320), (0, 90, 224)),
         "Surfers Oval": (387, (0, 127, 299), (0, 88, 260)),
         "Surfers Road": (441, (0, 127, 299), (0, 142, 314))}


def test_reverse_checkpoints_are_the_normal_ones_renumbered_less_any_just_after_the_line():
    """Phase 26 stage 3 Task 8 (Pascal, 13 Nov, after driving stage 3's set; it replaces their stage 2 drive choice): the
    normal lap's checkpoints renumbered for the reversed lap, (n − g) mod n sorted, the line 0 staying 0, less any renumbered
    point p with 0 < p < GATE_START_GAP (Phase 22i's rule applied in reverse as it is forward: the line fires instead).
    Diablo Canyon's START arch, forward point 421 of 457, 36 points after the reverse start, stays scenery and fires nothing."""
    assert reverse_checkpoints((0, 179, 289, 421), 457) == (0, 168, 278)
    assert reverse_checkpoints((0, 126, 222), 365) == (0, 143, 239)
    assert reverse_checkpoints((0, 100, 300 - GATE_START_GAP), 300) == (0, GATE_START_GAP, 200)       # 50 after the line: kept
    assert reverse_checkpoints((0, 100, 300 - GATE_START_GAP + 1), 300) == (0, 200)                   # 49 after the line: dropped


def test_the_six_other_courses_keep_their_reverse_checkpoints():
    """Only Diablo Canyon has a normal checkpoint within GATE_START_GAP points before its line: the six others' reverse sets
    are stage 2's, each the normal set renumbered."""
    for name, (n, normal, rev) in SEVEN.items():
        assert reverse_checkpoints(normal, n) == rev, name
        if name != "Diablo Canyon":
            assert rev == tuple(sorted((n - g) % n for g in normal)), name


def test_no_reverse_checkpoint_fires_that_does_not_fire_forward():
    """Every reverse checkpoint is a normal one renumbered; reversing twice gives the normal set back only where no point was
    dropped (a point the rule dropped in reverse does not come back)."""
    for cps, n in (((0, 126, 222), 365), ((0, 179, 289, 421), 457), ((0, 1, 2), 10), ((0, 60, 140), 200)):
        rev = reverse_checkpoints(cps, n)
        assert set(rev) <= {(n - g) % n for g in cps}
        dropped = [g for g in cps if 0 < (n - g) % n < GATE_START_GAP]
        if not dropped:
            assert reverse_checkpoints(rev, n) == cps
    assert reverse_checkpoints(reverse_checkpoints((0, 179, 289, 421), 457), 457) == (0, 179, 289)


def test_a_heading_past_16_bits_is_refused():
    quads, t, _ = _forward_and_reverse()
    lines = [[RoadPoint(p.x, p.z, ((700 * k) << 16) | (p.heading & 0xFFFF), p.link) for k, p in enumerate(line)] for line in t.lines]
    with pytest.raises(ConvertError):
        reverse_tables(RoadTables(lines, t.segments), quads)


# --- Phase 26 stage 4 (Task 2): the reverse pit pair and box ---------------------------------------------------------------
# In reverse the car meets the normal pit EXIT first, enters the lane there, and the game's own pit sequence takes it backwards
# up the lane to the box. The game starts a stop on a logic frame where the car's lap-position quad is the record's pit quad q
# or q + 1 with the car heading within 90 degrees of the quad's direction (recon §1.1): both are lane quads, the parked car
# stands on neither (recon §3 item 2: Alpine's first pair 242/243 held the box and a second stop began at once), no road line
# runs inside them (a car racing the road would be pulled in), and the straight run from the pair to the box is long enough to
# park (decision L3; Metropolis's 26 units circled the box, recon §3). The rules are the session lead's ruling of 14 Nov (Task 2,
# after its first STOP: the plan's "8 units from all eight lines" excluded the recon's driven pairs on Alpine and Metropolis,
# whose 9.9 was measured against lines 0 and 6): hard rules H1-H5, then the choice C1-C4 in order (`reverse.reverse_pit`).

ROAD_CLEAR = 8.0            # C2: a clear pair lies at least this far from all eight road lines ...
EXIT_CLEAR = 10.0           # ... and its quads' feet at least this far from the lane's exit end
COVER_TIE = 0.05            # C3: covers within this of the best count as equal, and C4 decides among them (the lead, 14 Nov)
SIX_BOXES = ("ALPINE", "AMAZON FALLS", "DIABLO CANYON", "PACIFIC COAST", "SURFERS OVAL", "SURFERS ROAD")
PIT_COURSES = SIX_BOXES + ("METROPOLIS",)
_PIT_BUILDS: dict = {}
_PITS: dict = {}


def _pit_builds(romset_zip, saturn_cue):
    """Per converted course: (sat, placement, lap, col, centreline, height) as `tencourse.convert_course` makes them, once per
    session, through the builder it uses (`tencourse.course_placement` and `course_collision`): convert_course builds the whole
    course (scenery, blobs) and returns no collision. The pit quads go into the ROM by index, so the tests must run on the
    build's collision: tests/test_convert_collision.py's fixtures call `saturn_collision` without `lane_points`, `grid_clear`
    and the hidden gates. Task 3 checks the built set against `reverse_pit` of the same conversion."""
    import vrtools.arcade.tencourse as tc
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import placed
    if not _PIT_BUILDS:
        rs = RomSet.from_zip(romset_zip)
        for plan in tc.COURSES:
            sat = tc.load_saturn_course(saturn_cue, plan.path)
            pl = tc.course_placement(rs, sat, plan.template, min_coverage=plan.min_coverage, flag_start=plan.flag_start)
            with placed(pl.angle, pl.tx, pl.tz):
                b = tc.course_collision(sat, pl, plan.template, min_coverage=plan.min_coverage, banking=plan.banking,
                                        camber=plan.camber, lane_points=plan.lane_points)
            _PIT_BUILDS[plan.name] = (b.sat, pl, b.lap, b.col, b.pts, b.hfn)
    return _PIT_BUILDS


def _reverse_pits(romset_zip, saturn_cue):
    """Per converted course: the build's collision, `reverse_pit`'s answer and what the tests measure it against (the normal
    pair and box as the build makes them, the lane's polyline and slices, the eight road lines' points as `road_tables` makes
    them with the collision's lanes, and Metropolis's drawn geometry for the tunnel's roof), once per session."""
    from types import SimpleNamespace
    from vrtools.convert.collision import mesh_heights, pit_box, pit_entry_quad, pit_lane_centres, pit_lane_polygons
    from vrtools.convert.geometry import course_quads, placed
    from vrtools.convert.reverse import reverse_pit
    from vrtools.convert.road import road_tables
    if not _PITS:
        for name, (sat, pl, lap, col, pts, hfn) in _pit_builds(romset_zip, saturn_cue).items():
            with placed(pl.angle, pl.tx, pl.tz):
                rp = reverse_pit(sat, col, pts)
                k = pit_entry_quad(sat, col, pts)
                box = pit_box(sat, col, pts)
                lane = pit_lane_centres(sat, pts)
                polys = [[(p[0], 0.0, p[2]) for p in poly] for poly in pit_lane_polygons(sat)]
                drawn = mesh_heights(course_quads(sat, groups=(0, 1, 2, 3, 4))) if name == "METROPOLIS" else None
            lines = [[(p.x, p.z) for p in line] for line in road_tables(lap, col.quads[:col.n_tarmac], lanes=col.lanes).lines]
            _PITS[name] = SimpleNamespace(sat=sat, col=col, pts=pts, hfn=hfn, rp=rp, k=k, box=box, lane=lane, polys=polys,
                                          lines=lines, drawn=drawn)
    return _PITS


def _seg_dist(x, z, a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dz * dz
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (z - a[1]) * dz) / l2))
    return math.hypot(a[0] + t * dx - x, a[1] + t * dz - z)


def _foot(line, x, z):
    """(arc length from the first point, distance, segment index) of the point of the open polyline `line` nearest (x, z)."""
    best, s0 = None, 0.0
    for i, (a, b) in enumerate(zip(line, line[1:])):
        L = math.dist(a, b)
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - a[0]) * (b[0] - a[0]) + (z - a[1]) * (b[1] - a[1])) / (L * L)))
        d = math.hypot(a[0] + t * (b[0] - a[0]) - x, a[1] + t * (b[1] - a[1]) - z)
        if best is None or d < best[1]:
            best = (s0 + t * L, d, i)
        s0 += L
    return best


def _length(line):
    return sum(math.dist(a, b) for a, b in zip(line, line[1:]))


def _loop_dist(loop, x, z):
    n = len(loop)
    return min(_seg_dist(x, z, loop[i], loop[(i + 1) % n]) for i in range(n))


def _crosses(a, b, c, d):
    o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) <= 0 and o(c, d, a) * o(c, d, b) <= 0


def _quad_to_loop(quad, loop):
    """The least distance in plan from quad's footprint to the closed polyline `loop` (0 where the line enters it)."""
    from vrtools.convert.collision import _point_in_xz
    c = [(p[0], p[2]) for p in quad.corners]
    edges = list(zip(c, c[1:] + c[:1]))
    best, n = math.inf, len(loop)
    for i in range(n):
        a, b = loop[i], loop[(i + 1) % n]
        if _point_in_xz(quad.corners, *a) or any(_crosses(a, b, e, f) for e, f in edges):
            return 0.0
        best = min(best, *(_seg_dist(px, pz, a, b) for px, pz in c), *(_seg_dist(*p, e, f) for p in (a, b) for e, f in edges))
    return best


def _lane_quad(t, i):
    """H1: tarmac quad i's centre lies within the lane's half width of the lane's polyline, nearer it than the race centreline."""
    if not 0 <= i < t.col.n_tarmac:
        return False
    x, z = t.col.quads[i].centre[0], t.col.quads[i].centre[2]
    d = _foot(t.lane, x, z)[1]
    return d < PIT_LANE_HALF_WIDTH and d < _loop_dist(t.pts, x, z)


def _depths(t, q):
    """The lane depths (arc length from the mouth) of the feet of quads q and q + 1's centres on the lane's polyline."""
    return [_foot(t.lane, t.col.quads[i].centre[0], t.col.quads[i].centre[2])[0] for i in (q, q + 1)]


def _run(t, q, box):
    """H5: the straight run to `box` from the nearer of the pair's centres, and whether it is over tarmac every 4 units (as
    `collision.pit_box`'s run)."""
    from vrtools.convert.collision import _tarmac_quad_at
    x, z = box[0], box[2]
    ex, ez = min(((t.col.quads[i].centre[0], t.col.quads[i].centre[2]) for i in (q, q + 1)), key=lambda c: math.dist(c, (x, z)))
    run = math.dist((ex, ez), (x, z))
    paved = all(_tarmac_quad_at(t.col, ex + (x - ex) * s / run, ez + (z - ez) * s / run) is not None for s in range(0, int(run) + 1, 4))
    return run, paved


def _clearance(t, q):
    """The least distance from either pair quad to any of the eight road lines (0 where a line runs inside one)."""
    return min(_quad_to_loop(t.col.quads[i], line) for i in (q, q + 1) for line in t.lines)


def _exit_gap(t, q):
    """The distance along the lane from the pair's foot nearest the exit to the lane's exit end."""
    return _length(t.lane) - max(_depths(t, q))


def _clear(t, q):
    return _clearance(t, q) >= ROAD_CLEAR and _exit_gap(t, q) >= EXIT_CLEAR


def _frame(line, s):
    """The point of the open polyline at arc length s and the unit normal of its segment there."""
    for i, (a, b) in enumerate(zip(line, line[1:])):
        L = math.dist(a, b)
        if s <= L or i == len(line) - 2:
            f = min(s, L) / L if L else 0.0
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), ((-(b[1] - a[1]) / L, (b[0] - a[0]) / L) if L else (0.0, 0.0))
        s -= L


def _cover(t, q):
    """C3: the share of the lane's width at the pair that a car driving along the lane cannot pass without crossing q or q + 1.
    Over the pair's extent along the lane's polyline (the feet of its quads' corners), lateral offsets every 0.5 unit over +-30:
    an offset's line (the polyline moved by it, sampled every 0.5 unit) is the lane's where a point of it lies in a lane slice,
    and covered where one lies in q or q + 1."""
    from vrtools.convert.collision import _point_in_xz
    pair = [t.col.quads[i] for i in (q, q + 1)]
    feet = [_foot(t.lane, c[0], c[2])[0] for qq in pair for c in qq.corners]
    s0, s1 = max(0.0, min(feet)), min(_length(t.lane), max(feet))
    k = max(1, math.ceil((s1 - s0) / 0.5))
    frames = [_frame(t.lane, s0 + (s1 - s0) * j / k) for j in range(k + 1)]
    width = covered = 0
    for u in range(-60, 61):
        pts = [(px + nx * u * 0.5, pz + nz * u * 0.5) for (px, pz), (nx, nz) in frames]
        if not any(_point_in_xz(poly, *p) for p in pts for poly in t.polys):
            continue
        width += 1
        covered += any(_point_in_xz(qq.corners, *p) for p in pts for qq in pair)
    return covered / width if width >= 3 else 0.0


def _box_free_pairs(t):
    """The pairs passing H1, H2's normal-pair clause and H3 (the rules that do not depend on the box), once per course."""
    from vrtools.convert.collision import _point_in_xz
    if not hasattr(t, "free"):
        lane = [i for i in range(t.col.n_tarmac) if _lane_quad(t, i)]
        t.free = [q for q in lane if q + 1 in set(lane) and not {q, q + 1} & {t.k, t.k + 1}
                  and not any(_point_in_xz(t.col.quads[i].corners, *p) for i in (q, q + 1) for line in t.lines for p in line)
                  and _clearance(t, q) > 0.0]
    return t.free


def _hard(t, q, box):
    """H2's box clause, H4 and H5 for a pair of `_box_free_pairs` with the box at (box[0], box[2])."""
    from vrtools.convert.collision import _point_in_xz
    from vrtools.convert.reverse import REVERSE_PIT_MIN_RUN
    if any(_point_in_xz(t.col.quads[i].corners, box[0], box[2]) for i in (q, q + 1)):
        return False
    sb = _foot(t.lane, box[0], box[2])[0]
    if not all(sb < s for s in _depths(t, q)):
        return False
    run, paved = _run(t, q, box)
    return run >= REVERSE_PIT_MIN_RUN and paved


def _candidates(t, box):
    return [q for q in _box_free_pairs(t) if _hard(t, q, box)]


def _left_after_c2(t):
    """The candidates at the chosen box that C2 leaves: the clear ones, else those of the greatest clearance."""
    cands = _candidates(t, t.rp.box)
    clear = [q for q in cands if _clear(t, q)]
    if clear:
        return clear
    most = max(_clearance(t, q) for q in cands)
    return [q for q in cands if _clearance(t, q) == most]


PAIR_DIRECTION_WORST = 32.0   # degrees: the largest measured (Diablo Canyon 59, -32.0; 58 -23.8, Amazon Falls 32 / 33 -14.3 / -11.7,
                              # Metropolis -9.9, the others within 2.2: scratch on Task 2's cached conversions, final review Minor 8)


@pytest.mark.parametrize("name", PIT_COURSES)
def test_both_reverse_pair_quads_face_the_reverse_lane(romset_zip, saturn_cue, name):
    """Final review (Minor 8): the game forces a stop on q or q + 1 only with the car's heading within 90 degrees of the quad's
    direction, which a reverse race turns by 0x8000 (`direction.dirattr`). In MAME every reverse trigger came on one quad of the
    pair, so the other is pinned here: both quads' direction attributes, turned half a turn, lie within 90 degrees of the
    reverse lane direction at their centres (the lane's polyline from its normal exit towards its mouth: the heading word of that
    segment, -atan2(dx, dz)). Measured worst: see PAIR_DIRECTION_WORST (printed)."""
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    worst = 0.0
    for i in (t.rp.quad, t.rp.quad + 1):
        q = t.col.quads[i]
        seg = _foot(t.lane, q.centre[0], q.centre[2])[2]
        (ax, az), (bx, bz) = t.lane[seg + 1], t.lane[seg]                # exit -> mouth: the reverse car's way
        lane = -math.atan2(bx - ax, bz - az) / math.tau * 65536
        diff = ((((q.attr + 0x8000) & 0xFFFF) - lane + 32768) % 65536 - 32768) / 65536 * 360
        worst = max(worst, abs(diff))
        assert abs(diff) < 90.0, (name, i, hex(q.attr & 0xFFFF), round(diff, 1))
    print("PAIR DIRECTION", name, t.rp.quad, "largest angle to the reverse lane direction (degrees)", round(worst, 1))
    assert worst <= PAIR_DIRECTION_WORST + 1.0, worst

@pytest.mark.parametrize("name", PIT_COURSES)
def test_h1_both_pair_quads_are_lane_quads(romset_zip, saturn_cue, name):
    from vrtools.convert.reverse import ReversePit
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    assert isinstance(t.rp, ReversePit), t.rp
    assert all(_lane_quad(t, i) for i in (t.rp.quad, t.rp.quad + 1)), (t.rp, t.col.n_tarmac)
    for i in (t.rp.quad, t.rp.quad + 1):          # pit_entry_quad's own lane test, by the polylines' points (vrtools/convert/
        x, z = t.col.quads[i].centre[0], t.col.quads[i].centre[2]      # collision.py:1742-1745, inside its pair_in_lane)
        d_lane = min(math.hypot(px - x, pz - z) for px, pz in t.lane)
        d_road = min(math.hypot(px - x, pz - z) for px, pz in t.pts)
        assert d_lane < PIT_LANE_HALF_WIDTH and d_lane < d_road, (i, d_lane, d_road)


@pytest.mark.parametrize("name", PIT_COURSES)
def test_h2_the_pair_holds_neither_the_box_nor_the_normal_pair(romset_zip, saturn_cue, name):
    from vrtools.convert.collision import _point_in_xz
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    pair = (t.rp.quad, t.rp.quad + 1)
    assert not any(_point_in_xz(t.col.quads[i].corners, t.rp.box[0], t.rp.box[2]) for i in pair), (pair, t.rp.box)
    assert not set(pair) & {t.k, t.k + 1}, (pair, t.k)


@pytest.mark.parametrize("name", PIT_COURSES)
def test_h3_no_road_line_runs_inside_the_pair(romset_zip, saturn_cue, name):
    """No point of the eight road lines (`road_tables`' own, with the collision's lanes) lies inside either quad: neither a
    line point nor a point between two."""
    from vrtools.convert.collision import _point_in_xz
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    pair = (t.rp.quad, t.rp.quad + 1)
    assert len(t.lines) == 8
    assert not [(i, L) for i in pair for L, line in enumerate(t.lines) if any(_point_in_xz(t.col.quads[i].corners, *p) for p in line)]
    assert _clearance(t, t.rp.quad) > 0.0, pair


@pytest.mark.parametrize("name", PIT_COURSES)
def test_reverse_pit_measures_road_tables_own_lines(romset_zip, saturn_cue, name):
    """`reverse.road_line_points` (a copy of `road_tables`' formula: road_tables builds the lines inline from a Lap) places the
    eight lines where `road_tables` does on each conversion."""
    from vrtools.convert.reverse import road_line_points
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    assert road_line_points(t.pts, t.col.lanes) == t.lines


@pytest.mark.parametrize("name", PIT_COURSES)
def test_h4_the_pair_lies_between_the_exit_and_the_box(romset_zip, saturn_cue, name):
    """Both centres' feet on the lane's polyline lie deeper than the box's (a foot is never past the exit end)."""
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    sb = _foot(t.lane, t.rp.box[0], t.rp.box[2])[0]
    depths = _depths(t, t.rp.quad)
    assert all(sb < s for s in depths), (sb, depths)


@pytest.mark.parametrize("name", PIT_COURSES)
def test_h5_the_run_to_the_box(romset_zip, saturn_cue, name):
    from vrtools.convert.reverse import REVERSE_PIT_MIN_RUN
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    assert REVERSE_PIT_MIN_RUN == 64.0
    run, paved = _run(t, t.rp.quad, t.rp.box)
    assert run >= REVERSE_PIT_MIN_RUN and paved, (run, paved)


@pytest.mark.parametrize("name", PIT_COURSES)
def test_c1_the_box_moves_only_when_no_candidate_reaches_the_normal_box_and_then_least(romset_zip, saturn_cue, name):
    """C1: the box is the normal box when any candidate passes the hard rules with it; otherwise no candidate passes with the
    box at any position of the implementation's walk before the chosen one: from the normal box's foot towards the mouth in
    steps of 0.1 unit along the lane's polyline, each position on tarmac (`reverse.REVERSE_PIT_BOX_STEP` and its condition)."""
    from vrtools.convert.collision import _tarmac_quad_at
    from vrtools.convert.reverse import REVERSE_PIT_BOX_STEP
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    at_normal = _candidates(t, t.box)
    assert (tuple(t.rp.box[:3]) == tuple(t.box[:3])) == bool(at_normal), (t.rp.box, t.box, at_normal)
    if not at_normal:
        assert REVERSE_PIT_BOX_STEP == 0.1
        sn, sc = _foot(t.lane, t.box[0], t.box[2])[0], _foot(t.lane, t.rp.box[0], t.rp.box[2])[0]
        early, s = [], sn - 0.1
        while s > sc + 0.05:
            (x, z), _ = _frame(t.lane, s)
            if _tarmac_quad_at(t.col, x, z) is not None and _candidates(t, (x, 0.0, z)):
                early.append(s)
            s -= 0.1
        assert not early, (sn, sc, early[:3])


@pytest.mark.parametrize("name", PIT_COURSES)
def test_the_reverse_pit_box(romset_zip, saturn_cue, name):
    """The box's heading is the normal box's turned half a turn; the car stops at the normal box (P1) on six courses; on
    Metropolis the normal box lies 35 units from the exit, too near for any pair's run (L3), and the box moves up the lane's
    polyline towards the mouth by the least distance that gives the run, into the tunnel (the prototype parked at z 270.0)."""
    from vrtools.convert.collision import _tarmac_quad_at
    from vrtools.convert.reverse import REVERSE_PIT_MIN_RUN
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    x, y, z, h = t.rp.box
    assert h == (t.box[3] + 0x8000) % 0x10000, (h, t.box)
    if name in SIX_BOXES:
        assert (x, y, z) == t.box[:3], (t.rp.box, t.box)
        return
    s, d, _ = _foot(t.lane, x, z)
    under = _tarmac_quad_at(t.col, x, z)
    assert d < 0.01 and s < _foot(t.lane, t.box[0], t.box[2])[0], (s, d)        # on the polyline, nearer the mouth
    assert under is not None and min(abs(c[1] - y) for c in t.col.quads[under].corners) < 2.0, (under, y)
    (bx, bz), _ = _frame(t.lane, s + 0.5)                                       # half a unit back towards the normal box: short
    run, paved = _run(t, t.rp.quad, (bx, 0.0, bz))
    assert run < REVERSE_PIT_MIN_RUN or not paved, (run, paved)
    assert 268.0 <= z <= 274.0, z
    roofed = lambda px, pz: any(4 < v - t.hfn(px, pz) < 60 for v in t.drawn(px, pz))   # test_metropolis_pit_box_stands_in_the_tunnel's
    assert roofed(x, z), (x, z)


@pytest.mark.parametrize("name", PIT_COURSES)
def test_c2_clear_pairs_come_first(romset_zip, saturn_cue, name):
    """C2: the chosen pair is clear (all of both quads 8 units from the eight lines, both feet 10 from the lane's exit end), or
    no candidate at the box is clear and none has a greater clearance from the eight lines."""
    from vrtools.convert import reverse as R
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    cands = _candidates(t, t.rp.box)
    assert t.rp.quad in cands, cands
    if not _clear(t, t.rp.quad):
        assert not [q for q in cands if _clear(t, q)], [(q, round(_clearance(t, q), 1), round(_exit_gap(t, q), 1)) for q in cands]
        assert _clearance(t, t.rp.quad) == max(_clearance(t, q) for q in cands), [(q, _clearance(t, q)) for q in cands]
    assert (R.REVERSE_PIT_ROAD_CLEAR, R.REVERSE_PIT_EXIT_CLEAR) == (ROAD_CLEAR, EXIT_CLEAR)


@pytest.mark.parametrize("name", PIT_COURSES)
def test_c3_the_best_cover_of_those_left(romset_zip, saturn_cue, name):
    """C3: of the candidates C2 leaves, none covers more than COVER_TIE more of the lane's width than the chosen pair. Printed
    per course."""
    from vrtools.convert import reverse as R
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    left = _left_after_c2(t)
    covers = {q: _cover(t, q) for q in left}
    L = _length(t.lane)
    run, _ = _run(t, t.rp.quad, t.rp.box)
    print(f"\n{name}: q {t.rp.quad}, from the exit {[round(L - s, 1) for s in _depths(t, t.rp.quad)]}, run {run:.1f}, "
          f"cover {_cover(t, t.rp.quad):.3f}, clearance {_clearance(t, t.rp.quad):.1f}, clear {_clear(t, t.rp.quad)}, "
          f"box {t.rp.box}, left after C2 {[(q, round(c, 3)) for q, c in covers.items()]}")
    assert t.rp.quad in covers and max(covers.values()) - covers[t.rp.quad] <= COVER_TIE, (t.rp.quad, covers)
    assert R.REVERSE_PIT_COVER_TIE == COVER_TIE


@pytest.mark.parametrize("name", PIT_COURSES)
def test_c4_ties_to_the_pair_nearest_the_exit(romset_zip, saturn_cue, name):
    """C4: of the candidates C2 leaves whose cover lies within COVER_TIE of the best, none is nearer the normal exit."""
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    left = _left_after_c2(t)
    covers = {q: _cover(t, q) for q in left}
    best = [q for q in left if covers[q] >= max(covers.values()) - COVER_TIE]
    assert min(best, key=lambda q: (_exit_gap(t, q), q)) == t.rp.quad, [(q, round(_exit_gap(t, q), 1)) for q in best]


# Converter outputs on the build's collision (measured 14 Nov, Task 2, after the lead's rulings), pinned as the other conversion
# tests pin theirs: q, the box (the normal one, or Metropolis's z), the cover, the clearance from the eight lines, clear.
PINNED = {"ALPINE": (250, None, 0.967, 3.836, False),
          "AMAZON FALLS": (32, None, 1.000, 11.149, True),
          "DIABLO CANYON": (58, None, 1.000, 8.780, True),
          "METROPOLIS": (86, 269.74, 1.000, 5.657, False),
          "PACIFIC COAST": (241, None, 0.976, 8.992, True),
          "SURFERS OVAL": (15, None, 1.000, 11.443, True),
          "SURFERS ROAD": (13, None, 1.000, 11.456, True)}


@pytest.mark.parametrize("name", PIT_COURSES)
def test_the_reverse_pit_of_each_course(romset_zip, saturn_cue, name):
    q, z, cover, clearance, clear = PINNED[name]
    t = _reverse_pits(romset_zip, saturn_cue)[name]
    assert t.rp.quad == q, t.rp
    if z is None:
        assert tuple(t.rp.box[:3]) == tuple(t.box[:3]), (t.rp.box, t.box)
    else:
        assert tuple(t.rp.box[:3]) != tuple(t.box[:3]) and abs(t.rp.box[2] - z) <= 0.05, (t.rp.box, t.box)
    assert abs(_cover(t, q) - cover) <= 0.005, _cover(t, q)
    assert abs(_clearance(t, q) - clearance) <= 0.05, _clearance(t, q)
    assert _clear(t, q) == clear, (_clearance(t, q), _exit_gap(t, q))


def test_h3_excludes_a_pair_the_other_hard_rules_allow(romset_zip, saturn_cue):
    """H3's negative control: on Surfers Oval adjacent lane quads 2-19 units from the normal exit pass H1, H2, H4 and H5 with
    the chosen box, but a road line runs inside them (measured: pairs 42 and 43, among others): H3 excludes them, and the
    chosen pair is not one of them."""
    t = _reverse_pits(romset_zip, saturn_cue)["SURFERS OVAL"]
    lane = [i for i in range(t.col.n_tarmac) if _lane_quad(t, i)]
    crossed = [q for q in lane if q + 1 in set(lane) and not {q, q + 1} & {t.k, t.k + 1} and _clearance(t, q) == 0.0
               and _hard(t, q, t.rp.box)]
    assert crossed, "no lane pair under a road line passes the other hard rules"
    assert t.rp.quad not in crossed and not set(crossed) & set(_box_free_pairs(t)), (t.rp.quad, crossed)


def test_a_course_without_a_pit_stop_has_no_reverse_pit(monkeypatch):
    """None for a course without a lane, a lane whose `PitLane.pit_stop` is false, and a lane without a pit entry quad."""
    import hashlib
    from types import SimpleNamespace
    import vrtools.convert.place as place
    from vrtools.convert.reverse import reverse_pit
    col = SimpleNamespace(quads=[], n_tarmac=0)
    cl = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert reverse_pit(SimpleNamespace(trck=None, segments=[]), col, cl) is None                 # no lane
    trck = SimpleNamespace(data=b"a course whose lane has no stop")
    monkeypatch.setitem(place.PIT_LANES, hashlib.sha1(trck.data).hexdigest()[:16], place.PitLane(None, (1, 2, 3), pit_stop=False))
    assert reverse_pit(SimpleNamespace(trck=trck, segments=[]), col, cl) is None                 # pit_stop false
    trck = SimpleNamespace(data=b"a course whose lane has no slices")
    monkeypatch.setitem(place.PIT_LANES, hashlib.sha1(trck.data).hexdigest()[:16], place.PitLane(None, (1, 2, 3)))
    assert reverse_pit(SimpleNamespace(trck=trck, segments=[]), col, cl) is None                 # pit_entry_quad None


def _straight_lane(monkeypatch, length):
    """A synthetic course for `reverse_pit`: a straight pit lane along +z at x 100 from z 0 to `length` (its mouth at z 0),
    tarmac quads 10 units long and wide along it in list order, the normal pair 0/1 at the mouth, the normal box at z 20,
    and a race centreline far away (a ring round (-300, 0)): every lane pair is a lane quad pair clear of the road."""
    from types import SimpleNamespace
    import vrtools.convert.reverse as R
    quads = [Quad16(((95.0, 0.0, z + 10.0), (105.0, 0.0, z + 10.0), (105.0, 0.0, z), (95.0, 0.0, z)), (100.0, 0.0, z + 5.0), 0)
             for z in range(0, length, 10)]
    cl = [(-300.0 + 50 * math.cos(2 * math.pi * j / 40), 50 * math.sin(2 * math.pi * j / 40)) for j in range(40)]
    monkeypatch.setattr(R, "pit_lane_of", lambda sat: SimpleNamespace(pit_stop=True))
    monkeypatch.setattr(R, "pit_entry_quad", lambda sat, col, centreline: 0)
    monkeypatch.setattr(R, "pit_box", lambda sat, col, centreline: (100.0, 0.0, 20.0, 0x1000))
    monkeypatch.setattr(R, "pit_lane_centres", lambda sat, centreline: [(100.0, float(z)) for z in range(0, length + 1, 10)])
    monkeypatch.setattr(R, "pit_lane_polygons", lambda sat: [])
    return SimpleNamespace(quads=quads, n_tarmac=len(quads), lanes=None), cl


def test_no_pair_with_the_run_is_refused(monkeypatch):
    """A lane 60 units long: its pairs pass H1-H4, but no box from the normal one to the mouth lies REVERSE_PIT_MIN_RUN from
    any of them (the walk runs out at the mouth): ConvertError. A lane 160 long gives a pair at the normal box (the control)."""
    from vrtools.convert.reverse import REVERSE_PIT_MIN_RUN, ReversePit, reverse_pit
    col, cl = _straight_lane(monkeypatch, 60)
    with pytest.raises(ConvertError, match="no reverse pit pair in the lane"):
        reverse_pit(object(), col, cl)
    col, cl = _straight_lane(monkeypatch, 160)
    rp = reverse_pit(object(), col, cl)
    assert isinstance(rp, ReversePit) and rp.box == (100.0, 0.0, 20.0, 0x9000), rp
    assert col.quads[rp.quad].centre[2] - 20.0 >= REVERSE_PIT_MIN_RUN, rp
