# Phase 35 recon: a best-time table for reverse races on all ten courses (16 Nov 2026)

Read and measure only: no product code changed. Branch `phase35-reverse-times-recon` (from main c94d7d9), local.
Phase 33 (`phase33-originals-reverse`, 6d21a14, not merged) was read, not touched.

Marks: **[V]** verified here by a headless MAME 0.289 run or a byte read on the built set `out/p35play1`
(main before Phase 32 was merged: four program ROM members differ from a build of c94d7d9; the ranking code is the
same, and the gate of §11 was run on a fresh build of c94d7d9);
**[V27]** verified by the Phase 27 recon's runs (`docs/spike/2026-11-phase27-reverse-ranking-recon.md`), not repeated;
**[R]** read in the code or the docs; **[calc]** arithmetic or an estimate; **[?]** not established.

## 0. The owner's decision, and the answer in brief

Pascal's words, all of them on this subject:

- 15 Nov 2026, to a list of recommendations that included "best times three per table on all ten reverse courses,
  decided before next release": **"Yes all your recommendation"**.
- 16 Nov 2026, asked whether to start this work now, beginning with a short recon that brings back its questions before
  building: **"yes"**.

At the time of the recon (§0 to §9) no layout, look or migration choice had been made by them. Their answer to this
recon's five questions, later on 16 Nov, is in §10: **four times a table on all ten**, which supersedes "three per
table". The gate that answer depends on is §11: **passed**.

What the recon found:

- The battery RAM has **78 bytes free** in the two runs Phase 27 used (3 + 75) [V]. An entry is 24 bytes.
- **Ten tables of three fit there (769 of 787 bytes)** only if four of the seven existing tables move and every
  fourth entry is dropped. A v0.2.1 player loses the fourth best reverse time of each of the seven courses.
- **There is other unused battery RAM**: 286 bytes after the S-RAM magic and 244 after the game's record, neither
  read nor written in any run made so far [V27, V]; the test menu's backup clear leaves them alone [V]. This is the same
  kind of evidence the ten normal tables' places have rested on since Phase 22r. With them, **all ten courses can keep
  four reverse times and nothing saved moves or is lost**.
- The premise of "three per table" was the 78 bytes. Which of the two Pascal wants is the first question (§6).
- A page of three rows works with the game's own page code (the row count poked from 4 to 3: three rows drawn, the
  normal pages unchanged) [V].
- The same default-time rule serves the originals: Bay Bridge and Big Forest 4'00, Acropolis 5'00, then 5 s steps [V].
- **For the builder: this builds on the branch `phase33-originals-reverse`** (not on main, where an original has no
  reverse race) **and removes its `rankgate3`** (§3).
- **For the owner of the Phase 33 branch** (that branch was not edited from here): its recon's §6.6 says Phase 27 "is
  on main but in no public release". That is stale: the README says v0.2.1 (15 Nov) released Phase 27, so saved
  four-entry reverse tables exist on players' machines.

## 1. The battery RAM today (main c94d7d9; the same layout as v0.2.1)

MAME's file `nvram/vr/nvram` is 65 536 bytes, the bytes of `0x400000..0x40ffff` in address order (the magic and the
tables decode at `address − 0x400000`, little-endian) [V]. The boot clears everything below `0x40e000` [R, `ranking.py`].
An entry is 24 bytes: rank u32 (+0), time u32 in 1/32 s (+4), view (+8), −1 or the player's word (+0xc), time again
(+0x10), three letters and a NUL (+0x14). The insert never writes +0: the ranks stay as the initialiser wrote them [V27].

Measured on `out/p35play1`: a boot on no battery RAM and 400 s of attract with a write tap on `0x40e000..0x40ffff`,
then the saved file decoded (`out/p35/recon/fresh`) [V]:

| Address | Bytes | What | Written by |
|---|---|---|---|
| `0x40e000`, `0x40e240`, `0x40e480` | 3 × 576 | the game's own tables: Bay Bridge, Acropolis, Big Forest (ranking ids 0, 1, 2), 24 entries each | the stock initialiser, frame 6 |
| `0x40e6c0`, `c4`, `cc` | 3 × 4 | their slot words (`0x40e6c8`: an unused fourth word, 0xff) | initialiser |
| `0x40e6d0..0x40e6e1` | 18 | the magic `S-RAM CHECK OK 10` and its NUL (the project's since Phase 22r; the arcade's ends `!!`) | the boot's S-RAM check |
| `0x40e6e2..0x40e7ff` | **286** | **0xff, never written** | - |
| `0x40e800..0x40e9ff` | 512 | the game's bookkeeping | every frame of a game, the attract load |
| `0x40ea00`, `0x40ec40` | 2 × 576 | normal tables of ids 3, 4 (Alpine, Amazon Falls) | initialiser |
| `0x40ee80`, `0x40eee0`, `0x40ef40`, `0x40efa0` | 4 × 96 | **reverse tables of entries 3..6**, 4 entries each | `revinit` |
| `0x40f000..0x40f00b` | 12 | the game's record | every boot |
| `0x40f00c..0x40f0ff` | **244** | **0xff, never written** | - |
| `0x40f100`, `0x40f340`, `0x40f580`, `0x40f7c0`, `0x40fa00` | 5 × 576 | normal tables of ids 5..9 | initialiser |
| `0x40fc40..0x40fc67` | 40 | ten slot words by ranking id; **the first three (12 bytes) are never used** (the originals keep `0x40e6c0..`), 0xff | `slot_init` (ids 3..9) |
| `0x40fc68` | 1 | the ranking id of the course selected | course select |
| `0x40fc69` | 1 | the id whose table was last chosen (the title reads it) | every setter call |
| `0x40fc6a..0x40fc6c` | 3 | the three attract groups' counters | the attract page, `raceend` |
| `0x40fc6d..0x40fc6f` | **3** | **0xff, free** | - |
| `0x40fc70`, `0x40fcd0`, `0x40fd30` | 3 × 96 | **reverse tables of entries 7..9** | `revinit` |
| `0x40fd90..0x40fdab` | 28 | the seven reverse slot words | `revinit`, the insert |
| `0x40fdac` | 4 | the tag `REV4` | `revinit` |
| `0x40fdb0`, `0x40fdb4` | 4 + 1 | the last entry's offset (0x228 or 0x48) and the page's row count (6 or 4) | every setter call |
| `0x40fdb5..0x40fdff` | **75** | **0xff, free** | - |
| `0x40fe00..0x40fecf` | 208 | the stack's margin (the deepest stack byte seen: `0x40fed0`) | - |

**Free: 3 + 75 = 78 bytes** in the two runs Phase 27 worked in (`0x40ee80..0x40efff`, 384, and `0x40fc6d..0x40fdff`,
403; 709 of 787 used) [V]. Outside them, unused: the 12 bytes of the three unused slot words, 286 and 244.

**No checksum.** The layout is told by two marks [R, V]:

| Battery RAM saved by | Magic at `0x40e6d0` | Tag at `0x40fdac` |
|---|---|---|
| the arcade, or the project before Phase 22r | `S-RAM CHECK OK !!` | 0xff |
| v0.2 (Phase 22r to 26) | `S-RAM CHECK OK 10` | 0xff |
| v0.2.1 and main | `S-RAM CHECK OK 10` | `REV4` |

**Boot** [R `ranking.py`, V the writes on frame 6]: the S-RAM check first calls `revtag`: the tag is not `REV4` →
`revinit` writes the seven reverse tables (ranks 1..4, default times, names YU., RNS, TKG, NAG), the seven slots and
the tag; no other byte. Then the check compares the magic; on a mismatch the stock initialiser (`0xfc3b49`) writes all
ten normal tables, `slot_init` the slots and the ranking id, and calls `revinit` again; then the magic is written.
So: a fresh battery RAM gets everything; a v0.2 one gets the reverse block alone, every saved time kept; a v0.2.1 one
is not written at all.

**The test menu's BACKUP RAM CLEAR** (driven headless as the standing test drives it, `out/p35/recon/clear`) [V]:
on one frame the ten normal tables and the whole reverse block are written again with the defaults (a poked reverse
time and a poked normal time both came back to their defaults; the tag stays `REV4`). **It writes nothing else of the
ranking area**: marker bytes poked at `0x40e6f0`, `0x40f010` and `0x40fdc0` before the clear were still there after it.
A table placed in any free byte is therefore reset only if the project's own `revinit` resets it.

**The two larger unused runs** (286 at `0x40e6e2`, 244 at `0x40f00c`):

