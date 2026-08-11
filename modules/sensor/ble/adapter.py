from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

NRF52840_BRIDGE_USB_ID = ("2fe3", "000c")


class BleAdapterPolicy(str, Enum):
    AUTO = "AUTO"
    BUILTIN = "BUILTIN"
    NRF52840_BRIDGE = "NRF52840_BRIDGE"


class BleAdapterResolutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BluezAdapter:
    name: str
    device_path: Path
    address: str | None = None
    usb_vendor_id: str | None = None
    usb_product_id: str | None = None
    usb_serial: str | None = None

    @property
    def usb_id(self) -> tuple[str, str] | None:
        if self.usb_vendor_id is None or self.usb_product_id is None:
            return None
        return (self.usb_vendor_id.lower(), self.usb_product_id.lower())

    @property
    def is_nrf52840_bridge(self) -> bool:
        return self.usb_id == NRF52840_BRIDGE_USB_ID


def _read_optional(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _find_usb_identity(
    device_path: Path,
) -> tuple[str | None, str | None, str | None]:
    for parent in (device_path, *device_path.parents):
        vendor_id = _read_optional(parent / "idVendor")
        product_id = _read_optional(parent / "idProduct")
        if vendor_id is None or product_id is None:
            continue
        return (
            vendor_id.lower(),
            product_id.lower(),
            _read_optional(parent / "serial"),
        )
    return (None, None, None)


def discover_bluez_adapters(
    sysfs_root: Path | str = "/sys/class/bluetooth",
) -> list[BluezAdapter]:
    """Discover BlueZ controllers without depending on their hci index."""

    root = Path(sysfs_root)
    try:
        adapter_paths = sorted(
            (
                path
                for path in root.iterdir()
                if path.name.startswith("hci") and path.name[3:].isdigit()
            ),
            key=lambda path: path.name,
        )
    except OSError:
        return []

    adapters = []
    for adapter_path in adapter_paths:
        device_link = adapter_path / "device"
        try:
            device_path = device_link.resolve(strict=True)
        except OSError:
            continue
        vendor_id, product_id, serial = _find_usb_identity(device_path)
        address = _read_optional(adapter_path / "address")
        adapters.append(
            BluezAdapter(
                name=adapter_path.name,
                device_path=device_path,
                address=address.upper() if address is not None else None,
                usb_vendor_id=vendor_id,
                usb_product_id=product_id,
                usb_serial=serial,
            )
        )
    return adapters


class BleAdapterResolver:
    def __init__(self, adapters: Iterable[BluezAdapter] | None = None):
        self._adapters = None if adapters is None else tuple(adapters)

    def adapters(self) -> tuple[BluezAdapter, ...]:
        if self._adapters is not None:
            return self._adapters
        if not sys.platform.startswith("linux"):
            return ()
        return tuple(discover_bluez_adapters())

    def resolve(
        self,
        policy: BleAdapterPolicy | str,
        *,
        preferred_address: str | None = None,
        preferred_usb_serial: str | None = None,
    ) -> str:
        try:
            resolved_policy = BleAdapterPolicy(policy)
        except ValueError as exc:
            raise BleAdapterResolutionError(
                f"Unknown adapter policy: {policy}"
            ) from exc

        adapters = list(self.adapters())
        if preferred_address:
            normalized_address = preferred_address.upper()
            adapters = [
                adapter for adapter in adapters if adapter.address == normalized_address
            ]

        if resolved_policy == BleAdapterPolicy.BUILTIN:
            adapters = [
                adapter for adapter in adapters if not adapter.is_nrf52840_bridge
            ]
        elif resolved_policy == BleAdapterPolicy.NRF52840_BRIDGE:
            adapters = [adapter for adapter in adapters if adapter.is_nrf52840_bridge]
            if preferred_usb_serial:
                adapters = [
                    adapter
                    for adapter in adapters
                    if adapter.usb_serial == preferred_usb_serial
                ]

        if len(adapters) == 1:
            return adapters[0].name
        if not adapters:
            raise BleAdapterResolutionError(
                f"No BlueZ adapter matches policy {resolved_policy.value}"
            )
        names = ", ".join(adapter.name for adapter in adapters)
        raise BleAdapterResolutionError(
            f"Multiple BlueZ adapters match policy {resolved_policy.value}: {names}"
        )
