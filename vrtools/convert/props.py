"""Phase 29: copies of an arcade prop baked into a converted course's scenery cells.

The arcade's own courses carry their trees inside the tile cells as world-space faces (the Phase 28 recon's §4.1: Big Forest's
trees are a 3- or 4-face canopy on a 3-face trunk). A prop is read from the user's own polygon ROM at build time (`prop_from_cell`:
the faces of one original cell that lie around a point, with their colour-table words' palette indices); nothing of its geometry
is stored in the repository. `baked` turns a copy about the vertical and moves it into world space as one-sided `WorldQuad`s that
`geometry.assign_colours` writes back with the original's drawn corners, lighting normal and palette index, culled, at the
original's z mode and light mode (measured on Big Forest's tree). Not record for record what the arcade stored: each copied face
is a chain of its own of type-1 records, with a repeated corner where four of the tree's seven source faces are triangle (type-2)
records, and without the source records' flag bits 23 and 24. What that changes on real hardware is unknown.
`plant` stands each copy on the drawn ground and refuses a site where it would float or sink, stand against the Saturn's own
upright scenery or come within PROP_CLEAR of any collision quad: a prop is drawn only (the collision never sees it), so a car must
never be able to reach one.

Phase 34 (Pascal, 16 Nov, after one 28-s run of the set `out/p34play3`: "those ones are great keep saturn"): a prop may also be cut out of the converted
course's own scenery (`CourseProp`, `prop_from_course`: Surfers Road's own roadside palm), its copies baked as the course's own
faces are: two-sided, the Saturn's colours. Nothing arcade is read for it. `plant` also refuses water, holds a small prop to the
tree's slope and keeps a wide prop's crown off the collision. (Bay Bridge's palm, at the arcade's size and scaled, was tried and
not kept: docs/spike/2026-11-phase34-surfers-palms-findings.md; that code is in the branch's history, not here.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, NamedTuple, Sequence

from vrtools.convert.geometry import ConvertError, WorldQuad

Point = tuple[float, float, float]

PROP_CLEAR = 10.0       # XZ units from every collision quad (the road, verges, run-off and pit lane, whose edges are the walls) to a
                        # prop's FOOT, not its canopy: Big Forest's tree reaches 5.116 from its foot, so its canopy can come within
                        # about 4.9 units of a collision quad's edge (a car's half width beyond the last quad a car can stand on)
SCENERY_CLEAR = 1.5     # XZ units between a prop's reach and the nearest face of the Saturn's upright scenery (rocks, pines, buildings)
PROP_FLAT = 4.5         # the drawn ground under a prop's reach (its centre and a ring at its radius) may rise or fall this much at most:
                        # about a 25-degree slope across a Big Forest tree's 9.8-unit spread (more: a steep slope or a rock face). The foot
                        # stands at the lowest ground within FOOT_RING, so on that slope the canopy's uphill edge meets the snow
CROWN_CLEAR = 2.0       # Phase 34 (binds no prop of today's plans; kept so that a prop reaching more than 8 can never hang over the road): XZ units between a prop's reach (its crown's edge) and every collision quad, for a prop wider than
                        # PROP_CLEAR - CROWN_CLEAR (neither Big Forest's tree, reach 5.1, nor Surfers Road's palm, 5.2, is): nothing of
                        # a prop may hang over where a car can stand
PROP_SLOPE = 0.4663     # Phase 34 (binds no prop of today's plans; kept so that a prop smaller than the tree cannot stand on a face PROP_FLAT
                        # alone would allow: 58 degrees for one 2.8 across): tan 25 degrees. The rise allowed across a prop's spread (twice its reach) is the smaller of PROP_FLAT
                        # and PROP_SLOPE x the spread: PROP_FLAT for Big Forest's tree (spread 10.2: 4.77) and Surfers Road's palm (10.3: 4.82)
FOOT_RING = 1.0         # the trunk's footprint: the prop stands at the lowest ground within it, so no side floats


@dataclass(frozen=True)
class PropFace:
    """One face of a prop in the prop's own frame (its foot at the origin, y up). An arcade prop's face (Phase 29): the corners
    as the arcade draws them (the culled side's winding) and its palette index (the colour-table word's low ten bits). A face of the
    converted course's own scenery (Phase 34, `CourseProp`): `palette` None and `rgb` its Saturn colour, the corners in the Saturn's
    order; its copy is two-sided with the nearest palette colour, as the course's own faces are."""
    p: tuple[Point, Point, Point, Point]
    palette: int | None
    rgb: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class ArcadeProp:
    faces: tuple[PropFace, ...]

    @property
    def height(self) -> float:
        return max(p[1] for f in self.faces for p in f.p) - min(p[1] for f in self.faces for p in f.p)

    @property
    def radius(self) -> float:
        """The farthest corner from the foot in XZ: the prop's reach."""
        return max(math.hypot(p[0], p[2]) for f in self.faces for p in f.p)


