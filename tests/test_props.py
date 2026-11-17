"""Phase 29: copies of an arcade prop baked into a converted course's scenery cells.

The prop's faces are read from the user's own polygon ROM at build time (`props.prop_from_cell`); `props.baked` turns and moves a
copy into world space as one-sided faces with the prop's own palette colours, which `geometry.assign_colours` writes back with
the arcade's drawn corners, lighting normal and palette index, culled (not record for record: `props`' docstring); `props.plant` stands each copy on the drawn ground and refuses a
site over the void, on a slope, against the Saturn's own upright scenery or near any collision quad (a car must never reach one).
The collision never sees a prop."""

import math

import pytest

from vrtools.arcade.colours import Palette
from vrtools.arcade.polyrom import encode_object, decode_object, quads as poly_quads
from vrtools.convert.geometry import ConvertError, WorldQuad, _normal, assign_colours
from vrtools.convert.props import (BIG_FOREST_TREE, PROP_CLEAR, ArcadeProp, Planting, PropFace, baked, ground_height, plant,
                                   planting_xz, prop_from_cell, prop_from_quads)

# A synthetic prop: a unit square face standing on the x axis (drawn corners in the arcade's winding) and a flat cap, two colours.
WALL = ((0.0, 0.0, 0.0), (0.0, 2.0, 0.0), (1.0, 2.0, 0.0), (1.0, 0.0, 0.0))
CAP = ((0.0, 2.0, 0.0), (0.0, 2.0, 1.0), (1.0, 2.0, 1.0), (1.0, 2.0, 0.0))
PROP = ArcadeProp((PropFace(WALL, 0x27D), PropFace(CAP, 0x27C)))


def _flat(y=5.0, half=100.0, rgb=(200, 200, 230)):
    """One big level ground quad centred on the origin."""
    return [WorldQuad(((-half, y, -half), (half, y, -half), (half, y, half), (-half, y, half)), rgb)]


def _pal():
    return Palette([0x7FFF] * 0x400)


def test_a_baked_copy_is_the_prop_turned_and_moved():
    """Heading h turns the prop about the vertical (x' = x cos h + z sin h, z' = -x sin h + z cos h, the converter's own rotation),
    then it moves to (x, y, z); every face is one-sided and keeps its palette index."""
    out = baked(PROP, 10.0, 3.0, -4.0, 90.0)
    assert len(out) == 2 and all(q.one_sided and isinstance(q, WorldQuad) for q in out)
    assert [q.palette for q in out] == [0x27D, 0x27C]
    a, d, c, b = out[0].p                          # stored in the Saturn's order: assign_colours reverses it back
    for got, want in zip((a, b, c, d), WALL):
        wx, wy, wz = want
        assert got == pytest.approx((10.0 + wz, 3.0 + wy, -4.0 - wx), abs=1e-9)


def test_assign_colours_writes_the_props_faces_with_the_arcades_corners_normal_and_colour():
    """The drawn corners come back in the prop's order, the lighting normal is the arcade's (the reversed winding's right-hand
    normal, as every original culled face stores it) and the colour entry is the prop's palette index, not a nearest colour."""
    out, words = assign_colours(baked(PROP, 0.0, 0.0, 0.0, 0.0), _pal(), tex_start=0x50000)
    assert sorted(words.values()) == [0x27C, 0x27D]
    wall = next(q for q in out if words[q.tex_adr] == 0x27D)
    assert wall.p == WALL and wall.one_sided
    a, b, c, d = WALL
    assert wall.normal == pytest.approx(_normal((a, d, c, b)))
    blob, layout = encode_object(out, tex_start=0x50000, no_cull=True)
    back = poly_quads(decode_object(blob, 0), 0x50000)
    assert len(back) == 2 and all(not (q.flags & 0x4000) for q in back)       # culled: drawn from the arcade's side only
    assert layout.record_count == 4


def test_a_quad_without_a_palette_index_still_takes_the_nearest_colour():
    pal = Palette([0x0000, 0x7FFF] + [0x0000] * 0x3FE)
    _, words = assign_colours([WorldQuad(WALL, (250, 250, 250))], pal, tex_start=0x50000)
    assert words == {0x50000: 1}


def test_ground_height_is_the_highest_drawn_surface_or_none():
    ground = _flat(5.0) + [WorldQuad(((-1, 9, -1), (1, 9, -1), (1, 9, 1), (-1, 9, 1)), (0, 0, 0))]
    assert ground_height(ground, 50.0, 50.0) == pytest.approx(5.0)
    assert ground_height(ground, 0.0, 0.0) == pytest.approx(9.0)
    assert ground_height(ground, 500.0, 0.0) is None
    slope = [WorldQuad(((0, 0, 0), (10, 10, 0), (10, 10, 10), (0, 0, 10)), (0, 0, 0))]
    assert ground_height(slope, 4.0, 5.0) == pytest.approx(4.0)


def test_planting_is_measured_from_the_road_point_to_the_right_of_travel():
    """Offset positive to the right of the direction of travel ((dz, -dx), the AI lines' convention), `along` ahead of the point."""
    cl = [(float(10 * k), 0.0) for k in range(10)]               # travelling +x
    assert planting_xz(cl, Planting(4, 12.0, 0.0)) == pytest.approx((40.0, -12.0))
    assert planting_xz(cl, Planting(4, -12.0, 0.0, along=3.0)) == pytest.approx((43.0, 12.0))


def test_a_planting_on_a_road_point_the_course_does_not_have_is_refused():
    """A point number past the centreline's end (or negative) is an error naming it, not another point by wrapping (review M7).
    The first and last points are the lap's own: their neighbours close the lap."""
    cl = [(float(10 * k), 0.0) for k in range(10)]
    for point in (10, 460, -1):
        with pytest.raises(ConvertError, match=f"road point {point}"):
            planting_xz(cl, Planting(point, 12.0, 0.0))
    planting_xz(cl, Planting(0, 12.0, 0.0))
    planting_xz(cl, Planting(9, 12.0, 0.0))


def test_a_capped_cell_that_holds_prop_faces_is_refused():
    """A cell over the record cap keeps its first split only; the props are added last, so the cap would drop their faces without
    a word (review M5). `geometry.first_split` (convert_tiles' own step) raises for a cell that holds prop faces, and caps a cell
    without any as before."""
    from vrtools.convert.geometry import first_split
    ground = [WorldQuad(((k, 0.0, 0.0), (k + 1.0, 0.0, 0.0), (k + 1.0, 0.0, 1.0), (k, 0.0, 1.0)), (200, 200, 230)) for k in range(6)]
    coloured, _ = assign_colours(ground + baked(PROP, 0.0, 0.0, 0.0, 0.0), _pal(), tex_start=0x50000)
    assert len(coloured) == 8
    first, over = first_split(0x45, coloured, 16, holds_props=True)                  # room for all 8 faces
    assert first == coloured and not over
    with pytest.raises(ConvertError, match="cell 0x45 holds prop faces"):
        first_split(0x45, coloured, 12, holds_props=True)                            # 6 faces fit: the prop's two would go
    first, over = first_split(0x45, coloured, 12)                                    # no props: capped as before
    assert first == coloured[:6] and over


