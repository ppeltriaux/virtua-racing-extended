# Phase 26 stage 4: findings

The measured findings of stage 4 of `docs/superpowers/specs/2026-11-11-reverse-courses-design.md` (§6.8): pit stops in a
reverse race on the seven converted courses, with Diablo Canyon's pit-lane wall trimmed off the lane. Facts and numbers only.
Plan: `docs/superpowers/plans/2026-11-14-reverse-stage4-pit-stops.md` (decisions P1-P6 and L1-L5); recon:
`docs/spike/2026-11-phase26-stage4-recon.md` ("the recon" below). The scripts, logs, builds, dumps and snapshots quoted are
git-ignored under `out/p26/stage4/` (one directory per task: `t1/` .. `t6/`; the crew's contact sheets under `look/`).

**Status: merged into main and pushed on 14 Nov 2026 on Pascal's "excellent, merge update md commit and push"** (§14), given
after one windowed run of the playtest set `out/p26play6` (§11: 113 s of emulation, launcher `out/rec159/launch.sh`). What they
drove in it was not stated; a 113-s run is too short to have reached a pit stop by the race clock, so this record does not say
that Pascal drove a reverse stop, Diablo Canyon's trimmed lane or the crew. They were sent five contact sheets of the crew and two
top views of Diablo Canyon's wall and have not commented on them. The whole suite was still running at the merge and ended after it with the 15 known failures only (§10).

Words used below:
- **The direction flag**: the byte 0x502294, 1 while a reverse variant is loaded (stage 1).
- **A variant**: the reverse version of a converted course: its own load and maps records and road tables over the normal
  course's collision (stages 1-2).
- **Pit pair**: the game forces a stop when the car's lap-position quad (`+0x150`) is the entry's pit quad q or q + 1, with stops
  left and the car heading along that quad; q and q + 1 are the pair.
- **Box**: where the game parks the car (x, y, z and a heading), in the entry's maps record.
- **Lane exit / mouth**: the pit lane's ends as the normal race uses them; a reverse car meets the exit first.
- **Work state**: the pit work the game picks at the trigger from the car's damage flags (1, 8, 11 or 14); each spawns its own crew.
- **The session lead** ("the lead"): the agent that planned and dispatched the tasks and ruled during the build.

**Map:**
- §1 what was built;
- §2 the decisions and who made them; the lead's rulings; what Pascal never ruled on;
- §3 the seven pairs and boxes;
- §4 Diablo Canyon's lane wall (Task 1);
- §5 the stops measured (Task 4);
- §6 the crew (Task 5);
- §7 ROM room and sites;
- §8 the normal direction against main (Task 6 Step 1);
- §9 the object at `[0x50138c]` (the spare tyres), measured;
- §10 the suite;
- §11 the playtest set;
- §12 not verified;
- §13 review items parked, open;
- §14 status;
- §15 the final review and the fix wave (its measures and the drive notes).

## 1. What was built

- **The reverse pit pair and box** (Task 2, `vrtools/convert/reverse.py` `reverse_pit`, `ReversePit`): per course, a pair of
  adjacent lane quads near the lane's exit, chosen by the lead's rules (§2, §3), and the box: the normal box turned half a turn
  on six courses, on Metropolis a box 40.7 units deeper in the lane, still under the tunnel roof.
- **The variant's records carry them** (Task 3, `vrtools/arcade/tencourse.py` `Reversed.pit_quad` / `pit_box`,
  `install_reverse`; `vrtools/arcade/directory.py` `_check`): load record +0x10 the pit quad, maps record +16..+31 the box. The
  game's pit routines read the served record, so no routine changed for the stop and no record grew.
- **Diablo Canyon's pit-lane wall trimmed off the lane** (Task 1, `vrtools/convert/collision.py` `PIT_LANE_WALL_TRIMS`,
  `trim_walls_off_the_lane`): one wall quad over the lane's west half is replaced by two that keep every part of it off the
  lane's tarmac (§4). It changes the normal race's collision on Diablo Canyon at that spot.
- **The crew turned half a turn in a reverse race** (Task 5, `vrtools/arcade/direction.py` `CREW_SITES`, `crewturn`,
  `CREW_RECORDS`): the four crew spawn sites call a flag-gated routine that reflects the crew through the box and turns each
  figure half a turn; `figmirror` holds for the crew's fourteen records too, so the animation is mirrored (§6).
- **Headless tests of the stops** (Task 4, `tests/test_pit_build.py`; `vrtools/mame/lua/pit_log.lua`, `crewdraw_log.lua`;
  `vrtools/mame/pitpaths.py`; `runner.parse_pit_log`, `parse_crew_draw_log`; `autopilot.lua`'s `VR_AUTOPILOT_AHEAD`, default 40
  as before): a normal and a reverse stop per course, the controls, Diablo Canyon's trimmed spot, the crew (§5, §6).
- **A normal race is main's** but for Diablo Canyon's wall: the ROM comparison and the races of §8.

## 2. The decisions and who made them

### 2.1 Pascal's decisions (14 Nov 2026)

The recon's questions were put to Pascal on 14 Nov as a table of six questions, each with one recommendation. **Pascal's answer
to the whole table: "Ok".** The lead read that one word as the six recommendations taken; that reading is the lead's, not
Pascal's words (ruling 1 below), and it was stated to Pascal in the plan's hand-over message so that they could correct it.

| | decision (as recorded in the plan) | Pascal's words |
|---|---|---|
| P1 | the car stops at the normal box in reverse; Metropolis's reverse box is deeper in the lane, in the tunnel | "Ok" (to the table) |
| P2 | the crew is turned half a turn about the box in a reverse race only; Alpine, Pacific Coast and Diablo Canyon keep in reverse the crew offset their normal race has | "Ok" (to the table) |
| P3 | stop and crew are both built before the drive | "Ok" (to the table) |
| P4 | Diablo Canyon's lane wall is fixed at the named spot (a shared-collision change, Diablo Canyon re-driven by Pascal in the normal direction); **decided twice**, see below | first "Ok" (to the table); then "What do you recommend for Diablo", then "Ok b, I follow your recommendation" |
| P5 | Alpine's PIT WORK firing about 13 units into the lane is accepted: no check of a second quad, no patch of the player's handler | "Ok" (to the table) |
| P6 | the game's rule that each checkpoint after a stop pays the next sector's extension is kept (both directions) | "Ok" (to the table) |

**P4 and a correction.** When the table was put to Pascal, the lead told them, in the recon's wording, that nothing drawn stands
at Diablo Canyon's lane wall. Task 1's first step showed that wrong: the wall quad is a step of the main road's right-side run-off
wall, and about a quarter of its footprint lies on the tip of a drawn rock (the recon had judged only the open part round the hit
point). Nothing was changed; Task 1 was parked and the question was put to Pascal again with the facts and a top view of the
quad and the rock, with two options: (a) leave the wall as it is; (b) trim only the part over the lane. Pascal asked "What do you
recommend for Diablo"; the lead recommended (b) (the rock keeps its wall; nothing moves nearer the road; the straight run from the
reverse pair to the box would pass 1.3-1.6 units from the wall's corner, computed, not driven). **Pascal: "Ok b, I follow your
recommendation".** Pascal wrote three messages on this stage, and only these: "Ok", the question "What do you recommend for
Diablo", and "Ok b, I follow your recommendation".

### 2.2 The lead's calls (the plan's L1-L5; cheap to change, Pascal may override)