@dataclass(frozen=True)
class PropSource:
    """Where a prop is read: the faces of original course `course`'s tile cell `cell` whose every corner lies within `radius`
    (XZ) of (x, z) in that course's world; `faces` is how many that must be (a guard against a wrong pick)."""
    course: int
    cell: int
    x: float
    z: float
    radius: float
    faces: int


# Big Forest's tree (the recon's §4.1): the 4-face canopy (three sides and its base, 12.3 high) on a 3-face trunk (2.7), complete
# from every side, 7 faces; the one at (-53.7, -774.2) in cell 0x17. Big Forest's palette is Alpine's (template 2).
BIG_FOREST_TREE = PropSource(course=0, cell=0x17, x=-53.7, z=-774.2, radius=6.0, faces=7)


@dataclass(frozen=True)
class CourseProp:
    """Phase 34: a prop cut out of the converted course's own upright scenery (the Saturn's structures and props as placed
    and coloured for this course): the faces whose every corner lies within `radius` (XZ) of `site`; `faces` is how many that must
    be. Its copies are the course's own species: the Saturn's geometry and colours."""
    site: "Planting"
    radius: float
    faces: int


@dataclass(frozen=True)
class Planting:
    """A site named along a converted course: `offset` units from centreline point `point` (the normal direction's numbering) to
    the right of the direction of travel (negative: left), `along` units ahead of it, the copy turned `heading` degrees.
    `planting_xz` refuses a `point` the course does not have."""
    point: int
    offset: float
    heading: float
    along: float = 0.0


class Planted(NamedTuple):
    """A copy as built: its foot in world space, its heading, the Planting's point (None for a bare site)."""
    x: float
    y: float
    z: float
    heading: float
    point: int | None = None


def prop_from_quads(quads: Sequence, word: Callable[[int], int], x: float, z: float, radius: float) -> ArcadeProp:
    """The faces among `quads` (polyrom Quads, world space) whose every corner lies within `radius` of (x, z) in XZ, moved so the
    prop's foot is the origin: the middle (XZ) of its lowest corners, at their height. `word(tex_adr)` is the colour-table word."""
    near = [q for q in quads if all(math.hypot(p[0] - x, p[2] - z) <= radius for p in q.p)]
    if not near:
        raise ConvertError(f"no prop face within {radius} of ({x}, {z})")
    y0 = min(p[1] for q in near for p in q.p)
    low = {(round(p[0], 4), round(p[2], 4)) for q in near for p in q.p if p[1] - y0 < 1e-3}
    fx, fz = sum(a for a, _ in low) / len(low), sum(b for _, b in low) / len(low)
    return ArcadeProp(tuple(PropFace(tuple((p[0] - fx, p[1] - y0, p[2] - fz) for p in q.p), word(q.tex_adr) & 0x3FF) for q in near))


