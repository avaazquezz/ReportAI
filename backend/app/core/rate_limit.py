import math
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RateLimitException
from app.models.rate_limit_hit import RateLimitHit

# Rows older than this are useless: no window below is longer. The worker prunes them.
KEEP_HITS_FOR = timedelta(days=1)


class AttemptLimiter:
    """Sliding-window count of attempts per key, in Postgres: every API worker and every restart
    shares it, so the limit is the configured one, not a multiple of it.

    # ponytail: check and record are separate statements, so a burst of simultaneous attempts
    # can overshoot the limit by a few. A per-key advisory lock closes that if it ever matters.
    """

    def __init__(self, name: str, max_attempts: int, window_seconds: int) -> None:
        self.name = name
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)

    def _key(self, key: str) -> str:
        return f"{self.name}:{key}"

    async def check(self, db: AsyncSession, key: str) -> None:
        """Raise RateLimitException if `key` already used up its attempts in the window."""
        count, oldest_left = (
            await db.execute(
                select(
                    func.count(),
                    func.extract("epoch", func.min(RateLimitHit.at) + self.window - func.now()),
                ).where(RateLimitHit.key == self._key(key), RateLimitHit.at > func.now() - self.window)
            )
        ).one()
        if count >= self.max_attempts:
            raise RateLimitException(max(math.ceil(oldest_left), 1))

    async def record(self, db: AsyncSession, key: str) -> None:
        """Counts one attempt and commits at once: the request usually fails right after, and
        its rollback must not take the attempt with it."""
        db.add(RateLimitHit(key=self._key(key)))
        await db.commit()

    async def reset(self, db: AsyncSession, key: str) -> None:
        await db.execute(delete(RateLimitHit).where(RateLimitHit.key == self._key(key)))


# Failed logins: per account (stops guessing one password list) and per IP (stops spraying
# one password over many accounts). Reset on a successful login.
login_by_email = AttemptLimiter("login_email", max_attempts=5, window_seconds=15 * 60)
login_by_ip = AttemptLimiter("login_ip", max_attempts=30, window_seconds=15 * 60)
# Every password-reset request counts — each one sends an email.
forgot_by_email = AttemptLimiter("forgot_email", max_attempts=5, window_seconds=60 * 60)
forgot_by_ip = AttemptLimiter("forgot_ip", max_attempts=20, window_seconds=60 * 60)
# Wrong setup codes: the code is long enough not to be guessed, this just keeps it that way.
setup_code_by_ip = AttemptLimiter("setup_code_ip", max_attempts=10, window_seconds=15 * 60)
# Technicians' sign-in links: each request sends an email, like a reset.
magic_link_by_email = AttemptLimiter("magic_link_email", max_attempts=5, window_seconds=60 * 60)
magic_link_by_ip = AttemptLimiter("magic_link_ip", max_attempts=20, window_seconds=60 * 60)
# Wrong typed codes: 5 and the outstanding code dies with them (8 characters, 31 symbols each).
MAGIC_CODE_ATTEMPTS = 5
magic_code_by_email = AttemptLimiter("magic_code_email", max_attempts=MAGIC_CODE_ATTEMPTS, window_seconds=15 * 60)
# A company's data export reads every file it has: once an hour is plenty for portability.
export_by_tenant = AttemptLimiter("export_tenant", max_attempts=1, window_seconds=60 * 60)


async def prune(db: AsyncSession) -> None:
    await db.execute(delete(RateLimitHit).where(RateLimitHit.at < func.now() - KEEP_HITS_FOR))
