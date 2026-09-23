from __future__ import annotations

from math import isfinite


ENGINEERING_RANGES: dict[str, tuple[float, float]] = {
    "PH": (0.0, 14.0),
    "WATER_TEMPERATURE": (-20.0, 80.0),
    "AIR_TEMPERATURE": (-50.0, 100.0),
    "DO": (0.0, 30.0),
    "TDS": (0.0, 100000.0),
    "WATER_LEVEL": (0.0, 100.0),
    "AIR_HUMIDITY": (0.0, 100.0),
    "LIGHT_INTENSITY": (0.0, 200000.0),
    "VOLTAGE": (0.0, 1000.0),
    "CURRENT": (0.0, 1000.0),
}


def classify_measurement_quality(
    model_code: str,
    value: float | None,
) -> tuple[str, str | None, float | None, float | None]:
    if value is None:
        return "NO_DATA", "Chưa nhận được dữ liệu.", None, None
    if not isfinite(value):
        return "INVALID", "Giá trị không phải số hữu hạn và không thể dùng làm phép đo.", None, None
    bounds = ENGINEERING_RANGES.get(model_code.upper())
    if bounds is None:
        return "UNVALIDATED", "Chưa có miền hợp lệ cho SensorModel.", None, None
    lower, upper = bounds
    if value < lower or value > upper:
        return "OUT_OF_RANGE", f"Giá trị vượt miền hợp lệ {lower:g}–{upper:g}.", lower, upper
    return "VALID", None, lower, upper
