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
        border-radius: 12px;
        border: 1px solid rgba(0, 0, 0, 192);
        font-size: 25px;
        color: rgba(0, 0, 0, 192);
        background-color: rgba(255, 255, 255, 128);
      }

      QPushButton:pressed {
        background-color: rgba(0, 0, 0, 128);
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setStyleSheet(self.STYLES)
        self.setIconSize(QtCore.QSize(30, 30))


class IconMapButton(MapButton):
    ICON_CLASS = None

    def __init__(self, *args):
        if self.ICON_CLASS is None:
            raise ValueError("ICON_CLASS is not set")
        super().__init__(self.ICON_CLASS(color="black"), "", *args)


class ZoomInButton(IconMapButton):
    ICON_CLASS = ZoomInIcon


class ZoomOutButton(IconMapButton):
    ICON_CLASS = ZoomOutIcon


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


class ArrowNorthButton(IconMapButton):
    ICON_CLASS = ArrowNorthIcon


class ArrowSouthButton(IconMapButton):
    ICON_CLASS = ArrowSouthIcon


class ArrowWestButton(IconMapButton):
    ICON_CLASS = ArrowWestIcon


class ArrowEastButton(IconMapButton):
    ICON_CLASS = ArrowEastIcon


class DirectionButton(IconMapButton):
    ICON_CLASS = DirectionsIcon


class MapLayersButton(IconMapButton):
    ICON_CLASS = MapLayersIcon


class MapNextButton(IconMapButton):
    ICON_CLASS = MapNextIcon


class MapPrevButton(IconMapButton):
    ICON_CLASS = MapPrevIcon
