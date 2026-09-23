from types import SimpleNamespace
from uuid import UUID

from app.api.v1.aquaponics_systems import _device_read


def _actuator(device, seq: int, row_id: int):
    return SimpleNamespace(
        id=row_id,
        public_id=UUID(int=row_id),
        device=device,
        actuator_model_id=row_id,
        sequence_number=seq,
        code=f"A{row_id}",
        name=f"Actuator {row_id}",
        location=None,
        notes=None,
        is_enabled=True,
        desired_state=False,
        reported_state=False,
        voltage_v=0.0,
        current_a=0.0,
        is_deleted=False,
        removed_at=None,
    )


def test_device_read_keeps_actuators_in_sequence_order():
    device = SimpleNamespace(
        public_id=UUID(int=100),
        project=SimpleNamespace(public_id=UUID(int=200)),
        code="DEV",
        name="Device",
        description=None,
        location=None,
        device_template_id=1,
        status="ONLINE",
        is_enabled=True,
        sensors=[],
        actuators=[],
    )
    device.actuators = [
        _actuator(device, 3, 3),
        _actuator(device, 1, 1),
        _actuator(device, 2, 2),
    ]

    payload = _device_read(device)

    assert [item["id"] for item in payload["actuators"]] == [
        UUID(int=1),
        UUID(int=2),
        UUID(int=3),
    ]
