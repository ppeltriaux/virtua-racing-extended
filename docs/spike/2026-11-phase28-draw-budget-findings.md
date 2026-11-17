# Phase 28: the frame's draw budget (15 Nov 2026) — findings

Pascal chose "3 first": the recon's third candidate step (`2026-11-phase28-polygons-recon.md` §8), raising the frame's record
budget (0x5011b0, 5 500) "to about 8 000", told that it also changes the three original courses (less far pop-in than the real
arcade). The brief: establish the value by measurement, the smallest round value that leaves no frame skipping, with a stated
margin; stop and report if that is more than about 10 000, or if anything sizes a buffer or a loop by the budget.

**The value is 10 500.** The measurement (§3) found the originals' busiest frames asking for up to 9 771 records, so the smallest
round value with a margin of 5 % or more was 10 500, past the brief's bound: this phase stopped and reported, with the options of
§3.4, the rate and host-speed measures and the note that the originals would then draw far scenery the real arcade dropped on busy
frames. The session lead recommended 10 500; **Pascal answered "Ok"**. Then, on 15 Nov, **Pascal said "It's critical the game stay
fluid at 60fps constant"**; the lead told them that the arcade itself draws one picture every second screen frame (about 29 a
second; the project's smoke test has always called 27-29 switches per 57 frames "the arcade rate") and that what is guaranteed is
never falling below the original's own rate, and **Pascal answered "Yes"** to continuing on that basis. They then ran the scratch
set with the 10 500 budget (`out/p28/budget/c10500`, byte for byte `out/p28play1`) twice on 15 Nov, 53 s and 57 s, MAME's average
speed 100.00 % both times with other jobs running, and said **"this is good continue"**. Asked whether the change also improves
the original three tracks, they were told yes (the originals' far-scenery skips go) and that it is a departure from the real
arcade. After the review they ran the same set a third time, 296 s of emulation, MAME's average speed 99.98 %, with this phase's
tests running in the background, and said **"looks good so far"**. What they drove in those runs was not stated (what two kept
recordings show, played back headless, is a fact about the recordings: §13.4). Nothing here says they validated or approved
anything in the game beyond those words. The ten-course build now writes 10 500 at `0xfe11bd` and 10 000 at `0xfe11d3` (the linked
cabinet's 5 000 raised by the same 5 000; linked play not run).

Marks: **[V]** verified by a run or a byte read in this phase; **[R]** read in code or a listing; **[?]** not established. Every
number from runs is from one run each unless stated; all runs are MAME 0.289 headless on main's tested set `out/p27play1` (or a
scratch copy of it with the patch), scripts under `out/p28/budget/` (git-ignored, §11).

## 1. The arcade's rate [R]

The arcade game has never drawn 60 pictures a second. The Model 1 screen is 57.52 Hz (`model1.cpp:1834`), and the game draws one
picture and runs one logic step every **second** screen frame (the main loop's two-vblank wait at `0xfe13db`): about **28.76
pictures a second**. Pascal's requirement is "It's critical the game stay fluid at 60fps constant" (15 Nov); the basis they said
"Yes" to is never falling below the original's own rate, held on every frame. It is measured three ways (the recon's §2.1, now
`vrtools/mame/framerate.py`):

- the game's own overrun counter 0x501148 (incremented at `0xfe13fe` when a frame's work took more than two vblanks): never moving.
  It is the exact detector: a pass whose work ends after the second vblank exits the wait at the fourth, one picture lost, the
  counter +1 (the review's trace of `0xfe13db..0xfe13fe`). Its second writer, the debug routine at `0xfe03cf` (bit 5 of
  0x501120), could only make a test fail with nothing wrong;
- the V60's busy time per logic frame: under 34.77 ms (two vblanks);
- the render rate: display-list switches per 57 screen frames, 28-29 (`renderrate.lua`). It shows that pictures keep coming, not
  each one: the windows do not overlap and alternate 28 and 29 (57 is odd), so a single lost picture in a 29-window reads 28 and
  passes, in about half its positions; the counter catches it.

## 2. Method

- **The budget out of the way:** the recon's logger with its `VR_P28_BUDGET=30000` switch (the word overwritten every frame), in an
  extended copy `out/p28/budget/p28b_frame.lua`. It adds, per logic frame:
  - **need**: the least budget under which that frame skips nothing. It is the highest record count the walker compares at
    `0xff848a` / `0xff84a2` (a list is skipped when the count is **above** the budget), and the count + 150 at the character path's
    check (`0xff5e33`, which never ran in these runs). It is lower than the frame's final record count (the **peak**) by the last
    list's records, which the walker lets through whatever their size.
  - the display list's bytes in use at the frame's end (0x5017F4 − 0x5017F8).
- **Runs** (`out/p28/budget/run.py`, 300 emulated seconds each, the race clock held as in the recon):
  - the 17 races (the three originals; the seven converted courses in both directions), each with the start and its full field;
  - four more on Big Forest (other autopilot lines) and two more on Acropolis;
  - a pit stop on Big Forest (laps through its pit lane, `bf_pit_path.csv`: two stops of 797 frames) and on Metropolis (main's
    pit-test path: two stops of 701 and 643 frames);
  - the attract cycle with no input, 300 s and 700 s (its demo races and the scenes between them).
- **Coverage**: one autopilot, in or behind the field. The converted courses' uncovered road points are the recon's (§1 there): their
  scenery is a third of the originals' and their frames are far below any candidate (§3.2).

## 3. The value

### 3.1 The originals [V]

| run | course, autopilot line | need max | peak max | race frames over 7 500 / 8 000 / 9 000 / 10 000 |
|---|---|---|---|---|
| L0 | Big Forest, line 0 | 9 168 | 10 141 | 0.40 % / 0.26 % / 0.18 % / 0 |
| L0m | Big Forest, AI mean | 9 642 | 10 615 | 0.50 % / 0.13 % / 0.12 % / 0 |
| L0l4 | Big Forest, line 4 | **9 771** | 10 744 | 2.10 % / 0.66 % / 0.35 % / 0 |
| L0l7 | Big Forest, line 7 | 9 691 | 10 664 | 2.52 % / 0.89 % / 0.29 % / 0 |
| P0 | Big Forest, pit lap | 9 595 | 10 568 | 0.64 % / 0.20 % / 0.13 % / 0 |
| L1 | Bay Bridge, line 0 | 6 922 | 7 392 | 0 |
| L2 | Acropolis, line 0 | 8 339 | 8 721 | 0.22 % / 0.06 % / 0 / 0 |
| L2m | Acropolis, AI mean | 9 206 | 9 588 | 0.33 % / 0.20 % / 0.06 % / 0 |
| L2l6 | Acropolis, line 6 | 8 229 | 8 611 | 0.38 % / 0.15 % / 0 / 0 |

