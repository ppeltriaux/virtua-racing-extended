# Phase 21 recon: select-screen pictures for the new courses

Design: `docs/superpowers/specs/2026-11-01-select-previews-design.md` (Pascal approved 1 Nov 2026).

## 1. The originals' panels

- Layer B (picture): Big Forest 311 distinct characters in palettes 102-104, Bay Bridge 258 in 105-107, Acropolis 288
  in 108-110 (characters 0x3300 + 0x180 x art, i.e. blocks 102 + 3 x art). The road, terrain and shading are all here.
- Layer A (overlay, pages 0x30-0x32 = blocks 96-100, palettes 96-101): the road outline, water, landmarks and the name.
- Name lettering (layer A, rows 150-163): white (240,240,240) 2-px strokes, (16,16,16) 1-px outline, letters 6 x 14
  (I: 2 wide), 1-px gaps. The three names give A B C D E F G I L O P R S T Y; the seven new names also need N M U V Z.

## 2. Character and palette memory on the select screen (MAME dump at frame 820, `spike/backdrop/tiledump.lua`)

- The boot's phase-0 list uploads characters into blocks 2-94 once; nothing reloads them. Off-limits.
- Every screen uploads into blocks 96-127 from bank 0's directory (`(pair list, palette block)` per screen). The select
  screen's list fills blocks 96-124 and palettes 96-124 (`0x900c00`, 0x1d0 halfwords).
- Visible tilemaps reference palettes 0, 4, 5, 8, 9, 79, 96 and 105-127 (with entries 4-6 shown).
- Free: blocks and palettes 125-127 (today's generated overlays live there and in the overlay pages' tails).

## 3. The START "highlight" (boot 0xfc27d6, 0x4c bytes to its rsr; no absolute references)

- By data index `36[R25]` (0, 1, 2): `0xfc36cb(i)` copies the chosen original's palettes, `0xfc3706(j)` the other two's,
  then `bsr 0xfc2880` (the cursor frame).
- Tables (u32 x 3, by data index): layer-A destinations `0xfc3741` (0x900c00 / c40 / c80, 0x20 halfwords = 2 palettes),
  layer-B destinations `0xfc3819` (0x900cc0 / d20 / d80, 0x30 halfwords = 3 palettes); chosen sources `0xfc374d` (A),
  `0xfc3825` (B); others' sources `0xfc3951` (A), `0xfc3a1d` (B).
- The chosen set equals the uploaded (normal) colours except 6 entries on Bay Bridge (indices 7, 8 of each palette).
  The others' set is **grey**: every colour becomes a grey level (Big Forest: (0,12,0) -> (10,10,10) ... (0,24,0) ->
  (22,22,22); (13,10,2) -> (10,10,10) ... (29,27,20) -> (22,22,22)); the orange frame colour (31,18,0) is kept.
- So at START the two courses not chosen turn grey and the chosen one keeps its colours.

## 4. The select routines today (`vrtools/arcade/select.py`)

- `band` turns the wheel into a band; on a change it stores `0x501942`/`0x501940` and calls `draw`.
- `draw` blits each slot's layer-A map (select record +8) to `SLOT_A[s]` and layer-B map (load record `panel_b`) to
  `SLOT_B[s]` through 0xff9436 (header `base, mode, rows, cols`; the blitter adds the base in 16 bits).
- Load records are 64 bytes and full (+0x3c is the last field).

## 5. Space

- Program-ROM reserve (`colours.RESERVED_CODE`, 0x78d70, 92 KB): 63 436 bytes used by the directory and routines, 30 772
  free. Bank 0's tail (`panel.BANK0_FREE`, 0xf3000): 53 248 bytes, all free in today's build.
- A picture: up to 320 characters (10 240 B), three palette sets of 48 halfwords, one 336-halfword map: about 11 KB.
  Seven: about 77 KB of the 83 KB free. The originals' pictures reuse their own data in bank 0 (characters at the
  select list's sources, palettes in the select palette block and the tables above).
