import pytest

from vrtools.arcade.trace import parse_trace
from vrtools.mame.runner import LUA_DIR, run_mame


def test_the_game_never_touches_the_direction_cell(tmp_path, romset_zip):
    """Phase 26: the reverse flag lives in one RAM byte; on the ORIGINAL set the game never reads or writes its word after the boot clears (frames 0 and 9)
    (docs/spike/2026-11-phase26-stage1-findings.md §1), attract and a Big Forest race alike."""
    from vrtools.arcade.course import DIRECTION_RAM

    span = f"{DIRECTION_RAM:x}-{DIRECTION_RAM + 3:x}"
    for name, script, env in (("attract", "memtrace.lua", {}), ("race", "autoplay.lua", {"VR_COURSE": "0"})):
        wd = tmp_path / name
        run_mame(LUA_DIR / script, 120, wd, romset_zip.parent,
                 env={**env, "VR_TRACE_LOG": str(wd / "trace.log"), "VR_TRACE_FINE": "1", "VR_TRACE_FROM": "20",
                      "VR_TRACE_READ": span, "VR_TRACE_WRITE": span})
        assert [e for e in parse_trace(wd / "trace.log") if e.kind in ("R", "W")] == [], name


_MARKERS: dict = {}


def _marker_set(rs):
    """Phase 26 Task 4: the originals, each with a reverse record that differs only by its HUD map words (map_tx 237.0, the
    record a load served is then read in RAM) and no pit quad, plus seven copies of Big Forest without one (X0..X6). Stage 3
    (Task 6 fix): with the COURSE DIRECTION screen's data block installed as `ten_course_set` installs it: the screen opens on
    the entries with a variant, and its `dirdraw` runs its draw list from that block (without it the list is erased ROM and the
    game hangs on the screen's first frame, measured: DIR_SHOWN 0xff and the logic frame counter stopped from frame 1206)."""
    from dataclasses import replace
    from vrtools.arcade.directory import ORIGINALS, ReverseRecord, directory_layout, install_directory
    from vrtools.arcade.tencourse import install_dirscreen_block

    end = (directory_layout()["end"] + 3) // 4 * 4     # the brief's `end + 0x40 + 64 k` with end rounded up to a word first: a record
                                                        # is 4-aligned and the routines end anywhere (0x27a97e in Task 4)
    d = [replace(e, reverse=ReverseRecord(end + 0x40 + 64 * k, replace(e, map_tx=237.0, map_cross=22, pit_quad=None)))
         for k, e in enumerate(ORIGINALS)] + [replace(ORIGINALS[0], name=f"X{k}") for k in range(7)]
    return install_dirscreen_block(install_directory(rs, d))


def _marker_build(tmp_path_factory, romset_zip):
    from vrtools.arcade.romset import RomSet
    from tests.test_tgp_build import _build

    key = str(romset_zip)
    if key not in _MARKERS:
        _MARKERS[key] = _build(tmp_path_factory.mktemp("markers"), romset_zip, _marker_set(RomSet.from_zip(romset_zip)))
    return _MARKERS[key]


@pytest.mark.parametrize("entry,poke,direction,map_tx,flag", [(2, "", "screen", 237.0, 1), (2, "", None, 149.0, 0), (3, "", "held", 149.0, 0),
                                                              (0, "40dca1=2,501103=2", "held", 149.0, 0)],
                         ids=["variant", "no-flag", "no-variant", "operator-fixed"])
def test_the_flag_serves_the_reverse_record_on_the_menu_path_only(tmp_path, tmp_path_factory, romset_zip, entry, poke, direction, map_tx,
                                                                  flag):
    """Plan D5: with the flag set the race loads the chosen entry's reverse record, and the loader writes back 1; without the
    flag, on an entry without a variant, or on the fallback path (the operator's fixed course, Bay Bridge through
    [0x501934]) the normal record is loaded and the byte reads 0. The RAM dump at frame 2200 is well into the race. Stage 3: on
    the marker set's entry 2 (it has a variant) the course lock opens the COURSE DIRECTION screen and autoplay.lua answers it,
    REVERSE ("screen") or NORMAL; where no screen opens the flag is held at 1 on the select screen by direction.lua ("held":
    mode 0x10's state 0 clears a flag poked before the coin). Task 6 fix: every case first shows that the race loaded (the mode
    byte 0x501138 in the dump is a race mode, and the logic frame counter 0x501144 advanced past the race load's), so a game
    hung before the load (which also leaves map_tx 149.0 and the flag 0) fails."""
    import struct
    from vrtools.arcade.course import DIRECTION_RAM, MAP_TX_RAM
    from vrtools.arcade.select import WHEEL_FOR_ENTRY

    build = _marker_build(tmp_path_factory, romset_zip)
    log = tmp_path / "trace.log"
    held = {"VR_DIRECTION": "1", **({"VR_DIRECTION_FORCE": "1", "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}"} if direction == "held" else {})} if direction else {}
    run_mame(LUA_DIR / "autoplay.lua", 40, tmp_path, build,
             env={"VR_WHEEL": str(WHEEL_FOR_ENTRY[entry]), "VR_POKE": poke, **held,
                  "VR_TRACE_LOG": str(log), "VR_TRACE_DUMP": "2200", "VR_TRACE_FROM": "0", "VR_TRACE_TO": "0"})
    ram = (tmp_path / "trace.log.ram.2200.bin").read_bytes()
    assert 0x11 <= ram[0x501138 - 0x500000] <= 0x14, hex(ram[0x501138 - 0x500000])        # racing (or loading), not on a screen
    assert struct.unpack_from("<I", ram, 0x501144 - 0x500000)[0] > 700                    # logic frames run: ~665 at the load (frame
                                                                                          # 1600), ~965 at frame 2200
    assert struct.unpack_from("<f", ram, MAP_TX_RAM - 0x500000)[0] == map_tx
    assert ram[DIRECTION_RAM - 0x500000] == flag


