# Phase 8: the remaining six courses (M5)

All seven Saturn-only courses now convert, fit the stock ROM images and drive in MAME at the arcade render
rate, selected from the ten-course Practice row (Phase 7). Build and drive them all:

```sh
source local.env
.venv/bin/python spike/ten_course_build.py out/p8/build [seconds]   # summary.txt: one block per course
mame vr -rompath out/p8/build
```

## Per course

Placed at the template's player spawn (see below), 90 s autopilot drives in MAME (the race starts at frame
~1603, the countdown holds the car ~290 frames more, so ~57 s of driving):

| course | host bank / template | slices usable / in lap | start (lap pt, turn over 300 u) | tarmac quads (from slices) | verges (dropped) | TGP KB | blob KB | scenery quads / cells / poly KB | forward / back (units) | rate |
|---|---|---|---|---|---|---|---|---|---|---|
| ALPINE | 3 / Big Forest | 526 / 526 | 279, 56° | 363 (526) | 668 (58) | 109 | 93 | 1631 / 50 / 130 | 3612 / 0 | 28–29 |
| AMAZON FALLS | 1 / Bay Bridge | 462 / 462 | 96, 41° | 372 (462) | 564 (180) | 101 | 78 | 1649 / 46 / 131 | 3416 / 0 (a lap: 0'50"56) | 28–29 |
| DIABLO CANYON | 2 / Acropolis | 641 / 641 | 36, 76° | 496 (641) | 917 (75) | 146 | 94 | 2054 / 54 / 163 | 2908 / 173 | 28–29 |
| METROPOLIS | 2 / Acropolis | 386 / 386 | 147, 28° | 255 (386) | 379 (131) | 73 | 81 | 1328 / 39 / 106 | 3470 / 52 | 28–29 |
| PACIFIC COAST | 1 / Bay Bridge | 564 / 564 | 249, 45° | 389 (564) | 724 (54) | 114 | 88 | 1633 / 42 / 130 | 2995 / 78 | 28–29 |
| SURFERS OVAL | 1 / Bay Bridge | 714 / 602 (infield left out) | 99, 63° | 618 (714) | 1059 (177) | 173 | 87 | 1922 / 52 / 153 | 1732 / 74 | 28–29 |
| SURFERS ROAD | 1 / Bay Bridge | 690 / 690 | 21, 54° | 595 (690) | 1108 (82) | 173 | 94 | 1929 / 53 / 154 | 2173 / 116 | 28–29 |

TGP data: 892 KB for the seven (unmerged: 1173 KB) against 985 KB free (the 0xff tail from word 0x4b170 plus
the zero fillers between the originals' list blocks); 23,744 words remain after the build. Blobs: 615 KB in the
banks' free space. Scenery: 970 KB of polygon ROM. No course needed thinning (`CoursePlan.thin` is 0.0
throughout; `convert_tiles(thin, keep_near)` is there for the next course that does). The three originals drive
identically (`test_directory_build_drives_the_originals_identically`).

## What it took

1. **Lap ordering** (Task 1, commit 106fdae): Pacific Coast and the Surfers files did not order. Touching
   polygons (distance < 0.5 units, not only shared edges) are adjacent; after the start-line cut the cut side
   bridges to unreached slices; a degenerate start slice moves to a proper quad slice with a clockwise axis.
   The oval file carries an unused 112-slice infield, so it orders at 80 % coverage.
2. **Merged straights** (Task 2): chains of up to six slices turning ≤ 3° in all, same width within 10 %,
   rear corners on the previous front corners within 0.15 of the width, found within four lap-order entries
   (side-by-side strips interleave), fuse into one quad; the fused quad must be convex, keep its width and hold
   every replaced slice's spine and corners; grown triangles and slivers over 40 units never fuse; verges fuse
   per side under the same checks. Verges whose centre lies on tarmac are dropped.
3. **How the TGP picks a quad** (Task 2, from the program disassembly, handler 0x489–0x4d5 + 0x4f5): every
   containing quad is a hit, and the hit whose height is nearest the car's current height is reported (exact
   ties to the last in list order). Phase 5's "last quad of the list" was that tie case. A verge sampled off
   the tarmac plane therefore captured the car wherever the two overlapped (Alpine sat on grass for 12 s with
   the merged data): verges now take the tarmac edge heights straight across, and tarmac quads grow 4 units a
   side (`TARMAC_GROW`) so strip seams (Big Forest's start straight has an 8-unit one) and bend wedges are
   not read as grass.
4. **Allocation** (Task 3): the TGP and polygon allocators work from the blank runs as the ROM stands
   (`copro_free_runs`, `poly_free_runs`), so a second course lands after the first; the polygon palette is one
   block for every course (boot routine 0xfe6b04 copies program ROM 0x2ec980..0x2ed082 to palette RAM
   0x902000 whatever the course; the three originals' palette RAM dumps are identical).
5. **Where the player spawns** (Task 4): relative to the template's road line 0, not at one absolute point —
   Big Forest 37 units left of road point 13 (−230.4, −269.6), Bay Bridge on road point 0 (−205.4, 2.5),
   Acropolis on road point 0 (−319.7, −190.8), heading +z (measured in MAME). Courses on the Bay Bridge or
   Acropolis template started 130 units before the aimed point, facing across the road, on sand.
   `place.GRID_OF_COURSE` aims the converted road at the spawn itself.
6. **A straight after the grid** (Task 4): Pacific Coast's first start turned 189° within 300 units and the
   player crashed into the sixteen-car pile-up at the hairpin four times. `choose_placement` ranks starts by the
   turn over the 300 units after the grid (15° buckets), then map fit, tries candidates until the lap orders
   from that start, and re-aims on the final centreline.

## After the review (fix pass)

- **TGP windows.** The TGP sets its ROM window from a list's or a quad's own address and walks on with a
  15-bit index, so a list or a 16-word quad crossing a multiple of 0x8000 words reads I/O space instead (the
  originals never cross; Pacific Coast's cell 5387 lost three of six entries). `install_collision` now keeps a
  course's list block inside one window and aligns its pool to 16 words; `test_build_all_keeps_every_list_and_quad_inside_a_tgp_window`.
- **The oval's infield** is grass without road tables (it had been tarmac with a borrowed lap position; left
  out entirely, the car fell into the void past the 44-unit verge).
- **Crossings.** Keeping verges over another deck (the reviewer's suggestion) was measured worse on Metropolis
  (16 deck-height jumps against 2) because the TGP compares |height| with the car's height and the converted
  courses lie below y = 0; dropping them stays, crossings are an open deviation for M6.

## Snapshots (out/p8/build/run*/snap)

- Select screen: generated panels for every entry (ACROPOLIS / ALPINE / AMAZON FALLS visible together).
- Amazon Falls crosses the line in 0'50"56 and gets EXTEND TIME; Metropolis, the Oval and Alpine run at speed
  with the host's sea/hills backdrop.
- Diablo Canyon's road reads yellow over a blue void: the host palette's nearest colours for sandy ground and
  the Saturn sea plane (fidelity item for M6).
- Pacific Coast and Surfers Road each show one stop (0 km/h) ~35 s in — a crash against the field or a spin;
  both still clear the progress gate. The Oval's and Surfers Road's logs lose 500–600 frames of player calls to
  crash sequences (M6: opponents and AI lines per course).

## Open after Phase 8

Per-course backdrops (the Saturn BGS compression is still unknown; Task 6 of the plan was optional and left),
Diablo's colours, the crash spots above, per-course music, labels per slot, the centred wheel landing on entry
5 (ask Pascal). Next: M6 (balance: opponents, laps, time limits per course), M7 (packaging), then the PS2
courses.
