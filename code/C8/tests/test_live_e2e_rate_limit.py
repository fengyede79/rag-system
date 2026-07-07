from e2e.rate_limit import RateLimiter


def test_backoff_schedule_is_bounded_and_conservative():
    limiter = RateLimiter(delay_seconds=5, rate_limit_cooldown_seconds=60)

    assert limiter.backoff_seconds(1) == 0
    assert limiter.backoff_seconds(2) == 10
    assert limiter.backoff_seconds(3) == 30
    assert limiter.backoff_seconds(4) == 60
    assert limiter.backoff_seconds(5) == 60


def test_rate_limiter_uses_injected_sleep():
    calls = []
    limiter = RateLimiter(delay_seconds=2, rate_limit_cooldown_seconds=60, sleep_func=calls.append)

    limiter.wait_after_turn()
    limiter.wait_after_rate_limit()

    assert calls == [2, 60]
