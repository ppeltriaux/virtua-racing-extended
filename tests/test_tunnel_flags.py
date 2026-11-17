"""Phase 37: the arcade's tunnel flag (bit 7 of a segment's flag: the player's engine mix, boot 0xffa671) on the tarmac quads of
the stretches a `CoursePlan` names. The writer (no ROM needed) and, with the ROM set and the disc, each named stretch against the
roof the built set draws over it."""
import math

import pytest

from vrtools.arcade.course import Segment
from vrtools.convert.geometry import ConvertError
from vrtools.convert.road import FLAG_PLAIN, FLAG_TUNNEL, RoadPoint, RoadTables, tunnel_quads, with_tunnel_flags


def _tables(credits):
    line = [RoadPoint(float(k), 0.0, 0, 0) for k in range(max(credits) + 1)]
    return RoadTables([line] * 8, [Segment(k, rp, FLAG_PLAIN) for k, rp in enumerate(credits)])


def test_the_quads_of_a_stretch_are_those_credited_to_its_points_ends_included():
    t = _tables([0, 2, 3, 3, 5, 4, 6, 9, 9])                      # the credits need not rise with the list (side strips, lane quads)
    assert tunnel_quads(t.segments, ((3, 5),), 10) == frozenset({2, 3, 4, 5})
    assert tunnel_quads(t.segments, ((0, 0), (9, 9)), 10) == frozenset({0, 7, 8})
    assert tunnel_quads(t.segments, (), 10) == frozenset()
    assert tunnel_quads(t.segments, ((7, 8),), 10) == frozenset()   # a stretch no quad is credited to names none


def test_the_flag_is_the_arcade_s_bit_7_over_the_plain_flag_and_nothing_else_moves():
    t = _tables([0, 2, 3, 3, 5, 4, 6, 9, 9])
    out = with_tunnel_flags(t, frozenset({2, 3, 5}))
    assert FLAG_TUNNEL == 0x80 and FLAG_PLAIN | FLAG_TUNNEL == 0x81   # Bay Bridge's own value on its quads 69-88
    assert [s.flag for s in out.segments] == [1, 1, 0x81, 0x81, 1, 0x81, 1, 1, 1]
    assert [(s.index, s.road_point) for s in out.segments] == [(s.index, s.road_point) for s in t.segments]
    assert out.lines is t.lines
    assert [s.flag for s in t.segments] == [1] * 9                  # the input is not changed
    assert with_tunnel_flags(t, frozenset()) is t                   # no stretch: the tables themselves


def test_a_reverse_array_takes_the_same_quads_whatever_its_own_credits():
    t = _tables([0, 2, 3, 3, 5, 4, 6, 9, 9])
    quads = tunnel_quads(t.segments, ((3, 5),), 10)
    rev = _tables([9, 8, 7, 7, 5, 6, 4, 1, 0])                     # the same quads credited the other way round
    assert [s.index for s in with_tunnel_flags(rev, quads).segments if s.flag == 0x81] == sorted(quads)


@pytest.mark.parametrize("stretches", [((5, 3),), ((-1, 2),), ((3, 10),), ((1, 4), (4, 6)), ((1,),), ((1.0, 2),)])
def test_a_bad_stretch_is_refused(stretches):
    t = _tables([0, 2, 3, 3, 5, 4, 6, 9, 9])
    with pytest.raises(ConvertError):
        tunnel_quads(t.segments, stretches, 10)


def test_a_quad_index_outside_the_array_is_refused():
    with pytest.raises(ConvertError):
        with_tunnel_flags(_tables([0, 1, 2]), frozenset({3}))


def test_the_plans_name_the_three_stretches_pascal_agreed_and_no_other():
    from vrtools.arcade.tencourse import COURSES
    assert {p.name: p.tunnels for p in COURSES if p.tunnels} == {"ALPINE": ((108, 146),), "METROPOLIS": ((50, 62), (251, 311))}