ATTRACT_LOADS = {0xFE217F: 0xFE2160, 0xFE2D16: 0xFE2CF7}       # the loader's return address after each attract bank site -> the site


def test_the_attract_demo_never_loads_a_reverse_record(tmp_path, tmp_path_factory, romset_zip):
    """Plan D5 ("attract mode: normal direction only"): attract_flag.lua holds the flag at 1 and points the menu entry at an
    original whose template matches the data index (`next`: one ahead; `same`), so an attract load can take the menu path,
    where the flag is read. Every load must serve the normal record (map_tx 149.0), at least one of them on the menu path,
    and loads through both attract bank sites (0xfe2160, game mode 2; 0xfe2cf7, mode 6) must be seen.

    The brief's version (the flag written every frame, a line at the end of each bank-change frame) could not pass; Task 4
    measured why: the bank switch and the loader run in different frames (the backdrop upload `jsr FFE007` between them
    spans a frame boundary: bankdemo cleared the flag in frame 273 (frames counted from 1), the loader read it in frame 274 after the script had
    written 1 again, and served Bay Bridge's variant, map_tx 237.0), so the script now stops writing from a bank change to
    the loader's map_tx write; and mode 6's load at 0xfe2cf7 saves the data index in the menu word, so with a saved index
    of 0 it takes the menu path for entry 0 (frame 2258: entry 0's variant, map_tx 237.0, with only 0xfe2160 clearing)."""
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.arcade.directory import FALLBACK

    build = _marker_build(tmp_path_factory, romset_zip)
    runs = {}
    for mode in ("next", "same"):
        wd = tmp_path / mode
        run_mame(LUA_DIR / "attract_flag.lua", 130, wd, build,
                 env={"VR_FLAG_LOG": str(wd / "flag.log"), "VR_FLAG_RAM": f"{DIRECTION_RAM:x}", "VR_FLAG_MENU": mode})
        runs[mode] = [(int(f), int(di), int(menu), float(tx), int(m), int(caller, 16)) for tag, f, di, menu, tx, m, _, caller in
                      (line.split() for line in open(wd / "flag.log")) if tag == "L"]
    loads = [x for lines in runs.values() for x in lines]
    assert all(runs.values()), runs
    assert all(tx == 149.0 for _, _, _, tx, _, _ in loads), runs
    assert any(di < 3 and menu == FALLBACK[di] for _, di, menu, _, _, _ in loads), runs                 # a menu-path load
    assert {ATTRACT_LOADS.get(caller) for *_, caller in loads} >= {0xFE2160, 0xFE2CF7}, runs          # through both sites
    assert any(m == 6 and ATTRACT_LOADS.get(caller) == 0xFE2CF7 for *_, m, caller in loads), runs     # mode 6's load


# Phase 26 Task 6 (plan D6): the brief's site table, by the quad operand of the game's `mov.w <quad>, [R24]`
DIRECTION_SITES = {("mov.w disp[reg],reg", 0x30, "r25"): (0xFE8D0B, 0xFE8F97, 0xFE9147, 0xFE92FD, 0xFEA927, 0xFEAA82, 0xFEAB05, 0xFEBD50, 0xFF2205,
                                                           0xFF241C),
                   ("mov.w disp[reg],reg", 0x30, "r19"): (0xFF4C9E,),
                   ("mov.w reg,reg", "r1"): (0xFEC003, 0xFEC152),
                   ("mov.w reg,reg", "r12"): (0xFFCFFC,)}
FLAG_SETTERS = ("cmp", "test", "sub", "add", "and", "or", "xor", "shl", "sha", "neg")     # what sets the flags before a test, at these sites


def _reads_r0_as_a_halfword(lines) -> None:
    """The game's code after a site, up to its next branch or call: R0 only in halfword instructions until a whole-word write
    replaces it, and the condition flags set before a conditional branch tests them (dirattr returns with the flags clobbered and,
    after its `add.w #8000`, possibly another upper half than `in.w` left)."""
    import re
    live, flags = True, False
    for l in lines:
        mnem, ops = (l.text.split(None, 1) + [""])[:2]
        if mnem.startswith("b") and mnem not in ("br", "bsr"):
            assert flags, l.text                                 # a conditional branch: the flags were set after the site
            return
        if mnem in ("br", "bsr", "jsr", "jmp", "rsr"):
            return
        if live and re.search(r"\bR0\b", ops) and not mnem.endswith(".h"):
            assert mnem in ("mov.w", "in.w") and ops.endswith(", R0") and not re.search(r"\bR0\b", ops[:-4]), l.text
            live = False                                         # R0 replaced whole: the direction is no longer in it
        flags = flags or mnem.startswith(FLAG_SETTERS)
    raise AssertionError(f"no branch within {len(lines)} instructions")


