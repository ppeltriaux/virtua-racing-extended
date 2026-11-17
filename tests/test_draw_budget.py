"""Phase 28: the frame's draw budget (`vrtools/arcade/budget.py`): its two sites on the original set, the patch's bytes and refusals,
and the ten-course build's values (FRAME_BUDGET 10 500, LINK_FRAME_BUDGET 10 000: Pascal's "Ok" to the session lead's recommendation,
docs/spike/2026-11-phase28-draw-budget-findings.md §3).

The game's frame record budget is the long word 0x5011b0: the object-list walker (0xff848a, 0xff84a2) skips every list entered with
the frame's record count 0x5011a0 already above it. The boot code sets it once (0xfe11bd: 5 500, the standalone cabinet's value;
0xfe11d3: 5 000, reached only on a linked cabinet whose comm board reads 0 at 0xb00001). `patch_budget` raises both immediates by
the same amount and changes nothing else."""
import pytest

from vrtools.arcade.disasm import listing
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet


def _copy(rs):
    return RomSet(rs.program, rs.boot, rs.data, rs.polygons, rs.copro_data, rs.tgp_program)


def test_the_two_budget_sites_are_the_games(romset_zip):
    """0xfe11bd `mov.w #157C, 5011B0` and 0xfe11d3 `mov.w #1388, 5011B0` (12 bytes each), the second behind the flag 0x501a35;
    the standalone path (0xfe10e5: the link setting 0x40dc8c at 0) sets the flag to 1 and jumps to the first."""
    from vrtools.arcade.budget import BUDGET_SITES, site_pattern
    rs = RomSet.from_zip(romset_zip)
    assert BUDGET_SITES == ((0xFE11BD, 5500), (0xFE11D3, 5000))
    assert [l.text for l in listing(rs, 0xFE11BD, 4)] == ["mov.w   #157C, 5011B0", "cmp.b   #0, 501A35[PC]", "bne     FE11DF",
                                                         "mov.w   #1388, 5011B0"]
    for site, value in BUDGET_SITES:
        assert rs.boot[site - 0xFC0000:site - 0xFC0000 + 12] == site_pattern(value)
    assert [l.text for l in listing(rs, 0xFE10E5, 2)] == ["cmp.b   #0, 40DC8C", "bne     FE1134"]
    assert [l.text for l in listing(rs, 0xFE1120, 3)] == ["mov.b   #1, 501A35[PC]", "jsr     FE1433", "bsr     FE1B06"]
    assert listing(rs, 0xFE1131, 1)[0].text == "br      FE11BD"


def test_patch_budget_changes_the_two_immediates_only(romset_zip):
    """`patch_budget(rs, b)`: b at 0xfe11bd, b - 500 at 0xfe11d3, their four immediate bytes only; the instructions after them the
    original's."""
    from vrtools.arcade.budget import patch_budget
    rs = RomSet.from_zip(romset_zip)
    out = _copy(rs)
    patch_budget(out, 9000)
    assert [l.text for l in listing(out, 0xFE11BD, 4)] == ["mov.w   #2328, 5011B0", "cmp.b   #0, 501A35[PC]", "bne     FE11DF",
                                                          "mov.w   #2134, 5011B0"]
    changed = [i + 0xFC0000 for i in range(len(rs.boot)) if rs.boot[i] != out.boot[i]]
    assert changed and all(0xFE11C0 <= a < 0xFE11C4 or 0xFE11D6 <= a < 0xFE11DA for a in changed)
    assert listing(out, 0xFE11DF, 6) == listing(rs, 0xFE11DF, 6)
    assert out.program == rs.program and out.data == rs.data and out.polygons == rs.polygons


@pytest.mark.parametrize("site", [0xFE11BD, 0xFE11D3])
def test_a_changed_budget_site_is_refused(romset_zip, site):
    """Other bytes at either site (a changed immediate, another instruction) are refused naming the site, and neither site is
    written."""
    from vrtools.arcade.budget import patch_budget
    rs = RomSet.from_zip(romset_zip)
    for at in (site - 0xFC0000 + 3, site - 0xFC0000 + 8):
        boot = bytearray(rs.boot)
        boot[at] ^= 0x01
        bad = RomSet(rs.program, bytes(boot), rs.data, rs.polygons, rs.copro_data, rs.tgp_program)
        with pytest.raises(PatchError, match=f"{site:#x}"):
            patch_budget(bad, 8000)
        assert bad.boot == bytes(boot)


def test_patch_budget_refuses_values_out_of_range(romset_zip):
    """Below the game's 5 500, or at MAME's 0x1000000 (push_object ignores an object with that size word), is refused."""
    from vrtools.arcade.budget import MAX_BUDGET, patch_budget
    rs = RomSet.from_zip(romset_zip)
    assert MAX_BUDGET == 0xFFFFFF
    for bad in (5499, 0x1000000, 0, -1):
        with pytest.raises(PatchError):
            patch_budget(_copy(rs), bad)


def test_the_ten_course_build_raises_the_budget_to_10500(romset_zip):
    """Pascal's "Ok" to 10 500 (findings §3): `install_directory` (the ten-course build) writes FRAME_BUDGET = 10 500 at 0xfe11bd and
    LINK_FRAME_BUDGET = 10 000 at 0xfe11d3 (the game's 5 000 raised by the same 5 000); both immediates are among
    tests/test_directory.py's allowed spans."""
    from vrtools.arcade.budget import FRAME_BUDGET, LINK_FRAME_BUDGET
    from vrtools.arcade.directory import ORIGINALS, install_directory
    from tests.test_directory import SPANS
    assert (FRAME_BUDGET, LINK_FRAME_BUDGET) == (10_500, 10_000)
    rs = RomSet.from_zip(romset_zip)
    out = install_directory(rs, (ORIGINALS * 4)[:10])
    assert [l.text for l in listing(out, 0xFE11BD, 4)] == ["mov.w   #2904, 5011B0", "cmp.b   #0, 501A35[PC]", "bne     FE11DF",
                                                          "mov.w   #2710, 5011B0"]
    assert (0xFE11C0, 4) in SPANS and (0xFE11D6, 4) in SPANS
    changed = [i + 0xFC0000 for i in range(0xFE1100 - 0xFC0000, 0xFE1200 - 0xFC0000) if rs.boot[i] != out.boot[i]]
    assert changed and all(0xFE11C0 <= a < 0xFE11C4 or 0xFE11D6 <= a < 0xFE11DA for a in changed)
