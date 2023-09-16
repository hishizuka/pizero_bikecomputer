import sys
import os

# import platform
import datetime
import signal
import asyncio
import numpy as np

USE_PYQT6 = False
try:
    import PyQt6.QtCore as QtCore
    import PyQt6.QtWidgets as QtWidgets
    import PyQt6.QtGui as QtGui

    USE_PYQT6 = True
except:
    import PyQt5.QtCore as QtCore
    import PyQt5.QtWidgets as QtWidgets
    import PyQt5.QtGui as QtGui

import qasync

from modules.gui_config import GUI_Config
from modules.pyqt.pyqt_style import PyQtStyle


class MyWindow(QtWidgets.QMainWindow):
    config = None
    gui = None

    def __init__(self, parent=None):
        # super().__init__(parent, flags=QtCore.Qt.FramelessWindowHint)
        super().__init__(parent=parent)
        print("Qt version:", QtCore.QT_VERSION_STR)

    def set_config(self, config):
        self.config = config

    def set_gui(self, gui):
        self.gui = gui

    # override from QtWidget
    @qasync.asyncClose
    async def closeEvent(self, event):
        # await self.config.quit()
        await self.config.gui.quit()

    # override from QtWidget
    def paintEvent(self, event):
        if self.gui != None:
            self.gui.draw_display()


