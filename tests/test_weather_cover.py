"""Weather stage 3, cover (spec 5.4 and 6; weather/cover.py and weather/cover_geom.py on the carrier, consulted by weather/rain.py): no
rain under tunnels and roofs, rain seen again through the exit, as Pascal approved it in spike 57 ("the long tunnel in metropolis is
perfect") and spike 68 ("short tunnel is good"). Static: the tune, the tables (marched from the set's faces, equal to the
prototype's), the single drops, the code, the cell `under_cover` and the order. In MAME (the cover's line of storm_log.lua, pictures
against a twin set that never draws the curtain): per stretch and direction no drop or splash drawn while the camera is under cover
and none over roof or walls; the pits roof's coverage from spike 68's six camera spots; the four views; a Metropolis pit stop under
the roof in both directions; Bay Bridge's tunnel in reverse; the rate gates of stage 2 on every run.

The MAME runs are made together at the first test that needs one (`cover_runs`, two MAME processes at a time), on tests/
test_weather_rain.py's session set; a selection of tests makes only the runs those tests read."""
import hashlib
import math
import os
import statistics
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from vrtools.arcade.patch import PatchError
from vrtools.arcade.weather import carrier, cover, cover_geom
from vrtools.arcade.weather.tune import CoverTune
from tests.test_weather_rain import storm_runs  # noqa: F401 (the fixture)

METROPOLIS, ALPINE, BAY_BRIDGE = 6, 3, 1
# The cover tables as the prototype built them (spike 57's march, spikes 61-68's pits roof; spike 70's tables for Alpine and Bay
# Bridge), pointers made offsets: computed from out/p57/tmp/metro_table57.pkl with spike/p57_rain.py's adjust and table_bytes, and
# out/p70/tmp/cover_3.pkl, cover_1.pkl (19 Nov 2026); every other course 4 bytes (no stretch).
TABLE_DIGESTS = {METROPOLIS: (1128, "6e5759b9c7f1dd6c"), ALPINE: (712, "ec5450345c77aee1"), BAY_BRIDGE: (392, "90a6ca4a05bb06e6")}
NO_TABLE = (4, "df3f619804a92fdb")
# The single drops and their table (seed 45). Re-pinned for the streaming rain (v0.4.1): the rain's crossed strips at a quarter of
# v0.4's width (spike 68's boxes were 40, 304, 6, "b17508620d7b9262"; their table "7c5e3cac85c3a355")
SINGLE_DROPS = (40, 264, 5, "60c8094ea603db69")
DROP_TABLE = "cf68218e96c281e9"


# ---- static ---------------------------------------------------------------------------------------------------------------------
def test_cover_tune_defaults_and_bounds():
    """CoverTune: the prototype's values (near 80, a mouth in view within 50 degrees, the long tunnel's curtain scale capped at 2,
    24 clusters under the pits roof's curtain); others refused."""
    t = CoverTune()
    assert (t.near, t.exit_angle, t.curtain_scale, t.roof_clusters) == (80.0, 50.0, 2.0, 24)
    for bad in ({"near": 10.0}, {"exit_angle": 90.0}, {"curtain_scale": 0.5}, {"roof_clusters": 0}, {"roof_clusters": 61}):
        with pytest.raises(ValueError):
            CoverTune(**bad)


def _set(romset_zip, saturn_cue):
    from tests.test_tgp_build import _seven
    return _seven(romset_zip, saturn_cue)[0]


def test_the_cover_tables_are_the_prototypes(romset_zip, saturn_cue):
    """Marched from the session set's own faces, every course's cover table is the prototype's byte for byte (pointers made
    offsets): Metropolis the pits roof's road and lane (measured, both ends seen, ROOFED) then the long tunnel (15 boxes, mouths at
    road points 249.9 and 311.95, about 40 units between the walls), Alpine one stretch of 14 boxes, Bay Bridge one of 6; the seven
    other courses no stretch."""
    rs = _set(romset_zip, saturn_cue)
    for e in range(10):
        st = cover_geom.tables(rs, e)
        blob = cover_geom.table_bytes(st, CoverTune().near)
        assert (len(blob), hashlib.sha256(blob).hexdigest()[:16]) == TABLE_DIGESTS.get(e, NO_TABLE), e
    road, lane, lt = cover_geom.tables(rs, METROPOLIS)
    assert [b.vis for b in road.boxes + lane.boxes] == [cover_geom.SEE0 | cover_geom.SEE1 | cover_geom.ROOFED] * 2
    assert lt.t == (249.9, 311.95) and len(lt.boxes) == 15 and all(b.vis & cover_geom.ROOFED == 0 for b in lt.boxes)
    assert all(39.0 < m.s[1] - m.s[0] < 43.0 for m in lt.mouths)
    (al,), (bb,) = cover_geom.tables(rs, ALPINE), cover_geom.tables(rs, BAY_BRIDGE)
    assert (al.t, len(al.boxes), bb.t, len(bb.boxes)) == ((105.05, 145.35), 14, (69.5, 89.45), 6)


def test_the_stretches_follow_the_tunnel_flags(romset_zip, saturn_cue, monkeypatch):
    """The road points of every course's tunnel-flagged quads lie in the cover's stretches and every stretch has flagged quads
    (Metropolis 50-62 and 251-311, Alpine 108-146, Bay Bridge 69-88; none elsewhere); a flag outside them, or a stretch without one,
    is refused naming the course."""
    rs = _set(romset_zip, saturn_cue)
    pts = {e: cover_geom.flagged_points(rs, e) for e in range(10)}
    assert {e for e in pts if pts[e]} == {BAY_BRIDGE, ALPINE, METROPOLIS}
    assert (min(pts[METROPOLIS]), max(pts[METROPOLIS])) == (50, 311) and (min(pts[ALPINE]), max(pts[ALPINE])) == (108, 146)
    assert (min(pts[BAY_BRIDGE]), max(pts[BAY_BRIDGE])) == (69, 88)
    real = cover_geom.flagged_points
    monkeypatch.setattr(cover_geom, "flagged_points", lambda rs_, e: real(rs_, e) + ([200] if e == ALPINE else []))
    with pytest.raises(PatchError, match="menu entry 3"):
        cover_geom.tables(rs, ALPINE)
    monkeypatch.setattr(cover_geom, "flagged_points", lambda rs_, e: [p for p in real(rs_, e) if p > 100])
    with pytest.raises(PatchError, match="menu entry 6"):
        cover_geom.tables(rs, METROPOLIS)
    monkeypatch.setattr(cover_geom, "flagged_points", lambda rs_, e: real(rs_, e) + ([10] if e == 0 else []))
    with pytest.raises(PatchError, match="menu entry 0"):
        cover_geom.tables(rs, 0)


def test_the_pits_roof_is_checked_against_the_faces(romset_zip, saturn_cue):
    """The pits roof's measured stretches hold on the session set (its underside at y 1.2 over the road and the lane, no roof just
    beyond its ends, the walls mid-roof where measured); without the roof's faces, or with its walls moved, the check refuses."""
    rs = _set(romset_zip, saturn_cue)
    tris, _ = cover_geom.course_faces(rs, METROPOLIS)
    cover_geom.check_pits_roof(cover_geom.Caster(tris))
    mid = tris.mean(1)
    roof = (np.abs(mid[:, 1] - cover_geom.ROOF_Y) < 0.5) & (mid[:, 0] > -121) & (mid[:, 0] < -70) & (mid[:, 2] > 222) & (mid[:, 2] < 340)
    assert roof.any()
    with pytest.raises(PatchError, match="pits roof"):
        cover_geom.check_pits_roof(cover_geom.Caster(tris[~roof]))
    moved = tris.copy()
    moved[:, :, 0] += 1.5                                 # every face 1.5 units across: the walls are not where measured
    with pytest.raises(PatchError, match="pits roof"):
        cover_geom.check_pits_roof(cover_geom.Caster(moved))


def test_the_single_drops_are_the_rains():
    """The 40 single-drop objects (the rain's 8 shapes' drops one by one, in bottom order, as the rain draws them since v0.4.1: two
    crossed strips at the rain's width and head share, one 264-byte object of 5 records each) and their table (centre, half width
    across, half height); a single drop's five records take the colour table's first five words of a set (H T J H T), so the set of
    the cluster's band serves them; the table's half heights are v0.4's (the length is the rain's matrix's, this pass)."""
    from vrtools.arcade.weather import rain
    from vrtools.arcade.weather.tune import RainTune
    rt = RainTune()
    objs, stride, recs = cover.single_drop_objects(rt)
    assert (len(objs), stride, recs, hashlib.sha256(b"".join(objs)).hexdigest()[:16]) == SINGLE_DROPS
    tab = cover.drop_table(rt)
    assert hashlib.sha256(tab).hexdigest()[:16] == DROP_TABLE and len(tab) == 40 * 16
    _, _, _, faces, _ = rain.drop_objects(rt)
    one = rain.cluster_object([rain.strips(*rain.shapes(width=rt.width)[0][0], rt.head)])[2]
    assert one == faces[:5] == ["H", "T", "J", "H", "T"]
    import struct as st
    halves = [st.unpack_from("<4f", tab, 16 * k) for k in range(40)]
    assert all(abs(hx - w / 2) < 1e-6 for (_, _, hx, _), (_, _, w, _, _) in
               zip(halves, [bx for m in rain.shapes(width=rt.width) for bx in sorted(m, key=lambda b: b[1] - b[3] / 2)]))


def test_the_cover_code_disassembles(romset_zip, saturn_cue):
    """The cover's code as laid out in the image disassembles as instructions throughout (no byte read as data), its entry points
    (frame, cluster, release) among them; the rain's new entries (rand, shape) too."""
    from tests.test_weather_carrier import _stage1
    from vrtools.arcade.disasm import listing_bytes
    lay, pieces, _ = carrier.lay_out(carrier.default_modules(_stage1(romset_zip, saturn_cue)))
    for name, labels in (("cover", ("frame", "cluster", "release")), ("rain", ("start", "frame", "release", "rand", "shape"))):
        at, code = pieces[name]
        lines = listing_bytes(code, at)
        assert sum(len(l.bytes) for l in lines) == len(code)
        assert not [l for l in lines if l.text.startswith("$") or "illegal" in l.text.lower()][:3], name
        assert {lay.label(name, k) for k in labels} <= {l.addr for l in lines}, name


def test_under_cover_is_a_byte_cell_written_before_the_rain(romset_zip, saturn_cue):
    """The interface of the parallel tracks: the cover is registered before the rain (the join's order: cover, lightning, rain), so
    its cells come first and the carrier calls its frame before the rain's in a SHOW pass; `under_cover` is a one-byte cell of the
    cover's, read by name (`lay.cell("cover", "under_cover")`); the cover's frame writes it (a byte write) and its release clears it;
    the cover has no start (the rain's placement passes need none)."""
    from tests.test_weather_carrier import _stage1
    s1 = _stage1(romset_zip, saturn_cue)
    mods = carrier.default_modules(s1)
    assert [m.name for m in mods] == ["cover", "lightning", "rain", "handling", "sound"] and mods[0].start is None   # the join's order
    assert dict(mods[0].cells)["under_cover"] == 1
    lay, pieces, _ = carrier.lay_out(mods)
    uc = lay.cell("cover", "under_cover")
    assert uc == carrier.MODULE_CELLS[0] < lay.cell("rain", "state")
    from vrtools.arcade.v60asm import asm
    body = pieces["carrier"][1]
    frames = [body.index(asm("jsr abs", lay.label(n, "frame"))) for n in ("cover", "rain")]
    assert frames[0] < frames[1]
    at, code = pieces["cover"]
    assert code.count(asm("mov.b imm,abs", 1, uc)) == 2 and code.count(asm("mov.b imm,abs", 0, uc)) == 2   # frame: 0 then 1; late: 1; release


def test_the_pits_roof_curtain_lies_on_the_end_plane(romset_zip, saturn_cue, monkeypatch):
    """The session lead's ruling C1 (19 Nov 2026): the approved picture is the reference, even where the prototype's code meant
    something else. Spike 68's code meant the pits roof's curtain to lie along the sight lines beyond the end plane, but an
    overwritten register put every cluster ON the end plane (measured on out/p68tunnels: u 4e-42 .. 6e-39), and that is what Pascal
    approved ("short tunnel is good"). cover.ROOF_U0 is that depth, 0.0, a deviation from the prototype's intent kept on purpose
    (docs/deviations.md, Cover): the cover's code places the roof's clusters at it (with it changed, exactly one `movf.s` of that
    value into the placement's u, R14, becomes one of the new value)."""
    from tests.test_weather_carrier import _stage1
    from vrtools.arcade.v60asm import asm
    assert cover.ROOF_U0 == 0.0
    s1 = _stage1(romset_zip, saturn_cue)
    a = carrier.lay_out(carrier.default_modules(s1))[1]["cover"][1]
    monkeypatch.setattr(cover, "ROOF_U0", 1.0)
    b = carrier.lay_out(carrier.default_modules(s1))[1]["cover"][1]
    zero, one = asm("movf.s imm,reg", 0.0, "r14"), asm("movf.s imm,reg", 1.0, "r14")
    assert (a.count(zero) - b.count(zero), b.count(one) - a.count(one)) == (1, 1), (a.count(zero), b.count(zero), a.count(one), b.count(one))


