import asyncio
import base64
import json
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
from modules.utils.asyncio import call_with_delay
from modules.utils.time import set_time
from logger import app_logger

# Message first and last byte markers
F_BYTE_MARKER = 0x10
L_BYTE_MARKER = 0x0A  # ord("\n")


class GadgetbridgeService(Service):
    service_uuid = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    rx_characteristic_uuid = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
    tx_characteristic_uuid = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

    product = None
    sensor = None
    gui = None
    bus = None

    status = False
    gps_status = False
    auto_connect_gps = False

    message = None

    timediff_from_utc = timedelta(hours=0)

    def __init__(self, product, sensor, gui, init_statuses=False):
        init_statuses = init_statuses or []
        self.product = product
        self.sensor = sensor
        self.gui = gui
        super().__init__(self.service_uuid, True)
        if init_statuses and init_statuses[0]:
            asyncio.create_task(self.on_off_uart_service())
            self.auto_connect_gps = init_statuses[1]

    async def quit(self):
        if not self.status and self.bus is not None:
            self.bus.disconnect()

    # direct access from central
    @characteristic(tx_characteristic_uuid, CharFlags.NOTIFY | CharFlags.READ)
    def tx_characteristic(self, options):
        return bytes(self.product, "utf-8")

    # notice to central
    def send_message(self, value):
        self.tx_characteristic.changed(bytes(value + "\\n\n", "utf-8"))

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
            app_logger.debug(f"Received message: {message_str}")
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
            advert = Advertisement(self.product, [self.service_uuid], 0, 60)
            await advert.register(self.bus, adapter)

        return self.status

    def on_off_gadgetbridge_gps(self):
        self.gps_status = not self.gps_status

        if self.gps_status:
            self.send_message('{t:"gps_power", status:true}')
        else:
            self.send_message('{t:"gps_power", status:false}')

        return self.gps_status

    @staticmethod
    def decode_b64(match_object):
        return f'"{base64.b64decode(match_object.group(1)).decode()}"'

    def decode_message(self, raw_message: str):
        message = raw_message.lstrip(chr(F_BYTE_MARKER)).rstrip(chr(L_BYTE_MARKER))

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
            message = message.lstrip("GB(").rstrip(")")
            # GadgetBridge uses a json-ish message format ('{t:"is_gps_active"}'), so we need to add "" to keys
            # It can also encode value in base64-ish using {key: atob("...")}
            try:
                message = re.sub(r'(\w+):("?\w*"?)', '"\\1":\\2', message)
                message = re.sub(r"atob\(\"(\S+)\"\)", self.decode_b64, message)

                message = json.loads(message, strict=False)

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
                        hdop = float(message["hdop"])
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
                            [hdop, hdop, hdop],
                            (int(message.get("satellites", 0)), None),
                            timestamp,
                        )
                    )
                elif m_type == "is_gps_active" and self.auto_connect_gps:
                    self.auto_connect_gps = False
                    call_with_delay(self.on_off_gadgetbridge_gps)
                elif m_type == "nav" and all(
                    [x in message for x in ["instr", "distance", "action"]]
                ):
                    # action
                    # "","continue",
                    # "left", "left_slight", "left_sharp",  "right", "right_slight", "right_sharp",
                    # "keep_left", "keep_right", "uturn_left", "uturn_right",
                    # "offroute",
                    # "roundabout_right", "roundabout_left", "roundabout_straight", "roundabout_uturn",
                    # "finish"
                    app_logger.info(message)
                    # blank distance: skip
                    # eta?
                    # app_logger.info(f"{len(self.value)}, {len(self.timestamp_bytes)}")
                    # msg = f"{message['distance']}, {message['action']}\n{message['instr']}"
                    # self.gui.show_forced_message(msg)

            except json.JSONDecodeError:
                app_logger.exception(f"Failed to load message as json {raw_message}")
            except Exception:  # noqa
                app_logger.exception(f"Failure during message {raw_message} handling")
        else:
            app_logger.warning(f"{raw_message} unknown message received")
