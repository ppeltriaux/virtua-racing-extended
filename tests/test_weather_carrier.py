"""Weather stage 2, the storm's carrier (weather/carrier.py: its RAM contract is its docstring): the RAM map, the blocks, the stub's
DRY path (the switch test only), the guard (the game's vblank count; no interrupt touched), the registry (a module adds code, cells, tables and per-course data), the
copy lists; in MAME: DRY runs no storm code and copies nothing (a DRY race and the attract, traced; the switch test's cost on a DRY
pass), a RAIN race ending normally or by time over puts everything back (Review Focus 2), and a second game, DRY or RAIN on another
course, starts clean (Review Focus 5). The MAME runs are tests/test_weather_rain.py's `storm_runs`."""
import statistics
import struct
from dataclasses import replace

import numpy as np
import pytest

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT
from vrtools.arcade.v60asm import Block
from vrtools.arcade.weather import carrier
from vrtools.arcade.weather.carrier import DATA, IMAGE, MODULE_CELLS, STORM_RAM
from vrtools.mame.framerate import RAIN_BUSY_MAX_MS
from vrtools.mame.runner import parse_stale_log
from tests.test_weather_rain import (AFTER_SNAPS, CHAIN_DUMP, END_DUMPS, RELOAD_DUMPS, RELOAD_JUNK, RELOAD_POKE, RESET_RACE,
                                     RESET_WINDOW, SVC_EXIT, TOVER_AFTER, WINDOW_EXIT, WINDOW_TEST, storm_runs)  # noqa: F401 (the fixture)

_S1: dict = {}


def _stage1(romset_zip, saturn_cue):
    """The session's set with the switch off and stage 1's screen installed: what carrier.install starts from."""
    from tests.test_weather_dry import _seven_dry
    from vrtools.arcade.weather import screen
    from vrtools.arcade.weather.tune import ScreenTune
    from tests.session_cache import cached                     # a failed build cached, not rebuilt (Task 7)

    def make():
        dry, conv = _seven_dry(romset_zip, saturn_cue)
        s1 = replace(dry)
        screen.install(s1, ScreenTune())
        return s1
    return cached(_S1, str(romset_zip), make)


def _listing(rs, addr, n):
    from vrtools.arcade.disasm import listing
    return [" ".join(l.text.split()) for l in listing(rs, addr, n)]


# ---- static ----------------------------------------------------------------------------------------------------------------
def test_the_ram_map():
    """The storm's RAM (0x520000..0x53efff: cleared by the boot, untouched by the game) in order: the carrier's cells, the modules'
    cells, the image, the data; the layout table's RAM blocks are these."""
    from vrtools.arcade.weather import layout
    assert STORM_RAM == (0x520000, 0x53F000)
    assert carrier.CARRIER_CELLS == STORM_RAM[0] < MODULE_CELLS[0] < MODULE_CELLS[1] <= IMAGE[0] < IMAGE[1] <= DATA[0] < DATA[1] <= STORM_RAM[1]
    ram = {b.name: (b.start, b.start + b.size) for b in layout.blocks() if b.space == "ram" and b.owner == "carrier"}
    assert ram == {"storm RAM cells": (STORM_RAM[0], MODULE_CELLS[1]), "storm RAM image": IMAGE, "storm RAM data": DATA}
    assert {carrier.SWITCH, carrier.STATE, carrier.PENDING, carrier.LOADKEY} < set(range(STORM_RAM[0], MODULE_CELLS[0]))


def test_the_carrier_blocks(romset_zip, saturn_cue):
    """The stage's ROM blocks: the stub in the boot ROM's erased run after the vector table, the image, data and course data in bank
    3's erased run (spike 70's place), the rain's objects and colour words; all erased on the set before the weather (layout.check);
    what the build uses of each fits, with room left."""
    from tests.test_weather_dry import _seven_dry
    from vrtools.arcade.weather import layout
    dry, _ = _seven_dry(romset_zip, saturn_cue)
    layout.check(dry)
    mine = {b.name: b for b in layout.blocks() if b.owner in ("carrier", "rain") and b.space != "ram"}
    assert set(mine) == {"storm stub", "storm image", "storm data", "storm course data", "rain objects", "rain colours",
                         "rain tones", "the scenery call"}                       # v0.4.1: the drops' colour table, "rain tones"
    assert mine["storm stub"].start == 0xFFF120 and mine["the scenery call"].start == carrier.HOOK_SITE   # after the vector table
    s1 = _stage1(romset_zip, saturn_cue)
    _, rep = carrier.build(s1, carrier.default_modules(s1))
    used = {"storm stub": rep["stub"][1], "storm image": rep["image"][1], "storm course data":
            rep["course_data_end"] - mine["storm course data"].start, "storm data": 2 * 96 * 128}
    for name, n in used.items():
        assert 0 < n <= mine[name].size, (name, n, mine[name].size)


def test_the_dry_path_is_the_switch_test(romset_zip, saturn_cue):
    """The hook site 0xfee144 calls the stub; the stub's first instructions are the DRY path: the weather byte compared with 1, the
    carrier's state with 0, and the game's scenery routine entered by a jump (its return goes straight back to the site): nothing
    else runs in a DRY game. The decision also tests linked play and the menu entry."""
    from tests.test_tgp_build import _seven
    from vrtools.arcade.weather import WEATHER_BYTE, layout
    out, _ = _seven(romset_zip, saturn_cue)
    stub = layout.block("storm stub").start
    assert _listing(out, carrier.HOOK_SITE, 1) == [f"jsr {stub:X}"]
    first = _listing(out, stub, 6)
    assert first[0] == f"cmp.b #1, {WEATHER_BYTE:X}" and first[1].startswith("be ")
    assert first[2] == f"cmp.b #0, {carrier.STATE:X}" and first[3].startswith("bne ") and first[1].split()[1] == first[3].split()[1]
    assert first[4] == f"jmp {carrier.SCENERY:X}"
    wet = _listing(out, int(first[1].split()[1], 16), 12)
    assert f"cmp.b #0, {carrier.LINKED:X}" in wet and f"movz.bw {carrier.MENU:X}, R0" in wet


def test_the_guard_never_touches_the_interrupts(romset_zip, saturn_cue):
    """The fallback round (the clock removed: the test menu's memory test crashed a machine whose vector table had been moved to
    RAM): nothing of the storm moves SBR (no ldpr) or writes the board's interval timer (0xe00008..0xe0000f) or the vector table's
    region of the boot ROM's copy: no block of code the weather emits holds such an instruction. The one thing it does to the
    interrupts (the final review's W8): the load masks them across its copy lists with the game's own pair of instructions, and
    nothing else of the weather touches the PSW. `guard_time` is the prototype's: late
    once the game's vblank count 0x500501 has moved since the pass's wait (the game writes 0 there at the wait's exit, 0xfe1406, so
    within a pass it is 0 until the vblank 17.38 ms in). The fixed quotas: the start places at most START_QUOTA clusters a pass, the
    grade copies GRADE_ROWS rows a pass."""
    from tests.test_tgp_build import _seven
    from vrtools.arcade.disasm import listing_bytes
    from vrtools.arcade.weather import layout, rain
    out, _ = _seven(romset_zip, saturn_cue)
    s1 = _stage1(romset_zip, saturn_cue)
    built, rep = carrier.build(s1, carrier.default_modules(s1))
    from vrtools.arcade.weather import sound
    assert sound.install_board(built) == out                        # the session's set is this build (stage 6: and its sound board)
    stub = layout.block("storm stub")
    code = out.boot[stub.start - V60_BOOT:stub.start - V60_BOOT + rep["common"] - stub.start]
    code_end = min(rep["layout"].tables.values()) - IMAGE[0]       # the image's code (its tables after it are data, not listed)
    image = out.data[3 * 0x100000 + layout.block("storm image").start - 0x100000:][:code_end]
    # every block of code the weather emits (the final review's W7): the storm stub and the image, the handling's stubs, the screens'
    # code, every site; ROM data blocks (colours, the screens' pictures in "screen pieces" and "screen graphics") are not code and are
    # left out (read as code, "screen pieces 2" shows an stpr that is picture bytes). The scan cannot see a register-indirect write to
    # the timer or a vector; the SBR assertion on every storm run (storm_log.lua) covers that at run time.
    blobs = [(code, stub.start, "storm stub"), (image, IMAGE[0], "storm image")]
    for blk in layout.blocks():
        if blk.owner != "carrier" and (blk.space in ("program site", "boot site") or blk.name in ("handling stubs", "screen code")):
            region, base = ("program", 0x200000) if blk.space.startswith("program") else ("boot", V60_BOOT)
            blobs.append((getattr(out, region)[blk.start - base:blk.start - base + blk.size], blk.start, blk.name))
    for blob, base, name in blobs:
        lines = listing_bytes(blob, base)
        text = [" ".join(l.text.split()) for l in lines]
        bad = [t for t in text if t.startswith(("ldpr", "stpr")) or any(r in t for r in ("E00008", "E0000A", "E0000C", "E0000E"))]
        assert bad == [], (name, bad[:5])
        psw = [t for t in text if t.startswith("updpsw")]
        if name == "storm stub":                       # W8: one mask pair, the game's own form, around the load's copy lists only;
            assert psw == ["updpsw.w#0, #40000", "updpsw.w#FFFFFFFF, #40000"], psw
            k0, k1 = text.index(psw[0]), text.index(psw[1])
            inside = text[k0:k1]
            assert any(t.startswith("jsr") for t in inside) and inside[-1].startswith("mov.b R2, E00004"), inside[-4:]
            # the re-review: nothing between the pair leaves it (no return, no jump; a branch only to an address inside the pair),
            # so the unmask is always reached (a jsr returns into it: the copy routine's own returns are its business)
            lo, hi = lines[k0].addr, lines[k1].addr
            out_of_pair = [t for t in inside if t.split()[0] in ("rsr", "ret", "reti", "jmp", "brk", "brkv", "trap", "halt")]
            for t in inside:
                op = t.split()[0]
                if op.startswith("b") and op not in ("bsr", "bset", "btst", "bclr", "bnot") and len(t.split()) == 2:
                    target = int(t.split()[1], 16)
                    if not lo <= target <= hi:
                        out_of_pair.append(t)
            assert out_of_pair == [], out_of_pair
        else:
            assert psw == [], (name, psw)
    assert not hasattr(carrier, "VECTORS") and not hasattr(carrier, "CLOCK_PERIOD")
    b = Block(0x522000)
    carrier.emit_guard_time(b, "late")
    b.label("late")
    assert [" ".join(l.text.split()) for l in listing_bytes(b.bytes(), 0x522000)] == ["cmp.b #0, 500501", f"bne {b.addr('late'):X}"]
    assert rain.START_QUOTA == 20 and rain.GRADE_ROWS == 3 and carrier.UNIT_MAX_US == 200


