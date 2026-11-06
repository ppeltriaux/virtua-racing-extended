# Phase 15 recon: the car's attitude — no roll with the camber, opponents flat on climbs (31 Oct 2026)

Pascal, watching the Pacific Coast clip on the page: the player's car does not bank to the side when the road does,
and the opponents keep flat when going up. Experiments under `out/p15/`; scripts in the session scratchpad `p15/`
(`attitude.lua`: per-frame pitch/roll/yaw of cars 0–3; `pitchwriter.lua`: who writes an opponent's pitch).

## 1. How the game sets a car's attitude

- **The player** (boot `0xfebd1a..0xfed7d3`, after the collision answers): the TGP returns four wheel heights
  (`+0x132/136/13a/13e`, defaults `0x501260..0x50126c` = the car's own y); `0xfed6b9..` asks the TGP for
  `atan` of the height difference over the wheelbase (command `0x05000000` on two `0x00800000` products from
  the wheel-offset table `0xfd3856`) → **pitch `+0x2e`**, then the same across → **roll `+0x2a`**; the per-wheel
  surface kinds (`+0x142..148 & 0x21`) pick which wheel pair. The displayed angles (`0xfea9e9..`): `+0x50` =
  pitch + `+0xe9` (a lean from steering × speed), `+0x4c` = roll + `+0xe5`, `+0x4e` = yaw `+0x6a` + `+0xe7`.
  So the player's roll is whatever the collision quads say under its four wheels: **our quads carry no lateral
  tilt** (the road profile is one height per 10 units of arc, "lateral tilt dropped", `docs/deviations.md`), so
  the player never banks. Its pitch works (front and rear wheels on a sloped profile): Alpine's trace shows
  −4..+11°.
- **The opponents** (boot `0xfecd90..0xfece6b`, every other frame): yaw `+0x36` moves toward a TGP answer
  (`0x07800000`); **roll `+0x2a` moves toward the halfword at `+8` of the car's current road-line point, pitch
  `+0x2e` toward the halfword at `+0xc`** — i.e. the **low halves of the road point's `heading` and `link`
  words** (formats §4: "low half small, mostly 0"; `link = segment << 16 | small`), in 1/65536 turn, approached
  over `R21` steps. Traced on Big Forest (`out/p15/att-bf`, `pw-bf`: writers `0xfece55` roll, `0xfece67`
  pitch): an opponent's roll follows the nearest point's heading low half (433 ↔ 505, −434 ↔ −464, 450 ↔ 579)
  and its pitch the link low half (2897 ↔ 2405, 2781 ↔ 3653, with lag). **The converter writes both halves as
  0** (`convert/road.py`: `RoadPoint(x, z, words[k], seg_at[k] << 16)`), so on every converted course the
  opponents' pitch and roll are exactly 0 for the whole run (Alpine trace: sd 0.00 on cars 1–3; Big Forest:
  pitch −15..+19°, roll ±4°).
- These per-point values are **authored attitude, not the collision's slope**: Big Forest's collision heights
  (segment k = quad k, mapped to road points) stay within 30–38 units over the lap with gradients under 2.5°,
  while the fields reach ±21° of pitch (points 102–111, 242–257, 268–288: the overpass humps) and ±5° of roll.
  Sega exaggerates. The originals' tarmac quads do carry camber: 20 % of Big Forest's first 256 tarmac quads
  differ by more than 0.5 units across the road (max 2.7 over a 26-unit width, about 6°), Bay Bridge 21 %,
  Acropolis 6 %.
- The Saturn slices carry the angles we need (`docs/formats/saturn-trck.md` §4, `Segment.words`): word 16 =
  banking about Z, word 17 = slope about X, in 1/2³² turn. On Alpine 428 of the lap's 526 slices have one
  non-zero: banking up to ±17.8°, slope up to +13.5° (slice 418), matching the normals.

## 2. Sign conventions (Phase 15, settled where the evidence allows)

- **Pitch: a positive value draws the car nose-up.** Two captures of Alpine's first climb (car 5 ahead at 30–40
  units, `out/p15/signcap` with −1250 written, `signcap2` with +1300): the negative value drew the car ahead rear-up,
  nose-down; the positive value level to nose-up. `road.PITCH_SIGN = +1` (a climb is positive). The recon's earlier
  reading of Big Forest's tables (positive on the descending side of the overpass) used quad heights that mix the
  two decks and is set aside; the authored values also lead the geometry (the car pitches before the crest), which
  is why the opponents' height change correlates poorly with the field.
