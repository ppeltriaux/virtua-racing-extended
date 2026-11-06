"""Phase 22b: the HUD map's outline for a converted course, built from its own centreline in the originals' style."""
import math
import struct

from vrtools.convert.hudmap import OUTLINE_WIDTH, OUTLINE_Y, encode_outline, outline_quads


def _loop(n=300, r=500.0):
    return [(r * math.cos(2 * math.pi * k / n) + 0.3 * r * math.cos(6 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _inside(q, x, z):
    pts = [(p[0], p[2]) for p in q.p]
    s = [(b[0] - a[0]) * (z - a[1]) - (b[1] - a[1]) * (x - a[0]) for a, b in zip(pts, pts[1:] + pts[:1])]
    return all(v >= -1e-6 for v in s) or all(v <= 1e-6 for v in s)


def test_the_outline_is_a_flat_strip_over_the_whole_centreline():
    """The originals' outlines are flat strips about 30 units wide at y 0.3 with normals (0, -1, 0), 69-131 quads; the
    car's cross and the markers are placed by the car's own position, so the strip must lie on the course's own road
    points (in arcade coordinates, as the road lines)."""
    cl = _loop()
    qs = outline_quads(cl)
    assert 20 <= len(qs) <= 200
    assert all(abs(p[1] - OUTLINE_Y) < 1e-6 for q in qs for p in q.p) and all(q.normal == (0.0, -1.0, 0.0) for q in qs)
    assert all(any(_inside(q, x, z) for q in qs) for x, z in cl)
    widths = [math.dist((q.p[0][0], q.p[0][2]), (q.p[1][0], q.p[1][2])) for q in qs]
    assert all(abs(w - OUTLINE_WIDTH) < 0.5 * OUTLINE_WIDTH for w in widths)


def test_the_outline_draws_like_the_originals():
    """The originals' outline records carry 0x20000 and z mode 1, chain starts 0x800000, drawing records 0x1000000
    (Big Forest: 0x825501 / 0x1025601); the object reads one colour entry (the host's outline colour)."""
    blob, layout = encode_outline(outline_quads(_loop()), tex=0x402AA)
    assert layout.tex_first == layout.tex_last == 0x402AA
    flags = [struct.unpack_from("<I", blob, i)[0] for i in range(24, len(blob), 40)]   # records after the 6-float seed
    live = [f for f in flags if f & 3]
    assert live and flags[-1] & 3 == 0
    assert all(f & 0x20000 and (f >> 10) & 3 == 1 and f & 0x4000 for f in live)
    assert all(bool(f & 0x800000) == ((f >> 8) & 3 == 0) and bool(f & 0x1000000) == ((f >> 8) & 3 != 0) for f in live)


def test_the_outline_carries_open_strips_along_the_pit_lanes():
    """Phase 22g (Pascal: the pit lane "is not displayed on the map"): as Big Forest's outline covers its start straight
    and pit lane with one wide quad, a course's pit lane (an open polyline) is drawn as a strip of its own beside the
    loop; the loop's strip is unchanged."""
    cl = _loop()
    lane = [(520.0 + 0.0 * t, -200.0 + 4.0 * t) for t in range(0, 101, 5)]          # 400 units along +z, outside the loop
    loop = outline_quads(cl)
    both = outline_quads(cl, extra=[lane])
    assert both[:len(loop)] == loop and len(both) > len(loop)
    assert all(any(_inside(q, x, z) for q in both[len(loop):]) for x, z in lane[1:-1])
    assert all(abs(p[1] - OUTLINE_Y) < 1e-6 for q in both for p in q.p)
