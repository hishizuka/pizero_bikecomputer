import os
import datetime
import asyncio
import traceback
import concurrent

import aiohttp
import aiofiles

from logger import app_logger
from modules.helper.api import api
from modules.utils.network import detect_network


class Network:
    config = None

    def __init__(self, config):
        self.config = config
        self.api = api(self.config)

        self.download_queue = asyncio.Queue()
        asyncio.create_task(self.download_worker())

    async def quit(self):
        await self.download_queue.put(None)

    @staticmethod
    async def get_json(url, params=None, headers=None, timeout=10):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=headers, timeout=timeout
            ) as res:
                json = await res.json()
                return json

    @staticmethod
    async def post(url, headers=None, params=None, data=None):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, params=params, data=data
            ) as res:
                json = await res.json()
                return json

    async def download_worker(self):
        failed = []
        # for urls, header, save_paths, params:
        while True:
            q = await self.download_queue.get()
            if q is None:
                break
            try:
                res = await self.download_files(**q)
                self.download_queue.task_done()
            except concurrent.futures._base.CancelledError:
                return

            # all False -> give up
            if not any(res) or res is None:
                failed.append((datetime.datetime.now(), q))
                app_logger.error("failed download")
                app_logger.error(q["urls"])
            # retry
            elif (
                not all(res)
                and len(q["urls"])
                and len(res)
                and len(q["urls"]) == len(res)
            ):
                retry_urls = []
                retry_save_paths = []
                for url, save_path, status in zip(q["urls"], q["save_paths"], res):
                    if not status:
                        retry_urls.append(url)
                        retry_save_paths.append(save_path)
                if len(retry_urls):
                    q["urls"] = retry_urls
                    q["save_paths"] = retry_save_paths
                    await self.download_queue.put(q)

    async def download_maptile(
        self, map_config, map_name, z, tiles, additional_download=False
    ):
        if not detect_network() or map_config[map_name]["url"] is None:
            return False

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
        elif map_config in [
            self.config.G_RAIN_OVERLAY_MAP_CONFIG,
            self.config.G_WIND_OVERLAY_MAP_CONFIG,
        ]:
            if (
                map_config[map_name]["basetime"] is None
                or map_config[map_name]["validtime"] is None
            ):
                return False
            additional_var["basetime"] = map_config[map_name]["basetime"]
            additional_var["validtime"] = map_config[map_name]["validtime"]
            if (
                map_config == self.config.G_WIND_OVERLAY_MAP_CONFIG
                and "jpn_scw" in map_name
            ):
                if map_config[map_name]["subdomain"] is None:
                    return False
                additional_var["subdomain"] = map_config[map_name]["subdomain"]

        # make header
        if (
            "referer" in map_config[map_name]
            and map_config[map_name]["referer"] is not None
        ):
            request_header["Referer"] = map_config[map_name]["referer"]
        if (
            "user_agent" in map_config[map_name]
            and map_config[map_name]["user_agent"] is not None
        ):
            request_header["User-Agent"] = map_config[map_name]["user_agent"]

        for tile in tiles:
            os.makedirs(f"maptile/{map_name}/{z}/{tile[0]}/", exist_ok=True)
            url = map_config[map_name]["url"].format(
                z=z, x=tile[0], y=tile[1], **additional_var
            )
            save_path = self.config.get_maptile_filename(map_name, z, *tile)
            urls.append(url)
            save_paths.append(save_path)

        await self.download_queue.put(
            {"urls": urls, "headers": request_header, "save_paths": save_paths}
        )

        if additional_download:
            additional_urls = []
            additional_save_paths = []

            max_zoom_cond = True
            if (
                "max_zoomlevel" in map_config[map_name]
                and z + 1 >= map_config[map_name]["max_zoomlevel"]
            ):
                max_zoom_cond = False
            min_zoom_cond = True
            if (
                "min_zoomlevel" in map_config[map_name]
                and z - 1 <= map_config[map_name]["min_zoomlevel"]
            ):
                min_zoom_cond = False

            for tile in tiles:
                if max_zoom_cond:
                    for i in range(2):
                        os.makedirs(
                            f"maptile/{map_name}/{z + 1}/{2 * tile[0] + i}",
                            exist_ok=True,
                        )
                        for j in range(2):
                            url = map_config[map_name]["url"].format(
                                z=z + 1,
                                x=2 * tile[0] + i,
                                y=2 * tile[1] + j,
                                **additional_var,
                            )
                            save_path = self.config.get_maptile_filename(
                                map_name, z + 1, 2 * tile[0] + i, 2 * tile[1] + j
                            )
                            additional_urls.append(url)
                            additional_save_paths.append(save_path)

                if z - 1 <= 0:
                    continue

                if min_zoom_cond:
                    os.makedirs(
                        f"maptile/{map_name}/{z - 1}/{int(tile[0] / 2)}",
                        exist_ok=True,
                    )
                    zoomout_url = map_config[map_name]["url"].format(
                        z=z - 1,
                        x=int(tile[0] / 2),
                        y=int(tile[1] / 2),
                        **additional_var,
                    )
                    if zoomout_url not in additional_urls:
                        additional_urls.append(zoomout_url)
                        additional_save_paths.append(
                            self.config.get_maptile_filename(
                                map_name, z - 1, int(tile[0] / 2), int(tile[1] / 2)
                            )
                        )

            if additional_urls:
                await self.download_queue.put(
                    {
                        "urls": additional_urls,
                        "headers": request_header,
                        "save_paths": additional_save_paths,
                    }
                )

        return True

    @staticmethod
    async def get_http_request(session, url, save_path, headers, params):
        try:
            async with session.get(url, headers=headers, params=params) as dl_file:
                if dl_file.status == 200:
                    async with aiofiles.open(save_path, mode="wb") as f:
                        await f.write(await dl_file.read())
                    return True
                else:
                    return False
        except asyncio.CancelledError:
            return False
        except:
            return False

    async def download_files(self, urls, save_paths, headers=None, params=None):
        tasks = []
        async with asyncio.Semaphore(self.config.G_COROUTINE_SEM):
            async with aiohttp.ClientSession() as session:
                for url, save_path in zip(urls, save_paths):
                    tasks.append(
                        self.get_http_request(session, url, save_path, headers, params)
                    )
                res = await asyncio.gather(*tasks)
        return res

    async def download_demtile(self, z, x, y):
        if not detect_network():
            return False
        header = {}
        try:
            os.makedirs(
                f"maptile/{self.config.G_DEM_MAP}/{z}/{x}/",
                exist_ok=True,
            )
            await self.download_queue.put(
                {
                    "urls": [
                        self.config.G_DEM_MAP_CONFIG[self.config.G_DEM_MAP][
                            "url"
                        ].format(z=z, x=x, y=y),
                    ],
                    "headers": header,
                    "save_paths": [
                        self.config.get_maptile_filename(
                            self.config.G_DEM_MAP, z, x, y
                        ),
                    ],
                }
            )
            return True
        except:
            traceback.print_exc()
            return False
