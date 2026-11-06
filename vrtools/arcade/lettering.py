"""The select panels' name lettering (Phase 21): the white letters the three original panels carry on their overlay
(layer A, rows 148-166: 2-px strokes, 1-px dark outline, 6 x 14, I 2 wide), cut from the user's ROM at build time,
plus N M U V Z drawn in the same style (the seven new names need them). Recon §1."""
from __future__ import annotations

import numpy as np

from vrtools.arcade.panel import COLS, ORIGINAL_PANELS, ROWS, char_pixels, char_source, decode_panel, select_palette
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet

WHITE = (240, 240, 240)
OUTLINE = (16, 16, 16)
NAME_ROWS = (148, 167)                      # the names' rows on the originals' overlays
ORIGINAL_NAMES = {0: "BIG FOREST", 1: "BAY BRIDGE", 2: "ACROPOLIS"}
LETTER_GAP, SPACE = 1, 4
NEW_LETTERS: dict[str, tuple[str, ...]] = {
    "N": ("##..##", "##..##", "###.##", "###.##", "###.##", "######", "######", "######", "##.###", "##.###", "##.###",
          "##..##", "##..##", "##..##"),
    "M": ("##...##", "###.###", "#######", "#######", "##.#.##", "##.#.##", "##...##", "##...##", "##...##", "##...##",
          "##...##", "##...##", "##...##", "##...##"),
    "U": ("##..##",) * 12 + ("######", ".####."),
    "V": ("##..##",) * 10 + (".####.", ".####.", "..##..", "..##.."),
    "Z": ("######", "######", "....##", "...###", "...##.", "..###.", "..##..", ".###..", ".##...", "###...", "##....",
          "##....", "######", "######"),
}


def _overlay_white(rs: RomSet, art: int) -> np.ndarray:
    """(168, 128) bool: the white (all channels >= 200) pixels of an original panel's overlay."""
    sp = select_palette(rs)
    base = (sp["dst"] - 0x900000) // 2
    words = sp["words"]
    m = decode_panel(rs, ORIGINAL_PANELS[art][0])
    out = np.zeros((ROWS * 8, COLS * 8), bool)
    for r in range(m.rows):
        for c in range(m.cols):
            ch = (m.base + m.tiles[r * m.cols + c]) & 0x3FFF
            try:
                px = char_pixels(char_source(rs, ch))
            except PatchError:
                continue
            for y in range(8):
                for x in range(8):
                    i = px[y][x]
                    k = (ch >> 7) * 16 + i - base
                    if i and 0 <= k < len(words):
                        w = words[k]
                        if min(w & 31, (w >> 5) & 31, (w >> 10) & 31) * 8 >= 200:
                            out[r * 8 + y, c * 8 + x] = True
    return out


def _clean(mask: np.ndarray) -> list[list[int]]:
    """The mask without isolated pixels, trimmed to its bounding box."""
    p = np.pad(mask, 1)
    nb = p[:-2, 1:-1].astype(int) + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]
    m = mask & (nb > 0)
    ys, xs = np.nonzero(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(int).tolist()


def original_letters(rs: RomSet) -> dict[str, list[list[int]]]:
    """Letter masks cut from the three original names: white column runs read right to left; a run 7k - 1 wide holds k
    touching letters; a wider run (Big Forest's B joins the road) is not used."""
    out: dict[str, list[list[int]]] = {}
    for art, name in ORIGINAL_NAMES.items():
        band = _overlay_white(rs, art)[NAME_ROWS[0]:NAME_ROWS[1]]
        cols = np.nonzero(band.any(0))[0]
        runs, start = [], cols[0]
        for a, b in zip(cols, cols[1:]):
            if b != a + 1:
                runs.append((start, a)); start = b
        runs.append((start, cols[-1]))
        chars = list(name.replace(" ", ""))
        for a, b in reversed(runs):
            if not chars:
                break
            w = b - a + 1
            if w <= 6:
                pieces = [(a, b)]
            elif (w + 1) % 7 == 0:
                pieces = [(a + 7 * k, a + 7 * k + 5) for k in range((w + 1) // 7)]
            else:
                chars.pop()                                        # a letter joined to something else: skipped
                continue
            for x0, x1 in reversed(pieces):
                ch = chars.pop()
                if ch not in out:
                    out[ch] = _clean(band[:, x0:x1 + 1])
    return out


def letters(rs: RomSet) -> dict[str, list[list[int]]]:
    out = original_letters(rs)
    for ch, rows in NEW_LETTERS.items():
        out[ch] = [[1 if c == "#" else 0 for c in r] for r in rows]
    return out


def draw_name(img: np.ndarray, text: str, right: int, bottom: int, masks: dict) -> None:
    """Draw `text` right-aligned at column `right` (exclusive) with its last row at `bottom` - 1: white strokes over a
    1-px dark outline, 1-px gaps, 4-px spaces (in place, H x W x 3 uint8)."""
    placed = []
    x = right
    for ch in reversed(text):
        if ch == " ":
            x -= SPACE
            continue
        if ch not in masks:
            raise PatchError(f"no letter {ch!r} for the select panel name {text!r}")
        m = np.array(masks[ch], bool)
        x -= m.shape[1]
        placed.append((x, bottom - m.shape[0], m))
        x -= LETTER_GAP
    h, w = img.shape[:2]
    white = np.zeros((h, w), bool)
    for x0, y0, m in placed:
        ys, xs = np.nonzero(m)
        ok = (y0 + ys >= 0) & (y0 + ys < h) & (x0 + xs >= 0) & (x0 + xs < w)
        white[y0 + ys[ok], x0 + xs[ok]] = True
    p = np.pad(white, 1)
    ring = np.zeros_like(white)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ring |= p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
    img[ring & ~white] = OUTLINE
    img[white] = WHITE
