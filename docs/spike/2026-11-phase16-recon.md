# Phase 16 recon: the swapped attitude fields, the player's roll, Diablo's pitch steps, the walls (31 Oct 2026)

Pascal after Phase 15: walls and the player's roll next, and the player's pitch on Diablo Canyon. Experiments under
`out/p16/`; scripts in the session scratchpad `p15/`.

## 1. Phase 15 swapped pitch and roll

The decisive test: every Alpine tarmac quad tilted directly in the ROM, right side up (`out/p16/tilt`, `tilt6`).

| Tilt across each quad | `+0x2a` median | `+0x2e` median |
|---|---|---|
| none (Phase 14 build) | +0.00° | +0.00° |
| 1 unit | +0.00° | −2.15° |
| 6 units (about 13°) | +0.23° | −13.08° (196 of 203 samples below −3°) |

And on flat Alpine's climbs the player's `+0x2a` follows its own slope with a correlation of +0.94 (83 windows),
`+0x2e` +0.19. So **`+0x2e` is the roll (negative = right side up) and `+0x2a` the pitch (positive = climbing)**:
the attitude recon (`2026-11-attitude-recon.md` §1) had them the other way round. Consequences:

- The opponents' code (`0xfece55` moves `+0x2a` toward the point's **heading** low half, `0xfece67` moves `+0x2e`
  toward its **link** low half) means **heading.lo = pitch target, link.lo = roll target**. Phase 15 wrote the roll
  into heading.lo and the pitch into link.lo: on `main` (e758fa3) the opponents tilt sideways on climbs and pitch on
  banked bends. The signs Phase 15 chose (pitch positive climbing, roll negative right-up) match the game's
  convention; only the halves are swapped. Big Forest's own values then read: pitch up to 994 (5.5°), roll up to
  3821 (21°, its banked bends) — Phase 15's clamps (pitch 3800, roll 1000) were the wrong way round too.
- The page captures taken from that build (`out/site4`) must not be published.

## 2. The player's roll works once the quads carry camber

The tilt test above is the player's own TGP roll following the quads, in proportion (6 units over a ~26-unit quad,
13.0° measured against 13° geometric). The Phase 15 "median roll 0.00" read the pitch field. The camber experiment
(`out/p15/camber`) also put only half the intended tilt into the quads (mean slope 0.047 for 0.1 asked, uneven:
0.006–0.086), because `cambered_height` takes its lateral from `lap_directions` (the lap order zigzags through
side-by-side strips; the Phase 15 review flagged the same for the roll targets). Fix: camber from the slice normal
along the smoothed centreline's lateral, `CoursePlan.camber` on, the Surfers forward-progress A/B as the gate.

## 3. Diablo's pitch steps are the player's collision heights

`profile_height(x, z)` projects onto the nearest lap centre and its lap-order neighbours; on zigzag strips it
plateaus then steps about 5 units (Diablo points 49–58: −23.09, −23.04, −17.67, −17.68, −12.84 …, the Phase 15
review). The opponents' pitch now uses the arc profile; the collision quads' corner heights still use the 2-D
projection, so the player's car pitches in steps on Diablo's climbs. Fix: the collision height function takes the
arc of the nearest centreline point and interpolates the arc profile (the same `_arc_profile` as the opponents),
then adds the camber.

## 4. The walls

- Big Forest's car slid along x = −169.4 for 200 frames (Phase 14). Not a vertical collision quad: Big Forest has one
  zero-area quad in 4974, none near the slide. Not a spawn entity: none of its 32 entities lies within 60 units.
- The player's position has one writer in free running and in a wall slide alike (`0xfe954e` x, `0xfe9553` z,
  `out/p16/wall-bf`), so the wall acts on the velocity before the position update, most likely from the collision
  answer at the car's next position (no quad, or a quad of some surface kind, refusing the move).
- **The wall is surface kind 5.** The per-wheel kinds (`+0x142..148`) are `1 << surface byte`: tarmac (1) reads 2,
  grass (2) reads 4, kerb (8) reads 0x100, and at the instant Big Forest's car locks to x = −169.4 one wheel reads
  **0x20 = surface 5** (`out/p16/wall-bf2`, frames 2525–2535; then all four wheels on grass while the car slides
  along the line). The attitude code's `and #21` tests kinds 1 and 0x20. Bay Bridge's surface table holds 705
  quads of kind 5 (and 931 grass, 962 kerb, 149 kind 3).
- **Confirmed on a converted course:** Alpine built with every non-tarmac quad as surface 5 (`out/p16/kind5`), the
  same 50-frame swerve: the car never gets more than about 15 units off the centreline, scrapes along the road edge
  and loses speed (77 to 25 units/s), wheels reading 0x20 at contact. With grass verges it went 111 units out.
- Design for Phase 16: grass verges out to a wall line, then a strip of surface-5 quads (the wall), nothing beyond.

## 5. Outcome (Phase 16, `docs/superpowers/plans/2026-10-31-phase16-walls-attitude.md`)

- Attitude: pitch → heading.lo, roll → link.lo, clamps 3800 both; the opponents' `+0x2a` follows the pitch target at
  their road point (correlation 0.92–0.95 on Alpine); Big Forest's opponents' roll unchanged (sd 2–8°).
- Collision: `profile.arc_height` (arc profile + slice-normal camber, ±1.3 units). Diablo: the height under the car's
  centreline off the profile by more than a unit at 8 of 452 points (84 with the 2-D projection, max 4.45 → 1.65); the
  player's pitch follows its climb at +0.60 (+0.37 before). The Oval: the player's roll has the camber's sign on ≥ 70 %
  of the banked samples (the flat build: 22 of 299 samples beyond 1°).
- Walls: 30 units of grass + 6 of surface 5 (fused: 137–240 wall quads per course); the 50-frame swerve on Alpine and
  Pacific Coast stays within 56 units of the centreline (111 and 123 with Phase 14's grass), slows by ≥ 30 % and comes
  back; every Phase 11–15 drive gate holds (46 drive tests).
- Open: the page's media re-capture (Task 5); Pascal's eye on the opponents' lean and the player's bank in the clips.
