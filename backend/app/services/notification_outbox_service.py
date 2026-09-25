from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.actuator import Actuator
from app.models.device import Device
from app.models.operational_alert import (
    NotificationDelivery,
    NotificationOutbox,
    OperationalIncident,
)
from app.models.project_settings import (
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)
from app.models.telemetry import TelemetryReading
from app.services.telegram_notifier import TelegramNotifier

RISK_LABELS = {"EXTREME": "CỰC CAO", "VERY_HIGH": "RẤT CAO", "HIGH": "CAO", "MEDIUM": "TRUNG BÌNH", "LOW_MEDIUM": "THẤP–TRUNG BÌNH", "LOW": "THẤP"}
QUALITY_LABELS = {"VALID": "Hợp lệ", "OUT_OF_RANGE": "Ngoài phạm vi", "INVALID": "Không hợp lệ", "UNVALIDATED": "Chưa được xác thực", "STALE": "Dữ liệu cũ", "NO_DATA": "Không có dữ liệu"}
COMMAND_LABELS = {"ACKNOWLEDGED": "Đã xác nhận", "FAILED": "Thất bại", "TIMEOUT": "Hết thời gian chờ", "PUBLISHED": "Đã gửi lệnh", "PENDING": "Đang chờ gửi"}
OPERATOR_LABELS = {"LT": "<", "LTE": "≤", "GT": ">", "GTE": "≥", "EQ": "=", "OUTSIDE": "ngoài"}

TELEGRAM_PUSH_INCIDENT_EVENTS = {"OPEN", "RECOVERED"}


def telegram_action_keyboard(project_id: int) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "🚨 Cảnh báo hiện tại", "callback_data": f"a:{project_id}"},
            {"text": "📊 Tình trạng hệ thống", "callback_data": f"s:{project_id}"},
        ]]
    }


def _event_heading(event: str, risk: str, *, canonical: bool) -> str:
    label = RISK_LABELS.get(risk, risk)
    heading = {
        "OPEN": f"🔴 CẢNH BÁO MỚI — MỨC ĐỘ {label}",
        "ACTIVE_SYNC": f"🟠 ĐỒNG BỘ CẢNH BÁO ĐANG HOẠT ĐỘNG — MỨC ĐỘ {label}",
        "ESCALATED": f"🔴 CẢNH BÁO ĐÃ TĂNG MỨC ĐỘ — {label}",
        "REMINDER": f"⏰ NHẮC LẠI CẢNH BÁO — MỨC ĐỘ {label}",
        "RECOVERED": "✅ ĐÃ TRỞ VỀ BÌNH THƯỜNG",
        "RESOLVED": "✅ CẢNH BÁO ĐÃ ĐƯỢC XỬ LÝ",
    }.get(event, f"🔴 CẢNH BÁO — MỨC ĐỘ {label}")
    return f"{heading} — HỆ THỐNG AQUAPONICS" if canonical else heading


def _number(value: object, digits: int = 3) -> str:
    if not isinstance(value, (float, int)):
        return "—"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".").replace(".", ",")


def _display_datetime(value: object) -> str:
    if not isinstance(value, str):
        return "—"
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(ZoneInfo(settings.display_timezone)).strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, TypeError):
        return value


def _duration(value: object) -> str:
    seconds = max(0, int(value)) if isinstance(value, (float, int)) else 0
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days} ngày")
    if hours:
        parts.append(f"{hours} giờ")
    if minutes:
        parts.append(f"{minutes} phút")
    if seconds or not parts:
        parts.append(f"{seconds} giây")
    return " ".join(parts)




