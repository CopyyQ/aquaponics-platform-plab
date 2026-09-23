import asyncio

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.enums import UserRole, UserStatus
from app.core.security import hash_password
from app.models.actuator_model import ActuatorModel
from app.models.device_template import (
    DeviceTemplate,
    DeviceTemplateActuator,
    DeviceTemplateSensor,
)
from app.models.permission import Permission, Role, RolePermission
from app.models.scenario_catalog import ScenarioCatalog, ScenarioCatalogItem
from app.models.sensor import SensorModel
from app.models.user import User

SENSOR_MODELS: tuple[dict[str, str | float | None], ...] = (
    {"code": "NH3", "name": "Cảm biến NH3", "unit": "mg/L", "description": "Đo nồng độ ammonia trong nước.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "NO3", "name": "Cảm biến NO3", "unit": "mg/L", "description": "Đo nồng độ nitrate trong nước.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "PH", "name": "Cảm biến pH", "unit": "pH", "description": "Đo độ pH của nước.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "DO", "name": "Cảm biến oxy hòa tan", "unit": "mg/L", "description": "Đo oxy hòa tan trong nước.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "TDS", "name": "Cảm biến TDS", "unit": "ppm", "description": "Đo tổng chất rắn hòa tan trong nước.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "WATER_TEMPERATURE", "name": "Cảm biến nhiệt độ nước", "unit": "°C", "description": "Đo nhiệt độ nước.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "WATER_LEVEL", "name": "Cảm biến mực nước", "unit": "%", "description": "Theo dõi mức nước trong hệ thống.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "AIR_TEMPERATURE", "name": "Cảm biến nhiệt độ không khí", "unit": "°C", "description": "Đo nhiệt độ không khí tại khu vực lắp đặt.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "AIR_HUMIDITY", "name": "Cảm biến độ ẩm không khí", "unit": "%RH", "description": "Đo độ ẩm tương đối của không khí.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "LIGHT_INTENSITY", "name": "Cảm biến ánh sáng", "unit": "lux", "description": "Đo cường độ ánh sáng tại khu vực lắp đặt.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "VOLTAGE", "name": "Cảm biến điện áp", "unit": "V", "description": "Đo điện áp của hệ thống điện.", "value_type": "NUMBER", "chart_type": "LINE"},
    {"code": "CURRENT", "name": "Cảm biến dòng điện", "unit": "A", "description": "Đo dòng điện của hệ thống điện.", "value_type": "NUMBER", "chart_type": "LINE"},
)

CANONICAL_SENSOR_MODEL_CODES = frozenset(item["code"] for item in SENSOR_MODELS)

ENVIRONMENTAL_SENSOR_MODEL_CODES = frozenset(
    {"AIR_HUMIDITY", "AIR_TEMPERATURE", "LIGHT_INTENSITY"}
)

ACTUATOR_MODELS = (
    ("FISH_TANK_PUMP", "Bơm bể cá", "Bơm nước từ bể cá sang cụm lọc."),
    ("BIOFILTER_PUMP", "Bơm bể lọc vi sinh", "Bơm nước từ bể lọc vi sinh lên giàn trồng."),
    ("AERATION_PUMP", "Máy sủi oxy", "Cấp oxy cho bể cá và hệ vi sinh."),
    ("FRESH_WATER_VALVE", "Van điện từ cấp nước", "Bổ sung nước sạch vào bể cá."),
    ("FILTER_DRAIN_VALVE", "Van điện từ xả đáy", "Xả chất thải tại bể lọc cơ học."),
    ("GROW_LIGHT", "Đèn chiếu sáng", "Chiếu sáng bổ sung cho khu vực trồng."),
    ("WARNING_LIGHT", "Đèn cảnh báo", "Cảnh báo trạng thái bất thường tại chỗ."),
    ("WARNING_BUZZER", "Loa/còi báo", "Phát cảnh báo âm thanh tại chỗ."),
)