LOAD_SPIN = 8_000                       # W8: the test-only delay in the load (about 8 ms at 1.01 us a turn: on Bay Bridge the load
                                        # begins 12.1 ms after a vblank, so the next one falls due inside it, and only one)
BW_ENTRY, BW_LOAD, BW_SNAPS = 1, 1606, (1608, 1640, 1700)    # Bay Bridge normal (its data in bank 1: Big Forest and Alpine live in
                                                             # bank 3, where the load's mapping is the course's own); the RAIN
                                                             # race loads on 1606 (every course, W8's twenty loads); pictures after


def test_the_load_spin_is_test_only(romset_zip, saturn_cue):
    """W8: build's test_load_spin (a delay loop inside the load while bank 3 is mapped) is test-only: 0 is the default build byte
    for byte, a spin changes only the storm stub's block, a value outside 0..LOAD_SPIN_MAX (or not an int) is refused."""
    from vrtools.arcade.weather import layout
    s1 = _stage1(romset_zip, saturn_cue)
    mods = carrier.default_modules(s1)
    base, _ = carrier.build(s1, mods)
    same, _ = carrier.build(s1, mods, test_load_spin=0)
    spin, _ = carrier.build(s1, mods, test_load_spin=LOAD_SPIN)
    assert same == base
    stub = layout.block("storm stub")
    assert spin.program == base.program and spin.data == base.data and spin.polygons == base.polygons
    diff = [i for i in range(len(base.boot)) if base.boot[i] != spin.boot[i]]
    assert diff and all(stub.start <= V60_BOOT + i < stub.start + stub.size for i in diff)
    for bad in (-1, carrier.LOAD_SPIN_MAX + 1, 1.5, True, "10"):
        with pytest.raises(PatchError, match="test_load_spin"):
            carrier.build(s1, mods, test_load_spin=bad)


def _bw_log(path):
    out = {"B": [], "W": [], "I": [], "P": {}}
    for row in open(path):
        a = row.split()
        if not a or a[0] == "END":
            continue
        if a[0] == "P":
            out["P"][int(a[1])] = (int(a[2]), int(a[3]))
        elif a[0] == "B":
            out["B"].append((int(a[1]), float(a[2]), int(a[3], 16), int(a[4], 16)))
        elif a[0] == "W":
            out["W"].append((int(a[1]), float(a[2]), int(a[3], 16), int(a[4], 16), int(a[5], 16)))
        elif a[0] == "I":
            out["I"].append((int(a[1]), float(a[2])))
    return out


def test_no_interrupt_reads_the_storms_bank(romset_zip, saturn_cue, tmp_path_factory):
    """W8 (the final review): the game's vblank handler (0xfe02bc) updates the sky backdrop's columns through 0xFFE0E0 -> 0xFFE498 ->
    0x279A76, which read the data bank window, on every vblank around the race's start; the storm's load maps bank 3 there for
    about 45-50 us, 3.6-7.1 ms before the next vblank on the twenty RAIN loads measured. A set whose load holds bank 3 mapped for
    about 8 ms (test_load_spin=LOAD_SPIN) against the normal set, Bay Bridge RAIN (bank_window.lua): a vblank falls due inside it;
    no code outside the stub reads the window while the storm's bank is mapped (the load keeps interrupts masked across its copy
    lists: the vblank is taken when they end); the pictures after the load at BW_SNAPS are the normal set's; no vblank and no pass
    is lost (the game's vblank ticks and the passes the same at every frame end from 1500 to the run's end, but the load's own frame end,
    where the vblank taken late may be counted one frame end later)"""
    from concurrent.futures import ThreadPoolExecutor
    from tests.test_tgp_build import _build
    from vrtools.arcade.course import course_entry_at, road_lines
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.select import WHEEL_FOR_ENTRY
    from vrtools.arcade.weather import layout, sound
    from vrtools.mame.runner import LUA_DIR, run_mame, write_centreline
    s1 = _stage1(romset_zip, saturn_cue)
    mods = carrier.default_modules(s1)
    stub = layout.block("storm stub")
    d = decode_directory(s1)[BW_ENTRY]
    line = [(q.x, q.z) for q in road_lines(s1, course_entry_at(s1, d.bank, window_base=d.header_base))[0]]
    own = (d.bank << 4) | 1
    runs = {}
    bases = {k: tmp_path_factory.mktemp(f"bw_{k}") for k in ("normal", "spin")}   # made here: mktemp is not thread-safe

    def make(kind):
        built, _ = carrier.build(s1, mods, test_load_spin=LOAD_SPIN if kind == "spin" else 0)
        base = bases[kind]
        setdir = _build(base, romset_zip, sound.install_board(built))
        wd = base / "run"
        wd.mkdir()
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[BW_ENTRY]), "VR_RAIN": "1", "VR_HOLD_CLOCK": "1",
               "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", line)), "VR_COLLISION_LOG": str(wd / "c.txt"),
               "VR_SNAPS": ",".join(map(str, BW_SNAPS)), "VR_EXTRA_LUA": str(LUA_DIR / "bank_window.lua"),
               "VR_BW_LOG": str(wd / "bw.txt"), "VR_BW_STUB": f"{stub.start:x},{stub.start + stub.size:x}", "VR_BW_BANK": f"{own:x}",
               "VR_BW_FROM": "1500"}
        run_mame(LUA_DIR / "autoplay.lua", 36, wd, setdir, env=env, timeout=1800)
        runs[kind] = wd
    with ThreadPoolExecutor(2) as ex:
        list(ex.map(make, ("normal", "spin")))
    logs = {k: _bw_log(wd / "bw.txt") for k, wd in runs.items()}
    sp = logs["spin"]
    loads = [b for b in sp["B"] if stub.start <= b[2] < stub.start + stub.size]
    assert loads and loads[0][0] == BW_LOAD and loads[-1][3] == own, loads[:3]
    t0, t1 = loads[0][1], loads[-1][1]
    inside = [t for _, t in sp["I"] if t0 < t < t1]
    after = [t for _, t in sp["I"] if t >= t1]
    due = max(t for _, t in sp["I"] if t <= t0) + 17_383.0  # the next vblank after the one before the load (278 144 cycles a frame)
    summary = (f"load {t1 - t0:.1f} us, a vblank due {due - t0:.1f} us into it, vblank fetches inside {len(inside)}, first after the "
               f"restore {after[0] - t1:.1f} us, window reads with the storm's bank {len(sp['W'])}")
    print(summary)
    assert t0 < due < t1, summary                       # a vblank fell due inside the load
    assert sp["W"] == [] and logs["normal"]["W"] == [], (summary, sp["W"][:5])
    assert inside == [] and after and after[0] - t1 < 50, summary
    # no vblank and no pass lost: the counts equal at every frame end, but at the load's frame end the vblank taken after the
    # unmask (late, not lost) may be counted one frame end later (the measured case: 1 tick, at the frame after the load only)
    pn = logs["normal"]["P"]
    assert len(sp["P"]) == len(pn) >= 500 and sorted(sp["P"]) == sorted(pn)      # 1500 to the run's end
    late = {f: (sp["P"][f], pn[f]) for f in pn if sp["P"][f] != pn[f]}
    assert all(f <= BW_LOAD + 2 and sp["P"][f][1] == pn[f][1] and pn[f][0] - sp["P"][f][0] == 1 for f in late), late
    import numpy as np
    from PIL import Image
    pics = {k: sorted((wd / "snap").rglob("*.png")) for k, wd in runs.items()}
    assert len(pics["spin"]) == len(pics["normal"]) >= len(BW_SNAPS)      # BW_SNAPS and autoplay.lua's own
    for a, b in zip(pics["spin"], pics["normal"]):
        assert np.array_equal(np.asarray(Image.open(a).convert("RGB")), np.asarray(Image.open(b).convert("RGB"))), a.name