def test_the_sound_log_pairs_the_latch_bytes_and_models_the_board_s_bit(tmp_path):
    """sound_log.lua's log as `parse_sound_log` reads it: a command is the high byte (PC 0xffa2a6) and the next low byte
    (0xffa36a); the board's tunnel bit is set by C201 and cleared by C200 and by the reset 8100; the helper is loaded by
    autoplay.lua and attract_snaps.lua."""
    from vrtools.mame.runner import LUA_DIR, MameError, parse_sound_log
    log = tmp_path / "sound.txt"
    log.write_text("S 3 0 ffa1ae\nS 9 81 ffa2a6\nS 10 0 ffa36a\nF 12 14 100000 fe8e18 45 81 1 106\n"
                   "S 20 c2 ffa2a6\nS 21 1 ffa36a\nS 30 c0 ffa2a6\nS 31 5a ffa36a\nS 40 c2 ffa2a6\nS 41 0 ffa36a\n"
                   "S 50 c2 ffa2a6\nS 51 1 ffa36a\nS 60 81 ffa2a6\nS 61 0 ffa36a\nEND\n")
    got = parse_sound_log(log)
    assert got.complete and got.commands == [(10, 0x8100), (21, 0xC201), (31, 0xC05A), (41, 0xC200), (51, 0xC201), (61, 0x8100)]
    assert got.tunnel() == [(10, 0x8100), (21, 0xC201), (41, 0xC200), (51, 0xC201), (61, 0x8100)]
    assert [got.bit_at(f) for f in (0, 20, 21, 40, 41, 55, 61, 99)] == [0, 0, 1, 1, 0, 1, 0, 0]
    f = got.flags[0]
    assert (f.frame, f.mode, f.gate, f.handler, f.quad, f.flag, f.previous, f.road_point) == (12, 0x14, 0x100000, 0xFE8E18, 0x45, 0x81, 1, 106)
    log.write_text("S 20 c2 ffa2a6\nS 21 c2 ffa2a6\n")
    with pytest.raises(MameError):
        parse_sound_log(log)
    log.write_text("S 21 1 ffa36a\n")
    with pytest.raises(MameError):
        parse_sound_log(log)
    load = 'if os.getenv("VR_SOUND_LOG") and lua_dir then dofile(lua_dir .. "/sound_log.lua") end'
    assert load in (LUA_DIR / "autoplay.lua").read_text() and load in (LUA_DIR / "attract_snaps.lua").read_text()


# --- each stretch against the drawn roof (ROM set and disc) -----------------------------------------------------------------------

ON_ROAD = 6.0            # a tarmac quad whose centre is this near the centreline is the road's own (not a side strip or the pit lane)
ROOF = (2.0, 60.0)       # a drawn face this far above a quad's centre is a roof over it
CLEAR = 5                # road points before and after a stretch whose road quads must have no roof (the stretch is tight to it)
_ROOFS: dict = {}


def roofed(tris, bb, x, y, z) -> bool:
    """A drawn triangle of `tris` (n, 3, 3; `bb` their xz boxes) lies ROOF above (x, y, z)."""
    import numpy as np
    m = (bb[:, 0] <= x) & (bb[:, 1] >= x) & (bb[:, 2] <= z) & (bb[:, 3] >= z)
    a, b, c = tris[m][:, 0], tris[m][:, 1], tris[m][:, 2]
    d = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
    ok = np.abs(d) > 1e-9
    a, b, c, d = a[ok], b[ok], c[ok], d[ok]
    u = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / d
    v = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / d
    w = 1 - u - v
    ys = (u * a[:, 1] + v * b[:, 1] + w * c[:, 1])[(u >= -1e-6) & (v >= -1e-6) & (w >= -1e-6)]
    return bool(((ys > y + ROOF[0]) & (ys < y + ROOF[1])).any())


