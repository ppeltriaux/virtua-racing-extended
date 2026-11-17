# Phase 33 recon: Big Forest, Bay Bridge and Acropolis in reverse (15 Nov 2026)

Pascal, 15 Nov: "We also need to do the reverse for the three initial tracks". Recon only: nothing is built in the tree.
Read on main (2a9f1ab) and measured on main's built set `out/p28play2` and the original set `out/roms/vr.zip`.

**[V]** = verified here by a decode or a MAME run; **[R]** = read in the repo's code or docs; **[?]** = not established.
Scratch (git-ignored, not in the repository): `out/p33/` (§12). The prototype of §2 is a throwaway script that patches a
copy of main's set; no ROM byte and no game data is in this commit.

## 0. Answer in brief

- **Feasible, and much nearer than the Phase 26 design assumed.** A reverse variant of each original, generated from the
  arcade's own decoded tables and installed through the existing `ReverseRecord` path, **raced in MAME today with no new
  V60 code**: the COURSE DIRECTION screen came up for the original, the grid formed behind the line, laps counted,
  checkpoints fired, all 15 opponents raced, none parked (§2) [V]. Every mechanism the seven needed (the collision's
  half turn, the grid start on the Big Forest template, the start figures, the direction screen) is keyed on the flag
  or on the entry's reverse record, not on "converted" [R, V].
- **No Saturn data is needed.** The one Saturn-fed step of the seven's reverse (`reverse.reverse_pit`) has an arcade
  equivalent in the originals' own pit-lane flag (segments flagged 66) (§1, §6.1).
- **The scenery from behind is a small problem, not a big one.** One-sided: 99.98-100 % of the tile polygons [V]. But
  a ray cast of the driver's view finds a face met from behind first on **0.09-0.12 % of the view over a reverse lap**
  (forward: 0.03-0.15 %), at worst 2-3 % of one view (Acropolis points 34-40 and 73-78); 52 / 66 / 85 distinct faces
  (Big Forest / Bay Bridge / Acropolis) are seen from behind in reverse and never forward (§4) [V, offline]. 150
  snapshots of the three reverse races show no hole [V]. Backing those faces costs about 16-25 KB of polygon ROM and
  no change to the normal course (§4.3).
- **The real obstacles:**
  1. **Bay Bridge's bank.** Its variant must lie in data bank 1, which has **13 488 bytes free**; eight reversed lines
     need **60 048**, three 25 968, two 19 152, **one 12 336** [V]. Today only a one-line Bay Bridge reverse fits (all
     15 opponents on the centreline; it raced, §2). Big Forest (53 152 of 487 540 free in bank 3) and Acropolis (84 496
     of 279 100 in bank 2) fit with all eight hand-made lines.
  2. **Best times.** The battery RAM has **78 bytes free**; three more 4-entry reverse tables need 300 [R, calc]. And as
     the code stands a reverse race on an original would be written into the original's NORMAL table (the setter moves
     only ids 3..9) [R]: this must be closed in the first stage whatever is decided.
  3. **What reads backwards.** The START and C.P. banners are blank white from behind [V snapshots]. START has a
     both-sides copy already (free to reuse); the four C.P. gantry lists are 32 animated frames of 132 records each
     (168 960 bytes a list): copies as START's do not fit (about 880 KB against 396 KB usable), lettering-only objects
     might (140-205 KB, estimate) [V sizes, ? method]. Arrow boards (Big Forest 4, Bay Bridge 10) point the wrong way.
- **Route recommended: A**, the originals' reverse generated from their own arcade tables (§7). Route B (convert the
  Saturn disc's versions) does not fit the ROMs on three counts (§7).
- **Not done here:** no human drive; no reverse pit stop was run; the opponents' quality was measured only by the
  autopilot harness (Big Forest: 19 off-tarmac jolts in 150 s against 1 forward).

## 1. Where the seven's reverse comes from, and what of it applies to an original

The reverse of a converted course (design `docs/superpowers/specs/2026-11-11-reverse-courses-design.md` §6.3-6.8) is
**not** a second conversion. It is the normal course's built tables read backwards plus a flag [R]:

