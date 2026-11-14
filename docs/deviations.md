# Known deviations from the Saturn courses

Decision 17 of the design: where the arcade engine cannot express something, deviate and list it here.
Status: **open** (still in the build), **fixed** (was a deviation, no longer), **by design** (will stay).

## Road and lap

- **Start line moved** (open, by design unless a course needs otherwise). The player spawns where the
  template's tables put it (Big Forest 37 units left of its road point 13; Bay Bridge and Acropolis on their
  road point 0; `place.GRID_OF_COURSE`); `convert/place.py` rotates and shifts the course so its lap passes
  there heading +z, prefers a start followed by a straight (the sixteen-car field piles up in a hairpin right
  after the grid), and keeps everything inside the ±1024 map. Phase 6, revised Phase 8.
- **Forks: the shorter branch only** (open). Where the Saturn slices fork (pit lanes, alternates), the lap is
  the shortest route back to the start line; the other branch keeps its collision quads but gets no road
  tables (no lap position, AI or heights of its own). Phase 6.
- **Road height from the profile along the lap, camber from the slice normal** (Phase 16; was "no banking", Phase 6).
  Saturn slices carry no height; the profile is the median ground-mesh height per 10 units of arc, sampled under the
  route's slice centres and (Phase 20) every 2.5 units along the route's centreline, so a centre over a hole in the
  ground no longer bends the profile: along every course the collision stays within 1.25 units of the drawn road
  (at most 5 points per course over 0.5; Diablo Canyon's first climb was 2.2 under, Pacific Coast 6.2 over). The collision's
  height function (`profile.arc_height`) takes that profile at the arc of the nearest 10-unit centreline point (the
  old 2-D projection onto lap-order neighbours stepped up to 20 units on Diablo Canyon's zigzag strips) and adds the
  slice normal's lateral slope along the centreline point's right, clamped to ±1.3 units: the player's TGP roll
  follows it (`CoursePlan.camber`, on for all seven; the Surfers forward-progress floors hold). Phase 22a: the side
  slope is the drawn road's (the ground mesh 8 units either side of the centreline, one side against the centre over a
  hole, averaged over three points and blended between them; the slice normal only where the mesh has nothing),
  clamped to ±3 units: on Surfers Road's 12.8° banking the player rolled 5° and sank into the road, now 12-14°.
  Phase 22a rework: that is only the estimate; the height is corrected to the drawn ground across the full width (the
  ground mesh every 2 units out to ±40 and every 2.5 along, followed outward from the centre at up to 45° and across up
  to 8 units of holes, never jumping to another deck; holes filled along the lap, then across). Inside a single wide
  Saturn segment the quad stays flat, so 0.4-9 % of road samples remain more than a unit off the drawn ground.
- **The opponents' attitude from the road points** (by design, Phase 15, corrected in Phase 16): an opponent's pitch
  (`+0x2a`, positive climbing) moves toward its road point's `heading` low half and its roll (`+0x2e`, negative =
  right side up) toward the `link` low half (boot `0xfece55/0xfece67`). Phase 15 wrote them into each other's halves;
  Phase 16 measured the game's own fields by tilting every Alpine quad in the ROM and swapped them back. The converter
  writes the arc profile's slope as the pitch and the slice normal's camber as the roll (averaged over three points),
  clamped to ±3800 (Big Forest's roll reaches 3821); the originals' values are authored, ours are the geometry.
- **No pit lane, no pit stops** (open). The arcade decides the pit entry from a per-slot quad index in the boot
  ROM (0xfe8e0c); converted courses set it to "none" (Bay Bridge's setting) and emit no flag-66 segments. Phase 6.
- **Pacific Coast does not order into a lap yet** (fixed, Phase 8): touching polygons count as adjacent and the
  start-line cut bridges to unreached slices.
- **Diablo Canyon needs a translation** (fixed, Phase 8: the placement step covers it).
- **The Surfers oval's infield is left out** (by design): the TRCKSPEE file carries 112 slices of an unused
  infield; the lap orders at 80 % coverage and slices the lap never reaches get no collision quads (their
  scenery stays). Phase 8.
- **Tarmac grown 4 units a side** (by design): side-by-side strips of Saturn slices leave seams (8 units on Big
  Forest's start straight) and bends leave wedges that the TGP reads as grass; verges start outside the grown
  edge. Phase 8. Since Phase 11 the tarmac is also grown or filled wherever the road's ±10 band lacks it
  (`fill_coverage`), and the verges start at the measured edge of the final tarmac (`road_verges`).

## Collision

- **One collision quad per Saturn road slice, straights merged** (by design): the arcade's 3 × 10-unit density
  would not fit the TGP ROM for seven courses; chains of up to six slices turning ≤ 3° fuse into one quad
  (`convert/collision.py`, Phase 8), and verges whose centre lies on another strip's tarmac are dropped. The
  seven courses take 892 KB of the 985 KB free. Phase 5 / 8.
- **Verges reach 40 units from the tarmac** (by design): the arcade's surface extends up to 170. Phase 5.
- **Road crossings share one height pick** (open): where a course passes over itself (Metropolis, twice) the
  TGP reports, of all quads under the car, the one whose |height| is nearest the car's; converted courses lie
  below y = 0, so the deck nearer 0 tends to win in any overlap. Verges whose centre lies on the other deck's
  tarmac are dropped (keeping them measured worse: 16 deck-height jumps against 2 in a 90 s Metropolis drive);
  a car running wide at a crossing can still be handed the other deck's height for a few frames. A positive
  height offset for converted courses plus per-deck verges is the M6 candidate. Phase 8.
- **Diablo Canyon's pit-lane wall trimmed off the lane** (by design, Pascal's decision of 14 Nov 2026, "Ok b, I follow your
  recommendation"; Phase 26 stage 4 Task 1, findings `docs/spike/2026-11-phase26-stage4-findings.md` §4). **A change to the
  normal race's collision**, not only the reverse one. One wall quad of the main road's right-side run-off wall, the step between
  centreline points 23 and 24, reached over the pit lane's west half up to its centre line (a car driving up the lane hit it in
  the stage 4 recon). Its cause: the gap-fill between drawn faces (`fill_faces`) bridged the rock at point 23 to the canyon side
  at point 28 with a straight line across the lane, and the step's centre lay on sand, so the centre-on-tarmac check kept it.
  About a quarter of its footprint stands on the tip of a drawn rock. A fenced rule (`collision.PIT_LANE_WALL_TRIMS`, Diablo's
  course key and the rectangle x −409.5..−388.0, z 31.0..43.5) replaces it by two quads (30.5 + 31.7 of its 120 square units)
  that keep every point of its footprint off the lane's tarmac walled: the end on the rock (all of the drawn rock it covered),
  the part over the sand and the edge facing the road. Only the 57.8 square units over the lane's tarmac lost their wall. Nothing
  moves nearer the road; the other six courses' collision is unchanged; the TGP reserve went from 7 651 to 7 631 words. Pascal
  was first told, wrongly, that nothing drawn stands there, and decided again with the facts. Pascal re-drives Diablo Canyon in
  the normal direction before a merge (not done yet).
- **Surface kinds: tarmac and grass only** (open): the arcade also uses 8 (kerb zone), 5 (run-off), 3 and more
  on Bay Bridge. Phase 6.

## AI and race

- **AI lines at fixed lateral offsets** (open): the arcade's seven lines are hand-made racing lines within ±13
  units of the centre; converted courses use −8, −3, 3, 8, 5, 0, −5. Phase 6.
- **The run-off is flat** (Phase 22k; Phase 22o: it follows the drawn ground within that cap, see above): a grass or wall
  quad rises at most 0.25 a unit from its inner line, whatever the
  drawn ground does (the originals' run-off is flat; the game takes a steeper slope across the car for a wall hit). Beside
  a canyon the collision lies under the drawn slope's foot.
- **Walls stand at their own drawn face** (Phase 22k): the scan's missing faces between two found ones take the line
  between them; a barrier wall run's inner line goes from one end's own lateral to the other's (the face less the
  1.5 setback, on a 1-unit grid rounded up) and breaks where the face bends more than a unit off that line, so the
  wall follows a receding rock instead of sitting at the run's nearest point. The Saturn's placed objects (group 4) count as drawn faces from 6.5 units out; nearer, over the
  road, they are ignored (Metropolis 126-128 R: a building's faces 4-6 out).
- **No tarmac sliver under a wall** (Phase 22k): a tarmac quad under 40 units whose corners all lie inside wall quads at
  its own height is dropped (the far road's slice at Metropolis's hairpin).
- **A curb at the road's edge or a prop narrows the AI lines anywhere** (Phase 22k, Pascal): their walls may stand
  inside 12.5 units with the lines scaled down to half; the terrain's other faces still narrow only at named points
  (Amazon's first corner).
- **The tarmac tiles without overlap** (Phase 22j): a tarmac quad is the Saturn slice's own polygon (no sideways growth,
  no overlap along the road); gaps beside a slice are edge strips sharing its side, holes get tight fillers, and the
  Saturn's own sub-unit holes between its slivers are closed by a fine scan. Where two tarmac quads still overlap with
  different heights (16-107 units of a lap's race line per course), the game's per-wheel pick can still step; the rest
  of the road is continuous, as the originals' is.
- **The AI lines shift onto the Saturn's own tarmac band** (Phase 22n): the arcade's lines are hand-made; ours are the
  centreline ±8, and the centreline follows the one Saturn strip the lap route takes, so where that strip is the
  road's edge one (the white-line strip at Metropolis's hairpin, the inner strip of the Oval's banking) the lines
  straddled it onto the sidewalk or the painted grass. `lane_shift` moves the seven lines sideways so their outer
  lines keep 3 units inside the slices contiguous across the road (their surface continuous within a unit at the
  joins and their place on the lap within 15 points, so another deck or a road crossing at grade stays out and the
  band ends where a crossing road's slab begins); the coverage fill follows them (not the
  centreline: the painted grass beside the route's strip is grass in the Saturn too), and nothing moves through the
  grid's zone. The wall's floor moves out with the lines on the side they move towards and comes in on the side they
  leave only at a plan's named points (Metropolis 318–356: the building's wall at its drawn face).
- **A quad's road point is the last point its front has reached, and a quad listed after one further ahead keeps
  its own** (Phase 22m): the original's quads are one road point long and centred on their points, so its segment
  array needs no rule; ours fall anywhere between the points (12–15-unit pieces near the line, merged quads of up
  to 100 units elsewhere, side strips in the Saturn's own list order). The last point is credited to the start band
  alone, as the original credits it to one quad, and the Oval's road pieces keep their own points under the apron's.
- **The verges follow the drawn ground** (Phase 22o): a verge corner takes the drawn ground's height where that ground
  continues the step's inner corner over its first two units (a bank; a deck a few units up stays out) and lies at
  most 0.7 under and 2 over the quad's edge line all the way across (a flat run-off to a hill foot keeps the profile:
  the quad's plane would float over the flat ground; a hole in the drawn mesh is skipped), held within the 22k slope
  cap, instead of the road profile's plane, which beside a banked road continued the tilt sideways under the Saturn's
  rising infield bank. A kerb lip within the first two units is still under-represented by up to 1.4 units (one plane
  per step). The verge starts from the built tarmac's own height at the measured edge (the quads follow the drawn
  surface across their width; the profile under-read the Oval's first banked curve by 1.5 at the edge, and the wall
  strip lay a step below the road), and a bank steeper than the cap is climbed at the cap: the verge stays under the
  drawn ground there by the difference (the Oval's first curve: 2.3 under at the wall's far edge).
- **Median walls** (Phase 22p): a drawn barrier standing between two tarmac strips (Metropolis's pit wall, points
  50-61 R: a 4-unit block, no ground between its rails) gets a wall strip over its footprint at the road's height, the
  fills leave the footprint open and the AI lines narrow to half beside it; the originals have no such median.
- **A placed object standing in the drawn road makes no wall and trims nothing** (Phase 22p): a prop face with drawn
  road of the race's colour beyond it (Metropolis's pit fence start post, 7.5 R at point 49, the mouth to 20.5 beyond) is
  ignored; the car drives through that post. A prop with grass beyond it keeps its face (Amazon's curbs and posts).
- **The clock on Metropolis and Pacific Coast** (Phase 22p): their checkpoint extensions are scaled by 1.15 (the race
  test's autopilot ended its 150-s race with 2 and 4 s left there, 10-20 s elsewhere); a playtesting knob, open.
- **A ranking table per course** (Phase 22r): the game keeps three best-time tables (one per original course); the seven
  converted courses have their own in battery RAM, initialised by the game's own routine from their race records (the
  first default time rounded up to the minute from the race's clock budget). A battery RAM from before this phase is
  re-initialised once (a new S-RAM magic): the originals' tables return to their defaults.
- **No grid boards** (Phase 22q): the host's grid-boards entity, which draws the row of country flags along the start
  straight, is left out of every converted course (the Saturn's courses have no such flags); the start lights and the
  grid girl are the program's own and stay.
- **One START arch where the lap starts at the Saturn's gate** (Phase 22o): the host's start gantry, re-placed at road
  point 0 since Phase 9, is left out on the courses whose Saturn START gate stands within 8 road points of the line.
- **The lap starts at the Saturn's START gate where it fits** (Phase 22l): Amazon Falls and Metropolis at it, the
  Surfers Oval 50 units after it, Surfers Road 60 (the road at the flag itself reaches 992 of the map's 970); Alpine
  and Pacific Coast cannot (1202, 1139) and start where the arcade's grid pose fits best, as Phase 6 placed every course.
- **Diablo Canyon placed around its pit lane** (Phase 22f): the arcade's PIT START spawn is an absolute place, so
  Diablo is placed with it in its pit lane and the lap starts on the main road at the pit lane's mouth. Phase 22n: the
  spawn 40 units in (`PitLane.spawn_depth`; the pit box keeps its 130) lets the course turn 0.55 of the way towards
  the pit straight, so the spawn faces 16 degrees off it (Phase 22f: 130 units in, a fifth of the way, 30 degrees;
  further, the loop's far end or a canyon rock beside it leaves the map). Phase 22i: driving into any course's pit lane forces a pit stop as on the originals: the game's
  autopilot takes the car from the trigger quad (40-185 units into the lane, where a quad pair spans the tarmac across
  it) to the course's own box (`collision.pit_box`, mid-lane and at least 130 units in; Diablo's is its spawn) and parks
  it facing down the lane; the crew stands at the game's fixed world-axis offsets around the box.
- **Pit stops in a reverse race; the crew turned half a turn** (by design, Pascal's decisions of 14 Nov 2026, P1 and P2: the lead's reading of their "Ok" to a table of six
  recommendations; Phase 26
  stage 4, findings `docs/spike/2026-11-phase26-stage4-findings.md`). The arcade has no reverse race. In a reverse race the car
  enters the pit lane at its normal exit, the game's pit sequence drives it backwards up the lane to the normal box (Metropolis:
  a box 40.7 units deeper, in the tunnel), parks it facing the reverse way, and the player drives out through the normal mouth.
  The game places its crew at fixed world-axis offsets from the box, for a car facing +z; in a reverse race the car faces the
  other way, so the crew is reflected through the box and each figure turned half a turn, and its animation's world-axis motion
  is mirrored (`direction.crewturn`, `figmirror`): it stands round the car as in a normal stop. On Alpine, Pacific Coast and
  Diablo Canyon, whose boxes do not face +z, the crew stays turned about the car in reverse as it is in their normal race (open
  in both directions, `docs/follow-ups.md`). A normal race's crew, the attract mode's pit scene and Alpine's PIT START keep the
  game's placement (the direction flag is 0 there). Where PIT WORK fires in reverse (the variant's pit quad) was chosen by the
  session lead's rules, not by Pascal: in the headless runs the quad that fired has its centre 12 to 141 units into the lane
  from the normal exit, measured along the lane.
- **Four checkpoints per lap on the converted courses** (Phase 22e, Pascal's choice): the start line plus the
  Saturn's own three gates (its START/GOAL and two C.P.), where the arcade's courses have the start line plus two.
  The arcade's start line is not the Saturn's (the absolute grid decides it), so the Saturn's START gate is a
  checkpoint mid-lap; the host's C.P. gantries are left out.
- **AI lines narrowed at Amazon's first corner only** (Phase 22c, Pascal's drives p22play29–32): the corner's curbs
  stand 9–11 units out, inside the walls' 12.5 floor, so a car ran over them. At centreline points 29–68
  (`CoursePlan.lane_points`) the lines narrow (down to half their offsets, tapering over 10 points) and the walls,
  grass and tarmac trim may come in to the curb. A course-wide version pulled Diablo's walls in to its white lines
  (early impacts); nothing narrows anywhere else, and a test pins the named points.
- **Seven of the fifteen opponents never raced** (fixed, Phase 9): the pointer block of a converted bank held five
  line pairs where the car setup reads eight, so the cars on AI lines 5–7 spawned at the world origin and the
  field "piled up" / crawled (leader 14 units/s against 75 on Big Forest). Eight pairs now
  (`course.LINE_COUNT`, `blob.build_course_blob`, `bank.build_bank`); the race gate checks that no opponent sits
  at the origin and reports the leader's progress.
- **The opponents did not drive on generated tables** (improved, Phase 10, `docs/spike/2026-11-opponents.md`): an
  opponent's line cursor advances only while the segment named by the line point has a road point the car has
  reached (formats §15); our tables named a segment ahead and credited merged quads at their centre. Now the end
  slices stay unmerged, the first and last segments are pinned to road points 0 and n−1, every point names the
  segment with the greatest road point at or before it and every quad is credited with the last road point its
  front has reached (Phase 22m; Phase 10 took the point nearest the front, which gave the quad before the start
  band the last point and doubled the wrapped cursor's run-on). The field moves on every course (9–15
  of 15 cars gain 100 road points or more; the leader gains 200–600 road points in 150 s against the original
  Big Forest's 877, a third to a half of the originals' pace).
- **Opponents parked on the road for good** (fixed, Phase 11, `docs/spike/2026-11-field-coverage.md`): two
  converter defects — tarmac quads that did not reach the AI lines off the centreline (triangles, slivers, merged
  bends), and verges lying across the road (a triangle slice's quad has a diagonal "side"; the originals' verges
  never overlap their tarmac) on which the TGP kept any car that had touched them. The tarmac is now grown or
  filled across the road's ±10 band and the verges are built from the road's measured edge. 150 s races: no car
  parked on any course (Phase 10: 4–13), every field 15 / 15 moving, the opponents at 85–100 % of the
  originals' speed in units per second (the road-point rates differ by the point spacing).
- **A start-line band across the road** (by design, Phase 11): one tarmac quad from 10 units before the line to
  10 past it, credited the last road point and alone under the car there (its neighbours are cut back to it), so
  that every car crossing the line is certain of the last point before its road point wraps — the opponent cursor
  compares road points as plain numbers (formats §15) and a car credited 0 straight from 450 parks for good
  (Diablo Canyon, three cars, found by the Phase 11 review). The originals' 10-unit quads never let a car skip a
  point. Phase 11.
- **Verges from the road's measured edge** (by design, Phase 11): one 40-unit quad per 10-unit step on each
  side (runs fuse on straights), at the tarmac's edge height, 0.3 away from zero; inside a tight bend a step is
  the convex hull of its crossing laterals (verges overlap there), outside one a wedge of run-off beyond the
  neighbouring steps stays bare (0.2–1.4 % of samples at lateral 12–40; the originals leave 22–34 % bare). A
  car over no quad gets height 0 from the TGP for that frame.
- **The field starts single file on the Bay Bridge / Acropolis templates and drives fixed-offset lines**
  (open, playtest): the game lines those fields up single file *in front of* the player (road points 1–15, the
  player at 0), slowest car first — the original Bay Bridge does the same; our AI lines are lateral offsets of
  the centreline, not hand-made racing lines, and the originals' lane groups (formats §16) are not generated.
  The opponents' speed is at parity with the originals' (Phase 11); "average difficulty" is for the playtest.
- **One segment per tarmac quad** (by design): the arcade packs about three per road point; the game only needs
  the quad → road point map. Phase 6.
- **The Surfers Oval runs wide onto its inner verge at speed** (open, improved by Phase 16's camber): with the banking
  dropped the autopilot drifted to the inner verge at speed; Phase 16 tilts the quads by the slice camber and the
  forward-progress floors of the Phase 9 A/B hold. Phase 8.
- **Checkpoints, time limits and opponent placement were the template's** (fixed, Phase 9): every converted course
  carries its own race blob (`arcade/race.py`, `convert/race.py`): two checkpoints at thirds of its lap (the
  arcade's are hand-placed), checkpoint extensions = the template's scaled by the sector length in road points
  (clamped 200..1200 clock units), the template's initial clock, a copy of the arcade car table with the opponents'
  performance scaled by a per-course `pace` (1.0 today) and `laps` = 5. Knobs per course in
  `tencourse.COURSES` (`laps`, `time_factor`, `pace`) for playtesting (design decision 11).
- **One car table for both operator modes** (by design, Phase 9): the arcade's alternate table (`0xfcd195`,
  operator flag `0x40dc8c`) differs in car bodies and line pairing; converted courses serve the normal table in
  both modes. Their time records do cover all three variants (normal / operator flag / linked).
- **Pacific Coast and Surfers Road crashed ~35 s in** (fixed for Pacific Coast, Phase 9: it was Bay Bridge's
  trackside props standing on the converted road; see "Trackside entities" below. Surfers Road's losses are
  collision-side: see the Phase 9 write-up).

## Packaging

- **The European Saturn disc only** (by design, Phase 12): `vrtools check` reads `VRSRCDIR/TRACKS00/<course>`
  from the data track named by the `.cue`; another region's disc, or a `.bin` not beside its `.cue`, is refused
  with the missing file named. Untested elsewhere.
- **The smoke test needs `mame` on `PATH`** (by design): `vrtools build --smoke` reports it skipped otherwise and
  the build succeeds; the set is then checked only by running it yourself.
- **Playtest knobs are command-line options, not a saved profile** (by design): `--tune` per course per build;
  the defaults are the shipped balance (5 laps, extensions by sector length, the original performance table).

## Scenery and presentation

- **All the Saturn's scenery layers** (fixed, Phase 18): groups 0-3 are layers of one picture, not alternates
  (`docs/spike/2026-11-phase18-scenery-recon.md` §1): 0 road and ground, 1 terrain, 2 road paint, 3 structures; 4 the
  props. Every course draws all five, every polygon of each. Polygons that share an edge are chained (one record each),
  and the scenery uses the erased tail of every 2 MB polygon-ROM chip (3 759 KB; 708 KB left after the build). The
  backdrop is still the host's (Phase 18b).
- **Large ground quads can occlude the car** (fixed, Phase 14): not their size — the polygon records' z mode.
  The originals' ground polygons sort at their farthest depth (flag bits 10–11 = 2) and the cars at their nearest
  (1); ours were mode 0 ("keep the old z") and a ground quad under the car kept the previous polygon's depth. Every
  converted quad now carries mode 2 (`polyrom.Z_MODE_MAX`); the car is drawn throughout the captures.
- **The course edges: grass, then a wall** (Phase 16): the game's wall is a surface kind — a quad whose surface byte
  is 5 slows a car that touches it (the wheel kinds `+0x142..148` are `1 << surface`: 0x20 at Big Forest's wall). The
  verges are 30 units of grass past the road's measured edge (`VERGE_GRASS`) and a 6-unit strip of surface-5 quads
  beyond (`WALL_WIDTH`, fused more coarsely than the grass to fit the TGP windows: runs of 12 steps through 8°); a wall
  quad over tarmac or within 3 units of the centreline or an AI line is dropped. A surface-5 quad slows and scrapes a
  car (measured 77 → 25 units/s) rather than stopping it dead. Phase 17: the grass starts a unit inside the run's
  narrowest edge (never inside 8.5 units, the AI lines' reach), so where the road widens inside a run the grass lies
  under the tarmac beside it, and grass over a side strip at the road's level is kept: on side areas (pits, start
  areas) up to 30-35 units of tarmac have grass under them (Diablo point 30, Amazon 2.5, Metropolis 289). The TGP keeps
  the tarmac for a car that arrives on the road, but a player who touched the grass keeps the grass's grip across such
  an area until it leaves it; no AI line is ever over grass. The wall strip overlaps the grass by
  2.5 units. No collision-free gap a unit or wider starts within 10.5 units of the centreline; 20 remain beyond it
  over the seven courses (17 on Metropolis, beside its wide areas and crossing decks, whose grass stays dropped).
  Phase 19: where the Saturn's water (its pure blue-cyan ground and terrain faces) lies inside those 30 units, the grass
  stops at the water and the wall stands at the shoreline, never inside 12.5 units of the centreline (the racing lines'
  clearance; where the water starts closer, a car can reach a band of at most 1.5 units of it). A shoreline wall
  follows the road's edge (its run breaks where the edge moves half a unit, at the points and halfway between them) and
  starts just outside the tarmac; beside Pacific Coast's jagged side areas a few wall corners still reach up to 1 unit
  (the edge scan's resolution) into the tarmac, and beside side areas wider than the 40.5-unit edge scan (Surfers Oval
  10-16, Surfers Road 141-145) walls stand on the side area's outer tarmac, as elsewhere since Phase 16. Walls are kept
  only where no point of the racing lines, sampled every unit, comes within 3 units of them (grass over tarmac keeps the
  10-unit samples). The cost: 27 085 TGP words left, under the former 30 000 reserve (now 25 000). The off-course
  put-back after 40 logic frames (Phase 14) stays (Phase 22a: 128, as the originals). Phase 22a (Pascal: "the car is able to go outside the wall"; "the
  rocks should stop the car"): the Saturn draws its cliffs, rocks, rails and fences 10-25 units from the centre,
  inside the 30 units of grass, and a wall at the ground's height only slowed a car (the game's wall is a step in the
  collision height: `docs/formats/model1-course-tables.md` §5). The wall now stands at the drawn scenery and is a
  step: the first face that a line at the car's body (the collision + 1) meets going outward — any non-water face of
  the terrain and structures (groups 1 and 3), a face steeper than 45° of the ground and paint groups (0 and 2, which
  also hold cliff faces), or a vertical rail met at 0.5 (Diablo 246-248: 0.7 tall) — median of five points, so a lone
  tree is no wall; the wall starts 1.5 units inside it (half a car) and never inside 12.5, the grass meets it with
  half a unit of overlap, and the strip is 12 units wide and lay 4 units off the ground's height (away from zero; Phase 22c:
  back at the ground's height, as the originals' walls measured on Big Forest, once nothing lies under a wall), so
  the first wheel on it trips the game's step check: the car is deflected along the wall, spins and, fast enough,
  crashes, as on Big Forest. Where the Saturn's road slice reaches past the drawn face (Diablo's start and canyon
  sides) the tarmac is cut back to it. Measured: a full-lock steer into Diablo's first two right turns stops 23 and 18
  units out (it reached 58, past the wall, and fell through a hole in the run-off before); Pascal's replay at the
  first right turn: deflected and slid along the wall where the car had crossed it. Then (Pascal's p22play17-21
  drives): a wall quad steps one way (`_wall_step`), grass and tarmac end at the wall's inner edge where all they lose
  lies under it (`clip_at_walls`), consecutive runs meet at the nearer inner corner (`_join_wall_runs`), a drawn
  barrier's wall takes its own point's width and a run its nearest point's edge + width, and a long run near the AI
  lines is split, not dropped; the off-course put-back is the originals' 128 counts (4.3 s, measured on Big Forest).
  Left: a run sits at its nearest point's lateral, so where the rock curves away (Diablo 91-97) the wall stands up
  to 5 units before it, and where the rock is nearer than 12.5 (Diablo 321-327, 8.5) the wall stays at 12.5.
  The run-off's holes and seams per course are measured limits in the tests (no wall is reverted to make them pass).
- **The HUD map shifted on anticlockwise courses** (by design, Phase 14): the map is car-centred and heading-up at a
  fixed 1/1250 scale with the player's cross drawn as a fixed 3×3 tile block, so a course whose interior lies on
  the car's left hangs its outline into the middle of the screen. Alpine and Pacific Coast (positive centreline
  area) move the map section's screen translate (`0x50231c`, the game's boot-time RAM copy of its record) from
  149 to 237 and the cross 11 cells right through a 7-byte boot ROM patch (`jsr` to the directory's `cross`
  routine: R1 = 0x700ae0 + [0x502328]); the originals and the five clockwise courses keep 149 / 0. A per-course
  map scale is not done (the 0.0008 is an immediate in several routines).
- **The HUD map's outline follows the road's height** (by design, Phase 25): the originals' outlines are flat, far
  under their roads; a converted course's lies 1 unit under its road all the way round, since a marker is hidden
  where its car is lower than the outline.
- **The select pictures are generated** (Phase 21): the Saturn has no top-down pictures, and its course data holds
  only a band about 60 units either side of the road; a converted course's picture is a generated low-polygon landscape
  coloured from its own terrain (seeded noise, deterministic), with its Saturn water and exact road, quantised to three
  16-colour palettes and at most 320 characters. Its 'not chosen' grey set maps each palette's luminance onto levels
  10-22 as the originals' hand-made greys span. The originals' pictures are untouched (copied from their own ROM data).
- **The backdrop is the course's own, quantised** (Phase 18b): the Saturn's 1280×256 256-colour panorama (`BGS*1`, the
  Oval shows Surfers Paradise's) is resampled to the arcade's 2048 px per turn (×1.6) and fitted vertically to the band
  (the Saturn's picture top to the band's top, its horizon to the arcade's: ×1.46, ~9 % flatter than its aspect), then
  quantised to 32 sixteen-colour palettes and ≤ 2 600 tiles. The 48 pixels above the band are one flat colour (the
  arcade's layer 3, filled from the panorama's first entry: the Saturn's top-of-screen sky); Phase 25: the band's first 8 pixels are
  that colour and the picture fades in under it over 48, so the top of the Saturn's sky is paler than its own. A boot ROM routine (`gfx`) makes the
  game read the course header's own directory (it read the bank's original header). Music is still the host bank's
  (open): Alpine Big Forest's, Amazon Falls, Pacific Coast and both Surfers courses Bay Bridge's, Diablo Canyon and
  Metropolis Acropolis's. Phase 7 / 8 / 18b.
- **Trackside entities: the host's race furniture re-placed, its props dropped** (by design, Phase 9): the
  entity spawn list of a converted course (`arcade/spawn.py`) holds the HUD minimap, the start gantry and the
  numbered grid boards at the same road-relative spots they have on the host (signed road point from the start
  line, lateral, yaw against the road, height from the road profile) and the two checkpoint gantries at the
  converted checkpoints; the host's barriers, boards, buildings and bridge pieces are gone (they stood on the
  converted road: Pacific Coast stopped dead against Bay Bridge's board row). Saturn scenery already carries the
  course's own trackside objects.
- **Select panels are generated** (by design, Pascal 2026-10-30): stylised loop (48 points, corner-cut, 3-px
  stroke), flat host colour, start mark, name in a small plain font; the BEGINNER / MEDIUM / EXPERT labels stay
  per slot, not per entry (open). Phase 7.
- **Entries 4–9 are placeholders** (fixed, Phase 8: all seven courses are converted).
- **Scenery thinning per course** (by design, unused): `convert_tiles(thin, keep_near)` drops small quads far
  from the road for the render rate, and `CoursePlan.terrain_thin` the small terrain beyond 60 units (Phase 18); no
  course needs either (28–29 switches / 57 frames everywhere with all five layers). Its keep rule
  is the quad centre's distance to the centreline points (40 units); before the first course that needs
  thinning it should also keep the ground quads the road profile sampled and measure polygon-to-road distance
  (Phase 8 review). Phase 8.
- **Diablo Canyon's road and ground read yellow over blue** (open): the host palette's nearest colours. Phase 8.
- **Attract rotation and linked play may show a converted course** (open): a course load uses the menu entry
  when its template equals the data index the game set; after someone played a converted entry whose template
  is Big Forest, the attract's Big Forest turn (or a linked master's Big Forest) runs that entry until the next
  free selection. Operator fixed-course settings and fresh boots load the originals. Phase 7.
- **Race-start music follows the template** for converted courses (open until per-course music is decided). Phase 7.
- **Flat colours, no textures** (by design): nearest course-palette entry per face. Phase 4.
- **The road is darker than the Saturn's** (by design, Phase 24): the ground layer's neutral greys are mapped down
  to the arcade's own road levels (`geometry.ROAD_GREYS`: 64 → 56, 80 → 72, 88 → 80, 104 → 88, 120 → 104; Big
  Forest's Saturn road lands on the arcade Big Forest's mean), since the arcade lights its palette on top and the
  Saturn shows its greys unlit. The Saturn's tile-to-tile shade pattern is kept; buildings and props keep their greys.
  On screen the converted roads are still about 10 lighter than the originals'.
- **The run-off is level with the road** (by design, Phase 24): the grass, snow and sand beside the road start at
  the road edge's height (the originals' run-off is level; ours sat 0.3 off until Phase 24 and leaned the car).
- **The gates' lettering reads from both sides: mirrored lettering copies** (by design, Pascal after the stage 2 drive,
  "go with C"; Phase 26 stage 2, findings §11.2). On every Saturn gate of the converted courses (START and C.P.) the
  lettering faces, which the conversion drew two-sided before, are drawn one-sided, and each gets a copy mirrored behind the
  banner (`gates.gate_lettering`, `gates.lettered_quads`), one-sided the other way: the letters read correctly from either
  side, in both directions. The Saturn draws them from the front only. Only the 21 cells holding gate lettering
  change (collision byte-identical); the copies are lit as back-facing faces, so from behind the red follows the banner's
  back lighting. In the normal direction it shows on Alpine and Pacific Coast, whose gates' lettered front faces the
  reverse driver: there a normal race used to show the letters mirrored (seen from behind) and now shows the readable
  copies. On the other five courses the normal driver sees the letters' own front, as before. The copies add records to
  the frame's record budget (0x5011b0, 5 500; findings §11.7) in the normal direction too: 14 per C.P. gate and 28 per
  START gate in view. Measured on normal Diablo Canyon against stage 1's playtest set: +14 on the frames that already
  passed the budget there (the same 10 frames, the same objects drawn); over the run 0, 14, 28, 46 or 60 on a drawn
  frame, the gantry's copies included.
- **The converted courses' own start gantry frames** (by design, Pascal after the stage 2 drive, option "B"; Phase 26
  stage 2, findings §11.6). Where a converted course keeps the arcade's waving start gantry at its line (Alpine, Diablo
  Canyon, Pacific Coast), its entity names a copy of the gantry's 32 animated frames (`arcade/gantry.py`, list at
  0x28f970 on the stage 2 set) instead of the arcade's list 0xfdc033: each frame is the arcade's records unchanged, then the
  "START" letters mirrored one-sided behind that frame's banner, so it reads from behind in reverse. The entity's
  object-list word changes in the normal direction too; the normal view is the arcade's frame (Alpine measured: 0 pixels
  differ). The 32 objects (241 408 bytes) and the list sit on erased ROM; the arcade's own frames, its list and the
  originals' spawn lists keep their bytes. Each frame adds 46 records to the frame's record budget (findings §11.7)
  while the gantry is drawn, in the normal direction too (measured on normal Diablo Canyon against stage 1's playtest
  set: the count higher by 46 or 60 on some frames, inferred to be the gantry's copies; the objects emitted the same on
  every frame).
