"""Phase 90: a pack is a plan for the set's seven converted menu slots (design docs/superpowers/specs/2026-11-26-ps2-pack-design.md).

Pack 1 ("saturn", "Virtua Racing Extended") is the released set: the seven Saturn courses of `tencourse.COURSES`, ten entries on
the wheel, the start gantry's frames copied whole, the battery RAM magic `ranking.NEW_MAGIC`. `vrtools build` makes it byte for
byte as before, through `tencourse.build_all` (not `build_pack`); tests/test_pack1_identity.py holds it to the released digests.

Pack 2 ("ps2", "Virtua Racing Extended: PS2 Tracks") holds the arcade's three courses and the PS2 game's three (Sega Ages 2500
Vol. 8: Virtua Racing FlatOut, the Japanese release), each at the best detail the frame allows (`Ps2Plan.tiers`, note §13), on a
six-entry wheel: Island (bank 1, pit stop), Mountain (bank 2), Beltway (bank 1); slots 7-10 are hidden copies of Beltway (no
Saturn course fits beside them). Its spare polygon ROM comes first from the start gantry stored as the arcade's own frames plus a
small lettering object each (`gantry="lettering"`); its battery RAM magic is its own, so a battery RAM saved by the other pack is
cleared at boot instead of showing times under the wrong course (its run line names its own battery RAM folder).

A slot is a `Ps2Plan` (`ps2entry.convert_ps2_course`) or a `Hidden` copy of an earlier slot (pack 1's are `tencourse.CoursePlan`)."""
from __future__ import annotations

from dataclasses import dataclass, replace

from vrtools.arcade.ranking import NEW_MAGIC
from vrtools.arcade.select import MENU
from vrtools.arcade.tencourse import BANK_ONE_GRID, BANK_ONE_PAIRS, COURSES, NEW_COURSES, CoursePlan  # noqa: F401

TEMPLATE_OF_BANK = {1: 0, 2: 1, 3: 2}                        # data bank -> its host's data index (0 Bay Bridge, 1 Acropolis, 2 Big Forest)
PACK2_MAGIC = b"S-RAM CHECK OK P2\x00"      # pack 2's battery RAM magic (pack 1: ranking.NEW_MAGIC, "S-RAM CHECK OK 10")


class PackError(ValueError):
    pass


@dataclass(frozen=True)
class Ps2Plan:
    """Where a PS2 course goes and how much of it: `index` is its number on the disc (`vrtools.ps2.course.COURSES`); bank, TGP slot,
    template (the bank's host) and label as a CoursePlan's. The detail: upright faces within `upright_keep` of the road never
    thinned (the roadside), every face beyond `far_cut` dropped (None: none), each structure's coplanar faces merged (`merge`;
    `windows`: the window bands folded into their wall's colour), the one-player mesh within `near_detail` of the road (None: the
    split-screen mesh everywhere), far silhouettes within `far_budget` bytes (0: none). `pit`: the PS2's pit lane as a pit stop
    (both directions: the reverse pair and box by the Saturn path's rule, `ps2entry.reverse_pit_of`). Tunnel and overpass
    stretches are always flagged (the tunnel sound; the storm's cover)."""
    index: int
    name: str
    bank: int
    tgp_slot: int
    template: int
    label: int
    laps: int = 5
    time_factor: float = 1.0
    pace: float = 1.0
    reverse: bool = True
    reverse_pairs: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7)
    reverse_grid: tuple[int, ...] | None = None
    pit: bool = False
    upright_keep: float = 60.0
    far_cut: float | None = None
    merge: bool = True
    windows: bool = False
    near_detail: float | None = None
    far_budget: int = 0
    tiers: tuple = ()                   # richer details, richest first: each (near_detail, far_cut, windows); with `frame_records`
                                        # every tile cell takes the richest tier the frame allows (`ps2entry.graded_cells`)
    frame_records: int | None = None    # scenery records a frame (Phase 28's model, every road point, both ways) never exceeded
    poly_budget: int | None = None      # with `tiers`: the scenery's polygon bytes at most (cells stepped down, the heaviest first)
    frame_cuts: tuple = ()              # with `tiers`: (direction "normal"/"reverse", first, last road point of that direction,
                                        # records) taken off those frames' caps, the farthest cells stepped down first: where MAME
                                        # measured a RAIN frame over the rain's room (tests/test_pack_rate.py's RECORDS_MAX)


