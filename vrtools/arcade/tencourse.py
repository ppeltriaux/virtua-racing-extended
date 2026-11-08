"""Assemble the ten-course set: the three originals plus converted courses as relocatable blobs (Phase 7, M4).

A converted course goes through the Phase 6 pipeline (placement at the arcade grid, lap, heights, collision,
road tables, scenery) and is installed as: a blob in the free space of its host bank (`arcade.blob`), its
collision in a free TGP slot (`patch.install_collision`), its scenery in polygon ROM behind a new tile table in
free program ROM (`patch.write_tile_table`), and a directory entry (`arcade.directory`).
"""
from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from vrtools.arcade.lettering import letters
from vrtools.arcade.picture import RECORD_BYTES, encode_record, free_runs, original_map, original_record, picture_blob, quantise
from vrtools.arcade.backdrop import GFX_MAGIC, ArcadePanorama, encode_panorama, read_panorama
from vrtools.arcade.blob import build_course_blob, place_blob
from vrtools.arcade.course import BANK_SIZE, CODE_FREE, COURSE_BANK, WINDOW, course_entry_at, road_centreline, road_lines
from vrtools.arcade.directory import ORIGINALS, CourseEntry10, Directory, directory_layout, install_directory
from vrtools.arcade.panel import free_chars, install_panels, render_panel
from vrtools.arcade.race import LEVELS, RACE_BLOB_BYTES, VARIANTS, RaceBlob, car_table, encode_race_blob, time_record
from vrtools.arcade.race import checkpoints as checkpoints_at
from vrtools.arcade.patch import (TILE_TABLE_BYTES, PatchError, copro_free_runs, install_collision, patch_course_tiles, poly_free_runs, write_data, write_program_blob,
                                  write_tile_table)
from vrtools.arcade.romset import RomSet
from vrtools.arcade.spawn import SPAWN_LIST_BYTES, decode_spawn_list, encode_spawn_list, replace_entities
from vrtools.arcade.title import install_title
from vrtools.convert.backdrop import CODE_LIMIT, TOP_CODE, convert_panorama
from vrtools.convert.collision import saturn_collision
from vrtools.convert.geometry import OUTSIDE_MAP_MAX, convert_tiles, placed
from vrtools.convert.preview import course_picture, with_name
from vrtools.convert.lap import Lap, centreline, order_slices
from vrtools.convert.place import COURSE_OF_TEMPLATE, GRID_OF_COURSE, choose_placement, grid_pose
GRID_CLEAR_OF_COURSE = {0: (20, 10), 1: (5, 25), 2: (5, 25)}   # Phase 22n: centreline points before / after the line where the AI lines'
                                                            # shift stays 0 (the grid: Big Forest's 13 points before the line to 3 after,
                                                            # Bay Bridge's and Acropolis's from the line to 15 after, race dumps)
from vrtools.convert.profile import _ground_quads, arc_height, banked_height, road_profile
from vrtools.convert.collision import mesh_height
from vrtools.convert.collision import pit_box, pit_entry_quad, pit_lane_line
from vrtools.convert.place import pit_lane_of
from vrtools.convert.gates import start_gate_point
from vrtools.convert.gates import GATE_GROUP, hide_unused_gates, saturn_gates
from vrtools.convert.race import car_table_for, check_laps, checkpoints_for, gate_checkpoints, time_records_for
from vrtools.convert.road import attitude_words, heading_word, road_tables
from vrtools.saturn.backdrop import BGS_OF_COURSE, SaturnPanorama, decode_bgs
from vrtools.saturn.course import SaturnCourse, decode_course
from vrtools.saturn.iso import Iso2352
from vrtools.saturn.trck import TrckFile

SATURN_NAMES = {"ALPINE00/TRCKALPN": "ALPINE", "AMAZON00/TRCKAMAZ": "AMAZON FALLS", "DIABLO00/TRCKDIAB": "DIABLO CANYON",
                "METROPOL/TRCKMETR": "METROPOLIS", "PACCOAST/TRCKPACC": "PACIFIC COAST", "SPEEDWAY/TRCKSPEE": "SURFERS OVAL",
                "SURFER00/TRCKSURF": "SURFERS ROAD"}
HOST_OF_BANK = {v: k for k, v in COURSE_BANK.items()}          # data bank -> menu index of the course that owns it


