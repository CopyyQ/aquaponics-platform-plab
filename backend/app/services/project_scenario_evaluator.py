from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.models.actuator import Actuator
from app.models.device import Device
from app.models.operational_alert import OperationalIncident
from app.models.project import Project
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.telemetry import TelemetryReading
from app.services.alert_evaluators import EVALUATOR_REGISTRY, validate_condition_config
from app.services.measurement_quality import classify_measurement_quality
from app.services.operational_incident_service import (
    ACTIVE_INCIDENT_STATUSES,
    enqueue_incident_notification,
)


def _scenario_options():
    return selectinload(ProjectScenario.items).options(
        selectinload(ProjectScenarioItem.sensor),
        selectinload(ProjectScenarioItem.actuator),
        selectinload(ProjectScenarioItem.branches),
    )




async def device_uses_project_scenarios(
    db: AsyncSession,
    *,
    device_id: int,
) -> bool:
    return bool(
        await db.scalar(
            select(ProjectScenario.id)
            .where(
                ProjectScenario.device_id == device_id,
                ProjectScenario.retired_at.is_(None),
            )
            .limit(1)
        )
    )


async def _active_scenario(
    db: AsyncSession,
    *,
    device_id: int,
) -> ProjectScenario | None:
    return await db.scalar(
        select(ProjectScenario)
        .where(
            ProjectScenario.device_id == device_id,
            ProjectScenario.is_active.is_(True),
            ProjectScenario.retired_at.is_(None),
        )
        .options(_scenario_options())
    )


def _history_window_seconds(
    evaluator_type: str,
    config: dict[str, Any],
) -> int:
    if evaluator_type == "BASELINE_DEVIATION":
        value = config.get("window_seconds")
    elif evaluator_type in {"WINDOW_DURATION", "TREND"}:
        value = config.get("window_duration_seconds")
    else:
        value = None
    return max(0, int(value)) if value is not None else 0


async def _sensor_context(
    db: AsyncSession,
    *,
    sensor: Sensor,
    sensor_model: SensorModel,
    evaluator_type: str,
    config: dict[str, Any],
    value: float,
    quality: str,
    recorded_at: datetime,
    received_at: datetime,
) -> dict[str, Any]:
    freshness = (
        "FRESH"
        if received_at - recorded_at
        <= timedelta(seconds=settings.sensor_offline_seconds)
        else "STALE"
    )
    context: dict[str, Any] = {
        "value": value,
        "quality": quality,
        "freshness": freshness,
    }
    window_seconds = _history_window_seconds(evaluator_type, config)
    if window_seconds <= 0:
        return context

    readings = list(
        (
            await db.scalars(
                select(TelemetryReading)
                .where(
                    TelemetryReading.sensor_id == sensor.id,
                    TelemetryReading.recorded_at
                    >= recorded_at - timedelta(seconds=window_seconds),
                    TelemetryReading.recorded_at <= recorded_at,
                )
                .order_by(TelemetryReading.recorded_at, TelemetryReading.id)
            )
        ).all()
    )
    samples = [
        {
            "value": row.value,
            "quality": classify_measurement_quality(
                sensor_model.code, row.value
            )[0],
        }
        for row in readings
    ]
    context["samples"] = samples
    context["coverage_ratio"] = 1.0 if samples else 0.0
    return context