CANONICAL_ACTUATOR_MODEL_CODES = frozenset(item[0] for item in ACTUATOR_MODELS)

ACTUATOR_ELECTRICAL_DEFAULTS: dict[str, dict[str, float]] = {}

CANONICAL_DEVICE_TEMPLATE_CODE = "AQUAPONICS_SYSTEM_DEVICE"
CANONICAL_DEVICE_TEMPLATE_NAME = "Thiết bị hệ thống Aquaponics"

CANONICAL_SCENARIO_CATALOG_CODE = "AQUAPONICS_OPERATION_SCENARIO"
CANONICAL_SCENARIO_CATALOG_NAME = "Kịch bản vận hành Aquaponics"
SCENARIO_SOURCE_REFERENCE = (
    "Yêu cầu thông báo Telegram Aquaponics + "
    "Phương án kỹ thuật hệ thống Aquaponics - IOT nhà vườn"
)


def _threshold_branch(
    key: str,
    label: str,
    operator: str,
    value: float,
    *,
    message: str,
    consequence: str,
    recommended_action: str,
    enabled: bool = True,
) -> dict:
    return {
        "key": key,
        "label": label,
        "enabled": enabled,
        "evaluator_type": "THRESHOLD",
        "condition_config": {
            "operator": operator,
            "value": value,
            "severity": "WARNING",
            "duration_seconds": 0,
        },
        "risk_level": "MEDIUM",
        "message": message,
        "consequence": consequence,
        "recommended_action": recommended_action,
    }


def _actuator_branch(
    key: str,
    label: str,
    voltage: float,
    *,
    message: str,
    consequence: str,
    recommended_action: str,
) -> dict:
    return {
        "key": key,
        "label": label,
        "enabled": True,
        "evaluator_type": "MULTI_CONDITION",
        "condition_config": {
            "logic": "AND",
            "desired_state": True,
            "reported_state": None,
            "voltage": {"operator": "EQ", "value": voltage},
            "current": {"operator": "EQ", "value": 0},
            "duration_seconds": 0,
        },
        "risk_level": "MEDIUM",
        "message": message,
        "consequence": consequence,
        "recommended_action": recommended_action,
    }


