# Phase 20 recon: the collision under the drawn road on climbs

Pascal's playtest (1 Nov 2026): on Diablo Canyon's first climb the car, or the camera, goes slightly under the road.

## 1. What the car rides on

Since Phase 16 the collision's height is the arc profile (`profile.arc_height`), read at each point's true arc along the
route (`centreline_arcs`). The profile (`road_profile`) samples the ground mesh (group 0) under each route slice centre,
bins the samples by arc (10 units, median), smooths them with a 5-bin moving median, and fills empty bins linearly.

## 2. Measured: the gap between the drawn road and the collision

Along each course's 5-unit centreline, wherever a ground level lies within 4 units of the collision: the drawn road minus
the collision (positive = the car sits below the drawn road).

| course | points over 0.5 | over 1 | worst |
|---|---|---|---|
| Alpine | 13 | 0 | -0.70 |
| Amazon Falls | 35 | 12 | -2.30 |
| Diablo Canyon | 57 | 12 | +2.21 (points 110-115 = the first climb) |
| Metropolis | 12 | 5 | -1.29 |
| Pacific Coast | 8 | 4 | -3.88 (and 5 points 5.2-6.2 over, beyond the 4-unit window: review) |
| Surfers Oval | 9 | 1 | +1.25 |
| Surfers Road | 20 | 4 | +1.70 |

## 3. Cause

Route centres that land in a hole in the ground mesh contribute nothing: 7-50 per course (Diablo 28). On Diablo's climb,
the route centres at arcs 546 and 569 have no ground under them, so the profile bridges 524 (-17.4) to 592 (-2.6) with a
straight line, which cuts under the climb's curve by up to 1.9 units at arc 556 (the drawn road -9.0, the collision -10.9).
Where the profile does have a sample it matches the drawn road (524: -17.7 vs -17.4; 604: -1.4 vs -1.3).

## 4. Spike: also sample along the route's resampled centreline

The same binning, with the ground also sampled every `s` units along the route's centreline (`lap.centreline` at its true
arcs, `centreline_arcs`):

| s | over 1 (all courses) | worst per course |
|---|---|---|
| none (today) | 38 | 0.70 / 2.30 / 2.21 / 1.29 / 6.2 / 1.25 / 1.70 |
| 5 | 1 | 0.57 / 0.78 / 0.67 / 0.89 / 0.95 / 1.08 / 0.78 |
| 2.5 | 1 | 0.48 / 0.64 / 0.63 / 0.66 / 0.96 / 1.08 / 0.78 |

2.5 units: at most 5 points over 0.5 per course, the one point over 1 is Surfers Oval 314 (1.08). The build still passes
the cliff check (`max_step`). Bridge decks keep working: each sample takes the level nearest the running profile.

## 5. What else reads the profile

- the collision quads' heights (all courses) and the start band;
- the opponents' pitch (`road.attitude_words`: the arc profile's slope);
- the drive gates: Diablo's pitch smoothness (<= 10 jumps over 6 deg, none over 15), opponents' pitch with the slope,
  the player banking on a cambered course.
