"""Race tables of the boot ROM (M6 recon, `docs/spike/2026-11-m6-recon.md`; formats §14) and the per-course *race blob*.

- Time records: `TIME_TABLES[variant][data index]` -> four record pointers by level -> 24 u32 (initial clock in
  1/32 s, then the extension added by the k-th checkpoint of the race). Variant 0 = normal, 1 = operator flag
  `[0x40dc8c]`, 2 = linked play.
- Checkpoints: `CHECKPOINT_TABLE[data index]` -> `count, points[count]` (road-point indices on line 0; entry 0 is
  the start line).
- Car table: `CAR_TABLES[variant]`, 16 × 0x20: five model pointers, road-line index, start road point, performance.
- Race blob (free program ROM, one per converted course): three variant tables of four record pointers, twelve
  records, the checkpoint record and the car table; the directory loader serves them (`directory.py`).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, RomSet

TIME_TABLES = (0xFCD5B9, 0xFCD5C5, 0xFCD5D1)
CHECKPOINT_TABLE = 0xFCF16D
CAR_TABLES = (0xFCD395, 0xFCD195)
LAP_COUNT = 0x5011A4
TIME_WORDS = 24
EXTENSIONS = TIME_WORDS - 1
LEVELS = 4
VARIANTS = 3
CARS = 16
CAR_SIZE = 0x20
LINES = 8
MAX_CHECKPOINTS = 23                       # the checkpoint record is reserved 24 words (count + 23 entries)
RECORD_BYTES = 4 * TIME_WORDS
CHECKPOINT_BYTES = 4 * (MAX_CHECKPOINTS + 1)
CAR_TABLE_BYTES = CARS * CAR_SIZE
RACE_BLOB_BYTES = (16 * VARIANTS + VARIANTS * LEVELS * RECORD_BYTES + CHECKPOINT_BYTES + CAR_TABLE_BYTES + 15) // 16 * 16


@dataclass(frozen=True)
class TimeRecord:
    initial: int
    extensions: tuple[int, ...]


@dataclass(frozen=True)
class CarEntry:
    models: tuple[int, int, int, int, int]
    line: int
    start_point: int
    perf: float


@dataclass(frozen=True)
class RaceBlob:
    times: dict[tuple[int, int], TimeRecord]      # (variant, level) -> record
    checkpoints: tuple[int, ...]
    cars: list[CarEntry]


def _boot(rs: RomSet, addr: int, fmt: str):
    return struct.unpack_from(fmt, rs.boot, addr - V60_BOOT)


def _check_word(v: int, what: str) -> None:
    if not (0 <= v < 1 << 32):
        raise PatchError(f"{what} {v} is not a 32-bit word")


def time_record(rs: RomSet, variant: int, course: int, level: int) -> TimeRecord:
    rec_set = _boot(rs, TIME_TABLES[variant] + 4 * course, "<I")[0]
    rec = _boot(rs, rec_set + 4 * level, "<I")[0]
    words = _boot(rs, rec, f"<{TIME_WORDS}I")
    return TimeRecord(words[0], tuple(words[1:]))


def encode_time_record(r: TimeRecord) -> bytes:
    if len(r.extensions) != EXTENSIONS:
        raise PatchError(f"a time record holds {EXTENSIONS} extensions, not {len(r.extensions)}")
    for v in (r.initial, *r.extensions):
        _check_word(v, "time record value")
    return struct.pack(f"<{TIME_WORDS}I", r.initial, *r.extensions)


def checkpoints(rs: RomSet, course: int) -> tuple[int, ...]:
    rec = _boot(rs, CHECKPOINT_TABLE + 4 * course, "<I")[0]
    count = _boot(rs, rec, "<I")[0]
    return tuple(_boot(rs, rec + 4, f"<{count}I"))


def encode_checkpoints(points: tuple[int, ...]) -> bytes:
    if not points or points[0] != 0 or any(b <= a for a, b in zip(points, points[1:])) or len(points) > MAX_CHECKPOINTS:
        raise PatchError(f"checkpoints must rise from 0, at most {MAX_CHECKPOINTS}: {points}")
    for v in points:
        _check_word(v, "checkpoint")
    return struct.pack(f"<{len(points) + 1}I", len(points), *points)


def car_table(rs: RomSet, variant: int) -> list[CarEntry]:
    out = []
    for i in range(CARS):
        *models, line, start, perf = _boot(rs, CAR_TABLES[variant] + CAR_SIZE * i, "<5IIIf")
        out.append(CarEntry(tuple(models), line, start, perf))
    return out


def encode_car_table(cars: list[CarEntry]) -> bytes:
    if len(cars) != CARS:
        raise PatchError(f"a car table holds {CARS} cars, not {len(cars)}")
    out = b""
    for c in cars:
        if not (0 <= c.line < LINES):
            raise PatchError(f"car line {c.line} (0..{LINES - 1})")
        for v in (*c.models, c.start_point):
            _check_word(v, "car table value")
        out += struct.pack("<5IIIf", *c.models, c.line, c.start_point, c.perf)
    return out


def race_blob_layout(base: int) -> dict[str, int]:
    lay = {"variants": base, "records": base + 16 * VARIANTS}
    lay["checkpoints"] = lay["records"] + VARIANTS * LEVELS * RECORD_BYTES
    lay["cars"] = lay["checkpoints"] + CHECKPOINT_BYTES
    lay["end"] = lay["cars"] + CAR_TABLE_BYTES
    return lay


def encode_race_blob(b: RaceBlob, base: int) -> bytes:
    lay = race_blob_layout(base)
    ptrs, records = [], b""
    for v in range(VARIANTS):
        for level in range(LEVELS):
            if (v, level) not in b.times:
                raise PatchError(f"race blob lacks the time record for variant {v} level {level}")
            ptrs.append(lay["records"] + len(records))
            records += encode_time_record(b.times[(v, level)])
    cps = encode_checkpoints(b.checkpoints).ljust(CHECKPOINT_BYTES, b"\0")
    out = struct.pack(f"<{VARIANTS * LEVELS}I", *ptrs) + records + cps + encode_car_table(b.cars)
    assert base + len(out) == lay["end"]
    return out.ljust(RACE_BLOB_BYTES, b"\0")


def decode_race_blob(rs: RomSet, base: int) -> RaceBlob:
    """Read a blob back from program ROM (tests and reports)."""
    from vrtools.arcade.romset import V60_PROGRAM
    lay = race_blob_layout(base)
    p = rs.program
    rd = lambda a, fmt: struct.unpack_from(fmt, p, a - V60_PROGRAM)
    ptrs = rd(base, f"<{VARIANTS * LEVELS}I")
    times = {}
    for i, ptr in enumerate(ptrs):
        w = rd(ptr, f"<{TIME_WORDS}I")
        times[(i // LEVELS, i % LEVELS)] = TimeRecord(w[0], tuple(w[1:]))
    count = rd(lay["checkpoints"], "<I")[0]
    cps = tuple(rd(lay["checkpoints"] + 4, f"<{count}I"))
    cars = []
    for i in range(CARS):
        *models, line, start, perf = rd(lay["cars"] + CAR_SIZE * i, "<5IIIf")
        cars.append(CarEntry(tuple(models), line, start, perf))
    return RaceBlob(times, cps, cars)