| Piece | Built by | Input | Usable on an original as is? |
|---|---|---|---|
| Collision (quads, cell map, surface) | shared with the normal course; `dirattr` adds half a turn to every quad direction read (14 sites of TGP 0x1800) while `DIRECTION_RAM` 0x502294 is 1 | none | **Yes**: flag-keyed, already in the ROM. **0 TGP words** (7 631 free [V]) |
| Road lines, segment array, header, pointer block (the "variant blob", in the entry's own data bank) | `reverse.reverse_tables`, `blob.build_variant_blob`, `tencourse.install_reverse` | arcade-format `RoadTables` + the tarmac quads | The blob builder yes; `reverse_tables` **no** (it copies the centreline's heading and link words to all eight lines and re-walks the segment credits the converter's way): an arcade-native version is 20 lines (§3) |
| Checkpoints | `reverse.reverse_checkpoints` | numbers | Yes [V §2] |
| Time records, car table (race blob, 1 808 bytes, program ROM annex) | `tencourse.race_blob_for` | the template's boot-ROM tables | Yes [V §2] |
| Load record + maps record (64 + 64 bytes, annex), the word in the reverse table | `directory.ReverseRecord`, `install_directory` | the entry | Yes: `ORIGINALS` are ordinary directory entries (race 0, header 0x100000) [R, V] |
| Grid start on the Big Forest template (no crew start in reverse) | `startbit` | flag | Yes (built for Alpine; Big Forest reverse started on the grid, §2) [V] |
| Start figures turned round the car (Acropolis template) | `figures`, `figmirror` | flag | Yes (seen on reverse Acropolis, §2) [V snapshot] |
| Pit quad + box of the variant | `reverse.reverse_pit` | **Saturn** (`SaturnCourse`: lane polyline and lane polygons) | **No**; the originals mark their lane themselves (flag 66), §6.1 |
| Crew turned about the box | `crewturn` | flag + the served box | Yes [R]; not run here |
| HUD map side | `map_tx` / `map_cross` of the variant's record | the lap's sense | Yes [R] |
| Gate lettering both sides | converted tiles (`gates.py`) | **Saturn** gates | n/a: the originals' gates are entities (§5.2) |
| START gantry both sides | `gantry.py`: a copy of the arcade's 32 frames with mirrored letters, in the ROM | arcade | Yes: a variant's spawn list can name the copy (§5.2) |
| COURSE DIRECTION screen | `dirlock`: shown when the entry's word in the reverse table is not 0 | the table | **Yes, automatically** [V §2] |
| Best-time table | `ranking.py`: ids 10..16 = entry + 7, **entries 3..9 only** | battery RAM | **No** (§6.6) |
| HUD name | `hudname`: prints the name when the served record has a race blob | record | Works, but a reverse original then shows its name where its normal race shows BEGINNER / MEDIUM / EXPERT (§6.5) [V] |

So of the reverse pipeline only two steps take Saturn data (the pit chooser and the gates' lettering), and neither is
needed in that form. The Saturn disc's own Big Forest, Bay Bridge and Acropolis (`TRCKBIGF`, `TRCKBAYB`, `TRCKACRO`,
`docs/formats/saturn-trck.md`) are not needed for route A.

## 2. The prototype: the three originals raced in reverse from their own tables [V]

`out/p33/proto.py` (scratch): on a copy of `out/p28play2/vr.zip`, per original: the eight lines reversed and the
segment credits renumbered (§3), `build_variant_blob` placed first-fit in the course's own bank, a race blob with the
reversed checkpoints and the normal lap's time total, a load and a maps record in the erased run at 0x2bcb10, and the
entry's word in the reverse table. **No routine, no site and no existing byte other than that one table word was
changed.** No pit (pit quad none), the normal spawn list, tile table and HUD-map values. Then the repo's own harness
(`autoplay.lua`, the autopilot on the centreline read backwards, 150 s, `race_log.lua`, `fieldtrace.lua`, RAM dumps).

| Run | Variant | Player | Extensions | Opponents moved / parked | Steps back over the line | Leader, points in 150 s | Opponent jolts |
|---|---|---|---|---|---|---|---|
| Big Forest reverse | 8 lines, bank 3 at 0x169ad0 | 2 laps counted | 6 | 15 / 0 | 0 | 842 | 19 |
| Big Forest normal (control, same set) | | 2 laps | 6 | 15 / 0 | 0 | 877 | 1 |
| Acropolis reverse | 8 lines, bank 2 at 0x1a4be0 | 1 lap + 382 points | 4 | 15 / 0 | 0 | 1 225 | 3 |
| Acropolis normal | | 1 lap + 372 | 4 | 15 / 0 | 0 | 1 219 | 4 |
| Bay Bridge reverse | **1 line** (all eight pairs name line 0), bank 1 at 0x1fcb50 | 1 lap + 393 | 5 | 15 / 0 | 0 | 1 143 | 14 |
| Bay Bridge normal | | 0 laps, stopped at point 226, clock out at frame 7 350 (the known baseline of this driver) | 2 | 15 / 0 | 0 | 858 | 11 |

- Every wrap of every car counted a lap (0 wraps without a lap); the opponents' line cursor led their road point by
  at most 6 points (Bay Bridge one-line: 14); reversed checkpoints (0, 108, 218), (0, 197, 306), (0, 169, 382).
- The player's yaw was within 0x2000 of the quad direction the game stored (`+0xeb`) on 6 552 of 6 764 frames (Big
  Forest), 6 666 of 6 764 (Acropolis), 6 338 of 6 764 (Bay Bridge): the half turn applies to the originals' quads.
- **The COURSE DIRECTION screen appeared for all three** with the course's own picture twice, the clockwise arrow on
  NORMAL and the anticlockwise on REVERSE, and the harness answered REVERSE on it (snapshot 0 of each run).
- Big Forest reverse started on the grid with the READY lights at frame 1 866 (its normal race, the crew start, at
  1 928); Acropolis's start figures stood round the car.
