"""BLE discovery and GATT clients independent of the sensor profiles."""

import asyncio
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from modules.app_logger import app_logger

GATT_CONNECT_TIMEOUT = 60.0


def format_ble_error(exc: Exception) -> str:
    """Keep the exception type when its message is empty."""
    return " ".join(repr(exc).splitlines())


@dataclass(frozen=True, slots=True)
class BleSensorCandidate:
    identifier: str
    name: str | None
    rssi: int | None
    profiles: tuple[str, ...] = ()


class BleTransportProtocol(Protocol):
    remote: bool
    supports_control: bool

    async def discover(self, **kwargs): ...

    async def find_device(self, identifier, *, timeout=10.0, adapter=None): ...

    def client(self, device, **kwargs): ...

    def connection_setup(self, adapter, device): ...


class BleakTransport:
    remote = False
    supports_control = True

    async def discover(self, **kwargs):
        from .discovery import discover_ble_devices

        return await discover_ble_devices(**kwargs)

    def client(
        self,
        device,
        *,
        adapter=None,
        timeout=GATT_CONNECT_TIMEOUT,
        disconnected_callback=None,
    ):
        from bleak import BleakClient

        kwargs = {"timeout": timeout}
        if adapter is not None and sys.platform.startswith("linux"):
            kwargs["bluez"] = {"adapter": adapter}
        if disconnected_callback is not None:
            kwargs["disconnected_callback"] = disconnected_callback
        return BleakClient(device, **kwargs)

    async def find_device(self, identifier, *, timeout=10.0, adapter=None):
        normalized_identifier = identifier.casefold()

        def matches_identifier(device, _advertisement):
            return device.address.casefold() == normalized_identifier

        devices = await self.discover(
            adapter=adapter,
            timeout=timeout,
            predicate=matches_identifier,
            stop_when=matches_identifier,
        )
        return devices[0][0] if devices else None

    @asynccontextmanager
    async def connection_setup(self, adapter, device):
        if adapter is not None and sys.platform.startswith("linux"):
            await self._load_initial_parameters(adapter, device)
        yield

    @staticmethod
    async def _load_initial_parameters(adapter, device):
        from .connection_parameters import load_initial_connection_parameters

        # The connection works without this, only with the stored slower parameters.
        try:
            loaded = await asyncio.to_thread(
                load_initial_connection_parameters,
                adapter,
                device.address,
                device.details["props"]["AddressType"],
            )
        except (AttributeError, OSError) as exc:
            app_logger.warning(f"[BLE-SENSOR] connection parameters not loaded: {exc}")
            return
        if not loaded:
            app_logger.debug(
                "[BLE-SENSOR] connection parameters need CAP_NET_ADMIN; "
                "using the values stored by BlueZ"
            )
