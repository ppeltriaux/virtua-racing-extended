"""Weather stage 3: cover. No rain under tunnels and roofs, rain seen again through the exit (spec 5.4), as Pascal approved it: "the
long tunnel in metropolis is perfect" (spike 57), then of the roof by the pits, after three rounds, "short tunnel is good" (spike
68, 7c7331e). A module of the storm's carrier (weather/carrier.py: its RAM contract), registered before the rain: its frame routine
runs first in a SHOW pass and writes the cell `under_cover`; the rain consults it for every cluster (weather/rain.py).

Pascal, 18 Nov 2026: "i think for the visual, we also need to stop the rain inside the tunnels, and show it again toward the exit
when we see the tunnel exit. can you look into this? think extra hard and ask questions". Of the roof by the pits, on the way: "i
felt like it was drawing water outside of the tunnel exit while i was still inside the tunnel, can you check? think extra hard"
(spike 61), "it looks like rain is missing on the right side of the tunnel from inside." (spike 65), "for short tunnel, rain feels
like it s not using the full section of the end tunnel think extra hard" (spike 68).

Ported (rewritten from the listings, the values unchanged) from spike 57's FRAME57 and CL57 with spikes 61-68's SIL57, WIN57 and
PD57 (`spike/p57_rain.py`), as spike 70 joined them (the table per course). Where it differs, each for a gate: every unit of its
work is preceded by the time guard and stays under carrier.UNIT_MAX_US (the prototype tested the time before each cluster, before a
placement and before nothing else); it never writes the rain's cells (the rain passes the car's ground in and takes the cluster's
back in registers; the generator and a new shape are the rain's entries `rand` and `shape`).

THE CELLS (the interface: the shared context of the parallel tracks)
  under_cover (byte): 1 on a pass whose camera is under cover (mode 2 or 3, below), else 0; written by `frame` before the rain's and
    the lightning's run (a late `frame` writes 1: the safe value). The lightning reads it: no bolt and no white-out under
    cover, the sky flash kept. Wet handling reads the game's own tunnel flag of the player's car instead (+0x152 bit 7).
  mode, walk, nosplash, g0m, tm (words of `state`): what the rain reads.

A PASS (the carrier's SHOW state)
  frame: the camera's world position C = -M^T t (the camera matrix 0x501b00; it trails the car by about 5 units); each stretch whose
    circle holds C, then each of its boxes within `near` of C in its own frame (at most NNEAR_MAX listed), and the box holding C
    (under a ROOFED box only below the roof: the game's high view puts the camera above it, outside). Mode 0: no box near;
    1: near, the camera outside (the nearest mouth's plane in view space, PL); 2: the camera inside, no exit in view; 3: the camera
    inside and a mouth in view (its box's build-time bit, and a point AIM units out of it within `exit_angle` of the view direction):
    the mouth's frame in view space (FR: U, S, H and the mouth's centre), its road as the curtain's ground (g0m, tm), FRESH on the
    first pass of a curtain; under a ROOFED box also nosplash, the walk cut to `roof_clusters`, the drops' ground 0.3 above the
    mouth's road and KCOV, the farthest view depth the end structure can have this pass.
  cluster (the rain's `jsr`, after a cluster's motion, in modes 1-3; R1-R3 the cluster's view position, R6 the cluster, R5 the
    display list, R14 / R10 the car's ground): returns R13 0 (the rain draws it) or 1 (not drawn by the rain, no splash), R12 the
    scale cap, R1-R3 its position, R14 / R10 the ground its drops land on, R5 past the single drops it drew; keeps R6 and R7.
      mode 1: hidden when inside a near box (margin MG) and behind the nearest mouth's plane (under a ROOFED box only below it);
      mode 2: hidden;
      mode 3, the long tunnel and the other marched stretches: the curtain, world-anchored in the mouth's frame (u s h per cluster in
        `cst`), placed again (random within D beyond the mouth, the placement's lateral bounds, 0..PH high; after the first pass in
        the top TOPBAND) when the rain relaunched it or the curtain is fresh; drawn at the capped scale; the renderer's sort hides
        what lies behind the portal, roof and walls (spike 57 checked it: "no drop over the walls/roof in any still");
      mode 3, the pits roof (ROOFED): the sort cannot be trusted (spike 61: its roof is a few huge triangles); `roof_clusters`
        clusters walked, the rest hidden; a cluster is placed ON THE END PLANE (ROOF_U0, below), at the lateral and height of a
        random sight line through the part of the end opening the screen shows (WIN) taken a random factor 1..kmax along it (kmax
        where the line meets the corridor's wall, the road or D); drawn whole when wholly inside the opening (or wholly deeper than
        the end structure, KCOV, and clear of the corridor walls), else drop by drop (single-drop objects, each drop tested against
        the opening and the walls); a loop breaker hides a cluster the rain brings back more than CLCALLS_MAX times in a pass.
  release: under_cover and the mode back to 0 (nothing outside the storm's RAM is changed).

ROOF_U0 (a finding, reported). Spike 68's code meant the pits roof's curtain to lie along the sight lines, u = -u0 (k - 1) beyond
the end plane, but the generator call before it overwrote R0 (-u0) with the generator's integer, which the float multiply reads as a
denormal (about 1e-39): every roof curtain cluster of the approved set lies on the end plane (measured on out/p68tunnels during a
pass under the roof: u from 4e-42 to 6e-39 on every cluster). What Pascal approved ("short tunnel is good") and spike 68's coverage
figures are that; the port places them at u = ROOF_U0 = 0 exactly. The intended depth was never seen by the owner. The session
lead's ruling (C1, 19 Nov 2026): the approved picture is the reference; a deviation from the prototype's intent, kept on purpose.

Units (carrier.UNIT_MAX_US 200 us between two guard tests; the float operations cost about 1.4 us each in MAME): frame's camera
position; each stretch's circle; each box; the mouths' in-view test; mode 1's plane; mode 3's frame in two parts, its ground and
KCOV; cluster's call (the rain's test before it); each near box of mode 1; a placement (WIN and the depth along the line); the
position and the tests after it; each single drop. Fixed quotas a pass (the prototype's): PLACE_MAX placements, PDMAX single drops."""
from __future__ import annotations

import math
import struct

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet
from vrtools.arcade.v60asm import Block
from vrtools.arcade.weather import carrier, cover_geom
from vrtools.arcade.weather.carrier import BUDGET, REC_COUNT, emit_guard_time
from vrtools.arcade.weather.tune import CoverTune, RainTune

CAM = 0x501B00
PY = 0x400D22                           # the player's car's y (rain.PY)
LOW_VIEW_MAX = 10.0                     # a view is low (the chase and cockpit views) while its camera is less than this above the car
                                        # (fix round 2, R2-4; measured in the three marched tunnels: VR1 0.5-1.2, VR2 0.7-2.2, VR3
                                        # 3.4-6.3, the high view VR4 14.3-23.3)
NNEAR_MAX = 12                          # near boxes listed at most (fix round 2, R2-2: every box within reach of a camera up to 25 units
                                        # off any road point of the three courses, 10 at most (Alpine); 6 dropped boxes in table order)
MG = 1.0                                # mode 1: a cluster this far outside a box still hidden
AIM = 20.0                              # the in-view test aims at the mouth's centre + AIM x outward
BIG = 1.0e9
TOPBAND = 0.3                           # after a curtain's first pass, clusters are placed in the top TOPBAND of its height
ZC = 3.0                                # a curtain cluster nearer than this view depth is placed again
PLACE_MAX = 90                          # curtain placements a pass at most
FALL = 0.32                             # the rain's fall a pass (rain.FALL)
CLCALLS_MAX = 4                         # the pits roof's loop breaker: visits of one cluster a pass
# The register contract of `cluster` (the rain's per-cluster call, weather/rain.py; fix round 1, F1): the rain enters with
# CLUSTER_INPUTS defined (R1-R3 the cluster's view position, R5 the list, R6 the cluster, R7 its loop count, R10 / R14 the car's
# ground) and reads CLUSTER_RETURNS after the call (R1-R3 the position stored again, R5 the list advanced by the single drops, R10 /
# R14 the drops' ground, R12 the scale cap, R13 drawn or not); every other register the rain reads after the call (R6, R7) the
# cover never writes. tests/test_weather_cover.py's test_the_cover_keeps_the_rains_live_registers derives the rain's live set and
# checks both from the emitted code.
CLUSTER_INPUTS = ("r1", "r2", "r3", "r5", "r6", "r7", "r10", "r14")
CLUSTER_RETURNS = ("r1", "r2", "r3", "r5", "r10", "r12", "r13", "r14")
CALLEE_RETURNS = {"pd": ("r5",)}          # the cover's own subroutines' results: pd advances R5 past the single drops it writes
ROOF_U0 = 0.0                           # the pits roof's curtain depth beyond the end plane: 0, ON the plane, as the approved prototype
                                        # drew it (its code meant a depth along the sight lines; an overwritten register made it 0:
                                        # the docstring's ROOF_U0). Kept on purpose (the session lead's ruling C1, docs/deviations.md):
                                        # do not "fix" it to the prototype's intent without the owner seeing the change
KM, SM_SIL, HM_SIL = 3.5, 0.1, 0.35     # the pits roof: a cluster's spread at the opening per unit of lam; the margins at the opening
GCAP_SIL = 1.5                          # the pits roof's cluster scale cap (spike 65: the smaller spread brings rain nearer the edges)
KDEPTH = 1.2 * GCAP_SIL + 0.5           # a cluster's drops reach this much nearer than its centre
PDMAX = 160                             # single drops a pass at most
TBS = 1.5                               # the top band: crossings this far above the visible opening's top edge
CMP, CEPS = 0.3, 0.01                   # placement this far inside the corridor walls; a sight line this flat meets no wall
WM = 2.31 * GCAP_SIL + 0.3              # a whole cluster's spread from the corridor walls
DW = 0.15                               # a drop's half width at a wall
SMAX = 0.30                             # the rain's slant at most (rain.SMAX: a drop's width across, slant included)
ZG = 14.0                               # clusters grow as max(1, z / ZG) (rain.ZG)
CLSZ = 32                               # a rain cluster's bytes
CSTSZ = 16                              # a cluster's curtain state: u s h sig
CST_U, CST_S, CST_H, CST_SIG = 0, 4, 8, 12                  # its fields
CL_OBJ, CL_TILT, CL_LANDED, CL_SHAPE = 12, 16, 24, 28       # the rain's cluster record (weather/rain.py): object, tilt word, drops
                                                            # landed, shape x NDROP x 8
