"""Weather stage 6, the storm's sound (spec 5.6 and 6; weather/sound.py, weather/thunder_gen.py): the generated samples, the sound
board's patches (the joined prototype's, out/p75storm, but for fix round 2's timing patch: P75_PROGRAM_DIFF), the V60's triggers on the
carrier, and in MAME the sound-latch contract, the other voices untouched outside the ducking windows, silence where the design says
silence, the test switch, a reset, a race ending during a thunder, no sample at full scale beyond the game's own start horn.

The thunder needs lightning's strikes: the normal set registers the real lightning (the join), whose strikes come at random every
20-40 s; the test sets put a stand-in module named `lightning` in its place that strikes on chosen race passes
(`tests/weather_standins.py`'s `strike_standin`, moved out of `vrtools` at the join)."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vrtools.arcade.patch import PatchError
from vrtools.mame.runner import LUA_DIR

ROOT = Path(__file__).resolve().parents[1]

# The prototype's samples (spike/p66_thunder.py, round 4's settings, as written into out/p75storm), SHA-256 of the 12-bit bytes.
SAMPLE_SHA256 = {"crack": "97106fbca62a261a8aa103ca20bbf4fe8e3135e8084a8b90c424fdd0cbcfa187",
                 "rumble": "2c85a556366cbda10750498293f0dd584bbd41177d28762335ffce2a37f42c69",
                 "rain": "5a8ed2dd908261321f5b01d8a27c55bc7ef39149e522acc6c5e6be40e94e6b04"}


# ---- static: the tune, the generator ----------------------------------------------------------------------------------------------
def test_sound_tune_defaults_and_bounds():
    """SoundTune: the rain at -7.1 dB under the voice's full level (Pascal: "now the rain is a bit too loud, id say in between before
    and now"), the thunder and the ducking at out/p75storm's values (the thunder one 1.5-dB step under round 4, the ducking 4.125 /
    3.0 / 2.25 dB: Pascal's "everything is good but level of the thunder is too high", not yet judged), the delays 0.3 / 0.6 / 0.9 s
    and the bands 467 / 633; the bytes the program gets from them; values the program cannot play exactly are refused."""
    from vrtools.arcade.weather.tune import SoundTune
    t = SoundTune()
    assert (t.rain_db, t.thunder_db, t.duck_db, t.delays_s, t.bands) == (-7.1, -1.5, (4.125, 3.0, 2.25), (0.3, 0.6, 0.9), (467, 633))
    assert (t.rain_level, t.thunder_steps, t.duck_steps, t.delay_ticks) == (0x26, 8, (11, 8, 6), (0x11, 0x22, 0x32))
    assert SoundTune(rain_db=-22.1).rain_level == 0x76                  # the quietest the program's fade-in lands on
    for bad in ({"rain_db": 0.0}, {"rain_db": -45.0}, {"rain_db": -23.0}, {"rain_db": -30.0}, {"thunder_db": 0.5}, {"thunder_db": -1.0}, {"thunder_db": -7.5},
                {"duck_db": (4.0, 3.0, 2.25)}, {"duck_db": (4.125, 3.0)}, {"duck_db": (-0.375, 0.0, 0.0)},
                {"delays_s": (0.0, 0.6, 0.9)}, {"delays_s": (0.3, 0.6, 5.0)}, {"delays_s": (0.3, 0.6)},
                {"bands": (633, 467)}, {"bands": (0, 633)}):
        with pytest.raises(ValueError):
            SoundTune(**bad)


def test_the_generator_matches_the_prototype():
    """thunder_gen's three samples are the prototype's bytes (SHA-256 pinned), at the rates and notes the program plays them, within
    a MultiPCM sample's 65 535 points; a one-shot ends on a 0 point (the chip loops there: silence), the crack starts at full scale."""
    from vrtools.arcade.weather import thunder_gen as g
    s = g.samples()
    assert {k: hashlib.sha256(v.data).hexdigest() for k, v in s.items()} == SAMPLE_SHA256
    assert [(k, v.points, len(v.data), v.rate, v.note, v.loop) for k, v in s.items()] == [
        ("crack", 7000, 10500, 20000.0, 0x30, False), ("rumble", 40912, 61368, 6294.3, 0x1C, False),
        ("rain", 31629, 47445, 15814.6, 0x2C, True)]
    pts = {k: g.s12_points(v.data) for k, v in s.items()}
    assert pts["crack"][0] == 2047 and pts["crack"][6999] == 0 and pts["rumble"][40911] == 0
    assert all(max(abs(p) for p in v) == 2047 for v in pts.values())


def test_the_generator_is_deterministic_in_two_processes():
    """The same bytes from two fresh interpreters (no state, no clock, no platform dependence the hashes would show)."""
    code = ("import hashlib; from vrtools.arcade.weather import thunder_gen as g; "
            "print(' '.join(k + ':' + hashlib.sha256(v.data).hexdigest() for k, v in g.samples().items()))")
    runs = [subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True,
                           env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONHASHSEED": str(seed)}).stdout for seed in (1, 2)]
    assert runs[0] == runs[1] and runs[0].split() == [f"{k}:{v}" for k, v in SAMPLE_SHA256.items()]


def test_the_generator_reads_no_file(monkeypatch):
    """The generator opens nothing (no input file, no recording): every way of opening a file fails while it runs, and it still
    makes its three samples."""
    import builtins
    import io
    import pathlib
    from vrtools.arcade.weather import thunder_gen as g

    def refuse(*a, **k):
        raise AssertionError(f"the generator opened a file: {a[:1]}")
    for mod, name in ((builtins, "open"), (io, "open"), (os, "open"), (pathlib.Path, "open"), (pathlib.Path, "read_bytes")):
        monkeypatch.setattr(mod, name, refuse)
    g.samples.cache_clear()
    try:
        assert {k: hashlib.sha256(v.data).hexdigest() for k, v in g.samples().items()} == SAMPLE_SHA256
    finally:
        monkeypatch.undo()
        g.samples.cache_clear()


# ---- static: the sound board ------------------------------------------------------------------------------------------------------
# out/p75storm's members (the joined prototype with spike 75's thunder level), CRC32 of the files as the zip holds them.
P75_CRC = {"sound_program": 0x610DFDBC, "sound_pcm1": 0x048048BE, "sound_pcm2": 0x239C2BEE}
# This build's (fix round 2, the session lead's ruling replacing ruling A): the two sample ROMs out/p75storm's; the program
# out/p75storm's but for P75_PROGRAM_DIFF.
BUILD_CRC = {"sound_program": 0x8C3E6961, "sound_pcm1": 0x048048BE, "sound_pcm2": 0x239C2BEE}
# (start, end, out/p75storm's bytes, this build's bytes, why): every byte range in which this build's sound program differs from
# out/p75storm's.
P75_PROGRAM_DIFF = (
    (0x544, 0x54E, "4ef90000ac004e714e71", "61000c384ef90000ac00",
     "the reset 8100's `bsr 117e` (the YM3438 timer A's reload) stays in place, so a reset restarts the ticks at v0.3's moment; the "
     "jump to the reset routine moves to 0x548"),
    (0x982, 0x98C, "41f900f00000383c1ff6", "4ef90000afb44e714e71", "the boot's RAM clear jumps to the clear routine (patch 4)"),
    (0xAC00, 0xAC3C,
     "4eb90000117e4eb9000019d41e3c00154eb9000016e61e3c00344eb9000016e61e3c00394eb9000016e642b900f0140042b900f014044ef900001aec",
     "4eb9000019d41e3c00154eb9000016e61e3c00344eb9000016e61e3c00394eb9000016e642b900f0140042b900f014044ef900001aec4e714e714e71",
     "the reset routine without its first call (made in place now), three dead nops keeping its length"),
    (0xAFB4, 0xAFD4, "ff" * 32, "41f900f000007000383c0ffa20c051ccfffc30c0383c1fe851ccfffe4ef80994",
     "the clear routine (patch 4): the same RAM by longs, then the wait that gives back the level hook's 8 288 cycles before the "
     "timer starts"),
)
# the approved joined set: VR_P75_SET through tests/reference_sets.py (W2; no default: it is local only)


def _files_crc(members: dict) -> dict:
    import zlib
    from vrtools.arcade.romset import _swap16
    return {k: zlib.crc32(_swap16(v) if k == "sound_program" else v) for k, v in members.items()}


def m68k_listing(blob: bytes, base: int) -> list[tuple[int, str]]:
    """(address, text) of every 68000 instruction of `blob` placed at `base` (MAME's unidasm)."""
    import re
    import tempfile
    from vrtools.arcade.disasm import UNIDASM
    if not Path(UNIDASM).exists():
        pytest.fail(f"unidasm not found at {UNIDASM}; run tools/build-mame.sh")
    with tempfile.NamedTemporaryFile(suffix=".m68k", delete=False) as t:
        t.write(blob)
    try:
        out = subprocess.run([str(UNIDASM), t.name, "-arch", "m68000", "-basepc", hex(base)], capture_output=True, text=True,
                             check=True).stdout
    finally:
        Path(t.name).unlink()
    rows = []
    for raw in out.splitlines():
        m = re.match(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4} )+\s*(.*)$", raw)
        if m and int(m.group(1), 16) < base + len(blob):
            rows.append((int(m.group(1), 16), " ".join(m.group(2).split())))
    return rows


_ORIGINAL: dict = {}


@pytest.fixture
def original(romset_zip):
    from vrtools.arcade.romset import RomSet
    if str(romset_zip) not in _ORIGINAL:
        _ORIGINAL[str(romset_zip)] = RomSet.from_zip(romset_zip)
    return _ORIGINAL[str(romset_zip)]


