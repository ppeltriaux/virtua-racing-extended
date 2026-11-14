"""Phase 22e: the Saturn course's own gates (its START/GOAL and its two C.P.), the converted lap's checkpoints.

Every Saturn course draws three gates as group-4 props spanning the road (recon in docs/follow-ups.md): a START/GOAL
gate (96 vertices, 12.9 units tall) and two C.P. gates (68 vertices, 10.6-10.9 tall). The arcade's start line sits
where its absolute grid fits (not at the Saturn's start), so all three are checkpoints after it (Pascal's choice A)
and the host's checkpoint gantries are left out of the spawn list."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from vrtools.convert.geometry import ConvertError, _normal, face_quads
from vrtools.saturn.course import Face, Mesh, SaturnCourse

GATE_GROUP = 4
GATE_VERTICES = (68, 96)
GATE_SPAN = 20.0          # a gate spans at least this across the road (Amazon's first C.P.: -7.6..18.9, 5 units off centre)
GATE_NEAR = 12.0          # and its centre lies within this of a centreline point


def saturn_gates(sat: SaturnCourse, centreline: list[tuple[float, float]]) -> list[int]:
    """The road points (indices into `centreline`, arcade coordinates: call inside the course's placement) of the
    Saturn's gates, sorted."""
    n = len(centreline)
    meshes, out = sat.meshes[GATE_GROUP], []
    for p in sat.placements[GATE_GROUP]:
        if not (0 <= p.mesh < len(meshes)) or len(meshes[p.mesh].vertices) not in GATE_VERTICES:
            continue
        pts = [q for f in face_quads(meshes[p.mesh], p) for q in f.p]
        if not pts:
            continue
        cx = sum(q[0] for q in pts) / len(pts); cz = sum(q[2] for q in pts) / len(pts)
        k = min(range(n), key=lambda i: math.dist(centreline[i], (cx, cz)))
        if math.dist(centreline[k], (cx, cz)) > GATE_NEAR:
            continue
        (ax, az), (bx, bz) = centreline[k - 1], centreline[(k + 1) % n]
        d = math.hypot(bx - ax, bz - az) or 1.0
        lats = [((qx - centreline[k][0]) * (bz - az) - (qz - centreline[k][1]) * (bx - ax)) / d for qx, _, qz in pts]
        if min(lats) < 0 < max(lats) and max(lats) - min(lats) >= GATE_SPAN:
            out.append(k)
    return sorted(out)


def start_gate_point(sat: SaturnCourse, centreline: list[tuple[float, float]]) -> int | None:
    """Phase 22l: the road point nearest the Saturn's START/GOAL gate (the 96-vertex prop), or None without one.
    Arcade coordinates: call inside the course's placement (or on the identity lap for the placement search)."""
    n = len(centreline)
    meshes = sat.meshes[GATE_GROUP]
    for p in sat.placements[GATE_GROUP]:
        if not (0 <= p.mesh < len(meshes)) or len(meshes[p.mesh].vertices) != 96:
            continue
        pts = [q for f in face_quads(meshes[p.mesh], p) for q in f.p]
        if pts:
            cx = sum(q[0] for q in pts) / len(pts); cz = sum(q[2] for q in pts) / len(pts)
            return min(range(n), key=lambda i: math.dist(centreline[i], (cx, cz)))
    return None


def hide_unused_gates(sat: SaturnCourse, centreline: list[tuple[float, float]]) -> SaturnCourse:
    """Phase 22t (Pascal, 8 Nov: a checkpoint flag on Pacific Coast "with no real checkpoint under it"): `sat` without the
    C.P. gates (68-vertex props) that are not checkpoints on the converted lap (`race.gate_checkpoints` drops a gate just
    after our start line: Phase 22i), so a drawn C.P. always fires; START/GOAL gates stay (one stands at our line). The
    props reach the scenery and the collision through `geometry.course_quads` only, so both lose it. Arcade coordinates:
    call inside the course's placement."""
    from vrtools.convert.race import gate_checkpoints
    n = len(centreline)
    cps = set(gate_checkpoints(saturn_gates(sat, centreline), n))
    meshes, kept = sat.meshes[GATE_GROUP], []
    for p in sat.placements[GATE_GROUP]:
        if 0 <= p.mesh < len(meshes) and len(meshes[p.mesh].vertices) == 68:
            pts = [q for f in face_quads(meshes[p.mesh], p) for q in f.p]
            if pts:
                cx = sum(q[0] for q in pts) / len(pts); cz = sum(q[2] for q in pts) / len(pts)
                k = min(range(n), key=lambda i: math.dist(centreline[i], (cx, cz)))
                if math.dist(centreline[k], (cx, cz)) <= GATE_NEAR and k not in cps:
                    continue
        kept.append(p)
    return replace(sat, placements={**sat.placements, GATE_GROUP: kept})


# --- Phase 26 stage 2: the lettering reads from both sides ------------------------------------------------------------
# Pascal's reverse drive (12 Nov): the gates seen from behind read "TRATS" and "P.C". Every converted face is drawn from both
# sides, and a gate's lettering is a set of faces of its own (red letters, white cut-outs) standing up to 0.045 Saturn units
# in front of a banner the Saturn stores twice (once per side); the Saturn draws the lettering from the front only. Option C
# (Pascal): the lettering one-sided, facing the side it reads from (the Saturn's), and a copy mirrored across the banner facing
# the other side.

BANNER_MIN_HEIGHT = 0.15   # Saturn units: a banner panel is at least this tall (the gates' 0.28-0.33; the ropes 0.01-0.03)
LETTER_DEPTH = 0.06        # a lettering face lies this near the banner (measured -0.002..0.045 on every gate of the seven courses)
_EPS = 0.01                # the lettering lies inside the banner's span within this


@dataclass(frozen=True)
class Lettering:
    """A gate mesh's lettering: the faces (indices into `mesh.faces`) and, for each, its copy's corners (mesh-local, the
    face's own corner order): mirrored left to right about the banner's centre `centre` (x -> 2 centre - x) and as far
    behind the banner as the face stands in front of it, so the text keeps its place on the banner and reads from behind."""
    faces: tuple[int, ...]
    mirrored: tuple[tuple[tuple[float, float, float], ...], ...]
    centre: float


def mirror_behind(pts, centre: float, zb) -> tuple[tuple[float, float, float], ...]:
    """A lettering face's copy: each corner (x, y, z) mirrored left to right about the vertical plane x = `centre` and standing
    as far behind the banner's surface `zb(x, y)` as it stands in front of it, (2c − x, y, zb(2c − x, y) + (zb(x, y) − z)),
    each corner following the surface under it (a bent or waving banner). The corner order is kept: the mirror and the depth
    reflection together turn the face half round, so it reads, the right way round, from behind (Phase 26 stage 2: Task 9's
    Saturn gates, zb along x alone; Task 11's arcade start gantry, zb over the waving banner's strips)."""
    return tuple((2 * centre - x, y, zb(2 * centre - x, y) + (zb(x, y) - z)) for x, y, z in pts)


def _corners(m: Mesh, f) -> list[tuple[float, float, float]]:
    return [m.vertices[i] for i in f.vertex_ids]


def _face_key(m: Mesh, f) -> frozenset:
    """A face's corners as a set (rounded): equal for the two copies of a face the mesh stores once per side."""
    return frozenset((round(x, 4), round(y, 4), round(z, 4)) for x, y, z in _corners(m, f))


def _banner(m: Mesh) -> list[tuple[tuple[float, float], tuple[float, float], float, float]]:
    """The banner's panels: faces the mesh stores twice (the same corners, once per side), standing upright and at least
    BANNER_MIN_HEIGHT tall; each as its two (x, z) ends in x order and its y span."""
    seen: dict[frozenset, int] = {}
    for f in m.faces:
        k = _face_key(m, f)
        seen[k] = seen.get(k, 0) + 1
    out = []
    for k, count in seen.items():
        if count < 2:
            continue
        xz = sorted({(x, z) for x, _, z in k})
        ys = [y for _, y, _ in k]
        if len(xz) == 2 and max(ys) - min(ys) >= BANNER_MIN_HEIGHT and xz[1][0] - xz[0][0] > abs(xz[1][1] - xz[0][1]):
            out.append((xz[0], xz[1], min(ys), max(ys)))
    return sorted(out)


def _duplicated(m: Mesh) -> set[int]:
    keys = [_face_key(m, f) for f in m.faces]
    return {i for i, k in enumerate(keys) if keys.count(k) > 1}


def gate_lettering(m: Mesh) -> Lettering | None:
    """The lettering of a gate mesh (mesh-local, Saturn units): the faces stored once, upright, inside the banner's x and y
    span and within LETTER_DEPTH of it, all wound to face one way (the Saturn draws them from that side only), the side
    they stand on (0.008-0.045 in front on every gate; two faces of the wider START banner of Metropolis and the Surfers
    courses lie flush with it, -0.002..0.001); None without a banner or lettering, or with faces wound both ways. The banner
    runs along the mesh's x axis (the gates' posts stand at its ends); its surface is the panels' polyline."""
    panels = _banner(m)
    if not panels:
        return None
    x0, x1 = panels[0][0][0], panels[-1][1][0]
    y0, y1 = min(p[2] for p in panels), max(p[3] for p in panels)

    def zb(x: float) -> float:
        (xa, za), (xb, zb_), _, _ = min(panels, key=lambda p: 0.0 if p[0][0] <= x <= p[1][0] else min(abs(x - p[0][0]), abs(x - p[1][0])))
        return za + (zb_ - za) * (x - xa) / (xb - xa)

    dup = _duplicated(m)
    faces, facing, depth = [], set(), 0.0
    for i, f in enumerate(m.faces):
        if i in dup:
            continue
        pts = _corners(m, f)
        if any(not (x0 - _EPS <= x <= x1 + _EPS and y0 - _EPS <= y <= y1 + _EPS) for x, y, _ in pts):
            continue
        n = _normal(tuple(pts))
        if abs(n[1]) > 0.5:
            continue                                                   # lying flat: not on the banner
        w = [zb(x) - z for x, _, z in pts]
        if max(abs(v) for v in w) > LETTER_DEPTH:
            continue
        faces.append(i)
        facing.add(n[2] > 0)
        depth += sum(w)
    # one winding for all, and the lettering on the side it is drawn from: the winding's right-hand normal points away from
    # it (+z for lettering in front, at -z: the Saturn's own normals point -z)
    if not faces or len(facing) != 1 or (depth > 0) != facing.pop():
        return None
    c = (x0 + x1) / 2
    mirrored = tuple(mirror_behind(_corners(m, m.faces[i]), c, lambda x, _y: zb(x)) for i in faces)
    return Lettering(tuple(faces), mirrored, c)


def lettered_quads(sat: SaturnCourse) -> list:
    """The props (group 4) as `geometry.course_quads` gives them, except that a drawn gate's lettering (`gate_lettering`) is
    one-sided and followed, after the prop's faces, by its mirrored copy, one-sided too (WorldQuad.one_sided: drawn from
    the side the Saturn's winding shows it to; the copy, turned half round on the banner, from the other). Scenery only:
    the collision reads the Saturn course itself and never sees the copies. ConvertError when a gate placement (a 68- or
    96-vertex mesh) has no recognisable lettering: it would be drawn mirrored from behind again (every gate of the ten
    Saturn courses is recognised: 30 placements)."""
    meshes = sat.meshes.get(GATE_GROUP, [])
    out = []
    for n, p in enumerate(sat.placements.get(GATE_GROUP, [])):
        if p.mesh < 0 or p.mesh >= len(meshes):
            continue
        m = meshes[p.mesh]
        qs = face_quads(m, p)
        if len(m.vertices) not in GATE_VERTICES:
            out.extend(qs)
            continue
        lt = gate_lettering(m)
        if lt is None:
            raise ConvertError(f"gate placement {n} (mesh {p.mesh}, {len(m.vertices)} vertices, at Saturn x {p.x:.2f} z {p.z:.2f}): "
                               "its lettering is not recognised, so it cannot be made to read from both sides")
        letters = set(lt.faces)
        out.extend(replace(q, one_sided=True) if i in letters else q for i, q in enumerate(qs))
        copy = Mesh(m.index, [v for c in lt.mirrored for v in c], [],
                    [Face(m.faces[f].colour, 0, 1, tuple(range(4 * k, 4 * k + 4))) for k, f in enumerate(lt.faces)])
        out.extend(replace(q, one_sided=True) for q in face_quads(copy, p))
    return out
