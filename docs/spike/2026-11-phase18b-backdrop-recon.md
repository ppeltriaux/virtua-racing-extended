# Phase 18b recon: the Saturn backdrops on the arcade (1 Nov 2026)

Pascal (Phase 18): convert each course's own sky backdrop in this phase. Today a converted course shows its host
bank's (Alpine Big Forest's, Amazon/Pacific/Oval/Surfers Road Bay Bridge's, Diablo/Metropolis Acropolis's). Tools:
`spike/saturn/` (Mednafen states), `spike/backdrop/tiledump.lua` (MAME tile RAM dumps); probes in `out/p18b/`.

## 1. The Saturn backdrop: decoded from the disc

`BGS*1` (`docs/formats/saturn-backdrop.md`): u32 load address `0x00238008`, u32 end address, then LZSS data of
`end − 0x238008` bytes, then the palette (the file's last 512 bytes: 256 big-endian RGB555 colours = CRAM bank 0,
256/256 equal on Pacific Coast). The LZSS: flag bytes read LSB first, 1 = a literal byte, 0 = a two-byte reference
`b0 b1` copying `(b0 & 0x0F) + 2` bytes from ring position `(b0 & 0xF0) << 4 | b1` of a zero-filled 4096-byte ring
whose write index starts at 1 (Okumura's LZSS with the length and position nibbles in the first byte). Output: 5 120
cells × 64 bytes, 8 bpp, laid out as four 320×256 quarters 40 cells wide: one seamless 1280×256 panorama.

Checked byte for byte against VDP2 VRAM in Mednafen race states (NBG0, 8 bpp cells, 2-word pattern names at
`0x5C000`): Alpine, Amazon Falls, Diablo Canyon, Metropolis, Pacific Coast, Surfers Road identical; the Surfers Oval has
no file and shows `BGSSURF1` (identical). The `…2` variants and the originals' (Big Forest, Bay Bridge, Acropolis race
with another variant) are not needed. SHA-1s of the decoded images are pinned for the tests (§5).

At the grid every course's plane shows panorama columns 0-319 (pattern names 1-40 per row); how the Saturn ties the
column to the heading is to be measured with a state after a turn (plan).

## 2. The arcade backdrop

Model 1's 2D layers are the System 24 tile chip (MAME `segas24_tile`): four 64×64 tilemaps of 8×8 4 bpp characters
(32 bytes, a 16-colour palette per tile, `(entry >> 7) & 0xff`), tile RAM `0x700000` (layer n at word `0x1000·n`,
scroll words at `0x5000`), character RAM `0x780000-0x7fffff`. In a race (dumps at frames 2200/3000/3800 on the three
originals): layers 0-1 the HUD, layer 3 flat sky/ground colours, **layer 2 the backdrop**: rows 6.. of a 512-pixel ring
the game streams columns into as the car turns (boot ROM `0xffe540`: per row it copies `R19` entries from a source
block at column `R1` to the ring at column `R2`, source stride 32 entries), horizontal scroll word `0x5002` (0-0x1ff),
vertical `0x5006` (a few pixels with the pitch, line-scroll mode `0x2000`).

The source is in the course's data bank, reached through the graphics-upload directory (`course.gfx_directory`):
phase 0 the character uploads (pair list to `0x7e0000`+: tile codes `0x3000-0x3fff`), phase 1 the palette block
(`0x900c00`), **phases 2-9 the panorama**: eight blocks, each a 12-byte header (`u16 0, u16 1, u32 rows, u32 32`) and
`rows × 32` tilemap entries (code | palette << 7). Eight blocks of 32 columns: a 2048-pixel 360° panorama; Big Forest
20 rows (160 px), Acropolis 23 (184 px); 2 382 / 2 564 distinct tiles, 20 / 21 palettes (`out/p18b/arcade_panos.png`).

## 3. What the conversion needs

