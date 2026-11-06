# Alpine drives in Big Forest's slot (Phase 6, M3)

`spike/alpine_build.py out/p6/alpine` builds the set and races it for 90 s under the autopilot
(`tests/test_tgp_build.py::test_alpine_drives_in_the_big_forest_slot` is the same pipeline with thresholds).
Numbers below are from `out/p6/alpine/summary.txt` (local, not committed).

## Pipeline

Saturn `ALPINE00/TRCKALPN` → `choose_placement` (grid pose from Big Forest's road point 13) → under `placed(...)`:
`order_slices(start_slice, direction)` → `road_profile` / `profile_height` → `saturn_collision(lap=)` →
`road_tables` → `build_bank` + `install_bank` (course 0) → `patch_collision` (slot 2) → `convert_tiles` +
`patch_course_tiles` → `patch_pit_entry(slot 2, None)`.

## Numbers

| | |
|---|---|
| slices | 528, 526 ordered, 0 skipped, route 380 (the other branch of a fork is left out) |
| lap | 4616 units, 452 road points, 526 segments (one per tarmac quad) |
| placement | centreline point 306 at the grid, start slice 223, rotation 89.9°, shift (−299, 187), max extent 765, 0 tiles outside |
| heights | −55.3 .. 0.3 (the grid sits at −12.7, the road climbs to 0 by road point 27) |
| collision | 1578 quads (526 tarmac + verges), 2325 cells, 38 977 words |
| scenery | 1631 quads in 51 cells, 366 colour entries, 133 744 polygon bytes, no capped cell |
| drive (90 s, autopilot) | 1416 probe calls, 2973 units, 0 off the collision surface (verges count as on), 0 no-hit; progress forward 2842 / backward 51; course (0, 2) |
| render rate | 28–29 display-list switches per 57 frames (the arcade's rate) |

## What it took beyond Tasks 2–7

**Placement.** The start grid is an absolute arcade position (player at (−230, −270) heading +z; Big Forest's
road point 13 is at (−193, −273)), not a road-line point. Without a placement the cars start 165 units from
Alpine's road in the void. `vrtools/convert/place.py` searches the lap (identity placement, every 3rd centreline
point) for a point whose rotation to +z and shift onto the grid pose keeps the whole centreline within ±1000 and
every tile inside the map, and puts the lap start 13 points before it. The transform is applied in arcade space
inside `to_arcade` and `tile_to_arcade` (`geometry.placed`), so road and tiles move together. The Saturn start
line moves (deviation).

**Pit lane.** The first drives ran 350 units, then the game took the car over, drove it back to the grid, showed
PIT WORK, parked it for 7 s and released it, every 22 s. Traced with RAM diffs, write taps and a stack capture:
the player's per-frame handler (boot ROM 0xfe8e88) enters the pit sequence when `entity+0x1bf` (pit stops left,
2 at the start) is non-zero, the car heads along the road (|heading − road heading| < 0x4000) and the
lap-position quad (`entity+0x150`, the last tarmac quad) equals the per-slot halfword at **0xfe8e0c** or that + 1:
Bay Bridge 0xffff (no pit lane), Acropolis 28, Big Forest 30. Big Forest's quads 30–59 are the pit lane beside
the start straight (lateral −33, flag 66 in the segment array) and 1085–1088 its entry taper; quads 0–29 are the
main straight. A converted course numbers its tarmac quads in lap order, so quad 30 is ordinary road 200 units
past the start. Segment flags are not involved (a build with every flag 1 behaved identically), so the generator
now emits flag 1 everywhere and `patch_pit_entry(rs, slot, None)` sets the slot to Bay Bridge's "no pit lane".
Deviation: no pit stops on converted courses until a pit lane is built (M5+).

**Boot ROM layout.** `RomSet` interleaved the two boot chips; MAME loads them flat (`ROM_LOAD` at 0xfc0000 and
0xfe0000). Fixed with tests; boot-region disassembly was garbage before. Shipped sets were unaffected
(`to_files` mirrored the layout).

## Drive and snapshots

The autopilot takes 6 s of countdown, reaches the centreline by road point 22 and runs the lap at 200–260 km/h;
it leaves the road for 8 s on the hairpin around road points 139–149 (its fixed gain and 60-unit lookahead, not
the data) and rejoins. EXTEND TIME appears at lap time 0'18" and the clock reads 41 at 0'34": the checkpoints
fire on the converted lap.

Snapshots (`out/p6/alpine/run/snap/`): at 10 s the car is on Alpine's straight with Big Forest's sky, backdrop,
HUD and course name (expected: those are M4 items); the HUD map draws Alpine's outline from the converted
centreline. At 25 s (the hairpin excursion) the camera is inside a sloped ground tile. At 42 s, on the road at
260 km/h, the car is not visible: a large Saturn ground quad is drawn over it. The arcade sorts objects by
depth; Saturn's ground group has quads much larger than Big Forest's, so one can sort in front of the car.
Finding for the scenery pass (split large ground quads), not an M3 blocker.

## Deviations added by this task

- The start line moves to wherever the lap best fits the arcade's grid pose (Alpine: centreline point 306, i.e.
  3060 units into the Saturn lap).
- No pit lane / pit stops on converted courses (pit entry disabled for the slot).
- Segment flag 66 (pit lane) is never emitted.
- Large ground quads can occlude the car (to fix in the scenery pass).
