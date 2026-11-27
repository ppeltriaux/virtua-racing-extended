"""Phase 90: a PS2 course into one of the set's seven converted slots (pack 2; `pack.Ps2Plan`).

`convert_course`'s steps (tencourse) on a `vrtools.convert.ps2course` conversion: the collision in the plan's TGP slot, the
backdrop (the PS2 sky as a panorama) and the road blob in the plan's bank, the tile table, the spawn list (the start gantry and the
checkpoint gantries, no grid boards), the scenery cells (with the far silhouettes when the plan gives them room), the HUD outline,
the race blob by the project's rule (`race_blob_for`: the template's tables scaled to the course's length; untuned) and the reverse
variant (the project's reverse rule: `reverse_tables`, the plan's pairs and grid; with a pit lane, the reverse pit pair and box by the Saturn path's rule: `reverse_pit_of`). Nothing of the disc is
kept: the course is read from the user's own image at build time."""
from __future__ import annotations

import math

import numpy as np

from vrtools.arcade import tencourse as T
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet
from vrtools.convert import ps2course as PC
from vrtools.convert.geometry import TILE_GRID, bin_quads, encode_cells
from vrtools.convert.preview import course_picture
from vrtools.convert.race import gate_checkpoints, lap_total
from vrtools.convert.reverse import reverse_pit_in, reverse_points, reverse_tables
from vrtools.convert.road import heading_word, road_tables, tunnel_quads, with_tunnel_flags

FAR_AREAS = (150, 200, 300, 450, 700, 1000, 1500, 2500)     # far silhouettes: the smallest face area whose copies fit the budget


def conversion(course, plan, frame) -> PC.Ps2Conversion:
    """The course converted at the plan's detail, its covered stretches (tunnel lamps and faces over the road) in `tunnels`."""
    conv = PC.convert(course, frame, pit=plan.pit, far_cut=plan.far_cut, upright_keep=plan.upright_keep,
                      near_detail=plan.near_detail)
    if plan.merge:
        conv.scenery, conv.report["merges"] = PC.merge_scenery(conv.scenery, conv.report.get("scenery_banner_faces", 0),
                                                               windows=plan.windows)   # the banners and flags (last) left whole
    cs = np.array([s.centre for s in conv.sections])
    hs = np.array([s.height for s in conv.sections])
    heights = [hs[int(np.argmin(((cs - p) ** 2).sum(1)))] for p in conv.centreline]
    conv.tunnels = PC.join_stretches(conv.tunnels, PC.covered_stretches(conv.scenery, conv.centreline, heights))
    return conv


def far_cells(rs: RomSet, conv, host: int, budget: int):
    """The scenery's cells, with far silhouettes added when `budget` (bytes) allows: the smallest face area of FAR_AREAS whose
    copies fit it. Returns (cells, outside, report or None)."""
    cells, outside = bin_quads(conv.scenery, TILE_GRID)
    if budget <= 0:
        return cells, outside, None
    base = sum(len(v[0]) for v in encode_cells(cells, rs, host)[0].values())
    for area in FAR_AREAS:
        far = PC.far_copies(conv.scenery, conv.centreline, area_min=area)
        trial = {c: list(v) for c, v in cells.items()}
        for c, qs in far.items():
            trial.setdefault(c, []).extend(qs)
        extra = sum(len(v[0]) for v in encode_cells(trial, rs, host)[0].values()) - base
        if extra <= budget:
            return trial, outside, {"area_min": area, "copies": sum(len(v) for v in far.values()), "cells": len(far), "bytes": extra}
    return cells, outside, None


def frames_of(cl) -> list[list[int]]:
    """The cells drawn from every road point, normal then reverse (Phase 28's model)."""
    n, out = len(cl), []
    for s in (1, -1):
        for k in range(n):
            d = np.subtract(cl[(k + s) % n], cl[(k - s) % n])
            d = d / (np.linalg.norm(d) or 1.0)
            out.append(PC.visible_cells(cl[k][0], cl[k][1], d[0], d[1]))
    return out


GRID_POINTS = 50                    # road points after the line (either way) where the sixteen cars are still bunched in view
GRID_CARS = 1200                    # records the bunched field adds there (pack 2's reverse RAIN reached 10 500 at its start)


