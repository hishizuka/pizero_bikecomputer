from modules._qt_qtwidgets import (
    QT_ALIGN_LEFT,
    QT_KEY_SPACE,
    QT_NO_FOCUS,
    QT_SCROLLBAR_ALWAYSOFF,
    QT_STRONG_FOCUS,
    QtCore,
    QtGui,
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

    @property
    def sensor_ble(self):
        return self.config.logger.sensor.sensor_ble

    @property
    def sensor_gps(self):
        return self.config.logger.sensor.sensor_gps

    def __init__(self, parent, page_name, config):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.config = config
        self.page_name = page_name
        self.back_index_key = None
        self.focus_widget = None
        self.menu_layout = None
        self.use_half_split_grid = False
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
        self.right_button_layout = QtWidgets.QHBoxLayout(self.right_button_container)
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

    def apply_half_split_grid(self):
        if not self.use_half_split_grid:
            return
        if not isinstance(self.menu_layout, QtWidgets.QGridLayout):
            return

        left_width = self.menu.width() // 2
        right_width = self.menu.width() - left_width

        self.menu_layout.setColumnStretch(0, 0)
        self.menu_layout.setColumnStretch(1, 0)
        self.menu_layout.setColumnMinimumWidth(0, left_width)
        self.menu_layout.setColumnMinimumWidth(1, right_width)

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
        self.use_half_split_grid = layout_type == QtWidgets.QGridLayout
        self.apply_half_split_grid()

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

        # Set the initial focus for keyboard-driven navigation.
        if self.config.uses_keyboard_navigation:
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

        self.apply_half_split_grid()

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
        button_conf = [
            # Name(page_name), button_attribute, connected functions, layout
            ("Sensors", "submenu", self.sensors_menu),
            ("Courses", "submenu", self.courses_menu),
            ("Ride Info", "submenu", self.ride_info_menu),
            ("Connectivity", "submenu", self.connectivity_menu),
            ("Upload Activity", "submenu", self.cloud_services_menu),
            ("Map and Data", "submenu", self.map_menu),
            ("Profile", "submenu", self.profile_menu),
            ("System", "submenu", self.setting_menu),
        ]
        self.add_buttons(button_conf)

    def sensors_menu(self):
        self.change_page("Sensors", preprocess=True)

    def courses_menu(self):
        self.change_page("Courses", preprocess=True)

    def connectivity_menu(self):
        self.change_page("Connectivity", preprocess=True)

    def cloud_services_menu(self):
        self.change_page("Upload Activity", preprocess=True)

    def map_menu(self):
        self.change_page("Map and Data")

    def profile_menu(self):
        self.change_page("Profile")

    def ride_info_menu(self):
        self.change_page("Ride Info")

    def setting_menu(self):
        self.change_page("System", preprocess=True)


class RideInfoMenuWidget(MenuWidget):
    def setup_menu(self):
        if getattr(self.sensor_gps, "supports_qzss_dcr", False):
            button_conf = (("QZSS DC Report", "submenu", self.qzss_dcr_report),)
        else:
            button_conf = (("No information available", "dummy", None),)
        self.add_buttons(button_conf)

    def qzss_dcr_report(self):
        self.change_page("QZSS DC Report", preprocess=True)


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
        self.list.itemClicked.connect(self.clicked_item)

    def clicked_item(self, list_item):
        widget = self.list.itemWidget(list_item)
        enter_signal = getattr(widget, "enter_signal", None)
        if widget is None or not widget.isEnabled() or enter_signal is None:
            selected_item = self.selected_item
            self.list.clearSelection()
            if selected_item is not None:
                selected_item.clearFocus()
            self.selected_item = None
            return
        self.selected_item = widget
        enter_signal.emit()

    @qasync.asyncSlot()
    async def button_func(self):
        await self.button_func_extra()
        self.back()

    async def button_func_extra(self):
        pass

    def changed_item(self):
        # item is QListWidgetItem
        item = self.list.selectedItems()
        for i in range(self.list.count()):
            list_item = self.list.item(i)
            widget = self.list.itemWidget(list_item)
            if widget is not None:
                widget.set_selected(list_item.isSelected())
        self.selected_item = self.list.itemWidget(item[0]) if item else None

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

    @property
    def has_detail_row(self):
        return bool(self.detail or self.detail_icon)

    def get_title_style(self):
        title_style = "padding-left: 10%; padding-top: 2%;"
        return (
            title_style
            if self.has_detail_row
            else f"{title_style} border-bottom: 1px solid #AAAAAA;"
        )

    def __init__(
        self,
        parent,
        title,
        detail=None,
        detail_icon=None,
        detail_left=None,
    ):
        self.title = title
        self.detail = detail
        self.detail_icon = detail_icon
        self.detail_left = detail_left
        self.selected = False
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.setup_ui()

    def setup_ui(self):
        self.setContentsMargins(0, 0, 0, 0)
        focus_policy = (
            QT_STRONG_FOCUS
            if self.parentWidget().config.uses_keyboard_navigation
            else QT_NO_FOCUS
        )
        self.setFocusPolicy(focus_policy)

        inner_layout = QtWidgets.QVBoxLayout()
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)

        self.title_label = QtWidgets.QLabel()
        self.title_label.setMargin(0)
        self.title_label.setContentsMargins(0, 0, 0, 0)
        self.title_label.setStyleSheet(self.get_title_style())
        self.title_label.setText(self.title)
        inner_layout.addWidget(self.title_label)

        if self.has_detail_row:
            self.detail_row = QtWidgets.QWidget()
            self.detail_row.setObjectName("listItemDetailRow")
            self.detail_row.setStyleSheet(
                "#listItemDetailRow { border-bottom: 1px solid #AAAAAA; }"
            )
            self.detail_row_layout = QtWidgets.QHBoxLayout(self.detail_row)
            self.detail_row_layout.setSpacing(4)
            self.detail_row_layout.setContentsMargins(0, 0, 0, 0)

            self.detail_label = QtWidgets.QLabel()
            self.detail_label.setMargin(0)
            self.detail_label.setContentsMargins(0, 0, 0, 0)
            self.detail_label.setStyleSheet("padding-bottom: 2%;")
            self.detail_label.setText(self.detail)
            if self.detail_icon:
                self.detail_icon_label = QtWidgets.QLabel()
                self.detail_icon_label.setMargin(0)
                self.detail_icon_label.setContentsMargins(0, 0, 0, 0)
                self.detail_row_layout.addWidget(self.detail_icon_label)
            self.detail_row_layout.addWidget(self.detail_label)
            inner_layout.addWidget(self.detail_row)

        self.outer_layout = QtWidgets.QHBoxLayout(self)
        self.outer_layout.setSpacing(0)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)

        self.outer_layout.addLayout(inner_layout, QT_ALIGN_LEFT)

    def keyPressEvent(self, e):
        if e.key() == QT_KEY_SPACE:
            self.enter_signal.emit()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update_selection_style()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update_selection_style()

    def set_selected(self, selected):
        self.selected = selected
        self.update_selection_style()

    def update_selection_style(self):
        self.setStyleSheet("color: white;" if self.selected or self.hasFocus() else "")

    def paintEvent(self, event):
        super().paintEvent(event)
        if not (self.selected or self.hasFocus()):
            return
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#000000"))

    @staticmethod
    def resize_label(label, font_size):
        q = label.font()
        q.setPixelSize(font_size)
        label.setFont(q)

    def resizeEvent(self, event):
        short_side_length = min(self.size().height(), self.size().width())
        self.resize_label(self.title_label, int(short_side_length * 0.45))
        if self.has_detail_row:
            self.resize_label(self.detail_label, int(short_side_length * 0.4))
            self.detail_row_layout.setContentsMargins(
                (
                    self.detail_left
                    if self.detail_left is not None
                    else int(self.width() * 0.2)
                ),
                0,
                0,
                int(short_side_length * 0.02),
            )
        if self.detail_icon:
            icon_size = int(short_side_length * 0.3)
            self.detail_icon_label.setFixedSize(icon_size, icon_size)
            self.detail_icon_label.setPixmap(
                self.detail_icon.pixmap(QtCore.QSize(icon_size, icon_size))
            )


