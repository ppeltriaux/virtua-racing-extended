# Phase 90 recon: the PS2 disc (Sega Ages 2500 Vol. 8, Virtua Racing FlatOut) and its additional courses

Status (26 Nov 2026, fix round 1, §18): pack 2 ("Virtua Racing Extended: PS2 Tracks") is built by `vrtools build --pack ps2`
from the arcade set and the PS2 disc; pack 1 is held to the released v0.4.1 by a standing test. §0-§11 are the recon of 25 Nov
("recon only" then). Base: main at dd8ca06. Pascal: "start the work on
the portage of the ps2 additional tracks". The source is the owner's own disc image (git-ignored). Scratch (git-ignored): `out/p90/disc/`: the ISO, the extracted file system
(`fs/`), every archive unpacked (`unpacked/`), pictures looked at (`pics/`), and the throwaway readers (`scripts/`: `bin2iso.py`,
`unpac.py`, `unpack_all.py`, `model.py`, `vcp.py`, `pat.py`, `tm2.py`, `calib.py`, `shapecmp.py`, `polycount.py`). Nothing of
the disc is in the tree. No emulator was run and nothing was downloaded.

**Since (26 Nov):** the session lead accepted §5's step. The readers are in the tree as `vrtools/ps2/` (tests on synthetic
bytes in `tests/test_ps2.py`; the disc test reads `VR_PS2_DISC`). The budget dry run for the three additional courses is §6.
It was measured against the room study (`docs/spike/2026-11-phase90-more-courses-room.md` on branch
`phase90-more-courses-room`). Its scratch is `out/p90/dry/`.

Marks: **[V]** verified on the disc's bytes (or against the arcade set through `vrtools`), **[I]** inferred, **[?]** not established.

## 0. The answer in brief

