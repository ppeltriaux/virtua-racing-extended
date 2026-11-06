# Model 1 Virtua Racing — course tables (V60 side)

Status: Phase 2 (M1), 2026-10-30. Decoders: `vrtools.arcade.course`. Evidence and
dead ends: `docs/spike/2026-11-arcade-course-tables.md`. Addresses are for the
MAME `vr` set; "window address" means a V60 address `0x10xxxx` inside the 1 MB
data-ROM window at `0x100000`.

## 1. Where a course lives

| Piece | Location | Size |
|---|---|---|
| Course bank (road, physics, graphics uploads) | data ROM bank = course data index + 1: Bay Bridge bank 1 (`RomSet.data[0x100000:]`), Acropolis bank 2, Big Forest bank 3; bank 0 is shared | ~180–220 KB of tables at the bank start, plus ~125 KB of graphics at bank +0xc0000 (BF, AC) |
| Tile pointer table (visible geometry grid) | program ROM: BB `0x2f1856`, AC `0x2f1c56`, BF `0x2f2056`; 256 × u32 | 1 KB each |
| Tile object records | program ROM `0x2e9980..0x2ec970` (16-byte records; the tables above point into it) | 256 records per course |
| Tile geometry | polygon ROM (Phase 1: world-space quad strips) | ~1.5 MB for Big Forest |
| Collision/height geometry | TGP data ROMs (`copro_data`): per-course quad lists addressed by the collision-map value | decoded, Phase 5 (`model1-tgp-collision.md`) |
| Entity spawn list (trackside objects, HUD minimap entity) | boot ROM, pointer in RAM `0x50197c` (BF `0xfdb90b`): 0x100 pointer slots to object lists | Phase 7 (§12) |

Selected course (menu order BF=0, BB=1, AC=2) is the byte at RAM `0x501940`; the
data index (bank − 1) is the byte at `0x501934`; the loader at `0xfe416a` writes
`((idx + 1) << 4) | 1` to `0xe00004`.

## 2. Course bank header (bank offset 0)

| offset | type | field | Big Forest |
|---|---|---|---|
| +0x00 | u32 win | graphics-upload directory | `0x115e98` |
| +0x04 | u32 win | segment array (entry 0 = counts) | `0x100020` |
| +0x08 | u32 win | pointer block: collision-map ptr, surface-table ptr, then the line table | `0x102250` |
| +0x0c, +0x10 | u32 win | pointer block + 4, + 8 | |
| +0x14..+0x1c | u32 win | centreline point list (×3) | `0x102298` |
| +0x20 | u16 | road point count | 338 |
| +0x24 | u16 | segment count (entries 1..n; Phase 2 read it as count + 1) | 1093 |
| +0x28 | | start of segment entry 1 (see §3) | |

Runtime copies: `0x501950` ← +0x04 + 8 (segment entry 1), `0x501954/8` ← counts,
`0x501960` ← pointer block + 8, `0x50196c` ← bank + 0xcf98 (collision map),
`0x501970` ← bank + 0x14f98 (surface table).

## 3. Segment array (+0x20, 8-byte entries)

Entry 0: `(road_points:u16, 0, segment_count:u16, 0)`. Entries 1..n:
`(2, index:u16 (0-based), road_point:u16, flag:u16)`. **Segment k is collision quad k**
(Big Forest: 1093 segments = its 1093 tarmac quads, which come first in the quad pool in
lap order). The car's lap position (`entity+0x30`, also `+0x150`) is the index of the
last tarmac quad it touched (surface kind 1, §5); the segment maps it to a road point.
Several consecutive segments map to the same road point (about 3 per point). Flag 1 is
plain road; **flag 66 marks the pit-lane quads** (Big Forest quads 30–59 beside the start
straight at lateral −33 and 1085–1088, the entry taper) — not a grid zone. Bay Bridge also
uses 2, 4, 16, 129 (unknown). Centreline points link back with `link >> 16` = segment index.

## 4. Road lines (pointer block + 8: **eight** `(ptr:u32 win, count:u32)` pairs; RAM `0x501960`)

**Eight** lists of `count` points, 16 bytes each: `x:f32, z:f32, heading:u32, link:u32`. The
pointer block addresses all eight (Phase 9 correction: the car setup `0xfe8ac1` reads pair `line` for each
car's AI line 0..7; converted banks wrote five pairs until Phase 9, so the seven cars on lines 5–7 read line 0's
first points as their pointer and spawned at the world origin); Bay Bridge's line 6 has 416 points, so its line
7 starts 32 bytes earlier than the stride. Each list is stored
as its `count` points **followed by its points 0..7 again with `heading | 0xc0000000`**
(wrap points), so the stride is `(count + 8) × 16`.

- List 0 (`0x102298`): **centreline**, spacing ≈ 10 units (median 10.1). Big Forest:
  338 points, x −197..326, z −711..587.
