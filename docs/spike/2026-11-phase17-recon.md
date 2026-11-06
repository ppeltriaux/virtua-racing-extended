# Phase 17 recon: the wall at full speed, the holes in the tarmac (31 Oct 2026)

Pascal after Phase 16: fix the two open items, (1) the wall's hold at full speed and (2) the small holes in the
tarmac. Scripts in the session scratchpad `p17/`; captures from `out/site6` (the `-v5` media, build `out/p16/build5`).

## 1. The wall holds: the "car in the sea" frames are grass

The Phase 16 write-up said the autopilot went through the wall twice on Pacific Coast (the contact sheet showed the
car spinning in the sea at about 74 s and 88–92 s). The collision log of that capture (`run-pacific/c.txt`, the
player's position and the quad under it every logic frame) says otherwise:

| Event | Furthest out | Under the car | Then |
|---|---|---|---|
| ~74 s (frames 4180–4300) | 25.3 units right of the centreline | grass quads 838–841 | back on the road |
| 88–92 s (frames 5040–5300) | 32.3 units right | grass quads 884–890 | spins on the grass, drives back |

Over all seven captures the car's centre was never on a wall quad or on no quad:

| Course | Logic frames on tarmac / grass | Furthest from the centreline |
|---|---|---|
| Alpine | 2357 / 5 | 27.5 |
| Amazon Falls | 1497 / 0 | 6.3 |
| Diablo Canyon | 1434 / 57 | 41.6 |
| Metropolis | 1407 / 92 | 46.8 (its wide start area) |
| Pacific Coast | 2824 / 109 | 32.5 |
| Surfers Oval | 2593 / 0 | 7.2 |
| Surfers Road | 1426 / 59 | 23.5 |

The water is the Saturn's scenery drawn inside the 30-unit grass band; the page already said a car on the grass "can
still look as if it is over the water". The README and page claims were corrected (hub 07c230d). Item 1 is not a
defect. The originals for comparison (`orig_walls.py`): tarmac, kerb, a little grass, then a wall strip with nothing
beyond, the wall's inner line at a median 18–23 units from the centreline and 7–10 units wide (Big Forest, Bay Bridge,
Acropolis); ours sit further out (road edge + 30) and 6 wide.

What would remove the "sea" look is a wall at the shoreline. The Saturn ground polygons under that grass carry green
flat colours (the blue is a texture), so the shoreline is not in the mesh colours; finding it would need the
textures. Not attempted: Pascal's call.

## 2. The holes in the tarmac

A scan from every centreline point and half-point, both sides, 0.5-unit steps out to 30 units, records each run of
samples with no collision quad that starts within 20 units of the centreline, and what lies on either side of it
(`holes_kind.py`; the same counts on the Phase 16 code before the review fixes, so they predate Phase 16):

| Course | Runs | Scan points hit | Tarmac→grass | Tarmac→tarmac | ≥ 3 units wide | Starting inside ±10 |
|---|---|---|---|---|---|---|
| Alpine | 251 | 204 / 904 | 237 | 13 | 24 | 3 |
| Amazon Falls | 263 | 223 / 660 | 202 | 58 | 21 | 0 |
| Diablo Canyon | 313 | 252 / 906 | 284 | 19 | 55 | 11 |
| Metropolis | 146 | 133 / 730 | 122 | 22 | 53 | 6 |
| Pacific Coast | 281 | 228 / 820 | 278 | 1 | 30 | 11 |
| Surfers Oval | 314 | 261 / 774 | 307 | 7 | 54 | 29 |
| Surfers Road | 405 | 326 / 882 | 397 | 7 | 42 | 1 |

Three kinds:

