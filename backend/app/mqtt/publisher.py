import json
import logging
import time
from contextlib import suppress

import paho.mqtt.client as mqtt

from app.core.config import settings

logger = logging.getLogger(__name__)


class MqttPublishError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def publish_actuator_command(
    device_code: str,
    command_id: int,
    actuator_code: str,
    desired_state: bool,
    requested_at: str,
) -> None:
    topic = settings.mqtt_command_topic.format(device_code=device_code)
    payload = json.dumps(
        {
            "command_id": str(command_id),
            "actuator_code": actuator_code,
            "desired_state": desired_state,
            "requested_at": requested_at,
        }
    )
    timeout_seconds = settings.actuator_command_publish_timeout_seconds
    deadline = time.monotonic() + timeout_seconds
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{settings.mqtt_client_id}-command-{command_id}",
    )
    client.connect_timeout = timeout_seconds

    try:
        connect_result = client.connect(settings.mqtt_host, settings.mqtt_port)
    except (OSError, TimeoutError) as exc:
        raise MqttPublishError("MQTT_CONNECT_ERROR") from exc
    except Exception as exc:
        raise MqttPublishError("MQTT_CONNECT_ERROR") from exc

    if connect_result != mqtt.MQTT_ERR_SUCCESS:
        raise MqttPublishError("MQTT_CONNECT_ERROR")

    client.loop_start()
    try:
        try:
            info = client.publish(
                topic,
                payload=payload,
                qos=settings.mqtt_qos,
                retain=False,
            )
        except Exception as exc:
            raise MqttPublishError("MQTT_PUBLISH_ERROR") from exc

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise MqttPublishError("MQTT_PUBLISH_ERROR")

        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise MqttPublishError("MQTT_TIMEOUT")

        try:
            info.wait_for_publish(timeout=remaining_seconds)
        except TimeoutError as exc:
            raise MqttPublishError("MQTT_TIMEOUT") from exc
        except Exception as exc:
            raise MqttPublishError("MQTT_PUBLISH_ERROR") from exc

        if not info.is_published():
            raise MqttPublishError("MQTT_TIMEOUT")
    finally:
        with suppress(Exception):
            client.disconnect()
        with suppress(Exception):
            client.loop_stop()

    logger.info(
        "event=actuator_command_published command_id=%s device_code=%s "
        "actuator_code=%s desired_state=%s",
        command_id,
        device_code,
        actuator_code,
        desired_state,
    )
