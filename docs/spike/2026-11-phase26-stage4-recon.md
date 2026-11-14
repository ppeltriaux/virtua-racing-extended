# Reverse courses, stage 4: recon for pit stops in reverse (13 Nov 2026)

What a pit stop in a reverse race needs (design §3, "Pit stops in reverse", Pascal: "we will need pit stop working, add it to a
later stage"; confirmed as the next stage on 13 Nov), measured on the set `out/p26play5` (the build of main 1216442) in MAME 0.289,
headless, and read from the original boot ROM's listing (`out/p26/stage2/t13/boot.lst`) and the project's code. Nothing was built
and nothing in `vrtools/` or `tests/` changed: the prototype pokes the variant's records into the program ROM region from Lua.
Scripts, logs and snapshots are git-ignored under `out/p26/stage4/recon/` (`runs/<label>/`; `run.py` calls
`vrtools.mame.run_mame` with `autoplay.lua`; `batch.py` runs several courses; `pitlog.lua` logs the player and the crew and applies
the ROM pokes; `inventory.py` → `inventory.txt`, `paircheck.py`, `quadsat.py`, `lanewalls.py`, `room.py` read the built set;
`lanegeo.py` places each Saturn course as the build does and keeps its pit-lane polyline; `paths.py` / `paths2.py` write the
autopilot paths). Tags: **[M]** measured (run named), **[R]** read (listing address or file:line), **[I]** inferred.
Design = `docs/superpowers/specs/2026-11-11-reverse-courses-design.md`; stage 2 recon = `docs/spike/2026-11-phase26-stage2-recon.md`.

Timing: a video frame is 1/57.52 s; the game logic steps once every two video frames. Frames below are video frames from boot; in
these runs the course loads (mode 0x11) at frame 1600 and the green (mode 0x14) is at 1864, normal Alpine's crew start at 1926
[M `s1_*`].

Driving: `autoplay.lua` answers the COURSE DIRECTION screen (`VR_DIRECTION=1` for REVERSE) and `autopilot.lua` steers along a CSV.
The runs use a copy of the Lua directory (`out/p26/stage4/recon/lua/`, `VR_LUA_DIR`) whose `autopilot.lua` takes its search window
ahead from `VR_AUTOPILOT_AHEAD` (the product's is fixed at 40 points; 40 for the normal runs, 15 for the reverse runs). Normal paths
splice the pit-lane polyline into line 6 (`paths.py`); reverse paths are the normal pit runs' own driven trajectories read
backwards, joined by line 6 read backwards (`paths2.py`). MAME writes one extra snapshot when a run ends: the last file of each
`snap/vr/` is not one of the requested frames [M].

## 1. A pit stop today, in the normal direction

### 1.1 The chain

| step | where | what |
|---|---|---|
| stops granted | `pitstops` (0xfe8bd8 site, `directory.py:646-668`) [R] | at the race start `+0x1bf` := 0 for an entry whose load record has no pit quad (0xfffe), else 2 (5 in linked play; none when `[0x40d826]` ≥ 2). Reverse variants carry 0xfffe today, so a reverse race has 0 stops (`tencourse.py:687`, `directory.py:189-190`) [R] |
| what forces it | the player handler 0xfe8e18, 0xfe8e88..0xfe8ec5 [R] | every logic frame: if `+0x1bf` ≠ 0 and the lap-position quad `+0x150` equals the entry's pit quad (from `pit`, which reads the served record's +0x10) or that + 1, and −0x4000 < `+0x36` − `+0xeb` < 0x4000 (the heading within 90° of the quad's direction), `jsr 0xff222f`. Nothing is offered: any pass over the pair with a stop left is a stop (Phase 22i's "forced pit stops") [R + M] |
| the direction it tests | 0xfe8f97 (`mov.w #18000000`, a `dirattr` site) [R] | `+0xeb` is stored from TGP command 0x1800 through `dirattr` (`direction.py` ATTR_SITES), which adds 0x8000 while the direction flag is set. The heading test reads last frame's `+0xeb` [R] |
| entering | 0xff222f [R] | `dec.b +0x1bf`; the work by the damage flags `+0x1ab`: `& 0xF` = 0 → state 1, `& 3` = 0 → state 11, `& 0xC` = 0 → state 8, else state 14; bit 0x1e of 0x501d14 when damaged; handler := 0xff2345 (state table 0xff2161, 17 entries: 0xff2509, 0xff250a, ... 0xff2793 [R, read from the ROM]) |
| autopilot | 0xff2345 → 0xfe968d (single cab), aim at `pitaim` (0xfe96a4 site) [R] | turns `+0x6a` by at most 0x200 a frame towards an aim point 10 units short of the box along its heading, then the box; speed by distance (formats §12) [R] |
| stop | 0xfe98c7 → `pitpark` [R] | the car at the box's x, z; yaw `+0x6a` := the box heading (maps record +16: x, y, z floats, heading u16, 1); flag 7 of `+0` [R + M] |
| crew | states 1/8/11/14 call 0xff27d8 / 0xff2d69 / 0xff33c7 / 0xff3a1b (`bsr FF4061` → `pitboxcrew`), sound 0xb003 [R] | five pool objects of `[0x501350]` (six in work state 14 [M `metro_rev_p1`]) at fixed world-axis offsets from the box, for work state 1: (+2.57, +1.39) heading 0x4000, (−2.82, +1.39) 0xc000, (−2.29, −1.47) 0xc000, (+2.79, −1.48) 0x4000, (+0.02, +3.48) 0x8000 [M `s1_3_*`, `s1_4_*`, `s1_8_*`: the same offsets on Alpine, Amazon and the Oval in both directions]. They are spawned at the trigger, not when the car arrives [M `crew_4_reverse`: frame 5096 for a trigger at 5094] |
| work | state 2 waits for flag 7, then 0xff2b51; state 3 waits for crew object 0's bit 0x1e [R] | release − park = 444 frames on every course, both directions [M all `s1_*`] |
| release | state 4, 0xff254f..0xff25c5 [R] | sound 0xb050 (single play), `0xfea42f`: `inc.b +0x57`, EXTEND display 0xA0, clock `+= [0xfcd5b5]` (384 = 12 s); print at tile 0x700b2a; handler := 0xfe8e18, state 0, `+0x131` := 0, `[0x501160]` := 0, `+0x1c0` := 0xfc18, `+0x1c2` := 1.0 [R]. The car stands at the box; the player drives it out [M] |
| clock | | frozen from the trigger to the release (Metropolis reverse: 1050 from 5198 to 5886), then +384 [M `metro_rev_p3`] |
| HUD | 0xff245d [R] | PIT WORK blinks while `+0x191` ≠ 0; EXTEND TIME after the release [M snapshots]. The HUD map's outline carries the pit lane (Phase 22g) |
| opponents | | the check is in the player's handler only [R]; during a reverse stop on Metropolis all 15 opponents advanced 62-91 road points (5200 → 5900) [M `field_6_reverse`] |

**A side effect in both directions [M + R].** `0xfea42f` increments the checkpoint counter `+0x57`, which indexes the time
records' extensions, so after a stop every checkpoint adds the next sector's extension. Normal Metropolis (`s1_6_normal`): pit at
frame 3122 (cps 0 → 1, +384), then checkpoint 126 added 255 (sector 2's) where 336 was due. Reverse Metropolis (`metro_rev_p3`):
the line added 380 where 336 was due, then checkpoint 143 added 255 where 381 was due. The arcade's own records were uniform, so it
did not show there. Not a reverse matter; noted for the owner (§8 D7).

### 1.2 Per course (normal direction)

Lane polylines from `lanegeo.py`; quads, records and credits from `inventory.py` on `out/p26play5`; "depth" is along the lane
from the forward mouth. Side as `place.PIT_LANES` names it (to the driver going the normal way).

| course | points | lane: mouth → exit (fwd points), side | length | box (x, z), heading | box depth / from exit | normal pair, depth | `PitLane` specials |
|---|---|---|---|---|---|---|---|
| Alpine | 452 | 184 → 209, right | 254 | (295.1, 605.3), 0x400f (90°) | 138 / 116 | 233 + duplicate, 44 | none; the Big Forest template's PIT START (normal only; reverse starts on the grid, design §6.7) |
| Amazon Falls | 330 | 316 → 22 (crosses the line), right | 362 | (−172.7, 52.0), 0x031c (4°) | 183 / 179 | 498 + duplicate, 42 | named pit-exit wall at points (20, 37) (Phase 22s); entry in shared tarmac (follow-ups) |
| Diablo Canyon | 457 | 446 → 29 (crosses), right, 87 out at mid-lane | 327 | (−346.0, −101.0), 0x0b96 (16°) | 128 / 198 | 784 + duplicate, 70 | start_slice 110, entry_slice 72, depth 130, spawn_depth 40, turn 0.55 (the course placed round its lane) |
| Metropolis | 365 | 50 → 63, right | 117 | (−89.6, 310.4), 0xfff9 (0°) | 82 / 35 | 71 + duplicate, 35 | depth 82 (box in the tunnel, Phase 22t); median walls at 50-61 (Phase 22p) |
| Pacific Coast | 410 | 160 → 210, right | 497 | (−483.6, −620.0), 0xb12b (−111°) | 247 / 251 | 195 + duplicate, 47 | none |
| Surfers Oval | 387 | 351 → 26 (crosses), left | 630 | (−240.4, −56.7), 0x00ce (1°) | 307 / 323 | 703 + 704 (side by side), 135 | entry in shared tarmac (follow-ups) |
| Surfers Road | 441 | 415 → 20 (crosses), left | 484 | (−241.1, −34.3), 0x007b (1°) | 241 / 243 | 862 + duplicate, 118 | entry_separate |

[M `inventory.txt`; R `place.py:103-125`]. Every lane quad's attribute is the nearest race-line point's direction
(`collision._RouteDirections`, `collision.py:265-286`) [R]: against the lane's own direction, median 0-7° and at most 13-17° on
Alpine, Metropolis, Pacific Coast and the Oval; Amazon at most 40°; Surfers Road at most 67° (2 of 65 quads over 45°); Diablo median
30°, at most 51° (30 of 90 over 45°), its lane running at an angle to the road [M `inventory.txt`].

Measured normal stops (one 150-s race each, `s1_<entry>_normal`; Metropolis `s1_6_normal`) [M]:

| course | trigger frame, quad, speed | trigger → box (units) | park | release | work state |
|---|---|---|---|---|---|
| Alpine | 3596, 234, 305 | 104 | 3900 | 4344 | 1 |
| Amazon Falls | 4452, 499, 328 | 145 | 4804 | 5248 | 1 |
| Diablo Canyon | 6160, 785, 293 | 62 | 6380 | 6824 | 14 |
| Metropolis | 2420, 72, 179 | 64 | 2678 | 3122 | 11 |
| Pacific Coast | 3792, 196, 296 | 203 | 4216 | 4660 | 1 |
| Surfers Oval | 5308, 703, 262 | 182 | 5710 | 6154 | 1 |
| Surfers Road | 6948, 863, 235 | 139 | 7302 | 7746 | 1 |

The crew stands where a car facing +z would have it [M]: on Amazon, Metropolis, the Oval and Surfers Road (boxes within 4° of +z) it
is round the car as in the arcade; on Alpine (90°), Pacific Coast (−111°) and Diablo (16°) it is turned about the car by the box
heading (the open follow-up "the crew stands turned about the car") [M snapshots `sheet_3_alpine.png`, `sheet_7_pacific.png`].

## 2. What depends on the direction of travel

| item | normal | in a reverse race today | what reverse needs | measured |
|---|---|---|---|---|
| stops granted | 2 | 0 (variant pit quad 0xfffe) | a pit quad in the variant's load record | with one poked, `+0x1bf` = 2 at the start [M all reverse runs] |
| where the car enters | the forward mouth | it meets the forward exit first | a pair (q, q + 1) at the forward exit, in the lane | §3 |
| the pair rule | `+0x150` = q or q + 1 | | q + 1 must be in the lane too. The converter made the normal pair by duplicating or moving a quad in the SHARED list (`pit_entry_pair`, `collision.py:1645-1681`) | on all seven courses two lane quads already sit at adjacent list indices near the forward exit (`inventory.txt`, "reverse-entry pair candidates"): no list change is needed [M]. Stage 2 recon §4 expected a change to the shared collision here |
| heading test | `+0xeb` = forward attribute | `+0xeb` = attribute + 0x8000 (`dirattr`) | nothing: a car driving up the lane backwards heads within 90° of the turned attribute | yaw − attribute at the reverse trigger 2-30° on the seven [M `s1_*_reverse`] |
| autopilot aim | 10 short along h, from the mouth side | | the box heading h + 0x8000 in the variant's maps record | §3 |
| park yaw | h | | h + 0x8000 (same field) | the car parks facing the reverse way [M] |
| box | mid-lane | | the same box on six courses; on Metropolis the run from the exit to the box is too short (§3) | §3 |
| lane credits | lane quads are tarmac with segment credits | the variant's segment array credits them too (`reverse_tables` turns every tarmac quad) | nothing | the reverse credits rise from the exit to the mouth on all seven; Amazon, Diablo, the Oval and Surfers Road's lanes cross the line (the lap counts in the lane) [M `inventory.txt`; laps counted, §3] |
| checkpoints in the lane | Alpine 192, Pacific 186 lie in their lanes | reverse 260 (Alpine) and 224 (Pacific) lie in them | nothing | they fired in the lane; a checkpoint or line crossed under the pit autopilot is paid after the release (Pacific 5154, the Oval 6124, Surfers Road 7370) [M] |
| wrong-way read, put-back, steering assist in the lane | forward attribute | turned attribute | nothing | no read of the wrong-way warning (`2f4d36-2f4d39`, `ff4d10-ff4d15`) in the reverse Metropolis race with its stop [M `metro_rev_p3`]; put-back and assist in the lane not driven [I: they use the same turned attribute] |
| crew | world-axis offsets for a +z car | the same offsets [M]: turned half a turn about the car | a turn of the placement and of the animation's world-axis motion (as stage 2's grid girls) | §4 |
| pit-out | the forward exit | the forward mouth, past the normal pair | nothing | driven out on all seven, no second stop: the variant's quad is not the normal pair [M]; Metropolis's mouth (the fence nose at point 50) passed [M `metro_rev_p3`] |
| HUD map | the outline with the lane strip | the same object (`install_reverse` keeps `map_obj`, `tencourse.py:687`) [R] | nothing | the lane strip is on the reverse map [M snapshots] |
| clock, EXTEND, `+0x57` | §1.1 | | nothing | the same in reverse [M] |

## 3. The prototype (Lua pokes on `out/p26play5`, no product change)

**Pokes** (`pitlog.lua`, `VR_ROM_POKE`, written into the `:maincpu` region at frame 1; read back the same [M]): the variant's load
record +0x10 := q (u16); its maps record +16 := the normal box's x, y, z with heading h + 0x8000 and 1. Variant records: Alpine
0x2b90c0, Amazon 0x2b9100, Diablo 0x2b9140, Metropolis 0x2b9180, Pacific 0x2b91c0, the Oval 0x2b9200, Surfers Road 0x2b9240; maps
record = load + 1 804 [M `room.py`, build report]. Nothing else: `pit`, `pitstops`, `pitbox`, `pitboxcrew`, `pitaim` and `pitpark`
read the served record through `entry` [R `directory.py:458-668`]. Only variant records are written, which no normal race reads [R
`entry`, `directory.py:312-348`].

**Metropolis first** (the design's course). `metro_rev_p1` (q = 86, the normal box z 310.4 with h 0x7ff9): PIT WORK at 5198 (quad
86, 272 km/h, state 14), the autopilot took the car, and it never parked: the trigger lies 26 units from the box (the lane's exit
is 35 from it), the car passed the box at 113 km/h and circled it at 40-60 km/h, radius about 9 units, until the run ended at 6903
(state 15 waiting for the park flag) [M]. This is the orbit Phase 22i saw on Alpine before `pitaim` (formats §12). `metro_rev_p2` /
`metro_rev_p3`: the same pair with the box moved to (−89.61, −8.87, 270.0) (the normal pair's quad, 40 units deeper towards the
forward mouth, still under the tunnel roof, which runs from the mouth to about z 340 [R `tests/test_convert_collision.py:2435`; M
snapshot `sheet_metro_reverse_p3.png`]): trigger 5198, park 5444 at the box facing 0x7ff9, release 5888 (+384, cps 2 → 3), pit-out
through the forward mouth, lap 1 at 6452 [M]. The first version of the path cut across the lane's side wall at (−96.4, 256) (`metro_rev_p2s`, wall
quad 1313): a path fault, gone with the later paths (`metro_rev_p3`, `s1_6_reverse`) [M].