def _scenario_condition_text(payload: dict) -> str:
    config = payload.get("condition_config")
    if not isinstance(config, dict):
        return "—"

    operator = str(config.get("operator") or "").upper()
    if isinstance(config.get("value"), (float, int)) and operator:
        symbol = OPERATOR_LABELS.get(operator, operator)
        unit = str(payload.get("unit") or "").strip()
        return f"{symbol} {_number(config['value'])} {unit}".strip()

    minimum = config.get("min")
    maximum = config.get("max")
    if isinstance(minimum, (float, int)) or isinstance(maximum, (float, int)):
        unit = str(payload.get("unit") or "").strip()
        if isinstance(minimum, (float, int)) and isinstance(maximum, (float, int)):
            return f"{_number(minimum)} – {_number(maximum)} {unit}".strip()
        if isinstance(minimum, (float, int)):
            return f"≥ {_number(minimum)} {unit}".strip()
        return f"≤ {_number(maximum)} {unit}".strip()

    conditions: list[str] = []
    desired = config.get("desired_state")
    reported = config.get("reported_state")
    if isinstance(desired, bool):
        conditions.append(f"Yêu cầu={'Bật' if desired else 'Tắt'}")
    if isinstance(reported, bool):
        conditions.append(f"Báo về={'Bật' if reported else 'Tắt'}")
    for field, label, unit in (
        ("voltage", "Điện áp", "V"),
        ("current", "Dòng điện", "A"),
    ):
        value = config.get(field)
        if not isinstance(value, dict):
            continue
        op = str(value.get("operator") or "").upper()
        threshold = value.get("value")
        if op and isinstance(threshold, (float, int)):
            conditions.append(
                f"{label} {OPERATOR_LABELS.get(op, op)} {_number(threshold)} {unit}"
            )
    return "; ".join(conditions) if conditions else "—"


_WORKBOOK_SCENARIO_NAME = "Kịch bản vận hành Aquaponics"
_WORKBOOK_RESOURCE_LABELS = {
    "AERATION_PUMP": "THIẾT BỊ CHẤP HÀNH - Máy sủi Oxy",
    "FISH_TANK_PUMP": "THIẾT BỊ CHẤP HÀNH - Bơm bể cá",
    "BIOFILTER_PUMP": "THIẾT BỊ CHẤP HÀNH - Bơm tưới giàn",
    "GROW_LIGHT": "THIẾT BỊ CHẤP HÀNH - Đèn chiếu sáng",
    "WATER_LEVEL": "CẢM BIẾN - Mức nước bể lọc vi sinh",
    "WATER_LEVELW2": "CẢM BIẾN - Mức nước bể cá",
    "PH": "CẢM BIẾN - Mức pH của bể cá",
    "WATER_TEMPERATURE": "CẢM BIẾN - Nhiệt độ nước trong bể cá",
    "TDS": "CẢM BIẾN - Nồng độ dinh dưỡng",
}
_WORKBOOK_ACTUATOR_CODES = {
    "AERATION_PUMP",
    "FISH_TANK_PUMP",
    "BIOFILTER_PUMP",
    "GROW_LIGHT",
}
_WORKBOOK_WATER_LEVEL_CONSEQUENCE = (
    "Gây hại cho hệ vi sinh trong bể, và lưu lượng nước vi sinh không tuần hoàn "
    "lên Giàn CẦN KHẮC PHỤC trong 3h tới."
)


def _scenario_resource_code(payload: dict) -> str:
    return str(
        payload.get("sensor_code") or payload.get("actuator_code") or ""
    ).strip().upper()


def _scenario_operator(payload: dict) -> str:
    config = payload.get("condition_config")
    if isinstance(config, dict):
        operator = config.get("operator")
        if operator:
            return str(operator).upper()
        range_config = config.get("range")
        value = payload.get("value")
        if isinstance(range_config, dict) and isinstance(value, (float, int)):
            minimum = range_config.get("min")
            maximum = range_config.get("max")
            if isinstance(minimum, (float, int)) and value < minimum:
                return "LT"
            if isinstance(maximum, (float, int)) and value > maximum:
                return "GT"
    return str(payload.get("operator") or "").upper()


def _workbook_action_lines(payload: dict) -> list[str]:
    value = payload.get("recommended_action") or payload.get("recommended_actions")
    raw_lines: list[str] = []
    if isinstance(value, str):
        raw_lines = value.splitlines()
    elif isinstance(value, list):
        raw_lines = [str(item) for item in value]

    lines: list[str] = []
    for raw in raw_lines:
        item = raw.strip()
        if not item:
            continue
        if item.startswith("-"):
            item = item[1:].strip()
        item = item.rstrip("/").strip()
        if item:
            lines.append(f"- {item}")
    return lines


