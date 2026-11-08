# Model 1 Virtua Racing — the attract logo (V.R. / Virtua / Racing)

Recon 9 Nov 2026 (MAME 0.289, tile/character/palette RAM dumps at the logo frames, attract frames ~2080–2260 and
~3800–3980 after boot). Used by `vrtools/arcade/title.py`.

- **What it is.** Two 2D tile maps, not polygons: the blue screen with the white "V.R." and the red "Virtua" /
  "Racing" (black drop shadow) shown twice per attract loop. The upper half slides in from above on tile layer 1,
  the lower half from below on layer 0; the 3D scene keeps running behind them. The black "V.R." screen that comes
  earlier in the loop is separate and does not use these maps.
- **Maps** (program ROM, map header `base:u16, mode:u16, rows:u32, cols:u32`, then the halfwords; mode 1, base
  0x8000, the same format the select panels use): upper `0x2f6b18`, 21 × 62 tiles; lower `0x2f7550`, 27 × 62, drawn
  from tile row 21 (y 168). Their pointers sit in the boot ROM at `0xfc1910` and `0xfc1924`. The lower map's rows 12–26
  under the V.R. (y 264–383) are plain blue (character 0x1f00).
- **Characters.** 0x1f00–0x2053 (upper 166, lower 197 distinct), loaded once at boot by bank 0's first upload list
  (directory word 0 → entry `+0x20` = (pair list `0x100028`, palette block `0x107c80`)); the pair `0x132a88 →
  0x7be000` loads 565 characters to 0x1f00. 0x2054–0x2134 are the HUD's yellow lettering (CREDIT, INSERT COIN(S),
  © SEGA 1992). **0x2135–0x217f (75 characters, the tail of block 66) are loaded by nothing.**
- **Colours.** A tile's palette is its character >> 7: palettes 0x3e–0x42 on the logo screen are
  `0 green, 1 white, 2 black, 3 red (248,0,0), 4 blue (0,0,248), 5 black, 6–7 yellow, 8 olive, 9–15 white`. The logo
  uses 4 (blue), 3 (red), 1 (white) and 2 (black, the shadow).
- **Lettering.** "Racing" is a hard-edged bold sans, red, with its shadow 3 px right and 2–3 px down, red pixels x
  202–428, y 175–245 (cap height ~57 px); "Virtua" x 68–262, y 106–164.
- **The boot list cannot grow in place.** Its terminator (`src = 0`) at bank 0 `+0x170` is followed directly by
  another upload's source (`0x100174`: count 0x80, then 128 characters, loaded to 0x100 and 0x180).

## What title.py does

"Extended" in bold italic (26 × 162 px, red with a 2 px black shadow, about half Racing's height), right-aligned
with "Racing" at x 268–429, y 268–293: 65 distinct non-blue tiles in characters 0x2135.., written into the lower
map's blue rows 33–36 (map rows 12–15). The characters go to a free bank-0 run behind their count word. A copy of the boot pair list with one more pair
(→ `0x7c26a0`) goes to bank 0's free space and directory entry `+0x20` points at it; the original list is left as it
was. MAME check: `tests/test_title.py::test_the_attract_logo_says_extended`.
