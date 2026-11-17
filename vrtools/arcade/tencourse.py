"""Assemble the ten-course set: the three originals plus converted courses as relocatable blobs (Phase 7, M4).

A converted course goes through the Phase 6 pipeline (placement at the arcade grid, lap, heights, collision,
road tables, scenery) and is installed as: a blob in the free space of its host bank (`arcade.blob`), its
collision in a free TGP slot (`patch.install_collision`), its scenery in polygon ROM behind a new tile table in
free program ROM (`patch.write_tile_table`), and a directory entry (`arcade.directory`).
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
from dataclasses import dataclass
from typing import NamedTuple
from pathlib import Path

from vrtools.arcade.lettering import letters
from vrtools.arcade.picture import RECORD_BYTES, encode_record, free_runs, original_map, original_record, picture_blob, quantise
from vrtools.arcade.backdrop import GFX_MAGIC, ArcadePanorama, encode_panorama, read_panorama
from vrtools.arcade.blob import build_course_blob, build_variant_blob, place_blob
from vrtools.arcade.course import BANK_SIZE, CODE_FREE, COURSE_BANK, WINDOW, course_entry_at, decode_pointer_block, road_centreline, road_lines
from vrtools.arcade.course import segments as segments_of
from vrtools.arcade.directory import (LOAD_SIZE, ORIGINALS, CourseEntry10, Directory, ReverseRecord, decode_directory, directory_layout,
                                      install_directory, maps_offset)
from vrtools.arcade.panel import free_chars, install_panels, render_panel
from vrtools.arcade.race import LEVELS, RACE_BLOB_BYTES, VARIANTS, CarEntry, RaceBlob, car_table, encode_race_blob, time_record
from vrtools.arcade.race import checkpoints as checkpoints_at
from vrtools.arcade.patch import (TILE_TABLE_BYTES, PatchError, copro_free_runs, install_collision, patch_course_tiles, poly_free_runs, write_data, write_program_blob,
                                  write_tile_table)
from vrtools.arcade.romset import V60_PROGRAM, RomSet
from vrtools.arcade.spawn import SPAWN_LIST_BYTES, decode_spawn_list, encode_spawn_list, replace_entities
from vrtools.arcade.title import install_title
from vrtools.convert.backdrop import CODE_LIMIT, TOP_CODE, convert_panorama
from vrtools.convert.collision import saturn_collision
from vrtools.convert.geometry import OUTSIDE_MAP_MAX, ConvertError, convert_tiles, placed
from vrtools.convert.silhouette import FarCopy
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
from vrtools.convert.props import BIG_FOREST_TREE, CourseProp, Planting, planting_xz, prop_from_cell, prop_from_course
from vrtools.convert.gates import GATE_GROUP, hide_unused_gates, saturn_gates
from vrtools.convert.race import car_table_for, check_laps, checkpoints_for, gate_checkpoints, lap_total, time_records_for
from vrtools.convert.reverse import reverse_checkpoints, reverse_original, reverse_pit, reverse_points, reverse_tables
from vrtools.convert.road import RoadTables, attitude_words, heading_word, road_tables, tunnel_quads, with_tunnel_flags
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
    reverse: bool = False         # Phase 26: the entry carries a reverse variant built from the same conversion (design §6.3);
                                  # stage 2: on all seven (design §6.7)
    reverse_pairs: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7)   # Phase 26 stage 2 (plan D2): pair k of the variant's pointer block names
                                  # line reverse_pairs[k]; each distinct line is stored once (build_variant_blob)
    reverse_grid: tuple[int, ...] | None = None   # Phase 26 stage 2, after the owner's drive: car k of the variant's car table starts on
                                  # road point reverse_grid[k] (None: the normal table's points); see BANK_ONE_GRID
    props: tuple = ()             # Phase 29: ((props.PropSource or, Phase 34, props.CourseProp, (props.Planting, ...)), ...):
                                  # copies of an arcade prop baked into the scenery cells (drawn only; the collision never sees them)
    tunnels: tuple = ()           # Phase 37 (prototype): ((first, last), ...) road points whose tarmac quads carry the arcade's tunnel
                                  # flag (road.FLAG_TUNNEL: the player's engine sounds as in Bay Bridge's tunnel), in the normal and
                                  # the reverse array; only the stretches Pascal named, each tied to the drawn roof by a test
    far_copies: tuple = ()        # Phase 31 (prototype): silhouette.FarCopy's, a far landmark's tall faces copied into nearer cells
                                  # (drawn from further away); installed by ten_course_set after everything else, on erased ROM


BANK_ONE_PAIRS = (0, 7, 7, 5, 5, 5, 5, 7)   # Phase 26 stage 2 (plan D2, recon §2): the centreline for the player, -5 for cars 1-4 and
                                            # 13-15, +5 for cars 5-12. Bank 1's one free run holds three stored lines on each of its four
                                            # courses (99 888 bytes, 13 488 left), not eight (227 888); of the two trios raced, centre/-5/+5
                                            # jolted least (Pacific 95 against 106 with eight lines, Surfers Road 73 against 85)

# Phase 26 stage 2, after the owner's drive (Surfers Road reverse: "lot of opponent crashes between each other right at the start";
# investigation out/p26/stage2/surfers/report.md). The reverse grid puts the player on road point 0 and car k on point k (the normal
# car table's points), so where a variant's pairs put several cars on one stored line they stand 10 units nose to tail on it. On the
# standing grid the game's "car directly behind" avoidance (contact B, boot 0xfeca95: the ranking neighbour behind within 10 units)
# then turns the follower at once towards a corner of the quad its line point's link word names; those corners are authored for the
# forward direction, so in reverse they lie behind or beside the car, at several bank-1 grid points on pit-lane quads beyond the
# pit wall: six cars started turned 52-68 degrees on Surfers Road. The measured remedy ("grid_alt", report §5) on the courses whose
# pairs are BANK_ONE_PAIRS: the eight cars of the +5 line (cars 5-12, pairs 3-6) take the odd points 1, 3, ..., 15 and the seven of
# the -5 line (cars 1-4 and 13-15, pairs 1, 2 and 7) the even points 2, 4, ..., 14, so cars of one line stand 20 units apart with a
# car of the other line between: no car turned on the four grids, no car off at the start but Pacific Coast's one cutting its first
# bend (stage 2 findings §11.5). It is that measured arrangement,
# not a rule for other pairs; lines, the player's start (point 0, line 0) and the rest of the car table stay the normal table's.
BANK_ONE_GRID = (0,                              # the player
                 2, 4, 6, 8,                     # cars 1-4: -5 line
                 1, 3, 5, 7, 9, 11, 13, 15,      # cars 5-12: +5 line
                 10, 12, 14)                     # cars 13-15: -5 line

# Phase 26 stage 2, after the owner's drive (Metropolis reverse: "quite a few oponent crashes by themselves"; report §7): the cars
# of the two outermost lines, -8 (pair 1, cars 1-2) and +8 (pair 4, cars 7-8), cut the inside of bends onto the grass; on the ±5
# lines (pairs 7 and 5) instead the jolts fell 26 -> 8 in the measured race, 15 of 15 racing. Six lines stored, not eight; the grid
# is the normal table's (as measured).
METROPOLIS_PAIRS = (0, 7, 2, 3, 5, 5, 6, 7)

# Phase 29 (docs/spike/2026-11-phase29-alpine-trees-findings.md): Big Forest's tree on Alpine
# along road points 400-449, the recon's lightest stretch, only where the Saturn draws ground beyond the walls that `props.plant`
# accepts. Points 410-438 have none on either side (the road runs on a causeway over the backdrop's fill; the Saturn's own giant pines
# there stand 25 units below the road over nothing), and the hillsides right of 400-418 are too steep: the trees stand on the snow
# crests left of 406-408 and 439-449 (about 25 units above the road) and on the flat ground right of 448-449 (at the road's height or
# 6-12 below it). Chosen by out/p29's picker (seed 38): every site 2.5 units along and 1 unit across that `props.plant` accepts,
# visited in a random order biased towards the road, each kept when it stands a random 7.5-12 units (Big Forest's own trees: nearest
# neighbour p5 7.4, median 9.3) from every tree kept before; headings random in 5-degree steps (seed 2029).
ALPINE_TREES = (
    Planting(406, -39.0, 315.0, along=0.0), Planting(408, -37.0, 305.0, along=0.0), Planting(439, -68.0, 110.0, along=7.5),
    Planting(440, -75.0, 110.0, along=0.0), Planting(440, -59.0, 260.0, along=0.0), Planting(440, -50.0, 330.0, along=7.5),
    Planting(446, -41.0, 335.0, along=7.5), Planting(447, -56.0, 85.0, along=5.0), Planting(447, -45.0, 180.0, along=7.5),
    Planting(448, -66.0, 200.0, along=2.5), Planting(448, -73.0, 335.0, along=7.5), Planting(448, 57.0, 255.0, along=7.5),
    Planting(448, 68.0, 295.0, along=7.5), Planting(448, 79.0, 250.0, along=7.5), Planting(449, 62.0, 315.0, along=0.0),
    Planting(449, -67.0, 340.0, along=2.5), Planting(449, 52.0, 140.0, along=2.5), Planting(449, -58.0, 160.0, along=5.0),
    Planting(449, 70.0, 15.0, along=5.0), Planting(449, 79.0, 325.0, along=5.0), Planting(449, 44.0, 60.0, along=7.5),
)

# Phase 34 (Pascal, 16 Nov, after one 28-s run of the set out/p34play3: "those ones are great keep saturn"; a keep, not the word to merge;
# docs/spike/2026-11-phase34-surfers-palms-findings.md): 13 more of Surfers Road's own palms. The prop is the Saturn course's own
# roadside palm, the one right of road point 47 (SURFERS_ROAD_PALM: 28 faces with its coconuts, 11.4 units tall, reaching 5.2), its
# geometry and colours as this course already converts them; nothing is borrowed from an arcade course. The copies stand along road
# points 25-99, all to the right of travel (the inside of the long bend), 10.8-13.6 units beyond the last collision quad: three on
# the sand slope at 25-28, two on the sand at 75-77 and a row of eight on the grass at 82-93, 12.5-22.8 units apart. Not planted:
# the left of 25-29 (the sea: `props.is_water`), the left of 30-68 (nothing drawn beyond the bank), the right of 39-64 (the hill is
# steeper than 25 degrees), the banks 20-30 units above the road. Headings random in 5-degree steps (out/p34's picker, seed 34).
# Tried at these sites and not kept (stills out/p34/look/, out/p34/look/v2/; the code is in the branch's history): Bay Bridge's
# small palm at the arcade's size (3.67 units; Pascal: "bigger palms would look better") and scaled 3.0 (they chose "Arcade x3" from
# stills, drove it, asked "can we try with the saturn ones", drove those and kept them).
SURFERS_PALMS = (
    Planting(25, 35.0, 335.0, along=2.5), Planting(27, 34.0, 225.0, along=0.0), Planting(28, 36.0, 15.0, along=7.5),
    Planting(75, 33.0, 145.0, along=0.0), Planting(77, 34.0, 15.0, along=2.5),
    Planting(82, 33.0, 245.0, along=0.0), Planting(83, 34.0, 230.0, along=2.5), Planting(85, 33.0, 40.0, along=0.0),
    Planting(86, 35.0, 270.0, along=2.5), Planting(88, 33.0, 195.0, along=5.0), Planting(90, 34.0, 215.0, along=0.0),
    Planting(91, 33.0, 60.0, along=7.5), Planting(93, 35.0, 325.0, along=2.5),
)

SURFERS_ROAD_PALM = CourseProp(Planting(47, 7.2, 0.0, along=1.4), radius=6.0, faces=28)


# Phase 31 (a prototype; Pascal after one 107-s run of it, 15 Nov: "yes it s good keep it"; the Phase 28 recon's candidate 5). One place: the far end of Metropolis's
# long straight (road points 53-106, driven towards +z in the normal direction), whose buildings are binned in cells 215 and
# 216 (row 13), so the game draws them only once the camera is in row 11:
# - the low banded building across the end of the street (30 faces of cell 215: x -136..-52, z 745..770, up to 59.6): in the
#   normal direction it appears at once at the vanishing point at road points 66-68 (METROPOLIS_FRONT);
# - the tall banded block beside it (15 faces of cells 215 and 216: x -18.6..51.4, z 746.1..781.8, up to 92.4): in reverse it
#   appears ahead of the car on the parallel street (cell 168 to 184); from the straight it is all but hidden (METROPOLIS_BLOCK).
# The same faces in cell 183 (row 11, two rows nearer on the straight) and, the block's, in cell 184 (two rows nearer on the
# parallel street) are drawn from row 9 on. docs/spike/2026-11-phase31-far-silhouette-findings.md.
METROPOLIS_BLOCK = (-19.0, 745.5, 52.0, 782.5)
METROPOLIS_FRONT = (-136.5, 744.5, -52.0, 770.5)
METROPOLIS_FAR = (FarCopy(215, (183,), 15.0, within=METROPOLIS_FRONT, faces=30),          # the counts pin the hand-tuned boxes:
                  FarCopy(215, (183, 184), 20.0, within=METROPOLIS_BLOCK, faces=7),       # another count is a ConvertError
                  FarCopy(216, (183, 184), 20.0, within=METROPOLIS_BLOCK, faces=8))


COURSES: list[CoursePlan] = [
    CoursePlan("ALPINE00/TRCKALPN", "ALPINE", 3, 3, 2, 0, reverse=True, props=((BIG_FOREST_TREE, ALPINE_TREES),),
               tunnels=((108, 146),)),                                           # Phase 37: the mountain tunnel   # Phase 29 prototype
    CoursePlan("AMAZON00/TRCKAMAZ", "AMAZON FALLS", 1, 4, 0, 1, lane_points=((152, 191), (20, 37)), flag_start=0,   # first corner's curbs
               reverse=True, reverse_pairs=BANK_ONE_PAIRS, reverse_grid=BANK_ONE_GRID),                                        # (p22play29: 29-68 from the old start, 207 points
                                                                                                   # before the flag); v0.1.1 (Pascal, rec120): the pit
                                                                                                   # exit, the rock 7-10 out on the right at 26-35
    CoursePlan("DIABLO00/TRCKDIAB", "DIABLO CANYON", 2, 5, 1, 2, reverse=True),
    CoursePlan("METROPOL/TRCKMETR", "METROPOLIS", 2, 6, 1, 1, flag_start=0,   # Phase 22n: the building at the hairpin's inside
               lane_points=((318, 356),), time_factor=1.15, reverse=True,    # Phase 22p: the clock (the autopilot's 150-s race ended with 71                      # (points 318-356 R since the flag start; 22k's 124-140): the lines
                                                                # shift 11 left onto the Saturn's road there and the wall may follow
                                                                # them in to the drawn face (22k's named points trimmed the road under
                                                                # the lines and broke the decks' separation: backstep 116)
               reverse_pairs=METROPOLIS_PAIRS,                  # Phase 26 stage 2, after the owner's drive: the ±8 lines' cars on ±5
               far_copies=METROPOLIS_FAR,                       # Phase 31 (prototype, kept on Pascal's word)
               tunnels=((50, 62), (251, 311))),                 # Phase 37: the roofed road beside the pit lane (the lane's quads
                                                                # under the same roof are credited to the same points), the long tunnel
    CoursePlan("PACCOAST/TRCKPACC", "PACIFIC COAST", 1, 7, 0, 1, time_factor=1.15,   # Phase 22p: the clock (128 units left, every
               reverse=True, reverse_pairs=BANK_ONE_PAIRS, reverse_grid=BANK_ONE_GRID),                       # other course 300-650; Metropolis 71)
    CoursePlan("SPEEDWAY/TRCKSPEE", "SURFERS OVAL", 1, 8, 0, 0, min_coverage=0.8, flag_start=5,   # the file carries an unused infield;
               reverse=True, reverse_pairs=BANK_ONE_PAIRS, reverse_grid=BANK_ONE_GRID),                                       # 22l: at the flag the road reaches 992 of 970 (5: 954; 6-7 re-aim to 1221)
    CoursePlan("SURFER00/TRCKSURF", "SURFERS ROAD", 1, 9, 0, 2, flag_start=6,   # 22l: at the flag the road reaches 992 of 970 (5: 954; 6-7 re-aim to 1221)
               reverse=True, reverse_pairs=BANK_ONE_PAIRS, reverse_grid=BANK_ONE_GRID,
               props=((SURFERS_ROAD_PALM, SURFERS_PALMS),)),                    # Phase 34: more of the course's own palms
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


@dataclass(frozen=True)
class Reversed:
    """Phase 26: a course's reverse variant as the conversion leaves it, installed by `ten_course_set` (`install_reverse`):
    the road tables read backwards (`convert.reverse.reverse_tables`), its race blob (the normal lap's checkpoints numbered
    backwards less any just after the line, `convert.reverse.reverse_checkpoints`, the time records with the normal lap's total, the normal car table,
    on the bank-1 courses with BANK_ONE_GRID's start points since the owner's drive), the reversed lap's
    interior side (the HUD map's shift) and, stage 2 (plan D2), the lines the variant's pointer block names (`pairs`, as
    `build_variant_blob` takes them). Stage 4 (decision L5): the variant's own pit quad and box (`convert.reverse.reverse_pit`,
    the box's heading turned half a turn), both None on a course whose normal entry has no pit stop."""
    tables: RoadTables
    race: RaceBlob
    interior_left: bool
    pairs: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7)
    pit_quad: int | None = None
    pit_box: tuple[float, float, float, int] | None = None