def test_plant_stands_each_copy_on_the_ground():
    quads, sites = plant(PROP, [(20.0, 30.0, 45.0)], _flat(5.0), upright=[], collision=[])
    assert len(quads) == 2 and sites[0].y == pytest.approx(5.0) and (sites[0].x, sites[0].z) == (20.0, 30.0)
    assert min(p[1] for q in quads for p in q.p) == pytest.approx(5.0)


def test_plant_refuses_a_site_over_the_void_or_on_a_slope():
    with pytest.raises(ConvertError, match="no drawn ground"):
        plant(PROP, [(99.5, 0.0, 0.0)], _flat(5.0), upright=[], collision=[])
    steep = [WorldQuad(((-50, -150, -50), (50, 150, -50), (50, 150, 50), (-50, -150, 50)), (0, 0, 0))]     # 72 degrees
    with pytest.raises(ConvertError, match="slope"):
        plant(PROP, [(0.0, 0.0, 0.0)], steep, upright=[], collision=[])


def test_plant_refuses_a_site_near_a_collision_quad_or_the_saturns_upright_scenery():
    """A car must never reach a prop: every collision quad (tarmac, verge, run-off, pit lane) stays PROP_CLEAR away in XZ; and a
    prop never stands in the Saturn's own rocks, pines or buildings."""
    road = [((-5.0, 5.0, -50.0), (5.0, 5.0, -50.0), (5.0, 5.0, 50.0), (-5.0, 5.0, 50.0))]
    with pytest.raises(ConvertError, match="collision"):
        plant(PROP, [(5.0 + PROP_CLEAR - 0.5, 0.0, 0.0)], _flat(5.0), upright=[], collision=road)
    plant(PROP, [(5.0 + PROP_CLEAR + 0.5, 0.0, 0.0)], _flat(5.0), upright=[], collision=road)
    pine = WorldQuad(((30, 5, 0), (31, 15, 0), (32, 5, 0), (32, 5, 0)), (0, 128, 40))
    with pytest.raises(ConvertError, match="scenery"):
        plant(PROP, [(31.0, 1.0, 0.0)], _flat(5.0), upright=[pine], collision=[])


def test_a_copy_stays_whole_in_the_cell_of_its_foot():
    """A copy whose faces straddle a cell boundary is binned whole into the cell its foot stands in (the Saturn's faces go by their
    centres): a cell is drawn whole or not at all, so a tree split across two cells could show half of itself at the edge of the
    visible block."""
    from vrtools.convert.geometry import TILE_GRID
    from vrtools.convert.props import cells_by_foot
    foot = (-0.5, 5.0, 10.0)                                   # 0.5 units left of the boundary at x 0 (cells 128 wide from -1024)
    faces = baked(PROP, *foot, 90.0)                           # turned: the wall stays at x -0.5, the cap spans x -0.5..0.5
    assert len({TILE_GRID.cell_of(sum(p[0] for p in q.p) / 4, sum(p[2] for p in q.p) / 4) for q in faces}) == 2
    from vrtools.convert.props import Planted
    cells = cells_by_foot([(Planted(*foot, 90.0), faces)], TILE_GRID)
    assert list(cells) == [TILE_GRID.cell_of(-0.5, 10.0)] and cells[TILE_GRID.cell_of(-0.5, 10.0)] == faces


def test_prop_from_quads_takes_the_faces_near_a_point_with_their_colours():
    """The faces whose every corner lies within `radius` of (x, z), moved so the prop's foot (the middle of its lowest corners)
    is the origin; each face's palette index is its colour-table word's."""
    from vrtools.arcade.polyrom import Quad
    far = Quad(((100, 0, 0), (101, 0, 0), (101, 1, 0), (100, 1, 0)), (0, 0, 1), 0x1, 7)
    near = [Quad(tuple((x + 50.0, y + 30.0, z - 20.0) for x, y, z in f), (0, 0, 1), 0x1, t) for f, t in ((WALL, 5), (CAP, 6))]
    words = {5: 0x27D, 6: 0x427C}
    prop = prop_from_quads([far] + near, words.__getitem__, 50.5, -20.0, 3.0)
    assert [f.palette for f in prop.faces] == [0x27D, 0x27C]          # the bright bit is not a palette index
    assert prop.faces[0].p[0] == pytest.approx((-0.5, 0.0, 0.0))
    assert prop.height == pytest.approx(2.0)


# ---- Phase 34 (Pascal: "those ones are great keep saturn"): the planting rules it added, and a prop cut from the course itself ----

def test_plant_refuses_a_prop_whose_crown_reaches_towards_the_collision():
    """PROP_CLEAR is the foot's distance; a prop wider than it would hang its crown over the driveable area. No collision quad
    may lie within the prop's reach + CROWN_CLEAR of its foot either (Big Forest's tree, reach 5.1, and Surfers Road's palm, 5.2,
    are inside PROP_CLEAR - CROWN_CLEAR already)."""
    from vrtools.convert.props import CROWN_CLEAR
    wide = ArcadeProp((PropFace(tuple((12.0 * x, y, 12.0 * z) for x, y, z in CAP), 0xD1),))        # reaches 17 from its foot
    assert wide.radius == pytest.approx(12.0 * math.sqrt(2))
    road = [((-5.0, 5.0, -50.0), (5.0, 5.0, -50.0), (5.0, 5.0, 50.0), (-5.0, 5.0, 50.0))]
    with pytest.raises(ConvertError, match="crown"):
        plant(wide, [(5.0 + PROP_CLEAR + 0.5, 0.0, 0.0)], _flat(5.0), upright=[], collision=road)
    plant(wide, [(5.0 + wide.radius + CROWN_CLEAR + 0.5, 0.0, 0.0)], _flat(5.0), upright=[], collision=road)


def test_a_small_prop_is_held_to_the_same_slope_not_the_same_rise():
    """PROP_FLAT (4.5) is about a 25-degree slope across Big Forest's tree; across a prop 2 units wide the same rise would be a
    66-degree face. The rise allowed under a prop's reach is the smaller of PROP_FLAT and PROP_SLOPE (the tangent of 25 degrees)
    times its spread, so a small prop stands on the slopes a tree may and no steeper."""
    from vrtools.convert.props import PROP_FLAT, PROP_SLOPE
    small = ArcadeProp((PropFace(CAP, 0xD1),))                                   # reaches 1.41 from its foot: spread 2.83
    assert 2 * small.radius * PROP_SLOPE < PROP_FLAT
    def slope(rise):                                                             # rises `rise` per unit of x
        return [WorldQuad(((-50, -50 * rise, -50), (50, 50 * rise, -50), (50, 50 * rise, 50), (-50, -50 * rise, 50)), (0, 0, 0))]
    plant(small, [(0.0, 0.0, 0.0)], slope(0.40), upright=[], collision=[])        # 22 degrees
    with pytest.raises(ConvertError, match="slope"):
        plant(small, [(0.0, 0.0, 0.0)], slope(0.60), upright=[], collision=[])    # 31 degrees: 1.7 across it, under PROP_FLAT
    tree_wide = ArcadeProp((PropFace(tuple((3.6 * x, y, 3.6 * z) for x, y, z in CAP), 0xD1),))    # reach 5.09, the tree's
    assert 2 * tree_wide.radius * PROP_SLOPE > PROP_FLAT                          # the tree's limit stays PROP_FLAT
    plant(tree_wide, [(0.0, 0.0, 0.0)], slope(0.43), upright=[], collision=[])    # 4.4 across it