def test_a_stale_pass_is_excused_only_where_the_released_game_shows_it():
    """The session lead's ruling C5: a stale pass within STALE_AFTER_LOAD_MAX frames after the race load is excused only when main's
    released set, run on the same inputs and boot, is stale on the same pass (counted from its own race load); any other stale pass,
    and one past the window, stays a fault."""
    assert stale_excused_by_released([1610], 1603, [276, 1610], 1603) == []
    assert stale_excused_by_released([1611], 1604, [1610], 1603) == []                  # the same pass, counted from each load
    assert stale_excused_by_released([1610], 1603, [1607], 1602) == [1610]              # main stale on another pass
    assert stale_excused_by_released([1610], 1603, [], 1603) == [1610]                  # main clean
    assert stale_excused_by_released([1603 + STALE_AFTER_LOAD_MAX + 2], 1603, [1603 + STALE_AFTER_LOAD_MAX + 2], 1603) != []
    assert stale_excused_by_released([1610, 2000], 1603, [1610, 2000], 1603) == [2000]  # main's later stale excuses nothing


# ---- the register contract between the rain and the cover (fix round 1, F1) -----------------------------------------------------
_OPN = {"reg": 1, "imm": 1, "abs": 1, "disp[reg]": 2, "[reg]": 1, "abs(reg)": 2}   # abs(reg): v0.4.1, the rain's `lit` table


def _rw(form: str, args) -> tuple[set, set]:
    """(registers read, registers written) of one emitted instruction (the forms the storm emits; jsr and rsr: none here)."""
    op, _, ks = form.partition(" ")
    ks = ks.split(",") if ks else []
    ops, i = [], 0
    for k in ks:
        ops.append((k, args[i:i + _OPN[k]]))
        i += _OPN[k]
    reads, writes = set(), set()
    for j, (k, a) in enumerate(ops):
        if k in ("disp[reg]", "abs(reg)"):
            reads.add(a[1])
        elif k == "[reg]":
            reads.add(a[0])
        elif k == "reg" and j < len(ops) - 1:
            reads.add(a[0])
    if op.startswith("movc"):                          # movcu.h [src],count,[dst],count: both counts, R27 and R28
        reads |= {ops[1][1][0], ops[3][1][0]}
        writes |= {ops[1][1][0], ops[3][1][0], "r27", "r28"}
    elif op in ("pushm", "popm"):
        raise AssertionError(f"{form}: not in the register audit")
    elif ops and ops[-1][0] == "reg":
        d = ops[-1][1][0]
        if op.startswith("cmp") or not op.startswith(("mov", "cvt", "neg")):     # compared, or read-modify-write
            reads.add(d)
        if not op.startswith("cmp"):
            writes.add(d)
    return reads, writes


def _traced(monkeypatch, romset_zip, saturn_cue):
    """The layout of the default modules with each Block's items traced: {"cover": (block, trace), "rain": (block, trace)}; a trace
    item is ("ins", form, args), ("br", cond, label) or ("label", name). (The attribute is `_cover_trace`: the join's handling has a
    Block subclass of its own with an attribute `trace`.)"""
    from tests.test_weather_carrier import _stage1
    from vrtools.arcade import v60asm
    from vrtools.arcade.weather import rain
    for meth, tag in (("emit", "ins"), ("branch", "br"), ("label", "label")):
        orig = getattr(v60asm.Block, meth)

        def rec(self, *a, _o=orig, _t=tag):
            self.__dict__.setdefault("_cover_trace", []).append((_t,) + a if _t == "label" else (_t, a[0], a[1:]) if _t == "ins" else (_t,) + a)
            return _o(self, *a)
        monkeypatch.setattr(v60asm.Block, meth, rec)
    got = {}
    for name, cls in (("cover", cover.Cover), ("rain", rain.Rain)):
        orig = cls.block

        def blk(self, _o=orig, _n=name):
            b = _o(self)
            got[_n] = (b, b._cover_trace)
            return b
        monkeypatch.setattr(cls, "block", blk)
    carrier.lay_out(carrier.default_modules(_stage1(romset_zip, saturn_cue)))
    return got


def _cfg(block, trace):
    """(instructions as (reads, writes, kind, arg), successors, label index, label of an address) of a traced block."""
    labels = {it[1]: k for k, it in enumerate(trace) if it[0] == "label"}
    addr = {block.addr(n): n for n in labels}
    succ = []
    for k, it in enumerate(trace):
        nxt = [k + 1] if k + 1 < len(trace) else []
        if it[0] == "br":
            succ.append([labels[it[2]]] if it[1] == "br" else [labels[it[2]]] + nxt)
        elif it[0] == "ins" and it[1] == "rsr":
            succ.append([])
        elif it[0] == "ins" and it[1] == "jmp abs":
            succ.append([labels[addr[it[2][0]]]] if it[2][0] in addr else [])
        else:
            succ.append(nxt)
    return labels, addr, succ


def _clobbers(block, trace, start: str, external: dict) -> set:
    """Every register a routine (from label `start` to its rsr, by its branches) or anything it calls writes."""
    labels, addr, succ = _cfg(block, trace)
    seen, todo, out = set(), [labels[start]], set()
    while todo:
        k = todo.pop()
        if k in seen:
            continue
        seen.add(k)
        it = trace[k]
        if it[0] == "ins" and it[1] == "jsr abs":
            t = it[2][0]
            out |= _clobbers(block, trace, addr[t], external) if t in addr else external[t]
        elif it[0] == "ins":
            out |= _rw(it[1], it[2])[1]
        todo += succ[k]
    return out


def test_the_cover_keeps_the_rains_live_registers(monkeypatch, romset_zip, saturn_cue):
    """Fix round 1, F1 (the review: the drop-by-drop routine returned a garbage scale cap in R12, a sibling of the R14 bug). The
    registers the rain still reads after its `jsr` to the cover's `cluster` (a liveness walk of the rain's own code, its loop
    included) are either ones the cover hands back (cover.CLUSTER_RETURNS: defined on every path to every `rsr` of `cluster`, a
    call killing what the callee writes) or ones no instruction reachable from `cluster`, callees included, writes. M3: where the
    rain skips the cover (its mode 0) it does not read R12, the cover's scale cap."""
    from tests.test_weather_carrier import _stage1
    got = _traced(monkeypatch, romset_zip, saturn_cue)
    cb, ct = got["cover"]
    rb, rt = got["rain"]
    lay = carrier.lay_out(carrier.default_modules(_stage1(romset_zip, saturn_cue)))[0]
    ext = {lay.label("rain", "rand"): {"r0"}, lay.label("rain", "shape"): {"r0", "r4", "r9"}}
    # the rain: liveness after the jsr to cluster
    labels, addr, succ = _cfg(rb, rt)
    cl = lay.label("cover", "cluster")
    calls = [k for k, it in enumerate(rt) if it[0] == "ins" and it[1] == "jsr abs" and it[2][0] == cl]
    assert calls
    others = {it[2][0] for it in rt if it[0] == "ins" and it[1] == "jsr abs"} - {cl} - set(addr)
    assert not others, [hex(a) for a in others]
    live = [set() for _ in rt]
    changed = True
    while changed:
        changed = False
        for k in range(len(rt) - 1, -1, -1):
            it = rt[k]
            out = set().union(*(live[j] for j in succ[k])) if succ[k] else set()
            if it[0] == "ins" and it[1] == "jsr abs":
                r, w = (set(cover.CLUSTER_INPUTS), _clobbers(cb, ct, "cluster", ext)) if it[2][0] == cl else (set(), set())
            elif it[0] == "ins":
                r, w = _rw(it[1], it[2])
            else:
                r, w = set(), set()
            new = r | (out - w)
            if new != live[k]:
                live[k], changed = new, True
    after = set().union(*(live[k + 1] for k in calls))
    skips = [k for k, it in enumerate(rt) if it[0] == "label" and it[1].endswith("cov_skip")]
    assert skips and all("r12" not in live[k] for k in skips), "R12 read where the cover was not called (fix round 1, M3)"
    keeps = after - set(cover.CLUSTER_RETURNS)
    clob = _clobbers(cb, ct, "cluster", ext)
    assert not (keeps & clob), ("the cover writes registers the rain keeps live across the call", sorted(keeps & clob))
    # the cover: every CLUSTER_RETURNS register defined at every rsr reachable from cluster (entry: the rain's inputs)
    labels, addr, succ = _cfg(cb, ct)
    inputs = set(cover.CLUSTER_INPUTS)
    state = {labels["cluster"]: inputs}
    todo, bad = [labels["cluster"]], []
    while todo:
        k = todo.pop()
        d = state[k]
        it = ct[k]
        if it[0] == "ins" and it[1] == "jsr abs":
            t = it[2][0]
            w = _clobbers(cb, ct, addr[t], ext) if t in addr else ext[t]
            d = (d - w) | (w & set(cover.CALLEE_RETURNS.get(addr.get(t), ())))     # what a callee hands back on purpose
        elif it[0] == "ins" and it[1] == "rsr":
            missing = set(cover.CLUSTER_RETURNS) - d
            if missing:
                bad.append((k, sorted(missing)))
        elif it[0] == "ins":
            d = d | _rw(it[1], it[2])[1]
        for j in succ[k]:
            nd = d if j not in state else state[j] & d
            if j not in state or nd != state[j]:
                state[j] = nd
                todo.append(j)
    assert not bad, ("returns undefined at an rsr of cluster (trace index, registers)", bad[:5])


def test_a_late_frame_reads_as_under_cover_and_the_walk_is_set_first(monkeypatch, romset_zip, saturn_cue):
    """Fix round 1, M1: on a late pass (the guard trips in `frame`) the cover forces mode 2 and writes `under_cover` 1, the safe value
    for the lightning (a bolt missed is harmless, a white-out inside a tunnel is not). M2: `frame` writes the rain's loop walk WALK
    before its first guard (the rain's loop is do-while: a walk of 0 would run it over every word)."""
    from tests.test_weather_carrier import _stage1
    got = _traced(monkeypatch, romset_zip, saturn_cue)
    cb, ct = got["cover"]
    lay = carrier.lay_out(carrier.default_modules(_stage1(romset_zip, saturn_cue)))[0]
    uc, walk = lay.cell("cover", "under_cover"), cover.cell(lay, "WALK")
    k = next(i for i, it in enumerate(ct) if it == ("label", "f_late"))
    end = next(i for i in range(k, len(ct)) if ct[i][0] == "ins" and ct[i][1] == "rsr")
    assert ("ins", "mov.b imm,abs", (1, uc)) in ct[k:end], ct[k:end]
    start = next(i for i, it in enumerate(ct) if it == ("label", "frame"))
    first_guard = next(i for i in range(start, len(ct)) if ct[i][0] == "br" and ct[i][2] == "f_late")
    walks = [i for i in range(start, len(ct)) if ct[i][0] == "ins" and ct[i][1] == "mov.w imm,abs" and ct[i][2][1] == walk]
    assert walks and walks[0] < first_guard, (walks[:2], first_guard)


CAM_REACH = 25.0                        # units: how far off a road point the camera may be (the chase views' distance behind the car)


def test_the_near_list_holds_every_box_in_reach(romset_zip, saturn_cue):
    """Fix round 2, R2-2: the frame lists the boxes within `near` of the camera in TABLE order up to NNEAR_MAX, and mode 1 hides
    clusters only in listed boxes: a box left off would let rain show inside a tunnel (the high view, an approach in reverse). For
    every road point of every road line of the three covered courses, the boxes within near + CAM_REACH (in each box's frame, as the
    frame tests) are at most NNEAR_MAX, so none is dropped."""
    from vrtools.arcade.course import course_entry_at, road_lines
    from vrtools.arcade.directory import decode_directory
    rs = _set(romset_zip, saturn_cue)
    d = decode_directory(rs)
    reach = CoverTune().near + CAM_REACH
    most = {}
    for e in COVERED_COURSES:
        boxes = [b for st in _tables(rs, e) for b in st.boxes]
        for line in road_lines(rs, course_entry_at(rs, d[e].bank, window_base=d[e].header_base)):
            for p in line:
                n = sum(1 for b in boxes if -reach <= (p.x - b.o[0]) * b.a[0] + (p.z - b.o[1]) * b.a[1] <= b.L + reach
                        and b.s[0] - reach <= (p.z - b.o[1]) * b.a[0] - (p.x - b.o[0]) * b.a[1] <= b.s[1] + reach)
                most[e] = max(most.get(e, 0), n)
    assert max(most.values()) <= cover.NNEAR_MAX, (most, cover.NNEAR_MAX)


COVERED_COURSES = (METROPOLIS, ALPINE, BAY_BRIDGE)   # the courses the geometry checks below run on (the near list, the views)


def test_the_checks_cover_every_flagged_course(romset_zip, saturn_cue):
    """The join (the cover's round-2 re-review): the near-list geometry test (test_the_near_list_holds_every_box_in_reach), the
    four views and their low-view height margin (test_the_four_views, LOW_VIEW_MAX) and the passes' runs (PASSES, both directions) run
    on COVERED_COURSES, and those are exactly the courses of the joined build with a tunnel-flagged stretch, in both directions (a
    reverse variant's flags are its course's): a later course with a flagged stretch fails here until it is added to both checks."""
    from vrtools.arcade.directory import decode_directory
    rs = _set(romset_zip, saturn_cue)
    flagged = {e for e in range(len(decode_directory(rs))) if cover_geom.flagged_points(rs, e)}
    assert flagged == set(COVERED_COURSES), (sorted(flagged), COVERED_COURSES)
    assert {e for e, _ in PASSES} == set(COVERED_COURSES) == set(VIEW_SNAPS)
    assert {r for e, r in PASSES} == {False, True} and all((e, r) in PASSES for e in COVERED_COURSES for r in (False, True))
    assert all(decode_directory(rs)[e].reverse is not None for e in COVERED_COURSES)


