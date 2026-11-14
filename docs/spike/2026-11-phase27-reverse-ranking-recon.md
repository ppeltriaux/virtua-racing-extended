# Phase 27 recon: a best-time table for reverse races (top 4 per course)

14 Nov 2026. Read and measure only: no product code changed. Branch `phase27-reverse-ranking`.

Marks: **[V]** verified by a MAME run or a byte read on the built set `out/p26play6`; **[R]** read in the boot ROM's
listing (`out/p26/stage2/t13/boot.lst`, bytes from `build/mame/unidasm` on the built set); **[?]** not established.

Scratch (git-ignored): `out/p27/recon/` — `taps.lua` (per-byte read/write taps, a mode and ranking-page log, ROM/RAM
pokes, snapshots), `run.py`, `touch2.py`, `sizes.py`, `vdis.py`; runs under `out/p27/recon/runs/`:

| run | what | emulated |
|---|---|---|
| A | fresh battery RAM, no input: boot (S-RAM initialiser), attract, 7 ranking pages | 400 s |
| A/second | a second boot on A's saved battery RAM (the magic present) | 70 s |
| N | coin, course select, direction screen answered NORMAL, Metropolis (entry 6), one lap (`race_end.lua`), name entry, attract | 430 s |
| R | the same answered REVERSE, the race's end, attract, a coin and a second game's select and race load | 430 s |
| X | N with four boot-ROM immediates poked (every table 4 entries long, one screen of 4 rows) | 260 s |
| E | R with the same four pokes, `rankgate` undone, entry 6's table and slot pointed at the free battery RAM | 330 s |