DEFAULT_SENSOR_SCENARIOS: dict[str, dict] = {
    "PH": {
        "is_enabled": True,
        "branches": [
            _threshold_branch(
                "PH_LOW", "pH thấp", "LT", 6,
                message="pH nước thấp hơn ngưỡng cho phép.",
                consequence=(
                    "Hệ vi sinh và cá bị ảnh hưởng; khả năng hấp thu dinh dưỡng "
                    "của rễ cây suy giảm."
                ),
                recommended_action=(
                    "Kiểm tra nguồn nước, thay một phần nước và dùng vật liệu "
                    "đệm pH phù hợp theo hướng dẫn vận hành."
                ),
            ),
            _threshold_branch(
                "PH_HIGH", "pH cao", "GT", 7.5,
                message="pH nước cao hơn ngưỡng cho phép.",
                consequence="Khả năng hấp thu dinh dưỡng của cây bị giảm.",
                recommended_action=(
                    "Kiểm tra vật thể lạ trong hệ thống; bổ sung nước mưa/nước "
                    "phù hợp theo quy trình và kiểm tra lại pH."
                ),
            ),
        ],
        "notes": "Ngưỡng theo tài liệu Telegram: pH < 6 hoặc pH > 7.5.",
    },
    "TDS": {
        "is_enabled": True,
        "branches": [
            _threshold_branch(
                "TDS_LOW", "TDS thấp", "LT", 100,
                message="TDS thấp hơn 100 ppm.",
                consequence="Cây có thể thiếu dinh dưỡng và sinh trưởng kém.",
                recommended_action=(
                    "Kiểm tra cân bằng mật độ cá/cây và bổ sung giải pháp sinh học "
                    "theo quy trình vận hành."
                ),
            )
        ],
        "notes": "Ngưỡng cảnh báo theo tài liệu Telegram: TDS < 100 ppm.",
    },
    "WATER_LEVEL": {
        "is_enabled": True,
        "branches": [
            _threshold_branch(
                "WATER_LEVEL_LOW", "Mực nước thấp", "LT", 60,
                message="Mực nước thấp hơn 60%.",
                consequence=(
                    "Dòng tuần hoàn và hoạt động của hệ lọc/giàn trồng có thể bị ảnh hưởng."
                ),
                recommended_action=(
                    "Kiểm tra bơm, van cấp nước, đường ống và vị trí rò rỉ/tắc nghẽn."
                ),
            )
        ],
        "notes": (
            "Tài liệu có tình huống cho bể cá và bể lọc vi sinh; catalog hiện có "
            "một SensorModel WATER_LEVEL và runtime location xác định vị trí thực tế."
        ),
    },
    "WATER_TEMPERATURE": {
        "is_enabled": True,
        "branches": [
            _threshold_branch(
                "WATER_TEMP_LOW", "Nhiệt độ nước thấp", "LT", 18,
                message="Nhiệt độ nước thấp hơn ngưỡng 18°C.",
                consequence="Tài liệu xác định ngưỡng nhưng chưa mô tả chi tiết nội dung Telegram.",
                recommended_action="Kiểm tra điều kiện môi trường và nhiệt độ nước.",
                enabled=False,
            ),
            _threshold_branch(
                "WATER_TEMP_HIGH", "Nhiệt độ nước cao", "GT", 35,
                message="Nhiệt độ nước cao hơn 35°C.",
                consequence="Oxy hòa tan giảm và cá có thể bị stress.",
                recommended_action=(
                    "Che mát bể cá và kiểm tra phương án bổ sung nước sạch theo "
                    "kịch bản vận hành."
                ),
            ),
        ],
        "notes": "Ngưỡng tài liệu: < 18°C hoặc > 35°C; Telegram mô tả chi tiết nhánh > 35°C.",
    },
    "DO": {
        "is_enabled": False,
        "branches": [{
            "key": "DO_LOW",
            "label": "DO thấp",
            "enabled": True,
            "evaluator_type": "THRESHOLD_BANDS",
            "condition_config": {
                "bands": [
                    {"severity": "WARNING", "operator": "LT", "value": 5},
                    {"severity": "CRITICAL", "operator": "LT", "value": 4},
                ],
                "duration_seconds": 0,
            },
            "risk_level": "MEDIUM",
            "message": "Nồng độ oxy hòa tan thấp.",
            "consequence": "Cá và hệ vi sinh có thể bị thiếu oxy.",
            "recommended_action": "Kiểm tra và tăng cường sục khí.",
        }],
        "notes": "Tài liệu đánh dấu hiện chưa cần gửi Telegram cho DO.",
    },
    "AIR_TEMPERATURE": {
        "is_enabled": False,
        "branches": [
            _threshold_branch(
                "AIR_TEMP_HIGH", "Nhiệt độ không khí cao", "GT", 35,
                message="Nhiệt độ không khí cao hơn 35°C.",
                consequence="Môi trường nhà vườn có thể gây stress nhiệt.",
                recommended_action="Kiểm tra thông gió và che nắng.",
            )
        ],
        "notes": "Tài liệu đánh dấu hiện chưa cần gửi Telegram.",
    },
    "NH3": {
        "is_enabled": False,
        "branches": [],
        "notes": "Tài liệu Telegram chưa cung cấp ngưỡng số hoàn chỉnh và đánh dấu chưa cần thông báo.",
    },
    "NO3": {
        "is_enabled": False,
        "branches": [],
        "notes": "Tài liệu Telegram nêu NO2, không phải NO3; không tự ánh xạ sang NO3.",
    },
    "AIR_HUMIDITY": {
        "is_enabled": False,
        "branches": [],
        "notes": "Tài liệu nêu độ ẩm > 85–90% kéo dài nhưng không chốt một ngưỡng duy nhất.",
    },
    "LIGHT_INTENSITY": {
        "is_enabled": False,
        "branches": [],
        "notes": "Tài liệu nêu thiếu ánh sáng kéo dài nhưng chưa cung cấp ngưỡng lux.",
    },
    "VOLTAGE": {
        "is_enabled": False,
        "branches": [],
        "notes": "Điện áp được dùng làm bằng chứng cho kịch bản cơ cấu chấp hành.",
    },
    "CURRENT": {
        "is_enabled": False,
        "branches": [],
        "notes": "Dòng điện được dùng làm bằng chứng cho kịch bản cơ cấu chấp hành.",
    },
}


