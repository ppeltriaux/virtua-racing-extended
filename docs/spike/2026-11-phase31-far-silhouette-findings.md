# Phase 31: a far silhouette in a near cell, on Metropolis (15 Nov 2026) — findings

**Prototype, kept on Pascal's word; not merged.** Pascal was shown four full-screen stills (normal and reverse, main against the prototype) and ran `out/p31play1` once on 15 Nov, 107 s, MAME's average speed 100.00 % (recording kept: `out/rec164/inp/pascal-2026-11-15-p31silhouette-107s.inp`); asked whether to keep it, drop it, or keep it and have more spots done: "yes it s good keep it". What they drove was not stated; more spots were not asked for. Not the word to merge. Reviewed since, and fixed (§10): the set after the fixes is `out/p31play2`, the same objects and pictures as the set Pascal drove, with the 59 colour entries at another address. Branch `phase31-far-silhouette`; not merged, not
pushed.

Pascal asked for "more polygons" on the tracks: scenery objects, then finer geometry, then a longer view distance. This is a
first step of "view distance", the recon's candidate 5 (`2026-11-phase28-polygons-recon.md` §6 and §8): the game draws only the 5×5
block of 128-unit cells around the camera, so a far structure appears a whole cell row at a time; a cell's object is world-space
geometry, so a copy of that structure's faces in a nearer cell's object is drawn from further away. Converter only: no boot-ROM or
code patch, no spawn entity, the collision untouched.

Marks: **[V]** measured in this phase; **[R]** read in code; **[?]** not established. Every number from runs is from one run each
unless stated; all runs are MAME 0.289 headless.

## 0. The answer in brief

- **Built** (converter only), one place on one course: the far end of Metropolis's long straight. The low banded building across
  the end of the street (30 faces) and the tall banded block beside it (15 faces), both binned in cells of row 13, are also put in
  cell 183 (row 11); the block also in cell 184. **+60 faces, +120 records** (cell 183 +90, cell 184 +30), **23 328 bytes** of
  polygon ROM, **59 colour entries**.
- **It works as the recon said** [V]: in the normal direction the building at the end of the street is on screen 186 frames
  (3.2 s, road points 44 to 68, about 240 units) before main draws it: it is there when the car comes out from under the bridge
  instead of appearing half-way down the straight. In reverse the block shows ahead of the car up to 428 frames earlier, as a
  sliver first, and for 62 frames before main's pop-in as the whole block.
- **The double draw** [V]: while both the copy and the original cell are in the 5×5 block the same polygons are drawn twice at
  the same depth. Over a dense sample (every 4th frame while both are listed) the picture is main's pixel for pixel in all 25
  frames of the normal direction and 33 of 83 in reverse; in the other 50, one stretch of 3.4 s passing the tall block, the dark
  part of the block's front face is (8,8,8) where main has (0,0,0), on 145 to 1 068 pixels, and nothing else differs. The cause
  is established (§3.3): two of the block's walls sort at exactly the same depth and the last one pushed wins; on main that is
  the hidden back wall, on the prototype the copy's front wall. Not lighting, and no flicker. No scheme avoids the double draw.
- **Frame**: on the passes that draw a copy, +120 records median and maximum (normal), +90 median, +120 maximum (reverse); 22-29 %
  of a race's passes. The busiest pass measured 6 715 records (main 6 595) against the 10 500 budget; a lap with a pit stop
  7 068. No list skipped, the overrun counter 0x501148 never moved, the V60's busy time identical to main's to the microsecond in
  the replays, render rate 28-29 (§4; §4.4 says which of these a test asserts and which one scratch script measured once).
- **Everything else is main's**: the set differs from `out/p28play2` in 14 bytes of program ROM inside Metropolis's two tile
  records (a span of 26), 116 bytes of program ROM that were erased (the colour entries) and 23 328 bytes of polygon ROM that were erased (the two
  new objects). Boot ROM, data ROM, TGP data (the collision) and TGP program byte for byte. Fed main's recorded inputs, the race
  is identical pass for pass over 4 177 passes, both directions.