@dataclass(frozen=True)
class CoursePlan:
    """Where a Saturn course goes: host data bank (its backdrop, entity list, in-race tables and music come with
    it, so `template` is the host's course), TGP slot, select-screen label (0 BEGINNER, 1 MEDIUM, 2 EXPERT),
    the lap's minimum slice coverage and the scenery thinning fraction."""
    path: str
    name: str
    bank: int
    tgp_slot: int
    template: int
    label: int
    min_coverage: float = 0.98
    thin: float = 0.0
    terrain_thin: float = 0.0     # XZ area (units^2) under which terrain far from the road is left out (Phase 18: the set must fit)
    laps: int = 5                 # race length written at course load (the game's own setting is 5)
    time_factor: float = 1.0      # scales the checkpoint extensions (playtesting knob, design decision 11)
    pace: float = 1.0             # scales the opponents' performance floats (playtesting knob)
    banking: bool = False         # collision quads tilted by the ground mesh (Phase 9 A/B: see docs/spike/2026-11-balance.md)
    backdrop: bool = True         # Phase 18b: the course's own Saturn backdrop (False: the host bank's)
    camber: bool = True           # collision quads tilted by the slice normal's camber (profile.arc_height): the player's car banks with
                                  # the road (Phase 16 recon §2: its roll +0x2e followed a 13 deg tilt in the quads)
    lane_points: tuple = ()       # Phase 22c: (first, last) centreline points where the AI lines narrow and the walls may come in to a
                                  # drawn curb; only spots Pascal named (Amazon's first corner), never course-wide
    flag_start: int | None = None # Phase 22l (Pascal): the lap starts this many centreline points after the Saturn's START gate
                                  # (0: at it) where that keeps the road on the map; None: wherever the arcade's grid pose fits best


COURSES: list[CoursePlan] = [
    CoursePlan("ALPINE00/TRCKALPN", "ALPINE", 3, 3, 2, 0),
    CoursePlan("AMAZON00/TRCKAMAZ", "AMAZON FALLS", 1, 4, 0, 1, lane_points=((152, 191), (20, 37)), flag_start=0),   # first corner's curbs
                                                                                                   # (p22play29: 29-68 from the old start, 207 points
                                                                                                   # before the flag); v0.1.1 (Pascal, rec120): the pit
                                                                                                   # exit, the rock 7-10 out on the right at 26-35
    CoursePlan("DIABLO00/TRCKDIAB", "DIABLO CANYON", 2, 5, 1, 2),
    CoursePlan("METROPOL/TRCKMETR", "METROPOLIS", 2, 6, 1, 1, flag_start=0,   # Phase 22n: the building at the hairpin's inside
               lane_points=((318, 356),), time_factor=1.15),    # Phase 22p: the clock (the autopilot's 150-s race ended with 71                      # (points 318-356 R since the flag start; 22k's 124-140): the lines
                                                                # shift 11 left onto the Saturn's road there and the wall may follow
                                                                # them in to the drawn face (22k's named points trimmed the road under
                                                                # the lines and broke the decks' separation: backstep 116)
    CoursePlan("PACCOAST/TRCKPACC", "PACIFIC COAST", 1, 7, 0, 1, time_factor=1.15),   # Phase 22p: the clock (128 units left, every
                                                                                   # other course 300-650; Metropolis 71)
    CoursePlan("SPEEDWAY/TRCKSPEE", "SURFERS OVAL", 1, 8, 0, 0, min_coverage=0.8, flag_start=5),   # the file carries an unused infield;
                                                                                                # 22l: at the flag the road reaches 992 of 970 (5: 954; 6-7 re-aim to 1221)
    CoursePlan("SURFER00/TRCKSURF", "SURFERS ROAD", 1, 9, 0, 2, flag_start=6),   # 22l: at the flag the road reaches 992 of 970 (5: 954; 6-7 re-aim to 1221)
]


POLY_FLOOR_BYTES = 65536        # polygon ROM the ten-course set leaves free (Phase 18: the Saturn's scenery layers fill the rest)


def poly_budget(rs: RomSet) -> int:
    """Erased polygon-ROM bytes left for scenery (the sum of `poly_free_runs`)."""
    return sum(n for _, n in poly_free_runs(rs))


