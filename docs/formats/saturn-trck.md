# Saturn Virtua Racing — `TRCK*` course files

Source: `VRSRCDIR/TRACKS00/<COURSE>/TRCK<xxxx>` on the Europe disc (T-4803G).
One file per course, same layout for all ten (the three arcade courses and
the seven Saturn-only ones).

## Header: pointer table

- 44 big-endian 32-bit pointers at file offset 0 (176 bytes).
- Pointers are absolute Saturn high-work-RAM addresses. **Load base is
  `0x06096000`**: every non-zero pointer in every file falls inside
  `[0x06096000, 0x06096000 + filesize)`.
- Entry 4 always equals base + `0xb0`, i.e. the data directly after the
  table. Entry 3 is zero in every file; Metropolis also has entries 38 and
  39 zero.
- Parser: `vrtools.saturn.trck.TrckFile` (`offset(i)`, `sections()`).

## File sizes (bytes)

| Course | File | Size |
|---|---|---|
| Acropolis | TRCKACRO | 429,904 |
| Alpine | TRCKALPN | 422,132 |
| Amazon Falls | TRCKAMAZ | 400,112 |
| Bay Bridge | TRCKBAYB | 356,276 |
| Big Forest | TRCKBIGF | 396,320 |
| Diablo Canyon | TRCKDIAB | 403,156 |
| Metropolis | TRCKMETR | 364,224 |
| Pacific Coast | TRCKPACC | 382,300 |
| Surfers Speedway (Oval + Road) | TRCKSPEE | 386,084 |
| Surfers (Surfer00) | TRCKSURF | 403,180 |

## Companion files per course

- `BGS<xxx>N` (70–290 KB) and `BGM<xxx>N` (always 10,240 bytes, a tilemap of
  sequential cell numbers): believed to be the 2D horizon backdrop (VDP2
  cells + map), 2 or 4 variants per course. Speedway has none.
- `TEXTMETR` exists only for Metropolis.

## Section 4: road segment table (verified on all ten files, Phase 3)

76-byte records of 19 big-endian 32-bit words (`vrtools.saturn.course.segments`); words 0–14 are 16.16, 15–17 angles, 18 raw:

