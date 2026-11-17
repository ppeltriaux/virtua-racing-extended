# Phase 33 stage 1 findings: Big Forest, Bay Bridge and Acropolis in reverse, a prototype (15 Nov 2026)

Pascal, 15 Nov: "We also need to do the reverse for the three initial tracks". This is stage 1 of the recon's route A
(`docs/spike/2026-11-phase33-originals-reverse-recon.md`), built on branch `phase33-originals-reverse` as a **prototype for
Pascal to drive and judge**. It is not merged and not pushed. (When this was written Pascal had neither seen nor driven it; they drove the stage 1 set on
16 Nov, §15.0, and the stage 2 set later that day, §16.0.) The eight decisions
the recon put to them were not yet answered when it was built, so every one of them is built on the recommended default and
kept cheap to change. They answered while it was being built (§11): "Yes all your recommendation"; the stage then gained
the START banner's lettering from behind and the removal of the arrow boards in reverse.

**The third review's corrections and the rebase onto main 75dd1cd are §18.** **The second fix wave (16 Nov, on main 1159aab) is §17** (one frame of the old colours at an original's lock, the put-back
Pascal met on Bay Bridge in reverse, the hook's move, the rebase). **The fix wave after the review (16 Nov) is §16** (the direction screen's picture of an original, the margin's test, the
Bay Bridge side road, Pascal's words on the stage 2 set). **Stage 2 (16 Nov) is §15**: Pascal drove the stage 1 set and REPORTED two things (the checkpoint flags white without the C.P.,
the pit not working) and then a third (no REVERSE during the race); the session lead brought those stages forward, and all
three are built on this branch, rebased on main c94d7d9 (Phase 32 merged). Where §0-§14 say "not built", "blank white",
"no pit stop" or "82 bytes", §15 has what holds now; §0-§14 are left as the record of stage 1.

**[V]** = measured here (a decode, a build, a MAME run; the artefact is named); **[R]** = read in the code or the boot listing;
**[?]** = not established. Scratch and artefacts (git-ignored): `out/p33/` (§13). No ROM byte and no game data is in the tree.

## 0. In brief

- **Built**: each original has a reverse variant generated from its own arcade tables, reached through the existing COURSE
  DIRECTION screen. No Saturn data, no new collision (0 TGP words), no new polygon. Two small routines beside the directory
  (82 bytes): a reverse race on an original records no best time, and its HUD label is the game's level word. Rebased on
  main add9799 (Phases 29 and 31), its block moved clear of Phase 31's reservation (§2).
- **The normal direction**: the three originals' data is untouched and a normal race is the build before's, pass for pass, on
  the same inputs [V]. One thing does change in the flow and cannot be avoided if the originals are to offer reverse: **after
  the course select an original now shows the COURSE DIRECTION screen**, as the seven do (§3).
- **Bay Bridge is a stopgap**: all fifteen opponents follow the centreline, because data bank 1 has room for one reversed line
  (12 336 of its 13 488 free bytes), not eight (60 048). It races (none parked), single file.
- **What the measurements changed against the recon's plan** (each a builder's choice by measurement, none driven):
  - **the reverse grids are not the game's** (§5.2): on the game's grid 3 to 10 opponents stood turned 25-56 degrees at the
    green. Bay Bridge and Acropolis: the cars two road points apart, the game's order, the grid twice as long. Big Forest:
    the lines interleaved within the game's fifteen points. After that none stands turned (at most 4.4 degrees);
  - **Big Forest's opponents use six of its eight lines** (§5.1): the two innermost lines put five cars onto the verge at one
    bend every lap (14 of 26 opponent jolts in the race to the time-out; the normal race: 3). On six lines: 9;
  - **the HUD map is NOT shifted** in reverse (§6.2): with the seven's shift the originals' own map outlines ran off the
    screen's right edge.
- **Added on Pascal's answers** (§11): in reverse the START banner reads from behind and the arrow boards are gone, by a spawn
  list of the variant's own (6 420 bytes of an erased run; the normal race's list untouched).
- **Looked into** (§5.4): on reverse Bay Bridge the test autopilot's car stood still for the rest of the race after the
  game put it back at the beach bend. Cause: the autopilot released the pedal and never pressed it again (the game's pedal
  cell reads 0); put-backs in reverse elsewhere on the originals drive on. Worth one try by hand at that bend.
- **Not in this stage**: pit stops in reverse (the pit lane does nothing, measured), the C.P. banners' backs, the scenery's
  backs, best-time tables, Bay Bridge's lines. Each is recorded open in §9.

## 1. What was built

| Piece | Where | What |
|---|---|---|
| `reverse_original(lines, segments)` | `vrtools/convert/reverse.py` | an original's eight lines each read backwards by itself (heading turned half a turn and unwrapped per line, pitch and roll negated, the link's segment kept), the segment credits renumbered (n − p) mod n, flags kept; a short line (Bay Bridge's line 6) completed from the centreline. Unit tests first, on synthetic data: `tests/test_reverse_original.py` (10) |
| `reverse_of_original(rs, entry)`, `ORIGINAL_REVERSE_PAIRS`, `ORIGINAL_REVERSE_GRID`, `interleaved_grid`, `origrev_address` | `vrtools/arcade/tencourse.py` | the variant: the reversed tables, a race blob (the game's checkpoints renumbered, the game's own time records, the game's car table on the reverse grid), no pit quad, the game's HUD-map values; installed by `ten_course_set` (`originals_reverse=True`) after the seven's variants, in the one annex and in each original's own bank |
| `rankgate3`, `hudorig` | `vrtools/arcade/origrev.py` (new) | the originals' block, 82 of 160 bytes at 0x28f7d0: erased ROM right below Phase 31's colour block (0x28f870..0x28f970), which is right below the start gantry's. **Not** in the directory image, which keeps its size (the test's bound is not raised). 160, not 96: room for §10 |
| `reserved_blocks`, `check_reserved_blocks` | `vrtools/arcade/tencourse.py` | every reserved span of the program ROM by name (the directory image, this block, Phase 31's colour block, the gantry's block, the direction screen's block, the reverse spawn lists' run); `ten_course_set` refuses a layout in which two overlap, and `install_origrev` writes on erased bytes only |
| `place_blob(min_run=)` | `vrtools/arcade/blob.py` | bank 1's last free run (13 488 bytes) is below the default 32 768 |
| `reverse_spawn_list`, `install_reverse_spawn_lists`, `SPAWN_ROOM` | `vrtools/arcade/tencourse.py`, `spawn.ARROW_BOARD` | the variant's own spawn list: the game's entities in the game's order, less the arrow boards (handler 0xffaa67), the start gantry naming the converted courses' both-sided frames (0x28f970) |
| the build report | `tencourse.report_lines` | one line per original's variant; Bay Bridge's says ONE LINE FOR ALL SIXTEEN CARS |

Variants in the built set [V, `out/p33play1/build-report.txt`]:

| | Tables | Lines stored | Grid (car k's road point) | Checkpoints |
|---|---|---|---|---|
| Big Forest | 42 080 bytes, bank 3 +0x69ad0 | 6: pairs (0, 1, 2, 3, 4, 6, 6, 4) | (0, 1, 3, 2, 4, 5, 7, 6, 8, 9, 11, 13, 15, 10, 12, 14) | (0, 108, 218) |
| Bay Bridge | 12 336 bytes, bank 1 +0xfcb50 (1 152 left in the bank) | **1**: the centreline for all sixteen cars | 2k: (0, 2, 4, …, 30) | (0, 197, 306) |
| Acropolis | 84 496 bytes, bank 2 +0xa4be0 | 8 | 2k | (0, 169, 382) |

## 2. The bytes [V, `out/p33/gates/bytes.txt`: every differing byte against merged main, named]

**Which main.** The branch is rebased on main add9799 (Phases 29 and 31 merged). The tree's set built with
`originals_reverse=False` (`out/p33/build/plain`) is the lead's build of that main, `out/p35play1`, byte for byte (program,
boot, data, polygon, TGP data, TGP program) [V]; the in-tree tests' comparison set (`_seven_plain`) is that set. Every figure
of this section and every gate of §3, §4.1, §4.3, §7 and §8 is against it. The trials of §5 (the line pairs, the grids), the
normal rows of §4.2 and the read tap below were run before the rebase, on sets built from main 2a9f1ab (`out/p28play2`); the
final measures of §5 were repeated on the rebased set.

| ROM | Span | Bytes | What |
|---|---|---|---|
| Polygon ROM, TGP data, TGP program | - | 0 | identical: **0 TGP words changed**, no collision byte, no wall moved |
| Boot | 0xfc40ce..0xfc40de | 16 | the race end's two instructions → `jsr rankgate3` + nops |
| Boot | 0xff479b..0xff479e | 3 (of the six of 0xff4799) | `jsr hudname` → `jsr hudorig` |
| Program | 0x2797ec..0x2797f7 | 9 of 12 | the reverse table's words of entries 0-2 (were 0) |
| Program | 0x28f7d0..0x28f822 | 82 | the originals' block, on erased ROM (reserved to 0x28f870) |
| Program | 0x2b92a0..0x2b9360 | 192 | the three new load records, on erased ROM, after the seven's |
| Program | 7 × 1-2 bytes at 0x2b910c, 0x2b914c, …, 0x2b928c | 12 | **the seven's reverse load records' race pointers: + 192** |
| Program | 0x2b99ac..0x2be110 | 18 276 | the three new maps records (on erased ROM, after the seven's, which are unchanged), then the ten race blobs: **the seven's reverse race blobs lie 192 bytes higher** (three more maps records before them), the same blobs decoded, and the three new ones follow |
| Program | 0x2fce10..0x2fe734 | 6 436 (three lists of 1 700, 3 356 and 1 364 bytes) | the three reverse spawn lists, in the erased run that ends the program ROM (0x2fce00..0x300000, 12 800 bytes) |
| Data | bank 3 +0x69ad0..+0x73f30 | 42 080 | Big Forest's reverse tables, on erased ROM |
| Data | bank 2 +0xa4be0..+0xb95f0 | 84 496 | Acropolis's, on erased ROM |
| Data | bank 1 +0xfcb50..+0xffb80 | 12 336 | Bay Bridge's, on erased ROM |

- The seven converted courses: their normal records, tile tables, spawn lists, race blobs, tables in the banks, their reverse
  variants' tables, load records (but the race pointer) and maps records are where they were and the same bytes; their reverse
  race blobs moved up 192 bytes with their pointers [V, `tests/test_originals_reverse.py::test_the_originals_variants_only_add_bytes`].
- **The reservations.** The first place of the originals' block (right below the start gantry's, 0x28f910) overlapped the
  block Phase 31 reserves there for its colour entries (0x28f870..0x28f970; the bytes written missed each other by 42). It
  now lies below Phase 31's (0x28f7d0..0x28f870, 160 bytes). `tencourse.reserved_blocks` names every reservation of the
  program ROM and `check_reserved_blocks` (run by `ten_course_set`) refuses a layout in which two overlap;
  `install_origrev` and `install_reverse_spawn_lists` write on erased bytes only and stop otherwise
  [V, `test_no_two_reserved_blocks_of_the_program_rom_overlap`, `test_the_sites_and_the_block_are_checked_before_anything_is_written`].
- The run at 0x2fce00 was read-tapped (on main 2a9f1ab's set) over a reverse Big Forest race (150 s) and a normal Bay Bridge
  race (100 s): its only reader is the boot's colour-table upload (PC 0xfe6b64, the last read at frame 268), as for the
  annex's run [V, `out/p33/gates/tap_2fce00.log`]. The attract mode was not tapped. It is erased on merged main too (the
  writer checks).
- The annex now ends at 0x2be110; the direction screen's block starts at 0x2be8b0 (1 952 bytes between).
- The directory image is unchanged in size and place (the test's bound not raised).

## 3. The normal direction, Grand Prix, the attract

- **The one change of flow**: an original's course lock now opens the COURSE DIRECTION screen (`dirlock` shows it for any
  entry with a word in the reverse table). NORMAL is the default; a second press of the gas or the ten-second countdown
  confirms. The race then loads `LOCK_TO_LOAD` (198) frames after the direction lock, and with the harness's answer on the
  same frame as before (1 600) [V `tests/test_dirscreen_build.py::test_an_original_shows_the_screen`, three entries, both answers]. This is a difference from main for the three originals in single play and it is
  the feature's own: without it there is nowhere to choose reverse.
- **A normal race on each original is main's, pass for pass** [V `tests/test_originals_reverse.py::test_the_normal_game_is_the_set_before_pass_for_pass`, 3 314 passes each, no difference]: 120 s on the set before (main's bytes) under the
  autopilot, the wheel and pedal recorded; the same race on this set fed those inputs frame for frame from the same battery
  RAM (`input_tape.lua`, `pass_state.lua`): the clock and all sixteen cars' x, z, road point, speed and lap identical at the
  end of every logic pass. Big Forest, Bay Bridge, Acropolis.