def test_the_board_is_the_prototypes(original):
    """The port is byte-faithful to the approved prototype (the session lead's ruling C2) but for the timing patch of fix round 2:
    with SoundTune() the two sample ROMs are out/p75storm's (CRC32 pinned) and the program this build's (pinned; out/p75storm's but
    for P75_PROGRAM_DIFF, whose new bytes are checked here without the set), 980 bytes from 0xac00 (out/p75storm's 948 and the clear routine's 32), chip 1 61 376 bytes, chip 2 57 968;
    every piece of out/p75storm's at its address there (the clear routine last)."""
    from vrtools.arcade.weather import sound
    from vrtools.arcade.weather.tune import SoundTune
    members, rep = sound.board(original, SoundTune())
    crc = _files_crc(members)
    assert crc == BUILD_CRC and crc["sound_pcm1"] == P75_CRC["sound_pcm1"] and crc["sound_pcm2"] == P75_CRC["sound_pcm2"]
    assert rep["program"]["used"] == 980 and rep["program"]["clear"] == 0xAC00 + 948
    assert [members["sound_program"][s:e].hex() for s, e, _, _, _ in P75_PROGRAM_DIFF] == [n for _, _, _, n, _ in P75_PROGRAM_DIFF]
    assert rep["pcm1"]["used"] == 61376 and rep["pcm2"]["used"] == 57968
    assert {k: v for k, v in rep["program"].items() if k not in ("clear", "used")} == {
        "reset": 0xAC00, "tunnel": 0xAC3C, "level": 0xACB0, "duck": 0xACF8, "handler close": 0xADB2, "handler medium": 0xADC8,
        "handler distant": 0xADDE, "rain loop": 0xADF4, "number close": 0xAF02, "number medium": 0xAF34, "number distant": 0xAF66,
        "number rain_on": 0xAF84, "number rain_off": 0xAF9E}


def test_the_clear_routine_gives_back_the_hooks_cycles():
    """Patch 4's arithmetic (68000 cycles, MAME's 10 MHz): the original RAM clear 180 050 cycles; the routine's fixed part (the jump,
    the long loop, the jump back) 90 060; its wait `move.w #8168, d4; dbra` 81 702: together 8 288 fewer than the original, the level
    hook's cost on the 168 writes before the timer starts (38 / 42 a non-level write on chip 1 / 2, 66 / 70 a level write; 56 level
    writes, half on each chip). The routine disassembles to the clear, the wait and `jmp $994.w`."""
    from vrtools.arcade.weather import sound
    assert sound.CLEAR_ORIGINAL_CYCLES == 180050 and sound.CLEAR_FIXED_CYCLES == 90060 and sound.clear_pad() == (8168, 0)
    assert (38 + 42) * 56 + (66 + 70) * 28 == sound.INIT_SURPLUS_CYCLES
    n, k = sound.clear_pad()
    assert sound.CLEAR_ORIGINAL_CYCLES - (sound.CLEAR_FIXED_CYCLES + 22 + 10 * n + 4 * k) == sound.INIT_SURPLUS_CYCLES
    assert [t for _, t in m68k_listing(sound._code(0xAFB4, sound.clear_routine), 0xAFB4)] == [
        "lea $f00000.l, A0", "moveq #$0, D0", "move.w #$ffa, D4", "move.l D0, (A0)+", "dbra D4, $afc0", "move.w D0, (A0)+",
        "move.w #$1fe8, D4", "dbra D4, $afcc", "jmp $994.w"]


def test_the_board_equals_the_approved_set(original):
    """Where the approved joined set is present (the reference set VR_P75_SET: local only), the sound members of this
    build with SoundTune() equal its members: the two sample ROMs byte for byte, the program byte for byte outside P75_PROGRAM_DIFF
    (fix round 2's timing patch, each range listed with its old bytes and its reason) and differing in each of those ranges."""
    import zipfile
    from vrtools.arcade.romset import SOUND_PCM1, SOUND_PCM2, SOUND_PROGRAM, _swap16
    from vrtools.arcade.weather import sound
    from vrtools.arcade.weather.tune import SoundTune
    from tests.reference_sets import reference_set
    zp = reference_set("VR_P75_SET") / "vr.zip"
    members, _ = sound.board(original, SoundTune())
    with zipfile.ZipFile(zp) as z:
        ref = {"sound_program": _swap16(z.read(SOUND_PROGRAM)), "sound_pcm1": z.read(SOUND_PCM1), "sound_pcm2": z.read(SOUND_PCM2)}
    assert [k for k in ref if k != "sound_program" and members[k] != ref[k]] == []
    a, b = ref["sound_program"], members["sound_program"]
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    assert diff and all(any(s <= i < e for s, e, _, _, _ in P75_PROGRAM_DIFF) for i in diff), [hex(i) for i in diff][:8]
    for s, e, old, new, why in P75_PROGRAM_DIFF:
        assert a[s:e].hex() == old and b[s:e].hex() == new, (hex(s), a[s:e].hex(), b[s:e].hex(), why)
    assert b[0xAC00:0xAC3C] == sound._code(0xAC00, sound.reset_routine) and b[0xAFB4:0xAFD4] == sound._code(0xAFB4, sound.clear_routine)


def test_the_board_changes_only_its_blocks(original):
    """Every byte the board changes in the three members lies in a sound block of the layout table and every such block is written;
    the blocks' room against what is used (the findings' room table)."""
    from vrtools.arcade.weather import layout, sound
    from vrtools.arcade.weather.tune import SoundTune
    new, _ = sound.board(original, SoundTune())
    blocks = [b for b in layout.blocks() if b.owner == "sound"]
    for field, rom in (("sound_program", "sound"), ("sound_pcm1", "pcm1"), ("sound_pcm2", "pcm2")):
        a, b = getattr(original, field), new[field]
        diff = [k for k in range(len(a)) if a[k] != b[k]]
        mine = [bl for bl in blocks if layout.ROM_OF[bl.space] == rom]
        assert diff and not [hex(k) for k in diff if not any(bl.start <= k < bl.start + bl.size for bl in mine)][:4], field
        assert not [bl.name for bl in mine if not any(bl.start <= k < bl.start + bl.size for k in diff)], field


def test_the_board_checks_everything_before_writing(original, monkeypatch):
    """A set without the sound members, a block not erased, a site holding other than its original instructions (and the tunnel
    handler's fall-through, 0x558..0x56b, which the tunnel routine re-implements), a sound number in use, a sample-table entry in
    use, or samples larger than their blocks: PatchError naming it, and the set given (the session's original) untouched."""
    import dataclasses
    from dataclasses import replace
    from vrtools.arcade.weather import layout, sound, thunder_gen
    from vrtools.arcade.weather.tune import SoundTune
    fields = ("sound_program", "sound_pcm1", "sound_pcm2")
    before = {f: hashlib.sha256(getattr(original, f)).hexdigest() for f in fields}
    with pytest.raises(PatchError, match="no sound members"):
        sound.board(replace(original, sound_pcm1=None), SoundTune())
    blocks = {b.name: b for b in layout.blocks() if b.owner == "sound"}
    for name, at in (("sound code", 0xAC10), ("sound main loop", 0x26E), ("sound reset", 0x54A), ("sound init clear", 0x983),
                     ("sound tunnel word", 0x552),
                     ("sound level write", 0x17F3), ("sound numbers", 0x926 + 8 * 2), ("chip 1 samples", 0x9000),
                     ("chip 1 sample table", 12 * 114 + 1), ("chip 2 crack entry", 12 * 110), ("chip 2 samples", 0x700)):
        field = layout.SOUND_ROMS[layout.ROM_OF[blocks[name].space]]
        data = bytearray(getattr(original, field))
        data[at] ^= 0x5A
        with pytest.raises(PatchError, match="sound|sample"):
            sound.board(replace(original, **{field: bytes(data)}), SoundTune())
    for at, what in ((0x559, "tunnel handler"), (0x563, "tunnel handler"), (0x56A, "tunnel handler"), (0x98D, "RAM clear loop"),
                     (0x993, "RAM clear loop"), (0x545, "reset's first call")):              # the fall-through and the clear's loop, which the routines re-implement
        data = bytearray(original.sound_program)
        data[at] ^= 0x5A
        with pytest.raises(PatchError, match=what):
            sound.board(replace(original, sound_program=bytes(data)), SoundTune())
    real = thunder_gen.samples()
    for name, extra in (("rumble", blocks["chip 1 samples"].size), ("rain", blocks["chip 2 samples"].size)):
        big = {**real, name: dataclasses.replace(real[name], data=real[name].data + bytes(extra))}
        with monkeypatch.context() as mp:
            mp.setattr(thunder_gen, "samples", lambda: big)
            with pytest.raises(PatchError, match="holds .* bytes, the samples need"):
                sound.board(original, SoundTune())
    assert sound.board(original, SoundTune())[1]["program"]["used"] == 980
    assert {f: hashlib.sha256(getattr(original, f)).hexdigest() for f in fields} == before


def test_the_board_code_disassembles(original):
    """The 68000 pieces disassemble (unidasm m68000) to the routines the contract names: the sites jump to them, the reset keys off
    the three voices and clears the duck before the game's tail, the thunder handlers arm the duck and enter the multi-voice handler,
    RAIN ON and RAIN OFF use the multi-voice handler itself."""
    from vrtools.arcade.weather import layout, sound
    from vrtools.arcade.weather.tune import SoundTune
    new, rep = sound.board(original, SoundTune())
    prog, at = new["sound_program"], rep["program"]

    def lst(a, n):
        return [t for _, t in m68k_listing(prog[a:a + n], a)]
    assert lst(0x26E, 8) == [f"jsr ${at['duck']:x}.l", "nop"]
    assert lst(0x544, 12) == ["bsr $117e", f"jmp ${at['reset']:x}.l", "nop"]
    assert lst(0x982, 10) == [f"jmp ${at['clear']:x}.l", "nop", "nop"]
    assert lst(0x550, 6) == [f"jmp ${at['tunnel']:x}.l"] and lst(0x17F2, 6) == [f"jmp ${at['level']:x}.l"]
    assert lst(at["reset"], at["tunnel"] - at["reset"]) == [
        "jsr $19d4.l", "move.b #$15, D7", "jsr $16e6.l", "move.b #$34, D7", "jsr $16e6.l", "move.b #$39, D7", "jsr $16e6.l",
        "clr.l $f01400.l", "clr.l $f01404.l", "jmp $1aec.l", "nop", "nop", "nop"]
    assert lst(at["handler close"], 22) == ["move.w #$d, $f01400.l", "move.b #$b, $f01406.l", "jmp $a5e.l"]
    assert lst(at["handler distant"], 22) == ["move.w #$2e, $f01400.l", "move.b #$6, $f01406.l", "jmp $a5e.l"]
    for name in ("reset", "tunnel", "level", "duck"):
        nxt = min(v for k, v in at.items() if k != "used" and v > at[name])
        assert not [t for t in lst(at[name], nxt - at[name]) if "dc.w" in t or "ILLEGAL" in t or "INVALID" in t], name
    table = layout.block("sound numbers").start
    assert [struct_be(prog, table + 8 * k + 4) for k in range(5)] == [at["handler close"], at["handler medium"],
                                                                      at["handler distant"], sound.MULTI, sound.MULTI]


def struct_be(b: bytes, at: int) -> int:
    return int.from_bytes(b[at:at + 4], "big")