**All seven** (`s1_<entry>_reverse`, one 150-s race each; the same results in `b2_*` / `b3_5_reverse`) [M]:

| course | q (q + 1) | where it fired (from the exit) | speed | trigger → box | park | release | after |
|---|---|---|---|---|---|---|---|
| Alpine | 250 (251) | 251, 13 units | 279 | 122 | 4906 | 5350 | checkpoint 260 in the lane at 5478 |
| Amazon Falls | 32 (33) | 32, 60 | 333 | 122 | 5418 | 5862 | lap at 6016; a second stop started at 8526 (log end) |
| Diablo Canyon | 40 (41) | 41, about 70 | 322 | 132 | 6432 | 6876 | lap at 6990 |
| Metropolis (box moved) | 86 (87) | 86, about 12 | 272 | 68 | 5444 | 5888 | lap at 6488 |
| Pacific Coast | 247 (248) | 248, 63 | 317 | 203 | 4708 | 5152 | checkpoint 224 paid at 5154 |
| Surfers Oval | 31 (32) | 31, 57 | 289 | 271 | 5678 | 6122 | lap counted under the autopilot (5426), line paid at 6124 |
| Surfers Road | 20 (21) | 20, 37 | 208 | 210 | 6924 | 7368 | lap under the autopilot (6722), line paid at 7370 |