- **The draw budget and the rate** (`frame_rate.lua`, the race clock held, the same 150 s):

  | Run | Highest need (records) | Lists skipped | Overrun counter | Worst V60 busy time |
  |---|---|---|---|---|
  | Big Forest reverse / normal | 9 851 / 9 137 | 0 / 0 | 0 / 0 | 12 784 / 14 604 us |
  | Acropolis reverse / normal | 7 495 / 8 339 | 0 / 0 | 0 / 0 | 13 569 / 13 502 us |
  | Bay Bridge reverse / normal | 7 997 / 6 922 | 0 / 0 | 0 / 0 | 14 571 / 13 491 us |

  Budget 10 500, two vblanks 34 770 us. Big Forest reverse leaves 649 records under the budget on this line (the
  standing test's worst forward frame is 9 771 on line 4): anything added to its reverse view counts against that.
- **Snapshots** (50 a race, every 130 frames, contact sheets `out/p33/sheet2_*.png`): no see-through scenery noticed on
  any of the three; Big Forest's bridges, grandstands and Ferris wheel, Bay Bridge's tunnel and suspension bridge,
  Acropolis's cliffs all drawn. Seen: the START banner and a C.P. banner blank white from behind (Acropolis at the
  line and at forward point 423, Bay Bridge at forward 112); the HUD reads BIG FOREST / ACROPOLIS / BAY BRIDGE where
  the normal race reads the level word; the HUD map, unshifted, lies further towards the screen's middle than in the
  normal race; on Bay Bridge the autopilot left the road at the same beach bend on both laps and was put back.
- What the prototype would do wrong if shipped: a finished reverse race would be inserted in the original's normal
  best-time table (§6.6) [R]; the check that an original never shows the screen (design §8) would fail by design.

## 3. The originals' road tables [V, decoded from the ROM]

| | Big Forest | Bay Bridge | Acropolis |
|---|---|---|---|
| Bank / template / TGP slot | 3 / 2 / 2 | 1 / 0 / 0 | 2 / 1 / 1 |
| Road points, segments | 338, 1 093 | 418, 674 | 592, 946 |
| Segment flags | 1: 1 059; 66: 34 | 1: 398; 16: 123; 4: 68; 2: 65; 129: 20 | 1: 914; 66: 32 |
| Segments a point | 1 on 201 points, 2 on 34, **8 on 103** | 1 on 253, 2 on 74, 3 on 91 | 1 on 514, 2 on 32, **8 on 46** |
| Lines whose heading word equals the centreline's | 0-23 of 338 points a line | 0-18 of 418 | 0-1 of 592 |
| Lines whose link word equals the centreline's | 146-151 of 338 | 77-95 of 418 | 233-247 of 592 |
| Line 6 | 338 points | **416 points** | 592 |
| Variant blob, eight lines | 53 152 bytes | 60 048 | 84 496 |

What differs from a converted course, and what it means for the reversal:

- **Each of the eight lines is its own hand-made racing line** with its own heading, pitch, roll and link at every
  point (lateral distance from the centreline up to 11-16 units). `reverse.reverse_tables` writes the centreline's
  words on all eight lines, so it cannot be used. Per line: points in the order (n − j) mod n, the heading's high half
  turned half a turn and unwrapped (the reversed ranges stay inside 16 bits on all 24 lines), the pitch and roll
  halves negated, wrap points by `bank.encode_line` (it takes each line's own net turn).
- **A quad is credited the point it is centred on**, not the point its front has reached: the centre of a flag-1 quad
  lies at −0.26..+0.19 of a point spacing from its credited point (5th-95th percentile; median −0.01 or −0.02) on all
  three courses. So the reverse credit is a renumbering, **(n − p) mod n**, with no geometry: quad k stays segment k,
  flags kept. The converter's reverse walk (`reverse.reverse_segments`) gives the same value on 1 071 of 1 093 (Big
  Forest) and 923 of 946 (Acropolis) segments but only 369 of 674 on Bay Bridge (its side areas), so it is not the tool.
- **Every line point's link names a segment credited that very point** (all 8 × n points, all three courses). With the
  renumbering, the reversed point j (forward n − j) keeps its link's segment, whose reverse credit is j: the cursor
  rule of formats §15 holds point for point with nothing recomputed.
- **Lane groups** (eight quads abreast sharing one road point: Big Forest forward points 79-118 and 231-293,
  Acropolis 350-395; Bay Bridge three abreast on 91 points; formats §16) keep one shared credit under the renumbering,
  so the game's group test still finds them. The converted courses have no lane groups: this path of the passing code
  had never run in reverse before §2. Nothing stalled or parked there in §2; which side a car moves to when it
  changes lane in reverse was not looked at [?].
- **Segment flags are not directional** [R, boot listing]: bit 0 (`0xfe9234`, `0xfeb07f`, `0xfeb1b4`, `0xffd350`,
  `0xffd467`) = "on the racing road" (clear on the pit lane and on Bay Bridge's 2 / 4 / 16 areas, which lie up to
  −159..+382 units from the centreline); bits 2-5 (`0xfebcbc`, mask 0x3c) = "not a put-back spot"; bit 7 (`0xffa67b`)
  = the tunnel's sound (Bay Bridge points 69-88, command 0xc201). No other reader of the flag word `+0x152` exists.
- **Bay Bridge's line 6 has 416 points**, two short. Reversed by index it needs points 416 and 417: two points to be
  made up (the prototype repeated the last one; with one stored line it was not exercised) [?].
