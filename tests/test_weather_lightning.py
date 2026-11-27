"""Weather stage 4, the lightning (spec 5.5, 5.4's last point and 6; weather/lightning.py on the carrier of weather/carrier.py): its
tune, timelines, bolt objects, colours, flash skies, white-out table and grids equal the prototype's (spike 60/62's "thin" tune as
joined in spike 70; the values pinned here were computed from the prototype's own functions, on this branch's set for the grids:
out/p80l/scripts/proto_values.py and grids_proto.py); the module's cells and its place in the frame order; and in MAME: the flash
rule over a stress build (a strike every 0.4-1.2 s, a test-only tune) on all ten courses, with the rate gates; a pattern denser than
the rule allows cut at its fourth onset; the white-out only on a strike's first stroke; under cover no bolt and no white-out and
the sky flash kept (a stand-in `cover` module saying 1 over a stretch); sampled strikes on all ten courses off the road, in front of
the camera and sorted behind nearer scenery; a race ending mid-strike leaves the sky and the grade right, and released clean; the
strikes in the RAIN race matrix (tests/test_weather_rain.py's runs, which carry this module's log).

The MAME runs of this module are made together at the first test that needs one (`light_runs`), VR_MAME_JOBS (default 2) at a time."""
import hashlib
import os
import statistics
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from vrtools.arcade.patch import PatchError
from vrtools.arcade.select import WHEEL_FOR_ENTRY
from vrtools.arcade.weather import carrier
from vrtools.mame.framerate import RAIN_BUSY_MAX_MS, arcade_rate_misses
from vrtools.mame.runner import LUA_DIR, light_env, parse_light_log, parse_stale_log, parse_storm_log, run_mame
from tests.test_weather_rain import HEAVY6, NAMES, POST_MOVE_MAX_US, RACES, _id, post_move_over, storm_runs  # noqa: F401

STRESS = (0.4, 1.2)                     # the stress build's interval (the prototype's out/p60stress)
STRESS_SECONDS = 90
COVER_ENTRIES = (6, 3)                  # the join: the real cover's flagged stretches, Metropolis (its long tunnel 251-311, the roof by
                                        # the pits 50-62) and Alpine (its tunnel 108-146), on the stress runs of those courses
DENSE = ((1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1),)    # 5 onsets in 13 logic frames (the prototype's out/p60ruletest)
END_AFTER = 634                         # the clock out this many frames after the race start: the race ends right after a white-out pass
END_INPUT = "2900:Coin 1:10;2950:1 Player Start:10"   # then a coin and START in the results: the next game's selections
END_SECONDS = 80
WINDOW_FRAMES = 58                      # video frames covering more than a second (57.52 a second)
JOBS = int(os.environ.get("VR_MAME_JOBS") or 2)
# TEST-ONLY planted faults for the RED evidence (lightning.FAULTS, comma-separated): every set this module builds carries them
FAULT = tuple(f for f in (os.environ.get("VR_LIGHT_FAULT") or "").split(",") if f)
from vrtools.arcade.weather.lightning import FAULTS as _FAULTS  # noqa: E402
if [f for f in FAULT if f not in _FAULTS]:            # the final review's W7: a mistyped fault would build a clean set silently
    raise ValueError(f"VR_LIGHT_FAULT={','.join(FAULT)}: only {', '.join(_FAULTS)}")
REFUSED_SECONDS = 60
METROPOLIS = 6
STREET_AIM = (2.0, 10.0)                # task 8: Metropolis aims down the street (the owner on spike 85's play set: "i think that works
                                        # better on metropolis"); every other course the approved 12-40 degrees
VIS_SECONDS = 100                       # the visibility runs (spike 85's): about 34 strikes on the stress tune
VIS_CLEAR_MIN = 0.35                    # Metropolis normal, the street aim: at least this share of strikes clearly visible (this
                                        # test's runs: 48 % street, 23 % the old aim; spike 85, with the handling: 43 % and 27 %) ...
VIS_MEDIAN_MIN = 0.20                   # ... and the median strike shows at least this share of its bolt (0.34 street, 0.10 old)
VIS_MIN_STRIKES = 20                    # strikes with a measurable twin (27 in this test's run)
MID_FRAME = 2442                        # the stress run on Big Forest: a white-out pass ends at 2443 (its flash sky and white-out up)
MID_SVC = (f"{MID_FRAME}:Service Mode:10;" + ";".join(f"{MID_FRAME + 100 + 40 * k}:VR1 (Red):8" for k in range(8))
           + f";{MID_FRAME + 450}:VR4 (Green):8;{MID_FRAME + 3500}:VR4 (Green):8;{MID_FRAME + 3600}:VR1 (Red):8;"
           f"{MID_FRAME + 3640}:VR1 (Red):8;{MID_FRAME + 3700}:VR4 (Green):8")   # the rain's SVC_INPUT, moved: MEMORY TEST, then EXIT
MID_EXIT = MID_FRAME + 3700
MID_RESET = MID_FRAME + 1                # MAME's soft reset at the white-out pass's frame end
# v0.4.1, the lit rain (the streaming rain's design point 6: on a strike's sky flash every streak the palette's brightest white and
# three times as wide): it changes only the rain's colour words and width, never palette RAM or the colour RAM, so the flash rule's
# measure (`observed_flash`) cannot see it; these show it adds no flash onset from the picture itself (rain_pixels.lua's mean
# relative luminance of the picture at every race frame on the stress runs; its key-coloured copy, LIT_KEY, its share).
PIC_STEP = 0.10                         # a picture flash: its mean relative luminance up this much over its lowest of the last
PIC_BACK = 8                            # PIC_BACK frames, and a fall of as much before the next one (WCAG's general flash, over the
                                        # whole picture)
PIC_MATCH = 3                           # video frames: a picture flash this near one of the lightning's onsets is that onset
LIT_SHARE_MAX = 0.12                    # the lit streaks' share of the picture on a flash frame, a reported bound (fix round 1: the
                                        # ten courses' maxima 0.058-0.109, Surfers Road highest; the first bound, 0.10, PIC_STEP, was
                                        # passed on Surfers Oval 0.106 and Surfers Road 0.109). The lit streaks switch on only on the
                                        # lightning's own flash passes (test_the_lit_rain_on_the_stress_runs): the evidence that they
                                        # add no onset; this share says how much of the picture they are then
SCENE_KEY_MAX = 600                     # a course's own pixels in the lit set's key colour (magenta) on the frames without a lit rain
                                        # (fix round 1: Pacific Coast 514 at most, its race's first minute, Big Forest 278, the others
                                        # 0-2; the lit-key run's own pass-by-pass check shows no lit pass there: the scene's)
RAIN_WATCH = ("WCUR", "AGLOW", "PN", "PM", "PF")   # the rain's cells on the stress runs' W lines, after the sound's nthunder


# ---- the log (lightning_log.lua: vrtools.mame.runner.light_env / parse_light_log) -------------------------------------------
def fbits(v: int) -> float:
    return struct.unpack("<f", struct.pack("<I", v & 0xFFFFFFFF))[0]


def storm_span(storm) -> range:
    """The frames over which the storm is loaded (storm_log.lua's S lines): from the load's pass (the first whose state is not
    IDLE) to the release's (the first after it back at IDLE) or the run's end. The re-review of the final wave: observed_flash's
    strict span is the storm's own state, not what the sky shows, so a wrong sky on the first visible pass, or one the release
    writes, cannot pass as "no flash"."""
    live = [k for k, p in enumerate(storm.passes) if p.state != 0]
    if not live:
        return range(0)
    lo = live[0]
    hi = next((k for k in range(lo, len(storm.passes)) if storm.passes[k].state == 0), len(storm.passes) - 1)
    return range(storm.passes[lo].frame, storm.passes[hi].frame + 1)


def observed_flash(passes, rs, entry, storm) -> list[tuple[int, int]]:
    """(frame, the full-screen flash shown at the pass's end) from palette RAM and the colour RAM, not the module's own cells: the
    sky's slot (0 the grey, 1..3 the flash skies, matched on the backdrop's colours 1..3), 4 when the colour RAM is washed (its first
    probe, the white-out's first row, at the white-out table's value). Over the storm's own span (`storm_span`: from the load to the
    release, from the storm log `storm`; before the load the backdrop holds the game's own palettes, which are no flash), a sky
    that is none of the known ones (the course's own, the rain's grey, the three flash skies) FAILS the run with its frame and value
    (the final review's W7: a wrong, bright sky must not pass as "no flash"; its re-review: the span from the storm's state, not
    from what the sky shows); outside that span a pass counts as no flash."""
    from vrtools.arcade.weather import lightning, rain
    _, _, n, cols = rain.course_sky(rs, entry)
    grey = rain.grey_sky(cols, entry == rain.METROPOLIS)
    slots = {tuple(cols[1:4]): 0, tuple(grey[1:4]): 0,
             **{tuple(lightning.flash_sky(grey, k)[1:4]): i + 1 for i, k in enumerate(lightning.SKY_K)}}
    W = lightning.whiteout_table()
    washed = int(W[0, 31, 32])                          # the first row the white-out writes (any white-out writes it)
    span = storm_span(storm)
    assert len(span) > 0, (entry, "the storm never loaded")
    out = []
    for p in passes:
        if p.frame in span:
            assert tuple(p.sky) in slots, (entry, p.frame, "a sky that is none of the known ones", [hex(c) for c in p.sky])
        f = slots.get(tuple(p.sky), 0)
        if p.probes[0] == washed:
            f = 4
        out.append((p.frame, f))
    return out