- **The course's name in the race HUD** (by design, Pascal's request of 13 Nov, decisions H1-H4; Phase 26 stage 3, findings
  `docs/spike/2026-11-phase26-stage3-findings.md` §5). The arcade's race HUD prints the host template's level word (BEGINNER /
  MEDIUM / EXPERT, by data index) at the bottom right; on a converted course that word was the host's, not the course's (MEDIUM on
  Pacific Coast, Bay Bridge's). On the seven converted courses the label reads the course's name instead (`hudname`, boot site
  0xff4799), right-aligned to the word's last column (58), in the colour of the level the select screen shows for the entry (blue
  BEGINNER, orange MEDIUM, red EXPERT), the same in reverse. The three originals keep the game's word. It changes a normal race
  on the converted courses: nothing else of the race differs from main's (findings §6). A linked slave cabinet's HUD (0xff53ae)
  still shows the template's word.
- **The COURSE DIRECTION screen** (by design, Pascal's request and chosen layout, design §2 item 3; Phase 26 stage 3). On the seven
  converted courses the course select's lock leads to a second screen inside the select mode, where the wheel chooses NORMAL or
  REVERSE and the gas (or a 10-s countdown) confirms; the race then loads with the game's own lock-to-load timing. Its title,
  labels and panels are the game's lettering and maps, its two ring arrows and the SELECT DIRECTION caption are drawn by the
  converter. On those courses the course select's own lock look (the chosen picture in colour, the others grey) is replaced by the
  screen's (D7). The arcade has no such screen; the originals, linked play and the operator's fixed course keep the game's flow.
  A reverse race records no best time and asks for no name (the flow of a race without a record).
