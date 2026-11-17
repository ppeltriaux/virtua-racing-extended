# Phase 29 prototype: Big Forest's trees on Alpine (15 Nov 2026)

**A prototype; not merged. Pascal's words and run, exactly: they ran the playtest set `out/p29play1` once on 15 Nov (110 s,
MAME's average speed 99.93 %; the recording is kept as `out/rec162/inp/pascal-2026-11-15-p29trees-110s.inp`); asked whether to
keep, change or drop the trees, they said "i think it s good"; later the same day, asked about another prototype and whether to
merge the trees once reviewed, they said "Keep the trees". What they drove was not stated. Neither is the word to merge.
Reviewed once since, with a fix wave (§11).** Branch `phase29-alpine-trees` (worktree `virtua-racing-p29`), cut from main after
Phase 28 and rebased on main (two doc-only commits) for the fix wave.

Pascal asked whether more polygons can be added to the tracks and chose the order: (1) more scenery objects ("perhaps borrowed
from the three arcade courses"), (2) finer geometry, (3) longer view distance. After the Phase 28 recon and the draw budget
(merged), they said "then continue": this is the recon's candidate step 1, about 30 Big Forest trees along Alpine's road points
400-449, built so that Pascal can see it and judge it. Their standing requirement: "It's critical the game stay fluid at 60fps
constant" (the arcade draws one picture every second screen frame; the guarantee is never falling below the original's own rate,
`tests/test_frame_rate.py`).

Marks: **[V]** verified by a run, a build or a byte comparison here; **[R]** read in code; **[?]** not established. Scratch
scripts, runs and pictures are under `out/p29/` (git-ignored, §10).

## 0. In brief

- **Built:** 21 copies of Big Forest's tree (7 faces, 16.35 units tall), read from the user's own polygon ROM at build time and
  baked into four of Alpine's scenery cells beside road points 406-449 [V]. Not 30: on 400-449 the Saturn draws little ground
  beyond the walls that a tree can stand on (§2).
- **Nothing but drawing changes [V]:** the TGP data (collision) of the built set is byte for byte `out/p28play2`'s, and the same
  build with and without the props differs only in Alpine's four tree cells
  (`tests/test_props.py::test_the_props_change_only_the_tree_cells`); fed the same
  inputs, the game's state at the end of every one of 6 765 logic passes (240 s, the clock, all 16 cars) is identical to main's set
  in both directions; the V60's busy time is identical frame for frame.
- **The rate [V]:** overrun counter 0 throughout, render rate 28-29 in every window, worst V60 busy 11 142 us (normal) and 11 271
  us (reverse) against two vblanks of 34 770, the same as without the trees. Records a frame along the stretch: median 1 924 ->
  2 190 normal, 2 535 -> 2 640 reverse; at most +266 on any frame (budget 10 500).
- **Room [V]:** polygon ROM 11 748 bytes (461 548 -> 449 800 free); colour table 16 entries (3 800 -> 3 784); TGP 0 words.
- **The look (for Pascal):** the trees (16.35 units) read as small dark cones beside Alpine's own pines, which are 30-120 units
  tall, about 2 to 7 times taller; Big
  Forest's greens are darker than Alpine's, neither has snow; most trees are visible only from parts of the stretch (§5).

## 1. How it is built [R, V]