def test_cover_is_not_a_game_changing_module():
    """The cover changes pictures only: it is not among the modules test_rain_does_not_change_the_game leaves out of its RAIN build
    (the replayed RAIN race runs with the cover on and must be the DRY race's game)."""
    from tests.test_weather_rain import GAME_CHANGING_MODULES
    assert "cover" not in GAME_CHANGING_MODULES


def test_the_rain_consults_the_cover_and_stands_alone(romset_zip, saturn_cue):
    """With the cover in the build the rain's code calls the cover's `cluster` entry and reads its walk and nosplash words; built
    alone (no cover) it lays out and references none of the cover's addresses."""
    from tests.test_weather_carrier import _stage1
    from vrtools.arcade.weather import rain
    from vrtools.arcade.weather.tune import RainTune
    s1 = _stage1(romset_zip, saturn_cue)
    lay, pieces, _ = carrier.lay_out(carrier.default_modules(s1))
    code = pieces["rain"][1]
    for a in (lay.label("cover", "cluster"), cover.cell(lay, "WALK"), cover.cell(lay, "NOSPLASH"), cover.cell(lay, "MODE")):
        assert struct.pack("<I", a) in code, hex(a)
    alone = carrier.lay_out([rain.module(s1, RainTune())])
    assert ("cover", "state") not in alone[0].cells and alone[1]["rain"][1]


# ---- the runs ---------------------------------------------------------------------------------------------------------------------
COVER_JOBS = 2                          # MAME processes at a time (the machine is shared by the parallel tracks)
# The passes through every flagged stretch, per (entry, reverse): seconds of RAIN race on the rate tests' line (Bay Bridge in reverse
# on its centreline from the session battery RAM: past the reverse fork, as test_originals_reverse's reverse races), long enough
# for one pass of each stretch; the set's run and the twin's (the curtain never drawn) on the same inputs.
PASSES = {(METROPOLIS, False): 100, (METROPOLIS, True): 150, (ALPINE, False): 75, (ALPINE, True): 150, (BAY_BRIDGE, False): 75,
          (BAY_BRIDGE, True): 150}
SNAP_MAX = 1500                         # snapshots of a pass at most (every frame in mode 3)
# Spike 68's six camera spots under the pits roof (out/p68/look/NOTE.txt: two of Pascal's stops, mid-roof 42 units from the exit
# and in the cockpit view 21 units from it, their stop 4.7 units from the exit, the pit stop in the lane, a reverse stop on the road
# near the outer wall, the reverse pit stop), made by scripted stops on the rate tests' Metropolis line here (Pascal's recorded drives
# are not in the repository; the stops measured on the dev runs: the camera mid-roof at z 298.6, in the cockpit at 324.9, near the
# exit at 335.4, in reverse at x -116.8 z 240.5): name -> (reverse, the stop (a road point, a box "x0,x1,z0,z1" of the car's x and z,
# or "pit"), the view button pressed at frame 2000 or None, seconds).
SPOTS = {"s12w1": (False, 50, None, 62), "s12w2": (False, 60, "VR1 (Red)", 62), "s3": (False, "-125,-95,326,345", None, 62),
         "s4": (False, "pit", None, 150), "s5": (True, 306, None, 150), "s7": (True, "pit", None, 180)}
SPOT_SNAPS = 600                        # frames a spot is pictured: at s5 300 frames gave the prototype 94.5 % and this build 82.3 % (a
                                        # few slow clusters cover a near opening; the same spot over 600 frames: 100 % and 99.4 %)
VIEWS = ("VR1 (Red)", "VR2 (Blue)", "VR3 (Yellow)", "VR4 (Green)")
VIEW_SNAPS = {METROPOLIS: "45-66,245-316", ALPINE: "100-150", BAY_BRIDGE: "62-95"}   # pictures of each view's run (road points)
PIT_SECONDS, REVERSE_PIT_SECONDS, REVERSE_AHEAD = 150, 180, 15     # tests/test_hudreverse_build.py's pit runs
COVERAGE_MIN = 0.95                     # spike 68's measure: 97.8-100 % on its six spots (p65 60.8-92.1 %)
LEAK_TOL_PX = 2                         # rain pixels farther than this outside the opening are a leak (spike 68's measure)
# Main's released set (v0.3's game code; git-ignored), for the stale pass at a battery-RAM race load (the session lead's ruling C5): its
# DRY race on the same inputs and boot, RELEASED_SECONDS long (the boot to a few seconds past the race load, frame ~1603)
# VR_RELEASED_SET through tests/reference_sets.py (W2): skipped (failed with VR_REQUIRE_REFERENCE_SETS=1) when absent
RELEASED_SECONDS = 40
TAPED_SPOTS = ("s3",)                   # the spot gated by its own cell count (fewer than SPOT_FEW_CELLS on screen): its game taped
# Fix round 1, F5: the storm generator's three trajectories every gated measure is taken on (storm_seed.lua sets the word at the race
# load; 0 is the unset generator's own start, the race as the game plays it)
SEEDS = (0, 0x9E3779B9, 0x2468ACE1)
POKE, POKE_FRAME, POKE_SECONDS = 0x1234567, 2000, 150     # F3: the hunt's poke (sd_b_1234567: its autopilot race left the twin's)
NEG_SNAP = "100-150"                    # the negative control's pictures: Alpine's tunnel by road point (108-146), every frame
STALE_AFTER_LOAD_MAX = 15               # frames after the race load in which a stale pass may be the game's own (main's at load + 7)


def _cover_modules(s1) -> list:
    """The modules of the cover's sets (the join): the registry's without the game-changing ones (tests/test_weather_rain.py's
    GAME_CHANGING_MODULES: the wet handling), so that a taped RAIN run is its DRY tape run's game pass for pass (`_same_game`): the
    cover, the lightning, the rain and the sound's triggers, the storm session's `same_build()`."""
    from tests.test_weather_rain import GAME_CHANGING_MODULES
    return [m for m in carrier.default_modules(s1) if m.name not in GAME_CHANGING_MODULES]


def _with_cover(s1, cov):
    """`_cover_modules` with `cov` in the cover's place (a twin, a planted fault): the same cells and layout as the cover's set's but
    the cover's code."""
    return [cov if m.name == "cover" else m for m in _cover_modules(s1)]