def tgp_budget(rs: RomSet) -> int:
    """Free words of the TGP data ROM: the blank runs install_collision allocates from (0xffffffff words in the
    free tail and zero words in the fillers between the originals' list blocks)."""
    return sum(n for _, n in copro_free_runs(rs))


def _disc(cue: Path) -> Iso2352:
    cue = Path(cue)
    m = re.search(r'FILE\s+"([^"]+)"', cue.read_text(errors="replace"))
    if not m:
        raise PatchError(f"{cue}: no FILE line")
    return Iso2352(cue.parent / m.group(1))


def load_saturn_course(cue: Path, path: str) -> SaturnCourse:
    """The decoded TRCK file `path` (under VRSRCDIR/TRACKS00) from the disc's data track named in the .cue."""
    return decode_course(TrckFile.from_bytes(_disc(cue).read(f"VRSRCDIR/TRACKS00/{path}")))


def load_saturn_backdrop(cue: Path, name: str) -> SaturnPanorama:
    """The course's Saturn backdrop (`BGS_OF_COURSE`), decoded."""
    return decode_bgs(_disc(cue).read(f"VRSRCDIR/TRACKS00/{BGS_OF_COURSE[name]}"))


# Phase 18b (recon §2, Task 4 measurements): the arcade shows source pixel heading/32 at the screen's left edge, the
# Saturn panorama x 0 at its start direction; both grow turning right. Vertically the Saturn's picture top (panorama row
# 15) goes to the band's top and its horizon (row ~100, Pacific Coast's sea) to the arcade's (band pixel ~124, Bay
# Bridge's sea line): the Saturn's whole visible sky fits the band, ~9 % flatter than its aspect.
BACKDROP_TOP_ROW = 15.0
BACKDROP_V_SCALE = 1.46
# Layer 3 above and below the band is filled from the panorama's first and last-row first entries (boot 0xffe034): the
# converter puts its reserved solid tiles there; the bottom one is palette 96's second code.
BACKDROP_FILL_CODE = TOP_CODE + 1


def column_offset_for(sat: SaturnCourse, min_coverage: float) -> int:
    """Arcade column of the Saturn panorama's x 0: the arcade heading of the Saturn lap's start direction (the lap
    ordered from slice 0, under the current placement) / 32, less 8 to centre the two fields of view (496/2 − 1.6 × 160)."""
    cl = centreline(order_slices(sat, start_slice=0, min_coverage=min_coverage))
    heading = (heading_word(cl[1][0] - cl[0][0], cl[1][1] - cl[0][1]) >> 16) * 4
    return heading // 32 - 8


def backdrop_for(rs: RomSet, bank: int, sat_pano: SaturnPanorama, column_offset: int) -> tuple[ArcadePanorama, dict]:
    """The course's converted backdrop (codes 0x3000-0x3fff, 32 palettes: the whole backdrop range is the course's)."""
    p, rep = convert_panorama(sat_pano, BACKDROP_TOP_ROW, column_offset, BACKDROP_FILL_CODE, v_scale=BACKDROP_V_SCALE)
    rep.update(code_limit=CODE_LIMIT, column_offset=column_offset, map_sha1=hashlib.sha1(p.map.tobytes()).hexdigest())
    return p, rep


@dataclass
class Converted:
    entry: CourseEntry10
    lap: Lap
    centreline: list[tuple[float, float]]
    report: dict
    picture: object = None               # Phase 21: the select picture without its name (convert/preview.py), uint8 168 x 128 x 3


def tile_table_address(k: int, code_base: int = CODE_FREE[0]) -> int:
    """Program-ROM address of the k-th new tile table, after the directory and its routines."""
    end = (directory_layout(code_base)["end"] + 15) // 16 * 16
    addr = end + k * TILE_TABLE_BYTES
    if addr + TILE_TABLE_BYTES > code_base + CODE_FREE[1]:
        raise PatchError(f"tile table {k} does not fit the free program ROM")
    return addr