Every stop: the car parked at the box facing h + 0x8000, release − park = 444, the clock frozen then +384, stops 2 → 1 [M]. The
trigger → park time is 246-502 frames. Plain reverse races on line 6 with the same pokes (`line_<entry>_reverse`, each past its
forward exit at least once): no stop fired on any course [M], and no road line passes through any chosen pair (least distance from
line 0 or 6: 9.9 Metropolis, 11.8 Alpine, 10.7-38.8 the others) [M `paircheck.py`].

**What went wrong on the way, and why** [M]:

1. **Metropolis's box is too near the forward exit** for the reverse run (above). Measured: 26 units circles, 64-68 parks (normal
   Metropolis parks from 64). The minimum between was not searched.
2. **Alpine, first pair 242 (243)** (`b1_3_reverse`): a normal stop at 4594-5274, then a second at once (5276-5722): quad 242 holds
   the box, so the parked car stood on the pit quad with a stop left. A reverse pair must not hold the box (`paircheck.py`: 242/243
   holds it; the normal pairs and the seven chosen pairs do not).
3. **Diablo Canyon: an invisible wall in the lane** (`b2_5_reverse` frame 6080; `diablo_wall`, snapshots
   `sheet_5_diablo_lanewall.png`): driving up the lane centre at 322 km/h the car hit wall quad 1689 at (−389.7, 41.4), lane point
   about 23, and was thrown out onto the sand. The quad's footprint (−388.9..−408.7, z 31.7..42.8) covers the lane's west half up
   to its centre line; the drawn tarmac continues there and no rock is drawn [M `quadsat.py`, snapshot 6082]. The normal pit-out
   (`b1_5_normal`) passed about 1 unit east of its corner, accelerating from the box. With the path moved 6 units east there the
   reverse stop worked (`b3_5_reverse`, `s1_5_reverse`). It is shared collision: it concerns both directions.