class CoverSession:
    """The cover's runs on the storm session's set without the game-changing modules (`same_build()`: the join, `_cover_modules`)
    and on its twin (`cover.module(..., twin=True)`: everything the same, the curtain never drawn), made at the first use."""

    def __init__(self, storm):
        from tests.test_tgp_build import _build
        from tests.test_weather_carrier import _stage1
        from vrtools.arcade.weather import rain
        from vrtools.arcade.weather.tune import RainTune
        self.storm, self.rate = storm, storm.rate
        self.base = storm.base / "cover"
        self.base.mkdir(parents=True, exist_ok=True)
        s1 = _stage1(self.rate.romset_zip, self.rate.saturn_cue)
        twin, rep = carrier.build(s1, _with_cover(s1, cover.module(s1, CoverTune(), twin=True)))   # the join: every module but the
                                                                                                        # cover the session set's
        (self.base / "twin").mkdir(exist_ok=True)
        self.twin = _build(self.base / "twin", self.rate.romset_zip, twin)
        self.set = storm.same_build()                  # the join: the taped games equal their DRY tape runs (no wet handling)
        self.lay = carrier.lay_out(_cover_modules(s1))[0]
        assert rep["layout"].cells == self.lay.cells                 # the twin's RAM is the set's (the same pictures but the curtain's)
        self.table = self.lay.data_at("cover", "table")
        self.runs, self.failed = {}, {}
        self._lock = threading.Lock()
        self._pitn = threading.Event()
        self._faults = {}

    def env(self, wd: Path) -> dict:
        from vrtools.mame.runner import LUA_DIR
        return {**self.storm.storm_env(wd, lay=self.lay), **cover.log_env(self.lay), "VR_FRAME_LOG": str(wd / "frames.txt"),
                "VR_RATE_LOG": str(wd / "rate.txt"), "VR_STALE_LOG": str(wd / "stale_list.txt"), "VR_HOLD_CLOCK": "1", "VR_RAIN": "1",
                "VR_LOOK_LOG": str(wd / "look.txt"), "VR_EXTRA_LUA": f"{LUA_DIR / 'cover_look.lua'};{LUA_DIR / 'test_inputs.lua'}",
                "VR_TEST_LOG": str(wd / "test.txt"), "VR_TEST_INPUT": ""}

    def _make(self, key):
        import shutil
        from tests.test_frame_rate import Run
        from vrtools.mame.pitpaths import reverse_pit_path
        from vrtools.mame.runner import LUA_DIR, PIT_HANDLER, parse_pit_log, run_mame, write_centreline
        kind, rest, which = key[0], key[1:-1], key[-1]
        wd = self.base / "_".join(str(k).replace(" ", "") for k in key)
        wd.mkdir(parents=True, exist_ok=True)
        build = self.twin if which == "twin" else self.set
        if kind in ("pass", "poke", "neg", "fault"):
            entry, reverse = rest[:2] if kind == "pass" else (ALPINE, False)
            seed = rest[2] if kind == "pass" and len(rest) > 2 else POKE if kind == "poke" and which != "tape" else None
            line = None
            env = self.rate._env(wd, entry, reverse, line)
            env.update(self.env(wd))
            env.update({"VR_LOOK_MODE": f"{cover.cell(self.lay, 'MODE'):x}:3", "VR_LOOK_EVERY": "1", "VR_LOOK_MAX": str(SNAP_MAX)})
            if (entry, reverse) == (BAY_BRIDGE, True):
                shutil.copytree(self.rate.nvram(), wd / "nvram")
            if kind == "poke":                         # the game only: no pictures
                env.pop("VR_LOOK_MODE")
            if kind == "neg":                          # the leak measure's negative control: the rain alone, in the tunnel too
                for k in [k for k in env if k.startswith("VR_STORM")] + ["VR_LOOK_MODE"]:
                    env.pop(k, None)
                env["VR_LOOK_SNAP"] = NEG_SNAP
                build = self.neg_build()
            if kind == "fault":                        # a planted fault the tests must catch (fix round 1, M6)
                build = self.fault_build(rest[0])
            if kind in ("pass", "fault") and which == "set":     # M5: what the rain draws on the approach (rain_records.lua)
                env.update({"VR_RECS_LOG": str(wd / "records.txt"), "VR_RECS_MODE": f"{cover.cell(self.lay, 'MODE'):x}:1",
                            **self.recs_poly()})
                env["VR_EXTRA_LUA"] = env["VR_EXTRA_LUA"] + f";{LUA_DIR / 'rain_records.lua'}"
            self._tape(key, wd, env)
            self._seed(wd, env, seed)
            seconds = POKE_SECONDS if kind == "poke" else PASSES[(entry, reverse)]
            run_mame(LUA_DIR / "autoplay.lua", seconds, wd, build, env=env, timeout=7200)
            return Run(wd, finish=False)
        if kind == "spot":
            from vrtools.convert.reverse import reverse_points
            name = rest[0]
            seed = rest[1] if len(rest) > 1 else None
            reverse, stop, view, seconds = SPOTS[name]
            line = None
            if stop == "pit":                         # the reverse pit path is already in reverse order: `_env` reads a line backwards
                line = self.rate.pit_path(METROPOLIS) if not reverse else reverse_points(reverse_pit_path(
                    parse_pit_log(self.run("spot", "s4", "set").wd / "pit.txt"), [(p.x, p.z) for p in self.rate.road[METROPOLIS][6]]))
            env = self.rate._env(wd, METROPOLIS, reverse, line)
            env.update(self.env(wd))
            env.update({"VR_LOOK_N": str(SPOT_SNAPS), "VR_PIT_LOG": str(wd / "pit.txt")})
            if stop == "pit":
                env["VR_LOOK_PIT"] = f"{PIT_HANDLER:x}"
                if reverse:
                    env["VR_AUTOPILOT_AHEAD"] = str(REVERSE_AHEAD)
            elif isinstance(stop, str):
                env["VR_LOOK_STOP_BOX"] = stop
            else:
                env["VR_LOOK_STOP"] = str(stop)
            if view:
                env["VR_TEST_INPUT"] = f"2000:{view}:8"
            self._tape(key, wd, env)
            self._seed(wd, env, seed)
            run_mame(LUA_DIR / "autoplay.lua", seconds, wd, build, env=env, timeout=7200)
            return Run(wd, finish=False)
        if kind == "view":                             # a view pressed at frame 2000 (after the green), the normal pass
            view, entry = rest
            env = self.rate._env(wd, entry, False)
            env.update(self.env(wd))
            env.update({"VR_TEST_INPUT": f"2000:{view}:8", "VR_LOOK_SNAP": VIEW_SNAPS[entry], "VR_LOOK_EVERY": "6", "VR_LOOK_MAX": "300"})
            # R2-2: what the rain draws in modes 0 and 1 (rain_records.lua)
            env.update({"VR_RECS_LOG": str(wd / "records.txt"), "VR_RECS_MODE": f"{cover.cell(self.lay, 'MODE'):x}:0,1",
                        **self.recs_poly()})
            env["VR_EXTRA_LUA"] = env["VR_EXTRA_LUA"] + f";{LUA_DIR / 'rain_records.lua'}"
            run_mame(LUA_DIR / "autoplay.lua", PASSES[(entry, False)], wd, build, env=env, timeout=7200)
            return Run(wd, finish=False)
        if kind == "released":                         # main's released set, DRY, the pass's inputs and battery RAM, to the load
            entry, reverse = rest
            from tests.reference_sets import reference_set
            RELEASED_SET = reference_set("VR_RELEASED_SET")
            env = self.rate._env(wd, entry, reverse, None)
            env.update({"VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"),
                        "VR_STALE_LOG": str(wd / "stale_list.txt"), "VR_HOLD_CLOCK": "1"})
            shutil.copytree(self.rate.nvram(), wd / "nvram")
            run_mame(LUA_DIR / "autoplay.lua", RELEASED_SECONDS, wd, RELEASED_SET, env=env, timeout=3600)
            return Run(wd, finish=False)
        raise ValueError(key)

    @staticmethod
    def taped(key) -> bool:
        """The runs whose game a tape fixes (fix round 1, F3/F5: the leak and the narrow spot's cells measured on the same game every
        time, on SEEDS generator trajectories): every pass, the poked trajectory, the negative control, and the spots of
        TAPED_SPOTS; set and twin alike."""
        return key[0] in ("pass", "poke", "neg", "fault") or (key[0] == "spot" and key[1] in TAPED_SPOTS)

    @staticmethod
    def tape_key(key) -> tuple:
        """The DRY tape run a taped run replays: ("pass", entry, reverse, "tape"), ("spot", name, "tape"), ("poke", "tape"); the
        negative control replays Alpine's pass tape."""
        if key[0] in ("neg", "fault"):
            return ("pass", ALPINE, False, "tape")
        return {"pass": key[:3], "spot": key[:2], "poke": key[:1]}[key[0]] + ("tape",)

    def _tape(self, key, wd: Path, env: dict) -> None:
        """A taped run's inputs: its tape run is the same race DRY on the set (the switch off: no storm, so no pass-time effect on
        the autopilot's sampling) recording the autopilot's wheel and pedal (input_tape.lua, as test_rain_does_not_change_the_game);
        its set and twin runs replay that tape and write what they fed; every one logs the game's pass state (pass_state.lua), which
        the tests compare."""
        if not self.taped(key):
            return
        env["VR_PASS_LOG"] = str(wd / "pass.txt")
        env["VR_INPUT_LOG"] = str(wd / "tape.txt")
        if key[-1] == "tape":
            env.pop("VR_RAIN", None)
        else:
            env["VR_INPUT_REPLAY"] = str(self.run(*self.tape_key(key)).wd / "tape.txt")

    def _seed(self, wd: Path, env: dict, seed) -> None:
        """The storm generator set to `seed` (storm_seed.lua): at the race load, or for the poked trajectory at POKE_FRAME."""
        from vrtools.arcade.weather import rain
        from vrtools.mame.runner import LUA_DIR
        if seed is None:
            return
        at = rain.cell(self.lay, "RAND")
        env["VR_STORM_SEED"] = f"{at:x}:{seed:x}" + (f":{POKE_FRAME}" if wd.name.startswith("poke") else "")
        env["VR_STORM_STATE"] = f"{carrier.STATE:x}"
        env["VR_SEED_LOG"] = str(wd / "seed.txt")
        env["VR_EXTRA_LUA"] = env["VR_EXTRA_LUA"] + f";{LUA_DIR / 'storm_seed.lua'}"

    @staticmethod
    def recs_poly() -> dict:
        """rain_records.lua's polygon ranges: the rain's and the cover's objects, the first splash object, the first single drop."""
        from vrtools.arcade.weather import layout, rain
        lo, hi = layout.block("rain objects"), layout.block("cover objects")
        from vrtools.arcade.weather.tune import RainTune
        objs, size, _, _, _ = rain.drop_objects(RainTune())
        return {"VR_RECS_POLY": f"{lo.start // 4:x}:{(hi.start + hi.size) // 4:x}",
                "VR_RECS_SPLASH": f"{(lo.start + len(objs) * size) // 4:x}", "VR_RECS_SINGLE": f"{hi.start // 4:x}"}

    def fault_build(self, fault: str) -> Path:
        """A set with a planted fault (cover.module's `fault`: "uc0", "ignore"), the session set's cells."""
        from tests.test_tgp_build import _build
        from tests.test_weather_carrier import _stage1
        from vrtools.arcade.weather import rain
        from vrtools.arcade.weather.tune import RainTune
        with self._lock:
            if fault not in self._faults:
                s1 = _stage1(self.rate.romset_zip, self.rate.saturn_cue)
                new, rep = carrier.build(s1, _with_cover(s1, cover.module(s1, CoverTune(), fault=fault)))
                assert rep["layout"].cells == self.lay.cells
                (self.base / f"fault_{fault}").mkdir(exist_ok=True)
                self._faults[fault] = _build(self.base / f"fault_{fault}", self.rate.romset_zip, new)
        return self._faults[fault]

    def neg_build(self) -> Path:
        """The negative control's set: the storm with the rain alone (no cover: the rain drawn inside the tunnels too)."""
        from tests.test_tgp_build import _build
        from tests.test_weather_carrier import _stage1
        from vrtools.arcade.weather import rain
        from vrtools.arcade.weather.tune import RainTune
        with self._lock:
            if not hasattr(self, "_neg"):
                s1 = _stage1(self.rate.romset_zip, self.rate.saturn_cue)
                (self.base / "neg").mkdir(exist_ok=True)
                self._neg = _build(self.base / "neg", self.rate.romset_zip, carrier.build(s1, [rain.module(s1, RainTune())])[0])
        return self._neg

    def prefetch(self, keys):
        keys = [k for k in dict.fromkeys(keys) if k not in self.runs]
        tapes = [t for t in dict.fromkeys(self.tape_key(k) for k in keys if self.taped(k) and k[-1] != "tape") if t not in self.runs]
        later = [k for k in keys if k[:2] == ("spot", "s7")]                  # the reverse pit path is read from s4's set run
        first = [k for k in keys if k not in later]

        def make(k):
            try:
                r = self._make(k)
            except (Exception, pytest.skip.Exception, pytest.fail.Exception) as e:   # noqa: BLE001 (raised again by `run`;
                # Phase 90: a run that skips or fails at its start, the released run without VR_RELEASED_SET, now ends only the tests
                # reading it: its skip escaped the prefetch, the session was never kept and every later test built one again)
                with self._lock:
                    self.failed[k] = e
                return
            with self._lock:
                self.runs[k] = r
        if any(k[1:3] == (BAY_BRIDGE, True) and k[0] in ("pass", "released") for k in keys):
            self.rate.nvram()
        if later and ("spot", "s4", "set") not in first and ("spot", "s4", "set") not in self.runs:
            first.append(("spot", "s4", "set"))
        with ThreadPoolExecutor(COVER_JOBS) as ex:              # the tapes before the runs that replay them
            list(ex.map(make, tapes))
        with ThreadPoolExecutor(COVER_JOBS) as ex:
            list(ex.map(make, first))
        with ThreadPoolExecutor(COVER_JOBS) as ex:
            list(ex.map(make, later))

    def run(self, *key):
        from vrtools.mame.runner import parse_storm_log
        if key in self.failed and isinstance(self.failed[key], pytest.skip.Exception):
            pytest.skip(f"the run {key}: {self.failed[key].msg}")
        if key in self.failed:
            raise AssertionError(f"the run {key} failed: {self.failed[key]!r}") from self.failed[key]
        if key not in self.runs:
            self.runs[key] = self._make(key)
        r = self.runs[key]
        if not hasattr(r, "storm") and key[0] not in ("released", "neg"):
            r.storm = parse_storm_log(r.wd / "storm.txt")
        return r


def cover_keys(items) -> list:
    def spot(name):
        return [("spot", name, seed, w) for seed in SEEDS for w in ("set", "twin")] if CoverSession.taped(("spot", name)) else \
            [("spot", name, w) for w in ("set", "twin")]
    need = {"test_no_rain_under_cover": lambda p: [("pass", p["entry"], p["reverse"], SEEDS[0], "set")],
            "test_rain_only_through_the_exit_opening": lambda p: [("pass", p["entry"], p["reverse"], seed, w) for seed in SEEDS
                                                                  for w in ("set", "twin")],
            "test_the_cover_runs_hold_the_rate": lambda p: [("pass", p["entry"], p["reverse"], seed, "set") for seed in SEEDS]
            + ([("released", BAY_BRIDGE, True, "main")] if (p["entry"], p["reverse"]) == (BAY_BRIDGE, True) else []),
            "test_the_cover_does_not_change_the_game": lambda p: [("poke", "set"), ("poke", "twin")],
            "test_the_leak_measure_sees_rain_in_a_tunnel": lambda p: [("neg", "set"), ("pass", ALPINE, False, SEEDS[0], "twin")],
            "test_a_planted_fault_is_caught": lambda p: [("fault", p["fault"], "set")],
            "test_no_rain_inside_the_mouth_on_the_approach": lambda p: [("pass", p["entry"], p["reverse"], seed, "set") for seed in SEEDS],
            "test_the_pits_roof_coverage_from_the_six_spots": lambda p: spot(p["spot"]),
            "test_a_pit_stop_under_the_roof": lambda p: [("spot", "s7" if p["reverse"] else "s4", "set")],
            "test_the_four_views": lambda p: [("view", v, p["entry"], "set") for v in VIEWS]}
    keys = []
    for i in items:
        name = getattr(i, "originalname", None) or getattr(i, "name", "")
        p = getattr(getattr(i, "callspec", None), "params", {})
        if name in need and not i.get_closest_marker("skip"):
            keys += need[name](p)
    return keys


_COVER: dict = {}


@pytest.fixture
def cover_runs(request, storm_runs) -> CoverSession:   # noqa: F811 (the fixture)
    key = id(storm_runs)
    if key not in _COVER:
        try:
            s = CoverSession(storm_runs)
            s.prefetch(cover_keys(request.session.items))
        except (Exception, pytest.skip.Exception, pytest.fail.Exception) as e:
            _COVER[key] = e        # Phase 90: a construction that failed (or skipped) is not made again by every later test
            raise
        _COVER[key] = s
    s = _COVER[key]
    if isinstance(s, pytest.skip.Exception):
        pytest.skip(f"the cover session skipped in an earlier test: {s.msg}")
    if isinstance(s, BaseException):
        raise RuntimeError(f"the cover session failed in an earlier test: {s!r}") from s
    return s


# ---- the measures -------------------------------------------------------------------------------------------------------------
_TABLES: dict = {}


def _tables(rs, entry: int):
    """cover_geom.tables, once per set and entry (a march takes about half a second)."""
    if (id(rs), entry) not in _TABLES:
        _TABLES[(id(rs), entry)] = cover_geom.tables(rs, entry)
    return _TABLES[(id(rs), entry)]


def stretch_of(cs: CoverSession, entry: int, box: int) -> int | None:
    """The stretch index of the box at RAM `box` in `entry`'s table (cover_geom.table_bytes' layout), None for 0."""
    if not box:
        return None
    st = _tables(cs.rate.out, entry)
    k = (box - cs.table - 4 - cover_geom.STRSZ * len(st)) // cover_geom.BOXSZ
    for si, s in enumerate(st):
        if k < len(s.boxes):
            return si
        k -= len(s.boxes)
    raise AssertionError(f"box {box:#x} outside the table")


def cover_faults(cov) -> list:
    """Per pass of the cover's line: under_cover not exactly modes 2 and 3; in mode 2 a cluster drawn (by the rain or by the cover)
    or a splash spawned; in mode 3 a cluster drawn by the rain the cover did not leave to it, or under the pits roof's curtain a
    splash spawned."""
    out = []
    for a, c in zip(cov, cov[1:]):
        sp = c.spawns - a.spawns
        if c.under_cover != (1 if c.mode >= 2 else 0):
            out.append(("under_cover", c.frame, c.mode, c.under_cover))
        if c.mode == 2 and (c.drawn or c.curtain or c.drops or sp):
            out.append(("drawn under cover", c.frame, c.drawn, c.curtain, c.drops, sp))
        if c.mode == 3 and c.drawn > c.curtain:
            out.append(("not the curtain", c.frame, c.drawn, c.curtain))
        if c.mode == 3 and c.roof and sp:
            out.append(("splash under the roof", c.frame, sp))
    return out


HUD = [(0, 0, 135, 58), (180, 8, 250, 48), (325, 8, 496, 58), (0, 58, 115, 205), (360, 95, 480, 330), (0, 330, 150, 384),
       (380, 345, 480, 384)]
CAR = (148, 212, 348, 384)
# (x0, y0, x1, y1): the HUD's boxes, and the player's car in the chase views (spike 68's measure left both out: the car's own faces
# sort differently with the list's length, and its tyres show one of the rain's greys). Fix round 1, F4 (ii): the car's box is left
# out only in a view that shows the car (`car=True`: the passes' default view; not the cockpit view VR1 of spot s12w2).