class GUI_PyQt(QtCore.QObject):
    config = None
    gui_config = None
    logger = None
    app = None
    style = None

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
    signal_next_button = QtCore.pyqtSignal(int)
    signal_prev_button = QtCore.pyqtSignal(int)
    signal_menu_button = QtCore.pyqtSignal(int)
    signal_menu_back_button = QtCore.pyqtSignal()
    signal_get_screenshot = QtCore.pyqtSignal()
    signal_start_and_stop_manual = QtCore.pyqtSignal()
    signal_count_laps = QtCore.pyqtSignal()
    signal_boot_status = QtCore.pyqtSignal(str)
    signal_draw_display = QtCore.pyqtSignal()

    # for draw_display
    screen_shape = None
    screen_image = None
    remove_bytes = 0
    old_pyqt = False
    bufsize = 0

    # for dialog
    display_dialog = False

    def __init__(self, config):
        super().__init__()

        self.config = config
        self.config.gui = self

        self.gui_config = GUI_Config(config)
        self.gui_config.set_qt5_or_qt6_constants(USE_PYQT6)

        self.style = PyQtStyle()
        self.logger = self.config.logger
        try:
            signal.signal(signal.SIGTERM, self.quit_by_ctrl_c)
            signal.signal(signal.SIGINT, self.quit_by_ctrl_c)
            signal.signal(signal.SIGQUIT, self.quit_by_ctrl_c)
            signal.signal(signal.SIGHUP, self.quit_by_ctrl_c)
        except:
            pass

        self.init_window()

    def init_window(self):
        self.app = QtWidgets.QApplication(sys.argv)
        self.config.loop = qasync.QEventLoop(self.app)
        self.config.loop.set_debug(True)
        self.config.init_loop(call_from_gui=True)

        self.main_window = MyWindow()
        self.main_window.set_config(self.config)
        self.main_window.set_gui(self)
        self.main_window.setWindowTitle(self.config.G_PRODUCT)
        self.main_window.setMinimumSize(self.config.G_WIDTH, self.config.G_HEIGHT)
        self.main_window.show()
        self.set_color()

        self.stack_widget = QtWidgets.QStackedWidget(self.main_window)
        self.main_window.setCentralWidget(self.stack_widget)
        self.stack_widget.setContentsMargins(0, 0, 0, 0)

        # stack_widget elements (splash)
        self.splash_widget = QtWidgets.QWidget(self.stack_widget)
        self.splash_widget.setContentsMargins(0, 0, 0, 0)
        self.stack_widget.addWidget(self.splash_widget)

        self.splash_layout = QtWidgets.QVBoxLayout(self.splash_widget)
        self.splash_layout.setContentsMargins(0, 0, 0, 0)
        self.splash_layout.setSpacing(0)
        self.splash_widget.setStyleSheet(self.style.G_GUI_PYQT_splash_screen)

        # self.splash_image = QtWidgets.QLabel()
        # self.splash_image.setPixmap(QtGui.QPixmap("some_logo.png"))
        # self.splash_layout.addWidget(self.splash_image)

        self.boot_status = QtWidgets.QLabel()
        self.signal_boot_status.connect(self.set_boot_status_internal)
        self.boot_status.setStyleSheet(self.style.G_GUI_PYQT_splash_boot_text)
        self.boot_status.setAlignment(self.gui_config.align_center)
        self.splash_layout.addWidget(self.boot_status)

        # for draw_display
        self.init_buffer()

        self.exec()

    async def set_boot_status(self, text):
        self.signal_boot_status.emit(text)
        self.draw_display(direct_update=True)
        if not self.config.G_IS_RASPI:
            await asyncio.sleep(0.01)  # need for changing QLabel in the event loop

    def set_boot_status_internal(self, text):
        self.boot_status.setText(text)

    def delay_init(self):
        time_profile = []
        t1 = datetime.datetime.now()

        self.add_font()

        # navi icon
        self.navi_icon = {
            "Default": QtGui.QIcon("img/navi_flag.png"),  # svg
            "Left": QtGui.QIcon("img/navi_turn_left.svg"),
            "Right": QtGui.QIcon("img/navi_turn_right.svg"),
            "Summit": QtGui.QIcon("img/summit.png"),  # svg
        }

        # physical button
        self.signal_next_button.connect(self.scroll)
        self.signal_prev_button.connect(self.scroll)
        self.signal_menu_button.connect(self.change_menu_page)
        self.signal_menu_back_button.connect(self.change_menu_back)
        # other
        self.signal_get_screenshot.connect(self.screenshot)

        self.signal_start_and_stop_manual.connect(self.start_and_stop_manual_internal)
        self.signal_count_laps.connect(self.count_laps_internal)

        self.signal_draw_display.connect(self.draw_display)

        self.msg_queue = asyncio.Queue()
        self.msg_event = asyncio.Event()
        asyncio.create_task(self.msg_worker())

        t2 = datetime.datetime.now()
        time_profile.append((t2 - t1).total_seconds())
        t1 = t2

        import modules.pyqt.graph.pyqt_map as pyqt_map
        import modules.pyqt.graph.pyqt_course_profile as pyqt_course_profile
        import modules.pyqt.graph.pyqt_value_graph as pyqt_value_graph
        from modules.pyqt.pyqt_values_widget import ValuesWidget

        from modules.pyqt.menu.pyqt_menu_widget import (
            TopMenuWidget,
            LiveTrackMenuWidget,
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
            ANTMultiScanScreenWidget,
        )
        from modules.pyqt.menu.pyqt_course_menu_widget import (
            CoursesMenuWidget,
            CourseListWidget,
            CourseDetailWidget,
        )  # , GoogleDirectionsAPISettingMenuWidget
        from modules.pyqt.menu.pyqt_map_menu_widget import (
            MapMenuWidget,
            MapListWidget,
            MapOverlayMenuWidget,
            HeatmapListWidget,
            RainmapListWidget,
            WindmapListWidget,
        )
        from modules.pyqt.menu.pyqt_adjust_widget import (
            AdjustAltitudeWidget,
            AdjustWheelCircumferenceWidget,
            AdjustCPWidget,
            AdjustWPrimeBalanceWidget,
        )
        from modules.pyqt.pyqt_cuesheet_widget import CueSheetWidget

        t2 = datetime.datetime.now()
        time_profile.append((t2 - t1).total_seconds())
        t1 = t2

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
        self.main_widget = QtWidgets.QWidget(self.stack_widget)
        self.main_widget.setContentsMargins(0, 0, 0, 0)
        self.stack_widget.addWidget(self.main_widget)

        # reverse order (make children widget first, then make parent widget)
        menus = [
            ("ANT+ Detail", ANTListWidget),
            ("ANT+ MultiScan", ANTMultiScanScreenWidget),
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
            ("Live Track", LiveTrackMenuWidget),
            ("Upload Activity", UploadActivityMenuWidget),
            ("Wind map List", WindmapListWidget),
            ("Rain map List", RainmapListWidget),
            ("Heatmap List", HeatmapListWidget),
            ("Map Overlay", MapOverlayMenuWidget),
            ("Select Map", MapListWidget),
            ("Map", MapMenuWidget),
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

        # main layout
        self.main_layout = QtWidgets.QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # main Widget
        self.main_page = QtWidgets.QStackedWidget(self.main_widget)
        self.main_page.setContentsMargins(0, 0, 0, 0)

        for k in self.gui_config.G_LAYOUT:
            if not self.gui_config.G_LAYOUT[k]["STATUS"]:
                continue
            if "LAYOUT" in self.gui_config.G_LAYOUT[k]:
                self.main_page.addWidget(
                    ValuesWidget(
                        self.main_page,
                        self.config,
                        self.gui_config.G_LAYOUT[k]["LAYOUT"],
                    )
                )
            else:
                if (
                    k == "ALTITUDE_GRAPH"
                    and "i2c_baro_temp" in self.config.logger.sensor.sensor_i2c.sensor
                ):
                    self.altitude_graph_widget = pyqt_value_graph.AltitudeGraphWidget(
                        self.main_page, self.config
                    )
                    self.main_page.addWidget(self.altitude_graph_widget)
                elif (
                    k == "ACC_GRAPH"
                    and self.config.logger.sensor.sensor_i2c.motion_sensor["ACC"]
                ):
                    self.acc_graph_widget = pyqt_value_graph.AccelerationGraphWidget(
                        self.main_page, self.config
                    )
                    self.main_page.addWidget(self.acc_graph_widget)
                elif k == "PERFORMANCE_GRAPH" and self.config.G_ANT["STATUS"]:
                    self.performance_graph_widget = (
                        pyqt_value_graph.PerformanceGraphWidget(
                            self.main_page, self.config
                        )
                    )
                    self.main_page.addWidget(self.performance_graph_widget)
                elif (
                    k == "COURSE_PROFILE_GRAPH"
                    and os.path.exists(self.config.G_COURSE_FILE_PATH)
                    and self.config.G_COURSE_INDEXING
                ):
                    self.course_profile_graph_widget = (
                        pyqt_course_profile.CourseProfileGraphWidget(
                            self.main_page, self.config
                        )
                    )
                    self.main_page.addWidget(self.course_profile_graph_widget)
                elif k == "SIMPLE_MAP":
                    self.map_widget = pyqt_map.MapWidget(self.main_page, self.config)
                    self.main_page.addWidget(self.map_widget)
                elif (
                    k == "CUESHEET"
                    and len(self.config.logger.course.point_name) > 0
                    and self.config.G_COURSE_INDEXING
                    and self.config.G_CUESHEET_DISPLAY_NUM > 0
                ):
                    self.cuesheet_widget = CueSheetWidget(self.main_page, self.config)
                    self.main_page.addWidget(self.cuesheet_widget)

        t2 = datetime.datetime.now()
        time_profile.append((t2 - t1).total_seconds())
        t1 = t2

        # integrate main_layout
        self.main_layout.addWidget(self.main_page)
        if self.config.display.has_touch():
            # button
            from modules.pyqt.pyqt_button_box_widget import ButtonBoxWidget

            self.button_box_widget = ButtonBoxWidget(self.main_widget, self.config)
            self.main_layout.addWidget(self.button_box_widget)

        # fullscreen
        if self.config.G_FULLSCREEN:
            self.main_window.showFullScreen()

        self.on_change_main_page(self.main_page_index)

        t2 = datetime.datetime.now()
        time_profile.append((t2 - t1).total_seconds())

        print()
        print("Drawing components:")
        print("  misc  : {:.3f} sec".format(time_profile[0]))
        print("  import: {:.3f} sec".format(time_profile[1]))
        print("  init  : {:.3f} sec".format(time_profile[2]))
        print("  layout: {:.3f} sec".format(time_profile[3]))
        print("  total : {:.3f} sec".format(sum(time_profile)))
        print()

    def init_buffer(self):
        if self.config.display.send_display:
            p = (
                self.stack_widget.grab()
                .toImage()
                .convertToFormat(self.gui_config.format)
            )
            # PyQt 5.11(Buster) or 5.15(Bullseye)
            qt_version = (QtCore.QT_VERSION_STR).split(".")
            if qt_version[0] == "5" and int(qt_version[1]) < 15:
                self.bufsize = p.bytesPerLine() * p.height()  # PyQt 5.11(Buster)
            else:
                self.bufsize = p.sizeInBytes()  # PyQt 5.15 or lator (Bullseye)

            self.screen_shape, self.remove_bytes = self.gui_config.get_screen_shape(p)

    def exec(self):
        # self.app.exec()
        with self.config.loop:
            self.config.loop.run_forever()
            # loop is stopped
        # loop is closed

    def add_font(self):
        # default font (macOS is not allowed relative path)
        res = QtGui.QFontDatabase.addApplicationFont(
            "fonts/Yantramanav/Yantramanav-Black.ttf"
        )
        if res != -1:
            font_name = QtGui.QFontDatabase.applicationFontFamilies(res)[0]
            self.stack_widget.setStyleSheet("font-family: {}".format(font_name))
            print("add font:", font_name)

        # Additional font from setting.conf
        if self.config.G_FONT_FULLPATH != "":
            res = QtGui.QFontDatabase.addApplicationFont(self.config.G_FONT_FULLPATH)
            if res != -1:
                self.config.G_FONT_NAME = QtGui.QFontDatabase.applicationFontFamilies(
                    res
                )[0]
                # self.stack_widget.setStyleSheet("font-family: {}".format(self.config.G_FONT_NAME))
                print("add font:", self.config.G_FONT_NAME)

        # for macOS
        # if platform.system() == 'Darwin' and QtCore.QLocale.system().bcp47Name() == "ja":
        #  font = QtGui.QFont("Hiragino Sans") #or Osaka
        #  self.app.setFont(font)

    @qasync.asyncSlot(object, object)
    async def quit_by_ctrl_c(self, signal, frame):
        await self.quit()

    async def quit(self):
        self.msg_event.set()
        await self.msg_queue.put(None)
        await self.config.quit()

        # with loop.close, so execute at the end
        self.app.quit()

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
        self.logger.reset_count()
        self.map_widget.reset_track()

    def press_key(self, key):
        e_press = QtGui.QKeyEvent(
            self.gui_config.key_press, key, self.gui_config.no_modifier, None
        )
        e_release = QtGui.QKeyEvent(
            self.gui_config.key_release, key, self.gui_config.no_modifier, None
        )
        QtCore.QCoreApplication.postEvent(QtWidgets.QApplication.focusWidget(), e_press)
        QtCore.QCoreApplication.postEvent(
            QtWidgets.QApplication.focusWidget(), e_release
        )

    def press_shift_tab(self):
        self.press_key(QtCore.Qt.Key_Backtab)
        # self.stack_widget.currentWidget().focusPreviousChild()

    def press_tab(self):
        self.press_key(QtCore.Qt.Key_Tab)
        # self.stack_widget.currentWidget().focusNextChild()

    def press_space(self):
        self.press_key(self.gui_config.key_space)

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
        self.config.change_mode()

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
        if self.course_profile_graph_widget != None:
            self.course_profile_graph_widget.reset_course()

    def init_course(self):
        self.map_widget.init_course()
        if self.course_profile_graph_widget != None:
            self.course_profile_graph_widget.init_course()

    def change_color_low(self):
        if (
            self.config.G_DITHERING_CUTOFF_LOW_INDEX
            == len(self.config.G_DITHERING_CUTOFF["LOW"]) - 1
        ):
            self.config.G_DITHERING_CUTOFF_LOW_INDEX = 0
        else:
            self.config.G_DITHERING_CUTOFF_LOW_INDEX += 1
        self.signal_draw_display.emit()
        print(
            "LOW:",
            self.config.G_DITHERING_CUTOFF["LOW"][
                self.config.G_DITHERING_CUTOFF_LOW_INDEX
            ],
        )

    def change_color_high(self):
        if (
            self.config.G_DITHERING_CUTOFF_HIGH_INDEX
            == len(self.config.G_DITHERING_CUTOFF["HIGH"]) - 1
        ):
            self.config.G_DITHERING_CUTOFF_HIGH_INDEX = 0
        else:
            self.config.G_DITHERING_CUTOFF_HIGH_INDEX += 1
        self.signal_draw_display.emit()
        print(
            "HIGH:",
            self.config.G_DITHERING_CUTOFF["HIGH"][
                self.config.G_DITHERING_CUTOFF_HIGH_INDEX
            ],
        )

    def dummy(self):
        pass

    def scroll(self, delta):
        mod_index = (
            self.main_page.currentIndex() + delta + self.main_page.count()
        ) % self.main_page.count()
        self.on_change_main_page(mod_index)
        self.main_page.setCurrentIndex(mod_index)

    def get_screenshot(self):
        self.signal_get_screenshot.emit()

    def screenshot(self):
        date = datetime.datetime.now()
        filename = date.strftime("%Y-%m-%d_%H-%M-%S.png")
        print("screenshot:", filename)
        p = self.stack_widget.grab()
        p.save(self.config.G_SCREENSHOT_DIR + filename, "png")

    def draw_display(self, direct_update=False):
        if not self.config.display.send_display or self.stack_widget == None:
            return

        # self.config.check_time("draw_display start")
        p = self.stack_widget.grab().toImage().convertToFormat(self.gui_config.format)

        # self.config.check_time("grab")
        ptr = p.constBits()
        if ptr == None:
            return

        if self.screen_image != None and p == self.screen_image:
            return
        self.screen_image = p

        ptr.setsize(self.bufsize)

        if self.remove_bytes > 0:
            buf = np.frombuffer(ptr, dtype=np.uint8).reshape(
                (p.height(), self.remove_bytes + int(p.width() / 8))
            )
            buf = buf[:, : -self.remove_bytes]
        else:
            buf = np.frombuffer(ptr, dtype=np.uint8).reshape(self.screen_shape)

        self.config.display.update(buf, direct_update)
        # self.config.check_time("draw_display end")

    def change_start_stop_button(self, status):
        if self.button_box_widget != None:
            self.button_box_widget.change_start_stop_button(status)

    def brightness_control(self):
        self.config.display.brightness_control()

    def turn_on_off_light(self):
        self.config.logger.sensor.sensor_ant.set_light_mode("ON_OFF_FLASH_LOW")

    def change_menu_page(self, page, focus_reset=True):
        self.stack_widget.setCurrentIndex(page)
        # default focus
        if not self.config.display.has_touch() and hasattr(
            self.stack_widget.widget(page), "focus_widget"
        ):
            if focus_reset and self.stack_widget.widget(page).focus_widget != None:
                self.stack_widget.widget(page).focus_widget.setFocus()

    def change_menu_back(self):
        self.stack_widget.currentWidget().back()

    def goto_menu(self):
        self.change_menu_page(self.gui_config.G_GUI_INDEX["Menu"])

    def set_color(self, daylight=True):
        if daylight:
            self.main_window.setStyleSheet("color: black; background-color: white")
        else:
            self.main_window.setStyleSheet("color: white; background-color: #222222")

    async def add_message_queue(self, title=None, message=None, fn=None):
        await self.msg_queue.put(message)

    async def msg_worker(self):
        while True:
            msg = await self.msg_queue.get()
            if msg == None:
                break
            self.msg_queue.task_done()

            await self.show_dialog_base(msg)

            # event set in close_dialog()
            await self.msg_event.wait()
            self.msg_event.clear()
            await asyncio.sleep(0.1)

    def delete_popup(self):
        if self.display_dialog:
            self.signal_menu_back_button.emit()

    def show_popup(self, title):
        asyncio.create_task(
            self.msg_queue.put(
                {
                    "title": title,
                    "button_num": 0,
                    "position": self.gui_config.align_bottom,
                }
            )
        )

    def show_popup_multiline(self, title, message):
        asyncio.create_task(
            self.msg_queue.put(
                {
                    "title": title,
                    "message": message,
                    "position": self.gui_config.align_bottom,
                    "text_align": self.gui_config.align_left,
                }
            )
        )

    def show_message(self, title, message, limit_length=False):
        t = title
        m = message

        if limit_length:
            width = 14
            w_t = width - 1
            w_m = 3 * width - 1

            if len(t) > w_t:
                t = t[0:w_t] + "..."
            if len(m) > w_m:
                m = m[0:w_m] + "..."
        asyncio.create_task(
            self.msg_queue.put(
                {
                    "title": t,
                    "message": m,
                    "button_num": 1,
                    "position": self.gui_config.align_bottom,
                    "text_align": self.gui_config.align_left,
                }
            )
        )
        # await self.config.logger.sensor.sensor_i2c.led_blink(5)

    def show_forced_message(self, msg):
        if self.dialog_exists():
            self.change_dialog(title=msg, button_label="OK")
        else:
            self.show_dialog_ok_only(None, msg)

    def show_navi_internal(self, title, title_icon=None):
        # self.show_dialog_base(title=title, title_icon=title_icon, button_num=0, position=self.gui_config.align_bottom)
        pass

    def show_dialog(self, fn, title):
        asyncio.create_task(
            self.msg_queue.put({"fn": fn, "title": title, "button_num": 2})
        )

    def show_dialog_ok_only(self, fn, title):
        asyncio.create_task(
            self.msg_queue.put(
                {"fn": fn, "title": title, "button_num": 1, "button_label": ["OK"]}
            )
        )

    def show_dialog_cancel_only(self, fn, title):
        asyncio.create_task(
            self.msg_queue.put(
                {"fn": fn, "title": title, "button_num": 1, "button_label": ["Cancel"]}
            )
        )

    async def show_dialog_base(self, msg):
        if self.display_dialog:
            return

        title = msg.get("title")
        title_icon = msg.get("title_icon")
        message = msg.get("message")
        button_num = msg.get("button_num", 0)  # 0: none, 1: OK, 2: OK+Cancel
        button_label = msg.get("button_label", None)  # button label for button_num = 1
        timeout = msg.get("timeout", 5)
        position = msg.get("position", self.gui_config.align_center)
        text_align = msg.get("text_align", self.gui_config.align_center)
        fn = msg.get("fn")  # use with OK button(button_num=2)

        self.display_dialog = True

        class DialogButton(QtWidgets.QPushButton):
            next_button = None
            prev_button = None

            def focusNextPrevChild(self, next):
                if next:
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

        def back():
            if not self.display_dialog:
                return
            self.close_dialog(self.stack_widget_current_index)
            background.deleteLater()

        self.stack_widget_current_index = self.stack_widget.currentIndex()
        self.stack_widget.layout().setStackingMode(
            self.gui_config.stackingmode_stackall
        )

        background = QtWidgets.QWidget(
            parent=self.stack_widget, objectName="background"
        )
        background.setStyleSheet(self.style.G_GUI_PYQT_dialog)
        background.back = back
        back_layout = QtWidgets.QVBoxLayout(background)
        container = Container(background)
        container.pe_widget = self.gui_config.PE_Widget

        # position
        back_layout.addWidget(container, alignment=position)
        container.setAutoFillBackground(True)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        font = self.main_window.font()
        fontsize = font.pointSize()
        font.setPointSize(int(fontsize * 2))
        title_label = QtWidgets.QLabel(title, font=font, objectName="title_label")
        # title_label = MarqueeLabel(config=self.config)
        title_label.setWordWrap(True)
        title_label.setText(title)
        title_label.setAlignment(text_align)
        title_label.setFont(font)

        # title_label_width = title_label.fontMetrics().horizontalAdvance(title_label.text())

        # title_icon
        if title_icon != None:
            outer_widget = QtWidgets.QWidget(container)

            left_icon = QtWidgets.QLabel()
            left_icon.setPixmap(title_icon.pixmap(QtCore.QSize(32, 32)))

            label_layout = QtWidgets.QHBoxLayout(outer_widget)
            label_layout.setContentsMargins(0, 0, 0, 0)
            label_layout.addWidget(left_icon)
            label_layout.addWidget(title_label, stretch=2)
            layout.addWidget(outer_widget)
        elif message != None:
            outer_widget = QtWidgets.QWidget(container)
            font.setPointSize(int(fontsize * 1.5))
            message_label = QtWidgets.QLabel(message, font=font)
            message_label.setAlignment(text_align)
            message_label.setWordWrap(True)
            title_label.setFont(font)
            title_label.setStyleSheet("font-weight: bold;")

            label_layout = QtWidgets.QVBoxLayout(outer_widget)
            label_layout.setContentsMargins(0, 0, 0, 0)
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
            if fn != None:
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
        self.stack_widget.layout().setStackingMode(
            self.gui_config.stackingmode_stackone
        )
        self.stack_widget.setCurrentIndex(index)
        self.display_dialog = False
        self.msg_event.set()