- **Roll: a negative value draws the right side up.** Big Forest's own tables: at road points whose quads have a
  camber over 0.3 units, the roll field is positive where the right side is LOWER on 17 of 20 (segment-mapped quads);
  the first capture's leaning car agreed. `road.ROLL_SIGN = −1` on top of the geometric slope (right side up positive).
- **The geometric camber comes from the slice normal, with its horizontal components NOT negated.** `to_arcade`
  negates a point's x and z before the placement rotation; doing the same to the normal gave the opposite lateral
  slope to the ground mesh (which is built from the points) at every banked centre on Alpine (0 of 68 agreeing) and
  the Oval (0 of 113), with matching magnitudes; `geometry.normal_to_arcade` therefore rotates (nx, nz) as they are.
  The slice's banking word 16 was dropped as the source: its sign depends on the lap's direction through the slices,
  and on Alpine's first climb it gave −4° where the normal gives level.
- **The player's own roll stays flat whatever the quads carry.** The wheel-height trace (`out/p15/wheels-*`) shows the
  four heights at `0x501260..6c` written by the same four TGP queries on both courses (`0xfed628/652/67d/6a8`; the
  `+0x132..13e` words are something else) with a spread up to 1.6 units on Big Forest and 1.2 on Alpine; the player's
  pitch sd is 8.7° on Big Forest and 1.1° on Alpine — Alpine's profile is flat at 0.0 for a quarter of the lap and
  steeper than 3° on 18 % (heights −55..0.3). But a clean experiment with every Alpine quad tilted right-side-up by
  5.7° (`out/p15/camber2`, the lateral from the smoothed lap direction) still reads a median roll of 0.00° (100 of
  178 moving samples within ±1°, mean +1.8°). The per-wheel query evidently does not sample the quads laterally the
  way the corner heights suggest; how Big Forest's camber reaches the player's roll is unresolved. Camber in the
  collision quads (`profile.cambered_height`, `CoursePlan.camber`) is built and tested but **off by default**.

## 3. Fix (Phase 15)

1. Road points: `heading` low half = roll target, `link` low half = pitch target, per point, from the Saturn
   slice under the point (banking word 16; slope word 17 or the profile's gradient, which is what the player's
   wheels feel), in 1/65536 turn with the signs of §2, clamped (the originals' maxima: 3821 pitch, 994 roll on
   Big Forest). The AI's cursor uses `link >> 16` and the heading's high half only; wrap points copy the low
   halves (`bank.py` already keeps `heading & 0xFFFF`).
2. Collision camber for the player: corner heights = profile + tan(banking) × lateral (clamped), keeping the
   centre on the profile (the `banked_height` shape, but from the slice angle, not the ground mesh whose lateral
   delta slowed the Surfers courses in Phase 9's A/B) — A/B the autopilot's forward progress on the ovals again
   before keeping it.
3. Drive proof: `attitude.lua` → a runner parser; gates: on Alpine the opponents' pitch sd > 1° and roll sd >
   0.5° with the right signs on a known climb and a known banked bend; the player's roll, once §2's trace says
   why it is flat, correlates with the banking at its position; the originals unchanged (their tables are
   untouched; the round trip is lossless).
4. Order: (a) the opponents' fields (data only, visible at once) — done; (b) the player's wheel-height trace —
   done, see §2; (c) camber in the quads — built, off by default until the player's roll path is understood.

## 4. Outcome (Phase 15, `docs/superpowers/plans/2026-10-31-phase15-attitude.md`)

- Opponents: `road.attitude_words` fills every line point's low halves (pitch = profile slope, roll = slice-normal
  camber, signs §2, clamps 3800 / 1000, no roll beyond 15 units of a lap centre); the all-course gate pins the
  clamps, neighbour jumps under 20° and at least 10 % non-zero points. Drive gates
  (`tests/test_race_build.py::test_opponents_pitch_and_lean_on_converted_courses`): on Alpine and Pacific Coast the
  opponents' pitch sd is between 1° and 8° and the roll sd over 0.5°; Big Forest's opponents unchanged (2–8°).
- Player: unchanged; `profile.cambered_height` built, off (§2).
- Open: the player's roll path; a per-course exaggeration of the pitch (Sega's ×4–8) if the geometric slope reads
  too tame in the clips.
