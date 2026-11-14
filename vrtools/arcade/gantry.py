"""Phase 26 stage 2 (Task 11): the converted courses' own copy of the arcade's start gantry, its lettering readable from behind.

The arcade's start gantry (spawn-list handler 0xffb07f; `docs/formats/model1-course-tables.md` §12) waves: each time it is
drawn (boot 0xffb0dc..0xffb25f) it hands `0xff84a2` frame `counter & 31` (entity +0x1c, incremented after each draw) of its
object list, 32 pointers (boot 0xfdc033) to records `(poly, tex, size)` each followed by a zero word (`0xff84a2` reads triples
until poly is 0; `size` only adds to the frame's record count at 0x5011a0, the renderer reads to the end marker). Each frame is
a polygon-ROM object of 141 records (117 quads): two posts, a white banner of narrow strips that swings 2.4 units fore and aft
over the cycle, and 23 red letter quads ("START") whose corners stand 0.52-1.18 units in front of its surface, every record two-sided. Seen from behind, the
letters are farther than the banner and its strips cover them in the painter's sort: a blank striped banner (the owner's
report on reverse Alpine and Diablo Canyon). The originals and the attract mode draw the same list.

Here (option B, the owner's choice), at build time: each frame read from the ROM, its records copied unchanged, followed by its
letters mirrored left to right about the banner's centre and standing as far behind that frame's banner as they stand in front
(`gates.mirror_behind`, Task 9's copy, following the banner's strips under each corner), one-sided and facing backwards; the 32
objects in free polygon ROM; a new list with its records and one colour run (the frames' entries, the same in every frame, then
the copies' entry) in a reserved block (`tencourse.start_gantry_address`); the converted courses' start-gantry entity names the
new list. Nothing of the arcade's own is written."""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from vrtools.arcade.colours import TABLE_BASE, colour_table
from vrtools.arcade.patch import Allocator, PatchError, poly_free_runs, write_colour_entries, write_polygons, write_program_blob
from vrtools.arcade.polyrom import Quad, _one_sided_corners, _pack_record, decode_object, quads
from vrtools.arcade.romset import V60_PROGRAM, RomSet
from vrtools.convert.gates import mirror_behind

START_GANTRY_OBJECTS = 0xFDC033   # boot ROM: the start gantry's object list in all three originals' spawn lists
FRAMES = 32                       # the handler takes frame (counter & 0x1f)
RECORD_BYTES = 16                 # (poly, tex, size) and the zero word that ends 0xff84a2's walk
LIST_BYTES = FRAMES * (4 + RECORD_BYTES)   # the 32 pointers, then the 32 records
BLOCK_BYTES = 1024                # the reserved block: the list (640 bytes), then the colour run (2 bytes an entry: 286 bytes)
BANNER_MIN_HEIGHT = 3.0           # arcade units: a banner strip is 3.8 tall (y 8.7-12.5); the tallest letter 2.5
MOVE_EPS = 0.01                   # a quad that moves more than this over the frames waves with the banner (the posts stand still)
LETTER_DEPTH = (0.25, 2.0)        # a letter stands this far in front of the banner at every corner (measured 0.52-1.18: each
                                  # corner's distance in front of the banner's surface under it, over the 32 frames)
_EPS = 0.05                       # the letters lie inside the banner's x and y span within this
_UPRIGHT = 0.75                   # |stored normal y| below this: upright (the S's lower bar leans to 0.51; the posts' caps are 1)


class GantryError(PatchError):
    pass


def frame_records(rs: RomSet, objects: int = START_GANTRY_OBJECTS) -> list[tuple[int, int, int]]:
    """The (poly word, tex, size) of each of the 32 frames of the object list at `objects`."""
    out = []
    for k in range(FRAMES):
        rec = struct.unpack("<I", rs.read_v60(objects + 4 * k, 4))[0]
        poly, tex, size, end = struct.unpack("<4I", rs.read_v60(rec, RECORD_BYTES))
        if end or not poly or not size or poly & 0x800000:
            raise GantryError(f"frame {k}: record {rec:#x} is not one (poly, tex, size) then 0: {poly:#x} {tex:#x} {size} {end:#x}")
        out.append((poly, tex, size))
    return out


def frame_quads(rs: RomSet, rec: tuple[int, int, int]) -> list[Quad]:
    poly, tex, size = rec
    return quads(decode_object(rs.polygons, poly, size), tex)


def _height(q: Quad) -> float:
    ys = [p[1] for p in q.p]
    return max(ys) - min(ys)