Taps in A, N, R, E: `0x40e000..0x40ffff` and `0x5030c0..0x53ffff`, reads and writes, per byte; the touch maps are the
last summary each run wrote (video frame 21 600 in A, 23 400 in N and R: in R after the second game's race load at 22 790).

## 0. Summary

- The game's insert, name entry and page run on a 4-entry table when **four immediates** change: two `#228` (the last
  entry's offset, in the qualify test and in the bubble), the page's end test `#18` and its row count `#6`. Nothing else
  in those routines knows the table's length [R]; run X and run E did exactly that with pokes and worked end to end [V].
- A reverse race with a record takes the normal race's mode sequence, name entry included; the direction flag is still 1
  through the name entry and is cleared by the attract load after it [V, run E].
- Battery RAM: the two free runs are confirmed (384 at `0x40ee80`, 403 at `0x40fc6d` up to `0x40fdff`) [V]. Seven tables
  of 96 bytes, seven slots, a tag and two cells take 709 of the 787 bytes.
- The S-RAM magic need not change: a separate tag for the reverse block keeps every saved time.
- Mechanism 1 (stock routines on short tables) costs about 300 bytes of routines and 84 of arrays; mechanism 2 (work
  table and copy-back) needs everything mechanism 1 needs for the page and the initialiser, plus about 250 bytes.

## 1. The insert at a race's end

The race-end routine (`0xfe4b21..`) calls `0xfc40ce` once (`0xfe4b49`, the only caller [R]); in runs N, X, E the writes
land on one video frame, the frame mode 0x1b is entered [V].

| address | bytes | what it does |
|---|---|---|
| `0xfc40ce` | 16 bytes, today `jsr rankgate` + 10 nops | originally `movz.bw #0, 5018FC; test1 #1, 501174`: record flag cleared, "race finished" tested |
| `0xfc40de` | `749e00` | `be FC417C`: not finished (or, today, reverse) → return, no record |
| `0xfc40e1` | | `movz.bw 501934, R0; bsr FC4208`: the setter (today `jmp` into the project's setter: table base → `0x5018f0`, slot address → `0x501918`, by the ranking id `[0x40fc68]`) |
| `0xfc40eb` | `2d20f2…` (7) | `mov.w 501320, R0`: the player |
| `0xfc40f2` | (7) | `mov.w 5018F0, R1` |
| **`0xfc40f9`** | **`8421f428020000`** | **`add.w #228, R1`: the last entry (23 × 24)** |
| `0xfc4100..0xfc410b` | `bc020104 6c71` | `R2 = [0x501168]` (the time, 1/32 s); `cmp.w R2, 4[R1]; blt FC417C`: the last entry's time is below the new time → no record. A tie qualifies |
| `0xfc410d..0xfc4168` | | the new entry overwrites the last one's fields +4 (time), +8 (the view used most: 0..3, from the counters `0x501d04..10`), +0xc (the player's halfword +0x171), +0x10 (time), +0x14 (`0x202020`: three spaces). **+0 (the rank number) is never written**: ranks 1..24 stay where the initialiser put them |
| `0xfc4171` | `480c00` | `bsr FC417D`: the bubble |
| `0xfc4174` | `9780e0f288d753ff` | `set1 #0, 5018FC`: the record flag |
| `0xfc417d` | (7) | bubble: `mov.w 5018F0, R0` |
| **`0xfc4184`** | **`8420f428020000`** | **`add.w #228, R0`**; `R1 = R0` (new entry), `R4 = [0x5018f0]` (the base) |
| `0xfc4195` | `ac20f418000000` | `sub.w #18, R0`: the entry above (24 is the entry size here, not the count) |
| `0xfc419c` | `bc8001040004 6c5b` | `cmp.w 4[R1], 4[R0]; blt FC41FD`: the entry above is faster → stop. Else the two entries' fields +4..+0x14 are swapped (a tie moves the new entry up) |
| `0xfc41ea..0xfc41fb` | | `sub.w #18` on both; `cmp.w R4, R0; bge FC419C`: until above the base |
| `0xfc41fd` | | `mov.w 501918, R10; mov.w R1, [R10]`: the new entry's address into the slot |

- The count 24 is wired in **two** instructions of the insert: `0xfc40f9` and `0xfc4184`, both `add.w #228` (7 bytes)
  [R]. The loop itself ends on the table base, not on a count.
- A per-call length without a hook: `add.w X[PC], R1` (or absolute) is also 7 bytes (`84 21 f2`/`f3` + 32 bits;
  assembled with `v60asm`: 7) [V], so both sites can read the last entry's offset from a cell the setter writes
  (0x228 or 0x48). Every call of the insert is preceded by the setter in the same routine (`0xfc40e8`) [R].
- Run X (both immediates poked to `#48`): the Metropolis race wrote `0x40f344..0x40f39f` only (the first four entries;
  the tap covered the whole table) and the name went to entry 0's +0x14 [V]. Run E the same on a 4-entry table at
  `0x40ee80`: 72 word writes inside `0x40ee80..0x40eedf`, none beyond, the bytes after the fourth entry still 0xff,
  Metropolis's own table (`0x40f340`) not written [V].
- Other places with 24: the initialiser's `mov.w #18, R8` at `0xfc3b8a` (24 entries a table, `dbr` at `0xfc3be8`) and
  the project's `slot_init` (`TABLE_BYTES // 24` fills of +0xc, seven tables) [R]. Neither runs on a table it is not
  given.

## 2. The name entry

- Mode 0x1e. Installed at `0xfe6575..0xfe65b2` when the post-results timer step runs: `test.h 501428` non-zero [?: what
  the halfword is; it is non-zero in single play, runs N and E], the player's byte +0x1b0 zero, and `0x5018fc` non-zero;
  then `mov.w #FC4226, A[R0]` on the entity `[0x501334]`. The race end's own test of `0x5018fc` is at `0xfe4b4f`.
- `0xfc4226`: `movz.bw 501934, R0; bsr FC4208` — the setter **again** (today by the ranking id `[0x40fc68]`), then the
  screen (`0xfc4981`), the cursor at `0x501900`, the name buffer `0x501904` (3 characters + NUL), the count `0x501910`,
  the timer `0x50113c`.
- What it reads from the table: only through the slot. `0xfc49f0` and `0xfc4a82`: `[[0x501918]]` → the entry, +0 the
  rank (two digits and the st/nd/rd/th picture, 11..20 forced to "th"); `0xfc4ab2`: +0x10 the time. `0xfc4661..0xfc4675`:
  with bit 0 of `0x5018fc` set, the name buffer's word → +0x14 of `[[0x501918]]` [R].
- It never reads `0x5018f0` and has no count or offset of the table: **no dependence on the table's length** [R]. Run E:
  "Your Ranking is 1st", total time and best lap shown, on the 4-entry table [V, snapshot `runs/E/snap/vr/0012.png`].
- It lasted 1537 video frames in N and E (the autoplay enters no full name; the timer runs out) [V].

## 3. The ranking page

- **There is no ranking page after a race.** Modes 0x1b–0x1d (450 video frames) are the RESULT / GAME OVER screen
  [V, `runs/X/snap/vr/0009.png`]; the page entity is not active in them (`act=0` in `page.txt`). The stage 3 findings'
  "race-end ranking page 0x1b–0x1d" is that screen. The page only exists in the attract: mode 0x03 state 2 calls
  `0xfc3c33` (`0xfe2670`, the only caller [R]), state 3 lasts while the page runs.
- The first attract cycle after a game starts with the page (mode 0x02, then 0x03 states 2, 3) [V]; later cycles
  alternate (with the page: states 2, 3; without: 0, 1). Which table it shows is the project's `attract` routine's
  choice: the next member of the attract group of the data index `[0x501934]`. After the Metropolis race in N and R it
  showed Acropolis (`0x40e240`), not Metropolis [V].
- `0xfc3c33` (today `jsr attract`): the setter; then on the entity `[0x501314]`: +0x36 (the first entry shown) := 0,
  +0x37 / +0x38 := 0x40, +0x39 := 0, handler := `0xfc3c75`.
- `0xfc3c75` every logic frame: a wipe counter (+0x37 += 2 up to 0x34, +0x38 += 4 up to 0x22, +0x39 toggles); on each
  toggle to "show":

  | address | bytes | |
  |---|---|---|
  | **`0xfc3ca1`** | **`b880f4181936`** (6) | **`cmp.b #18, 36[R25]`**; `bnl FC3CEC` (`6345`): past 24 entries → state := 4, entity off |
  | `0xfc3ca9` | `485600` | `bsr FC3CFF`: draw a screen |
  | `0xfc3cac` | `8080e61936` (5) | `add.b #6, 36[R25]`: six entries a screen |
  | `0xfc3cff` | today `jsr title` | the title; then four fixed header maps; `0xfc3d62`: `[[0x501918]]` + 0 → R20 (not used by the row routine `0xfc3dc2..0xfc3e9f` [R]) |
  | `0xfc3d70..0xfc3d82` | | `R10 = [0x5018f0] + [+0x36] × 0x18` |
  | `0xfc3d85`, `0xfc3d8c` | (7), `2d01f298db53ff` (7) | first row's tile address `0x702580` → `0x501924` |
  | **`0xfc3d93`** | **`2d23e6`** (3) | **`mov.w #6, R3`: six rows**, `0x200` tile bytes (4 tile rows) apart; loop target `0xfc3d96` |

- Measured [V, run A]: a screen is 396 video frames (264 shown, 132 wiping out); four screens, 1584 frames; six rows a
  screen, 24 entries.
- A row prints the rank (+0), its suffix, the name (+0x14), the time (+0x10) and one of four view pictures (+8) [R].
- **A 4-entry table on one screen** needs two things: the row count 4 (`0xfc3d93`) and the end after the first screen
  (`0xfc3ca1` comparing with any value 1..6). Runs X and E poked `0xfc3d95` to `e4` and `0xfc3ca4` to `06`: one screen
  of four rows, rows 5 and 6 empty (nothing left on them: every page starts on a cleared layer), the page 396 frames,
  then state 4 and the attract goes on; the attract cycle is 1188 frames shorter [V, `runs/X/snap/vr/0004.png`,
  `0012.png`, `runs/E/snap/vr/0016.png`: the reverse race's time first, the three poked defaults below it].
- Per table, both sites need a hook (neither has room for a memory operand): `0xfc3ca1` is exactly 6 bytes = `jsr`
  (flags survive `rsr`, as `rankgate` relies on); `0xfc3d8c..0xfc3d95` is 10 bytes = `jsr` + 4 nops. No branch in the
  listing targets the inside of either span [R].
- The title: `title` (the project's) indexes ten title routines by the shown id `[0x40fc69]` and falls back to the data
  index's title for an id of 10 or more [R]: a reverse table shown under a new id needs a title entry.

## 4. Mechanism 2: a work table and a copy-back

- **A free work-RAM region** [V]: `0x5030c4..0x53efff` is written once, by the boot's clear (`0xfe1469`, video frames
  0–4), and then neither read nor written in A, N, R and E (boot, attract with 7 pages, coin, select, direction screen,
  both races, name entry, a second game's load); `0x53f000..0x53ffff` is never touched at all. (`0x5030c0..0x5030c3` is
  in use: read every frame.) The only reads logged there are the scratch script's own dumps (one per 1800 frames, all
  bytes alike). A 0x240-byte table and a slot word fit anywhere, e.g. `0x504000` and `0x504240`. Not tapped: the test
  mode, linked play [?].
- Hooks it needs [R]:
  1. **fill**, after the setter and before the qualify test: `0xfc40eb` (`mov.w 501320, R0`, 7 bytes) → `jsr`: in a
     reverse race copy the course's 4 saved entries to the work table, add 20 fillers, point `0x5018f0` / `0x501918` at
     the work table and its slot.
  2. **copy-back**, after the bubble: `0xfc4171..0xfc417b` (`bsr FC417D; set1 #0, 5018FC`, 11 bytes) → `jsr`: the top 4
     back to battery RAM, and the slot's content turned into the battery entry's address (or the flag cleared when the
     entry landed below the fourth).
  3. **the name entry** calls the setter again (`0xfc422d`) and writes through the slot (`0xfc4675`), 450 frames and one
     screen later: either the setter returns the battery table and its slot (then nothing else is needed: rank and time
     are read from the battery entry, the name written into it), or a second copy-back is hooked at `0xfc4661`.
- **A time that ranks 5th..24th**: the game asks for a name whenever the record flag is set, and the flag is set whenever
  the time is at or below the last entry's time of the table the insert ran on; the name entry would show that rank
  ("Your Ranking is 17th") [R]. With fillers slower than every real time, every finisher is asked for a name that the
  copy-back drops. Two ways out: fillers carrying the fourth entry's time (then a time qualifies only at or below the
  fourth's, and a tie moves above the fillers and the fourth, so the new entry always lands in the top 4) [R, not run];
  or hook 2 clearing the flag.
- **The page**: showing the work table shows 20 filler rows on screens 1–4 (the row routine prints rank, name and time
  of whatever is there). Keeping them off the screen takes the same two page hooks as mechanism 1 (§3), and the page
  then reads the 4-entry battery table directly: the work table is of no use to the page.
- So mechanism 2 = mechanism 1's setter, page hooks, tables and initialiser, **minus** the two in-place operand changes
  at `0xfc40f9` / `0xfc4184`, **plus** the fill, the copy-back and the slot fix-up.

## 5. Battery RAM

Taps over A + N + R (boot with the initialiser, 7 attract pages in A and 4-5 more after each race, coin-up, course
select, direction screen, a normal race to its end with name entry, a reverse race to its end, a second game). Bytes
neither read nor written, runs of 4 or more [V]:

| run | bytes | note |
|---|---|---|
| +0xc of every entry of the three originals' tables | 4 each | the game writes +0xc only at an insert |
| `0x40e6c8..0x40e6cb` | 4 | the unused fourth slot word |
| `0x40e6e2..0x40e7ff` | 286 | after the magic (`0x40e6d0..0x40e6e1`); 0xff; no direct reference in the listing [R]; not in the Phase 26 table |
| **`0x40ee80..0x40efff`** | **384** | 0xff |
| `0x40f00c..0x40f0ff` | 244 | after the record `0x40f000..0x40f00b`; 0xff; no direct reference in the listing [R]; not in the Phase 26 table |
| `0x40fc40..0x40fc4b` | 12 | the first three of `NEW_SLOTS` (the originals keep their own slots) |
| **`0x40fc6d..0x40fecf`** | **611** | 0xff; the stack's deepest byte in these runs is `0x40fed0` (304 bytes used) |

- The two runs of the Phase 26 recon stand: 384 at `0x40ee80`, and 403 at `0x40fc6d..0x40fdff` when 208 bytes
  (`0x40fe00..0x40fecf`) are left as the stack's margin; 787 bytes [V].
- A second boot on the saved battery RAM (A/second): the initialiser does not run, no table is written, the same runs
  are untouched [V].
- The bookkeeping `0x40e800..0x40e9ff` is written on almost every frame of a game; `0x40e900` in one block at the
  attract load after a game (`0xfe0e5b`) [V].
- Not tapped: the test mode (its backup clear calls the initialiser at `0xfc76eb` [R]), operator settings, linked play;
  whether the 286 and 244 bytes are used there [?]. A real board's factory content [?] (MAME's fresh battery RAM reads
  0xff where nothing wrote).