def test_the_fourteen_direction_sites_call_dirattr(romset_zip):
    """Plan D6: every command-0x1800 site of the boot ROM (`mov.w #18000000, [R24]; mov.w <quad>, [R24]; in.w [R23], R0`; the program
    ROM has none) loads the quad into R0 and calls `dirattr`, which sends the command and adds half a turn in a reverse race; the
    code after each site reads R0 as a halfword and sets the flags itself before testing them (recon §6)."""
    from vrtools.arcade.direction import ATTR_SITES
    from vrtools.arcade.directory import ORIGINALS, directory_layout, install_directory
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.romset import RomSet
    from vrtools.arcade.v60asm import asm

    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, (ORIGINALS * 4)[:10])
    lay = directory_layout()
    sites = {site: load for load, group in DIRECTION_SITES.items() for site in group}
    command = bytes.fromhex("2d80f40000001878")
    assert sorted(a for a, _ in ATTR_SITES) == sorted(sites)
    assert sorted(sites) == [0xFC0000 + i for i in range(len(rs.boot)) if rs.boot[i:i + 8] == command]     # every 0x1800 site
    assert rs.program.find(command) == -1                     # and none in the program ROM (the format notes say "boot and program")
    for site, operand in ATTR_SITES:
        at, n = site - 0xFC0000, 8 + len(operand) + 3
        assert rs.boot[at:at + n] == command + operand + bytes.fromhex("242077"), hex(site)
        form, *args = sites[site]
        patched = asm(form, *args, "r0") + asm("jsr abs", lay["dirattr"])
        assert out.boot[at:at + n] == patched + asm("nop") * (n - len(patched)), hex(site)
        assert listing(out, site + n, 1) == listing(rs, site + n, 1), hex(site)
        _reads_r0_as_a_halfword(listing(rs, site + n, 30))


def test_dirattr_adds_half_a_turn_only_with_the_flag():
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.arcade.direction import direction_routines
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.disasm import listing_bytes

    lay = directory_layout()
    texts = [l.text for l in listing_bytes(direction_routines(lay["dirattr"], lay["pitbox"])["dirattr"], lay["dirattr"])]
    assert [t.split()[0] for t in texts] == ["mov.w", "mov.w", "in.w", "cmp.b", "be", "add.w", "rsr"]
    assert texts[0] == "mov.w   #18000000, [R24]" and texts[1] == "mov.w   R0, [R24]" and texts[2] == "in.w    [R23], R0"
    assert texts[3] == f"cmp.b   #0, {DIRECTION_RAM:X}" and texts[5] == "add.w   #8000, R0"


def test_a_changed_direction_site_is_refused(romset_zip):
    from vrtools.arcade.directory import ORIGINALS, install_directory
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    boot = bytearray(rs.boot)
    boot[0xFEC152 - 0xFC0000 + 9] ^= 0x0D                        # the quad operand R1 -> R12
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match="0xfec152"):
        install_directory(rs, (ORIGINALS * 4)[:10])


# Phase 26 stage 2 Task 5 (plan D6): the Big Forest template's crew start. Mode 0x11 sets bit 0x1e of the race-start task
# `[0x50134c]` at 0xfe41d6 (`set1 #1E, 0[R0]`) for data index 2 outside linked play; with it the player starts at the template's
# fixed pit-start pose facing the normal way (stage 2 recon §3). The site calls `startbit`, which sets the bit only with the
# direction flag 0, so reverse Alpine takes the standing grid start of the six other courses.
def test_the_start_bit_site_calls_startbit(romset_zip):
    """The site's nine bytes on the original are START_BIT_PATTERN; installed, they are `jsr startbit` and nops up to 0xfe41df
    (`push R0`, unchanged): R0 is kept by the routine and the flags after the site are not read."""
    from vrtools.arcade.direction import START_BIT_PATTERN, START_BIT_SITE
    from vrtools.arcade.directory import ORIGINALS, directory_layout, install_directory
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    at = START_BIT_SITE - 0xFC0000
    assert START_BIT_SITE == 0xFE41D6 and rs.boot[at:at + len(START_BIT_PATTERN)] == START_BIT_PATTERN
    assert listing(rs, START_BIT_SITE, 1)[0].text == "set1    #1E, 0[R0]"
    out = install_directory(rs, (ORIGINALS * 4)[:10])
    lines = [l for l in listing(out, START_BIT_SITE, 12) if l.addr < 0xFE41DF]
    assert lines[0].text == f"jsr     {directory_layout()['startbit']:X}"
    assert [l.text for l in lines[1:]] == ["nop"] * (len(lines) - 1) and lines[-1].addr == 0xFE41DE
    assert listing(out, 0xFE41DF, 1) == listing(rs, 0xFE41DF, 1)


def test_startbit_sets_the_bit_only_with_the_flag_clear():
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.arcade.direction import direction_routines
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.disasm import listing_bytes

    lay = directory_layout()
    code = direction_routines(lay["dirattr"], lay["pitbox"])["startbit"]
    lines = listing_bytes(code, lay["startbit"])
    texts = [l.text for l in lines]
    assert [t.split()[0] for t in texts] == ["cmp.b", "bne", "set1", "rsr"]
    assert texts[0] == f"cmp.b   #0, {DIRECTION_RAM:X}" and texts[1] == f"bne     {lines[3].addr:X}" and texts[2] == "set1    #1E, 0[R0]"