def project(m, P):
    """Screen x, y and view z of world points P with the camera matrix m (12 floats; the projection fitted on the drops by spike 68:
    x = 248 + 210 vx / vz, y = 221 - 280 vy / vz)."""
    P = np.asarray(P, float)
    v = [m[k] * P[..., 0] + m[3 + k] * P[..., 1] + m[6 + k] * P[..., 2] + m[9 + k] for k in range(3)]
    vz = np.where(np.abs(v[2]) < 1e-6, 1e-6, v[2])
    return 248 + 210 * v[0] / vz, 221 - 280 * v[1] / vz, v[2]


def under_roof(x: float, y: float, z: float) -> bool:
    """A camera position under the roof by Metropolis's pits: inside its walls and ends, below its underside."""
    return -120.0 < x < -70.8 and cover_geom.ROOF_Z[0] < z < cover_geom.ROOF_Z[1] and y < cover_geom.ROOF_Y


def camera_pos(m) -> list[float]:
    return [-(m[3 * k] * m[9] + m[3 * k + 1] * m[10] + m[3 * k + 2] * m[11]) for k in range(3)]


# The pits roof's end openings as spike 68's measure took them from the drawn faces (out/p68/coverage.py): the road's x -120 to the
# divider's end (-99.8 at the exit, -99.9 at the entrance), the lane's -98.4 to its wall (-80.9 at the exit; -82.5 at the
# entrance, the corridor's wall beyond it), from the road at that end up to the roof's underside y 1.2.
ROOF_ENDS = {"exit": (339.7, -6.47), "entrance": (222.4, -10.45)}


def _clip_project(m, C, near: float = 0.1):
    """The polygon of world corners C seen with the camera m, clipped to view depth `near` and over (Sutherland-Hodgman), on
    screen; [] when wholly behind."""
    C = np.asarray(C, float)
    v = np.stack([m[k] * C[:, 0] + m[3 + k] * C[:, 1] + m[6 + k] * C[:, 2] + m[9 + k] for k in range(3)], 1)
    out = []
    for a, b in zip(v, np.roll(v, -1, 0)):
        if a[2] >= near:
            out.append(a)
        if (a[2] >= near) != (b[2] >= near):
            t = (near - a[2]) / (b[2] - a[2])
            out.append(a + t * (b - a))
    return [(248 + 210 * p[0] / p[2], 221 - 280 * p[1] / p[2]) for p in out]


def roof_opening(m):
    """(name, x0, x1, y0, z, corners) of the pits roof's end opening the camera m looks through: the nearer end wholly in front of
    it (spike 68's rule), else an end partly in front (a camera a few units from the end, looking down, sees only its lower part:
    its picture clipped at the view depth 0.1); None when neither is in front."""
    cam = camera_pos(m)
    lane = cam[0] > -99.1
    x0 = -98.4 if lane else -120.0
    best = None
    for name, (z, y0) in ROOF_ENDS.items():
        x1 = (-80.9 if name == "exit" else -82.5) if lane else (-99.8 if name == "exit" else -99.9)
        C = [(x0, y0, z), (x1, y0, z), (x1, cover_geom.ROOF_Y, z), (x0, cover_geom.ROOF_Y, z)]
        whole = bool((project(m, np.array(C))[2] > 0.1).all())
        corners = _clip_project(m, C)
        key = (not whole, abs(z - cam[2]))
        if len(corners) >= 3 and (best is None or key < best[0]):
            best = (key, (name, x0, x1, y0, z, corners))
    return best[1] if best else None


_INTERIOR: dict = {}


def interior_faces(rs, entry: int) -> list:
    """Per marched stretch of `entry` (not the pits roof's), the course's drawn triangles inside it: every vertex within its boxes
    (along a box, and across within its lateral extent, a unit of margin) and not above its highest roof: its road, walls and roof,
    which from inside lie in front of everything beyond its mouths. [(stretch, n x 3 x 3 triangles), ...]."""
    if (id(rs), entry) not in _INTERIOR:
        tris, _ = cover_geom.course_faces(rs, entry)
        out = []
        for st in _tables(rs, entry):
            if st.boxes[0].vis & cover_geom.ROOFED:
                continue
            top = max(mo.c[1] + mo.H for mo in st.mouths) + 0.5
            inside = np.zeros(tris.shape[:2], bool)
            for b in st.boxes:
                dx, dz = tris[..., 0] - b.o[0], tris[..., 2] - b.o[1]
                u, sl = dx * b.a[0] + dz * b.a[1], dz * b.a[0] - dx * b.a[1]
                inside |= (u >= -0.5) & (u <= b.L + 0.5) & (sl >= b.s[0] - 1.0) & (sl <= b.s[1] + 1.0)
            keep = inside.all(1) & (tris[..., 1] <= top).all(1)
            out.append((st, tris[keep]))
        _INTERIOR[(id(rs), entry)] = out
    return _INTERIOR[(id(rs), entry)]


def interior_mask(faces, m, tol: int) -> np.ndarray | None:
    """The screen pixels the stretch's interior faces cover with the camera m (each triangle clipped at the view depth 0.1: fix round
    1, F4: the long wall and roof quads near the camera, which straddle its plane, are exactly where the exit's drops leak), shrunk
    by `tol` pixels; None when the camera is not inside the stretch (behind none of its mouths)."""
    from PIL import Image, ImageDraw, ImageFilter
    st, tris = faces
    cam = camera_pos(m)
    if not any(-0.5 <= (cam[0] - b.o[0]) * b.a[0] + (cam[2] - b.o[1]) * b.a[1] <= b.L + 0.5
               and b.s[0] <= (cam[2] - b.o[1]) * b.a[0] - (cam[0] - b.o[0]) * b.a[1] <= b.s[1] for b in st.boxes):
        return None
    _, _, vz = project(m, tris)
    img = Image.new("L", (496, 384), 0)
    d = ImageDraw.Draw(img)
    for t, z in zip(tris, vz):
        if (z <= 0.1).all():
            continue
        pts = [(float(x), float(y)) for x, y in _clip_project(m, t)] if (z <= 0.1).any() else \
            [(float(x), float(y)) for x, y in zip(*project(m, t)[:2])]
        if len(pts) >= 3:
            d.polygon([(min(max(x, -4000.0), 4000.0), min(max(y, -4000.0), 4000.0)) for x, y in pts], fill=255)
    if tol:
        img = img.filter(ImageFilter.MinFilter(2 * tol + 1))
    return np.asarray(img) > 0


def _k_rows(wd: Path) -> dict:
    rows = {}
    for line in open(wd / "look.txt"):
        s = line.split()
        if s and s[0] == "K":
            rows[int(s[1])] = (int(s[2]), list(map(float, s[4:16])))
    return rows


def _snaps(wd: Path) -> list[Path]:
    return sorted((wd / "snap").rglob("*.png"))


_RAIN_RGB: dict = {}


def lit_frames(wd: Path) -> set:
    """The video frames of a run whose picture can hold a lit rain (v0.4.1; the review's fix round 1, F3): each pass with the rain's
    WCUR over 1 or its afterglow running (the storm log's W lines: storm_env watches them third and fourth) and the 5 frames after."""
    import struct as st
    from vrtools.mame.runner import parse_storm_log
    if not (wd / "storm.txt").exists():                 # a run without the storm's log: the negative control's set (the rain
        return set()                                    # alone, no lightning: no lit rain)
    log = parse_storm_log(wd / "storm.txt")
    out = set()
    for f, v in log.watches.items():
        if len(v) >= 4 and (st.unpack("<f", st.pack("<I", v[2]))[0] != 1.0 or v[3]):
            out.update(range(f, f + 6))
    return out


def rain_colours_lit(rs) -> np.ndarray:
    """`rain_colours` with the lit set's white: the colours on a frame of `lit_frames`."""
    from vrtools.arcade.weather import rain
    from vrtools.arcade.weather.tune import RainTune
    pal, P = rain.polygon_palette(rs), rain.overcast_params()
    e = pal[rain.tone_picks(rs, RainTune())[3][0]]
    v = [min(255, rain.xlat_value((e >> (5 * k)) & 31, 64, P[k])) >> 3 for k in range(3)]
    return np.array(sorted({tuple(c) for c in rain_colours(rs)} | {tuple((x << 3) | (x >> 2) for x in v)}))


def rain_colours(rs) -> np.ndarray:
    """The colours the rain's drops and splashes show on screen (n x 3): their colour words' palette entries through the overcast grade
    at full intensity (the words' mode), as MAME's 5-bit output expands them to 8 bits. v0.4.1: the near, mid and far tone sets; not
    the lit set (the palette's brightest white, 255 255 255: the game's own sparks, spray and HUD map draw it too, and differ between
    a set and its twin with the timing; the lit rain is never drawn under cover: gate2 measured spot s5's 2 027 px of "leak" all in
    that white). On the frames whose pass had the lit rain (flash or afterglow: `lit_frames`, a camera outside near a tunnel) the
    measures take `rain_colours_lit`, so a lit streak over a tunnel's inside is seen (the review's fix round 1, F3)."""
    from vrtools.arcade.weather import rain
    key = id(rs)
    if key not in _RAIN_RGB:
        pal, P = rain.polygon_palette(rs), rain.overcast_params()
        from vrtools.arcade.weather.tune import RainTune
        _, _, records, faces, _ = rain.drop_objects(RainTune())
        drops = rain.tone_words(rs, faces, RainTune())[:3 * records]          # near, mid, far (rain.SETS' order; the lit set left out)
        splashes = rain.splash_words(rs, 6)
        out = set()
        for w in set(drops + splashes):
            e = pal[w & 0x3FF]
            v = [min(255, rain.xlat_value((e >> (5 * k)) & 31, 64, P[k])) >> 3 for k in range(3)]
            out.add(tuple((x << 3) | (x >> 2) for x in v))
        _RAIN_RGB[key] = np.array(sorted(out))
    return _RAIN_RGB[key]


def rain_pixels(set_png: Path, twin_png: Path, colours: np.ndarray, car: bool = True) -> np.ndarray:
    """The rain's pixels of the set's picture: where it differs from the twin's (sum of RGB over 24) in one of the rain's own colours
    (`rain_colours`: the renderer's order of equal-depth polygons changes with the list's length, so the scenery's edges differ by a
    pixel between the two pictures, and the game's own sparks are timing-dependent: spike 61's note), the HUD's boxes left out."""
    from PIL import Image
    a = np.asarray(Image.open(set_png).convert("RGB")).astype(int)
    b = np.asarray(Image.open(twin_png).convert("RGB")).astype(int)
    rain = (np.abs(a - b).sum(2) > 24) & (a[..., None, :] == colours[None, None]).all(-1).any(-1)
    for x0, y0, x1, y1 in HUD + ([CAR] if car else []):
        rain[y0:y1, x0:x1] = False
    return rain


def _poly_mask(corners, tol: int) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFilter
    sil = Image.new("L", (496, 384), 0)
    ImageDraw.Draw(sil).polygon([(float(x), float(y)) for x, y in corners], fill=255)
    if tol:
        sil = sil.filter(ImageFilter.MaxFilter(2 * tol + 1))
    return np.asarray(sil) > 0


CUT_ROT, CUT_MOVE = 0.15, 8.0           # a camera change between two logic frames larger than this (a matrix term; units) is a cut


def _cut(cands) -> bool:
    """A camera cut among the candidate cameras of a picture (consecutive ones): the game's pit camera or a view's jump, not motion
    (at 330 km/h the chase camera moves about 2.5 units a frame)."""
    for m0, m1 in zip(cands, cands[1:]):
        if max(abs(a - b) for a, b in zip(m0[:9], m1[:9])) > CUT_ROT or max(abs(a - b) for a, b in zip(camera_pos(m0), camera_pos(m1))) > CUT_MOVE:
            return True
    return False


LAGS = (2, 1, 0, -1, -2)                 # the picture's camera: the camera RAM of frame f + lag (`leak`)