NEW_COURSES = 7
# Phase 14 (docs/spike/2026-11-presentation-recon.md §2-3): the HUD map is car-centred, heading up, at a fixed scale, and the
# player's cross is a fixed 3x3 tile block; an anticlockwise course hangs its outline left of the cross, into the screen's
# middle, so its map and cross move 11 cells right. The game puts a car back on the road after 128 logic frames with a wheel
# off the tarmac; without the originals' walls that is 160 units of grass or water, so the converted courses use 40.
MAP_TX = 149.0                  # the game's screen translate x of the map section
MAP_SHIFT_CELLS = 11            # 8 px per tile cell; the cross lands on columns 59..61 of the 62 visible
MAP_TX_SHIFTED = MAP_TX + 8 * MAP_SHIFT_CELLS
MAP_CROSS_SHIFTED = 2 * MAP_SHIFT_CELLS
OFF_COURSE_LIMIT = 128          # logic frames, as the originals (0x80, about 4.3 s; Phase 14 had 40 when the courses had no walls: Pascal, Phase 22a: "the car just gets out and gets a reset")


def interior_on_the_left(centreline: list[tuple[float, float]]) -> bool:
    """The course's interior lies on the left of the direction of travel (anticlockwise): the shoelace area of the
    centreline over (x, z) is positive. The originals are clockwise (-505k, -449k, -656k); Alpine and Pacific Coast
    are anticlockwise (+602k, +847k)."""
    n = len(centreline)
    area = sum(centreline[i][0] * centreline[(i + 1) % n][1] - centreline[(i + 1) % n][0] * centreline[i][1] for i in range(n)) / 2
    return area > 0


def race_blob_address(k: int, code_base: int = CODE_FREE[0]) -> int:
    """Program-ROM address of the k-th course's race blob, after the seven tile tables."""
    addr = tile_table_address(NEW_COURSES, code_base) + k * RACE_BLOB_BYTES
    if addr + RACE_BLOB_BYTES > code_base + CODE_FREE[1]:
        raise PatchError(f"race blob {k} does not fit the free program ROM")
    return addr


MAX_ENTITIES = 32


def spawn_list_address(k: int, code_base: int = CODE_FREE[0]) -> int:
    """Program-ROM address of the k-th course's spawn list, after the seven race blobs."""
    size = SPAWN_LIST_BYTES(MAX_ENTITIES)
    addr = race_blob_address(NEW_COURSES, code_base) + k * size
    if addr + size > code_base + CODE_FREE[1]:
        raise PatchError(f"spawn list {k} does not fit the free program ROM")
    return addr


START_GATE_NEAR = 8            # Phase 22o: a course whose Saturn START gate stands within this many road points of its line gets no
                               # host start gantry (Pascal, p22play99 Metropolis: "2 start flags" since the 22l flag starts; Amazon
                               # Falls and Metropolis start at the gate, the Oval and Surfers Road 50-60 units after it; Diablo's
                               # gate is 36 points before its line and keeps both)


def spawn_list_for(rs: RomSet, host: int, line: list[tuple[float, float]], checkpoints: tuple[int, ...], height,
                   gantries: bool = True, start_gantry: bool = True, grid_boards: bool = True) -> list:
    """The host course's race furniture (minimap, start and checkpoint gantries, grid boards) re-placed on `line`."""
    host_line = road_centreline(road_lines(rs, course_entry_at(rs, COURSE_BANK[host]))[:1])
    ents = replace_entities(decode_spawn_list(rs, ORIGINALS[host].spawn_table), host_line, checkpoints_at(rs, ORIGINALS[host].template),
                            line, checkpoints, height, gantries=gantries, start_gantry=start_gantry, grid_boards=grid_boards)
    if len(ents) > MAX_ENTITIES:
        raise PatchError(f"{len(ents)} entities exceed the spawn list's {MAX_ENTITIES}")
    return ents


def race_blob_for(rs: RomSet, template: int, n_points: int, time_factor: float = 1.0, pace: float = 1.0,
                  laps: int = 5, checkpoints: tuple[int, ...] | None = None) -> RaceBlob:
    """Checkpoints at thirds of a lap of `n_points` (or `checkpoints`: Phase 22e, the Saturn gates), the template's twelve time records scaled by sector length,
    and the original car table (variant 0 for both variants) with the opponents' pace scaled. ConvertError when
    `laps` needs more extensions than a record holds."""
    cps = checkpoints if checkpoints is not None else checkpoints_for(n_points)     # Phase 22e: the Saturn gates
    check_laps(laps, cps)
    tcps = checkpoints_at(rs, template)
    tpoints = course_entry_at(rs, COURSE_BANK[COURSE_OF_TEMPLATE[template]]).header.road_points
    times = {(v, lvl): time_records_for(time_record(rs, v, template, lvl), tpoints, tcps, n_points, cps, time_factor)
             for v in range(VARIANTS) for lvl in range(LEVELS)}
    return RaceBlob(times, cps, car_table_for(car_table(rs, 0), pace))


