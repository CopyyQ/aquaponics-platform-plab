from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError, ErrorDetail
from app.models.operational_alert import (
    AlertRule,
    AlertRuleActuatorOverride,
    AlertRuleRevision,
    AlertRuleSensorOverride,
    OperationalIncident,
)
from app.schemas.alert_scenario import AlertScenarioCreate, AlertScenarioUpdate
from app.services.alert_evaluators import validate_condition_config
from app.services.operational_incident_service import (
    ACTIVE_INCIDENT_STATUSES,
    enqueue_incident_notification,
)


def _condition(target_type: str, values: dict) -> tuple[str, dict]:
    duration = int(values.get("duration_seconds", 0))
    if target_type == "ACTUATOR":
        config = {"logic": "AND", "desired_state": values.get("desired_state"),
                  "reported_state": values.get("reported_state"),
                  "voltage": values.get("voltage"), "current": values.get("current"),
                  "duration_seconds": duration}
        evaluator = "MULTI_CONDITION"
    else:
        bounds = values.get("range")
        mode = values.get("range_mode")
        if bounds is None or mode not in {"INSIDE_RANGE", "OUTSIDE_RANGE"}:
            raise ApplicationError(
                "INVALID_SENSOR_SCENARIO",
                "Kịch bản Sensor cần khoảng và chế độ đánh giá rõ ràng",
                422,
            )
        config = {"range": bounds, "range_mode": mode, "duration_seconds": duration}
        evaluator = "RANGE_BANDS"
    errors = _validate_scenario(evaluator, config)
    if errors:
        raise ApplicationError(
            "INVALID_ALERT_SCENARIO",
            "Kịch bản cảnh báo chưa hợp lệ.",
            422,
            tuple(
                ErrorDetail(
                    field=str(field),
                    message="Giá trị không hợp lệ.",
                )
                for field in errors
            ),
        )
    return evaluator, config


def _validate_scenario(evaluator: str, config: dict) -> list[str]:
    if evaluator == "RANGE_BANDS":
        bounds = config["range"]
        return ["range"] if bounds.get("min") is None and bounds.get("max") is None else []
    return validate_condition_config(evaluator, config)


def scenario_read(rule: AlertRule, revision: AlertRuleRevision) -> dict:
    config = revision.condition_config
    return {"id": rule.public_id, "name": rule.name, "target_type": rule.target_type,
            "evaluator_type": rule.evaluator_type, "is_enabled": rule.is_enabled,
            "risk_level": revision.business_risk_level, "duration_seconds": int(config.get("duration_seconds", 0)),
            "message": revision.message_template, "consequence": revision.consequence,
            "recommended_action": revision.recommended_action, "condition": config,
            "created_at": rule.created_at, "updated_at": rule.updated_at}


async def create_scenario(db: AsyncSession, *, target_type: str, resource_id: int, payload: AlertScenarioCreate, actor_id: int) -> AlertRule:
    values = payload.model_dump()
    evaluator, config = _condition(target_type, values)
    rule = AlertRule(code=f"SCENARIO_{uuid4().hex.upper()}",
                     name=payload.name, target_type=target_type, evaluator_type=evaluator, is_enabled=payload.is_enabled)
    db.add(rule); await db.flush()
    revision = AlertRuleRevision(rule_id=rule.id, revision=1, business_risk_level=payload.risk_level,
        condition_config=config, message_template=payload.message, consequence=payload.consequence,
        recommended_action=payload.recommended_action, source_reference="User alert scenario", source_order=0,
        status="PUBLISHED", created_by=actor_id, published_by=actor_id, published_at=datetime.now(UTC))
    db.add(revision); await db.flush(); rule.current_revision_id = revision.id
    binding = AlertRuleSensorOverride(rule_id=rule.id, sensor_id=resource_id, config={}, is_enabled=True) if target_type == "SENSOR" else AlertRuleActuatorOverride(rule_id=rule.id, actuator_id=resource_id, config={}, is_enabled=True)
    db.add(binding); await db.flush(); return rule