- **The prop** (`vrtools/convert/props.py`). `PropSource(course, cell, x, z, radius, faces)` names a prop by place: the faces of an
  original course's tile cell whose every corner lies within `radius` of (x, z). `BIG_FOREST_TREE` = Big Forest's cell 0x17, the
  tree at (-53.7, -774.2): a 4-face canopy (three sides and its base, 12.3 high) on a 3-face trunk (2.7):
  the recon's 4-face variant, complete from every side, so it looks right from both directions (the 3-face canopies of Big Forest
  have no back face). `prop_from_cell` reads it from `rs` (the user's ROM) at build time and checks the face count; nothing of its
  geometry is in the repository. Its faces keep their palette index (the colour-table word's low ten bits: 0x27C, 0x27E, 0x27F
  greens, 0x27D brown).
- **The copy** (`baked`): turned about the vertical (the rotation `face_quads` gives the Saturn's placements) and moved to its
  foot; each face a one-sided `WorldQuad` with `palette` set (a new optional field, Phase 29) and its corners in the Saturn's order,
  which `assign_colours` reverses back. Measured on the tree: every source face is culled and its stored lighting normal equals the reversed
  winding's right-hand normal [V `test_big_forests_tree_is_read_from_the_rom`], so the copies come out with the source's drawn
  corners, normal, palette index and cull bit, at its z mode (2) and light mode (0) [V, the source's records against the built
  cell's]. They are not record for record what the arcade stored: each copied face is a chain of its own of type-1 records, with
  a repeated corner where four of the tree's seven source faces are triangle (type-2) records, and without the source records'
  flag bits 23 and 24. What that changes on real hardware is unknown (§8).
  `assign_colours` takes the palette index as it is instead of the nearest colour when `palette` is set (the Saturn's faces are
  unchanged).
- **The planting** (`plant`): a copy stands at the lowest drawn height within `FOOT_RING` (1 unit) of its foot, so no side floats.
  It is refused (ConvertError naming the site; the build stops) when: no drawn ground (groups 0 and 1, as kept) is under its reach
  (the centre and 8 points on a ring at its radius, 5.12); that ground rises or falls more than `PROP_FLAT` 4.5 across it (about a
  25-degree slope; on it the canopy's uphill edge meets the snow); a face of the Saturn's upright scenery (groups 3 and 4: pines,
  buildings, gates) comes within its reach + `SCENERY_CLEAR` 1.5; or any collision quad (tarmac, verge, run-off, pit lane: a car
  stays inside them, their outer edges are the walls) lies within `PROP_CLEAR` 10 units in XZ of its foot. The clearance is the
  foot's, not the canopy's: the tree reaches 5.116 from its foot, so a canopy can come within about 4.9 units of a collision
  quad's edge (a car's half width beyond the last quad a car can stand on).
- **The plan:** `CoursePlan.props` (`((PropSource, (Planting, ...)), ...)`), `Planting(point, offset, heading, along)`: `offset`
  units to the right of the direction of travel ((dz, -dx), the AI lines' convention) from centreline point `point`, `along` ahead.
  Alpine's `ALPINE_TREES` in `tencourse.py`. `convert_course` reads the prop and resolves the plantings; `convert_tiles` plants them
  after the thinning and puts each copy whole into the cell its foot stands in (`cells_by_foot`; the Saturn's faces go by their own
  centres). A cell is drawn whole or not at all: the first build binned the copies' faces by their centres, and tree 20 (road point
  449) had 2 of its 7 faces in the next cell, which could show half a tree at the edge of the visible block; found by
  `test_alpines_trees_are_in_its_cells` once it checked every site, fixed, and every measurement here is on the rebuilt set. The collision is built before and never sees them. The build report's
  Alpine line ends ", props 21 (147 faces; Phase 29 prototype)"; its scenery quad count stays the Saturn's (6 543;
  counting the props in it broke `test_the_ten_course_set_keeps_polygon_rom_free`'s every-Saturn-face check, so they are counted
  apart: report "props" and "prop_faces").

## 2. Where trees can stand on 400-449 [V]

Alpine's road points 400-449 run from the hairpin's exit along a causeway to the start line (map `out/p29/look/map_trees.png`).
A scan of every site 2.5 units along and 1 unit across, both sides, out to 80 units, through `plant` itself (`scratch/cands2.py`):

- **410-438: no drawn ground on either side** beyond the verges. The road crosses on a causeway; below it the backdrop's flat fill
  shows (it reads as a distant snowfield in the pictures). The Saturn's own pines there (four, 60-97 units tall, base at y -80.7,
  25 units below the road) stand over nothing drawn [V `scratch/pines.py`].
- **Right of 400-418:** the hillside rises 11-18 units across a tree's reach (50 degrees and more), or ends in the void.
- **Left of 400-418:** within PROP_CLEAR of the walls, then a snow crest about 25 units above the road; only 404-409 is flat enough
  on top.
- **439-449:** the crest left of the road (25-33 above it) and flat ground right of 448-449 (at the road's height, and 6-12 below it
  right of 448).
- 447 sites pass all the rules; at PROP_FLAT 2.0 only 150 would (447 and 449 alone).

**The 21 sites** (`out/p29/scratch/pick.py`, seed 38): the passing sites visited in a random order biased towards the road
(weight exp((clearance - 10)/15)), each kept when it stands a random 7.5-12 units from every tree kept before (Big Forest's own
trees: nearest neighbour p5 7.4, median 9.3 [V, 167 trunks]); headings random in 5-degree steps (seed 2029). Offsets therefore
vary from 37 to 79 units, spacing from 7.5 to 12, and no two neighbours share a heading pattern. Several seeds gave 16-21 trees at
these rules; the largest (21) was kept. The list as built (`out/p29/look/trees.txt`): 2 on the crest left of 406-408; 9 on the
crest left of 439-449; 10 on the flat right of 448-449. Clearance from the foot to the nearest collision quad: 10.1-51.6 units.

Not done (the brief's rules): trees over the void (no drawn ground, though the Saturn puts its own pines there), on the steep
hillsides, in the pit lane (Alpine's is at road points 184-209), or nearer the road than PROP_CLEAR.

## 3. The ROMs against `out/p28play2` [V]

`out/p29play1` (`vrtools build` from this tree, `vrtools.__file__` the worktree's; log `out/p29/build_p29play1.log`), compared
member by member and by region (`scratch/romdiff.py`, `scratch/cellcmp.py`):

| member | bytes differing | what |
|---|---|---|
| the other 26 of the 38 members, among them the TGP data `mpr-14898..14901` and the boot ROM | **0** | the collision and the code: identical |
| `mpr-14890..14897` (polygon ROM) | 3 111 214 (from byte 0x2b1f34 of the polygon space on) | Alpine's four tree cells grown; every later object moved (§3.1) |
| `epr-14882.14`, `epr-14883.15` (program ROM) | 18 222 and 12 792 (31 014 in the program space) | tile tables, colour entries, the start gantry's object list, the select pictures, the directory's reverse records and the annex (§3.1) |
| `mpr-14880.6`, `mpr-14881.7` (data ROM) | 6 (0xde854-0xde868 of the data space) | the select pictures' four records: +0x20 |
| `model1io.zip`, `m1comm.zip` | 0 | |

### 3.1 What differs, cell by cell

- **The three originals:** every cell object and colour entry identical, at the same addresses.
- **Alpine:** 4 cells changed content (0x45 286 -> 384 records, 0x46 126 -> 140, 0x52 168 -> 196, 0x55 66 -> 220; each +4 colour
  entries, the tree's four palette indices), 8 identical in place, 66 identical but moved. Records in all Alpine cells 11 605 ->
  11 899 (+294 = 21 x 14: a one-sided face costs 2 records).
- **The six other converted courses:** every cell's object bytes and colour words identical; every one moved (their polygon
  addresses and colour entries follow Alpine's).
- **Relocated because Alpine's data grew:** Alpine's later cells and the six courses' cells, the seven HUD map outlines and the
  start gantry's frames (polygon ROM); in program ROM the seven converted tile tables (0x27b370-0x283b04: poly_adr and tex of
  moved cells), the colour entries and the select pictures behind them (0x2b1938-0x2b929f; the pictures +0x20, behind the 16 new
  entries) with the pictures' records (data ROM), the start gantry's object list (0x28f9f0-0x28fbe1), the reverse annex (load, maps and race
  blobs, 0x2b97cc-0x2bcb1f, +0x20) and the directory's reverse records that name it (0x27962c-0x279810). The build report differs
  in Alpine's line (469 192 -> 480 952 bytes of scenery, the props note), the seven reverse variants' load, maps
  and race blob addresses (+0x20) and the polygon ROM left.

### 3.2 Room used [V]

| | before (`p28play2`) | after | used |
|---|---|---|---|
| polygon ROM free | 461 548 bytes | 449 800 | 11 748 (floor 65 536: 384 264 above it) |
| Alpine's scenery objects | 469 192 bytes | 480 952 | 11 760 |
| colour table, the run the annex uses | 3 800 entries | 3 784 | 16 |
| highest colour entry read | 0x9b34b | 0x9b35b | +16 |
| TGP data free | 7 631 words | 7 631 | 0 |

## 4. The rate and the game, with and without the trees [V]

Method (`scratch/drive.py`): Alpine on `out/p28play2` with the standing test's autopilot line (`_drive_line`), the clock held
(`VR_HOLD_CLOCK`), 240 s, `VR_INPUT_LOG` (the tape), `VR_PASS_LOG`, `VR_FRAME_LOG`, `VR_RATE_LOG` (runs `M_n`, `M_r`); then
`out/p29play1` fed those tapes frame for frame (`VR_INPUT_REPLAY`; runs `A_n`, `A_r`). Same battery RAM (fresh). The stretch:
road points 400-449 (reverse: 3-52 in the run's numbering), after the green.

| | normal, main | normal, trees | reverse, main | reverse, trees |
|---|---|---|---|---|
| tape fed | - | main's, line for line | - | main's, line for line |
| pass log (6 765 passes + END) | | **identical** | | **identical** |
| race frames measured | 6 100 | 6 100 | 6 100 | 6 100 |
| records a frame on the stretch (669 / 877 frames): median, max | 1 924, 3 090 | 2 190, 3 118 | 2 535, 3 833 | 2 640, 4 085 |
| records added a frame (trees - main) on the stretch | | 0 to +266, median +252 | | +28 to +252, median +28 |
| records peak, whole race | 4 330 | 4 330 | 4 601 | 4 601 |
| V60 busy, worst (frame) | 11 142 us (1 959) | 11 142 us (1 959) | 11 271 us (1 607) | 11 271 us (1 607) |
| V60 busy, frame by frame | | identical on all 6 053 frames | | identical on all 6 053 frames |
| overrun counter 0x501148 | 0 -> 0 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| render rate from the green | 28-29 | 28-29 | 28-29 | 28-29 |
| frames with a skipped list | 0 | 0 | 0 | 0 |

The trees add records on 1 295 (normal) and 1 368 (reverse) of the race's frames, at most 266 (budget 10 500). As the recon found,
records cost no emulated time in MAME: the busy time is the same to the microsecond on every frame. The standing test on the
built set: §7.

## 5. The look [V pictures; the judgement is Pascal's]

Before/after pairs from the same frame of the same race (the replays above, snapshots every 4th frame over the stretch on both
sets, `runs/S_*`, compared pixel by pixel): `out/p29/look/` (NOTE.txt says what each shows).
Visible from 393-403 (trees 1-2, top left), 417-447 (the end groups), in reverse from normal 16 down to the line and from normal 437
to 414 (trees 1-2, small, top right). On frames between, the crest trees are above the camera's view or behind the rock faces.

- **Scale:** Big Forest's tree is 16.35 units; Alpine's own Saturn pines are 30-120, about 2 to 7 times taller. Side by side the arcade trees read as small dark
  cones, saplings rather than a forest. This is the plainest difference.
- **Colour and snow:** Big Forest's dark greens (0, 72, 0), (0, 104, 0), olive (64, 96, 0) and a brown trunk, against Alpine's
  brighter pines (0, 128, 40). Neither carries snow; on the snow they read as dark, not wrong-coloured. Nothing was recoloured.
- **Planting:** on the flat right of 448-449 they stand on the snow at the road's level; on the crests the foot is at the lowest
  ground under the trunk (slopes up to about 25 degrees).
- **From both sides:** the 4-face canopy and 3-face trunk are closed, culled as Big Forest draws them; the reverse pictures show
  them whole.
- **A second prop** (the brief allowed one from the recon's inventory) was not tried: the colours are not wrong; the scale is, and
  the inventory's other trees (Bay Bridge's palm, 3 x 4 x 3) are smaller still.

## 6. Tests

- `tests/test_props.py` (new; red first: the module did not exist): the copy turned and moved; `assign_colours` writing the faces
  with the prop's drawn corners, lighting normal and palette index and encoding them culled; the nearest colour kept for Saturn faces; `ground_height`; the planting's
  axes and its refusal of a road point the course does not have; a capped cell that holds prop faces refused
  (`geometry.first_split`); a copy kept whole in its foot's cell; `plant` standing a copy on the ground and refusing the void, a slope, a collision quad within PROP_CLEAR, the Saturn's
  upright scenery; `prop_from_quads`; on the user's ROM, Big Forest's tree (7 faces, four palette indices, 16.35 high, every
  source face culled, its stored normal the reversed winding's); on the build, Alpine's sites in its cells (the faces read back
  from the built polygon ROM), every tree's foot at least PROP_CLEAR from every collision quad read back from the built TGP data,
  and the build with `props=()` against the build with them (the TGP data and program byte for byte the same; the three
  originals' tile tables, objects and colour words the user's ROM's own, in place; every converted cell without a tree the same
  object bytes and colour words; Alpine's four tree cells 14 records a tree and four colour entries larger); in MAME, both
  directions: the tree cells' objects named in the display list while the player is on the approach and the stretch (dumped
  every 20 frames) and the three measures of the rate. What the display list shows: each tree cell's object is drawn, under a
  record limit (the draw budget, 10 500) larger than the object, which runs to its end marker in the with-trees record count (14
  a tree more than without props); the list itself does not carry the object's size.
- The final invocation: §7.

## 7. The final invocation

One run, after the review's fix wave (§11), at commit `db06c54` (the fixes; the commits after it change documents only), from
the worktree, 15 Nov 18:51-20:32:

```
source out/env.sh && VR_MAME_JOBS=2 PYTHONPATH=$PWD .venv/bin/python -m pytest \
  -o addopts="" -p no:cacheprovider -q -rfE tests/test_props.py tests/test_tencourse.py tests/test_directory.py \
  tests/test_gate_lettering.py "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate[entry_3]" \
  "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate[entry_3_reverse]" --basetemp out/p29/pytest_fix
```

(`out/env.sh`, `.venv` and `out/` are the main checkout's.) **66 passed, 16 skipped, 0 failed, 0 errors in 6 084.57 s
(1:41:24)** (`out/p29/pytest_fix.log`). No failure, so nothing to compare with the known-failing list
(`out/p27/full_failed.txt`, 15 names, none of them among this invocation's 82 tests).

- **The 16 skipped** are all in `tests/test_directory.py`: the worktree has no `build/mame/unidasm` (conftest skips a test that
  needs it). Those tests were then run apart with `disasm.UNIDASM` pointed at the main checkout's `build/mame/unidasm`:
  `tests/test_directory.py` **26 passed** in 1.93 s (`out/p29/pytest_fix_directory.log`). The branch touches neither the
  directory code nor its tests.
- **In the 66:** `tests/test_props.py` 18 (the two MAME drives among them), `tests/test_tencourse.py` 16,
  `tests/test_gate_lettering.py` 20 (the seven that were red before I1's fix among them), the 10 of `tests/test_directory.py`
  that need no disassembler, and the standing rate test on Alpine in both directions (2).
- The whole suite was not run (§11).

## 8. Not verified

- Real hardware (as Phase 28: MAME does not model the render board's time). Nor how real hardware draws the copies' records
  where they differ from the source's (type-1 records with a repeated corner for the triangles; flag bits 23 and 24 clear, §1).
- What Pascal saw: they ran the set for 110 s and said "i think it s good" (the head of this document); which course and
  which trees they saw was not stated, and the recording has not been played back.
- The look from a human driver's line: the pictures follow the autopilot, which runs wide at 393-403 and turns sideways at the
  line in reverse.
- Whether trees over the void (at the Saturn pines' base height) or larger copies would look better: not built (not in the brief's
  rules; scaling would be new geometry).
- The rate test's other races: only Alpine's two (normal, reverse) are part of this phase's claim (§7); whether the module's
  prefetch ran others in the final invocation was not looked at.

## 9. Next (not built)

The same `PropSource`/`Planting` path takes Bay Bridge's palm on Surfers Road (a spawn-list object, so a `PropSource` read from an
object address rather than a cell; palette: Bay Bridge's template, the shared polygon palette).

## 10. Files (git-ignored, `out/p29/`)

As listed on 15 Nov after the fix wave:

- `scratch/`: `alpine_data.py` (-> `alpine.pkl`), `alpine_only.py`, `topview.py`, `probe.py`, `zones.py`, `zones2.py`,
  `zones3.py`, `cands.py`, `cands2.py`, `pick.py` (-> `picked_29..38.pkl`), `pines.py`, `hmap.py`, `treemap.py`, `drive.py`,
  `rates.py`, `romdiff.py`, `cellcmp.py`, `find_trees.py`, `tree_normals.py`, and their pickles and pictures.
- `runs/`: `M_n`, `M_r` (main, autopilot), `A_n`, `A_r` (trees, replay), `B_n`, `B_r`, `B2_n`, `B2_r`, `S_A_n`, `S_A_r`, `S_B_n`,
  `S_B_r` (snapshot replays); the runs' logs `runs_*.log` and scripts `runs_A.sh`, `runs_S.sh`, `runs_redo.sh` beside them. A
  display-list run `D_n` has only its log (`runs_D_n.log`); the display lists the tests dumped are under `pytest/`.
- `look/`: `normal_1..5_frame*.png`, `reverse_1..3_frame*.png` (the pairs), `map_trees.png`, `trees.txt`, `NOTE.txt`.
- `build_p29play1.log`; `final_pytest.log`, `pytest/`, `pytest_quick/` (the prototype's runs); `pytest_fix.log`, `pytest_fix/`
  (the fix wave's final invocation, §7).
- Outside `out/p29/`: `out/p29play1` (the set Pascal ran), `out/p29play2` (the fix wave's rebuild, §11), `out/rec162/launch.sh`
  (the playtest launcher: `out/p29play1`, records to `inp/play.inp`).

## 11. The review and its fix wave (15 Nov)

An independent review of the branch found four important points (I1-I4) and minor ones (M1-M11); each was checked before it was
touched.
The branch was first rebased on main (two doc-only commits to `docs/follow-ups.md`; both kept, this phase's section before
Phase 30's).

| | finding | checked | done |
|---|---|---|---|
| I1 | `convert_tiles`: the prop copies' list reused the name `copies`, the gates' lettering count, so `report["lettering_copies"]` was a list on every course | true: `test_gate_lettering.py::test_only_the_gates_cells_change_and_convert_tiles_leaves_the_course_alone` red on all seven courses (`assert [] == 28`) | the list is `prop_copies`; the test green (7 passed) |
| I2 | "nothing but the tree cells changes" rested on scratch scripts | true | `test_the_props_change_only_the_tree_cells`: `build_all` with `props=()` and with them (§6) |
| I3 | the head and the follow-ups inferred from Pascal's words | true ("read as") | the two quotes and the run as they are, nothing inferred (the head, the follow-ups) |
| I4 | the deviation and the follow-ups said less than §3.1 about the other courses | true | both say it: the originals in place; the six other converted courses identical in content, relocated |
| M1 | "exactly as the arcade stored them" | true: the source's seven faces are three type-1 and four type-2 (triangle) records with flag bits 23/24 set on them; the copies are type-1 chains with a repeated corner, those bits clear; corners, normal, palette index, cull bit, z mode 2, light mode 0 the same | `props.py`, the test's docstring and name, §1, §8, the deviation |
| M2 | the ROM test's docstring said "all culled" and asserted neither that nor the normal | true | it reads the source records and asserts both (properties only) |
| M3 | the draw test showed the cells drawn, not the trees' records | true; and the display list's command does not carry the object's size: its count is the draw budget (10 500) | the test asserts each tree cell's object runs to its end marker in the with-trees count (14 a tree over the build without props), under the command's limit; docstring and §6 say what that shows |
| M4 | PROP_CLEAR is measured from the foot; the tree's reach is 5.116 | true | the comment, §1, §2, the deviation, the follow-ups say "foot"; the canopy can come within about 4.9 |
| M5 | a cell over `max_records` would drop prop faces silently | true (no cell is capped today) | `geometry.first_split`: ConvertError for a capped cell that holds prop faces; `test_a_capped_cell_that_holds_prop_faces_is_refused` |
| M6 | `prop_from_cell`'s errors did not name the course | true | inside the `try` in `convert_course` |
| M7 | `planting_xz` wrapped an out-of-range road point | true | ConvertError; `test_a_planting_on_a_road_point_the_course_does_not_have_is_refused` |
| M8 | the height comparison differed across the three documents | true | 16.35 against 30-120, about 2 to 7 times taller, in all three |
| M9 | §10 listed files that do not exist (`runs/D_n`) | true | §10 lists what is there |
| M10 | - | not in the fix wave's brief | - |
| M11 | unused imports in `tests/test_props.py` | true (`PALETTE_BASE`; `math` is used now) | removed |

**The set after the fixes [V]:** `out/p29play2`, `vrtools build` from the fix wave's tree (`vrtools.__file__` the worktree's; the
code as committed, log `out/p29/build_p29play2.log`): all 38 members of its `vr.zip` byte for byte those of `out/p29play1`, the
set Pascal ran; `model1io.zip` and `m1comm.zip` the same; the build report differs in its last line (the set's own path).
`out/p29play1` was not touched. No windowed MAME was run.

Not verified in the fix wave: real hardware; Pascal's recording (not played back); the whole suite (not run: the final
invocation is §7's).
