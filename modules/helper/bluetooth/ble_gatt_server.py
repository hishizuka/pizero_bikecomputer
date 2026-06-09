import asyncio
import base64
import json
import os
import re
from datetime import datetime, timedelta, timezone

try:
    from bluez_peripheral.gatt.service import Service
    from bluez_peripheral.gatt.characteristic import (
        characteristic,
        CharacteristicFlags as CharFlags,
    )
    from bluez_peripheral.util import *
    from bluez_peripheral.advert import Advertisement
    from bluez_peripheral.agent import NoIoAgent
except ImportError:
    raise ImportError("Missing bluez requirements")

from modules.sensor.gps.base import (
    HDOP_CUTOFF_FAIR,
    HDOP_CUTOFF_MODERATE,
    NMEA_MODE_2D,
    NMEA_MODE_3D,
    NMEA_MODE_NO_FIX,
)
from modules.utils.navigation import (
    gadgetbridge_action_to_turn_type,
    parse_gadgetbridge_distance,
)
from modules.utils.asyncio import call_with_delay
from modules.utils.time import set_time
from modules.app_logger import app_logger

# Message first and last byte markers
F_BYTE_MARKER = 0x10
L_BYTE_MARKER = 0x0A  # ord("\n")


class GadgetbridgeService(Service):
    service_uuid = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    rx_characteristic_uuid = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
    tx_characteristic_uuid = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    _ATOB_SENTINEL_KEY = "__gb_atob__"
    _PNG_SIGNATURE = "\x89PNG\r\n\x1a\n"
    _TX_CHUNK_SIZE = 20
    _HDOP_UEAE = 6

    product = None
    sensor = None
    gui = None
    bus = None

    status = False
    gps_status = False
    auto_connect_gps = False

    message = None

    termux_command = None
    _tx_lock = None
    _http_request_id = 0
    _http_pending_requests = None
    _nav_message_cache = None

    timediff_from_utc = timedelta(hours=0)

    def __init__(self, product, sensor, gui, init_statuses=False):
        init_statuses = init_statuses or []
        self.product = product
        self.sensor = sensor
        self.gui = gui
        self._tx_lock = None
        self._http_request_id = 0
        self._http_pending_requests = {}
        self._nav_message_cache = None
        super().__init__(self.service_uuid, True)
        if init_statuses and init_statuses[0]:
            asyncio.create_task(self.on_off_uart_service())
            self.auto_connect_gps = init_statuses[1]

    async def quit(self):
        if self.status and self.bus is not None:
            self.bus.disconnect()

    # direct access from central
    @characteristic(tx_characteristic_uuid, CharFlags.NOTIFY | CharFlags.READ)
    def tx_characteristic(self, options):
        return bytes(self.product, "utf-8")

    def _build_tx_payload(self, value):
        return bytes(value + "\\n\n", "utf-8")

    def _send_message_sync(self, value):
        payload = self._build_tx_payload(value)
        for i in range(0, len(payload), self._TX_CHUNK_SIZE):
            self.tx_characteristic.changed(payload[i : i + self._TX_CHUNK_SIZE])

    async def _send_message_async(self, value):
        if self._tx_lock is None:
            self._tx_lock = asyncio.Lock()

        payload = self._build_tx_payload(value)
        async with self._tx_lock:
            for i in range(0, len(payload), self._TX_CHUNK_SIZE):
                self.tx_characteristic.changed(payload[i : i + self._TX_CHUNK_SIZE])
                await asyncio.sleep(0)

    # notice to central
    def send_message(self, value):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._send_message_sync(value)
            return None
        return loop.create_task(self._send_message_async(value))

    def send_intent(self, action, target="activity", flags=None, **kwargs):
        message = {
            "t": "intent",
            "target": target,
            "action": action,
        }
        if flags:
            message["flags"] = flags
        message.update(kwargs)
        self.send_message(json.dumps(message, separators=(",", ":")))

    def start_google_assistant(self):
        self.send_intent(
            action="android.intent.action.VOICE_COMMAND",
            flags=["FLAG_ACTIVITY_NEW_TASK"],
        )

    def run_termux_command(self, command_path):
        self.send_intent(
            target="service",
            action="com.termux.RUN_COMMAND",
            package="com.termux",
            **{
                "class": "com.termux.app.RunCommandService",
                "extra": {
                    "com.termux.RUN_COMMAND_PATH": command_path,
                    "com.termux.RUN_COMMAND_BACKGROUND": True,
                },
            },
        )

    def start_termux_voice_command(self):
        if self.termux_command is not None:
            self.run_termux_command(self.termux_command)

    @staticmethod
    def _get_nav_message_cache_key(message):
        return (
            str(message.get("action", "")).strip().lower(),
            str(message.get("distance", "")).replace("\u00A0", " ").strip(),
            str(message.get("instr", "")).strip(),
        )

    def _ensure_http_state(self):
        if self._http_pending_requests is None:
            self._http_pending_requests = {}

    def _has_active_course(self):
        try:
            return bool(self.gui.config.logger.course.is_set)
        except Exception:
            return False

    def _handle_nav_message(self, message):
        if any(key not in message for key in ("distance", "action")):
            return

        if self._has_active_course():
            return

        cache_key = self._get_nav_message_cache_key(message)
        if cache_key == self._nav_message_cache:
            return
        self._nav_message_cache = cache_key

        instruction_name = gadgetbridge_action_to_turn_type(cache_key[0])
        instruction_distance = parse_gadgetbridge_distance(cache_key[1])

        if instruction_name and instruction_distance is not None:
            self.gui.set_external_instruction(instruction_name, instruction_distance)
            app_logger.debug(
                "[GB][NAV] update instruction: "
                f"action={cache_key[0]!r}, distance={cache_key[1]!r}, "
                f"instr={cache_key[2]!r}, turn_type={instruction_name!r}, "
                f"distance_m={instruction_distance:.1f}"
            )
            return

        self.gui.clear_external_instruction()
        app_logger.debug(
            "[GB][NAV] clear instruction: "
            f"action={cache_key[0]!r}, distance={cache_key[1]!r}, "
            f"instr={cache_key[2]!r}"
        )

    def _next_http_request_id(self):
        self._ensure_http_state()
        self._http_request_id += 1
        return str(self._http_request_id)

    async def request_http(
        self,
        url,
        method="GET",
        headers=None,
        body=None,
        timeout=30,
        insecure=False,
        xpath=None,
        return_type=None,
    ):
        if not self.status:
            raise RuntimeError("Gadgetbridge UART service is disabled")

        self._ensure_http_state()
        loop = asyncio.get_running_loop()
        request_id = self._next_http_request_id()
        future = loop.create_future()
        self._http_pending_requests[request_id] = future

        message = {
            "t": "http",
            "id": request_id,
            "url": url,
        }
        method = method.upper()
        if method != "GET":
            message["method"] = method
        if headers:
            message["headers"] = {str(key): str(value) for key, value in headers.items()}
        if body is not None:
            if not isinstance(body, str):
                body = json.dumps(body, separators=(",", ":"))
            message["body"] = body
        if insecure:
            message["insecure"] = True
        if xpath:
            message["xpath"] = xpath
        if return_type:
            message["return"] = return_type

        send_task = self.send_message(json.dumps(message, separators=(",", ":")))
        if send_task is not None:
            await send_task

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            app_logger.warning(
                "[GB][HTTP] request timed out: "
                f"id={request_id}, timeout={timeout}, url={url}"
            )
            raise
        except Exception as exc:
            app_logger.warning(
                "[GB][HTTP] request failed: "
                f"id={request_id}, type={type(exc).__name__}, detail={exc!r}"
            )
            raise
        finally:
            pending = self._http_pending_requests.get(request_id)
            if pending is future:
                self._http_pending_requests.pop(request_id, None)

    async def request_http_json(self, *args, **kwargs):
        response = await self.request_http(*args, **kwargs)
        payload = response.get("resp")
        if payload in (None, ""):
            return None
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        return json.loads(payload)

    @classmethod
    def _encode_http_download_payload(cls, payload, save_path=""):
        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload)
        if isinstance(payload, str):
            if payload.startswith(cls._PNG_SIGNATURE):
                return payload.encode("latin-1")
            return payload.encode("utf-8")
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _normalize_http_batch_values(name, values, expected_length, default_value):
        if values is None:
            return [default_value] * expected_length

        value_list = list(values)
        if len(value_list) != expected_length:
            raise ValueError(
                f"{name} length mismatch: expected {expected_length}, "
                f"got {len(value_list)}"
            )
        return value_list

    async def download_http_file(
        self,
        url,
        save_path,
        headers=None,
        method="GET",
        body=None,
        timeout=120,
        insecure=False,
    ):
        response = await self.request_http(
            url,
            method=method,
            headers=headers,
            body=body,
            timeout=timeout,
            insecure=insecure,
        )
        data = self._encode_http_download_payload(response.get("resp", ""), save_path)
        await asyncio.to_thread(self._write_http_download, save_path, data)
        return 200

    @staticmethod
    def _write_http_download(save_path, data):
        with open(save_path, "wb") as file_handle:
            file_handle.write(data)

    async def download_http_files(
        self,
        urls,
        save_paths,
        headers=None,
        methods=None,
        bodies=None,
        timeout=120,
        limit=None,
        insecure=False,
    ):
        url_list = list(urls)
        save_path_list = list(save_paths)
        if len(url_list) != len(save_path_list):
            raise ValueError(
                "save_paths length mismatch: "
                f"expected {len(url_list)}, got {len(save_path_list)}"
            )

        max_concurrency = limit or len(url_list) or 1
        semaphore = asyncio.Semaphore(max(1, max_concurrency))
        method_list = self._normalize_http_batch_values(
            "methods",
            methods,
            len(url_list),
            "GET",
        )
        body_list = self._normalize_http_batch_values(
            "bodies",
            bodies,
            len(url_list),
            None,
        )

        async def _download_one(url, save_path, method, body):
            async with semaphore:
                try:
                    return await self.download_http_file(
                        url,
                        save_path,
                        headers=headers,
                        method=method,
                        body=body,
                        timeout=timeout,
                        insecure=insecure,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    app_logger.error(f"Gadgetbridge HTTP download error: {exc}\n{url}")
                    return -1

        tasks = [
            _download_one(url, save_path, method, body)
            for url, save_path, method, body in zip(
                url_list, save_path_list, method_list, body_list
            )
        ]
        return await asyncio.gather(*tasks)

    async def show_gadgetbridge_download(
        self,
        url="https://tile.openstreetmap.org/13/7236/3225.png",
        output_dir="tmp",
    ):
        headers = {"User-Agent": self.product}

        if url.lower().endswith(".png"):
            os.makedirs(output_dir, exist_ok=True)
            save_path = os.path.join(
                output_dir,
                f"gadgetbridge_http_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            )
            try:
                status = await self.download_http_file(
                    url,
                    save_path,
                    headers=headers,
                    timeout=120,
                )
            except Exception as exc:
                app_logger.error(f"Gadgetbridge HTTP test error: {exc!r}")
                return

            app_logger.debug(
                f"[GB][HTTP][TEST] PNG download completed: status={status}, "
                f"save_path={save_path}"
            )
            return

        try:
            response = await self.request_http(
                url,
                headers=headers,
                timeout=30,
            )
        except Exception as exc:
            app_logger.error(f"Gadgetbridge HTTP test error: {exc!r}")
            return

        body = response.get("resp", "")
        if body is None:
            app_logger.debug("[GB][HTTP][TEST] empty response")
            return

        if isinstance(body, (bytes, bytearray)):
            body = bytes(body)
            app_logger.debug(
                "[GB][HTTP][TEST] response: "
                f"type=bytes, len={len(body)}, head_hex={body[:16].hex()}"
            )
            return

        text = str(body)
        app_logger.debug(
            "[GB][HTTP][TEST] response: "
            f"type={type(body).__name__}, len={len(text)}, preview={text[:80]!r}"
        )

    def _complete_http_request(self, message):
        self._ensure_http_state()
        request_id = message.get("id")
        if request_id is None:
            app_logger.warning(f"Gadgetbridge HTTP response without id: {message}")
            return

        future = self._http_pending_requests.pop(str(request_id), None)
        if future is None:
            app_logger.warning(
                f"Gadgetbridge HTTP response has no pending request: {message}"
            )
            return
        if future.done():
            return

        if "err" in message and message["err"]:
            app_logger.warning(
                "[GB][HTTP] response error: "
                f"id={request_id}, detail={message['err']!r}"
            )
            future.set_exception(RuntimeError(message["err"]))
            return

        future.set_result(message)

    @staticmethod
    def _strip_message_markers(message_str):
        return message_str.lstrip(chr(F_BYTE_MARKER)).rstrip(chr(L_BYTE_MARKER))

    @classmethod
    def _format_received_message_for_log(cls, message_str):
        message_str = cls._strip_message_markers(message_str)

        if len(message_str) <= 512:
            return message_str

        if '"t":"http"' in message_str or 't:"http"' in message_str:
            request_id = None
            for pattern in (r'"id":"([^"]+)"', r'"id":(\d+)', r'id:"([^"]+)"', r'id:(\d+)'):
                match = re.search(pattern, message_str)
                if match is not None:
                    request_id = match.group(1)
                    break
            request_id_str = f", id={request_id}" if request_id is not None else ""
            return (
                f"[GB][HTTP][RX] len={len(message_str)}{request_id_str}, "
                "payload omitted"
            )

        return f"{message_str[:256]}... (truncated, len={len(message_str)})"

    # receive from central
    @characteristic(rx_characteristic_uuid, CharFlags.WRITE).setter
    def rx_characteristic(self, value, options):
        # GB messages handler/decoder
        # messages are sent as \x10<content>\n (https://www.espruino.com/Gadgetbridge)
        # They are mostly \x10GB<content>\n but the setTime message which does not have the GB prefix
        if value[0] == F_BYTE_MARKER:
            if self.message:
                app_logger.warning(
                    f"Previous message was not received fully and got discarded: {self.message}"
                )
            self.message = bytearray(value)
        else:
            self.message.extend(bytearray(value))

        if self.message[-1] == L_BYTE_MARKER:
            # full message received, we can decode it
            message_str = self.message.decode("utf-8", "ignore")
            app_logger.debug(
                f"Received message: {self._format_received_message_for_log(message_str)}"
            )
            self.decode_message(message_str)
            self.message = None

    async def on_off_uart_service(self):
        self.status = not self.status

        if not self.status:
            self.bus.disconnect()
        else:
            self.bus = await get_message_bus()
            await self.register(self.bus)
            agent = NoIoAgent()
            await agent.register(self.bus)
            adapter = await Adapter.get_first(self.bus)
            advert = Advertisement(self.product, [self.service_uuid], 0, 180)
            await advert.register(self.bus, adapter)

        return self.status

    def on_off_gadgetbridge_gps(self):
        self.gps_status = not self.gps_status

        if self.gps_status:
            self.send_message('{t:"gps_power", status:true}')
        else:
            self.send_message('{t:"gps_power", status:false}')

        return self.gps_status

    @classmethod
    def _replace_atob_expression(cls, match_object):
        encoded = match_object.group(1)
        return f'{{"{cls._ATOB_SENTINEL_KEY}":"{encoded}"}}'

    @classmethod
    def _decode_atob_payload(cls, payload):
        data = base64.b64decode(payload)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data

    @classmethod
    def _decode_atob_values(cls, payload):
        if isinstance(payload, list):
            return [cls._decode_atob_values(value) for value in payload]
        if isinstance(payload, dict):
            if set(payload.keys()) == {cls._ATOB_SENTINEL_KEY}:
                return cls._decode_atob_payload(payload[cls._ATOB_SENTINEL_KEY])
            return {
                key: cls._decode_atob_values(value) for key, value in payload.items()
            }
        return payload

    def decode_message(self, raw_message: str):
        message = self._strip_message_markers(raw_message)

        if message.startswith("setTime"):
            res = re.match(r"^setTime\((\d+)\);E.setTimeZone\((\S+)\);", message)

            if res is not None:
                time_diff = timedelta(hours=float(res.group(2)))
                self.timediff_from_utc = time_diff
                # we have a known time fix, we can use it to set the time of the system before we get gps fix
                utctime = (
                    (
                        datetime.fromtimestamp(int(res.group(1)))
                        - time_diff
                        # we could also account for the time of message reception
                    )
                    .replace(tzinfo=timezone.utc)
                    .isoformat()
                )
                set_time(utctime)

        elif message.startswith("GB("):
            message = message[len("GB(") :]
            if message.endswith(")"):
                message = message[:-1]
            # GadgetBridge uses a json-ish message format ('{t:"is_gps_active"}'), so we need to add "" to keys
            # It can also encode value in base64-ish using {key: atob("...")}
            try:
                message = re.sub(
                    r'([{,]\s*)([A-Za-z_][\w-]*)\s*:',
                    r'\1"\2":',
                    message,
                )
                message = re.sub(
                    r'atob\("([^\"]+)"\)',
                    self._replace_atob_expression,
                    message,
                )

                message = json.loads(message, strict=False)
                message = self._decode_atob_values(message)

                m_type = message.get("t")

                if m_type == "notify" and "title" in message and "body" in message:
                    self.gui.show_message(
                        message["title"], message["body"], limit_length=True
                    )
                elif m_type.startswith("find") and message.get("n", False):
                    self.gui.show_dialog_ok_only(fn=None, title="Gadgetbridge")
                elif m_type == "gps":
                    # encode gps message
                    lat = lon = alt = speed = track = self.sensor.NULL_VALUE
                    hdop = mode = timestamp = self.sensor.NULL_VALUE
                    if "lat" in message and "lon" in message:
                        lat = float(message["lat"])
                        lon = float(message["lon"])
                    if "alt" in message:
                        alt = float(message["alt"])
                    if "speed" in message:
                        speed = float(message["speed"])
                        if speed != 0.0:
                            speed = speed / 3.6  # km/h -> m/s
                    if "course" in message:
                        track = int(message["course"])
                    if "time" in message:
                        timestamp = (
                            datetime.fromtimestamp(message["time"] // 1000)
                            - self.timediff_from_utc
                        ).replace(tzinfo=timezone.utc)
                    if "hdop" in message:
                        hdop = float(message["hdop"]) / self._HDOP_UEAE  # different from NMEA hdop
                        if hdop < HDOP_CUTOFF_MODERATE:
                            mode = NMEA_MODE_3D
                        elif hdop < HDOP_CUTOFF_FAIR:
                            mode = NMEA_MODE_2D
                        else:
                            mode = NMEA_MODE_NO_FIX

                    asyncio.create_task(
                        self.sensor.get_basic_values(
                            lat,
                            lon,
                            alt,
                            speed,
                            track,
                            mode,
                            None,
                            None,
                            [hdop, hdop, hdop],
                            (int(message.get("satellites", 0)), None),
                            timestamp,
                        )
                    )
                elif m_type == "is_gps_active" and self.auto_connect_gps:
                    self.auto_connect_gps = False
                    call_with_delay(self.on_off_gadgetbridge_gps)
                elif m_type == "http":
                    self._complete_http_request(message)
                elif m_type == "nav":
                    self._handle_nav_message(message)

            except json.JSONDecodeError:
                app_logger.exception(f"Failed to load message as json {raw_message}")
            except Exception:  # noqa
                app_logger.exception(f"Failure during message {raw_message} handling")
        else:
            app_logger.warning(f"{raw_message} unknown message received")
