try:
    import PyQt6.QtCore as QtCore
    import PyQt6.QtWidgets as QtWidgets
    import PyQt6.QtGui as QtGui
except:
    import PyQt5.QtCore as QtCore
    import PyQt5.QtWidgets as QtWidgets
    import PyQt5.QtGui as QtGui

from qasync import asyncSlot


#################################
# Menu
#################################


class MenuWidget(QtWidgets.QWidget):
    config = None
    page_name = None
    back_index_key = None
    focus_widget = None

    button = {}
    menu_layout = None

    logo_size = 30

    def __init__(self, parent, page_name, config):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.config = config
        self.page_name = page_name
        self.icon = QtGui.QIcon(
            self.config.gui.gui_config.icon_dir + "img/back_white.svg"
        )
        self.icon_x = 40
        self.icon_y = 32

        self.setup_ui()

    def setup_ui(self):
        self.setContentsMargins(0, 0, 0, 0)

        # top bar
        self.top_bar = QtWidgets.QWidget(self)
        self.top_bar.setStyleSheet(self.config.gui.style.G_GUI_PYQT_menu_topbar)

        self.back_button = QtWidgets.QPushButton()
        self.back_button.setIcon(self.icon)
        self.back_button.setIconSize(QtCore.QSize(20, 20))
        self.back_button.setProperty("style", "menu")
        self.back_button.setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_buttonStyle_navi
        )
        self.back_button.setFixedSize(self.icon_x, self.icon_y)
        # self.back_button.setScaledContents(True) #valid for svg icon
        if not self.config.G_IS_RASPI:
            self.back_button.focusInEvent = self.delete_focus

        self.page_name_label = QtWidgets.QLabel(self.page_name)
        self.page_name_label.setAlignment(self.config.gui.gui_config.align_center)
        self.page_name_label.setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_menu_topbar_page_name_label
        )

        self.next_button = QtWidgets.QPushButton()
        self.next_button.setEnabled(False)
        self.next_button.setFixedSize(self.icon_x, self.icon_y)
        self.next_button.setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_menu_topbar_next_button
        )

        self.top_bar_layout = QtWidgets.QHBoxLayout(self.top_bar)
        self.top_bar_layout.setContentsMargins(5, 5, 5, 5)
        self.top_bar_layout.setSpacing(0)
        self.top_bar_layout.addWidget(self.back_button)
        self.top_bar_layout.addWidget(self.page_name_label)
        self.top_bar_layout.addWidget(self.next_button)

        self.top_bar.setLayout(self.top_bar_layout)

        # self.scroll_area = QtWidgets.QScrollArea(self)
        # self.menu = QtWidgets.QWidget(self.scroll_area)
        self.menu = QtWidgets.QWidget(self)
        self.setup_menu()
        self.menu_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_layout.setSpacing(0)

        # self.scroll_area.setWidgetResizable(True)
        # self.scroll_area.setWidget(self.menu)
        # self.scroll_area.setFocusPolicy(self.config.gui.gui_config.no_focus)
        # self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        # self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.top_bar)
        layout.addWidget(self.menu)
        # layout.addWidget(self.scroll_area)
        self.setLayout(layout)

        self.connect_back_button()
        self.connect_buttons()

    def delete_focus(self, event):
        # fixed focus on PC or macOS
        if event.reason() == 7 and self.focusWidget() == self.back_button:
            self.back_button.clearFocus()
        super().focusInEvent(event)

    def make_menu_layout(self, qt_layout):
        self.menu_layout = qt_layout(self.menu)
        self.menu_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_layout.setSpacing(0)

    def add_buttons(self, buttons, back_connect=True):
        n = len(buttons)
        layout_type = None

        if n <= 4:
            layout_type = QtWidgets.QVBoxLayout
        else:
            layout_type = QtWidgets.QGridLayout
        if layout_type != None:
            self.make_menu_layout(layout_type)

        i = 0
        for b in buttons:
            self.button[b[0]] = self.MenuButton(b[0], self.config)
            if b[1] == "submenu":
                self.button[b[0]].set_submenu_icon(*b[3:])
                # set back_index of child widget
                if back_connect:
                    index = self.config.gui.gui_config.G_GUI_INDEX[b[0]]
                    self.parentWidget().widget(index).back_index_key = self.page_name
            elif b[1] == "toggle":
                self.button[b[0]].set_toggle_icon()
            elif b[1] == "cloud_upload":
                self.button[b[0]].set_cloud_upload_icon(*b[3:])
            else:
                self.button[b[0]].set_null_icon()

            if b[2] != None:
                self.button[b[0]].clicked.connect(b[2])
            else:
                self.button[b[0]].setEnabled(False)
                self.button[b[0]].setProperty("style", "unavailable")

            if layout_type == QtWidgets.QVBoxLayout:
                self.menu_layout.addWidget(self.button[b[0]])
            else:
                self.menu_layout.addWidget(self.button[b[0]], i % 4, i // 4)
                i += 1

        # add dummy button
        if n in (1, 2, 3):
            for j in range(4 - n):
                self.menu_layout.addWidget(self.MenuButton("", self.config, dummy=True))

        # set first focus
        if not self.config.display.has_touch():
            self.focus_widget = self.button[buttons[0][0]]

    def setup_menu(self):
        pass

    def resizeEvent(self, event):
        # w = self.size().width()
        h = self.size().height()
        self.top_bar.setFixedHeight(int(h / 5))

        q = self.page_name_label.font()
        q.setPixelSize(int(h / 12))
        self.page_name_label.setFont(q)

    def connect_buttons(self):
        pass

    def connect_back_button(self):
        self.back_button.clicked.connect(self.back)

    def back(self):
        index = 0
        if (
            self.back_index_key != None
            and self.back_index_key in self.config.gui.gui_config.G_GUI_INDEX
        ):
            index = self.config.gui.gui_config.G_GUI_INDEX[self.back_index_key]
        self.on_back_menu()
        self.config.gui.change_menu_page(index, focus_reset=False)

    def on_back_menu(self):
        pass

    def change_page(self, page, preprocess=False, **kargs):
        index = self.config.gui.gui_config.G_GUI_INDEX[page]
        if preprocess:
            self.parentWidget().widget(index).preprocess(**kargs)
        self.config.gui.change_menu_page(index)

    class MenuButton(QtWidgets.QPushButton):
        config = None
        button_type = None
        status = False
        first_button = False
        last_button = False
        icon_img = {
            "null": QtGui.QIcon(),
            "submenu": QtGui.QIcon("./img/forward_black_line.svg"),
            #'submenu': QtGui.QIcon('./img/forward_black.svg'),
            "toggle": QtGui.QIcon("./img/toggle_off.svg"),
            "cloud_upload": QtGui.QIcon("./img/cloud_upload.svg"),
            "background_task": QtGui.QIcon(),
        }
        toggle_img = {
            "on": QtGui.QIcon("./img/toggle_on_blue.svg"),
            "off": icon_img["toggle"],
            "off_hover": QtGui.QIcon("./img/toggle_off_hover.svg"),
        }
        res_img = {
            # True: QtGui.QIcon('./img/button_ok.svg'),
            True: QtGui.QIcon("./img/cloud_upload_done.svg"),
            False: QtGui.QIcon("./img/button_warning.svg"),
        }
        hover_img = {
            "submenu": {
                True: QtGui.QIcon("./img/forward_white_line.svg"),
                # True: QtGui.QIcon('./img/forward_white.svg'),
                False: icon_img["submenu"],
            },
            # toggle_off
            "toggle": {
                True: QtGui.QIcon("./img/toggle_off_hover.svg"),
                False: icon_img["toggle"],
            },
        }
        icon_size = {
            "toggle": 36,
            "submenu": 20,  # 24
            "cloud_upload": 24,
            "background_task": 24,
            "null": 24,
        }
        icon_qsize = {}
        icon_margin = {
            "toggle": 5,
            "submenu": 1,
            "cloud_upload": 10,
            "background_task": 10,
            "null": 0,
        }
        loading_result = False

        def __init__(self, text, config, dummy=False):
            super().__init__(text=text)
            self.config = config

            self.setSizePolicy(
                self.config.gui.gui_config.expanding,
                self.config.gui.gui_config.expanding,
            )
            self.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_menu)

            for k, v in self.icon_size.items():
                self.icon_qsize[k] = QtCore.QSize(v, v)

            if dummy:
                self.setEnabled(False)
                self.setProperty("style", "dummy")

        def setup_icon(self):
            self.right_icon = QtWidgets.QLabel()
            self.right_icon.setAttribute(
                self.config.gui.gui_config.WA_TranslucentBackground
            )
            self.right_icon.setAttribute(
                self.config.gui.gui_config.WA_TransparentForMouseEvents
            )

            self.icon_layout = QtWidgets.QHBoxLayout(self)
            self.icon_layout.addWidget(
                self.right_icon, alignment=self.config.gui.gui_config.align_right
            )

        def set_icon_with_size(self):
            self.setup_icon()
            self.icon_layout.setContentsMargins(
                0, 0, self.icon_margin[self.button_type], 0
            )
            self.right_icon.setPixmap(
                self.icon_img[self.button_type].pixmap(
                    self.icon_qsize[self.button_type]
                )
            )

        def set_service_icon(self, label_img, qsize):
            self.setText("")
            self.setIcon(QtGui.QIcon(QtGui.QPixmap(label_img)))
            self.setIconSize(qsize)

        def set_submenu_icon(self, label_img=None, qsize=None):
            self.button_type = "submenu"
            if label_img != None and qsize != None:
                self.set_service_icon(label_img, qsize)
            self.set_icon_with_size()

        def set_toggle_icon(self):
            self.button_type = "toggle"
            self.set_icon_with_size()

        def set_cloud_upload_icon(self, label_img, qsize):
            self.button_type = "cloud_upload"
            self.set_service_icon(label_img, qsize)
            self.set_icon_with_size()
            self.init_loading_icon()

        def set_background_task_icon(self):
            self.button_type = "background_task"
            self.set_icon_with_size()
            self.init_loading_icon()

        def set_null_icon(self):
            self.button_type = "null"
            self.set_icon_with_size()

        def onoff_button(self, status):
            if status:
                self.enable()
            else:
                self.disable()
            self.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_menu)

        def disable(self):
            self.setEnabled(False)
            self.setProperty("style", "unavailable")

        def enable(self):
            self.setEnabled(True)
            self.setProperty("style", None)

        def resizeEvent(self, event):
            # w = self.size().width()
            h = self.size().height()
            psize = int(h / 2.5) if int(h / 2.5) > 0 else 1

            q = self.font()
            q.setPixelSize(psize)
            self.setFont(q)

        def focusInEvent(self, event):
            super().focusInEvent(event)
            if self.button_type == "submenu" or (
                self.button_type == "toggle" and not self.status
            ):
                self.change_icon_with_hover(True)
            elif self.button_type == "null":
                self.right_icon.setPixmap(
                    self.icon_img["null"].pixmap(self.icon_qsize["null"])
                )
            # if self.first_button:
            #  vs = self.scroll_area.verticalScrollBar()
            #  vs.setValue(vs.minimum())
            # elif self.last_button:
            #  vs = self.scroll_area.verticalScrollBar()
            #  vs.setValue(vs.maximum())

        def focusOutEvent(self, event):
            super().focusOutEvent(event)
            if self.button_type == "submenu" or (
                self.button_type == "toggle" and not self.status
            ):
                self.change_icon_with_hover(False)
            elif self.button_type == "null":
                self.right_icon.setPixmap(
                    self.icon_img["null"].pixmap(self.icon_qsize["null"])
                )

        def change_icon_with_hover(self, status):
            self.right_icon.setPixmap(
                self.hover_img[self.button_type][status].pixmap(
                    self.icon_qsize[self.button_type]
                )
            )

        def change_toggle(self, status=False):
            self.status = status
            mode = "off"
            if self.status:
                mode = "on"
            elif self.hasFocus():
                mode = "off_hover"
            self.right_icon.setPixmap(
                self.toggle_img[mode].pixmap(self.icon_qsize[self.button_type])
            )

        @QtCore.pyqtSlot()
        def loading_start(self):
            if not self.status:
                self.status = True
                self.loading_movie.start()

        @QtCore.pyqtSlot()
        def loading_stop(self, res):
            self.loading_movie.stop()
            self.right_icon.setPixmap(
                self.res_img[res].pixmap(self.icon_qsize[self.button_type])
            )
            self.status = False

        def init_loading_icon(self):
            self.loading_result = False
            self.loading_movie = QtGui.QMovie(self)
            self.loading_movie.setFileName("./img/loading.gif")
            self.loading_movie.frameChanged.connect(self.on_frameChanged)
            if self.loading_movie.loopCount() != -1:
                self.loading_movie.finished.connect(self.start)

        @QtCore.pyqtSlot(int)
        def on_frameChanged(self, frameNumber):
            self.right_icon.setPixmap(
                QtGui.QIcon(self.loading_movie.currentPixmap()).pixmap(
                    self.icon_qsize[self.button_type]
                )
            )

        async def run(self, func):
            if self.status:
                return

            self.loading_start()
            self.loading_result = await func()
            self.loading_stop(self.loading_result)