async def get_scenario(db: AsyncSession, *, target_type: str, resource_id: int, public_id: UUID, include_retired: bool = False) -> tuple[AlertRule, AlertRuleRevision]:
    binding = AlertRuleSensorOverride if target_type == "SENSOR" else AlertRuleActuatorOverride
    resource_field = binding.sensor_id if target_type == "SENSOR" else binding.actuator_id
    query = select(AlertRule, AlertRuleRevision).join(binding, binding.rule_id == AlertRule.id).join(AlertRuleRevision, AlertRuleRevision.id == AlertRule.current_revision_id).where(AlertRule.public_id == public_id, AlertRule.target_type == target_type, resource_field == resource_id)
    if not include_retired: query = query.where(AlertRule.retired_at.is_(None))
    row = (await db.execute(query)).one_or_none()
    if row is None:
        raise ApplicationError(
            "ALERT_SCENARIO_NOT_FOUND",
            "Không tìm thấy kịch bản cảnh báo",
            404,
        )
    return row


async def list_scenarios(db: AsyncSession, *, target_type: str, resource_id: int) -> list[tuple[AlertRule, AlertRuleRevision]]:
    binding = AlertRuleSensorOverride if target_type == "SENSOR" else AlertRuleActuatorOverride
    resource_field = binding.sensor_id if target_type == "SENSOR" else binding.actuator_id
    return list((await db.execute(select(AlertRule, AlertRuleRevision).join(binding, binding.rule_id == AlertRule.id).join(AlertRuleRevision, AlertRuleRevision.id == AlertRule.current_revision_id).where(AlertRule.target_type == target_type, resource_field == resource_id, AlertRule.retired_at.is_(None)).order_by(AlertRule.created_at.desc()))).all())


async def update_scenario(db: AsyncSession, *, rule: AlertRule, current: AlertRuleRevision, payload: AlertScenarioUpdate, actor_id: int) -> AlertRuleRevision:
    changed_fields = payload.model_fields_set
    condition_fields = {"range_mode", "range", "desired_state", "reported_state", "voltage", "current"}
    if not (changed_fields & condition_fields):
        evaluator = rule.evaluator_type
        config = dict(current.condition_config)
        if "duration_seconds" in changed_fields and payload.duration_seconds is not None:
            config["duration_seconds"] = payload.duration_seconds
    else:
        values = {"duration_seconds": current.condition_config.get("duration_seconds", 0), **payload.model_dump(exclude_unset=True)}
        if rule.target_type == "ACTUATOR":
            values = {"desired_state": current.condition_config.get("desired_state"), "reported_state": current.condition_config.get("reported_state"), "voltage": current.condition_config.get("voltage"), "current": current.condition_config.get("current"), **values}
        else:
            values = {"range": current.condition_config.get("range"), "range_mode": current.condition_config.get("range_mode"), **values}
        evaluator, config = _condition(rule.target_type, values)
    rule.evaluator_type = evaluator
    if payload.name is not None: rule.name = payload.name
    if payload.is_enabled is not None: rule.is_enabled = payload.is_enabled
    revision = AlertRuleRevision(rule_id=rule.id, revision=current.revision + 1,
        business_risk_level=payload.risk_level or current.business_risk_level, condition_config=config,
        message_template=payload.message if "message" in payload.model_fields_set else current.message_template,
        consequence=payload.consequence if "consequence" in payload.model_fields_set else current.consequence,
        recommended_action=payload.recommended_action if "recommended_action" in payload.model_fields_set else current.recommended_action,
        source_reference="User alert scenario", source_order=0, status="PUBLISHED", created_by=actor_id,
        published_by=actor_id, published_at=datetime.now(UTC))
    db.add(revision); await db.flush(); rule.current_revision_id = revision.id; return revision


async def reconcile_disabled_scenario(db: AsyncSession, rule: AlertRule) -> None:
    now = datetime.now(UTC)
    incidents = (await db.scalars(select(OperationalIncident).where(OperationalIncident.rule_id == rule.id, OperationalIncident.status.in_(ACTIVE_INCIDENT_STATUSES)).with_for_update())).all()
    for incident in incidents:
        was_pending = incident.status == "PENDING"
        incident.status = "RESOLVED" if was_pending else "NORMALIZED"
        incident.normalized_at = now
        if not was_pending: await enqueue_incident_notification(db, incident, "RECOVERED")


async def retire_resource_scenarios(
    db: AsyncSession,
    *,
    target_type: str,
    resource_id: int,
) -> None:
    rows = await list_scenarios(
        db,
        target_type=target_type,
        resource_id=resource_id,
    )
    now = datetime.now(UTC)
    for rule, revision in rows:
        rule.is_enabled = False
        rule.retired_at = now
        revision.status = "RETIRED"
        await reconcile_disabled_scenario(db, rule)
    await db.flush()
