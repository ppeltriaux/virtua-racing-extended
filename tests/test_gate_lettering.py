"""Phase 26 stage 2 (Pascal's reverse drive: "START" read "TRATS" from behind; option C): a gate's lettering is drawn
one-sided, facing the side it reads from, and a copy mirrored across the banner faces the other side. Synthetic gate
meshes only (made-up coordinates in the Saturn's gate layout: banner along x, lettering on its -z side)."""
from types import SimpleNamespace

import pytest

from vrtools.arcade.colours import Palette
from vrtools.arcade.polyrom import decode_object, encode_object, quads as decoded_quads
from vrtools.convert.gates import GATE_GROUP, gate_lettering, lettered_quads
from vrtools.convert.geometry import ConvertError, WorldQuad, _normal, assign_colours, course_quads, face_quads
from vrtools.saturn.course import Face, Mesh, Placement

RED, WHITE, CREAM, BROWN = 0x001F, 0x7FFF, 0x6B9D, 0x1DB2

# banner panels as (x, z) ends, 0.30..0.62 high: a left wing, a centre panel and a longer right wing, bent like the Saturn's
PANELS = [((-0.9, -0.10), (-0.5, -0.20)), ((-0.5, -0.20), (0.5, -0.15)), ((0.5, -0.15), (1.1, -0.05))]
Y0, Y1 = 0.30, 0.62
DEPTH = 0.02                                   # the lettering stands this far in front (-z) of the banner


def _zb(x):
    for (xa, za), (xb, zb) in PANELS:
        if xa <= x <= xb:
            return za + (zb - za) * (x - xa) / (xb - xa)
    raise AssertionError(x)


# lettering rectangles (x0, x1, y0, y1, colour, depth in front of the banner), placed asymmetrically: one on the left
# wing, two on the centre panel, a white cut-out on the second, one flush with the right wing (as two faces of the wider
# START gates lie)
LETTERS = [(-0.80, -0.62, 0.36, 0.56, RED, DEPTH), (-0.30, -0.10, 0.36, 0.56, RED, DEPTH), (0.10, 0.40, 0.36, 0.56, RED, DEPTH),
           (0.20, 0.30, 0.42, 0.50, WHITE, DEPTH), (0.70, 0.85, 0.36, 0.56, RED, 0.0)]


def gate_mesh(vertex_count=68):
    verts, faces = [], []

    def quad(pts, colour, both=False):
        base = len(verts)
        verts.extend(pts)
        ids = (base + 3, base + 2, base + 1, base)              # the Saturn's order: right-bottom, right-top, left-top, left-bottom
        faces.append(Face(colour, len(faces), 1, ids))
        if both:
            faces.append(Face(colour, len(faces), 1, tuple(reversed(ids))))

    for (xa, za), (xb, zb) in PANELS:                           # each banner panel twice, once per side (as the Saturn has it)
        quad([(xa, Y0, za), (xa, Y1, za), (xb, Y1, zb), (xb, Y0, zb)], WHITE if xa == -0.5 else CREAM, both=True)
    for x0, x1, y0, y1, colour, depth in LETTERS:
        z0, z1 = _zb(x0) - depth, _zb(x1) - depth
        quad([(x0, y0, z0), (x0, y1, z0), (x1, y1, z1), (x1, y0, z1)], colour)
    for x in (-1.3, 1.4):                                       # posts: thin, beside the banner, one face each way
        quad([(x, 0.0, 0.0), (x, 0.7, 0.0), (x + 0.02, 0.7, 0.0), (x + 0.02, 0.0, 0.0)], BROWN)
        quad([(x, 0.0, -0.02), (x, 0.7, -0.02), (x, 0.7, 0.0), (x, 0.0, 0.0)], BROWN)
    while len(verts) < vertex_count:                            # the gate props are recognised by their vertex count
        verts.append((0.0, 0.0, 0.0))
    return Mesh(0, verts, [], faces)


N_BANNER = 2 * len(PANELS)
LETTER_FACES = tuple(range(N_BANNER, N_BANNER + len(LETTERS)))


def test_the_lettering_is_found_and_the_banner_and_posts_are_not():
    lt = gate_lettering(gate_mesh())
    assert lt is not None and lt.faces == LETTER_FACES


def test_the_copy_is_the_lettering_mirrored_across_the_banner():
    """Left-to-right about the banner's centre (x -> 2c - x: the text keeps its place on the banner), each corner as far
    behind the banner as the letter stands in front of it."""
    m = gate_mesh()
    lt = gate_lettering(m)
    c = (PANELS[0][0][0] + PANELS[-1][1][0]) / 2
    for f, copy, letter in zip(lt.faces, lt.mirrored, LETTERS):
        for (x, y, z), (mx, my, mz) in zip((m.vertices[i] for i in m.faces[f].vertex_ids), copy):
            assert mx == pytest.approx(2 * c - x) and my == pytest.approx(y)
            assert mz - _zb(mx) == pytest.approx(_zb(x) - z) and _zb(x) - z == pytest.approx(letter[5], abs=1e-9)