- Horizontal: the Saturn's 1280 px per turn against the arcade's 2048 (×1.6; both show ~90° across the screen).
- Vertical: the arcade band is 20-23 rows; the Saturn's 256 px (×1.6 = 410) is cropped to the band around its horizon.
- Colour: 8 bpp, one 256-colour palette → 4 bpp tiles, each picking one of ~20-32 sixteen-colour palettes.
- Size: ≤ 4 096 tile codes (`0x3000-0x3fff`); the data banks have 450 KB (bank 1, four courses), 541 KB (bank 2, two),
  631 KB (bank 3, one) free after Phase 18a: ~2 500 tiles (80 KB) + map (13 KB) + palette per course fits.
- Alignment: the panorama column the arcade shows at a heading (measured with a marked test panorama in MAME) against
  the Saturn's (a state after a turn), with the course placement's rotation in between.
- Wiring: the converted blob's header points `gfx_dir` at the template's directory today; a converted course gets its
  own directory (tiles, palette, eight blocks) in its bank's free space.

## 4. Render cost

The backdrop is a tile layer: no polygons, no TGP. The render rate is not at stake.

## 5. Pinned digests (decoded image, palette)

| Course | File | Image SHA-1 | Palette SHA-1 |
|---|---|---|---|
| Alpine | `ALPINE00/BGSALPN1` | 5e03eb42332e18e5bcf70a5325b815ed60bfd053 | b8593f834ef694cef695cc97a895897c2908b157 |
| Amazon Falls | `AMAZON00/BGSAMAZ1` | f0300d05f7f1f69809abbc56d3cea545b96b2af2 | fd2a2871b336c0d4a87256f529f4749b5391c3eb |
| Diablo Canyon | `DIABLO00/BGSDIAB1` | 14d582d9b5e7d78da3bba3ae25861a7984650fc5 | c0792d82af4c6f99473e4647ba815f85bef73d06 |
| Metropolis | `METROPOL/BGSMETR1` | 10c890adcbb14d772b31668b78135a17fa937816 | fb53e62a7e19e36380ec6575eb64b8e3e5f1dee3 |
| Pacific Coast | `PACCOAST/BGSPACC1` | 5ae342f4b2898cc347b2fcf3a90d27f3212890cd | 5de0167be3ff83f686030431476e487941f536d0 |
| Surfers Oval, Surfers Road | `SURFER00/BGSSURF1` | e2f049d72da722efff3520706329c3989f4cb779 | 2600cb0ad4c0e85faacbfe18951c5738d75665c6 |

## 6. Outcome (Phase 18b, `docs/superpowers/plans/2026-11-01-phase18b-backdrops.md`)

- `saturn.backdrop.decode_bgs` decodes every converted course's backdrop from the disc (digests §5); `arcade.backdrop`
  reads and writes the arcade's (the three originals round-trip); `convert.backdrop.convert_panorama` resamples
  (×1.6 across, 2048 px per turn; ×1.46 down from Saturn row 15, so its picture top meets the band's top and its horizon
  the arcade's) and quantises: 32 palettes (codes 0x3000-0x3fff are all the backdrop's: the originals' uploads there
  are their own band tiles), ≤ 2 600 tiles, 72-87 KB per course. Layer 3 above and below the band is filled from the
  panorama's entries [0][0] and [rows-1][0] (boot 0xffe034): the converter puts its two solid reserved tiles there.
- The game read every bank's backdrop directory from the header at window 0x100000. Both readers (0xffe007, the
  course-load uploads; 0xffe49e, the per-frame streaming, also at the title in bank 0) now call a boot routine `gfx`:
  the current entry's header's directory when the encoded image's GFX_MAGIC precedes it, else 0x100000's as before. A
  loader-written RAM copy did not work: the course-load upload runs before the loader in the same frame.
- Heading: the arcade shows source pixel heading/32 at the screen's left edge, the Saturn panorama column 0 at its
  start direction (slice 0); a right turn grows both (Saturn: SCXIN0 7887 ≡ 207 after a 5 s right turn). The column
  offset per course is the arcade heading of the Saturn start direction / 32 − 8.
- Drive suite 46 passed; captures `out/p18b/media`, comparison sheets `out/p18b/compare`, start-line check
  `out/p18b/facing.png` (Alpine and Pacific Coast as the Saturn's grid shows them).
