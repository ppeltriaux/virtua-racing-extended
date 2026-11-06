# Saturn vs arcade: the three shared courses (Phase 3, Task 7)

Reproduce: `source local.env && .venv/bin/python spike/compare_bigforest.py out/p3/compare`
(fits Saturn slice centres onto the arcade centreline, 8 starting orientations, ICP with
a similarity fit; pictures in `out/p3/compare/overlay_<n>.png`).

| | Big Forest | Bay Bridge | Acropolis |
|---|---|---|---|
| Saturn slices (with centre) / arcade points | 430 / 338 | 287 / 418 | 409 / 592 |
| fitted scale (arcade units per Saturn unit) | 11.74 | 11.61 | 11.70 |
| rotation / mirror | 180° / none | 180° / none | 180° / none |
| translation (arcade units) | (1.6, 1.2) | (0.6, 5.4) | (1.6, −3.8) |
| rms residual (arcade units) | 12.7 | 12.9 | 7.7 |
| median slice width (Saturn) → arcade road 26 | 2.40 → ratio 10.8 | 2.59 → 10.0 | 2.08 → 12.5 |
| arcade lap length (arcade units; Saturn slices are not lap-ordered yet) | 3,430 | 3,321 | 4,349 |
| Saturn grid cell (units) | 3.14 × 7.04 | 3.42 × 7.09 | 5.34 × 5.89 |
| Saturn tile lattice | 4 × 9 | 5 × 8 | 7 × 7 |

## The transform the converter must use

`arcade = −11.7 × saturn` on both axes (a 180° rotation about Y, no mirror), with the
origins coinciding to within a few arcade units. One constant serves all courses:
**11.7 arcade units per Saturn unit** (the width-based figure, 10–12.5, varies with
how each course's slices were authored; the position fit is the better estimate).
A Saturn 16-unit tile is 187 arcade units, larger than the arcade's own tile cells
(≈105 × 125), so a converted course's tile grid is re-cut, not mapped 1:1.

## Correspondences and gaps

- Saturn slices (≈1 unit long, 11.7 arcade) are finer than arcade centreline points
  (≈10 units apart): the converter resamples the slice chain into road points and
  derives the heading from the slice planes. No AI line has been identified in the
  Saturn data yet (the 32-entry 24-byte tables are candidates); if none exists, the
  arcade's four AI lines are synthesised as offset copies of the centreline.
- Saturn segment angles (banking/slope) and normals exist; the arcade keeps elevation in
  the TGP cell data (M1b) and only a flat centreline on the V60 side.
- Saturn ground tiles (four variants) and props map onto arcade tiles (world-space
  objects in polygon ROM); the Saturn's `attr_a/attr_b` face attributes and RGB555
  colours map onto the arcade's palette/texture table (M3).
- Arcade data with no Saturn source: segment array (derivable), collision map
  (derivable from slices), surface table, graphics-upload directory (backdrop; Saturn
  cell compression still unknown), tile pointer table (derivable).

Not reported (plan Task 7 asked for them): per-point correspondence and heading agreement, which need the slices in lap order first.
