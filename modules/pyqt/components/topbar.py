from modules._pyqt import QT_ALIGN_CENTER, QtCore, QtWidgets

from .icons import BackIcon, ForwardIcon
from .navi_button import NaviButton


# for some weird reason, inheriting from QtWidgets.QWidget is not working
# (styles are not applied, neither on Qt5 nor Qt6)
class TopBar:
    STYLES = """
      background-color: #00AA00
    """

    def __new__(cls, *args, **kwargs):
        instance = QtWidgets.QWidget(*args, **kwargs)
        instance.setStyleSheet(cls.STYLES)
        return instance


class TopBarLabel(QtWidgets.QLabel):
    def __init__(self, font_size, *__args):
        super().__init__(*__args)
        self.setAlignment(QT_ALIGN_CENTER)
        self.setStyleSheet(f"color: #FFFFFF; padding-right: 42.5px; font-size: {font_size}px;")


class TopBarBackButton(NaviButton):
    def __init__(self, size, *args):
        super().__init__(BackIcon(color="white"), "", *args)
        self.setIconSize(QtCore.QSize(20, 20))
        self.setProperty("style", "menu")
        self.setFixedSize(*size)


class TopBarNextButton(NaviButton):
    def __init__(self, size, *args):
        super().__init__(ForwardIcon(color="white"), "", *args)
        self.setIconSize(QtCore.QSize(20, 20))
        self.setProperty("style", "menu")
        self.setFixedSize(*size)