class Surface:
    """The banner's surface z(x, y) over its strips: each banner quad split into two triangles in the (x, y) plane, z
    interpolated over the triangle holding (x, y) (or, outside every triangle, extrapolated over the nearest)."""

    def __init__(self, qs: list[Quad]):
        self.tris = []
        for q in qs:
            for a, b, c in ((q.p[0], q.p[1], q.p[2]), (q.p[0], q.p[2], q.p[3])):
                det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
                if abs(det) > 1e-9:
                    self.tris.append((a, b, c, det))
        if not self.tris:
            raise GantryError("the banner has no surface")
        xs = [p[0] for q in qs for p in q.p]
        ys = [p[1] for q in qs for p in q.p]
        self.x0, self.x1, self.y0, self.y1 = min(xs), max(xs), min(ys), max(ys)

    def __call__(self, x: float, y: float) -> float:
        best = None
        for a, b, c, det in self.tris:
            u = ((b[0] - x) * (c[1] - y) - (c[0] - x) * (b[1] - y)) / det
            v = ((c[0] - x) * (a[1] - y) - (a[0] - x) * (c[1] - y)) / det
            w = 1.0 - u - v
            worst = min(u, v, w)
            if best is None or worst > best[0]:
                best = (worst, u * a[2] + v * b[2] + w * c[2])
            if worst >= -1e-9:
                break
        return best[1]


def _moving(frames: list[list[Quad]]) -> list[bool]:
    """Per quad index: it moves more than MOVE_EPS over the frames."""
    return [max(math.dist(a, b) for f in frames for a, b in zip(frames[0][i].p, f[i].p)) > MOVE_EPS for i in range(len(frames[0]))]


@dataclass(frozen=True)
class Parts:
    banner: tuple[int, ...]       # quad indices (as `quads` lists them) of the banner's strips
    letters: tuple[int, ...]      # of the lettering
    front: int                    # -1: the letters stand on the banner's -z side (the side they read from), +1: on its +z side


def gantry_parts(frames: list[list[Quad]]) -> Parts:
    """The banner (the upright quads at least BANNER_MIN_HEIGHT tall that move over the frames: the posts stand still) and the
    lettering (the other moving upright quads inside the banner's x and y span, standing LETTER_DEPTH in front of it at every
    corner, all on one side), the same quads in every frame. GantryError when the frames differ in shape or a frame has no
    banner, no lettering or lettering on both sides."""
    n = len(frames[0])
    if any(len(f) != n for f in frames):
        raise GantryError("the frames differ in their number of quads")
    moving = _moving(frames)
    upright = [all(abs(f[i].normal[1]) < _UPRIGHT for f in frames) for i in range(n)]
    banner = tuple(i for i in range(n) if moving[i] and upright[i] and min(_height(f[i]) for f in frames) >= BANNER_MIN_HEIGHT)
    if not banner:
        raise GantryError("no banner: no tall upright quad moves")
    found = set()
    for f in frames:
        zb = Surface([f[i] for i in banner])
        letters, sides = [], set()
        for i in range(n):
            if i in banner or not (moving[i] and upright[i]):
                continue
            pts = f[i].p
            if any(not (zb.x0 - _EPS <= x <= zb.x1 + _EPS and zb.y0 - _EPS <= y <= zb.y1 + _EPS) for x, y, _ in pts):
                continue
            d = [zb(x, y) - z for x, y, z in pts]                  # > 0: on the banner's -z side
            lo, hi = LETTER_DEPTH
            if all(lo <= v <= hi for v in d):
                sides.add(-1)
            elif all(lo <= -v <= hi for v in d):
                sides.add(1)
            else:
                continue
            letters.append(i)
        if not letters or len(sides) != 1:
            raise GantryError(f"a frame has {len(letters)} lettering quads on {len(sides)} sides")
        found.add((tuple(letters), sides.pop()))
    if len(found) != 1:
        raise GantryError("the lettering is not the same quads in every frame")
    letters, front = found.pop()
    return Parts(banner, letters, front)


def check_lettering(frames: list[list[Quad]], parts: Parts, colour) -> int:
    """The lettering found is all of it: every quad that moves with the banner and has a letter's colour word (`colour(tex)`)
    is among `parts.letters` in every frame (a letter outside LETTER_DEPTH would otherwise be left out without a copy).
    Returns the letters' one colour word; GantryError naming the frame and the quads otherwise."""
    words = {colour(f[i].tex_adr) for f in frames for i in parts.letters}
    if len(words) != 1:
        raise GantryError(f"the lettering reads {len(words)} colour words")
    word = words.pop()
    moving = _moving(frames)
    for k, f in enumerate(frames):
        missed = [i for i in range(len(f)) if moving[i] and i not in parts.letters and colour(f[i].tex_adr) == word]
        if missed:
            raise GantryError(f"frame {k}: quads {missed} move with the banner in the lettering's colour but are not lettering "
                              f"(outside {LETTER_DEPTH} in front of the banner or its span)")
    return word


def mirrored_letters(qs: list[Quad], parts: Parts, tex: int) -> list[Quad]:
    """One frame's letters mirrored left to right about the banner's centre and standing as far behind its banner as they stand
    in front (`gates.mirror_behind`, each corner over the strip under it), one-sided, on colour entry `tex`. The corner order is
    kept (the face turned half round: readable from behind, its first three corners' right-hand normal turned with it, so it is
    drawn from behind only) and the stored normal is the letter's turned half round, (-nx, ny, -nz): away from the side it is
    seen from, the originals' convention (the letter's own points away from the front)."""
    zb = Surface([qs[i] for i in parts.banner])
    centre = (zb.x0 + zb.x1) / 2
    out = []
    for i in parts.letters:
        q = qs[i]
        nx, ny, nz = q.normal
        out.append(Quad(mirror_behind(q.p, centre, zb), (-nx, ny, -nz), q.flags & ~0x4000, tex, one_sided=True))
    return out