def _actuator_health_scenario(name: str, consequence: str, action: str) -> dict:
    return {
        "is_enabled": True,
        "branches": [
            _actuator_branch(
                "NO_LOAD", "Có nguồn nhưng không có tải", 12,
                message=f"{name} đang được bật, có điện áp khoảng 12V nhưng dòng điện khoảng 0A.",
                consequence=consequence,
                recommended_action=action,
            ),
            _actuator_branch(
                "NO_POWER", "Không có nguồn động lực", 0,
                message=f"{name} đang được bật nhưng điện áp và dòng điện đều khoảng 0.",
                consequence=consequence,
                recommended_action=(
                    "Kiểm tra nguồn động lực/phần tử đóng cắt và liên hệ đơn vị "
                    "cung cấp nếu không khôi phục được."
                ),
            ),
        ],
        "notes": (
            "Tài liệu dùng ký hiệu xấp xỉ ~12V/~0A; cấu hình mặc định lưu giá trị "
            "tham chiếu và cần hiệu chỉnh tolerance theo phần cứng thực tế."
        ),
    }


DEFAULT_ACTUATOR_SCENARIOS: dict[str, dict] = {
    "AERATION_PUMP": _actuator_health_scenario(
        "Máy sủi oxy",
        "Oxy trong nước giảm nhanh, ảnh hưởng cá và hệ vi sinh.",
        "Kiểm tra giắc nguồn, dây điện và máy sủi; thay thiết bị nếu hỏng.",
    ),
    "FISH_TANK_PUMP": _actuator_health_scenario(
        "Bơm bể cá",
        "Chất thải cá không được tuần hoàn lên bộ lọc, làm ô nhiễm bể cá.",
        "Kiểm tra giắc nguồn, bơm và đường nước; thay bơm nếu hỏng.",
    ),
    "BIOFILTER_PUMP": _actuator_health_scenario(
        "Bơm bể lọc vi sinh",
        "Nước giàu dinh dưỡng không được đưa lên giàn trồng, rễ cây có thể bị khô.",
        "Kiểm tra giắc nguồn, bơm và đường ống lên giàn NFT.",
    ),
    "GROW_LIGHT": _actuator_health_scenario(
        "Đèn chiếu sáng",
        "Cây thiếu ánh sáng bổ sung và khả năng quan sát khu vực trồng bị ảnh hưởng.",
        "Kiểm tra giắc nguồn, đèn và phần tử đóng cắt.",
    ),
    "FRESH_WATER_VALVE": {
        "is_enabled": False, "branches": [],
        "notes": "Có trong hệ thống nhưng tài liệu Telegram chưa định nghĩa kịch bản lỗi riêng.",
    },
    "FILTER_DRAIN_VALVE": {
        "is_enabled": False, "branches": [],
        "notes": "Có trong hệ thống nhưng tài liệu Telegram chưa định nghĩa kịch bản lỗi riêng.",
    },
    "WARNING_LIGHT": {
        "is_enabled": False, "branches": [],
        "notes": "Cơ cấu cảnh báo tại chỗ; tài liệu chưa định nghĩa Telegram lỗi riêng.",
    },
    "WARNING_BUZZER": {
        "is_enabled": False, "branches": [],
        "notes": "Cơ cấu cảnh báo tại chỗ; tài liệu chưa định nghĩa Telegram lỗi riêng.",
    },
}


