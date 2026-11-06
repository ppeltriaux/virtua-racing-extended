"""The race-time backdrop of a course: a 360-degree tile panorama shown on the System 24 tile chip's layer 2 (Phase 18b,
`docs/spike/2026-11-phase18b-backdrop-recon.md` §2).

The course's graphics-upload directory (`course.gfx_directory`) holds ten window pointers:
- phase 0, the tile uploads: (src, dst) pairs ending with src = 0; a block at src is `u32 tiles` then `32 × tiles`
  bytes copied to character RAM at dst (`0x780000 + 32 × code`);
- phase 1, the palettes: entries `u32 dst, u32 colours` then the colours (xBGR555 halfwords), ending with dst = 0; the
  originals carry the backdrop's palettes at `0x900c00` (palette 96 on) and an empty entry at `0x901c00`;
- phases 2-9, the panorama: eight blocks, each `u16 0, u16 1, u32 rows, u32 32` then `rows × 32` tilemap entries.
  Side by side they make a 2048-pixel turn. A tile's palette is its code >> 7 (MAME `segas24_tile`).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

from vrtools.arcade.course import CourseEntry, _win, gfx_directory
from vrtools.arcade.romset import RomSet

CHAR_RAM = 0x780000
PALETTE_RAM = 0x900000
BACKDROP_PALETTE = 0x900c00          # palette 96: the first backdrop palette
EMPTY_PALETTE_ENTRY = 0x901c00       # the originals' second, empty phase-1 entry
GFX_MAGIC = struct.unpack("<I", b"VRBG")[0]   # opens an encoded image: the boot routine `gfx` (directory.py) takes a
                                               # course header's directory only when this word precedes it
BLOCKS = 8
BLOCK_COLUMNS = 32


@dataclass
class ArcadePanorama:
    tiles: dict[int, bytes]                       # code -> 32 bytes (4 bpp, as character RAM holds them)
    palettes: dict[int, tuple[int, ...]]          # palette number (96..) -> 16 xBGR555 words
    map: np.ndarray                               # uint16 (rows, 256): the eight blocks side by side
    uploads: list[tuple[int, bytes]] = field(default_factory=list)   # phase-0 uploads as (dst, data), in order


def _u32(rs: RomSet, e: CourseEntry, addr: int, what: str) -> int:
    return struct.unpack_from("<I", rs.data, _win(e.base, addr, what))[0]


def read_panorama(rs: RomSet, e: CourseEntry) -> ArcadePanorama:
    d = gfx_directory(rs, e)
    if len(d) < 2 + BLOCKS:
        raise ValueError(f"the graphics-upload directory has {len(d)} entries, not {2 + BLOCKS}")
    uploads, tiles = [], {}
    a = d[0]
    while (src := _u32(rs, e, a, "tile pair list")) != 0:
        dst = _u32(rs, e, a + 4, "tile pair list")
        n = _u32(rs, e, src, "tile block")
        off = _win(e.base, src + 4, "tile block")
        data = bytes(rs.data[off:off + 32 * n])
        uploads.append((dst, data))
        for k in range(n):
            tiles[(dst - CHAR_RAM) // 32 + k] = data[32 * k:32 * k + 32]
        a += 8
    palettes = {}
    a = d[1]
    while (dst := _u32(rs, e, a, "palette block")) != 0:
        n = _u32(rs, e, a + 4, "palette block")
        off = _win(e.base, a + 8, "palette block")
        colours = struct.unpack_from(f"<{n}H", rs.data, off)
        for k in range(0, n, 16):
            palettes[(dst - PALETTE_RAM) // 32 + k // 16] = tuple(colours[k:k + 16])
        a += 8 + 2 * n
    blocks = []
    for ptr in d[2:2 + BLOCKS]:
        off = _win(e.base, ptr, "panorama block")
        h0, h1, rows, cols = struct.unpack_from("<HHII", rs.data, off)
        if (h0, h1, cols) != (0, 1, BLOCK_COLUMNS):
            raise ValueError(f"panorama block {ptr:#x}: header {(h0, h1, rows, cols)}")
        blocks.append(np.frombuffer(rs.data, "<u2", rows * cols, off + 12).reshape(rows, cols))
    return ArcadePanorama(tiles, palettes, np.concatenate(blocks, axis=1).astype(np.uint16), uploads)


def encode_panorama(p: ArcadePanorama, window: int) -> tuple[bytes, int]:
    """A self-contained image for window address `window`: GFX_MAGIC, the directory (ten pointers), the tile pair list, the palette
    entries (the backdrop's palettes from 0x900c00, the empty 0x901c00 entry, the terminator), the tile blocks and the
    eight panorama blocks. Returns (image, the directory's window address)."""
    rows = p.map.shape[0]
    numbers = sorted(p.palettes)
    if numbers and numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise ValueError(f"palettes {numbers} are not consecutive")
    pal_dst = PALETTE_RAM + 32 * numbers[0] if numbers else BACKDROP_PALETTE
    colours = [c for n in numbers for c in p.palettes[n]]
    off_dir = 4
    off_pairs = off_dir + 4 * (2 + BLOCKS)
    off_pal = off_pairs + 8 * len(p.uploads) + 8
    off_tiles = off_pal + 8 + 2 * len(colours) + 8 + 8
    tile_offs, o = [], off_tiles
    for _, data in p.uploads:
        tile_offs.append(o)
        o += 4 + len(data)
    block_offs = [o + k * (12 + 2 * rows * BLOCK_COLUMNS) for k in range(BLOCKS)]
    end = block_offs[-1] + 12 + 2 * rows * BLOCK_COLUMNS
    out = bytearray(end)
    w = lambda off: window + off
    struct.pack_into("<I", out, 0, GFX_MAGIC)
    struct.pack_into(f"<{2 + BLOCKS}I", out, off_dir, w(off_pairs), w(off_pal), *(w(b) for b in block_offs))
    for k, (dst, _) in enumerate(p.uploads):
        struct.pack_into("<II", out, off_pairs + 8 * k, w(tile_offs[k]), dst)
    struct.pack_into("<II", out, off_pal, pal_dst, len(colours))
    struct.pack_into(f"<{len(colours)}H", out, off_pal + 8, *colours)
    q = off_pal + 8 + 2 * len(colours)
    struct.pack_into("<II", out, q, EMPTY_PALETTE_ENTRY, 0)            # as the originals have it; then the terminator (0)
    for (dst, data), t in zip(p.uploads, tile_offs):
        struct.pack_into("<I", out, t, len(data) // 32)
        out[t + 4:t + 4 + len(data)] = data
    for k, b in enumerate(block_offs):
        struct.pack_into("<HHII", out, b, 0, 1, rows, BLOCK_COLUMNS)
        block = np.ascontiguousarray(p.map[:, k * BLOCK_COLUMNS:(k + 1) * BLOCK_COLUMNS]).astype("<u2")
        out[b + 12:b + 12 + block.nbytes] = block.tobytes()
    return bytes(out), w(off_dir)
