"""`.PAC` archives: an LZSS-compressed file table and files.

Layout (docs/spike/2026-11-phase90-ps2-disc-recon.md §1.1): u32 1, u32 unpacked size, then an LZSS stream (Okumura's:
flag byte read LSB first, 1 = a literal byte, 0 = a two-byte reference, position `b0 | (b1 & 0xf0) << 4` in a 4096-byte
ring buffer that starts zero-filled with its write position at 4078, length `(b1 & 0x0f) + 3`). Unpacked: u32 file count,
padding to 16, then 32 bytes per file (name[16], u32 size, 12 zero bytes); the files follow the table, each padded to a
multiple of 64 bytes.
"""

from __future__ import annotations

from vrtools.ps2 import Ps2ReadError

import struct
from dataclasses import dataclass

MAGIC = 1
RING = 4096
RING_START = RING - 18
MIN_MATCH = 3
TABLE_START = 16
ENTRY_BYTES = 32
NAME_BYTES = 16
FILE_ALIGN = 64


class PacError(Ps2ReadError):
    pass


def lzss_decode(src: bytes, size: int) -> bytes:
    """`size` bytes unpacked from the LZSS stream `src`, stopping at `size`. PacError when the stream ends first."""
    ring = bytearray(RING)
    r = RING_START
    out = bytearray()
    i = 0
    flags = 0
    n = len(src)
    while len(out) < size:
        flags >>= 1
        if not flags & 0x100:
            if i >= n:
                break
            flags = src[i] | 0xFF00
            i += 1
        if flags & 1:
            if i >= n:
                break
            c = src[i]
            i += 1
            out.append(c)
            ring[r] = c
            r = (r + 1) & (RING - 1)
        else:
            if i + 1 >= n:
                break
            b0, b1 = src[i], src[i + 1]
            i += 2
            pos = b0 | ((b1 & 0xF0) << 4)
            for k in range((b1 & 0x0F) + MIN_MATCH):
                if len(out) == size:                    # the declared size reached: a match never runs past it
                    break
                c = ring[(pos + k) & (RING - 1)]
                out.append(c)
                ring[r] = c
                r = (r + 1) & (RING - 1)
    if len(out) < size:
        raise PacError(f"LZSS stream ended after {len(out)} of {size} bytes")
    return bytes(out[:size])


def unpack(data: bytes) -> bytes:
    """The unpacked archive image of a `.PAC` file."""
    if len(data) < 8:
        raise PacError("too short for a PAC header")
    magic, size = struct.unpack_from("<II", data, 0)
    if magic != MAGIC:
        raise PacError(f"PAC magic {magic} (expected {MAGIC})")
    return lzss_decode(data[8:], size)


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int          # in the unpacked image
    size: int            # unpadded


def entries(image: bytes) -> list[Entry]:
    """The files of an unpacked archive image, in table order. PacError when the table and the sizes disagree."""
    if len(image) < TABLE_START:
        raise PacError("too short for an archive table")
    count = struct.unpack_from("<I", image, 0)[0]
    pos = TABLE_START + ENTRY_BYTES * count
    if pos > len(image):
        raise PacError(f"{count} entries do not fit in {len(image)} bytes")
    out = []
    for k in range(count):
        at = TABLE_START + ENTRY_BYTES * k
        name = image[at:at + NAME_BYTES].split(b"\0", 1)[0].decode("latin-1")
        size = struct.unpack_from("<I", image, at + NAME_BYTES)[0]
        if pos + size > len(image):
            raise PacError(f"{name}: {size} bytes at {pos:#x} run past the image ({len(image):#x})")
        out.append(Entry(name, pos, size))
        pos += (size + FILE_ALIGN - 1) // FILE_ALIGN * FILE_ALIGN
    return out


def read_archive(image: bytes) -> dict[str, bytes]:
    """{name: bytes} of an unpacked archive image (names as stored; their case varies on the disc)."""
    return {e.name: image[e.offset:e.offset + e.size] for e in entries(image)}


def read_pac(data: bytes) -> dict[str, bytes]:
    """{name: bytes} of a `.PAC` file."""
    return read_archive(unpack(data))


def find(files: dict[str, bytes], name: str) -> bytes:
    """A file by name, ignoring case (the disc mixes `cous00.tm2` and `cous00.TM2`). KeyError when absent."""
    want = name.lower()
    for k, v in files.items():
        if k.lower() == want:
            return v
    raise KeyError(name)