def _probe_module():
    """A module as a later stage would add one: cells, a table, per-course data, start / frame / release."""
    def code(lay):
        b = Block(lay.code("probe"))
        b.label("start")
        b.emit("mov.w imm,reg", 0, "r0")
        b.emit("rsr")
        b.label("frame")
        b.emit("add.w imm,abs", 1, lay.cell("probe", "count"))
        b.emit("mov.w abs,reg", lay.table("probe", "tab"), "r1")
        b.emit("mov.w abs,reg", lay.data_at("probe", "per_course"), "r2")
        b.emit("rsr")
        b.label("release")
        b.emit("mov.w imm,abs", 0, lay.cell("probe", "count"))
        b.emit("rsr")
        return b
    return carrier.Module(name="probe", code=code, cells=(("count", 8),), tables=(("tab", b"\x11\x22\x33\x44"),),
                          course_data=lambda e: {"per_course": bytes([e + 1]) * 6}, start="start", frame="frame", release="release")


def test_a_module_adds_code_cells_and_course_data(romset_zip, saturn_cue):
    """A module registered after the rain gets cells after the rain's (zeroed with them at the load), its code and table in the image
    (stored in bank 3, copied to IMAGE), its per-course data in bank 3 and in every entry's copy list to its one DATA place; the
    carrier's pass calls its start and frame after the rain's, its release before the rain's (reverse order)."""
    s1 = _stage1(romset_zip, saturn_cue)
    mods = carrier.default_modules(s1) + [_probe_module()]
    out, rep = carrier.build(s1, mods)
    lay = rep["layout"]
    assert lay.cell("probe", "count") >= lay.cell("rain", "pool") + 16 * 40 and lay.carrier["cells_end"] <= MODULE_CELLS[1]
    img = out.data[3 * 0x100000 + 0x1DF4C0 - 0x100000:][:rep["image"][1]]                  # the storm image in bank 3
    code = mods[-1].code(lay).bytes()                                       # the probe (after the registry's modules)
    off = lay.code("probe") - IMAGE[0]
    assert img[off:off + len(code)] == code
    toff = lay.table("probe", "tab") - IMAGE[0]
    assert img[toff:toff + 4] == b"\x11\x22\x33\x44"
    dst = lay.data_at("probe", "per_course")
    for e, at in rep["lists"].items():
        recs = []
        while True:
            w = struct.unpack_from("<I", out.boot, at - V60_BOOT)[0]
            if w == 0:
                break
            recs.append(struct.unpack_from("<4I", out.boot, at - V60_BOOT))
            at += 16
        mine = [r for r in recs if r[2] == dst]
        assert len(mine) == 1 and mine[0][0] == 0x31 and mine[0][3] == 3, (e, mine)
        src = 3 * 0x100000 + mine[0][1] - 0x100000
        assert out.data[src:src + 6] == bytes([e + 1]) * 6
    from vrtools.arcade.disasm import listing_bytes
    image = bytes(img)
    calls = [" ".join(l.text.split()) for l in listing_bytes(image[:off], IMAGE[0]) if l.text.startswith("jsr")]
    order = [c.split()[1] for c in calls]
    want = {k: f"{lay.label(m, k2):X}" for k, (m, k2) in {"rs": ("rain", "start"), "ps": ("probe", "start"), "rf": ("rain", "frame"),
                                                         "pf": ("probe", "frame"), "rr": ("rain", "release"),
                                                         "pr": ("probe", "release")}.items()}
    assert [o for o in order if o in want.values()] == [want[k] for k in ("rs", "ps", "rf", "pf", "pr", "rr")], order


PROBE_SITE = 0xFEE13E                   # `jsr FF7C1E[PC]`, the race scene's call before the scenery call: every race pass
PROBE_SITE_BYTES = bytes.fromhex("e8f2e09a0000")
PROBE_CALLEE = 0xFF7C1E
PROBE_STUB = 0xFFF700                   # in the boot ROM's erased run after the storm stub's block (0xfff6e0..0xfffea0)


def _probe_blocks(owner="probe"):
    """The dummy module's two blocks, as a later stage adds its own to weather/layout.py's table: its hook site and its stub."""
    from vrtools.arcade.weather import layout
    return [layout.Block("probe site", "boot site", PROBE_SITE, len(PROBE_SITE_BYTES), owner),
            layout.Block("probe stub", "boot", PROBE_STUB, 0x40, "probe")]


def _probe_site_module(original=PROBE_SITE_BYTES):
    """The dummy module with a hook site (F1): the site's `jsr FF7C1E` becomes `jsr PROBE_STUB`; the stub, in the boot ROM, tests the
    weather byte, then SWITCH, and calls the module's RAM routine `hit` (it counts in the cell `hits`), then jumps to the site's
    original callee: its dry path is the site's own call."""
    from vrtools.arcade.weather import WEATHER_BYTE
    from vrtools.arcade.v60asm import asm
    base = _probe_module()

    def code(lay):
        b = base.code(lay)
        b.label("hit")
        b.emit("add.w imm,abs", 1, lay.cell("probe", "hits"))
        b.emit("rsr")
        return b

    def stub(lay):
        b = Block(PROBE_STUB)
        b.emit("cmp.b imm,abs", 1, WEATHER_BYTE)
        b.branch("bne", "dry")
        b.emit("cmp.b imm,abs", 0, carrier.SWITCH)
        b.branch("be", "dry")
        b.emit("jsr abs", lay.label("probe", "hit"))
        b.label("dry")
        b.emit("jmp abs", PROBE_CALLEE)
        return (("probe stub", b.bytes()),)
    return replace(base, code=code, cells=base.cells + (("hits", 4),), entries=("hit",), rom=stub,
                   sites=lambda lay: (("probe site", original, asm("jsr abs", PROBE_STUB)),))


def probe_build(s1):
    """The weather set with the dummy hook-site module after the rain: (set, report). Its MAME run is storm_runs' ("probe", ...)."""
    from vrtools.arcade.weather import layout
    return carrier.build(s1, carrier.default_modules(s1) + [_probe_site_module()], table=layout.blocks() + _probe_blocks())


def test_a_module_adds_a_hook_site(romset_zip, saturn_cue):
    """F1: a module declares a hook site, a named block of the layout table (`build`'s `table`: weather/layout.py's blocks and a later
    stage's own), its original bytes and new bytes made from the settled Layout; its stub in an erased block of the boot ROM, made
    from the Layout too (it calls the module's RAM routine `hit`, an exported entry). Built: the site calls the stub, the stub tests
    the weather byte, then SWITCH, calls `hit` and jumps to the site's original callee. Refused, naming the site, the set untouched:
    the site's bytes not the original; the site's block not in the table; the block another module's; new bytes of another length;
    the site declared twice (both would pass the bytes check, the last write winning)."""
    from vrtools.arcade.v60asm import asm
    from vrtools.arcade.weather import WEATHER_BYTE, layout
    s1 = _stage1(romset_zip, saturn_cue)
    assert s1.boot[PROBE_SITE - V60_BOOT:][:6] == PROBE_SITE_BYTES
    before = (s1.boot, s1.program)
    out, rep = probe_build(s1)
    lay = rep["layout"]
    assert out.boot[PROBE_SITE - V60_BOOT:][:6] == asm("jsr abs", PROBE_STUB)
    from vrtools.arcade.disasm import listing
    stub = listing(out, PROBE_STUB, 6)
    dry = f"{stub[5].addr:X}"                                       # the dry path: the jump to the site's original callee
    assert [" ".join(l.text.split()) for l in stub] == [f"cmp.b #1, {WEATHER_BYTE:X}", f"bne {dry}", f"cmp.b #0, {carrier.SWITCH:X}",
                                                        f"be {dry}", f"jsr {lay.label('probe', 'hit'):X}", f"jmp {PROBE_CALLEE:X}"]
    plain, _ = carrier.build(s1, carrier.default_modules(s1))
    from vrtools.arcade.weather import handling
    sb = layout.block("storm stub")
    jumps = {handling.stub_labels()[s.name] + 22 + k for s in handling.SITES for k in range(4)}   # each handling stub's `jmp` operand
    diff = [V60_BOOT + k for k in range(len(out.boot)) if out.boot[k] != plain.boot[k]]
    assert diff and all(PROBE_SITE <= a < PROBE_SITE + 6 or PROBE_STUB <= a < PROBE_STUB + 0x40 or sb.start <= a < sb.start + sb.size
                        or a in jumps
                        for a in diff)                      # the storm stub's own: more cells to zero, longer copy lists; stage 5's
                                                            # handling stubs: only their jumps' targets in the image, which the probe moves
    assert all(out.boot[handling.stub_labels()[s.name] + 20 - V60_BOOT:][:2] == b"\xd6\xf3" for s in handling.SITES)   # jmp abs there
    bad = bytearray(s1.boot)
    bad[PROBE_SITE - V60_BOOT + 3] ^= 0xFF
    cases = {"the site's bytes": (replace(s1, boot=bytes(bad)), _probe_site_module(), layout.blocks() + _probe_blocks()),
             "no block": (s1, _probe_site_module(), layout.blocks() + _probe_blocks()[1:]),
             "another's block": (s1, _probe_site_module(), layout.blocks() + _probe_blocks(owner="rain")),
             "another length": (s1, _probe_site_module(original=PROBE_SITE_BYTES[:4]), layout.blocks() + _probe_blocks())}
    twice = replace(_probe_site_module(), sites=lambda lay: (("probe site", PROBE_SITE_BYTES, asm("jsr abs", PROBE_STUB)),) * 2)
    cases["declared twice"] = (s1, twice, layout.blocks() + _probe_blocks())
    for what, (rs, mod, table) in cases.items():
        with pytest.raises(PatchError, match="probe site"):
            carrier.build(rs, carrier.default_modules(rs) + [mod], table=table)
    with pytest.raises(PatchError, match="declared twice"):
        carrier.build(s1, carrier.default_modules(s1) + [twice], table=layout.blocks() + _probe_blocks())
    assert (s1.boot, s1.program) == before


