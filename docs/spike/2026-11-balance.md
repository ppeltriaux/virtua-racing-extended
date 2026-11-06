# Phase 9: balance (M6) — every converted course races on its own tables (31 Oct 2026)

Plan: `docs/superpowers/plans/2026-10-31-phase9-balance.md`; recon: `docs/spike/2026-11-m6-recon.md`; formats:
`docs/formats/model1-course-tables.md` §13–14. Build and race: `spike/ten_course_build.py out/p9/build 90`, then
`spike/race_check.py out/p9/build` (150 s per entry, `race.txt`).

## What landed

- **Race blob per course** (`arcade/race.py`, `convert/race.py`, `tencourse.race_blob_for`): checkpoints at thirds
  of the converted lap; the template's twelve time records (3 operator variants × 4 levels) with each checkpoint
  extension scaled by the sector's length in road points over the template's mean sector (clamped 200..1200
  clock units); the arcade car table with the opponents' performance × `pace`; `laps` = 5. The directory's load
  record carries `race` (+0x2c) and `laps` (+0x30); the loader serves `0x501968` (time record by variant and
  level), `0x50195c` (checkpoints) and `0x5011a4` (laps) from the entry, and the car setup's table choice at
  `0xfe8a91` goes through a new `cars` routine. Entries without a blob (the originals) take the original chains.
- **Spawn list per course** (`arcade/spawn.py`, `tencourse.spawn_list_for`): the host's HUD minimap, start gantry
  and numbered grid boards re-placed at the same road-relative spot (signed road point from the start line,
  lateral, along-track offset, yaw against the road; height from the road profile), the two checkpoint gantries
  at the converted checkpoints, everything else dropped. Pacific Coast, which stopped dead against Bay Bridge's
  board row at (272, −321) in Phase 8, now drives through: forward 3300+ units in 90 s (was 2995), Surfers Road
  2361 (was 2173).
- **Banking** (`profile.banked_height`): the ground mesh's lateral delta against the foot on the centre polyline,
  clamped ±8 units, as a per-course option. A/B, 90 s autopilot, forward units: Surfers Oval 1044 flat / 857
  banked, Surfers Road 2361 flat / 559 banked. Off everywhere (`CoursePlan.banking = False`); the option stays
  for a later look at why the tilt hurts (the nearest-height rule at verge seams is the suspect).

## Build (`out/p9/build`, 90 s autopilot drives, `summary.txt`)

Every entry still renders at 28–29 display-list switches per 57 frames. Forward progress in 90 s: Alpine 3498,
Amazon Falls 3451 (a lap), Diablo Canyon 2897, Metropolis 3481, Pacific Coast 3802 (2995 in Phase 8, before its
host's props went), Surfers Oval 1044, Surfers Road 2361 (2173). Program ROM after the directory: seven tile
tables, seven race blobs (`RACE_BLOB_BYTES` = 1 808 each) and seven spawn lists (1 796 each) inside `CODE_FREE`.

## Race check (150 s under the autopilot, dumps every 250 frames; `tests/test_race_build.py`)

The autopilot is a slow driver (it lifts in every bend; 40–50 units/s against the originals' field at 72 on Big
Forest), so the clock is a floor test, not a balance verdict: decision 11 leaves the balance to playtesting.

| course | points | checkpoints | extension (clock units) | extensions fired | clock expired at (frame) | player laps |
|---|---|---|---|---|---|---|
| Alpine (BF template) | 452 | 151, 301 | 444 | 4 | — | 1 |
| Amazon Falls (BB) | 330 | 110, 220 | 261 | 5 | — | 1 |
| Diablo Canyon (AC) | 453 | 151, 302 | 350 | 2 | 7600 | 0 |
| Metropolis (AC) | 365 | 122, 243 | 283 | 4 | 8350 | 1 |
| Pacific Coast (BB) | 410 | 137, 273 | 324 | 4 | — | 1 |
| Surfers Oval (BB) | 387 | 129, 258 | 306 | 0 | 6100 | 0 |
| Surfers Road (BB) | 441 | 147, 294 | 349 | 1 | 6850 | 0 |

The originals under the same autopilot (road line 0 as its line): see "Baseline" below. The Oval remains the
weak course: the car runs wide onto the inner verge in the flat turns and crawls (Phase 8), so it never reaches
its first checkpoint; a human brakes.

## Baseline

The originals under the same autopilot (its line = road line 0; the autopilot needs `VR_COLLISION_LOG`, it reads
the car's position from the collision probe — a first baseline without it was the unsteered game), 150 s:
Big Forest 6 extensions, never expired, 2 laps (7034 units); Bay Bridge 2 extensions, expired at frame 7350 (the
autopilot crashes on the bridge: 3307 units); Acropolis 4 extensions, never expired (7054 units). Against that:
Alpine, Amazon Falls and Pacific Coast outlast the 150 s; Diablo Canyon (7600) and Metropolis (8350) expire where
Acropolis does not, although their clock per unit of road is Acropolis's by construction (the autopilot's pace is
~45 units/s on both; Diablo's clock ran out 30 units before its start line, where the next extension waits);
Surfers Road 6850 and the Oval 6100 against Bay Bridge's 7350. The autopilot is not the intended driver (a human
at pace does ~100 units/s), so the MAME gate (`tests/test_race_build.py::test_each_course_races_on_its_own_tables`)
checks the mechanics — the entry's own time and checkpoint records are in use, 5 laps, the checkpoints fire (the
Oval exempt: it never reaches its first checkpoint under this driver) — and the balance is a playtest (decision
11) with the knobs below. Candidates if a course feels tight: `time_factor` 1.1–1.2 on the Acropolis-template
courses.