def _format_aquaponics_workbook_scenario_message(payload: dict) -> str | None:
    if str(payload.get("scenario_name") or "") != _WORKBOOK_SCENARIO_NAME:
        return None

    code = _scenario_resource_code(payload)
    resource_label = _WORKBOOK_RESOURCE_LABELS.get(code)
    if resource_label is None:
        return None

    lines = [
        "TÌNH TRẠNG HỆ THỐNG",
        f"DỰ ÁN: {payload.get('project_name', '—')}",
        resource_label,
        "LỖI BẤT THƯỜNG",
    ]

    if code in _WORKBOOK_ACTUATOR_CODES:
        state = payload.get("reported_state")
        if not isinstance(state, bool):
            state = payload.get("desired_state")
        lines.extend(
            [
                f"Trạng thái: {'Bật' if state is True else 'Tắt' if state is False else '—'}",
                f"Điện áp: {_number(payload.get('voltage_v'))} VDC",
                f"Dòng điện: {_number(payload.get('current_a'))} A",
            ]
        )
    elif code == "PH":
        direction = "dưới" if _scenario_operator(payload) in {"LT", "LTE"} else "trên"
        lines.append(
            f"Giá trị pH: {_number(payload.get('value'))} - Vượt ngưỡng {direction}"
        )
    elif code == "WATER_TEMPERATURE":
        direction = "dưới" if _scenario_operator(payload) in {"LT", "LTE"} else "trên"
        lines.append(
            f"Giá trị nhiệt độ: {_number(payload.get('value'))} - Vượt ngưỡng {direction}"
        )
    elif code == "TDS":
        lines.append(
            f"Giá trị dinh dưỡng: {_number(payload.get('value'))} - Vượt ngưỡng dưới"
        )
    elif code in {"WATER_LEVEL", "WATER_LEVELW2"}:
        tank = "bể cá" if code == "WATER_LEVELW2" else "bể lọc vi sinh"
        lines.extend(
            [
                "Trạng thái: Bật",
                f"Mức nước {tank} THẤP: {_number(payload.get('value'))}%",
            ]
        )

    lines.append(
        f"Thời gian: {_display_datetime(payload.get('recorded_at') or payload.get('started_at'))}"
    )

    consequence = (
        _WORKBOOK_WATER_LEVEL_CONSEQUENCE
        if code in {"WATER_LEVEL", "WATER_LEVELW2"}
        else str(payload.get("consequence") or "").strip()
    )
    if consequence:
        lines.append(f"Ảnh hưởng: {consequence}")

    actions = _workbook_action_lines(payload)
    if actions:
        lines.append("Khắc phục:")
        lines.extend(actions)
    return "\n".join(lines)


def format_project_scenario_message(payload: dict) -> str:
    event = str(payload.get("event_type") or "OPEN")
    risk = str(payload.get("business_risk_level") or "MEDIUM")
    resource = str(
        payload.get("resource_name")
        or payload.get("sensor_name")
        or payload.get("actuator_name")
        or "Thiết bị"
    )
    lines = [
        _event_heading(event, risk, canonical=False),
        "",
        f"Hệ thống Aquaponics: {payload.get('project_name', '—')}",
        f"Thiết bị: {payload.get('device_name', '—')}",
        f"Kịch bản: {payload.get('scenario_name', '—')}",
        f"Nhánh: {payload.get('branch_name', '—')}",
        f"Nguồn: {resource}",
        f"Điều kiện: {_scenario_condition_text(payload)}",
    ]
    if payload.get("value") is not None:
        lines.append(
            f"Giá trị: {_number(payload['value'])} {payload.get('unit') or ''}".strip()
        )
    if payload.get("reported_state") is not None:
        lines.append(
            f"Trạng thái báo về: {'Bật' if payload['reported_state'] else 'Tắt'}"
        )
    if payload.get("desired_state") is not None:
        lines.append(
            f"Trạng thái yêu cầu: {'Bật' if payload['desired_state'] else 'Tắt'}"
        )
    if payload.get("voltage_v") is not None:
        lines.append(f"Điện áp: {_number(payload['voltage_v'])} V")
    if payload.get("current_a") is not None:
        lines.append(f"Dòng điện: {_number(payload['current_a'])} A")
    lines.extend(
        [
            f"Bắt đầu: {_display_datetime(payload.get('started_at'))}",
            f"Đã kéo dài: {_duration(payload.get('duration_seconds'))}",
        ]
    )
    message = str(
        payload.get("message_template") or payload.get("message") or ""
    ).strip()
    if message:
        lines.extend(["", message])
    if payload.get("consequence"):
        lines.extend(["", "Ảnh hưởng:", str(payload["consequence"])])
    action = payload.get("recommended_action") or payload.get("recommended_actions")
    if isinstance(action, str) and action.strip():
        lines.extend(["", "Khuyến nghị xử lý:", action.strip()])
    elif isinstance(action, list) and action:
        lines.extend(["", "Khuyến nghị xử lý:"])
        lines.extend(f"• {item}" for item in action)
    return "\n".join(lines)


