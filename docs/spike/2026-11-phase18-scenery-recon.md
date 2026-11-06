# Phase 18 recon: the Saturn scenery layers and backdrops (1 Nov 2026)

Pascal after Phase 17: "work on the side of the road and the background that seem missing compared to the Saturn
version". The converted courses draw only Saturn tile group 0 (road and ground) and group 4 (props). Scripts in
the session scratchpad `scenery/` and `saturn/`; spike builds in `out/scenery/`.

## 1. Groups 0-3 are layers, not variants

`docs/formats/saturn-trck.md` and the Phase 4 write-up called groups 0-3 "one group per variant" that "stack when
drawn together". Measured against the converted road (`layers.py`, `offroad.py`: each polygon's centre against the
centreline, its height against the road's and against the g0 polygon under it), they are layers of one picture:

| Group | Content | Polygons | On the road (< 12 units) | Over g0 at its height | Off the road, nothing of g0 under it |
|---|---|---|---|---|---|
| g0 | road and ground (built) | 1 005-1 674 | 401-855 | - | - |
| g1 | terrain: hills, cliffs, water, snow | 1 785-2 633 | 73-181 | 0-24 | 1 194-1 864 |
| g2 | road paint: edge and centre lines, start area, overpass shadows | 1 399-1 856 | 526-1 060 | 367-1 001 (median 0.04-0.18 above) | 292-564 |
| g3 | structures: trees, fences, Pacific's boat, Alpine's cable car; some flat decals | 595-1 036 | 295-442 | 191-324 | 94-435 |

g1 fills the ground beyond g0's verge instead of stacking on it; g2 lies on g0's road a few hundredths of a unit
up; g3 stands on both. Group 4 (props) is unchanged. The format doc's "variant" wording is corrected in Phase 18.

## 2. Spikes: fit, render rate, picture

`scenery/spike_groups.py` builds the ten-course set with other groups (the build's own converter, `convert_tiles`
with `groups=`) and drives entries with the autopilot, snaps and the render-rate log:

| Build | Fits | Pacific Coast rate | Alpine rate | Picture |
|---|---|---|---|---|
| g0+g4 (today) | yes | 28-29 | 28-29 | bare ground beyond the verges |
| g0+g1+g4 | yes | 28-29 | 28-29 | Pacific's cliffs and hills, Alpine's snow mountains |
| g0+g2+g4 | yes | 28-29 | - | edge lines, yellow lines, centre dashes, shadows; no fight with the road in the stills |
| g0-g4 | no: "no free range for 19024 bytes (largest free 6100)" | - | - | - |

The drive summaries are identical in all builds (scenery is not collision).

## 3. Budget

Polygon ROM free for scenery in the stock set: 2 518 KB in two runs (largest 1 376 KB); today's build uses 969 KB.
Colour table: 29 663 free entries; g0+g1+g4 used ~7 800 for all seven.

| Groups, all seven courses (`group_bytes.py`) | KB today (two 40-byte records a quad) | KB with edge chains (`chain.py`, estimate) |
|---|---|---|
| g0+g4 | 969 | 793 |
| g1 | 1 283 | 1 091 |
| g2 | 899 | 689 |
| g3 | 448 | 382 |
| all (measured together) | 3 543 | 2 955 |

The encoder (`polyrom.encode_object`) spends a link-0 record (the "old" edge) and a link-2 record (the quad) on every
quad. Any record with link 1, 2 or 3 draws `(old_p1, old_p0, p0, p1)` and then keeps, as the next old edge, one of
the drawn polygon's three other edges (link 2: `(p0, p1)`; link 1: `(old_p0, p0)`; link 3: `(p1, old_p1)`), so a
polygon that shares an edge with the previous one (reversed, as neighbours in a consistently wound mesh do) costs one
record. g1 is ~55 % triangles (repeated point); they chain the same way. A greedy chain per cell and colour saves
15-23 %; everything then still needs ~440 KB more than the 2 518 KB free. Pascal's call: keep all the paint and
structures and thin the distant terrain (g1) until it fits.

## 4. Saturn reference

Mednafen 1.32.1 (Homebrew) with Pascal's EUR BIOS (`~/.mednafen/firmware/mpr-17933.bin`, local only) runs the
Saturn disc. `saturn/drive.py` drives it by key events (Warp has Accessibility) to a Practice race on any course and
saves a state and snapshots: all seven converted courses plus Big Forest, Bay Bridge and Acropolis
(`saturn/overview.png`). These are the visual references for the comparison.

## 5. Backdrops (Phase 18b, separate plan)

- Saturn: NBG0 in 8 bpp cell mode; VDP2 VRAM cells 1-5120 hold the whole decompressed `BGS*1` panorama, four
  320×256 quarters 40 cells wide, a seamless 1280×256 256-colour image (all ten courses extracted from the states).
  That is the oracle for the `BGS` decompressor.
- Arcade: the System 24 tile chip (MAME `S24TILE`): character RAM `0x780000-0x7fffff` (8×8, 4 bpp, 32 bytes, a
  16-colour palette per tile), tilemaps `0x700000-0x70ffff`. The originals upload 76-102 KB of characters (phase 0,
  `0x7e0000`+) and a palette (phase 1, `0x900c00`); how the tilemap is built and scrolled with the heading is open.
- Data-bank room after today's build: bank 1 450 KB (four courses), bank 2 541 KB, bank 3 631 KB.

## 6. Outcome for the plan (18a)

- Chain edge-sharing polygons in the encoder (round trip through the decoder is the oracle).
- Convert groups 0-4; drop terrain hidden just under the road; thin small terrain far from the road, per course,
  until the set fits with margin.
- Gates: the build fits; every course keeps the render rate (min ≥ 27 per 57 frames); the drive suite holds; a
  capture per course next to the Saturn's for Pascal.

## 7. Outcome (Phase 18a, `docs/superpowers/plans/2026-11-01-phase18a-scenery-layers.md`)

- The encoder chains polygons that share an edge: today's layers 969 → 828 KB (12-15 %, less than §3's estimate,
  which let any exit follow); MAME snaps of the chained and unchained encodings differ in at most 0.032 % of pixels.
- Terrain thinning by area cannot fit the set (3 050 KB at no thinning, 2 904 KB even at 300 units²: terrain polygons
  are large). The polygon ROM's free space is the erased tail of every 2 MB chip (seven runs, 3 759 KB; Phase 1 listed
  the two largest): all five layers fit with nothing thinned, 708 KB left. `CoursePlan.terrain_thin` stays 0.
- Terrain under the road: measured against the drawn road (g0) no course has terrain 0.3-3 units under it within 12
  units of the centreline (Metropolis's and Diablo Canyon's 83 / 62 lie above it). The planned filter measured against
  the collision profile instead (up to 5.8 units off the drawn road on Pacific Coast) and cut 7 visible verge polygons
  there; the review removed it (every polygon of every layer is drawn).
- Render rate 28-29 on all seven (`RATE_FLOOR` 27, gated per course); drive suite 46 passed; TGP 34 657 words left.
- Captures (`out/p18/media`): the car is drawn in 97.8-100 % of on-road frames after the start; the misses are the car
  turned, spinning or blinking at a put-back. The road paint shows no one-frame drop-out over 115 full-rate frames on
  Pacific Coast, Alpine, Surfers Road and Diablo Canyon. `spike/scenery_compare.py` sheets put each course beside the
  Saturn's; the backdrop remains the host's (Phase 18b).
