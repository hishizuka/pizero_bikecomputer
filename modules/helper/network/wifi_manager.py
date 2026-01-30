import asyncio
import json
import shutil
import os

from modules.app_logger import app_logger
from modules.utils.cmd import exec_cmd, exec_cmd_return_value


BOOT_FILE = "/boot/firmware/config.txt"


def get_wifi_bt_status():
    if shutil.which("rfkill") is None:
        return False, False

    status = {"wlan": False, "bluetooth": False}
    try:
        raw_status, _ = exec_cmd_return_value([
            "sudo",
            "rfkill",
            "--json",
        ], cmd_print=False)
        json_status = json.loads(raw_status)
        _parse_wifi_bt_json(json_status, status, ["", "rfkilldevices"])
    except Exception as exc:
        app_logger.warning(
            f"Exception occurred trying to get wifi/bt status: {exc}"
        )
    return status["wlan"], status["bluetooth"]


def _parse_wifi_bt_json(json_status, status, keys):
    retrieved = False
    for key in keys:
        if key not in json_status:
            continue
        for device in json_status[key]:
            if "type" not in device or device["type"] not in ["wlan", "bluetooth"]:
                continue
            if device["soft"] == "unblocked" and device["hard"] == "unblocked":
                status[device["type"]] = True
                retrieved = True
        if retrieved:
            return


class WifiManager:
    def __init__(self, config):
        self.config = config

    def onoff_wifi_bt(self, key=None):
        if shutil.which("rfkill") is None:
            return

        onoff_cmd = {
            "Wifi": {
                True: ["sudo", "rfkill", "block", "wifi"],
                False: ["sudo", "rfkill", "unblock", "wifi"],
            },
            "Bluetooth": {
                True: ["sudo", "rfkill", "block", "bluetooth"],
                False: ["sudo", "rfkill", "unblock", "bluetooth"],
            },
        }
        status = {}
        status["Wifi"], status["Bluetooth"] = get_wifi_bt_status()
        exec_cmd(onoff_cmd[key][status[key]])

    def set_wifi_enabled(self, enabled):
        if shutil.which("rfkill") is None:
            return

        cmd = ["sudo", "rfkill", "unblock" if enabled else "block", "wifi"]
        exec_cmd(cmd, cmd_print=False)

    def hardware_wifi_bt(self, status):
        app_logger.info(f"Hardware Wifi/BT: {status}")
        if os.path.exists(BOOT_FILE):
            with open(BOOT_FILE, "r") as file_handle:
                data = file_handle.read()
            for dev in ["wifi", "bt"]:
                disable = f"dtoverlay=disable-{dev}"
                if status:
                    if disable in data and f"#{disable}" not in data:
                        exec_cmd(
                            [
                                "sudo",
                                "sed",
                                "-i",
                                rf"s/^dtoverlay\=disable\-{dev}/\#dtoverlay\=disable\-{dev}/",
                                BOOT_FILE,
                            ],
                            False,
                        )
                else:
                    if f"#{disable}" in data:
                        exec_cmd(
                            [
                                "sudo",
                                "sed",
                                "-i",
                                rf"s/^\#dtoverlay\=disable\-{dev}/dtoverlay\=disable\-{dev}/",
                                BOOT_FILE,
                            ],
                            False,
                        )
                    elif disable in data:
                        pass
                    else:
                        exec_cmd(["sudo", "sed", "-i", f"$a{disable}", BOOT_FILE], False)
            if status:
                exec_cmd(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-e",
                        r's/^\#DEVICES\="/dev/ttyS0"/DEVICES\="/dev/ttyS0"/',
                        "/etc/default/gpsd",
                    ],
                    False,
                )
                exec_cmd(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-e",
                        r's/^DEVICES\="/dev/ttyAMA0"/\#DEVICES\="/dev/ttyAMA0"/',
                        "/etc/default/gpsd",
                    ],
                    False,
                )
            else:
                exec_cmd(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-e",
                        r's/^DEVICES\="/dev/ttyS0"/\#DEVICES\="/dev/ttyS0"/',
                        "/etc/default/gpsd",
                    ],
                    False,
                )
                exec_cmd(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-e",
                        r's/^\#DEVICES\="/dev/ttyAMA0"/DEVICES\="/dev/ttyAMA0"/',
                        "/etc/default/gpsd",
                    ],
                    False,
                )

    async def wifi_connect_with_wps(self):
        if shutil.which("wpa_cli") is None:
            return False

        app_logger.info("Wifi connect with WPS")
        exec_cmd_return_value(["sudo", "wpa_cli", "wps_pbc"], cmd_print=True)

        self.config.gui.change_dialog(
            title="Wait for connection.",
            button_label="OK",
        )
        await asyncio.sleep(15)

        stdout, _ = exec_cmd_return_value(["sudo", "wpa_cli", "status"], cmd_print=True)

        if "wpa_state=COMPLETED" in stdout:
            return True
        return False


__all__ = ["WifiManager", "BOOT_FILE", "get_wifi_bt_status"]
