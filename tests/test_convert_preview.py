import math

import numpy as np
import pytest

from vrtools.arcade.romset import RomSet

_PICTURES: dict = {}


def _pictures(romset_zip, saturn_cue):
    """name -> (picture, centreline, fit) for the seven courses, rendered once."""
    if not _PICTURES:
        import vrtools.arcade.tencourse as tc
        from vrtools.arcade.lettering import letters
        from vrtools.convert.geometry import placed
        from vrtools.convert.lap import centreline, order_slices
        from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
        from vrtools.convert.preview import course_picture, fit
        rs = RomSet.from_zip(romset_zip)
        masks = letters(rs)
        for plan in tc.COURSES:
            sat = tc.load_saturn_course(saturn_cue, plan.path)
            gc = COURSE_OF_TEMPLATE[plan.template]
            pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage, flag_start=plan.flag_start)
            with placed(pl.angle, pl.tx, pl.tz):
                lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage)
                pic = course_picture(sat, lap, plan.name, masks)
                cl = centreline(lap, spacing=5.0)
                again = course_picture(sat, lap, plan.name, masks) if plan.name == "DIABLO CANYON" else None
            _PICTURES[plan.name] = (pic, cl, fit(cl), again)
    return _PICTURES


def test_a_picture_is_deterministic(romset_zip, saturn_cue):
    """Phase 21: the same course gives the same picture byte for byte (fixed seeds), 168 x 128 RGB."""
    pic, _, _, again = _pictures(romset_zip, saturn_cue)["DIABLO CANYON"]
    assert pic.shape == (168, 128, 3) and pic.dtype == np.uint8
    assert np.array_equal(pic, again)


def test_the_road_runs_under_the_centreline(romset_zip, saturn_cue):
    """The exact road is drawn: every 10th centreline point more than 4 px from the start mark lands on dark tarmac."""
    from vrtools.convert.preview import to_panel
    bad = {}
    for name, (pic, cl, f, _) in _pictures(romset_zip, saturn_cue).items():
        miss = []
        sx, sy = to_panel(*cl[0], f)
        for k in range(0, len(cl), 10):
            x, y = to_panel(*cl[k], f)
            px = pic[int(y), int(x)]
            if math.hypot(x - sx, y - sy) > 4 and px.max() >= 60:     # the start mark blends yellow into the tarmac
                miss.append((k, tuple(int(v) for v in px)))
        if miss:
            bad[name] = miss[:5]
    assert not bad, bad


def test_the_frame_and_the_name(romset_zip, saturn_cue):
    """The 2-px orange frame round the panel; the name bottom right in white letters with a dark outline."""
    from vrtools.convert.preview import FRAME
    for name, (pic, _, _, _) in _pictures(romset_zip, saturn_cue).items():
        for edge in (pic[0], pic[1], pic[-1], pic[-2], pic[:, 0], pic[:, 1], pic[:, -1], pic[:, -2]):
            assert (edge == FRAME).all(), name
        box = pic[150:164, 40:124].reshape(-1, 3)
        assert ((box == (240, 240, 240)).all(1)).any() and ((box == (16, 16, 16)).all(1)).any(), name


def test_no_saturn_road_side_strip(romset_zip, saturn_cue):
    """The Saturn's own polygons beside the road are not drawn (Pascal: the kerb/sand yellow looked wrong): in the ring
    3.5-5 px from the road's centre (outside its white edge) at most 10 % of Diablo Canyon's pixels are kerb yellow
    (red > 200, blue < 60); the spike with the strip had most of them."""
    from vrtools.convert.preview import to_panel
    pic, cl, f, _ = _pictures(romset_zip, saturn_cue)["DIABLO CANYON"]
    road = np.array([to_panel(x, z, f) for x, z in cl + cl[:1]])
    yy, xx = np.mgrid[0:168, 0:128] + 0.5
    dist = np.full((168, 128), 1e9)
    for a, b in zip(road[:-1], road[1:]):
        d = b - a
        t = np.clip(((xx - a[0]) * d[0] + (yy - a[1]) * d[1]) / ((d ** 2).sum() or 1.0), 0, 1)
        dist = np.minimum(dist, np.hypot(xx - a[0] - t * d[0], yy - a[1] - t * d[1]))
    ring = (dist > 3.5) & (dist < 5.0)
    ring[150:, 40:] = False                                       # the name
    yellow = (pic[..., 0] > 200) & (pic[..., 2] < 60)
    assert (yellow & ring).sum() <= 0.1 * ring.sum(), ((yellow & ring).sum(), ring.sum())