| | call | status |
|---|---|---|
| L1 | the wall first, so that the later tasks are made on the final collision | **dropped during execution** (14 Nov): Task 1 stopped at its first step and waited for Pascal; Tasks 2 and 3 went ahead (ruling 3) |
| L2 | the directory image's test bound (`end − loader` in `tests/test_directory.py`) 6 000 → 6 500 | as planned; measured 6 251 (§7). Task 5 also raised the bound's second copy in `tests/test_hudname.py` (its implementer's call, approved by the review) |
| L3 | `REVERSE_PIT_MIN_RUN = 64.0` units, the least straight run from the pair to the box (the shortest run measured to park, normal Metropolis's; 26 units circled in the recon) | as planned; only Metropolis's box moves |
| L4 | test paths computed in the test session: normal = line 6 with the lane spliced in; reverse = the same session's normal pit run read backwards, joined to line 6 read backwards; `VR_AUTOPILOT_AHEAD` (default 40) | as planned |
| L5 | the reverse pit data on `Reversed` (`pit_quad`, `pit_box`); a course whose normal entry has no pit gets none | as planned |

### 2.3 The lead's rulings during the build (the ledger's "Ruling:" lines)

| | ruling | why | cost if wrong |
|---|---|---|---|
| 1 | Pascal's "Ok" = the six recommendations taken (same box, Metropolis deeper; crew turned in reverse only; both before the drive; Diablo's lane wall fixed at the named spot; Alpine's trigger accepted; the extension rule kept) | one word to a table that named one recommendation per row; the cheap reading that asks nothing twice | one of the six rebuilt after the drive; the wall fix (shared collision) is the dear one, and it is fenced, reversible by a constant, and re-driven by Pascal |
| 2 | Task 1 parked and the question put back to Pascal (leave the wall, or trim the quad's lane side only, keeping its end at the rock) | Pascal's standing rule "never disable or revert walls at drawn rocks" (a standing rule from earlier stages) covers a quad that stands partly at a rock, and their "Ok" had been given on a wrong fact | none; a wait on one task |
| 3 | Tasks 2 and 3 go ahead while Task 1 waits (L1's order dropped) | the pairs are tarmac quads (indices below the walls') and the boxes do not depend on wall quads, so the wall's fate cannot move them | Task 2's Diablo values re-measured (not needed: the pair 58 did not move, Task 1 Step 4) |
| 4 | Task 2's rules re-ordered: hard rules H1-H5 (both quads lane quads; neither holds the box nor is the normal pair or its partner; no point of any of the eight road lines inside either quad; between the exit and the box; a run of at least 64 units over tarmac), then in order C1 the normal box if any candidate reaches it, else the least move of the box towards the mouth; C2 "clear" candidates first (at least 8 units from all eight road lines and both feet at least 10 units from the lane's exit end), among the others the greatest clearance; C3 the best cover (the share of the lane's width a car driving along the lane cannot pass without crossing q or q + 1); C4 nearest the exit | the plan's first wording ("at least 8 units from any point of the eight road lines" as a hard rule) misread the recon, whose 9.9 was measured against lines 0 and 6 only, and excluded the recon's pairs on five courses and moved two boxes (the lead's plan defect). The clearance guards a player on the road's edge from a forced stop (the dearer fault), and the order keeps P1 (six normal boxes, Metropolis about 40 deeper); Alpine and Metropolis have no clear candidate and fall back to the recon's driven pairs | pairs on Pacific Coast, Surfers Oval, Surfers Road and Diablo Canyon that the recon did not drive (Task 4 drives every one); PIT WORK fires deeper in those lanes than Pascal was first told: said to them in chat after Task 2 (they did not comment), and repeated in the drive notes (§2.4, `docs/follow-ups.md`) |
| 5 | C3's tolerance: covers within 0.05 of the best count as equal, then C4 (nearest the exit) decides | a gap of 2-3 % of the lane's width is narrower than any line a car can hold, and it must not outrank a run twice as long (Pacific Coast: 234, 163 units in with a run of 71, had beaten 241 on a cover of 1.000 against 0.976) | one more round; Task 4 drives the result either way |
| 6 | (Task 2 review, item 2) H1 keeps its segment distance in the code; the test also applies `pit_entry_quad`'s own lane test (by the polylines' points) to the chosen pairs | the brief's words named the rule's intent (a lane quad), not a formula; two metrics agreeing on the chosen pairs is the stronger check | none seen |
| 7 | (Task 2 review, items 3-4) the chosen q, box, cover and clearance pinned per course as fixed expectations, plus one negative control for H3 (Surfers Oval) | an independent oracle of this geometry would be a third copy of it; pinned results show any drift | none seen |
| 8 | Task 1: one fix round before closing: the every-course collision tests and the TGP budget test run on the trimmed collision; how much drawn rock the new quads keep and whether any drawn rock lies over the lane's tarmac; tarmac under every cleared lane sample; a heights test; `ConvertError` when a named spot trims nothing; docstring and comment fixes (the piece merge and the copied build path parked) | shared collision: the review's open points were evidence still owed, and "is the cleared lane really tarmac" is a safety check, not polish | an hour |
| 9 | Task 4: one fix round: a failed MAME run no longer loses its whole wave; a new test of Diablo Canyon's trimmed spot under the player's own line with no stop possible (the lane's centre and 3 units west); seven review minors (one parked) | the trim is a shared-collision change proven until then only under the game's pit steering; the player's line is what Pascal will drive, and the old wall covered the west half | two short runs |

Two implementer's calls in Task 5 were approved by its review, not ruled by the lead: the test switch `crew=False` also narrows
`figmirror` to the figures' three records (so a set built with it shows the game's own crew in reverse), and the second copy of
the 6 000 bound (`tests/test_hudname.py`) raised with the first.

### 2.4 What Pascal never ruled on

- **The rules that choose the reverse pit pair and box** (H1-H5, C1-C4, the 0.05 cover tolerance, the 64-unit run of L3, the
  8- and 10-unit clearances, the box walk's 0.1-unit step) are the lead's. P1 ("the normal box; Metropolis deeper") is Pascal's;
  the exact Metropolis box (z 269.74, 40.7 units deeper) is the rules' result.
- **Where PIT WORK fires in reverse.** Under the lead's rules it fires deeper in the lane than the recon's prototype on Pacific
  Coast (pair 241 against the prototype's 247), Surfers Oval (15 against 31) and Surfers Road (13 against 20), and nearer the
  normal exit, where the reverse car enters, on Diablo Canyon (58 against 40) (§3). Pascal was told this in chat after Task 2 and did not comment. Alpine
  (250), Amazon Falls (32) and Metropolis (86) use the recon's driven pairs. P5 accepted Alpine's trigger "13 units into the
  lane" as the recon measured it.
- **The trim's geometry**: Pascal chose "trim only the part over the lane"; the cut into two quads, the rectangle that fences it
  and the heights of the new corners are the build's.
- L1-L5, every ruling of §2.3, the tests' design and tolerances (among them the 180-s reverse runs, the 5-point gate slack, the
  spot runs' lookahead of 3 points), the crew's test switch.

## 3. The seven pairs and boxes

From Task 2 (pinned in `tests/test_convert_reverse.py`) and Task 3's decode of the built set. "From exit" is the distance along
the lane from the normal exit to each quad's centre; "run" from the pair's nearer centre to the box; "cover" C3's measure;
"clearance" the least distance from either quad to the eight road lines; "clear" C2's test.

| course | q (q + 1) | from exit (q / q + 1) | run | cover | clearance | clear | box (x, y, z), heading | the recon's prototype pair |
|---|---|---|---|---|---|---|---|---|
| Alpine | 250 (251) | 52.0 / 17.1 | 65.9 | 0.967 | 3.8 | no | normal (295.10, −0.000, 605.32), 0xc00f | 250: the same |
| Amazon Falls | 32 (33) | 58.1 / 61.1 | 117.8 | 1.000 | 11.1 | yes | normal (−172.68, 3.109, 51.98), 0x831c | 32: the same |
| Diablo Canyon | 58 (59) | 11.8 / 18.6 | 179.8 | 1.000 | 8.8 | yes | normal (−346.00, −35.198, −100.96), 0x8b96 | 40 (71.6 / 69.8 from the exit) |
| Metropolis | 86 (87) | 11.7 / 3.6 | 64.1 | 1.000 | 5.7 | no | (−89.633, −9.090, 269.739), 0x7ff9; the normal box (−89.608, −7.876, 310.439) | 86: the same (prototype box z 270.0) |
| Pacific Coast | 241 (242) | 104.6 / 116.3 | 135.0 | 0.976 | 9.0 | yes | normal (−483.58, −0.002, −620.00), 0x312b | 247 (63.4 / 63.4) |
| Surfers Oval | 15 (16) | 164.6 / 141.2 | 158.0 | 1.000 | 11.4 | yes | normal (−240.38, 0.000, −56.67), 0x80ce | 31 (56.0 / 47.1) |
| Surfers Road | 13 (14) | 107.6 / 84.2 | 134.7 | 1.000 | 11.5 | yes | normal (−241.11, 0.000, −34.30), 0x807b | 20 (37.3 / 27.2) |

- Every heading is the normal one + 0x8000; on the six courses whose box did not move, x, y and z are the normal box's to the bit.
  Metropolis's y (−9.09 against −7.88) is the height of the tarmac quad under the moved box.
- Alpine 250 and Metropolis 86 are not "clear": 3.8 and 5.7 units from the +8 road line. The recon drove them with no false
  trigger, on line 6 only; the plain reverse line of Task 4 is line 6 too, so the ±8 lines did not run over them. (The fix wave
  drove the +8 line and beyond it: §15.3.)
- The built set's records equal the pins (Task 3: decoded from the ROM); against a set built with both fields None only the
  seven variants' load +0x10..+0x11 and maps +16..+31 differ.

## 4. Diablo Canyon's lane wall (Task 1)

- **What stood there** (Task 1's first step, before any change): wall quad 1689 of 1 919 in the converter's list, corners
  (−400.52, 42.80), (−388.86, 39.95), (−397.06, 31.66), (−408.71, 34.50) in x, z, area 120 square units: the main road's
  right-side run-off wall, the step between centreline points 23 and 24, 30 → 36 units out at its inner edge, 42 → 48 at its
  outer. 28.2 square units (about 23 %) lie on a drawn rock slope, 1.4 on the rock's steep east face; the rest over open sand and
  the lane's west half up to its centre line. The recon's car hit it at (−389.7, 41.4) driving up the lane at 322 km/h.
- **The cause** (`collision.py`): the face scan finds the rock at point 23 and nothing at points 24-27; the gap-fill
  (`fill_faces`) bridges 23 → 28 with a straight line across the lane; the wall strip lays the steps; the centre-on-tarmac check
  dropped the steps at 24-26 (centres on lane tarmac) and kept this one, whose centre lies on sand.
- **The rule** (Pascal's P4, option b): `PIT_LANE_WALL_TRIMS = {Diablo's course key: (−409.5, −388.0, 31.0, 43.5)}` (x0, x1, z0,
  z1); `trim_walls_off_the_lane` acts only on wall quads wholly inside that rectangle (one on Diablo Canyon), subtracts the lane's
  tarmac slices that overlap it, keeps the rest exactly (old corners with their own height, new corners on the old quad's plane)
  and cuts it into the fewest convex quads; any other outcome raises `ConvertError`, and so does a named spot that trims nothing
  or (fix wave, Minor 6) another number of quads than the spot names (`WallTrim((−409.5, −388.0, 31.0, 43.5), 1)`).
  It runs after the late wall drop, so tarmac and verge indices do not move. `fill_faces`, the face scan, the wall strip and
  the centre-on-tarmac checks are unchanged.
- **The result:** two quads (index 1689, 30.5 square units, keeping the old point-23 cross edge, the rock end; index 1690, 31.7,
  keeping the road-facing edge at 30 and 36 units out). 57.8 square units removed, exactly the part over lane slices 23 and 24
  (tarmac quads 44 and 46). The new quads keep all of the drawn rock the old one covered; no drawn rock lies over the lane's
  tarmac at the spot (only the white line's paint). Later wall quads shift by one (walls 457 → 458); tarmac (809) and verges
  (653) identical. The other six courses' collision identical with the rule off and on. TGP reserve 7 651 → 7 631 words (floor
  7 500). Top views: `out/p26/stage4/t1/wall_topdown.png` (before), `wall_topdown_after.png` (after).
- **Tests** (`tests/test_convert_collision.py`, on Diablo Canyon's collision as the build makes it, rule off and on): the lane
  clear of walls at the spot and tarmac under every lane sample there (922 lane samples inside a wall with the rule off: the red);
  every point of the old footprint off the lane still walled, the new wall inside the old, the road-facing edge kept, heights;
  nothing else changed. The every-course collision tests on the trimmed collision: 15 passed, 2 failed, both on the known list
  with messages identical with the trim off.
- **Driven** (Task 4, §5): under the game's pit steering in the reverse stop, and under the Lua autopilot on the lane's centre and
  3 units west of it with no stop possible. No human has driven it.

## 5. The stops measured (Task 4)

Frames are video frames from boot (the race loads at about 1600, the green at about 1866). From Task 4's report; Task 4's second
run and Task 5's run reproduced every number. Speeds in km/h; "to box" is the straight distance from the car at the trigger.

**Normal stops** (the baseline):

| course | trigger | quad | speed | to box | park | release | clock before / after | stops |
|---|---|---|---|---|---|---|---|---|
| Alpine | 3596 | 234 | 306 | 101.8 | 3900 | 4344 | 1445 / 1829 | 2 → 1 |
| Amazon Falls | 4452 | 499 | 328 | 141.7 | 4804 | 5248 | 1349 / 1733 | 2 → 1 |
| Diablo Canyon | 6160 | 785 | 294 | 59.5 | 6380 | 6824 | 908 / 1292 | 2 → 1 |
| Metropolis | 2420 | 72 | 176 | 62.5 | 2678 | 3122 | 1802 / 2186 | 2 → 1 |
| Pacific Coast | 3792 | 196 | 293 | 200.6 | 4216 | 4660 | 1116 / 1500 | 2 → 1 |
| Surfers Oval | 5308 | 703 | 258 | 180.2 | 5710 | 6154 | 1069 / 1453 | 2 → 1 |
| Surfers Road | 6948 | 863 | 236 | 136.9 | 7302 | 7746 | 249 / 633 | 2 → 1 |

**Reverse stops** (the variant's pair and box):

| course | trigger | quad | speed | to box | park | release | clock before / after | stops |
|---|---|---|---|---|---|---|---|---|
| Alpine | 4576 | 251 | 279 | 119.4 | 4906 | 5350 | 1074 / 1458 | 2 → 1 |
| Amazon Falls | 5094 | 32 | 333 | 119.2 | 5418 | 5862 | 971 / 1355 | 2 → 1 |
| Diablo Canyon | 6052 | 58 | 323 | 188.1 | 6458 | 6902 | 701 / 1085 | 2 → 1 |
| Metropolis | 5180 | 86 | 272 | 67.7 | 5432 | 5876 | 1059 / 1443 | 2 → 1 |
| Pacific Coast | 4314 | 241 | 323 | 164.6 | 4692 | 5136 | 1101 / 1485 | 2 → 1 |
| Surfers Oval | 5246 | 16 | 231 | 196.8 | 5668 | 6112 | 1007 / 1391 | 2 → 1 |
| Surfers Road | 6524 | 14 | 238 | 173.5 | 6920 | 7364 | 496 / 880 | 2 → 1 |

- On every stop, both directions: the pit handler 0xff2345 one logic frame (2 video frames) after the car is first logged on
  the pair; parked at the box within 0.01 with the yaw equal to the box heading until the release; release − park 444 frames;
  the clock standing from the trigger to the release, then + 384 (12 s); stops 2 → 1.
- In reverse also: no trigger from the release until the car is more than 20 units from the lane's polyline (Review Focus 1);
  the next lap exactly one more; two or more gates after the release, in order (Alpine 260, 387, 0, 119; Amazon Falls 0, 93,
  213; Diablo Canyon 0, 168, 278; Metropolis 0, 143, 239; Pacific Coast 0, 90; Surfers Oval 88, 260; Surfers Road 142, 314);
  no read of the wrong-way warning from the green to the log's end (the taps' positive control: the clock read on 8 490
  frames); all 15 opponents advancing during the stop (54-115 road points). On Surfers Oval and Surfers Road the lap is counted
  under the game's pit autopilot, before the release.
- **Plain reverse line** (line 6 read backwards, 150 s, Review Focus 3): no stop on any of the seven; each run passed the normal
  exit once or twice and was never on the pair.
- **Two stops and no third** (Amazon Falls reverse, 240 s, Review Focus 2): first stop 5094 → 5862 (2 → 1); second 8526, park
  8852, release 9296 (1 → 0, clock 807 → 1191); a third pass over the pair at 11742: no trigger, stops 0 to the end (13806).
- **Diablo Canyon's trimmed spot:** in the reverse stop the car crosses it under the game's pit steering (the trigger is 38
  frames earlier), inside the rectangle at frames 6090-6091, 0.58-0.63 units from the lane's centre, no wall hit. With no stop
  possible (a set from the same conversions with the variants' pit fields None) and the Lua autopilot at a lookahead of 3 points:
  the centre line at 325 km/h, 0.71-1.23 units from its path; the line 3 units west at 325 km/h, 1.25-1.54 from its path,
  4.24-4.53 from the lane's centre; no wall hit from 20 units before the spot's band to 20 after. On main's build
  (`out/p26play5`, no trim) the west line was hit at frame 6636 and thrown 19.9 units off the lane's centre; the centre line at
  lookahead 3 passed there without a hit (0.08-0.49 units from the old quad's edges), so only the west line shows the trim.
- The reverse runs last 180 s (at 150 s Surfers Road reached no gate after its release and Diablo Canyon one).

## 6. The crew (Task 5)

- **Read from the boot listing before patching:** each spawn fills its objects' position, heading, record and handler before it
  returns; nothing places them later but the end-of-animation add (a figure site). State 1 spawns five objects, states 8, 11 and
  14 six. The fourteen crew records (§20 of the formats note) are each referenced as a 32-bit literal only at the four spawns'
  stores. The crew runs the start figures' character code (handler 0xff5c3d), so the figure sites already cover its animation.
- **Built:** the four sites `bsr <spawn>; inc.h 191[R25]` (0xff2518, 0xff26f0, 0xff2735, 0xff277a; pattern-checked) become
  `jsr crewturn<state>` + nop; each entry (34 bytes) runs the spawn and the `inc.h` and, with the flag set, calls `crewturn` (143
  bytes): each crew object reflected through `pitbox`'s box (the box the spawn used), heading + 0x8000. `figmirror` 54 → 229 bytes
  (17 records). With the flag 0 the path is the original's but for the condition flags, which nothing reads (checked by the
  review in the listing).
- **Measured** (`tests/test_pit_build.py`, every 20th frame from the park to the release; the reference stop of the same work
  state):

  | course | reference | work state | objects | largest difference from the reflection |
  |---|---|---|---|---|
  | Alpine | the normal stop | 1 | 5 | 0.0001 |
  | Amazon Falls | the normal stop | 1 | 5 | 0.0001 |
  | Diablo Canyon | the normal stop | 14 | 6 | 0.0 |
  | Metropolis | the reverse stop on a set without the crew change (its normal stop is work state 11, its reverse stop 14) | 14 | 6 | 0.0 |

  The asserted tolerance is 0.05 units (Task 5's commit message says "within 0.0001": that is the measured worst). Headings: the
  reference's + 0x8000. Animation (`crewdraw_log.lua`): every word pushed through the figure routines for each crew object, on
  each of the 222 logic frames from the park to the release, is the reference's negated, in the same order.
- **A normal stop's crew unchanged** (Review Focus 4): Amazon Falls and Metropolis normal on the set and on a set built without
  the crew change: pit logs identical over 7 030 lines, crew-push logs over 15 860 / 16 100 lines. The attract mode's pit scene
  against main's build: §8.
- **Contact sheets** (scratch, sent to Pascal, not commented on): `out/p26/stage4/look/crew_4_amazon.png`, `crew_6_metropolis.png`,
  `crew_8_surfers_oval.png`, `crew_9_surfers_road.png`, `crew_alpine_pacific_diablo.png` (rows: normal, reverse with the crew
  turned, reverse before Task 5; park + 150 and + 350). Seen by the lead (the lead's looking, not Pascal's): the reverse rows match the normal rows; on Amazon Falls
  the figure in front of the camera is gone. On Alpine, Pacific Coast and Diablo Canyon the crew is turned about the car in both
  directions (P2: as their normal race has it).

## 7. ROM room and sites

- **The directory image** ends at 0x27b0e3 (main 0x27af1d); `end − loader` 6 251 bytes (main 5 797) against the raised bound of
  6 500. `figmirror` grew 175 bytes, so `figrootx` .. `figwalk` moved +175; `crewturn` and its four entries (279 bytes) follow
  them, so the stage 3 routines (`dirclear` .. `hudattr`) moved +454. The tables stored after the image moved +0x1d0.
- **Free after the image** on the seven-course set: 2 592 bytes at 0x28ef50 (below the start-gantry block at 0x28f970; the recon
  had 3 056), six spawn-slot tails of 720 / 744 bytes, 98 at 0x28fd0e: 7 082 in all. First-fit placement was not simulated beyond
  the build succeeding.
- **Boot sites:** the four crew sites only (§6); listed in `tests/test_directory.py`'s allowed spans.
- **Records:** no record grew; no new RAM cell. The variants' pit quad (+0x10) and box (maps +16) were already in the layout.
- **TGP:** 7 631 words free (floor 7 500), after the trim's 20 words.

## 8. The normal direction against main (Task 6 Step 1)

**Builds.** Main 1216442 from `git archive` into `out/p26/stage4/t6/main_src/`, built with its own code by the CLI (`python -m
vrtools build`, run from that tree, which `vrtools.__file__` confirms) into `out/p26/stage4/t6/main/`; this tree (2e7883d) built
the same way into `out/p26/stage4/t6/branch/`. Both with the variants (the CLI's normal build). Compared by
`out/p26/stage4/t6/cmp6.py` (output `cmp6.out`), `cmp_col.py` (each course's collision decoded from each set, `cmp_col.out`) and
`cmp_extra.out`; each tree's directory layout from its own code (`lay_main.json`, `lay_branch.json`).

The plan's expectations were hypotheses; what each ROM shows:

| ROM | bytes differing | where, and why | against the plan |
|---|---|---|---|
| polygon (16 777 216), TGP program (8 192) | 0 | identical | as expected |
| TGP data (2 097 152) | 384 085 (143 608 words) | Diablo Canyon's lists (4 357 words) and quads (3 558 words; its first 1 689 quads identical); **and the collision of the four courses installed after it, moved**: Metropolis's list block +4 words (0xdc00 → 0xdc04, in the same zero-filled gap after Diablo's), its quad pool +0x10 words, Pacific Coast's, Surfers Oval's and Surfers Road's blocks and pools +0x10 words each, with the eight slot-table words of slots 6-9. The TGP allocator places each course first-fit after the one before; Diablo's lists grew 2 words and its pool one quad. Decoded from each set (lists in order, quads, collision map, surface table) the six other courses' collision is identical; Alpine's and Amazon Falls' did not move | **not as the plan expected** ("differs only in Diablo Canyon's collision"): four other courses' collision moved, content identical. A finding; the game reaches a course's collision only through its slot's two addresses |
| data (4 194 304) | 641 | 620 in Diablo Canyon's collision map (0x259a80..0x261a80: 616 cells, 615 of them a list offset + 2 words, the lists after the two that grew, and one + 1, cell (39, 66), between them); 1 in its surface table (index 1919: the table is one byte longer, and every shifted byte is a wall's 5 as before); 20 bytes = 10 code-area pointers in bank 0 (0xde80c..0xde845), each main's + 0x1d0 (the blocks after the spawn lists, moved with the tables) | Diablo's collision as expected; the 10 relocated pointers not named by the plan's wording (stage 3 had the same 10, + 0x3d0) |
| boot (262 144) | 48 | 28 inside the four crew sites (7 each: `bsr <spawn>; inc.h` → `jsr crewturn<state>` + nop); 20 bytes in 11 address operands, each main's value + the routine's move inside the image: + 454 for `dirlock` (0xfc278a), `rankgate` (0xfc40d0), `dirclear` (0xfe3cd0), `hudname` (0xff479b); + 175 for `figrootx` (0xff5e15, 0xff6a1a), `figrootz` (0xff5e21, 0xff6a2e), `figrot0` (0xff6c27), `figrot2` (0xff6c43), `figwalk` (0xff6714). Nothing else | as expected (the four sites and relocated operands, each listed) |
| program (4 194 304) | 46 470 | 46 331 in the code area, 139 in the annex (the variants' records), 0 elsewhere; the direction screen's data block identical. Annex: the seven variants' pit quads (load +0x10, 0xfffe → q) and boxes (maps +16, zeros → the box), and 14 relocated words (each variant's tile table and spawn list, + 0x1d0). Code area, entry by entry at each one's own address: the ten load records only relocated words (21: each converted entry's tile table, spawn list and race blob, + 0x1d0); `start` one (`dirdone`); the ranking block 21; `figmirror` changed by the plan (54 → 229); the stage 3 routines only relocated words (`dirlock` 1, `dirsel` 3, `dircursor` 1, `dirdraw` 2, `dirshow` 1, `hudname` 1); `crewturn` and its four entries new; the tables from 0x27af20 (main) against 0x27b0f0 (branch) up to the start-gantry block: 1 883 differing words, every one a code-area address + 0x1d0, nothing else; main's 0x28f7a0..0x28f970, past the branch's tables, erased; the gantry block identical | as expected (the code area, the variants' records, what the image's growth moved) |

**The races** (`out/p26/stage4/t6/race6.py`, runs under `out/p26/stage4/t6/runs/`). Main's tree has no `pit_log.lua`, so this
tree's runner and Lua drove both sets (the RAM the logs read and the reverse table's address, 0x2797ec, are the same on both).
The paths: the normal pit paths of Amazon Falls and Metropolis made by `pitpaths.normal_pit_path` in Task 5's session (line 6 of
the ROM with the lane spliced in; the road tables and the placement are the same on both sets), and Diablo Canyon's line 6
decoded from each set (the two files identical). Environment as Task 4's normal runs (pit, race, field, collision and start
logs; 150 s).

| run | main | this tree | comparison |
|---|---|---|---|
| Amazon Falls normal, its pit stop | trigger 4452 on quad 499 at 328 km/h, park 4804 at (−172.683, 51.976) heading 0x031c, release 5248, clock 1349 → 1733, stops 2 → 1, five crew objects | the same | pit log (7 030 lines), race log (7 243), field log (56 240), start log, collision log: **identical** |
| Metropolis normal, its pit stop | trigger 2420 on quad 72 at 176 km/h, park 2678 at (−89.608, 310.439) heading 0xfff9, release 3122, clock 1802 → 2186, stops 2 → 1, six crew objects | the same | pit log (7 030), race log (7 292), field log, start log, collision log: **identical** |
| Diablo Canyon normal, line 6, 150 s | see the measures below | the same | pit log (7 030), race log (7 325), start log: **identical**; collision log identical but for the list id the TGP was asked for (1 452 of 3 663 lines, each the branch's = main's + 2: the cell's list moved 2 words, §8's data ROM row) |

Diablo Canyon's measures on both sets (`runner.race_report`, side by side): extensions 6 / 6, the clock never ran out, 1 lap / 1,
leader 741 road points (6.31 a second) / the same, 15 opponents moved / 15, largest backstep 0 / 0, cursor lead 3 / 3, parked
0 / 0, opponents at the origin 0 / 0; the time and checkpoint record addresses 0x284970 / 0x284b40 and 0x284df0 / 0x284fc0 (the
race blob moved + 0x1d0). Line 6 never meets the spot: the car came no nearer than 28.5 units to the trim's rectangle (frame
2204, at (−437.4, 49.6)) and never entered the pit lane (no pit handler in the log). So the measures could not differ through the
trim, and they do not differ.

**Two more compares, after the lead's rulings on Task 6's stop** (14 Nov; the same harness):
- **Pacific Coast normal, line 6, 150 s** (one of the courses whose collision moved in the TGP data ROM and that Step 1 had not
  raced. Chosen over Surfers Oval, which under this driver crawls on its inner verge and reaches no checkpoint (the race tests
  exempt it from the extension check), and taken before Surfers Road because its lists and quads moved by the same 0x10 words
  and its autopilot race fires checkpoints and keeps the whole field moving: a run that exercises the moved collision fully).
  Race log (7 321 lines), start log, pit log and collision log (3 676 lines) **identical**: the list ids the TGP was asked for are
  the same (offset 0: Pacific Coast's lists moved as a block, and a cell's list offset is relative to its block). The field
  (`runner.race_report` from the pool dumps; this harness takes no `fieldtrace.lua` log) the same: 4 extensions, the clock never
  ran out, 1 lap, leader 831 road points (7.08 a second), 15 moved, backstep 0, cursor lead 8, parked 0. The RAM dumps every 250
  frames differ only in four 32-bit words at work RAM 0x1948..0x197f, each a code-area address + 0x1d0 (the served record's tile
  table, race blob records and spawn list, relocated).
- **Alpine normal with its PIT START and first stop** (`out/p26/stage4/t6/alp6.lua`, `alp6.py`: `autoplay.lua` plus a log, from
  the race load, of the player's handler and pit state, every live pool object 0-8 every frame, and every word pushed from the
  figure routines with its object; 80 s, Alpine's normal pit path). PIT START: the pit handler from frame 1604 (pit states 6, 7,
  5) to 1922; the first stop 3596 → 4344. The log (15 121 lines: 6 090 object lines of the five work-state-1 crew records, 9 020
  pushes), the pit log (3 003 lines), the race, start and collision logs: **identical** on main's set and on this tree's.

**The attract cycle** (Review Focus 4; `out/p26/stage4/t6/attract6.lua`, `attract6.py`; standalone, no coin, no input, 420 s from
boot; the existing figure log, `figures_log.lua`, starts at a race load and does not cover the attract mode, so this scratch log
was written). It logs the mode byte's changes, the direction byte, every live object of pool objects 0-8 of `[0x501350]` on
every frame of the pit scene (mode 0x07: flags, record, x, z, root offset x and z, heading, walk heading, handler), and every word
pushed to the TGP from inside the figure routines (each set's own span of `figrootx` .. `figrot2`, logged as the offset from
`figrootx`: the four routines have the same sizes in both builds) with the pool object it was for.
- 10 pit scenes in 420 s (mode 0x07 from frames 2260, 3974, 6630, 9286, 11942, 13656, 16312, 18968, 21624, 23338, each 666
  frames); the direction byte 0 throughout.
- **The two logs are identical** (160 214 lines each): 53 280 object lines (objects 0-5, 7, 8), 106 560 pushes during the
  scenes (90 190 of them non-zero).
- **A finding against Task 5's reading.** Task 5 read that the attract pit scene uses its own records (0xfd718c, 0xfd736f and two
  of the start figures'). Measured: objects 5, 7, 8 hold 0xfd718c, 0xfd743b, 0xfd747f (0xfd736f was not seen), and **objects
  0-4 hold the five crew records of work state 1 (0xfd7033, 0xfd7078, 0xfd70bd, 0xfd7102, 0xfd7147)**, which `figmirror` holds
  for since Task 5 when the flag is set. With the flag 0 in the attract mode (`bankdemo` clears it at the attract's course loads)
  `figmirror` does not hold, and the identical logs show nothing changed. Read in the boot listing (fix wave, after the final
  review): the scene places those five by running work state 1's spawn itself, **0xfc007e `jsr FF27D8[PC]`**, not through a
  crew site (positions identical on both sets, so the scene was not reflected). The spawns' callers on the original are exactly
  the four sites, 0xff25c9 (PIT START) and 0xfc007e, pinned by `tests/test_direction.py::
  test_the_crew_spawns_are_called_only_from_the_known_callers` (direct transfers and 32-bit literals; a computed target is not
  covered). **A dependency (the lead's ruling): the attract pit scene stays the game's only while the direction flag is 0 in
  the attract mode (`bankdemo`).** It is pinned by `tests/test_dirscreen_build.py::test_the_flag_is_zero_whenever_a_select_screen_starts`,
  which leaves the flag at 1 after a reverse race and asserts it 0 on every frame of at least six attract pit scenes (mode 0x07),
  and, for the attract's course loads, by `tests/test_direction.py::test_the_attract_demo_never_loads_a_reverse_record`; both
  passed in Step 2's first invocation (§10).

## 9. The object at `[0x50138c]` (the spare tyres), measured

The question (found while reading for Task 5): the object the crew spawns activate (0xff4101 / 0xff4129; handler 0xff414c, placed
by `bsr FF4061` at 0xff4165, drawn by 0xff417b at world-axis offsets, one model 0x2e05d0 per flag bit 0-3: read as four spare
tyres) is placed at the host template's box, not the course's. Measured on this tree's set, normal Amazon Falls with its pit stop
(`out/p26/stage4/t6/tyre6.lua`: `autoplay.lua` plus a per-frame log of the object from the trigger; run
`out/p26/stage4/t6/runs/branch_amazon_tyre/`):
- `[0x50138c]` = 0x403800 (an entity), handler 0xff414c for its first frame, then 0xff417b. Its flags word: live (bit 31) with
  bits 0-3 set (0x8000000f) for the first 401 frames, then further bits of the low halfword set and cleared during the work
  (0x8000010f .. 0x80000fff .. 0x800000f0), then not live (0x000000f0) for the last 505 frames logged.
- **Its position: (0.0000, 0.0000, 0.0000)**, heading 0, on every frame logged: the world origin. Amazon Falls's host template is
  Bay Bridge (data index 0), for which 0xff4061 holds no box (formats §12): it leaves zeros. The course's box is (−172.683,
  3.109, 51.976): the object lies **180.4 units** from it (x + 172.7, z − 52.0 from the box).
- **On screen at the park + 150** (park 4804, snapshot at frame 4954:
  `out/p26/stage4/t6/runs/branch_amazon_tyre/snap/vr/0001.png`): no tyre model is seen (looked at by Task 6's implementer, not by Pascal); the crew stands round the car with
  their tools. The origin lies behind the camera's view there (the car faces +z at the box, the origin is 52 units behind it and
  173 to the side), so this snapshot cannot show it. Whether it shows at another moment or from another camera position was not
  checked.
- On the other courses (read, not measured): the Acropolis-template courses (Metropolis, Diablo Canyon) get Acropolis's box
  (−346.42, 3.70, −58.96), Alpine (Big Forest template) Big Forest's (−230.38, 30.00, −269.57), the four Bay Bridge-template
  courses the origin. Diablo Canyon's own box is (−346.00, −35.198, −100.96), 42 units from Acropolis's in z and 39 below it.
- Nothing was changed. It is older than this stage (both directions; the original Acropolis and Big Forest are correct). Open in
  `docs/follow-ups.md`.

## 10. Suite

**Step 2, the pins, first invocation** (as briefed: one invocation, a fresh seven-course conversion; log
`out/p26/stage4/t6/pytest.log`). It was not clean:

`source out/env.sh && .venv/bin/python -m pytest -o addopts="" -q -rfEX -p no:cacheprovider --basetemp out/p26/stage4/t6/pytest
tests/test_race_build.py tests/test_tgp_build.py tests/test_tencourse.py tests/test_directory.py tests/test_direction.py
tests/test_reverse_build.py tests/test_dirscreen_build.py tests/test_hudname_build.py tests/test_pit_build.py`

**7 failed, 252 passed, 1 xpassed, 33 errors in 6569.01s (1:49:29).**
- The 7 FAILED names are all on the known list (`docs/spike/2026-11-phase26-stage2-findings.md` §8):
  `test_race_build.py::test_the_player_pitch_is_smooth_on_diablo`,
  `::test_a_hard_steer_into_diablos_first_right_turn_meets_the_wall[at0]` and `[at1]`;
  `test_tgp_build.py::test_saturn_collision_drives_big_forest`, `::test_alpine_drives_in_the_big_forest_slot`,
  `::test_alpine_as_entry_three_drives`, `::test_each_new_course_drives_at_the_arcade_rate[2]`. The xpass is main's
  (`test_regenerated_big_forest_drives`).
- **33 ERRORs, not on the known list: every MAME test of `tests/test_pit_build.py`** (the normal and reverse stops of the seven,
  the plain reverse line, two stops and no third, the crew's three tests, Diablo Canyon's spot) errored in the setup of the
  `pit_runs` fixture with `KeyError: 'entry'` at `tests/test_pit_build.py:362`:
  `entry = item.callspec.params["entry"] if fixed is None and hasattr(item, "callspec") else fixed`. The fixture walks every
  item of the session and reads its `entry` parameter even when the item is not one of its own tests (`_KINDS` gives no kinds);
  an item of another module parametrized without `entry` (here `tests/test_race_build.py`'s `k`, among others) raises. In the
  stage's earlier invocations the other modules collected with `tests/test_pit_build.py` had no such item, so it never showed.
  It is a defect of the test harness (Task 4's fixture), not a product failure; it also concerned the whole suite. **Task 6
  stopped there** (the brief's STOP rule): in this invocation none of the pit tests ran.

**The fix** (the lead's ruling: in scope for Task 6, since Step 2 cannot pass without it): the wanted runs are computed by a
module-level helper `_wanted(items)` that takes only the items named in `_KINDS` and skips every other item without touching its
parameters; an item named in `_KINDS` without a fixed entry and without an `entry` parameter raises a `ValueError` naming it.
Unit test `test_the_wanted_runs_come_from_this_modules_tests_only` (stand-in items, no ROM): red on the fixture's own logic moved
into the helper unchanged (`KeyError: 'entry'`, `out/p26/stage4/t6/fixture_red.log`), green after the fix. Nothing else in the
module changed.

**Step 2, second invocation** (the lead's ruling: `tests/test_pit_build.py` with one static module that has a test parametrized
without `entry`: `tests/test_dirscreen.py`, whose `test_a_changed_site_is_refused[state0]` .. `[lock]` (parameters `site`,
`offset`) would have raised; it needs no MAME and no conversion; log `out/p26/stage4/t6/pytest2.log`):

`source out/env.sh && .venv/bin/python -m pytest -o addopts="" -q -rfEX -p no:cacheprovider --basetemp out/p26/stage4/t6/pytest2
tests/test_pit_build.py tests/test_dirscreen.py`

**58 passed in 789.89s (0:13:09)**: no error, no failure (the log, run with `-q`, gives the total only).

The eight other modules' result stands from the first invocation (7 failed, all known), made on the tree one commit older
(2e7883d; 0d904b1 changed only `tests/test_pit_build.py`). The lead's whole-suite run on the final
tree repeats the combined collection.

**The whole suite:** started by the session lead on the final tree (cfb5249; the merge commit adds documents only):
`source out/env.sh && .venv/bin/python -m pytest -o addopts="" -q -rfEX -p no:cacheprovider --basetemp out/p26/stage4/fullbt`
(log `out/p26/stage4/full.log`). **Still running when Pascal said to merge**; the merge was not held for it, on Pascal's
word (as stage 2's merge was made without the second drive). **Result, after the merge: 15 failed, 1138 passed, 1 xpassed, 50 warnings in 12870.77s (3:34:30).**
- The 15 FAILED names are exactly the 15 known on main (`docs/spike/2026-11-phase26-stage2-findings.md` §8), compared by name
  as sets (`out/p26/stage4/full_failed.txt` against `out/p26/stage3/full_failed.txt`): none new, none gone. No ERROR: the
  combined collection that errored in Task 6's first invocation is clean.
- The xpass is main's (`test_regenerated_big_forest_drives`); the 50 warnings are main's.
- Stage 3's run was 975 passed; the 163 more are this stage's tests.
- The tree the suite ran on (cfb5249) and the merged tree differ in documents only.

Earlier evidence runs of this stage (each task's one invocation): Task 1 125 passed (36 min) and, on the trimmed collision, the
twelve every-course collision tests with the budget test 15 passed, 2 failed (both known); Task 2 89 passed then 98 passed;
Task 3 67 passed (1:01:31); Task 4 41 passed, then 43 passed; Task 5 113 passed (17 min).

## 11. The playtest set

- **The set:** `out/p26play6` (`.venv/bin/vrtools build --roms "$VR_ROMDIR" --saturn "$VR_SATURN_CUE" --out out/p26play6`, at
  0d904b1, the fixture fix's commit; the tree differed from it only in this stage's documents; `build-report.txt` beside it;
  build log `out/p26/stage4/t6/play6_build.log`), not committed. The 38 files of its `vr.zip`, and its `m1comm.zip` and `model1io.zip`, are
  identical to Step 1's build of this tree (`out/p26/stage4/t6/branch/`).
- **Boots:** a headless 60-s run of `attract6.lua` on it (no coin, no input; `out/p26/stage4/t6/runs/play6_boot/`) reaches the
  attract mode: the mode byte reads 0x02 from frame 272, 0x03 from 276, then 0x06, the pit scene 0x07 from 2260, 0x08, 0x02, 0x03
  again, the same sequence and frames as Step 1's attract runs.
- **Launcher:** `out/rec159/launch.sh` (stage 3's `out/rec158` with the set changed to `out/p26play6`; inputs recorded to
  `out/rec159/inp/play.inp`). Run once windowed on Pascal's "launch it" (14 Nov): joystick found on the first try, 113 s of
  emulation at 100% speed, MAME exited 0, while the whole suite ran headless. Pascal's word afterwards: "excellent"; what they
  drove was not stated. How to race in reverse on it is stage 3's (`docs/spike/2026-11-phase26-stage3-findings.md` §9); a reverse pit
  stop is entered by driving into the pit lane at its normal exit.

## 12. Not verified

- **Pascal's drive of the stage's changes.** Pascal ran `out/p26play6` once for 113 s and said "excellent" (§11); not stated
  which course or direction, and too short to reach a stop by the race clock. Not confirmed by them: a reverse stop, Diablo
  Canyon in the normal direction through its lane, the crew's look on the screen, Alpine's reverse pair at the road's edge.
- **A human's line into the reverse entries** (the lane's normal exits): only the Lua autopilot. The fix wave measured the road's
  pit-side edge on Alpine and Metropolis (§15.3: the +8 line never stops; PIT WORK starts at the road's outer edge on Alpine and
  1.4-1.7 units beyond it on Metropolis) and entries off the lane's centre on Diablo Canyon and Pacific Coast (§15.4). Not
  measured: the road's edge on the five other courses (their pairs lie 16.8-21.1 from the centreline, the review's probe), a car
  cutting in late, entries wider than 7.7 units east on Diablo Canyon.
- **A human's line into the normal entries**, as before this stage.
- **A reverse stop in work states 8 and 11** on courses other than Amazon Falls: the fix wave ran both there, forced by the damage
  flags (§15.5); elsewhere they rest on the same code.
- **Put-back and the steering assist inside a lane in reverse**: not driven (they use the same turned direction as the race).
- **Diablo Canyon's trimmed spot** under the game's pit steering and under the Lua autopilot only (the lane's centre and 3 units
  west), no human, and through the rectangle in reverse only (the normal-direction run passes 0.1-3.1 units east of it: §15.2).
  The centre-line run does not discriminate the trim (it passed on main's build too); only the west run fails without it (now
  asserted on the lane's tarmac and at least 1.5 units west of the lane's centre; measured 4.24-4.53).
- **Linked play** (the linked pit autopilot 0xfe98f6 and its per-cabinet boxes): no reverse race in linked play (design §3).
- **Real hardware.**
- **The crew on three of the seven courses, and at the second stop**: the crew's position and animation tests
  (`test_the_crew_stands_round_the_car_in_reverse`, `test_the_crews_animation_is_mirrored_in_reverse`) cover Alpine, Amazon
  Falls, Diablo Canyon and Metropolis. Pacific Coast, Surfers Oval and Surfers Road in reverse rest on the same code and on
  contact sheets looked at by the lead only. The second stop's crew (a second spawn and reflection, Amazon Falls's long run) is
  not asserted.
- **What the TGP draws for the crew**: the logs show the words pushed through the figure routines and the stored positions, not
  the TGP's output; the vertical rotation and the heading push are not routed through a routine (only the stored heading + 0x8000
  is checked).
- **The image's remaining room**: 2 592 bytes below the gantry block; first-fit placement of the pictures was not simulated
  beyond the build succeeding.
- **Alpine's reverse road edge** (§15.3's STOP): kept as built by the lead's ruling; not confirmed by Pascal on a drive.
- **The nine pins modules after the fixture fix**: they ran together only in the first invocation, in which every MAME test of
  `tests/test_pit_build.py` errored at setup; the pit tests' clean run was with `tests/test_dirscreen.py` only (§10). The combined
  collection is first repeated by the lead's whole-suite run.
- **Pacific Coast, Surfers Oval and Surfers Road in the normal direction against main**: Pacific Coast raced (§8); the two Surfers
  courses only by the ROM decode (their collision identical at moved addresses).
- **Trigger depths from the reverse entry** were not computed (Task 4's "to box" is a straight distance); the pairs' depths of §3
  are quad centres along the lane.
- **The second reverse stop's checkpoints** (P6's extension rule after a reverse stop) were not checked against the records.
- **The object at `[0x50138c]`** on screen at moments other than the park + 150, and on the other courses (§9).
- **Lap time with a reverse stop** against a normal one.
- **The Oval's wall and grass quads under its lane polyline** (the recon's §10: walls 1514-1516 at 112-123 units from the Oval's
  forward mouth; grass on six lanes): not driven by a human; the Lua runs passed.

## 13. Review items parked, open

From the task reviews (the ledger's "Parked minors" lines). **The fix wave (§15) fixed** the zero-trim message, the copied build
path (one shared builder), Task 2's three, Task 3's two, Task 4's side check, centre-run docstring and west-run assertion, and
Task 5's two docstrings. **Left as they are** (listed in `docs/follow-ups.md`): the trim's piece merge, the session's
registration when a prefetch fails outside `_make`, the set without pits shared by every `pit_runs` test, the `smoke` field
duplicating the race log's jolts, `figmirror` as a table loop. The list below is as it stood before the fix wave.
- **Task 1:** the zero-trim `ConvertError`'s message could name the late wall drop as a cause; the trim's piece merge (a convex
  remainder can come out of the subtraction as two pieces, which raises: Diablo works by its corner order; first review Minor 1);
  the build path copied in two test helpers (`_diablo_trim_builds` in `tests/test_convert_collision.py`, `_pit_builds` in
  `tests/test_convert_reverse.py`; a shared builder in `tencourse` would remove the copies).
- **Task 2:** `pytest.raises(ConvertError)` without `match` in `test_no_pair_with_the_run_is_refused`; a 160-character docstring
  line in `vrtools/convert/reverse.py` (about line 393); an import inside a test body (about line 162 of
  `tests/test_convert_reverse.py`).
- **Task 3:** the "bad" case `pit_quad=30` of `tests/test_directory.py` (lines 466-469) is now refused for another reason (it has
  no box): a comment or drop it; a comment split at `directory.py` lines 189-190.
- **Task 4** (`tests/test_pit_build.py`): the spot test's side check is unsigned (about line 548); the west run's margin 1.54 of
  2.0 (a possible flake: loosen to the lane's geometry or assert on the distance to the lane's centre); the centre run at lookahead
  3 proves only "clean on the trimmed set" (say so in its docstring); the session's registration when a prefetch fails outside
  `_make`; the set without pits shared by every `pit_runs` test; the `smoke` field duplicates `race_log.lua`'s jolt lines.
- **Task 5:** stale docstrings in `direction.py` (`direction_routines`, lines 948-949, and the Task 13 paragraph still name the
  figures' records where `MIRRORED_RECORDS` is meant); the records test's docstring (it finds 32-bit literal references only; the
  records sit in a 0x45-stride table, so a computed reference would escape it); `figmirror` as a table loop (about 90 bytes) if
  room gets tight; the commit message's "within 0.0001" is the measured worst, the asserted tolerance is 0.05.

## 14. Status

- Built and measured as above on branch `phase26-stage4`: Tasks 1-5 (commits 888afff, 1b5ddeb; 5413d17, aa851d1, 56f182b;
  f159d6d; 0f331ad, 8a0b20e; 2e7883d), Task 6's fixture fix (0d904b1) and this record. Not merged, not pushed. Playtest set
  `out/p26play6` (§11).
- Against main: a normal Amazon Falls and a normal Metropolis race with their pit stop give main's pit, race, field, start and
  collision logs; a normal Diablo Canyon race on line 6 gives main's race and pit logs (line 6 never meets the trimmed spot); the
  attract cycle's ten pit scenes give main's log; after the lead's rulings also a normal Pacific Coast race on line 6 (its
  collision moved in the TGP data ROM) and Alpine's PIT START with its first stop give main's logs. The ROMs differ as §8 lists; the TGP data ROM also holds four other courses'
  unchanged collision at moved addresses (a finding against the plan's wording).
- **Not driven by Pascal.** What they are asked to drive (`docs/follow-ups.md`): the seven reverse stops, and Diablo Canyon in
  the normal direction, pit lane included (the trim changes the normal race's collision there).
- The whole suite: the session lead's run after this task (§10).
- **The fix wave after the final review** (§15): C1, I1, Minors 1-8 and the parked text minors fixed; the road's pit-side edge,
  entries off the lane's centre and work states 8 / 11 measured headless; one STOP (Alpine's reverse pair at the road's edge,
  §15.3), ruled by the lead: kept as built; the set built from the wave's tree is byte-identical to `out/p26play6`.
- **Merged and pushed, 14 Nov 2026,** on Pascal's "excellent, merge update md commit and push": main fast-forwarded from
  1216442 to this record's commit (stage 4's 28 commits and this one); branch `phase26-stage4` kept locally. The whole suite was
  still running (§10); it ended after the merge with the 15 known failures only (1138 passed).


## 15. The final review and the fix wave

The final whole-branch review (1216442..5c72ac9, `.superpowers/sdd/2026-11-14-reverse-stage4-pit-stops/final-review.md`): "With
fixes", one Critical (C1), two Important (I1, I2), nine Minor. One fix wave answered it (the lead's ruling; brief `fix-wave-brief.md`
in the same directory). No product behaviour changed: the set built from the wave's tree is byte-identical to `out/p26play6`
(§15.6). Nothing in this section was driven by Pascal; every run is headless, the Lua autopilot or the game's pit steering.

### 15.1 Each review item, what was done

| item | what was done |
|---|---|
| C1 (a log excerpt as a fixture) | `test_parse_pit_log_reads_the_player_and_the_crew`'s lines and expected `PitFrame`s replaced by invented values (only the two handlers, game addresses, kept). Every other literal log line added in `tests/` on this branch (`git diff 1216442..HEAD -- tests`): the crew-draw parser test's four `D` lines, compared against every `crew.txt` under `out/p26/stage4/` (62 files): they occur only in that test's own tmp files (invented). Other literal numbers added on the branch are converter outputs (the pinned pairs, boxes and the pair-direction bound) or synthetic geometry, not logged values. The excerpt stays in the unpushed commits 0f331ad..5c72ac9 (the lead's ruling: put to Pascal with the merge question). |
| I1 (the attract pit scene) | Read in the boot listing and in unidasm's listing of the original boot ROM: **0xfc007e `jsr FF27D8[PC]`**: the scene runs work state 1's spawn, so its objects 0-4 hold `CREW_RECORDS[:5]`; it stays the game's because the flag is 0 there (`tests/test_dirscreen_build.py::test_the_flag_is_zero_whenever_a_select_screen_starts`, `tests/test_direction.py::test_the_attract_demo_never_loads_a_reverse_record`). Corrected in `direction.py`, `tests/test_direction.py` (comment and the records test's docstring), the formats note §20 and §8 above. New static test `test_the_crew_spawns_are_called_only_from_the_known_callers`: every byte of the original program and boot ROMs read as a possible direct transfer (`bsr`, 8- and 16-bit branches, `jsr` / `jmp` PC-relative by 8/16/32 bits or absolute) and every 32-bit literal of a spawn address: exactly the four sites, 0xff25c9 and 0xfc007e (red with 0xfc007e left out). Not covered: a target computed at run time. |
| I2 (Review Focus 3 on the road's edge) | `test_the_pit_side_edge_line_never_stops` (Alpine, Metropolis: road line 4, +8) and the scratch measure beyond it: §15.3. **STOP on Alpine** (§15.3). |
| Minor 1 (the trimmed spot, normal direction) | `test_the_trimmed_spot_is_passed_in_the_normal_direction`: §15.2. |
| Minor 2 (crew coverage) | §12 and the follow-ups say it. |
| Minor 3 (attribution) | "Pascal's decision P2" / "(Pascal, P1)" in code comments and the plan's Decisions heading now say "the lead's reading of Pascal's 'Ok'"; the two "Ok b" attributions in `collision.py` stay. |
| Minor 4 (the recon's "nothing drawn") | A dated correction under the recon's §4 table. |
| Minor 5 and the parked copied build path | One shared builder moved out of `convert_course` unchanged: `tencourse.course_placement` and `tencourse.course_collision` (a `CourseCollision`), used by `convert_course`, `_pit_builds`, `_diablo_trim_builds` and `pitpaths.pit_lane`; `collision.wall_trim_of(sat)` is the one course-key lookup of a named spot (also used by `tests/test_pit_build.py`). The set built afterwards is byte-identical to `out/p26play6`. |
| Minor 6 (the number a spot trims) | `PIT_LANE_WALL_TRIMS` maps the key to `WallTrim(rect, quads)` (Diablo: the same rectangle, 1); `trim_walls_off_the_lane(..., quads=)` raises `ConvertError` on another number, as on none; the zero-trim message names the late wall drop as a possible cause. Unit test red then green. |
| Minor 7 (entering off the lane's centre) | `test_a_reverse_stop_entered_off_the_lanes_centre`: §15.4. |
| Minor 8 (the partner quads) | `test_both_reverse_pair_quads_face_the_reverse_lane`: both quads of each pair, their direction turned half a turn, within 90° of the reverse lane direction. Measured worst 32.0° (Diablo Canyon 59; 58 23.8°, Amazon Falls 14.3° / 11.7°, Metropolis 9.9°, the others 2.2° or less; scratch on Task 2's cached conversions, whose tarmac the trim does not touch). |
| Minor 9 (nits) | Left; in the follow-ups. |
| Parked minors (§13) | Fixed: Task 2's three, Task 3's two, Task 4's three named in the brief, Task 5's two docstrings, the zero-trim message, the copied build path. Left (follow-ups): the trim's piece merge, the session's registration when a prefetch fails outside `_make`, the set without pits shared by every `pit_runs` test, `smoke` duplicating the race log's jolts, `figmirror` as a table loop. |
| Work states 8 and 11 (not verified before) | §15.5. |

### 15.2 The trimmed spot in the normal direction (Minor 1)

The normal Diablo Canyon run (`test_a_normal_pit_stop`'s, on the lane's polyline after the release) passes the spot's z band
(31.0..43.5) at frames 7055-7109, 236-242 km/h, on the lane's centre (0.01 units off it) and **0.14-3.07 units east of the
rectangle**: it never enters the trimmed footprint, so it says nothing about the trim; no wall hit from 20 units of z before the
band to 20 after. Which runs pass the spot: through the rectangle, **only reverse runs**: the game's pit steering in
`test_a_reverse_pit_stop` (within 2 units of the lane's centre) and the Lua autopilot's two spot runs (the centre line, 0.71-1.22
units west of the lane's centre; the west line, 4.24-4.53 units west, on the lane's tarmac). In the normal direction only beside it.

### 15.3 The road's pit-side edge in reverse (I2; the lead's ruling 4's "dearer fault")

**The test** (`test_the_pit_side_edge_line_never_stops`): a reverse race on road line 4 (`AI_OFFSETS[3]` = +8, right of the normal
direction), which on both courses is the outermost line on the lane's side at the normal exit (line 1, −8, lies on the far
side), read backwards. Alpine: the car passes the exit twice, never on the pair, no stop, +0x1bf 2 to the end; its centre comes at
most 11.3 units from the centreline within 60 units of the pair (the pair's nearest corner is 11.84 from it). Metropolis: the same,
no stop (pair's nearest corner 9.88 from the centreline).

**The measure** (scratch, not asserted: `out/p26/stage4/fix/scratch/edge_measure.py`, `edge_analyse.py`, runs under
`out/p26/stage4/fix/edge/`, on a copy of `out/p26play6` with Task 2's cached collision for "what is under the car"; the set is
byte-identical to this tree's, §15.6). The path is the centreline moved toward the lane by an offset near the pair (fully within
80 units along the road, then a 60-unit ramp), in steps of 1 unit; the car does not hold its path exactly (it ran up to 2.9 units
wide of it at speed), so the numbers below are **the car's own centre**, measured from the centreline, on the logic frame whose
lap-position quad the trigger tested.

| course, direction | no stop (the most toward the lane) | PIT WORK starts | what is under the car's centre there | the road slice's edge there |
|---|---|---|---|---|
| **Metropolis, reverse** (pair 86, road point 61, normal exit at point 63) | 8.3 (road line 4) | 10.5 units from the centreline (path +8); 11.9-16.6 on the wider paths | lane quad 86 only (the lane mouth's tarmac); quad 86 begins 10.3-10.8 out; between it and the road slice no collision quad (a 1.2-1.7-unit strip) | 8.8-9.1 from the centreline: **PIT WORK starts 1.4-1.7 units beyond the road's edge**, not on the road |
| **Alpine, reverse** (pair 251's side, road points 207-209, normal exit at 209) | 13.1 (path +10); 11.3 on road line 4 | 13.8 units from the centreline (path +11); 14.9-16.9 on the wider paths | **on the seam**: 0.04 units inside lane quad 251 and 0.016 inside road quad 255, which overlap by about 0.1 unit; the road slice and the lane mouth meet with no gap | 13.7-14.6 from the centreline along points 207-210, and lane quad 251 begins at the same distance: **PIT WORK starts the moment the car's centre reaches the road's outer edge**, 5.8 units beyond road line 4 |
| Metropolis, normal (pair 71, road point 52, mouth at 50; the pair Pascal drove in Phase 22) | 10.5 (path +2) | 13.5 units from the centreline (path +4) | lane quads 71 / 72 (they begin 12.35 out); a wall quad stands between the road and the lane there, and the car hit it on its way in (smoke 26 at the trigger: the autopilot ran wide at the bend before the mouth) | 8.2: PIT WORK starts 5.3 units beyond the road's edge, past a wall |

**STOP (Alpine; the brief's rule "a stop starts with the car's centre on the road's own slice").** On Alpine the reverse pair's
quad 251 begins where the road slice ends; on the tested frame the car's centre lay inside both road quad 255 and lane quad 251,
in their 0.1-unit overlap, 13.8 units from the centreline. Whether that is "on the road" is for the lead (or Pascal); nothing was
changed. On Metropolis the stop starts on the lane's own quad, beyond the road slice: no stop of the item there.

**The lead's ruling on the STOP (14 Nov, after the fix wave): kept as built.** The car's centre must reach the road's outer edge
on the pit side, 5.8 units beyond the outermost AI line, before PIT WORK starts; Alpine's normal pair lies about as near the road
(11.6 from the centreline, the review's probe) and was driven in Phase 22. Put to Pascal in chat with that recommendation and the
alternative (the pair one quad deeper into the lane, a small change); they did not rule on it, and said to merge.

### 15.4 Entering the reverse lane off its centre (Minor 7)

`test_a_reverse_stop_entered_off_the_lanes_centre` (`shift_path`: the reverse pit path moved across the lane about the pair's
middle, fully within 40 units along it, then a 30-unit ramp; "+" is the lane's road side, "−" the garage side). The reverse pit path
itself wanders about 2 units either side of the lane's centre, so the car's offset at the trigger differs from the shift; the
table gives both. Every stop completed as `_assert_a_stop` checks (the trigger on the first frame on the pair, parked within 0.01
at the box, 444 frames of work, +384 on the clock, one stop spent), the car's centre stayed on the lane's tarmac from the trigger
to the park, and no wall was hit (the smoke counter never rose from 0) from the trigger to the park. Invocation
`out/p26/stage4/fix/pytestB.log` (and again in §15.6's).

| course, run | shift | the car at the trigger (from the lane's centre) | the lane's tarmac at the pair's middle (road / garage side) | speed | the pit steering's most off the straight line to the box |
|---|---|---|---|---|---|
| Diablo Canyon, 3 toward the road | +3.0 | +3.06 | 11.5 / 11.8 | 323 km/h | 0.17 |
| Diablo Canyon, 3 away from it | −3.0 | −1.96 | | 323 | 0.09 |
| Diablo Canyon, widest toward the road | +9.5 | **+8.50** (x −407.1, z 76.4) | | 323 | 0.47 |
| Diablo Canyon, widest away from it | −9.8 | **−7.74** (x −391.7, z 82.7) | | 303 | 0.41 |
| Pacific Coast, 3 toward the road | +3.0 | +0.54 | 9.65 / 9.65 | 322 | 0.04 |
| Pacific Coast, 3 away from it | −3.0 | −4.38 | | 322 | 0.26 |

On Diablo Canyon the road side is the lane's west side. The review's model put a wall in the straight run from trigger points
more than about 8 units to one side, near (−384, 61), east of the lane: the garage (east) side's widest run reached 7.74 units, so
a car entering farther east than that was not driven. A scratch try that moved the path to a line at the offset (instead of by
it) dragged the path's road points before the exit too and the car missed the stop; the test keeps the shift.

### 15.5 Work states 8 and 11 in reverse (item 13)

Read in the boot listing at the trigger, 0xff222f: `mov.w 1AB[R25], R0; and.w #F, R0`: +0x1ab & 0xf = 0 gives state 1; else & 3 =
0 state 11 (0xb); else & 0xc = 0 state 8; else 14 (0xe) (the player's damage flags; Metropolis's normal stop had bits in 0xc only,
its reverse stop in both pairs). pit_log.lua's `VR_PIT_DAMAGE` writes a byte there on every frame from the green to the trigger:
1 gives state 8, 4 state 11 (scratch first: Amazon Falls normal, no poke state 1 with 5 crew objects, 1 → 8 and 4 → 11 with 6, the
trigger frame unchanged). The two crew tests got the cases Amazon Falls `reverse_s8` against `normal_s8` and `reverse_s11` against
`normal_s11`: work state 8 / 11 in both runs, six objects; every 20 frames from the park to the release each object stands at the
reference's reflected through the box, largest difference 0.0001 units over 23 frames, heading + 0x8000; on every frame the
pushes through the figure routines are the reference's negated (1 332 keys; non-zero pushes per routine, state 8: 1 114 / 1 003
/ 507 / 663; state 11: 1 118 / 1 028 / 763 / 585). So `crewturn8` and `crewturn11` with the flag set and the records 0xfd71d1,
0xfd7ad5, 0xfd7b1a now ran; on Amazon Falls only (the other courses' states 8 and 11 rest on the same code).

### 15.6 The invocation and the ROM comparison

- **The ROM comparison:** `.venv/bin/vrtools build --roms "$VR_ROMDIR" --saturn "$VR_SATURN_CUE" --out out/p26/stage4/fix/set`
  from the tree at 5fd8568 (the wave's product code; later commits touch tests, the Lua harness and documents only): every member
  of `vr.zip` (38), `m1comm.zip` (2) and `model1io.zip` (3) is byte-identical to `out/p26play6`'s. `out/p26play6` stays.
- **The invocation** (`source out/env.sh && .venv/bin/python -m pytest -o addopts="" -q -rfEX -p no:cacheprovider --basetemp
  out/p26/stage4/fix/pytest tests/test_pit_build.py tests/test_mame_runner.py tests/test_direction.py tests/test_directory.py
  tests/test_convert_reverse.py tests/test_convert_collision.py tests/test_reverse_build.py tests/test_dirscreen.py`, at d388412;
  log `out/p26/stage4/fix/pytest.log`): **5 failed, 455 passed in 5640.32 s (1:34:00)**. The five FAILED names, all in
  `tests/test_convert_collision.py` (`test_ai_lines_run_on_tarmac_on_every_course`,
  `test_metropolis_upper_deck_takes_no_height_from_the_deck_below`,
  `test_no_hole_between_the_centreline_and_the_wall_on_every_course`, `test_slice_quads_overlap_along_the_road`,
  `test_verges_never_overlap_the_tarmac_on_every_course`), are a subset of the known list (`out/p26/stage3/full_failed.txt`,
  15 names; stage 2 findings §8): compared as sets, no name outside it; the ten other known names are in modules not run here
  (`test_convert_geometry`, `test_convert_profile`, `test_race_build`, `test_tgp_build`). Every test of
  `tests/test_pit_build.py` passed (the B runs' numbers above are from `out/p26/stage4/fix/pytestB.log`, run with `-s`; this
  invocation ran `-q`).

### 15.7 Drive notes (for Pascal's drive; measured headless, never driven by a person)

- **Metropolis in reverse, past the normal exit on the pit side** (road point 61-63): PIT WORK starts once the car's centre is
  about **10.3-10.8 units from the centreline**, on the lane's quad 86, which is 1.4-1.7 units beyond the road's edge (the road
  slice ends 8.8-9.1 out). The outermost AI line (+8) passes at 8.3 without a stop. A car kept on the road does not stop; one
  whose centre drifts 1.5 units off the road's edge toward the lane does. Its normal pair (the one driven in Phase 22) needs the
  car 13.5 out, past a wall.
- **Alpine in reverse, past the normal exit on the pit side** (road points 207-209): PIT WORK starts the moment the car's centre
  reaches **the road's outer edge, about 13.7-14.6 units from the centreline** (5.8 beyond the outermost AI line, which passes at
  11.3 without a stop): the lane mouth's tarmac (quad 251) begins exactly where the road slice ends. Open question (§15.3's STOP).
- **Entering wide** (Diablo Canyon, Pacific Coast): entries 3 units either side of the lane's centre, and on Diablo up to 8.5
  units toward the road and 7.7 away from it, all stopped and parked with no wall hit. Farther than 7.7 east on Diablo was not
  driven (the review's model shows a wall in the steering's way from about 8).
- **The trimmed spot on Diablo Canyon by hand, both directions:** driven through the rectangle only in reverse (the game's pit
  steering, and the autopilot on the lane's centre and 3 units west of it); the normal-direction run passes 0.1-3.1 units east of
  it on the lane's centre. A normal-direction pass through the lane's west half, where the old wall stood, was not driven.
- **A stop after wall damage:** damage flags pick another crew (work states 8, 11, 14). States 8 and 11 now ran in reverse on
  Amazon Falls with the crew turned correctly; 14 ran on Diablo Canyon and Metropolis (Task 5). Not run on the other courses.