# ---- static: the V60's triggers ----------------------------------------------------------------------------------------------------
def test_the_registry_and_the_trigger_code():
    """The normal set's modules (the join): cover, lightning, rain, handling and the sound's triggers last; the triggers read the real
    lightning's two cells by name (lightning.cells() owns `strike_seq` and `strike_band`; without a module `lightning` the layout
    refuses, naming the cell) and the lightning cuts the bands where the sound's tune does (467 / 633); the code disassembles
    throughout and sends the five words through the game's queue 0xffa246."""
    from vrtools.arcade.disasm import listing_bytes
    from vrtools.arcade.weather import carrier, lightning, sound
    from vrtools.arcade.weather.tune import SoundTune
    from tests.weather_standins import STANDIN_CELLS
    names = [f.__name__ for f in carrier.REGISTRY]
    assert names[1:] == ["_lightning_factory", "_rain_factory", "_handling_factory", "_sound_factory"]
    assert names[0] == "_cover_factory"
    assert {"strike_seq", "strike_band"} <= dict(lightning.cells()).keys() and dict(STANDIN_CELLS).keys() <= dict(lightning.cells()).keys()
    assert tuple(lightning.BANDS) == tuple(float(b) for b in SoundTune().bands)
    cells_only = carrier.Module(name="lightning", code=lambda lay: carrier.Block(lay.code("lightning")), cells=lightning.cells())
    mods = [cells_only, carrier.module_named("sound", None)]
    assert [m.name for m in mods] == ["lightning", "sound"] and mods[1].frame == "frame" and mods[1].release is None
    lay, pieces, _ = carrier.lay_out(mods)
    at, code = pieces["sound"]
    lines = listing_bytes(code, at)
    assert sum(len(l.bytes) for l in lines) == len(code)
    assert not [l for l in lines if l.text.startswith("$") or "illegal" in l.text.lower()][:3]
    text = " ".join(l.text for l in lines)
    assert text.count("FFA246") == 2 and all(f"#{w:X}" in text for w in sound.WORDS.values()), text
    assert f"{lay.cell('lightning', 'strike_seq'):X}" in text and f"{lay.cell('lightning', 'strike_band'):X}" in text
    with pytest.raises(PatchError, match="strike_seq"):
        carrier.lay_out([mods[1]])
    assert len(code) < 256 and lay.carrier["cells_end"] - lay.cell("sound", "rain") == 20


def test_the_trigger_is_exempt_from_the_guard():
    """The join's round 2, J1 (the session lead's ruling): the trigger tests the guard only to count a late pass in its `late` cell
    and then does its work all the same: one return, at the work's end; the late path increments `late` and branches back into the
    work (with the planted late of the tests too); no path from the guard's test returns before the queue calls."""
    from vrtools.arcade.v60asm import asm
    from vrtools.arcade.weather import carrier, lightning, sound
    cells = lightning.cells() + (("late", 4),)                    # the stand-in's `late` too (planted_late reads it)
    cells_only = carrier.Module(name="lightning", code=lambda lay: carrier.Block(lay.code("lightning")), cells=cells)
    for planted in (False, True):
        lay, _, _ = carrier.lay_out([cells_only, sound.module(planted_late=planted)])
        items = sound.trigger_code(lay, planted_late=planted).items
        rsr = [k for k, i in enumerate(items) if i == asm("rsr")]
        k_late = items.index(("label", "late"))
        after = [i for i in items[k_late + 1:] if not (isinstance(i, tuple) and i[0] == "label")]
        assert len(rsr) == 1 and rsr[0] < k_late, (planted, rsr, k_late)
        assert after == [asm("add.w imm,abs", 1, lay.cell("sound", "late")), ("br", "work")], (planted, after)
        assert ("label", "work") in items and items.index(("label", "work")) < items.index(("label", "late"))


# ---- static: the logger's parser ---------------------------------------------------------------------------------------------------
def test_the_pcm_log_parser(tmp_path):
    """parse_pcm_log on a synthetic log: the chip writes, the words (a high byte from 0xffa2a6 and the next from 0xffa36a; another
    PC's byte skipped; a high byte cut by a reset dropped), the modes, the frames, the boots; a voice's key intervals and levels."""
    from vrtools.mame.runner import parse_pcm_log
    log = tmp_path / "pcm.txt"
    log.write_text("B 0.000000\nS 5 0.10 aa fe0000\nS 9 0.20 b0 ffa2a6\nS 10 0.22 77 ffa36a\nM 10 0.22 12\nF 10 0.22\n"
                   "P 11 0.25 2 19 1 73\nP 11 0.25 2 19 5 7e\nP 11 0.26 2 19 4 80\nP 20 0.40 2 19 5 26\nS 21 0.41 b0 ffa2a6\n"
                   "B 0.50\nP 2 0.60 2 19 4 0\nS 3 0.61 81 ffa2a6\nS 4 0.62 0 ffa36a\nP 5 0.70 2 19 4 80\nF 5 0.70\nEND\n")
    r = parse_pcm_log(log)
    assert r.complete and r.boots == [0.0, 0.5] and r.frames == [(10, 0.22), (5, 0.70)] and r.modes == [(10, 0.22, 0x12)]
    assert r.words == [(10, 0.22, 0xB077), (4, 0.62, 0x8100)]
    assert r.keyed(2, 0x19) == [(0.26, 0.60), (0.70, 0.70)] and r.keyed(1, 0x15) == []
    assert r.level_at(2, 0x19, 0.3) == 0x7E and r.level_at(2, 0x19, 0.5) == 0x26 and r.mode_at(0.3) == 0x12


# ---- the MAME runs ---------------------------------------------------------------------------------------------------------------
# Big Forest RAIN on the autopilot, one lap a race (race_end.lua: the clock held, the lap count 1), then the results, the attract and
# two more games: RAIN Metropolis (its long tunnel: the tunnel words fade the rain), DRY Metropolis. The test sets' stand-in strikes
# on these race passes of each race (SHOW passes in mode 0x14): close, medium, distant, and a close one FINISH_LEAD passes before
# Big Forest's finish (its 1-lap race ends on SHOW pass FINISH_PASS of the race on this autopilot line, measured: a race ending during
# a thunder, Review Focus 2).
BF, METRO = 0, 6
FINISH_PASS = 2512                      # measured (calibration on the strike set, FINISH_PASS 0: green 1928, finish 6952)
LATE_PASS = 1100                        # F2: a medium strike whose first pass the trigger finds late (the planted late guard)
FINISH_LEAD = 25                        # 25 passes (~0.87 s) before the finish: the close thunder's crack and rumble sound at the line
SCHEDULE = ((60, 1), (420, 2), (780, 3), (LATE_PASS, 2), (FINISH_PASS - FINISH_LEAD, 1))
AFTER_PASS = 30                         # the stand-in also strikes (close) on the 30th SHOW pass after the race mode (the goal)
CHAIN_SECONDS = 420
SOUND_JOBS = 2
SVC_PRESS, SVC_EXIT, RESET_AT = 2100, 2400, 2100       # the TEST switch / its menu's EXIT / a soft reset, during the first race
TOVER_AFTER = 480                       # time over this many frames after the race load (autoplay.lua's race start, ~1602): 2082, after
                                        # the close thunder of race pass 60 has sounded (its word at frame 2049, its voices from 2068)
OURS = ((2, 0x14), (2, 0x19), (1, 0x15))               # (chip, voice): the crack, the rain, the rumble
# The attract (no coin) with the words injected at frame ends (spike 75's frames for the thunder; the rain between the attract's own
# resets, 50.97 s and the run's end): close, medium, distant, rain on, rain off.
ALONE_WORDS = ((1200, 0xB074), (1600, 0xB075), (2300, 0xB076), (3000, 0xB077), (3350, 0xB078))
STORM_WORDS = set(range(0xB074, 0xB079))
TICK = 0.0179                           # the sound program's tick (s), nominal
TICK_MEASURED = 0.017957                # as measured in MAME 0.289 (the YM3438 timer's period)
MOMENT_S = 0.1                          # a "moment" of the game's own loudness: 0.1 s either side (fitted: see the full-scale test)
RAIN_PEAK_DBFS = -13.1                  # the rain bed's own peak, alone (test_the_storm_alone_stays_under_full_scale, measured)
# The tunnel words' fades of the rain (patch 2): C201 steps the level byte up by 8 a tick from the rain's 0x26 to 0xfe (27 steps),
# C200 down by 8 every second tick back to it (54 ticks); a tick to read the word and one more for the first step.
TUNNEL_OUT_S = (27 + 2) * TICK_MEASURED                   # 0.52 s (measured 0.454 .. 0.470 s)
TUNNEL_IN_S = (54 + 2) * TICK_MEASURED                    # 1.01 s (measured 0.946 .. 0.949 s without a duck)


