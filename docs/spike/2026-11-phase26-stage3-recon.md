# Reverse courses, stage 3: recon for the COURSE DIRECTION screen (13 Nov 2026)

What the screen of design §2 item 3 / §6.6 needs, measured on the set `out/p26play3` (what branch `phase26-stage3` at 026df67
builds) in MAME 0.289, headless, and read from the original boot ROM's listing and the project's code. Nothing was built.
Scripts, logs, dumps and snapshots are git-ignored under `out/p26/stage3/recon/` (`runs/<label>/`; the runner is `run.py`,
which calls `vrtools.mame.run_mame` with `autoplay.lua` and the env given). Tags: **[M]** measured (run named), **[R]** read
(listing address or file:line), **[I]** inferred. Recon = `docs/spike/2026-11-phase26-reverse-recon.md`.

Timing units: a video frame is 1/57.52 s; the game logic, the timer `[0x50113C]` and the frame counter `[0x501144]` step once
every two video frames (a "logic frame") [M `base`: 0x501144 +26 in 52 frames].

## 1. The flow hook

### 1.1 Today, from the gas edge to mode 0x11

Run `base` (coin 600, START 720, paddle 150 = entry 6 Metropolis, gas floored at 1400; `sel_log.lua`) [M]:

| frame | mode / state | timer | entity handler `[0x501318]+0xA` | what |
|---|---|---|---|---|
| 618 | 0x10 / 1 | 638 (0x27E) | 0xfc26c5 | course select running; countdown = timer >> 5 |
| 1402 | 0x10 / 1 | 246 | 0xfc277c | gas edge `[0x501078]` = 0xffff for this one logic frame; `0xfc26c5` installed the lock handler |
| 1404 | 0x10 / 1 | 32 | 0xfc27be | `0xfc277c` set timer := 0x20 and handler := 0xfc27be |
| 1470 | 0x10 / 6 | 64 | 0xfc27be | state 1 saw timer < 0: `0xfe3f01` timer := 0x40, state 6 |
| 1600 | 0x11 / 0 | -1 | (bit 31 cleared) | state 6 ran out: `0xfe3f9d` clears the entity's bit 31, `0xfe3fa8` mode 0x11 |
| 1604, 1864 | 0x12, 0x14 | | | grid, race |

- **Who does what [R]** (listing): mode 0x10 state 1 (`0xfe3d99`) calls `0xfc2de2` every logic frame (`0xfc3407`: timer >> 5
  printed by `0xff8f88` at tile `0x7013b8` when `[0x40dc9b]` != 0, else `0x701438`; `0xfc3444`: voice cues at timer 0x27E and
  0x180 (0x1A0 / 0xE0 on other settings)), then decrements the timer and leaves for `0xfe3f01` below 0 when `[0x40dc8c]` = 0
  (single play; linked play goes to state 2). The course select is the entity's handler: `0xfc26c5` (START bit → `[0x501936]`
  via `0xfc31e4`, wheel → `band` → `[0x501940]`, `id_store`, cursor `0xfc2880`; lock on `test.w 501078` or `timer − 0x20 ≤ 0`,
  or at once when `[0x501a35]` = 0, which only a linked slave has (`0xfe11b5`)). Lock handler `0xfc277c`: `mov.w #20, 50113C`;
  `mov.w #FC27BE, A[R25]` (0xfc2788, 9 bytes); then the cursor object's fields. `0xfc27be` runs `0xfc27d6` (now `jmp 27A19E`,
  the project's `start`) every logic frame when `[0x501a35]` != 0 or state > 5.
- **Palettes of the lock look [M]** (`base`, `select_dump.lua` dumps 1350 / 1500): only palettes 0x66-0x68 (slot 0) and
  0x6c-0x6e (slot 2) change: `start` copies each not-chosen slot's grey set (48 words) to its `SLOT_PAL`; the chosen slot keeps
  its colours [R `select.py:230-282`]. No tile changes between 1350 and 1595 except the countdown's six cells.
- **Lock to exit is the game's [M]**: 198 video frames (0x21 logic frames in state 1, 0x41 in state 6), the same in every run.

### 1.2 Two ways to put the screen between the lock and the race load

| | (a) a handler chained after the course lock | (b) mode 0x10's states run a second time |
|---|---|---|
| How | patch `0xfc2788` (`mov.w #FC27BE, A[R25]`) to `jsr dirlock`: for an entry with a reverse record and `[0x40dc8c]` = 0, handler := the direction screen's, timer := 0x140; else handler := 0xfc27be as today. State 1 keeps running: it prints the new countdown and leaves at timer < 0 exactly as after any lock | at state 6's exit put the mode back to 0x10, state 0, behind a phase cell; state 0 (`0xfe3cce`) re-inits the linked-play cells, sets bit 31 and handler 0xfc267e, draws through `0xfc2b7e`, sets timer 0x280 |
| Game sites patched | 1 (0xfc2788) | 4 (state 6's exit, `0xfc267e`'s screen choice, `0xfc2b7e`'s draw choice, state 0's timer) |
| Seen by the player | the screen 2 logic frames after the course press | 3.4 s of course-select lock look first (unless state 6 is shortened too), the 0x27E voice cue again, a full 20-count countdown unless patched |
| Originals, linked, operator-fixed | untouched: `0xfc277c` is reached only from the course select's handler (two refs, 0xfc2753 / 0xfc2775 [R]); the operator's screen locks through `0xfc2a1d` | needs the phase test at every site |
| Risk | small: one patched instruction, everything else is project code | state 0 also resets linked bookkeeping (0x5019c0..c6) and redraws without clearing layer 0 |

