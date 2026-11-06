"""SH-2 listing helper (unidasm -arch sh2) for the Saturn executable VRCODELO."""

from __future__ import annotations

import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from vrtools.config import REPO_ROOT

UNIDASM = REPO_ROOT / "build" / "mame" / "unidasm"
IP_SIZE = 0x100          # the Saturn IP header occupies the first 256 bytes of the boot file


class Sh2Error(Exception):
    pass


@dataclass(frozen=True)
class Line:
    addr: int
    bytes: bytes
    text: str


_LINE = re.compile(r"^([0-9a-fA-F]+):\s+((?:[0-9a-fA-F]{2} ?)+?)\s{2,}(.*)$")


def vrcodelo_load_address(ip: bytes) -> int:
    """Lowest 0x06xxxxxx jump-table constant in the boot file after the IP header, rounded down to 4 KB.

    The Saturn IP loads VRCODELO at 0x06010000; its jump table (0x06010034, 0x06010208, ...) sits in
    the boot file, so the smallest such constant locates the load page."""
    best = None
    for k in range(IP_SIZE, min(len(ip), 0x400) - 3, 4):
        v = struct.unpack_from(">I", ip, k)[0]
        if 0x06004000 <= v < 0x06100000 and (best is None or v < best):
            best = v
    if best is None:
        raise Sh2Error("no 0x06xxxxxx load constants found in the IP")
    return best & ~0xFFF


def listing(blob: bytes, base: int, addr: int, count: int = 32) -> list[Line]:
    if not Path(UNIDASM).exists():
        raise Sh2Error(f"unidasm not found at {UNIDASM}; run tools/build-mame.sh")
    if not (base <= addr < base + len(blob)):
        raise Sh2Error(f"address {addr:#x} is outside the blob ({base:#x}..{base + len(blob):#x})")
    with tempfile.NamedTemporaryFile(suffix=".sh2.bin", delete=False) as tmp:
        tmp.write(blob)
        path = tmp.name
    try:
        proc = subprocess.run([str(UNIDASM), "-arch", "sh2", "-basepc", f"0x{addr:x}", "-skip", f"0x{addr - base:x}",
                               "-count", str(count * 4), path], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise Sh2Error(f"unidasm failed: {e.stderr[-300:]}") from e
    finally:
        Path(path).unlink(missing_ok=True)
    lines = []
    for raw in proc.stdout.splitlines():
        m = _LINE.match(raw.rstrip())
        if m:
            lines.append(Line(int(m.group(1), 16), bytes.fromhex(m.group(2).replace(" ", "")), m.group(3).strip()))
    return lines[:count]


def find_refs(blob: bytes, base: int, value: int) -> list[int]:
    needle = struct.pack(">I", value)
    out = []
    i = blob.find(needle)
    while i != -1:
        out.append(base + i)
        i = blob.find(needle, i + 1)
    return out