def leak(cs: CoverSession, entry: int, set_run, twin_run) -> tuple[int, int, int, list, int]:
    """(frames judged, frames with rain, leak pixels, the worst frames, the lag) of a pair of runs on the same tape: per snapshot of
    both, the rain pixels (`rain_pixels`) where they must not be: under the pits roof, farther than LEAK_TOL_PX outside the end
    opening the camera looks through (spike 68's measure: `roof_opening`); in a marched stretch, more than LEAK_TOL_PX inside the
    picture of its interior faces (`interior_mask`, clipped at the near plane: its roof, walls and road, which lie in front of
    everything beyond its mouths: a drop painted there is drawn over them).
    The picture's camera: the camera RAM at a frame's end is up to two frames off the picture; under a replayed tape that lag is
    a property of the run, so it is fitted ONCE per run (fix round 1, F4 (i): the lag in LAGS whose total leak is least; the
    old per-frame minimum could swallow a real leak at the opening's edge, where the camera moves up to 26 px a frame); a frame
    whose camera cuts between f and f + lag (the pit camera, a view's jump) is left out, as spike 68's measure did."""
    ka, kb = _k_rows(set_run.wd), _k_rows(twin_run.wd)
    sa, sb = _snaps(set_run.wd), _snaps(twin_run.wd)
    oa, ob = len(sa) - len(ka), len(sb) - len(kb)
    colours, colours_lit, lit = rain_colours(cs.rate.out), rain_colours_lit(cs.rate.out), lit_frames(set_run.wd)
    faces = interior_faces(cs.rate.out, entry)
    per = {lag: {} for lag in LAGS}
    wetf = {}
    for f in sorted(set(ka) & set(kb)):
        rain = rain_pixels(sa[ka[f][0] - 1 + oa], sb[kb[f][0] - 1 + ob], colours_lit if f in lit else colours)
        wetf[f] = bool(rain.any())
        for lag in LAGS:
            if f + lag not in ka or _cut([ka[g][1] for g in range(min(f, f + lag), max(f, f + lag) + 1) if g in ka]):
                continue
            m = ka[f + lag][1]
            cam = camera_pos(m)
            if entry == METROPOLIS and -121 < cam[0] < -70 and 215 < cam[2] < 347:
                op = roof_opening(m)
                if op is None:
                    continue
                per[lag][f] = int((rain & ~_poly_mask(op[5], LEAK_TOL_PX)).sum())
            else:
                masks = [mk for mk in (interior_mask(fc, m, LEAK_TOL_PX) for fc in faces) if mk is not None]
                if masks:
                    per[lag][f] = int((rain & np.logical_or.reduce(masks)).sum())
    common = set.intersection(*(set(v) for v in per.values())) if per else set()
    lag = min(LAGS, key=lambda g: (sum(per[g][f] for f in common), abs(g)))
    got = per[lag]
    total = sum(got.values())
    worst = sorted(((v, f) for f, v in got.items() if v), reverse=True)[:5]
    return len(got), sum(wetf[f] for f in got), total, worst, lag


def coverage(set_run, twin_run, colours: np.ndarray, cell: float = 0.5, keep=None, car: bool = True) -> tuple:
    """Spike 68's coverage of the pits roof's end opening from a static spot: the opening (the one the spot's camera looks through)
    cut into `cell` x `cell` cells on its plane; a cell counts when in some frame its projection is wholly on screen and clear of the
    HUD and the player's car; it is reached when rain was drawn inside its projection in one of those frames. (coverage, leak pixels,
    frames, end, cells reached, cells on screen, cells reached by the stricter count)
    The picture's camera is the one of the frames f-2..f+2 that fits it best (the camera is held still at a spot; the pit camera
    pans). `car`: the car's box left out (not in the cockpit view). Fix round 1, F4 (iii): a cell counts as reached by any rain
    pixel in its screen bounding box; the stricter count asks for one in the middle half of that box (each side shrunk by a quarter),
    reported beside it."""
    ka, kb = _k_rows(set_run.wd), _k_rows(twin_run.wd)
    sa, sb = _snaps(set_run.wd), _snaps(twin_run.wd)
    oa, ob = len(sa) - len(ka), len(sb) - len(kb)
    lit = lit_frames(set_run.wd)                         # v0.4.1: `colours` and its lit white on a lit frame (`rain_colours`)
    colours_lit = np.array(sorted({tuple(c) for c in colours} | {(255, 255, 255)}))
    frames = [f for f in sorted(set(ka) & set(kb)) if keep is None or keep(ka[f][1])]     # `keep`: the frames whose camera it accepts
    op0 = roof_opening(ka[frames[0]][1])
    assert op0 is not None, ("the spot's camera looks through no end of the roof", camera_pos(ka[frames[0]][1]))
    name, x0, x1, y0, zp, _ = op0
    nx, ny = int(round((x1 - x0) / cell)), int(round((cover_geom.ROOF_Y - y0) / cell))
    X, Y = np.meshgrid(x0 + np.arange(nx + 1) * (x1 - x0) / nx, y0 + np.arange(ny + 1) * (cover_geom.ROOF_Y - y0) / ny)
    hud = np.zeros((384, 496), bool)
    for a, b, c, d in HUD + ([CAR] if car else []):
        hud[b:d, a:c] = True
    hh = np.zeros((385, 497), np.int64)
    hh[1:, 1:] = hud.cumsum(0).cumsum(1)
    seen, hit, strict = np.zeros((ny, nx), bool), np.zeros((ny, nx), bool), np.zeros((ny, nx), bool)
    leak_total, used = 0, 0
    for f in frames:
        if f + 2 not in ka:
            continue
        cands = [ka[g][1] for g in (f + 2, f + 1, f, f - 1, f - 2) if g in ka]
        rain = rain_pixels(sa[ka[f][0] - 1 + oa], sb[kb[f][0] - 1 + ob], colours_lit if f in lit else colours, car)
        fit = None
        for m in cands:
            op = roof_opening(m)
            if op is None or op[0] != name:
                continue
            lk = rain & ~_poly_mask(op[5], LEAK_TOL_PX)
            if fit is None or lk.sum() < fit[0]:
                fit = (int(lk.sum()), m)
        if fit is None:
            continue
        if fit[0] and _cut(cands):
            continue
        used += 1
        leak_total += fit[0]
        sx, sy, vz = project(fit[1], np.stack([X, Y, np.full_like(X, zp)], -1))
        front = (vz[:-1, :-1] > 0.1) & (vz[:-1, 1:] > 0.1) & (vz[1:, :-1] > 0.1) & (vz[1:, 1:] > 0.1)
        ii = np.zeros((385, 497), np.int64)
        ii[1:, 1:] = rain.cumsum(0).cumsum(1)
        q = np.stack([sx[:-1, :-1], sx[:-1, 1:], sx[1:, :-1], sx[1:, 1:]])
        r = np.stack([sy[:-1, :-1], sy[:-1, 1:], sy[1:, :-1], sy[1:, 1:]])
        x0_ = np.clip(q.min(0), 0, 496).astype(int)
        x1_ = np.clip(q.max(0) + 1, 0, 496).astype(int)
        y0_ = np.clip(r.min(0), 0, 384).astype(int)
        y1_ = np.clip(r.max(0) + 1, 0, 384).astype(int)
        box = lambda t: t[y1_, x1_] - t[y0_, x1_] - t[y1_, x0_] + t[y0_, x0_]
        vis = front & (q.min(0) >= 0) & (q.max(0) < 496) & (r.min(0) >= 0) & (r.max(0) < 384)          # wholly on screen,
        vis[vis] &= box(hh)[vis] == 0                                                                  # clear of the HUD
        seen |= vis
        hit |= vis & (box(ii) > 0) & (x1_ > x0_) & (y1_ > y0_)
        qx0, qx1 = x0_ + (x1_ - x0_) // 4, x1_ - (x1_ - x0_) // 4
        qy0, qy1 = y0_ + (y1_ - y0_) // 4, y1_ - (y1_ - y0_) // 4
        strict |= vis & (ii[qy1, qx1] - ii[qy0, qx1] - ii[qy1, qx0] + ii[qy0, qx0] > 0) & (qx1 > qx0) & (qy1 > qy0)
    return hit.sum() / max(1, seen.sum()), leak_total, used, name, int(hit.sum()), int(seen.sum()), int(strict.sum())


def stale_excused_by_released(stale, load, released_stale, released_load, within: int | None = None) -> list[int]:
    """`stale` (a run's stale passes, its race load at `load`) less those within `within` (STALE_AFTER_LOAD_MAX) frames after the load
    on which main's released set, run on the same inputs and boot (its stale passes `released_stale`, its race load at
    `released_load`), is stale too: the same pass counted from each run's own race load."""
    within = STALE_AFTER_LOAD_MAX if within is None else within
    theirs = {f - released_load for f in released_stale}
    return [f for f in stale if not (0 < f - load <= within and f - load in theirs)]


def rate_faults(r, released=None) -> list:
    """Stage 2's gates on a run from the storm's load: stale lists, passes over RAIN_BUSY_MAX_MS, the overrun counter moving, the
    render rate outside 28-29 from the green, a pass breaking the split bound after the vblank count's move (`post_move_over`: the
    unit in flight over UNIT_MAX_US or the tail over TAIL_US; the join). With
    `released` (main's released set's DRY run on the same inputs and boot: `CoverSession`'s "released" run) a stale pass within
    STALE_AFTER_LOAD_MAX frames after the race load is the game's own when the released set is stale on the same pass
    (`stale_excused_by_released`; the session lead's ruling C5: Bay Bridge in reverse on a battery-RAM boot, the released v0.3
    game's own stale picture at the race load + 7)."""
    from tests.test_frame_rate import _stale_result
    from tests.test_weather_rain import post_move_over
    from vrtools.mame.framerate import RAIN_BUSY_MAX_MS, arcade_rate_misses
    from vrtools.mame.runner import parse_stale_log
    stretch = r.stretch()
    out = []
    stale, text = _stale_result(r)
    if released is not None and stale:
        assert released.load, ("the released set's run has no race load", released.wd)
        theirs = parse_stale_log(released.wd / "stale_list.txt")
        stale = stale_excused_by_released(stale, r.load, theirs, released.load)
        text += f" (main's released set, the same inputs and boot: stale {[f - released.load for f in theirs if f > released.load]} after its load)"
    if stale != []:
        out.append(("stale", text))
    over = [(f.frame, f.busy_us) for f in stretch if f.busy_us > RAIN_BUSY_MAX_MS * 1000]
    if over:
        out.append(("busy", over[:5]))
    if stretch and stretch[0].overrun != stretch[-1].overrun:
        out.append(("overrun", stretch[0].overrun, stretch[-1].overrun))
    misses = arcade_rate_misses(r.frames, r.rate, r.start, r.end, rate_from=r.green)
    if misses:
        out.append(("rate", misses[:5]))
    pm = post_move_over(r)
    if pm:
        out.append(("after the count's move", pm[:3]))
    return out


def _summary(cs: CoverSession, text: str) -> None:
    with open(cs.storm.base / "cover_summary.txt", "a") as out:
        out.write(text + "\n")


COVERED = [pytest.param(e, r, id=f"{n}{'_reverse' if r else ''}") for (e, r) in PASSES
           for n in [{METROPOLIS: "metropolis", ALPINE: "alpine", BAY_BRIDGE: "bay_bridge"}[e]]]
# The passes on which the curtain paints a few drops over the tunnel's walls or roof at the exit's edges (the marched stretches'
# curtain relies on the renderer's sort, which the converted courses' farthest-corner quads defeat near the exit: spike 68's
# analysis of the pits roof). The approved prototype does the same at four exits: seeded the same on the same tapes, Alpine 1 490 /
# 84, 168 / 14, 139 / 8 here against 520 / 64, 0, 1 182 / 50, Metropolis reverse 388 / 28, 594 / 61, 902 / 56 against 240 / 24,
# 596 / 61, 24 / 5 (the findings, stage 3, fix round 2); Bay Bridge's exit (normal) is not shown to be shared (one seed of eight
# here, none of eight on the prototype: R2-5, wider sample). Whether to improve on the prototype there is the owner's decision. The
# gate (the session lead's ruling F5, fix round 1) is a tripwire for a real regression, not a comparison with the prototype: each pass is measured on the taped game (`CoverSession.taped`) on the three generator
# trajectories SEEDS; the maximum over them of the pass's leak and of its worst frame at most LEAK_TRIP times this build's own
# measured maximum, OWN_LEAKS (px, worst frame px); every other pass none on all three.
# RE-PIN RULE: a figure of OWN_LEAKS, OWN_SPOT_CELLS, OWN_SPOT_LEAK or OWN_APPROACH may be re-pinned only with a named cause (a
# change that moves the passes' time or the generator's use: the join, a new module before the rain, a fix in the cover) and the
# prototype comparison, seeded the same, re-run and recorded in the findings beside the new figure.
LEAK_TRIP = 1.5
OWN_LEAKS = {(METROPOLIS, True): (318, 21), (ALPINE, False): (1404, 173), (ALPINE, True): (194, 7), (BAY_BRIDGE, True): (376, 17),
             (BAY_BRIDGE, False): (71, 8), (METROPOLIS, False): (966, 74)}
# Re-pinned for the streaming rain (v0.4.1, the re-pin rule's cause: its leaning streaks, up to 9 times v0.4's length, cross an
# exit's edge where v0.4's short drops did not; the measure without the lit white, `rain_colours`): this build's maxima over SEEDS
# (out/p88/gate2, 25 Nov; per seed px / worst): Metropolis normal 336/17, 966/74, 330/34 (the pits roof's exit: one long streak over
# the wall right of the opening at 123 km/h, 74 px, out/p88/stills/metro_roof_leak.png); Metropolis reverse 245/8, 205/11, 318/21;
# Alpine 287/21, 1404/173, 791/98; Alpine reverse 194/5, 92/4, 138/7; Bay Bridge normal 56/7, 71/8, 44/5; Bay Bridge reverse 12/2,
# 376/17, 202/10. Worse than v0.4's on three: Metropolis normal (8/3), Alpine's worst frame (84) and Bay Bridge
# reverse (40/6); better on the other three. v0.4's pins, for the record:
# (the maxima over SEEDS of fix round 2's measure run, out/p80c/fr2a, 19 Nov: per seed 0 / 0x9e3779b9 / 0x2468ace1, px and worst:
# Metropolis reverse 388/28, 594/61, 902/56; Alpine 1490/84, 168/14, 139/8; Alpine reverse 851/27, 1048/59, 794/45; Bay Bridge
# reverse 13/3, 20/4, 40/6; Bay Bridge normal 0, 0, 123/32 (4fe3bec's code on the third seed: 123/32; the prototype seeded the
# same: 0, 0, 0: not shown to be shared; ruled: pinned as a known limitation, not called shared). Re-pinned with their causes: Metropolis reverse
# 418/44 -> 900/56 (F6's first form) -> 902/61 (fix round 2: R2-1 and R2-2 change what mode 1 hides); Alpine reverse 1214/79 ->
# 1048/59 (M3); Bay Bridge normal 57/15 -> 123/32 (fix round 2: R2-1, the prototype's mode-1 hiding restored); Metropolis reverse
# 902/61 -> 912/61 (the join: the lightning before the rain moves the passes' time and the rain's generator use; the joined
# build's measure run out/p80j/cover2, 20 Nov: 388/28, 594/61, 912/56; every other figure as before; the prototype's side,
# seeded the same, depends only on the prototype set and the taped DRY game, both unchanged by the join: its figures stand);
# Metropolis normal none -> 8/3 (the join, the session lead's ruling J3 of round 2: out/p80j/cover2, 0, 8/3 (frames 5240-5247),
# 0 on the three seeds; none on the cover alone; the prototype seeded the same: as before), to be re-measured after J1 and J2.)


