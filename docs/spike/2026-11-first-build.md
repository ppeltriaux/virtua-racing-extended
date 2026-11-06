# Spike log: first build — Saturn Big Forest scenery in the arcade engine (Nov 2026)

Phase 4, Task 5. `spike/first_build.py out/p4/build` converts the Saturn
Big Forest tile lattice (groups 0–3) and props (group 4) into arcade
polygon-ROM objects, writes them into the Big Forest tile grid of a patched
`vr.zip`, then runs the original and the patched set through the same
60-second autoplay (course 0, snapshots at frames 1700 / 2400 / 3200) with
the render-rate probe on.

## Result

**The patched set boots, the race starts, and the arcade engine draws the
Saturn scenery at the arcade's own render rate.**

| | original | patched |
|---|---|---|
| quads converted | — | 6,099 (0 outside the grid) |
| cells written | 69 (arcade) | 69 |
| colour-table entries used | — | 1,182 of the 47,432-entry free run at 0x7c6b8 |
| polygon bytes | — | 492,336 in the 0x2a7ca0 hole |
| largest cell object | — | 574 records (cap 5,500) |
| list switches / 57 frames, race | 28–29, mean 28.5 | 28–29, mean 28.5 |

`out/p4/build/compare.png` (local build output, not committed): top row original, bottom row
patched, frames 1700 / 2400 / 3200.

What is right:

- Saturn trees, grandstands, the bridge and the terrain all appear in the
  right cells of the course at arcade detail; the road, cars, HUD and
  minimap are the arcade's and unaffected.
- No drop in render rate with the Saturn geometry in place (both runs hold
  the every-other-frame cadence measured in the spec).
- The tile table rewrite round-trips (69 non-empty records).

What is wrong (the known-deviations list starts here):

1. **Overlapping terrain layers.** All four tile groups span the whole
   course (per-group quads 1448 / 1674 / 1980 / 804; extents all
   ≈ x −350..+270, z −600..+790 in Saturn units) and drawing them together
   produces stacked, interpenetrating ground surfaces. Group 0 is flat
   (y 0..11), group 1 carries the relief (y −34..+51), groups 2 and 3 sit
   between. The Saturn must pick among them (by distance, or by a visibility
   flag the decoder does not yet read). Next step: one build per group to
   see which single group matches the Saturn's own picture.
2. **Ground covers the road.** The Saturn ground polygons sit at the same
   height as the arcade road, which is drawn from the data bank, and win
   the depth test in places (frame 2400). Either the arcade draws its ground
   in the tile objects (so the converted ground must omit the road corridor)
   or the Saturn ground needs a small negative y bias.
3. **Pit buildings gone.** The arcade's start-line pit complex lived in the
   replaced tile cells; the Saturn equivalent is in a group we have not
   identified (or in the backdrop). Expected for a tile-only build.
4. **Vertical sign unverified.** YSIGN = +1 is still the ruling; the
   relief in the patched frames is plausible but has not been compared
   against a Saturn screenshot of the same spot.

None of these is a renderer limit: object count, colour entries and polygon
bytes are all well inside the holes found in Phase 2.

## How the pieces fit

Saturn `TRCKBIGF` → `decode_course` → `course_quads` (scale 11.7, 180°
turn, y up) → `cell_grid_from_arcade` (fitted from the arcade's own tile
centroids: x0 ≈ −943, z0 ≈ −1003, cell ≈ 118 × 125) → `bin_quads` → per
cell `assign_colours` (nearest Big Forest palette entry, one colour-table
entry per distinct colour per cell) → `encode_object` (no-cull records) →
`patch_course_tiles` (polygons into the first hole, colour entries into the
free run, 16-byte tile records rewritten, unlisted cells emptied) →
`RomSet.to_zip`.

## Tooling added

- `vrtools/mame/lua/renderrate.lua` + `VR_RATE_LOG`: counts display-list
  select toggles (`0x680000 & 0x40`) per 57 frames; `runner.parse_rate`.
- `VR_SNAPS`: snapshot frames for `autoplay.lua`.
- `spike/first_build.py`: the whole pipeline in one script; `stats.txt`
  per cell, `rate.txt` per run, `compare.png` montage.

## Addendum (Phase 6, Task 1): the tiles were half a turn off

Phase 6's recon found that `course_quads` placed the Saturn tiles rotated 180°
relative to the road slices (the slices are the verified frame: Phase 5's
collision matched the arcade lanes within 3 units). With the tile frame fixed
(`tile_to_arcade`), Saturn Big Forest tiles overlap the arcade tile geometry at
Jaccard 0.82 (0.58 before), the Saturn ground covers 90 %+ of Alpine's road
centres, and the rebuilt montage (`out/p6/first_build/compare.png`, local)
shows the Saturn road, kerbs and verges exactly under the arcade's road with
the pit markings at the grid. Of the deviations above, items 2 ("ground covers
the road") and 3 ("pit buildings gone") were this bug; item 1 (the four tile
groups stacked) stands. Render rate unchanged (28–29 / 57 frames).