def frame_caps(n: int, cap: int) -> list[int]:
    """Per frame of `frames_of` (normal then reverse): `cap`, less GRID_CARS within GRID_POINTS after the line."""
    return [cap - GRID_CARS if k < GRID_POINTS else cap for k in range(n)] + \
           [cap - GRID_CARS if k == 0 or k > n - GRID_POINTS else cap for k in range(n)]


def grade(tier_records: list[dict[int, int]], frames: list[list[int]], cap, tier_bytes: list[dict[int, int]] | None = None,
          budget: int | None = None, far_first: dict[int, dict[int, float]] | None = None) -> tuple[dict[int, int], list[int]]:
    """Each cell's tier (0 the richest of len(tier_records)): every cell starts richest; while a frame draws more than `cap`
    records, the cell of that frame whose step to the next poorer tier saves most is stepped down. The poorest tier is never
    left. `cap`: one for every frame, or a list (one per frame). Then, with `budget`, while the cells' bytes (`tier_bytes`) are over it, the cell whose step saves most bytes is stepped
    down. `far_first` ({frame: {cell: distance}}): over its frames the farthest cell that saves records is stepped down first (the
    least visible: `Ps2Plan.frame_cuts`). Returns ({cell: tier}, per-frame records)."""
    last = len(tier_records) - 1
    cells = set().union(*tier_records)
    tier = {c: 0 for c in cells}
    rec = lambda c: tier_records[tier[c]].get(c, 0)
    caps = cap if isinstance(cap, list) else [cap] * len(frames)
    while True:
        totals = [sum(rec(c) for c in f if c in tier) for f in frames]
        worst = max(range(len(frames)), key=lambda i: totals[i] - caps[i])
        if totals[worst] <= caps[worst]:
            break
        steps = [(rec(c) - tier_records[tier[c] + 1].get(c, 0), c) for c in frames[worst] if c in tier and tier[c] < last]
        steps = [s for s in steps if s[0] > 0] or [(0, c) for _, c in steps]
        if not steps:
            break                               # the poorest tier alone is over the cap here
        if far_first and worst in far_first:
            dist = far_first[worst]
            tier[max(steps, key=lambda s: (dist.get(s[1], 0.0), s[0]))[1]] += 1
            continue
        tier[max(steps)[1]] += 1
    if budget is not None and tier_bytes is not None:
        size = lambda c: tier_bytes[tier[c]].get(c, 0)
        total = sum(size(c) for c in tier)
        while total > budget:
            steps = [(size(c) - tier_bytes[tier[c] + 1].get(c, 0), c) for c in tier if tier[c] < last]
            if not steps:
                break
            saved, c = max(steps)
            tier[c] += 1
            total -= saved
        totals = [sum(rec(c) for c in f if c in tier) for f in frames]
    return tier, totals


def with_seams(tiers: list[dict], tier: dict[int, int]) -> tuple[dict, int]:
    """The cells at their tiers; a cell beside one at another tier also takes its own tier's faces binned in that neighbour which
    reach into it, or the ground along the cells' edge would show a hole. Returns (cells, seam faces added)."""
    cells = {c: list(tiers[t][c]) for c, t in tier.items() if tiers[t].get(c)}
    seams = 0
    for b, tb in tier.items():
        bx, bz = (b & 15) * 128 - 1024, (b >> 4) * 128 - 1024
        for a in (b - 17, b - 16, b - 15, b - 1, b + 1, b + 15, b + 16, b + 17):
            if tier.get(a, tb) == tb:                    # either way: a richer cell beside a poorer one misses the richer
                continue                                # faces binned next door that reach into it, as the poorer one does
            for q in tiers[tb].get(a, []):
                xs, zs = [p[0] for p in q.p], [p[2] for p in q.p]
                if max(xs) > bx and min(xs) < bx + 128 and max(zs) > bz and min(zs) < bz + 128:
                    cells.setdefault(b, []).append(q)
                    seams += 1
    return cells, seams


