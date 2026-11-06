# Phase 10: the opponents race on generated tables (31 Oct 2026)

Plan: `docs/superpowers/plans/2026-10-31-phase10-opponents.md`. The Phase 9 write-up (`2026-11-balance.md`) left
the field stalled on every converted course and bisected the cause to the generated road lines and segments.

## The rule (boot `0xfec69d..0xfec7a7`, formats §15)

An opponent keeps a **cursor** into its road line (`entity+0xe1`, one point per 16 bytes) and steers at the point
two beyond it. Each frame it reads the cursor's point, takes the segment named by the point's `link` high half,
and advances the cursor by one point only if that segment's road point is **at or before the car's own road
point** — which is the road point of the segment of the lap-position quad the TGP last reported under the car.
Its speed is its base performance unless the heading eight points beyond the target differs from the target's by
more than a quarter turn of 0x1000 units, in which case the TGP scales it down.

On the originals every road point owns one to eight segments (one per collision quad, quads 10 units long,
three per point) and a line point names the first segment of its own point, so the cursor advances as the car
passes each point and the two cross the start line together.

Our tables (Phase 6–9) named the *first segment at or after* the point, and the merged collision quads (up to
six slices, 60 units) left many road points without a segment of their own: the cursor waited for a point the
car had not been credited with, the target fell behind the car, and the car crawled or stopped. At the start
line a merged quad could credit the car with a road point past the line before the cursor reached the line's
last points, stranding the cursor there for good (the cursor comparison is not modular).

## What changed (`convert/collision.py`, `convert/road.py`)

1. The three slices at each end of the lap are never merged (`MERGE_KEEP_ENDS`), and the first and last segments
   are pinned to road points 0 and n−1 (`END_SNAP`): car and cursor cross the line together.
2. Every line point names the **last segment whose road point is at or before it** (the first segment before
   any): the cursor never waits for a point the car has not reached.
3. Each quad's road point is the centreline point nearest its **front** edge (was: its centre), searched in a
   window of −2..+15 points past the previous quad's (reach 60 units for side-by-side strips; a quad longer than
   200 units — Big Forest's degenerate sliver — keeps the previous point). With the centre, a car in the front
   part of a 60-unit merged quad was credited with a point behind it, its target (cursor + 2) fell at or behind
   it and it stopped: Pacific Coast's whole field stood at road point 75–77 on their lines. With the front the
   cursor leads the car by up to one quad: a 20–80 unit lookahead against the originals' 20.

## Experiments (regenerated Big Forest = Phase 6 tables in Big Forest's own bank; 150 s autopilot runs)