- **A converted course, both directions** [V the same test, 3 314 passes each]: Metropolis normal and Metropolis reverse, the same way: identical
  pass for pass (its reverse race blob is one of the seven that moved).
- **Grand Prix** [R boot listing; V for the single cabinet]:
  - The flag: the test menu's GAME MODE (NORMAL / GRANDPRIX) is the backup byte 0x40dca3, copied to `[0x501105]` at 0xfe1b12
    at every game set-up. The 20-lap Grand Prix race is set at 0xfe1170, on the path taken only when `[0x40dc8c]` (the link
    setting) is not 0 (0xfe10ed): **Grand Prix proper is a linked-play mode.** There `dirlock` installs the game's own lock
    handler and the screen is never shown, the two linked course loads clear the flag (`bankdemo`), and the fallback path of
    `entry` never reads it [R, unchanged from Phase 26 stage 3]. **Linked play was not run** (no second cabinet in the harness).
  - On a single cabinet with GAME MODE set to GRANDPRIX the race is the five-lap race with `[0x501105]` = 1 (the Grand
    Prix's pit rules). Measured: Big Forest's normal race with that setting is main's with that setting, pass for pass
    [V the same test, 3 314 passes; `[0x501105]` read 1 in both runs' RAM dumps]. The direction screen appears there as it does for the seven on main.
  - What several older notes call "linked play" at 0xfe8be6, 0xfe968d, 0xff4090 and the loader's third time-record set is this
    flag `[0x501105]`, not the link (formats §22).
- **The attract** [V `out/p33/gates/attract_ranking.txt`: 39 lines each, identical line for line; ids shown 0, 2, 4, 1, 11, 5, 3, 12]: 420 s with no input, this set against main's: the ranking pages' log
  (`ranking_title_log.lua`: frame, data index, shown ranking id, table, title row).
- **The operator's fixed course**: not run here; `entry`'s fallback path and the SHIFT MODE SELECTOR are not touched [R].

## 4. The reverse races, measured

### 4.1 The standing 150 s (the in-tree tests, `tests/test_originals_reverse.py`) [V `out/p33/pytest/final.log`]

| Reverse, 150 s | Player | Extensions | Opponents moved / parked | Steps back, laps not counted | Leader's points | Cursor lead max | Opponent jolts | Yaw within 45° of the quad's direction |
|---|---|---|---|---|---|---|---|---|
| Big Forest | 2 laps | 6 | 15 / 0 | 0, 0 | 849 | 6 | 7 | 6 586 of 6 764 frames (normal 6 527 of 6 702) |
| Bay Bridge (one line) | 1 lap | 5 | 15 / 0 | 0, 0 | 1 148 | 5 | 5 | 6 422 of 6 764 (normal 5 482 of 5 482) |
| Acropolis | 1 lap | 4 | 15 / 0 | 0, 0 | 1 223 | 4 | 7 | 6 617 of 6 764 (normal 6 676 of 6 764) |

The loader served each variant's own race blob (the time-record and checkpoint pointers in the RAM dump are the blob's), the
player starts on road point 0, and at the green every opponent stands on its grid point (§5.2).

### 4.2 To the race's own end (the autopilot is slower than the clock allows, so every race ends on time out) [V, `out/p33/gates/final_races.log`, `full_races.log`]

| Race | Ends after | Player | Extensions | Opponents moved / parked | Laps not counted / steps back | Leader's points | Cursor lead max | Opponent jolts |
|---|---|---|---|---|---|---|---|---|
| Big Forest reverse (final set) | 164.4 s | 2 laps + 304 points | 8 | 15 / 0 | 0 / 0 | 1 142 | 6 | 9 |
| Big Forest normal | 187.4 s | 3 laps + 197 | 10 | 15 / 0 | 0 / 0 | 1 371 | 6 | 3 |
| Bay Bridge reverse (final set, one line) | 141.3 s | 2 laps + 95, then the autopilot's pedal is up (§5.4) | 6 | 15 / 0 | 0 / 0 | 1 334 | 5 | 5 |
| Bay Bridge normal | 95.3 s | 0 laps, trapped at points 222-226 (this driver's known baseline) | 2 | 15 / 0 | 0 / 0 | 858 | 10 | 11 |
| Acropolis reverse (final set) | 151.7 s | 1 lap + 553 | 5 | 15 / 0 | 0 / 0 | 1 529 | 4 | 8 |
| Acropolis normal | 167.6 s | 2 laps + 197 | 6 | 15 / 0 | 0 / 0 | 1 706 | 5 | 6 |

The normal rows were run on the first build of this stage (their tables and code are main's in every build).

The order at the end is the grid's order in every race (car 15 first, car 1 last: the table's performance order), reverse as
normal.

### 4.3 Five laps to the finish, the race clock held (`VR_HOLD_CLOCK`) [V, `out/p33/gates/held_races.log`]

| Reverse, clock held | Player | Race time | Opponents' laps at the player's finish | Laps not counted / steps back | Parked | Opponent jolts |
|---|---|---|---|---|---|---|
| Big Forest | 5 laps, finished | 269.4 s | 3 (cars 1-2), 4 (3-7), 5 (8-15) | 0 / 0 | none | 10 |
| Acropolis | 5 laps, finished | 366.0 s | 4 (cars 1-6), 5 (7-11), 6 (12-15) | 0 / 0 | none | 14 |
| Bay Bridge (one line) | 2 laps, then the autopilot's pedal is up to the run's end (§5.4) | - | 7-12 in 560 s: the field raced on | 0 / 0 | none | 12 |

On Big Forest and Acropolis the order at the finish is the cars' performance order (car 15 first), as in the normal race.

## 5. Race quality: what was found and what was done

### 5.1 Big Forest's jolts (the recon's 19 against 1) [V, `out/p33/gates/full_races.log`, `trial_ab.log`]

- **What they are.** A "jolt" is an opponent's smoke counter starting: a wheel off the tarmac (its speed about halves for two
  seconds, formats §15) or a contact. Of the 26 in the eight-line race to its end (the normal race: 3): **14 at reverse road
  points 200-209** (forward 127-128), by the five cars of lines 5 and 7 (cars 9, 10, 13, 14, 15), lap after lap; 6 contacts
  with the player's car (the autopilot cannot give way; the normal race's jolts are of this kind); the rest single events.
- **Why there.** Forward points 126-133 are a left-hander whose inner (left) edge tapers in on the way out in reverse: the
  tarmac reaches lateral −10.5 at point 129, −8.2 at 128, −6.5 at 127, −5.3 at 126. In reverse every opponent leaves that
  bend 3.0-4.8 units inside its line (cars of lines 2, 5, 6 and 7 measured; forward, into the same bend, 1-2). Lines 5 and 7
  run nearest the edge there (−5.1 at point 129), so their cars were at −9.0..−9.6 where the tarmac ends at −8.2 and −6.5.
  It is not a bad link and not the eight-lane stretches: the cursor stays 0.7-1.0 points ahead of the car through it.
- **What was done.** `BIG_FOREST_REVERSE_PAIRS` (0, 1, 2, 3, 4, 6, 6, 4): the cars of lines 5 and 7 follow lines 6 and 4
  (−3.1 and −2.3 at that bend). Trials, the same race: eight lines 26 jolts; (…, 6, 6, 4) **9**, none at that bend, leader
  1 184 points against 1 120; (…, 2, 6, 6) 10. With the final grid, on the final set: **9** (§4.2). The same kind of choice as Metropolis's
  reverse pairs (Phase 26 stage 2), made here by measurement alone.
- **Left as it is**: in reverse the opponents cut every bend's exit some units more than forward; it only cost tarmac at that
  one taper. Whether it reads as odd from the cockpit is for the drive.

### 5.2 The reverse grids [V, `out/p33/gates/grid_baseline.log`, `grid_trials.log`, `final_runs.out`]

- **Found**: on the game's grid (car k on road point k of its line) the reverse start had opponents standing turned at the
  green: Big Forest 3 cars (25-41 degrees), Acropolis 10 (11-50), Bay Bridge's one line 10 (31-56, seven of them off the
  tarmac within three seconds). The cause is stage 2's (bank 1): the game's cars share their lines in twos and threes and
  stand one point apart (8-10 units); a car directly behind another on its line is turned towards a corner of its line
  point's quad, which in reverse lies behind or beside it. (The arcade's own normal Acropolis grid has seven cars at 10.9
  degrees for the same reason, forwards.)
- **Trials**:

  | Grid | Big Forest | Bay Bridge (one line) | Acropolis |
  |---|---|---|---|
  | the game's (car k on point k) | 3 turned, worst 40.8° | 10 turned, worst 56.2°, 7 early jolts | 10 turned, worst 50.0°, 2 early jolts |
  | lines interleaved within points 1-15 | **0 turned, worst 1.6°** (six lines; 2.8° on eight) | none exists (one line) | 6 turned, worst 45.1° |
  | car k on point 2k | 4 turned (10-16°), 3 early jolts: its road bends from reverse point 24 | **0 turned, worst 4.4°** | **0 turned, worst 3.9°** |

- **Built**: `ORIGINAL_REVERSE_GRID`: Big Forest interleaved (the front of the grid becomes cars 12, 15, 11, 14, 10, 13),
  Bay Bridge and Acropolis two points a car (the game's order; the front car 30 points, about 240 units, ahead of the
  player instead of 120). On the final set: 0 turned on all three, worst 1.6 / 4.4 / 3.9 degrees; one early jolt each on Bay
  Bridge and Acropolis (car 1, beside the player, 325 frames after the green).
- This is a difference from the normal race that Pascal has not seen: their decision (§11, new).

### 5.3 Bay Bridge on one line (the stopgap)

All sixteen cars on the centreline. Measured: none parked, every lap counted, leader 1 334 points in the race to the time-out
(normal, eight lines: 858 before the clock ran out under this driver), 5 jolts; the field kept racing for 560 s in the
clock-held run (7 to 12 laps a car). What cannot be measured by this harness is
how a single-file field looks and races from the cockpit. The options with their costs are the recon's §7 (one line; its
tables in bank 3 with a relocated copy of what a race reads from bank 1, one stage of its own; lines taken back from the four
converted bank-1 variants; a re-laid bank 1, ruled out by Pascal in Phase 26).

### 5.4 The autopilot's car stood still for good on reverse Bay Bridge: the test driver's pedal, not the game [V, `out/p33/runs/held_bay_bridge_rev`, `final_full_bay_bridge_rev`, `freeze_bb`]