def test_a_changed_start_bit_site_is_refused(romset_zip):
    from vrtools.arcade.directory import ORIGINALS, install_directory
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    boot = bytearray(rs.boot)
    boot[0xFE41D6 - 0xFC0000 + 3] = 0x1F                          # set1 #1F: another bit
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match="0xfe41d6"):
        install_directory(rs, (ORIGINALS * 4)[:10])


# Phase 26 stage 2 (plan D7's first way; built and measured in Task 7, chosen by Pascal after the drive in place of Task 7's
# fallback, which left the figures out in reverse): the Acropolis template's three start figures (Metropolis, Diablo Canyon). The
# race-start task places them at world-axis offsets from the player and ends the placement with `br FC0EEC` at 0xfc0eb0 (stage 2
# recon §3); the three-byte branch and the `clr1 #1E, 0[R19]; pop R19` before it become `jmp figures`, which re-emits those two
# and, with the direction flag set, turns the figures half a turn round the player before it jumps to 0xfc0eec.
def test_the_figures_site_jumps_to_figures(romset_zip):
    """On the original the span is the last figure's `clr1 #1E, 0[R19]`, `pop R19` and the placement's `br FC0EEC` at
    FIGURES_SITE (0xfc0eb0); installed it is `jmp figures` and nops up to 0xfc0eb3 (`mov.w #FC0FEA, A[R25]`, the crew branch's
    target from 0xfc0bd6, unchanged)."""
    from vrtools.arcade.direction import FIGURES_PATTERN, FIGURES_SITE, FIGURES_SPAN
    from vrtools.arcade.directory import ORIGINALS, directory_layout, install_directory
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    at = FIGURES_SPAN - 0xFC0000
    assert FIGURES_SITE == 0xFC0EB0 and FIGURES_SPAN + len(FIGURES_PATTERN) == FIGURES_SITE + 3
    assert rs.boot[at:at + len(FIGURES_PATTERN)] == FIGURES_PATTERN
    assert [l.text for l in listing(rs, FIGURES_SPAN, 3)] == ["clr1    #1E, 0[R19]", "pop     R19", "br      FC0EEC"]
    out = install_directory(rs, (ORIGINALS * 4)[:10])
    lines = [l for l in listing(out, FIGURES_SPAN, 12) if l.addr < FIGURES_SITE + 3]
    assert lines[0].text == f"jmp     {directory_layout()['figures']:X}"
    assert [l.text for l in lines[1:]] == ["nop"] * (len(lines) - 1) and lines[-1].addr == FIGURES_SITE + 2
    assert listing(out, FIGURES_SITE + 3, 1) == listing(rs, FIGURES_SITE + 3, 1)


def test_figures_turns_the_three_figures_round_the_player_only_with_the_flag():
    """`figures`: the original's two instructions, then with the flag 0 straight to 0xfc0eec; with it set, for pool objects 0-2
    (`[0x501350]`, 0x280 bytes each) x' = px + (px - x) and z' = pz + (pz - z) by the TGP's add (command 0, as the placement
    itself adds its offsets; the operand negated by adding 0x80000000, its sign bit) and 0x8000 added to the heading `+0x2c`."""
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.arcade.direction import direction_routines
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.disasm import listing_bytes

    lay = directory_layout()
    lines = listing_bytes(direction_routines(lay["dirattr"], lay["pitbox"])["figures"], lay["figures"])
    texts = [l.text for l in lines]
    assert texts[:4] == ["clr1    #1E, 0[R19]", "pop     R19", f"cmp.b   #0, {DIRECTION_RAM:X}", f"be      {lines[-1].addr:X}"]
    assert texts[-1] == "jmp     FC0EEC"
    body = texts[4:-1]
    assert body.count("mov.w   501350, R2") == 1 and body.count("mov.w   501320, R1") == 1
    assert body.count("add.w   #80000000, R0") == 2 and body.count("mov.w   #0, [R24]") == 4 and body.count("in.w    [R23], R0") == 4
    assert body.count("mov.w   1E[R1], [R24]") == 2 and body.count("mov.w   26[R1], [R24]") == 2
    assert "mov.w   R0, 1E[R2]" in body and "mov.w   R0, 26[R2]" in body
    assert "add.w   #8000, R0" in body and "mov.h   R0, 2C[R2]" in body and "add.w   #280, R2" in body
    pushed = [t.split()[1] for t in body if t.startswith("push")]
    assert [t.split()[1] for t in body if t.startswith("pop")] == pushed[::-1]          # the registers it uses come back


def test_a_changed_figures_site_is_refused(romset_zip):
    from vrtools.arcade.directory import ORIGINALS, install_directory
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    boot = bytearray(rs.boot)
    boot[0xFC0EB0 - 0xFC0000 + 1] += 1                           # br FC0EED: another target
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match="0xfc0eb0"):
        install_directory(rs, (ORIGINALS * 4)[:10])


