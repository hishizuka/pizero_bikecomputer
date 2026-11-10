"""Start each Linux LE connection with parameters validated on the target hardware.

The kernel and BlueZ keep the last parameters a peripheral requested and use them for
its next connection. On CM0, a sensor that had requested a slow idle link made later
GATT discovery slower and less reliable. Loading the measured working values before
each connection avoids inheriting that state. BlueZ has no D-Bus API for this, so the
values are loaded per device through the MGMT interface.
"""

import ctypes
import os
import socket
import struct

MGMT_OP_LOAD_CONN_PARAM = 0x0035
MGMT_EV_CMD_COMPLETE = 0x0001
MGMT_EV_CMD_STATUS = 0x0002
MGMT_STATUS_PERMISSION_DENIED = 0x14
MGMT_RESPONSE_TIMEOUT = 2.0
HCI_DEV_NONE = 0xFFFF
HCI_CHANNEL_CONTROL = 3
LE_ADDRESS_TYPES = {"public": 0x01, "random": 0x02}

# 30-50 ms keeps discovery short; 5 s survives Wi-Fi coexistence gaps on combo chips.
INITIAL_MIN_INTERVAL = 24
INITIAL_MAX_INTERVAL = 40
INITIAL_LATENCY = 0
INITIAL_SUPERVISION_TIMEOUT = 500


class _SockaddrHci(ctypes.Structure):
    _fields_ = (
        ("family", ctypes.c_ushort),
        ("device", ctypes.c_ushort),
        ("channel", ctypes.c_ushort),
    )


def build_load_conn_param(index: int, address: str, address_type: str) -> bytes:
    address_bytes = bytes.fromhex(address.replace(":", ""))[::-1]
    payload = (
        struct.pack("<H", 1)
        + address_bytes
        + struct.pack(
            "<BHHHH",
            LE_ADDRESS_TYPES[address_type],
            INITIAL_MIN_INTERVAL,
            INITIAL_MAX_INTERVAL,
            INITIAL_LATENCY,
            INITIAL_SUPERVISION_TIMEOUT,
        )
    )
    return struct.pack("<HHH", MGMT_OP_LOAD_CONN_PARAM, index, len(payload)) + payload


def _bind_control_channel(sock: socket.socket) -> None:
    # socket.bind() cannot select the HCI channel.
    libc = ctypes.CDLL(None, use_errno=True)
    address = _SockaddrHci(socket.AF_BLUETOOTH, HCI_DEV_NONE, HCI_CHANNEL_CONTROL)
    if libc.bind(sock.fileno(), ctypes.byref(address), ctypes.sizeof(address)) < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


def _read_command_status(sock: socket.socket, index: int) -> int:
    while True:
        response = sock.recv(1024)
        event, response_index, _length = struct.unpack_from("<HHH", response)
        if response_index != index:
            continue
        if event not in (MGMT_EV_CMD_COMPLETE, MGMT_EV_CMD_STATUS):
            continue
        opcode, status = struct.unpack_from("<HB", response, 6)
        if opcode == MGMT_OP_LOAD_CONN_PARAM:
            return status


def load_initial_connection_parameters(
    adapter: str, address: str, address_type: str
) -> bool:
    """Return False when the process lacks CAP_NET_ADMIN, which MGMT writes require."""
    index = int(adapter.removeprefix("hci"))
    with socket.socket(
        socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI
    ) as sock:
        sock.settimeout(MGMT_RESPONSE_TIMEOUT)
        _bind_control_channel(sock)
        sock.send(build_load_conn_param(index, address, address_type))
        status = _read_command_status(sock, index)
    if status == MGMT_STATUS_PERMISSION_DENIED:
        return False
    if status != 0:
        raise OSError(f"MGMT Load Connection Parameters status 0x{status:02x}")
    return True
