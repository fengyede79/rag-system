from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        *,
        delay_seconds: float,
        rate_limit_cooldown_seconds: float,
        sleep_func: Callable[[float], None] | None = None,
    ):
        self.delay_seconds = delay_seconds
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._sleep = sleep_func or time.sleep

    def backoff_seconds(self, attempt: int) -> float:
        if attempt <= 1:
            return 0
        if attempt == 2:
            return 10
        if attempt == 3:
            return 30
        return 60

    def wait_before_retry(self, attempt: int) -> None:
        seconds = self.backoff_seconds(attempt)
        if seconds > 0:
            self._sleep(seconds)

    def wait_after_turn(self) -> None:
        if self.delay_seconds > 0:
            self._sleep(self.delay_seconds)

    def wait_after_rate_limit(self) -> None:
        if self.rate_limit_cooldown_seconds > 0:
            self._sleep(self.rate_limit_cooldown_seconds)