class SoundSession:
    """The sets and runs of this module, made at the first use: the session's normal weather set ("wet": lightning's stand-in never
    strikes), the switch-off set ("dry"), and two test sets on the same stage-1 set: "strike" (the striking stand-in) and "control"
    (the same strikes, the thunder's words replaced by the no-op NOOP_WORD: the same queue turns, no thunder)."""

    def __init__(self, romset_zip, saturn_cue, base: Path):
        import threading
        self.romset_zip, self.saturn_cue, self.base = romset_zip, saturn_cue, base
        self.runs, self.failed, self.sets = {}, {}, {}
        self._lock, self._set_lock = threading.Lock(), threading.Lock()

    def lines(self):
        from tests.test_race_build import _drive_line
        from tests.test_tgp_build import _seven
        from vrtools.arcade.course import course_entry_at, road_lines
        from vrtools.arcade.directory import decode_directory
        out, conv = _seven(self.romset_zip, self.saturn_cue)
        d = decode_directory(out)
        return {BF: [(p.x, p.z) for p in road_lines(out, course_entry_at(out, d[BF].bank, window_base=d[BF].header_base))[0]],
                METRO: _drive_line(conv[METRO - 3])}

    def rain_cells(self) -> int:
        return self.layout().cell("rain", "state")

    def layout(self):
        from vrtools.arcade.weather import carrier, sound
        return carrier.lay_out(set_modules(self._stage1()))[0]

    def _stage1(self):
        from tests.test_weather_carrier import _stage1
        return _stage1(self.romset_zip, self.saturn_cue)

    def build(self, kind: str) -> Path:
        with self._set_lock:
            if kind not in self.sets:
                from tests.test_tgp_build import _build, _seven
                from tests.test_weather_dry import _seven_dry
                (self.base / f"set_{kind}").mkdir(parents=True, exist_ok=True)
                if kind == "wet":
                    rs = _seven(self.romset_zip, self.saturn_cue)[0]
                elif kind == "dry":
                    rs = _seven_dry(self.romset_zip, self.saturn_cue)[0]
                else:
                    rs = make_test_set(self.romset_zip, self.saturn_cue, kind)
                self.sets[kind] = _build(self.base / f"set_{kind}", self.romset_zip, rs)
            return self.sets[kind]

    def _make(self, key):
        from vrtools.arcade.course import DIRECTION_RAM
        from vrtools.arcade.select import WHEEL_FOR_ENTRY
        from vrtools.mame.runner import write_centreline
        kind, setname = key[0], key[1]
        wd = self.base / "runs" / "_".join(key)
        wd.mkdir(parents=True, exist_ok=True)
        lines = self.lines()
        env = {"VR_COURSE": "0", "VR_WHEEL": str(WHEEL_FOR_ENTRY[BF]), "VR_SNAPS": "", "VR_HOLD_CLOCK": "1",
               "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", lines[BF])), "VR_RACE_LOG": str(wd / "race.txt"),
               "VR_RACE_LOG_FROM": "0", "VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"),
               "VR_STALE_LOG": str(wd / "stale_list.txt"), "VR_PCM_LOG": str(wd / "pcm.txt"), "VR_SOUND_LOG": str(wd / "sound.txt")}
        if setname != "dry":
            env["VR_RAIN"] = "1"
            env.update({"VR_STORM_LOG": str(wd / "storm.txt"), "VR_STORM_FRAMES": "1",
                        "VR_STORM_RAIN": f"{self.rain_cells():x}", "VR_STORM_WATCH": ",".join(f"{self.layout().cell('sound', n):x}" for n in ("late", "nthunder", "nrain"))})
        extra = [str(LUA_DIR / "pcm_log.lua")]
        if kind == "chain":
            extra.append(str(LUA_DIR / "race_end.lua"))
            env.update({"VR_END_LOG": str(wd / "end.txt"), "VR_DIRECTION_RAM": f"{DIRECTION_RAM:x}",
                        "VR_END_NEXT": f"{WHEEL_FOR_ENTRY[METRO]}:0:1;{WHEEL_FOR_ENTRY[METRO]}:0",
                        "VR_END_NEXT_LINE": str(write_centreline(wd / "line2.csv", lines[METRO]))})
            seconds = CHAIN_SECONDS
        elif kind == "tover":
            extra.append(str(LUA_DIR / "clock_out.lua"))
            env["VR_CLOCK_OUT"] = str(TOVER_AFTER)
            env.pop("VR_HOLD_CLOCK")                   # a held clock would never run out
            seconds = 70
        elif kind in ("svc", "reset"):
            extra.append(str(LUA_DIR / "test_inputs.lua"))
            env["VR_TEST_LOG"] = str(wd / "test.txt")
            if kind == "svc":
                env["VR_TEST_INPUT"] = f"{SVC_PRESS}:Service Mode:10;{SVC_EXIT}:VR4 (Green):8"
            else:
                env["VR_SOFT_RESET"] = str(RESET_AT)
            seconds = 70
        elif kind == "alone":                          # the attract, no coin: the five words injected (sound_inject.lua)
            env = {"VR_PCM_LOG": str(wd / "pcm.txt"), "VR_SOUND_INJECT": ",".join(f"{f}:{w:04x}" for f, w in ALONE_WORDS)}
            from vrtools.mame.runner import run_mame
            run_mame(LUA_DIR / "sound_inject.lua", 64, wd, self.build(setname), env=env, timeout=1800,
                     extra_args=["-wavwrite", str(wd / "a.wav")])
            return wd
        elif kind == "metro":                          # Metropolis RAIN, the rate tests' autopilot, 150 s: the frame time, the tunnel
            env.update({"VR_WHEEL": str(WHEEL_FOR_ENTRY[METRO]), "VR_AUTOPILOT": str(write_centreline(wd / "line.csv", lines[METRO]))})
            seconds = 150
        else:
            raise ValueError(key)
        env["VR_EXTRA_LUA"] = ";".join(extra)
        run_mame_wav(wd, seconds, self.build(setname), env)
        return wd

    def prefetch(self, keys):
        from concurrent.futures import ThreadPoolExecutor
        keys = [k for k in dict.fromkeys(keys) if k not in self.runs]

        def make(k):
            try:
                wd = self._make(k)
            except Exception as e:                     # noqa: BLE001 (raised again by `run`)
                with self._lock:
                    self.failed[k] = e
                return
            with self._lock:
                self.runs[k] = wd
        self.build("strike"), self.build("control")
        with ThreadPoolExecutor(SOUND_JOBS) as ex:
            list(ex.map(make, keys))

    def run(self, *key) -> "SimpleRun":
        if key in self.failed:
            raise AssertionError(f"the run {key} failed: {self.failed[key]!r}") from self.failed[key]
        if key not in self.runs:
            self.runs[key] = self._make(key)
        return SimpleRun(self.runs[key])


def set_modules(s1, words: dict | None = None) -> list:
    """The test sets' storm modules: the normal set's, picked by name, with the striking stand-in (SCHEDULE) in the lightning's place
    and the sound's triggers with the planted late guard (and `words`); without the handling (it changes the game, not the sound's
    tests' business: the rain's own GAME_CHANGING_MODULES)."""
    from vrtools.arcade.weather import carrier, sound
    from tests.weather_standins import strike_standin
    mods = {n: carrier.module_named(n, s1) for n in ("cover", "rain")}
    return [mods["cover"], strike_standin(SCHEDULE, after=((AFTER_PASS, 1),), late_at=(LATE_PASS,)), mods["rain"],
            sound.module(words=words, planted_late=True)]


def make_test_set(romset_zip, saturn_cue, kind: str):
    """The stage-1 set with set_modules (the cover, the striking stand-in, the rain, the sound's triggers) and the sound board;
    "control": the triggers send NOOP_WORD for the thunder's three words."""
    from tests.test_weather_carrier import _stage1
    from vrtools.arcade.weather import carrier, sound
    s1 = _stage1(romset_zip, saturn_cue)
    words = {b: sound.NOOP_WORD for b in sound.BAND_WORDS} if kind == "control" else None
    return sound.install_board(carrier.build(s1, set_modules(s1, words))[0])


def run_mame_wav(wd: Path, seconds: int, rom_dir: Path, env: dict):
    from vrtools.mame.runner import run_mame
    run_mame(LUA_DIR / "autoplay.lua", seconds, wd, rom_dir, env=env, timeout=3600, extra_args=["-wavwrite", str(wd / "a.wav")])


class SimpleRun:
    """A run's logs: the chip and latch log (pcm_log.lua), the frames (frame_rate.lua), the race log; the WAV read on demand."""

    def __init__(self, wd: Path):
        from tests.test_frame_rate import Run
        from vrtools.mame.runner import parse_pcm_log
        self.wd = wd
        self.pcm = parse_pcm_log(wd / "pcm.txt")
        self.rate_run = Run(wd, finish=False)
        self._wav = None

    def wav(self):
        """(samples as float in [-1, 1), stereo, shape (n, 2); the rate)."""
        if self._wav is None:
            import wave
            import numpy as np
            with wave.open(str(self.wd / "a.wav")) as w:
                sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
                x = np.frombuffer(w.readframes(n), np.int16).reshape(-1, ch)
            self._wav = (x, sr)
        return self._wav

    def mode_starts(self, mode: int) -> list[tuple[int, float]]:
        """(frame, time) of every frame end at which the mode became `mode` (the first boot's frames)."""
        return [(f, t) for f, t, m in self.pcm.modes if m == mode]

    def words(self, which=None) -> list[tuple[int, float, int]]:
        return [w for w in self.pcm.words if which is None or w[2] in which]



def sound_keys(items) -> list:
    """The runs the collected tests `items` read."""
    need = {"test_the_latch_contract": [("chain", "strike")],
            "test_the_other_voices_are_unchanged_outside_the_duck": [("chain", "strike"), ("chain", "control")],
            "test_silence_through_results_name_entry_attract_and_the_next_games": [("chain", "strike")],
            "test_a_race_ending_during_a_thunder": [("chain", "strike"), ("chain", "control")],
            "test_a_strike_after_the_finish_sends_no_thunder": [("chain", "strike")],
            "test_time_over_during_a_thunder": [("tover", "strike")],
            "test_the_test_switch_during_a_rain_race": [("svc", "strike")],
            "test_a_soft_reset_during_a_rain_race": [("reset", "strike")],
            "test_full_scale_only_at_the_games_own_loudest_moments": [("chain", "strike"), ("chain", "dry")],
            "test_the_storm_alone_stays_under_full_scale": [("alone", "strike")],
            "test_the_thunder_adds_no_sample_at_full_scale": [("chain", "strike"), ("chain", "control")],
            "test_the_frame_time_with_the_triggers": [("chain", "strike"), ("metro", "strike")],
            "test_the_tunnel_words_fade_the_rain": [("chain", "strike"), ("metro", "strike")],
            "test_a_late_strike_still_thunders": [("chain", "strike")],
            "test_every_word_on_its_due_pass": [("chain", "strike")]}
    keys = []
    for i in items:
        name = getattr(i, "originalname", None) or getattr(i, "name", "")
        keys += need.get(name, [])
    return keys


_SESSIONS: dict = {}


@pytest.fixture
def sound_runs(request, romset_zip, saturn_cue, tmp_path_factory) -> SoundSession:
    key = str(romset_zip)
    if key not in _SESSIONS:
        s = SoundSession(romset_zip, saturn_cue, tmp_path_factory.mktemp("sound"))
        s.prefetch(sound_keys(request.session.items))
        _SESSIONS[key] = s
    return _SESSIONS[key]


def _race_spans(r: SimpleRun) -> list[tuple[float, float, float]]:
    """(countdown start, green, race end) times of each race of the run's first boot: mode 0x12's first frame, 0x14's, and the first
    mode after 0x14."""
    out, cd, green = [], None, None
    for f, t, m in r.pcm.modes:
        if m == 0x12 and cd is None:
            cd = t
        elif m == 0x14 and cd is not None and green is None:
            green = t
        elif green is not None and m != 0x14:
            out.append((cd, green, t))
            cd = green = None
    return out


