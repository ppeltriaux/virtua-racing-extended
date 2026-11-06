# Discovery log: arcade course tables (Phase 2 / M1)

Working notes, chronological. Facts promoted to `docs/formats/model1-course-tables.md`
once confirmed. Outputs live under `out/p2/` (not committed).

## Course variable (2026-10-30)

- Method: `autoplay.lua` with `VR_COURSE` 0/1/2 and `VR_TRACE_DUMP=1300,2400`; `ramdiff.diff_dumps`
  across the three runs; keep addresses in arithmetic progression.
- Select-screen wheel zones (absolute paddle value, measured by snapshot): `<=150` Big Forest,
  `175` Bay Bridge, `>=200` Acropolis. The centre value 128 selects Big Forest; the cursor
  follows the absolute wheel position every frame, so the wheel must be held through the
  "step on gas" start or the choice snaps back. `autoplay.lua` now holds it until frame 1700.
- **Result: `0x501940` (byte) = selected course, 0/1/2**, set during the select screen and still
  holding during the race. `0x501969` also differs (214/223/232: course-dependent, unknown).
- Readers during frames 1300–1700 (course 0): `0xfc2880` (148 reads, select loop, until frame 1597)
  and **`0xfc0bb8` once at frame 1604**, one frame after the data bank switches to 3 at frame 1603
  (course load). Writer: `0xfc26fa`.

## Course banks (2026-10-30)

- Tracing data-ROM reads in the load window (frames 1590–1700) for each course shows the loader
  switching the 1 MB window to **one bank per course**: Big Forest = bank 3 (data ROM
  `0x300000`), Bay Bridge = bank 1 (`0x100000`), Acropolis = bank 2 (`0x200000`); bank 0 is
  shared data. The bank write happens at PC `0xfe416a` (value `(bank<<4)|1`, frame 1602). The
  same loader PCs then read the same *relative* offsets in whichever bank is mapped.
- `PC` and `CURPC` agree in MAME's V60 core (checked), so traced PCs are instruction starts.
- Used size per bank (last non-0xFF byte): bank 0 971 KB, Big Forest 893 KB, Acropolis 860 KB,
  Bay Bridge 221 KB. But each course bank has a large 0xFF hole in the middle: course tables
  occupy roughly the first 0x2b000–0x37000 bytes, then nothing until `0xc0000`, where another
  ~125 KB block sits (Big Forest, Acropolis; Bay Bridge has none).

## Course bank header (Big Forest, offsets relative to the bank base; pointers are V60 window addresses `0x10xxxx`)

| offset | value (BF) | meaning (so far) |
|---|---|---|
| +0x00 | `0x115e98` | graphics-upload directory: 10 pointers to `(src, dst)` pair lists (one per phase), lists inline after the pointers; `dst` in tile RAM `0x7exxxx`/`0x7fxxxx` and palette `0x900c00` |
| +0x04 | `0x100020` | pointer to the counts/array block at +0x20 |
| +0x08..+0x10 | `0x102250/54/58` | pointers to three consecutive u32 at +0x2250: `0x10cf98`, `0x114f98`, `0x102298` |
| +0x14..+0x1c | `0x102298` ×3 | pointer to the road point list |
| | | *(rows below written before the pointer block was decoded; superseded by `docs/formats/model1-course-tables.md` §2–§5: the block at +0x2250 is collision ptr, surface ptr, then (ptr, count) pairs, and the cell formula is x low / z high)* |
| +0x20 | `0x152` (338) | number of road points |
| +0x24 | `0x445` (1093) | number of 8-byte entries in the array at +0x2c |
| +0x28 | `2` | ? |
| +0x2c | array | 1093 × `(road_point:u16, 1|66:u16, 2:u16, running index:u16)`; entries grouped by road point (1–8 per point) — meaning TBD (per-point slice/tile list?) |
| +0x2250 | `(ptr, count)` pairs after two pointers (superseded; see format doc) | five point lists of 338 × 16 bytes each: `0x102298` (centre), `0x103838`, `0x104dd8`, `0x106378`, `0x107918` |
| +0x2298 | point list | **road centreline**: `(x:f32, z:f32, heading:i32 (16.16), link:i32 (hi = index into the +0x2c array, lo = ?))`; plotted, it follows the Phase 1 tile map exactly (`out/p2/bf_roadpoints.png`); spacing ≈ 10 units; x/z extent −197..326 / −711..587 |
| +0x3838, +0x4dd8, +0x6378, +0x7918 | point lists | four more 338-point lines within ±13 units of the centre, alternating sides (not edges): candidate AI racing lines / lane lines |
| +0x8eb8 | | the +0x3838 list repeated? (same first values) — TBD |
| +0xcf98 | zeros | TBD |
| +0x14f98 | `0x01` bytes | TBD (grid?) |
| +0x15e98 | directory | 11 pointers + `(src, dst)` upload pairs, e.g. `0x12b0cc → 0x7f3000` |

