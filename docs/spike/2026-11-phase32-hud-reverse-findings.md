# Phase 32: the word REVERSE under the course's name in a reverse race: findings

Branch `phase32-hud-reverse`, rebased on main add9799 (Phases 29 and 31 merged). **Not merged, not pushed. Pascal has seen
stills and said "Yes all your recommendation" (§1); they have not driven this set.** An independent review found it ready with
fixes; §10 is the fix wave. Facts and numbers only. Marks: **[V]** measured in MAME 0.289 or computed from the built ROMs in this
phase (the artefact or test named), **[R]** read (a listing, a source file, MAME's source), **[?]** not established. The scripts,
runs, builds and snapshots quoted are git-ignored under `out/p32/` (`recon/`, `gates/`, `fw/`, `look/`); the playtest set is
`out/p32play2`.

**Which main.** Two builds of main are quoted: `out/p28play2` (main 2a9f1ab, before Phases 29 and 31: the recon and the first
round's gates ran against it) and `out/p35play1` (main add9799, the session lead's build of merged main: every "against main"
figure in §3, §5 and §9 is against this one unless it says p28play2).

**Map:** §1 the request and Pascal's decision; §2 what the game's own means give (the recon); §3 what was built; §4 registers and
flags; §5 the gates; §6 snapshots and the playtest set; §7 what a heavier shadow or a neon glow would take; §8 not verified; §9
the tests run; §10 the review and the fix wave.

## 1. The request and Pascal's decision

Pascal's words, 15 Nov 2026, in order:

1. "One additional idea, when playing a track in reverse it could have the word "reverse" under the track name(maybe in a neon
   red style?)"
2. Told (by the session lead, relayed to the builder mid-task) that the HUD font is flat-coloured tiles and a true neon glow would
   need new graphics: "Ok maybe just a shadows reverse then"
3. Shown three stills of the first build and the session lead's recommendations (red on every course; the placement as built,
   left to their eye; keep it and send it to review): "Yes all your recommendation"

They have not driven this set. The red rests on the third sentence: their first sentence offers red as a maybe, with neon, and
their second drops the neon and names no colour.

The builder's brief after the second sentence: the word REVERSE under the course's name with a shadow; first establish what the
game's own font gives; if a more pronounced shadow is possible with the game's own means, build it as one alternative; no custom
tiles; recommend one colour and show at most two. Nothing may change in a normal race or on the three originals.

## 2. What the game's own means give (recon)

Runs: `out/p32/recon/runs/` (`dia_r`: Diablo Canyon reverse on `out/p28play2`, a build of main before Phases 29 and 31, 150 s, the word poked into the tile RAM
by Lua 100 frames into the race; `sh_a`, `sh_b`: Alpine reverse, 60 s, with a second copy poked on layer 1 and its scroll set).
Script `out/p32/recon/recon.lua` (write taps, tile / palette / character RAM dumps).

**Room under the name.**

- The screen is 62 x 48 tiles (496 x 384); the name is on layer 0 (0x700000), rows 44-45. Rows 46-47 are the screen's last two
  rows. **[V]** (`dia_r` dump `race400_tile.bin`, snapshot `runs/race400_x3.png`)
