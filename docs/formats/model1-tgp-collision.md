# Model 1 Virtua Racing: TGP collision data (`copro_data`)

The road-height / surface queries the V60 makes every logic frame are answered
by the MB86233 "TGP" from per-course geometry in the TGP data ROMs
(`mpr-14898..14901`, one byte lane each, 2 MB = 0x80000 32-bit words). This is
the data a new course must supply for the car to drive on it. Decoded in Phase 5
from the TGP program listing (`unidasm -arch mb86233 315-5573.bin`, 2,048 words)
and MAME taps; recon with the raw measurements: `docs/spike/2026-11-tgp-collision.md`.
Decoder / encoder: `vrtools/arcade/tgp.py` (lossless on all three courses,
`tests/test_tgp.py`).

## 1. Addressing

All addresses below are **word** offsets into `RomSet.copro_data` (little-endian
u32 at byte `4 × word`). The TGP reads the ROM through I/O addresses
0x8000–0xffff as a 32K-word window: `ROM[(base & ~0x7fff) | (io − 0x8000)]`
with `base` written to I/O 0x2e (MAME `model1_m.cpp`, `copro_data_r`). The
program sets the base to the full word address it wants, so any 19-bit address
is reachable.

## 2. Layout

| words | content |
|---|---|
| 0x0–0xf | 4 × 4 identity matrix (TGP constants) |
| 0x10–0x1f | slot table: list block address of slots 0–15 |
| 0x20–0x2f | slot table: quad pool address of slots 0–15 |
| 0x30–0x3fa1 | Bay Bridge list block (slot 0) |
| 0x3fa1–0x8000 | zero filler |
| 0x8000–0xb547 | Acropolis list block (slot 1) |
| 0xb547–0x10000 | zero filler |
| 0x10000–0x12dfb | Big Forest list block (slot 2) |
| 0x12dfb–0x12e00 | `0xcdcdcdcd` filler |
| 0x12e00–0x28a90 | Bay Bridge quad pool, 5,577 quads |
| 0x28a90–0x3c170 | Acropolis quad pool, 4,974 quads |
| 0x3c170–0x4b170 | Big Forest quad pool, 3,840 quads |
| 0x4b170–0x80000 | `0xffffffff`: free, 216,720 words (846 KB) |

Slots 3–15 hold Bay Bridge's addresses (0x30 / 0x12e00). The zero gaps are
another 35,608 words (139 KB) that are not referenced by anything.

**Slot = course data index.** The V60's course-load routine (boot ROM
`0xfe48ed`) reads the data index at RAM `0x501934` (Bay Bridge 0, Acropolis 1,
Big Forest 2) and sends FIFO command `0x06800000, index`; TGP handler 13
(`0x1a5` → subroutine `0x7e2`) copies `ROM[0x10 + index]` into TGP variable
`$0x69` and `ROM[0x20 + index]` into `$0x6a`. A new course with data index *n*
therefore needs slot *n* filled. The same routine fills the per-course RAM
pointers from boot-ROM tables indexed by the data index (`0xfcd5b9`,
`0xfcf16d`, `0xfe49a4` → tile table pointer at `0x501948`, `0xfda543`) and
copies bank header words `0x100004/8/c/10` into `0x501954/58/50/60`; that is
where the M4 course-table work starts.

**Windows.** The TGP addresses ROM through a 32K-word window: a read sets the window base from the full
address (`$0x2e`), keeps the low 15 bits as its index and walks on with post-increment through a 16-bit
effective address, so a list (count + entries) or a 16-word quad that crosses a multiple of 0x8000 words
continues from I/O address 0, not from ROM. The originals never cross; `install_collision` keeps a course's
list block inside one window and aligns its pool to 16 words (Phase 8 review).

## 3. Lists

The V60 collision map (course bank +0xcf98, 128 × 128 halfwords, cell =
`((x+1024)>>4) + 128*((z+1024)>>4)`, 16-unit cells) holds, per cell, the
**word offset of the cell's list inside the course's list block** (0 = off
road). A list is `count:u32, quad_index:u32[count]`. Lists are stored
consecutively in id order, each referenced by exactly one cell (verified: the
walk from the first id to the last hits every id and nothing else on all three
courses). Mean 7.6–9.7 quads per list, maximum 45; the halfword map caps a
block at 0xffff words.

## 4. Quads

16 words per quad, `pool + 16 × index`:

