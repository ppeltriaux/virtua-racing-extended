import struct

import pytest

from vrtools.arcade.course import COURSE_BANK, course_entry_at, road_centreline, road_lines
from vrtools.arcade.directory import ORIGINALS
from vrtools.arcade.race import checkpoints
from vrtools.arcade.romset import RomSet
from vrtools.arcade.spawn import (CHECKPOINT_GANTRIES, GRID_BOARDS, KEEP_HANDLERS, MINIMAP, SPAWN_LIST_BYTES, START_GANTRY,
                                  decode_spawn_list, encode_spawn_list, replace_entities, road_relative)


def test_spawn_lists_round_trip(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    for host in range(3):
        ents = decode_spawn_list(rs, ORIGINALS[host].spawn_table)
        assert len(ents) == (32, 107, 14)[host]
        data = encode_spawn_list(ents, 0x290000)
        assert len(data) == SPAWN_LIST_BYTES(len(ents)) and struct.unpack_from("<I", data, 0)[0] == 0x290400
    bf = decode_spawn_list(rs, ORIGINALS[0].spawn_table)
    assert sum(e.handler == MINIMAP for e in bf) == 1 and sum(e.handler == START_GANTRY for e in bf) == 1
    assert sum(e.handler in CHECKPOINT_GANTRIES for e in bf) == 2 and sum(e.handler == GRID_BOARDS for e in bf) == 10


def test_race_furniture_is_road_relative_on_the_hosts(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    for host, course in ((0, 2), (1, 0), (2, 1)):
        line = road_centreline(road_lines(rs, course_entry_at(rs, COURSE_BANK[host]))[:1])
        ents = decode_spawn_list(rs, ORIGINALS[host].spawn_table)
        k, lat, dyaw = road_relative(next(e for e in ents if e.handler == START_GANTRY), line)
        assert k < 20 or k > len(line) - 20                                            # the start gantry straddles the start line
        assert abs(lat) < 20
        cps = checkpoints(rs, course)
        ks = sorted(road_relative(e, line)[0] for e in ents if e.handler in CHECKPOINT_GANTRIES)
        assert all(abs(a - b) <= 3 for a, b in zip(ks, cps[1:])), (host, ks, cps)      # gantries stand at the checkpoints


def test_replace_entities_keeps_only_furniture_at_the_converted_spots(romset_zip):
    rs = RomSet.from_zip(romset_zip)
    line = road_centreline(road_lines(rs, course_entry_at(rs, 1))[:1])              # Bay Bridge's line as a stand-in "converted" line ...
    shifted = [(x + 500.0, z) for x, z in line]                                       # ... shifted: the furniture must move with it
    ents = decode_spawn_list(rs, ORIGINALS[1].spawn_table)
    out = replace_entities(ents, line, checkpoints(rs, 0), shifted, checkpoints(rs, 0), lambda x, z: 7.0)
    assert {e.handler for e in out} <= KEEP_HANDLERS and sum(e.handler == MINIMAP for e in out) == 1
    assert len(out) == 1 + 1 + 2 + sum(e.handler == GRID_BOARDS for e in ents)
    g0 = next(e for e in ents if e.handler == START_GANTRY); g1 = next(e for e in out if e.handler == START_GANTRY)
    assert g1.x == pytest.approx(g0.x + 500.0, abs=1.0) and g1.z == pytest.approx(g0.z, abs=1.0) and g1.y == 7.0 and g1.yaw == g0.yaw


def test_replace_entities_can_leave_the_start_gantry_out(romset_zip):
    """Phase 22o (Pascal, p22play99 Metropolis: "2 start flags"): since Phase 22l a course may start at the Saturn's own
    START gate, a drawn prop, so the host's start gantry re-placed at road point 0 stood through it. With `start_gantry`
    False the host's gantry is left out; the minimap and the grid boards stay."""
    rs = RomSet.from_zip(romset_zip)
    line = road_centreline(road_lines(rs, course_entry_at(rs, 1))[:1])
    ents = decode_spawn_list(rs, ORIGINALS[1].spawn_table)
    out = replace_entities(ents, line, checkpoints(rs, 0), line, (0, 50, 120, 200), lambda x, z: 7.0, gantries=False, start_gantry=False)
    assert sum(e.handler == START_GANTRY for e in out) == 0 and sum(e.handler == MINIMAP for e in out) == 1
    assert sum(e.handler == GRID_BOARDS for e in out) == sum(e.handler == GRID_BOARDS for e in ents)


def test_replace_entities_can_leave_the_grid_boards_out(romset_zip):
    """Phase 22q (Pascal, p22play105 Metropolis: the row of country flags at the start "we can't touch", "hide them if
    they are not in the Saturn"): the host's grid boards entity draws the flag row along the start straight (an
    experimental build without it: the flags gone, the start lights and the grid girl, the program's own, still there);
    the Saturn's courses have no such flags. With `grid_boards` False the boards are left out; the minimap and the
    start gantry stay."""
    rs = RomSet.from_zip(romset_zip)
    line = road_centreline(road_lines(rs, course_entry_at(rs, 2))[:1])         # Acropolis (Metropolis's host): 7 boards; Bay Bridge has none
    ents = decode_spawn_list(rs, ORIGINALS[2].spawn_table)
    assert sum(e.handler == GRID_BOARDS for e in ents) >= 1
    out = replace_entities(ents, line, checkpoints(rs, 2), line, (0, 50, 120, 200), lambda x, z: 7.0, gantries=False, grid_boards=False)
    assert sum(e.handler == GRID_BOARDS for e in out) == 0
    assert sum(e.handler == START_GANTRY for e in out) == 1 and sum(e.handler == MINIMAP for e in out) == 1

def test_replace_entities_can_leave_the_checkpoint_gantries_out(romset_zip):
    """Phase 22e: the converted courses fire their checkpoints at the Saturn's own gates (drawn by the scenery, full
    road width), so the host's C.P. gantries (too narrow for the Saturn roads) are left out; the minimap, the start
    gantry and the grid boards stay."""
    rs = RomSet.from_zip(romset_zip)
    line = road_centreline(road_lines(rs, course_entry_at(rs, 1))[:1])
    ents = decode_spawn_list(rs, ORIGINALS[1].spawn_table)
    out = replace_entities(ents, line, checkpoints(rs, 0), line, (0, 50, 120, 200), lambda x, z: 7.0, gantries=False)
    assert not [e for e in out if e.handler in CHECKPOINT_GANTRIES]
    assert sum(e.handler == START_GANTRY for e in out) == 1 and sum(e.handler == MINIMAP for e in out) == 1