class TopMenuWidget(MenuWidget):
    back_index_key = "Main"

    def setup_menu(self):
        self.button = {}
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Sensors", "submenu", self.sensors_menu),
            ("Courses", "submenu", self.courses_menu),
            ("Live Track", "submenu", self.livetrack_menu),
            ("Upload Activity", "submenu", self.cloud_services_menu),
            ("Map", "submenu", self.map_menu),
            ("Profile", "submenu", self.profile_menu),
            ("System", "submenu", self.setting_menu),
        )
        self.add_buttons(button_conf)

    def sensors_menu(self):
        self.change_page("Sensors")

    def cloud_services_menu(self):
        self.change_page("Upload Activity")

    def courses_menu(self):
        self.change_page("Courses", preprocess=True)

    def livetrack_menu(self):
        self.change_page("Live Track", preprocess=True)

    def map_menu(self):
        self.change_page("Map")

    def profile_menu(self):
        self.change_page("Profile")

    def setting_menu(self):
        self.change_page("System")


class ListWidget(MenuWidget):
    list_type = None
    selected_item = None
    size_hint = None

    # for simple list
    settings = None

    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QVBoxLayout)

        self.list = QtWidgets.QListWidget()
        # self.list.setSortingEnabled(True)
        self.list.setHorizontalScrollBarPolicy(
            self.config.gui.gui_config.scrollbar_alwaysoff
        )
        self.list.setVerticalScrollBarPolicy(
            self.config.gui.gui_config.scrollbar_alwaysoff
        )
        self.list.setFocusPolicy(self.config.gui.gui_config.no_focus)
        self.list.setStyleSheet("background-color: transparent;")

        self.menu_layout.addWidget(self.list)

        self.setup_menu_extra()

    # override for custom list
    def setup_menu_extra(self):
        # for simple list
        for k in self.settings.keys():
            api_mode_item = ListItemWidget(self, self.config)
            api_mode_item.title_label.setText(k)
            api_mode_item.set_simple_list_stylesheet(hide_detail_label=True)
            api_mode_item.enter_signal.connect(self.button_func)
            self.add_list_item(api_mode_item)

    # override for custom list
    def connect_buttons(self):
        self.list.itemSelectionChanged.connect(self.changed_item)
        self.list.itemClicked.connect(self.button_func)

    @asyncSlot()
    async def button_func(self):
        await self.button_func_extra()
        self.back()

    async def button_func_extra(self):
        pass

    def changed_item(self):
        # item is QListWidgetItem
        item = self.list.selectedItems()
        if len(item) > 0:
            self.selected_item = self.list.itemWidget(item[0])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = int((self.height() - self.top_bar.height()) / 4)
        self.size_hint = QtCore.QSize(self.top_bar.width(), h)
        for i in range(self.list.count()):
            self.list.item(i).setSizeHint(self.size_hint)
        self.resize_extra()

    def resize_extra(self):
        pass

    def preprocess(self, **kargs):
        self.list_type = kargs.get("list_type")
        reset = kargs.get("reset", False)
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
        if default_index != None:
            self.list.setCurrentRow(default_index)
            self.list.itemWidget(self.list.currentItem()).setFocus()

    def get_default_value(self):
        return None

    def add_list_item(self, item):
        list_item = QtWidgets.QListWidgetItem(self.list)
        if self.size_hint != None:
            list_item.setSizeHint(self.size_hint)
        self.list.setItemWidget(list_item, item)


