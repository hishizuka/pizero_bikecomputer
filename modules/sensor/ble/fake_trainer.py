#!/usr/bin/env python3
import asyncio
import math
import struct
import signal

from bluez_peripheral.util import (
    get_message_bus,
    Adapter,
    is_bluez_available,
)
from bluez_peripheral.advert import Advertisement
from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import (
    characteristic,
    CharacteristicFlags as CharFlags,
)


class FtmsService(Service):
    """
    Simple FTMS (Indoor Bike) emulator compliant with bluez_peripheral.
    """

    # Specify 16-bit UUIDs as strings
    UUID_FTMS = "1826"
    UUID_FITNESS_MACHINE_FEATURE = "2ACC"
    UUID_INDOOR_BIKE_DATA = "2AD2"
    UUID_FITNESS_MACHINE_STATUS = "2ADA"
    UUID_FITNESS_MACHINE_CONTROL_POINT = "2AD9"

    def __init__(self) -> None:
        # Internal state
        self._running = False
        self._has_control = False
        self._elapsed_time = 0  # sec

        self._speed_kmh = 25.0
        self._cadence_rpm = 90.0
        self._power_w = 180

        # Fitness Machine Feature (4 bytes) + Target Settings Feature (4 bytes)
        self._feature_bytes = struct.pack("<II", 0, 0)

        # Dummy Fitness Machine Status (2 bytes: opcode, param)
        self._status_bytes = bytes([0x00, 0x00])

        # Service(UUID, primary)
        super().__init__(self.UUID_FTMS, True)

    # ------------------------------
    #  Fitness Machine Feature 0x2ACC (READ)
    # ------------------------------
    @characteristic(UUID_FITNESS_MACHINE_FEATURE, CharFlags.READ)
    def fitness_machine_feature(self, options) -> bytes:
        return self._feature_bytes

    # ------------------------------
    #  Indoor Bike Data 0x2AD2 (READ / NOTIFY)
    # ------------------------------
    @characteristic(
        UUID_INDOOR_BIKE_DATA,
        CharFlags.READ | CharFlags.NOTIFY,
    )
    def indoor_bike_data(self, options) -> bytes:
        return self._build_indoor_bike_data()

    def _build_indoor_bike_data(self) -> bytes:
        """
        Minimal Indoor Bike Data payload:
          Flags (uint16 LE)
          Instantaneous Speed   (uint16, 1/100 km/h)
          Instantaneous Cadence (uint16, 1/2 rpm)      [bit2]
          Instantaneous Power   (sint16, W)            [bit6]
          Elapsed Time          (uint16, s)            [bit11]
        """
        flags = 0
        flags |= (1 << 2)   # Cadence present
        flags |= (1 << 6)   # Power present
        flags |= (1 << 11)  # Elapsed time present

        parts = []

        # Flags
        parts.append(struct.pack("<H", flags))

        # Instantaneous Speed (1/100 km/h)
        inst_speed = int(self._speed_kmh * 100.0)
        parts.append(struct.pack("<H", inst_speed))

        # Instantaneous Cadence (1/2 rpm)
        inst_cad = int(self._cadence_rpm * 2.0)
        parts.append(struct.pack("<H", inst_cad))

        # Instantaneous Power (sint16)
        inst_power = int(self._power_w)
        parts.append(struct.pack("<h", inst_power))

        # Elapsed Time (seconds)
        elapsed = int(self._elapsed_time)
        parts.append(struct.pack("<H", elapsed))

        return b"".join(parts)

    # ------------------------------
    #  Fitness Machine Status 0x2ADA (READ / NOTIFY)
    # ------------------------------
    @characteristic(
        UUID_FITNESS_MACHINE_STATUS,
        CharFlags.READ | CharFlags.NOTIFY,
    )
    def machine_status(self, options) -> bytes:
        return self._status_bytes

    def _set_status(self, opcode: int, param: int = 0) -> None:
        self._status_bytes = bytes([opcode & 0xFF, param & 0xFF])
        self.machine_status.changed(self._status_bytes)

    # ------------------------------
    #  Fitness Machine Control Point 0x2AD9 (WRITE / INDICATE)
    # ------------------------------
    @characteristic(
        UUID_FITNESS_MACHINE_CONTROL_POINT,
        CharFlags.WRITE | CharFlags.INDICATE,
    )
    def control_point(self, options):
        # Read is unused
        return b""

    @control_point.setter
    def control_point(self, value: bytes, options) -> None:
        """
        Implement only required opcodes:
          0x00: Request Control
          0x01: Reset
          0x07: Start or Resume
          0x08: Stop or Pause

        Response:
          [0] 0x80 (Response Code)
          [1] Request Op Code
          [2] Result Code (0x01 = Success, 0x02 = Op Code not supported)
        """
        if not value:
            return

        op = value[0]
        result = 0x02  # Op Code not supported

        if op == 0x00:  # Request Control
            self._has_control = True
            result = 0x01  # Success
            self._set_status(0x01, 0x01)

        elif op == 0x01:  # Reset
            self._elapsed_time = 0
            result = 0x01
            self._set_status(0x02, 0x00)

        elif op == 0x07:  # Start or Resume
            # For experimentation, treat has_control leniently
            self._running = True
            result = 0x01
            self._set_status(0x03, 0x00)

        elif op == 0x08:  # Stop or Pause
            self._running = False
            result = 0x01
            self._set_status(0x04, 0x00)

        # Indicate the Response Code
        resp = bytes([0x80, op & 0xFF, result & 0xFF])
        self.control_point.changed(resp)

    # ------------------------------
    #  Dummy bike behavior loop
    # ------------------------------
    async def run_fake_bike_loop(self, stop_event: asyncio.Event):
        """
        Until stop_event is set, update dummy values every second
        and notify Indoor Bike Data.
        """
        t = 0.0
        while not stop_event.is_set():
            await asyncio.sleep(1.0)

            if self._running:
                self._elapsed_time += 1
                self._speed_kmh = 30.0 + 2.0 * math.sin(t / 5.0)
                self._cadence_rpm = 90.0 + 10.0 * math.sin(t / 3.0)
                self._power_w = 200 + int(20.0 * math.sin(t / 4.0))
                t += 1.0

            payload = self._build_indoor_bike_data()
            self.indoor_bike_data.changed(payload)