BASE_PERMISSION_CODES = (
    "users.read", "users.create", "users.update", "users.delete",
    "users.force_logout", "users.set_password", "users.lock", "users.unlock",
    "aquaponics_systems.read", "aquaponics_systems.create",
    "aquaponics_systems.update", "aquaponics_systems.delete",
    "aquaponics_systems.manage_members", "aquaponics_systems.read_all",
    "aquaponics_systems.manage_all",
    "devices.read", "devices.create", "devices.update", "devices.delete",
    "sensors.read", "sensors.create", "sensors.update", "sensors.delete",
    "sensors.telemetry.read", "sensors.thresholds.read",
    "sensors.thresholds.create", "sensors.thresholds.update",
    "sensors.thresholds.delete",
    "actuators.read", "actuators.create", "actuators.update", "actuators.delete",
    "actuators.commands.read", "actuators.commands.create",
    "actuators.readings.read", "actuators.thresholds.read",
    "actuators.thresholds.create", "actuators.thresholds.update",
    "actuators.thresholds.delete",
    "project_scenarios.read", "project_scenarios.create",
    "project_scenarios.update", "project_scenarios.delete",
    "project_scenarios.activate",
    "sensor_models.read", "sensor_models.create", "sensor_models.update",
    "sensor_models.delete", "actuator_models.read", "actuator_models.create",
    "actuator_models.update", "actuator_models.delete",
    "device_templates.read", "device_templates.create",
    "device_templates.update", "device_templates.delete",
    "monitoring.read", "incidents.read", "incidents.acknowledge",
    "incidents.resolve", "notifications.settings.read",
    "notifications.settings.update", "notifications.recipients.read",
    "notifications.recipients.create", "notifications.recipients.update",
    "notifications.recipients.delete", "notifications.recipients.test",
    "notifications.history.read", "mqtt_config.export", "scada.read",
    "scada.update", "activities.read",
)

ADMIN_STRUCTURAL_PERMISSION_CODES = (
    "permissions.read", "permissions.create", "permissions.update",
    "permissions.delete", "roles.read", "roles.create", "roles.update",
    "roles.delete", "roles.permissions.read", "roles.permissions.update",
    "role_assignments.read", "role_assignments.update",
    "user_permissions.read", "user_permissions.update",
)


def _canonical_permissions() -> tuple[tuple[str, str, str], ...]:
    """Return the seed-owned canonical permission catalog."""
    codes = BASE_PERMISSION_CODES + ADMIN_STRUCTURAL_PERMISSION_CODES
    return tuple((code, *code.split(".", 1)) for code in codes)


async def seed_rbac(db: AsyncSession) -> None:
    roles: dict[str, Role] = {row.code: row for row in (await db.scalars(select(Role))).all()}
    for code, name in (("ADMIN", "Administrator"), ("OWNER", "System Owner"), ("VIEWER", "Viewer")):
        if code not in roles:
            roles[code] = Role(code=code, name=name, is_system=True, enabled=True); db.add(roles[code])
    permissions: dict[str, Permission] = {row.code: row for row in (await db.scalars(select(Permission))).all()}
    for code, resource, action in _canonical_permissions():
        if code not in permissions:
            permissions[code] = Permission(code=code, resource=resource, action=action); db.add(permissions[code])
    await db.flush()
    existing = {(row.role_id, row.permission_id) for row in (await db.scalars(select(RolePermission))).all()}
    read_actions = {"read", "telemetry.read", "thresholds.read", "commands.read", "readings.read", "history.read", "export"}
    owner_writes = {"aquaponics_systems.manage_members", "sensors.thresholds.create", "sensors.thresholds.update",
                    "sensors.thresholds.delete", "actuators.thresholds.create", "actuators.thresholds.update",
                    "actuators.thresholds.delete", "project_scenarios.create",
                    "project_scenarios.update", "project_scenarios.delete",
                    "project_scenarios.activate", "notifications.settings.update",
                    "notifications.recipients.create", "notifications.recipients.update",
                    "notifications.recipients.delete", "actuators.commands.create",
                    "incidents.acknowledge", "incidents.resolve"}
    for role_code, role in roles.items():
        for permission in permissions.values():
            readable = permission.resource not in {"users", "permissions", "roles", "role_assignments", "user_permissions"} and permission.action in read_actions
            allowed = role_code == "ADMIN" or (role_code in {"OWNER", "VIEWER"} and readable) \
                or (role_code == "OWNER" and permission.code in owner_writes)
            if allowed and (role.id, permission.id) not in existing: db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await db.flush()


