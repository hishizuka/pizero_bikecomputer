"""Bluetooth-related helper modules."""

from .bluetooth_manager import BluetoothManager, BtOpenResult
from .bt_pan import (
    BTPan,
    BTPanDbus,
    BTPanDbusFast,
    HAS_DBUS,
    HAS_DBUS_FAST,
)
# Optional Gadgetbridge support (requires bluez_peripheral)
try:
    from .ble_gatt_server import GadgetbridgeService
    HAS_GADGETBRIDGE = True
except ImportError:
    GadgetbridgeService = None
    HAS_GADGETBRIDGE = False

__all__ = [
    "BluetoothManager",
    "BtOpenResult",
    "BTPan",
    "BTPanDbus",
    "BTPanDbusFast",
    "HAS_DBUS",
    "HAS_DBUS_FAST",
    "GadgetbridgeService",
    "HAS_GADGETBRIDGE",
]
