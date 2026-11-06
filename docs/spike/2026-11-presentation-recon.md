# Phase 14 recon: the vanishing car, the course edges, the HUD map (31 Oct 2026)

Three defects seen in the website captures (`docs/spike/2026-11-website.md`), Pascal's call to fix them before the
page goes live. Experiments under `out/p14/` (display-list dumps, timed steers, rebuilt sets); scripts in the session
scratchpad; the autopilot gained `VR_RACE_WHEEL`, `VR_RACE_STEER="from:frames:value"` and `VR_EXTRA_LUA`.

## 1. The player's car is not drawn for whole stretches

- Measured on the Phase 13 captures with `spike/site_cuts.py` (red pixels of the car in the lower centre of the
  frame, half-second by half-second): the car is drawn while at speed on the road only 5–15 % of the time; on Alpine
  it vanishes from 38 s to 44 s at 64–82 units/s on the tarmac.
- Not the objects' size: Alpine's scenery quads are 16–32 units across (1611 of 1631 within 40 units of the
  centreline; the Saturn course scenery is a strip along the road), and the display-list dumps show our ground cell
  objects drawn last in every frame (`out/p14/alp-dlist`), as Big Forest's tiles are.
- **The cause is the polygon flags.** The polygon-ROM record's bits 10–11 are the *z mode*, how the polygon sorts
  (`docs/formats/model1-polygon-rom.md`): 0 keep the old z, 1 the nearest of the four depths, 2 the farthest.
  Big Forest's 25 368 tile polygons use `0x1a01 / 0x1801 / 0x1902 / 0x1b02` (z mode 2, the farthest, on 13 500 of
  them; mode 1 on 3 000); the cars' polygons use `0x5601 / 0x5401` (mode 1, the nearest). Ours were `0x4201` and
  `0x0001` / `0x1001` (mode 0): a ground quad under the car kept whatever depth the previous polygon left and sorted
  in front of the car.
- **Fix:** `polyrom.encode_object` sets `Z_MODE_MAX` (`2 << 10`) on both records of every quad. Rebuilt Alpine,
  75 s autopilot run (`out/p14/zmax`): the car is drawn in **95 %** of the half-seconds at speed (60 of 63), render
  rate 28–29 unchanged.

## 2. The car sails off the course

