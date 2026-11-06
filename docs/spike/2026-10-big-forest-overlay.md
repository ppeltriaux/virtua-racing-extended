# Spike: Big Forest from both games (M0)

Throwaway exploration; scripts in `spike/`, outputs under `out/spike/` (not
committed). This page records what was learned.

## Reproduce

```sh
source local.env            # VR_ROMDIR, VR_SATURN_CUE
.venv/bin/python - <<'END'
from pathlib import Path; import os
from vrtools.mame.runner import run_mame, LUA_DIR
wd = Path("out/spike/arcade/run1").resolve()
run_mame(LUA_DIR / "autoplay.lua", 90, wd, Path(os.environ["VR_ROMDIR"]),
         env={"VR_COURSE": "0", "VR_DLIST_LOG": str(wd / "dl.txt"), "VR_DLIST_FROM": "1400", "VR_DLIST_EVERY": "15"})
END
.venv/bin/python spike/arcade_bigforest.py out/spike/arcade/run1/dl.txt out/spike/arcade
.venv/bin/python spike/saturn_trck_scan.py out/spike/arcade/world.csv out/spike/saturn
```

Produces `objects.csv`, `world.csv`, `stats.txt`, `topdown.png`,
`topdown_raw.png`, `bigforest_tiles.obj`, `objs/*.obj` (arcade) and
`sections.txt`, `segments.png`, `overlay.png` (Saturn). The `candidates.png`
scatter mentioned below was a one-off check that the big Saturn blobs are
*not* flat vertex arrays; it is not regenerated.

## Arcade (Model 1) — done 2026-10-30

**Method.** `autoplay.lua` drives Big Forest for 90 s while `dlist_log.lua`
dumps the active display list every 15 frames (252 samples). Every
`0x01` object was decoded from polygon ROM with `vrtools.arcade.polyrom`.

**Facts.**
- 531 distinct objects were drawn; all live in polygon ROM (no polygon-RAM
  uploads during the race); every object command uses `size = 5500` (a cap;
  objects end with their own end marker).
- Every object is preceded by its own `0x0b` matrix. Matrices come in three
  scales: `1.0` (world and cars), `0.0008` (= 1/1250: HUD icons drawn at
  z ≈ 1.5, e.g. the position markers on the lap map), and `1.2` / `2.0`
  (a few scaled props).
- **The track is a grid of world-space tiles.** Objects with ≥ 200 records
  (88 of them in the 90 s sample) are tiles about 130–170 units square whose
  vertices are absolute world coordinates (track XZ extent ≈ −323..409 by
  −645..656). Their matrix is simply the camera (view) transform, identical
  for all tiles in a frame. Plotting the raw tile geometry gives the Big
  Forest layout directly (`out/spike/arcade/topdown_raw.png`): pit straight,
  hairpin, sweeper. Trees, grandstands and other scenery are *baked into the
  tiles*, not placed as separate objects.
- Cars and animated props are separate objects with their own matrices
  (world pose × camera), and show up as "moving" when chained across frames.
- Tile data for Big Forest starts at polygon-ROM word address 0x67ec
  (byte 0x19fb0); the 88 sampled tiles span up to word 0x2d60cf and total
  about 1.5 MB of records. Object address ranges overlap each other (59 of
  87 adjacent pairs), so some "objects" are sub-ranges of larger strips
  (likely LOD or partial draws); the exact tile table must come from the
  V60 side (M1), not from ROM adjacency.
- Common record flag patterns in tiles: link 2 with z-mode 2, texture
  advance on nearly every record, light mode 0 or 1; `no_cull` set on the
  road surface records (visible from both directions).
- Elevation (Y) in tiles is small relative to XZ (Big Forest is nearly flat).

**What this means for the converter.**
- A new course's visible geometry = a set of world-space tile objects in
  polygon ROM, plus a table (in V60 data ROM, still to be found) that says
  which tiles exist and where, so the game can cull by camera position.
- Scenery density is controlled per tile: thinning for frame rate means
  dropping polygons inside tiles.

