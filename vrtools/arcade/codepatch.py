"""Exact-length code patches in the V60 boot and program ROMs."""
from __future__ import annotations

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.arcade.v60asm import asm

REGIONS = (("boot", V60_BOOT), ("program", V60_PROGRAM))


def patch_span(rs: RomSet, addr: int, blob: bytes, length: int) -> None:
    """Overwrite exactly `length` bytes at V60 code address `addr` with `blob` padded by `nop`s, in place.
    PatchError when the blob is longer than the span or the address is not in the boot or program ROM."""
    if len(blob) > length:
        raise PatchError(f"patch at {addr:#x} is {len(blob)} bytes, span is {length}")
    for name, base in REGIONS:
        region = getattr(rs, name)
        if base <= addr and addr + length <= base + len(region):
            data = bytearray(region)
            data[addr - base:addr - base + length] = blob + asm("nop") * (length - len(blob))
            object.__setattr__(rs, name, bytes(data))
            return
    raise PatchError(f"{addr:#x} (+{length}) is not inside the boot or program ROM")
