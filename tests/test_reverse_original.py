"""Phase 33: an original course's road tables read backwards from its own arcade tables (convert.reverse.reverse_original).

Synthetic data only: a ring of N points with eight lines that each carry their own position, heading, pitch, roll and link (as
the three originals' hand-made lines do), a segment array crediting each quad the point it is centred on, a stretch of eight
quads abreast (a lane group), a pit lane (flag 66) and one more flag."""
import math

import pytest

from vrtools.arcade.bank import line_turn
from vrtools.arcade.course import RoadPoint, Segment
from vrtools.convert.geometry import ConvertError
from vrtools.convert.reverse import reverse_original
from vrtools.convert.road import RoadTables, heading_word, unwrap_headings

N = 48
GROUP = range(10, 16)          # road points with eight quads abreast
PIT = (0, 1, 2, N - 1)         # road points with a second, pit-lane quad (flag 66)
TUNNEL = (30, 31)              # road points whose quad carries another flag (129)


def _hi(w: int) -> int:
    return ((w >> 16) ^ 0x8000) - 0x8000


def _s16(w: int) -> int:
    return ((w & 0xFFFF) ^ 0x8000) - 0x8000


def _segments() -> list[Segment]:
    """Quads in lap order: one a point, eight on GROUP's points, then the pit lane's quads (their credits out of order, as Big
    Forest's 1085-1088 are)."""
    segs = []
    for p in range(N):
        for _ in range(8 if p in GROUP else 1):
            segs.append(Segment(len(segs), p, 129 if p in TUNNEL else 1))
    for p in PIT:
        segs.append(Segment(len(segs), p, 66))
    return segs


def _lines(segs, short: int | None = None) -> list[list[RoadPoint]]:
    """Eight clockwise rings (the originals' sense: the heading falls by a turn a lap), each its own radius and phase so no two
    lines share a point, a heading, a pitch or a roll; a point's link names the first flag-1/129 segment credited that point,
    plus the line's number where the point has eight (each line in its own lane). `short`: that line is two points short."""
    first = {}
    for s in segs:
        if s.flag != 66:
            first.setdefault(s.road_point, s.index)
    lines = []
    for k in range(8):
        r, phase = 100.0 + 3.0 * k, 0.01 * k
        pts = [(r * math.sin(2 * math.pi * j / N + phase), r * math.cos(2 * math.pi * j / N + phase)) for j in range(N)]
        raw = [heading_word(pts[(j + 1) % N][0] - pts[j][0], pts[(j + 1) % N][1] - pts[j][1]) >> 16 for j in range(N)]
        heads = unwrap_headings([h % 16384 for h in raw])
        line = [RoadPoint(x, z, ((heads[j] & 0xFFFF) << 16) | ((7 * j + 100 * k - 150) & 0xFFFF),
                          ((first[j] + (k if j in GROUP else 0)) << 16) | ((300 - 11 * j - 50 * k) & 0xFFFF))
                for j, (x, z) in enumerate(pts)]
        lines.append(line[:N - 2] if k == short else line)
    return lines


def _both(short=None):
    segs = _segments()
    lines = _lines(segs, short)
    return lines, segs, reverse_original(lines, segs)


def test_the_result_is_road_tables_of_eight_equal_lines():
    lines, segs, t = _both()
    assert isinstance(t, RoadTables) and len(t.lines) == 8 and all(len(l) == N for l in t.lines) and len(t.segments) == len(segs)


def test_every_line_keeps_its_own_points_read_backwards_from_the_line():
    """Reversed point j of line k is that line's forward point (N - j) mod N: point 0 stays on the start line and every line
    keeps its own place on the road (not the centreline's)."""
    lines, _, t = _both()
    for k in range(8):
        assert [(p.x, p.z) for p in t.lines[k]] == [(lines[k][(N - j) % N].x, lines[k][(N - j) % N].z) for j in range(N)]
    assert len({(l[5].x, l[5].z) for l in t.lines}) == 8


def test_a_segment_is_credited_the_point_it_is_centred_on_renumbered():
    """Quad k stays segment k with its flag; its credit p becomes (N - p) mod N: the originals credit a quad the point at its
    centre, so the same quad is centred on that point's reversed number."""
    _, segs, t = _both()
    assert [(s.index, s.flag) for s in t.segments] == [(s.index, s.flag) for s in segs]
    assert [s.road_point for s in t.segments] == [(N - s.road_point) % N for s in segs]
    assert {s.flag for s in t.segments} == {1, 66, 129}
    assert next(s.road_point for s in t.segments if segs[s.index].road_point == 0 and s.flag == 1) == 0
    assert next(s.road_point for s in t.segments if segs[s.index].road_point == 1 and s.flag == 1) == N - 1