- **A. Seams between the tarmac and the grass** (most of them; median start 12.5–16 units out, mostly 0.5–1 unit
  wide, 9–47 per course 3 units or more). The grass's inner line is one straight lateral per fused run, at the run's
  widest measured edge less one scan step (`road_verges`: "the wider of its two ends ... a triangle of run-off is left
  bare instead"), while the tarmac's real edge wanders between samples and narrows inside the run.
- **B. Holes inside the road between road points.** The coverage fill samples the road only at the 10-unit points,
  ±10 units (`COVERAGE_SPACING`, `COVERAGE_HALF_WIDTH`); the half-points are never checked. Worst: Pacific Coast at
  point 318.5, 15.5 units with no quad starting at the centreline; Surfers Oval 46.5–49.5 and 95.5–96.5, 4.5–9 units
  starting 2.5–7 units out. Diablo point 240.5 (7.5 out, 3.5 wide) is the hole that gave the player its −87° pitch
  sample in the Phase 16 drive test.
- **C. Tarmac-to-tarmac holes past ±10** on wide stretches and side strips (Amazon's 58, up to 10.5 units; Diablo's
  start area up to 12.5), outside the coverage fill's ±10.

The overlap rule makes overlapping safe: the TGP takes, among the quads under the point, the one nearest the car's
height and the last of exact ties, and `cell_lists` puts the tarmac after the verges (`docs/formats/model1-tgp-collision.md`
§5). The capture logs had only 5 logic frames over a tarmac/grass overlap (3 answered grass, at the very edge).

## 3. Outcome for the plan

- Item 1: nothing to fix in the wall; the record is corrected. A shoreline wall is an option for Pascal, not planned.
- Item 2:
  - A: the grass starts inside the tarmac, from the run's narrowest edge less an overlap (as the wall now starts inside
    the grass), so no seam opens where the tarmac's edge narrows.
  - B, C: the coverage fill checks the half-points too and out to each point's measured road edge (both sides), filling
    with the existing grow / filler machinery; the TGP budget (43 077 words free) is the limit to watch.
  - The gate: the scan above finds no run 1 unit or wider anywhere between the centreline and the wall, on every
    course; the Phase 16 tarmac-to-wall seams should go with it.
  - The Diablo drive test's two −87° hole samples should go; the field and player gates must hold.

## 4. Outcome (Phase 17, `docs/superpowers/plans/2026-10-31-phase17-collision-holes.md`)

| Course | §2 runs before | after | Gate: wide (≥ 1 unit) beyond 10.5 units |
|---|---|---|---|
| Alpine | 251 | 0 | 0 |
| Amazon Falls | 263 | 1 | 1 |
| Diablo Canyon | 313 | 0 | 1 |
| Metropolis | 146 | 4 | 17 |
| Pacific Coast | 281 | 0 | 0 |
| Surfers Oval | 314 | 3 | 0 |
| Surfers Road | 405 | 2 | 1 |

None a unit or wider starts within 10.5 units of the centreline on any course.

- The grass: one inner line per run at the narrowest edge less 1 unit (`GRASS_OVERLAP`), never inside 8.5
  (`GRASS_FLOOR`) unless the whole run's tarmac ends there; the nearer of the smoothed- and chord-direction edges when
  the latter lies beyond 8.5; a dart-shaped step inside a tight bend is replaced by its hull; grass over a side strip
  at the road's level is kept (only another deck's tarmac drops it). Per-end inner lines with 1-unit splits at edge
  jumps closed slightly fewer holes for ~1 300 more quads and broke the TGP budget: removed.
- The coverage fill: every 5 units (`COVERAGE_FILL_SPACING`), out to each side's measured edge, sampled along both the
  chord and the smoothed direction; gaps beyond the 10-unit band get a filler over them alone, never a grown slice;
  fillers of consecutive points merged; new corners (fillers, grown quads) take the plane of the slice under them
  (`height` where none), a grown corner its own plane where that is another deck's (Metropolis); fillers keep out of
  the lap's wrapped tail. With `height` alone the new tarmac stood 0.3-0.6 units off the slices and the player's pitch
  jumped 11-15 times over 6° on Diablo Canyon; now 7 (Phase 16: 6).
- The edge scan bridges holes up to 8 units (`VERGE_EDGE_GAP`).
- The start band: as wide as the road anywhere in its 12 units; its cuts are clipped as polygons (Diablo Canyon's two
  skewed head quads were dropped whole: 8 units of nothing at the line); a head quad's part behind the band is listed
  with the lap's tail; the segment walk keeps its point for a quad just past the line whose front reads as just before.
- The wall: overlaps the grass by 2.5 units (`WALL_OVERLAP`; 1-unit gaps at ~42 units out on bends).
- TGP: 34 657 words left (Phase 16: 43 077; the floor is 30 000). Drive suite: 46 passed.
