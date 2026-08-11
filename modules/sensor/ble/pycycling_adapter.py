from __future__ import annotations

from typing import Callable

CSC_MEASUREMENT_UUID = "00002a5b-0000-1000-8000-00805f9b34fb"
CPS_MEASUREMENT_UUID = "00002a63-0000-1000-8000-00805f9b34fb"
HRS_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def _hrs_measurement_length(data: bytes | bytearray) -> int | None:
    if len(data) < 1:
        return None
    flags = data[0]
    expected = 1 + (2 if flags & 0x01 else 1)
    if flags & 0x08:
        expected += 2
    if flags & 0x10:
        expected += 2
    return expected


def _csc_measurement_length(data: bytes | bytearray) -> int | None:
    if len(data) < 1:
        return None
    flags = data[0]
    expected = 1
    if flags & 0x01:
        expected += 6
    if flags & 0x02:
        expected += 4
    return expected


def _cps_measurement_length(data: bytes | bytearray) -> int | None:
    if len(data) < 2:
        return None
    flags = int.from_bytes(data[:2], "little")
    expected = 4  # flags and instantaneous power
    optional_lengths = (
        (0, 1),
        (2, 2),
        (4, 6),
        (5, 4),
        (6, 4),
        (7, 4),
        (8, 3),
        (9, 2),
        (10, 2),
        (11, 2),
    )
    for bit, length in optional_lengths:
        if flags & (1 << bit):
            expected += length
    return expected


_MEASUREMENT_LENGTHS = {
    HRS_MEASUREMENT_UUID: _hrs_measurement_length,
    CSC_MEASUREMENT_UUID: _csc_measurement_length,
    CPS_MEASUREMENT_UUID: _cps_measurement_length,
}


class PycyclingValidationClient:
    """Validate variable-length GATT payloads before pycycling parses them."""

    def __init__(
        self,
        client,
        *,
        on_invalid_payload: Callable[[str, int, int | None], None] | None = None,
    ):
        self._client = client
        self.hrs_sensor_contact: bool | None = None
        self.hrs_sensor_contact_observed = False
        self._on_invalid_payload = on_invalid_payload or (
            lambda _uuid, _actual, _expected: None
        )

    def __getattr__(self, name):
        return getattr(self._client, name)

    async def start_notify(self, characteristic, callback, **kwargs):
        uuid = str(characteristic).lower()
        expected_length = _MEASUREMENT_LENGTHS.get(uuid)
        if expected_length is None:
            return await self._client.start_notify(characteristic, callback, **kwargs)

        def validated_callback(sender, data):
            expected = expected_length(data)
            if expected is None or len(data) < expected:
                self._on_invalid_payload(uuid, len(data), expected)
                return None
            if uuid == HRS_MEASUREMENT_UUID:
                # pycycling checks both contact bits together. Clear the support
                # bit so its bool reflects only the detected-status bit.
                data = bytearray(data)
                self.hrs_sensor_contact_observed = True
                self.hrs_sensor_contact = (
                    bool(data[0] & 0x02) if data[0] & 0x04 else None
                )
                data[0] &= ~0x04
            return callback(sender, data)

        return await self._client.start_notify(
            characteristic,
            validated_callback,
            **kwargs,
        )