def test_plant_refuses_a_site_in_the_water():
    """A prop does not stand in the sea: where the drawn ground under its foot is water-coloured (`props.is_water`: a strong blue
    with little red, the Saturn's sea), the site is refused. Snow, sand, grass and tarmac are not water."""
    from vrtools.convert.props import is_water
    # The two sea colours are constants here on purpose: they are colour values, not course geometry, and they are what the rule
    # was written for (out/p34/scratch/gcol.py read them under the sites left of Surfers Road's road points 25-29). Reading them
    # from the disc at test time would mean converting the course (about two minutes) to learn two numbers; the build-level
    # guarantee is that `plant` runs this rule on every site of every plan.
    assert is_water((0, 184, 248)) and is_water((0, 200, 248))
    for rgb in ((200, 200, 230), (232, 240, 248), (176, 160, 64), (96, 208, 0), (88, 88, 88), (0, 128, 40), (136, 248, 0)):
        assert not is_water(rgb), rgb
    with pytest.raises(ConvertError, match="water"):
        plant(PROP, [(0.0, 0.0, 0.0)], _flat(0.0, rgb=(0, 184, 248)), upright=[], collision=[])
    shore = _flat(0.0, rgb=(0, 184, 248)) + [WorldQuad(((-3, 1, -3), (3, 1, -3), (3, 1, 3), (-3, 1, 3)), (176, 160, 64))]
    plant(PROP, [(0.0, 0.0, 0.0)], shore, upright=[], collision=[])              # sand drawn over the sea: the top surface counts
    with pytest.raises(ConvertError, match="water"):
        plant(PROP, [(1.8, 0.0, 0.0)], shore, upright=[], collision=[])          # the foot on sand, part of its reach over the sea


def _saturn_palm(x, z, y=5.0):
    """A synthetic palm of the converted course's own scenery: a trunk face and a leaf, Saturn-wound, two colours."""
    trunk = WorldQuad(((x - 0.5, y, z), (x + 0.5, y, z), (x + 0.5, y + 8.0, z), (x - 0.5, y + 8.0, z)), (200, 40, 160))   # invented
    leaf = WorldQuad(((x, y + 8.0, z), (x + 3.0, y + 9.0, z), (x + 3.0, y + 9.0, z + 1.0), (x, y + 8.0, z + 1.0)), (40, 16, 240))  # colours
    return [trunk, leaf]


def test_a_prop_can_be_cut_from_the_courses_own_scenery():
    """`CourseProp` names a prop among the converted course's own upright scenery (the Saturn's palms on Surfers Road): the faces
    whose every corner lies within `radius` of a point, moved so the foot (the middle of its lowest corners) is the origin, each
    with its Saturn colour. Its copies are baked as the course's own faces are: two-sided, the corners in the Saturn's order, the
    colour the nearest palette entry (no palette index, no mode), so a copy is the same species as the original."""
    from vrtools.convert.props import CourseProp, prop_from_course
    scenery = _saturn_palm(50.0, -20.0) + _saturn_palm(90.0, -20.0)
    src = CourseProp(Planting(4, 20.0, 0.0), radius=4.0, faces=2)
    prop = prop_from_course(scenery, 50.2, -20.1, src)
    assert len(prop.faces) == 2 and [f.rgb for f in prop.faces] == [(200, 40, 160), (40, 16, 240)]
    assert all(f.palette is None for f in prop.faces)
    assert prop.faces[0].p[0] == pytest.approx((-0.5, 0.0, 0.0)) and prop.height == pytest.approx(9.0)
    copies = baked(prop, 10.0, 2.0, 30.0, 0.0)
    assert [(q.rgb, q.one_sided, q.palette) for q in copies] == [((200, 40, 160), False, None), ((40, 16, 240), False, None)]
    for got, want in zip(copies[0].p, scenery[0].p):                             # the Saturn's own corner order, moved
        assert got == pytest.approx((want[0] - 40.0, want[1] - 3.0, want[2] + 50.0))
    pal = Palette([rgb555(200, 40, 160), rgb555(40, 16, 240)] + [0x0000] * 0x3FE)
    out, words = assign_colours(copies, pal, tex_start=0x50000)
    assert sorted(words.values()) == [0, 1] and all(not q.one_sided for q in out)
    with pytest.raises(ConvertError, match="2 faces, not 5"):
        prop_from_course(scenery, 50.2, -20.1, CourseProp(Planting(4, 20.0, 0.0), radius=4.0, faces=5))
    with pytest.raises(ConvertError, match="no prop face"):
        prop_from_course(scenery, 70.0, -20.0, src)


def rgb555(r, g, b):
    from vrtools.arcade.colours import rgb555_word
    return rgb555_word(r, g, b)


# ---- the user's own ROM ----

def test_big_forests_tree_is_read_from_the_rom(romset_zip):
    """BIG_FOREST_TREE: a 4-face canopy (three sides and its base) on a 3-face trunk, 16.35 high, in Big Forest's palette
    (three greens and a brown), all culled as the arcade draws them; nothing of it is stored in the repository."""
    from vrtools.arcade.course import tile_table
    from vrtools.arcade.romset import RomSet
    rs = RomSet.from_zip(romset_zip)
    prop = prop_from_cell(rs, BIG_FOREST_TREE)
    assert len(prop.faces) == 7
    assert sorted({f.palette for f in prop.faces}) == [0x27C, 0x27D, 0x27E, 0x27F]
    assert prop.height == pytest.approx(16.35, abs=0.01)
    assert min(p[1] for f in prop.faces for p in f.p) == pytest.approx(0.0)
    assert 4.0 < prop.radius < 5.5
    src = BIG_FOREST_TREE                                         # the source records themselves (review M2): properties only
    t = tile_table(rs, src.course)[src.cell]
    faces = [q for q in poly_quads(decode_object(rs.polygons, t.poly_adr, t.size), t.tex_adr)
             if all(math.hypot(p[0] - src.x, p[2] - src.z) <= src.radius for p in q.p)]
    assert len(faces) == 7
    assert all(not (q.flags & 0x4000) for q in faces)             # every face culled (bit 14 clear)
    for q in faces:                                               # the stored lighting normal: the reversed winding's right-hand
        a, b, c, d = q.p                                          # normal, which is what `baked` + `assign_colours` write
        assert q.normal == pytest.approx(_normal((a, d, c, b)), abs=2e-3)