def onsets(levels) -> list[int]:
    """The frames of the flash onsets in [(frame, flash)]: a rise from 0, or a rise after a fall (the rule's definition)."""
    out, prev, falling = [], 0, False
    for f, v in levels:
        if v > prev and (prev == 0 or falling):
            out.append(f)
        if v < prev:
            falling = True
        if v > prev:
            falling = False
        if v == 0:
            falling = False
        prev = v
    return out


def crowded(frames, n=3, window=WINDOW_FRAMES) -> list[tuple[int, int]]:
    """(first, last) of every n + 1 onsets within `window` video frames (more than n in a second)."""
    return [(frames[i], frames[i + n]) for i in range(len(frames) - n) if frames[i + n] - frames[i] < window]


def band_of(d: float) -> int:
    from vrtools.arcade.weather import lightning
    return 1 if d < lightning.BANDS[0] else 2 if d < lightning.BANDS[1] else 3


def interface_errors(passes) -> list:
    """The sound's cells against the strikes (the interface of 19 Nov 2026, amended in fix round 1): strike_seq changes on a pass
    exactly when a strike's timeline begins there (the strikes counter goes up and the step is 1), by exactly +1, and on no other
    pass (an aborted placement, a strike skipped, changes nothing); strike_band is 1 / 2 / 3 by the strike's distance against BANDS,
    already set on that same pass, and held: it changes on no other pass of the run (not at the strike's end, not on a re-strike,
    not on an aborted attempt). The errors, as (frame, what)."""
    errs, prev = [], None
    for p in passes:
        if prev is not None:
            began = p.s["NSTRIKE"] != prev.s["NSTRIKE"]
            if began and (p.s["NSTRIKE"] != prev.s["NSTRIKE"] + 1 or p.s["STEP"] != 1):
                errs.append((p.frame, f"strikes {prev.s['NSTRIKE']} -> {p.s['NSTRIKE']}, step {p.s['STEP']}"))
            if began != (p.seq != prev.seq) or (began and p.seq != prev.seq + 1):
                errs.append((p.frame, f"strike_seq {prev.seq} -> {p.seq}, a strike began: {began}"))
            if began and p.band != band_of(fbits(p.s["DV"])):
                errs.append((p.frame, f"strike_band {p.band}, distance {fbits(p.s['DV']):.0f}"))
            if not began and p.band != prev.band:
                errs.append((p.frame, f"strike_band {prev.band} -> {p.band} with no strike"))
        prev = p
    return errs


def strikes_of(passes) -> list[list]:
    """The passes of each strike's timeline (PHASE RUNNING), one list a strike (a new strike_seq)."""
    out, cur, seq = [], None, None
    for p in passes:
        if p.s["PHASE"] == 3:
            if p.seq != seq:
                cur = []
                out.append(cur)
                seq = p.seq
            cur.append(p)
    return out


# ---- static: the tune, the timelines, the objects, the colours, the tables, the grids -------------------------------------------
def test_lightning_tune_defaults_and_bounds():
    """LightningTune: S5.5's values (a strike every 20-40 s, 300-800 units away, strokes 45 % thinner, at most three onsets in a
    second); others refused; the stress build's 0.4-1.2 s allowed."""
    from vrtools.arcade.weather.tune import LightningTune
    t = LightningTune()
    assert (t.interval_s, t.distance, t.stroke_scale, t.max_onsets_per_s) == ((20.0, 40.0), (300.0, 800.0), 0.55, 3)
    for bad in ({"interval_s": (40.0, 20.0)}, {"interval_s": (0.05, 1.0)}, {"distance": (800.0, 300.0)}, {"distance": (50.0, 300.0)},
                {"distance": (300.0, 1200.0)}, {"stroke_scale": 0.1}, {"stroke_scale": 1.5}, {"max_onsets_per_s": 4},
                {"max_onsets_per_s": 0}):
        with pytest.raises(ValueError):
            LightningTune(**bad)
    assert LightningTune(interval_s=STRESS).interval_s == STRESS


def test_the_aim_tune():
    """Task 8: the aim range (degrees off the camera's horizontal view direction, each side) is a tune: by default the approved 12-40
    for every course but Metropolis (entry 6), which aims down the street, 2-10; a course not in the table gets the default;
    a range must be 0 <= low < high <= AIM_MAX (40: the approved range's top, inside the in-view check's 43 degrees) and an entry
    listed once."""
    from vrtools.arcade.weather.tune import AIM_MAX, LightningTune
    t = LightningTune()
    from vrtools.arcade.weather import rain
    from vrtools.arcade.weather.tune import METROPOLIS_ENTRY
    assert t.aim_deg == (12.0, 40.0) and t.aim_by_entry == ((METROPOLIS, STREET_AIM),) and AIM_MAX == 40.0
    assert METROPOLIS_ENTRY == rain.METROPOLIS == METROPOLIS
    assert t.aim_for(METROPOLIS) == STREET_AIM and all(t.aim_for(e) == (12.0, 40.0) for e in range(10) if e != METROPOLIS)
    assert LightningTune(aim_by_entry=()).aim_for(METROPOLIS) == (12.0, 40.0)
    assert LightningTune(aim_deg=(5.0, 30.0), aim_by_entry=()).aim_for(3) == (5.0, 30.0)
    for bad in ({"aim_deg": (10.0, 5.0)}, {"aim_deg": (-1.0, 10.0)}, {"aim_deg": (12.0, 41.0)}, {"aim_deg": (12.0, 12.0)},
                {"aim_by_entry": ((6, (2.0, 10.0)), (6, (3.0, 9.0)))}, {"aim_by_entry": ((-1, (2.0, 10.0)),)},
                {"aim_by_entry": ((6, (0.0, 50.0)),)}, {"aim_by_entry": ((6, (10.0, 2.0)),)}):
        with pytest.raises(ValueError):
            LightningTune(**bad)


def test_the_faults_are_known():
    """VR_LIGHT_FAULT (the RED evidence's planted faults) may name only lightning.FAULTS: the module refuses another name at import
    (a mistyped fault would build a clean set and pass silently)."""
    import subprocess
    import sys
    from vrtools.arcade.weather import lightning
    assert set(lightning.FAULTS) == {"band", "seq", "cover", "norule"} and set(FAULT) <= set(lightning.FAULTS)
    r = subprocess.run([sys.executable, "-c", "import tests.test_weather_lightning"], capture_output=True, text=True,
                       env={**os.environ, "VR_LIGHT_FAULT": "seq,bnad"}, cwd=Path(__file__).resolve().parents[1])
    assert r.returncode != 0 and "VR_LIGHT_FAULT=seq,bnad: only band, seq, cover, norule" in r.stderr, r.stderr[-300:]


def test_the_timelines():
    """The six patterns of spike 60 (30, 27, 31, 32, 26, 32 logic frames, 0.9-1.1 s): each begins with the bolt alone, has two or
    three strokes, the white-out (level 4) once and only in its first stroke, later strokes the smaller sky flash (1), the dim
    flicker to end; by the rule's definition 2-3 onsets each, never more than the rule allows inside one pattern."""
    from vrtools.arcade.weather import lightning as L
    assert [len(p) for p in L.PATTERNS] == [30, 27, 31, 32, 26, 32]
    for p in L.PATTERNS:
        st = L.strokes(p)
        assert p[0] == 5 and 2 <= len(st) <= 3 and set(p) <= {0, 1, 2, 4, 5, 6}
        assert p.count(4) == 1 and 4 in st[0] and all(4 not in s and max(s) <= 5 and 1 in s for s in st[1:])
        flashes = [(k, L.FLASH_OF_LEVEL[v]) for k, v in enumerate(p)]
        assert 2 <= len(onsets(flashes)) <= 3 and crowded([2 * f for f in onsets(flashes)]) == []
    tab = L.pattern_table()
    assert len(tab) == L.PAT_LEN * 6 + 16 and tab[L.PAT_LEN * 6:L.PAT_LEN * 6 + 7] == bytes(L.FLASH_OF_LEVEL)
    with pytest.raises(PatchError):
        L.pattern_table(((5, 3, 5),))                  # level 3 (spike 51's half wash) is not built


def test_the_bolt_objects():
    """12 bolt objects (6 shapes and their mirrors, seed 56) with the rods 0.012 x 0.55 = 0.0066 thick, the prototype's bytes (the
    "thin" tune Pascal kept: "this is it, 45 is great keep it"); records 99-175 (the budget reserves the largest); every record
    sorted by its quad's farthest vertex (ZMAX: nearer scenery draws over the bolt), the glow strips solid and unculled, the rods
    culled; the far thickening 1 .. 1.30 over 360 units from 420."""
    from vrtools.arcade.weather import lightning as L
    objs = L.bolt_objects(0.55)
    assert [n for _, n, _ in objs] == [139, 119, 163, 159, 99, 175] * 2 and [g for _, _, g in objs] == [34, 29, 40, 39, 24, 43] * 2
    assert hashlib.sha256(b"".join(o for o, _, _ in objs)).hexdigest()[:16] == "bca649244b44e605"
    assert sum(len(o) for o, _, _ in objs) == 69088
    for o, n, g in objs:
        flags = [struct.unpack_from("<I", o, 24 + 40 * k)[0] for k in range(n)]
        assert all(f & 0x0C00 == L.ZMAX and f & 1 for f in flags)
        assert all(f & L.NOCULL for f in flags[:g]) and not any(f & L.NOCULL for f in flags[g:])
        assert struct.unpack_from("<I", o, 24 + 40 * n)[0] == 0
    assert abs(L.KH1 * L.KH_SPAN - 0.30) < 1e-9 and L.R_MAIN0 * 0.55 == pytest.approx(0.0066)


