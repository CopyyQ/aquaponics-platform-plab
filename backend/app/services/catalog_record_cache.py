from __future__ import annotations

from app.core.record_cache import RecordCache, record_cache

CACHE_NAMESPACE = "aquaponics"

SENSOR_MODEL_PREFIX = f"{CACHE_NAMESPACE}:sensor_model"
ACTUATOR_MODEL_PREFIX = f"{CACHE_NAMESPACE}:actuator_model"
DEVICE_TEMPLATE_PREFIX = f"{CACHE_NAMESPACE}:device_template"
SCENARIO_CATALOG_PREFIX = f"{CACHE_NAMESPACE}:scenario_catalog"


def sensor_model_key(model_id: int) -> str:
    return f"{SENSOR_MODEL_PREFIX}:{model_id}"


def actuator_model_key(model_id: int) -> str:
    return f"{ACTUATOR_MODEL_PREFIX}:{model_id}"


def device_template_key(template_id: int) -> str:
    return f"{DEVICE_TEMPLATE_PREFIX}:{template_id}"


def scenario_catalog_key(catalog_id: int) -> str:
    return f"{SCENARIO_CATALOG_PREFIX}:{catalog_id}"


async def invalidate_sensor_model(
    model_id: int,
    *,
    cache: RecordCache | None = None,
) -> None:
    selected_cache = cache or record_cache
    await selected_cache.delete(sensor_model_key(model_id))
    # DeviceTemplate and ScenarioCatalog payloads embed model names/codes.
    await selected_cache.delete_pattern(f"{DEVICE_TEMPLATE_PREFIX}:*")
    await selected_cache.delete_pattern(f"{SCENARIO_CATALOG_PREFIX}:*")


async def invalidate_actuator_model(
    model_id: int,
    *,
    cache: RecordCache | None = None,
) -> None:
    selected_cache = cache or record_cache
    await selected_cache.delete(actuator_model_key(model_id))
    await selected_cache.delete_pattern(f"{DEVICE_TEMPLATE_PREFIX}:*")
    await selected_cache.delete_pattern(f"{SCENARIO_CATALOG_PREFIX}:*")


async def invalidate_device_template(
    template_id: int,
    *,
    scenario_items_changed: bool = False,
    cache: RecordCache | None = None,
) -> None:
    selected_cache = cache or record_cache
    await selected_cache.delete(device_template_key(template_id))
    if scenario_items_changed:
        await selected_cache.delete_pattern(f"{SCENARIO_CATALOG_PREFIX}:*")


async def invalidate_scenario_catalog(
    catalog_id: int,
    *,
    cache: RecordCache | None = None,
) -> None:
    selected_cache = cache or record_cache
    await selected_cache.delete(scenario_catalog_key(catalog_id))