- **Quad directions**: within 22.5° of the centreline's heading on all flag-1 quads with a non-zero attribute but 4
  (Acropolis); a zero attribute is the +z heading of the start straights, not "none".

## 4. The scenery seen from behind

### 4.1 What is one-sided [V]

| | Big Forest | Bay Bridge | Acropolis |
|---|---|---|---|
| Tile cells used, records, bytes | 76, 25 188, 1 007 520 | 68, 17 688, 707 520 | 79, 25 220, 1 008 800 |
| Quads, one-sided (flag bit 14 clear) | 20 366, 20 362 (99.98 %) | 15 641, 15 641 | 21 923, 21 923 |

The face a record is drawn from is its first three corners' right-hand normal (formats `model1-polygon-rom.md`):
horizontal faces face up on 8 235 / 8 752 / 10 784 records against 581 / 124 / 179 [V], which fixes the sense used below.

### 4.2 How much of a reverse driver's view is missing [V, offline ray cast]

`out/p33/scene.py`, `cast2.py`: a camera at every centreline point, 2 units above the road, looking along travel
(±35° wide, −12°..+18° high, 64 × 28 rays), against every tile quad within 320 units; a ray is "missing" when the
nearest face it meets is one-sided and seen from behind (the game does not draw it). The same cast looking forward is
the arcade's own baseline.

| | Big Forest | Bay Bridge | Acropolis |
|---|---|---|---|
| Missing, forward (share of the rays that meet scenery) | 0.147 % | 0.029 % | 0.042 % |
| Missing, **reverse** | **0.090 %** | **0.115 %** | **0.107 %** |
| ... of which nothing at all is drawn behind (sky) | 36 of 310 rays | 448 of 544 | 401 of 767 |
| Cameras with more than 1 % of the view missing, reverse (forward) | 1 (1) of 330 | 8 (2) of 418 | 16 (3) of 590 |
| Worst reverse views | all under 1 % but point 279 (35 %; forward 67 %: see below) | 1.8 % at 384; 1.0-1.6 % at 381-388, 163-165, 121 | 3.2 % at 76 (73-78: 1.3-3.2 %); 2.3 % at 37 (34-40); 1.2 % at 116 |
| Distinct faces met from behind within 150 units: forward / reverse / **reverse only** | 194 / 101 / **52** in 13 cells | 46 / 66 / **66** in 16 cells | 59 / 98 / **85** in 19 cells |
| Where the reverse-only faces are (forward road points) | 280-289 (18), 0-9 (10), 260-269 (5), 320-339 (8) | 340-359 (22: seven sloped faces 15 units out, 17 up, near 351-357), 160-179 (16), 100-119 (9) | 20-29 (17), 360-369 (8), 100-109 and 140-149 (6 each), 590-591 (6), 440-449 (5) |

- Cameras dropped as artefacts (most of the view from behind in BOTH directions: the camera's height came from a
  quad of another level): Big Forest points 280-287, Acropolis 374-375; point 279 and Acropolis 373 / 384 sit beside
  them and read high forward too.
- The Phase 26 recon's 613 / 315 / 561 "candidate holes" had no occlusion test; with one, most are the far sides of
  closed hills, trees and boxes that something nearer covers.
- Limits of this measure: tile-table scenery only (not the spawn-list props of §5, not the large objects drawn by
  entity code, formats §6); one camera a point on the centreline; a 64 × 28 grid misses thin faces, so the face counts
  are lower bounds; no check against a MAME picture beyond the 150 snapshots of §2.

### 4.3 The options