- neither read nor written through boot, attract, coin-up, course select, the direction screen, a normal and a
  reverse race to the end, the name entry and a second game [V27, read and write taps];
- not written in 400 s of boot and attract [V]; neither read nor written through the entry into the test menu and the
  backup clear (`out/p35/recon/rw`; the tap's control range on a reverse table counted its writes) [V];
- no direct reference in the boot ROM's listing [V27: R];
- **not tapped**: the other test-menu pages, linked play [?]. The same is true of the bytes the seven normal tables
  (since Phase 22r) and the seven reverse tables (v0.2.1) live in: all were chosen on taps through boot, attract and
  races, and Phase 27's recon says so in its §5 and §9.

## 2. The options: bytes

Entry 24 bytes; a table also needs a slot word (4). A table's entries must be contiguous (the insert steps by 24 from
the table's base). A one-entry table does not work with the game's insert: its first compare reads the entry above
the last one before testing the base [R, Phase 27 recon §1], so the shortest safe table has two entries.

| | Option | New bytes needed | Free where | Fits? | Saved v0.2.1 reverse times |
|---|---|---|---|---|---|
| **A** | ten tables × 3, inside Phase 27's two runs | 720 + 40 slots + 4 tag + 5 cells = 769 | 787 | **yes**, 18 spare | first three kept; **the fourth of each of the seven dropped**; four tables move |
| **B** | the seven stay at 4; the originals get 3 | 216 + 12 slots (+ a 4-byte mark) | 78 (+ the 12 unused slot bytes) | **no** in the two runs; yes with the 286-byte run | all kept, nothing moves |
| **B4** | the seven stay at 4; **the originals get 4** | 288 + 12 slots + a 4-byte mark | as B | **no** in the two runs; yes with the 286 and 244 runs together (286 alone is 2 bytes short of three tables) | all kept, nothing moves |
| **C** | packed entries (time 3 bytes, name 3, view 1, in 8) and a work table | ten × 4 × 8 = 320 | 787 | yes | all four kept, every table rewritten in a new format |

Smaller economies do not change the table: one shared slot word saves 24 bytes and the two cells could live in work
RAM (5): 78 becomes 107, still short of B's 216 [calc].

**A, a layout** (the least movement that fits) [calc]:

| Address | What | Against today |
|---|---|---|
| `0x40ee80` | entry 3 (Alpine) | in place |
| `0x40eec8` | entry 4 (Amazon Falls) | moved down 24 |
| `0x40ef10` | entry 5 (Diablo Canyon) | moved down 48 |
| `0x40ef58` | an original | new |
| `0x40efa0` | entry 6 (Metropolis) | in place |
| `0x40efe8..0x40eff3` | three new slot words (12 spare after them) | - |
| `0x40fc70` | entry 7 (Pacific Coast) | in place |
| `0x40fcb8` | entry 8 (Surfers Oval) | moved down 24 |
| `0x40fd00` | entry 9 (Surfers Road) | moved down 48 |
| `0x40fd48` | an original | new |
| `0x40fd90..0x40fdb4` | the seven slots, the tag, the two cells | in place |
| `0x40fdb8..0x40fdff` | an original | new (ends at the stack's margin, which is not entered) |

With the seven left where they are, only one more table fits the two runs (72 bytes at `0x40fdb8`): A cannot avoid the
moves.

**B4, a layout** [calc]: nothing of today's moves. Bay Bridge's and Acropolis's reverse tables at `0x40e6e4` and
`0x40e744` (192 of the 286), Big Forest's at `0x40f010` (96 of the 244); their slot words in the three unused words
`0x40fc40..0x40fc4b`; a 4-byte mark for the originals' block at `0x40fdb8`. 304 new bytes. (B: three tables of 72 at
`0x40e6e4..0x40e7bb`.)

**C** is Phase 27's "mechanism 2" (a work table in work RAM, filled before the insert and copied back after it and
after the name entry, 450 frames later) with a pack and an unpack added: about 500 to 700 bytes of new routines
[calc from that recon's 550], three new hooks in the game's race-end and name-entry code, the meaning of the entry's
+0xc word unknown [?], and a migration that rewrites every reverse time into a new format. It buys nothing B4 does not.
Not recommended.

## 3. What must change in the code

Common to A, B and B4 [R]:

- **Ranking ids.** Today a reverse table's id is its entry + 7 (10..16), for entries 3..9 only. The originals' ranking
  ids are their data indices (0 Bay Bridge, 1 Acropolis, 2 Big Forest). Either add ids 17..19 for them, or renumber
  every reverse id as the normal id + 10 (10..19), which makes the setter shorter. The id is not saved (the byte
  `0x40fc69` is rewritten by every setter call).
- **The setter**: also send ids 0..2 to their reverse table when the direction flag is set.
- **Phase 33's `rankgate3`** (which makes an original's reverse race record nothing) is removed; its site returns to
  the game's own sixteen bytes, as on main. 50 of the 146 bytes of Phase 33's block come free.
