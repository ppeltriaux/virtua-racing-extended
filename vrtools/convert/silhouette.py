"""Phase 31 (prototype, the Phase 28 recon's candidate 5): a far landmark's silhouette in nearer cells.

The game draws only the 5x5 block of 128-unit cells around the camera, so a tall structure appears a whole cell row at a time.
A cell's object is world-space geometry, binned by centroid by the converter's own choice: a copy of a far structure's tall
faces placed in a nearer cell's object is drawn whenever that nearer cell is, so from further away. Both copies are drawn
while both cells are in the block (the same faces twice; measured in the Phase 31 findings).

Scenery only: the collision never sees these quads (it reads the Saturn course itself)."""

from __future__ import annotations

from dataclasses import dataclass

from vrtools.convert.geometry import ConvertError, WorldQuad


@dataclass(frozen=True)
class FarCopy:
    """The silhouette of cell `source` (its faces whose highest corner is at or above `min_top` and that rise at least
    `min_rise`; with `within` = (x0, z0, x1, z1), only those with every corner inside that box: one structure of a cell that
    holds several) copied into each cell of `into`. Cells are tile cells, z * 16 + x of the 128-unit grid (geometry.TILE_GRID).
    `faces`: the number of faces the selection is meant to give (a hand-tuned box pins it); any other count is a ConvertError."""
    source: int
    into: tuple[int, ...]
    min_top: float
    min_rise: float = 0.0
    within: tuple[float, float, float, float] | None = None
    faces: int | None = None


def silhouette_quads(quads: list[WorldQuad], min_top: float, min_rise: float = 0.0,
                     within: tuple[float, float, float, float] | None = None) -> list[WorldQuad]:
    """The quads whose highest corner is at or above `min_top` and whose corners span at least `min_rise` in height (the
    upright faces of a tall structure; a roof spans nothing), in the order given; with `within` = (x0, z0, x1, z1), only
    those with every corner inside that box (edges included)."""
    out = []
    for q in quads:
        ys = [p[1] for p in q.p]
        if max(ys) < min_top or max(ys) - min(ys) < min_rise:
            continue
        if within is not None and not all(within[0] <= p[0] <= within[2] and within[1] <= p[2] <= within[3] for p in q.p):
            continue
        out.append(q)
    return out


def far_copy_cells(cells: dict[int, list[WorldQuad]], copies: tuple[FarCopy, ...],
                   capped: frozenset | set = frozenset()) -> tuple[dict[int, list[WorldQuad]], dict]:
    """The cells `copies` change: {cell: its own quads followed by the silhouette faces copied into it, in the copies' order},
    and a report {cell: {"own", "copied", "from"}}. The faces are the sources' own quads as binned (a copy never carries
    another copy on); `cells` is not changed. ConvertError for a copy that cannot be made: a source without scenery or without
    a face of that height, a cell copied into itself, a number that is not a cell, a cell named twice or none named, a face
    count other than the copy's `faces`, or a source or target cell in `capped` (the cells over the record cap, of which only
    the first split is installed: their quads here are not what the game would draw)."""
    out: dict[int, list[WorldQuad]] = {}
    report: dict[int, dict] = {}
    for c in copies:
        if not c.into:
            raise ConvertError(f"far copy of cell {c.source}: no cell to copy it into")
        if len(set(c.into)) != len(c.into):
            raise ConvertError(f"far copy of cell {c.source}: a cell is named twice in {c.into}")
        for cell in (c.source, *c.into):
            if not (isinstance(cell, int) and 0 <= cell < 256):
                raise ConvertError(f"far copy of cell {c.source}: {cell} is not a cell (0..255)")
        if c.source in c.into:
            raise ConvertError(f"far copy of cell {c.source}: copied into itself")
        for cell in (c.source, *c.into):
            if cell in capped:
                raise ConvertError(f"far copy of cell {c.source}: cell {cell} is over the record cap (only its first split is drawn)")
        if not cells.get(c.source):
            raise ConvertError(f"far copy of cell {c.source}: the cell has no scenery")
        faces = silhouette_quads(cells[c.source], c.min_top, c.min_rise, c.within)
        if not faces:
            raise ConvertError(f"far copy of cell {c.source}: no face reaches {c.min_top} rising {c.min_rise}"
                               + (f" within {c.within}" if c.within else ""))
        if c.faces is not None and len(faces) != c.faces:
            raise ConvertError(f"far copy of cell {c.source}: the selection selects {len(faces)} faces, not the {c.faces} "
                               f"the plan pins" + (f" within {c.within}" if c.within else ""))
        for cell in c.into:
            if cell not in out:
                out[cell] = list(cells.get(cell, []))
                report[cell] = {"own": len(out[cell]), "copied": 0, "from": []}
            out[cell].extend(faces)
            report[cell]["copied"] += len(faces)
            report[cell]["from"].append(c.source)
    return out, report
