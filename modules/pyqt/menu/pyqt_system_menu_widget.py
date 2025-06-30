import logging
from functools import partial

from modules.app_logger import app_logger
from modules._qt_qtwidgets import (
    QT_TEXTEDIT_NOWRAP,
    QT_SCROLLBAR_ALWAYSOFF,
    QtWidgets,
)
from modules.utils.network import detect_network
from .pyqt_menu_widget import MenuWidget, ListWidget


class SystemMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("NETWORK", "Network", "submenu", self.network),
            ("BRIGHTNESS", "Brightness", None, None),
            ("LANGUAGE", "Language", None, None),
            (   "UPDATE",
                "Update",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.config.update_application, "Update"
                ),
            ),
            ("DEBUG", "Debug", "submenu", self.debug),
            (   "POWER_OFF",
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
            wifi_bt_button_func_wifi = lambda: self.onoff_wifi_bt(True, "WIFI_NETWORK")
            wifi_bt_button_func_bt = lambda: self.onoff_wifi_bt(True, "BLUETOOTH_NETWORK")

        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("WIFI_NETWORK", "Wifi", "toggle", wifi_bt_button_func_wifi),
            ("BLUETOOTH_NETWORK", "Bluetooth", "toggle", wifi_bt_button_func_bt),
            ("BT_TETHERING_NETWORK", "BT Tethering", "submenu", self.bt_tething),
            ("IP_ADDRESS_NETWORK", "IP Address", "dialog", self.show_ip_address),
        )
        self.add_buttons(button_conf)

        if (
            not self.config.G_BT_ADDRESSES
        ):  # if bt_pan is None there won't be any addresses
            self.buttons.disable_if_exists("BT_TETHERING_NETWORK")

    def preprocess(self):
        # initialize toggle button status
        if self.config.G_IS_RASPI:
            self.onoff_wifi_bt(change=False, key="WIFI_NETWORK")
            self.onoff_wifi_bt(change=False, key="BLUETOOTH_NETWORK")

    def onoff_wifi_bt(self, change=True, key=None):
        if change:
            self.config.network.onoff_wifi_bt(key)
        status = {}
        status["Wifi"], status["Bluetooth"] = self.config.network.get_wifi_bt_status()
        self.buttons.change_toggle_if_exists(key, status[key])

    def bt_tething(self):
        self.change_page("BT Tethering", preprocess=True)

    def show_ip_address(self):
        address = detect_network() or "No address"
        # Button is OK only
        self.config.gui.show_dialog_ok_only(None, address)


class DebugMenuWidget(MenuWidget):
    is_log_level_debug = False

    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("DEBUG_LOG", "Debug Log", "submenu", self.debug_log),
            ("DEBUG_LOG_LEVEL", "Debug Logging", "toggle", lambda: self.set_log_level_to_debug(True)),
            (   "DISABLE_ENABLE_WIFI_BT",
                "Disable Wifi/BT",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    partial(self.config.network.hardware_wifi_bt, False),
                    "Disable Wifi/BT\n(need reboot)",
                ),
            ),
            (   "DISABLE_ENABLE_WIFI_BT",
                "Enable Wifi/BT",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    partial(self.config.network.hardware_wifi_bt, True),
                    "Enable Wifi/BT\n(need reboot)",
                ),
            ),
            (   "RESTART",
                "Restart",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.config.restart_application, "Restart Application"
                ),
            ),
            (   "REBOOT",
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
        self.buttons.change_toggle_if_exists("DEBUG_LOG_LEVEL", self.is_log_level_debug)


class BluetoothTetheringListWidget(ListWidget):
    run_bt_tethering = False

    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_BT_ADDRESSES
        super().__init__(parent=parent, page_name=page_name, config=config)

    def preprocess(self, run_bt_tethering=True):
        super().preprocess()
        self.run_bt_tethering = run_bt_tethering

    def get_default_value(self):
        return self.config.G_BT_PAN_DEVICE

    async def button_func_extra(self):
        self.config.G_BT_PAN_DEVICE = self.selected_item.title_label.text()
        if self.run_bt_tethering:
            await self.config.network.bluetooth_tethering()


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