def test_the_converted_courses_reach_the_modules(romset_zip, saturn_cue, monkeypatch):
    """F1: `install(rs, converted)` hands `converted` to every module factory of the registry (carrier.REGISTRY, in frame order)."""
    from tests.test_weather_dry import _seven_dry
    s1 = _stage1(romset_zip, saturn_cue)
    _, conv = _seven_dry(romset_zip, saturn_cue)
    seen = []

    def factory(rs, converted, tune):
        seen.append(converted)
        return _probe_module()
    monkeypatch.setattr(carrier, "REGISTRY", carrier.REGISTRY + [factory])
    carrier.install(s1, conv)
    assert seen == [conv]


def test_a_module_reads_another_modules_cell_by_name():
    """The rider: one module's code reads a cell another module owns by name (`lay.cell(owner, name)`: stage 4 reading stage 3's,
    stage 6 stage 4's), whatever their order in the registry; the owner absent, the layout raises PatchError naming the cell; a small
    stand-in module declaring that cell (a builder's test) satisfies it. The routines run in registry order (start, frame), release
    in reverse. No ROM needed: `lay_out` only."""
    def owner(name="lightning"):
        def code(lay):
            b = Block(lay.code(name))
            b.label("frame")
            b.emit("mov.w imm,abs", 1, lay.cell(name, "flash"))
            b.emit("rsr")
            return b
        return carrier.Module(name=name, code=code, cells=(("flash", 4),), frame="frame")

    def reader(lay):
        b = Block(lay.code("handling"))
        b.label("frame")
        b.emit("mov.w abs,reg", lay.cell("lightning", "flash"), "r0")
        b.emit("rsr")
        return b
    reads = carrier.Module(name="handling", code=reader, frame="frame")
    for mods in ([owner(), reads], [reads, owner()]):
        lay = carrier.lay_out(mods)[0]
        flash = lay.cell("lightning", "flash")
        assert MODULE_CELLS[0] <= flash < MODULE_CELLS[1]
        code = reads.code(lay).bytes()
        assert struct.pack("<I", flash) in code                     # the reader's instruction holds the owner's cell
    with pytest.raises(PatchError, match="flash"):
        carrier.lay_out([reads])
    stand_in = carrier.Module(name="lightning", code=lambda lay: Block(lay.code("lightning")), cells=(("flash", 4),))
    lay = carrier.lay_out([stand_in, reads])[0]
    assert lay.cell("lightning", "flash") == MODULE_CELLS[0]


def test_the_layout_lookups_are_strict(romset_zip, saturn_cue):
    """M2: `Layout.cell` and `Layout.data_at` raise PatchError naming an unknown name, as `label`, `table` and `code` do."""
    s1 = _stage1(romset_zip, saturn_cue)
    lay = carrier.lay_out(carrier.default_modules(s1))[0]
    first = carrier.default_modules(s1)[0]                    # stage 3: the cover's cells come first, its tables per course only
    assert lay.cell(first.name, first.cells[0][0]) == MODULE_CELLS[0] and lay.data_at("rain", "overcast") == DATA[0]
    for f, name in ((lay.cell, "stat"), (lay.data_at, "overcats")):
        with pytest.raises(PatchError, match=name):
            f("rain", name)


def test_a_block_past_its_region_is_refused(romset_zip, saturn_cue):
    """M3: a block reaching past its ROM region's end (inside its space's bounds) is refused by layout.rom_bytes / erased and by the
    carrier's writer, which would otherwise take the short slice for erased and grow the region."""
    from vrtools.arcade.weather import layout
    s1 = _stage1(romset_zip, saturn_cue)
    n = len(s1.polygons)
    past = layout.Block("past the end", "polygon", n - 8, 16, "rain")
    tail = replace(s1, polygons=s1.polygons[:-8] + b"\xff" * 8)
    for f in (layout.rom_bytes, layout.erased):
        with pytest.raises(PatchError, match="past the end"):
            f(tail, past)
    parts = {"polygons": bytearray(tail.polygons)}
    with pytest.raises(PatchError, match="past"):
        carrier._put(parts, "polygon", n - 8, b"\0" * 16)
    assert len(parts["polygons"]) == n