def convert_course(rs: RomSet, sat: SaturnCourse, name: str, bank: int, tgp_slot: int, template: int, tile_table: int,
                   label: int = 0, panel: tuple[int, int, int] | None = None, spawn_table: int | None = None,
                   min_coverage: float = 0.98, merge: bool = True, thin: float = 0.0, terrain_thin: float = 0.0, race_blob: int | None = None,
                   laps: int = 5, time_factor: float = 1.0, pace: float = 1.0, spawn_list: int | None = None,
                   banking: bool = False, camber: bool = True, backdrop: bool = True, saturn_cue: Path | None = None,
                   lane_points: tuple = (), flag_start: int | None = None) -> tuple[RomSet, Converted]:
    """Convert one Saturn course into `rs`: blob in `bank`, collision in `tgp_slot` (straight slices merged when
    `merge`), scenery behind `tile_table` (thinned by `thin` when > 0). The entry's panel (map A, map B, art)
    defaults to the host course's (ten_course_set generates one); the entity spawn list defaults to the host's
    too (it carries the HUD minimap entity: an empty list draws the map huge and the car lost the hairpin
    without it). With `race_blob` (a free program-ROM address) the entry gets its own race blob (`race_blob_for`)
    and `laps`; without one it races on the template's tables. With `spawn_list` (a free program-ROM address) the
    entry gets the host's race furniture re-placed on its own road (`spawn_list_for`) instead of the host's whole
    list. PatchError names the course when its collision or blob does not fit."""
    host = HOST_OF_BANK[bank]
    # the player spawns where the template's tables put it (GRID_OF_TEMPLATE): the converted road must pass there
    grid_course = COURSE_OF_TEMPLATE[template]
    pl = choose_placement(sat, grid_pose(rs, grid_course), grid_point=GRID_OF_COURSE[grid_course][0], min_coverage=min_coverage,
                          flag_start=flag_start)                                  # Phase 22l: at the Saturn's flag where it fits
    with placed(pl.angle, pl.tx, pl.tz):
        lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=min_coverage)
        n_props = len(sat.placements.get(GATE_GROUP, []))
        sat = hide_unused_gates(sat, centreline(lap))                           # Phase 22t: no C.P. flag without its checkpoint
        hidden_gates = n_props - len(sat.placements.get(GATE_GROUP, []))
        heights = road_profile(sat, lap)
        hfn = banked_height(lap, heights, mesh_height(_ground_quads(sat))) if banking else \
            arc_height(lap, heights, sat.segments, camber=camber, ground=sat)       # Phase 16 (22a: the drawn banking): the arc profile (no 2-D steps) + the camber
        col, cells = saturn_collision(sat, hfn, lap=lap, merge=merge, cover=True, lane_points=lane_points,   # every AI line on tarmac (Phase 11)
                                      grid_clear=GRID_CLEAR_OF_COURSE[COURSE_OF_TEMPLATE[template]])   # 22n: the lines keep still at the grid
        pts = centreline(lap)                                                   # the same resampling road_tables uses
        pit_quad = pit_entry_quad(sat, col, pts)                                # Phase 22f: the pit lane's mouth, else none; Phase 22i:
        box = pit_box(sat, col, pts) if pit_quad is not None else None          # the pit sequence parks the car at the course's own box
        if pit_quad is not None and not pit_lane_of(sat).pit_stop:
            pit_quad = box = None
        tables = road_tables(lap, col.quads[:col.n_tarmac], attitude=attitude_words(lap, sat.segments, pts, heights),
                             lanes=col.lanes)   # Phase 15; Phase 22c: the AI lines narrow at a curb at the road
        try:
            out, cell_map = install_collision(rs, col, tgp_slot, cell_offsets=cells)      # refuses original or taken slots
            gfx_dir, backdrop_report = None, None
            if backdrop and saturn_cue is not None:
                pano, backdrop_report = backdrop_for(rs, bank, load_saturn_backdrop(saturn_cue, name), column_offset_for(sat, min_coverage))
                out, image = place_blob(out, bank, lambda b: encode_panorama(pano, b)[0])
                blob, gfx_dir = encode_panorama(pano, image)                                # the directory follows GFX_MAGIC
                backdrop_report["bytes"] = len(blob)
            out, base = place_blob(out, bank, lambda b: build_course_blob(out, host, tables, cell_map, col.surface, b, gfx_dir))
        except PatchError as e:
            raise PatchError(f"{name}: {e} (TGP budget left {tgp_budget(rs)} words, "
                             f"collision {col.list_words + 16 * len(col.quads)} words)") from e
        write_tile_table(out, tile_table)
        cl = centreline(lap)
        pit_line = pit_lane_line(sat, cl)                                       # Phase 22g: the pit lane on the HUD map
        cps = gate_checkpoints(saturn_gates(sat, cl), len(cl))                    # Phase 22e: the Saturn's own gates fire
        picture = course_picture(sat, lap, None, None)                         # Phase 21: the select picture (named later)
        if spawn_list is not None:
            gate = start_gate_point(sat, cl)                                   # Phase 22o: one START arch — the Saturn's own
            host_start = gate is None or min(gate, len(cl) - gate) > START_GATE_NEAR   # gate where the lap starts at it, else the host's
            ents = spawn_list_for(rs, host, cl, cps, hfn, gantries=False, start_gantry=host_start,   # (the host's narrow C.P. gantries left out;
                                  grid_boards=False)                                             # Phase 22q: the grid boards' flag row too)
            write_program_blob(out, spawn_list, encode_spawn_list(ents, spawn_list))
            spawn_table = spawn_list
        objs, words, report = convert_tiles(sat, out, host, thin=thin, keep_near=cl, terrain_thin=terrain_thin,
                                            outside_limit=OUTSIDE_MAP_MAX if flag_start is not None or pit_quad is not None else 0)   # Phase 22l: a flag
                                                                                               # start (22n: or a pit-lane placement) may leave a few scenery quads off the map
        report["coverage"] = col.coverage
        report["start_gantry"] = host_start if spawn_list is not None else None     # Phase 22o: the host's start gantry placed?
        report["grid_boards"] = False if spawn_list is not None else None           # Phase 22q: the host's grid boards (the flag row) left out
        report["lanes"] = col.lanes                                                 # Phase 22n: (left, right, shift) per centreline point
        report["checkpoints"] = cps
        report["hidden_gates"] = hidden_gates                                        # Phase 22t: the C.P. gates left out
        if backdrop_report is not None:
            report["backdrop"] = backdrop_report
    out = patch_course_tiles(out, host, objs, words, tile_table=tile_table)
    map_obj = install_outline(out, cl, template, extra=[pit_line] if pit_line else [])   # Phase 22b: the HUD map's own outline
    report["map_outline"] = map_obj
    pa, pb, art = panel if panel else (ORIGINALS[host].panel_map, ORIGINALS[host].panel_b, ORIGINALS[host].art)
    spawn = ORIGINALS[host].spawn_table if spawn_table is None else spawn_table
    music = next(o.music for o in ORIGINALS if o.template == template)
    race = 0
    if race_blob is not None:
        write_program_blob(out, race_blob, encode_race_blob(race_blob_for(rs, template, len(cl), time_factor, pace, laps, checkpoints=cps), race_blob))
        race = race_blob
    left = interior_on_the_left(cl)
    report["map_shift"] = left
    report["pit_quad"] = pit_quad
    report["pit_box"] = box
    e = CourseEntry10(name, label, bank, base, tgp_slot, template, tile_table, spawn, pit_quad, pa, pb, art, music, race,
                      laps if race_blob is not None else 0, MAP_TX_SHIFTED if left else MAP_TX, MAP_CROSS_SHIFTED if left else 0,
                      OFF_COURSE_LIMIT, map_obj=map_obj, pit_box=box)
    return out, Converted(e, lap, cl, report, picture)


