# Phase 26 stage 3: findings

The measured findings of stage 3 of `docs/superpowers/specs/2026-11-11-reverse-courses-design.md` (§2 item 3, §6.6: the COURSE
DIRECTION screen after the course select, replacing stage 1's debug switch), and of the task added during it at Pascal's request
(the course's name in the race HUD). Facts and numbers only. Plan: `docs/superpowers/plans/2026-11-13-reverse-stage3-direction-screen.md`
(decisions D1-D14); recon: `docs/spike/2026-11-phase26-stage3-recon.md`; the HUD name's recon is scratch
(`out/p26/stage3/hud/recon.md`). The scripts, logs, builds, dumps and snapshots quoted are git-ignored under `out/p26/stage3/`
(one directory per task: `t1/` .. `t8/`; snapshots under `look/`).

Stage 3 was executed on Pascal's "continue" (13 Nov) without their review of the plan. Pascal drove the playtest set `out/p26play4`
the same day (§12) and, while the whole suite ran, said "Merge and push when ready": merged into main and pushed on 13 Nov after
the suite (§8). The set with Task 8's change, `out/p26play5`, has not been driven.

**Map:**
- §1 what was built;
- §2 the decisions and who made them, and the session lead's rulings;
- §3 the ROM room, the sites and the RAM cells;
- §4 the screen measured;
- §5 the course's name in the race HUD;
- §6 the normal direction against main (Task 7 Step 1);
- §7 the data block's readers, and the middle slot after the lock (Task 7 Step 2);
- §8 the suite;
- §9 the playtest set and the contact sheet;
- §10 not verified, known limits;
- §11 status;
- §12 after Pascal's drive (13 Nov): the decisions, and Diablo Canyon's START arch no reverse checkpoint (Task 8).

## 1. What was built

- **The flag's life** (Task 1, recon §7). The flag `course.DIRECTION_RAM` (0x502294) is 0 whenever a select screen starts: mode
  0x10 state 0 (0xfe3cce) calls `dirclear`, which does the game's own clear of 0x5019c0 and clears the flag's word (the flag and
  the screen's three cells). The two linked course loads (0xfe2b07, mode 5; 0xfe1d37, a cabinet joining a linked race) call
  `bankdemo` as the attract's two do. Stage 1's open items "the flag is not cleared at game start" and "linked play's bank sites
  call `bank`" are closed.
- **A reverse race records nothing** (Task 1, recon §8, plan D9). The race end's call 0xfc40ce (16 bytes) becomes `jsr rankgate`:
  the record flag 0x5018fc is cleared as the game does, and with the flag set the `be FC417C` after the site skips the record and
  the name entry. After a reverse race the game takes the flow of a race without a record (the race-end ranking page shows the
  normal course's table). Stage 1's open item "a reverse race writes the course's ranking table" is closed.
- **The screen as behaviour** (Task 2, recon §1.2 option (a)). The course lock handler's `mov.w #FC27BE, A[R25]` (0xfc2788) becomes
  `jsr dirlock`. On an entry with a reverse record, in single play, `dirlock` hands the select entity to `dirsel` with the timer at
  0x140 (10 s). `dirsel` reads the wheel each logic frame (NORMAL until the wheel has been at or left of the threshold 0x1c on this
  screen, then REVERSE right of it), shows the choice, and locks on a gas edge or when the countdown reaches 0x20: the flag := the
  choice, then the entity goes back to the game's own lock handler 0xfc277c, so the race loads with the game's lock-to-load timing.
  On the three originals, in linked play and on the operator's fixed course the flow is today's.
- **The screen drawn** (Tasks 3-5): layer 0 cleared, layer 2's checker redrawn, the picked course's select picture twice on layer 2
  (NORMAL left, REVERSE right), the COURSE DIRECTION title, the NORMAL / REVERSE labels (the current choice yellow), the game's
  double arrow, wheel panel, red arrow, countdown and STEP TO START! panel; the game's yellow cursor frame at the chosen side
  (blinking while choosing, steady after the lock); at the lock the chosen picture keeps its colours and the other goes grey; two
  96-px ring arrows over the pictures (the NORMAL side's white, showing the course's own lap sense; the REVERSE side's red, the
  other sense) and the SELECT DIRECTION caption on the wheel panel. The arrows and caption are drawn by `vrtools/arcade/dirgfx.py`
  at build time.
- **Tests drive the real screen** (plan D14): `autoplay.lua` answers it on converted entries so that the direction lock falls on
  the frame of today's course lock (1402) and the race loads on today's frame (1600).
- **The course's name in the race HUD** (Task 6, Pascal's request of 13 Nov): on the seven converted courses the race HUD's
  bottom-right label reads the course's name in place of BEGINNER / MEDIUM / EXPERT; the three originals keep the game's word (§5).
- **Modules:** `vrtools/arcade/dirscreen.py` (the screen's routines, sites and cells), `vrtools/arcade/dirgfx.py` (the arrows, the
  caption, the data block and its draw list), `vrtools/arcade/hudname.py` (the HUD name). Lua: `race_end.lua`, `dirscreen_log.lua`,
  `dirscreen_drive.lua`, `hud_log.lua`, `slot_log.lua` (Task 7); `autoplay.lua` answers the screen.
- **No collision change.** The TGP data ROM is byte-identical to main's build (§6); `tests/test_tencourse.py`'s floor
  `tgp_budget >= 7_500` stands.

## 2. The decisions and who made them

**The plan's decisions** (recon §12 for D1-D9; D10-D14 the builder's ground, design §7). "Lead" = the session lead's call.

| | decision | who | status with Pascal |
|---|---|---|---|
| D1 | picture positions: the mockup's (16 × 21 tiles at rows 4-24, columns 9-24 and 37-52; title rows 1-3; labels rows 26-28; panels from row 30) | lead, from the mockups | Pascal saw the Task 3 snapshots on 13 Nov: "looks good", including the game's frame being wider than the mockup's (its top edge behind the title, its bottom edge at the labels): accepted as is. In those snapshots both labels were white and there were no arrows, no caption and no lock look |
| D2 | the pictures on layer 2, the arrows on layer 0 over them | lead | the pictures' layer seen in the Task 3 snapshots; the arrows over them sent after Task 5, not yet confirmed |
| D3 | the title in the countdown's bold yellow font (0xff870d), no new characters | lead | as D1 |
| D4 | the labels in the ranking titles' font (0xffe8fb), yellow 0xC200 for the current choice, white 0x8200 for the other | lead | the font and the positions seen in the Task 3 snapshots (both labels white there); the yellow highlight of the current choice (Task 4) sent afterwards, not yet confirmed |
| D5 | the wheel panel's caption reads SELECT DIRECTION (new lettering) | lead | snapshots sent after Task 5; shown, not yet confirmed |
| D6 | the choice starts NORMAL; the wheel chooses only once it has been at or left of the threshold on this screen; with no press the countdown takes the choice shown (NORMAL if the wheel was never armed) | built by the lead without authority (it departed from the design's wording Pascal had approved, below); decided by Pascal | decided by Pascal on 13 Nov after driving `out/p26play4`: "the wheel rule work great for the reverse/normal" (below, §12) |
| D7 | the screen replaces the course select at once (no half second of the course lock look first) | lead | not yet reviewed |
| D8 | arrow colours: the NORMAL side's white, the REVERSE side's red | lead | snapshots sent after Task 5, not yet confirmed |
| D9 | after a reverse race, today's flow of a race without a record | lead | not yet reviewed |
| D10 | the screen's routines in the directory image; the `end − loader` test bound raised from 5 000 to 6 000 | builder's ground (lead's ruling on the bound) | — |
| D11 | the graphics in one data block of at most 8 192 bytes ending at 0x2c0000 | builder's ground | — |
| D12 | the flag stays the byte 0x502294; the word's other three bytes are the screen's cells | builder's ground | — |
| D13 | timer 0x140; lock on a gas edge or at timer ≤ 0x20. As built: the direction lock hands the entity back to the game's own lock handler 0xfc277c (198 frames from lock to load) | builder's ground; the handoff a ruling of the lead (below) | — |
| D14 | tests drive the real screen; `direction.lua` stays a test tool for forcing the flag where no screen sets it | builder's ground | — |
| H1 | the HUD name on the converted courses only; the originals keep the game's word | Pascal ("Ok" to the lead's proposal, 13 Nov) | decided |
| H2 | the name's colour: the entry's select-screen level (blue BEGINNER, orange MEDIUM, red EXPERT) | Pascal (same "Ok") | decided |
| H3 | right-aligned, the last letter in column 58 | Pascal (same "Ok") | decided |
| H4 | the same name in reverse | Pascal (same "Ok") | decided |

**D6 departed from the design Pascal approved; Pascal has since decided it as built.** The design's §2 item 3, the behaviour
Pascal approved (and which its line 18 says a builder may never revisit), read "wheel left of centre or straight ahead is NORMAL, wheel to the right is REVERSE" and
"with no press, the countdown (about 10 seconds) takes whatever the wheel points at". As built, the choice starts NORMAL and the
wheel counts only once it has been at or left of the threshold (0x1c) on this screen; from then on wheel right is REVERSE; with no
press the countdown takes the choice shown, NORMAL if the wheel was never armed. A player who keeps the wheel right after choosing
the course and presses again gets NORMAL. Why the lead built it so: entries 7-9 and most of 6 are chosen with the wheel right of
the threshold (recon §5), so under the literal rule the screen would open on REVERSE and the countdown would give a reverse race
to a player who does nothing; the recon put this to the owner as its §12 D6. The lead took the recon's recommendation (b) instead
of asking, and had no authority to settle a "Pascal" item. It was put to Pascal with the recon's three alternatives: (a) the
wheel as it is (the design's literal rule: REVERSE pre-selected on entries 7-9 and most of 6, the countdown takes it); (b) as
built; (c) relative to the wheel at the screen's start. **Pascal's decision (13 Nov, after driving `out/p26play4`): "the wheel
rule work great for the reverse/normal"**: (b), D6 as built, is theirs; the design's §2 item 3 now states the built rule, marked
with the date (§12). The playtest instructions (§9) describe the rule as built.

Before the drive Pascal had said two things on stage 3: "Ok" to the HUD name proposal (H1-H4) and "looks good" on the Task 3
snapshots (white labels, no arrows, caption or lock look). Sent afterwards and not confirmed one by one: the yellow label of the
current choice and the lock look (Task 4), the arrows and the caption (Task 5), the HUD name's look (Task 6) and the contact
sheet (§9). Pascal then drove `out/p26play4` (13 Nov, two sessions): it "feels great"; their decisions are in §12.

**The session lead's rulings during the build** (the ledger's "Ruling:" lines, with their reason and their cost if wrong):

| ruling | why | cost if wrong |
|---|---|---|
| the plan executed without waiting for Pascal's review | their instruction was to continue; the design (§2 item 3, §6.6) is approved | rework of whatever they would change; nothing merged or pushed |
| D1-D9 taken as the recon recommends | D1/D2/D5 follow the chosen mockup and the design's text; D3/D4 cost no characters; D6 keeps "do nothing = NORMAL" | D6 about 20 bytes, D3/D4 a font change, D9 one more site |
| the `end − loader` bound 5 000 → 6 000 (D10) | a "routines stay small" test constant; the image is the project's one layout system | the screen's code moves to a block below the gantry (recon R2) |
| tests answer the screen with the course press made early (D14) | keeps every race baseline's frames, if the race proves identical (a STOP check) | the race tests' frame windows and bounds need a review with Pascal |
| the HUD name rides on this branch as an added task | it needs bytes in the same directory image; the comparison with main and the playtest set should cover it | the two features merge together or not at all |
| HUD defaults H1-H4 proposed | H1 follows Phase 23b; H2 keeps the game's meaning of the colours where the host's level differs (Metropolis, Surfers Oval, Surfers Road); H3/H4 the recon's clean layout | a table byte per entry or a few bytes of code (Pascal then said "Ok") |
| the lock hands the entity to 0xfc277c instead of setting timer 0x20 and handler 0xfc27be itself | the one-frame lock gives 196 frames to the load, the game's two-step lock 198; keeps lock 1402 and load 1600 | 0xfc277c runs twice per race start; the Task 2 review found it idempotent |
| the additions the brief did not name (`dirscreen_drive.lua`, `VR_REVERSE_TABLE` default in `run_mame`, `VR_DIRECTION_FORCE`, the `dirsides` table) | each is the smallest thing its test or routine needs | `VR_DIRECTION=1` alone no longer forces the flag on originals (§10) |
| `hudname` in its own module | a different responsibility | one more small module |
| `[0x501434]` restored after the name's print | a later reader would take the label's colour | about 12 bytes |
| names limited to 13 letters (the 14-byte field always ends in a NUL) | today's longest are 13 | a 14-letter name is refused at build time |
| the converted-entry case of `test_start_greys_the_other_courses` retired; Task 4's lock-look test takes its place | D7 removes the course select's START look on entries 3-9 | between Tasks 2 and 4 nothing pinned `start`'s palette body on a converted record |
| the transmission test releases START during the screen (test switch) | so it can catch a re-latch | none beyond a test switch |
| autoplay exits with an error when REVERSE is asked and the screen will not be answered | a silent normal race would hide a broken run | — |
| Task 3 kept compact (report past ~5 650, STOP past 6 000) | leave room for Tasks 4-6 | a later ruling to raise the bound |
| both sides show the entry's own picture in slot 0's and slot 2's blocks; the middle slot's blocks are Task 5's | D1 / D11 | none |
| Task 5's budget about 250 bytes, the bound raisable to 6 300 | Task 6 needs about 110 bytes | the tables move 300 bytes further (not needed: 5 678) |
| the draw list lives in the data block, `dirmaps` leaves the image | one loop for every copy and blit; 32 bytes of image back | the screen's game maps are ROM data outside the image |
| the lap sense read from the load record's `map_cross` | 0 bytes; two tests pin the equivalence | if the HUD map's shift is ever set for another reason the arrows follow it (fix: a 10-byte table) |
| the caption's palette copied at run time from palette RAM 0x73 to 0x6b | no game colour values in the repository | palette RAM may not read back on real hardware (§10) |
| the extra `hud_log.lua` line at the race load | `[0x501434]` is 3 on every course 60 frames in, so the brief's colour test could not fail | none |
| the `test_direction` hang fixed in the test's set builder, not in product code | real builds always carry the block; `ten_course_set` enforces it | a hand-built set with variants and no block still hangs on the screen (§10) |
| Task 7's pins invocation (Step 3) run by the session lead's whole-suite run, not by the implementer | the suite covers every file it names | a pin failure shows one step later |
| (concern A) the 34 boot-ROM bytes outside the plan's six sites are accepted | each is one byte of an address operand in an earlier project site whose target routine moved (+5 / +21) inside the directory image; that is the constraint's "up to relocated code-area addresses"; the plan's Task 7 wording ("only inside this plan's patched sites") was too narrow. Likewise not named by Step 1's wording for the program ROM ("only inside the code area and the data block"): 48 bytes in the annex (14 relocated words, 20 bytes of name NULs in the seven variant records) and the 33 bytes of name padding in the ten load records (Task 6's NULs) | none found; every byte is accounted for in `out/p26/stage3/t7/cmp_main.out` |
| (concern B) the middle-slot test asserts on content (no visible cell names a character still holding the direction screen's data), not on the character number | the game itself uses characters 0x3480..0x35ff after the race load (main's race names them too) and overwrites the blocks at the load; the number-only rule could never pass | 33 of the screen's characters stay in character RAM, unshown, until the attract load; a game screen that named one of those exact characters would show a fragment (none does in the modes run: race, goal, results, ranking, name entry, attract) |
| (final review, Important 1) D6's code stays as built for the playtest and D6 goes to Pascal as an explicit question (the arming rule as built, the design's literal rule, or relative to the wheel at the screen's start); the documents describe the built rule and say it departs from Pascal's approved wording pending their decision (Pascal decided it as built on 13 Nov, §12) | the literal rule opens the screen on REVERSE for entries 7-9 and most of 6 (the wheel is right of the threshold from choosing them) and the countdown would take REVERSE from a player who does nothing, which is what the recon's D6 question was about; the lead had no authority to settle it and should have asked before building | about 20 bytes of `dirsel` and its tests to change after Pascal answers, and a rebuild of the playtest set |
| (final review, Minors) fixed in one fix wave: 2 (autoplay does not answer early while a wheel sweep still moves at the early-press frame), 4 (the second game's two countdown locks asserted on the existing run), 5 (the title font cells 8 / 0x8000 and the text palettes pinned on the second select; recon §14's palettes item into §10), 6, 7, 8 (`rstrip(b"\0 ")`), 9 (`VR_DIRECTION_ONCE` removed; `slot_log.lua` takes the phase cell from `VR_DIRECTION_RAM`; `race_end.lua`'s `field()` errors on a missing field), 10, 11, 12. Parked to follow-ups: 3 (autoplay verifying `VR_REVERSE_TABLE` against the set) | the tests always build from the tree; a guard that scans the patched routine for the table's address is more machinery than the risk warrants before the drive | a run on a set built from another layout can press early or wait 10 s silently |
| (final review, declined to judge) into §10: the `[0x40dc9b]` = 0 map set against the screen's default panels and English caption; a coin during the screen; the attract's menu path onto the last-played converted course with the HUD name following the served record; `[0x40dc8c]` != 0 called "linked play" untraced; Metropolis's select band straddling the direction threshold. Left to Pascal's drive and eye: D7, D8, D9, the arrows' look and sense on the road, the frame over the title. Accepted as the design's: the transmission not shown on the direction screen. Noted in follow-ups: `spike/site_media.py`'s captures now pass through the direction screen | (the final review's list) | — |
| Task 8's rule is "the normal checkpoints renumbered, less any renumbered point p with 0 < p < `GATE_START_GAP`" rather than a return to stage 2's first code (`gate_checkpoints(reverse_gates(...))`) | it keeps "nothing fires in reverse that does not fire in the normal direction" and gives the same sets on all seven courses today | a future course with a normal checkpoint within 50 points before the line loses it in reverse (that is the rule Pascal chose) |
| the new playtest set is `out/p26play5`; `out/p26play4` is kept as the set Pascal drove | (keep the driven set) | 12 MB of scratch |
| the fix wave's re-review and Task 8 run at the same time (the re-review reads a diff file; anything it finds joins Task 8's fix round) | (time) | one more small fix commit |
| the whole suite runs on 257e79a while Task 8's review reads its diff; a review fix that touches only documents does not invalidate the run, one that touches code or tests means re-running what it touches or the whole suite | the suite takes three hours and Task 8's own tests passed | a second three-hour run (not needed: the review asked for document edits only) |
| Task 8 review's Minors 1 and 2 parked in follow-ups, not fixed (the new "nothing fires before the first checkpoint" check ends its window at the first sample at or past the gate, where the fire test allows up to 4 points past; the Diablo lap-sum tolerance of `len(checkpoints)` = 3 against a measured 1; a leftover print) | they are in a test file the running suite had collected; the run is deterministic and passes; the tolerance is the brief's and stage 2's | a future change that moves a fire onto that boundary sample fails the check misleadingly |

Parked by the lead (not fixed, Task 2 review): the countdown's voice cue at timer 0xE0 on the other `[0x40dc9a]` setting (§10); a
near-duplicate operator test; `run_mame` computing `directory_layout()` on every call.

## 3. ROM room, sites and RAM cells

**The directory image** (routines after the direction routines, plan D10). Sizes from the task reports:

| after task | image (0x278d70..) | bytes | `end − loader` (bound 6 000) |
|---|---|---|---|
| main (026df67) | ..0x27ab4d | 7 645 | 4 821 |
| 1 | ..0x27ab86 | 7 702 | 4 878 |
| 2 | ..0x27ace6 | 8 054 | 5 230 |
| 3 | ..0x27ae21 | 8 369 | 5 545 |
| 4 | ..0x27ae7a | 8 458 | 5 634 |
| 5 | ..0x27aea6 | 8 502 | 5 678 |
| 6 (final) | ..0x27af1d | 8 621 | 5 797 |

Final routines (bytes): `dirclear` 17, `rankgate` 40, `dirlock` 111, `dirsel` 160, `dirdone` 86 (falls into `dircursor`),
`dircursor` 41, `dirdraw` 261, `dirshow` 72, tables `dirsides` 16 and `dirtext` 32 (836 together, from 0x27ab62); `hudname` 116 at
0x27aea6 and its table `hudattr` 3 at 0x27af1a. In the select routines `draw` grew 158 → 178 (Task 3: `picture` takes its map's
destination and tile base from the caller), `picture` 988 → 973, `start` 227 → 243 (Task 2: its phase test); so `picture` moved
+20, `start` +5, and the ranking block and the stage 1-2 direction routines after it +21. The tables stored after the image (tile
tables, race blobs, spawn lists, the code-area pictures) moved +0x3d0 from main's places (§6).

**The data block** (plan D11, `tencourse.dirscreen_block()`): 0x2be8b0..0x2c0000, 5 968 bytes of the 8 192 allowed, erased in the
original and on main's build; `annex_regions()` ends the colour-run region at its start (the annex keeps about 7.5 KB past its end
0x2bcb00).

| part | address | bytes |
|---|---|---|
| rows (the draw list: 6 phases × 128) | 0x2be8b0 | 768 |
| clockwise arrow's characters (54) | 0x2bebb0 | 1 728 |
| anticlockwise arrow's characters (54) | 0x2bf270 | 1 728 |
| caption's characters (31) | 0x2bf930 | 992 |
| white set | 0x2bfd10 | 32 |
| red set | 0x2bfd30 | 32 |
| clockwise map | 0x2bfd50 | 300 |
| anticlockwise map | 0x2bfe7c | 300 |
| caption map | 0x2bffa8 | 84 |

**Boot sites** (each pattern-checked before it is patched, `PatchError` on a mismatch; listed in `tests/test_directory.py`'s spans):

| site | bytes | original | now |
|---|---|---|---|
| 0xfe3cce | 8 | `mov.b #0, 5019C0[PC]` (mode 0x10 state 0) | `jsr dirclear` + 2 nops |
| 0xfc40ce | 16 | `movz.bw #0, 5018FC[PC]; test1 #1, 501174[PC]` | `jsr rankgate` + 10 nops (the `be FC417C` after it stays) |
| 0xfe2b07, 0xfe1d37 | 0x16 each | `jsr bank` (the project's) | `jsr bankdemo` |
| 0xfc2788 | 9 | `mov.w #FC27BE, A[R25]` (in the lock handler 0xfc277c) | `jsr dirlock` + 3 nops |
| 0xff4799 | 6 | `jsr FF8926[PC]` (the HUD label's print) | `jsr hudname` |

**RAM cells** (plan D12): the flag 0x502294 (byte; every reader and writer in the project uses a byte access, checked in Task 1);
`DIR_PHASE` 0x502295 (0 no screen, 1 choosing, 2 locked), `DIR_ARMED` 0x502296 (1 once the wheel has been at or left of 0x1c),
`DIR_SHOWN` 0x502297 (0xff, 0xfe .. 0xfa while the six drawing phases run, 0xf9 once drawn, then the choice 0 or 1). `dirclear`
zeroes the four bytes in one word write.

## 4. The screen measured

Autoplay's answer on every run (Task 2 onwards): the early course press at 1200, its edge at 1202 (course lock), `dirlock` at 1204,
`dirsel` from 1206; the lift at 1210, the paddle 128 from 1210 (armed 4 frames later), 200 from 1300 with `VR_DIRECTION=1` (REVERSE
shown 2 frames later); the second press at 1400, its edge at 1402 locks the screen; handler 0xfc27be and timer 32 at 1404; mode
0x11 at 1600.

| measure | value | source |
|---|---|---|
| course lock → screen's handler | 1202 → 1204 | Task 2 |
| the drawing | DIR_SHOWN leaves 0xff at 1207, reaches 0xf9 at 1216, first choice written at 1218 | Task 5 |
| logic frames while drawing | every counter step +1 in 2 video frames (110 steps from 1190 to 1410) | Task 5 |
| one logic frame for all the drawing (Task 3's three phases) | fits in MAME with about one checker redraw to spare; three or six phases kept | Task 3 |
| direction lock → mode 0x11 | 198 video frames (lock 1402, load 1600), the game's | Tasks 2-6 |
| countdown, no press (entry 9) | lock 576 frames after the screen's first frame (1404 → 1980), load 2178; no steering NORMAL, 128 then 200 REVERSE | Task 2 |
| no press at all (Task 1's second game, nobody answering) | the course select's own countdown locks the course 1212 frames after its first frame (20594 → 21806: the timer 0x27e down to 0x20, no gas edge), `dirsel` 21808 → its countdown lock 22384 (576 frames), mode 0x11 at 22582 (198), flag 0 in that race; `out/p26/stage3/t7/pt/reverse0/end.txt` | asserted since the final review's fix wave |
| held gas from the course press | no edge, no lock until 1980; NORMAL | Task 2 |
| transmission (`VR_MANUAL=1`, START released on the screen) | `[0x501936]` 1 at the course lock and at the load | Task 2 |
| originals 0-2 | `dirsel` never seen; course lock → mode 0x11 198 frames; flag 0 | Task 2 |
| operator's fixed course | the SHIFT MODE SELECTOR's chain only; flag 0 | Tasks 1-2 |
| the cursor frame | box centres within 0.5 px of the pictures' centres at `SIDE_X` = ∓112.0, `SIDE_Y` = 65.0 | Task 3 |
| `[0x40dc9b]` = 0 | the countdown at rows 40-42 meets no piece; lock and load 198 frames apart | Task 3 |
| the lap sense (load record `map_cross`) | anticlockwise: 3 Alpine, 7 Pacific Coast; clockwise: 4, 5, 6, 8, 9 | Task 5 |

- **A reverse race records nothing** (Task 1): no write into Metropolis's table from the load on, 0x5018fc 0, no mode 0x1e; modes
  after the finish 19 1a 15 16 1b 1c 1d 02. The normal one-lap race still writes the table and enters the name (19 1a 15 16 1b 1c
  1d 1e 02).
- **The flag at the next select** (Task 1): after the reverse race the attract's pit scenes run with the flag 0 (at least six), and
  the second game's select starts with it 0.
- **The race against its parent** (Tasks 2-6, each task's STOP check): Metropolis normal 150 s under the autopilot, load on 1600,
  7 095 race-log lines from the load, identical to the previous task's build every time; Surfers Road reverse through the screen
  identical to the parent's `direction.lua` race (Task 2).

## 5. The course's name in the race HUD (Task 6)

- **The site:** 0xff4733..0xff4799 in 0xff471b (the HUD entity's first handler, run once at the race load) chooses the word by the
  data index `[0x501934]` and prints it with 0xff8926 on layer 0, rows 44-45, columns 51-58. Nothing redraws it until mode 0x15
  clears layer 0. 0xff4799 becomes `jsr hudname`.
- **`hudname`:** `entry` (the loader's lookup) gives the served load record. `race` 0 (an original): the printer is entered as the
  site entered it. Otherwise the record's name, right-aligned to column 58 (length counted to the NUL at run time), in the colour of
  the record's `label` (`hudattr`: 0x02 blue, 0x83 orange, 0x82 red); the colour cell `[0x501434]` is restored after the print.
- **The name field** (load record +0x1c, 14 bytes) is NUL-padded since Task 6 (it was space-padded); names at most 13 letters.
- **Measured** (`hud_log.lua`, keyed on the mode byte): ALPINE blue (0x8100), AMAZON FALLS orange (0xc180), DIABLO CANYON red
  (0xc100), METROPOLIS orange, PACIFIC COAST orange, SURFERS OVAL blue, SURFERS ROAD red, each in columns (59 − length)..58,
  columns 40 up to the name blank; reverse (entries 3, 9) the same cells; the originals BEGINNER / MEDIUM / EXPERT in their
  colours at 51-58; the goal (mode 0x1a) cells equal the race's; at the race load `[0x501434]` is the game's value again.
- **Not changed:** the linked slave's label site 0xff53ae..0xff53fa (row 15, column 52) is left as the game's: a linked slave
  shows the template's word.

## 6. The normal direction against main (Task 7 Step 1)

**Builds:** main 026df67 from `git archive` into `out/p26/stage3/t7/main_src/`, built with its own code by the CLI
(`python -m vrtools build`, run from that tree: `PYTHONPATH` loses to the checkout's editable install here) into
`out/p26/stage3/t7/main/`; this tree's CLI build is the playtest set `out/p26play4` (built at 92955b3). Both with the variants
(the CLI's normal build). Compared by `out/p26/stage3/t7/cmp_main.py` (output `cmp_main.out`), each tree's directory layout taken
from its own code (`layouts.json`).

| ROM | result |
|---|---|
| polygon ROM (16 777 216), TGP data (2 097 152), TGP program (8 192) | identical |
| data ROM | 20 bytes differ: 10 code-area pointers, each main's + 0x3d0 (bank 0, +0xde80c..+0xde844, pointing at the blocks after the spawn lists); nothing else |
| boot ROM | 72 bytes differ: 38 inside the plan's six sites (0xfe3cce 8, 0xfc40ce 16, 0xfe2b07 1, 0xfe1d37 1, 0xfc2788 8, 0xff4799 4); 34 bytes, one in each of 34 address operands (30 absolute, 4 PC-relative: 0xfc3b4f, 0xfc3b5e, 0xfe69f7, 0xfe6a18) of the project's earlier sites whose target routine or array moved inside the directory image: `start` +5 (0xfc27d6's `jmp`), +21 for the ranking block (0xfc270f, 0xfc3b4f, 0xfc3b5e, 0xfc3b6c, 0xfc3bf6, 0xfc3c33, 0xfc3cff, 0xfc4208, 0xfe69f7, 0xfe6a18), `dirattr` (its 14 sites), `startbit` (0xfe41d6), `figures` (0xfc0ea5) and the figures' seven animation sites. Each such operand is main's value + the move; no other byte differs |
| program ROM | 62 774 bytes differ: 5 959 in the data block (all 0xff on main); 56 767 in the code area; 48 outside both, in the annex: 14 relocated words (the seven variants' `tile_table` and `spawn_table`, + 0x3d0) and 20 bytes of the variants' name fields (spaces → NULs) |

Inside the code area, entry by entry at each one's own address:
- the ten load records: 21 relocated words (each converted entry's `tile_table`, `spawn_table`, `race`, + 0x3d0) and 33 bytes of the
  name fields (spaces → NULs, Task 6);
- `draw`, `picture`, `start`: changed by the plan (sizes above);
- the ranking block and the figures' routines: only relocated words (43 in the ranking block, one in each of five figure routines);
- the stage 3 routines appended;
- the tables from 0x27ab50 (main) against 0x27af20 (branch) up to the start-gantry block: 1 883 differing words, every one a
  code-area address + 0x3d0; main's 0x28f5a0..0x28f970, past the branch's tables, is erased; the gantry block 0x28f970..0x28fd70
  is identical.

So the boot ROM differs inside the plan's sites and, outside them, only in relocated operands of the project's own earlier sites
(the plan's text named only its own sites; the moves come from Task 2's `start` head and Task 3's `draw` / `picture` change), and
the program ROM outside the code area and the data block in the annex's 48 bytes (14 relocated words, 20 name NULs), with 33 bytes of
name NULs in the ten load records inside the code area: Step 1's wording did not name these; the lead accepted them as relocated
addresses and Task 6's planned padding (ruling A, §2).

**The race** (`out/p26/stage3/t7/baseline_run.py`, `compare.py`; Metropolis normal, 150 s under the autopilot, the same centreline
file for both; each tree's own runner and Lua):

| | main | this tree |
|---|---|---|
| the lock that starts the exit | the course lock: gas floored at 1400, edge at 1402 | the direction lock: course press at 1200 (edge 1202), screen 1204-1402, edge of the second press at 1402 (handler 0xfc277c, phase 2), 0xfc27be at 1404 |
| race load (mode 0x11, start_log's L line) | 1600 | 1600 |
| race-log lines from the load | 7 095 | 7 095 |
| comparison | IDENTICAL | |

The race log does not record tile RAM, so the HUD label (the plan's one exception) is not in it.

## 7. The data block's readers; the middle slot after the lock (Task 7 Step 2)

**Read tap** (`memtrace.lua`, reads 0x2be8b0..0x2bffff from frame 0; Metropolis reverse through the screen on `out/p26play4`, its
one-lap race with the clock held, the attract with six pit scenes, a coin, the second game's select and, unanswered, its own
direction screen; 430 s; `out/p26/stage3/t7/slot/tap/`):

| reader | reads | frames |
|---|---|---|
| the boot's colour-table upload, PC 0xfe6b64 | 2 984 (each halfword once) | 203-204 |
| `dirdraw`'s row loop (0x27add8, 0x27ade0, 0x27aded, 0x27adfe) | 4 692 | 1206-1215 (the screen), 24124-24133 (the second game's screen) |
| the game's blit 0xff9436 called by that loop, reading the block's maps (0xff943c..0xff9484) | 684 | the same frames |

No other reader: none in the race, the results, the attract or its pit scenes.

**The middle slot after the lock** (`tests/test_dirscreen_build.py::test_no_screen_after_the_lock_shows_the_middle_slot`;
`slot_log.lua`). Since Task 5 the middle slot's characters 0x3480..0x35ff (palettes 0x69-0x6b) hold the arrows and the caption
from the direction screen on. `slot_log.lua` scans, every second video frame (one scan per logic frame; a cell shown on one odd
video frame only would be missed), the visible cells of the four tile layers (the 62 × 48 window
each layer's scroll words give, as MAME's `segas24_tile_device::draw_common` draws it; a layer with its disable bit is skipped):
the cells that name a character of 0x3480..0x35ff, and those of them whose character still holds the locked screen's data
(taken at the lock's first frame). It dumps tile RAM and the middle slot's characters 2, 60 and 300 frames after every mode change
(the mode byte 0x501138) from the race load on. Measured on the playtest set (scratch `out/p26/stage3/t7/slot/`) and in the
committed test's two runs (Task 1's Metropolis runs: reverse to the second game's select; normal through the name entry). Scratch
logs: `out/p26/stage3/t7/slot/reverse/slot.txt` and `out/p26/stage3/t7/slot/normal/slot.txt` (the S and D lines; their dumps
under `slot/`), `out/p26/stage3/t7/slot/{reverse,normal}/end.txt` (`race_end.lua`'s modes), main's scan
`out/p26/stage3/t7/runs/main_slot/slot.txt`.

**The plan's rule was changed** (the lead's ruling on concern B, §2). The plan asked that no visible cell name a character of
0x3480..0x35ff (or palette 0x69-0x6b) before the next select. The game itself names those characters after the race load (below:
the race's backdrop layer, the results, the attract, the name entry; main's race too), after uploading its own characters into the
blocks, so that rule could never pass. The test asserts instead that no visible cell names a character that still holds the
direction screen's data; the raw counts are printed.

- **The positive controls.** At the lock (1402) and 60 frames on (1462) character RAM holds the built set's arrows and caption in
  the middle slot; 156 layer-0 cells name them and show them (two arrows of 60 cells and the 36-cell caption); the scan and the
  dump agree (`slot/{reverse,normal}/slot.txt`, the S line of frame 1402). The course select itself shows 336 layer-0 cells naming
  the middle slot (its middle picture; the S lines of frames 618 and 22908 in `slot/reverse/slot.txt`).
- **The race load overwrites the middle slot.** Between frames 1602 and 1604 (mode 0x11) the race uploads its own characters into
  the three blocks: of the locked screen's 344 non-blank middle characters 182 are unchanged after it (the S lines' `kept` field,
  frames 1602 and 1604 of both `slot.txt`), of the 139 the screen itself wrote (54 + 54 + 31; none of them blank) 33 (clockwise arrow
  characters from 0x34a7; from the dumps under `slot/normal/slot/`); the attract load (mode 0x02) overwrites those too (0 left).
- **Cells that name the middle slot after the lock** (the scratch runs on the playtest set, `slot/{reverse,normal}/slot.txt` from
  frame 1602, the reverse one up to 22906; most in one scan; every one on layer 2, the backdrop's layer, except the
  name entry's on layer 0):

  | mode | reverse run | normal run |
  |---|---|---|
  | race load 0x11, grid 0x12, 0x13 | 135, 137, 32 | 135, 137, 137 |
  | race 0x14 | 192 | 192 |
  | goal 0x19 / 0x1a | 32 / 192 | 137 / 191 |
  | results 0x15 | 125 | 68 |
  | race-end ranking page 0x1b-0x1d | 125 | 67 |
  | name entry 0x1e | — (a reverse race records nothing) | 28 (layer 0) |
  | attract 0x02, 0x03, 0x06, 0x07, 0x08 | 135, 480, 480, 241, 0 | 135, 192 (the run ends in 0x03) |
  | game start 0x0a (the second game) | 189 | — |

  None of them shows the locked screen's characters: 0 cells on every scan from the race load (frame 1602) to the second game's
  mode 0x0f (frame 22906, the S line in `slot/reverse/slot.txt`), and in every dump (reverse 123 of its 138 D lines lie before
  22906, normal all 42, in the scratch runs). The same layer-2 cells occur on main: a 150-s Metropolis race on main's build names up
  to 192 layer-2 cells of 0x3480..0x35ff in mode 0x14 (`runs/main_slot/slot.txt`), as here (192, `slot/normal/slot.txt`). These are the race's (and the
  attract's) own characters uploaded into those blocks.
- **The name entry page** was reached by the normal run (mode 0x1e from frame 9591 in the scratch run, `slot/normal/end.txt`; 6503
  in the committed test's run, `pt/normal0/end.txt`); `race_end.lua`'s held clock placed the car first. The reverse run has no name entry (§4).
- The snapshots taken at each dump of the scratch reverse run (`out/p26/stage3/t7/slot_reverse_sheet.png`) show no arrow or caption
  on any screen after the lock.
- The committed test asserts the zero counts (scan and dumps), that the run reached the race, the goal, the results, the race-end
  ranking page, the attract (and the name entry on the normal run, the second game's mode 0x0f on the reverse one), that each of
  those modes has a dump, and the positive controls. The raw counts above are printed, not asserted: the race's own use of those
  character numbers is the game's. In Task 7's invocation (§11) it passed on both runs: the locked screen 156 layer-0 cells naming
  and showing the arrows and caption (scan and dump alike); the reverse window frames 1602 to 20592 (the second game's mode 0x0f),
  123 dumps; the normal window 1602 to the run's end, 57 dumps (the test's printed lines in `out/p26/stage3/t7/pytest_mame.txt`), the name entry among its modes; 0 cells showing the locked screen's
  characters on every scan and in every dump; the locked screen's 344 non-blank middle characters down to 0 by the window's end.

## 8. Suite

The whole suite, run by the session lead on the tree at 257e79a (Task 8's last commit; the only later commits change documents):
`.venv/bin/python -m pytest -o addopts="" -q -rfEX -p no:cacheprovider --basetemp out/p26/stage3/fullbt` (log
`out/p26/stage3/full.log`): **15 failed, 975 passed, 1 xpassed, 50 warnings in 12084.33s (3:21:24)**.

- The 15 FAILED names are exactly the 15 known on main (`docs/spike/2026-11-phase26-stage2-findings.md` §8), compared by name
  as sets (`out/p26/stage3/full_failed.txt` against stage 2's `out/p26/stage2/full3.log`): none new, none gone. Five in
  `test_convert_collision`, one in `test_convert_geometry`, two in `test_convert_profile`, three in `test_race_build` (Diablo
  Canyon's first right turn at0 / at1, the player's pitch on Diablo), four in `test_tgp_build`.
- The xpass is main's (`test_regenerated_big_forest_drives`); the 50 warnings are main's (Pillow's `getdata` deprecation in
  `tests/test_site_page.py`).
- Main's last run was 868 passed (stage 2); the 107 more are this stage's tests.
- The run was started while Task 8's review read its diff (lead's ruling, table above); the review asked for document edits only
  (commit 1c35592), so the tree the suite ran on and the merged tree differ in documents only.

Task 7's invocation (the new test with the screen's files): see §11.

## 9. The playtest set and the contact sheet

- **The set:** `out/p26play4` (`.venv/bin/vrtools build --roms "$VR_ROMDIR" --saturn "$VR_SATURN_CUE" --out out/p26play4`, at
  92955b3, `build-report.txt` beside it; build log `out/p26/stage3/t7/play4_build.log`), not committed. A headless 30-s
  `run_mame` of `memtrace.lua` on it boots to the attract: the mode bytes read 0x03 at frames 480, 1 000 and 1 600
  (`out/p26/stage3/t7/bootcheck/`).
- **Since Task 8:** `out/p26play5` (§12.3), the same set but for Diablo Canyon's reverse race blob; `out/p26play4`, the set
  Pascal drove, is kept.
- **How to race in reverse on it:** pick a converted course with the gas, then lift the gas. To choose REVERSE, bring the wheel
  back to straight or left first, then turn it right, then press the gas. Doing nothing gives NORMAL after the 10-s countdown, and
  so does keeping the wheel right from the course select and pressing again: the choice starts NORMAL and the wheel counts only
  once it has been straight or left on this screen (D6 as built, decided by Pascal on 13 Nov: §2, §12). A plain `mame vr -rompath out/p26play4` is enough; a launcher like stage 2's
  `out/rec155/launch.sh` (normal) works. Stage 2's reverse launchers (`out/rec154`, `out/rec156`) run `direction.lua`
  standalone with `VR_DIRECTION=1`, which on a stage-3 build holds the flag at 1 on the select screen over the screen's choice:
  they are no longer the way to race in reverse.
- **Contact sheet** `out/p26/stage3/look/sheet.png` (run-time artefact, not committed; runs `out/p26/stage3/t7/look/`, script
  `look.py`): for the seven converted entries answered REVERSE, the screen with NORMAL shown (1252), with REVERSE shown (1372),
  locked (1432) and the race's bottom right 400 frames after its start; Alpine answered NORMAL (its NORMAL lock); the three originals'
  bottom right. Looked at by eye:
  - on every converted entry the NORMAL side's arrow is white and the REVERSE side's red; the NORMAL arrow is anticlockwise on
    Alpine and Pacific Coast and clockwise on the other five, the REVERSE arrow the other sense, as §4's lap sense table;
  - the frame and the yellow label on the shown choice; at the lock the other picture grey, the arrows keep their colours (by
    design, D8 and Task 5); Alpine's NORMAL lock greys the REVERSE picture;
  - the SELECT DIRECTION caption on every screen; no stray tile seen; the countdown reads 9 at 1252, 7 at 1372 and 0 at 1432
    (after a lock the timer is 0x20 and runs down, as after the game's own course lock);
  - the HUD names right-aligned and whole (ALPINE, AMAZON FALLS, DIABLO CANYON, METROPOLIS, PACIFIC COAST, SURFERS OVAL, SURFERS ROAD)
    in blue, orange, red, orange, orange, blue, red; the originals BEGINNER blue, MEDIUM orange, EXPERT red; nothing clipped; on
    Alpine the HUD map's outline passes behind the name.
  - Whether each arrow's sense matches the way the picture's road is driven cannot be read from a picture (it shows no direction);
    the sense comes from the centreline's signed area, which Task 5 checked against the race's HUD map on Metropolis and Alpine.

## 10. Not verified, known limits

- **Linked play:** the screen is bypassed when `[0x40dc8c]` != 0 (`dirlock`'s test; autoplay's error reasons for linked play, the
  wrong mode and the wrong handler were not exercised); checked statically only, with the two linked bank sites. The linked
  slave's HUD label site 0xff53ae..0xff53fa is left as the game's (a slave shows the template's word).
- **Real hardware:** the layer order (pictures on layer 2 under the arrows on layer 0; MAME's draw order is the reference); the
  drawing time of the screen's first phase (MAME's V60 timing is not exact; about two thirds of a logic frame spare in MAME);
  reading palette RAM back for the caption's palette.
- **Operator settings:** `[0x40dc9b]` = 1 not run (0 and the default 2 run); `[0x40dc9b]` = 0 after the lock not covered. On the
  other `[0x40dc9a]` setting the countdown's voice cue at timer 0xE0 also plays on the direction screen (read, not run).
- **A gas press during the screen's first six logic frames** (about 0.2 s, while it draws) is not seen.
- **Coverage by committed tests:** the Alpine NORMAL lock look and entries 4, 5, 7 and 8 on the screen are not covered by a
  committed test (the contact sheet covers them by eye, §9). Two of Task 4's tests are regression guards (they would have passed
  on Task 3's build).
- **A pit stop with the HUD name** was not driven (no clear or label-row write in the pit code was found, read only).
- **The HUD name to the goal** is run on Metropolis only (10 letters, columns 49-58); the 13-letter names (DIABLO CANYON,
  PACIFIC COAST, columns 46-58) are checked 60 frames into the race and on the contact sheet only.
- **The attract demo** can take the menu path onto the last-played converted course (the lookup predates this branch); the HUD
  name then follows whatever record the loader served. Not run.
- **The middle slot after the lock** (§7): the committed test covers characters only. The plan also named palettes 0x69-0x6b; on
  main those palettes held course-dependent picture colours, so the race must rewrite them, but that is inferred, not measured.
- **The text's palettes** (recon §14: whether anything rewrites palettes 0x84 / 0x85, the yellow labels, while a select screen is
  up). `test_the_course_select_after_a_reverse_race_is_clean` now asserts that the palettes the labels and the title use (4, 5,
  0x84, 0x85, 8-10) and the countdown font's cells (`[0x501438]` = 8, `[0x50143c]` = 0x8000, which `dirdraw` uses without
  setting them; mode 0x0f's upload sets them, 0xfe6bb9..0xfe6bc9) are the same 300 frames into the second game's select as into
  the first's. That closes the second-game part. Still open: a rewrite while a select screen or the direction screen is up (both
  measured at single frames), and the palettes on the direction screen itself (its tests assert tile words; the colours are seen
  on the contact sheet only).
- **`[0x40dc9b]` = 0:** the course select draws its other map set (0xfc2b9c) while the direction screen draws the default set's
  panels and English caption. The design is silent on operator language settings; not judged.
- **A coin during the screen:** nothing in states 1 / 6 or the screen's handlers reads it (read); not run.
- **"Linked play"** is `[0x40dc8c]` != 0 throughout. Whether a single-cabinet operator mode also sets that cell (the screen would
  then be absent there too) was not traced.
- **Metropolis and the threshold:** Metropolis's select band (wheel value R10 26..50) straddles the direction threshold (28) and
  there is no hysteresis, so a wheel resting where it chose Metropolis can arm and flip the choice on a small movement. For
  Pascal's drive.
- **A hand-built set with variants but without the data block** hangs on the screen (`dirdraw` runs its draw list from erased
  ROM). `ten_course_set` always installs the block and refuses foreign bytes; tests build such sets only with the block since
  92955b3. Task 6's old `no-flag` case was not rerun on the old set to show it passed while hung (inferred).
- **Test switches since Task 2:** `VR_DIRECTION=1` chooses REVERSE on the screen (autoplay answers it); `VR_DIRECTION_FORCE=1`
  loads `direction.lua` to force the flag where no screen sets it; `VR_DIR_ANSWER=0` with `VR_DIRECTION=1` races normal silently
  (intended); a race load before frame 1200 makes autoplay exit with "the mode is not 10". A `VR_WHEEL_SWEEP` still moving at
  the early-press frame (1200) is not answered early (since the final review's fix wave): the gas at 1400 locks the course as
  before the screen existed, a screen that opens is left to its countdown, and autoplay writes one line to stderr (with
  `VR_DIRECTION=1` it exits with an error instead). Autoplay trusts `VR_REVERSE_TABLE` (this tree's layout) without checking it
  against the set under test (parked: `docs/follow-ups.md`).
- **Cosmetic:** `picture` blanks its destination first, so layer 2's checker has a hole for part of the frame it copies in; the
  rows table spends 768 bytes on fixed 128-byte slots, mostly padding; 33 of the screen's characters stay in character RAM from the
  race load to the attract load (none shown, §7).
- **Not established:** the service-mode ROM test on a set with the data block (it lies in the run the original keeps erased, as
  the annex does).
- **Driven by Pascal:** `out/p26play4`, two sessions on 13 Nov (§12); `out/p26play5` (Task 8's set) not yet. Stage 2's open items (turned grid cars, Diablo Canyon's frame budget, Pacific
  Coast's rock, opponents cutting bends, the two questions to Pascal) stand as `docs/follow-ups.md` has them.

## 11. Status

- Built and measured as above. A normal Metropolis race under the autopilot gives main's race log from the load on (§6; the log
  does not record tile RAM, so the HUD label, the plan's one exception, is not in it); the originals and the attract are covered
  by the ROM comparison only. The boot ROM differs outside the plan's sites only in relocated operands of the project's earlier
  sites, and the program ROM outside the code area and the block only in relocated words and name NULs (§6, ruling A).
- Task 7's MAME invocation: `.venv/bin/python -m pytest -o addopts="" -s -rA -p no:cacheprovider tests/test_dirscreen.py
  tests/test_dirscreen_build.py --basetemp out/p26/stage3/t7/pt` (log `out/p26/stage3/t7/pytest_mame.txt`): **60 passed in
  963.77s (0:16:03)**, both cases of `test_no_screen_after_the_lock_shows_the_middle_slot` among them.
- Pascal drove `out/p26play4` on 13 Nov and decided D6 as built and Diablo Canyon's reverse checkpoints (§12); the playtest set
  with that change is `out/p26play5`.
- The whole suite on the final tree: the 15 known failures only (§8). Merged into main and pushed on 13 Nov on Pascal's "Merge
  and push when ready". `out/p26play5` (Task 8's change) not yet driven.
- Next: pit stops in reverse. A score table for reverse races is a stretch goal, kept separate (§12.1).

## 12. After Pascal's drive (13 Nov): the decisions, and Diablo Canyon's START arch no reverse checkpoint (Task 8)

### 12.1 The drive and what Pascal decided

- **The drive.** Pascal drove the playtest set `out/p26play4` on 13 Nov in two sessions (the session lead's launcher
  `out/rec157/launch.sh`, no Lua, the screen choosing; recordings `out/rec157/inp/play_1.inp` and `play.inp`, not committed).
  Their words: "feels great but i ve spotted a bug for the reverse track: the checkpoints are located at the same location as in
  the normal i believe so one checkpoint is right after the start grid (at least on diablo)".
- **The cause** (the session lead's investigation): not a stage 3 fault. Diablo Canyon's reverse checkpoints were (0, 36, 168,
  278) since stage 2's drive (design §6.7, stage 2 findings §11.4): there Pascal drove under the Saturn's START arch, forward
  point 421 of 457, drawn but silent 36 points after the reverse start, and chose that it fires. The other six courses' first
  reverse checkpoint is 88 or more points after the start. The gates are shared scenery (`hide_unused_gates` edits the Saturn
  course before conversion), so a gate cannot be hidden in reverse only without direction-specific scenery.
- **The choice** (Pascal, 13 Nov, answering "2" to three options the session lead put to them): **the arch stays as scenery but
  is no checkpoint in reverse; three checkpoints per lap, the same total lap time spread over them.** It reverses their stage 2
  drive choice. The options as shown: (1) keep it: the arch fires right after the start, no cost; (2) the arch stays as scenery
  but is no checkpoint, three checkpoints a lap with the same total lap time spread over them (432 / 283 / 460 against
  200 / 306 / 255 / 415): the lead's recommendation and the first reverse build's behaviour; (3) remove the arch in reverse: not
  cheap, the gates are scenery both directions share, and whether the arch has collision posts was not checked.
- **D6** (§2): "the wheel rule work great for the reverse/normal": the rule as built is Pascal's; the design's §2 item 3 states
  it with the date.
- **Pit stops and a score table in reverse** (Pascal, 13 Nov, asked whether they are planned): pit stops in reverse stay the next
  stage; a score table for reverse races is "separate for now", "a stretch goal". The design's non-goal on rankings stands (no
  battery RAM for more tables, first recon §3.2); a recon of that limit only if they ask for it.
- Pascal did not comment one by one on D4's yellow label, the lock look, D5, D7, D8 or D9.

### 12.2 What was changed

`reverse.reverse_checkpoints(checkpoints, n)`: the normal lap's checkpoints renumbered for the reversed lap, (n − g) mod n sorted,
the line 0 staying 0, **less any renumbered point p with 0 < p < `race.GATE_START_GAP` (50)**: Phase 22i's start rule applied in
reverse as it is forward (the line fires instead). `GATE_END_GAP` is not applied again and stage 2's first code path
(`gate_checkpoints(reverse_gates(...))`) does not come back (the lead's ruling, §2): nothing fires in reverse that does not fire in
the normal direction. "Reversing twice gives the normal set" now holds only where no point was dropped. The lap-total rule (plan
D4, `race.time_records_for(..., lap_total=)`) spreads the normal lap's total over Diablo Canyon's three reverse sectors; on the
six other courses its factor stays 1. The normal blobs, the drawn gates, the tables and the spawn lists do not change.

### 12.3 Measured

- **Reverse checkpoints**, before (`out/p26play4`, decoded) and after (`out/p26play5`; the same from the tests' conversion):

| course (road points) | normal | reverse before | reverse after |
|---|---|---|---|
| Alpine (452) | (0, 65, 192, 333) | (0, 119, 260, 387) | unchanged |
| Amazon Falls (330) | (0, 117, 237) | (0, 93, 213) | unchanged |
| Diablo Canyon (457) | (0, 179, 289, 421) | (0, 36, 168, 278) | **(0, 168, 278)** |
| Metropolis (365) | (0, 126, 222) | (0, 143, 239) | unchanged |
| Pacific Coast (410) | (0, 186, 320) | (0, 90, 224) | unchanged |
| Surfers Oval (387) | (0, 127, 299) | (0, 88, 260) | unchanged |
| Surfers Road (441) | (0, 127, 299) | (0, 142, 314) | unchanged |

- **Diablo Canyon's reverse records** (initial 2080): level 0 variant 0 **432, 283, 460**, variant 1 **418, 274, 445**: the
  values of stage 2's first reverse build (stage 2 findings §11.4, "reverse before"), the same figures. First-lap sums of the 12
  records against the normal ones: 1175 1175 1200 1200 1137 1143 1172 1179 1147 1147 1171 1171 against 1176 1176 1199 1199 1137
  1143 1173 1179 1148 1148 1171 1171 (at most 1 apart, rounding; the test allows `len(checkpoints)`, 3). The six other courses'
  sums are equal and their variant records unchanged; `check_laps` passes (Diablo: 3 per lap, 5 laps of the record's 23).
- **Nothing else moves** (`out/p26/stage3/t8/cmp_sets.txt`, `cmp_summary.txt`): `out/p26play5` against `out/p26play4`, every
  file of `vr.zip`, `m1comm.zip` and `model1io.zip` identical except the program ROM pair (epr-14882.14 / epr-14883.15). In the
  program ROM 408 bytes differ, all in 0x2ba7e4..0x2bac71, inside Diablo Canyon's reverse race blob (0x2ba7b0..0x2baec0): 402 in
  the 12 time records (0x2ba7e0..0x2bac60) and 6 in the checkpoint record (0x2bac60: the count 4 → 3 and the points
  36, 168, 278 → 168, 278). The blob's 12 record pointers and its car table are identical; every other blob, tile table, spawn
  list, the directory, the boot, data, polygon and TGP ROMs are identical.
- **The reverse race on Diablo Canyon** (150 s, autopilot, `VR_DIRECTION=1` answering the screen; `tests/test_reverse_build.py`,
  log `out/p26/stage3/t8/pytest.txt`): the green (the clock's first count) at frame 1866 with the player on point 0. From the
  green to the player's first frame on point 168 (frame 3876) the clock only fell, 2079 → 1074; the player passed the arch
  (reverse point 36) at frame 2276 with the clock at 1874 and nothing fired. Fires in the race window: (169, +431), (279, +282),
  (0, +459), (169, +431): the record's 432, 283, 460 each less one (stage 1's form), in order. The clock never ran out
  (`expired_at` None; the dump-sampled count 4 extensions).
- **The field, every bound as before** (none touched): laps at every crossing (no step back, no wrap without the lap byte
  rising; wraps 1 for the player and 14 of 15 opponents, car 1 none, as in the normal run); frames on point 456 per crossing
  8-20; 15 moved, none parked (bound 2), largest backstep 0 (bound 25), cursor lead 2 field / 9 crossings (bound 20), leader 723
  points (floor 500); jolts 118 against the normal run's 95 (bound 152.5); grid yaw largest 37.4 (KNOWN FAULT bound 37.9);
  start cars 7 and 8 (bound 2); the direction turned on 54 183 of 54 183 samples, no wrong-way read. These are stage 2
  §11.4's figures but for the fires.
- **Metropolis normal baseline** (`out/p26/stage3/t8/runs/`, `compare.txt`): 150 s under the autopilot, the race log from the
  load on identical on `out/p26play5` and on `out/p26play4` (load on frame 1600 on both, 7 095 lines), and identical to the
  final fix wave's reference run (`fix/runs/fix_metro_normal`).
- **The playtest set** `out/p26play5` (`.venv/bin/vrtools build --roms "$VR_ROMDIR" --saturn "$VR_SATURN_CUE" --out
  out/p26play5`, build log `out/p26/stage3/t8/build_play5.log`, not committed): a headless 30-s `memtrace.lua` run boots it to
  the attract (the mode byte 0x03 at frames 480, 1 000 and 1 600; `out/p26/stage3/t8/bootcheck/`). Not yet driven.
- **Command** (one session, a fresh conversion): `.venv/bin/python -m pytest -o addopts="" -s -v -rA -p no:cacheprovider
  --basetemp=out/p26/stage3/t8/pt` over `tests/test_convert_reverse.py`, `tests/test_convert_race.py` and
  `tests/test_reverse_build.py` (entries 3, 5 and 9 where parametrized, every other test of the files; the ids in
  `out/p26/stage3/t8/ids.txt`): **68 passed in 1136.09s (0:18:56)**.
