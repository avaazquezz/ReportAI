from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.execution_log import ExecutionLog
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser


async def _create_tenant_admin(db: AsyncSession, *, name: str = "Acme", slug: str = "acme") -> TenantUser:
    tenant = Tenant(name=name, slug=slug, is_active=True)
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id,
        email=f"admin@{slug}.test",
        hashed_password=hash_password("correct-password"),
        full_name="Admin",
        role="tenant_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_super_admin(db: AsyncSession) -> TenantUser:
    user = TenantUser(
        tenant_id=None,
        email="root@reportai.dev",
        hashed_password=hash_password("super-secret-password"),
        full_name="Root Admin",
        role="super_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "correct-password"})
    return str(response.json()["access_token"])


async def _login_super(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/login", json={"email": "root@reportai.dev", "password": "super-secret-password"}
    )
    return str(response.json()["access_token"])


async def test_usage_summary_computes_exact_aggregates(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)

    report1 = Report(tenant_id=user.tenant_id, status="delivered", requester_channel="telegram", requester_identifier="1")
    report2 = Report(tenant_id=user.tenant_id, status="failed", requester_channel="telegram", requester_identifier="2")
    db.add_all([report1, report2])
    await db.flush()

    db.add_all(
        [
            ExecutionLog(
                tenant_id=user.tenant_id,
                report_id=report1.id,
                step="extract",
                status="success",
                model_used="claude-sonnet-5",
                cost_usd=Decimal("0.0200"),
                latency_ms=100,
            ),
            ExecutionLog(
                tenant_id=user.tenant_id,
                report_id=report1.id,
                step="transcribe",
                status="success",
                model_used="whisper",
                cost_usd=Decimal("0.0100"),
                latency_ms=300,
            ),
            ExecutionLog(
                tenant_id=user.tenant_id,
                report_id=report2.id,
                step="extract",
                status="error",
                cost_usd=Decimal("0.0050"),
                latency_ms=200,
            ),
        ]
    )
    await db.commit()

    response = await client.get("/usage/summary?days=30", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_cost_usd"] == 0.035
    assert body["avg_latency_ms"] == 200.0
    assert body["reports_by_status"] == {"delivered": 1, "failed": 1}
    assert body["total_reports"] == 2


async def test_usage_summary_excludes_entries_outside_window(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)

    old_log = ExecutionLog(
        tenant_id=user.tenant_id,
        step="extract",
        status="success",
        cost_usd=Decimal("99.0"),
        latency_ms=100,
    )
    db.add(old_log)
    await db.flush()
    old_log.created_at = datetime.now(UTC) - timedelta(days=90)
    await db.commit()

    response = await client.get("/usage/summary?days=30", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["total_cost_usd"] == 0.0


async def test_usage_summary_is_tenant_isolated(client: AsyncClient, db: AsyncSession) -> None:
    owner = await _create_tenant_admin(db, name="Acme", slug="acme")
    other = await _create_tenant_admin(db, name="Other Co", slug="other")
    db.add(
        ExecutionLog(
            tenant_id=owner.tenant_id, step="extract", status="success", cost_usd=Decimal("5.0"), latency_ms=100
        )
    )
    await db.commit()

    other_token = await _login(client, other.email)
    response = await client.get(
        "/usage/summary?days=30", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.json()["total_cost_usd"] == 0.0


async def test_super_admin_drill_in_matches_tenant_summary(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    await _create_super_admin(db)
    db.add(
        ExecutionLog(
            tenant_id=user.tenant_id, step="extract", status="success", cost_usd=Decimal("3.5"), latency_ms=150
        )
    )
    await db.commit()

    super_token = await _login_super(client)
    response = await client.get(
        f"/admin/tenants/{user.tenant_id}/usage/summary?days=30",
        headers={"Authorization": f"Bearer {super_token}"},
    )

    assert response.status_code == 200
    assert response.json()["total_cost_usd"] == 3.5


async def test_tenant_admin_forbidden_from_super_admin_drill_in(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)

    response = await client.get(
        f"/admin/tenants/{user.tenant_id}/usage/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