def _sensor_snapshot(
    *,
    project: Project,
    device: Device,
    sensor: Sensor,
    sensor_model: SensorModel,
    scenario: ProjectScenario,
    item: ProjectScenarioItem,
    branch: ProjectScenarioBranch,
    value: float,
    quality: str,
    recorded_at: datetime,
    received_at: datetime,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    condition = copy.deepcopy(branch.condition_config)
    runtime_state = {
        "value": value,
        "quality": quality,
        "recorded_at": recorded_at.isoformat(),
        "received_at": received_at.isoformat(),
    }
    return {
        "snapshot_version": 1,
        "scenario_id": str(scenario.public_id),
        "scenario_name": scenario.name,
        "item_id": str(item.public_id),
        "branch_id": str(branch.public_id),
        "branch_name": branch.name,
        "evaluator_type": branch.evaluator_type,
        "condition_config": condition,
        "business_risk_level": branch.business_risk_level,
        "message_template": branch.message_template,
        "message": branch.message_template,
        "consequence": branch.consequence,
        "recommended_action": branch.recommended_action,
        "recommended_actions": branch.recommended_action,
        "runtime_value_or_state": runtime_state,
        "resource_type": "SENSOR",
        "resource_name": sensor.name,
        "project_code": project.code,
        "project_name": project.name,
        "device_name": device.name,
        "device_code": device.code,
        "sensor_name": sensor.name,
        "sensor_code": sensor.code,
        "value": value,
        "unit": sensor_model.unit,
        "quality": quality,
        "freshness": (
            "FRESH"
            if received_at - recorded_at
            <= timedelta(seconds=settings.sensor_offline_seconds)
            else "STALE"
        ),
        "recorded_at": recorded_at.isoformat(),
        "received_at": received_at.isoformat(),
        **(copy.deepcopy(evidence) if evidence else {}),
    }


def _actuator_snapshot(
    *,
    project: Project,
    device: Device,
    actuator: Actuator,
    scenario: ProjectScenario,
    item: ProjectScenarioItem,
    branch: ProjectScenarioBranch,
    recorded_at: datetime,
    received_at: datetime,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    runtime_state = {
        "desired_state": actuator.desired_state,
        "reported_state": actuator.reported_state,
        "voltage_v": actuator.voltage_v,
        "current_a": actuator.current_a,
        "recorded_at": recorded_at.isoformat(),
        "received_at": received_at.isoformat(),
    }
    return {
        "snapshot_version": 1,
        "scenario_id": str(scenario.public_id),
        "scenario_name": scenario.name,
        "item_id": str(item.public_id),
        "branch_id": str(branch.public_id),
        "branch_name": branch.name,
        "evaluator_type": branch.evaluator_type,
        "condition_config": copy.deepcopy(branch.condition_config),
        "business_risk_level": branch.business_risk_level,
        "message_template": branch.message_template,
        "message": branch.message_template,
        "consequence": branch.consequence,
        "recommended_action": branch.recommended_action,
        "recommended_actions": branch.recommended_action,
        "runtime_value_or_state": runtime_state,
        "resource_type": "ACTUATOR",
        "resource_name": actuator.name,
        "project_code": project.code,
        "project_name": project.name,
        "device_name": device.name,
        "device_code": device.code,
        "actuator_name": actuator.name,
        "actuator_code": actuator.code,
        "desired_state": actuator.desired_state,
        "reported_state": actuator.reported_state,
        "voltage_v": actuator.voltage_v,
        "current_a": actuator.current_a,
        "recorded_at": recorded_at.isoformat(),
        "received_at": received_at.isoformat(),
        **(copy.deepcopy(evidence) if evidence else {}),
    }


async def _active_branch_incident(
    db: AsyncSession,
    *,
    branch_id: int,
) -> OperationalIncident | None:
    return await db.scalar(
        select(OperationalIncident)
        .where(
            OperationalIncident.project_scenario_branch_id == branch_id,
            OperationalIncident.status.in_(ACTIVE_INCIDENT_STATUSES),
        )
        .with_for_update()
    )


async def _transition_branch_incident(
    db: AsyncSession,
    *,
    project: Project,
    device: Device,
    scenario: ProjectScenario,
    item: ProjectScenarioItem,
    branch: ProjectScenarioBranch,
    sensor: Sensor | None,
    actuator: Actuator | None,
    active: bool,
    technical_severity: str,
    observed_at: datetime,
    snapshot: dict[str, Any] | None,
) -> OperationalIncident | None:
    incident = await _active_branch_incident(db, branch_id=branch.id)
    if not active:
        if incident is None:
            return None
        if incident.status == "PENDING":
            incident.status = "RESOLVED"
            incident.normalized_at = observed_at
            incident.resolved_at = observed_at
            incident.resolution_reason = "CONDITION_CLEARED"
        else:
            incident.status = "NORMALIZED"
            incident.normalized_at = observed_at
            incident.resolution_reason = "CONDITION_CLEARED"
            await enqueue_incident_notification(db, incident, "RECOVERED")
        return incident

    if snapshot is None:
        raise ApplicationError(
            "SCENARIO_EVALUATION_SNAPSHOT_MISSING",
            "Thiếu snapshot khi mở cảnh báo kịch bản",
            500,
            expose_message=False,
        )

    if incident is None:
        delayed = branch.duration_seconds > 0
        incident = OperationalIncident(
            project_id=project.id,
            rule_id=None,
            rule_revision_id=None,
            device_id=device.id,
            sensor_id=sensor.id if sensor is not None else None,
            actuator_id=actuator.id if actuator is not None else None,
            project_scenario_id=scenario.id,
            project_scenario_item_id=item.id,
            project_scenario_branch_id=branch.id,
            context_key=f"scenario_branch:{branch.id}",
            status="PENDING" if delayed else "OPEN",
            technical_severity=technical_severity,
            business_risk_level_snapshot=branch.business_risk_level,
            started_at=observed_at,
            opened_at=None if delayed else observed_at,
            last_triggered_at=observed_at,
            occurrence_count=1,
            trigger_snapshot=copy.deepcopy(snapshot),
        )
        try:
            async with db.begin_nested():
                db.add(incident)
                await db.flush()
        except IntegrityError:
            return await _active_branch_incident(db, branch_id=branch.id)
        if not delayed:
            await enqueue_incident_notification(db, incident, "OPEN")
        return incident

    incident.last_triggered_at = observed_at
    incident.occurrence_count += 1
    if (
        incident.status == "PENDING"
        and observed_at
        >= incident.started_at + timedelta(seconds=branch.duration_seconds)
    ):
        incident.status = "OPEN"
        incident.opened_at = observed_at
        await enqueue_incident_notification(db, incident, "OPEN")
    return incident


async def evaluate_active_sensor_scenario(
    db: AsyncSession,
    *,
    device: Device,
    sensor: Sensor,
    value: float,
    quality: str,
    recorded_at: datetime,
    received_at: datetime,
) -> list[OperationalIncident]:
    scenario = await _active_scenario(db, device_id=device.id)
    if scenario is None:
        return []
    item = next(
        (
            row
            for row in scenario.items
            if row.retired_at is None
            and row.target_type == "SENSOR"
            and row.sensor_id == sensor.id
        ),
        None,
    )
    if item is None:
        return []

    project = await db.get(Project, device.project_id)
    sensor_model = await db.get(SensorModel, sensor.sensor_model_id)
    if project is None or sensor_model is None:
        return []

    changed: list[OperationalIncident] = []
    for branch in item.branches:
        if branch.retired_at is not None:
            continue
        errors = validate_condition_config(
            branch.evaluator_type, branch.condition_config
        )
        if errors:
            raise ApplicationError(
                "SCENARIO_BRANCH_INVALID",
                f"Nhánh {branch.name} chưa hợp lệ: {', '.join(errors)}",
                422,
            )

        branch_active = bool(item.is_enabled and branch.is_enabled)
        result = None
        if branch_active:
            context = await _sensor_context(
                db,
                sensor=sensor,
                sensor_model=sensor_model,
                evaluator_type=branch.evaluator_type,
                config=branch.condition_config,
                value=value,
                quality=quality,
                recorded_at=recorded_at,
                received_at=received_at,
            )
            result = EVALUATOR_REGISTRY[branch.evaluator_type].evaluate(
                branch.condition_config,
                context,
            )
            branch_active = result.active

        snapshot = (
            _sensor_snapshot(
                project=project,
                device=device,
                sensor=sensor,
                sensor_model=sensor_model,
                scenario=scenario,
                item=item,
                branch=branch,
                value=value,
                quality=quality,
                recorded_at=recorded_at,
                received_at=received_at,
                evidence=result.evidence if result is not None else None,
            )
            if branch_active
            else None
        )
        incident = await _transition_branch_incident(
            db,
            project=project,
            device=device,
            scenario=scenario,
            item=item,
            branch=branch,
            sensor=sensor,
            actuator=None,
            active=branch_active,
            technical_severity=(
                result.severity
                if result is not None and result.severity
                else "WARNING"
            ),
            observed_at=received_at,
            snapshot=snapshot,
        )
        if incident is not None:
            changed.append(incident)
    return changed


async def evaluate_active_actuator_scenario(
    db: AsyncSession,
    *,
    device: Device,
    actuator: Actuator,
    recorded_at: datetime,
    received_at: datetime,
) -> list[OperationalIncident]:
    scenario = await _active_scenario(db, device_id=device.id)
    if scenario is None:
        return []
    item = next(
        (
            row
            for row in scenario.items
            if row.retired_at is None
            and row.target_type == "ACTUATOR"
            and row.actuator_id == actuator.id
        ),
        None,
    )
    if item is None:
        return []
    project = await db.get(Project, device.project_id)
    if project is None:
        return []

    context = {
        "desired_state": actuator.desired_state,
        "reported_state": actuator.reported_state,
        "voltage_v": actuator.voltage_v,
        "current_a": actuator.current_a,
    }
    changed: list[OperationalIncident] = []
    for branch in item.branches:
        if branch.retired_at is not None:
            continue
        errors = validate_condition_config(
            branch.evaluator_type, branch.condition_config
        )
        if errors:
            raise ApplicationError(
                "SCENARIO_BRANCH_INVALID",
                f"Nhánh {branch.name} chưa hợp lệ: {', '.join(errors)}",
                422,
            )

        branch_active = bool(item.is_enabled and branch.is_enabled)
        result = None
        if branch_active:
            result = EVALUATOR_REGISTRY[branch.evaluator_type].evaluate(
                branch.condition_config,
                context,
            )
            branch_active = result.active

        snapshot = (
            _actuator_snapshot(
                project=project,
                device=device,
                actuator=actuator,
                scenario=scenario,
                item=item,
                branch=branch,
                recorded_at=recorded_at,
                received_at=received_at,
                evidence=result.evidence if result is not None else None,
            )
            if branch_active
            else None
        )
        incident = await _transition_branch_incident(
            db,
            project=project,
            device=device,
            scenario=scenario,
            item=item,
            branch=branch,
            sensor=None,
            actuator=actuator,
            active=branch_active,
            technical_severity=(
                result.severity
                if result is not None and result.severity
                else "WARNING"
            ),
            observed_at=received_at,
            snapshot=snapshot,
        )
        if incident is not None:
            changed.append(incident)
    return changed


async def resolve_scenario_incidents(
    db: AsyncSession,
    *,
    scenario_id: int,
    reason: str,
    resolved_at: datetime,
    enqueue_recovery: bool = False,
) -> int:
    incidents = list(
        (
            await db.scalars(
                select(OperationalIncident)
                .where(
                    OperationalIncident.project_scenario_id == scenario_id,
                    OperationalIncident.status.in_(ACTIVE_INCIDENT_STATUSES),
                )
                .with_for_update()
            )
        ).all()
    )
    for incident in incidents:
        prior_status = incident.status
        incident.status = "RESOLVED"
        incident.normalized_at = resolved_at
        incident.resolved_at = resolved_at
        incident.resolution_reason = reason
        if enqueue_recovery and prior_status != "PENDING":
            await enqueue_incident_notification(db, incident, "RECOVERED")
    return len(incidents)


async def resolve_resource_scenario_incidents(
    db: AsyncSession,
    *,
    sensor_id: int | None,
    actuator_id: int | None,
    reason: str,
    resolved_at: datetime,
) -> int:
    if (sensor_id is None) == (actuator_id is None):
        raise ValueError("Exactly one runtime resource id is required")
    filters = [
        OperationalIncident.project_scenario_id.is_not(None),
        OperationalIncident.status.in_(ACTIVE_INCIDENT_STATUSES),
    ]
    filters.append(
        OperationalIncident.sensor_id == sensor_id
        if sensor_id is not None
        else OperationalIncident.actuator_id == actuator_id
    )
    incidents = list(
        (
            await db.scalars(
                select(OperationalIncident)
                .where(*filters)
                .with_for_update()
            )
        ).all()
    )
    for incident in incidents:
        incident.status = "RESOLVED"
        incident.normalized_at = resolved_at
        incident.resolved_at = resolved_at
        incident.resolution_reason = reason
    return len(incidents)


async def _latest_sensor_reading(
    db: AsyncSession,
    sensor_id: int,
) -> TelemetryReading | None:
    return await db.scalar(
        select(TelemetryReading)
        .where(TelemetryReading.sensor_id == sensor_id)
        .order_by(
            TelemetryReading.recorded_at.desc(),
            TelemetryReading.id.desc(),
        )
        .limit(1)
    )


async def reevaluate_active_scenario_resources(
    db: AsyncSession,
    *,
    scenario: ProjectScenario,
    observed_at: datetime,
) -> tuple[int, int]:
    loaded = await db.scalar(
        select(ProjectScenario)
        .where(
            ProjectScenario.id == scenario.id,
            ProjectScenario.is_active.is_(True),
            ProjectScenario.retired_at.is_(None),
        )
        .options(_scenario_options())
    )
    if loaded is None:
        return 0, 0
    device = await db.get(Device, loaded.device_id)
    if device is None:
        return 0, 0

    sensor_count = 0
    actuator_count = 0
    for item in loaded.items:
        if item.retired_at is not None or not item.is_enabled:
            continue
        if item.target_type == "SENSOR" and item.sensor is not None:
            reading = await _latest_sensor_reading(db, item.sensor.id)
            if reading is None:
                continue
            model = await db.get(SensorModel, item.sensor.sensor_model_id)
            if model is None:
                continue
            quality = classify_measurement_quality(model.code, reading.value)[0]
            await evaluate_active_sensor_scenario(
                db,
                device=device,
                sensor=item.sensor,
                value=reading.value,
                quality=quality,
                recorded_at=reading.recorded_at,
                received_at=observed_at,
            )
            sensor_count += 1
        elif item.target_type == "ACTUATOR" and item.actuator is not None:
            recorded_at = (
                item.actuator.electrical_recorded_at
                or item.actuator.reported_state_at
                or observed_at
            )
            await evaluate_active_actuator_scenario(
                db,
                device=device,
                actuator=item.actuator,
                recorded_at=recorded_at,
                received_at=observed_at,
            )
            actuator_count += 1
    return sensor_count, actuator_count


async def reconcile_changed_branch(
    db: AsyncSession,
    *,
    branch: ProjectScenarioBranch,
    before_condition: dict[str, Any],
    before_evaluator_type: str,
    before_duration_seconds: int,
    changed_at: datetime,
) -> None:
    del before_condition, before_evaluator_type, before_duration_seconds

    incident = await _active_branch_incident(db, branch_id=branch.id)
    if incident is not None:
        incident.status = "RESOLVED"
        incident.normalized_at = changed_at
        incident.resolved_at = changed_at
        incident.resolution_reason = "SCENARIO_CONFIGURATION_CHANGED"

    item = await db.scalar(
        select(ProjectScenarioItem)
        .where(ProjectScenarioItem.id == branch.project_scenario_item_id)
        .options(
            selectinload(ProjectScenarioItem.sensor),
            selectinload(ProjectScenarioItem.actuator),
        )
    )
    if item is None or item.retired_at is not None or not item.is_enabled:
        return
    scenario = await db.get(ProjectScenario, item.project_scenario_id)
    if (
        scenario is None
        or not scenario.is_active
        or scenario.retired_at is not None
        or not branch.is_enabled
    ):
        return
    device = await db.get(Device, scenario.device_id)
    if device is None:
        return

    if item.target_type == "SENSOR" and item.sensor is not None:
        reading = await _latest_sensor_reading(db, item.sensor.id)
        if reading is None:
            return
        model = await db.get(SensorModel, item.sensor.sensor_model_id)
        if model is None:
            return
        quality = classify_measurement_quality(model.code, reading.value)[0]
        await evaluate_active_sensor_scenario(
            db,
            device=device,
            sensor=item.sensor,
            value=reading.value,
            quality=quality,
            recorded_at=reading.recorded_at,
            received_at=changed_at,
        )
    elif item.target_type == "ACTUATOR" and item.actuator is not None:
        await evaluate_active_actuator_scenario(
            db,
            device=device,
            actuator=item.actuator,
            recorded_at=(
                item.actuator.electrical_recorded_at
                or item.actuator.reported_state_at
                or changed_at
            ),
            received_at=changed_at,
        )
