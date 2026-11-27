"""Phase 90, task 2: a PS2 course's select picture (`preview.course_picture(faces=, sea=)`): the land in the colour of the topmost
ground face under each pixel, shaded by the Saturn pictures' mesh, the sea flat, the road, start mark, frame and name as on a
Saturn picture. A synthetic course (no disc) and the three PS2 courses (the PS2 disc)."""
import math

import numpy as np
import pytest

from vrtools.convert import preview
from vrtools.convert.geometry import WorldQuad
from vrtools.convert.lap import centreline

GREEN, RED, BLUE, HIGH = (40, 160, 40), (170, 60, 40), (30, 60, 200), (200, 200, 60)


def _sq(x0, z0, x1, z1, y, rgb):
    return WorldQuad(((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)), rgb)


def _faces():
    """Green land west of x 0 but for a sea corner north-west, red land east of it, a raised yellow patch over the red land."""
    return [_sq(-400, -400, 0, 230, 0.0, GREEN), _sq(-150, 230, 0, 400, 0.0, GREEN), _sq(0, -400, 400, 400, 0.0, RED),
            _sq(-400, 230, -150, 400, -1.0, BLUE), _sq(60, -60, 120, 0, 5.0, HIGH)]


def _sea(q):
    return q.rgb == BLUE


@pytest.fixture(scope="module")
def ring_lap():
    from tests.test_ps2course import _course
    from vrtools.convert import ps2course as P
    road, walls, line = _course()
    frame = P.Frame(0.0, 0.0, 0.0)
    lap, _ = P.build_lap(P.Ground([road], frame), P.Walls([walls], frame), -line)
    return lap


def _pixel(pic, f, x, z):
    px, py = preview.to_panel(x, z, f)
    return pic[int(py), int(px)].astype(float)


