import asyncio
import json
import re
import base64
import traceback
import datetime

from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import (
    characteristic,
    CharacteristicFlags as CharFlags,
)
from bluez_peripheral.util import *
from bluez_peripheral.advert import Advertisement
from bluez_peripheral.agent import NoIoAgent

from logger import app_logger


class GadgetbridgeService(Service):
    service_uuid = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    rx_characteristic_uuid = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
    tx_characteristic_uuid = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

    config = None
    bus = None

    status = False
    gps_status = False
    value = bytearray()
    value_extend = False

    timestamp_bytes = bytearray()
    timestamp_extend = False
    timestamp_done = False

    def __init__(self, config):
        self.config = config
        super().__init__(self.service_uuid, True)

    async def quit(self):
        if not self.status and self.bus is not None:
            self.bus.disconnect()

    # direct access from central
    @characteristic(tx_characteristic_uuid, CharFlags.NOTIFY | CharFlags.READ)
    def tx_characteristic(self, options):
        return bytes(self.config.G_PRODUCT, "utf-8")

    # notice to central
    def send_message(self, value):
        self.tx_characteristic.changed(bytes(value + "\\n\n", "utf-8"))

    def atob(self, matchobj):
        try:
            r = base64.b64decode(matchobj.group(1)).decode("utf-8", "ignore")
        except:
            r = ""
        return f'"{r}"'

    # receive from central
    @characteristic(rx_characteristic_uuid, CharFlags.WRITE).setter
    def rx_characteristic(self, value, options):
        app_logger.debug(value)

        # initialize
        if value.startswith(b'\x10GB({"') and not len(self.value):
            self.value_extend = True
        elif value.startswith(b'\x10setTime') and not self.timestamp_done and not len(self.timestamp_bytes):
            self.timestamp_extend = True

        # expand
        if self.timestamp_extend:
            self.timestamp_bytes.extend(bytearray(value))
        elif self.value_extend:
            self.value.extend(bytearray(value))
       
        # finalize: timestamp
        if self.timestamp_extend:
            res = re.match(
                "^setTime\((\d+)\);E.setTimeZone\((\S+)\)", self.timestamp_bytes.decode("utf-8", "ignore")[1:]
            )
            if res is not None:
                time_diff = datetime.timedelta(hours=float(res.group(2)))
                self.config.logger.sensor.sensor_gps.set_timediff_from_utc(time_diff)
                utctime = datetime.datetime.fromtimestamp(int(res.group(1))) - time_diff
                self.config.logger.sensor.sensor_gps.get_utc_time_from_datetime(utctime)
                self.timestamp_done = True
                self.timestamp_extend = False
                self.timestamp_bytes = bytearray()

        # finalize: gadgetbridge JSON message
        elif len(self.value) > 8 and self.value.endswith(b'})\n'):
            # remove emoji
            text_mod = re.sub(":\w+:", "", self.value.decode("utf-8", "ignore").strip()[5:-2])

            # decode base64
            b64_decode_ptn = re.compile(r"atob\(\"(\S+)\"\)")
            text_mod = re.sub(b64_decode_ptn, self.atob, text_mod)

            message = {}
            try:
                message = json.loads("{" + text_mod + "}", strict=False)
            except json.JSONDecodeError:
                app_logger.exception("failed to load json")
                app_logger.exception(self.value)
                app_logger.exception(text_mod)

            if (
                "t" in message
                and message["t"] == "notify"
                and "title" in message
                and "body" in message
            ):
                self.config.gui.show_message(
                    message["title"], message["body"], limit_length=True
                )
                app_logger.info(message)
            elif (
                "t" in message
                and len(message["t"]) >= 4
                and message["t"][0:4] == "find"
                and "n" in message
                and message["n"]
            ):
                self.config.gui.show_dialog_ok_only(fn=None, title="Gadgetbridge")
            elif "t" in message and message["t"] == "gps":
                asyncio.create_task(
                    self.config.logger.sensor.sensor_gps.update_GB(message)
                )
            elif (
                "t" in message
                and message["t"] == "nav"
                and "instr" in message
                and "distance" in message
                and "action" in message
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
                app_logger.info(f"{len(self.value)}, {len(self.timestamp_bytes)}")
                #msg = f"{message['distance']}, {message['action']}\n{message['instr']}"
                #self.config.gui.show_forced_message(msg)

            self.value_extend = False
            self.value = bytearray()

    async def on_off_uart_service(self):
        if self.status:
            self.bus.disconnect()
        else:
            self.bus = await get_message_bus()
            await self.register(self.bus)
            agent = NoIoAgent()
            await agent.register(self.bus)
            adapter = await Adapter.get_first(self.bus)
            advert = Advertisement(self.config.G_PRODUCT, [self.service_uuid], 0, 60)
            await advert.register(self.bus, adapter)

        self.status = not self.status

    def on_off_gadgetbridge_gps(self):
        if not self.gps_status:
            self.send_message('{t:"gps_power", status:true}')
        else:
            self.send_message('{t:"gps_power", status:false}')
        self.gps_status = not self.gps_status
