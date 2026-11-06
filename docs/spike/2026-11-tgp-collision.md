# Spike log: TGP collision data (Nov 2026, recon for Phase 5 / M1b)

How the arcade's MB86233 "TGP" answers the V60's road-height queries, where
the per-course geometry lives in the TGP data ROMs (`copro_data`), and what a
new course must supply. Everything below was measured on the Big Forest race in
MAME 0.289 with Lua taps on the TGP's I/O space and the V60's copro ports, plus
the `unidasm -arch mb86233` listing of the 2,048-word TGP program (315-5573).

## How the TGP reads its data ROM

MAME `model1_m.cpp`: the TGP's I/O space maps 0x8000–0xffff to
`copro_data[(base & ~0x7fff) | offset]` where `base` is written at I/O 0x2e.
So the data ROM is addressed in 32-bit **words** (0x80000 of them in the 2 MB
region); the TGP sets the full word address as the base and reads through the
window. A Lua read tap on `tgp_copro.spaces["io"]` 0x8000–0xffff, combined
with a write tap on 0x2e, gives absolute word addresses.

## The collision call

Per logic frame (the game runs logic every other video frame) the V60 routine
at `0xfed52b` sends, for the player and the opponents, on the FIFO
(V60 0xd80010/0xd80012 = low/high halves):

```
0x1b010000   command: dispatch index 0x1b00 >> 7 = 54 -> handler 0x482 (flag bit 0 = 1)
y            f32 car height (e.g. 29.99)
id           collision-map halfword at the car's 16x16-unit cell (e.g. 0x1587)
x, z         f32 car position
```

then polls TGP RAM word 0 (V60 I/O-space reads at 0xd20000 after writing
0xd00000 = 0) until it is no longer 0xffffffff, sets the RAM address to 0x8001
(auto-increment) and reads **word 1 = height y at (x, z)** and **word 2 = index of
the quad hit** (e.g. 0x2b). The quad index then feeds commands 0x1500 (with
x, z) and 0x1800 (handlers 0x34b / 0x431), which read the same quad record.

TGP handler (0x489–0x4d5): `list = $0x69 + id`; `count = ROM[list]`; for each
index `i` in `ROM[list+1 ..]`: `quad = $0x6a + 16*i`, copy 16 words, run the
convex point-in-polygon test ($0x35 → 0x693: sign of the cross product on each
edge, `brif !ged`), and on a hit record the index and the interpolated height.
`$0x69` and `$0x6a` are the course's **list block** and **quad pool** word
addresses.

## Course slots

Subroutine 0x7e2 (reached from command 0x0680, dispatch index 13) loads
`$0x69 = ROM[0x10 + n]` and `$0x6a = ROM[0x20 + n]` for slot `n`. The V60
sends `0x06800000, n` from its course-load routine `0xfe48ed`, with **n = the
course data index at RAM 0x501934** (Big Forest 2, Bay Bridge 0, Acropolis 1).
That routine also fills the per-course RAM pointers from tables indexed by the
same n (boot ROM `0xfcd5b9`, `0xfcf16d`, `0xfe49a4` → tile table pointer at
`0x501948`, `0xfda543`) and the bank header words 0x100004/8/c/10 — the course
table work of M4 starts there.

Data ROM words 0x0–0xf hold a 4×4 identity matrix (TGP constants); words
0x10–0x1f the 16 slot list blocks and 0x20–0x2f the 16 slot quad pools:

| slot | course | list block (words) | lists | quad pool (words) | quads |
|---|---|---|---|---|---|
| 0 | Bay Bridge (1) | 0x30–0x3fa1 | 1,587 | 0x12e00–0x28a90 | 5,577 |
| 1 | Acropolis (2) | 0x8000–0xb547 | 1,277 | 0x28a90–0x3c170 | 4,974 |
| 2 | Big Forest (0) | 0x10000–0x12dfb | 1,368 | 0x3c170–0x4b170 | 3,840 |
| 3–15 | unused | 0x30 (= slot 0) | | 0x12e00 (= slot 0) | |

Filler: zeros in 0x3fa1–0x8000 and 0xb547–0x10000, `0xcdcdcdcd` in
0x12dfb–0x12e00, `0xffffffff` from 0x4b170 to the end (0x80000). Free:
216,720 words (846 KB) of 0xff plus 35,608 words (139 KB) of zero gaps.

## Lists and quads

- **Collision map** (V60 data bank, 128×128 halfwords, Phase 2): the value is
  the **word offset of the cell's list inside the course's list block**. Lists
  are `count:u32, index:u32[count]`, stored consecutively in id order; every
  list is referenced by exactly one map cell (verified: the walk from the first
  id hits all 1,368 / 1,587 / 1,277 ids and ends at the last list). Mean 7.6–9.7
  quads per list, max 45.
- **Quad record**, 16 words: four corners `(x, y, z)` f32 in arcade world units,
  then the centre `(x, y, z)` (equal to the mean of the corners within 0.05 for
  98.5 % of quads) and an attribute word: a sign-extended 16-bit value, 0 on
  629 / 743 / 422 quads per course, otherwise 1,500–2,500 distinct values whose
  meaning is still unknown (not a heading, not sin/cos of the road direction,
  not a normal component; candidates: surface/rumble flags). All quads have
  negative signed area in XZ (same winding throughout). Typical size: 3–4 units
  across, 8–11 along the road (p90 18–20). Big Forest's road sits at y 29–46,
  Bay Bridge 0–40, Acropolis −1–22.
- Quad centres lie inside the referencing 16-unit cell (with a 24-unit margin)
  for 1,567 / 1,570, 2,089 / 2,089 and 1,830 / 1,830 sampled references, which
  is how the pools were assigned to courses.
- The **surface table** (bank +0x14f98) is 256 bytes of value 1 on all three
  courses.

## Budget for seven new courses

Big Forest's arcade data is 73,211 words (286 KB); seven courses at that
density would need 2 MB, more than the whole ROM. The Saturn side is coarser:
a Saturn road slice is one plane-bounded polygon about 2.5 × 1.0 Saturn units
(29 × 12 arcade units) and Big Forest has 431 of them (Alpine 528, Amazon 464),
so one quad per slice plus the cell lists is roughly 10,000 words (40 KB) per
course, 300 KB for seven: fits the 846 KB of 0xff space with room for finer
subdivision. Saturn segments carry no height (word 18 is 0 on every segment of
every course); the surface normal is there (y from −1 to 1 on Alpine), so the
road height must come from the Saturn ground mesh under each slice, or from
integrating the slope along the lap once the slices are ordered.

## Tooling notes

- TGP I/O taps: `tgp_copro.spaces["io"]:install_read_tap(0x8000, 0xffff, ...)`
  and `install_write_tap(0x2e, 0x2e, ...)`; `tgp.state["GENPC"]` is the TGP PC.
- The V60 reads the copro ports through its **I/O space** (`in` instructions):
  tap `maincpu.spaces["io"]` as well as `"program"` or the result reads are
  invisible.
- Instruction traces: `-debug -debugger none` plus
  `manager.machine.debugger:command("trace file,maincpu,noloop")` from Lua at a
  chosen frame; 2 frames of V60 are ~70k lines.
