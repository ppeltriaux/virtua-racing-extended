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
- **Two far buildings on Metropolis are drawn from two cell rows further away** (Phase 31; Pascal after one 107-s run of the prototype: "yes it s good keep it"; merged 15 Nov on their
  "Yes all your recommendation"). The arcade draws a cell's scenery when the camera is within two
  cells of it; the buildings at the far end of Metropolis's long straight are also stored in two nearer cells, so they are on
  screen before their own cells are drawn (and drawn twice while both are; where two of the tall block's walls tie in depth the
  front one is then drawn, one grey step lighter than the hidden one main draws there). Scenery only; the collision and the race
  are main's.
  `docs/spike/2026-11-phase31-far-silhouette-findings.md`.
- **The frame's draw budget is 10 500 records, not 5 500** (by Pascal's choice, Phase 28: "3 first", then "Ok" to the session
  lead's recommendation of 10 500). The arcade counts the polygon records it sends in a frame and skips every object list it
  reaches once the count is past its budget; the scenery cells come last, so on a busy frame the far cells drop out for that frame
  (far pop-in). Sega's own courses passed 5 500 on 3-22 % of race frames. At 10 500 no measured frame of any course, pit stop or
  attract scene skips a list (the highest need measured, 9 771, on Big Forest), so **the three original courses now draw far
  scenery that the real arcade dropped on busy frames**, and the converted courses' start-line skips (Diablo Canyon, Metropolis,
  Pacific Coast) are gone. In MAME the game's rate holds (one picture every second frame, the overrun counter still, the V60 at
  most 14.6 ms of its 34.77 ms in races and 18.0 ms in the attract's scenes), and the game's state at the end of every logic pass
  is main's, measured on Big Forest, Acropolis and Metropolis with the same inputs and the same battery RAM. A linked cabinet's
  budget (the game's 5 000) is raised by the same 5 000 to 10 000; linked play was not run. **Real hardware is untested:** MAME
  does not model the render board's time and the game does not wait for the renderer, and Sega's 5 500 may match what the
  renderer can draw in a picture, so on a real board this change might cost pictures; the set is for MAME.
  `docs/spike/2026-11-phase28-draw-budget-findings.md`.
- **Arcade trees on Alpine: objects the Saturn course never had** (Phase 29; Pascal after one 110-s run of the prototype: "i think it s good"; later the same day: "Keep the trees"; merged 15 Nov on their "Yes all your recommendation").
  21 copies of Big Forest's tree (a 4-face canopy on a 3-face trunk, read from the user's own polygon ROM at build time, its own
  palette colours) are baked into four of Alpine's scenery cells beside road points 406-449: on the snow crests left of 406-408
  and 439-449 and on the flat ground right of 448-449, each with its foot at least 10 units outside every collision quad (the canopy reaches 5.1 from the foot; drawn only: the
  collision is byte for byte main's). The three original courses are byte for byte the same, in place; the six other converted
  courses have every cell object and colour word identical in content but relocated (Alpine grows ahead of them), so their tile
  tables, colour entries and reverse-annex addresses differ. The copies are not record for record the arcade's (type-1 records
  with a repeated corner where four source faces are triangle records; the source's flag bits 23 and 24 clear); real hardware
  untested. The Saturn's Alpine has no such trees; the tree is 16.35 units tall and Alpine's own pines 30-120, about 2 to 7
  times taller.
  `docs/spike/2026-11-phase29-alpine-trees-findings.md`.
- **The word REVERSE in the race HUD** (Phase 32; Pascal: "One additional idea, when playing a track in reverse it could have the
  word "reverse" under the track name(maybe in a neon red style?)", then "Ok maybe just a shadows reverse then", then, shown
  three stills, "Yes all your recommendation" to red on every course and the placement as built; merged 16 Nov on their "Yes to all"; after a later run of a set with it: "reverse word was good also on the normal tracks"). The
  arcade shows no such word (it has no reverse races). In a reverse race on a converted course the HUD shows REVERSE under the
  course's name, on the screen's last two tile rows (rows 46-47, columns 52-58), in the game's own 8 x 16 font and its EXPERT red,
  with the font's own black outline. A normal race and the three originals show what they showed (the tile RAM byte-identical
  to main's set at the same frames). A real monitor's overscan on those last rows is untested.
  `docs/spike/2026-11-phase32-hud-reverse-findings.md`.
- **Thirteen more palms on Surfers Road than the Saturn course has** (Phase 34; merged 16 Nov on Pascal's "merge update md commit and push"; Pascal, 16 Nov, after one 28-s run of the set `out/p34play3`: "those ones are great keep saturn"; after one 94-s run of the final set `out/p34play4`, asked how the palms looked: "look good", then "palm").
  They are copies of the Saturn course's own roadside palm (the one at road point 47: its 28 faces and its colours as this course
  converts them, 11.4 units tall, nothing scaled), baked into four of Surfers Road's scenery cells right of road points 25-93:
  three on the sand slope at 25-28, two at 75-77 and a row of eight on the grass at 82-93, where the Saturn has bare ground. Each
  stands with its foot at least 10 units, and every leaf corner more than 5, outside every collision quad: drawn only (the
  collision is byte for byte main's; a car cannot reach one). The three originals and the six other converted courses are the
  same in content (Metropolis's two far-copy cells and Surfers Road's later data are stored elsewhere). Nothing is borrowed from an
  arcade course: Bay Bridge's small palm was tried at these sites first, at the arcade's size and scaled 3.0, and not kept.
  Real hardware untested.
  `docs/spike/2026-11-phase34-surfers-palms-findings.md`.
- **The arcade's tunnel sound in three covered stretches** (Phase 37; merged 16 Nov on Pascal's "merge update md commit and push"; of it they have heard Alpine's tunnel in one 53-s run, 16 Nov: "tunnel sound is
  good, launch the game again i want to test something" and, after a run through Bay Bridge's own tunnel, "ok tunnel is validated"
  (Metropolis's stretches, reverse and the pit stop not driven by them); branch `phase37-tunnel-sound`, not merged). In Alpine's mountain tunnel (road points 108-146) and on
  Metropolis under the roof beside the pit lane (50-62, the lane's quads under it included) and in its long tunnel (251-311),
  in both directions, the player's engine sounds as it does in Bay Bridge's tunnel on the arcade: the game's own flag (bit 7 of
  the segment flag) set on those tarmac quads, the game's own commands (`C201` / `C200`), the sound board's own mix. Whether the
  Saturn game changes its sound there is not known, so this may be something the Saturn courses do not have. The stretches are
  the ones Pascal agreed to on 16 Nov ("Yes to all", to the recon's questions as put to them), which were put to them as
  Alpine 106-145 and Metropolis 245-313 and 50-62 (the recon's driven samples) and are built as 108-146, 251-311 and 50-62 (the
  quads whose centre is under the drawn roof: the same places); two Metropolis underpasses (176-178, 186-191) were not in the
  list they answered, were put to them separately with a recommendation to leave both out ("yes correct") and are not flagged; the arches, bridges, gates and
  Metropolis's building before the line have none. The three originals are untouched. Nothing else of the set differs from
  main's (196 flag bytes). `docs/spike/2026-11-phase37-tunnel-sound-findings.md`.
- **The three original courses can be raced in reverse** (a prototype on branch `phase33-originals-reverse`; Pascal's
  request of 15 Nov: "We also need to do the reverse for the three initial tracks"; they drove stage 1 on 16 Nov: "reverse on
  original track is good but: - some checkpoint flags are white without the C.P. the pit isnt working. relaunch", then "reverse is not
  showing in the reverse track during gameplay, relaunch"; stage 2 answers those three; they drove it the same day: "1)fixed. 2)
  working. 3) looks good nice 5) single file doesnt bother me for beach i need a relaunch to try again 5) another relaunch",
  and of a normal race on an original "normal race look fine". Where the list below
  says no pit stop, blank C.P. banners and the level word alone, the stage 2 paragraph after it holds). The arcade has
  no reverse race. What the build changes for Big Forest, Bay Bridge and Acropolis:
  - **In the normal direction: one thing.** After the course is confirmed on the course select, the COURSE DIRECTION screen now
    appears for an original as it does for the seven (a second press of the gas, or its ten-second countdown, which takes
    NORMAL). The race that follows is the arcade's: the same bytes of course data (the data banks' original content, the tile
    tables, spawn lists, polygon and TGP ROMs are not written), and, fed the same inputs from the same battery RAM, the same
    game state at the end of every logic pass as the build before it (measured on all three, 120 s each). In linked play, with
    the operator's fixed course and in the attract mode the screen does not appear and nothing changes.
  - **A reverse race on an original**, against the quality of its normal race: no pit stop (the pit lane is plain road; pit
    stops in reverse are a later stage); no best time is recorded and no name asked (the battery RAM has no room for three more
    tables; **since Phase 35 a reverse race on an original keeps four best times, see the entry below**); **Bay Bridge's fifteen opponents all follow the centreline** (a stopgap: data bank 1 has room for one reversed
    line, not eight); Big Forest's opponents use six of its eight lines (the two innermost left a bend onto the verge every
    lap); the grid is not the game's (Bay Bridge and Acropolis: the cars two road points apart, the grid twice as long; Big
    Forest: another order at the front), because on the game's grid 3 to 10 cars stood turned 25-56 degrees; Big Forest starts
    on the grid with the READY lights, not with the pit crew; the C.P. banners are blank white from behind (START reads
    from behind, by the converted courses' both-sided frames); the arrow boards (Big Forest 4, Bay Bridge 10) are not there
    (Pascal: removed in reverse). The HUD's label is the game's
    level word and the HUD map is where the game draws it, as in the normal race.
  - **Stage 2 (16 Nov)**: in a reverse race on an original the six checkpoint banners read "C.P." from behind (lettering
    mirrored behind the banner, in the reverse race's own object lists; the normal race's banners are the arcade's); Big
    Forest and Acropolis have a pit stop in reverse: entered by the normal race's pit exit, at the end of the reverse lap just
    before the line, the car and the crew turned half round on the arcade's own box, the same two stops, PIT WORK and time on
    the box as the normal stop (Bay Bridge has no pit lane in the arcade); the HUD shows REVERSE in red under the arcade's level
    word, ending under its last visible letter (one cell further left under MEDIUM and EXPERT than under BEGINNER and the
    seven's names). The grids, Big Forest's six lines and the HUD map's place stay as built (Pascal: "Yes to all").
  - **Fix wave (16 Nov)**: on the COURSE DIRECTION screen an original's picture is the course select's own two-layer picture,
    pixel for pixel, under the arrows (stages 1 and 2 drew its front layer alone: flat cyan or magenta where the water, the
    track and the name belong; Pascal: "the colors in the track select looks bugged with ping highlighted on the track").
  - **Second fix wave (16 Nov)**: in a reverse race on an original the game does not put a car back onto fifteen quads whose
    centre faces a wall or a barrier within 25 units (Bay Bridge's last three before the fork's divider among them; Pascal:
    "it did put me back on bay bridge after a while but i ended up right in an obstacle."): it is put back on the quad before,
    and the off-course counter runs while a car is on one of them (the longest such stretch: six road points of one lane on
    Acropolis, about 63 units). A car that never steers after the put-back before Bay Bridge's fork drives into the divider's
    nose 28 units on and is put back again, about every 8 s. The arcade's own normal direction has such spots and keeps
    them.
  `docs/spike/2026-11-phase33-originals-reverse-findings.md`.
- **Best-time tables for reverse races on the three originals** (Phase 35; merged 17 Nov on Pascal's "merge upadte md commit and push";
  not driven by them). Pascal's words: 15 Nov, to a list including "best times three per table on all ten
  reverse courses": "Yes all your recommendation"; 16 Nov, to five recommendations (four times a table on all ten; the level
  word in the title; each original's reverse page straight after its own normal ranking page; the seven's rule for the starting
  times; the same release as the originals in reverse) and the condition that four entries depends on a check of every
  test-menu page (passed, recon §11): "yes to all"; 17 Nov, asked whether to release v0.3 without them: "Release with the
  original best time", then "Version 0.3". The arcade has no reverse race and no reverse table. What the build adds:
  - a reverse race on Big Forest, Bay Bridge or Acropolis that finishes at or under its table's fourth time is inserted in a
    4-entry table of its own and asks for a name, exactly as on the seven converted courses (Phase 33's `rankgate3`, which made
    such a race record nothing, is gone; the race end's boot bytes at 0xfc40ce are the arcade's again);
  - the three tables live in battery RAM the arcade never touched in any tapped run (formats §23: `0x40e6e4`, `0x40e744`,
    `0x40f010`, their slot words in three unused words, a tag "ORG4"); no byte saved by v0.2.1 moves or is written on the
    upgrade; the test mode's BACKUP RAM CLEAR resets them through the project's `slot_init`, as it does the seven's;
  - starting times: the first four of each original's own normal table (Big Forest and Bay Bridge 4'00 to 4'15, Acropolis 5'00
    to 5'15) and the game's first four default names;
  - in the attract each original's reverse table is shown right after its own table, one screen of four rows titled
    "BEGINNER REVERSE RANKING" (Big Forest), "MEDIUM REVERSE RANKING" (Bay Bridge), "EXPERT REVERSE RANKING" (Acropolis): the
    level word and REVERSE in red, RANKING in white. Each original's group is one page longer, so the arcade's own pages and
    the seven's come round one loop later than before; the pages themselves are unchanged. After a reverse race on an original
    the attract's first page is its reverse table (Phase 27b's rule).
  Not verified: any human drive; linked play; real hardware (a real board's battery content is unknown).
  `docs/spike/2026-11-phase35-reverse-times-findings.md`.
- **The COURSE WEATHER screen** (by design; weather stage 1). Pascal, 17 Nov 2026: "When: an
  addition weather selection screen like the reverse but for weather"; 18 Nov: "btw i think storm and rain shoudl be together (no
  separation on the course selection)". After COURSE DIRECTION, on all ten courses, a second screen in its layout chooses DRY or
  RAIN (the wheel at rest or left DRY, right RAIN; the gas or a 10-s countdown confirms; the countdown locks the choice shown,
  DRY unless steered). The race loads with the game's lock-to-load timing after the weather lock: answered at once, about 74 video
  frames (1.3 s) more before a race than on v0.3, 10 s more on a countdown. The arcade has no such screen. With it, COURSE
  DIRECTION greys the picture not shown while choosing (Pascal: "i just notice a separate bug: selecting reverse or normal doesnt
  grey out the one not selected (will need a fix)") and holds its lock look 16 logic frames (0.59 s) before the weather screen
  opens; `weather=False` keeps v0.3's direction screen. A RAIN race shows RAIN in white under the course's name (left of
  REVERSE in reverse), records no best time and asks for no name (Pascal: "Ok"); in this stage it is otherwise a dry race (the
  storm comes in the later stages). The attract, linked play and the operator's fixed course are always dry. The word RAIN, the
  badge, the steering zones and the 10-s countdown are the session lead's calls, not yet Pascal's decisions.
  `docs/spike/2026-11-phase80-weather-findings.md`.
- **The rain** (by design; weather stage 2). A RAIN race rains: 300 narrow solid 3D box drops in
  60 clusters falling with a slight wind slant round the camera and staying with the world when the car turns, a splash where a
  drop lands within 35 units, an overcast grade over the 3D picture and each course's backdrop greyed, from the countdown through
  the goal and the results; DRY is v0.3's race. The arcade has no weather. As Pascal approved it in the prototypes ("the rain is
  good"; "narrower drops"; of drops without splashes "it look like they're floating"). The design says: "An overcast grade over the
  3D picture and a grey sky per course (each course's own backdrop palette greyed); the HUD, the start lights and the READY board
  keep their colours." The build does as the prototype Pascal approved: the HUD (tile layers) keeps its colours exactly (palette
  and tile RAM unchanged); the start gantry, its READY board and its lamps are 3D objects, so the grade greys them slightly while
  their hue stays (spike 44: "the board's blue and the lamps' red keep their saturation"): measured on Metropolis's countdown, the
  board's band 60/60/185 in DRY and 66/73/155 in RAIN, a lit lamp 226/0/0 and 183/33/40 (the session lead accepted this reading and
  corrects the design's sentence). The rain is drawn
  after the game's scenery and trimmed first when a frame is short of records (Big Forest's busiest frames) or of time.
  Its time guard is the prototype's: the rain stops for the pass once the game's own vblank count has moved (17.38 ms into the
  pass), so a RAIN pass stays under 17.9 ms since the join (1.0 ms under the picture deadline: the count's move by 17.486 ms, a
  unit in flight of at most 0.2 ms, a tail of at most 160 us; 17.8 ms at this stage, with the rain alone; the prototype Pascal drove
  ran passes of 17.84 to 18.06 ms without a stale picture); the storm never moves the interrupt table or writes the timer, and masks
  interrupts only across its load's copy lists (the final review's W8: `weather/carrier.py`'s contract). Measured
  in MAME 0.289 only. In this stage it also rains inside
  tunnels (stage 3 adds cover). `docs/spike/2026-11-phase80-weather-findings.md` (stage 2).
- **Cover** (by design; its known limitations below are open, still in the build; weather stage 3). In a RAIN race no drop and no splash under the arcade's
  flagged tunnels and roofs (Metropolis's long tunnel and the roof by the pits with its pit lane, Alpine's tunnel, Bay Bridge's own
  tunnel); approaching, the rain stops at the mouth; inside, rain is seen beyond the exit in the opening and the car drives out
  into it. As Pascal approved it: "the long tunnel in metropolis is perfect", then of the roof by the pits "short tunnel is good".
  Short unflagged roofs and bridges keep their rain (the session lead's proposal, not objected). The high view (VR4) puts the camera
  above the pits roof: rain falls on the roof there. The arcade has no weather. Under the pits roof the exit's rain is sparser
  (about 38 drops in view, the prototype's) and lies on the end opening's plane, as in the prototype Pascal approved (stage 3
  findings: ROOF_U0). Measured in MAME 0.289 only. `docs/spike/2026-11-phase80-weather-findings.md` (stage 3).
  - A deviation from the prototype's INTENT, kept on purpose (the session lead's ruling C1: the approved picture is the
    reference): `cover.ROOF_U0 = 0.0`, the pits roof's curtain ON the end plane. Spike 68's code meant a depth along the sight
    lines; the generator call before it overwrote that register, so every curtain cluster of the approved set lies on the plane
    (measured on out/p68tunnels: u from 4e-42 to 6e-39 on every cluster). Pinned by
    `test_the_pits_roof_curtain_lies_on_the_end_plane`; changing it is a change of look for the owner to see.
  - Known limitations (the session lead's rulings C2, F5 and the pin ruling of 19 Nov), against the design's anti-goal "Rain that
    draws over roofs or walls, or falls inside a tunnel (Pascal rejected three versions of the pits roof for it)." and its gate
    "none over roof or walls". Every row but one is the approved prototype's own behaviour (four exits, spot s3, the approach and
    the curtain), made visible by fix round 1's stricter measure; the exception is Bay Bridge's exit (normal), seen in this build
    on one seed of eight and not on the prototype on the same eight seeds (fix round 2, R2-5: not called shared; the same
    mechanism as the other exits). The tests pin each at 1.5 times this build's own maximum over three generator seeds on a taped
    game (re-pin only with a named cause and the prototype comparison re-run); whether to improve on the prototype is the owner's
    call.

    | where | this build, three seeds (px / worst frame px) | the prototype, as nearly the same way | what a player sees |
    |---|---|---|---|
    | Alpine's exit | 1 490 / 84, 168 / 14, 139 / 8 | 520 / 64, 0, 1 182 / 50 (seeded the same on the same tape) | for a second or two before the exit, a few drops painted over the left wall at the opening's edge |
    | Alpine's exit in reverse | 851 / 27, 1 048 / 59, 794 / 45 | 1 365 / 29 (one autopilot run, the old measure) | the same, a few drops at the opening's edge |
    | Metropolis's long tunnel, reverse exit | 388 / 28, 594 / 61, 902 / 56 | 240 / 24, 596 / 61, 24 / 5 (seeded the same on the same tape) | drops over the roof's edge as the exit nears |
    | Metropolis's long tunnel, normal exit | on the joined build, one seed of three: 0, 8 / 3 (frames 5240-5247 on 0x9e3779b9), 0; none on the cover alone (the join's round 2, J3: pinned, cause the join) | as before (seeded the same; the join changes neither the prototype nor the taped game) | a drop or two at the exit's edge for a few frames, on some laps only |
    | Bay Bridge's exit in reverse | 13 / 3, 20 / 4, 40 / 6 | 541 / 74 (one autopilot run, the old measure, another path) | a drop or two over the roof's edge |
    | Bay Bridge's exit | seen on one seed of eight: 123 / 32 on 0x2468ace1 (4fe3bec's code: the same), 0 on the other seven | not seen on the same eight seeds (0 on each): not shown to be shared (R2-5, wider sample) | a drop or two over the roof's top-left edge, on some laps only |
    | the pits roof, spot s3 (stopped 4.6 units from its exit) | 0, 1 288, 2 250 px outside the opening, cells 32, 34, 32 of 36 (4fe3bec: 2 910 on the second seed) | 3 308, 4 530, 1 344 px, cells 34, 30, 34 (seeded the same) | a drop or two drawn over the divider beside the opening while stopped there |
    | approaching the pits roof's exit in reverse | 0, 0, 2 rain objects inside (one splash, two passes; centres judged: the re-review counted 16-314 objects a run centred within 3 units outside a box below its top, whose drops can reach inside) | not measured (its mode-1 margin is the same, MG 1) | rarely, one splash ring on the road just inside the roof, seen from outside |
    | the pits roof's curtain (`ROOF_U0`, above) | on the end opening's plane | the same (it is what was approved) | the roof's exit rain sits in the opening's plane, sparser than the long tunnel's |

    The high view (VR4), which the prototype never handled (it hid the rain over every tunnel there and counted the camera under
    cover; fix round 1, F6; fix round 2): the camera is above every flagged roof, so the cover counts it outside; the rain falls on
    the roofs and is drawn over them; a cluster above a roof within its box has no landing (no splash) and is hidden once it falls
    below the roof's top; nothing is drawn inside a tunnel below its roof (tested on the display records). In the three low views
    a marched box hides what the prototype hides (every cluster within MG of it, at any height). The one known difference of the
    low views: the "no landing" above a roof applies to the pits roof (ROOFED) in every view, so in the default views a cluster
    above the pits roof inside its footprint no longer splashes; in the prototype its drops landed on the car's ground plane,
    under the roof. What a player sees: approaching or passing the pits roof from outside, the drops still fall onto the roof
    and vanish at its top, but no splash rings appear on the road beneath the roof (fewer splashes under the roof, which is what
    the design wants).

    The earlier statement "3 to 6 times the prototype on every exit, a difference of the port" was wrong: it mixed in second exits
    where the autopilot's game had diverged; seeded the same, the two leak alike (stage 3 findings, pre-review round and fix round 1).

- **Lightning** (by design; weather stage 4). In a RAIN race a strike comes every 20-40 s of
  race at random: a 3D bolt of thin rods (a main channel and 2-4 branches, yellowish-white, warm pale yellow and darker gold faces,
  a soft glow) struck 300-800 units from the car beside the course and fixed in the world, about 1 s long, re-striking: the bolt
  alone, a sky flash with a one-frame white-out of the picture, the bolt, dark, one or two more strokes with a smaller sky flash, a
  dim flicker. The arcade has no weather. As Pascal approved it in the prototypes: "could it be a 3d lughtning?", then "B" (beside
  the course); "maybe it should bling in and out couple of time?"; the white-out on the first stroke only: "A"; of the strokes 45 %
  thinner, "this is it, 45 is great keep it". Never more than three full-screen flash onsets in any second (a rule in the code,
  whatever the pattern). Under cover no bolt and no white-out, the sky flash kept (the session lead's proposal, taken as accepted).
  The interval is the session lead's call ("tunable; Pascal did not answer on the interval"). The strike is drawn before the rain
  and trimmed by neither guard for the rain's sake; like the rain it works in fixed quotas behind the game's vblank count, so a strike
  may begin a few logic frames later than the prototype's, and a white-out that would come too late in a pass is not shown (the
  prototype's rule). Measured in MAME 0.289; Pascal drove the joined build on 20 Nov 2026: "big forest all good"; of Metropolis,
  the bolt hidden by the buildings (below). `docs/spike/2026-11-phase80-weather-findings.md` (stage 4).
  - **Metropolis aims down the street** (by design; task 8, 20 Nov). The design's 5.5 says "struck
    300-800 units from the car beside the course"; on Metropolis (both directions) the strike is still 300-800 units away, off the
    road and off any refused cell, but its direction is 2-10 degrees off the view (near the street's direction, the gap above the
    road) instead of 12-40. Pascal, after driving the joined build: "the thinder get hidden by the building"; after driving spike
    85's play set with this aim: "i think that works better on metropolis". Why: only the bolt's lower part is ever on screen (its
    top, at 0.85-1.27 x the distance, is above the screen's top edge, about 0.6 x the distance, on every course), and Metropolis's
    facades stand 80-105 units high right beside the road, so a sight line 12-40 degrees off the view crosses one 50-200 units out
    and it hides that lower part. Spike 85's measure (the bolt's pixels against a twin build drawing it in front of all scenery,
    about 34 stress strikes, Metropolis normal): 27 % of strikes clearly visible (half the bolt or more) with the old aim, 43 % with
    the street aim. Every other course keeps the approved 12-40 (Big Forest and Alpine were good as they were): the session lead
    proposed that only Metropolis change, the owner agreed ("yes only metropolis change agree"); both directions is the session
    lead's reading of "only metropolis". Metropolis reverse
    could not be measured (the autopilot stops against a bank there).

- **The wet handling** (by design; weather stage 5). In a RAIN race the car drives as Pascal
  approved it after driving the prototype ("hangling is good now!"): the slide starts at a lateral demand of 420 (the arcade's 546)
  and builds, and can end in the game's flat spin-out, only above half throttle (Pascal: "The lost of control in turns i think this
  shouldnt apply when we lift the foot of the gas pedal"); a slide held about 1.5 s at full lock on full gas above 100 km/h spins
  the car (cool-down 77 logic frames); the wheels spin at full gas in gears 1-3 (the traction x0.6 at a standstill rising to x1 at
  60 km/h; 0-100 km/h about 1.98 s against 1.70), with the game's smoke and squeal and a rising engine note; a brake held at 80 %
  for 8 logic frames above 100 km/h locks the front wheels (steering does nothing, the car slows as on a lift) until the brake is
  eased below 40 % or the car is under 20 km/h (Pascal: "A"); the braking clamp -1583 (the arcade's -1820), the grip base 376
  (392), the squeal from 280 (364); the opponents' working performance x0.97 (their laps 3.1 % longer). None of it under cover
  (the player's tunnel flag; Pascal: "A", dry inside), in the countdown, a put-back glide, a pit stop or after the goal; the
  opponents' factor under cover too. DRY is v0.3's handling. The arcade has no wet handling. Differences from the prototype Pascal
  drove: the squeal and the engine note follow the same gate as the other rules (in a glide or a pit stop they are the game's own:
  the prototype could keep a slip's squeal there); the clamp is the design's -1583.0 (the prototype's -1582.61). Measured in MAME
  0.289; Pascal drove the joined build on 20 Nov 2026 ("i think all the tests are good"; he named no handling point; before that
  the prototype's sets). `docs/spike/2026-11-phase80-weather-findings.md` (stage 5).
- **The wet handling's DRY cost, in DRY races and the attract** (by design, accepted and bounded; weather stage 5;
  the session lead's ruling of 19 Nov 2026). The track's rule: "the attract's busiest pass is 17.98 ms: add nothing to them; show
  their figures did not move". The wet handling breaks it by a few tens of microseconds. Each of its eight hook sites in the game's
  physics and sound code jumps to a boot-ROM stub that tests the weather byte and, in DRY, runs the site's own instructions and jumps
  back. That changes no state and no picture: DRY is identical pass for pass. But it costs time: 41.5 us on the mean DRY race pass,
  about 22 calls a pass, 15 of them at the opponents' site, once per opponent. The attract's demo races run those sites too: its
  busiest pass outside the scene loads is 17.734 ms against 17.708 ms on the same set without the handling (+26 us), about 1.2 ms
  from the deadline. No other construction does the approved behaviour: the game computes the opponents' speed per car and per pass
  from ROM constants, so the x0.97 can only be applied by a hook run per car whose dry path is already minimal (a test and the site's
  own instructions); moving it to a once-a-pass site would change the bend-limited sections' speed, which the prototype Pascal drove
  slowed too. RULING (the session lead, 19 Nov 2026): accepted. For this stage the rule reads: the attract and a DRY race may cost at
  most the handling's dry path, bounded by a test (`tests/test_weather_handling.py::test_the_hooks_cost`, `DRY_COST_MAX_US` 50 us on
  the mean DRY race pass and on the attract's busiest pass against the set without the handling). Stage 2's own switch test keeps its
  10 us bound, measured on the set without the game-changing modules (`tests/test_weather_carrier.py::test_dry_runs_no_storm_code`).
  The owner is told. Measured in MAME 0.289 only. `docs/spike/2026-11-phase80-weather-findings.md` (stage 5, fix round 1).

- **The storm's sound** (by design; weather stage 6). A RAIN race has a rain bed from the countdown to
  the finish (a generated 2 s loop of hiss at 2-7.5 kHz, a faint wash and droplet ticks, 7.1 dB under its voice's full level: Pascal,
  "now the rain is a bit too loud, id say in between before and now"), faded out under the game's own tunnel words and back, and
  after each lightning strike a thunder (a crack and a boom with a long rumble: "the thunder sound is good as A (one crack)",
  "actually i like 13!") close, medium or distant by the strike's distance (0.3 / 0.6 / 0.9 s after it, the farther lower and
  quieter), with the engine, music, effects and rain pulled down under it. The arcade has none of it. Every sample is made by the
  project's code at build time (no recording, no third-party audio); the build now reads and writes the sound program and the two
  sample ROMs (three more changed members). The thunder's level and the ducking are out/p75storm's (Pascal on the louder joined set:
  "everything is good but level of the thunder is too high"), settled on the joined build: "thunder level is good" (20 Nov 2026). A thunder that started before the
  finish rings out its sample (up to 7 s) into the goal, as in the prototype; no thunder after the finish.
  DRY plays v0.3's sounds, write for write, except that a word arriving within 3.8 us of a tick boundary may be read one tick (17.96 ms) apart; none in the three test races (fix round 2, measured): from the boot to the run's end every write to both MultiPCM
  chips is v0.3's in voice, register, value and order (Big Forest's DRY race 66 765 writes, Metropolis's 74 255), the only extra
  writes the storm's three spare voices' key-offs at a reset. The ticks coincide within 4 us; within a tick each write lands up to
  0.78 ms later than v0.3's, the level hook's few cycles on every write before it in that tick, so a note may start that much later
  in its tick (no write crosses a tick, no order changes). One residual race remains: the main loop polls the timer in a
  38-cycle loop (3.8 us), so a word reaching the board within that of a tick boundary can still be read a tick apart when anything has
  moved the loop by a few cycles: none in the three DRY races compared; once between the RAIN chain with and without thunder (C055 at
  194.631 s: engine writes a tick early). Before fix round 2 the hook's cost on the 168 register writes of the
  power-on initialisation, before the YM3438's timer A starts, put every tick 828.8 us behind v0.3's: commands near a tick boundary
  were read a tick apart and the five dynamic effect voices were allocated differently, so effects were cut short or ran longer by
  up to about 1.9 s (Big Forest's test race: five effects; a note held 20.4 ms longer at the word C041). The board now gives those 8
  288 cycles back before the timer starts (patch 4: the boot's RAM clear made faster and padded) and the reset 8100's timer reload
  stays in place. The price: the sound program differs from the approved prototype set's (out/p75storm) in four listed ranges
  (tests/test_weather_sound.py P75_PROGRAM_DIFF); its two sample ROMs are equal. The storm's own sounds are as before (the sound
  tests, the listening files' levels); two storm events start a tick later than on the board before (C201's fade at 233.76 s in
  the chain, the injected attract thunder at 21.19 s; up to 19.2 ms): inherent in the realignment. The owner can compare out/p80s/listen/11 and 12 (this board), 11b and 12b (the board before).
  The design says: "no output sample at full scale beyond the game's own start horn" (the session lead's gate). The build: where the
  game itself comes within a fraction of a dB of full scale without any rain (Big Forest's race on the autopilot: the start horn at
  -0.0 dBFS, a collision's effects at 111.0 s at -0.13 dBFS), the rain bed at Pascal's level lifts the mix over it: on that race 11
  samples at full scale (2 at the horn, 9 at 111.04-111.12 s), the same race without the storm none; while a thunder sounds or its
  duck holds the thunder adds none (outside that window, on fix round 2's board, the runs with and without thunder clip at different
  near-full-scale moments of the game's own, the looped samples' phase after a duck: 9 samples with the thunders, 226.162 s where the
  control peaks at -0.26 dBFS, against 8 without). Every full-scale sample lies within one tick (0.1 s before fix round 3) of where the switch-off set is within 2.17 dB of full scale (where the rain's own -13.1 dBFS peak could take it over; fix round 1, M1); the rain alone
  peaks at -13 dBFS. A later run also clipped one sample at Metropolis's start horn (158.76 s, the switch-off set -1.28 dBFS). Kept: the rain's level is Pascal's (the session lead's ruling). `docs/spike/2026-11-phase80-weather-findings.md` (stage 6).

### Weather, the join (20 Nov)

- **The storm's cap is 17.9 ms of V60 time a RAIN pass** (by design; the session lead's ruling at the join; the design amended on main): the
  game's vblank handler moves the count up to 17.486 ms into a pass, a unit of storm work in flight is at most 0.2 ms and the tail
  from the guard's trip to the pass's end at most 160 us since round 2 (149 measured: forced in the first module, every module's
  late path, the sound's trigger sending two words; round 1 had 190 for the rain's old late splash loop); 17.846 ms, the cap kept
  at 17.9 by the session lead's ruling (round 1: 17.876; stage 2 had 17.8 with one module's 31 us tail).
  The worst pass measured on all twenty races: 17.70 ms (Bay Bridge, both directions); MAME shows a stale picture past 18.9 ms.
- **The sound's trigger is exempt from the guard** (by design; round 2, J1, the session lead's ruling): it runs on every pass of a
  rain mode whatever the guard says, an
  allowed unguarded unit of 7 us idle and 25-32 us when it sends a thunder and a rain word on one pass, so every word reaches the
  board on the pass it is due (round 1 reported them up to about 1 s late on Metropolis and Bay Bridge).
