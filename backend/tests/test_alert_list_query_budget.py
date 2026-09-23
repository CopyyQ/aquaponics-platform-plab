from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select

from app.api.v1 import aquaponics_systems
from app.db.session import AsyncSessionLocal, engine
from app.models.device import Device
from app.models.operational_alert import OperationalIncident
from app.models.project import Project
from app.models.user import User


@pytest.mark.asyncio
async def test_alert_list_batches_related_resource_lookups(monkeypatch) -> None:
    suffix = uuid4().hex[:8].upper()
    device_ids: list[int] = []
    incident_ids: list[int] = []

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        assert project is not None
        now = datetime.now(UTC)
        for index in range(12):
            device = Device(
                project_id=project.id,
                code=f"ALERT-Q-{suffix}-{index:02d}",
                name=f"Alert query device {index}",
                is_enabled=True,
            )
            db.add(device)
            await db.flush()
            incident = OperationalIncident(
                project_id=project.id,
                rule_id=None,
                rule_revision_id=None,
                device_id=device.id,
                sensor_id=None,
                actuator_id=None,
                context_key=f"alert-query-{suffix}-{index}",
                status="OPEN",
                technical_severity="WARNING",
                business_risk_level_snapshot="LOW",
                started_at=now,
                opened_at=now,
                last_triggered_at=now,
                occurrence_count=1,
                trigger_snapshot={
                    "resource_type": "SENSOR",
                    "metric_type": "SENSOR_VALUE",
                    "message": f"Query budget {index}",
                },
            )
            db.add(incident)
            await db.flush()
            device_ids.append(device.id)
            incident_ids.append(incident.id)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
            owner = await db.scalar(select(User).where(User.username == "codex-test-owner"))
            assert project is not None and owner is not None

            async def public_system(_db, _public_id, _actor, *, manage=False):
                return project

            monkeypatch.setattr(aquaponics_systems, "_public_system", public_system)

            statements = 0

            def before_cursor_execute(*_args) -> None:
                nonlocal statements
                statements += 1

            event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
            try:
                rows = await aquaponics_systems.list_system_alerts(
                    project.public_id,
                    None,
                    db,
                    owner,
                )
            finally:
                event.remove(
                    engine.sync_engine,
                    "before_cursor_execute",
                    before_cursor_execute,
                )

            assert len(rows) >= 12
            assert statements <= 5
    finally:
        async with AsyncSessionLocal() as db:
            if incident_ids:
                await db.execute(
                    delete(OperationalIncident).where(
                        OperationalIncident.id.in_(incident_ids)
                    )
                )
            if device_ids:
                await db.execute(delete(Device).where(Device.id.in_(device_ids)))
            await db.commit()