## Review and fix pass

The fresh review found the lap count written in the operator / linked modes (now only in the normal mode: the
loader tests `0x40dc8c` before writing `0x5011a4`) and no cap on laps × checkpoints against the 23 extensions a
record holds (`convert.race.check_laps`: at most 7 laps with two checkpoints). The race report's opponent
progress then showed the real field problem: on every converted course seven opponents sat at the world origin
— the cars on AI lines 5–7, whose line pointers the car setup (`0xfe8ac1`) reads from the pointer block's pairs
5–7, which converted banks never wrote (five pairs since Phase 6; line 0's first points were read as pointers).
With eight pairs every opponent spawns on its grid slot (`opponents_at_origin` = 0 on all seven) — and the
field still does not drive: the leader gains 20–340 road points in 150 s against Big Forest's 870. Two
experiments narrow it down: **Big Forest regenerated from the Saturn data in its own bank** (Phase 6 tables:
our lines, segments and collision on the original's geometry) has a field that does not move at all (leader 0),
so the cause is in the generated tables, not in a course's shape; **Alpine with every opponent on line 0** (the
centreline) lifts the leader from 20 to 239, so the AI lines matter but are not the whole story. A bisection on
the regenerated Big Forest (120 s runs, leader's road points; the original field makes ~700 in that time): our
lines with the original segments and collision 193; the original lines with our segments and Saturn collision 84;
all ours 0 (the fourth combination, original lines and segments on Saturn collision, breaks the player too — the
segments index the original quads). So **both the generated road lines and the generated segments / collision
quads slow the TGP's opponents, and together they stop them**. Next phase: what the AI reads in a line point
beyond x, z and the heading's high half (the heading's low half and `link`'s low half are small signed values on
the originals, zero on ours; `link`'s high half is the segment index), and what it takes from the segment array
and the collision quads (merged 60-unit quads; the per-quad attribute). Scripts: the session scratchpad's
`exp_line0.py`, `exp_regen_bf.py`, `exp_bisect.py` (recreate from the write-up: build + `race_report`).

Consequences in the build: the Oval improves (the seven origin cars had been sitting on its road: 1044 → 1663
forward in 90 s) and the Bay Bridge-template courses get worse for the autopilot, whose spawn (road point 0,
lateral 0) is inside the stalled pack (Pacific Coast 3802 → 1542; `MAX_BACKWARD` in the drive gate). The
opponents' pace is therefore **open** and carried to the next phase with the experiment scripts' findings; the
pointer block fix stays because it is correct data and the field must be on the grid for any AI fix to show.

## Knobs for playtesting (`tencourse.COURSES`)

`laps` (5), `time_factor` (1.0: multiplies every extension; the initial clock is the template's), `pace` (1.0:
multiplies the opponents' performance floats, clamped 1.0..2.847 — 2.847 is the player's and the TGP's cap),
`banking` (False). Rebuild with `spike/ten_course_build.py`, race with `spike/race_check.py`.

## Open

- **The opponents do not drive on generated tables** (the M6 opponents goal is not reached): see the bisection
  above. Until then every converted course has a stalled field, and the Bay Bridge / Acropolis-template courses
  spawn the player inside it.
- The Surfers Oval's inner-verge excursions (banking rejected; the collision seams or the AI lines are next).
- Opponent AI lines are still fixed lateral offsets (Phase 6); the hosts' hand-made racing lines are the model.
- The alternate car table (operator flag `0x40dc8c`: other bodies, other line pairing) is not served for
  converted courses (one table for both modes).
- `0x5011a8` (set beside the lap count: 0x188 / 0x168) is not understood; converted courses leave it.
