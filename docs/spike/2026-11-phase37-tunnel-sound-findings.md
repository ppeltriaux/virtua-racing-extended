# Phase 37 findings: the arcade's tunnel sound on three stretches of the converted courses (prototype)

Status: **a prototype awaiting Pascal's judgement.** Heard and driven by them on 16 Nov in three runs (Alpine's tunnel once: "tunnel sound is
good, ..."; then Bay Bridge's own: "ok tunnel is validated"; §0); Metropolis's two stretches, reverse and the pit stop not driven by them. 16 Nov 2026. Branch `phase37-tunnel-sound`
(local, cut from the recon's commit 991f9ff on main 1159aab; not merged, not pushed). Recon:
`docs/spike/2026-11-phase37-tunnel-sound-recon.md` (the mechanism, the candidates, the options).

- Play set: `out/p37play1` (this branch's build). Launcher: `out/rec169/launch.sh` (windowed MAME with sound, records
  `out/rec169/inp/play.inp`; not launched here).
- Recordings, before and after, from the built set: `out/p37/listen/built/` (its `NOTE.txt`). Scratch, not in the repository.
- Main's set built by the same tool for the comparisons: `out/p37/base` (file for file `out/p34play4`).

## 0. Who said what

- **Pascal, 16 Nov 2026, the request:** "also for next work i would like to add the sound effect we have in tunnel (like in bay
  bridge tunnel) on all the saturn level undergrand sections like metropolis tunnel..."
- **The coordinating session, 16 Nov,** sent them eight of the recon's stills and its three recording pairs and put the recon's
  six questions with these recommendations: (1) the arcade's effect exactly as on Bay Bridge: yes; (2) the stretches: yes to
  Metropolis's long tunnel (B, 245-313), Alpine's mountain tunnel (A, 106-145) and Metropolis's roofed road by the pit lane (A,
  50-62); no to Metropolis under the building (C), Diablo Canyon's high bridge (D, "your call"), Surfers Road's footbridge and
  every arch, bridge and gate; (3) any covered place missed?; (4) Metropolis's pit lane under roof A sounds like the road beside
  it: yes; (5) reverse races use the same stretches: yes; (6) the three arcade courses untouched: yes.
- **Pascal answered, exactly:** "Yes to all". They named no missed place. Whether they listened to the recordings is not stated.
  Not a word to merge.
- **Pascal heard and drove it, 16 Nov:** `out/p37play1` through `out/rec169/launch.sh`, one run, 53 s, MAME 99.74 % (other
  jobs running; recording `out/rec169/inp/pascal-2026-11-16-p37tunnel-53s.inp`). Asked by the coordinating session how the tunnel
  sounded (right, too strong, or not noticeable) and whether they wanted either of the two short Metropolis underpasses
  (176-178, 186-191; its recommendation: no), they said exactly: "tunnel sound is good, launch the game again i want to test
  something". They did not answer about the two underpasses in that reply (answered later, below). Not a word to merge.
  **What that run was** (the recording replayed headless on `out/p37play1` from the launcher's start state with the latch log,
  `out/p37/runs/replay1`; 3 078 recorded frames): **Alpine, normal direction**; the green at frame 1072; the car came onto the
  mountain tunnel's first flagged quad (87, point 108) at frame 1924, `C201` at 1927; it left onto quad 129 (point 148) at 2678,
  `C200` at 2680: **one pass of Alpine's tunnel, 13.1 s inside it**; the recording ends at road point 182 of the first lap.
  Neither Metropolis stretch, no reverse race and no pit stop were driven in it.
  **Second run:** 19 s, MAME 98.03 % (`out/rec169/inp/pascal-2026-11-16-p37tunnel-19s-2.inp`); asked what they were testing:
  "wrong circuit", then "relaunch". Replayed (`out/p37/runs/replay_19s-2`; 1 125 recorded frames): the coin, the course select;
  the recording ends on the select screen with entry 2 (Acropolis) under the wheel. No race frame is in it.
  **Third run:** 32 s, MAME 99.99 % (`...-32s-3.inp`); asked whether they got to their test and what they found: **"ok tunnel is
  validated"**. Replayed (`out/p37/runs/replay_32s-3`; 1 899 recorded frames): **Bay Bridge, normal direction** (an arcade
  course, untouched by this phase); the green at frame 994; the car came onto the arcade's own tunnel's first quad (69) at 1778,
  `C201` at 1780, and left onto quad 89 at 1892, `C200` at 1894; the recording ends 5 frames later. What the "something" they
  wanted to test was is not stated. "validated" is not a word to merge.
  **The two underpasses, answered (16 Nov).** After "ok tunnel is validated" the coordinating session said the two short
  underpasses stay without the effect unless they say otherwise; they asked "which one"; it sent four stills (D at points 174
  and 176, E at 183 and 187) with a table (176-178, 13 units, about 0.15 s; 186-191, about 44 units, about 0.5 s) and "I
  recommend leaving both out... Say 'add the second' or 'add both' if you'd like to hear them with it." They answered exactly:
  **"yes correct"**. Read as agreeing to leave both out: D and E stay unflagged, now by their answer. Not a word to merge.