async def main():
    bus = await get_message_bus()
    if not await is_bluez_available(bus):
        print("BlueZ not found on D-Bus. Please check that bluetoothd is running.")
        return

    # Register FTMS service
    ftms_service = FtmsService()
    await ftms_service.register(bus)

    # Get adapter and power on
    adapter = await Adapter.get_first(bus)
    await adapter.set_powered(True)

    # Create and register advertisement
    # 0x0340: Cycling, Cycling Computer appearance
    advert = Advertisement("FakeTrainer", [FtmsService.UUID_FTMS], 0x0340, 0)
    await advert.register(bus, adapter)

    print("FTMS emulator started: advertising as FakeTrainer (Ctrl+C to quit)")

    # On Ctrl+C, call stop_event.set()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)

    # Dummy data notify loop
    bike_task = asyncio.create_task(ftms_service.run_fake_bike_loop(stop_event))

    # Wait until Ctrl+C is pressed
    await stop_event.wait()
    print("\nCtrl+C received, starting shutdown...")

    # The task will wind down naturally here, so just await it
    try:
        await bike_task
    except asyncio.CancelledError:
        # Safety net (normally not reached)
        pass

    # Unregister advertisement
    try:
        await advert.unregister()
    except Exception as e:
        print(f"Error in advert.unregister(): {e}")

    # Unregister GATT service
    try:
        await ftms_service.unregister()
    except Exception as e:
        print(f"Error in ftms_service.unregister(): {e}")

    print("Cleanup complete. Exiting.")


if __name__ == "__main__":
    asyncio.run(main())