async def seed_sensor_models(db: AsyncSession) -> int:
    codes = tuple(str(item["code"]) for item in SENSOR_MODELS)
    existing_models = {
        model.code: model
        for model in (
            await db.scalars(select(SensorModel).where(SensorModel.code.in_(codes)))
        ).all()
    }
    missing_models = [
        SensorModel(
            **item,
            is_active=True,
            is_visible=True,
        )
        for item in SENSOR_MODELS
        if item["code"] not in existing_models
    ]
    for item in SENSOR_MODELS:
        model = existing_models.get(str(item["code"]))
        if model is None:
            continue
        model.name = str(item["name"])
        model.unit = str(item["unit"])
        model.description = str(item["description"])
        model.value_type = str(item["value_type"])
        model.chart_type = str(item["chart_type"])
        model.measurement_semantics = str(item.get("measurement_semantics", "GAUGE"))
        model.is_visible = True
        model.is_active = True
        model.is_deleted = False
        model.deleted_at = None
    db.add_all(missing_models)
    await db.flush()
    return len(missing_models)


async def seed_actuator_models(db: AsyncSession) -> int:
    codes = tuple(item[0] for item in ACTUATOR_MODELS)
    existing_codes = set(
        (await db.scalars(select(ActuatorModel.code).where(ActuatorModel.code.in_(codes)))).all()
    )
    missing = [
        ActuatorModel(
            code=code,
            name=name,
            description=description,
            data_type="BOOLEAN",
            default_state=False,
            is_active=True,
            **ACTUATOR_ELECTRICAL_DEFAULTS.get(code, {}),
        )
        for code, name, description in ACTUATOR_MODELS
        if code not in existing_codes
    ]
    existing_models = list((await db.scalars(select(ActuatorModel).where(ActuatorModel.code.in_(codes)))).all())
    canonical_by_code = {
        code: (name, description)
        for code, name, description in ACTUATOR_MODELS
    }
    for model in existing_models:
        name, description = canonical_by_code[model.code]
        model.name = name
        model.description = description
        model.data_type = "BOOLEAN"
        model.default_state = False
        model.is_active = True
        model.is_deleted = False
        model.deleted_at = None
        for field, value in ACTUATOR_ELECTRICAL_DEFAULTS.get(model.code, {}).items():
            if getattr(model, field) is None:
                setattr(model, field, value)
    db.add_all(missing)
    await db.flush()
    return len(missing)


