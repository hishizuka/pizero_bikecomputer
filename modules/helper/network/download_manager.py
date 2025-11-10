import asyncio
import os

from modules.app_logger import app_logger
from modules.utils.map import get_maptile_filename
from modules.utils.network import detect_network

from ..bluetooth.bluetooth_manager import BtOpenResult
from .http_client import download_files


class DownloadManager:

    def __init__(self, config, bluetooth_manager, queue_block_duration_sec):
        self.config = config
        self.bluetooth = bluetooth_manager
        self.file_download_status = {}
        self._download_queue = asyncio.Queue()
        self._download_queue_block_until = 0.0
        self._queue_block_duration_sec = queue_block_duration_sec
        self._worker_task = asyncio.create_task(self._download_worker())

    async def shutdown(self):
        await self._download_queue.put(None)
        if self._worker_task:
            await self._worker_task

    def get_file_download_status(self, filename):
        return self.file_download_status.get(filename)

    async def download_maptiles(self, map_config, map_name, z, tiles, additional_download=False):
        # Skip queueing if there is no connectivity path available.
        if not self.config.network.check_network_with_bt_tethering():
            return False
        if self._is_download_queue_blocked():
            return False

        map_settings = map_config[map_name]
        urls = []
        save_paths = []
        request_header = {}
        additional_var = {}

        if (
            map_config == self.config.G_HEATMAP_OVERLAY_MAP_CONFIG
            and "strava_heatmap" in map_name
        ):
            additional_var["key_pair_id"] = self.config.G_STRAVA_COOKIE["KEY_PAIR_ID"]
            additional_var["policy"] = self.config.G_STRAVA_COOKIE["POLICY"]
            additional_var["signature"] = self.config.G_STRAVA_COOKIE["SIGNATURE"]
        elif "basetime" in map_settings and "validtime" in map_settings:
            if map_settings["basetime"] is None or map_settings["validtime"] is None:
                return False
            additional_var["basetime"] = map_settings["basetime"]
            additional_var["validtime"] = map_settings["validtime"]
            if map_name.startswith("jpn_scw"):
                if map_settings["subdomain"] is None:
                    return False
                additional_var["subdomain"] = map_settings["subdomain"]

        if map_settings.get("referer"):
            request_header["Referer"] = map_settings["referer"]
        if map_settings.get("user_agent"):
            request_header["User-Agent"] = self.config.G_PRODUCT

        basetime = additional_var.get("basetime")
        validtime = additional_var.get("validtime")

        for tile in tiles:
            self.make_maptile_dir(map_name, z, tile[0], basetime, validtime)
            url = map_settings["url"].format(z=z, x=tile[0], y=tile[1], **additional_var)
            save_path = get_maptile_filename(
                map_name, z, *tile, basetime=basetime, validtime=validtime
            )
            urls.append(url)
            save_paths.append(save_path)

        enqueued = await self._maybe_enqueue_download_item(
            {"urls": urls, "headers": request_header, "save_paths": save_paths}
        )
        if not enqueued:
            return False

        if not additional_download:
            return True

        additional_urls = []
        additional_save_paths = []
        z_plus_1 = z + 1
        z_minus_1 = z - 1

        max_zoom_cond = True
        if "max_zoomlevel" in map_settings and z_plus_1 >= map_settings["max_zoomlevel"]:
            max_zoom_cond = False

        min_zoom_cond = True
        if "min_zoomlevel" in map_settings and z_minus_1 <= map_settings["min_zoomlevel"]:
            min_zoom_cond = False

        for tile in tiles:
            if max_zoom_cond:
                for i in range(2):
                    x_val = 2 * tile[0] + i
                    self.make_maptile_dir(map_name, z_plus_1, x_val, basetime, validtime)
                    for j in range(2):
                        y_val = 2 * tile[1] + j
                        url = map_settings["url"].format(z=z_plus_1, x=x_val, y=y_val, **additional_var)
                        save_path = get_maptile_filename(
                            map_name, z_plus_1, x_val, y_val, basetime=basetime, validtime=validtime
                        )
                        additional_urls.append(url)
                        additional_save_paths.append(save_path)

            if z_minus_1 <= 0:
                continue

            if min_zoom_cond:
                x_val = int(tile[0] / 2)
                y_val = int(tile[1] / 2)
                self.make_maptile_dir(map_name, z_minus_1, x_val, basetime, validtime)
                url = map_settings["url"].format(z=z_minus_1, x=x_val, y=y_val, **additional_var)
                if url not in additional_urls:
                    save_path = get_maptile_filename(
                        map_name, z_minus_1, x_val, y_val, basetime=basetime, validtime=validtime
                    )
                    additional_urls.append(url)
                    additional_save_paths.append(save_path)

        if additional_urls:
            await self._maybe_enqueue_download_item(
                {
                    "urls": additional_urls,
                    "headers": request_header,
                    "save_paths": additional_save_paths,
                }
            )

        return True

    @staticmethod
    def make_maptile_dir(map_name, z, y, basetime, validtime):
        if basetime is not None and validtime is not None:
            map_dir = f"maptile/{map_name}/{basetime}/{validtime}/{z}/{y}/"
        else:
            map_dir = f"maptile/{map_name}/{z}/{y}/"
        os.makedirs(map_dir, exist_ok=True)

    async def _download_worker_handle_task(self, queue_item, caller_name):
        try:
            bt_open_result = await self.bluetooth.open_bt_tethering(caller_name, wait_lock=True)

            if bt_open_result is not BtOpenResult.SUCCESS:
                await self._cleanup_failed_downloads(queue_item["save_paths"], caller_name)
                return None

            results = await download_files(**queue_item, limit=self.bluetooth.get_bt_limit())
            for status, save_path in zip(results, queue_item["save_paths"]):
                self.file_download_status[save_path] = status
            return results
        finally:
            self._download_queue.task_done()

    async def _download_worker(self):
        caller_name = self._download_worker.__name__

        while True:
            if self._download_queue.qsize() == 0:
                await self.bluetooth.close_bt_tethering(caller_name)
            queue_item = await self._download_queue.get()
            if queue_item is None:
                break

            retry_count = queue_item.get("retry_count", 0)
            try:
                results = await self._download_worker_handle_task(queue_item, caller_name)
            except asyncio.CancelledError:
                return

            if results is None:
                continue

            #retry_urls = []
            #retry_save_paths = []
            forget_save_paths = []

            for url, save_path, status in zip(queue_item["urls"], queue_item["save_paths"], results):
                if status == -1:
                    forget_save_paths.append(save_path)

            if forget_save_paths:
                # Todo: block open_bt_tethering with retry
                await self._cleanup_failed_downloads(forget_save_paths, caller_name)
                continue

            #if retry_urls:
            #    await asyncio.sleep(120)
            #    queue_item["urls"] = retry_urls
            #    queue_item["save_paths"] = retry_save_paths
            #    queue_item["retry_count"] = retry_count + 1
            #    await self._download_queue.put(queue_item)

    async def put(self, queue_item):
        """Public queue-like interface used by other modules."""
        return await self._maybe_enqueue_download_item(queue_item)

    async def _maybe_enqueue_download_item(self, queue_item):
        if self._is_download_queue_blocked():
            return False
        await self._download_queue.put(queue_item)
        return True

    def _start_download_queue_block(self):
        loop = asyncio.get_running_loop()
        duration = self._queue_block_duration_sec
        self._download_queue_block_until = max(
            self._download_queue_block_until,
            loop.time() + duration,
        )

    def _is_download_queue_blocked(self):
        loop = asyncio.get_running_loop()
        return loop.time() < self._download_queue_block_until

    def update_queue_block_duration(self, seconds):
        self._queue_block_duration_sec = seconds

    async def _cleanup_failed_downloads(self, initial_paths, caller_name):
        drained_save_paths = await self._drain_queue_and_collect_save_paths()
        combined = list(dict.fromkeys(list(initial_paths) + drained_save_paths))
        if combined:
            self.config.api.maptile_with_values.delete_existing_tiles(combined)
            for save_path in combined:
                self.file_download_status[save_path] = -1
        await self.bluetooth.close_bt_tethering(caller_name)

    async def _drain_queue_and_collect_save_paths(self):
        """Remove remaining queued items and return their save paths."""
        self._start_download_queue_block()
        drained_save_paths = []
        shutdown_requested = False
        while True:
            try:
                pending_item = self._download_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if pending_item is None:
                shutdown_requested = True
            else:
                drained_save_paths.extend(pending_item.get("save_paths", []))
            self._download_queue.task_done()

        if shutdown_requested:
            await self._download_queue.put(None)

        return drained_save_paths

__all__ = ["DownloadManager"]