_KEEP = ~(0x4000 | 0x1000 | 0x300 | 0x3)   # a copy's records keep the letter's other flag bits (z mode, light): sorted and lit as it


def copy_records(copies: list[Quad], advance: bool = True) -> bytes:
    """The copies as records appended to a frame: each a chain of its own, a link-0 record setting the old edge (its corners 1,
    0) and a link-2 record drawing (0, 1, 2, 3), back-face tested (bit 14 clear); `polyrom._one_sided_corners` makes the first
    three corners distinct. With `advance` the first record moves to the next colour entry (the copies' one entry)."""
    out = b""
    for k, q in enumerate(copies):
        if q.tex_adr != copies[0].tex_adr:
            raise GantryError("the copies read more than one colour entry")
        d = _one_sided_corners(tuple(q.p))
        base = q.flags & _KEEP
        out += _pack_record(base | 0x1 | (0x1000 if advance and k == 0 else 0), q.normal, d[1], d[0])
        out += _pack_record(base | 0x1 | (2 << 8), q.normal, d[2], d[3])
    return out


END_MARKER = _pack_record(0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def frame_object(rs: RomSet, rec: tuple[int, int, int], copies: list[Quad]) -> tuple[bytes, int]:
    """A frame's new object: its seed and records copied unchanged from the ROM, the copies' records, an end marker; and its
    record count (the record's size)."""
    poly, _, size = rec
    body = rs.polygons[4 * poly:4 * (poly + 6 + 10 * size)]
    if struct.unpack_from("<I", rs.polygons, 4 * (poly + 6 + 10 * size))[0] & 3:
        raise GantryError(f"the frame at {poly:#x} does not end after its {size} records")
    return body + copy_records(copies) + END_MARKER, size + 2 * len(copies)


@dataclass(frozen=True)
class Installed:
    address: int                  # program ROM: the list (32 pointers, then the 32 records), then the colour run
    objects: tuple[int, ...]      # polygon-ROM word address of each frame's new object
    object_bytes: int
    tex: int                      # the colour run's base entry (every frame's tex; never read, left erased)
    entries: int                  # entries written from tex + 1: the frames' (141), then the copies' (1)
    size: int                     # records in each new object (the frame's and the copies')
    letters: int                  # lettering quads copied per frame


def install_start_gantry(rs: RomSet, address: int, objects: int = START_GANTRY_OBJECTS) -> Installed:
    """Write the gantry's new frames into free polygon ROM (first fit over `patch.poly_free_runs`), their list and records at
    program-ROM `address` and the colour run right after them (`rs` is written in place; every target must be erased).
    GantryError when the frames do not share one colour pattern or the copies more than one colour."""
    recs = frame_records(rs, objects)
    frames = [frame_quads(rs, r) for r in recs]
    parts = gantry_parts(frames)
    table = colour_table(rs)
    objs = [decode_object(rs.polygons, p, s) for p, _, s in recs]
    if not all(o.records[0].tex_advance for o in objs):
        raise GantryError("a frame's first record reads its tex base entry")
    advances = {sum(r.tex_advance for r in o.records) for o in objs}
    if len(advances) != 1:
        raise GantryError(f"the frames read different numbers of colour entries: {sorted(advances)}")
    n = advances.pop()
    runs = {tuple(table.entry(t + i) for i in range(1, n + 1)) for _, t, _ in recs}     # the entries a frame reads: tex+1..tex+n
    if len(runs) != 1:
        raise GantryError(f"{len(runs)} colour patterns over the frames")
    words = list(runs.pop()) + [check_lettering(frames, parts, table.entry)]
    if LIST_BYTES + 2 * (1 + len(words)) > BLOCK_BYTES or address % 16:
        raise GantryError(f"the list and {len(words)} colour entries do not fit the {BLOCK_BYTES}-byte block at {address:#x}")
    tex = TABLE_BASE + (address + LIST_BYTES - V60_PROGRAM) // 2     # the run's base entry: never read (each frame's first record
                                                                     # advances), left erased; the frames' entries from tex + 1
    alloc = Allocator(poly_free_runs(rs))
    placed, total, size = [], 0, None
    for r, qs in zip(recs, frames):
        blob, size = frame_object(rs, r, mirrored_letters(qs, parts, tex + n + 1))
        placed.append(write_polygons(rs, blob, alloc.alloc(len(blob), align=4, unit="bytes")))
        total += len(blob)
    first = address + 4 * FRAMES
    lst = struct.pack(f"<{FRAMES}I", *(first + RECORD_BYTES * k for k in range(FRAMES)))
    lst += b"".join(struct.pack("<4I", w, tex, size, 0) for w in placed)
    write_program_blob(rs, address, lst)
    write_colour_entries(rs, {tex + 1 + i: w for i, w in enumerate(words)})
    return Installed(address, tuple(placed), total, tex, len(words), size, len(parts.letters))
