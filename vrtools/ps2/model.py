"""Model files (`.bin` with the chunks Frame, Micro, Shape, Hrchy and optionally Tim2, Anime, Skin).

Layout (docs/spike/2026-11-phase90-ps2-disc-recon.md §3.2): u32 1, two zero words, the chunk count, then 16 bytes per
chunk (name[12], u32 offset). The geometry is a non-indexed triangle list introduced by four words
`(texture, n × 16, format, n)` and followed by four arrays of n float vec4s: position (x, y, z, 1), normal (nx, ny, nz, 1),
texture coordinate (u, v, 1, 0) and colour (r, g, b, 128). A file holds one list per texture it uses, the header's first word
being the texture's index among the names of the Tim2 chunk (Beltway's sections: a list on `cous00`, then one on `cous00b`),
in world coordinates (Frame, Micro and Hrchy are not decoded); the shadows' lists have format 0x1803 and zero texture coordinates, the rest
0x1813. Positions are in the PS2 frame: arcade units, y down (§3.1).
"""

from __future__ import annotations

from vrtools.ps2 import Ps2ReadError

import dataclasses
import re
import struct
from dataclasses import dataclass

import numpy as np

HEADER_WORDS = 4
ARRAYS = 4
VEC4 = 16
FORMATS = (0x1813, 0x1803)
MAX_VERTICES = 1 << 20
MAX_TEXTURES = 15
TEXTURE_NAME = re.compile(rb"[\w]+\.(?:tm2|TM2)")


class ModelError(Ps2ReadError):
    pass


@dataclass(frozen=True)
class Mesh:
    offset: int                 # of the four header words
    format: int
    positions: np.ndarray       # (n, 3) float32
    normals: np.ndarray         # (n, 3)
    uvs: np.ndarray             # (n, 2)
    colours: np.ndarray         # (n, 4): r, g, b, a as stored (0..255, a = 128)
    texture: int = 0            # index into the file's texture names (`texture_names`): the list header's first word
    texture_name: str = ""      # that name ("" when the file names fewer textures)

    @property
    def triangles(self) -> np.ndarray:
        """(n / 3, 3, 3) corner positions."""
        return self.positions.reshape(-1, 3, 3)

    def __len__(self) -> int:
        return len(self.positions) // 3


def is_model(data: bytes) -> bool:
    return len(data) >= 0x20 and data[:12] == b"\x01" + b"\0" * 11 and data[16:21] == b"Frame"


def chunks(data: bytes) -> dict[str, int]:
    """{chunk name: offset} from the header."""
    if not is_model(data):
        raise ModelError("not a model file (no Frame chunk in the header)")
    count = struct.unpack_from("<I", data, 12)[0]
    out = {}
    for k in range(count):
        at = 16 + 16 * k
        if at + 16 > len(data):
            raise ModelError(f"chunk table entry {k} past the end")
        name = data[at:at + 12].split(b"\0", 1)[0].decode("latin-1")
        out[name] = struct.unpack_from("<I", data, at + 12)[0]
    return out


def _mesh_at(data: bytes, off: int) -> Mesh | None:
    texture, size, fmt, n = struct.unpack_from("<4I", data, off)
    if texture > MAX_TEXTURES or fmt not in FORMATS or not (3 <= n <= MAX_VERTICES) or n % 3 or size != n * VEC4:
        return None
    base = off + VEC4
    if base + ARRAYS * n * VEC4 > len(data):
        return None
    arr = np.frombuffer(data, dtype="<f4", count=ARRAYS * n * 4, offset=base).reshape(ARRAYS, n, 4)
    if not np.all(arr[0, :, 3] == 1.0):
        return None
    return Mesh(off, fmt, arr[0, :, :3].copy(), arr[1, :, :3].copy(), arr[2, :, :2].copy(), arr[3].copy(), texture)


def meshes(data: bytes) -> list[Mesh]:
    """Every triangle list of a model file, in file order (16-byte aligned search)."""
    chunks(data)
    names = texture_names(data)
    out = []
    off = 0x10
    while off + VEC4 <= len(data):
        m = _mesh_at(data, off)
        if m is None:
            off += VEC4
            continue
        if m.texture < len(names):
            m = dataclasses.replace(m, texture_name=names[m.texture])
        out.append(m)
        off = m.offset + VEC4 + ARRAYS * len(m.positions) * VEC4
    return out


def texture_names(data: bytes) -> list[str]:
    """The picture names a model refers to (its Tim2 chunk), in order of first appearance."""
    return list(dict.fromkeys(m.decode("latin-1") for m in TEXTURE_NAME.findall(data)))
