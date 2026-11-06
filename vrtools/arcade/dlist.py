"""Walk a Model 1 display list (16-bit entries) the way MAME's tgp_render does.

Reference: src/mame/sega/model1_v.cpp (BSD-3-Clause, Olivier Galibert).
Offsets are in 16-bit units; `readi` joins two entries little-endian.
See docs/formats/model1-display-list.md.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

LIST_MASK = 0x7FFF
END = -1


@dataclass(frozen=True)
class Cmd:
    kind: int
    offset: int
    args: dict


def walk(entries: Sequence[int], start: int = 0) -> list[Cmd]:
    def rd(a: int) -> int:
        return entries[a & LIST_MASK]

    def readi(a: int) -> int:
        return rd(a) | (rd(a + 1) << 16)

    def readf(a: int) -> float:
        return struct.unpack("<f", struct.pack("<I", readi(a)))[0]

    def readi16(a: int) -> int:
        v = rd(a)
        return v - 0x10000 if v & 0x8000 else v

    cmds: list[Cmd] = []
    off = start
    while True:
        if off - start > LIST_MASK:                             # walked a full wrap without an end marker
            cmds.append(Cmd(END, off, {"stopped_on": None}))
            return cmds
        kind = readi(off)
        if kind == 0x00:
            cmds.append(Cmd(kind, off, {}))
            off += 2
        elif kind in (0x01, 0x41):
            cmds.append(Cmd(kind, off, {"tex_adr": readi(off + 2), "poly_adr": readi(off + 4), "size": readi(off + 6)}))
            off += 8
        elif kind == 0x02:                                      # skip_direct
            cmds.append(Cmd(kind, off, {"tex_adr": readi(off + 2)}))
            off += 18
            while off - start <= LIST_MASK:
                rtype = readi(off + 2) & 3
                if rtype == 0:
                    break
                off += 12 if rtype == 2 else 20
            off += 4
        elif kind == 0x03:
            cmds.append(Cmd(kind, off, {"xc": readi16(off + 4), "yc": readi16(off + 6), "x1": readi16(off + 8),
                                        "y2": readi16(off + 10), "x2": readi16(off + 12), "y1": readi16(off + 14)}))
            off += 16
        elif kind in (0x04, 0x05, 0x06):                       # uploads: adr at +2, len at +4
            adr, n = readi(off + 2), readi(off + 4)
            if kind == 0x04:
                n += 1                                          # colour table: len+1 16-bit values
            if 6 + 2 * n > LIST_MASK + 1:
                cmds.append(Cmd(END, off, {"stopped_on": kind, "reason": "bad length"}))
                return cmds
            read = rd if kind == 0x04 else readi
            cmds.append(Cmd(kind, off, {"adr": adr, "len": n, "data": [read(off + 6 + 2 * i) for i in range(n)]}))
            off += 6 + 2 * n
        elif kind in (0x07, 0x08):
            cmds.append(Cmd(kind, off, {"value": readi(off + 2)}))
            off += 4
        elif kind == 0x09:
            cmds.append(Cmd(kind, off, {"zx": readf(off + 2), "zy": readf(off + 4)}))
            off += 6
        elif kind == 0x0A:
            cmds.append(Cmd(kind, off, {"light": (readf(off + 2), readf(off + 4), readf(off + 6))}))
            off += 8
        elif kind == 0x0B:
            cmds.append(Cmd(kind, off, {"mat": [readf(off + 2 + 2 * i) for i in range(12)]}))
            off += 26
        elif kind == 0x0C:
            cmds.append(Cmd(kind, off, {"tx": readf(off + 2), "ty": readf(off + 4)}))
            off += 6
        else:
            cmds.append(Cmd(END, off, {"stopped_on": kind}))
            return cmds


def parse_log(path: Path) -> Iterator[tuple[int, int, list[Cmd]]]:
    """Yield (frame, list_base, cmds) from a dlist_log.lua dump: `F <frame> <base_hex> <hex entries>`."""
    with open(path) as f:
        for line in f:
            if not line.startswith("F "):
                continue
            _, frame, base, hexdata = line.split()
            data = bytes.fromhex(hexdata)
            entries = [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)]
            yield int(frame), int(base, 16), walk(entries)