# Phase 26 stage 2 Task 13 (Pascal, on the half turn's contact sheets: the figures "have to be around the car"): the figures'
# animation is world-axis, so a half turn of the placement alone leaves them drifting off the normal places. Each use of that
# animation (FIGURE_SITES: the root offset's x and z where the draw pushes it and where an ended animation adds it to the
# position; the body's two root rotations about the horizontal axes, applied outside the heading; the walk-off heading) calls a
# routine that re-emits the original instruction unless `figmirror` (the flag set and the object one of the three figures by
# its character record) holds, and then pushes the value negated (the walk-off heading: 0xc000). No branch of the boot lands
# inside a site (recon: a sweep of the boot listing's branch targets and of 32-bit words in the boot and program ROMs).
SITE_TEXTS = {0xFF5E13: "mov.w   17B[R25], [R24]", 0xFF5E1F: "mov.w   193[R25], [R24]", 0xFF6A18: "mov.w   17B[R25], [R24]",
              0xFF6A2C: "mov.w   193[R25], [R24]", 0xFF6C25: "movs.hw D1[R25], [R24]", 0xFF6C41: "movs.hw DD[R25], [R24]",
              0xFF6712: "mov.h   #4000, 36[R25]"}


def test_the_figures_animation_sites_call_their_routines(romset_zip):
    """On the original each site is its pattern and instruction; installed it is `jsr <routine>` and nops to the original's
    length, and the next instruction is unchanged."""
    from vrtools.arcade.direction import FIGURE_SITES
    from vrtools.arcade.directory import ORIGINALS, directory_layout, install_directory
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, (ORIGINALS * 4)[:10])
    lay = directory_layout()
    assert sorted(FIGURE_SITES) == sorted(SITE_TEXTS)
    for site, (pattern, name) in FIGURE_SITES.items():
        at, n = site - 0xFC0000, len(pattern)
        assert rs.boot[at:at + n] == pattern and listing(rs, site, 1)[0].text == SITE_TEXTS[site], hex(site)
        lines = [l for l in listing(out, site, 4) if l.addr < site + n]
        assert lines[0].text == f"jsr     {lay[name]:X}", (hex(site), lines[0].text)
        assert [l.text for l in lines[1:]] == ["nop"] * (len(lines) - 1), hex(site)
        assert out.boot[at:at + n] == bytes.fromhex("e8f3") + lay[name].to_bytes(4, "little") + b"\xcd" * (n - 6), hex(site)
        assert listing(out, site + n, 1) == listing(rs, site + n, 1), hex(site)


def test_figmirror_holds_only_with_the_flag_on_the_figures_and_the_crew():
    """Z when the flag is set and R25's character record is one of the three start figures' or (stage 4 Task 5) one of the pit
    crew's fourteen (CREW_RECORDS): the crew runs the same character code, FIGURE_SITES included."""
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.arcade.direction import direction_routines
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.disasm import listing_bytes

    lay = directory_layout()
    lines = listing_bytes(direction_routines(lay["dirattr"], lay["pitbox"])["figmirror"], lay["figmirror"])
    texts = [l.text for l in lines]
    records = [0xFD743B, 0xFD747F, 0xFD754B] + CREW_RECORDS
    done = lines[2 + 2 * len(records) - 1].addr
    plain = lines[2 + 2 * len(records)].addr
    tests = [t for rec in records for t in (f"cmp.w   #{rec:X}, 1AB[R25]", f"be      {done:X}")][:-1]
    assert texts == [f"cmp.b   #0, {DIRECTION_RAM:X}", f"be      {plain:X}", *tests, "rsr", f"cmp.b   #1, {DIRECTION_RAM:X}", "rsr"]


def test_the_figures_animation_routines_negate_only_when_mirrored():
    """Each routine: `jsr figmirror`, then the original instruction and `rsr` when it does not hold; else the field negated
    pushed to the TGP (a float by its sign bit, a halfword angle sign-extended and multiplied by −1), R0 kept. `figwalk`: the
    original's walk-off heading, then 0xc000 when it holds."""
    from vrtools.arcade.direction import FIGURE_SITES, direction_routines
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.disasm import listing_bytes

    lay = directory_layout()
    code = direction_routines(lay["dirattr"], lay["pitbox"])
    original = {name: SITE_TEXTS[site] for site, (_, name) in FIGURE_SITES.items()}
    for name, negate in (("figrootx", ["mov.w   17B[R25], R0", "add.w   #80000000, R0"]),
                         ("figrootz", ["mov.w   193[R25], R0", "add.w   #80000000, R0"]),
                         ("figrot0", ["movz.hw D1[R25], R0", "shl.w   #10, R0", "sha.w   #F0, R0", "mul.w   #FFFFFFFF, R0"]),
                         ("figrot2", ["movz.hw DD[R25], R0", "shl.w   #10, R0", "sha.w   #F0, R0", "mul.w   #FFFFFFFF, R0"])):
        lines = listing_bytes(code[name], lay[name])
        texts = [l.text for l in lines]
        assert texts == [f"jsr     {lay['figmirror']:X}", f"be      {lines[4].addr:X}", original[name], "rsr",
                         "push    R0", *negate, "mov.w   R0, [R24]", "pop     R0", "rsr"], (name, texts)
    lines = listing_bytes(code["figwalk"], lay["figwalk"])
    assert [l.text for l in lines] == [original["figwalk"], f"jsr     {lay['figmirror']:X}", f"bne     {lines[-1].addr:X}",
                                       "mov.h   #C000, 36[R25]", "rsr"]


def test_a_changed_figures_animation_site_is_refused(romset_zip):
    from vrtools.arcade.directory import ORIGINALS, install_directory
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    boot = bytearray(rs.boot)
    boot[0xFF6C41 - 0xFC0000 + 3] = 0xD7                         # movs.hw D7[R25]: the body's other rotation
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match="0xff6c41"):
        install_directory(rs, (ORIGINALS * 4)[:10])


