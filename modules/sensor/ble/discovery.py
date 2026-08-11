from __future__ import annotations

import asyncio
import sys
import time
import weakref
from dataclasses import dataclass, field
from typing import Callable

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

BleAdvertisement = tuple[BLEDevice, AdvertisementData]
BleAdvertisementPredicate = Callable[[BLEDevice, AdvertisementData], bool]

_COORDINATORS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _scanner_kwargs(adapter: str | None) -> dict:
    if adapter is None or not sys.platform.startswith("linux"):
        return {}
    return {"bluez": {"adapter": adapter}}


@dataclass(eq=False, slots=True)
class _DiscoveryRequest:
    predicate: BleAdvertisementPredicate
    stop_when: BleAdvertisementPredicate | None
    results: dict[str, BleAdvertisement] = field(default_factory=dict)
    completed: asyncio.Event = field(default_factory=asyncio.Event)


class BleDiscoveryCoordinator:
    """Share one scanner between all BLE discovery consumers on an adapter."""

    IDLE_STOP_DELAY = 2.5
    RECENT_ADVERTISEMENT_MAX_AGE = 5.0

    def __init__(self, adapter: str | None):
        self.adapter = adapter
        self._scanner: BleakScanner | None = None
        self._requests: set[_DiscoveryRequest] = set()
        self._recent_advertisements: dict[
            str,
            tuple[float, BleAdvertisement],
        ] = {}
        self._lock = asyncio.Lock()
        self._idle_stop_task: asyncio.Task | None = None

    async def discover(
        self,
        *,
        timeout: float,
        predicate: BleAdvertisementPredicate,
        stop_when: BleAdvertisementPredicate | None = None,
    ) -> list[BleAdvertisement]:
        request = _DiscoveryRequest(predicate, stop_when)
        await self._subscribe(request)
        try:
            try:
                await asyncio.wait_for(request.completed.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            return list(request.results.values())
        finally:
            await self._unsubscribe(request)

    async def shutdown(self) -> None:
        idle_stop_task = self._idle_stop_task
        self._idle_stop_task = None
        if idle_stop_task is not None:
            idle_stop_task.cancel()
            await asyncio.gather(idle_stop_task, return_exceptions=True)
        async with self._lock:
            scanner = self._scanner
            self._scanner = None
            if scanner is not None:
                await scanner.stop()

    async def _subscribe(self, request: _DiscoveryRequest) -> None:
        async with self._lock:
            if self._idle_stop_task is not None:
                self._idle_stop_task.cancel()
                self._idle_stop_task = None
            self._requests.add(request)
            if self._scanner is not None:
                self._deliver_recent_advertisements(request)
                return
            self._recent_advertisements.clear()
            scanner = BleakScanner(
                detection_callback=self._on_advertisement,
                **_scanner_kwargs(self.adapter),
            )
            try:
                await scanner.start()
            except BaseException:
                self._requests.remove(request)
                raise
            self._scanner = scanner

    async def _unsubscribe(self, request: _DiscoveryRequest) -> None:
        async with self._lock:
            self._requests.remove(request)
            if self._requests or self._scanner is None:
                return
            self._idle_stop_task = asyncio.create_task(self._stop_when_idle())

    async def _stop_when_idle(self) -> None:
        current_task = asyncio.current_task()
        try:
            await asyncio.sleep(self.IDLE_STOP_DELAY)
            async with self._lock:
                if self._requests or self._scanner is None:
                    return
                scanner = self._scanner
                self._scanner = None
                await scanner.stop()
        except asyncio.CancelledError:
            return
        finally:
            if self._idle_stop_task is current_task:
                self._idle_stop_task = None

    def _on_advertisement(
        self,
        device: BLEDevice,
        advertisement: AdvertisementData,
    ) -> None:
        self._recent_advertisements[device.address] = (
            time.monotonic(),
            (device, advertisement),
        )
        for request in tuple(self._requests):
            self._deliver(request, device, advertisement)

    def _deliver_recent_advertisements(self, request: _DiscoveryRequest) -> None:
        cutoff = time.monotonic() - self.RECENT_ADVERTISEMENT_MAX_AGE
        for received_at, (device, advertisement) in tuple(
            self._recent_advertisements.values()
        ):
            if received_at >= cutoff:
                self._deliver(request, device, advertisement)

    @staticmethod
    def _deliver(
        request: _DiscoveryRequest,
        device: BLEDevice,
        advertisement: AdvertisementData,
    ) -> None:
        if not request.predicate(device, advertisement):
            return
        request.results[device.address] = (device, advertisement)
        if request.stop_when is not None and request.stop_when(device, advertisement):
            request.completed.set()


def get_ble_discovery_coordinator(adapter: str | None) -> BleDiscoveryCoordinator:
    loop = asyncio.get_running_loop()
    coordinators = _COORDINATORS.get(loop)
    if coordinators is None:
        coordinators = {}
        _COORDINATORS[loop] = coordinators
    key = adapter or "platform-default"
    coordinator = coordinators.get(key)
    if coordinator is None:
        coordinator = BleDiscoveryCoordinator(adapter)
        coordinators[key] = coordinator
    return coordinator


async def discover_ble_devices(
    *,
    adapter: str | None,
    timeout: float,
    predicate: BleAdvertisementPredicate,
    stop_when: BleAdvertisementPredicate | None = None,
) -> list[BleAdvertisement]:
    return await get_ble_discovery_coordinator(adapter).discover(
        timeout=timeout,
        predicate=predicate,
        stop_when=stop_when,
    )


async def shutdown_ble_discovery(adapter: str | None) -> None:
    await get_ble_discovery_coordinator(adapter).shutdown()
