"""Weather stage 4: lightning, as the owner approved it (spec 5.5): a strike every 20-40 s of race at random; a 3D bolt of thin rods
(a main channel from the sky to the ground and 2-4 branches in depth, yellowish-white, warm pale yellow and darker gold faces, a
soft glow) struck 300-800 units from the car beside the course and fixed in the world; a strike of about 1 s that re-strikes (the
bolt alone, then a sky flash with a one-frame white-out of the picture, the bolt glowing, dark, one or two more strokes with a
smaller sky flash and no white-out, a dim flicker to end); never more than three full-screen flash onsets in any second; under cover
no bolt and no white-out, the sky flash kept. A module of the storm's carrier (weather/carrier.py: its RAM contract), registered
BEFORE the rain: its bolt is drawn first and so is served first by both guards (the rain is trimmed for it, never it for the rain;
the session lead's ruling of 19 Nov 2026 on the design's "The strike's objects are drawn before the rain and have priority over it in
both guards").

Pascal's path to it (17-18 Nov 2026): "a lightning effect also in 3d that pop sometime and kind of white the screen so it makes it
hard for the driver", the flash strength "B" (a sky flash and a brief white-out); "could it be a 3d lughtning?", placement "B" (beside
the course, 300-800 units away); "maybe it should bling in and out couple of time?", the white-out on the first stroke only: "A";
"i think the lightning might need to be a bit narrower"; of the strokes 45 % thinner, "this is it, 45 is great keep it".

Ported (rewritten from the listings, the values unchanged) from spike 60/62 (`spike/p60_lightning.py` at b918448, the "thin" tune:
the bolt objects, the glow, the far thickening, the six timelines, the safety rule, the placement with its height and occluder
grids, the in-view check) as spike 70 joined it (`spike/p70_storm.py`: the grids in int8, the bolts packed with a pointer table, the
flash skies made from the course's grey sky, no bolt and no wash under cover, the sky put back only when palette RAM still holds
ours). Differences, each from a rule of the carrier (the stage plan, docs/superpowers/plans/2026-11-18-weather-stage-4-lightning.md):
  - the placement search (up to NTRY tries of LOS_K sight-line samples: the prototype ran it whole in the strike's first pass) is
    PLACE_QUOTA tries a pass, each try one unit after the guard; the strike's timeline starts on the pass the search ends (a few
    passes later than in the prototype at most);
  - the white-out's colour-RAM switch (96 rows) and its restore are units of XLAT_UNIT rows each after the guard; a white-out whose
    first unit finds the pass late is not shown (the prototype's rule); one cut after its first unit shows the rows written (the
    brightest values first) and is restored from the next pass;
  - the sky's palette write waits for the guard too (a late pass keeps the sky as it is and the next pass writes it);
  - the strike has its own random generator, seeded at the first race frame from the rain's and the wheel's words (the prototype
    stirred the rain's own generator);
  - the grids are cropped to each course's box of cells that hold anything (lossless); a sight-line sample outside the 128 x 128
    grid reads "nothing there" (the prototype read past the grid's end there);
  - no valid foot in 16 tries: no strike (counted, NFALL; the next strike scheduled as after any other). The prototype struck on
    the player's ground at the place its registers still held: the last try that passed the view check, whose foot cell the grid had
    refused (within 48 units of the centreline or beside tall geometry), or garbage when no try passed it (fix round 1, F1);
  - the white-out's 96 rows go brightest value first (the prototype's channel-major order: the same table when whole).

A pass (the carrier's SHOW state, before the rain's): the scheduler (idle: in the race with the rain's grade complete, the countdown
to the next strike; then the placement, PLACE_QUOTA tries a pass; then the timeline, a level a pass from one of the six patterns,
each flash onset allowed only when the last three are ONSET_WINDOW logic frames old, else the strike ends there), then the level
applied: the sky's palette slot (the rain's grey or one of three flash skies), the colour RAM toward the white-out or back to the
overcast table, then the bolt (within the frame's record budget: a pass whose own lists leave less room than BOLT_RECORDS draws no
bolt; the game's lists are never trimmed, the storm runs after them). The level ends the strike's effects outside the race at once
(the release then has nothing to put back in the game's flow; it still puts the course's own sky back when palette RAM holds a flash
sky of ours).

The cells other modules read (the interface of 19 Nov 2026, as amended by the session lead in fix round 1): `strike_seq` (a word,
up by one on the first pass of every strike that happens, its timeline's first pass) and `strike_band` (a word, 1 close, 2 medium, 3
distant by the strike's distance against BANDS, set on that same pass and HELD unchanged until the first pass of the next strike that
happens: never cleared, not at the strike's end, not by a re-strike, not by an aborted attempt; a strike under cover happens, so it
sets both). Both 0 at each load (the carrier zeroes the module cells); both read correctly as a byte or a halfword at their address.
The sound tests its guard first and may read the band a pass or more later: the hold is for it. v0.4.1: the rain reads `LEVEL` (a
word of `state`: this pass's level, written on every pass at `apply` before the rain runs; 0 at the load) for its lit rain, a flash
where FLASH_OF_LEVEL is not 0 (weather/rain.py's table `lit`; carrier.READ_AFTER_WRITE: the lightning before the rain). It reads `under_cover` (the module `cover`'s byte: 1 on a pass whose
camera is under cover) and, by name, the rain's state cells (its grade's progress, its random word), its grey sky, the course's own
sky and its overcast table."""
from __future__ import annotations

import math
import random
import struct

import numpy as np

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_PROGRAM, RomSet
from vrtools.arcade.v60asm import Block
from vrtools.arcade.weather import carrier
from vrtools.arcade.weather.carrier import BUDGET, LIST_PTR, MODE, REC_COUNT, XLAT, emit_copy, emit_guard_time
from vrtools.arcade.weather.tune import AIM_DEFAULT, LightningTune

# ---- the game's cells ----------------------------------------------------------------------------------------------------------
PLAYER = 0x400D00
SPEED = PLAYER + 0x14
PX, PY, PZ = PLAYER + 0x1E, PLAYER + 0x22, PLAYER + 0x26
ROADPT = PLAYER + 0xA6                  # the player's road point (halfword)
CAM = 0x501B00                          # the camera matrix: 12 floats, the 3 x 3 column-major, then the translation
LINES_PTR = 0x501960                    # the course's line table (line 0 the centreline: x, z, heading, link; 16 bytes a point)
WHEEL = (0x501060, 0x501064, 0x501068, 0x50106C)   # the wheel's input words, mixed into the seed at the first race frame
RACE = 0x14                             # the race mode: strikes are scheduled and run only in it


def m(k: int) -> int:
    return CAM + 4 * k


# ---- the timelines and the rule (spike 60) ---------------------------------------------------------------------------------------
FPS = 28.76                             # logic frames a second (2 vblanks)
ONSET_WINDOW = 30                       # logic frames (1.04 s): an onset only when the last `max_onsets_per_s` are this old
PAT_LEN = 40
# levels: 0 off; 1 bolt + sky lit (k 0.40); 2 bolt + sky bright (0.80); 4 white-out + sky 0.95; 5 the bolt alone; 6 the bolt alone,
# dim colours (3, spike 51's half wash, is in no pattern: not built). The white-out (4) only in the first stroke; later strokes the
# smaller sky flash (1); the bolt off (0) between the strokes; a dim flicker (6) to end.
PATTERNS = (
    (5, 5, 5, 5) + (4, 2) + (5,) * 6 + (0,) * 3 + (1, 1) + (5,) * 6 + (0,) * 3 + (6, 6, 0, 6),                        # 2 strokes, 30
    (5, 5, 5) + (2, 4) + (5,) * 5 + (0,) * 3 + (1,) + (5,) * 7 + (0,) * 2 + (6, 0, 6, 6),                             # 2 strokes, 27
    (5, 5, 5, 5) + (4, 2) + (5,) * 4 + (0,) * 3 + (1,) + (5,) * 5 + (0,) * 2 + (1,) + (5,) * 3 + (0,) * 3 + (6, 0, 6),   # 3, 31
    (5, 5, 5) + (4, 1) + (5,) * 5 + (0,) * 2 + (1, 1) + (5,) * 4 + (0,) * 3 + (1,) + (5,) * 4 + (0,) * 2 + (6, 6, 0, 6),  # 3, 32
    (5, 5, 5, 5) + (4, 2, 1) + (5,) * 5 + (0,) * 3 + (1,) + (5,) * 5 + (0,) * 3 + (6, 6),                             # 2 strokes, 26
    (5, 5, 5, 5) + (2, 4) + (5,) * 5 + (0,) * 3 + (1,) + (5,) * 4 + (0,) * 2 + (1, 1) + (5,) * 3 + (0,) * 3 + (6, 0, 6),  # 3, 32
)
LEVELS = 7
FLASH_OF_LEVEL = (0, 1, 2, 3, 4, 0, 0)  # the level the safety rule sees (the bolt alone, 5 / 6, is no flash)
SKY_OF_LEVEL = (0, 1, 2, 2, 3, 0, 0)    # the sky's slot per level: 0 the rain's grey, 1..3 the flash skies
WHITEOUT_LEVEL = 4
DIM_LEVEL = 6
SKY_K = (0.40, 0.80, 0.95)              # the flash skies: the grey sky blended toward SKY_WHITE by these
SKY_WHITE = (31.0, 30.0, 28.0)          # a very slightly warm white (spike 53)
WHITEOUT_K = 0.85                       # the white-out: the overcast table's output blended toward 255 (spike 51's WASH_K[2])
BANDS = (467.0, 633.0)                  # strike_band 1 under the first, 2 under the second, 3 beyond (spec 5.6)
# ---- the bolt (spike 56/60/62) ---------------------------------------------------------------------------------------------------
NSH3, BOLT_SEED = 6, 56                 # shapes, each also built mirrored (objects 0..5 as built, 6..11 mirrored)
R_MAIN0 = 0.012                         # spike 56's rod radius (local units; the bolt is 1 tall): times the tune's stroke_scale
PROFILE = ((-0.866, 0.5), (-0.30, -0.80), (0.30, -0.80), (0.866, 0.5))     # x right, z away from the camera; faces L, H, R
FACES = ("L", "H", "R")
BOLT_COLOURS = {"G": (27, 24, 18), "L": (31, 30, 21), "H": (31, 31, 26), "R": (24, 21, 12),
                "Gd": (20, 15, 12), "Ld": (22, 21, 16), "Hd": (29, 28, 23), "Rd": (16, 14, 10)}   # shown under the grade
