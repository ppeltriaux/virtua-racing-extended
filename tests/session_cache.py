"""One behaviour for the tests' module-level session caches (weather Task 7, the whole suite: a session constructor that failed
after about ten minutes was rebuilt by every test of its module, fourteen times, two and a half hours of one run).

`cached(store, key, make)`: `store[key]` made once by `make()`; a failure is CACHED and raised again for every later test of the
session (a SessionBuildFailed naming the first error, chained to it), never rebuilt. A pytest skip (or any other outcome that is not
an Exception) is not cached: it costs nothing to reach again."""
from __future__ import annotations


class SessionBuildFailed(RuntimeError):
    """A cached session build that failed earlier in this session."""


class _Failed:
    def __init__(self, exc: Exception):
        self.exc = exc


def cached(store: dict, key, make):
    if key in store:
        value = store[key]
        if isinstance(value, _Failed):
            raise SessionBuildFailed(f"the session build {key!r} failed earlier in this session (not rebuilt): "
                                     f"{value.exc!r}") from value.exc
        return value
    try:
        value = make()
    except Exception as e:
        store[key] = _Failed(e)
        raise
    store[key] = value
    return value