def race_show_passes(r: SimpleRun) -> list[list[int]]:
    """The frames of the storm's SHOW passes in the race mode 0x14 (storm_log.lua's S lines, the mode from its F lines), a list per
    RAIN race of the run's first boot: the passes the striking stand-in counts (its n-th is `passes[n - 1]`)."""
    from vrtools.mame.runner import parse_storm_log
    st = parse_storm_log(r.wd / "storm.txt")
    out, cur, k, mode = [], [], 0, None
    for p in st.passes:
        while k < len(st.frames) and st.frames[k][0] <= p.frame:
            mode = st.frames[k][1]
            k += 1
        if p.state == 2 and mode == 0x14:
            cur.append(p.frame)
        elif cur and mode != 0x14:
            out.append(cur)
            cur = []
    return out + ([cur] if cur else [])


def _thunder_keyons(r: SimpleRun) -> list[tuple[float, int, int]]:
    """(time, chip, voice) of every key-on of the crack and the rumble."""
    return sorted((w.time, w.chip, w.voice) for w in r.pcm.writes if (w.chip, w.voice) in ((2, 0x14), (1, 0x15)) and w.reg == 4
                  and w.value & 0x80)


def test_the_latch_contract(sound_runs):
    """The sound-latch contract on three games (RAIN Big Forest to its finish, RAIN Metropolis, DRY Metropolis) with the stand-in's
    strikes: RAIN ON once a RAIN race, in its countdown's first frames; one thunder word a strike, by band, in the race; RAIN OFF once,
    in the frames after the finish; no storm word anywhere else (the DRY game, the results, the attract). On the board: the rain's
    voice keyed on only from RAIN ON to the fade after RAIN OFF; the crack and the rumble keyed on only after a thunder word, its wait
    later (0.3 / 0.6 / 0.9 s)."""
    from vrtools.arcade.weather import sound
    from vrtools.arcade.weather.tune import TICK_S, SoundTune
    r = sound_runs.run("chain", "strike")
    races = _race_spans(r)
    assert len(races) == 3 and r.pcm.boots == r.pcm.boots[:1], races
    words = r.words(STORM_WORDS)
    by_race = [[w for w in words if cd - 0.01 <= w[1] < end + 1.0] for cd, _, end in races]
    assert sum(len(x) for x in by_race) == len(words), "a storm word outside the races and the frames after them"
    shows = race_show_passes(r)
    assert len(shows) == 2, [len(s) for s in shows]
    for k, ((cd, green, end), ws) in enumerate(zip(races, by_race)):
        if k == 2:                                                                  # the DRY game
            assert ws == [], ws
            continue
        seq = [w for _, _, w in ws]
        thunders = [w for w in seq if w in (0xB074, 0xB075, 0xB076)]
        assert seq[0] == sound.WORDS["rain_on"] and seq[-1] == sound.WORDS["rain_off"], [hex(w) for w in seq]
        assert seq.count(sound.WORDS["rain_on"]) == 1 and seq.count(sound.WORDS["rain_off"]) == 1
        # one word for each strike the race reached (the stand-in strikes on its n-th SHOW pass of the race), by band, none lost
        bands = [sound.WORDS[sound.BAND_WORDS[b - 1]] for n, b in SCHEDULE if n <= len(shows[k])]
        assert thunders == bands and len(bands) >= 4, (k, len(shows[k]), [hex(w) for w in thunders], [hex(w) for w in bands])
        on, off = ws[0][1], ws[-1][1]
        assert cd <= on < cd + 0.25, ("RAIN ON not in the countdown's first frames", cd, on)
        assert end <= off < end + 0.4, ("RAIN OFF not right after the finish", end, off)
        assert all(green < t < end for _, t, w in ws if w in thunders), "a thunder word outside the race"
        keyed = [(a, b) for a, b in r.pcm.keyed(2, 0x19) if cd <= a < end + 2]
        assert len(keyed) == 1 and on < keyed[0][0] < on + 0.2 and off < keyed[0][1] < off + 1.0, (keyed, on, off)
    ticks = dict(zip((0xB074, 0xB075, 0xB076), SoundTune().delay_ticks))
    thunder_words = [(t, w) for _, t, w in words if w in ticks]
    for t, chip, voice in _thunder_keyons(r):
        before = [(tw, w) for tw, w in thunder_words if tw < t]
        assert before, (t, chip, voice)
        tw, w = before[-1]
        assert abs(t - tw - ticks[w] * TICK_S) < 0.06, ("a thunder voice keyed off its wait", hex(w), t - tw)
    assert not [k for k in r.pcm.keyed(2, 0x19) if not any(cd <= k[0] < end for cd, _, end in races[:2])]


TICK_FLIPS_MAX = 12                     # writes a tick away at most (the chain on this board: 6, one word read a tick early)


def tick_flips(pa: list, pb: list) -> tuple[list, list]:
    """Two runs' writes (PcmWrite, the same voices kept): (problems, the times of the writes that differ in place). Problems: any
    voice, fixed or one of the five dynamic effect voices (chip 1, 0x10-0x14), whose register values, repeats collapsed, differ in
    sequence or lie more than a tick from their twins (so a dynamic voice's level and pitch at a key-on and its writes after it are
    bounded by shape, not only by the count); a dynamic effect voice's key-ons differing in voice, sample or time (more than a
    tick)."""
    import collections
    key = lambda w: (w.chip, w.voice, w.reg, w.value)
    flips = [x.time for x, y in zip(pa, pb) if key(x) != key(y)]
    dyn = lambda w: w.chip == 1 and 0x10 <= w.voice < 0x15

    def seqs(ws):
        out = collections.defaultdict(list)
        for w in ws:
            k = (w.chip, w.voice, w.reg)
            if not out[k] or out[k][-1][1] != w.value:
                out[k].append((w.time, w.value))
        return out
    sa, sb, problems = seqs(pa), seqs(pb), []
    for k in sorted(set(sa) | set(sb)):
        a, b = sa.get(k, []), sb.get(k, [])
        if [v for _, v in a] != [v for _, v in b] or (a and max(abs(x[0] - y[0]) for x, y in zip(a, b)) > TICK * 1.1):
            problems.append(("a voice's register", k, len(a), len(b)))

    def keyons(ws):
        regs, out = {}, []
        for w in ws:
            if dyn(w):
                regs[(w.voice, w.reg)] = w.value
                if w.reg == 4 and w.value & 0x80:
                    out.append((w.time, w.voice, regs.get((w.voice, 1))))
        return out
    ka, kb = keyons(pa), keyons(pb)
    if len(ka) != len(kb) or any(x[1:] != y[1:] or abs(x[0] - y[0]) > TICK * 1.1 for x, y in zip(ka, kb)):
        problems.append(("the dynamic effect voices' key-ons", len(ka), len(kb)))
    return problems, flips


def _duck_windows(r: SimpleRun) -> list[tuple[float, float]]:
    """[from, to) of each ducking window: from the thunder word's latch time to its wait, the hold (DUCK_HOLD_TICKS), the release
    (a step a tick from the deepest duck) and a margin of 0.3 s; the game's reset 8100 clears the duck: to its time + 0.1 s at
    most."""
    from vrtools.arcade.weather import sound
    from vrtools.arcade.weather.tune import TICK_S, SoundTune
    t = SoundTune()
    ticks = dict(zip((0xB074, 0xB075, 0xB076), t.delay_ticks))
    resets = [tw for _, tw, w in r.words({0x8100})]
    out = []
    for _, tw, w in r.words(set(ticks)):
        to = tw + (ticks[w] + sound.DUCK_HOLD_TICKS + max(t.duck_steps)) * TICK_S + 0.3
        cut = [o for o in resets if tw < o < to]                # the reset clears the duck at once
        out.append((tw, min([to] + [o + 0.1 for o in cut])))
    return out


def test_the_other_voices_are_unchanged_outside_the_duck(sound_runs):
    """The same three games on the control set, whose triggers send the no-op word B062 on the same passes instead of the thunder's
    (the same queue turns): the latch words are the same but for those, at the same frames; on the board every write to every voice
    but the crack's and the rumble's (the engine, the tyres, the music, the effects, the announcer, the rain) is the same, register,
    value and time, but the level writes inside the ducking windows; and only level writes differ there (the duck pulls levels down,
    nothing else).
    Fix round 2 (measured): a thunder's work moves the board's main loop by a few cycles, so where the game's word reaches the board
    within the timer poll's 3.8 us (a 38-cycle loop at 0x1164) of a tick boundary, it is read a tick earlier or later with the
    thunder than without. Such a write is allowed only in this form (`tick_flips`): outside the ducking windows every fixed voice's
    register values in the same sequence, repeats collapsed, each within a tick of its twin, at most TICK_FLIPS_MAX writes a tick
    away, and the dynamic effect voices' key-ons (voice, sample, time) identical. The chain on this board: one word (C055 at 194.631 s,
    0.95 s after the last thunder's rumble ended at 193.681 s, 8.9 s after its word B076): four engine voices' pitch and two levels a
    tick early, nothing else."""
    from vrtools.arcade.weather import sound
    a, b = sound_runs.run("chain", "strike"), sound_runs.run("chain", "control")
    thunder = {0xB074, 0xB075, 0xB076}
    wa = [(f, w) for f, _, w in a.pcm.words]
    wb = [(f, w) for f, _, w in b.pcm.words]
    assert len(wa) == len(wb) and all(x == y or (x[0] == y[0] and x[1] in thunder and y[1] == sound.NOOP_WORD) for x, y in zip(wa, wb))
    assert sum(1 for _, w in wa if w in thunder) >= 6
    wins = _duck_windows(a)

    def others(r):
        return [w for w in r.pcm.writes if (w.chip, w.voice) not in ((2, 0x14), (1, 0x15))]
    oa, ob = others(a), others(b)
    inside = lambda w: any(lo <= w.time < hi for lo, hi in wins)
    key = lambda w: (w.chip, w.voice, w.reg, w.value)
    pa, pb = [w for w in oa if not (w.reg == 5 and inside(w))], [w for w in ob if not (w.reg == 5 and inside(w))]
    na, nb = [key(w) for w in pa], [key(w) for w in pb]
    problems, flips = tick_flips(pa, pb)
    assert problems == [] and len(na) == len(nb) and len(flips) <= TICK_FLIPS_MAX, ("the other voices differ outside the duck",
                                                                                     problems[:4], len(na), len(nb), flips[:8])
    same = [(x, y) for x, y in zip(pa, pb) if key(x) == key(y)]
    shift = max(abs(x.time - y.time) for x, y in same)
    assert shift < TICK, ("a write of another voice moved by more than a tick", shift)   # the handlers' own time moves writes
    la, lb = [key(w) for w in oa if w.reg == 5 and inside(w)], [key(w) for w in ob if w.reg == 5 and inside(w)]
    assert la != lb and len(na) > 50000, (len(la), len(lb), len(na))
    with open(sound_runs.base / "sound_summary.txt", "a") as out:
        out.write(f"other voices: {len(na)} writes outside {len(wins)} ducking windows, {len(na) - len(flips)} identical in "
                  f"place, {len(flips)} a tick away ({sorted(set(round(t, 3) for t in flips))}) (largest time shift "
                  f"{shift * 1e6:.0f} us); level writes inside: {len(la)} with the thunder, {len(lb)} without\n")