def test_the_tables():
    """The direction and turn tables, the white-out table (the overcast table's output 85 % toward 255, the protected entries too)
    and the flash skies (the grey sky 40 / 80 / 95 % toward a slightly warm white; every 16th colour and bit 15 kept) are the
    prototype's."""
    from vrtools.arcade.weather import lightning as L, rain
    dtab, jt = L.angle_tables()
    assert hashlib.sha256(dtab).hexdigest()[:16] == "6f868dfae4fc9d66" and hashlib.sha256(jt).hexdigest()[:16] == "25e972816c98ef5d"
    W = L.whiteout_table()
    assert hashlib.sha256(rain.table_bytes(W)).hexdigest()[:16] == "bdc117f94ab1ce6e"
    assert (int(W[1, 3, 10]), int(W[0, 0, 60]), int(W[2, 31, 63])) == (220, 217, 255)
    cols = [0x1234, 0xFC00, 0x03E0, 0x001F, 0x5294, 0x8000 | (6 << 5) | 30 << 10, 12345 & 0x7FFF]
    want = {0.4: ["0x1234", "0xf98c", "0x2fec", "0x2d9f", "0x5f18", "0xf60c", "0x49bb"],
            0.8: ["0x1234", "0xf719", "0x5bd9", "0x5b1f", "0x6b9d", "0xf339", "0x671e"],
            0.95: ["0x1234", "0xf39d", "0x6fdd", "0x6f9f", "0x73de", "0xf3bd", "0x6fbf"]}
    for k, w in want.items():
        assert [hex(v) for v in L.flash_sky(cols, k)] == w


def test_the_bolt_colours_are_the_prototypes(romset_zip, saturn_cue):
    """The eight colour words (glow, left, highlight, right; then dim), picked from the program ROM's polygon palette with the
    prototype's targets under the grade, are the prototype's picks (from its palette dump): 692, 248, 27, 227; 571, 542, 197, 150."""
    from tests.test_tgp_build import _seven
    from vrtools.arcade.weather import lightning as L
    out, _ = _seven(romset_zip, saturn_cue)
    words = L.bolt_colour_words(out)
    assert [w & 0x3FF for w in words] == [692, 248, 27, 227, 571, 542, 197, 150] and all(w & 0xC00 == 0xC00 for w in words)


# the prototype's grids (spike 60's height_grid, spike 70's encode_grids) on this branch's set: sha256[:12] of this branch's blobs,
# checked equal cell for cell against the prototype's by out/p80l/scripts/grids_proto.py
GRID_SHA = ("881eef8818ed", "b7adac03972d", "c41a9ee27ade", "00dfd16f4b0e", "066d406ff37e", "ec69015094a6", "740a772e7786",
            "6a4f3a5790e8", "4e5e3d79d3bb", "ad3780980f19")


def test_the_grids(romset_zip, saturn_cue):
    """Each course's foot and occluder grids (16-unit cells from the course's own tile geometry) in int8 at scale 1 (lossless: the
    largest foot error 0), cropped to the box of cells that hold anything, are the prototype's (the blobs' hashes, checked against
    the prototype's grids cell for cell); the crop is lossless (outside the box nothing but "beyond the band" and "none"); no cell
    within ROAD_CLEAR units of the centreline offers a foot: no bolt is struck on the road."""
    from tests.test_tgp_build import _seven
    from vrtools.arcade.course import course_entry_at, road_lines
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.weather import lightning as L
    out, _ = _seven(romset_zip, saturn_cue)
    for e, d in enumerate(decode_directory(out)):
        blob, st = L.grid_blob(out, e)
        assert st["scale"] == 1 and st["foot error"] == 0, (e, st)
        assert hashlib.sha256(blob).hexdigest()[:12] == GRID_SHA[e], e
        g, o, s, base = L.decode_grid_blob(blob)
        centre = np.array([(q.x, q.z) for q in road_lines(out, course_entry_at(out, d.bank, window_base=d.header_base))[0]])
        js, is_ = np.nonzero((g != L.GINV) & (g != L.GBEY))
        cx, cz = L.GRID_O + (is_ + 0.5) * L.GRID_C, L.GRID_O + (js + 0.5) * L.GRID_C
        a, b = centre, np.roll(centre, -1, 0)
        dmin = np.full(len(cx), 1e9)
        for (ax, az), (bx, bz) in zip(a, b):
            dx, dz = bx - ax, bz - az
            t = np.clip(((cx - ax) * dx + (cz - az) * dz) / (dx * dx + dz * dz or 1.0), 0, 1)
            dmin = np.minimum(dmin, np.hypot(cx - ax - t * dx, cz - az - t * dz))
        assert len(dmin) > 100 and dmin.min() >= L.ROAD_CLEAR, (e, len(dmin), dmin.min())


def test_the_module_and_its_place(romset_zip, saturn_cue):
    """The registry's order is cover, lightning, rain, handling, sound (the join's; the strike drawn before the rain: served
    first by both guards; the session lead's ruling of 19 Nov 2026); the lightning owns `strike_seq` and `strike_band` and reads the
    cover's `under_cover` by name (absent, the layout raises naming it); its code disassembles as instructions throughout; its RAM
    fits (the image, the cells, one course's data)."""
    from tests.test_tgp_build import _seven
    from tests.test_weather_carrier import _stage1
    from vrtools.arcade.disasm import listing_bytes
    from vrtools.arcade.weather import lightning as L
    from vrtools.arcade.weather.tune import LightningTune
    s1 = _stage1(romset_zip, saturn_cue)
    mods = carrier.default_modules(s1)
    assert [m.name for m in mods] == ["cover", "lightning", "rain", "handling", "sound"]     # the join's order
    lay, pieces, image = carrier.lay_out(mods)
    assert lay.label("lightning", "frame") < lay.label("rain", "frame")
    for n in ("strike_seq", "strike_band"):
        assert carrier.MODULE_CELLS[0] <= lay.cell("lightning", n) < carrier.MODULE_CELLS[1]
    with pytest.raises(PatchError, match="under_cover"):
        carrier.lay_out([L.module(s1, LightningTune()), mods[2]])
    at, code = pieces["lightning"]
    lines = listing_bytes(code, at)
    assert sum(len(x.bytes) for x in lines) == len(code)
    assert not [x for x in lines if x.text.startswith("$") or "illegal" in x.text.lower()][:3]
    assert {lay.label("lightning", k) for k in ("frame", "release")} <= {x.addr for x in lines}
    out, _ = _seven(romset_zip, saturn_cue)
    from vrtools.arcade.romset import V60_BOOT
    from vrtools.arcade.weather import layout
    for name in ("lightning objects", "lightning colours", "lightning data"):
        assert not layout.erased(out, layout.block(name)), name
    built, rep = carrier.build(s1, mods)
    from vrtools.arcade.weather import sound
    assert sound.install_board(built) == out                        # the session's set is this build (with its sound board: the join)

    def records(at):
        got = []
        while struct.unpack_from("<I", out.boot, at - V60_BOOT)[0]:
            got.append(struct.unpack_from("<4I", out.boot, at - V60_BOOT))
            at += 16
        return got
    dblk = layout.block("lightning data")
    assert (0x31, dblk.start, lay.data_at("lightning", "whiteout"), 96 * 64) in records(rep["common"])   # one record for every entry
    for e in rep["lists"]:
        mine = [r for r in records(rep["lists"][e]) if r[2] == lay.data_at("lightning", "course")]
        assert len(mine) == 1 and mine[0][0] == 0x31 and dblk.start < mine[0][1] < dblk.start + dblk.size, (e, mine)
    assert rep["stub"][1] <= layout.block("storm stub").size and rep["data_end"] <= carrier.DATA[1]


def _aim_of(rs, lay, lists, entry) -> np.ndarray:
    """The direction table a placement on `entry` reads (in RAM after that entry's load): the image's table (the common list copies
    the whole image at every load), then any of the entry's own copy records that land in it; as degrees off the view, sorted."""
    from vrtools.arcade.weather import layout, lightning as L
    dirs = lay.table("lightning", "dirs")
    n = 12 * 2 * L.NANG
    img = layout.block("storm image").start
    tab = bytearray(rs.data[0x200000 + img + dirs - carrier.IMAGE[0]:][:n])
    at = lists[entry]
    while True:
        flags, src, dst, hw = struct.unpack_from("<4I", rs.boot, at - 0xFC0000)
        if not flags:
            break
        if dirs <= dst < dirs + n:
            bank = flags >> 4
            k = dst - dirs
            tab[k:k + 2 * hw] = rs.data[bank * 0x100000 + src - 0x100000:][:2 * hw]
        at += 16
    c = np.frombuffer(bytes(tab), "<f4").reshape(-1, 3)
    return np.sort(np.degrees(np.arctan2(c[:, 1], c[:, 0])))


