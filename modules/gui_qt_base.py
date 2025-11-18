import os
import sys
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
_qt_import = importlib.import_module(f"modules._qt_{QtMode.lower()}")
QT_ALIGN_BOTTOM = _qt_import.QT_ALIGN_BOTTOM
QT_ALIGN_LEFT = _qt_import.QT_ALIGN_LEFT
QT_FORMAT_MONO = _qt_import.QT_FORMAT_MONO
QT_FORMAT_RGB888 = _qt_import.QT_FORMAT_RGB888
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

    # need override
    @property
    def grab_func(self):
        return None

    def set_render_widget(self, widget):
        self._render_widget = widget

    def __init__(self, config):
        super().__init__()
        app_logger.info(f"Qt version: {QtCore.QT_VERSION_STR} ({QT_PACKAGE})")

        self.config = config
        self.config.gui = self

        self.gui_config = GUI_Config(config.G_LAYOUT_FILE)

        self.init_window()

    async def delay_init(self):
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGTERM, self.app.quit)
            loop.add_signal_handler(signal.SIGINT, self.app.quit)
            loop.add_signal_handler(signal.SIGQUIT, self.app.quit)
            loop.add_signal_handler(signal.SIGHUP, self.app.quit)
        except:
            pass

    async def msg_worker(self):
        while True:
            msg = await self.msg_queue.get()
            if msg is None:
                break
            self.msg_queue.task_done()

            await self.show_dialog_base(msg)

            # event set in close_dialog()
            await self.msg_event.wait()
            self.msg_event.clear()
            await asyncio.sleep(0.1)
    
    async def quit(self):
        self.msg_event.set()
        await self.msg_queue.put(None)
        await self.config.quit()
    
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

    def show_popup(self, title, timeout=None):
        asyncio.create_task(
            self.msg_queue.put(
                {
                    "title": title,
                    "button_num": 0,
                    "position": QT_ALIGN_BOTTOM,
                    "timeout": timeout,
                }
            )
        )

    def show_popup_multiline(self, title, message, timeout=None):
        asyncio.create_task(
            self.msg_queue.put(
                {
                    "title": title,
                    "message": message,
                    "position": QT_ALIGN_BOTTOM,
                    "text_align": QT_ALIGN_LEFT,
                    "timeout": timeout,
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
                    "position": QT_ALIGN_BOTTOM,
                    "text_align": QT_ALIGN_LEFT,
                }
            )
        )

    def show_forced_message(self, msg):
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
        pass
    
    def change_dialog(self, title=None, button_label=None):
        pass