With the game's 5 500 the same runs would skip on 22-37 % of Big Forest's race frames, 3 % of Bay Bridge's and 18-20 % of
Acropolis's (the recon measured 22 %, 3 % and 17 %). The heaviest frames are Big Forest's road points 258-283, every lap, with 53-85
objects in the frame; Acropolis's road points 291-303.

### 3.2 The converted courses, the pit stops and the attract [V]

| run | start window need (load to green + 400) | race need | peak max |
|---|---|---|---|
| Alpine / reverse | 2 800 / 3 976 | 4 078 / 4 449 | 4 387 / 4 449 |
| Amazon Falls / reverse | 3 619 / 4 404 | 4 600 / 5 437 | 4 960 / 5 769 |
| Diablo Canyon / reverse | **5 711** / 4 789 | 4 907 / **5 522** | 5 895 / 5 875 |
| Metropolis / reverse | **5 803** / 4 921 | **6 322** / 3 363 | 6 568 / 4 921 |
| Pacific Coast / reverse | 3 814 / 3 682 | **5 745** / 3 781 | 6 009 / 4 387 |
| Surfers Oval / reverse | 3 566 / 3 838 | 4 061 / 4 240 | 4 182 / 4 240 |
| Surfers Road / reverse | 3 693 / 3 995 | 4 174 / 5 122 | 4 414 / 5 666 |
| Big Forest pit stops (two) | | 7 248 / 7 132 during the stops | |
| Metropolis pit stops (two) | | 6 948 / 6 946 | 6 948 |
| attract, 700 s (demo races, the scenes between) | | 8 354 (a demo race), the scenes 5 350-6 225 | 8 804 |

The start-line skips the recon found (Diablo Canyon, Metropolis, Pacific Coast, Diablo reverse) are the bold figures: every one
of them is cleared by **6 500**; Metropolis's pit stop by **7 000**.

### 3.3 The rule applied

- The highest need measured is **9 771** (Big Forest, line 4). It rose with almost every run added (9 168, 9 595, 9 642, 9 691,
  9 771): it depends on where the field's cars are at road points 260-275, so it is not bounded by these runs.
- 10 000 leaves no measured frame skipping, with a margin of 229 records (2.3 %) over a figure that is still moving.
- A margin of 5 % or more needs 10 260 or more: the smallest round value is **10 500** (margin 729, 7.5 %) or 11 000 (12.6 %).
- That is more than about 10 000: the brief's stop. The phase reported the options below; Pascal answered "Ok" to the lead's
  recommendation of 10 500.

### 3.4 The options as reported (10 500 chosen)

| budget | what it clears (measured) | what still skips | margin |
|---|---|---|---|
| 6 500 | every converted course's skips, start and race, both directions | Metropolis's pit stop (0.4 % of that run); the originals on 7-13 % of race frames (Big Forest), 0.2 % (Bay Bridge), 6-7 % (Acropolis) | 178 over the converted courses' 6 322 |
| 7 500 | the converted courses, both pit stops, the attract's scenes | the originals on 0.4-2.5 % (Big Forest), 0.2-0.4 % (Acropolis); the attract's demo races 0.2 % | 252 over Big Forest's pit stops |
| 8 000 (the first figure) | the same | Big Forest 0.1-0.9 %, Acropolis 0.06-0.2 %, the attract 0.1 % | |
| 10 000 | every measured frame | none measured | 229 (2.3 %) |
| 10 500 | every measured frame | none measured | 729 (7.5 %) |

None changes the arcade's rate (§5): with the budget at 30 000 every list was drawn and every run held it.

## 4. What reads the budget, and whether a larger one can overrun anything

- **Readers** [R, V byte search]: the original boot listing has five instructions that read 0x5011b0 and two that write it; a
  search of the boot and program ROMs for the address's four bytes finds exactly those seven (the program ROM none):
  - `0xff848a` / `0xff84a2`: the walker's compare (`cmp.w 5011B0, 5011A0[PC]; bgt` → return);
  - `0xff5e33`: an object with flag bit 0x1a is drawn only while the count is at most the budget less 150;
  - `0xff8571` / `0xff862c`: every 0x01 (and 0x10 0x11) display-list command carries the budget as its fourth word;
  - writers `0xfe11bd` (5 500) and `0xfe11d3` (5 000).
  - at run time [V]: a read and write tap over 0x5011b0..0x5011b3 in a 120 s boot of `out/p28play1` into the attract (no Lua writes
    to the word) saw the readers `0xff84a2`, `0xff8571`, `0xff862c` (and the logger's own read) and the writers `0xfe11bd` and
    `0xfe1469`, the boot's clear of 0x500000..0x53efff that runs before it. (With the recon's switch writing the word every frame
    the tap's PCs are the Lua callback's and mean nothing.)
- **The size word** [R, MAME `model1_v.cpp:856`]: `push_object` draws an object's records until its own end record (type 0) or
  `size` records, whichever is first, and ignores an object whose size is 0x1000000 or more. No object reaches 5 500 records (the
  largest original cell 1 566, converted 789; the converter caps a cell at 5 500, `polyrom.MAX_RECORDS`), so a larger size draws the
  same records. The size reaches the video side only: the TGP (the copro) does not see the display list in MAME. **What the real
  hardware's display-list processor does with it is not established [?].**