def test_the_aim_of_each_course(romset_zip, saturn_cue):
    """Each of the ten courses' placements read the directions of its aim range (LightningTune.aim_for: NANG angles evenly from low
    to high, left and right): Metropolis the street's 2-10 degrees, every other course 12-40; the image keeps the default table and
    Metropolis's own table reaches it by one copy record of its entry's list, after the common list (so the next load of another
    course has the default again)."""
    from tests.test_weather_carrier import _stage1
    from vrtools.arcade.weather import lightning as L
    from vrtools.arcade.weather.tune import Tunes
    s1 = _stage1(romset_zip, saturn_cue)
    built, rep = carrier.build(s1, carrier.default_modules(s1, Tunes()))
    t = Tunes().lightning
    for e in range(10):
        lo, hi = t.aim_for(e)
        angs = [lo + (hi - lo) * k / (L.NANG - 1) for k in range(L.NANG)]
        want = np.sort(np.array([-a for a in angs] + angs))
        got = _aim_of(built, rep["layout"], rep["lists"], e)
        assert np.allclose(got, want, atol=1e-4), (e, got)
        assert (lo, hi) == (STREET_AIM if e == METROPOLIS else (12.0, 40.0))


def test_the_aim_changes_no_other_course(romset_zip, saturn_cue):
    """The street aim on Metropolis changes nothing of any other course: against the same build with no override (the approved aim
    everywhere: 34cdf89's build byte for byte), the program and polygon ROMs, the storm image (code and tables), every course's blob and
    every other entry's copy records are the same; Metropolis's list has one record more (its table into the image's), and the only
    new bank-3 bytes are that table, after the last course blob."""
    from dataclasses import replace
    from tests.test_weather_carrier import _stage1
    from vrtools.arcade.weather import layout
    from vrtools.arcade.weather.tune import Tunes
    s1 = _stage1(romset_zip, saturn_cue)
    new, rn = carrier.build(s1, carrier.default_modules(s1, Tunes()))
    tun = replace(Tunes(), lightning=replace(Tunes().lightning, aim_by_entry=()))
    old, ro = carrier.build(s1, carrier.default_modules(s1, tun))
    assert new.program == old.program and new.polygons == old.polygons
    img = layout.block("storm image")
    assert rn["image"] == ro["image"] and rn["layout"].tables == ro["layout"].tables and rn["layout"].data == ro["layout"].data
    assert new.data[0x200000 + img.start:0x200000 + img.start + img.size] == old.data[0x200000 + img.start:0x200000 + img.start + img.size]

    def recs(rs, at):
        out = []
        while struct.unpack_from("<I", rs.boot, at - 0xFC0000)[0]:
            out.append(struct.unpack_from("<4I", rs.boot, at - 0xFC0000))
            at += 16
        return out
    dirs = rn["layout"].table("lightning", "dirs")
    assert recs(new, rn["common"]) == recs(old, ro["common"])
    for e in range(10):
        a, b = recs(new, rn["lists"][e]), recs(old, ro["lists"][e])
        if e == METROPOLIS:                            # one record more, into the image's direction table; the others as before
            aim = [r for r in a if r[2] == dirs]
            assert len(aim) == 1 and aim[0][3] == 12 * 16 // 2 and [r for r in a if r[2] != dirs] == b
        else:
            assert a == b, e
    stub = layout.block("storm stub")
    diff = [i for i in range(len(new.boot)) if new.boot[i] != old.boot[i]]
    assert diff and all(stub.start <= 0xFC0000 + i < stub.start + stub.size for i in diff)
    ld = layout.block("lightning data")
    ddiff = [i for i in range(len(new.data)) if new.data[i] != old.data[i]]
    mrec = next(r for r in recs(new, rn["lists"][METROPOLIS]) if r[2] == dirs)
    aim_at = 3 * 0x100000 + mrec[1] - 0x100000
    assert ddiff and min(ddiff) >= aim_at and max(ddiff) < aim_at + 192
    last_blob = max(r[1] + 2 * r[3] for e in range(10) for r in recs(old, ro["lists"][e]) if r[2] == ro["layout"].data_at("lightning", "course"))
    assert mrec[1] >= last_blob and 0x200000 + ld.start <= aim_at < 0x200000 + ld.start + ld.size


# ---- the runs -----------------------------------------------------------------------------------------------------------------
def storm_env(lay, wd: Path) -> dict:
    """A lightning run's logs on a storm set laid out as `lay` (a carrier.Layout), RAIN answered: the frame, rate and stale-list
    logs, the storm log pass by pass with the sound's thunder count and the rain's RAIN_WATCH cells, the lightning log
    (`light_env`). Phase 90 (fix round 1c): shared with pack 2's flash gate (tests/test_pack_gates.py)."""
    from vrtools.arcade.weather import rain
    watch = [lay.cell('sound', 'nthunder')] + [rain.cell(lay, n) for n in RAIN_WATCH]
    return {"VR_FRAME_LOG": str(wd / "frames.txt"), "VR_RATE_LOG": str(wd / "rate.txt"), "VR_STALE_LOG": str(wd / "stale_list.txt"),
            "VR_STORM_LOG": str(wd / "storm.txt"), "VR_STORM_RAIN": f"{lay.cell('rain', 'state'):x}", "VR_STORM_FRAMES": "1",
            "VR_RAIN": "1", **light_env(lay, wd), "VR_STORM_WATCH": ",".join(f"{a:x}" for a in watch)}


class LightSession:
    """The lightning's test sets (the stress tune; with the stand-in cover over a stretch; with the dense test pattern) and runs."""

    def __init__(self, storm, base: Path):
        self.storm, self.rate, self.base = storm, storm.rate, base
        self.sets, self.lays, self.runs, self.failed = {}, {}, {}, {}
        self._lock, self._set_lock = threading.Lock(), threading.Lock()

    def modules(self, kind):
        from tests.test_weather_carrier import _stage1
        from vrtools.arcade.weather import lightning, rain, sound
        from vrtools.arcade.weather.tune import LightningTune, RainTune
        s1 = _stage1(self.rate.romset_zip, self.rate.saturn_cue)
        cov = carrier.module_named("cover", s1)        # the real cover (the join; the lightning's stand-in is gone)
        return s1, [cov, lightning.module(s1, LightningTune(interval_s=STRESS), DENSE if kind == "dense" else lightning.PATTERNS,
                                          fault=FAULT, refuse_all=kind == "refused",
                                          measure=kind[4:] if kind.startswith("vis_") else ""), rain.module(s1, RainTune()),
                    sound.module()]                    # the join: the sound's triggers last (the thunders counted: the cell nthunder)

    def build(self, kind) -> tuple[Path, carrier.Layout]:
        """kind: "stress" (the cover, the lightning with the stress tune, the rain, the sound's triggers), "dense" (stress + DENSE only),
        "refused" (stress, every foot cell refused: no placement finds a valid foot), "litkey" (stress, the rain's lit set in
        magenta: v0.4.1's lit streaks counted on the picture)."""
        if kind == "litkey":
            st, lay = self.build("stress")
            with self._set_lock:
                if kind not in self.sets:
                    from tests.test_weather_streaming import KEYS, recolour, tone_addrs
                    self.sets[kind], self.lays[kind] = recolour(st, self.base / kind, {a: KEYS["magenta"] for a in tone_addrs(3)}), lay
                return self.sets[kind], self.lays[kind]
        with self._set_lock:
            if kind not in self.sets:
                from tests.test_tgp_build import _build
                s1, mods = self.modules(kind)
                new, rep = carrier.build(s1, mods)
                (self.base / kind).mkdir(parents=True, exist_ok=True)
                self.sets[kind], self.lays[kind] = _build(self.base / kind, self.rate.romset_zip, new), rep["layout"]
            return self.sets[kind], self.lays[kind]

    def _make(self, key):
        from tests.test_frame_rate import Run
        kind = key[0]
        wd = self.base / "runs" / "_".join(str(k) for k in key)
        wd.mkdir(parents=True, exist_ok=True)
        setkind = {"stress": "stress", "dense": "dense", "end": "stress", "refused": "refused", "svc_mid": "stress",
                   "reset_mid": "stress", "litkey": "litkey"}[kind] if kind != "vis" else f"vis_{key[1]}"
        build, lay = self.build(setkind)
        entry = key[1] if kind in ("stress", "litkey") else METROPOLIS if kind == "vis" else 0
        env = self.rate._env(wd, entry, False)
        env.update(storm_env(lay, wd))
        seconds = STRESS_SECONDS
        if kind == "end":
            env.pop("VR_HOLD_CLOCK", None)
            env.update({"VR_EXTRA_LUA": f"{LUA_DIR / 'clock_out.lua'};{LUA_DIR / 'test_inputs.lua'}", "VR_CLOCK_OUT": str(END_AFTER),
                        "VR_TEST_LOG": str(wd / "test.txt"), "VR_TEST_INPUT": END_INPUT, "VR_STORM_TRACE": "1",
                        "VR_STORM_DUMPS": ",".join(str(1600 + END_AFTER + k) for k in (-2, 60, 120))})
            seconds = END_SECONDS
        elif kind in ("svc_mid", "reset_mid"):        # F3: the TEST menu / a soft reset at a white-out pass (the stress run's)
            env.update({"VR_HOLD_CLOCK": "1", "VR_EXTRA_LUA": str(LUA_DIR / "test_inputs.lua"), "VR_TEST_LOG": str(wd / "test.txt"),
                        "VR_STORM_TRACE": "1"})
            if kind == "svc_mid":
                env.update({"VR_TEST_INPUT": MID_SVC, "VR_STORM_DUMPS": str(MID_EXIT + 900)})
                seconds = (MID_EXIT + 1000) // 57 + 1
            else:
                env.update({"VR_SOFT_RESET": str(MID_RESET), "VR_STORM_DUMPS": "900"})
                seconds = (MID_RESET + 1200) // 57 + 1
        elif kind == "vis":                           # task 8: the bolt's key pixels on every strike frame (bolt_pixels.lua)
            env.update({"VR_HOLD_CLOCK": "1", "VR_EXTRA_LUA": str(LUA_DIR / "bolt_pixels.lua"), "VR_PIX_LOG": str(wd / "pix.txt"),
                        "VR_PIX_STATE": f"{lay.cell('lightning', 'state'):x}", "VR_PIX_SEQ": f"{lay.cell('lightning', 'strike_seq'):x}"})
            seconds = VIS_SECONDS
        else:
            env["VR_HOLD_CLOCK"] = "1"
            if kind == "refused":
                seconds = REFUSED_SECONDS
            if kind in ("stress", "litkey"):            # v0.4.1: the picture (its luminance; on litkey also the lit streaks' key)
                env.update({"VR_EXTRA_LUA": str(LUA_DIR / "rain_pixels.lua"), "VR_RPIX_LOG": str(wd / "rpix.txt"),
                            "VR_RPIX_KEYS": "1" if kind == "litkey" else "0"})
        run_mame(LUA_DIR / "autoplay.lua", seconds, wd, build, env=env, timeout=5400)
        r = Run(wd, finish=kind not in ("end", "svc_mid", "reset_mid"))
        r.storm = parse_storm_log(wd / "storm.txt")
        r.light, r.gaps = parse_light_log(wd / "light.txt")
        r.entry = entry
        if (wd / "rpix.txt").exists():
            from vrtools.mame.runner import parse_rain_pixels
            r.pix = parse_rain_pixels(wd / "rpix.txt")
        r.rain = {f: dict(zip(RAIN_WATCH, v[1:])) for f, v in r.storm.watches.items() if len(v) > len(RAIN_WATCH)}
        return r

    def prefetch(self, keys):
        keys = [k for k in dict.fromkeys(keys) if k not in self.runs]

        def make(k):
            try:
                r = self._make(k)
            except Exception as e:                     # noqa: BLE001 (raised again by `run`)
                with self._lock:
                    self.failed[k] = e
                return
            with self._lock:
                self.runs[k] = r
        with ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(make, keys))

    def run(self, *key):
        if key in self.failed:
            raise AssertionError(f"the run {key} failed: {self.failed[key]!r}") from self.failed[key]
        if key not in self.runs:
            self.runs[key] = self._make(key)
        return self.runs[key]