| Option | Records | ROM | Normal course | Note |
|---|---|---|---|---|
| Accept | 0 | 0 | unchanged | about 0.1 % of the view; Acropolis's two worst stretches 2-3 % |
| Set bit 14 on the faces in place | 0 | 0 | **polygon ROM bytes change**; the faces are then drawn from behind in the normal race too | against the byte-identical rule |
| A copy of each changed cell's object with bit 14 set | 0 more | a whole cell object each: the 13-19 cells are a large share of 0.7-1.0 MB a course; 396 012 bytes usable | unchanged | does not fit in general |
| **Reverse-only "backs"**: the variant gets its own tile table (the load record's `tile_table`, already per record); a changed cell's list is the arcade's object followed by a small object holding the faces wound the other way (`0xff84a2` walks triples until a zero, formats §7) | about 2 a face: 100-170 a course over the lap, a handful in any one view | polygon ROM about 16 KB for the 203 faces (40 bytes a record), say 25-75 KB with the thin faces the cast missed; program ROM 3 × 1 024 (tables) + 48 × 28 (lists) = 4 416 bytes | **unchanged, byte for byte** | recommended if Pascal wants them; the colour words can be existing entries; a tile record with two triples has not been tried on a tile table [?] (the gantry lists use it) |

The converted courses avoided the question: every polygon they draw is two-sided (`encode_object(no_cull=True)`).

## 5. Spawn-list entities [V decode]

### 5.1 Inventory

| | Entities, list bytes | What |
|---|---|---|
| Big Forest | 32, 1 796 | 4 arrow boards (`0xffaa67`, forward points 36-45); 4 of `0xffd093` (35-44); the fairground group at point 305 (the wheel `0xffd60c` 398 quads, `0xffd8ef`, `0xffd746` two-sided, three `0xffabaa`, `0xffda84`); three 25-unit poles (301-312); 9 `0xffc17e` grid objects (points 336-27); START gantry at 0; C.P. gantries at 120 and 230 |
| Bay Bridge | 107, 3 596 | 10 arrow boards (125-159); 21 `0xffdbea` and 21 `0xffdf4c` (types 101-121, sharing one object list); 33 of `0xffcbfc` / `0xffcbf1` (types 3-35: points 172-181, 217-224, 252-255, 361-366); 7 `0xffacc6`; 5 `0xffc25d`; poles; `0xffb735`, `0xffb619` at 206; START at 0; C.P. at 112 and 221 |
| Acropolis | 14, 1 364 | 7 `0xffc17e` grid objects (1-20); `0xffb54f` at 300 (190 quads); `0xffbb9c` at 371; `0xffbf47` at 154; START at 591; C.P. at 210 and 423 |

Every simple prop object decoded is wholly one-sided (the arrow board: 16 quads, 4.3 × 10.8 units). What each
handler other than the gantries, the minimap and the boards draws was not identified here [?].

### 5.2 What reads wrong from behind

- **START gantry**: blank white from behind [V snapshots]. The both-sides copy made for Alpine, Diablo Canyon and
  Pacific Coast (`gantry.py`, the list at the top of the code area) is in the ROM; a variant's **own spawn list** can
  name it and the normal list stays untouched. Cost: the list's bytes (below), 0 polygon bytes.
- **C.P. gantries**: four lists (`0xfdc0b3` and `0xfdc1b3`: Big Forest and Bay Bridge; `0xfdc133` and `0xfdc233`:
  Acropolis), each 32 distinct frames of 132 two-sided records = 168 960 bytes [V]. Blank white from behind [V].
  Copies with mirrored letters as START's would be about 220 KB a list, 880 KB for four: no room. A second triple a
  frame holding only the mirrored letters (the frame record ends at a zero word, so a frame can be two objects) would
  be about 4 × 32 × 28-40 records × 40 bytes = 140-205 KB [estimate; the letter quads were not counted, and whether a
  separate object sorts behind the banner as the copy's records do is not known ?].
- **Arrow boards** (Big Forest 4, Bay Bridge 10): one-sided, and they announce the forward bend. In reverse they are
  met from behind, after the bend. A variant's own spawn list can leave them out or carry turned ones.
- **A variant's own spawn list** costs its bytes in the program or boot ROM: 1 796 + 3 596 + 1 364 = 6 756 bytes for
  the three (less without the props dropped). The loader takes `spawn_table` from the served record [R]; a variant
  whose list differs from its entry's has not been tried (the seven's variants share theirs) [?].

## 6. Item by item

### 6.1 Pit stops (Big Forest, Acropolis; Bay Bridge has none) [V decode, R]

| | Big Forest | Acropolis |
|---|---|---|
| Normal pit quad (table `0xfe8e0c`) | 30 | 28 |
| Lane quads (flag 66) | 30-59 (forward points 0-29) and the mouth 1085-1088 (points 334-337); one quad the lane's full width each, lateral −21..−35 | 28-55 (points 0-27) and 938-941 (588-591); lateral −19..−23 |
| Box (`0xff40d9`, `0xff40b1`) | (−230.38, 30.00, −269.57), beside point 13 | (−346.42, 3.70, −58.96), beside points 16-17 |
| Lane heading | +z (0.04°) | +z (359.9°) |
| A reverse pair by stage 4's rules (adjacent lane quads at the normal exit, not the box, 64 units or more of straight run to it) | 58, 59 (run 147-157 units) | 54, 55 (run 76-84) |

- The reverse car meets the normal exit before the line, as on the seven: the variant's record carries pit quad 58
  (54) and the same box with the heading turned half a turn (0x8000). `pitbox`, `pitaim`, `pitpark`, `pitstops` and
  `crewturn` all read the served record [R]. An original's normal race has no box in its record (the game's own code
  runs); only the variant would use the project's pit routines. **Not run here** [?].
- New code: a pair chooser from the flag-66 quads (the Saturn-fed `reverse_pit` is not usable); about the size of a
  test.

### 6.2 Start [V §2, R]

- Bay Bridge and Acropolis templates: the grid comes from the car table on the reversed lines; started in §2.
- Big Forest template: `startbit` withholds the crew start while the flag is 1, so reverse Big Forest starts on the
  grid as reverse Alpine does [V]. Pascal's stage 2 decision for Alpine ("no pit crew start in reverse") would apply.
- The grid objects (`0xffc17e`, 9 on Big Forest, 7 on Acropolis) stand where the normal grid is, which is behind the
  reverse grid; what they show from there was not looked at [?].

### 6.3 Checkpoints and time [V §2]

Reverse checkpoints (0, 108, 218), (0, 197, 306), (0, 169, 382): the normal gates renumbered; none falls within
`GATE_START_GAP` (50) of the reverse start. The time records are the template's with the sectors in the new order and
the normal lap's total (`race_blob_for(lap_totals=)`): 6 / 4 / 5 extensions fired in 150 s.

### 6.4 Opponents [V §2, ?]

