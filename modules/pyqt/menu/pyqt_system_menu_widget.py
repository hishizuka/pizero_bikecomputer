import asyncio
import logging
from functools import partial

from modules.app_logger import app_logger
from modules._qt_qtwidgets import (
    QT_TEXTEDIT_NOWRAP,
    QT_SCROLLBAR_ALWAYSOFF,
    QtWidgets,
    QtCore,
    qasync,
)
from modules.utils.network import detect_network
from .pyqt_menu_widget import MenuWidget, ListWidget, ListItemWidget


class SystemMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Network", "submenu", self.network),
            ("Brightness", None, None),
            ("Language", None, None),
            (
                "Update",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.config.update_application, "Update"
                ),
            ),
            ("Debug", "submenu", self.debug),
            (
                "Power Off",
                "dialog",
                lambda: self.config.gui.show_dialog(self.config.gui.power_off, "Power Off"),
            ),
        )
        self.add_buttons(button_conf)

    def network(self):
        self.change_page("Network", preprocess=True)

    def debug(self):
        self.change_page("Debug")


class NetworkMenuWidget(MenuWidget):
    def setup_menu(self):
        wifi_bt_button_func_wifi = None
        wifi_bt_button_func_bt = None

        if self.config.G_IS_RASPI:
            wifi_bt_button_func_wifi = lambda: self.onoff_wifi_bt(True, "Wifi")
            wifi_bt_button_func_bt = lambda: self.onoff_wifi_bt(True, "Bluetooth")

        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Wifi", "toggle", wifi_bt_button_func_wifi),
            ("Bluetooth", "toggle", wifi_bt_button_func_bt),
            ("BT Pairing", "submenu", self.bt_pairing),
            ("BT Paired Devices", "submenu", self.bt_paired_devices),
            ("BT Tethering", "submenu", self.bt_tething),  ### move to BluetoothPairedDeviceListWidget
            (
                "connect Wifi via WPS",
                "dialog",
                lambda: self.config.gui.show_dialog(self.wifi_connect_with_wps, "Connect to Wifi with WPS?")
            ),
            ("IP Address", "dialog", self.show_ip_address),
        )
        self.add_buttons(button_conf)

        if self.config.bt_pan is None:
            self.buttons["BT Tethering"].disable()
        
        if not self.config.G_IS_RASPI:
            self.buttons["BT Tethering"].disable()
            self.buttons["BT Paired Devices"].disable()
            self.buttons["BT Pairing"].disable()

    def preprocess(self):
        # initialize toggle button status
        if self.config.G_IS_RASPI:
            self.onoff_wifi_bt(change=False, key="Wifi")
            self.onoff_wifi_bt(change=False, key="Bluetooth")

    def onoff_wifi_bt(self, change=True, key=None):
        if change:
            self.config.network.onoff_wifi_bt(key)
        status = {}
        status["Wifi"], status["Bluetooth"] = self.config.network.get_wifi_bt_status()
        self.buttons[key].change_toggle(status[key])

    def bt_pairing(self):
        self.change_page("BT Pairing", preprocess=True)

    def bt_paired_devices(self):
        self.change_page("BT Paired Devices", preprocess=True)

    def bt_tething(self):
        self.change_page("BT Tethering", preprocess=True)

    @qasync.asyncSlot()
    async def wifi_connect_with_wps(self):
        self.config.gui.show_dialog_cancel_only(None, "Trying to connect...")
        await asyncio.sleep(1)  # wait for dialog to show
        connect_status = await self.config.network.wifi_connect_with_wps()

        # Show final result
        if connect_status:
            self.config.gui.change_dialog(
                title="Connection succeeded!", button_label="OK"
            )
        else:
            self.config.gui.change_dialog(
                title="Connection failed for some reason!", button_label="OK"
            )

    def show_ip_address(self):
        address = detect_network() or "No address"
        # Button is OK only
        self.config.gui.show_dialog_ok_only(None, address)


class BluetoothTetheringListWidget(ListWidget):
    run_bt_tethering = False

    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = {}
        super().__init__(parent=parent, page_name=page_name, config=config)

    def preprocess(self, run_bt_tethering=True):
        super().preprocess(reset=True)
        if self.config.bt_pan is not None:
            self.settings = self.config.bt_pan.get_bt_pan_devices()
            self.update_list()
        self.run_bt_tethering = run_bt_tethering

    def get_default_value(self):
        return self.config.G_BT_PAN_DEVICE

    async def button_func_extra(self):
        self.config.G_BT_PAN_DEVICE = self.selected_item.title
        if self.run_bt_tethering:
            await self.config.network.bluetooth_tethering()
            self.config.setting.write_config()


