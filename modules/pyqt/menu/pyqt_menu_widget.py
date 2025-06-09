from modules._qt_qtwidgets import (
    QT_ALIGN_LEFT,
    QT_KEY_SPACE,
    QT_NO_FOCUS,
    QT_SCROLLBAR_ALWAYSOFF,
    QT_STRONG_FOCUS,
    QtCore,
    QtWidgets,
    qasync,
    Signal,
)
from modules.pyqt.components import icons, topbar
from modules.button_registry import ButtonRegistry

from .pyqt_menu_button import MenuButton

#################################
# Menu
#################################


class MenuWidget(QtWidgets.QWidget):
    config = None

    icon_x = 40
    icon_y = 32

    @property
    def sensor_i2c(self):
        return self.config.logger.sensor.sensor_i2c
    
    @property
    def sensor_ant(self):
        return self.config.logger.sensor.sensor_ant

    def __init__(self, parent, page_name, config):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.config = config
        self.page_name = page_name
        self.back_index_key = None
        self.focus_widget = None
        self.menu_layout = None
        self.buttons = ButtonRegistry()

        self.setup_ui()

    def setup_ui(self):
        self.setContentsMargins(0, 0, 0, 0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # top bar
        self.top_bar = topbar.TopBar()

        self.back_button = topbar.TopBarBackButton((self.icon_x, self.icon_y))
        self.page_name_label = topbar.TopBarLabel(self.page_name)

        self.top_bar_layout = QtWidgets.QHBoxLayout()
        self.top_bar_layout.setContentsMargins(5, 5, 5, 5)
        self.top_bar_layout.setSpacing(0)
        self.top_bar_layout.addWidget(self.back_button)
        self.top_bar_layout.addWidget(self.page_name_label)

        self.top_bar.setLayout(self.top_bar_layout)

        self.menu = QtWidgets.QWidget()
        self.setup_menu()

        layout.addWidget(self.top_bar)
        layout.addWidget(self.menu)

        # connect back button
        self.back_button.clicked.connect(self.back)
        self.connect_buttons()

    def make_menu_layout(self, qt_layout):
        self.menu_layout = qt_layout(self.menu)
        self.menu_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_layout.setSpacing(0)

    def filter_buttons(self, buttons, wrap_menus):
        """
        Filter buttons based on the current configuration in the menus.yaml. If a button's key
        does not exist in the configuration it will be included by default.

        It is expected that the button's key is found in the menu_config.py and has
        a value corresponding to the location of the configuration in the menus.yaml
        file.
        """
        filtered_buttons_list = []
        for button in buttons:
            menu_config_key, name, *rest = button
            # Skip empty buttons if wrap_menus is enabled
            if wrap_menus and "EMPTY" in menu_config_key:
                continue
            # Check if the menu item is enabled in the config
            if self.config.gui.menu_config.get_status(menu_config_key):
                filtered_buttons_list.append(button)
        return filtered_buttons_list

    def add_buttons(self, buttons):
        wrap_menus = self.config.gui.menu_config.wrap_menus()
        filtered_buttons = self.filter_buttons(buttons, wrap_menus)
        n = len(filtered_buttons)
        vertical = True
        if self.parent().size().height() < self.parent().size().width():
            vertical = False

        if n <= 4 or vertical:
            layout_type = QtWidgets.QVBoxLayout
        else:
            layout_type = QtWidgets.QGridLayout
        self.make_menu_layout(layout_type)

        i = 0
        for b in filtered_buttons:
            icon = None
            menu_config_key, name, button_type, func, *rest = b
            if rest:
                icon = rest[0]

            if vertical and name == "":
                continue
            self.buttons[menu_config_key] = MenuButton(button_type, name, self.config, icon=icon)

            if func is not None:
                self.buttons[menu_config_key].clicked.connect(func)
            else:
                self.buttons[menu_config_key].setEnabled(False)
                self.buttons[menu_config_key].setProperty("style", "unavailable")

            if layout_type == QtWidgets.QVBoxLayout:
                self.menu_layout.addWidget(self.buttons[menu_config_key])
            elif wrap_menus == True: # QtWidgets.QVBoxLayout
                # wrap menus in a 2xN grid layout. Adds buttons left to right, top to bottom.
                columns = 2
                row = i // columns
                col = i % columns
                self.menu_layout.addWidget(self.buttons[menu_config_key], row, col)
                i += 1
            else: # QtWidgets.QVBoxLayout
                self.menu_layout.addWidget(self.buttons[menu_config_key], i % 4, i // 4)
                i += 1


        # add dummy buttons to fit 4x2 (horizontal) or 8x1 (vertical) layouts.
        if not vertical and n in (1, 2, 3):
            for j in range(4 - n):
                self.menu_layout.addWidget(MenuButton("dummy", "", self.config))
        elif vertical:
            for j in range(self.menu_layout.count(), 8):
                self.menu_layout.addWidget(MenuButton("dummy", "", self.config))

        # set first focus
        if not self.config.display.has_touch:
            self.focus_widget = self.buttons[buttons[0][0]]

    def setup_menu(self):
        pass

    def resizeEvent(self, event):
        h = self.size().height()
        w = self.size().width()
        rows = 5
        short_side_length = h
        if h > w:
            rows = 9
            short_side_length = w
        self.top_bar.setFixedHeight(int(h / rows))

        q = self.page_name_label.font()
        q.setPixelSize(int(short_side_length / 12))
        self.page_name_label.setFont(q)

    def connect_buttons(self):
        pass

    def back(self):
        index = self.config.gui.gui_config.G_GUI_INDEX.get(self.back_index_key, 0)
        self.on_back_menu()
        self.config.gui.change_menu_page(index, focus_reset=False)

    def on_back_menu(self):
        pass

    def change_page(self, page, preprocess=False, **kwargs):
        # always set back index
        index = self.config.gui.gui_config.G_GUI_INDEX[page]
        widget = self.parentWidget().widget(index)
        widget.back_index_key = self.page_name

        if preprocess:
            widget.preprocess(**kwargs)
        self.config.gui.change_menu_page(index)
        return widget


class TopMenuWidget(MenuWidget):

    def __init__(self, parent, page_name, config):
        super().__init__(parent, page_name, config)
        self.back_index_key = "Main"

    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("SENSORS", "Sensors", "submenu", self.sensors_menu),
            ("COURSES", "Courses", "submenu", self.courses_menu),
            ("CONNECTIVITY", "Connectivity", "submenu", self.connectivity_menu),
            ("UPLOAD_ACTIVITY", "Upload Activity", "submenu", self.cloud_services_menu),
            ("MAP_AND_DATA", "Map and Data", "submenu", self.map_menu),
            ("PROFILE", "Profile", "submenu", self.profile_menu),
            ("SYSTEM", "System", "submenu", self.setting_menu)
        )
        self.add_buttons(button_conf)

    def sensors_menu(self):
        self.change_page("Sensors", preprocess=True)

    def courses_menu(self):
        self.change_page("Courses", preprocess=True)

    def connectivity_menu(self):
        self.change_page("Connectivity", preprocess=True)

    def cloud_services_menu(self):
        self.change_page("Upload Activity")

    def map_menu(self):
        self.change_page("Map and Data")

    def profile_menu(self):
        self.change_page("Profile")

    def setting_menu(self):
        self.change_page("System")


class ListWidget(MenuWidget):
    STYLES = """
      background-color: transparent;
    """

    list_type = None
    selected_item = None
    size_hint = None

    # for simple list
    settings = None

    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QVBoxLayout)

        self.list = QtWidgets.QListWidget()
        self.list.setHorizontalScrollBarPolicy(QT_SCROLLBAR_ALWAYSOFF)
        self.list.setVerticalScrollBarPolicy(QT_SCROLLBAR_ALWAYSOFF)
        self.list.setFocusPolicy(QT_NO_FOCUS)
        self.list.setStyleSheet(self.STYLES)

        self.menu_layout.addWidget(self.list)

        if self.settings and self.settings.keys():
            for k in self.settings.keys():
                item = ListItemWidget(self, k)
                item.enter_signal.connect(self.button_func)
                self.add_list_item(item)

    # override for custom list
    def connect_buttons(self):
        self.list.itemSelectionChanged.connect(self.changed_item)
        self.list.itemClicked.connect(self.button_func)

    @qasync.asyncSlot()
    async def button_func(self):
        await self.button_func_extra()
        self.back()

    async def button_func_extra(self):
        pass

    def changed_item(self):
        # item is QListWidgetItem
        item = self.list.selectedItems()
        if len(item):
            self.selected_item = self.list.itemWidget(item[0])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rows = 4
        if self.size().height() > self.size().width():
            rows = 8
        h = int((self.height() - self.top_bar.height()) / rows)
        self.size_hint = QtCore.QSize(self.top_bar.width(), h)
        for i in range(self.list.count()):
            self.list.item(i).setSizeHint(self.size_hint)

    def preprocess(self, **kwargs):
        self.list_type = kwargs.get("list_type")
        reset = kwargs.get("reset", False)
        if reset:
            self.selected_item = None
            self.list.clear()
            self.list.verticalScrollBar().setValue(0)
        self.preprocess_extra()

    # override for custom list
    def preprocess_extra(self):
        # set default item in the list
        default_value = self.get_default_value()
        default_index = None

        for i, k in enumerate(self.settings):
            if k == default_value:
                default_index = i
                break
        if default_index is not None:
            self.list.setCurrentRow(default_index)
            self.list.itemWidget(self.list.currentItem()).setFocus()

    def get_default_value(self):
        return None

    def add_list_item(self, item):
        list_item = QtWidgets.QListWidgetItem(self.list)
        if self.size_hint:
            list_item.setSizeHint(self.size_hint)
        self.list.setItemWidget(list_item, item)


