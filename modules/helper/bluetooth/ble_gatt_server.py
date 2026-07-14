import asyncio
from datetime import datetime
from pathlib import Path

from modules.app_logger import app_logger
from modules.utils.time import set_time

from gadgetbridge_rpi_link import (
    F_BYTE_MARKER,
    L_BYTE_MARKER,
    RX_CHARACTERISTIC_UUID,
    SERVICE_UUID,
    TX_CHARACTERISTIC_UUID,
    FindDeviceEvent,
    GadgetbridgeEvent,
    GadgetbridgeProtocol,
    GadgetbridgeSession,
    GpsActiveQueryEvent,
    GpsFixEvent,
    HttpResponseEvent,
    NavigationEvent,
    NotificationAddEvent,
    NotificationRemoveEvent,
    NotificationUpdateEvent,
    ParseErrorEvent,
    SetTimeEvent,
    UnknownGBEvent,
    UnknownRawEvent,
)
from gadgetbridge_rpi_link.bluez import BluezGadgetbridgeUartServer


class GadgetbridgeService:
    ANDROID_VOICE_COMMAND_ACTION = "android.intent.action.VOICE_COMMAND"
    ANDROID_ACTIVITY_NEW_TASK_FLAG = "FLAG_ACTIVITY_NEW_TASK"
    TERMUX_RUN_COMMAND_ACTION = "com.termux.RUN_COMMAND"
    TERMUX_RUN_COMMAND_CLASS = "com.termux.app.RunCommandService"
    TERMUX_RUN_COMMAND_PATH_EXTRA = "com.termux.RUN_COMMAND_PATH"
    TERMUX_RUN_COMMAND_BACKGROUND_EXTRA = "com.termux.RUN_COMMAND_BACKGROUND"

    _ASYNC_SESSION_METHODS = {
        "download_http_file",
        "download_http_files",
        "download_http_text_sample",
        "request_http",
        "request_http_json",
    }
    _SYNC_SESSION_METHODS = {
        "send_intent",
        "send_message",
    }

    service_uuid = SERVICE_UUID
    rx_characteristic_uuid = RX_CHARACTERISTIC_UUID
    tx_characteristic_uuid = TX_CHARACTERISTIC_UUID

    def __init__(
        self,
        product,
        sensor,
        gui,
        init_statuses=False,
    ):
        init_statuses = init_statuses or []
        self.product = product
        self.sensor = sensor
        self.gui = gui
        self.status = False
        self.gps_status = False
        self.auto_connect_gps = False
        self.server = None
        self.bus = None
        self.protocol = GadgetbridgeProtocol()
        self.session = GadgetbridgeSession(
            sender=self._send_message,
            protocol=self.protocol,
        )
        self.termux_command = None
        self.logger = app_logger
        self._startup_task = None
        self._nav_message_cache = None

        if init_statuses and init_statuses[0]:
            self.auto_connect_gps = init_statuses[1]
            self.logger.info(
                "[GB] auto-start requested: "
                f"product={self.product!r}, gps={self.auto_connect_gps}"
            )
            self._startup_task = asyncio.create_task(self.on_off_uart_service())
            self._startup_task.add_done_callback(self._log_startup_task_result)

    def _log_startup_task_result(self, task):
        try:
            status = task.result()
        except asyncio.CancelledError:
            self.logger.debug("[GB] auto-start cancelled")
        except Exception:
            self.logger.exception("[GB] auto-start failed")
        else:
            self.logger.info(f"[GB] auto-start completed: status={status}")

    async def quit(self):
        if self.status:
            await self._stop_server()

    def _send_message(self, value):
        if self.server is None:
            raise RuntimeError("Gadgetbridge UART service is not started")
        return self.server.send(value)

    def start_termux_voice_command(self):
        if not self.termux_command:
            self.logger.warning("[GB] Termux command is not configured")
            return None
        self._ensure_uart_enabled()
        return self.session.send_intent(
            self.TERMUX_RUN_COMMAND_ACTION,
            target="service",
            package="com.termux",
            class_name=self.TERMUX_RUN_COMMAND_CLASS,
            extra={
                self.TERMUX_RUN_COMMAND_PATH_EXTRA: self.termux_command,
                self.TERMUX_RUN_COMMAND_BACKGROUND_EXTRA: True,
            },
        )

    def start_google_assistant(self):
        self._ensure_uart_enabled()
        return self.session.send_intent(
            self.ANDROID_VOICE_COMMAND_ACTION,
            flags=[self.ANDROID_ACTIVITY_NEW_TASK_FLAG],
        )

    def _ensure_uart_enabled(self):
        if not self.status:
            raise RuntimeError("Gadgetbridge UART service is disabled")

    def __getattr__(self, name):
        if name in self._ASYNC_SESSION_METHODS:
            method = getattr(self.session, name)

            async def async_session_method(*args, **kwargs):
                self._ensure_uart_enabled()
                return await method(*args, **kwargs)

            return async_session_method

        if name in self._SYNC_SESSION_METHODS:
            method = getattr(self.session, name)

            def session_method(*args, **kwargs):
                self._ensure_uart_enabled()
                return method(*args, **kwargs)

            return session_method

        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")

    async def show_gadgetbridge_download(
        self,
        url,
        output_dir="tmp",
        save_name=None,
        binary=True,
        timeout=600,
    ):
        try:
            self._ensure_uart_enabled()
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            if save_name is None:
                save_name = (
                    "gadgetbridge_http_test_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
            save_path = output_path / save_name
            await self.session.download_http_file(
                url,
                save_path,
                headers={"User-Agent": self.product},
                timeout=timeout,
                binary=binary,
            )
        except Exception as exc:
            self.logger.error(f"Gadgetbridge HTTP test error: {exc!r}")
            return None

        result = str(save_path)
        self.logger.debug(f"[GB][HTTP][TEST] result: {result!r}")
        return result

    @classmethod
    def _format_received_message_for_log(cls, message_str):
        message_str = message_str.lstrip(chr(F_BYTE_MARKER)).rstrip(
            chr(L_BYTE_MARKER)
        )

        if len(message_str) <= 512:
            return message_str

        if '"t":"http"' in message_str or 't:"http"' in message_str:
            return f"[GB][HTTP][RX] len={len(message_str)}, payload omitted"

        return f"{message_str[:256]}... (truncated, len={len(message_str)})"

    def _log_http_response_event(self, event):
        pending = getattr(self.session, "_http_pending", {})
        request_id = str(event.request_id) if event.request_id is not None else None
        pending_status = "pending" if request_id in pending else "no-pending"
        response = event.response
        if isinstance(response, bytes | bytearray):
            response_info = f"type=bytes, len={len(response)}"
        elif isinstance(response, str):
            response_info = f"type=str, len={len(response)}"
        elif response is None:
            response_info = "type=None, len=0"
        else:
            response_info = f"type={type(response).__name__}"

        log_message = (
            f"[GB][HTTP][RX] id={request_id!r}, {pending_status}, "
            f"error={event.error!r}, {response_info}"
        )
        if event.error:
            self.logger.warning(log_message)
        else:
            self.logger.debug(log_message)

    def rx_characteristic(self, value, options=None):
        del options
        self._dispatch_events(self.protocol.feed_rx(bytes(value)))

    async def on_off_uart_service(self):
        self.status = not self.status

        if not self.status:
            await self._stop_server()
            self.logger.info("[GB] Gadgetbridge UART service stopped")
            return self.status

        try:
            self.logger.info(
                f"[GB] starting Gadgetbridge UART service: product={self.product!r}"
            )
            self.server = BluezGadgetbridgeUartServer(
                product=self.product,
                on_event=self._handle_event,
                protocol=self.protocol,
            )
            await self.server.start()
            self.bus = self.server.bus
        except Exception:
            self.status = False
            self.server = None
            self.bus = None
            raise
        self.logger.info("[GB] Gadgetbridge UART service started")
        return self.status

    async def _stop_server(self):
        if self.server is not None:
            await self.server.stop()
            self.server = None
            self.bus = None
            return

        if self.bus is not None:
            self.bus.disconnect()
            self.bus = None

    def on_off_gadgetbridge_gps(self):
        next_status = not self.gps_status
        try:
            self._ensure_uart_enabled()
            self.logger.info(f"[GB][GPS] send gps_power: status={next_status}")
            self.session.gps_power(next_status)
        except Exception as exc:
            self.logger.error(
                "[GB] failed to toggle Gadgetbridge GPS: "
                f"{type(exc).__name__}: {exc!r}"
            )
            return self.gps_status

        self.gps_status = next_status
        return self.gps_status

    def decode_message(self, raw_message: str):
        self._dispatch_events(self.protocol.parse_text(raw_message))

    def _dispatch_events(self, events):
        for event in events:
            raw_text = getattr(event, "raw_text", "")
            if raw_text:
                self.logger.debug(
                    "Received message: "
                    f"{self._format_received_message_for_log(raw_text)}"
                )
            self._handle_event(event)

    def _handle_event(self, event: GadgetbridgeEvent):
        if isinstance(event, HttpResponseEvent):
            self._log_http_response_event(event)

        self.session.handle_event(event)

        if isinstance(event, NotificationAddEvent | NotificationUpdateEvent):
            self._show_notification(event)
        elif isinstance(event, NotificationRemoveEvent):
            self._remove_notification(event)
        elif isinstance(event, FindDeviceEvent) and event.active:
            self._show_find_device_dialog(event)
        elif isinstance(event, GpsFixEvent):
            asyncio.create_task(self._update_sensor_gps(event))
        elif isinstance(event, GpsActiveQueryEvent):
            if self.auto_connect_gps:
                self.logger.info("[GB][GPS] active query received; request GPS ON")
                self.auto_connect_gps = False
                self._call_gps_power_soon()
            else:
                self.logger.debug("[GB][GPS] active query received; auto GPS disabled")
        elif isinstance(event, NavigationEvent):
            self._handle_navigation(event)
        elif isinstance(event, SetTimeEvent):
            self.logger.info(f"[GB] setTime received: utc={event.utc_time.isoformat()}")
            self._set_system_time(event)
        elif isinstance(event, ParseErrorEvent):
            self.logger.error(
                "[GB] failed to parse message: "
                f"{event.error}; raw={event.raw_text!r}"
            )
        elif isinstance(event, UnknownGBEvent):
            self.logger.warning(f"[GB] unknown message received: {event.raw!r}")
        elif isinstance(event, UnknownRawEvent):
            self.logger.warning(f"{event.raw_text} unknown message received")

    def _call_gps_power_soon(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.on_off_gadgetbridge_gps()
            return
        loop.call_soon(self.on_off_gadgetbridge_gps)

    def _show_notification(self, event):
        if event.title or event.body:
            self.gui.show_message(event.title, event.body, limit_length=True)

    def _remove_notification(self, event):
        app_logger.debug(f"[GB][NOTIFY] remove notification: id={event.id!r}")

    def _show_find_device_dialog(self, _event):
        self.gui.show_dialog_ok_only(fn=None, title="Gadgetbridge")

    async def _update_sensor_gps(self, event):
        sensor = self.sensor
        if sensor is None:
            return

        null = sensor.NULL_VALUE
        hdop_values = (
            [event.hdop, event.hdop, event.hdop]
            if event.hdop is not None
            else [null, null, null]
        )
        await sensor.get_basic_values(
            event.lat if event.lat is not None else null,
            event.lon if event.lon is not None else null,
            event.alt_m if event.alt_m is not None else null,
            event.speed_mps if event.speed_mps is not None else null,
            int(event.course_deg) if event.course_deg is not None else null,
            event.fix_mode if event.fix_mode is not None else null,
            None,
            None,
            hdop_values,
            (event.satellites or 0, None),
            event.timestamp_utc if event.timestamp_utc is not None else null,
        )

    def _handle_navigation(self, event):
        if self._has_active_course():
            return

        cache_key = (event.action, event.distance_text, event.instruction)
        if cache_key == self._nav_message_cache:
            return
        self._nav_message_cache = cache_key

        if event.should_clear:
            self.gui.clear_external_instruction()
            app_logger.debug(
                "[GB][NAV] clear instruction: "
                f"action={event.action!r}, distance={event.distance_text!r}, "
                f"instr={event.instruction!r}"
            )
            return

        self.gui.set_external_instruction(event.turn_type, event.distance_m)
        app_logger.debug(
            "[GB][NAV] update instruction: "
            f"action={event.action!r}, distance={event.distance_text!r}, "
            f"instr={event.instruction!r}, turn_type={event.turn_type!r}, "
            f"distance_m={event.distance_m:.1f}"
        )

    def _has_active_course(self):
        try:
            return bool(self.gui.config.logger.course.is_set)
        except Exception:
            return False

    def _set_system_time(self, event):
        set_time(event.utc_time.isoformat())