**Prototypes [M].** `proto.lua` (option a): when the handler becomes 0xfc27be it pokes the SHIFT MODE SELECTOR's handler
0xfc29b3 (a stand-in: wheel, 0x1c threshold, two-position cursor, gas-edge and timer locks) and the timer 0x140, releases the
gas, steers, presses again; at the stand-in's lock it writes `[0x501936]` (wheel right of 0x1c) to the flag.

| run | after the course lock | second lock | mode 0x11 | after the load |
|---|---|---|---|---|
| `proto_p1` | release +20, paddle 200, press +150 | edge seen 1556, handler 0xfc2a59 at 1558, timer 32 | 1754 (+196) | flag 1, the car at the line facing the other way (yaw ≈ 0x7ff9): reverse |
| `proto_p2` | release, paddle 150 (wheel value 28), no press | timer lock at 1980: 575 frames after the restart (10.0 s) | 2178 | flag 0, normal |
| `proto_p3` | gas held from the course press, paddle 200 | no edge; timer lock at 1980 | 2178 | flag 1, reverse |

The countdown cell was reprinted from the restarted timer every 32 logic frames; the state machine took the second lock and
its exit with the game's own timing. `proto_b.lua` (option b): at the first mode-0x11 request it wrote mode 0x10 / state 0;
the course select came back (state 1 at 1604, timer 0x27E, pictures in colour again), a second press locked at 1802, mode 0x11
at 2000, the race loaded. **Recon §7 item 4 is settled: mode 0x10 can be run a second time [M].**

**Recommended: (a).** One game site, the screen right after the press, today's timing after the lock. Optional (owner, §12
D7): keep the course select's grey/colour confirmation for about 0.5 s before switching, by doing the switch from `start`
when a "pending" cell is set and the timer has fallen to about 0x10 (≈ 20 bytes).

## 2. Drawing the screen

### 2.1 What is on the tile layers at the lock [M] (`base`, dumps 1350 and 1405; `layers.py`, `render.py`)

- **Layer 0** (0x700000, every cell bit 15): the three pictures (rows 1-21, cols 4-19 / 23-38 / 42-57, tile words 0x8000 |
  slot characters), BEGINNER / MEDIUM / EXPERT (rows 23-25), AUTOMATIC ×3 (rows 27-28), the wheel panel (rows 30-42, cols 7-26),
  the red arrow (rows 32-36, cols 28-33), the countdown (rows 39-41, cols 28-31), STEP TO START! (rows 30-42, cols 35-54), the
  bottom bar TO PLAY 7SPEED MANUAL MODE / HOLDING START BUTTON (rows 43-46).
- **Layer 2** (0x704000): the checker (bit 15 clear, characters 0x3780-0x378f) and, at the three slots, Phase 7's overlays (bit
  15: outline, start mark and name in characters 0x3e80-0x3fff), hidden under the layer-0 pictures.
- Layers 1 and 3: stale content, not seen on the screen (layer 3 is under layer 2's opaque pass) [I].

### 2.2 Clearing and redrawing [R]

- `0xff92c9`: R0 = layer base; fills 0x1000 halfwords with 0x8020 (the boot font's blank). Mode 0x0f clears layers 0 and 2
  with it (`0xfe326f`). Clearing layer 0 on the direction screen = `mov.w #700000, R0; jsr FF92C9`.
- `0xfc358e`: the checker over the whole of layer 2 (map 0x1e0c18, 8×4 tiles, 9×13 blits). Re-running it removes the three
  slot overlays.
- `0xff9436`: blit (R0 = map, R1 = tile address); `0xff93a4`: erase a map's rectangle with 0x0020 (bit 15 clear: on layer 2
  that leaves holes in the checker; on layer 0 it is transparent).
- `select.picture` (r10 = slot, r11 = picture record): blanks the slot's 16×21 cells, copies up to three 128-character runs to
  the slot's blocks (`SLOT_CHAR` 0x3300 / 0x3480 / 0x3600), its normal palettes to `SLOT_PAL`, and writes the map to
  `slot_b[r10]` (layer 0) [R `select.py:168-227`]. Calling it with r10 = 0 and r10 = 2 and the chosen entry's record puts the
  picked course in both outer slots, each copy in its own character blocks and palettes (needed for the lock look, §4).

### 2.3 Where the two pictures go

- **The game's slot positions** (rows 1-21, cols 4-19 and 42-57): `picture` as it is. No room above them for a title (row 0
  only), and a 22-column gap in the middle.
- **The mockup's positions** (`dir_b_*.png`: pictures at rows 4-24, cols about 9-24 and 37-52, title rows 1-3, labels rows
  26-28, panels rows 30-42, no AUTOMATIC row, no bottom bar): needs `picture`'s map destination as a parameter (about 20 bytes;
  `draw` passes `slot_b[r10]`) and the cursor at other positions (§4).