def prop_from_cell(rs, src: PropSource) -> ArcadeProp:
    """`src`'s prop read from the polygon ROM of `rs` (the user's own arcade set) at build time."""
    from vrtools.arcade.colours import colour_table
    from vrtools.arcade.course import tile_table
    from vrtools.arcade.polyrom import decode_object, quads
    t = tile_table(rs, src.course)[src.cell]
    prop = prop_from_quads(quads(decode_object(rs.polygons, t.poly_adr, t.size), t.tex_adr), colour_table(rs).entry,
                           src.x, src.z, src.radius)
    if len(prop.faces) != src.faces:
        raise ConvertError(f"the prop at ({src.x}, {src.z}) in course {src.course}'s cell {src.cell:#x} has {len(prop.faces)} "
                           f"faces, not {src.faces}")
    return prop


def prop_from_course(upright: Sequence[WorldQuad], x: float, z: float, src: CourseProp) -> ArcadeProp:
    """`src`'s prop among `upright` (the converted course's own structure and prop faces, world space), (x, z) being its site:
    the faces whose every corner lies within `src.radius`, moved so the foot (the middle of its lowest corners, at their height) is
    the origin, each with its Saturn colour and the Saturn's corner order."""
    near = [q for q in upright if all(math.hypot(p[0] - x, p[2] - z) <= src.radius for p in q.p)]
    if not near:
        raise ConvertError(f"no prop face within {src.radius} of ({x:.1f}, {z:.1f}) in the course's own scenery")
    if len(near) != src.faces:
        raise ConvertError(f"the course's own prop at ({x:.1f}, {z:.1f}) has {len(near)} faces, not {src.faces}")
    y0 = min(p[1] for q in near for p in q.p)
    low = {(round(p[0], 4), round(p[2], 4)) for q in near for p in q.p if p[1] - y0 < 1e-3}
    fx, fz = sum(a for a, _ in low) / len(low), sum(b for _, b in low) / len(low)
    return ArcadeProp(tuple(PropFace(tuple((p[0] - fx, p[1] - y0, p[2] - fz) for p in q.p), None, tuple(q.rgb)) for q in near))


def is_water(rgb: Sequence[int]) -> bool:
    """A water-coloured ground face: a strong blue with little red, bluer than green (the Saturn's sea on the Surfers courses:
    (0, 184, 248), (0, 200, 248)). Snow, sand, grass and tarmac are not."""
    r, g, b = rgb
    return b >= 200 and r <= 64 and b > g


def baked(prop: ArcadeProp, x: float, y: float, z: float, heading: float) -> list[WorldQuad]:
    """A copy of `prop` turned `heading` degrees about the vertical (x' = x cos h + z sin h, z' = -x sin h + z cos h, the rotation
    `geometry.face_quads` gives the Saturn's placements) with its foot at (x, y, z). An arcade prop's face (a palette index): a one-sided
    WorldQuad with that index, its corners stored in the Saturn's order (the first kept, the rest reversed), which `assign_colours`
    turns back into the arcade's drawn order with the lighting normal every original culled face stores (the reversed winding's
    right-hand normal). A face of the course's own scenery (`rgb`, Phase 34): an ordinary two-sided WorldQuad in that colour, its
    corners in the order they had."""
    a = math.radians(heading)
    c, s = math.cos(a), math.sin(a)

    def world(p: Point) -> Point:
        return (x + p[0] * c + p[2] * s, y + p[1], z - p[0] * s + p[2] * c)

    out = []
    for f in prop.faces:
        p0, p1, p2, p3 = (world(p) for p in f.p)
        if f.rgb is not None:                                    # the course's own face (CourseProp): as the Saturn's are converted
            out.append(WorldQuad((p0, p1, p2, p3), f.rgb))
            continue
        out.append(WorldQuad((p0, p3, p2, p1), (0, 0, 0), one_sided=True, palette=f.palette))
    return out