@dataclass(frozen=True)
class Hidden:
    """A menu entry past the wheel's last band: a copy of slot `of` (its data, panel and picture), never chosen."""
    of: int


@dataclass(frozen=True)
class Pack:
    name: str
    slots: tuple
    menu: int = MENU                    # entries on the wheel (the slots past it are Hidden)
    gantry: str = "frames"              # "frames": the converted courses' own whole copy of the start gantry (pack 1);
                                        # "lettering": the arcade's frames, each followed by a lettering object (pack 2)
    magic: bytes = NEW_MAGIC
    reserve_weather: bool = False       # the storm's bank-0 blocks kept out of the select panels' and pictures' first fit


def ps2_names(pack: Pack) -> list[str]:
    return [s.name for s in pack.slots if isinstance(s, Ps2Plan)]


def check(pack: Pack) -> Pack:
    """PackError unless the plan can be built: seven slots; unique names and TGP slots (0..15, past the originals' 0..2); each
    course in a bank 1..3 hosted by its template; the Hidden slots last, copying an earlier visible slot, and exactly the slots
    past the wheel; gantry and magic as known."""
    if len(pack.slots) != NEW_COURSES:
        raise PackError(f"{pack.name}: {len(pack.slots)} slots, {NEW_COURSES} needed")
    visible = [s for s in pack.slots if not isinstance(s, Hidden)]
    names = [s.name for s in visible]
    if len(set(names)) != len(names):
        raise PackError(f"{pack.name}: a course twice: {names}")
    slots = [s.tgp_slot for s in visible]
    if len(set(slots)) != len(slots) or not all(3 <= t < 16 for t in slots):
        raise PackError(f"{pack.name}: TGP slots {slots} (unique, 3..15)")
    for s in visible:
        if TEMPLATE_OF_BANK.get(s.bank) != s.template:
            raise PackError(f"{pack.name}: {s.name} in bank {s.bank} with template {s.template} (bank 1 Bay Bridge 0, 2 Acropolis 1, "
                            "3 Big Forest 2)")
    hidden = [k for k, s in enumerate(pack.slots) if isinstance(s, Hidden)]
    if hidden != list(range(pack.menu - 3, NEW_COURSES)):
        raise PackError(f"{pack.name}: hidden slots {hidden} for a wheel of {pack.menu} entries")
    for k in hidden:
        if not (0 <= pack.slots[k].of < pack.menu - 3):
            raise PackError(f"{pack.name}: slot {k} copies slot {pack.slots[k].of}, not a visible one")
    if pack.gantry not in ("frames", "lettering"):
        raise PackError(f"{pack.name}: gantry {pack.gantry!r}")
    if len(pack.magic) != len(NEW_MAGIC) or pack.magic[-1:] != b"\0":
        raise PackError(f"{pack.name}: magic {pack.magic!r}")
    return pack


ISLAND = Ps2Plan(4, "ISLAND", 1, 4, 0, 0, pit=True, reverse_pairs=BANK_ONE_PAIRS, reverse_grid=BANK_ONE_GRID, far_budget=74000)
MOUNTAIN = Ps2Plan(3, "MOUNTAIN", 2, 6, 1, 1, far_budget=57000)
BELTWAY = Ps2Plan(5, "BELTWAY", 1, 9, 0, 2, far_cut=60.0, windows=True, reverse_pairs=BANK_ONE_PAIRS, reverse_grid=BANK_ONE_GRID)