**Fit**: 7 × 96 = 672. Proposed:

| address | bytes | |
|---|---|---|
| `0x40ee80`, `0x40eee0`, `0x40ef40`, `0x40efa0` | 4 × 96 = 384 | reverse tables of entries 3, 4, 5, 6 (the run exactly) |
| `0x40fc70`, `0x40fcd0`, `0x40fd30` | 3 × 96 = 288 | reverse tables of entries 7, 8, 9 |
| `0x40fd90..0x40fdab` | 28 | seven slot words (one shared word would do: a slot is only read back by the name entry of the same game and, unused, by the page) |
| `0x40fdac` | 4 | the reverse block's tag |
| `0x40fdb0`, `0x40fdb4` | 4 + 1 | the last entry's offset (0x228 / 0x48) for the two insert sites; the page's row count. (Work RAM would do as well: the setter writes both before every use.) |

709 bytes; `0x40fc6d..0x40fc6f` and `0x40fdb5..0x40fdff` (78 bytes) stay free, the stack margin unchanged. Run E's table
was at `0x40ee80` and its slot at `0x40fc70`: the game inserted, entered the name and paged there [V].

**The initialiser** (`0xfc3b49`, run when the magic at `0x40e6d0` is missing, and by the test mode's backup clear):

- Each new table needs four entries: +0 the rank 1..4 (**required**: the insert never writes it, the page and the name
  entry print it), +4 and +0x10 a default time, +8 = 0, +0xc = −1, +0x14 a name; and each slot the table's base (the
  page dereferences the slot on every screen).