- Everything below this line is this session's work; of it Pascal has heard Alpine's tunnel once (and the arcade's own on Bay
  Bridge), as above.

## 1. What was built

Option A of the recon: data only. No V60 code, no sound-board change, no new table.

- `CoursePlan.tunnels` (default none): `((first, last), ...)` in road points. `convert/road.tunnel_quads` takes every tarmac
  quad the segment array credits to a point of a stretch; `with_tunnel_flags` sets `FLAG_TUNNEL` (0x80, the arcade's bit 7:
  flag 0x81, Bay Bridge's own value) on those quads in the normal array and, **the same quad indices**, in the reverse
  variant's array (`tencourse.convert_course`; the conversion's report lists them under `tunnel_quads`).
- The plans: Alpine `((108, 146),)`, Metropolis `((50, 62), (251, 311))`. Nothing else.
- A test helper, `vrtools/mame/lua/sound_log.lua` (VR_SOUND_LOG; autoplay.lua and attract_snaps.lua load it):
  every byte the V60 writes to the sound latch, and the player's mode, handler, quad and flag at each change;
  `runner.parse_sound_log`.

### 1.1 The point ranges against the ones agreed

The recon's ranges (106-145, 245-313, 50-62) were of the driven car's samples (a roof over the car or 4 units to a side). A
flag belongs to a quad, and a quad is credited the road point its front edge has reached. The plans name the quads whose
centre lies under the drawn roof:

| stretch | agreed as | in the plan | flagged quads | why the numbers moved |
|---|---|---|---|---|
| Alpine, the mountain tunnel | 106-145 | 108-146 | 87-119 (33) | the quad credited 106 has no roof over its centre; two quads credited 146 have |
| Metropolis, the roofed road by the pit lane | 50-62 | 50-62 | 60-89 and 91 (31) | as agreed |
| Metropolis, the long tunnel | 245-313 | 251-311 | 377-410 (34) | the road quads credited 245-249 and 313 have no roof over their centre; the first roofed one is credited 251 |