- **Honest one-line read:** at this spot, in the normal direction, it is a visible improvement for almost nothing per frame; but
  it is one hand-picked building. It does not lengthen the view distance in general: the ground, the road and every other
  building of the far row still appear when they did, and each further place needs its own measurement and choice.

## 1. Which place, and how it was found

- **The measure** [V]: one autopilot race of Metropolis in each direction on main's set (`out/p31/runs/m6n`, `m6r`), with the
  game's visible-cell list (0x501cc0) logged every frame; the race replayed from its recorded inputs with a still two frames before
  and four after each frame where the list gains three or more cells (38 such events a lap normal, 33 reverse); the pairs looked at
  for a structure that appears against the sky on the racing line (`out/p31/scratch/events.py`, `sheet.py`).
- **An offline ranking did not find it** [V]: projecting every far cell's quads from the road point before it enters the block
  (`landmarks.py`, no occlusion) put Metropolis's 104-unit tower first (cells 134/135/150/151). In the stills that tower is hidden
  behind the bridge on its approaches. The frames decided, not the ranking.
- **Chosen: the far end of the long straight** (road points 53-106, the straight along cell column 7, driven towards +z in the
  normal direction):
  - at road point 66-68, when the camera enters row 11, cells 213-217 (row 13) are listed and a banded building appears at once at
    the vanishing point of the street (main's stills at frames 6146 and 6152, `out/p31/look/normal_f6146.png` left panel and
    `normal_f6152.png`);
  - in reverse the car drives the parallel street (cells 168 to 184, column 8, towards +z too) and the same row appears ahead of it
    when it enters row 11 (frames 7622 to 7628).
- **Two structures there** [V, decoded from the built set]:
  - the low building across the end of the street: x -136..-52, z 745..770, up to 59.6; six walls and 24 window bands in cell 215.
    It is what pops in on the straight;
  - the tall block beside it: x -18.6..51.4, z 746.1..781.8, up to 92.4; three walls and 12 bands in cells 215 and 216. It is what
    shows in reverse. From the straight it is all but hidden behind the street's right side (§6: the first build copied only this
    one and changed 24-53 pixels on the straight).
- Alpine was not tried. Its largest offline candidates were 2.5-8 % of the screen against Metropolis's 8-19 %; that ranking is the
  one that misled on the tower, so it says little.

## 2. What was built

- `vrtools/convert/silhouette.py` [R]: `FarCopy(source, into, min_top, min_rise, within)`: the faces of cell `source` whose
  highest corner reaches `min_top` (and that rise `min_rise`; with `within`, only those wholly inside a box in x and z: one
  structure of a cell that holds several) are added to each cell of `into`. `far_copy_cells` works on the binned quads and returns
  the changed cells only. A copy that cannot be made is a `ConvertError`.
- `vrtools/arcade/farcopy.py` [R]: `install_far_copies` writes each changed cell a **new** object (its own quads and the copies,
  coloured as the converter colours every cell) in the polygon ROM's free space, its colour entries in an erased run of the program
  ROM, and repoints the cell's tile record. `ten_course_set` calls it (`install_far`) after its last writer.
- **Why after everything else**: polygon objects and colour entries are placed first-fit, course after course. A cell that grows
  inside `convert_tiles` would move every later object and colour entry of Metropolis and of the three courses built after it.
  Writing the two cells again at the end leaves every other byte where it was. The price: the two cells' old objects (302 and 158
  records, about 18.5 KB) stay in the ROM unread.
