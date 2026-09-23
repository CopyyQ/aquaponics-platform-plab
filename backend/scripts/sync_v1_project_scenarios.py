from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any
from uuid import uuid4

import sqlalchemy as sa

from app.db.session import engine
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)

V1_REVISION = "v1"
ACTIVE_INCIDENT_STATUSES = ("PENDING", "OPEN", "ACKNOWLEDGED")


def _table(bind: sa.Connection, name: str) -> sa.Table:
    return sa.Table(name, sa.MetaData(), autoload_with=bind)


def _assert_v1_revision(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("alembic_version"):
        raise RuntimeError("V1_SCENARIO_SYNC_REQUIRES_ALEMBIC_V1")
    versions = list(
        bind.execute(sa.text("SELECT version_num FROM alembic_version")).scalars()
    )
    if versions != [V1_REVISION]:
        raise RuntimeError(
            "V1_SCENARIO_SYNC_REQUIRES_ALEMBIC_V1:"
            + ",".join(str(value) for value in versions)
        )


def _ensure_v1_project_scenario_schema(bind: sa.Connection) -> None:
    """Synchronize only the ProjectScenario additions while retaining revision v1."""
    _assert_v1_revision(bind)

    ProjectScenario.__table__.create(bind, checkfirst=True)
    ProjectScenarioItem.__table__.create(bind, checkfirst=True)
    ProjectScenarioBranch.__table__.create(bind, checkfirst=True)

    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"]
        for column in inspector.get_columns("operational_incidents")
    }
    column_ddls = {
        "project_scenario_id": "BIGINT NULL",
        "project_scenario_item_id": "BIGINT NULL",
        "project_scenario_branch_id": "BIGINT NULL",
        "resolution_reason": "VARCHAR(50) NULL",
    }
    for name, ddl in column_ddls.items():
        if name not in existing_columns:
            bind.execute(
                sa.text(
                    f'ALTER TABLE operational_incidents '
                    f'ADD COLUMN "{name}" {ddl}'
                )
            )

    inspector = sa.inspect(bind)
    existing_foreign_key_columns = {
        tuple(fk.get("constrained_columns") or ())
        for fk in inspector.get_foreign_keys("operational_incidents")
    }
    foreign_keys = (
        (
            "fk_operational_incidents_project_scenario_id_project_scenarios",
            "project_scenario_id",
            "project_scenarios",
        ),
        (
            "fk_operational_incidents_project_scenario_item_id_project_scenario_items",
            "project_scenario_item_id",
            "project_scenario_items",
        ),
        (
            "fk_operational_incidents_project_scenario_branch_id_project_scenario_branches",
            "project_scenario_branch_id",
            "project_scenario_branches",
        ),
    )
    for constraint_name, column_name, target_table in foreign_keys:
        if (column_name,) in existing_foreign_key_columns:
            continue
        bind.execute(
            sa.text(
                f'ALTER TABLE operational_incidents '
                f'ADD CONSTRAINT "{constraint_name}" '
                f'FOREIGN KEY ("{column_name}") REFERENCES "{target_table}" (id) '
                "ON DELETE RESTRICT"
            )
        )

    index_names = {
        index["name"]
        for index in sa.inspect(bind).get_indexes("operational_incidents")
    }
    ordinary_indexes = (
        ("ix_operational_incidents_project_scenario_id", "project_scenario_id"),
        (
            "ix_operational_incidents_project_scenario_item_id",
            "project_scenario_item_id",
        ),
        (
            "ix_operational_incidents_project_scenario_branch_id",
            "project_scenario_branch_id",
        ),
    )
    for index_name, column_name in ordinary_indexes:
        if index_name not in index_names:
            bind.execute(
                sa.text(
                    f'CREATE INDEX "{index_name}" '
                    f'ON operational_incidents ("{column_name}")'
                )
            )

    if "uq_active_operational_incident_scenario_branch" not in index_names:
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX "
                "uq_active_operational_incident_scenario_branch "
                "ON operational_incidents (project_scenario_branch_id) "
                "WHERE project_scenario_branch_id IS NOT NULL "
                "AND status IN ('PENDING','OPEN','ACKNOWLEDGED')"
            )
        )

    _assert_v1_revision(bind)


def _catalog_items_for_scenario(
    bind: sa.Connection, scenario_catalog_id: int | None
) -> list[dict[str, Any]]:
    if scenario_catalog_id is None:
        return []
    items = _table(bind, "scenario_catalog_items")
    rows = bind.execute(
        sa.select(items).where(items.c.scenario_catalog_id == scenario_catalog_id)
    ).mappings()
    return [dict(row) for row in rows]


