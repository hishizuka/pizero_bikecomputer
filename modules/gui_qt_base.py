import os
import signal
import asyncio

import numpy as np

from modules.app_logger import app_logger
from modules.gui_config import GUI_Config
from modules._qt_ver import (
    QtMode,
    USE_PYSIDE6,
    QT_PACKAGE,
)
import importlib

if QtMode == "QML":
    _qt_import = importlib.import_module("modules.qml.backend.qt")
else:
    _qt_import = importlib.import_module(f"modules._qt_{QtMode.lower()}")
QT_ALIGN_BOTTOM = _qt_import.QT_ALIGN_BOTTOM
QT_ALIGN_LEFT = _qt_import.QT_ALIGN_LEFT
QT_FORMAT_MONO = _qt_import.QT_FORMAT_MONO
QT_FORMAT_RGB888 = _qt_import.QT_FORMAT_RGB888
QT_COLOR_BLACK = _qt_import.QT_COLOR_BLACK
QtCore = _qt_import.QtCore
QtGui = _qt_import.QtGui
qasync = _qt_import.qasync
del _qt_import


class GUI_Qt_Base(QtCore.QObject):

    config = None
    gui_config = None
    app = None

    # for draw_display
    image_format = None
    screen_shape = None
    screen_image = None
    bufsize = 0
    bytes_per_line = 0
    _view_strides = None
    _needs_ptr_resize = False
    display_active = False
    _render_widget = None
    _display_has_color = True

    horizontal = True

    @property
    def logger(self):
        return self.config.logger

    @property
    def sensor(self):
        return self.logger.sensor

    @property
    def course(self):
        return self.logger.course

    # need override
    @property
    def grab_func(self):
        return None

    def set_render_widget(self, widget):
        self._render_widget = widget

    def get_button_mode(self):
        """Return a button profile page, or None for backend-specific resolution."""
        return None

    course_profile_graph_widget = None

    @property
    def current_navigation_page(self):
        return None

    @property
    def current_map_page(self):
        return None

    def reset_count_internal(self):
        result = self.logger.reset_count()
        if result:
            self.config.map.reset_track()
        return result

    def reset_map(self):
        self.config.map.reset_map()

    def refresh_map(self):
        self.config.map.notify("refresh_map")

    def reset_course(self):
        self.config.map.notify("reset_course")
        if self.course_profile_graph_widget is not None:
            self.course_profile_graph_widget.reset_course()

    def init_course(self):
        self.config.map.notify("init_course")
        if self.course_profile_graph_widget is not None:
            self.course_profile_graph_widget.init_course()

    def set_external_instruction(self, instruction_name, instruction_distance):
        self.config.map.set_external_instruction(instruction_name, instruction_distance)

    def clear_external_instruction(self):
        self.config.map.clear_external_instruction()

    def call_map(self, method, *args):
        handler = getattr(self.current_map_page, method, None)
        if callable(handler):
            handler(*args)

    def map_method(self, mode):
        page = self.current_navigation_page
        if page is not self.course_profile_graph_widget:
            page = self.current_map_page
        signal = getattr(page, f"signal_{mode}", None)
        if signal is not None:
            signal.emit()

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

    def change_map_overlays(self):
        self.call_map("change_map_overlays")

    def map_overlay_prev_time(self):
        self.call_map("update_overlay_time", False)

    def map_overlay_next_time(self):
        self.call_map("update_overlay_time", True)

    def __init__(self, config):
        super().__init__()
        app_logger.info(f"Qt version: {QtCore.QT_VERSION_STR} ({QT_PACKAGE})")

        self.config = config
        self.config.gui = self
        self._quit_requested = False
        self.msg_queue = None

        self.gui_config = GUI_Config(config.G_LAYOUT_FILE)

        self.init_window()

    def _enqueue_msg(self, msg):
        asyncio.create_task(self.msg_queue.put(msg))

    async def delay_init(self):
        loop = asyncio.get_running_loop()
        try:

            def _request_quit():
                if self._quit_requested:
                    return
                self._quit_requested = True
                loop.create_task(self.quit())

            loop.add_signal_handler(signal.SIGTERM, _request_quit)
            loop.add_signal_handler(signal.SIGINT, _request_quit)
            loop.add_signal_handler(signal.SIGQUIT, _request_quit)
            loop.add_signal_handler(signal.SIGHUP, _request_quit)
        except:
            pass

    async def msg_worker(self):
        while True:
            msg = await self.msg_queue.get()
            if msg is None:
                break
            self.msg_queue.task_done()

            await self.show_dialog_base(msg)
            buzzer = self.config.buzzer
            buzzer_sound = msg.get("buzzer_sound", "beep")
            if buzzer is not None and buzzer_sound is not None:
                buzzer.play(buzzer_sound)

            # event set in close_dialog()
            await self.msg_event.wait()
            self.msg_event.clear()
            await asyncio.sleep(0.1)

    async def quit(self):
        self._quit_requested = True
        await self.config.quit()

    async def quit_internal(self):
        self._quit_requested = True
        self.config.map.notify("stop")
        await self.config.map.track.close()
        self.msg_event.set()
        await self.msg_queue.put(None)

    def exec(self):
        asyncio.run(self.config.start_coroutine(), loop_factory=qasync.QEventLoop)

    def _grab_in_target_format(self):
        """Grab current frame and convert only if format differs."""
        image = None
        if self._render_widget is not None and self.image_format is not None:
            image = self._render_widget_to_image()
        if image is None:
            image = self.grab_func
        if image is None:
            return None
        if self.image_format is None:
            return image
        if image.format() != self.image_format:
            return image.convertToFormat(self.image_format)
        return image

    def _render_widget_to_image(self):
        widget = self._render_widget
        if widget is None:
            return None
        width = widget.width()
        height = widget.height()
        if width <= 0 or height <= 0:
            return None
        resized = self._ensure_screen_image_capacity(width, height)
        if self.screen_image is None:
            return None
        # clear previous frame to avoid blending old content when reusing QImage buffer
        self.screen_image.fill(QT_COLOR_BLACK)
        painter = QtGui.QPainter()
        if not painter.begin(self.screen_image):
            painter.end()
            return None
        widget.render(painter, QtCore.QPoint())
        painter.end()
        if resized:
            self._update_buffer_geometry(self.screen_image)
        return self.screen_image

    def _ensure_screen_image_capacity(self, width, height):
        if self.image_format is None:
            return False
        if width <= 0 or height <= 0:
            return False
        needs_new = (
            self.screen_image is None
            or self.screen_image.width() != width
            or self.screen_image.height() != height
            or self.screen_image.format() != self.image_format
        )
        if needs_new:
            self.screen_image = QtGui.QImage(width, height, self.image_format)
        return needs_new

    def _update_buffer_geometry(self, image):
        self.bufsize = image.sizeInBytes()
        self.bytes_per_line = image.bytesPerLine()
        if self._display_has_color:
            self.screen_shape = (image.height(), image.width(), 3)
            self._view_strides = (
                self.bytes_per_line,
                3,
                1,
            )
        else:
            self.screen_shape = (image.height(), int(image.width() / 8), 1)
            self._view_strides = (
                self.bytes_per_line,
                1,
                1,
            )

    def init_buffer(self, display):
        self.display_active = False
        if not display.send:
            return

        has_color = display.has_color
        self._display_has_color = has_color

        # set image format
        if has_color:
            self.image_format = QT_FORMAT_RGB888
        else:
            self.image_format = QT_FORMAT_MONO

        p = self._grab_in_target_format()
        if p is None:
            return

        self._update_buffer_geometry(p)

        self._needs_ptr_resize = not USE_PYSIDE6

        self.display_active = True

    def add_font(self):
        # Additional font from setting.conf
        if self.config.G_FONT_FILE:
            # use full path as macOS is not allowing relative paths
            res = QtGui.QFontDatabase.addApplicationFont(
                os.path.join(os.getcwd(), "fonts", self.config.G_FONT_FILE)
            )
            if res != -1:
                font_name = QtGui.QFontDatabase.applicationFontFamilies(res)[0]
                font = QtGui.QFont(font_name)
                self.app.setFont(font)
                app_logger.info(f"add font: {font_name}")

    def draw_display(self, direct_update=False):
        self.check_resolution()
        if not self.bufsize:
            return

        # self.config.check_time("draw_display start")
        p = self._grab_in_target_format()
        if p is None:
            return

        # self.config.check_time("grab")
        ptr = p.constBits()

        if ptr is None:
            return

        self.screen_image = p
        if self._needs_ptr_resize:
            ptr.setsize(self.bufsize)

        src = np.frombuffer(ptr, dtype=np.uint8, count=self.bufsize)
        buf = np.lib.stride_tricks.as_strided(
            src,
            shape=self.screen_shape,
            strides=self._view_strides,
        )

        self.config.display.update(buf, direct_update)
        # self.config.check_time("draw_display end")

    def show_popup(
        self,
        title,
        timeout=None,
        buzzer_sound="beep",
        background_color="white",
        text_color="black",
        alert_level=None,
    ):
        self._enqueue_msg(
            {
                "title": title,
                "button_num": 0,
                "position": QT_ALIGN_BOTTOM,
                "timeout": timeout,
                "buzzer_sound": buzzer_sound,
                "background_color": background_color,
                "text_color": text_color,
                "alert_level": alert_level,
            }
        )

    def show_qzss_alert(self, event, weather_pairs=None):
        self._enqueue_msg(
            {
                "title": "QZSS",
                "layout": "qzss",
                "event": event,
                "weather_pairs": weather_pairs,
                "timeout": 10,
                "buzzer_sound": "alert" if event["priority"] == "urgent" else "beep",
            }
        )

    def show_rain_alert(self, message, color):
        from modules.pyqt.components.icons import UmbrellaIcon

        self._enqueue_msg(
            {
                "title": message,
                "title_icon": UmbrellaIcon(color),
                "frame": "banner",
                "layout": "rain",
                "button_num": 1,
                "button_label": ["OK"],
                "position": QT_ALIGN_BOTTOM,
                "timeout": 10,
                "buzzer_sound": "beep",
                "background_color": "black",
                "text_color": "white",
            }
        )

    def show_popup_multiline(
        self,
        title,
        message,
        timeout=None,
        buzzer_sound="beep",
        background_color="white",
        text_color="black",
        alert_level=None,
        frame=None,
        title_icon=None,
    ):
        self._enqueue_msg(
            {
                "title": title,
                "frame": frame,
                "title_icon": title_icon,
                "message": message,
                "position": QT_ALIGN_BOTTOM,
                "text_align": QT_ALIGN_LEFT,
                "timeout": timeout,
                "buzzer_sound": buzzer_sound,
                "background_color": background_color,
                "text_color": text_color,
                "alert_level": alert_level,
            }
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
        self._enqueue_msg(
            {
                "title": t,
                "message": m,
                "button_num": 1,
                "position": QT_ALIGN_BOTTOM,
                "text_align": QT_ALIGN_LEFT,
            }
        )

    def show_forced_message(self, msg):
        pass

    def show_dialog(self, fn, title):
        self._enqueue_msg({"fn": fn, "title": title, "button_num": 2})

    def show_dialog_ok_only(self, fn, title, buzzer_sound="beep", button_label="OK"):
        self._enqueue_msg(
            {
                "fn": fn,
                "title": title,
                "button_num": 1,
                "button_label": [button_label],
                "buzzer_sound": buzzer_sound,
            }
        )

    def show_dialog_cancel_only(self, fn, title):
        self._enqueue_msg(
            {
                "fn": fn,
                "title": title,
                "button_num": 1,
                "button_label": ["Cancel"],
            }
        )

    def _run_gadgetbridge_action(self, action_name):
        ble_uart = self.config.ble_uart
        if ble_uart is None or not ble_uart.status:
            return False
        action = getattr(ble_uart, action_name)
        loop = getattr(self.config, "_loop", None)
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(action)
        else:
            action()
        return True

    def gadgetbridge_google_assistant(self):
        return self._run_gadgetbridge_action("start_google_assistant")

    def gadgetbridge_termux_voice_command(self):
        return self._run_gadgetbridge_action("start_termux_voice_command")

    async def show_dialog_base(self, msg):
        pass

    def change_dialog(self, title=None, button_label=None):
        pass