def format_operational_message(payload: dict) -> str:
    if str(payload.get("event_type") or "OPEN") == "RECOVERED":
        return format_recovered_operational_message(payload)
    if payload.get("scenario_name") and payload.get("branch_name"):
        workbook_message = _format_aquaponics_workbook_scenario_message(payload)
        if workbook_message is not None:
            return workbook_message
        return format_project_scenario_message(payload)
    if payload.get("resource_type") and payload.get("metric_type"):
        return format_canonical_operational_message(payload)
    event = str(payload.get("event_type") or "OPEN")
    risk = str(payload.get("business_risk_level") or "MEDIUM")
    lines = [
        _event_heading(event, risk, canonical=False),
        "",
        f"Hệ thống Aquaponics: {payload.get('project_name', '—')}",
        f"Thiết bị: {payload.get('device_name', '—')}",
    ]
    if payload.get("sensor_name"):
        lines.append(f"Cảm biến: {payload['sensor_name']}")
    if payload.get("sensor_code"):
        lines.append(f"Mã cảm biến: {payload['sensor_code']}")
    unit = str(payload.get("unit") or "").strip()
    if isinstance(payload.get("lower"), (float, int)) and isinstance(payload.get("upper"), (float, int)):
        lines.append(f"Ngưỡng cảnh báo: < {_number(payload['lower'])} hoặc > {_number(payload['upper'])} {unit}".strip())
    elif isinstance(payload.get("threshold"), (float, int)):
        operator = OPERATOR_LABELS.get(payload.get("operator"), payload.get("operator") or "")
        lines.append(f"Ngưỡng cảnh báo: {operator} {_number(payload['threshold'])} {unit}".strip())
    lines.extend([
        f"Bắt đầu: {_display_datetime(payload.get('started_at'))}",
        f"Đã kéo dài: {_duration(payload.get('duration_seconds'))}",
    ])
    if payload.get("message"):
        lines.extend(["", str(payload["message"])])
    return "\n".join(lines)


def format_recovered_operational_message(payload: dict) -> str:
    resource = str(payload.get("resource_name") or payload.get("sensor_name") or payload.get("actuator_name") or "Thiết bị")
    lines = [
        "✅ ĐÃ TRỞ VỀ BÌNH THƯỜNG — HỆ THỐNG AQUAPONICS",
        "",
        f"HỆ THỐNG: {payload.get('project_name', '—')}",
        f"THIẾT BỊ: {payload.get('device_name', '—')}",
        f"NGUỒN: {resource}",
    ]
    if payload.get("value") is not None:
        lines.append(f"Giá trị hiện tại: {_number(payload['value'])} {payload.get('unit') or ''}".strip())
    if payload.get("voltage_v") is not None:
        lines.append(f"Điện áp hiện tại: {_number(payload['voltage_v'])} V")
    if payload.get("current_a") is not None:
        lines.append(f"Dòng điện hiện tại: {_number(payload['current_a'])} A")
    if payload.get("reported_state") is not None:
        lines.append(f"Trạng thái hiện tại: {'Bật' if payload['reported_state'] else 'Tắt'}")
    if isinstance(payload.get("lower"), (float, int)) and isinstance(payload.get("upper"), (float, int)):
        lines.append(f"Khoảng bình thường: {_number(payload['lower'])} – {_number(payload['upper'])} {payload.get('unit') or ''}".strip())
    elif payload.get("threshold") is not None:
        direction = str(payload.get("threshold_direction") or "")
        operator = "<" if direction == "BELOW" else ">" if direction == "ABOVE" else ""
        if not operator:
            scenario_operator = _scenario_operator(payload)
            operator = OPERATOR_LABELS.get(scenario_operator, scenario_operator)
        lines.append(
            f"Điều kiện cảnh báo trước đó: {operator} {_number(payload['threshold'])} "
            f"{payload.get('unit') or ''}".strip()
        )
    lines.append(f"Phục hồi lúc: {_display_datetime(payload.get('recorded_at'))}")
    lines.append(f"Sự cố kéo dài: {_duration(payload.get('duration_seconds'))}")
    return "\n".join(lines)


