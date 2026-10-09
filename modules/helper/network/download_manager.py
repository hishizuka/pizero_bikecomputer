import asyncio
import os

from modules.app_logger import app_logger
from modules.utils.map import get_maptile_filename

from ..bluetooth.bluetooth_manager import BtOpenResult
from .http_client import download_files


class DownloadManager:

    def __init__(self, config, bluetooth_manager, queue_block_duration_sec):
        self.config = config
        self.bluetooth = bluetooth_manager
        self.file_download_status = {}
        self._pending_files = {}
        self._download_queue = asyncio.Queue()
        self._download_queue_block_until = 0.0
        self._queue_block_duration_sec = queue_block_duration_sec
        self._dns_retry_base_delay_sec = 15
        self._dns_retry_max_delay_sec = 120
        self._dns_retry_max_attempts = 3
        self._worker_task = asyncio.create_task(self._download_worker())

    async def shutdown(self):
        await self._download_queue.put(None)
        await self._worker_task

    def get_file_download_status(self, filename):
        return self.file_download_status.get(filename)

    async def wait_for_files(self, filenames, timeout=120):
        """Wait for shared downloads without canceling another consumer's work."""
        pending = [
            self._pending_files[name]
            for name in filenames if name in self._pending_files
        ]
        if pending:
            await asyncio.wait_for(
                asyncio.gather(*(asyncio.shield(item) for item in pending)), timeout
            )

    def _finish_files(self, filenames):
        for name in filenames:
            future = self._pending_files.pop(name, None)
            if future is not None and not future.done():
                future.set_result(None)

    async def download_maptiles(self, map_config, map_name, z, tiles, additional_download=False):
        if self._is_download_queue_blocked():
            return False

        map_settings = map_config[map_name]
        request_header = {}
        additional_var = {}
        download_options = {}

        if "strava_heatmap" in map_name:
            additional_var["key_pair_id"] = self.config.G_STRAVA_COOKIE["KEY_PAIR_ID"]
            additional_var["policy"] = self.config.G_STRAVA_COOKIE["POLICY"]
            additional_var["signature"] = self.config.G_STRAVA_COOKIE["SIGNATURE"]
            idcf = self.config.G_STRAVA_COOKIE["IDCF"]
            if idcf:
                request_header["Cookie"] = f"_strava_idcf={idcf}"
            download_options["log_suppressed_statuses"] = (404,)
            download_options["log_url"] = False
        elif "basetime" in map_settings and "validtime" in map_settings:
            if map_settings["basetime"] is None or map_settings["validtime"] is None:
                return False
            additional_var["basetime"] = map_settings["basetime"]
            additional_var["validtime"] = map_settings["validtime"]
            if map_name == "rainviewer":
                additional_var["host"] = map_settings["host"]
                additional_var["path"] = map_settings["path"]
            elif map_name.startswith("jpn_scw"):
                if map_settings["subdomain"] is None:
                    return False
                additional_var["subdomain"] = map_settings["subdomain"]

        if map_settings.get("referer"):
            request_header["Referer"] = map_settings["referer"]
        if map_settings.get("user_agent"):
            request_header["User-Agent"] = self.config.G_PRODUCT

        basetime = additional_var.get("basetime")
        validtime = additional_var.get("validtime")
        created_tile_dirs = set()

        def tile_request(zoom, x, y):
            if (zoom, x) not in created_tile_dirs:
                self.make_maptile_dir(map_name, zoom, x, basetime, validtime)
                created_tile_dirs.add((zoom, x))
            return (
                map_settings["url"].format(z=zoom, x=x, y=y, **additional_var),
                get_maptile_filename(map_name, zoom, x, y, map_settings),
            )

        async def enqueue(requests):
            return await self._maybe_enqueue_download_item(
                {
                    "urls": [url for url, _ in requests],
                    "headers": request_header,
                    "save_paths": [path for _, path in requests],
                    **download_options,
                }
            )

        if not await enqueue([tile_request(z, *tile) for tile in tiles]):
            return False

        if not additional_download or map_name == "rainviewer":
            return True

        additional_requests = []
        z_plus_1 = z + 1
        z_minus_1 = z - 1
        native_zoom_levels = map_settings.get("native_zoom_levels")

        max_zoom_cond = (
            "max_zoomlevel" not in map_settings
            or z_plus_1 < map_settings["max_zoomlevel"]
        ) and (native_zoom_levels is None or z_plus_1 in native_zoom_levels)
        min_zoom_cond = (
            "min_zoomlevel" not in map_settings
            or z_minus_1 > map_settings["min_zoomlevel"]
        ) and (native_zoom_levels is None or z_minus_1 in native_zoom_levels)

        for tile in tiles:
            if max_zoom_cond:
                additional_requests.extend(
                    tile_request(z_plus_1, 2 * tile[0] + i, 2 * tile[1] + j)
                    for i in range(2)
                    for j in range(2)
                )

            if z_minus_1 > 0 and min_zoom_cond:
                request = tile_request(z_minus_1, int(tile[0] / 2), int(tile[1] / 2))
                if not any(url == request[0] for url, _ in additional_requests):
                    additional_requests.append(request)

        if additional_requests:
            await enqueue(additional_requests)

        return True

    @staticmethod
    def make_maptile_dir(map_name, z, y, basetime, validtime):
        if basetime is not None and validtime is not None:
            map_dir = f"maptile/{map_name}/{basetime}/{validtime}/{z}/{y}/"
        else:
            map_dir = f"maptile/{map_name}/{z}/{y}/"
        os.makedirs(map_dir, exist_ok=True)

    async def _download_worker_handle_task(self, queue_item, caller_name):
        bt_open_result = await self.bluetooth.open_bt_tethering(caller_name, wait_lock=True)

        if bt_open_result is not BtOpenResult.SUCCESS:
            await self._cleanup_failed_downloads(queue_item["save_paths"], caller_name)
            return None

        limit = await asyncio.to_thread(self.bluetooth.get_bt_limit)
        results = await download_files(**queue_item, limit=limit)
        for status, save_path in zip(results, queue_item["save_paths"]):
            self.file_download_status[save_path] = status
        return results

    async def _download_worker(self):
        caller_name = self._download_worker.__name__

        try:
            while True:
                if self._download_queue.qsize() == 0:
                    await self.bluetooth.close_bt_tethering(caller_name)
                queue_item = await self._download_queue.get()
                if queue_item is None:
                    self._download_queue.task_done()
                    break

                retry_count = queue_item.get("retry_count", 0)
                original_paths = tuple(queue_item["save_paths"])

                # download files with retry
                while True:
                    try:
                        results = await self._download_worker_handle_task(
                            queue_item, caller_name
                        )
                    except asyncio.CancelledError:
                        self._finish_files(original_paths)
                        self._download_queue.task_done()
                        return

                    if results is None:
                        break

                    retry_pairs = [
                        (url, path)
                        for url, path, status in zip(
                            queue_item["urls"], queue_item["save_paths"], results
                        )
                        if status == -1  # DNS error
                    ]
                    if not retry_pairs:
                        break
                    retry_urls, retry_save_paths = map(list, zip(*retry_pairs))

                    if retry_count >= self._dns_retry_max_attempts:
                        await self._cleanup_failed_downloads(
                            retry_save_paths, caller_name
                        )
                        break

                    await self.bluetooth.close_bt_tethering(caller_name)
                    delay = self._calculate_retry_delay(retry_count)
                    self._start_download_queue_block(duration=delay)
                    self.bluetooth.start_bt_open_block(duration=delay)
                    app_logger.info(
                        "Download DNS failure detected, retrying in %ss "
                        "(attempt %s/%s)",
                        delay,
                        retry_count + 1,
                        self._dns_retry_max_attempts,
                    )
                    await asyncio.sleep(delay)
                    queue_item["urls"] = retry_urls
                    queue_item["save_paths"] = retry_save_paths
                    queue_item["retry_count"] = retry_count + 1
                    retry_count += 1

                self._finish_files(original_paths)
                self._download_queue.task_done()
        finally:
            await self.bluetooth.close_bt_tethering(caller_name)

    async def put(self, queue_item):
        """Public queue-like interface used by other modules."""
        return await self._maybe_enqueue_download_item(queue_item)

    async def _maybe_enqueue_download_item(self, queue_item):
        if self._is_download_queue_blocked():
            return False
        pairs = list(dict.fromkeys(zip(queue_item["urls"], queue_item["save_paths"])))
        pairs = [(url, path) for url, path in pairs if path not in self._pending_files]
        if not pairs:
            return True
        queue_item = dict(queue_item)
        queue_item["urls"], queue_item["save_paths"] = map(list, zip(*pairs))
        for _, path in pairs:
            self._pending_files[path] = asyncio.get_running_loop().create_future()
        await self._download_queue.put(queue_item)
        return True

    def _start_download_queue_block(self, duration=None):
        loop = asyncio.get_running_loop()
        duration = duration or self._queue_block_duration_sec
        self._download_queue_block_until = max(
            self._download_queue_block_until,
            loop.time() + duration,
        )

    def _is_download_queue_blocked(self):
        loop = asyncio.get_running_loop()
        return loop.time() < self._download_queue_block_until

    def _calculate_retry_delay(self, retry_count):
        delay = self._dns_retry_base_delay_sec * (2 ** retry_count)
        return min(delay, self._dns_retry_max_delay_sec)

    def update_queue_block_duration(self, seconds):
        self._queue_block_duration_sec = seconds

    async def _cleanup_failed_downloads(self, initial_paths, caller_name):
        drained_save_paths = await self._drain_queue_and_collect_save_paths()
        combined = list(dict.fromkeys(list(initial_paths) + drained_save_paths))
        if combined:
            self.config.api.maptile_with_values.delete_existing_tiles(combined)
            for save_path in combined:
                self.file_download_status[save_path] = -1
            self._finish_files(combined)
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
                drained_save_paths.extend(pending_item["save_paths"])
            self._download_queue.task_done()

        if shutdown_requested:
            await self._download_queue.put(None)

        return drained_save_paths

__all__ = ["DownloadManager"]
