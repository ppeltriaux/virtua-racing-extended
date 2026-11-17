# Phase 27: findings (a best-time table for reverse races)

The measured findings of Phase 27, `docs/superpowers/specs/2026-11-14-reverse-ranking-design.md` ("the design"): a reverse race
on one of the seven converted courses keeps its four best times in the battery RAM, with the name entry, and each reverse table
shows in the attract mode's ranking pages. Facts and numbers only. Plan: `docs/superpowers/plans/2026-11-14-phase27-reverse-ranking.md`
(five tasks); recon: `docs/spike/2026-11-phase27-reverse-ranking-recon.md` ("the recon"). The scripts, logs, builds and snapshots
quoted are git-ignored under `out/p27/` (one directory per task: `task1/` .. `task5/`, Task 3's fix round `task3fix/`; the
snapshots sent to Pascal under `look/`). The task reports and reviews are in `.superpowers/sdd/2026-11-14-phase27-reverse-ranking/`.

**Status: merged into main and pushed on 15 Nov 2026 on Pascal's "Merge update MD commit and push", given without a drive and while the whole suite was still running** (§13; the suite's result follows in a later commit). Pascal has driven nothing of this phase.
They were sent two snapshots of a reverse ranking page on 15 Nov and have not commented on them (§2.4). The final review's verdict:
ready for the owner's drive, with fixes to the record only (§13). The whole suite's result is still the session lead's to fill in (§10).

Words used below:
- **The direction flag**: the byte 0x502294, 1 while a reverse variant is loaded (Phase 26 stage 1); set only by the COURSE
  DIRECTION screen, cleared at every select screen's start and at the attract and linked course loads (stage 3).
- **A reverse table**: one of the seven 4-entry tables of this phase, one per converted course (entries 3..9). Its **ranking id**
  is its entry + 7 (10..16); a normal table's id is its entry (3..9) or an original's data index (0..2).
- **The setter**: the project's routine behind the boot ROM's 0xfc4208 (Phase 22r, 23b) that picks the table and slot for its
  three callers: the race's end (0xfc40e8), the name entry (0xfc422d) and the attract page (0xfc3c33, `attract` → `common`).
- **The cells**: the last entry's offset cell 0x40fdb0 and the row-count cell 0x40fdb4, written by every setter call.
- **Main**: the product code of commit e7c52ae (Phase 26 stage 4 with its fix wave). Its tested set is `out/p26play6`, which the
  public v0.2 export builds byte for byte; main's tip has since gained documents and tests only.
- **The session lead** ("the lead"): the agent that planned and dispatched the tasks and ruled during the build.

**Map:**
- §1 what was built;
- §2 the decisions and who made them; the lead's calls and rulings; what Pascal has and has not seen;
- §3 the eight proofs of the design's §5, each with its test;
- §4 the mechanism measured (a reverse race's record, the cells);
- §5 the reverse block at boot, on upgrade and at the backup clear;
- §6 ranks two to four, a slow time, ties, both directions;
- §7 a reverse race that finishes on another frame after a different boot (Task 3's fix round);
- §8 ROM room and sites;
- §9 the normal direction against main (Task 5 Step 1);
- §10 the pins and the suite;
- §11 the playtest set;
- §12 not verified;
- §13 status;
- §14 review items parked, open;
- §15 the follow-up: the attract's first page after a game (Phase 27b).

## 1. What was built

- **Seven reverse tables in the free battery RAM** (Task 1's addresses, Task 3's initialiser; `vrtools/arcade/ranking.py`):
  four entries of the game's 24 bytes each at 0x40ee80, 0x40eee0, 0x40ef40, 0x40efa0 (entries 3..6) and 0x40fc70, 0x40fcd0,
  0x40fd30 (entries 7..9); seven slot words from 0x40fd90; the tag "REV4" at 0x40fdac; the two cells. 709 of the 787 free bytes
  the recon confirmed; nothing else in the battery RAM is written by this phase (asserted, §4, §5). The S-RAM magic is unchanged.
- **The game's own insert, name entry and page run on the short tables** (Task 1; the recon's mechanism 1, the lead's L1): the
  setter adds 7 to the ranking id of an entry 3..9 at the race's end and at the name entry while the direction flag is set, and
  writes both cells on every call (0x228 / 6 for a 24-entry table, 0x48 / 4 for a reverse one); the insert's two `add.w #228`
  (0xfc40f9, 0xfc4184) read the offset cell in place; the page's end test (0xfc3ca1) and row count (0xfc3d8c) call `pagecmp` and
  `pagerows`, which read the row cell. Stage 3's `rankgate` is removed: 0xfc40ce is the original's again.
- **The reverse block made at boot under its own tag** (Task 3): `revinit` writes the seven tables (ranks 1..4, the course's
  normal table's four default times, +8 = 0, +0xc = −1, the game's first four default names YU., RNS, TKG, NAG), the slots and the
  tag. It runs from `slot_init` (the stock initialiser on a battery RAM without the magic; the test mode's backup clear) and from
  `revtag`, which the boot's S-RAM check calls first (0xfe69f0): a battery RAM saved by v0.2 (the magic, no tag) gets the reverse
  block alone, every saved time kept.
- **The reverse tables in the attract's ranking pages** (Task 3; Pascal's "1", the lead's L3, L4, L8): each reverse id follows its
  course's id in its host's group; a reverse page is one screen of four rows (396 frames) titled "<NAME> REVERSE RANKING", the name
  and REVERSE in the title's red (0x8300), RANKING in white (0x8200), by one shared routine `revtitle`.
- **Tests** (Tasks 1-4): `tests/test_reverse_ranking.py` (new; static and MAME), and changes to `tests/test_ranking.py`,
  `tests/test_dirscreen.py`, `tests/test_dirscreen_build.py`, `tests/test_directory.py`, `tests/test_hudname.py`, and (Task 5)
  `tests/test_reverse_build.py` (one pin's expectation brought up to the attract groups, §10). **Test harness**:
  `vrtools/mame/lua/race_end.lua` (VR_END_TABLE ranges, VR_END_READS, VR_END_TAP_AT, VR_END_NEXT, VR_END_NEXT_LINE, VR_END_PRESET,
  VR_END_SNAP; T, P, S lines), `vrtools/mame/lua/autopilot.lua` (`vr_autopilot_load`), `vrtools/mame/lua/ranking_attract.lua` (new).
  No product code outside `ranking.py`, `dirscreen.py` (`rankgate` removed) and `directory.py` (comments).
- **Commits:** bb580f2 (Task 1), dd82aac (Task 2), 6c1de14 and 2be1743 (Task 3 and its fix round), d1cc605 (Task 4), and this
  record (Task 5), on the design (b3bca59, approved) and the plan (d242662).

## 2. The decisions and who made them

### 2.1 Pascal's decisions (14 Nov 2026)

| | decision | Pascal's words |
|---|---|---|
| 1 | **the four best times per reverse course** (seven short tables): option 1 of the three put to them (the others: a single best time a course, a search for more battery RAM) | "Ok then do 1" |
| 2 | one screen of four rows, titled with the course's name and REVERSE; **no reverse tables in the attract mode**; four default entries a table | "Ok sounds good" |
| 3 | after the recon found that the game has **no ranking page after a race** (modes 0x1b-0x1d are the RESULT / GAME OVER screen), **the reverse tables are shown in the attract mode's ranking pages**: this replaced "no reverse tables in the attract" of decision 2 | "1" |
| 4 | the design | "Yes" |
| 5 | the plan, and its execution by an agent per task | "Yes" |

These are all of Pascal's words on this phase. The design they approved listed L1-L8 (§2.2) as the lead's calls, cheap to change,
that Pascal may override; they have ruled on none of them one by one, and L5 has changed since their "Yes" (ruling 8). They have
made no decision on the rulings of §2.3, on the title's look or on the default times.

### 2.2 The lead's calls (the design's L1-L8; cheap to change, Pascal may override any)

| | call | status |
|---|---|---|
| L1 | the game's own insert, name entry and page run on the short tables (the recon's mechanism 1) | as designed (Tasks 1-2) |
| L2 | a reverse table's ranking id is its entry + 7 (10..16) | as designed |
| L3 | in the attract a reverse table follows its course's normal table in its host's group, one member a loop | as designed; measured (§5): Bay Bridge's group has nine members, so a given member of it comes round every ninth loop instead of every fifth |
| L4 | the title is the course's ranking title with REVERSE in it, in the direction screen's red; "AMAZON FALLS REVERSE RANKING" if the longest name fits, else REVERSE alone; Pascal sees a snapshot before the merge | built as "<NAME> REVERSE RANKING" (every course fits: the longest, DIABLO CANYON and PACIFIC COAST, take 60 of the 62 columns); **the colour is not the direction screen's red**, which prints no red text (its REVERSE label is white or yellow; its reds are the arrows' own palettes): the name and REVERSE use the title's red 0x8300 (the game's BEGINNER / MEDIUM / EXPERT), RANKING white (Task 3's call; its review named it a deviation inside L4 that Pascal must judge; accepted by the lead, ruling 10). Snapshots sent, no comment yet (§2.4) |
| L5 | default entries: **changed during the build** by the lead's ruling of 15 Nov (§2.3, ruling 8): each reverse table starts with its course's NORMAL table's four default times. The first wording (the stock rule on the reverse variant's race blob) built Amazon Falls 3'00 and Diablo Canyon 4'00, a minute under their normal tables | as ruled; on the seven-course set Alpine and Diablo Canyon 5'00 .. 5'15, the five others 4'00 .. 4'15 (§5) |
| L6 | the magic is not changed; a 4-byte tag of its own marks the reverse block, checked at every boot | as designed ("REV4", §5) |
| L7 | `rankgate` is removed | as designed (Task 1) |
| L8 | rows 5 and 6 of a reverse page stay empty; the page lasts one screen (396 frames) | as designed; measured (§5) |

### 2.3 The lead's rulings during the build (the ledger's "Ruling:" lines)

| | ruling | why | cost (if wrong) |
|---|---|---|---|
| 1 | (pre-flight) Task 1 neither runs nor edits `tests/test_dirscreen_build.py`; Task 2 replaces its `test_a_reverse_race_records_nothing` | the plan's order: Task 1 removes `rankgate`, the test pinning it is replaced in Task 2 | one red test for one task |
| 2 | (pre-flight) Task 2 presets the reverse table by a poke before the race's end (as the recon's run E) and asserts the rank only as preset; the initialised rank is Task 3's | Task 2's "rank 1 in entry 0" needs the rank field, which the insert never writes and only Task 3's initialiser makes | none |
| 3 | commit trailers name the model that made the commit (the implementers ran on Opus) | attribution should be true | none |
| 4 | (Task 2, concern 1) the `race_end.lua` / `autopilot.lua` switches outside the brief's file list accepted | test harness, inert without the switches, needed by Task 4 | two more Lua files in the review |
| 5 | (Task 2, concern 2) the two-game test accepted as it stands, though it cannot show a leak between games (the attract page between them rewrites the cells) | the setter's decode test (Task 1) shows both cells written on every path, and no path reaches an insert or a page without a setter call (recon §8); the two-game test stays as evidence of the values at each insert | a leak only a path the recon missed could make |
| 6 | (Task 2, concern 3) the taps start at the coin; the boot-time writes are Task 3's tests (fresh battery RAM, upgrade, second boot) | the preset poke goes through the bus before the coin | none (carried into Task 3) |
| 7 | (Task 3, concern 2, first ruling) a reverse Metropolis race that finishes 208 frames earlier after a fresh or upgrade boot accepted for now as the emulation's sensitivity to boot timing; the reviewer asked to judge; then (fix round 1) "a stage with an unexplained change to a race does not go to Pascal": the mechanism to be established by two experiments | the reviewer found "the amount of boot work" unsupported and the mechanism unproven | a real behaviour change hidden as timing noise; closed by the fix round's measurement (§7) |
| 8 | (Task 3, concern 1) **the reverse tables start with their course's NORMAL table's four default times**, not L5's first rule on the variant's blob | the lead told Pascal "the same starting times as each course's normal table" when the design was approved | L5 as first written is dropped; `reverse_defaults` reads what the stock initialiser gives the course's normal id (four constants a course, computed at build time) |
| 9 | (Task 3, concern 3) Task 5's pins invocation runs the whole of `tests/test_dirscreen_build.py` | the select-dump test on the now-recording reverse run had not run | none (it ran in the fix round's invocation and in §10) |
| 10 | (Task 3, concerns 4 and 5) the title's red (0x8300) instead of a direction-screen red, and the files outside the brief (`ranking_attract.lua`, `test_directory.py`, `test_hudname.py`) accepted | the direction screen prints no red text; the files are harness and test bounds | a title redone if Pascal judges the look otherwise (40-100 bytes, L4) |
| 11 | Task 3's fix round goes to a fresh implementer, not a resume | Task 3's implementer had used 511k tokens and 340 tool calls (its context compacted) | the new agent re-reads the report |
| 12 | (Task 5) main for comparisons is e7c52ae's product code, `out/p26play6` its tested set; the normal direction is compared on battery RAM in the same state (each set booted once first, the compared run on its saved battery RAM) | an autopilot race can finish on another frame when the boot before it differs (§7: the harness's frame phase, not the ROM) | a difference that only a fresh boot shows is not compared here (the Task 2 test compares fresh boots of both, §9) |
| 13 | (Task 5, concern 2, ruling 2) the rows mid-draw at one frame end per screen goes to the final review as an open finding against the anti-goal's letter ("a normal page unchanged in every frame"); the likely cause the page hooks' extra cycles (two jsr per screen), **not measured**; the final review weighs whether to measure before merge | the cause was a guess from the logs | a visible one-frame difference on normal ranking pages; **superseded by ruling 15** |
| 14 | (Task 5, concern 3, ruling 3) the launcher's start battery RAM has the original game's magic, so every launch initialises all tables and Pascal's drive does not exercise the v0.2 upgrade; accepted for the drive; the lead prepares a second launcher on a v0.2-saved battery RAM if Pascal wants to see the upgrade | the upgrade is covered by Task 3's test | the upgrade path is not seen by a human (§11, §12) |
| 15 | (final review, "Final: Ruling:") the design's anti-goal "a normal page unchanged in any frame of its timing" is **read as the page's frames, their order and what each completed screen shows**; where a row stands mid-draw at a frame end varies by more on main alone (five states) than between main and this tree (3-4 words), so the finding is **closed as within main's own spread, not measured further** | the final review's reading of Task 5's logs (§9) | a one-frame partial-row difference on normal attract pages that no one has seen |
| 16 | (final review, "Final: Ruling:") the design's L5 quote "Same starting times as each course's normal table" is verbatim from the lead's summary table shown to Pascal when they approved the design; the design's own L5 cell then (commit b3bca59) gave the stock rule on the variant's blob, and the summary stated that rule's expected consequence, which proved false for two courses; recorded so in the design | the final review could not check the quote from the repository | none |
| 17 | (final review, "Final: Ruling:", the declined-to-judge list) linked play, real hardware and v0.2 save states stay "not verified"; the title's look and the default times are put to Pascal at the drive; the whole suite's result is the lead's gate; the Lua harness stands on the task reviews | outside the design or not the final review's to judge | a defect in one of these found later |
| 18 | (final review, "Final: Ruling:") the minors the final review says "may stay" stay, listed in §14; the 18-minute wait (below) goes to Pascal as a question, with the 20-30 byte follow-up as an option, **not built** | none is a player-visible defect | a player enters a reverse time and does not see its table soon |

