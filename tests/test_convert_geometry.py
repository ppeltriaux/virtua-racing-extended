import pytest

from vrtools.arcade.colours import Palette
from vrtools.convert.geometry import (SCALE, CellGrid, WorldQuad, assign_colours, bin_quads, course_quads, face_quads,
                                      rgb555, to_arcade)
from vrtools.saturn.course import Face, Mesh, Placement


def test_to_arcade_transform():
    assert to_arcade(1.0, 2.0, 3.0) == pytest.approx((-SCALE, 2.0 * SCALE, -3.0 * SCALE))


def test_rgb555_saturn_r_low():
    assert rgb555(0x001F) == (248, 0, 0) and rgb555(0x03E0) == (0, 248, 0) and rgb555(0x7C00) == (0, 0, 248)


def test_face_to_quads_triangle_repeats_point():
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
    m = Mesh(0, verts, [(0.0, 1.0, 0.0)], [Face(0x001F, 0, 1, (0, 1, 2, 3)), Face(0x03E0, 0, 1, (0, 1, 2, 2))])
    p = Placement(0, 0, 10.0, 0.5, -20.0, 0, 0x1000, 11.314, ())
    qs = face_quads(m, p)
    assert len(qs) == 2
    from vrtools.convert.geometry import tile_to_arcade
    assert qs[0].p[0] == pytest.approx(tile_to_arcade(10.0, 0.5, -20.0)) and qs[0].rgb == (248, 0, 0)   # tiles use the tile frame
    assert qs[1].p[2] == qs[1].p[3] and qs[1].rgb == (0, 248, 0)