@dataclass
class Converted:
    entry: CourseEntry10
    lap: Lap
    centreline: list[tuple[float, float]]
    report: dict
    picture: object = None               # Phase 21: the select picture without its name (convert/preview.py), uint8 168 x 128 x 3
    reverse: Reversed | None = None      # Phase 26: the reverse variant (CoursePlan.reverse), not yet in the ROM
    far_cells: dict | None = None        # Phase 31 (prototype): {cell: WorldQuads} of the cells that carry a far copy, not yet in the ROM


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


def start_gantry_address(code_base: int = CODE_FREE[0]) -> int:
    """Phase 26 stage 2 (Task 11): program-ROM address of the converted courses' start-gantry block (`gantry.BLOCK_BYTES`: the
    new object list and its records, then its colour run), the top BLOCK_BYTES of the code area. Erased in the original (the
    whole code area is) and above the fixed layout (the directory image, the seven tile tables, race blobs and spawn lists).
    No other writer claims it: the reverse annex's first region ends at it (`annex_regions`) and the select pictures' free-run
    search excludes it (`picture_exclusions`); build_all writes it before either runs. (Measured on the integrated stage-2
    set, out/p26play3: the fixed layout ends 24 468 bytes below it, the pictures 4 032 bytes below it, and the annex lies in
    the colour-table run, not in the code area.)"""
    from vrtools.arcade.gantry import BLOCK_BYTES
    addr = code_base + CODE_FREE[1] - BLOCK_BYTES
    layout_end = spawn_list_address(NEW_COURSES - 1, code_base) + SPAWN_LIST_BYTES(MAX_ENTITIES)
    if addr < layout_end or addr % 16:
        raise PatchError(f"the start gantry's {BLOCK_BYTES}-byte block at {addr:#x} would overlap the fixed layout of the code area "
                         f"(the last spawn list ends at {layout_end:#x})")
    return addr


FAR_COLOUR_BYTES = 256      # Phase 31: the block reserved for the far copies' colour entries (128 entries; Metropolis's take 59)


def far_colour_block(code_base: int = CODE_FREE[0]) -> tuple[int, int]:
    """Phase 31: program-ROM [start, end) reserved for the colour entries of the far copies' objects (`farcopy.colour_run`):
    the FAR_COLOUR_BYTES just below the start gantry's block, at the top of the code area. Erased in the original (the whole
    code area is) and above the fixed layout (the directory image, the seven tile tables, race blobs and spawn-list slots). No
    other writer may take it: the reverse annex's first region ends below it (at its start until Phase 33; since then at the
    originals' blocks stacked under it, `origpic_address`; `annex_regions`), the select pictures' free-run search leaves it out
    (`picture_exclusions`) and no other reserved block overlaps it (`check_reserved_blocks`). (On the Phase 31 set the pictures end 1 952 bytes below the gantry's
    block, so reserving it moved nothing.) Its only reader besides the objects' colour lookups is the boot's colour-table
    upload, which reads the whole program ROM. PatchError when it would overlap the fixed layout."""
    hi = start_gantry_address(code_base)
    lo = hi - FAR_COLOUR_BYTES
    layout_end = spawn_list_address(NEW_COURSES - 1, code_base) + SPAWN_LIST_BYTES(MAX_ENTITIES)
    if lo < layout_end or lo % 16:
        raise PatchError(f"the far copies' {FAR_COLOUR_BYTES}-byte colour block at {lo:#x} would overlap the fixed layout of the "
                         f"code area (the last spawn list ends at {layout_end:#x})")
    return lo, hi


def origrev_address(code_base: int = CODE_FREE[0]) -> int:
    """Phase 33: program-ROM address of the originals' reverse block (`origrev.BLOCK_BYTES`: `hudorig`; Phase 33's `rankgate3` until Phase 35): right
    below the far copies' colour block (Phase 31, `far_colour_block`), which lies right below the start gantry's block, in the
    code area's last free run (what the select pictures leave: 1 952 bytes at 0x28f1d0 before either block). The annex's first
    region ends at it and the pictures' free-run search leaves it out (`annex_regions`, `picture_exclusions`), so no first-fit
    writer lands on it; `origrev.install_origrev` writes it on erased ROM only. PatchError when it would reach down into the
    fixed layout of the code area (the directory image, the tile tables, race blobs and spawn-list slots)."""
    from vrtools.arcade.origrev import BLOCK_BYTES
    addr = far_colour_block(code_base)[0] - BLOCK_BYTES
    layout_end = spawn_list_address(NEW_COURSES - 1, code_base) + SPAWN_LIST_BYTES(MAX_ENTITIES)
    if addr < layout_end or addr % 16:
        raise PatchError(f"the originals' reverse block ({BLOCK_BYTES} bytes) at {addr:#x} would overlap the fixed layout of the code "
                         f"area (the last spawn list ends at {layout_end:#x})")
    return addr


def origpic_address(code_base: int = CODE_FREE[0]) -> int:
    """Phase 33 fix wave: program-ROM address of the originals' picture block (`origpic.BLOCK_BYTES`: `odraw`, `odone`), right
    below the originals' reverse block; the annex's first region ends at it and the pictures' search leaves it out."""
    from vrtools.arcade.origpic import BLOCK_BYTES
    addr = origrev_address(code_base) - BLOCK_BYTES
    layout_end = spawn_list_address(NEW_COURSES - 1, code_base) + SPAWN_LIST_BYTES(MAX_ENTITIES)
    if addr < layout_end or addr % 16:
        raise PatchError(f"the originals' picture block ({BLOCK_BYTES} bytes) at {addr:#x} would overlap the fixed layout of the code "
                         f"area (the last spawn list ends at {layout_end:#x})")
    return addr


BOOT_FREE = (0xFDC848, 0xFE0000)     # Phase 33 fix wave: the boot ROM's erased run 0xfdc845..0xfe0000 (14 267 bytes, erased in the
                                     # original; the code's jump table begins at 0xfe0000), 4-aligned. Nothing of the game's code
                                     # reads it but the test menu's MEMORY TEST, which sums the whole ROM (PC 0xfe0e81)


