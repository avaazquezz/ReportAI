import math
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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

    def __init__(self, name: str, max_attempts: int, window_seconds: int, *, refusal: str | None = None) -> None:
        self.name = name
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)
        # The 429's detail, when a caller must tell this limit from another one; None = the generic one.
        self.refusal = refusal

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
            retry_after = max(math.ceil(oldest_left), 1)
            if self.refusal is None:
                raise RateLimitException(retry_after)
            raise RateLimitException(retry_after, self.refusal)

    async def record(self, db: AsyncSession, key: str) -> None:
        """Counts one attempt and commits at once: the request usually fails right after, and
        its rollback must not take the attempt with it."""
        db.add(RateLimitHit(key=self._key(key)))
        await db.commit()

    async def reset(self, db: AsyncSession, key: str) -> None:
        await db.execute(delete(RateLimitHit).where(RateLimitHit.key == self._key(key)))


async def claim(db: AsyncSession, lock: str, *limits: tuple[AttemptLimiter, str]) -> None:
    """Checks every limit and counts one attempt against each as a single step, for a route where
    overshooting costs money. Simultaneous claims of one `lock` queue on a transaction-scoped
    advisory lock, so none counts before the previous one has recorded; the commit (or, on a
    refusal, the rollback) releases it. Commits whatever the session holds, like record().

    # ponytail: one lock for every key of a route serializes all its claims, a few milliseconds
    # each; a lock per key if a route ever claims hundreds of times a second.
    """
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock))))
    try:
        for limiter, key in limits:
            await limiter.check(db, key)
    except RateLimitException:
        await db.rollback()  # let the next one in now, not when this request's session closes
        raise
    db.add_all([RateLimitHit(key=limiter._key(key)) for limiter, key in limits])
    await db.commit()


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
# Each signup emails an address nobody has proven yet: few per address, few per sender.
signup_by_email = AttemptLimiter("signup_email", max_attempts=3, window_seconds=60 * 60)
signup_by_ip = AttemptLimiter("signup_ip", max_attempts=5, window_seconds=60 * 60)
# A company's data export reads every file it has: once an hour is plenty for portability.
export_by_tenant = AttemptLimiter("export_tenant", max_attempts=1, window_seconds=60 * 60)
# The landing's live demo is open to anyone and each try costs real AI: a few per visitor and a
# ceiling for everyone, per day, with details the page tells apart (frontend/app/utils/demoFields.ts
# reads "is full"), claimed with claim(). Each preview render hits Gotenberg.
_DAY = 24 * 60 * 60
DEMO_TOTAL_KEY = "all"
DEMO_FULL = "The demo is full for today. Try again tomorrow."
demo_capture_by_ip = AttemptLimiter(
    "demo_capture_ip", settings.PUBLIC_DEMO_PER_IP_DAILY, _DAY, refusal="You have used your demo tries for today."
)
demo_capture_total = AttemptLimiter("demo_capture_total", settings.PUBLIC_DEMO_DAILY_LIMIT, _DAY, refusal=DEMO_FULL)
demo_pdf_by_ip = AttemptLimiter("demo_pdf_ip", max_attempts=10, window_seconds=60 * 60)


async def prune(db: AsyncSession) -> None:
    await db.execute(delete(RateLimitHit).where(RateLimitHit.at < func.now() - KEEP_HITS_FOR))