def test_alpines_trees_are_in_its_cells(romset_zip, saturn_cue):
    """The build plants every Alpine site (report "props"), each over road points 400-449, and the cell its foot lies in carries
    the tree's faces exactly; no other course has any."""
    from tests.test_tgp_build import _built
    from vrtools.arcade.tencourse import ALPINE_TREES
    from vrtools.arcade.course import tile_table_at
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import TILE_GRID
    out, conv = _built(romset_zip, saturn_cue)
    alpine = conv[0]
    sites = alpine.report["props"]
    assert len(sites) == len(ALPINE_TREES) == 21
    assert all(400 <= s.point <= 449 for s in sites)
    assert all(not c.report.get("props") for c in conv[1:6])                  # (Phase 34: Surfers Road, the seventh, has its palms)
    prop = prop_from_cell(RomSet.from_zip(romset_zip), BIG_FOREST_TREE)
    table = tile_table_at(out, alpine.entry.tile_table)
    for s in sites:
        t = table[TILE_GRID.cell_of(s.x, s.z)]
        got = {tuple(round(v, 2) for p in q.p for v in p) for q in poly_quads(decode_object(out.polygons, t.poly_adr, t.size))}
        for q in baked(prop, s.x, s.y, s.z, s.heading):
            a, d, c, b = q.p
            assert any(tuple(round(v, 2) for p in r for v in p) in got for r in _rotations((a, b, c, d))), s


def _rotations(p):
    return [p[k:] + p[:k] for k in range(4)]


_BARE = {}


def _built_without_props(romset_zip, saturn_cue, course=0):
    """build_all with the plan of converted course `course` (0 Alpine, 6 Surfers Road: the two that have props) stripped of its
    props, once per session: the same build without that course's copies."""
    from dataclasses import replace
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.tencourse import COURSES, build_all
    key = (str(romset_zip), course)
    if key not in _BARE:
        assert [p.name for p in COURSES if p.props] == ["ALPINE", "SURFERS ROAD"] and COURSES[course].props
        plans = [replace(p, props=()) if k == course else p for k, p in enumerate(COURSES)]
        _BARE[key] = build_all(RomSet.from_zip(romset_zip), saturn_cue, plans)
    return _BARE[key]


def _cell(rs, t):
    """A tile cell's object bytes and its colour-table words, wherever they are stored."""
    from vrtools.arcade.colours import colour_table
    o = decode_object(rs.polygons, t.poly_adr, t.size)
    entries = 1 + sum(1 for r in o.records if r.tex_advance)
    table = colour_table(rs)
    return rs.polygons[4 * t.poly_adr:4 * (t.poly_adr + o.word_count)], [table.entry(t.tex_adr + i) for i in range(entries)]


def test_the_props_change_only_the_tree_cells(romset_zip, saturn_cue):
    """The same build with Alpine's `props=()` and with them (review I2; converter level, no MAME): the TGP data (the collision) and
    the TGP program are byte for byte the same; the three original courses' tile tables are the user's ROM's own, with every cell's
    object bytes and colour words; every converted cell that holds no tree has the same object bytes and colour words in both
    builds (they may be stored elsewhere: Alpine grows ahead of the other six); only Alpine's cells with a tree's foot in them
    differ, each by 14 records a tree (7 one-sided faces, a chain of 2 records each) and the tree's four palette indices."""
    from collections import Counter
    from tests.test_tgp_build import _built
    from vrtools.arcade.course import tile_table, tile_table_at
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import TILE_GRID
    rs = RomSet.from_zip(romset_zip)
    out, conv = _built(romset_zip, saturn_cue)
    bare, bare_conv = _built_without_props(romset_zip, saturn_cue)
    assert out.copro_data == bare.copro_data and out.tgp_program == bare.tgp_program == rs.tgp_program
    assert out.boot == bare.boot
    for course in range(3):                                                        # the originals: in place, as the user's ROM has them
        src = tile_table(rs, course)
        assert tile_table(out, course) == tile_table(bare, course) == src, course
        for t in src:
            if t.size:
                assert _cell(out, t) == _cell(bare, t) == _cell(rs, t), (course, t.cell)
    trees = Counter(TILE_GRID.cell_of(s.x, s.z) for s in conv[0].report["props"])
    assert sum(trees.values()) == 21 and len(trees) == 4
    assert not bare_conv[0].report.get("props")
    moved = 0
    for k, (c, b) in enumerate(zip(conv, bare_conv)):
        assert c.entry.tile_table == b.entry.tile_table
        with_props, without = tile_table_at(out, c.entry.tile_table), tile_table_at(bare, b.entry.tile_table)
        assert len(with_props) == len(without)
        for cell, (x, y) in enumerate(zip(with_props, without)):
            if k == 0 and cell in trees:
                assert x.size == y.size + 14 * trees[cell], (cell, x.size, y.size)
                xo, xw = _cell(out, x)
                yo, yw = _cell(bare, y)
                assert xo != yo and not Counter(yw) - Counter(xw)                # the cell's own colour words all kept,
                assert sorted(w & 0x3FF for w in (Counter(xw) - Counter(yw)).elements()) == [0x27C, 0x27D, 0x27E, 0x27F]   # + the tree's
                continue
            assert x.size == y.size, (k, cell)
            if x.size:
                assert _cell(out, x) == _cell(bare, y), (k, cell)
                moved += (x.poly_adr, x.tex_adr) != (y.poly_adr, y.tex_adr)
    assert moved                                                                   # identical in content, not in place (findings §3.1)


def test_trees_stay_clear_of_alpines_collision(romset_zip, saturn_cue):
    """Every planted tree is at least PROP_CLEAR in XZ from every collision quad the built set's TGP data gives Alpine (read back
    from the ROM through its collision map and slot: the tarmac, verges, run-off and pit lane, so the walls at their edges)."""
    from tests.test_tgp_build import _built
    from vrtools.arcade.course import collision_map, course_entry_at
    from vrtools.arcade.tgp import QUAD_WORDS, decode_quad, slot_table, words
    from vrtools.convert.props import xz_distance
    out, conv = _built(romset_zip, saturn_cue)
    e = conv[0].entry
    block, pool = slot_table(out)[e.tgp_slot]
    w = words(out)
    ids = {v for v in collision_map(out, course_entry_at(out, e.bank, window_base=e.header_base)) if v}
    index = {i for v in ids for i in w[block + v + 1:block + v + 1 + w[block + v]]}
    col = [decode_quad(w, pool + QUAD_WORDS * i).corners for i in sorted(index)]
    assert len(col) > 1000
    for s in conv[0].report["props"]:
        assert min(xz_distance(c, s.x, s.z) for c in col) >= PROP_CLEAR, s


# ---- MAME: the trees are drawn and the arcade's rate holds ----

