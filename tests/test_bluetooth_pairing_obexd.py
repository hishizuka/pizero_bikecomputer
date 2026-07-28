import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from modules.helper.bluetooth.bluetooth_manager import BluetoothManager


class FakeStdin:
    def __init__(self):
        self.commands = []

    def write(self, data):
        self.commands.append(data.decode().strip())

    async def drain(self):
        pass


class FakeProcess:
    def __init__(self, running=True):
        self.stdin = FakeStdin()
        self.stdout = None
        self.stderr = None
        self.returncode = None if running else 1
        self.terminated = False
        self.killed = False

    async def wait(self):
        if self.returncode is None:
            raise asyncio.TimeoutError
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9


class TestBluetoothPairingObexd(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            G_IS_RASPI=True,
            G_OBEXD_CMD="/usr/libexec/bluetooth/obexd",
            G_COURSE_DIR="courses",
            bt_pan=None,
        )
        self.manager = BluetoothManager(self.config, 180)

    @patch(
        "modules.helper.bluetooth.bluetooth_manager.os.path.isfile", return_value=True
    )
    @patch("modules.helper.bluetooth.bluetooth_manager.shutil.which")
    async def test_pairing_starts_obexd_before_bluetoothctl(
        self, mock_which, mock_isfile
    ):
        mock_which.return_value = "/usr/bin/bluetoothctl"
        obexd_proc = FakeProcess()
        bluetoothctl_proc = FakeProcess()
        commands = []

        async def create_process(*args, **kwargs):
            commands.append(args)
            if args[0] == self.config.G_OBEXD_CMD:
                return obexd_proc
            return bluetoothctl_proc

        with (
            patch.object(self.manager, "get_paired_bt_devices"),
            patch(
                "modules.helper.bluetooth.bluetooth_manager.asyncio.create_subprocess_exec",
                side_effect=create_process,
            ),
        ):
            await self.manager.start_bt_pairing()

        self.assertEqual(commands[0][0], self.config.G_OBEXD_CMD)
        self.assertEqual(
            commands[0][1:],
            (
                "-n",
                "-r",
                os.path.abspath(self.config.G_COURSE_DIR),
                "-p",
                "filesystem,bluetooth,opp,ftp",
            ),
        )
        self.assertEqual(commands[1][0], "bluetoothctl")
        self.assertEqual(
            bluetoothctl_proc.stdin.commands,
            [
                "agent DisplayOnly",
                "default-agent",
                "pairable on",
                "discoverable on",
                "scan on",
            ],
        )

    async def test_open_obexd_does_not_start_twice(self):
        self.manager.bt_pairing_obexd_proc = FakeProcess()

        with patch(
            "modules.helper.bluetooth.bluetooth_manager.asyncio.create_subprocess_exec"
        ) as create_process:
            result = await self.manager.open_bt_pairing_obexd_proc()

        self.assertTrue(result)
        create_process.assert_not_called()

    async def test_stop_pairing_stops_bluetoothctl_and_obexd(self):
        bluetoothctl_proc = FakeProcess()
        obexd_proc = FakeProcess()
        self.manager.bt_pairing_proc = bluetoothctl_proc
        self.manager.bt_pairing_obexd_proc = obexd_proc

        await self.manager.stop_bt_pairing()

        self.assertEqual(
            bluetoothctl_proc.stdin.commands,
            ["scan off", "discoverable off", "pairable off"],
        )
        self.assertTrue(bluetoothctl_proc.terminated)
        self.assertTrue(obexd_proc.terminated)
        self.assertIsNone(self.manager.bt_pairing_proc)
        self.assertIsNone(self.manager.bt_pairing_obexd_proc)

    @patch(
        "modules.helper.bluetooth.bluetooth_manager.os.path.isfile", return_value=True
    )
    async def test_open_obexd_handles_immediate_exit(self, mock_isfile):
        proc = FakeProcess(running=False)

        with patch(
            "modules.helper.bluetooth.bluetooth_manager.asyncio.create_subprocess_exec",
            return_value=proc,
        ):
            result = await self.manager.open_bt_pairing_obexd_proc()

        self.assertFalse(result)
        self.assertIsNone(self.manager.bt_pairing_obexd_proc)


if __name__ == "__main__":
    unittest.main()