They are the same three places. The effect starts when the car comes onto the first flagged quad (its rear edge lies up to a
quad's length before the point it is credited) and ends when it comes onto the first quad past the last.

### 1.2 Metropolis's pit lane (answer 4)

The lane's tarmac quads under roof A are credited to the stretch's own points, so the point list flags them; no separate rule
was needed. Under the roof (drawn from z 227 to about z 342, 8-12 units above the tarmac):

- the road's quads at x -110 and its side strips at x -99 and -121 (quads 60-63, 65-67, 69, 70, 73-76, 81-85, 88, 89);
- the lane's quads at x -90 and -75: **64, 68, 71, 72, 77, 78, 79, 80, 86, 87 and 91**. Quads 71/72 are the normal entry's pit
  pair (the PIT WORK trigger), 86/87 the reverse variant's; the normal box (z 310.4) lies on 77/79, the reverse box (z 269.7)
  on 71/72.
- Three flagged quads reach out from under the roof's end at z 342: the road's 88 and 89 (centres z 346, 345) and the lane's
  91 (z 346). **Kept as they are** (the reviewer: a list of road points cannot trim them, they are credited to the stretch's
  last points; the cost is about 0.16 s). The effect therefore ends about 10 units (0.13 s at 300 km/h) past the roof's edge in the normal direction and
  begins as much before it in reverse.

## 2. Exactly which bytes differ from main's set

`out/p37play1/vr.zip` against `out/p37/base/vr.zip` (main at 1159aab built by the same tool; file for file `out/p34play4`):
**196 bytes in two of the 38 files, each 0x01 on main and 0x81 here**; the other 36 files are identical.

| file | bytes | what they are |
|---|---|---|
| `mpr-14888.12` (data bank 3, even bytes) | 66 | Alpine: the low byte of the flag of quads 87-119 in the normal segment array (window 0x142470; data-ROM offsets 0x342736 to 0x342836, every 8) and in the reverse array (window 0x15a2d0; 0x35a596 to 0x35a696) |
| `mpr-14886.10` (data bank 2, even bytes) | 130 | Metropolis: the same byte of quads 60-89, 91 and 377-410 in the normal array (window 0x175c50; data-ROM offsets 0x275e3e to 0x27692e) and in the reverse array (window 0x19af30; 0x29b11e to 0x29bc0e) |

A flag's low byte is at data-ROM offset `array + 8 * (quad + 1) + 6`. The collision (the TGP's data), the program, boot and
polygon ROMs, every road line, the race blobs and the three originals' banks are untouched. The build reports of the two sets
are identical but for the path.

## 3. Gates

The first invocation, on d41891a's tree, 16 Nov (`out/p37/final_invocation.log`; started 15:24, after the last change to any code or
test; `out/p37play1` was built from the same code): **222 passed, 0 failed, 35 deselected in 54:45.**

    pytest tests/test_tunnel_flags.py tests/test_tunnel_sound_build.py tests/test_frame_rate.py tests/test_mame_runner.py \
      tests/test_convert_road.py tests/test_convert_reverse.py tests/test_course.py tests/test_blob.py \
      -k "tunnel or (holds_the_arcade_rate and (entry_3 or entry_6)) or metropolis_pit or test_mame_runner or
          test_convert_road or test_convert_reverse or test_course or test_blob"