def format_canonical_operational_message(payload: dict) -> str:
    event = str(payload.get("event_type") or "OPEN")
    if event == "RECOVERED":
        return format_recovered_operational_message(payload)
    risk = str(payload.get("business_risk_level") or "MEDIUM")
    direction = str(payload.get("threshold_direction") or "")
    resource = str(payload.get("resource_name") or "Thiết bị")
    metric = str(payload.get("metric_type") or "").replace("_", " ")
    heading = _event_heading(event, risk, canonical=True)
    lines = [heading, "", f"MỨC ĐỘ: {RISK_LABELS.get(risk, risk)}", f"HỆ THỐNG: {payload.get('project_name', '—')}", f"THIẾT BỊ: {payload.get('device_name', '—')}", f"NGUỒN: {resource}"]
    if payload.get("title"):
        lines.extend(["", "SỰ CỐ:", str(payload["title"])])
    if metric:
        lines.append(f"Chỉ số: {metric}")
    if payload.get("value") is not None:
        lines.append(f"Giá trị: {_number(payload['value'])} {payload.get('unit') or ''}".strip())
    if payload.get("threshold") is not None:
        operator = "<" if direction == "BELOW" else ">" if direction == "ABOVE" else ""
        lines.append(f"Ngưỡng: {operator} {_number(payload['threshold'])} {payload.get('unit') or ''}".strip())
    if payload.get("voltage_v") is not None:
        lines.append(f"Điện áp: {_number(payload['voltage_v'])} V")
    if payload.get("current_a") is not None:
        lines.append(f"Dòng điện: {_number(payload['current_a'])} A")
    if payload.get("reported_state") is not None:
        lines.append(f"Trạng thái báo về: {'Bật' if payload['reported_state'] else 'Tắt'}")
    if payload.get("desired_state") is not None:
        lines.append(f"Trạng thái yêu cầu: {'Bật' if payload['desired_state'] else 'Tắt'}")
    lines.append(f"Thời gian: {_display_datetime(payload.get('recorded_at'))}")
    if payload.get("consequence"):
        lines.extend(["", "Ảnh hưởng:", str(payload["consequence"])])
    actions = payload.get("recommended_actions")
    if isinstance(actions, str) and actions.strip():
        lines.extend(["", "Khuyến nghị xử lý:", actions.strip()])
    elif isinstance(actions, list) and actions:
        lines.extend(["", "Khuyến nghị xử lý:"])
        lines.extend(f"• {item}" for item in actions)
    elif payload.get("recommended_action"):
        lines.extend(["", "Khuyến nghị xử lý:", str(payload["recommended_action"])])
    custom_message = str(payload.get("message") or "").strip()
    if custom_message and custom_message != str(payload.get("title") or "").strip():
        lines.extend(["", f"Ghi chú: {custom_message}"])
    return "\n".join(lines)


def format_project_activity_message(payload: dict) -> str:
    """Render an already snapshotted project activity event without live reads."""
    return str(payload.get("message") or "Thông báo hoạt động dự án")


async def resolve_notification_recipients(
    db: AsyncSession, *, project_id: int
) -> list[ProjectNotificationRecipient]:
    return list((await db.scalars(
        select(ProjectNotificationRecipient).where(
            ProjectNotificationRecipient.project_id == project_id,
            ProjectNotificationRecipient.enabled.is_(True),
        )
    )).all())


async def evaluate_notification_policy(
    db: AsyncSession, *, project_id: int, source_type: str, event_type: str, risk: str | None
) -> str | None:
    """Return a precise skip reason, or ``None`` when Telegram delivery is allowed.

    Risk remains incident metadata for operator context, but it no longer gates
    Telegram. OPEN is fixed behavior whenever the channel is enabled. RECOVERED
    is the only optional lifecycle message.
    """
    del risk
    settings = await db.scalar(
        select(ProjectNotificationSettings).where(
            ProjectNotificationSettings.project_id == project_id
        )
    )
    if settings is None:
        return "PROJECT_NOTIFICATION_NOT_CONFIGURED"
    if not settings.enabled:
        return "NOTIFICATIONS_DISABLED"
    if not settings.telegram_enabled:
        return "TELEGRAM_DISABLED"
    if source_type != "INCIDENT":
        return "INCIDENT_ONLY"
    if event_type == "OPEN":
        return None
    if event_type == "RECOVERED":
        return None if settings.notify_alert_recovered else "RECOVERY_DISABLED"
    return "EVENT_DISABLED"