- The stock loop cannot make them: its count 24 (`0xfc3b8a`) is one immediate for all tables. A loop of its own, called
  from `slot_init` (so a backup clear resets the reverse tables with the others).
- Default times: the stock rule (the level-0 record's 5 laps of sectors, rounded up to the minute, +5 s an entry) needs
  the reverse variant's race blob; seven first times as build-time constants are 28 bytes. Which times: a design choice.
- **The magic need not change.** `0xfe69f0..0xfe6a34` compares 18 bytes at `0x40e6d0` with the project's "S-RAM CHECK
  OK 10" and runs the initialiser on a mismatch [R]. A battery RAM saved by the current build has the magic and 0xff in
  the new block. A second tag (4 bytes in the free battery RAM), tested on every boot beside the stock check (e.g.
  `0xfe69f0`, `mov.w FE6A47[PC], R0`, 7 bytes → `jsr` + nop), initialises the reverse block alone when it is missing:
  no saved time is lost. Changing the magic instead resets all ten tables once more.

## 6. Program room

- The directory image: `end − loader` = 6 251 bytes against the test bound of 6 500 (`tests/test_directory.py:162`,
  `tests/test_hudname.py:150`): 249 under the bound, a test constant [V: `directory_layout()`: loader `0x279878`, end
  `0x27b0e3`].
- Free 0xff runs in the program ROM's `CODE_FREE` on `out/p26play6` [V, byte read]: 2 592 at `0x28ef50` (below the
  start-gantry block), six spawn-slot tails of 720 / 744, 98 at `0x28fd0e`. The image's tables move up as the image
  grows.
