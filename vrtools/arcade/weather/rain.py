"""Weather stage 2: the rain, as the owner approved it (spec 5.3): 300 narrow solid 3D box drops falling with a slight wind slant in a
volume round the camera, anchored to the world sideways when the car turns, ending on the road with a splash fixed to the road; an
overcast grade over the 3D picture and each course's backdrop greyed. A module of the storm's carrier (weather/carrier.py: its RAM
contract); its RAM cells, tables and code are laid out there.

Pascal's path to it (17 Nov 2026): stippled streaks and flat screen streaks rejected; "rectangleish drops falling with depth
perspective", "transparent 3d paralellepipedes"; of the streaming drops "they should probably still be falling down"; solid faces
kept (stipple reads as a grid); "One thing that feel missing is the impact on the road, it look like they're floating"; "narrower
drops"; of the flash a late pass made, "like a flash"; then "the rain is good". Haze: "just look like a grid" (none).

Ported (rewritten from the listings, the values unchanged) from spike 46 (`spike/p46_rain.py`: the clusters, their motion, the
overcast and the skies), spike 47/48 (`spike/p48_rain.py`: landing, splashes, the narrower drops, the guard, mode 0x13) as spike 70
joined them (`spike/p70_storm.py`: the storm's switch, the grade back in one copy at the end, the sky written once at the start and
put back when palette RAM still holds it). The time guard is the prototype's (the game's vblank count, carrier.emit_guard_time).
Differences, each from a gate (the stage plan's D5-D7 and its fallback round): the 60 clusters are placed in the carrier's start
passes before the rain shows, START_QUOTA a pass (the prototype placed and drew all of them in its first rain pass: 17.84-18.06 ms);
the grade copies GRADE_ROWS rows a pass of the overcast table built here (the same values the prototype computed on the V60; it made
one row a pass always and up to 8 while no vblank had come: the grade faded in over about 34 passes at the pit box, "~1.2 s", which
3 rows a pass keeps: 32 passes); every row waits for the guard too (the prototype's first row did not).

A rain pass (the carrier's SHOW state), as spike 48's: the car's speed gives the slant (wind / fall + 0.05 per unit a frame, at most
0.30), the yaw's change shifts every cluster sideways by depth x angle (the rain stays with the world when the car turns); each of
the 60 clusters (5 drops, one of 8 shapes, a random tilt) falls 0.32 and drifts 0.05 a pass in view space, wraps at the sides, and
goes back to the top at a new depth (3.6 + 41.4 r^2) once out of the bottom or with all its drops landed; a drop lands when its
bottom reaches the car's ground plane in view space (the camera matrix 0x501b00 and the car's ground contact and pitch); a landing
1 to 35 units deep, within 12 units sideways and outside the car's box spawns a splash (a 40-entry ring, world coordinates, 6
stages, drawn sheared onto the ground plane, grown beyond 12 units deep); the clusters are drawn first, then the splashes, each
only while the frame's records stay within the budget and the pass is not late; after a late pass no new splashes for 3 passes,
and a late splash loop frees the splashes it did not reach. Then GRADE_ROWS rows of the grade."""
from __future__ import annotations

import math
import random
import struct

import numpy as np

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_PROGRAM, RomSet
from vrtools.arcade.v60asm import Block
from vrtools.arcade.weather import carrier
from vrtools.arcade.weather.carrier import (BUDGET, LIST_PTR, REC_COUNT, XLAT, emit_copy, emit_guard_time)
from vrtools.arcade.weather.tune import RainTune

# ---- the game's cells ----------------------------------------------------------------------------------------------------------
PLAYER = 0x400D00
SPEED, YAW = PLAYER + 0x14, PLAYER + 0x6A
PX, PY, PZ, PITCH = PLAYER + 0x1E, PLAYER + 0x22, PLAYER + 0x26, PLAYER + 0x2A
CAM = 0x501B00                          # the camera matrix: 12 floats, the 3 x 3 column-major, then the translation


def m(k: int) -> int:
    return CAM + 4 * k


# ---- the drops (spike 46, spike 48's narrower cross-section) ----------------------------------------------------------------
SEED = 45                               # the shapes' random sequence (spike 70's)
NDROP, NSHAPE = 5, 8
KV = 0.00872                            # units a logic frame per unit of the car's speed word
FALL, WIND = 0.32, 0.05
ZMIN, ZFAR = 3.6, 45.0                  # a cluster's depth ZMIN + (ZFAR - ZMIN) r^2
XEDGE, YTOP, YBOT = 248.0 / 210.0, 221.0 / 280.0, 163.0 / 280.0
EDGEK, MARG = 0.15, 2.5                 # the view's edges + EDGEK z + MARG
SPREAD, TILT = 2.0, 0.5                 # drop offsets in a cluster (+-), the sheet's depth tilt along x (+-)
S0, KS, SMAX = WIND / FALL, 0.05, 0.30  # the slant dx/dy: wind, + KS per unit a frame of speed, at most SMAX
W_R, H_R, TH_R, HL = (0.035, 0.05), (0.38, 0.62), (10.0, 35.0), 0.3     # width (spike 48: half spike 46's), height, turn, highlight
ZG = 14.0                               # clusters grow as max(1, z / ZG)
DYAW_MAX = 0x800
KYAW = 2 * math.pi / 65536
# ---- the splashes (spike 47/48) ----------------------------------------------------------------------------------------------
NSP = 40
ZDRAW, LAT, ZSG = 3.0, 12.0, 12.0       # nearer than ZDRAW not drawn; spawned within LAT sideways; grown beyond ZSG
CARW, CARL = 1.4, 2.6                   # no splash inside the car's box (view space)
T_LIM, G0_LIM = 0.6, 8.0                # clamps on the ground plane (between scenes the matrix can be anything)
SREC = 14
LATE_HOLD = 3                           # no new splashes for this many passes after a late one
SZ = 0.8
RIN = tuple(SZ * v for v in (0.05, 0.12, 0.19, 0.25, 0.30, 0.34))
ROUT = tuple(SZ * v for v in (0.14, 0.24, 0.31, 0.35, 0.38, 0.40))
CROWN = tuple(SZ * v for v in (0.07, 0.11, 0.10, 0.07, 0.03, 0.0))
DR = tuple(SZ * v for v in (0.08, 0.16, 0.24, 0.30, 0.35, 0.39))
DY = tuple(SZ * v for v in (0.08, 0.20, 0.27, 0.27, 0.20, 0.08))
DW = ((0.05, 0.08), (0.06, 0.10), (0.06, 0.10), (0.05, 0.09), (0.05, 0.08), (0.04, 0.06))
DANG = ((30.0, 150.0, 260.0), (80.0, 200.0, 320.0))
SEG = 8
# ---- polygon and colour words ------------------------------------------------------------------------------------------------
MOIRE, NOCULL, ZMAX, ZMIN_MODE = 0x2000, 0x4000, 2 << 10, 1 << 10
FULL = 0xC00                            # colour word mode 3: unlit, full intensity
GLASS = {"L": (17, 18, 21), "H": (29, 30, 31), "F": (19, 20, 23), "R": (15, 16, 19), "T": (27, 28, 30)}   # targets under the grade
SPLASH_COLOURS = {"ring": (24, 25, 27), "drop": (29, 30, 31), "ring_late": (20, 21, 24)}
POLY_PALETTE = 0x2EC980                 # the polygon palette in the program ROM (the boot copies it to 0x902000, 0xfe6b04)
POLY_PALETTE_END = 0x2ED082
DYNAMIC = (40, 41)                      # entries the game changes at run time: never picked
# ---- the grade (spike 46) and the skies --------------------------------------------------------------------------------------
KEEP, GREY, DARK, SH = 0.66, (16.5, 17.5, 19.5), (0.90, 0.92, 0.97), 18
LPROT = 56                              # c = 0 entries from LPROT kept black under the grade (the HUD map's line)
BOOT_PARAMS = [(1, 0, 1, 2, -2)] * 3    # the boot's table: (c (l + 1) + 2) >> 2
ROWS, ROW_ENTRIES = 96, 64              # 3 channels x 32 values; entries used per row
ROW_STRIDE = 0x200                      # bytes between the colour RAM's rows
GRADE_ROWS = 3                          # rows a pass (the fixed quota; the prototype's fade took about 34 passes at the pit box)
START_QUOTA = 20                        # clusters placed a start pass (the fixed quota: three start passes; measured in the findings)
SKY_KEEP, SKY_GREY, SKY_DARK = 0.35, (21.0, 22.0, 24.0), (0.90, 0.92, 0.95)   # Metropolis's (spike 46)
BF_SAT, BF_KEEP = 0.25, 0.40            # every other course: Big Forest's desaturating formula (spike 46)
METROPOLIS = 6
SKY_DST = 0x900C00                      # the backdrop palette's place in palette RAM (every course's first block)
SKY_COMPARE = (1, 2, 3)                 # colours compared to know palette RAM still holds our grey


