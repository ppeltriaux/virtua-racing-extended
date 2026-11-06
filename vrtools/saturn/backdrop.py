"""Saturn backdrop files BGS* (cell data, LZSS) and BGM* (64x80 cell map).

A BGS*1 file decodes to the course's 360-degree panorama, 1280x256 at 8 bpp, with its 256-colour palette at the end of
the file (Phase 18b; docs/formats/saturn-backdrop.md).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

BASE_CONST = 0x00238008      # first header word on every BGS file (load address of the cell data)
HEADER_SIZE = 8
PALETTE_SIZES = (512, 1024)  # 256 or 512 RGB555 entries after the cell data, at the end of the file
MAP_WIDTH, MAP_HEIGHT = 64, 80


class BackdropError(Exception):
    pass


@dataclass(frozen=True)
class BackdropHeader:
    base: int                # word 0: load address of the cell data
    end: int                 # word 1: base + compressed cell-data length
    palette_size: int        # bytes after the cell data, at the end of the file (512 or 1024)
    data_size: int           # compressed cell-data bytes

    @property
    def data_offset(self) -> int:
        return HEADER_SIZE


def parse_header(bgs: bytes) -> BackdropHeader:
    if len(bgs) < HEADER_SIZE + min(PALETTE_SIZES):
        raise BackdropError(f"BGS too short ({len(bgs)} bytes)")
    base, end = struct.unpack_from(">2I", bgs, 0)
    data_size = end - base
    palette = len(bgs) - HEADER_SIZE - data_size
    if palette not in PALETTE_SIZES:
        raise BackdropError(f"BGS header end {end:#x} does not match the file size {len(bgs)} (base {base:#x}, implied palette {palette})")
    return BackdropHeader(base, end, palette, data_size)


def map_cells(bgm: bytes) -> list[int]:
    """Cell ids (13-bit: 12-bit id plus the extension nibble) in map order, each < 5120."""
    if len(bgm) != 2 * MAP_WIDTH * MAP_HEIGHT:
        raise BackdropError(f"BGM must be {2 * MAP_WIDTH * MAP_HEIGHT} bytes, got {len(bgm)}")
    return [v & 0x1FFF for v in struct.unpack(f">{MAP_WIDTH * MAP_HEIGHT}H", bgm)]


RING = 4096
CELLS = 5120                    # 8x8 cells of 64 bytes (8 bpp): four 320x256 quarters, 40 cells wide
PANORAMA = (256, 1280)          # rows, columns: the quarters side by side

# The backdrop each converted course shows (recon §5): the Surfers Oval has no file of its own and shows Surfers
# Paradise's.
BGS_OF_COURSE = {"ALPINE": "ALPINE00/BGSALPN1", "AMAZON FALLS": "AMAZON00/BGSAMAZ1", "DIABLO CANYON": "DIABLO00/BGSDIAB1",
                 "METROPOLIS": "METROPOL/BGSMETR1", "PACIFIC COAST": "PACCOAST/BGSPACC1", "SURFERS OVAL": "SURFER00/BGSSURF1",
                 "SURFERS ROAD": "SURFER00/BGSSURF1"}


def decode_lzss(data: bytes, out_len: int) -> bytes:
    """Flag bytes read LSB first: 1 = one literal byte; 0 = two bytes b0 b1 copying (b0 & 0x0F) + 2 bytes from ring
    position (b0 & 0xF0) << 4 | b1 of a zero-filled 4096-byte ring whose write index starts at 1."""
    ring = bytearray(RING)
    r, i, out = 1, 0, bytearray()
    while len(out) < out_len and i < len(data):
        flags = data[i]
        i += 1
        for k in range(8):
            if len(out) >= out_len or i >= len(data):
                break
            if (flags >> k) & 1:
                c = data[i]
                i += 1
                out.append(c)
                ring[r] = c
                r = (r + 1) & (RING - 1)
            else:
                b0, b1 = data[i], data[i + 1]
                i += 2
                pos = (b0 & 0xF0) << 4 | b1
                for j in range((b0 & 0x0F) + 2):
                    c = ring[(pos + j) & (RING - 1)]
                    out.append(c)
                    ring[r] = c
                    r = (r + 1) & (RING - 1)
    if len(out) < out_len:
        raise BackdropError(f"LZSS data ran out after {len(out)} of {out_len} bytes")
    return bytes(out)


@dataclass(frozen=True)
class SaturnPanorama:
    pixels: np.ndarray              # uint8 (256, 1280): palette indices
    palette: tuple[int, ...]        # 256 RGB555 words (bit 15 ignored)


def decode_bgs(bgs: bytes) -> SaturnPanorama:
    """The course's panorama: the LZSS cell data (four 320x256 quarters of 40x32 cells) side by side, and the palette
    (the file's last 512 bytes, big-endian RGB555 = VDP2 CRAM bank 0)."""
    h = parse_header(bgs)
    cells = np.frombuffer(decode_lzss(bgs[h.data_offset:h.data_offset + h.data_size], CELLS * 64), np.uint8)
    quarters = cells.reshape(128, 40, 8, 8).transpose(0, 2, 1, 3).reshape(1024, 320)
    pixels = np.concatenate([quarters[256 * q:256 * (q + 1)] for q in range(4)], axis=1)
    return SaturnPanorama(np.ascontiguousarray(pixels), struct.unpack(">256H", bgs[-512:]))
