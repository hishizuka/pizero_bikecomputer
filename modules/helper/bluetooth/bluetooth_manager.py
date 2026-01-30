import asyncio
import ipaddress
import re
import shutil
import time
from enum import Enum

from modules.app_logger import app_logger
from modules.utils.cmd import exec_cmd, exec_cmd_return_value
from modules.utils.network import detect_network_async


BT_TETHERING_TIMEOUT_SEC = 15
_IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

class BtOpenResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    LOCKED = "locked"
    BNEP_FAILED = "bnep_not_created"
    BLOCKED = "network_unreachable"

    def is_success(self):
        return self is BtOpenResult.SUCCESS


def check_network_interface(iface=None):
    stdout, _ = exec_cmd_return_value(["ip", "-br", "-4", "a", "show", iface], cmd_print=False)
    if not stdout:
        return False

    # Accept any valid IPv4 address on the interface.
    for addr in _IPV4_PATTERN.findall(stdout):
        try:
            ipaddress.IPv4Address(addr)
            return True
        except ipaddress.AddressValueError:
            continue
    return False


def check_bnep0():
    return check_network_interface(iface="bnep0")


def check_wlan0():
    return check_network_interface(iface="wlan0")


class BluetoothManager:
    bt_error_limit = 15

    def __init__(self, config, bt_open_block_duration_sec):
        self.config = config
        self.bt_open_block_duration_sec = bt_open_block_duration_sec
        self.bt_tethering_status = {}
        self._bt_tethering_lock = asyncio.Lock()
        self._bt_open_block_until = 0

        self.bt_pairing_proc = None
        self.bt_paired_devices = {}

    @property
    def bt_pan(self):
        return self.config.bt_pan

    async def start_bt_pairing(self):
        if self.bt_pairing_proc is not None:
            return
        if shutil.which("bluetoothctl") is None:
            return

        self.get_paired_bt_devices()
        await self.open_btctl_proc()
        await self.btctl_write("scan on")

    async def open_btctl_proc(self):
        if self.bt_pairing_proc is not None:
            return
        self.bt_pairing_proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self.btctl_write("agent DisplayOnly")
        await self.btctl_write("default-agent")
        await self.btctl_write("discoverable on")

    async def stop_bt_pairing(self):
        await self.close_btctl_proc()

    async def btctl_write(self, cmd):
        if self.bt_pairing_proc is None:
            return
        self.bt_pairing_proc.stdin.write(cmd.encode() + b"\n")
        await self.bt_pairing_proc.stdin.drain()

    async def close_btctl_proc(self):
        if self.bt_pairing_proc:
            self.bt_pairing_proc.terminate()
            await self.bt_pairing_proc.wait()
            self.bt_pairing_proc = None

    async def pair_bt_device(self, mac):
        if self.bt_pairing_proc is None:
            return False

        await self.btctl_write("scan off")
        await self.btctl_write(f"pair {mac}")

        input_yes = False
        result = False
        start_time = time.time()
        while True:
            line = await self.bt_pairing_proc.stdout.readline()
            text = line.decode().strip()
            if "yes/no" in text and not input_yes:
                await self.btctl_write("yes")
                input_yes = True
            if "Paired: yes" in text:
                await self.btctl_write(f"trust {mac}")
                result = True
                if self.bt_pan is not None:
                    await self.bt_pan.update_bt_pan_devices()
                break
            if "Failed to pair" in text:
                break
            if time.time() - start_time > 30:
                break
        return result

    def get_bt_pairing_list(self):
        if shutil.which("bluetoothctl") is None:
            return {}

        skip_suffixes = (": yes",)
        result = {}
        paired_macs = set(self.bt_paired_devices.values())

        stdout, _ = exec_cmd_return_value(["bluetoothctl", "devices"], cmd_print=False)
        for line in stdout.splitlines():
            if line.endswith(skip_suffixes):
                continue
            parts = line.strip().split(" ", 2)
            if parts[0] != "Device":
                continue
            if len(parts) == 3:
                _, mac, name = parts
                if mac not in paired_macs:
                    result[name] = mac
        return result

    def get_paired_bt_devices(self):
        if shutil.which("bluetoothctl") is None:
            return {}

        skip_suffixes = (": yes",)
        self.bt_paired_devices = {}
        stdout, _ = exec_cmd_return_value([
            "bluetoothctl",
            "devices",
            "Paired",
        ], cmd_print=False)

        for line in stdout.splitlines():
            if line.endswith(skip_suffixes):
                continue
            parts = line.strip().split(" ", 2)
            if parts[0] != "Device":
                continue
            if len(parts) == 3:
                _, mac, name = parts
                self.bt_paired_devices[name] = mac
        return self.bt_paired_devices

    async def remove_bt_device(self, bt_address):
        if shutil.which("bluetoothctl") is not None:
            exec_cmd(["bluetoothctl", "remove", bt_address])
            if self.bt_pan is not None:
                await self.bt_pan.update_bt_pan_devices()

    def reset_bluetooth(self):
        if self.config.G_IS_RASPI:
            exec_cmd(["sudo", "systemctl", "restart", "bluetooth"])
            self.bt_tethering_status = {}

    def get_bt_limit(self):
        if self.config.G_IS_RASPI and check_bnep0() and not check_wlan0():
            return True
        return False

    async def bluetooth_tethering(self, disconnect=False):
        if (
            not self.config.G_IS_RASPI
            or not self.config.G_BT_PAN_DEVICE
            or not self.bt_pan
        ):
            return False

        bt_address = self.bt_pan.get_bt_pan_device_mac_address(self.config.G_BT_PAN_DEVICE)
        if shutil.which("nmcli") is not None:
            action = "connect"
            if disconnect:
                action = "disconnect"
            _, stderr = exec_cmd_return_value(
                ["sudo", "nmcli", "d", action, bt_address],
                cmd_print=False,
                timeout=10,
            )
        else:
            if not disconnect:
                stderr = await self.bt_pan.connect_tethering(bt_address)
            else:
                stderr = await self.bt_pan.disconnect_tethering(bt_address)

        return stderr

    def _start_bt_open_block(self, duration=None):
        duration = duration or self.bt_open_block_duration_sec
        self._bt_open_block_until = max(self._bt_open_block_until, time.time() + duration)

    def start_bt_open_block(self, duration=None):
        self._start_bt_open_block(duration)

    def _is_bt_open_block_active(self):
        return time.time() < self._bt_open_block_until

    async def open_bt_tethering(self, caller_name, wait_lock=False) -> BtOpenResult:
        if not self.config.G_IS_RASPI:
            return BtOpenResult.SUCCESS
        if not self.config.G_AUTO_BT_TETHERING:
            return BtOpenResult.SUCCESS
        else:
            if not self.config.G_BT_PAN_DEVICE or not self.bt_pan.get_bt_pan_devices():
                return BtOpenResult.FAILED

        # Locked
        if not wait_lock and self._bt_tethering_lock.locked():
            app_logger.info(
                f"[BT] open_bt_tethering locked, {caller_name=} {self.bt_tethering_status}"
            )
            return BtOpenResult.LOCKED

        await self._bt_tethering_lock.acquire()
        try:
            return await self._open_bt_tethering_impl(caller_name)
        finally:
            self._bt_tethering_lock.release()

    async def _open_bt_tethering_impl(self, caller_name) -> BtOpenResult:
        if await detect_network_async(cache=False):
            # Todo: disable when using wifi
            #app_logger.info(
            #    f"[BT] skip bt open(detected network), {caller_name=} {self.bt_tethering_status}"
            #)
            self.bt_tethering_status[caller_name] = True
            return BtOpenResult.SUCCESS

        # Blocked (DNS error, etc.)
        if self._is_bt_open_block_active():
            remaining = max(0, int(self._bt_open_block_until - time.time()))
            #app_logger.info(
            #    f"[BT] skip bt open(block active {remaining}s), {caller_name=} {self.bt_tethering_status}"
            #)
            return BtOpenResult.BLOCKED

        if any(self.bt_tethering_status.values()):
            #app_logger.info(
            #    f"[BT] skip bt open(other func), {caller_name=} {self.bt_tethering_status}"
            #)
            self.bt_tethering_status[caller_name] = True
            return BtOpenResult.SUCCESS

        bt_pan_error = await self.bluetooth_tethering()
        if bt_pan_error:
            app_logger.error(f"[BT] connect error: {bt_pan_error}, {caller_name=}")

        # bt_pan_error:
        #   "timed out", "input/output"
        #   Error: Connection activation failed: The Bluetooth connection failed or timed out
        #   Error: Connection activation failed: The device could not be readied for configuration.
        #   Error: Connection activation failed: Carrier/link changed.
        #   TimeoutExpired(['sudo', 'nmcli', 'd', 'connect', ~

        wait_time = 2
        elapsed = 0
        while elapsed < BT_TETHERING_TIMEOUT_SEC:
            await asyncio.sleep(wait_time)
            if check_bnep0():
                break
            elapsed += wait_time
        if not check_bnep0():
            self._start_bt_open_block()
            msg = "[BT] can't create bnep0"
            self.config.gui.show_popup(msg, 10)
            #self.config.gui.show_dialog_ok_only(fn=None, title=msg)
            #self.gui.show_dialog_ok_only(fn=None, title=msg)
            app_logger.error(f"{msg}, {caller_name=}")

            #self.config.network.onoff_wifi_bt("Wifi")
            #self.config.gui.show_popup(f"reset bluetooth", 10)
            #self.reset_bluetooth()

            return BtOpenResult.BNEP_FAILED

        elapsed = 0
        while elapsed < BT_TETHERING_TIMEOUT_SEC:
            if await detect_network_async(cache=False):
                break
            await asyncio.sleep(wait_time)
            elapsed += wait_time

        if elapsed >= BT_TETHERING_TIMEOUT_SEC and not await detect_network_async(cache=False):
            await self.bluetooth_tethering(disconnect=True)
            app_logger.error(
                f"[BT] created bnep0, but detect_network failed({elapsed}s), {caller_name=}"
            )
            self._start_bt_open_block()
            return BtOpenResult.BLOCKED

        self.bt_tethering_status[caller_name] = True
        app_logger.info(f"[BT] connected, {caller_name=}")
        return BtOpenResult.SUCCESS

    async def close_bt_tethering(self, caller_name):
        if not self.config.G_IS_RASPI:
            return True
        elif not self.config.G_AUTO_BT_TETHERING:
            return True
        else:
            if not self.config.G_BT_PAN_DEVICE or not self.bt_pan.get_bt_pan_devices():
                return True
        
        async with self._bt_tethering_lock:
            return await self._close_bt_tethering_impl(caller_name)

    async def _close_bt_tethering_impl(self, caller_name):

        self.bt_tethering_status[caller_name] = False

        if any(self.bt_tethering_status.values()):
            #app_logger.info(
            #    f"[BT] skip bt close(other func), {caller_name=} {self.bt_tethering_status}"
            #)
            return True

        if not check_bnep0():
            # Todo: disable when using wifi
            #app_logger.info(
            #    f"[BT] skip bt close(bnep0 don't exists), {caller_name=} {self.bt_tethering_status}"
            #)
            return True

        bt_pan_error = await self.bluetooth_tethering(disconnect=True)
        if bt_pan_error:
            app_logger.error(
                f"[BT] disconnect error: {bt_pan_error}, caller_name: {caller_name}"
            )

        await asyncio.sleep(3)
        status = check_bnep0()
        app_logger.info(f"[BT] disconnect, {caller_name=}")
        return not status

    async def shutdown(self):
        if self.config.G_IS_RASPI and check_bnep0():
            await self.bluetooth_tethering(disconnect=True)
            await asyncio.sleep(5)


__all__ = [
    "BluetoothManager",
    "BtOpenResult",
    "check_bnep0",
    "check_wlan0",
]
