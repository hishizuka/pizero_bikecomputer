"""PiLink settings and asynchronous service control shared by both GUIs."""

import asyncio
from contextlib import asynccontextmanager
import json
import os

from modules.app_logger import app_logger
from modules.sensor.ble.adapter import (
    BleAdapterNotFoundError,
    BleAdapterPolicy,
    BleAdapterResolutionError,
    BleAdapterResolver,
)


class PiLinkService:
    def __init__(self, config):
        self.config = config
        self.resolver = BleAdapterResolver()
        self.installed = False
        self.bluetooth_on = False
        self.wifi_on = False
        self.state = None
        self.adapter = None
        self.adapter_label = "Unused"
        self.error = None
        self.note = ""
        self._lock = asyncio.Lock()
        self._listeners = []

    @property
    def available(self):
        return self.installed and self.bluetooth_on

    @property
    def busy(self):
        return self._lock.locked()

    @property
    def can_control(self):
        return (
            self.available
            and not self.busy
            and self.config.setting.pilink_error is None
        )

    @property
    def status_label(self):
        if self.config.setting.pilink_error:
            return self.config.setting.pilink_error
        if not self.installed:
            return "Not installed"
        if not self.bluetooth_on:
            return "Bluetooth OFF"
        if self.busy:
            return "Applying..."
        if self.error:
            return self.error
        label = {
            "active": "Running",
            "inactive": "Stopped",
            "failed": "Failed",
            "activating": "Starting...",
            "deactivating": "Stopping...",
        }.get(self.state, self.state or "Unknown")
        return f"{label}: {self.note}" if self.note else label

    def subscribe(self, listener):
        self._listeners.append(listener)

    def is_network_active(self):
        try:
            with open(self.config.G_PILINK_NETWORK_STATUS_FILE) as stream:
                status = json.load(stream)
        except (OSError, ValueError):
            return False
        return isinstance(status, dict) and status.get("active") is True

    def _notify(self):
        for listener in self._listeners:
            listener()

    @asynccontextmanager
    async def _operation(self):
        try:
            async with self._lock:
                yield
        finally:
            # Publish the final state after releasing the lock.
            self._notify()

    async def _command(self, *args):
        command = [self.config.G_PILINK_CONTROL_CMD, *args]
        if os.geteuid() != 0:
            command = ["sudo", "-n", *command]
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            output, error = await asyncio.wait_for(process.communicate(), timeout=120)
            if process.returncode and not output:
                raise ValueError(error.decode().strip() or "PiLink operation failed")
            result = json.loads(output)
            if args[0] != "status":
                app_logger.info(
                    "[PiLink] %s: ok=%s state=%s adapter=%s reason=%s message=%s",
                    " ".join(args),
                    result["ok"],
                    result["state"],
                    result["adapter"],
                    result["reason"],
                    result["message"],
                )
            return result
        except (OSError, ValueError, asyncio.TimeoutError) as error:
            return {
                "ok": False,
                "reason": "command_failed",
                "message": str(error) or "PiLink operation timed out",
                "installed": self.installed,
                "state": self.state,
                "adapter": self.adapter,
            }
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()

    async def _record(self, result):
        previous = (self.installed, self.state, self.adapter)
        self.installed = result["installed"]
        self.state = result["state"]
        self.adapter = result["adapter"]
        if previous != (self.installed, self.state, self.adapter):
            app_logger.info(
                "[PiLink] status: installed=%s state=%s adapter=%s",
                self.installed,
                self.state,
                self.adapter,
            )
        if self.adapter:
            self.adapter_label = f"Unknown / {self.adapter}"
            adapters = await asyncio.to_thread(self.resolver.adapters)
            for adapter in adapters:
                if adapter.name == self.adapter:
                    role = "External" if adapter.is_nrf52840_bridge else "Internal"
                    self.adapter_label = f"{role} / {self.adapter}"
                    break
        else:
            self.adapter_label = {
                "inactive": "Unused",
                "failed": "Unused",
                "activating": "Starting...",
                "deactivating": "Stopping...",
            }.get(self.state, "Unknown")
        if not result["ok"]:
            self.error = result["message"]
            app_logger.warning("[PiLink] %s", self.error)

    async def _refresh(self):
        from modules.helper.network.wifi_manager import get_wifi_bt_status

        if not self.config.G_IS_RASPI:
            self.installed = False
            self.bluetooth_on = False
            return
        self.wifi_on, self.bluetooth_on = await asyncio.to_thread(get_wifi_bt_status)
        if not os.path.isfile(self.config.G_PILINK_CONTROL_CMD):
            self.installed = False
            return
        await self._record(await self._command("status"))

    async def refresh(self):
        if self.busy:
            return
        async with self._operation():
            await self._refresh()

    async def _apply(self):
        await self._refresh()
        if not self.installed or self.config.setting.pilink_error:
            return False
        self.error = None
        self.note = ""
        app_logger.info(
            "[PiLink] applying settings: enabled=%s use_secondary=%s bluetooth_on=%s",
            self.config.G_PILINK["ENABLED"],
            self.config.G_PILINK["USE_SECONDARY"],
            self.bluetooth_on,
        )
        if not self.config.G_PILINK["ENABLED"]:
            result = await self._command("disable")
            await self._record(result)
            return result["ok"]
        if not self.bluetooth_on:
            return False
        policies = [BleAdapterPolicy.BUILTIN]
        if self.config.G_PILINK["USE_SECONDARY"]:
            policies.insert(0, BleAdapterPolicy.NRF52840_BRIDGE)
        for policy in policies:
            try:
                adapter = await asyncio.to_thread(self.resolver.resolve, policy)
            except BleAdapterResolutionError as error:
                if policy != BleAdapterPolicy.NRF52840_BRIDGE or not isinstance(
                    error, BleAdapterNotFoundError
                ):
                    self.error = str(error)
                    app_logger.warning("[PiLink] %s", error)
                    return False
                fallback_reason = str(error)
            else:
                app_logger.info("[PiLink] selected %s / %s", policy.value, adapter)
                result = await self._command("apply", "--adapter", adapter)
                if (
                    policy != BleAdapterPolicy.NRF52840_BRIDGE
                    or result["ok"]
                    or result["reason"] != "adapter_unavailable"
                ):
                    await self._record(result)
                    return result["ok"]
                fallback_reason = result["message"]
            self.note = "External unavailable; using internal"
            app_logger.info("[PiLink] %s: %s", self.note, fallback_reason)

    async def apply(self):
        async with self._operation():
            self._notify()
            return await self._apply()

    async def set_setting(self, key, value):
        if not self.can_control:
            return False
        async with self._operation():
            self._notify()
            previous = self.config.G_PILINK[key]
            self.config.G_PILINK[key] = value
            try:
                await asyncio.to_thread(self.config.setting.write_config)
            except OSError as error:
                self.config.G_PILINK[key] = previous
                self.error = f"Could not save settings: {error}"
                app_logger.warning("[PiLink] %s", self.error)
                return False
            self._notify()
            if key == "USE_SECONDARY" and not self.config.G_PILINK["ENABLED"]:
                return True
            return await self._apply()

    async def stop(self):
        async with self._operation():
            if self.installed:
                await self._record(await self._command("stop"))