Road half-width is about 13 arcade units (point lists stay within 13 of the centre), i.e. road
width ≈ 26 units vs. the Saturn's 2.49 → unit ratio ≈ 10.4 (Phase 1's ICP fit said 8.4; the
width-based figure is the better one).

## Frame rate note

`-str N` ended runs at about 57.5 frames per emulated second (a 42 s run stopped at frame 2415),
so the Model 1 screen is not 60 Hz; trace windows must budget `frames / 57`.

## Runtime structure (from V60 instruction traces, 2026-10-30)

Work-RAM pointer block `0x501948..0x50197c` is filled at course load from the bank header
and per-course constants:

| RAM | value (Big Forest) | meaning |
|---|---|---|
| `0x501934` | 2 | data index (bank − 1): BB 0, AC 1, BF 2; bank switch at `0xfe416a` writes `((idx+1)<<4)|1` |
| `0x501940` | 0/1/2 | selected course (menu order BF/BB/AC) |
| `0x501948` | `0x2f2056` | **tile pointer table** (program ROM): u32 pointers to 16-byte object records `(poly_adr, tex_adr, size, 0)` |
| `0x501950` | `0x100028` | segment array in the bank (+0x28; entry k = `(2, k, road_point, 1\|66)`, 1092 entries; entry −1 at +0x20 holds the counts) |
| `0x501954/8` | 0x152 / 0x445 | road point count / segment count |
| `0x501960` | `0x102258` | table of `(ptr, count)` pairs for the five 338-point lines (+0x2258) |
| `0x50196c` | `0x10cf98` | **128×128 halfword collision map**, cell = `((x+1024)>>4) + 128*((z+1024)>>4)` (x low, z high; an earlier note had them swapped), value = cell id passed to TGP function `0x1b01` (bank +0xcf98..+0x14f98) |
| `0x501970` | `0x114f98` | byte table indexed by cell id (surface type, low nibble) |
| `0x50197c` | `0xfdb90b` | HUD course-map data (boot ROM, per course) |

- Display-list objects: `FF84A2(R0 = object list)` writes `[0x0b][matrix from TGP][type][tex][poly][5500]`
  per `(poly, tex, size)` triple until `poly == 0`. 47 calls/frame on Big Forest: 16 cars
  (`FEAD9A`, list from entity `+0xb0`), 12–13 **tiles** (`FF8450`: byte list at `0x501cc0` =
  `count, idx...`; each `idx` → `[0x501948](idx)` → record), fixed props and HUD pieces.
- Entities are 0x80-byte structs in RAMA at `0x407880` (131 live during a race): `+4` type,
  `+6` size, `+0xa` handler, `+0x18` object list, `+0x1e` xyz floats.
- Scenery (trees, stands) is baked into tiles (Phase 1); no separate placement table found so
  far: the 24-byte-record loader at `FFA7EC` reads the HUD-map descriptor list, not scenery.
- The TGP: collision/height queries go through the coprocessor with the cell id, so
  `copro_data` (TGP data ROMs) **does** hold per-course road geometry (spec decision 16 →
  MB86233 work is in scope for the converter; this is the biggest open item).

## Tile grid and visibility (2026-10-30)

- `0x501948` → per-course 256-entry pointer table (BF `0x2f2056`, BB `0x2f1856`, AC `0x2f1c56`,
  consecutive in program ROM). Object centroids show cell index = `z_cell*16 + x_cell`, cells ≈ 105 × 125
  units (BF uses x cells 5–11, z cells 1–9; 76 non-empty cells, 38 with ≥ 200 records).
- Per frame: TGP returns the car's cell; `0xff7d38..0xff7e1e` builds the visible index list at
  `0x501cc0` from a 25-byte neighbourhood table (`0xff7e1f`) with bitmaps at `0x501a80/aa0/ac0`;
  `0xff8450` draws them (12 in the sampled frame). 56 of Phase 1's 88 big tiles are not in this
  table (records at `0x2e4330..`, unreferenced from ROM data; one drawn via `0xff0d7d`): a second
  draw path, still to trace.
- Collision: `0xfed52b` computes cell = `((x+1024)>>4) + 128*((z+1024)>>4)` into the halfword map at
  bank +0xcf98 (`0x50196c`), and sends the id to TGP function 0x1b01; the result indexes the byte
  table at +0x14f98 (`0x501970`). So the TGP data ROMs carry per-course geometry.
- Decoders + golden round trip (header, five lines, segments, tile records) pass on all three courses:
  `vrtools/arcade/course.py`, `tests/test_course.py`.

## Not found in this phase

- Checkpoints / time extension; start grid (car table at boot `0xfcd395`, 0x20 bytes per car).
- Course-select assets. HUD course map descriptor at `0x50197c` (boot ROM) not decoded.
- The visibility loader at `0xffa7ec` (24-byte records: xyz floats, u16, u8 type, u32, object list) reads
  the list at `0x50197c`; its exact meaning is open (it ran 256 iterations, created 32 entities).