- **No buffer or loop is sized by it** [R]: the display list grows by a fixed number of entries an object (8 + a 26-entry matrix, the recon's §2.2),
  whatever the records; the record count only gates which lists are emitted. With every list drawn the display list peaked at
  **11 800 bytes of its 65 536 (18 %)** (the attract's ranking scenes, 161-165 objects); Big Forest's heaviest race frame used
  10 400 (142 objects) [V]. MAME's quad buffers hold 1 000 000 quads.
- **The second site** [R]: `0xfe10e5` tests the link setting 0x40dc8c. At 0 (a standalone cabinet) the boot sets the flag 0x501a35
  to 1 and branches to `0xfe11bd`, so the budget is 5 500 and `0xfe11d3` is never reached. Otherwise (a linked cabinet) `0xfe6c5f`
  initialises the comm board and writes the link mode to its byte 0xb00001; the flag is 1 if that byte still reads non-zero, and
  only with the flag 0 does `0xfe11d3` set 5 000. The flag is read at some 30 other places (the slave cabinet's HUD at `0xff471b`
  among them). **So the second site is linked play only.** `patch_budget` raises it by the same amount (500 below the first).
  Linked play was not run.

## 5. The arcade's rate with every list drawn [V]

All 17 races, both pit runs and the attract runs above, at budget 30 000 on main's set, from the pass after the course load to
the race's end:

- render rate 28-29 in every window from the green (the attract: in every window);
- 0x501148 = 0 throughout every run;
- V60 busy at most **14 604 us** (Big Forest; 42 % of 34 770), the attract's scenes at most 17 982 us.

Against main's budget (the recon's runs at 5 500, the same courses and autopilot lines), with the budget out of the way:

| course | busy median / max at 5 500 (us) | at 30 000 | change, median / max |
|---|---|---|---|
| Big Forest | 10 624 / 14 469 | 10 646 / 14 604 | +22 / +135 |
| Bay Bridge | 12 105 / 13 449 | 12 105 / 13 491 | 0 / +42 |
| Acropolis | 10 587 / 13 387 | 10 610 / 13 588 | +23 / +201 |
| the converted courses (nine runs) | 9 398-9 689 / 11 201-12 849 | 9 401-9 670 / 11 142-12 849 | −82..+57 / −1 423..0 |

The converted courses' differences are the runs' own (different lengths and field positions): they skipped almost nothing at 5 500.
Any budget between 5 500 and 30 000 draws a subset of what 30 000 drew, so its frame work is bounded by these figures.

**The standing test** (`tests/test_frame_rate.py`, one session on the session's ten-course set, the product as it stands, the
game's 5 500) [V]: all 17 races passed, 150 s each from the boot (3 511 logic frames from the pass after the course load, green at
frame 1 866 or 1 928). Asserted: render rate 28-29 in every window wholly after the green; 0x501148 unchanged; busy under 34 770 us
in every logic frame of the stretch. Measured: rate 28-29 everywhere, 0x501148 0 → 0 everywhere, worst busy 10 934-14 469 us (Big
Forest 14 469, Bay Bridge 13 449, Acropolis 13 387; the converted courses 10 934-12 849). The test fails on any one window outside
28-29, any frame of two vblanks or more, or the counter moving; its checks on synthetic logs show each kind caught, and on a real
log the course load's own pass (48.5 ms, which the test leaves out by design) is reported as a miss when counted.

### 5.1 The skips gone: red, then green [V]

`tests/test_frame_rate.py::test_no_list_is_skipped_where_the_games_budget_cut` (seven cases: the three originals on the standing
test's 150 s runs; Diablo Canyon both ways and Pacific Coast on road line 0, Metropolis on the AI lines' mean, the recon's lines,
150 s) asserts that frames whose need is above 5 500 are in the run and that no list is skipped from the boot to the run's end, with
the budget word 10 500 in every frame.

- **Red** (the same session's build with `patch_budget` left out of `install_directory`, `out/p28/budget/pytest_red.log`): 7 failed,
  each on its skipped frames: Big Forest 853, Bay Bridge 163, Acropolis 898, Diablo Canyon 3 (frames 2 249-2 253, its start), Diablo
  reverse 1 (frame 3 961, need 5 522), Metropolis 65 (from frame 2 223, its start), Pacific Coast 4 (from frame 2 483, road point 46).
- **Green** (the final session, `out/p28/budget/pytest_final.log`, the patch in the build): 7 passed; no frame of the seven runs
  skipped a list, and the frames above 5 500 are there: Big Forest 851 (need up to 9 137), Bay Bridge 163 (6 922), Acropolis 879
  (8 339), Diablo Canyon 3 (5 711), Diablo reverse 1 (5 522), Metropolis 65 (6 322), Pacific Coast 4 (5 745).
- **Red against green, frame by frame** (corrected in the fix wave, §13.2): on Bay Bridge and the four converted runs the frames
  above 5 500 are the same frames in both sessions. On Big Forest and Acropolis they are not: 853 red against 851 green (25 frames
  only in red, 23 only in green) and 898 against 879 (244 and 225), because the two sessions' autopilot races part at Big Forest's
  frame 4 730 and Acropolis's frame 3 354; before those frames the sets are identical (329 and 368 frames). The parting is the
  harness's, not the game's: fed the same wheel and pedal frame for frame, the 10 500 set's game state is identical to main's over
  the whole run on both courses (§13.2).

### 5.2 The standing test on the built 10 500 set, against the old set [V]

All 17 races passed in the final session: render rate 28-29 in every window from the green, 0x501148 0 → 0, no frame of two
vblanks. Worst V60 busy per course (us), the old set (the blocked round's session, the game's 5 500) against the new:

| course | old | new | change | | course | old | new |
|---|---|---|---|---|---|---|---|
| Big Forest | 14 469 | 14 604 | +135 | | Alpine / reverse | 11 142 / 11 271 | 11 142 / 11 271 |
| Bay Bridge | 13 449 | 13 491 | +42 | | Amazon Falls / reverse | 10 934 / 11 337 | 10 934 / 11 337 |
| Acropolis | 13 387 | 13 588 | +201 | | Diablo Canyon / reverse | 12 417 / 12 849 | 12 417 / 12 849 |
| | | | | | Metropolis / reverse | 12 699 / 12 540 | 12 699 / 12 540 |
| | | | | | Pacific Coast / reverse | 11 986 / 11 509 | 11 986 / 11 509 |
| | | | | | Surfers Oval / reverse | 11 663 / 11 248 | 11 663 / 11 248 |
| | | | | | Surfers Road / reverse | 12 118 / 11 601 | 12 118 / 11 601 |

The converted courses' worst frames are the same frames with the same work (their worst is not a frame where 5 500 skipped). The
largest frame drawn: 10 110 records (Big Forest). Two vblanks are 34 770 us: the worst is 42 % of it.

## 6. Nothing but drawing changes

First (the blocked round), a normal race of 120 s on Big Forest and on Metropolis, on a scratch candidate at 10 000 against main's
tested set, both started on
the same battery RAM (the candidate's after a 30 s boot to the attract, copied into both runs), with the race, field, collision and
pit logs and one more log, `passlog.lua`: the game's state at the **end of every logic pass** (at the wait's first read): the race
clock and, for all 16 cars, x and z (their bits), road point, speed and lap [V]:

| log | Big Forest | Metropolis |
|---|---|---|
| per logic pass (3 314 passes) | **identical** | **identical** |
| race (one line a frame end) | 6 lines of 6 904 differ, first at frame 3 545: the off-course counter 39 against 40 | identical |
| field (16 cars, every frame end) | 10 lines of 84 848, first at frame 1 984: car 2's x −197.0 against −196.9 | 1 line, frame 2 318: car 2's cursor 544 against 560 |
| collision (one per logic frame) | 1 line of 2 563: the call logged for frame 4 754 against 4 752 | identical |
| pit | 1 line, frame 4 997: the player's quad 917 against 925 | identical |

**Finding: the frame-end logs are not identical, and the game state at every pass's end is, in these two races** (the same battery
RAM, the autopilot's own steering, which did not part here; with it, the standing races on Big Forest and Acropolis do part, and
the comparison on the same inputs is §13.2). Every value that differs is one the other set shows at a
neighbouring frame (within ±4 frames, all 18 lines checked); positions, yaws and laps of the player never differ; the last lines are
identical. Skipped lists carried nothing the game logic reads in these two races. The final session repeats the comparison on the built 10 500
set against main's equivalent (§6.2, after the mechanism, §6.1).

### 6.1 The mechanism of the first differing line (Big Forest's field log, frame 1 984, car 2) [V]

Traced with `out/p28/budget/trace.lua` (emulated time of MAME's frame end, of the pass's start and end, of every write to car 2's x
0x40121e, of the display-list pointer and of every V60 access to the TGP FIFO 0xd80000..0xd80013), the same race on the scratch
10 500 set (A) and main's set (B), the same battery RAM; the field log's frame 1 984 is MAME frame 1 985:

1. **The sample is taken inside a pass.** The pass that writes car 2's x for that frame leaves the wait at 34 507 376.9 us (A) and
   34 507 376.6 us (B); MAME's frame end, where the field log samples, comes **1 503 us later** (34 508 880.0 us in both). Car 2's x
   is written (PC 0xfece98) 1 501.3 us into the pass in B, **2.1 us before** the frame end, and 1 516.0 us into it in A, **12.9 us
   after**. So B's log shows the new x (−196.9) and A's the old one (−197.0); at the next frame end both show the same.
2. **The pass is the same work, done later.** From the pass's start to car 2's write both sets make the same 745 V60 accesses to the
   TGP FIFO, in the same order with the same data (and the same display-list and record-count writes). No list is drawn there
   (the pass's logic comes before its drawing). A lags B by 0.013 us up to the 22nd access, 0.5 us at it, and the lag grows in steps of 0.5 us, each
   at a push of a new TGP command (`off=d80010`), to **14.7 us** by car 2's write.
3. **Where the first offset comes from.** The pass begins when the V60, polling the vblank counter in the wait loop (0xfe13db..
   0xfe13f3), sees it change. The previous pass took 161 us longer in A (34 485 358.7 against 34 485 197.9 us at its end: the lists
   the 10 500 budget drew), and A left the wait 0.3 us later after the same vblank [V]; the reading [R] is that it entered the polling loop
   at another point of the loop's period. Each V60-TGP handshake then waits for the TGP (an emulated MB86233, which consumes the FIFO at its own pace), and a
   start shifted by a fraction of a microsecond lands some of those waits on the next step of the TGP's progress: 0.5-us steps
   that add up [V steps; R the reading].
4. **What it is not.** No game value differs at any pass's end (the pass log, 3 314 passes); the TGP's commands and results are
   bit-identical; the same holds for Metropolis. The difference is in *when* within the pass the logic runs, and a log that samples
   at MAME's frame end can see it. Whether real hardware has the same sub-microsecond dependence was not examined [?]; on any
   hardware a frame-end sample of a pass in progress is a harness artefact.

### 6.2 On the built 10 500 set [V]

`test_the_game_is_the_same_pass_for_pass` in the final session: the session's 10 500 set against the same set with the two
immediates put back (main's set from the same conversions; `out/p28play1` is main's tested set but for those four bytes, §8), the
same battery RAM (the set's after a 30 s boot), 120 s: the pass logs identical on Big Forest and Metropolis (3 314 passes each);
the frame-end logs differ on Big Forest in 6 race, 10 field, 1 collision and 1 pit lines (the same lines as the 10 000 candidate's,
first again at the field log's frame 1 984), on Metropolis in 2 field lines; every differing field value is in the other set
within 4 frames (asserted).

The test `tests/test_frame_rate.py::test_the_game_is_the_same_pass_for_pass` asserted, in the final session, what was established
then: the per-pass state of all 16 cars and the clock identical to main's set over the whole run on Big Forest and Metropolis, and
every differing field-log value present in the other set for the same car within 4 frames. The new
`vrtools/mame/lua/pass_state.lua` (`VR_PASS_LOG`) writes the per-pass log. Since the fix wave it feeds the set main's run's own
inputs and covers Acropolis too (§13.2).

## 7. The host's speed (one machine's figure)

**One machine's figure:** this Mac, with other jobs running beside it (load average 7-70 during the runs). Big Forest on autopilot
line 4, its heaviest stretch (road points 258-283 every lap), 150 emulated seconds, the clock held, on the scratch candidate at
10 000 (every list drawn: need up to 9 704, no skip; the 10 500 set draws exactly the same in that run, since no frame needed more)
and on main's set (792 frames skipping) [V]:

| | candidate 10 000 | main (5 500) |
|---|---|---|
| throttled (run_mame's command less `-nothrottle`): MAME's "Average speed" | 100.00 % (149 s) | 100.00 % (149 s) |
| throttled, per 57-frame window after frame 2 000: mean / lowest | 99.996 % / 98.6 % | 99.994 % / 99.9 % |
| unthrottled: MAME's "Average speed" | 390.90 % | 392.85 % |
| unthrottled, per window after frame 2 000: mean / lowest | 375.6 % / 270.7 % | 379.1 % / 351.2 % |

The emulator keeps real time with the most polygons the game asks for, with about 3.7 times the speed it needs on average; the
lowest window (270.7 %) is one window and may be the other jobs' load. Not measured: a slower machine, Windows, MAME with a window (these runs use
`-video none`; whether MAME still rasterises every frame in that mode was not checked [?], so the host's cost of drawing to a
window may not be in these figures).

## 8. The ROMs

The playtest set `out/p28play1` (`vrtools build`, this branch) against main's tested set `out/p27play1` [V]: of the 38 members of
`vr.zip` one differs, the boot ROM's `epr-14879a.5` (0xfe0000..0xffffff), at four bytes: 0x11c0-0x11c1 (the immediate at 0xfe11bd,
0x157C → 0x2904, 5 500 → 10 500) and 0x11d6-0x11d7 (0xfe11d3, 0x1388 → 0x2710, 5 000 → 10 000); the immediates' upper bytes stay 0.
`model1io.zip` and `m1comm.zip` are identical; the build report is identical but for its last line (the path). Nothing moves: the
patch is in place. The scratch set `out/p28/budget/c10500` (main's set with `patch_budget`) is byte for byte `out/p28play1`.
A 120 s headless boot of `out/p28play1` into the attract: the budget word 10 500 in every frame, no list skipped, render rate 28-29,
0x501148 still, MAME's average speed 412 % [V].

## 9. Not verified

- The value: the originals' worst frame is not bounded by these runs (§3.3); 10 500 is 729 above the highest measured.
- A slower host or Windows; MAME drawing to a window (§7).
- Linked play (the second site), and the real hardware's handling of the 0x01 command's size word (§4).
- **Real hardware** (the review's M1): MAME does not model the render board's time (it rasterises the whole list at once on the
  host), and the game does not wait for the renderer in its main loop (0x500514 = 0xFF, set at `0xfe11f6`, bypasses the vblank
  handler's gate at `0xfe0313`); Sega's 5 500 may match the renderer's capacity per picture, so on a real board this change is
  untested and might cost pictures or leave them incomplete. The set is for MAME.
- What Pascal drove: they ran the 10 500 set three times (53 s, 57 s, 296 s; the intro) and did not say what they drove; how far
  scenery looks on the originals with no skip was not shown by a test (the recon's still pair at 20 000 is the only image).
- Pit scenes are measured in the attract as MAME showed them over 700 s; which scene is which was not named.
- The converted courses' road points the autopilot did not reach (the recon's model covers their scenery: §3.3 there).

## 10. What is in the tree

- `vrtools/arcade/budget.py`: the two sites, their expected bytes, FRAME_BUDGET 10 500 and LINK_FRAME_BUDGET 10 000, and
  `patch_budget` (`PatchError` on other bytes, both sites checked before either is written, or a value outside 5 500..0xFFFFFF),
  called by `install_directory`; the two immediates in `tests/test_directory.py`'s SPANS. `tests/test_draw_budget.py`: the sites, the
  patch's four bytes, refusals, the build's 10 500 / 10 000.
- `vrtools/mame/framerate.py`, `vrtools/mame/lua/frame_rate.lua` (autoplay.lua loads it with `VR_FRAME_LOG` or `VR_HOLD_CLOCK`; its
  F line carries the frame's need) and `vrtools/mame/lua/pass_state.lua` (`VR_PASS_LOG`: the game's state at every pass's end).
- `tests/test_frame_rate.py`: the standing rate test on all 17 races, the no-skip test where the game's budget cut, the per-pass
  comparison with main's set, and the checker's tests on synthetic logs; since the fix wave (§13) also the worst frames known and
  the attract, and the comparison on replayed inputs (`vrtools/mame/lua/input_tape.lua`, `VR_INPUT_LOG` / `VR_INPUT_REPLAY`).

## 11. Files (git-ignored, `out/p28/budget/`)

- `p28b_frame.lua` (the recon's logger plus need, the display list, `VR_SPEED_LOG`), `run.py`, `batch.sh`, `peaks.py`, `ident.py`,
  `speed.lua`, `mame_throttled.sh` (MAME without `-nothrottle`), `bf_pit_path.csv`;
- runs `runs/<tag>/`: `L0`-`L9`, `R3`-`R9` (the 17), `L0m`, `L0l4`, `L0l7`, `L2m`, `L2l6`, `P0`, `P6`, `A1`, `A2`, the speed runs `S_new_thr`, `S_main_thr`,
  `S_new_unthr`, `S_main_unthr`; `ident/c10000/` with `passlog.lua` (the identity runs);
- `cand10000/`, `c10500/` (scratch sets: main's with the patch at 10 000 and 10 500), `trace.lua`, `tracerun.py`, `trace/` (§6.1);
  `pytest/` and `pytest.log` (the blocked round's session, the product then unchanged), `pytest_red/` and `pytest_red.log` (the
  no-skip tests without the patch), `pytest_final/` and `pytest_final.log` (the final session), `red_static.txt`, `red_static2.txt`,
  `build_p28play1.log`, `runs/BOOT28` (the playtest set's boot).
- the fix wave (§13): `review.md` (the review), `replay/` (the replay experiment), `fix/play/` (the recordings' playback), `fix/att/`
  (the attract's vblank probe), `fix/main27b/` (main's tree built after Phase 27b), `fix/build_*.log`, `pytest_dev/` and
  `pytest_dev.log` (a development run of the new MAME tests), `pytest_fix/` and `pytest_fix.log` (the final invocation).

## 12. The report (the harness refused the report file under `out/`: its content is here)

- **The value:** 10 500 at 0xfe11bd, 10 000 at 0xfe11d3; chosen by the rule of §3.3 (the highest need measured 9 771, the smallest
  round value with a margin of 5 % or more), past the brief's 10 000 bound, so the phase stopped; Pascal's "Ok" to the lead's
  recommendation of 10 500. Peaks per course and direction: §3.1-3.2.
- **The sites and their bytes:** 0xfe11bd `2d 80 f4 7c 15 00 00 f3 b0 11 50 00` (`mov.w #157C, 5011B0`) → `2d 80 f4 04 29 00 00 f3
  b0 11 50 00`; 0xfe11d3 `2d 80 f4 88 13 00 00 f3 b0 11 50 00` (`mov.w #1388, 5011B0`) → `2d 80 f4 10 27 00 00 f3 b0 11 50 00`.
- **Red and green, with commands** (`source out/env.sh`; Python `.venv/bin/python` with `PYTHONPATH` the worktree; `-m pytest -o
  addopts=""`):
  - static, before `budget.py` existed: `tests/test_draw_budget.py` 2 import errors and 2 "DID NOT RAISE" (`red_static.txt`); the
    build's value before it was wired: 1 failed, 5 passed (`red_static2.txt`); then green;
  - the no-skip tests: red on the build without the patch, 7 failed (§5.1, `pytest_red.log`, `--basetemp out/p28/budget/pytest_red`
    `-k cut`); green in the final session;
  - the checker: written before its tests (no red run); it catches each kind of miss on synthetic logs and the course load's pass on
    a real log;
  - the final session (one invocation, `--basetemp out/p28/budget/pytest_final`, log `pytest_final.log`): `tests/test_draw_budget.py
    tests/test_frame_rate.py tests/test_directory.py tests/test_hudname.py tests/test_tencourse.py`: **82 passed, 0 failed** in 66 min
    (none of the 15 known failing names is in these files).
- **Against main:** §6 (the game state the same at every pass's end on Big Forest and Metropolis, on the same battery RAM; the
  frame-end logs' difference traced, §6.1, link 3 partly read), §8 (the ROMs); since the fix wave on the same inputs, three courses
  (§13.2).
- **The three rate measures:** §5 (every list drawn, main's set), §5.2 (the standing test on the built 10 500 set against the old set).
- **The host's speed:** §7 (one machine).
- **Playtest set:** `out/p28play1` (`vrtools build`, byte for byte main's set but the four bytes), booted headless into the attract
  (§8). Launcher `out/rec161/launch.sh` (rec160's with rec160 → rec161 and p27play1 → p28play1). **`out/rec161/` already existed when
  this phase came to write it:** someone had put there rec160's `start/` (identical to rec160's), a `launch-now.sh` pointing at the
  scratch set `out/p28/budget/c10500` (byte for byte `out/p28play1`), a `mame.log`, `nvram/`, `cfg/` and a recording
  `inp/play.inp` written 08:38-08:40. They were left untouched; `inp/` is therefore not empty, and `launch.sh` records to
  `inp/play.inp`, so a launch would overwrite that recording: move it first if it is wanted. The scratch set `c10500` is kept for
  `launch-now.sh`.
- **Not verified:** §9.
- **Concerns:** the originals' worst frame is bounded only by the runs (9 771 against 10 500); linked play; frame-end logs need the
  pass log to compare sets with different drawing loads (the new test does).

## 13. Review and fix wave (15 Nov)

The independent review (read-only, `out/p28/budget/review.md`): **ready to merge with fixes; no Critical finding**; three Important
findings (one a gap in the standing test, two claims in the record wrong or incomplete) and nine minors. The fix wave rebased the
branch onto main after Phase 27b and did the following.

### 13.1 The rebase

`git rebase main`: textual conflicts in `docs/follow-ups.md`, `README.md` and `public/README.md` only (both sides appended); both
sides' content kept, Phase 27b's before Phase 28's; `public/README.md` keeps one "Unreleased (after v0.2.1)" heading, 27b's bullet
first. `tests/test_directory.py`'s SPANS (27b's `(0xFC40E1, 10)` and this phase's two immediates) and `autoplay.lua` (this phase's
loads, 27b's `;`-split `VR_EXTRA_LUA`) merged without conflict. Every pytest run since: `VR_MAME_JOBS=3`.

### 13.2 I2: the red/green divergence is the autopilot's; the game is unchanged on the same inputs [V]

**The record corrected:** §5.1 said the green run's frames over 5 500 were "the same frames as the red runs'". The logs say Big
Forest 853 red against 851 green, Acropolis 898 against 879; Bay Bridge and the four converted runs are the same frames. §5.1 now
says so; §6's finding, README, `deviations.md` and `follow-ups.md` say what was shown and under what conditions.

**The experiment** (`out/p28/budget/replay/`: `replay.py`, `cmp.py`, runs `M0 N0 R0 M2 N2 R2`). The red session's build is byte for
byte `out/p27play1` and the final session's `out/p28/budget/c10500` (all 38 members compared), so the standing races are re-run
exactly: Big Forest (entry 0) and Acropolis (entry 2), line 0, 150 s, `VR_HOLD_CLOCK=1`, with the pass log, the frame, rate, race,
collision and field logs, and the new `vrtools/mame/lua/input_tape.lua`, which writes the autopilot's wheel and pedal every frame
(`VR_INPUT_LOG`) or feeds a recorded tape back instead of the autopilot (`VR_INPUT_REPLAY`):

- **M** main's set, the autopilot steering (its race and frame logs are byte for byte the red session's on Big Forest; on Acropolis
  the race log is, the frame log differs in 4 busy values of 3-4 us at frames 339-359, before the coin);
- **N** the 10 500 set, the autopilot steering (its race log byte for byte the final session's on both);
- **R** the 10 500 set fed M's tape, frame for frame.

| | Big Forest | Acropolis |
|---|---|---|
| M against N: first differing input | frame 4 728: wheel 208 against 184 | frame 3 352: wheel 153 against 151 |
| M against N: first differing pass | pass 2 228 (frame 4 730); the 2 227 before identical | pass 1 540 (frame 3 354); the 1 539 before identical |
| M against N: the collision log's first difference | M logs the player's call cluster at frame 4 727, N does not (its next at 4 729) | N logs a cluster at frame 3 349 that M does not (both at 3 351) |
| M against R: inputs fed | identical (7 026 lines) | identical (7 026 lines) |
| M against R: pass log | **identical, all 4 177 passes** | **identical, all 4 177 passes** |
| M against R: frame-end logs | race 12 lines of 8 630, field 15 of 112 464, collision 3 lines not in M within 4 frames (and 2 of M's not in R) | race 11 of 8 635, field 39 of 112 464 (every differing field value in the other set within 4 frames), collision 1 |

**Conclusion:** with the same inputs the game's state at the end of every pass (the clock, all 16 cars' x, z, road point, speed,
lap) is identical to main's over the whole 150-s run on Big Forest and on Acropolis; in the closed-loop runs the first difference
is the autopilot's wheel, two frames before the first differing pass, with every pass identical before it. The divergence is the
test harness's: `autopilot.lua` takes the player's position from `collision_log.lua`, which groups the TGP calls by MAME's frame
end and logs a frame only when its first five calls are the player's cluster; the frame end falls inside a pass, and a pass that
starts a fraction of a microsecond later (§6.1) can put the cluster on the other side of it, so the autopilot sees a position one
frame earlier or later and steers otherwise [V the logs; R the cluster falling across the frame end, not traced call by call].
The same family as Phase 27's findings §7 (`collision_log.lua` grouping by MAME's frame end).

**The test** `test_the_game_is_the_same_pass_for_pass` now runs main's set first with the autopilot and `VR_INPUT_LOG`, then the
set with `VR_INPUT_REPLAY` of that tape, both with `VR_FRAME_LOG` (M3), on Big Forest, **Acropolis** and Metropolis (120 s each, the
shared battery RAM as before). It asserts: the tape the set was fed is main's line for line; main's run skipped lists and the set's
none; the pass logs identical over the whole run; every differing field-log value present in the other set within 4 frames. A
development run (`out/p28/budget/pytest_dev`, the three courses): main's runs skipped lists on 606 (Big Forest), 645 (Acropolis)
and 60 (Metropolis) frames, the set's on none; 3 314 passes identical on each; 5 299 tape lines each.

### 13.3 I1: the standing test covers the worst frames known [V]

`tests/test_frame_rate.py` gains `test_the_worst_known_frames_hold_the_arcade_rate` (three cases) and
`test_the_attract_holds_the_arcade_rate`, all three measures asserted:

- **Big Forest on road line 4 for 300 s** (`WORST_SECONDS`; the scratch run's 9 771 came at frame 13 187, after 150 s): asserted
  also that the run reaches frames needing more than 9 000 records;
- **a lap through the pit lane with a pit stop**, on an original and on a converted course, both affordable (150 s each, about a
  minute of wall time): Big Forest (the measurement's path rebuilt in the test, `bf_pit_path`: line 0 with the lane's x, −226,
  from road point 334 round to 29, blended in and out) and Metropolis (the pit tests' `normal_pit_path` on line 6); asserted also
  that the run holds a stop (the pit handler 0xff2345 for 300 frames or more after the green, inside the stretch). The stretch of a
  pit run does not end at a still clock (the clock stands still during the stop);
- **the attract for 300 s with no input** (`attract_snaps.lua` now loads `frame_rate.lua` and `renderrate.lua` when asked): from
  the main loop's first pass, the counter still, the render rate 28-29 in every window, the busy time under 34 770 us in every pass
  but the scene loads, which are named by main's set's own run: the passes of 34 770 us or more that main's set (the game's budget)
  makes at the same frames (`framerate.scene_loads`, `excused`). On main's set too they take 41-52 ms with the counter at 0.

The docstrings say what each measure sees: the counter is the per-picture detector; the render rate shows pictures keep coming and
misses a single lost picture in a 29-window (about half the positions). New synthetic tests show both (`test_one_lost_picture_is_
the_counters_to_catch`) and that only the named loads are excused (`test_only_the_named_scene_loads_may_take_longer`, red first:
an import error before `scene_loads` existed). The checks on synthetic logs that make each kind of miss fail are kept.

### 13.4 I3: the record of Pascal's words and runs

The intro, §1, §9, README's Phase 28 section and `follow-ups.md` now carry exactly: "3 first"; "Ok"; "It's critical the game stay
fluid at 60fps constant" (15 Nov), the lead's answer (the arcade draws one picture every second screen frame, about 29 a second,
the smoke test's "arcade rate" 27-29 per 57 frames; the guarantee is never below the original's own rate) and Pascal's "Yes"; the two
runs of the scratch 10 500 set (byte for byte `out/p28play1`), 53 s and 57 s, MAME at 100.00 % both with other jobs running, and
"this is good continue"; the question on the originals (told yes, the far-scenery skips go, and that it is a departure from the real
arcade); the third run after the review, 296 s, MAME at 99.98 %, tests running in the background, and "looks good so far". What
they drove was not stated. "They have driven nothing of this phase" is gone; §1's "holding 60 fps" is replaced by Pascal's own words.

**What the kept recordings show** (a fact about the recordings, not something Pascal said): copies of
`out/rec161/inp/pascal-2026-11-15-c10500-57s.inp` and `…-session3.inp` played back headless (MAME's `-playback` on `out/p28play1`,
from the launcher's own starting battery RAM and configuration `out/rec161/start/`; scripts `out/p28/budget/fix/play/`); the
recordings themselves untouched. MAME reports 3 318 and 17 058 playback frames (57.7 s and 296.6 s).

- **The 57-s recording:** one credit, Diablo Canyon (entry 5), normal direction; the race from frame 768 to the recording's end,
  in its first lap (road point 456 at most).
- **The 296-s recording:** a credit on Big Forest (entry 0): the race from frame 640, three laps and part of a fourth; the car stands
  still from frame 10 852 (road point 224) until the time runs out at frame 11 746. Then a second credit on Acropolis (entry 2),
  the race from frame 12 884 to the recording's end, in its first lap.
- **The three measures over them** (the same playback): the overrun counter 0 throughout; no list skipped; render rate 28-29 in every
  window after the boot; the V60's busy time in the races at most 12 433 us (Diablo Canyon), 14 587 us (Big Forest), 13 495 us
  (Acropolis). Frames whose need was above the game's 5 500 (which main's set would have cut): 8 of 1 274 logic frames on Diablo
  Canyon, 959 of 5 550 on Big Forest (need up to 9 205), 643 of 2 085 on Acropolis (up to 8 869).
- The 53-s run's recording is not among the kept ones (`out/rec161/inp/` holds the 57-s and the 296-s recordings, and `play.inp`, a
  copy of the 296-s one).

### 13.5 The ROMs and the playtest set [V]

- **`out/p28play2`**: `vrtools build` from the rebased tree (`vrtools.__file__` the worktree's), log `out/p28/budget/fix/build_p28play2.log`.
- **Against main's tree after Phase 27b** (`git archive main` built the same way into `out/p28/budget/fix/main27b`): of the 38
  members of `vr.zip` one differs, the boot ROM's `epr-14879a.5`, at the four immediate bytes (0x11c0-0x11c1 7c 15 → 04 29, 0x11d6-
  0x11d7 88 13 → 10 27); `model1io.zip` and `m1comm.zip` identical; the build reports identical but for the last line (the path).
- **Against `out/p28play1`** (before the rebase): six members differ, `epr-14878a.4` (20 bytes), `epr-14879a.5` (31), `epr-14882.14`
  (19 736), `epr-14883.15` (14 828), `mpr-14880.6` (10), `mpr-14881.7` (2); the build report shows the converted courses' tables
  0x30 bytes further on. These are exactly Phase 27b's changes: main's post-27b build against `out/p27play1` differs at the same
  byte positions in the same six members (`raceend` and its table, the boot site 0xfc40e1, and the directory image grown to 6 895
  bytes, which moves what follows it).
- **Launcher:** `out/rec161/launch.sh` now runs `out/p28play2` and still records to `inp/play.inp` (resetting `nvram/` and `cfg/` from
  `start/` as before); Pascal's kept recordings `inp/pascal-2026-11-15-c10500-57s.inp` and `inp/pascal-2026-11-15-c10500-session3.inp`
  are not touched by it. `inp/play.inp` is at present a copy of the 296-s recording and a launch overwrites it.

### 13.6 The minors

- **M1** (real hardware): one honest sentence in §9, `deviations.md`, README and the public README's bullet.
- **M2** (the counter's second writer, 0xfe03cf): `framerate.py`'s docstring and §1.
- **M3** (the identity test checks main's run skipped lists): done (§13.2).
- **M4** (`tests/test_draw_budget.py`'s stale docstring): rewritten.
- **M5** (`frame_rate.lua`'s need omits the character path at 0xff5e33): documented in its header (it never ran in the races).
- **M6** (`deviations.md`: 14.6 ms is races, the attract 18.0 ms; "the race is the same" scoped): done.
- **M7**: §6.1 (the mechanism) now comes before §6.2; 3 315 passes corrected to 3 314; `follow-ups.md` says link 3 is partly read.
- **M8** (the public README's "not yet played by hand"; "the arcade's own rate, about 29 pictures a second"): done.
- **M9** (`polyrom.py`'s comment): a comment only, left as it is.

### 13.7 The final invocation [V]

One invocation on the rebased tree (`VR_MAME_JOBS=3`, `-o addopts=""`, `--basetemp out/p28/budget/pytest_fix`, log
`out/p28/budget/pytest_fix.log`): `tests/test_draw_budget.py tests/test_frame_rate.py tests/test_directory.py tests/test_hudname.py
tests/test_tencourse.py tests/test_mame_runner.py`. Result: **116 passed, 0 failed in 3 820.95 s (1:03:40)**, on
commit a895b0a (the code as merged; only the record changed after it). Compared by name with the known failing list
(`out/p27/full_failed.txt`, 15 names): no failure, so no new one (none of the 15 is in these six files).

The session's rate runs (`pytest_fix/rate0/rate_summary.txt`), every one 0x501148 0 → 0, render rate 28-29, no list skipped,
the budget word 10 500 in every frame:

| run | logic frames | worst V60 busy (us) | need max |
|---|---|---|---|
| the 17 races (ten courses, seven reversed), 150 s | 3 511 each | 10 934-14 604 (Big Forest 14 604 at the start, frame 1 975) | 4 026-9 137 |
| Big Forest, road line 4, 300 s | 7 823 | 14 604 (the start) | **9 771** |
| Big Forest, pit lap (a stop) | 3 511 | 14 627 (the start) | 9 211 |
| Metropolis, pit lap (a stop) | 3 511 | 14 489 (frame 2 433) | 6 948 |
| the attract, 300 s, from the main loop's first pass | 8 478 | **17 973** (frame 9 087), outside the 15 scene loads main's set also makes (the same 15 frames on both sets) | 8 257 |

The worst V60 busy time now in the standing test: **17 973 us** (the attract; 52 % of 34 770), races 14 627 us (42 %). The identity
test: main's runs skipped lists on 606 (Big Forest), 645 (Acropolis) and 60 (Metropolis) frames, the set's on none; the tapes fed
identical (5 299 lines each); the pass logs identical (3 314 passes each); the field logs differ in 10, 31 and 2 lines, every
differing value in the other set within 4 frames.

### 13.8 Not verified

- **Real hardware:** MAME does not model the render board's time and the game does not wait for the renderer; Sega's 5 500 may
  match the renderer's capacity per picture; untested on a board, this change might cost pictures or leave them incomplete.
- **Linked play** (the second site, 10 000).
- **A frame busier than any measured:** as the review reads the walker, the game does then what it did past 5 500, at the new
  threshold: the list that crosses 10 500 is drawn whole and the later lists are skipped for that frame (the far cells drop out),
  and the character path cuts at 10 350. The highest need measured is 9 771 (Big Forest line 4, again in the standing test).
- The cause of the autopilot's parting is shown in the logs (§13.2), the cluster falling across the frame end read, not traced call
  by call; a harness fix (grouping by the game's logic pass) was not made: the identity test uses the replayed inputs instead.
- What Pascal drove was not stated by them; §13.4 is what the recordings show.
- A slower host, Windows, MAME drawing to a window beyond Pascal's three runs.

## 14. The re-review and the merge

- **Scoped re-review of the fix wave** (independent, read-only, 15 Nov): I1, I2, I3, M1, M4, M6 and the rebase ADDRESSED; the final
  invocation confirmed (116 passed on a895b0a; the later commit changes documents only); no new breakage. Four minors left, none
  blocking: **N1** the attract test puts no upper bound on an excused scene-load pass, takes its excused frames from the same
  session's build with the budget reverted rather than from a fixed baseline, and bounds their count loosely (< 60 against 15);
  **N2** `docs/deviations.md`'s "at most 18.0 ms in the attract's scenes" leaves out the 15 scene-load passes of 41-52 ms, which
  the original budget has too; **N3** the pit case asserts 300 handler frames, not the stop's release (the runs did release);
  **N4** the README and the follow-ups state the autopilot's cause without "read, not traced call by call".
- **Merged into main and pushed on 15 Nov 2026** on Pascal's "merge update md commit and push then continue", given after the
  session lead reported the re-review. Not released: the public notes stay under "Unreleased (after v0.2.1)". The whole suite
  has not been run on the merged tree; the session lead starts it after the merge.
