# Phase 34: more of Surfers Road's own palms (15-16 Nov 2026)

**What this is now: 13 more copies of Surfers Road's own Saturn palm, planted beside road points 25-93. Nothing is borrowed from
Bay Bridge or any arcade course.** Kept by Pascal after one 28-s run of the set `out/p34play3`, and driven again by them in the final set `out/p34play4` (run 6
below); not merged, not pushed. Reviewed twice: the first, arcade-palm version (§11.6) and the kept one at `545cbee` (§S.8). Branch `phase34-surfers-palms` (worktree `virtua-racing-p34`),
rebased onto main at `c94d7d9` on 16 Nov.

**Pascal's words and runs, exactly (16 Nov), in order:**
1. Shown six stills of Bay Bridge's small palm on Surfers Road (the first version, `out/p34/look/`): "palms are great keep it".
   Later "palms are good", then "i drove surfers road"; that drive was in `out/p33play1`, a set without the palms, and the
   session lead told them so (and that what they had seen there were the Saturn's own palms: the session lead's statement to
   them, not something they said).
2. They ran `out/p34play1` (the small arcade palms) through `out/rec167/launch.sh` once, 92 s, MAME's average speed 100.00 %
   (recording `out/rec167/inp/pascal-2026-11-16-p34palms-92s.inp`), and asked: "is it the small palms on the sides?". Told yes,
   that the arcade palm is 3.67 units against the Saturn's 10-19, and given the choices keep / keep the row of eight / drop /
   bigger palms as new geometry, they said: "bigger palms would look better". No size was named.
3. Sent eight stills of the larger variants, then the four stills of frame 2816 labelled on the picture "1 SMALL (as driven)",
   "2 ARCADE PALM x2", "3 A: ARCADE PALM x3", "4 B: SATURN PALM", they answered: "Arcade x3".
4. They ran `out/p34play2` (the arcade palm x 3) once, 30 s, MAME 99.99 % (recording
   `out/rec167/inp/pascal-2026-11-16-p34palms-x3-30s.inp`), then said: "can we try with the saturn ones".
5. They ran `out/p34play3` (the Saturn course's own palm) once, 28 s, MAME 100.00 % (recording
   `out/rec167/inp/pascal-2026-11-16-p34palms-saturn-28s.inp`), and said: **"those ones are great keep saturn"**. This
   supersedes "Arcade x3". It is a keep, not the word to merge.