def test_every_reversed_line_point_names_a_segment_credited_that_point():
    """The opponents' cursor rule (formats §15): a line point's link names a segment whose road point the car must reach. On the
    originals every point of every line names a segment credited the point's own number; reversed, it still does, with the same
    segment (the one the forward point named)."""
    lines, segs, t = _both()
    for k in range(8):
        for j, p in enumerate(t.lines[k]):
            assert t.segments[p.link >> 16].road_point == j, (k, j)
            assert p.link >> 16 == lines[k][(N - j) % N].link >> 16
            assert t.segments[p.link >> 16].flag != 66


def test_a_lane_group_keeps_one_shared_credit():
    """Eight quads abreast share a road point (formats §16: the passing code finds a group by its eight equal credits). They
    still share one after the reversal, and each line's point there still names its own lane's quad."""
    lines, segs, t = _both()
    for p in GROUP:
        group = [s for s in t.segments if segs[s.index].road_point == p and s.flag == 1]
        assert len(group) == 8 and {s.road_point for s in group} == {N - p}
        assert [s.index for s in group] == list(range(group[0].index, group[0].index + 8))
        assert [t.lines[k][N - p].link >> 16 for k in range(8)] == [group[0].index + k for k in range(8)]


def test_each_line_heads_the_other_way_by_its_own_heading():
    """The heading's high half is the forward point's turned half a turn (8192 of 16384), unwrapped again from the start line:
    continuous along the reversed line, the lap's net turn of the opposite sign, and each line's own (a wide line's heading is
    not the centreline's)."""
    lines, _, t = _both()
    for k in range(8):
        hs = [_hi(p.heading) for p in t.lines[k]]
        for j in range(N):
            assert (hs[j] - _hi(lines[k][(N - j) % N].heading) - 8192) % 16384 == 0, (k, j)
        assert all(abs(b - a) < 8192 for a, b in zip(hs, hs[1:]))
        assert -8192 <= hs[0] <= 8192
        assert line_turn(lines[k]) == -16384 and line_turn(t.lines[k]) == 16384
    assert len({_hi(l[7].heading) for l in t.lines}) > 1


def test_pitch_and_roll_change_sign_line_by_line():
    """The low halves (the pitch and the roll an opponent takes on the point, formats §4) are the forward point's negated: a
    climb is a descent the other way, a bank to the right a bank to the left. Each line's own values."""
    lines, _, t = _both()
    for k in range(8):
        for j, p in enumerate(t.lines[k]):
            f = lines[k][(N - j) % N]
            assert _s16(p.heading) == -_s16(f.heading) and _s16(p.link) == -_s16(f.link), (k, j)
    assert len({_s16(l[9].heading) for l in t.lines}) == 8 and len({_s16(l[9].link) for l in t.lines}) == 8


def test_reversing_twice_gives_the_course_back():
    lines, segs, t = _both()
    back = reverse_original(t.lines, t.segments)
    assert back.segments == segs
    for k in range(8):
        for a, b in zip(back.lines[k], lines[k]):
            assert (a.x, a.z, a.link, a.heading & 0xFFFF) == (b.x, b.z, b.link, b.heading & 0xFFFF)
            assert (_hi(a.heading) - _hi(b.heading)) % 16384 == 0


def test_a_short_line_is_completed_from_the_centreline():
    """Bay Bridge's line 6 has 416 of 418 points. The blob stores eight lines of equal length, so a short line's missing points
    are the centreline's at the same numbers (their heading, pitch, roll and link with them); its own points keep their numbers."""
    lines, segs, t = _both(short=6)
    assert len(lines[6]) == N - 2 and len(t.lines[6]) == N
    for j in range(N):
        f = (N - j) % N
        src = lines[6][f] if f < N - 2 else lines[0][f]
        assert (t.lines[6][j].x, t.lines[6][j].z, t.lines[6][j].link >> 16) == (src.x, src.z, src.link >> 16)
    assert all(abs(_hi(b.heading) - _hi(a.heading)) < 8192 for a, b in zip(t.lines[6], t.lines[6][1:]))


def test_bad_tables_are_refused():
    lines, segs, _ = _both()
    with pytest.raises(ConvertError, match="eight"):
        reverse_original(lines[:7], segs)
    with pytest.raises(ConvertError, match="road point"):
        reverse_original(lines, segs[:-1] + [Segment(segs[-1].index, N, 1)])
    bad = [list(l) for l in lines]
    bad[3][5] = RoadPoint(bad[3][5].x, bad[3][5].z, bad[3][5].heading, (len(segs) << 16) | 5)
    with pytest.raises(ConvertError, match="segment"):
        reverse_original(bad, segs)
    with pytest.raises(ConvertError, match="longer"):
        reverse_original([lines[0]] + [l + l[:1] for l in lines[1:]], segs)
    spun = [list(l) for l in lines]                               # a line that winds four turns: its reversed heading leaves 16 bits
    spun[2] = [RoadPoint(p.x, p.z, (((-1500 * j) & 0xFFFF) << 16) | (p.heading & 0xFFFF), p.link) for j, p in enumerate(spun[2])]
    with pytest.raises(ConvertError, match="16 bits"):
        reverse_original(spun, segs)
