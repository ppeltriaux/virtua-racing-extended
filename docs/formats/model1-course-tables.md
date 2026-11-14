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

**The frame's record budget** (Phase 26 stage 2 fix wave, read in the boot listing; measured peaks in
`docs/spike/2026-11-phase26-stage2-findings.md` §11.7):
- `0x5011b0` is set at boot: `0xfe11bd mov.w #157C, 5011B0` (5 500), or `0xfe11d3 mov.w #1388, 5011B0`
  (5 000) when the flag `0x501a35` is 0, which `0xfe11b5` clears when the byte at `0xb00001` reads 0
  (not identified; 5 500 in every run measured).
- Both emitter entries, `0xff848a` (type 0x11) and `0xff84a2` (type 1), start with
  `cmp.w 5011B0, 5011A0; bgt FF8582` (an `rsr`): a list is skipped whole when the frame's count
  `0x5011a0` is already above the budget. Otherwise every triple is emitted and its `size` added to
  `0x5011a0` (`0xff854c`). The single-object emitter `0xff8583..0xff863b` adds at `0xff861a`, untested.
  So the count can end above 5 500: the list that crosses it is drawn whole, every later list that frame
  is not.
- In the character draw routine, an object whose flag word has bit 0x1a set (`0xff5d87 test1 #1A, 0[R25]`,
  `0xff5d90 bne FF5E33`) is emitted at `0xff5e33..0xff5e48` only while the count is at most
  `[0x5011b0] − 0x96` (150). The start figures (flag words 0x10000000 / 0x90000000 / 0xd0000000, bit
  0x1a clear) take `0xff5d93..0xff5e30` instead (visible-cell test, root pushes), where no budget test was found.