4. **Path faults, not the game's**: the product autopilot's 40-point window jumped from Diablo's lane to the road loop beside it
   (`b1_5_reverse`: the car never drove the lane); Surfers Road's spliced lane path lifted the gas at the junction (`b1_9_reverse`,
   208 km/h at the trigger) and ran into the wall at the forward mouth after the release; both gone with the trajectory paths and
   a 15-point window. Wall hits 450-500 frames after a release on Alpine (road 295) and Surfers Road (road 43) are the autopilot's
   usual hits on those courses, far from the lanes.

**The crew, placement only, from Lua** (`crewturn.lua`, `crew_4_reverse`, Amazon Falls): each crew object turned once, at its
spawn, by the car's park heading (0x831c) about the box. The five stood ahead of and round the car as in a normal stop; the
animation's root offsets (+0x17b, +0x193, world axes, up to 1.5 units during the work) were not turned, and one tyre carrier
stood a little off the car [M `sheet_4_amazon_crewturn.png`, `crew.txt`]. Stage 2 met the same drift on the grid girls (findings
§11.3.2) and mirrored the root offsets, the two horizontal rotations and the walk heading (`figmirror`).

## 4. Scenery from the other side

Two-row sheets, normal over reverse, at the trigger − 80, trigger, park − 60, park + 150, park + 350, release + 40 and + 140:
`out/p26/stage4/recon/sheet_<entry>_<course>.png` (3 alpine ... 9 surfersroad) [M].

