import numpy as np
import pytest

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet


def test_the_three_names_give_fifteen_letters(romset_zip):
    """Phase 21 (recon §1): the original names BIG FOREST, BAY BRIDGE and ACROPOLIS give fifteen letters, 14 rows tall,
    6 wide (I: 2)."""
    from vrtools.arcade.lettering import original_letters
    got = original_letters(RomSet.from_zip(romset_zip))
    assert set(got) == set("ABCDEFGILOPRSTY")
    for ch, m in got.items():
        assert len(m) == 14, (ch, len(m))
        assert {len(r) for r in m} == {2 if ch == "I" else 6}, (ch, {len(r) for r in m})


def test_every_new_course_name_can_be_spelt(romset_zip):
    from vrtools.arcade.lettering import letters
    from vrtools.arcade.tencourse import COURSES
    have = letters(RomSet.from_zip(romset_zip))
    for plan in COURSES:
        assert all(ch in have for ch in plan.name if ch != " "), plan.name


def test_a_missing_letter_is_an_error():
    from vrtools.arcade.lettering import draw_name
    with pytest.raises(PatchError, match="'X'"):
        draw_name(np.zeros((20, 60, 3), np.uint8), "QX", 58, 18, {"Q": [[1]]})


def test_draw_name_outlines_white_letters():
    """White strokes over a 1-px dark outline; nothing else touched."""
    from vrtools.arcade.lettering import draw_name
    img = np.full((10, 10, 3), 77, np.uint8)
    draw_name(img, "A", 7, 6, {"A": [[1, 1], [1, 1]]})          # rows 4-5, columns 5-6 (right exclusive)
    white = {(y, x) for y in (4, 5) for x in (5, 6)}
    ring = {(y, x) for y in range(3, 7) for x in range(4, 8)} - white
    for y in range(10):
        for x in range(10):
            want = (240, 240, 240) if (y, x) in white else (16, 16, 16) if (y, x) in ring else (77, 77, 77)
            assert tuple(img[y, x]) == want, (y, x, tuple(img[y, x]))