def test_no_lettering_when_its_faces_are_wound_both_ways():
    m = gate_mesh()
    f = m.faces[LETTER_FACES[1]]
    faces = list(m.faces)
    faces[LETTER_FACES[1]] = Face(f.colour, f.attr_a, f.attr_b, tuple(reversed(f.vertex_ids)))
    assert gate_lettering(Mesh(0, m.vertices, [], faces)) is None


def test_no_lettering_without_a_banner():
    m = gate_mesh()
    assert gate_lettering(Mesh(0, m.vertices, [], m.faces[N_BANNER:])) is None


def _sat(m, yaw=0x12345678):
    return SimpleNamespace(meshes={GATE_GROUP: [m]}, placements={GATE_GROUP: [Placement(0, 0, 3.0, 0.5, -2.0, yaw, 0, 2.0, ())]})


def test_letters_come_out_one_sided_with_a_one_sided_mirrored_copy():
    m = gate_mesh()
    sat = _sat(m)
    plain = course_quads(sat, groups=(GATE_GROUP,))
    out = lettered_quads(sat)
    n = len(m.faces)
    assert len(out) == n + len(LETTERS)
    for i, (a, b) in enumerate(zip(plain, out)):                 # every face where it was, the lettering marked one-sided
        assert a.p == b.p and a.rgb == b.rgb and b.one_sided == (i in LETTER_FACES)
    copies = out[n:]
    assert all(q.one_sided for q in copies) and [q.rgb for q in copies] == [plain[f].rgb for f in LETTER_FACES]
    placed = face_quads(Mesh(0, [p for c in gate_lettering(m).mirrored for p in c], [],
                             [Face(m.faces[f].colour, 0, 1, (4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3)) for k, f in enumerate(LETTER_FACES)]),
                        sat.placements[GATE_GROUP][0])
    assert [q.p for q in copies] == [q.p for q in placed]       # the copy placed like the prop


def test_the_copy_faces_the_other_way():
    """The copy is the letter turned half round a vertical axis on the banner: its lighting normal (the winding's, as every
    converted face has it) is the letter's turned the same way, so it faces the other side."""
    out = lettered_quads(_sat(gate_mesh(), yaw=0))
    n = len(gate_mesh().faces)
    for f, copy in zip(LETTER_FACES, out[n:]):
        a, b = _normal(out[f].p), _normal(copy.p)
        assert a[2] * b[2] < 0 and abs(a[1]) < 1e-6 and abs(b[1]) < 1e-6


def test_other_props_and_non_gate_meshes_are_unchanged():
    m = gate_mesh(vertex_count=70)                              # not a gate's vertex count
    sat = _sat(m)
    assert lettered_quads(sat) == course_quads(sat, groups=(GATE_GROUP,))


@pytest.mark.parametrize("vertex_count", [68, 96])
def test_a_gate_whose_lettering_is_not_recognised_fails_loudly(vertex_count):
    """A drawn gate (a 68- or 96-vertex prop) without recognisable lettering would still read mirrored from behind: the
    conversion stops and names the placement, rather than leave it two-sided."""
    m = gate_mesh(vertex_count)
    faces = list(m.faces)
    f = faces[LETTER_FACES[1]]
    faces[LETTER_FACES[1]] = Face(f.colour, f.attr_a, f.attr_b, tuple(reversed(f.vertex_ids)))   # wound both ways: not lettering
    sat = _sat(Mesh(0, m.vertices, [], faces))
    with pytest.raises(ConvertError, match=f"gate placement 0 \\(mesh 0, {vertex_count} vertices, at Saturn x 3.00 z -2.00\\)"):
        lettered_quads(sat)


def test_the_collisions_props_never_hold_the_copies():
    """collision.py takes the props as `course_quads(sat, groups=(4,))` (its walls at drawn objects, PROP_MIN_LATERAL); the
    lettering step builds its copies beside that list: the props the collision reads keep their length and hold no
    one-sided quad, before and after it, and the Saturn course is not changed."""
    sat = _sat(gate_mesh())
    props = course_quads(sat, groups=(GATE_GROUP,))
    placements, meshes = repr(sat.placements), repr(sat.meshes)
    out = lettered_quads(sat)
    after = course_quads(sat, groups=(GATE_GROUP,))
    assert len(out) == len(props) + len(LETTERS) and any(q.one_sided for q in out)
    assert after == props and len(after) == len(gate_mesh().faces) and not any(q.one_sided for q in after)
    assert (repr(sat.placements), repr(sat.meshes)) == (placements, meshes)


def test_the_collisions_code_never_takes_the_lettering_copies():
    """A source-level guard, kept because the collision is the owner's most protected area (never a wall disabled at drawn
    rocks or scenery, never one moved nearer the road): the modules that build the collision, its profile and its props'
    placement never name the step that makes the lettering copies, so the copies can reach the scenery only."""
    from pathlib import Path

    import vrtools.convert as convert

    root = Path(convert.__file__).parent
    for module in ("collision.py", "profile.py", "place.py"):
        text = (root / module).read_text()
        for name in ("lettered_quads", "convert_tiles"):
            assert name not in text, (module, name)