def _cos(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_the_land_takes_its_top_faces_colour(ring_lap):
    """Off the road each pixel has the hue of the face seen from above there (the mesh's shading scales it, 0.45-1.2): green
    west, red east, the raised patch's yellow over the red, the sea's blue exactly (flat, as the Saturn's water)."""
    pic = preview.course_picture(None, ring_lap, None, None, faces=_faces(), sea=_sea)
    f = preview.fit(centreline(ring_lap, spacing=5.0))
    for (x, z), want in {(-100, 0): GREEN, (-60, -120): GREEN, (-225, -60): GREEN, (100, 60): RED, (60, 140): RED,
                         (225, 0): RED, (90, -30): HIGH}.items():
        got = _pixel(pic, f, x, z)
        assert _cos(got, want) > 0.995, ((x, z), got, want)
    assert tuple(_pixel(pic, f, -200, 260)) == BLUE


def test_the_road_is_drawn_over_the_land(ring_lap):
    """Every centreline point clear of the start mark lands on the road's tarmac colour."""
    pic = preview.course_picture(None, ring_lap, None, None, faces=_faces(), sea=_sea)
    cl = centreline(ring_lap, spacing=5.0)
    f = preview.fit(cl)
    sx, sy = preview.to_panel(*cl[0], f)
    for k in range(0, len(cl), 3):
        x, y = preview.to_panel(*cl[k], f)
        if math.hypot(x - sx, y - sy) > 4:
            assert tuple(pic[int(y), int(x)]) == preview.TARMAC_RGB, k


def _road_mask(cl, f, reach):
    road = np.array([preview.to_panel(x, z, f) for x, z in cl + cl[:1]])
    yy, xx = np.mgrid[0:preview.H, 0:preview.W] + 0.5
    d = np.full(yy.shape, 1e9)
    for a, b in zip(road[:-1], road[1:]):
        v = b - a
        t = np.clip(((xx - a[0]) * v[0] + (yy - a[1]) * v[1]) / ((v ** 2).sum() or 1.0), 0, 1)
        d = np.minimum(d, np.hypot(xx - a[0] - t * v[0], yy - a[1] - t * v[1]))
    return d <= reach


def test_the_road_label_and_frame_are_the_saturn_paths(ring_lap, romset_zip, monkeypatch):
    """The same lap through the Saturn path (its terrain given the same faces) and the faces path: the road (wholly within its
    white edge), the start mark, the frame and the name's pixels are the same."""
    from vrtools.arcade.lettering import letters
    from vrtools.arcade.romset import RomSet
    masks = letters(RomSet.from_zip(romset_zip))
    ps2 = preview.course_picture(None, ring_lap, "ISLAND", masks, faces=_faces(), sea=_sea)
    bare = preview.course_picture(None, ring_lap, None, None, faces=_faces(), sea=_sea)
    monkeypatch.setattr(preview, "course_quads", lambda sat, groups: _faces())
    sat = preview.course_picture(object(), ring_lap, "ISLAND", masks)
    cl = centreline(ring_lap, spacing=5.0)
    road = _road_mask(cl, preview.fit(cl), preview.ROAD_EDGE / 2 - 0.75)
    label = (ps2 != bare).any(2)
    frame = np.zeros(road.shape, bool)
    frame[:2] = frame[-2:] = True
    frame[:, :2] = frame[:, -2:] = True
    assert road.sum() > 500 and label.sum() > 100
    for name, m in (("road", road), ("label", label), ("frame", frame)):
        assert np.array_equal(ps2[m], sat[m]), name


def test_the_saturn_path_is_unchanged_by_faces_none(ring_lap, monkeypatch):
    """`faces` None is the Saturn path as before: its colours come from the terrain's ramp by height (`course_quads`), not from the
    faces under each pixel. On the synthetic input the picture equals, pixel for pixel, a call that never passes `faces` or `sea`
    (also when only `sea` is passed: it is ignored without `faces`), and differs from the faces path's picture (pack 1's pictures
    are held byte for byte by tests/test_pack1_identity.py)."""
    monkeypatch.setattr(preview, "course_quads", lambda sat, groups: _faces())
    sat = preview.course_picture(object(), ring_lap, None, None, faces=None, sea=None)
    assert np.array_equal(sat, preview.course_picture(object(), ring_lap, None, None))
    assert np.array_equal(sat, preview.course_picture(object(), ring_lap, None, None, sea=_sea))
    assert not np.array_equal(sat, preview.course_picture(None, ring_lap, None, None, faces=_faces(), sea=_sea))


TARMAC_TOLERANCE = 8            # a road pixel lies within this of the tarmac colour per channel (the picture is quantised)
COLOURED = 30                   # a pixel is coloured when its channels differ by more than this
COLOURED_SHARE = 0.25           # Island's and Mountain's map areas: at least this share coloured (the grey pictures: 0.09, 0.07)


@pytest.fixture(scope="module")
def ps2_pictures():
    """name -> (picture with its name, centreline, fit) for the three PS2 courses, as ps2entry draws them."""
    from tests.reference_sets import missing_input, required_romset_zip
    from vrtools.arcade import pack as K, tencourse as T
    from vrtools.arcade.lettering import letters
    from vrtools.arcade.ps2entry import conversion
    from vrtools.arcade.romset import RomSet
    from vrtools.convert import ps2course as PC
    from vrtools.ps2 import disc as D
    from vrtools.ps2.course import load_from_disc
    path = D.ps2_disc()
    if path is None or not path.exists():
        missing_input(f"set {D.ENV} to the PS2 disc .cue")
    rs = RomSet.from_zip(required_romset_zip())
    masks, d, out = letters(rs), D.Ps2Disc(path), {}
    for plan in (K.ISLAND_TOP, K.MOUNTAIN_TOP, K.BELTWAY_TOP):
        course = load_from_disc(d, plan.index)
        frame = PC.Frame.for_host(rs, T.HOST_OF_BANK[plan.bank])
        conv = conversion(course, plan, frame)
        pic = preview.course_picture(None, conv.lap, plan.name, masks, faces=PC.picture_faces(course, frame), sea=PC.is_water)
        cl = centreline(conv.lap, spacing=5.0)
        out[plan.name] = (pic, cl, preview.fit(cl))
    return out


def test_ps2_pictures_are_coloured(ps2_pictures):
    """The owner's select sheet showed the three PS2 pictures grey. Now Island and Mountain have at least COLOURED_SHARE of
    their map area (frame and name excluded) in visibly coloured pixels (measured 0.82, 0.70; the grey ones 0.09, 0.07), Island
    a fifth of it sea blue and a tenth green, Mountain half of it brown; Beltway, a grey city by nature (its own pictures'
    concrete and roads), shows its parks green (5 %; measured 9 %) and its river blue (the grey picture had none)."""
    got = {}
    for name, (pic, _, _) in ps2_pictures.items():
        a = pic[2:148, 2:-2].astype(int)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        got[name] = {"coloured": float(((a.max(2) - a.min(2)) > COLOURED).mean()), "green": float(((g > r + 15) & (g > b + 15)).mean()),
                     "blue": float((b > r + 60).mean()), "brown": float(((r > b + 25) & (g > b + 10)).mean())}
    i, m, bw = got["ISLAND"], got["MOUNTAIN"], got["BELTWAY"]
    assert i["coloured"] >= COLOURED_SHARE and m["coloured"] >= COLOURED_SHARE, got
    assert i["blue"] >= 0.2 and i["green"] >= 0.1 and m["brown"] >= 0.5, got
    assert bw["green"] >= 0.05 and bw["blue"] >= 0.001, got


def test_ps2_pictures_road_frame_and_name(ps2_pictures):
    """On each PS2 picture the road runs under its centreline in the tarmac colour, the frame is the Saturn pictures' orange
    and the name is lettered white with its dark outline (test_convert_preview's checks of the Saturn pictures)."""
    for name, (pic, cl, f) in ps2_pictures.items():
        sx, sy = preview.to_panel(*cl[0], f)
        miss = [k for k in range(0, len(cl), 10) if math.hypot(*np.subtract(preview.to_panel(*cl[k], f), (sx, sy))) > 4
                and np.abs(pic[int(preview.to_panel(*cl[k], f)[1]), int(preview.to_panel(*cl[k], f)[0])].astype(int)
                           - preview.TARMAC_RGB).max() > TARMAC_TOLERANCE]
        assert not miss, (name, miss[:5])
        for edge in (pic[0], pic[1], pic[-1], pic[-2], pic[:, 0], pic[:, 1], pic[:, -1], pic[:, -2]):
            assert (edge == preview.FRAME).all(), name
        box = pic[150:164, 40:124].reshape(-1, 3)
        assert ((box == (240, 240, 240)).all(1)).any() and ((box == (16, 16, 16)).all(1)).any(), name
