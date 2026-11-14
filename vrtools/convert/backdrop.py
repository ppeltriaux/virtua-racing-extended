"""A Saturn backdrop (1280×256, one 256-colour palette) as the arcade's (2048 px per turn, 4 bpp tiles in up to 29
sixteen-colour palettes, a palette owning the 128 codes code >> 7 names) — Phase 18b, recon §3.

Resampled ×1.6 both ways (bilinear, wrapping round the turn) from Saturn row `top_row`; tiles grouped into palettes by
k-means on their colours, each palette's 15 colours (0 is transparent) by k-means on its tiles' pixels, tiles moved to
the palette that suits them best, then similar tiles of a palette merged (k-means, the member nearest each centre kept)
until each palette holds at most its 128 codes and the course at most MAX_TILES. Two codes are reserved as solid tiles
for layer 3's fills: TOP_CODE above the band (the band's top-row colour) and the host's `fill_code` below it (the
bottom-row colour). Deterministic (seeded)."""
from __future__ import annotations

import numpy as np

from vrtools.arcade.backdrop import ArcadePanorama, BLOCK_COLUMNS, CHAR_RAM
from vrtools.saturn.backdrop import SaturnPanorama

ARCADE_WIDTH = 2048
SCALE = 1.6
BAND_ROWS = 24
TOP_CODE = 0x3000                   # palette 96, code 0: layer 3's fill above the band
FIRST_PALETTE = TOP_CODE >> 7       # 96
TILES_PER_PALETTE = 128
CODE_LIMIT = 0x4000                 # palettes 96-127 (0x900c00-0x900fff; the polygon palette starts at 0x902000)
MAX_PALETTES = (CODE_LIMIT - TOP_CODE) // TILES_PER_PALETTE
MAX_TILES = 2600
TOP_FADE = 48                       # Phase 25: under its first tile row (the fill above it), the band fades in over this many pixels
SEED = 18