def _catalog_item_for_resource(
    catalog_items: list[dict[str, Any]],
    *,
    target_type: str,
    resource_code: str,
    model_id: int | None,
) -> dict[str, Any] | None:
    candidates = [
        item
        for item in catalog_items
        if item["target_type"] == target_type
    ]
    for item in candidates:
        if item["resource_code"] == resource_code:
            return item
    model_key = "sensor_model_id" if target_type == "SENSOR" else "actuator_model_id"
    matches = [item for item in candidates if item.get(model_key) == model_id]
    return matches[0] if len(matches) == 1 else None


def _insert_project_scenario(
    bind: sa.Connection,
    *,
    project_id: int,
    device_id: int,
    name: str,
    scenario_catalog_id: int | None,
) -> int:
    scenarios = _table(bind, "project_scenarios")
    existing = bind.execute(
        sa.select(scenarios.c.id)
        .where(
            scenarios.c.device_id == device_id,
            scenarios.c.retired_at.is_(None),
        )
        .order_by(scenarios.c.is_active.desc(), scenarios.c.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)

    projects = _table(bind, "aquaponics_systems")
    created_by = bind.execute(
        sa.select(projects.c.owner_user_id).where(projects.c.id == project_id)
    ).scalar_one_or_none()

    return int(
        bind.execute(
            sa.insert(scenarios)
            .values(
                public_id=uuid4(),
                aquaponics_system_id=project_id,
                device_id=device_id,
                name=name,
                description=None,
                is_active=True,
                source_scenario_catalog_id=scenario_catalog_id,
                cloned_from_scenario_id=None,
                created_by=created_by,
                updated_by=created_by,
                retired_at=None,
            )
            .returning(scenarios.c.id)
        ).scalar_one()
    )


def _insert_project_scenario_items(
    bind: sa.Connection,
    *,
    scenario_id: int,
    device_id: int,
) -> tuple[dict[int, int], dict[int, int]]:
    scenarios = _table(bind, "project_scenarios")
    items = _table(bind, "project_scenario_items")
    sensors = _table(bind, "sensors")
    actuators = _table(bind, "actuators")

    scenario_catalog_id = bind.execute(
        sa.select(scenarios.c.source_scenario_catalog_id).where(
            scenarios.c.id == scenario_id
        )
    ).scalar_one_or_none()
    catalog_items = _catalog_items_for_scenario(bind, scenario_catalog_id)

    sensor_item_ids: dict[int, int] = {}
    sensor_rows = bind.execute(
        sa.select(sensors).where(
            sensors.c.device_id == device_id,
            sensors.c.is_deleted.is_(False),
        )
    ).mappings()
    for row in sensor_rows:
        source_item = _catalog_item_for_resource(
            catalog_items,
            target_type="SENSOR",
            resource_code=str(row["code"]),
            model_id=row["sensor_model_id"],
        )
        existing = bind.execute(
            sa.select(items.c.id).where(
                items.c.project_scenario_id == scenario_id,
                items.c.sensor_id == row["id"],
                items.c.retired_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = bind.execute(
                sa.insert(items)
                .values(
                    public_id=uuid4(),
                    project_scenario_id=scenario_id,
                    target_type="SENSOR",
                    sensor_id=row["id"],
                    actuator_id=None,
                    name=row["name"],
                    is_enabled=bool(row["is_enabled"]),
                    source_scenario_catalog_item_id=(
                        source_item["id"] if source_item else None
                    ),
                    notes=None,
                    retired_at=None,
                )
                .returning(items.c.id)
            ).scalar_one()
        sensor_item_ids[int(row["id"])] = int(existing)

    actuator_item_ids: dict[int, int] = {}
    actuator_rows = bind.execute(
        sa.select(actuators).where(
            actuators.c.device_id == device_id,
            actuators.c.is_deleted.is_(False),
        )
    ).mappings()
    for row in actuator_rows:
        source_item = _catalog_item_for_resource(
            catalog_items,
            target_type="ACTUATOR",
            resource_code=str(row["code"]),
            model_id=row["actuator_model_id"],
        )
        existing = bind.execute(
            sa.select(items.c.id).where(
                items.c.project_scenario_id == scenario_id,
                items.c.actuator_id == row["id"],
                items.c.retired_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = bind.execute(
                sa.insert(items)
                .values(
                    public_id=uuid4(),
                    project_scenario_id=scenario_id,
                    target_type="ACTUATOR",
                    sensor_id=None,
                    actuator_id=row["id"],
                    name=row["name"],
                    is_enabled=bool(row["is_enabled"]),
                    source_scenario_catalog_item_id=(
                        source_item["id"] if source_item else None
                    ),
                    notes=None,
                    retired_at=None,
                )
                .returning(items.c.id)
            ).scalar_one()
        actuator_item_ids[int(row["id"])] = int(existing)

    return sensor_item_ids, actuator_item_ids


def _catalog_rule_lineage(
    code: str,
    *,
    scenario_catalog_id: int | None,
    catalog_items: list[dict[str, Any]],
) -> tuple[int | None, str | None]:
    if scenario_catalog_id is None:
        return None, None
    for item in catalog_items:
        prefix = f"CATALOG_{scenario_catalog_id}_{item['id']}_"
        if not code.startswith(prefix):
            continue
        remainder = code[len(prefix) :]
        branches = item.get("branches") or []
        branch_keys = sorted(
            (
                str(branch.get("key"))
                for branch in branches
                if branch.get("key") is not None
            ),
            key=len,
            reverse=True,
        )
        for branch_key in branch_keys:
            if remainder == branch_key or remainder.startswith(branch_key + "_"):
                return int(item["id"]), branch_key
    return None, None


def _runtime_rule_bindings(
    bind: sa.Connection, *, device_id: int
) -> dict[int, list[tuple[str, int, bool, dict[str, Any]]]]:
    sensor_overrides = _table(bind, "alert_rule_sensor_overrides")
    actuator_overrides = _table(bind, "alert_rule_actuator_overrides")
    sensors = _table(bind, "sensors")
    actuators = _table(bind, "actuators")

    bindings: dict[int, list[tuple[str, int, bool, dict[str, Any]]]] = defaultdict(list)

    for row in bind.execute(
        sa.select(
            sensor_overrides.c.rule_id,
            sensor_overrides.c.sensor_id,
            sensor_overrides.c.is_enabled,
            sensor_overrides.c.config,
        )
        .join(sensors, sensors.c.id == sensor_overrides.c.sensor_id)
        .where(sensors.c.device_id == device_id)
    ).mappings():
        bindings[int(row["rule_id"])].append(
            (
                "SENSOR",
                int(row["sensor_id"]),
                bool(row["is_enabled"]),
                dict(row["config"] or {}),
            )
        )

    for row in bind.execute(
        sa.select(
            actuator_overrides.c.rule_id,
            actuator_overrides.c.actuator_id,
            actuator_overrides.c.is_enabled,
            actuator_overrides.c.config,
        )
        .join(actuators, actuators.c.id == actuator_overrides.c.actuator_id)
        .where(actuators.c.device_id == device_id)
    ).mappings():
        bindings[int(row["rule_id"])].append(
            (
                "ACTUATOR",
                int(row["actuator_id"]),
                bool(row["is_enabled"]),
                dict(row["config"] or {}),
            )
        )

    return bindings


def _project_override_config(
    bind: sa.Connection, *, rule_id: int, project_id: int
) -> tuple[bool, dict[str, Any]]:
    overrides = _table(bind, "alert_rule_project_overrides")
    row = bind.execute(
        sa.select(overrides.c.is_enabled, overrides.c.config).where(
            overrides.c.rule_id == rule_id,
            overrides.c.aquaponics_system_id == project_id,
        )
    ).mappings().first()
    if row is None:
        return True, {}
    return bool(row["is_enabled"]), dict(row["config"] or {})


def _migrate_runtime_rule_branches(
    bind: sa.Connection,
    *,
    project_id: int,
    device_id: int,
    scenario_id: int,
    sensor_item_ids: dict[int, int],
    actuator_item_ids: dict[int, int],
) -> set[tuple[str, int, str]]:
    rules = _table(bind, "alert_rules")
    revisions = _table(bind, "alert_rule_revisions")
    branches = _table(bind, "project_scenario_branches")
    scenarios = _table(bind, "project_scenarios")

    scenario_catalog_id = bind.execute(
        sa.select(scenarios.c.source_scenario_catalog_id).where(
            scenarios.c.id == scenario_id
        )
    ).scalar_one_or_none()
    catalog_items = _catalog_items_for_scenario(bind, scenario_catalog_id)

    bindings = _runtime_rule_bindings(bind, device_id=device_id)
    migrated: set[tuple[str, int, str]] = set()

    for rule_id, resource_bindings in bindings.items():
        unique_targets = {(target, resource_id) for target, resource_id, _, _ in resource_bindings}
        if len(unique_targets) != 1:
            raise RuntimeError(f"V1_SCENARIO_SYNC_AMBIGUOUS_RULE:{rule_id}")

        rule = bind.execute(
            sa.select(rules).where(
                rules.c.id == rule_id,
                rules.c.retired_at.is_(None),
            )
        ).mappings().first()
        if rule is None or rule["current_revision_id"] is None:
            continue

        target_type, resource_id, binding_enabled, resource_config = resource_bindings[0]
        if str(rule["target_type"]) != target_type:
            raise RuntimeError(f"V1_SCENARIO_SYNC_AMBIGUOUS_RULE:{rule_id}")

        item_id = (
            sensor_item_ids.get(resource_id)
            if target_type == "SENSOR"
            else actuator_item_ids.get(resource_id)
        )
        if item_id is None:
            continue

        revision = bind.execute(
            sa.select(revisions).where(
                revisions.c.id == rule["current_revision_id"]
            )
        ).mappings().first()
        if revision is None:
            continue

        project_enabled, project_config = _project_override_config(
            bind, rule_id=rule_id, project_id=project_id
        )
        condition_config = dict(revision["condition_config"] or {})
        condition_config.update(project_config)
        condition_config.update(resource_config)
        duration_seconds = int(condition_config.pop("duration_seconds", 0) or 0)

        source_item_id, catalog_branch_key = _catalog_rule_lineage(
            str(rule["code"]),
            scenario_catalog_id=scenario_catalog_id,
            catalog_items=catalog_items,
        )
        branch_key = catalog_branch_key or f"USER_RULE_{rule_id}"

        existing = bind.execute(
            sa.select(branches.c.id).where(
                branches.c.project_scenario_item_id == item_id,
                branches.c.branch_key == branch_key,
                branches.c.retired_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is None:
            bind.execute(
                sa.insert(branches).values(
                    public_id=uuid4(),
                    project_scenario_item_id=item_id,
                    branch_key=branch_key,
                    name=str(rule["name"]),
                    evaluator_type=str(rule["evaluator_type"]),
                    condition_config=condition_config,
                    duration_seconds=duration_seconds,
                    business_risk_level=str(revision["business_risk_level"]),
                    message_template=revision["message_template"],
                    consequence=revision["consequence"],
                    recommended_action=revision["recommended_action"],
                    is_enabled=(
                        bool(rule["is_enabled"])
                        and binding_enabled
                        and project_enabled
                    ),
                    position=int(revision["source_order"] or 0),
                    created_by=revision["created_by"],
                    updated_by=revision["created_by"],
                    retired_at=None,
                )
            )

        item_table = _table(bind, "project_scenario_items")
        if source_item_id is not None:
            bind.execute(
                sa.update(item_table)
                .where(item_table.c.id == item_id)
                .values(source_scenario_catalog_item_id=source_item_id)
            )

        migrated.add((target_type, resource_id, branch_key))

    return migrated


def _catalog_branch_duration(branch: dict[str, Any]) -> tuple[dict[str, Any], int]:
    condition = dict(branch.get("condition_config") or {})
    duration = branch.get("duration_seconds")
    if duration is None:
        duration = condition.pop("duration_seconds", 0)
    else:
        condition.pop("duration_seconds", None)
    return condition, int(duration or 0)


def _fill_missing_catalog_branches(
    bind: sa.Connection,
    *,
    scenario_id: int,
    scenario_catalog_id: int | None,
    sensor_item_ids: dict[int, int],
    actuator_item_ids: dict[int, int],
    migrated_branch_keys: set[tuple[str, int, str]],
) -> None:
    if scenario_catalog_id is None:
        return

    items_table = _table(bind, "project_scenario_items")
    branches_table = _table(bind, "project_scenario_branches")
    catalog_items = _catalog_items_for_scenario(bind, scenario_catalog_id)
    catalog_by_id = {int(item["id"]): item for item in catalog_items}

    runtime_items = bind.execute(
        sa.select(items_table).where(
            items_table.c.project_scenario_id == scenario_id,
            items_table.c.retired_at.is_(None),
        )
    ).mappings()

    for runtime_item in runtime_items:
        target_type = str(runtime_item["target_type"])
        resource_id = (
            int(runtime_item["sensor_id"])
            if target_type == "SENSOR"
            else int(runtime_item["actuator_id"])
        )
        source_item_id = runtime_item["source_scenario_catalog_item_id"]
        catalog_item = (
            catalog_by_id.get(int(source_item_id))
            if source_item_id is not None
            else None
        )
        if catalog_item is None or not bool(catalog_item["is_enabled"]):
            continue

        for position, branch in enumerate(catalog_item.get("branches") or []):
            if not branch.get("enabled", True):
                continue
            branch_key = str(branch["key"])
            identity = (target_type, resource_id, branch_key)
            if identity in migrated_branch_keys:
                continue

            exists = bind.execute(
                sa.select(branches_table.c.id).where(
                    branches_table.c.project_scenario_item_id
                    == runtime_item["id"],
                    branches_table.c.branch_key == branch_key,
                    branches_table.c.retired_at.is_(None),
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue

            condition_config, duration_seconds = _catalog_branch_duration(branch)
            bind.execute(
                sa.insert(branches_table).values(
                    public_id=uuid4(),
                    project_scenario_item_id=runtime_item["id"],
                    branch_key=branch_key,
                    name=str(branch.get("label") or branch_key),
                    evaluator_type=str(branch["evaluator_type"]),
                    condition_config=condition_config,
                    duration_seconds=duration_seconds,
                    business_risk_level=str(
                        branch.get("risk_level") or "MEDIUM"
                    ),
                    message_template=branch.get("message"),
                    consequence=branch.get("consequence"),
                    recommended_action=branch.get("recommended_action"),
                    is_enabled=True,
                    position=position,
                    created_by=None,
                    updated_by=None,
                    retired_at=None,
                )
            )


def _backfill_device(
    bind: sa.Connection,
    *,
    project_id: int,
    device_id: int,
    scenario_catalog_id: int | None,
    scenario_name: str,
) -> None:
    scenario_id = _insert_project_scenario(
        bind,
        project_id=project_id,
        device_id=device_id,
        name=scenario_name,
        scenario_catalog_id=scenario_catalog_id,
    )
    sensor_item_ids, actuator_item_ids = _insert_project_scenario_items(
        bind,
        scenario_id=scenario_id,
        device_id=device_id,
    )
    migrated_branch_keys = _migrate_runtime_rule_branches(
        bind,
        project_id=project_id,
        device_id=device_id,
        scenario_id=scenario_id,
        sensor_item_ids=sensor_item_ids,
        actuator_item_ids=actuator_item_ids,
    )
    _fill_missing_catalog_branches(
        bind,
        scenario_id=scenario_id,
        scenario_catalog_id=scenario_catalog_id,
        sensor_item_ids=sensor_item_ids,
        actuator_item_ids=actuator_item_ids,
        migrated_branch_keys=migrated_branch_keys,
    )


def _backfill_project_scenarios(bind: sa.Connection) -> int:
    projects = _table(bind, "aquaponics_systems")
    devices = _table(bind, "devices")
    catalogs = _table(bind, "scenario_catalogs")
    scenarios = _table(bind, "project_scenarios")

    catalog_names = {
        int(row["id"]): str(row["name"])
        for row in bind.execute(sa.select(catalogs.c.id, catalogs.c.name)).mappings()
    }

    created_before = int(
        bind.execute(sa.select(sa.func.count()).select_from(scenarios)).scalar_one()
    )

    rows = bind.execute(
        sa.select(
            projects.c.id.label("project_id"),
            projects.c.scenario_catalog_id,
            devices.c.id.label("device_id"),
        )
        .join(devices, devices.c.aquaponics_system_id == projects.c.id)
        .where(
            projects.c.is_deleted.is_(False),
            devices.c.is_deleted.is_(False),
        )
    ).mappings()
    for row in rows:
        catalog_id = row["scenario_catalog_id"]
        name = (
            catalog_names.get(int(catalog_id), "Kịch bản vận hành")
            if catalog_id is not None
            else "Kịch bản vận hành"
        )
        _backfill_device(
            bind,
            project_id=int(row["project_id"]),
            device_id=int(row["device_id"]),
            scenario_catalog_id=(
                int(catalog_id) if catalog_id is not None else None
            ),
            scenario_name=name,
        )

    created_after = int(
        bind.execute(sa.select(sa.func.count()).select_from(scenarios)).scalar_one()
    )
    return created_after - created_before


def _sync_v1_project_scenarios(bind: sa.Connection) -> int:
    _assert_v1_revision(bind)
    _ensure_v1_project_scenario_schema(bind)
    created = _backfill_project_scenarios(bind)
    _assert_v1_revision(bind)
    return created


async def sync_v1_project_scenarios() -> int:
    async with engine.begin() as connection:
        return await connection.run_sync(_sync_v1_project_scenarios)


async def _main() -> None:
    created = await sync_v1_project_scenarios()
    print(
        "V1_PROJECT_SCENARIO_SYNC_OK "
        f"created_scenarios={created} alembic_revision={V1_REVISION}"
    )


if __name__ == "__main__":
    asyncio.run(_main())