FIGURE_RECORD_REFS = {0xFC0C61, 0xFC0D59, 0xFC0E2C,   # the race-start placement (`mov.w #<record>, 1AB[R19]`, 0xfc0bf2..0xfc0eb0)
                      0xFC0186, 0xFC0230}             # the attract mode's pit scene: two of the three records, placed unmirrored there
                                                      # only because `bankdemo` clears the flag before the attract runs


def test_the_figure_records_are_referenced_only_at_the_placement_and_the_attract_pit_scene(romset_zip):
    """`figmirror` tells a figure by its character record (+0x1ab), so an object holding one of FIGURE_RECORDS anywhere else
    would be mirrored too while the flag is set. On the original the three record values (32-bit, little-endian) occur in the
    program and boot ROMs only at the placement's three stores and at the attract pit scene's two (stage 2 findings §11.3.2:
    the flag is 0 there; the direction screen of stage 3 must keep that order)."""
    from vrtools.arcade.direction import FIGURE_RECORDS
    from vrtools.arcade.disasm import find_refs
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    refs = {a for rec in FIGURE_RECORDS for a in find_refs(rs, rec, ("program", "boot"))}
    assert refs == FIGURE_RECORD_REFS, sorted(hex(a) for a in refs)


# Phase 26 stage 4 Task 5 (decision P2, the lead's reading of Pascal's 'Ok', 14 Nov): the pit crew turned half a turn about the box in a reverse race. The
# pit sequence's work states 1, 8, 11 and 14 spawn the crew (`bsr <spawn>; inc.h 191[R25]` at CREW_SITES, read 14 Nov from the
# boot listing: each spawn places pool objects 0..n-1 of [0x501350] at world-axis offsets from the box, `pitboxcrew`'s, and sets
# their record, heading and handler 0xff5c3d before it returns; nothing later places them but the animation's end-of-animation
# add, a FIGURE_SITES site). Each site calls its entry `crewturn<state>`, which runs the spawn and the `inc.h`, and with the
# direction flag set calls `crewturn` with R3 = n: each object reflected through the served record's box (`pitbox`) and its
# heading + 0x8000. `figmirror` takes in the crew's character records, so their world-axis animation is mirrored too.
CREW_TEXTS = {0xFF2518: ("bsr     FF27D8", 5, "crewturn1"), 0xFF26F0: ("bsr     FF2D69", 6, "crewturn8"),
              0xFF2735: ("bsr     FF33C7", 6, "crewturn11"), 0xFF277A: ("bsr     FF3A1B", 6, "crewturn14")}
CREW_RECORDS = [0xFD7033, 0xFD7078, 0xFD70BD, 0xFD7102, 0xFD7147,            # work state 1's five (0xff27d8)
                0xFD7216, 0xFD725B, 0xFD6FEE, 0xFD71D1, 0xFD7AD5, 0xFD7B1A,   # 8's six (0xff2d69)
                0xFD72A0, 0xFD72E5, 0xFD732A]                                 # 11's (0xff33c7) and 14's (0xff3a1b) others
# every 32-bit occurrence of a crew record in the original program and boot ROMs: the `mov.w #<record>, 1AB[R19]` stores of the
# four spawns, nowhere else. The attract mode's pit scene runs work state 1's spawn itself (0xfc007e `jsr FF27D8[PC]`), so its
# objects 0-4 hold the first five records; its other objects take its own records (0xfc00d5, 0xfc02b5) and two of the figures'
CREW_CALLERS = {0xFF2518, 0xFF26F0, 0xFF2735, 0xFF277A,    # the four sites (CREW_TEXTS)
                0xFF25C9,                                # Alpine's PIT START, work state 6: `bsr FF27D8`
                0xFC007E}                                # the attract mode's pit scene: `jsr FF27D8[PC]`
CREW_RECORD_REFS = {0xFF282C, 0xFF28DD, 0xFF298E, 0xFF2A3F, 0xFF2AF0,
                    0xFF2DBD, 0xFF2E70, 0xFF2EF9, 0xFF2FAC, 0xFF3035, 0xFF3106,
                    0xFF341B, 0xFF34CE, 0xFF3557, 0xFF35E0, 0xFF3693, 0xFF371C,
                    0xFF3A6F, 0xFF3B22, 0xFF3BAB, 0xFF3C34, 0xFF3CE7, 0xFF3D70}
CREW_SPAWNS = ((0xFF27D8, 0xFF2B50), (0xFF2D69, 0xFF315C), (0xFF33C7, 0xFF379C), (0xFF3A1B, 0xFF3DD2))   # each spawn to its `rsr`