| course | seen driving the lane in reverse | blocker? |
|---|---|---|
| all seven | the garages and pit wall on the other side of the screen; no PIT lettering, arrows or one-sided boards in the lanes were seen | no |
| Alpine, Amazon Falls | a gate's START lettering in view beyond the lane, reading correctly (stage 2's two-sided lettering) | no |
| Amazon Falls, Metropolis, Surfers Oval, Surfers Road | the crew half-turned: the figure placed 3.48 units ahead of a +z car stands between the camera and the car through the whole work and hides a third of the screen; the wheel and wing work is done at the car's rear | cosmetic, very visible (`cmp_metro_crew.png`) |
| Alpine, Pacific Coast, Diablo Canyon | the crew turned by h + 180° (270°, 69°, 196°) instead of the normal h (90°, 249°, 16°): turned about the car in both directions | cosmetic |
| Metropolis | the fence posts at the forward mouth (yellow) close on both sides at the pit-out | no |
| Diablo Canyon | the lane wall of §3 item 3: nothing drawn, a crash | yes for a player on the lane's west half at point ≈ 23 (both directions) |

**Correction (14 Nov 2026, after Task 1):** "nothing drawn" is wrong for the wall quad's south end, which stands on a drawn rock (about 23 % of its footprint): found by Task 1, see `docs/spike/2026-11-phase26-stage4-findings.md` §2.1 and §4.

