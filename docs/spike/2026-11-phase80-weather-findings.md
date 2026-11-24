# Phase 80: weather (branch `phase80-weather`), findings

The weather feature built in stages on one branch (master plan `docs/superpowers/plans/2026-11-18-weather-storm.md`, design
`docs/superpowers/specs/2026-11-18-weather-storm-design.md`). Not merged; the branch waits for the storm.

## Stage 1: the screens and the weather byte (18 Nov 2026)

Stage plan `docs/superpowers/plans/2026-11-18-weather-stage-1-screens.md`. Code `vrtools/arcade/weather/` (`screen.py`, `layout.py`,
`tune.py`, `__init__.py`), the switch in `tencourse.ten_course_set(weather=True)` and `vrtools build --no-weather`; formats note §24.

### What Pascal said (exactly) and what is not theirs

- 17 Nov: "When: an addition weather selection screen like the reverse but for weather". 18 Nov: "btw i think storm and rain
  shoudl be together (no separation on the course selection)" (two choices).
- On the prototype sets they drove: "screen is good except, when changing, it doesnt hilight the one active" (out/p64weather);
  "i think leave the color the same on the selected one for the weather selection screen, you dont want the rain circuit dimmed"
  (out/p67weather); "the color change is working", then "i just notice a separate bug: selecting reverse or normal doesnt grey
  out the one not selected (will need a fix)" (out/p69weather). out/p71weather has that fix; it is the behaviour this stage keeps.
- Rain races keep no best times: "Ok". Linked play: "Let's do it later".
- Not Pascal's decisions (the session lead's calls, `ScreenTune` and the art): the word RAIN, the cloud-with-bolt badge on all ten
  courses and none on DRY, the steering zones, the 10-s countdown; the direction screen's grey-out shipping behind the weather
  switch. Pascal has driven the prototype sets, not this build.

### The port

- **The prototype's bytes.** `out/p80/scripts/port_check.py` (scratch, not committed) builds main's conversions once and compares:
  - `ten_course_set(..., weather=False)` against main's CLI set at this branch's base (`out/p35play2`): every region byte for
    byte;
  - the port with the prototype's placement (its report on the same build) against `out/p71weather`: every region byte for byte
    (the routines, the pieces, the art, the sites: the same machine code and data);
  - the port as laid out against `out/p71weather`: the program ROM differs at four pieces moved (below) and at the two pointer
    tables naming them (0x2dff08..0x2dff57); nothing else.
- **What changed from the prototype.**
  - **Four pieces moved out of the spawn-list slots.** The prototype's best-fit search put the weather pieces of Acropolis
    (`piece2`, `dpiece2`) and the converted courses' (`piece_conv`) and Bay Bridge's direction piece (`dpiece1`) in the erased tails
    of Alpine's and Pacific Coast's spawn-list slots (0x287670, 0x289280): room `tencourse.spawn_list_address` keeps for up to
    MAX_ENTITIES objects a course, so a course given more props would have failed the build. They lie in the colour-table run's
    erased tail below the direction screen's block now ("screen pieces 3", 0x2be160, 1 012 of 1 024 bytes); the layout check
    treats the spawn-list slots as main's reserved room.
  - **One layout table.** The best-fit search over the set's erased runs is gone: every block is named at a fixed address
    (`layout.TABLE`, `layout.CONTENTS`), checked against main's reserved blocks, the spawn-list slots and each other, and checked
    erased before anything is written. The sites are in `layout.blocks()` too, found in main's routines as main's layout
    assembles them.
  - **No environment switch.** The prototype read `VR_WEATHER` inside `ten_course_set`; the build follows its arguments only.
  - Cleaned: named constants from `ScreenTune` and `dirscreen` (the prototype's 0x100000 placeholders for laid-out routines, its
    unused `routines` defaults, the darkening routine's remains), one `Inputs` record for what the code reads from the set, the
    install returning a new set (`install_weather`) with every site checked before the first write.

### Space

| block | where | bytes used / size |
|---|---|---|
| screen code | program ROM 0x2df9c0 | 1 432 / 1 472 |
| screen pieces 1 | program ROM 0x28f320 (below the originals' picture block) | 644 / 656 |
| screen pieces 2 | program ROM 0x28fd80 (above the start gantry's block) | 492 / 496 |
| screen pieces 3 | program ROM 0x2be160 (below the direction screen's block) | 1 012 / 1 024 |
| screen graphics 1 | bank 0 0x1df240 | 2 472 / 2 480 |
| screen graphics 2 | bank 0 0x1ffb10 | 1 212 / 1 216 |
| sites | directory image (3), originals' picture block (2), boot ROM 0xfc40ce, 0xff4799 | in place |
| RAM | 0x502296 (the direction word's third byte) | nothing new |

The directory image keeps 7 221 bytes (bound 7 300). No boot ROM erased run is used (left for the storm's stubs).

`layout.check(rs)` refuses a block that overlaps main's reserved blocks, the seven spawn-list slots (0x287220..0x28a33c) or (fix
round 1) the reverse variants' annex as the set holds it (`layout.annex_span`: 0x2b9120..0x2be150 on this build, its 1 164-byte gap
between the load and maps records included); "screen pieces 1" lies in annex region 1's leftover and "screen pieces 3" just past
the annex's end, in region 2's leftover. **Room left after the weather's blocks** (erased runs of at least 96 bytes in the program
ROM outside every reserved block, the spawn slots and the annex; 256 in bank 0): program ROM 0x28ff70..0x290000 (144 bytes),
0x2be560..0x2be8b0 (848), 0x2dff80..0x2e0000 (128): about 1.1 KB, in pieces; bank 0 0x1dfbf0..0x1e0000 (1 040). The storm's data
goes to banks 2 and 3 (design approach 1); these leftovers will not hold it.

### The test harness (D2 of the stage plan)

On a set with the weather screen `autoplay.lua` answers COURSE DIRECTION earlier (REVERSE steered from 1260, the press at 1300: the
lock on 1302), the hold runs to 1336, and the gas floored at 1400 as before locks COURSE WEATHER on 1402 (DRY, or RAIN with
`VR_RAIN=1`): the race loads on 1600 as on main, so every race-driving test keeps its frames. `run_mame` passes where the screen's
first routine is and its first word (`VR_WEATHER_SELECT`, `VR_WEATHER_WORD`); a set without the screen is answered as before.
`race_end.lua`'s second game answers the same way. `slot_log.lua` takes the locked screen's characters again at the weather lock.
New: `weather_log.lua` (the select screens' palettes frame by frame) and `runner.parse_weather_log` / `palette_at`.

Round 2 (after two runs of fix round 1's final session were disturbed from outside): every test run's command
(`runner.mame_command`, used by `run_mame` and by the recorded-drive replay test) sets MAME's keyboard, mouse, light-gun and
joystick providers to `none`, so a real device cannot reach the emulated inputs (a gas edge had arrived at frame 1122 of a run
before any scripted press; a mouse with keyboard-mapped buttons was attached); and a run MAME ends with SIGKILL from outside the
runner is run once more from the work directory as it was, with a `MameKilledWarning` in the test summary (a second kill, a crash
or the runner's timeout still fail at once).

### Results (headless MAME 0.289; `tests/test_weather_screen.py`, `tests/test_weather_dry.py`)

| check | result |
|---|---|
| the chain, steered by hand (Metropolis, Bay Bridge: REVERSE, then RAIN) | course lock 1202, COURSE DIRECTION 1204, its lock 1302 (`wxsel`), the hold to 1336 (16 logic frames, `DIR_PHASE` 5), COURSE WEATHER 1336, its lock 1402 (the byte 1), the race load 1600, as main's after its direction lock on 1402 |
| every choosing frame (palette RAM, exact, the frames whose choice was the same two frames before) | direction screen 76 frames, weather screen 50 frames a run, both choices, three changes on each screen: the side shown in the record's normal set, the other in its grey set; an original's A palettes, its ring palettes (direction) and its badge groups (weather) likewise |
| the lock looks | the hold: the direction's lock look (chosen / grey; an original's origpic lock lists) on every frame from the lock + 2 to the weather screen; the weather's lock look (RAIN: the badge in colour) on every frame from its lock + 2 to the load |
| the cursor frame (snapshots, eight frames each) | DRY box (62, 28)-(209, 218) round the picture (72, 40)-(199, 207), RAIN (286, 28)-(433, 218); its top at y 28, the title on 0-23; steady after the weather lock; during the hold on the direction's chosen side |
| the weather screen drawn (tile, character and palette dumps, DRY and RAIN shown) | the title, labels, the four game maps one row lower, the caption (block 0x3580, palette 0x73's), the badge (converted: block 0x3480), both pictures in slot 0's and slot 2's words; nothing else on layer 0 but the countdown and the game's mark |
| no logic frame skipped (the counter every two video frames, the course lock to the load) | 199 steps (both steered runs), 693 (nobody answering), 454 (RAIN left to the countdown) |
| nobody answers (the course's press held; a coin at 1900 and START held 1920-2120 on the weather screen) | direction countdown lock 1780 (NORMAL), the hold, weather open 1814, countdown lock 2390 (DRY, no gas edge), load 2588; the byte 0 and the automatic transmission through the race |
| RAIN left to the countdown (Big Forest) | locked RAIN at open + 575, the byte 1 through the race |
| the test switch on the weather screen (1370) | the game stops in the test mode; EXIT (1900) restarts it (2203: the whole direction word 0), the attract from 2470 with the word 0, a coin: the select with the word 0 (3017), its countdown opens COURSE DIRECTION again (4232) |
| a stale byte | after the RAIN game the attract load clears the word 2 frames into mode 0x02 (bankdemo), nothing reads it there; 0 to the second game (Surfers Road, answered DRY) and through its race; the operator's fixed course with the word poked to a RAIN lock: 0 from the first select frame, SHIFT MODE SELECTOR's chain, 0 in the race, no HUD word; linked play by the code path |
| the HUD word | RAIN on rows 46-47 in colour base 0x8180 (none of the level words' 0x8100, 0xc180, 0xc100): columns 55-58 (Big Forest), 47-50 left of REVERSE 52-58 (Metropolis), 46-49 left of REVERSE 51-57 (Bay Bridge); nothing in DRY races |
| records | a one-lap DRY race on Metropolis (autoplay's answer) on the weather set and on the set without it: the same 474 writes in the same order, both with the name entry; **the same race RAIN (`VR_RAIN=1`): no write in any best-time table or slot, no name entry** (fix round 1's control: the DRY race records, so the gate does the work); the conv run's one-lap RAIN race in reverse writes nothing either, but that lap would not reach the reverse table's fourth time (found in fix round 1: the same lap DRY writes nothing), so on its own it proved nothing about the gate |
| the course select on a second game (after the RAIN game) | each slot's characters and palettes its record's, the text palettes the first game's |
| DRY is main's race (13 cases: all ten courses, Big Forest, Metropolis and Surfers Road in reverse) | pressed: the load on 1600 as main's; by the countdown: on 2110; 1 213 passes compared (1 303 on the countdown runs): **no difference on any case**; the race pictures at 600 and 1 200 frames after the race start identical |
| the screens' passes (frame_rate.lua and stale_list.lua, the course lock to the race load; steered: Metropolis, Bay Bridge; countdowns: Surfers Road, Big Forest) | **no stale display list** (`tests/test_frame_rate.py`'s `_stale` with the course lock as the stretch's start and the load as its end; no pass on the screens is a long pass, so none is excused), the overrun counter still, no object list skipped. Busiest: COURSE WEATHER's first pass 18.83 ms on all four runs (the frame-end wait before its first clear), COURSE DIRECTION's first pass 18.88 ms on an original (main's `osel`, the same wait) and 14.74 ms on a converted course; DEADLINE_MS 18.9: **margins of 0.07 and 0.02 ms**, a finding (no 3D is drawn on either pass; on main the busiest attract pass is 17.98 ms and the busiest race pass 15.52 ms) |
| the switch | off: the set given, untouched; off = main's CLI set (`out/p35play2`) in every region; on: only the program ROM, the boot ROM and data bank 0 differ, every changed byte inside a block of `layout.blocks()`, every block written |

### Main's tests changed, and why

The suite's session set (`tests.test_tgp_build._seven`) has the weather screen now, and the harness answers both screens so the
race loads where it did (above). The tests below pinned the direction screen's old look or timing, or compared the session's set
byte for byte with a set that cannot have the screen; each says in its docstring how it changed.

- `tests/test_dirscreen_build.py` (run on the weather set):
  - helpers: `_screen_handlers` knows `wxdir`; `_weather` and `_weather_lock` (the weather lock: the handler back to 0xfc277c
    with `DIR_PHASE` 4); `_screen(seconds=)`; ANSWER_LOCK 1302 (was 1402), WEATHER_LOCK 1402 (new), ANSWER_LOAD 1600 (unchanged);
    LATE 1298 (was 1390), SNAPS[1] 1288-1295 (was 1370-1377), LOCKED_SNAPS 1310-1317 and LOCKED_DUMP 1320, in the hold (were
    1440-1447 and 1462): autoplay locks the direction 100 frames earlier;
  - `test_the_flag_is_zero_whenever_a_select_screen_starts`: the second game's direction lock hands over to `wxsel`, the race loads
    198 frames after the weather lock (both screens left to their countdowns); the run 450 s (was 430);
  - `test_the_countdown_decides`, `test_the_course_press_does_not_confirm`: 60-s runs (COURSE WEATHER's countdown comes before the
    race); assertions unchanged;
  - `test_an_original_shows_the_screen`, `test_the_screen_is_sound_with_the_other_select_setting`: the lock hands over to `wxsel`,
    the load measured from the weather lock;
  - `test_the_lock_to_load_timing_is_the_games`: the direction lock on 1302 (`wxsel`, `DIR_PHASE` 2), the weather lock on 1402,
    then 0xfc27be, the load on 1600;
  - `test_the_screen_shows_the_picked_course_twice`: slot 2 (REVERSE, not shown) holds the record's grey set (was its normal set:
    Pascal's grey-out);
  - `test_the_frame_is_steady_after_the_lock` became `test_the_frame_stays_round_the_choice_through_the_hold`: during the hold the
    handler is `wxsel`, under which the game's cursor code blinks the frame (main's lock handed over to 0xfc27be, steady); the frame
    blinks in the same box; steadiness after the weather lock is `tests/test_weather_screen.py`'s; the on look's colour (red and green
    above 200 and 160, blue under 100 on average) is kept (fix round 1: the first rewrite had dropped it);
  - `_locked`: also checks the weather lock on 1402; `test_the_lock_keeps_the_chosen_picture_in_colour`,
    `test_the_arrows_show_each_direction`: their LOCKED_DUMP is in the hold now (docstrings), assertions unchanged;
  - `test_no_screen_after_the_lock_shows_the_middle_slot`: the locked screen is COURSE WEATHER's (its badge and caption, the last
    pieces written into the middle slot before the race; `slot_log.lua` takes them at the weather lock) where it was the direction
    screen's arrows and caption; this module's reading of the dumps checks both screens' characters that survive to the race load
    (the arrows' past the badge's and all of the anticlockwise arrow's, with the weather's badge and caption over them; fix round 1).
- `tests/test_originals_reverse.py`:
  - `test_an_originals_picture_on_the_direction_screen_is_the_course_selects`: the side not shown in the grey look (A, B and ring);
    the lock look read in the hold (1320, `DIR_PHASE` 5; was 1500, now COURSE WEATHER);
  - `test_no_frame_of_an_originals_lock_shows_a_half_drawn_picture`: a whole picture in the normal or the grey look (each pixel in
    one of the two on the frame the palettes change);
  - `test_a_converted_courses_lock_frames_are_the_set_befores`, `test_the_picture_block_and_the_lock_site`,
    `test_the_originals_variants_only_add_bytes`: on the session's set without the weather screen (`_seven_dry`), which is what
    they compare (origpic's `olock` against `dirlock`; origpic's block; the originals' variants); the weather screen's own changes
    are `tests/test_weather_dry.py::test_the_switch_changes_only_the_named_blocks`.
- `tests/test_reverse_times.py::test_the_race_end_s_record_site_is_the_game_s_again`: the arcade's bytes on the set without the
  weather screen; on the weather set the site calls `wxgate`.
- Not changed but run on the weather set: the rest of `tests/test_dirscreen_build.py`, `tests/test_originals_reverse.py`'s
  `test_the_course_select_is_the_same_after_an_originals_direction_screen_and_race` (the second game's course select after an
  original's two screens and race, byte for byte the set before Phase 33's) and `test_the_normal_game_is_the_set_before_pass_for_pass`
  (twelve races, the weather set against the set before Phase 33, identical pass for pass), `tests/test_reverse_ranking.py`,
  `tests/test_ranking.py`, `tests/test_cli.py`, `tests/test_directory.py`.

### TDD evidence

- The static tests were written before the package; their first runs failed on the then empty layout table, then passed.
- The screens' palette test, run (scratch, `out/p80/scripts/red_p69.py`) on the prototype set before Pascal's direction-screen fix
  (`out/p69weather`): **fails** on the direction screen's first stable REVERSE-not-shown frame (1220: slot 2's palettes 0x6c-0x6e,
  the next art's A palettes 0x64-0x65 and the ring palette 0x6a not grey); on `out/p71weather` and on this build: passes.
- The first MAME run of the new tests failed on four test errors (fixed): a race list that took in the second game's race; the
  attract's first two frames, before bankdemo's clear (measured, then bounded); main's own weather byte (on main 0x502296 is the
  direction screen's arming flag, 1 in its races); a helper that read a field race_end.lua's log does not have.

### Gates stage 7 must run with a variable set

- `tests/test_weather_dry.py::test_weather_off_is_mains_set_member_for_member` skips without a build of main at this branch's base:
  run it with `VR_PRE_WEATHER_SET=<directory of that build's vr.zip>` (here `out/p35play2` in the main checkout, which the
  worktree's default path does not reach). Fix round 1's final run set it; the test ran and passed.

### Not verified

- Linked play (one cabinet): asserted by the code path only (`test_linked_play_never_reaches_the_screens`).
- Real hardware, including the frame-end wait before the weather screen's first clear (in MAME it leaves that pass 0.07 ms under
  the display-list deadline, and main's own wait on an original's direction screen 0.02 ms).
- Pascal has not driven this build (the prototype sets only).

## Stage 2: the carrier, the rain, the splashes and the sky (19 Nov 2026)

Stage plan `docs/superpowers/plans/2026-11-18-weather-stage-2-rain.md`. Code `vrtools/arcade/weather/carrier.py` (the carrier and
its RAM contract), `rain.py`, `layout.py` and `tune.py` (`RainTune`), the assembler's float and string-move forms (`v60asm.py`;
an `ldpr` form for the removed clock was dropped in fix round 1); formats note §25. Tests `tests/test_weather_carrier.py`, `tests/test_weather_rain.py`.

### What Pascal said (exactly) and what is not theirs

- Of the rain prototypes (17 Nov): "rectangleish drops falling with depth perspective", "transparent 3d paralellepipedes"; of the
  streaming drops "they should probably still be falling down"; "One thing that feel missing is the impact on the road, it look
  like they're floating"; "i think the rain should be a bit thinner, there was also some glitch appearing can you check?" (the
  glitch "like a flash", thinner "narrower drops"); then "the rain is good". Of the stipple haze: "just look like a grid".
- Of the draw budget: "It's critical the game stay fluid at 60fps constant".
- Not Pascal's: the time cap (the spec's 17.4 ms margin was the session lead's; the cap is now 17.8 ms, the prototype's guard's
  bound, by the session lead's ruling), the start-up spread, the carrier's layout. Pascal has driven the prototype sets (`out/p48rain`, `out/p70storm`, `out/p75storm`),
  not this build.

### The port

Rewritten from spike 46/47/48's and spike 70's listings (not pasted); every value the prototype's. Checked against the prototype's
own functions (branch `spike70-storm`, run in its worktree): the 40 drop objects and the drop table, the 12 splash objects, the
overcast and the boot's colour tables, the colour picks and the ten courses' grey skies are byte for byte the prototype's (hashes
and picks pinned in `tests/test_weather_rain.py`). The prototype picked its colours against a MAME dump of palette RAM; the build
picks them against the program ROM's polygon palette (0x2ec980, 897 colours: what the boot copies to 0x902000 at 0xfe6b04, less
the two entries the game changes at run time) and gets the same eight entries.

What differs from the prototype, each from a gate:
- **A clock for the time guard (SUPERSEDED, removed in the fallback round below: it crashed under the test menu's memory test).**
  The prototype's guard stopped the rain at the first vblank after the wait (the count 0x500501,
  17.38 ms) and then still made a row of the grade: its stopped passes ended at 17.4-18.06 ms. The spec's 17.4 ms cannot be held
  with that count (the work after the hook alone is about 25 us). The board's interval timer (0xe00008 period, 0xe0000c count, in
  units of 2 048 V60 cycles; unused by Virtua Racing; its interrupt, IRQ 0, masked by the game: 0xe00002 = 0xfd) gives one: while
  the storm is loaded SBR points to a RAM copy of the boot ROM's vector table whose vblank vector restarts the timer and enters
  the game's own handler (0xfe02bc). The guard stops at 134 units (17.152 ms since the vblank interrupt, which comes before the
  measured pass starts), so a stopped pass ends under 17.4 ms. DRY never swaps SBR and never writes the timer.
- **The start-up spread over passes** (spec section 6): F0, the storm's first scenery call (the first countdown pass): the copy
  (image, both colour tables, the course's grey and own sky), nothing drawn; F1.. the start passes: the 60 clusters placed (with
  the drops already under the ground landed, no splash), 20 a pass (`rain.START_QUOTA`, the fallback round): three start passes;
  then the first visible pass, an ordinary rain pass that also writes the grey sky and starts the grade. The prototype copied in
  one pass and placed and drew all 60 clusters in its first rain pass (17.84-18.06 ms on every course).
- The grade: 3 rows a pass, each after the guard (`rain.GRADE_ROWS`, the fallback round: 32 passes; the prototype made one row a
  pass always and up to 8 while no vblank had come); the rows are copied from the overcast table built here (the prototype computed
  them on the V60: the same values).
- Not in this stage (later stages, on this carrier): cover, lightning, wet handling, sound. It rains inside tunnels.

### Results (headless MAME 0.289; `tests/test_weather_rain.py`, `tests/test_weather_carrier.py`) — SUPERSEDED by the fallback round

These figures are the first build's, with the clock (17.4 ms cap); the fallback round's below replace them.