def light_keys(items) -> list:
    need = {"test_the_flash_rule_under_stress": lambda p: [("stress", p["entry"])],
            "test_sampled_strikes_are_beside_the_course": lambda p: [("stress", p["entry"])],
            "test_the_white_out_only_on_the_first_stroke": lambda p: [("stress", e) for e in range(10)],
            "test_the_rule_cuts_a_denser_pattern": lambda p: [("dense",)],
            "test_under_cover_no_bolt_no_white_out_the_sky_flash_kept": lambda p: [("stress", e) for e in COVER_ENTRIES],
            "test_a_race_ending_mid_strike_ends_clean": lambda p: [("end",)],
            "test_no_strike_where_no_foot_is_valid": lambda p: [("refused",)],
            "test_the_test_menu_in_the_middle_of_a_strike": lambda p: [("svc_mid",), ("stress", 0)],
            "test_a_soft_reset_in_the_middle_of_a_strike": lambda p: [("reset_mid",), ("stress", 0)],
            "test_the_bolt_shows_on_metropolis": lambda p: [("vis", "key"), ("vis", "twin")],
            "test_the_picture_holds_the_flash_rule_under_stress": lambda p: [("stress", p["entry"])],
            "test_no_lit_rain_under_cover": lambda p: [("stress", e) for e in COVER_ENTRIES],
            "test_the_lit_streaks_share_of_a_flash_pass": lambda p: [("litkey", p["entry"])],
            "test_the_lit_rain_on_the_stress_runs": lambda p: [("stress", p["entry"])]}
    keys = []
    for i in items:
        name = getattr(i, "originalname", None) or getattr(i, "name", "")
        p = getattr(getattr(i, "callspec", None), "params", {})
        if name in need:
            keys += need[name](p)
    return keys


_SESSIONS: dict = {}


@pytest.fixture
def light_runs(request, storm_runs, tmp_path_factory) -> LightSession:  # noqa: F811 (the fixture)
    key = str(storm_runs.rate.romset_zip)
    if key not in _SESSIONS:
        s = LightSession(storm_runs, tmp_path_factory.mktemp("light"))
        s.prefetch(light_keys(request.session.items))
        _SESSIONS[key] = s
    return _SESSIONS[key]


def _rate_gates(r, name):
    """The rate gates on a lightning run: no stale display list, every pass at most RAIN_BUSY_MAX_MS, the overrun counter still, the
    render rate 28-29, no list skipped; the split bound after the count's move on every storm pass (`post_move_over`); no unit
    of the lightning's longer than UNIT_MAX_US between two guard tests (its last test to the next one, the rain's first, included)."""
    from tests.test_frame_rate import _stale_result
    stretch = r.stretch()
    misses = arcade_rate_misses(r.frames, r.rate, r.start, r.end, rate_from=r.green)
    stale, stale_text = _stale_result(r)
    over = [(f.frame, f.busy_us) for f in stretch if f.busy_us > RAIN_BUSY_MAX_MS * 1000]
    assert misses == [] and stale == [] and over == [], (name, misses[:5], stale_text, over[:5])
    assert sum(f.skipped for f in stretch) == 0
    assert post_move_over(r) == [], (name, post_move_over(r)[:3])
    long = sorted(((f, g.light_us) for f, g in r.gaps.items() if g.light_us > carrier.UNIT_MAX_US), key=lambda x: -x[1])
    assert long == [], (name, "a lightning unit over UNIT_MAX_US", long[:5])
    return stretch


def _summary(light_runs, name, r, extra=""):
    st = r.light[-1].s if r.light else {}
    stretch = r.stretch()
    with open(light_runs.base / "light_summary.txt", "a") as out:
        out.write(f"{name}: passes {len(stretch)}, busiest {max(f.busy_us for f in stretch) / 1000:.2f} ms, strikes {st.get('NSTRIKE')}, "
                  f"onsets {st.get('NONSET')}, blocked {st.get('NBLOCK')}, bolt passes {st.get('NBOLT')}, trimmed {st.get('NTRIMB')}, "
                  f"behind {st.get('NZSKIP')}, white-outs {st.get('NWASH')} (late {st.get('NLATEW')}, cut {st.get('NPART')}), "
                  f"placed in sight {st.get('NPLACED')} hidden {st.get('NHIDDEN')} fallback {st.get('NFALL')}, placement passes cut "
                  f"{st.get('NLATEP')}, longest lightning unit {max((g.light_us for g in r.gaps.values()), default=0):.0f} us, longest "
                  f"lightning-to-rain {max((g.to_rain_us for g in r.gaps.values()), default=0):.0f} us, longest unit "
                  f"{max((g.gap_us for g in r.gaps.values()), default=0):.0f} us{extra}\n")


STRESS_ENTRIES = [pytest.param(e, id=NAMES[e]) for e in range(10)]


@pytest.mark.parametrize("entry", STRESS_ENTRIES)
def test_the_flash_rule_under_stress(light_runs, entry):
    """The stress build (a strike 0.4-1.2 s after the last ends, the test-only tune) on each course, RAIN, STRESS_SECONDS: the flash
    onsets SHOWN (read from palette RAM and the colour RAM at each pass's end, not from the module's counters) never more than three
    within WINDOW_FRAMES video frames (more than a second); many strikes ran, each with its onsets; the rate gates hold under it;
    and the sound's cells follow the strikes (`interface_errors`: strike_seq +1 on each strike's first running pass and on no other,
    strike_band by the distance on that pass)."""
    r = light_runs.run("stress", entry)
    flash_rule(r, light_runs.rate.out, entry, NAMES[entry],
               lambda on: _summary(light_runs, f"stress {NAMES[entry]}", r, f", onsets seen {len(on)}"))


def flash_rule(r, rs, entry: int, name: str, summary=None) -> list[int]:
    """test_the_flash_rule_under_stress's gates on a stress run `r` of entry `entry` of the set `rs` (a RomSet): the rate gates
    (`_rate_gates`); at least 20 strikes, each with its onsets (the onsets seen at least 2 a strike, less 2); never more than three
    onsets within WINDOW_FRAMES (`crowded`); the sound's cells following the strikes (`interface_errors`, the strike count, the
    bands). `summary(onsets)` is called before the assertions on the onsets. Returns the onsets' frames. Phase 90 (fix round 1c):
    shared with pack 2's flash gate (tests/test_pack_gates.py)."""
    _rate_gates(r, name)
    on = onsets(observed_flash(r.light, rs, entry, r.storm))
    last = r.light[-1].s
    if summary is not None:
        summary(on)
    assert last["NSTRIKE"] >= 20 and len(on) >= 2 * last["NSTRIKE"] - 2, (last["NSTRIKE"], len(on))
    assert crowded(on) == [], crowded(on)[:3]
    assert interface_errors(r.light) == [], interface_errors(r.light)[:5]
    assert r.light[-1].seq == last["NSTRIKE"] and {p.band for p in r.light if p.seq} <= {1, 2, 3}
    return on


