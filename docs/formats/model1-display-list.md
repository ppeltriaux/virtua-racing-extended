# Model 1 display list (V60 → TGP/renderer)

Derived from MAME `src/mame/sega/model1_v.cpp` (`tgp_render`, `skip_direct`),
BSD-3-Clause, copyright Olivier Galibert. Walker: `vrtools.arcade.dlist`.

## Where it lives

- Two 64 KB lists in V60 space: list 0 at `0x600000`, list 1 at `0x610000`
  (double buffered). Entries are 16-bit; offsets below are in entries and
  wrap at `0x8000`.
- List control register at `0x680000` (16-bit): bit `0x40` set → list 1 is
  the one being rendered, clear → list 0.
- `readi(a)` = `e[a] | e[a+1] << 16`; floats are IEEE single via `readi`.
  **Command types and most arguments occupy two entries (32-bit).**

## Commands

| type | size (entries) | arguments (entry offsets) |
|---|---|---|
| 0x00 | 2 | no-op |
| 0x01 | 8 | object below HUD: `tex_adr` +2, `poly_adr` +4, `size` +6 |
| 0x41 | 8 | object above HUD (radar etc.), same layout |
| 0x02 | variable | direct screen-space polys: header 18, then records: `flags` at record +2, type 0 ends, type 2 = 12 entries, else 20; then +4 |
| 0x03 | 16 | viewport: int16 at +4 `xc`, +6 `yc`, +8 `x1`, +10 `y2`, +12 `x2`, +14 `y1` |
| 0x04 | 6 + 2·(len+1) | `adr` +2, `len` +4; writes `len+1` **16-bit** values (low half of each 2-entry slot from +6) to TGP RAM (colour/texture table) at `adr − 0x40000` |
| 0x05 | 6 + 2·len | `adr` +2, `len` +4; writes `len` 32-bit words from +6 to polygon RAM at `adr − 0x800000` |
| 0x06 | 6 + 2·len | `adr` +2, `len` +4; `len` 32-bit light parameter words (diffuse, ambient, specular, power bytes) |
| 0x07 | 4 | mode word (bit 0 = specular enable) |
| 0x08 | 4 | select mode |
| 0x09 | 6 | zoom x, y (floats, ×4 inside MAME) |
| 0x0a | 8 | light vector (3 floats) |
| 0x0b | 26 | 3×4 matrix: 12 floats at +2, +4, … +24 |
| 0x0c | 6 | view translation x, y |
| 0x0f | — | end of list; any other value also ends the list |

## Matrix (0x0b)

`x' = m0·x + m3·y + m6·z + m9`, `y' = m1·x + m4·y + m7·z + m10`,
`z' = m2·x + m5·y + m8·z + m11`. Column-major 3×3 plus translation; the
transform takes object space into view (camera) space, so world placement
of an object must be recovered from the camera pose.

## Logging in MAME

`vrtools/mame/lua/dlist_log.lua` dumps the active list as one line per
sampled frame (`F <frame> <base_hex> <hex>`); `dlist.parse_log` replays it
through `walk`.