def planting_xz(centreline: Sequence[tuple[float, float]], site: Planting) -> tuple[float, float]:
    """The site's (x, z): from centreline point `site.point`, `site.along` ahead along the local direction of travel (the chord
    through its neighbours, the lap closed) and `site.offset` to its right ((dz, -dx), the AI lines' convention). ConvertError for a
    point outside the centreline."""
    n = len(centreline)
    if not 0 <= site.point < n:                                  # (review M7: a wrong point number is an error, not another point)
        raise ConvertError(f"a planting names road point {site.point}; the course has points 0-{n - 1}")
    (ax, az), (bx, bz) = centreline[(site.point - 1) % n], centreline[(site.point + 1) % n]
    d = math.hypot(bx - ax, bz - az) or 1.0
    ux, uz = (bx - ax) / d, (bz - az) / d
    x, z = centreline[site.point]
    return (x + site.along * ux + site.offset * uz, z + site.along * uz - site.offset * ux)


def _inside(poly: Sequence[tuple[float, float]], x: float, z: float) -> bool:
    inside = False
    for i in range(len(poly)):
        (x1, z1), (x2, z2) = poly[i], poly[(i + 1) % len(poly)]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            inside = not inside
    return inside


def _segment(px: float, pz: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dz = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (pz - a[1]) * dz) / L2))
    return math.hypot(px - a[0] - t * dx, pz - a[1] - t * dz)


