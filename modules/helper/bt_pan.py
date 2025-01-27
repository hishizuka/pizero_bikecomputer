import asyncio

from logger import app_logger

HAS_DBUS_NEXT = False
HAS_DBUS = False

try:
    from dbus_next import BusType, DBusError
    from dbus_next.service import ServiceInterface, method, signal, dbus_property
    from dbus_next.aio.message_bus import MessageBus
    from dbus_next import Variant

    HAS_DBUS_NEXT = True
except ImportError:
    pass

try:
    if not HAS_DBUS_NEXT:
        import dbus

        HAS_DBUS = True
except ImportError:
    pass


class BTPan:
    bus = None
    devices = {}

    obj_bluez = "org.bluez"
    obj_object_manager = "org.freedesktop.DBus.ObjectManager"
    obj_properties = "org.freedesktop.DBus.Properties"
    obj_device = "org.bluez.Device1"
    obj_service = "org.bluez.Network1"
    path_bluez = "/org/bluez"

    service_uuid = "nap"
    remote_addr = ""
    interface = None


class BTPanDbusNext(BTPan):
    async def check_dbus(self):
        try:
            self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            await self.bus.introspect(self.obj_bluez, self.path_bluez)
            return True
        except Exception as e:  # noqa
            app_logger.warning(f"Check dbus failed {e}")
        return False

    async def find_bt_pan_devices(self):
        res = {}
        self.devices = {}

        proxy_object = self.bus.get_proxy_object(
            self.obj_bluez, "/", await self.bus.introspect(self.obj_bluez, "/")
        )
        manager = proxy_object.get_interface(self.obj_object_manager)
        objs = await manager.call_get_managed_objects()
        for path, ifaces in objs.items():
            if self.obj_service in ifaces.keys():
                proxy_object = self.bus.get_proxy_object(
                    self.obj_bluez,
                    path,
                    await self.bus.introspect(self.obj_bluez, path),
                )
                device = proxy_object.get_interface(self.obj_device)
                address = await device.get_address()
                res[await device.get_name()] = address
                self.devices[address] = path

        return res

    async def initialize_device(self, remote_addr):
        try:
            if self.remote_addr != remote_addr:
                obj_remote_addr = self.devices[remote_addr]
                proxy_object = self.bus.get_proxy_object(
                    self.obj_bluez,
                    obj_remote_addr,
                    await self.bus.introspect(self.obj_bluez, obj_remote_addr),
                )
                self.interface = proxy_object.get_interface(self.obj_service)
                self.remote_addr = remote_addr
        except Exception:  # noqa
            app_logger.exception("[BT] failed to initialize_device")
            return False
        return True

    async def connect_tethering(self, remote_addr):
        res_err = ""
        if not await self.initialize_device(remote_addr):
            return res_err

        try:
            await self.interface.call_connect(self.service_uuid)
        except DBusError as e:
            app_logger.error(f"[BT] {e}, {type(e)}")
            res_err = repr(e)
        return res_err

    async def disconnect_tethering(self, remote_addr):
        res_err = ""
        if not await self.initialize_device(remote_addr):
            return res_err

        try:
            await self.interface.call_disconnect()
        except DBusError as e:
            app_logger.error(f"[BT] {e}")
            res_err = repr(e)
        return res_err


# based on bluez(https://github.com/bluez/bluez) test/test-network
class BTPanDbus(BTPan):
    async def check_dbus(self):
        try:
            self.bus = dbus.SystemBus()
            self.bus.get_name_owner(self.obj_bluez)
            return True
        except Exception as e:  # noqa
            app_logger.warning(f"[BT] Check dbus failed {e}")
        return False

    def get_managed_objects(self):
        manager = dbus.Interface(
            self.bus.get_object(self.obj_bluez, "/"), self.obj_object_manager
        )
        return manager.GetManagedObjects()

    async def find_bt_pan_devices(self):
        objects = self.get_managed_objects()
        res = {}
        self.devices = {}

        for path, ifaces in objects.items():
            for i in ifaces:
                if self.obj_service in i:
                    device = ifaces.get(self.obj_device)
                    res[device["Name"]] = device["Address"]
                    self.devices[device["Address"]] = path
        return res

    def prop_get(self, obj, k, iface=None):
        if iface is None:
            iface = obj.dbus_interface
        return obj.Get(iface, k, dbus_interface=self.obj_properties)

    def initialize_device(self, remote_addr):
        try:
            if self.remote_addr != remote_addr:
                self.interface = dbus.Interface(
                    self.bus.get_object(self.obj_bluez, self.devices[remote_addr]),
                    self.obj_service,
                )
                self.remote_addr = remote_addr
        except Exception:  # noqa
            app_logger.exception("[BT] failed to initialize_device")
            return False
        return True

    async def connect_tethering(self, remote_addr):
        if not self.initialize_device(remote_addr):
            return False

        for n in range(2):
            try:
                self.interface.Connect(self.service_uuid)
            except dbus.exceptions.DBusException as e:
                app_logger.error(f"[BT] {e.get_dbus_name()}")
                await asyncio.sleep(1)
            else:
                break
        connected = self.prop_get(self.interface, "Connected")

        return connected

    async def disconnect_tethering(self, remote_addr):
        if not self.initialize_device(remote_addr):
            return False

        try:
            self.interface.Disconnect()
        except dbus.exceptions.DBusException as e:
            app_logger.error(f"[BT] {e.get_dbus_name()}")
        connected = self.prop_get(self.interface, "Connected")

        return connected