6. They ran `out/p34play4` (the same palms built on main, with Phase 32's word REVERSE in it) through `out/rec167/launch.sh`
   once, 94 s, MAME 100.00 % (recording `out/rec167/inp/pascal-2026-11-16-p34play4-94s.inp`). Asked how the palms looked in the
   final set and, if they raced in reverse, how the REVERSE word looked: "look good". Then, unprompted: "palm". Then: "reverse
   word was good also on the normal tracks". Not the word to merge.

What they drove in each run was not stated; none of the recordings has been played back.

Pascal's order for more polygons was (1) more scenery objects ("perhaps borrowed from the three arcade courses"), (2) finer
geometry, (3) longer view distance; of Phase 29's trees they said "i think it s good" and "Keep the trees". The phase began as the Phase 28
recon's candidate step 2 (§8): Bay Bridge's palm, a spawn-list object, was baked into Surfers Road's cells along road points
25-99 for Pascal to see and judge; it was not kept (the record below). Their standing requirement: "It's critical the game stay fluid at 60fps constant"
(`tests/test_frame_rate.py`).

The Phase 28 recon's candidate step 2 was "a Bay Bridge palm tree row" on Surfers Road, and that is what was
built first; the palms that are kept are the Saturn course's own.

Marks: **[V]** verified by a run, a build or a byte comparison here; **[R]** read in code; **[?]** not established. Scratch
scripts, runs and pictures are under `out/p34/` of the main checkout (git-ignored, §10).

## S. What ships: the Saturn course's own palm, 13 more of them

### S.1 What is built [R, V]

- **The prop** (`vrtools/convert/props.py`): `CourseProp(site, radius, faces)` names a prop inside the converted course's own
  upright scenery (the Saturn's structures and props, groups 3 and 4, as placed and coloured for this course): the faces whose
  every corner lies within `radius` of a site. `prop_from_course` cuts it out where `convert_tiles` has that scenery (the plan's
  entry reaches it as a callable) and moves it so its foot (the middle of its lowest corners) is the origin. Each face keeps its
  Saturn colour (`PropFace.rgb`) and the Saturn's corner order; `baked` turns and moves a copy and hands it on as an ordinary
  two-sided `WorldQuad`, so a copy goes through `assign_colours` and `encode_object` exactly as the course's own faces do: the
  nearest palette colour, two-sided, the converter's z mode 2 and light mode 0. **No arcade ROM data is read for it**, and
  nothing of the Saturn's geometry is in the repository (it is read from the user's own disc at build time, as the course is).
- **The palm:** `SURFERS_ROAD_PALM = CourseProp(Planting(47, 7.2, 0.0, along=1.4), radius=6.0, faces=28)`: the Saturn's roadside
  palm on the right verge at road point 47 (a twin stands at 39): 28 faces (a pale trunk, leaves, coconuts), 13 Saturn colours,
  11.44 units tall, reaching 5.17 from its foot. Nothing is scaled.
- **The sites:** `SURFERS_PALMS`, the same 13 as every variant tried: 3 on the sand slope right of road points 25-28, 2 on the
  sand at 75-77, a row of 8 on the grass at 82-93, 12.5-22.8 units apart, each turned differently (map
  `out/p34/look/map_palms.png`; where palms can and cannot stand: §5.1). The Saturn course already has this palm at road points 39 and 47 (and
  the same trunk at 307 and 310) and five palms of another, taller model on the banks.
- **The planting rules** (`plant`; Phase 29's, three added in this phase, each with a test written first):
  - `is_water`: no prop where the top drawn surface under its centre or its reach is water-coloured (the sea left of 25-29);
  - `PROP_SLOPE`: the rise allowed across a prop's spread is the smaller of `PROP_FLAT` and tan 25 degrees x the spread (it binds
    a prop smaller than Big Forest's tree; for this palm the limit stays `PROP_FLAT`);
  - `CROWN_CLEAR`: no collision quad within the reach + 2 of the foot (it binds a prop wider than 8 units' reach; not this one).
  - Unchanged: drawn ground under the centre and a ring at the reach; the Saturn's upright scenery clear by reach + 1.5; the foot
    at least `PROP_CLEAR` 10 from every collision quad; each copy whole in the cell of its foot; a capped cell with prop faces
    is an error.
- **Clear of the road [V]:** every foot 10.8-13.6 units outside every collision quad; the nearest any corner of any leaf comes
  to one is 5.6 (by test: more than 5 against every collision quad read back from the built TGP data; Big Forest's tree on
  Alpine comes within 4.9). The palms are drawn only: a car cannot reach one, and the collision never sees them.
- **What was removed from the tree** (unused by any plan once the Saturn palm was kept; it is in the branch's history at
  `d09ec43` and `754c4da`, and its measurements are the record below): the arcade-object prop source (`PropObject`,
  `prop_from_object`, `read_prop`, `BAY_BRIDGE_PALM`), the faces' own sort and light bits (`PropFace.mode`, `WorldQuad.mode`,
  `Quad.mode`; `polyrom.py` is main's again), the scale (`ArcadeProp.scaled`, the plan entry's third element) and the variants
  table, with their tests. Kept because the build uses them or `plant` applies them, and each is tested: `CourseProp`,
  `prop_from_course`, `PropFace.rgb`, `is_water`, `PROP_SLOPE`, `CROWN_CLEAR`. No switch remains that changes the ROM.

### S.2 Cost and what changes, against main [V]

The base is `out/p34/base_main_c94d7d9`: a `vrtools build` from the main checkout at `c94d7d9` (Phases 29, 31 and 32 in it).
`out/p34play4` is a `vrtools build` of this tree (`vrtools.__file__` the worktree's; log `out/p34/build_p34play4.log`).
Compared by `scratch/cellcmp.py` and `scratch/regions.py`, and by the tests of §S.4.

| | main | with the palms | |
|---|---|---|---|
| TGP data (the collision), TGP program, boot ROM | | **identical** | |
| members of `vr.zip` identical | | 32 of 38 | `epr-14882/3` (program), `mpr-14880/1` (data: 7 bytes), `mpr-14896/7` (polygons) differ |
| Surfers Road's cells changed in content | | 4 | 0x96 196 -> 250 records (1 palm), 0x99 119 -> 551 (8), 0xa6 341 -> 449 (2), 0xa8 83 -> 191 (2) |
| records a palm | | 54 | 28 two-sided faces as the converter chains them |
| records in all Surfers Road's cells | 11 287 | 11 989 | +702 |
| colour entries | | +36 | 12 new in each of three cells (of the palm's 13 palette indices); none in 0xa6, which already had every colour of the palm |
| free colour entries (the run the annex uses) | 3 784 | 3 752 | 32 fewer (the blocks stored behind the entries are aligned) |
| polygon ROM free | 426 472 bytes | 398 392 | 28 080 used (floor 65 536) |
| TGP data free | 7 631 words | 7 631 | 0 |
| capped cells | | none | the largest palm cell is 551 records; the cap is 5 500 |

- **The three originals; Alpine, Amazon Falls, Diablo Canyon, Pacific Coast, Surfers Oval:** every cell identical, in place.
- **Metropolis:** every cell identical in content; 48 in place, 2 moved. The two are the cells Phase 31 rewrites with its far
  copies, which `ten_course_set` installs after everything else on erased polygon ROM: they now land behind a larger Surfers
  Road. Their tile-table words (program 0x27ff10-0x27ff21, 4 bytes) follow.
- **Surfers Road:** the four cells above; 59 identical in place; 9 identical but moved.
- **Relocated, not changed** (the kinds of §3.1): in polygon ROM (bytes 0xf46250-0xf9ec23) Surfers Road's later cells, the HUD
  map outlines, the start gantry's frames and Metropolis's two far-copy cells; in program ROM Surfers Road's tile table
  (0x283908-0x283b34, 44 bytes), the start gantry's object list (0x28f9f0-0x28fbe1, 68), the colour entries from the first palm
  cell on and the select pictures behind them (0x2b64ac-0x2b92df), the reverse annex (0x2b97ec-0x2bcb5f) and the directory's
  reverse records that name it (0x2797ac-0x279810, 11 bytes); in data ROM the select pictures' records (0xde854-0xde868). The
  attribution of regions to tables is by address against Phase 29's list [R]; the cells are compared in content [V], and the
  race is identical (§S.3).

### S.3 The race, the rate, the records and the need [V]

By `test_surfers_palms_are_drawn_the_race_is_the_same_and_the_rate_holds` in the final invocation (§S.5; the numbers read back
from its runs under `out/p34/pytest_final4/` by `scratch/testrates4.py`): two Surfers Road races of 135 s, the clock held, fresh
battery RAM; the first on the set built without the palms (main's set, ROM for ROM) under the standing test's autopilot line,
its inputs taped; the second on the set with the palms, fed that tape. The stretch is road points 25-99 (the autopilot laps in
about 67 s, so the normal race crosses it twice).

| | normal, without | normal, with the palms | reverse, without | reverse, with the palms |
|---|---|---|---|---|
| tape fed | | line for line | | line for line |
| game state at the end of every logic pass (3 745 passes: the clock, all 16 cars) | | **identical** | | **identical** |
| records a frame on the stretch (626 / 265 frames): median | 2 611 | 3 073 | 2 583 | 2 788 |
| ... max | 4 740 | 5 280 | 4 331 | 4 547 |
| records added a frame on the stretch: min / median / max | | 0 / 432 / 540 | | 108 / 162 / 540 |
| highest record count of the race | 4 740 | 5 280 (frame 2 491) | 5 707 | 5 707 |
| highest need of the race | 4 621 | 4 910 | 5 499 | 5 499 |
| V60 busy, worst | 12 118 us | 12 118 us | 11 601 us | 11 601 us |
| V60 busy, frame by frame | | identical | | identical |
| overrun counter 0x501148 | 0 -> 0 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| render rate from the green | 28-29 | 28-29 | 28-29 | 28-29 |
| frames with a skipped list | 0 | 0 | 0 | 0 |

- **Records and need.** The budget (10 500) is compared with the count as the walker reaches each object list (the frame's
  "need": the least budget under which it skips nothing), not with the frame's final count. The frame with the most records
  (5 280) has a need of 4 729; the highest need is 4 910 in the normal race (4 621 without the palms) and 5 499 in reverse (the
  same without them, on a frame away from the stretch). All are under the set's 10 500, and under the game's original 5 500.
- +540 is ten palms: the cells 0x99 (8 palms) and 0xa8 (2) are in the visible block together on most of the normal stretch; a
  cell's records count whenever it is in the block, wherever the camera looks.
- Records cost no emulated time in MAME (Phases 28 and 29): the busy time is the same to the microsecond.
- **The standing assertion** (`tests/test_frame_rate.py::test_surfers_road_stays_inside_the_draw_budget`, both directions): on
  the rate test's own 150-s races, no list skipped, the set's budget in every frame, the need under it throughout.
- **Off the autopilot's line** (`test_surfers_road_fits_the_draw_budget_wherever_the_camera_is`): elsewhere all four palm cells
  could be in the visible block at once (+702). The game draws the cells of the 5 x 5 block around the camera's cell; over all
  256 camera cells the block with the most cell records holds 4 280 (as if every cell of it were drawn; it is a block without
  palm cells), and the most a Surfers Road frame was measured to hold besides its cells is 3 633 (on the grid; 616 dumped frames
  of two races, `scratch/noncell.py`, measured on the arcade-palm set: the palms are cell records and do not enter it). 4 280 +
  an allowance of 4 500 is under 10 500. The allowance is a measured maximum rounded up, not a proof.
- The standing `test_every_course_holds_the_arcade_rate` on all 17 races: §S.5.

### S.4 The gates, by test

`tests/test_props.py` (the Saturn palm's; the planting rules' synthetic tests are with Phase 29's at the top of the file):

- `test_a_prop_can_be_cut_from_the_courses_own_scenery`, `test_plant_refuses_a_site_in_the_water`,
  `test_a_small_prop_is_held_to_the_same_slope_not_the_same_rise`,
  `test_plant_refuses_a_prop_whose_crown_reaches_towards_the_collision` (synthetic, each written before its code).
- `test_surfers_palms_are_in_its_cells`: the plan; 13 sites on 25-99; the planted prop 28 coloured faces, 11.44 tall, reach
  5.17, standing on its foot; every face of every copy read back from the built polygon ROM, **two-sided**, z mode 2, light mode
  0, at the palm's own height; the source palm still whole in its own cell, which no copy shares; no capped cell; the spacing.
- `test_palms_stay_clear_of_surfers_collision`: every foot at least 10 from every collision quad of the built TGP data; every
  corner of every copy measured against every one of those quads: the nearest is more than 5 away (5.61).
- `test_the_palms_change_only_the_palm_cells`: against the build with `props=()`: the TGP data, TGP program and boot identical;
  the originals the user's ROM's own; the six earlier courses identical in place (in `build_all`'s output: Metropolis's far
  copies are installed later, §S.2); the four palm cells **54 records a palm** larger, every colour word they had kept, and
  **only palette indices that are the nearest colours of the palm's own faces gained, one entry a colour**; the other cells
  identical in content.
- `test_without_the_palms_the_set_is_the_base_branchs` (opt-in by `VR_P34_BASE_SET`, a record against the branch's base and not
  a standing gate: it skips, saying so, without it): the set built without the palms is `out/p34/base_main_c94d7d9` ROM for
  ROM (so nothing else on this branch changes a byte of main's set: Alpine's trees and Metropolis's far copies as main builds
  them); the collision, TGP program and boot of the set with the palms are main's; `out/p34play4` is the session's set ROM for
  ROM.
- `test_surfers_road_fits_the_draw_budget_wherever_the_camera_is`: §S.3's static bound.
- `test_surfers_palms_are_drawn_the_race_is_the_same_and_the_rate_holds[normal|reverse]`: §S.3.
- `tests/test_frame_rate.py::test_surfers_road_stays_inside_the_draw_budget[entry_9|entry_9_reverse]`: the standing need
  assertion on the rate test's own races.

### S.5 The final invocation

One run after the second review's fix wave, at commit `c163ecb` (the commit after it changes this document only), from the
worktree, 16 Nov 10:43-12:53, with a temporary symlink `build -> ` the main checkout's `build` (MAME's unidasm, for
`tests/test_directory.py`), removed afterwards:

```
source out/env.sh && VR_P34_SET=out/p34play4 VR_P34_BASE_SET=out/p34/base_main_c94d7d9 VR_MAIN_SET=out/p35play1 VR_MAME_JOBS=2 \
  PYTHONPATH=$PWD .venv/bin/python -m pytest -o addopts="" -p no:cacheprovider -q -rfEs \
  tests/test_props.py tests/test_polyrom.py tests/test_polyrom_encode.py tests/test_convert_geometry.py \
  tests/test_convert_silhouette.py tests/test_far_silhouette_build.py tests/test_tencourse.py tests/test_gate_lettering.py \
  tests/test_directory.py tests/test_reverse_build.py tests/test_hudreverse_build.py tests/test_dirscreen_build.py \
  "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate" \
  "tests/test_frame_rate.py::test_surfers_road_stays_inside_the_draw_budget" --basetemp out/p34/pytest_final5
```

(`out/env.sh`, `.venv` and `out/` are the main checkout's, given by their full paths in the run; `VR_MAIN_SET` is what
`test_hudreverse_build.py` compares with.) **323 passed, 1 failed, 0 skipped, 0 errors in 7 757.29 s (2:09:17)**
(`out/p34/pytest_final5.log`).

- **The one failure**, by name: `tests/test_convert_geometry.py::test_thinning_drops_small_far_quads_only`, on the known-failing
  list `out/p27/full_failed.txt`; none of that list's other 14 names is among this invocation's 324 tests.
- **Added for the second review** (what the palms relocate): `test_directory.py` 26, `test_reverse_build.py` 82,
  `test_hudreverse_build.py` 18, `test_dirscreen_build.py` 38: all passed, none skipped.
- **`out/p34play4` is still the build of the final tree:** `test_without_the_palms_the_set_is_the_base_branchs` ran (opted in)
  and found the session's own build of this tree ROM for ROM `out/p34play4`, and the palm-less build ROM for ROM main's set. The
  fix wave changed no ROM byte; no new play set was built.
- The rest as the earlier run below (`test_props.py` 29 with its four MAME drives, the rate test's 17 races, the standing need
  assertion). The numbers of §S.3 are that earlier run's; this run asserted the same conditions.

**The earlier run of the same day** (before the second review; its record kept):

One run at commit `0727ab9` (the commits after it change documents only), on the tree rebased onto main `c94d7d9`, from the
worktree, 16 Nov 08:17-10:05:

```
source out/env.sh && VR_P34_SET=out/p34play4 VR_P34_BASE_SET=out/p34/base_main_c94d7d9 VR_MAME_JOBS=2 \
  PYTHONPATH=$PWD .venv/bin/python -m pytest -o addopts="" -p no:cacheprovider -q -rfEs \
  tests/test_props.py tests/test_polyrom.py tests/test_polyrom_encode.py tests/test_convert_geometry.py \
  tests/test_convert_silhouette.py tests/test_far_silhouette_build.py tests/test_tencourse.py tests/test_gate_lettering.py \
  "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate" \
  "tests/test_frame_rate.py::test_surfers_road_stays_inside_the_draw_budget" --basetemp out/p34/pytest_final4
```

(`out/env.sh`, `.venv` and `out/` are the main checkout's, given by their full paths in the run.) **159 passed, 1 failed, 0
skipped, 0 errors in 6 430.58 s (1:47:10)** (`out/p34/pytest_final4.log`).

- **The one failure**, by name: `tests/test_convert_geometry.py::test_thinning_drops_small_far_quads_only` ("the pit-lane
  placement reaches 1073 (limit 970)", raised in `vrtools/convert/place.py`). It is on the known-failing list
  `out/p27/full_failed.txt` (15 names); none of the other 14 names is among this invocation's 160 tests. This branch does not
  touch `place.py` or that test.
- **In the 159:** `tests/test_props.py` 29 (Phase 29's on Alpine's trees, its two MAME drives among them; this phase's 4 planting
  and prop tests, 5 build tests and 2 MAME drives on Surfers Road; `test_without_the_palms_the_set_is_the_base_branchs` ran
  against `out/p34/base_main_c94d7d9` and `out/p34play4`, not skipped), `test_polyrom.py` 13, `test_polyrom_encode.py` 11,
  `test_convert_geometry.py` 27 of 28, `test_convert_silhouette.py` 19 and `test_far_silhouette_build.py` 5 (Phase 31's
  Metropolis gates, which the rebase brought under this branch's `convert_tiles`), `test_tencourse.py` 16,
  `test_gate_lettering.py` 20, the standing rate test on all 17 races and the standing need assertion for Surfers Road (2).
- **The rate test's own line for Surfers Road** (`out/p34/pytest_final4/rate0/rate_summary.txt`, 150-s races): normal: render
  28-29, overrun 0 -> 0, worst busy 12 118 us, records peak 5 280, need max 4 910, budget 10 500, no skipped list; reverse:
  28-29, 0 -> 0, 11 601 us, 5 707, 5 499, 10 500, none.
- **Before it, on the same day:** a first run of this invocation was stopped after its 24th test,
  `test_palms_stay_clear_of_surfers_collision`, failed on an assertion of mine: the test looked for collision quads within the
  reach + 5 of each foot to check the leaf corners against, and required that there be some; there are none (every foot is
  farther than that), which is the geometry's own proof that no corner comes within 5. The test now takes the quads within the
  reach + 9, requires some at every site and checks every corner against them (`out/p34/pytest_final3.log`, no summary line).
  The round-2 invocation on the earlier base was stopped unfinished when the choice changed (§11.7).
- Not run: `tests/test_directory.py` (untouched by the branch and the rebase; it needs the main checkout's unidasm) and the whole
  suite (one whole-suite run a batch of updates, not a branch).

### S.6 The look [V pictures]

Pascal's "those ones are great keep saturn" followed their 28-s run of `out/p34play3`; their "look good" and "palm" followed
their 94-s run of `out/p34play4`. The stills that exist are of the same palms at the same sites on the earlier base (before the
rebase; the palm cells' content is the same): `out/p34/look/v2/*_3_B_saturn_palm.png` (eight frames, both directions; the
triples beside them show the two arcade-palm versions that were not kept) and `out/p34/look/v2/crops/`. The Saturn palm is thin:
a pale forked trunk and a few dark leaf triangles; from 33-36 units it reads as a sparse, wiry tree, and it is the same model
as the roadside palms the course already has, so nothing clashes. The HUD lies over part of the row in both directions (every site is on
the inside of the bend). No stills were made of `out/p34play4`.

**Not ours, for the record (nothing touched):** the Saturn's own roadside palms that the copies are taken from stand inside the
collision on main: the palm at road point 47 (7.2 units right of the centreline) lies inside collision quad 1271 and its twin
at 39 inside quad 1263, both non-tarmac quads (the verge), not at a quad's outer edge; so no wall stands at them and a car can
drive through the drawn trunk [V by geometry, `out/p34/scratch`: the course's collision quads as converted, which this branch
leaves byte for byte]. The project's rule (walls at drawn scenery are never removed and never moved nearer the road) is not
touched by this branch either way.

### S.7 Not verified

- Real hardware (as Phases 28 and 29: MAME does not model the render board's time).
- No stills of `out/p34play4`.
- What Pascal drove in their runs; the look from a human driver's line.
- Off the autopilot's line: the allowance in §S.3's static bound is a measured maximum rounded up, not a proof.
- Whether a copy's faces sort wrongly against the hill or another copy anywhere (the two closest pairs of crowns stand about 2
  units apart; none seen in the eight stills).
- Which region of the program ROM's differences is which table, beyond the addresses matching Phase 29's list.
- Linked play; the attract mode on Surfers Road; `tests/test_directory.py` and the whole suite (not run: §S.5).

### S.8 The review of the kept variant (`545cbee`) and what was done

Verdict: ready with fixes; nothing critical, nothing that changes the ROM.

| | finding | checked | done |
|---|---|---|---|
| 1 | the comparison with main's set read a git-ignored set frozen at one commit and skipped silently without it | true | opt-in by `VR_P34_BASE_SET` only, with the reason in the skip; its docstring says it is a record, not a standing gate |
| 2 | the tests guarding what the palms relocate (the select pictures, the reverse annex, the directory's reverse records, the HUD map object, the gantry list, 7 data-ROM bytes) were not in the final invocation | true | `test_reverse_build.py`, `test_hudreverse_build.py`, `test_directory.py` (main's `build/` symlinked for unidasm, removed after) and `test_dirscreen_build.py` are in §S.5's invocation |
| m | the leaf-corner check could not fail at these sites and its `assert near` was tuned | true | every corner of every copy measured against every collision quad; the nearest must be more than 5 (5.61) |
| m | the need assertion adds nothing over "no list skipped"; "arcade props" in its docstring | true | the docstring says what the assertion is for (the number in a failure) and what the palms are |
| m | the 4 500 allowance was measured on the arcade-palm set on the autopilot's line; the 3 000-5 000 window was tuned | true | said in the comment, with the margin (the bound holds up to 6 219); the window replaced by "a block holds at least its largest cell" |
| m | stale text (`baked`'s docstring, "prototype awaiting", Bay Bridge's palm in the present tense) | true | corrected |
| m | `CROWN_CLEAR` and `PROP_SLOPE` bind no shipped prop | true | kept, one line each on why (a wider or a smaller prop than today's must not hang over the road or stand on a cliff); `ground_height` is now `ground_top`'s height: one implementation |
| m | inferences about Pascal ("they had seen the Saturn's own", "chose from driving", "after driving the set") | true | who said it, which set, how long; the 94-s run of `out/p34play4` added |
| m | the synthetic palm used two of the real palm's colours; two sea colours hard-coded | true; the sea's are kept | invented colours for the synthetic palm; a comment says why the two sea colours are constants (colour values the rule was written for; reading them from the disc means converting the course) |
| - | the source palm's own site lies inside a collision quad on main | true: quads 1271 (road point 47) and 1263 (39), verge quads, no wall | stated in §S.6; nothing touched |

---

# The record: what was tried and not kept

**Everything below is the record of the two arcade-palm versions and of the comparison, as written at the time** (sections 0-10:
Bay Bridge's palm at the arcade's own size, `out/p34play1`, code at `6ebb1b7` before the rebase; section 11: the palm scaled x 3
as "variant A", `out/p34play2`, and the Saturn palm as "variant B", `out/p34play3`, on the base `out/p29play2`). The code those
sections describe (`PropObject`, `mode`, `scaled`, the variants table) is no longer in the tree (§S.1). Their base sets predate
the rebase.

## 0. In brief

- **Built:** 13 copies of Bay Bridge's palm (45 faces, 3.67 units tall), read from the user's own ROM at build time and baked into
  four of Surfers Road's scenery cells, all right of the normal direction: 3 on the sand slope at road points 25-28, 2 on the sand
  at 75-77, a row of 8 on the grass at 82-93 [V].
- **Size: the arcade's, factor 1.0 [R, V].** The recon's "about 3 x 4 x 3" is the object as stored and as drawn: the entity
  handler's draw sends no scale (§2), and the display list's matrix for the palm on Bay Bridge has unit scale on 39 measured draws.
  Nothing was enlarged. The palms are small: about a third the height of Surfers Road's own Saturn palms (§5).
- **Colours: the palm's own palette entries [V].** One polygon palette serves every course [R]; the copies carry the palm's two
  palette indices (0xD0 trunk, 0xD1 crown) and its light mode. On screen they are the same browns and greens as on Bay Bridge in
  kind (the two commonest shades are the same); shade for shade was not compared (§5; corrected after the review, M5).
  Cost: 8 colour entries.
- **Nothing but drawing changes [V]:** the TGP data, the TGP program and the boot ROM are byte for byte the base set's
  (`out/p29play2`); only four cells of Surfers Road differ in content; nine more of its cells and what is stored behind them
  moved; the six other converted courses and the three originals are identical in place (§3). Fed the base's recorded inputs, the
  game's state at the end of every one of 3 745 logic passes (135 s, the clock, all 16 cars) is identical, both directions.
- **The rate [V]:** overrun counter 0 throughout, render rate 28-29, worst V60 busy 12 118 us (normal) and 11 601 us (reverse)
  against two vblanks of 34 770, the same as without the palms frame for frame. Records a frame on the stretch: median 2 611 ->
  3 283 normal, 2 583 -> 2 926 reverse; at most +900 on any frame of the autopilot's race; its highest record count 5 640 and highest need 5 270 (budget 10 500).
- **Room [V]:** polygon ROM 46 800 bytes (449 800 -> 403 000 free); colour table 8 entries (3 784 -> 3 776); TGP 0 words.
- **Cost a palm:** 90 records, not the source's 57: each face is a chain of its own (§1).

## 1. How it is built [R, V]

- **A second kind of prop source** (`vrtools/convert/props.py`). `PropObject(objlist, faces)` names the whole object an original's
  spawn-list entity draws, by the entity's object list (a V60 address: one record (poly word, colour entry, records) and a zero
  word). `prop_from_object` reads it from the user's ROM at build time: every face in the object's own frame (the origin is where
  the entity stands; nothing is moved, re-centred or scaled), with its colour word's palette index and its record's sort and light
  bits (`PropFace.mode`: z mode, light mode, light bank; `MODE_BITS`). It refuses a list that is not one record and a zero, and an
  object with another number of faces. `read_prop` takes either kind (`PropSource`: faces cut out of a cell, Phase 29).
  `BAY_BRIDGE_PALM = PropObject(objlist=0x2E04D0, faces=45)`. Nothing of the palm's geometry is in the repository.
- **The palm [V `test_bay_bridges_palm_is_read_from_the_rom`]:** the seven entities of handler `0xffacc6` in Bay Bridge's spawn
  list all name that list; the object is 57 records, 45 faces (a 9-face trunk, six fronds of 3 faces on each side; 24 of the 45
  are triangles), two palette indices, 3.669 units tall, reaching 1.421 from its origin, standing on its origin. Every face is
  culled (one-sided) and stores the reversed winding's normal (the dot product with the computed one is above 0.99 on all 45; a few
  faces are slightly off flat), z mode 1 (sorted at its nearest depth), light mode 1.
- **The copy** (`baked`, as Phase 29): turned about the vertical, moved to its foot, each face a one-sided `WorldQuad` with
  `palette` and now `mode`. `assign_colours` passes the mode to the polygon `Quad`; `encode_object` writes it on the face's drawing
  record in place of the converter's own z mode 2 / light mode 0 (`Quad.mode`; a face without one is written exactly as before:
  §3's bare build is the base set byte for byte). So a copy has the palm's drawn corners, normal (recomputed from the corners),
  palette index, cull bit, z mode and light mode [V `test_surfers_palms_are_in_its_cells`: read back from the built polygon ROM].
- **Not record for record the arcade's** (as Phase 29's tree): each face is a chain of its own, 2 type-1 records, so a palm costs
  90 records where the source object has 57 (it chains faces and uses 24 triangle records); a triangle is a type-1 record with a
  repeated corner; the source's flag bits 23 and 24 are clear; the source advances its colour entry on every record (57 entries
  holding two values), a cell with palms adds two entries however many palms it holds. What that changes on real hardware is
  unknown (§8).
- **Planting** (`plant`, Phase 29's rules, two added, each with a test written first):
  - `PROP_SLOPE` (tan 25 degrees): the rise allowed across a prop's spread is the smaller of `PROP_FLAT` (4.5) and `PROP_SLOPE` x
    the spread. `PROP_FLAT` alone would have let a palm 2.8 units across stand on a 58-degree face; the limit is 1.33 for the palm
    and stays 4.5 for Big Forest's tree (spread 10.2: 4.77), so Alpine's sites are judged exactly as before.
  - `CROWN_CLEAR` (2.0): no collision quad within the prop's reach + `CROWN_CLEAR` of its foot. It only bites for a prop wider
    than `PROP_CLEAR` - 2; neither the tree (reach 5.1) nor the palm (1.4) is.
  - Unchanged: drawn ground under the centre and a ring at its reach; clear of the Saturn's upright scenery by reach + 1.5; the
    FOOT at least `PROP_CLEAR` 10 from every collision quad; each copy whole in the cell of its foot; a capped cell with prop
    faces is an error.
- **The plan:** `SURFERS_PALMS` (13 `Planting`s) and `props=((BAY_BRIDGE_PALM, SURFERS_PALMS),)` on Surfers Road's `CoursePlan`
  (`vrtools/arcade/tencourse.py`). The build report's Surfers Road line ends ", props 13 (585 faces; Phase 34 prototype)".

## 2. The palm's size on Bay Bridge [R, V]

The brief asked whether the entity handler scales the palm at draw, as some spawn-list objects are.

- **The handler [R]** (`0xffacc6`, disassembled with the main checkout's unidasm): it sets the draw routine `0xffacf0`. Each
  frame, when the entity's cell is visible, that routine tests the player's car against a box around the palm (in the palm's
  frame: +-1.5 in x and z, -1 to 5 in y); on a hit it calls `0xfec003`, plays sound `0xb01a` and sets the palm's tilt (+0x2a =
  0x4000, which the routine then lowers by 0x200 a frame): **the palm can be knocked over on Bay Bridge.** The draw itself (`0xffae38..0xffaeb5`)
  writes five TGP commands and no other: `0x2800000`, `0x3800000` + the 12 words at `0x501b00` (the camera matrix), `0x9000000` +
  the entity's x, y, z, `0xA000000` + one angle (+0x2e, the tilt), then `0xff84a2` (the object list), then `0x3000000`.
  **No scale is sent** [V `test_the_palms_handler_draws_it_at_its_stored_size`: the command immediates, read from the user's boot
  ROM by byte pattern]. That 0x9 is a translation and 0xA a rotation is the reading of the gantry's and the pit code's use of the
  same commands (`docs/formats/model1-course-tables.md` §12) [R]; the measurement below does not depend on it.
- **Measured [V]** (`out/p34/scratch/bbscale.py` on the run `out/p34/runs/BB`: Bay Bridge on the base set under the autopilot,
  the display list dumped every 20 frames): on all 39 draws of the palm object (polygon word 0x1274ed) the 3x3 of the matrix
  command before it has rows and columns of length 1.0000 and determinant 1.0000.
- **So the factor is 1.0** and the copies are baked at the object's stored size: 3.67 units tall, 2.6-2.8 across. Enlarging them
  would be new geometry, which the brief rules out.
- **Where Bay Bridge puts them [V]:** three in a row 10 units apart at its road points 259-261 and four 12-17 apart at 109-116,
  22-27 units left of the centreline, within the car's reach. On Surfers Road the copies stand 33-36 units from the centreline
  (the collision is 23 wide on that side and `PROP_CLEAR` adds 10), so they come out smaller on screen than on Bay Bridge. The
  reference still: `out/p34/look/full/bay_bridge_palms_reference.png`.

## 3. The ROMs against the base (`out/p29play2`, a build of `b32ea76`) [V]

`out/p34play1` (`vrtools build` from this tree at the prototype's code, `vrtools.__file__` the worktree's; log
`out/p34/build_try1.log`; it was built as `out/p34/build_try1` and moved, its report's last line rewritten to the new path),
compared member by member, region by region and cell by cell (`scratch/cellcmp.py`, `scratch/regions.py`):

| member | bytes differing | what |
|---|---|---|
| 33 of the 38 members, among them the TGP data `mpr-14898..14901`, the boot ROM, `mpr-14890..14895` and `mpr-14881.7` | **0** | the collision and the code: identical |
| `mpr-14896.32`, `mpr-14897.33` (polygon ROM) | 344 670 in the polygon space (bytes 0xf46a98-0xf9da23) | Surfers Road's four palm cells grown; what is stored behind them moved |
| `epr-14882.14`, `epr-14883.15` (program ROM) | 8 552 and 6 442 (14 994 in the program space) | §3.1 |
| `mpr-14880.6` (data ROM) | 5 (0xde854-0xde868 of the data space) | the select pictures' records: +0x10 |
| `model1io.zip`, `m1comm.zip` | 0 | |

### 3.1 What differs, cell by cell and region by region

- **The three originals:** every cell object and colour entry identical, at the same addresses.
- **Alpine, Amazon Falls, Diablo Canyon, Metropolis, Pacific Coast, Surfers Oval:** every cell identical in content and in place
  (78, 67, 67, 50, 72, 72 cells; Alpine's four tree cells among them). Surfers Road is the last course written, so nothing
  before it moves.
- **Surfers Road:** 4 cells changed content: 0x96 196 -> 286 records (1 palm), 0x99 119 -> 839 (8), 0xa6 341 -> 521 (2), 0xa8
  83 -> 263 (2); each +2 colour entries, the palm's 0xD0 and 0xD1, none lost. 59 cells identical in place, 9 identical but
  moved. Records in all its cells 11 287 -> 12 457 (+1 170 = 13 x 90). No cell is capped (the cap is 5 500 records; its largest
  palm cell is 839).
- **Relocated because Surfers Road's data grew** (the same kinds as Phase 29's §3.1, here only what lies behind Surfers Road):
  in polygon ROM its later cells, the HUD map outlines and the start gantry's frames stored after them; in program ROM its tile
  table (0x2838d8-0x283b04: the moved cells' addresses, 46 bytes), the start gantry's object list (0x28f9f0-0x28fbe1, 71 bytes),
  the colour entries from its first palm cell on and the select pictures behind them (0x2b64bc-0x2b92af; the pictures +0x10,
  behind the 8 new entries) with the pictures' records in data ROM, the reverse annex (0x2b97ec-0x2bcb2f, +0x10) and the
  directory's reverse records that name it (0x2797ac-0x279810, 9 bytes). The build report differs in the polygon ROM left,
  Surfers Road's line (456 088 -> 502 888 bytes of scenery, the props note) and the seven reverse variants' load, maps and race
  blob addresses (+0x10). (The attribution of the regions to those kinds is by address against Phase 29's list [R]; that they
  are relocations and not changes of content is shown for the cells [V] and, for the game, by the identical race, §4.)
- **By test, not only by script:** `test_the_palms_change_only_the_palm_cells` (the build with Surfers Road's `props=()` against
  the build with them: the TGP data, TGP program and boot identical; the originals the user's ROM's own; the six earlier courses
  identical in place; Surfers Road's cells as above) and `test_without_the_palms_the_set_is_the_base_branchs` (the set built
  without the palms is `out/p29play2` ROM for ROM, so nothing else this branch changed alters a byte and Alpine's trees are built
  exactly as on the base; the collision of the set with the palms is the base's; with `VR_P34_SET`, the playtest set is the
  session's set ROM for ROM).

### 3.2 Room used [V]

| | base (`p29play2`) | with the palms | used |
|---|---|---|---|
| polygon ROM free | 449 800 bytes | 403 000 | 46 800 (floor 65 536: 337 464 above it) |
| Surfers Road's scenery objects | 456 088 bytes | 502 888 | 46 800 |
| colour table, the run the annex uses | 3 784 entries | 3 776 | 8 |
| TGP data free | 7 631 words | 7 631 | 0 |

## 4. The rate and the game, with and without the palms [V]

Method (`scratch/drive.py`, `scratch/snaps.sh`, `scratch/rates.py`): Surfers Road on `out/p29play2` with the standing test's
autopilot line, the clock held, 135 s, the inputs taped (`M_n`, `M_r`); then the base set again and `out/p34play1` fed those tapes
frame for frame (`S_B_*`, `S_A_*`), fresh battery RAM each. The stretch: road points 25-99 (reverse: 342-416 in the run's
numbering). The autopilot laps in about 67 s, so the normal race crosses the stretch twice.

| | normal, base | normal, palms | reverse, base | reverse, palms |
|---|---|---|---|---|
| tape fed | M's, line for line | M's, line for line | M's, line for line | M's, line for line |
| pass log (3 745 passes + END) | = M's | **identical** | = M's | **identical** |
| race frames measured | 3 080 | 3 080 | 3 080 | 3 080 |
| records a frame on the stretch (626 / 265 frames): median, max | 2 611, 4 740 | 3 283, 5 640 | 2 583, 4 331 | 2 926, 4 691 |
| records added a frame on the stretch | | 0 to +900, median +720 | | +180 to +900, median +270 |
| frames of the race with more records (of 2 950 after the green) | | 902 | | 422 |
| records peak, whole race | 4 740 | 5 640 | 5 707 | 5 707 |
| V60 busy, worst (frame) | 12 118 us (2 541) | 12 118 us (2 541) | 11 601 us (2 367) | 11 601 us (2 367) |
| V60 busy, frame by frame | | identical on every frame | | identical on every frame |
| overrun counter 0x501148 | 0 -> 0 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| render rate from the green | 28-29 | 28-29 | 28-29 | 28-29 |
| frames with a skipped list | 0 | 0 | 0 | 0 |

- +900 is ten palms: the cells 0x99 (8) and 0xa8 (2) are in the visible block together on most of the normal stretch; a cell's
  records count whenever it is in the block, wherever the camera looks.
- **Records and need (corrected after the review, I1).** The normal race's highest record count rises from 4 740 to 5 640
  (frame 2 491). That number is the frame's whole count; what decides whether a list is skipped is the count when the walker
  reaches each list (`frame_rate.lua`'s "need": the least budget under which the frame skips nothing). That frame's need is
  4 801, and the race's highest need is 5 270 (4 621 without the palms): **under the game's original 5 500 as well as under the
  set's 10 500**. The first version of this section said the original budget would have dropped a far cell on that frame; that
  was wrong. In reverse the highest need is 5 499 with and without the palms.
- As Phase 28 and 29 found, records cost no emulated time in MAME: the busy time is the same to the microsecond.
- The same by test: `test_surfers_palms_are_drawn_the_race_is_the_same_and_the_rate_holds[normal|reverse]` (its base is the set
  built without the palms, which the test above shows is `out/p29play2`), and the standing
  `test_every_course_holds_the_arcade_rate` on its 17 races (the ten courses, the seven converted ones in reverse; §7).

## 5. The look [V pictures; the judgement is Pascal's]

`out/p34/look/` (NOTE.txt says what each shows): `full/` whole-screen 1440x1080 pairs of the same frame of the same race
(`_1_base`, `_2_palms`; four normal, four reverse) and the Bay Bridge reference; `crops/` the palms' part enlarged, base left,
palms right; `map_palms.png` the top view; `palms.txt` the list.

- **Scale:** the palm is 3.67 units tall. Surfers Road's own Saturn palms on this stretch are about 11 tall at the road's edge
  (road points 39-40 and 47-48: a pale trunk of 8.8, a crown up to 11.4) and 10-19 on the outer bank (45-49, 59-60) [V
  `scratch/uprights.py`]: three to five times taller. Side by side (`normal_1`) the arcade's read as young palms beside a grown
  one. This is the plainest thing in the pictures, as it was for Phase 29's trees.
- **Two species:** the arcade's palm has a dark brown-orange trunk and a darker, denser crown; the Saturn's a pale trunk and four
  or eight bright green leaf faces. Where both are in view they do not read as one planting. They are never close: the nearest
  Saturn palm to a copy is on the other side of the collision (the Saturn's stand in the verges at 5-10 units from the
  centreline and on the outer bank; the copies 33-36 inside the bend).
- **As a row:** the eight on the grass (12.5-22.8 apart, each turned differently) read as a planted row from both directions
  (`normal_2`, `normal_3`, `reverse_1`, `reverse_2`).
- **From reverse:** whole; every face is one-sided as on Bay Bridge and each frond has faces on both sides.
- **Colour [V]:** the pixels the palms change on Surfers Road (37 369 over 129 snapshot pairs) are browns and greens with no
  blue, the shaded pair (74, 41, 0) and (16, 74, 0) most often; the same two are the commonest palm colours in the Bay Bridge
  still. The lit shades differ with the face's angle to the light. Whether Surfers Road's light parameters for light mode 1 are
  exactly Bay Bridge's was not read [?]; it is served from Bay Bridge's template (0).
- **The HUD:** every palm is on the inside of the bend, where the course map (normal) and the gear gauge and POSITION (reverse)
  lie over part of them.
- **Where the autopilot sees them:** normal, road points 21-25 (palms 1-3) and 65-91 (4-13); reverse, 106-80 and 37-30. Between
  26 and 64 none (the hill hides the far ones; there are no sites, below).

### 5.1 Where palms can stand on 25-99 [V `scratch/zones.py`, `zones2.py`, `cands.py`, `gcol.py`: through `plant` itself]

- **Right (the inside of the bend):** the collision reaches 22-23 units from the centreline, so the nearest site is at 32-33.
  25-29: a sand slope, 3-8 above the road. 30-36 and 39-64: the hill, steeper than 25 degrees (refused). 37-38 and 65-72: gentle
  but 18-26 above the road (not used: too high to read as roadside). 73-79: sand, 8-11 above. 81-99: grass, 1-7 above the road:
  the row.
- **Left:** 25-29 the first drawn ground beyond the collision is the sea (at the road's level; not planted: palms do not stand in
  water; chosen by hand, no rule in `plant`); 30-68 nothing drawn beyond the bank; 69-82 a grass bank 9-27 above the road (not
  used); 83-98 almost nothing.
- 5 933 scanned sites pass `plant`. The 13 were taken at the nearest passing offset (33-36 right) at stations chosen by hand for
  an uneven row (`scratch/pick.py`; headings random in 5-degree steps, seed 34). Clearance from the foot to the nearest
  collision quad 10.8-13.6; from any corner of any frond more than 9 [V `test_palms_stay_clear_of_surfers_collision`, against the
  collision read back from the built TGP data].
- **Fewer than could fit, by choice:** the brief asked for about 10; 13 are placed. No frame or cell forced fewer (§4, §3.1).

## 6. Tests (`tests/test_props.py`; each new one red first)

- **Synthetic, written before the code:** a prop read from an entity's object in the object's own frame, with its colours and
  modes; a list that is not one object, or another face count, refused; `read_prop` on either kind of source; a prop's sort and
  light bits reaching its records (and a prop without them encoded byte for byte as before); `plant` refusing a prop whose crown
  reaches the collision; a small prop held to the same slope, not the same rise.
- **The user's ROM:** `test_bay_bridges_palm_is_read_from_the_rom`, `test_the_palms_handler_draws_it_at_its_stored_size`.
- **The build:** `test_surfers_palms_are_in_its_cells` (13 sites on 25-99, each cell holding the palm's 45 faces at the arcade's
  height with the palm's z mode and light mode, culled; no capped cell; spacing 10 and more, varied),
  `test_palms_stay_clear_of_surfers_collision`, `test_the_palms_change_only_the_palm_cells`,
  `test_without_the_palms_the_set_is_the_base_branchs`.
- **MAME, both directions:** `test_surfers_palms_are_drawn_the_race_is_the_same_and_the_rate_holds`: the base's taped inputs
  fed line for line, the pass log identical, every palm cell's object in the display list while the player is on the stretch
  and running to its end marker in the with-palms record count under the command's limit, the three measures of the rate, no
  skipped list, every frame under the draw budget, the added records 0 to 13 x 90, the busy time identical frame for frame.
- Phase 29's tests adapted, not weakened: Alpine's still assert its 21 trees and that the five courses between have no props;
  `_built_without_props` strips one named course.

## 7. The final invocation

One run at commit `21e9b2d` (the prototype's code and tests; the commit after it changes documents only), from the worktree,
15 Nov 21:01-22:57, with a temporary symlink `build -> ` the main checkout's `build` (MAME's unidasm, for `tests/test_directory.py`),
removed afterwards:

```
source out/env.sh && VR_P34_SET=out/p34play1 VR_MAME_JOBS=2 PYTHONPATH=$PWD \
  .venv/bin/python -m pytest -o addopts="" -p no:cacheprovider -q -rfEs tests/test_props.py tests/test_polyrom.py \
  tests/test_polyrom_encode.py tests/test_convert_geometry.py tests/test_tencourse.py tests/test_directory.py \
  tests/test_gate_lettering.py "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate" --basetemp out/p34/pytest_final
```

(`out/env.sh`, `.venv` and `out/` are the main checkout's, given by their full paths in the run.) **162 passed, 1 failed, 0
skipped, 0 errors in 6 924.11 s (1:55:24)** (`out/p34/pytest_final.log`).

- **The one failure**, by name: `tests/test_convert_geometry.py::test_thinning_drops_small_far_quads_only` ("the pit-lane
  placement reaches 1073 (limit 970)", raised in `vrtools/convert/place.py`). It is one of the 15 names of the known-failing list
  `out/p27/full_failed.txt`; none of the other 14 names is among this invocation's 163 tests. This branch does not touch
  `place.py` or that test.
- **In the 162:** `tests/test_props.py` 32 (Phase 29's 18 and this phase's 14; the four MAME drives among them: Alpine's trees
  and Surfers Road's palms, normal and reverse; `test_without_the_palms_the_set_is_the_base_branchs` ran against `out/p29play2`
  and `out/p34play1`, not skipped), `tests/test_polyrom.py` 13, `tests/test_polyrom_encode.py` 11,
  `tests/test_convert_geometry.py` 27 of 28, `tests/test_tencourse.py` 16, `tests/test_directory.py` 26 (none skipped: the
  symlink), `tests/test_gate_lettering.py` 20, and the standing rate test `test_every_course_holds_the_arcade_rate` on all its
  17 races (the ten courses, and the seven converted ones in reverse; Surfers Road is `entry_9` and `entry_9_reverse`, Alpine
  `entry_3` and `entry_3_reverse`).
- **The palm test's own measurements** (read back from its runs under `out/p34/pytest_final/` by `scratch/testrates.py`) are §4's
  to the digit: normal 3 745 passes identical, the stretch's records 2 611 / 4 740 -> 3 283 / 5 640, added 0 / 720 / 900
  (minimum / median / maximum), worst busy 12 118 us; reverse 3 745 passes identical, 2 583 / 4 331 -> 2 926 / 4 691, added 180 /
  270 / 900, worst busy 11 601 us; overrun 0, render rate 28-29, no skipped list in both.
- The whole suite was not run (the brief: one whole-suite run a batch of updates, not a branch).

## 8. Not verified

- Real hardware (as Phases 28 and 29: MAME does not model the render board's time). Nor how real hardware draws the copies'
  records where they differ from the source's (§1).
- What Pascal drove in their 92-s run of `out/p34play1` (not stated; the recording not played back). Their words are at the head.
- The look from a human driver's line: the pictures follow the autopilot.
- Whether Surfers Road's light parameters for light mode 1 equal Bay Bridge's (§5): the colours match in kind, not measured
  shade for shade.
- The exact road point and frame of each still: MAME wrote one snapshot more than was asked for in each run (201 for 200, 151
  for 150); the pairs are matched by index and show the same frame on both sets (their differing pixels are the palms), but the
  frame number in a file name may be off by 4.
- Which regions of the program ROM's differences are which table, beyond the addresses matching Phase 29's list (§3.1).
- Linked play; the attract mode on Surfers Road (the standing attract test was not part of this invocation).
- The whole suite (not run: the brief's instruction; §7 is the invocation).
- A larger palm, palms nearer the road than `PROP_CLEAR`, or palms that can be hit (a spawn entity instead of baked faces): not
  built; each is outside the brief's rules.

## 9. Next (not built; Pascal's call)

- If the size is the objection: the arcade's own size is what was built. A larger copy is new geometry; nearer the road means a
  smaller `PROP_CLEAR` for a 1.4-unit prop (a rule change); the recon's other option is a spawn entity with the palm's own
  handler, which draws it at the roadside and lets the car knock it over (the handler's collision and sound come with it: §2).
- The lamp post (4 x 11 x 1, 16 quads) and the lighthouse are the recon's remaining Bay Bridge objects of roadside height.

## 10. Files (git-ignored, `out/p34/` of the main checkout)

- `scratch/`: `palm1.py`, `palm2.py`, `palm3.py` (the object), `v60dis.py` (the handler's listing), `bbpalms.py`, `bb.py`,
  `bbscale.py` (Bay Bridge), `surf_data.py` (-> `surf.pkl`), `zones.py`, `zones2.py`, `cands.py`, `gcol.py`, `uprights.py`,
  `topview.py`, `pick.py` (-> `picked.pkl`), `palmmap.py`, `drive.py`, `stretch.py`, `snaps.sh`, `diffs.py`, `sheet.py`,
  `look.py`, `rates.py`, `cellcmp.py`, `regions.py`, and their pickles and pictures.
- `runs/`: `M_n`, `M_r` (base, autopilot, the tapes), `S_B_n`, `S_B_r`, `S_A_n`, `S_A_r` (base and palms, replays with
  snapshots), `BB` (Bay Bridge), and the runs' logs.
- `look/`: `full/`, `crops/`, `map_palms.png`, `palms.txt`, `NOTE.txt`.
- `build_try1.log`; `pytest_final.log`, `pytest_final/` (§7); `pytest_red/`, `pytest_green/` (the red and green runs).
- Outside `out/p34/`: `out/p34play1` (the playtest set; Alpine's trees in it), `out/rec167/launch.sh` (the launcher, modelled on
  `out/rec163/launch.sh`: `start/` copied, `inp/` empty; records to `inp/play.inp`). No windowed MAME was run.

## 11. Round 2: bigger palms, two variants (16 Nov)

Pascal's words are at the head: "bigger palms would look better", no size named. The session lead's brief for the round: scale
the arcade palm to about the height of Surfers Road's own roadside palms (variant A); if cheap, plant the Saturn course's own palm
at the same sites instead (variant B); the same gates for each. Both were built. Neither has been seen by Pascal.

### 11.1 What was built [R, V]

- **A scale** (`ArcadeProp.scaled(factor)`): every corner `factor` times as far from the prop's origin, its foot. The copies are
  baked faces, so the game's own drawing (which has no scale for the palm, §2) does not bind them. **This is new geometry: the
  arcade never draws the palm at this size.** A plan's props entry may be `(source, plantings, scale)` (`prop_entry`); without
  one the scale is 1.0 and `scaled(1.0)` returns the prop itself, so everything built before is byte for byte the same (§11.3).
- **A prop cut from the course's own scenery** (`CourseProp(site, radius, faces)`, `prop_from_course`): the faces of the converted
  course's kept structures and props (Saturn groups 3 and 4, as placed and coloured) whose every corner lies within `radius` of a
  site, read inside `convert_tiles` where that scenery is. Its faces carry their Saturn colour (`PropFace.rgb`) and are baked as
  the course's own are: two-sided, the nearest palette colour, the converter's z mode and light mode. No arcade data at all.
- **No prop in the water** (`is_water`, in `plant`): a site is refused when the top drawn surface at its centre or anywhere on
  the ring at its reach is water-coloured (blue at least 200, red at most 64, bluer than green: the Saturn's sea here is
  (0, 184, 248) and (0, 200, 248)). Round 1 kept the palms out of the sea left of road points 25-29 by hand (§5.1); now the rule
  does [V `test_plant_refuses_a_site_in_the_water`]. Alpine's 21 sites still pass (the build would stop otherwise).
- **The planting rules read the prop they are given**, so a scaled prop is judged by its scaled reach: the drawn ground and the
  slope over its larger spread, the Saturn's scenery at reach + 1.5, `CROWN_CLEAR` [V `test_the_planting_rules_measure_the_scaled_prop`].
- **The variants** (`tencourse.SURFERS_PALM_VARIANTS`, all at `SURFERS_PALMS`' 13 sites):

  | | prop | tall | reach | faces | records a palm | play set |
  |---|---|---|---|---|---|---|
  | round 1 ("arcade") | the arcade palm as drawn | 3.67 | 1.42 | 45 one-sided | 90 | `out/p34play1` (built at `6ebb1b7`) |
  | **A** ("arcade3", the branch's plan) | the arcade palm x 3.0 | 11.01 | 4.26 | 45 one-sided | 90 | `out/p34play2` |
  | **B** ("saturn") | the Saturn's roadside palm right of road point 47 (`SURFERS_ROAD_PALM`: trunk, leaves and coconuts) | 11.44 | 5.17 | 28 two-sided | 54 | `out/p34play3` |
  | ("arcade2", stills only) | the arcade palm x 2.0 | 7.34 | 2.84 | 45 one-sided | 90 | none (`out/p34/build_x2`) |

  3.0 was chosen so that A stands as tall as the Saturn's roadside palms here (11.4). The x 2 build is there because 3.0 makes a
  stout palm (the object was modelled to be seen small): it is shown, not argued (§11.5).
- **Nothing moved:** all 13 sites pass `plant` for A, B and x 2 as they stand (`scratch/pick2.py`), so the row of eight is the
  same row. Neighbours stand 12.5-22.8 apart; A's crowns are 8.5 across and B's 10.3, so the two closest pairs stand 2-4 units apart crown to crown.
- **Clear of the road [V]:** every foot 10.8-13.6 units outside every collision quad, as before. The nearest any face corner
  comes to a collision quad: 9.4 (round 1), 8.1 (x 2), **6.8 (A), 5.6 (B)** (`scratch/clear2.py`; by test, more than 5 for A and
  B against every collision quad read back from the built TGP data). Big Forest's tree on Alpine comes within 4.9.

### 11.2 The ROMs against the base (`out/p29play2`) [V `scratch/cellcmp.py`, and by test]

| | A (`out/p34play2`) | B (`out/p34play3`) |
|---|---|---|
| TGP data, TGP program, boot ROM | identical | identical |
| the three originals, the six other converted courses | every cell identical, in place | every cell identical, in place |
| Surfers Road's cells changed in content | 4: 0x96 196 -> 286 records, 0x99 119 -> 839, 0xa6 341 -> 521, 0xa8 83 -> 263 | the same 4: 196 -> 250, 119 -> 551, 341 -> 449, 83 -> 191 |
| its other cells | 59 identical in place, 9 identical but moved | 59 in place, 9 moved |
| records in all its cells | 11 287 -> 12 457 (+1 170) | 11 287 -> 11 989 (+702) |
| colour entries | +8 (0xD0, 0xD1 in each palm cell) | +32 (12 new in each of three cells, none in 0xa6, which already had the palm's colours) |
| polygon ROM free | 449 800 -> 403 000 (46 800 used) | 449 800 -> 421 720 (28 080 used) |
| members of `vr.zip` identical to the base's | 33 of 38 | 32 of 38 (`mpr-14881.7` differs too, 2 bytes: the select pictures' records) |
| capped cells | none | none |

A's record counts, colour entries and relocations are round 1's exactly: **scaling costs no record**. The relocated regions are
those of §3.1 for both (B's offsets differ: it adds 32 colour entries where A adds 8).

### 11.3 The gates, by test (`tests/test_props.py`, each parametrised over `arcade3` and `saturn`)

- `test_surfers_palms_are_in_its_cells`: 13 sites on 25-99, the planted prop what the variant says (A: equal to the ROM's palm
  scaled 3.0; B: 28 coloured faces, 11.4 tall), every face of every copy read back from the built polygon ROM (A: culled, the
  palm's z mode and light mode; B: two-sided), no capped cell, the spacing.
- `test_palms_stay_clear_of_surfers_collision`: §11.1's clearances.
- `test_the_palms_change_only_the_palm_cells`: §11.2 against the build with Surfers Road's `props=()`.
- `test_without_the_palms_the_set_is_the_base_branchs`: that bare build is `out/p29play2` ROM for ROM (the default scale, the
  new sources and rules change no byte; Alpine's trees as on the base); the collision of both variants' sets is the base's; with
  `VR_P34_SET` / `VR_P34_SET_B` the two play sets are the session's sets ROM for ROM.
- `test_surfers_road_fits_the_draw_budget_wherever_the_camera_is` (review I2): §11.4.
- `test_surfers_palms_are_drawn_the_race_is_the_same_and_the_rate_holds[variant-direction]`: as round 1, plus the need under
  the budget in every frame.
- `tests/test_frame_rate.py::test_surfers_road_stays_inside_the_draw_budget[entry_9|entry_9_reverse]` (review I2, a standing
  test): on the rate test's own races, no skipped list, the set's budget in every frame, the need under it.

### 11.4 The rate, the records and the need [V]

The same method as §4: the tapes of `M_n` / `M_r` fed to each set (`S_A3_*`, `S_SAT_*`; `scratch/rates2.py`), and by the tests.

| | normal: base | A | B | reverse: base | A | B |
|---|---|---|---|---|---|---|
| pass log (3 745 passes) | | identical | identical | | identical | identical |
| records a frame on the stretch: median | 2 611 | 3 283 | 3 073 | 2 583 | 2 926 | 2 788 |
| ... max | 4 740 | 5 640 | 5 280 | 4 331 | 4 691 | 4 547 |
| records added a frame on the stretch: min / median / max | | 0 / 720 / 900 | 0 / 432 / 540 | | 180 / 270 / 900 | 108 / 162 / 540 |
| highest record count of the race | 4 740 | 5 640 | 5 280 | 5 707 | 5 707 | 5 707 |
| highest need of the race | 4 621 | 5 270 | 4 910 | 5 499 | 5 499 | 5 499 |
| V60 busy, worst; frame by frame | 12 118 us | 12 118; identical | 12 118; identical | 11 601 us | 11 601; identical | 11 601; identical |
| overrun; render rate; skipped lists | 0; 28-29; 0 | 0; 28-29; 0 | 0; 28-29; 0 | 0; 28-29; 0 | 0; 28-29; 0 | 0; 28-29; 0 |

- **A's numbers are round 1's to the digit**: bigger palms cover more pixels, the record count does not change (confirmed).
- **Records against need:** the budget (10 500) is compared with the count as the walker reaches each list (need), not with the
  frame's final count. The highest need with palms is 5 270 (A, normal) and 5 499 (reverse, the same without palms): under the
  set's 10 500 and under the game's original 5 500. No frame of these races would skip a list under either budget.
- **Off the autopilot's line (review I2):** "+900 at most" is the autopilot's figure; elsewhere all four palm cells could be in
  the visible block at once (+1 170 for A, +702 for B). The bound that does not depend on the line: the game draws the cells of
  the 5 x 5 block around the camera's cell; over all 256 camera cells the block with the most cell records holds 4 280 (A; as if
  every cell of it were drawn), and the most a Surfers Road frame was measured to hold besides its cells is 3 633 (on the grid;
  616 dumped frames of two races, `scratch/noncell.py`); 4 280 + an allowance of 4 500 is under 10 500 [V by test]. The allowance
  is a measured maximum rounded up, not a proof: what a pit stop or a crowded corner adds off the line was not measured [?].

### 11.5 The look [V pictures; the choice is Pascal's]

`out/p34/look/v2/` (its NOTE.txt): whole-screen 1440x1080 triples at round 1's eight frames, `_1_small_arcade_size`,
`_2_A_arcade_palm_x3`, `_3_B_saturn_palm` (`normal_1`: beside one of the Saturn's own; `normal_2`/`normal_3` and
`reverse_1`/`reverse_2`: the row of eight from each direction), `_x_arcade_palm_x2` for `normal_3` and `reverse_1`, and
`crops/` with the versions side by side.

- **A** reads boldly at speed: thick orange-brown trunks lit on one side, a dense green crown; it looks like the arcade game's
  own scenery. The trunk is stout for its height and the crown's facets are large. Beside a Saturn palm it is plainly another,
  heavier species.
- **B** is the course's own species, so nothing clashes, but the Saturn's palm is thin: a pale forked trunk and a few dark leaf
  triangles. From 33-36 units it reads as a sparse, wiry tree; the row is much less of a feature than A's.
- **x 2** sits between: better proportioned than A, still slight on the far half of the row.
- The HUD lies over part of them in every version (§5).

### 11.6 The review of round 1 (`b32ea76..6ebb1b7`) and what was done

| | finding | checked | done |
|---|---|---|---|
| I1 | "with the original budget that frame would have dropped a far cell" is false | true: frame 2 491 has 5 640 records and need 4 801; the race's highest need is 5 270; a list is skipped only when the count on reaching it exceeds the budget | §0, §4, §8, the follow-ups and the deviation corrected; §11.4 states records and need for the variants |
| I2 | no standing budget assertion for Surfers Road; the one assertion was on records, on the autopilot's line | true | `test_frame_rate.py::test_surfers_road_stays_inside_the_draw_budget` (need, both directions); the need asserted in the palm drive too; `test_surfers_road_fits_the_draw_budget_wherever_the_camera_is` (the worst 5 x 5 block + a stated allowance) |
| I3 | after the rebase the base set must be a main-built one | agreed | not done here: the rebase is the session lead's to call; §3, §3.2, §7, §11.2 are against `out/p29play2` until then |
| I4 | status wording ("awaiting", "not seen"); Phase 29 is merged; "Asked: about 10 palms" read as Pascal's | true | Pascal's words as given to me, at the head, in the follow-ups, the deviation, the code comments and the notes; the "about 10" attributed to the recon and the brief |
| M1 | an assertion that could not fail (a prop with `mode=None` against itself) | true | replaced: the converter's own mode said outright gives the same bytes, another mode different ones |
| M2 | `MODE_BITS` defined twice; `assign_colours` dropped a mode on a two-sided face | true | one definition (`polyrom.MODE_BITS`, which `props` imports); a two-sided face with a mode is a ConvertError; a test for both |
| M3 | the sea's exclusion was prose only | true | `is_water` in `plant`, with its test (§11.1) |
| M4 | the build report named the phase by `plan.name == 'ALPINE'` | true | the line ends ", props N (M faces)" |
| M5 | "are the colours of the palm on Bay Bridge" overstated §5 | true | §0 says what was compared |
| M6 | the frond clearance checked only the 12 nearest quads | true | every collision quad for the foot; for the corners every quad within the reach + 5 of the foot (no other can be within 5 of a corner) |

### 11.7 The final invocation of round 2

Not completed. The invocation (the tests of §11.3 with `test_tencourse.py`, `test_gate_lettering.py` and the rate tests) was
stopped on 16 Nov when Pascal's choice changed the plan: by then all 46 tests of `tests/test_props.py` (both variants' four MAME
drives among them), `test_polyrom.py`, `test_polyrom_encode.py` and `test_convert_geometry.py` had run with one failure,
`tests/test_convert_geometry.py::test_thinning_drops_small_far_quads_only` (named by running that file alone; it is on
`out/p27/full_failed.txt`). The log is `out/p34/pytest_final2.log` (no summary line). §S.5 is the invocation that counts.

### 11.8 Not verified in round 2

- Pascal has not seen the variants. Real hardware (§8), now also for a prop three times the size its records were authored at.
- The play sets `out/p34play2` and `out/p34play3` were built before the review's last code changes (the report's label, the
  single `MODE_BITS`, the refused two-sided mode, `prop_models` in the report); their build reports' Surfers Road and Alpine
  lines still end "... prototype)". Their ROMs are the final code's, ROM for ROM (§11.7's test with `VR_P34_SET` /
  `VR_P34_SET_B`). `out/p34play3` and the x 2 build were made by `out/p34/scratch/build_variant.py` (`cli.build` with Surfers
  Road's props replaced by the named variant), not by a `vrtools build` option.
- The x 2 size has stills and an identical pass log on the tapes, and nothing else: no play set, no tests.
- The allowance of §11.4 off the autopilot's line; whether B's or A's larger faces sort wrongly against the hill or the HUD
  anywhere (none seen in the 16 pictures); the look from a human driver's line.
- The launchers record to `play-a.inp` / `play-b.inp` (so that two drives do not overwrite each other), unlike rec163's
  `play.inp`. No windowed MAME was run.
- Not rebased onto main (I3); the whole suite not run.

Round 2's files (git-ignored, `out/p34/`): `scratch/satpalm.py`, `pick2.py`, `clear2.py`, `build_variant.py`, `look2.py`,
`rates2.py`, `noncell.py`; `runs/S_A3_*`, `S_SAT_*`, `S_A2_*`; `look/v2/`; `build_p34play2.log`, `build_p34play3.log`,
`build_x2.log`, `build_x2/`; `pytest_final2.log`, `pytest_final2/`; `pytest_red2/`, `pytest_green2/`. Outside it: `out/p34play2`,
`out/p34play3`, `out/rec167/launch.sh` (A), `launch-b.sh` (B), `launch-p34play1.sh` (round 1).
