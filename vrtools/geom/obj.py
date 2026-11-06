"""Wavefront OBJ writer for decoded quads (one `g` per named group)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from vrtools.arcade.polyrom import Point, Quad

Transform = Callable[[Point], Point]


def _fmt(v: float) -> str:
    return f"{v:.6g}"


def write_obj(path: Path, groups: dict[str, Iterable[Quad]], scale: float = 1.0,
              transform: Transform | None = None) -> None:
    lines: list[str] = ["# written by vrtools"]
    next_index = 1
    for name, quads in groups.items():
        lines.append(f"g {name}")
        index: dict[Point, int] = {}
        faces: list[str] = []
        for quad in quads:
            ids: list[int] = []
            for pt in quad.p:
                v = tuple(c * scale for c in pt)
                if transform:
                    v = transform(v)
                if v not in index:
                    index[v] = next_index
                    next_index += 1
                    lines.append("v " + " ".join(_fmt(c) for c in v))
                if ids and ids[-1] == index[v]:
                    continue                                   # collapse repeated vertex
                ids.append(index[v])
            if len(ids) > 1 and ids[0] == ids[-1]:
                ids.pop()
            if len(ids) < 3:
                continue
            faces.append(f"# tex {quad.tex_adr}")
            faces.append("f " + " ".join(str(i) for i in ids))
        lines.extend(faces)
    Path(path).write_text("\n".join(lines) + "\n")
