import re


_GADGETBRIDGE_ACTION_TURN_TYPE = {
    "continue": "Straight",
    "left": "Left",
    "left_slight": "Slight Left",
    "left_sharp": "Sharp Left",
    "right": "Right",
    "right_slight": "Slight Right",
    "right_sharp": "Sharp Right",
    "keep_left": "Slight Left",
    "keep_right": "Slight Right",
    "uturn_left": "Uturn Left",
    "uturn_right": "Uturn Right",
    "roundabout_right": "Right",
    "roundabout_left": "Left",
    "roundabout_uturn": "Uturn Right",
    "finish": "Finish",
}
_GADGETBRIDGE_HIDDEN_ACTIONS = {
    "",
    "offroute",
    "roundabout_straight",
}
_GADGETBRIDGE_DISTANCE_FACTORS = {
    "m": 1.0,
    "km": 1000.0,
    "ft": 0.3048,
    "yd": 0.9144,
    "mi": 1609.344,
}
_GADGETBRIDGE_DISTANCE_PATTERN = re.compile(
    r"^\s*([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))\s*([A-Za-z]+)?\s*$"
)


def _normalize_text(text):
    return re.sub(r"[\s_-]+", " ", text).strip().lower()


def _extract_side(normalized_text):
    has_left = "left" in normalized_text
    has_right = "right" in normalized_text
    if has_left and not has_right:
        return "Left"
    if has_right and not has_left:
        return "Right"
    return ""


def normalize_turn_type(point_type):
    if point_type is None:
        return ""

    text = str(point_type).strip()
    if not text:
        return ""

    normalized = _normalize_text(text)
    side = _extract_side(normalized)

    if "uturn" in normalized.replace(" ", "") or "u turn" in normalized:
        if side == "Left":
            return "Uturn Left"
        return "Uturn Right"

    if normalized == "straight":
        return "Straight"
    if normalized == "merge":
        return "Merge"
    if normalized == "keep":
        return "Keep"
    if normalized == "ferry":
        return "Ferry"
    if normalized == "ferry train":
        return "Ferry Train"

    if side:
        if "sharp" in normalized:
            return f"Sharp {side}"
        if any(word in normalized for word in ("slight", "keep", "ramp", "fork")):
            return f"Slight {side}"
        if "roundabout" in normalized:
            return side
        return side

    return text


def maneuver_to_turn_type(maneuver):
    turn_type = normalize_turn_type(maneuver)
    if turn_type in ("", "Straight", "Merge", "Keep", "Ferry", "Ferry Train"):
        return ""
    return turn_type


def gadgetbridge_action_to_turn_type(action):
    if action is None:
        return ""

    normalized = str(action).strip().lower()
    if normalized in _GADGETBRIDGE_HIDDEN_ACTIONS:
        return ""

    return _GADGETBRIDGE_ACTION_TURN_TYPE.get(normalized, "")


def parse_gadgetbridge_distance(distance):
    if distance is None:
        return None

    normalized = str(distance).replace("\u00A0", " ").strip().lower()
    if not normalized:
        return None

    match = _GADGETBRIDGE_DISTANCE_PATTERN.match(normalized)
    if match is None:
        return None

    value = match.group(1).replace(",", ".")
    unit = match.group(2) or "m"

    try:
        distance_value = float(value)
    except ValueError:
        return None

    if distance_value < 0:
        return None

    factor = _GADGETBRIDGE_DISTANCE_FACTORS.get(unit)
    if factor is None:
        return None

    return distance_value * factor
