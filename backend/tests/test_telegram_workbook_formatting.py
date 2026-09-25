from app.services.notification_outbox_service import format_operational_message


def _base_payload(**overrides):
    payload = {
        "event_type": "OPEN",
        "scenario_name": "Kịch bản vận hành Aquaponics",
        "branch_name": "Nhánh cảnh báo",
        "project_name": "Hệ thống Aquaponics",
        "resource_name": "Thiết bị",
        "recorded_at": "2026-09-25T06:51:30+00:00",
        "started_at": "2026-09-25T06:51:30+00:00",
        "business_risk_level": "VERY_HIGH",
        "consequence": "Ảnh hưởng kiểm thử.",
        "recommended_action": "- Bước một\n- Bước hai",
    }
    payload.update(overrides)
    return payload


def test_aquaponics_workbook_actuator_message_matches_required_shape():
    message = format_operational_message(
        _base_payload(
            actuator_code="AERATION_PUMP",
            actuator_name="Máy sủi oxy",
            resource_name="Máy sủi oxy",
            reported_state=True,
            desired_state=True,
            voltage_v=12.0,
            current_a=0.0,
            consequence=(
                "Lượng oxy cho cá và cây có thể tụt nhanh gây chết hàng loạt, "
                "CẦN KHẮC PHỤC NGAY."
            ),
            recommended_action=(
                "- Kiểm tra giắc cắm nguồn có bị lỏng hay không\n"
                "- Máy sục oxy có thể hỏng\n"
                "- Liên hệ nhà cung cấp"
            ),
        )
    )

    assert message.startswith("TÌNH TRẠNG HỆ THỐNG\nDỰ ÁN: Hệ thống Aquaponics")
    assert "THIẾT BỊ CHẤP HÀNH - Máy sủi Oxy" in message
    assert "LỖI BẤT THƯỜNG" in message
    assert "Trạng thái: Bật" in message
    assert "Điện áp: 12 VDC" in message
    assert "Dòng điện: 0 A" in message
    assert "Khắc phục:" in message
    assert "Kịch bản:" not in message
    assert "Nhánh:" not in message
    assert "Khuyến nghị xử lý:" not in message


def test_aquaponics_workbook_ph_uses_runtime_value_and_threshold_direction():
    message = format_operational_message(
        _base_payload(
            sensor_code="PH",
            sensor_name="Cảm biến pH",
            resource_name="Cảm biến pH",
            value=5.9,
            unit="pH",
            condition_config={"operator": "LT", "value": 6},
            message_template="Độ pH đang dưới mức cho phép - QUÁ THẤP.",
        )
    )

    assert "CẢM BIẾN - Mức pH của bể cá" in message
    assert "Giá trị pH: 5,9 - Vượt ngưỡng dưới" in message
    assert "QUÁ THẤP" not in message


def test_aquaponics_workbook_fish_tank_water_level_is_not_mixed_with_biofilter():
    message = format_operational_message(
        _base_payload(
            sensor_code="WATER_LEVELW2",
            sensor_name="Cảm biến mực nước bể cá",
            resource_name="Cảm biến mực nước bể cá",
            value=60.0,
            unit="%",
            condition_config={
                "range": {"min": 65, "max": 101},
                "range_mode": "OUTSIDE_RANGE",
            },
            consequence="Sai cũ: CẦN KHẮC PHỤC trong 24h tới.",
        )
    )

    assert "CẢM BIẾN - Mức nước bể cá" in message
    assert "Mức nước bể cá THẤP: 60%" in message
    assert "bể lọc vi sinh THẤP" not in message
    assert "CẦN KHẮC PHỤC trong 3h tới." in message
    assert "24h" not in message


def test_recovered_scenario_does_not_repeat_old_fault_content():
    message = format_operational_message(
        _base_payload(
            event_type="RECOVERED",
            sensor_code="PH",
            sensor_name="Cảm biến pH",
            resource_name="Cảm biến pH",
            value=7.2,
            unit="pH",
            threshold=6,
            condition_config={"operator": "LT", "value": 6},
            recorded_at="2026-09-25T06:52:15+00:00",
            message_template="Độ pH đang dưới mức cho phép - QUÁ THẤP.",
            consequence="Hệ vi sinh bị ảnh hưởng.",
            recommended_action="- Thay nước",
        )
    )

    assert message.startswith("✅ ĐÃ TRỞ VỀ BÌNH THƯỜNG")
    assert "Giá trị hiện tại: 7,2 pH" in message
    assert "Điều kiện cảnh báo trước đó: < 6 pH" in message
    assert "QUÁ THẤP" not in message
    assert "LỖI BẤT THƯỜNG" not in message
    assert "Khắc phục:" not in message