def picture_onsets(pix) -> list[int]:
    """The picture's flash onsets in rain_pixels.lua's lines: a rise of the mean relative luminance by PIC_STEP over its lowest of
    the last PIC_BACK frames, counted once until it has fallen PIC_STEP below its peak (a rise after a fall, the rule's definition);
    after a fall the lowest is taken from the frames since that fall only (a white-out falling to a bright sky is one flash, as the
    rule counts the lightning's levels 4 then 2; gate1 counted its next frame again on Surfers Road). The frames out of the race,
    which the logger skips, break the sequence."""
    out, high, peak, recent, last = [], False, 0.0, [], None
    for p in pix:
        if last is not None and p.frame != last + 1:
            high, recent = False, []
        last = p.frame
        if not high:
            if recent and p.luminance - min(recent[-PIC_BACK:]) >= PIC_STEP:
                out.append(p.frame)
                high, peak = True, p.luminance
        else:
            peak = max(peak, p.luminance)
            if peak - p.luminance >= PIC_STEP:
                high, recent = False, []
        recent.append(p.luminance)
    return out


def lit_frames(r) -> set:
    """The video frames whose picture can hold a lit rain: each pass with the rain lit (WCUR over 1) or in its afterglow, and the
    PIC_MATCH frames after it (the list a pass builds is shown on the frames after)."""
    from vrtools.arcade.weather import rain  # noqa: F401
    lit = {f for f, c in r.rain.items() if fbits(c["WCUR"]) != 1.0 or c["AGLOW"]}
    return {f + d for f in lit for d in range(PIC_MATCH + 2)}


@pytest.mark.parametrize("entry", STRESS_ENTRIES)
def test_the_lit_rain_on_the_stress_runs(light_runs, entry):
    """v0.4.1, the lit rain pass by pass on each course's stress run (a strike every 0.4-1.2 s; `lit_errors` of
    test_weather_streaming.py): lit and three times as wide exactly on the passes the lightning's flash is up in the open, the
    afterglow's length after it, nothing between strikes, nothing under cover. The flash and afterglow pass counts per course go to
    the summary (the findings)."""
    from tests.test_weather_streaming import lit_errors
    r = light_runs.run("stress", entry)
    flashes, glow, under, errs = lit_errors(r.rain, r.light, r.storm)
    _summary(light_runs, f"lit passes {NAMES[entry]}", r, f", flash passes {flashes}, afterglow passes {glow}, under cover {under}, "
                                                          f"errors {len(errs)}")
    assert flashes > 20 and glow > 50 and errs == [], (NAMES[entry], flashes, glow, errs[:5])


@pytest.mark.parametrize("entry", STRESS_ENTRIES)
def test_the_picture_holds_the_flash_rule_under_stress(light_runs, entry):
    """v0.4.1: the flash rule read from the picture itself, the lit rain in it (the stress runs of all ten courses): no picture flash
    onset (`picture_onsets`) on a frame the rain is lit or glowing that is not one of the lightning's own onsets (within PIC_MATCH
    frames of `observed_flash`'s): the lit rain adds no flash onset; and the storm's picture onsets (the lightning's own and any on a
    lit frame) and the scene's own brightness changes (gate1: Surfers Road's at 4942, no strike and no lit rain on it) together never
    more than three within WINDOW_FRAMES (the review's fix round 1: every picture onset counts). The lit streaks' share of the
    picture on a flash frame is 0.058 to 0.109 by course (LIT_SHARE_MAX; over PIC_STEP on the two Surfers courses only), so this
    measure would mostly not see an onset of the lit streaks alone: it is NOT the evidence that the lit rain adds none. That evidence
    is the pass-by-pass test, test_the_lit_rain_on_the_stress_runs: the rain is lit only on the passes the lightning's own flash is
    up, on all ten courses."""
    r = light_runs.run("stress", entry)
    pic = picture_onsets(r.pix)
    light = onsets(observed_flash(r.light, light_runs.rate.out, entry, r.storm))
    lit = lit_frames(r)
    near = lambda f: any(abs(f - g) <= PIC_MATCH + 2 for g in light)
    added = [f for f in pic if f in lit and not near(f)]
    storm = [f for f in pic if f in lit or near(f)]
    scene = [f for f in pic if f not in storm]
    lum = [p.luminance for p in r.pix]
    _summary(light_runs, f"picture {NAMES[entry]}", r, f", picture onsets {len(pic)} (the storm's {len(storm)}, the scene's "
                                                       f"{len(scene)} at {scene}), the lightning's {len(light)}, on lit frames not "
                                                       f"the lightning's {len(added)}, luminance {min(lum):.3f}-{max(lum):.3f}")
    assert len(r.pix) > 3000 and crowded(pic) == [] and added == [], (crowded(pic)[:3], added[:5], "the scene's onsets", scene)


def test_no_lit_rain_under_cover(light_runs):
    """v0.4.1 (design point 6: "nothing under cover"): on the stress runs through Metropolis's and Alpine's tunnels and the roof by
    the pits, no pass with the cover's under_cover set has the rain lit or glowing (WCUR 1, AGLOW 0, the near set); in the open the
    lit rain shows."""
    from vrtools.arcade.weather import layout, rain
    near = rain.tex(layout.block("rain tones").start)
    under = lit_open = 0
    for e in COVER_ENTRIES:
        r = light_runs.run("stress", e)
        early, last = set(), 0                         # passes the guard stopped before the rain's choices: its last pass's kept
        for sp in r.storm.passes:
            if sp.late > last and sp.drawn == 0:
                early.add(sp.frame)
            last = sp.late
        for p in r.light:
            c = r.rain.get(p.frame)
            if c is None or p.frame in early:
                continue
            if p.cover == 1 and c["PN"]:
                under += 1
                assert fbits(c["WCUR"]) == 1.0 and c["AGLOW"] == 0 and c["PN"] == near, (NAMES[e], p.frame, c)
            elif fbits(c["WCUR"]) != 1.0:
                lit_open += 1
    assert under > 50 and lit_open > 20, (under, lit_open)


@pytest.mark.parametrize("entry", STRESS_ENTRIES)
def test_the_lit_streaks_share_of_a_flash_pass(light_runs, entry):
    """v0.4.1: the lit streaks' share of the picture (each course's stress run with the rain's lit set in magenta) on the frames of a
    flash pass (the scene's own magenta not taken off: an upper bound): at most LIT_SHARE_MAX (reported with its mean); on the
    other frames no more than the scene's own (SCENE_KEY_MAX; nothing between strikes is test_the_lit_rain_on_the_stress_runs'
    pass by pass). Under PIC_STEP: the picture test cannot see an onset of the lit streaks alone."""
    r = light_runs.run("litkey", entry)
    from tests.test_weather_streaming import lit_errors
    assert lit_errors(r.rain, r.light, r.storm)[3] == [], (NAMES[entry], "a lit pass outside the lightning's flash on the lit-key run")
    lit = lit_frames(r)
    area = 496 * 384
    on = [sum(p.magenta) / area for p in r.pix if p.frame in lit]
    off = [sum(p.magenta) for p in r.pix if p.frame not in lit]
    _summary(light_runs, f"lit streaks {NAMES[entry]}", r, f", flash frames {len(on)}, share max {max(on, default=0):.4f} mean "
                                           f"{statistics.mean(on) if on else 0:.4f}, pixels on other frames max {max(off, default=0)}")
    assert len(on) > 100 and max(on) <= LIT_SHARE_MAX and max(off) <= SCENE_KEY_MAX, (len(on), max(on, default=0), max(off, default=0))


def test_the_rule_cuts_a_denser_pattern(light_runs):
    """A test-only pattern of five onsets in 13 logic frames (out/p60ruletest's): every strike is cut by the rule (at its fourth onset,
    or sooner when the last strike's onsets are still within the window: the rule in the code, whatever the pattern data), and the
    onsets shown are never more than three within WINDOW_FRAMES."""
    r = light_runs.run("dense")
    _rate_gates(r, "dense")
    on = onsets(observed_flash(r.light, light_runs.rate.out, 0, r.storm))
    last = r.light[-1].s
    _summary(light_runs, "dense", r, f", onsets seen {len(on)}")
    assert last["NSTRIKE"] >= 20 and last["NBLOCK"] >= last["NSTRIKE"] - 2, (last["NSTRIKE"], last["NBLOCK"])
    assert crowded(on) == [] and len(on) > last["NSTRIKE"], (crowded(on)[:3], len(on))


def test_the_white_out_only_on_the_first_stroke(light_runs):
    """Over the ten stress runs: the colour RAM is washed (the white-out) only on the pass that applies level 4 or while its restore
    runs on the next pass, level 4 comes once a strike in its first stroke, and most first strokes do show it (the guard leaves
    out only the ones whose first unit found the pass late; a strike whose white-out pass is under cover shows none by design: spec
    5.4, the cover's rule, `test_under_cover_no_bolt_no_white_out_the_sky_flash_kept`; not counted here since the join's real
    cover, task 8)."""
    for e in range(10):
        r = light_runs.run("stress", e)
        fl = dict(observed_flash(r.light, light_runs.rate.out, e, r.storm))
        prev = None
        for p in r.light:
            if fl[p.frame] == 4:
                assert p.s["LEVEL"] == 4 or (prev is not None and prev.s["LEVEL"] == 4), (e, p.frame)
            prev = p
        shown, covered = 0, 0
        for st in strikes_of(r.light):
            levels = [p.s["LEVEL"] for p in st]
            if 4 in levels:
                k = levels.index(4)
                assert levels.count(4) == 1 and 0 not in levels[:k], (e, levels)
                if st[k].cover:
                    covered += 1                       # under cover: no white-out, by design
                    assert not any(fl[p.frame] == 4 for p in st), (e, st[k].frame)
                    continue
                shown += any(fl[p.frame] == 4 for p in st)
        assert shown >= 0.8 * (len(strikes_of(r.light)) - covered), (e, shown, covered, len(strikes_of(r.light)))