- **What happened**, the same in the race to the time-out and in the clock-held run: on each reverse lap the autopilot leaves
  the road at the beach bend. On its third lap it stayed off the tarmac for the 128 frames and the game put it back (the
  race's first real put-back), setting it down at (−210.6, −649.9) on Bay Bridge's side road (the other arm of its fork:
  the quads flagged 2, here 466 / 467, credited forward point 323; 50 units from the centreline). From frame 9 798 the car
  did not move again, to the run's end (560 s in the held run). The fifteen opponents raced on.
- **Why**: from the put-back on, **the game's pedal cell `[0x501064]` reads 0** in every dump (255 while driving): the
  autopilot had released the pedal and never pressed it again. `autopilot.lua` lifts when its own speed estimate is above 3
  and its steering error is large; the estimate comes from the last two positions it was given, the put-back's glide left
  it high with the wheel at full lock, and at a standstill it is not refreshed. The game's side shows nothing held: the
  put-back's countdown `0x501160` is 0 (the handler is back on its driving branch, 0xfe8f1a), all four wheels read tarmac,
  the handler is the player's own, no byte of the player's entity changes between two frames 100 apart.
- **Put-backs in reverse on the originals work** [V, `out/p33/gates/putback.log`: the wheel held over from eight places a
  course, 32 runs]: the two runs that reached a put-back in reverse, Big Forest (at 261.7, −344.1) and Bay Bridge on its main
  road (at 50.5, −492.7), drove on (178 and 196 units in the next 320 frames), the first facing the race within 15 degrees.
  Acropolis and the normal controls never stayed off the tarmac for 128 frames in these runs: no put-back to judge.
- **Left**: nobody pressed the pedal after a put-back onto that side road, so that a car driven by hand pulls away there is
  inferred, not shown. Worth one try in the drive (leave the road at the beach bend in reverse, about reverse road point
  95). The same autopilot is trapped on the arcade's own Bay Bridge forwards (points 222-226, the known baseline): its
  Bay Bridge numbers measure the field, not the player.

## 6. Presentation

### 6.1 The HUD's label [V `test_the_hud_reads_the_level_word_in_reverse`, three courses; the snapshots]

The game's level word in the game's colour, cell for cell the normal race's (BEGINNER, MEDIUM, EXPERT), by `hudorig`. Without
it the variant's race blob made `hudname` print the course's name in reverse only.

### 6.2 The HUD map [V, snapshots]

The first build of this stage shifted it as the seven's reversed laps are (237.0 / 22: the interior on the left). On the
originals' own outline objects the map then ran off the screen's right edge on most of the lap (Big Forest: all but out of
view on six of the first thirty snapshots). It is built with the game's own values (149.0 / 0): the map is wholly on screen
in every snapshot looked at.

### 6.3 From behind [V, snapshots `out/p33/look/`]

`NOTE.txt` there says what each still shows. In about 450 stills of the three reverse races no see-through scenery was noticed.

- **START reads from behind** on all three (the variant's own spawn list names the converted courses' both-sided frames):
  `bigforest_6`, `baybridge_6`, `acropolis_8`. The normal race's list and gantry are the game's.
- **The C.P. banners are blank white from behind** (`bigforest_4`, `bigforest_5`, `baybridge_4`; Acropolis's from below shows
  grey with pieces of the letters' backs, `acropolis_5`). A C.P. banner seen from its front across the infield reads
  (`acropolis_4`).
- **The arrow boards are not in the reverse race** (4 and 10 entities fewer in the variant's list).
- **Acropolis's two worst stretches of the recon's scenery measure** (forward points 73-78 and 34-40) are `acropolis_6_*` and
  `acropolis_7_*`: nothing missing that I can see at this size; for Pascal's eye (C7).
- **The grids** as built: `*_1_start_grid`. Bay Bridge's is one file down the middle, two points apart.

## 7. The frame rate

### 7.1 The standing test, the three reverse originals added [V `tests/test_frame_rate.py`, all 42 tests passed (session B of §12); `out/p33/pytest/finalB/rate0/rate_summary.txt`]

| Reverse, 150 s, the centreline, the clock held | Render rate | Overrun counter 0x501148 | Worst V60 busy | Highest need | Records peak | Frames with a skipped list |
|---|---|---|---|---|---|---|
| Big Forest | 28-29 | 0 → 0 | 12 702 us | 9 708 | 9 709 | 0 |
| Bay Bridge | 28-29 | 0 → 0 | 13 963 us | 7 415 | 7 838 | 0 |
| Acropolis | 28-29 | 0 → 0 | 13 518 us | 7 504 | 7 886 | 0 |
| Big Forest, line 1 read backwards, 300 s (`big_forest_reverse_line1`, the new worst-frames test) | 28-29 | 0 → 0 | 12 997 us | **10 172** | 10 173 | 0 |

Budget 10 500 records, two vblanks 34 770 us. The other seventeen races, the three older worst-frame runs, the attract and
the three pass-for-pass races of that module passed as on main (Big Forest's normal line 4: need 9 771).

### 7.2 Big Forest's margin on the other lines, and the other two (the autopilot on each road line read backwards, the clock held) [V, `out/p33/gates/rate_lines.log`]

| Reverse, line read backwards | Big Forest (300 s) | Bay Bridge (150 s) | Acropolis (150 s) |
|---|---|---|---|
| line 0 | 9 708 | (the standing test's race) | (the standing test's race) |
| 1 | **10 172** | 8 526 | 7 605 |
| 2 | 9 518 | 7 352 | 8 386 |
| 3 | 9 576 | 7 433 | 8 045 |
| 4 | 9 828 | 7 906 | 7 417 |
| 5 | 10 152 | 7 938 | 7 979 |
| 6 | 9 911 | 7 454 | 7 774 |
| 7 | 9 826 | 7 612 | 7 779 |

The highest need of the pass (records), every run: **no frame above 10 500, no list skipped, the overrun counter still, the
render rate 28-29**, the V60 at most 13.0 ms on Big Forest, 14.9 on Bay Bridge, 13.6 on Acropolis in the race. Big Forest's
highest is at its reverse road points 38-53 (the fairground, forward points 285-300) on every line: **328 records under the
budget on line 1**, which is now a standing test (`big_forest_reverse_line1`). On lines 6 and 7 the 300 s run reaches the
finish (lap 5 at frames 16 118 and 16 396) and the results scene's load 850 frames later takes one pass of 43.7 ms, as every
race's end does on main (the standing test closes its stretch at the finish).

## 8. No best time, and no pit stop

- **`rankgate3`** [V `test_a_reverse_race_on_an_original_records_nothing`, `test_a_normal_race_on_an_original_still_records`]: a one-lap reverse race on each original, finished (the clock held, `race_end.lua`), with write
  taps on the whole ranking area of the battery RAM (0x40e000..0x40fdff: every table, slot, attract counter and the reverse
  block) from the race load to the attract: **no write in any best-time table or slot** (the area's other writes are the
  game's bookkeeping at 0x40e8f0 every frame and the attract's own cells), no name entry (mode 0x1e), then the attract. The control, a normal
  one-lap race on Big Forest on the same set: its table 0x40e480 is written and the name entry comes.
- **The pit lane** [V `test_the_pit_lane_does_nothing_in_reverse`: Big Forest 422 frames on 30 lane quads, Acropolis 176 on 28]: a reverse race driven along the pit lane on Big Forest and on Acropolis (in by the normal
  exit, out by the normal mouth): the car crosses the lane's quads lap after lap, its handler is never the pit's, the stops
  left read 0 from the green on, the laps count. A reverse car cannot enter a pit stop, broken or otherwise.
- Not looked at: what the pit building and the crew's place look like from a car driving the lane backwards.

## 9. Open, by the stage's scope (each with what was measured)

(Stage 2 built three of these rows: the pit stops, the C.P. banners and the word REVERSE: §15.)

| Item | State | Measured |
|---|---|---|
| Pit stops in reverse (Big Forest, Acropolis) | not built; the lane does nothing (§8) | recon §6.1: pairs 58/59 and 54/55, the box turned half a turn; not run |
| Best-time tables for the originals' reverse | not built; nothing is recorded (§8) | recon §6.6: 78 bytes free, 300 needed; ten 3-entry tables fit (769 of 787) |
| Bay Bridge's eight lines | one line (§5.3) | recon §7 |
| C.P. banners from behind | blank white (§6.3); START reads (built) | recon §5.2: four C.P. lists of 168 960 bytes |
| Scenery faces seen from behind | not backed | recon §4: about 0.1 % of the view; nothing missing noticed in the snapshots of §6.3 |
| The word REVERSE under the HUD label (Phase 32) | not built here (§10) | - |

## 10. The word REVERSE under the level word (Pascal's C5): the follow-up that lands after Phase 32 is merged

(Built in stage 2, §15.3, as planned here but for one cell: the word is right-aligned to the level word's visible letters.)

Not built here: Phase 32 (`phase32-hud-reverse`, kept by Pascal, in its fix wave) is not in this branch's base, and its text
does not exist here. Read in its tree (not changed), and as its reviewer put it to this branch:

- **Why it belongs in `hudorig`, not in Phase 32's `hudname`.** A reverse race on an original does NOT take `hudname`'s
  `race == 0` path: the variant has a race blob. On this branch the HUD site calls `hudorig`, which for "flag set and menu
  entry below 3" jumps straight to the game's printer; `hudname`, where Phase 32 prints REVERSE after a name, never runs for
  ids 0..2 in reverse. Merged as both stand, a reverse original shows the level word and no REVERSE.
- **The change, in `origrev.hudorig`, on the "flag set and menu entry < 3" path, in place of `jmp printer`:**
  1. `jsr printer` (the game's word, entered as the site entered it);
  2. save `[0x501434]` (through R2 and a push) and set it to 0x82 (Phase 32's red, on every course);
  3. `add.w #0xF2, R1` (from one past the word's 8th cell on row 44 to REVERSE's first cell on row 46);
  4. `mov.w #hudrev, R0` (Phase 32's 8-byte text, the directory layout's key `hudrev`); `jsr printer`;
  5. restore `[0x501434]`; `rsr`.
  The exit state is `hudname`'s reverse exit: R0 and R1 are rewritten at 0xff47af / 0xff47b6 before any read, R2 the game's
  word, R3 0, no flag read before `test.b` at 0xff47c3; the printer writes R0-R3 and R8 only and uses no stack.
- **The step 0xF2 holds because the game's three words are all 8 cells**: "BEGINNER", " MEDIUM ", " EXPERT " [R, `tests/test_hudname_build.py` `GAME_WORDS`,
  read off the screen by that test]. MEDIUM and EXPERT end in a space, so REVERSE's last letter will sit one cell to the
  right of theirs: to be shown to Pascal in a snapshot when it is built.
- **Room**: about 45 bytes more. The block is reserved at 160 bytes for it (82 used), so it does not move again.
- **Mechanics at the merge**: `install_origrev` takes `hudrev`'s address from the layout; it already checks that HUD_SITE holds
  `jsr hudname` at the layout's address, so it follows a moved or longer `hudname`. Phase 32 lengthens the directory image
  past its nine spare bytes, which moves the seven's tile tables, race blobs and spawn lists (its own enumeration). Both
  branches edit `tests/test_directory.py`. Tests to add then: the HUD rows 46-47 of a reverse original against a converted
  course's, and the normal race's rows untouched.

## 11. The eight decisions: Pascal's answer, and what is built

Pascal's answer to the eight decisions (15 Nov), put to them by the session lead as the list below, each with the recommended
answer; their reply, exact words: **"Yes all your recommendation"**. It is a yes to the recommendations as worded here, nothing
more.

- C1 Bay Bridge reverse with all 15 opponents on one racing line for now: yes; drive it, then decide on moving it to a bigger bank.
- C2 Best times for the originals in reverse: three per table on all ten reverse courses (the seven lose their fourth entry),
  decided before the next release. Not in stage 1: a reverse race on an original records nothing for now; the next stage.
- C3 Banners: START lettered from behind now (the both-sides copy already in the ROM, through a variant's own spawn list: to be
  tried in this stage, and reported rather than pursued if it is not cheap); the checkpoint banners later.
- C4 Arrow boards in reverse: removed (in the reverse variant only; the normal race untouched).
- C5 HUD label on the originals in reverse: the same level word as the normal race, with REVERSE under it. The word REVERSE is
  Phase 32's feature (`phase32-hud-reverse`, kept by Pascal, red on every course) and is not built here.
- C6 Pit stops in reverse on Big Forest and Acropolis: yes, as a second stage; the pit entry disabled in reverse for now.
- C7 Scenery backs: to be judged at Pascal's first drive; nothing built; the worst places (Acropolis points 34-40 and 73-78)
  in the snapshots.
- C8 Big Forest in reverse starts on the grid, not with the pit crew: yes.

| # | Built in stage 1 | Evidence | Left |
|---|---|---|---|
| C1 | Bay Bridge on one line, called a stopgap in the build report, the tests and the deviations | §4, §5.3 | their drive; the bank question (recon §7) |
| C2 | nothing recorded (`rankgate3`) | §8 | the next stage: ten 3-entry reverse tables (recon §6.6: 769 of the 787 bytes; a new tag, the reverse block made again once; the setter's ids 0..2; `revtitle`'s titles for the originals; `rankgate3` removed) |
| C3 | **START reads from behind**: each variant has its own spawn list whose start gantry draws the both-sided frames | §6.3; it was cheap: 6 420 bytes of an erased run, no code | the four C.P. gantry lists (recon §5.2) |
| C4 | **the arrow boards are not in the reverse race** (Big Forest 4, Bay Bridge 10): the same spawn list | §6.3 | - |
| C5 | the level word (`hudorig`) | §6.1 | REVERSE under it: Phase 32's, §10 says what it must change |
| C6 | no pit stop can start in reverse | §8 | stage 2 (recon §6.1) |
| C7 | nothing | the two places are in `out/p33/look/` | their judgement |
| C8 | the grid start (`startbit`, as reverse Alpine) | §4 | - |

**What the build found that the eight answers do not cover: three things Pascal has not been asked** (each a builder's choice by
measurement, each one table to change):

- **The reverse grid is not the game's** (§5.2). Is a grid twice as long on Bay Bridge and Acropolis, and another order at the
  front on Big Forest, acceptable in reverse? The alternative measured is 3 to 10 cars standing turned up to 56 degrees at the
  green. Recommended: yes, as built.
- **Big Forest's opponents on six of its eight lines** (§5.1). Recommended: as built; judge at the drive.
- **The HUD map in the game's own place**, not shifted as the seven's reversed laps are (§6.2). Recommended: as built.

**Answered on 16 Nov.** The lead put four questions to Pascal with a recommendation each: (1) the REVERSE label: merge it
(Phase 32); (2) the reverse starting grids on the originals as built: keep; (3) Big Forest's reverse opponents on six of eight
lines: keep; (4) the HUD map on the originals in reverse left in the game's own place: leave. Their answer, exact words:
**"Yes to all"**. So the three questions above are answered: as built. It is not a word to merge Phase 33.

Also new against the recon: an original's reverse race keeps the game's own time records (the game pays one extension at every
checkpoint, 331 or 457, whatever the sector's length; the converted courses' rule would have given Bay Bridge 468, 259, 266).

## 12. Tests

- **New**: `tests/test_reverse_original.py` (10, synthetic), `tests/test_originals_reverse.py` (35: the routines, the
  build against the set before, and in MAME the reverse race, the grid, the quads' direction, the HUD word, the pit lane, no
  record with its control, and the game the same pass for pass on the three originals, with GRANDPRIX and on Metropolis both ways).
- **Changed deliberately**:
  - `tests/test_tencourse.py` `BANK_ONE_FLOOR` 13 000 → **1 000** (Bay Bridge's one-line variant takes 12 336 of bank 1's
    13 488; 1 152 are left);
  - `tests/test_dirscreen_build.py`: "an original never shows the screen" → `test_an_original_shows_the_screen` (three
    entries, both answers);
  - `tests/test_reverse_build.py`: every entry has a reverse record; `_annex` spans all ten; the three tests of "the flag on
    an entry without a variant" (Bay Bridge, Big Forest's pit start, Acropolis's figures) and "the variant only adds bytes"
    run on the set without the originals' variants (`_seven_plain`: main's bytes);
  - `tests/test_hudname_build.py`: the records test counts ten variants; `tests/test_race_build.py`: the course select's lock
    look on an original is dumped on the set without the originals' variants (`_select_run(plain=True)`);
  - `tests/test_frame_rate.py`: the three originals in reverse in `COURSES` (20 races), a line by its number and `big_forest_reverse_line1` among the worst known frames.
- **Not raised**: the directory image's bound (6 900; the image is 6 895 as on main).
- **The final invocation and its result**: not the whole suite (by instruction), and not one invocation: twelve modules, 378 tests collected,
  run in sessions because of their length, each building the ten-course set afresh from the tree (about twelve minutes) with
  `VR_MAME_JOBS=1`, `-s -p no:cacheprovider -rfE --basetemp=out/p33/pytest/<name>`. The tree's `vrtools/` is the same in all
  of them (unchanged since the rebase commit); between sessions only tests were corrected.

  | Session (log in `out/p33/pytest/`) | What | Result |
  |---|---|---|
  | A `finalA.log` | `tests/test_reverse_original.py tests/test_originals_reverse.py tests/test_tencourse.py tests/test_directory.py tests/test_hudname_build.py tests/test_dirscreen_build.py tests/test_reverse_build.py` (stopped by hand once it entered `test_frame_rate.py`, which session B was running): 227 tests | 205 passed, 17 skipped (they need unidasm), **5 failed, each a test's own expectation, corrected and passed below**: the three no-record tests (they asserted no write in the whole battery area, where the game's bookkeeping and the attract's cells are written), the Acropolis pit-lane test (a floor of 200 frames in the lane; 176 in its one lap), `test_hudname_build.py::test_the_load_records_carry_the_names_the_hud_prints` (it counted seven variants) |
  | B `finalB.log` | `tests/test_frame_rate.py tests/test_race_build.py tests/test_start_gantry.py tests/test_ranking.py tests/test_reverse_ranking.py`: 151 tests | **129 passed, 18 skipped, 4 failed**: three are names of `out/p27/full_failed.txt` (`test_race_build.py::test_a_hard_steer_into_diablos_first_right_turn_meets_the_wall[at0]`, `[at1]`, `::test_the_player_pitch_is_smooth_on_diablo`); the fourth is new and is this stage's: `test_race_build.py::test_start_on_an_original_greys_its_neighbours` dumped the course select's lock look on Acropolis, where the direction screen now opens at once. It runs on the set without the originals' variants now (session D) |
  | 2 `final2.log` | the three no-record tests and their control, the reservations test, `tests/test_frame_rate.py::test_the_worst_known_frames_hold_the_arcade_rate` (four runs, the new `big_forest_reverse_line1` among them) | 9 passed |
  | C `finalC.log` | `test_the_pit_lane_does_nothing_in_reverse` (both courses), the HUD records test | 3 passed |
  | D `finalD.log` | `tests/test_race_build.py::test_start_on_an_original_greys_its_neighbours` | 1 passed |

  **By name against `out/p27/full_failed.txt`** (15 names): of the modules run, that list names three tests, all in
  `test_race_build.py`, and those three failed here as there. No other test of the twelve modules fails on the final tree.
  The list's twelve other names are in modules not run (`test_convert_collision.py`, `test_convert_geometry.py`,
  `test_convert_profile.py`, `test_tgp_build.py`). Not run at all: every other module of the suite (`test_cli.py` among
  them, whose build report count was read, not run).

## 13. Not verified

0. **A put-back onto Bay Bridge's side road in reverse, driven by hand** (§5.4): the autopilot's stop there was its own
   pedal; that a car pulls away there under a pressed pedal is inferred.
1. **(Stage 1, as written then.) Pascal has not seen or driven any of it.** Every race measure is the autopilot's: it cannot overtake, it follows road
   line 0, on Bay Bridge it leaves the road at one beach bend each reverse lap and is put back, and forwards it does not
   complete a lap of Bay Bridge at all (the known baseline). No human judgement of the grid, the single file, the lines.
2. Linked play and the linked Grand Prix: not run; by reading only (§3).
3. The operator's fixed course; the service-mode ROM test; real hardware.
4. A race finished on merit (the five-lap races of §4.3 have the clock held); the results screen's order.
5. The eight-lane stretches in reverse: nothing stalls, parks or jolts there in the runs, but which way a car moves when it
   changes lane was not looked at.
6. The pushes that use the forward-authored edge values (every reverse race's known limit, stage 1 findings §4).
7. The frame's need on the lines not driven by the standing test is measured once each (§7.2), not as a standing test
   (Big Forest's worst line is one); nothing was added to the reverse view in this stage.
8. The scenery from behind: the recon's offline measure and the snapshots of §6.3; no systematic comparison.
9. The start figures on the two-point grid (Acropolis): seen round the car in the snapshots; their animation was not measured
   again (stage 2's test is on Diablo Canyon and Metropolis).
10. What Phases 29, 31 and 32 take of the same ROM regions; a merge with Phase 32 (§10).
11. The whole suite was not run (by instruction): §12 has what was.

## 14. Artefacts (git-ignored)

| Path | What |
|---|---|
| `out/p33play1/` | the playtest set (the build report beside it) |
| `out/rec166/launch.sh` | the launcher, modelled on `out/rec163/launch.sh` (its `start/` copied; `inp/` empty; records `inp/play.inp`) |
| `out/p33/look/` | snapshots for Pascal, 1440 × 1080, with `NOTE.txt` |
| `out/p33/gates/` | `bytes.txt` (§2), `full_races.log` and `final_races.log` (§4.2), `held_races.log` (§4.3), `trial_ab.log`, `grid_baseline.log`, `grid_trials.log` (§5), `rate_lines.log` (§7.2), `attract_ranking.txt` (§3) |
| `out/p33/build/` | `base` (the tree before this stage: main's set), `plain` (`originals_reverse=False`: main's set), `final` (this set), the trial sets |
| `out/p33/pytest/` | the test sessions' logs and work directories |

## 15. Stage 2 (16 Nov): the checkpoint banners, the pit stops, the word REVERSE

### 15.0 What Pascal said, and what they drove

- 16 Nov, after two runs of `out/p33play1` through `out/rec166/launch.sh` (65 s and 70 s, MAME's average speed 100.00 % in
  both), exact words: **"reverse on original track is good but: - some checkpoint flags are white without the C.P. the pit
  isnt working. relaunch"**.
- After a third run (22 s, 100.02 %): **"reverse is not showing in the reverse track during gameplay, relaunch"**. A fourth
  run followed (49 s, 100.00 %). The lead told them the set did not hold the label's branch; they asked "what are the other
  quesitons?" and answered the four put to them **"Yes to all"** (§11).
- Their "Yes all your recommendation" of 15 Nov had put the C.P. banners and the pit stops in a later stage (C3, C6). The
  16 Nov message REPORTS two faults; it asks for nothing. It was the session lead who brought those stages forward on it.
  None of this is a word to merge Phase 33.
- **Which courses they drove was not said.** Established here by replaying the four recordings
  (`out/rec166/inp/pascal-2026-11-16-p33origrev-*.inp`) headless on `out/p33play1` from the launcher's own start state
  (`out/rec166/start`, copied), a Lua logging the mode, the menu entry `[0x501940]` and the direction flag `[0x502294]`
  [V, `out/p33/replay/*/modes.txt`]: run 1 raced entry 9 (Surfers Road), flag 0 (normal); run 2 **Big Forest in reverse**
  (entry 0, flag 1); run 3 Diablo Canyon in reverse (entry 5); run 4 **Acropolis in reverse** (entry 2). So the first message
  followed one reverse race on an original, Big Forest's; the replays' average recorded speed read 99 %. What they saw on the
  screen is not in a recording.

### 15.1 The checkpoint banners read C.P. from behind [V, stills `out/p33/look/stage2/`, `test_each_checkpoint_gantry_has_a_list_with_its_lettering_behind_the_banner`]

- **Which read and which did not** (stage 1's set, a reverse lap of each, stills): none of the six. Every checkpoint banner a
  reverse driver passes (two a course: reverse road points 108 and 218 on Big Forest, 197 and 306 on Bay Bridge, 169 and 382
  on Acropolis) showed no lettering from behind: Big Forest's and Bay Bridge's white, Acropolis's grey with pieces of the
  letters' backs. START read (stage 1).
- **Built**: the game's four checkpoint object lists (0xfdc0b3 and 0xfdc1b3: Big Forest's and Bay Bridge's; 0xfdc133 and
  0xfdc233: Acropolis's) each get a list of 32 frames in the reverse spawn lists' run (4 × 1 024 bytes from 0x2fce10): frame
  k is the game's own frame followed by one more object holding the frame's 23 letter quads mirrored left to right about the
  banner's centre and set as far behind the banner as they stand in front, one-sided, on the colour entry the game's letters
  read (`gantry.install_checkpoint_lettering`; no new colour entry). The variants' spawn lists name these lists; the normal
  race's lists, frames and gantries are the stock ROM's.
- **Polygon ROM**: 128 objects, 243 712 bytes, all on erased bytes; 426 472 → **182 760** bytes free (the floor is 65 536).
  They are installed after every other polygon writer (Phase 31's far copies), so nothing of main's moves.
- **After**: all six read "C.P." the right way round in a reverse lap (twelve stills, before / after).
- Frame cost: 46 records more in a frame with a gantry in view; the need near the six gantries is at most 6 809 records
  (§15.4).

### 15.2 Pit stops in reverse on Big Forest and Acropolis [V, `test_a_reverse_race_has_a_working_pit_stop`, `out/p33/s3/pit_*`]

Modelled on Phase 26 stage 4: the variant's record carries a pit quad and a pit box, and that phase's routines (`pitbox`,
`pitaim`, `pitpark`, `pitstops`, `crewturn`) serve it with no new code (`tencourse.original_reverse_pit`).

| | Normal pit quad | Lane quads (flag 66) | Reverse pit quad (pair) | Box (the game's own table) | Box heading |
|---|---|---|---|---|---|
| Big Forest | 30 | 30-59 | **58** (58, 59) | (-230.38, 30.0, -269.57), 0xff40d9 | 0x8000 |
| Acropolis | 28 | 28-55 | **54** (54, 55) | (-346.42, 3.70, -58.96), 0xff40b1 | 0x8000 |
| Bay Bridge | none | none | none: the game has no pit lane there | - | - |

Measured, the same lane driven both ways on the stage 2 set (the autopilot along the lane, the clock held, 200 s):

| | Big Forest reverse | Big Forest normal | Acropolis reverse | Acropolis normal |
|---|---|---|---|---|
| Stops granted at the green | 2 | 2 | 2 | 2 |
| Pit handler from quad | 59 | 30 | 55 | 28 |
| Handler states, in order | 1, 2, 3, 4 | 1, 2, 3, 4 | 14, 15, 16, 4 | 14, 15, 16, 4 |
| Drive up the lane to the box (frames) | 370 | 356 | 270 | 350 |
| On the box to the release (frames) | **442** | 442 | **442** | 442 |
| Parked at | the box | the box | the box | the box |
| Yaw on the box | 0x8000 | 0 | 0x8000 | 0 |
| Crew | 5, turned half round about the box | 5 | 6, turned | 6 |
| Stops left after | 1 (a second stop on the next lap: 0) | 1 | 1 | 1 |
| Lap counted after the release | yes, 244 frames on | (counted just before the stop) | yes, 244 frames on | (before the stop) |

**What differs from a normal stop, plainly**: (a) the lane is entered by the normal race's pit exit and left by its entry;
(b) the stop falls at the END of a reverse lap, just before the line, where the normal race has it just after the line; (c)
the car and the crew stand turned half round on the same box. PIT WORK shows, the time on the box is the same to the frame,
the stops count down the same, the laps count. REVERSE and the level word stay on their cells through the stop (no write
reaches them). **Not measured**: the tyres' state after the stop by itself (the game's own stop routine runs to its end);
opponents in the lane in reverse; a stop driven by hand.

### 15.3 REVERSE under the level word [V, `test_a_reverse_race_shows_reverse_under_the_level_word`, stills]

`origrev.hudorig`, the reverse-original path, now: `jsr` the game's printer (the level word, entered as the site entered it);
the colour cell `[0x501434]` saved through R2 on the stack and set to Phase 32's red (0x82); R1 + 0xF2 (Phase 32's step:
two rows down, seven cells back), less one cell on entries 1 and 2; R0 = the layout's `hudrev` (Phase 32's text); the printer
again; the cell written back; `rsr`. The exit state is `hudname`'s reverse exit. `hudorig` is 96 bytes, the block 146 of its
160; it did not move.

- **Where the last letter sits**: under the level word's last visible letter on all three: column 58 under BEGINNER's R (Big
  Forest: columns 52-58, where the seven have it), **column 57** under the M of " MEDIUM " and the T of " EXPERT " (Bay Bridge,
  Acropolis: columns 51-57; the game stores those two words with a space after them). The right-alignment the lead asked for
  "if cheap and clean" cost one compare, one branch and one subtract (10 bytes); without it the word stood one cell right of
  the M and the T. Rows 46-47, the game's red, as on the seven.
- Present at the race load, 60 frames in and at every 500th frame of a reverse race on each of the three; rows 46-47 blank
  from column 19 in the normal race; rows 44-45 the same cells in both; no write to those cells during the race; the colour
  cell the game's after the print in both; through a pit stop on Big Forest and Acropolis (§15.2).
- `check_reserved_blocks` is green with Phase 32's bytes in the tree (the directory image is Phase 32's; the block is where it
  was, 0x28f7d0).

### 15.4 The frame rate [V, `tests/test_frame_rate.py`, `out/p33/s3/`]

| Run on the stage 2 set (the clock held) | Highest need (records) | Under the budget of 10 500 |
|---|---|---|
| Big Forest reverse, road line 1, 300 s (the worst line of stage 1) | **10 172**, at reverse road point 42 (the fairground), as in stage 1 | **328**, unchanged: the worst frame has no gantry in view |
| Big Forest reverse, a lap through the pit lane with two stops | 10 052 (road point 42 again); 8 420 during the stop | 448 |
| Acropolis reverse, a lap through the pit lane with stops | 7 981; 7 170 during the stop | 2 519 |
| Reverse laps, within 150 frames before each checkpoint gantry | at most 5 968 (Big Forest), 5 225 (Bay Bridge), 6 809 (Acropolis) | 3 691 or more |

No list skipped, the budget 10 500 in every frame, in all of them. The standing test gains a reverse pit lap on Big Forest
and on Acropolis among the worst known frames (`big_forest_reverse_pit`, `acropolis_reverse_pit`).

### 15.5 The bytes and the normal direction [V, `out/p33/gates/bytes_s2.txt`]

- The comparison set: this tree built with `originals_reverse=False` is **`out/p32play2` byte for byte** (every ROM file;
  Phase 32's play set; main c94d7d9 is this tree less this branch, and the switch turns this branch's part off).
- Against it the stage 2 set differs in: the boot ROM's two sites (16 and 3 bytes); in the program ROM the reverse table's
  three words, the block (146 bytes, erased before), the seven's race pointers and the annex as in stage 1, and the run
  0x2fce10..0x2ff734 (the four lettered lists and the three spawn lists, erased before); in the data ROM the three variants'
  tables (erased before); in the polygon ROM 243 239 differing bytes in 0xf97e74..0xfd3674, all erased before. TGP data and
  program: identical. No unnamed byte.
- **Normal races on all ten courses are the comparison set's pass for pass** on the same inputs
  (`test_the_normal_game_is_the_set_before_pass_for_pass`: ten courses, Big Forest with GRANDPRIX, Metropolis in reverse).
- The normal race's collision: not written (0 TGP words; the data banks' original content untouched).

### 15.6 A reverse lap is not stage 1's frame for frame: traced by the reviewer

A reverse lap of Big Forest and of Acropolis on the stage 2 set is not the stage 1 set's frame for frame under the same
autopilot (Bay Bridge's is, for all 150 s). As first written here the first difference was given as a road point credited one
frame later at frame 3104 on Big Forest: that was the first difference of position or road point; the first difference of
any logged field is earlier. Corrected:

- **Big Forest: frame 2912**, the off-course counter `0x50115c` stepping one video frame later (5 against 6), positions
  identical [V here, `out/p33/s3/lap_big_forest_*`: the first differing sample]. Acropolis: frame 2372, a road point one frame
  later [V here]. The runs part physically at frames 3792 and 3576 [V here].
- **The cause, by the reviewer's scratch variants built from 10ca0dc (150 s reverse laps; their measurements, not run again
  here)**: Big Forest's stage 2 set WITHOUT the pit record is the stage 1 set frame for frame, so the pit record is a cause
  (confirmed). The checkpoint lettering ALSO changes runs: Big Forest's parts at frame 3468 (physically at 4672), Acropolis's
  physically at 3520; and Acropolis without the pit record differs from stage 1 in one road-point sample (frame 3320).
- **What it is**: a shift of WHEN within a logic pass a value is written (the code that runs for a pit record, and the longer
  display list, move a write across a video frame's end, where the Lua samples it; the autopilot then steers on a value one
  frame older and the races part). **Not a lost pass**: the overrun counter stands still and the V60 is busy about 10.4 ms a
  pass in these runs. The normal direction is not touched by either (pass for pass identical, §15.5).

### 15.7 Tests

- New or rewritten in `tests/test_originals_reverse.py`: the block's sizes and `hudorig`'s shape; where REVERSE stands; the
  variants' pit quads and boxes; the lettered lists; the spawn lists naming them; the bytes (the polygon ROM written on erased
  bytes only); `test_a_reverse_race_shows_reverse_under_the_level_word` (three courses); `test_a_reverse_race_has_a_working_pit_stop`
  (Big Forest, Acropolis; it replaces `test_the_pit_lane_does_nothing_in_reverse`); Bay Bridge has no lane; the pass-for-pass
  test on all ten courses.
- `tests/test_frame_rate.py`: the two reverse pit laps among the worst known frames.
- Absent in a normal race: also Phase 32's own `test_a_normal_race_shows_no_word` on entries 0-2, which runs on this set.
- The final invocation and its result: one invocation on commit 1b64d5a, the ten-course set built from the tree by
  the session, `VR_MAME_JOBS=2`, `VR_MAIN_SET=out/p35play1`, `-s -p no:cacheprovider -rfE --basetemp=out/p33/pytest/s2gate`:
  `tests/test_reverse_original.py tests/test_originals_reverse.py tests/test_frame_rate.py tests/test_hudreverse_build.py
  tests/test_hudname_build.py tests/test_start_gantry.py tests/test_reverse_build.py tests/test_dirscreen_build.py
  tests/test_directory.py tests/test_tencourse.py`: **299 passed, 17 skipped, 0 failed** in 2 h 18 min (316 collected; log
  `out/p33/pytest/s2gate.log`). The twelve pass-for-pass runs: no difference. Not in the invocation: `tests/test_race_build.py`
  (the three known failures of `out/p27/full_failed.txt` live there), `tests/test_pit_build.py`, the ranking modules and the
  rest of the suite.

### 15.8 Not verified in stage 2

1. **Pascal has not driven this set.** Every measure is the autopilot's.
2. The tyres' state after a reverse stop by itself; opponents entering the lane in reverse; a stop on a lap other than the
   first two; a stop entered at an angle or too fast by hand.
3. (§15.6 was traced by the reviewer; see there.)
4. Linked play, the operator's settings, real hardware; a monitor's overscan on rows 46-47 (Phase 32's own open point).
5. The whole suite (by instruction: once per batch, by the lead).

### 15.9 Artefacts (git-ignored)

`out/p33play2/` (the set), `out/rec166/launch.sh` (now on it; `launch-p33play1.sh` is the stage 1 launcher; `inp/` untouched),
`out/p33/look/stage2/` (25 stills and `NOTE.txt`), `out/p33/gates/bytes_s2.txt`, `out/p33/s3/` (the runs), `out/p33/replay/`
(the recordings' replays), `out/p33/build/` (`base3`, `plain3`, `s3`).

## 16. The fix wave after the review of 10ca0dc (16 Nov)

### 16.0 Pascal on the stage 2 set (`out/p33play2`), their words exactly

- One run, 85 s, MAME 99.99 % (`out/rec166/inp/pascal-2026-11-16-p33play2-85s.inp`). The lead had given them a numbered list to
  test: 1 checkpoint banners read "C.P." in reverse; 2 a pit stop in reverse on Big Forest or Acropolis; 3 REVERSE under the
  level word; 4 Bay Bridge in reverse (does the single file bother you; leave the road at the beach bend, be put back, drive
  on); 5 a normal race on one original. Their answer: **"1)fixed. 2) working. 3) looks good nice 5) single file doesnt bother
  me for beach i need a relaunch to try again 5) another relaunch"**. (Their two "5)" are as typed; the first evidently answers
  the lead's item 4.) So the beach put-back and the normal race were not yet tried; Bay Bridge on one line stays as built for
  now and the eight-line bank move is not asked for.
- Two more runs: 59 s (100.00 %, `...-59s-2.inp`) and 44 s (100.00 %, `...-44s-3.inp`). Asked whether the beach put-back on
  Bay Bridge in reverse let them drive on, and whether they noticed wrong colours on the direction screen: **"i think bay
  bridge work but the colors in the track select looks bugged with ping highlighted on the track"**. ("ping" as typed;
  evidently pink: Bay Bridge's magenta on the direction screen. They call it "the track select"; whether they also saw a
  fault on the course select itself is not established: §16.1 has the course select's check.)
- A fourth run, asked "relaunch for a normal race": 75 s, MAME 99.71 % (other jobs running; `...-75s-4.inp`). Asked how the
  normal race on the original was: **"normal race look fine"**. Which original was not stated.
- None of it is a word to merge.
- **What the four recordings hold** [V, replayed headless on `out/p33play2` from the launcher's start state with a Lua logging
  the mode, the entry, the flag, the player's position, the pit handler and the off-course counter;
  `out/p33/replay/p2_*/modes.txt`]:

  | Run | Course, direction | What the replay shows |
  |---|---|---|
  | 85 s | Big Forest, reverse | past both checkpoint gantries; into the pit lane, the pit handler on the box (frames 3 900-4 200), released, lap 1 counted |
  | 59 s | Big Forest, reverse (not Bay Bridge) | one put-back, at frame 3 623 at (-107.7, 602.5), road point 226, as the recording ends |
  | 44 s | Bay Bridge, reverse | one put-back, at frame 2 538 at (9.2, -387.9), road point 119: on the main road, NOT the side road of §5.4; 162 frames later the car is at (-70.8, -409.0), so it moved on |
  | 75 s | Big Forest, normal | a normal race; one put-back at frame 4 104, road point 302 |

  So "i think bay bridge work" rests on one put-back on Bay Bridge's main road; the side-road spot was not met by them (§16.4).

### 16.0a Pascal on the fixed direction screen (`out/p33play3`), their words exactly

- 16 Nov, `out/p33play3` through `out/rec166/launch.sh`, one run, 42 s, MAME 100.01 % (`out/rec166/inp/pascal-2026-11-16-p33play3-42s.inp`).
  They had been told to look for: the direction screen's pictures matching the course select on Bay Bridge, Acropolis and Big
  Forest (no pink, no cyan); the chosen picture in colour and the other grey; the course select after a race; and the
  side-road put-back on Bay Bridge in reverse. Asked whether the direction screen's colours looked right on the course they
  picked: **"direction is good"**. Which course they picked was not stated. Not a word to merge.
- **What the recording holds** [V, replayed headless on `out/p33play3` as in §16.0; `out/p33/replay/p3_42s/modes.txt`]: the
  course select moved over entries 5, 2 and 0 and settled on entry 1; **Bay Bridge, answered NORMAL** (the flag 0 at the race
  load, frame 1 022); a normal race to the recording's end (road point 130), no put-back. So they saw the direction screen of
  one original, Bay Bridge, and its lock look on NORMAL. Acropolis's and Big Forest's screens, the lock look on REVERSE and the
  course select after a race were not in this run; the side-road put-back remains untried by hand.

### 16.1 C1: an original's picture on the COURSE DIRECTION screen was drawn in wrong colours [fixed; V]

- **The fault** (the reviewer's sheet; Pascal's "ping"; visible in this phase's own stage 1 stills `out/p33/look/direction_screen_*.png`
  and not noticed or mentioned then): on the direction screen an original's picture showed flat cyan (Acropolis) or magenta
  (Bay Bridge) where the water, the track and the name belong, and Big Forest's name black. In normal-direction games too,
  since an original's lock opens the screen from stage 1 on. The course select itself was right.
- **The cause, traced** (not the palettes, as inferred): an original's select picture is the game's own TWO maps, "B" (the
  terrain, with see-through pixels; the course select has it on the front layer) over "A" (the water, the track, the name;
  the back layer). A converted course's picture is one map (Phase 21), and the screen was built for that: it drew B alone on
  the back layer, so B's see-through pixels showed the palette's colour 0.
- **The fix** (`vrtools/arcade/origpic.py`): the tile hardware has two planes and an original needs three things over one
  another (A, B, the arrow). For an original the screen puts A on the back layer and B on the front, as the course select
  does, and in the 60 cells of each arrow's 12 x 12 square that the arrow has a pixel in, a character made at build time: the
  arrow's pixels over B's, B's see-through pixels kept (A shows). Those cells' colours fit one or two palettes a side (measured:
  Big Forest 2 and 2, Bay Bridge 1 and 1, Acropolis 2 and 2), on character blocks the screen does not otherwise show (the
  middle slot's, the other two arts' A blocks). The right picture's A is a copy on another art's blocks, so that the two sides
  grey apart at the lock. Two routines, 301 bytes in a block of their own (320 bytes at 0x28f690, below the originals' block),
  entered by changing the target of two calls inside the directory image (`dirsel`'s `jsr dirdraw`, `start`'s `jmp dirdone`;
  the image keeps its length and nothing in it moves); for an entry of 3 or more both jump straight to the routine they
  replace. Data: 16 176 bytes; two originals' in the boot ROM's erased run 0xfdc845..0xfe0000 (14 267 bytes, erased in the
  original; no code of the game reads it but the test menu's MEMORY TEST, which reads the whole ROM: §17.6), Acropolis's in what
  bank 0 had left (5 392 of 6 112). (The second fix wave changed the hook and split the data: §17.2.)
- **Evidence**:
  - screen pixels, the three originals, both answers (`test_an_originals_picture_on_the_direction_screen_is_the_course_selects`,
    six runs): the course select's picture is the stock ROM's two maps composed; the direction screen's two pictures are that
    picture **pixel for pixel**, all 128 x 168 pixels but those under the yellow cursor frame, with the arrows' pixels over
    them; after the lock the chosen side is in the game's chosen palettes and the other in its grey ones. 0 pixels differ;
  - the data decoded from the built set and rendered in the three looks equals the same composition, cell for cell
    (`test_the_arrows_cells_draw_the_arrow_over_an_originals_picture`, no MAME);
  - **the course select after it**: a reverse race on Acropolis through the screen, then a second game: 300 frames into the
    second course select the pictures' characters, palettes and tile rows are byte for byte the first game's, and the first
    game's are the set's without the originals' variants (`test_the_course_select_is_the_same_after_...`). The screen leaves
    no damage behind, and the course select is main's;
  - no logic frame is lost while the screen draws or in the lock look, on the three originals (the two standing tests of
    `tests/test_dirscreen_build.py`, extended to them);
  - the seven: their screen is drawn by the code it was drawn by (the two routines jump to `dirdraw` / `dirdone`).
- **The lock look of an original on the shipped set** is this screen's (with the variants an original's course lock opens it);
  the test above is its standing guarantee. `tests/test_race_build.py`'s course-select lock look stays on the set without the
  variants, where that look still exists (and in linked play, not run).
- Stills: `out/p33/look/fixwave/` (15, with `NOTE.txt`).

### 16.2 I1: the margin under the frame budget, asserted and probed

- (Read with §17.6: the floor is a change detector, not a safety margin, and the parked views are not a worst case.)
- **Asserted** (`tests/test_frame_rate.py`): every worst-case run now asserts no skipped list, the budget 10 500 in every
  frame, and a floor under the margin (`MARGIN_FLOOR`: Big Forest reverse line 1 at least 300 under, measured 328; the reverse
  pit lap 400, measured 448; line 4 forwards 650, measured 729); and the three originals in reverse are in the "no list is
  skipped" test (`CUT_BEFORE`). §7.2 and §15.4 said "a standing test" of a margin no test asserted: now it is.
- **Probed: the car parked at the fairground peak and turned** [V, `out/p33/i1.log`, `i1b.log`; a scratch Lua holds the car's
  position and writes its yaw]: Big Forest reverse on line 1, the car held where it arrives at reverse road points 38, 40,
  42, 44, 46 on the first lap (the bunched field just ahead) and on the second (the field gone), turned through 16 directions,
  and at points 42-45 through 64: **the highest need of any parked view is 9 562** (point 46, first lap), on the second lap
  8 588. All below the moving peak of 10 172 (one frame, 2 403, between points 42 and 43 at racing speed with the field ahead;
  the same place on later laps: 9 576, 9 315). No list skipped in any.
- **Not bounded**: a static bound (the worst block of cells plus the most the cars and the HUD can add) was not derived; a
  field more bunched than the autopilot's first lap meets (it starts last and cannot overtake) was not produced. The margin
  stays 3.1 % on the one measured frame. If a view passes 10 500 the game does what main does above its own budget: it
  leaves out object lists for that frame; the rate is not at stake (the V60's worst pass in these runs is 13.0 ms of 33).
  Options if Pascal sees scenery flicker at Big Forest's fairground in reverse: thin the reverse variant's spawn list there,
  or drop the far side of the fairground from the reverse view. Nothing was changed.

### 16.3 I2: §15.6 corrected (the reviewer's trace; the first difference is frame 2912)

See §15.6.

### 16.4 I3: Bay Bridge's side road after a put-back in reverse

- **Omitted in §5.4, the reviewer's reading of `out/p33/runs/held_bay_bridge_rev/race.txt`**: after the put-back's glide the
  car is set down at about (-217.8, -650.0) on the side road, then turns a full turn with the off-course counter running up to
  about 51 over some 100 frames before it comes to rest at (-210.6, -649.9).
- **The reviewer's two pedal-held runs** (330 s, eight put-backs): all drove on; none landed on the side road.
- **Reproduced here with the pedal held** [V, `out/p33/i3.log`, the fix-wave set]: the same autopilot run to the same put-back
  (frame 9 611, taken at (-126.5, -592.2), reverse road point 95; set down on the side road, (-215.6, -651.9) at frame 9 700),
  once as it was and once with the pedal held down from frame 9 612 on. As it was: the car rests at (-210.6, -649.9) to the
  run's end (the autopilot's released pedal, §5.4). **With the pedal held: it pulls away at once** ((-209.4, -646.7) at frame
  9 800, (-188.4, -650.9) at 9 900), is back on the main road by frame 10 400 (reverse road point 108) and drives on (point
  151 by frame 12 400; the autopilot, with its pedal forced, leaves the road three more times on the way and is put back each
  time). So a car set down on that side road drives away under a pressed pedal: shown, by a forced pedal, not by a hand.
- Pascal's own put-back on Bay Bridge (§16.0) was on the main road.
- The put-back's target was not changed.

### 16.5 The minor points

- `BANK_ONE_FLOOR` is now the exact number, 1 152, asserted with `==` and its reason.
- "Its colour entries lie past every entry a record names": `test_no_record_reads_a_colour_entry_in_the_originals_blocks_or_the_spawn_room`
  reads every record of the ten entries' tile tables and every lettering object: none reads an entry inside the originals' two
  blocks or the room (the comment's "past every entry" was loose: the converted courses' entries lie above the blocks and
  below the room; what matters is that none lies inside).
- `origrev.py`'s stale text (the prototype line, "neither routine writes a register", "82 bytes") and the test's name.
- The docs: "asked for" and "brings them forward" (Pascal reported; the lead brought the stages forward); the two quotes whole
  in `deviations.md`; "neither seen nor driven" in this file, the follow-ups and the design spec.

### 16.6 The bytes [V, `out/p33/gates/bytes_s3.txt`]

Against `out/p32play2` the fix-wave set differs from the stage 2 set's enumeration (§15.5) in this more: boot ROM
0xfdc850..0xfdf270 (10 784 bytes, erased before: two originals' picture data); bank 0 +0xfe810..+0xffd20 (5 392 bytes, erased
before: the third's); program ROM 0x28f690..0x28f7d0 (the picture block, erased before) and the three bytes of each of the two
call targets inside the directory image (0x27a1af, 0x27b061). The set built with `originals_reverse=False` is still
`out/p32play2` byte for byte.

### 16.7 Tests: the final invocation

Two invocations, each building the ten-course set from the tree (`VR_MAME_JOBS=2`, `-s -p no:cacheprovider -rfEs`), main's
`build/` linked into the worktree for the disassembler while they ran (removed after).

1. **On 6d21a14, fourteen modules, 476 tests** (`tests/test_reverse_original.py tests/test_originals_reverse.py
   tests/test_frame_rate.py tests/test_hudreverse_build.py tests/test_hudname_build.py tests/test_start_gantry.py
   tests/test_reverse_build.py tests/test_dirscreen_build.py tests/test_directory.py tests/test_tencourse.py
   tests/test_ranking.py tests/test_reverse_ranking.py tests/test_race_build.py tests/test_pit_build.py`,
   `VR_MAIN_SET=out/p35play1`; log `out/p33/pytest/fwgate.log`): **462 passed, 9 skipped, 5 failed** in 3 h 26 min.
   - Three failures are names of `out/p27/full_failed.txt`: `test_race_build.py::test_the_player_pitch_is_smooth_on_diablo` and
     `::test_a_hard_steer_into_diablos_first_right_turn_meets_the_wall[at0]`, `[at1]`.
   - `test_the_course_select_is_the_same_after_...` failed on the test's own error: it compared every character of the select's
     blocks between a first and a second game, and a race leaves its own characters in the ones no picture uses (on main
     too). Rewritten to compare the set's second select with the second select of the set without the variants, byte for
     byte, and what the picture rows show with the first's.
   - `test_the_normal_game_is_the_set_before_pass_for_pass[entry2]` failed before any comparison: in that session the run on
     the COMPARISON set (main's bytes) raced Diablo Canyon, loaded at frame 1 501, instead of Acropolis at 1 605: its RAM dump
     shows the wheel centred and the menu entry 5 at the load, as if the harness had taken a race start about 300 frames early
     and let go of the wheel. **Why is not established** (the set's bytes, the battery RAM and the inputs' files are those of
     the passing runs). Rerun alone on the same tree it passes, and it passed in the stage 2 invocation and in invocation 2.
   - The 17 tests that skipped for want of the disassembler in stage 2 ran and passed. The 9 skips: 7 of
     `test_reverse_ranking.py` look for main's older sets under the worktree's own `out/` (`out/p26play6`, `out/p27play1`), 2
     of `test_race_build.py` need kept dumps and a recorded drive that are not there.
   - The session's built set is `out/p33play3` byte for byte, and its set without the variants `out/p32play2`.
2. **On the corrected tree, `tests/test_originals_reverse.py`** (log `out/p33/pytest/fwgate2.log`): **54 passed, 0 failed** in
   40 min; the twelve pass-for-pass runs (ten courses, GRANDPRIX, Metropolis reverse): 3 314 passes each, no difference.

### 16.8 Not verified in the fix wave

1. Pascal has seen the fixed screen on Bay Bridge only (§16.0a: "direction is good"); not Acropolis's, Big Forest's, the lock
   look on REVERSE, or the course select after a race.
2. The direction screen of an original in the frame between two drawing phases (a picture half drawn for one logic frame,
   as on the seven); the screen with the other select setting on an original.
3. A static bound on the frame's need (§16.2).
4. A put-back onto Bay Bridge's side road driven by a hand (§16.4).
5. Linked play, real hardware, the whole suite.

## 17. The second fix wave (16 Nov): after the second review of 44a8d3f, Pascal's put-back, the rebase onto main 1159aab

### 17.0 Pascal on the fix-wave set (`out/p33play3`), their words exactly

- "direction is good" (§16.0a; the recording: Bay Bridge, NORMAL).
- A second run after "relaunch for bay bridge reverse": 34 s, MAME 100.00 % (`out/rec166/inp/pascal-2026-11-16-p33play3-34s-2.inp`).
  The lead had asked them to go off on the side-road arm of the fork, let the game put them back, and check the car drives
  away. Asked how it went: **"it did put me back on bay bridge after a while but i ended up right in an obstacle."** (The rest
  of their message is about a different, future feature.) Not said: which obstacle, whether they could drive away.

### 17.1 The put-back into the fork's divider [V; `out/p33/replay/p3_34s*/`, `out/p33/putback/`, stills `out/p33/look/putback/`]

- **What happened, from the recording replayed headless** (per-frame log, snapshots): Bay Bridge in reverse. From the start
  they drove straight on at x -204.85 where the race road bends right, onto the fork's side arm (the quads flagged 16); the
  off-course counter began at frame 1 338 (z -114.3) and ran its 128 logic frames; at frame 1 594 (256 video frames, 4.4 s:
  "after a while" is the game's own delay, the same in either direction, 0xfebcdf `cmp.w #80`) the game took the car at
  (-204.2, -427.2) and glided it back to **(-187.25, -110.56), facing the reverse lap (yaw -32 744)**, by frame 1 678.
- **What is there**: the centre of quad 660, the last quad of the wide road before the fork. Straight ahead, four units on,
  is the nose of the fork's divider: the grey raised wedge between the two arms (course geometry, a wall in the collision; not
  a spawned object). The car, floored, hit it at once, the off-course counter ran, it was turned round (the game's wrong-way
  REVERSE came up) and after about 300 frames it was on the main arm at (-173.7, -134.4), facing the lap, where the recording
  ends. With the pedal forced after the recording's end it drives on. So: not stuck, but set down facing a wall at 4 units.
  (The test autopilot, set down there, bounced off the nose for the rest of its run.)
- **How the game picks the spot** [R, 0xfebc94..0xfebd7d, disassembled]: while all four wheels are on tarmac and the segment
  flag of the car's quad has none of the bits 0x3c, the quad is remembered (`+0x1b6`) and the counter 0x50115c cleared; else the
  counter runs, and past 0x80 the car is put on the remembered quad: its position from the TGP (command 0x1600: the quad's
  centre), its direction from the quad (0x1800; `dirattr` turns it half round in a reverse race), the glide by 0x1580. The
  same code and the same quads in both directions; no table of put-back points. In the normal direction a car put back on
  quad 660 faces away from the fork (the arms merge there); in reverse it faces the nose.
- **The same on all three, both directions, statically** (`tencourse.putback_clear`: every put-back spot's pose, probed
  straight ahead on three lines for the first point on a wall quad, or on no quad; `putback_objects`: a spawned object on
  those first units):

  | | Reverse: spots with under 10 / under 25 units clear | Normal (the arcade's own): under 10 / under 25 | An object on the pose's path (reverse; normal) |
  |---|---|---|---|
  | Big Forest | 1 / 2 (quads 60, 61: after the pit lane's end) | 6 / 10 | none; none |
  | Bay Bridge | 1 / 4 (660 at 4.0, 661, 662 before the nose; 501) | 2 / 4 (quads 221 and 511 at 4.0) | 509-511: the row of eight boards that closes the stub at forward points 361-368; ten quads |
  | Acropolis | 0 / 6 (15-23 units, one bend) | 0 / 5 | none; none |

  **So a put-back that faces a wall a few units ahead is the arcade's own behaviour too, in the normal direction, at other
  places** (Big Forest's quads 421-427 and 1040/1042 at 6 units, Bay Bridge's 221 and 511 at 4). The normal direction is not
  touched. A dynamic sweep (forced departures along the whole lap in MAME) was not made: the static probe found Pascal's spot
  as the worst of its course, and the mechanism is one rule.
- **The fix, in the reverse variants' own data only**: the variant's segment array (its own copy, in its bank) marks the
  quads with under 25 units clear or an object on the path with flag bit 2 (`FLAG_NO_PUTBACK`; 0xfebcbc's mask 0x3c is the only
  reader of bits 2-5 in the boot ROM: the other readers of the flag word test bits 0, 6 and 7). The game then never remembers
  them: the car is set down on the quad before. Marked: Big Forest 60, 61; Bay Bridge 501, 509, 510, 511, 660, 661, 662;
  Acropolis 386, 394, 402, 410, 418, 426 (15 flag bytes in the variants' tables). On Bay Bridge the set-down before the fork
  is now quad 663, (-188.0, -85.6), 28 units before the nose, the fork in view.
  **A side effect to know**: while a car is ON a marked quad the off-course counter runs (it is cleared on the next unmarked
  quad). (Corrected by the third review, §18.1: the longest marked stretch is NOT three road points. Acropolis's six marked
  quads are six consecutive road points of one lane of eight, about 63 units; Bay Bridge's 509-511 about 27 units each.)
- **Evidence**: `test_no_reverse_put_back_on_an_original_faces_a_wall` (the built variants: the marks, 25 units clear on every
  remaining spot, within 22.2 degrees of the lap's direction, no object on a path; the normal entries' segments the stock
  ROM's); `test_a_put_back_before_bay_bridges_fork_in_reverse_has_room` (MAME: the wheel held straight onto the side arm, the
  put-back, the set-down at (-188.0, -85.5), 3.9 degrees off the lap, and the car round the lap afterwards). Pascal's own
  recording replayed on the fixed set: set down before the fork (its inputs after that belong to the old set-down).
- **Not shown**: a hand at the wheel after the new set-down. From 28 units a car that does not steer still meets the nose
  (the centre of the wide road points at it). (Corrected by the third review, §18.1: "the test autopilot met it twice before
  it came away" understated it: a floored car that never steers is now put back again and again, about every 8 s.)

### 17.2 I-A: one frame of the old colours at an original's lock; the hook moved [fixed; V]

- **The fault** (second review; since stage 1): at an original's course lock, frame 1 206 showed the select pictures' back
  maps alone on magenta / cyan for one video frame: `dirdraw`'s first phase clears layer 0 before it redraws layer 2, and
  the handler begins a fraction of a millisecond before a video frame's end.
- **The fix**: an original's handler waits out that frame's end before the clears (4 000 passes of a two-instruction loop),
  so frame 1 206 holds the complete course select and frame 1 207 the cleared screen. This rests on the emulator's timing; the
  standing test reads every frame (`test_no_frame_of_an_originals_lock_shows_a_half_drawn_picture`: frames 1 196-1 299 on the
  three: each picture's place shows none of the picture or the whole of it; whole from 1 209 and 1 211).
- **The hook moved, and why** (second review, minor 5): with the dispatch in front of `dirdraw` a converted course ran three
  more instructions, and its frame 1 206 differed from main's by three cells of the layer clear. Now NOTHING inside the
  directory image is changed. The boot ROM's lock site calls `olock` in `dirlock`'s place: `dirlock` again, with the entry's
  handler chosen (`osel` for an original), in **the same number of instructions as `dirlock` on every path a converted
  course takes** (counted from the two listings by `test_olock_runs_dirlocks_instruction_count_...`: 17, 6, 8, 12).
  `test_a_converted_courses_lock_frames_are_the_set_befores`: Diablo Canyon, all 416 frames from before the lock to the race
  load, pixel for pixel the frames of the set without the variants.
- **The lock look** is written once, on the logic frame the direction locks (the B, A and ring palettes together), not every
  frame from `start`; the lock data is all in the boot ROM (minor 3: nothing is read from bank 0 after the lock). The
  null-record guard of `dirdraw` is in `osel` (minor 4).
- The block: 512 bytes at 0x28f5d0 (432 of code, 24 of addresses). Data: the three lock pieces (1 392 bytes) and two draw
  pieces in the boot ROM's run (0xfdc850..0xfdf520), Acropolis's draw piece in bank 0 (4 848 bytes).

### 17.3 I-B: the pass-for-pass misfire of the first fix wave's invocation (a harness follow-up)

Not a difference between the sets (the reviewer: the failing run's set is `out/p32play2` by CRC; `vrtools/mame` has no diff
against main). Its RAM dump: entry 5, the direction cells `00 02 01 00`, `[0x501a35]` = 1, the bank switch at frame 1 499.
The reviewer's inference: the course select locked on its first logic frames after START (about frame 722, the wheel not yet
applied) through stock boot code (the gas edge 0xfc2748 or the countdown 0xfc2762). Ten reruns loaded at 1 603. No code
change; recorded in `docs/follow-ups.md` as a harness follow-up. (My reading in §16.7, a race start taken 300 frames early,
is superseded by this.)

### 17.4 I-C: on main 1159aab (Phase 34's palms)

- The branch was applied again on 1159aab (one text conflict, `docs/deviations.md`, both sides kept). The tree built with
  `originals_reverse=False` is **`out/p34play4` byte for byte** (so `out/p34play4` is main's set at 1159aab), and the bytes
  against it are named in `out/p33/gates/bytes_s4.txt`, none unnamed.
- **Polygon ROM: 154 680 bytes left** (398 392 before the lettering), against the test's floor of 150 000: **4 680 spare**.
  The best-times work and anything else that writes polygons must know: the lettering takes 243 712, Phase 34's palms took
  28 080 of what was there.
- Bank 1's largest free run is 1 152, as asserted.
- `tests/test_props.py`'s opt-in record against Phase 34's base (`VR_P34_BASE_SET`) fails by design on a tree with this
  phase (it asserts the boot ROM equal); its docstring and skip reason say so.

### 17.5 Tests: the final invocation

Two invocations, each building the set from the rebased tree (`VR_MAME_JOBS=2` / 1, `-s -p no:cacheprovider -rfEs`), with
main's `build/` (the disassembler) and `out/` (the frozen sets and kept dumps the tests look for under the tree) linked into
the worktree while they ran, and removed after: nothing skipped for want of a file.

1. **On ff6b0f7, fifteen modules, 514 tests** (the fourteen of §16.7 and `tests/test_props.py`; `VR_MAIN_SET=out/p34play4` as
   the review asked; log `out/p33/pytest/gate3.log`): **496 passed, 1 skipped, 17 failed** in 4 h 9 min.
   - 12 in `tests/test_dirscreen_build.py`, all on the three originals (`test_an_original_shows_the_screen` x 6, the two "no
     logic frame is lost" tests x 3 each): the tests looked for the handler `dirsel`, and an original's handler is `osel`
     since §17.2. The tests were corrected (`_screen_handlers`); no product code changed after this invocation.
   - `test_hudreverse_build.py::test_a_reverse_race_is_mains_pass_for_pass`: its frozen set is by definition a build of main
     WITHOUT Phase 32 (it asserts that set shows no word); pointed at `out/p34play4`, which has Phase 32, its last assertion
     fails after the passes had compared identical. **The review's instruction is disputed on this one point**: that module's
     set stays `out/p35play1`; with `out/` linked it is found and nothing skips.
   - `test_race_build.py::test_banking_ab_on_the_surfers_courses[SURFERS ROAD]`: `ConvertError: prop site 0 (-173.7, 250.5),
     road point 25: a collision quad lies 0.0 away`. **Main's own, since Phase 34**: the same test run on main's tree at
     1159aab fails the same way (`out/p33/pytest/mainbank.log`). Not this branch's; a follow-up for main.
   - 3 are names of `out/p27/full_failed.txt` (`test_race_build.py`: the Diablo pitch, the hard steer x 2).
   - The one skip is `test_props.py`'s opt-in record, with the reason of §17.4. Pass for pass: twelve runs, 3 314 passes
     each, no difference. Worst frames: 10 172 (Big Forest reverse line 1), 10 052 (its pit lap), 9 771 (line 4), as before.
2. **On the corrected tests, `tests/test_dirscreen_build.py tests/test_hudreverse_build.py`** (the frozen set `out/p35play1`;
   log `out/p33/pytest/gate4.log`): **65 passed, 0 failed, 0 skipped** in 24 min.

### 17.6 The minor points, and what was overstated

1. **"Read by nothing"** overstated the boot ROM's run: the test menu's MEMORY TEST reads all of 0xfdc844..0xfdffff (PC
   0xfe0e81; the reviewer). Its result does not change with this branch: a patched set already shows IC 4-15 BAD
   (`out/p32play2`, the reviewer's `out/p33/review2/sheet_memtest.png`). That a patched set fails the service-mode ROM test
   is not documented on main as a fact (`docs/follow-ups.md` has it twice as "not established"): a follow-ups line is added.
2. **The margin's floor of 300 is a change detector, not a safety margin**: the measurement is deterministic (the same run
   gives 10 172 every time), and the floor fails the test when something eats a tenth of the margin. And **"parked and
   turned" is not a worst case**: every parked view measured is below the moving frame; it only shows that turning the view
   where the car arrives adds nothing.
3. Acropolis's lock lists were in bank 0, read every logic frame to five frames before the bank switch: they are in the boot
   ROM now and read once (§17.2; `test_the_picture_block_and_the_lock_site`).
4. The null-record guard: restored (§17.2).
5. The seven's frames: §17.2.
6. `docs/follow-ups.md`'s "The boot ROM's 0xfdc844 run is unread": corrected.

### 17.7 Not verified in the second fix wave

1. Pascal has not seen any of it.
2. A hand at the wheel after the new put-back before Bay Bridge's fork; the put-backs of Big Forest and Acropolis in reverse
   in MAME (the static probe and the marks only).
3. The wait at an original's lock on real hardware (it is the emulator's frame timing).
4. A dynamic sweep of put-backs; whether any object of a spawn list other than the board row stops a car.
5. Linked play, the whole suite.

## 18. After the third review of 8714d63 (no code defect): the record corrected, main 75dd1cd, the final gate

### 18.1 The put-back's limits, corrected (the reviewer's measurements, credited; not run again here)

- **The marked stretches** (wrong in §17.1 as first written): Bay Bridge's 660-662 before the fork are three road points,
  24 units; but **Acropolis's 386, 394, 402, 410, 418, 426 are six consecutive road points (reverse 236-241) of one lane of
  eight, about 63 units**, and Bay Bridge's 509-511 are about 27 units each.
- **A floored car that does not steer is now reset in a loop.** On `out/p33play4` it was set down on quad 663 **eight times**
  (frames 2 392 to 5 790, about every 8 s) until the clock ran out: it drives the 28 units into the nose, the counter runs on
  the marked quads, and it is put back. On `out/p33play3` it was set down once on 660 and stayed against the nose to
  time-over. §17.1's "met it twice before it came away" was my run with the autopilot taking the wheel back; it understated
  what a car that never steers gets. Either set needs the driver to steer into an arm; the new one gives 28 units and a
  second chance every 8 s, the old one four units and none. The lead has told Pascal.
- **The counter at speed and at a crawl** (the reviewer's figures): driving through, the counter peaks at 14 and 27 on Bay
  Bridge's 662-660, 25 and 9 on 511-509, 5 and 3 on 501, 7 on Big Forest's 61, against the 129 a put-back needs. A put-back
  from marked quads needs 129 consecutive logic frames on them: a car standing, or moving under about 0.09 units a frame
  (0.24 in Acropolis's lane); it then lands on the neighbouring unmarked quad.

### 18.2 The minor points

- **M1**: `putback_clear` probed only quads with flag bit 0; the game's rule is the mask 0x3c alone (0xfebcbf), so it also
  remembers Bay Bridge's 65 quads flagged 0x02 and the pit lanes' 0x42. The probe now follows the game's rule (Big Forest
  1 093 spots, Bay Bridge 483, Acropolis 946); the marks are the same fifteen (the reviewer's scratch probe had found none
  under 25 units among the added quads either way).
- **M2**: the I-A test covered one lock. Its margins, measured by the reviewer: `dirdraw`'s clear starts 2.66 ms after the
  frame's capture and the checker's redraw ends 4.7 ms before the next; the wait is 4 000 passes of `sub` / `bne` on R10,
  4.0 ms in MAME. Added: the same frames with the screen answered REVERSE (Bay Bridge). The course lock is at frame 1 202
  whatever the answer; the second lock, at 1 402, clears nothing (the lock look is palette words, read by the pixel test).
- **M3**: `osel` with a null picture record skips the `picture` call and still runs the phase's rows, as `dirdraw` does; the
  comment said "nothing". Corrected.

### 18.3 On main 75dd1cd (Phase 37's tunnel sound)

- Re-applied on 75dd1cd (three textual conflicts, both sides kept: `docs/deviations.md`, `docs/follow-ups.md`, two import
  lines of `tencourse.py`).
- **Bay Bridge's own tunnel in a reverse race** (a case neither phase had tested): the variant keeps the game's 0x81 on quads
  69-88, and the fifteen marks are 0x05 (`test_a_marked_quad_keeps_its_other_flag_bits`: the mark is OR-ed in).
  `test_bay_bridges_own_tunnel_sounds_in_a_reverse_race`: C201 as the car comes onto quad 88, C200 as it comes onto 68, once
  a pass, no other C2xx.
- The tree built with `originals_reverse=False` is **`out/p37play1` byte for byte** (so that set is main's at the tunnel merge);
  the bytes against it are named in `out/p33/gates/bytes_s5.txt`, none unnamed. The set, `out/p33play5`, differs from
  `out/p33play4` in 196 bytes in six runs of the data ROM (main's tunnel flags on Alpine and Metropolis) and nowhere else.
  Polygon ROM left: 154 680, as before.

### 18.4 Tests: the final invocation

One invocation on the rebased tree (on main 75dd1cd), the set built from the tree, `VR_MAME_JOBS=2`, main's `build/` and
`out/` linked into the worktree while it ran (removed after), `-s -p no:cacheprovider -rfEs`: the fifteen modules of §17.5
and `tests/test_tunnel_sound_build.py tests/test_tunnel_flags.py` (`test_banking_ab_on_the_surfers_courses` is in
`test_race_build.py`); log `out/p33/pytest/gate5.log`: **547 passed, 1 skipped, 4 failed** of 552 in 3 h 43 min.

- 3 failures are names of `out/p27/full_failed.txt` (`test_race_build.py`: the Diablo pitch, the hard steer x 2).
  `test_banking_ab_on_the_surfers_courses` passes (main's fix).
- 1 is this wave's own widened test, `test_no_reverse_put_back_on_an_original_faces_a_wall`: with the probe on the game's
  rule (M1) it also measured the ANGLE of Bay Bridge's side-road quads (flag 0x02) against the lap, 108 degrees: they lie
  along the side road, not the lap they are credited to, in the normal direction as well. The clear-ahead and object
  assertions held for all 476 spots. The angle is now asserted on the lap's own road only; rerun on the same build with
  `test_a_marked_quad_keeps_its_other_flag_bits`: 2 passed (`out/p33/pytest/gate6`). No product code changed after the
  invocation.
- The one skip: `test_props.py`'s opt-in record (§17.4), by design. Nothing else skipped: `test_hudreverse_build.py` ran on
  its frozen set `out/p35play1` (`VR_MAIN_SET` is read by that module only, and was left unset; this branch's own
  comparisons are against the tree built with `originals_reverse=False`, which is `out/p37play1` byte for byte).
- Pass for pass: twelve runs, 3 314 passes each, no difference. Big Forest reverse line 1: 10 172, the margin 328.
  Bay Bridge's tunnel in reverse: C201 at quad 88 (frames 4 580, 8 142), C200 at quad 68 (4 684, 8 246).
- The session's built set is `out/p33play5` byte for byte.

### 18.5 Not verified

Pascal has not driven `out/p33play4` or `out/p33play5`. A hand at the wheel at Bay Bridge's fork after a put-back; the
reviewer's loop and counter figures were not measured again here; real hardware; linked play; the whole suite.
