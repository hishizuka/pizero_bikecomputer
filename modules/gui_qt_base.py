import os
import signal
import asyncio
from datetime import datetime, timezone

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
    remove_bytes = 0
    bufsize = 0

    @property
    def logger(self):
        return self.config.logger

    # need override
    @property
    def grab_func(self):
        return None

    def __init__(self, config):
        super().__init__()
        app_logger.info(f"Qt version: {QtCore.QT_VERSION_STR} ({QT_PACKAGE})")

        self.config = config
        self.config.gui = self

        self.gui_config = GUI_Config(config.G_LAYOUT_FILE)

        try:
            signal.signal(signal.SIGTERM, self.quit_by_ctrl_c)
            signal.signal(signal.SIGINT, self.quit_by_ctrl_c)
            signal.signal(signal.SIGQUIT, self.quit_by_ctrl_c)
            signal.signal(signal.SIGHUP, self.quit_by_ctrl_c)
        except:
            pass

        self.init_window()

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

    @qasync.asyncSlot(object, object)
    async def quit_by_ctrl_c(self, signal, frame):
        await self.quit()
    
    async def quit(self):
        self.msg_event.set()
        await self.msg_queue.put(None)
        await self.config.quit()

        # with loop.close, so execute at the end
        # not need PyQt 6.7
        #self.app.quit()
    
    def exec(self):
        with self.config.loop:
            self.config.loop.run_forever()
            # loop is stopped
        # loop is closed

    def init_buffer(self, display):
        if display.send:
            has_color = display.has_color

            # set image format
            if has_color:
                self.image_format = QT_FORMAT_RGB888
            else:
                self.image_format = QT_FORMAT_MONO

            p = self.grab_func.convertToFormat(self.image_format)

            self.bufsize = p.sizeInBytes()  # PyQt 5.15 or later (Bullseye)

            if has_color:
                self.screen_shape = (p.height(), p.width(), 3)
            else:
                self.screen_shape = (p.height(), int(p.width() / 8), 1)
                self.remove_bytes = p.bytesPerLine() - int(p.width() / 8)

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
        if not self.bufsize:
            return

        # self.config.check_time("draw_display start")
        p = self.grab_func.convertToFormat(self.image_format)

        if self.screen_image is not None and p == self.screen_image:
            return

        # self.config.check_time("grab")
        ptr = p.constBits()

        if ptr is None:
            return

        self.screen_image = p
        if not USE_PYSIDE6:  # PyQt only
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