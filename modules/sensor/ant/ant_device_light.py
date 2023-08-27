import struct
import datetime
import time
import array
import threading
import queue

from logger import app_logger
from . import ant_device


class ANT_Device_Light(ant_device.ANT_Device):
    ant_config = {
        "interval": (4084, 4084, 4084),  # 4084 / 8168 / 16336 / 32672
        "type": 0x23,
        "transmission_type": 0x00,
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    elements = (
        "lgt_state",
        "pre_lgt_state",
        "button_state",
        "auto_state",
        "last_changed_timestamp",
    )
    page_34_count = 0
    light_retry_timeout = 5
    light_mode_bontrager_flare_rt = {
        "OFF": (0, 0x01),
        "ON_MAX": (1, 0x06),
        "ON_MID": (5, 0x16),
        "FLASH_H": (7, 0x1E),
        "FLASH_R": (8, 0x22),
        "FLASH_L": (63, 0xFE),
    }
    pickle_key = "ant+_lgt_values"

    def set_timeout(self):
        self.channel.set_search_timeout(self.timeout)

    def setup_channel_extra(self):
        # 0:-18 dBm, 1:-12 dBm, 2:-6 dBm, 3:0 dBm, 4:N/A
        self.channel.set_channel_tx_power(0)

        self.send_queue = queue.Queue()
        self.send_thread = threading.Thread(
            target=self.send_worker, name="send_worker", args=()
        )
        self.send_thread.start()

    def send_worker(self):
        for data in iter(self.send_queue.get, None):
            try:
                self.channel.send_acknowledged_data(data)
            except:
                app_logger.error(f"send_acknowledged_data failed: {data}")
            self.send_queue.task_done()

    def reset_value(self):
        self.values["pre_lgt_state"] = None
        self.values["lgt_state"] = None
        self.values["button_state"] = False
        self.values["auto_state"] = False
        self.values["last_changed_timestamp"] = datetime.datetime.now()

    def close_extra(self):
        if self.ant_state in ["quit", "disconnect_ant_sensor"]:
            self.send_disconnect_light()
            self.reset_value()
            self.send_queue.put(None)
            # need to wait for a pediod
            time.sleep(
                self.ant_config["interval"][self.config.G_ANT["INTERVAL"]] / 32672 + 0.5
            )

    def get_mode(self, m):
        for k, v in self.light_mode_bontrager_flare_rt.items():
            if m == v[0]:
                return k

    def init_after_connect(self):
        if (
            self.values["pre_lgt_state"] is None
            and self.values["lgt_state"] is None
            and self.ant_state in ["connect_ant_sensor"]
        ):
            self.send_connect_light()

    def on_data(self, data):
        if data[0] == 0x01:
            mode = self.get_mode(data[6] >> 2)
            seq_no = data[4]
            # print("###", mode, self.values['lgt_state'], self.page_34_count, seq_no, (datetime.datetime.now() - self.values['last_changed_timestamp']).total_seconds())
            if (
                self.values["lgt_state"] is not None
                and seq_no != self.page_34_count
                and (
                    datetime.datetime.now() - self.values["last_changed_timestamp"]
                ).total_seconds()
                > self.light_retry_timeout
            ):
                self.page_34_count -= 1
                app_logger.info(
                    f"Retry to change light mode...\n"
                    f"{mode}"
                    f"{self.values['lgt_state']}"
                    f"{seq_no}"
                    f"{self.page_34_count}"
                    f"{(datetime.datetime.now() - self.values['last_changed_timestamp']).total_seconds()}"
                )
                self.send_light_setting(self.values["lgt_state"])
            self.battery_status = data[2] >> 5
            self.light_type = (data[2] >> 2) & 0b00011
        elif data[0] == 0x02:
            pass
        # Common Data Page 80 (0x50): Manufacturer’s Information
        elif data[0] == 0x50 and not self.values["stored_page"][0x50]:
            self.setCommonPage80(data, self.values)
        # Common Data Page 81 (0x51): Product Information
        elif data[0] == 0x51 and not self.values["stored_page"][0x51]:
            self.setCommonPage81(data, self.values)

    def send_connect_light(self):
        self.send_queue.put(
            # ON: 0b01010000,0b01011000
            # array.array('B', struct.pack("<BBBBBHB",0x21,0x01,0xFF,0x5A,0x58,self.config.G_ANT['ID'][self.name],0x00))
            # OFF: 0b01001000
            array.array(
                "B",
                struct.pack(
                    "<BBBBBHB",
                    0x21,
                    0x01,
                    0xFF,
                    0x5A,
                    0x48,
                    self.config.G_ANT["ID"][self.name],
                    0x00,
                ),
            )
        )

    def send_disconnect_light(self):
        self.channel.send_acknowledged_data(
            array.array("B", [0x20, 0x01, 0x5A, 0x02, 0x00, 0x00, 0x00, 0x00])
        )

    def send_light_setting(self, mode):
        self.page_34_count = (self.page_34_count + 1) % 256
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
                    self.light_mode_bontrager_flare_rt[mode][1],
                    0x00,
                ],
            )
        )
        self.values["last_changed_timestamp"] = datetime.datetime.now()

    def send_light_setting_flash_low(self, auto=False):
        # mode 63, 15 hours
        self.send_light_setting_templete("FLASH_L", auto)

    def send_light_setting_flash_high(self, auto=False):
        # mode 7, 6 hours
        self.send_light_setting_templete("FLASH_H", auto)

    def send_light_setting_flash_mid(self, auto=False):
        # mode 8, 12 hours
        self.send_light_setting_templete("FLASH_R", auto)

    def send_light_setting_steady_high(self, auto=False):
        # mode 1, 4.5 hours
        self.send_light_setting_templete("ON_MAX", auto)

    def send_light_setting_steady_mid(self, auto=False):
        # mode 5, 13.5 hours
        self.send_light_setting_templete("ON_MID", auto)

    def check_mode(self):
        if (
            self.values["lgt_state"] is not None
            and self.values["lgt_state"] != self.values["pre_lgt_state"]
        ):
            app_logger.info(
                f"ANT+ Light mode change: {self.values['pre_lgt_state']} -> {self.values['lgt_state']}"
            )
            self.values["pre_lgt_state"] = self.values["lgt_state"]
            self.send_light_setting(self.values["lgt_state"])

    def send_light_setting_templete(self, mode, auto=False):
        if not auto:
            self.values["button_state"] = True
        else:
            self.values["auto_state"] = True

        if self.values["lgt_state"] != mode and (
            not auto or (auto and not self.values["button_state"])
        ):
            self.values["lgt_state"] = mode
            self.check_mode()
        # print("[ON] button:", self.values['button_state'], "lgt_state:", self.values['lgt_state'], "pre_lgt_state:", self.values['pre_lgt_state'])

    def send_light_setting_light_off(self, auto=False):
        if (
            not auto
            and self.values["auto_state"]
            and self.values["lgt_state"] != "OFF"
            and self.values["button_state"]
        ):
            self.values["button_state"] = False
            # print("button OFF only")
            return

        if not auto:
            self.values["button_state"] = False
        else:
            self.values["auto_state"] = False

        if self.values["lgt_state"] != "OFF" and (
            not auto or (auto and not self.values["button_state"])
        ):
            self.values["lgt_state"] = "OFF"
            self.check_mode()
        # print("[OFF] button:", self.values['button_state'], "lgt_state:", self.values['lgt_state'], "pre_lgt_state:", self.values['pre_lgt_state'])

    # button on/off only
    def send_light_setting_light_off_flash_low(self, auto=False):
        if not auto and not self.values["button_state"]:
            self.send_light_setting_flash_low()
        elif not auto and self.values["button_state"]:
            self.send_light_setting_light_off()
