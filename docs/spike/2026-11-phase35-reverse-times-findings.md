# Phase 35 findings: best times for reverse races on the three originals (17 Nov 2026)

Branch `phase35-reverse-times` (from main 47460b0; the recon's commits 678e64c, e55fe1d), local commits only, not merged.
Recon and gate: `docs/spike/2026-11-phase35-reverse-times-recon.md`. Formats: `docs/formats/model1-course-tables.md` §23.

Marks: **[V]** verified by a headless MAME 0.289 run of a named test or a byte read; **[R]** read in the code; **[?]** not
established.

## 0. The owner's words

- 15 Nov 2026, to a list including "best times three per table on all ten reverse courses": **"Yes all your recommendation"**.
- 16 Nov 2026, to five recommendations (1: four times a table on all ten; 2: an original's reverse page titled with the level
  word, "BEGINNER REVERSE RANKING", "MEDIUM REVERSE RANKING", "EXPERT REVERSE RANKING"; 3: each original's reverse page straight
  after its own normal ranking page; 4: starting times by the seven's rule, Big Forest and Bay Bridge 4'00 to 4'15, Acropolis
  5'00 to 5'15, five-second steps, names as the seven's rule gives; 5: the same release as the originals in reverse) and the
  condition that four entries depends on a check of every test-menu page (passed: recon §11): **"yes to all"**.
- 17 Nov 2026, asked whether to release v0.3 now without reverse best times on the originals: **"Release with the original
  best time"**. Then **"Version 0.3"**.

None of this is a word to merge. **Built for the release; not seen or driven by Pascal**, nor by any human.

## 1. What was built

- **Layout B4** (recon §2): three 4-entry tables, their slots and a tag, in battery RAM that the recon's gate found neither read
  nor written in 25 runs through every test-menu page, the backup clear, the races, the name entry, the cold boot and 1 250 s
  of attract. Nothing of v0.2.1's layout moves.
- **The setter** sends a reverse race's ranking id 0..2 to 17..19 (out of line, after its last `rsr`); a normal race and the
  attract's entry are unchanged. **Phase 33's `rankgate3` is gone**: the race end's 16 boot bytes at 0xfc40ce are the
  arcade's own again (as on every build before Phase 33), so a reverse race on an original goes through the game's own insert
  and name entry into its own table, as on the seven.
- **`originit`** (`revinit`'s loop for k = 7..9, then the tag ORG4) runs from `slot_init` (a battery RAM without the magic, and
  the test mode's BACKUP RAM CLEAR) and from `revtag` when ORG4 is missing (a battery RAM saved by v0.2.1 or v0.2).
- **Attract**: each original's reverse id stands straight after the original in its group; `revtitle` prints the game's own
  level word (boot ROM strings) in the name's place. Phase 27b's `raceend` is unchanged; three more position bytes.
- **Defaults** (`original_reverse_defaults`, at build time): the first four of each original's normal table as the stock
  initialiser writes it.

## 2. Where every new byte lives

| What | Where | Bytes |
|---|---|---|
| Bay Bridge's reverse table (ranking id 0 → 17) | battery `0x40e6e4..0x40e743` (run `0x40e6e2..0x40e7ff`) | 96 |
| Acropolis's (id 1 → 18) | battery `0x40e744..0x40e7a3` | 96 |
| Big Forest's (id 2 → 19) | battery `0x40f010..0x40f06f` (run `0x40f00c..0x40f0ff`) | 96 |
| their slot words | battery `0x40fc40..0x40fc4b` (the ten-word slot array's first three words, never used: ids 0..2 keep `0x40e6c0..`) | 12 |
| tag "ORG4" | battery `0x40fdb8..0x40fdbb` (run `0x40fdb5..0x40fdff`) | 4 |
| arrays by id 17 → 20 (bases, slots, titles), `firsts` and `revtitle`'s five arrays 7 → 10, `positions` 17 → 20 | program ROM, inside the directory image (ranking image at 0x27a296) | +111 |
| setter +9, `slot_init` +6 (the `jsr originit`), `revtag` +20 (the second check), `originit` 128 | the same image | +163 |
| `rankgate3` removed | the originals' block 0x28f7d0 (Phase 33's reservation, 160 bytes): `hudorig` alone, 96 bytes at its start; 64 free | −50 |
| boot ROM 0xfc40ce..0xfc40dd | the arcade's 16 bytes again | 0 |

The directory image: **6 947 → 7 221 bytes** (`tests/test_directory.py`'s bound 7 000 → 7 300, the reason in the test). As in
every phase that grew it, what follows the image in the program ROM moves up by as much; `check_reserved_blocks` passes on the
build (the image ends at 0x27b4ad; Phase 33's picture block 0x28f5d0, its originals' block 0x28f7d0, Phase 31's 0x28f870..
0x28f96f, the start gantry's 0x28f970.. are where they were). Against main's set (a build of 47460b0), six of the 38 members
differ (the boot, data and program ROM pairs), byte by byte [V `out/p35play2` against `out/p35/b35/main`; the review's
count agrees]: the boot ROM: 0xfc40ce..0xfc40dd back to the arcade's 16 bytes (`rankgate3` removed), and 43 short spans, every one an address
or PC-relative displacement of the project's own routines or data in the program ROM, moved with the longer image (28 by
+0x112, 7 by +0x7e, one each by +0x78, +0x92 and +0x6f, the HUD site's `jsr hudorig` by -0x32 as `hudorig` moved to its
block's start, 4 PC-relative displacements); the data ROM pair mpr-14880/14881: 20 bytes at data-ROM offsets
0xde80c..0xde845 (CPU 0x10de80c..), course-header pointer words into the program ROM, each +0x110 (the tables they point at
moved with the image); the program ROM pair: the image and everything after it. The polygon, copro data and TGP program ROMs
are identical to main's. Nothing is written in the boot ROM's erased run (0xfdc844..). (Written as "nothing in the data ROM" in
the first version of these findings: wrong, corrected after the review.)

## 3. How it was built

Taken over half-way: the previous builder had written `tests/test_reverse_times.py` and the product changes and stopped before
editing the existing tests; this session read that work, completed the existing tests' updates (`test_reverse_ranking.py`,
`test_originals_reverse.py`: `rankgate3`'s routine test reduced to `hudorig`, its "records nothing" test removed, the byte
comparison with the set before Phase 33 allowing the ranking image's groups and positions; `test_ranking.py`: 20 positions;
`test_directory.py`: the bound), ran the static tests (all green), then one development run of the new module in MAME, which
found four faults in the TESTS' expectations and none in the product (§4.3). Synthetic battery RAM only: every image is made in
the test from a battery RAM this set saved fresh (`synthetic_v021`, `synthetic_v02`); no dump of anyone's machine is read or
committed.

## 4. Evidence (development run, `out/p35/dev1`, 17 Nov; headless MAME 0.289, `VR_MAME_JOBS=2`)

### 4.1 Boots [V `test_a_fresh_battery_ram_gets_the_three_tables`, `test_a_v0_2_1_battery_ram_keeps_every_saved_byte`, `test_a_v0_2_battery_ram_gets_all_ten_reverse_tables`, `test_a_second_boot_writes_no_table` x2]

- Fresh battery RAM: the three tables, ranks 1..4, 0x1e00 / 0x2580 / 0x1e00 (4'00, 5'00, 4'00) stepping 0xa0 (5 s), +8 = 0,
  +0xc = -1, YU., RNS, TKG, NAG; slots on their bases; ORG4; written by `originit` alone, twice on the S-RAM check's frame
  (from `revtag`, then from `slot_init`), as `revinit` is on main. REV4 and the magic as on main.
- **Upgrade from v0.2.1** (synthetic: every one of the ten normal tables with two entries of its own, the seven reverse tables
  with four entries each, every time, view, player word and name distinct, the slots on different entries, one on a fourth):
  after the first boot and its attract **no byte of the ten normal tables, their slots, the magic, the ranking id, the seven
  reverse tables, their slots or REV4 was written, and each is the byte it was**; the three new tables, slots and ORG4 were
  written once, by `originit` from `revtag`; neither `revinit` nor the stock initialiser ran; everything else written is the
  game's record, the bookkeeping and the attract pages' own cells.
- Upgrade from v0.2 (no reverse block): the normal block kept and unwritten; all ten reverse tables made.
- Second boot (after fresh, after the upgrade): no table, slot or tag written.

### 4.2 Races [V `test_a_reverse_race_on_an_original_records_in_its_own_table` x3, `..._lands_third`, `..._slower_than_the_fourth_records_nothing`, `test_a_reverse_record_on_one_of_the_seven_after_it_keeps_the_rest`, `test_the_backup_clear_resets_all_twenty_tables`]

One-lap races, the clock held (`race_end.lua`), on the upgraded v0.2.1 image:

| Race | Time | After the finish | Table after | First page after |
|---|---|---|---|---|
| Big Forest reverse | 1 812 (56.62 s) | record, name entry (mode 0x1e) | 0'56"62, YU. 4'00, RNS 4'05, TKG 4'10 | 19 BEGINNER REVERSE |
| Bay Bridge reverse | 1 864 (58.25 s) | the same | 0'58"25, then 4'00 .. 4'10 | 17 MEDIUM REVERSE |
| Acropolis reverse | 2 273 (71.03 s) | the same | 1'11"03, then 5'00 .. 5'10 | 18 EXPERT REVERSE |
| Big Forest reverse, table preset round its time | 1 812 | record | AAA t-64, BBB t-32, the race, CCC t+32 | 19 |
| the same, preset four faster | 1 812 | no record, no name entry | as preset | 19 (every finished race jumps) |
| Amazon Falls reverse after the Big Forest record | 1 683 | record | the race, then the synthetic three first entries whole | its reverse page |

In each record, of every table, slot and tag the race wrote only its own reverse table's entries (+4..+0x17 of the four:
the time bubbles from fourth to first) and its slot, plus the ranking id at the course select; every other saved byte of the
image unwritten and unchanged, the two other originals' reverse tables too. The Amazon Falls race wrote only its own v0.2.1
table and slot, the three originals' tables (Big Forest's with its record) untouched.

**Backup clear** (the test mode's BACKUP RAM CLEAR on that battery RAM, as the standing test drives it): on its frame
(2 603) the ten normal tables come back to this set's fresh defaults, the seven reverse tables to `revinit`'s and the three
new ones to `originit`'s, with all slots and tags. The three are written by `originit` (from `slot_init`, which the stock
clear calls): the clear's own code writes none of their bytes, as the recon's gate found. The stock clear leaves the +0xc
word of the arcade's own three tables as it found it (the synthetic image's player words survived): the arcade's behaviour,
not touched by this or any phase.

### 4.3 Normal races and the attract against main [V `test_a_normal_race_records_as_on_main` x10, `test_the_attract_shows_the_three_new_pages_in_their_places`]

Main's set: a build of 47460b0 from a clean `git archive` (`out/p35/b35/main`). Since the fix wave these comparisons are
release records, opt-in: they run when `VR_P35_MAIN_SET` names such a set and skip with that reason otherwise (after the merge
main is no longer the set before this phase). A normal one-lap race on each of the ten
courses, on the upgraded image, main's set driven by the autopilot and its wheel and pedal taped, this set fed the tape:

- the record goes into the course's own normal table (an original's: the arcade's own table) and its slot; no reverse
  table, slot or tag written; the first page after the game is the course's normal table;
- **pass for pass identical** (the game's state at the end of every logic pass: clock, sixteen cars' x, z, road point,
  speed, lap) from the boot to the attract's second ranking page after the race, or to the run's end where neither log has a
  whole second page (5 527 to 6 761 passes; development run, nine courses: Bay Bridge's pair is in the final run only); battery writes
  from the race load to the first page's end write for write (frame, address, mask; data but the group counters), the PC
  equal wherever it is in the boot ROM; the saved tables equal at the end.
- The development run found the test's window too long: after a normal Big Forest race the second page was Acropolis's new
  reverse table (one screen, 396 frames) on this set and Alpine's (four screens, 1 584) on main's, and the next scene loaded
  1 188 frames sooner. That is the inserted page, by Pascal's choice 3; the test now compares up to that page. Three more
  test faults: the race log's select handlers (in the moved image) compared raw; group 0's counter byte logged in the other
  lane; Bay Bridge's normal race on the ROM's line 0, on which the autopilot finished on neither set (Phase 27b's recipe, the
  Saturn track's centreline with lookahead 3, finishes: precheck on the play set, then the final run).
- **Attract with no game** (1 450 s on a fresh battery RAM, this set and main's): every member of each group in its group's
  order, each original's reverse page straight after its own: Bay Bridge `0, 17, 4, 11, 7, 14, 8, 15, 9, 16`, Acropolis
  `1, 18, 5, 12, 6, 13`, Big Forest `2, 19, 3, 10`; each new page one screen of four rows, rows five and six empty, under
  its level-word title; the direction flag 0 throughout; against main's, each group's pages without the three new ones are
  main's pages in main's order with main's table, screens, length, title and rows, and up to the first new page's setter call
  (the page at frame 7 302) the two attracts are the same frame for frame.

## 5. Looks (stills, play set)

`out/p35/look/` (1440x1080, the game's 496x384 resized nearest-neighbour, as Phase 33's): `medium_reverse_ranking_bay_bridge`,
`expert_reverse_ranking_acropolis`, `beginner_reverse_ranking_big_forest` (an attract with no game: the level word and REVERSE
in red, RANKING in white, four rows 4'00 .. 4'15 / 5'00 .. 5'15, YU. RNS TKG NAG), `name_entry_after_big_forest_reverse`
("CONGRATULATIONS! ... Your Ranking is 1st", Total Time 00'56"62), `attract_first_page_after_big_forest_reverse` (BEGINNER
REVERSE RANKING with 0'56"62 first, the name blank: the autopilot enters no letter). Script `out/p35/look/stills.py`.

## 6. The final invocation (17 Nov, on 010de8c; log `out/p35/final.log`)

One invocation, building the set from the tree, `VR_MAME_JOBS=2`, `-s -p no:cacheprovider -rfEs`, with main's `build/` (the
disassembler) and `out/` (the frozen sets the tests look for under the tree: `out/p26play6`, `out/p27play1`, `out/p35play1`,
main's set `out/p35/b35/main`) linked into the worktree while it ran and removed after; `VR_MAIN_SET` not set (so
`test_hudreverse_build.py` keeps its frozen `out/p35play1`):
`tests/test_ranking.py tests/test_reverse_ranking.py tests/test_originals_reverse.py tests/test_directory.py
tests/test_dirscreen_build.py tests/test_hudreverse_build.py tests/test_reverse_times.py` and from `tests/test_frame_rate.py`
the three originals in reverse (`test_every_course_holds_the_arcade_rate`, `test_no_list_is_skipped_where_the_games_budget_cut`,
`test_the_worst_known_frames_hold_the_arcade_rate[big_forest_reverse_line1, big_forest_reverse_pit, acropolis_reverse_pit]`)
and `test_the_attract_holds_the_arcade_rate`.

**254 collected: 252 passed, 2 failed, 0 skipped**, in 1 h 50 min. Neither failure is a name of
`out/p27/full_failed.txt` (whose fifteen names are all in modules not run here).

1. `tests/test_ranking.py::test_attract_and_race_end_rankings_name_their_course`: **the test's**, not the product's. A MAME
   test this session had not run before the final invocation: it checked each attract page's table and title with Phase
   27's lists (ids 0..16), so the new page 17 (Bay Bridge's second member now) had no table in its list. Corrected in f3b5e93
   (ORIG_REVERSE_TABLES and the level word; Bay Bridge's and Acropolis's second members are 17 and 18) and checked on the
   invocation's saved attract log (pages 0, 2, 17, 1, 4, 18 all pass). Rerun alone (`out/p35/final2.log`), its second half
   failed the same way: after an Amazon Falls race that runs out of time (which never reaches the setter) it expected
   Amazon Falls's page, which was only the member at position 1 of Bay Bridge's group; that member is 17 now, and 17 came.
   Corrected to expect the group's next member under its own title, and rerun alone (`out/p35/final3.log`): **passed**.
2. `tests/test_originals_reverse.py::test_an_original_races_in_reverse_on_its_variant[1]` (Phase 33's standing test, Bay Bridge
   in reverse for 150 s under the autopilot, untaped, from no battery RAM): 3 clock extensions against its floor of 4; the
   clock ran out at frame 8 100 after the car crawled from road point 95 to 116 over 2 000 frames on its second lap.
   **Reproducible**, and the same test on main's tree passes (5 extensions) [V `out/p35/bay_p35.log`, `bay_main.log`]. Traced:
   - **the game is the same**: from the same battery RAM, and again from no battery RAM, main's set driven by the autopilot
     with its inputs taped and this set fed that tape give the same game state at the end of every one of 4 177 logic passes
     (the whole 150 s) [V `out/p35/baysame/`];
   - nothing reads the three new tables or their slots in that race (read taps on every unused run: only `revtag`'s two reads
     of the tag at the boot) [V `out/p35/baysame/tap`];
   - **the autopilot's inputs differ**: driven by its own autopilot this set's wheel differs from main's at frame 2 854 (72
     against 51), and the passes from 2 856 on. On a battery RAM without the tag this set's boot does more work (`originit`
     twice on the S-RAM check's frame), so MAME's frame ends, where the autopilot samples the car, fall at another point
     inside some passes (at frame 446 an opponent's x and z are equal on both sets and its road point one apart). Phase 28's
     note on frame-end logs says the same. Here the different steering led into a stall in reverse on Bay Bridge (where
     Phase 33 already recorded the autopilot stalling after a put-back).
   **The review's runs** (`out/p35/review/runs/`) agree: on a battery RAM already tagged ORG4 this branch and main are byte
   for byte the same in the tape, race and field logs, 5 extensions each; on a battery RAM main saved (no ORG4: `originit`
   runs once) the inputs part at frame 3 583 and both still get 5.
   **Fix wave (9e417e6)**: Phase 33's race runs (`_race`, every original in both directions) now boot on the battery RAM an
   earlier 30-s attract boot of the same set made in the session (`_booted`, the one its pass-for-pass test already used),
   on which the boot initialises nothing, as on the set before. The floor is unchanged. Result in §9.

Frame rates (from `rate_summary.txt`): the three originals in reverse 28-29 a window, the overrun counter 0 -> 0, no list
skipped, worst busy 12 744 / 13 988 / 13 544 us, the record peaks 9 709 / 7 877 / 7 535; Big Forest reverse line 1 10 173 and
its pit lap 10 053, Acropolis's pit 7 638 (all under 10 500); the attract (300 s) 28-29, 16 scene loads at main's frames, worst
busy outside them 17 982 us (as main's).

## 7. Downgrade

[R] v0.2.1's `revtag` checks REV4 only and its `slot_init` writes ids 0..9's slots (ids 0..2 at `0x40e6c0..`) and its seven
reverse tables: on a battery RAM this set saved it finds REV4 and its seven tables as it left them and writes nothing of the
three tables, their slots (`0x40fc40..0x40fc4b`) or ORG4; its title routine sends a shown id of 17 or more (a byte this set may
have left at `0x40fc69`) to the data index's title, and its attract routine wraps a counter past its shorter group to the
group's first member. **How established: read in the code; not run on v0.2.1's set.** Partial evidence from the review
(`out/p35/review/runs/`): main's set (47460b0, the same ranking code as v0.2.1 for the seven) booted on a battery RAM this
set saved, then raced, wrote only the game's bookkeeping, the game's record, `0x40fc69` (the shown id) and `0x40fc6a` (an
attract counter): no table byte, nothing of the three new tables, their slots or ORG4.

## 8. Not verified

- **Any human drive or look**: Pascal has seen nothing of this phase (no stills sent from here).
- A name entered letter by letter (the autopilot enters none; the name entry's code is the game's, as on the seven).
- A race that runs out of time on an original in reverse (read: it never reaches the setter, as on the seven).
- Linked play and the linked Grand Prix (the flag 0 there: a normal race path) [R].
- The downgrade to v0.2.1 (read only, §7) and an upgrade from v0.2.1's own set (synthetic images only, by instruction).
- Real hardware: a real board's battery content in these runs is unknown (0xff on every battery RAM MAME made; the recon's
  gate covered every test-menu page in MAME).
- The whole suite (by instruction: the named modules, one invocation).

## 9. Fix wave after the review of 4611d91

The review: ready with fixes, nothing critical; no path writes a byte of v0.2.1's saved layout (every routine read in source and
in the built ROM; 7 148 battery RAMs saved before Phase 35 under `out/` scanned: all 0xff in the four runs used). Done:

1. Phase 33's race runs boot on a battery RAM an earlier boot of the same set made (§6 item 2; 9e417e6). Bay Bridge in
   reverse: 5 extensions, passed.
2. The ROM changes are stated exactly (§2, formats §23, the README): boot ROM and data ROM bytes change with the image, not
   only the program ROM.
3. The downgrade is stated as read in the code, with the review's partial evidence (§7).
4. The comparisons with the set before Phase 35 are opt-in release records (`VR_P35_MAIN_SET`).
5. The public README says "Upgrading from v0.2 or v0.2.1".

**One invocation** on 9e417e6 (`out/p35/fixfinal.log`; `VR_MAME_JOBS=2`, `VR_P35_MAIN_SET` = the build of 47460b0, main's
`build/` and `out/` linked while it ran and removed after): `tests/test_originals_reverse.py tests/test_reverse_times.py
tests/test_ranking.py tests/test_directory.py`: **128 passed, 0 failed, 0 skipped** in 1 h 15 min. No name of
`out/p27/full_failed.txt` among them. **No ROM byte changed** in the fix wave (no product code touched; the session's built
`vr.zip` has every member's CRC equal to `out/p35play2`'s): `out/p35play2` stays the set.
