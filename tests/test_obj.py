from vrtools.arcade.polyrom import Quad
from vrtools.geom.obj import write_obj

N = (0.0, 1.0, 0.0)


def q(*pts, tex=0):
    return Quad(tuple(pts), N, 0x201, tex)


def test_groups_vertices_faces_and_running_indices(tmp_path):
    road = [q((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1), tex=7)]
    tree = [q((5, 0, 0), (6, 0, 0), (6, 1, 0), (5, 1, 0), tex=9)]
    p = tmp_path / "a.obj"
    write_obj(p, {"road": road, "tree": tree})
    lines = p.read_text().splitlines()
    assert "g road" in lines and "g tree" in lines
    assert sum(l.startswith("v ") for l in lines) == 8
    faces = [l for l in lines if l.startswith("f ")]
    assert faces == ["f 1 2 3 4", "f 5 6 7 8"]
    assert "# tex 7" in lines and lines.index("# tex 7") < lines.index("f 1 2 3 4")


def test_vertices_deduplicated_within_group(tmp_path):
    quads = [q((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)), q((0, 0, 1), (1, 0, 1), (1, 0, 2), (0, 0, 2))]
    p = tmp_path / "b.obj"
    write_obj(p, {"road": quads})
    lines = p.read_text().splitlines()
    assert sum(l.startswith("v ") for l in lines) == 6
    assert [l for l in lines if l.startswith("f ")] == ["f 1 2 3 4", "f 4 3 5 6"]


def test_degenerate_quad_written_as_triangle(tmp_path):
    p = tmp_path / "c.obj"
    write_obj(p, {"pt": [q((0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 0, 0))]})
    lines = p.read_text().splitlines()
    assert [l for l in lines if l.startswith("f ")] == ["f 1 2 3"]


def test_scale_and_transform(tmp_path):
    p = tmp_path / "d.obj"
    write_obj(p, {"g": [q((1, 2, 3), (1, 2, 3), (1, 2, 3), (1, 2, 3))]}, scale=2.0,
              transform=lambda v: (v[0], v[2], -v[1]))
    assert "v 2 6 -4" in p.read_text().splitlines()