def test_under_cover_no_bolt_no_white_out_the_sky_flash_kept(light_runs):
    """Under the real cover (the join: the stress runs of Metropolis and Alpine, COVER_ENTRIES, through their flagged tunnels and
    the roof by the pits; before the join a stand-in cover said 1 over a stretch of Big Forest): on every pass the cover's byte
    `under_cover` is 1 no bolt is drawn (no record of the lightning's) and the colour RAM is not washed, while the sky flashes there;
    in the open bolts and white-outs are drawn. A strike begun under cover is a strike for the sound (strike_seq and strike_band set
    as anywhere: spec 5.4, "Rain sound fades out under cover and back (5.6); thunder is heard the same."): the sound's triggers send
    one thunder word for every strike, those begun under cover included (the cell nthunder against the strikes)."""
    under, open_, begun, shown_under, bolts_open, wash_open = [], [], [], 0, 0, 0
    lasts = []
    for e in COVER_ENTRIES:
        r = light_runs.run("stress", e)
        _rate_gates(r, f"cover {NAMES[e]}")
        fl = dict(observed_flash(r.light, light_runs.rate.out, e, r.storm))
        u = [p for p in r.light if p.cover == 1 and p.s["PHASE"] == 3]
        o = [p for p in r.light if p.cover == 0 and p.s["PHASE"] == 3]
        assert all(p.s["REC"] == 0 for p in u) and not [p.frame for p in u if fl[p.frame] == 4], NAMES[e]
        under += u
        open_ += o
        shown_under += sum(1 for p in u if fl[p.frame] in (1, 2, 3))
        bolts_open += sum(1 for p in o if p.s["REC"] > 0)
        wash_open += sum(1 for p in o if fl[p.frame] == 4)
        b = [st[0] for st in strikes_of(r.light) if st[0].cover == 1]  # strikes whose timeline began under cover
        begun += b
        last = r.light[-1].s
        lasts.append(last)
        _summary(light_runs, f"cover {NAMES[e]}", r, f", under cover {len(u)} strike passes (bolts skipped {last['NCOVB']}, white-outs "
                                                      f"{last['NCOVW']}), {len(b)} strikes begun under cover")
        assert interface_errors(r.light) == [], (NAMES[e], interface_errors(r.light)[:5])   # each strike thunders (spec 5.4)
    assert len(under) > 50 and len(open_) > 100, (len(under), len(open_))
    assert shown_under > 10 and bolts_open > 100 and wash_open > 3, (shown_under, bolts_open, wash_open)
    assert sum(x["NCOVB"] for x in lasts) > 0 and sum(x["NCOVW"] for x in lasts) > 0 and begun, (len(begun),)
    for e, last in zip(COVER_ENTRIES, lasts):              # every strike thundered once, those begun under cover included (the
        thunders = max(light_runs.run("stress", e).storm.watch.values())     # sound's triggers: one word a strike_seq change)
        assert thunders == last["NSTRIKE"], (NAMES[e], thunders, last["NSTRIKE"])


@pytest.mark.parametrize("entry", STRESS_ENTRIES)
def test_sampled_strikes_are_beside_the_course(light_runs, entry):
    """Every strike of the stress run on each course (tens a course): its foot ROAD_CLEAR - 12 units or more from the centreline
    (the grid's cells refuse the road; a foot lies anywhere in its 16-unit cell), off the road, every strike (a placement that finds
    no valid foot strikes nowhere: test_no_strike_where_no_foot_is_valid); its distance in the tune's 300-800 units; the bolt drawn
    in front of the camera (view depth BOLT_ZMIN or more) on most of its passes; the objects sorted behind nearer scenery
    (test_the_bolt_objects: every record ZMAX)."""
    from vrtools.arcade.course import course_entry_at, road_lines
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.weather import lightning as L
    r = light_runs.run("stress", entry)
    out = light_runs.rate.out
    d = decode_directory(out)[entry]
    centre = np.array([(q.x, q.z) for q in road_lines(out, course_entry_at(out, d.bank, window_base=d.header_base))[0]])
    strikes = strikes_of(r.light)
    last = r.light[-1].s
    assert len(strikes) >= 20, len(strikes)
    near = []
    for st in strikes:
        p = st[0]
        x, z, dist = fbits(p.s["WX"]), fbits(p.s["WZ"]), fbits(p.s["DV"])
        assert 300.0 <= dist <= 800.0 and fbits(p.s["BESTH"]) >= 0, (entry, p.frame, dist, fbits(p.s["BESTH"]))
        q = np.array([x, z])
        dmin = min(np.hypot(*(q - a - np.clip(np.dot(q - a, b - a) / (np.dot(b - a, b - a) or 1.0), 0, 1) * (b - a)))
                   for a, b in zip(centre, np.roll(centre, -1, 0)))
        if dmin < L.ROAD_CLEAR - 12:
            near.append((p.frame, round(float(dmin), 1)))
    assert near == [], (entry, near[:5])
    drawn = sum(1 for p in r.light if p.s["REC"] > 0)
    shown = sum(1 for p in r.light if p.s["PHASE"] == 3 and p.s["LEVEL"] != 0 and p.cover == 0)
    assert drawn >= 0.7 * shown, (entry, drawn, shown)


def test_a_race_ending_mid_strike_ends_clean(light_runs):
    """Review Focus 2 for the lightning: the stress build, Big Forest, the race ended by time over END_AFTER frames after its start
    while a strike shows (its timeline running, a flash sky or the white-out up); a coin and START in the results. On the passes
    after the race mode the strike has ended and the sky is the grey again, the colour RAM the overcast table (the rain goes on
    through the results); at the release (the attract's opening) the colour RAM is the boot's table and the backdrop the course's
    own; nothing of the storm runs after it (no write into its RAM), the carrier IDLE."""
    from vrtools.arcade.weather import rain
    r = light_runs.run("end")
    out = light_runs.rate.out
    modes = [(f, md) for f, md, *_ in r.storm.frames]
    raced = min(f for f, md in modes if md == 0x14)
    race_end = next(f for f, md in modes if f > raced and md != 0x14)
    before = [p for p in r.light if p.frame < race_end]
    mid = before[-1]
    assert mid.s["PHASE"] == 3 and mid.s["PCUR"] > 0 and mid.s["WROWS"] > 0, mid               # a flash sky and the white-out up
    after = [p for p in r.light if race_end <= p.frame][:40]
    settled = [p for p in after[3:] if p.s["PHASE"] == 0 and p.s["PCUR"] == 0 and p.s["WROWS"] == 0]
    assert len(settled) == len(after[3:]) > 20, [(p.frame, p.s["PHASE"], p.s["PCUR"], p.s["WROWS"]) for p in after[:6]]
    T0, TB = rain.overcast_table().reshape(96, 64).tolist(), rain.boot_table().reshape(96, 64).tolist()
    _, _, n, own = rain.course_sky(out, 0)
    grey = rain.grey_sky(own, False)
    later = r.storm.dumps[1600 + END_AFTER + 120]
    assert np.array(later["X"]).reshape(96, 64).tolist() == T0 and later["P"][:n] == grey
    rel = next(p for p in r.storm.passes if p.frame > race_end and p.state == 0)
    dump = r.storm.dumps[rel.frame + 2]
    assert np.array(dump["X"]).reshape(96, 64).tolist() == TB and dump["P"][:n] == own
    assert [t for t in r.storm.traces if t[0] > rel.frame] == [] and all(p.state == 0 for p in r.storm.passes if p.frame >= rel.frame)
    _summary(light_runs, "end", r, f", time over at {race_end} mid-strike (pass {mid.frame}: level {mid.s['LEVEL']}, sky {mid.s['PCUR']}, "
                                   f"rows {mid.s['WROWS']}), released at {rel.frame}")


@pytest.mark.parametrize("entry,reverse", RACES)
def test_strikes_in_the_rain_matrix(storm_runs, entry, reverse):
    """The RAIN race matrix's runs (tests/test_weather_rain.py, the normal build: a strike every 20-40 s) carry the lightning's log:
    strikes happened (two or more: the race runs about 116 s of the 150, the first strike 20-40 s after the green), bolts were
    drawn, the onsets shown never more than three within WINDOW_FRAMES, and no unit of the lightning's longer than UNIT_MAX_US
    between two guard tests (with test_rain_holds_the_rate's gates on the same runs: the cap, no stale list, the bound after the
    count's move)."""
    r = storm_runs.run("rain", entry, reverse)
    light, gaps = parse_light_log(r.wd / "light.txt")
    last = light[-1].s
    on = onsets(observed_flash(light, storm_runs.rate.out, entry, r.storm))
    with open(storm_runs.base / "rain_summary.txt", "a") as out:
        out.write(f"lightning {_id(entry, reverse)}: strikes {last['NSTRIKE']} (bands {sorted(set(p.band for p in light if p.seq))}), "
                  f"onsets seen {len(on)}, bolt passes {last['NBOLT']} trimmed {last['NTRIMB']}, white-outs {last['NWASH']} (late "
                  f"{last['NLATEW']}, cut {last['NPART']}), placement passes cut {last['NLATEP']}, longest lightning unit "
                  f"{max((g.light_us for g in gaps.values()), default=0):.0f} us, lightning-to-rain "
                  f"{max((g.to_rain_us for g in gaps.values()), default=0):.0f} us\n")
    assert last["NSTRIKE"] >= 2 and light[-1].seq == last["NSTRIKE"] and last["NBOLT"] > 30, (last["NSTRIKE"], last["NBOLT"])
    assert crowded(on) == [] and interface_errors(light) == [], interface_errors(light)[:5]
    long = [(f, g.light_us) for f, g in gaps.items() if g.light_us > carrier.UNIT_MAX_US]
    assert long == [], long[:5]
    anyl = [(f, g.gap_us, hex(g.pc)) for f, g in gaps.items() if g.gap_us > carrier.UNIT_MAX_US]   # W4: any module's unit
    assert anyl == [], anyl[:5]


