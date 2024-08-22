from modules._qt_qtwidgets import QtWidgets
from .icons import BackIcon, ForwardIcon, NextIcon, LapIcon, MenuIcon
from .navi_button import NaviButton


class LapButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton {
        background-color: #FF0000;
        color: black;
        border-color: red;
        border-radius: 15px;
        border-style: outset;
        border-width: 0px;
      }

      QPushButton:pressed {
        background-color: white;
      }
    """

    def __init__(self, *args):
        super().__init__(LapIcon(), "", *args)
        self.setStyleSheet(self.STYLES)
        self.setFixedSize(50, 30)
        # long press
        self.setAutoRepeat(True)
        self.setAutoRepeatDelay(1000)
        self.setAutoRepeatInterval(1000)
        self._state = 0


class MenuButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton {
        color: none;
        border-color: none;
        border-radius: 2px;
        border-style: outset;
        border-width: 0px;
      }

      QPushButton:pressed {
        background-color: white;
      }
    """

    def __init__(self, *args):
        super().__init__(MenuIcon(), "", *args)
        self.setFixedSize(50, 30)
        self.setStyleSheet(self.STYLES)


class ScrollNextButton(NaviButton):
    def __init__(self, *args):
        super().__init__(ForwardIcon(), "", *args)
        self.setFixedSize(60, 30)


class ScrollPrevButton(NaviButton):
    def __init__(self, *args):
        super().__init__(BackIcon(), "", *args)
        self.setFixedSize(60, 30)


class StartButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton {
        background-color: #FF0000;
        color: black;
        border-color: red;
        border-radius: 15px;
        border-style: outset;
        border-width: 0px;
      }

      QPushButton:pressed {
        background-color: white;
      }
    """

    def __init__(self, *args):
        super().__init__(NextIcon(), "", *args)
        self.setStyleSheet(self.STYLES)
        self.setFixedSize(50, 30)
        # long press
        self.setAutoRepeat(True)
        self.setAutoRepeatDelay(1000)
        self.setAutoRepeatInterval(1000)
        self._state = 0
