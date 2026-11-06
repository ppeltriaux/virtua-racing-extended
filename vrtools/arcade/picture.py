"""A select-panel picture in the hardware's terms (Phase 21): 336 tiles of 8 x 8 in three 16-colour palettes (a tile's
palette is its character >> 7), at most PICTURE_CHARS characters; its 'not chosen' grey palettes (the START highlight
greys the courses not chosen, recon §3); and the picture record the select routines read.

Local character indices: palette p's characters are 128 p .. 128 p + n_p - 1 (a slot's area holds three 128-character
blocks, one per palette). Colours are xBGR555 words with bit 15 set, as the select screen's own palettes."""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

from vrtools.arcade.panel import char_bytes
from vrtools.convert.backdrop import _kmeans, _nearest

PICTURE_CHARS = 320                  # (288 while the pictures had to fit the bank-0 tail and the program reserve; Task 4 places them in free runs)
PALETTES, COLOURS = 3, 15
FRAME_WORD = 0x8000 | 3 << 10 | 15 << 5 | 29          # the panels' orange frame (232, 120, 24): kept in the grey set
GREY_LO, GREY_HI = 10, 22                              # the originals' grey sets span these levels
RECORD_BYTES = 36
SEED = 21


@dataclass
class Picture:
    chars: dict[int, bytes]          # local index -> 32 bytes (4 bpp, as character RAM holds them)
    palettes: list[int]              # 48 words, entry 0 of each palette 0x8000 (transparent, unused)
    map: list[int]                   # 336 local indices, row-major (21 rows of 16)


@dataclass
class PictureRecord:
    chars_addr: int                  # the three runs back to back
    counts: int                      # n0 | n1 << 8 | n2 << 16
    normal_addr: int                 # 48 words each
    chosen_addr: int
    grey_addr: int
    map_addr: int                    # 336 local indices (halfwords)
    a_dst: int = 0                   # the originals' layer-A palettes (palette RAM, 32 words), 0 for converted courses
    a_chosen_addr: int = 0
    a_grey_addr: int = 0


def _word(c: np.ndarray) -> int:
    r, g, b = (int(v) for v in np.clip(np.round(c / 8), 0, 31))
    return 0x8000 | b << 10 | g << 5 | r


def _rgb(w: int) -> np.ndarray:
    return np.array([(w & 31) * 8, ((w >> 5) & 31) * 8, ((w >> 10) & 31) * 8], float)


def quantise(rgb: np.ndarray, max_chars: int = PICTURE_CHARS) -> Picture:
    """Tiles grouped into three palettes (k-means on their mean and spread), fifteen colours per palette (k-means on its
    tiles' pixels), each tile moved to the palette that draws it best (twice), identical tiles shared, then similar
    tiles merged per palette (k-means, the member nearest each centre kept) until the picture holds at most `max_chars`
    characters and each palette at most 128."""
    px = rgb.astype(float)
    tiles = px.reshape(21, 8, 16, 8, 3).transpose(0, 2, 1, 3, 4).reshape(336, 64, 3)
    _, group = _kmeans(np.concatenate([tiles.mean(1), tiles.std(1)], 1), PALETTES, seed=SEED)
    for _ in range(2):
        colours = np.zeros((PALETTES, COLOURS, 3))
        for g in range(PALETTES):
            pix = tiles[group == g].reshape(-1, 3)
            c = _kmeans(pix, COLOURS, seed=SEED)[0] if len(pix) else np.zeros((1, 3))
            c = np.array([_rgb(_word(v)) for v in c])                      # what the hardware will show
            colours[g] = np.concatenate([c, np.repeat(c[-1:], COLOURS - len(c), 0)]) if len(c) < COLOURS else c
        err = np.stack([((tiles[:, :, None, :] - colours[g][None, None]) ** 2).sum(3).min(2).sum(1) for g in range(PALETTES)], 1)
        group = err.argmin(1)
    index = np.empty((336, 64), np.int64)
    for g in range(PALETTES):
        m = group == g
        if m.any():
            index[m] = ((tiles[m][:, :, None, :] - colours[g][None, None]) ** 2).sum(3).argmin(2) + 1
    uniq = {g: np.unique(index[group == g], axis=0, return_inverse=True) for g in range(PALETTES) if (group == g).any()}
    total = sum(len(u[0]) for u in uniq.values())
    quota = {g: min(128, len(u[0]), max(1, int(max_chars * len(u[0]) / max(total, max_chars)))) for g, u in uniq.items()}
    chars: dict[int, bytes] = {}
    local_of_tile = np.empty(336, np.int64)
    for g, (pats, inv) in uniq.items():
        inv = inv.ravel()
        q = quota[g]
        if len(pats) > q:
            vec = colours[g][pats - 1].reshape(len(pats), -1)
            centres, lab = _kmeans(vec, q, weights=np.bincount(inv, minlength=len(pats)).astype(float), seed=SEED)
            keep = {j: np.flatnonzero(lab == j)[((vec[lab == j] - centres[j]) ** 2).sum(1).argmin()] for j in set(lab.tolist())}
            rep = np.array([keep[j] for j in lab])
        else:
            rep = np.arange(len(pats))
        slot = {r: 128 * g + k for k, r in enumerate(sorted(set(rep.tolist())))}
        for r, local in slot.items():
            chars[local] = char_bytes(pats[r].reshape(8, 8).tolist())
        local_of_tile[np.flatnonzero(group == g)] = [slot[rep[i]] for i in inv]
    palettes = []
    for g in range(PALETTES):
        palettes += [0x8000] + [_word(c) for c in colours[g]]
    return Picture(chars, palettes, local_of_tile.tolist())


