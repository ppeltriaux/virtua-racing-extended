# Model 1 Virtua Racing — colour pipeline

Phase 4, 2026-10-30. Decoders: `vrtools.arcade.colours`.

1. Every polygon-ROM record carries a **texture address** (`tex_adr`), advanced by
   one when a record has flag 0x1000; the object command gives the start.
2. `tex_adr` indexes the **TGP colour table**, which the boot code uploads with
   display-list command 0x04 in 128 chunks of 4,096 entries (frames 14–268) to
   table indices 0x40000–0xbffff. The table is the **1 MB program ROM
   (epr-14882/14883) copied verbatim**: entry *i* is the little-endian u16 at
   ROM byte `2 * (i − 0x40000)` (verified on all 524,288 entries). The V60
   code lives in the boot ROM; this "program" ROM is colour table plus the
   tile/course tables above 0x2e0000.
3. A table word selects palette index `0x1000 | (word & 0x3ff)`; bit 0x400 means
   full brightness (no lighting).
4. Palette RAM (V60 `0x900000`, 2 bytes per entry) holds xBGR555:
   `0x8000 | b<<10 | g<<5 | r` (5 bits each). The polygon palette is entries
   0x1000–0x13ff (1,024 colours; Big Forest uses 541 distinct). Its source for
   Big Forest is program ROM `0x2ec980` (0x800 bytes, 1,794 bytes match the
   race-time RAM exactly; the rest is modified at runtime). Other courses' palettes
   are expected nearby (TBD).
5. Free colour-table entries (0xFFFF runs below the tile-record area):
   `0x7c6b8` (47,432 entries, ROM 0x78d70) and `0x98c21` (29,663, ROM 0xb1842).
   Big Forest's own tiles use entries 0x45802–0x8e0ba.

Converter rule: sort an object's quads by palette index, write one table entry per
colour change and set the advance flag on the first record of each new colour.