SATURN = check(Pack("saturn", tuple(COURSES)))
# Pack 2 at the best detail the arcade can draw (note §13; the owner: "it would be best to add more polygon for the draw distance
# and side details"): each tile cell takes the richest tier its frames allow (the one-player mesh out to 100 / 60 / 30 units, the
# split-screen mesh as driven last) under the course's records cap (`frame_records`) on Phase 28's model of the scenery records a
# frame at every road point both ways. The caps are MEASURED, not computed: the model's first caps (the as-driven set's measured
# RAIN peak plus the headroom to 10 200: Island 5 287 + 1 770 = 7 057, Mountain 2 641 + 2 242 = 4 883, Beltway 4 981 + 1 279 =
# 6 260) gave RAIN frames of 10 495-10 500 records in MAME, so they were lowered by hand until the RAIN peaks held (note §13.2):
# Island 6 500, Mountain 4 450, Beltway 6 000. The polygon ROM is the next limit: with the PS2 courses at that detail no Saturn
# extra fits, so the wheel has six entries (Beltway first, whole; Island and Mountain share the rest by their asks:
# `poly_budget`).
# Phase 90 (the session lead's ruling on the rain's room): where headless RAIN races measured a frame's records over 10 200
# (tests/test_pack_rate.py), those views' caps are lowered and their farthest cells stepped down first (`frame_cuts`): Beltway
# normal 10 494 at road point 257 and 10 117-10 256 at 183-224 (the city, the first lap's bunched field, the player on the
# right-hand side), reverse 10 144 at 101-112. Island's 10 500 at 152-160 was the scripted car's crash there (lookahead 3), not
# the course: on the test's line it peaks at 9 705 / 9 682, so it keeps its detail; Mountain peaks at 8 693 / 9 262.
# BELTWAY_CUTS and the `frame_records` caps are measured values: a change to the converter, the grading or the tiers invalidates
# them; tests/pack2_cuts.py says how to redo them from a failure of tests/test_pack_rate.py (frame -> road point -> the cells that
# view draws -> the cap to lower).
BELTWAY_CUTS = (("normal", 180, 226, 400), ("normal", 252, 262, 700), ("reverse", 99, 115, 400))
ISLAND_TOP = replace(ISLAND, tiers=((100.0, None, False), (60.0, None, False), (30.0, None, False)), frame_records=6500,
                     poly_budget=930000)
MOUNTAIN_TOP = replace(MOUNTAIN, tiers=((100.0, None, False), (60.0, None, False), (30.0, None, False)), frame_records=4450,
                       poly_budget=1045000)
BELTWAY_TOP = replace(BELTWAY, tiers=((60.0, None, False), (30.0, 100.0, False), (None, 100.0, False)), frame_records=6000,
                      poly_budget=1420000, frame_cuts=BELTWAY_CUTS)
PS2 = check(Pack("ps2", (ISLAND_TOP, MOUNTAIN_TOP, BELTWAY_TOP, Hidden(2), Hidden(2), Hidden(2), Hidden(2)),
                 menu=6, gantry="lettering", magic=PACK2_MAGIC, reserve_weather=True))
PACKS = {"saturn": SATURN, "ps2": PS2}


def _hidden(c, of: int):
    """A Converted for a hidden slot: slot `of`'s entry (its tables, tile table, race blob and spawn list) under `hidden`, without
    a reverse variant or far copies of its own."""
    from dataclasses import replace
    return replace(c, entry=replace(c.entry, hidden=True), reverse=None, far_cells=None,
                   report={**c.report, "hidden_copy_of": 3 + of})


def build_pack(rs, pack: Pack, ps2_disc=None):
    """Every slot of `pack` into `rs` in order, the k-th behind tile table k (`tencourse.build_all`'s steps; a PS2 slot through
    `ps2entry.convert_ps2_course`, read from the disc image `ps2_disc`); then the start gantry the converted courses name (pack 1:
    the frames copied whole; pack 2: the arcade's frames with a lettering object each). Returns (set, converted)."""
    from vrtools.arcade import tencourse as T
    from vrtools.arcade.gantry import install_start_gantry, install_start_lettering
    from vrtools.arcade.ps2entry import convert_ps2_course
    check(pack)
    out, converted = T.install_dirscreen_block(rs), []
    gantry_list = T.start_gantry_address()
    disc = None
    for k, p in enumerate(pack.slots):
        if isinstance(p, Hidden):
            converted.append(_hidden(converted[p.of], p.of))
            continue
        if not isinstance(p, Ps2Plan):                  # pack 1's Saturn courses are built by tencourse.build_all
            raise PackError(f"{pack.name}: slot {k} is not a PS2 course ({type(p).__name__}): build_pack takes PS2 and hidden slots")
        from vrtools.ps2.course import load_from_disc
        from vrtools.ps2.disc import Ps2Disc
        if disc is None:
            if ps2_disc is None:
                raise PackError(f"{pack.name}: {p.name} is a PS2 course and no PS2 disc was given (--ps2)")
            disc = Ps2Disc(ps2_disc)
        out, c = convert_ps2_course(out, load_from_disc(disc, p.index), p, k, gantry_list)
        converted.append(c)
    if any(c.report.get("start_gantry_list") for c in converted):
        installed = (install_start_gantry if pack.gantry == "frames" else install_start_lettering)(out, gantry_list)
        for c in converted:
            c.report["start_gantry_objects"] = installed if c.report.get("start_gantry_list") else None
    return out, converted


