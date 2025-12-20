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
        self.buttons = {}

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
        self.right_button_container = QtWidgets.QWidget()
        self.right_button_container.setFixedSize(self.icon_x, self.icon_y)
        self.right_button_layout = QtWidgets.QHBoxLayout(
            self.right_button_container
        )
        self.right_button_layout.setContentsMargins(0, 0, 0, 0)
        self.right_button_layout.setSpacing(0)

        self.top_bar_layout = QtWidgets.QHBoxLayout()
        self.top_bar_layout.setContentsMargins(5, 5, 5, 5)
        self.top_bar_layout.setSpacing(0)
        self.top_bar_layout.addWidget(self.back_button)
        self.top_bar_layout.addWidget(self.page_name_label)
        self.top_bar_layout.addWidget(self.right_button_container)
        self.top_bar_layout.setStretch(1, 1)

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

    def add_buttons(self, buttons):
        n = len(buttons)
        vertical = True
        if self.parent().size().height() < self.parent().size().width():
            vertical = False

        if n <= 4 or vertical:
            layout_type = QtWidgets.QVBoxLayout
        else:
            layout_type = QtWidgets.QGridLayout
        self.make_menu_layout(layout_type)
        
        i = 0
        for b in buttons:
            icon = None
            name, button_type, func, *rest = b
            if rest:
                icon = rest[0]

            if vertical and name == "":
                continue
            self.buttons[name] = MenuButton(button_type, name, self.config, icon=icon)

            if func is not None:
                self.buttons[name].clicked.connect(func)
            else:
                self.buttons[name].setEnabled(False)
                self.buttons[name].setProperty("style", "unavailable")

            if layout_type == QtWidgets.QVBoxLayout:
                self.menu_layout.addWidget(self.buttons[name])
            else:
                self.menu_layout.addWidget(self.buttons[name], i % 4, i // 4)
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
            # Name(page_name), button_attribute, connected functions, layout
            ("Sensors", "submenu", self.sensors_menu),
            ("Courses", "submenu", self.courses_menu),
            ("Connectivity", "submenu", self.connectivity_menu),
            ("Upload Activity", "submenu", self.cloud_services_menu),
            ("Map and Data", "submenu", self.map_menu),
            ("Profile", "submenu", self.profile_menu),
            ("System", "submenu", self.setting_menu),
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
    use_detail = False

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
        self.update_list()

    def update_list(self):
        if type(self.settings) == dict:
            self.add_list_items_internal(self.settings)

    def add_list(self, add_list):
        new_items = {k: add_list[k] for k in add_list if k not in self.settings}
        self.settings.update(new_items)
        self.add_list_items_internal(new_items)

    def add_list_items_internal(self, items):
        for k, v in items.items():
            detail = v if self.use_detail else None
            item = ListItemWidget(self, k, detail)
            item.enter_signal.connect(self.button_func)
            self.add_list_item(item)

    def add_list_item(self, item):
        list_item = QtWidgets.QListWidgetItem(self.list)
        if self.size_hint:
            list_item.setSizeHint(self.size_hint)
        self.list.setItemWidget(list_item, item)

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
            list_item = self.list.item(default_index)
            widget = self.list.itemWidget(list_item)
            if widget is not None:
                self.list.setCurrentRow(default_index)
                widget.setFocus()

    def get_default_value(self):
        return None


class ListItemWidget(QtWidgets.QWidget):
    title = None
    detail = None

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
            # Name(page_name), button_attribute, connected functions, icon
            (
                "Strava",
                "cloud_upload",
                self.strava_upload,
                (icons.StravaIcon(), (icons.BASE_LOGO_SIZE * 4, icons.BASE_LOGO_SIZE)),
            ),
            (
                "Garmin",
                "cloud_upload",
                self.garmin_upload,
                (icons.GarminIcon(), (icons.BASE_LOGO_SIZE * 5, icons.BASE_LOGO_SIZE)),
            ),
            (
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
        await self.buttons["Strava"].run(self.config.api.strava_upload)

    @qasync.asyncSlot()
    async def garmin_upload(self):
        await self.buttons["Garmin"].run(self.config.api.garmin_upload)

    @qasync.asyncSlot()
    async def rwgps_upload(self):
        await self.buttons["Ride with GPS"].run(self.config.api.rwgps_upload)


class ConnectivityMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Auto BT Tethering","toggle",lambda: self.bt_auto_tethering(True)),
            ("Select BT device", "submenu", self.select_bt_device),
            ("Live Track", "toggle", lambda: self.onoff_live_track(True)),
            ("", None, None),
            ("Gadgetbridge", "toggle", self.onoff_ble_uart_service),
            ("Get Location", "toggle", self.onoff_gadgetbridge_gps),
        )
        self.add_buttons(button_conf)

        # Auto BT Tethering
        if not self.config.G_IS_RASPI:
            self.buttons["Auto BT Tethering"].disable()
            self.buttons["Select BT device"].disable()

        # ThingsBoard
        if (
            not self.config.api.thingsboard_check()
            or not self.config.G_THINGSBOARD_API["HAVE_API_TOKEN"]
        ):
            self.buttons["Live Track"].disable()
        
        #GadgetBridge
        if self.config.ble_uart is None:
            self.buttons["Gadgetbridge"].disable()
            self.buttons["Get Location"].disable()

        # initialize toggle button status
        self.onoff_live_track(change=False)
        self.bt_auto_tethering(change=False)

    def preprocess(self):
        if self.config.ble_uart:
            status = self.config.ble_uart.status
            self.buttons["Gadgetbridge"].change_toggle(status)
            self.buttons["Get Location"].change_toggle(self.config.ble_uart.gps_status)
            self.buttons["Get Location"].onoff_button(status)

    def onoff_live_track(self, change=True):
        if change:
            self.config.G_THINGSBOARD_API["STATUS"] = not self.config.G_THINGSBOARD_API["STATUS"]
        self.buttons["Live Track"].change_toggle(
            self.config.G_THINGSBOARD_API["STATUS"]
        )

    def bt_auto_tethering(self, change=True):
        if change:
            self.config.G_AUTO_BT_TETHERING = not self.config.G_AUTO_BT_TETHERING
        self.buttons["Auto BT Tethering"].change_toggle(self.config.G_AUTO_BT_TETHERING)
        self.buttons["Select BT device"].onoff_button(self.config.G_AUTO_BT_TETHERING)

    def select_bt_device(self):
        self.change_page("BT Tethering", preprocess=True, run_bt_tethering=False)
    
    @qasync.asyncSlot()
    async def onoff_ble_uart_service(self):
        status = await self.config.ble_uart.on_off_uart_service()
        self.config.G_GADGETBRIDGE["STATUS"] = status
        self.buttons["Gadgetbridge"].change_toggle(status)
        self.buttons["Get Location"].onoff_button(status)

    def onoff_gadgetbridge_gps(self):
        status = self.config.ble_uart.on_off_gadgetbridge_gps()
        self.config.G_GADGETBRIDGE["USE_GPS"] = status
        self.buttons["Get Location"].change_toggle(status)
