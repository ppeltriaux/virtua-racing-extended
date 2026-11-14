"""Phase 26 stage 2, Task 11 (the owner's reverse drive: "a flag was there with nothing on it"; option B): the converted courses'
start gantry draws its own copy of the arcade's 32 waving frames, each frame's records unchanged and followed by its letters
mirrored left to right about the banner's centre, one-sided, standing as far behind that frame's banner as they stand in front.
Synthetic frames first (made-up coordinates in the gantry's layout: banner along x, lettering on its -z side); then the ROM
(no build) and the seven-course set (one build per session, shared with tests/test_tgp_build.py)."""
import math
import struct
from types import SimpleNamespace

import pytest

from vrtools.arcade import gantry as g
from vrtools.arcade.polyrom import Quad, decode_object, encode_object, quads as decoded_quads

# --- synthetic frames ---------------------------------------------------------------------------------------------------
STRIPS = [(-8.0, -4.0), (-4.0, 0.0), (0.0, 4.0), (4.0, 8.4)]   # the banner's strips (x ends); its centre 0.2, off the posts' axis
Y0, Y1 = 8.0, 12.0
DEPTH = 0.8                                                    # the letters stand this far in front (-z) of the banner
# an asymmetric glyph: an "L" (stem and a foot to the right) on the left, a dot high on the right
LETTERS = [(-6.0, -5.2, 8.8, 11.3), (-5.2, -3.0, 8.8, 9.5), (3.0, 3.8, 10.6, 11.3)]   # the stem 2.5 tall, as the tallest letter


def _wave(x, phase):
    """The banner's depth along x: straight on each strip between its ends, which follow a wave (a bent, flat-stripped banner)."""
    ends = [STRIPS[0][0]] + [b for _, b in STRIPS]
    k = max(0, min(len(ends) - 2, sum(1 for e in ends[1:-1] if x >= e)))
    (xa, xb) = ends[k], ends[k + 1]
    za, zb = (phase * (0.6 * math.sin(e / 3.0) + 0.02 * e) for e in (xa, xb))
    return za + (zb - za) * (x - xa) / (xb - xa)


def _zb(x, y, phase):
    return _wave(x, phase) + 0.01 * (y - Y0)                  # a slight lean with height, as the gantry's strips


def _upright(x0, x1, y0, y1, z, normal):
    """A rectangle wound so its first three corners' right-hand normal points -z (drawn from the front, as the ROM's)."""
    return Quad(((x0, y0, z(x0, y0)), (x0, y1, z(x0, y1)), (x1, y1, z(x1, y1)), (x1, y0, z(x1, y0))), normal, 0x5601, 0)


def synthetic_frame(phase):
    """Posts standing still at x = ±10, the banner's strips and the letters waving with it; tex entries 0x50000..: one a quad."""
    qs = [_upright(-10.3, -9.7, 0.0, 12.5, lambda x, y: -0.25, (0.0, 0.0, 1.0)),
          _upright(9.7, 10.3, 0.0, 12.5, lambda x, y: -0.25, (0.0, 0.0, 1.0))]
    qs += [_upright(a, b, Y0, Y1, lambda x, y: _zb(x, y, phase), (0.0, 0.0, 1.0)) for a, b in STRIPS]
    qs += [_upright(*r, lambda x, y: _zb(x, y, phase) - DEPTH, (0.0, 0.1, 1.0)) for r in LETTERS]
    return [Quad(q.p, q.normal, q.flags, 0x50000 + i) for i, q in enumerate(qs)]


PHASES = (1.0, 0.0, -1.0, 0.5)


def _rh(p):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = p[0], p[1], p[2]
    u, v = (bx - ax, by - ay, bz - az), (cx - ax, cy - ay, cz - az)
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def test_the_parts_are_the_waving_banner_and_its_lettering():
    p = g.gantry_parts([synthetic_frame(ph) for ph in PHASES])
    assert p.banner == (2, 3, 4, 5)                           # the posts stand still: not the banner
    assert p.letters == (6, 7, 8) and p.front == -1