def xz_distance(corners: Sequence[Point], x: float, z: float) -> float:
    """The XZ distance from (x, z) to the polygon `corners` (0 inside it)."""
    poly = [(p[0], p[2]) for p in corners]
    if _inside(poly, x, z):
        return 0.0
    return min(_segment(x, z, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def _triangle_height(a: Point, b: Point, c: Point, x: float, z: float) -> float | None:
    det = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
    if abs(det) < 1e-12:
        return None
    l1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / det
    l2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / det
    l3 = 1.0 - l1 - l2
    if min(l1, l2, l3) < -1e-9:
        return None
    return l1 * a[1] + l2 * b[1] + l3 * c[1]


def ground_height(ground: Sequence[WorldQuad], x: float, z: float) -> float | None:
    """The highest drawn surface among `ground` at (x, z) (each quad as two triangles on its corner-0/corner-2 diagonal), or None
    where nothing is drawn."""
    top = ground_top(ground, x, z)
    return None if top is None else top[0]


def ground_top(ground: Sequence[WorldQuad], x: float, z: float) -> tuple[float, WorldQuad] | None:
    """The highest drawn surface among `ground` at (x, z) (each quad as two triangles on its corner-0/corner-2 diagonal) and the
    face it belongs to, or None where nothing is drawn."""
    best = None
    for q in ground:
        a, b, c, d = q.p
        if not (min(a[0], b[0], c[0], d[0]) <= x <= max(a[0], b[0], c[0], d[0])
                and min(a[2], b[2], c[2], d[2]) <= z <= max(a[2], b[2], c[2], d[2])):
            continue
        for tri in ((a, b, c), (a, c, d)):
            h = _triangle_height(*tri, x, z)
            if h is not None and (best is None or h > best[0]):
                best = (h, q)
    return best


def _ring(x: float, z: float, r: float, n: int) -> list[tuple[float, float]]:
    return [(x + r * math.cos(2 * math.pi * k / n), z + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def plant(prop: ArcadeProp, sites: Sequence[tuple[float, float, float]], ground: Sequence[WorldQuad], upright: Sequence[WorldQuad],
          collision: Sequence[Sequence[Point]], points: Sequence[int | None] | None = None) -> tuple[list[WorldQuad], list[Planted]]:
    """Copies of `prop` at `sites` ((x, z, heading in degrees)), each standing on `ground` (the drawn ground and terrain faces): its
    foot at the lowest drawn height within FOOT_RING, so no side floats. ConvertError naming the site when there is no drawn ground
    under its reach (the centre and a ring at its radius), when that ground rises or falls more than PROP_FLAT or, for a small prop, PROP_SLOPE across its spread (a slope or a rock
    face), when a face of `upright` (the Saturn's own rocks, pines and buildings) comes within SCENERY_CLEAR of its reach, or when a
    quad of `collision` (corner tuples) lies within PROP_CLEAR of its foot in XZ or (Phase 34) within its reach + CROWN_CLEAR, or
    when the top surface anywhere under its reach is water-coloured (`is_water`)."""
    reach = prop.radius
    flat = min(PROP_FLAT, 2 * reach * PROP_SLOPE)
    quads: list[WorldQuad] = []
    planted: list[Planted] = []
    boxes = [(min(p[0] for p in q.p), max(p[0] for p in q.p), min(p[2] for p in q.p), max(p[2] for p in q.p), q) for q in upright]
    for i, (x, z, heading) in enumerate(sites):
        name = f"prop site {i} ({x:.1f}, {z:.1f})" + (f", road point {points[i]}" if points and points[i] is not None else "")
        near = [c for c in collision if xz_distance(c, x, z) < PROP_CLEAR]
        if near:
            raise ConvertError(f"{name}: a collision quad lies {min(xz_distance(c, x, z) for c in near):.1f} away, under "
                               f"PROP_CLEAR {PROP_CLEAR}: a car could reach it")
        if reach + CROWN_CLEAR > PROP_CLEAR:
            over = [d for d in (xz_distance(c, x, z) for c in collision) if d < reach + CROWN_CLEAR]
            if over:
                raise ConvertError(f"{name}: a collision quad lies {min(over):.1f} away, under its crown's reach {reach:.1f} + "
                                   f"CROWN_CLEAR {CROWN_CLEAR}: the prop would hang over where a car can stand")
        tops = [ground_top(ground, px, pz) for px, pz in [(x, z)] + _ring(x, z, reach, 8)]
        if any(t is None for t in tops):
            raise ConvertError(f"{name}: no drawn ground under its reach")
        if any(is_water(t[1].rgb) for t in tops):                # Phase 34 (review): a prop does not stand in the sea
            raise ConvertError(f"{name}: the ground under its reach is water")
        heights = [t[0] for t in tops]
        if max(heights) - min(heights) > flat:
            raise ConvertError(f"{name}: the ground under it rises {max(heights) - min(heights):.1f} (a slope or a rock face; "
                               f"the limit {flat:.2f}: PROP_FLAT {PROP_FLAT}, PROP_SLOPE {PROP_SLOPE} across its spread)")
        for x0, x1, z0, z1, q in boxes:
            if x1 < x - reach - SCENERY_CLEAR or x0 > x + reach + SCENERY_CLEAR or z1 < z - reach - SCENERY_CLEAR or z0 > z + reach + SCENERY_CLEAR:
                continue
            if xz_distance(q.p, x, z) < reach + SCENERY_CLEAR:
                raise ConvertError(f"{name}: the Saturn's upright scenery stands {xz_distance(q.p, x, z):.1f} from its foot "
                                   f"(its reach {reach:.1f} + SCENERY_CLEAR {SCENERY_CLEAR})")
        foot = [ground_height(ground, px, pz) for px, pz in [(x, z)] + _ring(x, z, FOOT_RING, 4)]
        y = min(h for h in foot if h is not None)
        quads.extend(baked(prop, x, y, z, heading))
        planted.append(Planted(x, y, z, heading, points[i] if points else None))
    return quads, planted


def cells_by_foot(copies: Sequence[tuple[Planted, Sequence[WorldQuad]]], grid) -> dict[int, list[WorldQuad]]:
    """Each copy's faces, whole, under the cell of `grid` its foot stands in (the Saturn's faces go by their own centres,
    `geometry.bin_quads`): a cell is drawn whole or not at all, so a copy split across two cells could show half of itself at the
    edge of the visible block. ConvertError for a foot off the map."""
    out: dict[int, list[WorldQuad]] = {}
    for site, faces in copies:
        cell = grid.cell_of(site.x, site.z)
        if cell is None:
            raise ConvertError(f"a prop's foot ({site.x:.1f}, {site.z:.1f}) is off the map")
        out.setdefault(cell, []).extend(faces)
    return out