All eight hand-made lines reverse cleanly (Big Forest, Acropolis). Measured only under the autopilot: none parked,
no step back, leader within 4 % of the normal race on Big Forest and equal on Acropolis. Open: Big Forest's 19 jolts
against 1; the grid (the seven needed a changed grid on bank 1 and changed line pairs on Metropolis after Pascal's
drives); lane changes in the eight-lane stretches; the pushes that use the forward-authored edge values (a known
limit of every reverse race, stage 1 findings §4).

### 6.5 HUD [V §2, R]

- **Label**: `hudname` prints the name when the served record has a race blob, and a variant must have one (its
  checkpoints). Keeping the level word in reverse needs one more test in `hudname` (the menu entry below 3). Phase 32
  (`phase32-hud-reverse`, in flight) works on the HUD in reverse by its name; its tree was not read.
- **Map**: the originals are clockwise (149.0 / 0); reversed, the interior lies on the left and the seven's rule gives
  237.0 / 22 (`MAP_TX_SHIFTED`, `MAP_CROSS_SHIFTED`). The prototype kept 149.0 / 0. How the originals' own outline
  objects sit with the shift was not looked at [?].

### 6.6 Best times [R, calc]

- Battery RAM free after Phase 27: `0x40fc6d..0x40fc6f` (3 bytes) and `0x40fdb5..0x40fdff` (75) = **78 bytes**
  (formats §21; not re-measured here).
- Three more reverse tables as the seven's (4 entries × 24 bytes, a slot word each): **300 bytes**. Does not fit. One
  entry each (72 + 12) does not fit either.
- **Ten reverse tables of 3 entries**: 720 + 40 slot words + tag 4 + cells 5 = **769 of the 787 bytes** of the two
  free runs Phase 27 started from. Fits, at the price of the seven's fourth best time and a new tag (the reverse
  block is re-initialised once). By the status lines of the design and the follow-ups, Phase 27 is on main but in no
  public release (v0.2 is Phase 26) [R], so only a battery RAM written by a main build since 15 Nov would lose reverse
  times.
- Or no table: a reverse race on an original records nothing (a gate, as stage 3's `rankgate` was, 40 bytes).
- Either way the setter must change: today it adds 7 to ids 3..9 only, so an original's reverse race would be inserted
  in its normal 24-entry table. `reverse_ids`, `reverse_defaults`, `attract_groups` and the title (`revtitle`: the
  originals' titles are the game's BEGINNER / MEDIUM / EXPERT routines) are written for entries 3..9.

### 6.7 The direction screen, the attract mode, linked play [V, R]

- **Screen**: gated on the entry's word in the reverse table alone (`dirlock`); it showed for all three in §2 with no
  change. Its arrows take the lap's sense from the normal record's `map_cross` (0 = clockwise: right for all three).
- **Attract**: the two attract loads and the two linked loads call `bankdemo`, which clears the flag before the
  lookup, entry 0's menu-path load in mode 6 included (`directory.py:94-100`) [R]. The attract demo and the ranking
  pages therefore stay normal. Not run here after a reverse race on an original [?].
- **Linked play**: `dirlock` installs the game's own handler when `[0x40dc8c]` is not 0; the fallback path of `entry`
  never reads the flag [R]. Untouched by route A.

### 6.8 Room [V on `out/p28play2` unless marked]

| Region | Free now | Route A needs | Fits? |
|---|---|---|---|
| Data bank 3 (Big Forest, Alpine) | 487 540 (353 584 at +0x69ad0, 133 956 at +0xdf4bc) | 53 152 | yes |
| Data bank 2 (Acropolis, Diablo, Metropolis) | 279 100 (111 648 at +0xa4be0, 167 452 at +0xd71e4) | 84 496 | yes |
| **Data bank 1** (Bay Bridge + four converted) | **13 488**, one run at +0xfcb50 | 60 048 (8 lines); 5 520 + 6 816 a stored line | **one line only** (12 336, leaving 1 152; `tests/test_tencourse.py` `BANK_ONE_FLOOR` is 13 000; `blob.MIN_FREE_RUN` 0x8000 hides the run from `place_blob`) |
| Data bank 0 | 9 688 | 0 | - |
| Program ROM, the annex's run (after the select pictures at 0x2b90b0, before the direction screen's block at 0x2be8b0) | 22 528 in all; 7 600 erased now at 0x2bcb00 | ten variants in one annex: 20 528 + 32 margin; or three more beside the seven: 7 424 + 32 | yes, with 1 968 or 144 bytes to spare; the run's start moves if the colour words or the pictures before it grow |
| Program ROM elsewhere | 12 800 at 0x2fce00 and 1 623 at 0x2df9a9 (no allocator, not shown unread); 1 952 at 0x28f1d0; 1 356 at 0x2b9280 | variant spawn lists up to 6 756; tile tables and lists 4 416 | only in the unvetted run or the boot ROM |
| Boot ROM | 14 267 at 0xfdc845, 3 792 at 0xfff120, 512 at 0xfe700c | (spawn lists may be boot addresses, `directory.py`) | room exists; not shown unread |
| Polygon ROM | 461 548 (floor `POLY_FLOOR_BYTES` 65 536: 396 012 usable) | backs 16-75 KB; C.P. lettering 140-205 KB if built | yes for the backs; the lettering takes up to half; Phases 29 and 31 (in flight) also draw on it [? their size] |
| TGP data | 7 631 words | 0 | - |
| Battery RAM | 78 bytes | 300 (or a re-layout, §6.6) | no as is |
| Directory image (`end − loader`) | 6 895 of the test bound 6 900 | a setter change, a `hudname` test, a pit chooser is build-time only | the bound is a test constant; Phase 32 grows the same image |

