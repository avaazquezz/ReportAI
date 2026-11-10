"""How long a company's data lives: voice notes expire, temporary files and old delivery ids are
swept, and a company that asked to be deleted is purged once its grace period is over — every
row, file and paused conversation, nothing left behind. The worker runs all of it."""

import asyncio
import logging
import shutil
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import ColumnElement, ScalarResult, and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.langgraph_checkpointer import get_checkpointer
from app.models.document_template import DocumentTemplate
from app.models.inbound_message import InboundMessage
from app.models.job import Job
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.tenant import Tenant
from app.services import audit
from app.services.channels.web import WEB

logger = logging.getLogger(__name__)

# Between asking to delete the company and the purge: time to change one's mind (through support).
DELETION_GRACE = timedelta(days=30)
# A channel redelivers a message within hours; after this its id can't come back.
KEEP_INBOUND_IDS_FOR = timedelta(days=30)
# An emailed voice note waits in inbound_tmp until its report copies it, minutes later. It isn't
# deleted on copy: a retried job reads it again.
KEEP_INBOUND_FILES_FOR = timedelta(days=2)
# What a visitor dictates to the landing's live demo is kept for a day, as the page promises.
PUBLIC_DEMO_TTL = timedelta(hours=24)

# Under the storage folder, a company's own files live in <folder>/<tenant id>, and a report's
# (document, audio) in <report id>.
_TENANT_FOLDERS = ("branding", "attachments", "templates", "template_drafts")


def _storage() -> Path:
    return Path(settings.DOCUMENT_STORAGE_PATH).resolve()


def _ours(path: str) -> Path | None:
    """A stored path, if it is inside the storage folder: nothing outside it is ever deleted."""
    resolved = Path(path).resolve()
    if resolved.is_relative_to(_storage()):
        return resolved
    logger.warning("Not deleting %s: it is outside the storage folder", path)
    return None


def _delete_files(paths: list[str], folders: list[Path]) -> None:
    for path in paths:
        if (file := _ours(path)) is not None:
            file.unlink(missing_ok=True)
    for folder in folders:
        if folder.exists():
            shutil.rmtree(folder)


async def purge_tenant(db: AsyncSession, tenant: Tenant) -> None:
    """Deletes the company and everything it has (no commit). Its paused conversations and files
    go first: they are found through its rows, so a crash halfway leaves the rows to find them
    again on the next run. Every table hanging off the company goes with it by ON DELETE CASCADE."""
    tenant_id, slug = tenant.id, tenant.slug
    reports = (await db.execute(select(Report.id, Report.file_path, Report.audio_path).where(Report.tenant_id == tenant_id))).all()
    photos = await db.scalars(select(ReportAttachment.path).where(ReportAttachment.tenant_id == tenant_id))
    templates = await db.scalars(select(DocumentTemplate.file_path).where(DocumentTemplate.tenant_id == tenant_id))
    # Every path the rows know, as well as the folders: files of older versions may live elsewhere.
    paths = [p for r in reports for p in (r.file_path, r.audio_path) if p] + list(photos) + list(templates)
    if tenant.logo_path:
        paths.append(tenant.logo_path)
    root = _storage()
    folders = [root / name / str(tenant_id) for name in _TENANT_FOLDERS] + [root / str(r.id) for r in reports]

    for report in reports:
        await get_checkpointer().adelete_thread(str(report.id))
    await asyncio.to_thread(_delete_files, paths, folders)
    await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
    # The company's own audit log went with it: this event, kept by the installation, says when.
    await audit.record(db, "tenant.purged", target=tenant_id, actor_label="system", slug=slug)


async def purge_due_tenants(db: AsyncSession) -> list[uuid.UUID]:
    """Purges every company whose grace period is over, one commit each. Still blocked is part
    of the condition: a company reactivated in the meantime is never purged."""
    due = list(
        await db.scalars(
            select(Tenant).where(
                Tenant.deletion_requested_at < datetime.now(UTC) - DELETION_GRACE,
                Tenant.is_active.is_(False),
            )
        )
    )
    for tenant in due:
        await purge_tenant(db, tenant)
        await db.commit()
    return [tenant.id for tenant in due]


async def drop_expired_audio(db: AsyncSession) -> int:
    """Deletes voice notes older than AUDIO_RETENTION_DAYS (no commit); the transcript stays."""
    if not settings.AUDIO_RETENTION_DAYS:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=settings.AUDIO_RETENTION_DAYS)
    expired = (
        await db.execute(select(Report.id, Report.audio_path).where(Report.audio_path.is_not(None), Report.created_at < cutoff))
    ).all()
    if not expired:
        return 0
    await asyncio.to_thread(_delete_files, [audio for _, audio in expired if audio], [])
    await db.execute(update(Report).where(Report.id.in_([report_id for report_id, _ in expired])).values(audio_path=None))
    return len(expired)


def is_public_demo_report() -> ColumnElement[bool]:
    """A report the landing's live demo made. Only the demo route puts this meta on an app (web)
    report, and the app's own captures carry none, so no chat message can pass for one."""
    return and_(Report.requester_channel == WEB, Report.channel_meta.contains({"public_demo": True}))


async def purge_expired_public_demo_reports(db: AsyncSession) -> int:
    """Deletes the live demo's reports once they are PUBLIC_DEMO_TTL old (no commit). Their paused
    conversations and files go first: they are found through the rows, so a crash halfway leaves
    the rows to find them again on the next run. Jobs and photos go with the rows by CASCADE.

    # ponytail: a sequential scan of reports every maintenance round; a partial index on
    # created_at WHERE the meta says public_demo if the table ever grows large.
    """
    expired = list(
        await db.execute(
            select(Report.id, Report.file_path, Report.audio_path).where(
                is_public_demo_report(), Report.created_at < datetime.now(UTC) - PUBLIC_DEMO_TTL
            )
        )
    )
    if not expired:
        return 0
    report_ids = [report.id for report in expired]
    photos = await db.scalars(select(ReportAttachment.path).where(ReportAttachment.report_id.in_(report_ids)))
    # The recording as it was uploaded waits in inbound_tmp, which is otherwise swept after two days.
    uploaded = Job.payload["media_reference"].astext
    uploads: ScalarResult[str] = await db.scalars(select(uploaded).where(Job.report_id.in_(report_ids), uploaded.is_not(None)))
    paths = [p for r in expired for p in (r.file_path, r.audio_path) if p] + list(photos) + list(uploads)
    folders = [_storage() / str(report_id) for report_id in report_ids]

    for report_id in report_ids:
        await get_checkpointer().adelete_thread(str(report_id))
    await asyncio.to_thread(_delete_files, paths, folders)
    await db.execute(delete(Report).where(Report.id.in_(report_ids)))
    return len(report_ids)


async def prune_inbound_ids(db: AsyncSession) -> None:
    await db.execute(delete(InboundMessage).where(InboundMessage.received_at < datetime.now(UTC) - KEEP_INBOUND_IDS_FOR))


def drop_stale_inbound_files() -> None:
    folder = _storage() / "inbound_tmp"
    if not folder.exists():
        return
    oldest = time.time() - KEEP_INBOUND_FILES_FOR.total_seconds()
    for file in folder.iterdir():
        if file.stat().st_mtime < oldest:
            file.unlink(missing_ok=True)
