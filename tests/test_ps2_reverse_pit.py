"""Phase 90, task 2 (the review's I11): Island's reverse pit pair and box by the Saturn path's rule (`reverse.reverse_pit_in`, through
`ps2entry.reverse_pit_of`), on the conversion read from the PS2 disc (no MAME). The stop itself in MAME: tests/test_pack_gates.py's
test_islands_reverse_pit_stop."""
import math

import pytest

from vrtools.convert.collision import PIT_LANE_HALF_WIDTH


@pytest.fixture(scope="module")
def island():
    from tests.reference_sets import missing_input, required_romset_zip
    from vrtools.arcade import tencourse as T
    from vrtools.arcade.pack import ISLAND
    from vrtools.arcade.romset import RomSet
    from vrtools.convert import ps2course as PC
    from vrtools.ps2 import disc as D
    from vrtools.ps2.course import load_from_disc
    path = D.ps2_disc()
    if path is None or not path.exists():
        missing_input(f"set {D.ENV} to the PS2 disc .cue")
    rs = RomSet.from_zip(required_romset_zip())
    return PC.convert(load_from_disc(D.Ps2Disc(path), ISLAND.index), PC.Frame.for_host(rs, T.HOST_OF_BANK[ISLAND.bank]), pit=True)


def test_islands_reverse_pit_pair_and_box(island):
    """The pair (q, q + 1) is two of the lane's own tarmac quads (after the lap's, within PIT_LANE_HALF_WIDTH of the lane's
    polyline), neither the normal pair nor holding the box, both deeper in the lane than the box (nearer the normal exit: the
    reverse car comes in that way); the box is the normal box turned half a turn (rule C1) and lies at least
    REVERSE_PIT_MIN_RUN from the pair's nearer quad."""
    from vrtools.arcade.ps2entry import reverse_pit_of
    from vrtools.convert.collision import _point_in_xz
    from vrtools.convert.reverse import REVERSE_PIT_MIN_RUN, _foot
    conv = island
    rp = reverse_pit_of(conv)
    assert rp is not None
    col, lane, k = conv.collision, conv.pit.line, conv.pit_quad
    first = col.n_tarmac - (len(conv.pit.quads) + 1)
    q = rp.quad
    assert first <= q and q + 1 < col.n_tarmac and not {q, q + 1} & {k, k + 1}, (q, first, col.n_tarmac, k)
    centres = [(col.quads[i].centre[0], col.quads[i].centre[2]) for i in (q, q + 1)]
    assert all(_foot(lane, x, z)[1] < PIT_LANE_HALF_WIDTH for x, z in centres), centres
    bx, by, bz, heading = rp.box
    nb = conv.pit.box
    assert heading == (nb[3] + 0x8000) & 0xFFFF and (bx, by, bz) == nb[:3], (rp.box, nb)
    sb = _foot(lane, bx, bz)[0]
    assert all(_foot(lane, x, z)[0] > sb for x, z in centres), (centres, sb)
    assert not any(_point_in_xz(col.quads[i].corners, bx, bz) for i in (q, q + 1))
    assert min(math.dist(c, (bx, bz)) for c in centres) >= REVERSE_PIT_MIN_RUN
    print("ISLAND reverse pit", q, rp.box, "normal", k, nb)