def test_a_copy_from_outside_the_bank_window_is_refused(romset_zip, saturn_cue):
    """M4: a module's per-course copy whose source is not inside the bank window (0x100000..0x1fffff) or whose bank the set has not
    is refused, naming it."""
    s1 = _stage1(romset_zip, saturn_cue)
    rain = carrier.default_modules(s1)

    def code(lay):
        b = Block(lay.code("probe"))
        b.label("frame")
        b.emit("rsr")
        return b
    for name, copy in (("over_the_end", (3, 0x1FFFF0, 0x40)), ("below_the_window", (3, 0xFFFF0, 0x10)),
                       ("no_such_bank", (len(s1.data) // 0x100000, 0x100000, 0x10))):
        mod = carrier.Module(name="probe", code=code, course_copies=lambda e, n=name, c=copy: {n: c}, frame="frame")
        with pytest.raises(PatchError, match=name):
            carrier.build(s1, rain + [mod])


def test_a_copy_into_an_image_table_is_checked(romset_zip, saturn_cue):
    """Task 8: a per-course copy named carrier.TABLE_COPY + <table> lands in the module's own image table (after the common list);
    one naming no table of the module's, one longer than the table, and an odd-length one at the table's length (the records copy
    whole halfwords: one byte past it) are refused naming it; one that fits lands at the table's RAM address."""
    s1 = _stage1(romset_zip, saturn_cue)
    rain = carrier.default_modules(s1)

    def code(lay):
        b = Block(lay.code("probe"))
        b.label("frame")
        b.emit("rsr")
        return b
    for tab, name, copy, err in ((b"\0" * 8, "@nosuch", (3, 0x100000, 8), "names no image table"),
                                 (b"\0" * 8, "@tab", (3, 0x100000, 10), "does not fit"),
                                 (b"\0" * 7, "@tab", (3, 0x100000, 7), "does not fit")):
        mod = carrier.Module(name="probe", code=code, tables=(("tab", tab),), frame="frame",
                             course_copies=lambda e, n=name, c=copy: {n: c})
        with pytest.raises(PatchError, match=err):
            carrier.build(s1, rain + [mod])
    mod = carrier.Module(name="probe", code=code, tables=(("tab", b"\0" * 8),), frame="frame",
                         course_copies=lambda e: {"@tab": (3, 0x100000, 8)})
    out, rep = carrier.build(s1, rain + [mod])
    at = rep["lists"][0]
    dsts = []
    while struct.unpack_from("<I", out.boot, at - V60_BOOT)[0]:
        dsts.append(struct.unpack_from("<4I", out.boot, at - V60_BOOT)[2:])
        at += 16
    assert (rep["layout"].table("probe", "tab"), 4) in dsts


def test_the_report_gives_the_data_end(romset_zip, saturn_cue):
    """M5: the build report's `data_end` is the end of the storm's RAM data (the last place's start plus its size: the rain's own sky,
    512 colours at most), inside DATA."""
    s1 = _stage1(romset_zip, saturn_cue)
    _, rep = carrier.build(s1, carrier.default_modules(s1))
    lay = rep["layout"]
    assert max(lay.data.values()) == lay.data_at("rain", "own")
    assert rep["data_end"] == lay.data_at("rain", "own") + 2 * 512 <= DATA[1]


def test_the_room_table(romset_zip, saturn_cue):
    """F2: `layout.room` (the findings' table of the room left, generated) gives the carrier's own figures for its blocks: the stub
    and its lists, the image, the static tables, the course data, the rain's objects and colour words; the RAM blocks as laid out."""
    from tests.test_tgp_build import _seven
    from vrtools.arcade.weather import layout, rain
    out, _ = _seven(romset_zip, saturn_cue)
    s1 = _stage1(romset_zip, saturn_cue)
    _, rep = carrier.build(s1, carrier.default_modules(s1))
    used = {name: u for name, _, _, _, u in layout.room(out, rep)}
    from vrtools.arcade.weather.tune import RainTune
    objs, sobjs = rain.drop_objects(RainTune())[0], rain.splash_objects(6)
    assert used["storm stub"] == rep["stub"][1] and used["storm image"] == rep["image"][1] == used["storm RAM image"]
    assert used["storm data"] == 2 * 96 * 128 and used["storm course data"] == rep["course_data_end"] - layout.block("storm course data").start
    assert used["rain objects"] == len(b"".join(objs + sobjs)) and used["rain colours"] == 2 * 12 and used["rain tones"] == 2 * 4 * 29
    assert used["storm RAM cells"] == rep["layout"].carrier["cells_end"] - STORM_RAM[0] and used["storm RAM data"] == rep["data_end"] - DATA[0]
    assert used["the scenery call"] == 6 and all(u <= size for _, _, _, size, u in layout.room(out, rep))


def test_the_copy_lists(romset_zip, saturn_cue):
    """The common list copies the image and the static tables from bank 3 to their RAM; each entry's list its grey sky (bank 3) and
    its own backdrop colours from its own bank (the reverse variant's are the same block); the bank table names each entry's bank."""
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.weather import rain
    s1 = _stage1(romset_zip, saturn_cue)
    out, rep = carrier.build(s1, carrier.default_modules(s1))
    lay = rep["layout"]

    def records(at):
        out_ = []
        while (w := struct.unpack_from("<I", out.boot, at - V60_BOOT)[0]) != 0:
            out_.append(struct.unpack_from("<4I", out.boot, at - V60_BOOT))
            at += 16
        return out_
    common = records(rep["common"])
    assert [(r[0], r[2], r[3]) for r in common] == [(0x31, IMAGE[0], rep["image"][1] // 2), (0x31, lay.data_at("rain", "overcast"), 96 * 64),
                                                    (0x31, lay.data_at("rain", "boot"), 96 * 64),
                                                    (0x31, lay.data_at("lightning", "whiteout"), 96 * 64)]     # stage 4
    dirs = decode_directory(out)
    for e, d in enumerate(dirs):
        bank, src, n, cols = rain.course_sky(out, e)
        recs = records(rep["lists"][e])
        assert (recs[0][0], recs[0][2]) == (0x31, lay.data_at("cover", "table"))   # stage 3: the cover's table first (its module first)
        recs = [r for r in recs[1:] if r[2] not in (lay.data_at("lightning", "course"), lay.table("lightning", "dirs"))]  # stage 4's
        # blob and task 8's per-course aim (Metropolis's direction table into the image's): the lightning's own tests
        assert [(r[0], r[2], r[3]) for r in recs] == [(0x31, lay.data_at("rain", "sky"), 4 + n), ((bank << 4) | 1, lay.data_at("rain", "own"), n)]
        assert recs[1][1] == src and out.boot[rep["banktab"] - V60_BOOT + e] == (d.bank << 4) | 1
        if d.reverse is not None:
            assert d.reverse.entry.bank == d.bank and rain.course_sky(out, e)[1] == src


def test_install_checks_the_hook_site(romset_zip, saturn_cue):
    """The scenery call holding other bytes than the game's `jsr FF8450[PC]` makes the install raise, naming it."""
    s1 = _stage1(romset_zip, saturn_cue)
    boot = bytearray(s1.boot)
    boot[carrier.HOOK_SITE - V60_BOOT + 2] ^= 0xFF
    with pytest.raises(PatchError, match="scenery call"):
        carrier.install(replace(s1, boot=bytes(boot)))


# ---- MAME -----------------------------------------------------------------------------------------------------------------
SBR_BOOT = 0xFFF000                     # the vector table base the boot sets (0xfe01d5) and the storm never changes
BOOT_DONE = 300                         # the boot's RAM clear (0xfe1469, frame 271) and its one write of the timer are before this


def test_dry_runs_no_storm_code(storm_runs, record_property):
    """A DRY race (Big Forest) and 200 s of the attract on the weather set, traced from the boot's end on: no write into the storm's
    RAM, no write to the interval timer, SBR the boot's (0xfff000) and the carrier IDLE at every pass. The switch test's cost: the
    same DRY race on the switch-off set, pass for pass from the load (the game's state is the same: test_weather_dry): the set's V60
    busy time over it by a few microseconds on the mean and median pass, measured on the set without the game-changing modules
    (stage 5: the wet handling's hooks in the game's code have their own bound, tests/test_weather_handling.py::test_the_hooks_cost)."""
    for key in (("dry_trace",), ("attract_trace",)):
        r = storm_runs.run(*key)
        S = [p for p in r.storm.passes if p.frame > BOOT_DONE]
        assert len(S) > 1500 and all(p.state == 0 and p.switch == 0 and p.sbr == SBR_BOOT for p in S), key
        assert [t for t in r.storm.traces if t[0] > BOOT_DONE] == [], (key, [t for t in r.storm.traces if t[0] > BOOT_DONE][:3])
    wet, main = storm_runs.run("dry_same"), storm_runs.run("dry_main")     # the switch test alone: the set without the game-changing
                                                                         # modules (stage 5's hooks have their own bound: test_the_hooks_cost)
    a = {f.frame: f.busy_us for f in wet.frames if f.frame >= wet.start}
    b = {f.frame: f.busy_us for f in main.frames if f.frame >= main.start}
    common = sorted(set(a) & set(b))
    assert wet.start == main.start and len(common) > 1000
    d = [a[f] - b[f] for f in common]
    mean = sum(d) / len(d)
    record_property("switch_test_us_mean", round(mean, 2))
    with open(storm_runs.base / "rain_summary.txt", "a") as out:
        out.write(f"DRY switch test: {len(d)} race passes, busy difference set - switch-off mean {mean:.2f} us, median "
                  f"{sorted(d)[len(d) // 2]}, min {min(d)}, max "
                  f"{max(d)}; attract busiest (outside its scene loads) "
                  f"{max(f.busy_us for f in storm_runs.run('attract_trace').frames if f.busy_us < 34_770) / 1000:.2f} ms\n")
    median = sorted(d)[len(d) // 2]                                 # single passes jitter by tens of us either way (the vblank
    assert 0 <= mean <= 10 and 0 <= median <= 10, (mean, median, min(d), max(d))   # interrupt landing elsewhere in the work)


def _released(r, after):
    """The first pass after frame `after` at which the storm is IDLE again."""
    return next(p for p in r.storm.passes if p.frame > after and p.state == 0)


def _sky(storm_runs, entry):
    from vrtools.arcade.weather import rain
    bank, src, n, cols = rain.course_sky(storm_runs.rate.out, entry)
    return n, cols, rain.grey_sky(cols, entry == rain.METROPOLIS)


def _tables():
    from vrtools.arcade.weather import rain
    return rain.overcast_table().reshape(96, 64).tolist(), rain.boot_table().reshape(96, 64).tolist()


def _x(dump):
    return np.array(dump["X"]).reshape(96, 64).tolist()


def _first_shows_and_releases(r):
    """F4: in a run with RAIN games, each game's first visible rain pass (the sky copy and the grade's start, before its first guard
    test) at most RAIN_BUSY_MAX_MS and neither it nor the next pass stale; each release pass (the state to IDLE: one unit,
    carrier.RELEASE_US_MAX) the attract's opening scene load, a pass of two vblanks and more (the game's own: the DRY twin of
    test_nothing_of_the_storm_shows_after_its_modes is as long but for the release), itself not stale. Returns (firsts, releases)."""
    from vrtools.mame.framerate import FRAME_US
    stale = set(parse_stale_log(r.wd / "stale_list.txt"))
    busy = {f.frame: f.busy_us for f in r.frames}
    nxt = {a.frame: b.frame for a, b in zip(r.frames, r.frames[1:])}
    firsts, releases, prev = [], [], None
    for p in r.storm.passes:
        if p.state == 2 and p.drawn > 0 and (not firsts or any(q.state == 0 for q in r.storm.passes if firsts[-1] < q.frame < p.frame)):
            firsts.append(p.frame)
        if prev is not None and prev.state != 0 and p.state == 0:
            releases.append(p.frame)
        prev = p
    assert firsts, "no visible rain"
    for f in firsts:
        assert busy[f] <= RAIN_BUSY_MAX_MS * 1000 and f not in stale and nxt[f] not in stale, (f, busy[f], sorted(stale & {f, nxt[f]}))
    for f in releases:
        modes = [x[1] for x in r.storm.frames if x[0] <= f]
        assert modes[-1] == 0x02 and busy[f] >= FRAME_US and f not in stale, (f, hex(modes[-1]), busy[f], f in stale)
    return firsts, releases


def test_a_rain_race_ends_clean(storm_runs):
    """RAIN on Big Forest to its end (race_end.lua: one lap, the results), the attract, then a DRY game. Mid-race the storm is on
    (the colour RAM holds the overcast table, the backdrop the course's grey); at the first scenery call after the race (the
    attract's opening, mode 0x2) everything is put back: the colour RAM the boot's table, the backdrop the course's own, SBR the
    boot's, the carrier IDLE and its switch 0; from then on nothing of the storm runs (no write into its RAM) through the attract.
    F4: the first visible rain pass within the cap and not stale; the release pass the attract's opening scene load, not stale."""
    r = storm_runs.run("end", "dry")
    T0, TB = _tables()
    n, own, grey = _sky(storm_runs, 0)
    mid = r.storm.dumps[END_DUMPS[0]]
    assert _x(mid) == T0 and mid["P"][:n] == grey
    loads = [int(l.split()[1]) for l in open(r.wd / "end.txt") if l.startswith("L ")]
    results = next(int(l.split()[1]) for l in open(r.wd / "end.txt") if l.startswith("T "))
    rel = _released(r, results)
    assert rel.switch == 0 and rel.sbr == SBR_BOOT and rel.loads == 1 and rel.frame < loads[1], (rel, loads)
    dump = r.storm.dumps[rel.frame + 2]
    assert _x(dump) == TB and dump["P"][:n] == own
    assert [t for t in r.storm.traces if rel.frame < t[0] < loads[1]] == []
    assert all(p.state == 0 and p.sbr == SBR_BOOT for p in r.storm.passes if rel.frame <= p.frame < loads[1])
    assert _first_shows_and_releases(r)[1][:1] == [rel.frame]


def test_time_over_mid_rain_ends_clean(storm_runs):
    """RAIN on Big Forest, the race ended by time over TOVER_AFTER frames after its start, splashes on the road and the grade made:
    released at the first scenery call off the rain's modes or the race (the colour RAM the boot's table, the backdrop the course's
    own, SBR the boot's), and nothing of the storm runs after. F4: the first visible pass and the release pass as
    `_first_shows_and_releases`."""
    r = storm_runs.run("tover")
    T0, TB = _tables()
    n, own, grey = _sky(storm_runs, 0)
    before = r.storm.dumps[1600 + TOVER_AFTER - 10]
    assert _x(before) == T0 and before["P"][:n] == grey
    on = [p for p in r.storm.passes if p.state == 2 and p.active]
    assert on and max(p.splashes for p in on[-60:]) > 0
    rel = _released(r, on[-1].frame)
    assert rel.sbr == SBR_BOOT and rel.switch == 0
    dump = r.storm.dumps[rel.frame + 2]
    assert _x(dump) == TB and dump["P"][:n] == own
    assert [t for t in r.storm.traces if t[0] > rel.frame] == [] and all(p.state == 0 for p in r.storm.passes if p.frame >= rel.frame)
    assert _first_shows_and_releases(r)[1] == [rel.frame]


def test_a_second_game_starts_clean(storm_runs):
    """After a RAIN game on Big Forest: a DRY game on Metropolis runs nothing of the storm (no write into its RAM, the carrier IDLE,
    SBR the boot's through its race); a RAIN game on Alpine loads again (a second load, the cells zeroed: its start passes place the
    clusters anew) with Alpine's grey sky, and rains as the first. F4: both games' first visible passes and the release between them
    as `_first_shows_and_releases`."""
    dry = storm_runs.run("end", "dry")
    loads = [int(l.split()[1]) for l in open(dry.wd / "end.txt") if l.startswith("L ")]
    assert len(loads) == 2
    after = [p for p in dry.storm.passes if p.frame >= loads[1]]
    assert len(after) > 1000 and all(p.state == 0 and p.switch == 0 and p.sbr == SBR_BOOT and p.loads == 1 for p in after)
    assert [t for t in dry.storm.traces if t[0] >= loads[1]] == []
    wet = storm_runs.run("end", "rain")
    loads = [int(l.split()[1]) for l in open(wet.wd / "end.txt") if l.startswith("L ")]
    second = [p for p in wet.storm.passes if p.frame >= loads[1]]
    released = [p for p in wet.storm.passes if p.frame < loads[1] and p.state == 0 and p.loads == 1]
    assert released, "no release between the two games"
    starts = [p for p in second if p.state == 1]
    assert starts and starts[0].loads == 2 and starts[0].primed == 0 and starts[0].drawn == 0
    shows = [p for p in second if p.state == 2 and p.active]
    assert len(shows) > 1000 and sorted(p.drawn for p in shows)[len(shows) // 2] == 60
    T0, TB = _tables()
    n, own, grey = _sky(storm_runs, 3)
    dump = wet.storm.dumps[END_DUMPS[1]]
    assert _x(dump) == T0 and dump["P"][:n] == grey
    firsts, releases = _first_shows_and_releases(wet)
    assert len(firsts) == 2 and releases[0] == released[0].frame and firsts[0] < releases[0] < loads[1] < firsts[1]


def test_an_unknown_label_is_refused_once_the_layout_settles(romset_zip, saturn_cue):
    """A module asking the Layout for a label no module has (a typo a later stage could make), or a table or code of no module, makes
    the layout raise PatchError naming it once the addresses have settled (before, every lookup is a placeholder of the same
    encoding); the labels that exist (another module's start, frame, release) are given."""
    s1 = _stage1(romset_zip, saturn_cue)
    rain_mods = carrier.default_modules(s1)

    def asking(what):
        def code(lay):
            b = Block(lay.code("probe"))
            b.label("frame")
            b.emit("jsr abs", lay.label("rain", "frame"))
            b.emit("jsr abs", {"label": lambda: lay.label("rain", "frmae"), "table": lambda: lay.table("rain", "dorps"),
                               "code": lambda: lay.code("cloud")}[what]())
            b.emit("rsr")
            return b
        return carrier.Module(name="probe", code=code, frame="frame")
    for what, name in (("label", "frmae"), ("table", "dorps"), ("code", "cloud")):   # stage 6: "lightning" has a stand-in now
        with pytest.raises(PatchError, match=name):
            carrier.lay_out(rain_mods + [asking(what)])
    ok = carrier.Module(name="probe", code=lambda lay: _probe_module().code(lay), cells=(("count", 8),), tables=(("tab", b"1234"),),
                        course_data=lambda e: {"per_course": b"\0" * 6}, frame="frame")
    lay = carrier.lay_out(rain_mods + [ok])[0]
    assert lay.settled and lay.label("rain", "release") > IMAGE[0]
    with pytest.raises(PatchError, match="nope"):
        lay.label("rain", "nope")


# ---- B4 (the fallback round): the TEST menu, a soft reset, three games --------------------------------------------------------
BOOT_CLEAR = 0xFE1469                   # the boot's RAM clear (0x500000..0x53efff): its writes into the storm RAM are the boot's


def _mode_changes(frames, after):
    """(frame, mode) at each change of the mode byte in storm_log's F lines, from frame `after` on."""
    out, last = [], None
    for f, mode, *_ in frames:
        if mode != last:
            if f > after:
                out.append((f, mode))
            last = mode
    return out


def _clean_after(r, frame):
    """From `frame` on: every F line idle (state 0, switch 0), SBR the boot's; no write into the storm RAM after the first pass line
    from there (that one counts every write since the last pass before the menu: the memory test's, the boot's clear)."""
    late = [x for x in r.storm.frames if x[0] >= frame]
    assert late and all(x[2] == 0 and x[3] == 0 and x[4] == SBR_BOOT for x in late), [x for x in late if x[2] or x[3]][:3]
    first = next(p.frame for p in r.storm.passes if p.frame >= frame)
    assert [t for t in r.storm.traces if t[0] > first] == []


def test_the_test_menu_from_a_rain_race(storm_runs):
    """The TEST switch in a RAIN race (Big Forest, the storm live), the menu's MEMORY TEST run to its end (it writes test patterns over
    all of 0x500000..0x53ffff, the storm's RAM included), escaped, then EXIT: the machine runs on (the first build, which had moved
    the interrupt table into RAM, stopped there), the game reboots and from then on is the game main's set plays under the same
    inputs (its race DRY: the switch-off set): the same modes on the same frames; the storm idle, SBR the boot's at every frame."""
    wet, main = storm_runs.run("svc", "rain"), storm_runs.run("svc", "main")
    assert any(x[2] == 2 for x in wet.storm.frames if x[0] < 2500), "the storm was not live when TEST was pressed"
    assert all(x[4] == SBR_BOOT for x in wet.storm.frames)
    reboot = next(f for f, mode in _mode_changes(wet.storm.frames, SVC_EXIT) if mode == 0)
    assert _mode_changes(wet.storm.frames, SVC_EXIT) == _mode_changes(main.storm.frames, SVC_EXIT)
    assert {m for _, m in _mode_changes(wet.storm.frames, reboot)} >= {0x02, 0x03}
    _clean_after(wet, reboot + 4)


def test_the_test_switch_after_a_rain_race(storm_runs):
    """The TEST switch in the results after a RAIN race (race_end.lua's lap: the storm still live in mode 0x1c, before its release at
    the attract), then EXIT: the game reboots, the attract plays, the storm idle and SBR the boot's from the reboot on."""
    r = storm_runs.run("svc", "window")
    at = [x for x in r.storm.frames if x[0] <= WINDOW_TEST]
    assert at[-1][1] == 0x1C and at[-1][2] == 2, at[-1]
    reboot = next(f for f, mode in _mode_changes(r.storm.frames, WINDOW_EXIT) if mode == 0)
    assert {m for _, m in _mode_changes(r.storm.frames, reboot)} >= {0x02, 0x03}
    _clean_after(r, reboot + 4)


def test_a_soft_reset_during_and_after_a_rain_race(storm_runs):
    """MAME's soft reset during a RAIN race (the storm drawing) and in the results after one (the storm live, not yet released). A soft
    reset runs the autoboot scripts again: the new storm logger reopens the log and counts frames from 1 again, while the old one
    (still running) writes its own frames from the reset's on; so the frames below the reset's are the new logger's, from the reset
    on. At the reset's first frame end the storm's state is still in RAM (state 2: it was live); by the third the boot has cleared it
    (it is not taken for loaded); from then on idle and SBR the boot's, through the attract, until a load of a new race."""
    for key, at in ((("reset", "race"), RESET_RACE), (("reset", "window"), RESET_WINDOW)):
        r = storm_runs.run(*key)
        assert [l for l in open(r.wd / "test.txt") if l.startswith("R ")] == [f"R {at}\n"], key
        fr = [x for x in r.storm.frames if x[0] < at]
        assert fr[0][0] == 1 and fr[0][2] == 2, (key, fr[:2])
        cleared = next(x for x in fr if x[2] == 0)
        load = next((x[0] for x in fr if x[1] == 0x11), 1 << 30)
        assert cleared[0] <= 4 and all(x[2] == 0 and x[3] == 0 and x[4] == SBR_BOOT for x in fr if cleared[0] <= x[0] < load), key
        assert {m for _, m in _mode_changes(fr, cleared[0]) if _ < load} >= {0x02, 0x03}, key


def test_three_games_rain_dry_rain(storm_runs):
    """A coin and START at the attract straight after a RAIN game (race_end.lua: 60 frames after the attract opens, the earliest a
    game can start), three games: RAIN on Big Forest, DRY on Metropolis, RAIN on Alpine. Released at the attract's first scenery call
    before the second game; nothing of the storm runs or is written in the DRY game; loaded again (cells zeroed) for the third; in
    each RAIN game the overcast table in the colour RAM and that course's grey sky, between them the boot's table and the course's own
    sky; SBR the boot's throughout. F4: the first visible passes and the release as `_first_shows_and_releases`."""
    r = storm_runs.run("chain")
    loads = [int(l.split()[1]) for l in open(r.wd / "end.txt") if l.startswith("L ")]
    assert len(loads) == 3, loads
    T0, TB = _tables()
    first = next(p for p in r.storm.passes if p.state != 0)
    rel = _released(r, first.frame)
    assert loads[0] < first.frame < rel.frame < loads[1], (loads, first.frame, rel.frame)
    third = next(p for p in r.storm.passes if p.frame > loads[2] and p.state != 0)
    assert third.loads == 2 and third.primed == 0
    assert all(p.state == 0 for p in r.storm.passes if rel.frame <= p.frame < third.frame)
    assert [t for t in r.storm.traces if rel.frame < t[0] < loads[2]] == []
    assert all(x[4] == SBR_BOOT for x in r.storm.frames) and all(p.sbr == SBR_BOOT for p in r.storm.passes)
    for at, entry, table in ((first.frame + CHAIN_DUMP, 0, T0), (rel.frame + 2, 0, TB), (third.frame + CHAIN_DUMP, 3, T0)):
        n, own, grey = _sky(storm_runs, entry)
        d = r.storm.dumps[at]
        assert _x(d) == table and d["P"][:n] == (grey if table is T0 else own), (at, entry)
    firsts, releases = _first_shows_and_releases(r)
    assert len(firsts) == 2 and releases[0] == rel.frame


# ---- fix round 1 ------------------------------------------------------------------------------------------------------------------
def _snaps(r):
    """{frame: RGB array} of a run's AFTER_SNAPS (MAME writes one more at the exit, after them)."""
    from PIL import Image
    files = sorted((r.wd / "snap").rglob("*.png"))
    assert len(files) in (len(AFTER_SNAPS), len(AFTER_SNAPS) + 1), (r.wd.name, len(files))
    return {f: np.asarray(Image.open(p).convert("RGB")) for f, p in zip(AFTER_SNAPS, files)}


def test_nothing_of_the_storm_shows_after_its_modes(storm_runs):
    """F3 (Review Focus 2). The grade stays in the colour RAM after the last rain mode until the release (the attract's opening
    scenery call); is anything drawn with it? The same race RAIN and DRY, the same inputs (Big Forest ended by time over
    TOVER_AFTER frames after its start, a coin and START in its results: the game over, the results' last mode 0x1d, the attract's
    opening, the next game's course and direction selections), compared at the same frames: before, the rain shows (pictures, the
    colour RAM and the backdrop differ); from the frame after the first one off the rain's modes (0x1d's first frame still shows the
    last rain picture) to the direction screen every snapshot equal pixel for pixel; the release in the attract's opening, before the
    selections, after which the colour RAM, the whole palette RAM and the tile maps equal at every dump (the grey sky was already
    replaced by the attract's own palette); the stale passes the same; every pass's V60 time the DRY one's within 50 us but the
    release pass's, the DRY one's (the attract's opening scene load) plus at most carrier.RELEASE_US_MAX."""
    from vrtools.arcade.weather import RAIN_MODES
    wet, dry = storm_runs.run("after", "rain"), storm_runs.run("after", "dry")
    shown = [x for x in wet.storm.frames if x[2] == 2]
    assert shown, "it did not rain"
    off = next(x[0] for x in wet.storm.frames if x[0] > shown[0][0] and x[1] not in RAIN_MODES)
    rel = _released(wet, off)
    modes = _mode_changes(wet.storm.frames, off - 1)
    assert modes == _mode_changes(dry.storm.frames, off - 1) and modes[0] == (off, 0x1D), modes[:4]
    select = next(f for f, m in modes if m == 0x0A)
    assert rel.frame < select and [m for f, m in modes if f <= rel.frame][-1] == 0x02, (rel.frame, modes[:6])
    sw, sd = _snaps(wet), _snaps(dry)
    before = [f for f in AFTER_SNAPS if f < off and (sw[f] != sd[f]).any()]
    after = [(f, int((sw[f] != sd[f]).any(-1).sum())) for f in AFTER_SNAPS if f > off and (sw[f] != sd[f]).any()]
    assert before and after == [], (off, before[:3], after[:5])
    assert max(AFTER_SNAPS) > select + 1500                         # through the course selection to the direction screen
    for f, dw in wet.storm.dumps.items():
        if f not in dry.storm.dumps:
            continue
        dd = dry.storm.dumps[f]
        if f < off:
            assert dw["X"] != dd["X"], f                                # the grade made
        elif f > rel.frame:
            assert all(dw[k] == dd[k] for k in ("X", "Q", "M")), (f, [k for k in ("X", "Q", "M") if dw[k] != dd[k]])
    assert len([f for f in wet.storm.dumps if f > rel.frame and f in dry.storm.dumps]) >= 5
    sa = [f for f in parse_stale_log(wet.wd / "stale_list.txt") if f >= off]
    assert sa == [f for f in parse_stale_log(dry.wd / "stale_list.txt") if f >= off]
    bw, bd = {f.frame: f.busy_us for f in wet.frames}, {f.frame: f.busy_us for f in dry.frames}
    diff = {f: bw[f] - bd[f] for f in bw if f in bd and f > off and abs(bw[f] - bd[f]) > 50}
    assert set(diff) == {rel.frame} and 0 < diff[rel.frame] <= carrier.RELEASE_US_MAX, diff
    with open(storm_runs.base / "rain_summary.txt", "a") as out:
        out.write(f"after the rain: off its modes at {off} (0x1d), released at {rel.frame} (+{diff[rel.frame]} us on the attract's "
                  f"opening scene load, {bd[rel.frame]} us DRY), {len([f for f in AFTER_SNAPS if f > off])} snapshots to "
                  f"{max(AFTER_SNAPS)} equal to DRY, stale {sa}\n")


def test_a_hook_site_runs_in_rain_only(storm_runs):
    """F1 in MAME: the dummy module's hook site (the race scene's call before the scenery call) on Big Forest. RAIN: its stub calls
    the module's RAM routine on every race pass from the one after the load (its counter, a module cell zeroed at the load, counts
    them: the passes the storm was on, STARTING or SHOW, but the load's); DRY: the stub takes its dry path (the site's own call), no
    write into the storm's RAM (traced), the counter cell never written (0), the carrier IDLE."""
    wet, dry = storm_runs.run("probe", "rain"), storm_runs.run("probe", "dry")
    live = [p for p in wet.storm.passes if p.state != 0]
    assert live and live[0].state == 1 and live[0].loads == 1
    hits = [wet.storm.watch[p.frame] for p in live]
    assert hits[0] == 0 and hits[-1] == len(live) - 1 and all(b - a == 1 for a, b in zip(hits, hits[1:])), hits[:8]
    assert len(live) > 1000 and statistics.median(p.drawn for p in live if p.state == 2) == 60   # 70 s: 1 210 live passes
    S = [p for p in dry.storm.passes if p.frame > BOOT_DONE]
    assert len(S) > 1500 and all(p.state == 0 and p.switch == 0 for p in S)
    assert all(v == 0 for f, v in dry.storm.watch.items() if f > BOOT_DONE)
    assert [t for t in dry.storm.traces if t[0] > BOOT_DONE] == []



# ---- the one rule for tunes (weather Task 6J, the join) ------------------------------------------------------------------------
def _probe_tunes():
    """A Tunes whose every field differs from its class's defaults (so a module given another's tune, or a fresh default, shows)."""
    from vrtools.arcade.weather.tune import HandlingTune, LightningTune, RainTune, ScreenTune, SoundTune, Tunes
    return Tunes(screen=ScreenTune(), lightning=LightningTune(interval_s=(21.0, 39.0)), rain=RainTune(),
                 handling=HandlingTune(slide_threshold=421), sound=SoundTune(thunder_db=-3.0))


def test_tunes_one_field_per_module():
    """tune.Tunes: one field per module that has a tune (and the screen's), each its own dataclass with its defaults; a field given
    another module's tune is refused, naming it; `of(name)` is the field of that module, an unknown name refused."""
    import dataclasses
    from vrtools.arcade.weather import tune as T
    t = T.Tunes()
    names = [f.name for f in dataclasses.fields(T.Tunes)]
    assert {"screen", "lightning", "rain", "handling", "sound"} <= set(names)
    for n in names:
        assert t.of(n) == type(t.of(n))() and t.of(n) is getattr(t, n)
    with pytest.raises(TypeError, match="rain"):
        T.Tunes(rain=T.LightningTune())
    with pytest.raises(KeyError, match="thunder"):
        t.of("thunder")


def test_each_module_receives_its_own_tune(monkeypatch):
    """Each factory of the registry hands its module `tunes.<the module's name>` and no other module's (no `isinstance` choice: the
    one rule for tunes), and install_weather hands the screen its own, the carrier the whole Tunes, the sound board its own."""
    import vrtools.arcade.weather as W
    from vrtools.arcade.weather import carrier as C, handling, lightning, rain, screen, sound
    probe, got = _probe_tunes(), {}
    for mod, name in ((rain, "rain"), (lightning, "lightning"), (handling, "handling")):
        monkeypatch.setattr(mod, "module", lambda rs, tune, *a, _n=name, **k: got.setdefault(_n, tune) and C.Module(_n, None))
    monkeypatch.setattr(sound, "module", lambda rs, converted, tune, *a, **k: got.setdefault("sound", tune) and C.Module("sound", None))
    extra = {}
    try:
        from vrtools.arcade.weather import cover
        monkeypatch.setattr(cover, "module", lambda rs, tune, rain_tune, *a, **k: (got.setdefault("cover", tune),
                                                                                    extra.setdefault("rain", rain_tune),
                                                                                    C.Module("cover", None))[2])
    except ImportError:                                 # before the cover's merge
        pass
    mods = C.default_modules(object(), probe)
    assert [m.name for m in mods] == ["cover", "lightning", "rain", "handling", "sound"]       # the join's frame order
    assert {"lightning", "rain", "handling", "sound"} <= set(got)  # (the cover's stand-in, before the cover's merge, takes no tune)
    for n, t in got.items():
        assert t is probe.of(n), (n, t)
    if "cover" in got:
        assert extra["rain"] is probe.rain               # the rain's facts the cover is made for (its cluster count; v0.4.1: the
                                                         # drops' width and head share, its single drops' objects)
    seen = {}
    monkeypatch.setattr(screen, "install", lambda rs, tune: seen.setdefault("screen", tune))
    monkeypatch.setattr(C, "install", lambda rs, converted=None, tunes=None, modules=None: seen.setdefault("carrier", tunes) and rs)
    monkeypatch.setattr(sound, "install_board", lambda rs, tune=None: seen.setdefault("board", tune) and rs)
    from vrtools.arcade.romset import RomSet
    W.install_weather(RomSet(b"", b"", b"", b"", b"", b""), None, tunes=probe)
    assert seen == {"screen": probe.screen, "carrier": probe, "board": probe.sound}


def test_the_reload_branch_on_a_forced_state(storm_runs):
    """The carrier's reload branch (another entry's load key while loaded: not reached in the game's flow, kept as defensive code by
    the session lead's ruling on stage 2's F6; this is the forced-state test promised for the join). In a Big Forest RAIN race's
    countdown the load key is poked to another entry's, with junk over the first colours of the grey sky in the storm's DATA (what
    the old course's data would be). At the next scenery call the storm is released and loaded again: the loads go 1 -> 2 on the
    pass after the poke, the start passes run again, then the frames; the copy is redone (the DATA word back to this course's, the
    junk gone, read every pass); the sky and the grade drawn after it are this course's own, as before the poke (palette and colour
    RAM equal at RELOAD_DUMPS); no stale list, no pass over the cap. The control (the junk alone, no key) keeps the junk in DATA
    (nothing copies it again): the DATA word is what the test reads."""
    from tests.test_frame_rate import _stale
    r, ctl = storm_runs.run("reload", "key"), storm_runs.run("reload", "control")
    poked = [l.split() for l in (r.wd / "poke.txt").read_text().splitlines()]
    assert len(poked) == 2 and {int(p[1]) for p in poked} == {RELOAD_POKE}, poked
    before = [p for p in r.storm.passes if p.frame <= RELOAD_POKE]
    after = [p for p in r.storm.passes if p.frame > RELOAD_POKE]
    assert before[-1].loads == 1 and before[-1].state == carrier.SHOW and after, (before[-1:], after[:1])
    reload = after[0]
    assert reload.loads == 2 and reload.state == carrier.STARTING, reload
    assert all(p.loads == 2 for p in after), sorted({p.loads for p in after})
    starts = [p for p in after if p.state == carrier.STARTING]
    show = next(p for p in after if p.state == carrier.SHOW)
    assert starts and show.frame > starts[-1].frame and len(starts) <= 8, (len(starts), show.frame)
    w = r.storm.watch
    junk_frames = [f for f, v in w.items() if v == RELOAD_JUNK]
    own = w[before[-1].frame]
    assert own != RELOAD_JUNK and junk_frames == [] and all(w[p.frame] == own for p in after), \
        (hex(own), junk_frames[:3], sorted({hex(w[p.frame]) for p in after}))
    a, b = RELOAD_DUMPS
    assert r.storm.dumps[a]["P"] == r.storm.dumps[b]["P"], "the sky after the reload is not this course's"
    assert r.storm.dumps[a]["X"] == r.storm.dumps[b]["X"], "the grade after the reload is not as before"
    assert _stale(r) == [] and max(f.busy_us for f in r.frames if f.frame > RELOAD_POKE) / 1000 <= RAIN_BUSY_MAX_MS
    wc = ctl.storm.watch
    assert {p.loads for p in ctl.storm.passes if p.frame > RELOAD_POKE} == {1}
    assert all(wc[p.frame] == RELOAD_JUNK for p in ctl.storm.passes if p.frame > RELOAD_POKE)
    with open(storm_runs.base / "rain_summary.txt", "a") as out:
        out.write(f"reload (forced): poked at {RELOAD_POKE}, reloaded on pass {reload.frame}, {len(starts)} start passes, frames from "
                  f"{show.frame}; DATA word {own:#x} back (junk {RELOAD_JUNK:#x} kept in the control)\n")



# --- build-time checks (the final review's W6) ----------------------------------------------------------------------------------
def test_the_readers_come_after_their_writers():
    """carrier.READ_AFTER_WRITE: the rain after the cover (it reads MODE / WALK / NOSPLASH, v0.4.1 `under_cover`), the lightning after
    the cover (`under_cover`), the sound after the lightning (strike_seq / strike_band of the same pass), v0.4.1 the rain after the
    lightning (its LEVEL: the lit rain); a list against it is refused by lay_out (so by build) naming both; the join's order passes;
    a list without one of the pair is not concerned."""
    from types import SimpleNamespace as M
    join = [M(name=n) for n in ("cover", "lightning", "rain", "handling", "sound")]
    carrier.check_order(join)
    assert carrier.READ_AFTER_WRITE == (("cover", "rain"), ("cover", "lightning"), ("lightning", "sound"), ("lightning", "rain"))
    for order, pair in ((("rain", "cover"), "cover must come before rain"), (("lightning", "cover"), "cover must come before lightning"),
                        (("cover", "sound", "lightning"), "lightning must come before sound"),
                        (("cover", "rain", "lightning"), "lightning must come before rain")):
        with pytest.raises(PatchError, match=pair):
            carrier.lay_out([M(name=n) for n in order])
    carrier.check_order([M(name="sound"), M(name="rain")])


def test_a_rain_tune_below_the_covers_roof_clusters_is_refused():
    """Tunes: the cover walks `roof_clusters` of the rain's clusters under the pits roof; a rain tune with fewer clusters is refused
    (its cluster index would run past the rain's cells); as many is allowed."""
    from vrtools.arcade.weather.tune import CoverTune, RainTune, Tunes
    with pytest.raises(ValueError, match="roof_clusters 24 is more than rain.clusters 20"):
        Tunes(rain=RainTune(clusters=20, drops=100))
    assert Tunes(rain=RainTune(clusters=24, drops=120)).rain.clusters == CoverTune().roof_clusters == 24


def test_the_stub_compares_the_directorys_count():
    """The stub's "a directory entry" test compares the menu entry with the directory's count (build passes len(dirs)), not a
    written-in 10: the same bytes for ten entries."""
    from vrtools.arcade.disasm import listing_bytes
    from vrtools.arcade.weather import RAIN_MODES, WEATHER_BYTE
    lay = {"body": 0x522000, "release": 0x522100, "cells_hw": 16, "copydir": 0xFFF300, "banktab": 0xFFF330, "common": 0xFFF340}
    texts = {}
    for n in (7, 10):
        b = carrier.stub_code(0xFFF120, {**lay, "entries": n}, RAIN_MODES, WEATHER_BYTE)
        texts[n] = [" ".join(l.text.split()) for l in listing_bytes(b.bytes(), 0xFFF120)]
    assert "cmp.w #7, R0" in texts[7] and "cmp.w #A, R0" in texts[10] and "cmp.w #A, R0" not in texts[7]
    assert carrier.stub_code(0xFFF120, lay, RAIN_MODES, WEATHER_BYTE).bytes() == \
        carrier.stub_code(0xFFF120, {**lay, "entries": 10}, RAIN_MODES, WEATHER_BYTE).bytes()


POLY_FREE_FLOOR = 8_000                 # W7: the polygon ROM's erased run left after the weather: 8 892 bytes measured (8 860 between
                                        # the cover's objects and the lightning's, 32 at the run's end), the floor about 10 % under it


def test_the_polygon_roms_room_after_the_weather(romset_zip, saturn_cue):
    """The final review's W7: the polygon ROM's erased run (from the rain's objects, 0xfda424, to the ROM's end) holds the storm's
    three object blocks; what is left erased outside them stays at POLY_FREE_FLOOR or more (a later stage that grows an object block
    finds out here, not by an overlap at build time). The review's 90 232 bytes could not be reproduced: before the weather the run
    is 154 588 bytes, the three blocks take 145 696."""
    from vrtools.arcade.weather import layout
    s1 = _stage1(romset_zip, saturn_cue)
    out, _ = carrier.build(s1, carrier.default_modules(s1))
    run0 = layout.block("rain objects").start
    poly = np.frombuffer(out.polygons, np.uint8)
    inside = np.zeros(len(poly) - run0, bool)
    for b in layout.blocks():
        if b.space == "polygon":
            inside[b.start - run0:b.start - run0 + b.size] = True
    free = int(((poly[run0:] == 0xFF) & ~inside).sum())
    assert len(poly) - run0 == 154_588 and int(inside.sum()) == 145_696
    assert free >= POLY_FREE_FLOOR, free