- What the game draws on rows 44-47 in a race, by column:
  - columns 2-11: the SPEED figures, down to row 46; row 47 empty. **[V]** (`dia_r` dumps)
  - columns 14-17, rows 44-46, **with the manual transmission only**: `[0x501936]` is the transmission the course select latched
    (the course select's code writes it: 0xfc29dc 1, 0xfc29aa and 0xfc29ca 0, 0xfc31f2 a register; `dirscreen_log.lua` logs it as such, and the tests' `VR_MANUAL` run sets it). When it is not 0 the HUD's first
    handler, right after the label's print, blits a map at row 42, column 13 (0x70151a) and two at row 44, columns 14 and 17
    (0x70161c, 0x701622), which reach row 46 (0xff47c3..0xff4802). **[R]** (the boot listing; the review's finding M1) + **[V]**:
    in a reverse race on Alpine with the manual transmission, rows 44-46 hold tiles on columns 14-17 that the automatic run does
    not have (`out/p32/fw/manual/`; `test_the_word_with_the_manual_transmission`).
  - from column 19 on: the name (rows 44-45) and, since this phase, the word (rows 46-47); everything else blank (0x8020) on
    every logged frame of every run of this phase. **[V]** This is what was measured, not a statement about every state of the
    game: a text of the game's that this phase did not provoke could use those cells (the linked cabinet's layouts, the
    operator's screens during a race, were not run).
- Nothing writes rows 44-47 from column 19 on between 60 frames into the race and the race's end: a write tap counted 0 on a
  finished reverse race, a finished normal race, a pit stop in each direction, a coin during a reverse race (§5), and 0 up to
  the last count before the time-out on a timed-out reverse race (`out/p32/gates/same/x/rows.txt`). **[V]**
- Who clears them: mode 0x15 (the results after the goal or the time-out) clears layer 0 in the frame the mode changes (194
  writes to the watched cells in that one frame, on main's set too); mode 0x0f before a select. **[V]** (`out/p32/gates/same/x/rows.txt`;
  the Phase 26 recon read the same)

**The font and its shadow.**

- The name's printer 0xff8926 writes, for each letter, the tile word (`[0x501434]` << 7) − 0x40 + 2·ch | `[0x50143c]` and that
  word + 1 on the row below: an 8 x 16 glyph, two characters. **[R]** (the boot listing; `vrtools/arcade/hudname.py`)
- **The dark edge is in the glyph tiles.** Each glyph uses three pixel values: 0 see-through, 1 the letter, 2 an outline one
  pixel wide all round the letter, corners included. **[V]** (characters 0x164/0x165 "R" and 0x14a/0x14b "E" decoded from
  `race400_chr.bin`)
- Colour 2 is black in each of the four palettes the font can reach; colour 1 is the letter's colour. **[V]** (`race400_pal.bin`:
  palette 0x02 (0, 184, 248) blue, 0x03 (248, 248, 248) white, 0x82 (248, 48, 0) red, 0x83 (248, 184, 0) orange; colour 2
  (0, 0, 0) in all four)
- So **REVERSE printed by the same printer has exactly the name's shadow, with no more code**. **[V]** (the snapshots, §6)

**Colours the font offers: four, no more.** A tile's palette is bits 7-14 of its word, and bits 7-13 are also part of the
character number (MAME `segaic24.cpp`, `tile_info`: character = word & 0x3fff, colour = (word >> 7) & 0xff). The font's two
copies are characters 0x100-0x17f and 0x180-0x1ff, so its glyphs can only be drawn in palettes 0x02, 0x82 (first copy) and 0x03,
0x83 (second copy): blue, red, white, orange. **[R]** + **[V]** (the palettes above). There is no other red or pink for these
characters, and no palette of theirs with a dark letter colour.

**A heavier shadow with the game's own means: not possible.** The idea was a second copy of the word behind the first, one pixel
down and right. It needs a tile layer that (a) is drawn under layer 0 and over the 3D picture, (b) can be offset by a pixel without
moving anything else, (c) can show the copy dark. None of the three other layers does:

| layer | what it is in a race | why it cannot carry the copy |
|---|---|---|
| 1 (0x702000) | the "window" partner of layer 0 | MAME draws it only where the window mask (0x70c000) selects it, and there layer 0 is not drawn: the two never overlap. **[R]** (`segaic24.cpp` `draw_rect`: `if(win) m = ~m`). **[V]**: the copy poked on layer 1 with its scroll words (shadow cells 0x501404 / 0x501406 → 0x70a002 / 0x70a00a) set to 0x1ff or 1 changed no pixel (`sh_a_crop.png`, `sh_b_crop.png`); the mask is all 0 in a race |
| 2 (0x704000) | the scrolling backdrop (772-827 different tile words; its scroll words change with the heading: 0x09e, 0x145, 0x1ed in three dumps) | a copy there would slide with the backdrop **[V]** (`dia_r` dumps) |
| 3 (0x706000) | layer 2's partner in the game's split mode (vscroll bit 13 set) | scrolled with layer 2 **[R]** + **[V]** |