TREE_SECONDS = 130          # the autopilot (the standing test's line) reaches road points 400-449 at about 92-99 s of the run, and in reverse passes them twice
TREE_WINDOW = [k % 452 for k in range(380, 452 + 15)]   # Alpine's road points from 20 before the stretch to 15 past the line


@pytest.mark.parametrize("reverse", [False, True], ids=["normal", "reverse"])
def test_alpines_trees_are_drawn_and_the_rate_holds(tmp_path, romset_zip, saturn_cue, reverse):
    """An Alpine race on the built set (the standing rate test's autopilot line, the clock held), the display list dumped every 20
    frames: while the player is on the approach to and along road points 400-449 (TREE_WINDOW, in the run's own numbering in
    reverse), every cell that carries trees is drawn on some dumped frame, and on at least 10 dumped frames some tree cell is. The
    display list's command names the cell's object and a record limit (the frame's draw budget, not the object's size); the object
    there runs to its end marker in fewer records than that limit, and those records are the with-trees count, 14 a tree more than
    the same cell's object in the build without props (review M3): the list draws the object whole, the trees' records with it.
    Those objects in the set's polygon ROM hold the trees' faces (test_alpines_trees_are_in_its_cells). The three measures of the arcade's
    rate hold from the race's first pass: the overrun counter still, the V60 busy under two vblanks, the render rate 28-29 from the
    green."""
    from collections import Counter
    from tests.test_race_build import _drive_line
    from tests.test_tgp_build import _build, _seven
    from vrtools.arcade.course import tile_table_at
    from vrtools.arcade.dlist import parse_log
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.convert.geometry import TILE_GRID
    from vrtools.convert.reverse import reverse_points
    from vrtools.mame.framerate import arcade_rate_misses, parse_frame_log
    from vrtools.mame.runner import LUA_DIR, parse_race_log, parse_rate, run_mame, write_centreline
    out, conv = _seven(romset_zip, saturn_cue)
    alpine = conv[0]
    table = tile_table_at(out, alpine.entry.tile_table)
    trees = Counter(TILE_GRID.cell_of(s.x, s.z) for s in alpine.report["props"])
    tree_cells = {table[cell].poly_adr for cell in trees}
    bare = tile_table_at(_built_without_props(romset_zip, saturn_cue)[0], alpine.entry.tile_table)
    size_with = {table[cell].poly_adr: table[cell].size for cell in trees}
    assert all(table[cell].size == bare[cell].size + 14 * n for cell, n in trees.items())
    build = _build(tmp_path, romset_zip, out)
    line = _drive_line(alpine)
    wd = tmp_path / "run"
    env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[3]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
           "VR_AUTOPILOT": str(write_centreline(tmp_path / "line.csv", reverse_points(line) if reverse else line)),
           "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0", "VR_HOLD_CLOCK": "1",
           "VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"),
           "VR_DLIST_LOG": str(wd / "dlist.txt"), "VR_DLIST_FROM": "1600", "VR_DLIST_EVERY": "20"}
    if reverse:
        env["VR_DIRECTION"] = "1"
    run_mame(LUA_DIR / "autoplay.lua", TREE_SECONDS, wd, build, env=env, timeout=3600)
    n = len(alpine.centreline)
    window = {(n - k) % n for k in TREE_WINDOW} if reverse else set(TREE_WINDOW)
    players = parse_race_log(wd / "race.txt")[0]
    point = {p.frame: p.road_point for p in players}
    clocks = [(p.frame, p.clock) for p in players]
    load = next(f for f, c in clocks if c > 0)
    green = next(clocks[i][0] for i in range(1, len(clocks)) if clocks[i][0] > load and 0 < clocks[i][1] < clocks[i - 1][1])
    seen, drawn, sizes = 0, set(), set()
    for frame, _, cmds in parse_log(wd / "dlist.txt"):
        if frame < green or point.get(frame) not in window:
            continue
        objs = {c.args["poly_adr"] for c in cmds if c.kind == 0x01} & tree_cells
        seen += bool(objs)
        drawn |= objs
        sizes |= {(c.args["poly_adr"], c.args["size"]) for c in cmds if c.kind == 0x01 and c.args["poly_adr"] in tree_cells}
    assert seen >= 10, ("tree cells drawn on too few dumped frames", seen)
    assert drawn == tree_cells, sorted(tree_cells - drawn)
    assert {adr for adr, _ in sizes} == tree_cells
    for adr, limit in sizes:                                                 # each drawn whole: the object ends (its end marker) within
        assert len(decode_object(out.polygons, adr).records) == size_with[adr] <= limit, (adr, limit)   # the command's record limit
    frames = parse_frame_log(wd / "frames.txt")
    start = next(f.frame for f in frames if f.frame >= load) + 1
    assert arcade_rate_misses(frames, parse_rate(wd / "rate.txt"), start, rate_from=green) == []


# ---- Phase 34: 13 more of Surfers Road's own palms (Pascal, after driving them: "those ones are great keep saturn") ----

SURFERS = 6                        # Surfers Road among the converted courses (menu entry 9)
PALM_FACES = 28                    # the course's own roadside palm: trunk, leaves and coconuts
PALM_RECORDS = 54                  # a copy: its 28 two-sided faces as the converter chains them


def _palm_cells(conv):
    from collections import Counter
    from vrtools.convert.geometry import TILE_GRID
    return Counter(TILE_GRID.cell_of(s.x, s.z) for s in conv[SURFERS].report["props"])