- The word each `0x01` command carries is `[0x5011b0]` itself (`0xff8571`, `0xff862c`); a record's
  `size` only adds to the frame's count, its share of the per-frame budget.

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
  Every one of these routines reads the served record through `entry`, so a reverse variant's own pit quad and box (Phase 26
  stage 4) work unchanged; the crew spawns and a reverse race: §20.
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
  +0x10 pit quad (0xfffe = none), +0x14 layer-B map, +0x18 art, +0x1c name[14]`; since Phase 26 stage 3 the name is
  NUL-padded, at most 13 letters: `hudname` prints it in the race HUD), nine 32-bit band thresholds,
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

- **Reverse variants** (Phase 26 stages 1 and 2, `directory.py`; measurements in `docs/spike/2026-11-phase26-stage1-findings.md`
  and `docs/spike/2026-11-phase26-stage2-findings.md`). An entry may carry a variant: the same course raced the other way round on
  its own road tables over the entry's collision.
  - **The reverse table** (`directory_layout()["reverse"]`) is ten u32 right after the maps table: per entry, the
    program-ROM address of its variant's load record (`ReverseRecord.at`), or 0 for none. In stage 1 only entry 6
    (Metropolis) had a variant; since stage 2 the seven converted courses (entries 3-9) each have one and the three
    originals none.
  - **A variant's records.**
    - Its 64-byte load record (the layout above) is at `at`. Its maps record is at `at + maps_offset()`, where
      `maps_offset()` = maps − load = 1 804. So the routines that reach a maps record at R8 + `maps_offset()` read a
      variant's as they read an entry's.
    - It has no select record: the variant takes its entry's `panel_map`.
    - `_check` requires the entry's bank, TGP slot and template, `at` 4-aligned and no nested variant. Until stage 4 it also
      required no pit (`pit_quad` None); since stage 4 a variant may carry a pit quad together with a box, never one without the
      other (§20). `install_directory` writes the records only onto erased program ROM outside the directory image.
    - The variant's header names its own segment array, pointer block and eight lines, but the entry's collision map,
      surface table and backdrop directory (`blob.build_variant_blob`).
    - It has its own race blob (`race`). `map_tx`/`map_cross` follow the reversed lap's interior side.
    - Stage 1 put the records and the race blob in one annex of `CODE_FREE` past the directory image
      (`tencourse.reverse_annex`): load records 64 bytes apart, their maps records 1 804 on, race blobs from the next
      16-byte boundary. Metropolis: load 0x28e810, maps 0x28ef1c, race 0x28ef60; tables at 0x18acd0 in bank 2.
  - **The annex's home since stage 2** (plan D1, recon §1). `reverse_annex` keeps that layout and takes the first erased run
    that holds all the variants, `ANNEX_MARGIN` bytes in from its ends, over `tencourse.annex_regions()` in order: the code
    area past the directory image (7 924 erased bytes in 8 runs on the stage 1 build, the longest 1 792: one variant, not seven), then the
    colour-table run 0x2b1842..0x2c0000. Seven variants need 14 912 bytes; they land in the colour run's tail: load records
    0x2b90c0 (64 bytes apart), maps records 0x2b97cc, race blobs 0x2b9990, end 0x2bcb00, 13 568 bytes to 0x2c0000 (13 552 after
    the margin). None of it may sit in the data window (the bank byte is read before the bank is mapped; the race pointers outlive
    bank switches). Why the tail is safe:
    - it is erased in the original (59 326 bytes);
    - every other writer of the run comes first and stops short of it: `build_all`'s colour words (to 0x2b6698, the highest
      colour entry 0x9b34b) and the select pictures (to 0x2b90b0). `reverse_annex` runs after both;
    - no object record's colour range reaches it: `tencourse.max_colour_entry` (the highest tex + tex advance over the
      converted courses' tile tables) is 0x9b34b, the annex's first halfword is entry 0x9c860
      (`test_the_annex_lies_in_a_vetted_region_past_every_colour`);
    - its only reader outside a reverse race is the boot's colour-table upload, PC 0xfe6b64 (128 chunks of 0x1000
      halfwords from 0x200000: the whole program ROM once, before frame 268). In a reverse race the game reads the served
      variant's own load record, maps record and race blob, nothing else in the span; on the select screen, with the flag
      set, `gfx` also reads the header word (load record +4..+7) of each variant whose entry the wheel passes over
      (`test_only_the_colour_upload_and_the_served_variant_read_the_annex`; recon `rom/taps.py`).
    - Not established: the service-mode ROM test (string at 0xfc7ea9) on any patched set.
  - **Stored lines behind eight pointers** (plan D2, `blob.build_variant_blob(..., pairs=)`). The pointer block's eight
    (pointer, count) pairs are read independently, so several may name one stored line. A variant's blob stores each
    distinct line of `pairs` once, in order of first use; pair k names line `pairs[k]` of the reversed tables. `pairs[0]`
    must be 0 (the centreline: the header's line and the player's). Alpine and Diablo Canyon store all eight
    (`(0, 1, ..., 7)`); Metropolis, since the owner's drive, six (`tencourse.METROPOLIS_PAIRS = (0, 7, 2, 3, 5, 5, 6, 7)`: the
    cars of the ±8 lines on the ±5 lines). The four bank-1 courses (Amazon Falls, Pacific Coast, Surfers Oval, Surfers Road) store three,
    `tencourse.BANK_ONE_PAIRS = (0, 7, 7, 5, 5, 5, 5, 7)`: the centreline for the player, the −5 line for cars 1-4 and 13-15
    (7 cars), the +5 line for cars 5-12 (8 cars). Their variants' car tables change only the start points
    (`tencourse.BANK_ONE_GRID`, after the owner's drive): the +5 line's cars on reverse points 1, 3, ..., 15, the −5 line's on
    2, 4, ..., 14, so no two cars of one stored line stand nose to tail on the grid; every other car table is the normal one.
    Bank 1 keeps one free run of 13 488 bytes
    (eight lines would need 227 888 against 113 380 free; `tests/test_tencourse.py`'s Phase 18b room check is 13 000 bytes
    for bank 1, 16 KiB for banks 2 and 3). The normal blob and the variant share one builder (`blob._road_part`, plan D3).
  - **The lap total** (plan D4, `race.time_records_for(..., lap_total=)`). A variant's race blob has the normal record's
    initial clock; its extensions are scaled by one factor so that the first lap's sum (`race.lap_total`: the first
    `len(checkpoints)` extensions) equals the normal record's. Where the reversed sectors are the normal ones in another order
    the factor is 1 and the record is the unscaled one. The variant's checkpoints are the normal lap's renumbered,
    (n − g) mod n, less any renumbered point p with 0 < p < `GATE_START_GAP` (`reverse.reverse_checkpoints`; stage 3 Task 8,
    Pascal's choice of 13 Nov). On six courses the reversed sectors are the normal ones in another order and the factor is 1.
    On Diablo Canyon the START gate, 36 points after the reverse line, is no reverse checkpoint: three sectors, level 0's
    reverse extensions 432, 283, 460 (a lap of 1 175 against the normal 1 176). Between stage 2's drive and stage 3's it
    fired (the rule had no drop): 200, 306, 255, 415, the normal 415, 255, 306, 200 in reverse order.
  - **The start spot** (plan D5 as narrowed in stage 2 Task 6, `reverse.reverse_segments`). The reversed walk credits each
    tarmac quad by its forward-rear edge. A quad the walk credits n − 1 that holds the reverse start spot (forward point 0,
    edges included within `SEAM_OVERLAP`) is credited 0, unless that would leave no tarmac quad credited n − 1 that holds a
    point of the reversed centreline before the line (from reversed point n − 1 to the spot): an opponent's line cursor
    wraps only when the car has been credited n − 1 before the line. Applied on Alpine and Amazon Falls (quad 0 each);
    withheld on Surfers Oval and Surfers Road, where quad 0 is the road's only n − 1 quad (credited 0, the opponents' cursors
    stayed at n − 1 after the first lap and the field stopped at the line); nothing to change on Diablo Canyon, Metropolis
    and Pacific Coast. On the two Surfers courses the quad under the spot is credited n − 1 and the player's road point still
    reads 0 at the first race frame (measured, not explained).
  - **`startbit`** (20 bytes, after `dirattr`; plan D6): `cmp.b #0, 502294; bne done; set1 #1E, 0[R0]; done: rsr` (the
    `set1` is the original's own 9 bytes). Boot site 0xfe41d6 (the 9-byte `set1 #1E, 0[R0]`, mode 0x11's set of the
    race-start task's bit 0x1e for data index 2 with `[0x40d826]` < 2, after the loader has written the flag back) becomes
    `jsr startbit` + nops. With the flag 0 the Big Forest template keeps the crew ("PIT START") start; reverse Alpine takes
    the standing grid start of the other six: the variant's car table, the READY lights, mode 0x14 at load + 264 frames. R0
    is kept; the flags after the site are not read.
  - **`figures`** (178 bytes, after `startbit`; plan D7's first way, Pascal's choice after the drive): the end of the start
    figures' placement in the race-start task (data index 1: the Acropolis template's Metropolis and Diablo Canyon),
    0xfc0ea5..0xfc0eb3 (`clr1 #1E, 0[R19]; pop R19; br FC0EEC`, 14 bytes; no branch lands inside it), becomes `jmp figures`
    + nops. The routine re-emits the two instructions, then `cmp.b #0, 502294; be done`; with the flag set it pushes R0-R3
    and, for pool objects 0-2 of `[0x501350]` (0x280 bytes each), writes x' = px + (px − x) and z' = pz + (pz − z) through
    the player `[0x501320]` (two TGP command-0 float adds per axis, the operand negated by adding 0x80000000) and adds
    0x8000 to the heading `+0x2c`; pops; `done: jmp FC0EEC`. With the flag 0 it differs from the original only in the
    condition flags at 0xfc0eec, which nothing reads (`push`, `mov.w`, then `jsr FE88A7`, whose `and.w` sets them before
    its `be`).
  - **The figures' animation** (Task 13, after Pascal rejected the unturned one; stage 2 findings §11.3.2). A figure is drawn
    T(position) T(root) T(record offset) R_b0(+0xd1) R_a8(+0xd7) R_a0(+0xdd) R_a8(+0x2c) and its limbs (0xff5df4, 0xff6bf3).
    The root offset (+0x17b, +0x187, +0x193) is keyed every fourth frame from the animation's table (`[19B]` → `0[R4]`: x, y,
    z floats then the joint bytes per key; 0xff67e6 sets it, 0xff68da / 0xff6a5d step it by (key − current) / 4 into
    +0x177 / +0x183 / +0x18f, 0xff6b20 adds the steps). The body's three root rotations are the first three joints of +0xcd
    (counter, step, value; 0xff6976). An ended animation adds the root offset's x and z to the position (0xff6a14). The
    walk-off (state 0x27, only the figures reach it) sets `+0x36` = 0x4000 (0xff6712), and 0xff6b70 moves the figure along
    −`+0x36` in world axes. The record offset is (0, 0, 0) for the three figures. A half turn about the vertical axis
    negates the root offset's x and z and the rotations about the horizontal axes (+0xd1, +0xdd), keeps +0xd7 and adds
    0x8000 to `+0x36`. Seven boot sites, each the original instruction → `jsr <routine>` + nops: 0xff5e13 and 0xff6a18
    (`mov.w 17B[R25], [R24]` → `figrootx`, 35 bytes), 0xff5e1f and 0xff6a2c (`mov.w 193[R25], [R24]` → `figrootz`, 35),
    0xff6c25 (`movs.hw D1[R25], [R24]` → `figrot0`, 43), 0xff6c41 (`movs.hw DD[R25], [R24]` → `figrot2`, 43), 0xff6712
    (`mov.h #4000, 36[R25]` → `figwalk`, 23). Each routine calls `figmirror` (54 bytes: Z when the flag is set and
    `1AB[R25]` is 0xfd743b, 0xfd747f or 0xfd754b, the three figures' records; the character code is shared with the pit
    crew); if it does not hold, the routine runs the original instruction's own bytes and returns, else it pushes the field
    negated (a float by adding 0x80000000; a halfword angle by `movz`, `shl #16`, `sha #−16`, `mul #−1`), R0 kept (`figwalk`
    stores 0xc000 after the original's 0x4000). The stored animation is never changed: only its uses are mirrored. The
    flags after each site are not read before the code sets them again. No branch or address word lands inside a site. The
    figure's visibility cell (+0x34, the start's, not updated) and its cull (0xff5cef) are not touched. Two of the three
    records (0xfd743b, 0xfd747f) are also used by the attract mode's pit scene (the values stored at 0xfc0186 and 0xfc0230;
    in the program and boot ROMs the three values occur only there and at the placement's 0xfc0c61, 0xfc0d59, 0xfc0e2c).
    Those figures stay unmirrored only because the flag is cleared before the attract runs (`bankdemo`); stage 3's
    direction screen must keep that order.
  - All the boot sites are patched whether or not the set has variants. With `dirattr` (32 bytes) the direction routines
    take 463 bytes; the directory image ends at `directory_layout()["end"]`, `end − loader` = 4 821 bytes
    (`tests/test_directory.py`'s bound is 5 000: 179 left; stage 3: 5 797 against a bound of 6 000, §19). The image grew 431 bytes in stage 2, so the normal courses' tile
    tables, race blobs and spawn lists, stored from the next 16-byte boundary after it, moved 0x1b0 bytes from main's places
    (0x30 with Task 7's 19-byte `figures`); their content is unchanged (stage 2 findings §8, §11.3.2).
  - **`entry`** (100 bytes, the first routine, at `directory_layout()["entry"]`) is the lookup that eleven routines call
    with `jsr`: `loader`, `bank`, `pit`, `music`, `cars`, `gfx`, `mapobj`, `pitbox`, `pitaim`, `pitpark`, `pitstops`.
    Each used to inline it.
    - **Menu path:** R8 = the menu entry's (`[0x501940]`) load record when its template equals the data index
      `[0x501934]`, or when the data index is 3 or more. On this path only, when the flag byte is non-zero and the
      entry's reverse word is non-zero, R8 = that word and R0 = 1; otherwise R0 = 0.
    - **Fallback path:** otherwise R8 = the original course for that data index (`FALLBACK`) and R0 = 0. The flag is not
      read.
    - R1 is clobbered.
  - **The flag, `course.DIRECTION_RAM` = 0x502294**, is one byte: 0 normal, 1 reverse.
    - The boot clears it (frames 0 and 9). Otherwise the game neither reads nor writes it, in attract or in a race
      (findings §1).
    - The loader writes `entry`'s R0 back right after its lookup (`mov.b R0, 502294`), so the byte reads 1 exactly while
      a variant is loaded.
    - Stages 1 and 2 set it from Lua on the select screen (`vrtools/mame/lua/direction.lua`). Since stage 3 the COURSE
      DIRECTION screen's lock sets it (§19); `direction.lua` stays a test tool (`VR_DIRECTION_FORCE=1`) for forcing it where
      no screen sets it.
  - **`bankdemo`** (14 bytes: `mov.b #0, 502294; jmp bank`) clears the flag at the attract cycle's two course loads
    (`ATTRACT_BANK_SITES`):
    - 0xfe2160: game mode 2, the demo;
    - 0xfe2cf7: mode 6, the Big Forest load between demos. It saves the data index in the menu word first, so its load
      takes the menu path.
    - The other three bank sites called `bank`: 0xfe415b (the race), 0xfe2b07 (mode 5, reached only through a linked
      cabinet's mode) and 0xfe1d37 (a cabinet joining a linked race). Since stage 3 the last two call `bankdemo` too (§19);
      only the race's 0xfe415b calls `bank`.
  - **`dirattr`** follows the ranking block: §18.

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
- **The start gantry waves** (Phase 26 stage 2, Task 11; `vrtools/arcade/gantry.py`). Its handler `0xffb07f` sets the draw
  routine `0xffb0dc` (`+0xa`). When the gantry's cell is visible (`test1` on the `0x501ac0` bitmap), that routine hands
  `0xff84a2` (§7) the record `[objlist + 4 × (+0x1c & 0x1f)]`, at the entity's position and yaw `+0x2c`, then `inc.h +0x1c`.
  So each draw advances one frame of 32. It also tests the player against the gantry through the TGP and, inside it, runs
  `0xffb264` (timers `0x501160`, `0x50114c`; sound `0xb01a`).
  - **The object list `0xfdc033`:** 32 pointers to records `(poly, tex, size)`, each followed by a zero word, which is the
    terminator of `0xff84a2`'s walk (`0x2e1b30 + 0x10·k`). The three originals' spawn lists share it.
  - **The records:** `size` only adds to the frame's record count `0x5011a0`; the renderer reads up to the end marker.
  - **Each frame:** an object of 141 records (117 quads), all two-sided, z mode 1. It holds two posts (still), a white
    banner of strips that swings 2.4 units fore and aft over the cycle, and 23 red letter quads ("START") on its −z side,
    their corners 0.52-1.18 units in front of the banner's surface. Every record advances the colour entry; the 32 frames read the same colour words.
  - **The converted courses' copy:** Alpine, Diablo Canyon and Pacific Coast name a copy of the list instead. Its frames
    are each arcade frame's records followed by 46 records of mirrored one-sided lettering, and the list sits at the top of
    the code area.

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
  Phase 25: with a quad credited the point at its FRONT (Phase 10), a point naming the first segment at or after it
  holds the cursor one point past the front of the car's own quad (target 30 units past it); naming the last segment
  at or before it let the cursor run to the NEXT quad's front (target 60-100 units ahead on 40-unit quads).
- **Off the tarmac** (boot `0xfea9a0..0xfea9e3`, Phase 25): when the surface word of the TGP's answer under the car
  (`+0x140`) has any of bits 0x2c, `+0x6c` is 0 and flag bit 8 of `+0` is clear, the game sets flag bit 15 of `+0`,
  counts `+0x131` and plays sound 0xb010; `0xfeafa4` then starts the rocking table at `+0x6c` and sets the smoke
  counter `+0x1aa` to 0x40 (flag bit 16 starts the table the other way; what sets it was not traced). The car's speed about halves over the next two seconds.
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
- Callers of the setter (Phase 23b recon): `0xfc3c33` (`movz.bw 501934, R0; bsr FC4208`, 10 bytes) is the attract
  mode's ranking page, which comes with the demo of each original (data index 0, 2, 1 in turn: MEDIUM, BEGINNER,
  EXPERT); `0xfc40e1` the race's end; `0xfc4226` the post-race task (installed at `0xfe65a7`). The page's title:
  `0xfc3cff..0xfc3d11` (19 bytes) jumps through `0xfc3db6` by data index to `0xfc3ea0 / 0xfc3efe / 0xfc3f5c`, each
  three calls of the string printer `0xffe8fb(string, tile address, attribute)`: the word (`0xfc400b` MEDIUM,
  `0xfc4012` EXPERT, `0xfc4019` BEGINNER) in red (`0x8300`) at column 9 (BEGINNER 8), `0xfc3fe9` COURSE and
  `0xfc3ff0` RANKING in white (`0x8200`) at 24 and 39 (26, 41) on the title row `0x700200` (2 columns a letter). The
  printer draws each character (ASCII & 0x3f) as 2 × 3 tiles from the glyph table `0x2f2456` (6 bytes a code); the
  font has A–Z, the digits and the space. Phase 22r's setter read the chosen course for every caller, so the attract
  pages all showed the last chosen course's table; Phase 23b gives the attract page its own setter (by data index,
  the original first, then the converted courses in its slot, one per loop) and routes the title through the shown
  table's ranking id (`ranking.py`).
- Initialiser `0xfc3b49`: R22 = `0xfcd5b9` (normal) or `0xfcd5c5` (operator flag `0x40dc8c`), R21 = `0xfcf16d`
  (checkpoint records), R23 = `0xfc3c1b` ((defaults `0xfc4dc0`, table) pairs), 3 iterations: the level-0 record's
  first 5 × [checkpoints] words summed, divided by 1920 (a minute in 1/32 s) and rounded up → the first entry's time;
  24 entries from the defaults (rank byte, step byte, name) stepping 0xa0 (5 s); then the three slot stores.
- `0x501934` (the data index) is written only at `0xfc270f` from the select record's byte +0x14 (`0xfc35c7 + 0x18·entry`;
  our ten-entry table since Phase 7); the game compares it with 1 in the player handler (`0xfe1775`) and at the race
  start (`0xfc0bf2`): Acropolis-template behaviour (data index 1 is Acropolis; Bay Bridge is 0, Big Forest 2), which
  is why the converted courses keep their template's value (Metropolis and Diablo Canyon carry 1) and carry the ranking
  id separately (`ranking.py`). The race-start compare places three start objects at fixed offsets from the player
  (Phase 26 findings §5, §7).