And whatever the layer, the copy could only be drawn in the font's four bright palettes: one pixel off it would thicken the black
edge on two sides and nothing else; two pixels off, a line of the bright copy would show. There is no flashing-text mechanism to
borrow either without a per-frame routine (the game's own blinking texts are redrawn by per-frame handlers). **[R]**

So one shadow is built, the font's own. No alternative shadow variant exists (§7 for what one would take).

## 3. What was built

- **In a reverse race the word REVERSE on layer 0, rows 46-47, columns 52-58**: right under the name, its last letter under the
  name's last letter (column 58), in the game's EXPERT red (palette 0x82) on every course. Printed once at the race load by the
  same routine and printer as the name. **[V]** (§5)
- **Nothing in a normal race, nothing on the three originals** (they have no reverse variant). **[V]** (§5)
- `vrtools/arcade/hudname.py`: `hudname` grows from 116 to 160 bytes (34 instructions, every one pinned by
  `tests/test_hudname.py`) and gets a text `hudrev` ("REVERSE" and a NUL, 8 bytes) after its table `hudattr`: 171 bytes against
  119. How it knows: the loader's lookup `entry`, which `hudname` already calls, returns R0 = 1 exactly when it served the
  reverse variant's record (the direction flag 0x502294 set and the menu entry has a variant). `hudname` keeps that answer on the
  stack while it prints the name and, when it is 1, calls the printer a second time. **[R]** (`entry`'s and `hudname`'s exact
  listings are pinned)
- **One routine, no build switch.** The first round had a second style (the word in the name's own colour) and an environment
  variable `VR_HUD_REVERSE` choosing between them and "off"; both are gone since Pascal's third sentence and the review (§10).
  A test sets the variable and gets the same bytes.
- **`hudrev` is a layout key** (`directory_layout()["hudrev"]`, the image's last 8 bytes). The originals' reverse (branch
  `phase33-originals-reverse`, in flight, not this branch's work) replaces the HUD site's call on its side; it can print the
  word from this text and should leave the registers as `hudname`'s reverse path does (§4).
- **The directory image** grew 52 bytes: `end − loader` 6 895 → 6 947 (the same after the rebase). The test bound
  (`tests/test_directory.py`, `tests/test_hudname.py`) was 6 900: **raised deliberately to 7 000** (53 bytes left). The tables
  stored after the image moved +0x30 (the first tile table 0x27b370 → 0x27b3a0). **[V]** (`directory_layout()`, the build reports
  of `out/p35play1` and `out/p32play2`)
- **ROM room after the moved tables.** On merged main (`out/p35play1`) the erased run after the tables is 1 696 bytes at 0x28f1d0,
  up to Phase 31's reserved colour block (0x28f870-0x28f96f); in this build (`out/p32play2`) it is 1 648 bytes at 0x28f200, up to
  the same block. **[V]** (the two program ROMs read). (Before Phases 29 and 31: 1 952 at 0x28f1d0 on `out/p28play2`, Phase 27b's
  figure.) Not used by this phase: the code lives in the image.
- **ROMs changed against main's set** (`out/p32/gates/romcmp_main35_play2.out`, `out/p35play1` against `out/p32play2`): the two
  program ROM halves (18 093 + 13 214 bytes: the image from `hudname` on, the tables moved +0x30 and the pointers to them) and 13
  bytes in the two data ROM halves (pointers to the moved tables). The other 34 files are identical, the boot ROM among them
  (the site 0xff4799 still calls `hudname` at the same address 0x27b2f0) and the polygon and TGP ROMs. The two build reports
  are the same text but for addresses. **[V]**
- Tools: `vrtools/mame/lua/hudrows_log.lua` (rows 44-47 at keyed moments, a write tap on those rows from column 19, a coin during
  a race), `vrtools/mame/lua/tile_dump.lua` (the whole tile RAM at given frames after the race load),
  `runner.parse_hudrows_log`.

## 4. Registers and flags (as `hudname.py`'s docstring argues it)

The site 0xff4799 (once at the race load, in the HUD entity's first handler) was `jsr printer`; it is `jsr hudname` since Phase 26.
The printer writes R0-R3 and R8, pushes nothing, and reads no flag before setting them.

| | what `hudname` writes | who reads it next |
|---|---|---|
| an original (the record's `race` 0) | nothing changed in this phase: R0, R1, R8 restored, `jmp printer` | as the game |
| a normal race on a converted course | R3 := `entry`'s answer (0), pushed over the saved `[0x501434]`; after the name's print popped back into R3 (0, as the printer left it), `cmp.w #0, R3`, branch to the end: the saved word popped into R2 and written back. At the `rsr` R0, R1, R2, R3, R8 and `[0x501434]` hold what they held before this phase; the stack is balanced (two pushes, two pops) | only the flags differ (`cmp.w`'s instead of the printer's `tb`'s): no flag is read before `test.b` at 0xff47c3 sets them (0xff479f..0xff47c3: three moves, `jsr FF9436`, whose first instructions are `pushm` and moves) **[R]** |
| a reverse race | the same, then `[0x501434]` := 0x82, R1 := R1 + 0xF2, R0 := `hudrev`, the printer; then the same end | R0 (past the text's NUL) is written at 0xff47b6 and R1 (row 46, column 59) at 0xff47af before any read; R3 is 0 and R8 `[0x50143c]` as after any print; R2 is the restored word, read by nothing before the entity loop writes it (0xfe1c25); `[0x501434]` is the game's value again (the HUD's per-frame code rewrites it from the next frame on anyway) **[R]** |

The exact listing is pinned by `tests/test_hudname.py` (`test_hudname_prints_the_name_right_aligned_in_the_levels_colour`,
`test_hudname_prints_reverse_under_the_name_in_a_reverse_race`). The independent review read the routine from the built set and
found it correct on every path. That the game then behaves the same is measured in §5.

## 5. The gates

Every row is a test of the final invocation (§9) unless it names a script; the tests named are in
`tests/test_hudreverse_build.py` unless another file is named.

| gate | evidence | result |
|---|---|---|
| tests first, red then green | first round: `tests/test_hudname.py` run before the code (3 failed); the MAME tests of the reverse race run on a build without the word (3 failed, 4 passed, `out/p32/t_build_red.log`). The fix wave's new tests (the manual transmission, the reverse pit stop, the coin, the two against main's set) were written after the code they read and were not seen red; the manual-transmission and coin cases were probed by a script first (`out/p32/fw/probe.py`) | **[V]** for the first round |
| the word in a reverse race, on a blue-, an orange- and a red-named course | `test_a_reverse_race_shows_reverse_under_the_name[3, 4, 5]` (Alpine, Amazon Falls, Diablo Canyon): the flag 1 at the load; rows 44-45 the name in its level's colour; rows 46-47 columns 52-58 REVERSE in 0xC100 (red), row 47's words row 46's + 1; the rest of rows 46-47 from column 19 blank; printed at the load, the same 60 frames into the race | **[V]** §9 |
| the manual transmission | `test_the_word_with_the_manual_transmission`: Alpine in reverse with START held at the course lock: the gear's tiles on rows 44-46 inside columns 13-18, the name and the word as in the automatic run, the rest from column 19 blank | **[V]** §9 |
| a normal race and the originals: no word | `test_a_normal_race_shows_no_word[0, 1, 2, 5]`: rows 46-47 blank from column 19 at the load and in the race | **[V]** §9 |
| a normal race and the three originals: the tile RAM byte-identical to main's set at the same frames | `test_a_normal_race_draws_mains_tiles[0, 1, 2, 5]`: the whole tile RAM 0x700000-0x70ffff (four layers, scroll words, window masks) 8, 60, 300, 400, 700, 1 200, 1 800 and 2 200 frames after the race load, on `out/p35play1` (main add9799) and on the session's set, Big Forest, Bay Bridge, Acropolis and Diablo Canyon (normal): the load on the same frame, the eight dumps identical. (First round, by the script `out/p32/gates/tiles.py` against `out/p28play2` and `out/p32play1`: identical, `tiles.out`.) | **[V]** §9 |
| the same pictures | script only: `out/p32/look/make.py` → `make.out`: the normal race's snapshots on Diablo Canyon and Big Forest, `out/p32play2` against `out/p35play1`, three moments each | **[V]** 0 of 190 464 pixels differ in each of the six pairs |
| the race itself unchanged | `test_a_reverse_race_is_mains_pass_for_pass`: Diablo Canyon in reverse, 120 s, from the same battery RAM: `out/p35play1` driven by the autopilot with its wheel and pedal recorded each frame (`input_tape.lua`), the session's set fed that tape; the tapes equal; the game's state at the end of every logic pass (`pass_state.lua`: the clock, 16 cars' x, z, road point, speed, lap, and the frame the pass ends in) identical over the whole run (3 314 passes, 5 300 tape lines); the flag 1 in both; main's rows 46-47 blank, the set's REVERSE. (First round, by the script `out/p32/gates/same.py` against `out/p28play2`: 3 314 passes identical, `same.out`.) | **[V]** §9 |
| the frame rate | `tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate[entry_5]` and `[entry_5_reverse]` (Diablo Canyon, 150 s each): the render rate 28-29 from the green, the overrun counter 0 → 0, no skipped list; the worst V60 busy time 12 403 us (normal) and 12 849 us (reverse), both in frame 1 607, the pass after the load (the bound, two vblanks, is 34 770 us) (`rate_summary.txt` under the tests' base directory) | **[V]** §9 |
| the word through the whole race | `test_the_word_stays_to_the_goal_and_goes_with_the_race`: Metropolis reverse, one lap to the goal: the word at the load, 60 frames in, every 500th frame and at the goal (mode 0x1a), the cells the same each time, 0 writes to them in between | **[V]** §9 |
| no stale word | the same run goes on through the results (modes 0x15-0x1d), the name entry (0x1e: a reverse race has its own best times since Phase 27), the attract (0x02, 0x03), a coin and the next select (0x0f, 0x10) into a normal race on Metropolis: rows 46-47 are blank from column 19 on every logged frame of the results (mode 0x15's clear), and on every logged frame of every later mode none of the word's 14 cells holds its tile word (the name entry, the attract and the select draw their own tiles on those rows); `test_the_next_normal_race_shows_no_stale_word`: the second race shows the name and blank rows 46-47 at its load, in the race, every 500th frame and at its goal | **[V]** §9 |
| a pit stop, normal direction | `test_a_pit_stop_writes_none_of_the_cells`: a lap through Metropolis's pit lane with a stop: 0 writes to rows 44-47 from column 19, the logged rows the same before, during and after the stop | **[V]** §9 |
| a pit stop in a reverse race, the word on screen | `test_the_word_stays_through_a_pit_stop_in_a_reverse_race`: the same lane in reverse (the normal run's trajectory read backwards, as `tests/test_pit_build.py` drives it): a stop of 300 frames or more; the name and the word on their cells before, during and after it, nothing else on rows 44-47 from column 19, 0 writes to those cells. "Pit messages intact" is shown this far: the game wrote nothing into the word's cells during the stop, so no tile text of the game's is under the word; what the game shows during a stop was not itself compared with main's; one snapshot from inside the stop shows PIT WORK across the middle of the screen and the word in its place (`out/p32/look/full/reverse_metropolis_pit_stop.png`) | **[V]** §9 |
| a coin during a reverse race | `test_a_coin_during_a_reverse_race_leaves_the_word`: Diablo Canyon in reverse, Coin 1 pressed 300 frames after the race line: the rows the same at the next 500th frame, 0 writes | **[V]** §9 |
| the directory image's bound | 6 947 against a bound raised from 6 900 to 7 000 (`tests/test_directory.py`; `tests/test_hudname.py` pins 6 947) | **[V]** §9 |
| the modules whose routines sit before `hudname` in the image | `tests/test_dirscreen.py`, `tests/test_direction.py`, `tests/test_directory.py` in the final invocation. (First round, before the rebase: those and `tests/test_ranking.py`, `tests/test_select.py`: 99 passed.) | **[V]** §9 |
| the first round's "off is main" | `out/p32/gates/romcmp_main_off.out`: the first round's build with the word switched off was `out/p28play2` byte for byte, all 38 ROM files. The switch is gone; after the rebase the corresponding fact is §3's ROM comparison (only the program ROM and 13 pointer bytes differ from `out/p35play1`) | **[V]** (first round) |
| no ROM or game data in the repository | the commits hold code, tests and documents; `out/` is git-ignored | **[V]** (`git show --stat`) |

## 6. Snapshots and the playtest set

- `out/p32/look/` (`NOTE.txt` explains every file): `full/` whole screens (496 x 384, x3 nearest neighbour, saved 4:3 at
  1 440 x 1 080), `crop/` the bottom-right corner x6, `contact_sheet.png`: reverse races on Alpine (blue), Amazon Falls (orange)
  and Diablo Canyon (red), three moments each, and normal races on Diablo Canyon and Big Forest on this set and on main's
  (`out/p32play2`, `out/p35play1`). `out/p32/look/v1/` keeps the first round's pictures (both styles, `out/p32play1` against
  `out/p28play2`): the only build that existed when Pascal was shown stills.
- What the pictures show **[V]**: the word sits on the screen's last two tile rows, its outline's bottom line on the picture's last
  line (all of it visible in MAME); name and word touch, their outlines merging into one black line (the font has no spare line
  between rows); the letters stay readable over the 3D course map where the two cross, as the name does.
- **The playtest set is `out/p32play2`** (built by `python -m vrtools build` from the rebased tree at the fix wave's code), its
  launcher `out/rec165/launch.sh` (rec163's launcher with the directory and the set changed; `start/` copied from rec163; `inp/`
  empty); `out/rec165/launch-p32play1.sh` still starts the first round's set. Not launched by the builder.
- **`out/p32play2` against `out/p32play1`** (`out/p32/gates/romcmp_play1_play2.out`): 12 ROM files differ: the two program ROM
  halves, 6 bytes in the two data ROM halves and the eight polygon ROM halves. That is the rebase: `out/p28play2` against
  `out/p35play1` (main before and after Phases 29 and 31, `romcmp_main28_main35.out`) differs in the same 12 files, with the same
  byte counts in each. The dropped style and switch change no byte (the default build was the red routine already; `hudname` is
  the same 160 bytes at the same address). **[V]**

## 7. What a heavier shadow or a neon glow would take (not built)

Both need glyphs the game does not have, drawn at build time and uploaded at the race load, as the COURSE DIRECTION screen's
arrows are (`dirgfx.py`):

- **Tiles:** the whole word as one small picture, 8 or 9 columns x 2 rows (a drop shadow or a glow spills over the letters'
  cells), so 16-18 characters x 32 bytes = 512-576 bytes of data. **[R]** (the character format)
- **A palette of its own:** a character's palette is tied to its number (§2), so the tiles must sit in a 128-character block
  whose palette the project sets: a letter colour, a shadow colour (a drop shadow) or two or three steps of red towards the
  background (a glow), 16 words. **[R]**
- **Free characters during a race:** the Phase 26 recon found unreferenced runs in one race dump (0x2f2a-0x2fff, 0x0e95-0x0eff)
  and did not vet them against the other modes. **[?]**
- **Code:** an upload of the characters and the palette at the race load and a map blit in place of the second print, about
  60-100 bytes; the upload must fit the load's frame (the direction screen spread its drawing over six logic frames). **[?]**
- **Room:** 1 648 bytes are free at 0x28f200 in this build, up to Phase 31's colour block at 0x28f870 **[V]** (§3); the data block before 0x2c0000 had about 2 200 bytes left
  at Phase 26 stage 3 (5 968 of 8 192 used; not rechecked since) **[R]**.
- A glow over the moving 3D picture is a fixed set of colours, not a blend: it would look like a red halo with hard steps, on any
  background. **[R]** (the tile layers have no transparency levels)

## 8. Not verified

- **Pascal has not driven it.** They saw three stills of the first round's build and said "Yes all your recommendation" (§1).
- **Real hardware and a real monitor.** The word's bottom line is the picture's last line; a CRT's overscan may hide part of rows
  46-47 (the SPEED figures' feet are on row 46 too). MAME shows all of it. **[?]**
- **The game's variant with `[0x40dc8c]` != 0** (what the project's documents call Grand Prix or linked play; 4 laps, its own
  time and car tables). **Read:** the direction flag 0x502294 becomes 1 in one place only, the direction screen's lock
  (`dirsel`); `dirlock` opens that screen only when `[0x40dc8c]` is 0 (its first test) and the entry has a variant; `dirclear`
  zeroes the flag at every select screen's start, `bankdemo` at the attract's and the linked loads; the loader then writes the
  flag back as `entry`'s answer, which is 0 when the flag was 0. So with `[0x40dc8c]` != 0 no reverse record is served and
  `hudname` takes the normal path: no word. **[R]** **Run:** one 60-s run with `40dc8c=1` poked before the coin and the test
  driver's usual inputs (`out/p32/fw/gp/`): the game stayed on the select screen for the whole run (no race loaded; the driver
  does not know that flow), the flag 0 throughout. So nothing of that variant's race HUD was seen. **[?]**
- **The linked cabinet's layouts** (the slave's label site 0xff53ae..0xff53fa is not patched, as before). Not run. **[?]**
- **Cells from column 19 on rows 44-47 in states this phase did not provoke** (§2): measured blank in every run here, not proved
  for every text the game can print.
- **What the game shows during a pit stop** in a reverse race was not compared with main's picture of the same stop; the evidence
  is that it writes none of rows 44-47 from column 19 (§5).
- **The attract's whole cycle** was not watched: the attract after the reverse race was logged at its first frames (modes 0x02,
  0x03) and showed no word. **[V]** for the logged frames only.
- **The other four converted courses in reverse** (Alpine, Amazon Falls, Diablo Canyon and Metropolis are driven): the routine
  does not depend on the course; `tests/test_hudname_build.py` reads the name on every course.
- **The whole suite was not run** (3.5 h; the brief's instruction): §9 is what ran.
- **Frame time of the load.** The second print runs once, at the race load (seven letters: 14 tile words). The frame-rate tests
  measure from the pass after the course load's own; whether the HUD's first handler runs inside that measured stretch was not
  looked at, and main's figures for the same runs were not taken in this phase. **[?]**
- **The in-test set against the CLI's.** The two tests against main's set compare `out/p35play1` (built by the CLI) with the
  session's set (built by the tests' own `_seven`); that they agree byte for byte in the tile RAM and pass for pass is the result
  itself. `out/p32play2` (the CLI's build of this branch) was compared with `out/p35play1` ROM by ROM (§3) and in the
  snapshots (§6), not through those two tests.

## 9. The tests run

**The final invocation** (15 Nov 2026, at commit 0f522c7, from the worktree; `VR_ROMDIR` and `VR_SATURN_CUE` from `out/env.sh`,
`VR_MAME_JOBS=2`, `PYTHONPATH` the worktree, `VR_MAIN_SET=out/p35play1`, main's `build/`
linked into the worktree for `unidasm` during the run and removed after it):

```
python -m pytest tests/test_hudname.py tests/test_hudname_build.py tests/test_hudreverse_build.py tests/test_directory.py \
  tests/test_dirscreen.py tests/test_direction.py \
  "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate[entry_5]" \
  "tests/test_frame_rate.py::test_every_course_holds_the_arcade_rate[entry_5_reverse]" \
  -o addopts="" -p no:cacheprovider --basetemp out/p32/t_fw2 -q -rs
```

**Result: 115 passed in 1729.30s (0:28:49)**, none skipped, none failed (`out/p32/t_fw2.log`), so there is no failure to compare
with `out/p27/full_failed.txt`. After it only documents changed.

Before it, in the fix wave:

- The same invocation at commit 3214de1 (`out/p32/t_fw_first.log`): 114 passed, 1 failed in 1 752.92 s. The failure was the new
  reverse pit-stop test's own check that a lap line follows the last frame of the pit handler: in that run a second stop was under
  way when the 180 s ended. The test now reads the run's first whole stop (5 180-5 876 in that run), checked against that run's
  kept logs before the second run; commit 0f522c7 is that one change. No product code changed between the two runs.

The first round (before the rebase, the first build; `out/p32/t_final2.log` and the logs beside it):

- 62 passed in 1 567.52 s for `tests/test_hudname.py tests/test_hudname_build.py tests/test_hudreverse_build.py
  tests/test_directory.py` and the two frame-rate entries; before it one run with 61 passed, 1 failed (the first stale-word
  assertion asked for blank cells in modes where the attract and the select draw their own tiles).
- Red: `tests/test_hudname.py` before the code (3 failed); the reverse-race MAME tests on a build without the word: 3 failed, 4
  passed in 863 s (`out/p32/t_build_red.log`).
- 99 passed in 971.86 s for `tests/test_hudname.py tests/test_directory.py tests/test_dirscreen.py tests/test_direction.py
  tests/test_ranking.py tests/test_select.py`.
- The script gates against `out/p28play2`: `out/p32/gates/tiles.out`, `same.out` (IDENTICAL), `romcmp_main_off.out` (IDENTICAL).

The whole suite was not run. `tests/test_ranking.py` and `tests/test_select.py` were not run after the rebase.

## 10. The review and the fix wave

An independent review of the first round (commits 141fb74 and 9c151b4 before the rebase) gave: ready with fixes, no Critical;
the V60 routine read correct on every path from the built set. What was done for each finding:

| finding | what was done |
|---|---|
| step 0: main moved (Phases 29 and 31, add9799) | rebased; one conflict in `docs/follow-ups.md`, both sections kept, this phase's after Phase 31's |
| I1: the record said "awaiting Pascal's judgement / not seen by them" | replaced everywhere with the three sentences and "they have not driven this set" (this document, `docs/follow-ups.md`, `docs/formats/model1-course-tables.md` §19, `hudname.py`, the three test files); a Phase 32 entry in `docs/deviations.md`; the inference "Pascal asked for red" removed (§1 says what the red rests on); the truncated quote in `tests/test_hudname.py` now whole; "inside the 6 900-byte bound" corrected to 7 000 |
| I2: the gates compared against main before Phases 29 and 31 | redone against `out/p35play1` (main add9799, the lead's build; its log ended "build 0" before use), as tests (I3); each figure says which main (the note at the top, §5) |
| I3: red accepted: drop the other style and the switch; pin the listing; gates as tests | `VR_HUD_REVERSE`, `reverse_style`, the `level` style and the hand copy of main's routine are gone: one routine; its 34 instructions are pinned by `tests/test_hudname.py` and a test shows the variable changes nothing. The tile-RAM comparison and the pass-for-pass reverse race are tests against main's set (they skip when it is absent: `VR_MAIN_SET`, or `out/p35play1` under the repository). Still script-only: the snapshot pixel comparison (§5) and the ROM-by-ROM comparisons (§3, §6) |
| M1: "the game writes columns 2-11 only" was a measurement, not general | corrected (§2, `hudname.py`, the formats note): `[0x501936]` is the latched transmission; with it set the gear's maps are on rows 44-46, columns 14-17. The tests read rows 44-47 from column 19 (was 12), the write tap likewise, and a reverse race with the manual transmission is driven |
| M2: with the word on screen: a reverse pit stop, a coin; Grand Prix | two tests (§5); the `[0x40dc8c]` variant read from the code and one run attempted (§8) |
| M3: the build switch was a hidden input that broke the static suite when exported | removed with I3 |
| M5 / M6: figures stale after the rebase | restated from the rebased builds (§3: the free run, the ROM differences; §6: the set comparison) |
| heads-up: the originals' reverse will print the word through its own routine | `hudrev` documented as a stable layout key (§3, `hudname.py`, the formats note, a test's docstring) |

Not disputed: none of the findings. Not done: nothing was added for the originals' reverse (another branch's work).
