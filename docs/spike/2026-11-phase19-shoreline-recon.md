# Phase 19 recon: the wall at the shoreline (1 Nov 2026)

Pascal (Phase 18b captures, Surfers Road): "the car is in the water, looks like a bug". The verges are 30 units of
grass past the road's measured edge, then a 6-unit wall strip (Phase 16); where the Saturn's ground and terrain draw sea
inside those 30 units a car runs onto grass that looks like water (Phase 17 recon §1: the car's centre was always on
grass). Phase 17 could not place a wall at the shoreline: the ground under the grass is green, the blue a texture. With
the terrain layer drawn since Phase 18a, the water is polygons: `out/p19/water.py`.

## Water polygons

The Saturn's water faces in groups 0-1 are pure blue-cyan: red 0, blue 144-248 (`(0, 200, 248)`, `(0, 104, 208)`…).
The snow on Alpine is pale blue with red 128-184 and is not water. Rule: red < 40, blue ≥ 128, blue > green.

## Where water lies inside today's run-off

Scanning each 10-unit centreline point and side from the road's measured edge out to the wall:

| Course | Water faces | Sides with water before the wall | within 3 units of the edge | 3-15 | 15-30 |
|---|---|---|---|---|---|
| Alpine | 33 | 19 / 904 | 8 | 8 | 3 |
| Amazon Falls | 64 | 50 / 660 | 23 | 12 | 15 |
| Diablo Canyon | 6 | 7 / 906 | 0 | 7 | 0 |
| Metropolis | 10 | 21 / 730 | 20 (deep water under the decks) | 1 | 0 |
| Pacific Coast | 83 | 82 / 820 | 68 | 12 | 2 |
| Surfers Oval | 320 | 147 / 774 | 78 | 19 | 50 |
| Surfers Road | 391 | 195 / 882 | 103 | 29 | 63 |

Many shores lie at the road's edge (a seawall): the Saturn's road runs along the water.

## Outcome for the plan

Per point and side, the grass is as wide as the distance to the shore, between MIN_RUNOFF (2 units) and VERGE_GRASS
(30); the wall strip starts there. The shore lateral is the nearest of the point and its two neighbours (no gap where
the water juts in between points). Gates: on every course the scan meets a wall quad at or before the water; the field
and TGP gates hold; the captures show no car on the sea.

## Outcome (Phase 19, `docs/superpowers/plans/2026-11-01-phase19-shoreline.md`)

- `shore_widths`: per point and side, the grass width from the measured edge to the first water sample (the nearest of
  the point and its neighbours), between MIN_RUNOFF (2) and VERGE_GRASS (30), and wide enough to reach a wall at
  WALL_MIN_LATERAL (12.5: the AI lines at ±8, WALL_CLEARANCE 3 and a unit for the inner edge sagging on a bend). The
  wall's inset is that width eroded over the grass's longest run (`wall_insets`: a grass run's end point could cut it
  short before a wall run kept its full width, Surfers Road 150-152). Shoreline walls take the grass's short runs (a
  12-point run's chord cut inside a gentle bend of the Oval to 2 units of the +8 line).
- `_near_racing_lines` measured a racing-line point's distance to a wall edge's infinite line: a wall step's radial end
  edge passes through its own point's AI points (distance 0). Walls 30 units out never reached the test; it now measures
  to the segment.
- Gate: on every course a wall quad comes before the first water sample beyond the tarmac (or by 13 units where the
  water starts inside the wall's minimum lateral). Captures: the car's centre over water off the tarmac 98 → 0 logic
  frames on Pacific Coast. TGP 30 090 words left.
