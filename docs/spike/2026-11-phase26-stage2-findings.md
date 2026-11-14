# Phase 26 stage 2: findings

The measured findings of stage 2 of `docs/superpowers/specs/2026-11-11-reverse-courses-design.md` (§6.7: the other six converted
courses raced the other way round, behind stage 1's debug flag). Facts and numbers only. Plan:
`docs/superpowers/plans/2026-11-12-reverse-stage2-six-courses.md` (decisions D1-D8); recon:
`docs/spike/2026-11-phase26-stage2-recon.md`. The scripts, logs, builds and contact sheets quoted are git-ignored under
`out/p26/stage2/` (one directory per task: `blob/`, `task2/`, `t3.log`, `credits/`, `t5/`, `t6/`, `t7/`, `figures/`, `t8/`; after the
owner's drive `drive/`, `gates/`, `t10/`, `t13/`, `surfers/`, `t12/`, `arch/`).

**Map:**
- §1 what was built;
- §2 ROM room: the annex and bank 1's three lines (Task 2);
- §3 a reverse lap's time (Task 3);
- §4 the start spot (Task 4, narrowed in Task 6);
- §5 Alpine's standing start (Task 5);
- §6 the seven reverse races (Task 6);
- §7 the start figures of the Acropolis template (Task 7);
- §8 the normal direction against main, the annex's readers and the normal pins (Task 8);
- §9 open after stage 2;
- §10 the verdict;
- §11 after the owner's drive: §11.1 what the owner reported; §11.2 the gates' lettering from both sides; §11.3 the start
  figures (§11.3.1 the placement turned half a turn, §11.3.2 the animation mirrored too: built); §11.4 the reverse checkpoints
  renumbered (Diablo Canyon's START gate); §11.5 the start crashes (the bank-1 grid interleaved, Metropolis's pairs, the known
  fault); §11.6 the arcade start gantry (its lettering readable from behind; the reverse starts measured on the merged set);
  §11.7 the frame's record budget.

## 1. What was built

- **Seven variants.** Every converted course (entries 3-9: Alpine, Amazon Falls, Diablo Canyon, Metropolis, Pacific Coast,
  Surfers Oval, Surfers Road) carries a reverse variant. As in stage 1: its own header, segment array, pointer block and
  lines in the course's own data bank beside the normal blob; the normal course's collision map, surface table and backdrop;
  its own load record, maps record and race blob. The flag `course.DIRECTION_RAM` (0x502294) picks it on the menu path; it is
  still set from Lua on the select screen (`direction.lua`). The screen is stage 3.
- **One annex** for the seven variants' records and race blobs, in the erased tail of the program ROM's colour-table run
  (plan D1, §2). Metropolis's records left `CODE_FREE` with it.
- **Three stored lines on the bank-1 courses** (plan D2, §2): the variant's eight pointer pairs name three stored lines.
- **One road-part builder** (plan D3, stage 1's deferred finding): `build_course_blob` and `build_variant_blob` share
  `blob._road_part`. Every normal blob kept its bytes: Task 1 recorded the arguments of the 14 `build_course_blob` calls of
  one `build_all` and the seven variants' inputs, fed the same inputs to the old module (`git show HEAD:vrtools/arcade/blob.py`)
  and the new one, and the 21 digests were identical (`out/p26/stage2/blob/digest.py`, `before.txt`, `after.txt`).
- **A reverse lap's time** (plan D4, §3), **the start spot** (plan D5 as narrowed, §4).
- **Two boot sites, two routines** beside `dirattr` in the directory image: `startbit` (20 bytes, site 0xfe41d6, plan D6: §5)
  and `figures` (19 bytes, site 0xfc0bf2, plan D7's fallback: §7). Both sites are patched with or without variants. The image
  grew 39 bytes; `end − loader` is 4 429 bytes, 571 under `tests/test_directory.py`'s bound of 5 000.
  (Superseded after the owner's drive: `figures` is the 178-byte half turn at 0xfc0ea5, §11.3.1; with the figures' animation
  routines the direction routines take 463 bytes, 179 left, §11.3.2.)
- No course's collision changed: no start band on any course, and `tests/test_tencourse.py`'s TGP floor `tgp_budget >= 7_500`
  stands.

## 2. ROM room: the annex and bank 1's three lines (Task 2)

**The annex** (`tencourse.annex_regions()`, `reverse_annex`). The first region that holds the seven variants, in order: the code
area past the directory image (the recon: 7 924 erased bytes on the stage 1 build, 9 864 without its annex, the longest run
1 792: room for one variant), then the colour-table run
0x2b1842..0x2c0000 (erased in the original, 59 326 bytes). They land in the second. Decoded from the fresh build of Task 2's
Step 4 run (`out/p26/stage2/task2/t2nums.py`):

- load records 0x2b90c0, maps records 0x2b97cc, race blobs 0x2b9990, end 0x2bcb00; 13 568 bytes to 0x2c0000 (13 552 after the
  margin), as recon §1 predicted;
- the run's other writers stop before it: the colour words at 0x2b6698 (`max_colour_entry` 0x9b34b, its word at 0x2b6696;
  the annex's first halfword is entry 0x9c860) and select picture 9 at 0x2b90b0.

| entry | course | bank | variant header | load record | race blob | table bytes | lines stored |
|---|---|---|---|---|---|---|---|
| 3 | Alpine | 3 | 0x15a2b0 | 0x2b90c0 | 0x2b9990 | 63 520 | 8 |
| 4 | Amazon Falls | 1 | 0x1e4520 | 0x2b9100 | 0x2ba0a0 | 20 496 | 3 |
| 5 | Diablo Canyon | 2 | 0x18acd0 | 0x2b9140 | 0x2ba7b0 | 66 112 | 8 |
| 6 | Metropolis | 2 | 0x19af10 | 0x2b9180 | 0x2baec0 | 52 080 (after the owner's drive: 40 144 bytes, 6 lines, §11.5) | 8 |
| 7 | Pacific Coast | 1 | 0x1e9530 | 0x2b91c0 | 0x2bb5d0 | 25 360 | 3 |
| 8 | Surfers Oval | 1 | 0x1ef840 | 0x2b9200 | 0x2bbce0 | 25 136 | 3 |
| 9 | Surfers Road | 1 | 0x1f5a70 | 0x2b9240 | 0x2bc3f0 | 28 896 | 3 |

- **Data banks after the variants:** bank 1 one free run of 13 488 bytes (at +0xfcb50); bank 2 99 712 + 167 452 (after the
  owner's drive, with Metropolis's six lines, the run after its variant is 111 648, §11.5); bank 3 353 584 + 133 956.
- **Bank 1's three lines** (plan D2): pairs `(0, 7, 7, 5, 5, 5, 5, 7)` on Amazon Falls, Pacific Coast, Surfers Oval and
  Surfers Road (`tencourse.BANK_ONE_PAIRS`): the centreline for the player, the −5 line for cars 1-4 and 13-15 (7 cars), the
  +5 line for cars 5-12 (8 cars); the car table unchanged. Chosen on the recon's trial races (jolts with these three lines
  95 / 73 / 12 / 24 on Pacific, Surfers Road, the Oval, Amazon, against 106 / 85 / 12 / 30 with eight; recon §2).
- **Phase 18b's room check** (`test_every_course_has_its_own_backdrop`, at least 16 KiB in free runs of 32 KiB or more per
  bank) failed on bank 1 under D2: its one run of 13 488 bytes is below 32 KiB. Ruling of the session lead: the check keeps
  16 KiB for banks 2 and 3, and bank 1's becomes "largest free run (`min_size=16`) ≥ 13 000" (`BANK_ONE_FLOOR`, shared with
  `test_bank_one_keeps_three_lines_a_course`), because design §6.4 spends bank 1's room on the reverse lines.
- **Command** (Task 2 Step 4, one invocation, the ten MAME tests of `tests/test_reverse_build.py` deselected by node id):
  `.venv/bin/python -m pytest tests/test_tencourse.py tests/test_cli.py tests/test_reverse_build.py -rA --basetemp
  out/p26/stage2/task2/bt-step4 --deselect ...`: 41 passed, 1 failed (the Phase 18b check above); after the ruling the two
  tests concerned, 2 passed (`out/p26/stage2/task2/step4.log`, `ruling.log`).

## 3. A reverse lap's time (Task 3)

`race.time_records_for(..., lap_total=)` scales every raw extension of the variant's record by one factor, so that the first
lap's sum equals the normal record's (`race.lap_total`: the first `len(checkpoints)` extensions). Where the reversed sectors
are the normal ones in another order the factor is 1 and the record is the unscaled one: the six other courses' variant blobs
keep their bytes (Metropolis's is pinned byte for byte against `race_blob_for` without `lap_totals`).

Diablo Canyon's first-lap sums, the 12 records sorted by (variant, level):

| | sums |
|---|---|
| normal (unchanged) | 1176 1176 1199 1199 1137 1143 1173 1179 1148 1148 1171 1171 |
| reverse before | 1059 1059 1084 1084 1017 1023 1056 1063 1029 1029 1054 1054 |
| reverse after | 1175 1175 1200 1200 1137 1143 1172 1179 1147 1147 1171 1171 |

- Level 0's reverse extensions: 389, 255, 415 before, 432, 283, 460 after. The difference against the normal sums (at most
  1) is rounding; `test_a_reverse_lap_has_the_normal_laps_time` allows `len(checkpoints)` on all 7 courses × 12 records.
- In the reverse race the checkpoints fire with 431 / 282 / 459 (the blob's value or one less, stage 1's form) and the clock
  never ran out on Diablo (the recon's trial: out at 109 s).
- **Command:** `tests/test_convert_race.py` and four set tests of `tests/test_reverse_build.py` in one invocation,
  `--basetemp out/p26/stage2/t3`: 11 passed (`out/p26/stage2/t3.log`).

(Superseded after the owner's drive: Diablo Canyon's reverse checkpoints are the normal ones renumbered, (0, 36, 168, 278),
and its reverse records are unscaled with the normal lap's sums; §11.4. That in turn was superseded on 13 Nov after stage 3's
drive: (0, 168, 278) again, the START arch no reverse checkpoint; stage 3 findings §12.)

## 4. The start spot (Task 4, narrowed in Task 6)

**Plan D5** (`reverse.reverse_segments`): a tarmac quad the reversed walk credits n − 1 that holds the reverse start spot
(forward point 0, edges within `SEAM_OVERLAP` = 0.5) is credited 0. Offline measure on a fresh conversion against main's
(`out/p26/stage2/credits/fresh.py`, `measure.py`, `measure.out`; along > 0 is before the line in reverse travel):

| course | n | quads changed n − 1 → 0 | along span | quads still credited n − 1 | quads holding the spot |
|---|---|---|---|---|---|
| Alpine | 452 | 0 | −0.5..+6.9 | 7 (1-7): 1, 2 beside quad 0; 3-5 on the side; 6, 7 from +4.1, +6.9 | 0, 564 |
| Amazon Falls | 330 | 0 | −0.5..+5.9 | 4 (1, 2, 6 on the side strip; 5 on the road +5.8..+17.6) | 0, 518 |
| Diablo Canyon | 457 | none | — | 2 (1, 2, from +2.8) | 0, 808 (credited 0 already) |
| Metropolis | 365 | none | — | 1 (1, +3.9..+15.6) | 0, 526 (credited 0 already) |
| Pacific Coast | 410 | none | — | 1 (1, +3.4..+15.9) | 0, 646 (credited 0 already) |
| Surfers Oval | 387 | 0 | −0.5..+12.4 | 2 (2, 3: apron only) | 0, 755 |
| Surfers Road | 441 | 0 | −0.5..+11.2 | 1 (2: apron only) | 0, 902 |

**The rule misbehaved on the two Surfers courses** (Task 6's first race run, `out/p26/stage2/t6/pytest.log`, `parked.py`):
quad 0 was the road's only quad credited n − 1. Credited 0, no car was ever credited n − 1: at every reverse crossing (20 on
the Oval, 16 on Surfers Road) the road point went from n − 2 straight to 0; after its first wrap each opponent's line cursor
stayed at n − 1 (386 / 440) and the car stood at the line. Parked 10 and 5 of 15, 3 steps back over the line on the Oval; on
Surfers Road every opponent ended the 150-s race there, the leader one lap (441 points) on. In the normal race and in the
recon's trial a car sits on n − 1 for 8-20 frames at each crossing and the cursor wraps.

**Ruling (Task 6): D5 narrowed.** The change is applied only if afterwards some tarmac quad credited n − 1 still holds a point
of the reversed centreline before the line (`_before_line`: from reversed point n − 1 to the spot, every 0.5 units; strict
containment); otherwise it is withheld and the walk's credits stand. Fresh conversion (`out/p26/stage2/t6/measure.out`,
`geom.out`):

| course | changed against the walk | n − 1 quad over the centreline before the line | D5 |
|---|---|---|---|
| Alpine | quad 0 → 0 | 6 | applied |
| Amazon Falls | quad 0 → 0 | 5 | applied |
| Diablo Canyon | none | 1 | nothing to change |
| Metropolis | none | 1 | nothing to change |
| Pacific Coast | none | 1 | nothing to change |
| Surfers Oval | none | 0 (the spot's quad) | withheld |
| Surfers Road | none | 0 (the spot's quad) | withheld |

- **On Surfers Oval and Surfers Road the quad under the spot is credited n − 1, and the player's road point still reads 0
  at the first race frame** (both races of §6; the recon read 0 on the Oval too). Why the spawn reads 0 there is not
  investigated: measured, not explained. The Amazon-type fault (a spawn credited n − 1 and a first crossing with no lap) is
  guarded on those two courses only by the race assertions (start point 0, every crossing +1 lap), which pass.
- **The arrays are read backwards** (Task 2's deferred check, added in Task 4): away from the line (forward credit 10..n − 10),
  (forward + reverse) mod n measured −3..+10 on all seven (about a quad's own length in points: forward credits the front
  edge, reverse the rear); the test's bound is −3..+12. An array not reversed would be hundreds of points off.
- **Commands:** Task 4, `.venv/bin/python -m pytest tests/test_convert_reverse.py tests/test_convert_road.py
  tests/test_reverse_build.py::{the nine static tests} --basetemp out/p26/stage2/t4pytest`: 41 passed
  (`out/p26/stage2/credits/pytest.out`); Task 6 after the ruling, §6's second invocation.

## 5. Alpine's standing start (Task 5)

`startbit` (plan D6, Pascal): mode 0x11 sets the race-start task's bit 0x1e (the crew, "PIT START", start of the Big Forest
template) only when the flag is 0. Runs of 45 s with the game's own inputs (no autopilot, deterministic), `start_log.lua` from
the course load (frame 1600 in all six runs; 990 frames logged each):

| run | pit state | mode 0x12 / 0x13 / 0x14 (frames from the load) | at the first mode-0x14 frame |
|---|---|---|---|
| Big Forest, flag 1 (written back 0) and flag 0 | 6 at 4, 7 from ~10, 0 at 323 | 4 / 324 / 326 | (−230.38, −269.57), yaw 0, point 13, lap 0 |
| Alpine normal, stage 2 set and set without variants | as Big Forest | 4 / 324 / 326 | (−230.38, −269.57), yaw 0, point 15 |
| Alpine reverse | 0 on every frame | 4 / 262 / 264 | (−265.07, −393.39), yaw = attribute 27246 (0x6a6e), point 0, lap 0, flag 1 |
| Metropolis reverse (control) | 0 | 4 / 262 / 264 | yaw = attribute 32761, point 0, lap 0 |

- Each pair's (frame, mode, pit state, x, z) streams are equal over all 990 frames.
- Reverse Alpine stands on forward line point 0 with that point's yaw 0xea6e + 0x8000 (settled by frame 50 after the
  load); no wrong-way warning read from the load on.
- Opponents on reverse Alpine stand still from frame 8 to the green (displacement 0.0 for all 15) on reversed road points 0,
  2, 3, 4, 5, 7, 7, 8, 9, 10, 11, 12, 13, 14, 14, lap 0 (car 1 shares point 0 with the player); reverse Metropolis alike.
  With the crew start they roll during the wait (164-439 units), as in the recon.
- **Command:** `tests/test_direction.py` (12 passed) and, in one invocation `--basetemp out/p26/stage2/t5/mame`, the three
  start tests of `tests/test_reverse_build.py`: 3 passed in 575 s (`out/p26/stage2/t5/mame.log`).

## 6. The seven reverse races (Task 6)

Each course raced 150 s each way in one pytest session (one conversion), under the autopilot (the drive line, read backwards
in reverse), stage 1's loggers and assertions; every bound is the normal test's own constant for the course or measured
against the normal race of the same session. Race window 1866-8630 (117.6 s) on every race but normal Alpine (1928-8630, the
crew start). Numbers from the second invocation, after §4's ruling (`out/p26/stage2/t6/table.py`, `table2.out`):

| course | player laps | extensions (clock expired) | opponents' wraps, cars 1-15 | jolts (bound) | lead field/dumps (bound) | player start point | string / warning frames | attribute turned % |
|---|---|---|---|---|---|---|---|---|
| Alpine | 1 → 1 | 6 → 5 (never) | 222211111111112 → 111111111111111 | 74 → 93 (121) | 10/5 → 8/7 (20) | 15 → 0 | 0/0 → 0/0 | 100 → 100 |
| Amazon Falls | 2 → 2 | 8 → 7 (never) | 111122222222222 → 111112222222222 | 14 → 23 (31) | 9/6 → 11/5 (20) | 0 → 0 | 0/0 → 0/0 | 100 → 100 |
| Diablo Canyon | 1 → 1 | 6 → 4 (never) | 011111111111111 → 011111111111111 | 95 → 118 (152.5) | 9/3 → 9/2 (20) | 0 → 0 | 0/0 → 0/0 | 100 → 100 |
| Metropolis | 1 → 1 | 5 → 5 (never) | 111111111122222 → 111111112222222 | 65 → 26 (107.5) | 7/5 → 7/6 (24) | 0 → 0 | 0/0 → 0/0 | 100 → 100 |
| Pacific Coast | 1 → 1 | 4 → 5 (never) | 111111111111222 → 111111111111112 | 91 → 95 (146.5) | 10/8 → 8/6 (24) | 0 → 0 | 0/0 → 0/0 | 100 → 100 |
| Surfers Oval | 2 → 2 | 6 → 6 (never) | 111111112222222 → 111111111222222 | 19 → 12 (38.5) | 9/7 → 8/7 (20) | 0 → 0 | 0/0 → 0/0 | 100 → 100 |
| Surfers Road | 1 → 1 | 5 → 4 (never) | 111111111111111 → 111111111111111 | 46 → 73 (79) | 8/7 → 7/6 (40) | 0 → 0 | 0/0 → 0/0 | 100 → 100 |

(normal → reverse; jolts bound 1.5 × normal + 10, stage 1's; string = frames the wrong-way string was read in the whole run;
warning = frames with any warning-tap read in the race window; attribute = the player's `+0xeb` equal to its quad's direction,
+ 0x8000 in reverse.)

- Reverse, all seven: no step back over the line, no wrap without the lap byte rising by one, none parked, largest backstep 0;
  checkpoints fire in order with the blob's extension or one less; no clock ran out (the recon's trial: Diablo 109 s,
  Surfers Road 108.8 s); render rate ≥ 27.
- Leader's gain (points): Alpine 821, Amazon 900, Diablo 723, Metropolis 849, Pacific 827, Oval 897, Road 768.
- Frames on point n − 1 per crossing (median, range), reverse: Alpine 16 (10-18), Amazon 12 (8-24), Diablo 12 (8-20),
  Metropolis 12 (8-16), Pacific 12 (8-18), Oval 10 (8-18), Road 10 (8-16); the Surfers figures are the recon trial's.
- Surfers Road's jolts are the nearest margin: 73 against 79, the recon trial's 73 / 79 too; one run each.
- Diablo's opponent 1 never wraps in either direction (14 of 15, the test's floor), as in the recon's normal run.
- The five courses whose credits did not change gave numbers identical to the first invocation's in every column.
- **Commands:** first, `.venv/bin/python -m pytest tests/test_reverse_build.py -s -v -p no:cacheprovider
  --basetemp=out/p26/stage2/t6/bt`: 3 failed (Surfers Oval crossings and field, Surfers Road field: §4), 55 passed; after the
  ruling, `.venv/bin/python -m pytest tests/test_convert_reverse.py tests/test_reverse_build.py -s -v -p no:cacheprovider
  --basetemp=out/p26/stage2/t6/bt2`: 67 passed in 1 203 s (`out/p26/stage2/t6/pytest2.log`; stage 1's and Task 5's MAME tests
  included). The flag-without-variant test moved from Diablo Canyon to Bay Bridge (entry 1): no converted course is without
  a variant now.

## 7. The start figures of the Acropolis template (Task 7)

**What the code does** (disassembly of the original boot ROM). The race-start task (data index 1: Metropolis, Diablo Canyon)
places pool objects 0-2 of `[0x501350]` at the player's position plus world-axis constants when the compare at 0xfc0bf2 is
equal (0xfc0bf2..0xfc0eb0, the stores through TGP command 0, then `jsr FF5B85`, state 0x27 with walk animations
0x38/0x39/0x3B). A figure is drawn (0xff5df4) at its position, then translated by its animation's root translation
(`+0x17b/+0x187/+0x193`), then turned (`+0x2c` at 0xff6c4f): the root offset is a world-axis offset applied before the
heading. When an animation ends (0xff6a14) the offset is added to the position, in world axes; state 0x27 then walks the figure
off along `+0x36` = 0x4000 (0xff6712). Only this block's three `mov.h #27, 1D1[R19]` reach state 0x27.

**The half turn was built and measured, and failed the gate** (plan D7's first way): a 178-byte routine at 0xfc0ea5 reflected
x, z through the player and added 0x8000 to `+0x2c`. Runs on Metropolis and Diablo Canyon, normal and reverse, the game's own
inputs, `figures_log.lua` from the load; each figure's drawn position (stored + root offset) in the car's frame at placement
(forward = (−sin, cos) of the yaw `+0x6a`). Gate: |dF| ≤ 0.5 and |dR| ≤ 0.5 between the directions until the end of the
animation (`out/p26/stage2/t7/measure.py`, `measure_rotation.txt`):

| course | figure | at placement (F, R), both directions | first frame over 0.5 | max \|dF\| | max \|dR\| |
|---|---|---|---|---|---|
| Metropolis | 0 | (3.98, 1.20) | 19 | 7.94 | 10.61 |
| Metropolis | 1 | (3.48, 1.00) | 19 | 7.67 | 12.14 |
| Metropolis | 2 | (0.54, −0.87) | 19 | 9.17 | 6.29 |
| Diablo Canyon | 0 | (2.96, 2.92) | 21 | 2.07 | 13.09 |
| Diablo Canyon | 1 | (2.61, 2.51) | 21 | 1.11 | 14.32 |
| Diablo Canyon | 2 | (0.88, −0.52) | 29 | 5.17 | 9.84 |

The placement turned exactly; then the figures drift up to 9-14 units in the car's frame (in normal, Metropolis's figure 0
goes towards the car and to one side, clearing the road; in reverse away from the car, to the other side). The gate read
"positions" as drawn positions: the stored position stays constant during the animation, so the stored-only reading (equal
at every frame before the end bit) could not show the root motion. Turning the root offset would mean changing the character
system the pit crew shares (0xff5df4, 0xff6a14), outside the plan.

**The fallback, committed** (decided by Pascal in advance): in a reverse race the three start figures are not placed. The
compare's 8 bytes at 0xfc0bf2 become `jsr figures` + 2 nops, the `bne FC0EEC` stays; `figures` returns not-equal while the
flag is set and otherwise makes the original's compare (format notes §13). `test_no_start_figures_in_reverse`: with the flag
0 objects 0-2 are placed as the three figures (frames 5-452 on Metropolis, 5-448 on Diablo), with the flag 1 never, and the
reverse start yaw is the normal one + 0x8000 within 0x400. Contact sheets of the final build
(`out/p26/stage2/figures/sheet_normal.png`, `sheet_reverse.png`, not committed): in reverse no figure in any frame, the road
ahead clear, the READY lights, the HUD and the field as before.

**Still Pascal's to choose at his drive:** he has been shown the rejected version's contact sheet
(`out/p26/stage2/figures/sheet_rotation_reverse.png`: at +40 frames the girls stand ahead of the car, from +120 they drift
ahead and to the right, still in view at +300) and may take the half turn after all. The routine is kept, not committed, in
`out/p26/stage2/t7/direction_rotation.py` and `test_direction_rotation.py`.

(Superseded after the owner's drive: Pascal chose the half turn, drift included, which replaced the fallback (§11.3.1); then
the figures' animation was mirrored too (§11.3.2, built).)

- **Command:** `.venv/bin/python -m pytest -s -v --basetemp=out/p26/stage2/t7/pt tests/test_direction.py tests/test_directory.py
  tests/test_mame_runner.py` plus the nine static tests, Task 5's three start tests and the two figures tests of
  `tests/test_reverse_build.py` by node id: 62 passed, 1 failed (`test_directory.py`'s list of allowed boot spans lacked the
  new site; added, that file 24 passed; `out/p26/stage2/t7/pytest.log`). The fourteen races of §6 were not re-run with the
  new site: the whole suite after this task runs them.

## 8. The normal direction against main, the annex's readers, the normal pins (Task 8)

**The set built without variants against one made by main's code** (the Task 5 ruling: with the flag 0, "keep their bytes" means content up to
relocation inside the code area). A git worktree of main 9458748 built main's ten-course set with main's code
(`ten_course_set(*build_all(...), reverse=False)`), and this branch's code built its own with `reverse=False`
(`out/p26/stage2/t8/dumpset.py`, run once with each tree on `sys.path`; compared by `out/p26/stage2/t8/cmpmain.py`, output
`cmpmain.out`). Each 32-bit word that differs is counted as a relocated address when both values lie in the code area
(`CODE_FREE`, 0x278d70..0x28fd70) and differ by the tables' move.

(Superseded figures: the +39 bytes, the 0x30 move and the boot site 0xfc0bf2 below are Task 7's 19-byte `figures`. After the
owner's drive `figures` and the figures' animation routines take more and patch other sites; the comparison was rerun for the
half turn (§11.3.1) and, the latest against main, for the mirrored figures (§11.3.2: +0x1b0, the boot differing only inside
the nine sites).)

- **The directory image** ends at 0x27a99e on main and 0x27a9c5 here (+39 bytes: `startbit` at 0x27a99e, `figures` at
  0x27a9b2, the two added routines; no routine moved). The tables stored after it (tile tables, race blobs, spawn lists and
  the blocks after them) start at the next 16-byte boundary, 0x27a9a0 on main and 0x27a9d0 here: a move of 0x30 bytes.
- **Polygon ROM, TGP data, TGP program:** byte-identical (16 777 216, 2 097 152 and 8 192 bytes).
- **Boot ROM:** 16 bytes differ, all inside the two new sites: 0xfe41d6 (9 bytes, `set1 #1E, 0[R0]` → `jsr startbit` +
  nops) and 0xfc0bf2 (8 bytes, `cmp.b #1, 501934[PC]` → `jsr figures` + nops). Nothing outside them.
- **Program ROM outside the code area:** 0 bytes differ.
- **Data banks:** 10 words differ, all in bank 0 at +0xde80c..+0xde844, each a pointer to a block in the code area after the
  spawn lists (0x289560..0x28e560 on main), each + 0x30. Nothing else differs in the four banks: the course tables, the
  collision and surface tables, the backdrops.
- **The directory image up to main's end:** 42 differing words, all relocated addresses: 21 in the load records of the
  converted entries (each one's `tile_table`, `spawn_table` and `race`), 21 as 32-bit operands at odd addresses in the ranking
  block's code (0x27a2dd..0x27a345: three per converted course).
- **The tables** compared at their relocated addresses (main 0x27a9a0..0x28fd40 against the branch's + 0x30): 1 883 words
  differ, every one a code-area address + 0x30 (the pointers the moved tables hold to their own records).
  Main's last 48 bytes of the code area are erased, so nothing was pushed out.
- **Per entry, decoded** (the ten entries): the three originals' records, tile tables and spawn lists equal; each converted
  entry's record equal but for `tile_table`, `spawn_table` and `race`, each + 0x30 (Alpine 0x27a9a0 → 0x27a9d0,
  0x286710 → 0x286740, 0x2835a0 → 0x2835d0; the others alike), its race blob decoded equal (12 time records, the
  checkpoints, the 16-car table), its 256-cell tile table and its spawn list equal in content.
- **Differences that are not a relocated address: none.**

**What that comparison covers, and what it does not.**
- Both sets were built without variants (`reverse=False`): neither holds the annex, the variants' tables in the data banks'
  free runs or the reverse table's non-zero words. The set that goes to the drive (`out/p26play2`, built with the variants)
  holds all three. The comparison shows that the set built without variants is main's up to relocated code-area addresses;
  on its own it says nothing about the variant set.
- It is a one-off measurement, not a committed test: it needs a build made by main's code beside this branch's, and ROM bytes
  may not be committed. Its scripts and output stay under `out/p26/stage2/t8/`.
- The step from the set without variants to the set with them is the committed `test_the_variant_only_adds_bytes`
  (`tests/test_reverse_build.py`, widened to all seven courses in Task 2). From one conversion it builds both sets with this
  branch's code (`ten_course_set(..., reverse=False)` against the tests' variant set) and asserts:
  - the boot ROM, the polygon ROM, the TGP data and the TGP program are identical;
  - in the data ROM, at least one byte differs, every differing byte lies inside one of the seven variants' blob spans (from
    its header to the end of its last stored line, in its entry's bank), and each is 0xff in the set without variants;
  - in the program ROM, every differing byte lies either in the reverse table's 40 bytes (all 0 in the set without variants)
    or inside the annex, from the first variant's load record to the end of the last race blob, where each is 0xff in the set
    without variants;
  - the set without variants has no reverse record.
  So the variants are written only onto erased bytes and onto the reverse table's words, and nothing of the normal build
  moves or is overwritten. With the one-off comparison: with the flag 0 the variant set's normal content is main's up to
  relocation, plus bytes written on ROM that was erased and on the reverse table's 40 bytes (which were 0, not erased).
  Whether a normal race reads the data banks' former free runs was not measured (below).
- **Open limits.**
  - Neither shows that no code reads the formerly erased bytes in a normal race. For the annex the tap test below does (the
    normal race on Surfers Oval: the colour upload alone). For the variants' tables in the data banks' former free runs no
    read tap was run: not measured.
  - The reverse table is read only on `entry`'s menu path after the flag test, so not with the flag 0 (read from
    `directory._entry`, not tapped).
  - `test_the_variant_only_adds_bytes` checks where the added bytes lie, not what they hold (the other set tests and the
    races check the variants' content).
  - `out/p26play2` is the command-line build of the same set; it was not compared byte for byte with the tests' set.

**Who reads the annex** (recon §1's pin, `test_only_the_colour_upload_and_the_served_variant_read_the_annex`): Surfers Oval
(entry 8, bank 1), 60 s each way with the game's own inputs, `memtrace.lua` read taps at exact addresses over the annex from
frame 0.

- **Normal race:** the annex 0x2b90c0..0x2bcb00 (14 912 bytes) is read only by the colour-table upload, PC 0xfe6b64:
  7 456 reads, one on each of its 7 456 halfwords, in frames 198-201. No other reader (the positive control: the taps see
  the whole span).
- **Reverse race:** the upload reads it the same way (7 456 reads, frames 198-201). Every other read falls in Surfers Oval's
  own variant: its load record 0x2b9200 (directory routines: `gfx` from frame 740 on the select screen, the loader, `bank`,
  `cars` and `pitstops` from the load at frame 1 603), its maps record 0x2b990c (`mapobj`, and 0xff853c..0xff854c every frame
  on its first 16 bytes, the HUD map outline's object list) and its race blob 0x2bbce0 (the loader; 0xfe4401 on a time record;
  0xfe8ac1..0xfe8e04 on the car table; 0xfea1f6..0xfea20d on the checkpoint record) — with one exception, before the load: on the
  select screen `direction.lua` holds the flag at 1, so `entry` serves the highlighted entry's variant and `gfx` (PC
  0x279a82) reads that variant's header word, bytes +4..+7 of its load record, as the wheel passes over it (Diablo Canyon's 240 reads in frames 618-737, Metropolis's 4 in
  738-739, Surfers Oval's own from 740). The brief's rule ("the other readers are inside that entry's own record and blob")
  holds from the load on; the test allows, before the load, `gfx` reads of bytes +4..+7 of a variant's load record and nothing else.
- **Commands:** `.venv/bin/python -m pytest -s -v -p no:cacheprovider --basetemp=out/p26/stage2/t8/bt-step1` with this test,
  `test_the_flag_leaves_acropolis_figures_alone`, `test_no_start_figures_in_reverse` and `tests/test_mame_runner.py`: 12
  passed, 1 failed (this test, in its first form, on the select-screen reads above; `step1.log`); this test again after the
  change, `--basetemp=out/p26/stage2/t8/bt-step1b`: 1 passed in 589 s (`step1b.log`); the narrowed test (the select-screen
  allowance cut to the header word, bytes +4..+7, and the loader's read asserted) with `tests/test_mame_runner.py`: 13 passed
  in 672 s (`out/p26/stage2/t8/fix1.log`).

**The Acropolis flag test is no longer vacuous** (the Task 7 review): `figures_log.lua` logs the direction byte on the select
screen's last frame (L line) and on every frame from the load (P lines). Measured: in the flag run the byte read 1 on the
select screen and on frames 0-3 after the load, 0 from frame 4 on (the loader's write-back); in the plain run 0 throughout;
the figures are placed from frame 5 in both. The test asserts the select-screen value (1 / 0) and 0 from the figures' first
frame on; `test_no_start_figures_in_reverse` passed again with the changed parser (the first invocation below).

**Normal-direction pins on the stage 2 set**, one invocation: `.venv/bin/python -m pytest tests/test_race_build.py
tests/test_tgp_build.py tests/test_tencourse.py tests/test_directory.py tests/test_direction.py -rA -p no:cacheprovider
--basetemp=out/p26/stage2/t8/bt-step2` (`out/p26/stage2/t8/step2.log`): **7 failed, 98 passed, 1 xpassed in 5 189 s
(1:26:29).** The seven failures are all names of the known list: `test_race_build.py::test_the_player_pitch_is_smooth_on_diablo`,
`::test_a_hard_steer_into_diablos_first_right_turn_meets_the_wall[at0]` and `[at1]`;
`test_tgp_build.py::test_saturn_collision_drives_big_forest`, `::test_alpine_drives_in_the_big_forest_slot`,
`::test_alpine_as_entry_three_drives`, `::test_each_new_course_drives_at_the_arcade_rate[2]`. The unexpected pass is the
Phase 22j `xfail` (`test_regenerated_big_forest_drives`), as on main. `tests/test_tencourse.py`, `tests/test_directory.py` and
`tests/test_direction.py` pass whole.

**Whole suite** (the known list: the 14 names of stage 1's plan and `test_alpine_as_entry_three_drives`; recorded in
`docs/follow-ups.md` too):
- On the stage 2 base (started on 124ffb8; log `out/p26/stage2/full.log`): 802 passed, 15 failed, 1 xpassed, counted from
  the progress marks (that log has no totals line). The 15 FAILED names are exactly the 15 of the known list.
- On the merged tree before the review's fixes (d93c0f2; log `out/p26/stage2/full2.log`): 867 passed, 16 failed, 1 xpassed
  in 3 h 11 min. The 16 FAILED names are the 15 of the known list and
  `tests/test_cli.py::test_build_writes_the_set_and_the_report`, which still expected eight stored lines for Metropolis's
  variant (six since §11.5); 669b760 corrects that test.
- On the final tree (75080f8; log `out/p26/stage2/full3.log`): 868 passed, 15 failed, 1 xpassed in 3 h 3 min. The 15 FAILED
  names are exactly the 15 of the known list.

**Playtest build:** `out/p26play2` (`.venv/bin/vrtools build --roms "$VR_ROMDIR" --saturn "$VR_SATURN_CUE" --out
out/p26play2`, `build-report.txt` beside it), launchers `out/rec153/launch.sh` (normal) and `out/rec154/launch.sh` (reverse:
`VR_DIRECTION=1 VR_DIRECTION_RAM=502294`, `direction.lua`), not committed. Its report's reverse lines give the annex addresses,
table sizes, lines stored and checkpoints of §2's table, and the normal tile tables, race blobs and spawn lists at main's
addresses + 0x30 (Alpine's tile table 0x27a9d0, race blob 0x2835d0, spawn list 0x286740; TGP budget 7 651 words left, as
stage 1's). A headless 30-s `run_mame` of `memtrace.lua` on the set boots to the attract: the mode byte 0x501139 reads 0x03
at frames 480, 1 000 and 1 600 (`out/p26/stage2/t8/bootcheck/`). The launchers were not run.

## 9. Open after stage 2

- **Not established in the ROM:**
  - the service-mode ROM test's code (string at 0xfc7ea9) and what it reports on any patched set (the annex lies in a run the
    original keeps erased);
  - taps on the annex in the test menu, in linked play and with an operator-fixed course.
- **Not measured, not compared (§8's open limits):**
  - no read tap on the data banks' former free runs (the variants' tables) in a normal race;
  - the playtest set `out/p26play2` was not compared byte for byte with the tests' set;
  - "the reverse table is not read with the flag 0" rests on reading the code (`directory._entry`), not on a tap.
- **Observed, not traced:** during the countdown the HUD shows 1ST on the Acropolis template in the normal direction and 16TH in
  reverse (16TH on Amazon Falls; 16TH everywhere once the cars move; recon §3; Task 7's reverse sheet shows 16TH/16).
- **For Pascal's drive** (judged by eye, not measured):
  - the three lines on the bank-1 courses: 7 cars on −5 and 8 on +5, how bunched the field looks (Amazon Falls, Pacific
    Coast, Surfers Oval, Surfers Road);
  - the start figures: none in reverse, or the half turn (§7; an open decision of Pascal's). Decided after the drive: the half
    turn, then the animation mirrored too (§11.3);
  - reverse Alpine's standing start (§5);
  - the gates seen from behind, and the backdrop's other half (the stage 1 recon's §7 item 6). Since Task 9 (§11.2) the gates'
    lettering reads correctly from behind. Still open:
    - the copies are lit as back-facing faces, so their red follows the banner's back lighting;
    - the banner's own back is unchanged (half grey, half white);
    - Metropolis's first C.P. was seen in reverse only at an angle;
  - tunnels at the grid rows (not established); the reverse grid rows on bends: Pacific's on a lane shift (−3.4 to −8.5
    units) on a 28° bend, Diablo's 29° bend at reverse points 10-14, Metropolis's last rows on the Phase 22n lane shift of a
    22° bend (recon §2, stage 1 §7); no fault showed in the races.
- **Measured once:** Surfers Road's reverse jolts 73 against the bound 79 (the recon's trial gave the same; 65 since the
  interleaved grid, §11.5); a second run would show whether that is typical. Diablo's opponent 1 never wraps in either
  direction.
- **After the owner's drive:** the KNOWN FAULT of turned cars on the reverse grids of Alpine, Diablo Canyon and Metropolis,
  the corner patch, the opponents' inside-bend cuts, Pacific Coast's first-bend cut and the link words (§11.5, "What stays
  open"); the gates' limits (above and §11.2); for stage 3, the flag cleared before the attract runs (the pit scene's figures,
  §11.3.2) and 179 bytes left under `tests/test_directory.py`'s bound of 5 000 (§11.3.2).
- **The two Surfers courses' spawn** reads point 0 on a quad credited n − 1 (§4): not explained, guarded by the race
  assertions only.
- **Stage 1's open items that stage 3 owns:** the flag is not cleared when a game starts (stage 3's screen writes it every
  game); a reverse race writes the course's ranking table (the launchers restore `start/nvram`); linked play's bank sites
  0xfe2b07 and 0xfe1d37 call `bank`, not `bankdemo`.
- **Stage 1's other open items still open:** the three read values of TGP 0x1500 (`+0xf1`, `+0xed`, `+0xf5`) as the forward
  quad gives them (Pascal drove with them on Metropolis); the put-back test's steer works at one spot (Metropolis).
- **Stage 1's open items closed by stage 2:** ROM room for six more variants (§2); the blob builders merged with a byte-identity
  check (§1); Alpine's PIT START (§5); the Acropolis template's start objects (§7); reverse start bands (none needed on any
  course, the floor stays 7 500).
- **Pit stops in reverse:** a stage of its own after the screen (recon §4 has the inventory).
- **Minor findings of the task reviews, deferred** (the session lead's ledger; not fixed in this stage):
  - `vrtools/arcade/blob.py`: `build_course_blob` repeats `_road_part`'s window-base check; `_road_part` couples the collision
    and the surface through `own = collision is None`, with no check that both are None or both set; a redundant
    `tuple(pairs)`; a local `import struct` in `_road_part` (and in `tests/test_blob.py`'s `_line_pointers`).
  - `vrtools/arcade/tencourse.py`: `max_colour_entry` iterates `decode_directory(rs)[3:]`, not `COURSES`; `convert_course`
    builds the normal blob (and runs `check_laps` on the normal checkpoints) when `reverse` is set without a race blob
    (unreachable today).
  - `vrtools/convert/race.py`: the parameter `lap_total` of `time_records_for` shadows the module function (the plan's name).
  - `vrtools/convert/reverse.py`: `reverse_segments`' return comprehension is dense.
  - `tests/test_cli.py`: line 36 scans twice; lines 37-43 do not check the report's "tables N bytes in bank B" figures.
    (Fixed in the final fix wave: one scan; each variant's "tables N bytes in bank B, K lines stored" checked against the
    size and the distinct line pointers read from the built bank.)
  - `tests/test_tencourse.py`: the bank-1 room assertion (line 346) lost its `, bank` message. (Restored in the final fix
    wave.)
  - `tests/test_convert_reverse.py`: no unit test of `_holds`' edge-distance branch (0.4 / 0.6 off an edge); the ring test no
    longer pins `rps[1] < N − 1`.
  - `tests/test_direction.py` and `tests/test_reverse_build.py` (Task 5): both flag-0 MAME comparisons run on patched boots,
    with no main-boot control run (§8's static comparison shows the boot equal outside the two sites); the static site test
    goes through `install_directory`, not `ten_course_set`.
  - `tests/test_reverse_build.py` (Task 6): line 162 calls `_before_line` with a two-element list standing for `pts[0]`,
    `pts[1]`; lines 199-201 leave "the rule applies → no n − 1 quad holds the spot" implicit through `kept == SPOT_KEPT`; the
    docstring at 173-176 says −3..+10, the bound is −3..+12.
  - `vrtools/mame/lua/figures_log.lua` (Task 7): the root offsets and headings are logged but no committed assertion reads
    them (they are what the measure of §7 used).
  - Fixed in Task 8: `test_the_flag_leaves_acropolis_figures_alone` now shows that the flag reached the byte (§8).

## 10. The verdict

- **One shared collision gives a sound reverse race on all seven converted courses under the autopilot** (§6): laps count at
  every crossing, the checkpoints fire in order with a reverse lap given the normal lap's time, the fifteen opponents race
  the reversed lap (none parked, none going back), the direction is turned on every sample, the wrong-way warning stays off.
  Jolts stay within stage 1's bound on all seven (Surfers Road nearest, 73 against 79).
- **No collision changed**: no start band, the TGP floor stays 7 500. The start spot needed a rule applied on two courses and
  withheld on two (§4).
- **Reverse Alpine starts on the grid** like the other six, facing the race; normal Alpine and Big Forest keep the crew start
  (§5).
- **The Acropolis template's start figures are left out in reverse** (§7); the half turn stays Pascal's choice at his drive.
  (After the drive: turned half a turn, placement and animation mirrored, §11.3.)
- **With the flag 0, the set built without variants is main's** up to relocated addresses in the code area (§8, a one-off
  comparison), and the variants only add bytes on erased ROM and the reverse table's words (`test_the_variant_only_adds_bytes`).
  Whether a normal race reads the data banks' former free runs was not measured.
- **Pascal drives next:** `out/rec154` (reverse) on each of the six new courses, `out/rec153` (normal) for spot checks. (Driven: §11.)

## 11. After the owner's drive

Pascal drove the reverse build (`out/p26play2`, `out/rec154`; replays under `out/p26/stage2/drive/`). Each piece of work
below was built on its own branch after the drive, reviewed, and merged: what Pascal reported (§11.1); the gates' lettering
(§11.2); the start figures (§11.3); the reverse checkpoints renumbered (§11.4); the start crashes (§11.5); the arcade start
gantry (§11.6). §11.7, the frame's record budget, comes from the final fix wave (`fix/`). Scripts, logs, runs and contact sheets, all git-ignored under `out/p26/stage2/`: `gates/` (§11.2), `t10/`
(§11.3.1, §11.4), `t13/` (§11.3.2), `surfers/` (the investigation of §11.5), `t12/` (its build), `arch/` (§11.6) and `integ/`
(the integration's builds and runs). The integrated tree's playtest set is `out/p26play3` (§11.6).

### 11.1 What the owner reported

| course (reverse) | what Pascal reported (their words in quotes) | answered in |
|---|---|---|
| Amazon Falls | the gates seen from behind read mirrored: "TRATS" on the START gate; on the C.P. gates a white banner with red marks and a grey banner with a red block | §11.2 |
| Metropolis, Diablo Canyon | the start figures: chose the half turn, drift included; then, on its contact sheets: "it bother me, they have to be arround the car" | §11.3 |
| Diablo Canyon | the Saturn's START gate, drawn, 36 points after the reverse start, fires nothing: a leftover? Chose that it fires in reverse too (reversed by Pascal on 13 Nov after stage 3's drive: stage 3 findings §12) | §11.4 |
| Surfers Road | "lot of opponent crashes between each other right at the start trying to overtake" | §11.5 |
| Metropolis | "quite a few oponent crashes by themselves" | §11.5 |
| Alpine, Diablo Canyon | an arch at the lap line whose banner showed nothing from behind: "a flag was there with nothing on it" | §11.6 |
| Pacific Coast | "was also able to go through a rock"; collisions with rocks give no large impact, "more like a road reset" | `docs/follow-ups.md` (not a reverse fault: the collision is shared) |


### 11.2 The gates' lettering from both sides (Task 9)

**From the drive.** On the reverse drive (Amazon Falls, `out/p26/stage2/drive/run3/`), the Saturn's gates seen from behind
read mirrored (§11.1). Pascal chose option C: the lettering must read correctly from both sides. The paths below are under
`out/p26/stage2/`.

**Recon (measured; `gates/recon_letters.txt`, `recon_mesh.txt`, `orig_cull.txt`, `recon_budget.txt`).**
- **The gates are the same two meshes on every course.** There are 20 drawn gates: 7 START gates and 13 C.P. gates (Pacific
  Coast draws one C.P.).
  - START gate (96 vertices, 34 faces): 14 lettering faces (7 red letter blocks and 7 white cut-outs), 6 banner faces (a centre
    panel and two wings, each stored twice, once per side), 8 rope faces (4 stored twice) and 6 post faces.
  - C.P. gate (68 vertices, 27 faces): 7 lettering faces (4 red, 3 white), 6 banner, 8 rope and 6 post faces.
- **The lettering is the Saturn's own faces.** Nothing in it is generated. The faces are stored once, all wound one way (the
  Saturn's normals point to the front, −z in the mesh), and they stand 0.008-0.045 Saturn units in front of the banner. Two
  faces of the wider START banner (Metropolis, Surfers Oval, Surfers Road) lie flush with it (−0.002..0.001).
- **No gate has a back panel of its own.** The Saturn draws the lettering from the front only, and the banner's back is the
  banner's second copy.
- **The grey back in Pascal's `cp2.png` is the banner's other copy, lit the other way.** From behind, the converted gate
  showed the front's letters through the banner. Where the banner's max-z sorted after them, part of the letters was hidden
  (the "red marks"); the painter's sort has no z-buffer.
- **The back-face test (§ "Back-face test" of `docs/formats/model1-polygon-rom.md`).** MAME skips a record with bit 14 clear
  when `view_determinant(old_p1, old_p0, p0) > 0`. The vertex order decides the side. The originals' culled ground faces up
  by its corners' right-hand normal (Big Forest: 9 177 of 9 793 horizontal culled records), and its stored normal points the
  other way (20 362 of 20 362). The Saturn's winding gives the opposite right-hand normal.
- **The headless experiment (`gates/exp_amazon_AB.png`, `exp_amazon_AB_zoom.png`).** On the build before the change, bit 14
  was cleared on the 14 records of Amazon Falls' START lettering (all in cell 118).
  - Variant A (no other change): the letters vanished from the front and still read "TRATS" from behind.
  - Variant B (their stored normals negated as well): seen from the same sides, the red drawn brighter.
  - So the vertex order decides the side, and the normal only lights the face.
- **Sorting.** A one-sided letter in front of its two-sided banner is drawn after it from its own side: it stands nearer by
  its depth and is smaller, as today from the front. The copy stands as far behind the banner, so the same holds from
  behind. The pictures show it on all 20 gates.
- **The record budget.** The cells holding lettering had 186-653 records against the 5 500 cap. The change adds 14 records
  per C.P. gate and 28 per START gate (the 653-record cell, Surfers Oval's cell 57, holds one stray copy: +2). The scenery
  objects grow by 15 120 bytes over the seven courses. `poly_budget` falls by 15 152 bytes (718 108 → 702 956; the floor is
  65 536): 15 152 = 15 120 + 48 (bytes left in gaps under 64, which `poly_budget` does not count; first fit packs the later
  objects differently) − 16 (0xFF bytes in the new objects' data, which the scan counts as erased, net of run starts rounded
  up to 4 bytes; with every erased run counted the drop is 15 104).

  No cell is capped, before or after.

**What was built.**
- **`gates.gate_lettering(mesh)`** finds the lettering faces and the copy of each:
  - the banner is the faces stored twice that stand upright and at least 0.15 tall;
  - the lettering is the faces stored once, upright, inside the banner's span, within 0.06 of it and all wound one way;
  - each copy is mirrored left to right about the banner's centre (x → 2c − x), with each corner as far behind the banner's
    polyline as the face stands in front of it. A flat banner would make this the face turned half round a vertical axis
    on the banner. On the bent banner, a copy whose span crosses a bend follows each panel; 1-2 copies per gate do.
- **`gates.lettered_quads(sat)`** gives the props as `course_quads` does, with the lettering marked one-sided and the copies
  appended after their prop's faces. `convert_tiles` uses it for group 4 only (`lettering=False` restores the old scenery).
  `assign_colours` writes a one-sided face with its corners reversed under the lighting normal it had, so it is drawn from
  the Saturn's side, lit as before. The copy keeps the letter's corner order, which makes it face and light the other way.
- **`polyrom.Quad.one_sided`**: `encode_object` clears bit 14 on that quad's drawing record only. A one-sided quad is a chain
  of its own, its corners rotated so that the test's three corners are distinct. An object without one encodes to the same
  bytes (digests pinned in `test_an_object_without_one_sided_quads_encodes_as_before`).

**The proofs (`gates/proof.txt`, builds `gates/before/` and `gates/after/`, made by `gates/build_digest.py`).**
- **Collision unchanged.** Measured once: the ten-course set's TGP data ROM is byte-identical before and after (sha256
  540af4b5…), and on each of the seven courses the `Collision` handed to `install_collision` and its cell offsets digest the
  same.
  - **The committed guards:** `test_the_collisions_code_never_takes_the_lettering_copies` (source level: `collision.py`,
    `profile.py` and `place.py` name neither `lettered_quads` nor `convert_tiles`; kept because the collision is the owner's
    most protected area). `test_the_collisions_props_never_hold_the_copies` (synthetic gate) checks that the props
    `collision.py` reads (`course_quads(sat, groups=(4,))`) keep their length and hold no one-sided quad.
    `test_only_the_gates_cells_change_and_convert_tiles_leaves_the_course_alone` (the seven courses) checks that
    `convert_tiles` leaves `sat` and `course_quads(sat)` unchanged.
  - **A gate whose lettering is not recognised** stops the conversion with a `ConvertError` naming the placement. All 30 gate
    placements of the ten Saturn courses are recognised.
- **Scenery.** Of 478 cells compared, 21 changed. They are exactly the cells that hold gate lettering:
  - Alpine 146, 150, 202;
  - Amazon Falls 74, 118, 170;
  - Diablo Canyon 70, 74, 150;
  - Metropolis 101, 136, 217;
  - Pacific Coast 52, 122;
  - Surfers Oval 41, 57, 118, 123;
  - Surfers Road 41, 118, 123.
  None of the other 457 cells changed. The colour entries are identical (each copy takes its letter's colour), `capped_cells`
  is 0 → 0 on every course, and the later objects only move in polygon ROM.

**The pictures (`gates/sheet_after_<k>_<course>.png`: every drawn gate approached at 60, 40 and 25 units, normal then
reverse; `gates/sheet_amazon_before_after.png`: Amazon Falls before and after, both ways).**
- **In reverse, every gate reads correctly: "START" and "C.P.".** On five courses the reverse driver sees the gates from
  behind, through the copies; on Alpine and Pacific Coast the lettered front faces the reverse driver (below), who sees the
  letters' own front. That covers all 7 START gates (on the wider
  Metropolis/Surfers banners too) and 12 of the 13 C.P. gates seen head-on. Metropolis's first C.P. (200, 713) stands just
  past a bend in reverse, and the autopilot sees it only obliquely, at the screen's left under the rev gauge
  (`gates/metropolis_cp2_reverse_zoom.png`). There the C, the dot and the P stand in reading order with the P's and the C's
  cut-outs on the correct sides. It is the same mesh as Metropolis's second C.P., which reads head-on.
- **In the normal direction, Amazon Falls looks as before.** Its three gates' before and after snapshots of the same frames
  differ by 2-79 pixels each, all one-pixel rows along the letters' edges (`gates/diff_normal_0010.png`): the reversed corner
  order rasterises the edges a pixel differently.
  - The other six courses have no before run. On Diablo Canyon, Metropolis, Surfers Oval and Surfers Road the normal driver
    faces the letters' front, as on Amazon Falls; there the claim rests on the scenery proof (only the lettering cells
    changed, the lettering drawn from the front by the same faces under the same normals) and on the after pictures, where
    every gate reads correctly.
- **In the normal direction, Alpine and Pacific Coast changed: their gates' lettering read mirrored before and reads
  correctly now** (found by the final review; not stated before this correction). On those two courses every Saturn gate's
  lettered front faces the reverse driver (stage 1 recon §4: Alpine's gates at road points 65, 192, 333, Pacific Coast's at
  186, 320). Before the change the normal driver saw the two-sided letters from behind, mirrored; now the letters are
  one-sided and the normal driver sees their mirrored one-sided copies, which read correctly. This follows from Pascal's
  option C (both sides readable) and is a visible normal-direction change; the scenery proof (the same 21 cells) covers its
  extent. Measured twice from the conversion, each gate's lettered side against the lap's direction at its nearest
  centreline point: by the final review (the faces' local −z side through the placement: dot +0.98..+1.0 on these two
  courses, −0.99..−1.0 on the other five; its figures, not re-run here) and, independently, by the fix wave's `out/p26/stage2/fix/scripts/fix_gate_side.py`
  (the world centroid of the lettering against that of its copies; `fix/gate_side.txt`): the same sign on all 20 gates, the
  lettered side facing the reverse driver on exactly Alpine's 65, 192, 333 and Pacific Coast's 186, 320. Its magnitudes
  (0.04-0.97) are smaller because the centroids also differ along the banner; only the sign is read. No before/after
  snapshot of these two courses in the normal direction was taken: the after pictures (`gates/sheet_after_<k>_<course>.png`)
  show the gates reading correctly; that they read mirrored before is inferred from the facing and the drawn sides (§ "The
  headless experiment" above), not photographed.

**Limits.**
- **The copies' lighting.** They are lit as back-facing faces: their stored normal is the letter's turned half round. From
  behind, the letters' red follows the banner's back lighting, not the front's.
- **The banner's own back is unchanged.** From behind it still shows half grey and half white, as before; the expected cause,
  not measured: its two stored copies sort by their max-z.
- **Metropolis's first C.P.** was seen in reverse only at an angle (above). It was not seen head-on.

### 11.3 The start figures

**Built: the placement turned half a turn round the player (`figures`, §11.3.1) and the figures' animation mirrored (the
seven `FIGURE_SITES`, §11.3.2).** The history, short: Task 7 left the figures out in reverse (§7); after the drive Pascal chose
the half turn of the placement alone, drift included (§11.3.1); on its contact sheets they rejected the unturned animation,
and Task 13 mirrored it too (§11.3.2), which replaced the half turn's drift bound with plan D7's gate.

#### 11.3.1 The placement turned half a turn (Task 10; the placement is built, its unturned animation superseded)

**From the drive.** Shown the contact sheets of both versions (none in reverse, and the half turn drifting off the normal
places), Pascal chose the half turn, drift included. It replaced §7's fallback.

**What was changed.**
- `direction.py`: `figures` is §7's half turn (plan D7's first way), Task 7's kept routine re-derived against the current
  tree (the code is the same; the surrounding constants and the docstring moved on). The site is the placement's end,
  0xfc0ea5..0xfc0eb3 (`clr1 #1E, 0[R19]; pop R19; br FC0EEC`, 14 bytes), not the compare at 0xfc0bf2, which is the
  original's again. With the flag set the routine reflects pool objects 0-2 through the player and adds 0x8000 to `+0x2c`;
  with the flag 0 it re-emits the two instructions and jumps to 0xfc0eec, and it differs from the original only in the
  condition flags there, which nothing reads (0xfc0eec `push R25; mov.w ...; jsr FE88A7`, whose `and.w` sets them before
  its `be`). The animation's root offset and the walk-off heading (`+0x36` = 0x4000) are not turned in this version, as in
  the version shown to Pascal (§11.3.2 mirrors them). The Big Forest and Bay Bridge templates do not reach the block (data index 1 only).
- Room: the routine is 178 bytes against the fallback's 19; the direction routines take 230 bytes, `end − loader` = 4 588,
  **412 bytes left** under `tests/test_directory.py`'s 5 000 at this step (179 since §11.3.2). The image ends at 0x27aa64
  (main 0x27a99e, +198 bytes), so the code-area tables move 0xd0 bytes from main's places (0x30 before).
- Tests: `tests/test_direction.py`'s three figures tests are Task 7's half-turn ones (the span, the routine's listing, a
  changed branch refused); `tests/test_directory.py`'s allowed boot span is (0xfc0ea5, 14) in place of (0xfc0bf2, 8);
  `tests/test_reverse_build.py::test_no_start_figures_in_reverse` is replaced by
  `test_the_start_figures_turn_half_a_turn_in_reverse` (itself replaced in §11.3.2).

**Measured** (the set built from a fresh conversion with this tree, `t10/built.pkl`; runs of the game's own inputs, no
autopilot, `figures_log.lua` from the load; `t10/measure.txt`):
- On both courses the three figures are placed at load + 5 in both directions (live frames 5-452 normal, 5-456 reverse on
  Metropolis; 5-448 and 5-454 on Diablo Canyon). At frame 5 the player stands on the same spot both ways (Metropolis
  (−319.74, −190.80), yaw −8 / 32760; Diablo Canyon (−411.45, −180.85), yaw 5060 / −27708). Each reverse figure stands at
  its normal place reflected through the player to the log's 4 decimals (offset 0.0000 on all six), its heading the normal
  one + 0x8000 (figures 0 and 1: 0 → 0x8000; figure 2: 0x8000 → 0), its root offset 0 there.
- Drift: the drawn position (stored + root offset) in the car's frame at placement, reverse minus normal, per axis.

| course | figure | before the animation's end: \|dF\|, \|dR\| at the largest (as §7) | every frame both live: max \|dF\|, max \|dR\| |
|---|---|---|---|
| Metropolis | 0 | 7.94, 10.61 | 8.00, 24.28 |
| Metropolis | 1 | 7.67, 12.14 | 7.68, 21.63 |
| Metropolis | 2 | 9.17, 6.29 | 9.20, 21.30 |
| Diablo Canyon | 0 | 2.07, 13.09 | 3.94, 24.59 |
| Diablo Canyon | 1 | 1.11, 14.32 | 2.99, 22.10 |
| Diablo Canyon | 2 | 5.17, 9.84 | 5.53, 22.52 |

  The first column repeats §7's figures exactly. After the animation's end both directions walk the figures along the
  same world axis, so in the two car frames they part further; every \|dR\| maximum falls on the last frames the normal
  figure is live (451 on Metropolis, 447 on Diablo Canyon). The last column is what the test prints and bounds.
  The test's bound `FIGURE_DRIFT_MAX` = 26.0 units per axis was this measurement's 24.59 plus about 6 %: the runs are
  deterministic, so it was a regression bound on the drift Pascal accepted, not a quality claim. It went with §11.3.2, which
  replaced it with plan D7's gate.
- **The set built without variants against main's** (Task 8's `dumpset.py` / `cmpmain.py` rerun on `t10/built.pkl` against
  Task 8's `main.pkl`, `t10/cmpmain.out`): the boot differs in 21 bytes, all inside the two sites (0xfe41d6, 9) and
  (0xfc0ea5, 14); polygon ROM, TGP data and program identical; the program ROM outside the code area identical; 10 data-bank
  words and every differing code-area word a relocated address (+0xd0); main's last 208 code-area bytes are erased, so
  nothing is pushed out; the ten entries' records equal up to relocation, their race blobs, tile tables and spawn lists
  equal. Differences that are not a relocated address: 0.
- **Contact sheets** (`t10/sheet_metropolis.png`, `t10/sheet_diablo_canyon.png`: normal on the top two rows, reverse under
  them, at +40 ... +440 frames after the race start):
  - Metropolis reverse: at +40 two girls stand just ahead of the car (one by the nose, one to the right with the parasol),
    as in the normal start; from +120 they drift ahead and to the right; at the green (+262/+275) they stand ahead right
    by the road's edge, and the car passes them by +340. Normal: they walk to the left foreground and leave by +340.
  - Diablo Canyon reverse: alike, the two girls ahead at +40, drifting right; at +275/+300 one stands ahead right as the
    car moves off; none in view from +340.
  - Both: the READY lights, the HUD (16TH/16 in reverse, §9), the field ahead as before. No figure stands in the car's path
    in any frame. (Reverse Diablo at +440 is on the verge: these runs hold the wheel centred, no autopilot.)
- **Command** (one session, a fresh conversion): `.venv/bin/python -m pytest -s -v -p no:cacheprovider
  --basetemp=out/p26/stage2/t10/pta tests/test_direction.py tests/test_directory.py tests/test_mame_runner.py` plus, from
  `tests/test_reverse_build.py` by node id, the nine static set tests, Task 5's three start tests,
  `test_the_start_figures_turn_half_a_turn_in_reverse` and `test_the_flag_leaves_acropolis_figures_alone`: **63 passed in
  1 050 s**, no warnings (`t10/pta.log`). The flag test still sees the byte at 1 on the select screen and on frames 0-3, the
  figures placed from frame 5 and the two streams equal.

#### 11.3.2 The animation mirrored too (Task 13; built)

**From the drive.** On §11.3.1's contact sheets (the girls drifting ahead and to the right and walking off the other way)
Pascal rejected the unturned animation (§11.1). In reverse, seen from the car, the figures must stand and move as in the
normal direction.

**Recon** (original boot ROM, disassembly in `out/p26/stage2/t13/boot.lst`; runs with `t13figs.lua`, `t13/recon_summary.txt`):
- A figure is drawn T(position) T(root) [0xff6bf3: T(record offset) R_b0(+0xd1) R_a8(+0xd7) R_a0(+0xdd) R_a8(+0x2c), then the
  limbs] (0xff5df4..0xff5e25). TGP 0xa8 is the vertical axis (the heading's). The root translation and the body's three root
  rotations are applied outside the heading, so they act in world axes. The limbs come after the heading, in the figure's own
  frame, and need nothing.
- **The root offset** (+0x17b x, +0x187 y, +0x193 z) comes from the animation's keyframe table: animation `[19B]` → `0[R4]`,
  each key x, y, z floats then one byte per joint. 0xff67e6 sets it from the first key. Every fourth frame (0xff68da, and
  0xff6a5d on an animation change) the step (key − current) / 4 is computed by TGP commands into +0x177 / +0x183 / +0x18f,
  and 0xff6b20 adds the steps each frame. The draw pushes it at 0xff5e13 / 0xff5e19 / 0xff5e1f. When an animation ends,
  0xff6a14 adds x and z to the position and clears them. World axes, keyed per animation, the same for both directions.
- **The body's root rotations** are the first three joints of the joint array +0xcd (per joint: counter, step, value; keyed
  from the same table's bytes, 0xff6976, stepped at 0xff6b4a). Measured on the normal runs: +0xd1 −1280..768, +0xd7 up to
  ±30 208, +0xdd −1024..768 on figures 0 and 1 and 0..13 312 (73°) on figure 2.
- **The record offset** (the record's first word → x, y, z) is (0, 0, 0) for the three figures.
- **The walk-off heading**: state 0x27 (0xff6705, reached only by the placement block's figures, Task 7's sweep) stores
  `+0x36` = 0x4000 at 0xff6712, and 0xff6b70 moves the figure by speed × (sin, cos) of −`+0x36` in world axes. Nothing else
  writes their `+0x36` or `+0x2c` (the turn +0x1e8 is 0 throughout).
- **What a half turn about the vertical axis needs**: R_y(π) T(r) = T(−rx, ry, −rz) R_y(π); R_y(π) R_x(a) = R_x(−a) R_y(π),
  the same for z. So: the root offset's x and z negated, +0xd1 and +0xdd negated, +0xd7 kept, `+0x36` + 0x8000, the
  record offset negated (it is 0), the heading + 0x8000 (§11.3.1). The limb joints need nothing.
- **Where it can be reached**: the animation code is the character system the pit crew shares (0xff5df4, 0xff6bf3 also from
  0xff5e78, 0xff72bb, 0xff730d). Changing the stored keys would touch the shared data, so the uses are mirrored instead, behind
  a test of the flag and of the object's character record. The figures' cell `+0x34` (0xff7b6d: a world-aligned 16 × 16 grid
  of 128-unit cells) and its visibility cull are not part of the drawn pose.

**What was built** (`direction.py`; directory image +233 bytes).
- `figmirror` (54 bytes): Z when the flag is set and `1AB[R25]` is one of the three figures' records.
- Seven boot sites (`FIGURE_SITES`), each its original instruction (pattern checked) → `jsr <routine>` + nops:
  - 0xff5e13 and 0xff6a18, `mov.w 17B[R25], [R24]` → `figrootx` (35 bytes);
  - 0xff5e1f and 0xff6a2c, `mov.w 193[R25], [R24]` → `figrootz` (35);
  - 0xff6c25, `movs.hw D1[R25], [R24]` → `figrot0` (43);
  - 0xff6c41, `movs.hw DD[R25], [R24]` → `figrot2` (43);
  - 0xff6712, `mov.h #4000, 36[R25]` → `figwalk` (23).
- Each root or rotation routine calls `figmirror`. If it does not hold, the routine runs the original's own bytes and
  returns. Else it pushes the field negated to the TGP, R0 kept: a float by adding 0x80000000, a halfword angle by `movz`,
  `shl #16`, `sha #−16`, `mul #−1`. `figwalk` stores the original's 0x4000, then 0xc000 if `figmirror` holds. The stored
  animation is never changed, only its uses.
- The flag-0 path, and any object that is not a figure: the original instruction's bytes, re-emitted. Flags differ only
  where the code after each site sets them again before reading them: 0xff5e19 and 0xff5e25 → 0xff6bf3 → 0xff8583
  (`add.w`), 0xff6a1e.. → 0xff6a51 `test1`, 0xff6c2b.. → 0xff6c54 `cmp.b`, 0xff6719.. → `inc.h` before the handler's `rsr`.
- No branch of the boot lands inside a site, and no 32-bit word in the boot or program ROMs points inside one (sweep, with
  0xff6a4d and 0xff6bf3 as positive controls).
- **The records `figmirror` tests are shared with the attract mode.** In the original program and boot ROMs the three record
  values occur only at the placement's stores (0xfc0c61, 0xfc0d59, 0xfc0e2c) and at two in the attract mode's pit scene
  (0xfc0186 and 0xfc0230: 0xfd743b and 0xfd747f, two of the three figures' records). Those attract figures stay unmirrored
  only because the flag is cleared before the attract runs (`bankdemo`); stage 3's direction screen must keep that order.
  `tests/test_direction.py::test_the_figure_records_are_referenced_only_at_the_placement_and_the_attract_pit_scene` pins the
  five references.
- Room: the direction routines take 463 bytes; `end − loader` = 4 821, **179 bytes left** under `tests/test_directory.py`'s
  5 000. The image ends at 0x27ab4d (main 0x27a99e, +431), so the code-area tables move 0x1b0 from main's places. The code
  area's erased tail had 5 280 bytes.
- Tests: `tests/test_direction.py` four new (the sites' patterns and `jsr`, `figmirror`'s listing, the routines' listings, a
  changed site refused); `tests/test_directory.py`'s allowed boot spans add the seven sites;
  `tests/test_reverse_build.py::test_the_start_figures_are_mirrored_in_reverse` replaces
  `test_the_start_figures_turn_half_a_turn_in_reverse` (D7's gate, below). `test_the_flag_leaves_acropolis_figures_alone`
  is unchanged.

**Measured** (a fresh conversion with this tree, `t13/built.pkl`; runs of the game's own inputs; `t13/gate.txt`,
`t13/cells.txt`).
- **Plan D7's gate**: the drawn position (stored + root as pushed: + root normal, − root reverse) in the car's frame at
  placement, reverse against normal, on every frame both runs show the figure live. Max |dF| and |dR| are **0.000** for
  all three figures on both courses: Metropolis frames 5-452, Diablo Canyon 5-448, exact to the log's 4 decimals. The test's
  gate is 0.5 per axis. It is a gate in the plane (x and z, read as forward and right): height (y) is neither gated nor
  measured, as a figure follows the ground at its mirrored spot.
- **What the gate measures and what it infers.** It measures the stored position and the stored root offset with the
  modelled sign (+ in normal, − in reverse, as `figrootx` / `figrootz` push it). It infers the draw sites and the body
  rotations: those are checked only by the static listing tests and by the contact sheets.
- The stored joints (+0xd1, +0xd7, +0xdd) are equal frame by frame in the two directions; the walk heading is 0x4000 in
  normal and 0xc000 in reverse. Placement as §11.3.1: the normal place reflected through the player (offset 0.0000), the
  heading + 0x8000.
- **Live spans**: the first live frame is load + 5 in both directions. The last differs: Metropolis 452 normal / 456 reverse
  (+4), Diablo Canyon 448 / 454 (+6). Not the figures' code:
  - each figure's cell stays the start's (101 on Metropolis, 100 on Diablo Canyon, the same in both directions, never updated);
  - 0xff5cef ends it two frames after that cell's bit in the visible-cell set 0x501ac0 clears;
  - the bit clears later in reverse, as the car drives off along the other road (Metropolis normal frame 451, reverse 455;
    Diablo 447 / 453).
  
  On every earlier live frame the cell is visible in both directions, so the figures are drawn throughout. From race start
  + 340 no figure is in view in either direction (the sheets), over 100 frames before the end. The test's
  `FIGURE_SPAN_SLACK` = 6 frames is this measurement: more than "a frame or two", for the reason above.
- **The frame's record budget with the figures** (measured in the final fix wave on the merged set `out/p26play3`, §11.6
  "On the merged set"; the budget §11.7). In reverse the frame's record count peaks at **4 921 on Metropolis** and **5 151 on
  Diablo Canyon** while the figures are live, against 3 891 and 4 121 at the same frames on the gantry line's after build,
  which draws no reverse figures: the three figures cost +1 030 records. Both peaks are under the 5 500 at which later
  object lists are skipped (349 to spare on Diablo Canyon), so nothing is skipped at the start. The character path with a
  budget − 150 check (0xff5e33, §11.7) is taken only by objects with flag bit 0x1a; the figures' flag words (0x10000000,
  0x90000000, 0xd0000000 in these runs) do not have it, and no budget test was found on the path they take
  (0xff5d93..0xff5e30): nothing found limits the figures' own draw by the count. Live spans in these runs:
  load + 5 to + 456 on Metropolis, + 5 to + 410 on Diablo Canyon (its autopilot line is `arch/after/conv.pickle`'s, not the
  test's, which may explain the shorter span than the 454 above; not checked).
- **The set built without variants against main's** (`t13/cmpmain.out`): the boot differs in 64 bytes, all inside the nine
  sites. Polygon ROM, TGP data and program are identical. The program ROM outside the code area is identical. The data banks
  differ in 10 words and the tables in 1 883 words, all relocated addresses (+0x1b0); main's last 432 code-area bytes are
  erased. The ten entries' records are equal up to relocation, and their race blobs, tile tables and spawn lists are equal.
  Differences that are not a relocated address: 0.
- **Contact sheets** (`t13/sheet_metropolis.png`, `t13/sheet_diablo_canyon.png`: normal rows on top, reverse under them, at
  race start + 40 ... + 440). On both courses the reverse frames show the girls where the normal frames show them, with the
  same poses: two ahead of the car at +40 and +120; one walking to the left foreground at +200 and +240; the group on the
  left verge at the green; the parasol girl passing the car on the left at +300 (Diablo) or leaving at the left (Metropolis);
  none from +340. Only the scenery behind them differs. They stand and walk around the car as in the normal direction, in the
  plane (height is not gated, above).
- **Command** (one session, a fresh conversion): `.venv/bin/python -m pytest -s -v -rA -p no:cacheprovider
  --basetemp=out/p26/stage2/t13/pt tests/test_direction.py tests/test_directory.py tests/test_mame_runner.py
  tests/test_reverse_build.py -k "not test_reverse_build or figures or 5 or 6"` (the two figures tests and the twelve reverse
  race tests of Diablo Canyon and Metropolis): **67 passed, 48 deselected in 1 169 s**, no warnings (`t13/pt.log`). The race
  tests give §11.4's figures again for Diablo Canyon and §6's for Metropolis; the Acropolis flag test as before.

### 11.4 The reverse checkpoints renumbered: Diablo Canyon's START gate fires (replaces §3's reverse checkpoints)

**Superseded after stage 3's drive** (Pascal, 13 Nov): the START arch is no reverse checkpoint again, Diablo Canyon's reverse
checkpoints (0, 168, 278) with the normal lap's total spread over three sectors; `docs/spike/2026-11-phase26-stage3-findings.md` §12.

**From the drive.** Driving reverse Diablo Canyon, Pascal passed through the Saturn's START gate (forward point 421 of 457, a
checkpoint in the normal direction), drawn but firing nothing 36 points after the reverse start, asked whether it was a
leftover, and chose that it fires in reverse too (§11.1).

**What was changed.** The reverse lap's checkpoints are exactly the normal lap's renumbered for the reversed lap,
(n − g) mod n sorted (`reverse.reverse_checkpoints`, replacing `gate_checkpoints(reverse_gates(...))`, which applied the
normal start rule, a gate within 50 points after the line dropped, to the mirrored gates). Every gate that fires one way fires
the other, nothing else does. The normal blobs, tables and spawn lists do not change (the normal checkpoints are the rule's
input); the drawn gates do not change. The lap-total rule (D4) stays: with the same sectors in reverse order its factor is 1.

**Measured.**
- Checkpoints (one conversion, `t10/blobs_before.txt`, `blobs_after.txt`): Diablo Canyon (0, 168, 278) → **(0, 36, 168, 278)**;
  the six others unchanged by the rule: Alpine (0, 119, 260, 387), Amazon Falls (0, 93, 213), Metropolis (0, 143, 239),
  Pacific Coast (0, 90, 224), Surfers Oval (0, 88, 260), Surfers Road (0, 142, 314); their variant blobs are the same as
  before.
- Diablo Canyon's reverse time records, level 0 (initial 2080 both):

| | variant 0 | variant 1 | first-lap sum (v0) |
|---|---|---|---|
| normal (0, 179, 289, 421) | 415, 255, 306, 200 | 398, 245, 294, 200 | 1176 |
| reverse before (0, 168, 278) | 432, 283, 460 (scaled) | 418, 274, 445 | 1175 |
| reverse after (0, 36, 168, 278) | 200, 306, 255, 415 (unscaled) | 200, 294, 245, 398 | 1176 |

  The reverse first-lap sums now equal the normal ones on all 12 records (1176 1176 1199 1199 1137 1143 1173 1179 1148 1148
  1171 1171); on every course the variant's record is the one `race_blob_for` gives without `lap_totals`; `check_laps`
  (5 laps) passes on every course with its reverse checkpoints (Diablo: 4 per lap, at most 5 laps).
- Diablo Canyon's reverse race (150 s, autopilot; `tests/test_reverse_build.py`, `t10/ptb.log`, `t10/firstfire.txt`): the
  green (the clock's first count) at frame 1866 with the player on point 0; the checkpoint 36 points after the line fires
  for the player at frame 2278 on road point 36, 412 frames after the green, adding 199 (the record's 200 less one, stage 1's
  form). Before the green the clock rose once only, when the load set it (0 → 2080 at frame 1602): nothing fired before the
  green. Fires in the race window: (36, +199), (169, +305), (279, +254), (0, +414), (36, +199), (169, +305): the record's
  200, 306, 255, 415 each less one, in order. The clock never ran out (`race_report`'s dump-sampled count, every 250 frames,
  gives 5 extensions: the fires at 6864 and 7100 fall between the same two dumps).
- The field: every car counts a lap at each crossing (no step back, no wrap without the lap byte rising; wraps 1 for the
  player and 14 of 15 opponents, car 1 none, as in the normal run and in §6); frames on point 456 per crossing 8-20; 15
  moved, none parked, largest backstep 0, cursor lead 2 (field) / 9 (crossings), leader 723 points; jolts 118 against the
  normal run's 95 (bound 152.5), the direction turned on 54 193 of 54 193 samples, no wrong-way read. These match §6's
  Diablo row except the extensions; the game showed no fault with a checkpoint that near the start.
- **Command** (one session, a fresh conversion, both parts): `.venv/bin/python -m pytest -s -v -rA -p no:cacheprovider
  --basetemp=out/p26/stage2/t10/ptb tests/test_convert_reverse.py tests/test_convert_race.py tests/test_direction.py
  tests/test_directory.py tests/test_mame_runner.py tests/test_reverse_build.py`: **127 passed in 1 727 s**, no warnings
  (`t10/ptb.log`).

### 11.5 The start crashes: the bank-1 grid interleaved, Metropolis's pairs, the known fault on Alpine, Diablo Canyon and Metropolis

**From the drive.** Opponents crashing into each other at the start of reverse Surfers Road, and by themselves on reverse
Metropolis (Pascal's words in §11.1). Who decided the two remedies below:
- **Metropolis's reverse lines:** Pascal approved them ("Ok" to the recommendation).
- **The interleaved grid on the four bank-1 variants:** the session lead's decision, not Pascal's. Reason: it removes the
  reported start crashes at their measured trigger without touching the collision, the normal bytes or bank room. Cost: the
  reverse grid order on those four courses differs from normal (car 5 first, car 12 last). Revert: one table
  (`tencourse.BANK_ONE_GRID`). Reported to Pascal with its results; awaiting their confirmation.

**The investigation** (`out/p26/stage2/surfers/report.md`, branch at 87abc80; autopilot races of 150 s that reproduce the owner's
drives: the same cars, road points and x/z). Every event is an opponent's smoke counter rising (the race log's J line): the
off-tarmac jolt (0xfeb058, the car's centre on grass or run-off) or a car-to-car bump (0xfebbfd); no wall hit, no crash animation.
- **Root cause of the start crashes** (measured). On the standing grid the game's "car directly behind" avoidance (contact B,
  0xfeca95: the ranking neighbour behind within 10 units, |R15| ≤ 6) blends the follower's target towards corner c0 or c1 of
  the quad its line point's link word names, and at standstill the steer (`yaw += (angle − yaw) / R21`, R21 = 1 at 0xfece3d)
  turns the car at once. In reverse the grid is single file (player on point 0, car k on point k) and with
  `BANK_ONE_PAIRS` seven or eight cars share a stored line, 10 units nose to tail. Those corners are authored for the forward
  direction: in reverse they lie behind or beside the car (on 431 of 441 reverse points of Surfers Road against 43 forward), at
  reverse points 2, 4-7, 10 and 14 on pit-lane quads 29-57 units right of the centreline, beyond the pit wall. Surfers Road:
  cars 2, 3, 6, 7, 10 and 14 stood turned 52-68 degrees; at the green 6, 7 and 10 swerved across and recovered, 2, 3 and 14
  reached the run-off.
- **Ruled out:** the three-line arrangement (Surfers Road's variant with all eight lines, alone in bank 1: the same cars turned,
  3 start events, 85 jolts); the grid's heading words (correct); the cursor and link progression (lead 0.8 points both ways).
  The normal grid has cars turned 14-32 degrees by the same push, harmlessly: the corners lie ahead there and the pit lane beside
  the normal grid is open tarmac.
- **Metropolis** (measured): 26 jolts in reverse, 22 of them inside-bend cuts 0-2 units onto the grass with no push, by the
  cars of the ±8 lines (lines 1 and 4, 4.5-7 units inside the tarmac edge at those points); none at the start. The normal
  direction does the same more often (65 jolts, 60 on the inside; per 1 000 car-points 6.16 normal, 2.32 reverse): the open
  AI-lines item, not a reverse fault.
- **Options measured** (one 150-s reverse run each, report §5): grid_alt Surfers Road 0 start events / 65 jolts (shipped 3 / 73),
  Amazon Falls 0 / 21, Pacific Coast 1 / 96, Surfers Oval 0 / 1; the corner patch (contacts A and B pushing to the reverse front
  corners c3/c2, boot code at 8 sites, scratch only) Surfers Road 1 / 63, mixed elsewhere (Pacific 95 → 106); links re-chosen
  2 / 63; every car 2 points apart 1 / 69; ±3 or ±4 lines 4 / 75-76; Metropolis on ±5 pairs 8 jolts, on ±3 5, with the corner
  patch 25.

**What was built** (Metropolis's pairs approved by Pascal; the bank-1 grid the session lead's decision, awaiting Pascal's
confirmation; above).
- **The bank-1 reverse grid** (`tencourse.BANK_ONE_GRID`, `CoursePlan.reverse_grid`, `race.car_table_for(start_points=)`): on
  Amazon Falls, Pacific Coast, Surfers Oval and Surfers Road the variant's car table starts cars 5-12 (the +5 line) on points
  1, 3, ..., 15 and cars 1-4 and 13-15 (the −5 line) on 2, 4, ..., 14: the investigation's `grid_alt`, exactly. Lines, models,
  performance and the player (point 0, line 0) stay the normal table's; `car_table_for` refuses a grid that is not the opponents'
  own points rearranged. It applies where the pairs put several cars on one stored line and is the measured arrangement, not a
  rule for other pairs. The normal direction's car tables do not change.
- **Metropolis's reverse pairs** (`tencourse.METROPOLIS_PAIRS = (0, 7, 2, 3, 5, 5, 6, 7)`): the cars of the ±8 lines (pairs 1
  and 4) follow the ±5 lines. Its grid stays the normal table's (as measured). `build_variant_blob` stores six lines: the variant
  is **40 144 bytes** (52 080 with eight), still at window 0x19af10 in bank 2 (to 0xa4be0); bank 2's run after it grows from
  99 712 to 111 648 bytes.
- **The race log** (`race_log.lua`) writes, with `VR_RACE_CARS_TO`, an O line per opponent per frame (road point, x/z, yaw +0x36,
  speed +0x14; `runner.parse_race_cars`), which the two new race tests read.

**Measured on this tree** (`out/p26/stage2/t12/`).
- **Bytes.** Two fresh conversions, one on 3290571 (`base.pkl`), one on the changed tree (`after.pkl`; `build_base.py`,
  `compare.py`, `compare.txt`): `build_all`'s set (no variants) identical in all six regions; in the ten-course set the seven
  normal race blobs have identical SHA-1 digests (`base_digests.txt`, `after_digests.txt`), as do Alpine's, Diablo Canyon's and
  Metropolis's reverse race blobs; the program ROM differs in 56 single bytes, the start-point bytes of cars 1-15 but car 9
  (point 9 either way) in the four bank-1 variants' race blobs; the data ROM only in bank 2's Metropolis variant (its pointer
  block and lines; its old tail erased). Bank 1 keeps its one run of 13 488 bytes.
- **Races** (one 150-s run each way per course, autopilot; the set raced is the base conversion with the change applied,
  shown identical to the changed tree's set in all six regions, `measure.py`, `measure.log`, `offline.txt`). Grid yaw: each
  opponent's largest |yaw − direction to its own line's point 3-7 ahead, the best of the five| over the 60 frames before the
  green (an unpushed standing car faces its target exactly: 0.0); start: the opponents with a J line in the 200 frames after
  the green.

| course | grid yaw reverse, before → after (cars turned) | grid yaw normal | start cars reverse, before → after | start cars normal | jolts reverse before → after (bound) | jolts normal | opponents moved |
|---|---|---|---|---|---|---|---|
| Alpine | 63.9 (3, 9, 15), unchanged | 35.0 (crew start, moving) | 1 (car 1, point 3) | 3 (cars 2, 5, 6) | 93 → 93 (121) | 74 | 15 / 15 |
| Amazon Falls | 62.3 (8 cars) → 0.0 | 32.3 | 1 → 0 | 0 | 23 → 21 (31) | 14 | 15 / 15 |
| Diablo Canyon | 37.4 (4, 5, 7, 9, 11, 13, 14), unchanged | 45.5 | 2 (cars 7, 8) | 3 (cars 6, 8, 9) | 118 → 118 (152.5) | 95 | 15 / 15 |
| Metropolis | 31.8 (5, 7, 10) → 35.5 (3, 5, 6, 7, 10) | 30.2 | 0 → 0 | 0 | 26 → 8 (107.5) | 65 | 15 / 15 |
| Pacific Coast | 56.2 (9, 10, 11) → 0.0 | 16.0 | 3 → 1 (car 15, the first bend) | 0 | 95 → 96 (146.5) | 91 | 15 / 15 |
| Surfers Oval | 74.5 (5 cars) → 0.0 | 26.4 | 3 → 0 | 0 | 12 → 1 (38.5) | 19 | 15 / 15 |
| Surfers Road | 67.2 (2, 3, 6, 7, 10, 14) → 0.0 | 34.9 | 3 → 0 | 0 | 73 → 65 (79) | 46 | 15 / 15 |

  "Before": the bank-1 and Metropolis grid yaws are the same measure on the investigation's shipped runs (`gridyaw_inv.py`; its
  F lines log the same yaw), the start cars and jolts the investigation's and §6's; Alpine and Diablo Canyon did not change.
  "Start cars normal": the same measure on the normal race of the final session (`t12/final.log`, STARTCARS lines).
  The Surfers Road grid_alt race reproduced the investigation's run event for event (the same J lines, frames and road points).
- **The tests' start bounds** (`START_CARS_MAX`) are the reverse measurement: 0 on Amazon Falls, Surfers Oval, Surfers Road and
  Metropolis; Alpine 1 and Diablo Canyon 2 are measured regression bounds (Alpine's start car is car 1, Diablo Canyon's cars 7
  and 8; the normal runs counted 3 on both). **Pacific Coast's bound of 1, against the normal run's 0, is a stated exception to
  the plan's rule that no reverse bound is looser than the normal direction's:** its one car (car 15 on the −5 line) cuts the
  first bend 159 frames after the green, the open AI-lines item, not the grid (the session lead's decision, told to Pascal
  as "3 -> 1", not asked). The KNOWN FAULT grid
  bounds below exceed the normal runs' grid yaw on Alpine (35.0) and Metropolis (30.2); they mark a fault, not an accepted
  figure.
- Against the local tangent of the centreline instead (point j − 1 to j + 1) the bank-1 grids read up to 5.0 degrees, Pacific
  Coast's 24.4 (its last rows on the 28-degree bend, aiming at their targets): why the test measures against the line ahead.
- All seven, reverse: laps at every crossing (no step back, no wrap without the lap byte rising; wraps 14 or 15 of 15, Diablo's
  car 1 none as before), the checkpoints in order, none parked, largest backstep 0, cursor lead 2-10, leader 723-893 points.
- The investigation's "start events" window took the green from a stale speed 400 frames early (frame 1467), so it ended 200
  frames after the real green (1866): the committed window is that, stated (`START_FRAMES` 200). Over 600 frames the first
  bends' inside cuts dominate (Surfers Road 10 cars, Pacific Coast 8, Alpine 8).

**Known faults found, not fixed here.** On the standing reverse grid of **Alpine** (cars 3, 9, 15 at 30, 24, 64 degrees),
**Diablo Canyon** (seven cars at 10-37) and **Metropolis** (five cars at 23-36; three at 28-32 on eight lines) opponents stand
turned like the bank-1 cars did; inferred, not traced: the same push (with eight lines the cars of each line still stand in
pairs nose to tail). Their start counts are small (Alpine 1: car 1 off at point 3, 34 frames after the green; Diablo Canyon 2:
cars 7 and 8; Metropolis 0) and the tests bound the grid yaw at the measurement plus 0.5 degree (`GRID_YAW_MAX`, marked KNOWN
FAULT: Alpine 64.4, Diablo Canyon 37.9, Metropolis 36.0). On Metropolis the ±5 pairs added cars 3 and 6 to the turned ones
(three cars up to 31.8 degrees before, five up to 35.5 after) while the jolts fell 26 → 8.

**What stays open.**
- The corner patch (the contact routines pushing to c3/c2 in reverse): correct in principle, mixed in effect on one run each;
  not recommended yet. It is the candidate for Alpine's, Diablo Canyon's and Metropolis's turned grid cars (not measured there).
- Opponents cutting the inside of bends onto the grass: most of the jolts left, both directions (Metropolis normal 65 against
  26 reverse in the window): the open AI-lines item.
- Pacific Coast's first-bend cut (car 15 on the −5 line at reverse point 20, 159 frames after the green).
- Link words naming side or pit-lane quads (`segment_links` keeps the last-listed quad), both directions.

**Commands.** Measurement: `out/p26/stage2/t12/measure.py` (pytest on `tests/test_reverse_build.py`'s static and race tests
with the set pre-built): 55 passed in 587 s (`t12/measure.log`, provisional bounds). Final, one session with a fresh conversion of the
changed tree: `.venv/bin/python -m pytest -s -v -rA -p no:cacheprovider --basetemp=out/p26/stage2/t12/bt-final
tests/test_convert_race.py tests/test_convert_reverse.py tests/test_blob.py tests/test_tencourse.py tests/test_directory.py
tests/test_reverse_build.py` plus the two race-log parser tests of `tests/test_mame_runner.py` by node id: **145 passed in
5 085 s**, none skipped (`t12/final.log`). Its races gave the numbers of the table above exactly (grid yaw, start cars, jolts).

### 11.6 The arcade start gantry: its lettering readable from behind (Task 11)

**From the drive.** Driving in reverse on Alpine and Diablo Canyon, Pascal passed an arch at the lap line whose banner
showed nothing from behind (§11.1; `drive/run2/line_big.png`). The arch is not a Saturn gate. It is the arcade's own start
gantry, which a converted course keeps where its Saturn START gate does not stand at the line (`START_GATE_NEAR`). Pascal
chose to add lettering and, after the recon, option B: the converted courses get their own copy of the waving gantry. The
paths below are under `out/p26/stage2/`.

**Recon (measured; `arch/recon_start_gantry.txt`, `recon_animation.txt`, `sheet_recon_today.png`).**
- **Where it stands.** The gantry is placed on Alpine (−260.8, −51.3, −396.1; road point 0 of 452; lateral +5.0), Diablo
  Canyon (−404.6, −35.2, −183.6; road point 456 of 457; +4.7) and Pacific Coast (−201.1, −17.9, 1.1; road point 0 of 410;
  +4.2). On all three it faces along the road (within 4.7°). The other four courses start at their Saturn START gate.
- **What the handler draws (`docs/formats/model1-course-tables.md` §14).** The handler `0xffb07f` draws frame
  `(+0x1c & 31)` of the object list `0xfdc033` at the entity's position and yaw, then counts the frame on. It advances one
  frame per logic frame while drawn, so a full wave takes 32 logic frames.
  - **The list:** 32 pointers to records `(poly, tex, size)`, each followed by a zero word that ends `0xff84a2`'s walk. All
    three originals' spawn lists, and so the attract mode, use this list.
  - **Each frame:** an object of 141 records (117 quads), every record two-sided, z mode 1, every record advancing its
    colour entry. The 32 frames read the same colour words.
  - **The quads:** posts (36 quads, still), a banner of 26 tall strips swinging 2.4 units fore and aft (z −1.39..+1.61), its
    border strips, and 23 red letter quads, "START", on the −z side, moving with it: their corners stand 0.52-1.18 units in
    front of the banner's surface under them (over the 32 frames).
- **Why the back is blank.** From behind, the two-sided letters are farther than the banner. The painter's sort draws the
  narrow strips after them, which hides the letters; any letter that showed would read mirrored. The pale stripes are the
  strips lit differently as the wave tilts them.
- **Why not static scenery.** A copy in the scenery could not follow a banner that swings 2.4 units. Placed beyond the
  swing, it would hover 0.6-3.6 units off the banner; placed at the mean, the banner would pass through it every cycle.

**What was built (`vrtools/arcade/gantry.py`).**
- **`gates.mirror_behind(pts, centre, zb)`** is Task 9's copy, made into a helper over a banner surface z(x, y). The Saturn
  gates' `gate_lettering` produces the same copies through it.
- **`gantry_parts(frames)`:**
  - the banner is the upright quads at least 3 units tall that move over the frames (the posts stand still);
  - the lettering is the other moving upright quads inside the banner's span, standing 0.25-2 units in front of it at every
    corner, all on one side;
  - the same quads must be chosen in every frame (26 banner strips, 23 letters).
- **`mirrored_letters`.** Each letter is mirrored about the frame's banner centre (the strips' x span, 0.06-0.14 off the
  posts' axis, so the copies sit up to about 0.27 units sideways from an exact back-to-front
  match; not visible in the pictures) and stands as far behind that frame's banner as it stands in front. Each corner follows the strip under it
  (`Surface`: z interpolated over the strips' triangles).
  - The corner order is kept, so the copy is the letter turned half round: it reads correctly from behind and is drawn from
    behind only. Its stored normal is the letter's turned half round, (−nx, ny, −nz).
  - Measured on all 32 frames: each copy's corners stand 0.52-1.18 units behind the banner's surface under them, the
    letters' corner range in front.
- **`frame_object`:**
  - the frame's seed and 141 records are copied byte for byte from the ROM;
  - then each copy follows as two records: a link-0 record and a link-2 drawing record, bit 14 clear, keeping the letter's
    other flag bits (z mode 1, its light bits), so it sorts and lights as the letters do;
  - then an end marker. Size 187.
- **`install_start_gantry`**, called by `build_all` after every course:
  - **Polygon ROM:** the 32 objects (7 544 bytes each, 241 408 in all) go first-fit into free polygon ROM, so no course's
    objects move.
  - **Program ROM:** the list (32 pointers, then 32 records of 16 bytes each with the zero word, the arcade's layout) and
    one colour run go into a 1 KB block at the top of the code area. `tencourse.start_gantry_address()` is 0x28f970..0x28fd70.
  - **The colour run:** its base entry is 0x87df8, never read because each frame's first record advances, and is left erased.
    The 141 entries the frames read follow, copied from the arcade's, which are the same for every frame, then one entry
    for the copies (the letters' word). That is 0x28fbf0..0x28fd0e.
- **The spawn lists.** `spawn_list_for(start_gantry_list=)` gives the start-gantry entity of Alpine, Diablo Canyon and
  Pacific Coast the new list. The handler, position, yaw and type stay as they were. `max_colour_entry` also walks the
  frames a converted course's gantry names.
- **Why the block is safe.**
  - The whole code area is erased in the original, and the block lies above the fixed layout (directory image, seven tile
    tables, race blobs and spawn lists); `start_gantry_address` refuses a block that would overlap it.
  - No other writer claims it (fix round 1): the reverse annex's first region (`annex_regions()`, computed when the annex is
    placed, not at import) ends at the block's start, and the select pictures' free-run search leaves it out
    (`tencourse.picture_exclusions`, which `install_pictures` passes: a committed behavioural test). `build_all` also writes
    it before either runs, and both take erased runs only.
  - Measured on the integrated tree's playtest set (`out/p26play3`, the directory image ending at 0x27ab4d with the mirrored
    figures' routines): the fixed layout ends at 0x2899dc (the last spawn list's slot, `start_gantry_address`'s bound),
    24 468 bytes below the block's start; the last bytes below the block, the select pictures', end at 0x28e9b0, 4 032 bytes
    below it; the annex lies in the colour-table run (0x2b90c0..0x2bcb00), whose read taps are untouched. (On 8bc449e's
    layout, 0x180 bytes lower: 25 876 bytes from the layout's end to the block's end, the pictures 4 416 below the block.)
  - `test_the_gantry_block_lies_in_erased_code_room_outside_the_annex` pins the bounds: the top 1 KB of `CODE_FREE`, above
    the last spawn list, erased in the original; the annex regions end at or below it and the pictures are never offered a
    run that meets it (checked on the original set, where it is erased); apart from the annex; and holding exactly what was
    written.

**Stated deviation (approved by the owner on seeing the options).** In the normal direction too, the gantry entity's
object-list word changes on Alpine, Diablo Canyon and Pacific Coast, from 0xfdc033 to 0x28f970. The new list and objects
are added on erased ROM.

**The proofs (`arch/proof.txt`; builds `arch/before/` at 8bc449e and `arch/after/`, made by `arch/scripts/arch_build.py`;
the whole-image comparison and the budgets re-measured on the integrated tree, below).**
- **Collision.** The TGP data ROM is byte-identical (sha256 540af4b5…, the same as Task 9's). On all seven courses, the
  input of `install_collision` digests the same.
- **Scenery.** 478 cells compared, 0 changed. The tile records, the colour words and `capped_cells` (0 → 0) are identical.
- **The whole image.**
  - The boot, data, TGP data and TGP program ROMs are identical.
  - The program ROM differs in 933 bytes: 924 in the block, which was erased before, and 9 in the three object-list words
    (0x286b70, 0x287978, 0x288780 on 8bc449e's layout). Nothing else.
  - The polygon ROM differs in 241 237 bytes, all inside the 32 new objects, all erased before.
  - **Re-measured on the integrated tree** (the set built before this merge, `integ/build/` at 7580c22, against
    `out/p26play3`, both with the variants): boot, data, TGP data and TGP program identical; the program ROM differs in
    933 bytes, 924 erased before and 9 in the three object-list words, now at 0x286cf0, 0x287af8, 0x288900; the polygon ROM
    in 241 237 bytes, all erased before.
- **The arcade's own gantry.** The 32 objects, the list, its records and the originals' spawn lists keep their bytes in the
  built set (a committed test).
- **Budgets.**
  - Polygon ROM free: 702 956 → 461 548 bytes (the floor is 65 536), the same on the integrated tree (its build reports
    before and after); TGP budget 7 651 words left in both.
  - `max_colour_entry`: 0x9b34b before and after.
  - The frame's record count (0x5011a0, write tap) rises by exactly 46 while the gantry is drawn. The highest seen near
    Alpine's gantry is 2 775 (in reverse), under the frame's record budget of 5 500 (§11.7: an object list that starts with
    the count above it is not drawn); Diablo Canyon's below.
- **Diablo Canyon's render rate near the gantry (measured, fix round 1; `arch/rate_diablo.txt`).** `arcade_rate[2]` stops
  at the known progress check before its rate check, so it was measured separately: a headless run with the render-rate
  log (list switches per 57 frames) and the per-logic-frame record count, before (8bc449e's build) and after, each way.
  The integrated tree's reverse start, which also draws the mirrored start figures (left out in reverse on 8bc449e), is
  measured below ("On the merged set").
  "Near the gantry" is every logic frame within 150 units on which the gantry was drawn (its frame counter advancing).
  - Normal direction: drawn on 81 logic frames, 146 to 2 units; rate 28-29 in every window holding them, before and after;
    record peak 3 256 before, 3 302 after (+46).
  - Reverse: drawn on 272 logic frames (at the start, the gantry behind the car, and on the approach at the lap's end, 148 to
    1 units); rate 28-29 in all 12 windows, before and after; record peak 4 075 before, 4 121 after (+46), under the
    frame's record budget of 5 500 (§11.7), so no object list was skipped on those frames.
  - The rate logs and the player's collision logs are byte-identical before and after, both ways. The floor the tests
    hold is 27.
- **On the merged set (measured in the final fix wave; `out/p26play3`, built from d93c0f2; `out/p26/stage2/fix/`,
  `scripts/fix_start.py`, `fix_rec.lua`, `fix_analyse.py`, `analyse.txt`, `analyse_compare.txt`).** One 80-s headless run per
  case under the autopilot (the drive line from `arch/after/conv.pickle`), with the render-rate log, the record count's
  write tap logged every frame from frame 1 (`arch_seq.lua`'s tap), `figures_log.lua` and the race log. The load is frame
  1600, the green 1866 (load + 266) in every run.

  | run | figures live (frames) | rate, windows holding a live figure | record peak, figures' frames | peak, load to green + 400 |
  |---|---|---|---|---|
  | Diablo Canyon reverse, merged set | 1605-2010 | 28-29 (8 windows) | 5 151 | 5 151 |
  | Metropolis reverse, merged set | 1605-2056 | 28-29 (9 windows) | 4 921 | 4 921 |
  | Diablo Canyon normal, merged set | 1605-2044 | 28-29 (8 windows) | 4 510 | 5 711 (frame 2251, §11.7) |
  | Diablo Canyon reverse, `arch/after/build` (the gantry line's after build: no reverse figures) | none | 28-29 (from the load) | n/a | 4 121 |
  | Metropolis reverse, `arch/after/build` (the gantry line's after build: no reverse figures) | none | 28-29 (from the load) | n/a | 3 891 |

  - Every 57-frame window from the load to the green + 400 reads 28-29 in all five runs. The only window under 27 in
    any run is the boot's first (frame 57: 24).
  - The reverse start is under the frame's record budget on both courses: Diablo Canyon peaks at 5 151, **349 records of
    margin**, and Metropolis at 4 921. The three mirrored figures cost **+1 030 records** at the start on both courses
    (5 151 against 4 121, 4 921 against 3 891 at the same frames). Nothing is skipped at the start.
  - The run on the gantry line's after build reproduces the earlier reverse record values exactly (3 922, then 4 121, at the same frames as
    `arch/rate_after_2_reverse.log`), so the two methods agree.
  - Not resolved: the gantry's drawn frames. The lookup read a frame counter of 0 throughout (inferred: it kept an entity
    left over from before the race), so "the gantry drawn" was not identified in these runs. The rate and record figures do not depend on it.
- **The race (Alpine, normal direction, 150 s under the autopilot, `arch/before|after/race0.json`).**
  - The race reports are identical: the player completes lap 1 across the line, 6 extensions, the same clock at every dump.
  - The player's collision log and the render-rate log are byte-identical, and so are both directions' approach logs.
  - The handler's player test, timers and sound run as before.

**The pictures (headless, autopilot).**
- **Normal direction, Alpine: no change.** The before and after runs were compared at the same frames, with the same
  animation frames logged. There are 30 snapshots from 119 to 3 units, and 0 pixels differ in each
  (`arch/sheet_normal_alpine_before_after.png`). The entity's list reads 0xfdc033 before and 0x28f970 after.
- **Reverse, all three courses: "START" reads correctly on the banner.** The snapshots run from 80 to 20 units
  (`arch/sheet_reverse_approach.png`, with Alpine before and after). Before, the banner was blank and striped; after,
  "START" reads correctly on Alpine, Diablo Canyon and Pacific Coast.
- **Across the wave.** The approach sequence snapshots every 2 logic frames from about 95 units, which covers more than one
  cycle at every animation frame. The letters stay on the banner as it swings, with no clipping by a strip, the post or
  anything else at any frame seen (`arch/sheet_reverse_phases.png`, every 4th frame over one cycle;
  `arch/zoom_reverse_<course>.png`, the banner cropped from every sequence snapshot within 75 units).
  - The copies' red looks as bright as the front's: they are lit by a normal turned half round, as Task 9's copies are.
  - At the lap line "EXTEND TIME / BEST LAP" shows on all three courses in reverse.
- **Seen in the pictures, not caused by the change.**
  - In reverse, Alpine's autopilot spins about 19 units before the gantry, in the before run too, on identical frames.
  - Pacific Coast shows a small red block on a far wall beyond the line, the course's own scenery.

**Tests.** New: `tests/test_start_gantry.py`: on the integrated tree `pytest --collect-only` collects 18 tests (12 test
functions, two of them parametrised; the integration's `install_pictures` test among them).
- **Synthetic frames:**
  - the parts are found, and refused when the frames differ in shape, when nothing waves, or when the lettering stands on
    both sides;
  - each copy is the letter mirrored behind that frame's banner;
  - handedness: seen from behind, the copies are the picture the letters show from the front. A mirror across the banner
    alone fails this.
  - a frame's object is its own bytes, then the copies drawn from behind only, under the letters' z mode, with an honest
    size.
- **The ROM:** 32 waving frames, 26 strips and 23 letters; the install writes on erased ROM only and leaves the TGP data
  ROM alone.
- **The set:** the arcade's gantry keeps its bytes, the converted gantries draw the new frames, and the block's bounds hold.

Run with `test_tencourse.py`, `test_gate_lettering.py`, `test_polyrom_encode.py`, `test_convert_geometry.py`, `test_spawn.py`,
`test_tgp_build.py -k arcade_rate`, `test_race_build.py::test_each_course_races_on_its_own_tables[0]` (Alpine: laps,
extensions, render rate) and three of `test_reverse_build.py` (the annex's region, the variants only adding bytes, and the
annex read taps). 99 passed; the 2 failures are on the known list: `test_thinning_drops_small_far_quads_only`, and
`arcade_rate[2]` on Diablo's forward and backward progress, the same 2094 / 1037 units as before; it fails before its
render-rate check, which is why Diablo's rate was measured separately (above).

**On the integrated tree** (after this line's merge with the gates', the figures' and the grid's lines; `integ/`).
- `annex_regions()` replaces the import-time `ANNEX_REGIONS` (the block's bound is computed where the annex is placed, so a
  layout overflow no longer raises on import), and `test_install_pictures_leaves_out_the_picture_exclusions` checks that
  `install_pictures` passes `picture_exclusions()` to its free-run search.
- One invocation, `--basetemp=out/p26/stage2/integ/bt2`: `tests/test_start_gantry.py`, `test_tencourse.py`,
  `test_gate_lettering.py`, `test_polyrom_encode.py`, `test_directory.py`, `test_direction.py`, `test_spawn.py`,
  `test_convert_geometry.py`, the twelve static and build-level tests of `test_reverse_build.py` and its annex read-tap test:
  **154 passed, 1 failed in 3 509 s** (`integ/pytest2.log`); the failure is the known
  `test_thinning_drops_small_far_quads_only`.
- **Playtest set `out/p26play3`** (`.venv/bin/vrtools build --roms "$VR_ROMDIR" --saturn "$VR_SATURN_CUE" --out
  out/p26play3`, with the variants; `build-report.txt` beside it): the block at 0x28f970..0x28fd70; the annex's load
  records from 0x2b90c0, race blobs 0x2b9990..0x2bcb00; polygon ROM left 461 548 bytes; TGP budget 7 651 words left. A
  headless 30-s `run_mame` of `memtrace.lua` boots to the attract: the mode byte 0x501139 reads 0x03 at frames 480, 1 000
  and 1 600 (`integ/bootcheck3/`). Launchers for it were made afterwards by the session lead: `out/rec155/launch.sh`
  (normal) and `out/rec156/launch.sh` (reverse: `VR_DIRECTION=1 VR_DIRECTION_RAM=502294`, `direction.lua`); not committed.

### 11.7 The frame's record budget (final fix wave)

The earlier sections compared the frame's record count with "the cap of 5 500" without saying what passing it does. Read
in the boot listing (`out/p26/stage2/t13/boot.lst`, each line checked there):
- **The budget word.** 0xfe11bd `mov.w #157C, 5011B0` sets 0x5011b0 to 5 500. Just before it, 0xfe119e..0xfe11b5 sets the
  flag 0x501a35 to 1 and clears it when the byte at 0xb00001 reads 0. When the flag is 0, 0xfe11d3 `mov.w #1388, 5011B0`
  sets 5 000 instead. What that byte is was not looked into: one branch sets 5 000; it was not seen in these runs (every
  run logged 5 500 in 0x5011b0 from the load on).
- **The object-list emitter.** Both entries, 0xff848a and 0xff84a2 (§7 of `docs/formats/model1-course-tables.md`), start
  with `cmp.w 5011B0, 5011A0` / `bgt FF8582` (an `rsr`): when the frame's count is already above the budget, the whole
  object list is skipped. Otherwise every `(poly, tex, size)` triple of the list is emitted and its `size` added to 0x5011a0
  (0xff854c). The single-object emitter at 0xff8583..0xff863b adds its size at 0xff861a with no test. So the count can end
  above 5 500: the list that crosses it is emitted whole, and every object list that comes later in that frame is not drawn.
- **A character draw path with its own check.** In the character draw routine, 0xff5d87 `test1 #1A, 0[R25]` / 0xff5d90
  `bne FF5E33`: only an object whose flag word has bit 0x1a set reaches 0xff5e33..0xff5e48, `mov.w 5011B0, R0; sub.w #96,
  R0; cmp.w R0, 5011A0; bgt FF5E83`, which emits it only while the count is at most the budget − 150. The start figures
  are not on that path: their flag words in every `figures_log.lua` run of the fix wave are 0x10000000, 0x90000000 and
  0xd0000000 (bit 0x1a clear), so they take 0xff5d93..0xff5e30 (the visible-cell test, then the root pushes), where no
  budget test was found. That nothing is skipped at the start rests on both reverse start peaks being under 5 500.
- So 5 500 is a per-frame budget of summed object sizes. The word each `0x01` object command carries is `[0x5011b0]`
  itself (0xff8571, 0xff862c); a record's `size` only adds to the count (§7).

**Measured peaks** (the write tap on 0x5011a0 logged per frame, the peak of each frame; one 80-s run each from the boot,
about 2 700 frames after the green, roughly half a lap at the autopilot's pace; `out/p26/stage2/fix/`). `arch/after/build`
is the gantry line's after build: it already holds the gates' lettering copies and the gantry's frames, without the
reverse figures, the bank-1 grid or Metropolis's pairs. `out/p26play1` is stage 1's playtest set (built from main's stage 1
code, not a fresh build of main; its normal content is the merged set's minus the stage 2 deviations, per the final
re-review).

| course, direction | set | peak at the start (load to green + 400) | highest in the run | frames ending above 5 500 |
|---|---|---|---|---|
| Diablo Canyon, reverse | merged `out/p26play3` | 5 151 | 5 893 (frame 4467) | 5: frames 4461-4469 (every second frame), reverse road point 201, 57-393 over |
| Diablo Canyon, reverse | `arch/after/build` | 4 121 | 5 893 (frame 4467) | the same 5 frames, the same values |
| Diablo Canyon, normal | merged `out/p26play3` | 4 510 with the figures; 5 711 at frame 2251 | 5 711 | 10: frames 2243-2257 (8, road points 30-31, 79-211 over) and 4401-4403 (2, road point 259, 38-160 over) |
| Diablo Canyon, normal | `arch/after/build` | the same | 5 711 | the same 10 frames, the same values |
| Diablo Canyon, normal | stage 1's `out/p26play1` | 4 464 with the figures; 5 697 at frame 2251 | 5 697 | the same 10 frames: 2243-2257 (65-197 over) and 4401-4403 (24-146 over), 14 under the merged set's on each |
| Metropolis, reverse | merged `out/p26play3` | 4 921 | 5 396 (frame 3305) | 0 |
| Metropolis, reverse | `arch/after/build` | 3 891 | 5 249 (frame 3247) | 0 |

- **Measured:** the reverse starts are under the budget (Diablo Canyon 349 to spare, Metropolis 579), with the render rate
  28-29 in every window from the load to the green + 400. Diablo Canyon passes the budget mid-race in both directions. The
  gantry line's after build passes it on exactly the merged set's frames and values; that shows only that the reverse
  figures, the bank-1 grid, Metropolis's pairs and the merge did not cause the crossings (that build already has the
  lettering copies and the gantry's frames). The reverse spot (reverse road point 201, forward 256 of 457) lies near the
  normal one at road point 259. Metropolis does not pass it. "Over" is the logged frame peak less 5 500: how far the list
  that crossed the budget carried the count.
- **Measured against stage 1's playtest set, normal Diablo Canyon** (`fix/5_normal_play1`, `fix/5_normal_play3`, the same
  80-s run on `out/p26play1` and `out/p26play3` in one session; `fix/scripts/fix_compare.py`, `fix/compare_play1_play3.txt`).
  The runs are frame-aligned: the player's x and z equal on all 4 602 race-log frames. The same 10 frames end above
  5 500 on both sets (2243-2257 and 4401-4403); the merged set's count is 14 higher on each of them. Over the whole run the number of writes to 0x5011a0 (one per emitted object, plus the frame's reset)
  is equal on every frame, and so is the number that raised the count: no frame of the run emits fewer objects on the
  merged set than on stage 1's. The merged set's count is higher by 0, 14, 28, 46 or 60 records on a drawn frame
  (inferred from the sizes, not traced: 14 per C.P. gate's lettering copies, 28 for a START gate's or two C.P. gates', 46
  for the gantry's copies, 60 for a C.P. gate's and the gantry's). So in the normal direction the crossing is present
  on stage 1's set too, with the same frames and the same objects drawn. Reverse Diablo Canyon has no stage 1 counterpart
  (stage 1's set has Metropolis's variant only).
- **Not determined:** which object lists are skipped on those frames (which list comes last in the frame), whether it
  shows on screen, a fresh build of main (stage 1's playtest set stands in for it), and the rest of each lap (the runs
  cover about half). Alpine, Amazon Falls, Pacific Coast and the two Surfers courses were not measured.

## 12. Status at the merge (13 Nov)

Stage 2 was merged into main and pushed on 13 Nov on Pascal's instruction, before a second drive.

- **Driven by Pascal:** the set `out/p26play2` (§11.1), which is the stage before the after-drive work.
- **Not driven by Pascal:** the set `out/p26play3`, which holds everything in §11.2 to §11.6. It was checked by the tests,
  the measurements and the contact sheets only (the figures' sheets were shown to Pascal; the rest was not). What a drive
  would judge:
  - the gates' lettering from both sides, and in the normal direction on Alpine and Pacific Coast (§11.2);
  - the arcade start gantry's "START" from behind on Alpine, Diablo Canyon and Pacific Coast (§11.6);
  - the mirrored start figures on Diablo Canyon and Metropolis in motion (§11.3.2);
  - Diablo Canyon's fourth checkpoint in reverse (§11.4);
  - the interleaved grids on the four bank-1 courses and Metropolis's lines (§11.5);
  - Surfers Oval in reverse, which was not driven on `out/p26play2` either;
  - whether Diablo Canyon's budget crossings show on screen (§11.7).
- **Still open with Pascal** (asked, not answered):
  - the interleaved reverse grid on the four bank-1 courses stays the session lead's decision (§11.5);
  - Pacific Coast's one car cutting the first bend at the reverse start, bound 1 against the normal direction's 0 (§11.5).
- **Whole suite on the merged tree:** §8 (868 passed, 15 failed, 1 xpassed on 75080f8; the commits after it change
  documents only).