def test_a_one_sided_face_is_encoded_reversed_and_keeps_its_lighting_normal():
    """The arcade draws a culled record from the side its first three drawn corners' right-hand normal faces (the
    originals' culled ground: up), the opposite of the Saturn's winding (whose right-hand normal is the converter's
    lighting normal: the road's points down). A one-sided face is therefore written with its corners reversed, under
    the lighting normal it had."""
    pal = Palette([0x8000, 0x801F] + [0] * 1022)
    p = ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    (two,), _ = assign_colours([WorldQuad(p, (240, 0, 0))], pal, tex_start=0x50000)
    (one,), _ = assign_colours([WorldQuad(p, (240, 0, 0), one_sided=True)], pal, tex_start=0x50000)
    assert not two.one_sided and two.p == p
    assert one.one_sided and one.normal == two.normal == _normal(p)
    assert one.p == (p[0], p[3], p[2], p[1])


def test_a_gate_encodes_its_lettering_one_sided_and_the_rest_two_sided():
    pal = Palette([0x8000, 0x801F, 0xFFFF, 0x8C63] + [0] * 1020)
    out = lettered_quads(_sat(gate_mesh()))
    coloured, _ = assign_colours(out, pal, tex_start=0x50000)
    blob, _ = encode_object(coloured, tex_start=0x50000, no_cull=True)
    drawn = decoded_quads(decode_object(blob, 0, 0))
    one = [q for q in drawn if not q.flags & 0x4000]
    assert len(one) == 2 * len(LETTERS) and len(drawn) == len(out)


@pytest.mark.parametrize("k", range(7))
def test_only_the_gates_cells_change_and_convert_tiles_leaves_the_course_alone(saturn_cue, romset_zip, k):
    """On each converted course, placed as the conversion places it: the scenery with the lettering two-sided against
    one-sided with its copies differs only in the cells that hold a gate's lettering (the copies take the letters' own
    colours: every other cell keeps its colour entries and bytes), no cell is newly capped, each drawn gate adds one copy
    per lettering face (START 14, C.P. 7), and `convert_tiles` leaves `sat` and `course_quads(sat)` as they were (what
    the collision is built from; the byte-identical collision itself was measured once, out/p26/stage2/gates/proof.txt)."""
    import hashlib, pickle
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.tencourse import COURSES, HOST_OF_BANK, load_saturn_course
    from vrtools.convert.gates import hide_unused_gates
    from vrtools.convert.geometry import TILE_GRID, convert_tiles, placed
    from vrtools.convert.lap import centreline, order_slices
    from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
    plan = COURSES[k]
    rs = RomSet.from_zip(romset_zip)
    sat = load_saturn_course(saturn_cue, plan.path)
    gc = COURSE_OF_TEMPLATE[plan.template]
    pl = choose_placement(sat, grid_pose(rs, gc), grid_point=GRID_OF_COURSE[gc][0], min_coverage=plan.min_coverage,
                          flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        cl = centreline(order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=plan.min_coverage))
        sat = hide_unused_gates(sat, cl)
        before = hashlib.sha256(pickle.dumps((sat.placements, sat.meshes, course_quads(sat)))).hexdigest()
        kw = dict(thin=plan.thin, keep_near=cl, terrain_thin=plan.terrain_thin, outside_limit=50)
        old, old_words, old_rep = convert_tiles(sat, rs, HOST_OF_BANK[plan.bank], lettering=False, **kw)
        new, new_words, new_rep = convert_tiles(sat, rs, HOST_OF_BANK[plan.bank], **kw)
        letter_cells = {TILE_GRID.cell_of(sum(p[0] for p in q.p) / 4, sum(p[2] for p in q.p) / 4)
                        for q in lettered_quads(sat) if q.one_sided}
        assert hashlib.sha256(pickle.dumps((sat.placements, sat.meshes, course_quads(sat)))).hexdigest() == before
        sizes = [len(sat.meshes[GATE_GROUP][p.mesh].vertices) for p in sat.placements[GATE_GROUP]]
    gates = {96: sizes.count(96), 68: sizes.count(68)}
    assert gates == {96: 1, 68: 1 if plan.name == "PACIFIC COAST" else 2}, (plan.name, gates)     # the drawn gates
    assert new_rep["lettering_copies"] == 14 * gates[96] + 7 * gates[68]
    changed = {c for c in old.keys() | new.keys() if old.get(c, (None,))[0] != new.get(c, (None,))[0]}
    assert old.keys() == new.keys() and changed == letter_cells and len(letter_cells) >= 1, (plan.name, changed, letter_cells)
    assert old_words == new_words and new_rep["capped_cells"] == old_rep["capped_cells"]
    assert old_rep["lettering_copies"] == 0 and new_rep["quads"] - old_rep["quads"] == new_rep["lettering_copies"]
    assert all(new[c][2] == old[c][2] for c in old)                  # every cell's colour entries where they were
