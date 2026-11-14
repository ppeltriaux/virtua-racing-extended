# Phase 26 stage 1: findings

The measured findings of stage 1 of `docs/superpowers/specs/2026-11-11-reverse-courses-design.md` (a reverse race on Metropolis behind a debug flag). Facts and numbers only.

**Map** (the plan's order; the sections keep the numbers other documents cite):
- §1 the flag cell;
- "The first reverse race (Task 8)", unnumbered: the measurements that §2, §3 and §6 use;
- §2 opponents against the quads' direction (recon §7 item 2);
- §3 the start line;
- §4 the six values of TGP 0x1500 (recon §7 item 1);
- §5 the Big Forest template's pose sites and bit 0x1e (recon §7 item 3; read, not run);
- §6 the numbers, normal against reverse;
- §7 open after stage 1;
- §8 the verdict.

The plan and its Task 13 say "recon §6" for the open list: since the recon gained its corrections section, that list is its §7.

## 1. The flag cell

**Cell: `course.DIRECTION_RAM = 0x502294`** (one byte used: 0 normal, 1 reverse; the test taps its whole word 0x502294..0x502297).

Chosen as the lowest 4-aligned address in 0x502280..0x50235c, outside 0x502328..0x50232f, whose four bytes have no read and no write event in either tap run (so the padding neighbours the brief named first, 0x5022f8 and 0x502330, were not needed).

Two tap runs on the Phase 25 build (`out/p25play2`), `memtrace.lua` with `VR_TRACE_FINE=1`, `VR_TRACE_FROM=20`, reads on 0x502280-0x50235f, 0x2fce00-0x2fffff, 0xfdc844-0xfdffff and writes on 0x502280-0x50235f:

| run | script | emulated | last frame logged | R/W events in 0x502280..0x50235f | events on 0x502294..0x502297 |
|---|---|---|---|---|---|
| A | attract (`memtrace.lua`) | 240 s | 13 805 | 132 958 R, 120 W | 0 |
| B | `autoplay.lua`, `VR_WHEEL=150` (entry 6, Metropolis), autopilot on Metropolis line 0 | 330 s | 18 981 | 161 914 R, 90 W | 0 |

- Touched words in the block: 0x502280..0x502292 (read), 0x5022a4..0x5022aa (R+W), 0x5022b0..0x5022c2, 0x5022d4..0x5022f2, 0x502304..0x502322 (map record copy: 0x50231c/e written), 0x502328..0x50232e (written 12 times in A, 9 in B: our own map-cross and off-course cells; the game's read count there is 1 and 750 in B), 0x502334..0x502352. Everything else, including 0x502294..0x5022a3 and 0x5022ac..0x5022af, has no event.
- Every write in the block comes at frames 273..13 654 (A) and 273..18 378 (B), the first at frame 273 after the course-load; none falls between frames 20 and 272.
- Tap note: the brief's `fdc845-fdffff` read range is not 4-aligned and MAME rejects it (`start address has low bits set`); 0xfdc844-0xfdffff was used.

**Boot (frame 0 on, run C: `out/p25play2`, 20 emulated s, `VR_TRACE_FROM=0`, read and write taps on 0x502294..0x502297, RAM dumps at frames 1, 100, 500, 1100).** The cell is written twice during boot and read by nothing but the tracer's own dumps:
- frame 0: one write per half-word (0x502294, 0x502296) by PC 0xfe1469, the same PC that writes 0x501138 and 0x50113a at frame 0 (the boot's RAM clear);
- frame 9: one write per half-word by PC 0xff9bb1 (a second clear);
- nothing else writes it through frame 1100. The only read events (frames 2, 101, 501, 1101, PCs 0xfe1469..0xfe13e7, two per half-word) are one frame after each dump: they are `read_range` in memtrace.lua running under the tap, not game reads (the same count of reads appears at each dump frame and at no other).
- The tap does not log values. The value is read from the dumps instead: bytes 0x502294..0x502297 are 00 00 00 00 at frames 1, 100, 500 and 1100, so after both boot writes (the later at frame 9) the cell is 0 and stays 0. **0 at power-on is shown.**
- Consequence: the game does write the cell at boot (two clears, frames 0 and 9, before the trace window of 20 that runs A and B used); from frame 10 to the end of run D below it has no event at all.

**A race to game over (run D, 330 emulated s, 18 981 frames: `autoplay.lua`, `VR_WHEEL=150`, Metropolis autopilot, `VR_TRACE_FROM=0`, read and write taps on 0x502294..0x502297 and write tap on 0x501138..0x50113b).** The cell has 4 events in the whole run: the two boot writes of run C (frames 0 and 9, PCs 0xfe1469 and 0xff9bb1) and none after frame 9. The mode byte 0x501139 is read from RAM dumps of an identical second run with no taps (run E; both runs have 18 981 frames): 0x00 at frame 240, 0x03 at 480, 0x10 (select) at 720, 0x12 at 1680, 0x14 (race) at 1880 and still at 10 880, 0x1c at 10 900, 0x03 (attract) at 11 360, then attract modes 0x07/0x03 until frame 18 960. The mode-byte writes of run D agree (non-per-frame PCs): 0xfe46a3/0xfe4705 at frames 1861/1863 (to the race), 0xfe48ad, 0xfe49c3, 0xfe4a7c, 0xfe4c9a at frames 10 889..10 895 (leaves 0x14), 0xfe4cb4, 0xfe6563, 0xfe6660, 0xfe2530 at frames 11 345..11 351 (to attract). So the race runs frames ~1 861..10 889 (about 157 s), the end-of-race screens until frame ~11 350, and the remaining ~7 600 frames are the attract mode again; the direction cell is silent over all of it.

For stage 2 only (recon §7 item 5): 0x2fce00..0x2fffff **is** read, in both runs identically, by one reader (PC 0xfe6b64): 6 400 read events (2 048 each on pages 0x2fd, 0x2fe, 0x2ff, 256 on page 0x2fc), all in frames 266..268, nothing afterwards. 0xfdc844..0xfdffff was **not** read in either run (0 events).

The test `tests/test_direction.py` repeats the check on the original arcade set: 120 s attract and 120 s Big Forest race, no R or W event on 0x502294..0x502297 in either.

## The first reverse race (Task 8)

Two 150-s races of entry 6 in one pytest session (`tests/test_reverse_build.py`, one seven-course conversion, logs under `out/p26/run1`), the autopilot on the drive line (read backwards in reverse), the race, edge and field logs and the RAM dumps; the put-back runs 120 s each. The race window is the stretch from the first frame the clock counts down (frame 1866 in both) to the end of the run (frame 8630: the clock never ran out), 117.6 s. The reverse run's numbers were the same to the unit in a second session (the emulation is deterministic for one build and one input script).

| | normal | reverse |
|---|---|---|
| player laps (wraps, lap byte 0 → 1) | 1 (frame 5653) | 1 (frame 5869) |
| extensions (in order, at road point, gain in 1/32 s) | 5: 126/335, 224/255, 1/380, 126/335, 224/255 | 5: 144/380, 241/255, 0/335, 144/380, 241/255 |
| opponents moved ≥ 100 points / parked / largest backstep | 15 / 0 / 0 | 15 / 0 / 0 |
| leader's gain, slowest opponent's gain (points) | 833, 509 | 849, 537 |
| cursor lead, largest (dumps / field log every 2nd frame) | 5 / 7 | 6 / 7 |
| wraps: opponents that crossed the line (twice) | 15 (5) | 15 (7) |
| steps back over the line; wraps without the lap byte rising by one | 0; 0 | 0; 0 |
| jolts in the window (cars with one) | 65 (15) | 26 (8) |
| frames on point 364 per crossing, all cars (field log, 2-frame resolution): median, range | 10, 8-16 (21 crossings) | 12, 8-16 (23 crossings) |
| the same for the player (race log, per frame) | 8 (1 crossing) | 8 (1 crossing) |
| attribute at `+0xeb` = its quad's direction (+0x8000 in reverse), E lines in the window | 54 180 of 54 180 | 54 186 of 54 186 |
| wrong-way warning read in the race window | 0 frames | 0 frames |
| put-back: yaw minus 4 × the raced line's heading, 60 frames after the counter returns to 0 | −0x8e | +0x1cd |
| put-back: nearest to the raced line within 400 frames; road point risen | 0.5 units; 22 | 0.3 units; 18 |

Tests failed: none (13 of 13 pass). In the first session the two put-back cases failed with the plan's steer (point 60, wheel 20, 350 frames): no put-back in either direction (off-course counter at most 18 normal, 5 reverse; see the put-back note below); the tuned steer passes in both. No bound was changed.

Notes on the measurements:
- **Frames.** `race_log.lua`, `edges_log.lua` and `steer_at.lua`'s log count frames from 1 at the first frame end; `fieldtrace.lua` samples from 0 (its frame f is the race log's f + 1); `memtrace.lua`'s events and dumps and `autoplay.lua`'s race start are numbered during the frame (the race log writes the same frame as one more). The tests join the field log to the race window with that one-frame shift.
- **E lines.** Each line now ends with two decimal columns: the frame of the 0x1500 snapshot (quad, x, z, the six words) and the frame of the attribute snapshot (attr quad, attr). In the window 68 (normal) and 74 (reverse) lines of about 54 000 carry edge values from an earlier frame (an attribute store with no 0x1500 call that frame). **Tasks 9 and 10 use only the fresh lines (`EdgeSample.fresh`: edge frame == frame) for the six values**; the attribute pair is consistent on every line (each store snapshots its own quad). The attribute is the halfword at `+0xeb..+0xec` (the game's stores are `mov.h`); the Task 7 loggers read one byte of it, corrected here in both `edges_log.lua` and `race_log.lua`.
- **Jolts.** The window is 117.6 s of race, not 150 s; Phase 25's 57 (a different tool, the same counter) is the order of this session's 65. Normal: 17 at points 40-59 and 22 at points 180-199, the rest spread; reverse: at most 6 in any 20-point stretch.
- **The wrong-way warning.** Boot 0xff4c9e checks on 8 of every 16 logic frames (bit 3 of the logic-frame counter 0x501144) whether the yaw is within 0x800 of opposite the quad's direction; if so it draws the tile map 0x2F4D36 when `[0x40DC9B]` is 0, or else prints the string "REVERSE" (boot 0xFF4D0F). On this set it takes the string path: in a 60-s positive control (the reverse variant with the flag held at 0 from the race on, so the car drives the reversed tables against its quads' authored direction) the check passes on 278 frames, the string is read by 0xff871e on each, and the tile map is read only by the boot's copy routine (0xfe6b64, frame 258); with the flag 1, on no frame. Committed after the whole-branch review as `test_the_wrong_way_warning_is_read_when_the_game_sees_the_car_against_its_quads` (`direction_off.lua` writes the 0 from mode 0x14 on; the floor is 50 frames of the string in the race window, and none of either range with the flag 1). The tests tap both the tile map and the string. A probe of the tile map alone (the plan's) sees nothing in either case.
- **Put-back.** Metropolis's walls stand 0-9 units past the tarmac's edge all round the lap on both sides (the surface kinds of the slot-6 quads sampled across the road at every drive-line point), and a car driven at them is turned back onto the road by the wall code before the off-course counter reaches 128: over 35 holds (18 at 17 points normal, 17 at 13 points reverse; wheel 20, 128 or 236; 150-350 frames) the counter reached 128 twice, both on the run-off around (−270, −478) beside forward points 330-334 (reversed 31-35): normal from point 330 with the wheel at 236 for 200 frames, reverse from point 22 with the wheel at 20 for 350 frames. These are the tests' steers. The put-back's turn shows on the attribute: 0x22fc there in the normal direction, 0xa2fc in reverse, and the yaw follows it.

## 2. Opponents against the quads' direction (recon §7 item 2)

With the direction half (0x1800) corrected and the 0x1500 values as authored for forward travel, the reverse field races:
- All 15 opponents travel the reversed lap: each gains 537-849 road points in the 117.6-s window (normal 509-833), none parks, no dump shows an opponent's progress going back (largest backstep 0 in both), 7 opponents cross the line twice (normal 5).
- Every opponent's attribute store gives its quad's direction plus half a turn (all 54 186 E lines in the window, cars 0-15), so the opponents' handler (0xfea881..0xfeab30) stores the reversed direction at `+0xeb` as the player's code does.
- Off-tarmac jolts (an opponent's smoke counter rising from 0): 26 in reverse against 65 in the normal race of the same session, on 8 opponents against 15. The normal race's two clusters (points 40-59 and 180-199) do not appear in reverse at the same places (reversed 306-325 and 166-185 hold 2 and 3).
- No disturbance of the opponents outside the put-back and spin paths shows in these measures with the six 0x1500 values uncorrected. What those values do in reverse is Task 9's question; the field and jolt tests are green before it.

## 3. The start line

- Every car's every crossing in the reverse race (23 crossings: the player once, every opponent once, 7 of them twice) wraps the road point from the top to the bottom of the lap with the lap byte rising by exactly one, and no car steps back over the line; the normal run's log satisfies the same form (21 crossings). The largest cursor lead in the field log is 7 in both directions (bound 24).
- A car sits on point 364 (the head quad, credited n − 1 by the reversed walk) for a median of 12 frames per crossing (8-16; field log at 2-frame resolution), the player 8 (per frame); normal 10 (8-16) and 8.
- **Decision (Step 4): segment credits alone are enough**: the lap test passes and the median is at most 18. Task 11 (a reverse start band) is not needed; the collision memory floor stays at 7 500.
- Step 4's other outcomes: the race loads and grids on the variant's tables (its time and checkpoint records, 5 laps, no opponent at the origin, the render rate at or above 27 after frame 2000); laps count; the direction half of the turned-round test passes. No STOP condition is met. The field and jolt tests are green, so Task 9 goes on as an investigation of the six values without a red test behind it.

## 4. The six values of 0x1500 (recon §7 item 1)

**Formulas** (`tgp.edge_values`). With a = the quad's attribute (low 16 bits, 1/65536 turn), u = (−sin a, cos a) its direction of travel, r = (u.z, −u.x) its right, p = (x, z) the car and c0..c3 its corners (front-left, front-right, back-right, back-left; c3 is not used):

| field (return order) | value | meaning |
|---|---|---|
| `+0xf1` | (c0 − p)·r | the front-left corner's lateral offset (negative: to the left) |
| `+0xed` | (c1 − p)·r | the front-right corner's |
| `+0xf5` | −(`+0xf1` + `+0xed`)/2 = (p − (c0 + c1)/2)·r | the car's lateral offset from the front edge's midpoint (positive: to the right) |
| `+0xf9` | (c1 − p)·u | the front edge's distance ahead, through c1 |
| `+0xfd` | (c2 − p)·u | the back edge's (negative: behind), through c2 |
| `+0x101` | −(`+0xf9` + `+0xfd`)/2 = (p − (c1 + c2)/2)·u | the car's offset along u from the middle of the right side |

- Fit: the fresh E lines of the Task 8 normal race in its window (frames 1866-8630), 54 112 lines over 393 quads: each value within 1e-3 × max(1, |value|) on 54 112 of 54 112. The same on the reverse race's (54 112 lines, 389 quads). The next-best candidate explains at most 43 %. Outside the race (frames 1-615, before the course loads) 2 735 lines fit nothing: zero values or other quads; they are not race lines.
- The fitted candidates were the brief's ((p − ci)·u, (p − ci)·r, distances to the edge lines, edge lengths, sin a, cos a, negatives) plus the means of two of them, added because handler 0x34b adds the two values of each group and scales the sum by −1/2 (`fadd`, then multiplies by constants), so `+0xf5` and `+0x101` are means.
- Step 3, confirmation: the Task 8 set with all 1 322 quads that Metropolis's 1 199 cell lists name in slot 6 replaced in place by `reverse_quad`. 96 s in the normal direction (race window 1866-5524): 29 264 fresh lines over 389 quads. The same formulas, evaluated on the re-authored quads, explain 29 264 of 29 264 for every value. The TGP uses the stored corners and attribute as they are. The build was deleted.

**Readers.** Read taps with `VR_TRACE_FINE=1`, 4-aligned (MAME refuses the odd start 0x400ded): `400dec-400e07,40106c-401087`. The first runs had the race and edge loggers on, and their Lua reads fired the tap at whatever PC was current (434 false "readers"). So the reader runs carry no logger:
- (a) 60 s from the race start, the player and car 1, each direction;
- (b) 220 s, all 16 cars, from the race start (frame 1860) through the end of the race, the end screens and the attract mode (to frame 12 655), each direction. The normal race ends at frame 10 889 (mode 0x14 → 0x1c). This reverse run ends at about 7 971: the autopilot's trajectory differs from Task 8's run from frame 2008 on, and the clock expired.

A static scan of the original boot-ROM listing for `ED/F1/F5/F9/FD/101[Rn]` gives the same set, plus the static-only sites marked below. Taps are per halfword, so a 32-bit read of `+0xed` shows as +0xec/+0xee/+0xf0. Fields are told apart by the instruction.

| field | PC | routine | use |
|---|---|---|---|
| `+0xed`, `+0xf1` | 0xfec805/0xfec80b (R19, the other car, only when its byte +4 is the player's), 0xfec827/0xfec82d (R25, this car) | car-to-car contact A (0xfec7b0..) | arithmetic: TGP 0x0080 (subtract, handler 0xa0) `+0xed` − `+0xf1` = (c1 − c0)·r, the front edge's width; compared with 5.0. The width test gates the lane-group test: only if both cars' quads are narrower than 5 does the lane-group test run (0xfec841..0xfec878: the segment's lane words via 0x501950, summed, rem their count, must fall in 0..7), and only if that passes is the lane path taken; otherwise the lateral path. The lane path ran in neither race (b) (row after next). This car's read is reached on 414 of 5 091 frames (normal, b): the other car's (the player's) quad is narrower than 5 on 8 % of frames |
| `+0xed`, `+0xf1` | 0xfecb14/0xfecb1a, 0xfecb36/0xfecb3c | contact B (0xfecaf0.., the second copy) | the same |
| `+0xf5` | 0xfec8df/0xfec8e5, 0xfecbee/0xfecbf4 (all 16 cars) | contacts A, B, lateral path | comparison between cars: R15 = `+0xf5`(R19, the other car) − `+0xf5`(R25, this car) (TGP 0x0080 returns its first operand minus its second: the follow-up below), R17 = int\|R15\|, R14 = the cars' distance (TGP 0x2180), as an integer. Each routine's own threshold (read by disassembly, 12 Nov): **contact A** pushes when R14 ≤ 7 (above 5 only when the other car's `+0x14` is the larger) and R17 ≤ 2; when the other car's byte +4 is the player's and `[0x40d826]` > 1, R14 ≤ 20 and R17 ≤ 5 if its `+0x1af` is set, R14 ≤ 0 if not (0xfec8fc..0xfec959); the sign of R15 (0xfec95c) picks the side of the push (R21 or R22 sent to TGP 0x0C00). **Contact B** pushes when R17 ≤ 6, R14 ≤ 10, or R14 up to 10 + half the amount by which this car's `+0x14` exceeds the other's (0xfecc6e..0xfecc95); the sign of R18 (0xfecca3: R15, or the other car's own `+0xf5` on the give-way branch below) picks the side. Contact B also tests R17 ≤ 3, with 4 < R14 ≤ 35 and this car's `+0x14` > 100 and not below the other's, before it rescales this car's `+0x48` (0xfecc0b..0xfecc69) |
| `+0xf5` | 0xfec8aa/0xfec8b0, 0xfecbb9/0xfecbbf | contacts A, B, lane path | comparison between cars: the difference plus 3 × the lane difference, the same sign test. Executed only in the attract after the reverse run (frames 11 824-12 128), not in either race |
| `+0xf5` | 0xfecc9e (all cars) | contact B | sign test: R18 = `+0xf5` when R21 = R22; its sign picks the side |
| `+0xf5` | 0xfecfa1/0xfecfa7 (10 cars against one) | car beside car (0xfecf8e..) | comparison between cars: \|`+0xf5`(this) − `+0xf5`(other)\| ≤ 2.5, cars within 30 → `+0x1b3` = 0x10 |
| `+0xf5` | 0xfec05c | wall kick (0xfec003) | copied to `+0x12d` at the hit (the side of the front-edge midline the car was on), spin state `+0x124` = 0x10 |
| `+0xf5` | 0xfebdca | shared wall routine 0xfebdbe | sign test: `+0x12d` XOR `+0xf5` (crossed the midline since the hit?) |
| `+0xf5` | 0xfe9576 | spin recovery 0xfe9571 | sign test: `+0x12d` XOR `+0xf5`. Signs differ: yaw, heading and `+0x125` eased to the attribute. Same sign: the spin goes on (`+0x12b`/0x18 a frame) |
| `+0xf5` | 0xfe7afb, 0xfe7c37, 0xfe7fe5 (player) | in states `+0x124` = 0x10, 0x0a and `+0x68` = 8 | sign test (bit 31) choosing one of two branches |
| `+0xf5` | 0xfe940e, 0xfe94aa (static only) | the player's car under game control | arithmetic: stored to `+0x173`; the next frame `+0x173` − `+0xf5`. Not executed in any race run |
| `+0xf9`, `+0xfd` | none | | no instruction reads them: the static scan finds only the seven 0x1500 sites, which write them |
| `+0x101` | 0xfea4d3 (static only) | race order (0xfea4a4, from the task 0xfe72be) | arithmetic: `+0x58` = 64 × (lap `+0x1b5` × `+0xe3` + `+0xa6`) + int(4 × `+0x101`). Not executed in any run (b), either direction, race or attract. 0xfed13d reads `+0x105` (halfword at +0x105), not `+0x101` |

**The rule** (F = `edge_values(q, p)`, G = `edge_values(reverse_quad(q), p)`). Turning the quad round swaps the corners to (c2, c3, c0, c1) and negates u and r, so p drops out of G[k] + F[partner]: each is a constant of the quad.
- G(`+0xf1`) = −F(`+0xed`) + (c1 − c2)·r
- G(`+0xed`) = −F(`+0xf1`) + (c0 − c3)·r
- G(`+0xf5`) = −F(`+0xf5`) − ((c1 − c2)·r + (c0 − c3)·r)/2
- G(`+0xf9`) = −F(`+0xfd`) + (c2 − c3)·u
- G(`+0xfd`) = −F(`+0xf9`) + (c1 − c0)·u
- G(`+0x101`) = −F(`+0x101`) − ((c2 − c3)·u + (c1 − c0)·u)/2

These are a signed permutation only where the right side is parallel to u, the left side too, and both edges are square to it. Measured:
- Over Metropolis's 1 322 quads, the constant exceeds 1e-3 on 927 / 915 / 1 264 / 1 214 / 1 209 / 1 230 quads (in field order). Medians 0.11-0.45 units, 90th percentiles 6.5-16.9, maxima 25.3-39.8 (triangles and tapered verge and wall quads).
- Both lateral constants are within 1e-3 on 42 quads.
- The best signed match holds on 30-41 % of the logged samples (normal race: 37.6 / 40.5 / 29.9 / 39.3 / 40.3 / 31.9 %).
- The width that contacts A and B test (G(`+0xed`) − G(`+0xf1`) = (c2 − c3)·r, the back edge's) falls on the other side of 5.0 from the front edge's on 161 quads; 641 quads have a front edge narrower than 5.

| value | outcome |
|---|---|
| `+0xf1` | **STOP**: needs (c1 − c2)·r, a quad dimension the six do not carry; varies by quad |
| `+0xed` | **STOP**: needs (c0 − c3)·r (corner c3); varies by quad |
| `+0xf5` | **STOP**: needs both; varies by quad |
| `+0xf9` | leave: no instruction reads it |
| `+0xfd` | leave: no instruction reads it |
| `+0x101` | leave: not read in a race (the one static reader, 0xfea4d3, did not run) |

What the uncorrected values are in the reverse race:
- `+0xf5` is still a lateral offset, but with right meaning the forward right (the reverse left) and measured from the forward front edge's midpoint.
- The front-edge width is the forward front edge's.
- The sign tests that compare `+0xf5` with itself (wall kick against spin recovery, 0xfebdca; car against car) do not depend on which side is called right. They do depend on the midline: the forward front edge's, not the reversed quad's.
- No signed permutation of the six gives a reverse-authored quad's values for the three fields that are read. The difference is two numbers per quad, (c1 − c2)·r and (c0 − c3)·r.

### What leaving the three values alone does in a reverse race, and what a plain mirror would leave

**Evidence.**
- The (a), (b) and plain-mirror columns below are read from the boot-ROM disassembly and the TGP handlers. No MAME run was made for this subsection, so they describe what the code would do, not behaviour that was observed.
- The plain mirror was never built: its column is a prediction.
- The one runtime input is the width sign (4 677 of 5 091 frames below). It comes from reader run (b), normal direction: read taps on all 16 cars, frames 1 860-12 655, counting reads of 0xfec805 against 0xfec827.
- The numbers in (c) are computed from the slot-6 quads of the Task 8 build.

Three cases are compared. Today: `+0xeb` turned half a turn by `dirattr`, the six values as the forward-authored quad gives them. Exact: the quad re-authored by `reverse_quad`. The plain mirror G' = (−F(`+0xed`), −F(`+0xf1`), −F(`+0xf5`)) stored at (`+0xf1`, `+0xed`, `+0xf5`).

Two facts decide most readers; the second rests on the runtime count:
- **Corners from TGP 0x0C00.** The contact routines take their push targets from command 0x0C00 (handler 0x2a8). It returns the twelve corner coordinates of a quad: c0 in R0-R2, c1 in R3-R5, and so on. Those corners stay forward-authored in a reverse race, whatever is done to the six values.
- **Sign of R15.** In contact A, R15 = `+0xf5`(R19) − `+0xf5`(R25) is the other car minus this car: TGP 0x0080 returns its first operand minus its second. This is shown by the width test: in reader run (b), normal direction, 0xfec805 is read on 5 091 frames and 0xfec827, reached only when `+0xed` − `+0xf1` < 5, on 414. So the difference is ≥ 5 on 4 677 frames, i.e. it is +width, not −width. R25 is the opponent being moved. R19 is its ranking neighbour: `+0x19c`, ahead, in contact A (0xfec7ab..0xfeca85); `+0x198`, behind, in contact B (0xfeca95..0xfecdd1).

Angles decrease towards r: heading +z is 0, +x (= r) is −0x4000. The yaw `+0x36` uses the attribute's convention: put-backs copy one to the other.

| reader | (a) how the value is used | (b) today against exact | the plain mirror |
|---|---|---|---|
| push, contacts A and B (0xfec95c, R15 ≥ 0 → 0x0C00(R21) → c0, else 0x0C00(R22) → c1; the AI target (R10, R11) is blended from its path point towards that corner by \|R15\|/2.5, or /6.5 in B) | combined with the quad's own corners, not with `+0xeb` or the yaw. Other car on the +r side → target towards c0, on the −r side of the quad, away | **would not be mirrored**: today the sign and the corners are both forward-authored, so the side would be right in the world. The corner aimed at is the target quad's forward-front corner, i.e. its near edge in reverse travel, not the far one | **would be mirrored** (prediction): the sign would flip while 0x0C00 still returns forward corners, so the opponent alongside would steer towards the other car instead of away from it |
| give way, contact B (0xfecc9e: in the lateral path, R21 = R22, the sign of the car behind's own `+0xf5` picks c0 or c1) | as above, the quad's own corners | **would not be mirrored**: the car being caught would move to the half of the road opposite the chasing car | **would be mirrored** (prediction): it would move onto the chasing car's half |
| heading match, contacts A and B (0xfeca4d, 0xfecd99: within 6 units, R0 = yaw(other) − yaw(this); if R15 > 0 and −0x1800 ≤ R0 ≤ 0, or R15 ≤ 0 and 0 ≤ R0 ≤ 0x1800, this car's yaw += R0/4) | combined with the cars' yaws: the sign of R15 picks which sign of the yaw difference triggers | **would be mirrored** (read, not observed). In the forward race the code fires when the car alongside turns away from this car, and this car eases a quarter of the way after it. In reverse today it would fire when the car alongside turns towards this car (the same quarter turn, now away from it), and a car turning away would get no response | would be restored: R15's sign follows the car's right. It differs from exact by the per-quad terms when the two cars are on different quads |
| sideways separation, contacts A and B (int\|R15\| ≤ 2, or ≤ 6 in B, together with the distance) | magnitude | none: \|R15\| would be the same up to the per-quad terms | the same as today |
| car beside car (0xfecfa1: \|R15\| ≤ 2.5, distance ≤ 30 → `+0x1b3` = 0x10) | magnitude | none: it would be identical on one quad, and differ by the per-quad terms across quads | the same as today |
| wall kick (0xfec05c) | stored only (`+0x12d` = `+0xf5`). The kick's turn comes from the yaw against the attribute, taken as an axis (0xfec019..0xfec057) | none | the same as today |
| wall routine (0xfebdca) and spin recovery (0xfe9571): sign of `+0x12d` XOR `+0xf5` | compares the value with itself at the hit. While the signs agree, 0xfebdbe returns without wall checks and the spin continues (`+0x6a` −= `+0x12b`/0x18). Once they differ, the wall checks resume and yaw, heading and `+0x125` are eased to the attribute | **would not be mirrored**: both samples are in the forward frame. The difference from exact would be only which line counts as crossed: the forward front edge's midline, not the reversed quad's. That line moves by the `+0xf5` error below, on each quad | exactly today's: the XOR of two negated values is unchanged |
| player sign tests (0xfe7afb with `+0x124` = 0x10 and 0xfe7c37 with 0x0a, `+0x124` being the spin state the wall kick sets; 0xfe7fe5 with `+0x68` = 8): the sign of `+0xf5` | picks sound command 0x5F or 0x6F, queued at 0x502500 (counter 0x5024fe, last command 0x5024fc); 0x0a swaps the pair | **would be mirrored**: the sign is relative to the forward right, which is the car's left in reverse, so the other command of the pair would be queued. What a driver hears is **not established**: that the two commands are a left and a right variant (stereo) is a guess. Settled by a run: the normal race with `-wavwrite`, the player steered (`steer_at.lua`) into the left wall and then the right wall, comparing channel levels at the 0x5F and 0x6F queue frames | would be restored, except where the per-quad term changes the sign |
| width test, contacts A and B (`+0xed` − `+0xf1` < 5.0 on both cars) | magnitude of the quad's own c1 − c0 along r; not combined with any direction | would not be mirrored. Today it measures the forward front edge, exact the back edge (c2 − c3)·r. The test gates only the lane-group test (0xfec841..0xfec878), which falls back to the lateral path; the lane path did not run in either race (b). Whether the back-edge width would change the outcome is **not established**: the test flips on 161 quads (116 tarmac, 45 others; (c) below), and no run tested whether a flip there reaches the lane path or changes a car's behaviour. Settled by a reverse race with the edge log and read taps on the six fields: count the frames on which 0xfec805 or 0xfecb14 runs with either car on one of the 161 quads, and whether the lane-group test after it (0xfec841..0xfec878) passes there | the same as today: the mirror leaves the width unchanged |

The lane path's `+0xf5` (0xfec8aa, 0xfecbb9) and the game-control reader (0xfe940e, 0xfe94aa) did not run in a race (above). They are not analysed further.

**(c) Plain mirror against exact, per quad of slot 6.** Every error is a constant of the quad:
- `+0xf5`: \|(c1 − c2)·r + (c0 − c3)·r\|/2;
- width: \|(c0 − c3)·r − (c1 − c2)·r\|.

| quads | `+0xf5` error (median / p90 / max, units) | width error (median / p90 / max) | width test (< 5) differs |
|---|---|---|---|
| tarmac, 0-526 (527) | 2.087 / 18.715 / 35.666 | 1.143 / 25.124 / 35.984 | 116 |
| run-off, wall and verge, 527-1 321 (795) | 0.121 / 0.994 / 8.252 | 0.239 / 1.989 / 16.505 | 45 |

- **The sign of `+0xf5` at the quad's centre differs between G' and G on every quad (527 of 527, 795 of 795), by construction.**
  - Each stored centre is its corners' mean, to within 4.6e-5.
  - At that point exact G(`+0xf5`) equals F(`+0xf5`), because the two midlines are symmetric about the centre. G' is −F there.
  - So the centre is the middle of the band where the two signs disagree.
- **Width of that band.** It is the `+0xf5` error above. As a share of the quad's mean width: median 0.386 on tarmac (p90 unbounded: quads whose width along r is about 0), and 0.026 (p90 0.288) on the rest. 488 tarmac quads and 776 others have a band of at least 1e-3.
- **Metropolis's tarmac quads are not cross-road slices of one shape.**
  - Front width deciles run −1.0..36.0 units, back width deciles −0.2..36.0. A negative width means c1 lies to the left of c0 along r.
  - 191 tarmac quads have a front edge narrower than 5, 267 a back edge narrower than 5. 16 have an edge shorter than 0.5.

## 5. The Big Forest template's pose sites and bit 0x1e (recon §7 item 3)

**Evidence.** Everything in this section is read from the disassembly of the original boot ROM (`disasm.listing` on `out/roms/vr.zip`, 12 Nov). No MAME run was made, nothing was patched, no Alpine was built: every row is **read, not run**. The sites are byte-identical in the Phase 25 build (`out/p25play2`): the directory patches none of them. These are stage 2's starting facts. Among the converted courses only Alpine has data index 2.

What the sites share:
- **Bit 0x1e of the race-start task `[0x50134c]`.** Mode 0x11 (handler 0xfe4013, the race's course load at bank site 0xfe415b) does three things:
  - it clears the bit (0xfe41b7);
  - it sets it when `[0x40d826]` < 2 and the data index `[0x501934]` is 2 (0xfe41c0..0xfe41d6, recon §1.3). `[0x40d826]` is the count byte the link code walks at 0xfe1632;
  - it starts the task at 0xfc0baf (0xfe41f1).
- **0xff4061 (`course.PIT_POSE`)** returns R10, R11, R12 = a pit box, chosen by data index:
  - index 1: the table at 0xff40b1;
  - index 2: the table at 0xff40d9 (Big Forest's box, (−230.38, 30.00, −269.57), recon §1.3);
  - index 0: it returns at once, leaving R10..R12 as they were.
  - With `[0x501105]` set, z comes from a table indexed by the player car's (`[0x501320]`) byte +4.
  - It has 14 callers. The directory sends the pit autopilot's six and the crew's four to the entry's own box (`PIT_BOX_CALLS`, `PIT_CREW_CALLS`, Phase 22i). The other four (0xfc005f, 0xfc0ec8, 0xff21a5, 0xff4165) still take the template's box.
- **The tests of the bit.** A byte scan of the boot ROM looked for `test1`/`set1`/`clr1 #1E` within 48 bytes after `mov.w 50134C[PC], Rn`. It finds:
  - the clear and the set above;
  - five tests: 0xfc10af, 0xfc1241, 0xfe4676, 0xfe8c35, 0xfed442.
  - The task's own handler also tests the bit, through R25, at 0xfc0bcd.
  - The recon named three of these sites (0xfed43b, 0xfc10af, 0xfc123a). The other three are 0xfc0bcd, 0xfe4676 and 0xfe8c35.
  - The scan would miss a test through a register loaded further back.

| site | where, reached from | condition | what it writes | a single-player race reaches it | in a reverse race (read) |
|---|---|---|---|---|---|
| 0xfc005f `jsr FF4061` | routine 0xfc0050, called at the start of task code 0xfc0000; attract mode 6 (handler 0xfe2ce3, the Big Forest load between demos) gives task `[0x501310]` that code at 0xfe2e8b | none | the player car's (`[0x501320]`) position `+0x1e/+0x22/+0x26` = the pit box, pit state `+0x191` = 2, `+0x14` = 0; then the crew (0xff27d8) and objects 5 and 7, placed from the box through TGP command 0 | **no**: attract mode 6 only, which `bankdemo` keeps in the normal direction | nothing |
| 0xfc0ec8 `jsr FF4061` | the race-start task's first handler 0xfc0baf (started by mode 0x11), on its first frame | bit set (0xfc0bcd) | handler 0xfc0fea, countdown `+0x36` = 0xa0, `+0x38` = 0, bit 0x1c of object 9; resets the player (0xfe88a7) and each opponent (0xfe8918). R10..R12 are **not stored** by this code: R10 is reloaded at 0xfc0eff; R11 and R12 were not traced through 0xfe88a7 | **yes**, on the Big Forest template, once | nothing on this branch: no pose written. **The bit-clear branch is not nothing** (corrected after the whole-branch review): with the bit clear the same handler starts task `[0x501348]` (0xfc1189) and, for data index 1 (Acropolis's template, which Metropolis and Diablo Canyon use), places three objects at the player's position plus fixed world-axis offsets (0xfc0bf2..0xfc0eb0), not turned by the yaw: in a reverse race they stand 0.5-4 units behind the car (§7, "The Acropolis template's start objects") |
| 0xff21a5 `bsr FF4061` (recon §1.3's player start; not in the brief's list, added for completeness) | the grid set-up, for the player only (0xfe8c51), when the task is live and the bit set (0xfe8c22..0xfe8c3e); the opponents take road point (count − 3 × (16 − i)) rem count, lap −1 (0xfe8c5a..) | bit set (0xfe8c35) | the player's position = the pit box; height and quad through 0xfed55e (`+0x22`, `+0x30`, `+0x140`); pitch, yaw, roll 0; then TGP 0x1800 on that quad (0xff2205, one of the 14 `dirattr` sites) → `+0xeb` and the yaw `+0x36`; pit state `+0x191` = 6 and flag bit 7: the **PIT START** | **yes**, on the Big Forest template | the position stays the template's pit box (absolute); the yaw is the quad's direction plus half a turn (`dirattr`); pit state 6 then runs the pit-out sequence (next row) |
| 0xff4165 `bsr FF4061` | first handler 0xff414c of task `[0x50138c]`. Its starters are 0xff4101 and 0xff4129, called from pit states 1 (0xff2515), 6 (0xff25c6), 8 (0xff26ed), 0xb (0xff2732) and 0xe (0xff2777) of the player's pit dispatcher (0xff237b: `jsr [FF2161 + 4 × +0x191]`) and from the attract demo (0xfc0316) | none: whenever the pit sequence starts that task | that task's position = the template's pit box (Big Forest's on Alpine), handler 0xff417b, `+0x12` = 0x51, `+0xe` = 0x502000. 0xff417b keeps the task while the player's `+0x191` ≠ 0 and sends it to the TGP as a drawn object; what it shows was not established | **yes**: on every pit stop (states 1, 8, 0xb, 0xe, set at 0xff2249..0xff2281), and at the PIT START (state 6) | an object at a fixed place: on Alpine it would stand at the forward pit, as today |
| 0xfed43b (in 0xfed42a, which the opponents' handler calls at 0xfea881 and 0xfea99a) | every opponent, every frame | `[0x501120]` = 1 << mode (0xfe1c96). In mode 0x12 (0x40000) the routine runs only with the bit set; in other modes when `[0x501120]` & 0x14100028 ≠ 0 (modes 3, 5, 0x14, 0x1a, 0x1c) | the opponent's speed terms `+0x40`, `+0x44`, from `+0x48`, `+0x11b` and the tables 0xfd1cbb, 0xfcf1fb by `+0x14` | **yes**. On the Big Forest template this also runs in mode 0x12: the opponents move while the player waits in the pit | nothing by reading: speeds, no direction or pose |
| 0xfc10af (in 0xfc10a8, called once from mode 0x13's handler 0xfe46ad at 0xfe46eb) | the race start | bit clear: stops the race-start task (clears its bit 0x1f). Bit set: the rest of this cell | the task: `+0x36` = 0x59, handler 0xfc1122; a blank string over the text row at tile 0x700d28 (where 0xfc1040 prints " PIT START"); tile map 0x2f2bbe at 0x700534; sound command 0xb054 | **yes**, once | nothing: text, tiles, sound |
| 0xfc123a (called once from mode 0x13, 0xfe46cd) | the race start | bit set: returns at once. Bit clear: the rest of this cell | if task `[0x501348]` is live, palette words from 0x2ec9c4/6 and 0x2ec990 to 0x902044/46/50/52; sound 0xb02a; sound flags at 0x5024fa (bit 0 clear, bit 1 set) when that task's bit 0x1e is clear | **yes**, once (it does nothing on the Big Forest template) | nothing |
| 0xfe4676 (mode 0x12's handler 0xfe4666) | every frame of mode 0x12 | bit clear: on to mode 0x13 when the timer 0x50113c goes negative. Bit set: when the player's pit state `+0x191` is 0 | 0x501a1c = 0; the mode byte 0x501139 = 0x13 | **yes** | on the Big Forest template the race (mode 0x14) starts only when the pit-out sequence has ended |

**For a reverse Alpine (stage 2), from the rows above:**
- The opponents' grid is road-relative. It would take reversed points on a variant's tables, lap −1.
- The player's start is not road-relative. The player would start in the forward pit, at the template's absolute pose, turned half a turn by `dirattr` at 0xff2205. The pit-out sequence would then drive the car out along a pit lane built for forward travel, and the race clock would start when that sequence ends.
- Stage 1's variant has no pit (`pit_quad` None).
- Not established: whether the pit-out sequence can bring a car into a reverse race, and where it would join the road.
- One option, neither designed nor tried: clear bit 0x1e for a variant. The grid would then take each car's line point (as on Metropolis), and 0xfc0bcd, 0xfc10af, 0xfc123a and 0xfe4676 would take their other branch.

## 6. The numbers, normal against reverse

Decoded from the playtest build `out/p26play1` (code head 28d91b0, the command-line build of the tests' seven-course set); the race rows are Task 8's (the table above).

| | normal | reverse |
|---|---|---|
| road points, segments, lines | 365, 527, 8 | 365, 527, 8: the same lines read backwards (reversed point j = forward point (365 − j) mod 365) |
| tables in data bank 2 (header, segment array, pointer block, eight lines) | header 0x175c30 | header 0x18acd0, 52 080 bytes (0x18acd0..0x19783f) |
| collision map, surface table, backdrop directory | 0x1827a0, 0x18a7a0, 0x162204 | the same: one collision |
| TGP collision words | unchanged: the floor 7 500 holds (7 651 left) | none added |
| load and maps records | in the directory's tables | 0x28e810 and 0x28ef1c, named by entry 6's word of the reverse table |
| race blob (1 808 bytes) | 0x284ad0 | 0x28ef60 |
| checkpoints (road points) | 0, 126, 222 | 0, 143, 239 |
| initial time; extensions (1/32 s, level 0) | 2080; 336, 256, 381 | 2080; 381, 256, 336 |
| pit | entry quad 71 | none |
| HUD map (`map_tx`, `map_cross`) | 149.0, 0 | 237.0, 22 |
| laps in the 117.6-s race window (player; every car) | 1; 21 crossings, each +1 | 1; 23 crossings, each +1 |
| extensions fired (road point / gain) | 126/335, 224/255, 1/380, ... | 144/380, 241/255, 0/335, ... |
| opponents moved ≥ 100 points / parked / largest backstep | 15 / 0 / 0 | 15 / 0 / 0 |
| leader's and slowest opponent's gain (points) | 833, 509 | 849, 537 |
| off-tarmac jolts (cars with one) | 65 (15) | 26 (8) |
| frames on point 364 per crossing (median, range; player) | 10, 8-16; 8 | 12, 8-16; 8 |
| `+0xeb` = the quad's direction (+ 0x8000 in reverse) | 54 180 of 54 180 lines | 54 186 of 54 186 |
| wrong-way warning in the race | 0 frames | 0 frames |
| put-back: yaw against the raced line, 60 frames on | −0x8e | +0x1cd |

The code stage 1 adds lives in the directory image, which now ends at 0x27a99e:
- `entry`: 100 bytes;
- the reverse table: 40 bytes;
- `bankdemo`: 14 bytes;
- the loader's write-back: 7 bytes (0x279884..0x27988b);
- `dirattr`: 32 bytes.

The eleven routines dropped their inlined lookup, a net saving of 389 bytes before `dirattr`: 616 bytes of inlined code removed, less 66 for the `jsr`s, 100 for `entry`, 40 for the reverse table, 14 for `bankdemo` and 7 for the write-back (616 − 66 − 100 − 40 − 14 − 7 = 389; the directory's end moved from 0x27ab03 to 0x27a97e, 389 bytes, in Task 4). The variant takes 3 680 bytes of `CODE_FREE`: the annex 0x28e810..0x28f670, including a 1 740-byte gap. It takes 52 080 bytes of data bank 2.

**Whole suite (12 Nov, started on code head 28d91b0): 738 passed, 15 failed, 1 unexpected pass. All 15 fail on main too: the 14 names known before stage 1 and `test_alpine_as_entry_three_drives`, a Phase 25 regression of an old autopilot drive found by this run (same figures on main 15e80e5; `docs/follow-ups.md`). No failure comes from stage 1.**

## 7. Open after stage 1

- **The flag's life.**
  - The flag is not cleared when a game starts. The byte holds what the last course load served (the loader writes back 1 or 0) until the attract cycle's next load, where `bankdemo` clears it (0xfe2160, 0xfe2cf7).
  - A game started before that load would see the last value. Not tried: whether a coin during the end-of-race screens reaches the select screen without a mode-2 load.
  - Stage 3's direction screen writes the flag on every game.
- **Rankings.** A reverse race still writes Metropolis's ranking table. In the playtest, the launchers restore `start/nvram` on every launch, and that alone keeps reverse laps out of Pascal's tables.
- **Linked play's two bank sites call `bank`, not `bankdemo`** (Task 4):
  - 0xfe2b07: game mode 5, reached only through a linked cabinet's mode;
  - 0xfe1d37: a cabinet joining a linked race, after its own loader call at 0xff0be8.
  - A linked load right after a reverse race, on the menu path, could serve the variant. Not run. For stage 3 (for example, 0xfe2b07 through `bankdemo`).
- **The reverse grid's last rows.** The opponents stand at forward points 364..350. Forward 350-356 (reverse rows 9-15) carry the Phase 22n lane shift (up to 6.2 units) on a 22° bend (plan D1). Not measured; for Pascal's drive.
- **The Acropolis template's start objects** (found by the whole-branch review; read from the disassembly of the original boot ROM, `disasm.listing` on `out/roms/vr.zip`, 12 Nov: **read, not run**).
  - The race-start task's first handler (0xfc0baf, started by mode 0x11) with bit 0x1e clear and data index 1 (the compare at 0xfc0bf2; Acropolis's template, which Metropolis and Diablo Canyon use) places objects 0, 1 and 2 of the pool at `[0x501350]` (0x280 bytes each) at the player's position (`[0x501320]` +0x1e/+0x22/+0x26) plus fixed offsets. Each coordinate is sent with its constant to TGP command 0, read as their sum (as at 0xfc005f, §5; the TGP handler itself was not read):
    - object 0: (+1.2, 0, +3.98), heading `+0x2c` = 0, model list `+0x1ab` = 0xfd743b;
    - object 1: (+1.0, 0, +3.48), heading 0, model list 0xfd747f;
    - object 2: (−0.87, 0, +0.54), heading 0x8000, model list 0xfd754b;
    - all three get handler 0xff5c3d, then `jsr FF5B85` (0xfc0c8d, 0xfc0d85, 0xfc0e5a).
  - The offsets and headings are world-axis constants: nothing between the position load (0xfc0bfd) and the stores reads the car's yaw.
  - Metropolis's start faces +z (its centreline runs from point 0 towards +z), and the reverse race starts at the same point facing −z. So in reverse the three objects stand 0.5-4 units behind the car, about where a chase camera sits, instead of ahead of it. What they draw is **not established**: the model lists were not decoded and no run looked.
  - Stage 2 inherits it on Diablo Canyon (data index 1 too).
  - Two ways out, neither designed: rotate the offsets and headings half a turn when the flag is set, or decide to leave them (after a look, from the chase camera, at what they draw in a reverse race).
- **The three read values of TGP 0x1500** (§4): `+0xf1`, `+0xed`, `+0xf5`, as the forward-authored quad gives them.
  - Mirrored, read from the disassembly and not observed:
    - the heading match of an opponent alongside another car (0xfeca4d, 0xfecd99);
    - the player's choice between sound commands 0x5F and 0x6F (0xfe7afb, 0xfe7c37, 0xfe7fe5). What a driver hears is not established; a `-wavwrite` run would settle it (§4).
  - Right as they are: the push side and the give-way.
  - A plain mirror would fix the two mirrored behaviours and break the push and the give-way.
  - What an exact correction would need, not designed:
    - two per-quad numbers, (c1 − c2)·r and (c0 − c3)·r, for every quad a car can stand on (1 322 in slot 6), read at the seven 0x1500 sites;
    - an answer for the readers that combine the value's sign with TGP 0x0C00's corners, which stay forward-authored (the push and the give-way).
  - Pascal decides (§8).
- **The put-back test's steer** works at one spot: normal from point 330, wheel 236 for 200 frames; reverse from point 22, wheel 20 for 350 frames. A later change may turn the test red for a reason that has nothing to do with facing. A retune may then be needed.
- **ROM room for stage 2.**
  - `CODE_FREE` after stage 1 (decoded from `out/p26play1`) has 7 924 erased bytes, and no more than 1 792 in one run:
    - 1 792 bytes at 0x28f670, up to the area's end;
    - 1 740 at 0x28e850, between the variant's load and maps records. The maps record must sit at load + `maps_offset()` = 1 804;
    - six gaps of 720-744 bytes inside `build_all`'s spawn slots.
  - Six more variants laid out as `reverse_annex` does need 13 040 bytes in one run: six 64-byte load records, their maps records 1 804 bytes on, six race blobs of 1 808 bytes. All seven in one annex need 14 912. One race blob is already larger than any free run.
  - Elsewhere in the program ROM, 0x2fce00..0x2fffff (12 800 bytes) **is read** by the game: one reader, PC 0xfe6b64, frames 266-268 (§1). It is not free until what the game copies from it is known.
  - The boot ROM's 14 267 bytes at 0xfdc844 were never read in either tap run (§1). Stage 1 placed nothing in the boot ROM.
  - The tables go to each course's own bank. Bank 1's four courses need 227 888 bytes for eight lines each, against 113 380 free (recon §3.2, design §6.4).
- **The blob builders.**
  - `build_variant_blob` repeats about 22 lines of `build_course_blob`'s layout (header, segment array, pointer block, lines). This is on purpose: D3 keeps the normal builder untouched.
  - When stage 2 next touches `blob.py`, the two should become one helper, with a byte-identity test of every normal blob.
- **Alpine's start** (§5). The PIT START needs a decision before a reverse Alpine can grid: an absolute pose from the template's pit box, then the pit-out sequence, with the race clock started when that sequence ends.
- **Reverse start bands.**
  - On Metropolis, segment credits alone were enough (§3).
  - The planner's prototype of the reversed walk put eight quads at n − 1 on Alpine and several side by side on the two Surfers courses. This is a planning prototype, not measured in stage 1.
  - So a reverse start band (the plan's Task 11, with the memory floor at 6 000) is likely to be needed there.
- **The recon's open list (§7):**
  - item 5 is answered (§1);
  - items 1-3 are this note's §4, §2, §5;
  - item 6 (the gates' backs, the backdrop's other half) is for Pascal's drive;
  - items 4, 7 and 8 are untouched.
- **Minor findings of the task reviews, deferred.** These bear on the correctness of the documents and tests; those still open:
  - `tests/test_direction.py`:
    - Task 1's test has no liveness check: a run that fails to start, or logs nothing, passes. Its race is 120 s on Big Forest without the autopilot, as specified: shorter than this note's runs.
    - The 14-site checker stops at the first `jsr`/`bsr`/`rsr` (the callees were checked by reading only). It treats every `b*` except `br`/`bsr` as conditional.
  - `tests/test_directory.py` hard-codes 0x16 for `BANK_SITE_LEN`, and `directory.py` recovers `bank_at` after the fact.
  - `directory.py`:
    - The `_entry` docstring says the returned flags are an equal compare's. On the `bge menu` branch (data index ≥ 3) they are not.
    - `_check` does not reject a variant whose `panel_map` or `picture` differ from its entry's (they are stored nowhere).
  - `tencourse.reverse_annex` scans from the directory's end, not from past `build_all`'s fixed slots. An erased run inside a reserved spawn slot would read as free. Not hit: the annex is at 0x28e810.
  - `reverse.py`: empty tables raise a bare IndexError, and no test covers a heading just inside the 16-bit bound.
  - `tests/test_reverse_build.py`:
    - The memtrace frames are joined without the one-frame shift (harmless at a window edge).
    - The put-back runs log "warning reads: 1" without saying that this is the boot copy at frame 258.
    - Task 12's test has no positive control that the byte was 1 before the load.
  - This note:
    - §1's "0 at power-on is shown" is the value after the frame-0 clear (the dumps start at frame 1).
    - §1's "game over" is inferred from the mode byte.
    - "`+0x101` not read in a race" means not observed over about 157 s normal and 106 s reverse.
    - The centre's sign flip "on every quad" leaves out the 39 + 19 quads whose band is under 1e-3.
    - The tap ranges given are the two-car runs'.
  - Fixed after the whole-branch review (12 Nov): `direction.lua` fails loudly on a missing or non-hex `VR_DIRECTION_RAM`; `direction.py`'s docstring no longer gives the 0x1500 sites to Task 10; the put-back test says a missing put-back may need a retune of STEER, and reads a missing `steer.txt` as "never triggered"; `tests/test_tgp.py` adds a skewed quad at attr 0x4000; §4's readers table now agrees with its follow-up (R15 = other − this, each contact routine's own threshold, the width test gating the lane-group test); the wrong-way warning has a committed positive control (`test_the_wrong_way_warning_is_read_when_the_game_sees_the_car_against_its_quads`); `tests/test_direction.py` scans the program ROM for the 0x1800 command word too.

## 8. The verdict

- **One shared collision gives a sound reverse race on Metropolis under the autopilot.**
  - The race runs on the variant's tables over the normal course's collision.
  - Laps count at every crossing, and the checkpoints fire in order with their times.
  - The fifteen opponents race the reversed lap: none parks, none goes back.
  - There are fewer off-tarmac jolts than in the normal race (26 against 65).
  - The direction is turned on every sample, the wrong-way warning stays off, and a put-back faces the race.
  - Segment credits alone serve the start line: no start band, and the memory floor stays at 7 500.
  - With the flag 0, and on every entry without a variant, the game is the Phase 25 build (Task 12). `bankdemo` keeps the attract in the normal direction.
  - No STOP condition of Task 8 or Task 11 was met.
- **Two behaviours are known to be mirrored.** This is read from the disassembly, not observed:
  - the heading match of an opponent alongside another car: it would ease after a car turning towards it, instead of away;
  - the player's choice between sound commands 0x5F and 0x6F.
  - Both come from the three read values of TGP 0x1500 (`+0xf1`, `+0xed`, `+0xf5`). No signed permutation corrects them: Task 9's STOP for those values. Task 10 did not run.
  - The push side and the give-way are right as they are. A plain mirror would fix the two mirrored behaviours and break those two.
- **The decision is Pascal's.** He can drive stage 1 with the three values as they are: the race is measured sound, and the two mirrored behaviours are known. Or he can have an exact per-quad correction designed first. **Answered 12 Nov:** he drove reverse Metropolis on p26play1 (rec152) with the values as they are and found the opponents, the start and a spin good; no correction is designed. No pit stop triggered, as designed; he wants pit stops in reverse in a later stage.