def test_placement_yaw_rotates_mesh():
    m = Mesh(0, [(1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [], [Face(0, 0, 1, (0, 1, 2, 3))])
    p = Placement(0, 0, 0.0, 0.0, 0.0, 0x40000000, 0, 1.0, ())      # 90 degrees about Y
    x, y, z = face_quads(m, p)[0].p[0]
    assert abs(x) < 1e-6 and abs(abs(z) - SCALE) < 1e-6


def test_bin_quads_every_quad_once_and_outside_reported():
    grid = CellGrid(x0=0.0, z0=0.0, cw=10.0, ch=10.0)
    inside = WorldQuad(((1, 0, 1), (2, 0, 1), (2, 0, 2), (1, 0, 2)), (0, 0, 0))
    far = WorldQuad(((500, 0, 1), (501, 0, 1), (501, 0, 2), (500, 0, 2)), (0, 0, 0))
    cells, outside = bin_quads([inside, far, inside], grid)
    assert cells == {0: [inside, inside]} and outside == [far]
    assert grid.cell_of(15.0, 25.0) == 2 * 16 + 1


def test_assign_colours_monotone_tex():
    pal = Palette([0x8000, 0x801F, 0x83E0] + [0] * 1021)
    quads = [WorldQuad(((0, 0, 0),) * 4, (0, 240, 0)), WorldQuad(((1, 0, 0),) * 4, (240, 0, 0)), WorldQuad(((2, 0, 0),) * 4, (0, 240, 0))]
    out, words = assign_colours(quads, pal, tex_start=0x50000)
    assert [q.tex_adr for q in out] == [0x50000, 0x50001, 0x50001]           # sorted by palette index: red (0x1001) then the two greens (0x1002)
    assert words == {0x50000: 0x0001, 0x50001: 0x0002}
    assert out[0].p[0] == (1, 0, 0)


def test_real_big_forest_conversion(saturn_cue, romset_zip):
    from vrtools.convert.geometry import cell_grid_from_arcade
    from vrtools.arcade.romset import RomSet
    from vrtools.saturn.iso import Iso2352
    from vrtools.saturn.trck import TrckFile
    from vrtools.saturn.course import decode_course
    iso = Iso2352(saturn_cue.with_name("Virtua Racing (Europe) (Track 01).bin"))
    sat = decode_course(TrckFile.from_bytes(iso.read("VRSRCDIR/TRACKS00/BIGFORES/TRCKBIGF")))
    qs = course_quads(sat)
    assert len(qs) >= 5000                      # Saturn Big Forest: ~6,100 faces over the four tile layers + props
    grid = cell_grid_from_arcade(RomSet.from_zip(romset_zip), 0)
    cells, outside = bin_quads(qs, grid)
    assert len(cells) >= 30 and len(outside) < 0.05 * len(qs)


# --- Phase 6: the tile frame -------------------------------------------------------------------------------------

def _saturn_course(cue, name):
    from pathlib import Path
    from vrtools.saturn.course import decode_course
    from vrtools.saturn.iso import Iso2352
    from vrtools.saturn.trck import TrckFile
    iso = Iso2352(Path(cue).with_name("Virtua Racing (Europe) (Track 01).bin"))
    return decode_course(TrckFile.from_bytes(iso.read(f"VRSRCDIR/TRACKS00/{name}")))


@pytest.mark.parametrize("course,name", [(0, "BIGFORES/TRCKBIGF"), (1, "BAYBRIDG/TRCKBAYB"), (2, "ACROPOLS/TRCKACRO")])
def test_saturn_tiles_land_on_the_arcade_tiles(romset_zip, saturn_cue, course, name):
    from vrtools.arcade.course import tile_table
    from vrtools.arcade.polyrom import decode_object, quads
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import tile_occupancy
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, name)
    arcade = set()
    for t in tile_table(rs, course):
        if t.size:
            arcade |= tile_occupancy(quads(decode_object(rs.polygons, t.poly_adr, t.size), t.tex_adr))
    saturn = tile_occupancy(course_quads(sat))
    assert len(arcade & saturn) / len(arcade | saturn) > 0.75


def test_saturn_ground_covers_the_road(saturn_cue):
    from vrtools.convert.collision import mesh_height
    from vrtools.convert.geometry import ConvertError, to_arcade
    sat = _saturn_course(saturn_cue, "ALPINE00/TRCKALPN")
    h = mesh_height(course_quads(sat, groups=(0,)))
    centres = [to_arcade(s.centre[0], 0, s.centre[1]) for s in sat.segments if s.centre is not None]
    covered = 0
    for x, _, z in centres:
        try:
            h(x, z)
            covered += 1
        except ConvertError:
            pass
    assert covered / len(centres) > 0.9


# --- Phase 6: the tile-cell rule and Alpine's scenery --------------------------------------------------------------

LOGGED_CELLS = [(-230.4, -269.6, 86), (-230.4, -254.8, 86), (-230.4, -236.9, 102), (-230.4, -181.8, 102), (-229.6, -103.2, 118),
                (-225.6, -8.6, 118), (-208.7, 25.7, 134), (-184.3, 108.0, 134), (-189.5, 144.9, 150), (-201.3, 233.4, 150),
                (-204.6, 274.4, 166), (-204.6, 397.2, 166), (-187.0, 228.3, 150), (-187.0, 283.1, 166), (-186.9, 416.3, 182),
                (-186.8, 510.8, 182), (-182.0, 558.0, 198), (-149.4, 582.2, 198)]     # (car x, z, game's own cell) from a logged race


def test_tile_grid_matches_the_logged_cells():
    from vrtools.convert.geometry import TILE_GRID
    ok = sum(1 for x, z, cell in LOGGED_CELLS if TILE_GRID.cell_of(x, z) == cell)
    assert ok / len(LOGGED_CELLS) > 0.85, ok      # the list is evaluated ~12 units behind the car (the camera): two
                                                  # samples just past a boundary still report the previous cell


def test_tile_grid_matches_the_arcade_tile_table(romset_zip):
    from vrtools.arcade.course import tile_table
    from vrtools.arcade.polyrom import decode_object, quads
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import TILE_GRID
    rs = RomSet.from_zip(romset_zip)
    for course in (0, 1, 2):
        for t in tile_table(rs, course):
            if t.size:
                pts = [p for q in quads(decode_object(rs.polygons, t.poly_adr, t.size), t.tex_adr) for p in q.p]
                cx, cz = sum(p[0] for p in pts) / len(pts), sum(p[2] for p in pts) / len(pts)
                assert TILE_GRID.cell_of(cx, cz) == t.cell


def test_convert_tiles_reports_outside_and_rejects_off_map(saturn_cue, romset_zip):
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import ConvertError, convert_tiles
    rs = RomSet.from_zip(romset_zip)
    objs, words, report = convert_tiles(_saturn_course(saturn_cue, "ALPINE00/TRCKALPN"), rs, 0, groups=(0, 4))   # unplaced: the terrain
    assert report["outside"] == 0 and 20 <= len(objs) <= 256 and report["quads"] > 1000
    assert all(len(objs[c][0]) % 4 == 0 for c in objs) and len(words) == report["colour_entries"]
    with pytest.raises(ConvertError, match="map"):
        convert_tiles(_saturn_course(saturn_cue, "DIABLO00/TRCKDIAB"), rs, 0, groups=(0, 4))   # layer leaves the map


def test_thinning_drops_small_far_quads_only(saturn_cue, romset_zip):
    """Scenery thinning for the render rate: a quad goes only when it is small (XZ area < thin) AND far from every
    keep point (the lap centreline), so the road's surroundings stay intact."""
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.geometry import convert_tiles
    from vrtools.convert.geometry import placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import choose_placement, grid_pose
    from tests.test_convert_collision import _saturn_course
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "DIABLO00/TRCKDIAB")
    pl = choose_placement(sat, grid_pose(rs, 0))
    with placed(pl.angle, pl.tx, pl.tz):                                                      # as the converter places it
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction)
        cl = centreline(lap)
        full = convert_tiles(sat, rs, 0)[2]
        thinned = convert_tiles(sat, rs, 0, thin=400.0, keep_near=cl)[2]
        everywhere = [(x, z) for x in range(-1000, 1001, 20) for z in range(-1000, 1001, 20)]
        none = convert_tiles(sat, rs, 0, thin=400.0, keep_near=everywhere)[2]
    assert 0 < thinned["thinned"] < 0.5 * full["quads"] and thinned["quads"] == full["quads"] - thinned["thinned"]
    assert thinned["polygon_bytes"] < full["polygon_bytes"]
    assert none["thinned"] == 0                                                               # everything is near a keep point