(`VR_MAME_JOBS=2`. The 35 deselected are the rest of `tests/test_frame_rate.py`. No failure, so nothing to compare with
`out/p27/full_failed.txt`; none of that list's tests was in the selection.)

"Main's set" in these tests is the same seven conversions built in the same session with every plan's `tunnels` emptied and
nothing else changed (`tests/test_tunnel_sound_build.py`'s `Session.plain`). Frames are video frames (57.52 a second).

| gate | test | what it showed |
|---|---|---|
| the flag writer | `tests/test_tunnel_flags.py` (12 without the ROMs) | the quads of a stretch are those credited to its points, ends included; only bit 7 is added; the reverse array takes the same quad indices; a bad or overlapping stretch is refused; the plans carry the three stretches and no other; the latch log's parser |
| each stretch tied to the drawn roof | `test_each_named_stretch_lies_under_the_roof_the_set_draws` (Alpine, Metropolis), `test_no_other_long_roofed_run_of_road_is_left_unnamed_on_the_two_courses` | every road quad of a stretch has a drawn face 2-60 units over its centre but at most one in seven (Metropolis's quad 88); none in the 5 points before or after has one; the same stretch moved 4 points either way fails; outside the stretches no 10 road points in a row are roofed (Metropolis's building, 354-358, is 5) |
| the bytes | `test_the_set_is_main_s_byte_for_byte_but_the_named_flag_bytes` | §2: the program, boot, polygon and TGP regions identical; the data region differs at exactly the named flag bytes |
| the flags | `test_every_flag_of_a_converted_course_is_plain_or_the_tunnel_s_and_both_arrays_flag_the_same_quads`, `test_metropolis_s_pit_quads_and_boxes_lie_on_flagged_quads_of_the_first_stretch` | all seven courses, both arrays: flags 1 or 0x81 only, 0x81 on the same quads both ways, none on the five other courses; Metropolis's pit pairs 71/72 and 86/87 are in the first stretch |
| the originals | `test_the_three_originals_segment_arrays_are_the_source_set_s`, `test_bay_bridge_still_fires_at_its_own_quads_and_its_stream_is_main_s` | the three arrays byte for byte the source set's; Bay Bridge on the built set: `C201` as the car comes onto quad 69 (frame 2788, the command 2 frames later), `C200` onto quad 89 (2894), and the whole command stream (562 commands) frame for frame main's |
| on at the mouth, off at the exit, once a pass | `test_each_stretch_switches_the_sound_on_at_its_mouth_and_off_at_its_exit_once_a_pass` (4) | below |
| the race and the other sounds are main's | `test_the_race_is_main_s_pass_for_pass_and_its_other_sound_commands_are_main_s` (4) | main's set with the autopilot, the set on the same taped inputs (7 027 tape lines): all 4 178 logic passes identical (clock, 16 cars' x, z, road point, speed, lap, the frame each pass ends in) on Alpine and Metropolis in both directions; the commands other than `C2xx` are the same words, as many of each (1 705 / 2 339 / 2 390 / 2 277), each no earlier than on main's set and at most 10 frames later; main's runs send no `C2xx`. **Not "in the same order"** (corrected after the review): a `C2xx` takes a turn of the queue, so a queued command behind it comes later and can change places with a revs word, which is not queued; the reviewer's staged Metropolis put-back showed it (`B045` and `C066`: main `B045` at 5682, `C066` at 5683; the set `C066` at 5683, `B045` at 5684). In these four races the order happened to be the same; the test no longer asserts it |
| the attract | `test_the_attract_sends_no_tunnel_command` | 300 s (17 258 frames) of the set's attract: no `C2xx`, although the demo's car crosses flagged quads in it: Bay Bridge's demo drives through the arcade's tunnel (flag 0x81 under the car on 40 logged frames, quads 69-88; asserted since the review). The demos in that time are of the three originals; none shows a converted course's stretch |
| nothing leaves the effect on | the four tests of §4 | §4 |
| the rate | `tests/test_frame_rate.py`: `test_every_course_holds_the_arcade_rate` entries 3 and 6, normal and reverse; `test_the_worst_known_frames_hold_the_arcade_rate[metropolis_pit]` | all five hold the arcade's rate: 3 511 logic frames each, the render rate 28-29 in every window from the green, the overrun counter still, no list skipped; worst V60 busy 11 142 us (Alpine), 11 276 (Alpine reverse), 12 699 (Metropolis), 12 540 (Metropolis reverse), 14 489 (Metropolis's pit lap, with a stop), under the two vblanks (`out/p37/pytest_try1/rate0/rate_summary.txt`) |

The passes of the 150-s races (the frame the flag changed under the car, the quad, its road point in that direction's array; each
command came 2-4 frames after its change, 2-8 over every run of the module, against a bound of 10):

| race | on | off |
|---|---|---|
| Alpine normal | 2916 (quad 87, point 108); 6674 | 3240 (quad 123, point 148); 7046 |
| Alpine reverse | 5136 (quad 117, reverse point 308) | 5604 (quad 86, reverse point 349) |
| Metropolis normal | 2388 (quad 60, point 50); 4686 (quad 377, point 251); 5998; 8034 | 2624 (quad 90, point 63); 5268 (quad 412, point 313); 6106 |
| Metropolis reverse | 2438 (quad 409, reverse 53); 5216 (quad 88, reverse 303); 6072 | 3188 (quad 376, reverse 116); 5322 (quad 59, reverse 317); 6710 |

Every pass lay in one stretch, began within 6 road points of the end it was entered by and ended on an unflagged quad. Alpine's
reverse race reached its tunnel once in 150 s (the autopilot's pace there); the others two or more times.

**After the review's fix wave, one invocation on the final tree** (`out/p37/final2.log`): **66 passed, 0 failed, 35 deselected in 39:51** (started 16:39, after the last change to any code or test; the docs were
edited while it ran).

    pytest tests/test_tunnel_flags.py tests/test_tunnel_sound_build.py tests/test_frame_rate.py tests/test_mame_runner.py \
      -k "tunnel or (holds_the_arcade_rate and (entry_3 or entry_6)) or metropolis_pit or test_mame_runner"

15 + 20 of the two tunnel modules (the 18 above, their comparisons as corrected, and the two put-backs), the five rate tests (the
same figures as the first invocation's, to the microsecond) and `tests/test_mame_runner.py`. The four converter modules of the
first invocation were not run again: no file they cover has changed since d41891a.

## 4. What a pit stop, a race's end and the attract do to the effect

The sound board's bit is set by `C201` only, and cleared by `C200` and by the reset `8100`. The V60 sends `C201`/`C200` only from
the player's race handler, on a change of the flag under the car.

Measured on the built set (`tests/test_tunnel_sound_build.py`), with a model of the board's bit read from the latch log
(`SoundLog.bit_at`). In every run below the commands match the flag's changes one for one, and from 12 frames after any change
of flag, mode or handler the board's bit equals the flag's bit under the car for as long as the race lasts.

| path | test | measured |
|---|---|---|
| **a pit stop under roof A, normal direction** (after the review: the same lap on main's set too; its pit log and collision log byte for byte the set's, in both directions) | `test_a_pit_stop_under_metropolis_s_roof_keeps_the_effect_on_and_ends_it_at_the_way_out[False]` | `C201` as the car comes onto the lane's quad 64 (frame 2390); PIT WORK triggers on quad 72 at 2420 with the bit set; the pit sequence's handler runs to the release at 3122 (the car parked at the box, -89.6, 310.4; the crew's work): every frame of it on a flagged quad, no command, the bit set throughout; the race handler is back within 4 frames; `C200` as the car comes onto quad 90 at 3258. The next lap's pass through the lane (no second stop asked) is 6454 to 7254 |
| **the same in reverse** (the lane entered at its normal exit, the reverse box 40 units deeper) | `...[True]` | `C201` onto quad 91 at 5168; the trigger on quad 86 at 5180, bit set; release at 5876 (the box at -89.6, 269.7), no command between, bit set; `C200` onto quad 59 at 6030 |
| **a race that runs out of time inside a stretch** | `test_a_race_that_runs_out_of_time_inside_a_stretch_is_followed_by_the_reset` | the clock run out on the first flagged frame (stretch A): `C201` at 2391, the race ends at 2394, **the game's own `8100` at 2397** clears the bit; through the game's end (modes 0x15, 0x16, 0x1b-0x1d) and the attract, to the run's end 68 s later, no `C2xx` and the bit clear |
| **a finished game, the attract, a coin, a second game** | `test_a_finished_game_the_attract_a_coin_and_a_second_game_start_with_the_effect_off` | a one-lap normal game (race 1864-5656: stretch A 2388-2624, B 4686-5268), what the game shows after a finish, the attract (`8100` at 8046), a coin, a one-lap reverse game (race 9364-13308: B 9922-10554, A 12850-12954): the bit is clear at each green, at each race's end and on every logged frame outside the two races; the second game's first tunnel command is a `C201`; a reset follows each game |
| **the attract** | `test_the_attract_sends_no_tunnel_command` | no `C2xx` in 300 s, the demo's car on Bay Bridge's flagged quads in it (§3) |
| **a put-back inside a stretch** (the reviewer's staging: the wheel held, the off-course limit poked down; they got Metropolis put back onto flagged quad 406 at frame 5390 and Alpine onto flagged quad 95 at 3058, race and collision logs byte-identical to main's, `C201`/`C200` balanced) | `test_a_put_back_inside_a_stretch_leaves_the_bit_with_the_flag` (Alpine, Metropolis; `putback.lua`, added after the review) | this session's standing version of it, on both sets (the paddle held hard over for 120 frames from a quad inside the stretch, the limit at 1 logic frame: the tunnels' walls keep a car on the tarmac): Alpine, held from frame 3010 on quad 93, **put back at 3040 onto flagged quad 94**; Metropolis, held from 5066 on quad 395, **put back at 5116 onto flagged quad 400**. The race log, the collision log and the put-backs are byte for byte main's; the bit is set at the put-back and stays with the flag; the stretch ends with its `C200` (Alpine 3478, Metropolis 5689); `C201`/`C200` in turn. A put-back onto an unflagged quad was not staged (in a tunnel the remembered quad is the tunnel's) |

No path was found that leaves the effect on, so nothing was fixed. Why none can, from the code (recon §1.2): the bit is set
only by `C201`, sent only on the frame the flag comes on under the player in a race; while the race handler runs, the next
frame off a flagged quad sends `C200`; when it stops running (a race's end) the game resets the sound board.

Not covered by a run: a coin and a second game straight after a race that timed out in a stretch (the board is already reset
at that point, and the second game of the finished-game run starts clear); a race finished (not timed out) inside a stretch
(no stretch holds a finish line).

## 4.1 The review (16 Nov) and its fix wave

The review of d41891a had no Critical or Important finding and five minors; all are taken, none changes a ROM byte.

1. The stream comparison asserted an exact order that a queued command behind a `C2xx` need not keep (the reviewer's staged
   put-back): now `_same_other_commands` (the same words, as many of each, each 0-10 frames later). §3's sentence corrected.
   The reviewer's staged put-backs are standing tests (credited to them above). The pit laps are compared with main's.
2. Two Metropolis underpasses (points 176-178 and 186-191) were missing from the recon's table: added there with stills
   (`out/p37/look/metropolis_*_D_*`, `*_E_*`). **They were not in the list Pascal answered "Yes to all" to.** Put to them separately since: not flagged, by
   their answer (§0).
3. `docs/deviations.md` now says how the stretches were put to Pascal (106-145, 245-313) and how they are built.
4. The attract test asserts the demo crossed flagged quads.
5. The recon's §1.2 cites the reviewer's reads of the segment array (two of them checked here) instead of the operand search.

**No ROM byte changed:** `git diff d41891a -- vrtools/arcade vrtools/convert vrtools/saturn vrtools/geom vrtools/cli.py` is
empty (the wave touched tests, two Lua helpers' worth of test tooling and docs), and the working tree built again after the wave (`out/p37/rebuild`) is file for file `out/p37play1`, all 38 files, the build reports identical but for the path. `out/p37play1` is the build of the final tree.

## 5. Not verified

- **By Pascal: of the three stretches only Alpine's tunnel, normal direction, one pass (§0).** Metropolis's two stretches, any reverse race and the pit
  stop under the roof have not been heard or driven by anyone. The recordings in `out/p37/listen/built/` were made headless.
- Real hardware; MAME's MultiPCM against a cabinet. Linked play. The service menu.
- A start on a flagged quad (no grid is under one; recon §7): not built, not measured.
- A second game after a race that ran out of time in a stretch was not played in one session; the board's bit is clear from the
  game's own reset on (§4), and a second game after a finished race was.
- Big Forest and Acropolis were not raced with the latch log (their segment arrays are byte for byte the source set's and
  carry no bit 7).
- The long suites were not run (the project's rule: once, at the end of a batch). The tests run are listed in §3.
- Whether the Saturn game changes its own sound in these places (recon §3.3).

## 6. If Pascal does not keep it

Empty the two plans' `tunnels`: the set is then main's, byte for byte (the comparison build of §3 is made exactly so).
