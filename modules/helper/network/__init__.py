from ..bluetooth.bluetooth_manager import BluetoothManager, BtOpenResult
from .download_manager import DownloadManager
from .http_client import get_json, post
from .wifi_manager import WifiManager
from modules.utils.network import detect_network


class Network:
    BT_OPEN_BLOCK_DURATION_SEC = 180

    def __init__(self, config):
        self.config = config
        self.bt_open_block_duration_sec = self.BT_OPEN_BLOCK_DURATION_SEC
        self.bluetooth = BluetoothManager(config, self.bt_open_block_duration_sec)
        self._downloads = DownloadManager(
            config,
            self.bluetooth,
            self.bt_open_block_duration_sec,
        )
        self.wifi = WifiManager(config)

    def set_bt_open_block_duration(self, seconds):
        self.bt_open_block_duration_sec = seconds
        self.bluetooth.bt_open_block_duration_sec = seconds
        self._downloads.update_queue_block_duration(seconds)

    async def download_queue_put(self, queue_item):
        """Enqueue download work via DownloadManager, dropping when blocked."""
        return await self._downloads.put(queue_item)

    async def quit(self):
        await self._downloads.shutdown()
        await self.bluetooth.shutdown()

    def reset_bluetooth(self):
        self.bluetooth.reset_bluetooth()

    async def start_bt_pairing(self):
        await self.bluetooth.start_bt_pairing()

    async def stop_bt_pairing(self):
        await self.bluetooth.stop_bt_pairing()

    async def pair_bt_device(self, mac):
        return await self.bluetooth.pair_bt_device(mac)

    def get_bt_pairing_list(self):
        return self.bluetooth.get_bt_pairing_list()

    def get_paired_bt_devices(self):
        return self.bluetooth.get_paired_bt_devices()

    async def remove_bt_device(self, bt_address):
        await self.bluetooth.remove_bt_device(bt_address)

    def get_file_download_status(self, filename):
        return self._downloads.get_file_download_status(filename)

    async def download_maptiles(self, *args, **kwargs):
        return await self._downloads.download_maptiles(*args, **kwargs)

    def check_network_with_bt_tethering(self):
        if not self.config.G_AUTO_BT_TETHERING:
            return detect_network(cache=False)

        has_required_device = (
            self.config.G_BT_PAN_DEVICE
            and self.config.bt_pan.get_bt_pan_devices()
        )
        return has_required_device

    async def bluetooth_tethering(self, disconnect=False):
        return await self.bluetooth.bluetooth_tethering(disconnect=disconnect)

    async def open_bt_tethering(self, caller_name):
        return await self.bluetooth.open_bt_tethering(caller_name)

    async def close_bt_tethering(self, caller_name):
        return await self.bluetooth.close_bt_tethering(caller_name)

    def onoff_wifi_bt(self, key=None):
        return self.wifi.onoff_wifi_bt(key)

    def set_wifi_enabled(self, enabled):
        return self.wifi.set_wifi_enabled(enabled)

    def hardware_wifi_bt(self, status):
        return self.wifi.hardware_wifi_bt(status)

    async def wifi_connect_with_wps(self):
        return await self.wifi.wifi_connect_with_wps()


__all__ = ["Network", "BtOpenResult", "get_json", "post"]