def _wq(cx, cz, y=0.0, size=1.0):
    h = size / 2
    return WorldQuad(((cx - h, y, cz - h), (cx + h, y, cz - h), (cx + h, y, cz + h), (cx - h, y, cz + h)), (0, 128, 0))


def test_far_small_terrain_is_thinned_and_the_rest_kept():
    """Pascal's call (Phase 18): keep all the road paint and structures, thin only small terrain far from the road."""
    from vrtools.convert.geometry import scenery_quads
    by_group = {1: [_wq(100, 0), _wq(30, 0)], 2: [_wq(100, 5)], 3: [_wq(100, -5)]}
    kept, report = scenery_quads(by_group, [(0.0, 0.0)], terrain_thin=2.0)
    assert len(kept) == 3 and report["terrain_thinned"] == 1
    assert by_group[1][0] not in kept and by_group[1][1] in kept


def test_convert_tiles_draws_every_layer(saturn_cue, romset_zip):
    """Phase 18: the converter draws all five Saturn tile groups (groups 0-3 are layers, not variants). Phase 26 stage 2:
    the props come with the gates' mirrored lettering (`gates.lettered_quads`)."""
    from vrtools.arcade.romset import RomSet
    from vrtools.convert.gates import lettered_quads
    from vrtools.convert.geometry import convert_tiles, placed
    from vrtools.convert.place import choose_placement, grid_pose
    rs = RomSet.from_zip(romset_zip)
    sat = _saturn_course(saturn_cue, "PACCOAST/TRCKPACC")
    pl = choose_placement(sat, grid_pose(rs, 1), grid_point=0)
    with placed(pl.angle, pl.tx, pl.tz):
        report = convert_tiles(sat, rs, 1)[2]
        assert report["quads"] == sum(len(course_quads(sat, (g,))) for g in range(4)) + len(lettered_quads(sat))
        assert len(lettered_quads(sat)) > len(course_quads(sat, (4,)))


def test_a_triangle_faces_the_same_way_wherever_its_repeated_corner_sits():
    """Phase 24: the Saturn stores a triangle as a quad with one corner repeated; its lighting normal must not depend
    on which corner that is (a repeat among the first three corners used to fall back to straight up, the opposite
    of every other ground face, and the arcade lit those road triangles as if they faced away: black wedges)."""
    from vrtools.convert.geometry import _normal
    a, b, c, d = (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 1.0, 10.0), (0.0, 1.0, 10.0)
    quad = _normal((a, b, c, d))
    for tri in ((a, a, b, c), (a, b, b, c), (a, b, c, c), (a, b, c, a)):
        assert _normal(tri) == pytest.approx(quad, abs=1e-6)
    assert _normal((a, b, c, d))[1] * _normal((d, c, b, a))[1] < 0          # the winding still decides the side