def F(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def cover_cell(lay, name: str) -> int:
    """A cover state word (weather/cover.py) the rain reads."""
    from vrtools.arcade.weather import cover
    return cover.cell(lay, name)


# ==================================================================================================================== objects
def shapes(seed: int = SEED) -> list[list[tuple]]:
    """Per shape the drops (x, y, w, h, turn), as spike 46 drew them (the same random sequence)."""
    rng = random.Random(seed)
    out = []
    for _ in range(NSHAPE):
        pts = []
        while len(pts) < NDROP:
            p = (rng.uniform(-SPREAD, SPREAD), rng.uniform(-SPREAD, SPREAD))
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 1.1 for q in pts):
                pts.append(p)
        boxes = []
        for x, y in pts:
            th = math.radians(rng.uniform(*TH_R)) * rng.choice((-1, 1))
            boxes.append((x, y, rng.uniform(*W_R), rng.uniform(*H_R), th))
        out.append(boxes)
    return out


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _faces_out(q, out) -> bool:
    """MAME's back-face test keeps the drawn quad q when (q1 - q0) x (q2 - q0) points along `out`."""
    n = _cross(_sub(q[1], q[0]), _sub(q[2], q[0]))
    return n[0] * out[0] + n[1] * out[1] + n[2] * out[2] > 0


def box(cx, cy, w, h, th) -> list[tuple]:
    """One drop: records (face, link, p0, p1, normal); a square w x w turned by th about y, h tall, centred at (cx, cy, 0). A quad
    strip round the left side, a highlight strip on the front's left edge, the front, the right side, then the top (back faces
    culled by the renderer: the faces the camera sees are drawn)."""
    a = w / 2
    c, s = math.cos(th), math.sin(th)

    def plan(u, v):
        return (cx + u * c - v * s, u * s + v * c)
    corners = {"BL": plan(-a, a), "FL": plan(-a, -a), "FR": plan(a, -a), "BR": plan(a, a)}
    fl, fr = corners["FL"], corners["FR"]
    corners["M"] = (fl[0] + HL * (fr[0] - fl[0]), fl[1] + HL * (fr[1] - fl[1]))
    yb, yt = cy - h / 2, cy + h / 2
    ring = ["BL", "FL", "M", "FR", "BR"]
    faces = ["L", "H", "F", "R"]
    norms = {"L": (-c, 0.0, -s), "H": (s, 0.0, -c), "F": (s, 0.0, -c), "R": (c, 0.0, s)}
    edge = {k: ((x, yb, z), (x, yt, z)) for k, (x, z) in corners.items()}
    q = (edge["BL"][1], edge["BL"][0], edge["FL"][0], edge["FL"][1])
    flip = not _faces_out(q, norms["L"])
    e = {k: (v[::-1] if flip else v) for k, v in edge.items()}
    recs = [("J", 0, *e["BL"], norms["L"])]
    for k in range(4):
        q = (e[ring[k]][1], e[ring[k]][0], e[ring[k + 1]][0], e[ring[k + 1]][1])
        if not _faces_out(q, norms[faces[k]]):
            raise PatchError(f"a drop's face {faces[k]} winds inward (turn {th})")
        recs.append((faces[k], 2, *e[ring[k + 1]], norms[faces[k]]))
    t = [(corners[k][0], yt, corners[k][1]) for k in ("FL", "FR", "BR", "BL")]
    if not _faces_out(t, (0.0, 1.0, 0.0)):
        t = t[::-1]
    recs.append(("J", 0, t[1], t[0], (0.0, 1.0, 0.0)))
    recs.append(("T", 2, t[2], t[3], (0.0, 1.0, 0.0)))
    return recs


def _rec(flags, n, p0, p1) -> bytes:
    return struct.pack("<I3f3f3f", flags, *n, *p0, *p1)


def cluster_object(boxes) -> tuple[bytes, int, list[str]]:
    """The first record's points are the seeds; every record after the first steps the colour pointer (flag 12). (bytes, records,
    each record's face)."""
    recs = [r for b in boxes for r in b]
    first = recs[0]
    out = struct.pack("<6f", *first[2], *first[3])
    order = []
    for k, (face, link, p0, p1, n) in enumerate(recs[1:]):
        fl = 0x1 | ZMAX | (link << 8) | (0x1000 if k else 0)
        out += _rec(fl, n, p0, p1)
        order.append(face)
    out += struct.pack("<I9f", 0, *([0.0] * 9))
    return out, len(order), order


def drop_objects(seed: int = SEED) -> tuple[list[bytes], int, int, list[str], bytes]:
    """Each shape's drops sorted by their bottom; per shape NDROP variants (all its drops, then without the lowest, the two lowest,
    ...): (the 40 objects padded to one size, that size, the full object's records (34), its faces, the drop table: per shape and
    drop (x, bottom) as two floats)."""
    objs, table = [], b""
    for meta in shapes(seed):
        meta = sorted(meta, key=lambda bx: bx[1] - bx[3] / 2)
        boxes = [box(*bx) for bx in meta]
        for k in range(NDROP):
            objs.append(cluster_object(boxes[k:]))
        table += b"".join(struct.pack("<2f", x, y - h / 2) for x, y, w, h, th in meta)
    size = len(objs[0][0])
    for k, (o, n, od) in enumerate(objs):
        if n != objs[0][1] - 7 * (k % NDROP) or od != objs[0][2][:n] or len(o) > size:
            raise PatchError(f"the drop object {k} is not the full one less {k % NDROP} drops")
    return [o + b"\0" * (size - len(o)) for o, _, _ in objs], size, objs[0][1], objs[0][2], table


def splash_object(t: int, layout: int) -> bytes:
    """Stage t of a splash: the ring strip (8 records, inner edge on the ground, outer edge raised) and 3 droplets."""
    base = 0x1 | ZMIN_MODE | NOCULL
    ri, ro, h = RIN[t], ROUT[t], CROWN[t]
    ang = [2 * math.pi * k / SEG for k in range(SEG + 1)]
    inner = [(ri * math.cos(a), 0.0, ri * math.sin(a)) for a in ang]
    outer = [(ro * math.cos(a), h, ro * math.sin(a)) for a in ang]
    out = struct.pack("<6f", *inner[0], *outer[0])
    for k in range(1, SEG + 1):
        out += _rec(base | (2 << 8), (0.0, 1.0, 0.0), inner[k], outer[k])
    w, hh = DW[t]
    for j, a in enumerate(DANG[layout]):
        a = math.radians(a + 25 * t)
        cx, cz, cy = DR[t] * math.cos(a), DR[t] * math.sin(a), DY[t]
        A, B = (cx, cy + hh / 2, cz), (cx + w / 2, cy, cz)
        C, D = (cx, cy - hh / 2, cz), (cx - w / 2, cy, cz)
        out += _rec(base | (0x1000 if j == 0 else 0), (0.0, 0.0, -1.0), B, A)
        out += _rec(base | (2 << 8), (0.0, 0.0, -1.0), C, D)
    out += struct.pack("<I9f", 0, *([0.0] * 9))
    return out


def splash_objects(frames: int) -> list[bytes]:
    """Two droplet layouts x `frames` stages (layout-major)."""
    return [splash_object(t, layout) for layout in range(2) for t in range(frames)]


# ==================================================================================================================== colours
def overcast_params() -> list[tuple[int, int, int, int, int]]:
    """Per channel (A, B, S, round, -shift): out = ((A c + B) (l + 1) S + round) >> shift."""
    return [(round(KEEP * 256), round((1 - KEEP) * GREY[ch] * 256), round(DARK[ch] * 256), 1 << (SH - 1), -SH) for ch in range(3)]