def pack_tunes(pack: Pack, tunes=None):
    """The weather's tunes for the pack: pack 1's own; another pack's without the lightning's per-entry aims (pack 1's are set
    for its own entries: Metropolis's at entry 6)."""
    from dataclasses import replace
    from vrtools.arcade.weather.tune import Tunes
    tunes = Tunes() if tunes is None else tunes
    if pack.name == "saturn":
        return tunes
    return replace(tunes, lightning=replace(tunes.lightning, aim_by_entry=()))


def pack_set(rs, converted, pack: Pack, weather: bool = True, tunes=None):
    """`tencourse.ten_course_set` with the pack's wheel, battery RAM magic and the storm's blocks reserved as the pack says."""
    from vrtools.arcade import tencourse as T
    return T.ten_course_set(rs, converted, weather=weather, weather_tunes=pack_tunes(pack, tunes), menu=pack.menu,
                            magic=pack.magic, reserve_weather=pack.reserve_weather)


PS2_EXECUTABLE = "SLPM_624.43"      # Sega Ages 2500 Vol. 8: Virtua Racing FlatOut (Japan): the one release this build reads


def check_ps2(path, pack: Pack = PS2) -> tuple[list[str], list[str]]:
    """(problems, notes) for the PS2 disc image `path` (.cue or .bin): the Japanese release (its SYSTEM.CNF names SLPM_624.43;
    another release, as Sega Classics Collection's Virtua Racing, is refused by name) holding every course the pack plans."""
    from pathlib import Path
    from vrtools.ps2.disc import Ps2Disc, bin_of
    from vrtools.saturn.iso import IsoError
    problems, notes = [], []
    path = Path(path)
    if not path.is_file():
        return [f"PS2 disc {path} does not exist (the .cue of Sega Ages 2500 Vol. 8: Virtua Racing FlatOut, Japan)"], notes
    try:
        track = bin_of(path)
        if not track.is_file():
            return [f"{path} names {track.name}, which is not beside it"], notes
        disc = Ps2Disc(path)
        cnf = disc.read("SYSTEM.CNF").decode("ascii", "replace")
    except (IsoError, OSError, UnicodeError) as e:
        return [f"{path}: not a PS2 disc image this build can read ({e})"], notes
    boot = next((line.split("\\")[-1].split(";")[0].strip() for line in cnf.splitlines() if line.upper().startswith("BOOT2")), "")
    if boot != PS2_EXECUTABLE:
        return [f"{path}: the disc boots {boot or 'nothing'}, not {PS2_EXECUTABLE}: this build reads only Sega Ages 2500 Vol. 8: "
                "Virtua Racing FlatOut (Japan, SLPM-62443); other releases (Sega Classics Collection and the like) are refused"], notes
    notes.append(f"{track.name}: Sega Ages 2500 Vol. 8: Virtua Racing FlatOut (Japan), {PS2_EXECUTABLE}")
    from vrtools.ps2.course import load_from_disc
    for p in pack.slots:
        if isinstance(p, Ps2Plan):
            try:
                load_from_disc(disc, p.index)
                notes.append(f"{track.name}: course {p.index} ({p.name}) read")
            except Exception as e:                      # the reader's errors name the file
                problems.append(f"{track.name}: course {p.index} ({p.name}) cannot be read: {e}")
    return problems, notes