**RAIN on every course, both directions** (`test_rain_holds_the_rate`, `test_the_start_up_is_spread`): the rate tests' autopilot
lines, 150 s with the clock held, measured from the pass after the course load (1605) to the race's end; the storm's load (F0) is
the first countdown pass (1607), the start passes follow, then the first visible rain pass. Every pass at most 17.4 ms; no stale
display list (the check's own excused pass after the load aside, as on main); the overrun counter still; the render rate 28-29;
no list of the game's skipped; the rain never took a frame's records over 10 500; 60 clusters drawn on the median visible pass.
Trims: by the records budget (clusters / splashes left out) and by the clock (clusters not reached / splashes ended), whole race.

| course | dir | busiest ms (frame) | F0 load ms | start passes ms | first rain frame ms | stale | records peak / game's need | clusters / splashes median | late passes | budget trims cl/sp | clock trims cl/sp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Big Forest | nor | 17.10 (1991) | 11.90 | 16.96 14.09 | 15.87 | [] | 10500 / 9211 | 60 / 9 | 36 | 382/127 | 13/112 |
| Big Forest | rev | 16.87 (2691) | 11.27 | 16.08 | 13.95 | [] | 10500 / 9708 | 60 / 9 | 0 | 649/1288 | 0/0 |
| Bay Bridge | nor | 17.02 (3507) | 11.91 | 16.70 | 14.58 | [] | 9344 / 6922 | 60 / 13 | 35 | 0/0 | 0/84 |
| Bay Bridge | rev | 17.07 (5853) | 12.42 | 16.93 11.77 | 15.10 | [] | 9839 / 7539 | 60 / 9 | 62 | 0/0 | 0/124 |
| Acropolis | nor | 17.04 (1623) | 13.65 | 17.00 13.62 | 16.07 | [] | 10498 / 8339 | 60 / 9 | 21 | 4/11 | 0/40 |
| Acropolis | rev | 16.99 (1943) | 13.59 | 16.93 13.39 | 15.90 | [] | 9322 / 7373 | 60 / 9 | 9 | 0/0 | 0/22 |
| Alpine | nor | 15.98 (1609) | 11.11 | 15.98 | 13.20 | [] | 6034 / 4078 | 60 / 9 | 0 | 0/0 | 0/0 |
| Alpine | rev | 16.20 (1609) | 11.33 | 16.20 | 14.04 | [] | 6550 / 4586 | 60 / 10 | 0 | 0/0 | 0/0 |
| Amazon Falls | nor | 15.33 (2525) | 10.35 | 15.24 | 13.11 | [] | 6711 / 4522 | 60 / 9 | 0 | 0/0 | 0/0 |
| Amazon Falls | rev | 15.74 (2523) | 10.42 | 15.20 | 13.06 | [] | 7304 / 5247 | 60 / 9 | 0 | 0/0 | 0/0 |
| Diablo Canyon | nor | 16.98 (1609) | 12.46 | 16.98 | 14.86 | [] | 7725 / 5711 | 60 / 9 | 0 | 0/0 | 0/0 |
| Diablo Canyon | rev | 17.01 (1609) | 12.92 | 17.01 12.24 | 15.37 | [] | 7939 / 5960 | 60 / 10 | 0 | 0/0 | 0/0 |
| Metropolis | nor | 16.94 (1609) | 12.76 | 16.94 11.75 | 15.01 | [] | 8573 / 6464 | 60 / 10 | 0 | 0/0 | 0/0 |
| Metropolis | rev | 16.95 (1609) | 12.59 | 16.95 11.51 | 14.99 | [] | 7280 / 5275 | 60 / 9 | 0 | 0/0 | 0/0 |
| Pacific Coast | nor | 16.42 (2477) | 10.45 | 15.35 | 13.23 | [] | 7332 / 5273 | 60 / 10 | 0 | 0/0 | 0/0 |
| Pacific Coast | rev | 17.14 (2191) | 11.18 | 15.95 | 13.72 | [] | 6706 / 4738 | 60 / 10 | 1 | 0/0 | 0/33 |
| Surfers Oval | nor | 15.89 (2631) | 10.11 | 15.03 | 12.90 | [] | 6103 / 4026 | 60 / 9 | 0 | 0/0 | 0/0 |
| Surfers Oval | rev | 15.10 (2127) | 10.26 | 15.03 | 12.91 | [] | 6251 / 4030 | 60 / 8 | 0 | 0/0 | 0/0 |
| Surfers Road | nor | 16.47 (2519) | 10.14 | 15.08 | 12.95 | [] | 7334 / 4910 | 60 / 9 | 0 | 0/0 | 0/0 |
| Surfers Road | rev | 15.51 (2403) | 10.33 | 15.14 | 13.01 | [] | 7626 / 5499 | 60 / 9 | 0 | 0/0 | 0/0 |

The first rain frame is now an ordinary rain pass (12.90-16.07 ms; the prototype's was the worst pass of nearly every run,
17.84-18.06 ms); F0 costs about 0.05 ms over main's same pass (Big Forest: 11.90 against 11.85); the heaviest start passes are
the placement's (up to 17.01 ms, stopped by the clock, the rest placed on the next pass). The clock trims far less than the
prototype's guard did (its storm also ran cover, lightning and the per-drop curtain); the records budget trims the rain on Big
Forest's and Acropolis's heaviest frames, as in the prototype ("rain on Big Forest is trimmed by the records budget on its busiest
frames": spec 7). Big Forest in reverse trimmed more clusters than the prototype's run (649 against 19): its autopilot's line
reached frames with the game's need up to 9 708 (the rain's longer passes move the frame-end samples the autopilot steers by, as
Phase 79 found for first-boot work); 649 of the race's about 210 000 cluster draws.

**Big Forest's heaviest place in RAIN** (`test_only_rain_is_trimmed`: road line 4, 150 s, the session battery RAM): the game's
need up to 10 302 (none of its lists skipped), the rain trimmed by the budget (480 clusters, 148 splashes) and the clock (12 / 110),
busiest pass 17.07 ms. On 5 passes the game's own lists ended past 10 500 (records peak 11 275: its walker tests the budget before
each list and the last one ran over, need 10 302); the rain drew nothing on them. The need is above the 9 704 that line's DRY run
measures: the rain's longer passes move the autopilot's frame-end samples and the car took another line (the game's lists are
its own: the rain is emitted after the walker).

**DRY** (`test_dry_runs_no_storm_code`): a DRY race on Big Forest (70 s) and 200 s of the attract on the weather set, traced: from
the boot's end (its RAM clear at frame 271 and its one write of the timer) no write into 0x520000..0x53efff, no write to the timer,
SBR 0xfff000 and the carrier idle at every pass. The switch test's cost: the same DRY race on the `weather=False` set, 1 210 race
passes compared pass by pass: the set's busy time over it by 2.1 us on the mean pass (median 3 us; single passes jitter between
-50 and +45 us, the vblank interrupt landing elsewhere in the work). DRY's race state is main's pass for pass
(`tests/test_weather_dry.py`, final run below). The attract's busiest pass outside its scene loads: 17.71 ms in the traced 200 s
(main's 17.98 ms in 300 s, stage 0; `tests/test_frame_rate.py`'s attract on the final tree below).

**A race ending, a second game** (`test_a_rain_race_ends_clean`, `test_time_over_mid_rain_ends_clean`,
`test_a_second_game_starts_clean`; Review Focus 2 and 5): RAIN on Big Forest to its end (race_end.lua): mid-race the colour RAM is
the overcast table and the backdrop the course's grey; the race's modes 0x15, 0x16, 0x1b, 0x1c rain, 0x1d draws no scene, and the
attract's first scenery call (the weather byte cleared by `bankdemo`) releases: the colour RAM the boot's table, the backdrop the
course's own colours, SBR 0xfff000, the timer stopped, the carrier idle; nothing of the storm runs through the attract and a DRY
second game on Metropolis. A RAIN second game on Alpine loads again (second load; the cells zeroed: its start passes place the
clusters anew) with Alpine's grey sky. RAIN ended by time over 200 frames after the start (splashes on the road, the grade made):
released the same way at the first scenery call off the rain's modes.

**The HUD, the lamps and the READY board** (`test_the_hud_lights_and_ready_board_keep_their_colours`, Metropolis, RAIN against DRY
at the same frames, the countdown and the race): the whole palette RAM equal but for the backdrop's colours, the tile maps equal
but for the HUD word RAIN, the HUD's text pixels equal. The start gantry, its READY board and its lamps are 3D objects: the grade
greys them as it greys all the 3D picture, as in the prototype Pascal approved (spike 44's notes: "the board's blue and the lamps'
red keep their saturation"): the board's band 60/60/185 in DRY, 66/73/155 in RAIN; a lit lamp 226/0/0, 183/33/40. The spec's
"keep their colours" is read here as the prototype's behaviour, not pixel-identical: the session lead accepted that reading (the
approved prototype is the reference for the look; a hue test is the right one) and corrects the design's sentence on main.

### Space: the room left (the final build; fix round 1)

Generated, not counted by eye: `weather/layout.py`'s `room` on the weather set (every block of `layout.blocks()`: the storm's
blocks as `carrier.build` reports them, the sites their size, stage 1's ROM blocks to their last byte that is not 0xff; checked by
`tests/test_weather_carrier.py::test_the_room_table`), rendered by the scratch script `out/p80/s2/scripts/roomtable.py`. The last
column counts the erased runs of 96 bytes or more in each ROM space outside the weather's blocks (and, in the program ROM, outside
main's reserved blocks and the converted courses' spawn-list slots), in the final set: the room later stages have beyond their
blocks. Formats §25 gives the same figures.

| space | block | address | bytes | used | left |
|---|---|---|---|---|---|
| program ROM | screen pieces 1 | 0x28f320 | 656 | 644 | 12 |
| program ROM | screen pieces 2 | 0x28fd80 | 496 | 492 | 4 |
| program ROM | rain colours | 0x28ff80 | 96 | 92 | 4 |
| program ROM | screen pieces 3 | 0x2be160 | 1 024 | 1 012 | 12 |
| program ROM | screen code | 0x2df9c0 | 1 472 | 1 432 | 40 |
| data bank 0 | screen graphics 1 | 0x1df240 | 2 480 | 2 472 | 8 |
| data bank 0 | screen graphics 2 | 0x1ffb10 | 1 216 | 1 212 | 4 |
| program ROM (sites) | bankdemo's clear | 0x2799f6 | 8 | 8 | 0 |
| program ROM (sites) | start's jmp dirdone | 0x27a1ad | 6 | 6 | 0 |
| program ROM (sites) | dirsel's lock | 0x27b1fc | 9 | 9 | 0 |
| program ROM (sites) | olock's original handler | 0x28f5fd | 9 | 9 | 0 |
| program ROM (sites) | olock's converted handler | 0x28f608 | 9 | 9 | 0 |
| boot ROM (sites) | the race end's record test | 0xfc40ce | 16 | 16 | 0 |
| boot ROM (sites) | the scenery call | 0xfee144 | 6 | 6 | 0 |
| boot ROM (sites) | the HUD's call | 0xff4799 | 6 | 6 | 0 |
| work RAM | weather byte | 0x502296 | 1 | 1 | 0 |
| work RAM | storm RAM cells | 0x520000 | 8 192 | 2 944 | 5 248 |
| work RAM | storm RAM image | 0x522000 | 32 768 | 4 880 | 27 888 |
| work RAM | storm RAM data | 0x52a000 | 86 016 | 26 640 | 59 376 |
| boot ROM | storm stub | 0xfff120 | 1 280 | 940 | 340 |
| data bank 3 | storm image | 0x1df4c0 | 20 480 | 4 880 | 15 600 |
| data bank 3 | storm data | 0x1e44c0 | 24 576 | 24 576 | 0 |
| data bank 3 | storm course data | 0x1ea4c0 | 10 496 | 9 664 | 832 |
| polygon ROM | rain objects | 0xfda424 | 64 448 | 64 448 | 0 |

| space | blocks' bytes | used | left in the blocks | erased runs of 96+ bytes elsewhere |
|---|---|---|---|---|
| program ROM | 3 744 | 3 672 | 72 | 2 140 |
| data bank 0 | 3 696 | 3 684 | 12 | 1 165 |
| program ROM (sites) | 41 | 41 | 0 |  |
| boot ROM (sites) | 28 | 28 | 0 |  |
| work RAM | 126 977 | 34 465 | 92 512 |  |
| boot ROM | 1 280 | 940 | 340 | 6 026 |
| data bank 3 | 55 552 | 39 120 | 16 432 | 389 904 |
| polygon ROM | 64 448 | 64 448 | 0 | 90 140 |

The directory image is not touched (7 221 of its 7 300 bytes, as stage 1 left it). Data bank 2 is not used (approach 3 not needed).
The clock build's table that stood here (stub 1 036 bytes used, image 4 848) is gone with the clock.

### The final run (one invocation on the final tree, `VR_PRE_WEATHER_SET` set, at most 3 MAME processes) — SUPERSEDED (the clock build)

`tests/test_weather_carrier.py tests/test_weather_rain.py tests/test_weather_screen.py tests/test_weather_dry.py
tests/test_frame_rate.py tests/test_cli.py tests/test_directory.py tests/test_v60asm.py`: `1 failed, 315 passed in 4054.79s
(1:07:34)`, no `MameKilledWarning`.
- The screens' passes did not move: COURSE DIRECTION 14.74 ms (converted) / 18.88 ms (original), COURSE WEATHER 18.83 ms, as stage
  1's run (`weather_rate_summary.txt`); no stale list.
- DRY with the screens on is main's race pass for pass on all ten courses and three reverse races (pressed and by countdown);
  `weather=False` is main's set member for member.