- **The colour entries** live in a block reserved for them: `far_colour_block()`, the 256 bytes just below the start gantry's
  block at the top of the code area, program ROM 0x28f870-0x28f96f (128 entries; Metropolis's 59 are entries 0x87c38-0x87c72,
  bytes 0x28f870-0x28f8e5). It is this feature's own reserve: erased in the original, above the fixed layout, left out of the
  select pictures' free-run search (`picture_exclusions`) and of the reverse annex's region (`annex_regions`), as the gantry's
  block is. `farcopy.colour_run` takes the entry after the last one in use in the block and never searches the ROM for erased
  bytes; a block without room is a `PatchError`. The whole program ROM is the colour table (`colours.py`); the block is below
  the reverse annex and the direction screen's block, so `max_colour_entry` is unchanged and the two standing tests that bound
  it still hold [V]. (**Before the review** the entries were put in the first long enough run of 0xff bytes found in the code
  area. On `out/p31play1`, the set Pascal drove, that was 0x287530-0x2875a5: the unused tail of Alpine's spawn-list slot. A later
  table holding such a run at a lower address would have been written over silently: review I1.)
- **The plan** (`tencourse.py`): `CoursePlan.far_copies`, default `()`. Only Metropolis names any: `METROPOLIS_FAR`, three
  `FarCopy` over two boxes (`METROPOLIS_FRONT`, `METROPOLIS_BLOCK`), each pinning the number of faces its box is meant to select (30, 7, 8:
  another count is a `ConvertError`). A cell over the record cap takes no part in a copy (`ConvertError`).
- **Which cells, and why two rows nearer**: a cell is drawn when the camera's cell is within two of it. The buildings are in row
  13, so drawn from row 11. Cell 183 (column 7, row 11) is drawn from row 9, where the straight begins; cell 184 (column 8, row 11)
  lies straight ahead on the reverse approach.
- Test harness: `tests/test_frame_rate.py` made every course's run whenever one parameter of a test was selected (17 races for
  `-k entry_6`). It now makes only the selected parameters' runs (`selected_keys`).

## 3. The look

Stills: `out/p31/look/` (`NOTE.txt` says what each shows). Left main's set, middle the prototype, right the differing pixels; the
same frame of the same recorded race on both sets.

### 3.1 Normal direction [V]

| frame (lap 2) | road point, camera cell | differing pixels | what |
|---|---|---|---|
| 5960 | 44, (7,9) | 0 | |
| 5966 | 44, (7,9) | 67 | first frame that differs |
| 5972 | 45, (7,9) | 360 | under the bridge: the building's bands where main has a gap of backdrop |
| 6026 | 55, (7,10) | 556 | |
| 6086 | 61, (7,10) | 1 169 | the building and a sliver of the block at the end of the street |
| 6146 | 68, (7,11) | 1 713 | the last sampled frame before main's pop-in |
| 6152 and the 19 later frames with both drawn | (7,11) on | 0 | main has drawn the row; identical |

Lap 1 in traffic is the same (first difference frame 2362, 1 606 pixels at 2674). The building's base meets the end of the street;
I see no gap under it in the pairs. The ground and the smaller structures of rows 12-13 are not copied and still appear at road
point 66-68, behind and below the building, where they are hard to see.

### 3.2 Reverse [V]

| frames (lap 2) | camera cell | differing pixels | what |
|---|---|---|---|
| 7200-7298 | (7,9) | 76-286 | a thin vertical sliver of the block between nearer buildings |
| 7304-7346 | (7,10) | 174-947 | more of it, then out of view |
| 7352-7554 | (7,10), (8,10) | 0 | not in view |
| 7560-7622 | (8,10), (8,11) | 52-2 142 | the block grows where main shows the backdrop's skyline |
| 7628 on | (8,11) | 0 | main has drawn the row |

A modest gain: one building of a row whose other buildings still pop in at 7622-7628 (`reverse_f7616.png` against
`reverse_f7634.png`).

### 3.3 The double draw

