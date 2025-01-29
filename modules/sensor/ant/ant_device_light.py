import struct
from datetime import datetime
import array
import asyncio

from modules.app_logger import app_logger
from . import ant_device


class ANT_Device_Light(ant_device.ANT_Device):
    ant_config = {
        "interval": (4084, 16336, 32672),  # 4084 / 8168 / 16336 / 32672
        "type": 0x23,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    elements = (
        # "light_mode",
        # "pre_light_mode",
        # "button_state",
        # "auto_state",
        # "changed_timestamp",
        # "auto_on_timestamp",
    )
    page_34_count = 0
    light_retry_timeout = 5  #[s]
    auto_light_min_duration = 5  #[s]

    light_modes = {
        "bontrager_flare_rt": {
            "OFF": (0, 0x01),
            "STEADY_HIGH": (1, 0x06),  # mode 1, 4.5 hours
            "STEADY_MID": (5, 0x16),   # mode 5, 13.5 hours
            "FLASH_HIGH": (7, 0x1E),   # mode 7, 6 hours
            "FLASH_MID": (8, 0x22),    # mode 8, 12 hours
            "FLASH_LOW": (63, 0xFE),   # mode 63, 15 hours
        },
    }
    light_name = "bontrager_flare_rt"

    battery_levels = {
        0x00: "Not Use",
        0x01: "New/Full",
        0x02: "Good",
        0x03: "OK",
        0x04: "Low",
        0x05: "Critical",
        0x06: "Charging",
        0x07: "Invalid",
    }

    auto_off_status = {}

    pickle_key = "ant+_lgt_values"

    def set_timeout(self):
        self.channel.set_search_timeout(self.timeout)

    def setup_channel_extra(self):
        # 0:-18 dBm, 1:-12 dBm, 2:-6 dBm, 3:0 dBm, 4:N/A
        self.channel.set_channel_tx_power(0)

        self.send_queue = asyncio.Queue()
        asyncio.create_task(self.send_worker())

    @staticmethod
    def format_list(l):
        return "[" + " ".join(map(lambda a: str.format("{0:02x}", a), l)) + "]"

    async def send_worker(self):
        while True:
            data = await self.send_queue.get()
            if data is None:
                break
            try:
                if not self.channel.send_acknowledged_data_with_retry(data):
                    app_logger.error(f"ANT+ light acknowledged_data retry error: {self.format_list(data)}")
            # ant.easy.exception.AntException: Timed out while waiting for message
            except Exception as e:
                app_logger.error(f"{e}")
                app_logger.error(f"ANT+ light acknowledged_data timeout: {self.format_list(data)}")
            self.send_queue.task_done()

    def reset_value(self):
        self.values["pre_light_mode"] = None
        self.values["light_mode"] = None
        self.values["button_state"] = False
        self.values["auto_state"] = False
        self.values["changed_timestamp"] = None
        self.values["auto_on_timestamp"] = datetime.now()

    def close_extra(self):
        self.send_disconnect_light()
        if self.ant_state == "quit":
            asyncio.create_task(self.send_queue.put(None))
        self.reset_value()

    def init_after_connect(self):
        if (
            self.values["pre_light_mode"] is None
            and self.values["light_mode"] is None
            and self.ant_state in ["connect_ant_sensor"]
        ):
            self.send_connect_light()

    def get_light_mode(self, m):
        for k, v in self.light_modes[self.light_name].items():
            if m == v[0]:
                return k

    def on_data(self, data):
        if data[0] == 0x01:
            mode = self.get_light_mode(data[6] >> 2)
            seq_no = data[4]
            self.battery_status = self.battery_levels[data[2] >> 5]
            self.light_type = (data[2] >> 2) & 0b00011

            time_delta = None
            if self.values["changed_timestamp"] is not None:
                time_delta = (datetime.now() - self.values["changed_timestamp"]).total_seconds()
            if (
                self.values["light_mode"] is not None
                and time_delta is not None
                and seq_no != self.page_34_count
            ):
                #app_logger.info(f"{mode} / {self.values['light_mode']}, {seq_no} / {self.page_34_count}")
                if mode == self.values['light_mode']:
                    self.page_34_count = seq_no
                elif (
                    mode != self.values['light_mode']
                    and time_delta > self.light_retry_timeout
                ):
                    app_logger.info(
                        f"Retry to change light mode "
                        f"{mode} -> {self.values['light_mode']}, "
                        f"seq_no: {seq_no} != "
                        f"page_34_count: {self.page_34_count}, "
                        f"time_delta: {round(time_delta, 2)} > "
                        f"self.light_retry_timeout: {self.light_retry_timeout}"
                    )
                    self.page_34_count = seq_no
                    # send directly
                    self.send_light_setting_on_data(self.values["light_mode"])
        elif data[0] == 0x02:
            pass
        # Common Data Page 80 (0x50): Manufacturer’s Information
        elif data[0] == 0x50 and not self.values["stored_page"][0x50]:
            self.setCommonPage80(data, self.values)
        # Common Data Page 81 (0x51): Product Information
        elif data[0] == 0x51 and not self.values["stored_page"][0x51]:
            self.setCommonPage81(data, self.values)

    def send_connect_light(self):
        asyncio.create_task(
            self.send_queue.put(
                array.array(
                    "B",
                    struct.pack(
                        "<BBBBBHB",
                        0x21,
                        0x01,
                        0xFF,
                        0x5A,
                        0b01001000,
                        self.config.G_ANT["ID"][self.name],
                        0x00,
                    ),
                )
            )
        )
        # 5th field:
        #  ON:  0b01010000 (0x50): steady
        #       0b01011000 (0x58): steady
        #  OFF: 0b01001000 (0x48): off
        self.values["pre_light_mode"] = "OFF"
        self.values["light_mode"] = "OFF"

    def send_disconnect_light(self):
        self.channel.send_acknowledged_data_with_retry(
            array.array("B", [0x20, 0x01, 0x5A, 0x02, 0x00, 0x00, 0x00, 0x00])
        )

    def send_light_setting(self, mode):
        self.page_34_count = (self.page_34_count + 1) % 256
        asyncio.create_task(
            self.send_queue.put(
                array.array(
                    "B",
                    [
                        0x22,
                        0x01,
                        0x28,
                        self.page_34_count,
                        0x5A,
                        0x10,
                        self.light_modes[self.light_name][mode][1],
                        0x00,
                    ],
                )
            )
        )
        self.values["changed_timestamp"] = datetime.now()

    def send_light_setting_on_data(self, mode):
        asyncio.run_coroutine_threadsafe(
            self.send_queue.put(
                array.array(
                    "B",
                    [
                        0x22,
                        0x01,
                        0x28,
                        self.page_34_count,
                        0x5A,
                        0x10,
                        self.light_modes[self.light_name][mode][1],
                        0x00,
                    ],
                )
            ),
            self.config.loop
        )
        self.values["changed_timestamp"] = datetime.now()

    def send_light_mode(self, mode, auto_id=None):
        if mode == "OFF":
            self.change_light_setting_off(auto_id)
        elif mode == "ON_OFF_FLASH_LOW":
            if not self.values["button_state"]: # OFF -> ON
                self.change_light_setting("FLASH_LOW", auto_id)
            else: # ON -> OFF
                self.change_light_setting_off(auto_id)
        elif mode in self.light_modes[self.light_name].keys():
            self.change_light_setting(mode, auto_id)

    def change_light_setting(self, mode, auto_id=None):
        if auto_id is not None:
            self.auto_off_status[auto_id] = True

            if self.values["light_mode"] != "OFF":
                if not self.values["auto_state"]:
                    return
                else:
                    self.values["auto_on_timestamp"] = datetime.now()

        # auto_state + auto_id request: Turn on
        # auto_state + manual(auto_id is Null) request: Turn on
        # manual(not auto_state) + manual(auto_id is Null) request: Turn on
        # manual(not auto_state) + auto_id request: Turn on if OFF, don't turn on if other
        if auto_id is not None:
            self.values["auto_state"] = True
        else:
            self.values["button_state"] = True
            self.values["auto_state"] = False

        if self.values["light_mode"] != mode:
            self.values["light_mode"] = mode
            self.change_light_mode()

        # app_logger.info(f"change_light_setting: {self.values['light_mode']}, mode:{mode}, auto:{auto}, auto_state:{self.values['auto_state']}, button:{self.values['button_state']}, auto_id:{auto_id}")

    def change_light_mode(self):
        if (
            self.values["light_mode"] is not None
            and self.values["light_mode"] != self.values["pre_light_mode"]
        ):
            # app_logger.info(
            #     f"ANT+ Light mode change: {self.values['pre_light_mode']} -> {self.values['light_mode']}"
            # )
            self.values["pre_light_mode"] = self.values["light_mode"]
            self.send_light_setting(self.values["light_mode"])

    def change_light_setting_off(self, auto_id=None):
        if auto_id is not None:
            self.auto_off_status[auto_id] = False
        
            t = (datetime.now() - self.values["auto_on_timestamp"]).total_seconds()
            if (
                any(self.auto_off_status.values())
                or t < self.auto_light_min_duration
            ):
                return
    
            if not self.values["auto_state"]:
                return

        # auto_state + auto request: Turn off
        # auto_state + manual request: Turn off
        # manual(not auto_state) + manual request: Turn off
        # manual(not auto_state) + auto request: Don't turn off light
        if auto_id is not None:
            self.values["auto_state"] = True
        else:
            self.values["button_state"] = False
            self.values["auto_state"] = False

        if self.values["light_mode"] != "OFF":
            self.values["light_mode"] = "OFF"
            self.change_light_mode()

        # app_logger.info(f"change_light_setting_off: {self.values['light_mode']}, auto:{auto}, auto_state:{self.values['auto_state']}, button:{self.values['button_state']}, auto_id:{auto_id}")
