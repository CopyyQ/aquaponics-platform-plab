import json

import pytest

from app.core.config import settings
from app.mqtt import publisher


class _PublishInfo:
    rc = 0

    def __init__(self, *, published: bool = True) -> None:
        self.published = published
        self.wait_timeout: float | None = None

    def wait_for_publish(self, timeout: float | None = None) -> None:
        self.wait_timeout = timeout

    def is_published(self) -> bool:
        return self.published


class _Client:
    def __init__(self, *_args, **_kwargs) -> None:
        self.connect_timeout = None
        self.connected: tuple[str, int] | None = None
        self.publish_args: tuple[str, str, int, bool] | None = None
        self.info = _PublishInfo()
        self.started = False
        self.stopped = False
        self.disconnected = False

    def connect(self, host: str, port: int, **_kwargs):
        self.connected = (host, port)
        return 0

    def loop_start(self) -> None:
        self.started = True

    def publish(self, topic: str, payload: str, qos: int, retain: bool):
        self.publish_args = (topic, payload, qos, retain)
        return self.info

    def disconnect(self) -> None:
        self.disconnected = True

    def loop_stop(self) -> None:
        self.stopped = True


def test_command_publish_settings_have_bounded_defaults() -> None:
    assert settings.actuator_command_dispatch_interval_seconds == 1.0
    assert settings.actuator_command_publish_max_attempts == 7
    assert settings.actuator_command_publish_batch_size == 20
    assert settings.actuator_command_publish_timeout_seconds == 5.0


def test_publisher_uses_qos_stable_payload_and_timeout(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(publisher.mqtt, "Client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(settings, "mqtt_qos", 2)
    monkeypatch.setattr(settings, "actuator_command_publish_timeout_seconds", 3.5)

    publisher.publish_actuator_command(
        "DEVICE-01",
        41,
        "PUMP-01",
        True,
        "2026-09-22T01:00:00+00:00",
    )

    assert client.connect_timeout == 3.5
    assert client.connected == (settings.mqtt_host, settings.mqtt_port)
    assert client.publish_args is not None
    topic, raw_payload, qos, retain = client.publish_args
    assert topic == settings.mqtt_command_topic.format(device_code="DEVICE-01")
    assert qos == 2
    assert retain is False
    assert json.loads(raw_payload) == {
        "command_id": "41",
        "actuator_code": "PUMP-01",
        "desired_state": True,
        "requested_at": "2026-09-22T01:00:00+00:00",
    }
    assert client.info.wait_timeout is not None
    assert 0 < client.info.wait_timeout <= 3.5
    assert client.started is True
    assert client.disconnected is True
    assert client.stopped is True


def test_publisher_uses_one_total_timeout_budget(monkeypatch) -> None:
    client = _Client()
    monotonic_values = iter((100.0, 102.0))
    monkeypatch.setattr(publisher.mqtt, "Client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(publisher.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(settings, "actuator_command_publish_timeout_seconds", 3.5)

    publisher.publish_actuator_command(
        "DEVICE-01",
        44,
        "PUMP-01",
        True,
        "2026-09-22T01:00:00+00:00",
    )

    assert client.connect_timeout == 3.5
    assert client.info.wait_timeout == pytest.approx(1.5)


def test_publisher_normalizes_connect_error(monkeypatch) -> None:
    class FailingClient(_Client):
        def connect(self, host: str, port: int, **_kwargs):
            raise OSError("broker-secret-host failed")

    monkeypatch.setattr(publisher.mqtt, "Client", lambda *_args, **_kwargs: FailingClient())

    with pytest.raises(publisher.MqttPublishError) as caught:
        publisher.publish_actuator_command(
            "DEVICE-01",
            42,
            "PUMP-01",
            False,
            "2026-09-22T01:00:00+00:00",
        )

    assert caught.value.code == "MQTT_CONNECT_ERROR"
    assert "broker-secret-host" not in str(caught.value)


def test_publisher_reports_publish_timeout(monkeypatch) -> None:
    client = _Client()
    client.info = _PublishInfo(published=False)
    monkeypatch.setattr(publisher.mqtt, "Client", lambda *_args, **_kwargs: client)

    with pytest.raises(publisher.MqttPublishError) as caught:
        publisher.publish_actuator_command(
            "DEVICE-01",
            43,
            "PUMP-01",
            True,
            "2026-09-22T01:00:00+00:00",
        )

    assert caught.value.code == "MQTT_TIMEOUT"