class ListItemWidget(QtWidgets.QWidget):
    enter_signal = Signal()

    def get_styles(self):
        border_style = "border-bottom: 1px solid #AAAAAA;"
        title_style = "padding-left: 10%; padding-top: 2%;"
        detail_style = None

        if self.detail:
            detail_style = f"padding-left: 20%; padding-bottom: 2%; {border_style}"
        else:
            title_style = f"{title_style} {border_style}"
        return title_style, detail_style

    def __init__(self, parent, title, detail=None):
        self.title = title
        self.detail = detail
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.setup_ui()

    def setup_ui(self):
        self.setContentsMargins(0, 0, 0, 0)
        self.setFocusPolicy(QT_STRONG_FOCUS)

        inner_layout = QtWidgets.QVBoxLayout()
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)

        title_style, detail_style = self.get_styles()

        self.title_label = QtWidgets.QLabel()
        self.title_label.setMargin(0)
        self.title_label.setContentsMargins(0, 0, 0, 0)
        self.title_label.setStyleSheet(title_style)
        self.title_label.setText(self.title)
        inner_layout.addWidget(self.title_label)

        if self.detail:
            self.detail_label = QtWidgets.QLabel()
            self.detail_label.setMargin(0)
            self.detail_label.setContentsMargins(0, 0, 0, 0)
            self.detail_label.setStyleSheet(detail_style)
            self.detail_label.setText(self.detail)
            inner_layout.addWidget(self.detail_label)

        self.outer_layout = QtWidgets.QHBoxLayout(self)
        self.outer_layout.setSpacing(0)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)

        self.outer_layout.addLayout(inner_layout, QT_ALIGN_LEFT)

    def keyPressEvent(self, e):
        if e.key() == QT_KEY_SPACE:
            self.enter_signal.emit()

    @staticmethod
    def resize_label(label, font_size):
        q = label.font()
        q.setPixelSize(font_size)
        label.setFont(q)

    def resizeEvent(self, event):
        short_side_length = min(self.size().height(), self.size().width())
        self.resize_label(self.title_label, int(short_side_length * 0.45))
        if self.detail:
            self.resize_label(self.detail_label, int(short_side_length * 0.4))


class UploadActivityMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, icon
            (
                "STRAVA_UPLOAD",
                "Strava",
                "cloud_upload",
                self.strava_upload,
                (icons.StravaIcon(), (icons.BASE_LOGO_SIZE * 4, icons.BASE_LOGO_SIZE)),
            ),
            (
                "GARMIN_CONNECT_UPLOAD",
                "Garmin",
                "cloud_upload",
                self.garmin_upload,
                (icons.GarminIcon(), (icons.BASE_LOGO_SIZE * 5, icons.BASE_LOGO_SIZE)),
            ),
            (
                "RIDE_WITH_GPS_UPLOAD",
                "Ride with GPS",
                "cloud_upload",
                self.rwgps_upload,
                (
                    icons.RideWithGPSIcon(),
                    (icons.BASE_LOGO_SIZE * 4, icons.BASE_LOGO_SIZE),
                ),
            ),
        )
        self.add_buttons(button_conf)

    @qasync.asyncSlot()
    async def strava_upload(self):
        await self.buttons.run_if_exists("STRAVA_UPLOAD", self.config.api.strava_upload)

    @qasync.asyncSlot()
    async def garmin_upload(self):
        await self.buttons.run_if_exists("GARMIN_CONNECT_UPLOAD", self.config.api.garmin_upload)

    @qasync.asyncSlot()
    async def rwgps_upload(self):
        await self.buttons.run_if_exists("RIDE_WITH_GPS_UPLOAD", self.config.api.rwgps_upload)


class ConnectivityMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("AUTO_BT_TETHERING", "Auto BT Tethering","toggle",lambda: self.bt_auto_tethering(True)),
            ("SELECT_BT_DEVICE", "Select BT device", "submenu", self.bt_tething),
            ("LIVE_TRACKING", "Live Track", "toggle", lambda: self.onoff_live_track(True)),
            ("CONNECTIVITY_EMPTY", "", None, None),
            ("GADGET_BRIDGE", "Gadgetbridge", "toggle", self.onoff_ble_uart_service),
            ("GET_LOCATION", "Get Location", "toggle", self.onoff_gadgetbridge_gps),
        )
        self.add_buttons(button_conf)

        # Auto BT Tethering
        if not self.config.G_IS_RASPI:
            self.buttons.disable_if_exists("AUTO_BT_TETHERING")
            self.buttons.disable_if_exists("SELECT_BT_DEVICE")

        # ThingsBoard
        if (
            not self.config.api.thingsboard_check()
            or not self.config.G_THINGSBOARD_API["HAVE_API_TOKEN"]
        ):
            self.buttons.disable_if_exists("LIVE_TRACKING")
        
        #GadgetBridge
        if self.config.ble_uart is None:
            self.buttons.disable_if_exists("GADGET_BRIDGE")
            self.buttons.disable_if_exists("GET_LOCATION")

        # initialize toggle button status
        self.onoff_live_track(change=False)
        self.bt_auto_tethering(change=False)

    def preprocess(self):
        if self.config.ble_uart:
            status = self.config.ble_uart.status
            self.buttons.change_toggle_if_exists("GADGET_BRIDGE", status)
            self.buttons.change_toggle_if_exists("GET_LOCATION", self.config.ble_uart.gps_status)
            self.buttons.onoff_button_if_exists("GET_LOCATION", status)

    def onoff_live_track(self, change=True):
        if change:
            self.config.G_THINGSBOARD_API["STATUS"] = not self.config.G_THINGSBOARD_API["STATUS"]
        self.buttons.change_toggle_if_exists("LIVE_TRACKING",
            self.config.G_THINGSBOARD_API["STATUS"]
        )

    def bt_auto_tethering(self, change=True):
        if change:
            self.config.G_AUTO_BT_TETHERING = not self.config.G_AUTO_BT_TETHERING
            self.config.network.reset_bt_error_counts()
        self.buttons.change_toggle_if_exists("AUTO_BT_TETHERING", self.config.G_AUTO_BT_TETHERING)
        self.buttons.onoff_button_if_exists("SELECT_BT_DEVICE", self.config.G_AUTO_BT_TETHERING)

    def bt_tething(self):
        self.change_page("BT Tethering", preprocess=True, run_bt_tethering=False)
    
    @qasync.asyncSlot()
    async def onoff_ble_uart_service(self):
        status = await self.config.ble_uart.on_off_uart_service()
        self.config.G_GADGETBRIDGE["STATUS"] = status
        self.buttons.change_toggle_if_exists("GADGET_BRIDGE", status)
        self.buttons.change_toggle_if_exists("GET_LOCATION", status)

    def onoff_gadgetbridge_gps(self):
        status = self.config.ble_uart.on_off_gadgetbridge_gps()
        self.config.G_GADGETBRIDGE["USE_GPS"] = status
        self.buttons.change_toggle_if_exists("GET_LOCATION", status)