class ListItemWidget(QtWidgets.QWidget):
    config = None
    icon = None
    list_info = {}
    enter_signal = QtCore.pyqtSignal()

    def __init__(self, parent, config):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.config = config
        self.setup_ui()

    def setup_ui(self):
        self.setContentsMargins(0, 0, 0, 0)
        self.setFocusPolicy(self.config.gui.gui_config.strong_focus)

        self.title_label = QtWidgets.QLabel()
        self.title_label.setMargin(0)
        self.title_label.setContentsMargins(0, 0, 0, 0)

        self.detail_label = QtWidgets.QLabel()
        self.detail_label.setMargin(0)
        self.detail_label.setContentsMargins(0, 0, 0, 0)

        self.inner_layout = QtWidgets.QVBoxLayout()
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(0)
        self.inner_layout.addWidget(self.title_label)
        self.inner_layout.addWidget(self.detail_label)

        self.outer_layout = QtWidgets.QHBoxLayout()
        self.outer_layout.setSpacing(0)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)

        self.add_extra()

        self.setLayout(self.outer_layout)

    def add_extra(self):
        # outer layout
        self.outer_layout.addLayout(
            self.inner_layout, self.config.gui.gui_config.align_left
        )

    def set_info(self, **kargs):
        pass

    def keyPressEvent(self, e):
        if e.key() == self.config.gui.gui_config.key_space:
            self.enter_signal.emit()

    def set_icon(self, image_path):
        self.icon.setPixmap(QtGui.QPixmap(image_path).scaled(30, 30))

    def resizeEvent(self, event):
        h = self.size().height()
        for text, fsize in zip(
            [self.title_label, self.detail_label], [int(h * 0.45), int(h * 0.4)]
        ):
            q = text.font()
            q.setPixelSize(fsize)
            text.setFont(q)

    def set_simple_list_stylesheet(self, hide_detail_label=False):
        title_style = "padding-left: 10%; padding-top: 2%;"
        detail_style = "padding-left: 20%; padding-bottom: 2%;"
        if hide_detail_label:
            self.detail_label.hide()
            title_style = (
                title_style + " " + self.config.gui.style.G_GUI_PYQT_menu_list_border
            )
        else:
            detail_style = (
                detail_style + " " + self.config.gui.style.G_GUI_PYQT_menu_list_border
            )
        self.title_label.setStyleSheet(title_style)
        self.detail_label.setStyleSheet(detail_style)