def test_the_crew_sites_call_their_crewturn_entries(romset_zip):
    """On the original each site is `bsr <spawn>; inc.h 191[R25]` (7 bytes) and the next instruction the state's `rsr`; installed
    it is `jsr crewturn<state>` and a nop, the `rsr` unchanged. Built with `crew=False` (the tests' set without Task 5's crew
    change) the sites are the original's and `figmirror` tests the three figures' records only, nop-padded to its length: the
    program ROM differs from the product's inside `figmirror` only, every address the same."""
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.arcade.direction import CREW_SITES, crew_site_pattern
    from vrtools.arcade.directory import ORIGINALS, directory_layout, install_directory
    from vrtools.arcade.disasm import listing
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, (ORIGINALS * 4)[:10])
    bare = install_directory(rs, (ORIGINALS * 4)[:10], crew=False)
    lay = directory_layout()
    assert sorted(CREW_SITES) == sorted(CREW_TEXTS)
    for site, (spawn, objects, name) in CREW_SITES.items():
        text, n_objects, entry = CREW_TEXTS[site]
        at = site - 0xFC0000
        assert (objects, name) == (n_objects, entry) and text == f"bsr     {spawn:X}"
        assert rs.boot[at:at + 7] == crew_site_pattern(site)
        assert [l.text for l in listing(rs, site, 3)] == [text, "inc.h   191[R25]", "rsr"], hex(site)
        assert out.boot[at:at + 7] == bytes.fromhex("e8f3") + lay[name].to_bytes(4, "little") + b"\xcd", hex(site)
        assert [l.text for l in listing(out, site, 3)] == [f"jsr     {lay[name]:X}", "nop", "rsr"], hex(site)
        assert bare.boot[at:at + 7] == rs.boot[at:at + 7], hex(site)
    changed = [i + 0xFC0000 for i in range(len(rs.boot)) if bare.boot[i] != out.boot[i]]
    assert changed and all(any(s <= a < s + 7 for s in CREW_SITES) for a in changed)       # the switch changes the four sites
    changed = [i + 0x200000 for i in range(len(rs.program)) if bare.program[i] != out.program[i]]
    assert changed and lay["figmirror"] <= min(changed) and max(changed) < lay["figrootx"]  # and figmirror
    texts = [l.text for l in listing(bare, lay["figmirror"], 60) if l.addr < lay["figrootx"]]
    assert texts[2:7:2] == ["cmp.w   #FD743B, 1AB[R25]", "cmp.w   #FD747F, 1AB[R25]", "cmp.w   #FD754B, 1AB[R25]"]
    assert texts[7:10] == ["rsr", f"cmp.b   #1, {DIRECTION_RAM:X}", "rsr"] and set(texts[10:]) == {"nop"}


def test_the_crewturn_entries_run_the_spawn_and_test_the_flag():
    """Each entry: the site's spawn (`jsr`, as the `bsr` was) and `inc.h 191[R25]`, then the flag; with it 0 straight to `rsr`
    (the flags after the site are dead: the state's `rsr` returns to the handler's 0xff2381 `test.h`); with it set R3 = the
    spawn's object count for `crewturn`, R3 kept."""
    from vrtools.arcade.course import DIRECTION_RAM
    from vrtools.arcade.direction import CREW_SITES, direction_routines
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.disasm import listing_bytes

    lay = directory_layout()
    code = direction_routines(lay["dirattr"], lay["pitbox"])
    for site, (spawn, objects, name) in CREW_SITES.items():
        lines = listing_bytes(code[name], lay[name])
        texts = [l.text for l in lines]
        assert texts == [f"jsr     {spawn:X}", "inc.h   191[R25]", f"cmp.b   #0, {DIRECTION_RAM:X}", f"be      {lines[-1].addr:X}",
                         "push    R3", f"mov.w   #{objects}, R3", f"jsr     {lay['crewturn']:X}", "pop     R3", "rsr"], (name, texts)


def test_crewturn_reflects_the_crew_through_the_box():
    """`crewturn`: R10, R11, R12 = the served record's box from `pitbox` (the spawn's own box); for R3 objects of the pool
    `[0x501350]` (0x280 bytes each) x' = bx + (bx + -x), z' = bz + (bz + -z) by the TGP's add (the operand negated by its sign
    bit) and 0x8000 added to the heading `+0x2c`; the registers it uses come back (R3 is the caller's)."""
    from vrtools.arcade.direction import direction_routines
    from vrtools.arcade.directory import directory_layout
    from vrtools.arcade.disasm import listing_bytes

    lay = directory_layout()
    lines = listing_bytes(direction_routines(lay["dirattr"], lay["pitbox"])["crewturn"], lay["crewturn"])
    texts = [l.text for l in lines]
    assert texts[-1] == "rsr" and f"jsr     {lay['pitbox']:X}" in texts and texts.count("mov.w   501350, R2") == 1
    body = texts[texts.index("mov.w   501350, R2") + 1:]
    assert body.count("add.w   #80000000, R0") == 2 and body.count("mov.w   #0, [R24]") == 4 and body.count("in.w    [R23], R0") == 4
    assert body.count("mov.w   R10, [R24]") == 2 and body.count("mov.w   R12, [R24]") == 2
    assert "mov.w   1E[R2], R0" in body and "mov.w   26[R2], R0" in body and "mov.w   R0, 1E[R2]" in body and "mov.w   R0, 26[R2]" in body
    assert "movz.hw 2C[R2], R0" in body and "add.w   #8000, R0" in body and "mov.h   R0, 2C[R2]" in body
    assert "add.w   #280, R2" in body and "sub.w   #1, R3" in body and any(t.startswith("bne") for t in body)
    pushed = [t.split()[1] for t in texts if t.startswith("push")]
    assert sorted(pushed) == ["R0", "R10", "R11", "R12", "R2"]
    assert [t.split()[1] for t in texts if t.startswith("pop")] == pushed[::-1]
    assert texts.index(f"jsr     {lay['pitbox']:X}") > max(i for i, t in enumerate(texts) if t.startswith("push"))


