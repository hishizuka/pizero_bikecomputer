import sys
import os

from datetime import datetime
import asyncio

from logger import app_logger
from modules.gui_qt_base import GUI_Qt_Base
from modules._pyqt import (
    QT_ALIGN_BOTTOM,
    QT_ALIGN_LEFT,
    QT_ALIGN_CENTER,
    QT_STACKINGMODE_STACKALL,
    QT_PE_WIDGET,
    QT_STACKINGMODE_STACKONE,
    QT_KEY_RELEASE,
    QT_KEY_SPACE,
    QT_KEY_PRESS,
    QT_KEY_BACKTAB,
    QT_KEY_TAB,
    QT_NO_MODIFIER,
    QtCore,
    QtWidgets,
    QtGui,
    qasync,
    Signal,
)
from modules.utils.timer import Timer, log_timers


class SplashScreen(QtWidgets.QWidget):
    STYLES = """
        background: black;
    """
    # gradient style
    #    qlineargradient(
    #        x1:0 y1:0, x2:0 y2:1.0, 
    #        stop:0 blue, stop:0.19 blue, stop:0.2 red, stop:0.39 red, stop:0.4 black, stop:0.59 black, stop:0.6 yellow, stop:0.79 yellow, stop:0.8 green
    #    );

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet(self.STYLES)