class UploadActivityMenuWidget(MenuWidget):
    def setup_menu(self):
        self.button = {}
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            (
                "Strava",
                "cloud_upload",
                self.strava_upload,
                "./img/strava_logo.svg",
                QtCore.QSize(self.logo_size * 4, self.logo_size),
            ),
            (
                "Garmin",
                "cloud_upload",
                self.garmin_upload,
                "./img/garmin_logo.svg",
                QtCore.QSize(self.logo_size * 5, self.logo_size),
            ),
            (
                "Ride with GPS",
                "cloud_upload",
                self.rwgps_upload,
                "./img/rwgps_logo.svg",
                QtCore.QSize(self.logo_size * 4, self.logo_size),
            ),
        )
        self.add_buttons(button_conf)

    @asyncSlot()
    async def strava_upload(self):
        await self.button["Strava"].run(self.config.network.api.strava_upload)

    @asyncSlot()
    async def garmin_upload(self):
        await self.button["Garmin"].run(self.config.network.api.garmin_upload)

    @asyncSlot()
    async def rwgps_upload(self):
        await self.button["Ride with GPS"].run(self.config.network.api.rwgps_upload)


class LiveTrackMenuWidget(MenuWidget):
    def setup_menu(self):
        self.button = {}
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Live Track", "toggle", lambda: self.onoff_live_track(True)),
            (
                "Auto upload via BT",
                "toggle",
                lambda: self.onoff_auto_upload_via_BT(True),
            ),
            ("Select BT device", "submenu", self.bt_tething),
        )
        self.add_buttons(button_conf, back_connect=False)

        # set back_index of child widget
        self.bt_page_name = "BT Tethering"
        self.bt_index = self.config.gui.gui_config.G_GUI_INDEX[self.bt_page_name]

        if (
            self.config.network.api.thingsboard_check()
            and self.config.G_THINGSBOARD_API["HAVE_API_TOKEN"]
        ):
            if not self.config.G_IS_RASPI:
                self.button["Auto upload via BT"].disable()
        else:
            self.button["Live Track"].disable()
            self.button["Auto upload via BT"].disable()

        if not self.config.G_THINGSBOARD_API["AUTO_UPLOAD_VIA_BT"]:
            self.button["Select BT device"].disable()

    def preprocess(self):
        # initialize toggle button status
        self.onoff_live_track(change=False)
        self.parentWidget().widget(self.bt_index).back_index_key = self.page_name

    def onoff_live_track(self, change=True):
        if change:
            self.config.G_THINGSBOARD_API["STATUS"] = not self.config.G_THINGSBOARD_API[
                "STATUS"
            ]
            self.config.setting.set_config_pickle(
                "G_THINGSBOARD_API_STATUS", self.config.G_THINGSBOARD_API["STATUS"]
            )
        self.button["Live Track"].change_toggle(self.config.G_THINGSBOARD_API["STATUS"])

    def onoff_auto_upload_via_BT(self, change=True):
        if change:
            self.config.G_THINGSBOARD_API[
                "AUTO_UPLOAD_VIA_BT"
            ] = not self.config.G_THINGSBOARD_API["AUTO_UPLOAD_VIA_BT"]
            self.config.setting.set_config_pickle(
                "AUTO_UPLOAD_VIA_BT",
                self.config.G_THINGSBOARD_API["AUTO_UPLOAD_VIA_BT"],
            )
        self.button["Auto upload via BT"].change_toggle(
            self.config.G_THINGSBOARD_API["AUTO_UPLOAD_VIA_BT"]
        )

        self.button["Select BT device"].onoff_button(
            self.config.G_THINGSBOARD_API["AUTO_UPLOAD_VIA_BT"]
        )

    def bt_tething(self):
        self.change_page(self.bt_page_name, preprocess=True, run_bt_tethering=False)