- `out/p14/bf-steer` vs `alp-steer`: from the race start + 500 frames the wheel holds 95 (a mild left) for 50 frames,
  then centres. On Big Forest the car runs 27 units off the centreline along `x = −169.4` for 200 frames at 36–45
  units/s: it slides along a **wall**, then (frame +1200) the game puts it back on the road (a crash reset). On
  Alpine the same input takes the car 54 units off the centreline onto the verge, where the grass slows it from 51
  to 16 units/s over 200 frames; the autopilot then brings it back. Our grass does slow the car; what Big Forest has
  and we do not is the wall, and the originals' run-off reaches 170 units where ours ends at 40: a car that crosses
  40 units of grass fast enough reaches cells with no quad (the collision map's 0) and keeps its height.
- The TGP's answer with no quad: `0xfed5d7` branches on the result word's bit, sets the height to −0.1 and the
  surface bits to kind 0 (`0xfed5f9`); the per-wheel kinds (`+0x142/144/146/148`) feed the attitude code
  (`0xfed6b9..`), where kinds 0 and 5 (`and #21`) pick which wheel pairs set pitch and roll.
- Big Forest's wall is the host's barrier entities (the `0xffcbfc` board rows and barrier pieces have collision:
  Pacific Coast "stopped dead at (272, −321) beside Bay Bridge's board row" in Phase 8). Converted courses drop the
  host's props and convert the Saturn's barriers as scenery only.
- **Fix candidates:** (a) wider verges (collision only, no render cost; the TGP list words grow with the cells each
  quad covers); (b) invisible barrier entities along the outer verge edge (needs the entity collision code); (c) the
  surface kind 5 (run-off) for the outer band if it slows harder. (a) first.
- **Budget, measured** (all seven courses, `tgp_budget` after `build_all`): 40 units (today) 69 784 words free;
  80 → 39 623; 100 → 24 771; 120 → Surfers Road no longer fits (short by 6 378); 150 → Alpine alone costs 38 000.
  Wide verges leave the collision map on the outer courses (the map covers −1024..1023): `road_verges` now pulls the
  outer corners back to ±1020 (`MAP_LIMIT`), which the 40-unit build never needed.
- **The swerve, measured** (`out/p14/alp-steer`, `bf-steer`; wheel 95 for 50 frames from race start + 500): Big
  Forest runs out to 26–28 units off the centreline, slides along the wall at 36–38 units/s for 200 frames, then the
  crash reset puts it back at 8 units (a jump of 160 units/s in the log). Alpine with 40-unit verges wanders to 46–49
  units off the centreline three times in 800 frames, slowing from 78 to 20 units/s each time; the verges end at 40.
  `out/p14/w100/steer-alp`, `steer-pac`: the same input on a 100-unit build (running).

## 3. The HUD course map is drawn mid-screen

- **How the map works** (display-list dumps on all three originals, `out/p14/bf-dlist`, `orig1-dlist`,
  `orig2-dlist`): the map is the first section of every frame (zoom 52.5 / 70, light (0, −0.4, 0.9), screen
  translate (149, 12)); its first object is the course outline (TGP-generated at course load, `poly 0x101ad4` on Big
  Forest's slot), followed by one marker object per car. The section's matrix is the car's **heading and position**:
  rotation = heading × 0.0008 (the same 1/1250 on all three originals), translation = −(car position) × 0.0008 with
  z 1.5. So the map is **car-centred, heading up, at a fixed scale**: the car's own point always projects to the
  screen centre + (149, −12) = (397, 180), and the fixed white cross drawn there is the player's marker.
- **Why the originals' maps sit at the right**: all three are clockwise circuits started on their west edge heading
  north (signed centreline area −505k / −449k / −656k; the course centroid lies to the right of the start heading).
  Driving a clockwise circuit, the course interior is always on the car's right, so the outline hangs to the right of
  the cross (and is clipped at the right edge at times, e.g. Big Forest at 27 s). **Alpine and Pacific Coast are
  anticlockwise** (+602k, +847k; centroid on the left): their outline hangs to the left of the cross, into the middle
  of the screen. The other five converted courses are clockwise. Course sizes are comparable: farthest point from the
  start 681–1017 units on the originals, 797–1285 on the converted.
- **Where the numbers live**: the section parameters are a table of 40-byte records in the boot ROM at `0xff9e22`
  (zoom, light, tx, ty); the game copies them to RAM once at boot (frame 9) — the map's record `0xff9e9a` goes to
  **`0x502300`**, so its translate is at **`0x50231c` (tx) / `0x502320` (ty)**, read every frame by the section
  writer (`0xff84f8`, `mov.w [R2+],[R5+]` with R2 = record + 0x1c) and never rewritten (write trace over a full run).
  Poking `0x50231c` moves the outline (and the car markers) on screen; the cross does not move: it is a **3 × 3 block
  of tiles** (codes `0xa73a..0xa741`, centre `0xa400`) drawn once at race start by `0xfeabf5..0xfeac03`
  (`movea.w #0x700ae0, R1` = page 0 cell (48, 21); `mov.w #0x2fa59a, R0` = the pattern in the program ROM; `jsr
  0xff9436`). The 8 bytes after the map's RAM record (`0x502328..0x50232f`) are never read or written after the boot
  RAM clear (full-run trace): free for us.
- **Fix** (per course, two knobs, both zero/original for the ten courses that are fine): for an anticlockwise
  course shift the whole map right by 88 px (11 tile cells) so its outline hangs within the same right-hand box as
  the originals': the directory record gains `map_tx` (float, 149.0 default; 237.0 for the shifted courses) and
  `map_cross` (byte offset into the tile page, 0 default; 22 = 11 cells); the course loader copies them to
  `0x50231c` and `0x502328`; the boot ROM's `movea.w #0x700ae0, R1` becomes `jsr <trampoline>; nop` with the
  trampoline (`mov.w #0x700ae0, R1; add.w 0x502328, R1; rsr`) in the directory's code area, so a zero offset (RAM at
  boot, before any course load) draws the cross where the game always did. The converter picks the shift from the
  centreline's signed area. Not done: a per-course scale (the 0.0008 is an immediate in several routines).

## 4. Outcome (Phase 14, `docs/superpowers/plans/2026-10-31-phase14-presentation.md`)

- Z mode 2 on every converted quad: the car is drawn throughout the new captures (`out/site3`); the cut finder's
  good runs are two to four times longer than Phase 13's.
- Verges 80 units (`VERGE_WIDTH`), outer corners held at ±1020 (`MAP_LIMIT`); a step whose laterals cross inside a
  tight bend or which contains a centreline point (Metropolis point 272: the upper deck's verge over the lower
  road) is built at 40 instead, dropped only if the narrow step still contains one. Budget: 40 996 words free in
  the CLI build (69 784 at 40 units; the test pins ≥ 30 000).
- Off-course limit per course (`CourseEntry10.off_course`, RAM `0x50232c`, the 12-byte `cmp.w abs,abs` at
  `0xfebcdf`): 40 logic frames on the seven converted courses, 128 on the originals. Measured in
  `tests/test_race_build.py::test_a_swerve_ends_on_the_verge_and_the_car_comes_back`: a 50-frame wheel input from
  race start + 500 on Alpine and Pacific Coast (the game's own steering otherwise, not the centreline autopilot,
  which would steer against it) takes the car off the road within 150 frames of the input, at most 80 units off the
  centreline, never without a quad, and it is back within 10 units inside 200 frames. The review caught the first
  version of the test measuring a later exit (its window started at the car's first movement + 500, 370 frames after
  the race start the input counts from); the gates had passed on that exit too. In the captures a car that runs wide spends a second or two on the grass or
  the water before the put-back. Not done: walls.
- HUD map: `map_tx` 237.0 and `map_cross` 22 on Alpine and Pacific Coast (anticlockwise by the centreline's signed
  area), 149.0 / 0 elsewhere; loader writes `0x50231c` and `0x502328`; the 7-byte `jsr` at `0xfeabf5` to the
  directory's `cross` routine. Measured in `test_the_hud_map_and_the_cross_move_together`: Alpine's display list
  carries translate (237, 12) with the cross tiles at columns 59–61, Big Forest (149, 12) at 48–50.