- **Six courses, three additional** [V]: Big Forest, Bay Bridge, Acropolis (the arcade's) and **Mountain, Island, Beltway**
  (names from the game's own menu text sheet `CF/op10.tm2`; internal prefixes `MOU`, `ILA`, `MEG`). None is a Saturn
  course: shape fits against the seven Saturn laps are no better than chance (§2).
- **Everything opens** [V]. The disc is a plain ISO 9660 CD (MODE2/2352). Course data sits in `.PAC` archives compressed
  with plain LZSS (Okumura's, 4 KB window). A 40-line reader unpacks all 40 archives byte-exact. The files inside are
  float vertex arrays, triangle lists and point lists, with no further packing.
- **Arcade units, arcade frame** [V]. On the three shared courses, the PS2 racing line fits the arcade centreline at
  **scale 1.00** (0.998, 1.0005, 0.9955). The fit needs a half turn about the vertical, and its origin lands on the arcade's
  road point 0 within 4 units. The PS2 data was built from the arcade's own coordinates. A PS2 course needs no scale fit,
  unlike the Saturn ones (10.4–11.7).
- **Flat-shaded look** [V]. The scenery is textured only in name: 99–100 % of triangles sample a single colour
  swatch from a 128×128 atlas, with grey prelit vertex shading. That converts to the arcade's flat colours directly.
- **The polygon count is the cost** [V]. A full course is 22,800–39,600 scenery triangles, plus trees and shadows. The
  disc's own split-screen versions hold 10,000–18,700, against the ~1,300–2,050 scenery quads a Saturn conversion placed
  in Phase 8. A 5–10× reduction is needed (merging triangle pairs into quads gives up to 2×, thinning gives the rest).
  **Corrected by §6's measurement:** since Phase 18's terrain layers, a Saturn course holds 10,400–12,000 records (about
  455 KB). The split-screen set with its triangles paired is already at that level for Island and Mountain. Beltway
  needs about half its faces cut.
- **Verdict:** all three can be converted with the pipeline's ideas. About half of `vrtools/convert/` carries over
  (centreline and AI lines, collision quads and cells, tiles and colours, placement, gates, map, race tables). What's
  new is a PS2 reader, a lap built from a triangle soup instead of Saturn slices, and stronger decimation. **Room in the
  arcade ROMs for courses 11–13 is the gating unknown.** It is outside this recon: the polygon ROM had ~155 KB free after
  Phase 33.

## 1. The disc

| item | what it is | evidence |
|---|---|---|
| `.bin`/`.cue` | one MODE2/2352 data track, 152 MB. User data at +24 of each 2352-byte sector gives a 132 MB ISO 9660 image (bsdtar lists it) | [V] |
| `SYSTEM.CNF` | `BOOT2 = cdrom0:\SLPM_624.43;1`, VER 1.03, NTSC | [V] |
| `SLPM_624.43` (1.0 MB) | the game: ELF32 MIPS (EE). Strings name the course archives (`%sCC%02d.PAC`, `%sCCBIN%02d.PAC`, `%sCCDIV%02d.PAC`), the collision prefixes and source files (`myCF_CourseSelect.c`). No ELF symbol table found by a quick parse | [V] |
| `MODULES/*.IRX`, `IOPRP280.IMG` | IOP modules (sound, pad, memory card, CD streaming) | [I] by name |
| `DATA/COURSE/` | 18 archives: `CC00..05` (course objects, collision, paths, sky), `CCBIN00..05` (one-player scenery), `CCDIV00..05` (split-screen: lighter scenery and its own collision) | [V] |
| `DATA/CAR`, `PIT`, `SIGNAL`, `EFFECT`, `MAPOBJ` | cars (`CAR`, `CARE`, `DIVCAR`), pit crew, start lights, effects, trackside animals and props (`cow`, `pony`, `yashi` palms), with three 10-point `YL0n.PAT` paths | [V] contents listed |
| `DATA/SYUHEN/CF.PAC`, `CFRACE.PAC`, `MC.PAC` | front end: menus, course-select models (`bi_ ba_ ac_ mo_ is_ be_sele.bin`), race HUD, the six minimaps `Cmap00..05.TM2` | [V] |
| `DATA/*.TM2` | loose pictures | [V] |
| `DATA/VREDM/VREDM.PSS` (20 MB) | the intro movie (MPEG program stream, `00 00 01 BA`) | [V] |
| `SOUND/IVB/VR01S..26S.IVB` | streamed music and voice (`IIVB` header) | [V] magic, [I] use |
| `SOUND/SE00..02.HD/.BD` | sound-effect banks (`SCEI` `Vers`/`Head` chunks: the standard libsd HD/BD pair) | [V] magic |
| `DUMMY64.BIN` | 64 MB of zeros (disc-layout filler) | [V] |

### 1.1 `.PAC` archives [V]

| offset | field |
|---|---|
| 0 | u32 = 1 |
| 4 | u32 unpacked size |
| 8.. | LZSS stream: flag byte, LSB first, 1 = literal byte, 0 = 2-byte reference `pos = b0 \| (b1 & 0xF0) << 4`, `len = (b1 & 0x0F) + 3`. 4096-byte ring buffer, zero-filled, write position starting at 4078 |

Unpacked: u32 file count, padding to 16, then per file 32 bytes (`name[16]`, `u32 size`, 12 zero bytes). File data follows
the table directly, each file padded to a multiple of 64 bytes. With that rule, every one of the 40 archives ends exactly
at its unpacked size. The sizes recorded are unpadded.

### 1.2 Pictures (`.tm2`, despite the name not TIM2) [V]

These are headerless TIM2-like images: a 64-byte header (not decoded), 8-bit or 4-bit pixels, then the CLUT at the end
(256 × RGBA with the PS2's 8-colour block swizzle, or 16 × RGBA), alpha 0x80. The menu sheets, course atlases and skies
decode and read correctly. The 4-bit minimaps `Cmap0n` did not decode cleanly (probably a swizzled or other width); they
are not needed (§4).

## 2. The courses

| # | course | prefix | arcade / additional | archives | evidence for the name |
|---|---|---|---|---|---|
| 0 | BIG FOREST | `BIG` | arcade | CC00, CCBIN00, CCDIV00 | menu text, select picture, scale-1 fit (§3.1) |
| 1 | BAY BRIDGE | `BAY` | arcade | CC01, CCBIN01, CCDIV01 | idem |
| 2 | ACROPOLIS | `ACR` | arcade | CC02, CCBIN02, CCDIV02 | idem |
| 3 | **MOUNTAIN** | `MOU` | **additional** | CC03, CCBIN03, CCDIV03 | menu text sheet `CF/op10.tm2` lists "BIG FOREST ISLAND BAY BRIDGE MOUNTAIN ACROPOLIS BELTWAY"; `mo_sele.bin` |
| 4 | **ISLAND** | `ILA` | **additional** | CC04, CCBIN04, CCDIV04 | idem; `is_sele.bin`; sea textures |
| 5 | **BELTWAY** | `MEG` | **additional** | CC05, CCBIN05, CCDIV05 | idem; `be_sele.bin`; buildings and lane markings in its atlas |

Index-to-name mapping: CC00–02 follow from the file prefixes and the calibration. The menu lists the courses in the order
Big Forest, Island, Bay Bridge, Mountain, Acropolis, Beltway. CC03/04/05 map to Mountain/Island/Beltway by prefix and by
the select files `mo_/is_/be_sele` [V for the names, I for "MEG" = Beltway, the only name left].

**Not Saturn courses** [V]: each new course's racing line was resampled to 300 points and fitted (similarity with free
scale, both directions, every start) to the seven Saturn laps decoded by `vrtools` (`out/p90/disc/scripts/shapecmp.py`).

| course | lap (units) | best three Saturn fits, rms as % of lap |
|---|---|---|
| Mountain | 3,761 | Surfers Oval 2.09 · Amazon Falls 2.87 · Pacific Coast 3.14 |
| Island | 3,085 | Surfers Oval 2.85 · Metropolis 3.30 · Amazon Falls 3.61 |
| Beltway | 4,099 | Pacific Coast 2.91 · Metropolis 3.03 · Alpine 3.60 |
| control: Big Forest vs Saturn | 3,507 | 3.13 (unrelated courses) |
| control: Big Forest vs arcade Big Forest | | **0.23** (the same course) |

### 2.1 Where each course's data is (one-player set)

| file (CCnn / CCBINnn) | what it is | evidence |
|---|---|---|
| `XXX_ATnn.VCP` (12–16 per course) | **road and ground collision** triangles, per section (atari) | [V] format; [I] name |
| `XXX_KBnn.VCP` | **wall** collision, the same format: vertical triangles up to ±100 high, one attribute (kabe) | [V] |
| `NORMAL.PAT` | **the racing line**: 41–97 sparse points round the lap from the start line. It fits the arcade centreline at 7–9 units rms | [V] |
| `DIRLINE.PAT` | a second line of the same length, offset a few units: the on-road "direction line" guide (`CCDIV03` has a `dirline.bin` model) | [V] shape, [I] use |
| `RETURNnn.PAT` | reset points after a crash (unordered, 112–138) | [V] unordered, [I] use |
| `CAMnn.PAT` | replay or attract camera points, above the road | [V] |
| `PIT00/01.PAT` | pit-lane paths: Big Forest, Acropolis, **Island**. Mountain and Beltway have none | [V] |
| `chk.bin` | **checkpoint gates**: planes across the road at lap fractions 0, ~0.35–0.44 and ~0.68–0.76 on every course | [V] positions |
| `st00..02.bin` | start gantry or banner at the origin, 3 states | [V] position, [I] use |
| `fl00/01.bin` | animated flags at the start (`Anime`/`Skin` chunks); Big Forest, Acropolis, Mountain | [V] |
| `sky00.bin` + `sky0a..3b.tm2` (+ `sea0..3`) | the sky: a 40-triangle dome carrying 256×256 8-bit photographic skies, two halves × four variants (weather/time: the executable has FINE, CLOUDY, DAYTIME, EVENING) | [V] |
| `CCBINnn/NN.bin` (12–16) | **section scenery**, one mesh per section, world coordinates | [V] |
| `CCBINnn/trNN.bin` | trees and props per section (Big Forest, Acropolis, Island, Beltway) | [V] |
| `CCBINnn/tunNN.bin` + `ton.TM2` | tunnel lamps (orange vertex colours): Bay Bridge, Island | [V] |
| `CCBINnn/CCKGnn`, `CCSHnn` | **shadows**: black, horizontal, at ground level | [V] |
| `CCBINnn/cous00.tm2` (+ `cous00b` on Beltway) | the course atlas, 128×128 8-bit | [V] |
| `CFRACE/Cmap0n.TM2` | minimap picture | [V] by name and size |
| race tables (laps, times, opponents' speeds) | **not found in the course files**; presumably in the executable | [?] |

## 3. The data's shape

### 3.1 Coordinates and scale [V]

The PS2 world uses floats in arcade units. `calib.py` fits `NORMAL.PAT` (resampled by arc length) to the arcade line 0
(`vrtools.arcade.bank.all_lines`):

| course | scale | rotation | rms (units) | PS2 origin in arcade | arcade road point 0 |
|---|---|---|---|---|---|
| Big Forest | 0.9984 | 180° | 8.0 | (−189.5, −398.9) | (−193.0, −402.8) |
| Bay Bridge | 1.0005 | 180° | 7.3 | (−203.3, 0.5) | (−205.4, 2.5) |
| Acropolis | 0.9955 | 180° | 9.0 | (−317.2, −191.3) | (−319.7, −190.8) |

The mapping is therefore arcade (x, z) = (−x, −z) + road point 0, the same sign pattern as `geometry.to_arcade` for Saturn
slices, with SCALE 1. Every course starts at the origin heading −z. The vertical axis points **down**: cameras sit at
y −2..−20 over a road at y ≈ 0. Tarmac height ranges are small: Mountain −8.9..10.2, Island −8.3..0.2, Beltway
−11.0..16.0. **Measured in §6** [V]: matching PS2 tarmac triangles to the arcade's own collision quads at the same place
gives arcade y = −1.05 / −0.99 / −1.04 × PS2 y + 30.1 / 29.9 / 3.8 (Big Forest / Bay Bridge / Acropolis). The
correlations are −0.96..−0.985, with residuals of 0.6–2.0 units. So the full mapping is arcade = (−x, −y, −z) + the host's
start, scale 1 on every axis.

### 3.2 Model files (`.bin`: chunks `Frame`, `Micro`, `Shape`, `Hrchy`, optional `Tim2`, `Anime`, `Skin`) [V, partly]

Header: u32 1, two zeros, chunk count, then 16-byte entries (`name[12]`, u32 offset). Each file seen holds **one triangle
list**, introduced by `(0, n×16, 0x1813, n)` and followed by four arrays of `n` float vec4s:

| array | content |
|---|---|
| 0 | position (x, y, z, 1), world coordinates (the bounding boxes match the collision sections) |
| 1 | normal (nx, ny, nz, 1) |
| 2 | texture coordinate (u, v, 1, 0) |
| 3 | vertex colour (r, g, b, 128) as floats; 99–100 % grey (prelit shade) on the scenery |

Non-indexed: every three vertices make a triangle, and quads appear as two triangles. The `Tim2` chunk names its
texture (`cous00.tm2`, `sky0a.tm2`, `ton.tm2`). `Frame`/`Micro`/`Hrchy` were **not decoded**. For the static scenery they
look like a single identity node (positions are already world), but that is unverified for the animated `st`/`fl` files.

**Colour [V]:** the atlas's upper-left quarter is a grid of solid colour swatches. Sampling the atlas at each triangle's
three UVs gives one colour (±8) for 100 % of Big Forest's and Island's scenery triangles, 99.6 % of Mountain's and
99.0 % of Beltway's. Swatch cells used: 34, 62, 41 and 126. The remainder are real textures (Beltway's windows and lane
markings, the start banners). The conversion colour is the swatch colour × the vertex grey, then quantised to the arcade
palette.

**Polygon counts (triangles)** [V, `polycount.py`]:

| course | scenery `NN` | trees `tr` | tunnel | shadows KG+SH | split-screen scenery + trees (CCDIV) | sections |
|---|---|---|---|---|---|---|
| Big Forest | 26,688 | 7,379 | – | 3,965 | 10,847 + 379 | 14 |
| Bay Bridge | 28,736 | – | 240 | 7,096 | 10,138 | 14 |
| Acropolis | 36,586 | 6,194 | – | 4,991 | 12,730 + 926 | 16 |
| **Mountain** | **39,611** | – | – | 4,444 | **11,965** | 14 |
| **Island** | **22,823** | **3,632** | 252 | 3,045 | **9,979 + 2,119** | 12 |
| **Beltway** | **28,737** | **12,147** | – | 4,798 | **18,673 + 6,110** | 14 |

For scale: a Saturn conversion places ~1,300–2,050 scenery quads and ~484 KB of polygon ROM per course (Phase 8, Phase 33
recon). The arcade frame budget is 5,500 records (Phase 28).

### 3.3 Collision (`.VCP`) [V, partly]

| offset | field |
|---|---|
| 0 | i32 ×4: grid bounds in cells (min x, min z, max x, max z). Consistent with a 6.0-unit cell on all 168 files, with 1–7 cells of margin [I] |
| 16 | f32 6.0 (cell size [I]) |
| 20, 24 | u32 triangle count, twice |
| 28 | per triangle 80 bytes: three vertices (x, y, z, 1.0) as floats, then 8 words: `0, 0, k, 0, attr, 0, 0, 0` (`k`: a near-constant word per file, meaning [?]) |
| then | the per-cell triangle lists (u16), not decoded; not needed, since the converter builds its own 16-unit cells |

`attr` low byte, measured by distance from the racing line [V numbers, I meaning]:

| low byte | where | meaning |
|---|---|---|
| 0 | median 3–6 units from the line, most of the area | tarmac |
| 1 | 11–15 units, thin strips | kerb or road edge |
| 2, 3 | 17–24 units | verge (grass, sand) |
| 0xa, 0xb, 0xd | on tarmac / at the edge line / far | [?]: markings, pit, off-road |
| walls (KB) | 1 throughout (a few 0 and 0x702) | wall |

The high byte (0x00, 0x0a, 0x14, plus 0x04/0x0e/0x18 on Mountain) is spread evenly over every kind: meaning [?] (sound,
grip or shade variant). Counts per course (AT/KB): Mountain 7,756/1,712, Island 4,764/1,230, Beltway 2,042/1,394 (Big
Forest 4,579/1,258). Tarmac area ÷ lap gives the mean width: Mountain 17.8, Island 25.0, Beltway 19.2. The road
half-width is about 12–13 units, as on the arcade (`model1-course-tables.md` §4).

### 3.4 Paths (`.PAT`) [V]

The layout is a u32 count, then 32-byte records: x, y, z as floats and 20 zero bytes. The lines are sparse (one point per
straight end and a few per bend), so they must be densified along the tarmac before they become a 10-unit arcade
centreline.

## 4. Verdict per additional course

What carries over from `vrtools/convert/` (all three):

- `road.road_tables` (centreline, seven AI lines, segments) once a Lap exists;
- `collision` (quads, 16-unit cells, surfaces) and `place` (spawn at the template's road point 0, a translation only,
  since scale and orientation already match);
- `geometry.convert_tiles` / `CellGrid` / `thin_quads` with a new PS2-to-`WorldQuad` adapter;
- `gates` (checkpoints from `chk.bin`), `race` (times), `hudmap` (the map from the centreline, so `Cmap` is not needed);
- `backdrop` (needs a new input: the 256×256 sky halves instead of a Saturn BGS panorama);
- `reverse`, and the weather cover from tunnels.

What's new:

1. A PS2 reader: PAC, models, VCP, PAT (formats above, ~300 lines).
2. **A Lap from a triangle soup.** The Saturn path orders road slices (`lap.order_slices`). Here, the slices would be cut
   across the densified `NORMAL` line on the tarmac triangles (`attr & 0xff == 0`), giving the left and right edges and
   the heights.
3. Triangle-to-quad pairing for collision and scenery.
4. A scenery reduction starting from the split-screen (`CCDIV`) meshes, with shadows dropped (§6 measures it: pairing and light thinning for Island and Mountain, about half the faces for Beltway).
5. Swatch-colour sampling.

| course | verdict | specific risks / unknowns |
|---|---|---|
| **Island** | **Convertible; the easiest.** The smallest scenery (9,979 + 2,119 split-screen) and the shortest lap. Has a pit lane like the arcade's | tunnels (`tun07/08`: lamps to drop or flatten, cover and tunnel-sound flags to set); the sea as backdrop; 2–3 tunnel stretches to check under the arcade's draw order |
| **Mountain** | **Convertible**; the most geometry (39,611 full, 11,965 split-screen), no trees file | the largest reduction; the most elevation (19 units of tarmac height) and a narrow road (mean 17.8), so collision and wall fencing need care; no pit-lane path |
| **Beltway** | **Convertible with more colour work**: the longest lap (4,099), many props (12,147 tree/prop triangles) | ~1 % truly textured faces (building windows, lane markings, second atlas `cous00b`) lose their detail as flat colour; the heaviest split-screen set (24,800); no pit-lane path |

Shared risks, from largest:

1. **Room.** The ten-course build leaves little polygon ROM (154,680 bytes after Phase 33, against a 150,000 floor),
   TGP words, bank space and select-screen slots. Three more courses do not fit as the set stands. This is a decision
   above this recon (see the parallel "more courses room" work).
2. **Polygon reduction** without losing the look: the arcade quads are flat like the PS2 swatches, so colour is not
   a risk; count is.
3. **Formats still open:** the `Hrchy`/`Frame` chunks (matter only if a file is not in world space), the VCP high byte
   and the 0xa/0xb/0xd kinds, the race tables in the executable.

## 5. Proposed first step

**A PS2 reader and an Island dry run (medium; about one session).** Write `vrtools/ps2/` (PAC + archive, model, VCP,
PAT) with tests on synthetic bytes only, and a spike that turns Island into the converter's intermediate products: Lap,
road tables, collision quads and cells, `WorldQuad` scenery from the split-screen meshes, colours. The spike reports
counts against the budgets (records per cell, polygon-ROM bytes, TGP words) without installing anything in a ROM. It
answers the reduction factor and the bytes a PS2 course needs, which is the number the room decision needs. Installing a
course (template bank, select slot, MAME drive) comes after the room question is settled.

## 6. The budget dry run (26 Nov)

Session lead: build the reader and run a budget dry run of all three additional courses through the converter's
measuring stages, nothing installed. Report each course beside the Saturn courses' rows from the room study, and say which
Saturn slot each would fit.

### 6.1 What ran

- **Readers (kept):** `vrtools/ps2/` (`pac`, `model`, `vcp`, `pat`, `picture`, `disc`, `course`), commit 0f30d87.
  `tests/test_ps2.py` has 15 tests on synthetic bytes and one disc test behind `VR_PS2_DISC`. All pass, with and
  without the disc. One finding from writing them: the VCP surface word is word 16 of the 20-word record (§3.3's
  `0, 0, k, 0, attr`); the recon's counts had already read that word.
- **Dry run (scratch, `out/p90/dry/scripts/`):** `ps2adapt.py` holds the adapters, and `dryrun.py COURSE HOST` runs one
  course. It is followed by `slotfit.py`, `thin3d.py`, `beltway_thin.py`, `saturn_frames.py` and `stills.py`. Logs and JSON
  are in `out/p90/dry/`, stills in `out/p90/dry/stills/`. Per course, the dry run does this:
  1. **Frame:** arcade = (−x, −y, −z) + the host's road point 0 and start height (§3.1).
  2. **Lap:** the racing line densified to 1 unit and smoothed. The tarmac band (kinds 0, 0xa, 0xb) is scanned across it
     every 5 units at the reference height, which keeps a crossover's lower road from being read. The band's middle is
     smoothed and scanned again every 8 units for the edges, the drawn ground (kinds 1–3, 0xd, capped at 40 units) and
     the walls (KB footprints hit by a lateral ray). This gives a `Lap` with one "slice" per section, then
     `lap.centreline` (10 units) and `road.road_tables`, unchanged.
  3. **Collision:** per section pair, a tarmac quad, a verge each side out to the drawn ground or the wall, and a 4-unit
     wall strip where a wall stands. Then `collision.merge_straights` and `collision.cell_lists`, unchanged.
     TGP words = list words + 16 × quads.
  4. **Data bank:** the real `blob.build_course_blob` (road part, collision map, surface table) and `build_variant_blob`
     for the reverse (8 lines, and the bank-1 courses' 3). The backdrop is the two sky halves (plus the sea picture
     below the horizon on Island) as a 1280 × 256 panorama, put through `convert_panorama` / `encode_panorama`, unchanged.
  5. **Scenery:** triangles with their swatch colour (§3.2) and vertex grey, in the arcade frame. Coplanar triangle pairs
     of one colour that make a convex quad become one quad. Then the core of `convert_tiles` (`bin_quads`, the course
     palette, `assign_colours`, the 5,500-record cap, `polyrom.encode_object`) gives polygon bytes, records per cell and
     colour entries. The HUD outline is `hudmap.encode_outline`.
  6. **Frame load:** Phase 28's visible-cell model (`out/p28/cellmodel.py`: 5 × 5 cells, ±45° wedge from 10 units back;
     Jaccard 0.84 against the logged lists). It sums scenery records at every road point in both directions. The same
     model was run on the v0.4.1 set (`out/p90/room/set`) for the comparison rows.
- **Hooks a proper build would add (none was added):**
  - `convert_tiles` taking a `WorldQuad` source instead of a `SaturnCourse`;
  - a `Lap` from generic cross-sections (`lap.order_slices` is Saturn-only);
  - `collision.slice_quads`/`saturn_collision` over generic cross-sections. This is the big one: the 3,000-line module
    reads verges, barriers, water and pit lanes from the Saturn course;
  - `preview.course_picture` taking quads (it reads the Saturn's terrain layer);
  - `convert_panorama` taking RGB.
- **Controls:**
  - PS2 Big Forest through the same pipeline gives 31,281 TGP words. The arcade's own Big Forest collision has 73,210
    (Bay Bridge 105,472, Acropolis 93,222): the arcade's is finer than any conversion.
  - Its split-screen scenery gives 11,444 records, the Saturn conversions' level (10,400–12,000), against the arcade
    original's 25,188.
  - The estimator's TGP density is 6.4–10.6 words per unit of lap. The seven Saturn courses' real builds are 7.6–10.0
    (mean 8.6). Hence the second TGP figure in §6.2: lap × 8.6.
- **Host fit:** Mountain does not fit Big Forest's start. One collision quad lands at z −1027, past the map's −1024. It
  fits Bay Bridge's and Acropolis's starts. Island and Beltway fit all three. Host choice changes nothing else
  measurable (±1 %).

### 6.2 Needs against the Saturn slots (bytes; TGP in words)

Saturn rows: the room study's §3 (measured on v0.4.1). PS2 rows: the proposed host, with scenery fitted to the proposed
slot (`slotfit.py`). Free today: polygon 18,552, TGP 7,631, bank 1 1,752, bank 2 206,908, bank 3 192,279, program
9,428 (no run over 2,252).

| course (bank / host) | polygon ROM | TGP words: estimator / 8.6 × lap | data bank: normal (backdrop) | reverse: 8 lines / 3 lines | program (est.) |
|---|---|---|---|---|---|
| **Island** (1 / Bay Bridge) | **437,200** (thin 6) | **29,347 / 26,650** | **163,916** (86,732) | 42,912 / **17,552** | **9,870** |
| **Mountain** (2 / Acropolis) | **437,440** (thin 3) | **39,788 / 32,280** | **166,188** (79,532) | **51,888** / 21,328 | **10,040** |
| **Beltway** (1 / Bay Bridge) | **487,536** (3-D thin 512) | **26,304 / 35,230** | **177,772** (88,204) | 55,488 / **22,288** | **10,070** |
| Pacific Coast (1) | 441,464 | 33,024 | 182,506 (89,700) | 25,360 (3) | 10,802 |
| Surfers Road (1) | 486,728 | 43,216 | 187,887 (88,292) | 28,896 (3) | 11,114 |
| Diablo Canyon (2) | 441,152 | 40,635 | 184,926 (84,184) | 66,118 (8) | 10,712 |
| Amazon Falls (1) | 481,312 | 26,583 | 161,346 (79,948) | 20,500 (3) | 11,274 |
| Metropolis (2) | 441,588 | 28,297 | 166,570 (80,432) | 40,144 (6) | 10,500 |
| Alpine (3) | 483,336 | 34,254 | 192,015 (94,388) | 63,522 (8) | 10,852 |
| Surfers Oval (1) | 434,640 | 38,688 | 176,324 (85,016) | 25,136 (3) | 10,836 |

Notes on the PS2 rows:

- **Program [I]:** the fixed slots (tile table 5,120, race blob 1,808, spawn list ≤ 768) plus 2 bytes per colour entry
  (1,089 / 1,174 / 1,187).
- **Lightning blob:** a course's lightning blob in bank 3 (12–27 KB on the seven) depends on its extent and was not
  computed [?]. A replaced course frees its own.

**The proposed pack (three for three):**

| PS2 course | slot | host | bank check (normal / reverse in the slot's places) | polygon | TGP |
|---|---|---|---|---|---|
| Island | **Pacific Coast** | Bay Bridge | 163,916 ≤ 182,506 / 17,552 ≤ 25,360 | 437,200 ≤ 441,464 | 29,347 ≤ 33,024 |
| Beltway | **Surfers Road** | Bay Bridge | 177,772 ≤ 187,887 / 22,288 ≤ 28,896 | 487,536: **808 over**, pooled | 26,304 ≤ 43,216 (35,230 by density, ≤) |
| Mountain | **Diablo Canyon** | Acropolis | 166,188 ≤ 184,926 / 51,888 ≤ 66,118 | 437,440 ≤ 441,152 | 39,788 ≤ 40,635 (32,280 by density) |

Each PS2 course's blobs fit inside the places its slot frees, in the same bank. Polygon and TGP are pooled (room study
§5c):

- **Polygon:** 1,362,176 needed against 1,369,344 freed plus 18,552 free.
- **TGP:** 95,439 words needed (94,160 by density) against 116,875 freed plus 7,631 free.

The program slots are the same size, and the PS2 colour entries are fewer than the Saturn's. Battery RAM, the
directory, the select screen and the ranking keep ten entries (room study §4).

**Why these slots:**
- **Island and Beltway take Bay Bridge as host.** Island is a coastal course with sea, and Beltway a city with a bay
  bridge feel. Bay Bridge's in-race tables, entity list and music come with the host.
- **Mountain takes Acropolis:** rock, like Diablo Canyon.
- **Other slots that pass:**
  - Island could also take Amazon Falls, but only 378 bytes of bank room would be left, and TGP would be 2.8 K words
    over unless pooled.
  - Island could also take Surfers Road.
  - Beltway could take Metropolis (bank 2 has 206,908 free besides).
  - Mountain cannot take Alpine (TGP 39,788 > 34,254, and Big Forest's start does not fit).

### 6.3 Display-list records a frame (scenery, model; median / p95 / max, normal · reverse)

| course | scenery records in all | normal | reverse | max + field p95 (2,200) + rain (~2,200) |
|---|---|---|---|---|
| **Island** (slot fit) | 10,765 | 1,318 / 2,474 / 2,953 | 1,282 / 2,675 / 3,917 | **8,317** |
| **Mountain** (slot fit) | 10,758 | 1,222 / 1,769 / 2,050 | 1,232 / 1,790 / 2,096 | **6,496** |
| **Beltway** (slot fit) | 11,984 | 1,375 / 2,058 / 2,498 | 1,354 / 2,096 / 2,533 | **6,933** |
| Saturn seven (same model, v0.4.1) | 10,444–11,989 | median 1,117–1,400, max 2,081–3,730 | median 1,055–1,397, max 1,941–3,182 | |
| arcade originals (same model) | 17,688–25,220 | median 2,197–3,018, max 5,336–6,441 | max 4,546–6,306 | |

The budget is **10,500 a frame**. The field's p95 (about 2,200) is Phase 28's measurement. The storm's share (RAIN peak
less the game's need, 2,000–2,300 on every course) comes from the weather findings' rate table. Every PS2 course stays
under the budget with the storm, with 2,200–4,000 records to spare. The start window, where cars, the gantry and the
figures take 3,000–4,300, was not modelled apart: it adds up to about 2,000 to the "field" column there. Island's reverse
peak (3,917) is the one spot to watch.

### 6.4 The reduction each course needs, and what it costs the eye

| course | one-player set | split-screen set | paired | slot fit | lost (stills under `out/p90/dry/stills/`) |
|---|---|---|---|---|---|
| Island | 26,707 tris | 12,098 tris | 7,169 faces (473 KB) | 6,606 faces, 437 KB | split-screen set: coarser cliffs, fewer lane dashes, 2,119 of 3,632 tree triangles. Thinning: 563 small faces over 40 units from the road, not visible at this scale |
| Mountain | 39,611 | 11,965 | 7,372 (486 KB) | 6,572, 437 KB | the split-screen set's coarser rock (the one-player set is 3.3× finer); 800 small far faces |
| Beltway | 40,884 | 24,783 | 14,024 (977 KB) | 6,915, 488 KB | **half the faces:** trees, lamp posts and sign detail go, building façades lose their window bands; some overhead structure is missing from the split-screen set itself |

The steps:

- **Pairing** is lossless: coplanar, one colour, convex. It merges 81 % of Island's split-screen triangles and 87 % of
  Beltway's into quads.
- **The split-screen set** is the PS2's own lower detail. Through this pipeline it lands at the Saturn conversions'
  density, about half the arcade originals' records.
- **The one-player set** is 1.1–1.6 MB paired, 2.4–3.7× a slot.
- **Beltway needs a different rule.** The converter's `thin_quads` judges a face by its xz area. A city's walls have
  almost none, so it removed building faces first (`beltway_2b_road.png`). The 3-D area (`thin3d.py`) keeps the
  buildings longer. A Beltway build should thin by true area, or per object.

### 6.5 What does not convert yet, and what it would take

| item | state | what it takes |
|---|---|---|
| **Race tables** (laps, times, opponents' speeds) | not in the course files. The executable has no symbol table; not searched further | the project's own rule, as for the Saturn courses: `race_blob_for` scales the host template's twelve time records by sector length, five laps, with `time_factor` / `pace` tuned by the owner's drives. The checkpoints come from `chk.bin`'s gates (lap fractions 0, 0.35–0.44, 0.68–0.76), as `gate_checkpoints` does with the Saturn's gates (a `ps2_gates` reader) |
| **Pit lane** (Island only) | `PIT00` (7 points) and `PIT01` (23 points) are paths. The lane is tarmac (kind 0): 33 % of Island's tarmac triangles lie within 6 units of `PIT01`, on the start straight (width p95 36.8) | a pit-lane polygon from `PIT01` and the tarmac band, in place of `collision.pit_lane_polygons(sat)`. Then `pit_entry_quad`, `pit_box` and `pit_lane_line` (HUD) as on the Saturn courses, and the reverse pit |
| **Tunnels** (storm cover, tunnel sound) | Island has two: road points 165–178 and 192–203 (lap 0.53 and 0.62), found as road points within 20 units of the `tun07/08` lamps. Mountain and Beltway have none. Beltway has overpasses | `CoursePlan.tunnels` from those stretches (automatic from the lamp meshes), tied to the drawn roof by a test as Phase 37 did. The storm's cover needs the roofs as `cover.py` reads them; Beltway's overpasses are to be checked the same way |
| **Reverse** | done in the dry run: `reverse_tables` on the PS2 lap, blob sizes in §6.2 | the reverse checkpoints, the reverse grid and the reverse pit as for the Saturn courses. The owner's drive picks lines (3 or 8) |
| **Select picture and panel** | not made. `preview.course_picture` reads the Saturn terrain layer for its colours | the hook taking quads (the PS2 split-screen scenery). The panel map comes from the centreline as now |
| **HUD map** | done: `hudmap` outline from the centreline, 1,864 / 2,064 / 2,224 bytes, counted in the polygon column | nothing new. The PS2's own `Cmap` pictures are not needed |
| **Backdrop** | measured (79.5–88.2 KB, 2,055–2,326 tiles), but the mapping of the PS2 sky halves onto 360° is assumed [I]. The PS2 skies are photographs without hills (the hills are geometry), so the arcade band shows sky over the far scenery cells | an owner's look; possibly the host's backdrop (`CoursePlan.backdrop=False` saves ~85 KB of bank) |
| **Beltway's second atlas** | which faces use `cous00b` is in the undecoded `Micro`/`Hrchy` chunks. The dry run samples `cous00` everywhere, so some Beltway colours are wrong | decode the material ranges (a small reader task) |

### 6.6 Unknowns left

1. **The real collision pipeline against the estimator.** Coverage fillers, bank splits, the start band and the pit lane
   add quads. The density check (8.6 × lap) puts all three within the slots, but Mountain is the tightest:
   39,788 against Diablo's 40,635.
2. **Beltway's look at a Saturn slot**, with half its faces gone. The owner's eye decides. The alternative is more
   polygon ROM from the room study's §5b (the gantry rework, about 180 KB) given to Beltway.
3. **The lightning blob per course**, the backdrop's sky mapping, the `cous00b` faces and the VCP kinds 0xa/0xb/0xd
   (surface sounds).

### 6.7 What a proper first build (Island installed in a pack) would take

1. **`vrtools/convert/ps2course.py`.** The adapters above made clean:
   - the frame;
   - the lap from tarmac and racing line;
   - sections, verges and walls;
   - paired swatch-coloured scenery;
   - gates from `chk.bin`;
   - the pit lane from `PIT01`;
   - tunnels from the lamp meshes.

   Plus the five hooks of §6.1 in `vrtools/convert/` (the collision one is the largest). About 2–3 sessions.
2. **The pack.** `vrtools build --pack ps2`:
   - a plan list per pack (room study §5c);
   - Island's `CoursePlan` in Pacific Coast's place (bank 1, Bay Bridge host, its TGP slot, program slots and ranking id);
   - a pack tag in battery RAM so saved times reset when the pack changes;
   - the per-pack tests.

   About 1–2 sessions.
3. **In MAME:** Island driven by the autopilot (render rate, collision coverage, the pit stop, the tunnels' sound), then
   the owner's look and drive, then the whole suite once for the pack (3.5 h). About 1–2 sessions.

Mountain and Beltway follow on the same code: Mountain in Diablo Canyon's slot, Beltway in Surfers Road's once its
thinning rule and the look are settled.

## 7. Island, drivable in MAME (prototype, 26 Nov)

Session lead: Island in a scratch ten-course set, in Pacific Coast's slot (bank 1, Bay Bridge's host), driven by the test
autopilot in headless MAME. This step does not build the pack's plumbing (no battery-RAM tag, no page, no notes).
Scratch is in `out/p90/island/`:
- `scripts/build_island.py` builds the set;
- `run_island.py` and `analyse_island.py` run and read MAME;
- `compare_sets.py` compares sets;
- `sheet.py` makes the stills sheet;
- `set/` holds the set, `runs/` the logs.

### 7.1 What is in the tree

- **`vrtools/convert/ps2course.py` (kept).** It holds §6's adapters made clean:
  - `Frame.for_host`: the host's road point 0 and its collision height there;
  - `build_lap` (the racing line, the tarmac band scanned at the reference height, then the band's middle);
  - `collision` (tarmac, verges, wall strips, `merge_straights`, `cell_lists`);
  - `attitude` (pitch along the lap, roll from the band's outer-third heights);
  - `scenery` (the split-screen set, pairs merged, `thin_quads` at 6);
  - `gate_points` from `chk.bin`, `tunnel_stretches` from the lamp meshes, `panorama` from the sky halves;
  - `convert` gathers these.
  - The tests in `tests/test_ps2course.py` use a synthetic ring course, with no disc.
- **Two hooks:**
  - `geometry.encode_cells` is `convert_tiles`' last stage on its own; `convert_tiles` now calls it.
  - `preview.course_picture(..., terrain=, ground=)` takes quads instead of the Saturn's layers.
  - **Proof that the Saturn path is unchanged:** `vrtools build` with the hooks (`out/p90/island/after`) is identical
    member for member (all three zips) to main's build (`out/p90/room/set`), and the build reports are identical.
- **One rule changed on the way:** the scenery takes the swatch colour **without** the PS2's vertex grey. The grey is
  the PS2's baked light. The first build drew Island near black because the arcade lit the faces again. Without the grey,
  it looks like the other courses (`sheet_island.png`).

### 7.2 The scratch set

- **The install** is a copy of `convert_course`'s steps for a `Ps2Conversion` (`build_island.convert_ps2_into`):
  - collision into Pacific Coast's TGP slot 7;
  - backdrop and road blob into bank 1, then the tile table, spawn list (Bay Bridge's start gantry; the arcade gantry
    frames), scenery cells, HUD outline and race blob;
  - the reverse variant with the bank-1 courses' three lines and grid, and no pit lane.
- **The other six Saturn courses** go through `convert_course` exactly as `build_all` calls them, and then through
  `ten_course_set` with the weather on.
- **The storm's cover tables are keyed by menu entry** (`weather/cover_geom.MARCHED`). The first build stopped there:
  entry 7 had tunnel flags but no cover table. The scratch script adds Island's two stretches to that registry for the
  build only, and the cover then marches the tunnels from the set's faces like Alpine's. A pack needs this as a real
  hook (cover stretches per plan, not per entry index).
- **Island's numbers:**
  - 386 sections and 309 road points (lap 3,099 units);
  - 1,495 collision quads (277 tarmac, 109 slices merged): 29,382 TGP words;
  - scenery from 12,098 triangles: 4,920 pairs, 569 thinned, 6,609 faces;
  - checkpoints (0, 129, 208) from the gates;
  - tunnels (165–178) and (192–203).
- **Room left in the whole set:** TGP 11,263 words (released 7,631) and polygon ROM 26,620 bytes (released 18,552).
  Island takes less than Pacific Coast in both.
- **What moved, against the released set (`compare_sets.py`):**
  - Every one of the nine other entries has the same road lines, segments and scenery records.
  - Surfers Oval and Surfers Road (after Island in bank 1 and in first-fit order) have new header addresses, HUD-outline
    addresses and colour-table entries; their content is the same.
  - Every entry's select-panel addresses (bank 0, re-rendered panels) and reverse records (the annex) moved.
  - Changed pages: bank 2 none, bank 1 162, bank 3 21 (the storm's per-course data), bank 0 15, program ROM 29,
    polygon ROM 432, TGP 114 (of 4 KB each).

### 7.3 Headless MAME (Island, entry 7)

Each run is 150 s under the autopilot on road line 0, with the clock held, the full field, and the rate test's three
measures (`vrtools.mame.framerate`).

| run | laps | lap times (from the green) | rate windows | overrun / worst V60 busy | stale lists | records peak / p95 (budget 10,500) | lists skipped |
|---|---|---|---|---|---|---|---|
| normal, DRY | 2 | 44.3 s (standing start), 39.7 s | 28/29 only | 0 / 10.97 ms | none in the stretch * | 5,437 / 4,665 | 0 |
| normal, RAIN | 2 | 57.7 s, 43.6 s | 28/29 only | 0 / 17.51 ms (deadline 18.9) | none * | 7,343 / 6,407 | 0 |
| reverse, DRY | 2 | 59.6 s, 41.0 s | 28/29 only | 0 / 11.24 ms | none * | 5,844 / 4,730 | 0 |

\* Two stale frames appear: 277 (the boot) and 1607, the pass right after the course load (1602), which the standing
check excuses as on main.

- **It loads:** the course words are (7, 0), so entry 7 on Bay Bridge's template. The HUD reads ISLAND, and Bay
  Bridge's start gantry stands on the grid.
- **Checkpoints and laps:** the checkpoints fire at road points 129, 208 and 0 (reverse 101, 180 and 0), and the lap
  counter reaches 2.
- **The rate holds** in all three runs. RAIN's worst pass, 17.5 ms, is above the Saturn courses' 15.1–17.1 ms but
  under the 18.9 ms deadline, with no stale list.
- **Where the autopilot leaves the road** (the collision log's quad under the player, against the build's surface
  table). It never touches a wall.
  - The S-bend before the first tunnel, road points 145–165: the road is about 19 units wide and turns 43–50° per
    50 units, left then right. The autopilot runs 10 units wide, and onto the verge on the second lap.
  - The hairpin at 210–215, the tightest corner (71° per 50 units).
  - Totals: 194 of 3,381 frames on the verge (DRY), 79 (RAIN), 71 (reverse). The off-course counter shows the same two
    places.
- **The opponents:** all fifteen run both laps, none is stuck in the last 10 s, and they spread over the lap.
  `race_log`'s jolts (an opponent's smoke counter starting): 59 / 65 / 80. No Saturn course was measured the same way
  for comparison.
- **RAIN on Island is safe:** it loads, keeps the rate, has cover in the tunnels (the scratch registry entry), and
  has no crash.

### 7.4 For the owner

- **The sheet:** `out/p90/island/sheet_island.png`. Six 4:3 pictures from the same autopilot run: the start, the far
  view (road point 100), inside the first tunnel (170), into the hairpin (205), the sea side (231), the run back to the
  line (280).
- **The play set:** `out/p90/island/play/launch.sh`, the p88 launcher's form (written, not run), with `NOTE.txt`
  (what is in, what is rough, what to look for).

### 7.5 Rough or missing

- **Pit lane:** none; the PS2's `PIT01` path is not built into a lane yet.
- **Times and pace:** the rule's defaults, untuned. A lap is 39.7 s for the autopilot.
- **The sea:** it does not read as sea in the stills. It is a few big faces in far cells, and the select picture's
  water test (`collision.is_water`, the Saturn's pure blue) finds none of the PS2's blues.
- **Narrow road:** the S-bend at 140–165 is about 19 units wide.
- **Cover registry:** the tunnels' storm cover needs that registry entry in the tree.
- **`report_lines`:** it reads Saturn-only report keys (KeyError `thinned`), so the scratch build writes a short report.
- **Best times:** they are those of the battery RAM's Pacific Coast slot.

### 7.6 What Mountain and Beltway would take next

- **Mountain** (Diablo Canyon's slot, Acropolis's host; it does not fit Big Forest's start):
  - the same code;
  - `Frame.for_host(rs, 2)` (start height 3.8);
  - a narrower road (mean 17.8 and p5 10 in §6), so the band scan's narrow sections need checking. The autopilot will
    struggle more than on Island;
  - no tunnels and no pit lane;
  - the flags at the start (`fl00/01`) are not converted, as on Island.
- **Beltway** (Surfers Road's slot, Bay Bridge's host):
  - a thinning by true area in `ps2course.scenery` (§6.4: the xz rule removes the buildings);
  - the `cous00b` atlas's faces (the undecoded `Micro` chunk);
  - almost no verges (walls along the road), which the collision already handles;
  - its overpasses: the band scan's reference height handled Island's crossing, but Beltway's flyovers want the storm's
    cover too, which is the same registry hook again.
- **For a pack, in the tree, for all three:**
  - the cover stretches per plan;
  - `report_lines` tolerant of a non-Saturn report;
  - the plan's source kind (Saturn or PS2), then the pack's tag and tests (room study §5c).

## 8. The look pass, and Mountain and Beltway as prototypes (26 Nov)

Scratch is in `out/p90/{island,mountain,beltway}/`. The build script `out/p90/scripts/build_ps2.py OUT PS2 SLOT NAME`
puts one PS2 course in one slot. Each set swaps only that course.

### 8.1 Why Island looked near black, and the rule now

- **Not the tones.** The palette colours Island's faces map to already sit in Bay Bridge's range per surface
  (`island/scripts/tones.py`, luminance p50):
  - verge 120 against Bay Bridge's 126;
  - ground 106 against 112;
  - roadside uprights 120 against 120;
  - road 72, against the Saturn path's road greys (mean 77.5, `geometry.ROAD_GREYS`).
- **The cause was the lighting side.** The PS2 frame is a point reflection of the arcade's, so the windings come out
  reversed. 82 % of Island's level faces had their lighting normal pointing up. The arcade's own ground faces point
  down, and so does the Saturn path's (1,272 of 1,272 level faces on Pacific Coast). So the road and the ground were lit
  from behind.
- **The rule (`ps2course.orient`):**
  - level faces point down;
  - other faces point away from the nearest centreline point;
  - the PS2 swatch colour is kept as it is, without the vertex grey (§7.1).
- **Result:** the road, verges, kerbs and lines now read at the arcade's tones (`island/sheet_island2.png`, with two of
  the first sheet's pictures beside the new ones).

### 8.2 The sea

- **Where it is:** the PS2's sea is one level plane at y 27.9 (arcade frame) under the whole course. That is 1.8 units
  below the lowest road point; the coast and the road stand on it. Its three blue swatches are kept.
- **What I tried:** raising it to 0.6 under the lowest road (`ps2course.lift_water`) changed nothing seen from the road.
  The coast stands 2–4 units above it, and it is just as hidden in the PS2's own geometry (the dry run's road-level
  renders show no sea either). The PS2 shows its sea through its sky dome's `sea0` band at the horizon. The
  arcade's sky panorama carries that band, but terrain mostly hides it.
- **Status: not solved.** The next try would be a lower horizon for Island's panorama, or a sea strip (a far ring of
  level quads at the waterline).

### 8.3 Bare, or emptier than the PS2?

- **Nothing is lost in encoding:** no cell is capped and none is outside the map. Island's thinning drops only small far
  faces (thin 192 at the slot's bytes).
- **The emptiness is the split-screen version's own.** Within 40 units of the road the one-player version has 2.2× the
  section faces (10,555 against 4,784), mostly level ones: road subdivision and markings. It has 1,742 upright faces
  against 639, and 1,272 prop faces against 942 (`island/scripts/bare.py`).
- **Cheap and valuable, now in:** the one-player trees and props within 40 units of the road (`NEAR_PROPS`), about
  +17 KB. The set's free polygon ROM pays for it, and far faces are thinned to keep Island in Pacific Coast's bytes.
- **Not in:**
  - the one-player version's roadside uprights (about 55 KB);
  - the tunnel lamps (172 faces, 12.4 KB).
  - Both need the pool to grow (the gantry rework).

### 8.4 The other converter changes

- **`ps2.model` reads one triangle list per texture.** The list header's first word is the texture's index. The reader
  had taken only each file's first list, so Beltway's split-screen set was 4,980 triangles short; they are its `cous00b`
  faces, which are now coloured from that atlas.
- **Kerbs inside the tarmac band.** The PS2's kerb strips (kind 1) are part of the collision's tarmac band. Separate
  kerb quads made Mountain's collision 56,437 words, past Diablo Canyon's slot.
- **Thinning by true area** (`thin_true_area`), for Beltway.
- **Scratch-only work-arounds in the build script:**
  - Beltway's select panel drawn from a coarser outline, and a one-colour select picture. Beltway's busier ones need
    more of bank 0 than it has: they ran into the weather's screen graphics.
  - A `W` letter for the panel (the panel font has no `W`).
  - The weather cover registry entry per swapped tunnel (§7.2).
- **The Saturn path is unchanged:** the released set built at the end of this pass is again identical member for member
  to main's (`island/after2`).

### 8.5 Island after the look pass

- **Build:** Pacific Coast's slot, scenery thinned (xz 192) to 439 KB with the near-road props.
- **Set room left:** 23,012 bytes of polygon ROM and 12,927 TGP words.
- **Run figures:** 150 s each, autopilot, clock held. Stale frames 277 and 1607 occur in every run, as in §7.3.

| run | laps | lap times | rate windows / overruns / worst busy | stale in stretch | records peak (of 10,500) | verge frames |
|---|---|---|---|---|---|---|
| DRY | 2 | 48.0, 39.5 s | 28/29 / 0 / 10.8 ms | none | 5,598 | 141 of 3,381 |
| RAIN | 2 | 59.0, 45.2 s | 28/29 / 0 / 17.5 ms | none | 7,779 | 109 |

The autopilot still leaves the road at the S-bend before the first tunnel (145–160) and at the hairpin (215).

### 8.6 Mountain (Diablo Canyon's slot, Acropolis's host; only Mountain swapped in)

- **Frame:** `Frame.for_host(rs, 2)`, start height 3.7.
- **Collision:** 467 sections and 374 road points (lap 3,753); TGP well inside Diablo's 40,635 words (the set leaves
  8,251).
- **Scenery:** the split-screen set thinned (xz) to 438 KB (the set leaves 27,112 bytes). There are no tunnels or
  pit lane, and the start flags (`fl00/01`, animated) are not converted.
- **The narrow stretch is real:** road points 175–221 are 9–10 units of tarmac with 4–5 units of kerb each side
  (kinds across the band: `333311110000000000111133`). With the kerbs in the band, the collision is 18–19 wide there.
- **Hairpins:** the tightest corners are road points 288 (62° per 50 units), 264–265 and 131–133.
- **Highest point:** road point 148, y 12.4; the lowest is 97, y −6.5.
- **Sheet:** `mountain/sheet_mountain.png` (start, into the first hairpin, the highest point, the pass, into the second
  hairpin, out of the tightest corner).
- **Play set:** `mountain/play/launch.sh` with `NOTE.txt` (written, not run).

| run | laps in 150 s | lap times | rate windows / overruns / worst busy | stale in stretch | records peak | verge frames |
|---|---|---|---|---|---|---|
| DRY | 1 (the second unfinished) | 68.6 s | 28/29 / 0 / 12.9 ms | none | 5,809 | 193 of 3,381 |
| RAIN | 1 | 64.7 s | 28/29 / 0 / 17.5 ms | none | 7,668 | 158 (and 1 frame on a wall strip) |

- **Where the autopilot leaves the road:** the hairpins (road points 65–85, 265–270, 310) and the pass (180–185).
- **Checkpoints:** they fire at 163 and 286.
- **The opponents:** one of fifteen stood still on the pass (road point 218) for the last 10 s of the DRY run, and
  `race_log`'s jolts are 108 (Island: 43).

### 8.7 Beltway (Surfers Road's slot, Bay Bridge's host; only Beltway swapped in)

- **Thinning by true area, two variants:**
  - **(a)** at Surfers Road's polygon room: thin 768, 7,107 faces, 484 KB.
  - **(b)** with about 180 KB more assumed: thin 256, 9,379 faces, 650 KB. It is built in a scratch set without the
    converted start-gantry frames (241 KB freed). This only measures the variant; the gantry was not reworked.
- **The second atlas** decoded cheaply: `cous00b` holds the buildings' window bands.
- **Collision:** 509 sections and 407 road points (lap 4,097), almost all wall-lined, within Surfers Road's TGP. The set
  leaves 24,511 words.
- **Both sets are built without the weather feature.** With Beltway in, the select screens' first-fit placement
  overwrote the weather's reserved bank-0 blocks. First the select picture went over `screen graphics 2`. With the
  weather blocks excluded from the pictures' search (scratch), there was then no run left for the originals'
  direction-screen pictures. With a flat select picture, `screen graphics 1` was hit.
  - Main's build fits these blocks by its sizes alone. A pack needs them reserved: the panels, the select pictures, the
    originals' pictures and the weather blocks share bank 0 and the program ROM's last few KB.
- **Sheet:** `beltway/sheet_beltway.png`, (a) and (b) side by side at the same six places of the same drive.
  - (a) loses the towers' faces, and most buildings read as a few slabs.
  - (b) keeps the towers and the city skyline.
- **Play set:** `beltway/play/launch.sh` (variant a; written, not run).

| run (no weather) | laps in 150 s | lap time | rate windows / overruns / worst busy | stale in stretch | records peak | verge frames |
|---|---|---|---|---|---|---|
| (a) DRY | 1 | 83.2 s | 28/29 / 0 / 11.2 ms | none | 5,258 | 0 (walls along the road) |
| (b) DRY | 1 | 83.2 s | 28/29 / 0 / 11.2 ms | none | 5,592 | 0 |

- **The tight corners:** the tightest are at road points 240–242 (82° per 50 units), 263–264 and 212. The off-course
  counter runs at 60 and 215.
- **Checkpoints:** they fire at 141 and 293.
- **The opponents:** `race_log`'s jolts are 146, the most of the three.

### 8.8 What the owner should look at first

1. `island/sheet_island2.png` (the look pass), then the Island play set.
2. `beltway/sheet_beltway.png`, (a) against (b). This is the decision whether Beltway needs the start-gantry rework's
   polygon room.
3. `mountain/sheet_mountain.png`, then the pass at road points 175–221 in the Mountain play set (9–10 units of
   tarmac).

## 9. Island's pit lane, and Mountain's opponents on the pass (26 Nov)

The new sets are beside the play sets the owner may launch; those are untouched. Scratch is in `out/p90/island/pit/` and
`out/p90/mountain/v2/`.

### 9.1 Island's pit lane (`ps2course.pit_lane`, in place of the Saturn reader `collision.pit_lane_polygons` / `pit_box`)

- **The lane:** the PS2's `PIT01` path, from its start to where it rejoins the road (within 8 units of the centreline),
  with its tarmac band scanned across it every 8 units. It runs 19–26 units right of the race road on the start straight,
  behind a grass strip at road points 0–20, and ends at road point 40.
  - Its 54 quads are appended to the lap's tarmac, where the segment array credits them to the nearest road points.
  - The entry quad is the first lane section clear of the race band (road point 307, 27 units right, 13 wide). It is
    doubled in the list, because the game's PIT WORK check reads the entry quad or the next.
- **The box:** `PIT00`'s point farthest from the road: road point 15, 35 units right, in the PS2's kind-0xa box zone,
  heading the lane's (+z).
  - The host's pit crew scene comes with the entry's pit quad and box, as on the converted courses.
  - The HUD map draws the lane.
- **Opponents:** they cannot take it. Their lines are offsets of the race centreline, and the lane is collision only.
- **Reverse:** not built. The project's reverse pit rule (`reverse.reverse_pit`) reads the Saturn course; porting it is
  the next step.
- **Headless run** (`scripts/pit_run.py`, 150 s): the pit tests' normal pit path (`pitpaths.normal_pit_path`: line 6
  with the lane spliced in), checked with the pit tests' constants.
  - The first frame on the entry pair is 6440 and the trigger 6442, on the pair.
  - The car parks exactly at the box (x, z within 0.01, yaw 0) and stays there to the release.
  - Release − park is 444 frames. The clock stands from the trigger to the release, then gets +384 (12 s). Stops go
    2 → 1, and five crew objects are live at the park.
  - Rate windows 28/29, no overrun, worst busy 13.3 ms, no stale list in the stretch, records peak 4,899.
  - The plain autopilot lap on the same set: two laps, 48.2 s and 39.6 s.
- **Set and play set:** `island/pit/set`, `island/play_pit/launch.sh` (written, not run).
- **Still:** `island/pit_stop_island.png`. The PS2 sea shows beside the pit straight, the one place it meets the
  raised water.
- **A test-harness note:** the autopilot reads the player's position from `collision_log.lua`, so a pit run needs
  `VR_COLLISION_LOG`. The first pit run went without it and drove blind.

### 9.2 Mountain's opponents on the pass

- **Why it stopped:** in the first set, car 7 ran on line 4 (+8 units: the band's edge on the pass, where the band
  spans about ±9.3 with its kerbs). Through the pass it swerved from +13.5 to −13.4 units, then stood at +8 to +9.6 with
  speed 79 against a wall strip, from frame 5017 to the run's end (63 s). It was never put back. No other car was within
  250 units, so it was not a meeting of two cars.
- **The fix is the conversion's (`ps2course.lane_scales`).** Per centreline point, the AI offsets are scaled so the
  outermost line keeps AI_MARGIN = 4 units inside the band (out to the kerbs). The narrowest scale holds three points
  either side and the floor is 0.3. On the pass the lines shrink to 0.72 of their width. All eight lines are kept: at
  ±5.7 they fit.
- **Measured** on `mountain/v2/set`, 360 s, the race run to its end (the player finishes five laps):

| run | opponents' laps (least) | put-backs | stationary ≥ 3 s | rate windows / overruns / worst busy | stale in stretch | records peak |
|---|---|---|---|---|---|---|
| Mountain DRY | 3.22 | 0 | 0 | 28/29 / 0 / 12.6 ms | none | 5,889 |
| Mountain RAIN | 3.29 | 0 | 0 | 28/29 / 0 / 17.5 ms | none | 7,612 |
| Metropolis (released set, Saturn reference, 260 s) DRY / RAIN | 2.72 / 2.67 (in 260 s) | 0 / 0 | 0 / 0 | | | |
| first Mountain set (150 s) | 0.56 (car 7) | 0 | 1 (62.6 s) | | | |

- **The player's test autopilot** still leaves the road at the hairpins (65–95, 250–270, 310) and on the pass
  (180–185): it does not brake as a driver would. A human line fits: the pass is 18–19 units across with its kerbs.
- **Play set:** `mountain/play2/launch.sh` (written, not run).
- **The Saturn path:** these commits change only `vrtools/convert/ps2course.py`. The hooks are as built and proven
  in §8, where the released set was identical to main's (`island/after2`).

## 10. Is scenery lost? The reference renders, the inventory, the fixes (26 Nov)

**The owner's words, after driving:**
- Island: "the checkpoint flag is missing the white section. at the start, the center middle discontinued white line
  seems to not be rectangular (check with original) and i feel we need more polygons or more distance".
- Mountain: "same issue with checkpoint flags missing the white part and C.P and drawing distance increase".
- Beltway: "beltway also is missing the checkpoitn flag but it has a lot ore issues: most of the side decors are missing
  (even from the very start) check extra hard".

The session lead asked to check for scenery lost in the conversion before any tuning.

### 10.1 How it was checked

- **A reference renderer** (`out/p90/scripts/refrender.py`: numpy z-buffer, flat colour per face from the swatch). It
  draws:
  - every triangle list of every model file of a course, in both versions;
  - the course archive's banners and flags;
  - the faces a built set's polygon ROM holds for an entry.
- **Reference sheets** (`out/p90/<course>/sheet_reference_<course>.png`, scratch only). Columns: PS2 one-player, PS2
  split-screen, built set, MAME. Rows: the grid, road point 2, three places along the lap, and top views of road points
  0–60. The sheets now show the sets after the fixes; the first renders (before) had the screen mirrored and were
  replaced.
- **An inventory** (`scripts/inventory.py`): the triangles within 60 units of the road by kind (geometric classes: road,
  marking, kerb, ground, barrier/rail, post/lamp, sign/board, banner over the road, tree, building/structure, other
  upright), on road points 0–60 and the whole lap.
- **A census of every model file** for vertex data outside the read triangle lists:
  - the one-player and split-screen scenery files: none;
  - the course archive's `st00-02`/`fl00-01`: 538–1,192 vec4s each, their animation data.

### 10.2 The inventory (triangles within 60 units of the road, road points 0–60; "before" = the driven sets, "after" = §10.3's sets)

| kind | Island 1P / split / before / after | Mountain 1P / split / before / after | Beltway 1P / split / before / after |
|---|---|---|---|
| sign/board | 258 / 156 / 10 / 193 | 275 / 99 / 67 / 147 | 148 / 93 / 20 / 118 |
| post/lamp | 1,007 / 55 / 31 / 73 | 1,124 / 459 / 174 / 721 | 671 / 377 / 85 / 371 |
| tree | 60 / 44 / 122 / 184 | 0 / 0 / 2 / 6 | 968 / 674 / 6 / 85 |
| building/structure | 94 / 39 / 28 / 60 | 546 / 124 / 134 / 204 | 650 / 343 / 21 / 87 |
| other upright | 410 / 278 / 198 / 395 | 760 / 160 / 198 / 242 | 601 / 339 / 17 / 80 |
| barrier/rail | 387 / 249 / 366 / 395 | 54 / 20 / 105 / 259 | 738 / 225 / 347 / 928 |
| marking | 392 / 339 / 338 / 339 | 624 / 209 / 217 / 211 | 396 / 60 / 58 / 56 |
| ground | 1,510 / 814 / 711 / 815 | 1,986 / 398 / 401 / 397 | 1,345 / 668 / 179 / 622 |

How to read the table:
- **Placed counts are triangles** (a quad counts as two). They can exceed the split-screen version's where the
  one-player props near the road replace it.
- **Whole lap, before → after:**
  - Island: signs 137 → 309;
  - Mountain: signs 418 → 671, posts 653 → 1,308;
  - Beltway: trees 212 → 614, buildings 241 → 517.
  - The full tables are in `out/p90/ref/inv_*.txt`.

### 10.3 Causes (each shown on an example) and fixes

1. **Checkpoint flags: not read.** The PS2 keeps its checkpoint banners (white panel, red "C.P" letters, modelled as
   faces) in the course archive's `st01/st02`, in world coordinates at the gates; `st00` is the START banner. The loader
   read only the scenery archives, and `chk.bin` is the invisible trigger planes.
   - Fix: `ps2.course` reads `st00-02` and `fl00-01`, and `ps2course.scenery` places `st01/st02` and the flags whole,
     never thinned. The arcade's START gantry stays the host's.
   - Evidence: Island road point 120, the banner in the PS2 render, the built set and MAME.
   - All three courses had it.
2. **The start's centre line: pairing across dashes.** The PS2 line is rectangles of 0.55 × 10.3 (each two triangles,
   stored twice).
   - Greedy pairing merged a triangle of one rectangle with one of the next across their common end. On Island's start
     that gave 25 long slanted parallelograms and 4 triangles among 32 faces. The arcade sorts a face by its farthest
     corner, so the road faces painted over parts of these long faces.
   - Fix: pair only along both triangles' longest edges (the diagonal). Island's start line is now 30 rectangles and
     no other shape.
   - The same holds for every marking, kerb strip and grid box. All three courses had it.
3. **Thinning removed the roadside.**
   - The xz-area rule (Island, Mountain) dropped every upright face more than 40 units from the road: an upright has
     almost no xz area. Island's signs on road points 0–60 went from 156 to 10.
   - Beltway's true-area rule at Surfers Road's room (thin 768, roadside 20 units) dropped its trees (674 → 6), its
     building fronts (343 → 21) and its posts (377 → 85).
   - Fix: `thin_roadside`: level faces are thinned by xz area as before, upright faces within 60 units of the road are
     never thinned, and an optional far cut is available.
4. **The split-screen version's own lightness.** It has 5–18 % of the one-player version's posts and lamps on
   Island's start (55 against 1,007) and fewer signs and markings. That is real; using the one-player version costs room
   (§10.4).
5. **Not found: placement tables for the MAPOBJ models.** These are cows, ponies, palms, boats, yachts and birds
   (`DATA/MAPOBJ`, in local coordinates). Only `cow_gr.vcp` and three yacht paths are named in the executable, and the
   per-course placements are not in the course archives: presumably tables in the executable. They are animated extras
   and are not converted.
6. **Ruled out:**
   - unread triangle lists in the scenery files (the census);
   - local-coordinate scenery models (positions agree with the collision);
   - faces lost to pairing, to cell caps (0) or to the map (0–3 outside);
   - winding (all records are two-sided).
7. **The reference renderer's first sheets were mirrored left to right** (the screen's right vector). They were redrawn.

### 10.4 Room: what keeping the roadside costs

The scenery bytes with `thin_roadside` (thin 6, no far cut), against the slots:

| course | scenery (split-screen + near props + banners) | slot | over | smallest with the roadside kept (thin 768, far cut 120) |
|---|---|---|---|---|
| Island | 541 KB | 441 KB (Pacific Coast) | +100 KB | 505 KB |
| Mountain | 564 KB | 441 KB (Diablo Canyon) | +123 KB | 502 KB |
| Beltway | 1,450 KB | 487 KB (Surfers Road) | +963 KB | 1,203 KB |

- **Island and Mountain** fit with about 180 KB more polygon ROM (the start-gantry rework), each on its own.
- **Beltway does not.** About 15,800 faces lie within 60 units of its road (about 1.0 MB), mostly building fronts of
  small faces. The next converter step would be merging a building's coplanar same-colour faces into larger quads,
  beyond pairs.
- **The new sets assume the gantry room.** They are built without the converted start-gantry frames
  (`--no-gantry-frames`, scratch), so the other converted courses show the arcade's own start gantry object.
- **Beltway's set** holds 700 KB: every upright within 25 units is kept, and smaller faces past 25 are thinned.
- **Drawing distance** was not changed in this round. The arcade draws the camera's 5 × 5 cells of 128 units within a
  forward wedge (Phase 28's model), about 250–320 units ahead.

### 10.5 The new sets (headless, 150 s, autopilot, clock held; no stale list in any stretch, no list skipped)

| set | laps | rate windows / overruns / worst busy | records peak (of 10,500) |
|---|---|---|---|
| Island DRY / RAIN (`island/v5`, pit lane in) | 2 / 2 | 28/29 / 0 / 10.9 ms; 17.5 ms in RAIN | 5,953 / 8,001 |
| Mountain DRY / RAIN (`mountain/v3`) | 2 / 1 | 28/29 / 0 / 12.9 ms; 17.5 ms in RAIN | 6,305 / 8,028 |
| Beltway DRY, no weather (`beltway/v2`) | 1 | 28/29 / 0 / 10.8 ms | 6,147 |

- **Play sets** (launchers written, not run): `island/play3`, `mountain/play3`, `beltway/play2`. The driven sets are
  untouched.
- **The Saturn path:** only `vrtools/ps2/course.py` and `vrtools/convert/ps2course.py` changed, so the hooks are as
  proven in §8.

## 11. Drawing distance, and Beltway's buildings (26 Nov)

The owner asked for "more polygons or more distance". The three distance options below were each measured. Then a new
converter step merges a building's faces, and Beltway was measured against three amounts of room.

### 11.1 The cell walk, in the boot ROM

- **The walk is `0xff7beb..0xff7e1e`** [R]:
  - `0xff7beb` turns the camera's x, z (`1E[R25]`, `26[R25]`) into its 128-unit cell.
  - `0xff7c9e..0xff7d24` builds the off-map mask in R17. It is 25 bits (`or.w #108421` and the others, one bit for each
    of the 25 neighbours).
  - `0xff7ea1` (`0xff7e51` when looking steeply down) gives the yaw masks, also 25 bits.
  - The loop at `0xff7d38` runs 25 times (`mov.w #19, R20`). It walks the order table at `0xff7e1f` and the signed
    offsets at `0xff7e38`.
  - It writes three lists of at most 63 cells: 0x501c01, 0x501cc1 and the new cells at 0x501c41.
- **A 7 × 7 walk (49 cells) is not a small change.** Both masks must grow past 32 bits, so two registers each. The yaw
  routine must be rewritten for the new corners, and the counter and the two tables replaced.
- **A longer forward wedge is not a small change either.** The offsets are fixed to the world, not to the heading, so a
  forward shape needs code that picks the cells from the heading.
- **(c) was therefore not patched.** It was measured instead with Phase 28's visible-cell model (`visible_cells`, now
  in `ps2course.py`; 84 % agreement with the logged lists) and Phase 28's pass-time fit. That fit is about 8 ms fixed
  plus 27–64 µs per drawn object. Records add no measurable time.

### 11.2 The three options, measured

Scenery records a frame come from the model at every road point, both directions; the pass times are from MAME, headless,
150 s. The reach is the median run of road points ahead that stay inside the drawn cells.

| course | (a) 5 × 5: records median / max, reach | (b) far silhouettes: bytes, MAME records peak DRY / RAIN, worst pass | (c) 7 × 7: records median / max, reach, extra drawn cells median / max |
|---|---|---|---|
| Island (`island/v5` → `v6`) | 1,698 / 5,030, 36 points | +74 KB (1,007 faces of 200 u² or more), 5,953 → 6,226 / 8,001 → 8,529, 17.5 ms unchanged | 2,320 / 6,350, 49 points, +4 / +8 |
| Mountain (`mountain/v3` → `v4`) | 1,610 / 2,582, 38 points | +57 KB (761 faces of 450 u² or more), 6,305 → 6,460 / 8,028 → 8,133, 17.5 ms unchanged | 2,322 / 3,909, 52 points, +4 / +8 |
| Big Forest (released) | 3,066 / 6,306, 33 points | — | 4,627 / 9,453, 46.5 points, +5 / +8; extra records up to +5,307 |
| Bay Bridge (released) | 2,274 / 5,336, 45 points | — | 3,073 / 6,398, 59 points, +3 / +9; extra records up to +3,409 |

- **The released courses in MAME (measured):**
  - Big Forest DRY: records peak 10,385 of 10,500, worst pass 14.7 ms.
  - Big Forest RAIN: 10,222, 17.5 ms.
  - Bay Bridge RAIN: 8,957, 17.6 ms.
  - All windows hold, and no list is stale or skipped.
- **What (c) does to the released courses (estimated from the measured figures):**
  - A 7 × 7 walk changes every course, the ten originals and the converted ones alike.
  - Big Forest would go past the 10,500 budget wherever the extra ring holds scenery, up to about +5,300 records. The
    budget skip would then drop the last-walked cells, which are the new outer ring. The gain shows as cells flickering
    in and out, not as distance.
  - Up to 9 more drawn objects add 0.2–0.6 ms to the logic pass. Rain's worst 17.5–17.6 ms then reaches the 17.9 ms
    rain cap and comes within about 0.7 ms of the 18.9 ms deadline. Stale pictures would follow wherever the pass
    passes the deadline.
- **What more distance gives on screen.** `island/sheet_distance_island.png` and `mountain/sheet_distance_mountain.png`
  show four places each: the PS2 one-player render, MAME (a), MAME (b), and the set's faces drawn offline from the 5 × 5
  and from the 7 × 7 cells.
  - At all eight places the five columns of the set show nearly the same picture. `ref/far_check3.png` also adds the
    far copies made up to 4 times, and all cells.
  - The far hills the reference shows are in the set and inside the walk. What differs is their **detail**. The PS2
    draws the one-player mesh (Island 40,121 triangles at full detail), while the sets are converted from the
    split-screen mesh (12,475): the same hills with about a third of the faces.
- **"More polygons" costs.** The one-player mesh instead of the split one (thin 6 to 768) takes Island 1.06–1.18 MB,
  with 3,300–3,900 scenery records median and 6,600 max a frame. It takes Mountain 1.44–1.78 MB, 3,800–4,700 median
  and 9,700–10,600 max, which is past the budget on its own. Neither fits a slot, nor a slot plus the gantry room.

### 11.3 Beltway's buildings: `merge_coplanar`

- **What it does:**
  - Upright faces in one plane (normal to 0.01, plane offset to 0.1 unit) and of one colour (within 12 a channel) that
    share a whole edge are joined while the union stays a convex polygon of at most four corners. This repeats until
    nothing more joins.
  - With `windows`, every face in a plane first takes the plane's main colour by area. The window bands and strips drawn
    over a wall go into the wall.
  - Level faces, one-sided faces and picture faces are left as they are.
- **Beltway, with the roadside and the buildings kept to 60 units (thin 768):**

| | faces | polygon bytes |
|---|---|---|
| as converted | 20,692 | 1,354 KB |
| merged | 18,606 | 1,239 KB |
| merged, windows into walls | 17,051 | 1,073 KB |
| the same, faces beyond 80 units of the road dropped | 14,209 | 891 KB |
| the same, beyond 60 units | 13,667 | 855 KB |

- **The best that fits each room** (merged, windows into walls):
  - (i) Surfers Road's slot, 487 KB: buildings kept to 12 units only, 6,566 faces, 421 KB. That is little more than the
    first row of fronts.
  - (ii) the slot plus 180 KB, about 667 KB: kept to 30 units, 10,265 faces, 653 KB.
  - (iii) two slots, about 940 KB: kept to 60 units, faces beyond 60–80 dropped, 13,667–14,209 faces, 855–891 KB.
- **The sheet.** `beltway/sheet_beltway_buildings.png` shows (ii) and (iii), merged with and without windows, at four
  places beside the reference.
  - (iii) brings back most of the city at the start: the tower blocks and the skyline behind the trees.
  - (ii) still shows only the nearest fronts.
  - Folding the windows in costs the bands on the tower fronts. It saves 23 KB at (ii) and 87 KB at (iii).

### 11.4 The new sets and the recommendation

| set | what | records peak (of 10,500) | worst pass |
|---|---|---|---|
| `island/v6` → `island/play4` | v5 plus far silhouettes, +74 KB | 6,226 DRY / 8,529 RAIN | 10.9 / 17.5 ms |
| `mountain/v4` → `mountain/play4` | v3 plus far silhouettes, +57 KB | 6,460 DRY / 8,133 RAIN | 12.9 / 17.5 ms |
| `beltway/v3` (ii) | merged with windows into walls, uprights to 30 units, 653 KB | 6,188 DRY | 10.8 ms |
| `beltway/v4` (iii) → `beltway/play3` | merged with windows into walls, uprights to 60 units, beyond 60 dropped, 855 KB | 7,398 DRY | 10.8 ms |

- **Run checks.** Every run holds 28/29 rate windows. No list is stale in the stretch (only 277 and 1607, as always) and
  no list is skipped.
- **(iii) is scratch only.** Its room comes from leaving out the converted gantry frames and Surfers Oval's thinnable
  scenery (`--starve 5`). It does not prove that a pack can give Beltway two slots.
- **The Saturn path is unchanged.** Only `vrtools/convert/ps2course.py` changed (`merge_coplanar`, `far_copies`,
  `visible_cells`), with its tests. The hooks are as proven in §8, and the boot ROM was not touched.
- **Recommendations:**
  - **Distance:** keep (b) as a cheap extra (57–74 KB, a few hundred records, no time cost). Do not widen the walk. It
    would change every course, push Big Forest past the budget, where the skip would undo it, and bring rain to its
    cap. It would also add little: at the places checked, the hills are already drawn.
  - **"More polygons" is the real gap.** The lever is the one-player mesh near the road, for example within 60–100 units,
    with the split mesh beyond. That would be the next measure, against the gantry room.
  - **Beltway:** the merge with windows folded in is worth keeping (−21 % bytes). Only (iii) brings the city back as the
    reference shows it. (ii) is a better play2, not the reference.

## 12. Pack 2: the three PS2 courses in a second set (26 Nov)

The owner's call (design `docs/superpowers/specs/2026-11-26-ps2-pack-design.md`): "We don't want to remove any a Saturn track".
The PS2 courses go into a second set, pack 2. Its spare room goes to PS2 detail first, and its remaining menu slots go to whichever
Saturn courses still fit. Pack 1 stays byte for byte what `vrtools build` makes.

### 12.1 The composition's arithmetic (before any build)

- **Sources:** room per region from the room study (`phase90-more-courses-room`, §2 and §3: measured on v0.4.1's build). The PS2
  courses' bank and TGP costs are read from the prototype sets: each set's room per region against `room/set`, less the Saturn
  course it replaced.

**Pack 2's room before the seven Saturn courses are placed** (the arcade's three, the storm, the shared blocks and the originals'
reverses kept):

| region | room for the seven slots | how |
|---|---|---|
| polygon ROM | 3 228 772 B | 18 552 free + the seven sceneries 3 210 220 (Metropolis's far copies with it) |
| + the start gantry stored as the arcade's frames + its lettering, once (no visual cost) | +180 480 B | 241 408 − 32 × 1 904 (each frame keeps the arcade's own object, followed by a small lettering object, as the checkpoint gantries already do) |
| = polygon ROM for courses | **3 409 252 B** | |
| TGP data ROM | **252 328 words**; slots 13 of 16 | 7 631 free + the seven collisions 244 697 |
| data bank 1 (Bay Bridge host) | **809 707 B** | 1 752 + Amazon, Pacific Coast, Surfers Oval, Surfers Road, normal + reverse |
| data bank 2 (Acropolis host) | **664 666 B** | 206 908 + Diablo Canyon, Metropolis, normal + reverse |
| data bank 3 (Big Forest host) | **447 816 B** | 192 279 + Alpine, normal + reverse (the storm's 253 452 stays) |
| program ROM | 7 fixed course slots (tile table, race blob, spawn list) + 9 428 free | unchanged: seven slots, whatever fills them |
| bank 0 (select screens, the weather's blocks reserved) | 7 536 free + 7 panels (25 808) + 7 pictures (45 927) | unchanged count: seven panels and pictures (the weather's bank-0 blocks reserved before they are placed, §12.3) |
| battery RAM | unchanged | ten entries, same tables; pack 2's own S-RAM magic is its pack tag (§12.3) |

- **Not used: the dead objects.** The 18 528 B of dead objects lie inside Metropolis's conversion, and Metropolis is not in
  pack 2.

**The PS2 courses at the design's detail:**

| course (host) | polygon | TGP words | its bank, normal + reverse |
|---|---|---|---|
| Island (Bay Bridge, bank 1; pit lane in) | 523 KB: the roadside kept, each structure's coplanar faces merged (lossless: upright faces of one plane and one colour) | 28 842 | 182 150 |
| Mountain (Acropolis, bank 2) | 537 KB (the same) | 40 012 | 218 512 |
| Beltway (Bay Bridge, bank 1) | 857 KB: the city to 60 units, merged, windows folded into the walls (1 075 KB with the windows kept) | 26 326 | 194 456 |
| **the three** | **1 917 KB** (2 135 KB with Beltway's windows kept) | **95 180** | bank 1 376 606; bank 2 218 512 |

**What the one-player mesh near the road adds** (Island and Mountain: the one-player mesh's ground and terrain within D of
the road, the split-screen mesh beyond; `scenery(near_detail=D)`; records a frame from Phase 28's model at every road point,
both directions; the storm adds about 2 000–2 500 records on top):

| | faces | polygon | colour words | scenery records a frame, median / p95 / max |
|---|---|---|---|---|
| Island, split mesh (as built) | 8 295 | 541 KB | 992 | 1 698 / 3 104 / 5 030 |
| Island, one-player within 30 | 12 938 | 844 KB | 1 055 | 2 701 / 4 866 / 6 854 |
| Island, within 60 | 15 559 | 1 043 KB | 1 126 | 3 576 / 5 248 / 7 690 |
| Island, within 100 | 16 415 | 1 107 KB | 1 156 | 3 731 / 5 397 / 7 709 |
| Mountain, split mesh (as built) | 8 730 | 564 KB | 981 | 1 610 / 2 270 / 2 582 |
| Mountain, one-player within 30 | 18 003 | 1 132 KB | 1 098 | 3 202 / 5 989 / 7 036 |
| Mountain, within 60 | 23 201 | 1 468 KB | 1 178 | 3 916 / 8 071 / 9 388 |
| Mountain, within 100 | 25 769 | 1 640 KB | 1 265 | 4 356 / 9 071 / 10 422 |

- **TGP is unaffected:** the collision does not read the scenery.
- **The budget:** within 60 units, Mountain's worst views reach 9 400 scenery records before the road, the cars and the rain.
  That is past 10 500 in the storm. Island within 60 reaches 7 700, so the rain would bring it to the cap.
- **The room:** the cheapest step costs +303 KB on Island and +568 KB on Mountain, which is a Saturn course's room or more.
  **Not taken:** it would cost a menu slot, and on Mountain the budget too.

**Spending the rest: the Saturn courses that still fit.** After the three, the polygon room left is 1 492 KB.

| Saturn course (bank) | polygon | TGP | bank, normal + reverse | fits with the others chosen? |
|---|---|---|---|---|
| Surfers Oval (1) | 434 640 | 38 688 | 201 460 | yes |
| Diablo Canyon (2) | 441 152 | 40 635 | 251 044 | yes |
| Pacific Coast (1) | 441 464 | 33 024 | 207 866 | yes |
| Metropolis (2) | 441 588 | 28 297 | 206 714 | polygon yes, bank 2 no: with Mountain and Diablo, 676 270 > 664 666 |
| Amazon Falls (1) | 481 312 | 26 583 | 181 846 | bank 1 no: 4 courses there already |
| Alpine (3) | 483 336 | 34 254 | 255 537 | polygon no, as a fourth |
| Surfers Road (1) | 486 728 | 43 216 | 216 783 | polygon no |

- **Three fit: Surfers Oval, Diablo Canyon, Pacific Coast.**
  - Polygon: 1 317 256 of 1 492 KB, leaving 175 KB. Island's and Mountain's far silhouettes (74 + 57 KB) then fit, with
    about 44 KB of margin.
  - TGP: 207 527 of 252 328 words.
  - Bank 1: Island, Beltway, Surfers Oval and Pacific Coast take 785 KB of 810 KB.
  - Bank 2: Mountain and Diablo Canyon take 470 KB of 665 KB.
  - Bank 3: the storm alone.
- **A fourth does not fit in any combination.** The smallest fourth costs 441 KB of polygon ROM against 175 KB left (44 KB
  with the silhouettes).

**The tenth entry: the options and their cost.**

| option | cost | |
|---|---|---|
| (1) a shorter menu: nine courses on the wheel; the directory keeps ten entries, the tenth unreachable (a copy of the ninth) | the select wheel's thresholds as data (nine bands of 28.4) and the window's clamp (6 instead of 7), as pack parameters; pack 1 keeps its own; about 1 KB of bank 0 and program ROM for the unreachable copy's panel and picture | **recommended and built** |
| (2) a stand-in: the tenth entry repeats a course already in the pack under its name | nothing but its panel and picture; a course shown twice on the wheel | |
| (3) a lighter PS2 detail for one more Saturn course | Beltway's city cut to 12 units (421 KB: the first row of fronts only, the owner's own complaint) makes room for Alpine. A 30-unit city still falls 106 KB short. Island and Mountain at the old thinning (441 KB each, the roadside lost) with Beltway at 30 units would also do. | not recommended: it undoes what the owner asked for |
| (4) a Saturn course at lower detail | not allowed without the owner's word | |

### 12.2 The plumbing (real code)

*Superseded by §13 (pack 2 at the best detail; the nine-entry as-driven plan was removed in fix round 1, §18).*

- **`vrtools/arcade/pack.py`: a pack is a plan.**
  - Seven slots, each a `CoursePlan` (Saturn), a `Ps2Plan` (PS2) or a `Hidden` copy.
  - The plan also gives: the number of entries on the wheel; the start gantry (`frames` copied whole as in pack 1, or
    `lettering`); the battery RAM magic (the pack tag); whether the storm's blocks are reserved; the lightning's own aims by
    course name.
  - `check` refuses a plan that cannot be built. `build_pack` and `pack_set` build it.
  - `check_ps2` accepts only the Japanese release (SYSTEM.CNF boots `SLPM_624.43`) and refuses any other by name.
  - `SATURN` is pack 1, `PS2` is pack 2.
- **`vrtools/arcade/ps2entry.py`:** `convert_course`'s steps on a PS2 conversion: collision, the sky panorama, road blob,
  tile table, spawn list, scenery cells with the far silhouettes, outline, race blob by the project's rule, and the reverse.
- **`vrtools build --pack ps2 --ps2 <disc>`** (or `$VR_PS2_DISC`) writes pack 2 into `--out`. With no option, `build` runs
  the old path untouched.
- **Shared code, all defaults keeping pack 1 as it was:**
  - `select.bands_for` / `wheel_for` / `first_of(menu)`: a nine-band wheel. The ninth threshold is unreachable and the
    window clamp is `menu − 3`.
  - `CourseEntry10.hidden`: not encoded; kept off the attract ranking; takes its source's panel and picture, and has no
    reverse.
  - `install_directory(menu, magic)` and `ranking_image(magic)`.
  - `install_panels(room)`: the panels stop before the storm's screen graphics in bank 0's tail.
  - `install_pictures(exclude)`: the storm's bank-0 and program blocks are left out of the first fit.
  - `ten_course_set(menu, magic, reserve_weather)`.
  - `gantry.install_start_lettering`: the arcade's frames plus a lettering object each, as the checkpoint gantries.
  - `lettering`: W.
  - The weather by course, not by menu entry:
    - `cover_geom.tables` matches pack 1's stretches by name; a course of no Saturn or arcade name is marched along its
      own flagged stretches;
    - Metropolis's grey sky goes by name (`rain.metropolis_entry`);
    - the lightning's aims go by name through the pack.
  - `report_lines` takes a PS2 course and a hidden entry.
  - `reverse_tables(loop)`: a pit lane appended after the lap is credited apart.
- **The pack tag:** pack 2's battery RAM magic is "S-RAM CHECK OK P2" (pack 1's: "… 10").
  - At boot each pack compares the magic and clears the battery RAM if it is not its own. Times never show under another
    pack's courses.
  - A pack 2 run's saved battery RAM holds "P2".
- **Converter (`ps2course`):**
  - `near_detail`: the one-player mesh near the road.
  - `covered_stretches`: faces over the road, which finds Beltway's three overpasses (67–72, 277–279, 305–308) and
    Island's two tunnels.
  - `join_stretches`.
- **Tests:** `tests/test_pack.py`: the plans, the refusals, the nine-band wheel, the pack tag, the disc check
  (synthetic, plus one disc test that skips without `VR_PS2_DISC`). `tests/test_ps2course.py`: the covered stretches.

**Pack 1 stays byte for byte.** It was built three times from this branch's code with `vrtools build` (the last after the
final change). Each time all 38 members are identical to `room/set`, main's build (dd8ca06; main's later commits change
no code).

### 12.3 Pack 2's room, measured (`out/p90/pack2/set3`)

*Superseded by §13 (pack 2 at the best detail; the nine-entry as-driven plan was removed in fix round 1, §18).*

| region | pack 2 free | pack 1 free | the six courses take (pack 2) |
|---|---|---|---|
| polygon ROM | 44 796 | 18 552 | Island 595 032 (73 896 of it far silhouettes), Mountain 591 120 (56 440), Beltway 854 664, Surfers Oval 432 688, Pacific Coast 439 248, Diablo Canyon 438 888 |
| TGP words | 44 788 (slots 4–9 used, 10–15 free) | 7 631 | 207 540 |
| bank 0 | 13 245 | 7 536 | six panels and pictures (the hidden entry shares Diablo's) |
| bank 1 | 23 785 | 1 752 | Island, Beltway, Surfers Oval, Pacific Coast, each with its reverse |
| bank 2 | 195 136 | 206 908 | Mountain, Diablo Canyon, each with its reverse |
| bank 3 | 453 672 | 192 279 | the storm; no course |
| program ROM | 33 598 | 9 428 | |
| boot ROM | 5 700 | 5 684 | |
| battery RAM | about 304 B, as pack 1 | about 304 B | the same tables (the hidden entry's unused) |

**The Saturn courses kept are pack 1's** (`samecourse.py`). For Surfers Oval, Pacific Coast and Diablo Canyon, every
scenery record is identical (quads, flags and colour words), and so are the road lines, the segment flags and the record
counts. What moved:
- the headers in their banks;
- the polygon and colour addresses of every object;
- the HUD outlines;
- the panels;
- for Surfers Oval and Diablo Canyon, their program slots (tile table, race blob, spawn list), because their slot
  numbers differ.

### 12.4 Headless evidence (pack 2, MAME 0.289, autopilot, clock held, at most four jobs, no window)

*Superseded by §13 (pack 2 at the best detail; the nine-entry as-driven plan was removed in fix round 1, §18).*

| run | laps | checkpoints | rate windows 28/29 | stale | records peak | worst pass | 15 opponents |
|---|---|---|---|---|---|---|---|
| Island DRY, 300 s | 4 | 12 | 135/135 | none in the race (one after it, below) | 6 188 | 10.9 ms in the race | running, none held |
| Island RAIN | 2 | 7 | 59/60 | none | 8 430 | 17.6 ms | running |
| Island reverse DRY | 2 | 7 | 59/60 | none | 6 149 | 11.0 ms | running |
| Island reverse RAIN | 2 | 6 | 59/60 | none | 8 245 | 17.5 ms | running |
| Island pit stop | | | no miss | | 5 479 | 13.3 ms | |
| Mountain DRY, 300 s | 4 | 12 | 135/135 | none | 6 284 | 12.9 ms | running |
| Mountain RAIN | 1 | 5 | 59/60 | none | 7 958 | 17.5 ms | running |
| Mountain reverse DRY | 1 | 5 | 59/60 | none | 6 329 | 13.1 ms | running |
| Mountain reverse RAIN | 1 | 5 | 59/60 | none | 8 184 | 17.5 ms | running |
| Beltway DRY, 300 s | 3 | 10 | 135/135 | none | 7 398 | 10.9 ms | running |
| Beltway RAIN | 1 | 4 | 59/60 | none | 8 921 | 17.5 ms | running |
| Beltway reverse DRY | 1 | 4 | 59/60 | none | 6 941 | 11.4 ms | running |
| Beltway reverse RAIN | 1 | 4 | 59/60 | none | 8 888 | 17.5 ms | running |
| Surfers Oval DRY | 2 | 7 | 59/60 | none | 4 182 | 11.2 ms | running |
| Pacific Coast DRY | 1 | 4 | 59/60 | none | 6 009 | 11.8 ms | running |
| Diablo Canyon DRY | 0 | 0 | 59/60 | none | 5 895 | 12.5 ms | running |

- **Notes on the runs:**
  - The stale lists 277 and 1607 are the two scene loads every run has; no other list is stale in a race.
  - Every rain pass stays under the 17.9 ms cap.
  - Island's pit stop: the trigger on the pair (271, 272), parked still at the box for 444 frames, +384 on the clock, stops
    2 → 1.
- **Island DRY, 300 s:** a 42 ms pass and a stale list at frame 16 345 come after the race. For 0.4 s before it no records
  were drawn: it is the next scene's load, like 277.
- **Diablo Canyon DRY:** the scratch autopilot leaves the road at road points 90–120 on pack 1's set too. The figures are
  the same (3 852 frames off, records peak 5 895), so the course is unchanged and the test driver is what fails there.
- **The reverse fix:** Island's reverse first put the car back to the line inside the tunnel and held 11 opponents on the
  grid. `reverse_segments` had walked the pit lane, appended after the lap, as if it were the lap. Fixed with
  `reverse_tables(loop)`: 2 laps both ways, no car held.

### 12.5 Open

- Race tables are untuned (the project's rule).
- In reverse, Island's pit lane is plain road (no reverse pit stop).
- The reverse grids are the bank-1 rule's (Island, Beltway) and the normal table's points (Mountain).
- The Saturn courses kept were not run in reverse or in rain this round.
- The sheets (`out/p90/pack2/sheet_{island,mountain,beltway}.png`, scratch) were taken on `set1`. Its scenery is the final
  set's: only Island's reverse tables changed.

## 13. Pack 2 at the best detail the arcade can draw (26 Nov)

The owner, after driving pack 2:
- "bellway is better but seems we r missing a lot of polygons. can we increase their number";
- "on bellway it s also missing some of the CP checkpoint flags";
- "ok island is good but same note: it would be best to add more polygon for the draw distance and side details".

Pack 2 becomes the PS2 courses at the best detail the frame holds. The Saturn courses are extras that stay only if room is
left. Pack 1 keeps all seven.

### 13.1 Beltway's checkpoint banners

The PS2 data puts both Beltway banners (st01, st02, 55 faces each: the white panel and the red "C.P") at the start line,
road point 406 of 407, where the game places them at run time. Its checkpoints are at 141 and 292, so pack 2 as driven
showed no banner at either.

**The fix:**
- `place_banners`: a banner farther than 10 road points from every checkpoint gate is carried to its gate (st01 to the
  first, st02 to the second). It is turned by the road's change of heading, keeps its offset from the road, and follows
  the road's height.
- `merge_scenery`: the banners and the start flags, which `scenery` puts last, are never merged. Folding the windows into
  the walls would also have folded the red letters into the white panel.
- The banners are never thinned or cut: they are added after thinning, as before.
- Tests: a synthetic banner keeps its red letters through merging with the windows folded, and one far from its gate is
  carried to it.

**Count against the data:**

| course | banners in the data | where | placed by the built set |
|---|---|---|---|
| Island | 2 (59 and 54 faces) | at their gates, 129 and 208 | both, unchanged |
| Mountain | 2 banners (53 faces each) and 2 start flags | at their gates, 163 and 284; the flags at 0 and 10 | all, unchanged |
| Beltway | 2 (55 faces each) | both at 406 in the data | carried to 141 and 292 |

- The banners are two-sided: they show in both directions.
- The arcade's checkpoints, where the clock is extended, are the gates (`gate_checkpoints`): normal (0, g1, g2), reverse
  (0, n − g2, n − g1). They stand where the banners stand.

### 13.2 The ceiling per course: graded by tile cell under the frame (`ps2entry.graded_cells`)

**How each cell is chosen:**
- Each tile cell takes the richest of four tiers its views allow:
  - one-player mesh within 100 units of the road;
  - within 60;
  - within 30;
  - the split-screen mesh as driven.

  Beltway's tiers are different: one-player within 60, every building and the window bands kept; then within 30 with
  buildings to 100 units; then buildings to 100 units only; then as driven.
- The cap is on scenery records a frame (Phase 28's model at every road point, both ways). Within 50 points after the line,
  where the sixteen cars are still bunched, the cap is 1 200 lower (§13.4).
- The cell stepped down is the one in the worst frame whose step saves most. A poorer cell beside a richer one also takes
  the poorer faces reaching into it (seams), and the grading repeats until the cells as written hold the cap.
- Then the polygon ROM: Island and Mountain have byte budgets, and the heaviest steps are taken first.
- The roadside (uprights within 60), the banners and the flags are in every tier.

**The caps come from MAME, not the model:**
- A first build at the model's caps reached 10 495–10 500 records in RAIN on Island, Mountain and Beltway.
- Final caps: Island 6 500 (its byte budget holds it at 6 301 anyway), Mountain 4 450, Beltway 6 000.

**What reads as distance on these courses:**
- The far hills', rocks' and skyline's detail, which the split-screen mesh drew coarse.
- The pop-in of a whole row of cells about 256 units ahead at the 5 × 5 edge, softened by the far silhouettes.
- On Island, the sea.

**What the room buys:**
- the finer mesh out to 100 units wherever the frame allows;
- more far silhouettes (Island 907 faces of 150 u² or more, Mountain 476);
- Beltway's skyline with no distance cut and its window bands.

**It does not buy:**
- a farther walk (§11.1);
- the sea's reach.

**The share of the one-player mesh now in** (triangles within 60 / 100 units of the road; first figure pack 2 as driven,
second the new set):
- Island: 66 → 99 % / 65 → 96 %
- Mountain: 45 → 85 % / 45 → 80 %
- Beltway: 72 → 94 % / 61 → 88 %

### 13.3 The new pack 2 (`out/p90/pack2c/set2`, = `pack2c/play`)

**Scenery per course** (records a frame: Phase 28's model as built, median / peak and where; the MAME figures are below):

| course | faces' polygon bytes (as driven → new) | cells per tier, richest first | records a frame, median / peak |
|---|---|---|---|
| Island | 595 KB → 871 KB | 54 / 10 / 3 / 9 | 3 070 / 6 301 (road point 217, reverse) |
| Mountain | 591 KB → 1 000 KB | 49 / 10 / 6 / 18 | 3 031 / 4 427 (309, reverse) |
| Beltway | 855 KB → 1 374 KB | 60 / 17 / 3 / 23 | 3 610 / 5 850 (296, normal) |

- **Seams:** 397, 527 and 712 faces.
- **Polygon ROM left:** 157 860 B.
- **What limits each course:**
  - Island: the polygon ROM. Its frame would allow more.
  - Mountain: the frame at the canyon (road points 190–290), which stays as driven, and the polygon ROM.
  - Beltway: the frame, mostly at the start line (the bunched field) and at its densest blocks.

**The Saturn extras:** none fits. A Saturn course needs at least 433 KB of polygon ROM and 158 KB is left; the PS2
courses could give some back only by going below the frame's ceiling. The wheel has six entries: the arcade's three,
Island, Mountain, Beltway. Entries 7–10 are hidden copies of Beltway.

**What else changed:**
- `select.bands_for` takes 6–10 entries.
- A hidden copy shares its course's storm data. The lightning blob and an entry's course data are stored once when
  identical (`carrier`, `lightning`).
- The originals' direction-screen pictures stay off the storm's blocks when they are reserved (`install_original_pictures(exclude)`).

**Headless runs** (MAME 0.289, autopilot, clock held, four jobs at most, no window; 300 s DRY normal, 150 s otherwise):

| run | laps | checkpoints | rate windows | records peak | worst pass | 15 opponents |
|---|---|---|---|---|---|---|
| Island DRY / RAIN | 4 / 2 | 12 / 7 | 135/135, 59/60 | 7 204 / 9 672 | 13.6 / 17.6 ms | running, none held |
| Island reverse DRY / RAIN | 2 / 2 | 7 / 6 | 59/60 | 8 085 / 9 695 | 11.0 / 17.5 ms | running |
| Island pit stop | | | no miss | 6 453 | 13.3 ms | |
| Mountain DRY / RAIN | 4 / 1 | 12 / 5 | 135/135, 59/60 | 7 890 / 9 592 | 12.9 / 17.5 ms | running |
| Mountain reverse DRY / RAIN | 1 / 1 | 5 / 5 | 59/60 | 7 172 / 9 425 | 13.1 / 17.5 ms | running |
| Beltway DRY / RAIN | 3 / 1 | 10 / 4 | 135/135, 59/60 | 8 670 / 10 030 | 10.9 / 17.5 ms | running |
| Beltway reverse DRY / RAIN | 1 / 1 | 4 / 4 | 59/60 | 8 544 / 10 172 | 11.4 / 17.5 ms | running |

- **Stale pictures:** none in a race. The 300 s Island DRY run shows its post-race scene load at frame 16 345, as in §12.4.
- **Island's pit stop:** the trigger on the pair, parked still for 444 frames, +384 on the clock, stops 2 → 1.

**Pack 1:** built again after the last change to shared code. All 38 members are identical to main's build.

### 13.4 The holes in the hills (the lead's look at the Island sheet)

At Island's road points 144 and 147 (the hill over the tunnel) and 255 (the far ridge), and at 150, the sky showed through
the hills in the new set. Pack 2 as driven had the same holes, smaller.

**How they were found:**
- From the road's cameras, every 6th road point both ways, faces within 150 units, the sky's pixels where the one-player
  reference draws ground (`holes.py`).
- Then each of the conversion's stages was drawn alone at the worst places.

**Causes, in order of size:**
1. **`merge_coplanar` made wrong unions.** For some pairs of faces the joined polygon did not cover the two faces: walking
   the second face from the shared edge produced a quad over a different area. A hill's faces vanished and left
   triangles of sky. This is the arch at 150 and the notches at 144, 147 and 255. It happened in pack 2 as driven too.
   - Fixed: a union is taken only when its area is the two faces' areas, within 1 %. On Island, 211 of the 387 merges stay.
   - New test: a wall of 32 triangles keeps its area exactly through merging.
2. **The join between two detail levels.** With the one-player mesh near the road, a split-screen face straddling the
   radius was dropped by its centre while nothing covered its outer part, leaving a ring of sky.
   - Fixed by closing the join on the coarse side: a coarse face goes only when all its corners lie inside the radius,
     and a fine face comes when any corner does. They overlap along the join.
3. **The joins between tile cells at two tiers.** A richer cell missed the richer faces binned next door that reach into
   it, as a poorer cell missed the poorer ones. Both directions are now filled.
4. **Far ground the split-screen mesh never had** (hills behind a ridge). Within the detail radius the one-player faces
   now come in; beyond it, one-player faces that no split-screen face covers in plan are added (`uncovered`).

**Not holes:**
- **Beltway:** buildings missing beyond 60 units in cells stepped down to a poorer tier. These are the frame's limit.
- **Island:** the far hills beyond the cells, where the reference keeps more than the split-screen mesh.

**The frame's ceiling re-checked:**
- The seams cost records and bytes, so the grading now repeats until the written cells hold both the cap and the polygon
  budget.
- The first fixed set still reached 10 500 in Beltway's reverse RAIN, about 13 s after the start with the field still
  bunched. The lowered stretch after the line is now 50 points and 1 200 records.

**Confirmed in MAME:** `out/p90/pack2c/sheet_seams.png` shows before and after at Island 144, 150 and 255, Mountain 18 and
42, and Beltway 36 and 156. The holes at Island 144, 150 and 255 are closed.

## 14. The course select on the six-entry wheel: the cursor on screen, and the owner's stick (26 Nov, takeover)

The owner: "for some reason i cant select beltway"; "my joystick lock one row before"; "i still unable to select beltway".

### 14.1 The cursor, on pictures (`out/p90/pack2e/sheet_select.png`)

- **How:** headless MAME 0.289. `autoplay.lua` holds the wheel port at one value from frame 735. Snapshots are taken every
  4 frames from 855 (2 s held) and at 1190, just before the gas press. The gas then locks the entry, and the collision
  log says which entry loads. The yellow frame blinks, so the sheet shows the first snapshot in which it is lit. The slot
  it stands on is also counted from its pixels.
- **Pack 2, six entries** (`pack2e/set`, built from 2a18dd7). Every value below shows the cursor on the panel of the entry
  that the gas then races. Beltway, held at 212, raced to road point 179.

  | port | 0 | 44 | 100 | 116 | 128 | 136 | 156 | 212 | 255 |
  |---|---|---|---|---|---|---|---|---|---|
  | panel under the cursor | Big Forest | Big Forest | Bay Bridge | Acropolis | Island | Island | Mountain | Beltway | Beltway |
  | entry raced | 0 | 0 | 1 | 2 | 3 | 3 | 4 | 5 | 5 |

- **Released set** (`out/p88/play`):
  - port 0: Big Forest under the cursor, entry 0 raced;
  - port 128: Diablo Canyon, entry 5;
  - port 255: Surfers Road, entry 9.
- **Wheel sizes 7 to 9:** no set of these sizes is built, so they are checked only by the record test, every entry on its
  window slot (`tests/test_pack.py`). Pack 1's ten entries are byte for byte main's build (item 1 of the takeover).

### 14.2 The owner's recordings, replayed (`out/p90/takeover/rep`, `stick.txt`)

**How:** each `.inp` is replayed headless (`-playback`) on its play folder's set, with that folder's `start/` battery RAM and
settings. The recording is read from a copy, so the play folder is left alone. Logged every frame: the wheel port, the pedal,
the course select's handler and the entry the game holds (`[0x501940]`).

**The device:** an Xbox One Elite 2 controller (`mame-10s.log`: "Adding joystick #1"). Its thumbstick is an ABSOLUTE axis
mapped to the paddle.
- On the select screens the port sits at 128 (rest), 0 or 255 most of the time.
- A push from 128 to an end takes 1 to 3 frames, a jump; one push of the thirteen took 25 frames. Each entry in between shows
  for 2 frames on the way.
- The owner also holds the stick part-way. Each hold stays within about 3 to 7 port units for 30 to 80 frames:
  - 151-157, then 165 for 47 frames (pack 2, nine entries);
  - 170-172 for 66 frames (the Island prototype);
  - 93-95 for 38 frames, and 113 for 31 frames (pack 2, nine entries).

| recording (wheel) | port on the select screen: 0 / 128 / 255 / other (frames) | what was chosen, and how |
|---|---|---|
| p80j2-62s (ten) | 25 / 41 / 0 / 2 | Big Forest (0): pushed to 0, held 22 frames, gas |
| beltway-46s (ten, Beltway at 9) | 0 / 52 / 53 / 1 | Beltway (9): pushed to 255, held 50 frames, gas |
| island-63s (ten, Island at 7) | 23 / 61 / 90 / 82 | Island (7): a part-way hold at 170-172, 66 frames, gas |
| mountain-84s (ten, Mountain at 5) | 0 / 82 / 0 / 0 | Mountain (5): the stick at rest, gas |
| pack2-80s (nine) | 0 / 173 / 0 / 189 | Beltway (5): part-way holds (entries 6 and 8 shown), then 5 |
| pack2-b-114s (nine) | 0 / 108 / 0 / 0 | Mountain (4): at rest |
| pack2-c-69s (nine) | 0 / 127 / 0 / 127 | Island (3): part-way holds at 93-127 |
| pack2c-49s (six, first bands) | 0 / 155 / 0 / 51 | Island (3): Mountain held part-way 50 frames, back to rest, gas |
| pack2c-b-17s (six, first bands) | 13 / 652 / 438 / 109 | none. 255 held 50, 59, 112 and 217 frames: the game held Beltway (5) each time, but the cursor was drawn on Mountain. No gas press; the stick back at rest |
| pack2d-10s (six, today's bands) | 35 / 882 / 125 / 12 | none. 255 held 81 and 44 frames: Beltway held, the cursor on Mountain. No gas press; the recording ends on the select screen |

- **The owner's failed sessions.** In both, the stick reached 255 and the game held Beltway, but the screen showed the
  cursor on Mountain, so the owner never pressed the gas. This is the cursor fault fixed in 2a18dd7, which §14.1 confirms
  on pictures. It is not a stick that cannot reach the band.
- **What this device holds long enough to lock:**
  - **(a) The released ten-entry wheel.** Entries 0, 5 and 9 by the stick's end or rest. Entries 1-4 and 6-8 only by a
    part-way hold inside a band 14.6 port units wide. The owner did that on the prototypes (entry 7) and on the nine-entry
    pack 2 (entries 2, 3, 6, 8). A flick does not do it: 2 frames per entry.
  - **(b) Pack 2's six-entry wheel, today's bands.**
    - Big Forest (0-97), Island (128-142, the rest position) and Beltway (158-255) are held with the stick at an end or
      at rest.
    - Bay Bridge (98-112), Acropolis (113-127) and Mountain (143-157) need a part-way hold within about ±7 units, the same
      width as the ten-entry wheel's bands.
    - The owner's holds flicker at that width: pack2-80s at 151-165 switched between two entries.
    - The rest position is one unit from Acropolis's band (127). The released wheel has the same property at its
      entries 4 and 5.

### 14.3 Options for the owner (the selection is NOT changed: the lead's and the owner's call)

1. **Equal bands over the travel that counts.**
   - The game reads R10 ≈ 1.72 × (port − 128), clamped near ports 54 and 202. Six equal bands over that span are about
     24.7 port units each: Big Forest below about 78, Bay Bridge 78-103, Acropolis 103-128, Island 128-152, Mountain
     152-177, Beltway from 177.
   - Gain: the three middle entries' bands become 1.7 times wider than today's (24.7 units against 14.6), easier to hold
     part-way.
   - Cost: the ends need a fuller push. The rest position stays on a boundary (an even number of entries), unless the
     bands are shifted by half a band.
   - It is data only (`select.bands_for` for menu 6) and pack 1 stays identical.
   - Pack 2's first six-entry wheel spread its bands over the whole 0-255 travel, which is not the same thing.
2. **A stepping selection.** Each push from the rest position past a threshold, and back, moves the cursor one entry.
   - Every entry is then reached by flicks alone, which suits this device's 0/128/255 use.
   - It touches the select's band routine (the V60 code at the `ZONES` site that `select.py` writes) and needs a latch in a
     free RAM byte. The redraw needs no change: it already follows the index. The DIRECTION and WEATHER screens need none
     (two choices each).
   - Pack 1 can stay byte-identical: the routine is chosen by the pack's plan (pack 2 only), as the wheel's size already is.
   - Costs:
     - a new routine and its MAME test;
     - up to five pushes from Big Forest to Beltway against the select's countdown;
     - a play style unlike the arcade's.
3. **MAME-side settings.**
   - **Today:** the play sets' `start/cfg/vr.cfg` holds no input section. The driver's defaults apply: the paddle at
     sensitivity 100, `PORT_KEYDELTA(3)`, which in MAME sets both the digital speed and the auto-centre speed to 3, not
     reversed.
   - Digital speed and auto-centre act only on DIGITAL inputs (keys, a d-pad mapped to the paddle's dec/inc). The Elite
     2's thumbstick is an absolute axis: no digital-speed or auto-centre setting slows it.
   - A slow sweep would need the d-pad mapped to the paddle's dec/inc with digital speed 1. That is about a third of
     today's speed (MAME's scaling, not measured here). The thumbstick stays mapped for the race. The d-pad must stay held
     while the gas is pressed, because auto-centre brings it back.
   - Sensitivity below 100 on the thumbstick would shrink its reach for the whole game, the race's steering included: not
     advised.

The takeover's view (input for the lead): the owner's two failures were the cursor drawn on the wrong panel. With `pack2e`,
Big Forest, Island and Beltway are reached at the stick's ends and rest. A relaunch on `pack2e` tells whether any change to
the selection is still wanted. If the owner finds the part-way entries hard (Bay Bridge, Acropolis, Mountain), option 1 is
the cheapest change and option 2 the most robust.

## 15. Beltway's split road after the start (26 Nov, takeover)

The owner, on `pack2e`: "at the beginning of belway, the road is split in half with pilon separating both side, in the recording
i went to the right side and keep getting reset until i finally pass it, the left side is fine".

### 15.1 What the recording shows

- **How:** the owner's `pack2e-62s.inp` was replayed headless from a copy of the play folder, with `start/` copied too. Logged
  every frame: the car's position, its road point, its lap-position quad and remembered quad, the segment flag, the
  off-course counter `0x50115c` and the put-back timer. Logged every logic frame: all five collision calls of the car,
  each wheel's quad.
- **Where:** Beltway road points 54-66, on the owner's right of the divider (lateral +8 to +16 units).
- **What happened:** the wheels kept reading verge quads and wall quads, with the crash slide each time. The heading
  flipped and the speed fell from 190 to 0 twice. The off-course counter climbed to 119 against the limit of 128.
- **No put-back fired:**
  - no position jump;
  - the counter stayed under its limit;
  - never all four wheels on wall.

  The "resets" the owner saw were the wall slide (formats §5: `0xfec152` → `0xfec2ac`, which puts the car back on the
  wall's edge and turns it along it) and the car stopping on grass.

### 15.2 The cause in the converter

- The PS2 road is one tarmac band, about 34 units wide (`AT` kind 0 under the pylons too). Two closed `KB` wall boxes stand
  in its middle, each about 3 units wide: road points 54-58 and 60-64.
- `ps2course.scan` took the first wall crossing from the band's centre as each edge's wall: 1.56 units, the pylons.
- `collision` then laid each side's "verge" from the tarmac edge back in to 1.56, and a 4-unit wall strip outward from
  there. Both carriageways were covered by grass and wall quads. The TGP gives the nearest height and, on exact ties,
  the last listed quad.
- Top views (scratch): `out/p90/split/ana/top_split.png` before and `top_split_after.png` after. Each shows the PS2's `AT`
  triangles and `KB` walls against the converted quads and the owner's path. `top_zoom.png` is a close view of the first box.

### 15.3 The fix (PS2 only; pack 1 byte-identical, re-proven)

- **`_walls_across`:** a wall crossing more than 4 units inside the tarmac edge, with tarmac beyond it, stands IN the road.
  That is a divider: the lateral offsets of its faces, at least 1.5 wide. The road's edge walls are the first crossings
  that are not inside.
- **`divider_ends`:** finds where a divider begins or ends between two sections, every 0.5 units.
- **`collision`, on a divided section pair:**
  - two tarmac quads, one each side;
  - a wall quad over the divider, at the road's height;
  - where the divider ends inside the pair, the rest of the pair as one band.

  Tarmac is never laid under the divider: the TGP gives tarmac the exact ties, so a wall over tarmac would never be read.
  Such a slice is not merged (`merge_straights(keep=)`, a new optional argument whose default keeps pack 1 as it was). Its
  other pieces follow its first in the tarmac list, in lap order.
- The PS2 collides with these walls (`KB`), so the arcade does too.
- The pylons' scenery is unchanged. The opponents' eight lines are unchanged in position and heading. Their links now name
  finer segments at road points 55, 56, 62, 63 and 65. The checkpoints are unchanged.
- **Test:** `test_a_divider_in_the_road_leaves_both_carriageways_tarmac`, a synthetic box on the ring. It fails on the old
  code.

### 15.4 The scan of all three courses (`out/p90/split/ana/scan.py`; the converter's output against the PS2's own collision)

**PS2 road (`AT` road and kerb kinds) the conversion does not give as tarmac**, after the fix. Areas are in square units.
Excluded: area behind or under a PS2 wall, and kerbs raised more than 2 units (the barrier tops).

| course | before | after | where, after |
|---|---|---|---|
| Beltway | 1 071 verge + 162 wall at road points 54-65: the split | none beside the pylons | the pylons' own footprint, about 170 (a wall on the PS2 too) |
| Island | 33 kerb at 1-21, 24 at 247-269, 18 at 281-284, 9 at 128-129 (unchanged) | the same | kerb and verge slivers under 2 units wide at the band's edge |
| Mountain | 35 at 121-122, 28 at 171, 55 at 290-295 (unchanged) | the same | verge slivers where the tarmac bulges past the band by under 2 units |

**PS2 walls the conversion lets a car drive through** (units of wall footprint):

| course | before | after |
|---|---|---|
| Beltway | 260 at road points 54-64 (both pylon rows) | single samples of 2 units at 60 and 64 (the boxes' corners), and 2-6 at 143, 215, 242, 263 and 278: posts at the road's edge |
| Island | 14 at road point 24, 38 at 306-307 | the same: the pit lane median's nose (about 7 units) and a post |
| Mountain | 50: posts on the grass run-off (0, 96, 119, 230, 243, 277, 284) | the same |

- Only Beltway has a divider (sections with one: Beltway 10; Island and Mountain 0). Their collisions are unchanged by the
  fix (1 460 and 2 004 quads, as before).
- **Not fixed: the residual posts and slivers.** A wall over a verge or over tarmac is never read unless the quad under it
  is cut around it. They are a few units each and not of the split's class. The Island median's nose is the section
  spacing (8 units) on the pit lane's median, which is validated as driven.

### 15.5 Evidence (headless, MAME 0.289, no window)

- **The owner's recording on the fixed set (`pack2f/set`):**
  - It is identical to `pack2e` up to frame 1898, road point 54, the first divider. From there the collision differs,
    so the owner's later inputs no longer apply.
  - Through road points 50-70 on the fixed set: no logic frame with four wheels off tarmac (147 before). The counter
    peaked at 8 (119 before). No position jump.
- **Scripted drives** (autopilot with lookahead 3, on the centreline moved 11 units to one side through road points 48-66):

  | run | wheel on a wall | four wheels off tarmac | counter peak | put-backs | records peak there | worst pass | rate min |
  |---|---|---|---|---|---|---|---|
  | pack2e, owner's right side, DRY | 60 | 83 | 78 | 0 | 6 977 | 10.9 ms | 28 |
  | pack2f, right side, DRY | 1 | 0 | 1 | 0 | 5 937 | 9.9 ms | 28 |
  | pack2e, left side, DRY | 0 | 0 | 0 | 0 | 5 764 | 10.6 ms | 28 |
  | pack2f, left side, DRY | 0 | 0 | 0 | 0 | 5 593 | 10.0 ms | 28 |
  | pack2e, right, RAIN | 11 | 0 | 11 | 0 | 9 655 | 17.5 ms | 28 |
  | pack2f, right, RAIN | 1 | 0 | 1 | 0 | 8 294 | 17.5 ms | 28 |
  | pack2f, left, RAIN | 56 (40 the divider: the wet car slid onto it and along it) | 0 | 55 | 0 | 8 453 | 17.5 ms | 28 |
  | pack2f, reverse RAIN (both offsets) | 45 / 63 (sliding along the divider) | 0 | 33 / 41 | 0 | 7 933 / 7 975 | 15.4 ms | 28 |

  - No stale list at the split in any run.
  - All 15 opponents passed the split in every normal run. In reverse, seven passed by the 150 s end on both sets alike.
  - Records are counted at the split only. The whole runs on `pack2f` peak at 9 631-10 256, under 10 500.
- **Pack 1:** rebuilt after the change to `collision.py`. All 43 members are identical to main's build.
- **Set:** `out/p90/pack2f/play` (`launch.sh` written, NOT run).

## 16. Beltway's opponents at the divider (26 Nov, takeover)

The owner, on `pack2f`: "seems the oponent didnt crash (it s fixed now for me". The split was fixed for the player. The
opponents still rode their lines through the pylons: their seven lines are fixed offsets of the centreline, and lines 2, 3
and 6 cross the divider.

### 16.1 Where the PS2 sends its cars

All three of the PS2's lines pass the split on the right-hand carriageway (offsets from our centreline):
- NORMAL (the racing line): +8.1 to +8.3;
- RETURN: +7.6 to +8.7;
- DIRLINE: +5 to +10.5.

So every opponent line goes down the right side, as on the PS2 (`_racing_side` reads it from NORMAL.PAT).

### 16.2 The lines (`lane_scales` → `divider_lanes`; PS2 only, the centreline and the player's line 0 unchanged)

- **Beside a divider:** every line's reach lies in the racing side's carriageway. It keeps DIVIDER_CLEAR (8) from the
  divider's face and AI_MARGIN (4) from that point's edge. The edge is the kerb, or a wall, the narrowest within three
  points.
- **First try, with AI_MARGIN from the face:** the opponents lagged 3-5 units onto the divider. The bend just before the
  pylons pushes them out, and an opponent steers at its cursor + 2. Headless, 8 passes of 55 went through a box.
  - The clearance is now 8, reached DIVIDER_GUARD (6) points before the divider.
  - It is held as long after it, with a smoothstep of DIVIDER_RAMP (10) points either way.
  - On the way, no line goes past that point's own edge.
- **Posts (`_wall_reach`):** where a wall stands within WALL_CLEAR (3) of the outermost line, that side is bounded by the
  wall instead of the kerb. These are Beltway's posts on the kerb, at road points 101-110, 131-138, 211-217, 230-245,
  260-266 and 310-317.
- **Island and Mountain:** no line comes within 3.6 units of a wall. Their lines are byte for byte as before.
- **Beltway's lines, offsets from the centreline:**
  - before: -8, -3, 3, 8, 5, 0 and -5 everywhere;
  - now: from road point 40 they move right; at 50 they are at +9.4 to +10.4; at 54-64, beside the pylons, at +9.6 to
    +13.3; at 66-70 at +9.1 to +10.1; by 82 they are back to the plain offsets.
  - The least distance from any line to any PS2 wall on the course: 2.8 (line 4 at the bend before the pylons, road point
    49; it was 1.1 at the pylons and 1.2 at a post).
- **Tests:** `test_beside_a_divider_every_ai_line_keeps_to_one_carriageway`, both sides on the synthetic ring.

### 16.3 Evidence (headless, `pack2g`)

Each run is 270-300 s with the clock held. The player is on its scripted right-side line, so the field passes the split
3-4 times per car. Distances are each opponent's least distance to the divider's walls on each pass; negative means inside
a box.

| run | passes | inside a box | least distance | stops (30+ frames) / jumps in the race |
|---|---|---|---|---|
| pack2f, DRY (before) | 55 | 24 | -1.56 | 0 / 0 |
| pack2g, DRY | 55 | 0 | 0.37 (car 6 once, at the divider's nose); every other pass 2.6 or more | 0 / 0 |
| pack2g, RAIN | 52 | 2 (car 2 in the first lap's bunch at the nose; car 4 pushed by the player, 4 units away) | -0.49 | 0 / 0 |
| pack2g, reverse DRY | 52 | 1 | -1.00 | 0 / 0 |
| pack2g, reverse RAIN | 50 | 0 | 2.96 | 0 / 0 |

- **The player's scripted drives on `pack2g`:**
  - right side DRY: 1 logic frame on a wall, counter 1;
  - left side DRY: 0, counter 0;
  - right side RAIN: 1, counter 1;
  - no put-back.
- **At the split, with the player there:**
  - records peak 5 657 DRY and 8 698 RAIN (8 172 reverse RAIN);
  - worst pass 10.0 and 17.5 ms;
  - rate windows 28 or more;
  - no stale list.
- **Elsewhere in the RAIN races:**
  - The peak is 10 494 at road point 257, with no list skipped. It is the dense city, not the split.
  - `pack2e` and `pack2f` reached 10 256-10 260 at road points 172-224 on the same scripted line.
- **Checkpoints, links and segments:** unchanged. Only Beltway's eight lines differ from `pack2f`, in banks 1's members
  `mpr-14884/5`.
- **Set:** `out/p90/pack2g/play` (`launch.sh` written, NOT run).
- **Pack 1:** no shared code changed in this round (`ps2course` only), so it stays byte-identical as proven after b40ea67.

## 17. The rain's room on the PS2 courses (26 Nov, takeover; the session lead's ruling, option A)

### 17.1 What the frame log says

`frame_rate.lua` logs two counts per pass:
- **records:** the frame's peak count, the rain's records included.
- **need:** the highest count the list walker compared with the budget, which is the least budget under which no list is
  skipped.

The released rate test keeps its floor on `need` (Big Forest line 4: `need <= 10 500 - 400`). The rain is drawn last and
only while the count is under the budget (rain.py), so a frame at 10 500 records thins the rain; it does not skip a list.

| set | course and run | records | need there | lists skipped |
|---|---|---|---|---|
| pack2g | Beltway, first lap with the field bunched, right-side line | 10 494 at road point 257 | 8 007 | none |
| pack2g | Beltway reverse | 10 144 at road point 112 | 8 164 | none |
| pack2e | Beltway | 10 500 | 8 062 | none |

The max-detail design meant to hold the storm's peak under 10 200, so 10 200 is the rain's room.

### 17.2 The standing test (`tests/test_pack_rate.py`, gated on `VR_PS2_DISC` and MAME)

- **Setup:** pack 2 is built once. Each course is run normal and reverse in RAIN for 200 s with the clock held, the
  scripted car from the boot through the start (the first lap's bunched field in view):
  - Island and Mountain on their centreline, lookahead 6;
  - Beltway on its offset-0 AI line (the right-hand carriageway beside the pylons), and again on the line the owner drove
    past the pylons, where pack2g's 10 494 came from.
- **Assertions, per run:**
  - `need <= FRAME_BUDGET - 400` and no list skipped: the scenery's lists;
  - `records <= 10 200`: the rain not being cut short.
- **Island's crash:** with lookahead 3 the scripted car crashed at Island's road points 152-160, and the stopped view
  reached 10 500. That was the script, not the course. On the test's line Island peaks at 9 705 / 9 682.

### 17.3 Where detail was lowered (`Ps2Plan.frame_cuts`, `ps2entry.cut_frames`; Beltway only)

**Method:**
- Each failing view's cap is lowered, and those frames step their farthest cells down first (`grade(far_first=)`).
- Every tier keeps the uprights within 60 units and the banners, so stepping down never touches them.

**The cuts:**

| direction | road points | cap lowered by |
|---|---|---|
| normal | 180-226 | 400 |
| normal | 252-262 | 700 |
| reverse | 99-115 | 400 |

**The model's records at those views, before → after (max):**

| direction | road points | before | after |
|---|---|---|---|
| normal | 180-226 | 5 813 | 5 219 |
| normal | 252-262 | 4 997 | 4 324 |
| reverse | 99-115 | 5 977 | 5 103 |

**Given up:**
- Beltway's tiers go from 47 / 19 / 3 / 37 cells to 47 / 15 / 6 / 38.
- Faces: 21 861 → 21 792. Scenery bytes: 1 406 808 → 1 408 288; other cells re-graded richer under the relieved global cap.
- 45 cells changed.

**Stills:** `out/p90/pack2h/sheet_floor.png`, at normal road point 257 and reverse road point 112, before and after. The
difference is a few far buildings.

### 17.4 Figures (`tests/test_pack_rate.py` on pack2h: "8 passed in 358.39s")

| course | normal: records / need | reverse: records / need |
|---|---|---|
| Island | 9 705 / 7 761 | 9 682 / 7 880 |
| Mountain | 8 693 / 6 634 | 9 262 / 7 484 |
| Beltway | 9 702 / 7 455 | 9 142 / 7 167 |
| Beltway, the owner's line | 9 771 / 7 258 | 9 142 / 7 167 |

- No list was skipped in any run.
- Island and Mountain are unchanged in bytes.
- **Set:** `out/p90/pack2h/play` (`launch.sh` written, NOT run).
- **Pack 1:** rebuilt after this round's change to `pack.py`. All 43 members are identical to main's build.

## 18. Fix round 1 after the branch's review (26 Nov)

**Done:**
- C1: pack 1's identity is a standing test (`tests/test_pack1_identity.py`, 43 sha256 pinned from v0.4.1); the storm's sharing
  of stored course data and lightning blobs follows the plan's hidden entries only (`carrier.hidden_copies`, `shared_with`).
- I1, I10: the grading refuses to ship a frame over its cap or the scenery over its budget after 8 rounds, and a capped cell.
- I2: `--tune` reaches the chosen pack's courses (`ISLAND:pace=1.1` with `--pack ps2`).
- I3: pack 2's run line names its own battery RAM folder; a headless test of the tag both ways (`tests/test_pack_mame.py`).
- I4: the parked check in RAIN at each course's three worst views per direction (the build's model, 30 road points apart) and
  Island 152-160: worst need 7 681 and records 9 401 (Island, parked at 156); no list skipped; no cut needed.
- I5: the cursor checked on the installed records against the installed draw routine, and on pictures (the frame on each
  entry's own panel); both RED on the code or set before 2a18dd7.
- I6, I8, I9: the banner test asserts; the caps' comment and how to redo the measured values (`tests/pack2_cuts.py`); the
  variant code removed (pack 2's bytes unchanged).
- I12: the start gantry compared with pack 1's on Big Forest during the countdown (see the fix round's report for the figures).
  Corrected by §19: the gantry is not in view at the countdown; it is compared at the end of Big Forest's first lap.
- Minors: the report (graded tiers, wheel size, pack tag), the readers' errors under one base and reported with exit 2, the
  `--saturn` note, the LZSS stop, `HOST_OF_BANK` once, the doubled comment.

**Open (not in this round):**
- I11: Island's reverse pit stop (no pit lane in reverse).
- I7's race gates for pack 2 as standing tests: the arcade's rate pass for pass, the stale list, the 17.9 ms rain cap, the
  opponents running at the end, the checkpoints, Island's pit stop, a finished race writing its best-time table and that table
  under its course, the DRY identity against pack 2 built with the weather off, the flash rule's stress form on the three
  PS2 courses. Today `tests/test_pack_rate.py` (need, records, parked) and `tests/test_pack_mame.py` run from the tree.
- The build report's room per region (bank 0-3, program ROM) for pack 2.
- The overhead faces' winding (the review's minor): not looked at in this round; what the player sees under an overpass is
  still to be checked on a picture.
- `build_lap`'s made-up 12-unit section: to raise if it happens on a real course (not checked on the three).
- Each PS2 course is decoded twice in a build (the disc check and the build).

## 19. Fix round 1b (26 Nov): the gantry check, pack 2's race gates, the owed runs

**Done:**
- I12 (`tests/test_pack_mame.py`): round 1's fourth picture was MAME's own `-str` snapshot at the run's end; autoplay.lua's
  `VR_SNAP_LOG` names the frame of each of its snapshots and the test picks by it. The start gantry stands at road point 0 and
  every grid starts past it (Big Forest from the pits), so it is first in view at the end of lap 1: Big Forest taped on the
  autopilot in pack 1 and replayed in pack 1 and pack 2, rows 0-200 identical pixel for pixel over 23 frames before the lap's end
  (lettering 699 px at the nearest); Island (pack 2, clock held) shows its START in the arcade's lettering colours (737 px).
  Stills: `out/p90/fix1b/gantry_sheet.png`.
- I7, gates a, b, e (`tests/test_pack_gates.py`, built from the tree; `pack_sets.built(weather=False)` added, default unchanged):
  the rate and the display list DRY and RAIN (RAIN peak pass 17.56 ms of the 17.9 cap), the race to its own end (all six RAIN
  races end by time over; 4-8 checkpoints, each in order with its extension; fifteen opponents running, none put back; the
  machine running on), DRY = pack 2 without the weather pass for pass on a taped Island race. 19 passed.
- The owed no-MAME runs of the files round 1 touched (carrier, lightning, cli, tencourse): all passed (the task report has the lines).

**Open:**
- I7 gate c (Island's pit stop, normal), d (a finished PS2 race's best-time table shown under its course after a restart) and f
  (the flash rule's stress form on the three PS2 courses: it needs a stress-tuned pack 2 and its storm layout for the lightning
  log): not written in this round.
- The autopilot never finishes a PS2 race unheld (time over first): gate b sees time-over ends only.
- I11 and the rest of §18's open list unchanged.
- The final invocation (head d8a739c; the seven pack-2 files with `test_pack1_identity.py`): "109 passed in 1935.32s (0:32:15)".

## 20. Fix round 1c (26 Nov): the last race gates, a finished race, the re-review's items

**Done** (`tests/test_pack_gates.py`; the released tests' helpers imported):
- Gate c, Island's pit stop (normal): the released pit test's form. Trigger on the pair, parked at the box, 444 work frames, the
  clock +384, stops 2 -> 1, out of the lane after the release.
- Gate d, best times: a one-lap Beltway race by race_end.lua (the released ranking tests' finish, the clock held) records 75.75 s
  first in Beltway's table, and in no other. After a new boot on that battery RAM, Beltway's page shows it. No page of a hidden
  entry is shown: the game's attract group 0 holds none, though `attract_groups` on the decoded directory would.
- Gate b, a race to the game's own finish: Island DRY with the harness's clock hold, five laps counted one by one, the finish,
  then the RECORD sequence to the attract.
- Gate f, the flash rule: pack 2 built with the lightning's stress tune through the pack's own build (`pack_sets.built(tunes=,
  tag=)`; its storm layout from `pack_sets.layout`). On Island, Mountain and Beltway: 29-30 strikes, 72-74 onsets, never more
  than three in a second.
- The re-review's 5a: under VR_REQUIRE_REFERENCE_SETS=1 the pack 1 identity gate and the pack-2 MAME modules fail when their
  inputs are missing, instead of skipping. 5b: the minors (§18's gantry line, a test comment, `build_pack`'s parameter, the
  report's capped count).
- No gate failed on the real game. Pack 2's bytes equal `out/p90/pack2h/play`'s.
- Final invocation (head e9aa267): "32 passed in 1799.48s (0:29:59)".

**Open:**
- I11 and the rest of §18's open list unchanged.
- The released lightning stress runs (pack 1) were not rerun after `flash_rule` / `storm_env` were factored out (no-MAME parts
  ran).

## 21. Task 2 (26 Nov): the select pictures in colour, Island's reverse pit stop

**Done** (branch `phase90-ps2-pictures`, from 5ed9958):
- The select pictures (6ebee1a). Cause: the PS2 path ran the Saturn rule, a height ramp of the ten commonest face colours by
  COUNT: on the PS2 faces those are tarmac, wall and building greys; the sea (red 62-80) failed the Saturn's water test. Now
  `preview.course_picture(faces=, sea=)` colours each sample by the topmost non-upright face (`_top_view`) of the split-screen
  set whole (`ps2course.picture_faces`: the thinned scenery lost Island's sea and Beltway's blocks beyond 40 units), shaded by
  the Saturn pictures' mesh, the sea flat; where the PS2 models nothing (`_beyond`): inside the road's loop its commonest
  off-road colour, outside the sea when a quarter of what is seen there is sea, else the commonest; the course's tarmac greys
  never a fill. Same road, start mark, frame, name, quantiser; the Saturn path untouched. Coloured share of the map (channels
  apart > 30): Island 0.82 (was 0.09), Mountain 0.70 (0.07); Beltway is a grey city (0.11): parks green 9 %, the river blue.
  Headless sheet: `out/p90/task2/sheet_select.png` (new, pack2h, released).
- Island's reverse pit stop (bffa253). The released Saturn courses with pits have one (tencourse.py:986, `reverse.reverse_pit`);
  its choice is now `reverse.reverse_pit_in` on the course's pieces (pack 1 identical), applied by `ps2entry.reverse_pit_of`
  to the PS2 lane: pair (301, 302), the normal box turned half a turn. Gate c reverse (`test_islands_reverse_pit_stop`):
  trigger on 302, park, 444 work frames, clock +384, stops 2 -> 1, out of the lane, next lap, 15 opponents advancing.
- Pack 2 against pack2h: vr.zip's epr-14882.14, epr-14883.15, mpr-14880.6, mpr-14881.7. Play set `out/p90/pack2i/play` (its
  zips equal the final invocation's pack 2, member for member).
- Final invocation (head bffa253; the seven pack-2 files, test_ps2_picture, test_ps2_reverse_pit, test_convert_preview; PS2 disc,
  reference variables, VR_REQUIRE_REFERENCE_SETS=1): "127 passed in 2379.09s (0:39:39)"; pack 1 identity included.

**Open:** the PS2 pictures' colours are the PS2 swatches (darker and less saturated than the Saturn ramps); the fill where the
PS2 models nothing is a choice, not the disc's. Island reverse: the wrong-way warning and the gates after the release (the
released reverse test's extra checks) are not in gate c reverse (done: b17f398). The rest of §18's open list unchanged.