- **The arrows over the pictures** (mockup): in this MAME the draw order is layer 3/2 category 0, layer 1/0 category 0, the 3D
  pass, then layers 3, 2, 1, 0 category 1 (`build/mame/src/mame/sega/model1_v.cpp:1852-1865`) [R]: nothing is above layer 0's
  category 1, where the pictures are. `layertest.lua` moved the middle picture's tiles to layer 2 (bit 15) and put a glyph on
  layer 0 over it: the picture shows, the glyph draws over it with its transparent pixels, the 3D cursor frame shows round it,
  and the lock look's palettes still grey it [M `layertest`, snapshots 0001-0003]. So with arrows over the pictures, the
  pictures go on layer 2 and the arrows on layer 0.
- **Look mock-ups in MAME's renderer [M]**: `lookmock.lua` composes the screen from Lua on the course select (no V60 code):
  layer 0 cleared, layer 2's slot area re-checkered, the picture at the mockup positions on layer 2, title, labels, the double
  arrow, the panels. `runs/look_a/snap/vr/0000.png` (countdown-font title, SELECT TRANSMISSION panel, NORMAL yellow) and
  `runs/look_b/...` (the SHIFT title map as a stand-in, SELECT COURSE panel, REVERSE yellow). The layout of the mockup fits the
  screen as drawn.

### 2.4 The game's own pieces on the select screens [M] (character RAM dump at 1350; drawn in `look_a` / `look_b`)

| piece | map | layer-0 place on the SHIFT / course screen | characters | loaded at the course select |
|---|---|---|---|---|
| red double arrow | 0x1e2205 (8 × 6) | row 14, col 28 | 0x39a5..0x3d41, palettes 0x73/0x77/0x7a | yes (one upload serves both screens) |
| wheel panel SELECT COURSE | 0x1e0f71 (13 × 20) | row 30, col 7 | 0x3900..0x39a4 | yes |
| wheel panel SELECT TRANSMISSION | 0x1e2895 (13 × 20) | row 30, col 7 | 0x3900..0x3e14 | yes |
| STEP TO START! | 0x1e13e1 (13 × 20) | row 30, col 35 | 0x3900..0x3a22 | yes |
| red arrow | 0x1e1185 (5 × 6) | row 32, col 28 | 0x39a5..0x39b0 | yes |
| countdown | `0xff8f88` from the timer | row 39, col 28 | boot font 0x460..0x496 | yes; reprinted by state 1 every logic frame |
| SHIFT MODE SELECTOR title | 0x1e2271 (4 × 36) | row 4, col 14 | 0x39a5..0x3d6f | yes |

These maps are the `[0x40dc9b]` != 0 branch (`0xfc2c2b`, `0xfc2d55`); the set's value is 2 (test-menu setting 0..2, default 2,
`0xfc6011`) [M/R]. With 0 the select screens draw another set of maps (`0xfc2b9c`, `0xfc2cc6`): not looked at.

## 3. Lettering and the arrows

### 3.1 Printers and fonts usable on this screen

| printer | font | colours | new characters | for |
|---|---|---|---|---|
| `0xff870d` (R0 string, R1 tile; tile = (ch − 0x20)·6 + `[0x501438]`<<7 \| `[0x50143c]`, 8 and 0x8000 on the select screens) | 16×24 bold, complete capitals, chars 0x400.. | yellow with a dark shadow (palettes 8-10) [M dump]; bit 14 gives palettes 0x88-0x8a, a paler orange, not white [M dump] | 0 | the title: COURSE DIRECTION, 32 columns, rows 1-3, cols 15-46 [M `look_a`] |
| `0xffe8fb` (stack: string, tile, attribute; tile = attribute \| glyph byte from 0x2f2456) [R] | 16×24 thin (the ranking titles'), chars 0x200..0x2ff | **0x8200 white, 0xC200 yellow** (bit 14 → palettes 0x84/0x85), black outline [M `look_a`/`look_b`]; 0x8300 red | 0 | NORMAL (12 columns) and REVERSE (14 columns), the chosen one yellow; `ranking._print` emits the call (33 bytes) |
| the SHIFT MODE SELECTOR title's tiles | 16×32 orange, black outline, 2 columns a letter | as the game's other select screen title | U and N are not in it (letters S H I F T M O D E L C R): about 16 new characters, or U composed from its own pieces [I] | a title in the game's select-screen style |
| BEGINNER / MEDIUM / EXPERT, AUTOMATIC maps | outline / blue | | missing O A L V S | not usable |
| the wheel panels' captions | narrow, not on the 8-px grid | black on white | "SELECT DIRECTION" = a new caption (about 40 characters, D drawn new) [I] | the caption, or keep SELECT COURSE (design's fallback) |

### 3.2 Free characters [M] (`analyze.py` against the character dump at 1350; `analyze.txt`)