- The boot's work-RAM clear `0xfe0016`: `movcfu.h` 0x7000 zero halfwords from `0x400000` — everything below `0x40e000`
  is work RAM (the entity pool at `0x400d00`); only `0x40e000..0x40ffff` persists. In that part the bookkeeping lives at
  `0x40e800 / 0x40e900`, a record at `0x40f000`, the stack at `0x40ff00`; `0x40ea00..0x40f000` and `0x40f100..0x40fe00`
  are 0xff since the factory and untouched through boot, attract, coin-up and a race (Phase 22r's taps) — the converted
  courses' ranking tables live there. (Work RAM that is never non-zero is still read as zeros by the race: a table placed
  at `0x40c940` hung the race start.)

## 18. The collision quad's direction in a reverse race (Phase 26 stage 1, `direction.py`, `tgp.py`)

Word 15 of every collision quad is its direction of forward travel (1/65536 turn), and its corners run front-left,
front-right, back-right, back-left (recon `docs/spike/2026-11-phase26-reverse-recon.md` §2; the TGP's use of both, §5). A reverse variant races
the same collision the other way round. Two TGP commands read the direction (findings
`docs/spike/2026-11-phase26-stage1-findings.md` §4 and the Task 8 notes):

- **Command 0x1800** (handler 0x431) takes a quad and returns its direction in R0.
  - The 14 sites (`direction.ATTR_SITES`) are each `mov.w #18000000, [R24]; mov.w <quad>, [R24]; in.w [R23], R0` (16
    bytes, 14 with a register operand). They are the only occurrences of the command word in the boot and program ROMs
    (`tests/test_direction.py` scans both).
  - Quad `30[R25]` (the car's current quad):
    - 0xfe8d0b: the grid, seeds `+0xeb` and the yaw `+0x36`;
    - 0xfe8f97, 0xfe9147, 0xfe92fd: `+0xeb`, each right after a 0x1500 site;
    - 0xfea927, 0xfeaa82, 0xfeab05: the opponents' handler, `+0xeb`;
    - 0xfebd50: `+0xeb`, then the 0x1580 put-back sequence;
    - 0xff2205: the Big Forest template's PIT START, `+0xeb` and the yaw (findings §5);
    - 0xff241c: `+0xeb`.
  - The other operands:
    - 0xff4c9e, `30[R19]`: the wrong-way warning (below);
    - 0xfec003, R1: the wall kick, the yaw against the direction taken as an axis;
    - 0xfec152, R1: yaw minus direction compared with 0x1000, before the kick;
    - 0xffcffc, R12: yaw = 2 × direction − yaw.
  - All ten stores of `+0xeb` follow one of these sites: one `mov.h R0, EB[R25]` after each of the ten `30[R25]` sites (its
    bytes occur ten times in the boot ROM). After every site the game reads R0 only as a halfword and sets
    the condition flags itself before testing them (read by disassembly; `tests/test_direction.py` checks it up to the
    next branch or call).
- **`dirattr`** is 32 bytes at `directory_layout()["dirattr"]`, after the ranking block:
  `mov.w #18000000, [R24]; mov.w R0, [R24]; in.w [R23], R0; cmp.b #0, 502294; be done; add.w #8000, R0; done: rsr`.
  - Each of the 14 sites becomes `mov.w <quad>, R0; jsr dirattr`, nop-padded to the original's length
    (`patch_direction_sites`; every site is checked against its own pattern before any is written).
  - With the flag `course.DIRECTION_RAM` set, every reader gets the direction turned half a turn. With the flag 0 it
    gets the TGP's own answer. The condition flags are clobbered.
- **The wrong-way warning** (0xff4c9e) runs on 8 of every 16 logic frames (bit 3 of the logic-frame counter 0x501144).
  - It compares the direction with the car's heading `+0x6a` (`sub.h 6A[R19]`, `cmp.h #7800`): within 0x800 of
    opposite, it draws the tile map 0x2F4D36 when `[0x40DC9B]` is 0, or else prints the string "REVERSE" (boot
    0xFF4D0F; read by 0xff871e).
  - On the `vr` set the string path is the one taken (findings, Task 8: 278 frames of a positive control).
  - Through `dirattr`, a car racing a variant compares against the turned direction: 0 frames of warning in the reverse
    race (the turned-round test, `tests/test_reverse_build.py`). Its positive control,
    `test_the_wrong_way_warning_is_read_when_the_game_sees_the_car_against_its_quads`, checks that a car driving the
    variant with the flag forced back to 0 in the race (`direction_off.lua`: the quads' direction as authored, so the
    car travels against it) gets the string on at least 50 frames of 60 s, and that the same drive with the flag 1 gets
    nothing.
- **Command 0x1500** (handler 0x34b) takes the quad, x and z and returns six values, which the V60 stores at
  `+0xf1, +0xed, +0xf5, +0xf9, +0xfd, +0x101` (`tgp.edge_values`). With a = the attribute's low 16 bits, u = (−sin a,
  cos a) the direction of travel, r = (u.z, −u.x) its right, p = (x, z) the car and c0, c1, c2 the first three corners
  (c3 is not used):

  | field | value | meaning |
  |---|---|---|
  | `+0xf1` | (c0 − p)·r | the front-left corner's lateral offset |
  | `+0xed` | (c1 − p)·r | the front-right corner's |
  | `+0xf5` | −(`+0xf1` + `+0xed`)/2 | the car's lateral offset from the front edge's midpoint (positive to the right) |
  | `+0xf9` | (c1 − p)·u | the front edge's distance ahead (through c1) |
  | `+0xfd` | (c2 − p)·u | the back edge's (negative behind; through c2) |
  | `+0x101` | −(`+0xf9` + `+0xfd`)/2 | the car's offset along u from the middle of the right side |

  - The formulas reproduce every fresh logged value of a normal and a reverse Metropolis race, and of a build with every
    quad turned round. The fit is within 1e-3 × max(1, |value|).
  - The seven sites are 0xfe8f5c, 0xfe910c, 0xfe92c2, 0xfea8ec, 0xfeaa47, 0xfeaaca and 0xff23e1: one identical 59-byte
    sequence each, each followed directly by a 0x1800 site.
  - The readers in a race:
    - `+0xed` − `+0xf1`, the front edge's width against 5.0, in the two car-to-car contact routines;
    - `+0xf5`, in the contacts' separation, push side and heading match, the car-beside-car flag, the wall kick, the sign
      tests 0xfebdca and 0xfe9571, and three player sign tests (sound 0x5F or 0x6F).
    - `+0xf9` and `+0xfd` have no reader. `+0x101`'s one reader (0xfea4d3, the race order) did not run.
- **The 0x1500 sites are untouched, and there is no `edges` routine.** The plan's Task 10 did not run.
  - Turning a quad round swaps its corners to (c2, c3, c0, c1) and negates u and r. So a reverse-authored quad's value
    is minus the forward value of its partner field, plus a per-quad constant: (c1 − c2)·r for `+0xf1`, (c0 − c3)·r
    for `+0xed`, and their mean for `+0xf5`.
  - These constants are within 1e-3 on 42 of Metropolis's 1 322 quads only, so no signed permutation corrects the three
    values that are read (findings §4, Task 9's STOP for those values).
  - Left as they are, the push side and the give-way are right. Read from the disassembly, not observed: the heading
    match of an opponent alongside another car and the player's sound choice are mirrored. A plain mirror would swap
    which behaviours are wrong (findings §4, §8).
- **Command 0x1580** has three sites (0xfebd65, 0xfebfaa, 0xffd4f5, the put-backs). It takes the quad, the position and
  the yaw. Untouched: whether its handler reads the corner order was not established. A put-back in a reverse race faces
  the race (findings, Task 8).

## 19. The COURSE DIRECTION screen and the HUD name (Phase 26 stage 3, `dirscreen.py`, `dirgfx.py`, `hudname.py`)

Measurements in `docs/spike/2026-11-phase26-stage3-findings.md`; recon `docs/spike/2026-11-phase26-stage3-recon.md`.

- **Boot sites** (each checked against its pattern before any is written; `PatchError` naming the site):

  | site | bytes | original | becomes |
  |---|---|---|---|
  | 0xfe3cce | 8 | `mov.b #0, 5019C0[PC]`, mode 0x10 state 0's first instruction (every select screen, every cabinet) | `jsr dirclear` + nops |
  | 0xfc40ce | 16 | `movz.bw #0, 5018FC[PC]; test1 #1, 501174[PC]` (the race end's record test) | `jsr rankgate` + nops; the `be FC417C` after it stays |
  | 0xfe2b07, 0xfe1d37 | 0x16 | the linked course loads' bank switch (`jsr bank`) | `jsr bankdemo` |
  | 0xfc2788 | 9 | `mov.w #FC27BE, A[R25]` in the course select's lock handler 0xfc277c | `jsr dirlock` + nops |
  | 0xff4799 | 6 | `jsr FF8926[PC]`, the race HUD's level word print in 0xff471b | `jsr hudname` |

  Each span is entered only at its first byte (`br FE3CCE` at 0xfe3cb9; `jsr FC40CE[PC]` at 0xfe4b49; 0xfc277c from 0xfc2750 and
  0xfc2772; 0xff4799 from the instruction before it), and no 32-bit word of the boot or program ROM points inside one.
- **RAM cells** (the flag's word, 0x502294..0x502297, byte accesses only):
  - 0x502294 the flag (§13);
  - 0x502295 `DIR_PHASE`: 0 no direction screen, 1 choosing, 2 locked;
  - 0x502296 `DIR_ARMED`: 1 once the wheel value R10 has been ≤ 0x1c on a logic frame of this screen;
  - 0x502297 `DIR_SHOWN`: 0xff when the screen opens, stepped down by one per drawing phase (0xff, 0xfe, 0xfd, 0xfc, 0xfb, 0xfa),
    0xf9 once drawn, then the choice shown (0 NORMAL, 1 REVERSE); from the lock on, the flag's value.
  `dirclear` writes 0 to all four with one `mov.w`.
- **The flow.** `dirlock` (from 0xfc277c) installs 0xfc27be as the original when `[0x40dc8c]` != 0 (linked play), when
  `DIR_PHASE` != 0 (the direction lock's own pass) or when the entry's word in the reverse table is 0; otherwise the select
  entity's handler := `dirsel`, the timer 0x50113c := 0x140, `DIR_PHASE` 1, `DIR_ARMED` 0, `DIR_SHOWN` 0xff, the flag 0. `dirsel`
  (every logic frame) calls `dirdraw` while `DIR_SHOWN` is above 0xf9 (unsigned), and then: R10 = ([0x501060] + [0x50106c]) >> 1;
  `DIR_ARMED` := 1 when R10 ≤ 0x1c; the choice is 1 when armed and R10 > 0x1c; on a change `DIR_SHOWN` := the choice and
  `dirshow`; `dircursor`; the lock on `[0x501078]` != 0 (the gas edge) or the timer ≤ 0x20: the flag := `DIR_SHOWN`,
  `DIR_PHASE` := 2, the handler := 0xfc277c, which on the next logic frame sets the timer to 0x20 and, through `dirlock`, the handler
  to 0xfc27be (198 video frames from the lock to mode 0x11). `start` (select.py, from 0xfc27d6) begins with
  `cmp.b #0, 502295; be body; jmp dirdone`. `dirdone` copies slot 0's and slot 2's 48 palette words from the picture record's
  `chosen` or `grey` set (the chosen side in colour) and falls into `dircursor`. `dircursor` draws the game's course cursor frame
  (0xfc2880's body from 0xfc28a7) at the `dirsides` record of `DIR_SHOWN`: (−112.0, 65.0) NORMAL, (112.0, 65.0) REVERSE.
  `rankgate` returns with Z set while the flag is set (the `be` skips the record and so the name entry), else with the original
  `test1`'s flags.
- **The screen's tile layout** (64 × 64 cells a layer, 0x80 bytes a row; `dirscreen.tile_address`):

  | piece | layer | cells (row, column) | drawn by |
  |---|---|---|---|
  | layer 0 cleared, layer 2's checker | 0, 2 | all | 0xff92c9, 0xfc358e |
  | COURSE DIRECTION | 0 | rows 1-3, columns 15-46 | 0xff870d (countdown font) |
  | the picked course's picture, NORMAL / REVERSE (16 × 21) | 2 | (4, 9) / (4, 37), slot 0's / slot 2's blocks and palettes | select.`picture` |
  | the ring arrows (12 × 12) | 0 | (8, 11) NORMAL, (8, 39) REVERSE | the draw list |
  | the double arrow 0x1e2205 (8 × 6) | 0 | (10, 28) | the draw list (0xff9436) |
  | NORMAL / REVERSE | 0 | (26, 11) / (26, 38), rows 26-28 | 0xffe8fb, attribute 0xC200 (yellow) for `DIR_SHOWN`, 0x8200 (white) for the other |
  | wheel panel 0x1e0f71 (13 × 20), its caption (2 × 18) | 0 | (30, 7); caption at (31, 8) | the draw list |
  | red arrow 0x1e1185 (5 × 6) | 0 | (32, 28) | the draw list |
  | STEP TO START! 0x1e13e1 (13 × 20) | 0 | (30, 35) | the draw list |
  | the countdown | 0 | rows 39-41 (40-42 with `[0x40dc9b]` = 0), columns 28-31 | the game (state 1) |

- **The middle slot.** The arrows and the caption use the middle slot's three blocks, which the direction screen does not show
  (characters 0x3480 clockwise arrow, 0x3500 anticlockwise, 0x3580 caption; palettes 0x69, 0x6a, 0x6b: a tile word's palette is
  its character >> 7). The NORMAL side's block gets the white set and the other's the red set. The caption's palette 0x6b is
  copied from palette RAM 0x73 (the wheel panel's own palette); the caption uses its colours 8 (paper) and 1 (ink). The race load
  uploads its own characters over those blocks; the next course select's mode 0x0f uploads the select characters again.
- **The data block** (`tencourse.dirscreen_block()`, `dirgfx.block_image`): 5 968 bytes at 0x2be8b0..0x2c0000, at the top of the
  colour-table run (the annex's region ends at its start), erased in the original; written first by `build_all` and, when missing,
  by `ten_course_set` (`install_dirscreen_block`: keeps an identical block, writes on erased ROM, refuses anything else). Gaps and
  padding are 0x00 (no 0xff run). Layout: the rows (6 phases × 128 bytes), then the clockwise arrow's 54 characters, the
  anticlockwise one's 54, the caption's 31 (32 bytes each), the white and red palette sets (16 words each), the clockwise and
  anticlockwise maps (300 bytes each) and the caption's map (84), each 4-aligned (addresses in the findings §3). Maps are
  0xff9436's mode-1 format (`base:u16, mode:u16, rows:u32, cols:u32`, then halfword indices); an arrow's empty cell gives 0x8020.
- **The draw list ("rows").** Each phase's rows are at the block's start + 128 × (`DIR_SHOWN` − 0xfa), up to seven rows of 16
  bytes `(source:u32, destination:u32, count:u32, swap:i32)`, then a row with source 0, which ends them. count > 0 copies `count`
  longwords from source to destination; count 0 blits the map at source to the tile address destination (0xff9436). When the
  chosen entry's lap is anticlockwise (its load record's `map_cross`, +0x38, non-zero) the destination moves by `swap` first. The
  phases: 0xff clears, title, labels (white, through `dirshow`), then rows: the four game maps, the caption's characters to 0x3580,
  palette 0x73 to 0x6b, the caption's map; 0xfe and 0xfd the two pictures (no rows); 0xfc the clockwise arrow's characters; 0xfb the
  anticlockwise one's; 0xfa the white set to palette 0x69 (swap +0x20), the red set to 0x6a (swap −0x20), the clockwise map to
  (8, 11) (swap to (8, 39)), the anticlockwise map to (8, 39) (swap to (8, 11)). So the NORMAL side always shows the arrow of the
  entry's own lap, in white.
- **The HUD name** (`hudname`, after `dirtext`, and its table `hudattr` = 0x02, 0x83, 0x82). The game's site picks the word by the
  data index `[0x501934]` (0 " MEDIUM " colour cell 0x83, 1 " EXPERT " 0x82, 2 "BEGINNER" 2) and prints it with 0xff8926 (R0 a
  NUL-ended string, R1 the first cell; glyph word (`[0x501434]` << 7) − 0x40 + 2·ch | `[0x50143c]` on row 44, + 1 on row 45) at
  layer 0, rows 44-45, columns 51-58. `hudname`: `pushm` R0, R1, R8; `jsr entry` (R8 = the served load record); `race` (+0x2c) 0:
  `popm`, `jmp FF8926` (the game's word). Otherwise R0 = the record + 0x1c (the name), R1 = the site's R1 + 16 − 2 per letter up to
  the NUL (the last letter in column 58), `[0x501434]` saved, set to `hudattr[label]` (+3), the printer called, the cell restored.
  The load record's name field (+0x1c, 14 bytes) is NUL-padded and holds at most 13 letters (`directory._load_record`, `_check`).
  The linked slave's copy of the site (0xff53ae..0xff53fa, row 15, column 52) is not patched.
- **Size.** The image is 8 621 bytes (0x278d70..0x27af1d), `end − loader` 5 797 against `tests/test_directory.py`'s bound of 6 000
  (raised from 5 000, plan D10). The tables stored after it moved 0x3d0 from main's places. (Stage 4: 6 251 against 6 500, §20.)

## 20. Pit stops in a reverse race (Phase 26 stage 4, `reverse.py`, `tencourse.py`, `directory.py`, `direction.py`, `collision.py`)

Measurements in `docs/spike/2026-11-phase26-stage4-findings.md`; recon `docs/spike/2026-11-phase26-stage4-recon.md`.

- **No routine changes for the stop itself.** The player handler's pit check (0xfe8e88, §12), `pit`, `pitstops`, `pitbox`,
  `pitboxcrew`, `pitaim` and `pitpark` read the served record through `entry`, so a reverse variant's own pit quad and box are
  used as an entry's are. The heading test compares the car's heading with `+0xeb`, which `dirattr` (§18) turns half a turn in a
  reverse race, so a car driving up the lane backwards passes it.
- **The variant's records.** Load record +0x10: the variant's pit quad q (u16; the game also triggers on q + 1), 0xfffe (none)
  until stage 4. Maps record +16..+31: the box (x, y, z floats, heading u16, then the u16 1), zeros until stage 4. Both come from
  `reverse.reverse_pit` (`tencourse.Reversed.pit_quad`, `pit_box`), only for a course whose normal entry has a pit stop; `_check`
  refuses a quad without a box and a box without a quad. No record grew. On the stage 4 set the seven variants' records hold:

  | course | variant pit quad | box (x, y, z), heading |
  |---|---|---|
  | Alpine | 250 | the normal box, heading 0xc00f (normal 0x400f) |
  | Amazon Falls | 32 | the normal box, 0x831c (normal 0x031c) |
  | Diablo Canyon | 58 | the normal box, 0x8b96 (normal 0x0b96) |
  | Metropolis | 86 | (−89.633, −9.090, 269.739), 0x7ff9 (normal box (−89.608, −7.876, 310.439), 0xfff9) |
  | Pacific Coast | 241 | the normal box, 0x312b (normal 0xb12b) |
  | Surfers Oval | 15 | the normal box, 0x80ce (normal 0x00ce) |
  | Surfers Road | 13 | the normal box, 0x807b (normal 0x007b) |

- **The crew** (four boot sites, each checked against its pattern `bsr <spawn>; inc.h 191[R25]`, 7 bytes, before any is written;
  `PatchError` on a mismatch; listed in `tests/test_directory.py`'s allowed spans):

  | site | work state | spawn | objects | becomes |
  |---|---|---|---|---|
  | 0xff2518 | 1 | 0xff27d8 | 5 | `jsr crewturn1` + nop |
  | 0xff26f0 | 8 | 0xff2d69 | 6 | `jsr crewturn8` + nop |
  | 0xff2735 | 11 | 0xff33c7 | 6 | `jsr crewturn11` + nop |
  | 0xff277a | 14 | 0xff3a1b | 6 | `jsr crewturn14` + nop |

  Each entry (34 bytes) calls the spawn, does the `inc.h 191[R25]`, tests the flag 0x502294 and, when it is set, calls
  `crewturn` (143 bytes) with R3 = the spawn's object count: R10-R12 = `pitbox`'s box (the box the spawn used: the variant's in
  a reverse race), and each pool object k < R3 of `[0x501350]` gets x' = bx + (bx − x), z' = bz + (bz − z) by two TGP
  command-0 float adds per axis (the operand negated by adding 0x80000000) and heading `+0x2c` + 0x8000. Registers are kept; the
  condition flags after a site are not read (0xff2381 `test.h` sets them). With the flag 0 the path is the original's but for
  the condition flags. The pit work state is chosen at the trigger by the player's damage flags `+0x1ab` (§12).
- **The crew's animation.** The crew runs the start figures' character code (handler 0xff5c3d), whose world-axis uses of the
  animation call the figure routines (§13, "The figures' animation"). `figmirror` (229 bytes, was 54) holds for the three
  figures' records and the crew's fourteen (`direction.CREW_RECORDS`: 0xfd7033, 0xfd7078, 0xfd70bd, 0xfd7102, 0xfd7147,
  0xfd7216, 0xfd725b, 0xfd6fee, 0xfd71d1, 0xfd7ad5, 0xfd7b1a, 0xfd72a0, 0xfd72e5, 0xfd732a; each written only at the four
  spawns' stores, as 32-bit literals), so with the flag set the root offsets and the two horizontal rotations are pushed
  negated. The spawns' only callers on the original are the four sites, 0xff25c9 and 0xfc007e (every byte of the program and
  boot ROMs read as a direct transfer, every 32-bit literal of a spawn's address: `tests/test_direction.py::
  test_the_crew_spawns_are_called_only_from_the_known_callers`; a target computed at run time is not covered). Alpine's PIT START
  runs the spawn 0xff27d8 from 0xff25c9, which is not a site, in a normal race only. The attract mode's pit scene runs the same
  spawn from 0xfc007e (`jsr FF27D8[PC]`), so its objects 0-4 hold work state 1's five records (`CREW_RECORDS[:5]`); its other
  objects take its own records and two of the figures'. It keeps the game's crew only because the flag is 0 there, pinned by
  `tests/test_dirscreen_build.py::test_the_flag_is_zero_whenever_a_select_screen_starts` and
  `tests/test_direction.py::test_the_attract_demo_never_loads_a_reverse_record`.
- **The object at `[0x50138c]`** (activated at the crew spawns by 0xff4101 / 0xff4129, handler 0xff414c, placed by `bsr FF4061`
  at 0xff4165, drawn by 0xff417b at world-axis offsets: read as four spare tyres) is not changed: 0xff4061 gives the host
  template's box, not the course's (one of the call sites Phase 22i left alone). Measured on Amazon Falls: the findings §9.
- **Size.** The directory image ends at 0x27b0e3; `end − loader` = 6 251 bytes against `tests/test_directory.py`'s bound of 6 500
  (raised from 6 000, plan L2). `figrootx` .. `figwalk` moved +175 (after `figmirror`), the stage 3 routines +454; the tables
  stored after the image moved +0x1d0 from main's places. Free after the image on the seven-course set: 2 592 bytes at 0x28ef50
  (below the start-gantry block 0x28f970), six spawn-slot tails of 720 / 744, 98 at 0x28fd0e.
- **Diablo Canyon's lane wall** (`collision.PIT_LANE_WALL_TRIMS`, `trim_walls_off_the_lane`, in `saturn_collision` after the late
  wall drop): the wall quads wholly inside the named rectangle (x −409.5..−388.0, z 31.0..43.5) lose the part over the lane's
  tarmac slices (`pit_lane_polygons`); the rest is kept exactly (old corners with their own height, new corners on the old quad's
  TGP plane), cut into the fewest convex quads. On Diablo one quad (index 1689) becomes two (1689, 1690); the later wall quads
  shift by one; tarmac and verge indices do not move. Diablo's lists grow from 9 911 to 9 913 words. The spot names the number
  of quads it trims (`WallTrim(rect, quads=1)`); a build that trims none or another number raises `ConvertError`.
