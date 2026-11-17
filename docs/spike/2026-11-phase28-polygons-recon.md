# Phase 28 recon: more polygons on the tracks (15 Nov 2026)

Pascal: "Can we add more polygons to the tracks?" In order of priority: (1) more scenery objects, (2) finer geometry,
(3) longer view distance, holding 60 fps. This page establishes what limits a frame, how much of each limit the ten
courses use today, and what each direction would take. Nothing in the product changed; all scripts, logs, runs and
images are under `out/p28/` (git-ignored, listed in §10).

Marks: **[V]** verified by a run or a byte read in this recon; **[R]** read in code or a listing; **[?]** not
established. Numbers from runs come from **one run each** (the autopilot, 30-540 s of race), unless stated.

## 0. The answer in brief

- **What "60 fps" can mean here.** The arcade game has never drawn 60 pictures a second. It draws one picture and runs
  one logic step every **second** screen frame: the Model 1 screen is 57.52 Hz, so the game runs at **28.76 pictures a
  second** [R: MAME `model1.cpp:1834`, the main loop's two-vblank wait at `0xfe13db`]. "Holding 60 fps" can only mean
  holding that native two-vblank cadence on every frame. That is measurable (§2.1) and held today on every course
  [V]. Pascal should know this: the target cannot be a literal 60.
- **Records cost no emulated time in MAME.** Polygons are transformed and drawn by MAME's video code at the screen
  update, with no cycle cost. Over about 140 000 logic frames (14 runs) the V60 was busy for 8.5-14.5 ms of the 34.77 ms frame
  window. The game's own overrun counter never moved, and the render rate held at 28-29 [V]. A frame with 1 200
  more records cost +0.1 ms (Big Forest at a 20 000 budget) [V].
- **The binding limit is the game's own frame budget: 5 500 records a frame** (0x5011b0). Passing it does not slow
  the game or corrupt anything. The object list that crosses the budget is drawn whole, and **every later list is
  skipped**. The scenery cells come last in the frame, outer ring last, so passing the budget drops the
  **far scenery cells** for that frame, which shows as far pop-in [V]. **Sega's own courses pass the budget on 17-22 %
  of race frames** (Big Forest, Acropolis; Bay Bridge 3 %) [V]. The converted courses pass it only at the start on
  Diablo Canyon, Metropolis and Pacific Coast (3-86 frames a run), and there the cause is cars and start furniture,
  not scenery [V].
- **Headroom.** Away from the start, a converted course's frame peaks at a median of 2 100-2 900 records and a p95 of
  2 900-4 700 [V]. Its scenery cells carry a median of 1 050-1 400 records per frame over the whole lap, against
  2 200-3 070 on the originals [V model, §3.3]. So about **+1 000 to +1 500 scenery records a frame** fits on most of
  every converted lap before the converted courses skip as often as Sega's own do. About +2 000 fits on stretches
  away from the start. Near the start lines, cars, the gantry and the figures take 3 000-4 300, so there is little
  or nothing to spare.
- **Room is the second limit.** Polygon ROM has **461 548 bytes** free (11 500 records at 40 bytes; 396 000 bytes above
  the 64 KB floor the build keeps). The colour table has **3 800 free entries**. Both are shared by all seven
  courses [V].
- **Verdicts (§8):** (1) more scenery objects: **feasible**, best baked into the cells; bounded per frame by about
  +1 000-1 500 records and in total by the polygon ROM's ~9 900 records. (2) Finer geometry: **feasible in places
  only**: doubling the road strip costs +450-540 records a frame median, and the ROM has room for it on only about
  two courses. (3) Longer view distance: **not without a code change**. The draw distance is a fixed 5×5 block of
  128-unit cells (256-400 units ahead), the same rule as on the originals. Larger cells or neighbourhoods mean
  patching the boot ROM's cell walk.

## 1. Method and instruments

- **Frame logger** `out/p28/p28_frame.lua` (scratch, run through `VR_EXTRA_LUA`), one line per logic frame (per main loop
  iteration):
  - the V60's busy time: emulated time from the two-vblank wait's exit (`mov.b #0, 500501` at `0xfe1406`) to its next
    entry (the first read of 0x500501 from `0xfe13db..0xfe13f3`);
  - the frame's record count peak (a write tap on 0x5011a0);
  - objects added; object-list entries and lists skipped (a read tap on 0x5011b0 at `0xff848a`/`0xff84a2`, a skip being
    a list entered with the count already above the budget);
  - the game's overrun counter 0x501148; the budget word;
  - the player's x, z and road point;
  - the visible-cell list at 0x501cc0;
  - every 100th frame, and every frame with a skip, the sequence of sizes added.

  It also has two harness switches:
  - `VR_P28_HOLD_CLOCK` puts the race clock back to 60 s, so that the autopilot, which cannot overtake and follows the
    field, does not time out;
  - `VR_P28_BUDGET` overwrites 0x5011b0 every frame (the experiment in §2.3).
- **Runner** `out/p28/run_course.py`: `run_mame` with `autoplay.lua` on `out/p27play1`, the autopilot on road line 0
  (or, with `P28_AI_MEAN`, the mean of AI lines 1-7: Alpine and Metropolis stalled on line 0), plus `renderrate.lua`
  and `race_log.lua`. `vrtools` was imported from this worktree (checked: `vrtools.__file__`).
- **Analysis** `out/p28/analyse.py`. Race frames run from the course load to the race's end. The end is the first
  attract frame: three runs finished five laps, and runs without the clock hold timed out, after which the attract
  demo on an original course had contaminated the first set of runs (discarded).
- **Static and model tools.**
  - `static_cells.py`: every cell's records, quads and extent, from the built set.
  - `cellmodel.py` / `lapmodel.py`: an offline model of the visible-cell list (the 5×5 block, kept where a cell meets a
    ±45° wedge from 10 units behind the car). It was checked against the logged lists on five runs: Jaccard 0.84, the
    per-frame scenery-record sum exact in the median frame, bias −15..+10 records. The model gives the scenery load at
    every road point in both directions, which the autopilot runs do not cover.
  - `geom.py`: road-strip resolution.
  - `render.py`: a flat offline render of polygon-ROM objects, for shapes and colours only.
- **Coverage of the runs:** originals 220-589 road points (Big Forest 328 of 338). Converted courses: Alpine 257 (a3)
  and 239 reverse (hr3) of 452; Amazon Falls 170 of 330; Diablo 252 of 457 and 250 reverse; Metropolis 219 of 365;
  Pacific Coast 239 of 410; the Oval 230 of 387; Surfers Road 285 of 441. The autopilot spends the race in or behind
  the field and sometimes on the grass. So the measured "other" share (cars) is pessimistic against a player who
  pulls away, and the scenery share is completed by the model (§3.3).

## 2. A. What limits a frame

### 2.1 What "holding 60 fps" means measurably

| Fact | Value | Mark |
|---|---|---|
| Screen | 16 MHz pixel clock, 656 × 424 total → **57.52 Hz** (`model1.cpp:1834`) | R |
| Main loop | `0xfe11ff..0xfe1387`: start the list (`0xff96b5`), the game step and the display list, close the list (`0xff96d0`: end marker, `xor.h #8, 500510`, the select bit written to 0x680000), then `0xfe13db`: wait until the vblank counter 0x500501 has gone odd, then even; reset it | R |
| Picture and logic rate | one list swap and one logic step per two vblanks = **28.76 a second** (the off-course counter "once per logic frame, every other video frame", `model1-course-tables.md` §5) | R |
| An overrun | if the work takes more than two vblanks, the counter reads ≥ 3 at the wait's exit, **0x501148 is incremented** (`0xfe13fe`) and that iteration takes four vblanks (14.4 pictures a second for that frame) | R |
| MAME's swap | the game writes 0x0082 to the list control at init (`0xfe692c`, bit 2 clear), so MAME takes the list from the game's bit 3 (`model1_v.cpp:1340`), not from its own auto-swap. `renderrate.lua` therefore counts the game's own swaps | R |
| Today | render rate 28-29 switches per 57 frames in every window of every run; **0x501148 = 0 throughout every run** (14 runs, about 140 000 logic frames) | V |

**Measurable definition used here:** render rate 28-29 (the smoke test's 27-29, `RATE_FLOOR` 27), 0x501148 unchanged
over a run, and the V60's busy time under 34.77 ms (two vblanks) in every frame.

### 2.2 Every limit between "a polygon in the ROM" and "on screen"

| Limit | Value | Passing it | Used today (worst seen) | Mark |
|---|---|---|---|---|
| **Frame record budget** 0x5011b0 | **5 500** (set at `0xfe11bd`; **5 000** at `0xfe11d3` when the flag 0x501a35 is 0, cleared at `0xfe11b5` when the byte at 0xb00001 reads 0; 0xb00000 is the comm board's range, so probably the linked cabinet's value; 5 500 in every run) | the list that crosses it is drawn whole; every later object list that frame is skipped (`0xff848a`/`0xff84a2`). The scenery cells are emitted last (`0xff8450`), in the 0x501cc0 order (own cell, the 8 around, then the outer 16), so the outer cells go first | originals 6 213-6 952 peak; converted 4 078-6 037 peak | R (code), V (order, skips) |
| Character path's own check | objects with flag bit 0x1a are drawn only while count ≤ budget − 150 (`0xff5e33`) | that object not drawn | - | R (stage 2 §11.7) |
| Per-object record cap | every `0x01` command carries `[0x5011b0]` as its size (5 500) | MAME stops the object there | largest converted cell 789 records, original 1 566 | R, V |
| V60 + TGP time | two vblanks = 34.77 ms | the overrun above (half rate for that frame) | busy 8.5-14.5 ms in race frames (median 9.4-12.1 ms); about 8 ms fixed + 27-64 µs per object; records add no measurable time (fitted slope −0.2 to +0.17 ms per 1 000 records) | V |
| Display list | 64 KB = 32 768 entries a list (double-buffered); an object costs 8 entries + a 26-entry matrix | not reached | Diablo's heaviest start frame: 69 objects, the list ends at entry 2 540 (7.8 %) | R, V |
| MAME's quad buffers | 1 000 000 quads, 2 000 000 points (`model1_v.cpp:1728`) | - | ≤ ~6 000 a frame | R |
| MAME's clipping | near only (z > 0); **no far clip, no fog** in `push_object` / `draw_quads` | - | - | R |
| TGP FIFO | the V60 waits on it for matrix results; that wait is inside the busy time above | - | inside the 14.5 ms worst | R, V |
| Entity table | RAMA 0x407880, 0x80 bytes an entity; Big Forest has 131 live; **capacity not established** | ? | Bay Bridge's spawn list alone creates 107 | ? |

**Unlike real hardware, MAME's renderer has no polygon throughput limit.** Its cost is host CPU time (software
raster), which was not measured. The 5 500 budget is a game-side constant that protected Sega's hardware.

### 2.3 Raising the budget: the experiment [V]

Big Forest, the same autopilot run twice (frame-identical positions), budget 5 500 against 20 000 (Lua write each frame):

| | budget 5 500 | budget 20 000 |
|---|---|---|
| start frames 2001-2005: lists skipped / peak records | 6-7 / 6 090 | 0 / 7 283 |
| busy at frame 2001 | 13 426 µs | 13 534 µs |
| busy median / max (race) | 10 380 / 14 469 µs | 10 381 / 14 604 µs |
| render rate, 0x501148 | 28-29, 0 | 28-29, 0 |
| pixels differing | - | 0.7 % at 2001-2005 (far trees on the horizon, behind "GO!"); 0 at 2301-3201 |

`out/p28/snaps/budget/bigforest_2001_5500_vs_20000.png`. A boot-ROM change of the immediate at `0xfe11bd` (and
`0xfe11d3`) would therefore remove the skip at no measured emulated cost. It would also change the originals' own
behaviour on the 17-22 % of frames where they skip (§3).

## 3. B. How much of each limit is used today

### 3.1 Per course (one autopilot run each, race frames only)

"Start" is the course load to the green + 400 frames. "Race" is everything after that. "Other" is the frame's peak less
the visible cells' records: cars, the player's car and wheels, the gantry, the start figures and the HUD map. Scenery
model figures are per road point over the whole lap, forward (§3.3).

| course | run | road pts seen | start peak | race median | race p95 | race max | race frames skipping a list | scenery (model, whole lap) median / p95 / max | other median / p95 (measured) |
|---|---|---|---|---|---|---|---|---|---|
| Big Forest | h0 | 328/338 | 6 090 | 4 608 | 5 950 | 6 576 | **1 667 of 7 465 (22.3 %)** | 3 018 / 4 878 / 5 827 | 1 180 / 2 817 |
| Bay Bridge | h1 | 220/418 | 5 269 | 4 840 | 5 457 | 6 213 | 241 of 7 496 (3.2 %) | 2 198 / 4 300 / 5 336 | 2 019 / 2 620 |
| Acropolis | h2 | 589/592 | 6 143 | 4 425 | 6 211 | 6 952 | **1 265 of 7 496 (16.9 %)** | 2 794 / 5 179 / 6 441 | 1 393 / 2 388 |
| Alpine | a3 | 257/452 | 2 800 | 2 178 | 2 905 | 4 078 | 0 of 9 868 | 1 225 / 1 888 / 2 081 | 940 / 1 737 |
| Alpine reverse | hr3 | 239/452 | 3 984 | 2 222 | 3 290 | 4 449 | 0 of 13 087 | 1 249 / 1 894 / 2 105 | 1 000 / 2 129 |
| Amazon Falls | h4 | 170/330 | 3 619 | 2 378 | 3 618 | 4 960 | 0 of 6 709 | 1 348 / 2 089 / 2 311 | 983 / 2 171 |
| Diablo Canyon | h5 | 252/457 | **5 711** | 2 312 | 3 191 | 5 091 | 0 of 14 398 (start: 3 frames) | 1 221 / 1 801 / 2 379 | 1 311 / 2 073 |
| Diablo reverse | hr5 | 250/457 | 5 151 | 2 385 | 3 661 | **5 751** | 1 of 12 361 | 1 232 / 1 792 / 2 144 | 1 157 / 2 236 |
| Metropolis | a6 | 219/365 | **6 037** | 2 911 | 4 691 | 6 018 | 86 of 9 566 (0.9 %; start 9) | 1 400 / 3 150 / 3 682 | 1 237 / 2 305 |
| Pacific Coast | h7 | 239/410 | 4 310 | 2 304 | 3 486 | 5 745 | 4 of 9 218 | 1 156 / 1 774 / 2 111 | 1 138 / 2 315 |
| Surfers Oval | h8 | 230/387 | 3 566 | 2 108 | 2 967 | 4 182 | 0 of 7 180 | 1 117 / 1 727 / 2 123 | 931 / 2 198 |
| Surfers Road | h9 | 285/441 | 3 693 | 2 156 | 3 439 | 4 414 | 0 of 9 111 | 1 068 / 2 019 / 2 534 | 1 004 / 2 134 |

Every run: render rate 28-29, 0x501148 = 0, V60 busy ≤ 14.5 ms [V].

### 3.2 The originals against the converted courses

| per course | originals (BF / BB / AC) | converted (seven) | Mark |
|---|---|---|---|
| scenery quads | 20 366 / 15 641 / 21 923 | 5 982-6 860 | V |
| records (the budget's unit) | 25 188 / 17 688 / 25 220 | 10 324-11 883 | V |
| records per quad | 1.24 / 1.13 / 1.15 | **1.67-1.77** | V |
| quads within 15 units of the centreline, per 100 units of lap | 142 / 195 / 170 | 58-65 | V |
| median road quad size / ground quad size away from the road | 8-10 / 9.5-12 units | 12-14 / **22-24** units | V |
| upright quads (walls, trees, buildings, signs; normal within 60° of horizontal) | 8 546 / 4 155 / 5 095 | 1 431-2 432 | V |
| scenery records a frame (model, median) | 2 198-3 018 | 1 068-1 400 | V model |
| race frames skipping a list | 3-22 % | 0-0.9 % | V |

The converted courses carry about 30 % of the originals' polygons at about 1.5× the record cost a polygon. Per frame
they spend about **half** the originals' scenery records. **Sega ran its courses into the budget routinely and let the
skip trim the far cells.** The converted courses barely touch it.

### 3.3 Sections with headroom and with none

- **No headroom, the start straights**, where the field, the player's car (386 + 4 × 47 records), the start gantry and
  the start figures stand:
  - **Diablo Canyon**, normal road points 30-31: peak 5 711, 8 frames over, 3 frames with a list skipped. The same
    frames as stage 2's §11.7.
  - **Diablo reverse**, road point 178: peak 5 751, 5 frames over, 1 skipped.
  - **Metropolis**, road points 25-50 (and 125-175 in the field): peak 6 037, 109 frames over, 86 skipped.
  - **Pacific Coast**, road points 46 and 58: peak 5 745, 4 frames skipped.

  The start window peaks at 3 566-6 037 on the converted courses.
- **What is skipped on Diablo [V]** (display list decoded at frame 2249, `dl_diablo`, deleted after reading). There are
  69 objects:
  - scenery cells 262 + 301 + 101 + 45 + 261 + 39 + 4 + 256 = 1 269 records, and the **last cell, 0xa6 (184 records),
    skipped**;
  - the field: 16 cars at 5-111 records each, about 1 750;
  - the player's car and wheels: 574;
  - an animated object of 599 records: the start gantry [? inferred: its address changes frame to frame as the
    gantry's 32 frames do];
  - six or seven animated objects of 81-199 records, about 1 400 in all: the start figures [? inferred from their
    animation and stage 2's +1 030 for the reverse figures].

  The crossing comes from the start furniture and the field. The scenery is under a quarter of that frame.
- **Most headroom** (model, the lightest 25-point sections, scenery 840-1 160 records):
  - Alpine 400-449 and 50-74 reverse;
  - Diablo 450 and 275-374, and 75-124 reverse;
  - Pacific Coast 250-274 and 400-410 reverse;
  - the Oval 25-74;
  - Surfers Road 25-99;
  - Amazon Falls 0-24 and 25-49 reverse.

  There, with the field's p95 of about 2 200, a frame stands near 3 000-3 400 records: **about 2 000 records to spare**.
- **Heaviest scenery spots** (model max): Metropolis road points 39 and 170-174 (3 682), Surfers Road 283-314 (2 534),
  Amazon Falls 114-155, Diablo 231-236 (2 379).

## 4. C. How the arcade's scenery objects work

### 4.1 Two mechanisms on the originals [R, V]

1. **Baked into the tile cells.** Every original course's ground, road, pit buildings, grandstands, crowd, trees and walls
   are world-space quads inside 128 × 128-unit cell objects (`model1-course-tables.md` §6), one polygon-ROM object per
   cell. No placement table, no per-object culling, no level of detail: a cell is drawn whole when it is in the
   visible set. Repeated shapes found in the tiles (`out/p28/snaps/props/baked_sheet.png`):
   - **Big Forest's trees**: 3-quad pyramid canopies 15 high and 6 wide (×253) and 4-quad canopies 12 × 8 (×101), each
     on a 3-quad trunk 2-3 high (×151, ×145), so a tree is **6-7 quads**;
   - Acropolis's columns: 16 quads (×15) and 4-quad pillars (×16);
   - Bay Bridge's thin red posts.

   Big Forest's cell 0x56 (the pit straight: pits, grandstand with a painted crowd) is 738 quads in 1 077 records
   (`snaps/props/BF_cell_56.png`).
2. **Spawn-list entities** (`model1-course-tables.md` §12, `spawn.py`). There are 24-byte records (x, y, z, yaw, type,
   handler, object list), created at course load as entities whose handler draws their object list with their own
   matrix. They pass the visible-cell test (`0xff5d93`) and are drawn before the tiles, so they take budget first.
   Bay Bridge has 107 such entities, Big Forest 32, Acropolis 14. The converted courses have **1-2**: the HUD map, plus
   the arcade start gantry on Alpine, Diablo and Pacific Coast [V].

### 4.2 Inventory of reusable props (the originals' spawn-list objects) [V decode, offline renders]

`snaps/props/sheet.png` (flat offline render, not the Model 1's look). Object = the first record of the entity's list.

| course | handler | count | polygon word | quads / records | size (x × y × z) | what it is (render) |
|---|---|---|---|---|---|---|
| Bay Bridge | 0xffacc6 | 7 | 0x1274ed | 45 / 57 | 3 × 4 × 3 | palm tree |
| Bay Bridge | 0xffb619 + 0xffb735 | 1 + 1 | 0x108295, 0x107e5b | 47 / 56, 84 / 87 | 13 × 18 × 9, 10 × 13 × 10 | lighthouse (two parts) |
| Bay Bridge | 0xffcbfc (type 32) | 4 | 0x112ddc | 32 / 38 | | arrow board |
| Bay Bridge | 0xffd1a5, 0xffd1cf | 1, 2 | 0x111978, 0x1116c5 | 68 / 68 | 1 × 28 × 0 | striped pole |
| Bay Bridge | 0xffc25d (type 1) | 5 | 0x16527d.. (8 frames) | 72 / 86 | 1 × 1 × 2 (scaled at draw) | animated figure or animal |
| Bay Bridge, Big Forest | 0xffaa67 | 10, 4 | 0x1260b6 | 16 / 19 | 4 × 11 × 1 | lamp post |
| Big Forest | 0xffabaa | 3 | 0x10bc15.. | 51 / 53 | 2 × 4 × 2 | hut or booth |
| Big Forest | 0xffd223/22b/237 | 3 | 0x1116c5 | 68 / 68 | 1 × 25 × 0 | striped pole |
| Big Forest | 0xffd60c, 0xffd746, 0xffd8ef, 0xffda84 | 1 each, one spot (−70, 30, −746) | 0x1084d0, 0x109c42, 0x109f3b, 0x10b424 | 398 / 428, 65 / 75, 22 / 35, 9 / 9 | 204 × 45 × 44 … | one animated landmark in four parts (a wheel, a sign, a lattice tower) |
| Acropolis | 0xffb54f | 1 | 0x10d039 | 190 / 204 | 13 × 13 × 4 | billboard with scaffold |
| all three | 0xffb07f, 0xffb08a/95/a0/ab, 0xffc17e | 1, 2, 7-10 | animated frame tables | | | start gantry, checkpoint gantries, grid boards (`gantry.py`, `spawn.py`) |

Baked props (Big Forest's tree: 6-7 quads) are not separate objects. They would be copied out of the tile quads by
shape.

### 4.3 Colour and light [R]

- A record carries no colour. `tex_adr` indexes the colour table (the program ROM read as 16-bit entries), whose
  entry picks a palette index in **the course's palette**. A converted course uses its template's palette (template
  2, Big Forest's: Alpine; template 1, Acropolis's: Diablo, Metropolis; template 0, Bay Bridge's: the other four) [V
  directory].
- A Big Forest prop keeps its colours only on Alpine. Anywhere else its quads need new colour entries chosen by
  nearest colour, as `assign_colours` does for the Saturn faces.
- Shading is flat per quad, from the record's normal and light mode (bits 17-20) against the light parameters sent with
  `0x06`. A prop brings its own normals. Whether the light table differs per course was not checked [?].

### 4.4 What placing one arcade prop on a converted course takes

| | baked into the cell (converter only) | as a spawn entity |
|---|---|---|
| data | the prop's quads translated and rotated into world space, added to the cell's quad list before `assign_colours`/`encode_object` | a 24-byte spawn record; an object list (16 bytes) pointing at a recoloured copy of the object when the template's palette differs |
| room | 40 bytes a record in polygon ROM (461 548 free); one colour entry per new colour per cell (3 800 free) | ~30 more records fit in each converted course's spawn slot (free gaps of 720-744 bytes at 0x2874e4.. ÷ 24) [V]; polygon ROM only for a recoloured copy |
| code | none | none, if an existing handler draws a static object; what each handler does besides drawing (animation, sound, **collision**: Pacific Coast stopped dead against Bay Bridge's boards in Phase 8) is unknown per handler [?] |
| cost a frame, visible | its records in the cell's size, on every frame the cell is in the visible set (even when the prop is behind the camera). A tree ≈ 7-12 records | its records + 1 object: ~30-60 µs of V60 time [V fit] and 34 display-list entries; counted before the tiles, so it pushes the far cells out first |
| reverse | drawn two-sided (`no_cull`) like all converted scenery; visible from both directions | the same object both ways |
| collision | none (scenery is not collision) | depends on the handler [?] |

Examples (records = quads × 1.7, the converter's current rate):
- **20 Big Forest trees** along one straight: ~140 quads → ~240 records, ~9.6 KB, 2-3 colours in each affected cell.
- **A Bay Bridge palm tree**: 45 quads → ~77 records, ~3 KB.

## 5. D. Finer geometry

- **The Saturn's resolution** [V]:
  - the road segment table slices the road 1 Saturn unit long, about 11.7 arcade units (`2026-10-big-forest-overlay.md`);
  - the converted courses' centreline has one point every 10.0 units;
  - the drawn road quads are a median 12-14 units long, against 8-10 on the originals;
  - the ground away from the road is 22-24 units, against 9.5-12.
- **Corner faceting** (the heading change between neighbouring centreline points) [V]: p95 4.8-13.0°, max 8-50°, on
  the converted courses (Diablo 13.0°, Metropolis 12.1°, Surfers Road 11.5°), against 4.5-8.6° p95 on the originals.
- **Hill faceting** [V]: the pitch change between points is p95 1.3-1.6° (Diablo max 5.8°), against 1.0-1.1° on the
  originals.
- **The Saturn carries no finer data.** Subdividing would interpolate (for example a spline through the slice heights
  and headings): new geometry, not recovered geometry [R].
- **What the shading does** [R, MAME `model1_v.cpp:1048`]: one brightness per polygon from its normal. Two facets
  1.5° apart differ by a fraction of a percent in brightness, so smoothing a gentle hill changes almost nothing inside
  the surface. **Faceting shows at silhouettes and outlines**: crests against the sky, the polygonal edge of the road
  and its paint through a corner, the big flat rock faces. In `snaps/diablo_start_rocks.png` the canyon rocks are a
  few large flat faces; in `snaps/diablo_crest.png` the crest's edge and the road edge show as straight segments.
- **Cost model** [V model] for one level of lengthwise subdivision of everything within 15 units of the centreline (road,
  paint, verge):

  | courses | quads in the drawn cells | records at 1.7 records a quad |
  |---|---|---|
  | converted | median 262-305, max 440-995 | **+450-540 a frame median, +760-1 720 max** |
  | originals | 648-843 | |

  Polygon ROM: the near-road quads of a course (2 100-2 900) at 1.7 records and 40 bytes come to **150-200 KB a
  course**. That is about **two courses** inside the 396 KB above the floor.
- **Kerbs:** the converted kerbs are Saturn road-paint quads (group 2). Rounder kerbs mean more of them per corner, under
  the same cost rule.
- **Collision:** none needed. The drawn road and the collision are separate (`model1-tgp-collision.md`). A drawn
  surface that departs from the collision heights by more than a few hundredths of a unit makes the car float or
  sink visibly. A smoother drawn hill would want the collision profile smoothed the same way, which costs TGP words
  only if quads are added (7 631 words free; the floor test is `tgp_budget >= 7_500`) [R].

## 6. E. View distance

- **The rule** [R `0xff7beb..0xff7e1e`, V table bytes, identical in the original set]:
  - The camera's 128-unit cell is computed, and its 5×5 neighbourhood walked in the order of the table at `0xff7e1f`:
    own cell, the 8 around, then the 16 outer.
  - Cells off the map edge are masked (R17), and a yaw mask comes from a frustum test of the cell corners through the
    TGP (`0xff7ea1`; `0xff7e51` when looking steeply down).
  - The kept cells are written to 0x501cc0 and drawn in that order.
  - There is no distance cut, no fog and no far clip (MAME clips only at the near plane). Beyond the cells there is the
    2D backdrop.
- **The originals and the converted courses use the same grid and the same rule.** Modelled at every road point
  [V model]:
  - the drawn cells reach a **median of 356-412 units** ahead (minimum about 250) on every course, originals included;
  - the road stays inside the drawn cells for a median of 333-375 units ahead;
  - the p5 is 199-280 units, where the road leaves the 5×5 block sideways.
- **Pop-in:** when the camera crosses a cell boundary, a whole row of cells about 256 units ahead appears at once
  [R from the rule]. On the originals the budget skip also drops the outer cells on 17-22 % of frames, so in
  practice **they draw less far than the converted courses**, which almost never skip.
- **Extending it:**
  1. More cells: a 7×7 walk (49 cells) does not fit the 32-bit masks (R17 and the yaw mask hold 25 bits), so it means a
     rewrite of `0xff7c1e..0xff7e1e` and of the yaw test in the boot ROM. The 0x501cc0 list area and the
     visited-cell bitmaps would grow [R]. Cost: about 1.4× more cells a frame from the 16 outer to the 24 next, for
     about +600-1 000 scenery records median on a converted course [? estimate from the per-cell sizes].
  2. **Without code:** a cell object can hold geometry anywhere, since it is world-space and binned by centroid by the
     converter's choice. A copy of a distant landmark's silhouette (a mountain ridge, a tall building) placed in a
     nearer cell's object is drawn from further away. It costs that copy's records in the nearer cell. A distant
     silhouette is usually large and simple, so tens of quads.
  3. Raising the budget (§2.3) makes the originals draw as far as the converted courses do. It does not extend the
     converted courses.

## 7. G. What could make additions unsafe

- **The start window** carries the field, the gantry and the figures, 3 000-4 300 records of "other". Diablo,
  Metropolis and Pacific Coast already pass the budget there. Scenery added in the start cells is skipped or pushes
  the outer cells out on those frames [V].
- **Entities are drawn before the tiles.** Props added as entities take budget from the far cells, not from themselves
  [V order].
- **The reverse direction** draws the same tile tables, chosen by camera cell and yaw (nothing forward-only).
  Converted quads are two-sided, so baked props show from both directions. Reverse has its own heavy spots (Diablo
  reverse point 178) [V, phase 26 recon §4].
- **The pit stop** adds the crew entities (6 entities) on the start straight. Not measured here [?].
- **The attract demo** races the originals. The deviations list says it may show a converted course (open). Additions
  there behave the same [R].
- **The HUD map** is its own object (drawn early in the frame, small). It is unaffected [V seq].
- **Linked play** (unsupported): the 5 000 budget branch is tied to a read in the comm board's range, so a linked
  cabinet would skip earlier [R, ? identification].
- **Shared room:** the polygon ROM (461 548 bytes) and the colour table (3 800 entries) serve all seven courses. The
  colour table is the tighter: crossing colours inside a strip, as the originals do (an entry per record), would need
  thousands of entries [V counts].
- **Per-cell cap:** a cell object over 5 500 records is cut by `split_quads` (`capped_cells`). Today's largest is 789
  records, so this is far off [V].

## 8. F. Verdicts and candidate first steps

| direction | verdict | bounding number | why |
|---|---|---|---|
| 1. more scenery objects | **feasible** | per frame: about +1 000-1 500 records on most of every lap and about +2 000 on the lightest stretches (5 500 less a converted frame's p95 of 2 900-4 700); in total: ~396 KB of polygon ROM ≈ **9 900 records ≈ 5 800 quads ≈ 800 arcade trees** across all seven courses; colour entries 3 800 | records cost no emulated time; the converted courses use half the originals' scenery a frame; passing the budget drops only far cells, as on the originals |
| 2. finer geometry | **feasible in places** | doubling the road strip: +450-540 records a frame median (fits), but 150-200 KB of polygon ROM a course (fits about two courses) | the ROM is the limit, not the frame; shading hides most of it except at silhouettes and road outlines |
| 3. longer view distance | **not without giving something up** (a boot-ROM change of the cell walk; or nearer copies of far silhouettes at their record cost) | the fixed 5×5 cell block: 356-412 units ahead median on every course | the draw distance is the cell rule, not the budget |

**Raising the frame budget** (one immediate, `0xfe11bd`/`0xfe11d3`) would also remove Diablo's, Metropolis's and Pacific
Coast's start skips at no measured emulated cost [V experiment]. It is a boot-ROM change and it changes the originals' own
behaviour (more far trees on 17-22 % of their frames). That is Pascal's call. Without it, Diablo's start could instead be
relieved where the budget goes: the gantry object of 599 records and the figures of about 1 400 [? attribution].

**Re-chaining** the converted cells is a lever for all three. Inside today's colour scheme it is worth up to 8-10 % of
records: an edge-connected same-colour floor of 1.59-1.66 records a quad against 1.73-1.77 today [V offline count, an
optimistic floor]. The originals' 1.15-1.24 needs a colour entry per strip step, which the 3 800 free entries cannot
pay for.

**Candidate first steps** (each buildable and shown on one course):

1. **Arcade trees on Alpine** (Big Forest's palette, so no recolouring). About 30 Big Forest trees (6-7 quads each, ~200
   quads, ~350 records, ~14 KB, a few colour entries) baked into the cells of Alpine's road points 400-449 and 0-25,
   the lightest section (scenery 894-1 022 records, frame p95 there about 3 000). Cost: +350 records on frames that
   see those cells, so still under 4 000. Risk: low; converter-only. Measure with `p28_frame.lua`, and show stills to
   Pascal.
2. **A Bay Bridge palm tree row on Pacific Coast or the Surfers courses** (template 0, Bay Bridge's palette): 10 palms ×
   45 quads ≈ 770 records baked into the cells along Surfers Road's road points 25-99 (scenery about 900-1 075 there).
   Cost: ≤ +770 a frame. Risk: low; it tests a 45-quad prop's look at speed.
3. **Diablo's start relief, measured**: a build with the budget immediate at, say, 8 000, run through `p28_frame.lua` on
   Diablo, Metropolis and Pacific Coast. Expect 0 skips, render rate 28-29, 0x501148 = 0, and a still pair of the
   start. Cost: 4 bytes of boot ROM. Risk: the originals change too (decide with Pascal). The alternative is to leave
   the budget and lighten the gantry object.
4. **One smoothed crest on Diablo**: subdivide the road, paint and verge quads ×2 lengthwise over one hill (about 40
   road points, a few hundred quads, ~600 records, ~25 KB), the collision profile left alone. A still pair against
   today at the crest. Cost: ~+300-500 records on those frames (Diablo's race p95 is 3 191). Risk: drawn road against
   collision height; shows whether smoothing is visible at all.
5. **A far silhouette in a near cell** on Metropolis or Alpine: copy one landmark's outer faces into the cell 2 rows
   nearer and compare the pop-in point in two stills. Cost: tens of records. Risk: low.

## 9. Not established

- What each spawn-list handler does besides drawing (animation, sound, **collision with the car**), and the entity
  table's capacity.
- The attribution of Diablo's 599-record object (gantry) and the 81-199-record animated objects (start figures):
  inferred from the animation, not traced.
- MAME's host-side render cost at higher record counts (the real-time speed on Pascal's machine).
- Whether the light parameter table differs per course (an arcade prop's lighting on another template).
- Full-lap measured coverage: the autopilot covered 170-289 of 330-457 road points on the converted courses. The rest
  is the cell model (Jaccard 0.84), and "other" in the uncovered sections is not measured.
- The pit stop's frame cost; the attract demo on a converted course.
- How a Saturn mesh would be subdivided (no finer data exists). The look of a smoothed crest was not tried.
- The 7×7 cell-walk cost and design: estimated from the per-cell sizes only.

## 10. Files (all git-ignored under `out/p28/`)

- Scripts:
  - `p28_frame.lua` (the logger and the harness switches);
  - `run_course.py`, `analyse.py`;
  - `static_cells.py` (→ `cells_p27play1.json`);
  - `cellmodel.py`, `lapmodel.py` (→ `lapmodel.json`);
  - `geom.py` (→ `geom.json`);
  - `render.py`.
- Runs `runs/<tag>/`:
  - `h0`-`h9`, `hr3`, `hr5`, `a3`, `a6`: held clock; the summary is `summary_held.txt`;
  - `n*`/`r5`: first set, clock not held, contaminated by the attract after the time-out, superseded;
  - `e_bf`, `e_bf_b20k`: the budget experiment;
  - `e_db`: Diablo stills and the display-list decode.
- Images:
  - `snaps/budget/bigforest_2001_5500_vs_20000.png`;
  - `snaps/diablo_start_rocks.png`, `snaps/diablo_crest.png`, `snaps/diablo_sheet.png`;
  - `snaps/props/sheet.png` (the spawn props), `snaps/props/baked_sheet.png` (baked tree, column and post shapes),
    `snaps/props/BF_cell_56.png`.
