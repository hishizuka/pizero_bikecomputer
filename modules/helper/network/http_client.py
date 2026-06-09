import asyncio
from datetime import datetime
from typing import Iterable

import aiohttp

from modules.app_logger import app_logger


DEFAULT_COROUTINE_SEM = 100


def _write_binary_file(save_path, data):
    with open(save_path, mode="wb") as file_handle:
        file_handle.write(data)


async def get_response(url, params=None, headers=None, timeout=30, response_type="json"):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=headers, timeout=timeout
            ) as res:
                if res.status != 200:
                    data = await res.read()
                    text = data.decode("utf-8", errors="replace")
                    app_logger.error(
                        f"get_response status {res.status}: {text[:200]}\n{url}"
                    )
                    return None
                if response_type == "json":
                    return await res.json()
                if response_type == "bytes":
                    return await res.read()
                raise ValueError(f"unknown response_type: {response_type}")
    except asyncio.CancelledError:
        return None
    except Exception as exc:
        app_logger.error(f"get_response error: {exc}\n{url}")
        return None


async def get_json(url, params=None, headers=None, timeout=30):
    return await get_response(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        response_type="json",
    )


async def get_bytes(url, params=None, headers=None, timeout=30):
    return await get_response(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        response_type="bytes",
    )


async def post(url, headers=None, params=None, data=None):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, params=params, data=data
            ) as res:
                data = await res.json()
                return data
    except asyncio.CancelledError:
        return None
    except Exception as exc:
        app_logger.error(f"post error: {exc}\n{url}")
        return None


async def _get_http_request(session, url, save_path, headers, params, semaphore, timeout):
    start_time = datetime.now().strftime("%H:%M:%S")
    async with semaphore:
        response_code = None
        try:
            async with session.get(
                url, headers=headers, params=params, timeout=timeout
            ) as dl_file:
                response_code = dl_file.status
                if dl_file.status != 200:
                    app_logger.info(
                        f"dl_file status {dl_file.status}: {dl_file.reason}\n{url}"
                    )
                    return response_code

                data = await dl_file.read()
                await asyncio.to_thread(_write_binary_file, save_path, data)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            app_logger.error(
                f"Download Error ({start_time}->{datetime.now().strftime('%H:%M:%S')}): {exc}\n{url}"
            )
            if "cannot connect" in str(exc).lower() or "dns server" in str(exc).lower():
                response_code = -1
        return response_code


async def download_files(
    urls: Iterable[str],
    save_paths: Iterable[str],
    headers=None,
    params=None,
    retry_count=None,
    limit=None,
    timeout=120,
):
    semaphore = asyncio.Semaphore(1 if limit else DEFAULT_COROUTINE_SEM)
    async with aiohttp.ClientSession() as session:
        tasks = [
            _get_http_request(
                session, url, save_path, headers, params, semaphore, timeout
            )
            for url, save_path in zip(urls, save_paths)
        ]
        return await asyncio.gather(*tasks)


__all__ = [
    "download_files",
    "get_bytes",
    "get_json",
    "get_response",
    "post",
    "DEFAULT_COROUTINE_SEM",
]