async def seed_device_template(db: AsyncSession) -> int:
    template = await db.scalar(
        select(DeviceTemplate).where(
            DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE
        )
    )
    if template is None:
        template = DeviceTemplate(
            code=CANONICAL_DEVICE_TEMPLATE_CODE,
            name=CANONICAL_DEVICE_TEMPLATE_NAME,
            description=(
                "Thiết bị chuẩn của hệ thống Aquaponics gồm 12 cảm biến "
                "và 8 cơ cấu chấp hành."
            ),
            is_active=True,
        )
        db.add(template)
        await db.flush()
    else:
        template.name = CANONICAL_DEVICE_TEMPLATE_NAME
        template.description = (
            "Thiết bị chuẩn của hệ thống Aquaponics gồm 12 cảm biến "
            "và 8 cơ cấu chấp hành."
        )
        template.is_active = True
        template.is_deleted = False
        template.deleted_at = None

    await db.execute(
        delete(DeviceTemplateSensor).where(
            DeviceTemplateSensor.device_template_id == template.id
        )
    )
    await db.execute(
        delete(DeviceTemplateActuator).where(
            DeviceTemplateActuator.device_template_id == template.id
        )
    )

    sensor_rows = {
        row.code: row
        for row in (
            await db.scalars(
                select(SensorModel).where(
                    SensorModel.code.in_(CANONICAL_SENSOR_MODEL_CODES)
                )
            )
        ).all()
    }
    actuator_rows = {
        row.code: row
        for row in (
            await db.scalars(
                select(ActuatorModel).where(
                    ActuatorModel.code.in_(CANONICAL_ACTUATOR_MODEL_CODES)
                )
            )
        ).all()
    }
    if set(sensor_rows) != set(CANONICAL_SENSOR_MODEL_CODES):
        raise RuntimeError("Canonical SensorModel catalog is incomplete")
    if set(actuator_rows) != set(CANONICAL_ACTUATOR_MODEL_CODES):
        raise RuntimeError("Canonical ActuatorModel catalog is incomplete")

    for item in SENSOR_MODELS:
        code = str(item["code"])
        db.add(
            DeviceTemplateSensor(
                device_template_id=template.id,
                sensor_model_id=sensor_rows[code].id,
                code=code,
                display_name=str(item["name"]),
                is_required=True,
            )
        )

    for code, name, _ in ACTUATOR_MODELS:
        db.add(
            DeviceTemplateActuator(
                device_template_id=template.id,
                actuator_model_id=actuator_rows[code].id,
                code=code,
                default_name=name,
                is_required=True,
            )
        )
    await db.flush()
    return template.id