def xlat_value(c: int, l1: int, p) -> int:
    a, b, s, r, sh = p
    v = ((a * c + b) * l1 * s + r) >> (-sh)
    return 0xFFFF if v >= 256 else v


def overcast_table() -> np.ndarray:
    """[channel][c][l] under the grade (l < 64), the c = 0 entries from LPROT black."""
    P = overcast_params()
    T = np.array([[[xlat_value(c, l + 1, P[ch]) for l in range(ROW_ENTRIES)] for c in range(32)] for ch in range(3)], np.int64)
    T[:, 0, LPROT:] = 0
    return T


def boot_table() -> np.ndarray:
    """[channel][c][l] as the boot makes it (0xfe011a..0xfe01a7)."""
    return np.array([[[xlat_value(c, l + 1, BOOT_PARAMS[ch]) for l in range(ROW_ENTRIES)] for c in range(32)] for ch in range(3)],
                    np.int64)


def table_bytes(T: np.ndarray) -> bytes:
    """96 rows (channel x 32 + c) of 64 halfwords."""
    return np.ascontiguousarray(T.reshape(ROWS, ROW_ENTRIES)).astype("<u2").tobytes()


def shown5(c: int, ch: int) -> int:
    """The 5-bit channel shown for palette channel c at full intensity under the grade."""
    return (xlat_value(c, 64, overcast_params()[ch]) >> 3) & 0x1F


def polygon_palette(rs: RomSet) -> list[int]:
    """The polygon palette as the boot copies it, the entries the game changes at run time as 0 (never picked)."""
    a = POLY_PALETTE - V60_PROGRAM
    words = list(struct.unpack_from(f"<{(POLY_PALETTE_END - POLY_PALETTE) // 2}H", rs.program, a))
    for k in DYNAMIC:
        words[k] = 0
    return words


def pick(palette: list[int], target: tuple[int, int, int]) -> int:
    """The palette entry (not 0) whose colour under the grade is nearest `target` (squared distance; the first of equals)."""
    best = None
    for i, w in enumerate(palette):
        if w == 0:
            continue
        c = (w & 31, (w >> 5) & 31, (w >> 10) & 31)
        d = sum((shown5(c[k], k) - target[k]) ** 2 for k in range(3))
        if best is None or d < best[0]:
            best = (d, i)
    return best[1]


def colour_words(rs: RomSet, faces: list[str], frames: int) -> tuple[list[int], list[int]]:
    """(the drops' sequence, a word per record: a jump record takes the next face's colour; the splashes': per stage the ring,
    dimmer in the last two stages, and the droplets)."""
    pal = polygon_palette(rs)
    picks = {f: pick(pal, t) for f, t in GLASS.items()}
    drops = [FULL | picks[faces[k + 1] if f == "J" else f] for k, f in enumerate(faces)]
    sp = {c: pick(pal, t) for c, t in SPLASH_COLOURS.items()}
    splashes = []
    for t in range(frames):
        splashes += [FULL | sp["ring_late" if t >= frames - 2 else "ring"], FULL | sp["drop"]]
    return drops, splashes


def rgb555(r, g, b) -> int:
    return 0x8000 | (int(b) << 10) | (int(g) << 5) | int(r)


def grey_sky(cols: list[int], metropolis: bool) -> list[int]:
    """A course's backdrop colours greyed (spike 46: Metropolis's own blend; every other course desaturated first, Big Forest's
    formula); every 16th colour (transparent) and bit 15 kept."""
    out = []
    for k, w in enumerate(cols):
        if k % 16 == 0:
            out.append(w)
            continue
        c = [w & 31, (w >> 5) & 31, (w >> 10) & 31]
        if metropolis:
            g = [min(31, round((SKY_KEEP * c[i] + (1 - SKY_KEEP) * SKY_GREY[i]) * SKY_DARK[i])) for i in range(3)]
        else:
            y = 0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]
            c1 = [y + BF_SAT * (c[i] - y) for i in range(3)]
            g = [min(31, round((BF_KEEP * c1[i] + (1 - BF_KEEP) * SKY_GREY[i]) * SKY_DARK[i])) for i in range(3)]
        out.append((w & 0x8000) | rgb555(*g) & 0x7FFF)
    return out


def course_sky(rs: RomSet, entry: int) -> tuple[int, int, int, list[int]]:
    """(its bank, the window address of its backdrop colours, their count, the colours): the first block of the course's palette
    uploads, to 0x900c00 (the reverse variants use the same block: checked by the build's report)."""
    from vrtools.arcade.course import _win, course_entry_at, gfx_directory
    from vrtools.arcade.directory import decode_directory
    e = decode_directory(rs)[entry]
    ce = course_entry_at(rs, e.bank, window_base=e.header_base)
    o = _win(ce.base, gfx_directory(rs, ce)[1], "pal")
    dst, n = struct.unpack_from("<II", rs.data, o)
    if dst != SKY_DST or not 0 < n <= 512:
        raise PatchError(f"{e.name}: its first palette block goes to {dst:#x} ({n} colours), not the backdrop's {SKY_DST:#x}")
    return e.bank, 0x100000 + (o + 8 - e.bank * 0x100000), n, list(struct.unpack_from(f"<{n}H", rs.data, o + 8))


# ==================================================================================================================== the code
def _f(b: Block, op: str, src, dst: str) -> None:
    """A float instruction: src a register, ("f", x) an immediate, ("abs", a), ("disp", d, reg); dst a register."""
    if isinstance(src, str):
        b.emit(f"{op} reg,reg", src, dst)
    elif src[0] == "f":
        b.emit(f"{op} imm,reg", float(src[1]), dst)
    elif src[0] == "abs":
        b.emit(f"{op} abs,reg", src[1], dst)
    else:
        b.emit(f"{op} disp[reg],reg", src[1], src[2], dst)


def _dot(b: Block, regs, maddrs, dst: str, tmp: str, add=None) -> None:
    """dst = sum regs[i] x [maddrs[i]] (+ [add])."""
    b.emit("mov.w reg,reg", regs[0], dst)
    _f(b, "mulf.s", ("abs", maddrs[0]), dst)
    for r, a in zip(regs[1:], maddrs[1:]):
        b.emit("mov.w reg,reg", r, tmp)
        _f(b, "mulf.s", ("abs", a), tmp)
        _f(b, "addf.s", tmp, dst)
    if add is not None:
        _f(b, "addf.s", ("abs", add), dst)


def _clamp(b: Block, reg: str, lo: float, hi: float, q: str) -> None:
    _f(b, "cmpf.s", ("f", hi), reg)
    b.branch("ble", q + "a")
    _f(b, "movf.s", ("f", hi), reg)
    b.label(q + "a")
    _f(b, "cmpf.s", ("f", lo), reg)
    b.branch("bge", q + "b")
    _f(b, "movf.s", ("f", lo), reg)
    b.label(q + "b")


STATE_NAMES = ("ACTIVE XSTATE XLEFT LASTYAW RAND DTH SLV DRAWN SPDRAWN SPW PYV PZV TV G0V PXV LATEF PRIMED LANDS SPAWNS LATE TRIM_CL "
               "TRIM_SP TRIM_LCL TRIM_LSP NFRAMES REC_IN REC_OUT SPLIVE LV").split()
# SPLIVE (the join, round 2, J2): the splash slots alive (age not 0), kept exact (+1 when a spawn takes a dead slot, -1 when a
# splash ends, set at a late trip); LV: this pass's splash loop's slots processed and still alive. Appended last: storm_log.lua
# reads the words before them by index.


def cell(lay: carrier.Layout, name: str) -> int:
    """The address of one of the rain's state words (STATE_NAMES), for a module that reads it (stage 3's cover reads SLV)."""
    return lay.cell("rain", "state") + 4 * STATE_NAMES.index(name)