def test_no_strike_where_no_foot_is_valid(light_runs):
    """F1 (fix round 1): a test build whose every foot cell is refused (the stress tune, Big Forest): every placement ends without a
    valid foot and strikes nowhere (the prototype struck on the player's ground at its registers' place: on the road); counted
    (NFALL), no timeline, no bolt, no flash, and the sound's cells untouched (strike_seq and strike_band 0); the next strike is
    scheduled as after any other."""
    r = light_runs.run("refused")
    last = r.light[-1].s
    fl = observed_flash(r.light, light_runs.rate.out, 0, r.storm)
    struck = [p.frame for p in r.light if p.s["PHASE"] in (2, 3) or p.s["REC"] > 0]
    _summary(light_runs, "refused", r, f", placements without a foot {last['NFALL']}")
    assert last["NFALL"] >= 10 and last["NSTRIKE"] == 0, (last["NFALL"], last["NSTRIKE"], struck[:5])
    assert struck == [] and {f for _, f in fl if _ > r.start} == {0}, (struck[:5], sorted({f for _, f in fl}))
    assert {(p.seq, p.band) for p in r.light} == {(0, 0)} and interface_errors(r.light) == []


def _mid_strike(light_runs):
    """The stress run on Big Forest at MID_FRAME: its pass there shows the white-out and a flash sky (the TEST and reset runs are
    the same race up to their input: the same set, the same autopilot)."""
    ref = light_runs.run("stress", 0)
    p = next(q for q in ref.light if q.frame >= MID_FRAME)
    assert p.s["PHASE"] == 3 and p.s["PCUR"] > 0 and p.s["WROWS"] > 0, (p.frame, p.s["PHASE"], p.s["PCUR"], p.s["WROWS"])
    return p


def test_the_test_menu_in_the_middle_of_a_strike(light_runs):
    """F3: the TEST switch at a white-out pass of a strike in a RAIN race (the stress build, Big Forest), the menu's MEMORY TEST run,
    escaped, EXIT: the race up to the press is the stress run's, the last pass before the menu left the white-out and a flash sky
    up; the machine runs on, reboots, plays the attract; from the reboot the storm is idle, SBR the boot's, nothing of the storm
    written; the colour RAM is the boot's table (the white-out gone with the reboot)."""
    from tests.test_weather_carrier import SBR_BOOT, _clean_after, _mode_changes
    from vrtools.arcade.weather import rain
    ref = _mid_strike(light_runs)
    r = light_runs.run("svc_mid")
    last = [p for p in r.light if p.frame <= ref.frame + 2][-1]
    assert (last.frame, last.s["WROWS"], last.s["PCUR"]) == (ref.frame, ref.s["WROWS"], ref.s["PCUR"]), (last.frame, ref.frame)
    reboot = next(f for f, mode in _mode_changes(r.storm.frames, MID_EXIT) if mode == 0)
    assert {m for _, m in _mode_changes(r.storm.frames, reboot)} >= {0x02, 0x03}
    assert all(x[4] == SBR_BOOT for x in r.storm.frames)
    _clean_after(r, reboot + 4)
    assert np.array(r.storm.dumps[MID_EXIT + 900]["X"]).reshape(96, 64).tolist() == rain.boot_table().reshape(96, 64).tolist()


def test_a_soft_reset_in_the_middle_of_a_strike(light_runs):
    """F3: MAME's soft reset at a white-out pass's frame end (the stress build, Big Forest; the race up to it the stress run's): as
    the rain's standing test reads it (the new logger's frames from 1 again), the storm's state still in RAM at the reset's first
    frame end, cleared by the boot by the fourth, idle and SBR the boot's from then until a new race's load; the attract plays; the
    colour RAM is the boot's table 900 frames on."""
    from tests.test_weather_carrier import SBR_BOOT, _mode_changes
    from vrtools.arcade.weather import rain
    _mid_strike(light_runs)
    r = light_runs.run("reset_mid")
    assert [l for l in open(r.wd / "test.txt") if l.startswith("R ")] == [f"R {MID_RESET}\n"]
    fr = [x for x in r.storm.frames if x[0] < MID_RESET]
    assert fr[0][0] == 1 and fr[0][2] == 2, fr[:2]
    cleared = next(x for x in fr if x[2] == 0)
    load = next((x[0] for x in fr if x[1] == 0x11), 1 << 30)
    assert cleared[0] <= 4 and all(x[2] == 0 and x[3] == 0 and x[4] == SBR_BOOT for x in fr if cleared[0] <= x[0] < load)
    assert {m for _, m in _mode_changes(fr, cleared[0]) if _ < load} >= {0x02, 0x03}
    assert np.array(r.storm.dumps[900]["X"]).reshape(96, 64).tolist() == rain.boot_table().reshape(96, 64).tolist()


def test_a_course_blob_never_overlaps_its_grids():
    """M5 (fix round 1): a course's three flash skies must fit FLASH_ROOM (the grids are read at FLASH + FLASH_ROOM): more is
    refused, naming it; a fitting blob puts the grids at FLASH_ROOM."""
    from vrtools.arcade.weather import lightning as L
    assert L.course_blob(b"\x01" * 960, b"grid")[L.FLASH_ROOM:] == b"grid"
    with pytest.raises(PatchError, match="FLASH_ROOM"):
        L.course_blob(b"\x01" * (L.FLASH_ROOM + 2), b"grid")


def bolt_shares(key_log: Path, twin_log: Path) -> tuple[list, bool]:
    """Per strike (strike_seq 1..), the share of its bolt the player sees: its key pixels over the twin's (the same bolt drawn in
    front of all scenery), summed over the strike's frames but the white-out's (level 4: the colour RAM washes the key colour);
    None for a strike whose twin shows under 150 pixels (off the screen or behind the HUD). And whether the two runs stayed in
    lockstep (every frame's strike, phase and level the same)."""
    def read(p):
        return {int(a[1]): tuple(map(int, a[2:6])) for a in (row.split() for row in open(p)) if a and a[0] == "P"}
    K, T = read(key_log), read(twin_log)
    lock = set(K) == set(T) and all(K[f][:3] == T[f][:3] for f in K)
    per: dict = {}
    for f, (seq, _, lvl, n) in K.items():
        if seq >= 1 and lvl != 4:
            k, t = per.get(seq, (0, 0))
            per[seq] = (k + n, t + T[f][3])
    return [k / t if t >= 150 else None for _, (k, t) in sorted(per.items())], lock


def test_the_bolt_shows_on_metropolis(light_runs):
    """Task 8 (the owner, spike 85: "i think one issue on metropolis, is the thinder get hidden by the building"): on Metropolis
    normal (the stress tune, VIS_SECONDS of race) enough of the bolt shows. Measured as spike 85 did: two builds with the same code
    and timing (lightning.module(measure="key" / "twin")): the bolt in one key colour, and the twin whose bolt matrix is scaled about
    the camera (its foot at view z TWIN_K: the same picture, in front of every scenery polygon); a strike's share is its key pixels
    over the twin's (bolt_pixels.lua, `bolt_shares`). At least VIS_CLEAR_MIN of the strikes show half their bolt or more and the
    median strike shows VIS_MEDIAN_MIN or more: below the street aim's figures and above the old aim's (the test fails if the aim
    goes back to 12-40). The figures are single samples of a deterministic run: any change of the main CPU's timing (a module's
    code, the guard's units) reshuffles which strikes happen where. The clear share is the bound that separates the two aims in
    every build measured (23 % -> 48 % here, 27 % -> 43 % in spike 85's build); the median less so (spike 85's build had the old
    aim's median at 0.34). When this trips after such a change: re-measure both aims (the old with aim_by_entry=()) and re-pin
    between them, naming the cause."""
    import statistics
    k, t = light_runs.run("vis", "key"), light_runs.run("vis", "twin")
    shares, lock = bolt_shares(k.wd / "pix.txt", t.wd / "pix.txt")
    got = [x for x in shares if x is not None]
    clear = sum(1 for x in got if x >= 0.5) / max(1, len(got))
    med = statistics.median(got) if got else 0.0
    with open(light_runs.base / "light_summary.txt", "a") as out:
        out.write(f"visibility, Metropolis normal: strikes {len(shares)}, measured {len(got)}, clear {clear:.0%}, under 10 % "
                  f"{sum(1 for x in got if x < 0.1) / max(1, len(got)):.0%}, median {med:.2f}\n")
    assert lock and len(got) >= VIS_MIN_STRIKES, (lock, len(got))
    assert clear >= VIS_CLEAR_MIN and med >= VIS_MEDIAN_MIN, (round(clear, 3), round(med, 3), len(got))