def test_no_parts_without_one_shape_or_with_lettering_on_both_sides():
    frames = [synthetic_frame(ph) for ph in PHASES]
    with pytest.raises(g.GantryError):
        g.gantry_parts([frames[0], frames[1][:-1]])           # a quad fewer in one frame
    flipped = []
    for f in frames:
        q = f[8]
        flipped.append(f[:8] + [Quad(tuple((x, y, z + 2 * DEPTH) for x, y, z in q.p), q.normal, q.flags, q.tex_adr)])
    with pytest.raises(g.GantryError):
        g.gantry_parts(flipped)                               # the dot behind the banner, the L in front
    still = [synthetic_frame(0.0)] * 2
    with pytest.raises(g.GantryError):
        g.gantry_parts(still)                                 # nothing waves: no banner


def test_a_letter_left_out_of_the_lettering_is_refused():
    """A letter outside the depth window in every frame (the dot 2.6 units in front of the banner) is not found as lettering;
    the cross-check on the letters' colour word names it and the frame instead of leaving it without a copy."""
    frames = []
    for ph in PHASES:
        f = synthetic_frame(ph)
        q = f[8]
        frames.append(f[:8] + [Quad(tuple((x, y, z - 1.8) for x, y, z in q.p), q.normal, q.flags, q.tex_adr)])
    p = g.gantry_parts(frames)
    assert p.letters == (6, 7)                                # found without the dot ...
    colour = lambda tex: 2 if tex - 0x50000 in (6, 7, 8) else 0x7FFF
    with pytest.raises(g.GantryError, match=r"frame 0: quads \[8\]"):
        g.check_lettering(frames, p, colour)                  # ... and refused
    good = [synthetic_frame(ph) for ph in PHASES]
    assert g.check_lettering(good, g.gantry_parts(good), colour) == 2


@pytest.mark.parametrize("phase", PHASES)
def test_each_copy_is_the_letter_mirrored_behind_that_frames_banner(phase):
    f = synthetic_frame(phase)
    p = g.gantry_parts([synthetic_frame(ph) for ph in PHASES])
    copies = g.mirrored_letters(f, p, 0x51000)
    c = (STRIPS[0][0] + STRIPS[-1][1]) / 2
    assert len(copies) == 3
    for i, cp in zip(p.letters, copies):
        assert cp.one_sided and not cp.flags & 0x4000 and cp.tex_adr == 0x51000
        nx, ny, nz = f[i].normal
        assert cp.normal == (-nx, ny, -nz)                    # turned half round: away from the side it is seen from
        for (x, y, z), (x2, y2, z2) in zip(f[i].p, cp.p):     # the corner order kept
            assert x2 == pytest.approx(2 * c - x) and y2 == y
            assert z2 - _zb(x2, y2, phase) == pytest.approx(_zb(x, y, phase) - z, abs=1e-6)   # as far behind as the letter in front


def _seen(points, behind):
    """A face as its viewer sees it, translated to its first corner: (screen right, up) from the front is (x, y) in the frame of a
    viewer on the -z side; the viewer behind the banner is the same viewer turned half round, whose right is -x."""
    faces = [points] if isinstance(points[0][0], float) else points
    pts = [[(-x if behind else x, y) for x, y, _ in face] for face in faces]
    u0, v0 = pts[0][0]
    return [[(round(u - u0, 5), round(v - v0, 5)) for u, v in face] for face in pts]


@pytest.mark.parametrize("phase", PHASES)
def test_the_copies_read_from_behind_as_the_letters_from_the_front(phase):
    """Handedness: seen from behind, the copies are the picture the letters show from the front, each face wound the same way
    and the faces in the same places (the L's foot to the viewer's right of its stem, the dot to the right of the L), so the
    text reads from both sides. A mirror across the banner alone (depth reflected, x kept, the corners reversed to face the
    back) gives the mirrored picture and fails here."""
    f = synthetic_frame(phase)
    p = g.gantry_parts([synthetic_frame(ph) for ph in PHASES])
    copies = g.mirrored_letters(f, p, 0)
    letters = [f[i].p for i in p.letters]
    assert _seen([cp.p for cp in copies], behind=True) == _seen(letters, behind=False)
    wrong = [tuple((x, y, 2 * _zb(x, y, phase) - z) for x, y, z in reversed(q)) for q in letters]
    assert _seen(wrong, behind=True) != _seen(letters, behind=False)
    for cp, q in zip(copies, letters):                       # each face on its own too: the same corners, the same winding
        assert _seen(cp.p, behind=True) == _seen(q, behind=False)