def cut_frames(cl, frames: list[list[int]], caps: list[int], cuts) -> dict[int, dict[int, float]]:
    """`caps` lowered in place by the plan's `frame_cuts` (normal road point k is frame k; reverse road point j is the normal point
    (n - j) mod n seen the other way, frame n + that); returns {frame: {cell: distance from the road point to the cell's centre}}
    for those frames (`grade`'s far_first)."""
    n = len(cl)
    out = {}
    for direction, first, last, records in cuts:
        for j in range(first, last + 1):
            k = j % n if direction == "normal" else n + (n - j) % n
            caps[k] -= records
            x, z = cl[k % n]
            out[k] = {c: math.hypot(TILE_GRID.x0 + TILE_GRID.cw * (c % 16 + 0.5) - x, TILE_GRID.z0 + TILE_GRID.ch * (c // 16 + 0.5) - z)
                      for c in frames[k]}
    return out


def check_capped(name: str, capped) -> None:
    """Fix round 1, I10: PatchError when a scenery cell is over the arcade's records a cell (`encode_cells`' capped cells): its
    last faces would not be drawn, silently (the Saturn path refuses it for a cell holding props)."""
    if capped:
        raise PatchError(f"{name}: {len(capped)} scenery cells over the arcade's records a cell (cells {sorted(capped)}): their "
                         "last faces would not be drawn")


SETTLE_ROUNDS = 8                   # graded_cells: rounds of grading again under a lower cap / budget before giving up


def settle(attempt, cap: int, budget: int | None, name: str, rounds: int = SETTLE_ROUNDS):
    """`attempt(cap, budget)` -> (result, over, extra) until both are within (over: the worst frame's records past its cap; extra:
    the scenery's polygon bytes past the plan's budget), lowering the cap by over + 50 and the budget by extra + 4096 after each
    round. Returns the result; PatchError naming the course, what is over and by how much after `rounds` rounds (fix round 1, I1:
    no longer a silent give-up that ships a frame over its cap)."""
    for _ in range(rounds):
        result, over, extra = attempt(cap, budget)
        if over <= 0 and extra <= 0:
            return result
        if over > 0:
            cap -= over + 50
        if extra > 0 and budget is not None:
            budget -= extra + 4096
    what = ([f"a frame {over} records over its cap"] if over > 0 else []) + \
           ([f"the scenery {extra} bytes over its polygon budget"] if extra > 0 else [])
    raise PatchError(f"{name}: the graded scenery still has {' and '.join(what)} after {rounds} rounds")


WORST_VIEWS, WORST_APART = 3, 30    # the places per direction with the most scenery records (the parked check), this far apart


def worst_views(totals: list[int], n: int, k: int = WORST_VIEWS, apart: int = WORST_APART) -> dict[str, list[int]]:
    """The `k` road points per direction (in that direction's own numbering: reverse road point j is frame n + (n - j) mod n,
    as `cut_frames`) whose frames draw the most scenery records by the build's model (`frames_of`), each at least `apart` points
    from the others: the views tests/test_pack_rate.py parks the car at (fix round 1, I4)."""
    out = {}
    for name, base in (("normal", 0), ("reverse", n)):
        order = sorted(range(n), key=lambda i: -totals[base + i])
        picked = []
        for i in order:
            rp = i if name == "normal" else (n - i) % n
            if all(min((rp - q) % n, (q - rp) % n) >= apart for q in picked):
                picked.append(rp)
            if len(picked) == k:
                break
        out[name] = picked
    return out


def tier_quads(course, frame, cl, plan, floor, gates, heights) -> list[list]:
    """The scenery at each of the plan's `tiers` (richest first): `scenery` at the tier's detail, then merged with the banners and
    flags (its last faces) left whole."""
    quads = []
    for near, far_cut, windows in plan.tiers:
        q, rep = PC.scenery(course, frame, cl, road_floor=floor, far_cut=far_cut, upright_keep=plan.upright_keep, near_detail=near,
                            gates=gates, heights=heights)
        quads.append(PC.merge_scenery(q, rep["banner_faces"], windows=windows)[0])
    return quads


def graded_cells(rs: RomSet, conv, course, frame, plan, host: int):
    """The scenery as tiers (the plan's `tiers`, richest first, then the plan's own detail), each cell at the richest tier that
    keeps every frame within `plan.frame_records`; the far silhouettes (within `far_budget`) ride on the richest tier."""
    cl = conv.centreline
    cs, hs = np.array([s.centre for s in conv.sections]), np.array([s.height for s in conv.sections])
    heights = [hs[int(np.argmin(((cs - p) ** 2).sum(1)))] for p in cl]
    floor = min(s.height for s in conv.sections)
    quads = tier_quads(course, frame, cl, plan, floor, conv.gates, heights) + [conv.scenery]
    tiers = [bin_quads(q, TILE_GRID)[0] for q in quads]
    far = None
    if plan.far_budget > 0:
        rich = type(conv)(**{**conv.__dict__, "scenery": quads[0]})
        tiers[0], _, far = far_cells(rs, rich, host, plan.far_budget)
    encoded = [encode_cells(t, rs, host)[0] for t in tiers]
    records = [{c: v[1].record_count for c, v in e.items()} for e in encoded]
    sizes = [{c: len(v[0]) for c, v in e.items()} for e in encoded]
    frames = frames_of(cl)
    cap, budget = plan.frame_records, plan.poly_budget
    caps = frame_caps(len(cl), plan.frame_records)
    far_first = cut_frames(cl, frames, caps, getattr(plan, "frame_cuts", ()))
    def attempt(cap, budget):                           # the seams add records and bytes: graded again under a lower cap and
        tier, _ = grade(records, frames, [c - (plan.frame_records - cap) for c in caps], sizes, budget, far_first)   # budget
        cells, seams = with_seams(tiers, tier)                                                           # until as written
        enc = encode_cells(cells, rs, host)[0]                                                           # they hold both
        final = {c: v[1].record_count for c, v in enc.items()}
        totals = [sum(final.get(c, 0) for c in f) for f in frames]
        over = max(t - c for t, c in zip(totals, caps))
        extra = sum(len(v[0]) for v in enc.values()) - plan.poly_budget if plan.poly_budget else 0
        return (tier, cells, seams, totals), over, extra
    (tier, cells, seams, totals) = settle(attempt, cap, budget, plan.name)
    worst = max(range(len(totals)), key=totals.__getitem__)
    n = len(cl)
    report = {"tiers": [sum(1 for t in tier.values() if t == k) for k in range(len(tiers))], "far_copies": far, "seam_faces": seams,
              "frame_records": {"median": int(np.median(totals)), "peak": totals[worst], "at": worst % n,
                                "direction": "normal" if worst < n else "reverse", "cap": plan.frame_records},
              "worst_views": worst_views(totals, n)}
    outside = bin_quads(conv.scenery, TILE_GRID)[1]
    return cells, outside, report


def reverse_pit_of(conv):
    """Task 2 (the review's I11): the reverse variant's pit pair and box (`reverse.ReversePit`) of a PS2 course with a pit stop, by
    the Saturn path's rule (`reverse.reverse_pit_in`: a pair of lane quads deeper than the box, the normal box turned half a
    turn, ...) on the conversion's lane: its polyline, its tarmac quads as the polygons, the normal pit quad and box, the AI
    lines' scales the road tables use. None without a pit lane."""
    if conv.pit is None or conv.pit_quad is None:
        return None
    polys = [[(c[0], 0.0, c[2]) for c in q.corners] for q in conv.pit.quads]
    return reverse_pit_in(conv.collision, conv.centreline, conv.pit.line, polys, conv.pit_quad, conv.pit.box, conv.lanes)


def convert_ps2_course(rs: RomSet, course, plan, k: int, gantry_list: int | None) -> tuple[RomSet, T.Converted]:
    """The PS2 course `course` (a `vrtools.ps2.course.Ps2Course`) into slot `k` (tile table, race blob and spawn list k) as the plan
    says; `gantry_list`: the start gantry's list for the spawn list (None: the host's own). Returns the set and the Converted."""
    host = T.HOST_OF_BANK[plan.bank]
    frame = PC.Frame.for_host(rs, host)
    conv = conversion(course, plan, frame)
    tile_table, race_blob, spawn_list = T.tile_table_address(k), T.race_blob_address(k), T.spawn_list_address(k)
    col, cl, lap = conv.collision, conv.centreline, conv.lap
    tarmac = col.quads[:col.n_tarmac]
    tables = road_tables(lap, tarmac, attitude=conv.attitude, lanes=conv.lanes)
    loop = col.n_tarmac - (len(conv.pit.quads) + 1) if conv.pit else None      # the pit lane and its doubled entry follow the lap
    rtables = reverse_tables(tables, tarmac, loop) if plan.reverse else None
    tunnel = tunnel_quads(tables.segments, conv.tunnels, len(tables.lines[0]))
    tables = with_tunnel_flags(tables, tunnel)
    rtables = with_tunnel_flags(rtables, tunnel) if plan.reverse else None
    out, cell_map = T.install_collision(rs, col, plan.tgp_slot, cell_offsets=conv.cells)
    heading = (heading_word(cl[1][0] - cl[0][0], cl[1][1] - cl[0][1]) >> 16) * 4
    pano, brep = T.backdrop_for(rs, plan.bank, PC.panorama(course), heading // 32 - 8)
    out, image = T.place_blob(out, plan.bank, lambda b: T.encode_panorama(pano, b)[0])
    blob, gfx_dir = T.encode_panorama(pano, image)
    brep["bytes"] = len(blob)
    out, base = T.place_blob(out, plan.bank, lambda b: T.build_course_blob(out, host, tables, cell_map, col.surface, b, gfx_dir))
    T.write_tile_table(out, tile_table)
    cps = gate_checkpoints(conv.gates, len(cl))
    picture = course_picture(None, lap, None, None, faces=PC.picture_faces(course, frame), sea=PC.is_water)
    ents = T.spawn_list_for(rs, host, cl, cps, conv.height, gantries=False, start_gantry=True, grid_boards=False,
                            start_gantry_list=gantry_list)
    T.write_program_blob(out, spawn_list, T.encode_spawn_list(ents, spawn_list))
    if plan.frame_records is None or not plan.tiers:
        raise PatchError(f"{plan.name}: a PS2 plan grades its cells (`tiers` and `frame_records`)")
    cells, outside, graded = graded_cells(out, conv, course, frame, plan, host)
    far = graded["far_copies"]
    objs, words, capped = encode_cells(cells, out, host)
    check_capped(plan.name, capped)
    out = T.patch_course_tiles(out, host, objs, words, tile_table=tile_table)
    map_obj = T.install_outline(out, cl, plan.template, extra=[conv.pit.line] if conv.pit else [], floor=T.map_floor(col.quads))
    o = T.ORIGINALS[host]
    music = next(x.music for x in T.ORIGINALS if x.template == plan.template)
    normal_blob = T.race_blob_for(rs, plan.template, len(cl), plan.time_factor, plan.pace, plan.laps, checkpoints=cps)
    T.write_program_blob(out, race_blob, T.encode_race_blob(normal_blob, race_blob))
    rev = rpit = None
    if plan.reverse:
        rpit = reverse_pit_of(conv)
        rcps = T.reverse_checkpoints(cps, len(cl))
        totals = {key: lap_total(r, cps) for key, r in normal_blob.times.items()}
        rev = T.Reversed(rtables, T.race_blob_for(rs, plan.template, len(cl), plan.time_factor, plan.pace, plan.laps, checkpoints=rcps,
                                                  lap_totals=totals, start_points=plan.reverse_grid),
                         T.interior_on_the_left(reverse_points(cl)), tuple(plan.reverse_pairs),
                         pit_quad=rpit.quad if rpit else None, pit_box=rpit.box if rpit else None)
    left = T.interior_on_the_left(cl)
    report = {**conv.report, "source": "ps2", "ps2_index": plan.index, "cells": len(objs),
              "polygon_bytes": sum(len(v[0]) for v in objs.values()), "records": sum(v[1].record_count for v in objs.values()),
              "colour_entries": len(words), "capped_cells": len(capped), "outside": len(outside), "checkpoints": cps,
              "gates": conv.gates, "tunnels": conv.tunnels, "cover": conv.tunnels, "tunnel_quads": sorted(tunnel), "backdrop": brep,
              "map_outline": map_obj, "map_shift": left, "pit_quad": conv.pit_quad, "pit_box": conv.pit.box if conv.pit else None,
              "pit_line": conv.pit.line if conv.pit else None, "start_gantry": True, "start_gantry_list": gantry_list,
              "grid_boards": False, "lanes": None, "coverage": None, "hidden_gates": 0,
              "reverse_pit_quad": rpit.quad if rpit else None, "reverse_pit_box": rpit.box if rpit else None, "far_copies": far, "graded": graded, "thinned": conv.report.get("thinned", 0), "surface": list(col.surface),
              "centreline": [tuple(map(float, p)) for p in cl]}
    e = T.CourseEntry10(plan.name, plan.label, plan.bank, base, plan.tgp_slot, plan.template, tile_table, spawn_list, conv.pit_quad,
                        o.panel_map, o.panel_b, o.art, music, race_blob, plan.laps,
                        T.MAP_TX_SHIFTED if left else T.MAP_TX, T.MAP_CROSS_SHIFTED if left else 0, T.OFF_COURSE_LIMIT,
                        map_obj=map_obj, pit_box=conv.pit.box if conv.pit else None)
    return out, T.Converted(e, lap, cl, report, picture, rev, None)
