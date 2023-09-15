import os
import asyncio
import datetime
import re
import json

try:
    import PyQt6.QtCore as QtCore
    import PyQt6.QtWidgets as QtWidgets
    import PyQt6.QtGui as QtGui
except:
    import PyQt5.QtCore as QtCore
    import PyQt5.QtWidgets as QtWidgets
    import PyQt5.QtGui as QtGui

from qasync import asyncSlot

from .pyqt_menu_widget import MenuWidget, ListWidget


class SystemMenuWidget(MenuWidget):
    def setup_menu(self):
        self.button = {}

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
                lambda: self.config.gui.show_dialog(self.config.poweroff, "Power Off"),
            ),
        )
        self.add_buttons(button_conf)

    def network(self):
        self.change_page("Network", preprocess=True)

    def debug(self):
        self.change_page("Debug", preprocess=True)


class NetworkMenuWidget(MenuWidget):
    ble_msg_status = False

    def setup_menu(self):
        self.button = {}
        wifi_bt_button_func_wifi = None
        wifi_bt_button_func_bt = None
        if self.config.G_IS_RASPI:
            wifi_bt_button_func_wifi = lambda: self.onoff_wifi_bt(True, "Wifi")
            wifi_bt_button_func_bt = lambda: self.onoff_wifi_bt(True, "Bluetooth")
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Wifi", "toggle", wifi_bt_button_func_wifi),
            ("Bluetooth", "toggle", wifi_bt_button_func_bt),
            ("BT Tethering", "submenu", self.bt_tething),
            ("IP Address", "dialog", self.show_ip_address),
            ("Gadgetbridge", "toggle", lambda: self.onoff_ble_uart_service(True)),
            ("Get Location", "toggle", lambda: self.onoff_gadgetbridge_gps(True)),
        )
        self.add_buttons(button_conf)

        # set back_index of child widget
        self.bt_page_name = "BT Tethering"
        self.bt_index = self.config.gui.gui_config.G_GUI_INDEX[self.bt_page_name]

        if self.config.bt_pan == None or len(self.config.G_BT_ADDRESS) == 0:
            self.button["BT Tethering"].disable()

        if self.config.ble_uart == None:
            self.button["Gadgetbridge"].disable()

        self.button["Get Location"].disable()

    def preprocess(self):
        # initialize toggle button status
        if self.config.G_IS_RASPI:
            self.onoff_wifi_bt(change=False, key="Wifi")
            self.onoff_wifi_bt(change=False, key="Bluetooth")
        self.onoff_ble_uart_service(change=False)
        self.onoff_gadgetbridge_gps(change=False)
        self.parentWidget().widget(self.bt_index).back_index_key = self.page_name

    def onoff_wifi_bt(self, change=True, key=None):
        if change:
            self.config.onoff_wifi_bt(key)
        status = {}
        status["Wifi"], status["Bluetooth"] = self.config.get_wifi_bt_status()
        self.button[key].change_toggle(status[key])

    def bt_tething(self):
        self.change_page("BT Tethering", preprocess=True)

    def show_ip_address(self):
        self.config.detect_network()
        # Button is OK only
        self.config.gui.show_dialog_ok_only(None, self.config.G_IP_ADDRESS)

    @asyncSlot()
    async def onoff_ble_uart_service(self, change=True):
        if change:
            await self.config.ble_uart.on_off_uart_service()
            self.button["Gadgetbridge"].change_toggle(self.config.ble_uart.status)
            self.button["Get Location"].onoff_button(self.config.ble_uart.status)

    def onoff_gadgetbridge_gps(self, change=True):
        if change:
            self.config.ble_uart.on_off_gadgetbridge_gps()
            self.button["Get Location"].change_toggle(self.config.ble_uart.gps_status)


class DebugMenuWidget(MenuWidget):
    def setup_menu(self):
        self.button = {}
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Debug Log", "submenu", self.debug_log),
            (
                "Disable Wifi/BT",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.config.hardware_wifi_bt_off, "Disable Wifi/BT\n(need reboot)"
                ),
            ),
            (
                "Enable Wifi/BT",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.config.hardware_wifi_bt_on, "Enable Wifi/BT\n(need reboot)"
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
        pass

    def debug_log(self):
        self.change_page("Debug Log", preprocess=True)


class BluetoothTetheringListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_BT_ADDRESS
        super().__init__(parent=parent, page_name=page_name, config=config)

    def preprocess(self, run_bt_tethering=True):
        self.run_bt_tethering = run_bt_tethering

    def get_default_value(self):
        return self.config.G_BT_USE_ADDRESS

    async def button_func_extra(self):
        self.config.G_BT_USE_ADDRESS = self.selected_item.title_label.text()
        self.config.setting.set_config_pickle(
            "G_BT_USE_ADDRESS", self.config.G_BT_USE_ADDRESS
        )

        if self.run_bt_tethering:
            await self.config.bluetooth_tethering()


class DebugLogViewerWidget(MenuWidget):
    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QVBoxLayout)

        # self.scroll_area = QtWidgets.QScrollArea()
        # self.scroll_area.setWidgetResizable(True)
        try:
            self.debug_log_screen = QtWidgets.QTextEdit()
        except:
            # for old Qt (5.11.3 buster PyQt5 Package)
            QtGui.QTextEdit()
        self.debug_log_screen.setReadOnly(True)
        self.debug_log_screen.setLineWrapMode(
            self.config.gui.gui_config.qtextedit_nowrap
        )
        self.debug_log_screen.setHorizontalScrollBarPolicy(
            self.config.gui.gui_config.scrollbar_alwaysoff
        )
        # self.debug_log_screen.setVerticalScrollBarPolicy(self.config.gui.gui_config.scrollbar_alwaysoff)
        # QtWidgets.QScroller.grabGesture(self, QtWidgets.QScroller.LeftMouseButtonGesture)
        # self.scroll_area.setWidget(self.debug_log_screen) if USE_PYQT6 else self.menu_layout.addWidget(self.debug_log_screen)
        # self.menu_layout.addWidget(self.scroll_area)
        self.menu_layout.addWidget(self.debug_log_screen)

        self.menu.setLayout(self.menu_layout)

    def preprocess(self):
        debug_log = "log/debug.txt"
        if not os.path.exists(debug_log):
            return
        f = open(debug_log)
        self.debug_log_screen.setText(f.read())
        f.close()