def _same_game(cs: CoverSession, runs, tape_key) -> list:
    """Faults of taped runs against their DRY tape run: each fed the whole tape (input_tape.lua's log equal to the tape) and the
    game's pass state (pass_state.lua) identical to the DRY run's from the race load to the end (fix round 1, F3: the cover draws
    only; the storm's generator, seeded or poked, changes no pass of the game)."""
    from vrtools.mame.framerate import parse_pass_log
    t = cs.run(*tape_key)
    tape = (t.wd / "tape.txt").read_text().splitlines()
    ref = [l.split()[2:] for l in parse_pass_log(t.wd / "pass.txt") if int(l.split()[2]) >= t.load]
    out = []
    if len(tape) < 500 or len(ref) < 500:              # spot s3's run is the shortest: 982 passes from its load
        out.append(("short", t.wd.name, len(tape), len(ref)))
    for r in runs:
        if (r.wd / "tape.txt").read_text().splitlines() != tape:
            out.append(("tape", r.wd.name))
        got = [l.split()[2:] for l in parse_pass_log(r.wd / "pass.txt") if int(l.split()[2]) >= t.load]
        first = next((k for k, (a, b) in enumerate(zip(ref, got)) if a != b), None if len(ref) == len(got) else min(len(ref), len(got)))
        if first is not None:
            out.append(("game", r.wd.name, "pass", first, ref[first][:6] if first < len(ref) else None, got[first][:6] if first < len(got) else None))
    return out


# ---- MAME -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("entry,reverse", COVERED)
def test_no_rain_under_cover(cover_runs, entry, reverse):
    """A RAIN pass through every flagged stretch of the course in that direction (Bay Bridge in reverse on a line past the reverse
    fork, which the prototype's autopilot never passed), the taped game on its first trajectory (SEEDS[0]): the camera is under
    cover (modes 2 and 3) in each stretch; on every pass `under_cover` is 1 exactly in modes 2 and 3; in mode 2 nothing of the rain
    is drawn and no splash spawned; in mode 3 the rain draws only the clusters the cover left to it (the curtain) and under the pits
    roof spawns no splash; approaching from outside, clusters behind the mouth are hidden (mode 1 hides some); after each stretch
    the rain is drawn again."""
    r = cover_runs.run("pass", entry, reverse, SEEDS[0], "set")
    cov = r.storm.cover
    assert len(cov) > 2000
    st = _tables(cover_runs.rate.out, entry)
    under = {stretch_of(cover_runs, entry, c.box) for c in cov if c.mode >= 2}
    assert under == set(range(len(st))) - ({1} if entry == METROPOLIS else set()) or under == set(range(len(st))), \
        (entry, reverse, "stretches passed under cover", under)
    assert cover_faults(cov) == [], cover_faults(cov)[:8]
    assert any(c.mode == 1 and c.hidden > 0 for c in cov)
    ends = [b.frame for a, b in zip(cov, cov[1:]) if a.mode >= 2 and b.mode < 2]
    for f in ends:
        after = [c for c in cov if f < c.frame <= f + 120 and c.mode < 2]
        assert after and max(c.drawn for c in after) > 0, (entry, reverse, "no rain after the exit at", f)
    _summary(cover_runs, f"cover {entry}{'r' if reverse else ''}: passes {len(cov)}, modes "
             f"{ {m: sum(1 for c in cov if c.mode == m) for m in range(4)} }, stretches under cover {sorted(under)}, "
             f"roof curtain passes {sum(1 for c in cov if c.roof)}, median curtain {statistics.median([c.curtain for c in cov if c.mode == 3] or [0])}, "
             f"single drops max {max(c.drops for c in cov)}")


@pytest.mark.parametrize("entry,reverse", COVERED)
def test_rain_only_through_the_exit_opening(cover_runs, entry, reverse):
    """The pass on the set and on its twin (the curtain never drawn), the taped game, on each of the three generator trajectories
    SEEDS; every frame while the camera is inside with an exit in view (mode 3): no rain pixel of the set's lies on the roof or the
    walls (`leak`: the pits roof's, beyond LEAK_TOL_PX of its measured end opening; a marched stretch's, more than LEAK_TOL_PX
    inside the picture of its interior faces), except on the passes of OWN_LEAKS, where the maximum over the trajectories of the
    pass's leak and of its worst frame is at most LEAK_TRIP times this build's own; rain was seen through the exit. Every run fed
    the whole tape and played the DRY run's game pass for pass."""
    figs = []
    for seed in SEEDS:
        a, b = cover_runs.run("pass", entry, reverse, seed, "set"), cover_runs.run("pass", entry, reverse, seed, "twin")
        assert _same_game(cover_runs, [a, b], ("pass", entry, reverse, "tape")) == []
        judged, wet, total, worst, lag = leak(cover_runs, entry, a, b)
        assert judged > 20 and wet > judged // 4, (seed, judged, wet)
        figs.append((seed, total, worst[0][0] if worst else 0, judged, lag, worst))
    own = OWN_LEAKS.get((entry, reverse), (0, 0))
    _summary(cover_runs, f"leak {entry}{'r' if reverse else ''}: per seed (seed, px, worst, frames, lag) "
             f"{[f[:5] for f in figs]}, max {max(f[1] for f in figs)} / {max(f[2] for f in figs)}, pinned {own}")
    assert max(f[1] for f in figs) <= LEAK_TRIP * own[0] and max(f[2] for f in figs) <= LEAK_TRIP * own[1], \
        (entry, reverse, "per seed (seed, px, worst, frames, lag, worst frames)", figs, "pinned", own)


NEG_MIN = 10000                         # px: the negative control's least leak (stage 3's first control: 90 941 px on Metropolis)


def test_the_leak_measure_sees_rain_in_a_tunnel(cover_runs):
    """Fix round 1, F4: the leak measure's negative control as a test. The storm with the rain alone (no cover: its drops drawn inside
    Alpine's tunnel too), on Alpine's tape, against the cover's twin on the same tape: the measure reports a large leak (over
    NEG_MIN px), so a measure gone blind (no mask, no frames, the wrong lag) fails here."""
    a, b = cover_runs.run("neg", "set"), cover_runs.run("pass", ALPINE, False, SEEDS[0], "twin")
    assert _same_game(cover_runs, [a], ("pass", ALPINE, False, "tape")) == []
    judged, wet, total, worst, lag = leak(cover_runs, ALPINE, a, b)
    _summary(cover_runs, f"negative control (Alpine, the rain alone): {judged} frames judged, leak {total} px, worst {worst[:2]}, lag {lag}")
    assert judged > 20 and total > NEG_MIN, (judged, total, worst)


APPROACH_MARGIN = 0.25                  # units: a drawn cluster's centre this far inside a stretch (and below its roof) is a fault
APPROACH_ZMIN = 1.0                     # view depth: an object nearer (or behind the camera) is not on screen and not judged


def inside_on_approach(cs: CoverSession, entry: int, r, low: bool = True) -> tuple[int, int, list]:
    """(passes logged, rain objects drawn on them, those drawn inside a stretch where the cover hides them) of a run's records.txt:
    under the pits roof (ROOFED) below its mouths' higher top; in a marched stretch, with `low` (a low view: fix round 2, R2-1, the
    approved prototype's rule) at any height, else (the high view) below the top."""
    st = _tables(cs.rate.out, entry)
    frames, drawn, bad = 0, 0, []
    for line in open(r.wd / "records.txt"):
        p = line.split()
        if len(p) < 15 or p[0] != "R":
            continue
        m, n, vals = list(map(float, p[2:14])), int(p[14]), list(map(float, p[15:]))
        if len(vals) != 4 * n:
            continue                                    # the last line, cut by the run's end
        frames += 1
        drawn += n
        for k in range(n):
            if vals[4 * k + 2] <= APPROACH_ZMIN:
                continue                                # behind the camera: not on screen (the renderer culls it)
            w = _world(m, vals[4 * k:4 * k + 3]) + [int(vals[4 * k + 3])]          # world x y z, kind (0 drops, 1 splash, 2 single)
            for s_ in st:
                any_height = low and not s_.boxes[0].vis & cover_geom.ROOFED
                if in_stretch(s_, w[0], w[2], -APPROACH_MARGIN) and (any_height or w[1] < top_of(s_) - APPROACH_MARGIN):
                    bad.append((int(p[1]), [round(x, 2) for x in w[:3]], w[3]))
    return frames, drawn, bad


def _world(m, v) -> list[float]:
    """World x, y, z of the view-space point v with the camera matrix m (the inverse of `project`'s transform)."""
    return [sum(m[3 * j + k] * (v[k] - m[9 + k]) for k in range(3)) for j in range(3)]


# The approach's known limitation (the session lead's pin ruling, 19 Nov): rain objects inside a stretch while approaching, the
# maximum over SEEDS of this build's own (fix round 1's measure: Metropolis reverse 0, 0, 2: one splash under the pits roof, two
# passes, frames 5221-5223 of seed 0x2468ace1); at most LEAK_TRIP times it; every other pass none. The likely cause is a follow-up
# for the owner (mode 1 hides a cluster within MG = 1 unit of a box while its drops spread about 4). The re-pin rule applies.
OWN_APPROACH = {(METROPOLIS, True): 2}


@pytest.mark.parametrize("entry,reverse", COVERED)
def test_no_rain_inside_the_mouth_on_the_approach(cover_runs, entry, reverse):
    """Fix round 1, M5: the approach (mode 1: a box near, the camera outside every stretch): on every such pass of the taped game on
    the three trajectories SEEDS, no rain object the pass drew (rain_records.lua: the drops' clusters and the splashes, from the
    display list itself) lies inside a stretch (APPROACH_MARGIN clear of its boxes' edges): in a marched stretch at any height (fix
    round 2, R2-1: the default view draws what the approved prototype draws), under the pits roof below its mouths' higher top: the
    rain stops
    at the mouth (the design), and above a roof it falls on it. Not a picture measure: from outside, a drop in front of the mouth and
    one behind it cover the same pixels; the records carry the depth the pictures lose. On the passes of OWN_APPROACH the maximum
    over the trajectories is at most LEAK_TRIP times this build's own (a known limitation, the prototype's margin)."""
    res = []
    for seed in SEEDS:
        frames, drawn, bad = inside_on_approach(cover_runs, entry, cover_runs.run("pass", entry, reverse, seed, "set"))
        _summary(cover_runs, f"approach {entry}{'r' if reverse else ''} seed {seed:#x}: mode-1 passes {frames}, rain objects drawn {drawn}, inside {len(bad)}")
        assert frames > 20 and drawn > 0, (seed, frames, drawn)
        res.append((seed, len(bad), bad[:4]))
    assert max(r[1] for r in res) <= LEAK_TRIP * OWN_APPROACH.get((entry, reverse), 0), (entry, reverse, res, OWN_APPROACH.get((entry, reverse), 0))


@pytest.mark.parametrize("fault", ["uc0", "ignore"])
def test_a_planted_fault_is_caught(cover_runs, fault):
    """Fix round 1, M6: the main behaviours' checks seen failing on their own assertion. Alpine's taped pass on a set with a planted
    fault: "uc0" (`under_cover` stuck at 0) and "ignore" (the rain never consults the cover: rain inside the tunnel) are each caught
    by `cover_faults`, the check test_no_rain_under_cover applies; "ignore" by the approach's check as well."""
    r = cover_runs.run("fault", fault, "set")
    found = cover_faults(r.storm.cover)
    kinds = {f[0] for f in found}
    assert len(r.storm.cover) > 2000 and kinds >= ({"under_cover"} if fault == "uc0" else {"drawn under cover"}), (fault, found[:4])
    if fault == "ignore":
        frames, drawn, bad = inside_on_approach(cover_runs, ALPINE, r)
        assert frames > 20 and len(bad) > 10, (frames, drawn, len(bad))