class BluetoothPairingListWidget(ListWidget):

    def __init__(self, parent, page_name, config):
        self.settings = {}
        self.use_detail = True
        super().__init__(parent, page_name, config)

    def setup_menu(self):
        super().setup_menu()
        # update panel for every 1 seconds
        self.timer = QtCore.QTimer(parent=self)
        self.timer.timeout.connect(self.update_display)

    @qasync.asyncSlot()
    async def button_func(self):
        if self.selected_item is None:
            return
        self.config.gui.show_dialog(
            self.pair_bt_device,
            "Pair with this device?",
        )
    
    @qasync.asyncSlot()
    async def pair_bt_device(self):
        self.config.gui.show_dialog_cancel_only(
            self.back, "Pair with your phone."
        )
        res = await self.config.network.pair_bt_device(self.selected_item.detail)
        await asyncio.sleep(2)
        msg = ""
        if res:
            msg = "Bluetooth pairing successful!"
        else:
            msg = "Bluetooth pairing failed."
        self.config.gui.show_forced_message(msg)

    def on_back_menu(self):
        self.timer.stop()
        asyncio.create_task(self.config.network.stop_bt_pairing())

    def preprocess(self):
        super().preprocess(reset=True)

    def preprocess_extra(self):
        self.settings.clear()
        asyncio.create_task(self.config.network.start_bt_pairing())
        self.timer.start(self.config.G_DRAW_INTERVAL)
        super().preprocess_extra()

    def update_display(self):
        self.add_list(self.config.network.get_bt_pairing_list())
 

class BluetoothPairedDeviceListWidget(ListWidget):
    settings = {}
    
    def preprocess(self):
        super().preprocess(reset=True)
        self.settings = self.config.network.get_paired_bt_devices()
        self.update_list()

    @qasync.asyncSlot()
    async def button_func(self):
        self.config.gui.show_dialog(
            self.remove_bt_device,
            "Delete this device?",
        )
    
    @qasync.asyncSlot()
    async def remove_bt_device(self):
        await self.config.network.remove_bt_device(self.settings[self.selected_item.title])
        self.back()
        


class DebugMenuWidget(MenuWidget):
    is_log_level_debug = False

    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Debug Log", "submenu", self.debug_log),
            ("Debug Level Log", "toggle", lambda: self.set_log_level_to_debug(True)),
            (
                "Disable Wifi/BT",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    partial(self.config.network.hardware_wifi_bt, False),
                    "Disable Wifi/BT\n(need reboot)",
                ),
            ),
            (
                "Enable Wifi/BT",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    partial(self.config.network.hardware_wifi_bt, True),
                    "Enable Wifi/BT\n(need reboot)",
                ),
            ),
            (
                "Restart",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.config.restart_application, "Restart Application"
                ),
            ),
            (
                "Reboot",
                "dialog",
                lambda: self.config.gui.show_dialog(self.config.reboot, "Reboot"),
            ),
        )
        self.add_buttons(button_conf)

    def preprocess(self):
        # initialize toggle button status
        self.set_log_level_to_debug(change=False)

    def debug_log(self):
        self.change_page("Debug Log", preprocess=True)

    def set_log_level_to_debug(self, change=True):
        # assume the initial log level is INFO.
        # Future support for multiple log levels.
        if change:
            if app_logger.level == logging.DEBUG:
                app_logger.setLevel(level=logging.INFO)
                self.is_log_level_debug = False
            else:
                app_logger.setLevel(level=logging.DEBUG)
                self.is_log_level_debug = True
        self.buttons["Debug Level Log"].change_toggle(self.is_log_level_debug)


class DebugLogViewerWidget(MenuWidget):
    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QVBoxLayout)

        # self.scroll_area = QtWidgets.QScrollArea()
        # self.scroll_area.setWidgetResizable(True)
        self.debug_log_screen = QtWidgets.QTextEdit()
        self.debug_log_screen.setReadOnly(True)
        self.debug_log_screen.setLineWrapMode(QT_TEXTEDIT_NOWRAP)
        self.debug_log_screen.setHorizontalScrollBarPolicy(QT_SCROLLBAR_ALWAYSOFF)
        # self.debug_log_screen.setVerticalScrollBarPolicy(QT_SCROLLBAR_ALWAYSOFF)
        # QtWidgets.QScroller.grabGesture(self, QtWidgets.QScroller.LeftMouseButtonGesture)
        # self.scroll_area.setWidget(self.debug_log_screen) if USE_PYQT6 else self.menu_layout.addWidget(self.debug_log_screen)
        # self.menu_layout.addWidget(self.scroll_area)
        self.menu_layout.addWidget(self.debug_log_screen)

    def preprocess(self):
        try:
            with open(self.config.G_LOG_DEBUG_FILE) as f:
                self.debug_log_screen.setText(f.read())
        except FileNotFoundError:
            self.debug_log_screen.setText("No logs found")