class UploadActivityMenuWidget(MenuWidget):
    AUTO_UPLOAD_BUTTON = "Auto Upload"
    AUTO_UPLOAD_SERVICE_BUTTONS = {
        "STRAVA": "Strava",
        "GARMIN": "Garmin",
        "RWGPS": "Ride with GPS",
    }
    MANUAL_UPLOAD_BUTTONS = {
        "STRAVA": "Upload to Strava",
        "GARMIN": "Upload to Garmin",
        "RWGPS": "Upload to Ride with GPS",
    }

    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, icon
            (
                self.AUTO_UPLOAD_BUTTON,
                "toggle",
                lambda: self.onoff_auto_upload(True),
            ),
            (
                self.AUTO_UPLOAD_SERVICE_BUTTONS["STRAVA"],
                "toggle",
                lambda: self.onoff_auto_upload_service("STRAVA", True),
            ),
            (
                self.AUTO_UPLOAD_SERVICE_BUTTONS["GARMIN"],
                "toggle",
                lambda: self.onoff_auto_upload_service("GARMIN", True),
            ),
            (
                self.AUTO_UPLOAD_SERVICE_BUTTONS["RWGPS"],
                "toggle",
                lambda: self.onoff_auto_upload_service("RWGPS", True),
            ),
            ("", None, None),
            (
                self.MANUAL_UPLOAD_BUTTONS["STRAVA"],
                "cloud_upload",
                self.strava_upload,
                (icons.StravaIcon(), (icons.BASE_LOGO_SIZE * 4, icons.BASE_LOGO_SIZE)),
            ),
            (
                self.MANUAL_UPLOAD_BUTTONS["GARMIN"],
                "cloud_upload",
                self.garmin_upload,
                (icons.GarminIcon(), (icons.BASE_LOGO_SIZE * 5, icons.BASE_LOGO_SIZE)),
            ),
            (
                self.MANUAL_UPLOAD_BUTTONS["RWGPS"],
                "cloud_upload",
                self.rwgps_upload,
                (
                    icons.RideWithGPSIcon(),
                    (icons.BASE_LOGO_SIZE * 4, icons.BASE_LOGO_SIZE),
                ),
            ),
        )
        self.add_buttons(button_conf)

    def preprocess(self):
        for button in self.buttons.values():
            button.reset_loading_state()
        self.onoff_auto_upload(False)
        for service in self.AUTO_UPLOAD_SERVICE_BUTTONS:
            self.onoff_auto_upload_service(service, False)

    def onoff_auto_upload(self, change=True):
        if change:
            self.config.G_AUTO_UPLOAD = not self.config.G_AUTO_UPLOAD
            self.config.setting.write_config()
        self.buttons[self.AUTO_UPLOAD_BUTTON].change_toggle(self.config.G_AUTO_UPLOAD)

    def onoff_auto_upload_service(self, service, change=True):
        if change:
            self.config.G_AUTO_UPLOAD_SERVICE[service] = (
                not self.config.G_AUTO_UPLOAD_SERVICE[service]
            )
            self.config.setting.write_config()
        button_name = self.AUTO_UPLOAD_SERVICE_BUTTONS[service]
        self.buttons[button_name].change_toggle(
            self.config.G_AUTO_UPLOAD_SERVICE[service]
        )

    @qasync.asyncSlot()
    async def strava_upload(self):
        await self.buttons[self.MANUAL_UPLOAD_BUTTONS["STRAVA"]].run(
            self.config.api.strava_upload
        )

    @qasync.asyncSlot()
    async def garmin_upload(self):
        await self.buttons[self.MANUAL_UPLOAD_BUTTONS["GARMIN"]].run(
            self.config.api.garmin_upload
        )

    @qasync.asyncSlot()
    async def rwgps_upload(self):
        await self.buttons[self.MANUAL_UPLOAD_BUTTONS["RWGPS"]].run(
            self.config.api.rwgps_upload
        )