def _kmeans(x: np.ndarray, k: int, iters: int = 12, weights: np.ndarray | None = None, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    """Lloyd's k-means with k-means++ seeding; returns (centres, labels). k is capped at the distinct rows of x."""
    rng = np.random.default_rng(seed)
    distinct = np.unique(x, axis=0)
    k = max(1, min(k, len(distinct)))
    centres = [distinct[rng.integers(len(distinct))]]
    d2 = ((distinct - centres[0]) ** 2).sum(1)
    for _ in range(1, k):
        p = d2 / d2.sum() if d2.sum() > 0 else None
        centres.append(distinct[rng.choice(len(distinct), p=p)])
        d2 = np.minimum(d2, ((distinct - centres[-1]) ** 2).sum(1))
    c = np.array(centres, dtype=float)
    w = np.ones(len(x)) if weights is None else weights
    for _ in range(iters):
        labels = _nearest(x, c)
        for j in range(k):
            m = labels == j
            if m.any():
                c[j] = (x[m] * w[m, None]).sum(0) / w[m].sum()
    return c, _nearest(x, c)


def _nearest(x: np.ndarray, c: np.ndarray, chunk: int = 4096) -> np.ndarray:
    out = np.empty(len(x), dtype=np.int64)
    for i in range(0, len(x), chunk):
        out[i:i + chunk] = (((x[i:i + chunk, None, :] - c[None, :, :]) ** 2).sum(2)).argmin(1)
    return out


def _resample(rgb: np.ndarray, top_row: float, column_offset: int, rows: int, v_scale: float = SCALE) -> np.ndarray:
    """(rows·8, 2048, 3) bilinear samples of the Saturn image (5-bit floats): x wraps (×SCALE), y clamps (×v_scale)."""
    h, w, _ = rgb.shape
    ys = np.clip(top_row + (np.arange(rows * 8) + 0.5) / v_scale - 0.5, 0, h - 1)
    xs = ((np.arange(ARCADE_WIDTH) - column_offset + 0.5) / SCALE - 0.5) % w
    y0 = np.floor(ys).astype(int); y1 = np.minimum(y0 + 1, h - 1); fy = (ys - y0)[:, None, None]
    x0 = np.floor(xs).astype(int); x1 = (x0 + 1) % w; fx = (xs - x0)[None, :, None]
    top = rgb[y0][:, x0] * (1 - fx) + rgb[y0][:, x1] * fx
    bottom = rgb[y1][:, x0] * (1 - fx) + rgb[y1][:, x1] * fx
    return top * (1 - fy) + bottom * fy


def _word(c: np.ndarray) -> int:
    r, g, b = (int(round(v)) for v in np.clip(c, 0, 31))
    return 0x8000 | b << 10 | g << 5 | r


def convert_panorama(sat: SaturnPanorama, top_row: float, column_offset: int, fill_code: int, rows: int = BAND_ROWS,
                     code_limit: int = CODE_LIMIT, v_scale: float = SCALE) -> tuple[ArcadePanorama, dict]:
    pal = np.array(sat.palette, dtype=np.int64)
    lut = np.stack([pal & 31, (pal >> 5) & 31, (pal >> 10) & 31], -1).astype(float)
    target = _resample(lut[sat.pixels], top_row, column_offset, rows, v_scale)                      # (H, 2048, 3), 0..31
    n_pal = (code_limit - TOP_CODE) // TILES_PER_PALETTE
    f_pal, f_local = (fill_code >> 7) - FIRST_PALETTE, fill_code & (TILES_PER_PALETTE - 1)
    if not (0 <= f_pal < n_pal) or fill_code == TOP_CODE:
        raise ValueError(f"fill code {fill_code:#x} is outside the {n_pal} palettes below {code_limit:#x}")
    top_colour, bottom_colour = target[0].mean(0), target[-1].mean(0)
    # Phase 25: layer 3 above the band is one flat colour, so a sky that is not flat at the picture's top (clouds) met it
    # on a hard line. The band's first tile row is that colour and the picture fades in under it (smoothstep).
    t = np.clip((np.arange(len(target)) - 7.5) / TOP_FADE, 0.0, 1.0)
    t = (t * t * (3 - 2 * t))[:, None, None]
    target = target + (top_colour - target) * (1 - t)
    tiles = target.reshape(rows, 8, ARCADE_WIDTH // 8, 8, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 64, 3)  # row-major tiles
    n = len(tiles)

    # palettes: group tiles by colour, then 15 colours per group, then move tiles to their best palette (twice)
    _, group = _kmeans(np.concatenate([tiles.mean(1), tiles.std(1)], 1), n_pal)
    order = np.argsort([tiles[group == g].mean((0, 1)).sum() if (group == g).any() else 1e9 for g in range(n_pal)])
    group = np.argsort(order)[group]                                                       # palettes sorted by brightness
    reserved = {0: [top_colour], f_pal: [bottom_colour]} if f_pal != 0 else {0: [top_colour, bottom_colour]}
    for _ in range(2):
        colours = np.zeros((n_pal, 15, 3))
        for g in range(n_pal):
            fixed = reserved.get(g, [])
            px = tiles[group == g].reshape(-1, 3)
            free = 15 - len(fixed)
            c = _kmeans(px, free)[0] if len(px) else np.zeros((1, 3))
            c = np.concatenate([c, np.repeat(c[-1:], free - len(c), 0)]) if len(c) < free else c
            colours[g] = np.concatenate([c, np.array(fixed).reshape(-1, 3)])
        err = np.empty((n, n_pal))
        for g in range(n_pal):
            d = ((tiles[:, :, None, :] - colours[g][None, None]) ** 2).sum(3)
            err[:, g] = d.min(2).sum(1)
        group = err.argmin(1)
    index = np.empty((n, 64), dtype=np.uint8)
    for g in range(n_pal):
        m = group == g
        if m.any():
            index[m] = ((tiles[m][:, :, None, :] - colours[g][None, None]) ** 2).sum(3).argmin(2) + 1

    # tiles: per palette, distinct index patterns merged down to the palette's codes and the course's budget
    caps = {g: TILES_PER_PALETTE - (1 if g == 0 else 0) - (1 if g == f_pal else 0) for g in range(n_pal)}
    uniq = {g: np.unique(index[group == g], axis=0, return_inverse=True) for g in range(n_pal) if (group == g).any()}
    total = sum(len(u[0]) for u in uniq.values())
    budget = MAX_TILES - 2
    quota = {g: min(caps[g], max(1, int(budget * len(u[0]) / total))) for g, u in uniq.items()}
    code_of_tile = np.empty(n, dtype=np.int64)
    out_tiles: dict[int, bytes] = {}

    def pack(ix: np.ndarray) -> bytes:
        return bytes((ix[0::2] << 4 | ix[1::2]).astype(np.uint8))

    for g, (pats, inv) in uniq.items():
        inv = inv.ravel()
        q = min(quota[g], len(pats))
        if len(pats) > q:
            vec = colours[g][pats - 1].reshape(len(pats), -1)
            weights = np.bincount(inv, minlength=len(pats)).astype(float)
            centres, lab = _kmeans(vec, q, weights=weights)
            keep = np.array([np.flatnonzero(lab == j)[((vec[lab == j] - centres[j]) ** 2).sum(1).argmin()] if (lab == j).any() else -1
                             for j in range(len(centres))])
            rep = keep[lab]
        else:
            rep = np.arange(len(pats))
        locals_free = [j for j in range(TILES_PER_PALETTE) if not (g == 0 and j == 0) and not (g == f_pal and j == f_local)]
        slot = {r: locals_free[k] for k, r in enumerate(sorted(set(rep.tolist())))}
        base = TOP_CODE + TILES_PER_PALETTE * g
        for r, j in slot.items():
            out_tiles[base + j] = pack(pats[r])
        members = np.flatnonzero(group == g)
        code_of_tile[members] = [base + slot[rep[i]] for i in inv]
    out_tiles[TOP_CODE] = pack(np.full(64, 15 if f_pal != 0 else 14, np.uint8))
    out_tiles[fill_code] = pack(np.full(64, 15, np.uint8))

    palettes = {FIRST_PALETTE + g: (0x8000,) + tuple(_word(c) for c in colours[g]) for g in range(n_pal)}
    code_of_tile[:ARCADE_WIDTH // 8] = TOP_CODE                                             # Phase 25: the first row is the fill
    code_of_tile[0], code_of_tile[(rows - 1) * (ARCADE_WIDTH // 8)] = TOP_CODE, fill_code   # the game fills layer 3 from
    tile_map = code_of_tile.reshape(rows, ARCADE_WIDTH // 8).astype(np.uint16)                # these two entries (boot 0xffe034)
    uploads, run = [], []
    for code in sorted(out_tiles):
        if run and code != run[-1] + 1:
            uploads.append((CHAR_RAM + 32 * run[0], b"".join(out_tiles[c] for c in run))); run = []
        run.append(code)
    uploads.append((CHAR_RAM + 32 * run[0], b"".join(out_tiles[c] for c in run)))
    p = ArcadePanorama(out_tiles, palettes, tile_map, uploads)

    # mean absolute error, 0-255 scale, of what the arcade draws against the resampled source
    pal_rgb = {k: np.array([[w & 31, (w >> 5) & 31, (w >> 10) & 31] for w in v], float) for k, v in palettes.items()}
    drawn = np.empty_like(tiles)
    for i, code in enumerate(code_of_tile):
        px = np.frombuffer(out_tiles[int(code)], np.uint8)
        drawn[i] = pal_rgb[int(code) >> 7][np.stack([px >> 4, px & 15], -1).ravel()]
    report = {"palettes": n_pal, "tiles": len(out_tiles), "mean_error": float(np.abs(drawn - tiles).mean() * 255 / 31)}
    assert tile_map.shape == (rows, BLOCK_COLUMNS * 8)
    return p, report
