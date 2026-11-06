# Phase 11: tarmac under the field (31 Oct 2026)

Plan: `docs/superpowers/plans/2026-10-31-phase11-field-coverage.md`; recon: `docs/spike/2026-11-ai-lanes-recon.md`
(the parked pairs traced to two converter defects); formats §15–16.

## The two defects

1. **Tarmac coverage off the centreline.** A slice's collision quad is the slice's own polygon (triangles get a
   fourth corner, straights merge), grown 4 units a side. Where the Saturn road is built from triangles and
   slivers, or a merged run cuts a bend, the quad does not reach the road's edge: at Metropolis road points
   42–49 nothing but verge covered lateral +6..+10, where an AI line runs. Phase 8's coverage test checked the
   centreline only. An opponent on verge stops and never restarts (the player, driven, merely slows).
2. **Verges level with the tarmac.** A verge takes the tarmac edge's height straight across (Phase 8); where a
   verge overlaps tarmac at exactly that height the TGP's tie rule (the later list entry) can hand a car on
   tarmac the verge: its lap position freezes, its cursor target lands on itself and it stops (Metropolis car 11
   at road point 267).

## What changed (`convert/collision.py`)

- `coverage_gaps` samples every centreline point at lateral −10..+10 (1-unit steps) and reports the points no
  tarmac quad contains; `fill_coverage` grows the nearest tarmac quad of the same stretch (centre within 40 units,
  lap arc within 60) sideways by what the gap needs (at most 14 units), and where no quad can absorb a gap adds a
  **filler** quad (10 units along the road, the gaps' lateral span ± 6 across, the road's height, the nearest
  quad's direction attribute) to the tarmac block. `saturn_collision(..., cover=True)` runs it after the merge;
  the build does. Fill reports (gaps → grown + fillers; verges built): Alpine 190 → 52 + 20 (553), Amazon Falls
  354 → 76 + 88 (375), Diablo Canyon 460 → 109 + 93 (529), Metropolis 190 → 28 + 13 (405), Pacific Coast
  243 → 93 + 63 (483), Surfers Oval 555 → 88 + 81 (488), Surfers Road 603 → 126 + 123 (584). TGP words free
  after the build: 70 045 (27 084 after Phase 10's; the road verges are fewer and larger than the per-slice ones).
- **Verges are built from the road's measured edge** (`road_edges`, `road_verges`), not from each slice's quad.
  The first attempt kept the per-slice verges and sank them 0.3 below the tarmac (then 0.3 *away from zero*,
  because the TGP compares |height|: a sink across y = 0 parked Diablo Canyon's and the Oval's whole fields);
  the battery still parked 5–15 cars per course, and every parked car sat at the verge's height, 0.3 above the
  tarmac under it, with a verge quad across the road there. Measured against the originals: Big Forest and
  Acropolis have **no** sample of the road's ±10 band under both a verge and a tarmac quad; our courses had
  16–37 % of that band under a verge, at the centreline too — a triangle slice's quad has a diagonal "side",
  and the verge built 40 units off it lies across the road. Whatever the offset's sign, a car that has once
  touched such a verge is nearer its height than the tarmac's and the TGP keeps it there; its lap position and
  cursor freeze, its target falls on itself, and it stops. So after the fill the side verges are rebuilt: at
  every centreline point the tarmac's lateral extent is scanned in half-unit steps (following the surface's
  height sample to sample, so a crossing's other deck does not count), and a 40-unit verge quad is laid from
  that edge per step (runs of equal edges on straights fuse, up to six steps; each step takes its two ends' own
  laterals so consecutive steps share their end lines, takes the four points' convex hull where the laterals
  cross inside a tight bend, and takes the wider end's edge where the road widens between two samples; directions are smoothed
  over five points for the lap seam, which zigzags on Diablo Canyon). Verge and tarmac touch and overlap by less
  than half a unit; `VERGE_SINK` = 0.3 away from zero stays as the tie-breaker for that strip.
- **Fillers and grown quads are placed by their front centreline point** (the point nearest the quad's front
  among the points heading the quad's way, by its direction attribute), not by `arc_of` lap arcs: on Amazon
  Falls the arc named the other leg where the road passes near itself, a filler for point 134 was inserted among
  the quads of point 188 and credited 188, and every car that touched it jumped 54 road points (cursor lead 67).
- **A start-line band** (`start_line_band`, found by the review): three of Diablo Canyon's opponents stopped at
  the start line for good — they drove straight from a quad credited 450 into the first quad, credited 0 (its rear
  9 units before the line), were never credited n−1, and their cursors waited at n−1 for a road point ≥ n−1 for
  the rest of the race (formats §15; the parked window and the cursor-lead metric both missed it: the cars stalled
  late, and a cursor *behind* the car reads as lead 0). The TGP breaks ties between overlapping quads by rounding,
  so a car is certain of a credit only where no other quad lies under it. One quad now spans the road's measured
  width from 10 units before the line to 10 past it, appended last (a straddler: credited n−1), and the quads
  around it are cut back to its edges (a head quad crossing the line loses its rear — the first segment is pinned
  to road point 0 —, a quad ending inside the band's rear half loses its front, one wholly inside is dropped, the
  tail's straddlers stay). The band is laid in the frame of the road's smoothed direction at point 0: the
  resampled centreline hooks ten units sideways at Diablo's lap seam, which is why a check walking its points
  passed while cars driving straight were stranded; the road test now samples the band on a grid.
- Fillers for points near the lap start go among the head quads, before the wrapped tail (review): fillers for
  Amazon's points 1–2 had landed after the last straddler, the last segment became road point 2, the n−1 pin did
  not fire and the cursors ran past the line while the cars were at 320–329 (lead 16).
- `race_report` counts opponents **parked** (no progress over the last 8 dumps of the race window) and names
  them; the race gate caps them at `PARKED_DEFAULT` = 2 per course.
- Tests: no verge over tarmac in the ±10 band on any course (contact strip excepted) and the run-off under some
  quad (the originals leave 22–34 % of lateral 12–40 bare; ours ≤ 1.4 %); every tarmac quad under every road
  point and AI offset credited from three behind to its own length ahead (`test_convert_road`).

## Results (150 s autopilot races, `spike/race_check.py out/p11/build`; 15 opponents)

| course | parked (Phase 10 build) | moved | leader gain (points / s) | player extensions / expiry | cursor lead |
|---|---|---|---|---|---|
| Big Forest (original) | 0 | 15 | 877 (7.5) | 6 / — | 4 |
| Bay Bridge (original) | 0 | 15 | 858 (9.4) | 2 / 7350 | 4 |
| Acropolis (original) | 0 | 15 | 1219 (10.4) | 4 / — | 3 |
| Alpine | 0 (4) | 15 | 782 (6.7) | 4 / — | 10 |
| Amazon Falls | 0 (5) | 15 | 851 (7.3) | 7 / — (lapped) | 9 |
| Diablo Canyon | 0 (6) | 15 | 634–710 (6.5) | 2–3 / 7600–8350 | 8 |
| Metropolis | 0 (4) | 15 | 682–709 (6.3) | 4 / 8350 | 16 |
| Pacific Coast | 0 (2–13) | 15 | 867 (7.4) | 4–5 / — | 13 |
| Surfers Oval | 0 (6) | 15 | 895 (7.6) | 5–6 / — (lapped) | 15 |
| Surfers Road | 0 (6) | 15 | 731–740 (6.8) | 3 / 8350 | 9 |

(The shipped build, `out/p11/build`; ranges where the three Phase 11 builds — road verges, the band past the line,
the band at the line — differed. The regenerated Big Forest harness: 15 moved / 0 parked and 13 / 3 in two runs
of the same code; its start strip's quads carry road points 40–65 and it is gated at Phase 10's floor.)

No opponent goes backward between dumps on any course (Phase 10: up to 25). The cursors lead the cars by 8–16
points (the originals 3–4; Phase 10: 7–23): one merged quad plus the 12 units of the start-line band. In road
points per second the converted fields run at 70–90 % of the originals' (a third to a half in Phase 10), but
the originals' points are 7.4–10.2 units apart and ours 10: **in units per second the fields are at parity** —
the opponents' mean speed over the race window (straight-line distance between dumps) Big Forest 59.7, Bay
Bridge 56.5, Acropolis 56.7; Alpine 50.9, Amazon Falls 54.4, Diablo Canyon 49.3, Metropolis 51.4, Pacific
Coast 56.3, Surfers Oval 59.8, Surfers Road 54.4 (85–100 %). The share of opponent samples with the working
performance cut below the base (the heading rule, formats §15) is 3–6 % on the originals and 2–13 % on ours
(Metropolis 12, Surfers Road 13: the twistiest), and the lines' bendiness as the AI measures it (a heading
change above 22.5° over 8 points) is 0–2.3 % of points on both. The parked cars were the pace problem; the
"shared-road-point jam" of the Phase 10 write-up was this — a car on a verge with its lap position frozen,
and the pack braking for it. The 90 s drives (`ten_course_build.py`): 28–29 display-list switches per 57
frames on every entry; the autopilot's forward progress Alpine 2917, Amazon Falls 3533 (a lap), Diablo Canyon
3190, Metropolis 3033, Pacific Coast 2837, Surfers Oval 3278, Surfers Road 2919 (977 and 587 on the two Surfers
courses in Phase 10, behind the queue); `offroad 0` everywhere. Diablo Canyon's autopilot, cutting a hairpin,
found no quad for two frames in the fan a triangle-clamped verge step left bare; the step is now the four
points' convex hull (the run-off stays under some quad in all but 0.2–1.4 % of samples at lateral 12–40; the
originals leave 22–34 % bare there), and the final build's drives show one no-hit frame each on Diablo Canyon
and Surfers Road, none elsewhere (the TGP answers height 0 for that frame; the car's height did not move).
The Pacific Coast 90 s drive is 2837 units (3791 behind Phase 10's jammed field): the autopilot cannot overtake
and follows the slowest opponent, which runs at about 3.5 road points a second. The regenerated Big Forest
harness, built with the coverage path like the deliverables, goes from 9 moved / 12 parked to 15 / 0.

Gates (`tests/test_race_build.py`, `tests/test_tgp_build.py`): every field moves ≥ 14 of 15, leader ≥ 500
points, parked ≤ 2, cursor lead ≤ 20, extensions ≥ 1 on every course (the Phase 10 allowances for the Oval and
Surfers Road, Pacific Coast's "moved 2" floor and the drive floors are gone).

## Open

- The single-file starts of the Bay Bridge / Acropolis templates (the original Bay Bridge starts the same way)
  and the fixed-offset AI lines (no hand-made racing lines; the originals' lane groups of formats §16 unused):
  the pace is at parity, so these are playtest items — "average difficulty" (spec §2) with `pace`, `laps`,
  `time_factor` per course.
- Side-by-side strips credit a car on the narrower strip with the other strip's merged quad's front (Alpine
  185–192: up to 8 points ahead; a 118-unit merged quad credits 11 ahead at its rear): the lookahead Phase 10
  accepted, now pinned by `test_the_tarmac_under_each_road_point_is_credited_near_it`.
- The resampled centreline hooks ten units sideways at the lap seam on Diablo Canyon (the grid's side strips):
  the verges and the start-line band use smoothed directions there; the AI lines (line 0's own points) do not yet.
- The player's Diablo Canyon race varies between 2 extensions (expiry at 7600) and 3 (8350) run to run.
- The autopilot cannot overtake; its progress with a live field measures traffic.