## 5. Room

[M `room.py` on `out/p26play5`; R `tencourse.py`, `directory.py`]

| region | numbers |
|---|---|
| directory image | 0x278d70..0x27af1d, 8 621 bytes; `end − loader` = 5 797 against `tests/test_directory.py:161`'s `< 6000` (203 left): a "routines stay small" test bound, not hardware |
| after the image | tile tables from 0x27af20, race blobs, spawn lists to 0x289dac, all placed from `directory_layout()["end"]`: growing the image by N moves them by N rounded to 16, and the select pictures first-fit after them [R `tencourse.py:226-274`] |
| code area free | erased runs past the image: 3 056 at 0x28ed80 (below the start-gantry block 0x28f970, 1 024 bytes, top-anchored), six spawn-slot tails of 720 / 744, 98 at 0x28fd0e; 7 546 in all. The image can grow by about 3 000 bytes before the pictures meet the gantry block [I: first-fit not simulated] |
| variant records | the pit quad (+0x10, u16), a pad halfword after it (+0x12, written 0, `directory.py:271`; no reader known [I]), the box (maps record +16..+31, zeros today): a reverse stop needs no new record bytes |
| reverse annex | 0x2b90c0..0x2bcb00 (internal gap 1 356 at 0x2b9280); 7 600 erased at 0x2bcb00..0x2be8b0 (the direction screen's block from 0x2be8b0) |
| other erased runs | program 0x2fce00 (12 800), 0x2df9a9 (1 623); boot 0xfdc845 (14 267), 0xfff120 (3 792), 0xfe700c (512); bank 0 window 0x1df228 (3 544), 0x1fe800 (6 144). Their readers as stage 3 recon §6 measured |
| TGP | 7 651 words free; floor 7 500 (`tests/test_tencourse.py`, `tgp_budget >= 7_500`); a variant-only stop spends none |
| RAM | 0x502294..0x502297 all in use (flag and the screen's cells); a variant-only stop and a crew turn at spawn need no new cell [I] |

## 6. Options

| | what | size (estimates [I]) | touches | risk to the normal race | what the player sees |
|---|---|---|---|---|---|
| A | **the lane entered at the forward exit, driven backwards to the box**: the converter picks the variant's pit quad among the lane quads at adjacent list indices near the forward exit (both in the lane, not holding the box, not on any road line, a straight run to the box of 60+ units, the pair spanning the lane) and writes the box with h + 0x8000; Metropolis gets a reverse box deeper in the lane (in the tunnel) | converter ≈ 80-120 lines (`convert/reverse.py`, `tencourse.install_reverse`), `directory._check` relaxed (2 lines), 0 routine bytes, 0 record bytes, 0 TGP words; tests: unit tests of the pair and box on the seven, the record decode, MAME stops | variant records only | none: normal records, routines and collision unchanged [R] | a forced stop in reverse at every course as in a normal race, with the crew half-turned (§4) |
| A2 | A plus a two-quad check: the boot check (0xfe8e8f..0xfe8eab) asks for the record's quad or its second quad (the pad +0x12; q + 1 for every normal entry) | ≈ 40-60 routine bytes, one pattern-checked boot span [I] | a shared routine (the normal path behaves as today by construction) | small: a patched site in the player's handler | the same, and the trigger can sit deeper (Alpine's fires 13 units into the lane with A; 55 with quad 250 alone) |
| B | **a different stopping place**: a reverse box placed by the normal rule from the reverse entry (mid-lane from the forward exit, at least 130 in) on every course, not only Metropolis | converter only, as A | variant records only | none | the car stops at another spot than in a normal race on the courses whose box is not mid-lane both ways |
| B2 | the same mouth used both ways (the reverse car enters at the forward mouth) | n/a | n/a | n/a | not possible as built: the reverse car reaches the forward exit first and the forward mouth opens backwards to it [I from the lane geometry] |
| C | **reduced first version**: A with the crew left as the game places it | A | variant records only | none | the figure in front of the camera on four courses (§4) |
| C2 | A plus **the crew half-turned in reverse**: at the four crew spawns (0xff2518, 0xff26f0, 0xff2735, 0xff277a: `bsr <spawn>; inc.h 191[R25]`, 7 bytes each) reflect the pool objects through the box and add 0x8000 to `+0x2c` when the flag is set (as `figures` does for the grid girls), and widen `figmirror`'s test to the crew's records (seen 0xfd6fee..0xfd732a [M]) so their world-axis animation is mirrored | ≈ 150-200 bytes + ≈ 25 [I, from `figures` 178 and `figmirror` 54]: past the 6 000 test bound (raise it, or a top-anchored block) | boot sites + directory image; the flag gates it (0 in normal races, the attract pit scene, Alpine's PIT START [R stage 3 recon §7]) | small (pattern-checked sites, flag-gated) | the crew round the car in reverse as in a normal stop on Amazon, Metropolis, the Oval and Surfers Road; on Alpine, Pacific and Diablo turned as in the normal race |
| C3 | the crew turned by the park heading in both directions (an arbitrary rotation of the placement and of the root offsets at the draw sites) | ≈ 300-400 bytes [I] | boot sites; **changes the normal race** on Alpine, Pacific and Diablo | a normal-race change (owner, re-drive) | the crew right on all seven, both ways; closes the follow-up |
| D | Diablo's lane wall (quad 1689) moved off the lane at a named spot | 1-3 quads, a fenced rule [I] | **shared collision** | Pascal re-drives Diablo normal; the TGP floor | no crash on the lane's west half at point ≈ 23, both ways |

**Recommendation: A, then C2 as its own task once Pascal has chosen D2.** A makes the stop work on all seven with no routine byte,
no record byte and no shared change, and the prototype completed it on all seven with exactly A's data. The crew is the one thing
a player sees wrong, and Pascal rejected the grid girls behind the car in stage 2 ("they have to be around the car"): C2 reuses that
mechanism, but it is their call (D2). A2 only if they want Alpine's trigger deeper (D5). D only on their word (D4).

## 7. Testing it headless

- **Today [R]**: no committed test drives a pit stop in either direction (`git grep` of `tests/`: the pit appears in static site
  checks, `tests/test_directory.py:313-403`; the converter's geometry, `tests/test_convert_collision.py:2154-2470`; and Alpine's
  PIT START, pit state 6, `tests/test_reverse_build.py:822-922`). `tests/test_reverse_build.py:73` asserts the variants have no pit.
- **Steering into the lane [M]**: normal: line 6 with the lane polyline spliced in (`paths.py`) drove into every lane; reverse: the
  normal pit run's trajectory read backwards (`paths2.py`), with the autopilot's window ahead at 15 points and, on Diablo, the path
  kept east of quad 1689. The product `autopilot.lua` has no window knob: a test needs one (an env var) or paths that never pass
  near another part of themselves.
- **What a reverse pit test asserts** (per course, one 150-s run, plus the plain-line control):

  | assert | from |
  |---|---|
  | `+0x1bf` = 2 at the green | pit log |
  | trigger: handler 0xff2345 on the first frame `+0x150` ∈ {q, q + 1}, at the reverse pair's place | pit log |
  | park: x, z = the variant's box within 0.01, yaw = h + 0x8000 | pit log |
  | release − park = 444; the clock constant from trigger to release, then +384; `+0x1bf` 2 → 1 | pit log |
  | one stop per pass (no trigger at the release frame + 2) | pit log |
  | the next lap counted and its checkpoints in order | race log |
  | no read of the wrong-way warning | `memtrace.lua` taps (`WARNING_READS`) |
  | the opponents advance during the stop (15 of 15) | `fieldtrace.lua` |
  | on line 6 read backwards: no stop | pit log |
  | the normal race unchanged: the normal records and routines byte-identical; one normal stop per course as baseline | ROM compare, pit log |

## 8. Decisions for the owner

| | decision | options | recommendation |
|---|---|---|---|
| D1 | where the car stops in reverse | (a) the normal box on six courses, Metropolis's 40 units deeper towards the forward mouth (still in the tunnel); (b) every course a reverse box mid-lane from the reverse entry (B) | (a): the same garage both ways where the game can reach it |
| D2 | the crew in reverse | (a) as the game places it: half-turned, a figure between the camera and the car on Amazon, Metropolis, the Oval and Surfers Road (`cmp_metro_crew.png`); (b) half-turned back, reverse only (C2); (c) turned by the park heading both ways, normal Alpine, Pacific and Diablo included (C3, a normal-race change) | (b), after a first build with (a) |
| D3 | a first version with the crew as placed | yes (C) / no (wait for C2) | yes: the stop is testable and drivable alone |
| D4 | Diablo's lane wall (quad 1689, west half of the lane at point ≈ 23, both directions) | (a) leave it (the reverse player must keep east there; the normal pit-out passes 1 unit off it); (b) a named-spot fix (shared collision, Diablo re-driven in the normal direction) | show Pascal `sheet_5_diablo_lanewall.png`; (b) only on their word |
| D5 | how deep PIT WORK fires in reverse | (a) the adjacent pairs as they are: 12-75 units into the lane (Alpine 13); (b) a second quad in the record (A2) so every course fires 40+ units in | (a) unless Pascal finds Alpine's too early |
| D6 | per-course exceptions | Metropolis's reverse box (D1), Diablo's wall (D4), Alpine's trigger (D5) | as above |
| D7 | after a stop each checkpoint pays the next sector's extension (§1.1), in both directions | (a) keep the game's rule; (b) correct it (a boot site, both directions) | (a): not a reverse matter |

## 9. Proposed tasks

| # | task | proved by |
|---|---|---|
| 1 | `convert/reverse.py`: the reverse pit pair (adjacent lane quads near the forward exit, not holding the box, on no road line, spanning the lane, a 60+ run) and the reverse box (h + 0x8000; Metropolis deeper) from the same conversion | unit tests on the seven courses: the pairs and boxes of §3 (or better ones), each rule as its own assert |
| 2 | the variant records carry them: `install_reverse` passes pit quad and box; `_check` allows a variant's pit; `tests/test_reverse_build.py:73` updated | decode of the built set; the normal records byte-identical |
| 3 | the autopilot's window knob; MAME tests: a normal stop per course (baseline) and a reverse stop per course with §7's asserts; the plain-line control | headless runs |
| 4 | (D2 b) the crew half-turn in reverse: four crew-spawn sites, `figmirror` widened, layout room | contact sheets normal / reverse; the crew's stored positions mirrored through the box in a MAME run |
| 5 | (D5 b) the two-quad check, if chosen | static listing; the normal stops unchanged in task 3's runs |
| 6 | (D4 b) Diablo's lane wall at a named spot, if chosen | the collision tests; a reverse run on the lane centre; Pascal's normal drive |
| 7 | design, follow-ups, deviations; Pascal's drive of the seven reverse stops | |

## 10. Not verified

- The least straight run the autopilot parks from (26 units circled, 64-68 parked; nothing between was tried).
- A human driver's lines into the forward exits; only the autopilot on the trajectory paths, one race per course. Whether a car
  cutting in late at a forward exit can pass beside the reverse pair (shared tarmac at the exits) was not measured.
- The second reverse stop of a race to its end (Amazon's started at 8526 when the log ended).
- The crew's full mirror (C2): only the placement was turned, from Lua, on Amazon. C3 not tried.
- Put-back and steering assist inside a lane in reverse; the wrong-way read only on Metropolis.
- The wall and grass quads that `lanewalls.py` finds under the lane centre polylines (the Oval's walls 1514-1516 at 112-123 units
  from its forward mouth, grass on six lanes): not driven; only Diablo's quad 1689 was hit.
- What 0xff4101 / 0xff4129 (called at the crew spawns) do, and which code stops the clock during the sequence.
- Metropolis's moved box under the roof: seen on a snapshot, not checked with the roof test.
- That nothing reads the record pad +0x12 (A2's second quad).
- Linked play (the pit autopilot 0xfe98f6, per-cabinet boxes): no reverse race in linked play (design §3).
- The image growth of about 3 000 bytes before the code area is full (first-fit placement not simulated).
- Lap time with a reverse stop against a normal one.