TEX_ORDER = ("G", "L", "H", "R", "Gd", "Ld", "Hd", "Rd")
GLOW_W, GLOW_Z = 2.3, 1.6               # the glow strip's half-width and its distance behind the rod, in rod radii
KH_D0, KH_MAX, KH_SPAN = 420.0, 1.30, 360.0   # far bolts thicker: 1 + KH1 (d - KH_D0), 1 .. KH_MAX (spike 62, "thin")
KH1 = (KH_MAX - 1.0) / KH_SPAN
BOLT_ZMIN = 50.0                        # not drawn nearer than this in view z (a spin or a put-back turned the camera)
ZMAX, NOCULL = 2 << 10, 0x4000
FULL = 0xC00                            # colour word mode 3: unlit, full intensity
# ---- the placement (spike 56/60) ---------------------------------------------------------------------------------------------
STRIKE_FR, VIEW_TAN, KV_UNITS, TURN_MAX = 34, 0.93, 0.00872, 1.0
PANG, NANG = AIM_DEFAULT, 8            # degrees off the camera's horizontal view direction (left or right); angles a side
JIT, NJIT = 25.0, 9                     # the bolt's turn about the vertical from facing the camera
SB0, SB1, SBJ = 200.0, 0.60, 0.10       # the bolt's height (local 1) = (SB0 + SB1 d) (1 +- SBJ)
NTRY = 16                               # tries (the first with the foot in sight wins, else the least hidden, else no strike)
PLACE_QUOTA = 4                         # tries a pass (the fixed quota; each try one unit after the guard)
GRID_N, GRID_C, GRID_O = 128, 16.0, -1024.0
INVALID, BEYOND = -32768, -32767
BEYOND_DY = -4.0
ROAD_CLEAR, OBST_DY, FOOT_SINK = 48.0, 6.0, 2.0
EYE, LOS_H, LOS_K = 3.0, 10.0, 7
LOS_HALF = 4                            # a guard test before this sample too (a try is three units)
GINV, GBEY = -128, -127                 # the int8 grids' codes: refused / none; beyond the scenery band
GRID_HDR = 24                           # a course's grid blob: i0, j0, w, h, scale, base (words), then the foot and occluder grids
FLASH_ROOM = 3 * 2 * 512                # a course's blob: its three flash skies (n colours each, one after the other), the grids here
# ---- the visibility measure (TEST ONLY: tests/test_weather_lightning.py's bolt-visibility test; off in every build) -------------
MEASURES = ("key", "twin")              # "key": the eight bolt colours one key colour (the palette entry nearest magenta), the bolt's
                                        # matrix through s = 0 / z + 1; "twin": the same, s = TWIN_K / z (the bolt scaled about the
                                        # camera so its foot lies at view z TWIN_K: the same picture, in front of every scenery
                                        # polygon). The same code in both: the two runs stay pass for pass in lockstep.
TWIN_K = 30.0
# ---- the colour RAM ----------------------------------------------------------------------------------------------------------
ROWS, ROW_ENTRIES, ROW_STRIDE = 96, 64, 0x200
XLAT_UNIT = 8                           # rows a unit of the white-out's switch or restore (a row 12.8 us measured: about 105 us)


def F(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _faces_out(q, out) -> bool:
    """MAME's back-face test keeps the drawn quad q when (q1 - q0) x (q2 - q0) points along `out`."""
    n = _cross(_sub(q[1], q[0]), _sub(q[2], q[0]))
    return n[0] * out[0] + n[1] * out[1] + n[2] * out[2] > 0


def _rec(flags, n, p0, p1) -> bytes:
    return struct.pack("<I3f3f3f", flags, *n, *p0, *p1)


# ==================================================================================================================== the bolt
def bolt_paths(rng: random.Random, r_main: float) -> list[tuple]:
    """One bolt's paths [(points, r0, r1)]: the main channel (top -> the foot at the origin, a jagged walk in x and z) and 2-4
    branches spread round it (each its own direction, so not coplanar), going down and out at 35-62 degrees from the vertical, with
    an occasional twig (spike 56's art, the same random sequence)."""
    pts = [(0.0, 1.0, 0.0)]
    x = z = 0.0
    y = 1.0
    hd = rng.uniform(0, 2 * math.pi)
    lean = (rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12))
    while y > 0.0:
        dy = rng.uniform(0.045, 0.09)
        y = max(0.0, y - dy)
        hd += math.pi + rng.uniform(-1.0, 1.0) if rng.random() < 0.7 else rng.uniform(-0.6, 0.6)
        st = rng.uniform(0.03, 0.075)
        x += st * math.cos(hd) + lean[0] * dy
        z += st * math.sin(hd) + lean[1] * dy
        pts.append((x, y, z))
    fx, fz = pts[-1][0], pts[-1][2]
    pts = [(px - fx, py, pz - fz) for px, py, pz in pts]
    paths = [(pts, 0.8 * r_main, 1.0 * r_main)]
    nb = rng.choice((2, 3, 3, 4))
    cand = [i for i, p in enumerate(pts) if 0.22 <= p[1] <= 0.78]
    starts = sorted(rng.sample(cand, k=min(nb, len(cand))))
    az0 = rng.uniform(0, 2 * math.pi)
    for k, s in enumerate(starts):
        az = az0 + k * (2 * math.pi / len(starts)) + rng.uniform(-0.5, 0.5)
        el = math.radians(rng.uniform(35, 62))
        bx, by, bz = pts[s]
        br = [(bx, by, bz)]
        for _ in range(rng.randint(3, 5)):
            L = rng.uniform(0.05, 0.09)
            a = az + rng.uniform(-0.6, 0.6)
            e = el + rng.uniform(-0.25, 0.25)
            if by - L * math.cos(e) < 0.08:             # every segment goes down (the faces' winding follows the drop)
                break
            bx += L * math.sin(e) * math.cos(a)
            bz += L * math.sin(e) * math.sin(a)
            by -= L * math.cos(e)
            br.append((bx, by, bz))
        if len(br) < 3:
            continue
        paths.append((br, 0.62 * r_main, 0.22 * r_main))
        if rng.random() < 0.45:
            t = rng.randrange(1, len(br) - 1)
            tx, ty, tz = br[t]
            tw = [(tx, ty, tz)]
            a = az + rng.choice((-1, 1)) * rng.uniform(0.8, 1.4)
            for _ in range(2):
                L = rng.uniform(0.04, 0.06)
                if ty - L * 0.7 < 0.08:
                    break
                tx += L * 0.7 * math.cos(a)
                tz += L * 0.7 * math.sin(a)
                ty -= L * 0.7
                tw.append((tx, ty, tz))
            if len(tw) == 3:
                paths.append((tw, 0.38 * r_main, 0.15 * r_main))
    return paths


def _rings(path, r0, r1, mirror):
    pts = [((-p[0] if mirror else p[0]), p[1], p[2]) for p in path]
    n = len(pts)
    return [[(x + (r0 + (r1 - r0) * i / max(1, n - 1)) * px, y, z + (r0 + (r1 - r0) * i / max(1, n - 1)) * pz)
             for px, pz in PROFILE] for i, (x, y, z) in enumerate(pts)]


def _face_normal(k):
    (ax, az), (bx, bz) = PROFILE[k], PROFILE[k + 1]
    nx, nz = bz - az, -(bx - ax)
    L = math.hypot(nx, nz)
    return (nx / L, 0.0, nz / L)


def _glow_edges(path, r0, r1, mirror):
    """The backing strip's edge pairs along a path: perpendicular to the path in the local x-y plane (the camera looks along local
    z), GLOW_W radii each side, GLOW_Z radii behind the rod's centre; mitred joints capped at 2x."""
    pts = [((-p[0] if mirror else p[0]), p[1], p[2]) for p in path]
    n = len(pts)
    out = []
    for i, (x, y, z) in enumerate(pts):
        segs = []
        if i > 0:
            segs.append((x - pts[i - 1][0], y - pts[i - 1][1]))
        if i < n - 1:
            segs.append((pts[i + 1][0] - x, pts[i + 1][1] - y))
        norms = []
        for dx, dy in segs:
            L = math.hypot(dx, dy) or 1.0
            norms.append((-dy / L, dx / L))
        px, py = sum(q[0] for q in norms), sum(q[1] for q in norms)
        L = math.hypot(px, py) or 1.0
        px, py = px / L, py / L
        cos_half = max(0.5, px * norms[0][0] + py * norms[0][1])
        r = r0 + (r1 - r0) * i / max(1, n - 1)
        w = GLOW_W * r / cos_half
        zb = z + GLOW_Z * r
        out.append(((x - px * w, y - py * w, zb), (x + px * w, y + py * w, zb)))
    return out


def bolt_object(paths, mirror) -> tuple[bytes, int, int]:
    """One bolt object: the glow strips first (colour G; solid, no culling), then all L strips, then all H, then all R (the first
    record of each group after the first steps the colour pointer); per strip a link-0 record (the first strip: the seeds) and a
    link-2 record a segment; the rods wound so MAME's back-face test keeps the outer side; every record sorted by the quad's farthest
    vertex (ZMAX: nearer scenery draws over the bolt), the glow strip behind its rod. (bytes, records, glow records)."""
    recs = []
    nrm = (0.0, 0.0, -1.0)
    for path, r0, r1 in paths:
        ed = _glow_edges(path, r0, r1, mirror)
        recs.append((0, 0, ed[0][0], ed[0][1], nrm))
        recs += [(0, 2, l, r, nrm) for l, r in ed[1:]]
    nglow = len(recs) - 1
    for k, f in enumerate(FACES):
        n = _face_normal(k)
        for path, r0, r1 in paths:
            rg = _rings(path, r0, r1, mirror)
            a, b = k, k + 1
            if not _faces_out((rg[0][b], rg[0][a], rg[1][a], rg[1][b]), n):
                a, b = b, a
            for i in range(1, len(rg)):
                if not _faces_out((rg[i - 1][b], rg[i - 1][a], rg[i][a], rg[i][b]), n):
                    raise PatchError(f"a bolt's face {f} winds inward at ring {i}")
            recs.append((k + 1, 0, rg[0][a], rg[0][b], n))
            recs += [(k + 1, 2, rg[i][a], rg[i][b], n) for i in range(1, len(rg))]
    out = struct.pack("<6f", *recs[0][2], *recs[0][3])
    face = 0
    for k, link, p0, p1, n in recs[1:]:
        fl = 0x1 | ZMAX | (link << 8) | (NOCULL if k == 0 else 0)
        if k != face:
            fl |= 0x1000
            face = k
        out += _rec(fl, n, p0, p1)
    out += struct.pack("<I9f", 0, *([0.0] * 9))
    return out, len(recs) - 1, nglow