A normal race reads none of this: a variant is reached only through the reverse table with the flag set.

## 7. Routes

### A. Each original's reverse generated from its own arcade tables (recommended)

- **Reused**: everything of §1 marked Yes; the harness and the per-course reverse tests (parametrised by entry).
- **New**: `reverse_original` (§3: per-line reversal, renumbered credits, kept flags and links); a pit pair chooser
  from flag 66; `ORIGINALS` entries with a `ReverseRecord` in `ten_course_set` and the annex sized for ten; the
  ranking setter's case for ids 0..2 (gate or tables); `hudname`'s choice; optionally variant spawn lists, tile tables
  with backs, C.P. lettering; tests (`BANK_ONE_FLOOR`, the check that an original never shows the screen, the reverse
  build tests' and `ranking.py`'s entries 3..9).
- **Biggest risk**: not the mechanics (they ran) but the quality bar on things only a drive shows: the field's
  behaviour on the hand-made lines run backwards (grid, lane stretches, Big Forest's jolts), and Bay Bridge's one line.
- **Size**: stage 1, the three reverse races behind the screen with the best-time question closed and the HUD as
  decided (Bay Bridge on one line), then Pascal's drive; stage 2, pit stops on Big Forest and Acropolis, the START
  gantry's copy, the arrow boards, the map side; stage 3, the scenery backs and the C.P. lettering if wanted; a
  separate stage for Bay Bridge's lines if one line is refused (below). Each smaller than the matching stage of
  Phase 26: no code routine is new.

**Bay Bridge's lines**, the options with their numbers:

| Option | Lines | Cost | Risk |
|---|---|---|---|
| One stored line in bank 1 | 1 (the centreline for all 16 cars) | 12 336 of 13 488 bytes; the bank's test floor lowered | raced in §2: 0 parked, leader 1 143 points; a single-file field |
| Its reverse tables in bank 3 with a relocated copy of what a race reads from bank 1 | 8 | 60 048 + collision map 32 768 + surface 256 + the graphics directory and its blocks (the original bank's whole content is 226 533 bytes; phase 0 alone uploads 13 blocks from 0x11e531..0x135671); bank 3 has 353 584 − 53 152 in its larger run | `directory._check` forbids a variant in another bank; the graphics directory's phases 1-3 are not decoded by `course.gfx_uploads`; whether the Bay Bridge template reads the window at fixed addresses is not known [?]; one stage of its own |
| Take stored lines back from the four converted bank-1 variants (three each today) | up to 4 | 0 bytes; their reverse fields change | they were driven and accepted by Pascal as they are |
| Re-lay bank 1 or store its backdrops coarser | 8 | - | ruled out by Pascal in Phase 26 (design §6.4) |

### B. Convert the Saturn disc's Big Forest, Bay Bridge and Acropolis for reverse only

Does not fit [V numbers]: a converted course's collision is 19 760-32 960 TGP words against **7 631 free**; the seven
conversions took 3 388 472 bytes of polygon ROM (484 KB each on average) against **461 548 free**; a tile table is
5 120 bytes of a code area that has runs of at most 1 952 left; and ten menu entries are wired in, so the three would
have to be variants whose collision, tile table and scenery all differ from their entry's (today a variant shares its
entry's TGP slot by rule). It would also give a reverse race on a different road, with other walls and other scenery
than the normal one; how different was not measured here (`docs/spike/2026-11-big-forest-comparison.md` has the
Phase 3 comparison). Not recommended.

### C. A mix

Route A for Big Forest and Acropolis now, Bay Bridge after a decision on its lines. This is route A with its stages
ordered by what is certain; it is the recommendation's first step, not a different route.

## 8. The constraints that stand, against route A

- **Normal originals and Grand Prix byte-identical and unchanged**: the variant only adds bytes in erased runs and one
  word of the reverse table; the originals' banks, tile tables, spawn lists, polygon and TGP data are not written
  (the scenery option recommended in §4.3 and the spawn-list option of §5.2 are chosen for that). The control races of
  §2 on the patched set matched the known baselines (Big Forest 15 moved, 877 points, 6 extensions). Which flag is
  "Grand Prix" and whether the direction screen can appear in it was not traced here [?]: the screen's own tests are
  linked play `[0x40dc8c]` and the operator's fixed course, as for the seven.
- **Frame rate**: §2's table; 0 overruns, 0 lists skipped, busy time under 14.6 ms of 34.8 on the three reverse
  races. `tests/test_frame_rate.py` gains three races; Big Forest reverse has 649 records of margin on the centreline.
- **Walls**: route A changes no collision byte.
- **No ROM or game data in the repo**: the variants are generated at build time from the user's ROM, as the seven's.

## 9. Decisions that are Pascal's

1. **Bay Bridge in reverse with all 15 opponents on one line, or wait for a stage that gives it eight?** Recommended:
   build it on one line in stage 1 so it can be driven, and decide on the bank-3 stage after that drive.
2. **Best times for the three originals in reverse: none, or three best times a course on all ten reverse tables (the
   seven lose their fourth)?** Recommended: three on all ten, decided before the next public release (the 4-entry
   layout has not been released).
3. **The C.P. banners are blank from behind on the originals. Letter them as on the seven (up to 205 KB of the 396 KB
   of polygon ROM left), or accept?** Recommended: the START banner both-sided at once (it costs no polygon ROM), the
   C.P. banners as a later stage once Phases 29 and 31 have taken their polygon ROM.
4. **The arrow boards (Big Forest 4, Bay Bridge 10) point the wrong way in reverse: leave them out of the reverse
   race, or leave them standing with a plain back?** Recommended: leave them out.
5. **The HUD's bottom-right label in reverse: BEGINNER / MEDIUM / EXPERT as in the normal race, or the course's name
   as on the seven?** Recommended: the same word as the normal race.
6. **Pit stops in reverse on Big Forest and Acropolis by the seven's scheme (in by the normal exit, the same box, the
   crew turned round the car)?** Recommended: yes, in stage 2.
7. **The scenery faces seen from behind (about 0.1 % of the view; Acropolis 2-3 % at two stretches): back them
   (16-75 KB of polygon ROM, reverse only), or accept?** Recommended: judge at the first drive; back them if any shows.
8. **Big Forest in reverse starts on the grid, not with the pit crew (as reverse Alpine).** Recommended: yes.

## 10. Candidate first steps

1. **Cheapest prototype to show Pascal: all three, as §2 built them**, made properly: `reverse_original` in
   `vrtools/convert/reverse.py` with unit tests on the decoded originals (credits (n − p) mod n; every reversed line
   point's link credited its own index; flags kept; lane groups keep one credit), the three `ReverseRecord`s in
   `ten_course_set`, the annex for ten, a gate on the best-time insert for ids 0..2. Big Forest and Acropolis with
   eight lines, Bay Bridge with one. That is a set he can drive: three reverse races behind the existing screen.
2. The reverse race tests of `tests/test_reverse_build.py` and three reverse races in `tests/test_frame_rate.py`
   extended to entries 0-2 (they are parametrised by entry; the originals have no `Converted`, so the drive line is
   the ROM's line 0).
3. Read up before stage 2: the grid objects `0xffc17e` from the reverse side, the lane-change side in the eight-lane
   stretches (`fieldtrace.lua` on Big Forest forward points 231-293), a reverse pit stop on both courses with the
   pairs of §6.1, and the HUD map with 237.0 / 22.
4. For Bay Bridge's eight lines, if wanted: a read tap on the bank window over a Bay Bridge race (which addresses are
   read, from which PCs) and a decode of the graphics directory's other phases, before any design.

## 11. Not established

1. No human drive of any reverse original; every race measure of §2 is the autopilot's (it cannot overtake, and on Bay
   Bridge it leaves the road at one beach bend each reverse lap and does not complete a normal lap at all).
2. The opponents' quality in reverse: Big Forest's 19 jolts against 1; the reverse grid (turned cars, start
   collisions); lane changes and pushes in the eight-lane stretches; a whole five-lap race.
3. No reverse pit stop was run; the pairs and boxes of §6.1 are read from the tables.
4. The scenery measure is offline and tile-table only (§4.2's limits); the props' and the grid objects' look from
   behind; a tile record of two triples; a variant with its own spawn list.
5. The C.P. lettering's real cost and whether a letters-only object sorts correctly.
6. The frame's need on other lines, in the pit lane and with anything added to the reverse view; real hardware.
7. Bay Bridge in another bank: the graphics directory's phases 1-3, fixed-address reads of the bank window.
8. Bay Bridge's line 6 (416 points) reversed.
9. The battery RAM's free runs were taken from the Phase 27 record, not re-measured.
10. What Phases 29, 31 and 32 (in flight) take of the polygon ROM, the colour run (it moves the annex's start) and
    the directory image.
11. Which flag is Grand Prix and the direction screen's behaviour in it; the attract cycle after a reverse race on an
    original; the service-mode ROM test.
12. The HUD map with the shifted values on the originals' own outline objects.
13. Whether the unvetted erased runs (0x2fce00, the boot ROM's) are read by the game.

## 12. Scratch files (`out/p33/`, not in the repository)

| File | What |
|---|---|
| `dec1.py`, `dec2.py` | the originals' lines, segments, flags, credits and links (§3) |
| `room.py`, `bank1.py` | free runs, budgets, the directory as built, the banks' original content (§6.8) |
| `scene.py`, `cast.py`, `cast2.py` | the tile scenery and the ray cast (§4) |
| `spawn.py`, `gan.py`, `pit.py` | spawn lists, gantry lists, pit lanes (§5, §6.1) |
| `proto.py`, `proto2.py`, `runs.sh`, `runs2.sh`, `*.log`, `run/<label>/` | the prototype sets, the six races, the six rate runs, their logs and snapshots (§2) |
| `sheet2_*.png` | contact sheets of the reverse races |