**Still unknown (M1 work).**
- The V60-side course tables: tile index/grid, road centreline/edges used
  for physics and the AI racing line, checkpoints, start grid, the
  course-select tables. Approach: `unidasm` (built in `build/mame/`) on the
  V60 program plus MAME debugger watchpoints on polygon-address writes into
  the display list.
- How `tex_adr` ranges map to palette colours per tile (colour table is
  uploaded with command `0x04` at course load, before our logging window).

## Saturn — done 2026-10-30

**Method.** `vrtools.saturn.trck` splits `TRCKBIGF` into its 44 pointer
sections; each was characterised (entropy, periodicity, first bytes) and the
structured ones decoded by hand. Every hypothesis was then re-checked on all
ten course files.

**Facts (hold for all ten courses).**
- **Section 4 = road segment table**: `length % 76 == 0` for every course
  (Big Forest 431 segments, Bay Bridge 287, Acropolis 409, Alpine 528,
  Amazon 464, Diablo 645, Metropolis 388, Pacific 566, Speedway 717,
  Surfer 695). Each 76-byte record starts with four planes
  `(nx, nz, d)` in 16.16 fixed point, in pairs of opposite normals, that
  bound one slice of road: Big Forest record 0 is x ∈ [14.6, 17.09],
  z ∈ [42.0, 43.0], i.e. a road 2.49 units wide sliced 1 unit long on the
  pit straight; curved records have rotated normals. Words 12–14 look like
  a surface normal, words 15–18 and the int16 tail vary with the record
  (banking/height/next-segment links: to decode in M2).
- **Section 9 = 16×16 spatial grid**: 256 pointers (1 KB) followed by
  lists of `count:u16, index:u16[]` (indices < segment count), i.e. which
  road segments touch each grid cell — a collision/lookup accelerator.
- **Object groups**: five groups, each a placement table (56-byte entries,
  count in the following 4-byte section) plus a pointer list into one of
  four geometry blobs (sections 10, 15, 30, 39; Metropolis lacks 39).
  Big Forest: 36/25, 36/31, 36/25, 36/30 and 9/14 placements/objects.
  A placement entry carries a world position (e.g. x = −18.69, z = −75.79,
  repeated every 16 units along the pit straight) and what looks like an
  object index/flags word. An object starts with `count:u32` followed by
  `count` vertices of three 16.16 values in **object-local coordinates**
  (values up to 8.0), then face data (not decoded yet).
- Units: the Saturn world for Big Forest spans about 81 × 183 units
  (segment centres); the road is 2.49 units wide.

## Overlay — done 2026-10-30

`spike/saturn_trck_scan.py` fits the 388 solvable Saturn segment centres onto
the arcade's flat tile vertices with an iterative nearest-point similarity
fit (8 starting orientations). Best fit: rotation 180°, no mirror,
**scale ≈ 8.4 arcade units per Saturn unit (provisional)**, mean residual
16.8 arcade units (about four fifths of the 2.49 × 8.4 ≈ 21-unit road width). The overlay
(`out/spike/saturn/overlay.png`) matches the pit straight, the top sweeper
and the right-hand descent; the hairpin is under-sampled because 43 records
with parallel plane pairs were skipped by the simple centre solver. The
fit is good enough to confirm the two games describe the same layout; the
exact unit ratio should be pinned in M2 from road width (2.49 Saturn units
vs. the arcade road width) rather than from this fit.

## Conclusion

- Arcade: course = world-space tile objects in polygon ROM (geometry and
  baked scenery) + V60-side tables (still to find).
- Saturn: course = segment table (road + collision) + 16×16 grid +
  placed scenery objects with local-coordinate meshes.
- The data-converter approach stands: Saturn segments give the road
  centreline/edges, Saturn placements + meshes give scenery, and both
  must be re-emitted as arcade tiles plus whatever V60 tables M1 uncovers.
- M1 next: find the V60 tables (tile list, road/AI/checkpoints, course
  select) with `unidasm` + MAME debugger. M2 next: decode segment words
  12–18, the placement entry, and object face data.