def test_silence_through_results_name_entry_attract_and_the_next_games(sound_runs):
    """From the fade after RAIN OFF to the next RAIN race's RAIN ON (Big Forest's goal, results, the attract, Metropolis' selection),
    and through the DRY game that follows a RAIN game (its race, results, any name entry, the attract), none of our three voices is
    keyed on and none sounds but the tail of a thunder keyed before RAIN OFF (the session lead's ruling C2: a thunder that had
    already started finishes its sample); the next RAIN race's rain comes back with its RAIN ON."""
    r = sound_runs.run("chain", "strike")
    races = _race_spans(r)
    offs = [t for _, t, w in r.words({0xB078})]
    ons = [t for _, t, w in r.words({0xB077})]
    assert len(offs) == 2 and len(ons) == 2, (offs, ons)
    quiet = [(offs[0] + 1.2, ons[1]), (offs[1] + 1.2, r.pcm.frames[-1][1])]
    for k, (lo, hi) in enumerate(quiet):                # the window after race k's RAIN OFF
        cd = races[k][0]
        for chip, voice in OURS:
            for a, b in r.pcm.keyed(chip, voice):
                if lo < b and a < hi:                   # only the tail of a thunder keyed in that race before its RAIN OFF (ruling C2)
                    assert (chip, voice) != (2, 0x19) and cd <= a < offs[k] and b - a <= max(THUNDER_LONGEST_S.values()) + TICK, (
                        "our voice sounds where the design says silence", k, chip, voice, a, b)
    dry_cd, dry_green, dry_end = races[2]
    modes = {m for _, t, m in r.pcm.modes if t > dry_end}
    with open(sound_runs.base / "sound_summary.txt", "a") as out:
        out.write(f"silence: our voices silent from {quiet[0][0]:.1f} to {quiet[0][1]:.1f} s and from {quiet[1][0]:.1f} s to the "
                  f"end; modes after the DRY race {sorted(hex(m) for m in modes)} (0x1e: a name entry)\n")


# The longest a thunder sounds from its voices' key-on, by band (the session lead's ruling C2: a thunder that has started finishes its
# sample): the rumble's track holds its note 255 + 108 ticks (close and medium) or the distant one 255 + 137 ticks, then keys it off;
# the crack's 24 ticks. At the measured tick: 6.518 s close and medium, 7.039 s distant (measured 6.51, 6.52, 7.039 s); from the word
# add the wait (0.30 / 0.61 / 0.90 s): 6.8, 7.1, 7.9 s.
THUNDER_TICKS = {0xB074: 255 + 108, 0xB075: 255 + 108, 0xB076: 255 + 137}
THUNDER_LONGEST_S = {w: n * TICK_MEASURED for w, n in THUNDER_TICKS.items()}


def test_a_race_ending_during_a_thunder(sound_runs):
    """Review Focus 2 with the session lead's ruling C2 (the approved prototype: RAIN OFF ends the rain loop, a thunder already
    sounding finishes its sample): Big Forest's finish comes while a close thunder sounds (struck FINISH_LEAD passes before the line).
    The rain's voice is keyed off within 1 s of RAIN OFF; the thunder's voices, keyed before the line, end by themselves within the
    band's longest (THUNDER_LONGEST_S from their key-on, a tick's margin) and nothing of ours sounds after them until the next RAIN
    ON; every thunder of the run ends within its band's longest; from the thunder's end every write to the board is the control
    set's (the same race without thunder), voice, register and value, within a tick."""
    a, b = sound_runs.run("chain", "strike"), sound_runs.run("chain", "control")
    cd, green, end = _race_spans(a)[0]
    off = next(t for _, t, w in a.words({0xB078}) if t >= end)
    on2 = [t for _, t, w in a.words({0xB077}) if t > end][0]
    rain = [x for x in a.pcm.keyed(2, 0x19) if x[0] < end]
    assert rain and rain[-1][1] < off + 1.0, (rain[-1:], off)
    rumble = [x for x in a.pcm.keyed(1, 0x15) if x[0] < end <= x[1]]
    assert rumble, "the rumble did not sound at the finish"
    last = rumble[0][1]
    assert last - rumble[0][0] <= THUNDER_LONGEST_S[0xB074] + TICK, rumble
    for chip, voice in OURS:
        assert not [x for x in a.pcm.keyed(chip, voice) if last < x[1] and x[0] < on2], (chip, voice, "sounds after the thunder")
    words = [(t, w) for _, t, w in a.words(set(THUNDER_LONGEST_S))]
    for x0, x1 in a.pcm.keyed(1, 0x15):
        w = [w for t, w in words if t < x0][-1]
        assert x1 - x0 <= THUNDER_LONGEST_S[w] + TICK, (hex(w), x0, x1)
    nxt = min(_race_spans(a)[1][0], _race_spans(b)[1][0])
    after = lambda r: [w for w in r.pcm.writes if last + 0.5 <= w.time < nxt]
    wa, wb = after(a), after(b)
    assert len(wa) > 5000 and [(w.chip, w.voice, w.reg, w.value) for w in wa] == [(w.chip, w.voice, w.reg, w.value) for w in wb]
    assert max(abs(x.time - y.time) for x, y in zip(wa, wb)) < TICK
    with open(sound_runs.base / "sound_summary.txt", "a") as out:
        out.write(f"finish during a thunder: finish {end:.2f} s, RAIN OFF {off:.2f} s, rain off {rain[-1][1]:.2f} s, the rumble "
                  f"{rumble[0][0]:.2f}-{last:.2f} s ({last - rumble[0][0]:.2f} s); rumbles {[round(x1 - x0, 2) for x0, x1 in a.pcm.keyed(1, 0x15)]}\n")


def test_a_strike_after_the_finish_sends_no_thunder(sound_runs):
    """The prototype's lightning starts a strike only in the race mode 0x14 (spike 70's `light`: `cmp.b #0x14, mode; bne`), so it
    never thunders after the finish though the storm's pictures run on through the goal and results (rain modes). The triggers do
    the same for any strike lightning might raise there: the stand-in strikes on the 30th storm pass after the race (the goal),
    `strike_seq` changes, and no thunder word is sent and no thunder voice keyed until the next race's countdown."""
    r = sound_runs.run("chain", "strike")
    cd, green, end = _race_spans(r)[0]
    cd2 = _race_spans(r)[1][0]
    assert [hex(w) for _, t, w in r.words({0xB074, 0xB075, 0xB076}) if end <= t < cd2] == []
    assert [x for x in _thunder_keyons(r) if end + 0.5 < x[0] < cd2] == []
    passes = parse_storm_log_after(r, end)
    assert passes >= AFTER_PASS, ("the storm ran fewer passes after the race than the stand-in's strike needs", passes)


def tunnel_fade(r: SimpleRun) -> tuple[list, list]:
    """The tunnel words' fades of the rain (design 5.4 / 5.6, patch 2) on a run: (problems, figures). For each C201 sent while the
    rain plays (its voice keyed from before the word to after the fade back) and whose C200 comes after the fade-out could end: the
    rain voice's level byte reaches 0xfe within TUNNEL_OUT_S and stays there until C200; after C200 it is back at
    SoundTune().rain_level within TUNNEL_IN_S, or, where a thunder's duck holds the rain down then (the level hook adds it), within
    the duck's window and no higher than the deepest duck by TUNNEL_IN_S. Figures: (C201 time, out s, back s) of each checked."""
    from vrtools.arcade.weather.tune import SoundTune
    t = SoundTune()
    lvl, deep = t.rain_level, t.rain_level + 2 * max(t.duck_steps)
    lv = [(x.time, x.value) for x in r.pcm.writes if (x.chip, x.voice, x.reg) == (2, 0x19, 5)]
    tw = [(u, x) for _, u, x in r.pcm.words if x in (0xC201, 0xC200)]
    wins = _duck_windows(r)
    problems, figures = [], []
    for i, (t0, x) in enumerate(tw):
        t1 = next((u for u, y in tw[i + 1:] if y == 0xC200), None)
        if x != 0xC201 or t1 is None or t1 - t0 < TUNNEL_OUT_S + 0.1:
            continue
        duck_to = max([hi for lo, hi in wins if lo < t1 + TUNNEL_IN_S and t1 < hi], default=None)
        if not any(a < t0 and max(t1 + TUNNEL_IN_S, duck_to or 0) < b for a, b in r.pcm.keyed(2, 0x19)):
            continue                                    # the rain does not play through it (the DRY game, the rain's own fades)
        reach = next((u for u, v in lv if t0 <= u <= t1 and v == 0xFE), None)
        back = next((u for u, v in lv if u > t1 and v == lvl), None)
        figures.append((round(t0, 3), round(reach - t0, 3) if reach else None, round(back - t1, 3) if back else None))
        if reach is None or reach - t0 > TUNNEL_OUT_S:
            problems.append(("the rain not faded out", round(t0, 3), reach and round(reach - t0, 3)))
        elif [v for u, v in lv if reach < u < t1 and v != 0xFE]:
            problems.append(("the rain not held out until C200", round(t0, 3)))
        if duck_to is None:
            if back is None or back - t1 > TUNNEL_IN_S:
                problems.append(("the rain not back at its level", round(t1, 3), back and round(back - t1, 3)))
        elif r.pcm.level_at(2, 0x19, t1 + TUNNEL_IN_S) > deep or back is None or back > duck_to:
            problems.append(("the rain not back under the duck", round(t1, 3), r.pcm.level_at(2, 0x19, t1 + TUNNEL_IN_S), back))
    return problems, figures


def test_the_tunnel_words_fade_the_rain(sound_runs):
    """F1 (design 5.4 / 5.6: the game's own tunnel words fade the rain out and back): on the strike runs' Metropolis RAIN races (the
    chain's second game: two tunnels while the rain plays; the 150-s race: two), every C201 takes the rain voice from its level to
    0xfe within TUNNEL_OUT_S and holds it there until C200, which brings it back within TUNNEL_IN_S (`tunnel_fade`; under a thunder's
    duck, within the duck)."""
    checked = []
    for key in (("chain", "strike"), ("metro", "strike")):
        problems, figures = tunnel_fade(sound_runs.run(*key))
        assert problems == [], (key, problems)
        checked += figures
        with open(sound_runs.base / "sound_summary.txt", "a") as out:
            out.write(f"tunnel fades {key}: (C201 s, out s, back s) {figures}\n")
    assert len(checked) >= 4, checked