def _rom(frames):
    """A stand-in RomSet holding the frames' objects (encode_object, two-sided as the ROM's) one after the other: (rs, records)."""
    blob, recs = b"", []
    for f in frames:
        b, lay = encode_object(f, f[0].tex_adr, no_cull=True)
        recs.append((len(blob) // 4, f[0].tex_adr, lay.record_count))
        blob += b
    return SimpleNamespace(polygons=blob), recs


def test_a_frames_object_is_its_records_then_the_copies_drawn_from_behind_only():
    frames = [synthetic_frame(ph) for ph in PHASES]
    rs, recs = _rom(frames)
    decoded = [g.frame_quads(rs, r) for r in recs]
    p = g.gantry_parts(decoded)
    poly, tex, size = recs[1]
    last = max(q.tex_adr for q in decoded[1])
    copies = g.mirrored_letters(decoded[1], p, last + 1)
    blob, new_size = g.frame_object(rs, recs[1], copies)
    assert new_size == size + 2 * len(copies)
    assert blob[:4 * (6 + 10 * size)] == rs.polygons[4 * poly:4 * (poly + 6 + 10 * size)]     # the frame's own bytes unchanged
    assert blob[-40:] == bytes(40)                                                            # an end marker
    obj = decode_object(blob, 0, new_size)
    assert len(obj.records) == new_size and struct.unpack_from("<I", blob, 4 * (6 + 10 * new_size))[0] & 3 == 0   # the size is honest
    qs = decoded_quads(obj, tex)
    assert qs[:len(decoded[1])] == decoded[1]
    drawn = qs[len(decoded[1]):]
    assert len(drawn) == len(copies)
    for d, cp, i in zip(drawn, copies, p.letters):
        assert not d.flags & 0x4000 and d.tex_adr == last + 1                                 # back-face tested, the copies' entry
        assert {tuple(round(v, 4) for v in pt) for pt in d.p} == {tuple(round(v, 4) for v in pt) for pt in cp.p}
        assert _rh(d.p)[2] > 0 and _rh(decoded[1][i].p)[2] < 0                                # drawn from behind (+z); the letter from the front
        assert d.flags & 0xC00 == decoded[1][i].flags & 0xC00                                 # sorted as the letters (their z mode)
    assert sum(1 for r in obj.records if r.tex_advance) == sum(1 for r in decode_object(rs.polygons, poly, size).records if r.tex_advance) + 1


# --- the ROM (no build) -------------------------------------------------------------------------------------------------

def test_the_arcade_gantry_is_32_waving_frames(romset_zip):
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.directory import ORIGINALS
    from vrtools.arcade.spawn import START_GANTRY, decode_spawn_list
    rs = RomSet.from_zip(romset_zip)
    assert {e.objlist for o in ORIGINALS for e in decode_spawn_list(rs, o.spawn_table) if e.handler == START_GANTRY} == {g.START_GANTRY_OBJECTS}
    recs = g.frame_records(rs)
    assert len({r[0] for r in recs}) == g.FRAMES and {r[2] for r in recs} == {141}
    p = g.gantry_parts([g.frame_quads(rs, r) for r in recs])
    assert len(p.banner) == 26 and len(p.letters) == 23 and p.front == -1


def test_the_install_writes_erased_rom_only(romset_zip):
    """On the original set: the install changes polygon ROM only where it was erased (the 32 objects), the program ROM only in its
    block, and nothing else (the TGP data ROM, the collision's, among them)."""
    import numpy as np
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.tencourse import start_gantry_address
    rs = RomSet.from_zip(romset_zip)
    out = RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
    inst = g.install_start_gantry(out, start_gantry_address())
    assert (out.boot, out.data, out.copro_data, out.tgp_program) == (rs.boot, rs.data, rs.copro_data, rs.tgp_program)
    a, b = np.frombuffer(rs.program, np.uint8), np.frombuffer(out.program, np.uint8)
    diff = np.flatnonzero(a != b) + 0x200000
    assert len(diff) and inst.address <= diff.min() and diff.max() < inst.address + g.BLOCK_BYTES
    a, b = np.frombuffer(rs.polygons, np.uint8), np.frombuffer(out.polygons, np.uint8)
    diff = np.flatnonzero(a != b)
    assert (a[diff] == 0xFF).all() and len(diff) <= inst.object_bytes
    assert inst.size == 141 + 2 * 23 and inst.letters == 23 and inst.entries == 142


# --- the seven-course set -----------------------------------------------------------------------------------------------

def test_nothing_of_the_arcades_gantry_changes(romset_zip, saturn_cue):
    """The 32 arcade objects, their list and records and the originals' spawn lists keep their bytes in the built set."""
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.directory import ORIGINALS
    from vrtools.arcade.spawn import decode_spawn_list
    from tests.test_tgp_build import _seven
    rs = RomSet.from_zip(romset_zip)
    out, _ = _seven(romset_zip, saturn_cue)
    assert out.read_v60(g.START_GANTRY_OBJECTS, 4 * g.FRAMES) == rs.read_v60(g.START_GANTRY_OBJECTS, 4 * g.FRAMES)
    for k, (poly, tex, size) in enumerate(g.frame_records(rs)):
        rec = struct.unpack("<I", rs.read_v60(g.START_GANTRY_OBJECTS + 4 * k, 4))[0]
        assert out.read_v60(rec, g.RECORD_BYTES) == rs.read_v60(rec, g.RECORD_BYTES)
        end = 4 * (poly + 6 + 10 * size) + 4                                       # with the end marker's flags word
        assert out.polygons[4 * poly:end] == rs.polygons[4 * poly:end], k
    for o in ORIGINALS:
        assert decode_spawn_list(out, o.spawn_table) == decode_spawn_list(rs, o.spawn_table), o.name
    from vrtools.arcade.colours import colour_table
    t_rs, t_out = colour_table(rs), colour_table(out)
    for _, tex, _ in g.frame_records(rs):                                           # the arcade's colour entries, every frame's run
        assert [t_out.entry(tex + i) for i in range(1, 142)] == [t_rs.entry(tex + i) for i in range(1, 142)]


def test_the_converted_start_gantries_draw_their_own_frames(romset_zip, saturn_cue):
    """The courses that keep the host's start gantry (Alpine, Diablo Canyon, Pacific Coast) name the new list; each frame is
    the arcade's records unchanged, then 23 one-sided copies on the run's last entry; the run repeats the arcade's entries."""
    from vrtools.arcade.colours import colour_table
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.spawn import START_GANTRY, decode_spawn_list
    from vrtools.arcade.tencourse import start_gantry_address
    from tests.test_tgp_build import _seven
    rs = RomSet.from_zip(romset_zip)
    out, conv = _seven(romset_zip, saturn_cue)
    at = start_gantry_address()
    lists = {}
    for e in decode_directory(out)[3:10]:
        lists[e.name] = [x.objlist for x in decode_spawn_list(out, e.spawn_table) if x.handler == START_GANTRY]
    assert lists == {"ALPINE": [at], "AMAZON FALLS": [], "DIABLO CANYON": [at], "METROPOLIS": [], "PACIFIC COAST": [at],
                     "SURFERS OVAL": [], "SURFERS ROAD": []}
    assert {c.entry.name: c.report["start_gantry_list"] for c in conv if c.report["start_gantry_list"]} == {
        n: at for n in ("ALPINE", "DIABLO CANYON", "PACIFIC COAST")}
    old, new = g.frame_records(rs), g.frame_records(out, at)
    t_old, t_new = colour_table(rs), colour_table(out)
    assert len({tex for _, tex, _ in new}) == 1                                     # one colour run for all frames
    tex = new[0][1]
    for (op, otex, osize), (np_, ntex, nsize) in zip(old, new):
        assert nsize == osize + 2 * 23
        n = 4 * (6 + 10 * osize)
        assert out.polygons[4 * np_:4 * np_ + n] == rs.polygons[4 * op:4 * op + n]   # the frame's own records, unchanged
        obj = decode_object(out.polygons, np_, nsize)
        assert struct.unpack_from("<I", out.polygons, 4 * (np_ + 6 + 10 * nsize))[0] & 3 == 0   # the size counts every record
        drawing = [r for r in obj.records[osize:] if r.link]
        assert len(drawing) == 23 and not any(r.no_cull for r in drawing)
        assert all(r.no_cull for r in obj.records[:osize])
        assert [t_new.entry(tex + i) for i in range(1, 142)] == [t_old.entry(otex + i) for i in range(1, 142)]
    letter = {t_old.entry(q.tex_adr) for q in g.frame_quads(rs, old[0])[94:117]}
    assert [t_new.entry(tex + 142)] == list(letter)


def test_the_gantry_block_lies_in_erased_code_room_outside_the_annex(romset_zip, saturn_cue):
    """The block's bounds: the top BLOCK_BYTES of the code area (CODE_FREE), above the fixed layout's last spawn list, erased in
    the original; claimed by no other writer (the reverse annex's regions end at or below it, the pictures' free-run search
    leaves it out); apart from the annex; and in the set holding the list and colour run as written, its tail still erased."""
    from vrtools.arcade.course import CODE_FREE
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.race import RACE_BLOB_BYTES
    from vrtools.arcade.romset import V60_PROGRAM, RomSet
    from vrtools.arcade.spawn import SPAWN_LIST_BYTES
    from vrtools.arcade.tencourse import MAX_ENTITIES, NEW_COURSES, spawn_list_address, start_gantry_address
    from tests.test_tgp_build import _seven
    rs = RomSet.from_zip(romset_zip)
    out, _ = _seven(romset_zip, saturn_cue)
    lo = start_gantry_address()
    hi = lo + g.BLOCK_BYTES
    assert hi == CODE_FREE[0] + CODE_FREE[1]
    assert lo >= spawn_list_address(NEW_COURSES - 1) + SPAWN_LIST_BYTES(MAX_ENTITIES)
    assert set(rs.program[lo - V60_PROGRAM:hi - V60_PROGRAM]) == {0xFF}
    rec = [e.reverse for e in decode_directory(out)[3:10]]
    alo, ahi = min(r.at for r in rec), max(r.entry.race for r in rec) + RACE_BLOB_BYTES
    assert ahi <= lo or hi <= alo
    from vrtools.arcade.picture import free_runs
    from vrtools.arcade.tencourse import annex_regions, picture_exclusions
    assert all(b <= lo or a >= hi for a, b in annex_regions())                     # no annex region reaches into the block
    assert annex_regions()[0][1] <= lo
    for a, n in free_runs(rs, picture_exclusions()):                                # the pictures are never offered it, even
        assert a + n <= lo or a >= hi, (hex(a), n)                                  # where it is erased (the original set)
    used = g.LIST_BYTES + 2 * (1 + 142)                                             # the run: its base entry, then 142
    block = out.program[lo - V60_PROGRAM:hi - V60_PROGRAM]
    assert set(block[used:]) == {0xFF} and block[g.LIST_BYTES:g.LIST_BYTES + 2] == b"\xff\xff"   # the run's unread base entry left erased
    ptrs = struct.unpack_from(f"<{g.FRAMES}I", block)
    assert ptrs == tuple(lo + 4 * g.FRAMES + g.RECORD_BYTES * k for k in range(g.FRAMES))


def test_install_pictures_leaves_out_the_picture_exclusions(romset_zip, monkeypatch):
    """`install_pictures` hands `picture_exclusions()` to the pictures' free-run search, so the start-gantry block (and the
    directory image) are never offered to a picture. Behavioural: `picture_exclusions` is replaced by a sentinel and the search
    records what it was given, then stops the install."""
    from vrtools.arcade import tencourse
    from vrtools.arcade.romset import RomSet

    sentinel = [(0x2ABCD0, 0x40)]
    seen = []

    class Searched(Exception):
        pass

    def search(rs, exclude, *args, **kwargs):
        seen.append(exclude)
        raise Searched

    monkeypatch.setattr(tencourse, "picture_exclusions", lambda: sentinel)
    monkeypatch.setattr(tencourse, "free_runs", search)
    with pytest.raises(Searched):
        tencourse.install_pictures(RomSet.from_zip(romset_zip), [], [])
    assert seen == [sentinel]