- **It cannot be avoided by choosing cells** [R]: the copy's cell N is drawn from every camera cell within two of N, the original's
  cell F from every camera cell within two of F. A copy that helps is one or two rows from F, so some camera cells are within two
  of both (here rows 11-13). A cell's object cannot depend on where the camera is. Moving the faces instead of copying them would
  take the building away from every camera cell that sees F and not N (the reverse lap's return along row 13, for one).
- **What it does in MAME** [R `model1_v.cpp` `quad_t::compare`, `sort_quads`]: all of a frame's polygons are sorted by depth, the
  converted scenery at each polygon's farthest corner; polygons at exactly the same depth are drawn in the order they were pushed,
  the last on top. The copy is the same corners, normal, flags and palette index as the original (decoded and compared [V]).
- **Measured, densely** [V, `out/p31/look/double_draw_reverse.txt`, `double_draw_normal.txt`: every 4th frame of the stretches in
  which the game lists a copy cell and an original cell together, the same replays on `out/p28play2` and the prototype]:
  - normal direction: 25 frames, all main's pixel for pixel;
  - reverse: 83 frames, 33 identical; **50 differ, one continuous stretch, frames 8068 to 8264** (3.4 s, the car coming back along
    row 13 past the tall block, camera cells (9,13) and (8,13)), 145 to 1 068 pixels a frame, **every one of them (0,0,0) on main
    and (8,8,8) on the prototype**, 27 357 pixels in all.
  The first, sparse sample of this document had hit three frames of that stretch (8100, 8160, 8220) and I wrote "3 of 45"; the
  stretch is continuous.
- **The cause: a depth tie broken by push order; established** [V, `out/p31/look/display_list_f8160.txt`, from a display-list
  dump (`dlist_log.lua`) at frame 8160 on both sets]:
  - the light vector, the matrix and every other state command in force are identical at the objects of cells 215, 216 and 183,
    and identical between the two sets; the cell objects come in the same order on both, 216, then 215, then 183 last. So the
    copy is not lit differently: my first reading ("the copy is lit one step lighter", and "window bands") was wrong (review I2).
  - The tall block has three walls: two palette-black ones (west, in cell 215; east, in cell 216) and the front one, a
    (16,16,16) palette entry lit to (8,8,8) at this frame (cell 216). Its stripes are the cream bands; the differing pixels are
    the dark wall between them.
  - The front wall and the west wall share two corners exactly. At frame 8160 the farthest corner of both is the same shared
    corner (-18.16, 9.66, 746.70), depth 146.316 for both through the list's matrix: an exact tie.
  - On main the tie goes to the west wall (cell 215 is pushed after cell 216): the **hidden back wall** is drawn over the front
    wall where they overlap on screen, black. On the prototype cell 183 is pushed last and its object holds the black walls
    first and the front wall last, so the front wall is on top, (8,8,8). The prototype's picture is the geometrically right one
    there; main's is its own sort artefact, one grey step away.
- **Can a tie give a larger artefact for these two buildings?** [V decode, R] A tie needs two faces whose farthest corner is the
  same point, so in practice faces that share a corner, and it shows only where those two overlap on screen. The copy changes
  the outcome only by being pushed later than the originals. The pairs that share a corner and differ in palette colour:
  - among the 45 copied faces: black with (16,16,16) (the case above), black with (0,0,24), (0,0,24) with (0,0,48) (the low
    building's walls: black and two dark blues), and one pair of bands, (128,128,152) with (160,160,176);
  - a copied face with a face of cells 215/216 that is not copied (the buildings' podium and ground at the walls' feet): a black
    or dark blue wall with a grey (104-136) face, 14 pairs.
  The first group can only exchange near-black shades, or two greys of one band row. The second could draw a strip of dark wall
  over grey podium (or the reverse on main) where a wall's foot and the podium's top overlap on screen with their farthest corner
  shared. **It was not seen**: in the 108 dense frames and the 45 sparse ones with both listed, the only differing colour pair is
  (0,0,0) to (8,8,8). It is not excluded for camera positions the autopilot did not take [?]. Whatever a tie does, it stays
  inside the two buildings' own outline, and main already resolves the same ties by push order.
- In the 123 sparsely sampled frames where no copy cell is listed, 0 pixels differ.

## 4. The numbers

### 4.1 The bytes [V]

`out/p31/scratch/compare_sets.py` (kept: `out/p31/compare_p28play2_p31play2.txt`, `compare_p31play1_p31play2.txt`, and
`compare_p28play2_p31play1.txt` for the set Pascal drove); `out/p28play2` is a build of main.

**`out/p31play2` (after the review) against main's `out/p28play2`:**

| region | result |
|---|---|
| boot ROM, data ROM, TGP data ROM (the collision), TGP program | identical |
| program ROM | 130 bytes differ: 14 inside Metropolis's tile records for cells 183 and 184 (a span of 26 bytes, 0x27fee0-0x27fef9), 116 that were erased, the 59 colour entries (0x28f870-0x28f8e5, in `far_colour_block`) |
| polygon ROM | 23 328 bytes written at 0xf8f674-0xf95194, all erased before (23 139 differ from 0xff) |
| tile records of the ten entries | differ on entry 6, cells 183 and 184, only; every other record names the same bytes |
| zip members that differ | `epr-14882.14`, `epr-14883.15` (program), `mpr-14896.32`, `mpr-14897.33` (polygons) |
| polygon ROM free | 461 548 → 438 220 bytes (the floor is 65 536) |

The other nine courses are byte for byte main's. The same is asserted in the test session against the set made from the same
conversions without the copies (§5).

**`out/p31play2` against `out/p31play1` (the set Pascal drove):** only the program ROM differs, 236 bytes: the 59 colour entries
are at 0x28f870-0x28f8e5 instead of 0x287530-0x2875a5 (the old place erased again), and the two tile records name the new entries
(0x87c38 and 0x87c5d for 0x83a98 and 0x83abd; 4 bytes). The polygon ROM (the two objects), boot ROM, data ROM, TGP data and TGP
program are identical. The same replays on both sets give the same picture in all 322 stills compared (169 reverse, 153 normal)
and the same state pass for pass [V, `out/p31/runs/dd_p1_*`, `dd_p2_*`].

**Against which main:** "byte for byte main's" was shown against main before Phase 29 (`fef6ce8`, `out/p28play2`). Once Alpine's
trees (Phase 29) are in, Alpine's scenery grows and every polygon-ROM address quoted here moves; what should then hold is the
same statement against that main's set, to be shown again after the merge.

### 4.2 The frame [V]

| run | passes | passes drawing a copy | added records, median / max | busiest pass | lists skipped | 0x501148 | worst V60 busy | render rate |
|---|---|---|---|---|---|---|---|---|
| identity test, normal (150 s) | 4 177 | 934 (22 %) | 120 / 120 | 6 715 (main 6 595) | 0 | still | 12 093 us (main 12 093) | |
| identity test, reverse | 4 177 | 1 087 (26 %) | 90 / 120 | 5 396 (main 5 396) | 0 | still | 12 041 us (main 12 041) | |
| standing test, entry 6 (150 s, clock held) | 3 511 | | | 6 715, need 6 464 | 0 | 0 → 0 | 12 699 us | 28-29 |
| standing test, entry 6 reverse | 3 511 | | | 5 396, need 5 275 | 0 | 0 → 0 | 12 540 us | 28-29 |
| standing test, Metropolis pit lap | 3 511 | | | 7 068 | 0 | 0 → 0 | 14 489 us | 28-29 |
| look replays (170 s), normal / reverse | 3 890 each | 1 091 / 1 134 | 120 / 120 and 90 / 120 | 6 715 / 5 396 | 0 | still | as main's | 28-29 both sets |

The budget is 10 500; two vblanks are 34 770 us. The added records per pass take the values 0, 30, 90 and 120 only (cell 184
alone, cell 183 alone, both). The reverse race's busiest pass is not one that draws a copy.

### 4.3 The race [V]

On the same battery RAM, main's equivalent (the set without the copies) with the autopilot, then the prototype fed the recorded
wheel and pedal: the state at the end of every logic pass (`pass_state.lua`: clock, all 16 cars' x, z, road point, speed, lap, the
frame the pass ends in) is identical over 4 177 passes, normal and reverse. The two look replays against `out/p28play2` are
identical too (4 753 passes each; `pass.txt` the same file).

### 4.4 What a test asserts, and what one scratch script measured once

- **Asserted by the branch's tests** (every run of them): the bytes against the set without the copies (§4.1's table, but against
  that set, not `out/p28play2`); the two cells' faces; the race pass for pass on recorded inputs, both directions; per pass, the
  records never fewer than without the copies and at most 120 more, no list skipped, the overrun counter still, the frame inside
  the budget; the standing rate test's three measures for Metropolis.
- **Measured once, by scratch scripts under `out/p31/scratch/`, on one recorded race in each direction; no test repeats them:**
  - the comparison with `out/p28play2` itself (`compare_sets.py`);
  - every look figure: the 186 frames (3.2 s) and the 428 and 62 frames of §0, §3.1 and §3.2, all pixel counts (`lookdiff.py`,
    `mkpair.py`), the dense double-draw counts of §3.3 (`dd.py`), the display-list comparison (`dl.py`);
  - "the V60's busy time identical to main's to the microsecond" and the added-records medians of the look replays
    (`records.py`); the test writes the same figures for its own runs to `far_summary.txt` but asserts only the bounds above;
  - the stills are single frames of the autopilot's line.

## 5. Tests

- `tests/test_convert_silhouette.py` (new, 15 tests, synthetic data, no ROM): written before the code (they failed on the missing
  modules; the box test failed on the missing parameter). The selection by height, rise and box; the copy as the very same quads;
  only the named cells returned and nothing given changed; two sources into one cell; a copy into an empty cell; six kinds of copy
  that cannot be made; the installation on a synthetic ROM image (only the named cell repointed, every changed byte erased before,
  colour entries inside the region given); nothing to install; no room for the colours; the plan's default.
- `tests/test_far_silhouette_build.py` (new, 5 tests; ROM, disc and MAME): the bytes against the set without the copies; the two
  cells' faces point for point; the race pass for pass and the frame's records, both directions. Written after the unit tests,
  before the first build.
- `tests/test_frame_rate.py::test_only_the_selected_tests_runs_are_made` (new) was written together with `selected_keys`, not
  before it.
- **The first gate session** (before the review, the tree at commit `8e8a0bc`): the new files, the Metropolis entries of
  `tests/test_frame_rate.py` and two tests of `tests/test_reverse_build.py`: 27 passed, 113 deselected in 914.77 s
  (`out/p31/gates.log`).
- **Added in the fix wave** (§10): in `tests/test_convert_silhouette.py`, the reserved colour block (written first, failing), the
  record cap and the polygon room (passing as written: the behaviour was there, untested), `install_far`'s floor and block
  (failing first), the capped cell (failing first), the pinned face count (failing first); 19 tests in the file now. In
  `tests/test_far_silhouette_build.py`, the colour entries inside `far_colour_block`, the block untouched before.
- **The final invocation** (the tree at commit `928382c`, `VR_MAME_JOBS=2`), from the worktree with `out/env.sh` sourced:

  ```
  python -m pytest tests/test_convert_silhouette.py tests/test_far_silhouette_build.py tests/test_tencourse.py \
      tests/test_reverse_build.py tests/test_pit_build.py tests/test_directory.py \
      "tests/test_frame_rate.py::test_only_the_selected_tests_runs_are_made" \
      "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate[entry_6]" \
      "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate[entry_6_reverse]" \
      "tests/test_frame_rate.py::test_the_worst_known_frames_hold_the_arcade_rate[metropolis_pit]" \
      "tests/test_frame_rate.py::test_no_list_is_skipped_where_the_games_budget_cut[entry_6]" \
      -o addopts="" -p no:cacheprovider --basetemp out/p31/pt_final -v --junitxml out/p31/final_junit.xml
  ```

  **187 passed, 16 skipped in 6 883.06 s (1 h 54 min 43 s)** (`out/p31/final.log`, `final_junit.xml`). No failure, so nothing to
  compare by name with `out/p27/full_failed.txt` (main's 15 known failures are in other files: `test_convert_collision`,
  `test_convert_geometry`, `test_convert_profile`, `test_race_build`, `test_tgp_build`; none of them was in this invocation).
  The 16 skips are all in `tests/test_directory.py`, "needs unidasm": the worktree has no `build/mame/unidasm`. Run again on
  their own with the main checkout's `build/` linked in for the run: `tests/test_directory.py`, **26 passed** in 1.87 s
  (`out/p31/final_directory_unidasm.log`). In the invocation, on the set with the reserved colour block: the byte tests, the
  race pass for pass over 4 177 passes in both directions (added records median 120 / max 120 normal, 90 / 120 reverse; busiest
  pass 6 715), the standing rate test for entry 6, entry 6 reverse and the Metropolis pit lap (0x501148 0 → 0, worst busy
  12 699, 12 540 and 14 489 us, render rate 28-29, no list skipped, records at most 7 068). The same figures as before the fix
  wave: the fix moved colour entries only.
- **The whole suite was not run** (3.5 h; once per batch of updates).

## 6. Found on the way

- **The first build copied the wrong building.** The pop-in still shows a banded building at the end of the street; the tallest
  banded structure decoded there is the 92-unit block, and the first plan copied that. On the straight it changed 24-53 pixels: the
  block is hidden behind the street's right side, and what pops in is the lower building on the street's axis. Found by counting
  differing pixels per frame, fixed by adding that building (the first set is kept as `out/p31/v1_set`).
- **Metropolis's 2D backdrop** has its own photo skyline, which shows wherever the far cells are not drawn (`reverse_f7616.png`,
  left). A copied building replaces a piece of it.