PD_CX, PD_CY, PD_HX, PD_HY = 0, 4, 8, 12                    # a single drop's entry of the drop table: centre, half width, half height
NDROP, NSHAPE = 5, 8
STATE = ("MODE INBOX MOUTH NNEAR HIDDEN PLACED CX CY CZ CURDRAWN LASTMODE FRESH G0M TM SILF LASTCL CLCALLS PDL PDS PDH PDE KCOV "
         "PDMODE PDCOUNT WALK NOSPLASH G0C TC NFRAMES LATE").split()
NEARL, PL, FR = 4 * len(STATE), 4 * len(STATE) + 4 * NNEAR_MAX, 4 * len(STATE) + 4 * NNEAR_MAX + 16
STATE_BYTES = FR + 60                   # FR: U(3) u0 S(3) s0 H(3) h0 Mc(3)


def cell(lay: carrier.Layout, name: str) -> int:
    """The address of one of the cover's state words (STATE's names; "NEARL", "PL", "FR" the arrays)."""
    base = lay.cell("cover", "state")
    if name in ("NEARL", "PL", "FR"):
        return base + {"NEARL": NEARL, "PL": PL, "FR": FR}[name]
    return base + 4 * STATE.index(name)


def F(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _kind(x):
    if isinstance(x, str):
        return "reg", (x,)
    if x[0] == "f":
        return "imm", (float(x[1]),)
    if x[0] == "abs":
        return "abs", (x[1],)
    return "disp[reg]", (x[1], x[2])


def fop(b: Block, op: str, src, dst) -> None:
    """A float instruction `op src, dst` (dst op= src; cmpf.s: the flags of dst - src): a register, ("f", x), ("abs", a) or
    ("disp", d, reg) each."""
    (ks, a), (kd, c) = _kind(src), _kind(dst)
    b.emit(f"{op} {ks},{kd}", *a, *c)


def D(off, reg):
    return ("disp", off, reg)


def A(addr):
    return ("abs", addr)


def single_drop_objects(rt: RainTune) -> tuple[list[bytes], int, int]:
    """The rain's 8 shapes' drops one by one (the rain's crossed strips at its width and head share, v0.4.1), sorted by their bottom
    as the drop table (40 objects, padded to one stride): (objects, stride, records each). The colour words are the first of the
    rain's colour table's set for the drop's band (a single drop's records are the full object's first: head, tail, jump, head,
    tail)."""
    from vrtools.arcade.weather import rain
    objs = []
    for meta in rain.shapes(width=rt.width):
        for bx in sorted(meta, key=lambda bx: bx[1] - bx[3] / 2):
            objs.append(rain.cluster_object([rain.strips(*bx, rt.head)]))
    stride = (max(len(o[0]) for o in objs) + 3) & ~3
    recs = {o[1] for o in objs}
    if len(recs) != 1:
        raise PatchError(f"the single drops have {sorted(recs)} records, not one count")
    return [o[0] + b"\0" * (stride - len(o[0])) for o in objs], stride, recs.pop()


def drop_table(rt: RainTune) -> bytes:
    """Per shape and drop (in bottom order): its centre x, y, half width across and half height (4 floats); the crossed strips' half
    width across is w / 2 whatever the view (v0.4's turned boxes: a (|cos| + |sin|))."""
    from vrtools.arcade.weather import rain
    out = b""
    for meta in rain.shapes(width=rt.width):
        for x, y, w, h, th in sorted(meta, key=lambda bx: bx[1] - bx[3] / 2):
            out += struct.pack("<4f", x, y, w / 2, h / 2)
    return out


class Cover:
    """The cover's code for one Layout: `block()` is its Block (labels frame, cluster, release)."""

    def __init__(self, lay: carrier.Layout, k: dict, tune: CoverTune, twin: bool = False, fault: str | None = None):
        from vrtools.arcade.weather import rain
        self.lay, self.k, self.t, self.twin, self.fault = lay, k, tune, twin, fault
        self.c = {n: cell(lay, n) for n in STATE + ["NEARL", "PL", "FR"]}
        self.UC = lay.cell("cover", "under_cover")
        self.CST = lay.cell("cover", "cst")
        self.T = lay.data_at("cover", "table")
        self.PDT = lay.table("cover", "drops")
        self.CL = lay.cell("rain", "clusters")
        self.SLV = rain.cell(lay, "SLV")
        self.R = {n: rain.cell(lay, n) for n in ("LEANK", "LEANT", "PN", "PM", "PF", "CUTA", "CUTB")}   # the rain's pass choices
        self.RAND = lay.label("rain", "rand")
        self.SHAPE = lay.label("rain", "shape")

    def m(self, k: int) -> int:
        return CAM + 4 * k

    def rnd(self, b: Block, dst: str) -> None:
        """dst = a float in [0, 1) from the rain's generator (R0 used)."""
        b.emit("jsr abs", self.RAND)
        if dst != "r0":
            b.emit("mov.w reg,reg", "r0", dst)

    def vec(self, b: Block, xs, coefs, dst: str, tmp: str) -> None:
        """dst = sum xs[i] coefs[i] (xs registers or operands; coefs operands)."""
        for i, (x, cf) in enumerate(zip(xs, coefs)):
            r = dst if i == 0 else tmp
            if isinstance(x, str):
                b.emit("mov.w reg,reg", x, r)
            else:
                fop(b, "movf.s", x, r)
            fop(b, "mulf.s", cf, r)
            if i:
                fop(b, "addf.s", tmp, dst)

    def ptr(self, b: Block, off: int, base: str, dst: str) -> None:
        """dst = the table's address of the offset at [base + off]."""
        b.emit("mov.w disp[reg],reg", off, base, dst)
        b.emit("add.w imm,reg", self.T, dst)

    def tops(self, b: Block, box: str, dst: str, pa: str, pb: str, tmp: str, q: str) -> None:
        """dst = the higher of the box's stretch's two mouths' tops (road + H). Uses pa pb tmp dst (`box` may be pb)."""
        self.ptr(b, cover_geom.BOX_MOUTH, box, pa)
        self.ptr(b, cover_geom.BOX_MOUTH + 4, box, pb)
        fop(b, "movf.s", D(cover_geom.MOUTH_MY, pa), dst)
        fop(b, "addf.s", D(cover_geom.MOUTH_H, pa), dst)
        fop(b, "movf.s", D(cover_geom.MOUTH_MY, pb), tmp)
        fop(b, "addf.s", D(cover_geom.MOUTH_H, pb), tmp)
        fop(b, "cmpf.s", dst, tmp)
        b.branch("ble", q)
        b.emit("mov.w reg,reg", tmp, dst)
        b.label(q)

    # ================================================================================================================ frame
    def frame(self, b: Block) -> None:
        c, m = self.c, self.m
        b.label("frame")
        b.emit("add.w imm,abs", 1, c["NFRAMES"])
        b.emit("mov.w imm,abs", self.k["clusters"], c["WALK"])     # before the first guard (fix round 1, M2: the rain's loop walks it)
        emit_guard_time(b, "f_late")
        for n in ("MODE", "INBOX", "MOUTH", "NNEAR", "HIDDEN", "PLACED", "CURDRAWN", "SILF", "LASTCL", "PDCOUNT", "NOSPLASH"):
            b.emit("mov.w imm,abs", 0, c[n])
        b.emit("cmp.w imm,abs", 0, self.T)
        b.branch("be", "f_end")                         # no stretch on this course
        for k_, r in ((9, "r15"), (10, "r16"), (11, "r17")):
            fop(b, "movf.s", A(m(k_)), r)
        for k_, dst in enumerate(("CX", "CY", "CZ")):      # C = -M^T t
            self.vec(b, ("r15", "r16", "r17"), (A(m(3 * k_)), A(m(3 * k_ + 1)), A(m(3 * k_ + 2))), "r9", "r0")
            fop(b, "negf.s", "r9", "r9")
            b.emit("mov.w reg,abs", "r9", c[dst])
        b.emit("mov.w imm,reg", c["NEARL"], "r8")
        b.emit("mov.w imm,reg", self.T + 4, "r10")
        b.emit("mov.w abs,reg", self.T, "r11")
        b.label("f_str")
        emit_guard_time(b, "f_late")
        fop(b, "movf.s", A(c["CX"]), "r0")
        fop(b, "subf.s", D(cover_geom.STR_CX, "r10"), "r0")
        fop(b, "mulf.s", "r0", "r0")
        fop(b, "movf.s", A(c["CZ"]), "r1")
        fop(b, "subf.s", D(cover_geom.STR_CZ, "r10"), "r1")
        fop(b, "mulf.s", "r1", "r1")
        fop(b, "addf.s", "r1", "r0")
        fop(b, "cmpf.s", D(cover_geom.STR_RR, "r10"), "r0")
        b.branch("bgt", "f_snext")
        self.ptr(b, cover_geom.STR_BOX, "r10", "r6")
        b.emit("mov.w disp[reg],reg", cover_geom.STR_NBOX, "r10", "r7")
        b.label("f_box")
        emit_guard_time(b, "f_late")                     # each box a unit
        fop(b, "movf.s", A(c["CX"]), "r0")
        fop(b, "subf.s", D(cover_geom.BOX_OX, "r6"), "r0")
        fop(b, "movf.s", A(c["CZ"]), "r1")
        fop(b, "subf.s", D(cover_geom.BOX_OZ, "r6"), "r1")
        b.emit("mov.w reg,reg", "r0", "r2")
        fop(b, "mulf.s", D(cover_geom.BOX_AX, "r6"), "r2")
        b.emit("mov.w reg,reg", "r1", "r4")
        fop(b, "mulf.s", D(cover_geom.BOX_AZ, "r6"), "r4")
        fop(b, "addf.s", "r4", "r2")                     # u
        b.emit("mov.w reg,reg", "r1", "r3")
        fop(b, "mulf.s", D(cover_geom.BOX_AX, "r6"), "r3")
        b.emit("mov.w reg,reg", "r0", "r4")
        fop(b, "mulf.s", D(cover_geom.BOX_AZ, "r6"), "r4")
        fop(b, "subf.s", "r4", "r3")                     # s
        near = self.t.near
        fop(b, "cmpf.s", ("f", -near), "r2")
        b.branch("blt", "f_next")
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_L, "r6", "r4")
        fop(b, "addf.s", ("f", near), "r4")
        fop(b, "cmpf.s", "r4", "r2")
        b.branch("bgt", "f_next")
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_SMIN, "r6", "r4")
        fop(b, "subf.s", ("f", near), "r4")
        fop(b, "cmpf.s", "r4", "r3")
        b.branch("blt", "f_next")
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_SMAX, "r6", "r4")
        fop(b, "addf.s", ("f", near), "r4")
        fop(b, "cmpf.s", "r4", "r3")
        b.branch("bgt", "f_next")
        b.emit("cmp.w imm,abs", NNEAR_MAX, c["NNEAR"])
        b.branch("bge", "f_full")
        b.emit("mov.w reg,[reg]", "r6", "r8")
        b.emit("add.w imm,reg", 4, "r8")
        b.emit("add.w imm,abs", 1, c["NNEAR"])
        b.label("f_full")
        fop(b, "cmpf.s", ("f", 0.0), "r2")
        b.branch("blt", "f_next")
        fop(b, "cmpf.s", D(cover_geom.BOX_L, "r6"), "r2")
        b.branch("bgt", "f_next")
        fop(b, "cmpf.s", D(cover_geom.BOX_SMIN, "r6"), "r3")
        b.branch("blt", "f_next")
        fop(b, "cmpf.s", D(cover_geom.BOX_SMAX, "r6"), "r3")
        b.branch("bgt", "f_next")
        # a box holds the camera only below its roof (fix round 1, F6: the high view above a tunnel is outside): a ROOFED box (the
        # pits roof, flat) below its end's top (road + H), as the prototype; a marched box while the view is low: the camera less
        # than LOW_VIEW_MAX above the player's car (fix round 2, R2-4: a tunnel's road rises and falls inside, so no mouth's top is
        # the roof there, and Bay Bridge's VR3 rides within half a unit of its roof's H: a margin, not H, separates the views)
        emit_guard_time(b, "f_late")
        self.ptr(b, cover_geom.BOX_MOUTH, "r6", "r12")
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_VIS, "r6", "r0")
        b.emit("and.w imm,reg", cover_geom.ROOFED, "r0")
        b.emit("cmp.w imm,reg", 0, "r0")
        b.branch("be", "f_hcar")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_MY, "r12", "r1")
        fop(b, "addf.s", D(cover_geom.MOUTH_H, "r12"), "r1")              # the roof's height (mouth 0: its road + H)
        fop(b, "cmpf.s", A(c["CY"]), "r1")
        b.branch("blt", "f_next")
        b.branch("br", "f_inbox")
        b.label("f_hcar")
        fop(b, "movf.s", A(PY), "r1")
        fop(b, "addf.s", ("f", LOW_VIEW_MAX), "r1")                       # a low view's camera is below this
        fop(b, "cmpf.s", A(c["CY"]), "r1")
        b.branch("blt", "f_next")
        b.label("f_inbox")
        b.emit("mov.w reg,abs", "r6", c["INBOX"])
        b.label("f_next")
        b.emit("add.w imm,reg", cover_geom.BOXSZ, "r6")
        b.emit("sub.w imm,reg", 1, "r7")
        b.emit("cmp.w imm,reg", 0, "r7")
        b.branch("bne", "f_box")
        b.label("f_snext")
        b.emit("add.w imm,reg", cover_geom.STRSZ, "r10")
        b.emit("sub.w imm,reg", 1, "r11")
        b.emit("cmp.w imm,reg", 0, "r11")
        b.branch("bne", "f_str")
        b.emit("cmp.w imm,abs", 0, c["NNEAR"])
        b.branch("be", "f_end")
        b.emit("mov.w imm,abs", 1, c["MODE"])
        b.emit("cmp.w imm,abs", 0, c["INBOX"])
        b.branch("be", "f_m1")
        b.emit("mov.w abs,reg", c["INBOX"], "r9")
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_VIS, "r9", "r0")
        b.emit("and.w imm,reg", cover_geom.OPEN, "r0")
        b.emit("cmp.w imm,reg", 0, "r0")
        b.branch("bne", "f_m1")
        b.emit("mov.w imm,abs", 2, c["MODE"])
        cos2 = math.cos(math.radians(self.t.exit_angle)) ** 2
        for k_ in range(2):                             # a mouth in view: its box sees it and it is within exit_angle of the view
            q = f"f_m{k_}"
            emit_guard_time(b, "f_late")
            b.emit("mov.w disp[reg],reg", cover_geom.BOX_VIS, "r9", "r0")
            b.emit("and.w imm,reg", 1 << k_, "r0")
            b.emit("cmp.w imm,reg", 0, "r0")
            b.branch("be", q + "n")
            self.ptr(b, cover_geom.BOX_MOUTH + 4 * k_, "r9", "r12")
            b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_OX, "r12", "r0")
            fop(b, "mulf.s", ("f", AIM), "r0")
            fop(b, "addf.s", D(cover_geom.MOUTH_MX, "r12"), "r0")
            fop(b, "subf.s", A(c["CX"]), "r0")
            b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_OZ, "r12", "r1")
            fop(b, "mulf.s", ("f", AIM), "r1")
            fop(b, "addf.s", D(cover_geom.MOUTH_MZ, "r12"), "r1")
            fop(b, "subf.s", A(c["CZ"]), "r1")
            b.emit("mov.w reg,reg", "r0", "r2")
            fop(b, "mulf.s", A(m(2)), "r2")
            b.emit("mov.w reg,reg", "r1", "r4")
            fop(b, "mulf.s", A(m(8)), "r4")
            fop(b, "addf.s", "r4", "r2")
            fop(b, "cmpf.s", ("f", 0.0), "r2")
            b.branch("ble", q + "n")
            fop(b, "mulf.s", "r2", "r2")
            b.emit("mov.w reg,reg", "r0", "r3")
            fop(b, "mulf.s", "r0", "r3")
            b.emit("mov.w reg,reg", "r1", "r4")
            fop(b, "mulf.s", "r1", "r4")
            fop(b, "addf.s", "r4", "r3")
            fop(b, "movf.s", A(m(2)), "r4")
            fop(b, "mulf.s", "r4", "r4")
            fop(b, "movf.s", A(m(8)), "r5")
            fop(b, "mulf.s", "r5", "r5")
            fop(b, "addf.s", "r5", "r4")
            fop(b, "mulf.s", "r4", "r3")
            fop(b, "mulf.s", ("f", cos2), "r3")
            fop(b, "cmpf.s", "r3", "r2")
            b.branch("blt", q + "n")
            b.emit("mov.w reg,abs", "r12", c["MOUTH"])
            b.emit("mov.w imm,abs", 3, c["MODE"])
            b.branch("br", "f_m3")
            b.label(q + "n")
        b.branch("br", "f_end")
        # ---- mode 1: the nearest mouth of the first near box's stretch: its plane in view space (N = M o, n0 = -N.t - o.Mc)
        b.label("f_m1")
        emit_guard_time(b, "f_late")
        b.emit("mov.w abs,reg", c["NEARL"], "r9")
        self.ptr(b, cover_geom.BOX_MOUTH, "r9", "r12")
        self.ptr(b, cover_geom.BOX_MOUTH + 4, "r9", "r13")
        for reg, dst in (("r12", "r2"), ("r13", "r3")):
            fop(b, "movf.s", A(c["CX"]), dst)
            fop(b, "subf.s", D(cover_geom.MOUTH_MX, reg), dst)
            fop(b, "mulf.s", dst, dst)
            fop(b, "movf.s", A(c["CZ"]), "r4")
            fop(b, "subf.s", D(cover_geom.MOUTH_MZ, reg), "r4")
            fop(b, "mulf.s", "r4", "r4")
            fop(b, "addf.s", "r4", dst)
        fop(b, "cmpf.s", "r2", "r3")
        b.branch("bge", "f_m1a")
        b.emit("mov.w reg,reg", "r13", "r12")
        b.label("f_m1a")
        self.mframe(b, "r12", c["PL"], with_s=False)
        b.branch("br", "f_end")
        # ---- mode 3: the mouth's frame in view space, its road as the curtain's ground, the roof's own settings
        b.label("f_m3")
        self.mframe(b, "r12", c["FR"], with_s=True)
        emit_guard_time(b, "f_late")
        self.vec(b, ("r15", "r16", "r17"), (A(m(3)), A(m(4)), A(m(5))), "r1", "r0")
        fop(b, "addf.s", D(cover_geom.MOUTH_MY, "r12"), "r1")
        fop(b, "divf.s", A(m(4)), "r1")
        self.clamp(b, "r1", -32.0, 32.0, "f_cg")
        b.emit("mov.w reg,abs", "r1", c["G0M"])
        fop(b, "movf.s", A(m(5)), "r2")
        fop(b, "negf.s", "r2", "r2")
        fop(b, "divf.s", A(m(4)), "r2")
        self.clamp(b, "r2", -0.6, 0.6, "f_ct")
        b.emit("mov.w reg,abs", "r2", c["TM"])
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_VIS, "r9", "r0")     # a ROOFED stretch: its own curtain, no splash this pass
        b.emit("and.w imm,reg", cover_geom.ROOFED, "r0")
        b.emit("mov.w reg,abs", "r0", c["SILF"])
        b.emit("cmp.w imm,reg", 0, "r0")
        b.branch("be", "f_ncl")
        b.emit("mov.w imm,abs", 1, c["NOSPLASH"])
        fop(b, "movf.s", A(c["G0M"]), "r0")
        fop(b, "addf.s", ("f", 0.3), "r0")               # the drops land 0.3 above the mouth's road (none sunk at the opening)
        b.emit("mov.w reg,abs", "r0", c["G0M"])
        b.emit("mov.w imm,abs", self.t.roof_clusters, c["WALK"])
        emit_guard_time(b, "f_late")
        fop(b, "movf.s", D(cover_geom.MOUTH_MZ, "r12"), "r3")              # KCOV: the largest view z of the end structure's box corners
        fop(b, "mulf.s", A(m(8)), "r3")
        fop(b, "addf.s", A(m(11)), "r3")
        fop(b, "movf.s", ("f", -1.0e9), "r4")
        for xo in (cover_geom.MOUTH_KX0, cover_geom.MOUTH_KX1):
            for yo in (cover_geom.MOUTH_KY0, cover_geom.MOUTH_KY1):
                fop(b, "movf.s", D(xo, "r12"), "r0")
                fop(b, "mulf.s", A(m(2)), "r0")
                fop(b, "movf.s", D(yo, "r12"), "r1")
                fop(b, "mulf.s", A(m(5)), "r1")
                fop(b, "addf.s", "r1", "r0")
                fop(b, "addf.s", "r3", "r0")
                fop(b, "cmpf.s", "r4", "r0")
                b.branch("ble", f"f_kc{xo}{yo}")
                b.emit("mov.w reg,reg", "r0", "r4")
                b.label(f"f_kc{xo}{yo}")
        b.emit("mov.w reg,abs", "r4", c["KCOV"])
        b.label("f_ncl")
        b.emit("mov.w imm,abs", 0, c["FRESH"])
        b.emit("cmp.w imm,abs", 3, c["LASTMODE"])
        b.branch("be", "f_end")
        b.emit("mov.w imm,abs", 1, c["FRESH"])
        b.label("f_end")
        b.emit("mov.w abs,abs", c["MODE"], c["LASTMODE"])
        b.emit("mov.b imm,abs", 0, self.UC)
        b.emit("cmp.w imm,abs", 2, c["MODE"])
        b.branch("blt", "f_out")
        b.emit("mov.b imm,abs", 0 if self.fault == "uc0" else 1, self.UC)     # TEST ONLY fault "uc0": stuck at 0
        b.label("f_out")
        b.emit("rsr")
        b.label("f_late")                               # late: the rain and the lightning draw nothing this pass; nothing of the
        b.emit("add.w imm,abs", 1, c["LATE"])           # rain shown if it ran (mode 2); the last mode kept; under_cover 1, the
        b.emit("mov.w imm,abs", 2, c["MODE"])           # safe value for the lightning (fix round 1, M1: a missed bolt is harmless,
        b.emit("mov.b imm,abs", 1, self.UC)             # a white-out inside a tunnel is not)
        b.emit("rsr")

    def clamp(self, b: Block, reg: str, lo: float, hi: float, q: str) -> None:
        fop(b, "cmpf.s", ("f", hi), reg)
        b.branch("ble", q + "a")
        fop(b, "movf.s", ("f", hi), reg)
        b.label(q + "a")
        fop(b, "cmpf.s", ("f", lo), reg)
        b.branch("bge", q + "b")
        fop(b, "movf.s", ("f", lo), reg)
        b.label(q + "b")

    def mframe(self, b: Block, mr: str, dst: int, with_s: bool) -> None:
        """The mouth (`mr`) in view space at `dst`: U = M o, u0 = -U.t - o.Mc; with_s also S = M n_o, s0, H = M up, h0 and
        Mc_v = M Mc + t (each part after a guard test). Loads R15-R17 = t; uses R0-R5."""
        m = self.m
        for k_, r in ((9, "r15"), (10, "r16"), (11, "r17")):
            fop(b, "movf.s", A(m(k_)), r)

        def rot(wx, wz, off):
            for k_ in range(3):
                fop(b, "movf.s", wx, "r0")
                fop(b, "mulf.s", A(m(k_)), "r0")
                fop(b, "movf.s", wz, "r1")
                fop(b, "mulf.s", A(m(6 + k_)), "r1")
                fop(b, "addf.s", "r1", "r0")
                b.emit("mov.w reg,abs", "r0", dst + off + 4 * k_)

        def offs(off):                                  # dst+off+12 = -(V . t) - R2
            self.vec(b, ("r15", "r16", "r17"), (A(dst + off), A(dst + off + 4), A(dst + off + 8)), "r0", "r1")
            fop(b, "addf.s", "r2", "r0")
            fop(b, "negf.s", "r0", "r0")
            b.emit("mov.w reg,abs", "r0", dst + off + 12)
        emit_guard_time(b, "f_late")
        rot(D(cover_geom.MOUTH_OX, mr), D(cover_geom.MOUTH_OZ, mr), 0)
        self.vec(b, (D(cover_geom.MOUTH_OX, mr), D(cover_geom.MOUTH_OZ, mr)), (D(cover_geom.MOUTH_MX, mr), D(cover_geom.MOUTH_MZ, mr)), "r2", "r1")
        offs(0)
        if not with_s:
            return
        emit_guard_time(b, "f_late")
        fop(b, "negf.s", D(cover_geom.MOUTH_OZ, mr), "r3")               # n_o = (-oz, ox)
        rot("r3", D(cover_geom.MOUTH_OX, mr), 16)
        fop(b, "movf.s", D(cover_geom.MOUTH_MX, mr), "r2")
        fop(b, "mulf.s", "r3", "r2")
        fop(b, "movf.s", D(cover_geom.MOUTH_MZ, mr), "r1")
        fop(b, "mulf.s", D(cover_geom.MOUTH_OX, mr), "r1")
        fop(b, "addf.s", "r1", "r2")
        offs(16)
        emit_guard_time(b, "f_late")
        for k_ in range(3):
            b.emit("mov.w abs,abs", m(3 + k_), dst + 32 + 4 * k_)
        fop(b, "movf.s", D(cover_geom.MOUTH_MY, mr), "r2")
        offs(32)
        for k_ in range(3):
            self.vec(b, (D(cover_geom.MOUTH_MX, mr), D(cover_geom.MOUTH_MY, mr), D(cover_geom.MOUTH_MZ, mr)), (A(m(k_)), A(m(3 + k_)), A(m(6 + k_))), "r0", "r1")
            fop(b, "addf.s", A(m(9 + k_)), "r0")
            b.emit("mov.w reg,abs", "r0", dst + 48 + 4 * k_)

    # ================================================================================================================ cluster
    def shape(self, b: Block) -> None:
        """A new shape and tilts for the cluster R6 (the rain's entry; R14-R20 kept)."""
        b.emit("jsr abs", self.SHAPE)

    def cluster(self, b: Block) -> None:
        c, m = self.c, self.m
        late = "c_hide"
        b.label("cluster")
        if self.fault == "ignore":                      # TEST ONLY fault: the cover ignored (every cluster drawn, splashes too)
            b.emit("mov.w imm,reg", 0, "r13")
            b.emit("mov.w imm,reg", F(BIG), "r12")
            b.emit("rsr")
        b.emit("mov.w reg,abs", "r14", c["G0C"])         # the car's ground, for a hidden cluster
        b.emit("mov.w reg,abs", "r10", c["TC"])
        b.emit("mov.w imm,reg", 0, "r13")
        b.emit("mov.w imm,reg", F(BIG), "r12")
        b.emit("cmp.w imm,abs", 2, c["MODE"])
        b.branch("be", "c_hide")
        b.branch("bgt", "c_cur")
        self._mode1(b, late)                            # mode 1
        # ---- mode 3
        b.label("c_cur")
        b.emit("cmp.w imm,abs", 0, c["SILF"])
        b.branch("bne", "s57")
        self._cst(b)
        b.emit("mov.w disp[reg],reg", CST_SIG, "r8", "r0")
        b.emit("cmp.w disp[reg],reg", CL_TILT, "r6", "r0")   # sig: the tilt word it was placed with (the rain's relaunch draws a new one)
        b.branch("bne", "c_place")
        b.emit("cmp.w imm,abs", 0, c["FRESH"])
        b.branch("bne", "c_place")
        fop(b, "movf.s", D(CST_U, "r8"), "r14")
        fop(b, "movf.s", D(CST_S, "r8"), "r15")
        fop(b, "movf.s", D(CST_H, "r8"), "r16")
        fop(b, "subf.s", ("f", FALL), "r16")
        fop(b, "movf.s", "r16", D(CST_H, "r8"))
        b.branch("br", "c_pos")
        b.label("c_place")
        b.emit("cmp.w imm,abs", PLACE_MAX, c["PLACED"])
        b.branch("bge", "c_hide")
        emit_guard_time(b, "c_hide")                    # a placement a unit (spike 61: none past the vblank)
        b.emit("add.w imm,abs", 1, c["PLACED"])
        b.emit("mov.w abs,reg", c["MOUTH"], "r9")
        self.rnd(b, "r14")
        fop(b, "mulf.s", D(cover_geom.MOUTH_D, "r9"), "r14")             # u in 0..D
        self.rnd(b, "r15")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_PMAX, "r9", "r4")
        fop(b, "subf.s", D(cover_geom.MOUTH_PMIN, "r9"), "r4")
        fop(b, "mulf.s", "r4", "r15")
        fop(b, "addf.s", D(cover_geom.MOUTH_PMIN, "r9"), "r15")             # s in pmin..pmax
        self.rnd(b, "r16")
        b.emit("cmp.w imm,abs", 0, c["FRESH"])
        b.branch("bne", "c_allh")
        fop(b, "mulf.s", ("f", -TOPBAND), "r16")
        fop(b, "addf.s", ("f", 1.0), "r16")              # the top band (falls into view)
        b.label("c_allh")
        fop(b, "mulf.s", D(cover_geom.MOUTH_PH, "r9"), "r16")             # h
        self.shape(b)
        b.emit("mov.w disp[reg],disp[reg]", CL_TILT, "r6", CST_SIG, "r8")
        b.emit("mov.w reg,disp[reg]", "r14", CST_U, "r8")
        b.emit("mov.w reg,disp[reg]", "r15", CST_S, "r8")
        b.emit("mov.w reg,disp[reg]", "r16", CST_H, "r8")
        b.label("c_pos")                                # v = Mc_v + u U + s S + h H
        b.emit("mov.w imm,reg", F(self.t.curtain_scale), "r12")
        self.position(b)
        b.emit("mov.w abs,reg", c["G0M"], "r14")
        b.emit("mov.w abs,reg", c["TM"], "r10")
        fop(b, "cmpf.s", ("f", ZC), "r3")               # passed by the camera, or too near: placed again next pass
        b.branch("bge", "c_zok")
        b.emit("mov.w imm,disp[reg]", 0, CST_SIG, "r8")
        b.branch("br", "c_hide")
        b.label("c_zok")
        b.emit("add.w imm,abs", 1, c["CURDRAWN"])
        if self.twin:                                   # TEST ONLY: the curtain never drawn (the pixel tests' twin)
            b.emit("mov.w imm,reg", 1, "r13")
        b.emit("rsr")
        b.label("c_hide")
        b.emit("mov.w imm,reg", 1, "r13")
        b.emit("add.w imm,abs", 1, c["HIDDEN"])
        b.emit("mov.w abs,reg", c["G0C"], "r14")
        b.emit("mov.w abs,reg", c["TC"], "r10")
        b.emit("rsr")
        self.sil(b)

    def _cst(self, b: Block) -> None:
        """R8 = the cluster's curtain state (`cst` + its index x 16)."""
        b.emit("mov.w reg,reg", "r6", "r8")
        b.emit("sub.w imm,reg", self.CL, "r8")
        b.emit("shl.w imm,reg", -1, "r8")
        b.emit("add.w imm,reg", self.CST, "r8")

    def position(self, b: Block) -> None:
        """R1-R3 = Mc_v + R14 U + R15 S + R16 H (the mouth's frame FR)."""
        fr = self.c["FR"]
        for k_, dst in enumerate(("r1", "r2", "r3")):
            self.vec(b, ("r14", "r15", "r16"), (A(fr + 4 * k_), A(fr + 16 + 4 * k_), A(fr + 32 + 4 * k_)), dst, "r0")
            fop(b, "addf.s", A(fr + 48 + 4 * k_), dst)

    def _mode1(self, b: Block, late: str) -> None:
        c, m = self.c, self.m
        # (the plane test's value is in R14's place: recomputed into R15 to keep R14 for the car's ground)
        self.vec(b, ("r1", "r2", "r3"), (A(c["PL"]), A(c["PL"] + 4), A(c["PL"] + 8)), "r15", "r16")
        fop(b, "addf.s", A(c["PL"] + 12), "r15")
        fop(b, "cmpf.s", ("f", MG), "r15")
        b.branch("bgt", "c_ret")
        b.emit("mov.w reg,reg", "r1", "r15")
        fop(b, "subf.s", A(m(9)), "r15")
        b.emit("mov.w reg,reg", "r2", "r16")
        fop(b, "subf.s", A(m(10)), "r16")
        b.emit("mov.w reg,reg", "r3", "r19")
        fop(b, "subf.s", A(m(11)), "r19")
        self.vec(b, ("r15", "r16", "r19"), (A(m(0)), A(m(1)), A(m(2))), "r17", "r0")     # Wx
        self.vec(b, ("r15", "r16", "r19"), (A(m(6)), A(m(7)), A(m(8))), "r18", "r0")     # Wz
        b.emit("mov.w imm,reg", c["NEARL"], "r8")
        b.emit("mov.w abs,reg", c["NNEAR"], "r9")
        b.label("c_nb")
        emit_guard_time(b, late)                         # each near box a unit
        b.emit("mov.w [reg],reg", "r8", "r0")
        b.emit("mov.w reg,reg", "r17", "r19")
        fop(b, "subf.s", D(cover_geom.BOX_OX, "r0"), "r19")
        b.emit("mov.w reg,reg", "r18", "r20")
        fop(b, "subf.s", D(cover_geom.BOX_OZ, "r0"), "r20")
        b.emit("mov.w reg,reg", "r19", "r15")
        fop(b, "mulf.s", D(cover_geom.BOX_AX, "r0"), "r15")
        b.emit("mov.w reg,reg", "r20", "r16")
        fop(b, "mulf.s", D(cover_geom.BOX_AZ, "r0"), "r16")
        fop(b, "addf.s", "r16", "r15")                   # u
        fop(b, "cmpf.s", ("f", -MG), "r15")
        b.branch("blt", "c_nbn")
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_L, "r0", "r16")
        fop(b, "addf.s", ("f", MG), "r16")
        fop(b, "cmpf.s", "r16", "r15")
        b.branch("bgt", "c_nbn")
        b.emit("mov.w reg,reg", "r20", "r15")
        fop(b, "mulf.s", D(cover_geom.BOX_AX, "r0"), "r15")
        b.emit("mov.w reg,reg", "r19", "r16")
        fop(b, "mulf.s", D(cover_geom.BOX_AZ, "r0"), "r16")
        fop(b, "subf.s", "r16", "r15")                   # s
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_SMIN, "r0", "r16")
        fop(b, "subf.s", ("f", MG), "r16")
        fop(b, "cmpf.s", "r16", "r15")
        b.branch("blt", "c_nbn")
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_SMAX, "r0", "r16")
        fop(b, "addf.s", ("f", MG), "r16")
        fop(b, "cmpf.s", "r16", "r15")
        b.branch("bgt", "c_nbn")
        # fix round 2, R2-1: a marched box hides every cluster within MG whatever its height while the view is low (the approved
        # prototype's CL57); only a high view (the camera LOW_VIEW_MAX or more above the car: above the roof) and the pits roof
        # (ROOFED) hide only below the mouths' higher top, so the rain falls on the roof there
        b.emit("mov.w disp[reg],reg", cover_geom.BOX_VIS, "r0", "r16")
        b.emit("and.w imm,reg", cover_geom.ROOFED, "r16")
        b.emit("cmp.w imm,reg", 0, "r16")
        b.branch("bne", "c_hrule")
        fop(b, "movf.s", A(PY), "r16")
        fop(b, "addf.s", ("f", LOW_VIEW_MAX), "r16")
        fop(b, "cmpf.s", A(self.c["CY"]), "r16")
        b.branch("bgt", "c_hide")                       # a low view: hidden
        b.label("c_hrule")
        self.tops(b, "r0", "r20", "r16", "r0", "r4", "c_tops")
        b.emit("mov.w reg,reg", "r1", "r19")
        fop(b, "subf.s", A(m(9)), "r19")
        fop(b, "mulf.s", A(m(3)), "r19")
        b.emit("mov.w reg,reg", "r2", "r15")
        fop(b, "subf.s", A(m(10)), "r15")
        fop(b, "mulf.s", A(m(4)), "r15")
        fop(b, "addf.s", "r15", "r19")
        b.emit("mov.w reg,reg", "r3", "r15")
        fop(b, "subf.s", A(m(11)), "r15")
        fop(b, "mulf.s", A(m(5)), "r15")
        fop(b, "addf.s", "r15", "r19")                   # Wy
        fop(b, "cmpf.s", "r20", "r19")
        b.branch("ble", "c_hide")
        # above the roof within the box (the rain falls on the roof): its drops never land (no splash on the car's ground plane
        # carried under the roof; fix round 2, R2-2); it is hidden once it falls below the top
        b.emit("mov.w imm,reg", F(-BIG), "r14")
        b.emit("mov.w imm,reg", 0, "r10")
        b.label("c_nbn")
        b.emit("add.w imm,reg", 4, "r8")
        b.emit("sub.w imm,reg", 1, "r9")
        b.emit("cmp.w imm,reg", 0, "r9")
        b.branch("bne", "c_nb")
        b.label("c_ret")
        b.emit("rsr")

    # ================================================================================================================ the pits roof
    def sil(self, b: Block) -> None:
        """SIL57: mode 3 under a ROOFED stretch (the roof by the pits)."""
        c = self.c
        b.label("s57")
        b.emit("cmp.w abs,reg", c["LASTCL"], "r6")       # the loop breaker: the same cluster back more than CLCALLS_MAX times
        b.branch("be", "s_again")
        b.emit("mov.w reg,abs", "r6", c["LASTCL"])
        b.emit("mov.w imm,abs", 0, c["CLCALLS"])
        b.label("s_again")
        b.emit("add.w imm,abs", 1, c["CLCALLS"])
        b.emit("cmp.w imm,abs", CLCALLS_MAX, c["CLCALLS"])
        b.branch("ble", "s_go")
        b.emit("mov.w imm,reg", 1, "r13")               # hidden, its drops never land this pass
        b.emit("mov.w imm,reg", F(-BIG), "r14")
        b.emit("mov.w imm,reg", 0, "r10")
        b.emit("rsr")
        b.label("s_go")
        b.emit("cmp.w imm,reg", self.CL + CLSZ * self.t.roof_clusters, "r6")
        b.branch("bge", "s_hide")
        self._cst(b)
        b.emit("mov.w abs,reg", c["MOUTH"], "r9")
        b.emit("mov.w disp[reg],reg", CST_SIG, "r8", "r0")
        b.emit("cmp.w disp[reg],reg", CL_TILT, "r6", "r0")
        b.branch("bne", "s_place")
        b.emit("cmp.w imm,abs", 0, c["FRESH"])
        b.branch("bne", "s_place")
        fop(b, "movf.s", D(CST_U, "r8"), "r14")
        fop(b, "movf.s", D(CST_S, "r8"), "r15")
        fop(b, "movf.s", D(CST_H, "r8"), "r16")
        fop(b, "subf.s", ("f", FALL), "r16")
        fop(b, "movf.s", "r16", D(CST_H, "r8"))
        b.branch("br", "s_pos")
        b.label("s_place")
        b.emit("cmp.w imm,abs", PLACE_MAX, c["PLACED"])
        b.branch("bge", "s_hide")
        emit_guard_time(b, "s_hide")
        b.emit("add.w imm,abs", 1, c["PLACED"])
        b.emit("jsr abs", self._win_label)              # s* h* over the part the screen shows
        b.emit("mov.w abs,reg", c["MOUTH"], "r9")
        b.emit("mov.w reg,reg", "r17", "r19")
        fop(b, "subf.s", A(c["FR"] + 28), "r19")         # s* - s0
        fop(b, "movf.s", A(c["FR"] + 12), "r0")
        fop(b, "negf.s", "r0", "r0")                     # -u0 (> 0)
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_D, "r9", "r20")
        fop(b, "addf.s", "r0", "r20")
        fop(b, "divf.s", "r0", "r20")                    # k at D: (D - u0) / -u0
        fop(b, "cmpf.s", ("f", CEPS), "r19")             # where the sight line meets a corridor wall
        b.branch("ble", "s_l2")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_PMAX, "r9", "r4")
        fop(b, "subf.s", ("f", CMP), "r4")
        b.branch("br", "s_l3")
        b.label("s_l2")
        fop(b, "cmpf.s", ("f", -CEPS), "r19")
        b.branch("bge", "s_lnone")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_PMIN, "r9", "r4")
        fop(b, "addf.s", ("f", CMP), "r4")
        b.label("s_l3")
        fop(b, "subf.s", A(c["FR"] + 28), "r4")
        fop(b, "divf.s", "r19", "r4")
        fop(b, "cmpf.s", "r20", "r4")
        b.branch("bge", "s_lnone")
        b.emit("mov.w reg,reg", "r4", "r20")
        b.label("s_lnone")
        fop(b, "movf.s", A(c["FR"] + 44), "r4")          # where it meets the road (looking down)
        fop(b, "subf.s", "r18", "r4")                    # h0 - h*
        fop(b, "cmpf.s", ("f", CEPS), "r4")
        b.branch("ble", "s_gnone")
        fop(b, "movf.s", A(c["FR"] + 44), "r12")
        fop(b, "divf.s", "r4", "r12")
        fop(b, "cmpf.s", "r20", "r12")
        b.branch("bge", "s_gnone")
        b.emit("mov.w reg,reg", "r12", "r20")
        b.label("s_gnone")
        fop(b, "cmpf.s", ("f", 1.001), "r20")
        b.branch("bge", "s_kok")
        fop(b, "movf.s", ("f", 1.001), "r20")
        b.label("s_kok")
        self.rnd(b, "r4")                                # k uniform in 1 .. kmax (the depth along the line)
        fop(b, "subf.s", ("f", 1.0), "r20")
        fop(b, "mulf.s", "r20", "r4")
        fop(b, "addf.s", ("f", 1.0), "r4")
        fop(b, "movf.s", ("f", ROOF_U0), "r14")          # u = ROOF_U0: ON THE END PLANE, as the approved prototype placed it
        b.emit("mov.w reg,reg", "r19", "r15")
        fop(b, "mulf.s", "r4", "r15")
        fop(b, "addf.s", A(c["FR"] + 28), "r15")         # s = s0 + (s* - s0) k
        b.emit("mov.w reg,reg", "r18", "r16")
        fop(b, "subf.s", A(c["FR"] + 44), "r16")
        fop(b, "mulf.s", "r4", "r16")
        fop(b, "addf.s", A(c["FR"] + 44), "r16")         # h = h0 + (h* - h0) k
        self.shape(b)
        b.emit("mov.w disp[reg],disp[reg]", CL_TILT, "r6", CST_SIG, "r8")
        b.emit("mov.w reg,disp[reg]", "r14", CST_U, "r8")
        b.emit("mov.w reg,disp[reg]", "r15", CST_S, "r8")
        b.emit("mov.w reg,disp[reg]", "r16", CST_H, "r8")
        b.label("s_pos")
        emit_guard_time(b, "s_hide")                    # the position and its tests a unit
        self.position(b)
        b.emit("mov.w abs,reg", c["G0M"], "r14")
        b.emit("mov.w abs,reg", c["TM"], "r10")
        b.emit("mov.w imm,reg", F(GCAP_SIL), "r12")
        fop(b, "cmpf.s", ("f", ZC), "r3")
        b.branch("bge", "s_zok")
        b.emit("mov.w imm,disp[reg]", 0, CST_SIG, "r8")
        b.branch("br", "s_hide")
        b.label("s_zok")
        b.emit("mov.w abs,reg", c["MOUTH"], "r9")
        b.emit("mov.w imm,abs", 0, c["PDMODE"])
        # the crossing of the sight line through the cluster with the end plane: lam = -u0 / (u - u0), s*, h*
        fop(b, "movf.s", A(c["FR"] + 12), "r17")
        fop(b, "movf.s", D(CST_U, "r8"), "r18")              # u
        fop(b, "subf.s", "r17", "r18")
        fop(b, "negf.s", "r17", "r17")
        fop(b, "divf.s", "r18", "r17")
        fop(b, "movf.s", A(c["FR"] + 28), "r18")
        fop(b, "movf.s", D(CST_S, "r8"), "r19")
        fop(b, "subf.s", "r18", "r19")
        fop(b, "mulf.s", "r17", "r19")
        fop(b, "addf.s", "r18", "r19")                   # s*
        fop(b, "movf.s", A(c["FR"] + 44), "r18")
        fop(b, "movf.s", D(CST_H, "r8"), "r20")
        fop(b, "subf.s", "r18", "r20")
        fop(b, "mulf.s", "r17", "r20")
        fop(b, "addf.s", "r18", "r20")                   # h*
        b.emit("mov.w reg,abs", "r17", c["PDL"])
        b.emit("mov.w reg,abs", "r19", c["PDS"])
        b.emit("mov.w reg,abs", "r20", c["PDH"])
        fop(b, "mulf.s", ("f", KM), "r17")               # the cluster's spread at the opening
        b.emit("mov.w reg,reg", "r17", "r11")            # v0.4.1: its height spread at the opening, the rain's streaks this
        fop(b, "mulf.s", A(self.R["LEANK"]), "r11")      # pass (LEANK: 1 at rest; R11, g, is set again before the rain uses it)
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMIN, "r9", "r4")    # wholly outside the opening: hidden
        fop(b, "subf.s", "r17", "r4")
        fop(b, "cmpf.s", "r4", "r19")
        b.branch("blt", "s_hide2")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMAX, "r9", "r4")
        fop(b, "addf.s", "r17", "r4")
        fop(b, "cmpf.s", "r4", "r19")
        b.branch("bgt", "s_hide2")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_H, "r9", "r4")
        fop(b, "addf.s", "r11", "r4")
        fop(b, "cmpf.s", "r4", "r20")
        b.branch("bgt", "s_hide2")
        b.emit("mov.w reg,reg", "r11", "r4")
        fop(b, "negf.s", "r4", "r4")
        fop(b, "cmpf.s", "r4", "r20")                    # wholly under the road at the opening
        b.branch("blt", "s_hide2")
        # every drop deeper than the end structure (KCOV): the sort clips it at the opening's edges; only the corridor's walls beyond
        # the end (long quads keyed by their far end) need care
        b.emit("mov.w reg,reg", "r3", "r0")
        fop(b, "subf.s", ("f", KDEPTH), "r0")
        fop(b, "movf.s", A(self.R["LEANT"]), "r4")       # v0.4.1: the leaning streaks reach nearer by the cluster's spread x LEANT
        fop(b, "mulf.s", ("f", 2.31 * GCAP_SIL), "r4")
        fop(b, "subf.s", "r4", "r0")
        fop(b, "cmpf.s", A(c["KCOV"]), "r0")
        b.branch("ble", "s_edges")
        b.emit("mov.w imm,abs", 1, c["PDMODE"])
        fop(b, "movf.s", D(CST_S, "r8"), "r15")              # s
        b.emit("mov.w reg,reg", "r15", "r0")             # the distance to the nearer corridor wall
        fop(b, "subf.s", D(cover_geom.MOUTH_PMIN, "r9"), "r0")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_PMAX, "r9", "r4")
        fop(b, "subf.s", "r15", "r4")
        fop(b, "cmpf.s", "r0", "r4")
        b.branch("bge", "s_dmin")
        b.emit("mov.w reg,reg", "r4", "r0")
        b.label("s_dmin")
        fop(b, "subf.s", ("f", DW), "r0")
        fop(b, "cmpf.s", ("f", 0.1), "r0")
        b.branch("blt", "s_hide2")
        self.g(b, "r4", "s_g")
        b.emit("mov.w reg,reg", "r4", "r18")
        fop(b, "mulf.s", ("f", 2.31), "r18")
        fop(b, "addf.s", ("f", 0.1), "r18")              # the half spread
        fop(b, "cmpf.s", "r18", "r0")
        b.branch("blt", "s_drops")                       # too near a wall for the whole cluster: drop by drop (walls only)
        b.branch("br", "s_whole")
        b.label("s_edges")                              # wholly inside the opening (and clear of the corridor walls): one object
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMIN, "r9", "r4")
        fop(b, "addf.s", "r17", "r4")
        fop(b, "addf.s", ("f", SM_SIL), "r4")
        fop(b, "cmpf.s", "r4", "r19")
        b.branch("blt", "s_drops")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMAX, "r9", "r4")
        fop(b, "subf.s", "r17", "r4")
        fop(b, "subf.s", ("f", SM_SIL), "r4")
        fop(b, "cmpf.s", "r4", "r19")
        b.branch("bgt", "s_drops")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_H, "r9", "r4")
        fop(b, "subf.s", "r11", "r4")
        fop(b, "subf.s", ("f", HM_SIL), "r4")
        fop(b, "cmpf.s", "r4", "r20")
        b.branch("bgt", "s_drops")
        fop(b, "cmpf.s", ("f", 0.3), "r20")              # its centre above the road at the opening
        b.branch("blt", "s_drops")
        fop(b, "movf.s", D(CST_S, "r8"), "r15")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_PMIN, "r9", "r4")
        fop(b, "addf.s", ("f", WM), "r4")
        fop(b, "cmpf.s", "r4", "r15")
        b.branch("blt", "s_drops")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_PMAX, "r9", "r4")
        fop(b, "subf.s", ("f", WM), "r4")
        fop(b, "cmpf.s", "r4", "r15")
        b.branch("bgt", "s_drops")
        b.label("s_whole")
        b.emit("add.w imm,abs", 1, c["CURDRAWN"])
        if self.twin:
            b.emit("mov.w imm,reg", 1, "r13")
        b.emit("rsr")
        b.label("s_drops")
        if not self.twin:                               # g and slant x g as the rain will take them, then the drops
            self.g(b, "r11", "s_pg")
            b.emit("mov.w abs,reg", self.SLV, "r4")
            fop(b, "mulf.s", "r11", "r4")
            b.emit("jsr abs", self._pd_label)
            b.emit("mov.w abs,reg", c["G0M"], "r14")    # the drops' ground again (pd used R14 as a temporary)
            b.emit("mov.w abs,reg", c["TM"], "r10")
            b.emit("mov.w imm,reg", F(GCAP_SIL), "r12")  # and the roof's scale cap (pd used R12 too: fix round 1, F1)
        b.emit("mov.w imm,reg", 1, "r13")               # the rain draws nothing more of it (and no splash)
        b.emit("rsr")
        b.label("s_hide")
        b.emit("mov.w imm,reg", 1, "r13")
        b.emit("add.w imm,abs", 1, c["HIDDEN"])
        b.emit("mov.w abs,reg", c["G0C"], "r14")
        b.emit("mov.w abs,reg", c["TC"], "r10")
        b.emit("mov.w imm,reg", F(BIG), "r12")          # no cap, as at the call's entry (win used R12: fix round 1, F1)
        b.emit("rsr")
        b.label("s_hide2")                              # out of the opening: hidden, the mouth's ground kept
        b.emit("mov.w imm,reg", 1, "r13")
        b.emit("add.w imm,abs", 1, c["HIDDEN"])
        b.emit("rsr")

    def g(self, b: Block, dst: str, q: str) -> None:
        """dst = the cluster's scale as the rain takes it: max(1, z / ZG) capped at GCAP_SIL (R3 = z)."""
        b.emit("mov.w reg,reg", "r3", dst)
        fop(b, "mulf.s", ("f", 1.0 / ZG), dst)
        fop(b, "cmpf.s", ("f", 1.0), dst)
        b.branch("bge", q + "1")
        fop(b, "movf.s", ("f", 1.0), dst)
        b.label(q + "1")
        fop(b, "cmpf.s", ("f", GCAP_SIL), dst)
        b.branch("ble", q + "2")
        fop(b, "movf.s", ("f", GCAP_SIL), dst)
        b.label(q + "2")

    def win(self, b: Block) -> None:
        """WIN57 (R9 the mouth): R17 s*, R18 h*: a crossing drawn uniformly over the part of the end opening the screen shows (the
        view axis meets the plane at (sa, ha), t along it; the screen spans about +-1.18 t across, 0.79 t up and 0.58 t down: +-1.3 t,
        0.9 t, 0.7 t), or the band just above that part's top edge after the curtain's first pass. Uses R0 R4 R12 R14-R20."""
        c = self.c
        fr = c["FR"]
        b.label("win")
        fop(b, "movf.s", A(fr + 12), "r14")
        fop(b, "negf.s", "r14", "r14")                   # -u0
        fop(b, "movf.s", A(fr + 8), "r15")               # the view axis along the outward direction
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMIN, "r9", "r16")   # the whole opening, as a start
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMAX, "r9", "r19")
        fop(b, "movf.s", ("f", 0.0), "r20")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_H, "r9", "r12")
        fop(b, "cmpf.s", ("f", 0.3), "r15")
        b.branch("blt", "w_draw")
        fop(b, "divf.s", "r15", "r14")                   # t
        fop(b, "movf.s", A(fr + 24), "r15")
        fop(b, "mulf.s", "r14", "r15")
        fop(b, "addf.s", A(fr + 28), "r15")              # sa
        b.emit("mov.w reg,reg", "r14", "r4")
        fop(b, "mulf.s", ("f", 1.3), "r4")
        b.emit("mov.w reg,reg", "r15", "r0")
        fop(b, "subf.s", "r4", "r0")
        fop(b, "addf.s", "r4", "r15")
        fop(b, "cmpf.s", "r16", "r0")
        b.branch("ble", "w_s1")
        b.emit("mov.w reg,reg", "r0", "r16")
        b.label("w_s1")
        fop(b, "cmpf.s", "r19", "r15")
        b.branch("bge", "w_s2")
        b.emit("mov.w reg,reg", "r15", "r19")
        b.label("w_s2")
        fop(b, "cmpf.s", "r16", "r19")
        b.branch("bgt", "w_s3")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMIN, "r9", "r16")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMAX, "r9", "r19")
        b.label("w_s3")
        fop(b, "movf.s", A(fr + 40), "r15")
        fop(b, "mulf.s", "r14", "r15")
        fop(b, "addf.s", A(fr + 44), "r15")              # ha
        b.emit("mov.w reg,reg", "r14", "r4")
        fop(b, "mulf.s", ("f", 0.7), "r4")
        b.emit("mov.w reg,reg", "r15", "r0")
        fop(b, "subf.s", "r4", "r0")
        fop(b, "cmpf.s", "r20", "r0")
        b.branch("ble", "w_h1")
        b.emit("mov.w reg,reg", "r0", "r20")
        b.label("w_h1")
        fop(b, "mulf.s", ("f", 0.9), "r14")
        fop(b, "addf.s", "r14", "r15")
        fop(b, "cmpf.s", "r12", "r15")
        b.branch("bge", "w_h2")
        b.emit("mov.w reg,reg", "r15", "r12")
        b.label("w_h2")
        fop(b, "cmpf.s", "r20", "r12")
        b.branch("bgt", "w_draw")
        fop(b, "movf.s", ("f", 0.0), "r20")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_H, "r9", "r12")
        b.label("w_draw")
        self.rnd(b, "r17")
        b.emit("mov.w reg,reg", "r19", "r4")
        fop(b, "subf.s", "r16", "r4")
        fop(b, "mulf.s", "r4", "r17")
        fop(b, "addf.s", "r16", "r17")                   # s*
        self.rnd(b, "r18")
        b.emit("cmp.w imm,abs", 0, c["FRESH"])
        b.branch("be", "w_top")
        b.emit("mov.w reg,reg", "r12", "r4")
        fop(b, "subf.s", "r20", "r4")
        fop(b, "mulf.s", "r4", "r18")
        fop(b, "addf.s", "r20", "r18")                   # h* over the window (the curtain's first pass)
        b.emit("rsr")
        b.label("w_top")
        fop(b, "mulf.s", ("f", TBS), "r18")
        fop(b, "addf.s", "r12", "r18")                   # just above the window's top edge: falls into view
        b.emit("rsr")

    def pd(self, b: Block) -> None:
        """PD57: a pits-roof curtain cluster on an edge, drawn drop by drop. In R1-R3 (the cluster), R4 (slant x g), R11 (g), R5 (the
        list), R6 (the cluster); PDL/PDS/PDH its lam, s*, h*. A drop j at (cx, cy) in the cluster is d = cx (g, 0, tilt) + cy (slant
        g K, g K, g T) in view space (v0.4.1: the rain's leaning y column this pass, K / T its LEANK / LEANT: (slant g, g, 0) at rest);
        its lateral and height in the mouth's frame move by t = S.d, th = H.d, its crossing by lam t, lam th; its half height in the
        margins is hy K (the streak's length this pass; its lean in depth is not tested: the crossing is the centre's). Drawn as the
        rain draws a cluster: the leaning matrix and the colour set of the cluster's band (the rain's PN / PM / PF by CUTA / CUTB).
        Each drop a unit (the guard before it). Keeps R1-R7 R10 R11; uses R0 R8 R9 R12-R20."""
        c, k = self.c, self.k
        fr = c["FR"]
        b.label("pd")
        self._cst(b)
        for ax, bx_, base in (("r14", "r15", fr + 16), ("r16", "r17", fr + 32)):   # As = g Sx + tilt Sz, Bs = K (sg Sx + g Sy) + g T Sz
            b.emit("mov.w reg,reg", "r11", ax)
            fop(b, "mulf.s", A(base), ax)
            fop(b, "movf.s", D(CL_TILT, "r6"), "r12")
            fop(b, "mulf.s", A(base + 8), "r12")
            fop(b, "addf.s", "r12", ax)
            b.emit("mov.w reg,reg", "r4", bx_)
            fop(b, "mulf.s", A(base), bx_)
            b.emit("mov.w reg,reg", "r11", "r12")
            fop(b, "mulf.s", A(base + 4), "r12")
            fop(b, "addf.s", "r12", bx_)
            fop(b, "mulf.s", A(self.R["LEANK"]), bx_)
            b.emit("mov.w reg,reg", "r11", "r12")
            fop(b, "mulf.s", A(self.R["LEANT"]), "r12")
            fop(b, "mulf.s", A(base + 8), "r12")
            fop(b, "addf.s", "r12", bx_)
        b.emit("mov.w disp[reg],reg", CL_LANDED, "r6", "r13")   # j from the landed count
        b.label("pd_loop")
        b.emit("cmp.w imm,reg", NDROP, "r13")
        b.branch("bge", "pd_done")
        b.emit("cmp.w imm,abs", PDMAX, c["PDCOUNT"])
        b.branch("bge", "pd_done")
        emit_guard_time(b, "pd_done")                   # each drop a unit
        b.emit("mov.w reg,reg", "r13", "r0")
        b.emit("shl.w imm,reg", 4, "r0")
        b.emit("mov.w disp[reg],reg", CL_SHAPE, "r6", "r9")
        b.emit("shl.w imm,reg", 1, "r9")                 # shape x 5 x 16
        b.emit("add.w reg,reg", "r9", "r0")
        b.emit("add.w imm,reg", self.PDT, "r0")          # the drop's entry: cx cy hx hy
        b.emit("mov.w abs,reg", c["MOUTH"], "r9")
        b.emit("mov.w reg,abs", "r0", c["PDE"])
        fop(b, "movf.s", D(PD_CY, "r0"), "r19")              # cy
        fop(b, "movf.s", D(PD_CX, "r0"), "r18")              # cx
        b.emit("mov.w reg,reg", "r18", "r20")
        fop(b, "mulf.s", "r14", "r20")
        b.emit("mov.w reg,reg", "r19", "r12")
        fop(b, "mulf.s", "r15", "r12")
        fop(b, "addf.s", "r12", "r20")                   # t = As cx + Bs cy
        fop(b, "mulf.s", "r16", "r18")
        fop(b, "mulf.s", "r17", "r19")
        fop(b, "addf.s", "r19", "r18")                   # th = Ah cx + Bh cy
        fop(b, "movf.s", D(CST_S, "r8"), "r19")
        fop(b, "addf.s", "r20", "r19")                   # s_j, clear of the corridor walls by its half width
        b.emit("mov.w abs,reg", c["PDE"], "r0")
        fop(b, "movf.s", D(PD_HY, "r0"), "r12")
        fop(b, "mulf.s", A(self.R["LEANK"]), "r12")
        fop(b, "mulf.s", ("f", SMAX), "r12")
        fop(b, "addf.s", D(PD_HX, "r0"), "r12")
        fop(b, "mulf.s", "r11", "r12")                   # g (hx + 0.3 hy K)
        fop(b, "addf.s", ("f", 0.05), "r12")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_PMIN, "r9", "r0")
        fop(b, "addf.s", "r12", "r0")
        fop(b, "cmpf.s", "r0", "r19")
        b.branch("blt", "pd_next")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_PMAX, "r9", "r0")
        fop(b, "subf.s", "r12", "r0")
        fop(b, "cmpf.s", "r0", "r19")
        b.branch("bgt", "pd_next")
        b.emit("cmp.w imm,abs", 0, c["PDMODE"])          # its crossing inside the opening by a drop's size (not when the sort clips)
        b.branch("bne", "pd_draw")
        fop(b, "movf.s", A(c["PDL"]), "r12")
        fop(b, "mulf.s", "r12", "r20")
        fop(b, "addf.s", A(c["PDS"]), "r20")             # s*_j
        fop(b, "mulf.s", "r12", "r18")
        fop(b, "addf.s", A(c["PDH"]), "r18")             # h*_j
        fop(b, "mulf.s", "r11", "r12")                   # lam g
        b.emit("mov.w abs,reg", c["PDE"], "r0")
        fop(b, "movf.s", D(PD_HY, "r0"), "r19")
        fop(b, "mulf.s", A(self.R["LEANK"]), "r19")
        fop(b, "mulf.s", ("f", SMAX), "r19")
        fop(b, "addf.s", D(PD_HX, "r0"), "r19")
        fop(b, "mulf.s", "r12", "r19")
        fop(b, "addf.s", ("f", SM_SIL), "r19")           # the lateral margin
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMIN, "r9", "r0")
        fop(b, "addf.s", "r19", "r0")
        fop(b, "cmpf.s", "r0", "r20")
        b.branch("blt", "pd_next")
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_SMAX, "r9", "r0")
        fop(b, "subf.s", "r19", "r0")
        fop(b, "cmpf.s", "r0", "r20")
        b.branch("bgt", "pd_next")
        b.emit("mov.w abs,reg", c["PDE"], "r0")
        fop(b, "mulf.s", D(PD_HY, "r0"), "r12")
        fop(b, "mulf.s", A(self.R["LEANK"]), "r12")
        fop(b, "addf.s", ("f", HM_SIL), "r12")           # the vertical margin: lam g hy K
        b.emit("mov.w disp[reg],reg", cover_geom.MOUTH_H, "r9", "r0")
        fop(b, "subf.s", "r12", "r0")
        fop(b, "cmpf.s", "r0", "r18")
        b.branch("bgt", "pd_next")
        fop(b, "cmpf.s", "r12", "r18")                   # its bottom above the road at the opening
        b.branch("blt", "pd_next")
        b.label("pd_draw")
        b.emit("mov.w abs,reg", REC_COUNT, "r0")         # the records budget (guard_records' test inline)
        b.emit("add.w imm,reg", k["sd_records"], "r0")
        b.emit("cmp.w abs,reg", BUDGET, "r0")
        b.branch("bgt", "pd_done")
        b.emit("mov.w reg,abs", "r0", REC_COUNT)
        b.emit("add.w imm,abs", 1, c["PDCOUNT"])
        b.emit("mov.w imm,disp[reg]", 0xB, 0, "r5")       # the matrix: as the rain's cluster (its width factor is 1 under cover)
        b.emit("mov.w reg,disp[reg]", "r11", 4, "r5")
        b.emit("mov.w imm,disp[reg]", 0, 8, "r5")
        b.emit("mov.w disp[reg],disp[reg]", CL_TILT, "r6", 12, "r5")
        for off, src, kc in ((16, "r4", "LEANK"), (20, "r11", "LEANK"), (24, "r11", "LEANT")):
            b.emit("mov.w reg,reg", src, "r0")
            fop(b, "mulf.s", A(self.R[kc]), "r0")
            b.emit("mov.w reg,disp[reg]", "r0", off, "r5")
        for off in (28, 32):
            b.emit("mov.w imm,disp[reg]", 0, off, "r5")
        b.emit("mov.w reg,disp[reg]", "r11", 36, "r5")
        b.emit("mov.w reg,disp[reg]", "r1", 40, "r5")
        b.emit("mov.w reg,disp[reg]", "r2", 44, "r5")
        b.emit("mov.w reg,disp[reg]", "r3", 48, "r5")
        b.emit("mov.w imm,disp[reg]", 1, 52, "r5")
        b.emit("mov.w abs,reg", self.R["PN"], "r0")      # the colours: the set of the cluster's band, as the rain's
        fop(b, "cmpf.s", A(self.R["CUTA"]), "r3")
        b.branch("blt", "pd_band")
        b.emit("mov.w abs,reg", self.R["PM"], "r0")
        fop(b, "cmpf.s", A(self.R["CUTB"]), "r3")
        b.branch("blt", "pd_band")
        b.emit("mov.w abs,reg", self.R["PF"], "r0")
        b.label("pd_band")
        b.emit("mov.w reg,disp[reg]", "r0", 56, "r5")
        b.emit("mov.w disp[reg],reg", CL_SHAPE, "r6", "r0")
        b.emit("shl.w imm,reg", -3, "r0")
        b.emit("add.w reg,reg", "r13", "r0")
        b.emit("mul.w imm,reg", k["sd_words"], "r0")
        b.emit("add.w imm,reg", k["sd_poly"], "r0")
        b.emit("mov.w reg,disp[reg]", "r0", 60, "r5")
        b.emit("mov.w abs,disp[reg]", BUDGET, 64, "r5")
        b.emit("add.w imm,reg", 68, "r5")
        b.label("pd_next")
        b.emit("add.w imm,reg", 1, "r13")
        b.branch("br", "pd_loop")
        b.label("pd_done")
        b.emit("rsr")

    # ================================================================================================================ the block
    def block(self) -> Block:
        c = self.c
        self._win_label, self._pd_label = 0xFFFFFFF0, 0xFFFFFFF0
        for _ in range(4):                              # win and pd are called before they are emitted: settle their addresses
            b = self._block()
            got = (b.addr("win"), b.addr("pd"))
            if got == (self._win_label, self._pd_label):
                return b
            self._win_label, self._pd_label = got
        raise PatchError("the cover's code did not settle")

    def _block(self) -> Block:
        c = self.c
        b = Block(self.lay.code("cover"))
        self.frame(b)
        self.cluster(b)
        self.win(b)
        self.pd(b)
        b.label("release")
        b.emit("mov.b imm,abs", 0, self.UC)
        b.emit("mov.w imm,abs", 0, c["MODE"])
        b.emit("mov.w imm,abs", 0, c["LASTMODE"])
        b.emit("rsr")
        return b