class Rain:
    """The rain's code for one Layout: `block()` is its Block (labels start, frame, release; the entries rand and shape).

    Stage 3: with a `cover` module in the layout (weather/cover.py) the rain consults it for every cluster after its motion (only
    when the cover's mode is not 0): a guard test, `jsr` the cover's `cluster` with R1-R3 the cluster's view position, R6 the
    cluster, R5 the list and R14 / R10 the car's ground; back R13 (0 drawn by the rain, else not drawn and no splash), R12 the
    scale cap, R1-R3 its position (stored again), R14 / R10 its drops' ground, R5. The landing reads the ground from R14 / R10
    (the car's, loaded before the loop, when no cover changes them); the loop walks the cover's `walk` clusters; no splash is
    spawned while the cover's `nosplash` is set. The entries `rand` (R0 = a float in [0, 1) from the generator; R0 only) and
    `shape` (a new shape and tilts for the cluster R6, as the rain's own placement; R0, R4, R9) are for the cover, which never
    writes the rain's cells."""

    def __init__(self, lay: carrier.Layout, k: dict, tune: RainTune, fault_spin: int = 0, fault_keep_grade: bool = False):
        self.lay, self.k, self.t = lay, k, tune
        self.fault_spin, self.fault_keep_grade = fault_spin, fault_keep_grade   # TEST-ONLY planted faults (off in every build)
        c = lambda n: lay.cell("rain", n)
        st = c("state")
        self.c = {n: st + 4 * i for i, n in enumerate(STATE_NAMES)}
        self.cover = ("cover", "state") in lay.cells     # stage 3's cover in this build
        self.CL, self.POOL = c("clusters"), c("pool")
        self.table = lay.table("rain", "drops")
        self.T0, self.TB = lay.data_at("rain", "overcast"), lay.data_at("rain", "boot")
        self.SKY, self.OWN = lay.data_at("rain", "sky"), lay.data_at("rain", "own")

    # ---- pieces
    def rnd(self, b: Block, dst: str) -> None:
        """dst = a float in [0, 1) from the LCG (R0 used)."""
        R = self.c["RAND"]
        b.emit("mov.w abs,reg", R, "r0")
        b.emit("mul.w imm,reg", 1103515245, "r0")
        b.emit("add.w imm,reg", 12345, "r0")
        b.emit("mov.w reg,abs", "r0", R)
        b.emit("shl.w imm,reg", -9, "r0")
        _f(b, "cvt.ws", "r0", dst)
        _f(b, "mulf.s", ("f", 1.0 / 8388608), dst)

    def newz(self, b: Block) -> None:
        """R3 = a new depth ZMIN + (ZFAR - ZMIN) r^2."""
        self.rnd(b, "r3")
        _f(b, "mulf.s", "r3", "r3")
        _f(b, "mulf.s", ("f", ZFAR - ZMIN), "r3")
        _f(b, "addf.s", ("f", ZMIN), "r3")

    def lim(self, b: Block, dst: str, kk: float) -> None:
        """dst = z (kk + EDGEK) + MARG (R3 = z)."""
        b.emit("mov.w reg,reg", "r3", dst)
        _f(b, "mulf.s", ("f", kk + EDGEK), dst)
        _f(b, "addf.s", ("f", MARG), dst)

    def place(self, b: Block) -> None:
        """R1, R2 across the view at depth R3; a new shape (polygon base +12, drop table offset +28, landed 0 +24) and tilts (R6)."""
        k = self.k
        self.rnd(b, "r1")
        _f(b, "mulf.s", ("f", 2.0), "r1")
        _f(b, "subf.s", ("f", 1.0), "r1")
        _f(b, "mulf.s", ("f", XEDGE), "r1")
        _f(b, "mulf.s", "r3", "r1")
        self.rnd(b, "r2")
        _f(b, "mulf.s", ("f", YTOP + YBOT), "r2")
        _f(b, "subf.s", ("f", YBOT), "r2")
        _f(b, "mulf.s", "r3", "r2")
        self.shape(b)

    def shape(self, b: Block) -> None:
        """A new shape for the cluster R6 (polygon base +12, drop table offset +28, landed 0 +24) and its tilts (+16, +20); R0, R4
        and R9 used."""
        k = self.k
        b.emit("mov.w abs,reg", self.c["RAND"], "r0")
        b.emit("shl.w imm,reg", -20, "r0")
        b.emit("and.w imm,reg", NSHAPE - 1, "r0")
        b.emit("mov.w reg,reg", "r0", "r9")
        b.emit("mul.w imm,reg", NDROP * 8, "r9")
        b.emit("mov.w reg,disp[reg]", "r9", 28, "r6")
        b.emit("mul.w imm,reg", NDROP * k["shape_words"], "r0")
        b.emit("add.w imm,reg", k["poly0"], "r0")
        b.emit("mov.w reg,disp[reg]", "r0", 12, "r6")
        b.emit("mov.w imm,disp[reg]", 0, 24, "r6")
        for off in (16, 20):
            self.rnd(b, "r4")
            _f(b, "mulf.s", ("f", 2 * TILT), "r4")
            _f(b, "subf.s", ("f", TILT), "r4")
            b.emit("mov.w reg,disp[reg]", "r4", off, "r6")

    def carbox(self, b: Block, rx: str, rz: str, inside: str, q: str) -> None:
        """To `inside` when (rx, rz) is within the car's box round its ground contact (R0 used)."""
        b.emit("mov.w reg,reg", rx, "r0")
        _f(b, "subf.s", ("abs", self.c["PXV"]), "r0")
        _f(b, "cmpf.s", ("f", CARW), "r0")
        b.branch("bge", q + "out")
        _f(b, "cmpf.s", ("f", -CARW), "r0")
        b.branch("ble", q + "out")
        b.emit("mov.w reg,reg", rz, "r0")
        _f(b, "subf.s", ("abs", self.c["PZV"]), "r0")
        _f(b, "cmpf.s", ("f", CARL), "r0")
        b.branch("bge", q + "out")
        _f(b, "cmpf.s", ("f", -CARL), "r0")
        b.branch("bgt", inside)
        b.label(q + "out")

    def setup(self, b: Block, q: str) -> None:
        """The pass's slant (SLV), the yaw's change (DTH; 0 on the rain's first visible pass) and the ground plane in view space:
        P = M (car) + t, T = tan(pitch) - m5 (clamped), G0 = P.y - P.z T (clamped)."""
        c = self.c
        b.emit("mov.w abs,reg", SPEED, "r0")
        _f(b, "cvt.ws", "r0", "r1")
        _f(b, "mulf.s", ("f", KV * KS), "r1")
        _f(b, "addf.s", ("f", S0), "r1")
        _f(b, "cmpf.s", ("f", SMAX), "r1")
        b.branch("ble", q + "s_ok")
        _f(b, "movf.s", ("f", SMAX), "r1")
        b.label(q + "s_ok")
        _f(b, "negf.s", "r1", "r1")
        b.emit("mov.w reg,abs", "r1", c["SLV"])
        b.emit("movz.hw abs,reg", YAW, "r0")
        b.emit("mov.w reg,reg", "r0", "r2")
        b.emit("sub.w abs,reg", c["LASTYAW"], "r0")
        b.emit("mov.w reg,abs", "r2", c["LASTYAW"])
        b.emit("shl.w imm,reg", 16, "r0")
        b.emit("sha.w imm,reg", -16, "r0")
        b.emit("cmp.w imm,reg", DYAW_MAX, "r0")
        b.branch("bgt", q + "ybig")
        b.emit("cmp.w imm,reg", -DYAW_MAX, "r0")
        b.branch("blt", q + "ybig")
        b.emit("cmp.w imm,abs", 0, c["ACTIVE"])
        b.branch("bne", q + "yok")
        b.label(q + "ybig")
        b.emit("mov.w imm,reg", 0, "r0")
        b.label(q + "yok")
        _f(b, "cvt.ws", "r0", "r1")
        _f(b, "mulf.s", ("f", KYAW), "r1")
        b.emit("mov.w reg,abs", "r1", c["DTH"])
        for addr, r in ((PX, "r15"), (PY, "r16"), (PZ, "r17")):
            _f(b, "movf.s", ("abs", addr), r)
        _dot(b, ("r15", "r16", "r17"), (m(1), m(4), m(7)), "r12", "r0", add=m(10))
        _dot(b, ("r15", "r16", "r17"), (m(2), m(5), m(8)), "r13", "r0", add=m(11))
        b.emit("mov.w reg,abs", "r12", c["PYV"])
        _dot(b, ("r15", "r16", "r17"), (m(0), m(3), m(6)), "r9", "r0", add=m(9))
        b.emit("mov.w reg,abs", "r9", c["PXV"])
        b.emit("mov.w reg,abs", "r13", c["PZV"])
        b.emit("movz.hw abs,reg", PITCH, "r0")
        b.emit("shl.w imm,reg", 16, "r0")
        b.emit("sha.w imm,reg", -16, "r0")
        _f(b, "cvt.ws", "r0", "r14")
        _f(b, "mulf.s", ("f", 2 * math.pi / 65536), "r14")
        _f(b, "subf.s", ("abs", m(5)), "r14")
        _clamp(b, "r14", -T_LIM, T_LIM, q + "ct")
        b.emit("mov.w reg,reg", "r13", "r0")
        _f(b, "mulf.s", "r14", "r0")
        _f(b, "subf.s", "r0", "r12")
        _clamp(b, "r12", -G0_LIM, G0_LIM, q + "cg")
        b.emit("mov.w reg,abs", "r14", c["TV"])
        b.emit("mov.w reg,abs", "r12", c["G0V"])
        b.emit("mov.w imm,abs", 0, c["LANDS"])

    def scale(self, b: Block, q: str) -> None:
        """R11 = g = max(1, z / ZG) (R3 = z); the slant column SLV g follows."""
        b.emit("mov.w reg,reg", "r3", "r11")
        _f(b, "mulf.s", ("f", 1.0 / ZG), "r11")
        _f(b, "cmpf.s", ("f", 1.0), "r11")
        b.branch("bge", q + "g_ok")
        _f(b, "movf.s", ("f", 1.0), "r11")
        b.label(q + "g_ok")

    def clusters(self, b: Block, q: str, prime: bool, late: str) -> None:
        """The cluster loop from R6 (the cluster), R7 (clusters left); prime: placed, landed without splashes, not drawn (PRIMED
        counts them); else moved, landed with splashes, drawn at R5 (the list) within the budget. To `late` once the pass is late."""
        c, k = self.c, self.k
        b.label(q + "loop")
        emit_guard_time(b, late)
        b.emit("mov.w disp[reg],reg", 0, "r6", "r1")
        b.emit("mov.w disp[reg],reg", 4, "r6", "r2")
        b.emit("mov.w disp[reg],reg", 8, "r6", "r3")
        if prime:
            self.newz(b)
            self.place(b)
            b.branch("br", q + "post")
        else:
            _f(b, "subf.s", ("f", FALL), "r2")
            _f(b, "addf.s", ("f", WIND), "r1")
            b.emit("mov.w reg,reg", "r3", "r4")
            _f(b, "mulf.s", ("abs", c["DTH"]), "r4")
            _f(b, "addf.s", "r4", "r1")
            self.lim(b, "r4", XEDGE)                    # out of a side: wrapped to the other
            _f(b, "cmpf.s", "r4", "r1")
            b.branch("ble", q + "w1")
            _f(b, "subf.s", "r4", "r1")
            _f(b, "subf.s", "r4", "r1")
            b.label(q + "w1")
            _f(b, "negf.s", "r4", "r8")
            _f(b, "cmpf.s", "r8", "r1")
            b.branch("bge", q + "w2")
            _f(b, "addf.s", "r4", "r1")
            _f(b, "addf.s", "r4", "r1")
            b.label(q + "w2")
            self.lim(b, "r4", YBOT)                     # out of the bottom: back to the top
            _f(b, "negf.s", "r4", "r4")
            _f(b, "cmpf.s", "r4", "r2")
            b.branch("bge", q + "post")
        # The relaunch and the landing loop below have no bound of their own, only the guard (each relaunch and each landing a
        # unit): the prototype's behaviour (spike 48). A cluster relaunched with all its drops already under the ground lands them
        # and is relaunched again; the most placements of one cluster in one pass seen: 2 (fix round 1, 150 s RAIN on Big Forest
        # and on Alpine: of about 3 650 cluster passes with a placement in each, 24 had a second, none a third).
        b.label(q + "relaunch")
        emit_guard_time(b, late)                        # a unit inside the cluster: a relaunch not begun keeps the old state
        self.newz(b)
        self.place(b)
        self.lim(b, "r2", YTOP)
        b.label(q + "post")
        b.emit("mov.w reg,disp[reg]", "r1", 0, "r6")
        b.emit("mov.w reg,disp[reg]", "r2", 4, "r6")
        b.emit("mov.w reg,disp[reg]", "r3", 8, "r6")
        cover = self.cover and not prime
        if cover:                                       # stage 3: the cover's word on this cluster (its mode 0: none)
            b.emit("cmp.w imm,abs", 0, cover_cell(self.lay, "MODE"))
            b.branch("be", q + "cov_skip")
            emit_guard_time(b, late)                    # the cover's work its own unit
            b.emit("mov.w abs,reg", c["G0V"], "r14")    # the car's ground in
            b.emit("mov.w abs,reg", c["TV"], "r10")
            b.emit("jsr abs", self.lay.label("cover", "cluster"))
            b.emit("mov.w reg,disp[reg]", "r1", 0, "r6")
            b.emit("mov.w reg,disp[reg]", "r2", 4, "r6")
            b.emit("mov.w reg,disp[reg]", "r3", 8, "r6")
            self.scale(b, q + "c")
            _f(b, "cmpf.s", "r12", "r11")                # the cover's scale cap (BIG: none), only after its call (fix round 1,
            b.branch("ble", q + "g_done")               # M3: a course or a pass without cover pays nothing for it, and R12 is
            _f(b, "movf.s", "r12", "r11")               # never read where the cover did not set it)
            b.branch("br", q + "g_done")
            b.label(q + "cov_skip")
        self.scale(b, q)
        if cover:
            b.label(q + "g_done")
        b.emit("mov.w abs,reg", c["SLV"], "r4")
        _f(b, "mulf.s", "r11", "r4")
        b.label(q + "land")                             # the next-lowest drop's bottom against the ground plane
        emit_guard_time(b, late)                        # each landing a unit (the drops landed so far stay counted)
        b.emit("mov.w disp[reg],reg", 24, "r6", "r8")
        b.emit("cmp.w imm,reg", NDROP, "r8")
        b.branch("bge", q + "relaunch")
        b.emit("mov.w reg,reg", "r8", "r0")
        b.emit("shl.w imm,reg", 3, "r0")
        b.emit("add.w disp[reg],reg", 28, "r6", "r0")
        b.emit("add.w imm,reg", self.table, "r0")
        _f(b, "movf.s", ("disp", 0, "r0"), "r15")       # cx
        _f(b, "movf.s", ("disp", 4, "r0"), "r16")       # the drop's bottom
        b.emit("mov.w reg,reg", "r16", "r17")
        _f(b, "mulf.s", "r11", "r17")
        _f(b, "addf.s", "r2", "r17")                    # yd
        b.emit("mov.w reg,reg", "r15", "r18")
        _f(b, "mulf.s", ("disp", 16, "r6"), "r18")
        _f(b, "addf.s", "r3", "r18")                    # zd
        b.emit("mov.w reg,reg", "r18", "r19")
        _f(b, "mulf.s", "r10", "r19")
        _f(b, "addf.s", "r14", "r19")                   # yg (the ground: R14 / R10, the car's unless the cover gave another)
        _f(b, "cmpf.s", "r19", "r17")
        b.branch("bgt", q + "landed_done")
        b.emit("add.w imm,disp[reg]", 1, 24, "r6")
        b.emit("add.w imm,abs", 1, c["LANDS"])
        if prime:                                       # placed under the ground: gone, no splash
            b.branch("br", q + "land")
        else:
            _f(b, "cmpf.s", ("f", self.t.splash_range), "r18")
            b.branch("bgt", q + "land")
            _f(b, "cmpf.s", ("f", ZDRAW), "r18")
            b.branch("blt", q + "land")
            b.emit("mov.w reg,reg", "r15", "r20")
            _f(b, "mulf.s", "r11", "r20")
            b.emit("mov.w reg,reg", "r16", "r9")
            _f(b, "mulf.s", "r4", "r9")
            _f(b, "addf.s", "r9", "r20")
            _f(b, "addf.s", "r1", "r20")                # xd
            _f(b, "cmpf.s", ("f", LAT), "r20")
            b.branch("bgt", q + "land")
            _f(b, "cmpf.s", ("f", -LAT), "r20")
            b.branch("blt", q + "land")
            self.carbox(b, "r20", "r18", q + "land", q + "cb1")
            b.emit("cmp.w imm,abs", 0, c["LATEF"])      # no new splash for LATE_HOLD passes after a late one
            b.branch("bne", q + "land")
            if cover:                                   # nor for a cluster the cover took, nor under the pits roof's curtain
                b.emit("cmp.w imm,reg", 0, "r13")
                b.branch("bne", q + "land")
                b.emit("cmp.w imm,abs", 0, cover_cell(self.lay, "NOSPLASH"))
                b.branch("bne", q + "land")
            emit_guard_time(b, late)                    # the spawn its own unit (a late landing leaves no splash)
            b.emit("mov.w abs,reg", c["SPW"], "r0")     # spawn: W = M^T (v - t) into the ring's next entry
            b.emit("shl.w imm,reg", 4, "r0")
            b.emit("add.w imm,reg", self.POOL, "r0")
            _f(b, "subf.s", ("abs", m(9)), "r20")
            _f(b, "subf.s", ("abs", m(10)), "r19")
            _f(b, "subf.s", ("abs", m(11)), "r18")
            for kk in range(3):
                _dot(b, ("r20", "r19", "r18"), (m(3 * kk), m(3 * kk + 1), m(3 * kk + 2)), "r9", "r15")
                b.emit("mov.w reg,disp[reg]", "r9", 4 * kk, "r0")
            b.emit("cmp.w imm,disp[reg]", 0, 12, "r0")    # the ring's slot dead: one more alive (J2's live count)
            b.branch("bne", q + "sp_was_live")
            b.emit("add.w imm,abs", 1, c["SPLIVE"])
            b.label(q + "sp_was_live")
            b.emit("mov.w imm,disp[reg]", 1, 12, "r0")
            b.emit("add.w imm,abs", 1, c["SPAWNS"])
            b.emit("mov.w abs,reg", c["SPW"], "r0")
            b.emit("add.w imm,reg", 1, "r0")
            b.emit("cmp.w imm,reg", NSP, "r0")
            b.branch("blt", q + "spw_ok")
            b.emit("mov.w imm,reg", 0, "r0")
            b.label(q + "spw_ok")
            b.emit("mov.w reg,abs", "r0", c["SPW"])
            b.branch("br", q + "land")
        b.label(q + "landed_done")
        if prime:
            b.emit("add.w imm,abs", 1, c["PRIMED"])
        else:                                           # the budget, then the cluster (variant k: records - 7k, polygon + k stride)
            if cover:
                b.emit("cmp.w imm,reg", 0, "r13")       # the cover hid it (or drew it drop by drop)
                b.branch("bne", q + "next")
            b.emit("mov.w disp[reg],reg", 24, "r6", "r8")
            b.emit("mov.w reg,reg", "r8", "r9")
            b.emit("mul.w imm,reg", 7, "r9")
            b.emit("mov.w abs,reg", REC_COUNT, "r0")
            b.emit("add.w imm,reg", k["records"], "r0")
            b.emit("sub.w reg,reg", "r9", "r0")
            b.emit("cmp.w abs,reg", BUDGET, "r0")
            b.branch("bgt", q + "trim")
            b.emit("mov.w reg,abs", "r0", REC_COUNT)
            b.emit("add.w imm,abs", 1, c["DRAWN"])
            b.emit("mov.w imm,disp[reg]", 0xB, 0, "r5")  # the matrix: x (g, 0, tilt), y (SLV g, g, 0), z (0, 0, g), t (x, y, z)
            b.emit("mov.w reg,disp[reg]", "r11", 4, "r5")
            b.emit("mov.w imm,disp[reg]", 0, 8, "r5")
            b.emit("mov.w disp[reg],disp[reg]", 16, "r6", 12, "r5")
            b.emit("mov.w reg,disp[reg]", "r4", 16, "r5")
            b.emit("mov.w reg,disp[reg]", "r11", 20, "r5")
            for off in (24, 28, 32):
                b.emit("mov.w imm,disp[reg]", 0, off, "r5")
            b.emit("mov.w reg,disp[reg]", "r11", 36, "r5")
            b.emit("mov.w reg,disp[reg]", "r1", 40, "r5")
            b.emit("mov.w reg,disp[reg]", "r2", 44, "r5")
            b.emit("mov.w reg,disp[reg]", "r3", 48, "r5")
            b.emit("mov.w imm,disp[reg]", 1, 52, "r5")
            b.emit("mov.w imm,disp[reg]", k["tex"], 56, "r5")
            b.emit("mul.w imm,reg", k["shape_words"], "r8")
            b.emit("add.w disp[reg],reg", 12, "r6", "r8")
            b.emit("mov.w reg,disp[reg]", "r8", 60, "r5")
            b.emit("mov.w abs,disp[reg]", BUDGET, 64, "r5")
            b.emit("add.w imm,reg", 68, "r5")
            b.branch("br", q + "next")
            b.label(q + "trim")
            b.emit("add.w imm,abs", 1, c["TRIM_CL"])
        b.label(q + "next")
        b.emit("add.w imm,reg", 32, "r6")
        b.emit("sub.w imm,reg", 1, "r7")
        b.emit("cmp.w imm,reg", 0, "r7")
        b.branch("bne", q + "loop")

    def splashes(self, b: Block, done: str) -> None:
        """The splash loop (after the clusters: the guards trim it first), then to `done`."""
        c, k = self.c, self.k
        frames = self.t.splash_frames
        b.emit("mov.w imm,abs", 0, c["SPDRAWN"])
        b.emit("mov.w imm,abs", 0, c["LV"])
        b.emit("mov.w imm,reg", self.POOL, "r6")
        b.emit("mov.w imm,reg", 0, "r8")
        b.label("sloop")
        emit_guard_time(b, "slate")
        b.emit("mov.w disp[reg],reg", 12, "r6", "r9")
        b.emit("cmp.w imm,reg", 0, "r9")
        b.branch("be", "snext")
        _f(b, "movf.s", ("disp", 0, "r6"), "r15")
        _f(b, "movf.s", ("disp", 4, "r6"), "r16")
        _f(b, "movf.s", ("disp", 8, "r6"), "r17")
        _dot(b, ("r15", "r16", "r17"), (m(0), m(3), m(6)), "r1", "r0", add=m(9))
        _dot(b, ("r15", "r16", "r17"), (m(1), m(4), m(7)), "r2", "r0", add=m(10))
        _dot(b, ("r15", "r16", "r17"), (m(2), m(5), m(8)), "r3", "r0", add=m(11))
        if self.fault_spin:                             # TEST ONLY: a long splash unit (tests/test_weather_rain.py, VR_STORM_FAULT_SPIN)
            b.emit("push reg", "r20")
            b.emit("mov.w imm,reg", self.fault_spin, "r20")
            b.label("fault_spin")
            b.emit("sub.w imm,reg", 1, "r20")
            b.branch("bne", "fault_spin")
            b.emit("pop reg", "r20")
        emit_guard_time(b, "slate")                     # the transform and the drawing two units (a late splash is ended)
        _f(b, "cmpf.s", ("f", ZDRAW), "r3")
        b.branch("blt", "sage")
        self.carbox(b, "r1", "r3", "sage", "cb2")
        b.emit("mov.w reg,reg", "r3", "r11")
        _f(b, "mulf.s", ("f", 1.0 / ZSG), "r11")
        _f(b, "cmpf.s", ("f", 1.0), "r11")
        b.branch("bge", "gs_ok")
        _f(b, "movf.s", ("f", 1.0), "r11")
        b.label("gs_ok")
        b.emit("mov.w abs,reg", REC_COUNT, "r0")
        b.emit("add.w imm,reg", SREC, "r0")
        b.emit("cmp.w abs,reg", BUDGET, "r0")
        b.branch("bgt", "strim")
        b.emit("mov.w reg,abs", "r0", REC_COUNT)
        b.emit("add.w imm,abs", 1, c["SPDRAWN"])
        b.emit("mov.w imm,disp[reg]", 0xB, 0, "r5")      # x (+-gs, 0, 0), y (0, gs, 0), z (0, T gs, gs): sheared onto the ground
        b.emit("mov.w reg,reg", "r11", "r0")
        b.emit("mov.w reg,reg", "r8", "r12")
        b.emit("and.w imm,reg", 2, "r12")
        b.emit("cmp.w imm,reg", 0, "r12")
        b.branch("be", "noflip")
        _f(b, "negf.s", "r0", "r0")
        b.label("noflip")
        b.emit("mov.w reg,disp[reg]", "r0", 4, "r5")
        for off in (8, 12, 16):
            b.emit("mov.w imm,disp[reg]", 0, off, "r5")
        b.emit("mov.w reg,disp[reg]", "r11", 20, "r5")
        for off in (24, 28):
            b.emit("mov.w imm,disp[reg]", 0, off, "r5")
        b.emit("mov.w reg,reg", "r11", "r0")
        _f(b, "mulf.s", ("abs", c["TV"]), "r0")
        b.emit("mov.w reg,disp[reg]", "r0", 32, "r5")
        b.emit("mov.w reg,disp[reg]", "r11", 36, "r5")
        b.emit("mov.w reg,disp[reg]", "r1", 40, "r5")
        b.emit("mov.w reg,disp[reg]", "r2", 44, "r5")
        b.emit("mov.w reg,disp[reg]", "r3", 48, "r5")
        b.emit("mov.w imm,disp[reg]", 1, 52, "r5")
        b.emit("mov.w reg,reg", "r9", "r0")             # colours: two words a stage
        b.emit("sub.w imm,reg", 1, "r0")
        b.emit("shl.w imm,reg", 1, "r0")
        b.emit("add.w imm,reg", k["sp_tex"], "r0")
        b.emit("mov.w reg,disp[reg]", "r0", 56, "r5")
        b.emit("mov.w reg,reg", "r8", "r0")             # object: layout (index & 1) x frames + age - 1
        b.emit("and.w imm,reg", 1, "r0")
        b.emit("mul.w imm,reg", frames, "r0")
        b.emit("add.w reg,reg", "r9", "r0")
        b.emit("sub.w imm,reg", 1, "r0")
        b.emit("mul.w imm,reg", k["sp_words"], "r0")
        b.emit("add.w imm,reg", k["sp_poly"], "r0")
        b.emit("mov.w reg,disp[reg]", "r0", 60, "r5")
        b.emit("mov.w abs,disp[reg]", BUDGET, 64, "r5")
        b.emit("add.w imm,reg", 68, "r5")
        b.branch("br", "sage")
        b.label("strim")
        b.emit("add.w imm,abs", 1, c["TRIM_SP"])
        b.label("sage")
        b.emit("add.w imm,reg", 1, "r9")
        b.emit("cmp.w imm,reg", frames, "r9")
        b.branch("ble", "sage_ok")
        b.emit("mov.w imm,reg", 0, "r9")                # the splash ends: one less alive
        b.emit("sub.w imm,abs", 1, c["SPLIVE"])
        b.branch("br", "sage_st")
        b.label("sage_ok")
        b.emit("add.w imm,abs", 1, c["LV"])
        b.label("sage_st")
        b.emit("mov.w reg,disp[reg]", "r9", 12, "r6")
        b.label("snext")
        b.emit("add.w imm,reg", 16, "r6")
        b.emit("add.w imm,reg", 1, "r8")
        b.emit("cmp.w imm,reg", NSP, "r8")
        b.branch("blt", "sloop")
        b.emit("cmp.w imm,abs", 0, c["LATEF"])          # an on-time pass: one less to hold
        b.branch("be", done)
        b.emit("sub.w imm,abs", 1, c["LATEF"])
        b.branch("br", done)
        b.label("slate")                                # late in the splash loop: the rest end now (shortened, none blinks)
        b.emit("add.w imm,abs", 1, c["LATE"])
        b.emit("mov.w imm,abs", LATE_HOLD, c["LATEF"])
        # J2 (the join, round 2): the slots from R8 on, alive or not, are dead from this pass on, as the visiting loop made them,
        # in constant time: the late trims are the alive ones among them, SPLIVE less this pass's alive ones before R8 (LV); then
        # every remaining slot is cleared whole by one string fill (a dead slot's other words are never read)
        b.emit("mov.w abs,reg", c["SPLIVE"], "r0")
        b.emit("sub.w abs,reg", c["LV"], "r0")
        b.emit("add.w reg,abs", "r0", c["TRIM_LSP"])
        b.emit("mov.w abs,abs", c["LV"], c["SPLIVE"])
        b.emit("mov.w imm,reg", NSP, "r3")
        b.emit("sub.w reg,reg", "r8", "r3")
        b.emit("shl.w imm,reg", 3, "r3")                # halfwords: 8 a slot
        b.emit("mov.w imm,reg", 0, "r26")               # movcfu.h's fill: R26's half
        b.emit("movcfu.h [reg],imm,[reg],reg", "r6", 0, "r6", "r3")
        b.branch("br", done)

    def copy_table(self, b: Block, src: int, q: str) -> None:
        """The colour RAM's 96 rows from the table at `src` (rows 128 bytes apart; the RAM's 0x200)."""
        b.emit("mov.w imm,reg", src, "r0")
        b.emit("mov.w imm,reg", XLAT, "r1")
        b.emit("mov.w imm,reg", ROWS, "r5")
        b.label(q)
        emit_copy(b, "r0", "r1", ROW_ENTRIES)
        b.emit("add.w imm,reg", 2 * ROW_ENTRIES, "r0")
        b.emit("add.w imm,reg", ROW_STRIDE, "r1")
        b.emit("sub.w imm,reg", 1, "r5")
        b.emit("cmp.w imm,reg", 0, "r5")
        b.branch("bne", q)

    def grade(self, b: Block) -> None:
        """GRADE_ROWS rows of the overcast table into the colour RAM, in the prototype's order (row r: channel r % 3, value
        r / 3), each after the guard."""
        c = self.c
        b.emit("mov.w imm,reg", GRADE_ROWS, "r5")
        b.label("grow")
        emit_guard_time(b, "gdone")
        b.emit("cmp.w imm,abs", 0, c["XLEFT"])
        b.branch("be", "gdone")
        b.emit("mov.w imm,reg", ROWS, "r4")
        b.emit("sub.w abs,reg", c["XLEFT"], "r4")       # the row 0..95
        b.emit("sub.w imm,abs", 1, c["XLEFT"])
        b.emit("mov.w reg,reg", "r4", "r6")
        b.emit("mul.w imm,reg", 43, "r6")
        b.emit("shl.w imm,reg", -7, "r6")               # c = row / 3 (exact for 0..95)
        b.emit("mov.w reg,reg", "r6", "r2")
        b.emit("mul.w imm,reg", 3, "r2")
        b.emit("sub.w reg,reg", "r2", "r4")             # channel = row - 3 c
        b.emit("mov.w reg,reg", "r4", "r0")
        b.emit("shl.w imm,reg", 5, "r0")
        b.emit("add.w reg,reg", "r6", "r0")
        b.emit("mul.w imm,reg", 2 * ROW_ENTRIES, "r0")
        b.emit("add.w imm,reg", self.T0, "r0")          # the table's row
        b.emit("mov.w reg,reg", "r4", "r1")
        b.emit("shl.w imm,reg", 14, "r1")
        b.emit("shl.w imm,reg", 9, "r6")
        b.emit("add.w reg,reg", "r6", "r1")
        b.emit("add.w imm,reg", XLAT, "r1")             # the colour RAM's row
        emit_copy(b, "r0", "r1", ROW_ENTRIES)
        b.emit("sub.w imm,reg", 1, "r5")
        b.emit("cmp.w imm,reg", 0, "r5")
        b.branch("bne", "grow")
        b.label("gdone")

    # ---- the module's routines
    def block(self) -> Block:
        c = self.c
        b = Block(self.lay.code("rain"))
        # start: called in the carrier's STARTING passes; places START_QUOTA clusters at most (the guard the backstop); R0 = 0 once
        # every cluster is placed, else 1
        b.label("start")
        self.setup(b, "st_")
        b.emit("mov.w abs,reg", c["PRIMED"], "r7")
        b.emit("mov.w reg,reg", "r7", "r6")
        b.emit("shl.w imm,reg", 5, "r6")
        b.emit("add.w imm,reg", self.CL, "r6")
        b.emit("mul.w imm,reg", -1, "r7")
        b.emit("add.w imm,reg", self.t.clusters, "r7")   # clusters left to place
        b.emit("cmp.w imm,reg", 0, "r7")
        b.branch("be", "st_done")
        b.emit("cmp.w imm,reg", START_QUOTA, "r7")
        b.branch("ble", "st_quota")
        b.emit("mov.w imm,reg", START_QUOTA, "r7")      # this pass's quota
        b.label("st_quota")
        b.emit("mov.w abs,reg", c["G0V"], "r14")        # the landing's ground: the car's
        b.emit("mov.w abs,reg", c["TV"], "r10")
        self.clusters(b, "p_", prime=True, late="st_late")
        b.label("st_done")
        b.emit("cmp.w imm,abs", self.t.clusters, c["PRIMED"])
        b.branch("bne", "st_late")
        b.emit("mov.w imm,reg", 0, "r0")
        b.emit("rsr")
        b.label("st_late")
        b.emit("mov.w imm,reg", 1, "r0")
        b.emit("rsr")
        # frame: a rain pass (the carrier's SHOW state)
        b.label("frame")
        b.emit("add.w imm,abs", 1, c["NFRAMES"])
        self.setup(b, "fr_")
        b.emit("cmp.w imm,abs", 0, c["ACTIVE"])
        b.branch("bne", "fr_on")
        b.emit("mov.w imm,abs", 1, c["ACTIVE"])          # the first visible pass: the grey sky in, the grade starts
        b.emit("mov.w imm,reg", self.SKY + 8, "r0")
        b.emit("mov.w abs,reg", self.SKY, "r1")
        b.emit("mov.w abs,reg", self.SKY + 4, "r3")
        emit_copy(b, "r0", "r1", "r3")
        b.emit("mov.w imm,abs", 1, c["XSTATE"])
        b.emit("mov.w imm,abs", ROWS, c["XLEFT"])
        b.label("fr_on")
        b.emit("mov.w abs,reg", LIST_PTR, "r5")
        b.emit("mov.w imm,reg", self.CL, "r6")
        if self.cover:                                  # stage 3: the clusters the cover lets the rain walk (60; 24 under the pits
            b.emit("mov.w abs,reg", cover_cell(self.lay, "WALK"), "r7")    # roof's curtain: the others keep their state)
            b.emit("mov.w imm,reg", F(1.0e9), "r12")    # no cover on a cluster: no cap, drawn by the rain
            b.emit("mov.w imm,reg", 0, "r13")
        else:
            b.emit("mov.w imm,reg", self.t.clusters, "r7")
        b.emit("mov.w abs,reg", c["G0V"], "r14")        # the landing's ground: the car's
        b.emit("mov.w abs,reg", c["TV"], "r10")
        b.emit("mov.w imm,abs", 0, c["DRAWN"])
        b.emit("mov.w abs,abs", REC_COUNT, c["REC_IN"])
        self.clusters(b, "c_", prime=False, late="late")
        self.splashes(b, "listout")
        b.label("late")                                 # late: the clusters not reached keep their state, not drawn
        b.emit("add.w imm,abs", 1, c["LATE"])
        b.emit("mov.w imm,abs", LATE_HOLD, c["LATEF"])
        b.emit("add.w reg,abs", "r7", c["TRIM_LCL"])
        b.label("listout")
        b.emit("mov.w reg,abs", "r5", LIST_PTR)
        b.emit("mov.w abs,abs", REC_COUNT, c["REC_OUT"])
        self.grade(b)
        b.emit("rsr")
        # the entries the cover calls: rand (R0 a float in [0, 1)), shape (a new shape and tilts for the cluster R6)
        b.label("rand")
        self.rnd(b, "r0")
        b.emit("rsr")
        b.label("shape")
        self.shape(b)
        b.emit("rsr")
        # release: the boot's colour table back in one copy, the course's own sky back when palette RAM still holds our grey
        b.label("release")
        b.emit("cmp.w imm,abs", 0, c["XSTATE"])
        b.branch("be", "rl_sky")
        if not self.fault_keep_grade:                   # TEST ONLY when set: the grade left in the colour RAM (VR_STORM_FAULT_KEEP_GRADE)
            self.copy_table(b, self.TB, "rl_row")
        b.emit("mov.w imm,abs", 0, c["XSTATE"])
        b.emit("mov.w imm,abs", 0, c["XLEFT"])
        b.label("rl_sky")
        b.emit("cmp.w imm,abs", 0, c["ACTIVE"])
        b.branch("be", "rl_done")
        b.emit("mov.w imm,abs", 0, c["ACTIVE"])
        b.emit("mov.w abs,reg", self.SKY, "r1")
        for kk in SKY_COMPARE:
            b.emit("movz.hw disp[reg],reg", 2 * kk, "r1", "r2")
            b.emit("movz.hw abs,reg", self.SKY + 8 + 2 * kk, "r4")
            b.emit("cmp.w reg,reg", "r2", "r4")
            b.branch("bne", "rl_done")                  # the game has written its own palette since: left as it is
        b.emit("mov.w imm,reg", self.OWN, "r0")
        b.emit("mov.w abs,reg", self.SKY + 4, "r3")
        emit_copy(b, "r0", "r1", "r3")
        b.label("rl_done")
        b.emit("rsr")
        return b