- `panel.free_chars` on the built set: 415 in five ranges. **Three are inside the slot picture blocks** (recon §5.3's inference
  holds): 0x3437-0x347f, 0x3582-0x35ff and 0x3720-0x377f are each slot's third block, rewritten by `picture` at every wheel step
  (non-zero in the dump up to the shown pictures' counts). Truly unused on the course select: **0x30e7-0x30ff (25, palette 0x61)
  and 0x32a1-0x32ff (95, palette 0x65)**. Not searched by `free_chars` and not uploaded: 0x3790-0x37ff (112, palette 0x6f, shared
  with the checker), 0x38b7-0x38ff (73, 0x71, shared with the labels), 0x3e15-0x3e7f (107, 0x7c, shared with the panels). Palettes
  0x60-0x7f are all in the select palette block (512 entries, the block's maximum).
- **On the direction screen far more is free [I from the layer dumps]**: it does not show the middle slot (blocks 0x3480-0x35ff,
  384 characters with three palettes of its own, 0x69-0x6b), the slot overlays (0x3000-0x32ff, 0x3e80-0x3fff) or the course
  select's labels and bar. Mode 0x0f re-uploads every select character and the palette block at each game start [R `0xfe3b10`],
  and the second-game runs of §7 pass through it [M]. The slot blocks are already rewritten at will by `picture`, so the race
  does not rely on them [I].
- **Recommended home for the arrows and any new lettering: the middle slot's three blocks**, uploaded by the screen's own code
  (a memory copy as `picture` does, about 40 bytes), each block's palette written by the screen. One arrow shape per block lets
  each be coloured by side for free (§12 D8).

### 3.3 The arrows (new graphics)

Character counts for a ring arrow with an outline and a head, by size (`numpy` sketch in this session) [I]: 64 px 42, 80 px 53,
96 px 73, 112 px 82 distinct non-empty characters; the clockwise and anticlockwise shapes are two sets (tiles have no flip
bits: `segaic24.cpp:55` takes `val & tile_mask` and the palette only [R]). Two 96-px arrows: about 146 characters (two of the
three middle-slot blocks), 4 672 bytes plus two 12×12 maps (about 600 bytes). Empty cells use the blank 0x8020. Which shape is
NORMAL: the sign of the lap (`tencourse.interior_on_the_left`), a byte per entry (a pad byte of the load record, or a 10-byte
table).

Upload means: (U1) more pairs in the select upload list at mode 0x0f (bank 0 holds 3 544 + 6 144 erased bytes, window 0x1df228
and 0x1fe800 [M]; `install_panels` already relocates the list), but only into the palette-shared ranges above; (U2, recommended)
a copy by the screen's code into the middle slot's blocks, from program ROM, spread over the screen's first logic frames
(two pictures plus 5-7 KB of characters in one logic frame may overrun it: `picture` alone was ~28 ms before its unrolling
[R `select.py:173`]) [I].

## 4. The cursor and the lock look

- **Objects [R]**: both cursors draw list 0x2e04b0 (4 polygons) through the TGP. Course cursor `0xfc2880`: position from the
  select table record of `[0x501940]` (x = `SLOT_X` −151 / 1 / 153, y = 88.0), scale (0.7687, 1.0, 0.8138). SHIFT cursor
  `0xfc2a5d`: x −128.0 / +128.0, y 34.0, scale (0.62, 1.0, 0.87), an extra 0x4000 turn (TGP 0xA800000), for its 24×13-tile
  pictures. The direction screen frames 128×168 pictures: the course cursor's geometry.
- **Blink [R]**: state ≤ 5: steady when the handler is 0xfc27be, else on `[0x501144]` bit 1 (4 video frames on, 4 off); state
  > 5: bit 0 (2 on, 2 off).
- **Any position, cheaply [R]**: `0xfc2880` is `movz.hw 501940, R11; mul.w #18, R11; mov.w #3, R0; jsr FF8474; mov.w #502150,
  E[R25]; movea.b <select table>[R11], R13`, then from 0xfc28a7 reads only R13's x, y (+0, +4), R25, R24 and `[0x501144]`. A
  shim doing the first three itself and `mov.w #<record>, R13; jmp FC28A7` draws the course cursor at any (x, y): about 35 bytes
  plus 8 bytes a position. At the slot positions an even cheaper call exists: `jsr FC2887` with R11 = 0 or 9 (entries 0 and 9
  sit in slots 0 and 2).
- **Positions [M/I]**: x is 1 px a unit (slot centres 96 / 248 / 400 px for −151 / 1 / 153; the SHIFT cursor at −128 ↔ 120
  px) [M layer dumps]. y from the two screens' pictures: y_px ≈ 183 − 1.04·y [I, two points]; pictures at rows 4-24 (centre 116
  px) → y ≈ 65; the mockup's columns 9-24 / 37-52 (centres 136 / 360 px) → x ≈ −112 / +112. To be checked in the first build's snapshot.
- **Steady after the lock**: the frame is steady only when the handler is literally 0xfc27be. Either the direction lock sets
  0xfc27be and the project's `start` gets a branch on a phase cell (direction palettes, then the cursor shim), or the frame
  blinks slowly for the 0x21 logic frames before state 6 (builder's choice; visible).
- **Chosen in colour, the other grey [R + M]**: palettes only (§1.1); with the two copies in slots 0 and 2, a direction
  `start` copies the record's chosen set to the chosen side's `SLOT_PAL` and the grey set to the other's (about 60-80 bytes).
  The project's `start` itself cannot serve: it decides by `first_of([0x501940]) + slot`, so one slot only would match.

## 5. Wheel and timing

- **Threshold [R + M]**: SHIFT: `cmp.w #1C, R10; ble` → 1 when R10 > 28, R10 = (`[0x501060]` + `[0x50106c]`) >> 1, −127..127.
  Paddle sweep (`sweep`, autoplay `VR_WHEEL_SWEEP`): 125-135 → 0 (dead zone), 150 → 27 (28 when held, `base`), 151 → 28, 152 → 30, 160 → 44, 200 →
  112, 210+ → 127. So REVERSE from paddle 152 on; tests should use 128 (0) and 170+ (61+). 0x1c is about a fifth of full lock.
- **The wheel carries over [M]**: on entering the screen the wheel is where it chose the course: entry 6's band is R10 26-50
  (`select.BANDS`), entries 7-9 are 51 and beyond. Read literally, the design pre-selects REVERSE for Metropolis (most of its
  band), Pacific Coast and both Surfers courses, and the countdown takes REVERSE if the player does nothing. Owner's decision
  (§12 D6).
- **Countdown [M]**: timer := 0x140 at the screen's first frame shows 10 (timer >> 5) and locks at 0x20 after 288 logic frames:
  575 video frames, 10.0 s (`proto_p2`). Keep the start below 0x180, or state 1's voice cue (B05C on this setting) fires.
- **The course press cannot confirm the direction [R + M]**: the edge is `((new ^ old) & new)` bit 7 of the gas value, sampled
  once a logic frame (`0xfe6812..0xfe6837`): 0xffff for one logic frame when the pedal crosses 128 upward, nothing again until
  it has gone below 128. The course lock is seen on that frame, the lock handler runs on the next, the screen's handler on the
  one after: the cell is 0 by then. Held gas: no lock until the countdown (`proto_p3`).
- **Lock to exit**: the game's, 198 video frames (§1.1); with (a) the screen's lock sets timer := 0x20 as the original locks do.

## 6. Room for the code and data

**Estimate [I]** (the SHIFT MODE SELECTOR is 522 + 298 bytes):

| piece | bytes |
|---|---|
| `dirlock` at 0xfc2788 (variant and single-play test, flag 0, handler, timer) | 60 |
| flag clear at mode 0x10 state 0 (§7), the ranking gate (§8) | 20 + 30 |
| `dirinit`, over 2-3 logic frames: layer 0 cleared, checker, two pictures, four maps, title, labels, arrow upload and maps, palettes | 400 |
| `dirsel`: wheel, threshold and start rule, cursor shim, label recolour on a change, lock tests, lock (flag, timer, handler) | 220 |
| `dirdone`: chosen / grey palettes of two slots, cursor | 100 |
| `picture`'s destination as a parameter; positions, strings, destinations | 20 + 80 |
| **code and tables** | **≈ 930** |
| data: two arrows (≈ 146 characters, 4 672) and maps (600), caption (≈ 40 characters, 1 280 + map), three palettes (96), SHIFT-style title map and U/N (≈ 780, only with that font) | **≈ 6.7-7.5 KB** |

**The layout, measured on the tree / the set [M]** (`analyze.py`, `analyze.txt`):

| region | numbers |
|---|---|
| directory image | 0x278d70..0x27ab4d, 7 645 bytes; `end − loader` = 4 821 against `tests/test_directory.py:138`'s `< 5000`: **179 left**. The bound is a test constant ("routines stay small"), not hardware |
| after the image | tile tables from 0x27ab50 (7 × 5 120), race blobs 0x283750 (7 × 1 808), spawn lists 0x2868c0..0x2899dc, all from `directory_layout()["end"]` (`tencourse.py:226-274`): growing the image by N moves all three by N rounded to 16, and the select pictures placed first-fit after them |
| `CODE_FREE` erased runs past the image | six 720/744-byte tails inside spawn slots (0x286cf4 ...); **4 032 at 0x28e9b0** between the pictures' end and the start-gantry block (0x28f970, 1 024, top-anchored); 98 inside the gantry block |
| colour-table run | annex 0x2b90c0..0x2bcb00 (its 1 356-byte internal gap at 0x2b9280); **13 568 erased at 0x2bcb00..0x2c0000** |
| program ROM, unallocated | 12 800 at 0x2fce00; 1 623 at 0x2df9a9 |
| boot ROM, unallocated | 14 267 at 0xfdc845; 3 792 at 0xfff120 (ends at the reset vector 0xfffff0); 512 at 0xfe700c; 218 at 0xffef26 |
| bank 0 (select screens) | 3 544 at window 0x1df228, 6 144 at 0x1fe800 |

**Who reads them [M]** (`memtrace.lua` read taps, `tapsum.py`, `tapsum.txt`): runs `tap_norm` and `tap_rev` (boot, attract,
coin, course select, about 165 s of a Metropolis race, normal / reverse) and `fixed2` (operator-fixed course: SHIFT MODE SELECTOR, a Bay
Bridge race): 0x2fce00.., 0x2df9a8.., the colour tail 0x2bcb00.. and `CODE_FREE`'s tail are read only by the colour-table upload
PC 0xfe6b64, each halfword once, frames 155-268; the four boot runs are never read (the only read near them is the reset vector
fetch at 0xfffff0, outside the run); the bank-0 runs are never read with bank 0 mapped. Same result as stage 2's taps
(`docs/spike/2026-11-phase26-stage2-recon.md` §1), now including the select screens and the operator's screen. Not tapped:
linked play, the test menu.

**Options for the code (≈ 930 bytes)**:
- (R1) in the directory image, with the test bound raised (to 6 000): one layout system; moves the tile tables, race blobs,
  spawn lists and the code-area pictures by ≈ 0x3a0 (stage 2 moved them 0x1b0); the 4 032-byte tail shrinks to ≈ 3 100.
- (R2) a new top-anchored block just below the start-gantry block, in the 4 032-byte tail: nothing moves; `picture_exclusions`
  and `annex_regions` must end before it (as for the gantry).
- (R3) a top-anchored block at the end of the colour run (0x2c0000 − size): nothing moves; the annex's region shrinks to
  ≈ 6 KB of spare. Same reader status as the annex.

**Recommended**: code in R1 (or R2 if the builder prefers no moves) and the data (≈ 7 KB) in R3 (the only vetted run with room
apart from 0x2fce00, which the project has never allocated from). Builder's choice (design §7); invisible to the player.

## 7. The flag's life

**Today [R]**: writers of 0x502294: the loader's write-back (1 when it served a variant, else 0; `directory.py:344`), `bankdemo`
(`directory.py:429`, at the attract's bank sites 0xfe2160 and 0xfe2cf7); Lua: `direction.lua` (VR_DIRECTION, every frame the
mode byte reads 0x10), `direction_off.lua`, tests' `VR_POKE` before the coin (`tests/test_direction.py:61`,
`tests/test_reverse_build.py:728`). Readers: `entry` (menu path only), `dirattr`, `startbit`, `figures`, `figmirror`
(`direction.py`); 8 references in the program ROM [M `find_refs`]; Lua loggers `start_log.lua`, `figures_log.lua`. The loader is
called at 0xfe217c (attract demo), 0xfe2b23 (mode 5, linked), 0xfe2d13 (mode 6, Big Forest), 0xfe4177 (mode 0x11) and 0xff0be8
(a cabinet joining a linked race) [R].

**Measured after a reverse race** (`attract_after_rev2`: a one-lap reverse Metropolis race with the clock held, then 420 s;
`figtap.lua` taps writes into the object pool `[0x501350]` by the start-figure placement and the attract pit scene; `coin2_*`):

| moment | flag |
|---|---|
| race, results, name entry (modes 0x14-0x1e) | 1 (what the loader served) |
| attract load (mode 0x02, `bankdemo` at 0xfe2160) | 0 from frame 10381 |
| the attract pit scene (mode 0x07, pool objects 5, 7, 8: writes by 0xfc0100.. at 12366, 14080, 16736, ...) | 0 every time (6 scenes) |
| a coin during the name entry (`coin2_name`) | the name entry ends; mode 0x02 runs (flag 0) before 0x0a, 0x0f, 0x10 |
| a coin during the results (`coin2_res`) | ignored until the attract; mode 0x02 before 0x0a |

(In those two runs `direction.lua` wrote 1 again on the second select screen: that is the debug switch, not the game.)

**What it must be, and who sets it**:

| situation | must be | set by |
|---|---|---|
| game start (mode 0x0a) and the select screen shown again | 0 | today: the attract load before it (both measured paths). Robust: a clear at mode 0x10 state 0 (`0xfe3cce`, `mov.b #0, 5019C0[PC]`, 8 bytes → `jsr`; covers both screens and every cabinet) |
| course lock on an original, or in linked play | 0 | the clear above, or `dirlock` writing 0 |
| direction lock | the choice | `dirsel` |
| operator-fixed course | 0 | the state-0 clear (`0xfc277c` is never reached on that path [M `fixed2`]) |
| attract demo (mode 0x02, mode 6) | 0 | `bankdemo` (exists) |
| linked loads 0xfe2b07 (mode 5) and 0xfe1d37 (joining cabinet) | 0 | route both to `bankdemo` (zero code bytes: the two sites change target) |
| race load (mode 0x11) | as set | loader's write-back records what was served |

**Smallest set** making "1 only when the direction screen asked for it" true: (1) the direction lock writes the choice; (2) one
clear common to every select screen (state 0); (3) `bankdemo` at the two attract sites (exists); (4) `bankdemo` at the two linked
sites. Without (2) the operator's screen and an unmeasured post-race path could inherit a 1; without (4) a linked load right
after a reverse race could serve a variant (stage 1 findings §7). The attract pit scene runs only in mode 0x07, after mode 0x02's
`bankdemo` [M], so it never sees 1 as long as `bankdemo` stays at 0xfe2160 / 0xfe2cf7.

## 8. Rankings and the name entry

- **Sites [R]**: at the race's end (`0xfe4b21..`), `jsr FC40CE`: `movz.bw #0, 5018FC`; `test1 #1, 501174` (race finished);
  `be FC417C` (rsr); the setter `0xfc4208` (now the project's, by `[0x40fc68]`); if the elapsed time `[0x501168]` beats entry 23
  (+0x228) it is written there (+4, +8, +0xc, +0x10, +0x14) and bubbled up (`0xfc417d`), then `set1 #0, 5018FC`. The name entry
  is entered when `5018FC` is set: `0xfe4b4f` and `0xfe658c` (handler 0xfc4226 on entity `[0x501334]`); `0xfc4661` writes the
  name. The project's `ranking.py` sites are the setter, the initialiser, `id_store` (0xfc270f), the attract page and the title.
- **Today a reverse race writes [M]** (`fin_rev2`, one lap, clock held): Metropolis's table (0x40f340..) written at frame 8387 by
  0xfc4168 and 0xfc41b8.., record flag set by 0xfc4174, name entry (mode 0x1e, handler 0xfc429b) from 8841 to 10217. The normal
  one-lap race (`fin_nor2`) does the same. A timed-out race (`fin_rev`) writes nothing: modes 0x15, 0x16, 0x1b, 0x1c, 0x1d, then
  0x02, no 0x1e.
- **Smallest change**: replace `movz.bw #0, 5018FC; test1 #1, 501174` (0xfc40ce, 16 bytes; no branch lands at 0xfc40d6 [R])
  with `jsr rankgate` + nops, keeping `be FC417C`: `rankgate` clears 5018FC as the original, then sets Z when the flag is 1
  (skip), else does the original `test1` (≈ 30 bytes, one pattern-checked boot site). Nothing is written, 5018FC stays 0, so
  `0xfe4b4f` / `0xfe658c` skip the name entry.
- **What the player then sees [M + I]**: the flow of a race without a record (`fin_rev`): finish (0x19, 0x1a when finished),
  results 0x15 / 0x16, the race-end ranking page 0x1b-0x1d, which shows the normal course's table under its name (Phase 23b,
  `tests/test_ranking.py:229`) without the player's time, then the attract. Whether to skip that page is the owner's (§12 D9).

## 9. Proving it headless

- **Today [R + M]**: `autoplay.lua`: coin 600, START 720, paddle `WHEEL_FOR_ENTRY[entry]` from 735, the gas floored from 1400
  and held; the race start is detected from TGP command 0x0680 (not timed). Reverse races set the flag with `direction.lua`.
- **The runner can [M]**: a `VR_EXTRA_LUA` script's frame callback runs after autoplay's and its `set_value` wins: `proto.lua`
  released the gas, held paddle 200, pressed again at chosen frames, and logged the handler, timer, edge, flag and entry
  (`proto_p1..p3`). Snapshots, RAM and layer dumps at chosen frames work under `-video none` (§10).
- **A stage-3 test needs**: after the course lock (handler 0xfc27be or the screen's), paddle 128 (NORMAL) or 170+ (REVERSE),
  the gas below 128 for at least one logic frame, then 255; log the screen's handler, `[0x501940]`, the flag at the last mode-0x10
  frame and after the load (the loader's write-back), the cursor side, the countdown cell.
- **Existing tests [I, risk]**: every race on entries 3-9 now meets the screen. With autoplay unchanged (gas held) each such
  race waits for the 10-s countdown, and the countdown takes the course's wheel position (REVERSE on entries 7-9, and on 6 above
  28) unless the start rule of §12 D6 is taken. `direction.lua` writes the flag on every mode-0x10 frame after the V60 has written
  it, so it would override the screen. Recommended: autoplay answers the screen by default (release and press 2-4 logic frames
  after it appears, steering right when VR_DIRECTION=1), so a converted race starts ≈ 10 frames later than today; then review the
  tests that use absolute frames (`VR_FIELD_FROM` 1400, the start windows, `VR_TRACE_DUMP`, fixed `VR_SNAPS`).

Test cases (design §8):

| case | inputs | logs and asserts |
|---|---|---|
| reverse through the screen | entry k (3-9), paddle 200 on the screen, second press | screen handler seen; flag 1 at the load; the variant's checkpoints / yaw (as the reverse race tests) |
| normal through the screen | paddle 128, second press | flag 0; the normal race's start pose |
| countdown decides | no second press, paddle 200 / 128 | lock at ≈ 575 frames after the screen; flag 1 / 0 |
| the course press does not confirm | gas held from the course select | no lock before the countdown |
| an original | entries 0-2 | handler never the screen's; lock to mode 0x11 in 198 frames; flag 0 |
| operator-fixed | `VR_POKE=40dca1=2,501103=2` | SHIFT handler 0xfc29b3; no screen; flag 0 |
| attract after a reverse race | one-lap reverse race with the clock held, then ≥ 300 s | flag 0 from the attract load; pit-scene writes (0xfc0100..) only with flag 0 |
| reverse race records nothing | one-lap reverse race, clock held | no write to the entry's table, `5018FC` 0, no mode 0x1e; the normal one-lap race still enters the name |
| linked play | not runnable headless (no link partner) | static: `dirlock` tests `[0x40dc8c]`; both linked bank sites decode to `bankdemo` |

## 10. Showing the owner the look

- `VR_SNAPS="f1,f2"` (or `VR_SNAPS_AFTER_START`) → MAME writes `snap/vr/NNNN.png` (496 × 384) into the run's work directory,
  headless [M `base`, `look_*`]. `select_dump.lua` (`VR_SELECT_DIR`, `VR_SELECT_DUMP`) dumps tile, character and palette RAM at
  chosen frames; `render.py` draws layers, maps and characters from them offline [M].
- Before any V60 code, `lookmock.lua` composes candidate looks in MAME's own renderer (fonts, colours, layer order) [M `look_a`,
  `look_b`]; the arrows can be added the same way (write their characters into the middle slot's blocks and their tiles on layer
  0 from Lua). After the build: snapshots at screen frames for NORMAL, REVERSE and the locked look.

## 11. Contradictions and corrections

1. **Slots against the mockup**: design §6.6 says "the left and right picture slots"; the chosen mockup has the pictures lower
   (rows 4-24) and closer together (cols ≈ 9-24, 37-52) with the title above. At the slot positions there is no room for a title.
2. **The arrows over the pictures** need the pictures on layer 2 (MAME's draw order, §2.3); not in the design, measured feasible.
3. **"Wheel straight is NORMAL" with the wheel carried over** pre-selects REVERSE on entries 7-9 (and most of 6), and the
   countdown then takes REVERSE (§5).
4. **Recon §5.3's free characters**: confirmed that three of `free_chars`' five ranges are inside the slot picture blocks; only 120
   characters are free on the course select in its ranges (§3.2).
5. **Recon §5.1**: `start` is at 0x27a19e in this build (the recon's 0x27a323 was p25play2's).
6. **Stage 1 findings §7 "the flag is not cleared at game start"**: in both measured post-race coin paths the attract load (with
   `bankdemo`) ran before mode 0x0a (§7); the clear at state 0 is still recommended for the paths not measured.
7. **The attract pit scene** uses pool objects 5, 7 and 8, not 0-2, and runs in mode 0x07 (§7) [M].

## 12. Decisions for the owner

| | decision | options and cost |
|---|---|---|
| D1 | picture positions | (a) the mockup's (rows 4-24, inset; title above): `picture` gets a destination parameter (≈ 20 bytes), cursor at measured positions — recommended, it is the chosen layout; (b) the game's slots (no code, no title room) |
| D2 | arrows | (a) over the pictures (mockup): pictures on layer 2, arrows on layer 0, ≈ 146 characters — recommended; (b) beside the pictures: no layer change, smaller arrows |
| D3 | title | (a) the countdown's bold yellow font, 0 characters (`look_a`); (b) the SHIFT MODE SELECTOR's orange title style, U and N drawn (≈ 16 characters + a 4 × 32 map); (c) new lettering |
| D4 | labels | (a) the ranking titles' font, yellow / white by attribute, 0 characters (`look_a`, `look_b`); (b) bold new lettering like the mockup (≈ 80 characters) |
| D5 | wheel panel caption | (a) SELECT COURSE as it is (design's fallback, 0 cost); (b) a new SELECT DIRECTION caption (≈ 40 characters, D drawn new) |
| D6 | where the choice starts | (a) the wheel as it is (REVERSE pre-selected on entries 7-9 and most of 6; the countdown takes it); (b) NORMAL until the wheel has been at or left of 0x1c once on this screen, then the wheel (≈ 20 bytes) — recommended; (c) relative to the wheel at the screen's start |
| D7 | course lock look before the screen | (a) switch at once; (b) ≈ 0.5 s of the grey / colour confirmation first (≈ 20 bytes) |
| D8 | arrow colours | per side (left white, right red, as the mockup) or the same: free either way (palette per block) |
| D9 | after a reverse race | (a) today's flow: the race-end ranking page shows the normal course's table; (b) skip that page (another site, not designed) |

## 13. Recommended build order

| # | piece | proved by |
|---|---|---|
| 1 | the flag's life: state-0 clear, linked bank sites → `bankdemo` | listings of the sites; MAME: flag 0 at the select after a reverse race, on the operator's screen, through the attract's pit scenes |
| 2 | the ranking gate at 0xfc40ce | MAME: one-lap reverse race (clock held) writes nothing, no mode 0x1e; the normal one still enters the name |
| 3 | the hook and a bare screen: `dirlock`, `dirsel` (wheel, D6 rule, cursor shim, gas-edge and timer locks, flag), `dirdone` without graphics | MAME cases of §9 (reverse, normal, countdown, held gas, original, operator-fixed); lock to mode 0x11 in 198 frames |
| 4 | autoplay answers the screen; `direction.lua` retired or made consistent; frame-window review | the reverse and normal race tests on one course each, start ≈ 10 frames later than today |
| 5 | drawing: layer-0 clear, checker, two pictures (layer 2, D1), maps, title (D3), labels (D4) | snapshots NORMAL / REVERSE for the owner |
| 6 | arrows and caption (build-time rendering, upload to the middle slot's blocks, palettes per side) | snapshots; character counts against the blocks |
| 7 | lock look: chosen in colour / other grey, labels, steady or blinking frame | snapshot sequence across the lock |
| 8 | ROM placement (R1/R2 code, R3 data), allocator exclusions | the layout tests; a read tap over the new block across select, race and attract (only 0xfe6b64) |
| 9 | the affected tests and the known-failure list; Pascal's drive | |

## 14. Not verified

- Linked play (no partner cabinet headless): the screen skipped, the two linked bank sites, a slave's immediate lock.
- `[0x40dc9b]` other than 2 (the other select-screen maps and countdown cell); other operator settings.
- The cursor frame's y and x at the mockup positions (inferred formula, §4).
- CPU time of drawing two pictures and uploading the arrows: whether it fits one logic frame.
- That the race never displays the middle slot's blocks after the screen (inferred from `picture` rewriting them at will).
- Other post-race paths (coin at other moments, continue) reaching mode 0x0a without mode 0x02.
- The test menu's ROM check on any new region; taps in the test menu and linked play.
- Whether a race whose start moves by ≈ 10 frames stays identical (the game's random state per frame).
- Real hardware's layer priority (this MAME's `model1_v.cpp` draw order is the reference used).
- U composed from the SHIFT title's own pieces; the caption's letters from the panels' glyphs (not drawn).
- Whether anything rewrites palettes 0x84 / 0x85 (the yellow labels) while the select screen is up (measured once, frame 1350).