def test_surfers_palms_are_in_its_cells(romset_zip, saturn_cue):
    """The build plants 13 copies of Surfers Road's own roadside palm (the plan's `SURFERS_ROAD_PALM`: the 28 faces of the Saturn's
    palm right of road point 47, 11.4 units tall, reaching 5.2, in the Saturn's colours) along road points 25-99; the cell each
    foot lies in carries the whole copy, every face two-sided as the Saturn's own scenery is; the source palm is still where it
    was, in its own cell; no cell of the course is capped; the row's spacing varies (10 units and more between neighbours)."""
    from tests.test_tgp_build import _built
    from vrtools.arcade.course import tile_table_at
    from vrtools.arcade.tencourse import COURSES, SURFERS_PALMS, SURFERS_ROAD_PALM
    from vrtools.convert.geometry import TILE_GRID
    from vrtools.convert.props import Planted
    out, conv = _built(romset_zip, saturn_cue)
    surfers = conv[SURFERS]
    assert COURSES[SURFERS].name == "SURFERS ROAD" and COURSES[SURFERS].props == ((SURFERS_ROAD_PALM, SURFERS_PALMS),)
    sites = surfers.report["props"]
    (prop,) = surfers.report["prop_models"]
    assert len(sites) == len(SURFERS_PALMS) == 13 and surfers.report["prop_faces"] == 13 * PALM_FACES
    assert all(25 <= s.point <= 99 for s in sites)
    assert surfers.report["capped_cells"] == 0
    gaps = [min(math.hypot(a.x - b.x, a.z - b.z) for b in sites if b is not a) for a in sites]
    assert min(gaps) >= 10.0 and len({round(g) for g in gaps}) >= 4
    assert len(prop.faces) == PALM_FACES and all(f.rgb is not None and f.palette is None for f in prop.faces)
    assert prop.height == pytest.approx(11.44, abs=0.05) and prop.radius == pytest.approx(5.17, abs=0.05)
    assert min(p[1] for f in prop.faces for p in f.p) == 0.0                     # it stands on its foot
    table = tile_table_at(out, surfers.entry.tile_table)

    def held(cell):
        got = {}
        for q in poly_quads(decode_object(out.polygons, table[cell].poly_adr, table[cell].size)):
            for r in _rotations(tuple(q.p)) + _rotations(tuple(q.p)[::-1]):
                got[tuple(round(v, 2) for p in r for v in p)] = q
        return got

    for s in sites:
        got = held(TILE_GRID.cell_of(s.x, s.z))
        ys = []
        for q in baked(prop, s.x, s.y, s.z, s.heading):
            found = got.get(tuple(round(v, 2) for p in q.p for v in p))
            assert found is not None, (s, q.p)
            assert found.flags & 0x4000 and (found.flags >> 10) & 3 == 2 and (found.flags >> 17) & 15 == 0, s   # two-sided, the
            ys += [p[1] for p in q.p]                                                                           # converter's modes
        assert max(ys) - min(ys) == pytest.approx(prop.height, abs=1e-3)         # the Saturn palm's own size: nothing scaled
    x, z = planting_xz(surfers.centreline, SURFERS_ROAD_PALM.site)              # the source: unturned, unmoved, in its own cell
    source = [q for q in poly_quads(decode_object(out.polygons, table[TILE_GRID.cell_of(x, z)].poly_adr,
                                                  table[TILE_GRID.cell_of(x, z)].size))
              if all(math.hypot(c[0] - x, c[2] - z) <= SURFERS_ROAD_PALM.radius for c in q.p)]
    assert len(source) == PALM_FACES
    assert TILE_GRID.cell_of(x, z) not in _palm_cells(conv)                      # no copy shares the source's cell


def _collision_quads(out, entry):
    """The collision quads the built set's TGP data gives a course, read back through its collision map and slot."""
    from vrtools.arcade.course import collision_map, course_entry_at
    from vrtools.arcade.tgp import QUAD_WORDS, decode_quad, slot_table, words
    block, pool = slot_table(out)[entry.tgp_slot]
    w = words(out)
    ids = {v for v in collision_map(out, course_entry_at(out, entry.bank, window_base=entry.header_base)) if v}
    index = {i for v in ids for i in w[block + v + 1:block + v + 1 + w[block + v]]}
    return [decode_quad(w, pool + QUAD_WORDS * i).corners for i in sorted(index)]


def test_palms_stay_clear_of_surfers_collision(romset_zip, saturn_cue):
    """Every planted palm's foot is at least PROP_CLEAR in XZ from every collision quad the built set's TGP data gives Surfers
    Road (the tarmac, verges, run-off and pit lane, so the walls at their edges), and no corner of any face of any copy (the crown
    reaches 5.2 from the foot) comes within 5 units of one (Big Forest's tree on Alpine: 4.9): nothing hangs over where a car can
    stand. Every corner of every copy is measured against every collision quad of the course."""
    from tests.test_tgp_build import _built
    from vrtools.convert.props import xz_distance
    out, conv = _built(romset_zip, saturn_cue)
    col = _collision_quads(out, conv[SURFERS].entry)
    assert len(col) > 1000
    (prop,) = conv[SURFERS].report["prop_models"]
    worst = float("inf")
    for s in conv[SURFERS].report["props"]:
        foot = [xz_distance(c, s.x, s.z) for c in col]                         # every collision quad of the course
        assert min(foot) >= PROP_CLEAR, s
        corners = {(round(p[0], 3), round(p[2], 3)) for q in baked(prop, s.x, s.y, s.z, s.heading) for p in q.p}
        worst = min(worst, min(xz_distance(c, x, z) for c in col for x, z in corners))        # every corner, every quad
    assert 5.0 < worst < PROP_CLEAR, worst                                     # (measured 5.61; under PROP_CLEAR: the crowns do reach in)


def test_the_palms_change_only_the_palm_cells(romset_zip, saturn_cue):
    """The same build with Surfers Road's `props=()` and with them (converter level, no MAME): the TGP data (the collision), the TGP
    program and the boot ROM are byte for byte the same; the three originals' tile tables, objects and colour words are the user's
    ROM's own, in place; every cell of the six courses before Surfers Road (Alpine's tree cells among them) is the same bytes and
    colour words at the same addresses; of Surfers Road's cells only the four with a palm's foot in them differ: each grows by 54
    records a palm (28 two-sided faces), keeps every colour word it had and gains only palette indices that are the nearest colours
    of the palm's own faces (at most one entry a colour). Its other cells have the same object bytes and colour words (some stored
    elsewhere: they follow the grown cells)."""
    from collections import Counter
    from tests.test_tgp_build import _built
    from vrtools.arcade.colours import PALETTE_BASE, nearest, palette_from_rom
    from vrtools.arcade.course import tile_table, tile_table_at
    from vrtools.arcade.romset import RomSet
    rs = RomSet.from_zip(romset_zip)
    out, conv = _built(romset_zip, saturn_cue)
    bare, bare_conv = _built_without_props(romset_zip, saturn_cue, SURFERS)
    assert out.copro_data == bare.copro_data and out.tgp_program == bare.tgp_program == rs.tgp_program
    assert out.boot == bare.boot
    for course in range(3):
        src = tile_table(rs, course)
        assert tile_table(out, course) == tile_table(bare, course) == src, course
        for t in src:
            if t.size:
                assert _cell(out, t) == _cell(bare, t) == _cell(rs, t), (course, t.cell)
    palms = _palm_cells(conv)
    assert sum(palms.values()) == 13 and sorted(palms.values()) == [1, 2, 2, 8]
    assert not bare_conv[SURFERS].report.get("props")
    assert len(conv[0].report["props"]) == len(bare_conv[0].report["props"]) == 21          # Alpine's trees: in both
    (prop,) = conv[SURFERS].report["prop_models"]
    pal = palette_from_rom(rs, 0)
    palm_words = {(nearest(pal, f.rgb) - PALETTE_BASE) & 0x3FF for f in prop.faces}        # the palette indices its faces take
    assert 8 <= len(palm_words) <= 13
    moved = gained = 0
    for k, (c, b) in enumerate(zip(conv, bare_conv)):
        assert c.entry.tile_table == b.entry.tile_table
        with_props, without = tile_table_at(out, c.entry.tile_table), tile_table_at(bare, b.entry.tile_table)
        assert len(with_props) == len(without)
        for cell, (x, y) in enumerate(zip(with_props, without)):
            if k == SURFERS and cell in palms:
                xo, xw = _cell(out, x)
                yo, yw = _cell(bare, y)
                assert x.size == y.size + PALM_RECORDS * palms[cell], (cell, x.size, y.size)
                assert xo != yo and not Counter(yw) - Counter(xw)                # the cell's own colour words all kept
                new = [w & 0x3FF for w in (Counter(xw) - Counter(yw)).elements()]
                assert len(new) == len(set(new)) and set(new) <= palm_words, (cell, new)   # + the palm's, one entry a colour
                assert palm_words <= {w & 0x3FF for w in xw}, cell                # every colour of the palm is in the cell
                gained += len(new)
                continue
            assert x.size == y.size, (k, cell)
            if x.size:
                assert _cell(out, x) == _cell(bare, y), (k, cell)
                if k < SURFERS:
                    assert (x.poly_adr, x.tex_adr) == (y.poly_adr, y.tex_adr), (k, cell)     # the earlier courses: in place
                moved += (x.poly_adr, x.tex_adr) != (y.poly_adr, y.tex_adr)
    assert moved                                                                   # Surfers Road's later cells: not in place
    assert 0 < gained <= 4 * len(palm_words)                                       # the colour entries the palms cost in all