@pytest.mark.parametrize("path", ["ALPINE00/TRCKALPN", "AMAZON00/TRCKAMAZ", "DIABLO00/TRCKDIAB", "METROPOL/TRCKMETR",
                                  "PACCOAST/TRCKPACC", "SPEEDWAY/TRCKSPEE", "SURFER00/TRCKSURF"])
def test_the_road_faces_one_way_on_every_course(saturn_cue, path):
    """Phase 24: the near-flat grey ground faces (the road) all take a lighting normal on the same side (measured
    before the fix: 15-45 % the other way, every one a triangle; after: at most 3 faces of a course)."""
    from vrtools.convert.geometry import _normal
    sat = _saturn_course(saturn_cue, path)
    up = down = 0
    for q in course_quads(sat, groups=(0,)):
        if not (q.rgb[0] == q.rgb[1] == q.rgb[2] and 40 <= q.rgb[0] <= 128):
            continue
        ny = _normal(q.p)[1]
        if abs(ny) >= 0.9:
            up, down = up + (ny > 0), down + (ny < 0)
    assert down > 300 and up <= 0.01 * down


def test_the_roads_greys_take_the_arcades_levels():
    """Phase 24 (Pascal: align the converted courses' road colour with the arcade's): the Saturn paints its road lighter
    than the arcade and with larger steps between tiles (Big Forest: greys 64-104, mean 87, against the arcade's 56-88,
    mean 77), and the arcade lights its palette on top: converted roads stood at 107-140 on screen against the
    originals' 74-107. The ground layer's neutral greys go down ROAD_GREYS; colours, other greys and other layers stay."""
    from vrtools.convert.geometry import ROAD_GREYS, road_greys
    p = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 0.0, 1.0))
    quads = [WorldQuad(p, (104, 104, 104)), WorldQuad(p, (64, 64, 64)), WorldQuad(p, (88, 104, 120)),
             WorldQuad(p, (208, 208, 208)), WorldQuad(p, (248, 248, 248))]
    assert [q.rgb for q in road_greys(quads)] == [(88, 88, 88), (56, 56, 56), (88, 104, 120), (208, 208, 208), (248, 248, 248)]
    assert all(q.p == p for q in road_greys(quads))
    assert all(v <= k and k - v <= 24 for k, v in ROAD_GREYS.items())           # darker, never by much
    vals = [ROAD_GREYS[k] for k in sorted(ROAD_GREYS)]
    assert vals == sorted(vals)                                                 # the order of the shades is kept


def test_big_forests_saturn_road_lands_on_the_arcades_mean(saturn_cue):
    """Phase 24: the shared course is the measure — the Saturn Big Forest's road greys, mapped, average the arcade Big
    Forest's road (77 in the palette, measured at the same spots; unmapped 87)."""
    from vrtools.convert.geometry import road_greys
    sat = _saturn_course(saturn_cue, "BIGFORES/TRCKBIGF")
    road = [q for q in course_quads(sat, groups=(0,)) if q.rgb[0] == q.rgb[1] == q.rgb[2] and 40 <= q.rgb[0] <= 128]
    mean = lambda qs: sum(q.rgb[0] for q in qs) / len(qs)
    assert 84 <= mean(road) <= 92 and 74 <= mean(road_greys(road)) <= 80, (mean(road), mean(road_greys(road)))


def test_convert_tiles_maps_the_ground_layers_greys_only(saturn_cue, romset_zip):
    """Phase 24: the converter draws the ground layer (group 0) with the mapped greys; the buildings' and props' greys
    (groups 3, 4) are the Saturn's."""
    from vrtools.convert import geometry
    seen = {}
    real = geometry.scenery_quads
    def spy(by_group, *a, **k):
        seen.update({g: [q.rgb for q in qs] for g, qs in by_group.items()}); return real(by_group, *a, **k)
    geometry.scenery_quads = spy
    try:
        from vrtools.arcade.romset import RomSet
        from vrtools.convert.geometry import convert_tiles, placed
        from vrtools.convert.place import choose_placement, grid_pose
        rs = RomSet.from_zip(romset_zip)
        sat = _saturn_course(saturn_cue, "PACCOAST/TRCKPACC")
        pl = choose_placement(sat, grid_pose(rs, 1), grid_point=0)
        with placed(pl.angle, pl.tx, pl.tz):
            convert_tiles(sat, rs, 1)
    finally:
        geometry.scenery_quads = real
    assert (104, 104, 104) not in seen[0] and (88, 88, 88) in seen[0]
    assert seen[3] == [q.rgb for q in course_quads(sat, groups=(3,))]