def bolt_objects(stroke_scale: float) -> list[tuple[bytes, int, int]]:
    """The 12 bolt objects (NSH3 shapes, then the same mirrored) with rods R_MAIN0 x stroke_scale thick: (bytes, records, glow)."""
    rng = random.Random(BOLT_SEED)
    paths = [bolt_paths(rng, R_MAIN0 * stroke_scale) for _ in range(NSH3)]
    return [bolt_object(p, mir) for mir in (False, True) for p in paths]


def angle_tables(pang=PANG) -> tuple[bytes, bytes]:
    """(the direction table: per direction `pang` (default PANG, the approved range) off the view, left negative, its cos, sin and VIEW_TAN cos - |sin|; the turn table:
    NJIT (cos, sin) of -JIT..JIT, then the sight line's (LOS_K + 1) / k for k = 1..LOS_K)."""
    angs = [pang[0] + (pang[1] - pang[0]) * k / (NANG - 1) for k in range(NANG)]
    dirs = [-a for a in angs] + angs
    jits = [-JIT + 2 * JIT * k / (NJIT - 1) for k in range(NJIT)]
    dtab = b"".join(struct.pack("<3f", math.cos(math.radians(a)), math.sin(math.radians(a)),
                                VIEW_TAN * math.cos(math.radians(a)) - abs(math.sin(math.radians(a)))) for a in dirs)
    jt = b"".join(struct.pack("<2f", math.cos(math.radians(a)), math.sin(math.radians(a))) for a in jits)
    invt = b"".join(struct.pack("<f", (LOS_K + 1) / k) for k in range(1, LOS_K + 1))
    return dtab, jt + invt


def pattern_table(patterns=PATTERNS) -> bytes:
    """The patterns (PAT_LEN bytes each, 0xff-terminated), then FLASH_OF_LEVEL and SKY_OF_LEVEL."""
    out = b""
    for p in patterns:
        if not (0 < len(p) < PAT_LEN and all(0 <= v < LEVELS and v != 3 for v in p)):
            raise PatchError(f"a lightning pattern of {len(p)} levels: 1..{PAT_LEN - 1}, each of 0, 1, 2, 4, 5, 6")
        out += bytes(p) + b"\xff" * (PAT_LEN - len(p))
    return out + bytes(FLASH_OF_LEVEL) + bytes(SKY_OF_LEVEL) + b"\0\0"


def strokes(pattern) -> list[list[int]]:
    """A pattern's strokes: the runs of levels between the dark frames (0) that hold a flash (1, 2, 4)."""
    out, cur = [], []
    for v in list(pattern) + [0]:
        if v == 0:
            if any(FLASH_OF_LEVEL[x] for x in cur):
                out.append(cur)
            cur = []
        else:
            cur.append(v)
    return out


# ==================================================================================================================== colours
def whiteout_table() -> np.ndarray:
    """[channel][c][l]: the rain's overcast table's output blended toward 255 by WHITEOUT_K, the protected c = 0 entries too (spike
    51: kept at 0 they turned the car's red stripe magenta; the HUD map's line washes with the rest for that one frame)."""
    from vrtools.arcade.weather import rain
    T0 = rain.overcast_table()
    v0 = np.where(T0 == 0xFFFF, 255, T0)
    v = np.round(v0 + (255 - v0) * WHITEOUT_K).astype(np.int64)
    v[:, 0, rain.LPROT:] = round(255 * WHITEOUT_K)
    return v


def flash_sky(grey: list[int], k: float) -> list[int]:
    """The course's grey sky blended toward SKY_WHITE by k; every 16th colour (transparent) and bit 15 kept."""
    out = []
    for i, w in enumerate(grey):
        if i % 16 == 0:
            out.append(w)
            continue
        c = [w & 31, (w >> 5) & 31, (w >> 10) & 31]
        c = [min(31, round(c[j] + (SKY_WHITE[j] - c[j]) * k)) for j in range(3)]
        out.append((w & 0x8000) | (c[2] << 10) | (c[1] << 5) | c[0])
    return out


def key_colour_words(rs: RomSet) -> list[int]:
    """TEST ONLY (the visibility measure): the polygon palette's entry nearest pure magenta, for all eight words."""
    from vrtools.arcade.weather import rain
    return [FULL | rain.pick(rain.polygon_palette(rs), (31, 0, 31))] * 8


def bolt_colour_words(rs: RomSet) -> list[int]:
    """The eight colour words (TEX_ORDER): each the polygon-palette entry nearest its target under the grade (the rain's pick)."""
    from vrtools.arcade.weather import rain
    pal = rain.polygon_palette(rs)
    return [FULL | rain.pick(pal, BOLT_COLOURS[c]) for c in TEX_ORDER]


# ==================================================================================================================== the grids
def _tri_raster(grid: np.ndarray, a, b, c) -> None:
    """The highest value of the triangle's plane at each cell centre it covers (spike 56's raster, the same arithmetic)."""
    xs, zs = (a[0], b[0], c[0]), (a[2], b[2], c[2])
    i0, i1 = int(math.floor((min(xs) - GRID_O) / GRID_C - 0.5)), int(math.ceil((max(xs) - GRID_O) / GRID_C - 0.5))
    j0, j1 = int(math.floor((min(zs) - GRID_O) / GRID_C - 0.5)), int(math.ceil((max(zs) - GRID_O) / GRID_C - 0.5))
    den = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
    if abs(den) < 1e-6:
        return
    i0, i1, j0, j1 = max(0, i0), min(GRID_N, i1 + 1), max(0, j0), min(GRID_N, j1 + 1)
    if i0 >= i1 or j0 >= j1:
        return
    x = GRID_O + (np.arange(i0, i1) + 0.5) * GRID_C
    z = GRID_O + (np.arange(j0, j1) + 0.5) * GRID_C
    X, Z = np.meshgrid(x, z)
    l1 = ((b[2] - c[2]) * (X - c[0]) + (c[0] - b[0]) * (Z - c[2])) / den
    l2 = ((c[2] - a[2]) * (X - c[0]) + (a[0] - c[0]) * (Z - c[2])) / den
    l3 = 1 - l1 - l2
    inside = np.minimum(np.minimum(l1, l2), l3) >= -1e-4
    y = l1 * a[1] + l2 * b[1] + l3 * c[1]
    sub = grid[j0:j1, i0:i1]
    np.copyto(sub, y, where=inside & (y > sub))