- **Main's own sort artefacts** at the tall block: its cream bands are drawn broken into diagonal pieces from some angles
  (`reverse_f8160_double_draw_crop4x.png`, top): they stand 0.4-0.6 off their wall and sort against it; and its hidden west wall is
  drawn over its front wall where the two tie in depth (§3.3). Neither is touched here; the second no longer shows while cell
  183 is drawn after cell 215.
- A build of the ten-course set took 12 minutes here with the machine otherwise quiet and did not finish in 25 with two other test
  runs going.

## 7. Not established

- **What Pascal saw in their 107-s run** (the head of this document): not stated; the recording has not been played back. Whether they want more places: not asked for.
- **The look in motion.** The stills are single frames. A building that is already there and then gains its ground and
  neighbours when the row is drawn may read differently at speed than a clean pop-in.
- **A depth tie that shows more than one grey step** (§3.3): possible in principle where a copied wall and a grey podium face
  share their farthest corner and overlap on screen; not seen in 153 frames with both drawn; camera positions off the autopilot's
  line not sampled.
- **Real hardware** (the project is MAME-only): what a real Model 1 does with the same polygon twice at the same depth is unknown;
  MAME does not model the render board's time.
- **Other camera positions**: the autopilot's line only. A car elsewhere on the road, stopped, spun, or in the pit lane sees the
  copy cells from other angles; the double draw was sampled every 4th frame of one lap's stretches in each direction (108 frames), not every frame. The attract demo does not show a
  converted course.
