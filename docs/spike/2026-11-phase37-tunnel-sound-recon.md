# Phase 37 recon: the arcade's tunnel sound, and the converted courses' covered stretches

Status: recon only, 16 Nov 2026. No feature code, no test, no ROM change in the tree. Base: main at 1159aab; the set driven is
`out/p34play4` (main's code at 1159aab) and the original MAME 0.289 `vr` set. Scratch (git-ignored): `out/p37/` (tools, runs,
stills in `look/`, recordings in `listen/`, experimental sets in `sets/`). The long suites were not run; no test was run at all.

**Since (16 Nov):** Pascal answered §6's questions as the coordinating session put them, with "Yes to all"; option A was built
as a prototype on branch `phase37-tunnel-sound`: `docs/spike/2026-11-phase37-tunnel-sound-findings.md` (their words, the
stretches as built, and what §7 left open that has since been measured: the pit stop under Metropolis A, a race's end, the
attract).

Marks: **[R]** read in a disassembly, **[M]** measured in headless MAME, **[I]** inferred, **[?]** not established.

## 0. The request

Pascal (they/them), 16 Nov 2026, their words, the whole request:

> also for next work i would like to add the sound effect we have in tunnel (like in bay bridge tunnel) on all the saturn level undergrand sections like metropolis tunnel...

Which sections count, and anything about how it should sound, is not decided. §6 asks.

## 1. What the arcade does in Bay Bridge's tunnel

### 1.1 In one paragraph

Each tarmac collision quad of a course has a 16-bit flag in the course bank's segment array. Bit 7 of the flag means "tunnel".
Every logic frame the player's car copies the flag of the quad it is on; when bit 7 changes, the game sends the sound board one
two-byte command: `C201` (on) or `C200` (off). The sound board's program keeps that as one bit. While the bit is set it changes
the **levels of the player's own engine voices**: the engine's usual layer is turned down and its second layer, which normally
fades away as the revs rise, is held at full level. Nothing else changes: no reverb or delay unit exists on the board, the music
and the other effects are not touched, no other car is involved, and nothing on screen or in the driving depends on the bit.

### 1.2 The V60 side

- **The flag.** Segment array entry: `(2, index, road_point, flag)`, 8 bytes, one per tarmac quad
  (`docs/formats/model1-course-tables.md` §3). The player's per-frame routine `0xfe94b3` reads the entry of its lap-position quad
  (`+0x30`) and stores the flag at `+0x152` (`0xfe94c8`); `0xfeab31` does the same for the other cars [R].