def height_grid(rs: RomSet, tile_table: int, centre: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray, dict]:
    """[z cell][x cell] int16, 16-unit cells from -1024: the foot height (the highest ground-like face (|normal y| >= 0.6) at the
    cell's centre or corners, less FOOT_SINK), INVALID where refused (within ROAD_CLEAR of the centreline, or a face rising OBST_DY
    above the ground in the cell or a neighbour), BEYOND for cells with no geometry (beyond the scenery band: the foot at the
    player's ground + BEYOND_DY); and the occluder grid: the highest face of any kind in each cell and its 8 neighbours (INVALID:
    none). From the course's tile geometry (spike 56; entity objects such as pit garages and signs are not in it)."""
    from vrtools.arcade.course import tile_table_at
    from vrtools.arcade.polyrom import decode_object, quads
    ground = np.full((GRID_N, GRID_N), -1e9)
    anyg = np.full((GRID_N, GRID_N), -1e9)
    for t in tile_table_at(rs, tile_table):
        if not t.size:
            continue
        for q in quads(decode_object(rs.polygons, t.poly_adr, t.size)):
            P = [np.array(p, float) for p in q.p]
            nrm = np.cross(P[2] - P[0], P[1] - P[0])
            if np.linalg.norm(nrm) < 1e-9:
                nrm = np.cross(P[3] - P[1], P[2] - P[1])
            L = np.linalg.norm(nrm)
            if L < 1e-9:
                continue
            for g in (anyg, ground) if abs(nrm[1]) / L >= 0.6 else (anyg,):
                _tri_raster(g, P[0], P[1], P[2])
                _tri_raster(g, P[0], P[2], P[3])
                for p in P:
                    i, j = int((p[0] - GRID_O) // GRID_C), int((p[2] - GRID_O) // GRID_C)
                    if 0 <= i < GRID_N and 0 <= j < GRID_N and p[1] > g[j, i]:
                        g[j, i] = p[1]
    has = ground > -1e8
    tall = (anyg - np.where(has, ground, anyg)) > OBST_DY
    tall_n = tall.copy()
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            tall_n |= np.roll(np.roll(tall, dj, 0), di, 1)
    h = np.where(has, ground, 0.0)
    cx = GRID_O + (np.arange(GRID_N) + 0.5) * GRID_C
    X, Z = np.meshgrid(cx, cx)
    cl = np.array(centre, float)
    near = np.zeros((GRID_N, GRID_N), bool)
    for (ax, az), (bx, bz) in zip(cl, np.roll(cl, -1, 0)):
        dx, dz = bx - ax, bz - az
        L2 = dx * dx + dz * dz or 1.0
        t = np.clip(((X - ax) * dx + (Z - az) * dz) / L2, 0, 1)
        near |= (X - ax - t * dx) ** 2 + (Z - az - t * dz) ** 2 < ROAD_CLEAR ** 2
    bad = near | (has & tall_n)
    out = np.where(bad, INVALID, np.where(has, np.clip(np.floor(h - FOOT_SINK), -32000, 32000), BEYOND)).astype(np.int16)
    occ = anyg.copy()
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            occ = np.maximum(occ, np.roll(np.roll(anyg, dj, 0), di, 1))
    occ = np.where(occ > -1e8, np.clip(np.ceil(occ), -32000, 32000), INVALID).astype(np.int16)
    stats = {"ground cells": int(has.sum()), "refused near road": int(near.sum()), "refused tall": int((has & tall_n & ~near).sum()),
             "valid in band": int((has & ~bad).sum())}
    return out, occ, stats


def encode_grids(grid: np.ndarray, occ: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, int, int]:
    """int16 foot / occluder grids -> int8 (value x s + base) with the codes GINV / GBEY; s the smallest scale that fits the course's
    span (spike 70). (foot, occluders, s, base, the largest foot error)."""
    fv = grid[(grid != INVALID) & (grid != BEYOND)].astype(np.int64)
    ov = occ[occ != INVALID].astype(np.int64)
    vals = np.concatenate([fv, ov]) if len(fv) or len(ov) else np.array([0])
    lo, hi = int(vals.min()), int(vals.max())
    s = 1
    while (hi - lo) / s > 252:
        s += 1
    base = lo + 126 * s
    g = np.floor((grid.astype(np.int64) - base) / s)
    g = np.where(grid == INVALID, GINV, np.where(grid == BEYOND, GBEY, np.clip(g, -126, 127)))
    o = np.ceil((occ.astype(np.int64) - base) / s)
    o = np.where(occ == INVALID, GINV, np.clip(o, -126, 127))
    ok = (grid != INVALID) & (grid != BEYOND)
    err = int(np.max(np.abs(g[ok] * s + base - grid[ok]))) if ok.any() else 0
    return g.astype(np.int8), o.astype(np.int8), s, base, err


def crop_box(g8: np.ndarray, o8: np.ndarray) -> tuple[int, int, int, int]:
    """(i0, j0, w, h): the smallest box holding every cell whose foot is not GBEY or whose occluder is not GINV (outside it the
    grids read GBEY and GINV: lossless)."""
    keep = (g8 != GBEY) | (o8 != GINV)
    if not keep.any():
        return 0, 0, 1, 1
    js, is_ = np.nonzero(keep)
    return int(is_.min()), int(js.min()), int(is_.max() - is_.min() + 1), int(js.max() - js.min() + 1)


def grid_blob(rs: RomSet, entry: int) -> tuple[bytes, dict]:
    """A course's grid blob (GRID_HDR bytes of i0, j0, w, h, scale, base, then the cropped int8 foot grid and the occluder grid, w x h
    each, z-major) and its figures."""
    from vrtools.arcade.course import course_entry_at, road_lines
    from vrtools.arcade.directory import decode_directory
    e = decode_directory(rs)[entry]
    centre = [(q.x, q.z) for q in road_lines(rs, course_entry_at(rs, e.bank, window_base=e.header_base))[0]]
    grid, occ, stats = height_grid(rs, e.tile_table, centre)
    g8, o8, s, base, err = encode_grids(grid, occ)
    i0, j0, w, h = crop_box(g8, o8)
    blob = struct.pack("<6i", i0, j0, w, h, s, base) + g8[j0:j0 + h, i0:i0 + w].tobytes() + o8[j0:j0 + h, i0:i0 + w].tobytes()
    blob += b"\0" * (-len(blob) % 4)
    return blob, {**stats, "scale": s, "base": base, "foot error": err, "box": (i0, j0, w, h)}


def decode_grid_blob(blob: bytes) -> tuple[np.ndarray, np.ndarray, int, int]:
    """The full 128 x 128 int8 grids a blob stands for (outside its box GBEY and GINV), its scale and base."""
    i0, j0, w, h, s, base = struct.unpack_from("<6i", blob)
    g = np.full((GRID_N, GRID_N), GBEY, np.int8)
    o = np.full((GRID_N, GRID_N), GINV, np.int8)
    a = np.frombuffer(blob, np.int8, w * h, GRID_HDR).reshape(h, w)
    b = np.frombuffer(blob, np.int8, w * h, GRID_HDR + w * h).reshape(h, w)
    g[j0:j0 + h, i0:i0 + w] = a
    o[j0:j0 + h, i0:i0 + w] = b
    return g, o, s, base


# ==================================================================================================================== the code
STATE_NAMES = tuple(("INIT LF PHASE NEXT SEEDED RAND PAT STEP PREV FALLING ONI ON0 ON1 ON2 LEVEL PCUR WROWS WTARGET TRIES RUNV TURNV "
                     "HAVEV BESTH WX WY WZ DV CV SV AXX AXZ AZX AZZ SBV KHV SHP REC NSTRIKE NONSET NBLOCK NBOLT NCOVB NCOVW NLATEW "
                     "NTRIMB NPLACED NHIDDEN NFALL NVIEW NTRYS NLATEP NPART NZSKIP NLATES NLATEB VIEWZ NWASH").split())
IDLE, PLACING, FRAMING, RUNNING = 0, 1, 2, 3     # PHASE


def _f(b: Block, op: str, src, dst: str) -> None:
    """A float instruction: src a register, ("f", x) an immediate, ("abs", a), ("disp", d, reg), ("absx", a, reg); dst a register."""
    if isinstance(src, str):
        b.emit(f"{op} reg,reg", src, dst)
    elif src[0] == "f":
        b.emit(f"{op} imm,reg", float(src[1]), dst)
    elif src[0] == "abs":
        b.emit(f"{op} abs,reg", src[1], dst)
    elif src[0] == "absx":
        b.emit(f"{op} abs(reg),reg", src[1], src[2], dst)
    else:
        b.emit(f"{op} disp[reg],reg", src[1], src[2], dst)


def _lin2(b: Block, dst, k1, x1, k2, x2, tmp, sub=False) -> None:
    """dst = k1 x1 + k2 x2 (or - with sub); k1, k2 registers, x1, x2 `_f` operands (tmp used)."""
    b.emit("mov.w reg,reg", k1, dst)
    _f(b, "mulf.s", x1, dst)
    b.emit("mov.w reg,reg", k2, tmp)
    _f(b, "mulf.s", x2, tmp)
    _f(b, "subf.s" if sub else "addf.s", tmp, dst)


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


class Lightning:
    """The lightning's code for one Layout: `block()` is its Block (labels frame, release)."""

    def __init__(self, lay: carrier.Layout, k: dict, tune: LightningTune, fault: tuple = (), measure: str = ""):
        from vrtools.arcade.weather import rain
        self.lay, self.k, self.t = lay, k, tune
        self.measure = measure                          # TEST-ONLY visibility measure (MEASURES; "" in every build)
        self.fault = frozenset(fault)                   # TEST-ONLY planted faults (FAULTS; empty in every build)
        st = lay.cell("lightning", "state")
        self.c = {n: st + 4 * i for i, n in enumerate(STATE_NAMES)}
        self.SEQ, self.BAND = lay.cell("lightning", "strike_seq"), lay.cell("lightning", "strike_band")
        self.COVER = lay.cell("cover", "under_cover")
        rc = rain.Rain(lay, None, None).c                # the rain's state cells, by name (read only)
        self.R_XSTATE, self.R_XLEFT, self.R_RAND = rc["XSTATE"], rc["XLEFT"], rc["RAND"]
        self.SKY, self.OWN, self.T0 = lay.data_at("rain", "sky"), lay.data_at("rain", "own"), lay.data_at("rain", "overcast")
        self.WHITE = lay.data_at("lightning", "whiteout")
        self.FLASH = lay.data_at("lightning", "course")                # the three flash skies (FLASH_ROOM bytes), then the grids
        self.GRID = self.FLASH + FLASH_ROOM
        self.PATS = lay.table("lightning", "patterns")
        self.FLASH_OF = self.PATS + PAT_LEN * k["npat"]
        self.SKY_OF = self.FLASH_OF + LEVELS
        self.DIRTAB, self.JITTAB = lay.table("lightning", "dirs"), lay.table("lightning", "turns")
        self.INVT = self.JITTAB + 8 * NJIT
        self.SHPTAB = lay.table("lightning", "bolts")
        self.every = (round(tune.interval_s[0] * FPS), round(tune.interval_s[1] * FPS))

    # ---- pieces
    def lcg(self, b: Block) -> None:
        R = self.c["RAND"]
        b.emit("mov.w abs,reg", R, "r0")
        b.emit("mul.w imm,reg", 1103515245, "r0")
        b.emit("add.w imm,reg", 12345, "r0")
        b.emit("mov.w reg,abs", "r0", R)

    def rint(self, b: Block, n: int, dst: str = "r0") -> None:
        """dst = an integer in [0, n) (R0 used)."""
        self.lcg(b)
        b.emit("shl.w imm,reg", -16, "r0")
        b.emit("mul.w imm,reg", n, "r0")
        b.emit("shl.w imm,reg", -16, "r0")
        if dst != "r0":
            b.emit("mov.w reg,reg", "r0", dst)

    def rnd(self, b: Block, dst: str) -> None:
        """dst = a float in [0, 1) (R0 used)."""
        self.lcg(b)
        b.emit("shl.w imm,reg", -9, "r0")
        _f(b, "cvt.ws", "r0", dst)
        _f(b, "mulf.s", ("f", 1.0 / 8388608), dst)

    def schedule(self, b: Block, lo: int, hi: int) -> None:
        self.rint(b, hi - lo + 1)
        b.emit("add.w imm,reg", lo, "r0")
        b.emit("mov.w reg,abs", "r0", self.c["NEXT"])

    def cell_index(self, b: Block, rx: str, rz: str, dst: str, q: str, outside: str, clamp: bool) -> None:
        """dst = the crop-box index of the grid cell under world (rx, rz) (floats); with `clamp` the cell clamped to 0..127 first
        (the prototype's foot lookup), else a cell off the grid goes to `outside` too; a cell off the box goes to `outside`. R0, R3
        used (R3 the z cell)."""
        G = self.GRID
        for src, r, qq in ((rx, dst, "x"), (rz, "r3", "z")):
            _f(b, "cvt.sw", src, r)
            b.emit("add.w imm,reg", 1024, r)
            b.emit("sha.w imm,reg", -4, r)
            if clamp:
                b.emit("cmp.w imm,reg", 0, r)
                b.branch("bge", q + qq + "a")
                b.emit("mov.w imm,reg", 0, r)
                b.label(q + qq + "a")
                b.emit("cmp.w imm,reg", GRID_N - 1, r)
                b.branch("ble", q + qq + "b")
                b.emit("mov.w imm,reg", GRID_N - 1, r)
                b.label(q + qq + "b")
            b.emit("sub.w abs,reg", G + (0 if qq == "x" else 4), r)       # minus i0 / j0
            b.emit("cmp.w imm,reg", 0, r)
            b.branch("blt", outside)
            b.emit("cmp.w abs,reg", G + (8 if qq == "x" else 12), r)      # w / h
            b.branch("bge", outside)
        b.emit("mul.w abs,reg", G + 8, "r3")
        b.emit("add.w reg,reg", "r3", dst)

    # ---- the scheduler: a strike's start
    def begin(self, b: Block) -> None:
        """A strike begins: the next one scheduled (counted from this one's end), a pattern, the car's run over STRIKE_FR logic frames
        (RUNV) and the turn ahead (TURNV: tan of the centreline's heading change k points past the player's, k = the run / 10 units
        at most 8; clamped to TURN_MAX), the placement next."""
        c = self.c
        self.schedule(b, *self.every)
        self.rint(b, self.k["npat"])
        b.emit("mul.w imm,reg", PAT_LEN, "r0")
        b.emit("add.w imm,reg", self.PATS, "r0")
        b.emit("mov.w reg,abs", "r0", c["PAT"])
        b.emit("mov.w abs,reg", SPEED, "r0")
        _f(b, "cvt.ws", "r0", "r5")
        _f(b, "mulf.s", ("f", KV_UNITS * STRIKE_FR), "r5")
        b.emit("mov.w reg,abs", "r5", c["RUNV"])
        b.emit("mov.w abs,reg", SPEED, "r0")
        _f(b, "cvt.ws", "r0", "r4")
        _f(b, "mulf.s", ("f", KV_UNITS * STRIKE_FR / 10.0), "r4")
        _f(b, "cvt.sw", "r4", "r4")
        b.emit("cmp.w imm,reg", 0, "r4")
        b.branch("bge", "tk0")
        b.emit("mov.w imm,reg", 0, "r4")
        b.label("tk0")
        b.emit("cmp.w imm,reg", 8, "r4")
        b.branch("ble", "tk1")
        b.emit("mov.w imm,reg", 8, "r4")
        b.label("tk1")
        b.emit("mov.w abs,reg", LINES_PTR, "r1")
        b.emit("mov.w [reg],reg", "r1", "r2")                          # line 0's first point (window address)
        b.emit("movz.hw abs,reg", ROADPT, "r3")
        b.emit("shl.w imm,reg", 4, "r3")
        b.emit("add.w reg,reg", "r3", "r2")
        b.emit("movz.hw disp[reg],reg", 10, "r2", "r7")
        b.emit("shl.w imm,reg", 4, "r4")
        b.emit("add.w reg,reg", "r4", "r2")
        b.emit("movz.hw disp[reg],reg", 10, "r2", "r8")
        b.emit("sub.w reg,reg", "r7", "r8")
        b.emit("shl.w imm,reg", 16, "r8")
        b.emit("sha.w imm,reg", -16, "r8")
        _f(b, "cvt.ws", "r8", "r6")
        _f(b, "mulf.s", ("f", 2 * math.pi / 16384), "r6")
        _clamp(b, "r6", -TURN_MAX, TURN_MAX, "tu")
        b.emit("mov.w reg,reg", "r6", "r7")
        _f(b, "mulf.s", "r6", "r7")
        b.emit("mov.w reg,reg", "r7", "r8")
        _f(b, "mulf.s", ("f", 2.0 / 15.0), "r8")
        _f(b, "addf.s", ("f", 1.0 / 3.0), "r8")
        _f(b, "mulf.s", "r7", "r8")
        _f(b, "addf.s", ("f", 1.0), "r8")
        _f(b, "mulf.s", "r6", "r8")
        b.emit("mov.w reg,abs", "r8", c["TURNV"])
        b.emit("mov.w imm,abs", NTRY, c["TRIES"])
        b.emit("mov.w imm,abs", 0, c["HAVEV"])
        b.emit("mov.w imm,abs", PLACING, c["PHASE"])

    # ---- the placement: one try (three units: the place and its foot; sight-line samples 0..3; 4..6 and the keep); to `found` (the
    # foot in sight), else on to `nxt`; to `late` when the guard stops it inside (that try is not counted: redone next pass)
    def try_(self, b: Block, found: str, nxt: str, late: str) -> None:
        c, t = self.c, self.t
        G = self.GRID
        b.emit("add.w imm,abs", 1, c["NTRYS"])
        b.emit("mov.w abs,reg", c["RUNV"], "r5")
        self.rint(b, 2 * NANG)
        b.emit("mul.w imm,reg", 3, "r0")
        b.emit("mov.w abs(reg),reg", self.DIRTAB, "r0", "r15")          # c
        b.emit("add.w imm,reg", 1, "r0")
        b.emit("mov.w abs(reg),reg", self.DIRTAB, "r0", "r16")          # s
        _lin2(b, "r17", "r15", ("abs", m(2)), "r16", ("abs", m(0)), "r0")   # D = c F + s R (F = (m2, m8), R = (m0, m6))
        _lin2(b, "r18", "r15", ("abs", m(8)), "r16", ("abs", m(6)), "r0")
        self.rnd(b, "r19")
        _f(b, "mulf.s", ("f", t.distance[1] - t.distance[0]), "r19")
        _f(b, "addf.s", ("f", t.distance[0]), "r19")                   # R19 = the distance
        # still in view at the strike's end: after the run m straight ahead the foot is at (u, v) = (d s, d c - m); turned by T
        # (tan ~ T): tan = (u + T v) / (v - T u); refused unless v and the denominator are at least 1 and |tan| <= VIEW_TAN
        b.emit("mov.w reg,reg", "r19", "r3")
        _f(b, "mulf.s", "r16", "r3")
        b.emit("mov.w reg,reg", "r19", "r4")
        _f(b, "mulf.s", "r15", "r4")
        _f(b, "subf.s", "r5", "r4")
        _f(b, "cmpf.s", ("f", 1.0), "r4")
        b.branch("blt", "pvbad")
        _f(b, "movf.s", ("abs", c["TURNV"]), "r7")
        _f(b, "mulf.s", "r4", "r7")
        _f(b, "addf.s", "r3", "r7")
        _f(b, "movf.s", ("abs", c["TURNV"]), "r6")
        _f(b, "mulf.s", "r3", "r6")
        b.emit("mov.w reg,reg", "r4", "r0")
        _f(b, "subf.s", "r6", "r0")
        _f(b, "cmpf.s", ("f", 1.0), "r0")
        b.branch("blt", "pvbad")
        _f(b, "mulf.s", ("f", VIEW_TAN), "r0")
        _f(b, "cmpf.s", "r0", "r7")
        b.branch("bgt", "pvbad")
        _f(b, "negf.s", "r0", "r0")
        _f(b, "cmpf.s", "r0", "r7")
        b.branch("bge", "pview")
        b.label("pvbad")
        b.emit("add.w imm,abs", 1, c["NVIEW"])
        b.branch("br", nxt)
        b.label("pview")
        for dst, dcomp, car in (("r11", "r17", PX), ("r12", "r18", PZ)):
            b.emit("mov.w reg,reg", dcomp, dst)
            _f(b, "mulf.s", "r19", dst)
            _f(b, "addf.s", ("abs", car), dst)
        # the foot's cell (clamped to the grid, as the prototype), its code: refused, beyond the band, or a height
        self.cell_index(b, "r11", "r12", "r2", "pc", "pfbey", clamp=True)
        b.emit("movz.bw abs(reg),reg", G + GRID_HDR, "r2", "r3")
        b.emit("shl.w imm,reg", 24, "r3")
        b.emit("sha.w imm,reg", -24, "r3")
        b.emit("cmp.w imm,reg", GINV, "r3")
        b.branch("be", nxt)
        b.emit("cmp.w imm,reg", GBEY, "r3")
        b.branch("bne", "pgdec")
        b.label("pfbey")
        _f(b, "movf.s", ("abs", PY), "r13")                            # beyond the band: the player's ground + BEYOND_DY
        _f(b, "addf.s", ("f", BEYOND_DY), "r13")
        b.branch("br", "pgy")
        b.label("pgdec")
        b.emit("mul.w abs,reg", G + 16, "r3")
        b.emit("add.w abs,reg", G + 20, "r3")
        _f(b, "cvt.ws", "r3", "r13")                                   # R13 = the foot's height
        b.label("pgy")
        # the sight from the car (+ EYE) to the bolt's vertical: LOS_K samples at t = k / (LOS_K + 1) against the occluder grid; past
        # an occluder o at t the bolt shows above eye + (o - eye) / t: R8 = the highest of those and foot + LOS_H; R8 - foot the
        # hidden height; the lowest kept (BESTH); LOS_H or less (the foot in sight) ends the search
        _f(b, "movf.s", ("abs", PX), "r6")
        _f(b, "movf.s", ("abs", PZ), "r7")
        _f(b, "movf.s", ("abs", PY), "r10")
        _f(b, "addf.s", ("f", EYE), "r10")
        for k, d_from, org in (("r1", "r11", "r6"), ("r2", "r12", "r7")):
            b.emit("mov.w reg,reg", d_from, k)
            _f(b, "subf.s", org, k)
            _f(b, "mulf.s", ("f", 1.0 / (LOS_K + 1)), k)
        emit_guard_time(b, late)
        b.emit("mov.w reg,reg", "r13", "r8")
        _f(b, "addf.s", ("f", LOS_H), "r8")
        b.emit("mov.w imm,reg", 0, "r9")
        b.emit("mov.w imm,reg", F(1e9), "r4")                          # R4: past this the try cannot beat the best one (pruned)
        b.emit("cmp.w imm,abs", 0, c["HAVEV"])
        b.branch("be", "lloop")
        _f(b, "movf.s", ("abs", c["BESTH"]), "r4")
        _f(b, "addf.s", "r13", "r4")
        b.label("lloop")
        b.emit("cmp.w imm,reg", LOS_HALF, "r9")
        b.branch("bne", "lgo")
        emit_guard_time(b, late)
        b.label("lgo")
        _f(b, "addf.s", "r1", "r6")
        _f(b, "addf.s", "r2", "r7")
        b.emit("push reg", "r2")
        self.cell_index(b, "r6", "r7", "r2", "lc", "lnone", clamp=False)
        b.emit("mov.w abs,reg", G + 8, "r0")                           # the occluder grid follows the foot grid (w h bytes)
        b.emit("mul.w abs,reg", G + 12, "r0")
        b.emit("add.w reg,reg", "r0", "r2")
        b.emit("movz.bw abs(reg),reg", G + GRID_HDR, "r2", "r3")
        b.emit("shl.w imm,reg", 24, "r3")
        b.emit("sha.w imm,reg", -24, "r3")
        b.emit("cmp.w imm,reg", GINV, "r3")
        b.branch("bne", "odec")
        b.label("lnone")
        b.emit("mov.w imm,reg", -32768, "r3")
        b.branch("br", "odone")
        b.label("odec")
        b.emit("mul.w abs,reg", G + 16, "r3")
        b.emit("add.w abs,reg", G + 20, "r3")
        b.label("odone")
        b.emit("pop reg", "r2")
        _f(b, "cvt.ws", "r3", "r14")
        _f(b, "subf.s", "r10", "r14")
        _f(b, "mulf.s", ("absx", self.INVT, "r9"), "r14")
        _f(b, "addf.s", "r10", "r14")
        _f(b, "cmpf.s", "r8", "r14")
        b.branch("ble", "lnext")
        b.emit("mov.w reg,reg", "r14", "r8")
        _f(b, "cmpf.s", "r4", "r8")
        b.branch("bge", nxt)
        b.label("lnext")
        b.emit("add.w imm,reg", 1, "r9")
        b.emit("cmp.w imm,reg", LOS_K, "r9")
        b.branch("blt", "lloop")
        _f(b, "subf.s", "r13", "r8")                                   # R8 = the hidden height
        b.emit("cmp.w imm,abs", 0, c["HAVEV"])
        b.branch("be", "psave")
        _f(b, "cmpf.s", ("abs", c["BESTH"]), "r8")
        b.branch("bge", nxt)
        b.label("psave")
        for r, a in (("r11", "WX"), ("r13", "WY"), ("r12", "WZ"), ("r19", "DV"), ("r15", "CV"), ("r16", "SV"), ("r8", "BESTH")):
            b.emit("mov.w reg,abs", r, c[a])
        b.emit("mov.w imm,abs", 1, c["HAVEV"])
        _f(b, "cmpf.s", ("f", LOS_H + 0.5), "r8")
        b.branch("bgt", nxt)
        b.emit("add.w imm,abs", 1, c["NPLACED"])
        b.branch("br", found)

    def frame_of_bolt(self, b: Block) -> None:
        """The strike's bolt: facing the camera along D turned by a random jitter, scaled (SB0 + SB1 d)(1 +- SBJ) and in x and z by
        the far thickening KH; a random one of the 12 objects."""
        c = self.c
        for r, a in (("r15", "CV"), ("r16", "SV"), ("r19", "DV")):
            b.emit("mov.w abs,reg", c[a], r)
        _lin2(b, "r17", "r15", ("abs", m(2)), "r16", ("abs", m(0)), "r0")
        _lin2(b, "r18", "r15", ("abs", m(8)), "r16", ("abs", m(6)), "r0")
        _lin2(b, "r6", "r15", ("abs", m(0)), "r16", ("abs", m(2)), "r0", sub=True)
        _lin2(b, "r7", "r15", ("abs", m(6)), "r16", ("abs", m(8)), "r0", sub=True)
        self.rint(b, NJIT)
        b.emit("shl.w imm,reg", 1, "r0")
        b.emit("mov.w abs(reg),reg", self.JITTAB, "r0", "r15")         # cj
        b.emit("add.w imm,reg", 1, "r0")
        b.emit("mov.w abs(reg),reg", self.JITTAB, "r0", "r16")         # sj
        b.emit("mov.w reg,reg", "r19", "r14")
        _f(b, "mulf.s", ("f", SB1), "r14")
        _f(b, "addf.s", ("f", SB0), "r14")
        self.rnd(b, "r4")
        _f(b, "mulf.s", ("f", 2 * SBJ), "r4")
        _f(b, "addf.s", ("f", 1 - SBJ), "r4")
        _f(b, "mulf.s", "r4", "r14")
        b.emit("mov.w reg,abs", "r14", c["SBV"])
        b.emit("mov.w reg,reg", "r19", "r4")
        _f(b, "subf.s", ("f", KH_D0), "r4")
        _f(b, "mulf.s", ("f", KH1), "r4")
        _f(b, "addf.s", ("f", 1.0), "r4")
        _clamp(b, "r4", 1.0, KH_MAX, "kh")
        b.emit("mov.w reg,abs", "r4", c["KHV"])
        _f(b, "mulf.s", "r4", "r14")
        for dst, (a1, a2, sub) in (("AZX", ("r17", "r6", False)), ("AZZ", ("r18", "r7", False)),
                                   ("AXX", ("r6", "r17", True)), ("AXZ", ("r7", "r18", True))):
            _lin2(b, "r1", "r15", a1, "r16", a2, "r0", sub=sub)
            _f(b, "mulf.s", "r14", "r1")
            b.emit("mov.w reg,abs", "r1", c[dst])
        self.rint(b, 2 * NSH3)
        b.emit("mov.w abs(reg),reg", self.SHPTAB, "r0", "r0")
        b.emit("mov.w reg,abs", "r0", c["SHP"])
        # the interface: one more strike, its band by the distance
        b.emit("add.w imm,abs", 2 if "seq" in self.fault else 1, self.SEQ)
        b.emit("mov.w imm,reg", 1, "r0")
        _f(b, "cmpf.s", ("f", BANDS[0]), "r19")
        b.branch("blt", "band_ok")
        b.emit("mov.w imm,reg", 2, "r0")
        _f(b, "cmpf.s", ("f", BANDS[1]), "r19")
        b.branch("blt", "band_ok")
        b.emit("mov.w imm,reg", 3, "r0")
        b.label("band_ok")
        if "band" in self.fault:                        # TEST ONLY: the band one off (1 -> 2 -> 3 -> 1)
            b.emit("add.w imm,reg", 1, "r0")
            b.emit("cmp.w imm,reg", 4, "r0")
            b.branch("bne", "band_f")
            b.emit("mov.w imm,reg", 1, "r0")
            b.label("band_f")
        b.emit("mov.w reg,abs", "r0", self.BAND)
        b.emit("add.w imm,abs", 1, c["NSTRIKE"])
        b.emit("mov.w imm,abs", 0, c["STEP"])
        b.emit("mov.w imm,abs", RUNNING, c["PHASE"])

    def safety(self, b: Block) -> None:
        """The rule (spike 51, on the flash level R8 = FLASH_OF[R9]; PREV the previous pass's): an onset (a rise from 0, or a rise
        after a fall) only when the last `max_onsets_per_s` are ONSET_WINDOW logic frames old or older; otherwise the strike ends
        here (to `abort`)."""
        c, n = self.c, self.t.max_onsets_per_s
        b.emit("movz.bw abs(reg),reg", self.FLASH_OF, "r9", "r8")
        b.emit("cmp.w abs,reg", c["PREV"], "r8")
        b.branch("ble", "no_onset")
        b.emit("cmp.w imm,abs", 0, c["PREV"])
        b.branch("be", "onset")
        b.emit("cmp.w imm,abs", 0, c["FALLING"])
        b.branch("be", "no_onset")
        b.label("onset")
        b.emit("mov.w abs,reg", c["ONI"], "r1")
        if "norule" in self.fault:                      # TEST ONLY: every onset allowed (the rule gone)
            b.branch("br", "onset_ok")
        b.emit("mov.w abs,reg", c["LF"], "r2")
        b.emit("sub.w abs(reg),reg", c["ON0"], "r1", "r2")              # R2 = LF - the oldest of the last n onsets
        b.emit("cmp.w imm,reg", ONSET_WINDOW, "r2")
        b.branch("bge", "onset_ok")
        b.emit("add.w imm,abs", 1, c["NBLOCK"])
        b.branch("br", "abort")
        b.label("onset_ok")
        b.emit("mov.w abs,reg", c["LF"], "r2")
        b.emit("mov.w reg,abs(reg)", "r2", c["ON0"], "r1")
        b.emit("add.w imm,reg", 1, "r1")
        b.emit("cmp.w imm,reg", n, "r1")
        b.branch("blt", "oni_ok")
        b.emit("mov.w imm,reg", 0, "r1")
        b.label("oni_ok")
        b.emit("mov.w reg,abs", "r1", c["ONI"])
        b.emit("add.w imm,abs", 1, c["NONSET"])
        b.label("no_onset")
        b.emit("cmp.w abs,reg", c["PREV"], "r8")
        b.branch("bge", "not_falling")
        b.emit("mov.w imm,abs", 1, c["FALLING"])
        b.label("not_falling")
        b.emit("cmp.w abs,reg", c["PREV"], "r8")
        b.branch("ble", "rise_done")
        b.emit("mov.w imm,abs", 0, c["FALLING"])
        b.label("rise_done")
        b.emit("cmp.w imm,reg", 0, "r8")
        b.branch("bne", "apply")
        b.emit("mov.w imm,abs", 0, c["FALLING"])

    def sky(self, b: Block) -> None:
        """The sky's slot for level R9 into palette RAM when it is not there (one unit after the guard; a late pass keeps the sky and
        the next pass writes it): slot 0 the rain's grey (its data), 1..3 the flash skies (FLASH + (slot - 1) x 2n)."""
        c = self.c
        b.emit("movz.bw abs(reg),reg", self.SKY_OF, "r9", "r2")
        b.emit("cmp.w abs,reg", c["PCUR"], "r2")
        b.branch("be", "sky_ok")
        emit_guard_time(b, "sky_late")
        b.emit("mov.w reg,abs", "r2", c["PCUR"])
        b.emit("mov.w imm,reg", self.SKY + 8, "r0")
        b.emit("mov.w abs,reg", self.SKY + 4, "r3")                    # n colours
        b.emit("cmp.w imm,reg", 0, "r2")
        b.branch("be", "sky_copy")
        b.emit("mov.w reg,reg", "r2", "r0")
        b.emit("sub.w imm,reg", 1, "r0")
        b.emit("mul.w reg,reg", "r3", "r0")
        b.emit("shl.w imm,reg", 1, "r0")
        b.emit("add.w imm,reg", self.FLASH, "r0")
        b.label("sky_copy")
        b.emit("mov.w abs,reg", self.SKY, "r1")                        # the backdrop's place in palette RAM
        emit_copy(b, "r0", "r1", "r3")
        b.branch("br", "sky_ok")
        b.label("sky_late")
        b.emit("add.w imm,abs", 1, c["NLATES"])
        b.label("sky_ok")

    def xlat(self, b: Block) -> None:
        """The colour RAM toward WTARGET (96: the white-out; 0: the rain's overcast table), XLAT_UNIT rows a unit after the guard. Row
        k of the order is channel k % 3 of value 31 - k / 3 (the brightest values first, the three channels together: a white-out
        cut short is the bright values washed); the switch writes rows WROWS.. from the white-out table, the restore rows ..WROWS - 1
        backwards from the overcast table. A white-out whose first unit finds the pass late is not shown (NLATEW); one cut later
        (NPART) is restored from the next pass."""
        c = self.c
        b.label("xloop")
        b.emit("mov.w abs,reg", c["WROWS"], "r4")
        b.emit("cmp.w abs,reg", c["WTARGET"], "r4")
        b.branch("be", "xdone")
        emit_guard_time(b, "xlate")
        b.emit("mov.w imm,reg", XLAT_UNIT, "r5")
        b.emit("cmp.w abs,reg", c["WTARGET"], "r4")
        b.branch("bgt", "xback")
        b.emit("cmp.w imm,reg", 0, "r4")
        b.branch("bne", "xrow")
        b.emit("add.w imm,abs", 1, c["NWASH"])                         # a white-out begins
        b.label("xrow")                                                # forward: row r4 from the white-out table, then r4 + 1
        self.row_addrs(b, self.WHITE)
        emit_copy(b, "r0", "r1", ROW_ENTRIES)
        b.emit("add.w imm,reg", 1, "r4")
        b.emit("sub.w imm,reg", 1, "r5")
        b.emit("cmp.w imm,reg", 0, "r5")
        b.branch("bne", "xrow")
        b.emit("mov.w reg,abs", "r4", c["WROWS"])
        b.branch("br", "xloop")
        b.label("xback")                                               # backward: row r4 - 1 from the overcast table
        b.emit("sub.w imm,reg", 1, "r4")
        self.row_addrs(b, self.T0)
        emit_copy(b, "r0", "r1", ROW_ENTRIES)
        b.emit("sub.w imm,reg", 1, "r5")
        b.emit("cmp.w imm,reg", 0, "r5")
        b.branch("bne", "xback")
        b.emit("mov.w reg,abs", "r4", c["WROWS"])
        b.branch("br", "xloop")
        b.label("xlate")
        b.emit("cmp.w abs,reg", c["WTARGET"], "r4")
        b.branch("bgt", "xdone")                                       # a restore: the next pass goes on
        b.emit("cmp.w imm,reg", 0, "r4")
        b.branch("bne", "xpart")
        b.emit("add.w imm,abs", 1, c["NLATEW"])
        b.emit("mov.w imm,abs", 0, c["WTARGET"])
        b.branch("br", "xdone")
        b.label("xpart")
        b.emit("add.w imm,abs", 1, c["NPART"])
        b.label("xdone")

    def row_addrs(self, b: Block, table: int) -> None:
        """R0 = the table's row and R1 the colour RAM's for order row R4 (channel R4 % 3, value 31 - R4 / 3). R2, R6 used."""
        b.emit("mov.w reg,reg", "r4", "r6")
        b.emit("mul.w imm,reg", 43, "r6")
        b.emit("shl.w imm,reg", -7, "r6")                              # R4 / 3 (exact for 0..95)
        b.emit("mov.w reg,reg", "r6", "r2")
        b.emit("mul.w imm,reg", 3, "r2")
        b.emit("mov.w reg,reg", "r4", "r0")
        b.emit("sub.w reg,reg", "r2", "r0")                            # R0 = the channel
        b.emit("mov.w imm,reg", 31, "r2")
        b.emit("sub.w reg,reg", "r6", "r2")                            # R2 = the value
        b.emit("mov.w reg,reg", "r0", "r1")
        b.emit("shl.w imm,reg", 14, "r1")
        b.emit("mov.w reg,reg", "r2", "r6")
        b.emit("shl.w imm,reg", 9, "r6")
        b.emit("add.w reg,reg", "r6", "r1")
        b.emit("add.w imm,reg", XLAT, "r1")
        b.emit("shl.w imm,reg", 5, "r0")
        b.emit("add.w reg,reg", "r2", "r0")
        b.emit("mul.w imm,reg", 2 * ROW_ENTRIES, "r0")
        b.emit("add.w imm,reg", table, "r0")

    def bolt(self, b: Block) -> None:
        """The bolt for level R9 (nonzero): not under cover; after the guard; within the frame's budget (BOLT_RECORDS, the largest
        object: a pass whose own lists leave less room draws none, NTRIMB); in front of the camera (view z BOLT_ZMIN or more); the
        world-fixed matrix (M x the bolt's frame) and the object entry at the list pointer."""
        c = self.c
        b.emit("cmp.b imm,abs", 0, self.COVER if "cover" not in self.fault else MODE)   # TEST ONLY "cover": never under cover
        b.branch("be" if "cover" not in self.fault else "bne", "b_open")
        b.emit("add.w imm,abs", 1, c["NCOVB"])
        b.branch("br", "done")
        b.label("b_open")
        emit_guard_time(b, "b_late")
        b.emit("mov.w abs,reg", REC_COUNT, "r0")
        b.emit("add.w imm,reg", self.k["records"], "r0")
        b.emit("cmp.w abs,reg", BUDGET, "r0")
        b.branch("ble", "b_room")
        b.emit("add.w imm,abs", 1, c["NTRIMB"])
        b.branch("br", "done")
        b.label("b_room")
        for a, r in (("WX", "r15"), ("WY", "r16"), ("WZ", "r17")):
            _f(b, "movf.s", ("abs", c[a]), r)
        _dot(b, ("r15", "r16", "r17"), (m(0), m(3), m(6)), "r1", "r0", add=m(9))
        _dot(b, ("r15", "r16", "r17"), (m(1), m(4), m(7)), "r2", "r0", add=m(10))
        _dot(b, ("r15", "r16", "r17"), (m(2), m(5), m(8)), "r3", "r0", add=m(11))
        b.emit("mov.w reg,abs", "r3", c["VIEWZ"])
        _f(b, "cmpf.s", ("f", BOLT_ZMIN), "r3")
        b.branch("bge", "b_front")
        b.emit("add.w imm,abs", 1, c["NZSKIP"])
        b.branch("br", "done")
        b.label("b_front")
        if self.measure:                                # TEST ONLY: s = TWIN_K / z ("twin") or 0 / z + 1 ("key"): the same code
            _f(b, "movf.s", ("f", TWIN_K if self.measure == "twin" else 0.0), "r10")
            _f(b, "divf.s", "r3", "r10")
            _f(b, "addf.s", ("f", 0.0 if self.measure == "twin" else 1.0), "r10")
            for r in ("r1", "r2", "r3"):
                _f(b, "mulf.s", "r10", r)
        b.emit("mov.w abs,reg", LIST_PTR, "r5")
        b.emit("mov.w imm,disp[reg]", 0xB, 0, "r5")
        # the matrix, column-major: col 0 = AXx (m0 m1 m2) + AXz (m6 m7 m8), col 1 = SB (m3 m4 m5), col 2 = AZx (m0..) + AZz (m6..)
        b.emit("mov.w imm,reg", 0, "r7")
        b.emit("mov.w reg,reg", "r5", "r8")
        b.label("mrow")
        for (kx, kz), off in ((("AXX", "AXZ"), 4), (("AZX", "AZZ"), 28)):
            _f(b, "movf.s", ("abs", c[kx]), "r0")
            _f(b, "mulf.s", ("absx", CAM, "r7"), "r0")
            _f(b, "movf.s", ("abs", c[kz]), "r4")
            _f(b, "mulf.s", ("absx", CAM + 24, "r7"), "r4")
            _f(b, "addf.s", "r4", "r0")
            if self.measure:
                _f(b, "mulf.s", "r10", "r0")
            b.emit("mov.w reg,disp[reg]", "r0", off, "r8")
        _f(b, "movf.s", ("abs", c["SBV"]), "r0")
        _f(b, "mulf.s", ("absx", CAM + 12, "r7"), "r0")
        if self.measure:
            _f(b, "mulf.s", "r10", "r0")
        b.emit("mov.w reg,disp[reg]", "r0", 16, "r8")
        b.emit("add.w imm,reg", 4, "r8")
        b.emit("add.w imm,reg", 1, "r7")
        b.emit("cmp.w imm,reg", 3, "r7")
        b.branch("blt", "mrow")
        b.emit("mov.w reg,disp[reg]", "r1", 40, "r5")
        b.emit("mov.w reg,disp[reg]", "r2", 44, "r5")
        b.emit("mov.w reg,disp[reg]", "r3", 48, "r5")
        b.emit("mov.w imm,disp[reg]", 1, 52, "r5")
        b.emit("mov.w imm,disp[reg]", self.k["tex"], 56, "r5")
        b.emit("cmp.w imm,reg", DIM_LEVEL, "r9")
        b.branch("bne", "tex_ok")
        b.emit("mov.w imm,disp[reg]", self.k["tex"] + 4, 56, "r5")     # the dim colours: the four words after
        b.label("tex_ok")
        b.emit("mov.w abs,disp[reg]", c["SHP"], 60, "r5")
        b.emit("mov.w abs,disp[reg]", BUDGET, 64, "r5")
        b.emit("add.w imm,reg", 68, "r5")
        b.emit("mov.w reg,abs", "r5", LIST_PTR)
        b.emit("add.w imm,abs", self.k["records"], REC_COUNT)
        b.emit("mov.w imm,abs", self.k["records"], c["REC"])
        b.emit("add.w imm,abs", 1, c["NBOLT"])
        b.branch("br", "done")
        b.label("b_late")
        b.emit("add.w imm,abs", 1, c["NLATEB"])

    # ---- the module's routines
    def block(self) -> Block:
        c = self.c
        b = Block(self.lay.code("lightning"))
        b.label("frame")
        b.emit("add.w imm,abs", 1, c["LF"])
        b.emit("mov.w imm,abs", 0, c["REC"])
        b.emit("cmp.w imm,abs", 0, c["INIT"])
        b.branch("bne", "inited")
        b.emit("mov.w imm,abs", 1, c["INIT"])                          # the first pass after a load (the cells are zeroed there)
        for k in range(3):
            b.emit("mov.w imm,abs", -1000, c[f"ON{k}"])
        b.label("inited")
        b.emit("mov.w imm,reg", 0, "r9")                               # R9 = this pass's level
        b.emit("cmp.w imm,abs", RUNNING, c["PHASE"])
        b.branch("be", "running")
        b.emit("cmp.w imm,abs", FRAMING, c["PHASE"])
        b.branch("be", "framing")
        b.emit("cmp.w imm,abs", PLACING, c["PHASE"])
        b.branch("be", "placing")
        # idle: the countdown, in the race only and once the rain's grade is complete
        b.emit("cmp.b imm,abs", RACE, MODE)
        b.branch("bne", "apply")
        b.emit("cmp.w imm,abs", 1, self.R_XSTATE)
        b.branch("bne", "apply")
        b.emit("cmp.w imm,abs", 0, self.R_XLEFT)
        b.branch("bne", "apply")
        b.emit("cmp.w imm,abs", 0, c["SEEDED"])
        b.branch("bne", "seeded")
        b.emit("mov.w imm,abs", 1, c["SEEDED"])                        # the first race frame: the seed, then the first strike scheduled
        b.emit("mov.w abs,reg", WHEEL[0], "r1")
        for w in WHEEL[1:]:
            b.emit("add.w abs,reg", w, "r1")
        b.emit("mul.w imm,reg", 0x9E3779B1, "r1")
        b.emit("add.w abs,reg", self.R_RAND, "r1")
        b.emit("mov.w reg,abs", "r1", c["RAND"])
        self.schedule(b, *self.every)
        b.label("seeded")
        b.emit("sub.w imm,abs", 1, c["NEXT"])
        b.emit("cmp.w imm,abs", 0, c["NEXT"])
        b.branch("bgt", "apply")
        emit_guard_time(b, "apply")                                    # the strike's start a unit too (late: the next pass begins it)
        self.begin(b)
        # the placement: PLACE_QUOTA tries a pass, each after the guard
        b.label("placing")
        b.emit("cmp.b imm,abs", RACE, MODE)
        b.branch("bne", "abort")
        b.emit("mov.w imm,reg", PLACE_QUOTA, "r20")
        b.label("ploop")
        emit_guard_time(b, "plate")
        self.try_(b, "pfound", "pnext", "plate")
        b.label("pnext")
        b.emit("sub.w imm,abs", 1, c["TRIES"])
        b.emit("cmp.w imm,abs", 0, c["TRIES"])
        b.branch("ble", "pend")
        b.emit("sub.w imm,reg", 1, "r20")
        b.emit("cmp.w imm,reg", 0, "r20")
        b.branch("bne", "ploop")
        b.branch("br", "apply0")                                       # the search goes on next pass
        b.label("plate")
        b.emit("add.w imm,abs", 1, c["NLATEP"])
        b.branch("br", "apply0")
        b.label("pend")                                                # no foot in sight: the least hidden, or no strike
        b.emit("cmp.w imm,abs", 0, c["HAVEV"])
        b.branch("be", "pfall")
        b.emit("add.w imm,abs", 1, c["NHIDDEN"])
        b.branch("br", "pfound")
        b.label("pfall")                                               # no valid foot in NTRY tries: no strike (fix round 1, F1)
        b.emit("add.w imm,abs", 1, c["NFALL"])
        b.branch("br", "abort")
        b.label("pfound")
        b.emit("mov.w imm,abs", FRAMING, c["PHASE"])
        # the bolt's frame and the interface's cells (a unit after the guard), then the timeline from this pass
        b.label("framing")
        b.emit("cmp.b imm,abs", RACE, MODE)
        b.branch("bne", "abort")
        emit_guard_time(b, "flate")
        self.frame_of_bolt(b)
        b.branch("br", "running")
        b.label("flate")
        b.emit("add.w imm,abs", 1, c["NLATEP"])
        b.label("apply0")
        b.emit("mov.w imm,reg", 0, "r9")
        b.branch("br", "apply")
        # the timeline: this pass's level (0xff ends it); the strike ends when the race does
        b.label("running")
        b.emit("cmp.b imm,abs", RACE, MODE)
        b.branch("bne", "abort")
        b.emit("mov.w abs,reg", c["PAT"], "r0")
        b.emit("add.w abs,reg", c["STEP"], "r0")
        b.emit("movz.bw [reg],reg", "r0", "r9")
        b.emit("add.w imm,abs", 1, c["STEP"])
        b.emit("cmp.w imm,reg", 0xFF, "r9")
        b.branch("bne", "safety")
        b.label("abort")
        b.emit("mov.w imm,abs", IDLE, c["PHASE"])
        b.emit("mov.w imm,reg", 0, "r9")
        b.branch("br", "apply")
        b.label("safety")
        self.safety(b)
        # ---- the level R9 applied: the sky, the colour RAM, the bolt
        b.label("apply")
        b.emit("movz.bw abs(reg),reg", self.FLASH_OF, "r9", "r2")
        b.emit("mov.w reg,abs", "r2", c["PREV"])
        b.emit("mov.w reg,abs", "r9", c["LEVEL"])
        self.sky(b)
        b.emit("mov.w imm,abs", 0, c["WTARGET"])
        b.emit("cmp.w imm,reg", WHITEOUT_LEVEL, "r9")
        b.branch("bne", "wt_ok")
        b.emit("cmp.b imm,abs", 0, self.COVER if "cover" not in self.fault else MODE)   # TEST ONLY "cover": never under cover
        b.branch("be" if "cover" not in self.fault else "bne", "wt_open")
        b.emit("add.w imm,abs", 1, c["NCOVW"])                         # under cover: no white-out (the sky flash stays)
        b.branch("br", "wt_ok")
        b.label("wt_open")
        b.emit("mov.w imm,abs", ROWS, c["WTARGET"])
        b.label("wt_ok")
        b.emit("push reg", "r9")
        self.xlat(b)
        b.emit("pop reg", "r9")
        b.emit("cmp.w imm,reg", 0, "r9")
        b.branch("be", "done")
        self.bolt(b)
        b.label("done")
        b.emit("rsr")
        # ---- release: the course's own sky back when palette RAM still holds a flash sky of ours (the rain's release, before this
        # one, puts the boot's colour table back: the grade and any white-out together; it leaves a flash sky alone)
        b.label("release")
        b.emit("mov.w abs,reg", c["PCUR"], "r2")
        b.emit("cmp.w imm,reg", 0, "r2")
        b.branch("be", "rl_done")
        b.emit("mov.w abs,reg", self.SKY + 4, "r3")
        b.emit("sub.w imm,reg", 1, "r2")
        b.emit("mul.w reg,reg", "r3", "r2")
        b.emit("shl.w imm,reg", 1, "r2")
        b.emit("add.w imm,reg", self.FLASH, "r2")                      # our flash sky's colours
        b.emit("mov.w abs,reg", self.SKY, "r1")
        for kk in (1, 2, 3):
            b.emit("movz.hw disp[reg],reg", 2 * kk, "r1", "r4")
            b.emit("movz.hw disp[reg],reg", 2 * kk, "r2", "r5")
            b.emit("cmp.w reg,reg", "r4", "r5")
            b.branch("bne", "rl_done")                                 # the game has written its own palette since: left as it is
        b.emit("mov.w imm,reg", self.OWN, "r0")
        emit_copy(b, "r0", "r1", "r3")
        b.label("rl_done")
        for n in ("PCUR", "WROWS", "WTARGET", "PHASE", "LEVEL", "PREV"):
            b.emit("mov.w imm,abs", 0, c[n])
        b.emit("rsr")
        return b


def cells() -> tuple[tuple[str, int], ...]:
    return (("state", 4 * len(STATE_NAMES)), ("strike_seq", 4), ("strike_band", 4))


FAULTS = ("band", "seq", "cover", "norule")       # test-only planted faults (tests/test_weather_lightning.py, VR_LIGHT_FAULT)


def course_blob(skies: bytes, grids: bytes) -> bytes:
    """A course's blob: its flash skies padded to FLASH_ROOM, then its grids (read at FLASH + FLASH_ROOM); PatchError when the skies
    do not fit FLASH_ROOM (three of more than 512 colours)."""
    if len(skies) > FLASH_ROOM:
        raise PatchError(f"a course's flash skies ({len(skies)} bytes) overrun FLASH_ROOM ({FLASH_ROOM}): the grids would move")
    return skies + b"\xff" * (FLASH_ROOM - len(skies)) + grids


def module(rs: RomSet, tune: LightningTune, patterns=PATTERNS, fault: tuple = (), refuse_all: bool = False,
           measure: str = "") -> carrier.Module:
    """Lightning as a carrier module: its code and cells; its tables in the image (the patterns and level tables, the direction and
    turn tables, the bolts' pointer table); its ROM (the 12 bolt objects packed in "lightning objects", their eight colour words in
    "lightning colours", and in "lightning data" (bank 3) the white-out table, then per course one blob: its three flash skies in
    FLASH_ROOM bytes and its grids); copied into RAM at the load: the white-out table by one record of the common list
    (`Module.copies`), the course's blob by one record an entry (`course_copies`). `patterns` is for one test only (a pattern
    denser than the rule allows: tests/test_weather_lightning.py); PATTERNS in every build. `fault` (FAULTS) and `refuse_all` (Big
    Forest's every foot cell refused, the grid not cropped: a placement there never finds a valid foot) are for tests only, off in
    every build. `measure` (MEASURES) is the bolt-visibility test's, "" in every build."""
    from vrtools.arcade.directory import decode_directory
    if measure not in ("",) + MEASURES:
        raise PatchError(f"lightning measure {measure!r}: one of {MEASURES} (test only) or none")
    from vrtools.arcade.weather import layout, rain
    objs = bolt_objects(tune.stroke_scale)
    pblk = layout.block("lightning objects")
    words, pos, packed = [], pblk.start, b""
    for o, _, _ in objs:
        words.append(pos // 4)
        packed += o
        pos += len(o)
    colours = layout.block("lightning colours")
    k = {"records": max(n for _, n, _ in objs), "tex": 0x40000 + (colours.start - V60_PROGRAM) // 2, "npat": len(patterns)}
    dtab, jt = angle_tables(tune.aim_deg)
    nent = len(decode_directory(rs))
    dblk = layout.block("lightning data")
    white = rain.table_bytes(whiteout_table())
    data = bytearray(white)
    course_at = {}
    for e in range(nent):
        bank, src, n, cols = rain.course_sky(rs, e)
        grey = rain.grey_sky(cols, e == rain.METROPOLIS)
        skies = b"".join(struct.pack(f"<{n}H", *flash_sky(grey, kk)) for kk in SKY_K)
        g, _ = grid_blob(rs, e)
        if refuse_all:                                  # TEST ONLY: Big Forest's whole grid refused (its occluders kept), the others
            _, o8, gs, gb = decode_grid_blob(g)         # emptied (the test races Big Forest only; whole grids for all do not fit)
            n_ = GRID_N if e == 0 else 1
            g = struct.pack("<6i", 0, 0, n_, n_, gs, gb) + bytes([GINV & 0xFF]) * (n_ * n_) + o8[:n_, :n_].tobytes()
            g += b"\0" * (-len(g) % 4)
        blob = course_blob(skies, g)
        course_at[e] = (dblk.start + len(data), len(blob))
        data += blob
    aim_at = {}                                         # task 8: a course's own aim range: its direction table after every blob
    for e, rng in tune.aim_by_entry:                    # (the other courses' blobs keep their places), copied over the image's
        if e >= nent:                                   # table by one record of its entry's list
            raise PatchError(f"lightning aim_by_entry: entry {e}, the set has {nent} entries")
        if tuple(rng) != tuple(tune.aim_deg):
            t = angle_tables(rng)[0]
            aim_at[e] = (dblk.start + len(data), len(t))
            data += t
    if len(data) > dblk.size:
        raise PatchError(f"the lightning's data ({len(data)} bytes) do not fit their block ({dblk.size})")

    def course_copies(e):
        out = {"course": (3, *course_at[e])}
        if e in aim_at:
            out[carrier.TABLE_COPY + "dirs"] = (3, *aim_at[e])
        return out
    return carrier.Module(
        name="lightning", code=lambda lay: Lightning(lay, k, tune, fault, measure).block(), cells=cells(),
        tables=(("patterns", pattern_table(patterns)), ("dirs", dtab), ("turns", jt), ("bolts", struct.pack(f"<{len(words)}I", *words))),
        course_copies=course_copies, copies=(("whiteout", (3, dblk.start, len(white))),),
        rom=(("lightning objects", packed), ("lightning colours", struct.pack("<8H", *(key_colour_words(rs) if measure else bolt_colour_words(rs)))),
             ("lightning data", bytes(data))),
        frame="frame", release="release")
