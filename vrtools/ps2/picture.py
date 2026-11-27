"""Pictures (`.tm2` on the disc, not TIM2 files): a 64-byte header (not decoded), pixels, the CLUT at the end.

8-bit pictures end with 256 RGBA entries in the PS2's CLUT order (in every 32 entries, entries 8-15 and 16-23 swap
places); 4-bit pictures end with 16 RGBA entries. Alpha is 0x80 for opaque. The width is not read from the header: the
callers know their pictures (course atlas 128 × 128, sky halves 256 × 256; docs/spike/2026-11-phase90-ps2-disc-recon.md §1.2).
"""

from __future__ import annotations

from vrtools.ps2 import Ps2ReadError

from dataclasses import dataclass

import numpy as np

HEADER = 64


class PictureError(Ps2ReadError):
    pass


@dataclass(frozen=True)
class Picture:
    pixels: np.ndarray          # (h, w) uint8 palette indices
    palette: np.ndarray         # (256 or 16, 4) uint8 RGBA, in index order

    def rgb(self) -> np.ndarray:
        """(h, w, 3) uint8."""
        return self.palette[self.pixels][:, :, :3]


def unswizzle_clut(clut: np.ndarray) -> np.ndarray:
    """A 256-entry CLUT in index order (entries 8-15 and 16-23 of every 32 swapped back)."""
    out = clut.copy()
    for b in range(0, len(clut), 32):
        out[b + 8:b + 16], out[b + 16:b + 24] = clut[b + 16:b + 24], clut[b + 8:b + 16]
    return out


def decode(data: bytes, width: int, bpp: int = 8) -> Picture:
    """The picture: `bpp` 8 (256-entry CLUT) or 4 (16-entry, low nibble first), rows of `width` pixels."""
    if bpp not in (4, 8):
        raise PictureError(f"bpp {bpp}")
    entries = 256 if bpp == 8 else 16
    pix_bytes = len(data) - HEADER - 4 * entries
    if pix_bytes <= 0 or (pix_bytes * 8 // bpp) % width:
        raise PictureError(f"{len(data)} bytes do not hold {bpp}-bit rows of {width}")
    raw = np.frombuffer(data, dtype=np.uint8, count=pix_bytes, offset=HEADER)
    if bpp == 4:
        px = np.empty(raw.size * 2, np.uint8)
        px[0::2], px[1::2] = raw & 15, raw >> 4
    else:
        px = raw
    clut = np.frombuffer(data, dtype=np.uint8, offset=len(data) - 4 * entries).reshape(entries, 4)
    if entries == 256:
        clut = unswizzle_clut(clut)
    return Picture(px.reshape(-1, width).copy(), clut.copy())