def install_original_pictures(rs: RomSet, lay: dict[str, int]) -> tuple[list[int], list[int]]:
    """Phase 33 fix waves (review C1, `origpic`): each original's direction-screen picture data. The three LOCK pieces (read
    every logic frame up to the race load) first, in BOOT_FREE, which is always mapped; then the DRAW pieces, first fit in what
    BOOT_FREE has left and then in what is STILL erased of bank 0 or the program ROM (`picture.free_runs` outside
    `picture_exclusions`; bank 0 is mapped while the select screens draw). Called last of all, so nothing else of the set
    moves. Then the code block with the six addresses, and its two places. Returns (the draw addresses, the lock addresses)."""
    from vrtools.arcade.origpic import data_sizes, install_origpic, picture_data
    from vrtools.arcade.romset import V60_BOOT
    runs = [[BOOT_FREE[0], BOOT_FREE[1] - BOOT_FREE[0]]]
    runs += [list(r) for r in free_runs(rs, picture_exclusions() + [(SPAWN_ROOM[0], SPAWN_ROOM[1] - SPAWN_ROOM[0])])]
    arts = range(len(ORIGINALS))
    sizes = [data_sizes(rs, art) for art in arts]

    def place(size: int, pool: list, what: str) -> int:
        for r in pool:
            at = (r[0] + 15) // 16 * 16
            if at + size <= r[0] + r[1]:
                r[1] -= at + size - r[0]; r[0] = at + size
                return at
        raise PatchError(f"no erased run of {size} bytes for {what}")
    lock_at = [place(sizes[art][1], runs[:1], f"original {art}'s lock data in the boot ROM") for art in arts]
    draw_at = [place(sizes[art][0], runs, f"original {art}'s direction-screen picture") for art in arts]
    for art in arts:
        draw, lock, _ = picture_data(rs, art, draw_at[art], lock_at[art])
        for at, blob in ((draw_at[art], draw), (lock_at[art], lock)):
            rom, base = (("boot", V60_BOOT) if at >= V60_BOOT else ("data", 0x100000) if at < 0x200000 else ("program", V60_PROGRAM))
            image = bytearray(getattr(rs, rom))
            if any(x != 0xFF for x in image[at - base:at - base + len(blob)]):
                raise PatchError(f"{rom} ROM at {at:#x} (+{len(blob)}) is not erased for original {art}'s direction-screen picture")
            image[at - base:at - base + len(blob)] = blob
            object.__setattr__(rs, rom, bytes(image))
    install_origpic(rs, origpic_address(), lay, draw_at, lock_at)
    return draw_at, lock_at


def reserved_blocks() -> dict[str, tuple[int, int]]:
    """Phase 33: every reserved [start, end) of the program ROM that the first-fit writers are kept out of, by name: the
    directory image, the originals' reverse block, the far copies' colour block, the start gantry's block, the direction
    screen's block, the originals' reverse spawn lists' run. `check_reserved_blocks` shows that no two overlap."""
    from vrtools.arcade.gantry import BLOCK_BYTES as GANTRY_BYTES
    from vrtools.arcade.origrev import BLOCK_BYTES as ORIGREV_BYTES
    return {"directory image": (CODE_FREE[0], directory_layout()["end"]),
            "originals' reverse block": (origrev_address(), origrev_address() + ORIGREV_BYTES),
            "originals' picture block": (origpic_address(), origrev_address()),
            "far copies' colour block": far_colour_block(),
            "start gantry's block": (start_gantry_address(), start_gantry_address() + GANTRY_BYTES),
            "direction screen's block": dirscreen_block(),
            "originals' reverse spawn lists": SPAWN_ROOM}


def check_reserved_blocks() -> None:
    """PatchError naming the two when two reserved blocks of the program ROM overlap (`reserved_blocks`)."""
    blocks = sorted(reserved_blocks().items(), key=lambda kv: kv[1])
    for (na, (_, ea)), (nb, (sb, _)) in zip(blocks, blocks[1:]):
        if sb < ea:
            raise PatchError(f"the {na} (to {ea:#x}) and the {nb} (from {sb:#x}) overlap in the program ROM")


# Phase 33 stage 1 (a prototype for the owner's drive; Pascal, 15 Nov: "We also need to do the reverse for the three initial
# tracks"): the lines an original's reverse variant stores, by menu entry, as `build_variant_blob`'s pairs. Big Forest and
# Acropolis keep their eight hand-made lines. BAY BRIDGE IS A STOPGAP: data bank 1 has 13 488 bytes free, eight lines need
# 60 048, two 19 152 and one 12 336, so all sixteen cars take the centreline (recon §6.8 and §7 have the options).
#
# Big Forest stores six lines: the cars of lines 5 and 7 (cars 9-10 and 13-15) follow lines 6 and 4. Measured (findings §5): in
# reverse every opponent leaves the left-hander at forward points 126-133 three to five units inside its line, where the tarmac's
# inner edge tapers in (lateral -10.5 at point 129, -5.3 at 126); lines 5 and 7 run nearest that edge (-5.1) and their five cars
# went onto the verge there lap after lap: 14 of the 26 opponent jolts of the race to the time-out (the normal race: 3). On
# lines 6 and 4 (-3.1, -2.3): 9 jolts, none at that bend. The same kind of choice as METROPOLIS_PAIRS, by measurement, not driven.
BIG_FOREST_REVERSE_PAIRS = (0, 1, 2, 3, 4, 6, 6, 4)
ORIGINAL_REVERSE_PAIRS = {0: BIG_FOREST_REVERSE_PAIRS, 1: (0, 0, 0, 0, 0, 0, 0, 0), 2: (0, 1, 2, 3, 4, 5, 6, 7)}
# The originals' reverse grids, by menu entry (car k's start road point; the game's table: car k on point k). Measured (findings
# §5): the game's cars share their lines in twos and threes and stand one point (8-10 units) nose to tail; on the standing grid
# a car directly behind another on its line is turned towards a corner of its line point's quad, which lies behind or beside it
# in reverse (stage 2's finding on bank 1). On the game's grid 3 cars stood turned 25-41 degrees on Big Forest's reverse grid,
# 10 on Acropolis's (11-50) and 10 on Bay Bridge's one line (31-56, seven of them off the tarmac in the first three seconds).
# - Bay Bridge and Acropolis: car k on point 2k, the game's order kept, the grid twice as long (the front car 30 points, about
#   240 units, ahead of the player): no car turned (at most 4.4 degrees). Interleaving Acropolis's lines within fifteen points
#   left 6 cars turned.
# - Big Forest: its reverse road bends from point 24 on, and cars 12-15 put there stood 10-16 degrees off their line with three
#   of them off the tarmac at the start; within the game's fifteen points the lines are interleaved instead (`interleaved_grid`
#   on the stored lines of BIG_FOREST_REVERSE_PAIRS: no two cars of one stored line on neighbouring points; BANK_ONE_GRID's
#   way): no car turned (at most 1.6 degrees). The order at the front becomes cars 12, 15, 11, 14, 10, 13.
def interleaved_grid(stored: tuple[int, ...]) -> tuple[int, ...]:
    """Start points 1..15 for cars 1..15 (the player, car 0, on point 0) such that no two cars on neighbouring points follow
    the same stored line; `stored[k]` is car k's. Of the arrangements, the one whose order of cars from point 1 up comes first
    (lowest car numbers at the back, as the game's grid). PatchError when there is none (one line for every car)."""
    cars = list(range(1, len(stored)))

    def go(seq: list[int], left: list[int]):
        if not left:
            return seq
        for c in left:
            if not seq or stored[c] != stored[seq[-1]]:
                found = go(seq + [c], [x for x in left if x != c])
                if found:
                    return found
        return None
    seq = go([], cars)
    if seq is None:
        raise PatchError(f"no grid keeps the cars of one stored line apart: {stored}")
    grid = [0] * len(stored)
    for point, car in enumerate(seq, 1):
        grid[car] = point
    return tuple(grid)


GAME_CAR_LINES = (0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 7)     # the game's car table: car k's road line (boot 0xfcd395)
SPACED_GRID = tuple(2 * k for k in range(16))
ORIGINAL_REVERSE_GRID = {0: interleaved_grid(tuple(BIG_FOREST_REVERSE_PAIRS[l] for l in GAME_CAR_LINES)), 1: SPACED_GRID, 2: SPACED_GRID}
SPAWN_ROOM = (0x2FCE00, 0x300000)   # Phase 33: the erased run that ends the program ROM (12 800 bytes), for the originals' reverse
                                    # spawn lists. Its only reader is the boot's colour-table upload (PC 0xfe6b64, each halfword once
                                    # before the first picture: read taps over a reverse Big Forest and a normal Bay Bridge race,
                                    # findings §2); no record reads a colour entry inside it (tests/test_originals_reverse.py).
SPAWN_MARGIN = 16


def reverse_spawn_list(rs: RomSet, entry: int, gantry_list: int | None, checkpoint_lists: dict[int, int] | None = None) -> list:
    """Phase 33 (Pascal, 15 Nov: "Yes all your recommendation", C3 and C4): original `entry`'s entities for its reverse race: its
    own spawn list less the arrow boards (`spawn.ARROW_BOARD`: one-sided, and they announce the forward bend), and its start
    gantry drawing the converted courses' both-sided frames (`gantry_list`, `start_gantry_address()`: START reads from behind;
    None when the set has no such list: the game's frames stay). Stage 2 (Pascal, 16 Nov: "some checkpoint flags are white
    without the C.P."): each checkpoint gantry draws the list `checkpoint_lists` gives for its own (the arcade's frames with
    their lettering mirrored behind the banner, `gantry.install_checkpoint_lettering`). Everything else as the game placed it,
    in the game's order."""
    from dataclasses import replace
    from vrtools.arcade.spawn import ARROW_BOARD, CHECKPOINT_GANTRIES, START_GANTRY
    out = []
    for e in decode_spawn_list(rs, ORIGINALS[entry].spawn_table):
        if e.handler == ARROW_BOARD:
            continue
        if e.handler == START_GANTRY and gantry_list is not None:
            e = replace(e, objlist=gantry_list)
        elif e.handler in CHECKPOINT_GANTRIES and checkpoint_lists and e.objlist in checkpoint_lists:
            e = replace(e, objlist=checkpoint_lists[e.objlist])
        out.append(e)
    return out


def checkpoint_lists(rs: RomSet, originals: list[CourseEntry10]) -> dict[int, int]:
    """Stage 2: {the game's checkpoint object list: the address of its lettered list} for every object list a checkpoint gantry
    of an original with a variant names: `gantry.CHECKPOINT_LIST_BYTES` each from SPAWN_ROOM's start, in the order of the
    game's lists' addresses. PatchError when they do not fit the room."""
    from vrtools.arcade.gantry import CHECKPOINT_LIST_BYTES
    from vrtools.arcade.spawn import CHECKPOINT_GANTRIES
    lo, hi = SPAWN_ROOM
    wanted = sorted({e.objlist for k, o in enumerate(originals) if o.reverse is not None
                     for e in decode_spawn_list(rs, ORIGINALS[k].spawn_table) if e.handler in CHECKPOINT_GANTRIES})
    if lo + SPAWN_MARGIN + CHECKPOINT_LIST_BYTES * len(wanted) + SPAWN_MARGIN > hi:
        raise PatchError(f"{len(wanted)} checkpoint gantry lists do not fit {lo:#x}..{hi:#x}")
    return {o: lo + SPAWN_MARGIN + CHECKPOINT_LIST_BYTES * k for k, o in enumerate(wanted)}


