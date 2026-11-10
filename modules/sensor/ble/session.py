"""Connection-session policy shared by BLE sensor profiles."""

import asyncio

GATT_SETUP_TIMEOUT = 20.0


class BleSetupDeadline:
    """Apply one deadline across all GATT operations needed to make a link ready."""

    def __init__(self, timeout: float = GATT_SETUP_TIMEOUT):
        self.deadline = asyncio.get_running_loop().time() + timeout

    async def wait(self, operation):
        async with asyncio.timeout_at(self.deadline):
            return await operation
