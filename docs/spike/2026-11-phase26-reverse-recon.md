# Phase 26 recon: racing a course in the opposite direction (11 Nov 2026)

Read-only recon on build `out/p25play2` (Phase 25's tree) for the reverse-course design
(`docs/superpowers/specs/2026-11-11-reverse-courses-design.md`). Three strands: the direction-dependent data and the
room for a second set (§1-3), the scenery seen from behind (§4), the front end and the SHIFT MODE SELECTOR screen
(§5). **[V]** = verified by running code (tables decoded from the built ROM, disassembly, or a MAME trace);
**[R]** = read from the repo's code or docs. Nothing here was verified by driving a reversed course: no such build
exists yet.

## 1. What depends on the direction of travel

### 1.1 Tables in the data bank (reached through the entry's header)

The loader takes everything from the entry's header (`directory.py:235-282`): header+4 the segment array, +0x10 the
line table, `*(header+8)` the collision map, `*(header+0xc)` the surface table, header+0 the backdrop directory. A
second header in the same bank can point at the same collision map, surface table and backdrop. [R]

| Item | Size | Reversed |
|---|---|---|
| Eight road lines, 16 bytes a point + 8 wrap points each (`course.py:234`, `bank.py:60`) | 43 264-76 800 bytes a course; one line 5 408-9 600 [V] | Point order reversed; heading high half turned half a turn and unwrapped again (the lap's net turn changes sign: −16384 on eight courses, +16384 on Alpine and Pacific Coast today [V]); wrap points regenerated (`bank.encode_line`); pitch (heading low half) and roll (link low half) negated; `link >> 16` recomputed against the reversed segment array |
| Segment array, 8 bytes a segment `(2, index, road_point, flag)` (`course.py:263`) | 4 160-8 752 bytes [V] | Index k stays collision quad k; only `road_point` changes |
| Pointer block (72 bytes), header (0x20) | 112 bytes | New copies; collision and surface pointers unchanged |
| Collision map (32 768 bytes), surface table (1 byte a quad) | - | Not direction-dependent |

Game rules that make the road-point numbering directional [V, boot disassembly]:

- **Lap counting** is the road point's wrap only: at `0xfea247`, previous − new > 100 counts a lap, < −100
  decrements the guard `+0x70`. Driving backwards on forward tables never counts a lap.
- **Checkpoints** fire only on forward steps of 1-29 points (`0xfea1c6`).
- **No separate wrong-way detection** was found among the readers of the road heading `+0xeb`.
- The opponent cursor compares road points as plain numbers (formats §15).
- Segment flag bit 0 is tested at `0xfe9234`, `0xfeb07f`, `0xfeb1b4`, `0xffd350`, `0xffd467`; bit 7 at `0xffa67b`.
  The seven converted courses carry flag 1 only; the originals carry pit-lane 66 (Big Forest segments 30-59 and
  1085-1088, Acropolis 28-55 and 938-941) and Bay Bridge 129 / 4 / 16 / 2 on its branches.

### 1.2 Race data (the entry's race blob, load record +0x2c; 0 = the template's boot-ROM tables)

| Item | Size | Direction |
|---|---|---|
| Checkpoint record | 96 bytes | road-point indices rising from 0 |
| 12 time records | 1 152 bytes | extension k belongs to sector (k−1) mod sectors (`convert/race.py:47`) |
| Car table, 16 × 0x20 | 512 bytes | line index and start road point (0-15 in every table [V]); road-relative |
| Whole blob | 1 808 bytes (`RACE_BLOB_BYTES`, `race.py:35`) | |

Checkpoints in the build [V]: Alpine (0, 65, 192, 333), Amazon (0, 117, 237), Diablo (0, 179, 289, 421), Metropolis
(0, 126, 222), Pacific (0, 186, 320), Oval (0, 127, 299), Surfers Road (0, 127, 299). The gate rule is asymmetric: a
gate is dropped within 50 points after the line or 8 before it (`convert/race.py:23-36`), and `hide_unused_gates`
removes C.P. gates from the shared scenery by the forward list (`gates.py:62`). [R]

### 1.3 The start grid is wired by template [V]

- `0xfe41cb`: `cmp.b #2, [0x501934]` sets bit 0x1e of the task at `[0x50134c]`, for data index 2 (the Big Forest
  template: Big Forest and Alpine) and `[0x40d826] < 2`.
- **Bit set (Big Forest, Alpine)**: opponent i starts at road point `(count − 3 × (16 − i)) rem count`, lap −1
  (`0xfe8c5a..0xfe8c91`); the car table's start point is ignored. The player goes through `0xff21a5` →
  `0xff4061`: an ABSOLUTE pose by data index (Big Forest `0xff40d9` = (−230.38, 30.00, −269.57)), pitch, yaw and
  roll zeroed at `0xff21d7..0xff21e1` (yaw 0 = +z). The directory patches only the pit autopilot's and crew's calls
  of `0xff4061` (`course.py:57-60`); the calls at `0xff21a5`, `0xfc005f` (race intro), `0xfc0ec8`, `0xff4165` are
  untouched.
- **Bit clear (the Bay Bridge and Acropolis templates: the other eight entries)**: each car starts at its car-table
  point on its own line; position, yaw (heading high half × 4), pitch and roll come from that line point
  (`0xfe8c94..0xfe8ce2`). Fully road-relative.
- Converter side: `place.GRID_OF_COURSE` (`place.py:22`) and `choose_placement` aim the road at that pose;
  `GRID_CLEAR_OF_COURSE` (`tencourse.py:36`) and `SHIFT_GRID_CLEAR` (`collision.py:1356`) are before/after-line
  asymmetric. [R]

### 1.4 Spawn list, pit, HUD map

- **Spawn lists** [V]: Alpine, Diablo and Pacific Coast hold the minimap and the host's start gantry (1 076 bytes);
  Amazon, Metropolis, the Oval and Surfers Road the minimap only (no direction-dependent content). The gantries
  stand at the line with yaw within a few degrees of the forward road heading.
- **Pit**: the entry quad (load +0x10) fires on the quad or the next in the list, only when the car's heading is
  within 90° of the quad's attribute (`0xfe8eae..0xfe8ec5`) [V]; the converter reorders or duplicates quads so the
  pair spans the lane at the FORWARD mouth (`collision.py:1645`, `:1718`); the box is (x, y, z, heading) in the maps
  record, `pitaim` aims 10 units short along the heading and `pitpark` sets the yaw (`directory.py:430-499`) [R].
- **HUD map**: `map_tx` (load +0x34) and `map_cross` (+0x38) per entry, by which side the interior lies
  (`tencourse.interior_on_the_left`, `tencourse.py:193`). Reversing flips all: the five clockwise converted courses
  take 237.0 / 22, Alpine and Pacific Coast go back to 149.0 / 0. The outline object is geometry only.

## 2. The collision quads carry the forward direction

The list block and the cell map are direction-free; every quad is not. [V]

- **Word 15** of a quad is `−atan2(dx, dz)` of forward travel: non-zero on every converted tarmac quad, within
  22.5° of the forward centreline on 514-527 of 527 (Metropolis) up to 756 of 756 (the Oval).
- **Corner order** is front-left, front-right, back-right, back-left (`collision.order_corners`,
  `collision.py:691`); 23-79 converted tarmac quads per course deviate.
- **The TGP uses both**: command 0x1500 (handler 0x34b) takes the attribute's sine and cosine and corners 0, 1, 2
  to produce the six values the V60 stores at `+0xf1, +0xed, +0xf5, +0xf9, +0xfd, +0x101`; command 0x1800 (handler
  0x431) returns the attribute; handler 0x463 (command 0x1980) also uses it, but no V60 site sends it.

Where the game uses the attribute (`+0xeb`):

| Site | Effect |
|---|---|
| `0xfebd50..0xfebdb8` | off-course put-back: yaw turned to the attribute over 0x20 frames |
| `0xfebf64..0xfebffd` | four-wall-wheels put-back: yaw turned to the attribute over 10 frames |
| `0xffd4f5..0xffd548` | a third put-back of the same form (entity in R19) |
| `0xfe957e..0xfe95af` | spin after a wall hit: yaw and heading eased towards the attribute |
| `0xfeb2e7..0xfeb335` | the player's steering assist: engages when the yaw is within ±0x222 of the attribute, nudges up to 0x18 a frame |
| `0xfe8eae` | pit entry heading test |
| `0xfe924f`, `0xfe926f` | the player's car under game control: heading eased or snapped to the attribute |
| `0xfe8d0b..0xfe8d23`, `0xff2205..0xff221d` | start: `+0x36` seeded from the attribute |
| `0xfec003..0xfec030` | wall kick: treats the direction as an axis (subtracts 0x8000 beyond ±90°): the one direction-free use |

With unmodified quads a reversed car is turned to face forward at every put-back, and the steering assist does not
engage.

The two ways out, in numbers:

- **Run-time**: 14 boot-ROM sites send command 0x1800 (`0xfe8d0b, 0xfe8f97, 0xfe9147, 0xfe92fd, 0xfea927,
  0xfeaa82, 0xfeab05, 0xfebd50, 0xfec003, 0xfec152, 0xff2205, 0xff241c, 0xff4c9e, 0xffcffc`) and 7 send 0x1500. The
  TGP program itself has 2 free words (0x7ee, 0x7ef).
- **A second quad pool**: 19 760-32 960 words per converted course against 7 651 free. Does not fit for any course.

Forward-only assumptions baked into the converter and into the shared quads [R, measured V]:

- **Front-edge credit** (`road.py:168-198`): a quad takes the last point its front (corners 0 and 1) has reached.
  In the build the front is 0 or 1 point from the credit while the rear lies up to 3 or more points back (quads span
  up to 11 points on Alpine; lengths p90 26-35 units, max 37-111). A reversed credit cannot be derived from the
  forward array: it needs the quad geometry (`tgp.decode_quad`) and the centreline.
- **Line wrap** (`road.py:184-205`): straddlers take n−1; `END_SNAP` pins the first and last segments.
- **Geometry before the line**: `END_SPLIT_UNITS` 120 / `END_SPLIT_LEN` 15 (`collision.py:2648-2651`),
  `MERGE_KEEP_ENDS` 3 / `MERGE_KEEP_UNITS` 100 (`:416-419`), `START_BAND` (one quad from −12 to 0 credited n−1,
  alone under the car; `:2654`, `:2765`), `SEAM_OVERLAP` 0.5.
- **Measured round the line**: on the far side (the reversed approach) quads are 12-36 units long; on six of the
  seven converted courses quad 0 is the only quad under laterals −8..8 from +2 to at least +4 past the line; on
  Alpine quads 0, 1, 562 and 564 lie side by side at +0..+2.
- **Lap derivation**: `order_slices(direction=…)` (`lap.py:109`, `:236`) re-derives the lap and everything
  downstream (`road_profile`, `arc_height`, `saturn_collision`) is keyed on it: running the pipeline with a reversed
  lap builds a DIFFERENT collision. No existing code reverses built tables.

## 3. Room

### 3.1 The direction-dependent tables per course (header + segment array + pointer block + 8 lines) [V]

| Entry | Bank | Points | Segments | Seg. array | 8 lines | Total | One line |
|---|---|---|---|---|---|---|---|
| Big Forest | 3 | 338 | 1093 | 8 752 | 44 288 | 53 152 | 5 536 |
| Bay Bridge | 1 | 418 | 674 | 5 400 | 54 496 | 60 016 | 6 816 |
| Acropolis | 2 | 592 | 946 | 7 576 | 76 800 | 84 496 | 9 600 |
| Alpine | 3 | 452 | 565 | 4 528 | 58 880 | 63 520 | 7 360 |
| Amazon Falls | 1 | 330 | 519 | 4 160 | 43 264 | 47 536 | 5 408 |
| Diablo Canyon | 2 | 457 | 809 | 6 480 | 59 520 | 66 112 | 7 440 |
| Metropolis | 2 | 365 | 527 | 4 224 | 47 744 | 52 080 | 5 968 |
| Pacific Coast | 1 | 410 | 647 | 5 184 | 53 504 | 58 800 | 6 688 |
| Surfers Oval | 1 | 387 | 756 | 6 056 | 50 560 | 56 736 | 6 320 |
| Surfers Road | 1 | 441 | 903 | 7 232 | 57 472 | 64 816 | 7 184 |

### 3.2 Free space in the build [V]

| Region | Free | Notes |
|---|---|---|
| Data bank 1 (Bay Bridge, Amazon, Pacific, the Oval, Surfers Road) | 113 380, one run at +0xe451c | the four converted courses there need 227 888 for eight lines each: with k distinct lines a variant, about 23 088 + 25 600 × k (k = 3: 99 888 fits; k = 4: 125 488 does not) |
| Data bank 2 (Acropolis, Diablo, Metropolis) | 385 362 (217 910 at +0x8acca, 167 452 at +0xd71e4) | Diablo + Metropolis need 118 192 |
| Data bank 3 (Big Forest, Alpine) | 551 062 (417 106 at +0x5a2ae, 133 956 at +0xdf4bc) | Alpine needs 63 520 |
| Data bank 0 (the select screens) | 9 688 (3 544 at 0x1df228, 6 144 at 0x1fe800) | one more select picture is 9.2-11.2 KB: none fits |
| Program ROM `CODE_FREE` (0x278d70..0x28fd70, 94 208) | 5 120 at 0x28e970, plus six gaps of 720-744 inside spawn slots | in use: directory 7 571, seven tile tables 35 840, seven race blobs 12 656, seven spawn slots 12 572, select pictures of entries 7 and 8 |
| Program ROM elsewhere | 12 800 at 0x2fce00; 1 623 at 0x2df9a9; 28 496 at 0x2b90b0 (colour allocator's territory) | no allocator hands these out for tables; whether the game reads them was not tapped |
| Boot ROM | 14 267 at 0xfdc845; 3 792 at 0xfff120; 512 at 0xfe700c; 218 at 0xffef26 | byte-identical to the original set; `_check` restricts `race` to the program ROM (`directory.py:128`), spawn tables may be boot addresses |
| TGP data | 7 651 words | a second pool fits for no course |
| Polygon ROM | 718 108 bytes | |
| Battery RAM (rankings) | 384 at 0x40ee80, 403 at 0x40fc6d | a table is 0x240: no extra table fits |

A bank-1 variant cannot simply move to another bank: the collision map, surface table and backdrop are window
pointers into the entry's own bank [R].

### 3.3 Where ten is wired in

- `directory.ENTRIES = 10` (`directory.py:50`) sizes the select (24 bytes an entry), load (64), maps (64) and picture
  (4) tables; growing the directory moves the tile tables, race blobs and spawn lists, all addressed from
  `directory_layout()["end"]` (`tencourse.py:172-219`).
- The entry lookup `_entry_in_r8` (`directory.py:205-222`) is `[0x501940] << 6`, inlined in 11 routines (loader,
  bank, pit, music, cars, gfx, mapobj, pitbox, pitaim, pitpark, pitstops); the maps table is reached at the same
  stride. The menu entry is used only when its template byte equals `[0x501934]`, else `FALLBACK` (1, 2, 0) by data
  index (the attract demo, a linked master).
- `tests/test_directory.py:138` asserts `end − loader < 5000` (4 887 now): a test constant, not a hardware limit.
- Select screen (`select.py`): nine band thresholds, the window clamp `clamp(i − 1, 0, 7)`, ten wheel values.
- Ranking (`ranking.py`): `COURSES = 10` sizes its arrays; keyed by the ranking id `[0x40fc68]`; the setter has no
  bounds check.

## 4. The scenery from the other side

- **What is drawn** is chosen by the camera's cell and yaw, not by the road point or the direction of travel [V]:
  `0xff7beb` computes the 128-unit cell from the camera's position; `0xff7d38..0xff7e1e` walks a 5×5 neighbourhood
  against a draw mask built from the camera yaw `0x501A2C` (`0xff7ea1`; a 2×2 block when looking steeply down,
  `0xff7e51`). The converted tile tables are binned by cell (`geometry.py:221-300`); `keep_near` is the centreline
  as an unordered point set. Nothing is forward-only.
- **Converted courses**: every drawn polygon is two-sided (flags 0x4801; `encode_object(..., no_cull=True)`,
  `geometry.py:261`): 5 954-6 832 polygons a course, none culled from behind. [V]
- **Originals**: 99.95-99.98 % of tile polygons are one-sided. Faces against and along travel are about as many
  (Big Forest 1 563 / 1 429 within 100 units of the road, Bay Bridge 444 / 491, Acropolis 879 / 694): trees are
  closed pyramids, buildings closed boxes. Candidate holes (forward-facing steep faces with no opposite face within
  15 units, no occlusion test): Big Forest 613, Bay Bridge 315, Acropolis 561; among them the cross-members of Big
  Forest's two bridges (road points ~140-160, ~180-200) and wall strips on Bay Bridge (~125-150, ~320) and
  Acropolis (~310). Arrow boards (Big Forest ×4, Bay Bridge ×29) and Acropolis's billboard show a plain back. [V,
  offline renders only]
- **The arcade start and C.P. gantries** (`0xffb07f`, `0xffb08a/95/a0/ab`): 117 polygons, all two-sided; the red
  letters stand in front of the white banner, facing the forward driver. From behind: a blank banner in an offline
  render; what the hardware's depth sort shows was not checked. [V decode, R render]
- **The Saturn gates** baked into the converted tiles (`gates.py:15`): two-sided, layered (posts, back layer,
  banner, letter blocks). The lettered side faces the forward driver on Amazon, Diablo, Metropolis, the Oval and
  Surfers Road, and the REVERSE driver on Alpine (gates at 65, 192, 333) and Pacific Coast (186, 320): on those two
  today's driver sees the gates' backs. Whether the two courses run against the Saturn's direction or the models are
  simply made so was not settled (the Saturn disc was not loaded). [V]
- **Backdrop**: a full turn, scrolled by absolute heading (`backdrop.py:1-11`,
  `docs/spike/2026-11-phase18b-backdrop-recon.md`): the reverse driver sees the other half. [R]
- **Road paint**: flat and two-sided on the converted courses. [R]

## 5. The front end

### 5.1 Flow [V, MAME trace on p25play2]

- Top-level mode: byte `[0x501139]` (dispatcher `0xfe1c7d`, 33 entries, every 2 video frames); sub-state
  `[0x501180]`; shared timer `[0x50113c]` (one count a logic frame).

| Mode | Routine | What |
|---|---|---|
| 0x02 | `0xfe204d` | attract demo load (data index by rotation, or the operator's fixed course) |
| 0x0a | `0xfe33cc` | game start, → 0x0f |
| 0x0f | `0xfe3a5c` | select set-up: clears tile layers 0x700000 and 0x704000 (`0xfe326f`), maps bank 0, uploads the select screens' characters and palettes (`mov.w 100004, R20; bsr FE6B90`: one upload serves the course select and the transmission screen), → 0x10 |
| 0x10 | `0xfe3caa` | the select screen's state machine |
| 0x11 | `0xfe4013` | race load: bank switch `0xfe415b`, `jsr FFE007`, the loader (`0xfe48ed` → `jmp 2797EC`), → 0x12 |
| 0x12 | `0xfe4666` | grid / READY, timer 0x80 |
| 0x13, 0x14 | `0xfe46ad`, `0xfe470c` | → race |

- Mode 0x10's states (table at `0xfe3cb9`): **0** (`0xfe3cce`) gives the entity at `[0x501318]` (0x400380) bit 31
  and the handler `+0xA = 0xfc267e`, draws the static maps (`jsr FC2B7E`), timer = 0x280; **1** (`0xfe3d99`) runs
  the countdown (`0xfc3407`: timer >> 5 printed at 0x7013b8) and, below 0 with `[0x40dc8c] == 0`, goes to
  `0xfe3f01` (timer 0x40, state 6); **2-5** are linked play only; **6** (`0xfe3f82`) counts down, clears the entity's
  bit 31 and sets mode 0x11 (`0xfe3fa8`).
- The screen itself is the entity's handler. `0xfc267e`: `[0x501103] == 0` → the course select (init `0xfc268b`,
  handler `0xfc26c5`), else the transmission screen (init `0xfc2974`, handler `0xfc29b3`); the draw routine
  `0xfc2b7e` branches the same way (`0xfc2b8b` / `0xfc2cb8`).
- **There is no separate transmission screen in normal play**: on the course select START held is manual
  (`0xfc31e4`: `[0x501936] = ([0x501050] >> 4) & 1` every logic frame) and the gas confirms. The SHIFT MODE SELECTOR
  screen runs INSTEAD of the course select when the operator fixes the course (`[0x501103] != 0`, copied from
  0x40dca1 at `0xfe1b06`).
- Course-select handler `0xfc26c5`, every logic frame: wheel R10 = (`[0x501060]` + `[0x50106c]`) >> 1 (−127..127);
  `jsr 279E5C` (the project's `band`: R11 = entry 0..9); `[0x501940]` = entry; `id_store` (`0x27a7b3`):
  `[0x501934]` = template, `[0x40fc68]` = ranking id; the cursor frame (`bsr FC2880`); **lock** on a gas edge
  (`test.w 501078`) or when the timer reaches 0x20. Lock = handler `0xfc277c`: timer := 0x20, handler :=
  `0xfc27be` (the project's `start` at `0x27a323`: chosen / grey palettes and the cursor).
- **Inputs** (`0xfe6790..0xfe68a1`): wheel `[0x501060]` / previous `[0x50106c]`; gas `[0x501064]` 0..255, and
  `[0x501078]` = 0xffff for ONE logic frame when the pedal crosses half travel upward (an edge: a held pedal gives
  no second trigger); START = bit 4 of `[0x501050]`.
- There is no separate latch of the course: the handler stops running. The data loads in mode 0x11, about 200
  frames after the gas.
- Measured (coin at frame 600, gas at 1400): mode 0x10 at 617; countdown = timer >> 5, one count per 64 frames,
  20 s in all; lock at 1402 (timer := 0x20); state 6 at 1470 (timer 0x40); mode 0x11 at 1600; 0x12 at 1604; race
  at 1864.

### 5.2 The SHIFT MODE SELECTOR screen [V]

- Code `0xfc2974..0xfc2b7d` (522 bytes) and the static draw `0xfc2cb8..0xfc2de1` (298 bytes).
- Handler `0xfc29b3`: R10 = the wheel as above; `[0x501936]` = 0, or 1 when R10 > 0x1c; cursor (`bsr FC2A5D`); gas
  edge or timer ≤ 0x20 → lock (`0xfc2a1d`: timer := 0x20, handler := `0xfc2a59`, cursor only).
- Cursor `0xfc2a5d`: the course cursor's object (list `0x2e04b0`, 4 polygons, sent through the TGP) at x −128.0 or
  +128.0, y 34.0, scale (0.62, 1.0, 0.87) (the course cursor: 0.7687, 1.0, 0.8138, drawn by `0xfc2880`); it blinks
  on `[0x501144]` bit 1 while choosing and is steady when locked.
- Graphics: seven tile maps blitted once on layer 0 by `0xff9436` (R0 = map, R1 = tile address; map header
  base:u16, mode:u16, rows:u32, cols:u32); `0xff93a4` erases a map's rectangle with tile 0x20. The big words are
  pictures (maps `0x1e2271` title, `0x1e239d` AUTOMATIC, `0x1e2619` MANUAL 7 SPEED, `0x1e2895` SELECT TRANSMISSION,
  `0x1e13e1` STEP TO START!, `0x1e2205` and `0x1e1185` arrows), characters 0x3900..0x3e14 from one upload
  (src 0x1575c4 → char RAM 0x7f2000), palette = char >> 7 from the select palette block (→ 0x900c00).
- Layers on both screens: tile RAM 0x700000 = four 64×64 layers of 0x2000 bytes (pitch 0x80); layer 0 holds the
  screen's content (every cell with bit 15), layer 2 the checker background (and the Phase 7 outline overlays),
  layer 1 stale attract text that is not shown. The only 3D is the cursor frame.
- It is not a callable subroutine: the result cell, the 0x1c threshold, the two cursor positions and the seven
  map / destination pairs are immediates, and the timer and the exit to mode 0x11 belong to mode 0x10's states.

### 5.3 What the project already has

- **Text printers in the game** [V offline]: `0xff870d` (R0 = NUL-terminated string, R1 = tile address): 16×24 px
  letters, tile = (ch − 0x20) × 6 + (`[0x501438]` << 7) | `[0x50143c]`; on the select screens `[0x501438]` = 8,
  `[0x50143c]` = 0x8000: the countdown's yellow font, complete capitals (used for "COURSE IS SELECTED !" at
  `0xfc3198`). `0xff8926`: 8×16 px white. `0xffe8fb` (stack: string, tile address, attribute): 16×24 px, 0x8200
  white / 0x8300 red (the ranking titles; `ranking._print` emits this call).
- **Repo lettering**: `font.py` (5×7), `lettering.py` (6×14 white letters with an outline: the course names),
  `title.py` (repo-authored lettering written as tiles into never-loaded characters).
- **Panels and pictures**: `panel.py` (`decode_panel` / `encode_panel`, `select_uploads` / `select_palette`,
  `install_panels`, `free_chars`), `picture.py` (`quantise`, `picture_blob`, `free_runs`). The course select draws
  three picture slots (`select.py`: `SLOT_CHAR` 0x3300 / 0x3480 / 0x3600, three 128-character blocks each, rewritten
  per wheel step by the `picture` routine; `draw`, `start`).
- **Free characters**: `panel.free_chars` gives 415 on the build, but three of its five ranges lie inside the slot
  picture blocks (inferred, not checked in a dump); characters 0x3e15-0x3e7f are in no upload list. Palettes 0x60..
  0x7f are all in the select palette block.
- **Patch sites**: listed with lengths in `directory.py`, `course.py`, `select.py`, `ranking.py`; all are
  pattern-checked and nop-padded (`codepatch.patch_span`); assembler `v60asm.Block`.
- **Project RAM cells so far**: 0x502328, 0x50232c (padding after the map record), battery RAM
  0x40fc40..0x40fc6c. Free RAM beyond these was not surveyed.

## 6. Corrections from the stage 1 planning read (11 Nov, by disassembly of the original boot ROM)

- **The game HAS a wrong-way warning** (§1.1 said none was found): `0xff4c9e`, one of the 14 command-0x1800 sites,
  compares the quad's direction with the car's yaw and, within ±0x800 of opposite, draws the tile map 0x2F4D36 or
  prints "REVERSE" (string at `0xff4d0f`). It reads no `+0xeb`, which is why the search of that field's readers
  missed it. A reverse race without the half turn would show it all the time.
- **Command 0x1580** exists (three sites: `0xfebd65`, `0xfebfaa`, `0xffd4f5`, the three put-backs): it takes the quad,
  the position and the yaw. Whether its handler reads the corner order was not established.
- All 14 command-0x1800 sites share one shape (`mov.w #18000000,[R24]; mov.w <quad>,[R24]; in.w [R23],R0`, R0 read as
  a halfword) and all 7 command-0x1500 sites are one identical 59-byte sequence, each directly followed by a 0x1800
  site; all nine stores of `+0xeb` follow a 0x1800 site.
- Command 0x1500's inputs are the quad, x and z only: one position gives the same six values whichever way the car
  travels. What matters is what a quad authored for the reverse direction would return.

## 7. Not verified

1. How the six results of command 0x1500 behave when travel opposes the attribute; they feed the passing logic
   (`0xfec805..0xfecfa7`) and the spin recovery (`0xfe9571`).
2. Whether opponents are disturbed outside the put-back and spin paths (their handler `0xfea881..0xfeab30` stores
   `+0xeb` and calls the shared wall routine `0xfebdbe`).
3. The remaining absolute-pose sites of the Big Forest template (`0xfc005f`, `0xfc0ec8`, `0xff4165`) and the other
   tests of bit 0x1e (`0xfed43b`, `0xfc10af`, `0xfc123a`).
4. Whether mode 0x10 can be run a second time; known constraints: the gas trigger is an edge, and state 0 redraws
   maps without clearing layer 0 (only mode 0x0f clears layers 0 and 2).
5. Whether the game reads the free 0xff runs at 0x2fce00 or in the boot ROM.
6. No reverse view was seen in MAME: the gantries' and gates' backs, the backdrop's other half.
7. Free RAM for new cells; the meaning of `[0x40dc9b]`, `[0x501a35]`, `[0x40dc9a]`.
8. Alpine's and Pacific Coast's gate orientation (§4).