async def seed_scenario_catalog(db: AsyncSession, device_template_id: int) -> int:
    catalog = await db.scalar(
        select(ScenarioCatalog).where(
            ScenarioCatalog.code == CANONICAL_SCENARIO_CATALOG_CODE
        )
    )
    if catalog is None:
        catalog = ScenarioCatalog(
            device_template_id=device_template_id,
            code=CANONICAL_SCENARIO_CATALOG_CODE,
            name=CANONICAL_SCENARIO_CATALOG_NAME,
            description=(
                "Bộ kịch bản vận hành/cảnh báo Aquaponics chuẩn hóa từ tài liệu "
                "Telegram và phương án kỹ thuật."
            ),
            is_active=True,
        )
        db.add(catalog)
        await db.flush()
    else:
        catalog.name = CANONICAL_SCENARIO_CATALOG_NAME
        catalog.device_template_id = device_template_id
        catalog.is_active = True
        catalog.is_deleted = False
        catalog.deleted_at = None

    sensor_mappings = list(
        (
            await db.scalars(
                select(DeviceTemplateSensor)
                .options(selectinload(DeviceTemplateSensor.sensor_model))
                .where(DeviceTemplateSensor.device_template_id == device_template_id)
                .order_by(DeviceTemplateSensor.id)
            )
        ).all()
    )
    actuator_mappings = list(
        (
            await db.scalars(
                select(DeviceTemplateActuator)
                .options(selectinload(DeviceTemplateActuator.actuator_model))
                .where(DeviceTemplateActuator.device_template_id == device_template_id)
                .order_by(DeviceTemplateActuator.id)
            )
        ).all()
    )
    existing = list(
        (
            await db.scalars(
                select(ScenarioCatalogItem).where(
                    ScenarioCatalogItem.scenario_catalog_id == catalog.id
                )
            )
        ).all()
    )
    sensor_items = {
        item.resource_code: item for item in existing if item.target_type == "SENSOR"
    }
    actuator_items = {
        item.resource_code: item for item in existing if item.target_type == "ACTUATOR"
    }

    for mapping in sensor_mappings:
        model = mapping.sensor_model
        item = sensor_items.get(mapping.code)
        config = DEFAULT_SENSOR_SCENARIOS.get(
            model.code,
            {"is_enabled": False, "branches": [], "notes": None},
        )
        if item is None:
            item = ScenarioCatalogItem(
                scenario_catalog_id=catalog.id,
                target_type="SENSOR",
                resource_code=mapping.code,
                sensor_model_id=model.id,
                name=mapping.display_name or model.name,
            )
            db.add(item)
        item.sensor_model_id = model.id
        item.name = mapping.display_name or model.name
        item.is_enabled = bool(config["is_enabled"])
        item.branches = list(config["branches"])
        item.source_reference = SCENARIO_SOURCE_REFERENCE
        item.notes = config.get("notes")

    for mapping in actuator_mappings:
        model = mapping.actuator_model
        item = actuator_items.get(mapping.code)
        config = DEFAULT_ACTUATOR_SCENARIOS.get(
            model.code,
            {"is_enabled": False, "branches": [], "notes": None},
        )
        if item is None:
            item = ScenarioCatalogItem(
                scenario_catalog_id=catalog.id,
                target_type="ACTUATOR",
                resource_code=mapping.code,
                actuator_model_id=model.id,
                name=mapping.default_name or model.name,
            )
            db.add(item)
        item.actuator_model_id = model.id
        item.name = mapping.default_name or model.name
        item.is_enabled = bool(config["is_enabled"])
        item.branches = list(config["branches"])
        item.source_reference = SCENARIO_SOURCE_REFERENCE
        item.notes = config.get("notes")

    await db.flush()
    return catalog.id


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        await seed_rbac(db)
        admin = await db.scalar(select(User).where(User.username == settings.default_admin_username))
        if admin is None:
            admin = User(
                username=settings.default_admin_username,
                password_hash=hash_password(settings.default_admin_password),
                full_name="Quản trị viên hệ thống",
                email="admin@aquaponics.vn",
                phone_number="0000000000",
                address="",
                system_role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                must_change_password=False,
            )
            db.add(admin)
        else:
            admin.system_role = UserRole.ADMIN
            admin.status = UserStatus.ACTIVE
            admin.is_deleted = False
            admin.deleted_at = None
            admin.must_change_password = False
            admin.email = "admin@aquaponics.vn"
            if settings.reset_default_admin_password:
                admin.password_hash = hash_password(settings.default_admin_password)
        owner = await db.scalar(select(User).where(User.username == settings.default_owner_username))
        if owner is None:
            owner = User(
                username=settings.default_owner_username,
                password_hash=hash_password(settings.default_admin_password),
                full_name="Chủ sở hữu hệ thống",
                email="owner@aquaponics.vn",
                phone_number="0000000001",
                address="",
                system_role=UserRole.OWNER,
                status=UserStatus.ACTIVE,
                must_change_password=True,
            )
            db.add(owner)
        else:
            owner.system_role = UserRole.OWNER
            owner.status = UserStatus.ACTIVE
            owner.is_deleted = False
            owner.deleted_at = None
            owner.must_change_password = True
        await seed_sensor_models(db)
        await db.flush()
        await seed_actuator_models(db)
        await db.flush()
        device_template_id = await seed_device_template(db)
        await db.flush()
        await seed_scenario_catalog(db, device_template_id)
        roles = {role.code: role.id for role in (await db.scalars(select(Role))).all()}
        if roles:
            admin.role_id = roles.get(UserRole.ADMIN.value)
            owner.role_id = roles.get(UserRole.OWNER.value)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