class BootStatus(QtWidgets.QLabel):
    STYLES = """
      color: white;
      font-size: 20px;
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setStyleSheet(self.STYLES)
        self.setAlignment(QT_ALIGN_CENTER)


class MainWindow(QtWidgets.QMainWindow):
    gui = None

    def __init__(self, title, size, parent=None):
        super().__init__(parent=parent)
        app_logger.info(f"Qt version: {QtCore.QT_VERSION_STR}")
        self.setWindowTitle(title)
        self.setMinimumSize(*size)
        self.set_color()

    # TODO, daylight does not seem to be used at all,
    #  Could/Should be replaced by setting stylesheet on init
    def set_color(self, daylight=True):
        if daylight:
            self.setStyleSheet("color: black; background-color: white")
        else:
            self.setStyleSheet("color: white; background-color: #222222")

    def set_gui(self, gui):
        self.gui = gui

    # override from QtWidget
    @qasync.asyncClose
    async def closeEvent(self, event):
        await self.gui.quit()

    # override from QtWidget
    def paintEvent(self, event):
        self.gui.draw_display()


class GUI_PyQt(GUI_Qt_Base):
    main_window = None

    stack_widget = None
    button_box_widget = None
    main_page = None
    main_page_index = 0
    altitude_graph_widget = None
    acc_graph_widget = None
    performance_graph_widget = None
    course_profile_graph_widget = None
    map_widget = None
    cuesheet_widget = None
    multi_scan_widget = None

    # signal
    signal_next_button = Signal(int)
    signal_prev_button = Signal(int)
    signal_menu_button = Signal(int)
    signal_menu_back_button = Signal()
    signal_get_screenshot = Signal()
    signal_multiscan = Signal()
    signal_start_and_stop_manual = Signal()
    signal_count_laps = Signal()
    signal_reset_count = Signal()
    signal_boot_status = Signal(str)
    signal_change_overlay = Signal()
    signal_modify_map_tile = Signal()
    signal_turn_on_off_light = Signal()

    # for dialog
    display_dialog = False
    
    @property
    def grab_func(self):
        return self.stack_widget.grab().toImage()

    def __init__(self, config):
        super().__init__(config)

    def init_window(self):
        self.app = QtWidgets.QApplication(sys.argv)
        self.config.loop = qasync.QEventLoop(self.app)
        self.config.loop.set_debug(True)
        self.config.init_loop(call_from_gui=True)

        self.main_window = MainWindow(
            self.config.G_PRODUCT, self.config.display.resolution
        )
        self.main_window.set_gui(self)
        self.main_window.show()

        self.stack_widget = QtWidgets.QStackedWidget(self.main_window)
        self.main_window.setCentralWidget(self.stack_widget)
        self.stack_widget.setContentsMargins(0, 0, 0, 0)

        # stack_widget elements (splash)
        splash_widget = SplashScreen(self.stack_widget)
        self.stack_widget.addWidget(splash_widget)

        splash_layout = QtWidgets.QVBoxLayout(splash_widget)
        splash_layout.setContentsMargins(0, 0, 0, 0)
        splash_layout.setSpacing(0)

        boot_status = BootStatus()
        self.signal_boot_status.connect(boot_status.setText)
        splash_layout.addWidget(boot_status)

        # for draw_display
        self.init_buffer(self.config.display)

        self.exec()

    async def set_boot_status(self, text):
        self.signal_boot_status.emit(text)
        self.draw_display(direct_update=True)
        if not self.config.G_IS_RASPI:
            await asyncio.sleep(0.01)  # need for changing QLabel in the event loop

    def delay_init(self):
        # ensure visually alignment for log
        timers = [
            Timer(auto_start=False, text="  misc  : {0:.3f} sec"),
            Timer(auto_start=False, text="  import: {0:.3f} sec"),
            Timer(auto_start=False, text="  menu  : {0:.3f} sec"),
            Timer(auto_start=False, text="  main  : {0:.3f} sec"),
        ]

        with timers[0]:
            self.add_font()

            # physical button
            self.signal_next_button.connect(self.scroll)
            self.signal_prev_button.connect(self.scroll)
            self.signal_menu_button.connect(self.change_menu_page)
            self.signal_menu_back_button.connect(self.change_menu_back)
            # other
            self.signal_get_screenshot.connect(self.screenshot)
            self.signal_multiscan.connect(self.multiscan_internal)

            self.signal_start_and_stop_manual.connect(
                self.start_and_stop_manual_internal
            )
            self.signal_count_laps.connect(self.count_laps_internal)
            self.signal_reset_count.connect(self.reset_count_internal)

            self.signal_change_overlay.connect(self.change_map_overlays_internal)
            self.signal_modify_map_tile.connect(self.modify_map_tile_internal)

            self.signal_turn_on_off_light.connect(self.turn_on_off_light_internal)

            self.msg_queue = asyncio.Queue()
            self.msg_event = asyncio.Event()
            asyncio.create_task(self.msg_worker())

        with timers[1]:
            import modules.pyqt.graph.pyqt_map as pyqt_map
            import modules.pyqt.graph.pyqt_course_profile as pyqt_course_profile
            import modules.pyqt.graph.pyqt_value_graph as pyqt_value_graph
            from modules.pyqt.pyqt_values_widget import ValuesWidget

            from modules.pyqt.menu.pyqt_menu_widget import (
                TopMenuWidget,
                ConnectivityMenuWidget,
                UploadActivityMenuWidget,
            )
            from modules.pyqt.menu.pyqt_system_menu_widget import (
                SystemMenuWidget,
                NetworkMenuWidget,
                BluetoothTetheringListWidget,
                DebugMenuWidget,
                DebugLogViewerWidget,
            )
            from modules.pyqt.menu.pyqt_profile_widget import ProfileWidget
            from modules.pyqt.menu.pyqt_sensor_menu_widget import (
                SensorMenuWidget,
                ANTMenuWidget,
                ANTListWidget,
            )
            from modules.pyqt.menu.pyqt_course_menu_widget import (
                CoursesMenuWidget,
                CourseListWidget,
                CourseDetailWidget,
                #GoogleDirectionsAPISettingMenuWidget
            ) 
            from modules.pyqt.menu.pyqt_map_menu_widget import (
                MapMenuWidget,
                MapListWidget,
                MapOverlayMenuWidget,
                HeatmapListWidget,
                RainmapListWidget,
                WindmapListWidget,
                ExternalDataSourceMenuWidget,
                WindSourceListWidget,
                DEMTileListWidget,
            )
            from modules.pyqt.menu.pyqt_adjust_widget import (
                AdjustAltitudeWidget,
                AdjustWheelCircumferenceWidget,
                AdjustCPWidget,
                AdjustWPrimeBalanceWidget,
            )
            from modules.pyqt.pyqt_cuesheet_widget import CueSheetWidget
            from modules.pyqt.pyqt_multiscan_widget import MultiScanWidget

        with timers[2]:
            # self.main_window
            #  stack_widget
            #    splash_widget
            #    main_widget
            #      main_layout
            #        main_page
            #        button_box_widget
            #    menu_widget
            #    ant_menu_widget
            #    ant_detail_widget
            #    adjust_wheel_circumference_widget
            #    adjust_atitude_widget
            #    debug_log_viewer_widget

            # stack_widget elements (main)
            main_widget = QtWidgets.QWidget(self.stack_widget)
            main_widget.setContentsMargins(0, 0, 0, 0)
            self.stack_widget.addWidget(main_widget)

            # reverse order (make children widget first, then make parent widget)
            menus = [
                ("ANT+ Detail", ANTListWidget),
                ("ANT+ Sensors", ANTMenuWidget),
                ("Wheel Size", AdjustWheelCircumferenceWidget),
                ("Adjust Altitude", AdjustAltitudeWidget),
                ("Sensors", SensorMenuWidget),
                ("BT Tethering", BluetoothTetheringListWidget),
                ("Network", NetworkMenuWidget),
                ("Debug Log", DebugLogViewerWidget),
                ("Debug", DebugMenuWidget),
                ("System", SystemMenuWidget),
                ("CP", AdjustCPWidget),
                ("W Prime Balance", AdjustWPrimeBalanceWidget),
                ("Profile", ProfileWidget),
                ("Connectivity", ConnectivityMenuWidget),
                ("Upload Activity", UploadActivityMenuWidget),
                ("DEM Tile source", DEMTileListWidget),
                ("Wind Source", WindSourceListWidget),
                ("External Data Sources", ExternalDataSourceMenuWidget),
                ("Wind map List", WindmapListWidget),
                ("Rain map List", RainmapListWidget),
                ("Heatmap List", HeatmapListWidget),
                ("Map Overlay", MapOverlayMenuWidget),
                ("Select Map", MapListWidget),
                ("Map and Data", MapMenuWidget),
                # ("Google Directions API mode", GoogleDirectionsAPISettingMenuWidget),
                ("Course Detail", CourseDetailWidget),
                ("Courses List", CourseListWidget),
                ("Courses", CoursesMenuWidget),
                ("Menu", TopMenuWidget),
            ]
            menu_count = max(self.gui_config.G_GUI_INDEX.values()) + 1
            for m in menus:
                m_widget = m[1](self.stack_widget, m[0], self.config)
                m_widget.setContentsMargins(0, 0, 0, 0)
                self.stack_widget.addWidget(m_widget)
                self.gui_config.G_GUI_INDEX[m[0]] = menu_count
                menu_count += 1

            self.stack_widget.setCurrentIndex(1)

        with timers[3]:
            # main layout
            main_layout = QtWidgets.QVBoxLayout(main_widget)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # main Widget
            self.main_page = QtWidgets.QStackedWidget(main_widget)
            self.main_page.setContentsMargins(0, 0, 0, 0)

            for k, v in self.gui_config.layout.items():
                if not v["STATUS"]:
                    continue
                if "LAYOUT" in v:
                    self.main_page.addWidget(
                        ValuesWidget(
                            self.main_page,
                            self.config,
                            v["LAYOUT"],
                        )
                    )
                else:
                    if (
                        k == "ALTITUDE_GRAPH"
                        and "i2c_baro_temp"
                        in self.config.logger.sensor.sensor_i2c.sensor
                    ):
                        self.altitude_graph_widget = (
                            pyqt_value_graph.AltitudeGraphWidget(
                                self.main_page, self.config
                            )
                        )
                        self.main_page.addWidget(self.altitude_graph_widget)
                    elif (
                        k == "ACC_GRAPH"
                        and self.config.logger.sensor.sensor_i2c.motion_sensor["ACC"]
                    ):
                        self.acc_graph_widget = (
                            pyqt_value_graph.AccelerationGraphWidget(
                                self.main_page, self.config
                            )
                        )
                        self.main_page.addWidget(self.acc_graph_widget)
                    elif k == "PERFORMANCE_GRAPH" and self.config.G_ANT["STATUS"]:
                        self.performance_graph_widget = (
                            pyqt_value_graph.PerformanceGraphWidget(
                                self.main_page, self.config
                            )
                        )
                        self.main_page.addWidget(self.performance_graph_widget)
                    elif k == "COURSE_PROFILE_GRAPH":
                        self.course_profile_graph_widget = (
                            pyqt_course_profile.CourseProfileGraphWidget(
                                self.main_page, self.config
                            )
                        )
                        self.main_page.addWidget(self.course_profile_graph_widget)
                    elif k == "SIMPLE_MAP":
                        self.map_widget = pyqt_map.MapWidget(
                            self.main_page, self.config
                        )
                        self.main_page.addWidget(self.map_widget)
                    elif (
                        k == "CUESHEET"
                    ):
                        self.cuesheet_widget = CueSheetWidget(
                            self.main_page, self.config
                        )
                        self.main_page.addWidget(self.cuesheet_widget)
                    
            if self.config.G_ANT["STATUS"]:
                self.multi_scan_widget = MultiScanWidget(self.main_page, self.config)
                self.main_page.addWidget(self.multi_scan_widget)
                self.multiscan_index = self.main_page.count() - 1
                self.multiscan_back_index = self.multiscan_index

            # integrate main_layout
            main_layout.addWidget(self.main_page)
            if self.config.display.has_touch:
                from modules.pyqt.pyqt_button_box_widget import ButtonBoxWidget

                self.button_box_widget = ButtonBoxWidget(main_widget, self.config)
                main_layout.addWidget(self.button_box_widget)

            # fullscreen
            if self.config.G_FULLSCREEN:
                self.main_window.showFullScreen()

            self.on_change_main_page(self.main_page_index)

        app_logger.info("Drawing components:")
        log_timers(timers, text_total="  total : {0:.3f} sec")

    # for main_page page transition
    def on_change_main_page(self, index):
        self.main_page.widget(self.main_page_index).stop()
        self.main_page.widget(index).start()
        self.main_page_index = index

    def start_and_stop_manual(self):
        self.signal_start_and_stop_manual.emit()

    def start_and_stop_manual_internal(self):
        self.logger.start_and_stop_manual()

    def count_laps(self):
        self.signal_count_laps.emit()

    def count_laps_internal(self):
        self.logger.count_laps()

    def reset_count(self):
        self.signal_reset_count.emit()

    def reset_count_internal(self):
        res = self.logger.reset_count()
        self.map_widget.reset_track()
        if (
            res
            and self.config.G_AUTO_UPLOAD
            and any(self.config.G_AUTO_UPLOAD_SERVICE.values())
        ):
            self.show_dialog(self.upload_activity, "Upload Activity?")

    @qasync.asyncSlot()
    async def upload_activity(self):
        f_name = self.upload_activity.__name__
        upload_func = {
            "STRAVA": self.config.api.strava_upload,
            "RWGPS": self.config.api.rwgps_upload,
            "GARMIN": self.config.api.garmin_upload,
        }

        # BT tethering on
        bt_status = await self.config.network.open_bt_tethering(f_name)
        res_status = False

        for k, v in self.config.G_AUTO_UPLOAD_SERVICE.items():
            if v:
                self.show_forced_message(f"Upload to {k}...")
                await asyncio.sleep(1.0)
                # need to select service with loading images
                res_status |= await upload_func[k]()

        # BT tethering off
        if bt_status:
            await self.config.network.close_bt_tethering(f_name)

        self.delete_popup()
        if res_status:
            self.show_dialog(self.power_off, "Power Off?")
        else:
            self.show_dialog_ok_only(None, "Upload failed.")

    @qasync.asyncSlot()
    async def power_off(self):
        await self.config.power_off()

    @staticmethod
    def press_key(key):
        e_press = QtGui.QKeyEvent(QT_KEY_PRESS, key, QT_NO_MODIFIER, None)
        e_release = QtGui.QKeyEvent(QT_KEY_RELEASE, key, QT_NO_MODIFIER, None)
        QtCore.QCoreApplication.postEvent(QtWidgets.QApplication.focusWidget(), e_press)
        QtCore.QCoreApplication.postEvent(
            QtWidgets.QApplication.focusWidget(), e_release
        )

    def press_shift_tab(self):
        self.press_key(QT_KEY_BACKTAB)
        # self.stack_widget.currentWidget().focusPreviousChild()

    def press_tab(self):
        self.press_key(QT_KEY_TAB)
        # self.stack_widget.currentWidget().focusNextChild()

    def press_space(self):
        self.press_key(QT_KEY_SPACE)

    def scroll_next(self):
        self.signal_next_button.emit(1)

    def scroll_prev(self):
        self.signal_next_button.emit(-1)

    def enter_menu(self):
        i = self.stack_widget.currentIndex()
        if i == 1:
            # goto_menu:
            self.signal_menu_button.emit(self.gui_config.G_GUI_INDEX["Menu"])
        elif i >= 2:
            # back
            self.back_menu()

    def back_menu(self):
        self.signal_menu_back_button.emit()

    def change_mode(self):
        # check MAIN
        if self.stack_widget.currentIndex() != 1:
            return
        self.config.button_config.change_mode()

    def change_map_overlays(self):
        if self.map_widget is not None:
            self.signal_change_overlay.emit()

    def modify_map_tile(self):
        if self.map_widget is not None:
            self.signal_modify_map_tile.emit()

    def change_map_overlays_internal(self):
        self.map_widget.change_map_overlays()

    def modify_map_tile_internal(self):
        self.map_widget.modify_map_tile()

    def map_move_x_plus(self):
        self.map_method("move_x_plus")

    def map_move_x_minus(self):
        self.map_method("move_x_minus")

    def map_move_y_plus(self):
        self.map_method("move_y_plus")

    def map_move_y_minus(self):
        self.map_method("move_y_minus")

    def map_change_move(self):
        self.map_method("change_move")

    def map_zoom_plus(self):
        self.map_method("zoom_plus")

    def map_zoom_minus(self):
        self.map_method("zoom_minus")

    def map_search_route(self):
        self.map_method("search_route")

    def map_method(self, mode):
        w = self.main_page.widget(self.main_page.currentIndex())
        if w == self.map_widget:
            eval("w.signal_" + mode + ".emit()")
        elif w == self.course_profile_graph_widget:
            eval("w.signal_" + mode + ".emit()")

    def reset_course(self):
        self.map_widget.reset_course()
        if self.course_profile_graph_widget is not None:
            self.course_profile_graph_widget.reset_course()

    def init_course(self):
        self.map_widget.init_course()
        if self.course_profile_graph_widget is not None:
            self.course_profile_graph_widget.init_course()

    def scroll(self, delta):
        n = self.main_page.count()
        d = delta
        mod_index = self.main_page.currentIndex()
        while d != 0:
            mod_index = (mod_index + d + n) % n
            w = self.main_page.widget(mod_index)

            if (
                (
                    w == self.course_profile_graph_widget
                    and (
                        not self.config.logger.course.is_set
                        or not self.config.logger.course.has_altitude
                        or not self.config.G_COURSE_INDEXING
                    )
                )
                or (
                    w == self.cuesheet_widget
                    and (                
                            not self.config.logger.course.course_points.is_set
                            or not self.config.G_COURSE_INDEXING
                            or not self.config.G_CUESHEET_DISPLAY_NUM
                    ) 
                )
                or (
                    w == self.multi_scan_widget
                )
            ):
                d = delta
            else:
                d = 0

        self.on_change_main_page(mod_index)
        self.main_page.setCurrentIndex(mod_index)

    def multiscan(self):
        self.signal_multiscan.emit()

    def multiscan_internal(self):
        if self.multi_scan_widget is None:
            return
        if self.main_page.currentWidget() != self.multi_scan_widget:
            self.multiscan_back_index = self.main_page.currentIndex()
            self.on_change_main_page(self.multiscan_index)
            self.main_page.setCurrentIndex(self.multiscan_index)
        else:
            self.on_change_main_page(self.multiscan_back_index)
            self.main_page.setCurrentIndex(self.multiscan_back_index)

    def get_screenshot(self):
        self.signal_get_screenshot.emit()

    def screenshot(self):
        date = datetime.now()
        filename = date.strftime("%Y-%m-%d_%H-%M-%S.png")
        app_logger.info(f"screenshot: {filename}")
        p = self.stack_widget.grab()
        p.save(os.path.join(self.config.G_SCREENSHOT_DIR, filename), "png")
        self.config.display.screen_flash_short()

    def change_start_stop_button(self, status):
        if self.button_box_widget is not None:
            self.button_box_widget.change_start_stop_button(status)

    def brightness_control(self):
        self.config.display.change_brightness()

    def turn_on_off_light(self):
        self.signal_turn_on_off_light.emit()

    def turn_on_off_light_internal(self):
        self.config.logger.sensor.sensor_ant.set_light_mode("ON_OFF_FLASH_LOW")

    def change_menu_page(self, page, focus_reset=True):
        self.stack_widget.setCurrentIndex(page)
        # default focus, set only when has_touch is false
        focus_widget = getattr(self.stack_widget.widget(page), "focus_widget", None)
        if focus_widget:
            if focus_reset:
                focus_widget.setFocus()
        elif self.config.display.has_touch:
            # reset automatic focus there might not be one
            focus_widget = QtWidgets.QApplication.focusWidget()
            if focus_widget:
                focus_widget.clearFocus()

    def change_menu_back(self):
        self.stack_widget.currentWidget().back()

    def goto_menu(self):
        self.change_menu_page(self.gui_config.G_GUI_INDEX["Menu"])

    def delete_popup(self):
        if self.display_dialog:
            self.signal_menu_back_button.emit()

    def show_forced_message(self, msg):
        if self.dialog_exists():
            self.change_dialog(title=msg, button_label="OK")
        else:
            self.show_dialog_ok_only(None, msg)

    async def show_dialog_base(self, msg):
        if self.display_dialog:
            return

        title = msg.get("title")
        title_icon = msg.get("title_icon")  # QtGui.QIcon
        message = msg.get("message")
        button_num = msg.get("button_num", 0)  # 0: none, 1: OK, 2: OK+Cancel
        button_label = msg.get("button_label", None)  # button label for button_num = 1
        position = msg.get("position", QT_ALIGN_CENTER)
        text_align = msg.get("text_align", QT_ALIGN_CENTER)
        fn = msg.get("fn")  # use with OK button(button_num=2)

        default_timeout = 5
        timeout = msg.get("timeout", default_timeout)
        if timeout is None:
            timeout = default_timeout
            
        self.display_dialog = True

        class DialogButton(QtWidgets.QPushButton):
            next_button = None
            prev_button = None

            def focusNextPrevChild(self, is_next):
                if is_next:
                    self.next_button.setFocus()
                else:
                    self.prev_button.setFocus()
                return True

        class Container(QtWidgets.QWidget):
            pe_widget = None

            def showEvent(self, event):
                if not event.spontaneous():
                    self.setFocus()
                    QtCore.QTimer.singleShot(0, self.focusNextChild)

            def paintEvent(self, event):
                qp = QtWidgets.QStylePainter(self)
                opt = QtWidgets.QStyleOption()
                opt.initFrom(self)
                qp.drawPrimitive(self.pe_widget, opt)

        class DialogBackground(QtWidgets.QWidget):
            STYLES = """
              #background {
                /* transparent black */
                background-color: rgba(0, 0, 0, 64);
                /* transparent white */
                /*
                  background-color: rgba(255, 255, 255, 128);
                */
              }
              Container {
                border: 3px solid black;
                border-radius: 5px;
                padding: 10px;
              }
              Container DialogButton{
                border: 2px solid #AAAAAA;
                border-radius: 3px;
                text-align: center;
                padding: 3px;
              }
              Container DialogButton:pressed{background-color: black; }
              Container DialogButton:focus{background-color: black; color: white; }
            """

            def __init__(self, *__args):
                super().__init__(*__args, objectName="background")
                self.setStyleSheet(self.STYLES)

        def back():
            if not self.display_dialog:
                return
            self.close_dialog(self.stack_widget_current_index)
            background.deleteLater()

        self.stack_widget_current_index = self.stack_widget.currentIndex()
        self.stack_widget.layout().setStackingMode(QT_STACKINGMODE_STACKALL)

        background = DialogBackground(self.stack_widget)
        background.back = back
        back_layout = QtWidgets.QVBoxLayout(background)
        container = Container(background)
        container.pe_widget = QT_PE_WIDGET

        # position
        back_layout.addWidget(container, alignment=position)
        container.setAutoFillBackground(True)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setSpacing(0)

        font = self.main_window.font()
        font_size = font.pointSize()
        font.setPointSize(int(font_size * 2))
        title_label = QtWidgets.QLabel(title, font=font, objectName="title_label")
        # title_label = MarqueeLabel(config=self.config)
        title_label.setWordWrap(True)
        title_label.setText(title)
        title_label.setAlignment(text_align)
        title_label.setFont(font)
        title_label.setContentsMargins(5, 5, 5, 5)

        # title_label_width = title_label.fontMetrics().horizontalAdvance(title_label.text())

        # title_icon
        if title_icon is not None:
            outer_widget = QtWidgets.QWidget(container)
            left_icon = QtWidgets.QLabel()
            left_icon.setPixmap(title_icon.pixmap(QtCore.QSize(32, 32)))
            title_label.setAlignment(QT_ALIGN_LEFT)

            label_layout = QtWidgets.QHBoxLayout(outer_widget)
            label_layout.setContentsMargins(0, 0, 0, 0)
            label_layout.setSpacing(0)
            label_layout.addWidget(left_icon)
            label_layout.addWidget(title_label, stretch=2)
            layout.addWidget(outer_widget)
        elif message is not None:
            outer_widget = QtWidgets.QWidget(container)
            font.setPointSize(int(font_size * 1.5))
            title_label.setFont(font)
            title_label.setStyleSheet("font-weight: bold;")
            message_label = QtWidgets.QLabel(message, font=font)
            message_label.setAlignment(text_align)
            message_label.setWordWrap(True)
            message_label.setContentsMargins(5, 5, 5, 5)

            label_layout = QtWidgets.QVBoxLayout(outer_widget)
            label_layout.setContentsMargins(0, 0, 0, 0)
            label_layout.setSpacing(0)
            label_layout.addWidget(title_label)
            label_layout.addWidget(message_label)
            layout.addWidget(outer_widget)
        else:
            layout.addWidget(title_label)

        # timeout
        if button_num == 0:
            QtCore.QTimer.singleShot(timeout * 1000, back)
        # button_num
        elif button_num > 0:
            button_widget = QtWidgets.QWidget(container)
            button_layout = QtWidgets.QHBoxLayout(button_widget)
            button_layout.setContentsMargins(5, 10, 5, 10)
            button_layout.setSpacing(10)
            if not button_label:
                button_label = ["OK", "Cancel"]
            buttons = []

            for i in range(button_num):
                b = DialogButton(text=button_label[i], parent=button_widget)
                b.setFixedWidth(70)
                button_layout.addWidget(b)
                buttons.append(b)

            for i in range(button_num):
                next_index = i + 1
                prev_index = i - 1
                if next_index == button_num:
                    next_index = 0
                buttons[i].next_button = buttons[next_index]
                buttons[i].prev_button = buttons[prev_index]
                buttons[i].clicked.connect(
                    lambda: self.close_dialog(self.stack_widget_current_index)
                )
                buttons[i].clicked.connect(background.deleteLater)

            # func with OK button
            if fn is not None:
                buttons[0].clicked.connect(fn)

            layout.addWidget(button_widget)

        self.main_window.centralWidget().addWidget(background)
        self.main_window.centralWidget().setCurrentWidget(background)

    def change_dialog(self, title=None, button_label=None):
        if title:
            title_label = (
                self.main_window.centralWidget()
                .currentWidget()
                .findChild(QtWidgets.QLabel, "title_label")
            )
            if title_label:
                title_label.setText(title)
        if button_label:
            button = (
                self.main_window.centralWidget()
                .currentWidget()
                .findChild(QtWidgets.QPushButton)
            )
            if button:
                button.setText(button_label)

    def dialog_exists(self):
        return (
            self.main_window.centralWidget().currentWidget().objectName()
            == "background"
        )

    def close_dialog(self, index):
        self.stack_widget.layout().setStackingMode(QT_STACKINGMODE_STACKONE)
        self.stack_widget.setCurrentIndex(index)
        self.display_dialog = False
        self.msg_event.set()
