# Saturn Virtua Racing — backdrop files (`BGS*`, `BGM*`)

Status: decoded (Phase 18b, 2026-11-01). Decoders: `vrtools.saturn.backdrop` (`decode_bgs`, `map_cells`).

## `BGM*` — cell map

10,240 bytes = 64 × 80 big-endian u16. Each value is a 13-bit cell id (12-bit id
plus one extension bit in the high nibble) below 5120. The `…1`/`…3` variants use
every cell exactly once (a permutation of 0..5119); the `…2`/`…4` variants reuse
cells (739–2,241 distinct) and have correspondingly smaller `BGS*` files. Two or
four variants per course; Speedway has none.

## `BGS*` — cell data (decoded, Phase 18b)

| offset | content |
|---|---|
| 0 | u32 `0x00238008` on all 24 files (load address of the data block) |
| 4 | u32 end address: the data is `end − 0x238008` bytes from offset 8 |
| 8 | LZSS data (below) |
| file end − 512 | the palette: 256 big-endian RGB555 colours (VDP2 CRAM bank 0) |

LZSS: flag bytes read LSB first; 1 = one literal byte; 0 = two bytes `b0 b1` copying `(b0 & 0x0F) + 2` bytes from
position `(b0 & 0xF0) << 4 | b1` of a 4096-byte ring, zero-filled, whose write index starts at 1. The `…1` files decode
to 5 120 cells × 64 bytes (8 bpp) = four 320×256 quarters 40 cells wide, side by side a seamless 1280×256 panorama
(verified byte for byte against VDP2 VRAM in race states: `docs/spike/2026-11-phase18b-backdrop-recon.md`). Speedway
uses Surfers Paradise's `BGSSURF1`. (Phase 3 had taken the first 512 bytes of the data for a palette: they are the
start of the LZSS stream.)