- **The decision.** `0xffa671`, called once per logic frame from the player's race handler (`0xfe8fc7`), with the player
  `[0x501320]`: bit 7 of `+0x152` against bit 7 of `+0x195` (last frame's copy). Set now and clear before: `C201`. Clear now and
  set before: `C200`. Then `+0x195` := `+0x152` [R]. It is an edge test on the quad under the car, so it does not know a direction
  of travel.
- **The send.** Through `0xffa24b`: the command is queued only while `[0x501120]` has bit 18 or bit 20 set (0x40000 on the grid,
  0x100000 in the race) [R, M]; the queue (32 words at `0x503020`) shares the sound latch `0xc40000` with the revs and tyre
  words, at most one command a frame, high byte then low byte (`0xffa2a6`, `0xffa36a`) [R, M].
- **Who else reads the flag.** The reviewer of the prototype (16 Nov) read the array's users, and this paragraph now rests on
  their reads rather than on this recon's operand search: six instructions reference the array's pointer `[0x501950]`; of
  them only `0xfe94c8` and `0xfeab46` read the flag halfword, and both store it to `+0x152`; bit 0 of `+0x152` is tested at
  `0xfe9234`, `0xfeb07f`, `0xfeb1b4`, `0xffd350`, `0xffd467`; bit 6 (the pit lane's 0x40 of flag 66) at `0xfea3d7`; mask 0x3c
  (bits 2-5) at `0xfebcbf`, the "remember this quad for the put-back" test; **bit 7 only in `0xffa671`**; there is no
  whole-value compare, and the flag is never passed to the TGP (the reviewer's). Checked here, of those: the six references
  to `[0x501950]` (`0xfe94ba`, `0xfeab38`, `0xfec6da`, `0xfec848`, `0xfecb57`, `0xffd4a1`; the last four read road points) and
  the two stores; `0xfea3d7` re-disassembled at its instruction boundary (`out/boot.lst`'s linear listing misreads it); the
  mask at `0xfebcbf` on the copy taken at `0xfebc94` [R]. This recon's own search (a byte search of the boot and program ROMs
  of both sets for the `+0x152` and `+0x195` operands: eleven and three instructions, all among the above and `0xffa671`'s
  copy at `0xffa6ab`) agrees with it but would miss an access through another register or addressing mode. So bit 7 drives the
  sound command and nothing else: no palette, light, headlight, opponent or physics use [R], and §4.2 measures it.
- **Where the data is.** Bay Bridge (bank 1): flag 0x81 on quads 69-88, road points 69-88, 20 quads, 143 units along the
  centreline. Its other flags are 1 (398 quads), 2, 4 and 16 (not looked into [?]). Big Forest: 1 and 66 (pit lane) only.
  Acropolis: 1 and 66 only [R, `out/p37/tools/flags.py`]. **So the arcade has the effect on Bay Bridge only**, on one stretch.

### 1.3 Measured on the original set [M]

Autopilot on Bay Bridge's line 0, a write tap on `0xc40000` (`out/p37/tools/sndtap.lua`, run `out/p37/runs/bb_orig`):

| frame | event |
|---|---|
| 2788 | the player's quad becomes 69 (road point 69), flag 0x81, 313 km/h |
| 2789 | `C201` at the latch |
| 2894 | quad 89, flag 1, 326 km/h |
| 2895 | `C200` |

106 frames = 1.84 s (the machine runs 57.52 frames a second). No other `C2xx` in the 110-s run. The rest of the stream is
`C0xx` (engine revs, 1 298), `B0xx` (effects and music, 144), `C1xx` (tyres, 81), `8100` (reset, 2).

- **Attract mode.** 400 s of attract on the original set (`runs/attract_orig`): the demo car crossed Bay Bridge's flagged quads in
  three demos (first at frame 1102) and no `C2xx` was sent. `[0x501120]` is 4 or 8 in the demos, so `0xffa24b` drops every race
  sound there, and `+0x195` stayed 0 [M]. The tunnel sound exists only in a player's race.
- **A race that ends in the tunnel.** With the clock run out on a flagged quad (`runs/bb_timeout`): `C201` at 2789, the race ends
  at 2794, **`8100` at 2795**; the sound program's `8100` handler clears the bit (§1.4) [M, R]. Nothing is left on for the next
  game.

### 1.4 The sound board side [R]

The sound board (MAME's Model 1 audio: a 68000, two MultiPCM chips, a YM3438). Its program (`epr-14870a.7`, disassembled in
scratch only) takes a command byte of 0x81 or more and one data byte:

- `C0xx` stores the engine revs (0-0x7f); `C1xx` the tyre state; **`C2xx` sets or clears bit 1 of a state byte** by bit 0 of the
  data; `C3xx` sets or clears bit 7 of the same byte, which nothing in the program reads; `8100` resets the driver and zeroes the
  three bytes.
- The engine is four voices of the first MultiPCM chip, started once at reset: a pair playing sample 0 (one voice panned left,
  one right) and a pair playing sample 1 (the same pans), each pair started a little apart in time. Every pass of the main loop
  sets all four voices' pitch from one table indexed by the revs, then their level:
  - **bit clear:** pair 0 at a constant level; pair 1 at the same level at low revs, fading out as the revs rise (nearly silent
    at the top);
  - **bit set:** pair 0 turned down by 38 level steps (about 14 dB), pair 1 at the chip's full level whatever the revs.
- Bit 1 is tested at those two places and nowhere else. The music, the effects (`B0xx`) and the tyre voice do not read it.
- The arcade has no engine voices for the other cars in this routine; the bit acts on the player's engine only.

### 1.5 What a player hears [M]

Two recordings of the same Bay Bridge race, frame for frame (`-wavwrite`): the original set, and a scratch copy with the 20 flags
set back to 1 (`out/p37/sets/bb_noflag`; the race logs are identical, the second has no `C2xx`). The two files are identical
sample for sample up to the tunnel, differ in it, and agree again to about -70 dB after it.

| in the tunnel (frames 2801-2889) | as the arcade | flag removed |
|---|---|---|
| level, whole mix | -16 dBFS | -20 dBFS |
| 0-100 / 100-200 / 200-400 Hz | 45 / 50 / 48 dB | 34 / 40 / 34 dB |
| 400-800 / 800-1600 Hz | 47 / 38 dB | 43 / 37 dB |
| 6.4-12.8 / 12.8-24 kHz | 22 / 17 dB | 33 / 29 dB |
| left/right correlation | 0.59 | -0.12 |

In words: the engine becomes **louder (about 4 dB), much deeper (10-14 dB more below 400 Hz), duller (about 11 dB less above
6 kHz) and more centred**: a boom, switched on at the mouth and off at the exit within a frame or two. It is not an echo of the
whole game: it is the engine's mix. The recordings are in `out/p37/listen/` (pairs 1_; its `NOTE.txt`).
[?] How close MAME's MultiPCM is to a cabinet here; what samples 0 and 1 are on their own (not listened to in isolation).

## 2. Is the trigger data-driven per course? Yes

- The field is the segment flag (§1.2). The loader copies the header's segment array pointer to `0x501950` for any course, so
  a converted course's own array is what the game reads [R, `model1-course-tables.md` §2].
- **A converted course already has the field, set to "off".** `convert/road.segment_credits` and
  `convert/reverse.reverse_segments` write `FLAG_PLAIN` (1) for every quad; main's seven courses carry flag 1 throughout
  (`FLAG_PIT` 66 is never emitted; the pit is found through the directory's pit quad) [R]. A reverse variant has its own segment
  array over the same collision quads.
- **Nothing visual or gameplay comes with bit 7** (§1.2 [R]; §4.2 [M]). Flag 0x81 keeps bit 0, which the plain road has, and
  none of bits 2-5.
- The effect itself (how it sounds) is fixed in the sound program, the same for every course.

## 3. Where the converted courses have covered stretches

### 3.1 Method

- One autopilot race per course on `out/p34play4` (line 6, 170 s), the player's x, y, z logged every frame.
- **Geometry:** every drawn face of the course's tile tables (polygon ROM, world space; 6 042-7 133 quads a course); a sample is
  "roofed" when a face lies 2 to 60 units above the car over its position or 4 units to either side
  (`out/p37/tools/roofs.py`, `roofsum.py`). Spawn-list props are not in the tile tables and were not scanned.
- **Stills:** a snapshot every 36 frames of a flying lap (contact sheets `out/p37/runs/sheet_*.png`); the Metropolis, Alpine and
  candidate sheets were looked at. The stills for the yes/no are in `out/p37/look/`, 1440x1080, named
  `<course>_p<road point>_<stretch>_<what>.png`; `arcade_baybridge_*` shows the arcade's own tunnel for comparison.
- Road points are the normal direction's. Seconds: at 300 km/h (0.25 units a second per km/h, measured on Bay Bridge), and as
  the autopilot drove it (it is slower than a player and hit things in Metropolis B).

### 3.2 The candidates

| course | stretch | road points | what the still shows | units | s at 300 | s driven | roof above car | stills (`out/p37/look/`) |
|---|---|---|---|---|---|---|---|---|
| (Bay Bridge, arcade) | the tunnel | 69-88 | rock tunnel, open on the left | 143 | 1.9 | 1.8 | | `arcade_baybridge_p061..p092` |
| Metropolis | **B** | 245-313 | the long tunnel: roof and both walls, a bend inside | 690 | 9.2 | 11.2-13.2 | 8-20 | `metropolis_p245_B_before`, `p248_B_mouth`, `p253/p277/p301_B_in`, `p309_B_exit`, `p313_B_after` |
| Metropolis | **A** | 50-62 | a roofed stretch of the main road; the pit lane runs under the same roof (pit quad 71 is at point 55) | 130 | 1.7 | 1.7-1.9 | 8-12 | `metropolis_p044_A_before`, `p050/p055_A_in`, `p060_A_end`, `p063_A_after` |
| Metropolis | C | 354-358 | under a building that spans the road, just before the start line | 50 | 0.7 | 0.5-0.8 | 11-13 | `metropolis_p350_C_before`, `p352_C_in`, `p357_C_end`, `p360_C_after` |
| Alpine | **A** | 106-145 | the mountain tunnel: roof, walls 13-19 units out | 400 | 5.3 | 6.3-7.1 | 7-8 | `alpine_p094_A_before`, `p106_A_mouth`, `p108/p122/p140_A_in`, `p145_A_exit`, `p150_A_after` |
| Metropolis | D (added after the review) | 176-178 | an underpass: the underside of a deck low over the road (the scan: a face 2.2-2.8 up over part of the width); the reviewer measured 13 units | 13 | 0.2 | 0.2 | 2-3, over a fifth of the samples | `metropolis_p174_D_underpass_before`, `p176/p178_D_underpass`, `p181_D_underpass_after` |
| Metropolis | E (added after the review) | 186-191 | an underpass under the upper deck; the reviewer measured about 44 units, close to C's 50 | 44 | 0.6 | 1.0 | 5, over a third of the samples | `metropolis_p183_E_underpass_before`, `p187/p189_E_underpass`, `p192_E_underpass_after` |
| Diablo Canyon | D | 427-440 | a bridge high over the road between canyon walls, before the start | 140 | 1.9 | 1.3 | 21-24, over half the samples | `diablocanyon_p430_D_bridge_before`, `p434/p440_D_bridge` |
| Diablo Canyon | B | 169-172 | a rock arch | 40 | 0.5 | 0.5 | 16-18 | `diablocanyon_p165_B_arch_before`, `p170_B_arch` |
| Diablo Canyon | C | 179-181 | the C.P. gate building | 30 | 0.4 | 0.1 | 10-11 | `diablocanyon_p176_C_gate` |
| Diablo Canyon | A | 140-144 | a bridge far above | 50 | 0.7 | 0.5 | 32 | `diablocanyon_p137_A_bridge_before`, `p140_A_bridge` |
| Amazon Falls | A | 209-210 | a rock arch | 20 | 0.3 | 0.3 | 22-24 | `amazonfalls_p199_A_arch_before`, `p203_A_arch` |
| Amazon Falls | B | 220-222 | a rock arch | 30 | 0.4 | 0.3 | 22-32 | `amazonfalls_p214_B_arch_before`, `p218_B_arch` |
| Pacific Coast | A | 93-96 | a road bridge over the track | 40 | 0.5 | 0.5 | 10-11 | `pacificcoast_p089_A_bridge_before`, `p096_A_bridge` |
| Pacific Coast | B | 108-110 | a road bridge over the track | 30 | 0.4 | 0.3 | 8-9 | `pacificcoast_p106_B_bridge_before`, `p108_B_bridge` |
| Surfers Road | A | 360-371 | an open footbridge, crossed at an angle | 120 | 1.6 | | 8, under half the samples | `surfersroad_p355_A_footbridge_before`, `p359_A_footbridge` |
| Surfers Oval | none | | no drawn face over the driven line anywhere | | | | | |

The point ranges are the scan's (every point with a roofed sample, gaps of two points closed); a still named "before" or by an
earlier point shows the thing ahead of the car. The exact first and last quad of a stretch is for the implementation to pin
against the drawn roof (§4.1). Only the three bold stretches are tunnels in the sense of
the arcade's (a roof and walls for longer than Bay Bridge's or about as long).

- **Metropolis D and E were not in this table when the questions went to Pascal** (the scan had found them, 174-183 and
  186-192 with a face over a minority of the samples, and this recon left them out as the autopilot's excursion; the
  reviewer of the prototype found them: two real underpasses). They were not in the list Pascal answered "Yes to all" to; the
  coordinating session put them to Pascal with a recommendation to leave both out; they answered "yes correct" (the
  findings §0 has the exchange). They are not flagged.
- Metropolis A and the pit lane: the README's "pit lane runs through a tunnel (drawn roof 8-11 units over it from the mouth,
  z 227, to about z 340)" is this roof. The lane's quads are tarmac quads with their own flags, so they can follow the road's or
  not (§6, question 4). The lane's own length under the roof was not driven in this recon [?].
- No course has its grid under a candidate: the player's first race point is Alpine 15, Amazon Falls 0, Diablo Canyon 456,
  Metropolis 364, Pacific Coast 0, Surfers Oval 0, Surfers Road 440 [M].

### 3.3 Does the Saturn version change its sound there?

**Cannot tell from the disc data read so far.** The TRCK sections decoded so far hold no per-slice attribute that marks a tunnel
(segment word 18 is 0 on every course; `docs/formats/saturn-trck.md`). The disc has a sound directory (`VRSRCDIR/SOUNDDRV`: one
bank per course, `SOUNDGLB`, and a 1 344-byte `DSPPROG0`, a program for the Saturn sound chip's effect unit), so an effect is
possible on the Saturn; whether its code switches one in tunnels was not traced (it would mean reading the Saturn program, not
the track files) [?].

## 4. Feasibility, measured on scratch sets (no feature code)

`out/p37/tools/mkset10.py` copies a set and sets bit 7 in the flags of the tarmac quads credited to given road points, in the
entry's normal segment array and, for the same quads, in its reverse variant's array. Set `out/p37/sets/exp1` = `out/p34play4`
with Alpine 106-145 (31 of 565 quads) and Metropolis 50-62, 245-313, 354-358 (79 of 527 quads).

### 4.1 The commands, both directions [M]

| run | `C201` at (point) | `C200` at (point) | per lap |
|---|---|---|---|
| Alpine normal | 106 | 146 | 1 on, 1 off |
| Alpine reverse | reverse point 309 | 352 | 1, 1 |
| Metropolis normal | 50; 245; 354 | 63; 314; 359 | 3, 3 |
| Metropolis reverse | reverse 7; 52; 303 | 12; 121; 317 | 3, 3 |
| Bay Bridge on the ten-course set (entry 1) | 69 | 89 | as the original set, same frames (2789, 2895) |

- Every edge of the flag under the car gave exactly one command, 1 to 6 frames later (the queue's pace), in 38 edges over the
  five runs; none was lost, none came without an edge.
- **Entered from the other end it works unchanged**: the test is on the quad under the car.
- Resolution: the flag is per quad. Consecutive tarmac quads of the seven courses step at most 6 road points (4 to 6 by course),
  so an end can sit up to one quad from a wished point.

### 4.2 Nothing else moves [M]

- Alpine and Metropolis, normal direction, 170 s, same autopilot: the player's per-frame race log (position, heading, road
  point, lap, clock) and the collision log are **byte-identical** with and without the flags.
- The sound command stream with the `C2xx` removed is the same list in the same order (2 024 and 2 598 commands); one command
  of Metropolis's came one frame later, behind a `C2xx` in the queue.
- So the rate is untouched: no V60 instruction is added, and each frame's work is what it was (`tests/test_frame_rate.py`'s
  rule, never below the arcade's rate, has nothing new to meet).
- The sound board: no voice is started or stopped (the four engine voices always run); two more commands per stretch per lap
  against about 16 revs commands a second.

### 4.3 How it sounds there [M]

Same race recorded on `exp1` and on `out/p34play4` (race logs identical): in Metropolis B the mix is 2.3 dB louder, 5-6 dB up
below 400 Hz, 4-6 dB down above 6.4 kHz; in Alpine's tunnel 2.2 dB louder, 4-9 dB up below 400 Hz, 4-10 dB down above 6.4 kHz
(the music is louder in these mixes than on Bay Bridge, so the same engine change shows less). Recordings: `out/p37/listen/`
pairs 2_ and 3_.

## 5. Options

Main has no symbol named `reserved_blocks`; its reservations are `colours.RESERVED_CODE` / `course.CODE_FREE` (the directory
image, 6 947 bytes against `tests/test_directory.py`'s bound of 7 000: 53 left), `tencourse.annex_regions()` and the banks' free
runs. Option A needs none of them.

| | option | code bytes in the ROM | table bytes | sound board | rate | risks |
|---|---|---|---|---|---|---|
| **A** | **Data only: the arcade's own flag.** The converter writes 0x81 instead of 1 for the tarmac quads of the stretches Pascal names (a per-course list in `CoursePlan`, like `lane_points`), in the normal array and for the same quads in the reverse array. | 0 | 0 (the flag halfwords exist) | unchanged program; 2 commands per stretch per lap | unchanged (§4.2) | the lists are road points: a renumbering (`flag_start`) would move them, so a test ties each stretch to the drawn roof; ends accurate to one quad; a grid under a flagged quad is untested (§7) |
| A' | As A, but the stretches found by rule (a quad is flagged when a drawn face lies over it for a run longer than N units) instead of a list. | 0 | 0 | as A | unchanged | arches, bridges and gates qualify by geometry; what counts is Pascal's call, which a list states and a rule guesses |
| B | A different or stronger effect (other levels, another layer, the music too): a patch to the sound program `epr-14870a.7`. | 0 in the V60 ROMs; a patch in the sound ROM | 0 | changed program | unchanged | the tool reads and writes no sound ROM today (`romset.py`: one of the 13 files it never reads); the change would also alter Bay Bridge's arcade sound unless a new command were added; the board has no echo or reverb unit, so "an echo" would have to be built from voices; nothing of this is measured |
| C | A V60 hook (a region test or a new command) | new routine; the directory image has 53 bytes under its bound | maybe a table | as A or B | a per-frame cost to measure | no reason found for it: the flag already does this per quad |
| 0 | Leave as is. | | | | | |

**Recommended: A**, with the stretches from §6. It is the arcade's mechanism used as the arcade uses it, it changes no code and
no table size, and §4 shows it working in both directions on two courses.

Size of the work for A: a `tunnels` field on `CoursePlan`, the flag in `segment_credits` / `reverse_segments` (or one pass over
the finished arrays by quad), a sound-latch log helper for the tests (the scratch `sndtap.lua` is the model), the tests below,
the docs (`model1-course-tables.md` §3: bit 7; `deviations.md`: the stretches).

Tests that would pin it:

1. Converter (no MAME): every flag of a converted course is 1 or 0x81; 0x81 exactly on the quads of the listed stretches; the
   reverse array flags the same quad indices; no other bit is ever set.
2. Each listed stretch lies under drawn faces of the built set (a share of its points), so a renumbered course fails loudly.
3. MAME, a standing test per course with stretches, normal and reverse: the latch log shows `C201` within a few frames of
   entering each stretch and `C200` after leaving it, strictly alternating, none anywhere else in the lap.
4. The same runs' command streams with `C2xx` removed equal the streams of the same set built without the list, and the race
   logs are identical (what §4.2 measured by hand).
5. The three originals: their segment arrays byte-identical to the source set's; Bay Bridge on the built set sends `C201` at
   quad 69 and `C200` at quad 89 and nothing else; Big Forest and Acropolis send no `C2xx`; the attract sends none.
6. A race that ends inside a stretch is followed by `8100` (the arcade's own reset, §1.3), so the next game starts dry.

The 3.5-hour suite once at the end of the batch, as the project's rule has it.

## 6. Questions for Pascal

Each with what I would do and what it means. The stills are in `out/p37/look/`, the recordings in `out/p37/listen/`.

1. **Is the arcade's effect, exactly as it is on Bay Bridge, what you want?** It is the engine getting louder, deeper and
   duller between the mouth and the exit; the music and the other cars do not change. Listen to `listen/1_...` (Bay Bridge with
   and without) and `listen/2_...`, `3_...` (Metropolis's long tunnel and Alpine's with it, and as they are today).
   *Recommended: yes, the arcade's own.* Consequence: no code changes and Bay Bridge stays the reference; anything else
   (stronger, an echo, the music too) means changing the sound board's program, which this project has never touched.
2. **Which stretches? Say yes or no to each** (stills named in §3.2):
   - Metropolis B, the long tunnel (points 245-313, about 9 s): *recommended yes.*
   - Alpine A, the mountain tunnel (106-145, about 5 s): *recommended yes.*
   - Metropolis A, the roofed stretch by the pit lane (50-62, about 1.7 s, the length of Bay Bridge's): *recommended yes.*
   - Metropolis C, under the building before the start line (354-358, about 0.7 s): *recommended no.* Consequence of yes: a
     half-second blip of the effect once a lap.
   - Diablo Canyon D, under the high bridge before the start (427-440, about 1.9 s): *recommended no* (the bridge is 21 units
     up and covers half the width; it is not a tunnel), but it is the longest of the rest: your call.
   - The arches, bridges and gates: Diablo Canyon A, B, C; Amazon Falls A, B; Pacific Coast A, B; Surfers Road A (0.3 to
     1.6 s each): *recommended no.* Consequence of yes: short blips; the arcade does not do it under its own bridges.
   - Surfers Oval: nothing to decide, nothing is over the road.
3. **Did I miss one?** If you know a covered place that is not in the list (I scanned the driven line for drawn faces overhead
   and looked at Metropolis's and Alpine's laps and the other candidates), name the course and roughly where.
4. **Metropolis's pit lane** runs under roof A. *Recommended: the lane sounds like the road beside it* (its quads flagged while
   under the roof). Consequence: the effect stays on while you drive into the box under the roof; during the stop itself the
   engine idles.
5. **Reverse races:** the same stretches, entered from the other end. *Recommended: yes, always the same places* (measured
   working). Consequence of no: a tunnel that booms one way and not the other.
6. **The three arcade courses stay exactly as they are** (Bay Bridge's one tunnel; none on Big Forest or Acropolis).
   *Recommended: yes.*

## 7. Not established

- What the Saturn game does to its sound in these places (§3.3).
- A start or a restart on a flagged quad: `0xffa24b` drops a command while the race bits of `[0x501120]` are clear, and
  `0xffa671` still updates `+0x195`, so an "on" at a moment the gate is shut would be lost until the next entry [I, from the
  code]. No candidate is under a grid (§3.2), and the put-back keeps the race bits; not measured.
- The pit stop under Metropolis A: the pit sequence replaces the player's handler, so the bit should hold from the entry to the
  release and be corrected on the first frame after [I]; not driven.
- Linked play; the service menu; real hardware against MAME's MultiPCM.
- Bay Bridge's flags 2, 4 and 16, and command `C3xx` (stored by the sound program, read by nothing found).
- Spawn-list props overhead (not in the tile tables); the contact sheets of the laps' other parts were not all looked at; the
  scan found nothing there.

## 8. Reproduce (scratch, `out/p37/tools/`)

- `flags.py <set>/vr.zip`: the three originals' flags by quad and road point.
- `drive.py <set dir> <workdir> --orig 1 | --entry N [--reverse] [--line 6] [--attract]`: one headless run with `sndtap.lua`
  (`S` lines: bytes to `0xc40000` with the PC; `F` lines: mode, `[0x501120]`, road point, quad, `+0x152`, `+0x195`, x, z, speed,
  y); `sndparse.py`, `c2.py` read it.
- `mkset.py` / `mkset10.py`: the experimental sets; `wavcmp.py`: two recordings compared; `roofs.py`, `roofsum.py`: the roof
  scan; `sheets.py`, `look.py`: the contact sheets and stills.
- Environment: `source out/env.sh`, `PYTHONPATH` = the worktree, `VR_MAME_JOBS=2`.