**A correction to ruling 8 as the ledger and the design first worded it.** Both cited a second reason: "3'00 for five laps of
Amazon Falls is beyond a human's reach", on the strength of a best lap of 0'43. That lap was the **autopilot's**, read off the
HUD of the video footage, not Pascal's; no lap time of Pascal's on Amazon Falls is recorded in this phase. The design's L5 cell now
rests on the one true reason (the lead's words to Pascal at the design's approval, "the same starting times as each course's
normal table", verbatim from the lead's summary table shown to Pascal then, ruling 16: the design's own L5 cell at that time, commit
b3bca59, gave the stock rule on the variant's blob, whose expected consequence the summary stated); corrected in Task 5. The ruling stands on that reason alone.

### 2.4 What Pascal has and has not seen

- **The snapshots.** On 15 Nov Pascal was sent two snapshots of a reverse ranking page (`out/p27/look/`, Task 3 Step 5): Diablo
  Canyon (the longest name, "DIABLO CANYON REVERSE RANKING") and Alpine (the shortest, "ALPINE REVERSE RANKING"), each with four
  rows of default entries, rows 5 and 6 empty. They showed the **first** default times: Diablo Canyon 4'00 .. 4'15, since changed by
  ruling 8 to 5'00 .. 5'15 (the file in `out/p27/look/` has been overwritten since); Alpine 5'00 .. 5'15, which ruling 8 did not
  change. **Pascal has not commented on them.** Nothing in this record says that Pascal saw, approved or validated the title's
  look (its wording, its colours, the line's layout), the default times, or anything in the game.
- **Not ruled by Pascal:** L1-L8 one by one (they approved the design that lists them as the lead's calls; L5 changed after that),
  and every ruling of §2.3, among them the default times (ruling 8); the title's colour
  (0x8300 for the name and REVERSE, not the direction screen's red that L4 named); the rotation of the attract groups (L3: Bay
  Bridge's group now nine members long); the tie rule as measured (§6: the game's own, unchanged); the tests' design.
- **Not driven.** Pascal has driven nothing of this phase: no reverse race to a name entry, no reverse page in the attract. The
  playtest set `out/p27play1` and its launcher `out/rec160/launch.sh` were made in Task 5 and have not been run windowed (§11).

## 3. The eight proofs of the design's §5

| | proof | test (all in `tests/test_reverse_ranking.py` unless named), and what it asserts | result |
|---|---|---|---|
| 1 | a reverse race ranking 1st, 2nd, 3rd and 4th on a short table: the entry lands there, ranks 1..4 stay, the name entry shows that rank, nothing written outside the table and its slot | `test_a_reverse_race_records_in_its_own_table[6, 4]` (1st, Metropolis and Amazon Falls); `test_a_reverse_time_lands_in_its_place[second-2, third-3, fourth-4]` (a table preset round the race's own time at its results); both assert every battery write from the coin on inside the course's reverse table, its slot, the cells, the bookkeeping or main's own writes, the table bytes written exactly +4..+0x17 of the entries from the place down (no rank field), the ranks 1..4, the entries below moved down one, the old fourth gone, the slot on the new entry | verified (MAME). "The name entry shows that rank" is asserted through the slot and the entry's rank field the name entry prints; the snapshots of "Your Ranking is 2nd / 3rd / 4th" (`out/p27/task4/snaps/`) were looked at by the Task 4 implementer, no test reads the picture |
| 2 | a reverse time slower than the fourth: no record flag, no name entry, no write | `test_a_reverse_time_slower_than_the_fourth_records_nothing`: the `NO_RECORD` mode sequence, the record flag never set, no snapshot, no table or slot write over the whole run, only the qualify site read the cell (the bubble never ran) | verified (MAME), 1 s slower than the fourth; a time one tick (1/32 s) slower was not run |
| 3 | a tie with the fourth | `test_a_tie_with_the_last_entry_records_above_the_equal_times[tie-4, tie2-3, normaltie-24, normaltie2-23]` | verified (MAME): a tie qualifies and goes above every equal time, on a reverse and a normal table alike (§6) |
| 4 | a normal race after a reverse one on the same course, and the reverse: each writes its own table only; the normal table's 24 entries, its page and its name entry as on main | `test_both_directions_on_one_course_keep_their_own_times[reverse,normal-6, normal,reverse-4]`, `test_the_cells_follow_every_setter_call[...]` (same sessions), `test_a_normal_race_writes_as_on_main[6, 4]` (the normal table's write log, every battery write but the cells, the mode lines, against `out/p26play6`); the normal page's four screens of six rows (1 584 frames): `test_the_attract_shows_every_member_of_each_group`; the normal race to its name entry against main: §9 | verified (MAME), with a gap: each session runs one order on one course (Metropolis reverse then normal; Amazon Falls normal then reverse), order and course not crossed (§14, Task 4) |
| 5 | the attract cycle: every original's and converted course's page as on main; each reverse page one screen, four rows, rows 5 and 6 empty, the right title; the flag 0 throughout | `test_the_attract_shows_every_member_of_each_group` (1 250 s from a fresh boot: every member of the three groups, each normal page four screens of six rows, 1 584 frames, each reverse page one screen, 396 frames, rows 5 and 6 blank on every frame, the title's tiles, the flag 0 on every frame end); `tests/test_ranking.py::test_attract_and_race_end_rankings_name_their_course`; "as on main": §9 | verified (MAME); the title's tiles are checked on the last logged frame of each page (Task 3 review M5, parked) |
| 6 | upgrade: a battery RAM saved by the v0.2 set, with a best time, boots with that time kept and the reverse tables created; a second boot writes no table | `test_a_battery_ram_saved_by_main_keeps_every_time` (main's set `out/p26play6`, which v0.2 builds byte for byte, after a normal Metropolis race to the name entry: the ten tables, 13 slot words, the magic and the ranking id byte-identical and never written, the reverse block written once by `revtag`, every other write in a closed list, the writes before the first reverse page identical to main's own boot of the same battery RAM); `test_a_second_boot_writes_no_table[fresh2, upgrade2]` | verified (MAME), one saved time in one converted table, 150 s from the boot |
| 7 | the operator's backup clear resets the reverse tables with the others | `test_the_backup_clear_resets_the_reverse_tables`: the test mode driven headless (Service Mode, Red ×9 to BACKUP RAM CLEAR, Green, Red to YES, Green), a reverse table, its slot and a Metropolis time poked at frame 300 (read back through the bus), all reset as on a fresh battery RAM on frames 2 603-2 604 | verified (MAME). The poke-survival check skips the frame right after the poke (`f > 300`, should be `f >= 300`: parked, §14) |
| 8 | the three originals, the attract demo and the operator's fixed course: no reverse table is ever chosen | the setter's decode with a path walker (`test_the_setter_chooses_by_the_flag_at_the_race_and_by_the_id_in_the_attract`: +7 only when the flag is not 0 and the id is 3..9; `common`, the attract page's entry, never reads the flag); the flag 0 on every attract frame end (`test_the_attract_shows_every_member_of_each_group`) and on every frame of six attract pit scenes after a reverse race (`tests/test_dirscreen_build.py::test_the_flag_is_zero_whenever_a_select_screen_starts`) | verified for the attract and by the code for the originals (ids 0..2 never get +7). **Not run in MAME:** a race on an original and a race on the operator's fixed course with a record (the flag is 0 there by stage 3's design: the screen never opens; stage 3's tests) |

## 4. The mechanism measured (Task 2)

- **A reverse race records** (`rank_runs`, one-lap `race_end.lua` races under the autopilot, the reverse table preset by a poke
  before the coin: ranks 1..4, 5'00 .. 5'15, name "AAA"): Metropolis 2 012/32 s (62.88 s), insert on frame 6 281, name entry
  6 735 .. 8 271, attract load 8 272 (the recon's run E's frames); Amazon Falls 1 683/32 s (52.59 s). (Task 3's boot changed the
  Metropolis run to 1 908/32 s, insert 6 073: §7.)
- **Writes:** every battery byte written from the coin on lies in the course's reverse table, its slot, the two cells, the
  bookkeeping 0x40e800..0x40e9ff, or what main's normal race also writes there (`MAIN_OUTSIDE`: the game's record
  0x40f000..0x40f007, the ranking id 0x40fc68, the shown id 0x40fc69, the attract counters 0x40fc6a..0x40fc6c). No normal table or
  slot is written; the table bytes written are exactly +4..+0x17 of the four entries.
- **The cells at every setter call** (two games in one session): setter calls (frame, id) Metropolis reverse then normal (6 281, 13)
  (6 734, 13) (8 277, 1) (14 077, 6) (14 530, 6) (16 073, 5); Amazon Falls normal then reverse (4 971, 4) (5 424, 4) (6 967, 4)
  (12 045, 11) (12 498, 11) (14 041, 7). Each call makes its three cell writes (the 16-bit bus) in the same frame; each insert's two sites read the
  offset cell once (0x48 in a reverse race, 0x228 in a normal one). The attract page between the games resets the cells to 0x228 / 6
  about 5 frames after the attract load, so these sessions cannot show a leak from one game into the next (ruling 5).
- **A normal race against main** (`test_a_normal_race_writes_as_on_main`, fresh boots of both sets): identical write logs but for
  the cells and the PCs of three routines in the program ROM that moved with the image: setter 0x27a491 → 0x27a4e0, `id_store`
  0x27a64c → 0x27a6c9, `attract` 0x27a69c → 0x27a719 (Task 2's tree; they moved again with Task 3).

## 5. The reverse block at boot, on upgrade and at the backup clear (Task 3 and its fix round)

- **Fresh battery RAM:** `revtag` finds no tag and calls `revinit`; the stock initialiser then runs (no magic) and calls it again
  through `slot_init`: the block is written twice, on frame 6, the same frame as the stock initialiser. The ten normal tables,
  their slots, the magic and the ranking id end byte-identical to main's set's fresh boot.
- **The default times** (ruling 8; `reverse_defaults` printed by the fresh-boot test): Alpine 5'00, Amazon Falls 4'00, Diablo
  Canyon 5'00, Metropolis, Pacific Coast, Surfers Oval and Surfers Road 4'00, each stepping 5 s to the fourth; on the fresh battery
  RAM each reverse table's four times equal entries 0..3 of the game-made normal table of the same course (asserted). Before the
  ruling, L5's first rule gave Amazon Falls 3'00 (the reverse sectors' sum 5 722/32 s against the normal 5 779, either side of
  3'00 = 5 760) and Diablo Canyon 4'00 (its variant has 3 sectors, the normal course 4).
- **Upgrade** (main's battery RAM after a normal Metropolis race to the name entry: first entry 1 896/32 s = 59.25 s, the magic,
  the reverse block 0xff): no byte of the ten tables, the 13 slot words, the magic or the ranking id is written on the first boot;
  the reverse block is written once, on frame 6, by `revtag`; the stock initialiser does not run. The battery writes match main's
  own boot of the same battery RAM write for write up to video frame 7 300, the first page that shows a reverse id.
- **Second boot** (of the fresh run's and of the upgrade's battery RAM): no write to a table, a slot, the tag, the magic or the
  ranking id.
- **The attract** (1 800 s from a fresh boot, scratch; the test runs 1 250 s): every member of each group came, one a page of its
  data index, in group order: Bay Bridge [0, 4, 11, 7, 14, 8, 15, 9, 16] (the last, 16, at frame 64 104), Acropolis [1, 5, 12, 6,
  13], Big Forest [2, 3, 10]. Every normal page: first entries 0, 6, 12, 18, 1 584 frames, six rows. Every reverse page: first entry
  0, 396 frames, rows 1..4 drawn (in two frames), rows 5 and 6 only the blank word 0x0020 on every frame. The flag 0 at every frame
  end.
- **The backup clear:** driven headless from frame 600 (about 20 minutes to find the inputs); on frames 2 603-2 604 0xfc3b49 (from
  0xfc76eb) rewrites the ten tables and `slot_init` calls `revinit`.
- **The title** (`reverse_title_columns`): every planned name fits "<NAME> REVERSE RANKING" on the 62 columns: DIABLO CANYON and
  PACIFIC COAST 60 columns from column 1, AMAZON FALLS 58 from 2, ALPINE 46 from 8; any name up to 14 letters fits. The fallback
  for 15 letters ("<NAME> REVERSE") is unit-tested only.

## 6. Ranks two to four, a slow time, ties, both directions (Task 4)

The table is preset round the race's own time at its results (`race_end.lua`'s VR_END_PRESET, written through the nvram share on
the frame the mode first reads 0x16; the insert ran 3 frames later in every run). Times: reverse Metropolis 1 908/32 s (59.62 s),
reverse Amazon Falls 1 683 (52.59 s), normal Metropolis 1 896 (59.25 s), normal Amazon Falls 1 357 (42.41 s).

- **2nd, 3rd, 4th:** each time landed where its preset put it; the entries below moved down one with all their fields, the old
  fourth was gone, the ranks stayed 1..4, the slot held the new entry; the name entry's snapshots read "Your Ranking is 2nd"
  (00'59"62), "3rd" (00'52"59), "4th" (looked at, not asserted).
- **Slower than the fourth** (by 1 s): modes 19 1a 15 16 1b 1c 1d 02 (`NO_RECORD`), the record flag 0, no table or slot write, the
  qualify site read the cell (0x48) once and the bubble site never.
- **Ties (the game's rule, unchanged):** a time equal to the fourth records, replaces the old fourth and ranks 4th; equal to the
  third and the fourth, it ranks 3rd, above the equal old third, which moves to 4th, the old fourth gone. A normal 24-entry table
  does the same (24th; 23rd above the equal old 23rd). In the listing (0xfc4100..0xfc41fb, the same code for both lengths): the
  qualify test `cmp.w R2, 4[R1]; blt` refuses only a strictly faster last entry; the bubble `cmp.w 4[R1], 4[R0]; blt` stops only
  on a strictly faster entry above, so a tie moves the new entry up. The short tables behave as the normal ones: no discrepancy
  with the design.
- **Both directions on one course:** Metropolis reverse 1 908 then normal 2 101; Amazon Falls normal 1 357 then reverse 1 683.
  Each table holds its own time only; in the normal game's window nothing is written in the reverse block, in the reverse game's
  nothing in the normal tables or slots.
- **The insert's frame:** on the normal Amazon Falls run mode 0x1b is first read at frame end 4 970 and the insert logged on 4 971;
  on the others both on one frame end. The recon's "the insert runs on the frame mode 0x1b is entered" holds to one video frame.

## 7. A reverse race that finishes on another frame after a different boot (Task 3's fix round)

- **Seen:** after Task 3, the reverse Metropolis race of `rank_runs` (fresh boot) finished 208 frames earlier than in Task 2
  (5 680 against 5 888; time 1 908 against 2 012). On a battery RAM already set up, Task 2's code and Task 3's raced the same
  (5 889 both); only a boot that runs `revinit` (fresh, or the first boot of an upgrade) moved it. Normal races did not move
  (5 656 / 5 657 on both codes).
- **Measured** (controlled pair on battery RAMs that differ only in the reverse block; whole work RAM and battery RAM dumped at
  dense frames): no byte `revinit` or the tag check writes outside the block survives past frame 11; RAM is identical at the coin,
  the race load and the green light. Every device read (I/O board, coprocessor, display list, vblank counter) matches in value and
  order up to frame 3 635, where the wheel port reads 0xa7 against 0xa4. The wheel is the Lua autopilot's: `revinit`'s 202.5 µs of
  CPU move the main CPU's phase against the frame end; at the frame end after video frame 3 633 the fifth collision result read
  lands 4.125 µs before it in one run and 1.25 µs after it in the other, so `collision_log.lua` drops one frame's player position
  in one run and the autopilot steers on an older one. A delay of equal cycles that writes nothing (the reverse block left 0xff)
  reproduces the 5 681 with the same frame-end PC and SP on frames 8..6 000.
- **Conclusion (the fix round's, re-reviewed "addressed"):** a property of the test harness (the collision log groups by MAME's
  frame end), not of the ROM; no ROM change. The re-review's weakest link: "one dropped position → wheel 0xa4" is inferred from
  `autopilot.lua`'s code, the two autopilots' outputs not compared frame by frame; a replay of one run's inputs on the other boot
  was not run.
- **Consequence for the tests:** an autopilot race after a boot that does a different amount of work can finish on another frame.
  Fresh-boot autopilot tests outside the modules this phase ran may finish elsewhere than on main (parked, §14; the whole suite
  shows it, §10).

## 8. ROM room and sites

- **The directory image:** `end − loader` 6 856 bytes (main 6 251; Task 1 6 374), the test bound raised to 6 900 in
  `tests/test_directory.py` and `tests/test_hudname.py` (it was 6 500). The image ends at 0x27b340 (main 0x27b0e3): the routines
  after the ranking block moved +0x285 (`dirattr` 0x27a993 → 0x27ac18 .. `dirclear` 0x27ad28 → 0x27afad), those after `rankgate`'s
  old place +0x25d (`dirlock` 0x27ad61 → 0x27afbe .. `hudattr` 0x27b0e0 → 0x27b33d). Growth: Task 1 +123 (the
  setter 45 → 114, the arrays over ids 10..16 +56, `pagecmp` 23, `pagerows` 15, `rankgate` −40), Task 3 +482 (`revinit` 128,
  `revtag` 28, `revtitle` 112, `slot_init` +6, `title` +4, the titles' array +28, "REVERSE" 8, `firsts` 28, `revtitle`'s arguments
  140).
- **Boot sites:** 0xfc40f9 and 0xfc4184 (7 bytes each, in place), 0xfc3ca1 (6), 0xfc3d8c (10), 0xfe69f0 (7); 0xfc40ce back to the
  original's 16 bytes. Each checked against its original bytes (the recon's, confirmed in `out/p26/stage2/t13/boot.lst`) before it
  is written; no branch in the listing targets inside any of them (formats doc §21).
- **Room left** (measured by the final review on the built sets): the free run below the start-gantry block is now **2 000 bytes at
  0x28f1a0** (main: 2 592 at 0x28ef50; the tables moved +0x250); the six spawn-slot tails (720 / 744) and the 98 bytes at 0x28fd0e
  are unchanged in size. The image is 6 856 against the test bound 6 900: **44 bytes** under a test constant, not under a hard
  limit.
- **Battery RAM:** 709 bytes, the addresses of §1; the stack's margin 0x40fe00..0x40fecf untouched.

## 9. The normal direction against main (Task 5 Step 1)

**Sets.** Main: `out/p26play6` (e7c52ae's product code, the lead's ruling 12). This tree: `out/p27play1` (§11; d1cc605's product
code). This tree's runner and Lua drove both (`out/p27/task5/s1.py`; the reverse table's address 0x2797ec is the same on both).
**Battery RAM in the same state:** each set was booted once from a fresh battery RAM (`ranking_attract.lua`, 30 s, no input) and
every compared run started from that boot's saved battery RAM (so this tree's held the reverse block and the tag). The two fresh
boots themselves: the same mode lines (attract from frame 270, the first page from 276), and the same 6 736 battery writes (frame,
address, data, mask; main's PCs inside the directory image mapped to this tree's) once this tree's 704 writes of the reverse block
(frame 6, `revinit`'s PCs) and its 3 cell writes are set aside. Compared by `out/p27/task5/cmp5.py`, `shift5.py`, `pages5.py`
(outputs beside them).

**The races** (`autoplay.lua` + `race_end.lua` + the pit, race, field (every second frame from 1 600), start and collision logs,
write taps over 0x40e000..0x40fdff from the coin; 200 s: one lap with the clock held, the results, the name entry, the attract after
it; the autopilot on the same line files on both, Metropolis `metro.csv`, Amazon Falls `amazon.csv`, copied from Task 4's runs):

| run | main | this tree | comparison |
|---|---|---|---|
| Metropolis normal | load 1 601, finish 5 657, time 1 896/32 s, insert 6 050, name entry 6 504 .. 8 040, attract load 8 041, its first page Acropolis's id 1 | the same | pit (9 906 lines), race (10 169), field (79 248), start (158 481), collision (2 750) logs **identical**; `race_end.lua`'s 46 mode lines identical but one field (below); its 23 654 battery writes identical (frame, PC mapped, address, data, mask), this tree's 9 cell writes set aside |
| Amazon Falls normal | load 1 601, finish 4 579, time 1 357/32 s, insert 4 971, name entry 5 426 .. 6 962, attract load 6 963, its first page id 7 (Pacific Coast, Bay Bridge's group), 1 584 frames | the same to frame 6 967; its first page **id 11 (Amazon Falls REVERSE)**, 396 frames | every log identical up to frame 7 364; the battery writes before frame 7 365: 15 374 a side, **one differs**: frame 6 968, the setter's `common` writes the shown id 0x40fc69 = 7 on main, 11 here (the attract's added reverse page). From frame 7 365 (this tree's page ends, state 4) the attract runs 1 188 frames earlier here and every log differs: the logs follow the player's car entity, which goes on moving after the game, and the bookkeeping counters, both by the time spent |

- **The one other difference in the races:** `race_end.lua`'s mode line at frame 1 205 (the course select, mode 0x10) logs the
  select entity's handler, `dirsel`, a routine in the directory image: 0x27add0 on main, 0x27b02d here (+0x25d: the image's
  routines after the ranking block moved with it). A moved program-ROM address.
- **Not compared by these races:** the attract page after the Metropolis game is an original's (id 1) on both, so it shows no
  reverse page; the Amazon Falls game's shows one at once.

**The attract** (`attract5.lua`: `ranking_attract.lua` (modes, the direction byte, each page's id, table, first entry, title row
and rows, battery writes) and stage 4's `attract6.lua` (the attract pit scene's pool objects and figure pushes, the direction byte)
in one session; 600 s, no input, from the booted battery RAM): 15 attract cycles (mode 0x02) on main, 17 here.

- **Pages shown:** main ids 4, 2, 7, 1, 8, 5, 3, 6, 2, 9; this tree 4, 2, **11**, 1, 7, 5, 3, **12**, **10**, **14**, 2, 8. The
  first reverse page comes at frame 7 301 on both, where main shows Bay Bridge's group's next member 7 and this tree 11 (L3).
  Each reverse page lasts 396 frames, each normal page 1 584 on both.
- **The mode, state and flag sequence** over the 213 runs both logs share: identical; the durations identical but for four, each a
  page (mode 0x03 state 3) of 1 584 frames on main and 396 here, the four reverse pages in that span. The direction byte 0 on every
  frame of both runs.
- **The battery writes:** identical (PCs mapped, cells set aside) up to frame 7 300, where the first difference is the shown id
  (7 on main, 11 here); after it the attract runs on 1 188 frames earlier at each reverse page.
- **The attract pit scenes:** the 14 scenes both runs reach (666 frames each, 15 984 object and push lines each), compared line by
  line with frames counted from each scene's start: **identical**.
- **The normal pages, page by page** (each id shown in both runs: 4, 2 (twice here), 1, 7, 5, 3, 8; same id, table, first entries
  0, 6, 12, 18, title row and length 1 584 on both): every line identical **except 11 lines of the rows' log, a finding**: each on
  the first frame end of a screen (page-relative frames 0, 396, 792, 1 188), where one row is still being drawn and holds a few more
  or fewer distinct tile words on this tree than on main (for example id 2 at 4 645: row 2 has 47 distinct words on main, 43 here;
  its second showing here at 28 939: 69 and row 3 12 against main's 47 and 1); at the next frame end, and on every later frame of
  every screen, the rows are identical. On the five first screens (rows drawn onto a cleared layer) this tree had drawn less than
  main on four and more on one (page 2's second showing); on the six later screens the row being overwritten holds another mix of
  the old and the new screen's words.
  **Closed by the lead's ruling as within main's own spread; not measured further.** What was read and what was measured (the final
  review, from Task 5's existing logs and the built sets; no run was made for it):
  - **Main's own spread** (measured: `out/p27/task5/runs/{main,br}_attract/rank.txt`, distinct tile words a row at each page's
    relative frame 0). On **main alone**, pages whose settled content is count for count identical (ids 4, 2, 7, 8, 6, 9: 61, 69,
    72, 70, 65, 69 words a row from relative frame 1) stand at five different draw states at relative frame 0: row 2 at 69 words
    or 47 (id 2), row 3 at 1, 1, 1, 2 (id 8), 8 (id 6), 3 (id 9); ids 1 and 3 have row 3 at 24, id 5 at 1. At relative frames 792
    and 1 188 main's ids 7, 9 and 5 also differ from their look-alikes (72, 68, 75 against 68, 73, 70). So on unmodified main
    the tile state at a screen's first frame end is not a property of the page: it moves by up to about 30 tile words from page
    to page. Main against this tree differs by 3-4 words (id 2: 47 to 43; ids 1 and 3: 24 to 21) on the pages before the first
    reverse page, inside a tenth of main's own spread.
  - **The hooks' instruction counts** (read in the listing and in the built set, not measured on a run): on a normal page
    `pagecmp` runs 5 instructions for the original 1 (jsr, cmp cell, be, cmp, rsr) and `pagerows` 8 for 2 (jsr, mov, movz, rsr,
    and the four `nop`s that pad 0xfc3d92..0xfc3d95: bytes `e8f341a82700cdcdcdcd` on `out/p27play1`, read): **10 instructions
    more a screen**; the setter adds 4 at the page's start, `revtag` 5 at the boot. MAME's V60 is **inferred** to charge a flat
    cost per instruction (§7's 202.5 us is exactly the 405 instructions of `jsr revinit` and `revinit` at 0.5 us), which makes
    the hooks about 5 us a screen, a twelfth of a scanline. Inferred, not measured.
  - **The cause** was not isolated. The plausible class is the sub-frame CPU phase at MAME's frame-done sample (§7), not the hooks
    alone: the setter's and `revtag`'s instructions shift it too, and from the first reverse page (frame 7 301) every later page
    falls on other absolute frames with another history, which fits this tree showing more on one page (id 2's second showing).
    Nothing in the code can change what is drawn or on which logic frame: same row routine, same R10, R3 and 0x501924 for ids 0..9,
    first entries 0, 6, 12, 18 and 1 584 frames on every normal page (the tests and logs above).
  - **The anti-goal it bears on** (design §3): "A normal race's insert, name entry or page changing in any byte written or any
    frame of its timing". Every byte written (the two cells aside) and every frame of the game's modes, page length, screen starts and
    settled content is identical to main's; the draw state mid-row at one frame end per screen is what differs.
  - **The lead's ruling** (the ledger's "Final: Ruling:"): the anti-goal's "any frame of its timing" is read as the page's frames,
    their order and what each completed screen shows; where a row stands mid-draw at a frame end varies by more on main alone (five
    states) than between main and this tree (3-4 words), so the finding is closed as within main's own spread, not measured
    further. **Cost if wrong:** a one-frame partial-row difference on normal attract pages that no one has seen. Pascal has not been
    asked and has not seen it; one line in the report to them.
  - **Options not taken** (the final review's, neither recommended before the drive): (a) drop `pagecmp` and restore 0xfc3ca1, with
    `pagerows`' short path storing 0x12 so the stock `add.b #6` makes 0x18: 3 instructions more a screen instead of 10, 23 bytes
    back, but the reverse page's logged first entry becomes 0x18 (the tests' `firsts == [0, 6]` change); (b) normal pages truly
    untouched: `attract` installs a copied short-page handler for ids 10..16 (about 290 bytes; 2 000 are free) and both sites go
    back to the original, the setter's extra instructions at the page's start remaining. Removing the hooks would not make the
    difference disappear (the cell writes and the short pages' history still move the phase).

**Each difference, classified** (the lead's four kinds):

| difference | kind |
|---|---|
| the attract's page after the Amazon Falls game: id 11 for 396 frames instead of id 7 for 1 584, and every log after it shifted by 1 188 frames | the attract's added reverse pages (expected) |
| the attract run's pages 11, 12, 10, 14, their 396-frame lengths, and every later line shifted by 1 188 frames for each of them | the attract's added reverse pages (expected) |
| this tree's cell writes (9 in the Metropolis run, 12 in the Amazon Falls run, 39 in the attract run) | the two cells' writes (expected) |
| `dirsel`'s address in the mode line at frame 1 205; the PCs of the setter, `id_store`, `attract` and the figure routines in the write logs (mapped before comparing) | moved program-ROM addresses (expected) |
| 11 frame ends, each the first of a screen of a normal page, at which one row is mid-draw with a different number of tiles drawn | **something else: a finding** (above), **closed by the lead's ruling as within main's own spread, not measured further**; the content from the next frame end on identical |

**The ROMs** (`out/p27/task5/cmprom.py`, output `cmprom.out`): 32 of `vr.zip`'s 38 members identical, `model1io.zip` and
`m1comm.zip` identical.

| ROM | bytes differing | where, and why |
|---|---|---|
| polygon, TGP program, TGP data | 0 | identical |
| data (`mpr-14880.6`, `mpr-14881.7`) | 20 | 10 code-area pointers in bank 0 (0xde80c..0xde845), each main's + 0x250: the tables stored after the directory image moved with its growth. Nothing else |
| boot (`epr-14878a.4`, `epr-14879a.5`) | 123 | the five sites of §8 (0xfc40f9 4 of its 7 bytes, 0xfc4184 4, 0xfc3ca1 6, 0xfc3d8c 10, 0xfe69f0 6) and 0xfc40ce's 16 back to the original; 36 absolute address operands, each main's value + its routine's move inside the image (the ranking block's: `id_store`, `prologue`, `attract`, `title` +0x14f, `slot_init` +0x149, the setter +0x104; `dirattr`'s 14 sites, `startbit`, `figures`, `dirclear`, the four `crewturn` sites and the figure routines' seven +0x285; `dirlock` and `hudname` +0x25d, after `rankgate`'s 40 bytes left the image); 5 bytes in the 4 PC-relative operands of 0xfc3b4f, 0xfc3b5e (the record arrays) and 0xfe69f7, 0xfe6a18 (the magic), each target +0x38. Nothing else |
| program (`epr-14882.14`, `epr-14883.15`) | 52 288 | in the code area only: the directory image (3 965 bytes: the ranking block rewritten by design; every routine before it identical at its place but `start`, one relocated word; every routine after it identical at its own place but for relocated words: the figure routines, `crewturn1..14`, `dirlock`, `dirsel` 3, `dircursor`, `dirdraw` 2, `dirshow`, `hudname`; `rankgate` gone); the tables after the image, compared at their moved places (0x27b0f0 on main, 0x27b340 here, up to the start-gantry block): 1 883 words differ, every one a code-area address + 0x250, nothing else; main's last 0x250 bytes before the gantry are 0xff here (the gantry block itself identical); the ten load records before the loader, 21 relocated words; the variants' annex, 14 relocated words. In the ranking block the normal ids' arrays hold main's values (`bases`, `slots`, `pairs`, the magic, the names identical; `counts`, `records`, `records_oper` + 0x250 for the converted courses' race blobs); the groups gain the reverse ids |

## 10. The pins and the suite

**Step 2, the pins** (one invocation, a fresh seven-course conversion; log `out/p27/task5/pins.log`; run while Step 1's MAME runs
and Step 3's build shared the machine):

`source out/env.sh && .venv/bin/python -m pytest -o addopts="" -q -rfEX -p no:cacheprovider --basetemp out/p27/task5/pytest
tests/test_ranking.py tests/test_reverse_ranking.py tests/test_dirscreen.py tests/test_dirscreen_build.py tests/test_directory.py
tests/test_direction.py tests/test_hudname.py tests/test_hudname_build.py tests/test_reverse_build.py tests/test_pit_build.py`

**1 failed, 316 passed in 3350.48 s (0:55:50)**, no error, no skip, no warning (collected per module: test_ranking 10,
test_reverse_ranking 43, test_dirscreen 20, test_dirscreen_build 38 (the whole module, ruling 9), test_directory 26,
test_direction 26, test_hudname 5, test_hudname_build 17, test_reverse_build 82, test_pit_build 50).

- **By name against the known list** (`out/p26/stage4/full_failed.txt`, 15 names, compared as sets): none of the 15 is in these ten
  modules, so none was expected here and none is gone; **one failure is new**:
  `tests/test_reverse_build.py::test_the_variant_only_adds_bytes`, at its assertion that the set with the variants differs from
  the set without them only in the annex and the reverse table's words: `AssertionError: ['0x27a3fa', '0x27a3fd', ...]`.
- **What it is** (`out/p27/task5/variant5.py`, output `variant5.out`: the test's two sets made from one conversion and diffed):
  the boot, polygon and TGP ROMs identical; below the annex the program ROMs differ in 19 bytes of the reverse table (allowed by the
  test) and 14 bytes at 0x27a3fa.., the ranking image's `groups`: Task 3's attract groups put each variant's reverse id after its
  course's id (L3, `attract_groups`), so a set built without the variants has groups without them. Nothing else. The test was
  written in Phase 26 stage 2, before the groups depended on the variants, and none of Tasks 1-4 ran `tests/test_reverse_build.py`.
- **The fix (test only; the brief allows a test change where a pin needs it):** the test now also allows the groups' 48 bytes,
  and asserts what they hold: each set's groups equal `attract_groups` of its own directory, and the set without variants' groups
  are the set with them less the ids 10..16 (and differ from them). Its other assertions are unchanged. RED: the pins invocation
  above. A first rerun failed on the test's own reader (`OverflowError`: a uint8 count added to the index; `out/p27/task5/fix.log`),
  fixed by reading the count as an int. GREEN: `pytest ... --basetemp out/p27/task5/pytest_fix2
  "tests/test_reverse_build.py::test_the_variant_only_adds_bytes"`: **1 passed in 483.05 s** (log `out/p27/task5/fix2.log`).
- **Not run together after the fix:** the ten modules ran together only in the invocation above; the fixed test ran alone (its
  change touches no fixture). The lead's whole-suite run repeats the combined collection.

Earlier evidence runs of this phase (each task's invocation): Task 1 99 passed (12:44); Task 2 67 passed (25:45); Task 3 91 passed,
1 failed (a test of `tests/test_ranking.py` that predated the reverse groups, fixed) then 10 passed (11:11); Task 3's fix round 111
passed (30:52); Task 4 81 passed (21:47).

**The whole suite:** started by the session lead on e9d73ce (the later commit 7f8b01a changes documents, one comment and one docstring): `source out/env.sh && .venv/bin/python -m pytest -o addopts="" -q -rfEX -p no:cacheprovider --basetemp out/p27/fullbt` (log `out/p27/full.log`). **Still running when Pascal said to merge**; the merge was not held for it, on their word (as stage 4's). **Result, after the merge: 15 failed, 1179 passed, 1 xpassed, 59 warnings in 12889.09s (3:34:49).** The 15 FAILED names are exactly the 15 known on main, compared by name as sets (`out/p27/full_failed.txt` against `out/p26/stage4/full_failed.txt`): none new, none gone; no ERROR; the xpass is main's (`test_regenerated_big_forest_drives`). Stage 4's run was 1 138 passed; the 41 more are this phase's tests less the ones it replaced. The fresh-boot autopilot tests outside this phase's modules (§7's risk) all passed.

## 11. The playtest set

- **The set:** `out/p27play1` (`.venv/bin/vrtools build --roms "$VR_ROMDIR" --saturn "$VR_SATURN_CUE" --out out/p27play1`, at
  d1cc605: the tree differed from it only in this task's documents; 8 min 51 s; log `out/p27/task5/play1_build.log`;
  `build-report.txt` beside it), not committed. Its `build-report.txt` differs from `out/p26play6`'s only in each converted
  course's tile table, race blob and spawn list addresses, each + 0x250 (the tables after the grown image); the variants' lines are
  identical. Its ROMs against main's: §9. The seven-course set the pins invocation built for its MAME tests (§10;
  `out/p27/task5/pytest/rank0/build/`, `boot0/build/`) and the one `test_attract_and_race_end_rankings_name_their_course` built hold the same 38 members byte for
  byte as `out/p27play1`'s `vr.zip`.
- **Boots:** a headless 30-s run of `ranking_attract.lua` on it from a fresh battery RAM (no coin, no input;
  `out/p27/task5/runs/br_boot/`) reaches the attract mode: the mode byte reads 0x02 from frame 270, 0x03 from 274, the first ranking
  page from 276, the same frames as main's set; the saved battery RAM holds the magic "S-RAM CHECK OK 10" and the tag "REV4".
- **Launcher:** `out/rec160/launch.sh`, a copy of `out/rec159/launch.sh` with rec159 → rec160 and p26play6 → p27play1; its
  `start/` (the cfg and the battery RAM the launcher copies in on every try) a copy of `out/rec159/start/`; `inp/` empty (the run
  records `out/rec160/inp/play.inp`). **Not run windowed** (the lead runs it on Pascal's word). Note: the battery RAM in `start/`
  holds the original game's magic "S-RAM CHECK OK !!", not the patch's, so every launch initialises all seventeen tables to their
  defaults (the fresh path: §5), and a drive from it does not exercise the upgrade path.
- **For Pascal's drive** (the design's §5: "a reverse race to a name entry, and the attract's reverse pages"): a reverse race on a
  converted course finished at or under its reverse table's fourth time (the defaults' 4'15, 5'15 on Alpine and Diablo Canyon, for
  the five laps) records and asks for a name (no human five-lap time is measured here); in the attract mode, the reverse pages follow their course's
  page (Big Forest's group: Alpine reverse after Alpine; Acropolis's: Diablo Canyon reverse, Metropolis reverse; Bay Bridge's: the
  other four), one member a loop, so a given reverse page can take several loops (up to nine on Bay Bridge's group) to come round.
  The title's look (L4, the colour of §2.2) is Pascal's to judge. Also: coin and START during the results screen of a reverse race
  that set a record (the name entry calls the setter again about 450 frames after the insert and trusts the direction flag; no
  path that clears it was found, read not run); check both tables afterwards.

## 12. Not verified

- **Pascal's drive:** nothing of this phase has been driven by Pascal or by any human. Not confirmed by them: a reverse race to a
  name entry, the reverse pages in the attract mode, the title's look, the default times.
- **The ten pins modules together after Task 5's test change:** the changed test ran alone (§10).
- **A full five-lap reverse race** to its end and name entry: every measured race is `race_end.lua`'s one lap with the clock held
  (as in the recon).
- **A human entering a name:** the autoplay enters none; the name entry's timer runs out and the blank name is kept (asserted).
- **A time one tick (1/32 s) slower than the fourth** (the slow case is 1 s slower; the tie rule read in the listing covers it).
- **Both orders on one course:** each two-game session runs one order on one course (Metropolis reverse then normal, Amazon Falls
  normal then reverse), order and course not crossed (§14).
- **A leak of the cells from one game into the next:** the attract page between two games rewrites the cells, so the two-game
  sessions cannot show one (ruling 5).
- **The name entry's picture:** "Your Ranking is 2nd / 3rd / 4th" read off snapshots, not by a test.
- **A race with a record on an original course and on the operator's fixed course** after this phase (proof 8 rests on the setter's
  decode and the flag 0 there by stage 3's design).
- **The operator-variant records** (the stock initialiser on `records_oper` when the operator setting selects it): the normal tables
  would start from those, the reverse tables always from the normal records' defaults; not run.
- **The 15-letter title fallback** ("<NAME> REVERSE"): unit-tested only; no course has 15 letters.
- **Upgrade from v0.2 with times in several tables, and after a race that later fills a reverse table:** the upgrade test enters one
  normal time in one converted table and watches 150 s.
- **The normal direction against main for the five other converted courses and the originals in a race:** §9 raced Metropolis and
  Amazon Falls; the others rest on the ROM comparison (no product change outside the ranking block, the five sites and relocated
  words) and on the attract's pages.
- **The cause of the 11 partly drawn rows of §9** (one frame end per screen): not measured further; the finding is closed by the lead's
  ruling as within main's own spread (§9, §2.3 ruling 15).
- **The autopilot race's 208-frame move after a boot that runs `revinit` (§7):** the replay that would close the re-review's weakest
  link was not run.
- **The test mode beyond the backup clear;** linked play (a linked race is never reverse: design §3); real hardware; a real board's
  battery RAM content where MAME's reads 0xff.

## 13. Status

- Built and measured as above on branch `phase27-reverse-ranking`: the recon (e72794b), the design (b3bca59, approved by Pascal's
  "Yes"), the plan (d242662), Tasks 1-4 (bb580f2, dd82aac, 6c1de14, 2be1743, d1cc605) and this record (Task 5). **Merged and
  pushed on 15 Nov** on Pascal's word, without their drive (below).
- Against main (§9): a normal Metropolis race to the name entry and on into the attract gives main's logs; a normal Amazon Falls race
  gives them up to the attract page after it, which is the added reverse page; 600 s of attract give main's mode sequence, pit scenes
  and pages, with the reverse pages added and one finding (rows mid-draw at one frame end per screen), closed by the lead's ruling as
  within main's own spread (§9). The ROMs differ as §9 lists.
- The pins (§10): 316 passed and one new failure, `tests/test_reverse_build.py::test_the_variant_only_adds_bytes`, whose
  expectation predated Task 3's attract groups; the test was updated (test only) and passed alone (1 passed, 8 min).
- **The final review** (whole branch, be2db9b..e9d73ce; `.superpowers/sdd/2026-11-14-phase27-reverse-ranking/final-review.md`; read
  only, no pytest, no MAME): **ready to hand to the owner for their drive, with fixes to the record only**; no Critical finding; one
  Important finding (§9, closed by the lead's ruling 15); no product or test code change required. It found no path by which a
  v0.2 player loses a best time and no stale use of the cells.
- **The final fix wave** (15 Nov 2026; documents, comments and docstrings only; no product or test logic): the findings' §2.3, §8,
  §9, §11, §12, §13, §14, the follow-ups, the README, the formats doc's room line, the design's L5 row, the plan's Task 3 Step 1
  note, two comments in `tests/test_reverse_ranking.py`.
- **Merged and pushed:** merged into main and pushed on 15 Nov 2026 on Pascal's "Merge update MD commit and push", given without a drive and while the whole suite was still running: main fast-forwarded from be2db9b (the phase's commits and this one); branch `phase27-reverse-ranking` kept locally. Not put to a drive before the merge: the reverse name entry and the attract's reverse pages on a real screen, the title's look (the snapshots of 15 Nov, not commented on), the coin and START during a reverse record's results. Not answered by Pascal: the 18-minute wait before a table just raced comes round in the attract (§14).
- **The whole suite** (§10): the 15 known failures only, 1 179 passed.
- **Released as the public v0.2.1** on 15 Nov on Pascal's "Release and add the screenshot yes" (the number is the session lead's choice, told to Pascal), with Windows steps and a test run on Windows, macOS and Ubuntu (Pascal: "Include it"). Still not driven by Pascal; the public notes say the feature was tested with the autopilot in one-lap races and not played by hand.
- Playtest set `out/p27play1`, launcher `out/rec160/launch.sh`, not run windowed (§11).
- **Pascal has driven nothing of this phase** and has not commented on the two snapshots they were sent (§2.4).

## 14. Review items parked, open

As the ledger (`progress.md`) has them, task by task; none fixed in Task 5 except where the lead's Task 5 instructions say so
(marked). The final review triaged them (`final-review.md`); the lead ruled that the ones it says "may stay" stay (§2.3, ruling 18):

- **May stay (the final review's list):**
  - Task 3 `f > 300` to `f >= 300` in the backup-clear test: a one-frame blind window after the poke; the later assertions do not
    depend on it; change it the next time the file is touched and rerun that test then.
  - Task 5 R4 (the public "keeps every best time"): judged supported (the test taps every write and finds none in any of the ten
    tables, their slots or the magic).
  - Task 5 R1 (group padding not asserted); Task 1 (copied helpers, the 196-character line); Task 2 minors 1, 4-8, 11; Task 3 M2-M5,
    M9; Task 4's brittle Lua string test and docstrings citing snapshot text: test polish, no player effect.
  - Task 2 minor 9 (`vr_autopilot_load` leaves `last_ang`, `last_speed`, `last_off`, `seen_frame`): harness; fixing it can move the
    second game's autopilot and needs the two-game sessions rerun; not before the drive.
  - Task 4: both orders not crossed with both courses; no one-tick-slower case (the compare is one strict signed `blt` on both table
    lengths; the equal and 1 s slower sides are run).
  - Task 3: no test of reverse defaults under the operator-variant records (cosmetic on an operator setting; §12).
  - Task 3 report lines 13, 121, 305 stale (scratch, not the record).
  - M5: the name entry trusts the direction flag a second time (a drive note: §11).
  - M6: `pagerows` loads the row count straight from the cell; any value but 4 or 6 would draw that many rows; unreachable as built;
    closing it costs instructions on the normal page.
- **Done in the final fix wave** (record and comments only): Task 5 R2, R3, R5, R6 (R7 needed no change: §2.1's heading dates all five decisions 14 Nov 2026); Task 2 minors 3 and 10; the plan's Task 3 Step 1
  note; the final review's I1, M1-M4, M7.
- **An open question for Pascal, not built:** after a reverse record the player may wait about 18 minutes of attract to see its
  table (Bay Bridge's group is nine long; its last member first came at frame 64 104, about 18 minutes, in the fresh-boot run); main
  does the same for normal tables, so it is not a regression. A follow-up of some 20-30 bytes could point the group's counter at the
  table just raced. Cost of leaving it: a player enters a reverse time and does not see its table soon.
- **Not run:** a second launcher on a v0.2-saved battery RAM (ruling 14) would let Pascal see the upgrade with their own times.

The items as the ledger worded them, task by task:

- **Task 1** (ledger: "Parked minors"): "test helpers copied from tests/test_ranking.py / test_dirscreen.py into
  tests/test_reverse_ranking.py (lines 24-33, 74-75, 102-104, 119-121); a 196-char docstring line at vrtools/arcade/dirscreen.py:414."
- **Task 2** (ledger: "11 minors parked in task-2-review.md"): "Carried: minor 2 (two-game sessions do not check each game's time
  landed in its own direction's table) -> Task 4's both-orders test; minors 3 (comment "59-63 s" vs 52.59 s measured), 9
  (vr_autopilot_load leaves last_ang/last_speed/last_off/seen_frame), 10 (docstring: the attract page resets the cells between
  games) -> final fix wave; 1, 4-8, 11 parked." Minor 2 was done by Task 4 (`test_both_directions_on_one_course_keep_their_own_times`).
  The parked ones, as `task-2-review.md` words them: 1, the string test of `race_end.lua`'s exact source lines (a change detector);
  4, `_after_finish` / `_driving` duplicating `tests/test_dirscreen_build.py`'s helpers; 5, imports in the middle of the test module
  (`noqa: E402`); 6, the cell writes not checked by PC; 7, the second game hard-coding `autoplay.lua`'s input frames; 8, the
  `:WHEEL` / `:ACCEL` lookups running with no switch set; 11, the fixture making all eight runs whatever test is selected, and a
  failed build not cached.
- **Task 3** (ledger: "Deferred minors"): "backup-clear test's no-overwrite check `f > 300` should be `f >= 300`; the design's L5
  "why" cell: "3'00 beyond a human's reach" rested on a best lap of 0'43 that was the AUTOPILOT's (the video footage's HUD), not
  Pascal's — the lead corrects the wording in Task 5's record (the ruling stands on "the lead told Pascal the same starting times as
  the normal table"); the plan's Task 3 line words L5 the old way; report lines 13, 121, 305 stale; fresh-boot autopilot tests outside
  the five modules may finish on other frames than on main (the whole suite will show); no test of reverse defaults under the
  operator-variant records. M2-M5, M9 of the first review parked."
  - **Done in Task 5 (the lead's instructions):** the design's L5 cell corrected (§2.3); the plan's Task 3 interface line reworded
    to what was built (its Step 1 still says "on each variant's blob": left, not named in the instruction).
  - M2-M5, M9 as `task-3-review.md` words them: M2, a chain's second-step failure marks the first run failed too
    (`self.runs[label] = f.exception() or f.result()[k]`); M3, the skip message names a missing main set when the main race failed;
    M4, the whole fresh-battery test skips without main's set though only two assertions need it; M5, rows 1..4 drawn and the title
    words checked on one logged line a page; M9, the failure message omits GAME_RECORD.
- **Task 4** (ledger: "Deferred minors"): "both-orders test does not cross order and course (docstring should name the gap; two more
  300-s sessions would close it); docstrings cite the snapshot's text though no test reads the picture; no one-tick-slower boundary
  case; exact-Lua-line string test brittle."
- **Found in Task 5 (not a review item):** the pin `test_the_variant_only_adds_bytes` failed on Task 3's attract groups and was
  updated (§10); §9's partly drawn rows at one frame end per screen of a normal page (closed by the lead's ruling as within main's
  own spread, not measured further);
  the launcher's start battery RAM takes the fresh path (§11).

## 15. The attract's first page after a game

A follow-up on branch `phase27b-attract-jump` (from main at 6d04860), on Pascal's request: "Add the follow up to jump to the race we
just did" (§14's parked question). Their only words on it. Not merged, not driven by Pascal.

- **What was built** (`vrtools/arcade/ranking.py`): at the race's end, after the ranking setter, the counter of the raced course's
  attract group is set to the position in that group of the table the setter chose (the course's id, or id + 7 in a reverse race),
  so the attract's first ranking page after the game shows that table; `attract` then stores position + 1 as before and the
  rotation goes on from the member after it, wrapping as before.
  - **The site** 0xfc40e1 (10 bytes; `movz.bw 501934[PC], R0; bsr FC4208`, bytes `0d20f253d853ff482001`, checked before the patch;
    no branch in the listing lands inside it) becomes `bsr FC4208; jsr raceend; nop`. The `movz.bw` was dead since Phase 22r (the
    setter loads the ranking id itself). The insert at 0xfc40eb follows unchanged.
  - **`raceend`** (22 bytes): `movz.bw 501934, R1; mov.b positions(R0), 40FC6A(R1); rsr`. R0 is the id the setter chose (`common`
    keeps it); R1 and R0 are reloaded by the insert's next two instructions. The counter written is the data index's, the group the
    first page after the game reads (recon §3: the page after a Metropolis race read Acropolis's group).
  - **`positions`** (17 bytes, by ranking id 0..16; `attract_positions`): each id's index in its group; 0 for an id in no group.
  - **Not touched:** the name entry's setter call (0xfc4226), the attract page's (0xfc3c33), the setter, the page, the insert.
  - **Room:** the directory image's `end − loader` 6 856 → **6 895** bytes; the test bound 6 900 is not raised. The free run below the
    start-gantry block: 2 000 bytes at 0x28f1a0 → **1 952 at 0x28f1d0** (the tables after the image moved +0x30).
  - **Battery RAM:** one byte written that a race did not write before (`0x40fc6a + data index`, the counter the attract page
    already keeps). Magic and reverse tag unchanged; a v0.2.1 save keeps everything.
  - **Which races:** every race that reaches the setter at 0xfc40e1, that is every finished race (0xfc40d6 tests the finish bit 1
    of 0x501174, set by the lap count code at 0xfea2d8), with or without a record, normal or reverse, any course. A race that does
    not finish (time over) skips the insert and the setter and leaves the counter: the attract goes on with its rotation (read in
    the listing, not run).
- **Harness:** autoplay.lua's VR_EXTRA_LUA takes several scripts separated by ';' (race_end.lua and ranking_attract.lua together);
  `run_mame` honours VR_MAME_JOBS=n (at most n MAME processes at once from one pytest process). The autopilot finishes a one-lap Bay
  Bridge race on the Saturn track's centreline with a lookahead of 3 points (with the default 6 the car stuck on a wall from frame ~4 000; 10 finished later;
  scratch runs `out/p27b/bay*`, `la3`, `la10`, `lift3`).
- **Measured** (MAME 0.289, one-lap `race_end.lua` races under the autopilot, fresh battery RAM; tests in
  `tests/test_reverse_ranking.py`, "Phase 27b"):

  | run | race (time, 1/32 s) | first page after the game (frame, group, id) | then | main (6d04860) |
  |---|---|---|---|---|
  | Metropolis normal | 1 896, record | 8 046, Acropolis's, **6** (four screens, its title) | next of that group 15 072: **13** (Metropolis reverse) | 8 046, id 1 (Acropolis) |
  | Amazon Falls reverse | 1 683, record | 7 620, Bay Bridge's, **11** "AMAZON FALLS REVERSE RANKING", one screen of four rows | | 7 620, id 4 (measured on this tree before the change) |
  | Bay Bridge (an original) | 2 136, record | 8 526, Bay Bridge's, **0** (MEDIUM COURSE RANKING) | | 8 526, id 4 (before the change) |
  | Metropolis reverse, no record (the table preset 4 .. 1 s faster at its results) | 1 908, no record, no name entry | 6 532, Acropolis's, **13** | next of that group 12 370: **1** (the wrap from the last member) | 6 532, id 1 (before the change) |

  - `raceend` wrote the counter once a race, on the insert's frame (6 049, 5 623, 6 529, 6 073), with the position (3, 2, 0, 4);
    the page then stored position + 1 (4, 3, 1, 5), as `attract` always did.
  - **A race against main** (`test_a_race_writes_as_on_main_but_its_group_s_counter`; the same normal Metropolis race on
    `out/p27play1`, both from a fresh battery RAM): the same race time and frames; up to the attract load (frame 8 040) all 16 727
    battery writes identical (frame, address, data, mask, boot-ROM PCs) besides `raceend`'s one; the modes identical frame for frame
    up to 11 400; from the attract load to 11 400, 6 725 writes on the same frames, addresses and masks, the data differing only in
    the shown id (0x40fc69) and the counter (0x40fc6b).
  - **No game against main** (`test_with_no_game_the_attract_is_main_s_frame_for_frame`, 1 250 s from a fresh boot on this set and on
    `out/p27play1`): the modes, all 101 page lines (frame, shown id, data index, table, first entry shown), the title rows and the
    page rows identical, and all 147 928 battery writes identical (frame, address, data, mask, boot-ROM PCs).
  - **Before the change** (RED, this tree's tests on the unchanged product code, `out/p27b/red_mame.log`): the first pages after the
    same races showed ids 1, 4, 4 and 1 (each group's next member), the tests failed on that; the wrap test saw 1 then 5.

- **The tests** (`VR_MAME_JOBS=3`, `--basetemp out/p27b/pytest`): `tests/test_reverse_ranking.py tests/test_ranking.py
  tests/test_directory.py tests/test_hudname.py tests/test_dirscreen_build.py`: 131 passed, 1 failed in 52 min 18 s. The failure was
  the new race-against-main test's frame bound (60 frames a second; main's 200-s run ends at frame 11 504, the video's 57.5 Hz):
  test only, bound set to 57 a second, then that test alone: 1 passed (13 min 39 s, `out/p27b/pytest2`). Also alone (no MAME):
  `tests/test_reverse_build.py::test_the_variant_only_adds_bytes`, updated for the positions (each set's from its own groups):
  1 passed; `tests/test_mame_runner.py`: passed. The whole suite was not run.
- **Not verified:** the whole suite; a race that runs out of time (read only: no setter call, no jump); a five-lap race; linked play and the
  operator's fixed course (they reach the same site: the same jump, read only); a human's drive; Acropolis and Big Forest races
  (originals: only Bay Bridge run); the other converted courses than Metropolis and Amazon Falls (the positions table is checked
  statically against the groups).

- **Review and fix wave** (`out/p27b/review.md`, independent, read-only): verdict ready to merge with fixes; no Critical or Important
  finding. This wave changed: M1 the README's Phase 27b paragraph has its own heading after the "Public release v0.2.1" section;
  M2 "a race that runs out of time does not reach the setter" is marked "(read in the listing, not run)" in the README and
  `docs/follow-ups.md`; M3 `VR_MAME_JOBS` that is not a positive integer (0, negative, text) raises a `MameError` instead of waiting
  forever or a bare ValueError (unit test first: it failed on the old code, `0` by hanging, then passed); M5 the no-game test's skip
  names `out/p27play1`; M8 the `VR_MAME_JOBS` cap test pairs its fakes on a barrier and asserts the peak never exceeds the cap (no
  timing). M4: `tests/test_reverse_ranking.py` and `tests/test_mame_runner.py` in one invocation on the final text
  (`VR_MAME_JOBS=3`, `out/p27b/fix_pytest.log`): **77 passed in 1512 s (25 min 12 s)**, no failure.
  - Parked, as the review words them:
    - M6: the group comes from DATA_INDEX and the position from RANKING_INDEX(+7); if they disagree (linked play, the operator's
      course: not run) the first page shows an arbitrary member of the group, harmless, clamped; document, no code (no room).
    - M7: `raceend` does not clamp the data index as `attract` does (>= 3 gives 0); no reachable path found; a data index of 3..5
      would write 0x40fc6d..6f (free bytes); document, a clamp would need 6+ bytes the image does not have.
    - M9: no run covers data index 2 (Big Forest's group, counter 0x40fc6c) or the Acropolis / Big Forest originals; none needed
      before merge.
    - M10: `test_a_normal_race_writes_as_on_main`'s same-frames-after-the-attract-load holds only because RUN_SECONDS = 200 ends
      before the group's second page after the game; comment the dependency or cut the comparison at the first page's end.
