import math
import time
from collections import defaultdict, deque

from app.core.exceptions import RateLimitException


class AttemptLimiter:
    """Sliding-window counter of attempts per key, kept in this process's memory.

    # ponytail: per-process, so with `--workers 2` the effective limit is up to twice the
    # configured one, and it resets on restart. Move the counters to Postgres if brute force
    # against a real installation ever shows up in the logs.
    """

    _PURGE_ABOVE_KEYS = 10_000  # bounds memory against an attacker spraying distinct keys

    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str) -> deque[float]:
        attempts = self._attempts[key]
        cutoff = time.monotonic() - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts

    def check(self, key: str) -> None:
        """Raise RateLimitException if `key` already used up its attempts in the window."""
        attempts = self._recent(key)
        if len(attempts) >= self.max_attempts:
            retry_after = math.ceil(attempts[0] + self.window_seconds - time.monotonic())
            raise RateLimitException(max(retry_after, 1))

    def record(self, key: str) -> None:
        if len(self._attempts) > self._PURGE_ABOVE_KEYS:
            for stale in [k for k in self._attempts if not self._recent(k)]:
                del self._attempts[stale]
        self._recent(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)

    def clear(self) -> None:
        self._attempts.clear()


# Failed logins: per account (stops guessing one password list) and per IP (stops spraying
# one password over many accounts). Reset on a successful login.
login_by_email = AttemptLimiter(max_attempts=5, window_seconds=15 * 60)
login_by_ip = AttemptLimiter(max_attempts=30, window_seconds=15 * 60)
# Every password-reset request counts — each one sends an email.
forgot_by_email = AttemptLimiter(max_attempts=5, window_seconds=60 * 60)
forgot_by_ip = AttemptLimiter(max_attempts=20, window_seconds=60 * 60)


def clear_all() -> None:
    for limiter in (login_by_email, login_by_ip, forgot_by_email, forgot_by_ip):
        limiter.clear()