DRAW_BUDGET = 10_500
SURFERS_NON_CELL = 4_500    # records a Surfers Road frame may hold besides its tile cells (the cars, the start gantry, the figures,
                            # the HUD's objects): the most measured is 3 633, on the grid, in 616 dumped frames of two autopilot
                            # races on the set that had Bay Bridge's palms (out/p34/scratch/noncell.py; palms are cell records
                            # and do not enter it); rounded up. Not a proof off that line: with the worst block at 4 280 the
                            # bound holds for anything up to 6 219


def test_surfers_road_fits_the_draw_budget_wherever_the_camera_is(romset_zip, saturn_cue):
    """(Review I2.) A bound that does not depend on the autopilot's line: the game draws the tile cells of the 5 x 5 block around
    the camera's cell (the Phase 28 recon's §5), each whole. For every one of the 256 camera cells, the records of all the cells
    of its block (as if every one were drawn), with the palms, plus SURFERS_NON_CELL stay under the draw budget."""
    from tests.test_tgp_build import _built
    from vrtools.arcade.budget import FRAME_BUDGET
    from vrtools.arcade.course import tile_table_at
    out, conv = _built(romset_zip, saturn_cue)
    assert FRAME_BUDGET == DRAW_BUDGET
    size = {(t.x_cell, t.z_cell): t.size for t in tile_table_at(out, conv[SURFERS].entry.tile_table)}
    assert len(size) == 256 and sum(1 for n in size.values() if n) == conv[SURFERS].report["cells"]
    block = {(x, z): sum(size.get((x + i, z + j), 0) for i in range(-2, 3) for j in range(-2, 3)) for x in range(16) for z in range(16)}
    worst = max(block, key=block.get)
    assert block[worst] + SURFERS_NON_CELL < FRAME_BUDGET, (worst, block[worst])
    assert block[worst] >= max(size.values()) > 0                                 # (a block holds at least its largest cell)


_BARE_SET = {}


def _set_without_palms(romset_zip, saturn_cue):
    """The ten-course set of the build without Surfers Road's palms (Alpine's trees in it), once per session."""
    from vrtools.arcade.tencourse import ten_course_set
    key = str(romset_zip)
    if key not in _BARE_SET:
        bare, bare_conv = _built_without_props(romset_zip, saturn_cue, SURFERS)
        _BARE_SET[key] = (ten_course_set(bare, bare_conv), bare_conv)
    return _BARE_SET[key]


ROMS = ("program", "boot", "data", "polygons", "copro_data", "tgp_program")


def test_without_the_palms_the_set_is_the_base_branchs(romset_zip, saturn_cue):
    """Opt-in, a record of the branch against its base and not a standing gate (the base is a git-ignored build frozen at one
    commit; without VR_P34_BASE_SET the test skips and says so). This tree's set built without Surfers Road's palms is, ROM for
    ROM, the set main builds (VR_P34_BASE_SET: a directory holding a `vrtools build` of main at c94d7d9): nothing else this
    phase touched (the course prop source, the slope, crown and water rules, the report) changes a byte, and Alpine's trees and
    Metropolis's far copies are built exactly as there; the collision, the TGP program and the boot ROM of the set with the palms
    are main's. With VR_P34_SET (a built set's directory): that set is, ROM for ROM, this
    session's set with the palms.
    Phase 33 (the three originals in reverse) ends this record's use: with it the set differs from c94d7d9's in every ROM the
    originals' variants write, the boot ROM among them (the lock site, the picture data in its erased run), so opted in after
    that phase the test FAILS by design. It is kept as Phase 34's record; the skip's reason says so."""
    import os
    from pathlib import Path
    from tests.test_tgp_build import _seven
    from vrtools.arcade.romset import RomSet
    if not os.environ.get("VR_P34_BASE_SET"):
        pytest.skip("opt-in record of Phase 34 against its base: set VR_P34_BASE_SET to a directory holding a `vrtools build` of main "
                    "at c94d7d9. It holds only on a tree WITHOUT Phase 33: with the originals' reverse variants the set differs from "
                    "that base in the boot ROM and others, and this test then fails by design")
    base = Path(os.environ["VR_P34_BASE_SET"])
    assert (base / "vr.zip").is_file(), f"VR_P34_BASE_SET names {base}, which holds no vr.zip"
    theirs = RomSet.from_zip(base / "vr.zip", verify=False)
    ours, _ = _set_without_palms(romset_zip, saturn_cue)
    for name in ROMS:
        assert getattr(ours, name) == getattr(theirs, name), name
    with_palms, _ = _seven(romset_zip, saturn_cue)
    assert with_palms.copro_data == theirs.copro_data and with_palms.tgp_program == theirs.tgp_program      # the collision
    assert with_palms.boot == theirs.boot
    play = os.environ.get("VR_P34_SET")                                          # the playtest set handed to Pascal, when named
    if play:
        handed = RomSet.from_zip(Path(play) / "vr.zip", verify=False)
        for name in ROMS:
            assert getattr(with_palms, name) == getattr(handed, name), name


# ---- MAME: the palms are drawn, the race is the same and the arcade's rate holds ----

PALM_SECONDS = 135          # the autopilot passes road points 25-99 at about 37-49 s of the run, in reverse at about 84-93 s
PALM_WINDOW = list(range(15, 106))    # Surfers Road's road points from 10 before the stretch to 6 past it
PALM_STRETCH = set(range(25, 100))


def _pass_lines(path):
    lines = open(path).read().split("\n")
    assert lines[-2:] == ["END", ""] or lines[-1] == "END", "the pass log did not end"
    return [l for l in lines if l.startswith("W ")]