- The rate tests (DRY on the weather set): no stale list in any of the 27 runs; the attract's busiest pass outside its scene loads
  17.986 ms (main's 17.982 ms, stage 0).
- **The failure: `test_the_worst_known_frames_hold_the_arcade_rate[big_forest_line4]`**, the margin under the budget 709 against
  stage 0's floor 716 (the game's need 9 791; 9 704 before). Not the game's drawing: Big Forest line 4, DRY, 300 s on the session's
  battery RAM, the rate test's own environment (`out/p80/s2/scripts/line4_replay.py`, scratch): the switch-off set with the
  autopilot needs 9 704; the weather set with the autopilot 9 791, its race parting from the switch-off set's at pass 1 550 of
  8 492; the weather set fed the switch-off set's recorded inputs (input_tape.lua) needs 9 704 with all 8 492 passes identical.
  The autopilot steers from samples grouped by MAME's frame end, and the switch test's 2 us a pass moved a sample (stage 0's
  finding with the boot's first-boot work, again). The floor is stage 0's and its re-baseline is the session lead's call: left as
  it is (follow-ups).

### TDD evidence (the first build's, with the clock and the 17.4 ms cap of then)

- `tests/test_v60asm.py`'s new forms: RED 15 failed, 62 passed (the forms unknown); GREEN 77 passed.
- The two new files at the commit before the carrier and the rain (a scratch export of HEAD with the test files): collection
  errors (`cannot import name 'carrier'`); GREEN after (the static tests 27 passed with stage 1's layout tests and
  `test_weather_dry`'s static gates). The static parts were written before their tests, the MAME tests before their runs.
- The MAME tests, on a scratch copy of f57b018 with three planted faults: the time guard at 19.2 ms (`test_rain_holds_the_rate`
  [big_forest] failed: 21 passes over 17.4 ms, 17.52 the highest); the stub's DRY path always taking the wet branch
  (`test_dry_runs_no_storm_code` failed: the switch written from 0xfff1f8 at every scenery call); the rain's release dropped
  (`test_a_rain_race_ends_clean` failed: the colour RAM still the overcast table after the release).
- Two failures of the first MAME session were the tests' own (fixed): the DRY runs had no race log (no `start`), and the records
  bound was the game's (its own last list can end past 10 500): now "the rain never takes the count over the budget".

### Not verified

- A human drive of this build (Pascal drove the prototypes); real hardware (the vblank count and the string moves' cost as MAME
  emulates them: MAME charges a string move almost nothing, so the load and the release would take longer on the board).
- Linked play (the switch tests 0x40dc8c; never run); the operator's fixed course (stage 1 tested the byte 0 there).
- The race ending during a grade fade-in (the fade is over in 32 passes of the countdown; the release copies the boot's table
  whatever the rows made, checked in the code, not in a run).
- Rain inside tunnels and under the pits roof (stage 3).

### Pre-review round (19 Nov, the session lead's rulings)

- **Line 4's floor** (C1): 400 (fails above 10 100): its need follows the autopilot's line, which moves with any timing change
  (9 771, 9 886, 9 704, 9 791 on identical games; 10 302 on a RAIN race's line); the 716 of stage 0 was tighter than that spread.
- **The storm does not change the game** (C1b, `test_rain_does_not_change_the_game`, standing): a DRY race's autopilot inputs
  replayed in RAIN on the same set. Big Forest line 4 (300 s, the session battery RAM): all 7 827 passes from the load identical,
  the game's need 9 791 in both, the game's own records equal on all 7 822 visible rain passes. Metropolis (150 s): 3 512 passes
  identical, need 6 464 in both, records equal on 3 508. So the 10 302 of the RAIN rate run was the autopilot's line, not the storm.
  Stage 5 leaves its wet handling out of that test's RAIN build through `GAME_CHANGING_MODULES` in `tests/test_weather_rain.py`.
- **The clock fails a robustness test** (C3a): entered from a RAIN race, the TEST menu keeps SBR at the RAM vector copy; its
  MEMORY TEST (pc 0xfc78ed, interrupts off) writes patterns over 0x500000.., the copy included, and the next interrupt vectors
  through them: MAME stops, `Unhandled OpCode found : bc35 at 02500007`. On main's set the same inputs run the memory test to the
  run's end. Also found: the boot leaves the interval timer running with period 1 (0xfe005b); the release writes 0. Not fixed:
  for the session lead (the fallback, the prototype's vblank-count guard with the cap at 17.6 ms, or another way).

### Fallback round (19 Nov, the session lead's ruling: "the storm must never move the interrupt table")

**What was tried and removed (do not rebuild it).** To hold the first 17.4 ms cap the first build swapped SBR to a RAM copy of the
boot ROM's vector table while the storm was loaded; its vblank vector restarted the board's interval timer (0xe00008), whose count
(0xe0000c) then gave the time since the vblank. Entered from a RAIN race, the test menu keeps SBR as it finds it; its MEMORY TEST
(pc 0xfc78ed, interrupts off) writes patterns over 0x500000..0x53ffff, the RAM table included, and the next interrupt vectored
through them: MAME stopped (`Unhandled OpCode found : bc35 at 02500007`, frame about 4 940); main's set, the same inputs, ran on.
Removed: no SBR change, no RAM vector table, no write to the interval timer (it stays as the boot leaves it: period 1, written at
0xfe005b). Nothing of the storm touches the interrupts.

**The guard as built.** The prototype's: late once the game's vblank count 0x500501 has moved (the game writes 0 there at its
wait's exit, 0xfe1406, where the pass begins; its vblank handler counts it up 17.38 ms in). It says only "already late", so:
- the start-up placement takes a fixed quota, 20 clusters a start pass (`rain.START_QUOTA`): three start passes on every course,
  11.2-14.9 ms (the heaviest Big Forest's first, 14.90 ms);
- the grade copies 3 rows a pass (`rain.GRADE_ROWS`): the prototype made one row a pass always and up to 8 while no vblank had come,
  which at the pit box faded the grade in over about 34 passes ("~1.2 s", spike 48's notes); 3 rows a pass is 32 passes;
- the guard is tested before every unit: each cluster, each relaunch, each landing test, each splash spawn, each splash's transform
  and its drawing, each grade row. The longest gap between two tests measured 178 us (Big Forest, 90 s), but every long gap holds
  the game's own vblank handler, which runs inside whatever unit it lands in (two tests of idle splashes, a few instructions apart,
  measured 147 us); the rule for stages 3-6: no unit above 0.5 ms (`carrier.UNIT_MAX_US`; 0.2 ms from the R round below).

**The cap (17.6 ms) is not held on 3 passes** (the session lead's instruction: report before changing how the rain looks). RAIN on
every course and direction, 150 s (`out/p80/s2/fb1`):

| course | dir | busiest ms (frame) | F0 ms | start passes ms | first rain frame ms | stale | records peak / game's need | clusters / splashes median | late passes | budget trims cl/sp | late trims cl/sp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Big Forest | nor | **17.602** (1943) | 11.89 | 14.90 14.35 14.24 | 15.73 | [] | 10500 / 9504 | 60 / 9 | 18 | 306/70 | 6/106 |
| Big Forest | rev | 16.75 (2691) | 11.27 | 12.24 12.36 12.32 | 13.84 | [] | 10500 / 9708 | 60 / 9 | 0 | 629/1258 | 0/0 |
| Bay Bridge | nor | 17.57 (6337) | 11.91 | 12.85 13.01 12.95 | 14.47 | [] | 9414 / 6922 | 60 / 14 | 10 | 0/0 | 0/31 |
| Bay Bridge | rev | 17.57 (2371) | 12.41 | 13.38 13.52 13.47 | 14.99 | [] | 9878 / 7415 | 60 / 9 | 23 | 0/0 | 0/36 |
| Acropolis | nor | 17.47 (1983) | 13.64 | 14.33 14.48 14.44 | 16.35 | [] | 10082 / 7688 | 60 / 10 | 10 | 0/0 | 0/20 |
| Acropolis | rev | 17.48 (1951) | 13.59 | 14.20 14.34 14.28 | 16.20 | [] | 9851 / 7548 | 60 / 10 | 2 | 0/0 | 0/5 |
| Alpine | nor | 15.84 (1959) | 11.11 | 12.15 11.62 11.55 | 12.94 | [] | 6132 / 4078 | 60 / 9 | 0 | 0/0 | 0/0 |
| Alpine | rev | 16.02 (1959) | 11.33 | 12.38 12.49 12.45 | 13.94 | [] | 6522 / 4586 | 60 / 10 | 0 | 0/0 | 0/0 |
| Amazon Falls | nor | 15.49 (2525) | 10.34 | 11.40 11.53 11.50 | 13.01 | [] | 6711 / 4522 | 60 / 9 | 0 | 0/0 | 0/0 |
| Amazon Falls | rev | 15.81 (2525) | 10.41 | 11.36 11.49 11.44 | 12.97 | [] | 7283 / 5247 | 60 / 9 | 0 | 0/0 | 0/0 |
| Diablo Canyon | nor | 16.34 (1887) | 12.46 | 13.13 13.28 13.20 | 15.13 | [] | 7718 / 5711 | 60 / 9 | 0 | 0/0 | 0/0 |
| Diablo Canyon | rev | 16.86 (1887) | 12.92 | 13.66 13.80 13.74 | 15.65 | [] | 7932 / 5960 | 60 / 10 | 0 | 0/0 | 0/0 |
| Metropolis | nor | 16.62 (1927) | 12.75 | 13.39 13.51 13.47 | 15.32 | [] | 8598 / 6464 | 60 / 10 | 0 | 0/0 | 0/0 |
| Metropolis | rev | 16.67 (7427) | 12.59 | 13.27 13.40 13.36 | 15.28 | [] | 7233 / 5275 | 60 / 9 | 0 | 0/0 | 0/0 |
| Pacific Coast | nor | 16.46 (2479) | 10.45 | 11.51 11.64 11.60 | 13.11 | [] | 7423 / 5273 | 60 / 10 | 0 | 0/0 | 0/0 |
| Pacific Coast | rev | **17.633** (2191) | 11.18 | 12.11 12.23 12.17 | 13.63 | [] | 6713 / 4738 | 60 / 10 | 1 | 0/0 | 0/31 |
| Surfers Oval | nor | 15.88 (2631) | 10.11 | 11.19 11.32 11.27 | 12.81 | [] | 6159 / 4026 | 60 / 9 | 0 | 0/0 | 0/0 |
| Surfers Oval | rev | 14.98 (2345) | 10.25 | 11.19 11.33 11.30 | 12.79 | [] | 6279 / 4030 | 60 / 8 | 0 | 0/0 | 0/0 |
| Surfers Road | nor | 16.31 (2525) | 10.13 | 11.24 11.36 11.34 | 12.86 | [] | 7256 / 4910 | 60 / 9 | 0 | 0/0 | 0/0 |
| Surfers Road | rev | 15.55 (2729) | 10.33 | 11.28 11.44 11.37 | 12.92 | [] | 7670 / 5499 | 60 / 9 | 0 | 0/0 | 0/0 |

Big Forest line 4 in RAIN (150 s): busiest **17.619 ms**. No stale display list anywhere (the deadline is 18.9 ms). Every other
pass of every run is at most 17.57 ms. The make-up of the busiest passes (a timing logger on Big Forest and Bay Bridge reverse,
scratch `out/p80/s2/scripts/units.lua`): the game's own work up to the scenery call about 13.0-13.7 ms; the scenery and the rain to
the vblank; the game's vblank handler then moves 0x500501 17.383 ms into the pass on most passes, but on some its work before the
increment is longer and the count moves at 17.486 ms (0.1 ms late); the storm's next test sees it, the unit in flight ends (up to
about 0.06 ms of the storm's own work, the rest of each long gap being the handler), and the pass's tail is 31 us (the routines'
returns, the game's list submission and loop). So a pass the guard stops ends between 17.42 and about 17.65 ms, and the late part
is the game's handler, which no shorter unit removes. Holding 17.6 on every pass needs one of: the cap raised (17.7 ms leaves 1.2
ms to the deadline), the rain stopped before the vblank by a fixed budget (less rain on the heavy passes: a change of the look),
or another clock (excluded).

**The final run of the fallback round** (7def283; all targeted files and test_v60asm in one invocation, `VR_PRE_WEATHER_SET` set):
`3 failed, 320 passed in 4060.87s (1:07:40)`, no MameKilledWarning. The three failures are the three passes over 17.6 ms above
(`test_rain_holds_the_rate[big_forest]`, `[pacific_coast_reverse]`, `test_only_rain_is_trimmed`); everything else passes: the new
robustness tests (the test menu and its memory test from a RAIN race and the reboot identical to main's, the test switch after a
RAIN race, a soft reset during and after one, three games RAIN / DRY / RAIN), the storm not changing the game, DRY pass for pass,
`weather=False` member for member, the screens' passes unchanged (14.74 / 18.88 / 18.83 ms), the rate tests with line 4's floor at
400 (its need 9 791), the attract (17.986 ms outside its loads, no stale list).

### R round (19 Nov, the session lead's ruling: "the cap follows from the mechanism")

- **The cap is the guard's bound: 17.8 ms** (`RAIN_BUSY_MAX_MS`; 1.1 ms under the 18.9 ms deadline; the prototype Pascal drove ran
  passes of 17.84-18.06 ms without a stale list). The derivation, from the timing logger (three heavy courses, 60 s each): the game's
  vblank handler moved the count 0x500501 at 17.383-17.387 ms into the pass on 48 of the 49 passes it moved in, at 17.486 ms on one
  (Bay Bridge reverse); then the storm's unit in flight, at most 0.2 ms by the rule below; then the pass's tail, 31 us: 17.49 + 0.20
  + 0.03 = 17.72 ms, rounded up. Worst pass measured: 17.633 ms (Pacific Coast reverse).
- **The rule for stages 3-6**: no unit of storm work longer than 0.2 ms between two guard tests (`carrier.UNIT_MAX_US`), the guard
  tested before every unit. The rain's longest today: 178 us between the cluster loop's test and the cluster's first landing test (a
  cluster's motion, its wraps and its scale; measured with the game's vblank handler inside when it lands there).
- **The mechanism tested**: `storm_log.lua` writes, for a pass in which the count moved during the work, the time from the move to
  the pass's end (A lines); on every pass the guard stopped it stays under 300 us (`POST_MOVE_MAX_US`, tests/test_weather_rain.py:
  the rate test on all 20 races and Big Forest line 4; fix round 1 makes it 231 us on every pass of the storm's). The timing
  logger's 60-s run gave 182.5 us (Big Forest); the final tree's runs below 197 us. A later stage's long unit shows there even on a
  run whose worst pass stays under the cap.
- **Evidence on the final tree** (4c3edb3): `tests/test_weather_rain.py tests/test_weather_carrier.py tests/test_frame_rate.py` in one
  invocation: `121 passed in 1817.19s (0:30:17)`, no MameKilledWarning. Guard trips per race (passes the guard stopped): 0 on the
  light courses, up to 23 (Bay Bridge reverse); the longest from the count's move to the pass's end 197 us (Pacific Coast reverse,
  its 17.633-ms pass), 185 us (Big Forest). The other targeted files' evidence is 7def283's all-files run (320 passed; the 3 failures
  were the passes over the 17.6 ms cap of then); nothing they exercise changed after it.

### Fix round 1 (19 Nov, the review of 4ccfed8..9dc2057 and the session lead's rulings)

**What shows between the last rain mode and the release (F3), established first.** The same race RAIN and DRY on the weather set,
the same inputs (Big Forest ended by time over 200 frames after its start, a coin at 2100 and START at 2150 in the results),
snapshots at every frame 2380-2419 and every 8th to 4292, the colour RAM, the whole palette RAM and the tile maps dumped:
- the modes, identical in both: the results 0x1c (the rain falling behind them) to 2387, 0x1d at 2388 (two frames: it shows the
  last rain picture), the attract's opening 0x2 from 2390 (three frames of a blue screen, then the sky), 0x3 at 2394, the course
  selection 0x0a / 0x0f / 0x10 from 2396, the direction screen; the release at the pass ending 2393, the fourth frame of 0x2;
- every snapshot from 2389 to 4292 equal pixel for pixel (165 732 pixels differ at 2380-2388: the rain);
- the palette RAM and the tile maps equal from 2389 (the game loads the attract's palette over the grey sky at 0x2's first frame);
  the colour RAM holds the grade (5 357 of its 6 144 halfwords differ) through 2392 and equals DRY's from the release on;
- the stale passes the same (2395, 2401, 2403: the attract's own scene loads); every pass's V60 time equal within 50 us but the
  release pass's, 45 024 us against 44 668 (+356 us: the release, on the attract's opening scene load, two vblanks and more).
A race finished (race_end.lua's lap): RAIN asks no name (stage 1), so its results go 0x1d -> 0x2 at 7797 where DRY's go to the name
entry; RAIN's frames from 0x2 against the DRY attract's opening above, aligned on the mode change: 6 frames equal pixel for pixel,
then 222-249 pixels apart, the attract demo car one pixel off (its place, not a colour). A coin and START during the race (3000,
3050): the same flow, released at 7801 in 0x2. So nothing drawn shows the storm's colours where the design says dry: no defect,
the built set unchanged; pinned by `tests/test_weather_carrier.py::test_nothing_of_the_storm_shows_after_its_modes`. The margin is
the game's flow, not a delay of ours: with a release that leaves the grade (a planted fault) the selection screens differ from 2395
on (182 895 pixels), so the colour RAM does reach them; the release at the attract's opening comes two frames before.

**The reload path (F6) cannot be run as ruled.** The stub releases and loads again when a RAIN race on another menu entry follows
without a release. In the game's flow that never happens: every way from a RAIN race to the next game passes 0x1d and the attract's
opening, whose scenery call releases (above: with the coin and START in the results, and during the race). A RAIN-then-RAIN chain
with a coin "before the attract's first race scene" releases at the attract's opening like the others, then loads anew for course
B: what `test_a_second_game_starts_clean` and `test_three_games_rain_dry_rain` already run. Not worked around (no forced state in
a test); reported. The session lead's ruling: the branch is kept as defensive code, documented as not reached, and a
forced-state test (the load key poked) comes at the join (follow-ups).

**The units with no guard test before them (F4)**, measured with a timing logger (scratch `out/p80/s2/scripts/f4units.lua`; Big
Forest, 320 sky colours, and Bay Bridge, 512, the worst; RAIN ended by time over): from the scenery routine's return to the first
guard test 47.5-47.6 us on a rain pass, 50.0-50.1 us on a start pass, 51.5 us on the first visible pass (its sky copy included);
the load (F0) 40.0 us; the release 349.0 us on both (the boot's table in one copy; the sky left, the game having replaced it). The
release runs on the attract's opening scene load only (above), so it is allowed as one unit, bounded by `carrier.RELEASE_US_MAX`
400 us and named in the contract; the end, time-over, second-game and chain tests assert each first visible pass within the cap and
not stale, and each release pass the attract's opening scene load, not stale.

**The bound after the count's move (F5).** `post_move` (tests/test_weather_rain.py) now takes every pass at whose end the storm is
live (the load, the starts, the shows) in which the vblank count moved before the pass's work ended, whichever guard stopped it
(the grade's included, and passes no guard stopped), and a pass the rain counted late without its A line is a failure; the bound is
`carrier.UNIT_MAX_US + carrier.TAIL_US`, 231 us. A planted fault (a test-only build variant, `rain.module(..., fault_spin=240)`: a
two-instruction loop of about 0.29 ms in every splash's transform unit; `VR_STORM_FAULT_SPIN=240`) makes
`test_rain_holds_the_rate[big_forest]` fail: 165 passes over the bound, the longest 424 us (frame 1943). Without the fault, Big Forest
in RAIN 150 s measured at most 182 us on the 19 passes the count moved in (Alpine: none).

**The hook sites (F1).** A module declares hook sites (`Module.sites`, a function of the settled Layout: block name, original
bytes, new bytes): each a "boot site" or "program site" block of its own in the layout table, its bytes checked against the
original before anything is written (PatchError naming the site); its stub an erased block of its own whose bytes may be made from
the Layout too (`Module.rom` as a function), calling the module's RAM routines (`Module.entries`, exported labels); `build` takes
the layout table (`table`, weather/layout.py's by default, checked); `install(rs, converted)` hands `converted` to every module
factory (`carrier.REGISTRY`). The worked example is `tests/test_weather_carrier.py`'s dummy module: the race scene's call before the
scenery call (0xfee13e, `jsr FF7C1E[PC]`) becomes `jsr 0xfff700`, a stub that tests the weather byte, then SWITCH, calls the
module's routine `hit` (it counts in a module cell) and jumps to 0xff7c1e; refused when the site's bytes are not the original, its
block not in the table or another module's, or the new bytes of another length.

**Documents (F2).** The stage plan rewritten as built (one dated section on the removed clock); the clock build's space table
replaced by the generated one above; the sections of the first build marked; `ldpr` dropped from the assembler (M1); the remaining
hits of `clock`, `SBR`, `timer`, `17.4`, `17.6`, `182.5` in this stage's files are the dated records of the removed clock, the
game's own race clock and countdown timers, the negative checks (SBR stays the boot's, no timer write, no `ldpr`), the prototype's
measured 17.4-18.0 ms passes and the cap's derivation.

**The smaller fixes.** M2: `Layout.cell` and `data_at` raise PatchError naming an unknown name. M3: a block reaching past its ROM
region's end is refused by `layout.rom_bytes` / `erased` and by the carrier's writer. M4: a copy whose source is not inside the bank
window, or whose bank the set has not, is refused naming it. M5: the report's `data_end` is the data's end (0x530810). M6:
`race_end.lua` refuses "128:01" (the old pattern took it for RAIN; checked in MAME: the new pattern stops the script, the old ran).
M7: the relaunch loop's comment states the prototype's behaviour and the worst count seen, 2 placements of a cluster in one pass
(Big Forest and Alpine, 150 s each: of about 3 650 cluster passes with a placement, 24 had a second, none a third).

**The RAIN race matrix's subset (the session lead's rider R-S, for stages 3-6 built in parallel).** `test_rain_holds_the_rate` and
`test_the_start_up_is_spread` (the only tests parametrised over the twenty RAIN races) read `VR_RAIN_SUBSET`: unset (the default)
all twenty races, exactly as before: what the join and stage 7 run; `heavy6` the six with the highest busiest pass of the final
per-course table (Pacific Coast reverse 17.63 ms, Big Forest 17.60, Bay Bridge 17.57, Bay Bridge reverse 17.57, Acropolis reverse
17.48, Acropolis 17.47) and Metropolis normal (16.62; added for its two tunnels): seven races; any other value a comma-separated list
of race ids, exactly those (a stage adds the courses its feature needs). The races outside the subset are skipped with a reason
naming the variable and make no MAME run; an unknown id fails the collection. `test_the_rain_subset_selection` checks the logic
(no MAME). The carrier's contract now also states the routines' order (start and frame in the registry's order, release in
reverse; a module's place is its factory's place in `carrier.REGISTRY`) and how a module reads a cell another owns by name
(`lay.cell(owner, name)`; the owner absent, PatchError naming the cell; a stand-in module of the owner's name satisfies it:
`test_a_module_reads_another_modules_cell_by_name`).

**TDD evidence and the final runs (fix round 1).** RED on 9dc2057's code (a scratch worktree with the new test files): the hook site
(no `entries`), the converted courses (no `REGISTRY`), the strict lookups (KeyError), the block past its region and the copy
outside the window (did not raise), the data end (the last start), the room table (no `room`), the hook site's MAME test (its set
could not be built); planted faults on the final code: the 0.29 ms splash unit (165 passes over 231 us, the longest 424) and the
release leaving the grade (the selections 182 895 pixels apart from 2395); race_end.lua's "128:01" taken by 9dc2057's script. The
built set (weather on) byte-identical to 9dc2057's, so the earlier runs of the other targeted files stand. `tests/test_weather_carrier.py
tests/test_weather_rain.py tests/test_v60asm.py` on 118268d: `1 failed, 152 passed in 1386.57s (0:23:06)`, no MameKilledWarning; the
failure the hook-site test's own threshold (it asked for 1 500 live passes of a 70-s run that has 1 210; its counter stepped by one
on every one), corrected, and the harness's double build of the probe set locked; rerun with `VR_RAIN_SUBSET=heavy6`: `1 passed, 2
skipped` (the two Alpine cases skipped naming the variable). The longest time from the count's move to a pass's end on the twenty
races: 197 us (Pacific Coast reverse), 185 (Big Forest).

## Stage 3: cover (19 Nov 2026, branch `phase80-cover`, one of the four parallel tracks)

Plan: `docs/superpowers/plans/2026-11-18-weather-stage-3-cover.md`. Code: `weather/cover.py`, `weather/cover_geom.py`, the rain's
per-cluster call (`weather/rain.py`), `tune.CoverTune`, a `cover objects` block (`weather/layout.py`); tests
`tests/test_weather_cover.py`; harness `vrtools/mame/lua/cover_look.lua` and the cover's line of `storm_log.lua`.

### What Pascal said (exactly) and what is not theirs

"i think for the visual, we also need to stop the rain inside the tunnels, and show it again toward the exit when we see the tunnel
exit. can you look into this? think extra hard and ask questions"; dry road inside tunnels: "A"; "the long tunnel in metropolis is
perfect"; of the roof by the pits: "i felt like it was drawing water outside of the tunnel exit while i was still inside the tunnel,
can you check? think extra hard", "it looks like rain is missing on the right side of the tunnel from inside.", "for short tunnel,
rain feels like it s not using the full section of the end tunnel think extra hard", then "short tunnel is good". Not theirs:
short unflagged roofs keep their rain (the session lead's proposal, not objected); Alpine's and Bay Bridge's covers (the session
lead's extension in spike 70, judged from stills only); lightning under cover (the lightning track's).

### The port

- The tables are marched from the set's faces at build time and equal the prototype's byte for byte (pointers made offsets): every
  float of the long tunnel's 15 boxes, Alpine's 14 and Bay Bridge's 6 differs by 0 from spike 57/70's pickles; 0.3-0.5 s a course.
  The pits roof's road and lane are spike 61-68's measured stretches, checked against the set's faces at build time (its underside,
  its ends, its walls mid-roof); the stretches are checked against the set's tunnel flags.
- The single drops and their table are spike 68's bytes.
- FINDING ROOF_U0: in the approved prototype every pits-roof curtain cluster lies on the end opening's plane: spike 68's code meant
  u = -u0 (k - 1) along the sight line, but the generator call before it overwrites R0 (-u0) with the generator's integer, read by
  the float multiply as a denormal (about 1e-39). Measured on out/p68tunnels (a dump of its curtain cells under the roof: u from
  4e-42 to 6e-39 on every cluster). The port places them at u = 0, the look Pascal approved; the intended depth was never seen.
- A bug of the port's own found by the gate (fixed in 65885bf): the drop-by-drop routine used R14, which carries the drops' ground
  back to the rain.
- Differences by design (plan C6): the cover's work cut into guarded units; the splashes sheared onto the car's ground always; the
  rain's start passes do not consult the cover.

### Results (headless MAME 0.289; `tests/test_weather_cover.py` on the session's set and a twin that never draws the curtain)

Per flagged stretch and direction (the rate tests' line; Bay Bridge in reverse on its centreline from the session battery RAM, past
the reverse fork, which the prototype's autopilot never passed): the camera under cover in every stretch passed (Metropolis's pits
roof on the road and the long tunnel, Alpine's tunnel, Bay Bridge's tunnel, both ways); no fault on any pass (under_cover exactly
modes 2-3; in mode 2 nothing drawn and no splash; in mode 3 only the curtain; no splash under the roof's curtain).

| pass | modes 0/1/2/3 (passes) | leak (frames judged, px) | busiest | the cover late |
|---|---|---|---|---|
| Metropolis | 2060/277/168/234 | 468, 0 | 17.64 ms | 0 |
| Metropolis reverse | 3040/396/345/396 | 578, 659 (37 at most a frame: the long tunnel's exit, drops over its roof's edge) | 17.61 | 0 |
| Alpine | 1742/113/102/63 | 126, 1 493 (79 at most: drops over the left wall at the opening's edge) | 17.53 | 0 |
| Alpine reverse | 3873/68/115/121 | 242, 834 (27) | 17.54 | 0 |
| Bay Bridge | 1907/61/0/52 | 104, 0 | 17.67 | 0 |
| Bay Bridge reverse | 3908/155/0/115 | 128, 170 (29: drops over the roof's edge) | 17.66 | 0 |

The leaks are the prototype's own at four exits (the curtain of the marched stretches relies on the renderer's sort, which the
converted courses' farthest-corner quads defeat near the exit, as spike 68 found under the pits roof; the prototype shows the same
drops at Alpine's exit, out/p80c/look), with one exception found later: Bay Bridge normal's exit, seen in the build on one seed of
eight (123 px, 32 in the worst frame) and not on the prototype on the same eight (fix round 2, R2-5; not shown to be shared):
reported, not changed; their tests were strict xfails (superseded: the pre-review round, which also finds this
build past the prototype on Alpine and Metropolis reverse). The measure: rain pixels = set != twin in the rain's own colours,
outside the HUD and the player's car; the pits roof against its measured end opening (spike 68's), a marched stretch against the
picture of its own interior faces (roof, walls, road: in front of everything beyond its mouths); the picture's camera is the one of
f-2..f+2 that fits (the camera RAM is up to two frames off; the camera jumps up to 26 px a logic frame on the road's bumps).
Negative control: the stage-2 set (no cover) against the twin: 90 941 px.

The pits roof from spike 68's six spots (scripted stops: Pascal's drives are not in the repository; 600 frames each):

| spot | camera | coverage | leak |
|---|---|---|---|
| s12w1 mid-roof | -112.1, -6.3, 298.6 | 100.0 % | 0 |
| s12w2 cockpit | -106.3, -6.4, 324.9 | 100.0 % | 0 |
| s3 near the exit | -104.8, -5.0, 335.4 | 88.9 % (strict xfail: the prototype at the same stop 91.7 %) | 0 |
| s4 pit stop | the pit camera | 100.0 % | 0 |
| s5 reverse road | -116.8, -8.2, 240.5 | 99.4 % (the prototype at the same stop: 100 %) | 0 |
| s7 reverse pit stop | the pit camera | 100.0 % | 0 |

Over 300 frames s5 gave 94.5 % on the prototype and 82.3 % on the port (a few slow clusters cover a near opening): the spots are
pictured 600 frames. s3 sees only 36 cells of the opening wholly on screen, and its lowest row (the drops end 0.3 above the road)
is rarely reached in both.

- Four views (VR1-VR4 before the roof): VR1 modes 2-3 under the roof, VR2 3, VR3 1-3, VR4 (the high view, the camera above the
  roof) only 1: outside, the rain drawn on the roof (60 clusters); no fault, the rate gates held.
- Metropolis pit stops under the roof: normal 2420-3121 (351 passes, all with the camera under the roof: under cover), reverse
  5180-5875 on the pit tests' reverse path (348 passes, 347 with the camera under the roof): the first reverse stop under this
  roof in any build; the pit camera leaves the roof at the stop's first pass.
- Rate gates on every cover run: 0 stale lists (Bay Bridge reverse on a battery-RAM boot: one stale list at the race load + 7, the
  game's own, also in a DRY race of the stage-2 set booted the same way; the pre-review round: main's released set too), busiest
  17.67 ms, overrun still, render 28-29, the longest time from the vblank count's move to a storm pass's end 208 us (Bay Bridge, in
  its tunnel; bound 231).
- The RAIN matrix (heavy6 and Metropolis, Alpine both ways): every race holds the gates (busiest 17.67 ms, the cover's units under
  0.2 ms); `test_rain_does_not_change_the_game` (Big Forest line 4, Metropolis: every pass identical); the DRY identity on Big Forest,
  Alpine, Metropolis (1 213 passes each, no difference); DRY runs no storm code (the switch test's mean +2.13 us); the screens'
  rate test: 18.88 / 18.83 ms (unchanged), the attract's busiest 17.71 ms.

### Space (against stage 2's room)

| space | block | stage 2 | stage 3 | added |
|---|---|---|---|---|
| boot | storm stub (0x500) | 940 | 1 100 | 160 (a copy record of the cover table per entry) |
| bank 3 | storm image (0x5000) | 4 880 | 11 716 | 6 836 (the cover's code 5 850, its drop table 640, the rain's call and entries) |
| bank 3 | storm course data | 9 664 of 0x2900 | 12 032 of 0x3300 (grown) | 2 368 (the tables: Metropolis 1 128, Alpine 712, Bay Bridge 392, 4 elsewhere) |
| polygon | cover objects 0xfe9fe4 | - | 12 160 | 12 160 (spike 70's place) |
| program, bank 0/1/2, sites | | | | 0 |
| RAM | cells / image / data | to 0x520b80 / 4 880 / 26 640 | to 0x521020 / 11 716 / 27 776 | 1 184 / 6 836 / 1 136 |

### Not verified

Pascal has not driven this build. The six spots are scripted stops, not Pascal's. The leaks named above stay (the owner's call).
Linked play excluded by code. Real hardware untried.

### Pre-review round (19 Nov, the session lead's rulings C1, C2, C3, C5)

The prototype measured the same way as the build: spike 70's joined set rebuilt with the handling and the sound off (the game's own
handling, so the car's path on the same inputs is this build's) and its twin (the curtain never drawn), from the read-only p70
worktree with its emitter patched in memory (`out/p80c/tools/protobuild.py`); the cover test's lines, seconds and boots; the
test's own `leak` and `coverage` (`out/p80c/runs/pt_*`).

- **C5, main's set (the released v0.3 game code, out/p35play2), DRY, Bay Bridge in reverse on the test's line**: on a battery-RAM
  boot (its own 30-s attract boot, and the cover session's battery RAM) one stale display list at the race load + 7 (frames 1603
  and 1610), exactly as this build and the stage-2 set; on an empty battery its one stale pass is the pass right after the load
  (load + 5, after the long load pass at + 3), which the standard rule excuses. The list pointer shows why: after the load pass
  writes list 0x60, the next two passes both write 0x61 on the battery boot; on the empty one the load pass writes 0x61 and so does
  the pass right after it, then they alternate. So the
  released game, started on a battery RAM on Bay Bridge in reverse, shows one frozen picture for one render just after the race
  load, before the green: the game's own, not the storm's. The test now runs the released set to the load on the same inputs and
  battery RAM (`VR_RELEASED_SET`) and excuses a stale pass within 15 frames of the load only where that run is stale on the same
  pass (`stale_excused_by_released`, pinned by a unit test); the hard-coded frame is gone.
- **C1**: `cover.ROOF_U0 = 0.0` named and pinned (`test_the_pits_roof_curtain_lies_on_the_end_plane`); a deviation from the
  prototype's intent in docs/deviations.md.
- **C2, the exit leaks against the prototype's (leak px of the pass / the worst frame's px)**:

  | pass | this build | approved prototype | gate |
  |---|---|---|---|
  | Alpine | 1 493 / 79 | 495 / 55 | over |
  | Alpine reverse | 834 / 27 | 1 365 / 29 | holds |
  | Bay Bridge reverse | 170 / 29 | 541 / 74 (its tunnel at frames 4584 and 8146, this build's at 4930 and 8110) | holds |
  | Metropolis reverse (the long tunnel's exit) | 659 / 37 | 400 / 64 | over (the pass's total) |
  | every other pass | 0 | - | none |

  Not chance: Alpine run 150 s (two exits) gives this build 3 448 px and the prototype 542 (the second exit: 0 on the prototype,
  up to 96 px a frame on this build); with the storm's generator reseeded at frame 2000 in both, 5 778 against 1 144. The leaked
  drops are over the exit's LEFT wall, from about 30 frames before the exit, where the prototype's rain stops at the opening's
  edge (out/p80c/look/c2_leaks_worst_frames_build_left_prototype_right.png; out/p80c/tmp_c2_al_*.png). Ruled out by dumps of both
  machines' RAM at the same frames: the mouth's record and the curtain's frame in view space are identical in both at every frame;
  the curtain clusters' placements are uniform over the same bounds in both (89 and 88 placements in the 66 frames before it).
  The rain of stage 2 is not the prototype's rain (its clusters already differ before the tunnel with the same seed), so the
  machines cannot be compared cluster for cluster. NOT FOUND: why this build's curtain drops escape the renderer's sort at
  Alpine's left wall more often. The gate fails on Alpine and Metropolis reverse until it is.
- **C3, the spots by cells (reached / on screen)**: this build s12w1 600/600, s12w2 299/299, s3 32/36, s4 525/525, s5 326/328,
  s7 736/736. Only s3 has fewer than 50 cells: the prototype measured the same way reaches 34 of 36 (and leaks 3 308 px outside
  the opening there; this build 0). This build is two cells under it: the gate (one cell fewer allowed) fails at s3. (The earlier
  91.7 % was out/p68tunnels by a single-run method, 33 of 36.) The other five keep 95 % and leak 0.
- **The round's invocation** (`out/p80c/final4.sh`: every test of tests/test_weather_cover.py, one session, `VR_RELEASED_SET` set,
  two MAME processes): `3 failed, 35 passed in 1449.94s (0:24:09)`, no xfail left. The three failures are the ones above:
  `test_rain_only_through_the_exit_opening[alpine]` (1 493 / 79 against 495 / 55), `[metropolis_reverse]` (659 / 37 against
  400 / 64), `test_the_pits_roof_coverage_from_the_six_spots[s3]` (32 of 36 against 34). Bay Bridge reverse's rate test passed with
  the released set's run (load 1603, stale at 276 and 1610: the same pass as this build's). Every figure equals the dev runs'.

### Fix round 1 (19 Nov, the review of 690f7b5..4fe3bec and the session lead's rulings F1-F7, M1-M6)

- **F3, the game divergence: the cover draws only.** Two runs decide it (Alpine normal, 150 s, the storm generator poked at frame
  2000 as in the hunt's `sd_b_1234567`; `out/p80c/runs/f3_*`): (a) under the DRY run's replayed tape the poked set and the poked
  twin play the DRY game pass for pass to the end (4 178 passes, the pass-state logs byte-identical, each fed the whole tape);
  (b) on the autopilot (the hunt's diverging pair, reproduced exactly), the INPUTS differ first: frame 5730 (set wheel 23, pedal
  255; twin 18, 0), the game state two frames later (frame 5732, the player's x and z). It is the test autopilot's frame-end
  sampling, as on Big Forest line 4 in stages 0 and 2. The poked trajectory is now a test
  (`test_the_cover_does_not_change_the_game`), and every taped cover run is held to its DRY tape run pass for pass (`_same_game`).
- **F1, the scale cap.** `pd` and `win` use R12 as a temporary; the rain caps each cluster's scale with R12 for its landing whether
  drawn or not. Now GCAP_SIL after `jsr pd` and BIG at `s_hide`. The prototype draws the single drops at the same point (inside the
  cluster call, before the landing: spike 57's `s_drops`; PD57's docstring "after the landing" is stale) and had the same clobber;
  the order is kept. The register contract (formats §26) is checked from the emitted code (RED on 4fe3bec: R12 undefined at two
  `rsr` of `cluster`).
- **F4, the leak measure.** Triangles near the camera clipped at the near plane (no longer dropped); the picture's lag fitted once
  per run (1 or 2 on every run); the car's box left out only where the car is shown; coverage's stricter count reported (the
  middle half of a cell's box: s3 31-33 cells against 32-34). The negative control is a test (the rain alone on Alpine's tape).
  The clip exposes a few drops at Bay Bridge's exit in the normal direction too (57 px, worst 15, on one seed of three).
- **F5, the gates.** Every pass and spot s3 on the taped game on three generator trajectories (set at the race load). Leak
  px / worst frame per seed (0, 0x9e3779b9, 0x2468ace1), the measure run on the final code (`out/p80c/fr1c`; the earlier
  measure runs fr1a and fr1b agree to the pixel wherever the code between them did not change the pass):

  | pass | seed 0 | 0x9e3779b9 | 0x2468ace1 | gate |
  |---|---|---|---|---|
  | Metropolis | 0 | 0 | 0 | none |
  | Metropolis reverse | 388 / 28 | 246 / 15 | 900 / 56 | at most 1.5 x 900 / 56 |
  | Alpine | 1 490 / 84 | 168 / 14 | 139 / 8 | at most 1.5 x 1 490 / 84 |
  | Alpine reverse | 851 / 27 | 1 048 / 59 | 794 / 45 | at most 1.5 x 1 048 / 59 |
  | Bay Bridge | 0 | 0 | 57 / 15 | none: FAILS (the ruling's strict gate) |
  | Bay Bridge reverse | 12 / 3 | 12 / 3 | 40 / 6 | at most 1.5 x 40 / 6 |

  s3: cells 32, 34, 32 of 36 (the gate: at least 31); leak 0, 1 288, 2 250 px outside the opening: FAILS the ruling's "leak 0" on
  two seeds. The same seed on 4fe3bec's code: 36 of 36, 2 910 px (the F1 fix reduced it); the prototype on its own trajectory:
  34 of 36, 3 308 px. The prototype seeded the same on Alpine's tape (the re-pin rule's comparison; `out/p80c/runs/ps_*`): 520 / 64,
  0, 1 182 / 50 px (this build 1 490 / 84, 168 / 14, 139 / 8): the same degree, the trajectories differ (the two rains use the
  generator differently). Re-pin rule: in the test's docstring.
- **F2**: the spots apply stage 2's rate gates (every spot run passes them).
- **F6, the views.** In Alpine's, Bay Bridge's and Metropolis's tunnels the high view (VR4) puts the camera 14-23 units above the
  car, above the roof, and the game draws the roof from above (out/p80c/look/f6_high_view_in_the_tunnels.png); 4fe3bec's cover
  counted it under cover (non-ROOFED boxes ignored the height) and hid the rain there. A marched box now holds the camera only
  while it is less than the roof's height H above the player's car (the chase and cockpit views are 0.7-2.2 above it), the pits
  roof as before (below its end's top); mode 1 hides clusters only below the higher of the stretch's mouths' tops. A first form
  (the mouths' tops interpolated along the stretch) failed in Metropolis's long tunnel, whose road rises 30 units above the line
  between its mouths: rain drawn inside in the default view (the aborted invocation `out/p80c/fr1final_aborted_chord_roof.log`:
  modes 1 396 / 2 90 / 3 193 against 4fe3bec's 277 / 168 / 234; the approach check caught 6 rain objects inside). With the
  car-relative rule the default view's modes are exactly 4fe3bec's and the high view is never under cover, its rain drawn
  (f6_alpine_high_view_frame3009_before_left_fix_right.png). Tested in all three courses and four views.
- **M1** `under_cover` 1 on a late pass; **M2** `walk` written before the first guard (one test, RED then GREEN); **M4** the
  table records' fields named and the logger's indices passed by name (the cover's code bytes unchanged by the renaming, checked).
- **M3, the cover's cost where there is no cover.** A/B on the same tape, the storm with the cover against the rain alone, 3 511
  passes each: Big Forest +195 us a pass (median 200), Acropolis +194; the rain capped every cluster's scale with R12, which on a
  pass without the cover still held the frame's clamped ground value (G0V: harmless in the pictures checked, the scales equal in
  the records, but undefined). The cap now sits on the cover's path only (a test: R12 not live where the rain skips the cover):
  +135 us a pass (median 139) on both; the busiest pass unchanged (Big Forest 17.60 / 17.60 ms, Acropolis 17.48 / 17.47). What
  remains is the per-cluster test of the cover's mode and the cover's frame call. (The matrix's own trim and late counts are not
  comparable with stage 2's: those were autopilot runs on another trajectory.)
- **M5, the approach**, from the display records (rain_records.lua): on the final code 17 of 18 pass x seed runs show no rain
  object inside a stretch below its mouths' top while the camera approaches; Metropolis reverse, seed 0x2468ace1, shows one: a
  splash (world-fixed at (-117.9, -7.7, 313.1), two passes) on the road 26 units inside the pits roof, while the camera
  approaches its exit end from outside (frames 5221-5223; reproduced in dev with RAM dumps, `out/p80c/runs/ap_dbg`). Not traced
  to its cluster in this round; the likely cause: mode 1 hides a cluster only within MG = 1 unit of a box (the prototype's
  margin) while a cluster's drops spread up to about 4 units, so a cluster beside the roof can land a drop, and a splash, under
  it. Reported, not changed; the test fails there.
- **M6** planted faults (`under_cover` stuck at 0; the cover ignored), each caught by `cover_faults`, the second also by the
  approach check.
- **The built set against 4fe3bec's** (the quick build of each from out/p35play2): program ROM, polygons, coprocessor: identical;
  bank 3's storm image (data 0x3df4e2..0x3e230b) and the boot's copy record of its length (2 bytes at 0x3f33c): the cover's code
  5 850 -> 5 953 bytes (the cap, the late write, the height tests), the rain's 4 706 -> 4 737 (the cap's move); the image 11 852
  of 0x5000.
- **The one invocation on the final code** (`out/p80c/fr1final.sh`: every test of tests/test_weather_cover.py, the RAIN matrix on
  the subset, test_rain_does_not_change_the_game both cases with the cover in, the DRY identity on entries 0, 3, 6, the screens'
  rate test; log `out/p80c/fr1final.log`): `3 failed, 68 passed, 10 skipped in 2888.27s (0:48:08)` (the 10: races outside the
  subset). The three failures are the strict gates reported above: Bay Bridge normal's leak (57 px on one seed), the approach's
  splash under the pits roof (Metropolis reverse, one seed), s3's leak (1 288 and 2 250 px on two seeds). Every stage-2 gate
  passed: the matrix (busiest 17.68 ms, Bay Bridge both ways), the same game (Big Forest line 4: 7 827 passes; Metropolis: 3 512,
  the cover in), the three DRY cases, the screens. Two earlier invocations were superseded by code changes (kept:
  `fr1final_aborted_chord_roof.log`, F6's first form; `fr1final_before_m3.log`: 4 failed, the views test's own form, since fixed).

### Pins as ruled (19 Nov, the session lead's ruling on the three strict gates left failing)

Behaviour made visible by the stricter measure, pinned as known limitations at 1.5 times this build's own maximum over the three
seeds (re-pin rule below); every other pass, spot and approach keeps "none". The approved prototype shares the leaks at four exits
(Alpine both ways, Metropolis reverse, Bay Bridge reverse), spot s3 and the approach; Bay Bridge's exit (normal) is NOT shown to
be shared (fix round 2, R2-5: seen in the build on one seed of eight, not on the prototype on the same eight):
- Bay Bridge's exit (normal) joins the leaking passes: 0, 0, 57 / 15 px over the three seeds (fix round 2: 123 / 32 on the third).
  The measure's fix moved it there, not a change of the build: 4fe3bec's code on the same seed measured with the new measure
  leaks 123 px (worst 32).
- Spot s3's leak outside the opening: 0, 1 288, 2 250 px (the cell gate unchanged: 32, 34, 32 of 36); 4fe3bec's code 2 910 px on
  the second seed, the prototype 3 308 px on its own trajectory.
- The approach: Metropolis reverse 0, 0, 2 rain objects inside (one splash under the pits roof, frames 5221-5223); MG not changed
  (the follow-up for the owner). Note: the approach measure judges centres only; drops of clusters centred just outside a box can
  still fall inside it.

The table of the cover's known limitations is in docs/deviations.md (Cover); the owner's sheet with the new measure's worst frames:
out/p80c/look/known_limitations_fix_round_1.png. The re-run of the tests the pins touch (`out/p80c/pins.sh`: the leak, coverage
and approach tests on the three seeds): `18 passed, 34 deselected in 2273.54s (0:37:53)`.

### Fix round 2 (19 Nov, the re-review of 6df3c89: R2-1 to R2-5)

- **R2-1, the default view on the approach.** F6's rework had made a marched box hide a cluster only below its mouths' top, so on
  the approach the default view drew clusters centred above a tunnel's top inside its footprint, which the approved prototype
  (CL57: within MG of a box, any height) hid. Counted on 6df3c89's own runs (fr1final, objects inside a marched footprint at any
  height, three seeds): Metropolis 0; Metropolis reverse 540, 580, 488; Alpine 194, 298, 210; Alpine reverse 151, 180, 150; Bay
  Bridge 57, 114, 140; Bay Bridge reverse 177, 178, 204. Now the three low views hide exactly what the prototype hid (a marched
  box: any height within MG while the camera is less than LOW_VIEW_MAX = 10 above the car); the height rule applies to the high
  view only, and to the pits roof as before. The approach test checks any height in a marched footprint (objects in front of the
  camera; on the round's code 0 inside on every pass and seed but Metropolis reverse's third seed: the pinned splash, 2 objects).
- **R2-2, the high view and the near list.** The frame listed at most 6 near boxes in table order; up to 10 lie within reach of a
  camera 25 units off a road point (Alpine; Metropolis 8, Bay Bridge 6): NNEAR_MAX is 12, held by a geometry test. The view runs
  now log the display records; in the high view nothing may be drawn inside a tunnel below its roof. A dev run found 15 splash
  objects under the pits roof in Metropolis's high view: drops of clusters above the roof landed on the car's ground plane, carried
  forward under the roof; a cluster above a roof within a box now has no landing (it is hidden once it falls below the top).
  Behind the camera: a few clusters of the rain wander hundreds of units off (view z -6, x -450 on Metropolis reverse, seed
  0x2468ace1); they are not on screen (culled) and the approach measure now judges objects in front of the camera only.
- **R2-3** the remaining raw offsets named (the bytes identical, checked). **R2-4** the marched-box rule is a margin between the
  views, not H: VR1 0.5-1.2, VR2 0.7-2.2, VR3 3.4-6.3 (Bay Bridge 4.6-4.9 under H 5.0), VR4 14.3-23.3 above the car in the three
  tunnels; LOW_VIEW_MAX 10; the views test judges every pass.
- **R2-5, the prototype on the rows that had no direct evidence** (spike 70's set, handling and sound off, against its twin, the
  build's tapes, seeded at the build's race-load frame 1607; `out/p80c/runs/pb_*`, `pm_*`, `ps3_*`; its game identical to the
  tape's): **Bay Bridge normal: 0, 0, 0 px on the three seeds: the prototype does NOT leak there** (the build: 0, 0, 57 / 15 on
  fix round 1's code; 4fe3bec's 123 / 32 on the third seed). That row is not shown to be shared. Metropolis reverse: 240 / 24,
  596 / 61, 24 / 5 (the build 388 / 28, 246 / 15, 900 / 56 on fix round 1's code): shared. Spot s3: 3 308, 4 530, 1 344 px
  outside the opening (cells 34, 30, 34 of 36; the build 0, 1 288, 2 250, cells 32, 34, 32): shared.
- **The measures' fits, stated here as well as in the tests.** The leak measure fits the picture's camera lag once per run (the
  camera RAM at a frame's end is up to two frames off the picture; under a replayed tape that lag is a property of the run). The
  coverage measure at the pits roof's spots fits the camera per frame among f-2..f+2: at a spot the camera is held still, so the
  fit changes nothing there except under the pit camera, which pans and cuts (a frame whose candidates differ by a cut is left
  out). RE-PIN RULE: a pinned figure (OWN_LEAKS, OWN_SPOT_CELLS, OWN_SPOT_LEAK, OWN_APPROACH) may be re-pinned only with a named
  cause (a change that moves the passes' time or the generator's use: the join, a new module before the rain, a fix in the cover)
  and the prototype comparison, seeded the same, re-run and recorded beside the new figure.
- **Pins re-measured** on the round's code (`out/p80c/fr2a`; re-pin cause R2-1 and R2-2): Metropolis reverse 388 / 28, 594 / 61,
  902 / 56 (pinned 902 / 61); Bay Bridge normal 0, 0, 123 / 32 (pinned 123 / 32: now exactly 4fe3bec's figure on that seed); the
  others unchanged (Alpine 1 490 / 84 max, Alpine reverse 1 048 / 59, Bay Bridge reverse 40 / 6, s3 2 250 px and 32 cells, the
  approach 2 objects).
- **The built set against 6df3c89's** (quick builds): program, polygons, coprocessor identical; bank 3's storm image (0x3df4e2..
  0x3e2327) and two copy-record bytes in the boot (0x3f26c, 0x3f33c): the cover's code 5 953 -> 5 982 bytes, its cells 24 bytes
  longer (the near list's 6 more words), so the rain's cells and every absolute reference to them move by 0x18 (rain state
  0x5205b8); the image 11 880 of 0x5000.
- **The one invocation on the round's code** (`out/p80c/fr2final.sh`: every test of tests/test_weather_cover.py, the RAIN matrix on
  the subset, test_rain_does_not_change_the_game both cases with the cover in, the DRY identity on entries 0, 3, 6, the screens'
  rate test; log `out/p80c/fr2final.log`): `72 passed, 10 skipped in 2999.42s (0:49:59)` (the 10: races outside the subset).
- **R2-5, wider sample** (the session lead's ruling: the pin stands; measure more, no code changed). Bay Bridge normal's exit on
  eight seeds, both builds on the pass's DRY tape (55 s runs: the pass's mode-3 frames end at 2902; `out/p80c/tools/bb8.sh`, the
  test's leak measure `out/p80c/tools/bb8.py`, results `out/p80c/runs/bb8_result.txt`). The round's build is the one invocation's
  set and twin, seeded at the race load as the test does (its seed-0 run's game is the test's own, line for line, and its three
  old seeds give the test's figures); the prototype is spike 70's set and twin seeded at frame 1607. Leak px (worst frame):

  | seed | build | prototype |
  |---|---|---|
  | 0 | 0 | 0 |
  | 0x9e3779b9 | 0 | 0 |
  | 0x2468ace1 | 123 (32 at frame 2892) | 0 |
  | 0x12345678 | 0 | 0 |
  | 0x89abcdef | 0 | 0 |
  | 0xdeadbeef | 0 | 0 |
  | 0x0f1e2d3c | 0 | 0 |
  | 0x7f4a7c15 | 0 | 0 |

  The build leaks on 1 seed of 8 (largest 123 / 32); the prototype on none of 8. Neither of the ruling's cases: the prototype does
  not leak, but the build leaks on one seed only, which eight samples cannot tell from chance. The row is not called shared.
  What the leaking frames show (one more run of that seed logging the display records in mode 3, `runs/bbr_2468ace1_set`): the
  camera is 12-26 units inside the exit, mode 3; the near list holds 4-5 of the stretch's 6 boxes (under the old 6, so R2-2's
  longer list does not touch this exit, and 4fe3bec's code, before it, leaked the same 123 / 32); no rain object stands behind
  the exit plane; about half of the 60 drawn objects stand beyond the exit above the opening's top (H 5.0), the nearest 2-5 units
  past the plane at 9-10 over the mouth's road, at the opening's sides (lateral -19.5 and 14.9 against the box's -20 to 9): drawn
  last, they paint over the roof's underside around the opening. Not hunted further in this step.


## Stage 4: lightning (19 Nov 2026, branch `phase80-lightning`)

Stage plan `docs/superpowers/plans/2026-11-18-weather-stage-4-lightning.md`. Code `vrtools/arcade/weather/lightning.py`,
`weather/cover_standin.py` (a stand-in, removed at the join), `LightningTune` in `tune.py`, three blocks in `layout.py`, the registry
entries and `Module.copies` in `carrier.py`, `vrtools/mame/lua/lightning_log.lua`; formats note §27. Tests
`tests/test_weather_lightning.py`.

### What Pascal said (exactly) and what is not theirs

- 17 Nov: "the rain is good, it would be great to add two things: a lightning effect also in 3d that pop sometime and kind of white
  the screen so it makes it hard for the driver"; of the three flash strengths proposed (B recommended): "B".
- 18 Nov: "lightning is good but i think we should see the lighning a bit before or longer, it barely visible because of the flash
  and maybe make the color a bit more yellowish?"; "i think lightning is good but could it be a 3d lughtning?", the placement "B";
  "the lightning looks good but it s not visible enough (maybe not long enough) or maybe it should bling in and out couple of time?
  think extra hard", the white-out on the first stroke only: "and A for your question"; "good one more thing i think the lightning
  might need to be a bit narrower"; of the strokes 45 % thinner: "this is it, 45 is great keep it".
- Not Pascal's: the 20-40 s interval (the design: "tunable; Pascal did not answer on the interval"), lightning under cover (no bolt,
  no white-out, the sky flash kept: the session lead's proposal, taken as accepted), the lightning before the rain in the frame
  order (the design's sentence, and the session lead's ruling of 19 Nov when the plan's amendment said otherwise), the quotas and
  units. Pascal has driven the prototype sets (`out/p62lightningThin`, `out/p70storm`, `out/p75storm`), not this build.

### The port

Rewritten from spike 60/62's and spike 70's listings (not pasted); every value the prototype's. Checked against the prototype's own
functions run in its worktrees (scratch `out/p80l/scripts/proto_values.py`, `grids_proto.py`): the 12 bolt objects (the "thin"
strokes: rods 0.012 x 0.55 = 0.0066; 99-175 records, 69 088 bytes), the direction and turn tables, the white-out table (the overcast
table 85 % toward 255), the flash skies (the grey sky 40 / 80 / 95 % toward (31, 30, 28)), the eight colour picks (692, 248, 27, 227;
571, 542, 197, 150), the six patterns and the rule; and the ten courses' foot and occluder grids, computed on this branch's set by
the prototype's `height_grid` and `encode_grids`, equal cell for cell to this build's (decoded from its cropped blobs; int8 at scale
1, the largest foot error 0). Pinned in `tests/test_weather_lightning.py`.

What differs from the prototype, each from a rule of the carrier (lightning.py's docstring has the same list):
- **The placement over a few passes.** The prototype ran its up-to-16 tries in the strike's first pass (its worst strike frames,
  15.0-15.9 ms in its own runs). Here 4 tries a pass, a try three units after the guard (the place and its foot; sight-line samples
  0-3; 4-6 and the keep): a strike's timeline begins up to four passes later (about 0.14 s), unseen by the player.
- **The white-out in units.** A smoke run measured the colour RAM's row string move at 12.8 us (32 rows were 408 us; the prototype's
  note had estimated 0.25 ms for all 96): the switch is 12 units of 8 rows (about 1.2 ms on the white-out's pass, as much for the
  restore on the next), each after the guard, the brightest values first. A white-out whose first unit finds the pass late is not
  shown (the prototype's rule: "when the first vblank has already come at the strike, the wash table is not switched in"); one cut
  later would show its bright values washed for that frame and be restored from the next pass. The lightning runs before the rain,
  early in the pass: in every run below neither happened (white-outs late 0, cut 0), so the white-out frames are the prototype's.
- **The sky's palette write and the strike's start after the guard** (a late pass leaves them to the next).
- **Its own random generator**, seeded at the first race pass from the rain's word and the wheel's input words (the prototype stirred
  the wheel's words into the rain's own generator).
- **The grids cropped** to each course's box of cells holding anything (9 124-24 088 bytes a course against 32 768; lossless), and a
  sight-line sample off the 128 x 128 grid reads "nothing there" (the prototype read past the grid's end there).
- **No valid foot, no strike** (corrected in fix round 1, F1). When none of its 16 tries finds a foot the grid accepts, the
  prototype struck anyway, on the player's ground at the place its registers still held: the last try that passed the view check,
  whose foot cell the grid had just refused (within 48 units of the centreline, or beside tall geometry), or garbage when no try
  passed it. The first build kept that place (it did not reach it in any run, but it was a bolt on the road waiting to happen); the
  build now strikes nowhere then (counted, NFALL; the next strike is scheduled as after any other; strike_seq and strike_band
  untouched, so no thunder for a strike nobody saw).

### Units and quotas (measured: `lightning_log.lua`'s G and U lines, the time between two guard tests from the storm's code)

Over the stage's runs (gate session 1: the ten stress runs, the cover, dense and race-end runs, the seven RAIN matrix runs), the
longest time from each test to the next in the same pass (a time in which the game's vblank handler moved the count, 17.38 ms in,
is left out: it holds the handler's own work, and the A lines bound the time from that move to the pass's end):

| unit (the test it begins at) | longest |
|---|---|
| a try's sight-line samples 0-3 | 148 us |
| 8 colour-RAM rows (a white-out unit or a restore unit; the last one up to the rain's first test, its setup included) | 150 us |
| a try's samples 4-6 and the keep | 131 us |
| the bolt's frame, strike_seq / strike_band | 118 us |
| a try's place and foot | 107 us |
| the bolt (transform, matrix, object entry; up to the rain's first test) | 102 us |
| the sky's palette write | 60 us |
| the strike's start (the next scheduled, the pattern, the run and the turn) | 35 us |
| (the rain's longest, for comparison: a splash's drawing) | 147 us |

The work before a pass's first guard test (from the carrier's body, its show counter, to the first test: the lightning's
scheduler or timeline and rule, then the rain's setup on a pass where the lightning tests nothing): median 63 us, longest 71.5 us
(74.5 us with the stand-in cover's test routine); stage 2 named 47.5-51.5 us from the scenery routine's return for the rain alone.
PLACE_QUOTA 4 tries a pass; XLAT_UNIT 8 rows; a try three units. No placement pass was cut by the guard, no white-out skipped or
cut, no sky write late in any run. The release: in the game's flow a strike always ends with the race mode (the time-over run
below), so the lightning's release finds nothing to put back (a compare); when a flash sky is up it adds one string move of n
colours to the rain's 349 us (not reached by the game's flow, not measured).

### Results (headless MAME 0.289, gate session 1, 19 Nov; `VR_RAIN_SUBSET=heavy6`, `VR_MAME_JOBS=2`)

The RAIN race matrix (the normal build: a strike every 20-40 s; 150 s runs, about 116 s of race):

| race | busiest (stage 2) | late passes | after the move | strikes (bands) | bolt passes | white-outs (late, cut) | longest lightning unit |
|---|---|---|---|---|---|---|---|
| Big Forest | 17.61 ms (17.60) | 19 | 186 us | 3 (1, 2, 3) | 69 | 3 (0, 0) | 129 us |
| Bay Bridge | 17.64 ms (17.57) | 8 | 156 us | 3 (1, 3) | 65 | 3 (0, 0) | 146 us |
| Bay Bridge reverse | 17.58 ms (17.57) | 22 | 191 us | 3 (1) | 70 | 3 (0, 0) | 129 us |
| Acropolis | 17.48 ms (17.47) | 10 | 92 us | 3 (1, 2) | 65 | 3 (0, 0) | 150 us |
| Acropolis reverse | 17.48 ms (17.48) | 5 | 77 us | 3 (1, 2) | 65 | 3 (0, 0) | 146 us |
| Metropolis | 16.65 ms (16.62) | 0 | - | 3 (1, 2) | 65 | 3 (0, 0) | 128 us |
| Pacific Coast reverse | 17.65 ms (17.63) | 1 | 216 us | 3 (1, 2, 3) | 65 | 3 (0, 0) | 108 us |

Every race: no stale display list, every pass under 17.8 ms, the overrun counter still, the render rate 28-29, no list skipped,
60 clusters drawn on the median pass, the onsets shown never more than three within 58 video frames. Bay Bridge's busiest pass
(3801) is a white-out pass. Under the autopilot the strikes come at nearly the same frames on every course (the seed is the rain's
word and the wheel's input words at the first race pass, alike under the autopilot; a player's are not).

The stress build (a strike 0.4-1.2 s after the last ends; 90 s, the ten courses, the rate tests' autopilot lines): 29-31 strikes a
course (298 in all), 69-78 onsets each (every one read from palette RAM and the colour RAM at the pass's end, not from the module's
counters), never more than three within 58 video frames; busiest 15.76-17.64 ms, no stale list, the bound after the move held;
bolts drawn on 622-686 passes a course, none trimmed, none behind the camera; the feet in sight on 0-11 strikes a course, the
others the least hidden of 16 tries, no fallback; every strike's foot 36 units or more from the centreline (the grids refuse 48
around it; a foot lies anywhere in its 16-unit cell) and 300-800 units away. The dense test pattern (5 onsets in 13 logic frames):
47 strikes, all 47 cut by the rule, 114 onsets, never more than three in 58 frames. The stand-in cover over road points 40-139 of
Big Forest: 236 strike passes under cover, no bolt (178 skipped) and no white-out (8 skipped) there, the sky flashing on them;
outside it bolts and white-outs as usual. A race ended by time over on a white-out pass (Big Forest, pass 2241: the flash sky and
the white-out up): on the next pass the strike had ended, the sky was the grey and the colour RAM the overcast table (the rain going
on through the results); released at the attract's opening (2703): the boot's table, the course's own sky, nothing of the storm
after.

DRY: the identity gate on entry 0, entry 6 and entry 9 reverse (pressed and by the countdown) is main's race pass for pass, the
pictures equal; `weather=False` is main's set member for member. The lightning has no hook in the game's code: a DRY pass runs the
stub's switch test only (stage 2's), unchanged. `test_rain_does_not_change_the_game` (the lightning's records subtracted): Big
Forest line 4, 7 827 passes identical, 7 821 visible rain passes with the game's own records equal; Metropolis 3 512 and 3 507.
The screens did not move: COURSE DIRECTION 14.74 ms (converted) / 18.88 ms (original), COURSE WEATHER 18.83 ms, no stale list.

### Space (the stage-4 branch's own build; `layout.room` on it)

| space | stage 2 used | stage 4 used | the lightning's |
|---|---|---|---|
| work RAM: cells | 2 944 | 3 188 | 240 (236 its cells, 4 the stand-in's) |
| work RAM: image | 4 880 | 9 316 | 4 436 (code 3 682, tables 596, alignment) |
| work RAM: data | 26 640 | 66 096 | 39 456 (the white-out table 12 288; one course's blob, at most 27 160: Surfers Oval / Road) |
| boot ROM: storm stub and lists | 940 of 1 280 | 1 116 | 176 (one common record, one an entry); 164 left |
| bank 3: storm image | 4 880 of 20 480 | 9 316 | 4 436 |
| bank 3: lightning data (new block 0x174000) | - | 201 844 of 204 800 | the white-out table and ten course blobs |
| polygon ROM: lightning objects (new block 0xfef200) | - | 69 088 of 69 088 | 12 bolts; 21 052 bytes left at the run's start (0xfe9fe4) |
| program ROM: lightning colours (new block 0x28ffe0) | - | 16 of 16 | 8 colour words |

The prototype used 87 072 bytes of RAM for its lightning block (four colour tables, int8 grids of 32 768 a course, five skies);
this build uses 39 456 of data and 4 436 of image. Bank 2 is still unused.

### TDD evidence

- RED: `tests/test_weather_lightning.py` committed before the module (106b9d1); its static tests failed on the missing module and
  tune (`4 failed`: out/p80l/red_static.txt). The first static run on the module found seven tests of stage 2's carrier file that
  pinned the rain as the only module (the stub's lists overflowing with three copy records an entry; the rain's cell first; the
  image listed with its tables; the copy lists; an unknown module named "lightning"): the stub's lists led to `Module.copies`
  (38ec57d), the others to the shared test commit (9315dac, then ed21f38).
- GREEN: gate session 1, `2 failed, 82 passed, 26 skipped in 2698.10s`: the two failures a test's slip (the carrier test picking the
  probe module by index) and the white-out read from the colour RAM (the boot's table before the rain read as a white-out); fixed
  in ed21f38 and run again in gate session 2: the static tests of the carrier, rain and DRY files, all of
  `tests/test_weather_lightning.py` and the RAIN matrix's rate test (heavy6), `75 passed, 26 skipped in 1542.62s` (the 26 skipped:
  the thirteen races outside heavy6, twice), every run's figures identical to session 1's (the code unchanged between them; the
  DRY, same-game and screens tests passed in session 1 on this code).

### Not verified

- Pascal has not driven this build; the stills are under `out/p80l/look/`.
- The release with a flash sky up (not reached in the game's flow: a strike ends with the race mode; the code is there).
- The whole RAIN matrix (thirteen races skipped by `VR_RAIN_SUBSET=heavy6`) and the whole DRY gate: the join and stage 7 run them.
- Real hardware.

### Stage 4, fix round 1 (19 Nov, the review of 690f7b5..2db74ac and the session lead's rulings)

- **F1, no valid foot, no strike.** When none of the 16 tries finds a foot the grid accepts, the build now strikes nowhere
  (counted, NFALL; the next strike scheduled as after any other; strike_seq and strike_band untouched). The prototype, and the first
  build, struck on the player's ground at the last try that passed the view check, whose foot cell the grid had refused (within 48
  units of the centreline or beside tall geometry): a bolt on the road, never reached in the runs but reachable. Shown on a test
  build whose Big Forest grid refuses every cell (`lightning.module(..., refuse_all=True)`; the grid not cropped there):
  `test_no_strike_where_no_foot_is_valid`. The sampled-strikes test no longer exempts any strike.
- **F2, the sound's cells checked.** `interface_errors` (tests/test_weather_lightning.py): strike_seq changes on a pass exactly when a
  strike's timeline begins there, by +1, and on no other pass; strike_band changes only then and is 1 / 2 / 3 by the distance
  against 467 / 633, and is held unchanged on every pass until the next strike's first pass (the session lead's amendment, found by
  the sound's review: the sound tests its guard first and may read the band a pass or more later; the code already held it: the
  band is written only on a strike's first pass and never cleared). Applied to the ten stress runs, the cover run, the matrix's runs and the refused run (where neither cell ever
  changes). A strike begun under cover counts for the sound (spec 5.4: "Rain sound fades out under cover and back (5.6); thunder is
  heard the same."): the cover run's strikes begun under cover set both cells (formats §27 says so).
- **F3, the TEST menu and a soft reset in the middle of a strike** (the stress build, Big Forest, at the white-out pass ending on
  frame 2443, its flash sky and white-out up): the menu's MEMORY TEST, escaped, EXIT: the machine reboots, the attract plays, the
  storm idle, SBR the boot's, nothing of the storm written, the colour RAM the boot's table; a soft reset there: the storm's state
  cleared by the boot within four frames, idle until a new race's load, the colour RAM the boot's table.
- **M5**: a course's flash skies overrunning FLASH_ROOM are refused (PatchError) instead of moving the grids silently.
- **M7b**: the lightning log's helpers live in `vrtools/mame/runner.py`; no test module imports another for them.
- **M8**: test-only planted faults (`lightning.FAULTS`, the tests' `VR_LIGHT_FAULT`): "band" (the band one off), "seq" (+2), "cover"
  (`under_cover` ignored), "norule" (every onset allowed); each makes its test fail (below).
- The built set changes against 2db74ac's only in the storm image (bank 3 0x1df4e2..0x1e1923: the lightning's code 104 bytes
  shorter without the fallback's place, its state one word shorter, so the rain's cells and code moved by 4 and 104 bytes) and in
  three bytes of the stub (boot 0xfff26c: the module cells' count it zeroes, 0x5ba -> 0x5b8 halfwords; 0xfff33c..0xfff33d: the
  image's length in its common list, 0x1232 -> 0x11fe halfwords); program ROM and polygon ROM unchanged; the DRY set unchanged
  (gate session 2's builds against the GREEN run's, member by member).
- **TDD evidence.** The tests first (1fa5e7a; the log helpers moved before them, 4535fd7), RED on 2db74ac's module with the planted
  faults: `5 failed, 2 passed in 901.09s` (the blob overlap: DID NOT RAISE PatchError; no valid foot: no NFALL count, 14 strikes;
  the stress run: strike_seq 0 -> 2, strike_band 1 at distance 663; under cover; the denser pattern: 41 onsets, none cut). The fix (bb6fc3a); the refused build
  then still struck (`1 failed in 752.45s`: 14 strikes, the grid refused only inside its crop box), fixed in 7ab298f (the whole grid
  refused). GREEN on e2e66b1 (the static tests of the carrier, rain and DRY files, all of `tests/test_weather_lightning.py`, the
  heavy6 RAIN matrix's rate test and lightning matrix, `test_rain_does_not_change_the_game`, the DRY identity gate on entry0,
  entry6, entry9_reverse; `VR_RAIN_SUBSET=heavy6`, two MAME jobs): `84 passed, 26 skipped in 1954.58s (0:32:34)`, no
  MameKilledWarning.

## Stage 5: the wet handling (19 Nov 2026; branch `phase80-handling`, one of the four parallel tracks)

Plan: `docs/superpowers/plans/2026-11-18-weather-stage-5-handling.md`. Module: `vrtools/arcade/weather/handling.py` (its docstring
is the contract: the sites, the stubs, the routines, what each preserves); formats §28; tests `tests/test_weather_handling.py`.

### What Pascal said (exactly) and what is not theirs

Pascal, 17 Nov 2026: "when pressing full gas on lower gear 1/2/3 it wheels might sleep, braking hard might also trigger a slide and
cornering should feel slightly wider but just for a bit i dont want the game to feel strange, i prefer the risk is cornering for too
long and loosing control". After the first prototype's drive: "The lost of control in turns i think this shouldnt apply when we lift
the foot of the gas pedal (it has to be linked with the gas)"; of a lock: "A" (releasing the brake gives grip back at once); of
tunnels: "A" (dry inside); after the take-off's last change: "hangling is good now!". Every value is the design's table (S5.7, the
prototype's as driven). The builder's calls, not Pascal's: the one gate for every player rule (below), the pit lane read as the pit
stop, the cost figures' acceptance (follow-ups).

### What was built

Eight hook sites of the prototype in the boot ROM's physics and sound code (slide 0xfed8be, brake 0xfed178, wheelspin 0xfed190,
steering 0xfeb2df, engine sound 0xffa390, grip 0xfeb43d, squeal 0xffa46e, opponents 0xfec7a7), each a `jmp` to a boot-ROM stub
that tests the weather byte, then SWITCH (the carrier's rule for code outside the scenery call), and either jumps to its wet routine
in the storm image or runs the site's own instructions (byte for byte; the grip's PC-relative read in its absolute form) and jumps
back. The wet routines test the race mode first (so the countdown, the goal and results, mode 0x1d and the test menu, where SWITCH
can still be 1, run the game's own instructions), then the gate: the player's race handler (not the start, pit or post-goal
handler), no put-back glide, pit state 0, not under the player's tunnel flag (+0x152 bit 7, the game's own; not cover's cell). The
module's `frame` (after the rain's) clears the state outside the race mode; the carrier zeroes the cells at each load. No `start`,
no `release` (nothing outside its RAM is changed). Registered after the rain.

### Differences from the prototype, and why

- The squeal and the engine note follow the same gate as the other rules: they run from the race HUD every pass, also during a
  glide or a pit stop, where the prototype's stale slip mark or engine note could sound (the shared context's rule: none of it in a
  glide or the pit). The grip's gate gained the handler/glide/pit tests, which change nothing (the steering routine runs only on the
  race and post-goal handlers' driving branch).
- The brake clamp is the design's -1583.0 (the prototype's -1820 / 1.15 = -1582.61; 0.03 % of the force).
- Every site is a `jmp` (the prototype called three stubs with `jsr`): the same instructions run, a DRY call costs less.
- Gone: the prototype's tune table in ROM (the values are the build's immediates), WS_DUR and its counter (0, off, in the approved
  set), DRY_COVER and RAIN_ON (always on; DRY is the weather byte), the lock's x 1.0 (the lift force itself).
- The stubs test the weather byte and SWITCH (the carrier's contract) where the prototype tested its RAINF only: 323 bytes of boot
  ROM against its 240.

### The rules, the tests, the values (for the session lead and Pascal)

| rule (S5.7) | test | this build (MAME 0.289, scripted) | the prototype (out/p54/look/NOTE.txt) |
|---|---|---|---|
| slide from 420 (dry 546) | `test_the_designs_values_are_the_codes`; `test_none_of_it_under_cover` (546 inside) | immediate 420; under cover S grew to 2 444 by the dry rule, no spin | 420; under cover S to 2 486, no spin |
| builds only above half gas (128) | `test_full_lock_on_half_gas_does_not_spin` | the game's pedal 127, full lock at 294 km/h: S stays 0, no spin | in-game 127: S stays 0, no spin |
| spin: S >= 0x900 above 100 km/h, cool-down 77; about 1.4-1.8 s | `test_full_lock_on_full_gas_spins` | 1.53 s after the wheel (294 km/h), at 305 km/h, on the tarmac | 1.48 s after the wheel, at 324 km/h |
| grip base -16 | `test_the_designs_values_are_the_codes`; `test_the_grip_base_and_the_player_out_of_the_opponents_factor` (fix round 1) | immediate -16 (376); measured: the same race under cover to 280 km/h, then open on one run, 38 % lock: the open run's grip settles 16 under the covered run's for 8 passes (181-177 against 197-193) | 376 (187-189 -> 171-175 across Metropolis's exit) |
| wheelspin x0.6 -> x1 at 60 km/h, gears 1-3 | `test_the_take_off` (the curve asserted on every slipping pass since fix round 1) | 0-100 1.98 s (without it 1.70); traction minimum 0.303 at 0 km/h (the game's own 0.5 there, times 0.6); on every slipping pass between 0.5 x m and m (m = 0.6 + 0.4 x km/h / 60); slip to 58 km/h, gears 1-3, full gas only (none at the game's pedal 178: the speed pass for pass the set's without the handling); the engine note +1200 a slipping pass to 6000, -1500 without, the engine command the game's of rpm + note | 1.96 s (dry 1.69); traction 0.30 at standstill; slip to 60 km/h |
| lock: 80 % for 8 logic frames above 100 km/h | `test_a_held_brake_locks_the_front_wheels` | 17 video frames after the press (8 passes), at 304 km/h; path turned 0.00 deg; released 3 frames after the brake's end; locked 48.7 km/h/s, lift 47.9 | 0.28 s (8 logic frames); path 0.0 deg; locked 49.4 km/h/s, lift 48.6 |
| no lock on taps | `test_brake_taps_do_not_lock` | 6 on / 2 off: count max 6, never locked, 76.3 km/h/s | count max 6, 79.4 km/h/s |
| clamp -1583 | `test_the_designs_values_are_the_codes` | immediate -1583.0 | -1582.61 |
| squeal from 280 | `test_the_designs_values_are_the_codes` | immediate 280 | 280 |
| opponents x0.97 | `test_the_opponents_lap_about_3_percent_slower`; the player out of it: `test_the_grip_base_and_the_player_out_of_the_opponents_factor` (fix round 1) | flying laps 3.08 % longer (2.86-3.24 % over 15); the player's speed and place on the start straight (247 passes, top 204 km/h) the same in RAIN and DRY with no rule firing, the opponents' factor at work on all of them | not measured as laps |
| none under cover / countdown / glide / pit / after the goal | `test_none_of_it_under_cover`, `..._in_the_countdown_or_a_glide`, `..._in_a_pit_stop`, `..._after_the_goal` | cells still through 161 countdown passes, a 32-pass glide, two pit stops of 398 passes, 299 passes after the goal; brake inside the tunnel at 321 km/h: no lock | cover and glide measured; pit, post-goal: "gated in code, not driven" |
| a race ending mid-effect | `test_a_race_ending_mid_lock_...`, `..._mid_spin_...` | locked at the time over, cleared 24 frames later; the next DRY game's cells untouched; the next RAIN game's cells 0 at its load and its lock / spin as the first's (17 frames; 1.67 s) | not run |
| DRY untouched | `test_a_dry_races_handling_fields_are_mains`, the DRY identity gate | 1 211 passes of a scripted DRY race: every handling field main's | Big Forest / Metropolis pass for pass |

### Cost

`test_the_hooks_cost` (pass for pass the same game, busy time differences): a DRY race pass pays 41.5 us for the handling's dry paths
(median 42; the whole storm's DRY cost against the switch-off set 43.6 us); the calls a pass: the opponents' site 15.1 (once per
opponent), the engine and squeal sites 1.0, slide, brake, steering, grip 0.84, wheelspin 0.72 (the physics routines skip some
passes): about 1.9 us a call. A RAIN race pass on which no rule fires (the probe set: the opponents' factor 1.0, the gas under the
wheelspin's) pays 165 us for the wet routines (median 172); a countdown pass 57 us. The hooks run in the game's own logic before the
scenery call; the rain's guard then trims rain on a heavy pass, the cap holds (the matrix below).

Per site (fix round 1, F4; a measurement build only, `handling.module(trace=True)`: every exit and every stub's dry path writes its
number to a cell, and `handling_log.lua`'s VR_HANDLING_TRACE times each call from the stub's read of the weather byte to that write,
MAME 0.289's emulated time, in steps of 0.5 us; the time includes the site's own instructions where the path runs them and the trace
write; Big Forest, 1 049 race passes, four runs: DRY, RAIN with the gas under the wheelspin's and the wheel straight (no player rule
firing), RAIN with SCRIPT's take-off, full lock, held brake and taps, RAIN with full lock at speed to a spin):

| site | calls a race pass | DRY (the stub's dry path) | RAIN, no rule firing (the routine's usual exit) | RAIN, the rule firing | outside the race mode (countdown, goal) |
|---|---|---|---|---|---|
| slide | 0.70-0.93 | 1.5 us | 17.0 (the slide drains: the game's decay) | 28.5 (the slide grows / the spin fires; 26.5-39.5) | 3.5 |
| brake | 0.97 | 1.5 | 14.0 (no lock) | 16.0 counting, 19.0 the lock taking hold, 16.5-20.5 locked (the lift force) | 3.5 |
| wheelspin | 0.82-0.91 | 1.5 | 12.5-15.0 (the game's own traction) | 27.5 slipping (the curve and the note), 16.0 gripping | 3.5 |
| steering | 0.97 | 2.0 | 4.5 | 6.5 (a skipped pass under a lock) | 3.5 |
| engine sound | 1.00 | 2.0 | 6.5-9.0 (the note added, 0 when none) | the same | 3.5 |
| grip | 0.97 | 1.5 | 8.5 (the base -16) | the same | 3.5 |
| squeal | 1.00 | 1.5 | 9.0 (from 280) | 9.0-10.5 (the slip's floor) | 3.5 |
| opponents | 15.1 (once per car) | 2.0 | 6.0 an opponent (x0.97), 4.5 the player (skipped) | the same | 3.5 |
| per race pass | about 22 calls | 41.1 us (the A/B: 41.5) | about 161 us (the A/B: 165) | at most about 212 us (every site's slowest measured exit at once; a lock and a slide never grow together) | about 57 (the A/B: 57) |

The opponents' site is most of either cost (DRY 30 us of 41, RAIN 90 of 161): fifteen calls a pass.

### The gates (one invocation on the real fixtures, `VR_RAIN_SUBSET=heavy6`, `VR_PRE_WEATHER_SET=out/p35play2`, `VR_MAME_JOBS=2`)

`tests/test_weather_handling.py tests/test_weather_rain.py tests/test_weather_carrier.py tests/test_weather_dry.py
tests/test_weather_screen.py::test_the_screens_frames_hold_the_rate` on 712bd06: `5 failed, 93 passed, 26 skipped in 2948.55s
(0:49:08)`, no MameKilledWarning. The five were stage 2's tests that assumed the storm does not change the game or its timing (the
HUD's and after-the-modes' RAIN-against-DRY pictures, the TEST switch at fixed frames of race_end.lua's lap), the handling replay's
assertion (it parts on the green's own pass, not after it) and the two same-game replays racing to build the set without the
handling (a FileExistsError); fixed in 7306701 (those runs race both RAIN and DRY on the set without the game-changing modules, the
build under a lock) and run again: below.

The RAIN race matrix (heavy6; the handling in every race, the autopilot driving it wet):

| race | busiest pass | stage 2's | first rain frame | late passes | longest after the count's move | stale |
|---|---|---|---|---|---|---|
| Big Forest | 17.61 ms | 17.60 | 15.83 | 24 | 180 us | 0 |
| Bay Bridge | 17.64 | 17.57 | 14.56 | 16 | 153 | 0 |
| Acropolis | 17.56 | 17.47 | 16.45 | 14 | 172 | 0 |
| Metropolis | 16.93 | 16.62 | 15.41 | 0 | - | 0 |
| Bay Bridge reverse | 17.66 | 17.57 | 15.13 | 55 | 178 | 0 |
| Acropolis reverse | 17.48 | 17.48 | 16.30 | 5 | 92 | 0 |
| Pacific Coast reverse | 17.50 | 17.63 | 13.75 | 1 | 62 | 0 |

Every pass under 17.8 ms, the overrun counter still, render 28-29, 60 clusters drawn on the median visible pass (the passes differ
from stage 2's: the car drives another race in the wet). Big Forest line 4: busiest 17.62 ms, only rain trimmed.
DRY identity: all thirteen cases (ten courses, three reverse) pass for pass main's from the load (1 213 passes, pressed and by the
countdown), pictures equal; the switch-off set member for member main's. The screens: COURSE DIRECTION 18.88 / 14.74 ms, COURSE
WEATHER 18.83 ms (stage 1's figures, unchanged). The attract's busiest pass outside its scene loads: 17.73 ms in the traced 200 s
(stage 2: 17.71 ms; the opponents' site runs for the demo car and the opponents: the hooks' dry paths). The test menu from a RAIN
race (MEMORY TEST, EXIT), a soft reset, three games RAIN / DRY / RAIN, the race's end and time over: pass with the handling in.

### Room

| space | used by stage 5 | stage 2 left | note |
|---|---|---|---|
| boot ROM | 323 bytes (block "handling stubs" 0xfffea0, 0x150) + 8 sites in place (67 bytes) | 6 026 in runs of 96+ | the top of the run 0xfff120..0xfffff0; 0xfff620..0xfffea0 (2 176) left for the others |
| storm image (RAM 0x522000.., bank 3 0x1df4c0..) | 1 457 bytes of code | 27 888 / 15 600 | image 6 344 bytes in all |
| module cells (RAM) | 28 bytes | 5 248 | |
| program ROM, bank 0, polygon ROM, bank 3 data | 0 | | |

The prototype used 240 bytes of boot ROM for its stubs (one test of its RAINF each; these test the weather byte, then SWITCH, the
carrier's rule, and every site returns by a jump), 1.2 KB of code and 0.1 KB of table in program ROM, 30 bytes of cells.

### Not verified

Pascal's drive of this build (the behaviour is the prototype's: `out/p59handling`, `out/p75storm`); the RAIN race matrix's other
thirteen races (the join's); Surfers Oval in the wet (the prototype's autopilot got stuck on its verge; not run here); a pit stop in
reverse and on the converted courses (Big Forest's normal pit stop only); the grip's -16 measured in a corner (pinned in the code,
`test_the_designs_values_are_the_codes`; the prototype measured it; fix round 1 measured it on a straight, not in a corner);
real hardware.

**The rerun (7306701, real fixtures):** the five and the static pin: `7 passed in 996.55s (0:16:36)`, no MameKilledWarning. With
the handling switched off for it, the same game: Big Forest line 4 7 827 passes and Metropolis 3 512 passes from the load identical;
with it on (`test_the_handling_changes_the_replayed_game`) the Metropolis replay parts from the DRY race at the green's pass (frame
1867); after the rain's modes 266 snapshots to the direction screen equal to DRY, released at the attract's opening (+356 us).

### Fix round 1 (19 Nov, the review of 690f7b5..0b4516c and the session lead's rulings)

Rulings: the DRY cost in DRY races and the attract is accepted (at most the handling's dry path, bounded by a test; recorded in
`docs/deviations.md`, the wet handling's DRY cost); "in the pit lane" is the pit stop (the pit handler, from the trigger to the
release), as built.

- F1, the bounds: stage 2's switch-test bound is back at 10 us, measured on the set without the game-changing modules against the
  switch-off set (`test_dry_runs_no_storm_code`, a `dry_same` run). The handling's own DRY cost has one constant,
  `DRY_COST_MAX_US` = 50 in `tests/test_weather_handling.py`: on the mean DRY race pass (the set against the set without the
  handling) and on the attract's busiest pass outside its scene loads (the same two sets, 200 s each). Before the fix the whole
  storm against the switch-off set measured 43.6 us a DRY pass: the 10 us bound fails there (the RED); on the set without the
  game-changing modules it holds (the final run: 2.13 us mean, median 3, over 1 210 DRY race passes).
- F2, the excluded states: a static test that slide, brake, wheelspin, engine note, grip and squeal each hold the whole gate in
  order (race handler, no glide, pit state 0, no tunnel flag). Dynamic: in a glide and a pit stop, with a stale slip mark and engine
  note forced into the cells (the logger's ports `slip`, `note`), the engine and squeal commands equal the game's dry formulas of the
  pass's rpm and L on every pass (and the wet values would differ on some); the countdown's opponents equal the DRY race's on every
  countdown pass; after the goal the opponents run at their base performance on most car-passes (0 % in the race); under cover on
  any road (the logger's VR_HANDLING_COVER forces the tunnel flag) SCRIPT's take-off, full lock, held brake and taps in RAIN equal
  the DRY run pass for pass (1 211 passes: traction, slide, grip, lock, engine and squeal commands). Planted faults
  (`handling.FAULTS`, test builds only; `VR_HANDLING_FAULT`), each RED:

| fault | test | how it fails |
|---|---|---|
| cover (no tunnel-flag test) | `test_none_of_it_under_cover` | Metropolis's tunnel: the wet rules act inside (|S| 792, not the dry rule's > 0x900); the cover twin parts at the first race pass (traction 0.593 against 0.988, squeal 0xc10c against 0xc108) |
| glide (no glide test) | `test_none_of_it_in_the_countdown_or_a_glide` | in the glide the engine command 0xc07f against the dry 0xc059 (the note added), the squeal 0xc10c against 0xc108 |
| pit (no handler, no pit-state test) | `test_none_of_it_in_a_pit_stop` | in the pit stop the engine command 0xc07f against 0xc066, the squeal 0xc10c against 0xc108 |
| countdown (modes 0x12-0x13 taken as the race) | `test_none_of_it_in_the_countdown_or_a_glide` | the opponents' working performance differs from the DRY race's on 160 of 161 countdown passes |
| goal (modes to 0x1c taken as the race) | `test_none_of_it_after_the_goal` | the opponents at their base on 0.0 % of the car-passes after the goal (more than 50 % required) |
| player (the opponents' factor not skipping the player) | `test_the_grip_base_and_the_player_out_of_the_opponents_factor` | the player's own +0x48 x0.9700 from frame 2473 (490 of 762 race passes) |

  The speed check alone (M7's first half) did not fail on the "player" fault: the opponents' site runs for the player only on the
  passes its steering fade-in does (here from the bend's wall on), and the value it stores there does not set the speed on a
  straight; the player's own +0x48 is now logged and compared on every race pass.
- F3: this round's changes to shared files are their own commits (runner.py, test_weather_rain.py, test_weather_carrier.py); the
  branch's history is not rewritten (the task report lists every shared-file hunk for the join).
- F4: the per-site cost, measured per call (the cost section's table above).
- M1 the registry test asserts only the handling after the rain and before the sound if present; M2 the cost runs' probe set is
  the registry's modules with the handling built with the factor 1.0; M3 the logger's mode trigger printed in hex; M4 the take-off
  curve asserted on every slipping pass (the rules table above; RED on the set without the handling: 0-100 1.70 s, no slipping
  pass); M5 the call-site `jsr`/`rsr` code removed (the built set's bytes unchanged, sha256 per region against 0b4516c); M6 only the
  handling stubs' `jmp` operands may differ in the hook-site test (RED: one planted byte in a stub's weather test, the old assertion
  passed it, the new one fails); M7 the grip base measured (-16, the rules table) and the player out of the opponents' factor.

The final invocation (real fixtures, `VR_MAME_JOBS=2`, on a1f1b85): `tests/test_weather_handling.py` in full and
`tests/test_weather_carrier.py::test_a_module_adds_a_hook_site`, `::test_dry_runs_no_storm_code`,
`::test_a_module_adds_code_cells_and_course_data`: 28 passed, exit 0, 25 min 54 s, no MameKilledWarning. Its figures: the handling's
dry paths 41.50 us on the mean DRY race pass (median 42; 1 210 passes), the whole storm against the switch-off set 43.62 us; the
attract's busiest pass 17.734 ms against 17.708 ms without the handling (+26 us); the RAIN wet routines with no rule firing
165.46 us a race pass, a countdown pass 57.17 us; stage 2's switch test 2.13 us; the take-off 1.98 s (1.70 without), 38 slipping
passes to 56 km/h, traction minimum 0.303 at 0 km/h, traction / m 0.504-0.988, the note 1200, 2400, 3600, 4800, 6000; the cover twin
1 211 passes, no difference; the opponents after the goal at their base on 81.3 % of car-passes (0.0 % in the race); the grip 16
under for 8 passes; the player's straight 247 passes identical (top 204 km/h), its +0x48 the DRY race's on all 762 race passes.

## Stage 6: the storm's sound (19 Nov 2026, branch `phase80-sound`, built in parallel with stages 3-5)

Plan: `docs/superpowers/plans/2026-11-18-weather-stage-6-sound.md` (with its "as built" notes). Code: `weather/sound.py` (the board,
the V60's triggers, lightning's stand-ins), `weather/thunder_gen.py` (the samples), `tune.SoundTune`; `romset.RomSet` reads and writes
the sound board's three members; `vrtools/mame/lua/pcm_log.lua` and `runner.parse_pcm_log`; `tests/test_weather_sound.py`. Formats
note §29.

### What Pascal said (exactly) and what is not theirs

- "the thunder sound is good as A (one crack)", "actually i like 13!": the crack A with the rumble (the generator's settings).
- "rain is too low i cant hear it and i think same for the thunder", then "now the rain is a bit too loud, id say in between before
  and now": the rain bed at -7.1 dB (settled).
- Of the joined set: "everything is good but level of the thunder is too high". The build has out/p75storm's thunder (-1.5 dB) and
  ducking (4.125 / 3.0 / 2.25 dB) as `SoundTune` defaults: settled on the joined build, "thunder level is good" (20 Nov 2026).
- Not Pascal's: lightning's stand-ins, the board's layout. (D6, which ended a thunder at RAIN OFF, was withdrawn by the session
  lead's ruling C2: the approved prototype wins.)

### The port

- Samples: byte for byte the prototype's (SHA-256 pinned; deterministic in two processes; no file opened).
- Board: the two sample ROMs are out/p75storm's byte for byte (CRC 048048be / 239c2bee); the program is out/p75storm's (610dfdbc)
  but for four listed ranges (fix round 2's timing patch: CRC 8c3e6961; P75_PROGRAM_DIFF; a standing test against the set where
  VR_P75_SET is present), 980 bytes from 0xac00 (out/p75storm's 948 at their addresses and the clear routine's 32 after them). The
  68000 code is emitted from named instructions; each site's original instructions are checked (encoded as instructions), and so
  are the originals the routines re-implement or rely on (the tunnel handler's fall-through, the RAM clear's loop, the reset's
  `bsr 117e`); the sound numbers' handlers must be the no-op 0x588 and the sample-table entries free, before anything is written.
- Triggers: the module `sound`, last in the frame order (rain, lightning's stand-in, sound), 204 bytes of code, 20 bytes of cells;
  no hook site, no release, no data. Nothing of it runs outside the scenery call: in mode 0x1d and in the test menu entered from a
  RAIN race (SWITCH still 1) it does not run.
- Measured alone (the attract, the words injected): close 0-1 s RMS -10.9 dBFS (peak -2.5), medium -11.7 (-3.2), distant -14.1 (-7.6),
  the rain -20.9: out/p75storm's own figures, its chip writes identical in order and value (31 285 writes).

### Results (headless MAME 0.289)

| Gate | Result |
|---|---|
| Latch contract (3 games: RAIN Big Forest to its finish, RAIN Metropolis, DRY Metropolis) | RAIN ON once a RAIN race, 0.19 s into the countdown; one thunder word a strike by band (8 strikes); RAIN OFF 0.15 s after the finish; none in the DRY game, the results or the attract; the rain voice keyed from RAIN ON to 0.65 s after RAIN OFF; the thunder voices keyed their wait after the word |
| Other voices against the control set (the same strikes sending the no-op B062) | 456 832 writes to every other voice identical in order and value outside the 8 ducking windows, moved at most 2.2 ms (the handlers' own time); level writes inside the windows 6 824 against 5 473 |
| Silence | our voices silent from the fade after RAIN OFF to the next RAIN ON (122.2-154.3 s) and from the second RAIN OFF to the end, through the DRY game's race, results and name entry (mode 0x1e) and the attract |
| A race ending during a thunder (struck 25 passes before the line) | finish 120.86 s, RAIN OFF 121.01 s, the rain keyed off 121.66 s; the rumble sounding at the line rings out its sample, 120.29-126.81 s (6.51 s), and nothing of ours after it; every rumble of the run within its band's longest (6.51 / 6.52 / 7.04 s from key-on); from its end every write to the board the control's |
| A strike after the finish (the stand-in strikes in the goal) | no thunder word, no thunder voice: the triggers send thunder only in the countdown and race; the prototype's lightning starts a strike only in mode 0x14, so it never thunders after the finish |
| Time over while a thunder sounds | the game's 8100 in the frame the race mode ends keys all our voices off; RAIN OFF follows; nothing after |
| TEST switch in a RAIN race (not run in the prototype) | 8100 within 0.3 s keys everything off; no storm word in the menu or after its EXIT (reboot) |
| Soft reset in a RAIN race | the boot's 8100 keys everything off; no storm word after |
| Full scale: the thunder adds none | while a thunder sounds or its duck holds, no full-scale sample the control set does not have (fix round 2's restatement; none in that window on these runs, with or without thunder); outside it the runs differ by the looped samples' phase after a duck: on fix round 2's board 9 samples with the thunders (226.162 s, where the control peaks at -0.26 dBFS) against 8 without (225.132 s); before it, 11 against 16 |
| Full scale only at the game's own loudest moments (ruling C1) | every full-scale sample within one tick (fix round 3; within 0.1 s before) of a moment where the switch-off set is within 2.17 dB of full scale (where the rain's own -13.1 dBFS peak could take it over; fix round 1, M1): 11 samples (32.57, 33.68, 111.04-111.12 s) against the switch-off set's 0 (36 within 1 dB); fix round 1's run: 11 (32.57, 33.68, 111.04-111.12, 158.76 s: Metropolis's horn, the switch-off set -1.28 dBFS); within a tick, 111.122 s missed by 0.20 dB on the board before fix round 2; on fix round 2's board the one-tick window misses nothing and is the asserted form (fix round 3) |
| The storm alone (the attract, words injected) | the rain peaks -13.1 dBFS (RMS -20.8), the thunders under -1 dBFS at p75storm's levels |
| Frame time with the triggers and strikes | Big Forest 2 673 passes busiest 17.577 ms, Metropolis 3 511 passes 17.606 ms; stale 0 (the pass after the load excused as `_stale` does) |
| RAIN matrix (`VR_RAIN_SUBSET=big_forest,metropolis`, the normal set: the stand-in never strikes) | Big Forest busiest 17.61 ms, Metropolis 16.64 ms; stale 0; start-up 4 passes; post-move 186 us |
| `test_rain_does_not_change_the_game` | Big Forest line 4: 7 827 passes identical; Metropolis 3 512 (sound is not a game-changing module) |
| DRY identity (entry0, entry6, entry9_reverse) | pass for pass main's (1 213 passes; timeout 1 303); the sound latch words from the load identical to the switch-off set's (934 / 810 / 1 060 words) |
| DRY sound board (fix round 2; Big Forest, Metropolis, entry 9 reverse, from the boot) | write for write, except that a word arriving within 3.8 us of a tick boundary may be read one tick (17.96 ms) apart; none in the three test races: every write to both chips v0.3's in voice, register, value and order (66 765 / 74 255), only the spare voices' key-offs at a reset extra; the ticks within 4 us, each write up to 0.78 ms later within its tick (the level hook). The residual race: the main loop polls the timer in a 38-cycle loop (0x1164, 3.8 us), so a word reaching the board within that of a tick boundary can be read a tick apart when anything has moved the loop by a few cycles (none in the DRY races; once between the RAIN chain with and without thunder: C055 at 194.631 s). Before fix round 2 (828.8 us late, from the init's 168 hooked writes): dynamic effects cut short or run longer by up to ~1.9 s, a note held 20.4 ms at C041 |
| Switch off | main's set member for member (`VR_PRE_WEATHER_SET=out/p35play2`); the switch on changes the three sound members only inside their layout blocks |
| Screens | COURSE DIRECTION worst 14.74 ms, COURSE WEATHER 18.83 ms (converted course): unchanged |

### Found: the approved rain level and full scale (the session lead's ruling C1: the gate restated)

On Big Forest's autopilot race the switch-off set peaks at -0.0 dBFS at the start horn and -0.13 dBFS at 111.0 s (a collision's
effects: B04A, B015, B046). With the rain bed at its settled level the mix reaches full scale there: 11 samples, 2 at the horn
(32.57, 33.68 s) and 9 at 111.04-111.12 s, with or without thunder (the race without thunder: 16). The prototype's record shows the
same (p74 on Pascal's drive: 4 samples at full scale, 1 without the storm). Not changed: the rain's level is Pascal's. The gate is
now what is required: the thunder adds no full-scale sample, every full-scale sample lies in a moment where the switch-off set is
within 2.17 dB of full scale (fix round 1), the storm alone stays under it (deviations; `out/p80s/listen/` 09 / 10 to hear the collision).

### Found: the duck's trace

- A voice whose track ends while the duck is down keeps the ducked level written to it until its next note (the duck restores the
  levels of active tracks only): measured, the race's voices left so were all keyed off (silent), so nothing audible stays ducked.
- The thunder word's handler takes longer than the no-op's, so writes in that tick move by up to 2.2 ms and key-ons by up to 0.3 ms;
  looped samples keep the phase shift: the output is not sample-identical to the race without thunder afterwards (per-second
  loudness within 0.86 dB, mean 0.03 dB). Inherent in the prototype too.

### Differences from the prototype

- In the sound board: the sample ROMs none; the program four ranges (fix round 2's timing patch, P75_PROGRAM_DIFF: the reset's
  `bsr 117e` back in place at 0x544, the boot's RAM clear at 0x982 jumping to the clear routine, the reset routine without its first
  call, the clear routine at 0xafb4), so the board's ticks are v0.3's (the prototype's ran 828.8 us late). Two storm events start a
  tick later than on the board before it (C201's fade at 233.76 s in the chain, the injected attract thunder at 21.19 s; up to
  19.2 ms): inherent in the realignment. After the finish, as the prototype: RAIN OFF ends the rain loop; a thunder that had
  started rings out its sample (at most 6.5 s close and medium, 7.0 s distant from its sound's start; 6.8 / 7.1 / 7.9 s from the
  word); the results begin about 6.7 s after the line, so a thunder struck in the race's last second or so is heard at the start of
  the results: "silence through results" holds except that tail (the session lead amends the design's sentence).
- The trigger tests the guard first and does nothing on a late pass (its decisions are by state: the word goes on the next pass);
  the prototype's had no guard test.
- The prototype sent the thunder word at a strike's start even when its placement found no place (`jsr place` then `jsr
  snd_strike`); this build sends it only when lightning's `strike_seq` changes, and the real lightning (being fixed) changes it only
  for a strike that is not aborted: an aborted strike will have no thunder (the prototype's had one).

### Room (this stage, against stage 2's table)

- Storm RAM cells +28 bytes (the stand-in's 8, the sound's 20); storm image +204 bytes (RAM and its bank-3 copy); no data, course
  data, stub list, polygon, colour or site block of the V60's.
- Sound board (its own members): program 980 of the 0x500 block from 0xac00 (948 the prototype's, 32 the clear routine of fix round 2) (erased run 87 044 bytes), plus 40 bytes of the
  sound-number table and the five code sites' blocks (0x26e, 0x548, 0x550, 0x982, 0x17f2: 42 bytes; 34 before fix round 2); chip 1 61 376 of 0xf000 from 0x600 (+24 bytes of table); chip 2 57 968 of 0xe300
  (+24 bytes of table).

### The join

Remove `carrier._lightning_standin_factory` from `carrier.REGISTRY` when the real lightning is registered (cells `strike_seq` and
`strike_band`; the triggers read their low bytes; a strike is `strike_seq` + 1 with `strike_band` 1 / 2 / 3 on that pass), keep
`_sound_factory` last, cut the bands at `SoundTune.bands` (467, 633). The test sets of `tests/test_weather_sound.py` keep their own
striking stand-in. The trigger relies only on `strike_seq` changing: `strike_band` is read only on a pass where `strike_seq`'s low
byte differs from the last seen, so a strike that the real lightning aborts without touching either cell sends nothing.

### Not verified

- By ear: nothing (WAVs and their levels for Pascal in `out/p80s/listen/` with NOTE.txt).
- With the real lightning (the join); the other eighteen RAIN races with the triggers (stage 7); the test menu's SOUND TEST playing
  the new numbers; real hardware.

## The join (Task 6J, 19 Nov 2026): cover, lightning, wet handling and sound on one branch

Brief `.superpowers/sdd/2026-11-18-weather-storm/task-6J-brief.md`; stage plan `docs/superpowers/plans/2026-11-18-weather-stage-6J-join.md`.
The join changes no behaviour: every look, sound and drive was approved on prototypes and ported by the tracks. What it changed is
listed under "What the join changed".

### The merges

Merge commits on `phase80-weather` (base 0820e91, stage 2's closing touches), in this order: `phase80-lightning` 4077fa6 (no
conflict), `phase80-handling` 757ad14, `phase80-sound` ba84cc6, then `phase80-cover` at d954913, 8bb6b9c and 82607ea (the last two
documents only). The conflicts, all resolved by hand:
- `weather/carrier.py`: the factories and REGISTRY: [cover, lightning, rain, handling, sound]; the lightning's stand-in cover and
  the sound's stand-in lightning were not kept (two modules of one name cannot be laid out); stage 2's closing docstring kept.
- `weather/layout.py`: every track's blocks in the table; the docstring's paragraphs in stage order 3, 4, 5, 6.
- `weather/tune.py`: CoverTune, LightningTune, HandlingTune, SoundTune in stage order.
- `tests/test_weather_carrier.py`: the same three assertions edited by three tracks (the image's code listed without its tables,
  the probe as the last module, the first module's cell): one line each; the copy lists take the cover's table first and leave the
  lightning's course record to its own test.
- The documents (deviations, follow-ups, formats note, findings): each track appended at the end; kept in stage order 3, 4, 5, 6,
  every heading of each branch present (checked by a grep of each branch's added headings).
- Auto-merged and read: `vrtools/mame/runner.py` (the lightning's log helpers, the handling's F and P lines, the cover's C lines),
  `storm_log.lua`, `tests/test_weather_rain.py` (GAME_CHANGING_MODULES = ("handling",), `same_build`, the lightning's record
  subtraction), `weather/__init__.py` (the sound board after the carrier), `weather/rain.py` (the cover's version, wholesale: no
  other track touched it).

### What the join changed

- The stand-ins out of `vrtools`: `weather/cover_standin.py` deleted; the sound's `lightning_standin_factory` removed; the
  striking stand-in (`strike_standin`, `STANDIN_CELLS`) moved to `tests/weather_standins.py`, a test helper of the sound's tests.
- One rule for tunes: `tune.Tunes`, one field per module by name; every registry factory hands its module its own field and no
  other; `install_weather(..., tunes=)`, `carrier.install`, `default_modules`, `module_named`, `ten_course_set(weather_tunes=)`,
  `cli.build(weather_tunes=)`. The cover is also handed the rain's cluster count (`tunes.rain.clusters`: a fact of the rain its
  tables are made for).
- The storm stub's block grown from 0x500 to 0x5c0 through the layout table (the five modules' copy lists need 1 276 bytes).
- Three fixes the reviews left for the join: the DRY sound comparison's offset figure on the ticks where the boards agree (a
  recognised one-tick event no longer pairs writes a tick apart); a forced-state test of the carrier's reload branch
  (`test_the_reload_branch_on_a_forced_state`, `storm_poke.lua`); `run_mame`'s safety copy beside the work directory, removed in a
  `finally`, stale ones swept.
- The bound after the vblank count's move split in two (the session lead's ruling): the unit in flight (the move to the guard's
  trip) at most `UNIT_MAX_US` (200 us), the tail (the trip to the pass's end) at most `TAIL_US` (190 us, from 31); the cap
  `RAIN_BUSY_MAX_MS` 17.8 -> 17.9 ms (below, "The cap").
- `test_the_hooks_cost`'s attract comparison keeps its upper bound only (the session lead's ruling: the busiest pass of two sets is
  not a sum; 17.702 ms with the handling against 17.708 without, per pass -30 to +93 us).
- The formats note's weather sections renumbered: §26 cover, §27 lightning, §28 wet handling, §29 sound; the joined RAM table
  generated from the layout.

### Room (the joined build, `layout.room`; out/p80j/room_cover.txt)

| block | space | size | used | left |
|---|---|---|---|---|
| storm stub | boot 0xfff120 (grown at the join from 0x500) | 1 472 | 1 276 (1 312 after task 8's record and W8's mask) | 196 (160) |
| storm image | bank 3 0x1df4c0 | 20 480 | 17 948 (round 2; round 1 17 888) | 2 532 |
| storm data | bank 3 0x1e44c0 | 24 576 | 24 576 | 0 |
| storm course data | bank 3 0x1ea4c0 | 13 056 | 12 032 | 1 024 |
| lightning data | bank 3 0x174000 | 204 800 | 201 844 | 2 956 |
| rain objects | polygon 0xfda424 | 64 448 | 64 448 | 0 |
| cover objects | polygon 0xfe9fe4 | 12 160 | 12 160 | 0 |
| lightning objects | polygon 0xfef200 | 69 088 | 69 088 | 0 |
| rain colours | program 0x28ff80 | 96 | 92 | 4 |
| lightning colours | program 0x28ffe0 | 16 | 16 | 0 |
| handling stubs | boot 0xfffea0 | 336 | 323 | 13 |
| storm RAM cells | ram 0x520000 | 8 192 | 4 436 | 3 756 |
| storm RAM image | ram 0x522000 | 32 768 | 17 948 (round 2) | 14 820 |
| storm RAM data | ram 0x52a000 | 86 016 | 67 232 | 18 784 |
| sound code | sound 0xac00 | 1 280 | 980 | 300 |
| chip 1 samples | pcm1 0x600 | 61 440 | 61 368 | 72 |
| chip 2 samples | pcm2 0x600 | 58 112 | 57 957 | 155 |

The boot ROM's erased run between the storm stub and the handling's stubs: 0xfff6e0..0xfffea0, 1 984 bytes free. The joined RAM map,
generated from the layout: formats note §30.

### The one invocation on all twenty races (the brief's gate list)

`out/p80j/scripts/gate.sh final all` on d84cce1 (log out/p80j/final.log): the eight `tests/test_weather_*.py` modules,
`test_frame_rate`, `test_cli`, `test_directory`, `test_v60asm`, `test_dirscreen_build`, `test_originals_reverse`,
`test_reverse_times`, `test_ranking`, `test_reverse_ranking`, `test_mame_runner`; VR_RAIN_SUBSET unset, VR_PRE_WEATHER_SET,
VR_P75_SET, VR_MAME_JOBS=3: `28 failed, 703 passed, 11 skipped in 11680.27s (3:14:40)`, no MameKilledWarning. The skips are
`test_reverse_times`' release records (VR_P35_MAIN_SET, a build of 47460b0, not on this machine: accepted). The failures:
- 18 in `test_weather_cover.py`: the cover's taped tests ran on the set with the wet handling, which changes the replayed game by
  design (a harness problem of the join); the cover's sets now leave the game-changing modules out (as the rain's same-game tests);
  re-run (out/p80j/cover2.log): `1 failed, 53 passed in 2708.53s (0:45:08)`: Metropolis normal's exit (below).
- `test_weather_sound.py::test_a_late_strike_still_thunders`: the sound's trigger late on runs of passes (below).
- `test_frame_rate.py::test_the_game_is_the_same_pass_for_pass[2]`: one frame-end field sample (below); it passes on the base.
- `test_cli.py::test_no_weather_reaches_the_build` x2: the test's expected keywords lacked the join's `weather_tunes`: fixed.
- `test_originals_reverse.py` x2 and `test_reverse_ranking.py` x4: the same six fail on `phase80-weather`'s base 0820e91 (stages 1
  and 2, before the join; out/p80j/base_run.log `6 failed, 1 passed`): not the join's; for Task 7.
The split bound re-evaluated on the run's own storm logs (136; the run's Python asserted the old sum, its logger wrote the B
lines): the longest unit in flight 80 us, the longest tail 186.5 us on the RAIN matrix and 195.5 us on one cover pass run with
the handling in (Bay Bridge reverse, frame 4288: 39 live splash slots cleared after the trip): over TAIL_US 190 (reported).

### The per-course table (the joined build, all five modules, the RAIN matrix: 150 s, the autopilot, both directions)

Busiest pass (what it was: the cover's mode on that pass, a strike); passes at or above 17.7 ms / 17.6 ms (the cap is 17.9 ms: none
within 0.2 ms of it); the first rain frame; stale lists; the longest time from the count's move to the pass's end, and its parts
(the unit in flight, the tail); the longest unit between two guard tests (the lightning log's G lines); records peak; the rain's
trims (budget and late, clusters / splashes); the lightning's strikes and white-outs (its own trims: 0 on every race); thunders
sent; the rain's late passes; the cover's late passes.

| race | busiest ms (what, frame) | >=17.7 / >=17.6 | first | stale | move-end (unit, tail) us | longest unit | records | rain trims budget; late | strikes, white-outs | thunders | rain late | cover late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| big_forest | 17.63 (open road, 1991) | 0 / 3 | 16.01 | 0 | 198 (33, 175) | 140 | 10500 | 143/20; 19/93 | 3, 3 | 3 | 29 | 0 |
| big_forest_reverse | 17.09 (a strike, 5471) | 0 / 0 | 14.13 | 0 | 0 | 130 | 10500 | 953/775; 0/0 | 3, 3 | 3 | 0 | 0 |
| bay_bridge | 17.70 (inside, the curtain at the exit, 2865) | 0 / 17 | 14.80 | 0 | 214 (61, 181) | 146 | 8963 | 0/0; 130/125 | 3, 3 | 3 | 87 | 0 |
| bay_bridge_reverse | 17.70 (open road, 6335) | 0 / 15 | 15.33 | 0 | 209 (42, 186) | 151 | 9419 | 0/0; 468/131 | 3, 3 | 3 | 140 | 0 |
| acropolis | 17.55 (open road, 1927) | 0 / 0 | 16.63 | 0 | 162 (37, 140) | 130 | 10494 | 0/2; 0/64 | 3, 3 | 3 | 20 | 0 |
| acropolis_reverse | 17.50 (open road, 1871) | 0 / 0 | 16.48 | 0 | 118 (31, 93) | 131 | 9410 | 0/0; 0/37 | 3, 3 | 3 | 10 | 0 |
| alpine | 17.54 (inside, the curtain at the exit, 3083) | 0 / 0 | 13.27 | 0 | 160 (32, 152) | 150 | 5997 | 0/0; 6/0 | 3, 3 | 3 | 5 | 0 |
| alpine_reverse | 17.52 (near a mouth, outside, 5297) | 0 / 0 | 14.24 | 0 | 78 (23, 68) | 131 | 6919 | 0/0; 9/7 | 3, 2 | 3 | 6 | 0 |
| diablo | 15.68 (open road, 2427) | 0 / 0 | 13.32 | 0 | 0 | 130 | 6640 | 0/0; 0/0 | 3, 3 | 3 | 0 | 0 |
| diablo_reverse | 15.88 (open road, 2481) | 0 / 0 | 13.24 | 0 | 0 | 130 | 7299 | 0/0; 0/0 | 3, 3 | 3 | 0 | 0 |
| surfers_road | 16.80 (open road, 1927) | 0 / 0 | 15.43 | 0 | 0 | 108 | 7457 | 0/0; 0/0 | 3, 3 | 3 | 0 | 0 |
| surfers_road_reverse | 17.54 (open road, 4817) | 0 / 0 | 15.97 | 0 | 106 (36, 88) | 108 | 7307 | 0/0; 0/12 | 3, 3 | 3 | 1 | 0 |
| metropolis | 17.65 (near a mouth, outside, 4047) | 0 / 13 | 15.63 | 0 | 216 (44, 182) | 146 | 8681 | 0/0; 71/60 | 3, 3 | 3 | 86 | 0 |
| metropolis_reverse | 17.65 (near a mouth, outside, 3571) | 0 / 4 | 15.60 | 0 | 212 (53, 180) | 144 | 8110 | 0/0; 12/22 | 3, 3 | 3 | 25 | 0 |
| pacific_coast | 15.93 (open road, 2357) | 0 / 0 | 13.43 | 0 | 0 | 131 | 6694 | 0/0; 0/0 | 3, 3 | 3 | 0 | 0 |
| pacific_coast_reverse | 17.49 (open road, 2207) | 0 / 0 | 13.92 | 0 | 54 (15, 40) | 130 | 7380 | 0/0; 7/0 | 3, 3 | 3 | 1 | 0 |
| surfers_oval | 16.24 (open road, 2481) | 0 / 0 | 13.10 | 0 | 0 | 112 | 7199 | 0/0; 0/0 | 3, 3 | 3 | 0 | 0 |
| surfers_oval_reverse | 15.57 (a strike, 8443) | 0 / 0 | 13.11 | 0 | 0 | 130 | 6034 | 0/0; 0/0 | 4, 4 | 4 | 0 | 0 |
| amazon_falls | 16.40 (open road, 2529) | 0 / 0 | 13.14 | 0 | 0 | 128 | 7094 | 0/0; 0/0 | 4, 4 | 4 | 0 | 0 |
| amazon_falls_reverse | 16.43 (open road, 2523) | 0 / 0 | 13.20 | 0 | 0 | 108 | 7136 | 0/0; 0/0 | 4, 4 | 4 | 0 | 0 |

Every race: overrun counter still, render rate 28-29 from the green, no list of the game's skipped, the rain never took a frame
over the budget (test_rain_holds_the_rate passed on all twenty). The strikes: every strike thundered once (thunders = strikes).
Beside the tracks alone: the rain alone (stage 2) busiest 17.60-17.63 ms on the heavy courses; the lightning alone 17.48-17.65;
the handling alone 17.66; the cover alone 17.69 (its own measure); joined 17.70. The rain's trims grew where the cover adds work
(Metropolis late trims 0 -> 71/60 against the four modules without the cover; Bay Bridge reverse 239/78 -> 468/131): the guard
trims rain first, as designed. Big Forest's budget trims: 1 352/279 with the four modules before the cover (e1), 143/20 joined
(not explained further here: the cover consumes the rain's generator and the passes' timing moved).

### The heaviest pass's make-up

The busiest pass of the twenty races, Bay Bridge frame 2865, 17.699 ms (re-run with storm_makeup.lua: the same game, 4 176 of 4 176
busy times equal; out/p80j/mk_final_bb.txt): the game's own work 11.629 ms (with the handling's hooks but 26 us of them: below); the
wet handling's 22 hook calls 26 us by the logger; from the
scenery routine's return to the first guard test 5 us; the cover 353 us (mode 3: the camera inside Bay Bridge's tunnel, the
curtain at the exit, 62 curtain clusters; the lightning's idle frame returns before its guard test and counts in this share); the
rain 5 652 us (it draws until the guard: on this pass the count moved during a cluster's landing unit, 35 us before the trip at the
splash loop's guard, then its late splash path); the handling's frame 2 us; the sound's triggers and the game's tail 32 us. The
next busiest on that race: frames 2895 (17.692), 2919, 2867 the same make-up (the same exit); frame 3803 (17.689 ms) a strike: the
lightning 1 376 us (its white-out units), the rain 3 239 us, the cover 52 us. On Metropolis (frame 4047, 17.652 ms): the game's own
10.4 ms, the cover 197 us (mode 1, near a mouth outside), the rain 6 935 us. The known costs alone, for comparison: a white-out about
1.2 ms on its pass (here 1.38 ms of the lightning's share with the bolt), the handling's wet routines 161-212 us a race pass outside
the scenery call (the logger's figure here, 26-62 us, counts each call from the stub's test to the routine's last access of the
handling's own cells: the opponents' hook, 15 calls a pass, touches none, so it undercounts; the trace build's 161-212 us stands,
and the "game's own" figures above include the difference), the cover's units up to about 0.35-0.49 ms a pass at a mouth, the sound's triggers a few
microseconds.

### The cap, the split bound and the contract (the session lead's ruling of 19 Nov 2026)

The bound after the vblank count's move is now held in two parts (storm_log.lua's B lines; `post_move_over`): the unit in flight
(the move to the next guard test, the trip) at most UNIT_MAX_US, 200 us; the tail (the trip to the pass's end) at most TAIL_US,
190 us (stage 2: 31 us, one module's returns and the game's list submission). Measured with storm_makeup.lua on Metropolis (the
same game as the matrix run, pass for pass): the 216 us pass was 35 us of the rain's cluster-landing unit after the move, then 181
us from the trip at the splash loop's guard to the end: the rain's late splash path (`slate` / `sl2`) clears and counts every
remaining splash slot, up to 40, in one unguarded loop (about 145 us), then the handling's frame (2 us), the sound's triggers and
the game's tail (32 us). Natural tails: after a trip in the rain up to 182 us (186.5 on Bay Bridge reverse in the matrix), after a
trip in the cover 50 us; forced in the first module (the count written 1 at the carrier's body, every module's late path) 102.5-112.5
us (114.5 on Bay Bridge). The cap: 17.486 + 0.200 + 0.190 = 17.876 ms, RAIN_BUSY_MAX_MS 17.9 (stage 2: 17.8). The worst pass measured on all twenty
races: 17.70 ms. One tail of 195.5 us was measured (reported above).

The contract's other figures with every module on: from the scenery routine's return to the first guard test 4.9-5.1 us over
3 507 show passes (the cover tests the guard at once; stage 2: 47.5-51.5 us); the load pass 83.5 us from the routine's return to
the pass's end (stage 2's load alone: 40 us); the release 360 us on the attract's opening scene load (stage 2: 349; bound 400);
the longest unit between two guard tests 151 us (Bay Bridge reverse).

### DRY on the joined build

- The identity gate: all 13 cases (`test_dry_is_mains_race_pass_for_pass`, both forms) PASSED; `weather=False` is main's set
  member for member (VR_PRE_WEATHER_SET); the switch changes only the named blocks.
- The switch test on `same_build()` (stage 2's 10 us bound): mean 2.13 us, median 3, over 1 210 DRY race passes.
- The handling's DRY cost: 41.50 us a mean DRY race pass (median 42; bound 50; alone 41.50); the whole storm against the switch-off
  set 43.62 us. The attract's busiest pass (outside its scene loads): 17.702 ms with the handling, 17.708 ms without (per pass -30
  to +93 us, mean +23.6), against main's 17.98 ms; no stale list.
- The screens: COURSE DIRECTION 14.74 / 18.88 ms (converted / original), COURSE WEATHER 18.83 ms: not moved.
- The sound's exact DRY comparison on its three races (entries 0, 6, 9 reverse) PASSED with the corrected offset figure;
  the DRY sound words identical to main's (test_dry_sends_mains_sound_words).
- The reload branch, forced: PASSED (poked at 1700, reloaded on pass 1701, 3 start passes, frames from 1707; the DATA word back,
  the junk kept in the control).

### The cover's pins on the joined build (its re-pin rule; the cause: the join)

Measured on the cover's sets without the game-changing modules (out/p80j/cover2): Metropolis reverse's exit 388/28, 594/61, 912/56
on the three seeds (pinned 902/61 -> 912/61); spot s3's leak 0, 1 288, 2 278 px (pinned 2 250 -> 2 278; cells 32, 34, 32 of 36);
Alpine 1 490/84, 168/14, 139/8; Alpine reverse 851/27, 1 048/59, 794/45; Bay Bridge 0, 0, 123/32; Bay Bridge reverse 12/3, 20/4,
40/6; the approach: Metropolis reverse 2 objects at most (as pinned), every other pass 0; the negative control 225 141 px; the
cover never late on any of its runs; its rate runs' busiest 17.69 ms. The prototype's side of each comparison (seeded the same, on
the same taped DRY game, which the join does not change) stands as the cover's findings give it: not re-run. **Metropolis normal's
exit**, strict "none" until now, leaks 8 px (3 in the worst frame, frames 5240-5247) on seed 0x9e3779b9 and none on the other two:
a look gate that fails only with the effects together, reported; round 2 (the session lead's ruling J3): pinned under the re-pin rule
(cause: the join) at 8/3, and added to the limitations table (docs/deviations.md, Cover) as "on the joined build, one seed of three;
none on the cover alone"; re-measured after J1 and J2 (Round 2, below).

### Round 2 (20 Nov 2026: the session lead's rulings J1-J5, task-6J-fix-1.md)

**J1: the sound's trigger exempt from the guard.** On a pass the guard finds late the trigger counts the pass in its `late` cell
("sent on a late pass") and does its work all the same (`sound.trigger_code`: one return; the late path counts and branches back
into the work). Every word goes on the pass it is due: the thunder on the pass `strike_seq` changes, RAIN ON on the race's first
live pass, RAIN OFF on the first live pass after the race mode. The carrier's contract names it as an allowed unguarded unit
(`SOUND_TRIGGER_US` 40), measured from its guard test to its last access of its cells (storm_makeup.lua's VR_MAKEUP_SCELLS;
Metropolis and Bay Bridge reverse RAIN, the round-2 build):

| the trigger's pass | us (median / max) |
|---|---|
| idle (3 415 passes on Metropolis) | 7.0 / 7.1 |
| idle, late (88) | 8.0 / 8.1 |
| a rain word | 14.5 (17.5 late) |
| a thunder word | 18.5-21.5 |
| a thunder and a rain word on one pass (forced: 3 621 passes, late or not) | 25-29 / 32 |

(A pass the game's vblank handler lands in adds the handler's own ~190-240 us, as for any unit.) RED on the build before
(out/p80j/j1_red.log): the planted late strike's thunder a pass late (nthunder 3, 3, 4 at the passes before, on and after frame
4127), the fourth strike's thunder at 4129 against its strike pass 4127. GREEN: the focused runs (out/p80j/focused.log, focused2.log): the late strike thunders on its own late pass in both RAIN races of the chain; every word on its due pass (RAIN ON 1615 and 8873, the storms' first live passes; RAIN OFF 6953 and 14879, the first passes after the race mode; all ten thunders on their strike passes; the test's first form took the pass that turned SHOW as live, corrected); `test_every_strike_thunders_on_its_pass` on Metropolis and Bay Bridge both ways (three strikes each, every thunder on its strike pass); the frame time with the triggers: busiest 17.468 / 17.568 ms, no stale list, the trigger counted 454 / 397 passes late and sent on them.

**J2: the late splash path in constant time, the same picture.** After a trip in the splash loop the remaining slots are still
dead from that pass on (the prototype's anti-blink rule), cleared whole by one string fill (`movcfu.h`, R26 0; a dead slot's other
words are never read), and the late splash trims stay exact by the live count: SPLIVE (+1 when a spawn takes a dead slot, -1 when
a splash ends) less this pass's alive slots before the trip (LV); both appended to the rain's state words.
`test_the_late_splash_path_is_constant_time`: no branch back inside the late path. The proof that the picture is unchanged
(out/p80j/scripts/j2proof.py; old = round 1's final build, new = J2 alone, the same tape):

- Natural taped races (Bay Bridge reverse, Metropolis, Big Forest): the game's pass state identical; the rain's records and
  counters part at the first pass whose trip falls on another guard test (passes 1 003, 1 113, 691). The guard is a time test and
  J2 changes the storm's time (the late path about 140 us shorter, so the next pass starts at another phase of the vblank; a few
  instructions a spawn and an alive splash for the live count): no change to the storm's timing can keep a natural race equal
  pass for pass. The totals stay alike (late splash trims 26 / 27, 90 / 90, 100 / 115).
- The deterministic proof: storm_guardctl.lua makes the guard a function of the guard tests' order (every storm read of the vblank
  count 0, but on every second pass 1 from the n-th read after the splash loop's start, n cycling 1-81), so both builds trip on
  the same test; old, new and old again on the same tape (out/p80j/j2proof_gcsh.txt). On all three races (4 311 passes each; 570,
  459 and 555 passes through the late splash path; 1 824, 1 421 and 1 868 late splash trims) every write the storm's code makes
  into the display lists (storm_dlhash.lua: address, data and mask, hashed pass by pass) is IDENTICAL on every pass, old against
  new as old against old; the rain's counters (drawn, splashes, late, the four trims, records in / out) identical on every pass;
  the game's pass state identical (on Metropolis five passes END one frame later on the old build, its late path being longer:
  the same state). The frame-end record samples (rain_records.lua) are equal on two races and part on Metropolis at a frame where
  the list was sampled half written (a frame-end sample, not the picture).

The tail re-measured on the round-2 build (J1 and J2; out/p80j/mk_r2*.txt):

| tail (the trip to the pass's end) | us |
|---|---|
| natural: the trip in the rain / the cover / the handling / the sound | at most 52 / 58 / 41.5 / 39.5 |
| forced at the splash loop's head (storm_forcetail.lua): 40 live slots, the trigger sending a thunder and a rain word | 72.0 (median and 99th percentile) |
| forced in the first module (every module's late path), the trigger sending both words | 149.0 at most (median 132) |

TAIL_US 190 -> 160 (149 and a small allowance). The cap's arithmetic: 17.486 + 0.200 + 0.160 = 17.846 ms; RAIN_BUSY_MAX_MS stays
17.9 as ruled (`test_the_cap_covers_the_guard_bound`).

**J3: Metropolis normal's exit.** Pinned at 8 / 3 under the cover's re-pin rule (cause: the join) and added to the limitations
table (docs/deviations.md, Cover: "on the joined build, one seed of three; none on the cover alone"). Re-measured on the round-2
build: 0, 8 / 3, 0 on the three seeds (out/p80j/focused, cover_summary.txt): unchanged; stays pinned.

**J4: the same game pass for pass, compared at pass ends.** pass_state.lua with VR_PASS_FIELDS=1 logs every car's line cursor,
target, lap-position quad, working performance, rank and ranking neighbours at each pass's end (what fieldtrace.lua sampled at
frame ends); `test_the_game_is_the_same_pass_for_pass` compares the pass logs. RED: the old measure's torn frame-end sample on
Acropolis (round 1's final run). GREEN: Big Forest, Acropolis and Metropolis identical on every pass (3 314 passes, all 16 cars' twelve fields; out/p80j/focused); the planted control (car 3's x written 0.0 at frame 2500; its speed, the first choice, the game sets again each pass) differs from that frame on (focused2).

**J5: the six failures that fail on 0820e91 too, classified.** None is a difference from main in a DRY game or the attract.

| test | what differs, and why | class | fix |
|---|---|---|---|
| test_reverse_ranking: `test_with_no_game_the_attract_is_main_s_frame_for_frame` | up to the first original's reverse page (7 301) modes, pages and titles are main's frame for frame; the rows are logged on the same 16 frames; one differs: 4 646, where page 2's first step starts, one tile of row 1 ('8248') not yet written at that frame's end on this set, written by the next (4 647 equal; the page then stands as main's) | (b) a frame-end sample of a row being drawn | `settled_rows`: the rows on the same frames, equal wherever they stand more than one frame |
| test_reverse_ranking: `test_a_normal_race_writes_as_on_main` [4], [6]; `test_a_race_writes_as_on_main_but_its_group_s_counter` (the "1302 against 1402") | the COURSE WEATHER screen's handler takes main's select handler's place in mode 0x10 state 1 (1 204-1 402) and adds a mode line at its own second step (1 302, another address in the screen's code); every other line, write and load on main's frame | (a) stale: the old screens' lines | `_mode_frames` leaves out a line on which only the handler moved within the screen's code |
| test_originals_reverse: `test_each_checkpoint_gantry_has_a_list_with_its_lettering_behind_the_banner` | POLY_LEFT_FLOOR 150 000 (Phase 33, measured 182 760) predates the weather; v0.3 (with the palms, 28 080 bytes) stays above it; the weather's polygon objects (145 696 bytes, its own room table) take it to 8 952 | (a) a stale floor | the weather's polygon blocks counted back |
| test_originals_reverse: `test_an_original_races_in_reverse_on_its_variant[1]` (Bay Bridge reverse, 3 extensions against 4) | untaped on v0.3: 5 extensions; on the weather set fed v0.3's recorded inputs the game's state is v0.3's on all 4 177 passes, 5 extensions, the clock out on the same frame; untaped on the weather set the autopilot's frame-end samples part at pass 1 042 (the player's x in its last bits after another wheel value): 3 extensions (out/p80j/j5bb.txt) | (b) the autopilot's frame-end steering | `_race` replays the inputs of the same race on the set before the weather |


### Reported for the session lead (not decided at the join)

1. The sound's triggers late on runs of passes: last in the frame order and testing the guard first, they send nothing on a late
   pass; where the cover's work fills the passes to the guard (Metropolis, Bay Bridge) a thunder word or RAIN ON / OFF reaches the
   board up to 31 passes late (about 1.05 s) in the matrix and 106 passes (about 3.6 s) in the sound tests' Metropolis race
   (`test_a_late_strike_still_thunders`: the distant strike's word of pass 780 sent 0.33 s after its pass). Before the cover the
   longest run was 2.
2. The tail of 195.5 us against TAIL_US 190 (one pass, 39 live splash slots).
3. Metropolis normal's exit leak, 8 px on one seed (above).
4. `test_frame_rate.py::test_the_game_is_the_same_pass_for_pass[2]` (Acropolis): the game is the same pass for pass; one frame-end
   sample of the player's car (frame 3510: x 631.2, z 14.6) is a value main's log never shows within four frames, a read in the
   middle of the car's update: the handling's dry paths move where the frame end falls inside a pass. It passes on the base.

### Not verified

Pascal drove the joined build on 20 Nov 2026 (`out/p80j/play`, built from 83fc9cb): "big forest all good"; "metropolis tunels pit
rains sound good, i think one issue on metropolis, is the thinder get hidden by the building, maybe we should try to make the
thunder animation appears where it s not completly hidden?"; "alpine rain s good too" and "alpine tunel is also good"; "thunder
level is good"; "all good on dry"; "all good on bay bridge rain reverse"; "i think all the tests are good". On the street aim's
throwaway build (`out/p85/play_street`, 161 s on Metropolis): "i think that works better on metropolis"; on the scope: "yes only
metropolis change agree". Not driven by him: the street aim's proper build (`out/p86/play`); Metropolis in reverse he did not
name. He gave no word to merge or release.
Real hardware. Linked play (excluded by code). The whole suite (Task 7). The cover's prototype comparisons not re-run on the joined
build (their prototype side is unchanged by construction).

## Bolt placement on Metropolis (task 8, 20 Nov 2026; branch `phase86-bolt-street`, not merged)

The owner, after driving the joined build: "metropolis tunels pit rains sound good, i think one issue on metropolis, is the thinder
get hidden by the building, maybe we should try to make the thunder animation appears where it s not completly hidden?" (of Big
Forest: "big forest all good"). Spike 85 (throwaway, `spike85-bolt-visibility`, out/p85/NOTE.txt) measured the bolt's visible
share and tried placements; after driving its play set with the street aim: "i think that works better on metropolis". The session
lead proposed that only Metropolis change and every other course keep the approved placement; the owner: "yes only metropolis
change agree". Both directions of Metropolis is the session lead's reading of "only metropolis"; every other course keeps 12-40
degrees.

- **The measure** (`test_the_bolt_shows_on_metropolis`): two builds with the same code and timing, `lightning.module(measure="key")`
  (the bolt in one key colour, the palette entry nearest magenta) and `measure="twin"` (the same, its matrix scaled about the camera
  so the foot lies at view z 30: the same picture, drawn in front of every scenery polygon); `bolt_pixels.lua` counts the key pixels
  on every strike frame; a strike's share is its pixels over the twin's (the white-out frame left out); the two runs checked in
  lockstep. Metropolis normal, the stress tune, 100 s (the test session's modules: cover, lightning, rain, sound):

  | aim | strikes measured | clearly visible (half or more) | under 10 % | median share |
  |---|---|---|---|---|
  | 12-40 (34cdf89's, RED) | 30 | 23 % | 50 % | 0.10 |
  | 2-10 (the street, GREEN) | 27 | 48 % | 26 % | 0.34 |

  Pinned: at least 35 % clear and a median of at least 0.20. (Spike 85, with the wet handling in the build too: 27 % -> 43 % clear,
  median 0.34 -> 0.40.) Why the bolt hides there: only its lower part is ever on screen (its top, 0.85-1.27 x the distance, is above
  the screen's top edge, about 0.6 x the distance, on every course), and the facades stand 80-105 units high beside the road; the
  sight test's first sample is 37-100 units out, so it does not see them (follow-ups).
- **The build**: `LightningTune.aim_deg` (12-40) and `aim_by_entry` (Metropolis 2-10); the image keeps the default direction table;
  Metropolis's own table (192 bytes) sits after the last course blob in "lightning data" and one record of its entry's list copies
  it over the image's table after the common list (`carrier.TABLE_COPY`). Against 34cdf89's build: the program, polygon, sound and
  TGP ROMs, the storm image and every course's blob identical; 192 bytes of bank 3 (window 0x1a5474..0x1a5533, erased before) and
  127 bytes of the storm stub's lists (boot 0xfff318..0xfff62b: the copy directory's pointers of entries 7-9, Metropolis's list one
  record longer, the lists of entries 7-9 moved 16 bytes, their records the same); the stub's code unchanged; its lists have 180
  bytes left (160 after W8's two instructions).
- **Not verified**: Metropolis reverse (the autopilot stops against a bank there); the owner has not driven this build
  (out/p86/play).

## The final review's fix wave (20 Nov 2026; final-fix-wave.md, the session lead's rulings W1-W9)

Two final reviewers read the whole branch at fa8f251 (ready to merge with fixes, no Critical). The wave changes no emitted byte but
one, ruled as the exception: W8.

**W8, an interrupt during the storm's load.** The game enables one interrupt in play, the vblank (vector 65, handler 0xfe02bc).
Followed by every direct branch, bsr, jsr and call (550 instructions; the reviewer had not followed `call`): its backdrop column
update (0xfe02fa -> 0xFFE0E0 -> 0xFFE498 -> 0x279A76, while 0x40DF00 is 0) reads the data bank window for the sky's columns, on
every vblank around a race's start (61 of the 61 frames around each load). Its call through the RAM pointer 0x40DF20 is taken only
when that pointer is non-zero: 0 in every mode from the boot to the race. No hook site of the weather and no bank register write is
reachable from the handler. The storm's load is the only moment the storm maps another bank: measured on fa8f251's build over the
twenty RAIN loads (out/p86/w8, the PSW's interrupt bit set at every one), the load holds bank 3 for 45-50 us, 10.2-13.8 ms after the
vblank before it and 3.55-7.09 ms before the next (closest: Acropolis normal, 3.55 ms); no interrupt landed inside one. Held open
across a vblank (`carrier.build(test_load_spin=8000)`, Bay Bridge, its data in bank 1), the handler read the window 62 times with bank
3 mapped and the sky showed a wrong backdrop column (8 px at the left edge, rows 60-204) on every picture after the load (Big Forest
and Alpine live in bank 3: the load's mapping is theirs). The gate byte 0x40DF00 does not close it: the game sets it in the TEST
menu, and with it set the handler also skips its uptime counters and coin handling, lost rather than deferred. Fixed: the load
masks interrupts across its copy lists with the game's own pair (`updpsw.w #0, #40000` / `updpsw.w #FFFFFFFF, #40000`, as its
main code at 0xfe065a / 0xfe06a2 and four more pairs); with the forced spin no window read happens while bank 3 is mapped, the
vblank is taken 0.5 us after the unmask, the pictures after the load and the game's vblank and pass counts are the normal set's
(the vblank taken late is counted one frame end later on the load's frame only). Against fa8f251's build: one member differs,
the boot ROM's odd lane, 648 bytes all inside the storm stub's block (0xfff279..0xfff63f: the two instructions and the lists and
tables after them moved by 20 bytes, every record the same); three taped RAIN races (Big Forest, Bay Bridge reverse, Metropolis) are
the same game pass for pass with the full fields (2 739 passes each) and the same busy time on every frame from the third pass
after the load to the run's end (the load pass and the next one or two differ by 1-5 us: not explained; the likely cause is the
instruction the next vblank lands on moving with the 1 us longer load). The load pass costs 84.5 us (89.5 on Metropolis with task
8's record) against 83.5 (88.5) before. The owner has NOT driven the W8 bytes: `out/p80j/play` and `out/p86/play` predate them;
`out/p80j/play2` (Task 7) is the play set that has them.

**W4 and W9 figures**: in the evidence run (below). The join's and task 8's logs (161 files) had no unit between two guard tests
over 160 us.

## The whole suite and the merge (Task 7, 20 Nov 2026)

**The batch's one whole suite ran in two parts on two heads.** Part 1: `tests/` in full on 4aefa17 (out/p80j/suite.log, 8 h 23,
`VR_MAME_JOBS=4`, every reference set, all twenty races), real evidence up to `tests/test_tunnel_sound_build.py`; the session lead
then moved `vr.zip` aside (the weather tests behind it would have run on superseded bytes), so every later test that needs the
game set SKIPPED by that action, not as evidence (those needing no set still ran: the static parsers and units). Raw line:
`25 failed, 1503 passed, 324 skipped, 1 xpassed, 69 warnings, 15 errors in 30169.72s (8:22:49)`. Part 2, the last run on the merged
head (out/p80j/last-run.log, last-run.xml): the tunnel module and every file after it (test_v60asm, all test_weather_*), test_frame_rate,
and every test file changed since 4aefa17 (the first part's fixes among them), on 20d1b1f. Raw line: `7 failed, 795 passed, 2 skipped, 1 xpassed, 124 warnings in 14407.88s (4:00:07)`: the six known failures of main's (test_race_build's diablo at0 / at1, test_tgp_build's four) and test_the_game_sees_the_quads_turned_round[9] (unclassified, below); every weather file, the rate and stale-list gates, the flash rule and the cover's Metropolis pins passed.

Part 1's failures (F and X before the tunnel module), classified (c = a known failure of main's: on the list or failing on main
093d88a the same way, out/p80j/mainchk):

| test | class | cause | done |
|---|---|---|---|
| test_convert_collision (5), test_convert_geometry::thinning, test_convert_profile (2), test_race_build::diablo [at0, at1], test_tgp_build (4: saturn collision Big Forest, Alpine in Big Forest's slot, Alpine as entry three, arcade rate [2]) | c | out/p27/full_failed.txt | none |
| test_tgp_build::test_regenerated_big_forest_drives (XPASS) | c | main's Phase 22j xfail | none |
| test_hudname::test_hudname_follows_the_direction_screens_routines | c | image 7 221 bytes against a pin of 6 947; fails on main identically | none |
| test_pit_build::test_a_normal_pit_stop[9], test_a_reverse_pit_stop[9] | c | Surfers Road's pit stop never triggers; fails on main identically | none |
| test_props::test_without_the_palms_the_set_is_the_base_branchs | c | opt-in Phase 34 record, fails by design since Phase 33 | none |
| test_site_page::test_page_media_rules | a | the branch's copy predates main's 18 Nov page test (11 videos) | main's file taken |
| test_tencourse::test_the_ten_course_set_keeps_polygon_rom_free | a | POLY_FLOOR_BYTES is the courses' floor before the weather (8 952 left after its 145 696 bytes) | the weather's blocks counted back |
| test_tencourse::test_stand_in_entries_show_their_course_picture; test_race_build::test_banking_ab_on_the_surfers_courses [OVAL, ROAD] | a | one-course test sets cannot take the weather (the cover's stretches; the screen's room) | built with weather=False |
| test_reverse_build::test_the_ten_course_set_writes_a_missing_direction_block | a | its bare set lost the sound members the weather's board needs | dataclasses.replace keeps them |
| test_reverse_build::test_the_game_sees_the_quads_turned_round[9] | b | untaped, the weather set's autopilot steered otherwise: the car spins on Surfers Road reverse's road point 124 (yaw turning about 150 degrees), against its quads 7328-7424 (1.7 s), so the warning fires; fed the set before the weather's inputs the race is that set's pass for pass, warning silent (out/p80j/quads9.log) | both races taped from VR_PRE_WEATHER_SET, the pass state asserted equal (da5eb90) |
| test_tunnel_sound_build (15 errors) | a | its comparison set without the stretches cannot carry the weather; the constructor was rebuilt by every test | both sets weather=False; session_cache.cached caches a failed build |

Totals of the 25 F, 1 X and 15 E: a 6 F and the 15 E (one cause), b 1, c 18 F and the X, d 0.

Re-measured on the merged head (Task 8's Metropolis aim, the load's mask): the cover's Metropolis pins and the two lightning tests
in part 2 (above). The owner has not driven the merged head's bytes; out/p80j/play2 is its play set.
