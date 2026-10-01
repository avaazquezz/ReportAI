"""Which release this installation runs, whether a newer one is out, and whether a published
security advisory affects it — shown to whoever runs the installation, since keeping it updated
is their job (`reportai update` does it).

Releases are GitHub releases of UPDATE_REPOSITORY; advisories are security/advisories.json on its
main branch. Asked at most every few hours, and a failure to ask never breaks the panel."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(hours=6)
_FAILURE_TTL = timedelta(minutes=15)


@dataclass(frozen=True)
class Advisory:
    id: str
    title: str
    severity: str
    fixed_in: str
    url: str | None


@dataclass(frozen=True)
class UpdateStatus:
    current: str
    latest: str | None = None
    latest_url: str | None = None
    update_available: bool = False
    advisories: list[Advisory] = field(default_factory=list)  # the ones that affect this release
    checked_at: datetime | None = None
    error: str | None = None


_cache: tuple[datetime, UpdateStatus] | None = None


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """'v1.4.2' → (1, 4, 2); None for anything that is not a release number (a dev build)."""
    if not value:
        return None
    parts = value.strip().removeprefix("v").split(".")
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return None


def affecting(advisories: list[dict[str, Any]], current: str) -> list[Advisory]:
    """Advisories whose range covers `current`: introduced (default: always) ≤ current < fixed_in."""
    version = parse_version(current)
    if version is None:
        return []
    found = []
    for item in advisories:
        fixed = parse_version(item.get("fixed_in"))
        introduced = parse_version(item.get("introduced")) or (0,)
        if fixed is not None and introduced <= version < fixed:
            found.append(
                Advisory(
                    id=str(item.get("id", "")),
                    title=str(item.get("title", "")),
                    severity=str(item.get("severity", "unknown")),
                    fixed_in=str(item["fixed_in"]),
                    url=item.get("url"),
                )
            )
    return found


async def _fetch() -> UpdateStatus:
    current = settings.REPORTAI_VERSION
    repository = settings.UPDATE_REPOSITORY
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"ReportAI/{current}"}
    async with httpx.AsyncClient(timeout=8, headers=headers, follow_redirects=True) as client:
        release = await client.get(f"https://api.github.com/repos/{repository}/releases/latest")
        latest, latest_url = None, None
        if release.status_code == 200:
            latest = str(release.json().get("tag_name", "")).removeprefix("v") or None
            latest_url = release.json().get("html_url")
        elif release.status_code != 404:  # 404: nothing released yet
            release.raise_for_status()
        published = await client.get(f"https://raw.githubusercontent.com/{repository}/main/security/advisories.json")
        advisories = published.json().get("advisories", []) if published.status_code == 200 else []
    current_version, latest_version = parse_version(current), parse_version(latest)
    return UpdateStatus(
        current=current,
        latest=latest,
        latest_url=latest_url,
        update_available=bool(current_version and latest_version and latest_version > current_version),
        advisories=affecting(advisories, current),
        checked_at=datetime.now(UTC),
    )


async def update_status(*, refresh: bool = False) -> UpdateStatus:
    global _cache
    if not settings.UPDATE_CHECK_ENABLED:
        return UpdateStatus(current=settings.REPORTAI_VERSION, error="Update checks are turned off (UPDATE_CHECK_ENABLED)")
    now = datetime.now(UTC)
    if _cache and not refresh:
        cached_at, status = _cache
        if now - cached_at < (_FAILURE_TTL if status.error else _CACHE_TTL):
            return status
    try:
        status = await _fetch()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Couldn't check for ReportAI updates: %s", type(exc).__name__)
        status = UpdateStatus(current=settings.REPORTAI_VERSION, error="Couldn't reach GitHub to check for updates")
    _cache = (now, status)
    return status


def clear_cache() -> None:
    global _cache
    _cache = None
