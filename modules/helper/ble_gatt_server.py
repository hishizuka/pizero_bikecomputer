import asyncio
import json
import re
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

    timestamp_str = ""
    timestamp_status = False
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

    # receive from central
    @characteristic(rx_characteristic_uuid, CharFlags.WRITE).setter
    def rx_characteristic(self, value, options):
        if value[0] == 0x10:
            self.value = bytearray()
            self.value_extend = True

            self.timestamp_status = False
            if (not self.timestamp_done or self.timestamp_status) and value[
                1:8
            ].decode() == "setTime":
                self.timestamp_str = value.decode()[1:]
                self.timestamp_status = True

        elif self.timestamp_status:
            self.timestamp_str += value.decode()

            res = re.match(
                "^setTime\((\d+)\);E.setTimeZone\((\S+)\)", self.timestamp_str
            )
            if res is not None:
                self.timestamp_done = True
                self.timestamp_status = False
                time_diff = datetime.timedelta(hours=float(res.group(2)))
                self.config.logger.sensor.sensor_gps.set_timediff_from_utc(time_diff)
                utctime = datetime.datetime.fromtimestamp(int(res.group(1))) - time_diff
                self.config.logger.sensor.sensor_gps.get_utc_time_from_datetime(utctime)

        if self.value_extend:
            self.value.extend(bytearray(value))

        # for gadgetbridge JSON message
        if (
            len(self.value) > 8
            and self.value[-3] == 0x7D
            and self.value[-2] == 0x29
            and self.value[-1] == 0x0A
        ):
            # remove emoji
            text_mod = re.sub(":\w+:", "", self.value.decode().strip()[5:-2])
            # add double quotation
            text_mod = re.sub('(\w+):("?\w*"?)', '"\\1":\\2', text_mod)
            message = {}
            try:
                message = json.loads("{" + text_mod + "}", strict=False)
            except:
                print("failed to load json")
                print(traceback.print_exc())
                print(self.value.decode().strip()[5:-2])
                print(text_mod)
                try:
                    message = json.loads("{" + text_mod + '"}', strict=False)
                except:
                    print("failed to load json (retry)")

            if (
                "t" in message
                and message["t"] == "notify"
                and "title" in message
                and "body" in message
            ):
                self.config.gui.show_message(
                    message["title"], message["body"], limit_length=True
                )
                print("success: ", message)
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

            self.value_extend = False

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
