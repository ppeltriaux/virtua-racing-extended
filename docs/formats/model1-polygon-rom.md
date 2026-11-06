# Model 1 polygon ROM — object format

Derived from MAME `src/mame/sega/model1_v.cpp` (`push_object`), BSD-3-Clause,
copyright Olivier Galibert. Implemented in `vrtools.arcade.polyrom`.

## Addressing

- Display-list command `0x01` carries `tex_adr`, `poly_adr`, `size`.
- `poly_adr` is an index of **32-bit words**. Bit `0x800000` set means the
  object lives in polygon RAM (uploaded by command `0x05`); clear means the
  16 MB polygon ROM (`RomSet.polygons`).
- `size` = maximum number of records; `0` = unlimited (stop at end marker).

## Layout

| Words | Content |
|---|---|
| 0–5 | seed points `p0 (x,y,z)`, `p1 (x,y,z)` as IEEE floats |
| then, per record (10 words) | `flags` (u32), normal `nx ny nz`, `p0 x y z`, `p1 x y z` (floats) |

Parsing stops at the first record with `flags & 3 == 0`.

## Flags

| Bits | Meaning |
|---|---|
| 0–1 | type: 0 = end, 2 = point (`p1 := p0`), 1/3 = normal |
| 8–9 | link mode (see below) |
| 10–11 | z mode: 0 keep old z, 1 min of the four, 2 max, 3 zero. The originals' ground polygons use 2 and the cars 1; the converter writes 2 on every quad (`polyrom.Z_MODE_MAX`), since mode 0 sorted our ground in front of the car (Phase 14) |
| 12 | advance `tex_adr` by one before this record is drawn |
| 13 | moiré (stipple) |
| 14 | skip back-face test |
| 17–20 | light mode |
| 22 | second light bank (adds 0x80 to light mode) |

## Link modes (quad strip)

Each record with link ≠ 0 emits the quad `(old_p1, old_p0, p0, p1)`, then
the "old" points update:

| link | quad | update |
|---|---|---|
| 0 | none | `old_p0, old_p1 = p0, p1` |
| 1 | yes | `old_p1 = p0` |
| 2 | yes | `old_p0, old_p1 = p0, p1` |
| 3 | yes | `old_p0 = p1` |

## Colour

No colour in the record. `tex_adr` indexes TGP RAM (written by command
`0x04`); palette index = `0x1000 | (word & 0x3ff)`; bit 10 of the word
forces full brightness. Lighting is flat per quad from the record normal.