- **The cost of doing this widely.** Each place is one or two re-encoded cells (here 23 KB of polygon ROM for 60 faces, most of
  it the cells' own quads written a second time) and a hand-made choice from stills. With 438 KB free and a 64 KB floor, about
  fifteen places like this one fit as built; installed in place (§8) it would be about 4.8 KB a place.
- **Alpine**, and any ridge or terrain silhouette: only buildings were tried.
- The whole suite on this tree.

## 8. If kept

- Build the copies inside `convert_tiles` instead of after everything: the dead objects go (about 18.5 KB back), and the colour
  entries join the course's own run. Metropolis's later cells and the three courses after it then move in the ROM (same content),
  so "byte for byte main's" becomes "same content, other addresses" for them.
- More places: check each for depth ties as §3.3 does (faces sharing a corner, with colours that differ visibly), by a dense
  sample of the frames where both the copy and the original are drawn.
- More places want a tool: the per-frame visible-cell log and the pop-in still pairs of §1 are scratch scripts.

## 9. Files (git-ignored)

- Playtest sets: `out/p31play2` (after the review; build report inside), launcher `out/rec164/launch.sh` (as
  `out/rec163/launch.sh`, the same `start/` battery RAM and settings, records to `out/rec164/inp/play.inp`); `out/p31play1`, the
  set Pascal drove, launcher kept as `out/rec164/launch-p31play1.sh`. Not launched by the agent.
- Stills `out/p31/look/` (`NOTE.txt`, `diff_normal.txt`, `diff_reverse.txt`, `records.txt`; after the review
  `double_draw_reverse.txt`, `double_draw_normal.txt`, `display_list_f8160.txt`). The stills are of `out/p31play1`.
- Runs `out/p31/runs/`: `m6n`, `m6r` (main's set, the autopilot, recording the tape); `s6n`, `s6r` (the pop-in pairs); `look_main_*`
  and `look_new_*` (the replays the stills come from); `look_v1_*` (the first build); `dd_main_*`, `dd_p1_*`, `dd_p2_*` (the dense double-draw sample on main's set, `p31play1`,
  `p31play2`); `dl_main_r`, `dl_p1_r` (the display-list dumps, `out/p31/dl_*.txt`).
- `out/p31/compare_p28play2_p31play1.txt`, `out/p31/gates.log`, `out/p31/gates_junit.xml`, `out/p31/pt_gates/` (the test
  session's runs and summaries).
- Scratch scripts `out/p31/scratch/`: `build_set.py`, `run.py`, `cells_log.lua`, `events.py`, `sheet.py`, `landmarks.py`,
  `cellstats.py`, `snapframes.py`, `lookdiff.py`, `mkpair.py`, `pair.py`, `crop.py`, `records.py`, `compare_sets.py`.

## 10. The review and the fix wave (15 Nov)

An independent review of the branch at `ee5b11e`: ready with fixes, nothing Critical. Each finding was checked before it was
fixed; none is disputed.

- **I1, the colour entries placed by a search for erased bytes: confirmed and fixed.** `colour_run` took the first run of 0xff
  bytes long enough in `annex_regions()[0]`, which holds live tables; on `out/p31play1` that was 0x287530, inside Alpine's
  spawn-list slot (0x2870e0-0x2877e3), past its list's end [V]. Now `far_colour_block()` reserves 256 bytes below the start
  gantry's block, the pictures' search and the annex's region leave it out, and `colour_run` only ever writes inside it, after
  the last entry in use, failing loudly without room (§2). The built set's bytes changed: `out/p31play2`, §4.1.
- **I2, "the copy is lit one grey step lighter": wrong, corrected.** The display-list dump the review asked for shows the same
  light, matrix and object order on both sets; the difference is a depth tie between two of the block's walls broken by push
  order, and the pixels are the dark wall, not "window bands" (§3.3). The dense sample found the stretch to be continuous (50 of
  83 reverse frames, up to 1 068 pixels, always (0,0,0) to (8,8,8)), not "3 of 45 frames"; the risk of a larger artefact is
  bounded in §3.3 and listed in §7.
- **M1** "26 bytes" was the span; 14 bytes differ (§0, §4.1).
- **M2** stale wording after Pascal's answer: `tencourse.py`, the build test's docstring, `follow-ups.md`, `deviations.md`,
  `out/p31/look/NOTE.txt`.
- **M3** a cell over the record cap is installed as its first split only: `far_copy_cells(capped=)` refuses a copy from or into
  one; `convert_tiles` passes its capped cells. (No cell of the set is capped today.)
- **M4** `install_far_copies` catches the encoder's own error only; tests for the record cap, the polygon room and
  `install_far`'s floor.
- **M5** `FarCopy.faces` pins the number of faces a hand-tuned box selects (30, 7 and 8 on Metropolis); another count is a
  `ConvertError` in the converter, not only a failed build test.
- The claims that rest on one-off scripts are named as such (§4.4).
- **At the merge**: this branch and `phase29-alpine-trees` both add to `tencourse.py`, `geometry.py` and `follow-ups.md`; the
  byte comparison is against main before Phase 29 (§4.1).