- Today's ranking block is 1 789 bytes: setter 45, `slot_init` 396 (seven unrolled fills), `attract` 84, `title` 30,
  seven title routines of 100; `rankgate` is 40.
- Rough sizes (sketches assembled with `v60asm` for the count only, `out/p27/recon/sizes.py`):

  | piece | bytes | mechanism |
  |---|---|---|
  | setter: the id + 7 in a reverse race, table, slot, the last-entry offset and the row count | 103 (replaces 45) | 1, 2 |
  | the two insert operands in place | 0 | 1 |
  | `pagecmp` (`0xfc3ca1`), `pagerows` (`0xfc3d8c`) | 23 + 15 | 1, 2 |
  | the reverse tables' initialiser and the boot tag check | 131 + 28 | 1, 2 |
  | arrays: 7 bases, 7 slots, 7 first times | 84 | 1, 2 |
  | `rankgate` removed (the flag is only ever set on entries 3..9, which all get a table) | −40 | 1, 2 |
  | fill; copy-back and slot fix-up | 148 + 98 | 2 |
  | attract groups: the reverse ids in the three 16-byte groups (15 ids a group; the largest has 5 today) | 0 | if shown in the attract |
  | titles for the reverse ids | 28 + from about 40 (one shared routine: the course's title and one more print) to 700 (seven routines as today's) | if shown in the attract |

  **Mechanism 1: about 300 bytes of routines (net about +215) + 84 of arrays; mechanism 2: about 550 + 84.** Either
  passes the 6 500 test bound (249 left) and fits the 2 592 free bytes; the titles decide by how much.