class LiveTrackMenuWidget(MenuWidget):
    THINGSBOARD_BUTTON = "ThingsBoard"
    GARMIN_BUTTON = "Garmin"
    GARMIN_MESSAGES_BUTTON = "Garmin Messages"

    def setup_menu(self):
        button_conf = (
            (
                self.THINGSBOARD_BUTTON,
                "toggle",
                lambda: self.onoff_thingsboard_livetrack(True),
            ),
            (
                self.GARMIN_BUTTON,
                "toggle",
                lambda: self.onoff_garmin_livetrack(True),
            ),
            (
                self.GARMIN_MESSAGES_BUTTON,
                "toggle",
                lambda: self.onoff_garmin_messages(True),
            ),
        )
        self.add_buttons(button_conf)
        self.update_buttons()

    def preprocess(self):
        self.update_buttons()

    def _thingsboard_available(self):
        thingsboard = self.config.G_THINGSBOARD_API
        return bool(
            thingsboard.get("HAVE_API_TOKEN")
            and thingsboard.get("TOKEN", "").strip()
            and thingsboard.get("SERVER", "").strip()
        )

    def _garmin_unavailable_reason(self):
        api_helper = getattr(self.config, "api", None)
        if api_helper is None:
            return "Garmin LiveTrack is disabled because API helper is not available."
        return api_helper.garmin_livetrack_configuration_reason()

    def _garmin_available(self):
        return self._garmin_unavailable_reason() is None

    def _show_unavailable(self, title, reason):
        gui = getattr(self.config, "gui", None)
        if gui is None:
            return
        popup_multiline = getattr(gui, "show_popup_multiline", None)
        if callable(popup_multiline):
            popup_multiline(title, reason, 5)
            return
        popup = getattr(gui, "show_popup", None)
        if callable(popup):
            popup(title, 5)

    def update_buttons(self):
        thingsboard_status = self.config.G_THINGSBOARD_API["STATUS"]
        garmin_status = self.config.G_GARMINCONNECT_API["LIVETRACK_STATUS"]
        messages_status = self.config.G_GARMINCONNECT_API["LIVETRACK_MESSAGES"]

        self.buttons[self.THINGSBOARD_BUTTON].change_toggle(thingsboard_status)
        self.buttons[self.GARMIN_BUTTON].change_toggle(garmin_status)
        self.buttons[self.GARMIN_MESSAGES_BUTTON].change_toggle(messages_status)

        self.buttons[self.THINGSBOARD_BUTTON].onoff_button(
            self._thingsboard_available() or thingsboard_status
        )
        garmin_available = self._garmin_available()
        self.buttons[self.GARMIN_BUTTON].onoff_button(garmin_available or garmin_status)
        self.buttons[self.GARMIN_MESSAGES_BUTTON].onoff_button(garmin_status)

    def onoff_thingsboard_livetrack(self, change=True):
        if change:
            if (
                not self.config.G_THINGSBOARD_API["STATUS"]
                and not self._thingsboard_available()
            ):
                self._show_unavailable(
                    "LiveTrack disabled",
                    "ThingsBoard TOKEN or SERVER is not configured.",
                )
                return
            self.config.G_THINGSBOARD_API["STATUS"] = not self.config.G_THINGSBOARD_API[
                "STATUS"
            ]
            self.config.setting.write_config()
        self.update_buttons()

    def onoff_garmin_livetrack(self, change=True):
        if change:
            if (
                not self.config.G_GARMINCONNECT_API["LIVETRACK_STATUS"]
                and not self._garmin_available()
            ):
                self._show_unavailable(
                    "Garmin LiveTrack disabled",
                    self._garmin_unavailable_reason(),
                )
                return
            self.config.G_GARMINCONNECT_API["LIVETRACK_STATUS"] = (
                not self.config.G_GARMINCONNECT_API["LIVETRACK_STATUS"]
            )
            self.config.setting.write_config()
        self.update_buttons()

    def onoff_garmin_messages(self, change=True):
        if change:
            if not self.config.G_GARMINCONNECT_API["LIVETRACK_STATUS"]:
                self._show_unavailable(
                    "Garmin Messages disabled",
                    "Enable Garmin LiveTrack first.",
                )
                return
            self.config.G_GARMINCONNECT_API["LIVETRACK_MESSAGES"] = (
                not self.config.G_GARMINCONNECT_API["LIVETRACK_MESSAGES"]
            )
            self.config.setting.write_config()
            self.config.api.request_garmin_message_capability_update()
        self.update_buttons()


class ConnectivityMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Auto BT Tethering", "toggle", lambda: self.bt_auto_tethering(True)),
            ("Select BT device", "submenu", self.select_bt_device),
            ("Live Track", "submenu", self.live_track_menu),
            ("Gadgetbridge", "toggle", self.onoff_ble_uart_service),
            ("Get Location", "toggle", self.onoff_gadgetbridge_gps),
        )
        self.add_buttons(button_conf)

        # Auto BT Tethering
        if not self.config.G_IS_RASPI:
            self.buttons["Auto BT Tethering"].disable()
            self.buttons["Select BT device"].disable()

        self.update_livetrack_button()

        # GadgetBridge
        if self.config.ble_uart is None:
            self.buttons["Gadgetbridge"].disable()
            self.buttons["Get Location"].disable()

        # initialize toggle button status
        self.bt_auto_tethering(change=False)

    def preprocess(self):
        if self.config.ble_uart:
            status = self.config.ble_uart.status
            self.buttons["Gadgetbridge"].change_toggle(status)
            self.buttons["Get Location"].change_toggle(self.config.ble_uart.gps_status)
            self.buttons["Get Location"].onoff_button(status)
        self.update_livetrack_button()

    def update_livetrack_button(self):
        thingsboard = self.config.G_THINGSBOARD_API
        thingsboard_available = bool(
            thingsboard.get("HAVE_API_TOKEN")
            and thingsboard.get("TOKEN", "").strip()
            and thingsboard.get("SERVER", "").strip()
        )
        api_helper = getattr(self.config, "api", None)
        garmin_reason = (
            api_helper.garmin_livetrack_configuration_reason()
            if api_helper is not None
            else "API helper is not available."
        )
        garmin_available = garmin_reason is None
        active = (
            thingsboard.get("STATUS")
            or self.config.G_GARMINCONNECT_API["LIVETRACK_STATUS"]
            or self.config.G_GARMINCONNECT_API["LIVETRACK_MESSAGES"]
        )
        self.buttons["Live Track"].onoff_button(
            thingsboard_available or garmin_available or active
        )

    def live_track_menu(self):
        self.change_page("Live Track", preprocess=True)

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