async def enqueue_project_activity_notification(
    db: AsyncSession, *, project_id: int, activity_id: int, payload_snapshot: dict
) -> None:
    await db.execute(insert(NotificationOutbox).values(
        incident_id=None, project_id=project_id, source_type="PROJECT_ACTIVITY",
        event_type="PROJECT_ACTIVITY", idempotency_key=f"project-activity:{activity_id}",
        payload_snapshot={**payload_snapshot, "source_type": "PROJECT_ACTIVITY", "activity_id": activity_id},
        status="PENDING", available_at=datetime.now(UTC), attempt_count=0,
    ).on_conflict_do_nothing(index_elements=["idempotency_key"]))


async def enqueue_operational_event(
    db: AsyncSession, *, project_id: int, source_key: str, event_type: str, payload_snapshot: dict
) -> None:
    """Persist a non-threshold operational event for the common worker."""
    await db.execute(insert(NotificationOutbox).values(
        incident_id=None, project_id=project_id, source_type="SYSTEM_EVENT",
        event_type=event_type, idempotency_key=f"system-event:{source_key}",
        payload_snapshot={**payload_snapshot, "source_type": "SYSTEM_EVENT"},
        status="PENDING", available_at=datetime.now(UTC), attempt_count=0,
    ).on_conflict_do_nothing(index_elements=["idempotency_key"]))


def _payload_at_delivery(outbox: NotificationOutbox, incident: OperationalIncident, now: datetime) -> dict:
    """Return the immutable event snapshot plus delivery identity metadata.

    New outboxes snapshot all presentation fields when enqueued. The setdefault
    values retain compatibility for historical rows without allowing a later
    Incident trigger snapshot to rewrite an older event's content.
    """
    payload = dict(outbox.payload_snapshot or {})
    payload["incident_id"] = incident.id
    payload["event_type"] = outbox.event_type
    payload.setdefault("business_risk_level", incident.business_risk_level_snapshot)
    payload.setdefault("started_at", incident.started_at.isoformat())
    payload.setdefault("opened_at", incident.opened_at.isoformat() if incident.opened_at else None)
    if "duration_seconds" not in payload:
        snapshot_at = outbox.created_at or outbox.available_at or incident.started_at
        payload["duration_seconds"] = max(0, int((snapshot_at - incident.started_at).total_seconds()))
    return payload


async def _hydrate_recovery_payload(
    db: AsyncSession, incident: OperationalIncident, payload: dict
) -> dict:
    hydrated = dict(payload)
    if incident.sensor_id is not None:
        reading = await db.scalar(
            select(TelemetryReading)
            .where(TelemetryReading.sensor_id == incident.sensor_id)
            .order_by(TelemetryReading.recorded_at.desc(), TelemetryReading.id.desc())
            .limit(1)
        )
        if reading is not None:
            hydrated["value"] = reading.value
            hydrated["recorded_at"] = reading.recorded_at.isoformat()
            hydrated["received_at"] = reading.received_at.isoformat()
    if incident.actuator_id is not None:
        actuator = await db.get(Actuator, incident.actuator_id)
        if actuator is not None:
            hydrated["voltage_v"] = actuator.voltage_v
            hydrated["current_a"] = actuator.current_a
            hydrated["reported_state"] = actuator.reported_state
            hydrated["desired_state"] = actuator.desired_state
            if actuator.last_reported_at is not None:
                hydrated["recorded_at"] = actuator.last_reported_at.isoformat()
    return hydrated


def _delivery_identity(outbox: NotificationOutbox, incident: OperationalIncident | None) -> str:
    if incident is None:
        return f"{outbox.source_type.lower()}:{outbox.idempotency_key}"
    return f"incident:{incident.id}:{outbox.event_type}"