| words | content |
|---|---|
| 0–11 | four planes `(nx, nz, d)` bounding one road slice in the XZ plane (`n·p + d ≥ 0` inside); an all-zero plane means the slice is a triangle (3 planes) |
| 12–14 | surface normal `(nx, ny, nz)` (unit; `(0, 1, 0)` on flat ground) |
| 15–17 | three angles in 1/2³² of a turn: word 16 is the banking (rotation about Z, e.g. −1.78° where the normal's x is 0.031) and word 17 the slope (about X); word 15 is tiny (about Y). All zero on flat segments |
| 18 | always 0 |

Derived: corners = intersections of consecutive active planes, accepted only when
they form a proper convex polygon inside every plane (otherwise `centre` is None;
≥ 99 % of records qualify on every course); centre = mean of corners; for quads, width ≈ 2.49 (Big Forest, across the road), length ≈ 1.0
(along it), heading = direction along the short sides oriented by plane 1's
normal. Records are **not** stored in lap order as a whole: they come in lap-ordered
**runs** joined by jumps (see Runs below); `vrtools.convert.lap.order_slices` orders them
into a lap by shared edges.

## Sections 5–9: spatial grid (verified on all ten files, Phase 3)

Sections 5–8 are one 16.16 word each: `-xmax`, `-zmax`, `16/(xmax-xmin)`,
`16/(zmax-zmin)` where the bounds are those of the segment polygons. Section 9
is 256 absolute pointers (one per cell, 0 = empty; `cell = zc*16 + xc` with
`xc = int((xmax - x) * inv_w)`, `zc = int((zmax - z) * inv_h)`, i.e. counted from
the (xmax, zmax) corner) to lists `count:u16, segment_index:u16[]`. Every cell has
a pointer (empty cells point at a 2-byte empty list; the lists are contiguous in
cell order and one more empty list trails the section). A segment is listed in
every cell its polygon overlaps (99.7–100 % of entries check out).
Sections 11–14 hold a second, slightly padded set of the same four parameters
(use TBD). Decoders: `grid_params`, `grid`, `cell_of`.

## Objects (geometry blobs in sections 10, 15, 30, 39; verified on all ten files, Phase 3)

Each object group's pointer list (sections 2, 18, 21, 24, 37) holds absolute
pointers to objects; an object runs to the next object start (a few padding
bytes may follow its faces). Layout, all big-endian (`vrtools.saturn.course.meshes`):

| field | content |
|---|---|
| `count:u32` + `count` × `(x, y, z)` 16.16 | vertices in object-local units (±8) |
| `count:u32` + `count` × `(nx, ny, nz)` 16.16 | normals |
| `count:u32` + `count` × 14-byte faces | `colour:u16 RGB555, attr_a:u16 (0..11), attr_b:u16 (mostly 1 or 6), v0..v3:u16`; a triangle repeats a vertex id |

Big Forest: group 0 = 25 objects, group 1 = 31; 1,415 objects and 64,268 faces
across the ten courses, every vertex id valid. `attr_b` is **not** an index into
the normal list (out of range for 4 % of faces); both attributes are kept raw.
Some objects are empty placeholders (zero vertices).

## Placement tables (sections 0, 16, 19, 22, 35; counts in 1, 17, 20, 23, 36; verified on all ten files, Phase 3)

56-byte entries, 14 big-endian i32 words (`vrtools.saturn.course.placements`); the entry count is the u16 at the start of the group's count section:

| word | content |
|---|---|
| 0 | flags: `0x1000` for ground tiles, 0 for props |
| 1 | mesh index in the high half (signed i16; −1 = empty slot) into the group's pointer list |
| 3 | yaw about Y in 1/2³² of a turn (0x40000000 = 90°) |
| 4 | a second angle (props only; TBD) |
| 5, 6, 7 | x, y, z (16.16 world units). Note: placed geometry is half a turn from the road-slice frame — the converter maps slices with `to_arcade` (x, z negated) and placements with `tile_to_arcade` (not negated); see `docs/spike/2026-11-m3-recon.md` §1 |
| 11 | bounding radius (16.16): 11.314 = 8√2 for a 16-unit tile |
| 2, 8–10, 12, 13 | zero |

Groups 0–3 are **ground tiles**: a regular lattice 16 units apart (Big Forest 4 × 9
= 36 entries at x ∈ {−18.69, −2.69, 13.31, 29.31}), the Saturn equivalent of the arcade's tile grid. They are
**layers of one picture**, not variants (measured in Phase 18, `docs/spike/2026-11-phase18-scenery-recon.md` §1):
group 0 the road and ground, group 1 the terrain (hills, cliffs, water, snow) where group 0 has nothing, group 2 the
road paint lying a few hundredths of a unit on group 0's road, group 3 the structures (trees, fences, boats) and some
flat decals. The mesh lists differ (Big Forest 25/31/25/30 meshes). Group 4 holds free-placed props with rotation and
height (Big Forest 9, Bay Bridge 87).

## Whole-file round trip

`vrtools.saturn.course.decode_course` / `encode_course` / `verify_lossless` re-emit the
segment table, grid parameters, grid, placement tables and every object
byte-identically on all ten course files (`tests/test_saturn_roundtrip.py`), and the
re-emitted regions never overlap. Sections not covered: the count sections
(1, 17, 20, 23, 36), 11–14 (second parameter set), 25–29/38/40–43 (32-entry
24-byte tables), the small u32 sections 31–34, and the pointer lists themselves.

## Runs and lap ordering (Phase 6)

Consecutive indices are adjacent (< 2 units) for 316 / 430 slices on Big Forest and
371 / 527 on Alpine; the rest are jumps between runs, and a run can go either way
round the course. Slices tile the road as a 2-D mesh (strips side by side, triangle
fans at the kerbs), so the lap is recovered from shared edges rather than indices:
`order_slices` builds the shared-edge graph, bridges gaps up to 8 units, cuts the edges
crossing the start line, takes Dijkstra distances for the arc and the shortest path back
to the start as the route (a fork keeps its shorter branch).

Phase 8: polygons that touch (within 0.5 units) without sharing an edge are adjacent too,
and after the start-line cut the cut side bridges to slices still unreached; with that all
ten files order. The Surfers files (TRCKSFSP oval, TRCKSURF road) and Amazon Falls build
their kerbs and much of their road from triangles and long slivers (Surfers Road's route:
113 triangles and 83 slivers of 285 slices) and start with the kerb triangles, out of lap
order; the oval file also carries an unused 112-slice infield (the lap orders at 80 %
coverage). The first slice of a degenerate start (step < 0.5) is moved to a proper quad
slice with a clockwise axis.

## Trackside cameras (sections 26, 41, 43)

The 32-row tables (43 rows on Alpine, 41 Amazon, 57 / 48 Bay Bridge) are
`(cos, sin, x, z, w, flag)` with positions up to 400 units from the road: trackside
camera placements, not AI lines. Section 28 (3–4 rows, last word ≈ 2.7) is similar.

## Heights

Segment word 18 is 0 on every course and the slices carry no height; the ground tiles of
placement group 0 hold the road faces, so the road height is read from the mesh under
each slice (`vrtools.convert.profile.road_profile`: median per 10 units of arc,
interpolated over holes, banking dropped).

## Sections still undecoded

| Section(s) | Content |
|---|---|
| 11–14 | a second set of the four grid parameters, slightly padded bounds (use TBD) |
| 25, 27, 29, 38, 40, 42 | 24-byte-row tables with preceding counts (26 / 41 / 43 are cameras, 28 camera-like; the rest candidates for checkpoints) |
| 31–34 | two 16.16 values and two small integers |

Details and evidence: `docs/spike/2026-11-saturn-course.md` and `docs/spike/2026-10-big-forest-overlay.md`.
