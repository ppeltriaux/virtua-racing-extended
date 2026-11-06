import math

import numpy as np
import pytest

from vrtools.geom.fit import nearest_pairs, similarity_fit


def test_similarity_fit_recovers_scale_rotation_translation():
    rng = np.random.default_rng(1)
    src = rng.uniform(-50, 50, size=(200, 2))
    a = math.pi
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    dst = 10.4 * (src @ R.T) + np.array([100.0, -7.0])
    scale, Rf, t, residual = similarity_fit(src, dst)
    assert scale == pytest.approx(10.4, abs=1e-6)
    assert Rf == pytest.approx(R, abs=1e-6)
    assert t == pytest.approx([100.0, -7.0], abs=1e-6)
    assert residual < 1e-9


def test_nearest_pairs():
    a = np.array([[0.0, 0.0], [10.0, 10.0]]); b = np.array([[9.0, 9.0], [1.0, 0.0], [50.0, 50.0]])
    assert nearest_pairs(a, b) == [(0, 1), (1, 0)]