def test_a_late_strike_still_thunders(sound_runs):
    """F2, and the join's round 2, J1 (the session lead's ruling: the trigger is exempt from the guard): the test sets' stand-in
    strikes (medium) on race pass LATE_PASS and the planted late guard makes the triggers find that pass late
    (`module(planted_late=True)`); the trigger counts it late (its `late` cell, storm_log's W lines: "sent on a late pass") and
    queues the medium's B075 on that same pass (its `nthunder` +1 on it, never a later one); exactly one thunder word comes between
    the strikes before and after it. In both RAIN races of the chain."""
    from vrtools.mame.runner import parse_storm_log
    r = sound_runs.run("chain", "strike")
    st = parse_storm_log(r.wd / "storm.txt")
    times = dict(r.pcm.frames)
    before = max(n for n, _ in SCHEDULE if n < LATE_PASS)
    after = min(n for n, _ in SCHEDULE if n > LATE_PASS)
    shows = race_show_passes(r)
    for k, passes in enumerate(shows):
        assert len(passes) > after, (k, len(passes))
        f_prev, f_late, f_next = passes[LATE_PASS - 2], passes[LATE_PASS - 1], passes[LATE_PASS]
        assert st.watch[f_late] == st.watch[f_prev] + 1 and st.watch[f_next] == st.watch[f_late], (k, f_late, st.watch[f_prev],
                                                                                                     st.watch[f_late], st.watch[f_next])
        th = lambda f: st.watches[f][1]
        assert th(f_late) == th(f_prev) + 1 and th(f_next) == th(f_late), (k, "the thunder not queued on the late pass itself",
                                                                           th(f_prev), th(f_late), th(f_next))
        between = [(f, t, w) for f, t, w in r.words({0xB074, 0xB075, 0xB076})
                   if times[passes[before - 1]] + 0.1 < t < times[passes[after - 1]] - 0.1]
        assert [w for _, _, w in between] == [0xB075], (k, between)
        assert times[f_prev] < between[0][1] <= times[f_next] + 0.05, (k, times[f_prev], between[0][1], times[f_next])
        with open(sound_runs.base / "sound_summary.txt", "a") as out:
            out.write(f"late strike, race {k}: pass {LATE_PASS} at frame {f_late} late (the trigger's late count "
                      f"{st.watch[f_prev]} -> {st.watch[f_late]}), B075 at {between[0][1]:.3f} s (the next pass ends at "
                      f"{times[f_next]:.3f} s)\n")


def test_every_word_on_its_due_pass(sound_runs):
    """The join's round 2, J1 (the session lead's ruling: the sound's trigger is exempt from the guard, so every word goes on the pass
    it is due, late or not): in both RAIN races of the chain (Big Forest, then Metropolis, whose passes fill to the guard on long
    runs with the cover in) the trigger's counters (storm_log's W lines: `late`, `nthunder`, `nrain`) show every stand-in strike's
    thunder queued on its own strike pass (SCHEDULE's race passes), RAIN ON on the race's first live pass of a rain mode, RAIN OFF on
    the first live pass after the race mode, and no word on any other pass (a live pass: the frames run in it, STATE SHOW at its
    start). The passes the trigger found late are counted (it sent on them all the same)."""
    from vrtools.arcade.weather import sound
    from vrtools.mame.runner import parse_storm_log
    r = sound_runs.run("chain", "strike")
    st = parse_storm_log(r.wd / "storm.txt")
    frames = sorted(st.watches)
    step = lambda i, f0, f: st.watches[f][i] - st.watches[f0][i]
    thunders = [f for f0, f in zip(frames, frames[1:]) if step(1, f0, f) == 1]
    rains = [f for f0, f in zip(frames, frames[1:]) if step(2, f0, f) == 1]
    lates = [f for f0, f in zip(frames, frames[1:]) if step(0, f0, f) == 1]
    modes = sorted(st.frames)
    mode_at = lambda f: max((m for m in modes if m[0] <= f), default=(0, 0))[1]
    shows = race_show_passes(r)
    assert len(shows) == 2
    want_thunder = [p[n - 1] for p in shows for n, _ in SCHEDULE if n <= len(p)]
    assert thunders == want_thunder, ("thunders not on their strike passes", thunders, want_thunder)
    live = [p.frame for p0, p in zip(st.passes, st.passes[1:]) if p0.state == 2]    # a live pass: SHOW at its start (an S
                                                                                     # line's state is the pass's end's)
    want_rain, prev_end = [], 0
    for p in shows:
        want_rain.append(min(f for f in live if prev_end < f <= p[0] and mode_at(f) in sound.SOUND_MODES))   # RAIN ON
        want_rain.append(min(f for f in live if f > p[-1]))                                                    # RAIN OFF
        prev_end = p[-1]
    assert rains == want_rain, ("rain words not on their passes", rains, want_rain)
    with open(sound_runs.base / "sound_summary.txt", "a") as out:
        out.write(f"due passes: {len(thunders)} thunders on their strike passes, rain words on {rains}; the trigger found {len(lates)} "
                  f"passes late and sent on them\n")


def parse_storm_log_after(r: "SimpleRun", end: float) -> int:
    """SHOW passes of the storm after the race's end (the goal and results' rain modes) in the first race."""
    from vrtools.mame.runner import parse_storm_log
    st = parse_storm_log(r.wd / "storm.txt")
    endf = max(f for f, t in r.pcm.frames if t <= end)
    nxt = next(f for f, t, m in r.pcm.modes if t > end and m == 0x11)
    return sum(1 for p in st.passes if p.state == 2 and endf < p.frame < nxt)


def _ours_off_after(r: SimpleRun, t0: float, within: float) -> None:
    """All our voices keyed off by `t0 + within` and none keyed on after `t0`."""
    for chip, voice in OURS:
        for a, b in r.pcm.keyed(chip, voice):
            assert a < t0 and b <= t0 + within, ("our voice sounds after", chip, voice, a, b, t0)


def test_time_over_during_a_thunder(sound_runs):
    """Big Forest RAIN ended by time over TOVER_AFTER frames after the start while the close thunder of the race's pass 60 sounds: the
    game's reset 8100 follows the race's end within a few frames and keys off all our voices at once (patch 1); RAIN OFF follows; no
    storm word after; nothing of ours sounds after the reset, through the results and the attract."""
    r = sound_runs.run("tover", "strike")
    cd, green, end = _race_spans(r)[0]
    resets = [t for _, t, w in r.words({0x8100}) if t >= end - 0.05]          # sent in the frame the race mode ends
    assert resets and resets[0] < end + 0.2, (end, resets[:2])
    keyons = [t for t, c, v in _thunder_keyons(r)]
    assert keyons and keyons[-1] < end and any(b >= end for a, b in r.pcm.keyed(1, 0x15)), "no thunder in flight at the time over"
    _ours_off_after(r, resets[0], 0.05)
    after = [(t, hex(w)) for _, t, w in r.words(STORM_WORDS) if t > resets[0]]
    assert len(after) <= 1 and all(w == "0xb078" and t < resets[0] + 0.5 for t, w in after), after


def test_the_test_switch_during_a_rain_race(sound_runs):
    """The TEST switch pressed in a RAIN race while a thunder and the rain sound (not run in the prototype): the game sends its reset
    8100 within a few frames and it keys off all our voices; no storm word is sent after the press, in the test menu or after its
    EXIT (the game reboots); nothing of ours sounds after the reset. (The triggers run only inside the scenery call: in the menu,
    where SWITCH stays 1, they do not run.)"""
    r = sound_runs.run("svc", "strike")
    press = next(t for f, t in r.pcm.frames if f == SVC_PRESS)
    resets = [t for _, t, w in r.words({0x8100}) if t >= press]
    assert resets and resets[0] < press + 0.3, (press, resets[:2])
    assert any(a < press < b for a, b in r.pcm.keyed(2, 0x19)), "the rain did not sound at the press"
    _ours_off_after(r, resets[0], 0.05)
    assert [w for _, t, w in r.words(STORM_WORDS) if t > press] == []


def test_a_soft_reset_during_a_rain_race(sound_runs):
    """A soft reset in a RAIN race while the rain and a thunder sound: the boot's reset 8100 keys off all our voices within a second of
    the reset; no storm word after it; nothing of ours sounds after."""
    r = sound_runs.run("reset", "strike")
    assert len(r.pcm.boots) == 2, r.pcm.boots
    reset = r.pcm.boots[1]
    assert any(a < reset < b for a, b in r.pcm.keyed(2, 0x19)), "the rain did not sound at the reset"
    resets = [t for _, t, w in r.words({0x8100}) if t >= reset]
    assert resets and resets[0] < reset + 1.0, (reset, resets[:2])
    _ours_off_after(r, resets[0], 0.05)
    assert [w for _, t, w in r.words(STORM_WORDS) if t > reset] == []


def _full_scale(r: SimpleRun):
    import numpy as np
    x, sr = r.wav()
    return np.nonzero((np.abs(x.astype(np.int32)) >= 32767).any(axis=1))[0] / sr


def test_the_thunder_adds_no_sample_at_full_scale(sound_runs):
    """The three games with every thunder against the same games without (the control set): while a thunder sounds or its duck
    holds (from its word to the end of its rumble or of its ducking window, whichever is later), no output sample at full scale that
    is not within 10 ms of one of the games without thunder, and no more of them (the thunder and its duck add none; a voice left at
    its ducked level moves the mix by a little, so the same clipped moment may fall on neighbouring samples).
    Fix round 2 (measured): outside those windows the two runs' game sounds are the same but for the looped samples' phase after a
    duck, so the game's own near-full-scale moments may clip in one run and not the other: 226.162 s with the thunders (the control
    at -0.26 dBFS there), 225.132 s without. Those lie in the full-scale test's moments (test_full_scale_only_at_the_games_own_
    loudest_moments) and are reported here, not asserted."""
    sa, sb = (sound_runs.run("chain", k) for k in ("strike", "control"))
    a, b = _full_scale(sa), _full_scale(sb)
    rumbles = sa.pcm.keyed(1, 0x15) + sa.pcm.keyed(2, 0x14)
    held = []
    for lo, hi in _duck_windows(sa):
        ends = [y for x, y in rumbles if lo <= x < hi + 1.0]
        held.append((lo, max([hi] + ends)))
    problems, fig = thunder_clips(a, b, held)
    with open(sound_runs.base / "sound_summary.txt", "a") as out:
        out.write(f"thunder full scale: during the thunders {fig['during']} samples with them, against without; outside, "
                  f"{fig['outside']} with, against without\n")
    assert problems == [], (problems, fig)


