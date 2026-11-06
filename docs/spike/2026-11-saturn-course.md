# Discovery log: Saturn course decode (Phase 3 / M2)

Working notes; confirmed facts are in `docs/formats/saturn-trck.md`. Outputs under
`out/p3/` (not committed).

## Segments (section 4) — 2026-10-30

- 76-byte records = 19 big-endian 16.16 words: 4 planes `(nx, nz, d)`, a surface
  normal, three angle words (1/2³² turn: word 16 ≈ banking about Z, word 17 ≈ slope
  about X; e.g. −11,891,315 → −0.997° where the normal's z is −0.017), word 18 = 0.
- Slices are convex 3- or 4-gons (an all-zero plane = absent); corner-based centre
  works for 98 %+ of records on all ten files; Big Forest quads: width median 2.4
  (69 % within 2.3–2.7; pit lane and run-off are wider/narrower), length ≈ 1.0.
- Records are not in lap order.

## Grid (sections 5–9)

- Sections 5–8 = `-xmax, -zmax, 16/(xmax-xmin), 16/(zmax-zmin)` (exact match with the
  segment polygon bounds on all ten files; Surfers' z reciprocal differs: it shares
  Speedway's grid parameters).
- Cell = `zc*16 + xc` counted from the (xmax, zmax) corner; a segment is listed in
  every cell its polygon overlaps (99.7–100 % of 8,000 list entries verified).
- Sections 11–14 hold a second set of four parameters (slightly padded bounds); use TBD.

## Objects and placements

- Object = vertices (count + 16.16 triples), normals (count + triples), faces (count +
  14-byte records: RGB555 colour, attr_a 0..11, attr_b mostly 1|6, four vertex ids).
  Validated on 1,415 objects / 64,268 faces (every vertex id in range). attr_b is not a
  normal index. LZ/VDP1 command hypotheses were not needed.
- Placement entry (56 B): flags, mesh index (signed i16, high half of word 1), yaw
  (1/2³² turn), x/y/z, bounding radius. Groups 0–3: 16-unit tile lattices (four
  variants of the ground tiles; Big Forest 4 × 9 = 36 slots, 25/31/25/30 meshes);
  group 4: props.

## SH-2

- `VRCODELO` loads at `0x06010000` (IP jump table constants `0x06010034`, `0x06010208`,
  …). Its literal pool at `0x06027500` holds `0x06096000`, stored into a global by the
  code at `0x060274c4` (track-data pointer). Stride confirmation from code: deferred,
  the data-driven checks across ten files stand in.

## Comparison with the arcade

See `docs/spike/2026-11-big-forest-comparison.md`: scale 11.7, 180° rotation, no
translation, rms residual 8–13 arcade units on the three shared courses.

## Backdrop (BGS/BGM) — header and map only

- BGM: 5,120 u16 entries (64 × 80 cells) of 13-bit cell ids; the `…1/…3` variants use
  every cell once, the `…2/…4` variants reuse cells.
- BGS header: word 0 = `0x00238008` (load address), word 1 = base + compressed data
  length; between them and the data sits a 512- or 1024-byte palette block (all 24
  files). The `…2/…4` map variants reuse cells (739–2,241 distinct), the `…1/…3` ones use
  all 5,120 once.
- The cell data is compressed (21–71 bytes per distinct cell); plain LZSS variants (12-bit
  offset / 4-bit length, either flag polarity / bit order / endianness) do not produce
  163,840 (4 bpp) or 327,680 (8 bpp) bytes. Left open: the SH-2 decompressor in
  `VRCODELO` is the oracle.