@pytest.mark.parametrize("reverse", [False, True], ids=["normal", "reverse"])
def test_surfers_palms_are_drawn_the_race_is_the_same_and_the_rate_holds(tmp_path, romset_zip, saturn_cue, reverse, record_property):
    """Two Surfers Road races of PALM_SECONDS from a fresh battery RAM, the clock held: on the set built without the palms, under
    the standing rate test's autopilot line, its wheel and pedal recorded (input_tape.lua); then on the set with them, fed that
    tape frame for frame.
    - The race is the same: the tape is fed line for line and the game's state at the end of every logic pass (pass_state.lua:
      the clock and all 16 cars' position, road point, speed and lap) is identical in the two runs.
    - The palms are drawn: while the player is on PALM_WINDOW, every cell that carries palms is named in the display list on some
      dumped frame (every 20th), on at least 10 dumped frames some palm cell is, and each such object runs to its end marker in the
      with-palms record count (larger than the build without), under the command's record limit.
    - The arcade's rate holds from the race's first pass: the overrun counter still, the V60 busy under two vblanks and identical
      frame for frame to the run without palms, the render rate 28-29 from the green, no list skipped; and every frame of the race
      stays under the draw budget (Surfers Road's standing budget assertion), the palms adding no more records to any frame of the
      stretch than their four cells hold (the added records are reported: `record_property`)."""
    import statistics
    from tests.test_race_build import _drive_line
    from tests.test_tgp_build import _build, _seven
    from vrtools.arcade.course import tile_table_at
    from vrtools.arcade.dlist import parse_log
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.convert.reverse import reverse_points
    from vrtools.mame.framerate import arcade_rate_misses, parse_frame_log
    from vrtools.mame.runner import LUA_DIR, parse_race_log, parse_rate, run_mame, write_centreline
    out, conv = _seven(romset_zip, saturn_cue)
    bare, bare_conv = _set_without_palms(romset_zip, saturn_cue)
    surfers = conv[SURFERS]
    table, bare_table = tile_table_at(out, surfers.entry.tile_table), tile_table_at(bare, bare_conv[SURFERS].entry.tile_table)
    palms = _palm_cells(conv)
    grown = {cell: table[cell].size - bare_table[cell].size for cell in palms}
    assert grown == {cell: PALM_RECORDS * n for cell, n in palms.items()}
    palm_cells = {table[cell].poly_adr: table[cell].size for cell in palms}
    line = _drive_line(surfers)
    assert line == _drive_line(bare_conv[SURFERS])
    logs = {}
    for tag, rs in (("base", bare), ("palms", out)):
        (tmp_path / tag).mkdir()
        build = _build(tmp_path / tag, romset_zip, rs)
        wd = tmp_path / tag / "run"
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[3 + SURFERS]), "VR_COLLISION_LOG": str(wd / "c.txt"), "VR_SNAPS": "",
               "VR_AUTOPILOT": str(write_centreline(tmp_path / tag / "line.csv", reverse_points(line) if reverse else line)),
               "VR_RACE_LOG": str(wd / "race.txt"), "VR_RACE_LOG_FROM": "0", "VR_HOLD_CLOCK": "1",
               "VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"), "VR_PASS_LOG": str(wd / "pass.txt"),
               "VR_INPUT_LOG": str(wd / "tape.txt")}
        if reverse:
            env["VR_DIRECTION"] = "1"
        if tag == "palms":
            env.update({"VR_INPUT_REPLAY": str(logs["base"] / "tape.txt"), "VR_DLIST_LOG": str(wd / "dlist.txt"),
                        "VR_DLIST_FROM": "1600", "VR_DLIST_EVERY": "20"})
        run_mame(LUA_DIR / "autoplay.lua", PALM_SECONDS, wd, build, env=env, timeout=3600)
        logs[tag] = wd
    base, wd = logs["base"], logs["palms"]
    assert (wd / "tape.txt").read_text() == (base / "tape.txt").read_text()                    # fed line for line
    ours, theirs = _pass_lines(wd / "pass.txt"), _pass_lines(base / "pass.txt")
    assert len(ours) == len(theirs) > 3000
    assert ours == theirs                                                                    # the game's state, pass for pass
    n = len(surfers.centreline)
    turn = (lambda k: (n - k) % n) if reverse else (lambda k: k)
    window, stretch = {turn(k) for k in PALM_WINDOW}, {turn(k) for k in PALM_STRETCH}
    players = parse_race_log(wd / "race.txt")[0]
    point = {p.frame: p.road_point for p in players}
    clocks = [(p.frame, p.clock) for p in players]
    load = next(f for f, c in clocks if c > 0)
    green = next(clocks[i][0] for i in range(1, len(clocks)) if clocks[i][0] > load and 0 < clocks[i][1] < clocks[i - 1][1])
    seen, drawn, sizes = 0, set(), set()
    for frame, _, cmds in parse_log(wd / "dlist.txt"):
        if frame < green or point.get(frame) not in window:
            continue
        objs = {c.args["poly_adr"] for c in cmds if c.kind == 0x01} & set(palm_cells)
        seen += bool(objs)
        drawn |= objs
        sizes |= {(c.args["poly_adr"], c.args["size"]) for c in cmds if c.kind == 0x01 and c.args["poly_adr"] in palm_cells}
    assert seen >= 10, ("palm cells drawn on too few dumped frames", seen)
    assert drawn == set(palm_cells), sorted(set(palm_cells) - drawn)
    for adr, limit in sizes:
        assert len(decode_object(out.polygons, adr).records) == palm_cells[adr] <= limit, (adr, limit)
    frames, base_frames = parse_frame_log(wd / "frames.txt"), parse_frame_log(base / "frames.txt")
    start = next(f.frame for f in frames if f.frame >= load) + 1
    assert arcade_rate_misses(frames, parse_rate(wd / "rate.txt"), start, rate_from=green) == []
    race = [f for f in frames if f.frame >= start]
    assert sum(1 for f in race if f.skipped) == 0 and max(f.records for f in race) < DRAW_BUDGET
    assert max(f.need for f in race) < DRAW_BUDGET and {f.budget for f in race} == {DRAW_BUDGET}   # (review I2) need: the least budget
                                                                                                # under which the frame skips no list
    before = {f.frame: f for f in base_frames}
    on = [f for f in race if f.frame > green and point.get(f.frame) in stretch and f.frame in before]
    assert len(on) > 200, ("the player was on the stretch for too few frames", len(on))
    added = [f.records - before[f.frame].records for f in on]
    assert min(added) >= 0 and max(added) <= sum(grown.values())
    assert [f.busy_us for f in race if f.frame in before] == [before[f.frame].busy_us for f in race if f.frame in before]
    summary = (f"stretch frames {len(on)}; records a frame there, without {statistics.median(before[f.frame].records for f in on)} "
               f"median {max(before[f.frame].records for f in on)} max, with {statistics.median(f.records for f in on)} median "
               f"{max(f.records for f in on)} max; added {min(added)}..{max(added)}, median {statistics.median(added)}; race records "
               f"max {max(f.records for f in race)}, need max {max(f.need for f in race)}; worst busy {max(f.busy_us for f in race)} us; passes {len(ours)}")
    record_property("palms", summary)
    print(("reverse: " if reverse else "normal: ") + summary)