def road_roofs(romset_zip, saturn_cue, name):
    """Per tarmac quad of the course `name` as the build makes it: (quad, credited road point, on the road?, roofed?), the roof
    read from the faces the built set draws (its tile table's objects in the polygon ROM, world space)."""
    import numpy as np
    import vrtools.arcade.tencourse as tc
    from tests.test_tgp_build import _seven
    from vrtools.arcade.course import tile_table_at
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.polyrom import decode_object, quads
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import placed
    from vrtools.convert.road import road_tables
    if name not in _ROOFS:
        out, _ = _seven(romset_zip, saturn_cue)
        entry = next(e for e in decode_directory(out) if e.name == name)
        faces = np.array([q.p for t in tile_table_at(out, entry.tile_table) if t.size
                          for q in quads(decode_object(out.polygons, t.poly_adr, t.size), t.tex_adr)], dtype=np.float64)
        tris = np.concatenate([faces[:, [0, 1, 2]], faces[:, [0, 2, 3]]])
        bb = np.stack([tris[:, :, 0].min(1), tris[:, :, 0].max(1), tris[:, :, 2].min(1), tris[:, :, 2].max(1)], 1)
        rs = RomSet.from_zip(romset_zip)
        plan = next(p for p in tc.COURSES if p.name == name)
        sat = tc.load_saturn_course(saturn_cue, plan.path)
        pl = tc.course_placement(rs, sat, plan.template, min_coverage=plan.min_coverage, flag_start=plan.flag_start)
        with placed(pl.angle, pl.tx, pl.tz):
            cc = tc.course_collision(sat, pl, plan.template, min_coverage=plan.min_coverage, banking=plan.banking, camber=plan.camber,
                                     lane_points=plan.lane_points)
            segs = road_tables(cc.lap, cc.col.quads[:cc.col.n_tarmac], lanes=cc.col.lanes).segments
        rows = []
        for s in segs:
            x, y, z = cc.col.quads[s.index].centre
            rows.append((s.index, s.road_point, min(math.dist(p, (x, z)) for p in cc.pts) <= ON_ROAD, roofed(tris, bb, x, y, z)))
        _ROOFS[name] = rows, len(cc.pts)
    return _ROOFS[name]


def stretch_fits(rows, first, last) -> list[str]:
    """What is wrong with the stretch (first, last) against `rows` (`road_roofs`): nothing when every road quad credited to it is
    under a roof but at most one in seven (an end quad reaching out from under it), its first road quad is, and no road quad
    credited to the CLEAR points before it or after it is."""
    inside = [r for r in rows if r[2] and first <= r[1] <= last]
    bad = []
    if not inside:
        return [f"no road quad is credited to {first}-{last}"]
    if not inside[0][3]:
        bad.append(f"the first road quad of {first}-{last} (quad {inside[0][0]}, point {inside[0][1]}) has no roof")
    if 7 * sum(1 for r in inside if not r[3]) > len(inside):
        bad.append(f"road quads of {first}-{last} without a roof: {[(r[0], r[1]) for r in inside if not r[3]]}")
    out = [(r[0], r[1]) for r in rows if r[2] and r[3] and (first - CLEAR <= r[1] < first or last < r[1] <= last + CLEAR)]
    if out:
        bad.append(f"roofed road quads just outside {first}-{last}: {out}")
    return bad


@pytest.mark.parametrize("name", ["ALPINE", "METROPOLIS"])
def test_each_named_stretch_lies_under_the_roof_the_set_draws(romset_zip, saturn_cue, name):
    """A renumbering of the road points (a new start, a changed lap) would move a stretch off its tunnel: it fails here."""
    import vrtools.arcade.tencourse as tc
    rows, n = road_roofs(romset_zip, saturn_cue, name)
    plan = next(p for p in tc.COURSES if p.name == name)
    for first, last in plan.tunnels:
        assert stretch_fits(rows, first, last) == [], (name, first, last)
        for shift in (-4, 4):                                       # the test has teeth: the same stretch four points off fails
            assert stretch_fits(rows, first + shift, last + shift), (name, first, last, shift)


def test_no_other_long_roofed_run_of_road_is_left_unnamed_on_the_two_courses(romset_zip, saturn_cue):
    """The stretches named are the two courses' long roofed runs: outside them no ten consecutive road points' road quads are all
    under a roof (Metropolis's building before the line, 354-358, is five points: Pascal's "no")."""
    import vrtools.arcade.tencourse as tc
    for name in ("ALPINE", "METROPOLIS"):
        rows, n = road_roofs(romset_zip, saturn_cue, name)
        plan = next(p for p in tc.COURSES if p.name == name)
        by_point: dict = {}
        for _, rp, on, roof in rows:
            if on and not any(a <= rp <= b for a, b in plan.tunnels):
                by_point[rp] = by_point.get(rp, True) and roof
        run = longest = 0
        last = None
        for rp in sorted(by_point):
            run = run + (rp - last if last is not None and run else 1) if by_point[rp] else 0
            longest, last = max(longest, run), rp
        assert longest < 10, (name, longest)