def install_checkpoint_lists(rs: RomSet, originals: list[CourseEntry10]) -> None:
    """Stage 2: the lettered checkpoint lists at `checkpoint_lists`' addresses (in place; `gantry.install_checkpoint_lettering`:
    their lettering objects first-fit in free polygon ROM). Called AFTER every other writer of the polygon ROM (the far copies,
    Phase 31), so that everything else of the set lies where it lies without them. PatchError when less than POLY_FLOOR_BYTES
    of polygon ROM would stay free."""
    from vrtools.arcade.gantry import install_checkpoint_lettering
    for objects, addr in checkpoint_lists(rs, originals).items():
        install_checkpoint_lettering(rs, addr, objects)
    if poly_budget(rs) < POLY_FLOOR_BYTES:
        raise PatchError(f"the checkpoint gantries' lettering leaves less than {POLY_FLOOR_BYTES} bytes of polygon ROM free")


def install_reverse_spawn_lists(rs: RomSet, originals: list[CourseEntry10]) -> list[CourseEntry10]:
    """The three originals' reverse spawn lists (`reverse_spawn_list`) in SPAWN_ROOM (in place, on erased ROM only): the room's
    start is kept for the checkpoint gantries' lettered lists (stage 2, `checkpoint_lists`: the spawn records name them here,
    `install_checkpoint_lists` writes them last of all), then one spawn list a course (all its entities behind slot 0, as the
    converted courses' lists are: the loader creates every record whatever its slot); and `originals` with each variant's
    `spawn_table` naming its list. The normal entries and the game's own lists are not touched. PatchError when the room is not
    erased or too small."""
    from dataclasses import replace
    from vrtools.arcade.gantry import CHECKPOINT_LIST_BYTES, START_GANTRY_OBJECTS
    at = start_gantry_address()
    have = struct.unpack_from("<I", rs.program, at - V60_PROGRAM)[0]
    gantry = at if have != 0xFFFFFFFF else None                   # the both-sided frames' list, when build_all installed it
    lo, hi = SPAWN_ROOM
    if any(x != 0xFF for x in rs.program[lo - V60_PROGRAM:hi - V60_PROGRAM]):
        raise PatchError(f"program ROM {lo:#x}..{hi:#x} is not erased for the originals' reverse spawn lists")
    lettered = checkpoint_lists(rs, originals)
    addr = lo + SPAWN_MARGIN + CHECKPOINT_LIST_BYTES * len(lettered)
    out = []
    for k, o in enumerate(originals):
        if o.reverse is None:
            out.append(o)
            continue
        ents = reverse_spawn_list(rs, k, gantry, lettered)
        blob = encode_spawn_list(ents, addr)
        if addr + len(blob) + SPAWN_MARGIN > hi:
            raise PatchError(f"{o.name}: its reverse spawn list ({len(blob)} bytes) does not fit {lo:#x}..{hi:#x}")
        write_program_blob(rs, addr, blob)
        out.append(replace(o, reverse=ReverseRecord(o.reverse.at, replace(o.reverse.entry, spawn_table=addr))))
        addr = (addr + len(blob) + 15) // 16 * 16
    assert START_GANTRY_OBJECTS != at
    return out


# Phase 33 stage 2 (Pascal, 16 Nov, after driving the stage 1 set: "the pit isnt working"): the pit stop in a reverse race on
# an original, by Phase 26 stage 4's scheme for the seven: the reverse car meets the normal pit EXIT first, enters the lane
# there and the game's own pit sequence takes it up the lane to the box, parks it facing the reverse way, and it leaves by the
# normal mouth. The variant's record carries a pit quad q (the game starts a stop when the car's lap-position quad is q or
# q + 1 and it heads along the quad's direction, turned half a turn in reverse) and the box with its heading turned.
PIT_BOX_TABLES = {1: 0xFF40B1, 2: 0xFF40D9}     # boot ROM, by template: the game's pit box x, y, z (Acropolis, Big Forest; `course.PIT_POSE`)
FLAG_PIT_LANE = 66                               # the segment flag of the originals' pit-lane quads
ORIGINAL_PIT_MIN_RUN = 64.0                      # stage 4's L3: the straight run from the pair to the box, at least


