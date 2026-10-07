from modules._qt_qtwidgets import QtWidgets, QtCore
from modules.map.style import MAP_CONTROLS_STYLE
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


def create_map_button_group(parent):
    group = QtWidgets.QWidget(parent)
    group.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
    group.setStyleSheet(
        "background-color: rgba(255, 255, 255, 128); "
        f"border-radius: {MAP_CONTROLS_STYLE['group_radius']}px;"
    )
    layout = QtWidgets.QVBoxLayout(group)
    layout.setContentsMargins(*(MAP_CONTROLS_STYLE["padding"],) * 4)
    layout.setSpacing(MAP_CONTROLS_STYLE["spacing"])
    return group, layout


def create_map_controls(parent, layout, buttons, actions, has_route):
    """Place the same pointer controls on both QWidget map pages."""
    left, left_layout = create_map_button_group(parent)
    for key in ("lock", "zoomup", "zoomdown"):
        left_layout.addWidget(buttons[key])
    if has_route:
        buttons["go"] = DirectionButton(parent)
        buttons["go"].clicked.connect(actions.search_route)
        left_layout.addSpacing(MAP_CONTROLS_STYLE["route_spacing"])
        left_layout.addWidget(buttons["go"])
    right, right_layout = create_map_button_group(parent)
    buttons["layers"] = MapLayersButton(parent)
    buttons["layers"].clicked.connect(actions.change_map_overlays)
    right_layout.addWidget(buttons["layers"])
    time_group = QtWidgets.QWidget(right)
    time_layout = QtWidgets.QHBoxLayout(time_group)
    time_layout.setContentsMargins(0, 0, 0, 0)
    time_layout.setSpacing(MAP_CONTROLS_STYLE["spacing"])
    for forward, key, button_class in (
        (False, "prev_time", MapPrevButton),
        (True, "next_time", MapNextButton),
    ):
        buttons[key] = button_class(parent)
        buttons[key].clicked.connect(
            lambda checked=False, forward=forward: actions.update_overlay_time(forward)
        )
        time_layout.addWidget(buttons[key])
    right_layout.addWidget(time_group)
    for column, group, side in (
        (0, left, QtCore.Qt.AlignmentFlag.AlignLeft),
        (4, right, QtCore.Qt.AlignmentFlag.AlignRight),
    ):
        layout.addWidget(
            group, 0, column, alignment=QtCore.Qt.AlignmentFlag.AlignTop | side
        )
    return left, right, time_group


class MapButton(QtWidgets.QPushButton):
    STYLES = f"""
      QPushButton {{
        border-radius: {MAP_CONTROLS_STYLE['button_radius']}px;
        border: 1px solid rgba(0, 0, 0, 192);
        font-size: 25px;
        color: rgba(0, 0, 0, 192);
        background-color: rgba(255, 255, 255, 128);
      }}

      QPushButton:pressed {{
        background-color: rgba(0, 0, 0, 128);
      }}
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setStyleSheet(self.STYLES)
        size = MAP_CONTROLS_STYLE["icon_size"]
        self.setIconSize(QtCore.QSize(size, size))

    def sizeHint(self):
        return QtCore.QSize(
            MAP_CONTROLS_STYLE["button_width"], MAP_CONTROLS_STYLE["button_height"]
        )


class IconMapButton(MapButton):
    def __init__(self, *args):
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
