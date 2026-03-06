import re


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
