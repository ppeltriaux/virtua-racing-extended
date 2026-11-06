"""Entity spawn lists (M6): the host course's race furniture re-placed on a converted course, its props dropped.

A spawn list is 0x100 pointer slots, each to `count:u32` then 24-byte records `x y z :f32, yaw:u16, type:u8, pad,
handler:u32, objlist:u32`; the loader (`0xffa7ec`) creates every record as an entity whatever the slot. The three
hosts share a family of handlers (recon `docs/spike/2026-11-m6-recon.md` §5): the HUD minimap, the start gantry,
two checkpoint gantries and the numbered grid boards; everything else is the host's trackside props, which sat on
the converted road at their absolute positions (Pacific Coast stopped dead against Bay Bridge's boards)."""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, replace

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.convert.road import heading_word

SLOTS = 0x100
RECORD = 24
MINIMAP = 0xFFCB59
START_GANTRY = 0xFFB07F
CHECKPOINT_GANTRIES = (0xFFB08A, 0xFFB095, 0xFFB0A0, 0xFFB0AB)
GRID_BOARDS = 0xFFC17E
KEEP_HANDLERS = {MINIMAP, START_GANTRY, *CHECKPOINT_GANTRIES, GRID_BOARDS}


@dataclass(frozen=True)
class Entity:
    x: float
    y: float
    z: float
    yaw: int                  # 1/65536 turn
    type: int
    handler: int
    objlist: int


def SPAWN_LIST_BYTES(n: int) -> int:
    return 4 * SLOTS + 4 + RECORD * n


def _read(rs: RomSet, addr: int, fmt: str):
    if addr >= V60_BOOT:
        return struct.unpack_from(fmt, rs.boot, addr - V60_BOOT)
    return struct.unpack_from(fmt, rs.program, addr - V60_PROGRAM)


def decode_spawn_list(rs: RomSet, table: int) -> list[Entity]:
    out = []
    for slot in _read(rs, table, f"<{SLOTS}I"):
        if not slot:
            continue
        count = _read(rs, slot, "<I")[0]
        for k in range(count):
            x, y, z, yaw, ty, _, handler, objs = _read(rs, slot + 4 + RECORD * k, "<3fHBBII")
            out.append(Entity(x, y, z, yaw, ty, handler, objs))
    return out


def encode_spawn_list(entities: list[Entity], base: int) -> bytes:
    """Slot 0 points at one list with every entity (right after the slots); the other slots are empty."""
    if base % 4:
        raise PatchError(f"spawn list at {base:#x} is misaligned")
    out = struct.pack("<I", base + 4 * SLOTS) + bytes(4 * (SLOTS - 1)) + struct.pack("<I", len(entities))
    for e in entities:
        if not (0 <= e.yaw < 0x10000 and 0 <= e.type < 0x100):
            raise PatchError(f"entity yaw {e.yaw} / type {e.type} out of range")
        out += struct.pack("<3fHBBII", e.x, e.y, e.z, e.yaw, e.type, 0, e.handler, e.objlist)
    return out


def _frame(line: list[tuple[float, float]], k: int) -> tuple[float, float, float, float, int]:
    """Point k's (x, z), the unit direction of travel and the road heading in 1/65536 turn."""
    n = len(line)
    (ax, az), (bx, bz) = line[k - 1], line[(k + 1) % n]
    d = math.hypot(bx - ax, bz - az) or 1.0
    dx, dz = (bx - ax) / d, (bz - az) / d
    return line[k][0], line[k][1], dx, dz, (heading_word(dx, dz) >> 16) * 4


def _relative(e: Entity, line: list[tuple[float, float]]) -> tuple[int, float, float, int]:
    """Nearest road point, signed lateral (right of travel positive), offset along the travel direction and yaw
    relative to the road heading."""
    k = min(range(len(line)), key=lambda i: (line[i][0] - e.x) ** 2 + (line[i][1] - e.z) ** 2)
    px, pz, dx, dz, heading = _frame(line, k)
    lateral = (e.x - px) * dz - (e.z - pz) * dx
    along = (e.x - px) * dx + (e.z - pz) * dz
    return k, lateral, along, (e.yaw - heading) & 0xFFFF


def road_relative(e: Entity, line: list[tuple[float, float]]) -> tuple[int, float, int]:
    """Nearest road point, signed lateral (right of travel positive) and yaw relative to the road heading."""
    k, lateral, _, dyaw = _relative(e, line)
    return k, lateral, dyaw


def absolute(k: int, lateral: float, dyaw: int, line: list[tuple[float, float]], height,
             along: float = 0.0) -> tuple[float, float, float, int]:
    px, pz, dx, dz, heading = _frame(line, k % len(line))
    x, z = px + lateral * dz + along * dx, pz - lateral * dx + along * dz
    return x, height(x, z), z, (heading + dyaw) & 0xFFFF


def _signed(k: int, n: int) -> int:
    return k - n if k > n // 2 else k


def replace_entities(host: list[Entity], host_line: list[tuple[float, float]], host_checkpoints: tuple[int, ...],
                     line: list[tuple[float, float]], checkpoints: tuple[int, ...], height, gantries: bool = True,
                     start_gantry: bool = True, grid_boards: bool = True) -> list[Entity]:
    """The minimap as is; the start gantry and grid boards at the same road-relative spot (signed road point from the
    start line, lateral, yaw relative to the road) on `line`; each checkpoint gantry at the converted checkpoint
    with the same index as the host checkpoint it stood at (none with `gantries` False: Phase 22e, the Saturn's own
    gates mark the checkpoints; no start gantry with `start_gantry` False: Phase 22o, a course that starts at the
    Saturn's own START gate has that gate drawn there; no grid boards with `grid_boards` False: Phase 22q, that entity
    draws the row of country flags along the start straight, which the Saturn's courses do not have). Everything else is
    dropped."""
    out = []
    gantries_wanted, gantries = gantries, []
    for e in host:
        if e.handler == MINIMAP:
            out.append(e)
        elif e.handler == START_GANTRY and not start_gantry:
            continue
        elif e.handler == GRID_BOARDS and not grid_boards:
            continue
        elif e.handler in (START_GANTRY, GRID_BOARDS):
            k, lat, along, dyaw = _relative(e, host_line)
            x, y, z, yaw = absolute(_signed(k, len(host_line)), lat, dyaw, line, height, along)
            out.append(replace(e, x=x, y=y, z=z, yaw=yaw))
        elif e.handler in CHECKPOINT_GANTRIES:
            gantries.append((road_relative(e, host_line), e))
    if sum(e.handler == MINIMAP for e in out) != 1 or sum(e.handler == START_GANTRY for e in out) != (1 if start_gantry else 0):
        raise PatchError("the host spawn list lacks the minimap or the start gantry")
    if not gantries_wanted:
        return out
    if len(gantries) != len(host_checkpoints) - 1 or len(checkpoints) != len(host_checkpoints):
        raise PatchError(f"{len(gantries)} checkpoint gantries for {len(host_checkpoints) - 1} host checkpoints "
                         f"and {len(checkpoints) - 1} converted ones")
    gantries.sort(key=lambda g: g[0][0])
    for ((k, lat, dyaw), e), cp in zip(gantries, checkpoints[1:]):
        x, y, z, yaw = absolute(cp, lat, dyaw, line, height)
        out.append(replace(e, x=x, y=y, z=z, yaw=yaw))
    return out