def thunder_clips(with_t, without_t, held) -> tuple[list, dict]:
    """The full-scale samples' times of the race with the thunders (`with_t`) and without (`without_t`) against the windows `held`
    ([from, to) while a thunder sounds or its duck holds): (problems, figures). Problems: a sample with the thunders inside a window
    without one of the race without within 10 ms; more such samples inside the windows with the thunders than without. Samples
    outside the windows are reported only (figures)."""
    inside = lambda ts: [float(t) for t in ts if any(lo <= t < hi for lo, hi in held)]
    outside = lambda ts: sorted(set(round(float(t), 3) for t in ts if not any(lo <= t < hi for lo, hi in held)))
    da, db = inside(with_t), inside(without_t)
    alone = [round(t, 4) for t in da if not any(abs(t - u) < 0.01 for u in without_t)]
    problems = ([("a full-scale sample only with the thunder", alone)] if alone else []) + \
        ([("more full-scale samples with the thunder", len(da), len(db))] if len(da) > len(db) else [])
    return problems, {"during": (len(da), len(db)), "outside": (outside(with_t), outside(without_t))}


def test_the_thunder_clip_check_on_planted_times():
    """thunder_clips without MAME (the restated test (b) has nothing to catch on its own runs): a planted full-scale sample inside a
    held window with no twin in the race without fails; the same sample with a twin within 10 ms passes, but two of them against one
    fails; the same sample outside every window is reported and passes."""
    held = [(10.0, 12.0), (30.0, 33.5)]
    assert thunder_clips([11.0], [], held)[0] != []
    assert thunder_clips([11.0], [11.005], held)[0] == []
    assert thunder_clips([11.0, 11.001], [11.005], held)[0] != []
    assert thunder_clips([20.0, 226.162], [225.132], held) == ([], {"during": (0, 0), "outside": ([20.0, 226.162], [225.132])})
    assert thunder_clips([33.5], [], held)[0] == [] and thunder_clips([30.0], [], held)[0] != []


def test_full_scale_only_at_the_games_own_loudest_moments(sound_runs):
    """The session lead's ruling C1 (the design's "no output sample at full scale beyond the game's own start horn" cannot hold where
    the game itself is 0.13 dB from full scale without rain, and the rain's level is the owner's): every output sample at full scale
    of the three games with the rain and every thunder lies in a moment where the switch-off set's own output, under the
    same inputs (the same race, the same time from its green), is near full scale within MOMENT_S (the game's own loudest
    moments: the start horns, a collision's effects: Big Forest's collision at 111.0 s peaks at 111.04 s and its clipped samples run to
    111.12 s). The counts are reported (the findings), not asserted.
    "Near" is the threshold from the storm's own peak (fix round 1, M1): the rain alone peaks at RAIN_PEAK_DBFS, so a sample can only
    clip where the game alone is within 2.17 dB of full scale; the window is one tick (TICK_MEASURED), the alignment the reviewer gave.
    History: on the board before fix round 2, whose timeline ran 828.8 us behind the switch-off set's, the one-tick form missed
    111.122 s by 0.20 dB and a fitted 0.1 s window (MOMENT_S) was asserted instead; on fix round 2's board the one-tick form misses
    nothing (fix round 3 asserts it). The fitted 0.1 s form is still computed and reported."""
    import numpy as np
    a, d = sound_runs.run("chain", "strike"), sound_runs.run("chain", "dry")
    ra, rd = _race_spans(a), _race_spans(d)
    (xd, sr) = d.wav()
    full = _full_scale(a)

    def misses(window, near):
        bad = []
        for t in full:
            k = next((k for k, (cd, green, end) in enumerate(ra) if cd - 1 <= t < end + 3), None)
            if k is None:
                bad.append((round(float(t), 3), "outside the races"))
                continue
            td = t - ra[k][1] + rd[k][1]
            seg = np.abs(xd[max(0, int((td - window) * sr)):int((td + window) * sr)].astype(np.int32))
            if seg.size == 0 or seg.max() < near:
                bad.append((round(float(t), 3), round(20 * np.log10(max(1, seg.max()) / 32767), 2) if seg.size else None))
        return bad
    near = 32767 * (1 - 10 ** (RAIN_PEAK_DBFS / 20))                  # -2.17 dBFS
    fitted = misses(MOMENT_S, near)
    bad = misses(TICK_MEASURED, near)
    nd = int((np.abs(xd.astype(np.int32)) >= 32767).any(axis=1).sum())
    nnear = int((np.abs(xd.astype(np.int32)) >= near).any(axis=1).sum())
    with open(sound_runs.base / "sound_summary.txt", "a") as out:
        out.write(f"full scale: the storm's games {len(full)} samples at full scale "
                  f"({sorted(set(round(float(t), 2) for t in full))}); the switch-off set's {nd} (within 2.17 dB: {nnear}); "
                  f"within a tick (asserted) it misses {sorted(set(bad))}, within 0.1 s {sorted(set(fitted))}\n")
    assert bad == [], bad[:10]


def test_the_storm_alone_stays_under_full_scale(sound_runs):
    """The storm's sounds alone (the attract, the words injected): the rain bed held peaks under -6 dBFS (measured -13 dBFS: it never
    reaches full scale by itself), every thunder under -1 dBFS; RAIN OFF leaves silence. Their levels are out/p75storm's (alone:
    close 0-1 s RMS -10.9 dBFS, medium -11.7, distant -14.1; the rain -20.9), within 0.3 dB."""
    import numpy as np
    r = sound_runs.run("alone", "strike")
    x, sr = r.wav()
    f = x.astype(float).mean(axis=1) / 32768
    wt = {w: t for _, t, w in r.pcm.words}
    db = lambda v: 20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)
    pk = lambda v: 20 * np.log10(np.abs(v).max() + 1e-12)
    rain = f[int((wt[0xB077] + 1) * sr):int(wt[0xB078] * sr)]
    assert pk(rain) < -6 and abs(db(rain) - (-20.9)) < 0.3, (pk(rain), db(rain))
    for w, rms, delay in ((0xB074, -10.9, 0.30), (0xB075, -11.7, 0.61), (0xB076, -14.1, 0.90)):
        t0 = wt[w] + delay
        seg = f[int((t0 - 0.05) * sr):int((t0 + 1.5) * sr)]
        on = int((t0 - 0.05) * sr) + int(np.argmax(np.abs(seg) > 0.02))
        one = f[on:on + sr]
        assert pk(one) < -1 and abs(db(one) - rms) < 0.3, (hex(w), pk(one), db(one))
    assert db(f[int((wt[0xB078] + 1) * sr):int((wt[0xB078] + 3) * sr)]) < -55
    with open(sound_runs.base / "sound_summary.txt", "a") as out:
        out.write(f"alone: rain RMS {db(rain):.1f} dBFS peak {pk(rain):.1f}\n")


def test_the_frame_time_with_the_triggers(sound_runs):
    """With the triggers and the stand-in's strikes: Big Forest's and Metropolis' RAIN races hold the rain's frame gates (every pass
    of the race at most RAIN_BUSY_MAX_MS, no stale display list); on every pass of the storm's in which the vblank count moved, at
    most UNIT_MAX_US from the move to the guard's trip and TAIL_US from the trip to the pass's end (`post_move_over`, the join's split
    bound; the queue calls happen on these runs); the triggers skip a pass
    (their `late` cell, storm_log's W lines) only when it is late, the vblank count having moved (an A line), or on the planted late
    pass of each race (LATE_PASS); the strikes' words are not lost by it (the latch contract counts them, test_a_late_strike_...)."""
    from types import SimpleNamespace
    from tests.test_weather_rain import POST_MOVE_MAX_US, post_move, post_move_over
    from vrtools.mame.framerate import FRAME_US, RAIN_BUSY_MAX_MS
    from vrtools.mame.runner import parse_stale_log, parse_storm_log
    for key in (("chain", "strike"), ("metro", "strike")):
        r = sound_runs.run(*key)
        st = parse_storm_log(r.wd / "storm.txt")
        assert post_move_over(SimpleNamespace(storm=st)) == [], (key, POST_MOVE_MAX_US, post_move_over(SimpleNamespace(storm=st))[:3])
        planted = {p[LATE_PASS - 1] for p in race_show_passes(r) if len(p) >= LATE_PASS}
        frames = sorted(st.watch)
        skipped = [f for f0, f in zip(frames, frames[1:]) if st.watch[f] == st.watch[f0] + 1]
        assert len(planted) >= 1 and planted <= set(skipped) and [f for f in skipped if f not in planted and f not in st.after] == [], (
            key, sorted(planted), skipped[:10])
        assert all(st.watch[f] - st.watch[f0] in (0, 1) or st.watch[f] == 0 for f0, f in zip(frames, frames[1:]))   # 0: a load
        rr = r.rate_run
        assert rr.load and rr.green, key
        end = _race_spans(r)[0][2] if _race_spans(r) else r.pcm.frames[-1][1]
        last = max(f for f, t in r.pcm.frames if t <= end)
        stretch = [f for f in rr.frames if rr.start <= f.frame <= last]
        frames = [f.frame for f in rr.frames]
        excused = {frames[i + 1] for i, f in enumerate(rr.frames[:-1]) if f.busy_us >= FRAME_US}   # the pass after a load (the
        stale = [f for f in parse_stale_log(r.wd / "stale_list.txt")                                # rate logic's and _stale's rule)
                 if rr.start <= f <= last and f not in excused]
        busiest = max(stretch, key=lambda f: f.busy_us)
        text = str(stale)
        assert len(stretch) > 1000 and stale == [] and busiest.busy_us <= RAIN_BUSY_MAX_MS * 1000, (key, text, busiest)
        with open(sound_runs.base / "sound_summary.txt", "a") as out:
            out.write(f"frame time {key}: {len(stretch)} passes, busiest {busiest.busy_us / 1000:.3f} ms at {busiest.frame}, stale {text}; "
                      f"the triggers skipped {len(skipped)} passes late ({len(planted)} planted); post-move longest "
                      f"{max((a or 0 for a in post_move(SimpleNamespace(storm=st)).values()), default=0):.0f} us\n")
