import asyncio
import json
import logging
import urllib.parse

import numpy as np

from modules.app_logger import app_logger
from modules.helper.livetrack import run_with_bt_tethering

_IMPORT_THINGSBOARD = False
try:
    from tb_device_mqtt import TBDeviceMqttClient, TBPublishInfo

    logging.getLogger("tb_connection").setLevel(logging.ERROR)
    _IMPORT_THINGSBOARD = True
except ImportError:
    TBDeviceMqttClient = None
    TBPublishInfo = None


class ThingsBoardLiveTrackClient:
    """Send ThingsBoard LiveTrack telemetry and course attributes."""

    # Leave room for the MQTT topic, packet identifier, properties, and header.
    MAX_COURSE_PAYLOAD_BYTES = 65536 - 128

    def __init__(self, config, gadgetbridge_service_getter):
        self.config = config
        self._gadgetbridge_service_getter = gadgetbridge_service_getter
        self.mqtt_client = None
        self.telemetry_url = None
        self.attributes_url = None
        self.course_send_status = "RESET"
        self.course_send_revision = 0

        settings = config.G_THINGSBOARD_API
        server = settings.get("SERVER", "").strip()
        if server and not server.startswith(("http://", "https://")):
            server = f"https://{server}"
        server = server.rstrip("/")
        token = settings.get("TOKEN", "").strip()

        if token and server:
            access_token = urllib.parse.quote(token, safe="")
            self.telemetry_url = f"{server}/api/v1/{access_token}/telemetry"
            self.attributes_url = f"{server}/api/v1/{access_token}/attributes"

        if _IMPORT_THINGSBOARD and token and server:
            self.mqtt_client = TBDeviceMqttClient(
                settings["SERVER"], 1883, settings["TOKEN"]
            )

    def enabled(self):
        return bool(self.config.G_THINGSBOARD_API.get("STATUS", False))

    def configuration_reason(self):
        settings = self.config.G_THINGSBOARD_API
        if not self.enabled():
            return None
        if not settings.get("TOKEN", "").strip():
            return "LiveTrack is disabled because ThingsBoard TOKEN is not configured."
        if not settings.get("SERVER", "").strip():
            return "LiveTrack is disabled because ThingsBoard server is not configured."
        return None

    def has_path(self):
        if self._gadgetbridge_service_getter() is not None:
            return True
        return (
            _IMPORT_THINGSBOARD
            and self.config.network.check_network_with_bt_tethering()
        )

    async def _send_via_gadgetbridge(self, url, data, timeout=15):
        service = self._gadgetbridge_service_getter()
        if service is None or url is None:
            return False
        try:
            await service.request_http(
                url,
                method="POST",
                headers={"Content-Type": "application/json"},
                body=data,
                timeout=timeout,
            )
        except Exception:
            app_logger.error("[GB] ThingsBoard HTTP request failed")
            return False
        return True

    def _publish_mqtt(self, method, data):
        self.mqtt_client.connect()
        try:
            return getattr(self.mqtt_client, method)(data).get()
        finally:
            self.mqtt_client.disconnect()

    async def _send_via_mqtt(self, data, caller_name, method, purpose):
        if self.mqtt_client is None:
            return None

        async def operation():
            try:
                result = await asyncio.to_thread(self._publish_mqtt, method, data)
                if result != TBPublishInfo.TB_ERR_SUCCESS:
                    app_logger.error(f"[BT] thingsboard upload error: {result}")
                    return None
                app_logger.debug(f"[TB][MQTT] {purpose} sent successfully")
                return "success"
            except Exception as exc:
                app_logger.error(f"[TB][MQTT] {purpose} failed: {type(exc).__name__}")
            return None

        status, value = await run_with_bt_tethering(
            self.config.network,
            caller_name,
            operation,
            log_prefix="[TB][MQTT]",
            purpose=purpose,
        )
        return value if status == "success" else status

    async def send_sample(self, sample, caller_name):
        data = sample.to_thingsboard_payload()
        if await self._send_via_gadgetbridge(self.telemetry_url, data):
            return True, "success"

        app_logger.warning("[TB] livetrack HTTP failed, falling back to MQTT")
        status = await self._send_via_mqtt(
            data, caller_name, "send_telemetry", "livetrack"
        )
        app_logger.debug(f"[TB] livetrack MQTT fallback completed: status={status}")
        return status == "success", status

    async def send_course(
        self, course, reset=False, caller_name="send_livetrack_course"
    ):
        if not reset and (not len(course.latitude) or not len(course.longitude)):
            return False

        course_path = []
        if not reset:
            points = np.round(np.stack([course.latitude, course.longitude], axis=1), 5)
            course_path = points[:1].tolist()
            low, high = 1, len(points)
            while low <= high:
                point_count = (low + high) // 2
                indexes = np.linspace(
                    0,
                    len(points) - 1,
                    point_count,
                    dtype=int,
                )
                candidate = points[indexes].tolist()
                payload_size = len(
                    json.dumps(
                        {"course_path": candidate}, separators=(",", ":")
                    ).encode()
                )
                if payload_size <= self.MAX_COURSE_PAYLOAD_BYTES:
                    course_path = candidate
                    low = point_count + 1
                else:
                    high = point_count - 1
        data = {"course_path": course_path}
        app_logger.debug(
            f"[TB] course send started: reset={reset}, points={len(course_path)}"
        )

        if await self._send_via_gadgetbridge(self.attributes_url, data):
            app_logger.debug("[TB] course sent via GadgetBridge HTTP")
            return True

        app_logger.debug("[TB] course HTTP failed, falling back to MQTT")
        status = await self._send_via_mqtt(
            data, caller_name, "send_attributes", "course"
        )
        if status != "success":
            return False
        app_logger.debug("[TB] course sent via MQTT")
        return True