| build | opponents moved (≥100 points) | leader gain (points) | notes |
|---|---|---|---|
| original Big Forest | 15 | 877 | reference |
| Phase 9 tables, regenerated BF | 0 | 0 | the stall |
| Phase 9 tables, Alpine | 5 | 249 | seven cars at the origin before the pointer fix; then 20 |
| floor-mapped links only, regenerated BF | 4 | 227 | cars stranded at the line (cursor at the last point, road point wrapped) |
| floor-mapped links only, Alpine | — | 281 | car 9: 129 points in 26 s (original's car 9: 178) |
| front-of-quad road points + floor, Alpine | 15 | 492 | the player unaffected; hurt the player on regenerated BF |
| floor + cap on the last eight points | — | — | cursors ran away after the wrap; two cars never left the grid |
| end slices unmerged + pinned ends + floor, centre road points | 10 / 572 (Alpine) | | Pacific Coast's field deadlocked mid-lap at 75–77 |
| **+ front-of-quad road points (shipped)** | 15 / 492 (Alpine), 11 / 607 (regenerated BF) | | see the table below |
| narrower AI offsets (½, ¼) on the shipped tables | Pacific Coast 0 / 69–71 | | worse: the offsets are not the lever |
| merge runs of 2 slices (fits: 10 k TGP words spare) | Pacific Coast 2 / 379 | | still jams |
| no merging at all (does not fit the seven courses) | Pacific Coast 12 / 460 | | one run; Pacific varies 2–12 with the same build |
| field started ahead of the player (start points +48) | Pacific Coast 1 / 150 | | the cursor protocol needs the game's grid |

## Results per course (150 s autopilot races, `tests/test_race_build.py`; the original Big Forest's field: 15 moved, leader 877)

| course | opponents moved (≥ 100 points) | leader gain | player extensions / expiry |
|---|---|---|---|
| Alpine (BF template) | 13 | 555 | 4 / — |
| Amazon Falls (BB) | 14 | 471 | 2 / 7100 (0 before the review pass: a mapping defect, see below) |
| Diablo Canyon (AC) | 12 | 402 | 2 / 7600 |
| Metropolis (AC) | 13 | 592 | 4 / 8350 |
| Pacific Coast (BB) | 2–12 (varies run to run) | 300–380 | 2–5 / varies (lapped in the final run) |
| Surfers Oval (BB) | 9 | 294 | 0 / 6100 — standing behind parked cars |
| Surfers Road (BB) | 9 | 212 | 0 / 6100 — standing behind parked cars |
| regenerated Big Forest | 11 | 607 | 5 / — |

(The shipped build's `race.txt` after the review pass; "moved" = gained 100 road points at some time. Parked at the
end of the 150 s on the same run: Alpine 6, Amazon Falls 7, Diablo Canyon 8, Metropolis 6, Pacific Coast 13,
Surfers Oval 6, Surfers Road 7. Largest cursor lead over the car's road point: 7–23 points, the originals 4.)

"Moved" counts cars that gained 100 road points at some time; it does not say they kept going. Cars parked for
good (no road-point change over the last 35 s of the race): Alpine 4, Amazon Falls 5, Diablo Canyon 6,
Metropolis 4, Pacific Coast 2–13, Surfers Oval 6, Surfers Road 6; the originals 0. They are often pairs or groups
sharing a road point (Metropolis 43/43 and 264/264, the Oval three cars at 49, Diablo four at 188): the
shared-road-point jam described under Open is general, not Pacific Coast's alone. On the Oval and Surfers Road
the autopilot ends up standing still behind parked cars.

Two things the per-frame trace (`vrtools/mame/lua/fieldtrace.lua`, `VR_FIELD_LOG`) established about the starts:
on the Big Forest template the game uses its grid formula (cars 3 road points apart behind the line, the player
on the left of row 8); on the Bay Bridge and Acropolis templates it lines the field up **single file at road
points 1–15, the slowest car first, with the player at 0 behind them** (the original Bay Bridge does the same),
and everyone waits out the countdown. On those courses the pack then queues behind car 1 (performance 1.74) with
braking waves (negative working performance) because our fixed-offset lines give the AI no overtaking room, and
the autopilot, which cannot overtake either, rams the queue — hence its 0 extensions there. The original Bay
Bridge's field reaches 9.4 points/s; ours 2–3 on those courses, 5–6 on Alpine and Metropolis.

Build `out/p10/build` (`spike/ten_course_build.py`, 90 s drives): every entry at 28–29 switches / 57 frames; the
player's progress with the live field: Alpine 3243, Amazon Falls 2908, Diablo Canyon 2261, Metropolis 2924,
Pacific Coast 3791 (a lap with 5 extensions in the 150 s race check), Surfers Oval 977, Surfers Road 587
(traffic, not the road: the render-rate check stays the hard part of that gate). `spike/race_check.py`
(150 s, ten entries) leader pace in road points per second: Big Forest 7.5, Bay Bridge 9.4, Acropolis 10.4;
Alpine 4.7, Amazon Falls 5.4, Diablo Canyon 4.2, Metropolis 5.5, Pacific Coast 3.2, Surfers Oval 4.2, Surfers
Road 3.1 — the converted fields run at a third to a half of the originals' pace.

## Review pass

The fresh review found two data defects the gates had not caught and the claims overstated. (1) On Amazon Falls
two quads whose front lies 386 units from any centreline point fell back to the globally nearest point (117) and
the monotone clamp dragged the next 91 quads (about 1000 units of road) to road point 117: the player's road
point jumped 0 → 117 after the line and its first checkpoint (110) never fired — the "boxed in" reading was
wrong. Fixed: a fallback farther than `SEGMENT_REACH` keeps the previous quad's point; a seven-course invariant
test (every segment within reach of its quad's front or kept, no jump over one merged quad) pins it, and
Amazon's extension check is back in the gate. (2) Every quad whose front was at or past the line was credited
n−1 (Alpine 4 quads, Diablo Canyon 11), so cars were credited the last point for ~50 units and their cursors,
already wrapped, ran away (Alpine: cursors at 18–34 with the cars at road points 2–5 for 10–17 s). Fixed: only
quads straddling the line take n−1 and a straddler advances the lap's progress only to its rear; quads entirely
past the line take their own point; `race_report` measures the cursor's lead (`max_cursor_lead`, the originals
≤ 4) and the gate caps it at 20. The claims were cut back to what is measured (spec: M6 partial), the parked
cars are listed per course above and in `docs/deviations.md`, and the gate floors carry the measurements with
their reasons (Pacific Coast's field varies 2–12 moved on the same build).

## Open

- **Cars park for good on every course; Pacific Coast's field jams in some runs** (2 of 4 with the same build) at
  road points 74–77: the segments of that side-by-side stretch (quads 69–72) all carry road point 74, so cars 40
  units apart report the same position; the game ranks the cars by road point and brakes each for the one
  ranked ahead (`0xfec7ab..`, the neighbour pointers `+0x198/+0x19c` from the ranking at `0xfea5d1`), which can
  be physically behind — two such cars block each other for good and the pack piles up behind. The originals'
  10-unit quads never let cars that far apart share a point. Candidates: distinct road points per quad within a
  strip, or the ranking's tie-break.
- **AI lines**: fixed lateral offsets of the centreline (Phase 6). The field's pace (a quarter to two thirds of
  the originals') and the queue behind the slowest car on single-file starts both hang on them: the originals'
  hand-made racing lines let the AI overtake. Next pass: lines that spread the pack (staggered offsets at the
  start, apex lines in bends) and a look at the line-switch logic (`0xff7616`).
- The autopilot cannot overtake, so with a live field its progress on the Bay Bridge-template courses measures
  traffic; the gates carry the measured floors and reasons.
- `pace` per course is for the playtest.
