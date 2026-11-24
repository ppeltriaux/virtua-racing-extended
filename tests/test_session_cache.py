"""tests/session_cache.py: a session build made once, a failure cached and raised again (not rebuilt), a skip not cached."""
import pytest

from tests.session_cache import SessionBuildFailed, cached


def test_a_build_is_made_once():
    store, calls = {}, []
    make = lambda: calls.append(1) or "set"
    assert cached(store, "k", make) == "set" and cached(store, "k", make) == "set" and calls == [1]


def test_a_failed_build_is_cached_and_raised_again_not_rebuilt():
    store, calls = {}, []

    def make():
        calls.append(1)
        raise ValueError("the cover refuses entry 3")
    with pytest.raises(ValueError, match="entry 3"):
        cached(store, "k", make)
    for _ in range(3):
        with pytest.raises(SessionBuildFailed, match="failed earlier in this session") as e:
            cached(store, "k", make)
        assert isinstance(e.value.__cause__, ValueError)
    assert calls == [1]


def test_a_skip_is_not_cached():
    store, calls = {}, []

    def make():
        calls.append(1)
        pytest.skip("no reference set")
    for _ in range(2):
        with pytest.raises(pytest.skip.Exception):
            cached(store, "k", make)
    assert calls == [1, 1] and "k" not in store