def install_outline(rs: RomSet, cl, template: int, extra=()) -> tuple[int, int, int]:
    """Phase 22b: the course's HUD map outline (`hudmap.outline_quads` along its centreline) written into free polygon ROM
    on the colour entry of its host's outline (the game's table at MAP_OBJ_TABLE, by data index); returns the object list
    record (polygon word address, tex, size) the directory's `mapobj` routine hands to the map entity."""
    from vrtools.arcade.course import MAP_OBJ_TABLE
    from vrtools.arcade.patch import poly_free_runs, write_polygons
    from vrtools.convert.hudmap import encode_outline, outline_quads
    host_list = struct.unpack("<I", rs.read_v60(MAP_OBJ_TABLE + 4 * template, 4))[0]
    _, host_tex, _, _ = struct.unpack("<4I", rs.read_v60(host_list, 16))
    blob, layout = encode_outline(outline_quads(cl, extra=list(extra)), tex=host_tex + 1)   # the host's first outline quad's entry
    at = next((a for a, n in poly_free_runs(rs) if n >= len(blob)), None)
    if at is None:
        raise PatchError("no polygon ROM left for the HUD map outline")
    return write_polygons(rs, blob, at), host_tex + 1, layout.record_count


def build_all(rs: RomSet, saturn_cue: Path, plans: list[CoursePlan] = COURSES) -> tuple[RomSet, list[Converted]]:
    """Convert every planned course into `rs` in order, the k-th behind tile table k. PatchError (naming the
    course) when one does not fit its bank or the TGP budget."""
    out, converted = rs, []
    for k, p in enumerate(plans):
        sat = load_saturn_course(saturn_cue, p.path)
        out, c = convert_course(out, sat, p.name, p.bank, p.tgp_slot, p.template, tile_table_address(k), label=p.label,
                                min_coverage=p.min_coverage, thin=p.thin, terrain_thin=p.terrain_thin, race_blob=race_blob_address(k), laps=p.laps,
                                time_factor=p.time_factor, pace=p.pace, spawn_list=spawn_list_address(k), banking=p.banking, camber=p.camber,
                            backdrop=p.backdrop, saturn_cue=saturn_cue, lane_points=p.lane_points, flag_start=p.flag_start)
        converted.append(c)
    return out, converted