LOG_FIELDS = ("MODE", "HIDDEN", "CURDRAWN", "PDCOUNT", "PLACED", "SILF", "WALK", "NOSPLASH", "LATE", "CX", "CY", "CZ", "INBOX")


def log_env(lay: carrier.Layout) -> dict:
    """storm_log.lua's environment for the cover's C line: its state cells, its under_cover byte and the indices of LOG_FIELDS in STATE
    (the logger reads every word by name through these: fix round 1, M4)."""
    return {"VR_STORM_COVER": f"{lay.cell('cover', 'state'):x}", "VR_STORM_UC": f"{lay.cell('cover', 'under_cover'):x}",
            "VR_STORM_COVER_FIELDS": ",".join(str(STATE.index(n)) for n in LOG_FIELDS)}


def cells(clusters: int) -> tuple[tuple[str, int], ...]:
    return (("under_cover", 1), ("state", STATE_BYTES), ("cst", CSTSZ * clusters))


def module(rs: RomSet, tune: CoverTune, rain: RainTune | None = None, twin: bool = False, fault: str | None = None) -> carrier.Module:
    """The cover as a carrier module: its code, cells, the single-drop table (image), each course's cover table (course data: from
    cover_geom.tables, marched from `rs`'s faces) and the 40 single-drop objects (polygon ROM). `rain`: the rain's tune (its
    clusters, the drops' width and head share: facts of the rain's, which the cover hides and draws drop by drop; the defaults when
    None). `twin` is
    for the pixel tests only: the curtain never drawn (everything else the same); False in every build. `fault` ("uc0": under_cover
    stuck at 0; "ignore": the rain never consults the cover) plants a fault for the tests that must catch it (fix round 1, M6);
    None in every build."""
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.weather import layout
    rain = RainTune() if rain is None else rain
    clusters = rain.clusters
    objs, stride, recs = single_drop_objects(rain)
    poly = layout.block("cover objects").start
    k = {"clusters": clusters, "sd_poly": poly // 4, "sd_words": stride // 4, "sd_records": recs}
    tabs = {e: cover_geom.table_bytes(cover_geom.tables(rs, e), tune.near) for e in range(len(decode_directory(rs)))}
    return carrier.Module(
        name="cover", code=lambda lay: Cover(lay, k, tune, twin, fault).block(), cells=cells(clusters), tables=(("drops", drop_table(rain)),),
        course_data=lambda e: {"table": tabs[e]}, rom=(("cover objects", b"".join(objs)),),
        frame="frame", release="release", entries=("cluster",))