def cells(tune: RainTune) -> tuple[tuple[str, int], ...]:
    return (("state", 0x80), ("clusters", 32 * tune.clusters), ("pool", 16 * NSP))


def module(rs: RomSet, tune: RainTune, fault_spin: int = 0, fault_keep_grade: bool = False) -> carrier.Module:
    """The rain as a carrier module: its code, cells, the drop table (image), the overcast and boot tables (data), each course's
    grey sky (course data: dst, count, colours) and own sky (a copy from the course's bank), its polygon objects and colour words.
    `fault_spin` is for one test only (the planted fault that shows tests/test_weather_rain.py's bound on the time after the vblank
    count's move failing): that many turns of a two-instruction loop in every splash's transform unit; 0 (no code) in every build.
    `fault_keep_grade` likewise (the planted fault that shows test_nothing_of_the_storm_shows_after_its_modes failing): the release
    leaves the grade in the colour RAM; False in every build."""
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.weather import layout
    objs, size, records, faces, table = drop_objects()
    sobjs = splash_objects(tune.splash_frames)
    ssize = len(sobjs[0])
    if any(len(o) != ssize for o in sobjs):
        raise PatchError("the splash objects are not one size")
    drops, sp = colour_words(rs, faces, tune.splash_frames)
    poly = layout.block("rain objects").start
    colours = layout.block("rain colours").start
    k = {"poly0": poly // 4, "shape_words": size // 4, "records": records, "sp_poly": (poly + len(objs) * size) // 4,
         "sp_words": ssize // 4, "tex": 0x40000 + (colours - V60_PROGRAM) // 2}
    k["sp_tex"] = k["tex"] + len(drops)
    skies = {e: course_sky(rs, e) for e in range(len(decode_directory(rs)))}

    def course_data(e):
        bank, src, n, cols = skies[e]
        grey = grey_sky(cols, e == METROPOLIS)
        return {"sky": struct.pack("<II", SKY_DST, n) + struct.pack(f"<{n}H", *grey)}

    def course_copies(e):
        bank, src, n, cols = skies[e]
        return {"own": (bank, src, 2 * n)}
    return carrier.Module(
        name="rain", code=lambda lay: Rain(lay, k, tune, fault_spin, fault_keep_grade).block(), cells=cells(tune), tables=(("drops", table),),
        data=(("overcast", table_bytes(overcast_table())), ("boot", table_bytes(boot_table()))),
        course_data=course_data, course_copies=course_copies,
        rom=(("rain objects", b"".join(objs) + b"".join(sobjs)), ("rain colours", struct.pack(f"<{len(drops) + len(sp)}H", *drops, *sp))),
        start="start", frame="frame", release="release", entries=("rand", "shape"))