- **The image's arrays** by id grow from 17 to 20: bases, slots, titles (+36 bytes), first default times (+12),
  `revtitle`'s arguments (+60), the positions for Phase 27b's "table just raced comes first" (+3).
- **`reverse_ids`, `reverse_defaults`, `attract_groups`, `attract_positions`**: written for entries 3..9; extended to
  the three originals. `raceend` itself (Phase 27b) does not change: it reads the position of whatever id the setter
  chose, so an original's reverse race jumps to its reverse page once the positions array has its three more bytes.
- **Record insertion and name entry: no change.** Both run through the setter's table, slot and last-entry offset
  [V27]; the name entry does not know a table's length.
- **`revinit` and `revtag`** (first boot, upgrade): §4.

Only A: `SHORT_ENTRIES` 4 → 3 (the offset cell 0x30, the row cell 3, the page's end test), seven table addresses, the
migration routine. Only B: two short lengths side by side (a three-way setter, a per-table count in `revinit`).
B4: no length changes at all.

**The three-row page** [V, `out/p35/recon/three` against `four`]: on main's set with the four constants poked (the
setter's 0x48 → 0x30 and 4 → 3, `pagecmp`'s two 4 → 3) a reverse page drew three rows and left rows 4 to 6 blank; the
unpoked set drew four; normal pages drew six in both; the pages came on the same frames in both runs. Insert and name
entry on a three-entry table were not run: read as length-free, and run on four entries [V27].

**ROM room** [V byte read, calc]:

| | |
|---|---|
| Directory image today | 6 947 bytes of the test's bound 7 000: 53 spare |
| Growth, A | about 260: arrays 111, the migration (four moves, ten slots, the tag) and the three-way `revtag` about 150 |
| Growth, B4 | about 150: arrays 111, a start index for `revinit` and a second mark about 40 |
| Growth, B | about 190 |
| Title strings for the originals | 0: the game's BEGINNER, MEDIUM, EXPERT strings are in the boot ROM beside COURSE and RANKING [V]; three course names instead: about 31 |
| Free run after the image's products | main: 1 696 bytes, `0x28f1d0..0x28f870` [V]. With Phase 33: to its picture block at `0x28f690`, 1 216 [calc from its `reserved_blocks`; its set was not read] |

The arrays are indexed by id and must stay in one piece inside the image, so the image grows past 7 000 under every
option: the bound is raised (to about 7 300), as each phase before did (6 251 → 6 500 → 6 900 → 7 000). A longer
image moves what follows it (tile tables, race blobs, spawn lists), as in those phases. Nothing here needs Phase 31's
block (`0x28f870..0x28f96f`), Phase 32's bytes (inside the image) or Phase 33's block (`0x28f7d0..0x28f870`); the
free run stays above 900 bytes.

## 4. Migration

How the layout is told: the magic and the tag of §1, plus one new mark.

| Battery RAM from | A (ten × 3) | B4 (ten × 4; B the same with 3 on the originals) |
|---|---|---|
| **v0.2.1 / main** (magic, `REV4`) | Each of the seven keeps its first three entries, byte for byte (time, view, name), ranks 1..3. **The fourth entry of each is dropped.** Tables of entries 4, 5, 8, 9 are copied down 24 or 48 bytes; 3, 6, 7 stay. All ten slot words are set to their table's base (a v0.2.1 slot can point at a fourth entry). The three originals get default tables. The tag changes. | **Not one saved byte is written.** The three originals' tables, their slots and the new mark are added. `REV4` stays. |
| **v0.2** (magic, no tag) | Ten default reverse tables; normal tables untouched (as today, plus three). | The same. |
| **before Phase 22r** (old magic) | Everything initialised once, as today. | The same. |
| **Second boot** | Nothing written. | Nothing written. |
| **Backup clear** | All twenty tables back to defaults. | The same. |
| **Going back to v0.2.1 afterwards** | v0.2.1 does not know the new tag and writes its seven default tables over the reverse block: **every reverse time lost** (normal times kept). | v0.2.1 finds `REV4` and its seven tables as it left them; the originals' reverse times are ignored, and still there on the next upgrade. |