@pytest.mark.parametrize("entry,reverse", COVERED)
def test_the_cover_runs_hold_the_rate(cover_runs, entry, reverse):
    """Stage 2's rate gates on every cover pass (the taped game, every trajectory): no stale list, every pass at most
    RAIN_BUSY_MAX_MS, the overrun counter still, the render rate 28-29, the split bound after the vblank count's move on every storm
    pass (`post_move_over`); the cover itself never late but behind the game's own late pass."""
    battery = (entry, reverse) == (BAY_BRIDGE, True)               # booted on the session battery RAM (`CoverSession._make`)
    for seed in SEEDS:
        r = cover_runs.run("pass", entry, reverse, seed, "set")
        assert r.load and r.green and r.start
        faults = rate_faults(r, released=cover_runs.run("released", entry, reverse, "main") if battery else None)
        assert faults == [], (seed, faults)
        busiest = max((f for f in r.stretch()), key=lambda f: f.busy_us)
        _summary(cover_runs, f"rate {entry}{'r' if reverse else ''} seed {seed:#x}: busiest {busiest.busy_us / 1000:.2f} ms at "
                 f"{busiest.frame}, cover late passes {r.storm.cover[-1].late}, rain late passes {r.storm.passes[-1].late}")


def test_the_cover_does_not_change_the_game(cover_runs):
    """Fix round 1, F3: the hunt's autopilot race whose storm generator was poked at frame POKE_FRAME (sd_b_1234567) left its
    twin's path at frame 5732; the inputs differed first (frame 5730: the autopilot steers from samples at MAME's frame ends, which
    the passes' times move), the game two frames later. Under the DRY run's tape the poked set and the poked twin play the DRY
    game pass for pass to the end: the cover draws only (its absence from GAME_CHANGING_MODULES stands)."""
    runs = [cover_runs.run("poke", w) for w in ("set", "twin")]
    assert _same_game(cover_runs, runs, ("poke", "tape")) == []
    for r in runs:
        assert (r.wd / "seed.txt").read_text().split()[1] == str(POKE_FRAME), r.wd.name


# The session lead's rulings C3 and F5: with fewer than SPOT_FEW_CELLS of the end opening's cells on screen one cell is 2 % or more
# and a percentage gate is noise; such a spot (its game taped: TAPED_SPOTS) is measured on the three trajectories SEEDS and passes
# with its least count at least OWN_SPOT_CELLS's (this build's own least count, cells reached of on screen) less one, leak 0 on all
# three. Only s3 (4.6 units from the exit) falls under it. The approved prototype at the same stop, measured the same way (one
# trajectory): 34 of 36, with 3 308 px outside the opening (the findings). The re-pin rule above applies.
SPOT_FEW_CELLS = 50
OWN_SPOT_CELLS = {"s3": (32, 36)}       # fix round 1's measure run: 32, 34, 32 of 36
# s3's leak outside the opening (the session lead's pin ruling, 19 Nov): the maximum over SEEDS of this build's own, 0, 1 288 and
# 2 250 px; at most LEAK_TRIP times it; every other spot 0. 4fe3bec's code on seed 0x9e3779b9: 2 910 px; the prototype on its
# own trajectory: 3 308 (the findings). The re-pin rule applies.
OWN_SPOT_LEAK = {"s3": 2586}            # the join: 2 250 -> 2 278 (out/p80j/cover2: 0, 1 288, 2 278 px; the re-pin rule's cause:
                                        # the lightning before the rain; the prototype's 3 308 stands, as above); v0.4.1: 2 278 ->
                                        # 2 586 (the streaming rain; out/p88/gate2: 2 586, 2 214, 1 801 px, without the lit white)


@pytest.mark.parametrize("spot", list(SPOTS))
def test_the_pits_roof_coverage_from_the_six_spots(cover_runs, spot):
    """Spike 68's measure as a test: from each of the six camera spots under the roof by the pits (the camera held still, SPOT_SNAPS
    frames; the pit stops' camera pans), the rain reaches at least COVERAGE_MIN of the end opening's visible cells (with fewer than
    SPOT_FEW_CELLS on screen: the taped game on the three trajectories, the least count at least this build's own less one,
    OWN_SPOT_CELLS) and no rain pixel lies more than LEAK_TOL_PX outside it (s3: at most LEAK_TRIP times its own, OWN_SPOT_LEAK);
    the camera is under the roof (mode 3, the roof's curtain) and no splash is spawned; every run holds stage 2's rate gates (fix
    round 1, F2)."""
    taped = CoverSession.taped(("spot", spot))
    res = []
    for seed in (SEEDS if taped else (None,)):
        key = ("spot", spot) + ((seed,) if taped else ())
        a, b = cover_runs.run(*key, "set"), cover_runs.run(*key, "twin")
        if taped:
            assert _same_game(cover_runs, [a, b], ("spot", spot, "tape")) == []
        assert rate_faults(a) == [], (spot, seed, rate_faults(a))
        ka = _k_rows(a.wd)
        assert len(ka) >= SPOT_SNAPS - 10, len(ka)
        cov = {c.frame: c for c in a.storm.cover}
        window = [cov[f] for f in sorted(cov) if min(ka) <= f <= max(ka)]
        pit = SPOTS[spot][1] == "pit"             # the pit camera pans, out of the roof's ends too: its frames under the roof judged
        inside = [c for c in window if not pit or under_roof(c.cx, c.cy, c.cz)]
        assert len(inside) > 50 and all(c.mode == 3 and c.roof for c in inside), [(c.frame, c.mode, c.roof) for c in inside if not (c.mode == 3 and c.roof)][:5]
        assert window[-1].spawns == window[0].spawns
        frac, lk, used, end, hit, seen, strict = coverage(a, b, rain_colours(cover_runs.rate.out),
                                                          keep=(lambda m: under_roof(*camera_pos(m))) if pit else None,
                                                          car=SPOTS[spot][2] is None)
        res.append((seed, frac, lk, used, hit, seen, strict))
        cam = camera_pos(ka[min(ka)][1])
        _summary(cover_runs, f"spot {spot}{'' if seed is None else f' seed {seed:#x}'}: camera ({cam[0]:.1f}, {cam[1]:.1f}, {cam[2]:.1f}), "
                 f"{used} frames, the {end} end, coverage {100 * frac:.1f} % ({hit} of {seen} cells; the stricter count {strict}), "
                 f"leak {lk} px")
    assert all(r[3] > 100 for r in res) and max(r[2] for r in res) <= LEAK_TRIP * OWN_SPOT_LEAK.get(spot, 0), \
        (spot, res, OWN_SPOT_LEAK.get(spot, 0))
    if min(r[5] for r in res) < SPOT_FEW_CELLS:
        assert spot in OWN_SPOT_CELLS and taped, (spot, res, "few cells: no pinned count, or not taped")
        assert min(r[4] for r in res) >= OWN_SPOT_CELLS[spot][0] - 1, (spot, res, OWN_SPOT_CELLS[spot])
    else:
        assert all(r[1] >= COVERAGE_MIN for r in res), (spot, res)


@pytest.mark.parametrize("reverse", [False, True], ids=["normal", "reverse"])
def test_a_pit_stop_under_the_roof(cover_runs, reverse):
    """A Metropolis pit stop in the lane under the roof (the pit tests' paths: the normal pit path, the reverse one read backwards from
    the normal run, which the prototype's autopilot never managed in reverse): a whole stop (the player's pit handler for 300 frames
    or more) with the car under the roof; on every pass of it whose camera is under the roof (the pit camera pans, out of the roof's
    ends too) the cover is under cover with the roof's curtain, and nothing but the curtain is drawn, no splash spawned; the run holds
    stage 2's rate gates."""
    from vrtools.mame.runner import PIT_HANDLER, parse_pit_log
    r = cover_runs.run("spot", "s7" if reverse else "s4", "set")
    pit = parse_pit_log(r.wd / "pit.txt")
    first = next((k for k, p in enumerate(pit) if p.handler == PIT_HANDLER), None)
    assert first is not None, "no stop"
    end = next((k for k in range(first, len(pit)) if pit[k].handler != PIT_HANDLER), len(pit))
    car = pit[first:end]                                                          # the run's first stop, to its release
    stopped = [p.frame for p in car]
    assert stopped[-1] - stopped[0] >= 300, ("no whole stop", stopped[0], stopped[-1])
    assert all(-120 < p.x < -70 and cover_geom.ROOF_Z[0] < p.z < cover_geom.ROOF_Z[1] for p in car), (car[0].x, car[0].z)
    cov = [c for c in r.storm.cover if stopped[0] <= c.frame <= stopped[-1]]
    inside = [c for c in cov if under_roof(c.cx, c.cy, c.cz)]                 # the pit camera pans: in and out of the roof
    assert len(inside) > 50 and all(c.under_cover == 1 and c.roof for c in inside), [(c.frame, c.mode) for c in inside if not c.under_cover][:5]
    assert cover_faults(r.storm.cover) == [] and cov[-1].spawns == cov[0].spawns
    assert rate_faults(r) == [], rate_faults(r)
    _summary(cover_runs, f"pit stop {'reverse' if reverse else 'normal'}: stop {stopped[0]}-{stopped[-1]}, cover passes in it "
             f"{len(cov)} ({len(inside)} with the camera under the roof), modes {sorted({c.mode for c in cov})}, busiest {max(f.busy_us for f in r.stretch()) / 1000:.2f} ms")


def top_of(st) -> float:
    """The higher of a stretch's two mouths' tops (road + H): the height under which the cover hides a cluster (fix round 1, F6)."""
    return max(mo.c[1] + mo.H for mo in st.mouths)


def roof_margin(st, c) -> float:
    """How far inside the cover's test for "under this stretch's roof" the camera of the pass c is (negative: outside), as weather/
    cover.py's frame takes it: under a ROOFED stretch (the pits roof) its end's top (mouth 0's road + H) less the camera's y; under
    a marched one LOW_VIEW_MAX less the camera's height above the player's car (fix round 2, R2-4)."""
    if st.boxes[0].vis & cover_geom.ROOFED:
        return st.mouths[0].c[1] + st.mouths[0].H - c.cy
    return cover.LOW_VIEW_MAX - (c.cy - c.py)


def in_stretch(st, x: float, z: float, margin: float = 0.0) -> bool:
    return any(-margin <= (x - b.o[0]) * b.a[0] + (z - b.o[1]) * b.a[1] <= b.L + margin
               and b.s[0] - margin <= (z - b.o[1]) * b.a[0] - (x - b.o[0]) * b.a[1] <= b.s[1] + margin for b in st.boxes)


VIEW_MARGIN = 0.5                       # units: camera passes this near a box's edge or its roof are not judged


@pytest.mark.parametrize("entry", COVERED_COURSES, ids=["metropolis", "alpine", "bay_bridge"])
def test_the_four_views(cover_runs, entry):
    """Fix round 1, F6: each of the four views (VR1-VR4 pressed after the green) through the course's flagged stretches (Metropolis:
    the pits roof and the long tunnel; Alpine's tunnel; Bay Bridge's): on every pass whose camera is inside a stretch's boxes
    (VIEW_MARGIN clear of their edges) `under_cover` is 1 exactly when the camera is below the roof there (`roof_margin`) and 0
    above it; the high view (VR4) puts the camera above these roofs on almost every pass (the game draws the roof from above: the findings'
    pictures; in Alpine's tunnel it dips below the roof for a pass or two), so it sees the rain drawn there (it falls on the roof);
    the low views see the cover (modes 2 and 3; in Bay Bridge's low tunnel the VR3 camera rides at the roof's height, under it:
    out/p80c/look/f6_bay_bridge_views_vr1_vr3_vr4.png; fix round 2, R2-4: the rule's margin judges every such pass). In the high
    view no rain object is drawn inside a tunnel below its roof (R2-2: rain_records.lua, modes 0 and 1). No fault of
    `cover_faults`; every run holds stage 2's rate gates."""
    st = _tables(cover_runs.rate.out, entry)
    for v in VIEWS:
        r = cover_runs.run("view", v, entry, "set")
        assert cover_faults(r.storm.cover) == [] and rate_faults(r) == [], (v, cover_faults(r.storm.cover)[:3], rate_faults(r))
        judged, above, below, wrong, border = 0, [], [], [], []
        for c in r.storm.cover:
            for s_ in st:
                if not in_stretch(s_, c.cx, c.cz, -VIEW_MARGIN):
                    continue
                h = roof_margin(s_, c)
                if abs(h) < VIEW_MARGIN:
                    border.append(c)                    # within VIEW_MARGIN of the test's height: none measured in a marched tunnel
                    continue
                judged += 1
                (above if h < 0 else below).append(c)
                if c.under_cover != (1 if h > 0 else 0):
                    wrong.append((c.frame, round(c.cy, 2), round(c.py, 2), round(h, 2), c.under_cover, c.mode))
        assert judged > 30 and wrong == [], (v, judged, len(border), wrong[:8])
        if v.startswith("VR4"):
            assert len(above) > 10 * len(below) and max(c.drawn for c in above) > 0, (v, len(above), len(below))
            frames, drawn, bad = inside_on_approach(cover_runs, entry, r, low=False)     # R2-2: nothing inside a tunnel below its roof
            assert frames > 30 and drawn > 0 and bad == [], (v, frames, drawn, bad[:6])
        else:
            assert not above and any(c.mode >= 2 for c in below), (v, len(above), len(below), len(border))
        _summary(cover_runs, f"view {v} entry {entry}: passes judged inside a stretch {judged}, camera above the roof {len(above)}, "
                 f"below {len(below)}, at the roof's height {len(border)} (modes {sorted({c.mode for c in border})}), "
                 f"rain drawn above max {max([c.drawn for c in above] or [0])}")
