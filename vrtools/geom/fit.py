"""Similarity transform fitting (Umeyama) and nearest-neighbour pairing for 2-D point sets."""

from __future__ import annotations

import numpy as np


def similarity_fit(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, float]:
    """Least-squares scale, rotation and translation with dst ≈ scale * R @ src + t (paired rows).

    Returns (scale, R (2x2), t (2,), rms residual)."""
    src = np.asarray(src, dtype=float); dst = np.asarray(dst, dtype=float)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[0] < 2:
        raise ValueError("need two equally sized (n, 2) point sets with n >= 2")
    ms, md = src.mean(0), dst.mean(0)
    cs, cd = src - ms, dst - md
    cov = cd.T @ cs / len(src)
    U, S, Vt = np.linalg.svd(cov)
    D = np.eye(2)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[1, 1] = -1
    R = U @ D @ Vt
    var_s = (cs ** 2).sum() / len(src)
    scale = float(np.trace(np.diag(S) @ D) / var_s)
    t = md - scale * R @ ms
    fitted = scale * (src @ R.T) + t
    residual = float(np.sqrt(((fitted - dst) ** 2).sum(1).mean()))
    return scale, R, t, residual


def nearest_pairs(a: np.ndarray, b: np.ndarray) -> list[tuple[int, int]]:
    """For each row of a, the index of the nearest row of b."""
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    d = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
    return [(i, int(j)) for i, j in enumerate(d.argmin(1))]