## 7. A reverse race's end today, and with a record

Video frames from run R (today) and run E (`rankgate` undone, short table) [V]; mode `0x501139`, flag `0x502294`:

| | today (R) | with a record (E) | normal race (N) |
|---|---|---|---|
| finish 0x19, 0x1a | 5888, 5890 | 5888, 5890 | 5656, 5658 |
| results 0x15, 0x16 | 6276, 6278 | 6276, 6278 | 6044, 6046 |
| 0x1b (the insert runs on this frame) | 6281, record flag stays 0 | 6281, flag 1 from 6282 | 6049, 1 from 6050 |
| RESULT / GAME OVER 0x1c, 0x1d | 6282..6734 | 6282..6734 | 6050..6502 |
| name entry 0x1e | — | 6735..8271 | 6503..8039 |
| attract load 0x02 | 6735 | 8272 | 8040 |
| direction flag | 1 until 6736, 0 from 6737 | 1 until 8274, 0 from 8275 | 0 |
| first attract page | 6740, Acropolis | 8278 | 8046, Acropolis |

- What changes with a record: mode 0x1e is inserted (1537 frames when no name is completed), exactly as after a normal
  race; nothing else moves.
- The direction flag is 1 at both setter calls (the race end's at 6281, the name entry's at 6735) and is cleared only
  by the attract load (`bankdemo`): a setter that picks the reverse table by the flag serves both calls; the attract
  page's setter (`attract`) runs after the clear and must not use the flag [V].
- In run E the page after the game showed the reverse race's own table because the scratch run poked the attract group
  counter; unpoked it is the group's next member (§3).

## 8. Dependencies for the normal direction

- `0xfc40f9` / `0xfc4184` are the normal races' insert too: with a memory operand, the cell must hold 0x228 for every
  24-entry table. The setter runs before the insert in the same routine on every path (`0xfc40e8`) [R].
- The page hooks serve every attract page (ten tables today): the row count and the end must be set by `attract` /
  `common` before each page; nothing else calls the setter while a page runs (the page is mode 0x03 state 3 only) [V].
- The setter has three callers: the race end (`0xfc40e8`), the name entry (`0xfc422d`), the attract page (`0xfc3c33`,
  the project's own routine). `0x5018f0` and `0x501918` are referenced nowhere outside `0xfc3b49..0xfc4cd4` in the boot
  ROM; `0x5018fc` only at `0xfe4b4f` and `0xfe658c` [R].
- The attract: groups hold 15 ids; a 4-entry page is 396 frames instead of 1584, so cycles with a reverse page are
  shorter; the title falls back to the data index's for an id the `title` table does not know.
- The originals' tables and slots (`0x40e000..0x40e6cf`) and the seven tables of Phase 22r are not touched by either
  mechanism; in run E nothing but the short table, its slot and the game's bookkeeping was written after boot [V].
- The S-RAM magic and `slot_init`: unchanged magic keeps saved times (§5); the backup clear's path (`0xfc76eb`) reaches
  `slot_init` [R].
- Linked play: `dirlock` never opens the direction screen there and the linked loads clear the flag (stage 3), so the
  flag is 0 at every linked race's end [R]; the name entry's own gate on `0x501428` [?].
- The operator's fixed course never reaches the direction screen (stage 3) [R].
- Tests that pin today's behaviour: `tests/test_dirscreen_build.py::test_a_reverse_race_records_nothing` (no write, no
  mode 0x1e, the `NO_RECORD` mode tuple), the `rankgate` site in `tests/test_dirscreen.py`, the directory image's bound,
  the boot ROM's allowed spans in `tests/test_directory.py`.
- `race_end.lua` races one lap with the clock held: every measured insert here is such a race's (59–63 s against
  defaults of 4–5 minutes), always first. A time landing 2nd..4th, a time that does not qualify, and a tie were read
  from the code, not run [R].

## 9. Not established

- `0x501428` (the name entry's second condition) [?].
- The test mode, the operator's backup clear, linked play: not tapped; the 286 bytes at `0x40e6e2` and 244 at `0x40f00c`
  are free only as far as these runs and the listing's direct references go.
- Mechanism 2 was not run (no fill or copy-back was emulated); its filler rule (§4) is read from the compare and the
  bubble.
- The rank shown by the name entry for ranks 2..4 on a short table, and a full five-lap reverse race's end.
- Default times and the look of a reverse table's page and title: design, not measured here.