async def process_notification_outbox(db: AsyncSession, *, notifier: TelegramNotifier | None = None, limit: int = 50) -> int:
    notifier = notifier or TelegramNotifier()
    now = datetime.now(UTC)
    # MQTT evaluation locks an incident before inserting/updating its outbox.
    # Claim in the same order to avoid an incident<->outbox deadlock while
    # telemetry and the scheduler are active concurrently.
    candidates = (await db.execute(
        select(NotificationOutbox.id, NotificationOutbox.incident_id)
        .where(
            NotificationOutbox.status.in_(("PENDING", "RETRYING")),
            NotificationOutbox.available_at <= now,
        )
        .order_by(NotificationOutbox.id)
        .limit(limit)
    )).all()
    claimed: list[tuple[NotificationOutbox, OperationalIncident | None]] = []
    for outbox_id, incident_id in candidates:
        incident = None
        if incident_id is not None:
            incident = await db.scalar(
                select(OperationalIncident)
                .where(OperationalIncident.id == incident_id)
                .with_for_update()
            )
        outbox = await db.scalar(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.id == outbox_id,
                NotificationOutbox.status.in_(("PENDING", "RETRYING")),
                NotificationOutbox.available_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        if outbox is not None:
            claimed.append((outbox, incident))
    processed = 0
    for outbox, incident in claimed:
        project_id = incident.project_id if incident else outbox.project_id
        if project_id is None or (outbox.incident_id is not None and incident is None):
            outbox.status = "FAILED"
            outbox.skip_reason = "SOURCE_NOT_FOUND"
            continue
        risk = str(outbox.payload_snapshot.get("business_risk_level") or "")
        policy_reason = await evaluate_notification_policy(
            db, project_id=project_id, source_type=outbox.source_type,
            event_type=outbox.event_type, risk=risk or None,
        )
        if policy_reason:
            outbox.status = "SKIPPED"
            outbox.skip_reason = policy_reason
            await _record_skipped_delivery(db, outbox, incident, policy_reason)
            outbox.processed_at = now
            processed += 1
            continue
        if incident is not None and incident.device_id and (outbox.payload_snapshot.get("freshness") == "STALE" or outbox.payload_snapshot.get("quality") == "STALE"):
            device = await db.get(Device, incident.device_id)
            if device is not None and str(device.status.value) == "OFFLINE":
                outbox.status = "SKIPPED"
                outbox.skip_reason = "SUPPRESSED_BY_DEVICE_OFFLINE"
                await _record_skipped_delivery(db, outbox, incident, outbox.skip_reason)
                outbox.processed_at = now
                processed += 1
                continue
        recipients = await resolve_notification_recipients(db, project_id=project_id)
        target_recipient_id = outbox.target_recipient_id or outbox.payload_snapshot.get("target_recipient_id")
        if target_recipient_id is not None:
            recipients = [item for item in recipients if item.id == target_recipient_id]
            if not recipients:
                outbox.status = "SKIPPED"
                outbox.skip_reason = "RECIPIENT_DISABLED"
                await _record_skipped_delivery(db, outbox, incident, outbox.skip_reason)
                outbox.processed_at = now
                processed += 1
                continue
        if incident is not None and outbox.event_type == "RECOVERED":
            informed_recipient_ids = set(
                (
                    await db.scalars(
                        select(NotificationDelivery.recipient_id)
                        .join(
                            NotificationOutbox,
                            NotificationOutbox.id == NotificationDelivery.outbox_id,
                        )
                        .where(
                            NotificationDelivery.incident_id == incident.id,
                            NotificationDelivery.channel == "TELEGRAM",
                            NotificationDelivery.status == "SENT",
                            NotificationDelivery.recipient_id.is_not(None),
                            NotificationOutbox.event_type == "OPEN",
                        )
                    )
                ).all()
            )
            recipients = [
                item for item in recipients if item.id in informed_recipient_ids
            ]
            if not recipients:
                outbox.status = "SKIPPED"
                outbox.skip_reason = "NO_PRIOR_OPEN_DELIVERY"
                await _record_skipped_delivery(db, outbox, incident, outbox.skip_reason)
                outbox.processed_at = now
                processed += 1
                continue
        if not recipients:
            outbox.status = "SKIPPED"
            outbox.skip_reason = "NO_RECIPIENT"
            await _record_skipped_delivery(db, outbox, incident, outbox.skip_reason)
            outbox.processed_at = now
            processed += 1
            continue
        if not getattr(notifier, "configured", True):
            outbox.status = "SKIPPED"
            outbox.skip_reason = "BOT_NOT_CONFIGURED"
            await _record_skipped_delivery(db, outbox, incident, outbox.skip_reason)
            outbox.processed_at = now
            processed += 1
            continue
        all_sent = True
        defensive_deduplication = outbox.event_type in {"OPEN", "RECOVERED"}
        duplicate_for_all = bool(recipients) and defensive_deduplication
        payload = _payload_at_delivery(outbox, incident, now) if incident else {**outbox.payload_snapshot, "event_type": outbox.event_type}
        if incident is not None and outbox.event_type == "RECOVERED":
            payload = await _hydrate_recovery_payload(db, incident, payload)
        reply_markup = (
            telegram_action_keyboard(project_id)
            if incident is not None and outbox.event_type in TELEGRAM_PUSH_INCIDENT_EVENTS
            else None
        )
        for recipient in recipients:
            if defensive_deduplication:
                prior_sent = await db.scalar(
                    select(NotificationDelivery.id)
                    .join(NotificationOutbox, NotificationOutbox.id == NotificationDelivery.outbox_id)
                    .where(
                        NotificationDelivery.incident_id == incident.id,
                        NotificationDelivery.channel == "TELEGRAM",
                        NotificationDelivery.recipient_id == recipient.id,
                        NotificationDelivery.status == "SENT",
                        NotificationOutbox.event_type == outbox.event_type,
                        NotificationOutbox.id != outbox.id,
                    )
                    .limit(1)
                )
                if prior_sent is not None:
                    continue
                duplicate_for_all = False
            delivery_key = f"{_delivery_identity(outbox, incident)}:TELEGRAM:{recipient.id}"
            await db.execute(insert(NotificationDelivery).values(outbox_id=outbox.id, incident_id=incident.id if incident else None, channel="TELEGRAM", recipient_id=recipient.id, recipient_reference=recipient.name, idempotency_key=delivery_key, status="PENDING", attempt_count=0).on_conflict_do_nothing(index_elements=["idempotency_key"]))
            delivery = await db.scalar(select(NotificationDelivery).where(NotificationDelivery.idempotency_key == delivery_key).with_for_update())
            if delivery is None or delivery.status == "SENT":
                continue
            delivery.attempt_count += 1
            delivery.last_attempt_at = now
            message = format_project_activity_message(payload) if outbox.source_type == "PROJECT_ACTIVITY" else format_operational_message(payload)
            result = await notifier.send_message(
                recipient.telegram_chat_id, message, reply_markup=reply_markup
            )
            if result.sent:
                delivery.status = "SENT"
                delivery.sent_at = now
                delivery.failed_at = None
                delivery.error_category = None
                delivery.provider_status_code = result.status_code
                delivery.error_message = None
            else:
                all_sent = False
                delivery.status = "RETRYING" if delivery.attempt_count < 5 else "FAILED"
                delivery.failed_at = now
                delivery.error_category = result.error_category
                delivery.provider_status_code = result.status_code
                delivery.error_message = {
                    "RATE_LIMITED": "Telegram giới hạn tần suất gửi; hệ thống sẽ thử lại.",
                    "BAD_REQUEST": "Telegram từ chối yêu cầu hoặc Chat ID không hợp lệ.",
                    "FORBIDDEN": "Bot không được phép gửi tới người nhận này.",
                    "INVALID_TOKEN": "Cấu hình Telegram phía máy chủ không hợp lệ.",
                    "TIMEOUT": "Telegram không phản hồi trong thời gian cho phép.",
                    "NETWORK_ERROR": "Không thể kết nối tới Telegram.",
                }.get(result.error_category, "Telegram trả về lỗi; hệ thống sẽ thử lại nếu phù hợp.")
                retry_delay = result.retry_after_seconds or min(3600, 60 * (2 ** delivery.attempt_count))
                delivery.next_retry_at = now + timedelta(seconds=retry_delay)
        outbox.attempt_count += 1
        outbox.last_attempt_at = now
        if all_sent and duplicate_for_all:
            outbox.status = "SKIPPED"
            outbox.skip_reason = "DUPLICATE_OPEN_EVENT" if outbox.event_type == "OPEN" else "DUPLICATE_INCIDENT_EVENT"
            outbox.processed_at = now
            processed += 1
        elif all_sent:
            outbox.status = "SENT"
            outbox.processed_at = now
            processed += 1
        elif outbox.attempt_count < 5:
            outbox.status = "RETRYING"
            retry_after = max(
                (delivery.next_retry_at for delivery in (await db.scalars(select(NotificationDelivery).where(NotificationDelivery.outbox_id == outbox.id))).all() if delivery.next_retry_at),
                default=now + timedelta(minutes=min(60, 2 ** outbox.attempt_count)),
            )
            outbox.available_at = retry_after
        else:
            outbox.status = "FAILED"
    await db.commit()
    return processed


async def _record_skipped_delivery(db: AsyncSession, outbox: NotificationOutbox, incident: OperationalIncident | None, reason: str) -> None:
    await db.execute(
        insert(NotificationDelivery).values(
            outbox_id=outbox.id, incident_id=incident.id if incident else None, channel="TELEGRAM",
            recipient_id=None, recipient_reference="Hệ thống",
            idempotency_key=f"{outbox.id}:TELEGRAM:SKIPPED",
            status="SKIPPED", attempt_count=0, error_category=reason,
        ).on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
