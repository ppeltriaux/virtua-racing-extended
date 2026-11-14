# Reverse courses, stage 2: recon (12 Nov 2026)

What the other six converted courses need for a reverse variant, measured on main 9458748 (stage 1 merged). Three
read-only strands; their full reports, scripts, logs, builds and snapshots are git-ignored under `out/p26/stage2/`
(`recon-rom.md` + `rom/`, `recon-courses.md` + `courses/`, `recon-start.md` + `start/`). This note keeps what the
stage 2 plan rests on. Tags: **[M]** measured (script named), **[R]** read from the code or the disassembly,
**[G]** guessed.

## 1. ROM room for seven variants

- **What a variant needs outside its data bank [R]** (`directory.py`, `tencourse.reverse_annex`): a 64-byte load
  record; a maps record exactly `maps_offset()` = 1 804 bytes after it (`mapobj`, `pitbox`, `pitaim` and `pitpark`
  add that constant to R8); a 1 808-byte race blob named by the load record's absolute pointer. None may sit in the
  data window (the bank byte is read before the bank is mapped; the race pointers outlive bank switches). For n
  variants in `reverse_annex`'s layout: 1 804 + 64·n (rounded up to 16) + 1 808·n: six 13 040, seven 14 912 **[M]**
  (`rom/annexsim.py`).
- **`CODE_FREE` cannot hold them [M]** (`rom/freemap.py`): 7 924 erased bytes in 8 runs, the longest 1 792; 9 864 once
  the stage 1 annex leaves, even if packed, and packing would move the normal courses' spawn lists. Two variants do
  not build today (`courses/q1place.out`).
