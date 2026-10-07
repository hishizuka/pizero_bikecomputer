"""Course and current-position styling shared by the existing and GPU maps."""

COURSE_LINE_WIDTH = 7
COURSE_OUTLINE_WIDTH = 11
COURSE_DETAIL_MIN_ZOOM = 13
COURSE_ARROW_SPACING = 112
COURSE_ARROW_WIDTH = 16
COURSE_ARROW_OUTLINE_WIDTH = 3
COURSE_WIND_MARKER_SIZE = 42

POSITION_MARKER_SIZE = 29
POSITION_MARKER_BORDER = 2
POSITION_MARKER_CANVAS_SIZE = 37
POSITION_MARKER_COLORS = {"fix": (0, 0, 255), "lost": (170, 170, 170)}

TRACK_COLOR = (0, 170, 255)
TRACK_WIDTH = 4

MAP_LAYER_ORDER = {
    "base": -100,
    "overlay": -90,
    "course": 20,
    "history": 30,
    "tail": 31,
    "wind": 35,
    "position": 40,
    "course_points": 41,
    "center": 50,
    "controls": 60,
    "hud": 70,
    "instruction": 80,
}
MAP_CONTROLS_STYLE = {
    "button_width": 35,
    "button_height": 31,
    "icon_size": 30,
    "padding": 8,
    "spacing": 6,
    "route_spacing": 4,
    "button_radius": 12,
    "group_radius": 8,
}


def course_offset_pixels(
    zoom,
    traffic_side,
    line_width=COURSE_LINE_WIDTH,
    outline_width=COURSE_OUTLINE_WIDTH,
    min_zoom=COURSE_DETAIL_MIN_ZOOM,
):
    if traffic_side == "NONE" or zoom < min_zoom:
        return 0.0
    offset = line_width / 2 + 0.5 if zoom == min_zoom else outline_width / 2
    return offset if traffic_side == "LEFT" else -offset


DEFAULT_COURSE_POINT_ICON_PATH = "img/navi_flag_white.svg"
COURSE_POINT_MARKER_SIZE = 24
COURSE_POINT_ICON_SIZE = 16
COURSE_POINT_MARKER_BG_COLOR = (0, 128, 0, 240)
COURSE_POINT_MARKER_BORDER_COLOR = (0, 0, 0, 220)
COURSE_POINT_MARKER_BORDER_WIDTH = 1