def original_reverse_pit(rs: RomSet, entry: int) -> tuple[int, tuple[float, float, float, int]] | None:
    """Original `entry`'s reverse pit quad and box, or None when the course has no pit lane (Bay Bridge). The lane's quads are
    the game's own (segments flagged 66); beside the start straight they are one quad the lane's width for each road point, in
    lap order from the normal pit quad (`ORIGINALS[entry].pit_quad`, the lane's first quad at the line) to the normal exit. The
    reverse pair is the last two of that run, the pit quad the first of the two: the two lane quads a reverse car meets first.
    The box is the game's own (PIT_BOX_TABLES), its heading the lane's direction turned half a turn (the lane's heading taken
    from the run's straight middle). PatchError when the pair lies less than ORIGINAL_PIT_MIN_RUN from the box (stage 4's
    rule: nearer, the car circled the box) or the run is not a lane."""
    e = ORIGINALS[entry]
    if e.pit_quad is None:
        return None
    from vrtools.arcade.tgp import SLOT_OF_COURSE, decode_collision
    normal = course_entry_at(rs, e.bank, e.header_base)
    segs = segments_of(rs, normal)
    run = []
    k = e.pit_quad
    while k < len(segs) and segs[k].flag == FLAG_PIT_LANE:
        run.append(k)
        k += 1
    if len(run) < 4:
        raise PatchError(f"{e.name}: {len(run)} pit-lane quads from quad {e.pit_quad}")
    quads = decode_collision(rs, entry).quads
    centre = lambda q: (sum(c[0] for c in quads[q].corners) / 4, sum(c[2] for c in quads[q].corners) / 4)
    (x0, z0), (x1, z1) = centre(run[len(run) // 4]), centre(run[3 * len(run) // 4])    # the lane's straight middle (its ends taper)
    forward = int(round(-math.atan2(x1 - x0, z1 - z0) / (2 * math.pi) * 65536)) % 65536      # the lane's heading, as a box's
    bx, by, bz = struct.unpack_from("<3f", rs.boot, PIT_BOX_TABLES[e.template] - 0xFC0000)
    q = run[-2]
    near = min(math.dist(centre(i), (bx, bz)) for i in (q, q + 1))
    if near < ORIGINAL_PIT_MIN_RUN:
        raise PatchError(f"{e.name}: the reverse pit pair {q}, {q + 1} lies {near:.0f} units from the box, under {ORIGINAL_PIT_MIN_RUN:.0f}")
    return q, (bx, by, bz, (forward + 0x8000) % 0x10000)


ORIGINAL_MIN_RUN = 4096     # the shortest free run an original's variant may take in its bank (`blob.MIN_FREE_RUN` is 32 768)

# Phase 33 second fix wave (Pascal, 16 Nov, Bay Bridge in reverse, having left the road on the fork's side arm: "it did put me back
# on bay bridge after a while but i ended up right in an obstacle."). The game's off-course put-back (0xfebc94) sets the car
# down on the CENTRE of the last quad it remembered and along that quad's direction (turned half round in a reverse race); it
# remembers a quad while all four wheels are on tarmac and the quad's segment flag has none of the bits 0x3c. In reverse the
# last quad before Bay Bridge's fork (660) is remembered while the car leaves onto the side arm, and its centre faces the nose
# of the fork's divider four units ahead. The reverse variant's own segment array marks such quads with FLAG_NO_PUTBACK: they
# are not remembered, the car is set down on an earlier quad, and while it is on them the off-course counter runs (it is
# cleared on the next quad). Bit 2 of the flag has no other reader (0xfebcbc's mask is the only test of bits 2-5).
FLAG_NO_PUTBACK = 4
PUTBACK_CLEAR = 25.0        # units of tarmac or kerb a put-back pose must have straight ahead of it in reverse
PUTBACK_HALF_WIDTH = 1.2    # the pose is probed on three lines: its axis and this far to each side
PUTBACK_REACH = 60.0        # the probe's length (the distance reported when nothing blocks it)
SURFACE_WALL_KIND = 5       # tgp.SURFACE_WALL: a quad whose surface byte's low nibble is 5 is a wall
DRIVABLE_KINDS = (1, 8)     # tarmac, kerb


def putback_clear(rs: RomSet, entry: int, reverse: bool) -> dict[int, float]:
    """Original `entry`'s put-back spots (the quads of its segments whose flag has none of the bits 0x3c: the game's own rule,
    0xfebcbf; the racing road's, and also the pit lanes' 0x42 and Bay Bridge's 0x02) ->
    how far straight ahead of the put-back pose (the quad's centre, its direction, turned half round with `reverse`) the
    first point lies that is on a wall quad with no tarmac or kerb quad under it, or on no quad at all; PUTBACK_REACH when
    there is none within it. Read from the stock collision and surface table (`rs` may be any set: the originals' are not
    written)."""
    from vrtools.arcade.course import surface_table
    from vrtools.arcade.tgp import decode_collision
    e = ORIGINALS[entry]
    ce = course_entry_at(rs, e.bank, e.header_base)
    quads = decode_collision(rs, entry).quads
    surf = surface_table(rs, ce, len(quads))
    boxes = [(k, min(c[0] for c in q.corners), max(c[0] for c in q.corners), min(c[2] for c in q.corners), max(c[2] for c in q.corners))
             for k, q in enumerate(quads)]
    grid: dict[tuple[int, int], list] = {}
    for b in boxes:
        for gx in range(int(b[1] // 16), int(b[2] // 16) + 1):
            for gz in range(int(b[3] // 16), int(b[4] // 16) + 1):
                grid.setdefault((gx, gz), []).append(b)

    def inside(q, x: float, z: float) -> bool:
        sign = 0
        for i in range(4):
            (x0, _, z0), (x1, _, z1) = q.corners[i], q.corners[(i + 1) % 4]
            cross = (x1 - x0) * (z - z0) - (z1 - z0) * (x - x0)
            if abs(cross) < 1e-9:
                continue
            if sign == 0:
                sign = 1 if cross > 0 else -1
            elif (cross > 0) != (sign > 0):
                return False
        return True

    def drivable(x: float, z: float) -> bool:
        kinds = [surf[b[0]] & 15 for b in grid.get((int(x // 16), int(z // 16)), ())
                 if b[1] <= x <= b[2] and b[3] <= z <= b[4] and inside(quads[b[0]], x, z)]
        return bool(kinds) and (any(k in DRIVABLE_KINDS for k in kinds) or SURFACE_WALL_KIND not in kinds)
    out = {}
    for s in segments_of(rs, ce):
        if s.flag & 0x3C or s.index >= len(quads):
            continue
        q = quads[s.index]
        a = (((q.attr & 0xFFFF) + (0x8000 if reverse else 0)) & 0xFFFF) / 65536 * 2 * math.pi
        fx, fz = -math.sin(a), math.cos(a)                          # yaw 0 is +z; forward is (-sin, cos)
        clear = PUTBACK_REACH
        for step in range(10, int(PUTBACK_REACH * 10), 10):
            d = step / 10
            if not all(drivable(q.centre[0] + fx * d - fz * w, q.centre[2] + fz * d + fx * w) for w in (-PUTBACK_HALF_WIDTH, 0.0, PUTBACK_HALF_WIDTH)):
                clear = d
                break
        out[s.index] = clear
    return out


PUTBACK_OBJECT_CLEAR = 2.5  # units between a pose's first PUTBACK_CLEAR units and a spawned object


def putback_objects(rs: RomSet, entry: int, reverse: bool) -> dict[int, tuple[float, float]]:
    """Original `entry`'s put-back spots whose pose has an object of the course's spawn list within PUTBACK_OBJECT_CLEAR of
    its first PUTBACK_CLEAR units -> that object's (x, z). The start and checkpoint gantries (overhead), the arrow boards (not
    in a reverse race) and the list's entities at the origin (the HUD map) are left out. (Bay Bridge: the row of eight boards
    that closes the stub at forward road points 361-368 ends on quad 509's centre.)"""
    from vrtools.arcade.spawn import ARROW_BOARD, CHECKPOINT_GANTRIES, START_GANTRY
    from vrtools.arcade.tgp import decode_collision
    e = ORIGINALS[entry]
    quads = decode_collision(rs, entry).quads
    objects = [(x.x, x.z) for x in decode_spawn_list(rs, e.spawn_table)
               if x.handler not in (START_GANTRY, ARROW_BOARD, *CHECKPOINT_GANTRIES) and (x.x, x.z) != (0.0, 0.0)]
    out = {}
    for k in putback_clear(rs, entry, reverse):
        q = quads[k]
        a = (((q.attr & 0xFFFF) + (0x8000 if reverse else 0)) & 0xFFFF) / 65536 * 2 * math.pi
        fx, fz = -math.sin(a), math.cos(a)
        for ox, oz in objects:
            along = (ox - q.centre[0]) * fx + (oz - q.centre[2]) * fz
            aside = abs((ox - q.centre[0]) * -fz + (oz - q.centre[2]) * fx)
            if -PUTBACK_OBJECT_CLEAR <= along <= PUTBACK_CLEAR and aside < PUTBACK_OBJECT_CLEAR:
                out[k] = (ox, oz)
                break
    return out


def mark_no_putback(segments: list, marked) -> list:
    """`segments` with FLAG_NO_PUTBACK set on those whose quad is in `marked`; every other bit of a flag kept (a tunnel
    quad's 0x80, a pit lane's 0x42), every other segment as it is."""
    from dataclasses import replace
    marked = set(marked)
    return [replace(s, flag=s.flag | FLAG_NO_PUTBACK) if s.index in marked else s for s in segments]


def reverse_no_putback(rs: RomSet, entry: int) -> tuple[int, ...]:
    """The quads of original `entry` its reverse variant marks FLAG_NO_PUTBACK: the put-back spots with less than
    PUTBACK_CLEAR of tarmac or kerb ahead of the reverse pose (`putback_clear`), or with a spawned object on those first units
    (`putback_objects`)."""
    return tuple(sorted({k for k, d in putback_clear(rs, entry, True).items() if d < PUTBACK_CLEAR} | set(putback_objects(rs, entry, True))))


def reverse_of_original(rs: RomSet, entry: int) -> Reversed:
    """Phase 33: original `entry`'s (0 Big Forest, 1 Bay Bridge, 2 Acropolis) reverse variant from its own arcade tables in
    `rs`: the eight lines and the segment array read backwards (`convert.reverse.reverse_original`), a race blob with the game's
    checkpoints renumbered (`reverse_checkpoints`), the game's own twelve time records as they are, and the game's car table.
    (The game pays one extension at every checkpoint of a course, whatever the sector's length: Big Forest and Bay Bridge 331,
    Acropolis 457 at level 0. So the reversed lap's record is the game's record; `race_blob_for` would scale the extensions by
    the sectors' lengths, the converted courses' rule, and give Bay Bridge 468, 259, 266. ConvertError if a record of the ROM
    does not hold one value.) Further: the HUD map where the game draws it (NOT shifted for the reversed lap's interior as the seven's
    are: with 237.0 / 22 the originals' own outline objects ran off the screen's right edge on most of the lap, measured on the
    three, findings §6), the lines of ORIGINAL_REVERSE_PAIRS, the cars on ORIGINAL_REVERSE_GRID's points.
    No pit quad and no box: stage 1 offers no pit
    stop in reverse, as stage 1 of the seven did (the variant's pit quad is PIT_NONE and `pitstops` then grants none)."""
    e = ORIGINALS[entry]
    normal = course_entry_at(rs, e.bank, e.header_base)
    lines = road_lines(rs, normal)
    cl = [(p.x, p.z) for p in lines[0]]
    cps = checkpoints_at(rs, e.template)
    rcps = reverse_checkpoints(cps, len(cl))
    check_laps(5, rcps)
    times = {(v, lvl): time_record(rs, v, e.template, lvl) for v in range(VARIANTS) for lvl in range(LEVELS)}
    for key, rec in times.items():
        if len(set(rec.extensions)) != 1:
            raise ConvertError(f"{e.name}: the game's time record {key} pays {sorted(set(rec.extensions))}, not one extension")
    race = RaceBlob(times, rcps, car_table(rs, 0))
    if tuple(c.line for c in race.cars) != GAME_CAR_LINES:
        raise PatchError(f"the game's car table names the lines {tuple(c.line for c in race.cars)}, not {GAME_CAR_LINES}")
    race = RaceBlob(race.times, race.checkpoints, [CarEntry(c.models, c.line, ORIGINAL_REVERSE_GRID[entry][k], c.perf)
                                                   for k, c in enumerate(race.cars)])
    pit = original_reverse_pit(rs, entry)                             # stage 2: the pit stop in reverse (None: Bay Bridge)
    from dataclasses import replace
    tables = reverse_original(lines, segments_of(rs, normal))
    marked = set(reverse_no_putback(rs, entry))                       # second fix wave: no put-back onto a quad that faces a wall
    tables = replace(tables, segments=mark_no_putback(tables.segments, marked))
    return Reversed(tables, race, False, ORIGINAL_REVERSE_PAIRS[entry], pit[0] if pit else None, pit[1] if pit else None)


def picture_exclusions() -> list[tuple[int, int]]:
    """(address, length) spans the select pictures' free-run search leaves out: the directory image, the start-gantry block,
    (Phase 26 stage 3) the direction screen's block (`dirscreen_block`) and (Phase 31) the far copies' colour block
    (`far_colour_block`)."""
    from vrtools.arcade.gantry import BLOCK_BYTES
    lo, hi = dirscreen_block()
    flo, fhi = far_colour_block()
    from vrtools.arcade.origrev import BLOCK_BYTES as ORIGREV_BYTES
    return [(CODE_FREE[0], directory_layout()["end"] - CODE_FREE[0]), (flo, fhi - flo), (start_gantry_address(), BLOCK_BYTES),
            (lo, hi - lo), (origpic_address(), origrev_address() + ORIGREV_BYTES - origpic_address())]


def dirscreen_block() -> tuple[int, int]:
    """Phase 26 stage 3 (plan D11, Task 5): program-ROM [start, end) of the COURSE DIRECTION screen's data block (dirgfx.py: its
    arrows, caption, maps, palette sets and draw list), at most dirgfx.BLOCK_LIMIT bytes ending at the colour-table run's end
    (COLOUR_RUN_TAIL), its start 16-aligned. Erased in the original; build_all writes it before any first-fit writer, the annex's
    colour-run region ends at its start (`annex_regions`) and the select pictures' free-run search leaves it out
    (`picture_exclusions`). Its only other reader is the boot's colour-table upload (recon §6: the run's tail, PC 0xfe6b64); no
    colour entry a converted course names reaches it (`max_colour_entry`, checked on the built set)."""
    from vrtools.arcade.dirgfx import BLOCK_END, BLOCK_LIMIT, block_start
    lo = block_start()
    if not (COLOUR_RUN_TAIL[0] <= lo and BLOCK_END == COLOUR_RUN_TAIL[1] and BLOCK_END - lo <= BLOCK_LIMIT):
        raise PatchError(f"the direction screen's block {lo:#x}..{BLOCK_END:#x} does not fit {BLOCK_LIMIT} bytes at the colour run's end")
    return lo, BLOCK_END


def install_dirscreen_block(rs: RomSet) -> RomSet:
    """A new RomSet with the direction screen's block (dirgfx.block_image) at `dirscreen_block()`: written on erased ROM, kept
    when it is there already (build_all wrote it and ten_course_set makes sure of it); PatchError naming the span otherwise."""
    from vrtools.arcade.dirgfx import block_image
    lo, hi = dirscreen_block()
    image, _ = block_image(lo)
    assert len(image) == hi - lo
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    have = rs.program[lo - V60_PROGRAM:hi - V60_PROGRAM]
    if have == image:
        return out
    if any(b != 0xFF for b in have):
        raise PatchError(f"the direction screen's block {lo:#x}..{hi:#x} is neither erased nor the block")
    write_program_blob(out, lo, image)
    return out


START_GATE_NEAR = 8            # Phase 22o: a course whose Saturn START gate stands within this many road points of its line gets no
                               # host start gantry (Pascal, p22play99 Metropolis: "2 start flags" since the 22l flag starts; Amazon
                               # Falls and Metropolis start at the gate, the Oval and Surfers Road 50-60 units after it; Diablo's
                               # gate is 36 points before its line and keeps both)


def spawn_list_for(rs: RomSet, host: int, line: list[tuple[float, float]], checkpoints: tuple[int, ...], height,
                   gantries: bool = True, start_gantry: bool = True, grid_boards: bool = True, start_gantry_list: int | None = None) -> list:
    """The host course's race furniture (minimap, start and checkpoint gantries, grid boards) re-placed on `line`. With
    `start_gantry_list` (Phase 26 stage 2, Task 11) the start gantry draws that object list (`gantry.install_start_gantry`)
    instead of the arcade's: the same handler, position and yaw."""
    from dataclasses import replace
    from vrtools.arcade.spawn import START_GANTRY
    host_line = road_centreline(road_lines(rs, course_entry_at(rs, COURSE_BANK[host]))[:1])
    ents = replace_entities(decode_spawn_list(rs, ORIGINALS[host].spawn_table), host_line, checkpoints_at(rs, ORIGINALS[host].template),
                            line, checkpoints, height, gantries=gantries, start_gantry=start_gantry, grid_boards=grid_boards)
    if start_gantry_list is not None:
        ents = [replace(e, objlist=start_gantry_list) if e.handler == START_GANTRY else e for e in ents]
    if len(ents) > MAX_ENTITIES:
        raise PatchError(f"{len(ents)} entities exceed the spawn list's {MAX_ENTITIES}")
    return ents


def race_blob_for(rs: RomSet, template: int, n_points: int, time_factor: float = 1.0, pace: float = 1.0,
                  laps: int = 5, checkpoints: tuple[int, ...] | None = None, lap_totals: dict | None = None,
                  start_points: tuple[int, ...] | None = None) -> RaceBlob:
    """Checkpoints at thirds of a lap of `n_points` (or `checkpoints`: Phase 22e, the Saturn gates), the template's twelve time records scaled by sector length,
    and the original car table (variant 0 for both variants) with the opponents' pace scaled. ConvertError when
    `laps` needs more extensions than a record holds. With `lap_totals` (Phase 26 stage 2, plan D4) the record of each
    `(v, level)` key has that first-lap sum (`time_records_for(lap_total=)`): a reverse lap takes the normal lap's time. With
    `start_points` (after the owner's drive, a reverse grid such as BANK_ONE_GRID) car k starts on that point
    (`car_table_for(start_points=)`)."""
    cps = checkpoints if checkpoints is not None else checkpoints_for(n_points)     # Phase 22e: the Saturn gates
    check_laps(laps, cps)
    tcps = checkpoints_at(rs, template)
    tpoints = course_entry_at(rs, COURSE_BANK[COURSE_OF_TEMPLATE[template]]).header.road_points
    times = {(v, lvl): time_records_for(time_record(rs, v, template, lvl), tpoints, tcps, n_points, cps, time_factor,
                                  None if lap_totals is None else lap_totals[v, lvl])
             for v in range(VARIANTS) for lvl in range(LEVELS)}
    return RaceBlob(times, cps, car_table_for(car_table(rs, 0), pace, start_points))



def course_placement(rs: RomSet, sat: SaturnCourse, template: int, min_coverage: float = 0.98, flag_start: int | None = None):
    """The placement `convert_course` gives the Saturn course `sat` on the template's grid (`place.choose_placement`). Shared
    with the tests and `mame.pitpaths.pit_lane`, which need the build's own placement (the final review of Phase 26 stage 4)."""
    # the player spawns where the template's tables put it (GRID_OF_TEMPLATE): the converted road must pass there
    grid_course = COURSE_OF_TEMPLATE[template]
    return choose_placement(sat, grid_pose(rs, grid_course), grid_point=GRID_OF_COURSE[grid_course][0], min_coverage=min_coverage,
                            flag_start=flag_start)                                # Phase 22l: at the Saturn's flag where it fits


class CourseCollision(NamedTuple):
    lap: Lap
    sat: SaturnCourse          # with the unused gates hidden
    hidden_gates: int
    heights: object
    hfn: object
    col: object
    cells: object
    pts: list                  # centreline(lap): the resampling road_tables uses


def course_collision(sat: SaturnCourse, pl, template: int, min_coverage: float = 0.98, merge: bool = True, banking: bool = False,
                     camber: bool = True, lane_points: tuple = ()) -> CourseCollision:
    """The lap, heights and collision `convert_course` builds for `sat` at the placement `pl` (`course_placement`); called inside
    `placed(pl.angle, pl.tx, pl.tz)`. Shared with the tests that need the build's own collision (the pit quads go into the ROM by
    index; the final review of Phase 26 stage 4)."""
    lap = order_slices(sat, start_slice=pl.start_slice, direction=pl.direction, min_coverage=min_coverage)
    n_props = len(sat.placements.get(GATE_GROUP, []))
    sat = hide_unused_gates(sat, centreline(lap))                               # Phase 22t: no C.P. flag without its checkpoint
    hidden_gates = n_props - len(sat.placements.get(GATE_GROUP, []))
    heights = road_profile(sat, lap)
    hfn = banked_height(lap, heights, mesh_height(_ground_quads(sat))) if banking else \
        arc_height(lap, heights, sat.segments, camber=camber, ground=sat)           # Phase 16 (22a: the drawn banking): the arc profile (no 2-D steps) + the camber
    col, cells = saturn_collision(sat, hfn, lap=lap, merge=merge, cover=True, lane_points=lane_points,   # every AI line on tarmac (Phase 11)
                                  grid_clear=GRID_CLEAR_OF_COURSE[COURSE_OF_TEMPLATE[template]])   # 22n: the lines keep still at the grid
    pts = centreline(lap)                                                       # the same resampling road_tables uses
    return CourseCollision(lap, sat, hidden_gates, heights, hfn, col, cells, pts)

def _prop_reader(rs: RomSet, cl, src):
    """A plan's prop: read from the user's ROM now (an arcade prop, `PropSource`), or, for a `CourseProp` (Phase 34), a callable
    that cuts it out of the course's own upright scenery once `convert_tiles` has it."""
    if isinstance(src, CourseProp):
        x, z = planting_xz(cl, src.site)
        return lambda upright: prop_from_course(upright, x, z, src)
    return prop_from_cell(rs, src)


def convert_course(rs: RomSet, sat: SaturnCourse, name: str, bank: int, tgp_slot: int, template: int, tile_table: int,
                   label: int = 0, panel: tuple[int, int, int] | None = None, spawn_table: int | None = None,
                   min_coverage: float = 0.98, merge: bool = True, thin: float = 0.0, terrain_thin: float = 0.0, race_blob: int | None = None,
                   laps: int = 5, time_factor: float = 1.0, pace: float = 1.0, spawn_list: int | None = None,
                   banking: bool = False, camber: bool = True, backdrop: bool = True, saturn_cue: Path | None = None,
                   lane_points: tuple = (), flag_start: int | None = None, reverse: bool = False,
                   reverse_pairs: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7),
                   reverse_grid: tuple[int, ...] | None = None, start_gantry_list: int | None = None,
                   props: tuple = (), far_copies: tuple = (), tunnels: tuple = ()) -> tuple[RomSet, Converted]:
    """Convert one Saturn course into `rs`: blob in `bank`, collision in `tgp_slot` (straight slices merged when
    `merge`), scenery behind `tile_table` (thinned by `thin` when > 0). The entry's panel (map A, map B, art)
    defaults to the host course's (ten_course_set generates one); the entity spawn list defaults to the host's
    too (it carries the HUD minimap entity: an empty list draws the map huge and the car lost the hairpin
    without it). With `race_blob` (a free program-ROM address) the entry gets its own race blob (`race_blob_for`)
    and `laps`; without one it races on the template's tables. With `spawn_list` (a free program-ROM address) the
    entry gets the host's race furniture re-placed on its own road (`spawn_list_for`) instead of the host's whole
    list. With `reverse` (Phase 26) the result carries the course's reverse variant from the same conversion (`Reversed`),
    for `ten_course_set` to install, its pointer block naming the lines `reverse_pairs` (stage 2, plan D2) and, with
    `reverse_grid`, its car table starting car k on road point `reverse_grid[k]` (after the owner's drive). With
    `start_gantry_list` (stage 2, Task 11) a start gantry in the spawn list draws that object list (build_all installs it
    after every course). With `props` (Phase 29, `CoursePlan.props`) copies of each arcade prop, read from `rs` itself, are baked into
    the scenery cells at their plantings (`props.plant`: on the drawn ground, clear of the collision and the Saturn's upright scenery;
    report "props", the copies as built).
    With `far_copies` (Phase 31 prototype) the result carries the cells that hold a far landmark's
    silhouette (`Converted.far_cells`), for `ten_course_set` to install last; the course is otherwise built as without them.
    With `tunnels` (Phase 37, `CoursePlan.tunnels`) the tarmac quads credited to those road points carry the tunnel flag in the
    normal segment array and, the same quads, in the reverse variant's (report "tunnel_quads", the indices); every other byte of the
    course is as without them.
    PatchError names the course when its collision or blob does not fit."""
    host = HOST_OF_BANK[bank]
    pl = course_placement(rs, sat, template, min_coverage=min_coverage, flag_start=flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        lap, sat, hidden_gates, heights, hfn, col, cells, pts = course_collision(
            sat, pl, template, min_coverage=min_coverage, merge=merge, banking=banking, camber=camber, lane_points=lane_points)
        pit_quad = pit_entry_quad(sat, col, pts)                                # Phase 22f: the pit lane's mouth, else none; Phase 22i:
        box = pit_box(sat, col, pts) if pit_quad is not None else None          # the pit sequence parks the car at the course's own box
        if pit_quad is not None and not pit_lane_of(sat).pit_stop:
            pit_quad = box = None
        rpit = reverse_pit(sat, col, pts) if reverse and pit_quad is not None else None   # stage 4: the variant's pair and box,
                                                                                           # on the same collision and centreline
        tables = road_tables(lap, col.quads[:col.n_tarmac], attitude=attitude_words(lap, sat.segments, pts, heights),
                             lanes=col.lanes)   # Phase 15; Phase 22c: the AI lines narrow at a curb at the road
        rtables = reverse_tables(tables, col.quads[:col.n_tarmac]) if reverse else None   # Phase 26: the same lines and quads
        tunnel = tunnel_quads(tables.segments, tunnels, len(tables.lines[0]))             # Phase 37: the same quads both ways
        tables = with_tunnel_flags(tables, tunnel)
        rtables = with_tunnel_flags(rtables, tunnel) if reverse else None
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
        gates = saturn_gates(sat, cl)
        cps = gate_checkpoints(gates, len(cl))                                    # Phase 22e: the Saturn's own gates fire
        picture = course_picture(sat, lap, None, None)                         # Phase 21: the select picture (named later)
        if spawn_list is not None:
            gate = start_gate_point(sat, cl)                                   # Phase 22o: one START arch — the Saturn's own
            host_start = gate is None or min(gate, len(cl) - gate) > START_GATE_NEAR   # gate where the lap starts at it, else the host's
            ents = spawn_list_for(rs, host, cl, cps, hfn, gantries=False, start_gantry=host_start,   # (the host's narrow C.P. gantries left out;
                                  grid_boards=False, start_gantry_list=start_gantry_list)        # Phase 22q: the grid boards' flag row too;
                                                                                                 # Task 11: the gantry's own frames)
            write_program_blob(out, spawn_list, encode_spawn_list(ents, spawn_list))
            spawn_table = spawn_list
        try:
            baked = [(_prop_reader(rs, cl, src), [(*planting_xz(cl, s), s.heading) for s in sites], [s.point for s in sites])
                     for src, sites in props]                                   # Phase 29: read from the user's own ROM at build time
                                                                                # (review M6: inside the try, so its errors name the course)
            objs, words, report = convert_tiles(sat, out, host, thin=thin, keep_near=cl, terrain_thin=terrain_thin,
                                                props=baked, prop_collision=[q.corners for q in col.quads],
                                                outside_limit=OUTSIDE_MAP_MAX if flag_start is not None or pit_quad is not None else 0,
                                                far_copies=far_copies)   # Phase 22l: a flag
                                                                                                   # start (22n: or a pit-lane placement) may leave a few scenery quads off the map
        except ConvertError as e:                                               # Phase 26 stage 2: added for a gate whose lettering is not
            raise ConvertError(f"{name}: {e}") from e                           # recognised; it names the course in every ConvertError of convert_tiles
        far_cells = report.pop("far_cells", None)                                   # Phase 31 (prototype): installed by ten_course_set
        report["coverage"] = col.coverage
        report["start_gantry"] = host_start if spawn_list is not None else None     # Phase 22o: the host's start gantry placed?
        report["start_gantry_list"] = start_gantry_list if spawn_list is not None and host_start else None   # Task 11: drawing which list
        report["grid_boards"] = False if spawn_list is not None else None           # Phase 22q: the host's grid boards (the flag row) left out
        report["lanes"] = col.lanes                                                 # Phase 22n: (left, right, shift) per centreline point
        report["checkpoints"] = cps
        report["hidden_gates"] = hidden_gates                                        # Phase 22t: the C.P. gates left out
        if backdrop_report is not None:
            report["backdrop"] = backdrop_report
    out = patch_course_tiles(out, host, objs, words, tile_table=tile_table)
    map_obj = install_outline(out, cl, template, extra=[pit_line] if pit_line else [],   # Phase 22b: the HUD map's own outline;
                              floor=map_floor(col.quads))                                # Phase 25: under the cars' markers
    report["map_outline"] = map_obj
    pa, pb, art = panel if panel else (ORIGINALS[host].panel_map, ORIGINALS[host].panel_b, ORIGINALS[host].art)
    spawn = ORIGINALS[host].spawn_table if spawn_table is None else spawn_table
    music = next(o.music for o in ORIGINALS if o.template == template)
    race = 0
    normal_blob = race_blob_for(rs, template, len(cl), time_factor, pace, laps, checkpoints=cps) if race_blob is not None or reverse else None
    if race_blob is not None:
        write_program_blob(out, race_blob, encode_race_blob(normal_blob, race_blob))
        race = race_blob
    rev = None
    if reverse:                                                                   # Phase 26: the same gates, numbered backwards
        rcps = reverse_checkpoints(cps, len(cl))                                  # the normal lap's renumbered, less any just after the line (stage 3 Task 8)
        totals = {k: lap_total(r, cps) for k, r in normal_blob.times.items()}   # stage 2 (D4): the reverse lap takes the normal lap's time
        rev = Reversed(rtables, race_blob_for(rs, template, len(cl), time_factor, pace, laps, checkpoints=rcps, lap_totals=totals,
                                              start_points=reverse_grid),   # after the drive: BANK_ONE_GRID on the bank-1 courses
                       interior_on_the_left(reverse_points(cl)), tuple(reverse_pairs),
                       pit_quad=rpit.quad if rpit else None, pit_box=rpit.box if rpit else None)
    left = interior_on_the_left(cl)
    report["map_shift"] = left
    report["pit_quad"] = pit_quad
    report["tunnel_quads"] = sorted(tunnel)                                      # Phase 37: the quads that carry the tunnel flag
    report["pit_box"] = box
    report["reverse_pit_quad"] = rpit.quad if rpit else None                     # stage 4: the reverse variant's (None: no variant
    report["reverse_pit_box"] = rpit.box if rpit else None                       # or no pit stop)
    e = CourseEntry10(name, label, bank, base, tgp_slot, template, tile_table, spawn, pit_quad, pa, pb, art, music, race,
                      laps if race_blob is not None else 0, MAP_TX_SHIFTED if left else MAP_TX, MAP_CROSS_SHIFTED if left else 0,
                      OFF_COURSE_LIMIT, map_obj=map_obj, pit_box=box)
    return out, Converted(e, lap, cl, report, picture, rev, far_cells)


MAP_FLOOR_RADIUS = 60.0     # the outline lies under every collision quad corner this near (the road, its run-off, the pit lane)


def map_floor(quads):
    """Phase 25: the lowest height a car can have about a point: the lowest corner of the collision quads within
    MAP_FLOOR_RADIUS of it (the HUD map's outline is laid under it, `hudmap.outline_quads`)."""
    import numpy as np
    c = np.array([p for q in quads for p in q.corners], float)

    def floor(x: float, z: float) -> float:
        d2 = (c[:, 0] - x) ** 2 + (c[:, 2] - z) ** 2
        near = c[d2 <= MAP_FLOOR_RADIUS ** 2, 1]
        return float(near.min()) if len(near) else float(c[int(d2.argmin()), 1])
    return floor


def install_outline(rs: RomSet, cl, template: int, extra=(), floor=None) -> tuple[int, int, int]:
    """Phase 22b: the course's HUD map outline (`hudmap.outline_quads` along its centreline) written into free polygon ROM
    on the colour entry of its host's outline (the game's table at MAP_OBJ_TABLE, by data index); returns the object list
    record (polygon word address, tex, size) the directory's `mapobj` routine hands to the map entity."""
    from vrtools.arcade.course import MAP_OBJ_TABLE
    from vrtools.arcade.patch import poly_free_runs, write_polygons
    from vrtools.convert.hudmap import encode_outline, outline_quads
    host_list = struct.unpack("<I", rs.read_v60(MAP_OBJ_TABLE + 4 * template, 4))[0]
    _, host_tex, _, _ = struct.unpack("<4I", rs.read_v60(host_list, 16))
    blob, layout = encode_outline(outline_quads(cl, extra=list(extra), floor=floor), tex=host_tex + 1)   # the host's first outline quad's entry
    at = next((a for a, n in poly_free_runs(rs) if n >= len(blob)), None)
    if at is None:
        raise PatchError("no polygon ROM left for the HUD map outline")
    return write_polygons(rs, blob, at), host_tex + 1, layout.record_count


def build_all(rs: RomSet, saturn_cue: Path, plans: list[CoursePlan] = COURSES) -> tuple[RomSet, list[Converted]]:
    """Convert every planned course into `rs` in order, the k-th behind tile table k. PatchError (naming the
    course) when one does not fit its bank or the TGP budget. Phase 26 stage 2 (Task 11): a course that keeps the host's start
    gantry has it draw the converted courses' own frames (`gantry.install_start_gantry`, at `start_gantry_address()`), written
    after every course so that no course's polygon-ROM objects move; each such course's report carries the `Installed`."""
    from vrtools.arcade.gantry import install_start_gantry
    out, converted = install_dirscreen_block(rs), []                           # Phase 26 stage 3 (D11): before every first-fit writer
    gantry_list = start_gantry_address()
    for k, p in enumerate(plans):
        sat = load_saturn_course(saturn_cue, p.path)
        out, c = convert_course(out, sat, p.name, p.bank, p.tgp_slot, p.template, tile_table_address(k), label=p.label,
                                min_coverage=p.min_coverage, thin=p.thin, terrain_thin=p.terrain_thin, race_blob=race_blob_address(k), laps=p.laps,
                                time_factor=p.time_factor, pace=p.pace, spawn_list=spawn_list_address(k), banking=p.banking, camber=p.camber,
                            backdrop=p.backdrop, saturn_cue=saturn_cue, lane_points=p.lane_points, flag_start=p.flag_start,
                                reverse=p.reverse, reverse_pairs=p.reverse_pairs, reverse_grid=p.reverse_grid,
                                start_gantry_list=gantry_list, props=p.props, far_copies=p.far_copies, tunnels=p.tunnels)
        converted.append(c)
    if any(c.report.get("start_gantry_list") for c in converted):
        installed = install_start_gantry(out, gantry_list)                     # in place, on erased ROM only
        for c in converted:
            c.report["start_gantry_objects"] = installed if c.report.get("start_gantry_list") else None
    return out, converted


def with_spawn(d: Directory, lay: dict[str, int]) -> Directory:
    """Entries with spawn_table 0 get the directory's empty spawn list."""
    from dataclasses import replace
    return [replace(e, spawn_table=lay["spawn"]) if e.spawn_table == 0 else e for e in d]


def report_lines(before: int, after: int, converted: list[Converted], plans: list[CoursePlan] = COURSES,
                 poly_left: int | None = None, directory: Directory | None = None) -> list[str]:
    """The build report: the TGP budget and one line per converted course (bank, header, TGP slot, tile table, lap
    length, scenery, race blob knobs, spawn list, coverage fill) and, Phase 26, one line after it per reverse variant (its
    load and maps records in the annex, header and race blob, read from `directory`, the set's decoded directory; its
    tables' bytes in the bank, the lines stored and its checkpoints) — what `spike/ten_course_build.py` prints."""
    lines = [f"TGP budget: {before} words free before, {after} after" + ("" if poly_left is None else f"; polygon ROM left {poly_left} bytes")]
    for k, (plan, c) in enumerate(zip(plans, converted)):
        e = c.entry
        lines.append(f"entry {3 + k} {e.name}: bank {e.bank}, header {e.header_base:#x}, TGP slot {e.tgp_slot}, tile table {e.tile_table:#x}, "
                     f"lap {c.lap.length:.0f} units, scenery {c.report['quads']} quads in {c.report['cells']} cells ({c.report['polygon_bytes']} bytes; layers g0-g4, "
                     f"terrain thinned {c.report.get('terrain_thinned', 0)} (terrain_thin {plan.terrain_thin})), "
                     f"thinned {c.report['thinned']} (thin {plan.thin}), "
                     f"race blob {e.race:#x} (laps {e.laps}, time x{plan.time_factor}, pace x{plan.pace}, banking {plan.banking}), spawn list {e.spawn_table:#x}, "
                     f"coverage {c.report.get('coverage')}, HUD map {'shifted right (anticlockwise)' if c.report.get('map_shift') else 'as the game draws it'}, "
                     f"off-course limit {e.off_course} frames"
                     + (f", props {len(c.report['props'])} ({c.report['prop_faces']} faces)" if c.report.get("props") else ""))
        if c.reverse is not None:
            rec = directory[3 + k].reverse if directory is not None else None
            size = len(build_variant_blob(c.reverse.tables, WINDOW, WINDOW, WINDOW, WINDOW, c.reverse.pairs))   # the size alone
            lines.append(f"  entry {3 + k} reverse variant: "
                         + (f"load {rec.at:#x}, maps {rec.at + maps_offset():#x}, header {rec.entry.header_base:#x}, race blob {rec.entry.race:#x}, "
                            if rec else "")
                         + f"tables {size} bytes in bank {e.bank}, {len(set(c.reverse.pairs))} lines stored (pairs {c.reverse.pairs}), "
                         f"checkpoints {c.reverse.race.checkpoints}")
        if c.report.get("far_copies"):                               # Phase 31 (prototype)
            inst = c.report.get("far_installed") or {}
            lines.append(f"  entry {3 + k} far copies (Phase 31 prototype): " + ", ".join(
                f"cell {cell} +{v['copied']} faces from cells {v['from']}" for cell, v in sorted(c.report["far_copies"].items()))
                + (f"; +{inst['added_records']} records, {inst['polygon_bytes']} bytes of polygon ROM, {inst['colour_entries']} colour "
                   f"entries from {inst['colour_first']:#x}" if inst else "; not installed"))
    for k, e in enumerate((directory or [])[:len(ORIGINALS)]):                   # Phase 33: the originals' reverse variants
        if e.reverse is not None:
            rec, pairs, grid = e.reverse, ORIGINAL_REVERSE_PAIRS[k], ORIGINAL_REVERSE_GRID[k]
            lines.append(f"entry {k} {e.name} reverse variant (from its own arcade tables): load {rec.at:#x}, maps {rec.at + maps_offset():#x}, "
                         f"header {rec.entry.header_base:#x} in bank {e.bank}, race blob {rec.entry.race:#x}, {len(set(pairs))} lines stored "
                         f"(pairs {pairs}), grid {grid}, " + (f"pit quad {rec.entry.pit_quad}, box {rec.entry.pit_box}" if rec.entry.pit_quad is not None else "no pit lane") + ", HUD map as the game draws it"
                         + ("; ONE LINE FOR ALL SIXTEEN CARS: a stopgap, bank 1 has no room for more" if len(set(pairs)) == 1 else ""))
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


def backdrop_headers(entries: list[CourseEntry10]) -> list[tuple[int, int]]:
    """(bank, header) of every entry and of every reverse variant: the `gfx` routine reads [header] of whichever record the
    loader serves (Phase 26: a variant's header too), so `check_backdrop_markers` covers both."""
    out = []
    for e in entries:
        if e.bank is None:
            continue
        out.append((e.bank, e.header_base))
        if e.reverse is not None:
            out.append((e.reverse.entry.bank, e.reverse.entry.header_base))
    return out


ANNEX_MARGIN = 16           # erased bytes left at each end of a run (as picture.free_runs leaves): a table may end in 0xff bytes
COLOUR_RUN_TAIL = (0x2B1842, 0x2C0000)    # the colour-table run, erased in the original (59 326 bytes)


def annex_regions() -> list[tuple[int, int]]:
    """Phase 26 stage 2 (plan D1, recon §1): program-ROM [start, end) the annex may take, in order: the code area past the
    directory image (`directory_layout()["end"]`) up to the originals' picture block (Phase 33, `origpic_address`; above it
    the originals' reverse block, the far copies' colour block, Phase 31, `far_colour_block`, and the start-gantry block,
    Task 11, `start_gantry_address`), then the
    colour-table run's tail up to the direction screen's block (stage 3, `dirscreen_block`). Computed when called, not at
    import, so a layout that overflows raises where the annex is placed (PatchError from `start_gantry_address`), not on every
    import of this module."""
    return [(directory_layout()["end"], origpic_address()), (COLOUR_RUN_TAIL[0], dirscreen_block()[0])]


def reverse_annex(rs: RomSet, count: int) -> dict[str, int]:
    """Phase 26: room for `count` reverse variants in the program ROM: their 64-byte load records from "load", their maps
    records from "maps" = load + maps_offset() (the routines reach a maps record at R8 + maps_offset(), a variant's as a
    directory entry's), their race blobs from "race", up to "end"; record k at + LOAD_SIZE * k, blob k at + RACE_BLOB_BYTES * k.
    None of it may sit in the data window (the bank byte is read before the bank is mapped; the race pointers outlive bank
    switches). The first erased run that holds it, ANNEX_MARGIN bytes in from the run's ends, over `annex_regions()` in order:
    - the code area past the directory image (CODE_FREE from `directory_layout()["end"]`, up to the start-gantry block since
      Task 11, `start_gantry_address`): erased since Phase 7, but what the tile tables, race blobs, spawn lists and select
      pictures leave of it lies in short runs (stage 2 recon §1 on the stage 1 build: the longest 1 792 bytes; on the
      stage 2 set out/p26play3, the longest 4 032, below the start-gantry block): too short for the seven;
    - the colour-table run 0x2b1842..0x2c0000, erased in the original (59 326 bytes), whose head the conversions' colour words
      (to 0x2b6698, entry 0x9b34b) and the select pictures (to 0x2b90b0) take first: seven variants land in its tail
      (0x2b90c0..0x2bcb00 on the stage-2 build, 13 552 bytes spare). Its only reader is the boot's colour-table upload, PC
      0xfe6b64, which reads the whole program ROM once (128 chunks of 0x1000 halfwords from 0x200000): read taps on
      0x2b90b0..0x2bffff over attract (240 s) and the reverse Metropolis, Big Forest and Surfers Oval races (330 s each) saw
      that PC alone, each halfword once, before frame 268 (recon rom/taps.py, rom/tapsum.log), the same as on CODE_FREE's
      tail; no object record's colour range reaches the tail (rom/texscan.py; `max_colour_entry` checks the set's).
    Called after every other writer of these regions (build_all's tile tables, race blobs, spawn lists and colour words, the
    select pictures), and the directory image ends before the first, so nothing written later lands on it. PatchError with
    the sizes and the regions when none holds it."""
    if not (1 <= count and LOAD_SIZE * count <= maps_offset()):
        raise PatchError(f"{count} reverse variants: the load records would run into the maps records ({maps_offset()} bytes apart)")
    rel = {"load": 0, "maps": maps_offset()}
    rel["race"] = (rel["maps"] + LOAD_SIZE * count + 15) // 16 * 16
    rel["end"] = rel["race"] + RACE_BLOB_BYTES * count
    regions = annex_regions()
    for lo, hi in regions:
        for m in re.finditer(rb"\xff{%d,}" % (rel["end"] + 2 * ANNEX_MARGIN), rs.program[lo - V60_PROGRAM:hi - V60_PROGRAM]):
            load = (lo + m.start() + ANNEX_MARGIN + 15) // 16 * 16
            if load + rel["end"] <= lo + m.end() - ANNEX_MARGIN:
                return {k: load + v for k, v in rel.items()}
    raise PatchError(f"no erased run of {rel['end']} bytes (+{ANNEX_MARGIN} at each end) in {', '.join(f'{lo:#x}..{hi:#x}' for lo, hi in regions)} "
                     f"for {count} reverse variants ({count} x {LOAD_SIZE}-byte load and maps records {maps_offset()} bytes apart, "
                     f"{count} x {RACE_BLOB_BYTES}-byte race blobs)")


def max_colour_entry(rs: RomSet) -> int:
    """Phase 26 stage 2 (plan D1, recon §1): the highest colour-table entry the converted courses' scenery reads: over every
    record of the tile tables of directory entries 3-9, its tex plus its object's tex advances (each advancing record reads
    the next entry; recon rom/texscan.py). Entry e is program-ROM byte 2 * (e - 0x40000) (`colours.TABLE_BASE`): the boot
    uploads the whole program ROM as the colour table, so the annex in the colour run must lie past this entry's word.
    Task 11: the frames of a converted entry's start gantry too (its spawn list's object list other than the arcade's)."""
    from vrtools.arcade.course import tile_table_at
    from vrtools.arcade.gantry import START_GANTRY_OBJECTS, frame_records
    from vrtools.arcade.polyrom import decode_object
    from vrtools.arcade.spawn import START_GANTRY
    top = 0
    d = decode_directory(rs)[3:]
    records = [(t.poly_adr, t.tex_adr, t.size) for tbl in sorted({e.tile_table for e in d}) for t in tile_table_at(rs, tbl)]
    for objs in sorted({x.objlist for e in d for x in decode_spawn_list(rs, e.spawn_table) if x.handler == START_GANTRY}):
        if objs != START_GANTRY_OBJECTS:
            records += frame_records(rs, objs)
    for poly, tex, size in records:
        if size:                                                                  # empty cells: (0, 0, 0)
            obj = decode_object(rs.polygons, poly, size)
            top = max(top, tex + sum(1 for r in obj.records if r.tex_advance))
    return top


def install_reverse(rs: RomSet, entry: CourseEntry10, rev: Reversed, at: int, race_at: int,
                    min_run: int | None = None) -> tuple[RomSet, CourseEntry10]:
    """Phase 26 (design §6.3): a new RomSet with `entry`'s reverse variant beside it: its blob (`build_variant_blob`) placed
    first-fit in the entry's bank, naming the normal blob's collision map, surface table and backdrop directory (read back
    from the entry's header), its pointer block naming the lines `rev.pairs` (stage 2, plan D2), and its race blob at
    `race_at`; and the entry with its ReverseRecord(at, variant). The variant is the entry with its own header and race blob,
    its own pit quad and box (stage 4: `rev.pit_quad`, `rev.pit_box`; both None, no pit, where the normal entry has no pit
    stop) and the HUD map shifted by the reversed lap's interior side; its load and maps records at `at` are written by
    install_directory (the pit quad at the load record's +0x10, the box at the maps record's +16). `min_run` (Phase 33): the
    shortest free run of the bank the blob may take (`blob.place_blob`; None: its default)."""
    from dataclasses import replace
    normal = course_entry_at(rs, entry.bank, entry.header_base)
    pb = decode_pointer_block(rs, normal)
    out, base = place_blob(rs, entry.bank, lambda b: build_variant_blob(rev.tables, b, normal.header.gfx_dir, pb.collision, pb.surface,
                                                                        rev.pairs),
                           **({} if min_run is None else {"min_run": min_run}))
    write_program_blob(out, race_at, encode_race_blob(rev.race, race_at))   # in place: on place_blob's new RomSet, never on `rs`
    v = replace(entry, header_base=base, race=race_at, pit_quad=rev.pit_quad, pit_box=rev.pit_box, map_tx=MAP_TX_SHIFTED if rev.interior_left else MAP_TX,
                map_cross=MAP_CROSS_SHIFTED if rev.interior_left else 0, reverse=None)
    return out, replace(entry, reverse=ReverseRecord(at, v))


def ten_course_set(rs: RomSet, converted: list[Converted], placeholder: Converted | None = None,
                   panels: bool = True, reverse: bool = True, crew: bool = True, originals_reverse: bool = True) -> RomSet:
    """The directory for the three originals followed by `converted` (in order); remaining entries up to ten
    repeat `placeholder` (or the last converted course) under the remaining Saturn names. With `panels`, every
    non-original entry gets a generated select panel (its course outline and name on the host's frame). With `reverse`
    (Phase 26), every converted course with a reverse variant gets it beside its entry (stand-ins get none), and the set gets
    the COURSE DIRECTION screen's block (stage 3, `install_dirscreen_block`: written when the block's span is erased, kept when
    build_all wrote it, PatchError when other bytes are there). The attract logo gets its "Extended" (title.py). `crew` False
    (a switch for the tests only, stage 4 Task 5): the set without Task 5's crew change (`install_directory`). Phase 31
    (prototype): a converted course's far copies (`Converted.far_cells`) are installed last of all (`install_far`), on what is
    still erased, so the set is otherwise byte for byte the set without them up to that point; the course's report gets
    "far_installed". (Phase 33's checkpoint lettering, installed after them, takes first fit what they leave: in a set built
    without them it lands on their bytes, so only `originals_reverse` False gives two sets that differ by the copies alone.)
    Phase 33 (`originals_reverse`, with `reverse`): the three originals get a reverse variant too (`reverse_of_original`), their
    records and race blobs after the converted courses' in the one annex (so the seven's records stay where they were and their
    race blobs move up by the three more maps records), their tables after the converted variants' in their banks, and the
    set gets the originals' reverse block (`origrev.install_origrev`: no best time recorded, the HUD's level word). False: the
    set as before Phase 33."""
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
    variants = [k for k, c in enumerate(converted) if c.reverse is not None] if reverse else []
    firsts = list(range(len(ORIGINALS))) if reverse and originals_reverse else []
    if variants or firsts:                                                    # Phase 26: after the pictures (they take CODE_FREE's runs first-fit),
        out = install_dirscreen_block(out)                          # so the variants take what is left past everything else; stage 3:
        annex = reverse_annex(out, len(variants) + len(firsts))     # the direction screen's block (build_all's, kept; else written)
        for i, k in enumerate(variants):
            out, entries[k] = install_reverse(out, entries[k], converted[k].reverse, annex["load"] + LOAD_SIZE * i,
                                              annex["race"] + RACE_BLOB_BYTES * i)
        for i, k in enumerate(firsts, len(variants)):              # Phase 33: after the seven's, in the annex and in the banks
            out, originals[k] = install_reverse(out, originals[k], reverse_of_original(out, k), annex["load"] + LOAD_SIZE * i,
                                                annex["race"] + RACE_BLOB_BYTES * i, min_run=ORIGINAL_MIN_RUN)
    if firsts:                                                      # Phase 33 (C3, C4): START reads from behind, no arrow boards
        originals = install_reverse_spawn_lists(out, originals)
    lay = directory_layout()
    check_backdrop_markers(out.data, backdrop_headers(entries) + [(o.reverse.entry.bank, o.reverse.entry.header_base)
                                                                  for o in originals if o.reverse is not None])
    out = install_directory(out, with_spawn(originals + entries, lay), crew=crew)
    if firsts:                                                      # Phase 33: no best time and the level word in an original's reverse race
        from vrtools.arcade.origrev import install_origrev
        check_reserved_blocks()
        install_origrev(out, origrev_address(), lay["hudname"], lay["hudrev"])
    out = install_title(out)                                        # the attract logo's "Extended"
    for c in converted:
        if c.far_cells:                                             # Phase 31 (prototype): after every other writer
            out, c.report["far_installed"] = install_far(out, c)
    if firsts:                                                      # Phase 33 stage 2: C.P. reads from behind; after the far copies, so
        install_checkpoint_lists(out, originals)                    # that they lie where they lie without it
        if panels:                                                  # fix wave (C1): an original's two-layer picture on the
            install_original_pictures(out, lay)                     # direction screen; last of all, on what is still erased
    return out


def install_far(rs: RomSet, c: Converted) -> tuple[RomSet, dict]:
    """Phase 31 (prototype): `c`'s far copies in the set (`farcopy.install_far_copies`): new objects for the cells that carry
    them, on the polygon ROM's erased bytes, their colour entries in the block reserved for them (`far_colour_block`: below
    the colour run's annex and the direction screen's block, so `max_colour_entry` stays below both; after review, no longer
    in whatever erased run a search of the code area found, which was the unused tail of Alpine's spawn-list slot). Called by
    ten_course_set after its last writer: nothing else in the set moves. The polygon-ROM floor (POLY_FLOOR_BYTES) must still
    hold."""
    from vrtools.arcade.farcopy import install_far_copies
    out, report = install_far_copies(rs, c.entry.tile_table, HOST_OF_BANK[c.entry.bank], c.far_cells, far_colour_block())
    if poly_budget(out) < POLY_FLOOR_BYTES:
        raise PatchError(f"{c.entry.name}: the far copies ({report['polygon_bytes']} bytes) leave less than {POLY_FLOOR_BYTES} "
                         f"bytes of polygon ROM free")
    return out, report


def install_pictures(rs: RomSet, names: list[str], bases: list) -> tuple[RomSet, list[int]]:
    """Phase 21: the seven entries' pictures (`bases` lettered with `names`, quantised), the originals' maps and the ten
    picture records, placed in free runs of bank 0 and the program ROM (outside the directory's code area). Returns the
    new RomSet and the ten record addresses (the three originals first)."""
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    masks = letters(rs)
    runs = [list(r) for r in free_runs(rs, picture_exclusions())]

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