def grey(palettes: list[int], keep: tuple[int, ...] = (FRAME_WORD,)) -> list[int]:
    """The 'not chosen' set: per palette, each colour a grey level from GREY_LO to GREY_HI by its luminance within the
    palette (the originals' ramps each span 10-22), `keep` colours and entry 0 unchanged."""
    out = list(palettes)
    lum = lambda w: 0.3 * (w & 31) + 0.59 * ((w >> 5) & 31) + 0.11 * ((w >> 10) & 31)
    for p in range(len(palettes) // 16):
        idx = [i for i in range(16 * p + 1, 16 * p + 16) if palettes[i] not in keep]
        if not idx:
            continue
        lo, hi = min(lum(palettes[i]) for i in idx), max(lum(palettes[i]) for i in idx)
        for i in idx:
            v = (GREY_LO + GREY_HI) / 2 if hi == lo else GREY_LO + (GREY_HI - GREY_LO) * (lum(palettes[i]) - lo) / (hi - lo)
            g = int(round(v))
            out[i] = 0x8000 | g << 10 | g << 5 | g
    return out


def encode_record(r: PictureRecord) -> bytes:
    return struct.pack("<9I", r.chars_addr, r.counts, r.normal_addr, r.chosen_addr, r.grey_addr, r.map_addr,
                       r.a_dst, r.a_chosen_addr, r.a_grey_addr)


def picture_blob(p: Picture, at: int) -> tuple[bytes, PictureRecord]:
    """The picture's data laid out from address `at`: the three character runs, the normal, chosen (= normal) and grey
    palettes, the map."""
    runs = [sorted(k for k in p.chars if k >> 7 == q) for q in range(PALETTES)]
    for q, run in enumerate(runs):
        if run != list(range(128 * q, 128 * q + len(run))):
            raise ValueError(f"palette {q}'s characters are not one run from {128 * q}")
    data = b"".join(p.chars[k] for run in runs for k in run)
    pal = struct.pack("<48H", *p.palettes)
    blob = data + pal + pal + struct.pack("<48H", *grey(p.palettes)) + struct.pack("<336H", *p.map)
    n = [len(r) for r in runs]
    normal = at + len(data)
    rec = PictureRecord(at, n[0] | n[1] << 8 | n[2] << 16, normal, normal + 96, normal + 192, normal + 288)
    return blob, rec


# ---- the originals (recon §3): their pictures stay in the ROM; a record points at them
START_TABLES = {"b_chosen": 0xFC3825, "b_grey": 0xFC3A1D, "a_dst": 0xFC3741, "a_chosen": 0xFC374D, "a_grey": 0xFC3951}


def _boot_u32(rs, addr: int) -> int:
    return struct.unpack_from("<I", rs.boot, addr - 0xFC0000)[0]


def original_map(rs, art: int) -> list[int]:
    """The original's layer-B map as local indices (its characters start at its slot's first character)."""
    from vrtools.arcade.panel import ORIGINAL_PANELS, decode_panel
    from vrtools.arcade.select import SLOT_CHAR
    m = decode_panel(rs, ORIGINAL_PANELS[art][1])
    local = [((m.base + t) & 0x3FFF) - SLOT_CHAR[art] for t in m.tiles]
    if not all(0 <= v < 384 for v in local):
        raise ValueError(f"art {art}: a picture character outside its three blocks")
    return local


def original_record(rs, art: int, map_addr: int) -> PictureRecord:
    """The record of original `art` (0 BF, 1 BB, 2 AC; the START tables are indexed the same way): its characters where
    the select screen's upload list takes them, its palettes in the select palette block, the START tables' sets."""
    from vrtools.arcade.panel import select_palette, select_uploads
    from vrtools.arcade.select import CHAR_RAM, SLOT_CHAR
    src, n = next((s, c) for s, d, c in select_uploads(rs) if d == CHAR_RAM + 32 * SLOT_CHAR[art])
    sp = select_palette(rs)
    normal = sp["ptr"] + 8 + 2 * (16 * (SLOT_CHAR[art] >> 7) - (sp["dst"] - 0x900000) // 2)
    counts = min(n, 128) | min(max(n - 128, 0), 128) << 8 | max(n - 256, 0) << 16
    t = {k: _boot_u32(rs, a + 4 * art) for k, a in START_TABLES.items()}
    return PictureRecord(src + 4, counts, normal, t["b_chosen"], t["b_grey"], map_addr, t["a_dst"], t["a_chosen"], t["a_grey"])


def free_runs(rs, exclude: list[tuple[int, int]], min_size: int = 4096) -> list[tuple[int, int]]:
    """(V60 address, length) of the 0xff runs of at least `min_size` bytes in bank 0 (mapped on the select screen) and
    the program ROM, outside `exclude` (address, length) spans, 16 bytes kept at each end; bank 0 first."""
    import re
    out = []
    for blob, base in ((rs.data[:0x100000], 0x100000), (rs.program, 0x200000)):
        for m in re.finditer(rb"\xff{%d,}" % min_size, blob):
            a, b = base + m.start() + 16, base + m.end() - 16
            for x, n in exclude:
                if x < b and a < x + n:                                     # cut the run around the excluded span
                    if x - a >= min_size:
                        out.append((a, x - a))
                    a = max(a, x + n)
            if b - a >= min_size:
                out.append(((a + 15) // 16 * 16, b - (a + 15) // 16 * 16))
    return out
