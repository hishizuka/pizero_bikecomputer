"""Bluetooth-related helper modules."""

from .bluetooth_manager import BluetoothManager, BtOpenResult
from .bt_pan import (
    BTPan,
    BTPanDbus,
    BTPanDbusFast,
    HAS_DBUS,
    HAS_DBUS_FAST,
)

# Optional Gadgetbridge support (requires gadgetbridge-rpi-link)
try:
    from gadgetbridge_rpi_link.bluez import is_bluez_supported

    from .ble_gatt_server import GadgetbridgeService

    if is_bluez_supported():
        HAS_GADGETBRIDGE = True
    else:
        GadgetbridgeService = None
        HAS_GADGETBRIDGE = False
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