A's details:

- The new tag should differ from `REV4` in one byte (`REV3`), so that the change is a single bus write.
- The copy runs once, inside the boot's S-RAM check, on tables that overlap their old places. It cannot be run twice.
  Under MAME the file is written when MAME exits, so a MAME that dies during that boot leaves the v0.2.1 file as it
  was [R: MAME's behaviour, not tested]. The project is MAME-only.
- A player whose only mark on a course is its fourth place loses it.

**Testing it with synthetic battery RAM** (no real dump, nothing committed but code):

1. The test boots the new set on no battery RAM and takes the 65 536 bytes MAME saves.
2. In Python it rewrites the reverse block into the **v0.2.1 layout from constants frozen in the test** (the seven
   addresses, slots and tag of §1): four entries a table, each with its own time and name (so a swapped or shifted
   entry shows), ranks 1..4, slots pointing at different entries (one at a fourth), the tag `REV4`; and gives each of
   the ten normal tables a distinctive first entry.
3. It boots the new set on that file (the harness's `_attract(..., before=bytes)` already does this) with a write tap
   on the whole ranking area, and asserts: every byte of the ten normal tables, their slots, the magic: unchanged and
   unwritten; A: each new table's entries 1..3 equal the old entries 1..3 field for field, each slot its base, the
   originals at their defaults, the new tag; B4: no write at all to the seven tables, their slots and the tag, the
   three new tables at their defaults.
4. A second boot on the result: no write to any table, slot, tag or mark.
5. The v0.2 case: the same file with both reverse runs and the new tables' bytes set to 0xff.
6. Where the released set is on the machine (`out/p27play1`, git-ignored; skipped otherwise): a reverse race on it
   to a saved time, then the new set on its battery RAM, as Phase 27's `test_a_battery_ram_saved_by_main_keeps_every_time`.

## 5. The originals' pages, the rotation, the defaults

- **The page.** The game's own page code, as the seven's reverse pages: one screen (396 frames against the normal
  page's four screens), four rows (or three), the game's header, rank, name, time and view picture. The originals'
  normal pages are the arcade's own and are not touched: they go through the same two page hooks as today with the
  row cell at 6.
- **The title.** `revtitle` prints three strings by id: a name, REVERSE, RANKING. For an original the least invasive
  title is its level word in the name's place: "BEGINNER REVERSE RANKING" under the arcade's "BEGINNER COURSE RANKING"
  (Big Forest), "MEDIUM REVERSE RANKING" (Bay Bridge), "EXPERT REVERSE RANKING" (Acropolis). All fit the 62 columns;
  so do "BIG FOREST / BAY BRIDGE / ACROPOLIS REVERSE RANKING" [V, `reverse_title_columns`]. Which words: Pascal's (§6).
- **The rotation.** Each attract loop shows one member of the group of the course in the demo. Today: Bay Bridge's
  group `0, 4, 11, 7, 14, 8, 15, 9, 16`, Acropolis's `1, 5, 12, 6, 13`, Big Forest's `2, 3, 10` [V]. The least
  invasive place for an original's reverse page is straight after its own page, as each of the seven's: the groups
  become ten, six and four members (a group holds fifteen). A full turn of a group is one loop longer. Nothing of
  the normal pages changes but when they come round.
- **After a race** (Phase 27b): a reverse race on an original then shows its reverse table first, with the three
  position bytes of §3. Today, on Phase 33, such a race skips the setter with the record and leaves the rotation where it was [R].
- **The defaults.** The seven's rule is "the first entries of the course's normal default table", worked out at build
  time from the ROM. The same function gives the originals 4'00 (Bay Bridge), 5'00 (Acropolis), 4'00 (Big Forest),
  then 5 s an entry [V: `_first_default` on ids 0..2, and the fresh battery RAM's normal tables read the same], with
  the game's default names YU., RNS, TKG (and NAG). So yes. That rule was the session lead's ruling in Phase 27, not
  a choice of Pascal's, and nobody has measured whether a reverse lap is slower or faster than a normal one.

## 6. Risks and unknowns

| Risk | Applies to | What is known |
|---|---|---|
| A saved time lost or scrambled on upgrade | A (four tables copied, the fourth entries dropped by design) | B4 writes no saved byte. A's copy is testable byte for byte (§4) |
| A downgrade wipes reverse times | A | by design of v0.2.1's own check |
| The 286 and 244 bytes are used by something not yet run | B, B4 | untouched in every run so far, the backup clear included (§1); other test pages and linked play not tapped [?]. A failure would garble an original's reverse table, not a normal one |
| The same, for today's tables | all, already shipped | same evidence class since Phase 22r |
| Insert on a three-entry table | A, B | read as length-free; run on four only |
| Normal tables or pages change | all | the shared sites (two insert operands, two page hooks, the setter) already serve both lengths; gates below |
| Phase 33 not merged | all | this builds on it; on main alone the three tables would exist with no race to fill them |
| Real hardware | all | not a target (MAME only); a real board's battery content is unknown [?] |
| The image grows, addresses after it move | all | as in every phase; byte gates against main must name the moved spans |
| No human has driven any of it | all | Pascal has driven nothing of Phase 27 either |

## 7. A staged plan, with gates

0. **Before building**: Pascal's answers (§8). If B4 or B: a tap run (reads and writes) over the two unused runs
   through every test-menu page. A single touch → fall back to A.
1. **Layout and arrays** (no MAME): the new constants, ids, groups, positions, titles. Gate: the new block overlaps no
   table, slot, cell or the stack's margin; the v0.2.1 addresses frozen in a test; the directory tests' bound raised
   with the measured size; Phase 33's `rankgate3` gone and its site the game's bytes.
2. **Boot and upgrade**. Gates (synthetic battery RAM, §4): fresh; v0.2; v0.2.1 with every saved entry accounted for;
   second boot writes nothing; backup clear resets all twenty; the released set's own battery RAM where present.
3. **Races** (one-lap autopilot, as Phase 27's): a reverse race on each original records in its own reverse table
   and asks a name; lands 1st to last; slower than the last records nothing; a tie; both directions on one original
   keep their own times. Gate: **a normal race on each original and on two of the seven writes exactly main's
   battery bytes**, and the seven's reverse races write as today (or, under A, as today on three entries).
4. **Attract**: every member of each group shown, the three new titles, the row counts; a reverse race on an
   original shows its reverse table first. Gate: with no game played, the normal pages' frames against main's,
   frame for frame but for the new members.
5. **Record and release**: the formats note §21, the README, the public notes with the upgrade's effect in plain
   words; the whole suite once, by the lead; Pascal's drive.

## 8. The questions for Pascal

(Answered on 16 Nov: §10.)

1. **Three times a table, or four?** You agreed to three on all ten when the only room known was 78 bytes. This recon
   found room to keep four on the seven and give the three originals four as well.
   *Recommendation: four on all ten.* Consequence: nobody loses a saved time and nothing saved is moved; the seven's
   pages stay as released. If you keep to three: every v0.2.1 player loses the fourth best reverse time on each of the
   seven courses, the pages show three rows, and going back to v0.2.1 afterwards resets all reverse times.
   (A middle way, four on the seven and three on the originals, is possible and has no advantage.)
2. **The title of an original's reverse page.** "BEGINNER REVERSE RANKING" (and MEDIUM, EXPERT), or
   "BIG FOREST REVERSE RANKING" (and BAY BRIDGE, ACROPOLIS)?
   *Recommendation: the level words.* Consequence: it matches the arcade's own "BEGINNER COURSE RANKING" page shown
   just before it and the level word you kept in the race's HUD; the seven keep their course names.
3. **Where the three new pages come in the attract mode.**
   *Recommendation: each straight after its own course's normal page, as the seven's do.* Consequence: the arcade's
   own three pages are unchanged; each group's turn is one short page longer.
4. **The starting times of the three new tables.**
   *Recommendation: the same rule as the seven: the course's own normal starting times* (Bay Bridge and Big Forest
   4'00, 4'05, 4'10, 4'15; Acropolis 5'00 to 5'15; names YU., RNS, TKG, NAG). Consequence: a first reverse race
   that finishes under those times asks for your name, as on the seven.
5. **When it ships.** *Recommendation: in the same release as the three originals in reverse (Phase 33), not
   before.* Consequence: no release in which an original can be raced in reverse without keeping its time.

## 9. Scratch files (`out/p35/recon/`, not in the repository)

| File | What |
|---|---|
| `boot.py`, `analyse.py`, `fresh/` | the fresh boot and 400 s of attract on `out/p35play1`, the write log and the saved battery RAM decoded by region (§1) |
| `clear.py`, `clear/` | the backup clear with a poked reverse time, a poked normal time and three marker bytes (§1) |
| `rw.lua`, `rw/` | read and write taps on the unused runs through the test menu's entry and the clear (§1) |
| `rompoke.lua`, `three.py`, `three/`, `four/` | the row count poked to three against the unpoked set (§3) |
| `sizes.py`, `rom.py` | the image's sizes on main and on Phase 33's tree, the free ROM runs, the originals' default times, the level-word strings (§3, §5) |

## 10. Decisions (16 Nov 2026)

On 16 Nov the session lead put this recon's five questions to Pascal, each with its recommendation:

1. three or four times per table: **four on all ten**;
2. the title of an original's reverse page: **the level words** ("BEGINNER REVERSE RANKING");
3. the place in the attract: **straight after each original's own ranking page**, as on the seven;
4. the starting times: **the seven's rule** (Big Forest and Bay Bridge 4'00 to 4'15, Acropolis 5'00 to 5'15,
   five-second steps; a first reverse finish under those asks for a name);
5. it ships **in the same release as the originals in reverse**.

Pascal was told that four entries has one condition: a check through every test-menu page before building, and a
fall-back to three per table if anything touches those bytes. Their answer, exact words: **"yes to all"**.

**This supersedes the earlier "three per table"**: their "Yes all your recommendation" of 15 Nov was given to a list
that included "best times three per table on all ten reverse courses, decided before next release". The decision
now is four per table on all ten (option B4 of §2), on the condition of §11.

It is a yes to those five recommendations and that condition. Not a word to build beyond this plan; not a word to merge.

## 11. The gate for four per table (16 Nov 2026): passed

**Verdict: no byte of the unused runs was read or written in any run. B4 stands; no fall-back is needed.**

**The set.** A fresh build of main c94d7d9 from this worktree (`out/p35/gate/build`, by the tests' own `_seven`).
`out/p35play1` is main before Phase 32 (four program ROM members differ) and was used only to find the way through
the menus; every run counted below is on the fresh build. Headless MAME 0.289.

**The instrument** (`out/p35/gate/gate.lua`): read taps and write taps, exact to the byte, on `0x40e6e2..0x40e7ff`
(286), `0x40f00c..0x40f0ff` (244), `0x40fc40..0x40fc4b` (12), `0x40fc6d..0x40fc6f` (3) and `0x40fdb5..0x40fdff` (75),
installed before the first instruction; on frame 300 every one of those 620 bytes is set to 0xA5 through MAME's
nvram share. Each touch would be logged with its frame, PC, address and the game's mode. Control: with a reverse
table's first eight bytes and the magic's first four added to the tapped ranges, the same script logged their boot
writes and the magic's read with their PCs (`main/k_control`). After every run the saved file was read in Python:
all 620 bytes still 0xA5 in each of the 25 runs. Each run's screens were checked on snapshots.

| Run | What was driven | Touched? | First PC |
|---|---|---|---|
| `t1_bookkeeping` | BOOK KEEPING: the credit and time report, the game report, round three times, escape. The page offers no clear of its own | no | - |
| `t2_gamesystem_all` | GAME SYSTEM: each of the ten settings changed (Blue twice, Yellow once), exit, "SAVE THE CHANGE?" answered NO | no | - |
| `s1a_all_saved` | the same ten changes, answered YES ("EXECUTED TO SAVE") | no | - |
| `s1b_boot_on_all` | a boot on that battery RAM (LINK ID "LIVE"): the game stops at "NETWORK CHECKING", 200 s | no | - |
| `s4a_all_but_link_saved`, `s4b_game_on_all_but_link` | nine settings changed and saved (3 credits a start, free play, orange car, course fixed, GRANDPRIX, U.S, 4:3, SPECIAL cabinet, EASY), LINK ID left at NO LINK; then a boot, a game to the time over, the attract with its extra screens | no | - |
| `s2a_fixed_on`, `s2b_fixed_game` | **the operator's fixed course on** (COURSE SELECT: EXPERT, saved); a boot, a coin, a game on Acropolis with no course select, **left to run out of time: game over without a time**, the attract | no | - |
| `s2c_fixed_off`, `s2d_boot_after_off` | **the fixed course off** again (MAJORITY VOTE, saved); a boot and the attract | no | - |
| `t3_input` | INPUT TEST: both coins, service, start, three V.R. buttons, both shifts; escape | no | - |
| `t4_output` | OUTPUT TEST: CRT size, CRT colour, lamp test, round twice; escape | no | - |
| `t5_drivebd` | DRIVE BD TEST: the six send codes with START, both shifts; the test switch to escape | no | - |
| `t6_sound` | SOUND TEST: the music, voice and effect pages, sounds started, the list moved; escape | no | - |
| `t7_tgp` | TGP TEST: run to its result (four ICs GOOD), escape | no | - |
| `t8_memory` | MEMORY TEST: run to its end (300 s; the second board's twelve ICs GOOD) | no | - |
| `t9_clear_no` | BACKUP RAM CLEAR answered NO, entered again | no | - |
| `t9_clear_yes` | **BACKUP RAM CLEAR answered YES**, on a battery RAM with saved times: a poked normal time and a saved reverse time and name came back to their defaults | no | - |
| `t10_exit` | EXIT: "EXIT TEST MODE", the game's boot, the attract | no | - |
| `r1_normal_metropolis_record` | a coin, the course select, **a normal race to a new best time, the name entry** ("Your Ranking is 1st"), the attract | no | - |
| `r2_reverse_amazon_record` | the direction screen answered REVERSE, **a reverse race to a new best time, the name entry**, the attract | no | - |
| `r3_reverse_metropolis_no_record` | a reverse race that finishes slower than its table's fourth time: no name entry | no | - |
| `r4_normal_bay_bridge_record` | a normal race on an original (Bay Bridge) to a new best time, the name entry | no | - |
| `c1_cold_boot_no_magic` | **a cold boot with the magic and the tag invalidated** (zeroed) and a normal time poked: the first-boot initialiser ran (magic and `REV4` back, the time at its default) | no | - |
| `a1_attract_1250s` | **the attract with no input for 1 250 s**: many whole loops, every member of each ranking group (the standing test's length) | no | - |

The four races are one-lap races with the clock held (the tests' `race_end.lua` and autopilot); the name entry
takes no letter and ends on its timer.

**Not exercised, and why:**

- **Linked play** (two or more cabinets, the linked Grand Prix): with a link identity set the game waits at "NETWORK
  CHECKING" for a partner; a second linked MAME was not set up. The settings that select it were changed and saved
  (`s1a`), and the boot's network check ran (`s1b`).
- **A Grand Prix race driven to its finish**: the mode was set and a game started in it (`s4b`), which ended on the
  time over.
- **A full-length race** (five laps) and **a pit stop** by the player.
- **A name entered letter by letter.**
- **A game on a setting other than those above taken one at a time** (each was changed together with the others).
- **The I/O board's own DIP switches and the drive board's reactions** (MAME shows them all off; the drive board
  test ran its six commands).
- **Real hardware.**

**Fall-back, had anything been touched** (not needed; recorded for the builder): B4 needs 288 bytes of tables. If
only the 244-byte run were clean: two four-entry tables there (192) and no third, so B (three three-entry tables,
216, in that run, `0x40f010..0x40f0e7`). If only the 286-byte run were clean: B there (`0x40e6e4..0x40e7bb`).
If neither: A (§2), with its dropped fourth entries and its moved tables.

Scratch for this section: `out/p35/gate/` (`gate.lua`, `run.py`, `pages.py`, `menujobs.py`, `sys2.py`, `fix.py`,
`races.py`, `boots.py`, `build.py`; the runs under `main/`, the exploration on `out/p35play1` under `runs/`). Not in
the repository.
