"""V60 disassembly via MAME's unidasm (built by tools/build-mame.sh) and a cheap cross-reference finder."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from vrtools.config import REPO_ROOT
from vrtools.arcade.romset import RomSet, V60_BOOT, V60_PROGRAM

UNIDASM = REPO_ROOT / "build" / "mame" / "unidasm"
REGIONS = {"program": V60_PROGRAM, "boot": V60_BOOT}


class DisasmError(Exception):
    pass


@dataclass(frozen=True)
class Line:
    addr: int
    bytes: bytes
    text: str


_LINE = re.compile(r"^([0-9a-fA-F]+):\s+((?:[0-9a-fA-F]{2} ?)+?)\s{2,}(.*)$")
_HEX = re.compile(r"(?<![0-9a-zA-Z_])(?:#|0x)?([0-9A-Fa-f]{5,8})h?(?![0-9a-zA-Z_])")


def _region_for(rs: RomSet, addr: int) -> tuple[str, int, bytes]:
    for name, base in REGIONS.items():
        blob = getattr(rs, name)
        if base <= addr < base + len(blob):
            return name, base, blob
    raise DisasmError(f"address {addr:#x} is not in program or boot ROM")


def _unidasm(blob: bytes, base: int, skip: int, nbytes: int, suffix: str = ".bin") -> list[Line]:
    if not Path(UNIDASM).exists():
        raise DisasmError(f"unidasm not found at {UNIDASM}; run tools/build-mame.sh")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(blob)
        path = tmp.name
    try:
        proc = subprocess.run([str(UNIDASM), "-arch", "v60", "-basepc", f"0x{base + skip:x}", "-skip", f"0x{skip:x}",
                               "-count", str(nbytes), path], capture_output=True, text=True, check=True)  # -count is bytes
    except subprocess.CalledProcessError as e:
        raise DisasmError(f"unidasm failed: {e.stderr[-300:]}") from e
    finally:
        Path(path).unlink(missing_ok=True)
    lines: list[Line] = []
    for raw in proc.stdout.splitlines():
        m = _LINE.match(raw.rstrip())
        if not m:
            continue
        lines.append(Line(int(m.group(1), 16), bytes.fromhex(m.group(2).replace(" ", "")), m.group(3).strip()))
    return lines


def listing(rs: RomSet, addr: int, count: int = 64) -> list[Line]:
    name, base, blob = _region_for(rs, addr)
    return _unidasm(blob, base, addr - base, count * 12, f".{name}.bin")[:count]


def listing_bytes(blob: bytes, base: int) -> list[Line]:
    """Every instruction of `blob` as placed at V60 address `base` (the encoder's round-trip check)."""
    return [l for l in _unidasm(blob, base, 0, len(blob)) if l.addr < base + len(blob)]


def immediates(lines: list[Line], lo: int = 0x100000, hi: int = 0xFFFFFF) -> set[int]:
    out: set[int] = set()
    for ln in lines:
        for m in _HEX.finditer(ln.text):
            v = int(m.group(1), 16)
            if lo <= v <= hi:
                out.add(v)
    return out


def find_refs(rs: RomSet, value: int, regions: tuple[str, ...] = ("program", "boot"), width: int = 4) -> list[int]:
    """V60 addresses where `value` appears little-endian with the given byte width (4 or 3)."""
    needle = value.to_bytes(width, "little")
    hits: list[int] = []
    for name in regions:
        base, blob = REGIONS[name], getattr(rs, name)
        i = blob.find(needle)
        while i != -1:
            hits.append(base + i)
            i = blob.find(needle, i + 1)
    return hits
