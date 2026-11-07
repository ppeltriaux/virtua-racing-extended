"""Phase 22e: the Saturn course's own gates (its START/GOAL and its two C.P.), the converted lap's checkpoints.

Every Saturn course draws three gates as group-4 props spanning the road (recon in docs/follow-ups.md): a START/GOAL
gate (96 vertices, 12.9 units tall) and two C.P. gates (68 vertices, 10.6-10.9 tall). The arcade's start line sits
where its absolute grid fits (not at the Saturn's start), so all three are checkpoints after it (Pascal's choice A)
and the host's checkpoint gantries are left out of the spawn list."""

from __future__ import annotations

import math

from vrtools.convert.geometry import face_quads
from vrtools.saturn.course import SaturnCourse

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
    from dataclasses import replace
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