def with_spawn(d: Directory, lay: dict[str, int]) -> Directory:
    """Entries with spawn_table 0 get the directory's empty spawn list."""
    from dataclasses import replace
    return [replace(e, spawn_table=lay["spawn"]) if e.spawn_table == 0 else e for e in d]


def report_lines(before: int, after: int, converted: list[Converted], plans: list[CoursePlan] = COURSES,
                 poly_left: int | None = None) -> list[str]:
    """The build report: the TGP budget and one line per converted course (bank, header, TGP slot, tile table, lap
    length, scenery, race blob knobs, spawn list, coverage fill) — what `spike/ten_course_build.py` prints."""
    lines = [f"TGP budget: {before} words free before, {after} after" + ("" if poly_left is None else f"; polygon ROM left {poly_left} bytes")]
    for k, (plan, c) in enumerate(zip(plans, converted)):
        e = c.entry
        lines.append(f"entry {3 + k} {e.name}: bank {e.bank}, header {e.header_base:#x}, TGP slot {e.tgp_slot}, tile table {e.tile_table:#x}, "
                     f"lap {c.lap.length:.0f} units, scenery {c.report['quads']} quads in {c.report['cells']} cells ({c.report['polygon_bytes']} bytes; layers g0-g4, "
                     f"terrain thinned {c.report.get('terrain_thinned', 0)} (terrain_thin {plan.terrain_thin})), "
                     f"thinned {c.report['thinned']} (thin {plan.thin}), "
                     f"race blob {e.race:#x} (laps {e.laps}, time x{plan.time_factor}, pace x{plan.pace}, banking {plan.banking}), spawn list {e.spawn_table:#x}, "
                     f"coverage {c.report.get('coverage')}, HUD map {'shifted right (anticlockwise)' if c.report.get('map_shift') else 'as the game draws it'}, "
                     f"off-course limit {e.off_course} frames")
    return lines


