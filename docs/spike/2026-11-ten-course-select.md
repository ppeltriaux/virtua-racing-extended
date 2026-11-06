# Ten-course select (Phase 7, M4)

`spike/ten_course_build.py out/p7/build` builds the set: entries 0–2 the originals, entry 3 Alpine (a blob in Big
Forest's bank, TGP slot 3, its own tile table), entries 4–9 the remaining Saturn names on Alpine's data until M5
converts them. `mame vr -rompath out/p7/build`; turn the wheel to scroll the row of ten.

## What the game does, and what changed

- **Selection.** `R10 = ([0x501060] + [0x50106c]) >> 1` runs −127..127 (≈ 1.72 × (paddle − 128), clamped at
  paddle ≈ 54 / 202). The original cuts it at 0x1c and 0x58; the band routine cuts it into ten bands
  (thresholds −102, −77, −51, −26, 0, 26, 51, 77, 102; band centres at paddle 61, 76, 91, 106, 120, 135, 150,
  165, 180, 195). The chosen entry is in the middle slot except at the ends; the three visible panels are
  redrawn from the directory when the band changes (0x501942 keeps the last drawn index). The yellow frame
  follows via the static slot position in the entry's select record; the BEGINNER / MEDIUM / EXPERT labels stay
  per slot (deferred).
- **Directory** at program ROM 0x278d70 (2 468 bytes of tables and code): ten 24-byte select records in the
  game's own layout, ten 64-byte load records (bank, TGP slot, template, label, header base, tile table, spawn
  list, pit quad, layer-B map, art, name), the band table, slot destinations, an empty spawn list, and the
  routines: loader (0x27951c), bank (0x2795fd), pit (0x279624), band (0x27963e), draw (0x27968b).
- **Patched sites** (exact-length, `nop`-padded, `unidasm`-verified): the loader 0xfe48ed (0xb7 bytes →
  `jmp`), the five `(data index + 1) << 4 | 1` bank switches (0xfe1d37, 0xfe2160 attract, 0xfe2b07, 0xfe2cf7,
  0xfe415b race; 0x16 each → `jsr`), the pit check 0xfe8e8f (0xd), the two select-table references (0xfc270b,
  0xfc28a3), the wheel zones 0xfc26df (0x1b), the panel blits 0xfc3622 (0x79) and the race-music read
  0xfc0bb8 (0xf). The `mov.b #1, E00004` sites map bank 0 (shared graphics) and stay. `[0x501934]` holds the
  entry's *template* (the in-race per-course tables, Bay Bridge 0 / Acropolis 1 / Big Forest 2). The routines
  use the menu entry only when its template equals `[0x501934]`; when the game set the data index itself
  (operator's fixed course, linked play, attract rotation) the original course for it loads — verified for the
  operator setting (`0x40dca1 = 2`: Bay Bridge, identical probe stream to the original).
- **Course blobs.** `arcade/blob.py` lays a course's tables out for any window address inside a bank (pointers
  are window addresses; the graphics directory is the host bank's) and first-fits it into the bank's 0xff runs
  (Alpine: bank 3 at window 0x12b390, 97 536 bytes). Collision goes to a free TGP slot (`install_collision`),
  scenery behind a new tile table in free program ROM (`write_tile_table`, 0x279720 for the first).
- **Panels.** Two 16 × 21-tile maps per panel (128 × 168 portrait): the picture (layer B, page 0, words
  0x8000 | char) and an overlay (layer A, page 2). Generated panels keep the host's frame, fill the interior with
  the picture's dominant colour and the name strip with white (new flat characters), and draw a stylised loop
  (resampled to 48 points, corner-cut three times, 3-px stroke), a start mark and the name in a 5 × 7 font as a
  high-priority overlay (bit 15 of the tile word). Characters come from 0x3e80..0x3fff (palettes 0x7d..0x7f,
  free on the select screen) and the overlay pages' free tails; the select screen's upload list and palette block
  are copied, extended and re-pointed from bank 0's free tail (+0xf3000).

## Evidence

- Identity: with the ten-entry directory holding the three originals, Big Forest and Bay Bridge produce the
  same collision-probe stream, sample for sample, as the unpatched set (45 s races).
- Each of the ten wheel bands selects its entry and loads its data (ten 30-s runs); the select screen shows the
  scrolled row with the cursor at the right slot (snapshots at both ends of the list).
- Alpine as entry 3: 2 994 units forward / 79 backward in 90 s, never off the collision surface, render rate
  28–29 / 57 frames; entry 0 still drives Big Forest identically in the same build.

## Findings worth keeping

- The directory's area is unused colour-table space: the colour allocator must stay out of it
  (`colours.RESERVED_CODE`).
- `0x50197c` is the per-course **entity spawn list**, not a HUD map; the minimap is drawn from the road lines.
  A converted course needs a spawn list (the host's): with an empty one the minimap entity is missing (the map
  draws huge) and the autopilot lost the hairpin.
- The game takes the paddle read around coin/START (frames 600–730 in autoplay) as the **steering centre**:
  a paddle held hard left from boot biased the whole race (the Alpine swap drive fell from 2 895 to 1 627 units
  forward). The course choice can also latch at the START press, and the filtered wheel value needs ~50 frames
  to travel, so autoplay holds the paddle from frame 735 (`VR_WHEEL_FROM`) — this was the "race start varies"
  mystery of Phases 5–6.
- The pit-entry "none" value is 0xfffe: the check also tries quad + 1, and the original's 0xffff + 1 is quad 0.

## Deviations added

See `docs/deviations.md`: host-bank backdrop, host's trackside entities, placeholder entries 4–9 until M5,
labels per slot, attract demo on entry 0, names in a small plain font, no pit lane.
