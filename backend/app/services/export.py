"""Data portability (GDPR art. 20): everything ReportAI holds for one company in one zip its
admin downloads — its settings, team, channels, document types with their templates, reports
with their documents, audio and photos, and its audit log. Never a secret: the queries select
named columns, so password hashes, session versions and channel credentials are not even read."""

import asyncio
import json
import tempfile
import uuid
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.channel_connection import ChannelConnection
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.report_revision import ReportRevision
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser

# Bumped when a file's shape changes in a way a reader of an older export would misread.
FORMAT_VERSION = 1


async def _rows(db: AsyncSession, *columns: Any, where: ColumnElement[bool], order_by: Any) -> list[dict[str, Any]]:
    result = await db.execute(select(*columns).where(where).order_by(order_by))
    return [dict(row._mapping) for row in result]


def _existing(paths: list[str]) -> set[str]:
    return {path for path in paths if Path(path).is_file()}


def _json(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"{type(value).__name__} has no JSON form in the export")


def _write(documents: dict[str, Any], files: dict[str, str]) -> Path:
    with tempfile.NamedTemporaryFile(prefix="reportai-export-", suffix=".zip", delete=False) as out:
        path = Path(out.name)
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in documents.items():
                    archive.writestr(name, json.dumps(data, indent=2, ensure_ascii=False, default=_json))
                for name, source in files.items():
                    archive.write(source, name)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    return path


async def build(db: AsyncSession, tenant: Tenant, exported_at: datetime) -> Path:
    """Writes the company's export to a temporary zip and returns its path: the caller deletes it."""
    tenant_id = tenant.id
    team = await _rows(
        db, TenantUser.full_name, TenantUser.email, TenantUser.role, TenantUser.is_active, TenantUser.created_at,
        TenantUser.email_verified_at, where=TenantUser.tenant_id == tenant_id, order_by=TenantUser.created_at,
    )
    channels = await _rows(
        db, ChannelConnection.channel_type, ChannelConnection.display_name, ChannelConnection.routing_key,
        ChannelConnection.allowed_senders, ChannelConnection.is_active, ChannelConnection.created_at,
        where=ChannelConnection.tenant_id == tenant_id, order_by=ChannelConnection.created_at,
    )
    document_types = await _rows(
        db, DocumentType.id, DocumentType.name, DocumentType.description, DocumentType.field_schema,
        DocumentType.prompt_instructions, DocumentType.notification_emails, DocumentType.is_active,
        DocumentType.created_at, DocumentType.updated_at,
        where=DocumentType.tenant_id == tenant_id, order_by=DocumentType.created_at,
    )
    templates = await _rows(
        db, DocumentTemplate.id, DocumentTemplate.document_type_id, DocumentTemplate.file_path,
        DocumentTemplate.original_filename, DocumentTemplate.version, DocumentTemplate.is_active,
        DocumentTemplate.created_at,
        where=DocumentTemplate.tenant_id == tenant_id, order_by=DocumentTemplate.version,
    )
    reports = await _rows(
        db, Report.id, Report.document_type_id, Report.file_path, Report.audio_path, Report.status,
        Report.requester_channel, Report.requester_identifier, Report.source_text, Report.extracted_fields,
        Report.evidence, Report.channel_meta, Report.received_at, Report.created_at, Report.completed_at,
        Report.reject_reason,
        where=Report.tenant_id == tenant_id, order_by=Report.created_at,
    )
    revisions = [
        dict(row._mapping)
        for row in await db.execute(
            select(
                ReportRevision.report_id, ReportRevision.action, ReportRevision.changes, ReportRevision.note,
                ReportRevision.created_at, TenantUser.email.label("author"),
            )
            .join(Report, Report.id == ReportRevision.report_id)
            .outerjoin(TenantUser, TenantUser.id == ReportRevision.user_id)
            .where(Report.tenant_id == tenant_id)
            .order_by(ReportRevision.created_at)
        )
    ]
    photos = await _rows(
        db, ReportAttachment.id, ReportAttachment.report_id, ReportAttachment.path,
        where=(ReportAttachment.tenant_id == tenant_id) & ReportAttachment.report_id.is_not(None),
        order_by=ReportAttachment.created_at,
    )
    audit_events = await _rows(
        db, AuditEvent.created_at, AuditEvent.actor_label, AuditEvent.action, AuditEvent.target, AuditEvent.ip,
        AuditEvent.details, where=AuditEvent.tenant_id == tenant_id, order_by=AuditEvent.created_at,
    )

    referenced = [
        path
        for path in (
            tenant.logo_path,
            *(t["file_path"] for t in templates),
            *(r[key] for r in reports for key in ("file_path", "audio_path")),
            *(p["path"] for p in photos),
        )
        if path
    ]
    present = await asyncio.to_thread(_existing, referenced)
    files: dict[str, str] = {}  # path in the zip → path on disk
    missing: list[str] = []

    def include(source: str | None, name: str) -> str | None:
        """The file's path in the zip, or None (listed in the manifest) when it is gone from disk."""
        if not source:
            return None
        if source not in present:
            missing.append(source)
            return None
        files[name] = source
        return name

    templates_of: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for template in templates:
        templates_of[template.pop("document_type_id")].append(template)
        template_id, source = template.pop("id"), template.pop("file_path")
        template["file"] = include(source, f"templates/{template_id}{Path(source).suffix}")
    names: dict[uuid.UUID, str] = {}
    for document_type in document_types:
        type_id = document_type.pop("id")
        names[type_id] = document_type["name"]
        document_type["templates"] = templates_of[type_id]

    revisions_of: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for revision in revisions:
        revisions_of[revision.pop("report_id")].append(revision)
    photos_of: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for photo in photos:
        photos_of[photo["report_id"]].append(photo)
    for report in reports:
        folder = f"reports/{report['id']}"
        document, audio = report.pop("file_path"), report.pop("audio_path")
        report["document_type"] = names.get(report.pop("document_type_id"))
        report["revisions"] = revisions_of[report["id"]]
        candidates = [
            include(document, f"{folder}/document{Path(document or '').suffix}"),
            include(audio, f"{folder}/audio{Path(audio or '').suffix}"),
            *(include(p["path"], f"{folder}/photos/{p['id']}{Path(p['path']).suffix}") for p in photos_of[report["id"]]),
        ]
        report["files"] = [name for name in candidates if name]

    company = {
        "name": tenant.name, "slug": tenant.slug, "language": tenant.language, "timezone": tenant.timezone,
        "brand_color": tenant.brand_color, "reply_to_email": tenant.reply_to_email, "plan": tenant.plan,
        "plan_status": tenant.plan_status, "created_at": tenant.created_at,
        "logo": include(tenant.logo_path, f"branding/logo{Path(tenant.logo_path or '').suffix}"),
    }
    manifest = {
        "format_version": FORMAT_VERSION,
        "exported_at": exported_at,
        "company": tenant.slug,
        "counts": {
            "team": len(team), "channels": len(channels), "document_types": len(document_types),
            "templates": len(templates), "reports": len(reports), "revisions": len(revisions),
            "audit_events": len(audit_events), "files": len(files),
        },
        "missing_files": missing,
    }
    documents = {
        "manifest.json": manifest, "company.json": company, "team.json": team, "channels.json": channels,
        "document_types.json": document_types, "reports.json": reports, "audit_events.json": audit_events,
    }
    return await asyncio.to_thread(_write, documents, files)