def check_backdrop_markers(data: bytes, headers: list[tuple[int, int]]) -> None:
    """PatchError when another data bank holds, at a converted course's header address, a pointer just after a GFX_MAGIC:
    the boot routine `gfx` (directory.py) would take that bank's data for a backdrop directory while it is mapped."""
    for bank, header in headers:
        for other in range(len(data) // BANK_SIZE):
            if other == bank:
                continue
            base = other * BANK_SIZE - WINDOW
            v = struct.unpack_from("<I", data, base + header)[0]
            if WINDOW + 4 <= v < WINDOW + BANK_SIZE and struct.unpack_from("<I", data, base + v - 4)[0] == GFX_MAGIC:
                raise PatchError(f"bank {other} holds a GFX_MAGIC before {v:#x}, the word at bank {bank}'s header {header:#x}")


def ten_course_set(rs: RomSet, converted: list[Converted], placeholder: Converted | None = None,
                   panels: bool = True) -> RomSet:
    """The directory for the three originals followed by `converted` (in order); remaining entries up to ten
    repeat `placeholder` (or the last converted course) under the remaining Saturn names. With `panels`, every
    non-original entry gets a generated select panel (its course outline and name on the host's frame). The attract
    logo gets its "Extended" (title.py)."""
    from dataclasses import replace
    entries = [c.entry for c in converted]
    outlines = [c.centreline for c in converted]
    names = [n for n in SATURN_NAMES.values() if n not in {e.name for e in ORIGINALS + entries}]
    filler = placeholder or converted[-1]
    while len(entries) < 7:
        entries.append(replace(filler.entry, name=names.pop(0)))
        outlines.append(filler.centreline)
    out = rs
    if panels:
        pool = free_chars(rs)
        rendered = [render_panel(rs, pool, o, e.name, HOST_OF_BANK[e.bank]) for e, o in zip(entries, outlines)]
        out, addrs = install_panels(rs, rendered)
        entries = [replace(e, panel_map=a, panel_b=b, art=HOST_OF_BANK[e.bank]) for e, (a, b) in zip(entries, addrs)]
    originals = list(ORIGINALS)
    bases = [c.picture for c in converted] + [filler.picture] * (len(entries) - len(converted))
    if panels and all(b is not None for b in bases):                # Phase 21: every entry's picture record
        out, records = install_pictures(out, [e.name for e in entries], bases)
        originals = [replace(e, picture=r) for e, r in zip(originals, records)]
        entries = [replace(e, picture=r) for e, r in zip(entries, records[3:])]
    lay = directory_layout()
    check_backdrop_markers(out.data, [(e.bank, e.header_base) for e in entries if e.bank is not None])
    return install_title(install_directory(out, with_spawn(originals + entries, lay)))   # the attract logo's "Extended"


def install_pictures(rs: RomSet, names: list[str], bases: list) -> tuple[RomSet, list[int]]:
    """Phase 21: the seven entries' pictures (`bases` lettered with `names`, quantised), the originals' maps and the ten
    picture records, placed in free runs of bank 0 and the program ROM (outside the directory's code area). Returns the
    new RomSet and the ten record addresses (the three originals first)."""
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    masks = letters(rs)
    runs = [list(r) for r in free_runs(rs, [(CODE_FREE[0], directory_layout()["end"] - CODE_FREE[0])])]

    def place(blob_of, size: int) -> int:
        for r in runs:
            at = (r[0] + 15) // 16 * 16
            if at + size <= r[0] + r[1]:
                blob = blob_of(at)
                assert len(blob) == size
                if at < 0x200000:
                    write_data(out, at - 0x100000, blob)
                else:
                    write_program_blob(out, at, blob)
                r[1] -= at + size - r[0]; r[0] = at + size
                return at
        raise PatchError(f"no free run of {size} bytes for a select picture (runs left: {[(hex(a), n) for a, n in runs][:6]})")
    records = []
    for art in range(3):
        local = original_map(rs, art)
        at = place(lambda a: struct.pack("<336H", *local), 672)
        records.append(original_record(out, art, at))
    for name, base in zip(names, bases):
        p = quantise(with_name(base, name, masks))
        size = len(picture_blob(p, 0)[0])
        holder = {}
        def blob_of(a, p=p):
            holder["blob"], holder["rec"] = picture_blob(p, a)
            return holder["blob"]
        place(blob_of, size)
        records.append(holder["rec"])
    table = place(lambda a: b"".join(encode_record(r) for r in records), RECORD_BYTES * len(records))
    return out, [table + RECORD_BYTES * k for k in range(len(records))]