def test_a_changed_crew_site_is_refused(romset_zip):
    from vrtools.arcade.directory import ORIGINALS, install_directory
    from vrtools.arcade.patch import PatchError
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    boot = bytearray(rs.boot)
    boot[0xFF26F0 - 0xFC0000 + 1] += 1                           # bsr FF2D6A: another target
    object.__setattr__(rs, "boot", bytes(boot))
    with pytest.raises(PatchError, match="0xff26f0"):
        install_directory(rs, (ORIGINALS * 4)[:10])


def test_the_crew_records_are_referenced_only_at_the_crew_spawns(romset_zip):
    """`figmirror` tells the crew by its character records, so an object holding one of CREW_RECORDS anywhere else would be
    mirrored too while the flag is set. On the original the fourteen values (32-bit, little-endian) occur in the program and
    boot ROMs only at the four spawns' record stores. This finds literal references only: the records lie in a table of 0x45-byte
    entries (0xfd6fee + 0x45·k), and a reference computed as the table's base plus an index would escape it, so it supports "no
    other object takes a crew record" without establishing it. Work state 1's spawn (0xff27d8) is also run by Alpine's PIT
    START (state 6, 0xff25c9, normal only: reverse Alpine starts on the grid, `startbit`) and by the attract mode's pit scene
    (0xfc007e), whose objects 0-4 therefore hold the first five records; both keep the game's crew because the flag is 0 there
    (the attract: tests/test_dirscreen_build.py::test_the_flag_is_zero_whenever_a_select_screen_starts and
    test_the_attract_demo_never_loads_a_reverse_record). The spawns' callers: `test_the_crew_spawns_are_called_only_from_the_known_callers`.
    None is a figure's record."""
    from vrtools.arcade.direction import CREW_RECORDS as RECORDS, FIGURE_RECORDS
    from vrtools.arcade.disasm import find_refs
    from vrtools.arcade.romset import RomSet

    rs = RomSet.from_zip(romset_zip)
    assert list(RECORDS) == CREW_RECORDS and not set(RECORDS) & set(FIGURE_RECORDS)
    refs = {a for rec in RECORDS for a in find_refs(rs, rec, ("program", "boot"))}
    assert refs == CREW_RECORD_REFS, sorted(hex(a) for a in refs)
    assert all(any(lo <= a < hi for lo, hi in CREW_SPAWNS) for a in refs)


def _transfer_targets(blob: bytes, base: int, i: int) -> list[int]:
    """The targets of a direct control transfer whose opcode would sit at byte `i` of `blob` (placed at `base`): `bsr` and the
    16-bit branches (0x48, 0x70-0x7f, displacement from the instruction), the 8-bit branches (0x60-0x6f), and `jsr` / `jmp` (0xe8 /
    0xd6) PC-relative by 8, 16 or 32 bits (modes 0xf0-0xf2) or absolute (0xf3). Read at every byte, not along an instruction
    stream, so an instruction a linear listing would step over is not missed."""
    import struct
    a, op = base + i, blob[i]
    out = []
    if op == 0x48 or 0x70 <= op <= 0x7F:
        out.append(a + struct.unpack_from("<h", blob, i + 1)[0])
    elif 0x60 <= op <= 0x6F:
        out.append(a + struct.unpack_from("<b", blob, i + 1)[0])
    elif op in (0xE8, 0xD6):
        mode = blob[i + 1]
        if mode == 0xF0:
            out.append(a + struct.unpack_from("<b", blob, i + 2)[0])
        elif mode == 0xF1:
            out.append(a + struct.unpack_from("<h", blob, i + 2)[0])
        elif mode == 0xF2:
            out.append((a + struct.unpack_from("<i", blob, i + 2)[0]) & 0xFFFFFFFF)
        elif mode == 0xF3:
            out.append(struct.unpack_from("<I", blob, i + 2)[0])
    return out


def test_the_crew_spawns_are_called_only_from_the_known_callers(romset_zip):
    """Final review (I1): the crew's records reach an object only through the four spawns (CREW_SPAWNS' entries), and on the
    original the spawns are reached only from CREW_CALLERS: the four sites, Alpine's PIT START (0xff25c9) and the attract mode's pit
    scene (0xfc007e). Every byte of the program and boot ROMs is read as a possible direct transfer (`_transfer_targets`) and
    every 32-bit occurrence of a spawn's address is found (a table entry, a pointer a register call would load, an absolute
    `jsr`): the places naming a spawn are exactly CREW_CALLERS, each disassembling to its call. Not covered: a target computed at
    run time (a base plus an offset), which no static read finds."""
    from vrtools.arcade.disasm import find_refs, listing
    from vrtools.arcade.romset import RomSet, V60_BOOT, V60_PROGRAM

    rs = RomSet.from_zip(romset_zip)
    spawns = {lo for lo, _ in CREW_SPAWNS}
    named = {}
    for base, blob in ((V60_BOOT, rs.boot), (V60_PROGRAM, rs.program)):
        for i in range(len(blob) - 6):
            for t in _transfer_targets(blob, base, i):
                if t in spawns:
                    named.setdefault(base + i, set()).add(t)
    for s in spawns:
        for a in find_refs(rs, s, ("program", "boot")):
            named.setdefault(a, set()).add(s)
    assert set(named) == CREW_CALLERS, sorted(hex(a) for a in named)
    for a in sorted(CREW_CALLERS):
        (target,) = named[a]
        text = listing(rs, a, 1)[0].text
        assert text in (f"bsr     {target:X}", f"jsr     {target:X}[PC]"), (hex(a), text)