- `heading` high half = `−atan2(dx, dz)` in 1/16384 turn (the collision quad attribute's
  angle at a quarter of the resolution), **unwrapped along the lap** (Big Forest 56 → −16493,
  Bay Bridge 165 → −17942, Acropolis 16489 → 2; largest step between neighbours 778); the
  wrap points carry heading − one turn within a rounding unit (reads as `| 0xc0000000` on these
  clockwise laps; Bay Bridge's unaddressed lines 6–7 have their wrap block shifted by two points).
  **Low half = the pitch target** an opponent on that point takes (signed, 1/65536 turn; boot `0xfece55` moves the
  car's `+0x2a`, its pitch, positive climbing; Big Forest up to ±994). `link = segment << 16 | roll`: **the low half
  is the roll target** (`0xfece67` → `+0x2e`, the roll, negative = right side up; Big Forest up to ±3821 on its banked
  bends). Measured in Phase 16 by tilting every Alpine quad in the ROM (Phase 15 had the two the other way round);
  the converter writes the arc profile's slope and the slice normal's camber (`convert/road.attitude_words`).
- Lists 1–7: seven more lines, each the same point count, lateral offsets within ±13 units
  of the centre (medians −2..+1): hand-made **AI racing lines**; the car setup picks a line
  per car (`car table +0x14` → line index, `+0x18` → start road point).
- Road half-width ≈ 13 units at the centre (the start straight is 60 wide: pit lane +
  track); the Saturn road is 2.49 units wide, so **1 Saturn unit ≈ 10.4 arcade units**
  (the Phase 3 position fit says 11.7).
- Generator: `vrtools/convert/road.road_tables` (centreline + seven fixed-offset lines),
  `vrtools/arcade/bank.build_bank` (layout, wrap points, relocation into free space).

## 5. Collision map (+0xcf98) and surface table (+0x14f98)

128 × 128 halfwords; cell = `((int(x) + 1024) >> 4) + 128 * ((int(z) + 1024) >> 4)`
(float→int truncates toward zero; cells are 16 units). Value 0 = off-road; a non-zero
value is the **word offset of the cell's quad-index list inside the course's TGP list
block** (Big Forest: 1368 cells, lists stored consecutively so the ids ascend along the
track). The V60 passes it to TGP function `0x1b01` with the car position and reads back
the height and the index of the quad hit (`model1-tgp-collision.md`). The **surface table
at +0x14f98 holds one byte per collision quad** (`movz.bw [0x501970](quad)`): kind 1 tarmac
(the first 1093 quads on Big Forest; updates the lap position), 8 kerb zone, 2 grass, **5 wall**, 3 and others on
Bay Bridge; the table is one byte per quad (as long as the quad pool). The per-wheel kinds at entity `+0x142..148`
are `1 << kind` (no quad: 1; tarmac 2, grass 4, wall 0x20, kerb 0x100), written by the wheel routine `0xfed55e`
(a miss answers height −0.1 and kind 0). After the hit the V60 asks the TGP for the car's distances to the quad's
edges (command `0x1500`) and the quad's attribute (`0x1800`, the road direction it steers along).

**How the game stops a car** (Phase 22a, the V60 code at `0xfebc94..0xfec3d6`, measured on Big Forest and on a
converted course): a wall is a **step in the collision height**, not a surface kind.

- `0xfebe46`: the four wheels' heights (`0x501264` FL, `0x501260` FR, `0x50126c` RL, `0x501268` RR): front and rear
  more than 2.0 apart on either side, or left and right more than 1.2 apart at the front or the rear, run the wall
  response `0xfec003` with the car's own quad (`+0x17b`): a yaw kick towards that quad's road direction (`+0x12b`,
  about 1.5 × the angle off it), a spin timer (`+0x124` = 0x10), smoke (`+0x1aa`) and, over speed `+0x14` > 0x118,
  the crash animation (`+0x56` from the table at `0xfd3946`, sound `0xb01b`); the car slides along the step.
- `0xfebdbe`: the AND of the four kinds: all tarmac, nothing more; all wall or all off the collision (kind 0) →
  `0xfebf4a`, speed halved and the car put back on its last good quad (`+0x30`) over 10 frames (what a player sees as
  a reset); all grass → `0xfebf00` (grass handling); mixed, a wheel on wall or off the collision → `0xfec152` with
  that wheel's quad: within 22.5° of the quad's direction the wheels' movement is tested against its four edges
  (`0xfec3d7`) and a crossing moves the car back onto the edge and turns it along it (`0xfec2ac`, crash sound
  `0xc110`); further off, `0xfec003` as above.
- `0xfebc94`: while all four wheels are on tarmac the car's quad is remembered (`+0x1b6`); otherwise a counter
  (`0x50115c`) runs and past 0x80 counts the car is put back there (the off-course put-back: speed 0, the car glides
  back). The counter runs once per logic frame, every other video frame: 0x80 is 4.3 s (Pascal's Big Forest drive on
  the original set, on pure grass too).
- The step check `0xfebe46` runs only when no wheel is on a wall or off the collision; with one there, `0xfec152`
  decides, and within 22.5° its edge test (`0xfec3d7`) needs the wheel's move to cross one of the wall quad's edges:
  a wheel already inside the wall's outline (grass or tarmac under the wall, where the TGP keeps the nearer height)
  or crossing a run's end (`0xfec2ac` then slides it along the long edge, into the wall) ends with four wall wheels
  and the put-back `0xfebf4a` (converted courses, Phase 22a: `clip_at_walls`, `_join_wall_runs`).

A wall quad at the ground's height (as the converted courses had from Phase 16) only slows a car: Pascal's Diablo
car crossed a 12-unit strip at 1.36 → 1.27 units a frame, then left the collision and was put back. The converted
walls lay `WALL_STEP` (4) units from the ground's height for a while (Phase 22a); Phase 22c measured the original's
walls on Pascal's Big Forest drives: at the ground's height (a wall wheel 41.62 beside 41.05), the slide `0xfec2ac` keeping
the car off them, so a car never stands on four wall wheels. The step was a workaround for grass and tarmac under the
walls (no edge crossed); with them cut at the wall (`clip_at_walls`) the converted walls are back at the ground's height
(`WALL_STEP` 0): a step let a slow car mount the Oval's banked wall and the put-back (onto the car's own quad, the wall)
looped.

## 6. Tile grid (program ROM)

Per course, 256 pointers (`TILE_TABLE[index]`) to 16-byte records
`(poly_adr:u32 word index, tex_adr:u32, size:u32 records, 0)`. Cell index =
`z_cell * 16 + x_cell`; Big Forest uses x cells 5–11 and z cells 1–9 with cells of
about 105 × 125 units (object centroids: x ≈ −277 + 105·(xc−5), z ≈ −800 + 125·zc).
Each frame the TGP reports the car's cell; a 25-entry neighbourhood table at boot
ROM `0xff7e1f` plus visited-cell bitmaps (`0x501a80/a0/c0`) select ~12 cells, whose
indices are written as a byte list at `0x501cc0` and drawn by `0xff8450` through
`0xff84a2` with the camera matrix (tiles are world-space objects). Records with
`size == 0` are empty cells. 76 of 256 cells are used by Big Forest, 38 of them
with ≥ 200 records.

A second set of large objects (Phase 1 saw 56 more big tiles, records at
`0x2e4330..`) is drawn through entity call sites not yet traced (e.g. `0xff0d7d`);
see the discovery log.

## 7. Display list emission (per object)

`0xff84a2(R0 = list)`: for each `(poly, tex, size)` triple until `poly == 0`, emit
`0x0b` + 12 matrix words read from the TGP result FIFO, then
`type (entity+0x12, normally 1), tex, poly, 5500` as an `0x01` command. So the
per-object `size` in the record is **not** what the renderer sees; 5500 is a global
cap (`0x5011b0`).

## 8. Graphics uploads (header +0: directory)

The directory is a list of window pointers, one per upload phase (Big Forest: 10),
ending where the first pointed-to list begins (the pair lists sit inline after the
pointers). Only phase 0 is verified to be a pair list; later entries hold other
block formats (e.g. Big Forest's second entry is a palette block starting
`0x900c00, 0x140, data…`) and are kept opaque. A pair list is `(src:u32 win,
dst:u32)` pairs terminated by `src == 0`; the loader (`0xffe583`, called with
`directory[phase]`) copies
`(u32 at src) << 4` halfwords from `src` to `dst`. Destinations are tile RAM
(`0x7e0000`, `0x7f3000`) and the palette (`0x900c00`): the race-time 2D backdrop
and HUD graphics. Decoders: `gfx_directory`, `gfx_uploads(rs, e, phase)`.

## 9. Entities (RAMA `0x407880`, 0x80 bytes each)

`+0 flags, +4 type, +6 size, +0xa handler, +0x12 draw type, +0x18 object list,
+0x1e x, +0x22 y, +0x26 z (floats), +0x30 segment index, +0xa6 road point,
+0xb0 car object list, +0xdd road-line pointer`. 131 entities during a Big Forest race
(16 cars, props, HUD). The player's car is the 0x280-byte entity at RAMA `0x400d00`:
`+0x36` heading, `+0xeb` road heading at the car, `+0x150` lap-position quad, `+0x191`
sub-state, `+0x1ab` damage flags (select the pit work), `+0x1bf` pit stops left (2).

## 10. What the converter must produce for a new course

1. A course bank (`vrtools/arcade/bank.build_bank`, done in Phase 6 on a template bank):
   header counts, segment array (one segment per tarmac quad), eight road lines with wrap
   points, pointer block, collision map (128×128 cells with list offsets), surface table
   (one byte per quad); inherited from the template for now: the graphics-upload directory
   (backdrop tiles, palette) and the table at +0x8eb8.
2. A 256-entry tile pointer table and up to 256 object records in program ROM, with
   the tile geometry in polygon ROM (world-space quad strips).
3. TGP collision data: quads, per-cell lists and a slot entry in `copro_data`
   (`model1-tgp-collision.md` §6), with the collision map above carrying the list offsets.
4. An entry in the ten-course directory (§13): bank, header base, TGP slot, template, tile table, spawn
   list, pit quad, panels, name (Phase 7).

Units: arcade = −11.7 × Saturn on both axes (Phase 3 position fit; width-based estimates 10–12.5); free space: polygon ROM 3.8 MB, data ROM 2.4 MB
(bank holes), program ROM ~160 KB.

### 10.1 Colour pipeline (Phase 4, done for item 2)

Each polygon record carries a colour-table index `tex_adr` (advanced by flag
0x1000); the table is the 1 MB program ROM read verbatim (entry *i* at ROM byte
`2*(i - 0x40000)`), and its 16-bit entry selects palette entry
`0x1000 | (entry & 0x3ff)` (bit 0x400 = bright) from the course's palette RAM
(xBGR555, loaded from program ROM — Big Forest's at 0x2ec980). Unused runs of
0xFFFF entries below the tile records (0x7c6b8 with 47,432 entries, 0x98c21
with 29,663) are free. The converter therefore, per cell: picks the nearest
course-palette entry for each face colour (`convert.geometry.assign_colours`),
emits one table entry per distinct palette index, sorts the quads by index so
`tex_adr` only advances, and writes the entries into the free run
(`arcade.patch.write_colour_entries`). Big Forest's whole Saturn scenery used
1,182 entries. Details: `docs/formats/model1-colours.md`.

## 11. Not found / out of scope in this phase

- Checkpoints and the time-extension table; start grid (car table at boot ROM
  `0xfcd395`, 0x20 bytes per car, only partially read).
- Course-select screen assets (names, map panels).
- The exact rule that maps the car position to a tile cell (done by the TGP; the
  collision side is now known, see `model1-tgp-collision.md`).

## 12. Per-course data in the boot ROM (Phase 6)

- **Pit-entry table `0xfe8e0c`**: one halfword per course-data slot (`[0x501934]`: Bay Bridge 0,
  Acropolis 1, Big Forest 2) = the collision quad index at which the player enters the pit
  sequence; `0xffff` = no pit lane. Values: `0xffff, 28, 30`. The player handler at
  `0xfe8e88` enters the pit (`jsr 0xff222f`, handler `0xff2345`, PIT WORK) when `+0x1bf` is
  non-zero, the lap-position quad `+0x150` equals the table value or that + 1 (Phase 22j: the converter puts a lane quad
  or a duplicate of the entry quad at + 1; the Saturn's lane and road slices alternate in the list), and the car
  heads along the road (|`+0x36` − `+0xeb`| < 0x4000). `vrtools/arcade/course.pit_entry_table`,
  `vrtools/arcade/patch.patch_pit_entry`.
- **Pit box** (Phase 22i): the pit sequence (`0xff222f` enters it; handler `0xff2345` runs the state table `0xff2161`,
  17 states: the crew's walk-on, the work chosen by the damage flags, the release) drives the car with its own autopilot
  (`0xfe968d`, single-cab; `0xfe98f6` the linked-play variant by sub-state `+0x1c6`): each frame it turns the car's
  heading `+0x6a` by at most 0x200 (2.8°) towards an aim point: 10 units short of the box along −z until the car's z
  reaches it, then the box itself (TGP `0x800000` is a subtract; `0x7800000` the bearing; `0xE800000`/`0xF000000`
  s·sin a / s·cos a with a in 1/65536 turn; `0` add: probed from Lua on 4 Nov), scales the speed by the distance (200
  above 100 units) and parks at 0.2 units: `0xfe98c7` puts the car on the point, heading 0 (+z), and sets flag 7 of
  `+0`. The short aim lines the car up on a +z lane; on a lane along another axis the box lies aside and the car, at
  0.4 units a frame and 2.8° a frame (turning radius 8), orbits it (Alpine, rec74), so `pitaim` (`0xfe96a4`) lays the
  short aim along the entry's box heading. The point comes from `0xff4061` by data index `[0x501934]`: nothing
  for Bay Bridge, Acropolis's table `0xff40b1` (x −346.42, y 3.70, z −58.96, then seven z values per cabinet for
  linked play), Big Forest's `0xff40d9` (−230.38, 30.00, −269.57, …); y is the tarmac's height. The crew (entities 0–5
  at `[0x501350]`, 0x280 bytes each, spawned by `0xff27d8`) stands at fixed world-axis offsets from the same point.
  `0xff4061` also places the PIT START grid (`0xfc005f`, `0xff21a5`, `0xff4165`), so it stays as it is: the autopilot's
  six calls and the four crew spawns' (`0xff27d8 0xff2d69 0xff33c7 0xff3a1b`, one per pit work) go to the directory's
  `pitbox` / `pitboxcrew`, and the park to `pitpark` (x, y, z and a heading after the entry's map record, +16;
  `collision.pit_box`). The 16-bit heading h gives the direction (−sin h, cos h),
  1/65536 of a turn (Alpine's drive log, rec70). The race start grants the pit stops (`+0x1bf`, `0xfe8bd8`): none for
  Bay Bridge's data index, 5 in linked play, else 2 unless `[0x40d826]` ≥ 2; `pitstops` decides by the entry's pit quad.
- **Start grid**: absolute positions (player at (−230, −270) heading +z on Big Forest,
  i.e. road point 13 at lateral −37); converted courses are placed to meet it
  (`vrtools/convert/place.py`). The grid table itself is still to be located (M4).
- **Entity spawn lists** `0xfda543[idx]` → `0xfda54f / 0xfdb39f / 0xfdb90b` (RAM `0x50197c`): 0x100 pointer
  slots, each to a list `(count, then per object: x, y, z floats, +0x2c halfword, type byte, handler, object
  list)` read by `0xffa7ec` at course load. The HUD minimap is one of these entities (drawn from the road lines),
  so a converted course keeps its host's list. (Phase 6's "HUD map polyline" reading was wrong.) The minimap's
  outline is a fixed polygon-ROM object per original (object lists `0x2e0040` Big Forest, `0x2e0050` Bay Bridge,
  `0x2e0060` Acropolis: poly, tex, size, 0), chosen by data index at boot `0xfeac10` (`mov.w FEAC1B[PC](R0),
  18[R25]`, table `0xfeac1b`); Phase 22b routes that site through the directory's `mapobj` (per-entry outline).
- Per-course tables at `0xfcf199` and `0xfcd66d` of unknown format (`docs/spike/2026-11-m3-recon.md` §6).
- Layout note: the two boot chips (`epr-14878a.4`, `epr-14879a.5`) are flat and consecutive
  at `0xfc0000` / `0xfe0000` (`ROM_LOAD`), unlike the byte-interleaved program and data pairs.

## 13. Ten-course directory and select screen (Phase 7)

- **Directory** (`vrtools/arcade/directory.py`, program ROM `0x278d70`, inside unused colour-table space that
  `colours.RESERVED_CODE` keeps the colour allocator out of): ten 24-byte *select* records in the original
  layout of `0xfc35c7` (`x:f32, y:f32, +8 layer-A map, +0xc/+0x10 ints, +0x14 template`), ten 64-byte *load*
  records (`+0 bank, +1 TGP slot, +2 template, +3 label, +4 header base (window), +8 tile table, +0xc spawn list,
  +0x10 pit quad (0xfffe = none), +0x14 layer-B map, +0x18 art, +0x1c name[14]`), nine 32-bit band thresholds,
  the three slots' tile-RAM destinations for layers A and B, an empty spawn list (0x100 zero words) and the V60
  routines (`v60asm.py`, absolute addressing only). The original per-course lookups by data index
  (`0xfcd5b9/c5/d1`, `0xfcf16d`) stay, applied to the entry's **template**, which also becomes `[0x501934]`.
- **Code sites** (`course.py`): loader `0xfe48ed` (0xb7, `jmp`), bank switches `0xfe1d37 0xfe2160 0xfe2b07
  0xfe2cf7 0xfe415b` (0x16 each, pattern-checked, `jsr`), pit check `0xfe8e8f` (0xd), select-table displacements
  `0xfc270b 0xfc28a3`, wheel zones `0xfc26df` (0x1b), panel blits `0xfc3622` (0x79) and, from Phase 9, the car
  setup's table choice `0xfe8a91` (0x16, pattern-checked, `jsr` → the `cars` routine: R10 = the entry's car table).
- **Race fields** (Phase 9): load record `+0x2c race` (program-ROM address of the entry's race blob, 0 = the
  template's original tables) and `+0x30 laps` (0 = the game's setting). The loader serves `0x501968` from the
  blob's variant table (same flag tests as the original: `0x40dc8c`, then `0x501105`, by level `0x501110`),
  `0x50195c` from the blob's checkpoint record and `0x5011a4` from `laps`. Race blob layout (`race.py`): 3 × 16-byte
  variant tables (four record pointers), 12 × 96-byte time records, a 96-byte checkpoint record (count + up to
  23 points), the 512-byte car table; `RACE_BLOB_BYTES` per course after the seven tile tables
  (`tencourse.race_blob_address`), then the per-course spawn lists (`spawn_list_address`, 0x400 slots + records). `0xfc369b` (compare
  `0x501940`/`0x501942`, re-colour) is unreferenced dead code.
- **Presentation fields** (Phase 14, `docs/spike/2026-11-presentation-recon.md`): load record `+0x34 map_tx` (float,
  the HUD map section's screen translate x, the game's 149.0), `+0x38 map_cross` (u32 byte offset of the player's
  cross tile cell, 0 = the game's cell (48, 21)), `+0x3c off_course` (u32 logic frames with a wheel off the tarmac
  before the car is put back on the road, the game's 128). The loader copies them to `0x50231c` (the game's RAM copy
  of the map record `0xff9e9a`, made once at boot and read by the display-list writer `0xff84f8` every frame),
  `0x502328` and `0x50232c` (the never-touched padding after that record). Two more boot sites: `0xfeabf5` (7 bytes,
  `movea.w #700AE0, R1` before the cross pattern draw → `jsr` the `cross` routine: R1 = 0x700ae0 + [0x502328]) and
  `0xfebcdf` (12 bytes, `cmp.w #80, 50115C[PC]` → `cmp.w 50232C, 50115C`: the limit from RAM). The map is drawn
  car-centred, heading up, at a fixed 1/1250 scale; anticlockwise courses get `map_tx` 237.0 and `map_cross` 22
  (11 cells right) so the outline hangs in the same right-hand box as the clockwise originals'; converted courses get
  `off_course` 40.
- **Select screen** (`select.py`): wheel value `R10 = ([0x501060] + [0x50106c]) >> 1`, −127..127; ten bands;
  window of three entries (`first = clamp(index − 1, 0, 7)`); the blitter `0xff9436` takes R0 = map, R1 = tile
  RAM; slot destinations `0x704088 + 0x26·s` (layer A) and `0x700088 + 0x26·s` (layer B). The text printer
  `0xfc402a` prints the big labels; `0xfc2880` builds the cursor frame at the entry's select-record x/y.
- **Panel maps** (`panel.py`): header `base:u16, mode:u16, rows:u32, cols:u32` (16 × 21 tiles, 128 × 168 px
  portrait) then byte (mode 0, + base = character page) or halfword (mode 1) indices; the blitter adds the base in
  16 bits. Originals: layer A `0x1e0000 / 0x1e015c / 0x1e02b8` (BF, BB, AC; pages 0x30–0x32, overlay), layer B
  `0x1e0414 / 0x1e06c0 / 0x1e096c` (words 0x8000 | 0x3300.., the picture). Tile word: bits 0–13 character,
  bits 7–14 palette (= character >> 7: a 128-character block shares a 16-colour palette), bit 15 the
  high-priority category. Characters: 8 × 8 × 4 bpp, 32 bytes, pixel pairs in byte-swapped halfwords, high nibble
  first; colour 0 transparent.
- **Uploads** (bank 0, mapped on the select screen): directory at bank +0 — phase 0 pair list, then 8-byte
  entries `(pair list, palette block)` per screen; the select screen's is the first (`+0x4a324`): nine
  `(src, dst)` pairs (count word at `src` = 32-byte units; `0x7e0000` ← chars 0x3000..) and a palette block
  `(dst 0x900c00, count 0x1d0 halfwords, data, then dst 0 terminator)` read by `0xffe5ac`. Free on the select
  screen: characters 0x3e80..0x3fff with palettes 0x7d..0x7f, the overlay pages' unuploaded tails, bank 0's tail
  from +0xf3000 (52 KB).

- **Pictures** (Phase 21, `picture.py`, `select.py`; recon `docs/spike/2026-11-phase21-select-previews-recon.md`): the
  boot loads character blocks 2-94 once (off-limits); each screen loads blocks 96-127 (the select screen 96-124).
  Slot s owns characters `0x3300 + 0x180·s` (blocks 102+3s, the originals' picture blocks) and palettes `0x900cc0 +
  0x60·s`. A ten-entry table (`directory_layout()["pictures"]`) points at 36-byte picture records: `chars, counts (n0 |
  n1<<8 | n2<<16), normal, chosen, grey, map (336 local indices), a_dst, a_chosen, a_grey`. `draw` calls `picture` per
  slot: the three character runs to the slot's blocks, the normal palettes, the tile words `0x8000 | (first + local)`
  at the slot's layer-B rows (pitch 0x80). START (`0xfc27d6`, by menu index 0 BF / 1 BB / 2 AC: chosen sets
  `0xfc374d`/`0xfc3825`, the others' grey sets `0xfc3951`/`0xfc3a1d`, destinations `0xfc3741`/`0xfc3819`) jumps to
  `start`: chosen palettes for the slot showing `[0x501940]`, grey for the others (an original's layer-A set too), then
  the game's cursor frame `0xfc2880`.

## 14. Race tables in the boot ROM (M6 recon, `docs/spike/2026-11-m6-recon.md`)

- **Race clock** `0x50116c` (s32, 1/32 s on the HUD, decremented every other frame); initial value and the
  per-checkpoint extensions come from a **time record** (24 × u32: `initial, ext[1..23]`) selected by the loader:
  `0xfcd5b9` / `0xfcd5c5` (`[0x40dc8c] ≠ 0`) / `0xfcd5d1` (`[0x501105]`, linked) `[data index]` → four record
  pointers by level `[0x501110]`; the chosen record's address is kept at `0x501968`. The k-th checkpoint of the
  race adds `ext[k]` (`0xfea3c7`). Values: `vrtools/arcade/race.py`.
- **Checkpoints** `0xfcf16d[data index]` → `count:u32, points[count]:u32` (road-point indices on line 0; entry 0 =
  the start line), kept at `0x50195c`: BB `(3, 0, 112, 221)`, AC `(3, 0, 210, 423)`, BF `(3, 0, 120, 230)`.
  Firing (`0xfea1c6`, Phase 22m read): on a frame where the car's road point `+0xa6` has moved forward by 1..29
  points over the previous frame's (`+0x16f`), entries 1..count−1 are walked and one fires (flag bit 0x15, counter
  `+0x16e`, the extension) when both previous road points (`+0x16f`, and `+0x171` = the last forward step's) are
  below it and the new one is at or past it. No exact match: a credit that skips the checkpoint's point still
  fires. A step of 30 points or more skips the walk and leaves `+0x171` behind, so a car that jumps across a
  checkpoint (a put-back, a deck below the road) never gets it.
- **Laps** `0x5011a4` = 5 (`0xfe10fb`), 4 with `[0x40dc8c]`, 20 linked; set at game start, not per course.
- **Car table** `0xfcd395` (`0xfcd195` with `[0x40dc8c]`): 16 × 0x20 — five model pointers, road-line index
  (u32), start road point (u32), performance (f32; the player 2.847, opponents 1.736..2.786); car i starts at
  road point `start_pt − 3 × (16 − i)`; read at `0xfe8a91`.
- **Entity spawn records** (§12): `x y z :f32, yaw:u16, type:u8, pad, handler:u32, objlist:u32`; `0xffcb59` =
  HUD minimap, `0xffb07f` = start gantry, `0xffb08a/0xffb095/0xffb0a0/0xffb0ab` = checkpoint gantries,
  `0xffc17e` = grid boards; the rest are the course's props.

## 15. How an opponent follows its road line (Phase 10 recon, boot `0xfec69d..0xfec7a7`)

- Each car keeps a **line cursor** `entity+0xe1` (byte offset into its line: 16 per point), its **target**
  `+0x1b1` = cursor + 2 points, its line pointer `+0xdd` and count `+0xe3` (from the pointer block's pair `line`,
  §4), and its **road point** `+0xa6` = `segments[lap-position quad].road_point` (`0xfe94b3`; the lap-position
  quad is the last tarmac quad the TGP reported under the car).
- Every frame: read the cursor's line point; `link >> 16` names a segment; if that segment's `road_point` ≤ the
  car's road point, advance the cursor one point (wrapping at `count`). So the cursor keeps pace with the car only
  when every line point names a segment whose road point the car has reached — on the originals every road point
  owns one to eight segments and `link >> 16` is the first of them, so the cursor advances as the car passes each
  point. A line point naming a segment *ahead* of the car (our Phase 6–9 tables: the first segment at or after the
  point, with merged quads leaving many points without a segment) stalls the cursor, the target drops behind the
  car and it crawls; a car whose road point jumps past the line's last points (a long merged quad near the start
  line) strands the cursor there for good.
- Speed: the working performance `+0x48` is the car's base `+0x3c` unless the heading (high half, `+0xa` of the
  point) **8 points beyond the target** differs from the target's by more than `0x1000/4` units of 1/16384 turn,
  in which case the TGP computes a reduced value (`0x388cccd1 × (4|Δ| − 0x1000)` taken off 2.847); a cursor more
  than three points behind the target gives the full 2.847. Reads run up to 10 points past the cursor: the eight
  wrap points and the next line's first two points.
- The line point's low halves (`heading & 0xffff`, `link & 0xffff`) are not read by this routine; the TGP gets the
  car's own state, not the line.

## 16. Ranking, lanes and the brake for the car ahead (Phase 11 recon, boot `0xfea597`, `0xfec7ab..0xfeca85`)

- **Ranking** (`0xfea597..0xfea680`): the cars are sorted by road point (`+0xa6`), ties by the previous rank
  (`+0x123`); each car keeps its ranking neighbours, `+0x198` (behind) and `+0x19c` (ahead), and its rank in `+0x123`.
- **Lanes**: the originals pack **eight segments per road point** on some stretches (Big Forest points 79–118 and
  231–293, Acropolis 350–395; Bay Bridge uses two or three per point on 91 points): eight narrow collision quads
  side by side across the road (Big Forest point 80: lateral −5..24 in 3.5-unit lanes), consecutive in the segment
  array. A car's lane is its lap-position quad's index within the group (`& 7`).
- **Brake / pass** (`0xfec7ab`): for the car ranked ahead (the player's shadow entity `0x40c900` when it is the
  player) the TGP returns the distance (command `0x2180`); nothing happens beyond **7 units**. Within it, the
  code tests whether the target line point's segment heads a lane group (the next seven segments' road points
  sum to a multiple of this one's, remainder ≤ 7) and, if so, compares the two cars' lanes (`+0x30` lap-position
  quad − group base, `& 7`, × 3) to decide a lane change (command `0x0c00` reads the lane quad's geometry);
  otherwise a fallback compares the two cars' speeds (`+0xf5`). With one merged quad per stretch (ours), two cars
  in the same quad report the same road point, the ranking can put the physically rear car ahead, and each
  brakes for the other within 7 units: the parked pairs of Phase 10.

## 17. Ranking tables (Phase 22r recon, boot `0xfc3b49..0xfc4300`)

- Three best-time tables in the battery RAM at `0x40e000`, `0x40e240`, `0x40e480` (0x240 bytes each: 24 entries of
  24 bytes — `rank:u32, time:u32` in 1/32 s, `0:u32`, `-1:u32`, `time:u32` again, `name:3 chars + NUL`), by the
  course's data index (Bay Bridge, Acropolis, Big Forest). A slot word per table at `0x40e6c0 / 0x40e6c4 / 0x40e6cc`
  (`0x40e6c8` unused) holds the table base; the insert (`0xfc419c..0xfc4207`, shifting entries down) writes the new
  entry's address into it. The magic "S-RAM CHECK OK !!" lives at `0x40e6d0` (compared and, if missing, copied by
  `0xfe69f0`, which then calls the initialiser).
- Setter `0xfc4208` (callers `0xfc40e8` at the race's end with R0 = [0x501934] and `0xfc4226` for the attract page;
  `0xfc3c3a`): `and.w #3, R0`, then the two 3-entry tables `0xfc4cd5` (bases) and `0xfc4ce1` (slots) indexed by R0
  into `0x5018f0` and `0x501918`. The ranking display `0xfc3cff..0xfc3e9f` reads `[0x501918]` for the slot, `[0x5018f0]`
  for the entries (page `36[R25]` × 0x18), prints with `0xffe848 / 0xffe8fb / 0xffe74d`, and picks the title by
  `[0x501934]` through the jump table `0xfc3db6`.
- Initialiser `0xfc3b49`: R22 = `0xfcd5b9` (normal) or `0xfcd5c5` (operator flag `0x40dc8c`), R21 = `0xfcf16d`
  (checkpoint records), R23 = `0xfc3c1b` ((defaults `0xfc4dc0`, table) pairs), 3 iterations: the level-0 record's
  first 5 × [checkpoints] words summed, divided by 1920 (a minute in 1/32 s) and rounded up → the first entry's time;
  24 entries from the defaults (rank byte, step byte, name) stepping 0xa0 (5 s); then the three slot stores.
- `0x501934` (the data index) is written only at `0xfc270f` from the select record's byte +0x14 (`0xfc35c7 + 0x18·entry`;
  our ten-entry table since Phase 7); the game compares it with 1 in the player handler (`0xfe1775`) and at the race
  start (`0xfc0bf2`): Bay Bridge-only behaviour, which is why the converted courses keep their template's value and
  carry the ranking id separately (`ranking.py`).
- The boot's work-RAM clear `0xfe0016`: `movcfu.h` 0x7000 zero halfwords from `0x400000` — everything below `0x40e000`
  is work RAM (the entity pool at `0x400d00`); only `0x40e000..0x40ffff` persists. In that part the bookkeeping lives at
  `0x40e800 / 0x40e900`, a record at `0x40f000`, the stack at `0x40ff00`; `0x40ea00..0x40f000` and `0x40f100..0x40fe00`
  are 0xff since the factory and untouched through boot, attract, coin-up and a race (Phase 22r's taps) — the converted
  courses' ranking tables live there. (Work RAM that is never non-zero is still read as zeros by the race: a table placed
  at `0x40c940` hung the race start.)