| words | content |
|---|---|
| 0–11 | four corners `(x, y, z)` f32, arcade world units |
| 12–14 | centre `(x, y, z)` f32 (mean of the corners within 0.05 on 98.5 % of quads) |
| 15 | **road direction**: a sign-extended 16-bit angle in 1/65536 turn, `−atan2(dx, dz)` of the direction of travel (the road-line heading word's high half is the same angle in 1/16384 turn). 97 % of Big Forest's non-zero values lie within ±22° of the centreline direction at the nearest point; 0 on 11–16 % of quads (the start-grid straight among them) |

Every original quad has the same winding: negative signed area in XZ
(`Σ (x_k·z_{k+1} − x_{k+1}·z_k) < 0`). Typical size 3–4 units across and 8–11
along the road (p90 18–20); Big Forest's road lies at y 29–46, Bay Bridge
0–40, Acropolis −1–22. One original quad (Acropolis index 4973) is vertical
(zero XZ area): a wall. The surface byte table at bank +0x14f98 is 256 × 0x01
on all three courses.

What the direction does (Phase 5 experiment, `spike/attr_experiment.py`): with
the wheel centred and the pedal floored, the original car follows the road for
the whole 60-second run (1,293 units, reaching the raised section at y 45).
With every attribute forced to 0 the same car takes a different line (same quad
on 344 of 916 samples, up to 179 units apart) and never climbs; forced to 0x7fff
it is slower (1,008 units) and to 0xffff8001 it diverges by 308 units. The game
therefore steers (or pulls) a car along the quad's direction: a converted course
without directions has no road-following help, and an unsteered car runs
straight. Emitting it needs the Saturn slices in lap order (M3): the Saturn
slice heading gives the road axis only up to a 180° flip (61 % of Big Forest
slices within ±22°, split 33 / 28 between the two signs).

## 5. The collision call (TGP function 0x1b01)

V60 routine `0xfed52b`, for the player then each opponent, writes on the FIFO
(0xd80010 low half, 0xd80012 high half):

```
0x1b010000        dispatch index 0x1b00 >> 7 = 54 -> handler 0x482 (then 0x489); bit 0 = variant
y                 f32 current height
id                collision-map value at the car's cell
x, z              f32 position
```

Handler 0x489–0x4d5: `list = $0x69 + id`, then for each index `quad = $0x6a +
16·index`, copy the 16 words to RAM and run the convex point-in-polygon test
(one-sided: the cross product of every edge with the point must be ≥ 0, which
the originals' negative-area winding gives for interior points). **Every quad
containing the point is a hit**: its index and interpolated height
(subroutine `0x693`) are appended to a hit array at TGP RAM 0x110 and counted
in `$0x4b`. The interpolation treats the quad as **two triangles on its
corner-0/corner-2 diagonal**: the plane of corners 0-1-2 on corner 1's side of
the diagonal, of 2-3-0 on the other (Phase 22a, Diablo replay: 131 samples on
twisted converted quads within 0.0006 units, against up to 0.79 for the plane
of the first three corners alone). A twisted quad is therefore a continuous
surface through all four corners; `convert/collision.tgp_height` models it. The continuation at 0x4f5 then picks **the hit whose
`| |height| − y |` is smallest**, `y` being the height the V60 passed (the
car's current height); a later hit replaces an equal one, so exact ties go to
the last entry in list order, and ties broken by the interpolation's rounding
go either way (measured: 75 % last, 25 % first on a flat course). The
originals' quads do not overlap (measured again in Phase 11: on Big Forest and
Acropolis no sample of the road's ±10 band lies under both a verge and a tarmac
quad; Bay Bridge's 120 are its overpass decks, more than 2 units apart), so this
only matters for converted data: a verge quad whose plane sits off the tarmac's
captures a car in any overlap (its height is nearest the car's own once the car
is on it) **whatever the sign of the offset** — a car that has touched the verge
stays on it wherever verge and tarmac overlap, and its lap position freezes.
`convert/collision.py` therefore builds the verges from the road's measured edge
after the tarmac is final (`road_edges` / `road_verges`, Phase 11), so that the
two touch and overlap by less than half a unit, and sets the verge `VERGE_SINK`
(0.3) away from zero of the tarmac's height so that the contact strip resolves
for the tarmac when the car is at the tarmac's height. Results go to TGP RAM: word 0 is
cleared from 0xffffffff when done, **word 1 = height at (x, z)**, **word 2 =
index of the quad chosen**. The V60 polls word 0 through its I/O space
(writes 0 to 0xd00000, reads 0xd20000 until not 0xffffffff), then writes
0x8001 to 0xd00000 and reads words 1 and 2. The quad index is then passed to
commands 0x1500 (with x, z; handler 0x34b) and 0x1800 (handler 0x431), which
read the same record again.

## 6. What a new course must supply

1. Quads covering the drivable road (and walls if wanted), same winding as
   the originals, at the course's road height.
2. One list per 16-unit cell the road touches, each quad listed in every cell
   its XZ polygon overlaps; lists consecutive, block ≤ 0xffff words.
3. The course bank's collision map rewritten with the list offsets.
4. A slot entry (list block, pool) at words 0x10 + n / 0x20 + n for the
   course's data index n, with the data in the free area from 0x4b170.

Budget: Big Forest's arcade data is 73,211 words (286 KB), so seven courses at
arcade density (≈ 2 MB) do not fit. One quad per Saturn road slice (431 slices
on Big Forest, 528 on Alpine, 464 on Amazon Falls; a slice is about 29 × 12
arcade units) plus lists is about 10,000 words (40 KB) per course: seven fit in
the 846 KB with room for subdivision. Saturn slices carry no height (segment
word 18 is 0 everywhere) — only the surface normal — so the road height of a
converted course comes from the Saturn ground mesh under each slice.
