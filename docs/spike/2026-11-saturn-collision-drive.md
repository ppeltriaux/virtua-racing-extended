# Spike log: Big Forest driven on Saturn-derived collision data (Nov 2026, Phase 5 Task 6)

`spike/saturn_collision_build.py out/p5/build` converts the Saturn Big Forest road
slices into TGP collision quads and cell lists (`vrtools/convert/collision.py`),
writes them into the free TGP data ROM with slot 2 repointed and the Big Forest
collision map rewritten (`patch_collision`), and drives the result with the
collision probe (`collision_log.lua`). The autoplay has no steering: the car is
floored from the grid and runs straight, so the comparison is the stretch before
it first leaves the quads.

## Numbers

| | arcade Big Forest | Saturn-derived |
|---|---|---|
| quads | 3,840 | 430 (one per Saturn slice, 40-unit verge margin, 1-unit overlap) |
| collision cells | 1,368 | 1,566 |
| TGP words | 73,210 (286 KB) | 14,679 (57 KB) |

60-second runs, player samples from the probe (one per logic frame):

| | original | Saturn-derived |
|---|---|---|
| samples | 916 | 735 |
| distance (XZ) | 1,293 | 1,298 |
| on-road before the first exit | 1,293 (never left) | 693 units / 496 samples |
| off-road (id 0) / no-hit | 0 / 0 | 2 / 16 |
| unanswered | 0 | 0 |
| height range on the road | 30.0 – 45.1 | 30.0 – 30.0 (flat height function) |

The car drives the whole start straight on the converted data at the expected
height, with every collision call answered, and leaves the quads where the
first bend starts. The original car, with the same centred wheel, follows the
road all the way: the quad attribute word is the road direction and the game
steers along it (`docs/formats/model1-tgp-collision.md` §4); the converted
quads carry 0 until the slices are in lap order (M3), so the unsteered car runs
straight into the first bend, where the arcade's run-off would still have
caught it (the arcade band is up to 170 units wide at the start straight, the
converted band is the tarmac plus 40 units each side). `tests/test_tgp_build.py` pins
this: course Big Forest, ≥ 500 samples, ≥ 600 units on the road, < 5 % off-road
or no-hit, no unanswered calls, heights within 28–32.

## What it took

1. **Empty list at offset 0.** The TGP reads the count at `block + id` for
   every id including 0 (off-road cells). The first build left that word erased
   (0xffffffff): the quad loop ran forever, the V60 spun on the "done" word,
   and the race never drew a car. The originals keep a zero count at offset 0
   of every block, which is why their lists start at offset 1. `patch_collision`
   now writes it.
2. **Seams.** Consecutive Saturn slices do not share an edge exactly (16.16
   planes: quad 108 ended at z 210.62, quad 109 started at 210.63). The car hit
   the seam, got height 0, dropped under the road and never recovered. Each
   quad is now stretched by 1 unit at both ends along the road.
3. **Verge margin.** The arcade start grid puts the player 30 units left of the
   single lane past the grid; a 30-unit margin left the car 0.4 units outside
   the band. Margin 40.
4. **Probe semantics.** The player makes five calls per logic frame (centre and
   four wheels within a few units); opponents call once on the other frames.
   "No hit" is the TGP answering height 0 while the car is still above 1.
5. **Race start varies between MAME invocations.** Runs in one process are
   identical, but the frame the course loads at was seen at 865, 1263, 1293 and
   1605 across invocations, and autoplay used to hold the wheel at the select
   position until frame 1700, so an early start meant a race driven hard left.
   Autoplay now detects the course load (TGP command 0x0680) and centres the
   wheel one frame later; the log carries the course RAM, the machine clock and
   the detected start (`S` lines) and the test asserts Big Forest, data index 2.
   The cause of the varying start is not known (the script's frame counter
   agrees with the machine clock in every run inspected).

## Deviations for the list

- Run-off beyond 40 units of the tarmac has no collision surface on a
  converted course (the arcade covers up to 170 units at the start straight).
- The converted quads carry attribute 0; the originals carry the road direction,
  which the game steers along. Until the slices are ordered (M3) a converted
  course has no road-following help.
- The arcade still draws its own road, so on this test build the car visibly
  runs on grass where the Saturn grid lane merges (frame 2400 snapshot, at
  320 km/h): grass effects come from the V60's road lines, not from the TGP.
- Height is a constant 30 here; a real conversion samples the Saturn ground
  mesh (`mesh_height`), still to be chosen per group (Phase 4 open item).