- **The home: the tail of the colour-table free run [M].** Program ROM 0x2b1842..0x2c0000 is erased in the original
  (59 326 bytes). In `out/p26play1` the conversions' colour words fill 0x2b1842..0x2b6698 and select picture 9
  0x2b66b0..0x2b90b0; **0x2b90b0..0x2c0000, 28 496 bytes, is erased after every writer** (`build_all`'s colour
  allocation, then `ten_course_set`'s pictures, then the annex). Seven variants: load 0x2b90c0, maps 0x2b97cc, race
  0x2b9990, end 0x2bcb00, 13 552 spare.
- **Who reads it [M + R].** PC 0xfe6b64 is the boot's colour-table upload: 128 chunks of 0x1000 halfwords from
  0x200000, the whole program ROM once (0xfe6b2b..0xfe6b64) [R]. Read taps on `out/p26play1` over four runs (attract
  240 s; reverse Metropolis, Big Forest and Surfers Oval races of 330 s): 0x2b90b0..0x2bffff, 0x2df9a8..0x2dffff,
  0x2fce00..0x2fffff and `CODE_FREE`'s tail are read by 0xfe6b64 only, each halfword once, before frame 268
  (`rom/taps.py`, `rom/tapsum.log`). `CODE_FREE` has had this status since Phase 7. So the "reader of 0x2fce00"
  stage 1 found is this upload.
- **Colour entries [M]** (`rom/texscan.py`): no object record's colour range reaches the tail; the conversions' words
  end at entry 0x9b34b (ROM 0x2b6698). Not covered: boot-ROM model lists in other formats, objects built at run time.
- **Other homes.** The boot ROM's tail 0xfdc845..0xfe0000 (14 267 bytes, never read in six runs, no reference [M])
  holds six variants, not seven, and needs boot-ROM paths in `directory.py`. 0x2fce00..0x300000 (12 800) holds seven
  race blobs alone, 112 spare. Fallback if the colour run's tail ever shrinks under 14 944: records block in
  `CODE_FREE`, blobs at 0x2fce00 (arithmetic, not built).
- **Not established:** the service-mode ROM test's code (string at 0xfc7ea9) and what it reports on any patched
  set; taps in the test menu, linked play and with an operator-fixed course.

## 2. The six courses reversed

One `build_all` with `reverse=True` on all seven, cached (`courses/s2build.py`); each course raced 150 s both ways
with the variant on that course alone (`courses/q4race.py`, stage 1's harness and measures, `courses/ana_*.txt`).

| course | bank | points | variant bytes, 8 lines | start: quads credited n−1 | checkpoints (reverse) | first fault in the reverse race |
|---|---|---|---|---|---|---|
| Alpine | 3 | 452 | 63 520 | 8 (0-7), and quad 562 (credit 0) overlaps them | 0, 119, 260, 387 | the template's pit start: §3 |
| Amazon Falls | 1 | 330 | 47 536 | 5 (0, 1, 2, 5, 6); quad 0 spans −0.5..+5.9 round the line | 0, 93, 213 | the player spawns credited n−1 (329) and wraps at frame 1880 with the lap byte unchanged; cursor lead 21 (bound 20); jolts 37 against 14 |
| Diablo Canyon | 2 | 457 | 66 112 | 2 (1, 2), from +2.8 | 0, 168, 278 (gate 421 dropped) | the clock ran out at 109 s |
| Pacific Coast | 1 | 410 | 58 800 | 1 (1), from +3.4 | 0, 90, 224 | none |
| Surfers Oval | 1 | 387 | 56 736 | 3 (0, 2, 3: road and apron) | 0, 88, 260 | none (the spawn read 0) |
| Surfers Road | 1 | 441 | 64 816 | 2 (0, 2: road and apron) | 0, 142, 314 | jolts 85 against 46 (stage 1's bound 1.5 × normal + 10 = 79) |

In all six: laps count at the crossings, checkpoints fire in the reversed order, 15 of 15 opponents move, none
parked, no step back over the line, the direction attribute turned on every sample **[M]**. With the variant on any
one course the normal direction is byte-identical (`courses/q5bytes.out`).

- **Bank 1 [M]** (`courses/q1place.out`): one free run of 113 380 bytes. Eight lines on the four courses need
  227 888. Three stored lines each place (99 888; 13 488 left); one course could have a fourth (Amazon: 8 080 left).
  More does not place: `place_blob` takes runs of at least 0x8000.
- **No line is stored twice on any course [M]**: every course has a lane shift, so line 6 (offset 0) differs from the
  centreline.
- **Fewer stored lines need no car-table change [R + M]**: the pointer block's eight (pointer, count) pairs are
  independent; several can name one stored line (built and decoded, `courses/q4exp.py`). The car table: player on
  line 0; opponents 1-2 line 1 (−8), 3-4 line 2 (−3), 5-6 line 3 (+3), 7-8 line 4 (+8), 9-10 line 5 (+5), 11-12 line
  6 (0), 13-15 line 7 (−5).
- **Which three [M]** (150-s reverse races, jolts in the 117.6-s window):

  | course | 8 lines | pairs (0,1,1,4,4,4,4,1): centre, −8, +8 | pairs (0,7,7,5,5,5,5,7): centre, −5, +5 |
  |---|---|---|---|
  | Pacific Coast | 106 | 166 | 95 |
  | Surfers Road | 85 | 113 | 73 |
  | Surfers Oval | 12 | not run | 12 |
  | Amazon Falls (start credits fixed) | 30 | not run | 24 |

  The centreline (line 0) must stay stored (header, player) and is not a good opponent line (not shifted onto the
  Saturn's tarmac). How bunched the field looks was not judged.
- **Amazon's start [M]**: crediting 0 the quads at the line that were credited n−1 and begin at most 1 unit before
  it (quads 0 and 1) fixes it: no bad wrap, lead 13-15, jolts 30; with the three lines above, lead 9, jolts 24. No
  collision memory spent. The same change on Alpine (quads 0-5) under the pit start parks six opponents; not
  understood.
- **Diablo's clock [M + R]**: a reverse lap's extensions sum to 1 056 (388 + 254 + 414), a normal lap's to 1 172
  (414 + 254 + 305 + 199). The normal lap has a fourth, 36-point sector lifted to `EXTENSION_MIN` (200); the reverse
  lap drops that gate (36 points after the reverse start). On the other five the sectors are the same lengths in
  another order and the totals agree.
- **Start bands**: none needed on five courses. Alpine: not established (about 110-130 words [G]); any band changes
  the shared collision and so the normal direction's bytes.
- **Grid rows [M]** (`courses/q3grid.out`): Pacific's reverse grid stands on a lane shift (−3.4 to −8.5 units) on a
  28° bend; Diablo has a 29° bend at reverse 10-14; the Oval and Surfers Road are straight over reverse 0-19;
  Amazon straight-ish with its pit mouth beside reverse 9. No fault showed in the races.
- **HUD map [M]**: reverse `map_tx`/`map_cross` 149/0 on Alpine and Pacific, 237/22 on the other four.
- **Not established:** tunnels at the grid rows; whether Surfers Road's jolts are run-to-run variance (one run
  each).

## 3. The race start per template

Runs on `out/p26play1`, no autopilot (`start/run_metro.py`, `start/startlog.lua`); disassembly of the original boot
ROM.

- **Templates [R]**: Alpine → Big Forest (data index 2). Diablo Canyon, Metropolis → Acropolis (1). Amazon Falls,
  Pacific Coast, Surfers Oval, Surfers Road → Bay Bridge (0).
- **The fork [R]**: bit 0x1e of the race-start task `[0x50134c]`, set by mode 0x11 at 0xfe41d6 (`set1 #1E, 0[R0]`,
  9 bytes `97 80 f4 1e 00 00 00 00 00`) only for data index 2 with `[0x40d826]` < 2, after the loader has run
  (0xfe4177). The original takes the bit-clear start on Big Forest in a linked race [R, not run].
- **Bit clear (Bay Bridge, Acropolis) [R + M]**: the player and the field stand at the car table's points on the
  variant's lines (0xfe8c94..0xfe8ce2); the READY lights are drawn in view space; mode 0x12 ends on a timer (frames
  1604-1861), the clock counts from 1866. Nothing in it is tied to a direction. Same framing both ways.
- **Bit set (Big Forest: Alpine) [R + M]**: the player's pose is absolute, from template code only (0xff21a5 →
  0xff4061 → boot table 0xff40d9; pitch, yaw and roll stored 0 at 0xff21d7..0xff21ff). On Alpine that pose is on
  the main road, 3.3 units from line point 13; the crew stands at Alpine's own pit box, far away; nothing drives a
  pit-out, the race starts when the crew's animation ends (clock at ~1928). With a variant served and today's code
  the player faces the forward way at forward point 13 with the attribute turned: "REVERSE" shows (101 frames in the
  trial race), the first crossing counts no lap, the opponents roll during the wait **[M]** (`courses/race_ALPINE`).
- **The patch for Alpine [R + M]**: do not set the bit when the direction flag is 1. `set1 #1E` at 0xfe41d6 becomes
  a jump to `cmp.b #0, 502294; bne done; set1 #1E, 0[R0]; done: rsr` (R0 kept; the flags after it are not read; the
  flag is valid there). Trial on normal Alpine with the bit cleared from Lua one frame after it was set
  (`start/run_alpine_bitclear`): the car at line point 0 with the line's yaw, the lights, mode 0x14 at 1864, the
  clock from 1866, the field on the grid. Not run: a reverse Alpine with the patch.
- **The three start figures of the Acropolis template [R + M]**: animated grid girls on the pit crew's character
  system (character records 0xfd743b, 0xfd747f, 0xfd754b; object 0 holds a parasol, 0x2e5360), placed at the
  player's position plus (+1.2, +3.98), (+1.0, +3.48), (−0.87, +0.54) with headings 0, 0, 0x8000: world-axis
  constants, the same in both directions. When its animation ends a figure jumps to the animation's end point and
  walks off along heading 0x4000 (a constant in shared code, 0xff6712). In reverse they stand behind and beside the
  car: a figure's legs fill the left third of the screen 40 frames in, a parasol hides part of the road on the right
  at the green light, none in view after 340 frames (`start/sheet_reverse.png` against `sheet_normal.png`). No effect
  on the car or the timing. Two ways: no figures in reverse (the compare at 0xfc0bf2, `cmp.b #1, 501934; bne
  FC0EEC`), or a half turn (a routine at 0xfc0eb0, `br FC0EEC`: reflect each figure's x, z through the car and add
  0x8000 to `+0x2c`; whether the animation's root motion turns with `+0x2c` is not established).
- **Observed, not traced [M]**: during the countdown the HUD shows 1ST on the Acropolis template in the normal
  direction and 16TH in reverse (16TH on Amazon; 16TH everywhere once the cars move).

## 4. Pit stops in reverse: inventory for a later stage [R]

Pascal wants pit stops working in reverse in a stage of its own. The pit routines (`pit`, `pitstops`, `pitbox`,
`pitboxcrew`, `pitaim`, `pitpark`) go through `entry` and so already read the variant's record.

| piece | a later stage must supply |
|---|---|
| entry trigger (0xfe8e88..0xfe8ec5) | an entry quad (and quad + 1) at the reverse mouth, the forward exit: a change to the shared collision |
| stop count (`pitstops`) | the variant's pit quad; `_check` relaxed |
| drive to the box (0xfe968d, a straight aim) | the box in the variant's maps record, heading + 0x8000; the aim from the reverse mouth must clear the lane's walls |
| release | a drive check that the forward entry mouth can be driven out of in reverse |
| lane credits | that the pit-lane quads are among the variant's credited tarmac quads (not checked) |

The crew and the pit-box props are cosmetic and not direction-specific. Not established: what the pit-box task
draws; the linked-play pit autopilot 0xfe98f6.

## 5. Decisions taken on this recon (12 Nov)

- **Pascal:** reverse Alpine gets the standing grid start of the other six (the patch of §3), not the crew start.
- **Pascal:** the grid girls are turned half a turn in reverse so they stand ahead of the car; if their animation
  does not follow the heading, they are left out in reverse instead.
- **Builder:** all seven variants in one annex in the colour run's tail (§1); three stored lines (centre, −5, +5) on
  the four bank-1 courses, no fourth line on one course (its benefit is not measured and the bank's 13 488 spare
  bytes are kept); a reverse lap gets the normal lap's total extension time (§2, Diablo); the quads that touch the
  line are credited 0 (§2, Amazon); no start band unless Alpine's measured start needs one, which stops for Pascal.
