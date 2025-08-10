from modules._qt_qtwidgets import QtWidgets, QtCore
from modules.pyqt.components.icons import (
    ZoomInIcon,
    ZoomOutIcon,
    LockIcon,
    LockOpenIcon,
    ArrowNorthIcon,
    ArrowSouthIcon,
    ArrowWestIcon,
    ArrowEastIcon,
    DirectionsIcon,
    MapLayersIcon,
    MapNextIcon,
    MapPrevIcon,
)

class MapButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton {
        border-radius: 15px;
        border-style: outset;
        border-width: 1px;
        font-size: 25px;
        color: rgba(0, 0, 0, 192);
        background: rgba(255, 255, 255, 128);
      }

      QPushButton:pressed {
        background-color: rgba(0, 0, 0, 128);
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setStyleSheet(self.STYLES)
        self.setIconSize(QtCore.QSize(30, 30))


class ZoomInButton(MapButton):
    def __init__(self, *args):
        super().__init__(ZoomInIcon(color="black"), "", *args)


class ZoomOutButton(MapButton):
    def __init__(self, *args):
        super().__init__(ZoomOutIcon(color="black"), "", *args)


class LockButton(MapButton):
    def __init__(self, *args):
        self.lock_icon = LockIcon(color="black")
        self.lock_open_icon = LockOpenIcon(color="black")
        super().__init__(self.lock_icon, "", *args)
    
    def change_status(self, status):
        if status:
            self.setIcon(self.lock_icon)
        else:
            self.setIcon(self.lock_open_icon)


class ArrowNorthButton(MapButton):
    def __init__(self, *args):
        super().__init__(ArrowNorthIcon(color="black"), "", *args)


class ArrowSouthButton(MapButton):
    def __init__(self, *args):
        super().__init__(ArrowSouthIcon(color="black"), "", *args)


class ArrowWestButton(MapButton):
    def __init__(self, *args):
        super().__init__(ArrowWestIcon(color="black"), "", *args)


class ArrowEastButton(MapButton):
    def __init__(self, *args):
        super().__init__(ArrowEastIcon(color="black"), "", *args)


class DirectionButton(MapButton):
    def __init__(self, *args):
        super().__init__(DirectionsIcon(color="black"), "", *args)


class MapLayersButton(MapButton):
    def __init__(self, *args):
        super().__init__(MapLayersIcon(color="black"), "", *args)

class MapNextButton(MapButton):
    def __init__(self, *args):
        super().__init__(MapNextIcon(color="black"), "", *args)

class MapPrevButton(MapButton):
    def __init__(self, *args):
        super().__init__(MapPrevIcon(color="black"), "", *args)
