from modules._pyqt import (
    QT_ALIGN_RIGHT,
    QT_EXPANDING,
    QtCore,
    QtWidgets,
    QtGui,
)
from modules.pyqt.components import icons

#################################
# Menu
#################################

MENU_BUTTON_ICON_MAP = {
    "submenu": icons.MenuRightIcon,
    "toggle": icons.MenuToggleIcon,
    "cloud_upload": icons.MenuCloudUploadIcon,
    "background_task": icons.MenuBackgroundIcon,
}


class MenuButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton{
        border-color: #AAAAAA;
        border-style: outset;
        border-width: 0px 1px 1px 0px;
        text-align: left;
        padding-left: 15%;
      }
      QPushButton:pressed{background-color: black; }
      QPushButton:focus{background-color: black; color: white; }
      QPushButton[style='connect']{
        text-align: center;
        padding-left: 0;
        border-width: 1px 0px 0px 0px;
        border-style: solid;
      }
      QPushButton[style='dummy']{ border-width: 0px; }
      QPushButton[style='unavailable']{ color: #AAAAAA; }
    """
    config = None
    button_type = None
    status = False

    res_img = {
        True: QtGui.QIcon("img/cloud_upload_done.svg"),
        False: QtGui.QIcon("img/button_warning.svg"),
    }

    loading_result = False

    def __init__(self, button_type, text, config, icon=None):
        # if icon is passed, no text is used
        super().__init__(text=text if not icon else "")

        self.config = config
        self.button_type = button_type

        self.setMinimumHeight(40)
        self.setMaximumHeight(50)
        self.setSizePolicy(
            QT_EXPANDING,
            QT_EXPANDING,
        )
        self.setStyleSheet(self.STYLES)

        if icon:
            qt_icon, size = icon
            self.setIcon(qt_icon)
            self.setIconSize(QtCore.QSize(*size))

        if MENU_BUTTON_ICON_MAP.get(button_type):
            self.set_icon_with_size()
            if button_type in ["cloud_upload", "background_task"]:
                self.init_loading_icon()

        # TODO we should remove this but that's for later
        if button_type == "dummy":
            self.setEnabled(False)
            self.setProperty("style", "dummy")

    def set_icon_with_size(self):
        icon_layout = QtWidgets.QHBoxLayout(self)
        self.right_icon = MENU_BUTTON_ICON_MAP[self.button_type]()
        icon_layout.addWidget(self.right_icon, alignment=QT_ALIGN_RIGHT)
        icon_layout.setContentsMargins(0, 0, self.right_icon.margin, 0)

    def onoff_button(self, status):
        if status:
            self.enable()
        else:
            self.disable()
        self.setStyleSheet(self.STYLES)

    def disable(self):
        self.setEnabled(False)
        self.setProperty("style", "unavailable")

    def enable(self):
        self.setEnabled(True)
        self.setProperty("style", None)

    def resizeEvent(self, event):
        h = self.size().height()

        # NOTE: why x > 0 else 1? is there an undocumented edge case?
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

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self.button_type == "submenu" or (
            self.button_type == "toggle" and not self.status
        ):
            self.change_icon_with_hover(False)

    def change_icon_with_hover(self, hover):
        self.right_icon.hover(hover)

    def change_toggle(self, status):
        self.status = status
        self.right_icon.toggle(status, self.hasFocus())

    @QtCore.pyqtSlot()
    def loading_start(self):
        if not self.status:
            self.status = True
            self.loading_movie.start()

    @QtCore.pyqtSlot()
    def loading_stop(self, res):
        self.loading_movie.stop()
        self.right_icon.set_icon(self.res_img[res])
        self.status = False

    def init_loading_icon(self):
        self.loading_result = False
        self.loading_movie = QtGui.QMovie(self)
        self.loading_movie.setFileName("img/loading.gif")
        self.loading_movie.frameChanged.connect(self.on_frameChanged)
        if self.loading_movie.loopCount() != -1:
            self.loading_movie.finished.connect(self.start)

    @QtCore.pyqtSlot(int)
    def on_frameChanged(self, frameNumber):
        self.right_icon.set_icon(QtGui.QIcon(self.loading_movie.currentPixmap()))

    async def run(self, func):
        if self.status:
            return

        self.loading_start()
        self.loading_result = await func()
        self.loading_stop(self.loading_result)
