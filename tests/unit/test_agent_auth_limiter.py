"""In-memory sliding-window rate limiter — fake clock, no DB/network."""

from neurolegal.agent.auth import limiter as limiter_mod
from neurolegal.agent.auth.limiter import RateLimiter


def test_allows_up_to_limit_within_window() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])

    assert limiter.allow("k", limit=3, window_seconds=60.0) is True
    assert limiter.allow("k", limit=3, window_seconds=60.0) is True
    assert limiter.allow("k", limit=3, window_seconds=60.0) is True
    assert limiter.allow("k", limit=3, window_seconds=60.0) is False


def test_old_hits_fall_out_of_the_window() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])

    for _ in range(3):
        assert limiter.allow("k", limit=3, window_seconds=60.0) is True
    assert limiter.allow("k", limit=3, window_seconds=60.0) is False

    now[0] = 61.0  # past the window — old hits expire
    assert limiter.allow("k", limit=3, window_seconds=60.0) is True


def test_keys_are_independent() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])

    assert limiter.allow("a", limit=1, window_seconds=60.0) is True
    assert limiter.allow("a", limit=1, window_seconds=60.0) is False
    # a different key has its own budget
    assert limiter.allow("b", limit=1, window_seconds=60.0) is True


def test_default_clock_is_wall_clock() -> None:
    # No fake clock supplied — must not raise, must use a real monotonic clock.
    limiter = RateLimiter()
    assert limiter.allow("k", limit=1, window_seconds=60.0) is True


def test_sweep_drops_aged_out_keys_but_keeps_live_ones() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])

    limiter.allow("old", limit=5, window_seconds=60.0)
    now[0] = 100.0  # "old" is now past its window
    limiter.allow("fresh", limit=5, window_seconds=60.0)

    limiter.sweep(window_seconds=60.0)
    assert "old" not in limiter._hits
    assert "fresh" in limiter._hits


def test_allow_sweeps_at_threshold_bounding_the_map(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])
    # tiny threshold so the test doesn't build 10k keys
    monkeypatch.setattr(limiter_mod, "_SWEEP_THRESHOLD", 3)

    for i in range(3):
        limiter.allow(f"stale-{i}", limit=5, window_seconds=60.0)
    now[0] = 100.0  # all three stale keys age out
    # crossing the threshold triggers a sweep before recording the new hit
    limiter.allow("live", limit=5, window_seconds=60.0)
    assert set(limiter._hits) == {"live"}
