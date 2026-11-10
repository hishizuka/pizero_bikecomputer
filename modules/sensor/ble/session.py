"""Connection-session policy shared by BLE sensor profiles."""

import asyncio
from contextlib import AsyncExitStack, suppress
from typing import Callable

from .transport import BleTransportProtocol

GATT_SETUP_TIMEOUT = 20.0


class BleSetupDeadline:
    """Apply one deadline across all GATT operations needed to make a link ready."""

    def __init__(self, timeout: float = GATT_SETUP_TIMEOUT):
        self.deadline = asyncio.get_running_loop().time() + timeout

    async def wait(self, operation):
        async with asyncio.timeout_at(self.deadline):
            return await operation


class BleGattLink:
    """Own one GATT client from connection preparation through disconnect."""

    def __init__(
        self,
        transport: BleTransportProtocol,
        device,
        *,
        adapter: str | None,
        on_unexpected_disconnect: Callable[[], None] | None = None,
    ):
        self._on_unexpected_disconnect = on_unexpected_disconnect
        self.disconnected = asyncio.Event()
        self.client = transport.client(
            device,
            adapter=adapter,
            disconnected_callback=self._on_disconnected,
        )
        self._setup = AsyncExitStack()
        self._setup_context = transport.connection_setup(adapter, device)
        self._established = False
        self._expected_disconnect = False

    async def connect(self) -> None:
        await self._setup.enter_async_context(self._setup_context)
        await self.client.connect()
        self._established = True

    async def mark_ready(self) -> None:
        await self._setup.aclose()

    def expect_disconnect(self) -> None:
        self._expected_disconnect = True

    async def close(self) -> None:
        self.expect_disconnect()
        await self._setup.aclose()
        if self.client.is_connected:
            with suppress(Exception):
                await self.client.disconnect()

    def _on_disconnected(self, _client) -> None:
        # BlueZ may report failed retries while connect() is still in progress.
        if not self._established:
            return
        if not self._expected_disconnect and self._on_unexpected_disconnect is not None:
            self._on_unexpected_disconnect()
        self.disconnected.set()


async def wait_for_any_event(*events: asyncio.Event) -> None:
    """Wait for one event and cancel all temporary waiter tasks."""

    tasks = tuple(asyncio.create_task(event.wait()) for event in events)
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def wait_for_stop(stop_event: asyncio.Event, timeout: float) -> None:
    """Wait for a stop request without delaying shutdown for the full timeout."""

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
    except TimeoutError:
        pass
