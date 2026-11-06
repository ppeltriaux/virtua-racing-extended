"""Parse and aggregate memory traces written by vrtools/mame/lua/memtrace.lua.

Line formats:
  B <frame> <bank>                      data-ROM bank selected (write of (bank<<4)|1 to 0xe00004)
  R <frame> <pc> <addr> <bank> <count>  reads of V60 address page (addr & ~0xff) by pc, aggregated per frame
  W <frame> <pc> <addr> <count>         writes, same aggregation
  D <frame> <path>                      work-RAM dump written
  E <frame> <message>                   tracer-side error (kept so the rest of the log still parses)
  END <frames> <events>                 checkpoint; may appear several times, the last one counts
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

DATA_WINDOW = 0x100000
DATA_WINDOW_SIZE = 0x100000


class TraceError(Exception):
    pass


@dataclass(frozen=True)
class Event:
    kind: str
    frame: int
    pc: int
    addr: int
    bank: int
    count: int


def parse_trace(path: Path) -> list[Event]:
    events: list[Event] = []
    ended = False
    with open(path) as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            k = parts[0]
            if k == "END":
                ended = True
                continue
            if k == "B":
                events.append(Event(k, int(parts[1]), 0, 0, int(parts[2]), 0))
            elif k == "R":
                events.append(Event(k, int(parts[1]), int(parts[2], 16), int(parts[3], 16), int(parts[4]), int(parts[5])))
            elif k == "W":
                events.append(Event(k, int(parts[1]), int(parts[2], 16), int(parts[3], 16), 0, int(parts[4])))
            elif k == "D":
                events.append(Event(k, int(parts[1]), 0, 0, 0, 0))
            elif k == "E":                                   # flush error reported by the tracer
                events.append(Event(k, int(parts[1]), 0, 0, 0, 0))
            else:
                raise TraceError(f"{path}: unknown line {line.strip()!r}")
    if not ended:
        raise TraceError(f"{path}: no END line (trace incomplete)")
    return events


def data_rom_addr(addr: int, bank: int) -> int | None:
    """V60 address in the banked window -> absolute offset into RomSet.data, else None."""
    if DATA_WINDOW <= addr < DATA_WINDOW + DATA_WINDOW_SIZE:
        return bank * DATA_WINDOW_SIZE + (addr - DATA_WINDOW)
    return None


def by_pc(events: list[Event]) -> dict[int, Counter]:
    out: dict[int, Counter] = defaultdict(Counter)
    for e in events:
        if e.kind != "R":
            continue
        a = data_rom_addr(e.addr, e.bank)
        if a is not None:
            out[e.pc][a] += e.count
    return dict(out)


def by_page(events: list[Event]) -> dict[int, Counter]:
    out: dict[int, Counter] = defaultdict(Counter)
    for e in events:
        if e.kind != "R":
            continue
        a = data_rom_addr(e.addr, e.bank)
        if a is not None:
            out[a][e.pc] += e.count
    return dict(out)


def summary(events: list[Event]) -> str:
    n = sum(e.count for e in events if e.kind in "RW")
    reads = [e for e in events if e.kind == "R"]
    writes = [e for e in events if e.kind == "W"]
    frames = sorted({e.frame for e in events})
    lines = [f"{n} events in {len(frames)} frames" + (f" ({frames[0]}..{frames[-1]})" if frames else "")]
    lines.append(f"reads: {sum(e.count for e in reads)} by {len({e.pc for e in reads})} pcs; "
                 f"writes: {sum(e.count for e in writes)} by {len({e.pc for e in writes})} pcs")
    return "\n".join(lines)
